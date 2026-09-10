from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt

from ea_node_editor.execution.runtime import CorexRuntime
from ea_node_editor.persistence.solution_repository import SolutionRepositoryFactory
from ea_node_editor.ui.shell.controllers import (
    AddonManagerController,
    PluginAuthoringController,
    ProjectSessionController,
    RunController,
    RunEventController,
    RunProjectionController,
)
from ea_node_editor.ui.shell.window_search_scope_state import (
    WindowSearchScopeController,
)

if TYPE_CHECKING:
    from ea_node_editor.nodes.registry import NodeRegistry
    from ea_node_editor.ui.shell.composition.state import ShellStateDependencies
    from ea_node_editor.ui.shell.window import ShellWindow


@dataclass(frozen=True, slots=True)
class ShellControllerDependencies:
    search_scope_controller: WindowSearchScopeController
    addon_manager_controller: AddonManagerController
    plugin_authoring_controller: PluginAuthoringController
    project_session_controller: ProjectSessionController
    run_projection_controller: RunProjectionController
    run_controller: RunController
    run_event_controller: RunEventController
    execution_client: object

    def attach(self, host: "ShellWindow") -> None:
        host.search_scope_controller = self.search_scope_controller
        host.addon_manager_controller = self.addon_manager_controller
        host.plugin_authoring_controller = self.plugin_authoring_controller
        host.project_session_controller = self.project_session_controller
        host.run_projection_controller = self.run_projection_controller
        host.run_controller = self.run_controller
        host.run_event_controller = self.run_event_controller
        host.execution_client = self.execution_client


def _create_shell_execution_client(registry: "NodeRegistry") -> CorexRuntime:
    return CorexRuntime(
        registry=registry,
        solution_repository_factory=SolutionRepositoryFactory(),
    )


def create_controller_dependencies(
    host: "ShellWindow",
    state: "ShellStateDependencies",
    *,
    registry: "NodeRegistry",
) -> ShellControllerDependencies:
    search_scope_controller = WindowSearchScopeController(
        host, state.search_scope_state
    )
    addon_manager_controller = AddonManagerController(host)
    plugin_authoring_controller = PluginAuthoringController(host)
    project_session_controller = ProjectSessionController(host)
    run_projection_controller = RunProjectionController(host)
    run_controller = RunController(
        host,
        projection_controller=run_projection_controller,
    )
    run_event_controller = RunEventController(
        host,
        run_controller=run_controller,
        projection_controller=run_projection_controller,
    )
    execution_client = _create_shell_execution_client(registry)
    execution_client.subscribe(host.execution_event.emit)
    host.execution_event.connect(
        run_event_controller.handle_execution_event,
        Qt.ConnectionType.QueuedConnection,
    )
    return ShellControllerDependencies(
        search_scope_controller=search_scope_controller,
        addon_manager_controller=addon_manager_controller,
        plugin_authoring_controller=plugin_authoring_controller,
        project_session_controller=project_session_controller,
        run_projection_controller=run_projection_controller,
        run_controller=run_controller,
        run_event_controller=run_event_controller,
        execution_client=execution_client,
    )


__all__ = [
    "ShellControllerDependencies",
    "create_controller_dependencies",
]
