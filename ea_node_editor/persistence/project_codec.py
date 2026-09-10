from __future__ import annotations

import copy
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ea_node_editor.graph.hierarchy import normalize_scope_path
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.graph.workspace_state import ViewState, WorkspaceData
from ea_node_editor.graph.record_payloads import (
    edge_instance_from_mapping,
    edge_instance_to_mapping,
    node_instance_from_mapping,
    node_instance_to_mapping,
)
from ea_node_editor.graph.hierarchy import sanitize_workspace_parent_links
from ea_node_editor.graph.registry_normalization import normalize_project_for_registry
from ea_node_editor.nodes.builtins.web_viewer import (
    WEB_PAGE_VIEWER_TYPE_ID,
    normalize_web_page_viewer_properties,
)
from ea_node_editor.nodes.node_specs import PropertySpec
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.common.payload_tools import copy_json_safe
from ea_node_editor.common.artifact_refs import (
    ManagedArtifactRef,
    StagedArtifactRef,
    parse_artifact_ref,
)
from ea_node_editor.persistence.artifact_store import (
    ProjectArtifactStore,
    normalize_artifact_store_metadata,
)
from ea_node_editor.persistence.migration import JsonProjectMigration
from ea_node_editor.runtime_contracts import (
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    ArrayDataRef,
    ArraySlice2DRef,
    DataTree,
    Interval1D,
    RuntimeArtifactRef,
    RuntimeHandleRef,
    ImageValue,
    TabularDataRef,
    TabularWindowRef,
    TypedInlineValue,
    deserialize_runtime_value,
    serialize_runtime_value,
)
from ea_node_editor.settings import SCHEMA_VERSION
from ea_node_editor.workspace.ownership import resolve_workspace_ownership, sync_project_workspace_ownership

_GROUP_BACKDROP_RUNTIME_MEMBERSHIP_KEYS = (
    "owner_backdrop_id",
    "backdrop_depth",
    "member_node_ids",
    "member_backdrop_ids",
    "contained_node_ids",
    "contained_backdrop_ids",
)
_OBSOLETE_PORT_LOCKING_VIEW_STATE_KEY = "port_locking_view_state"
_LEGACY_RECOVERY_METADATA_KEYS = (
    "_persistence_envelope",
    "_runtime_unresolved_workspaces",
)


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _legacy_recovery_payload_has_content(payload: Any) -> bool:
    if isinstance(payload, Mapping):
        return any(
            str(key) != "document_flavor" and _legacy_recovery_payload_has_content(value)
            for key, value in payload.items()
        )
    if isinstance(payload, list | tuple | set | frozenset):
        return any(_legacy_recovery_payload_has_content(value) for value in payload)
    return bool(payload)


def _drop_or_reject_legacy_recovery_metadata(metadata: dict[str, Any]) -> None:
    for key in _LEGACY_RECOVERY_METADATA_KEYS:
        payload = metadata.pop(key, None)
        if _legacy_recovery_payload_has_content(payload):
            raise ValueError(
                "Legacy project contains unresolved add-ons in recovery metadata."
            )


def _iter_reserved_artifact_ref_strings(payload: Any):
    if isinstance(payload, str):
        stripped = payload.strip()
        if stripped.casefold().startswith(("saved://", "temp://")):
            yield payload
        return
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            yield from _iter_reserved_artifact_ref_strings(key)
            yield from _iter_reserved_artifact_ref_strings(value)
        return
    if isinstance(payload, (list, tuple, set, frozenset)):
        for value in payload:
            yield from _iter_reserved_artifact_ref_strings(value)


@dataclass(frozen=True, slots=True)
class ProjectArtifactReferenceSet:
    managed_ids: frozenset[str]
    staged_ids: frozenset[str]


def collect_project_artifact_references(payload: Any) -> ProjectArtifactReferenceSet:
    managed_ids: set[str] = set()
    staged_ids: set[str] = set()
    _collect_project_artifact_references(payload, managed_ids=managed_ids, staged_ids=staged_ids)
    return ProjectArtifactReferenceSet(
        managed_ids=frozenset(managed_ids),
        staged_ids=frozenset(staged_ids),
    )


