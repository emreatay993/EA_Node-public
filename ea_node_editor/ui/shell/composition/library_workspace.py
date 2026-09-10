from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from ea_node_editor.ui.shell.controllers.mutation_ui_effects import MutationUiEffects
from ea_node_editor.ui.shell.controllers.canvas_import_controller import CanvasImportController
from ea_node_editor.ui.shell.controllers.workflow_library_controller import (
    WorkflowLibraryController,
)
from ea_node_editor.ui.shell.controllers.workspace_drop_connect_controller import (
    WorkspaceDropConnectController,
)
from ea_node_editor.ui.shell.controllers.workspace_edit_controller import (
    WorkspaceEditController,
)
from ea_node_editor.ui.shell.controllers.workspace_navigation_controller import (
    WorkspaceNavigationController,
)
from ea_node_editor.ui.shell.controllers.workspace_package_io_controller import (
    WorkspacePackageIOController,
)
from ea_node_editor.ui.shell.controllers.workspace_selection_context import (
    WorkspaceSelectionContext,
)
from ea_node_editor.ui.shell.library_flow import pick_connection_candidate

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


@dataclass(frozen=True, slots=True)
class ShellLibraryWorkspaceDependencies:
    workspace_selection_context: WorkspaceSelectionContext
    workflow_library_controller: WorkflowLibraryController
    workspace_navigation_controller: WorkspaceNavigationController
    mutation_ui_effects: MutationUiEffects
    workspace_edit_controller: WorkspaceEditController
    canvas_import_controller: CanvasImportController
    workspace_drop_connect_controller: WorkspaceDropConnectController
    workspace_package_io_controller: WorkspacePackageIOController

    def attach(self, host: "ShellWindow") -> None:
        host.workspace_selection_context = self.workspace_selection_context
        host.workflow_library_controller = self.workflow_library_controller
        host.workspace_navigation_controller = self.workspace_navigation_controller
        host.workspace_edit_controller = self.workspace_edit_controller
        host.canvas_import_controller = self.canvas_import_controller
        host.workspace_drop_connect_controller = self.workspace_drop_connect_controller
        host.workspace_package_io_controller = self.workspace_package_io_controller


def create_library_workspace_dependencies(
    host: "ShellWindow",
) -> ShellLibraryWorkspaceDependencies:
    selection_context = WorkspaceSelectionContext(host)
    workflow_controller = WorkflowLibraryController(host, selection_context)
    navigation_controller = WorkspaceNavigationController(host)
    effects = MutationUiEffects(
        host=host,
        refresh_workspace_tabs=lambda: navigation_controller.refresh_workspace_tabs(),
    )
    edit_controller = WorkspaceEditController(
        host,
        selection_context=selection_context,
        effects=effects,
    )
    drop_connect_controller = WorkspaceDropConnectController(
        host,
        active_workspace=selection_context.active_workspace,
        resolve_custom_workflow_definition=(
            workflow_controller.resolve_custom_workflow_definition
        ),
        prompt_connection_candidate=partial(
            pick_connection_candidate,
            parent=host,
        ),
        effects=effects,
    )
    package_io_controller = WorkspacePackageIOController(
        host,
        workflow_controller.custom_workflow_definitions,
        workflow_controller.set_custom_workflow_definitions,
    )
    return ShellLibraryWorkspaceDependencies(
        workspace_selection_context=selection_context,
        workflow_library_controller=workflow_controller,
        workspace_navigation_controller=navigation_controller,
        mutation_ui_effects=effects,
        workspace_edit_controller=edit_controller,
        canvas_import_controller=CanvasImportController(host, effects=effects),
        workspace_drop_connect_controller=drop_connect_controller,
        workspace_package_io_controller=package_io_controller,
    )


__all__ = [
    "ShellLibraryWorkspaceDependencies",
    "create_library_workspace_dependencies",
]
