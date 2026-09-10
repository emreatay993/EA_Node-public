from __future__ import annotations

from typing import Any

from ea_node_editor.graph.group_backdrop_mutation_ops import wrap_selection_in_group_backdrop
from ea_node_editor.ui.shell.runtime_history import ACTION_WRAP_GROUP


def wrap_nodes_in_group_backdrop(self, node_ids: list[Any]) -> str:
    model = self._scene_context.model
    if model is None:
        return ""
    registry = self._scene_context.registry
    if registry is None:
        return ""
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return ""

    wrapped = None
    history_group = self._scene_context.grouped_history_action(
        ACTION_WRAP_GROUP,
        workspace,
        commit_if=lambda: wrapped is not None,
    )
    with history_group:
        wrapped = self._run_graph_operation(
            "wrap_selection_in_group_backdrop",
            lambda: wrap_selection_in_group_backdrop(
                model=model,
                registry=registry,
                workspace_id=workspace.workspace_id,
                selected_node_ids=node_ids,
                scope_path=self._scene_context.scope_path,
                boundary_adapters=self._boundary_adapters,
            ),
        )
    if wrapped is None:
        return ""

    self._scope_selection.set_selected_node_ids([wrapped.backdrop_node_id], workspace=workspace)
    if not self._scene_context.publish_node_addition_delta(
        wrapped.backdrop_node_id,
        publication_path="group_backdrop_addition_delta",
    ):
        self._scene_context.rebuild_models()
    return wrapped.backdrop_node_id


def wrap_selected_nodes_in_group_backdrop(self) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    selected_node_ids = self._selected_node_ids_in_workspace(workspace)
    if not selected_node_ids:
        return False
    return bool(self.wrap_nodes_in_group_backdrop(selected_node_ids))


__all__ = ["wrap_nodes_in_group_backdrop", "wrap_selected_nodes_in_group_backdrop"]
