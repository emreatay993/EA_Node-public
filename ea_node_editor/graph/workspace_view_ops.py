from __future__ import annotations

from dataclasses import dataclass

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.workspace_state import ViewState, WorkspaceData


@dataclass(slots=True)
class WorkspaceViewMutation:
    model: GraphModel
    workspace_id: str

    @property
    def workspace(self) -> WorkspaceData:
        return self.model.project.workspaces[self.workspace_id]

    def active_view_state(self) -> ViewState:
        return self.workspace.active_view_state()

    def save_active_view_state(self, *, zoom: float, pan_x: float, pan_y: float) -> bool:
        view_state = self.active_view_state()
        normalized_zoom = float(zoom)
        normalized_pan_x = float(pan_x)
        normalized_pan_y = float(pan_y)
        if (
            float(view_state.zoom) == normalized_zoom
            and float(view_state.pan_x) == normalized_pan_x
            and float(view_state.pan_y) == normalized_pan_y
        ):
            return False
        view_state.zoom = normalized_zoom
        view_state.pan_x = normalized_pan_x
        view_state.pan_y = normalized_pan_y
        self.workspace.bump_mutation_revision()
        return True

    def create_view(
        self,
        name: str | None = None,
        *,
        source_view_id: str | None = None,
    ) -> ViewState:
        return self.model._create_view_record(
            self.workspace_id,
            name=name,
            source_view_id=source_view_id,
        )

    def set_active_view(self, view_id: str) -> None:
        self.model._set_active_view_record(self.workspace_id, view_id)

    def close_view(self, view_id: str) -> None:
        self.model._close_view_record(self.workspace_id, view_id)

    def rename_view(self, view_id: str, new_name: str) -> None:
        self.model._rename_view_record(self.workspace_id, view_id, new_name)

    def move_view(self, from_index: int, to_index: int) -> None:
        self.model._move_view_record(self.workspace_id, from_index, to_index)


def workspace_view_mutations(model: GraphModel, workspace_id: str) -> WorkspaceViewMutation:
    normalized_workspace_id = str(workspace_id or "").strip()
    if normalized_workspace_id not in model.project.workspaces:
        raise KeyError(f"Unknown workspace: {normalized_workspace_id}")
    return WorkspaceViewMutation(model=model, workspace_id=normalized_workspace_id)


__all__ = ["WorkspaceViewMutation", "workspace_view_mutations"]