def _collect_project_artifact_references(
    payload: Any,
    *,
    managed_ids: set[str],
    staged_ids: set[str],
) -> None:
    if isinstance(payload, str):
        parsed = parse_artifact_ref(payload)
        if isinstance(parsed, ManagedArtifactRef):
            managed_ids.add(parsed.artifact_id)
        elif isinstance(parsed, StagedArtifactRef):
            staged_ids.add(parsed.artifact_id)
        return
    if isinstance(payload, Mapping):
        for value in payload.values():
            _collect_project_artifact_references(value, managed_ids=managed_ids, staged_ids=staged_ids)
        return
    if isinstance(payload, list | tuple | set | frozenset):
        for value in payload:
            _collect_project_artifact_references(value, managed_ids=managed_ids, staged_ids=staged_ids)


def rewrite_project_artifact_refs(payload: Any, replacements: Mapping[str, str]) -> Any:
    replacement_map = {
        str(source): str(target)
        for source, target in replacements.items()
        if str(source).strip() and str(target).strip()
    }
    if not replacement_map:
        return payload
    return _rewrite_project_artifact_refs(payload, replacements=replacement_map)


def _rewrite_project_artifact_refs(payload: Any, *, replacements: Mapping[str, str]) -> Any:
    if isinstance(payload, RuntimeArtifactRef):
        replacement = replacements.get(payload.ref)
        return replacement if replacement is not None else copy.deepcopy(payload)
    if isinstance(payload, str):
        return replacements.get(payload, payload)
    if isinstance(payload, Mapping):
        return {
            copy.deepcopy(key): _rewrite_project_artifact_refs(value, replacements=replacements)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_rewrite_project_artifact_refs(value, replacements=replacements) for value in payload]
    if isinstance(payload, tuple):
        return tuple(_rewrite_project_artifact_refs(value, replacements=replacements) for value in payload)
    if isinstance(payload, set):
        return {_rewrite_project_artifact_refs(value, replacements=replacements) for value in payload}
    if isinstance(payload, frozenset):
        return frozenset(_rewrite_project_artifact_refs(value, replacements=replacements) for value in payload)
    return copy.deepcopy(payload)


