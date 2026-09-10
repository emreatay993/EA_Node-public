from __future__ import annotations

from typing import Any, Iterable

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.workspace.manager import WorkspaceManager


class ShellWorkspaceManagerAdapter:
    def __init__(self, manager: WorkspaceManager, model: GraphModel) -> None:
        self._manager = manager
        self._model = model

    def list_workspaces(self):
        return self._manager.list_workspaces()

    def create_workspace(self, name: str | None = None) -> str:
        return self._manager.create_workspace(name=name)

    def rename_workspace(self, workspace_id: str, new_name: str) -> None:
        self._manager.rename_workspace(workspace_id, new_name)

    def duplicate_workspace(self, workspace_id: str) -> str:
        return self._manager.duplicate_workspace(workspace_id)

    def close_workspace(self, workspace_id: str) -> None:
        self._manager.close_workspace(workspace_id)

    def set_active_workspace(self, workspace_id: str) -> None:
        self._manager.set_active_workspace(workspace_id)

    def move_workspace(self, from_index: int, to_index: int) -> None:
        self._manager.move_workspace(from_index, to_index)

    def active_workspace_id(self) -> str:
        return self._manager.active_workspace_id()

    def create_view(
        self,
        workspace_id: str,
        name: str | None = None,
        *,
        source_view_id: str | None = None,
    ) -> str:
        return self._model.create_view(
            workspace_id,
            name=name,
            source_view_id=source_view_id,
        ).view_id

    def set_active_view(self, workspace_id: str, view_id: str) -> None:
        self._model.set_active_view(workspace_id, view_id)

    def close_view(self, workspace_id: str, view_id: str) -> None:
        self._model.close_view(workspace_id, view_id)

    def rename_view(self, workspace_id: str, view_id: str, new_name: str) -> None:
        self._model.rename_view(workspace_id, view_id, new_name)

    def move_view(self, workspace_id: str, from_index: int, to_index: int) -> None:
        self._model.move_view(workspace_id, from_index, to_index)


def next_workspace_tab_index(count: int, current_index: int, offset: int) -> int | None:
    if count <= 0:
        return None
    if current_index < 0:
        current_index = 0
    return (current_index + offset) % count


def build_workspace_tab_items(workspace_refs: Iterable[Any]) -> list[dict[str, str]]:
    tabs: list[dict[str, str]] = []
    for workspace_ref in workspace_refs:
        workspace_id = str(getattr(workspace_ref, "workspace_id", "")).strip()
        if not workspace_id:
            continue
        name = str(getattr(workspace_ref, "name", "")).strip() or "Workspace"
        dirty = bool(getattr(workspace_ref, "dirty", False))
        tabs.append(
            {
                "workspace_id": workspace_id,
                "label": f"{name}{' *' if dirty else ''}",
            }
        )
    return tabs
