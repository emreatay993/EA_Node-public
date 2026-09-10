"""Execution-owned runtime snapshot assembly boundary.

The snapshot wire shape is passive. Project normalization, runtime snapshot
assembly, and artifact-store context setup remain execution concerns rather
than runtime-contract concerns.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

from ea_node_editor.execution.runtime_snapshot_assembly import RuntimeSnapshotAssembly
from ea_node_editor.execution.runtime_dto import RuntimeWorkspace
from ea_node_editor.runtime_contracts import (
    deserialize_runtime_value,
    serialize_runtime_value,
)
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.settings import PROJECT_ARTIFACT_STORE_METADATA_KEY

if TYPE_CHECKING:
    from ea_node_editor.graph.project_state import ProjectData
    from ea_node_editor.nodes.registry import NodeRegistry
    from ea_node_editor.runtime_contracts import DataTypeCatalog


def _snapshot_string_field(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    default: str = "",
    strip: bool = True,
) -> str:
    if field_name not in payload:
        return default
    value = payload[field_name]
    if not isinstance(value, str):
        raise ValueError(f"runtime_snapshot.{field_name} must be a string.")
    return value.strip() if strip else value


def _snapshot_nonnegative_int_field(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    default: int = 0,
) -> int:
    if field_name not in payload:
        return default
    value = payload[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"runtime_snapshot.{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"runtime_snapshot.{field_name} must be non-negative.")
    return value


def _snapshot_mapping_field(
    payload: Mapping[str, Any],
    field_name: str,
) -> dict[str, Any]:
    if field_name not in payload:
        return {}
    value = payload[field_name]
    if not isinstance(value, Mapping):
        raise ValueError(f"runtime_snapshot.{field_name} must be a mapping.")
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"runtime_snapshot.{field_name} keys must be strings.")
        normalized[key] = copy.deepcopy(item)
    return normalized


@dataclass(slots=True, frozen=True)
class RuntimeSnapshot:
    schema_version: int = 0
    project_id: str = ""
    name: str = ""
    active_workspace_id: str = ""
    workspace_order: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    workspaces: tuple[RuntimeWorkspace, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        catalog: "DataTypeCatalog | None" = None,
    ) -> RuntimeSnapshot:
        normalized_payload = deserialize_runtime_value(dict(payload), catalog=catalog)
        if not isinstance(normalized_payload, Mapping):
            raise ValueError("runtime_snapshot must be a mapping.")
        raw_workspaces = normalized_payload.get("workspaces")
        if not isinstance(raw_workspaces, (list, tuple)):
            raise ValueError("runtime_snapshot.workspaces must be a list.")
        workspaces = tuple(
            RuntimeWorkspace.from_mapping(workspace_doc)
            for workspace_doc in raw_workspaces
            if _require_workspace_mapping(workspace_doc)
        )
        raw_workspace_order = normalized_payload.get("workspace_order")
        if not isinstance(raw_workspace_order, (list, tuple)):
            raise ValueError("runtime_snapshot.workspace_order must be a list.")
        workspace_order_list: list[str] = []
        for index, item in enumerate(raw_workspace_order):
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    "runtime_snapshot.workspace_order entries must be non-empty "
                    f"strings; invalid entry at index {index}."
                )
            workspace_order_list.append(item.strip())
        workspace_order = tuple(workspace_order_list)
        workspace_ids = {
            workspace.workspace_id for workspace in workspaces if workspace.workspace_id
        }
        missing_workspace_ids = [
            workspace_id
            for workspace_id in workspace_order
            if workspace_id not in workspace_ids
        ]
        if missing_workspace_ids:
            raise ValueError(
                "runtime_snapshot.workspace_order references unknown workspaces: "
                + ", ".join(missing_workspace_ids)
            )
        return cls(
            schema_version=_snapshot_nonnegative_int_field(
                normalized_payload,
                "schema_version",
            ),
            project_id=_snapshot_string_field(normalized_payload, "project_id"),
            name=_snapshot_string_field(
                normalized_payload,
                "name",
                strip=False,
            ),
            active_workspace_id=_snapshot_string_field(
                normalized_payload,
                "active_workspace_id",
            ),
            workspace_order=workspace_order,
            metadata=_snapshot_mapping_field(normalized_payload, "metadata"),
            workspaces=workspaces,
        )

    @classmethod
    def from_project_data(cls, project: "ProjectData") -> RuntimeSnapshot:
        assembly = RuntimeSnapshotAssembly.from_project_data(project)

        return cls(
            schema_version=assembly.schema_version,
            project_id=project.project_id,
            name=project.name,
            active_workspace_id=assembly.active_workspace_id,
            workspace_order=assembly.workspace_order,
            metadata=assembly.metadata,
            workspaces=assembly.workspaces,
        )

    def workspace(self, workspace_id: str = "") -> RuntimeWorkspace:
        target_workspace_id = str(workspace_id or self.active_workspace_id).strip()
        for workspace in self.workspaces:
            if workspace.workspace_id == target_workspace_id:
                return workspace
        raise KeyError(
            f"Workspace not found in runtime snapshot: {target_workspace_id}"
        )

    def to_document(
        self,
        *,
        catalog: "DataTypeCatalog | None" = None,
    ) -> dict[str, Any]:
        workspaces_by_id = {
            workspace.workspace_id: workspace.to_document()
            for workspace in self.workspaces
            if workspace.workspace_id
        }
        ordered_workspace_ids: list[str] = [
            workspace_id
            for workspace_id in self.workspace_order
            if workspace_id in workspaces_by_id
        ]
        ordered_workspace_ids.extend(
            workspace.workspace_id
            for workspace in self.workspaces
            if workspace.workspace_id
            and workspace.workspace_id not in ordered_workspace_ids
        )
        payload = {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "name": self.name,
            "active_workspace_id": self.active_workspace_id,
            "workspace_order": ordered_workspace_ids,
            "workspaces": [
                copy.deepcopy(workspaces_by_id[workspace_id])
                for workspace_id in ordered_workspace_ids
            ],
            "metadata": copy.deepcopy(self.metadata),
        }
        serialized = serialize_runtime_value(payload, catalog=catalog)
        document = dict(serialized) if isinstance(serialized, Mapping) else payload
        RuntimeSnapshot.from_mapping(document, catalog=catalog)
        return document


@dataclass(slots=True)
class RuntimeSnapshotContext:
    runtime_snapshot: RuntimeSnapshot | None = None
    project_path: str = ""
    artifact_store: ProjectArtifactStore | None = None

    def __post_init__(self) -> None:
        if self.artifact_store is None:
            self.artifact_store = ProjectArtifactStore.from_project_metadata(
                project_path=self.project_path or None,
                project_metadata=(
                    self.runtime_snapshot.metadata
                    if self.runtime_snapshot is not None
                    else None
                ),
            )

    @classmethod
    def from_snapshot(
        cls,
        runtime_snapshot: RuntimeSnapshot | None,
        *,
        project_path: str = "",
        artifact_store: ProjectArtifactStore | None = None,
    ) -> RuntimeSnapshotContext:
        return cls(
            runtime_snapshot=runtime_snapshot,
            project_path=str(project_path).strip(),
            artifact_store=artifact_store,
        )

    def project_metadata(self) -> dict[str, Any]:
        metadata = (
            copy.deepcopy(self.runtime_snapshot.metadata)
            if self.runtime_snapshot is not None
            else {}
        )
        artifact_store = self.artifact_store
        if artifact_store is None:
            metadata.pop(PROJECT_ARTIFACT_STORE_METADATA_KEY, None)
            return metadata
        metadata[PROJECT_ARTIFACT_STORE_METADATA_KEY] = artifact_store.metadata
        return metadata


def coerce_runtime_snapshot(
    value: RuntimeSnapshot | Mapping[str, Any] | None,
    *,
    catalog: "DataTypeCatalog | None" = None,
) -> RuntimeSnapshot | None:
    if isinstance(value, RuntimeSnapshot):
        return value
    if isinstance(value, Mapping):
        return RuntimeSnapshot.from_mapping(value, catalog=catalog)
    return None


def _require_workspace_mapping(value: Any) -> bool:
    if isinstance(value, Mapping):
        return True
    raise ValueError("runtime_snapshot.workspaces entries must be mappings.")


def build_runtime_snapshot(
    project: "ProjectData",
    *,
    workspace_id: str,
    registry: "NodeRegistry",
) -> RuntimeSnapshot:
    from ea_node_editor.graph.registry_normalization import (
        normalize_project_for_registry,
    )

    project_copy = copy.deepcopy(project)
    normalize_project_for_registry(project_copy, registry)
    snapshot = RuntimeSnapshot.from_project_data(project_copy)
    snapshot.workspace(workspace_id)
    return snapshot


__all__ = [
    "RuntimeSnapshot",
    "RuntimeSnapshotContext",
    "build_runtime_snapshot",
    "coerce_runtime_snapshot",
]