class JsonProjectCodec:
    def __init__(self, registry: NodeRegistry | None = None) -> None:
        self._registry = registry
        self.last_load_phase_timings_ms: dict[str, float] = {}

    @staticmethod
    def _copy_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(dict(mapping))

    @staticmethod
    def _normalize_owned_node_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
        from ea_node_editor.common.node_property_migrations import migrate_panel_properties

        for key in _GROUP_BACKDROP_RUNTIME_MEMBERSHIP_KEYS:
            mapping.pop(key, None)
        type_id = str(mapping.get("type_id", "")).strip()
        if type_id == "data.panel" and isinstance(mapping.get("properties"), Mapping):
            mapping["properties"] = migrate_panel_properties(type_id, mapping["properties"])
        if type_id == WEB_PAGE_VIEWER_TYPE_ID:
            properties = mapping.get("properties")
            if isinstance(properties, Mapping):
                mapping["properties"] = normalize_web_page_viewer_properties(properties)
        if type_id.startswith("plot."):
            properties = mapping.get("properties")
            if isinstance(properties, dict):
                # Legacy projects embedded plot series data in node properties;
                # plot series now live outside the document, so strip the key on
                # both load and save (files shrink on the next save).
                properties.pop("preview_series", None)
        return mapping

    @classmethod
    def _copy_node_mapping(cls, mapping: Mapping[str, Any]) -> dict[str, Any]:
        return cls._normalize_owned_node_mapping(cls._copy_mapping(mapping))

    def _prepare_project_properties(
        self,
        *,
        node_type_id: str,
        properties: Mapping[str, Any],
        artifact_store: ProjectArtifactStore | None = None,
    ) -> dict[str, Any]:
        if self._registry is None:
            return copy.deepcopy(dict(properties))
        spec = self._registry.spec_or_none(node_type_id)
        if spec is not None:
            spec = self._registry.resolve_spec(node_type_id, properties)
        property_specs = (
            {prop.key: prop for prop in spec.properties}
            if spec is not None
            else {}
        )
        return {
            str(key): self._prepare_project_property_value(
                value,
                property_spec=property_specs.get(str(key)),
                context=f"node type {node_type_id!r} property {str(key)!r}",
                root=True,
                artifact_store=artifact_store,
            )
            for key, value in properties.items()
        }

    def _prepare_project_property_value(
        self,
        value: Any,
        *,
        property_spec: PropertySpec | None,
        context: str,
        root: bool,
        artifact_store: ProjectArtifactStore | None = None,
    ) -> Any:
        if self._registry is None:
            return copy.deepcopy(value)
        catalog = self._registry.data_types
        declared_type_id = (
            property_spec.persistence_data_type_id
            if property_spec is not None
            else ""
        )
        declared_spec = (
            catalog.require(declared_type_id)
            if declared_type_id
            else None
        )

        if isinstance(value, DataTree):
            raise ValueError(f"{context} cannot persist a DataTree")
        if isinstance(value, ImageValue):
            if not declared_type_id or declared_spec is None:
                raise ValueError(f"{context} does not permit typed persistence")
            if declared_spec.persistence != "inline":
                raise ValueError(f"{context} data type does not permit image persistence")
            catalog.validate_carrier(declared_type_id, value)
            return value
        if isinstance(
            value,
            (
                RuntimeHandleRef,
                TabularDataRef,
                ArrayDataRef,
                TabularWindowRef,
                ArraySlice2DRef,
            ),
        ):
            raise ValueError(f"{context} cannot persist a live handle")
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError(f"{context} cannot persist bytes")
        if isinstance(value, RuntimeArtifactRef):
            if not declared_type_id or declared_spec is None:
                raise ValueError(f"{context} does not permit typed persistence")
            actual_spec = catalog.require(value.data_type_id)
            if (
                declared_spec.persistence != "saved_artifact"
                or actual_spec.persistence != "saved_artifact"
            ):
                raise ValueError(
                    f"{context} data type does not permit saved_artifact persistence"
                )
            catalog.validate_carrier(declared_type_id, value)
            if artifact_store is None:
                raise ValueError(
                    f"{context} typed artifact requires artifact-store metadata"
                )
            self._require_typed_artifact(
                artifact_ref=value.ref,
                property_spec=property_spec,
                store=artifact_store,
                context=context,
                expected_descriptor=value.to_descriptor(),
            )
            return value.ref
        if isinstance(value, (TypedInlineValue, Interval1D)):
            if not declared_type_id or declared_spec is None:
                raise ValueError(f"{context} does not permit typed persistence")
            actual_type_id = (
                value.data_type_id
                if isinstance(value, TypedInlineValue)
                else INTERVAL_1D_GRAPH_DATA_TYPE_ID
            )
            actual_spec = catalog.require(actual_type_id)
            if (
                declared_spec.persistence != "inline"
                or actual_spec.persistence != "inline"
            ):
                raise ValueError(
                    f"{context} data type does not permit inline persistence"
                )
            catalog.validate_carrier(declared_type_id, value)
            return value
        if isinstance(value, Mapping):
            if "__ea_runtime_value__" in value:
                try:
                    decoded = deserialize_runtime_value(value, catalog=catalog)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"{context} contains an unauthorized runtime marker"
                    ) from exc
                if isinstance(decoded, Mapping):
                    raise ValueError(
                        f"{context} contains an unauthorized runtime marker"
                    )
                if isinstance(decoded, RuntimeArtifactRef):
                    raise ValueError(
                        f"{context} typed artifact must use a saved:// ref"
                    )
                prepared = self._prepare_project_property_value(
                    decoded,
                    property_spec=property_spec,
                    context=context,
                    root=root,
                    artifact_store=artifact_store,
                )
                return serialize_runtime_value(prepared, catalog=catalog)
            copied = {
                str(key): self._prepare_project_property_value(
                    item,
                    property_spec=property_spec,
                    context=context,
                    root=False,
                    artifact_store=artifact_store,
                )
                for key, item in value.items()
                if isinstance(key, str)
            }
            if len(copied) != len(value):
                raise TypeError(f"{context} mapping keys must be strings")
            if root and declared_spec is not None:
                if declared_spec.persistence != "inline":
                    raise ValueError(
                        f"{context} must use a saved:// artifact ref"
                    )
                catalog.validate_carrier(declared_type_id, copied)
            return copied
        if isinstance(value, (list, tuple)):
            copied = [
                self._prepare_project_property_value(
                    item,
                    property_spec=property_spec,
                    context=context,
                    root=False,
                    artifact_store=artifact_store,
                )
                for item in value
            ]
            if root and declared_spec is not None:
                if declared_spec.persistence != "inline":
                    raise ValueError(
                        f"{context} must use a saved:// artifact ref"
                    )
                catalog.validate_carrier(declared_type_id, copied)
            return copied

        try:
            copied = copy_json_safe(value, field_name=context)
        except (TypeError, ValueError) as exc:
            raise type(exc)(f"{context}: {exc}") from exc
        if root and declared_spec is not None:
            if declared_spec.persistence == "saved_artifact":
                parsed = parse_artifact_ref(copied)
                if copied != "" and not isinstance(
                    parsed,
                    (ManagedArtifactRef, StagedArtifactRef),
                ):
                    raise ValueError(
                        f"{context} must use a saved:// artifact ref"
                    )
                if (
                    copied != ""
                    and artifact_store is not None
                    and isinstance(parsed, (ManagedArtifactRef, StagedArtifactRef))
                ):
                    self._require_typed_artifact(
                        artifact_ref=parsed.as_string(),
                        property_spec=property_spec,
                        store=artifact_store,
                        context=context,
                    )
            else:
                catalog.validate_carrier(declared_type_id, copied)
        return copied

    def _require_typed_artifact(
        self,
        *,
        artifact_ref: str,
        property_spec: PropertySpec,
        store: ProjectArtifactStore,
        context: str,
        expected_descriptor: Mapping[str, Any] | None = None,
    ) -> None:
        if self._registry is None:
            raise ValueError(f"{context} requires an active node registry")
        parsed = parse_artifact_ref(artifact_ref)
        if isinstance(parsed, ManagedArtifactRef):
            scope_label = "managed"
            entry = store.managed_entry(parsed.artifact_id)
        elif isinstance(parsed, StagedArtifactRef):
            scope_label = "staged"
            entry = store.staged_entry(parsed.artifact_id)
        else:
            raise ValueError(f"{context} typed artifact ref is invalid")
        if entry is None:
            raise ValueError(
                f"{context} references unowned {scope_label} artifact "
                f"{parsed.artifact_id!r}"
            )
        descriptor = entry.extra.get("runtime_artifact")
        if not isinstance(descriptor, Mapping):
            raise ValueError(
                f"{context} {scope_label} artifact "
                f"{parsed.artifact_id!r} descriptor is missing"
            )
        try:
            runtime_ref = RuntimeArtifactRef.from_artifact_ref(
                artifact_ref,
                data_type_id=descriptor["data_type_id"],
                schema_version=descriptor["schema_version"],
                format=descriptor["format"],
                size_bytes=descriptor["size_bytes"],
                sha256=descriptor["sha256"],
                provenance=descriptor["provenance"],
            )
            expected = runtime_ref.to_descriptor()
            if set(descriptor) != set(expected):
                raise ValueError
            if any(
                type(descriptor[key]) is not type(expected_value)
                or descriptor[key] != expected_value
                for key, expected_value in expected.items()
            ):
                raise ValueError
            if expected_descriptor is not None and (
                set(expected_descriptor) != set(expected)
                or any(
                    type(expected_descriptor[key]) is not type(expected_value)
                    or expected_descriptor[key] != expected_value
                    for key, expected_value in expected.items()
                )
            ):
                raise ValueError
            actual_spec = self._registry.data_types.require(
                runtime_ref.data_type_id
            )
            if actual_spec.persistence != "saved_artifact":
                raise ValueError
            self._registry.data_types.validate_carrier(
                property_spec.persistence_data_type_id,
                runtime_ref,
            )
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                f"{context} {scope_label} artifact "
                f"{parsed.artifact_id!r} descriptor is invalid"
            ) from None

    def validate_persistent_document(self, document: Mapping[str, Any]) -> None:
        copy_json_safe(document, field_name="persistent project document")
        property_payloads: list[tuple[str, Mapping[str, Any]]] = []
        for workspace in document.get("workspaces", ()):
            if not isinstance(workspace, Mapping):
                continue
            for node in workspace.get("nodes", ()):
                if not isinstance(node, Mapping):
                    continue
                properties = node.get("properties")
                if not isinstance(properties, Mapping):
                    continue
                property_payloads.append(
                    (str(node.get("type_id", "")).strip(), properties)
                )

        def reject_unauthorized_runtime_markers(
            payload: Any,
            *,
            context: str,
            path: tuple[object, ...] = (),
        ) -> None:
            if isinstance(payload, Mapping):
                if "__ea_runtime_value__" in payload:
                    raise ValueError(
                        f"{context} contains an unauthorized runtime marker"
                    )
                if (
                    len(path) == 5
                    and path[0] == "workspaces"
                    and isinstance(path[1], int)
                    and path[2] == "nodes"
                    and isinstance(path[3], int)
                    and path[4] == "properties"
                ):
                    return
                for key, value in payload.items():
                    reject_unauthorized_runtime_markers(
                        value,
                        context=f"{context}.{key}",
                        path=(*path, key),
                    )
                return
            if isinstance(payload, (list, tuple)):
                for index, value in enumerate(payload):
                    reject_unauthorized_runtime_markers(
                        value,
                        context=f"{context}[{index}]",
                        path=(*path, index),
                    )

        reject_unauthorized_runtime_markers(document, context="persistent project")
        managed_artifact_ids: set[str] = set()
        for raw_ref in _iter_reserved_artifact_ref_strings(document):
            parsed = parse_artifact_ref(raw_ref)
            if isinstance(parsed, StagedArtifactRef):
                raise ValueError("persistent project cannot contain temp:// refs")
            if not isinstance(parsed, ManagedArtifactRef) or raw_ref != parsed.as_string():
                raise ValueError(
                    f"persistent project contains malformed artifact ref {raw_ref!r}"
                )
            managed_artifact_ids.add(parsed.artifact_id)

        metadata = (
            document.get("metadata")
            if isinstance(document.get("metadata"), Mapping)
            else {}
        )
        store = ProjectArtifactStore.from_project_metadata(
            project_path=None,
            project_metadata=metadata,
        )
        for artifact_id in managed_artifact_ids:
            if store.managed_entry(artifact_id) is None:
                raise ValueError(
                    f"persistent project references unowned managed artifact "
                    f"{artifact_id!r}"
                )

        for node_type_id, properties in property_payloads:
            self._prepare_project_properties(
                node_type_id=node_type_id,
                properties=properties,
                artifact_store=store,
            )
            spec = (
                self._registry.spec_or_none(node_type_id)
                if self._registry is not None
                else None
            )
            if spec is None:
                continue
            spec = self._registry.resolve_spec(node_type_id, properties)
            for property_spec in spec.properties:
                if (
                    not property_spec.persistence_data_type_id
                    or self._registry.data_types.require(
                        property_spec.persistence_data_type_id
                    ).persistence
                    != "saved_artifact"
                ):
                    continue
                value = properties.get(property_spec.key)
                parsed = parse_artifact_ref(value)
                if isinstance(parsed, ManagedArtifactRef):
                    self._require_typed_artifact(
                        artifact_ref=parsed.as_string(),
                        property_spec=property_spec,
                        store=store,
                        context=(
                            f"node type {node_type_id!r} property "
                            f"{property_spec.key!r}"
                        ),
                    )

    def to_document(self, project: ProjectData) -> dict[str, Any]:
        return self._encode_document(project, include_runtime_fields=True)

    def to_persistent_document(self, project: ProjectData) -> dict[str, Any]:
        return self._encode_document(project, include_runtime_fields=False)

    def _encode_document(
        self,
        project: ProjectData,
        *,
        include_runtime_fields: bool,
    ) -> dict[str, Any]:
        metadata = project.metadata if isinstance(project.metadata, Mapping) else {}
        ownership = resolve_workspace_ownership(
            project.workspaces,
            order_sources=(metadata.get("workspace_order"),),
            active_workspace_id=project.active_workspace_id,
        )
        metadata = JsonProjectMigration.normalize_metadata(metadata, ownership.workspace_order)
        _drop_or_reject_legacy_recovery_metadata(metadata)
        metadata["artifact_store"] = normalize_artifact_store_metadata(metadata.get("artifact_store"))
        metadata.pop(_OBSOLETE_PORT_LOCKING_VIEW_STATE_KEY, None)
        artifact_store = ProjectArtifactStore.from_project_metadata(
            project_path=None,
            project_metadata=metadata,
        )

        workspaces: list[dict[str, Any]] = []
        for workspace_id in ownership.workspace_order:
            workspace = project.workspaces[workspace_id]
            workspace.ensure_default_view()
            active_view_id = workspace.active_view_id
            if active_view_id not in workspace.views:
                active_view_id = next(iter(workspace.views))
            workspace_doc = {
                "workspace_id": workspace.workspace_id,
                "name": workspace.name,
                "dirty": workspace.dirty,
                "active_view_id": active_view_id,
                "views": [
                    {
                        "view_id": view.view_id,
                        "name": view.name,
                        "zoom": view.zoom,
                        "pan_x": view.pan_x,
                        "pan_y": view.pan_y,
                        "scope_path": list(normalize_scope_path(workspace, view.scope_path)),
                        "hide_optional_ports": view.hide_optional_ports,
                    }
                    for view in workspace.views.values()
                ],
            }
            if include_runtime_fields:
                workspace_doc["document_fields"] = {
                    key: copy.deepcopy(value)
                    for key, value in workspace_doc.items()
                    if key not in {"nodes", "edges", "document_fields"}
                }
            workspace_doc["nodes"] = self._workspace_node_docs(
                workspace,
                artifact_store=artifact_store,
            )
            workspace_doc["edges"] = self._workspace_edge_docs(workspace)
            workspaces.append(workspace_doc)
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": project.project_id,
            "name": project.name,
            "active_workspace_id": ownership.active_workspace_id,
            "workspace_order": ownership.workspace_order,
            "workspaces": workspaces,
            "metadata": metadata,
        }

    def from_document(self, payload: dict[str, Any]) -> ProjectData:
        started = time.perf_counter()
        workspace_decode_ms = 0.0
        node_decode_ms = 0.0
        edge_decode_ms = 0.0
        registry_lookup_ms = 0.0
        project = ProjectData(
            project_id=payload.get("project_id", "proj_unknown"),
            name=payload.get("name", "untitled"),
            schema_version=int(payload.get("schema_version", SCHEMA_VERSION)),
            active_workspace_id=payload.get("active_workspace_id", ""),
            metadata=dict(payload.get("metadata", {})) if isinstance(payload.get("metadata"), Mapping) else {},
        )
        _drop_or_reject_legacy_recovery_metadata(project.metadata)
        project.metadata.pop(_OBSOLETE_PORT_LOCKING_VIEW_STATE_KEY, None)
        for ws_doc in payload.get("workspaces", []):
            if not isinstance(ws_doc, Mapping):
                continue
            workspace_id = str(ws_doc.get("workspace_id", "")).strip()
            workspace_name = str(ws_doc.get("name", "")).strip()
            if not workspace_id or not workspace_name:
                continue
            workspace_started = time.perf_counter()
            workspace = WorkspaceData(
                workspace_id=workspace_id,
                name=workspace_name,
                active_view_id=ws_doc.get("active_view_id", ""),
                dirty=bool(ws_doc.get("dirty", False)),
            )
            for view_doc in ws_doc.get("views", []):
                if not isinstance(view_doc, Mapping):
                    continue
                view_id = view_doc.get("view_id")
                if not view_id:
                    continue
                view = ViewState(
                    view_id=str(view_id),
                    name=view_doc.get("name", "V"),
                    zoom=float(view_doc.get("zoom", 1.0)),
                    pan_x=float(view_doc.get("pan_x", 0.0)),
                    pan_y=float(view_doc.get("pan_y", 0.0)),
                    scope_path=[
                        str(item).strip()
                        for item in view_doc.get("scope_path", [])
                        if str(item).strip()
                    ],
                    hide_optional_ports=_coerce_bool(view_doc.get("hide_optional_ports"), False),
                )
                workspace.views[view.view_id] = view
            workspace.ensure_default_view()
            if workspace.active_view_id not in workspace.views:
                workspace.active_view_id = next(iter(workspace.views))

            for node_doc in ws_doc.get("nodes", []):
                if not isinstance(node_doc, Mapping):
                    continue
                node_started = time.perf_counter()
                if self._node_doc_is_unresolved(node_doc):
                    raise ValueError(
                        "Project contains unresolved node type: "
                        + str(node_doc.get("type_id", "")).strip()
                    )
                self._decode_workspace_node_doc(workspace, node_doc=node_doc)
                node_decode_ms += _elapsed_ms(node_started)
            valid_node_ids = set(workspace.nodes)
            for edge_doc in ws_doc.get("edges", []):
                if not isinstance(edge_doc, Mapping):
                    continue
                edge_started = time.perf_counter()
                self._decode_workspace_edge_doc(
                    workspace,
                    edge_doc=edge_doc,
                    valid_node_ids=valid_node_ids,
                )
                edge_decode_ms += _elapsed_ms(edge_started)
            sanitize_workspace_parent_links(workspace)
            project.workspaces[workspace.workspace_id] = workspace
            workspace_decode_ms += _elapsed_ms(workspace_started)

        project.ensure_default_workspace()
        ownership = sync_project_workspace_ownership(
            project,
            order_sources=(payload.get("workspace_order"),),
        )
        metadata = JsonProjectMigration.normalize_metadata(project.metadata, ownership.workspace_order)
        metadata["artifact_store"] = normalize_artifact_store_metadata(metadata.get("artifact_store"))
        project.replace_metadata(metadata)
        if self._registry is not None:
            registry_started = time.perf_counter()
            normalize_project_for_registry(project, self._registry)
            registry_lookup_ms = _elapsed_ms(registry_started)
        for workspace in project.workspaces.values():
            for view in workspace.views.values():
                view.scope_path = list(normalize_scope_path(workspace, view.scope_path))
        total_ms = _elapsed_ms(started)
        self.last_load_phase_timings_ms = {
            "project_conversion_ms": max(0.0, total_ms - registry_lookup_ms),
            "registry_lookup_ms": registry_lookup_ms,
            "workspace_decode_ms": workspace_decode_ms,
            "node_decode_ms": node_decode_ms,
            "edge_decode_ms": edge_decode_ms,
        }
        return project

    def _workspace_node_docs(
        self,
        workspace: WorkspaceData,
        *,
        artifact_store: ProjectArtifactStore,
    ) -> list[dict[str, Any]]:
        node_docs: list[dict[str, Any]] = []
        for node in sorted(workspace.nodes.values(), key=lambda item: item.node_id):
            prepared_properties = self._prepare_project_properties(
                node_type_id=node.type_id,
                properties=node.properties,
                artifact_store=artifact_store,
            )
            node_doc = self._normalize_owned_node_mapping(
                node_instance_to_mapping(
                    node,
                    source_workspace_id=workspace.workspace_id,
                    data_types=(
                        self._registry.data_types
                        if self._registry is not None
                        else None
                    ),
                    properties_override=prepared_properties,
                )
            )
            spec = self._registry.spec_or_none(node.type_id) if self._registry is not None else None
            if (
                spec is not None
                and str(spec.runtime_behavior or "").strip().lower() != "passive"
            ):
                node_doc.pop("visual_style", None)
            node_docs.append(node_doc)
        return node_docs

    def _workspace_edge_docs(self, workspace: WorkspaceData) -> list[dict[str, Any]]:
        return [
            edge_instance_to_mapping(edge)
            for edge in sorted(
                workspace.edges.values(),
                key=lambda item: (
                    item.target_node_id,
                    item.target_port_key,
                    item.input_order,
                    item.edge_id,
                ),
            )
        ]

    def _node_doc_is_unresolved(self, node_doc: Mapping[str, Any]) -> bool:
        node_id = str(node_doc.get("node_id", "")).strip()
        type_id = str(node_doc.get("type_id", "")).strip()
        if not node_id or not type_id or self._registry is None:
            return False
        return self._registry.spec_or_none(type_id) is None

    def _decode_workspace_node_doc(
        self,
        workspace: WorkspaceData,
        *,
        node_doc: Mapping[str, Any],
    ) -> None:
        node_id = str(node_doc.get("node_id", "")).strip()
        type_id = str(node_doc.get("type_id", "")).strip()
        if not node_id or not type_id:
            return
        if node_id in workspace.nodes:
            return
        sanitized_node_doc = self._copy_node_mapping(node_doc)
        surface_title_property = None
        if self._registry is not None:
            spec = self._registry.spec_or_none(type_id)
            if spec is None:
                return
            if str(spec.surface_family or "").strip() in {
                "flowchart",
                "planning",
                "annotation",
                "group_backdrop",
            }:
                surface_title_property = next(
                    (prop for prop in spec.properties if prop.key == "title"), None
                )
            if surface_title_property is None and not str(
                sanitized_node_doc.get("title", "")
            ).strip():
                sanitized_node_doc["title"] = spec.display_name
            if str(spec.runtime_behavior or "").strip().lower() != "passive":
                sanitized_node_doc.pop("visual_style", None)
            raw_properties = sanitized_node_doc.get("properties")
            if isinstance(raw_properties, Mapping):
                prepared_properties = self._prepare_project_properties(
                    node_type_id=type_id,
                    properties=raw_properties,
                )
                sanitized_node_doc["properties"] = serialize_runtime_value(
                    prepared_properties,
                    catalog=self._registry.data_types,
                )
        node = node_instance_from_mapping(
            sanitized_node_doc,
            source_workspace_id=workspace.workspace_id,
            data_types=(
                self._registry.data_types
                if self._registry is not None
                else None
            ),
        )
        if node is None:
            return
        if surface_title_property is not None:
            node.title = str(
                node.properties.get("title", surface_title_property.default)
            ).strip()
        workspace.nodes[node.node_id] = node

    def _decode_workspace_edge_doc(
        self,
        workspace: WorkspaceData,
        *,
        edge_doc: Mapping[str, Any],
        valid_node_ids: set[str],
    ) -> None:
        edge_id = str(edge_doc.get("edge_id", "")).strip()
        source_node_id = str(edge_doc.get("source_node_id", "")).strip()
        source_port_key = str(edge_doc.get("source_port_key", "")).strip()
        target_node_id = str(edge_doc.get("target_node_id", "")).strip()
        target_port_key = str(edge_doc.get("target_port_key", "")).strip()
        if not edge_id or not source_node_id or not target_node_id:
            return
        if edge_id in workspace.edges:
            return
        if source_node_id not in valid_node_ids or target_node_id not in valid_node_ids:
            return
        source_node = workspace.nodes.get(source_node_id)
        target_node = workspace.nodes.get(target_node_id)
        if source_node is not None and not source_node.exposed_ports.get(source_port_key, True):
            return
        if target_node is not None and not target_node.exposed_ports.get(target_port_key, True):
            return
        edge = edge_instance_from_mapping(edge_doc)
        if edge is None:
            return
        workspace.edges[edge.edge_id] = edge
