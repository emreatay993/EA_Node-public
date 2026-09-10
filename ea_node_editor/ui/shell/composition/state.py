from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ea_node_editor.settings import DEFAULT_GRAPHICS_SETTINGS
from ea_node_editor.ui.shell.presenters import build_default_shell_workspace_ui_state
from ea_node_editor.ui.shell.state import ShellState

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


@dataclass(frozen=True, slots=True)
class ShellStateDependencies:
    state: ShellState
    project_session_state: object
    library_filter_state: object
    run_state: object
    search_scope_state: object
    workspace_ui_state: object

    def attach(self, host: "ShellWindow") -> None:
        host.state = self.state
        host.project_session_state = self.project_session_state
        host.library_filter_state = self.library_filter_state
        host.run_state = self.run_state
        host.search_scope_state = self.search_scope_state
        host.workspace_ui_state = self.workspace_ui_state


def create_state_dependencies() -> ShellStateDependencies:
    state = ShellState()
    project_session_state = state.project_session
    library_filter_state = state.library_filters
    run_state = state.run
    search_scope_state = state.search_scope

    graphics_settings = DEFAULT_GRAPHICS_SETTINGS
    workspace_ui_state = build_default_shell_workspace_ui_state(graphics_settings)
    search_scope_state.graphics_minimap_expanded = bool(graphics_settings["canvas"]["minimap_expanded"])
    search_scope_state.snap_to_grid_enabled = bool(graphics_settings["interaction"]["snap_to_grid"])

    return ShellStateDependencies(
        state=state,
        project_session_state=project_session_state,
        library_filter_state=library_filter_state,
        run_state=run_state,
        search_scope_state=search_scope_state,
        workspace_ui_state=workspace_ui_state,
    )


__all__ = [
    "ShellStateDependencies",
    "create_state_dependencies",
]
