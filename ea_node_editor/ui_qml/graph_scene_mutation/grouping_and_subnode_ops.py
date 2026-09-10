from __future__ import annotations

from typing import TYPE_CHECKING

from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.graph.transform_grouping_ops import group_selection_into_subnode, ungroup_subnode
from ea_node_editor.graph.transforms import plan_subnode_shell_pin_addition
from ea_node_editor.nodes.builtins.subnode import SUBNODE_PIN_LABEL_PROPERTY, is_subnode_shell_type
from ea_node_editor.ui.shell.runtime_history import (
    ACTION_GROUP_SELECTED_NODES,
    ACTION_UNGROUP_SELECTED_SUBNODE,
)

if TYPE_CHECKING:
    from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation


def add_subnode_shell_pin(self, shell_node_id: str, pin_type_id: str) -> str:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return ""
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return ""
    shell_node = workspace.nodes.get(str(shell_node_id).strip())
    if shell_node is None or not is_subnode_shell_type(shell_node.type_id):
        return ""
    plan = plan_subnode_shell_pin_addition(
        workspace=workspace,
        shell_node_id=shell_node_id,
        pin_type_id=pin_type_id,
    )
    if plan is None:
        return ""

    def _after_create(node: NodeInstance, mutations: ValidatedGraphMutation) -> None:
        mutations.set_exposed_port(shell_node.node_id, node.node_id, True)

    return self.create_node_from_type(
        type_id=plan.pin_type_id,
        x=plan.x,
        y=plan.y,
        parent_node_id=shell_node.node_id,
        select_node=False,
        property_overrides={SUBNODE_PIN_LABEL_PROPERTY: plan.label},
        after_create=_after_create,
    )


def group_selected_nodes(self) -> bool:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    selected_node_ids = self._selected_node_ids_in_workspace(workspace)
    if len(selected_node_ids) < 2:
        return False
    selection_bounds = self._scope_selection.bounds_for_node_ids(selected_node_ids)
    if selection_bounds is None:
        return False
    grouped = None
    history_group = self._scene_context.grouped_history_action(
        ACTION_GROUP_SELECTED_NODES,
        workspace,
        commit_if=lambda: grouped is not None,
    )
    with history_group:
        grouped = self._run_graph_operation(
            "group_selection_into_subnode",
            lambda: group_selection_into_subnode(
                model=model,
                registry=registry,
                workspace_id=workspace.workspace_id,
                selected_node_ids=selected_node_ids,
                scope_path=self._scene_context.scope_path,
                shell_x=selection_bounds.x(),
                shell_y=selection_bounds.y(),
            ),
        )
    if grouped is None:
        return False

    self._scope_selection.set_selected_node_ids([grouped.shell_node_id], workspace=workspace)
    self._scene_context.rebuild_models()
    return True


def ungroup_selected_subnode(self) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    selected_node_ids = self._selected_node_ids_in_workspace(workspace)
    if len(selected_node_ids) != 1:
        return False
    shell_node_id = selected_node_ids[0]

    ungrouped = None
    history_group = self._scene_context.grouped_history_action(
        ACTION_UNGROUP_SELECTED_SUBNODE,
        workspace,
        commit_if=lambda: ungrouped is not None,
    )
    with history_group:
        ungrouped = self._run_graph_operation(
            "ungroup_subnode",
            lambda: ungroup_subnode(
                model=model,
                workspace_id=workspace.workspace_id,
                shell_node_id=shell_node_id,
            ),
        )
    if ungrouped is None:
        return False

    self._scope_selection.set_selected_node_ids(list(ungrouped.moved_node_ids), workspace=workspace)
    self._scene_context.rebuild_models()
    return True


__all__ = ["add_subnode_shell_pin", "group_selected_nodes", "ungroup_selected_subnode"]
