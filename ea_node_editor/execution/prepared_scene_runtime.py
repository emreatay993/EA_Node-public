# Purpose: Prepare and cache neutral FE/CAD scenes behind worker-owned runtime handles.
# Map: subsystems/execution.md
# Tests: tests/test_engineering_import_nodes.py
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any, Callable, Iterator
from uuid import uuid4

import numpy as np

from ea_node_editor.common.payload_tools import compact_sequence_metadata
from ea_node_editor.common.scene_protocol import (
    CAD_SCENE_SUFFIXES,
    COREX_SCENE_HANDLE_KIND,
    FE_SCENE_SUFFIXES,
    ENGINEERING_SELECTION_TOPOLOGY_SCHEMA,
    OCP_CAD_SCENE_SUFFIXES,
    SCENE_IMPORTER_VERSION,
    SceneDescriptor,
    SceneSourceMetadata,
    normalize_length_unit,
    validate_engineering_selection_topology,
    validate_scene_bundle,
)
from ea_node_editor.execution.handle_registry import StaleHandleError
from ea_node_editor.runtime_contracts.value_refs import RuntimeHandleRef
from ea_node_editor.runtime_contracts import ENGINEERING_SCENE_DATA_TYPE_ID

if TYPE_CHECKING:
    from ea_node_editor.execution.worker_services import WorkerServices


_SOURCE_RGBA_ARRAY = "corex_source_rgba"
_SOURCE_COLOR_VALID_ARRAY = "corex_source_color_valid"
_PART_INDEX_ARRAY = "corex_part_index"
_BODY_INDEX_ARRAY = "corex_body_index"
_FACE_INDEX_ARRAY = "corex_face_index"
_EDGE_INDEX_ARRAY = "corex_edge_index"
_VERTEX_INDEX_ARRAY = "corex_vertex_index"
_BLOCK_INDEX_ARRAY = "corex_block_index"
_NODE_INDEX_ARRAY = "corex_node_index"
_ELEMENT_INDEX_ARRAY = "corex_element_index"
_ELEMENT_FACE_INDEX_ARRAY = "corex_element_face_index"
_FALLBACK_RGBA = (208, 215, 222, 255)


@dataclass(slots=True, frozen=True)
class _CadPart:
    part_index: int
    hierarchy_id: str
    shape: Any
    location: Any
    instance_label: Any | None = None
    definition_label: Any | None = None


@dataclass(slots=True, frozen=True)
class _CadMetadata:
    hierarchy: tuple[dict[str, Any], ...] = ()
    topology_mappings: dict[str, Any] | None = None
    length_unit: str = ""
    provenance: dict[str, Any] | None = None
    document: Any | None = None
    parts: tuple[_CadPart, ...] = ()


@dataclass(slots=True)
class PreparedScene:
    descriptor: SceneDescriptor
    dataset: Any
    exact_model: Any | None = None
    reader: Any | None = None

    def read_state(
        self,
        *,
        time_value: float | None = None,
        point_arrays: tuple[str, ...] | None = None,
        cell_arrays: tuple[str, ...] | None = None,
    ) -> Any:
        """Read one FE state without materializing every time/array combination."""

        if self.reader is None:
            if time_value is None and point_arrays is None and cell_arrays is None:
                return self.dataset
            raise RuntimeError(
                "This prepared scene does not retain a stateful FE reader."
            )
        if time_value is not None:
            normalized_time = float(time_value)
            if normalized_time not in self.descriptor.time_steps:
                raise ValueError(f"Unknown FE time value: {normalized_time}.")
            setter = getattr(self.reader, "set_active_time_value", None)
            if not callable(setter):
                raise RuntimeError("This FE reader cannot select time values lazily.")
            setter(normalized_time)
        self._select_arrays("point", point_arrays)
        self._select_arrays("cell", cell_arrays)
        return self.reader.read()

    def _select_arrays(self, location: str, requested: tuple[str, ...] | None) -> None:
        if requested is None:
            return
        available = {
            str(name) for name in getattr(self.reader, f"{location}_array_names", ())
        }
        unknown = sorted(set(requested) - available)
        if unknown:
            raise ValueError(f"Unknown FE {location} result array: {unknown[0]!r}.")
        disable_all = getattr(self.reader, f"disable_all_{location}_arrays", None)
        enable = getattr(self.reader, f"enable_{location}_array", None)
        if not callable(disable_all) or not callable(enable):
            raise RuntimeError(
                f"This FE reader cannot select {location} result arrays lazily."
            )
        disable_all()
        for name in requested:
            enable(name)


