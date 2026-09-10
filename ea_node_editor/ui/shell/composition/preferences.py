from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ea_node_editor.telemetry.frame_rate import FrameRateSampler
from ea_node_editor.telemetry.startup_profile import phase
from ea_node_editor.ui.graph_theme import default_graph_theme_id_for_shell_theme
from ea_node_editor.ui.shell.controllers import AppPreferencesController
from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
from ea_node_editor.ui_qml.status_model import StatusItemModel
from ea_node_editor.ui_qml.theme_bridge import ThemeBridge

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.composition.primitives import ShellPrimitiveDependencies
    from ea_node_editor.ui.shell.composition.state import ShellStateDependencies
    from ea_node_editor.ui.shell.window import ShellWindow


@dataclass(frozen=True, slots=True)
class ShellPreferencesThemeStatusDependencies:
    app_preferences_controller: AppPreferencesController
    status_engine: StatusItemModel
    status_jobs: StatusItemModel
    status_metrics: StatusItemModel
    status_notifications: StatusItemModel
    _frame_rate_sampler: FrameRateSampler
    theme_bridge: ThemeBridge
    graph_theme_bridge: GraphThemeBridge

    def attach(self, host: "ShellWindow") -> None:
        host.app_preferences_controller = self.app_preferences_controller
        host.status_engine = self.status_engine
        host.status_jobs = self.status_jobs
        host.status_metrics = self.status_metrics
        host.status_notifications = self.status_notifications
        host._frame_rate_sampler = self._frame_rate_sampler
        host.theme_bridge = self.theme_bridge
        host.graph_theme_bridge = self.graph_theme_bridge


def create_preferences_theme_status_dependencies(
    host: "ShellWindow",
    state: "ShellStateDependencies",
    primitives: "ShellPrimitiveDependencies",
    *,
    preferences_document: Any = None,
) -> ShellPreferencesThemeStatusDependencies:
    with phase("prefs.AppPreferencesController"):
        app_preferences_controller = AppPreferencesController(preloaded_document=preferences_document)
    with phase("prefs.StatusItemModels"):
        status_engine = StatusItemModel("E", "Ready", host)
        status_jobs = StatusItemModel("J", "R:0 Q:0 D:0 F:0", host)
        status_metrics = StatusItemModel("M", "FPS:0 CPU:0% RAM:0/0 GB Disk R:0.0 W:0.0 MB/s", host)
        status_notifications = StatusItemModel("N", "W:0 E:0", host)
        status_engine.action_requested.connect(host.request_focus_status_execution_node)
        status_jobs.action_requested.connect(host.request_focus_status_execution_node)
        status_notifications.action_requested.connect(host.request_focus_status_execution_node)
    with phase("prefs.FrameRateSampler"):
        frame_rate_sampler = FrameRateSampler()
    with phase("prefs.ThemeBridge"):
        theme_bridge = ThemeBridge(host, theme_id=state.workspace_ui_state.active_theme_id)
    with phase("prefs.GraphThemeBridge"):
        graph_theme_bridge = GraphThemeBridge(
            host,
            theme_id=default_graph_theme_id_for_shell_theme(state.workspace_ui_state.active_theme_id),
        )
        primitives.scene.bind_graph_theme_bridge(graph_theme_bridge)
    return ShellPreferencesThemeStatusDependencies(
        app_preferences_controller=app_preferences_controller,
        status_engine=status_engine,
        status_jobs=status_jobs,
        status_metrics=status_metrics,
        status_notifications=status_notifications,
        _frame_rate_sampler=frame_rate_sampler,
        theme_bridge=theme_bridge,
        graph_theme_bridge=graph_theme_bridge,
    )


__all__ = [
    "ShellPreferencesThemeStatusDependencies",
    "create_preferences_theme_status_dependencies",
]
