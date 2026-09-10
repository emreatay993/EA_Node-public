from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ea_node_editor.ui.shell.host_presenter import ShellHostPresenter
from ea_node_editor.ui.shell.presenters import (
    CanvasExportPresenter,
    GraphCanvasHostPresenter,
    ProjectReviewDeckPresenter,
    ShellInspectorPresenter,
    ShellLibraryPresenter,
    ShellWorkspacePresenter,
)

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.composition.state import ShellStateDependencies
    from ea_node_editor.ui.shell.window import ShellWindow


@dataclass(frozen=True, slots=True)
class ShellPresenterDependencies:
    shell_host_presenter: ShellHostPresenter
    shell_library_presenter: ShellLibraryPresenter
    shell_workspace_presenter: ShellWorkspacePresenter
    shell_inspector_presenter: ShellInspectorPresenter
    canvas_export_presenter: CanvasExportPresenter
    graph_canvas_host_presenter: GraphCanvasHostPresenter
    project_review_deck_presenter: ProjectReviewDeckPresenter

    def attach(self, host: "ShellWindow") -> None:
        host.shell_host_presenter = self.shell_host_presenter
        host.shell_library_presenter = self.shell_library_presenter
        host.shell_workspace_presenter = self.shell_workspace_presenter
        host.shell_inspector_presenter = self.shell_inspector_presenter
        host.canvas_export_presenter = self.canvas_export_presenter
        host.graph_canvas_host_presenter = self.graph_canvas_host_presenter
        host.project_review_deck_presenter = self.project_review_deck_presenter


def create_presenter_dependencies(
    host: "ShellWindow",
    state: "ShellStateDependencies",
) -> ShellPresenterDependencies:
    shell_host_presenter = ShellHostPresenter(host)
    shell_library_presenter = ShellLibraryPresenter(host, parent=host)
    shell_workspace_presenter = ShellWorkspacePresenter(
        host,
        parent=host,
        ui_state=state.workspace_ui_state,
    )
    shell_inspector_presenter = ShellInspectorPresenter(host, parent=host)
    canvas_export_presenter = CanvasExportPresenter(
        host,
        workspace_presenter=shell_workspace_presenter,
    )
    graph_canvas_host_presenter = GraphCanvasHostPresenter(host, parent=host)
    project_review_deck_presenter = ProjectReviewDeckPresenter(host, parent=host)
    return ShellPresenterDependencies(
        shell_host_presenter=shell_host_presenter,
        shell_library_presenter=shell_library_presenter,
        shell_workspace_presenter=shell_workspace_presenter,
        shell_inspector_presenter=shell_inspector_presenter,
        canvas_export_presenter=canvas_export_presenter,
        graph_canvas_host_presenter=graph_canvas_host_presenter,
        project_review_deck_presenter=project_review_deck_presenter,
    )


__all__ = [
    "ShellPresenterDependencies",
    "create_presenter_dependencies",
]