class PreparedSceneRuntime:
    def __init__(
        self,
        worker_services: WorkerServices,
        *,
        cache_root: str | Path | None = None,
    ) -> None:
        self._worker_services = worker_services
        self._cache: dict[str, RuntimeHandleRef] = {}
        self._lifecycle_lock = RLock()
        self._display_root: Path | None = None
        self._cache_root = (
            Path(cache_root).expanduser().resolve()
            if cache_root is not None
            else Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
            / "COREX"
            / "Cache"
            / "scene_cache"
        )

    @property
    def cache_size(self) -> int:
        with self._lifecycle_lock:
            return len(self._cache)

    @contextmanager
    def lifecycle_guard(self) -> Iterator[None]:
        with self._lifecycle_lock:
            yield

    def prepare_fe_scene(
        self,
        path: str | Path,
        *,
        length_unit: str = "",
        workspace_id: str = "",
        owner_scope: str = "",
    ) -> RuntimeHandleRef:
        with self._lifecycle_lock:
            return self._prepare_scene(
                path,
                source_kind="fe",
                supported_suffixes=FE_SCENE_SUFFIXES,
                length_unit=length_unit,
                workspace_id=workspace_id,
                owner_scope=owner_scope,
            )

    def prepare_cad_scene(
        self,
        path: str | Path,
        *,
        length_unit: str = "",
        workspace_id: str = "",
        owner_scope: str = "",
    ) -> RuntimeHandleRef:
        with self._lifecycle_lock:
            return self._prepare_scene(
                path,
                source_kind="cad",
                supported_suffixes=CAD_SCENE_SUFFIXES,
                length_unit=length_unit,
                workspace_id=workspace_id,
                owner_scope=owner_scope,
            )

    def prepare_cad_shape(
        self,
        shape: Any,
        *,
        source_identity: str,
        owner_scope: str,
        length_unit: str = "m",
        source_name: str = "OCPBody",
    ) -> RuntimeHandleRef:
        with self._lifecycle_lock:
            if type(source_identity) is not str or not source_identity:
                raise ValueError("CAD shape source_identity is required.")
            normalized_length_unit = normalize_length_unit(length_unit)
            if not normalized_length_unit:
                raise ValueError("CAD shape length_unit is required.")
            normalized_source_name = str(source_name).strip() or "OCPBody"

            fingerprint = hashlib.sha256(source_identity.encode("utf-8")).hexdigest()
            source_uri = f"memory://corex/ocp-body/{fingerprint}"
            source_label = Path(f"{normalized_source_name}.ocp")
            parts = self._cad_parts(shape, _CadMetadata())
            hierarchy = (
                {
                    "id": "cad:body:0",
                    "parent_id": "scene:root",
                    "name": "OCP Body",
                    "kind": "body",
                    "visible": True,
                    "part_index": 1,
                },
            )
            cad_metadata = _CadMetadata(
                hierarchy=hierarchy,
                topology_mappings=self._exact_topology_mappings(
                    shape,
                    hierarchy,
                    parts=parts,
                ),
                provenance={"source": "worker_local_ocp_shape"},
                parts=parts,
            )
            dataset, has_colors = self._cad_surface_dataset(
                shape,
                source_label,
                linear_deflection=0.001,
                cad_metadata=cad_metadata,
            )
            geometry_assets = (
                {
                    "id": "geometry:full",
                    "role": "full",
                    "path": "",
                    "format": ".vtp",
                    "content": "surface",
                    "attribute_colors": self._generated_color_metadata(
                        available=has_colors,
                        source="ocp",
                    ),
                    "entity_arrays": {
                        "part_index": _PART_INDEX_ARRAY,
                        "body_index": _BODY_INDEX_ARRAY,
                        "face_index": _FACE_INDEX_ARRAY,
                    },
                },
            )
            descriptor = self._scene_descriptor(
                dataset,
                source_kind="cad",
                source=SceneSourceMetadata(
                    source_path=f"memory://corex/{normalized_source_name}",
                    resolved_path=source_uri,
                    source_format=".ocp",
                    size_bytes=0,
                    modified_time_ns=0,
                    sha256=fingerprint,
                ),
                display_path=None,
                length_unit=normalized_length_unit,
                exact_model_available=True,
                cache_manifest_path=None,
                geometry_assets=geometry_assets,
                reader=None,
                cad_metadata=cad_metadata,
                storage="memory",
            )
            descriptor = SceneDescriptor.from_payload(descriptor.to_payload())
            prepared = PreparedScene(
                descriptor=descriptor,
                dataset=dataset,
                exact_model=shape,
            )
            return self._worker_services.register_handle(
                prepared,
                data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
                kind=COREX_SCENE_HANDLE_KIND,
                owner_scope=owner_scope,
                metadata=self._handle_metadata(descriptor),
            )

    def reset(
        self,
        *,
        warn: Callable[[str], None] | None = None,
    ) -> None:
        with self._lifecycle_lock:
            for signature in tuple(self._cache):
                self._discard_cached(signature, warn=warn)
            self._display_root = None

    def _prepare_scene(
        self,
        path: str | Path,
        *,
        source_kind: str,
        supported_suffixes: tuple[str, ...],
        length_unit: str,
        workspace_id: str,
        owner_scope: str,
    ) -> RuntimeHandleRef:
        source_path = str(path)
        resolved_path = Path(path).expanduser().resolve()
        if not resolved_path.is_file():
            raise FileNotFoundError(
                f"{source_kind.upper()} import file does not exist: {resolved_path}"
            )

        source_format = resolved_path.suffix.lower()
        if source_format not in supported_suffixes:
            supported = ", ".join(supported_suffixes)
            raise ValueError(
                f"Unsupported {source_kind.upper()} import format {source_format or '<none>'!r}. "
                f"Supported formats: {supported}."
            )

        normalized_length_unit = normalize_length_unit(length_unit)
        stat = resolved_path.stat()
        source_sha256 = self._sha256(resolved_path)
        self._assert_source_unchanged(
            resolved_path,
            source_kind=source_kind,
            initial_stat=stat,
            initial_sha256=source_sha256,
            verify_hash=False,
        )
        signature = self._source_signature(
            source_kind=source_kind,
            source_sha256=source_sha256,
            length_unit=normalized_length_unit,
        )
        source = SceneSourceMetadata(
            source_path=source_path,
            resolved_path=str(resolved_path),
            source_format=source_format,
            size_bytes=stat.st_size,
            modified_time_ns=stat.st_mtime_ns,
            sha256=source_sha256,
        )
        import_settings = {
            "source_kind": source_kind,
            "length_unit": normalized_length_unit,
            "importer_version": SCENE_IMPORTER_VERSION,
        }
        manifest_path = self._manifest_path(signature, workspace_id=workspace_id)
        cached_descriptor = self._load_cached_descriptor(
            manifest_path,
            signature=signature,
            source=source,
            import_settings=import_settings,
        )

        cached = self._cache.get(signature)
        if cached is not None and cached_descriptor is not None:
            try:
                prepared = self._worker_services.resolve_handle(
                    cached,
                    expected_data_type=ENGINEERING_SCENE_DATA_TYPE_ID,
                    expected_kind=COREX_SCENE_HANDLE_KIND,
                )
            except (StaleHandleError, TypeError):
                self._discard_cached(signature)
            else:
                if (
                    isinstance(prepared, PreparedScene)
                    and prepared.descriptor.to_payload()
                    == cached_descriptor.to_payload()
                ):
                    return self._lease_for_owner(cached, owner_scope=owner_scope)
                self._discard_cached(signature)
        elif cached is not None:
            self._discard_cached(signature)

        exact_model = None
        cad_metadata = _CadMetadata()
        reader = None
        display_paths: dict[str, Path] = {}
        generated_paths: list[Path] = []
        try:
            if cached_descriptor is not None:
                display_path = Path(cached_descriptor.display_artifact_path)
                geometry_assets = tuple(cached_descriptor.geometry_assets)
            elif source_kind == "cad" and source_format in OCP_CAD_SCENE_SUFFIXES:
                display_paths = self._display_artifact_paths(
                    signature,
                    workspace_id=workspace_id,
                )
                display_path = display_paths["full"]
                geometry_assets = ()
            else:
                display_path = resolved_path
                geometry_assets = ()

            if source_kind == "cad" and source_format in OCP_CAD_SCENE_SUFFIXES:
                exact_model, cad_metadata = self._load_ocp_cad(resolved_path)
                if cached_descriptor is None:
                    written_paths, surface_colors, edge_colors, topology_sha256 = (
                        self._write_cad_lods(
                            exact_model,
                            resolved_path,
                            display_paths,
                            cad_metadata=cad_metadata,
                        )
                    )
                    generated_paths.extend(written_paths)
                    geometry_assets = self._cad_lod_assets(
                        display_paths,
                        surface_colors=surface_colors,
                        edge_colors=edge_colors,
                        topology_sha256=topology_sha256,
                    )

            dataset, reader = self._read_display_dataset(
                display_path,
                source_kind=source_kind,
            )
            if source_kind == "fe" and cached_descriptor is None:
                fe_paths = self._fe_selection_artifact_paths(
                    signature,
                    workspace_id=workspace_id,
                )
                fe_written, fe_assets = self._write_fe_selection_assets(
                    dataset,
                    fe_paths,
                )
                generated_paths.extend(fe_written)
                geometry_assets = (
                    *self._full_geometry_asset(
                        display_path,
                        content="mesh",
                        attribute_colors=self._direct_color_metadata(dataset),
                    ),
                    *fe_assets,
                )
            if cached_descriptor is None and not geometry_assets:
                geometry_assets = self._full_geometry_asset(
                    display_path,
                    content="mesh",
                    attribute_colors=self._direct_color_metadata(dataset),
                )
            if (
                source_kind == "cad"
                and source_format == ".stl"
                and cached_descriptor is None
            ):
                coarse_path = self._stl_coarse_artifact_path(
                    signature,
                    workspace_id=workspace_id,
                )
                self._write_stl_coarse_lod(dataset, coarse_path)
                generated_paths.append(coarse_path)
                geometry_assets = (
                    {
                        "id": "geometry:coarse",
                        "role": "coarse",
                        "path": str(coarse_path),
                        "format": ".vtp",
                        "content": "mesh",
                        "attribute_colors": self._direct_color_metadata(dataset),
                        "entity_arrays": {},
                    },
                    *geometry_assets,
                )

            resolved_length_unit = (
                normalized_length_unit
                or cad_metadata.length_unit
                or self._dataset_length_unit(dataset)
            )
            if not resolved_length_unit:
                raise ValueError(
                    f"{source_kind.upper()} file '{resolved_path.name}' has no usable length unit. "
                    "Choose Length Unit on the import node."
                )

            descriptor = cached_descriptor or self._scene_descriptor(
                dataset,
                source_kind=source_kind,
                source=source,
                display_path=display_path,
                length_unit=resolved_length_unit,
                exact_model_available=exact_model is not None,
                cache_manifest_path=manifest_path,
                geometry_assets=geometry_assets,
                reader=reader,
                cad_metadata=cad_metadata,
            )
            self._assert_source_unchanged(
                resolved_path,
                source_kind=source_kind,
                initial_stat=stat,
                initial_sha256=source_sha256,
            )
            if cached_descriptor is None:
                self._write_manifest(
                    descriptor,
                    signature=signature,
                    import_settings=import_settings,
                )
        except Exception:
            if cached_descriptor is None:
                manifest_path.unlink(missing_ok=True)
                for generated_path in generated_paths:
                    generated_path.unlink(missing_ok=True)
            raise

        prepared = PreparedScene(
            descriptor=descriptor,
            dataset=dataset,
            exact_model=exact_model,
            reader=reader if source_kind == "fe" else None,
        )
        handle_metadata = self._handle_metadata(descriptor)
        runtime_ref = self._worker_services.register_handle(
            prepared,
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope=self._cache_owner_scope(signature),
            metadata=handle_metadata,
        )
        self._cache[signature] = runtime_ref
        return self._lease_for_owner(runtime_ref, owner_scope=owner_scope)

    @staticmethod
    def _cache_owner_scope(signature: str) -> str:
        return f"cache:prepared_scene:{signature}"

    def _lease_for_owner(
        self,
        runtime_ref: RuntimeHandleRef,
        *,
        owner_scope: str,
    ) -> RuntimeHandleRef:
        normalized_owner_scope = str(owner_scope).strip()
        if not normalized_owner_scope or runtime_ref.owner_scope == normalized_owner_scope:
            return runtime_ref
        if (
            self._worker_services.handle_registry.lease_count(
                runtime_ref,
                owner_scope=normalized_owner_scope,
            )
            == 0
        ):
            return self._worker_services.lease_handle(
                runtime_ref,
                owner_scope=normalized_owner_scope,
            )
        return replace(runtime_ref, owner_scope=normalized_owner_scope)

    def _discard_cached(
        self,
        signature: str,
        *,
        warn: Callable[[str], None] | None = None,
    ) -> None:
        cached = self._cache.get(signature)
        if cached is None:
            return
        self._worker_services.handle_registry.release_owner_scope(
            cached.owner_scope,
            warn=warn,
        )
        self._cache.pop(signature, None)

    @staticmethod
    def _handle_metadata(descriptor: SceneDescriptor) -> dict[str, Any]:
        descriptor_payload = descriptor.to_payload()
        source_payload = descriptor_payload["source"]
        metadata = {
            "schema": descriptor_payload["schema"],
            "scene_id": descriptor_payload["scene_id"],
            "source_kind": descriptor_payload["source_kind"],
            "source": {
                "source_path": (
                    str(source_payload["source_path"])
                    if descriptor.storage == "memory"
                    else Path(str(source_payload["source_path"])).name
                ),
                "source_format": source_payload["source_format"],
                "sha256": source_payload["sha256"],
            },
            "dataset_kind": descriptor_payload["dataset_kind"],
            "point_count": descriptor_payload["point_count"],
            "cell_count": descriptor_payload["cell_count"],
            "block_count": descriptor_payload["block_count"],
            "bounds": descriptor_payload["bounds"],
            "length_unit": descriptor_payload["length_unit"],
            "capabilities": descriptor_payload["capabilities"],
            "topology_summary": {
                "mapping_count": len(descriptor.topology_mappings),
                "block_count": len(
                    descriptor.topology_mappings.get("blocks", ())
                ),
            },
        }
        if descriptor.storage != "file":
            metadata["storage"] = descriptor.storage
        for key in ("point_arrays", "cell_arrays", "hierarchy"):
            metadata.update(
                compact_sequence_metadata(
                    key,
                    descriptor_payload[key],
                    max_inline_items=0,
                    max_inline_bytes=0,
                )
            )
        return metadata

    @staticmethod
    def _source_signature(
        *,
        source_kind: str,
        source_sha256: str,
        length_unit: str,
    ) -> str:
        payload = {
            "source_kind": source_kind,
            "source_sha256": source_sha256,
            "length_unit": length_unit,
            "importer_version": SCENE_IMPORTER_VERSION,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def _display_artifact_paths(
        self,
        signature: str,
        *,
        workspace_id: str,
    ) -> dict[str, Path]:
        root = self._workspace_cache_root(workspace_id)
        return {
            "coarse": root / f"{signature}.surface.coarse.vtp",
            "full": root / f"{signature}.surface.full.vtp",
            "topology_edges": root / f"{signature}.topology_edges.vtp",
            "topology_vertices": root / f"{signature}.topology_vertices.vtp",
            "selection_topology": root / f"{signature}.selection_topology.json",
        }

    def _stl_coarse_artifact_path(self, signature: str, *, workspace_id: str) -> Path:
        return self._workspace_cache_root(workspace_id) / f"{signature}.mesh.coarse.vtp"

    def _fe_selection_artifact_paths(
        self,
        signature: str,
        *,
        workspace_id: str,
    ) -> dict[str, Path]:
        root = self._workspace_cache_root(workspace_id)
        return {
            "identity": root / f"{signature}.selection_mesh.vtu",
            "element_faces": root / f"{signature}.element_faces.vtp",
            "selection_topology": root / f"{signature}.selection_topology.json",
        }

    def _manifest_path(self, signature: str, *, workspace_id: str) -> Path:
        return self._workspace_cache_root(workspace_id) / f"{signature}.scene.json"

    def _workspace_cache_root(self, workspace_id: str) -> Path:
        workspace_token = hashlib.sha1(
            (str(workspace_id).strip() or "default").encode("utf-8")
        ).hexdigest()[:16]
        self._display_root = self._cache_root / workspace_token
        self._display_root.mkdir(parents=True, exist_ok=True)
        return self._display_root

    @staticmethod
    def _full_geometry_asset(
        display_path: Path,
        *,
        content: str,
        attribute_colors: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        return (
            {
                "id": "geometry:full",
                "role": "full",
                "path": str(display_path),
                "format": display_path.suffix.casefold(),
                "content": content,
                "attribute_colors": dict(attribute_colors),
                "entity_arrays": {},
            },
        )

    @staticmethod
    def _cad_lod_assets(
        display_paths: dict[str, Path],
        *,
        surface_colors: bool,
        edge_colors: bool,
        topology_sha256: str,
    ) -> tuple[dict[str, Any], ...]:
        surface_color_metadata = PreparedSceneRuntime._generated_color_metadata(
            available=surface_colors,
            source="xcaf",
        )
        edge_color_metadata = PreparedSceneRuntime._generated_color_metadata(
            available=edge_colors,
            source="xcaf",
        )
        return (
            {
                "id": "geometry:coarse",
                "role": "coarse",
                "path": str(display_paths["coarse"]),
                "format": ".vtp",
                "content": "surface",
                "attribute_colors": surface_color_metadata,
                "entity_arrays": {
                    "part_index": _PART_INDEX_ARRAY,
                    "body_index": _BODY_INDEX_ARRAY,
                    "face_index": _FACE_INDEX_ARRAY,
                },
            },
            {
                "id": "geometry:full",
                "role": "full",
                "path": str(display_paths["full"]),
                "format": ".vtp",
                "content": "surface",
                "attribute_colors": surface_color_metadata,
                "entity_arrays": {
                    "part_index": _PART_INDEX_ARRAY,
                    "body_index": _BODY_INDEX_ARRAY,
                    "face_index": _FACE_INDEX_ARRAY,
                },
            },
            {
                "id": "geometry:topology_edges",
                "role": "topology_edges",
                "path": str(display_paths["topology_edges"]),
                "format": ".vtp",
                "content": "topological_edges",
                "attribute_colors": edge_color_metadata,
                "entity_arrays": {
                    "part_index": _PART_INDEX_ARRAY,
                    "edge_index": _EDGE_INDEX_ARRAY,
                },
            },
            {
                "id": "geometry:topology_vertices",
                "role": "topology_vertices",
                "path": str(display_paths["topology_vertices"]),
                "format": ".vtp",
                "content": "topological_vertices",
                "attribute_colors": PreparedSceneRuntime._unavailable_color_metadata(
                    "Topological vertices do not define source colors."
                ),
                "entity_arrays": {
                    "part_index": _PART_INDEX_ARRAY,
                    "vertex_index": _VERTEX_INDEX_ARRAY,
                },
            },
            {
                "id": "selection:topology",
                "role": "selection_topology",
                "path": str(display_paths["selection_topology"]),
                "format": ".json",
                "content": "selection_topology",
                "schema": ENGINEERING_SELECTION_TOPOLOGY_SCHEMA,
                "sha256": str(topology_sha256),
                "attribute_colors": PreparedSceneRuntime._unavailable_color_metadata(
                    "Selection topology is non-renderable metadata."
                ),
                "entity_arrays": {},
            },
        )

    @staticmethod
    def _unavailable_color_metadata(reason: str) -> dict[str, Any]:
        return {
            "available": False,
            "array_name": "",
            "valid_mask_name": "",
            "association": "",
            "component_count": 0,
            "encoding": "",
            "source": "",
            "fallback_rgba": list(_FALLBACK_RGBA),
            "unsupported_reason": str(reason),
        }

    @staticmethod
    def _generated_color_metadata(*, available: bool, source: str) -> dict[str, Any]:
        if not available:
            return PreparedSceneRuntime._unavailable_color_metadata(
                "The CAD source does not define colors for this geometry."
            )
        return {
            "available": True,
            "array_name": _SOURCE_RGBA_ARRAY,
            "valid_mask_name": _SOURCE_COLOR_VALID_ARRAY,
            "association": "cell",
            "component_count": 4,
            "encoding": "uint8",
            "source": str(source),
            "fallback_rgba": list(_FALLBACK_RGBA),
            "unsupported_reason": "",
        }

    @staticmethod
    def _direct_color_metadata(dataset: Any) -> dict[str, Any]:
        try:
            import pyvista
        except ModuleNotFoundError:  # pragma: no cover - guarded by the reader path
            return PreparedSceneRuntime._unavailable_color_metadata(
                "PyVista is unavailable for direct-color inspection."
            )

        leaves: list[Any] = []

        def visit(value: Any) -> None:
            if isinstance(value, pyvista.MultiBlock):
                for child in value:
                    if child is not None:
                        visit(child)
            else:
                leaves.append(value)

        visit(dataset)
        if not leaves:
            return PreparedSceneRuntime._unavailable_color_metadata(
                "The mesh contains no displayable color arrays."
            )

        accepted_names = (
            "rgba",
            "rgb",
            "colors",
            "colours",
            "color",
            "colour",
            "vertexcolors",
            "vertexcolor",
            "cellcolors",
            "cellcolor",
        )

        def candidate(
            value: Any, association: str, name: str
        ) -> tuple[int, str] | None:
            container = getattr(value, f"{association}_data", {})
            if name not in container:
                return None
            array = np.asarray(container[name])
            expected_count = int(
                getattr(value, "n_points" if association == "point" else "n_cells", 0)
            )
            if (
                array.ndim != 2
                or array.shape[0] != expected_count
                or array.shape[1] not in {3, 4}
            ):
                return None
            if array.dtype == np.dtype(np.uint8):
                encoding = "uint8"
            elif np.issubdtype(array.dtype, np.floating):
                if (
                    not np.all(np.isfinite(array))
                    or np.any(array < 0.0)
                    or np.any(array > 1.0)
                ):
                    return None
                encoding = "float01"
            else:
                return None
            return int(array.shape[1]), encoding

        first = leaves[0]
        candidates: list[tuple[int, int, int, str, str, int, str]] = []
        for association_index, association in enumerate(("point", "cell")):
            container = getattr(first, f"{association}_data", {})
            for name in container.keys():
                normalized_name = "".join(
                    character
                    for character in str(name).casefold()
                    if character.isalnum()
                )
                if normalized_name not in accepted_names:
                    continue
                details = candidate(first, association, str(name))
                if details is None:
                    continue
                component_count, encoding = details
                candidates.append(
                    (
                        0 if component_count == 4 else 1,
                        accepted_names.index(normalized_name),
                        association_index,
                        association,
                        str(name),
                        component_count,
                        encoding,
                    )
                )
        for _, _, _, association, name, component_count, encoding in sorted(candidates):
            if all(
                candidate(leaf, association, name) == (component_count, encoding)
                for leaf in leaves
            ):
                return {
                    "available": True,
                    "array_name": name,
                    "valid_mask_name": "",
                    "association": association,
                    "component_count": component_count,
                    "encoding": encoding,
                    "source": "vtk_array",
                    "fallback_rgba": list(_FALLBACK_RGBA),
                    "unsupported_reason": "",
                }
        return PreparedSceneRuntime._unavailable_color_metadata(
            "No consistent source-authored RGB or RGBA array is available across the mesh."
        )

    @staticmethod
    def _load_cached_descriptor(
        manifest_path: Path,
        *,
        signature: str,
        source: SceneSourceMetadata,
        import_settings: dict[str, Any],
    ) -> SceneDescriptor | None:
        if not manifest_path.is_file():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("cache_signature") != signature:
                raise ValueError("cache signature mismatch")
            if manifest.get("import_settings") != import_settings:
                raise ValueError("import settings mismatch")
            descriptor = SceneDescriptor.from_payload(manifest.get("scene"))
            if (
                Path(descriptor.cache_manifest_path).resolve()
                != manifest_path.resolve()
            ):
                raise ValueError("cache manifest path mismatch")
            if descriptor.source.sha256 != source.sha256:
                raise ValueError("source fingerprint mismatch")
            if (
                descriptor.source.size_bytes != source.size_bytes
                or descriptor.source.modified_time_ns != source.modified_time_ns
            ):
                raise ValueError("source metadata mismatch")
            if (
                Path(descriptor.source.resolved_path).resolve()
                != Path(source.resolved_path).resolve()
            ):
                raise ValueError("source path mismatch")
            asset_paths = [
                Path(str(asset.get("path", ""))) for asset in descriptor.geometry_assets
            ]
            if not asset_paths or not all(path.is_file() for path in asset_paths):
                raise FileNotFoundError("prepared scene asset is missing")
            for asset in descriptor.geometry_assets:
                if (
                    str(asset.get("content", "")).strip().casefold()
                    != "selection_topology"
                ):
                    continue
                topology_path = Path(str(asset.get("path", "")))
                topology_bytes = topology_path.read_bytes()
                if (
                    hashlib.sha256(topology_bytes).hexdigest()
                    != str(asset.get("sha256", "")).strip().casefold()
                ):
                    raise ValueError("selection topology checksum mismatch")
                validate_engineering_selection_topology(
                    json.loads(topology_bytes.decode("utf-8"))
                )
            if not Path(descriptor.display_artifact_path).is_file():
                raise FileNotFoundError("prepared scene display artifact is missing")
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            manifest_path.unlink(missing_ok=True)
            return None
        return descriptor

    @staticmethod
    def _write_manifest(
        descriptor: SceneDescriptor,
        *,
        signature: str,
        import_settings: dict[str, Any],
    ) -> None:
        manifest_path = Path(descriptor.cache_manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cache_signature": signature,
            "import_settings": dict(import_settings),
            "scene": validate_scene_bundle(descriptor.to_payload()),
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=manifest_path.parent,
            prefix=f".{manifest_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(payload, temporary_file, indent=2, sort_keys=True)
            temporary_path = Path(temporary_file.name)
        try:
            temporary_path.replace(manifest_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _write_cad_lods(
        self,
        shape: Any,
        source_path: Path,
        display_paths: dict[str, Path],
        *,
        cad_metadata: _CadMetadata,
    ) -> tuple[list[Path], bool, bool, str]:
        temporary_paths: dict[str, Path] = {}
        replaced_paths: list[Path] = []
        surface_colors = False
        edge_colors = False
        topology_sha256 = ""
        try:
            for role, deflection in (("coarse", 0.01), ("full", 0.001)):
                final_path = display_paths[role]
                final_path.parent.mkdir(parents=True, exist_ok=True)
                temporary_path = final_path.with_name(
                    f".{final_path.stem}.{uuid4().hex}.tmp{final_path.suffix}"
                )
                temporary_paths[role] = temporary_path
                surface, has_colors = self._cad_surface_dataset(
                    shape,
                    source_path,
                    linear_deflection=deflection,
                    cad_metadata=cad_metadata,
                )
                surface.save(temporary_path)
                surface_colors = surface_colors or has_colors

            edge_path = display_paths["topology_edges"]
            edge_path.parent.mkdir(parents=True, exist_ok=True)
            edge_temporary_path = edge_path.with_name(
                f".{edge_path.stem}.{uuid4().hex}.tmp{edge_path.suffix}"
            )
            temporary_paths["topology_edges"] = edge_temporary_path
            edges, edge_colors = self._cad_edge_dataset(
                shape,
                source_path,
                linear_deflection=0.001,
                cad_metadata=cad_metadata,
            )
            edges.save(edge_temporary_path)

            vertex_path = display_paths["topology_vertices"]
            vertex_path.parent.mkdir(parents=True, exist_ok=True)
            vertex_temporary_path = vertex_path.with_name(
                f".{vertex_path.stem}.{uuid4().hex}.tmp{vertex_path.suffix}"
            )
            temporary_paths["topology_vertices"] = vertex_temporary_path
            self._cad_vertex_dataset(
                shape, source_path, cad_metadata=cad_metadata
            ).save(vertex_temporary_path)

            topology_path = display_paths["selection_topology"]
            topology_path.parent.mkdir(parents=True, exist_ok=True)
            topology_temporary_path = topology_path.with_name(
                f".{topology_path.stem}.{uuid4().hex}.tmp{topology_path.suffix}"
            )
            temporary_paths["selection_topology"] = topology_temporary_path
            topology_payload = self._cad_selection_topology(
                shape,
                source_path,
                cad_metadata=cad_metadata,
            )
            topology_bytes = json.dumps(
                topology_payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            topology_temporary_path.write_bytes(topology_bytes)
            topology_sha256 = hashlib.sha256(topology_bytes).hexdigest()

            for role in (
                "coarse",
                "full",
                "topology_edges",
                "topology_vertices",
                "selection_topology",
            ):
                final_path = display_paths[role]
                temporary_paths[role].replace(final_path)
                replaced_paths.append(final_path)
        except Exception:
            for final_path in replaced_paths:
                final_path.unlink(missing_ok=True)
            raise
        finally:
            for temporary_path in temporary_paths.values():
                temporary_path.unlink(missing_ok=True)
        return replaced_paths, surface_colors, edge_colors, topology_sha256

    @classmethod
    def _write_stl_coarse_lod(cls, dataset: Any, output_path: Path) -> None:
        combined = (
            dataset.combine()
            if callable(getattr(dataset, "combine", None))
            else dataset
        )
        extract_surface = getattr(combined, "extract_surface", None)
        surface = (
            extract_surface(algorithm=None) if callable(extract_surface) else combined
        )
        triangulate = getattr(surface, "triangulate", None)
        surface = triangulate() if callable(triangulate) else surface
        if int(getattr(surface, "n_cells", 0)) > 8:
            decimate = getattr(surface, "decimate_pro", None)
            if callable(decimate):
                reduced = decimate(0.75, preserve_topology=True)
                if int(getattr(reduced, "n_cells", 0)) > 0:
                    surface = reduced
        cls._write_dataset_atomic(surface, output_path)

    @staticmethod
    def _write_dataset_atomic(dataset: Any, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_name(
            f".{output_path.stem}.{uuid4().hex}.tmp{output_path.suffix}"
        )
        try:
            dataset.save(temporary_path)
            temporary_path.replace(output_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @classmethod
    def _write_fe_selection_assets(
        cls,
        dataset: Any,
        output_paths: dict[str, Path],
    ) -> tuple[list[Path], tuple[dict[str, Any], ...]]:
        import pyvista

        leaf_records: list[tuple[str, Any]] = []

        def visit(value: Any, *, path: tuple[int, ...]) -> None:
            if isinstance(value, pyvista.MultiBlock):
                for index, child in enumerate(value):
                    if child is not None:
                        visit(child, path=(*path, index))
                return
            block_path = path or (0,)
            leaf_records.append(
                ("block:" + ".".join(str(item) for item in block_path), value)
            )

        visit(dataset, path=())
        identity_blocks: list[Any] = []
        face_blocks: list[Any] = []
        block_records: list[dict[str, Any]] = []
        node_count = 0
        element_count = 0
        element_face_count = 0
        point_id_candidates = {
            "globalnodeid",
            "globalnodeids",
            "nodeid",
            "nodeids",
            "vtkoriginalpointids",
        }
        cell_id_candidates = {
            "globalelementid",
            "globalelementids",
            "elementid",
            "elementids",
            "vtkoriginalcellids",
        }
        element_face_id_candidates = {
            "solverfaceids",
            "solverfacenumbers",
            "elementfaceids",
            "elementfacenumbers",
        }

        def source_id_array(container: Any, candidates: set[str]) -> str:
            for name in getattr(container, "keys", lambda: ())():
                token = "".join(
                    character
                    for character in str(name).casefold()
                    if character.isalnum()
                )
                if token in candidates:
                    return str(name)
            return ""

        def authored_element_face_array(
            container: Any,
            *,
            cell_count: int,
            highest_local_face_index: int,
        ) -> str:
            for name in getattr(container, "keys", lambda: ())():
                token = "".join(
                    character
                    for character in str(name).casefold()
                    if character.isalnum()
                )
                if token not in element_face_id_candidates:
                    continue
                array = np.asarray(container[name])
                if (
                    array.ndim == 2
                    and array.shape[0] == cell_count
                    and array.shape[1] > highest_local_face_index
                    and np.issubdtype(array.dtype, np.integer)
                    and not np.issubdtype(array.dtype, np.bool_)
                ):
                    return str(name)
            return ""

        for block_index, (block_id, leaf) in enumerate(leaf_records):
            identity = leaf.copy(deep=True)
            point_count = int(getattr(identity, "n_points", 0))
            cell_count = int(getattr(identity, "n_cells", 0))
            identity.point_data[_BLOCK_INDEX_ARRAY] = np.full(
                point_count,
                block_index,
                dtype=np.int32,
            )
            identity.point_data[_NODE_INDEX_ARRAY] = np.arange(
                point_count, dtype=np.int64
            )
            identity.cell_data[_BLOCK_INDEX_ARRAY] = np.full(
                cell_count,
                block_index,
                dtype=np.int32,
            )
            identity.cell_data[_ELEMENT_INDEX_ARRAY] = np.arange(
                cell_count, dtype=np.int64
            )
            identity_blocks.append(identity)
            node_count += point_count
            element_count += cell_count
            block_record = {
                "block_index": block_index,
                "block_id": block_id,
                "point_id_array": source_id_array(
                    getattr(leaf, "point_data", {}),
                    point_id_candidates,
                ),
                "cell_id_array": source_id_array(
                    getattr(leaf, "cell_data", {}),
                    cell_id_candidates,
                ),
                "point_count": point_count,
                "cell_count": cell_count,
                "exterior_element_face_count": 0,
                "element_face_id_array": "",
                "element_face_id_unsupported_reason": (
                    "The FE source does not provide a usable authored element-face number array."
                ),
            }
            block_records.append(block_record)

            face_candidates: dict[
                tuple[int, ...], list[tuple[int, int, list[int]]]
            ] = {}
            for element_index in range(cell_count):
                cell = leaf.get_cell(element_index)
                dimension = int(getattr(cell, "dimension", 0))
                if dimension == 3:
                    local_faces = list(getattr(cell, "faces", ()))
                    face_point_ids = [list(face.point_ids) for face in local_faces]
                elif dimension == 2:
                    face_point_ids = [list(cell.point_ids)]
                else:
                    face_point_ids = []
                for local_face_index, point_ids in enumerate(face_point_ids):
                    if len(point_ids) < 3:
                        continue
                    key = tuple(sorted(int(value) for value in point_ids))
                    face_candidates.setdefault(key, []).append(
                        (
                            element_index,
                            local_face_index,
                            [int(value) for value in point_ids],
                        )
                    )
            exterior = [
                values[0] for values in face_candidates.values() if len(values) == 1
            ]
            if not exterior:
                continue
            source_face_array = authored_element_face_array(
                getattr(leaf, "cell_data", {}),
                cell_count=cell_count,
                highest_local_face_index=max(value[1] for value in exterior),
            )
            faces = np.asarray(
                [
                    value
                    for _element_index, _face_index, point_ids in exterior
                    for value in (len(point_ids), *point_ids)
                ],
                dtype=np.int64,
            )
            face_dataset = pyvista.PolyData(np.asarray(leaf.points), faces=faces)
            face_dataset.cell_data[_BLOCK_INDEX_ARRAY] = np.full(
                len(exterior),
                block_index,
                dtype=np.int32,
            )
            face_dataset.cell_data[_ELEMENT_INDEX_ARRAY] = np.asarray(
                [value[0] for value in exterior],
                dtype=np.int64,
            )
            face_dataset.cell_data[_ELEMENT_FACE_INDEX_ARRAY] = np.asarray(
                [value[1] for value in exterior],
                dtype=np.int32,
            )
            if source_face_array:
                authored_values = np.asarray(leaf.cell_data[source_face_array])
                face_dataset.cell_data[source_face_array] = np.asarray(
                    [
                        authored_values[element_index, local_face_index]
                        for element_index, local_face_index, _point_ids in exterior
                    ]
                )
                block_record["element_face_id_array"] = source_face_array
                block_record["element_face_id_unsupported_reason"] = ""
            face_blocks.append(face_dataset)
            element_face_count += len(exterior)
            block_record["exterior_element_face_count"] = len(exterior)

        exterior_records = [
            record
            for record in block_records
            if int(record["exterior_element_face_count"]) > 0
        ]
        retained_face_names = {
            str(record["element_face_id_array"])
            for record in exterior_records
            if str(record["element_face_id_array"])
        }
        if exterior_records and (
            len(retained_face_names) != 1
            or any(not record["element_face_id_array"] for record in exterior_records)
        ):
            for face_block in face_blocks:
                for array_name in retained_face_names:
                    if array_name in face_block.cell_data:
                        del face_block.cell_data[array_name]
            for record in exterior_records:
                record["element_face_id_array"] = ""
                record["element_face_id_unsupported_reason"] = (
                    "Authored element-face numbering is unavailable or inconsistent across FE blocks."
                )

        if not identity_blocks:
            raise ValueError("The FE scene contains no selectable mesh blocks.")
        identity_dataset = pyvista.MultiBlock(identity_blocks).combine(
            merge_points=False
        )
        faces_dataset = (
            pyvista.merge(face_blocks, merge_points=False)
            if face_blocks
            else pyvista.PolyData()
        )
        topology_payload = {
            "schema": ENGINEERING_SELECTION_TOPOLOGY_SCHEMA,
            "parts": [],
            "blocks": block_records,
            "edge_continuity": [],
            "face_continuity": [],
            "capabilities": {
                "fe_node_selection": {
                    "available": node_count > 0,
                    "unsupported_reason": ""
                    if node_count > 0
                    else "The FE mesh has no nodes.",
                },
                "fe_element_selection": {
                    "available": element_count > 0,
                    "unsupported_reason": ""
                    if element_count > 0
                    else "The FE mesh has no elements.",
                },
                "fe_element_face_selection": {
                    "available": element_face_count > 0,
                    "unsupported_reason": (
                        ""
                        if element_face_count > 0
                        else "The FE mesh has no exterior element faces."
                    ),
                },
                "cad_vertex_selection": {
                    "available": False,
                    "unsupported_reason": "FE sources do not define CAD vertices.",
                },
                "cad_edge_selection": {
                    "available": False,
                    "unsupported_reason": "FE sources do not define exact CAD edges.",
                },
                "cad_face_selection": {
                    "available": False,
                    "unsupported_reason": "FE sources do not define CAD faces.",
                },
                "cad_body_selection": {
                    "available": False,
                    "unsupported_reason": "FE sources do not define CAD bodies.",
                },
                "tangent_edge_propagation": {
                    "available": False,
                    "unsupported_reason": "Tangent propagation requires exact CAD topology.",
                },
                "tangent_face_propagation": {
                    "available": False,
                    "unsupported_reason": "Tangent propagation requires exact CAD topology.",
                },
            },
            "counts": {
                "blocks": len(leaf_records),
                "nodes": node_count,
                "elements": element_count,
                "exterior_element_faces": element_face_count,
            },
        }
        topology_bytes = json.dumps(
            topology_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        topology_path = output_paths["selection_topology"]
        written_paths: list[Path] = []
        try:
            cls._write_dataset_atomic(identity_dataset, output_paths["identity"])
            written_paths.append(output_paths["identity"])
            cls._write_dataset_atomic(faces_dataset, output_paths["element_faces"])
            written_paths.append(output_paths["element_faces"])
            topology_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=topology_path.parent,
                prefix=f".{topology_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_file.write(topology_bytes)
                temporary_path = Path(temporary_file.name)
            try:
                temporary_path.replace(topology_path)
                written_paths.append(topology_path)
            finally:
                temporary_path.unlink(missing_ok=True)
        except Exception:
            for output_path in output_paths.values():
                output_path.unlink(missing_ok=True)
            raise
        topology_sha256 = hashlib.sha256(topology_bytes).hexdigest()
        unavailable_colors = cls._unavailable_color_metadata(
            "Selection identity assets do not define display colors."
        )
        assets = (
            {
                "id": "selection:mesh_identity",
                "role": "selection_identity",
                "path": str(output_paths["identity"]),
                "format": ".vtu",
                "content": "mesh",
                "attribute_colors": unavailable_colors,
                "entity_arrays": {
                    "block_index": _BLOCK_INDEX_ARRAY,
                    "node_index": _NODE_INDEX_ARRAY,
                    "element_index": _ELEMENT_INDEX_ARRAY,
                },
            },
            {
                "id": "selection:element_faces",
                "role": "element_faces",
                "path": str(output_paths["element_faces"]),
                "format": ".vtp",
                "content": "element_faces",
                "attribute_colors": unavailable_colors,
                "entity_arrays": {
                    "block_index": _BLOCK_INDEX_ARRAY,
                    "element_index": _ELEMENT_INDEX_ARRAY,
                    "element_face_index": _ELEMENT_FACE_INDEX_ARRAY,
                },
            },
            {
                "id": "selection:topology",
                "role": "selection_topology",
                "path": str(topology_path),
                "format": ".json",
                "content": "selection_topology",
                "schema": ENGINEERING_SELECTION_TOPOLOGY_SCHEMA,
                "sha256": topology_sha256,
                "attribute_colors": cls._unavailable_color_metadata(
                    "Selection topology is non-renderable metadata."
                ),
                "entity_arrays": {},
            },
        )
        return written_paths, assets

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _assert_source_unchanged(
        cls,
        path: Path,
        *,
        source_kind: str,
        initial_stat: os.stat_result,
        initial_sha256: str,
        verify_hash: bool = True,
    ) -> None:
        current_stat = path.stat()
        changed = (
            current_stat.st_size != initial_stat.st_size
            or current_stat.st_mtime_ns != initial_stat.st_mtime_ns
        )
        if verify_hash and not changed:
            changed = cls._sha256(path) != initial_sha256
        if changed:
            raise RuntimeError(
                f"Source changed during {source_kind.upper()} import: {path}"
            )

    @staticmethod
    def _read_display_dataset(path: Path, *, source_kind: str) -> tuple[Any, Any]:
        try:
            import pyvista
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"{source_kind.upper()} import requires the optional PyVista/VTK viewer dependencies."
            ) from exc

        try:
            reader = pyvista.get_reader(str(path))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"No PyVista/VTK reader is available for {source_kind.upper()} file: {path}"
            ) from exc
        try:
            dataset = reader.read()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Could not read {source_kind.upper()} file '{path}': {exc}"
            ) from exc
        if not isinstance(dataset, (pyvista.DataSet, pyvista.MultiBlock)):
            raise TypeError(
                f"{source_kind.upper()} reader returned unsupported display data: {type(dataset).__name__}"
            )
        return dataset, reader

    @staticmethod
    def _scene_descriptor(
        dataset: Any,
        *,
        source_kind: str,
        source: SceneSourceMetadata,
        display_path: Path | None,
        length_unit: str,
        exact_model_available: bool,
        cache_manifest_path: Path | None,
        geometry_assets: tuple[dict[str, Any], ...],
        reader: Any,
        cad_metadata: _CadMetadata,
        storage: str = "file",
    ) -> SceneDescriptor:
        try:
            import pyvista
        except (
            ModuleNotFoundError
        ) as exc:  # pragma: no cover - guarded by the reader path
            raise RuntimeError("Scene descriptor creation requires PyVista.") from exc

        hierarchy: list[dict[str, Any]] = [
            {
                "id": "scene:root",
                "parent_id": "",
                "name": Path(source.source_path).name or "Scene",
                "kind": "scene",
                "visible": True,
            }
        ]
        leaf_records: list[tuple[str, Any]] = []

        def walk_blocks(value: Any, *, parent_id: str, path: tuple[int, ...]) -> None:
            if not isinstance(value, pyvista.MultiBlock):
                leaf_records.append((parent_id, value))
                return
            keys = tuple(value.keys())
            for index, block in enumerate(value):
                if block is None:
                    continue
                block_path = (*path, index)
                block_id = "block:" + ".".join(str(item) for item in block_path)
                block_name = keys[index] if index < len(keys) else ""
                hierarchy.append(
                    {
                        "id": block_id,
                        "parent_id": parent_id,
                        "name": str(block_name or f"Block {index + 1}"),
                        "kind": "group"
                        if isinstance(block, pyvista.MultiBlock)
                        else "block",
                        "visible": True,
                    }
                )
                walk_blocks(block, parent_id=block_id, path=block_path)

        walk_blocks(dataset, parent_id="scene:root", path=())
        leaf_datasets = tuple(value for _, value in leaf_records)
        if not leaf_datasets:
            raise ValueError("Imported scene contains no displayable datasets.")

        point_arrays = {str(name) for name in getattr(reader, "point_array_names", ())}
        point_arrays.update(
            {
                str(name)
                for leaf in leaf_datasets
                for name in getattr(leaf, "point_data", {}).keys()
            }
        )
        cell_arrays = {str(name) for name in getattr(reader, "cell_array_names", ())}
        cell_arrays.update(
            {
                str(name)
                for leaf in leaf_datasets
                for name in getattr(leaf, "cell_data", {}).keys()
            }
        )
        bounds = tuple(float(value) for value in dataset.bounds)
        if len(bounds) != 6 or not all(math.isfinite(value) for value in bounds):
            raise ValueError("Imported scene does not have finite display bounds.")

        display_metadata_arrays = {
            _PART_INDEX_ARRAY,
            _BODY_INDEX_ARRAY,
            _FACE_INDEX_ARRAY,
            _EDGE_INDEX_ARRAY,
            _VERTEX_INDEX_ARRAY,
            _BLOCK_INDEX_ARRAY,
            _NODE_INDEX_ARRAY,
            _ELEMENT_INDEX_ARRAY,
            _ELEMENT_FACE_INDEX_ARRAY,
            _SOURCE_RGBA_ARRAY,
            _SOURCE_COLOR_VALID_ARRAY,
            *(
                str(attribute_colors.get("array_name", ""))
                for asset in geometry_assets
                if (attribute_colors := dict(asset.get("attribute_colors", {}))).get(
                    "available", False
                )
            ),
        }
        display_metadata_arrays.discard("")
        result_field_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for location, container_name in (
            ("point", "point_data"),
            ("cell", "cell_data"),
        ):
            for leaf in leaf_datasets:
                container = getattr(leaf, container_name, {})
                for name in container.keys():
                    if str(name) in display_metadata_arrays:
                        continue
                    array = container[name]
                    shape = getattr(array, "shape", ())
                    component_count = int(shape[1]) if len(shape) > 1 else 1
                    normalized_name = str(name)
                    key = (location, normalized_name)
                    result_field_by_key.setdefault(
                        key,
                        {
                            "name": normalized_name,
                            "location": location,
                            "component_count": component_count,
                            "components": PreparedSceneRuntime._result_components(
                                component_count
                            ),
                            "data_type": str(getattr(array, "dtype", "")),
                            "unit": PreparedSceneRuntime._result_unit(
                                leaf,
                                normalized_name,
                            ),
                            "deformation_candidate": bool(
                                source_kind == "fe"
                                and component_count == 3
                                and any(
                                    token in normalized_name.casefold()
                                    for token in (
                                        "displacement",
                                        "deformation",
                                        "disp",
                                        "warp",
                                    )
                                )
                            ),
                        },
                    )

        result_fields = tuple(
            result_field_by_key[key] for key in sorted(result_field_by_key)
        )
        deformation_field = next(
            (field for field in result_fields if field["deformation_candidate"]),
            None,
        )
        deformation = {
            "available": deformation_field is not None,
            "enabled": False,
            "scale_factor": 1.0,
            "field_name": str(deformation_field["name"]) if deformation_field else "",
            "location": str(deformation_field["location"]) if deformation_field else "",
        }
        if cad_metadata.hierarchy:
            hierarchy = [hierarchy[0], *[dict(item) for item in cad_metadata.hierarchy]]

        topology_mappings = (
            dict(cad_metadata.topology_mappings)
            if cad_metadata.topology_mappings
            else PreparedSceneRuntime._fe_topology_mappings(leaf_records)
        )
        time_steps = PreparedSceneRuntime._reader_time_steps(reader)

        capability_names = ["geometry", "picking", "bounds", "export"]
        if result_fields:
            capability_names.extend(("scalar_results", "probe"))
        if deformation["available"]:
            capability_names.append("deformation")
        if time_steps:
            capability_names.append("time_steps")
        if exact_model_available:
            capability_names.extend(
                ("exact_measurement", "mass_properties", "step_export")
            )
        if any(
            asset.get("content") == "topological_edges" for asset in geometry_assets
        ):
            capability_names.append("topological_edges")
        if any(
            bool(dict(asset.get("attribute_colors", {})).get("available", False))
            for asset in geometry_assets
        ):
            capability_names.append("attribute_colors")

        return SceneDescriptor(
            scene_id=f"scene:{source.sha256}",
            source_kind=source_kind,
            source=source,
            display_artifact_path=str(display_path) if display_path is not None else "",
            display_format=(
                display_path.suffix.lower() if display_path is not None else ".vtp"
            ),
            cache_manifest_path=(
                str(cache_manifest_path) if cache_manifest_path is not None else ""
            ),
            dataset_kind=type(dataset).__name__,
            point_count=sum(
                int(getattr(leaf, "n_points", 0)) for leaf in leaf_datasets
            ),
            cell_count=sum(int(getattr(leaf, "n_cells", 0)) for leaf in leaf_datasets),
            block_count=len(leaf_datasets),
            bounds=bounds,  # type: ignore[arg-type]
            length_unit=length_unit,
            point_arrays=tuple(sorted(point_arrays)),
            cell_arrays=tuple(sorted(cell_arrays)),
            hierarchy=tuple(hierarchy),
            geometry_assets=geometry_assets,
            topology_mappings=topology_mappings,
            result_fields=result_fields,
            time_steps=time_steps,
            deformation=deformation,
            capabilities=tuple(sorted(set(capability_names))),
            provenance={
                "importer": "corex.neutral_scene",
                "importer_version": SCENE_IMPORTER_VERSION,
                "source_sha256": source.sha256,
                "lazy_time_loading": bool(
                    time_steps
                    and callable(getattr(reader, "set_active_time_value", None))
                ),
                "lazy_result_array_loading": bool(
                    callable(getattr(reader, "disable_all_point_arrays", None))
                    and callable(getattr(reader, "enable_point_array", None))
                ),
                **dict(cad_metadata.provenance or {}),
            },
            storage=storage,
        )

    @staticmethod
    def _result_components(component_count: int) -> list[str]:
        if component_count == 3:
            return ["magnitude", "x", "y", "z"]
        if component_count == 6:
            return ["xx", "yy", "zz", "xy", "yz", "xz"]
        if component_count == 9:
            return ["xx", "xy", "xz", "yx", "yy", "yz", "zx", "zy", "zz"]
        return (
            ["value"]
            if component_count == 1
            else [str(index) for index in range(component_count)]
        )

    @staticmethod
    def _result_unit(dataset: Any, array_name: str) -> str:
        field_data = getattr(dataset, "field_data", {})
        candidate_keys = {
            f"{array_name}_unit".casefold(),
            f"{array_name}_units".casefold(),
        }
        for key in getattr(field_data, "keys", lambda: ())():
            if str(key).strip().casefold() not in candidate_keys:
                continue
            value = field_data[key]
            value = getattr(value, "tolist", lambda: value)()
            while isinstance(value, (list, tuple)) and value:
                value = value[0]
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            return str(value).strip()
        return ""

    @staticmethod
    def _reader_time_steps(reader: Any) -> tuple[float, ...]:
        raw_values = getattr(reader, "time_values", None)
        if raw_values is None:
            return ()
        try:
            values = sorted({float(item) for item in raw_values})
        except (TypeError, ValueError):
            return ()
        return tuple(value for value in values if math.isfinite(value))

    @staticmethod
    def _fe_topology_mappings(
        leaf_records: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        point_candidates = {
            "globalnodeid",
            "globalnodeids",
            "nodeid",
            "nodeids",
            "vtkoriginalpointids",
        }
        cell_candidates = {
            "globalelementid",
            "globalelementids",
            "elementid",
            "elementids",
            "vtkoriginalcellids",
        }

        def source_id_array(container: Any, candidates: set[str]) -> str:
            for name in getattr(container, "keys", lambda: ())():
                token = "".join(
                    character
                    for character in str(name).casefold()
                    if character.isalnum()
                )
                if token in candidates:
                    return str(name)
            return ""

        blocks: list[dict[str, Any]] = []
        for block_index, (block_id, leaf) in enumerate(leaf_records):
            point_array = source_id_array(
                getattr(leaf, "point_data", {}), point_candidates
            )
            cell_array = source_id_array(
                getattr(leaf, "cell_data", {}), cell_candidates
            )
            blocks.append(
                {
                    "block_index": block_index,
                    "block_id": block_id if block_id != "scene:root" else "block:0",
                    "point_id_array": point_array,
                    "cell_id_array": cell_array,
                    "point_count": int(getattr(leaf, "n_points", 0)),
                    "cell_count": int(getattr(leaf, "n_cells", 0)),
                }
            )
        return {
            "point_ids": {
                "policy": "source_array_or_block_local_index",
                "stable_for_source_fingerprint": True,
            },
            "cell_ids": {
                "policy": "source_array_or_block_local_index",
                "stable_for_source_fingerprint": True,
            },
            "blocks": blocks,
        }

    @staticmethod
    def _cad_parts(shape: Any, cad_metadata: _CadMetadata) -> tuple[_CadPart, ...]:
        if cad_metadata.parts:
            return cad_metadata.parts
        from OCP.TopLoc import TopLoc_Location

        return (
            _CadPart(
                part_index=1,
                hierarchy_id="cad:body:0",
                shape=shape,
                location=TopLoc_Location(),
            ),
        )

    @staticmethod
    def _xcaf_subshape_color(
        cad_metadata: _CadMetadata,
        part: _CadPart,
        subshape: Any,
        *,
        edge: bool,
    ) -> tuple[tuple[int, int, int, int], bool]:
        if cad_metadata.document is None:
            return _FALLBACK_RGBA, False

        from OCP.Quantity import Quantity_ColorRGBA
        from OCP.TDF import TDF_Label
        from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool

        color_tool = XCAFDoc_DocumentTool.ColorTool_s(cad_metadata.document.Main())
        shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(cad_metadata.document.Main())
        color_types = (
            (
                XCAFDoc_ColorType.XCAFDoc_ColorCurv,
                XCAFDoc_ColorType.XCAFDoc_ColorGen,
                XCAFDoc_ColorType.XCAFDoc_ColorSurf,
            )
            if edge
            else (
                XCAFDoc_ColorType.XCAFDoc_ColorSurf,
                XCAFDoc_ColorType.XCAFDoc_ColorGen,
            )
        )

        def rgba_bytes(color: Any) -> tuple[int, int, int, int]:
            rgb = color.GetRGB()
            return (
                round(float(rgb.Red()) * 255.0),
                round(float(rgb.Green()) * 255.0),
                round(float(rgb.Blue()) * 255.0),
                round(float(color.Alpha()) * 255.0),
            )

        located_subshape = subshape.Moved(part.location)
        for color_type in color_types:
            color = Quantity_ColorRGBA()
            if color_tool.GetInstanceColor(located_subshape, color_type, color):
                return rgba_bytes(color), True
            color = Quantity_ColorRGBA()
            if color_tool.GetColor(subshape, color_type, color):
                return rgba_bytes(color), True

        if part.definition_label is not None:
            subshape_label = TDF_Label()
            if shape_tool.FindSubShape(part.definition_label, subshape, subshape_label):
                for color_type in color_types:
                    color = Quantity_ColorRGBA()
                    if color_tool.GetColor_s(subshape_label, color_type, color):
                        return rgba_bytes(color), True

        for label in (part.instance_label, part.definition_label):
            if label is None:
                continue
            for color_type in color_types:
                color = Quantity_ColorRGBA()
                if color_tool.GetColor_s(label, color_type, color):
                    return rgba_bytes(color), True
        return _FALLBACK_RGBA, False

    @staticmethod
    def _cad_body_shapes(owner: Any) -> list[tuple[str, Any, list[Any]]]:
        """Return solids plus standalone shells/faces as stable selectable bodies."""

        from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        def mapped(shape: Any, shape_type: Any) -> list[Any]:
            mapping = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(shape, shape_type, mapping)
            return [mapping.FindKey(index) for index in range(1, mapping.Extent() + 1)]

        def contains(shapes: list[Any], candidate: Any) -> bool:
            return any(candidate.IsSame(item) for item in shapes)

        solids = mapped(owner, TopAbs_SOLID)
        all_shells = mapped(owner, TopAbs_SHELL)
        all_faces = mapped(owner, TopAbs_FACE)
        solid_shells = [
            shell for solid in solids for shell in mapped(solid, TopAbs_SHELL)
        ]
        standalone_shells = [
            shell for shell in all_shells if not contains(solid_shells, shell)
        ]
        claimed_faces = [
            face for solid in solids for face in mapped(solid, TopAbs_FACE)
        ]
        claimed_faces.extend(
            face for shell in standalone_shells for face in mapped(shell, TopAbs_FACE)
        )
        standalone_faces = [
            face for face in all_faces if not contains(claimed_faces, face)
        ]
        return [
            *(("solid", solid, mapped(solid, TopAbs_FACE)) for solid in solids),
            *(
                ("shell", shell, mapped(shell, TopAbs_FACE))
                for shell in standalone_shells
            ),
            *(("surface", face, [face]) for face in standalone_faces),
        ]

    @classmethod
    def _cad_surface_dataset(
        cls,
        shape: Any,
        source_path: Path,
        *,
        linear_deflection: float,
        cad_metadata: _CadMetadata,
    ) -> tuple[Any, bool]:
        try:
            import pyvista
            from OCP.BRep import BRep_Tool
            from OCP.BRepMesh import BRepMesh_IncrementalMesh
            from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
            from OCP.TopExp import TopExp
            from OCP.TopLoc import TopLoc_Location
            from OCP.TopoDS import TopoDS
            from OCP.TopTools import TopTools_IndexedMapOfShape
        except ModuleNotFoundError as exc:
            raise cls._missing_ocp_error(source_path) from exc

        points: list[tuple[float, float, float]] = []
        faces: list[int] = []
        part_indices: list[int] = []
        body_indices: list[int] = []
        face_indices: list[int] = []
        source_rgba: list[tuple[int, int, int, int]] = []
        source_color_valid: list[int] = []
        has_colors = False
        expected_faces: set[tuple[int, int]] = set()

        for part in cls._cad_parts(shape, cad_metadata):
            mesher = BRepMesh_IncrementalMesh(
                part.shape,
                float(linear_deflection),
                True,
                0.5,
                True,
            )
            mesher.Perform()
            if hasattr(mesher, "IsDone") and not mesher.IsDone():
                raise RuntimeError(f"OCP could not tessellate CAD file: {source_path}")
            indexed_faces = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(part.shape, TopAbs_FACE, indexed_faces)
            expected_faces.update(
                (part.part_index, face_index)
                for face_index in range(1, indexed_faces.Extent() + 1)
            )
            body_faces = [
                (body_index, body_record[2])
                for body_index, body_record in enumerate(
                    cls._cad_body_shapes(part.shape),
                    start=1,
                )
            ]
            for face_index in range(1, indexed_faces.Extent() + 1):
                local_face = TopoDS.Face_s(indexed_faces.FindKey(face_index))
                body_index = next(
                    (
                        candidate_index
                        for candidate_index, candidate_faces in body_faces
                        if any(
                            local_face.IsSame(candidate_face)
                            for candidate_face in candidate_faces
                        )
                    ),
                    0,
                )
                located_face = TopoDS.Face_s(local_face.Moved(part.location))
                location = TopLoc_Location()
                triangulation = BRep_Tool.Triangulation_s(located_face, location)
                if triangulation is None or triangulation.NbTriangles() < 1:
                    continue
                transform = location.Transformation()
                point_offset = len(points)
                for node_index in range(1, triangulation.NbNodes() + 1):
                    point = triangulation.Node(node_index).Transformed(transform)
                    points.append(
                        (float(point.X()), float(point.Y()), float(point.Z()))
                    )
                rgba, valid = cls._xcaf_subshape_color(
                    cad_metadata,
                    part,
                    local_face,
                    edge=False,
                )
                has_colors = has_colors or valid
                reversed_face = local_face.Orientation() == TopAbs_REVERSED
                for triangle_index in range(1, triangulation.NbTriangles() + 1):
                    node_ids = list(triangulation.Triangle(triangle_index).Get())
                    if reversed_face:
                        node_ids[1], node_ids[2] = node_ids[2], node_ids[1]
                    faces.extend(
                        [
                            3,
                            *(point_offset + node_id - 1 for node_id in node_ids),
                        ]
                    )
                    part_indices.append(part.part_index)
                    body_indices.append(body_index)
                    face_indices.append(face_index)
                    source_rgba.append(rgba)
                    source_color_valid.append(1 if valid else 0)

        if not faces:
            raise RuntimeError(
                f"OCP produced no displayable CAD faces for: {source_path}"
            )
        missing_faces = expected_faces.difference(zip(part_indices, face_indices))
        if missing_faces or any(body_index < 1 for body_index in body_indices):
            raise RuntimeError(
                f"OCP could not preserve exact CAD face/body identities for: {source_path}"
            )
        dataset = pyvista.PolyData(
            np.asarray(points, dtype=float),
            faces=np.asarray(faces, dtype=np.int64),
        )
        dataset.cell_data[_PART_INDEX_ARRAY] = np.asarray(part_indices, dtype=np.int32)
        dataset.cell_data[_BODY_INDEX_ARRAY] = np.asarray(body_indices, dtype=np.int32)
        dataset.cell_data[_FACE_INDEX_ARRAY] = np.asarray(face_indices, dtype=np.int32)
        dataset.cell_data[_SOURCE_RGBA_ARRAY] = np.asarray(source_rgba, dtype=np.uint8)
        dataset.cell_data[_SOURCE_COLOR_VALID_ARRAY] = np.asarray(
            source_color_valid,
            dtype=np.uint8,
        )
        return dataset, has_colors

    @classmethod
    def _cad_edge_dataset(
        cls,
        shape: Any,
        source_path: Path,
        *,
        linear_deflection: float,
        cad_metadata: _CadMetadata,
    ) -> tuple[Any, bool]:
        try:
            import pyvista
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.GCPnts import GCPnts_QuasiUniformDeflection
            from OCP.TopAbs import TopAbs_EDGE
            from OCP.TopExp import TopExp
            from OCP.TopoDS import TopoDS
            from OCP.TopTools import TopTools_IndexedMapOfShape
        except ModuleNotFoundError as exc:
            raise cls._missing_ocp_error(source_path) from exc

        points: list[tuple[float, float, float]] = []
        lines: list[int] = []
        part_indices: list[int] = []
        edge_indices: list[int] = []
        source_rgba: list[tuple[int, int, int, int]] = []
        source_color_valid: list[int] = []
        has_colors = False
        expected_edges: set[tuple[int, int]] = set()

        for part in cls._cad_parts(shape, cad_metadata):
            indexed_edges = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(part.shape, TopAbs_EDGE, indexed_edges)
            expected_edges.update(
                (part.part_index, edge_index)
                for edge_index in range(1, indexed_edges.Extent() + 1)
            )
            for edge_index in range(1, indexed_edges.Extent() + 1):
                local_edge = TopoDS.Edge_s(indexed_edges.FindKey(edge_index))
                located_edge = TopoDS.Edge_s(local_edge.Moved(part.location))
                try:
                    curve = BRepAdaptor_Curve(located_edge)
                    first = float(curve.FirstParameter())
                    last = float(curve.LastParameter())
                    if (
                        not math.isfinite(first)
                        or not math.isfinite(last)
                        or first == last
                    ):
                        continue
                    sampler = GCPnts_QuasiUniformDeflection()
                    sampler.Initialize(
                        curve,
                        float(linear_deflection),
                        first,
                        last,
                    )
                    sampled = (
                        [
                            sampler.Value(index)
                            for index in range(1, sampler.NbPoints() + 1)
                        ]
                        if sampler.IsDone() and sampler.NbPoints() >= 2
                        else [curve.Value(first), curve.Value(last)]
                    )
                except (RuntimeError, ValueError):
                    continue
                point_offset = len(points)
                for point in sampled:
                    points.append(
                        (float(point.X()), float(point.Y()), float(point.Z()))
                    )
                lines.extend(
                    [
                        len(sampled),
                        *(point_offset + index for index in range(len(sampled))),
                    ]
                )
                rgba, valid = cls._xcaf_subshape_color(
                    cad_metadata,
                    part,
                    local_edge,
                    edge=True,
                )
                has_colors = has_colors or valid
                part_indices.append(part.part_index)
                edge_indices.append(edge_index)
                source_rgba.append(rgba)
                source_color_valid.append(1 if valid else 0)

        missing_edges = expected_edges.difference(zip(part_indices, edge_indices))
        if missing_edges:
            raise RuntimeError(
                f"OCP could not preserve exact CAD edge identities for: {source_path}"
            )

        dataset = pyvista.PolyData(
            np.asarray(points, dtype=float).reshape((-1, 3)),
            lines=np.asarray(lines, dtype=np.int64),
        )
        dataset.cell_data[_PART_INDEX_ARRAY] = np.asarray(part_indices, dtype=np.int32)
        dataset.cell_data[_EDGE_INDEX_ARRAY] = np.asarray(edge_indices, dtype=np.int32)
        dataset.cell_data[_SOURCE_RGBA_ARRAY] = np.asarray(
            source_rgba, dtype=np.uint8
        ).reshape((-1, 4))
        dataset.cell_data[_SOURCE_COLOR_VALID_ARRAY] = np.asarray(
            source_color_valid,
            dtype=np.uint8,
        )
        return dataset, has_colors

    @classmethod
    def _cad_vertex_dataset(
        cls,
        shape: Any,
        source_path: Path,
        *,
        cad_metadata: _CadMetadata,
    ) -> Any:
        try:
            import pyvista
            from OCP.BRep import BRep_Tool
            from OCP.TopAbs import TopAbs_VERTEX
            from OCP.TopExp import TopExp
            from OCP.TopoDS import TopoDS
            from OCP.TopTools import TopTools_IndexedMapOfShape
        except ModuleNotFoundError as exc:
            raise cls._missing_ocp_error(source_path) from exc

        points: list[tuple[float, float, float]] = []
        part_indices: list[int] = []
        vertex_indices: list[int] = []
        for part in cls._cad_parts(shape, cad_metadata):
            indexed_vertices = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(part.shape, TopAbs_VERTEX, indexed_vertices)
            for vertex_index in range(1, indexed_vertices.Extent() + 1):
                local_vertex = TopoDS.Vertex_s(indexed_vertices.FindKey(vertex_index))
                located_vertex = TopoDS.Vertex_s(local_vertex.Moved(part.location))
                point = BRep_Tool.Pnt_s(located_vertex)
                points.append((float(point.X()), float(point.Y()), float(point.Z())))
                part_indices.append(part.part_index)
                vertex_indices.append(vertex_index)
        if not points:
            raise RuntimeError(
                f"OCP produced no selectable CAD vertices for: {source_path}"
            )
        vertices = np.column_stack(
            (
                np.ones(len(points), dtype=np.int64),
                np.arange(len(points), dtype=np.int64),
            )
        ).reshape(-1)
        dataset = pyvista.PolyData(np.asarray(points, dtype=float), verts=vertices)
        dataset.cell_data[_PART_INDEX_ARRAY] = np.asarray(part_indices, dtype=np.int32)
        dataset.cell_data[_VERTEX_INDEX_ARRAY] = np.asarray(
            vertex_indices, dtype=np.int32
        )
        return dataset

    @classmethod
    def _cad_selection_topology(
        cls,
        shape: Any,
        source_path: Path,
        *,
        cad_metadata: _CadMetadata,
    ) -> dict[str, Any]:
        try:
            from OCP.BRep import BRep_Tool
            from OCP.BRepAdaptor import (
                BRepAdaptor_Curve,
                BRepAdaptor_Curve2d,
                BRepAdaptor_Surface,
            )
            from OCP.BRepLProp import BRepLProp_SLProps
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
            from OCP.TopExp import TopExp, TopExp_Explorer
            from OCP.TopoDS import TopoDS
            from OCP.TopTools import TopTools_IndexedMapOfShape
            from OCP.gp import gp_Pnt, gp_Pnt2d, gp_Vec
        except ModuleNotFoundError as exc:
            raise cls._missing_ocp_error(source_path) from exc

        def mapped_indices(owner: Any, shape_type: Any) -> tuple[Any, list[Any]]:
            mapping = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(owner, shape_type, mapping)
            return mapping, [
                mapping.FindKey(index) for index in range(1, mapping.Extent() + 1)
            ]

        def child_indices(owner: Any, shape_type: Any, mapping: Any) -> list[int]:
            result: list[int] = []
            explorer = TopExp_Explorer(owner, shape_type)
            while explorer.More():
                index = int(mapping.FindIndex(explorer.Current()))
                if index > 0 and index not in result:
                    result.append(index)
                explorer.Next()
            return result

        def edge_direction(edge: Any, vertex: Any) -> tuple[float, float, float]:
            curve = BRepAdaptor_Curve(TopoDS.Edge_s(edge))
            first = float(curve.FirstParameter())
            last = float(curve.LastParameter())
            vertex_point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertex))
            first_point, first_vector = gp_Pnt(), gp_Vec()
            last_point, last_vector = gp_Pnt(), gp_Vec()
            curve.D1(first, first_point, first_vector)
            curve.D1(last, last_point, last_vector)
            use_first = first_point.Distance(vertex_point) <= last_point.Distance(
                vertex_point
            )
            vector = first_vector if use_first else last_vector.Reversed()
            magnitude = float(vector.Magnitude())
            if not math.isfinite(magnitude) or magnitude <= 1e-14:
                raise ValueError("The edge tangent is degenerate at the shared vertex.")
            return (
                float(vector.X()) / magnitude,
                float(vector.Y()) / magnitude,
                float(vector.Z()) / magnitude,
            )

        def face_normal_deviation(
            edge: Any, first_face: Any, second_face: Any
        ) -> float:
            normals: list[Any] = []
            for face in (first_face, second_face):
                curve = BRepAdaptor_Curve2d(TopoDS.Edge_s(edge), TopoDS.Face_s(face))
                parameter = (
                    float(curve.FirstParameter()) + float(curve.LastParameter())
                ) / 2.0
                uv = gp_Pnt2d()
                curve.D0(parameter, uv)
                surface = BRepAdaptor_Surface(TopoDS.Face_s(face), True)
                properties = BRepLProp_SLProps(
                    surface,
                    float(uv.X()),
                    float(uv.Y()),
                    1,
                    1.0e-9,
                )
                if not properties.IsNormalDefined():
                    raise ValueError("The face normal is undefined at the shared edge.")
                normals.append(properties.Normal())
            dot = abs(
                float(normals[0].X()) * float(normals[1].X())
                + float(normals[0].Y()) * float(normals[1].Y())
                + float(normals[0].Z()) * float(normals[1].Z())
            )
            return math.degrees(math.acos(max(-1.0, min(1.0, dot))))

        parts_payload: list[dict[str, Any]] = []
        edge_continuity: list[dict[str, Any]] = []
        face_continuity: list[dict[str, Any]] = []
        edge_failures: list[str] = []
        face_failures: list[str] = []
        body_available = False

        for part in cls._cad_parts(shape, cad_metadata):
            vertex_map, vertices = mapped_indices(part.shape, TopAbs_VERTEX)
            edge_map, edges = mapped_indices(part.shape, TopAbs_EDGE)
            face_map, faces = mapped_indices(part.shape, TopAbs_FACE)
            body_records = cls._cad_body_shapes(part.shape)
            bodies = [record[1] for record in body_records]
            body_available = body_available or bool(body_records)
            vertex_edges: dict[int, list[int]] = {
                index: [] for index in range(1, len(vertices) + 1)
            }
            edge_faces: dict[int, list[int]] = {
                index: [] for index in range(1, len(edges) + 1)
            }
            face_bodies: dict[int, list[int]] = {
                index: [] for index in range(1, len(faces) + 1)
            }
            edge_vertices: dict[int, list[int]] = {}
            face_edges: dict[int, list[int]] = {}
            body_faces: dict[int, list[int]] = {}

            for edge_index, edge in enumerate(edges, start=1):
                indices = child_indices(edge, TopAbs_VERTEX, vertex_map)
                edge_vertices[edge_index] = indices
                for vertex_index in indices:
                    vertex_edges[vertex_index].append(edge_index)
            for face_index, face in enumerate(faces, start=1):
                indices = child_indices(face, TopAbs_EDGE, edge_map)
                face_edges[face_index] = indices
                for edge_index in indices:
                    edge_faces[edge_index].append(face_index)
            for body_index, (_body_kind, _body, body_face_shapes) in enumerate(
                body_records,
                start=1,
            ):
                indices = [
                    int(face_map.FindIndex(body_face))
                    for body_face in body_face_shapes
                    if int(face_map.FindIndex(body_face)) > 0
                ]
                body_faces[body_index] = indices
                for face_index in indices:
                    face_bodies[face_index].append(body_index)

            def entity_id(kind: str, index: int) -> str:
                return f"part:{part.part_index}/{kind}:{index}"

            for vertex_index, incident_edges in vertex_edges.items():
                for first_position, first_edge_index in enumerate(incident_edges):
                    for second_edge_index in incident_edges[first_position + 1 :]:
                        record: dict[str, Any] = {
                            "edge_a": entity_id("edge", first_edge_index),
                            "edge_b": entity_id("edge", second_edge_index),
                            "via_vertex": entity_id("vertex", vertex_index),
                            "supported": True,
                        }
                        try:
                            first_direction = edge_direction(
                                edges[first_edge_index - 1],
                                vertices[vertex_index - 1],
                            )
                            second_direction = edge_direction(
                                edges[second_edge_index - 1],
                                vertices[vertex_index - 1],
                            )
                            dot = max(
                                -1.0,
                                min(
                                    1.0,
                                    sum(
                                        a * b
                                        for a, b in zip(
                                            first_direction,
                                            second_direction,
                                            strict=True,
                                        )
                                    ),
                                ),
                            )
                            angle = math.degrees(math.acos(dot))
                            record["tangent_deviation_degrees"] = abs(180.0 - angle)
                        except (RuntimeError, ValueError) as exc:
                            record.update({"supported": False, "reason": str(exc)})
                            edge_failures.append(str(exc))
                        edge_continuity.append(record)

            for edge_index, incident_faces in edge_faces.items():
                for first_position, first_face_index in enumerate(incident_faces):
                    for second_face_index in incident_faces[first_position + 1 :]:
                        record = {
                            "face_a": entity_id("face", first_face_index),
                            "face_b": entity_id("face", second_face_index),
                            "shared_edge": entity_id("edge", edge_index),
                            "supported": True,
                        }
                        try:
                            continuity = BRep_Tool.Continuity_s(
                                TopoDS.Edge_s(edges[edge_index - 1]),
                                TopoDS.Face_s(faces[first_face_index - 1]),
                                TopoDS.Face_s(faces[second_face_index - 1]),
                            )
                            continuity_order = int(continuity)
                            record.update(
                                {
                                    "continuity": str(continuity).rsplit(".", 1)[-1],
                                    "continuity_order": continuity_order,
                                    "tangent": continuity_order >= 1,
                                    "angular_deviation_degrees": face_normal_deviation(
                                        edges[edge_index - 1],
                                        faces[first_face_index - 1],
                                        faces[second_face_index - 1],
                                    ),
                                }
                            )
                        except (RuntimeError, ValueError) as exc:
                            record.update({"supported": False, "reason": str(exc)})
                            face_failures.append(str(exc))
                        face_continuity.append(record)

            vertex_payload = []
            for vertex_index, vertex in enumerate(vertices, start=1):
                located_vertex = TopoDS.Vertex_s(
                    TopoDS.Vertex_s(vertex).Moved(part.location)
                )
                point = BRep_Tool.Pnt_s(located_vertex)
                vertex_payload.append(
                    {
                        "id": entity_id("vertex", vertex_index),
                        "part_index": part.part_index,
                        "vertex_index": vertex_index,
                        "position": [
                            float(point.X()),
                            float(point.Y()),
                            float(point.Z()),
                        ],
                        "edge_ids": [
                            entity_id("edge", value)
                            for value in vertex_edges[vertex_index]
                        ],
                    }
                )
            parts_payload.append(
                {
                    "part_index": part.part_index,
                    "hierarchy_id": part.hierarchy_id,
                    "vertices": vertex_payload,
                    "edges": [
                        {
                            "id": entity_id("edge", index),
                            "part_index": part.part_index,
                            "edge_index": index,
                            "vertex_ids": [
                                entity_id("vertex", value)
                                for value in edge_vertices[index]
                            ],
                            "face_ids": [
                                entity_id("face", value) for value in edge_faces[index]
                            ],
                        }
                        for index in range(1, len(edges) + 1)
                    ],
                    "faces": [
                        {
                            "id": entity_id("face", index),
                            "part_index": part.part_index,
                            "face_index": index,
                            "body_ids": [
                                entity_id("body", value) for value in face_bodies[index]
                            ],
                            "edge_ids": [
                                entity_id("edge", value) for value in face_edges[index]
                            ],
                        }
                        for index in range(1, len(faces) + 1)
                    ],
                    "bodies": [
                        {
                            "id": entity_id("body", index),
                            "part_index": part.part_index,
                            "body_index": index,
                            "body_kind": body_records[index - 1][0],
                            "face_ids": [
                                entity_id("face", value) for value in body_faces[index]
                            ],
                        }
                        for index in range(1, len(bodies) + 1)
                    ],
                }
            )

        return {
            "schema": ENGINEERING_SELECTION_TOPOLOGY_SCHEMA,
            "source": str(source_path),
            "parts": parts_payload,
            "blocks": [],
            "edge_continuity": edge_continuity,
            "face_continuity": face_continuity,
            "capabilities": {
                "cad_vertex_selection": {
                    "available": any(part["vertices"] for part in parts_payload),
                    "unsupported_reason": (
                        ""
                        if any(part["vertices"] for part in parts_payload)
                        else "The CAD source has no vertices."
                    ),
                },
                "cad_edge_selection": {
                    "available": any(part["edges"] for part in parts_payload),
                    "unsupported_reason": (
                        ""
                        if any(part["edges"] for part in parts_payload)
                        else "The CAD source has no edges."
                    ),
                },
                "cad_face_selection": {
                    "available": any(part["faces"] for part in parts_payload),
                    "unsupported_reason": (
                        ""
                        if any(part["faces"] for part in parts_payload)
                        else "The CAD source has no faces."
                    ),
                },
                "cad_body_selection": {
                    "available": body_available,
                    "unsupported_reason": ""
                    if body_available
                    else "The CAD source has no selectable bodies.",
                },
                "fe_node_selection": {
                    "available": False,
                    "unsupported_reason": "CAD sources do not define FE nodes.",
                },
                "fe_element_face_selection": {
                    "available": False,
                    "unsupported_reason": "CAD sources do not define FE element faces.",
                },
                "fe_element_selection": {
                    "available": False,
                    "unsupported_reason": "CAD sources do not define FE elements.",
                },
                "tangent_edge_propagation": {
                    "available": bool(edge_continuity) and not edge_failures,
                    "unsupported_reason": (
                        edge_failures[0]
                        if edge_failures
                        else ""
                        if edge_continuity
                        else "The CAD topology has no adjacent edge pairs."
                    ),
                },
                "tangent_face_propagation": {
                    "available": bool(face_continuity) and not face_failures,
                    "unsupported_reason": (
                        face_failures[0]
                        if face_failures
                        else ""
                        if face_continuity
                        else "The CAD topology has no adjacent face pairs."
                    ),
                },
            },
        }

    @staticmethod
    def _dataset_length_unit(dataset: Any) -> str:
        candidates = ("length_unit", "length_units", "unit", "units")
        field_data = getattr(dataset, "field_data", {})
        for key in candidates:
            value = None
            for actual_key in getattr(field_data, "keys", lambda: ())():
                if str(actual_key).strip().casefold() == key:
                    value = field_data[actual_key]
                    break
            if value is None:
                continue
            values = getattr(value, "tolist", lambda: value)()
            if isinstance(values, (list, tuple)) and values:
                values = values[0]
            normalized = normalize_length_unit(values)
            if normalized:
                return normalized
        return ""

    @staticmethod
    def _load_ocp_cad(source_path: Path) -> tuple[Any, _CadMetadata]:
        suffix = source_path.suffix.lower()
        try:
            import OCP  # noqa: F401

            if suffix in {".step", ".stp"}:
                return PreparedSceneRuntime._load_step_xcaf(source_path)
            elif suffix in {".iges", ".igs"}:
                from OCP.IFSelect import IFSelect_RetDone
                from OCP.IGESControl import IGESControl_Reader

                reader = IGESControl_Reader()
                if reader.ReadFile(str(source_path)) != IFSelect_RetDone:
                    raise ValueError(f"OCP could not read IGES file: {source_path}")
                reader.TransferRoots()
                shape = reader.OneShape()
            else:
                from OCP.BRep import BRep_Builder
                from OCP.BRepTools import BRepTools
                from OCP.TopoDS import TopoDS_Shape

                shape = TopoDS_Shape()
                read_shape = getattr(BRepTools, "Read_s", None) or getattr(
                    BRepTools, "Read", None
                )
                if not callable(read_shape):
                    raise RuntimeError("Installed OCP does not expose BRepTools.Read.")
                if read_shape(shape, str(source_path), BRep_Builder()) is False:
                    raise ValueError(f"OCP could not read BREP file: {source_path}")
        except ModuleNotFoundError as exc:
            raise PreparedSceneRuntime._missing_ocp_error(source_path) from exc

        if hasattr(shape, "IsNull") and shape.IsNull():
            raise ValueError(f"OCP returned an empty CAD shape for: {source_path}")
        body_id = "cad:body:0"
        hierarchy = (
            {
                "id": body_id,
                "parent_id": "scene:root",
                "name": source_path.name,
                "kind": "body",
                "visible": True,
                "color": {},
                "layers": [],
            },
        )
        return shape, _CadMetadata(
            hierarchy=hierarchy,
            topology_mappings=PreparedSceneRuntime._exact_topology_mappings(
                shape,
                hierarchy,
            ),
            provenance={"cad_metadata": "shape_only"},
        )

    @staticmethod
    def _load_step_xcaf(source_path: Path) -> tuple[Any, _CadMetadata]:
        try:
            from OCP.IFSelect import IFSelect_RetDone
            from OCP.STEPCAFControl import STEPCAFControl_Reader
            from OCP.TCollection import TCollection_ExtendedString
            from OCP.TDocStd import TDocStd_Document
            from OCP.XCAFDoc import XCAFDoc_DocumentTool
        except ModuleNotFoundError as exc:
            raise PreparedSceneRuntime._missing_ocp_error(source_path) from exc

        document = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        reader.SetColorMode(True)
        reader.SetLayerMode(True)
        reader.SetPropsMode(True)
        if reader.ReadFile(str(source_path)) != IFSelect_RetDone:
            raise ValueError(f"OCP could not read STEP file: {source_path}")
        if reader.Transfer(document) is False:
            raise ValueError(f"OCP could not transfer STEP/XCAF data: {source_path}")
        shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
        shape = shape_tool.GetOneShape()
        if hasattr(shape, "IsNull") and shape.IsNull():
            raise ValueError(f"OCP returned an empty STEP shape for: {source_path}")

        hierarchy, parts = PreparedSceneRuntime._xcaf_hierarchy(document, source_path)
        unit_names = PreparedSceneRuntime._step_length_unit_names(reader.Reader())
        normalized_units = {
            normalized
            for unit_name in unit_names
            if (normalized := normalize_length_unit(unit_name))
        }
        length_unit = next(iter(normalized_units)) if len(normalized_units) == 1 else ""
        return shape, _CadMetadata(
            hierarchy=hierarchy,
            topology_mappings=PreparedSceneRuntime._exact_topology_mappings(
                shape,
                hierarchy,
                parts=parts,
            ),
            length_unit=length_unit,
            provenance={
                "cad_metadata": "xcaf",
                "source_length_units": list(unit_names),
            },
            document=document,
            parts=parts,
        )

    @staticmethod
    def _step_length_unit_names(reader: Any) -> tuple[str, ...]:
        from OCP.TColStd import TColStd_SequenceOfAsciiString

        length_names = TColStd_SequenceOfAsciiString()
        angle_names = TColStd_SequenceOfAsciiString()
        solid_angle_names = TColStd_SequenceOfAsciiString()
        reader.FileUnits(length_names, angle_names, solid_angle_names)
        return tuple(
            str(length_names.Value(index).ToCString()).strip()
            for index in range(1, length_names.Length() + 1)
            if str(length_names.Value(index).ToCString()).strip()
        )

    @staticmethod
    def _xcaf_hierarchy(
        document: Any,
        source_path: Path,
    ) -> tuple[tuple[dict[str, Any], ...], tuple[_CadPart, ...]]:
        from OCP.Quantity import Quantity_ColorRGBA
        from OCP.TCollection import TCollection_AsciiString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
        from OCP.TopLoc import TopLoc_Location
        from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool

        shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
        color_tool = XCAFDoc_DocumentTool.ColorTool_s(document.Main())
        layer_tool = XCAFDoc_DocumentTool.LayerTool_s(document.Main())

        def label_entry(label: Any) -> str:
            value = TCollection_AsciiString()
            TDF_Tool.Entry_s(label, value)
            return str(value.ToCString()).strip()

        def label_name(label: Any) -> str:
            attribute = TDataStd_Name()
            if label.FindAttribute(TDataStd_Name.GetID_s(), attribute):
                return str(attribute.Get().ToExtString()).strip()
            return ""

        def label_color(label: Any) -> dict[str, Any]:
            for color_type, role in (
                (XCAFDoc_ColorType.XCAFDoc_ColorSurf, "surface"),
                (XCAFDoc_ColorType.XCAFDoc_ColorGen, "general"),
                (XCAFDoc_ColorType.XCAFDoc_ColorCurv, "curve"),
            ):
                color = Quantity_ColorRGBA()
                if color_tool.GetColor_s(label, color_type, color):
                    rgb = color.GetRGB()
                    return {
                        "role": role,
                        "rgba": [
                            float(rgb.Red()),
                            float(rgb.Green()),
                            float(rgb.Blue()),
                            float(color.Alpha()),
                        ],
                    }
            return {}

        def label_layers(label: Any) -> list[str]:
            layers = layer_tool.GetLayers(label)
            return [
                str(layers.Value(index).ToExtString()).strip()
                for index in range(1, layers.Length() + 1)
                if str(layers.Value(index).ToExtString()).strip()
            ]

        hierarchy: list[dict[str, Any]] = []
        parts: list[_CadPart] = []

        def visit(
            label: Any,
            *,
            parent_id: str,
            path: tuple[str, ...],
            parent_location: Any,
        ) -> None:
            referred = TDF_Label()
            is_reference = bool(shape_tool.GetReferredShape_s(label, referred))
            definition = referred if is_reference else label
            entry = label_entry(label) or f"label-{len(hierarchy) + 1}"
            item_path = (*path, entry)
            item_id = "cad:" + "/".join(item_path)
            name = label_name(label) or label_name(definition) or source_path.stem
            is_assembly = bool(shape_tool.IsAssembly_s(definition))
            world_location = parent_location.Multiplied(shape_tool.GetLocation_s(label))
            item = {
                "id": item_id,
                "parent_id": parent_id,
                "name": name,
                "kind": "instance"
                if is_reference
                else "assembly"
                if is_assembly
                else "body",
                "visible": True,
                "label_entry": entry,
                "definition_label_entry": label_entry(definition),
                "color": label_color(label) or label_color(definition),
                "layers": label_layers(label) or label_layers(definition),
            }
            if not is_assembly:
                part_shape = shape_tool.GetShape_s(definition)
                if not part_shape.IsNull():
                    part_index = len(parts) + 1
                    item["part_index"] = part_index
                    parts.append(
                        _CadPart(
                            part_index=part_index,
                            hierarchy_id=item_id,
                            shape=part_shape,
                            location=world_location,
                            instance_label=label,
                            definition_label=definition,
                        )
                    )
            hierarchy.append(item)
            if not is_assembly:
                return
            components = TDF_LabelSequence()
            shape_tool.GetComponents_s(definition, components, False)
            for index in range(1, components.Length() + 1):
                visit(
                    components.Value(index),
                    parent_id=item_id,
                    path=item_path,
                    parent_location=world_location,
                )

        roots = TDF_LabelSequence()
        shape_tool.GetFreeShapes(roots)
        for index in range(1, roots.Length() + 1):
            visit(
                roots.Value(index),
                parent_id="scene:root",
                path=(),
                parent_location=TopLoc_Location(),
            )
        if hierarchy:
            return tuple(hierarchy), tuple(parts)
        fallback_shape = shape_tool.GetOneShape()
        return (
            (
                {
                    "id": "cad:body:0",
                    "parent_id": "scene:root",
                    "name": source_path.name,
                    "kind": "body",
                    "visible": True,
                    "label_entry": "",
                    "definition_label_entry": "",
                    "color": {},
                    "layers": [],
                    "part_index": 1,
                },
            ),
            (
                _CadPart(
                    part_index=1,
                    hierarchy_id="cad:body:0",
                    shape=fallback_shape,
                    location=TopLoc_Location(),
                ),
            ),
        )

    @staticmethod
    def _exact_topology_mappings(
        shape: Any,
        hierarchy: tuple[dict[str, Any], ...],
        *,
        parts: tuple[_CadPart, ...] = (),
    ) -> dict[str, Any]:
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        def indexed_ids(kind: str, shape_type: Any) -> list[dict[str, Any]]:
            shapes = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(shape, shape_type, shapes)
            return [
                {"id": f"{kind}:{index:08d}", "occt_index": index}
                for index in range(1, shapes.Extent() + 1)
            ]

        def part_entities(kind: str, shape_type: Any) -> list[dict[str, Any]]:
            entities: list[dict[str, Any]] = []
            for part in parts:
                shapes = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(part.shape, shape_type, shapes)
                entities.extend(
                    {
                        "id": f"part:{part.part_index}/{kind}:{index}",
                        "part_index": part.part_index,
                        f"{kind}_index": index,
                        "occt_index": index,
                    }
                    for index in range(1, shapes.Extent() + 1)
                )
            return entities

        def body_entities(body_parts: tuple[_CadPart, ...]) -> list[dict[str, Any]]:
            entities: list[dict[str, Any]] = []
            owners = body_parts or (
                _CadPart(
                    part_index=1,
                    hierarchy_id="cad:body:0",
                    shape=shape,
                    location=None,
                ),
            )
            for part in owners:
                entities.extend(
                    {
                        "id": f"part:{part.part_index}/body:{body_index}",
                        "part_index": part.part_index,
                        "body_index": body_index,
                        "body_kind": body_kind,
                    }
                    for body_index, (body_kind, _body, _faces) in enumerate(
                        PreparedSceneRuntime._cad_body_shapes(part.shape),
                        start=1,
                    )
                )
            return entities

        return {
            "parts": [
                {
                    "id": str(item["id"]),
                    "kind": str(item["kind"]),
                    **(
                        {"part_index": int(item["part_index"])}
                        if "part_index" in item
                        else {}
                    ),
                }
                for item in hierarchy
                if str(item.get("kind", "")) in {"assembly", "instance", "body"}
            ],
            "bodies": {
                "policy": "part_local_exact_body_index",
                "stable_for_source_fingerprint": True,
                "entities": body_entities(parts),
            },
            "faces": {
                "policy": "part_local_occt_indexed_map"
                if parts
                else "occt_indexed_map",
                "stable_for_source_fingerprint": True,
                "entities": (
                    part_entities("face", TopAbs_FACE)
                    if parts
                    else indexed_ids("face", TopAbs_FACE)
                ),
            },
            "edges": {
                "policy": "part_local_occt_indexed_map"
                if parts
                else "occt_indexed_map",
                "stable_for_source_fingerprint": True,
                "entities": (
                    part_entities("edge", TopAbs_EDGE)
                    if parts
                    else indexed_ids("edge", TopAbs_EDGE)
                ),
            },
            "vertices": {
                "policy": "part_local_occt_indexed_map"
                if parts
                else "occt_indexed_map",
                "stable_for_source_fingerprint": True,
                "entities": (
                    part_entities("vertex", TopAbs_VERTEX)
                    if parts
                    else indexed_ids("vertex", TopAbs_VERTEX)
                ),
            },
        }

    @staticmethod
    def _missing_ocp_error(source_path: Path) -> RuntimeError:
        return RuntimeError(
            f"CAD import for '{source_path.suffix.lower()}' requires the optional cadquery-ocp "
            "package (Python module 'OCP'). STL remains available without OCP."
        )


__all__ = ["PreparedScene", "PreparedSceneRuntime"]
