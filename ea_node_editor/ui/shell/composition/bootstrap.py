from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from ea_node_editor.settings import AUTOSAVE_INTERVAL_MS
from ea_node_editor.telemetry.startup_profile import phase
from ea_node_editor.ui.app_icon import apply_window_icon
from ea_node_editor.ui.shell.composition.factory import build_shell_window_composition
from ea_node_editor.ui.shell.composition.services import ShellWindowComposition
from ea_node_editor.ui_qml.qml_host_factory import (
    QML_HOST_QQUICKWIDGET,
    ShellQmlHost,
    create_shell_qml_host,
)
from ea_node_editor.ui_qml.shell_context_bootstrap import bootstrap_shell_qml_context

if TYPE_CHECKING:
    from ea_node_editor.nodes.registry import NodeRegistry
    from ea_node_editor.ui.shell.window import ShellWindow


@dataclass(frozen=True, slots=True)
class ShellTimerDependencies:
    metrics_timer: QTimer
    graph_hint_timer: QTimer
    autosave_timer: QTimer

    def attach(self, host: "ShellWindow") -> None:
        host.metrics_timer = self.metrics_timer
        host.graph_hint_timer = self.graph_hint_timer
        host.autosave_timer = self.autosave_timer


class ShellWindowBootstrapCoordinator:
    def bootstrap(self, host: "ShellWindow", composition: ShellWindowComposition) -> None:
        with phase("coord.configure_host"):
            _configure_shell_window_host(host)
        with phase("coord.composition.attach"):
            composition.attach(host)
        with phase("coord.startup_sequence"):
            _run_shell_startup_sequence(host)
        with phase("coord.timer_deps"):
            self.create_timer_dependencies(host).attach(host)
        with phase("coord.finalize"):
            _finalize_shell_window_bootstrap(host)
        with phase("coord.evaluate_open_workspace"):
            _evaluate_open_workspace(host)

    def create_timer_dependencies(self, host: "ShellWindow") -> ShellTimerDependencies:
        return _create_shell_timer_dependencies(host)


def create_shell_window(
    registry: "NodeRegistry | None" = None,
    *,
    preferences_document: Any = None,
) -> "ShellWindow":
    """Build the shell window, optionally reusing a pre-built node registry.

    Pass ``registry`` to skip the blocking ``build_default_registry()`` call —
    the splash builds the registry on a worker thread and hands it in here.
    See ``PLANS_TO_IMPLEMENT/in_progress/splash_threaded_plugin_registry.md``.
    """
    from ea_node_editor.ui.shell.window import ShellWindow

    with phase("shell.ShellWindow()"):
        host = ShellWindow(_defer_bootstrap=True)
    with phase("shell.build_composition"):
        composition = build_shell_window_composition(
            host,
            registry=registry,
            preferences_document=preferences_document,
        )
    with phase("shell.bootstrap"):
        bootstrap_shell_window(host, composition)
    with phase("shell.connect_state_signal"):
        host._connect_application_state_signal()
    return host


def bootstrap_shell_window(host: "ShellWindow", composition: ShellWindowComposition) -> None:
    ShellWindowBootstrapCoordinator().bootstrap(host, composition)


def _configure_shell_window_host(host: "ShellWindow") -> None:
    host.setWindowTitle("COREX Node Editor")
    apply_window_icon(host)
    host.resize(1600, 900)


def _run_shell_startup_sequence(host: "ShellWindow") -> None:
    host._create_actions()
    host._build_menu_bar()
    host.app_preferences_controller.load_into_host(host)
    host._wire_signals()
    qml_host = _build_shell_qml_host(host)
    host.qml_host = qml_host
    host.quick_widget = qml_host.widget if qml_host.host_kind == QML_HOST_QQUICKWIDGET else qml_host
    host._restore_session()
    host._ensure_project_metadata_defaults()
    host.workspace_navigation_controller.refresh_workspace_tabs()
    host.workspace_navigation_controller.switch_workspace(
        host.workspace_manager.active_workspace_id()
    )
    host._restore_script_editor_state()


def _build_shell_qml_host(host: "ShellWindow") -> ShellQmlHost:
    from ea_node_editor.ui.shell.canvas_drop_capture import CanvasDropCapture
    from ea_node_editor.ui_qml.qml_host_factory import QML_HOST_QQUICKVIEW_CONTAINER

    qml_host = create_shell_qml_host(host)
    host.qml_host = qml_host
    drop_surface = (
        qml_host.quick_window()
        if qml_host.host_kind == QML_HOST_QQUICKVIEW_CONTAINER
        else qml_host.event_filter_widget
    )
    host.canvas_drop_capture = CanvasDropCapture(drop_surface, host.canvas_import_controller)
    qml_context = host.shell_services.qml_context
    host_bindings = qml_context.qml_host_bindings
    context_property_bindings = qml_context.qml_context_property_bindings
    bootstrap_shell_qml_context(host_bindings, qml_host, context_property_bindings)
    status = qml_host.status()
    if getattr(status, "name", "") == "Error":
        formatted_errors = "\n".join(error.toString() for error in qml_host.errors()).strip()
        message = formatted_errors or "Unknown QML load error."
        host.console_panel.append_log("error", f"Failed to load MainShell.qml.\n{message}")
        QMessageBox.critical(host, "UI Load Error", f"Could not load the main UI.\n\n{message}")
    host.setCentralWidget(qml_host.container_widget)
    return qml_host


def _create_shell_timer_dependencies(host: "ShellWindow") -> ShellTimerDependencies:
    metrics_timer = QTimer(host)
    metrics_timer.setInterval(1000)
    metrics_timer.timeout.connect(host._update_metrics)
    metrics_timer.start()

    graph_hint_timer = QTimer(host)
    graph_hint_timer.setSingleShot(True)
    graph_hint_timer.timeout.connect(host.clear_graph_hint)

    autosave_timer = QTimer(host)
    autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
    autosave_timer.timeout.connect(host._autosave_tick)
    autosave_timer.start()

    return ShellTimerDependencies(
        metrics_timer=metrics_timer,
        graph_hint_timer=graph_hint_timer,
        autosave_timer=autosave_timer,
    )


def _finalize_shell_window_bootstrap(host: "ShellWindow") -> None:
    host.run_projection_controller.set_run_ui_state(
        "ready",
        "Idle",
        0,
        0,
        0,
        0,
        clear_active_run=host.run_controller.clear_active_run,
    )
    host._update_metrics()


def _evaluate_open_workspace(host: "ShellWindow") -> None:
    workspace_id = str(host.workspace_manager.active_workspace_id() or "").strip()
    evaluate = getattr(host.run_controller, "evaluate_workspace_on_open", None)
    if workspace_id and callable(evaluate):
        evaluate(workspace_id)


__all__ = [
    "ShellTimerDependencies",
    "ShellWindowBootstrapCoordinator",
    "bootstrap_shell_window",
    "create_shell_window",
]
