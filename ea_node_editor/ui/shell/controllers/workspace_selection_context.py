# Purpose: Resolve the active workspace and selected node/spec for shell workspace owners.
# Map: feature_routes/graph_actions_and_context_menus.md
# Tests: tests/test_workspace_edit_controller.py
from __future__ import annotations

from typing import TYPE_CHECKING

from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.nodes.node_specs import NodeTypeSpec

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


class WorkspaceSelectionContext:
    def __init__(self, host: ShellWindow) -> None:
        self._host = host

    def selected_node_context(self) -> tuple[NodeInstance, NodeTypeSpec] | None:
        node_id = self._host.scene.selected_node_id()
        if not node_id:
            return None
        workspace = self.active_workspace()
        if workspace is None:
            return None
        node = workspace.nodes.get(node_id)
        if node is None:
            return None
        return node, self._host.registry.resolve_spec(node.type_id, node.properties)

    def active_workspace(self) -> WorkspaceData | None:
        workspace_id = str(
            getattr(self._host, "active_workspace_id", "")
            or self._host.workspace_manager.active_workspace_id()
        ).strip()
        return self._host.model.project.workspaces.get(workspace_id)


__all__ = ["WorkspaceSelectionContext"]
