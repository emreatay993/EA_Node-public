from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ea_node_editor.ui.shell.controllers.graph_action_controller import GraphActionController
from ea_node_editor.ui_qml.graph_action_bridge import GraphActionBridge

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.composition.bridges import ShellContextBridgeDependencies
    from ea_node_editor.ui.shell.composition.controllers import ShellControllerDependencies
    from ea_node_editor.ui.shell.composition.library_workspace import ShellLibraryWorkspaceDependencies
    from ea_node_editor.ui.shell.composition.presenters import ShellPresenterDependencies
    from ea_node_editor.ui.shell.composition.primitives import ShellPrimitiveDependencies
    from ea_node_editor.ui.shell.window import ShellWindow


@dataclass(frozen=True, slots=True)
class ShellGraphActionDependencies:
    graph_action_controller: GraphActionController
    graph_action_bridge: GraphActionBridge

    def attach(self, host: "ShellWindow") -> None:
        host.graph_action_controller = self.graph_action_controller
        host.graph_action_bridge = self.graph_action_bridge


def create_graph_action_dependencies(
    host: "ShellWindow",
    primitives: "ShellPrimitiveDependencies",
    library_workspace: "ShellLibraryWorkspaceDependencies",
    controllers: "ShellControllerDependencies",
    presenters: "ShellPresenterDependencies",
    context_bridges: "ShellContextBridgeDependencies",
) -> ShellGraphActionDependencies:
    graph_action_controller = GraphActionController(
        workspace_edit_controller=library_workspace.workspace_edit_controller,
        workflow_library_controller=library_workspace.workflow_library_controller,
        search_scope_controller=controllers.search_scope_controller,
        show_graph_hint=host.show_graph_hint,
        graph_canvas_host_presenter=presenters.graph_canvas_host_presenter,
        scene_bridge=primitives.scene,
        help_bridge=context_bridges.help_bridge,
        addon_manager_bridge=context_bridges.addon_manager_bridge,
        run_controller=controllers.run_controller,
    )
    return ShellGraphActionDependencies(
        graph_action_controller=graph_action_controller,
        graph_action_bridge=GraphActionBridge(host, controller=graph_action_controller),
    )


__all__ = [
    "ShellGraphActionDependencies",
    "create_graph_action_dependencies",
]
