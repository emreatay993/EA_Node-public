from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Literal

from ea_node_editor.ui.shell.window_actions import (
    build_window_menu_bar,
    create_window_actions,
    refresh_recent_projects_menu as refresh_recent_projects_menu_entries,
)

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


# The `_qt_*` functions stay module-level on purpose: `window.py` binds them as
# `pyqtProperty(fget=context_properties._qt_<name>)` and tests call them with an
# explicit host argument.


def _qt_project_display_name(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.project_display_name


def _qt_filtered_node_library_items(self: "ShellWindow") -> list[dict[str, Any]]:
    return self.shell_library_presenter.filtered_node_library_items


def _qt_grouped_node_library_items(self: "ShellWindow") -> list[dict[str, Any]]:
    return self.shell_library_presenter.grouped_node_library_items


def _qt_library_category_options(self: "ShellWindow") -> list[dict[str, str]]:
    return self.shell_library_presenter.library_category_options


def _qt_library_direction_options(self: "ShellWindow") -> list[dict[str, str]]:
    return self.shell_library_presenter.library_direction_options


def _qt_library_data_type_options(self: "ShellWindow") -> list[dict[str, str]]:
    return self.shell_library_presenter.library_data_type_options


def _qt_pin_data_type_options(self: "ShellWindow") -> list[str]:
    return self.shell_inspector_presenter.pin_data_type_options


def _qt_graph_search_open(self: "ShellWindow") -> bool:
    return self.shell_library_presenter.graph_search_open


def _qt_graph_search_query(self: "ShellWindow") -> str:
    return self.shell_library_presenter.graph_search_query


def _qt_graph_search_enabled_scopes(self: "ShellWindow") -> list[str]:
    return self.shell_library_presenter.graph_search_enabled_scopes


def _qt_graph_search_results(self: "ShellWindow") -> list[dict[str, Any]]:
    return self.shell_library_presenter.graph_search_results


def _qt_graph_search_highlight_index(self: "ShellWindow") -> int:
    return self.shell_library_presenter.graph_search_highlight_index


def _qt_connection_quick_insert_open(self: "ShellWindow") -> bool:
    return self.shell_library_presenter.connection_quick_insert_open


def _qt_connection_quick_insert_query(self: "ShellWindow") -> str:
    return self.shell_library_presenter.connection_quick_insert_query


def _qt_connection_quick_insert_results(self: "ShellWindow") -> list[dict[str, Any]]:
    return self.shell_library_presenter.connection_quick_insert_results


def _qt_connection_quick_insert_highlight_index(self: "ShellWindow") -> int:
    return self.shell_library_presenter.connection_quick_insert_highlight_index


def _qt_connection_quick_insert_overlay_x(self: "ShellWindow") -> float:
    return self.shell_library_presenter.connection_quick_insert_overlay_x


def _qt_connection_quick_insert_overlay_y(self: "ShellWindow") -> float:
    return self.shell_library_presenter.connection_quick_insert_overlay_y


def _qt_connection_quick_insert_source_summary(self: "ShellWindow") -> str:
    return self.shell_library_presenter.connection_quick_insert_source_summary


def _qt_connection_quick_insert_is_canvas_mode(self: "ShellWindow") -> bool:
    return self.shell_library_presenter.connection_quick_insert_is_canvas_mode


def _qt_graph_hint_message(self: "ShellWindow") -> str:
    return self.shell_library_presenter.graph_hint_message


def _qt_graph_hint_visible(self: "ShellWindow") -> bool:
    return self.shell_library_presenter.graph_hint_visible


def _qt_graphics_expand_collision_avoidance(self: "ShellWindow") -> dict[str, Any]:
    return self.shell_workspace_presenter.graphics_expand_collision_avoidance


def _qt_addon_manager_request(self: "ShellWindow") -> dict[str, Any]:
    return self.addon_manager_request_snapshot()


def _qt_addon_manager_open(self: "ShellWindow") -> bool:
    return bool(self.addon_manager_request_snapshot().get("open", False))


def _qt_addon_manager_focus_addon_id(self: "ShellWindow") -> str:
    return str(self.addon_manager_request_snapshot().get("focus_addon_id", ""))


def _qt_addon_manager_request_serial(self: "ShellWindow") -> int:
    return int(self.addon_manager_request_snapshot().get("request_serial", 0))


def _qt_graphics_show_grid(self: "ShellWindow") -> bool:
    return self.shell_workspace_presenter.graphics_show_grid


def _qt_graphics_grid_style(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.graphics_grid_style


def _qt_graphics_edge_crossing_style(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.graphics_edge_crossing_style


def _qt_graphics_graph_label_pixel_size(self: "ShellWindow") -> int:
    return self.shell_workspace_presenter.graphics_graph_label_pixel_size


def _qt_graphics_graph_node_icon_pixel_size_override(self: "ShellWindow") -> int | None:
    return self.shell_workspace_presenter.graphics_graph_node_icon_pixel_size_override


def _qt_graphics_node_title_icon_pixel_size(self: "ShellWindow") -> int:
    return self.shell_workspace_presenter.graphics_node_title_icon_pixel_size


def _qt_graphics_show_minimap(self: "ShellWindow") -> bool:
    return self.shell_workspace_presenter.graphics_show_minimap


def _qt_graphics_show_canvas_options_button(self: "ShellWindow") -> bool:
    return self.shell_workspace_presenter.graphics_show_canvas_options_button


def _qt_graphics_show_port_labels(self: "ShellWindow") -> bool:
    return self.shell_workspace_presenter.graphics_show_port_labels


def _qt_graphics_notched_ports(self: "ShellWindow") -> bool:
    return self.shell_workspace_presenter.graphics_notched_ports


def _qt_graphics_node_elapsed_time_unit(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.graphics_node_elapsed_time_unit


def _qt_graphics_node_elapsed_time_visibility(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.graphics_node_elapsed_time_visibility


def _qt_graphics_show_tooltips(self: "ShellWindow") -> bool:
    return self.shell_workspace_presenter.graphics_show_tooltips


def _qt_graphics_tooltip_categories(self: "ShellWindow") -> dict[str, bool]:
    return self.shell_workspace_presenter.graphics_tooltip_categories


def _qt_graphics_tooltip_category_visibility(self: "ShellWindow") -> dict[str, bool]:
    return self.shell_workspace_presenter.graphics_tooltip_category_visibility


def _qt_graphics_minimap_expanded(self: "ShellWindow") -> bool:
    return bool(self.search_scope_state.graphics_minimap_expanded)


def _qt_graphics_node_shadow(self: "ShellWindow") -> bool:
    return self.shell_workspace_presenter.graphics_node_shadow


def _qt_graphics_shadow_strength(self: "ShellWindow") -> int:
    return self.shell_workspace_presenter.graphics_shadow_strength


def _qt_graphics_shadow_softness(self: "ShellWindow") -> int:
    return self.shell_workspace_presenter.graphics_shadow_softness


def _qt_graphics_shadow_offset(self: "ShellWindow") -> int:
    return self.shell_workspace_presenter.graphics_shadow_offset


def _qt_graphics_status_bar_layout(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.graphics_status_bar_layout


def _qt_graphics_show_fps_telemetry(self: "ShellWindow") -> bool:
    return self.shell_workspace_presenter.graphics_show_fps_telemetry


def _qt_graphics_floating_toolbar_style(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.graphics_floating_toolbar_style


def _qt_graphics_floating_toolbar_size(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.graphics_floating_toolbar_size


def _qt_graphics_selection_toolbar_mode(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.graphics_selection_toolbar_mode


def _qt_graphics_selection_toolbar_minimal_menu_trigger(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.graphics_selection_toolbar_minimal_menu_trigger


def _qt_graphics_folder_explorer_column_widths(self: "ShellWindow") -> dict[str, int]:
    return self.shell_workspace_presenter.graphics_folder_explorer_column_widths


def _qt_graphics_tab_strip_density(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.graphics_tab_strip_density


def _qt_active_theme_id(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.active_theme_id


def _qt_snap_to_grid_enabled(self: "ShellWindow") -> bool:
    return bool(self.search_scope_state.snap_to_grid_enabled)


def _qt_snap_grid_size(self: "ShellWindow") -> float:
    return float(self._SNAP_GRID_SIZE)


def _qt_active_workspace_id(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.active_workspace_id


def _qt_active_workspace_name(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.active_workspace_name


def _qt_active_view_name(self: "ShellWindow") -> str:
    return self.shell_workspace_presenter.active_view_name


def _qt_active_view_items(self: "ShellWindow") -> list[dict[str, Any]]:
    return self.shell_workspace_presenter.active_view_items


def _qt_active_scope_breadcrumb_items(self: "ShellWindow") -> list[dict[str, str]]:
    return self.shell_workspace_presenter.active_scope_breadcrumb_items


def _qt_selected_node_title(self: "ShellWindow") -> str:
    return self.shell_inspector_presenter.selected_node_title


def _qt_selected_node_subtitle(self: "ShellWindow") -> str:
    return self.shell_inspector_presenter.selected_node_subtitle


def _qt_selected_node_header_items(self: "ShellWindow") -> list[dict[str, str]]:
    return self.shell_inspector_presenter.selected_node_header_items


def _qt_selected_node_summary(self: "ShellWindow") -> str:
    return self.shell_inspector_presenter.selected_node_summary


def _qt_has_selected_node(self: "ShellWindow") -> bool:
    return self.shell_inspector_presenter.has_selected_node


def _qt_selected_node_collapsible(self: "ShellWindow") -> bool:
    return self.shell_inspector_presenter.selected_node_collapsible


def _qt_selected_node_collapsed(self: "ShellWindow") -> bool:
    return self.shell_inspector_presenter.selected_node_collapsed


def _qt_selected_node_is_subnode_pin(self: "ShellWindow") -> bool:
    return self.shell_inspector_presenter.selected_node_is_subnode_pin


def _qt_selected_node_is_subnode_shell(self: "ShellWindow") -> bool:
    return self.shell_inspector_presenter.selected_node_is_subnode_shell


def _qt_can_publish_custom_workflow_from_scope(self: "ShellWindow") -> bool:
    return self.shell_workspace_presenter.can_publish_custom_workflow_from_scope


def _qt_selected_node_property_items(self: "ShellWindow") -> list[dict[str, Any]]:
    return self.shell_inspector_presenter.selected_node_property_items


def _qt_selected_node_link_items(self: "ShellWindow") -> list[dict[str, Any]]:
    return self.shell_inspector_presenter.selected_node_link_items


def _qt_selected_node_port_items(self: "ShellWindow") -> list[dict[str, Any]]:
    return self.shell_inspector_presenter.selected_node_port_items


class ShellWindowContextPropertiesMixin:
    @property
    def project_path(self: "ShellWindow") -> str:
        return self.project_session_state.project_path

    @project_path.setter
    def project_path(self: "ShellWindow", value: str) -> None:
        self.project_session_state.project_path = str(value)

    @property
    def recent_project_paths(self: "ShellWindow") -> list[str]:
        return list(self.project_session_state.recent_project_paths)

    @recent_project_paths.setter
    def recent_project_paths(self: "ShellWindow", value: list[str]) -> None:
        self.project_session_state.recent_project_paths = [str(path) for path in value]

    @property
    def _library_query(self: "ShellWindow") -> str:
        return self.library_filter_state.library_query

    @_library_query.setter
    def _library_query(self: "ShellWindow", value: str) -> None:
        self.library_filter_state.library_query = str(value)

    @property
    def _library_category(self: "ShellWindow") -> str:
        return self.library_filter_state.library_category

    @_library_category.setter
    def _library_category(self: "ShellWindow", value: str) -> None:
        self.library_filter_state.library_category = str(value)

    @property
    def _library_data_type(self: "ShellWindow") -> str:
        return self.library_filter_state.library_data_type

    @_library_data_type.setter
    def _library_data_type(self: "ShellWindow", value: str) -> None:
        self.library_filter_state.library_data_type = str(value)

    @property
    def _library_direction(self: "ShellWindow") -> str:
        return self.library_filter_state.library_direction

    @_library_direction.setter
    def _library_direction(self: "ShellWindow", value: str) -> None:
        self.library_filter_state.library_direction = str(value)

    @property
    def _active_run_id(self: "ShellWindow") -> str:
        return self.run_state.active_run_id

    @_active_run_id.setter
    def _active_run_id(self: "ShellWindow", value: str) -> None:
        self.run_state.active_run_id = str(value)

    @property
    def _active_run_workspace_id(self: "ShellWindow") -> str:
        return self.run_state.active_run_workspace_id

    @_active_run_workspace_id.setter
    def _active_run_workspace_id(self: "ShellWindow", value: str) -> None:
        self.run_state.active_run_workspace_id = str(value)

    @property
    def _engine_state_value(self: "ShellWindow") -> Literal["ready", "running", "paused", "error"]:
        return self.run_state.engine_state_value

    @_engine_state_value.setter
    def _engine_state_value(
        self: "ShellWindow",
        value: Literal["ready", "running", "paused", "error"] | str,
    ) -> None:
        normalized = str(value)
        if normalized not in {"ready", "running", "paused", "error"}:
            normalized = "ready"
        self.run_state.engine_state_value = normalized  # type: ignore[assignment]

    @property
    def _last_manual_save_ts(self: "ShellWindow") -> float:
        return self.project_session_state.last_manual_save_ts

    @_last_manual_save_ts.setter
    def _last_manual_save_ts(self: "ShellWindow", value: float) -> None:
        self.project_session_state.last_manual_save_ts = float(value)

    @property
    def _last_autosave_fingerprint(self: "ShellWindow") -> str:
        return self.project_session_state.last_autosave_fingerprint

    @_last_autosave_fingerprint.setter
    def _last_autosave_fingerprint(self: "ShellWindow", value: str) -> None:
        self.project_session_state.last_autosave_fingerprint = str(value)

    @property
    def _autosave_recovery_deferred(self: "ShellWindow") -> bool:
        return self.project_session_state.autosave_recovery_deferred

    @_autosave_recovery_deferred.setter
    def _autosave_recovery_deferred(self: "ShellWindow", value: bool) -> None:
        self.project_session_state.autosave_recovery_deferred = bool(value)

    def _registry_library_items(self: "ShellWindow") -> list[dict[str, Any]]:
        return self.shell_library_presenter._registry_library_items()

    def _combined_library_items(self: "ShellWindow") -> list[dict[str, Any]]:
        return self.shell_library_presenter._combined_library_items()

    def _library_item_matches_filters(
        self: "ShellWindow",
        item: dict[str, Any],
        *,
        query: str,
        category: str,
        data_type: str,
        direction: str,
    ) -> bool:
        return self.shell_library_presenter._library_item_matches_filters(
            item,
            query=query,
            category=category,
            data_type=data_type,
            direction=direction,
        )

    def _selected_node_header_data(self: "ShellWindow") -> dict[str, Any]:
        return self.shell_inspector_presenter._selected_node_header_data()

    def _node_property_spec(self: "ShellWindow", node_id: str, key: str):
        return self.shell_inspector_presenter._node_property_spec(node_id, key)

    def _selected_node_property_spec(self: "ShellWindow", key: str):
        return self.shell_inspector_presenter._selected_node_property_spec(key)

    def _path_dialog_start_path(self: "ShellWindow", current_path: str) -> str:
        return self.shell_inspector_presenter._path_dialog_start_path(current_path)

    def _create_actions(self: "ShellWindow") -> None:
        create_window_actions(self)

    def _build_menu_bar(self: "ShellWindow") -> None:
        build_window_menu_bar(self)

    def _refresh_recent_projects_menu(self: "ShellWindow") -> None:
        refresh_recent_projects_menu_entries(self)

    def _active_scope_camera_key(
        self: "ShellWindow",
        scope_path: tuple[str, ...] | None = None,
    ) -> tuple[str, str, tuple[str, ...]] | None:
        return self.search_scope_controller.active_scope_camera_key(scope_path)

    def _remember_scope_camera(self: "ShellWindow", scope_path: tuple[str, ...] | None = None) -> None:
        self.search_scope_controller.remember_scope_camera(scope_path)

    def _restore_scope_camera(self: "ShellWindow", scope_path: tuple[str, ...] | None = None) -> bool:
        return bool(self.search_scope_controller.restore_scope_camera(scope_path))

    def _navigate_scope(self: "ShellWindow", navigate_fn: Callable[[], bool]) -> bool:
        return bool(self.search_scope_controller.navigate_scope(navigate_fn))

    def _on_scene_scope_changed(self: "ShellWindow") -> None:
        self.request_close_connection_quick_insert()
        self.workspace_state_changed.emit()
        self.selected_node_changed.emit()

    def _on_project_meta_changed(self: "ShellWindow") -> None:
        self.selected_node_changed.emit()
        self._refresh_active_workspace_scene_payload()


__all__ = [
    "ShellWindowContextPropertiesMixin",
]
