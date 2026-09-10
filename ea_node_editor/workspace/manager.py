from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.workspace.ownership import resolve_workspace_ownership


@dataclass(slots=True)
class WorkspaceRef:
    workspace_id: str
    name: str
    dirty: bool


class WorkspaceManager:
    def __init__(self, model: GraphModel) -> None:
        self._model = model

    def _project_metadata(self) -> dict[str, Any]:
        metadata = self._model.project.metadata
        if not isinstance(metadata, dict):
            self._model.project.replace_metadata({})
            metadata = self._model.project.metadata
        return metadata

    def _workspace_order(self) -> list[str]:
        ownership = resolve_workspace_ownership(
            self._model.project.workspaces,
            active_workspace_id=self._model.project.active_workspace_id,
        )
        return list(ownership.workspace_order)

    def _apply_workspace_order(self, workspace_order: list[str]) -> list[str]:
        project = self._model.project
        previous_order = list(project.workspaces)
        ownership = resolve_workspace_ownership(
            project.workspaces,
            order_sources=(workspace_order,),
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
        metadata = dict(self._project_metadata())
        metadata["workspace_order"] = list(ownership.workspace_order)
        project.replace_metadata(metadata)
        if project.active_workspace_id not in project.workspaces and ownership.active_workspace_id:
            self._model._set_active_workspace_id(ownership.active_workspace_id)
        return list(ownership.workspace_order)

    def list_workspaces(self) -> list[WorkspaceRef]:
        order = self._workspace_order()
        refs: list[WorkspaceRef] = []
        for workspace_id in order:
            workspace = self._model.project.workspaces[workspace_id]
            refs.append(
                WorkspaceRef(
                    workspace_id=workspace.workspace_id,
                    name=workspace.name,
                    dirty=workspace.dirty,
                )
            )
        return refs

    def create_workspace(self, name: str | None = None) -> str:
        order = self._workspace_order()
        workspace = self._model._create_workspace_record(name=name)
        order.append(workspace.workspace_id)
        self._apply_workspace_order(order)
        self._model._set_active_workspace_id(workspace.workspace_id)
        return workspace.workspace_id

    def rename_workspace(self, workspace_id: str, new_name: str) -> None:
        self._model._rename_workspace_record(workspace_id, new_name)

    def duplicate_workspace(self, workspace_id: str) -> str:
        source_order = self._workspace_order()
        duplicated = self._model._duplicate_workspace_record(workspace_id)
        order = [
            candidate_id
            for candidate_id in source_order
            if candidate_id in self._model.project.workspaces and candidate_id != duplicated.workspace_id
        ]
        try:
            source_index = order.index(workspace_id)
        except ValueError:
            source_index = len(order) - 1
        order.insert(source_index + 1, duplicated.workspace_id)
        self._apply_workspace_order(order)
        self._model._set_active_workspace_id(duplicated.workspace_id)
        return duplicated.workspace_id

    def close_workspace(self, workspace_id: str) -> None:
        order = self._workspace_order()
        if workspace_id not in self._model.project.workspaces:
            return
        was_active = self._model.project.active_workspace_id == workspace_id
        close_index = order.index(workspace_id) if workspace_id in order else -1
        self._model._close_workspace_record(workspace_id)
        order = [candidate_id for candidate_id in order if candidate_id in self._model.project.workspaces]
        self._apply_workspace_order(order)
        if was_active and order:
            next_index = min(max(close_index, 0), len(order) - 1)
            self._model._set_active_workspace_id(order[next_index])

    def set_active_workspace(self, workspace_id: str) -> None:
        self._model._set_active_workspace_id(workspace_id)

    def move_workspace(self, from_index: int, to_index: int) -> None:
        order = self._workspace_order()
        if len(order) < 2:
            return
        if from_index < 0 or from_index >= len(order):
            return
        to_index = max(0, min(to_index, len(order) - 1))
        if from_index == to_index:
            return
        workspace_id = order.pop(from_index)
        order.insert(to_index, workspace_id)
        self._apply_workspace_order(order)

    def active_workspace_id(self) -> str:
        order = self._workspace_order()
        if not order:
            workspace = self._model.project.ensure_default_workspace()
            order = self._apply_workspace_order([workspace.workspace_id])
        active_id = self._model.project.active_workspace_id
        if active_id in self._model.project.workspaces:
            return active_id
        fallback_id = order[0]
        self._model._set_active_workspace_id(fallback_id)
        return fallback_id
