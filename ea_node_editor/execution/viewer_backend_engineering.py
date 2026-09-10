# Purpose: Materialize neutral COREX CAD and FE scenes into lightweight viewer transports.
# Map: subsystems/execution.md
# Tests: tests/test_engineering_viewer_backend.py
# Landmarks: EngineeringViewerBackend materialize/query/export; topology and display-state helpers.
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import warnings
from collections.abc import Mapping
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ea_node_editor.common.coercions import coerce_int
from ea_node_editor.common.scene_protocol import (
    COREX_SCENE_SCHEMA,
    COREX_SCENE_HANDLE_KIND,
    ENGINEERING_VIEWER_BACKEND_ID,
    length_unit_scale,
    normalize_scene_styles,
    validate_engineering_selection_topology,
    validate_scene_bundle,
)
from ea_node_editor.execution.viewer_backend import (
    ViewerBackendMaterializationRequest,
    ViewerBackendMaterializationResult,
    ViewerBackendQueryRequest,
    ViewerBackendQueryResult,
)
from ea_node_editor.runtime_contracts.value_refs import coerce_runtime_handle_ref
from ea_node_editor.runtime_contracts import ENGINEERING_SCENE_DATA_TYPE_ID

if TYPE_CHECKING:
    from ea_node_editor.execution.worker_services import WorkerServices


ENGINEERING_VIEWER_TRANSPORT_KIND = "engineering_scene_bundle"
ENGINEERING_VIEWER_TRANSPORT_SCHEMA = "ea.corex.engineering_scene.v2"
ENGINEERING_VIEWER_SHARED_MEMORY_ASSET_SCHEMA = (
    "ea.corex.engineering_scene.shared_memory_asset.v1"
)

_MAX_SHARED_MEMORY_ASSET_COUNT = 32
_MAX_SHARED_MEMORY_SEGMENT_BYTES = 512 * 1024 * 1024
_MAX_SHARED_MEMORY_TOTAL_BYTES = 1024 * 1024 * 1024
_MAX_SHARED_MEMORY_NAME_BYTES = 255
_MAX_SHARED_MEMORY_DESCRIPTOR_BYTES = 64 * 1024

_STYLE_KEYS = (
    "clim",
    "cmap",
    "color",
    "line_width",
    "opacity",
    "pickable",
    "point_size",
    "representation",
    "scalars",
    "show_edges",
    "smooth_shading",
)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


