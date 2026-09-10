from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from ea_node_editor.help.help_bridge import HelpBridge
from ea_node_editor.ui.shell.context_bridges import ShellContextBridges
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.shell_inspector_bridge import ShellInspectorBridge
from ea_node_editor.ui_qml.shell_library_bridge import ShellLibraryBridge
from ea_node_editor.ui_qml.shell_workspace_bridge import ShellWorkspaceBridge

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.composition.controllers import ShellControllerDependencies
    from ea_node_editor.ui.shell.composition.library_workspace import (
        ShellLibraryWorkspaceDependencies,
    )
    from ea_node_editor.ui.shell.composition.preferences import (
        ShellPreferencesThemeStatusDependencies,
    )
    from ea_node_editor.ui.shell.composition.presenters import ShellPresenterDependencies
    from ea_node_editor.ui.shell.composition.primitives import ShellPrimitiveDependencies
    from ea_node_editor.ui.shell.composition.runtime_services import ShellRuntimeDependencies
    from ea_node_editor.ui.shell.composition.state import ShellStateDependencies
    from ea_node_editor.ui.shell.controllers import AddonManagerController
    from ea_node_editor.ui.shell.window import ShellWindow


class AddonManagerBridge(QObject):
    state_changed = pyqtSignal(name="stateChanged")

    def __init__(
        self,
        host: "ShellWindow",
        *,
        controller: "AddonManagerController",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent or host)
        self._host = host
        self._controller = controller
        host.addon_manager_request_changed.connect(self.state_changed.emit)

    @pyqtProperty(bool, notify=state_changed)
    def open(self) -> bool:
        return self._controller.open

    @pyqtProperty(str, notify=state_changed)
    def focusAddonId(self) -> str:
        return self._controller.focus_addon_id

    @pyqtProperty(int, notify=state_changed)
    def requestSerial(self) -> int:
        return self._controller.request_serial

    @pyqtProperty("QVariantMap", notify=state_changed)
    def request(self) -> dict[str, object]:
        return self._controller.snapshot()

    @pyqtSlot()
    def requestClose(self) -> None:
        self._controller.request_close()

    @pyqtSlot(str)
    def requestOpen(self, focus_addon_id: str = "") -> None:
        self._controller.request_open(focus_addon_id)


@dataclass(frozen=True, slots=True)
class ShellContextBridgeDependencies:
    shell_context_bridges: ShellContextBridges
    shell_library_bridge: ShellLibraryBridge
    shell_workspace_bridge: ShellWorkspaceBridge
    shell_inspector_bridge: ShellInspectorBridge
    addon_manager_bridge: AddonManagerBridge
    graph_canvas_state_bridge: GraphCanvasStateBridge
    graph_canvas_command_bridge: GraphCanvasCommandBridge
    help_bridge: HelpBridge

    def attach(self, host: "ShellWindow") -> None:
        host.shell_library_bridge = self.shell_library_bridge
        host.shell_workspace_bridge = self.shell_workspace_bridge
        host.shell_inspector_bridge = self.shell_inspector_bridge
        host.addon_manager_bridge = self.addon_manager_bridge
        host.graph_canvas_state_bridge = self.graph_canvas_state_bridge
        host.graph_canvas_command_bridge = self.graph_canvas_command_bridge
        host.help_bridge = self.help_bridge


def create_context_bridge_dependencies(
    host: "ShellWindow",
    state: "ShellStateDependencies",
    primitives: "ShellPrimitiveDependencies",
    preferences: "ShellPreferencesThemeStatusDependencies",
    library_workspace: "ShellLibraryWorkspaceDependencies",
    controllers: "ShellControllerDependencies",
    presenters: "ShellPresenterDependencies",
    runtime: "ShellRuntimeDependencies",
) -> ShellContextBridgeDependencies:
    graph_canvas_state_bridge = GraphCanvasStateBridge(
        host,
        session_state=state.search_scope_state,
        snap_to_grid_changed_signal=host.snap_to_grid_changed,
        snap_grid_size=host._SNAP_GRID_SIZE,
        app_preferences_source=preferences.app_preferences_controller,
        graphics_source=presenters.shell_workspace_presenter,
        execution_source=host,
        project_source=host,
        scene_bridge=primitives.scene,
        view_bridge=primitives.view,
    )
    graph_canvas_command_bridge = GraphCanvasCommandBridge(
        host,
        search_scope_controller=controllers.search_scope_controller,
        app_preferences_source=preferences.app_preferences_controller,
        graphics_preferences_changed_signal=host.graphics_preferences_changed,
        run_controller=controllers.run_controller,
        show_graph_hint=host.show_graph_hint,
        inspector_source=presenters.shell_inspector_presenter,
        library_source=presenters.shell_library_presenter,
        workspace_edit_controller=library_workspace.workspace_edit_controller,
        canvas_import_controller=library_workspace.canvas_import_controller,
        workspace_drop_connect_controller=(
            library_workspace.workspace_drop_connect_controller
        ),
        media_action_source=runtime.media_panel_action_service,
        graphics_source=presenters.shell_workspace_presenter,
        host_source=presenters.graph_canvas_host_presenter,
        scene_bridge=primitives.scene,
        view_bridge=primitives.view,
        model_provider=lambda: host.model,
        active_workspace_id_provider=lambda: str(
            host.workspace_manager.active_workspace_id() or ""
        ),
        workspace_navigation_controller=library_workspace.workspace_navigation_controller,
    )
    primitives.scene.bind_graphics_preferences_source(
        presenters.shell_workspace_presenter
    )
    shell_context_bridges = ShellContextBridges(
        shell_library_bridge=ShellLibraryBridge(
            host,
            library_source=presenters.shell_library_presenter,
        ),
        shell_workspace_bridge=ShellWorkspaceBridge(
            host,
            shell_window=host,
            workspace_source=presenters.shell_workspace_presenter,
            scene_bridge=primitives.scene,
            view_bridge=primitives.view,
            console_bridge=primitives.console_panel,
            workspace_tabs_bridge=primitives.workspace_tabs,
        ),
        shell_inspector_bridge=ShellInspectorBridge(
            host,
            inspector_source=presenters.shell_inspector_presenter,
            scene_bridge=primitives.scene,
        ),
        graph_canvas_state_bridge=graph_canvas_state_bridge,
        graph_canvas_command_bridge=graph_canvas_command_bridge,
    )
    help_bridge = HelpBridge(host, shell_window=host)
    addon_manager_bridge = AddonManagerBridge(
        host,
        controller=controllers.addon_manager_controller,
        parent=host,
    )
    return ShellContextBridgeDependencies(
        shell_context_bridges=shell_context_bridges,
        shell_library_bridge=shell_context_bridges.shell_library_bridge,
        shell_workspace_bridge=shell_context_bridges.shell_workspace_bridge,
        shell_inspector_bridge=shell_context_bridges.shell_inspector_bridge,
        addon_manager_bridge=addon_manager_bridge,
        graph_canvas_state_bridge=graph_canvas_state_bridge,
        graph_canvas_command_bridge=graph_canvas_command_bridge,
        help_bridge=help_bridge,
    )


__all__ = [
    "AddonManagerBridge",
    "ShellContextBridgeDependencies",
    "create_context_bridge_dependencies",
]
