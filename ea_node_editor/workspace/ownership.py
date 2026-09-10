from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ea_node_editor.graph.project_state import ProjectData


@dataclass(frozen=True, slots=True)
class WorkspaceOwnership:
    workspace_order: list[str]
    active_workspace_id: str


def resolve_workspace_ownership(
    workspaces: Mapping[str, Any] | Sequence[Any],
    *,
    order_sources: Sequence[Any] = (),
    active_workspace_id: Any = "",
) -> WorkspaceOwnership:
    known_workspace_ids = _known_workspace_ids(workspaces)
    known_workspace_set = set(known_workspace_ids)
    workspace_order: list[str] = []
    seen_ids: set[str] = set()

    for source in order_sources:
        for workspace_id in _workspace_order_candidates(source):
            if workspace_id not in known_workspace_set or workspace_id in seen_ids:
                continue
            seen_ids.add(workspace_id)
            workspace_order.append(workspace_id)

    for workspace_id in known_workspace_ids:
        if workspace_id in seen_ids:
            continue
        seen_ids.add(workspace_id)
        workspace_order.append(workspace_id)

    normalized_active_workspace_id = _normalize_workspace_id(active_workspace_id)
    if normalized_active_workspace_id not in known_workspace_set:
        normalized_active_workspace_id = workspace_order[0] if workspace_order else ""

    return WorkspaceOwnership(
        workspace_order=workspace_order,
        active_workspace_id=normalized_active_workspace_id,
    )


def sync_project_workspace_ownership(
    project: ProjectData,
    *,
    order_sources: Sequence[Any] = (),
) -> WorkspaceOwnership:
    metadata = project.metadata if isinstance(project.metadata, dict) else {}
    previous_order = list(project.workspaces)
    previous_active_workspace_id = project.active_workspace_id
    ownership = resolve_workspace_ownership(
        project.workspaces,
        order_sources=order_sources,
        active_workspace_id=project.active_workspace_id,
    )
    ordered_workspaces = {
        workspace_id: project.workspaces[workspace_id]
        for workspace_id in ownership.workspace_order
        if workspace_id in project.workspaces
    }
    if list(ordered_workspaces) != previous_order:
        project.workspaces = ordered_workspaces
        project.bump_project_document_revision()
    updated_metadata = dict(metadata)
    updated_metadata["workspace_order"] = list(ownership.workspace_order)
    project.replace_metadata(updated_metadata)
    if previous_active_workspace_id != ownership.active_workspace_id:
        project.active_workspace_id = ownership.active_workspace_id
        project.bump_project_document_revision()
    return ownership


def _known_workspace_ids(workspaces: Mapping[str, Any] | Sequence[Any]) -> list[str]:
    if isinstance(workspaces, Mapping):
        return _workspace_order_candidates(workspaces.keys())
    return _workspace_order_candidates(workspaces)


def _workspace_order_candidates(source: Any) -> list[str]:
    if isinstance(source, Mapping):
        values = source.values()
    elif isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        values = source
    elif isinstance(source, Iterable) and not isinstance(source, (str, bytes, bytearray)):
        values = source
    else:
        return []

    candidates: list[str] = []
    seen_ids: set[str] = set()
    for value in values:
        workspace_id = _normalize_workspace_id(value)
        if not workspace_id or workspace_id in seen_ids:
            continue
        seen_ids.add(workspace_id)
        candidates.append(workspace_id)
    return candidates


def _normalize_workspace_id(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


__all__ = [
    "WorkspaceOwnership",
    "resolve_workspace_ownership",
    "sync_project_workspace_ownership",
]
