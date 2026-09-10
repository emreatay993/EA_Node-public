from __future__ import annotations

from typing import Any, Protocol

from PyQt6.QtCore import QObject

from ea_node_editor.common.protocols import SignalLike as _SignalLike


def _presenter_parent(host: object, parent: QObject | None) -> QObject | None:
    if parent is not None:
        return parent
    return host if isinstance(host, QObject) else None


class _ShellLibraryPresenterHostProtocol(Protocol):
    node_library_changed: _SignalLike
    library_pane_reset_requested: _SignalLike
    graph_search_changed: _SignalLike
    connection_quick_insert_changed: _SignalLike
    graph_hint_changed: _SignalLike
    registry: Any
    workspace_ui_state: Any
    workflow_library_controller: Any
    workspace_drop_connect_controller: Any
    library_filter_state: Any
    search_scope_controller: Any
    search_scope_state: Any
    model: Any
    workspace_manager: Any
    scene: Any
    _CONNECTION_QUICK_INSERT_LIMIT: int
    _CONNECTION_QUICK_INSERT_OFFSET: float


class _ShellWorkspacePresenterHostProtocol(Protocol):
    project_meta_changed: _SignalLike
    workspace_state_changed: _SignalLike
    graphics_preferences_changed: _SignalLike
    run_controls_changed: _SignalLike
    project_path: str
    workspace_ui_state: Any
    workspace_manager: Any
    model: Any
    scene: Any
    run_state: Any
    run_controller: Any
    project_session_controller: Any
    search_scope_controller: Any
    search_scope_state: Any
    workspace_navigation_controller: Any
    shell_host_presenter: Any
    shell_inspector_presenter: Any
    canvas_export_presenter: Any
    graph_theme_bridge: Any
    app_preferences_controller: Any


class _ShellInspectorPresenterHostProtocol(Protocol):
    selected_node_changed: _SignalLike
    workspace_state_changed: _SignalLike
    node_execution_state_changed: _SignalLike
    run_state: Any
    workspace_selection_context: Any
    workspace_edit_controller: Any
    workspace_navigation_controller: Any
    model: Any
    workspace_manager: Any
    registry: Any
    _SUBNODE_PIN_TYPE_IDS: set[str]
    project_path: str
    shell_host_presenter: Any

    def _repair_property_path_dialog(
        self,
        *,
        node_id: str = "",
        node_title: str = "",
        node_type: str = "",
        node_type_id: str,
        property_key: str,
        property_label: str,
        current_path: str,
        file_filter: str = "",
    ) -> str: ...


class _CanvasExportPresenterHostProtocol(Protocol):
    scene: Any
    view: Any
    model: Any
    workspace_manager: Any
    quick_widget: Any
    shell_host_presenter: Any
    viewer_host_service: Any
    plot_host_service: Any
    embedded_viewer_overlay_manager: Any
    project_path: str
    console_panel: Any

    def show_graph_hint(self, message: str, timeout_ms: int = 3600) -> None: ...

    def update_notification_counters(self, warnings: int, errors: int) -> None: ...


class _GraphCanvasHostPresenterHostProtocol(Protocol):
    project_meta_changed: _SignalLike
    project_path: str
    model: Any
    registry: Any
    workspace_manager: Any
    search_scope_controller: Any
    scene: Any
    project_session_controller: Any
    quick_widget: Any
    workspace_edit_controller: Any


class _ProjectReviewDeckPresenterHostProtocol(Protocol):
    model: Any
    registry: Any
    project_path: str
    workspace_manager: Any
    workspace_navigation_controller: Any
    canvas_export_presenter: Any
    shell_host_presenter: Any
    console_panel: Any

    def show_graph_hint(self, message: str, timeout_ms: int = 3600) -> None: ...