class EngineeringViewerBackend:
    """Resolve a neutral COREX scene into a lightweight PyVista transport."""

    backend_id = ENGINEERING_VIEWER_BACKEND_ID

    def __init__(self, worker_services: "WorkerServices") -> None:
        self._worker_services = worker_services
        self._session_revisions: dict[tuple[str, str], tuple[str, int]] = {}
        self._session_sources: dict[tuple[str, str], dict[str, Any]] = {}
        self._session_transports: dict[tuple[str, str], dict[str, Any]] = {}
        self._session_shared_memory: dict[
            tuple[str, str], dict[int, tuple[SharedMemory, ...]]
        ] = {}

    def materialize(
        self,
        request: ViewerBackendMaterializationRequest,
    ) -> ViewerBackendMaterializationResult:
        try:
            descriptor = self._resolve_scene_descriptor(request.source_refs)
            layers = self._scene_layers(
                descriptor,
                project_path=request.project_path,
                session_options=request.session_options,
            )
        except (TypeError, ValueError) as exc:
            return self._blocked_result(
                code="scene_contract_invalid",
                reason=f"Engineering scene contract is invalid: {exc}",
                rerun_required=True,
            )
        if any(
            not layer.get("display_path") and layer.get("_prepared_scene") is None
            for layer in layers
        ):
            return self._blocked_result(
                code="display_path_missing",
                reason="The COREX scene does not provide display geometry.",
            )

        missing_paths = []
        validated_selection_topologies: list[
            tuple[Mapping[str, Any], dict[str, Any]]
        ] = []
        for layer in layers:
            has_memory_geometry = layer.get("_prepared_scene") is not None
            for key in ("display_path", "interaction_display_path"):
                path = str(layer.get(key, "")).strip()
                if (
                    path
                    and not Path(path).is_file()
                    and not (key == "display_path" and has_memory_geometry)
                ):
                    missing_paths.append(path)
            for asset in layer.get("geometry_assets", ()):
                asset_map = _mapping(asset)
                role = str(asset_map.get("role", "")).strip().casefold()
                content = str(asset_map.get("content", "")).strip().casefold()
                asset_path = str(asset_map.get("path", "")).strip()
                if (
                    has_memory_geometry
                    and role in {"", "full", "display"}
                    and content in {"", "surface", "mesh"}
                ):
                    continue
                if not asset_path or not Path(asset_path).is_file():
                    if content == "topological_edges":
                        return self._blocked_result(
                            code="topology_edge_file_missing",
                            reason=(
                                "Model viewer topology-edge file is missing: "
                                f"{asset_path or '<unspecified>'}"
                            ),
                            rerun_required=True,
                        )
                    return self._blocked_result(
                        code="declared_geometry_asset_missing",
                        reason=(
                            "Model viewer declared asset is missing: "
                            f"{asset_path or '<unspecified>'}"
                        ),
                        rerun_required=True,
                    )
                if content == "selection_topology":
                    try:
                        topology_bytes = Path(asset_path).read_bytes()
                    except OSError as exc:
                        return self._blocked_result(
                            code="selection_topology_invalid",
                            reason=f"Engineering selection topology cannot be read: {exc}",
                            rerun_required=True,
                        )
                    expected_checksum = (
                        str(asset_map.get("sha256", "")).strip().casefold()
                    )
                    actual_checksum = hashlib.sha256(topology_bytes).hexdigest()
                    if not expected_checksum or actual_checksum != expected_checksum:
                        return self._blocked_result(
                            code="selection_topology_mismatch",
                            reason="Engineering selection topology checksum does not match.",
                            rerun_required=True,
                        )
                    try:
                        payload = validate_engineering_selection_topology(
                            json.loads(topology_bytes.decode("utf-8"))
                        )
                    except (
                        TypeError,
                        UnicodeDecodeError,
                        ValueError,
                        json.JSONDecodeError,
                    ) as exc:
                        return self._blocked_result(
                            code="selection_topology_invalid",
                            reason=f"Engineering selection topology is invalid: {exc}",
                            rerun_required=True,
                        )
                    asset_error = self._selection_capability_asset_error(layer, payload)
                    if asset_error:
                        return self._blocked_result(
                            code="selection_topology_assets_mismatch",
                            reason=asset_error,
                            rerun_required=True,
                        )
                    validated_selection_topologies.append((layer, payload))
                if content != "topological_edges":
                    continue
                edge_path = asset_path
                if not edge_path or not Path(edge_path).is_file():
                    return self._blocked_result(
                        code="topology_edge_file_missing",
                        reason=(
                            "Model viewer topology-edge file is missing: "
                            f"{edge_path or '<unspecified>'}"
                        ),
                        rerun_required=True,
                    )
        if missing_paths:
            return self._blocked_result(
                code="display_file_missing",
                reason=f"Model viewer display file is missing: {missing_paths[0]}",
                rerun_required=True,
            )

        selection_filters = self._selection_filter_summary(
            validated_selection_topologies
        )
        display_bounds = self._combined_display_bounds(layers)
        fit = self._fit_data(
            display_bounds,
            length_unit=str(layers[0].get("length_unit", "")),
        )
        transport = {
            "kind": ENGINEERING_VIEWER_TRANSPORT_KIND,
            "schema": ENGINEERING_VIEWER_TRANSPORT_SCHEMA,
            "backend_id": self.backend_id,
            "status": "ready",
            "layers": layers,
            "display_bounds": display_bounds,
            "fit": fit,
        }
        try:
            shared_memory_payloads = self._prepare_shared_memory_payloads(
                layers,
            )
        except Exception:  # noqa: BLE001
            return self._blocked_result(
                code="shared_memory_transport_invalid",
                reason="Engineering scene shared-memory transport could not be prepared.",
                rerun_required=True,
            )
        signature = self._transport_signature(transport)
        session_key = (str(request.workspace_id), str(request.session_id))
        previous_signature, previous_revision = self._session_revisions.get(
            session_key, ("", 0)
        )
        previous_revision = max(
            previous_revision,
            coerce_int(request.session_summary.get("transport_revision"), default=0),
        )
        force_recompute = _truthy(request.request_options.get("force_recompute"))
        reuse_revision = (
            previous_revision > 0
            and signature == previous_signature
            and not force_recompute
            and session_key in self._session_transports
        )
        revision = previous_revision if reuse_revision else previous_revision + 1
        if reuse_revision:
            transport = copy.deepcopy(self._session_transports[session_key])
            layers = [
                _mapping(value)
                for value in transport.get("layers", ())
                if isinstance(value, Mapping)
            ]
        else:
            try:
                segments = self._allocate_shared_memory(
                    shared_memory_payloads,
                )
            except Exception:  # noqa: BLE001
                return self._blocked_result(
                    code="shared_memory_transport_unavailable",
                    reason="Engineering scene shared-memory transport is unavailable.",
                    rerun_required=True,
                )
            self._session_shared_memory.setdefault(session_key, {})[revision] = segments
        self._session_revisions[session_key] = (signature, revision)
        self._session_sources[session_key] = dict(request.source_refs)
        transport["transport_revision"] = revision
        self._session_transports[session_key] = copy.deepcopy(transport)

        warnings = self._composition_warnings(layers)
        display_capabilities = {
            **_mapping(request.session_summary.get("capabilities")),
            **self._display_capabilities(
                layers,
                selection_summary=selection_filters,
            ),
        }
        scene_summaries = {
            str(item.get("id", "")): dict(item)
            for item in request.session_summary.get("scene_layers", [])
            if isinstance(item, Mapping)
        }
        return ViewerBackendMaterializationResult(
            backend_id=self.backend_id,
            transport=copy.deepcopy(transport),
            transport_revision=revision,
            live_open_status="ready",
            camera_state=_mapping(request.session_summary.get("camera_state")),
            summary={
                "viewer_kind": "engineering_scene",
                "scene_layer_count": len(layers),
                "display_bounds": display_bounds,
                "fit": fit,
                "capabilities": display_capabilities,
                "supported_render_modes": self._supported_render_modes(
                    display_capabilities
                ),
                "supported_selection_filters": selection_filters["filters"],
                "default_selection_filter": selection_filters["default"],
                "scene_layers": [
                    {
                        **scene_summaries.get(str(layer["id"]), {}),
                        "id": str(layer["id"]),
                        "name": str(layer.get("name", "")),
                        "length_unit": str(layer.get("length_unit", "")),
                        "visible": bool(layer.get("visible", True)),
                        "source_kind": str(layer.get("source_kind", "")),
                        "display_format": Path(str(layer.get("display_path", "")))
                        .suffix.casefold()
                        .lstrip("."),
                        "result_fields": copy.deepcopy(layer.get("result_fields", [])),
                        "time_steps": list(layer.get("time_steps", [])),
                        "bounds": list(layer.get("bounds", [])),
                    }
                    for layer in layers
                ],
                "model_tree": [
                    {
                        **dict(item),
                        "layer_id": str(layer["id"]),
                        "layer_name": str(layer.get("name", "")),
                        "id": (f"{layer['id']}:{item.get('id', '')}"),
                        "parent_id": (
                            f"{layer['id']}:{item.get('parent_id', '')}"
                            if str(item.get("parent_id", "")).strip()
                            else ""
                        ),
                    }
                    for layer in layers
                    for item in layer.get("hierarchy", ())
                    if isinstance(item, Mapping)
                ],
                "warnings": warnings,
            },
        )

    def release_session_transport(self, *, workspace_id: str, session_id: str) -> None:
        key = (str(workspace_id), str(session_id))
        self._release_shared_memory(key)
        self._session_revisions.pop(key, None)
        self._session_sources.pop(key, None)
        self._session_transports.pop(key, None)

    def release_workspace_transport(self, *, workspace_id: str) -> None:
        normalized_workspace_id = str(workspace_id)
        keys = set(self._session_revisions) | set(self._session_shared_memory)
        for key in tuple(keys):
            if key[0] == normalized_workspace_id:
                self._release_shared_memory(key)
                self._session_revisions.pop(key, None)
                self._session_sources.pop(key, None)
                self._session_transports.pop(key, None)

    def reset(self) -> None:
        for key in tuple(self._session_shared_memory):
            self._release_shared_memory(key)
        self._session_revisions.clear()
        self._session_sources.clear()
        self._session_transports.clear()

    def query(self, request: ViewerBackendQueryRequest) -> ViewerBackendQueryResult:
        session_key = (request.workspace_id, request.session_id)
        source_refs = self._session_sources.get(session_key)
        if source_refs is None:
            return ViewerBackendQueryResult(
                supported=False,
                explanation="The engineering scene is not materialized in this worker session.",
            )
        query_type = str(request.query_type).strip().casefold()
        transport = _mapping(request.transport) or self._session_transports.get(
            session_key, {}
        )
        if query_type == "bounds":
            fit = _mapping(transport.get("fit"))
            return ViewerBackendQueryResult(
                supported=True,
                value={
                    "bounds": self._coerce_bounds(transport.get("display_bounds")),
                    "fit": fit,
                    "length_unit": str(fit.get("length_unit", "")),
                },
            )
        if query_type == "export":
            return self._export_query(
                request=request, source_refs=source_refs, transport=transport
            )
        entity_ids = {
            str(entity.get("layer_id", "")).strip()
            for key in ("entity", "entity_a", "entity_b", "vertex_entity")
            if isinstance(entity := request.payload.get(key), Mapping)
            and str(entity.get("layer_id", "")).strip()
        }
        requested_id = str(request.payload.get("layer_id", "")).strip()
        if len(entity_ids) > 1 or (
            entity_ids and requested_id and requested_id not in entity_ids
        ):
            return ViewerBackendQueryResult(
                supported=False,
                explanation="Entity geometry queries require entities from one scene.",
            )
        order = source_refs["scene_order"]
        layer_id = (
            next(iter(entity_ids), "")
            or requested_id
            or str(request.session_options.get("active_scene_id", "")).strip()
            or order[0]
        )
        if layer_id not in order:
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"Scene {layer_id!r} is not in the displayed composition.",
            )
        prepared = self._resolve_prepared_scene(source_refs.get(f"scene:{layer_id}"))
        if prepared is None:
            return ViewerBackendQueryResult(
                supported=False,
                explanation="This scene transport does not retain queryable engineering data.",
            )
        if query_type == "entity_info":
            result = self._entity_info_query(prepared, request.payload)
            if result.supported:
                return ViewerBackendQueryResult(
                    supported=True, value={**result.value, "layer_id": layer_id}
                )
            return result
        if query_type in {"distance", "shortest_distance"}:
            return self._distance_query(
                prepared,
                request.payload,
                length_unit=prepared.descriptor.length_unit,
                shortest=query_type == "shortest_distance",
            )
        if query_type == "angle":
            return self._angle_query(prepared, request.payload)
        if query_type in {"coordinates", "coordinate"}:
            point = self._measurement_point(
                prepared, request.payload, point_key="point", entity_key="entity"
            )
            if point is None:
                return ViewerBackendQueryResult(
                    supported=False,
                    explanation="Coordinates require one finite point.",
                )
            return ViewerBackendQueryResult(
                supported=True,
                value={
                    "point": list(point),
                    "length_unit": prepared.descriptor.length_unit,
                },
            )
        if query_type in {"radius", "diameter"}:
            return self._radius_query(prepared, request.payload)
        if query_type == "mass_properties":
            return self._mass_properties_query(prepared)
        return ViewerBackendQueryResult(
            supported=False,
            explanation=f"Model viewer query '{request.query_type}' is not supported.",
        )

    def _resolve_prepared_scene(self, value: Any) -> Any | None:
        runtime_ref = coerce_runtime_handle_ref(value)
        if (
            runtime_ref is None
            or runtime_ref.data_type_id != ENGINEERING_SCENE_DATA_TYPE_ID
            or runtime_ref.kind != COREX_SCENE_HANDLE_KIND
        ):
            return None
        resolved = self._worker_services.resolve_handle(
            runtime_ref,
            expected_data_type=ENGINEERING_SCENE_DATA_TYPE_ID,
            expected_kind=COREX_SCENE_HANDLE_KIND,
        )
        if not hasattr(resolved, "descriptor") or not hasattr(resolved, "dataset"):
            return None
        return resolved

    @staticmethod
    def _point(value: Any) -> tuple[float, float, float] | None:
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            return None
        try:
            point = tuple(float(item) for item in value)
        except (TypeError, ValueError):
            return None
        return point if all(math.isfinite(item) for item in point) else None  # type: ignore[return-value]

    def _entity_info_query(
        self,
        prepared: Any,
        payload: Mapping[str, Any],
    ) -> ViewerBackendQueryResult:
        raw_entity = payload.get("entity")
        entity = (
            _mapping(raw_entity)
            if isinstance(raw_entity, Mapping)
            else _mapping(payload)
        )
        kind = str(entity.get("entity_kind", entity.get("kind", ""))).strip().casefold()
        kind = {"node": "point", "element": "cell"}.get(kind, kind)
        entity_id = str(entity.get("entity_id", entity.get("id", ""))).strip()
        if not kind or not entity_id:
            return ViewerBackendQueryResult(
                supported=False,
                explanation="Entity information requires entity_kind and entity_id.",
            )

        topology = _mapping(prepared.descriptor.topology_mappings)
        topology_kind = {"body": "bodies", "face": "faces", "edge": "edges"}.get(
            kind,
            kind,
        )
        mapping = _mapping(topology.get(f"{kind}_ids", topology.get(topology_kind)))
        entities = mapping.get("entities", mapping.get("values"))
        value: dict[str, Any] = {}
        if isinstance(entities, Mapping) and entity_id in entities:
            value = _mapping(entities[entity_id])
        elif isinstance(entities, (list, tuple)):
            value = next(
                (
                    _mapping(item)
                    for item in entities
                    if isinstance(item, Mapping)
                    and str(item.get("id", "")).strip() == entity_id
                ),
                {},
            )
        if value:
            value.update(
                {
                    "entity_kind": kind,
                    "entity_id": entity_id,
                    "stable_for_source_fingerprint": bool(
                        mapping.get("stable_for_source_fingerprint", False)
                    ),
                }
            )
            return ViewerBackendQueryResult(supported=True, value=value)

        if kind in {"scene", "block"}:
            for item in prepared.descriptor.hierarchy:
                if str(item.get("id", "")).strip() == entity_id:
                    return ViewerBackendQueryResult(
                        supported=True,
                        value={
                            **dict(item),
                            "entity_kind": kind,
                            "entity_id": entity_id,
                        },
                    )
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"Unknown {kind} entity id {entity_id!r}.",
            )

        if kind not in {"point", "cell"} or not mapping:
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"The scene has no queryable {kind or 'entity'} topology mapping.",
            )
        policy = str(mapping.get("policy", "")).strip()
        if policy not in {
            "block_local_index",
            "global_index",
            "source_array_or_block_local_index",
        }:
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"The {kind} topology mapping policy is not queryable.",
            )

        leaves = self._dataset_leaves(prepared.dataset)
        block_value = entity.get(
            "block_index",
            entity.get("block_id", payload.get("block_index", payload.get("block_id"))),
        )
        if len(leaves) > 1 and block_value in {None, ""}:
            return ViewerBackendQueryResult(
                supported=False,
                explanation="Block-local entity information requires block_index for a multi-block scene.",
            )
        block_records = topology.get("blocks")
        block_records = (
            list(block_records) if isinstance(block_records, (list, tuple)) else []
        )
        try:
            block_index = int(block_value) if block_value not in {None, ""} else 0
        except (TypeError, ValueError):
            block_index = next(
                (
                    index
                    for index, block in enumerate(block_records)
                    if str(_mapping(block).get("block_id", "")) == str(block_value)
                ),
                -1,
            )
        if block_index < 0 or block_index >= len(leaves):
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"Block index {block_value!r} is unavailable.",
            )
        dataset = leaves[block_index]
        block_record = (
            _mapping(block_records[block_index])
            if block_index < len(block_records)
            else {}
        )
        source_array_name = str(block_record.get(f"{kind}_id_array", "")).strip()
        source_container = getattr(
            dataset, "point_data" if kind == "point" else "cell_data", {}
        )
        if source_array_name and source_array_name in source_container:
            source_values = source_container[source_array_name]
            index = next(
                (
                    candidate_index
                    for candidate_index, source_value in enumerate(source_values)
                    if str(self._json_value(source_value)) == entity_id
                ),
                -1,
            )
            if index < 0:
                return ViewerBackendQueryResult(
                    supported=False,
                    explanation=f"Unknown source {kind} entity id {entity_id!r}.",
                )
        else:
            try:
                index = int(entity_id)
            except ValueError:
                return ViewerBackendQueryResult(
                    supported=False,
                    explanation=f"{kind.title()} entity id must be a non-negative integer.",
                )
            if index < 0:
                return ViewerBackendQueryResult(
                    supported=False,
                    explanation=f"{kind.title()} entity id must be a non-negative integer.",
                )
        count = int(getattr(dataset, "n_points" if kind == "point" else "n_cells", 0))
        if index >= count:
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"{kind.title()} entity id {entity_id!r} is outside the scene topology.",
            )

        value: dict[str, Any] = {
            "entity_kind": kind,
            "entity_id": entity_id,
            "block_index": block_index,
            "mapping_policy": str(mapping.get("policy", "")),
            "stable_for_source_fingerprint": bool(
                mapping.get("stable_for_source_fingerprint", False)
            ),
        }
        if kind == "point":
            value["coordinates"] = self._json_value(dataset.points[index])
            value["data"] = self._indexed_data(
                getattr(dataset, "point_data", {}), index
            )
        else:
            cell = dataset.get_cell(index)
            value.update(
                {
                    "bounds": self._json_value(getattr(cell, "bounds", ())),
                    "center": self._json_value(getattr(cell, "center", ())),
                    "point_ids": self._json_value(getattr(cell, "point_ids", ())),
                    "dimension": int(getattr(cell, "dimension", 0)),
                    "cell_type": str(getattr(cell, "type", "")),
                    "data": self._indexed_data(
                        getattr(dataset, "cell_data", {}), index
                    ),
                }
            )
        return ViewerBackendQueryResult(supported=True, value=value)

    @classmethod
    def _dataset_leaves(cls, dataset: Any) -> list[Any]:
        if hasattr(dataset, "n_points") and hasattr(dataset, "n_cells"):
            return [dataset]
        leaves: list[Any] = []
        try:
            values = list(dataset)
        except TypeError:
            return leaves
        for value in values:
            if value is not None:
                leaves.extend(cls._dataset_leaves(value))
        return leaves

    @staticmethod
    def _json_value(value: Any) -> Any:
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            return tolist()
        item = getattr(value, "item", None)
        if callable(item):
            try:
                return item()
            except ValueError:
                pass
        if isinstance(value, tuple):
            return list(value)
        return value

    @classmethod
    def _indexed_data(cls, container: Any, index: int) -> dict[str, Any]:
        if not isinstance(container, Mapping):
            return {}
        result: dict[str, Any] = {}
        for name in container.keys():
            try:
                result[str(name)] = cls._json_value(container[name][index])
            except (IndexError, KeyError, TypeError):
                continue
        return result

    def _measurement_point(
        self,
        prepared: Any,
        payload: Mapping[str, Any],
        *,
        point_key: str,
        entity_key: str,
    ) -> tuple[float, float, float] | None:
        point = self._point(payload.get(point_key))
        if point is not None:
            return point
        entity = payload.get(entity_key)
        if not isinstance(entity, Mapping):
            return None
        info = self._entity_info_query(prepared, {"entity": entity})
        if not info.supported or str(info.value.get("entity_kind", "")) != "point":
            return None
        return self._point(info.value.get("coordinates"))

    def _distance_query(
        self,
        prepared: Any,
        payload: Mapping[str, Any],
        *,
        length_unit: str,
        shortest: bool,
    ) -> ViewerBackendQueryResult:
        first = self._measurement_point(
            prepared,
            payload,
            point_key="point_a",
            entity_key="entity_a",
        )
        second = self._measurement_point(
            prepared,
            payload,
            point_key="point_b",
            entity_key="entity_b",
        )
        if first is None or second is None:
            return ViewerBackendQueryResult(
                supported=False,
                explanation=(
                    "Shortest distance is available only for two points or point entities."
                    if shortest
                    else "Distance requires two finite points or point entities."
                ),
            )
        distance = math.dist(first, second)
        return ViewerBackendQueryResult(
            supported=True,
            value={
                "distance": distance,
                "length_unit": length_unit,
                "method": "point_to_point",
            },
        )

    def _angle_query(
        self, prepared: Any, payload: Mapping[str, Any]
    ) -> ViewerBackendQueryResult:
        first = self._measurement_point(
            prepared,
            payload,
            point_key="point_a",
            entity_key="entity_a",
        )
        vertex = self._measurement_point(
            prepared,
            payload,
            point_key="vertex",
            entity_key="vertex_entity",
        )
        second = self._measurement_point(
            prepared,
            payload,
            point_key="point_b",
            entity_key="entity_b",
        )
        if first is None or vertex is None or second is None:
            return ViewerBackendQueryResult(
                supported=False,
                explanation="Angle requires finite point_a, vertex, and point_b coordinates.",
            )
        vector_a = tuple(first[index] - vertex[index] for index in range(3))
        vector_b = tuple(second[index] - vertex[index] for index in range(3))
        norm_a = math.sqrt(sum(value * value for value in vector_a))
        norm_b = math.sqrt(sum(value * value for value in vector_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return ViewerBackendQueryResult(
                supported=False,
                explanation="Angle is unavailable for a zero-length direction.",
            )
        cosine = sum(a * b for a, b in zip(vector_a, vector_b, strict=True)) / (
            norm_a * norm_b
        )
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
        return ViewerBackendQueryResult(supported=True, value={"angle_degrees": angle})

    def _radius_query(
        self,
        prepared: Any,
        payload: Mapping[str, Any],
    ) -> ViewerBackendQueryResult:
        entity = payload.get("entity")
        if not isinstance(entity, Mapping):
            return ViewerBackendQueryResult(
                supported=False,
                explanation=(
                    "Radius and diameter require circular topology metadata; "
                    "COREX does not infer a radius from arbitrary center/point coordinates."
                ),
            )
        info = self._entity_info_query(prepared, {"entity": entity})
        if not info.supported:
            return info
        try:
            radius = float(info.value.get("radius"))
        except (TypeError, ValueError):
            try:
                radius = float(info.value.get("diameter")) / 2.0
            except (TypeError, ValueError):
                return ViewerBackendQueryResult(
                    supported=False,
                    explanation="The selected entity has no exact circular radius metadata.",
                )
        if not math.isfinite(radius) or radius < 0.0:
            return ViewerBackendQueryResult(
                supported=False,
                explanation="The selected entity has invalid circular radius metadata.",
            )
        return ViewerBackendQueryResult(
            supported=True,
            value={
                "radius": radius,
                "diameter": radius * 2.0,
                "length_unit": prepared.descriptor.length_unit,
                "entity": info.value,
            },
        )

    @staticmethod
    def _mass_properties_query(prepared: Any) -> ViewerBackendQueryResult:
        if str(prepared.descriptor.source_kind).strip().casefold() != "cad":
            return ViewerBackendQueryResult(
                supported=False,
                explanation=(
                    "Mass properties are unavailable for FE datasets without explicit physical-property data."
                ),
            )
        if prepared.exact_model is not None:
            try:
                return EngineeringViewerBackend._exact_mass_properties(
                    prepared.exact_model,
                    length_unit=prepared.descriptor.length_unit,
                )
            except Exception as exc:  # noqa: BLE001
                return ViewerBackendQueryResult(
                    supported=False,
                    explanation=f"Exact CAD mass properties failed: {exc}",
                )
        dataset = prepared.dataset
        extract_surface = getattr(dataset, "extract_surface", None)
        surface = (
            extract_surface(algorithm=None).triangulate()
            if callable(extract_surface)
            else dataset
        )
        is_manifold = bool(getattr(surface, "is_manifold", False))
        if not is_manifold:
            return ViewerBackendQueryResult(
                supported=False,
                explanation=(
                    "Volume and centre properties are unavailable because the tessellated body "
                    "is not watertight."
                ),
            )
        center_of_mass = getattr(surface, "center_of_mass", None)
        center = (
            list(center_of_mass())
            if callable(center_of_mass)
            else list(getattr(surface, "center", ()))
        )
        return ViewerBackendQueryResult(
            supported=True,
            value={
                "method": "mesh_derived",
                "surface_area": float(getattr(surface, "area", 0.0)),
                "volume": float(getattr(surface, "volume", 0.0)),
                "center_of_mass": center,
                "length_unit": prepared.descriptor.length_unit,
                "inertia": None,
            },
            explanation="Values are mesh-derived; inertia requires an exact CAD body.",
        )

    @staticmethod
    def _exact_mass_properties(
        shape: Any, *, length_unit: str
    ) -> ViewerBackendQueryResult:
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps

        volume_props = GProp_GProps()
        surface_props = GProp_GProps()
        volume_method = getattr(BRepGProp, "VolumeProperties_s", None)
        surface_method = getattr(BRepGProp, "SurfaceProperties_s", None)
        if not callable(volume_method) or not callable(surface_method):
            raise RuntimeError(
                "Installed OCP does not expose exact BRepGProp property functions."
            )
        volume_method(shape, volume_props)
        surface_method(shape, surface_props)
        centre = volume_props.CentreOfMass()
        inertia = volume_props.MatrixOfInertia()
        return ViewerBackendQueryResult(
            supported=True,
            value={
                "method": "exact_brep",
                "surface_area": float(surface_props.Mass()),
                "volume": float(volume_props.Mass()),
                "center_of_mass": [
                    float(centre.X()),
                    float(centre.Y()),
                    float(centre.Z()),
                ],
                "inertia": [
                    [float(inertia.Value(row, column)) for column in range(1, 4)]
                    for row in range(1, 4)
                ],
                "length_unit": length_unit,
            },
        )

    def _export_query(
        self,
        *,
        request: ViewerBackendQueryRequest,
        source_refs: Mapping[str, Any],
        transport: Mapping[str, Any],
    ) -> ViewerBackendQueryResult:
        payload = request.payload
        output_path = Path(str(payload.get("path", "")).strip()).expanduser()
        export_format = (
            str(payload.get("format", output_path.suffix.lstrip(".")))
            .strip()
            .casefold()
        )
        if not output_path.name:
            return ViewerBackendQueryResult(
                supported=False,
                explanation="Export requires an output path.",
            )
        display_state = _mapping(payload.get("display_state"))
        if any(
            key in payload or key in display_state
            for key in ("visible_entity_ids", "hidden_entity_ids", "entity_visibility")
        ):
            return ViewerBackendQueryResult(
                supported=False,
                explanation="Part/entity-level export visibility is unavailable without exact topology mapping.",
            )
        layers = self._visible_export_layers(
            source_refs=source_refs,
            transport=transport,
            session_options=request.session_options,
            payload=payload,
        )
        if not layers:
            return ViewerBackendQueryResult(
                supported=False,
                explanation="Export has no visible engineering scene layers.",
            )

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            extra: dict[str, Any] = {}
            if export_format in {"step", "stp"}:
                shapes = [
                    layer["prepared"].exact_model
                    for layer in layers
                    if layer["prepared"].exact_model is not None
                ]
                if not shapes:
                    return ViewerBackendQueryResult(
                        supported=False,
                        explanation="STEP export requires at least one visible exact CAD layer.",
                    )
                shape = self._compound_shape(shapes)
                from OCP.IFSelect import IFSelect_RetDone
                from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

                writer = STEPControl_Writer()
                writer.Transfer(shape, STEPControl_AsIs)
                if writer.Write(str(output_path)) != IFSelect_RetDone:
                    return ViewerBackendQueryResult(
                        supported=False,
                        explanation="OCP could not write the STEP export.",
                    )
                extra["skipped_non_exact_layers"] = [
                    layer["name"]
                    for layer in layers
                    if layer["prepared"].exact_model is None
                ]
            elif export_format in {"vtk", "vtu", "vtm"}:
                vtk_result = self._write_vtk_export(
                    output_path, export_format=export_format, layers=layers
                )
                if vtk_result is not None:
                    return vtk_result
                extra["source_coordinates"] = True
            elif export_format in {"gltf", "glb"}:
                gltf_result = self._write_gltf_export(
                    output_path,
                    export_format=export_format,
                    layers=layers,
                    session_options=request.session_options,
                    display_state=display_state,
                )
                if gltf_result is not None:
                    return gltf_result
                extra["display_coordinates"] = True
            else:
                return ViewerBackendQueryResult(
                    supported=False,
                    explanation=f"Engineering export format '{export_format}' is not supported.",
                )
        except Exception as exc:  # noqa: BLE001
            output_path.unlink(missing_ok=True)
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"Engineering {export_format or 'scene'} export failed: {exc}",
            )
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            return ViewerBackendQueryResult(
                supported=False,
                explanation="The export writer did not produce a non-empty file.",
            )
        return ViewerBackendQueryResult(
            supported=True,
            value={
                "path": str(output_path.resolve()),
                "format": export_format,
                "visible_layers": [layer["name"] for layer in layers],
                "visible_layer_ids": [layer["id"] for layer in layers],
                "display_state_applied": True,
                **extra,
            },
        )

    def _visible_export_layers(
        self,
        *,
        source_refs: Mapping[str, Any],
        transport: Mapping[str, Any],
        session_options: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        transport_layers = transport.get("layers", [])
        display_state = _mapping(payload.get("display_state"))
        visibility: dict[str, Any] = {}
        for candidate in (
            session_options.get("layer_visibility"),
            display_state.get("layer_visibility"),
            payload.get("layer_visibility"),
        ):
            visibility.update(_mapping(candidate))
        visible_ids_value = payload.get(
            "visible_layers", display_state.get("visible_layers")
        )
        visible_ids = (
            {str(value).strip() for value in visible_ids_value if str(value).strip()}
            if isinstance(visible_ids_value, (list, tuple, set, frozenset))
            else None
        )

        scene_styles = normalize_scene_styles(
            display_state.get("scene_styles", session_options.get("scene_styles", {}))
        )
        layers: list[dict[str, Any]] = []
        for layer in transport_layers:
            layer_id = str(layer["id"])
            resolved = self._resolve_prepared_scene(
                source_refs.get(f"scene:{layer_id}")
            )
            if resolved is None:
                continue
            name = str(layer["name"])
            visible = bool(layer.get("visible", True))
            if layer_id in visibility:
                visible = _truthy(visibility[layer_id])
            if visible_ids is not None:
                visible = layer_id in visible_ids
            if not visible:
                continue
            style = _mapping(layer.get("style"))
            style["representation"] = display_state.get(
                "representation",
                session_options.get(
                    "representation", style.get("representation", "surface")
                ),
            )
            style["show_edges"] = display_state.get(
                "show_mesh_edges",
                session_options.get("show_mesh_edges", style.get("show_edges", False)),
            )
            scene_style = scene_styles.get(layer_id, {})
            if scene_style:
                style["opacity"] = scene_style.get("opacity", 1.0)
                if scene_style.get("color"):
                    style["color"] = scene_style["color"]
            layers.append(
                {
                    "name": name,
                    "id": layer_id,
                    "prepared": resolved,
                    "scale_factor": float(layer.get("scale_factor", 1.0) or 1.0),
                    "style": style,
                    "attribute_colors": _mapping(layer.get("attribute_colors")),
                }
            )
        return layers

    @staticmethod
    def _compound_shape(shapes: list[Any]) -> Any:
        if len(shapes) == 1:
            return shapes[0]
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Compound

        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        for shape in shapes:
            builder.Add(compound, shape)
        return compound

    @staticmethod
    def _write_vtk_export(
        output_path: Path,
        *,
        export_format: str,
        layers: list[dict[str, Any]],
    ) -> ViewerBackendQueryResult | None:
        if export_format == "vtm":
            import pyvista as pv

            dataset = pv.MultiBlock()
            for layer in layers:
                dataset.append(
                    layer["prepared"].dataset.copy(deep=True), name=layer["name"]
                )
            dataset.save(output_path)
            return None
        if len(layers) != 1:
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"{export_format.upper()} export supports one visible layer; use VTM for several layers.",
            )
        dataset = layers[0]["prepared"].dataset
        if not hasattr(dataset, "n_points") or not hasattr(dataset, "n_cells"):
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"{export_format.upper()} cannot represent a multi-block scene; use VTM.",
            )
        if export_format == "vtu":
            cast = getattr(dataset, "cast_to_unstructured_grid", None)
            if not callable(cast):
                return ViewerBackendQueryResult(
                    supported=False,
                    explanation="VTU export requires a dataset convertible to an unstructured grid.",
                )
            dataset = cast()
        save = getattr(dataset, "save", None)
        if not callable(save):
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"The visible scene cannot be written as {export_format.upper()}.",
            )
        save(output_path)
        return None

    def _write_gltf_export(
        self,
        output_path: Path,
        *,
        export_format: str,
        layers: list[dict[str, Any]],
        session_options: Mapping[str, Any],
        display_state: Mapping[str, Any],
    ) -> ViewerBackendQueryResult | None:
        required_suffix = f".{export_format}"
        if output_path.suffix.casefold() != required_suffix:
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"{export_format.upper()} export requires a {required_suffix} output path.",
            )
        deform_value = display_state.get(
            "deform_scale", session_options.get("deform_scale", 0.0)
        )
        try:
            deformation_active = float(deform_value or 0.0) != 0.0
        except (TypeError, ValueError):
            deformation_active = str(deform_value).strip().casefold() == "auto"
        if deformation_active:
            return ViewerBackendQueryResult(
                supported=False,
                explanation="glTF/GLB export cannot honor active deformation until deformation is materialized.",
            )
        if display_state.get("active_field") or session_options.get("active_field"):
            return ViewerBackendQueryResult(
                supported=False,
                explanation="glTF/GLB export cannot honor an active scalar field until display colors are materialized.",
            )
        for layer in layers:
            style = layer["style"]
            representation = (
                str(style.get("representation", "surface")).strip().casefold()
            )
            if representation != "surface" or _truthy(style.get("show_edges")):
                return ViewerBackendQueryResult(
                    supported=False,
                    explanation="glTF/GLB export currently supports surface display without edge overlays.",
                )

        import numpy as np
        import pyvista as pv
        from vtkmodules.vtkIOGeometry import vtkGLTFWriter

        scene = pv.MultiBlock()
        for layer in layers:
            layer_block = pv.MultiBlock()
            style = layer["style"]
            color = self._rgba_color(
                style.get("color", "#d0d7de"), opacity=style.get("opacity", 1.0)
            )
            attribute_colors = _mapping(layer.get("attribute_colors"))
            source_color_array = (
                str(attribute_colors.get("array_name", ""))
                if attribute_colors.get("available") and not style.get("color")
                else ""
            )
            for piece_index, leaf in enumerate(
                self._dataset_leaves(layer["prepared"].dataset)
            ):
                extract_surface = getattr(leaf, "extract_surface", None)
                surface = (
                    extract_surface(algorithm=None)
                    if callable(extract_surface)
                    else leaf
                )
                triangulate = getattr(surface, "triangulate", None)
                surface = triangulate() if callable(triangulate) else surface
                surface = surface.copy(deep=True)
                if source_color_array in surface.cell_data:
                    # Keep authored face colors sharp when exporting point colors.
                    surface = (
                        surface.separate_cells()
                        .extract_surface(algorithm=None)
                        .cell_data_to_point_data()
                    )
                scale_factor = float(layer["scale_factor"])
                if scale_factor != 1.0:
                    surface.scale(
                        (scale_factor, scale_factor, scale_factor), inplace=True
                    )
                if int(getattr(surface, "n_points", 0)) > 0:
                    colors = np.tile(
                        np.asarray(color, dtype=np.uint8),
                        (int(surface.n_points), 1),
                    )
                    if source_color_array in surface.point_data:
                        authored = np.asarray(surface.point_data[source_color_array])
                        if authored.ndim == 2 and authored.shape[1] in {3, 4}:
                            colors[:, :3] = authored[:, :3]
                            if authored.shape[1] == 4:
                                colors[:, 3] = np.rint(
                                    authored[:, 3].astype(float)
                                    * float(style.get("opacity", 1.0))
                                ).astype(np.uint8)
                            mask_name = str(attribute_colors.get("valid_mask_name", ""))
                            if mask_name in surface.point_data:
                                colors[
                                    ~np.asarray(
                                        surface.point_data[mask_name], dtype=bool
                                    )
                                ] = color
                    surface.point_data["COLOR_0"] = colors
                layer_block.append(surface, name=f"piece_{piece_index}")
            scene.append(layer_block, name=layer["name"])

        writer = vtkGLTFWriter()
        writer.SetInputDataObject(scene)
        writer.SetFileName(str(output_path))
        writer.SetInlineData(True)
        if writer.Write() != 1:
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"VTK could not write the {export_format.upper()} scene.",
            )
        if export_format == "glb":
            with output_path.open("rb") as stream:
                if stream.read(4) != b"glTF":
                    output_path.unlink(missing_ok=True)
                    return ViewerBackendQueryResult(
                        supported=False,
                        explanation="VTK did not produce a binary GLB payload.",
                    )
        return None

    @staticmethod
    def _rgba_color(value: Any, *, opacity: Any) -> tuple[int, int, int, int]:
        token = str(value or "").strip().lstrip("#")
        if len(token) != 6:
            token = "d0d7de"
        try:
            rgb = tuple(int(token[index : index + 2], 16) for index in (0, 2, 4))
        except ValueError:
            rgb = (208, 215, 222)
        try:
            alpha = round(max(0.0, min(1.0, float(opacity))) * 255.0)
        except (TypeError, ValueError):
            alpha = 255
        return rgb[0], rgb[1], rgb[2], alpha

    def _resolve_scene_descriptor(
        self, source_refs: Mapping[str, Any]
    ) -> dict[str, Any]:
        order = source_refs.get("scene_order")
        if not isinstance(order, (list, tuple)) or not order:
            raise ValueError(
                "Model viewer materialization requires ordered scene sources."
            )
        if any(not isinstance(value, str) or not value.strip() for value in order):
            raise ValueError("Scene IDs must be non-empty strings.")
        if len(set(order)) != len(order):
            raise ValueError("Scene IDs must be unique.")
        labels = _mapping(source_refs.get("scene_labels"))
        layers = []
        for index, layer_id in enumerate(order, start=1):
            scene_value = source_refs.get(f"scene:{layer_id}")
            if scene_value is None:
                raise ValueError(f"Scene input {layer_id!r} has no source.")
            try:
                layer = self._resolve_scene_value(scene_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Scene input {layer_id!r}: {exc}") from exc
            layers.append(
                {
                    **layer,
                    "id": layer_id,
                    "name": str(labels.get(layer_id, f"Scene {index}")),
                }
            )
        return {"layers": layers}

    def _resolve_scene_value(self, scene_value: Any) -> dict[str, Any]:
        runtime_ref = coerce_runtime_handle_ref(scene_value)
        if runtime_ref is None:
            descriptor = self._descriptor(scene_value)
            return (
                validate_scene_bundle(descriptor)
                if descriptor.get("schema") == COREX_SCENE_SCHEMA
                else descriptor
            )
        if (
            runtime_ref.data_type_id != ENGINEERING_SCENE_DATA_TYPE_ID
            or runtime_ref.kind != COREX_SCENE_HANDLE_KIND
        ):
            raise TypeError(
                "Model viewer requires semantic type "
                f"{ENGINEERING_SCENE_DATA_TYPE_ID!r} with handle kind "
                f"{COREX_SCENE_HANDLE_KIND!r}, not "
                f"{runtime_ref.data_type_id!r}/{runtime_ref.kind!r}."
            )
        resolved_value = self._worker_services.resolve_handle(
            runtime_ref,
            expected_data_type=ENGINEERING_SCENE_DATA_TYPE_ID,
            expected_kind=COREX_SCENE_HANDLE_KIND,
        )
        descriptor = getattr(resolved_value, "descriptor", None)
        descriptor_payload = (
            descriptor.to_payload()
            if descriptor is not None
            and callable(getattr(descriptor, "to_payload", None))
            else {}
        )
        descriptor_payload = {
            **_mapping(runtime_ref.metadata),
            **_mapping(descriptor_payload),
            **self._descriptor(resolved_value),
        }
        resolved_descriptor = (
            validate_scene_bundle(descriptor_payload)
            if descriptor_payload.get("schema") == COREX_SCENE_SCHEMA
            else descriptor_payload
        )
        if hasattr(resolved_value, "dataset"):
            resolved_descriptor["_prepared_scene"] = resolved_value
        return resolved_descriptor

    @staticmethod
    def _descriptor(value: Any) -> dict[str, Any]:
        if isinstance(value, (str, os.PathLike)):
            return {"display_path": os.fspath(value)}
        descriptor = _mapping(value)
        if descriptor:
            return descriptor
        display_path = getattr(value, "display_path", "")
        metadata = _mapping(getattr(value, "metadata", None))
        if display_path:
            metadata["display_path"] = os.fspath(display_path)
        return metadata

    @classmethod
    def _scene_layers(
        cls,
        descriptor: Mapping[str, Any],
        *,
        project_path: str,
        session_options: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        layers = [
            cls._layer(value, project_path=project_path)
            for value in descriptor["layers"]
        ]
        normalize_scene_styles(session_options.get("scene_styles", {}))
        display_unit = str(layers[0].get("length_unit", "")).strip()
        for layer in layers:
            style = _mapping(layer.get("style"))
            style["representation"] = session_options.get("representation", "surface")
            style["show_edges"] = session_options.get("show_mesh_edges", False)
            style["pickable"] = True
            # Appearance overrides stay in session options so Auto restores the source.
            style["opacity"] = 1.0
            layer["style"] = style
            layer["scale_factor"] = length_unit_scale(
                str(layer.get("length_unit", "")), display_unit
            )
        return layers

    @classmethod
    def _layer(
        cls,
        value: Any,
        *,
        project_path: str,
    ) -> dict[str, Any]:
        layer = cls._descriptor(value)
        raw_path = layer.get(
            "display_path",
            layer.get(
                "display_artifact_path", layer.get("file_path", layer.get("path", ""))
            ),
        )
        display_path = cls._display_path(raw_path, project_path=project_path)
        geometry_assets = [
            dict(item)
            for item in layer.get("geometry_assets", ())
            if isinstance(item, Mapping)
        ]
        for asset in geometry_assets:
            asset["path"] = cls._display_path(
                asset.get("path", ""),
                project_path=project_path,
            )
        interaction_path = ""
        topological_edge_path = ""
        full_display_asset: dict[str, Any] = {}
        for asset in geometry_assets:
            role_token = str(asset.get("role", "")).strip().casefold()
            content_token = str(asset.get("content", "")).strip().casefold()
            if (
                not interaction_path
                and role_token in {"coarse", "interaction"}
                and content_token in {"", "surface", "mesh"}
            ):
                interaction_path = str(asset.get("path", ""))
            if content_token == "topological_edges" and not topological_edge_path:
                topological_edge_path = str(asset.get("path", ""))
            if (
                role_token == "full"
                and content_token in {"", "surface", "mesh"}
                and not full_display_asset
            ):
                full_display_asset = asset
        style = _mapping(layer.get("style"))
        for key in _STYLE_KEYS:
            if key in layer:
                style[key] = copy.deepcopy(layer[key])
        return {
            "id": str(layer["id"]),
            "name": str(layer["name"]),
            "display_path": display_path,
            "interaction_display_path": interaction_path,
            "topological_edge_path": topological_edge_path,
            "visible": not ("visible" in layer and not _truthy(layer.get("visible"))),
            "style": style,
            "length_unit": str(layer.get("length_unit", "")).strip(),
            "bounds": list(layer.get("bounds", ())),
            "scene_id": str(layer.get("scene_id", "")),
            "source_kind": str(layer.get("source_kind", "")),
            "source": copy.deepcopy(_mapping(layer.get("source"))),
            "hierarchy": [
                copy.deepcopy(dict(item))
                for item in layer.get("hierarchy", ())
                if isinstance(item, Mapping)
            ],
            "geometry_assets": geometry_assets,
            "attribute_colors": copy.deepcopy(
                _mapping(full_display_asset.get("attribute_colors"))
            ),
            "entity_arrays": copy.deepcopy(
                _mapping(full_display_asset.get("entity_arrays"))
            ),
            "topology_mappings": copy.deepcopy(
                _mapping(layer.get("topology_mappings"))
            ),
            "result_fields": [
                copy.deepcopy(dict(item))
                for item in layer.get("result_fields", ())
                if isinstance(item, Mapping)
            ],
            "time_steps": list(layer.get("time_steps", ())),
            "deformation": copy.deepcopy(_mapping(layer.get("deformation"))),
            "capabilities": list(layer.get("capabilities", ())),
            "provenance": copy.deepcopy(_mapping(layer.get("provenance"))),
            "_prepared_scene": layer.get("_prepared_scene"),
        }

    @staticmethod
    def _coerce_bounds(value: Any) -> list[float]:
        if not isinstance(value, (list, tuple)) or len(value) != 6:
            return []
        try:
            bounds = [float(item) for item in value]
        except (TypeError, ValueError):
            return []
        if not all(math.isfinite(item) for item in bounds):
            return []
        if any(bounds[axis * 2] > bounds[axis * 2 + 1] for axis in range(3)):
            return []
        return bounds

    @classmethod
    def _combined_display_bounds(
        cls,
        layers: list[dict[str, Any]],
    ) -> list[float]:
        layer_bounds: list[list[float]] = []
        for layer in layers:
            if not bool(layer.get("visible", True)):
                continue
            bounds = cls._coerce_bounds(layer.get("bounds"))
            if not bounds:
                continue
            scale = float(layer.get("scale_factor", 1.0) or 1.0)
            layer_bounds.append([value * scale for value in bounds])
        if not layer_bounds:
            return []
        return [
            value
            for axis in range(3)
            for value in (
                min(bounds[axis * 2] for bounds in layer_bounds),
                max(bounds[axis * 2 + 1] for bounds in layer_bounds),
            )
        ]

    @staticmethod
    def _fit_data(bounds: list[float], *, length_unit: str) -> dict[str, Any]:
        if len(bounds) != 6:
            return {}
        center = [(bounds[axis * 2] + bounds[axis * 2 + 1]) / 2.0 for axis in range(3)]
        diagonal = math.sqrt(
            sum((bounds[axis * 2 + 1] - bounds[axis * 2]) ** 2 for axis in range(3))
        )
        return {
            "bounds": list(bounds),
            "center": center,
            "diagonal": diagonal,
            "length_unit": str(length_unit),
        }

    @staticmethod
    def _composition_warnings(
        layers: list[dict[str, Any]],
    ) -> list[str]:
        reference_bounds = layers[0].get("bounds")
        if (
            not isinstance(reference_bounds, (list, tuple))
            or len(reference_bounds) != 6
        ):
            return []
        warnings: list[str] = []
        for layer in layers[1:]:
            if not bool(layer.get("visible", True)):
                continue
            bounds = layer.get("bounds")
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 6:
                continue
            scale = float(layer.get("scale_factor", 1.0) or 1.0)
            scaled = [float(value) * scale for value in bounds]
            overlaps = all(
                float(reference_bounds[axis * 2]) <= scaled[axis * 2 + 1]
                and scaled[axis * 2] <= float(reference_bounds[axis * 2 + 1])
                for axis in range(3)
            )
            if not overlaps:
                warnings.append(
                    f"Scene bounds do not overlap for scene '{layer['name']}'. "
                    "COREX preserved the source coordinates and did not align the model."
                )
        return warnings

    @staticmethod
    def _display_path(value: Any, *, project_path: str) -> str:
        raw_path = (
            os.fspath(value).strip() if isinstance(value, (str, os.PathLike)) else ""
        )
        if not raw_path:
            return ""
        path = Path(raw_path).expanduser()
        if not path.is_absolute() and str(project_path).strip():
            project = Path(str(project_path)).expanduser()
            base = project if project.is_dir() else project.parent
            path = base / path
        return str(path.resolve())

    @staticmethod
    def _display_capabilities(
        layers: list[dict[str, Any]],
        *,
        selection_summary: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        has_topological_edges = any(
            bool(str(layer.get("topological_edge_path", "")).strip())
            for layer in layers
        )
        has_topological_edge_colors = any(
            bool(_mapping(asset).get("attribute_colors", {}).get("available", False))
            for layer in layers
            for asset in layer.get("geometry_assets", ())
            if str(_mapping(asset).get("content", "")).strip().casefold()
            == "topological_edges"
        )
        has_attribute_colors = has_topological_edge_colors or any(
            bool(_mapping(layer.get("attribute_colors")).get("available", False))
            for layer in layers
        )
        selection_summary = dict(
            selection_summary or EngineeringViewerBackend._selection_filter_summary(())
        )
        selection_flags = {
            entry["id"]: bool(entry["available"])
            for entry in selection_summary["filters"]
        }
        propagation_flags = {
            entry["id"]: bool(entry["available"])
            for entry in selection_summary["propagation"]
        }
        return {
            "camera_bookmarks": True,
            "fit_selection": True,
            "orientation_triad": True,
            "projection": True,
            "selection_isolate": True,
            "topological_edges": has_topological_edges,
            "body_edges": has_topological_edges,
            "mesh_edges": any(
                bool(str(layer.get("display_path", "")).strip()) for layer in layers
            ),
            "attribute_colors": has_attribute_colors,
            "topological_edge_colors": has_topological_edge_colors,
            "view_cube": True,
            "wireframe_visible_edges": True,
            "world_axes": True,
            **selection_flags,
            **propagation_flags,
            "selection_filter_reasons": {
                entry["id"]: entry["unsupported_reason"]
                for entry in (
                    *selection_summary["filters"],
                    *selection_summary["propagation"],
                )
                if entry["unsupported_reason"]
            },
        }

    @staticmethod
    def _selection_capability_asset_error(
        layer: Mapping[str, Any],
        topology: Mapping[str, Any],
    ) -> str:
        assets = [
            _mapping(asset)
            for asset in layer.get("geometry_assets", ())
            if isinstance(asset, Mapping)
        ]

        def matching_asset(
            *,
            content: str,
            arrays: Mapping[str, str],
            role: str = "",
        ) -> dict[str, Any] | None:
            return next(
                (
                    asset
                    for asset in assets
                    if str(asset.get("content", "")).strip().casefold() == content
                    and (not role or str(asset.get("role", "")).strip() == role)
                    and _mapping(asset.get("entity_arrays")) == dict(arrays)
                ),
                None,
            )

        surface = (
            "surface",
            "full",
            "cell",
            {
                "part_index": "corex_part_index",
                "body_index": "corex_body_index",
                "face_index": "corex_face_index",
            },
            ("corex_part_index", "corex_body_index", "corex_face_index"),
        )
        edges = (
            "topological_edges",
            "topology_edges",
            "cell",
            {
                "part_index": "corex_part_index",
                "edge_index": "corex_edge_index",
            },
            ("corex_part_index", "corex_edge_index"),
        )
        vertices = (
            "topological_vertices",
            "topology_vertices",
            "cell",
            {
                "part_index": "corex_part_index",
                "vertex_index": "corex_vertex_index",
            },
            ("corex_part_index", "corex_vertex_index"),
        )
        fe_nodes = (
            "mesh",
            "selection_identity",
            "point",
            {
                "block_index": "corex_block_index",
                "node_index": "corex_node_index",
                "element_index": "corex_element_index",
            },
            ("corex_block_index", "corex_node_index"),
        )
        fe_elements = (
            *fe_nodes[:2],
            "cell",
            fe_nodes[3],
            ("corex_block_index", "corex_element_index"),
        )
        element_faces = (
            "element_faces",
            "element_faces",
            "cell",
            {
                "block_index": "corex_block_index",
                "element_index": "corex_element_index",
                "element_face_index": "corex_element_face_index",
            },
            (
                "corex_block_index",
                "corex_element_index",
                "corex_element_face_index",
            ),
        )
        capability_assets = {
            "cad_vertex_selection": (vertices,),
            "cad_edge_selection": (edges,),
            "cad_face_selection": (surface,),
            "cad_body_selection": (surface,),
            "fe_node_selection": (fe_nodes,),
            "fe_element_selection": (fe_elements,),
            "fe_element_face_selection": (element_faces,),
            "tangent_edge_propagation": (vertices, edges),
            "tangent_face_propagation": (edges, surface),
        }
        capabilities = _mapping(topology.get("capabilities"))
        required_assets: dict[
            tuple[str, str, str, tuple[str, ...]],
            dict[str, Any],
        ] = {}
        for capability_id, capability in capabilities.items():
            if not bool(_mapping(capability).get("available", False)):
                continue
            for (
                content,
                role,
                association,
                arrays,
                array_names,
            ) in capability_assets.get(str(capability_id), ()):
                asset = matching_asset(content=content, role=role, arrays=arrays)
                if asset is None:
                    return (
                        f"Engineering selection capability {capability_id!r} is declared "
                        "available without its exact canonical geometry asset."
                    )
                key = (content, role, association, tuple(array_names))
                required_assets[key] = asset

        if not required_assets:
            return ""
        try:
            import pyvista
        except ModuleNotFoundError:
            return "Exact engineering selection assets require PyVista."

        loaded: dict[str, Any] = {}
        identity_columns: dict[
            tuple[str, str, str, tuple[str, ...]], dict[str, list[int]]
        ] = {}
        for (
            content,
            role,
            association,
            array_names,
        ), asset in required_assets.items():
            path = str(asset.get("path", "")).strip()
            if path not in loaded:
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        loaded[path] = pyvista.read(path)
                except Exception as exc:  # noqa: BLE001
                    return (
                        f"Engineering selection asset {role!r} could not be read: {exc}"
                    )
            dataset = loaded[path]
            tuple_count = int(
                getattr(dataset, "n_points" if association == "point" else "n_cells", 0)
            )
            if tuple_count <= 0:
                return (
                    f"Engineering selection asset {role!r} contains no selectable "
                    f"{association} tuples."
                )
            container = getattr(dataset, f"{association}_data", {})
            other_association = "cell" if association == "point" else "point"
            other_container = getattr(dataset, f"{other_association}_data", {})
            normalized_columns: dict[str, list[int]] = {}
            for array_name in array_names:
                if array_name not in container:
                    location = (
                        f" is stored in {other_association}_data"
                        if array_name in other_container
                        else " is missing"
                    )
                    return (
                        f"Engineering selection asset {role!r} array {array_name!r}"
                        f"{location}; expected {association}_data."
                    )
                values = container[array_name]
                shape = tuple(getattr(values, "shape", ()))
                if (
                    not shape
                    or int(shape[0]) != tuple_count
                    or len(shape) > 2
                    or (len(shape) == 2 and int(shape[1]) != 1)
                ):
                    return (
                        f"Engineering selection asset {role!r} array {array_name!r} "
                        f"does not provide one value for each {association} tuple."
                    )
                normalized_values: list[int] = []
                for value in values:
                    try:
                        numeric = float(value)
                        integer = int(numeric)
                    except (TypeError, ValueError, OverflowError):
                        return (
                            f"Engineering selection asset {role!r} array {array_name!r} "
                            "must contain integer identities."
                        )
                    if not math.isfinite(numeric) or numeric != integer or integer < 0:
                        return (
                            f"Engineering selection asset {role!r} array {array_name!r} "
                            "must contain non-negative integer identities."
                        )
                    normalized_values.append(integer)
                normalized_columns[array_name] = normalized_values
            identity_columns[(content, role, association, tuple(array_names))] = (
                normalized_columns
            )

        def actual_identities(
            spec: tuple[str, str, str, Mapping[str, str], tuple[str, ...]],
            *array_names: str,
        ) -> list[tuple[int, ...]]:
            key = (spec[0], spec[1], spec[2], tuple(spec[4]))
            columns = identity_columns.get(key, {})
            if not array_names or any(name not in columns for name in array_names):
                return []
            return list(zip(*(columns[name] for name in array_names), strict=True))

        expected_cad = {
            kind: {
                (int(part["part_index"]), int(entity[f"{kind}_index"]))
                for part in topology.get("parts", ())
                for entity in _mapping(part).get(
                    {"body": "bodies"}.get(kind, f"{kind}s"), ()
                )
            }
            for kind in ("vertex", "edge", "face", "body")
        }
        cad_specs = {
            "vertex": (vertices, ("corex_part_index", "corex_vertex_index")),
            "edge": (edges, ("corex_part_index", "corex_edge_index")),
            "face": (surface, ("corex_part_index", "corex_face_index")),
            "body": (surface, ("corex_part_index", "corex_body_index")),
        }
        for kind, expected in expected_cad.items():
            if not expected:
                continue
            spec, names = cad_specs[kind]
            actual = set(actual_identities(spec, *names))
            if actual != expected:
                return (
                    f"Engineering selection asset identities for CAD {kind}s do not "
                    "match the exact topology sidecar."
                )

        blocks = [_mapping(block) for block in topology.get("blocks", ())]
        expected_nodes = {
            (int(block["block_index"]), index)
            for block in blocks
            for index in range(int(block["point_count"]))
        }
        expected_elements = {
            (int(block["block_index"]), index)
            for block in blocks
            for index in range(int(block["cell_count"]))
        }
        for label, expected, spec, names in (
            (
                "FE nodes",
                expected_nodes,
                fe_nodes,
                ("corex_block_index", "corex_node_index"),
            ),
            (
                "FE elements",
                expected_elements,
                fe_elements,
                ("corex_block_index", "corex_element_index"),
            ),
        ):
            if expected and set(actual_identities(spec, *names)) != expected:
                return (
                    f"Engineering selection asset identities for {label} do not match "
                    "the exact topology sidecar."
                )

        expected_face_counts = {
            int(block["block_index"]): int(block["exterior_element_face_count"])
            for block in blocks
        }
        face_rows = actual_identities(
            element_faces,
            "corex_block_index",
            "corex_element_index",
            "corex_element_face_index",
        )
        if any(expected_face_counts.values()):
            if len(face_rows) != len(set(face_rows)):
                return "Engineering element-face identities must be unique."
            actual_face_counts = {
                block_index: sum(row[0] == block_index for row in face_rows)
                for block_index in expected_face_counts
            }
            cell_counts = {
                int(block["block_index"]): int(block["cell_count"]) for block in blocks
            }
            if actual_face_counts != expected_face_counts or any(
                block_index not in cell_counts
                or element_index >= cell_counts[block_index]
                for block_index, element_index, _face_index in face_rows
            ):
                return (
                    "Engineering element-face identities do not match the exact "
                    "topology sidecar."
                )

            face_asset = matching_asset(
                content="element_faces",
                role="element_faces",
                arrays=element_faces[3],
            )
            face_dataset = loaded.get(str(_mapping(face_asset).get("path", "")))
            face_data = getattr(face_dataset, "cell_data", {})
            authored_names = {
                str(block.get("element_face_id_array", "")).strip()
                for block in blocks
                if int(block.get("exterior_element_face_count", 0)) > 0
                and str(block.get("element_face_id_array", "")).strip()
            }
            for array_name in authored_names:
                values = face_data.get(array_name)
                shape = tuple(getattr(values, "shape", ()))
                if (
                    not shape
                    or int(shape[0]) != len(face_rows)
                    or len(shape) > 2
                    or (len(shape) == 2 and int(shape[1]) != 1)
                ):
                    return (
                        f"Engineering authored element-face array {array_name!r} is "
                        "missing or does not provide one value per exterior face."
                    )
        return ""

    @staticmethod
    def _selection_filter_summary(
        topology_layers: tuple[tuple[Mapping[str, Any], Mapping[str, Any]], ...]
        | list[tuple[Mapping[str, Any], Mapping[str, Any]]],
    ) -> dict[str, Any]:
        filter_ids = (
            "cad_vertex_selection",
            "cad_edge_selection",
            "cad_face_selection",
            "cad_body_selection",
            "fe_node_selection",
            "fe_element_face_selection",
            "fe_element_selection",
        )
        propagation_ids = ("tangent_edge_propagation", "tangent_face_propagation")
        facts: dict[str, dict[str, Any]] = {
            key: {
                "available": False,
                "unsupported_reason": "The active sources do not support this selection mode.",
            }
            for key in (*filter_ids, *propagation_ids)
        }
        for _layer, topology in topology_layers:
            for key, value in _mapping(topology.get("capabilities")).items():
                if key not in facts:
                    continue
                capability = _mapping(value)
                if capability.get("available") is True:
                    facts[key] = {"available": True, "unsupported_reason": ""}
                elif not facts[key]["available"]:
                    facts[key] = {
                        "available": False,
                        "unsupported_reason": str(
                            capability.get("unsupported_reason", "")
                        ).strip()
                        or facts[key]["unsupported_reason"],
                    }
        filters = [
            {
                "id": key.removesuffix("_selection"),
                "available": bool(facts[key]["available"]),
                "unsupported_reason": str(facts[key]["unsupported_reason"]),
            }
            for key in filter_ids
        ]
        propagation = [
            {
                "id": key,
                "available": bool(facts[key]["available"]),
                "unsupported_reason": str(facts[key]["unsupported_reason"]),
            }
            for key in propagation_ids
        ]
        available_ids = {entry["id"] for entry in filters if entry["available"]}
        default_filter = (
            "cad_body"
            if "cad_body" in available_ids
            else "fe_element"
            if "fe_element" in available_ids
            else next((entry["id"] for entry in filters if entry["available"]), "")
        )
        return {
            "filters": filters,
            "propagation": propagation,
            "default": default_filter,
        }

    @staticmethod
    def _supported_render_modes(capabilities: Mapping[str, Any]) -> list[str]:
        modes = ["surface", "wireframe", "wireframe_visible_edges", "points"]
        if bool(capabilities.get("topological_edges", False)):
            modes.insert(1, "surface_with_edges")
        return modes

    @classmethod
    def _prepare_shared_memory_payloads(
        cls,
        layers: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], bytes]]:
        payloads: list[tuple[dict[str, Any], bytes]] = []
        total_bytes = 0
        for layer in layers:
            prepared = layer.pop("_prepared_scene", None)
            dataset = getattr(prepared, "dataset", None)
            if dataset is None:
                continue
            if len(payloads) >= _MAX_SHARED_MEMORY_ASSET_COUNT:
                raise ValueError("Too many shared-memory viewer assets.")
            payload = cls._vtk_polydata_payload(dataset)
            byte_length = len(payload)
            if not 0 < byte_length <= _MAX_SHARED_MEMORY_SEGMENT_BYTES:
                raise ValueError("Shared-memory viewer asset size is invalid.")
            total_bytes += byte_length
            if total_bytes > _MAX_SHARED_MEMORY_TOTAL_BYTES:
                raise ValueError("Shared-memory viewer assets are too large.")
            full_asset = next(
                (
                    _mapping(asset)
                    for asset in layer.get("geometry_assets", ())
                    if str(_mapping(asset).get("role", "")).strip().casefold()
                    in {"", "full", "display"}
                    and str(_mapping(asset).get("content", "")).strip().casefold()
                    in {"", "surface", "mesh"}
                ),
                {},
            )
            descriptor = {
                "schema": ENGINEERING_VIEWER_SHARED_MEMORY_ASSET_SCHEMA,
                "version": 1,
                "storage": "shared_memory",
                "name": "",
                "byte_length": byte_length,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "format": "vtkxml-polydata",
                "role": str(full_asset.get("role", "full")).strip() or "full",
                "content": str(full_asset.get("content", "surface")).strip()
                or "surface",
                "attribute_colors": copy.deepcopy(
                    _mapping(layer.get("attribute_colors"))
                ),
                "entity_arrays": copy.deepcopy(_mapping(layer.get("entity_arrays"))),
            }
            probe = {**descriptor, "name": "x" * _MAX_SHARED_MEMORY_NAME_BYTES}
            encoded_descriptor = json.dumps(
                probe,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            if len(encoded_descriptor) > _MAX_SHARED_MEMORY_DESCRIPTOR_BYTES:
                raise ValueError("Shared-memory viewer descriptor is too large.")
            layer["display_asset"] = descriptor
            payloads.append((descriptor, payload))
        return payloads

    @classmethod
    def _vtk_polydata_payload(cls, dataset: Any) -> bytes:
        import pyvista as pv
        from vtkmodules.vtkIOXML import vtkXMLPolyDataWriter

        surfaces: list[Any] = []
        for leaf in cls._dataset_leaves(dataset):
            wrapped = pv.wrap(leaf)
            if not isinstance(wrapped, pv.PolyData):
                extract_surface = getattr(wrapped, "extract_surface", None)
                if not callable(extract_surface):
                    raise TypeError("Engineering dataset has no displayable surface.")
                wrapped = extract_surface(algorithm=None)
            surface = wrapped.copy(deep=True)
            if int(getattr(surface, "n_points", 0)) > 0:
                surfaces.append(surface)
        if not surfaces:
            raise ValueError("Engineering dataset has no displayable points.")
        if len(surfaces) == 1:
            polydata = surfaces[0]
        else:
            combined = pv.MultiBlock(surfaces).combine(merge_points=False)
            polydata = combined.extract_surface(algorithm=None)
        writer = vtkXMLPolyDataWriter()
        writer.SetInputData(polydata)
        writer.SetWriteToOutputString(True)
        writer.SetDataModeToBinary()
        if writer.Write() != 1:
            raise RuntimeError("VTK could not serialize engineering geometry.")
        return writer.GetOutputString().encode("utf-8")

    @staticmethod
    def _allocate_shared_memory(
        payloads: list[tuple[dict[str, Any], bytes]],
    ) -> tuple[SharedMemory, ...]:
        allocated: list[tuple[dict[str, Any], SharedMemory]] = []
        try:
            for descriptor, payload in payloads:
                segment = SharedMemory(create=True, size=len(payload))
                segment.buf[: len(payload)] = payload
                allocated.append((descriptor, segment))
        except BaseException:
            EngineeringViewerBackend._discard_shared_memory(
                tuple(segment for _descriptor, segment in allocated)
            )
            raise
        for descriptor, segment in allocated:
            name = str(segment.name)
            if not name or len(name.encode("utf-8")) > _MAX_SHARED_MEMORY_NAME_BYTES:
                EngineeringViewerBackend._discard_shared_memory(
                    tuple(item for _descriptor, item in allocated)
                )
                raise ValueError("Shared-memory viewer asset name is invalid.")
            descriptor["name"] = name
        return tuple(segment for _descriptor, segment in allocated)

    def _release_shared_memory(self, key: tuple[str, str]) -> None:
        revisions = self._session_shared_memory.pop(key, {})
        for segments in revisions.values():
            self._discard_shared_memory(segments)

    @staticmethod
    def _discard_shared_memory(segments: tuple[SharedMemory, ...]) -> None:
        for segment in segments:
            try:
                segment.unlink()
            except FileNotFoundError:
                pass
            finally:
                try:
                    segment.close()
                except OSError:
                    pass

    @staticmethod
    def _transport_signature(transport: Mapping[str, Any]) -> str:
        file_facts: list[tuple[str, int, int]] = []
        visited_paths: set[str] = set()
        for layer in transport.get("layers", []):
            layer_paths = [
                str(layer.get(key, "")).strip()
                for key in (
                    "display_path",
                    "interaction_display_path",
                    "topological_edge_path",
                )
            ]
            layer_paths.extend(
                str(_mapping(asset).get("path", "")).strip()
                for asset in layer.get("geometry_assets", ())
            )
            for path_text in layer_paths:
                if not path_text or path_text in visited_paths:
                    continue
                visited_paths.add(path_text)
                path = Path(path_text)
                if not path.is_file():
                    continue
                stat = path.stat()
                file_facts.append((str(path), int(stat.st_mtime_ns), int(stat.st_size)))
        return json.dumps(
            {"transport": transport, "file_facts": file_facts},
            ensure_ascii=True,
            sort_keys=True,
            default=str,
        )

    def _blocked_result(
        self,
        *,
        code: str,
        reason: str,
        rerun_required: bool = False,
    ) -> ViewerBackendMaterializationResult:
        blocker = {
            "code": str(code),
            "reason": str(reason),
            "rerun_required": bool(rerun_required),
        }
        return ViewerBackendMaterializationResult(
            backend_id=self.backend_id,
            live_open_status="blocked",
            live_open_blocker=blocker,
            summary={"viewer_kind": "engineering_scene", "live_open_blocker": blocker},
        )


__all__ = [
    "COREX_SCENE_HANDLE_KIND",
    "ENGINEERING_VIEWER_BACKEND_ID",
    "ENGINEERING_VIEWER_SHARED_MEMORY_ASSET_SCHEMA",
    "ENGINEERING_VIEWER_TRANSPORT_KIND",
    "ENGINEERING_VIEWER_TRANSPORT_SCHEMA",
    "EngineeringViewerBackend",
]
