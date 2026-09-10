from __future__ import annotations

from ea_node_editor.ui.shell.controllers.app_preferences_controller import normalize_graph_theme_settings

from .addon_manager_presenter import AddOnManagerPresenter
from .canvas_export_presenter import CanvasExportPresenter
from .graph_canvas_host_presenter import GraphCanvasHostPresenter
from .inspector_presenter import ShellInspectorPresenter
from .library_presenter import ShellLibraryPresenter
from .project_review_deck_presenter import ProjectReviewDeckPresenter
from .state import ShellWorkspaceUiState, build_default_shell_workspace_ui_state
from .workspace_presenter import ShellWorkspacePresenter

__all__ = [
    "AddOnManagerPresenter",
    "CanvasExportPresenter",
    "GraphCanvasHostPresenter",
    "ProjectReviewDeckPresenter",
    "ShellInspectorPresenter",
    "ShellLibraryPresenter",
    "ShellWorkspacePresenter",
    "ShellWorkspaceUiState",
    "build_default_shell_workspace_ui_state",
    "normalize_graph_theme_settings",
]
