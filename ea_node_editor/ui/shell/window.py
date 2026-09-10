from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QEvent, QTimer, Qt, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtQuickWidgets import QQuickWidget
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow

from ea_node_editor.nodes.builtins.subnode import (
    SUBNODE_INPUT_TYPE_ID,
    SUBNODE_OUTPUT_TYPE_ID,
)
from ea_node_editor.settings import (
    DEFAULT_GRAPHICS_SETTINGS,
    autosave_project_path,
    recent_session_path,
)
from ea_node_editor.ui.shell.window_state import (
    context_properties,
    library_and_overlay_state,
    project_session_actions,
    run_and_style_state,
    workspace_graph_actions,
)
from ea_node_editor.ui.shell.composition import (
    ShellWindowComposition,
    bootstrap_shell_window,
    build_shell_window_composition,
)
from ea_node_editor.ui.shell.tooltip_manager import TooltipManager
from ea_node_editor.ui_qml.embedded_viewer_overlay_manager import EmbeddedViewerOverlayManager
from ea_node_editor.ui_qml.qml_host_factory import QML_HOST_QQUICKWIDGET
from ea_node_editor.ui_qml.qtquick_backend import configure_qtquick_backend, qtquick_backend_diagnostics


configure_qtquick_backend()


class ShellWindow(
    QMainWindow,
    context_properties.ShellWindowContextPropertiesMixin,
    library_and_overlay_state.ShellWindowLibraryOverlayStateMixin,
    workspace_graph_actions.ShellWindowWorkspaceGraphActionsMixin,
    project_session_actions.ShellWindowProjectSessionActionsMixin,
    run_and_style_state.ShellWindowRunAndStyleStateMixin,
):
    execution_event = pyqtSignal(dict)
    node_library_changed = pyqtSignal()
    library_pane_reset_requested = pyqtSignal(name="libraryPaneResetRequested")
    workspace_state_changed = pyqtSignal()
    run_controls_changed = pyqtSignal()
    selected_node_changed = pyqtSignal()
    project_meta_changed = pyqtSignal()
    graph_search_changed = pyqtSignal()
    connection_quick_insert_changed = pyqtSignal()
    graph_hint_changed = pyqtSignal()
    run_failure_changed = pyqtSignal()
    node_execution_state_changed = pyqtSignal()
    snap_to_grid_changed = pyqtSignal()
    graphics_preferences_changed = pyqtSignal()
    addon_manager_request_changed = pyqtSignal(name="addonManagerRequestChanged")

    _RUN_SCOPED_EVENT_TYPES = {
        "run_started",
        "run_state",
        "run_completed",
        "run_failed",
        "run_stopped",
        "node_started",
        "node_settled",
        "trigger_capture_settled",
        "trigger_published",
        "log",
    }
    _GRAPH_SEARCH_LIMIT = 10
    _CONNECTION_QUICK_INSERT_LIMIT = 12
    _CONNECTION_QUICK_INSERT_OFFSET = 36.0
    _SNAP_GRID_SIZE = 20.0
    _SUBNODE_PIN_TYPE_IDS = {
        SUBNODE_INPUT_TYPE_ID,
        SUBNODE_OUTPUT_TYPE_ID,
    }

    project_display_name = pyqtProperty(
        str,
        fget=context_properties._qt_project_display_name,
        notify=project_meta_changed,
    )
    filtered_node_library_items = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_filtered_node_library_items,
        notify=node_library_changed,
    )
    grouped_node_library_items = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_grouped_node_library_items,
        notify=node_library_changed,
    )
    library_category_options = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_library_category_options,
        notify=node_library_changed,
    )
    library_direction_options = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_library_direction_options,
        notify=node_library_changed,
    )
    library_data_type_options = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_library_data_type_options,
        notify=node_library_changed,
    )
    pin_data_type_options = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_pin_data_type_options,
        notify=workspace_state_changed,
    )
    graph_search_open = pyqtProperty(
        bool,
        fget=context_properties._qt_graph_search_open,
        notify=graph_search_changed,
    )
    graph_search_query = pyqtProperty(
        str,
        fget=context_properties._qt_graph_search_query,
        notify=graph_search_changed,
    )
    graph_search_enabled_scopes = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_graph_search_enabled_scopes,
        notify=graph_search_changed,
    )
    graph_search_results = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_graph_search_results,
        notify=graph_search_changed,
    )
    graph_search_highlight_index = pyqtProperty(
        int,
        fget=context_properties._qt_graph_search_highlight_index,
        notify=graph_search_changed,
    )
    connection_quick_insert_open = pyqtProperty(
        bool,
        fget=context_properties._qt_connection_quick_insert_open,
        notify=connection_quick_insert_changed,
    )
    connection_quick_insert_query = pyqtProperty(
        str,
        fget=context_properties._qt_connection_quick_insert_query,
        notify=connection_quick_insert_changed,
    )
    connection_quick_insert_results = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_connection_quick_insert_results,
        notify=connection_quick_insert_changed,
    )
    connection_quick_insert_highlight_index = pyqtProperty(
        int,
        fget=context_properties._qt_connection_quick_insert_highlight_index,
        notify=connection_quick_insert_changed,
    )
    connection_quick_insert_overlay_x = pyqtProperty(
        float,
        fget=context_properties._qt_connection_quick_insert_overlay_x,
        notify=connection_quick_insert_changed,
    )
    connection_quick_insert_overlay_y = pyqtProperty(
        float,
        fget=context_properties._qt_connection_quick_insert_overlay_y,
        notify=connection_quick_insert_changed,
    )
    connection_quick_insert_source_summary = pyqtProperty(
        str,
        fget=context_properties._qt_connection_quick_insert_source_summary,
        notify=connection_quick_insert_changed,
    )
    connection_quick_insert_is_canvas_mode = pyqtProperty(
        bool,
        fget=context_properties._qt_connection_quick_insert_is_canvas_mode,
        notify=connection_quick_insert_changed,
    )
    graph_hint_message = pyqtProperty(
        str,
        fget=context_properties._qt_graph_hint_message,
        notify=graph_hint_changed,
    )
    graph_hint_visible = pyqtProperty(
        bool,
        fget=context_properties._qt_graph_hint_visible,
        notify=graph_hint_changed,
    )
    addon_manager_request = pyqtProperty(
        "QVariantMap",
        fget=context_properties._qt_addon_manager_request,
        notify=addon_manager_request_changed,
    )
    addon_manager_open = pyqtProperty(
        bool,
        fget=context_properties._qt_addon_manager_open,
        notify=addon_manager_request_changed,
    )
    addon_manager_focus_addon_id = pyqtProperty(
        str,
        fget=context_properties._qt_addon_manager_focus_addon_id,
        notify=addon_manager_request_changed,
    )
    addon_manager_request_serial = pyqtProperty(
        int,
        fget=context_properties._qt_addon_manager_request_serial,
        notify=addon_manager_request_changed,
    )
    graphics_show_grid = pyqtProperty(
        bool,
        fget=context_properties._qt_graphics_show_grid,
        notify=graphics_preferences_changed,
    )
    graphics_grid_style = pyqtProperty(
        str,
        fget=context_properties._qt_graphics_grid_style,
        notify=graphics_preferences_changed,
    )
    graphics_edge_crossing_style = pyqtProperty(
        str,
        fget=context_properties._qt_graphics_edge_crossing_style,
        notify=graphics_preferences_changed,
    )
    graphics_expand_collision_avoidance = pyqtProperty(
        "QVariantMap",
        fget=context_properties._qt_graphics_expand_collision_avoidance,
        notify=graphics_preferences_changed,
    )
    graphics_graph_label_pixel_size = pyqtProperty(
        int,
        fget=context_properties._qt_graphics_graph_label_pixel_size,
        notify=graphics_preferences_changed,
    )
    graphics_graph_node_icon_pixel_size_override = pyqtProperty(
        "QVariant",
        fget=context_properties._qt_graphics_graph_node_icon_pixel_size_override,
        notify=graphics_preferences_changed,
    )
    graphics_node_title_icon_pixel_size = pyqtProperty(
        int,
        fget=context_properties._qt_graphics_node_title_icon_pixel_size,
        notify=graphics_preferences_changed,
    )
    graphics_show_minimap = pyqtProperty(
        bool,
        fget=context_properties._qt_graphics_show_minimap,
        notify=graphics_preferences_changed,
    )
    graphics_show_canvas_options_button = pyqtProperty(
        bool,
        fget=context_properties._qt_graphics_show_canvas_options_button,
        notify=graphics_preferences_changed,
    )
    graphics_show_port_labels = pyqtProperty(
        bool,
        fget=context_properties._qt_graphics_show_port_labels,
        notify=graphics_preferences_changed,
    )
    graphics_notched_ports = pyqtProperty(
        bool,
        fget=context_properties._qt_graphics_notched_ports,
        notify=graphics_preferences_changed,
    )
    graphics_node_elapsed_time_unit = pyqtProperty(
        str,
        fget=context_properties._qt_graphics_node_elapsed_time_unit,
        notify=graphics_preferences_changed,
    )
    graphics_node_elapsed_time_visibility = pyqtProperty(
        str,
        fget=context_properties._qt_graphics_node_elapsed_time_visibility,
        notify=graphics_preferences_changed,
    )
    graphics_show_tooltips = pyqtProperty(
        bool,
        fget=context_properties._qt_graphics_show_tooltips,
        notify=graphics_preferences_changed,
    )
    graphics_tooltip_categories = pyqtProperty(
        "QVariantMap",
        fget=context_properties._qt_graphics_tooltip_categories,
        notify=graphics_preferences_changed,
    )
    graphics_tooltip_category_visibility = pyqtProperty(
        "QVariantMap",
        fget=context_properties._qt_graphics_tooltip_category_visibility,
        notify=graphics_preferences_changed,
    )
    graphics_minimap_expanded = pyqtProperty(
        bool,
        fget=context_properties._qt_graphics_minimap_expanded,
        notify=graphics_preferences_changed,
    )
    graphics_node_shadow = pyqtProperty(
        bool,
        fget=context_properties._qt_graphics_node_shadow,
        notify=graphics_preferences_changed,
    )
    graphics_shadow_strength = pyqtProperty(
        int,
        fget=context_properties._qt_graphics_shadow_strength,
        notify=graphics_preferences_changed,
    )
    graphics_shadow_softness = pyqtProperty(
        int,
        fget=context_properties._qt_graphics_shadow_softness,
        notify=graphics_preferences_changed,
    )
    graphics_shadow_offset = pyqtProperty(
        int,
        fget=context_properties._qt_graphics_shadow_offset,
        notify=graphics_preferences_changed,
    )
    graphics_status_bar_layout = pyqtProperty(
        str,
        fget=context_properties._qt_graphics_status_bar_layout,
        notify=graphics_preferences_changed,
    )
    graphics_show_fps_telemetry = pyqtProperty(
        bool,
        fget=context_properties._qt_graphics_show_fps_telemetry,
        notify=graphics_preferences_changed,
    )
    graphics_floating_toolbar_style = pyqtProperty(
        str,
        fget=context_properties._qt_graphics_floating_toolbar_style,
        notify=graphics_preferences_changed,
    )
    graphics_floating_toolbar_size = pyqtProperty(
        str,
        fget=context_properties._qt_graphics_floating_toolbar_size,
        notify=graphics_preferences_changed,
    )
    graphics_selection_toolbar_mode = pyqtProperty(
        str,
        fget=context_properties._qt_graphics_selection_toolbar_mode,
        notify=graphics_preferences_changed,
    )
    graphics_selection_toolbar_minimal_menu_trigger = pyqtProperty(
        str,
        fget=context_properties._qt_graphics_selection_toolbar_minimal_menu_trigger,
        notify=graphics_preferences_changed,
    )
    graphics_folder_explorer_column_widths = pyqtProperty(
        "QVariantMap",
        fget=context_properties._qt_graphics_folder_explorer_column_widths,
        notify=graphics_preferences_changed,
    )
    graphics_tab_strip_density = pyqtProperty(
        str,
        fget=context_properties._qt_graphics_tab_strip_density,
        notify=graphics_preferences_changed,
    )
    active_theme_id = pyqtProperty(
        str,
        fget=context_properties._qt_active_theme_id,
        notify=graphics_preferences_changed,
    )
    snap_to_grid_enabled = pyqtProperty(
        bool,
        fget=context_properties._qt_snap_to_grid_enabled,
        notify=snap_to_grid_changed,
    )
    snap_grid_size = pyqtProperty(float, fget=context_properties._qt_snap_grid_size, constant=True)
    active_workspace_id = pyqtProperty(
        str,
        fget=context_properties._qt_active_workspace_id,
        notify=workspace_state_changed,
    )
    active_workspace_name = pyqtProperty(
        str,
        fget=context_properties._qt_active_workspace_name,
        notify=workspace_state_changed,
    )
    active_view_name = pyqtProperty(
        str,
        fget=context_properties._qt_active_view_name,
        notify=workspace_state_changed,
    )
    active_view_items = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_active_view_items,
        notify=workspace_state_changed,
    )
    active_scope_breadcrumb_items = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_active_scope_breadcrumb_items,
        notify=workspace_state_changed,
    )
    selected_node_title = pyqtProperty(
        str,
        fget=context_properties._qt_selected_node_title,
        notify=selected_node_changed,
    )
    selected_node_subtitle = pyqtProperty(
        str,
        fget=context_properties._qt_selected_node_subtitle,
        notify=selected_node_changed,
    )
    selected_node_header_items = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_selected_node_header_items,
        notify=selected_node_changed,
    )
    selected_node_summary = pyqtProperty(
        str,
        fget=context_properties._qt_selected_node_summary,
        notify=selected_node_changed,
    )
    has_selected_node = pyqtProperty(
        bool,
        fget=context_properties._qt_has_selected_node,
        notify=selected_node_changed,
    )
    selected_node_collapsible = pyqtProperty(
        bool,
        fget=context_properties._qt_selected_node_collapsible,
        notify=selected_node_changed,
    )
    selected_node_collapsed = pyqtProperty(
        bool,
        fget=context_properties._qt_selected_node_collapsed,
        notify=selected_node_changed,
    )
    selected_node_is_subnode_pin = pyqtProperty(
        bool,
        fget=context_properties._qt_selected_node_is_subnode_pin,
        notify=selected_node_changed,
    )
    selected_node_is_subnode_shell = pyqtProperty(
        bool,
        fget=context_properties._qt_selected_node_is_subnode_shell,
        notify=selected_node_changed,
    )
    can_publish_custom_workflow_from_scope = pyqtProperty(
        bool,
        fget=context_properties._qt_can_publish_custom_workflow_from_scope,
        notify=workspace_state_changed,
    )
    selected_node_property_items = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_selected_node_property_items,
        notify=selected_node_changed,
    )
    selected_node_link_items = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_selected_node_link_items,
        notify=selected_node_changed,
    )
    selected_node_port_items = pyqtProperty(
        "QVariantList",
        fget=context_properties._qt_selected_node_port_items,
        notify=selected_node_changed,
    )

    def __init__(self, composition: ShellWindowComposition | None = None, *, _defer_bootstrap: bool = False) -> None:
        super().__init__()
        self._viewer_window_active = True
        self._viewer_deactivate_decision_queued = False
        self._application_state_signal_connected = False
        self._shell_teardown_started = False
        self.tooltip_manager = TooltipManager(
            tooltip_categories=DEFAULT_GRAPHICS_SETTINGS["shell"].get("tooltip_categories"),
        )
        if _defer_bootstrap:
            return
        resolved_composition = composition or build_shell_window_composition(self)
        bootstrap_shell_window(self, resolved_composition)
        self._connect_application_state_signal()

    def addon_manager_request_snapshot(self) -> dict[str, Any]:
        return self.addon_manager_controller.snapshot()

    @pyqtSlot(result="QVariantMap")
    def qtquick_backend_debug_payload(self) -> dict[str, Any]:
        qml_host = getattr(self, "qml_host", None)
        if qml_host is not None:
            quick_window = qml_host.quick_window()
            qml_host_kind = str(getattr(qml_host, "host_kind", ""))
            return qtquick_backend_diagnostics(
                quick_window,
                qml_host_kind=qml_host_kind,
                grab_window_readback_included=False,
            )
        quick_widget = getattr(self, "quick_widget", None)
        quick_window = quick_widget.quickWindow() if isinstance(quick_widget, QQuickWidget) else None
        return qtquick_backend_diagnostics(
            quick_window,
            qml_host_kind=QML_HOST_QQUICKWIDGET,
            grab_window_readback_included=False,
        )

    def request_open_addon_manager(self, focus_addon_id: str | None = None) -> None:
        self.addon_manager_controller.request_open(focus_addon_id)

    def request_close_addon_manager(self) -> None:
        self.addon_manager_controller.request_close()

    @property
    def embedded_viewer_overlay_manager(self) -> EmbeddedViewerOverlayManager | None:
        return self._ensure_embedded_viewer_overlay_manager()

    def _ensure_embedded_viewer_overlay_manager(
        self,
        quick_widget: Any | None = None,
    ) -> EmbeddedViewerOverlayManager | None:
        qml_host = getattr(self, "qml_host", None)
        resolved_quick_widget = quick_widget or getattr(qml_host, "widget", None) or getattr(qml_host, "view", None)
        if resolved_quick_widget is None:
            candidate = getattr(self, "quick_widget", None)
            resolved_quick_widget = candidate if isinstance(candidate, QQuickWidget) else None
        overlay_parent_widget = getattr(qml_host, "overlay_parent_widget", None)
        event_filter_widget = getattr(qml_host, "event_filter_widget", None)
        if resolved_quick_widget is None or overlay_parent_widget is None or event_filter_widget is None:
            return None

        manager = getattr(self, "_embedded_viewer_overlay_manager", None)
        if (
            manager is not None
            and manager.quick_widget is resolved_quick_widget
            and manager.overlay_parent_widget is overlay_parent_widget
        ):
            host_service = getattr(self, "viewer_host_service", None)
            if host_service is not None:
                host_service.set_overlay_manager(manager)
            plot_service = getattr(self, "plot_host_service", None)
            if plot_service is not None:
                plot_service.set_overlay_manager(manager)
            folder_service = getattr(self, "native_folder_explorer_host_service", None)
            if folder_service is not None:
                folder_service.set_overlay_manager(manager)
            return manager
        if manager is not None:
            host_service = getattr(self, "viewer_host_service", None)
            if host_service is not None:
                host_service.set_overlay_manager(None)
            plot_service = getattr(self, "plot_host_service", None)
            if plot_service is not None:
                plot_service.set_overlay_manager(None)
            folder_service = getattr(self, "native_folder_explorer_host_service", None)
            if folder_service is not None:
                folder_service.set_overlay_manager(None)
            manager.deleteLater()

        manager = EmbeddedViewerOverlayManager(
            overlay_parent_widget,
            quick_widget=resolved_quick_widget,
            overlay_parent_widget=overlay_parent_widget,
            event_filter_widget=event_filter_widget,
            shell_window=self,
            scene_bridge=self.scene,
            view_bridge=self.view,
        )
        self._embedded_viewer_overlay_manager = manager
        host_service = getattr(self, "viewer_host_service", None)
        if host_service is not None:
            host_service.set_overlay_manager(manager)
        plot_service = getattr(self, "plot_host_service", None)
        if plot_service is not None:
            plot_service.set_overlay_manager(manager)
        folder_service = getattr(self, "native_folder_explorer_host_service", None)
        if folder_service is not None:
            folder_service.set_overlay_manager(manager)
        return manager

    def setCentralWidget(self, widget) -> None:  # noqa: ANN001, N802
        existing_quick_widget = getattr(self, "quick_widget", None)
        if isinstance(existing_quick_widget, QQuickWidget) and widget is not existing_quick_widget:
            manager = getattr(self, "_embedded_viewer_overlay_manager", None)
            if manager is not None:
                host_service = getattr(self, "viewer_host_service", None)
                if host_service is not None:
                    host_service.set_overlay_manager(None)
                plot_service = getattr(self, "plot_host_service", None)
                if plot_service is not None:
                    plot_service.set_overlay_manager(None)
                folder_service = getattr(self, "native_folder_explorer_host_service", None)
                if folder_service is not None:
                    folder_service.set_overlay_manager(None)
                manager.deleteLater()
                self._embedded_viewer_overlay_manager = None
        super().setCentralWidget(widget)
        if isinstance(widget, QQuickWidget):
            self.quick_widget = widget
            self._ensure_embedded_viewer_overlay_manager(widget)
            return
        qml_host = getattr(self, "qml_host", None)
        if qml_host is not None and widget is getattr(qml_host, "container_widget", None):
            self._ensure_embedded_viewer_overlay_manager()

    def _wire_signals(self) -> None:
        self.scene.node_selected.connect(
            self.workspace_edit_controller.on_scene_node_selected
        )
        self.scene.scope_changed.connect(self._on_scene_scope_changed)
        self.script_editor.script_apply_requested.connect(
            self.workspace_edit_controller.on_node_property_changed
        )
        self.workspace_tabs.current_index_changed.connect(
            self.workspace_navigation_controller.on_workspace_tab_changed
        )
        self.project_meta_changed.connect(self._on_project_meta_changed)

    def _reset_viewer_session_bridge(self, *, reason: str) -> None:
        host_service = getattr(self, "viewer_host_service", None)
        if host_service is not None:
            host_service.reset(reason=reason)
        bridge = getattr(self, "viewer_session_bridge", None)
        if bridge is None:
            return
        bridge.reset_all_sessions(reason=reason)

    def _open_logs(self) -> None:
        return

    def _clear_viewer_focus_for_deactivation(self) -> None:
        if not getattr(self, "_viewer_window_active", True):
            return
        self._viewer_window_active = False
        bridge = getattr(self, "viewer_session_bridge", None)
        clear_focus = getattr(bridge, "clear_viewer_focus", None)
        if not callable(clear_focus):
            return
        try:
            clear_focus()
        except Exception:  # noqa: BLE001
            return

    def _queue_window_deactivate_decision(self) -> None:
        if self._viewer_deactivate_decision_queued:
            return
        self._viewer_deactivate_decision_queued = True
        QTimer.singleShot(0, self._resolve_window_deactivate_decision)

    def _resolve_window_deactivate_decision(self) -> None:
        if not self._viewer_deactivate_decision_queued:
            return
        self._viewer_deactivate_decision_queued = False
        app = QApplication.instance()
        if app is None or app.applicationState() != Qt.ApplicationState.ApplicationActive:
            self._clear_viewer_focus_for_deactivation()
            return
        active_window = QApplication.activeWindow()
        if active_window is self:
            self._viewer_window_active = True
            return
        host_service = getattr(self, "viewer_host_service", None)
        owns_detached = getattr(host_service, "owns_detached_viewer_window", None)
        if callable(owns_detached):
            try:
                if owns_detached(active_window):
                    self._viewer_window_active = True
                    return
            except Exception:  # noqa: BLE001
                pass
        self._clear_viewer_focus_for_deactivation()

    def _connect_application_state_signal(self) -> None:
        if self._application_state_signal_connected:
            return
        app = QApplication.instance()
        signal = getattr(app, "applicationStateChanged", None) if app is not None else None
        if signal is not None and hasattr(signal, "connect"):
            signal.connect(self._handle_application_state_changed)
            self._application_state_signal_connected = True

    def _disconnect_application_state_signal(self) -> None:
        if not self._application_state_signal_connected:
            return
        app = QApplication.instance()
        signal = getattr(app, "applicationStateChanged", None) if app is not None else None
        if signal is None or not hasattr(signal, "disconnect"):
            self._application_state_signal_connected = False
            return
        try:
            signal.disconnect(self._handle_application_state_changed)
        except (TypeError, RuntimeError):
            pass
        self._application_state_signal_connected = False

    def _teardown_qml_surface(self) -> None:
        canvas_import = getattr(self, "canvas_import_controller", None)
        if canvas_import is not None:
            canvas_import.shutdown()
        host_service = getattr(self, "viewer_host_service", None)
        shutdown = getattr(host_service, "shutdown", None)
        if callable(shutdown):
            shutdown(reason="window_close")
        viewer_control_bridge = getattr(self, "viewer_control_bridge", None)
        control_shutdown = getattr(viewer_control_bridge, "shutdown", None)
        if callable(control_shutdown):
            control_shutdown()
        plot_service = getattr(self, "plot_host_service", None)
        plot_shutdown = getattr(plot_service, "shutdown", None)
        if callable(plot_shutdown):
            plot_shutdown(reason="window_close")
        plot_auto_preview_service = getattr(self, "plot_auto_preview_service", None)
        plot_auto_preview_shutdown = getattr(plot_auto_preview_service, "shutdown", None)
        if callable(plot_auto_preview_shutdown):
            plot_auto_preview_shutdown()
        inspector_presenter = getattr(self, "shell_inspector_presenter", None)
        inspector_shutdown = getattr(inspector_presenter, "shutdown", None)
        if callable(inspector_shutdown):
            inspector_shutdown()
        graph_canvas_host_presenter = getattr(self, "graph_canvas_host_presenter", None)
        graph_canvas_shutdown = getattr(graph_canvas_host_presenter, "shutdown", None)
        if callable(graph_canvas_shutdown):
            graph_canvas_shutdown()
        fullscreen_bridge = getattr(self, "content_fullscreen_bridge", None)
        fullscreen_shutdown = getattr(fullscreen_bridge, "shutdown", None)
        if callable(fullscreen_shutdown):
            fullscreen_shutdown()
        folder_service = getattr(self, "native_folder_explorer_host_service", None)
        folder_shutdown = getattr(folder_service, "shutdown", None)
        if callable(folder_shutdown):
            folder_shutdown(reason="window_close")
        jupyter_bridge = getattr(self, "jupyter_server_bridge", None)
        jupyter_shutdown = getattr(jupyter_bridge, "shutdown", None)
        if callable(jupyter_shutdown):
            jupyter_shutdown()

        manager = getattr(self, "_embedded_viewer_overlay_manager", None)
        if manager is not None:
            manager.deleteLater()
            self._embedded_viewer_overlay_manager = None

        qml_host = getattr(self, "qml_host", None)
        if qml_host is not None:
            try:
                qml_host.teardown()
            except Exception:  # noqa: BLE001
                return
            return
        quick_widget = getattr(self, "quick_widget", None)
        if not isinstance(quick_widget, QQuickWidget):
            return
        try:
            quick_widget.setUpdatesEnabled(False)
        except Exception:  # noqa: BLE001
            pass
        try:
            quick_widget.setSource(QUrl())
        except Exception:  # noqa: BLE001
            return

    def _handle_application_state_changed(self, state) -> None:  # noqa: ANN001
        if state == Qt.ApplicationState.ApplicationActive:
            self._viewer_window_active = True
            return
        self._viewer_deactivate_decision_queued = False
        self._clear_viewer_focus_for_deactivation()

    def event(self, event):  # noqa: ANN001
        if event is not None and event.type() == QEvent.Type.WindowDeactivate:
            self._queue_window_deactivate_decision()
        return super().event(event)

    def changeEvent(self, event) -> None:  # noqa: ANN001
        if event is not None and event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                self._viewer_window_active = True
            else:
                self._queue_window_deactivate_decision()
        super().changeEvent(event)

    def showEvent(self, event) -> None:  # noqa: ANN001
        self._viewer_window_active = True
        super().showEvent(event)
        if self._autosave_recovery_deferred:
            QTimer.singleShot(0, self._process_deferred_autosave_recovery_if_open)

    def _process_deferred_autosave_recovery_if_open(self) -> None:
        if self._shell_teardown_started:
            return
        self._process_deferred_autosave_recovery()

    def closeEvent(self, event) -> None:  # noqa: ANN001
        if self._shell_teardown_started:
            super().closeEvent(event)
            return
        self._shell_teardown_started = True
        for timer_name in ("metrics_timer", "graph_hint_timer", "autosave_timer"):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                timer.stop()
        try:
            if hasattr(self, "run_state"):
                self.run_projection_controller.clear_run_failure_focus()
            self._reset_viewer_session_bridge(reason="project_close")
            project_session_controller = getattr(self, "project_session_controller", None)
            if project_session_controller is not None:
                project_session_controller.close_session()
            self._disconnect_application_state_signal()
            self._teardown_qml_surface()
        finally:
            execution_client = getattr(self, "execution_client", None)
            if execution_client is not None:
                execution_client.shutdown()
            super().closeEvent(event)
