from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from ea_node_editor.app_preferences import (
    effective_graph_node_icon_pixel_size,
    normalize_edge_crossing_style,
    normalize_expand_collision_avoidance_settings,
    normalize_floating_toolbar_size,
    normalize_floating_toolbar_style,
    normalize_folder_explorer_column_widths,
    normalize_graph_label_pixel_size,
    normalize_graph_node_icon_pixel_size_override,
    normalize_status_bar_layout,
    normalize_canvas_background_variant,
    normalize_canvas_import_mode,
    normalize_grid_overlay_style,
    normalize_media_panel_settings,
    normalize_node_comment_editor_default,
    normalize_node_elapsed_time_unit,
    normalize_node_elapsed_time_visibility,
    normalize_passive_node_library_display_mode,
    normalize_plot_settings,
    normalize_property_pane_variant,
    normalize_selection_toolbar_minimal_menu_trigger,
    normalize_selection_toolbar_mode,
    normalize_shell_panel_collapsed,
)
from ea_node_editor.settings import DEFAULT_GRAPHICS_SETTINGS
from ea_node_editor.text_style import normalize_recent_text_colors
from ea_node_editor.ui.shell.run_flow import (
    SelectedWorkspaceRunControlState,
    selected_workspace_run_control_state,
)
from ea_node_editor.ui.shell.tooltip_policy import (
    TOOLTIP_CATEGORY_GENERAL,
    TOOLTIP_CATEGORY_NAMES,
    normalize_tooltip_category_name,
    normalize_tooltip_category_preferences,
    tooltip_category_effectively_visible,
)
from ea_node_editor.ui.graph_theme import resolve_graph_theme_id, serialize_custom_graph_themes

from .contracts import _ShellWorkspacePresenterHostProtocol, _presenter_parent
from .state import ShellWorkspaceUiState


class ShellWorkspacePresenter(QObject):
    project_meta_changed = pyqtSignal()
    workspace_state_changed = pyqtSignal()
    graphics_preferences_changed = pyqtSignal()
    run_controls_changed = pyqtSignal()

    def __init__(
        self,
        host: _ShellWorkspacePresenterHostProtocol,
        *,
        parent: QObject | None = None,
        ui_state: ShellWorkspaceUiState | None = None,
    ) -> None:
        super().__init__(_presenter_parent(host, parent))
        self._host = host
        self._ui_state = ui_state if ui_state is not None else host.workspace_ui_state
        self._expand_collision_avoidance = normalize_expand_collision_avoidance_settings(
            DEFAULT_GRAPHICS_SETTINGS["interaction"]["expand_collision_avoidance"]
        )
        self._tooltip_categories_cache: dict[str, bool] | None = None
        self._tooltip_category_visibility_cache: dict[str, bool] | None = None
        host.project_meta_changed.connect(self.project_meta_changed.emit)
        host.workspace_state_changed.connect(self.workspace_state_changed.emit)
        host.graphics_preferences_changed.connect(self._handle_graphics_preferences_changed)
        host.run_controls_changed.connect(self.run_controls_changed.emit)

    def _handle_graphics_preferences_changed(self) -> None:
        self._tooltip_categories_cache = None
        self._tooltip_category_visibility_cache = None
        self.graphics_preferences_changed.emit()

    def _tooltip_categories_projection(self) -> dict[str, bool]:
        if self._tooltip_categories_cache is None:
            self._tooltip_categories_cache = dict(self._ui_state.graphics_tooltip_categories)
        return self._tooltip_categories_cache

    def _tooltip_category_visibility_projection(self) -> dict[str, bool]:
        if self._tooltip_category_visibility_cache is None:
            tooltip_categories = self._tooltip_categories_projection()
            self._tooltip_category_visibility_cache = {
                category: tooltip_category_effectively_visible(
                    category,
                    tooltip_categories=tooltip_categories,
                )
                for category in TOOLTIP_CATEGORY_NAMES
            }
        return self._tooltip_category_visibility_cache

    @property
    def project_display_name(self) -> str:
        filename = Path(self._host.project_path).name if self._host.project_path else "untitled.cxproj"
        return f"COREX Node Editor - {filename}"

    @property
    def project_file_name(self) -> str:
        return Path(self._host.project_path).name if self._host.project_path else "untitled.cxproj"

    @property
    def graphics_tab_strip_density(self) -> str: return str(self._ui_state.tab_strip_density)

    @property
    def graphics_show_grid(self) -> bool: return bool(self._ui_state.show_grid)

    @property
    def graphics_canvas_background_variant(self) -> str:
        return str(self._ui_state.canvas_background_variant)

    @property
    def graphics_grid_style(self) -> str: return str(self._ui_state.grid_style)

    @property
    def graphics_show_minimap(self) -> bool: return bool(self._ui_state.show_minimap)

    @property
    def graphics_show_canvas_options_button(self) -> bool:
        return bool(self._ui_state.show_canvas_options_button)

    @property
    def graphics_show_port_labels(self) -> bool: return bool(self._ui_state.show_port_labels)

    @property
    def graphics_show_tooltips(self) -> bool:
        return self.tooltip_category_enabled(TOOLTIP_CATEGORY_GENERAL)

    @property
    def graphics_tooltip_categories(self) -> dict[str, bool]:
        return dict(self._tooltip_categories_projection())

    @property
    def graphics_tooltip_category_visibility(self) -> dict[str, bool]:
        return dict(self._tooltip_category_visibility_projection())

    def tooltip_category_enabled(self, category: object) -> bool:
        return bool(
            self._tooltip_category_visibility_projection().get(
                normalize_tooltip_category_name(category),
                False,
            )
        )

    @property
    def graphics_status_bar_layout(self) -> str: return str(self._ui_state.status_bar_layout)

    @property
    def graphics_show_fps_telemetry(self) -> bool: return bool(self._ui_state.show_fps_telemetry)

    @property
    def passive_node_library_display_mode(self) -> str:
        return str(self._ui_state.passive_node_library_display_mode)

    @property
    def shell_panel_collapsed(self) -> dict[str, bool]:
        return copy.deepcopy(self._ui_state.shell_panel_collapsed)

    @property
    def graphics_floating_toolbar_style(self) -> str: return str(self._ui_state.floating_toolbar_style)

    @property
    def graphics_floating_toolbar_size(self) -> str: return str(self._ui_state.floating_toolbar_size)

    @property
    def graphics_node_floating_toolbar_opens_on_hover(self) -> bool:
        return bool(self._ui_state.node_floating_toolbar_opens_on_hover)

    @property
    def graphics_selection_toolbar_mode(self) -> str: return str(self._ui_state.selection_toolbar_mode)

    @property
    def graphics_selection_toolbar_minimal_menu_trigger(self) -> str:
        return str(self._ui_state.selection_toolbar_minimal_menu_trigger)

    @property
    def graphics_edge_crossing_style(self) -> str: return str(self._ui_state.edge_crossing_style)

    @property
    def graphics_notched_ports(self) -> bool: return bool(self._ui_state.notched_ports)

    @property
    def graphics_keep_expanded_node_width(self) -> bool:
        return bool(self._ui_state.keep_expanded_node_width)

    @property
    def graphics_node_elapsed_time_unit(self) -> str:
        return str(self._ui_state.node_elapsed_time_unit)

    @property
    def graphics_node_elapsed_time_visibility(self) -> str:
        return str(self._ui_state.node_elapsed_time_visibility)

    @property
    def graphics_node_comment_editor_default(self) -> str:
        return str(self._ui_state.node_comment_editor_default)

    @property
    def graphics_node_shadow(self) -> bool: return bool(self._ui_state.node_shadow)

    @property
    def graphics_shadow_strength(self) -> int: return int(self._ui_state.shadow_strength)

    @property
    def graphics_shadow_softness(self) -> int: return int(self._ui_state.shadow_softness)

    @property
    def graphics_shadow_offset(self) -> int: return int(self._ui_state.shadow_offset)

    @property
    def graphics_canvas_import_mode(self) -> str:
        return self._ui_state.canvas_import_mode

    @property
    def graphics_expand_collision_avoidance(self) -> dict[str, Any]:
        return copy.deepcopy(self._expand_collision_avoidance)

    def set_shell_panel_collapsed(self, panel_id: str, collapsed: bool) -> None:
        normalized_panel_id = str(panel_id or "").strip()
        defaults = DEFAULT_GRAPHICS_SETTINGS["shell"]["panel_collapsed"]
        if normalized_panel_id not in defaults:
            return
        current = normalize_shell_panel_collapsed(self._ui_state.shell_panel_collapsed)
        next_state = copy.deepcopy(current)
        next_state[normalized_panel_id] = bool(collapsed)
        if next_state == current:
            return
        self._host.app_preferences_controller.update_graphics_settings(
            {"shell": {"panel_collapsed": next_state}},
            host=self._host,
        )

    @property
    def graphics_graph_label_pixel_size(self) -> int: return int(self._ui_state.graph_label_pixel_size)

    @property
    def graphics_graph_node_icon_pixel_size_override(self) -> int | None:
        return self._ui_state.graph_node_icon_pixel_size_override

    @property
    def graphics_recent_text_colors(self) -> list[str]:
        return list(self._ui_state.recent_text_colors)

    @property
    def graphics_node_title_icon_pixel_size(self) -> int:
        return int(self._ui_state.node_title_icon_pixel_size)

    @property
    def graphics_media_panel_defaults(self) -> dict[str, bool]:
        return {
            "show_title": self.graphics_media_panel_default_show_title,
            "show_frame": self.graphics_media_panel_default_show_frame,
            "autoplay_animations": self.graphics_media_panel_autoplay_animations,
            "source_input_exposed": self.graphics_media_panel_source_input_exposed,
        }

    @property
    def graphics_media_panel_default_show_title(self) -> bool:
        return bool(self._ui_state.media_panel_default_show_title)

    @property
    def graphics_media_panel_default_show_frame(self) -> bool:
        return bool(self._ui_state.media_panel_default_show_frame)

    @property
    def graphics_media_panel_autoplay_animations(self) -> bool:
        return bool(self._ui_state.media_panel_autoplay_animations)

    @property
    def graphics_media_panel_source_input_exposed(self) -> bool:
        return bool(self._ui_state.media_panel_source_input_exposed)

    @property
    def graphics_folder_explorer_column_widths(self) -> dict[str, int]:
        return copy.deepcopy(self._ui_state.folder_explorer_column_widths)

    @property
    def graphics_lightweight_canvas(self) -> bool:
        return bool(self._ui_state.lightweight_canvas)

    @property
    def graphics_plot_default_backend_per_type(self) -> dict[str, str]:
        return copy.deepcopy(self._ui_state.plot_default_backend_per_type)

    @property
    def active_theme_id(self) -> str: return str(self._ui_state.active_theme_id)

    @property
    def graphics_graph_follow_shell_theme(self) -> bool:
        settings = self._host.app_preferences_controller.graph_theme_settings()
        return bool(settings.get("follow_shell_theme", DEFAULT_GRAPHICS_SETTINGS["graph_theme"]["follow_shell_theme"]))

    @property
    def graphics_selected_graph_theme_id(self) -> str:
        settings = self._host.app_preferences_controller.graph_theme_settings()
        return str(settings.get("selected_theme_id", DEFAULT_GRAPHICS_SETTINGS["graph_theme"]["selected_theme_id"]))

    @property
    def active_workspace_id(self) -> str:
        try:
            return self._host.workspace_manager.active_workspace_id()
        except Exception:  # noqa: BLE001
            return ""

    @property
    def active_workspace_name(self) -> str:
        workspace = self._host.model.project.workspaces.get(self.active_workspace_id)
        return workspace.name if workspace is not None else ""

    @property
    def active_view_name(self) -> str:
        workspace = self._host.model.project.workspaces.get(self.active_workspace_id)
        if workspace is None:
            return ""
        workspace.ensure_default_view()
        active_view = workspace.views.get(workspace.active_view_id)
        return active_view.name if active_view is not None else ""

    @property
    def active_view_items(self) -> list[dict[str, Any]]:
        workspace = self._host.model.project.workspaces.get(self.active_workspace_id)
        if workspace is None:
            return []
        workspace.ensure_default_view()
        return [
            {
                "view_id": view.view_id,
                "label": view.name,
                "active": view.view_id == workspace.active_view_id,
            }
            for view in workspace.views.values()
        ]

    @property
    def active_scope_breadcrumb_items(self) -> list[dict[str, str]]:
        return list(self._host.scene.scope_breadcrumb_model)

    @property
    def can_publish_custom_workflow_from_scope(self) -> bool: return bool(self._host.scene.active_scope_path)

    @property
    def _active_workspace_run_controls(self) -> SelectedWorkspaceRunControlState:
        run_state = self._host.run_state
        return selected_workspace_run_control_state(
            selected_workspace_id=self.active_workspace_id,
            active_run_id=getattr(run_state, "active_run_id", ""),
            active_run_workspace_id=getattr(run_state, "active_run_workspace_id", ""),
            engine_state=getattr(run_state, "engine_state_value", ""),
        )

    @property
    def active_workspace_can_run(self) -> bool:
        return bool(self._active_workspace_run_controls.can_run_active_workspace)

    @property
    def active_workspace_can_pause(self) -> bool:
        return bool(self._active_workspace_run_controls.can_pause_active_workspace)

    @property
    def active_workspace_can_stop(self) -> bool:
        return bool(self._active_workspace_run_controls.can_stop_active_workspace)

    @property
    def active_workspace_run_control_mode(self) -> str:
        controls = self._active_workspace_run_controls
        if not controls.selected_workspace_owns_active_run:
            return "run"
        return "resume" if controls.pause_label == "Resume" else "pause"

    @property
    def auto_run_enabled(self) -> bool:
        return self._host.run_controller.auto_run_enabled_for_workspace()

    def request_run_workflow(self) -> None: self._host.run_controller.run_workflow()
    def request_save_project_as(self) -> None: self._host.project_session_controller.save_project_as()
    def request_toggle_run_pause(self) -> None: self._host.run_controller.toggle_pause_resume()
    def request_stop_workflow(self) -> None: self._host.run_controller.stop_workflow()
    def request_toggle_auto_run(self) -> None: self._host.run_controller.toggle_auto_run()
    def show_workflow_settings_dialog(self, _checked: bool = False) -> None: self._host.project_session_controller.show_workflow_settings_dialog()
    def set_script_editor_panel_visible(self, checked: bool | None = None) -> None: self._host.project_session_controller.set_script_editor_panel_visible(checked)
    def _update_graphics_settings(self, updates: dict[str, Any]) -> None:
        self._host.app_preferences_controller.update_graphics_settings(
            updates,
            host=self._host,
        )

    def set_graphics_canvas_import_mode(self, mode: str) -> None:
        self._host.app_preferences_controller.set_graphics_canvas_import_mode(
            mode,
            host=self._host,
        )

    def set_graphics_show_grid(self, show_grid: bool) -> None:
        self._update_graphics_settings({"canvas": {"show_grid": bool(show_grid)}})

    def set_graphics_canvas_background_variant(self, variant: str) -> None:
        self._update_graphics_settings({"canvas": {"background_variant": str(variant)}})

    def set_graphics_grid_style(self, style: str) -> None:
        self._update_graphics_settings({"canvas": {"grid_style": str(style)}})

    def set_graphics_show_port_labels(self, show_port_labels: bool) -> None:
        self._update_graphics_settings(
            {"canvas": {"show_port_labels": bool(show_port_labels)}}
        )

    def set_graphics_node_elapsed_time_unit(self, unit: str) -> None:
        self._update_graphics_settings({"canvas": {"node_elapsed_time_unit": str(unit)}})

    def set_graphics_node_elapsed_time_visibility(self, visibility: str) -> None:
        self._update_graphics_settings(
            {"canvas": {"node_elapsed_time_visibility": str(visibility)}}
        )

    def set_graphics_node_comment_editor_default(self, value: str) -> None:
        self._host.app_preferences_controller.set_graphics_node_comment_editor_default(
            value,
            host=self._host,
        )

    def set_graphics_node_shadow(self, enabled: bool) -> None:
        self._update_graphics_settings({"canvas": {"node_shadow": bool(enabled)}})

    def set_graphics_floating_toolbar_style(self, style: str) -> None:
        self._host.app_preferences_controller.set_graphics_floating_toolbar_style(
            style,
            host=self._host,
        )

    def set_graphics_floating_toolbar_size(self, size: str) -> None:
        self._host.app_preferences_controller.set_graphics_floating_toolbar_size(
            size,
            host=self._host,
        )

    def set_graphics_selection_toolbar_mode(self, mode: str) -> None:
        self._host.app_preferences_controller.set_graphics_selection_toolbar_mode(
            mode,
            host=self._host,
        )

    def set_graphics_selection_toolbar_minimal_menu_trigger(self, trigger: str) -> None:
        self._host.app_preferences_controller.set_graphics_selection_toolbar_minimal_menu_trigger(
            trigger,
            host=self._host,
        )

    def set_folder_explorer_column_widths(self, widths: dict[str, object]) -> None:
        self._update_graphics_settings(
            {"folder_explorer": {"column_widths": dict(widths or {})}}
        )

    def record_recent_text_color(self, color: str) -> None:
        self._host.app_preferences_controller.record_recent_text_color(
            color,
            host=self._host,
        )

    def set_graphics_shell_theme(self, theme_id: str) -> None:
        self._update_graphics_settings({"theme": {"theme_id": str(theme_id)}})

    def set_graphics_graph_follow_shell_theme(self, follow_shell_theme: bool) -> None:
        self._update_graphics_settings(
            {"graph_theme": {"follow_shell_theme": bool(follow_shell_theme)}}
        )

    def set_graphics_graph_theme(self, theme_id: str) -> None:
        self._update_graphics_settings(
            {
                "graph_theme": {
                    "follow_shell_theme": False,
                    "selected_theme_id": str(theme_id),
                }
            }
        )

    def set_graphics_tooltip_categories(self, categories: Any) -> None:
        self._host.app_preferences_controller.set_graphics_tooltip_categories(
            categories,
            host=self._host,
        )

    def set_graphics_tooltip_category_enabled(
        self,
        category: object,
        enabled: bool,
    ) -> None:
        self._host.app_preferences_controller.set_graphics_tooltip_category_enabled(
            category,
            enabled,
            host=self._host,
        )

    def set_graphics_expand_collision_avoidance(self, settings: Any) -> None:
        self._host.app_preferences_controller.set_graphics_expand_collision_avoidance(
            settings,
            host=self._host,
        )

    def request_open_graphics_settings(self) -> None:
        self._host.shell_host_presenter.show_graphics_settings_dialog()

    def request_open_scope_breadcrumb(self, node_id: str) -> bool:
        normalized_node_id = str(node_id).strip()
        return bool(
            self._host.search_scope_controller.navigate_scope(
                lambda: self._host.scene.navigate_scope_to(normalized_node_id)
            )
        )

    def request_switch_view(self, view_id: str) -> None:
        workspace_id = self._host.workspace_manager.active_workspace_id()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if workspace is None:
            return
        workspace.ensure_default_view()
        target_id = str(view_id).strip()
        if not target_id or target_id not in workspace.views or workspace.active_view_id == target_id:
            return
        self._host.search_scope_controller.remember_scope_camera()
        self._host.workspace_navigation_controller.switch_view(target_id)
        self._host.scene.sync_scope_with_active_view()
        self._host.search_scope_controller.restore_scope_camera()

    def request_move_view_tab(self, from_index: int, to_index: int) -> bool:
        return bool(self._host.workspace_navigation_controller.move_view(from_index, to_index))

    def request_rename_view(self, view_id: str) -> bool:
        return bool(self._host.workspace_navigation_controller.rename_view(view_id))

    def request_close_view(self, view_id: str) -> bool:
        return bool(self._host.workspace_navigation_controller.close_view(view_id))

    def request_export_view(self, view_id: str) -> bool:
        return bool(self._host.canvas_export_presenter.export_canvas_views([view_id]))

    def request_export_all_views(self) -> bool:
        return bool(self._host.canvas_export_presenter.export_canvas_views())

    def request_create_view(self) -> None: self._host.workspace_navigation_controller.create_view()

    def request_move_workspace_tab(self, from_index: int, to_index: int) -> bool:
        return bool(self._host.workspace_navigation_controller.move_workspace(from_index, to_index))

    def request_rename_workspace_by_id(self, workspace_id: str) -> bool:
        return bool(self._host.workspace_navigation_controller.rename_workspace_by_id(workspace_id))

    def request_close_workspace_by_id(self, workspace_id: str) -> bool:
        return bool(self._host.workspace_navigation_controller.close_workspace_by_id(workspace_id))

    def request_create_workspace(self) -> None: self._host.workspace_navigation_controller.create_workspace()

    def apply_graphics_preferences(self, graphics: Any) -> dict[str, Any]:
        canvas = graphics.get("canvas", {}) if isinstance(graphics, dict) else {}
        interaction = graphics.get("interaction", {}) if isinstance(graphics, dict) else {}
        shell = graphics.get("shell", {}) if isinstance(graphics, dict) else {}
        theme = graphics.get("theme", {}) if isinstance(graphics, dict) else {}
        typography = graphics.get("typography", {}) if isinstance(graphics, dict) else {}
        media_panel = graphics.get("media_panel") if isinstance(graphics, dict) else None
        folder_explorer = graphics.get("folder_explorer", {}) if isinstance(graphics, dict) else {}
        graph_theme = graphics.get("graph_theme", {}) if isinstance(graphics, dict) else {}
        plot_settings = (
            normalize_plot_settings(graphics.get("plot"))
            if isinstance(graphics, dict) and "plot" in graphics
            else {
                "lightweight_canvas": self._ui_state.lightweight_canvas,
                "plot_default_backend_per_type": copy.deepcopy(
                    self._ui_state.plot_default_backend_per_type
                ),
            }
        )

        changed = False
        canvas_import_mode = normalize_canvas_import_mode(
            interaction.get("canvas_import_mode", self._ui_state.canvas_import_mode)
        )
        show_grid = bool(canvas.get("show_grid", self._ui_state.show_grid))
        canvas_background_variant = normalize_canvas_background_variant(
            canvas.get("background_variant", self._ui_state.canvas_background_variant),
            self._ui_state.canvas_background_variant,
        )
        grid_style = normalize_grid_overlay_style(
            canvas.get("grid_style", self._ui_state.grid_style),
            self._ui_state.grid_style,
        )
        edge_crossing_style = normalize_edge_crossing_style(
            canvas.get("edge_crossing_style", self._ui_state.edge_crossing_style),
            self._ui_state.edge_crossing_style,
        )
        floating_toolbar_style = normalize_floating_toolbar_style(
            canvas.get("floating_toolbar_style", self._ui_state.floating_toolbar_style),
            self._ui_state.floating_toolbar_style,
        )
        floating_toolbar_size = normalize_floating_toolbar_size(
            canvas.get("floating_toolbar_size", self._ui_state.floating_toolbar_size),
            self._ui_state.floating_toolbar_size,
        )
        node_floating_toolbar_opens_on_hover = bool(
            canvas.get(
                "node_floating_toolbar_opens_on_hover",
                self._ui_state.node_floating_toolbar_opens_on_hover,
            )
        )
        selection_toolbar_mode = normalize_selection_toolbar_mode(
            canvas.get("selection_toolbar_mode", self._ui_state.selection_toolbar_mode),
            self._ui_state.selection_toolbar_mode,
        )
        selection_toolbar_minimal_menu_trigger = normalize_selection_toolbar_minimal_menu_trigger(
            canvas.get(
                "selection_toolbar_minimal_menu_trigger",
                self._ui_state.selection_toolbar_minimal_menu_trigger,
            ),
            self._ui_state.selection_toolbar_minimal_menu_trigger,
        )
        graph_label_pixel_size = normalize_graph_label_pixel_size(
            typography.get("graph_label_pixel_size", self._ui_state.graph_label_pixel_size),
            self._ui_state.graph_label_pixel_size,
        )
        graph_node_icon_pixel_size_override = normalize_graph_node_icon_pixel_size_override(
            typography.get("graph_node_icon_pixel_size_override", self._ui_state.graph_node_icon_pixel_size_override)
        )
        recent_text_colors = normalize_recent_text_colors(
            typography.get("recent_text_colors", self._ui_state.recent_text_colors)
        )
        node_title_icon_pixel_size = effective_graph_node_icon_pixel_size(
            graph_label_pixel_size,
            graph_node_icon_pixel_size_override,
        )
        media_panel_settings = (
            normalize_media_panel_settings(media_panel)
            if isinstance(graphics, dict) and "media_panel" in graphics
            else self.graphics_media_panel_defaults
        )
        folder_explorer_column_widths = (
            normalize_folder_explorer_column_widths(folder_explorer.get("column_widths"))
            if isinstance(folder_explorer, dict) and "column_widths" in folder_explorer
            else copy.deepcopy(self._ui_state.folder_explorer_column_widths)
        )
        lightweight_canvas = bool(plot_settings["lightweight_canvas"])
        plot_default_backend_per_type = dict(
            plot_settings["plot_default_backend_per_type"]
        )
        show_minimap = bool(canvas.get("show_minimap", self._ui_state.show_minimap))
        show_canvas_options_button = bool(
            canvas.get(
                "show_canvas_options_button",
                self._ui_state.show_canvas_options_button,
            )
        )
        show_port_labels = bool(canvas.get("show_port_labels", self._ui_state.show_port_labels))
        notched_ports = bool(canvas.get("notched_ports", self._ui_state.notched_ports))
        keep_expanded_node_width = bool(canvas.get("keep_expanded_node_width", self._ui_state.keep_expanded_node_width))
        node_elapsed_time_unit = normalize_node_elapsed_time_unit(
            canvas.get("node_elapsed_time_unit", self._ui_state.node_elapsed_time_unit),
            self._ui_state.node_elapsed_time_unit,
        )
        node_elapsed_time_visibility = normalize_node_elapsed_time_visibility(
            canvas.get(
                "node_elapsed_time_visibility",
                self._ui_state.node_elapsed_time_visibility,
            ),
            self._ui_state.node_elapsed_time_visibility,
        )
        node_comment_editor_default = normalize_node_comment_editor_default(
            canvas.get("node_comment_editor_default", self._ui_state.node_comment_editor_default),
            self._ui_state.node_comment_editor_default,
        )
        minimap_expanded = bool(
            canvas.get("minimap_expanded", self._host.search_scope_state.graphics_minimap_expanded)
        )
        node_shadow = bool(canvas.get("node_shadow", self._ui_state.node_shadow))
        shadow_strength = int(canvas.get("shadow_strength", self._ui_state.shadow_strength))
        shadow_softness = int(canvas.get("shadow_softness", self._ui_state.shadow_softness))
        shadow_offset = int(canvas.get("shadow_offset", self._ui_state.shadow_offset))
        if "expand_collision_avoidance" in interaction:
            expand_collision_avoidance = normalize_expand_collision_avoidance_settings(
                interaction.get("expand_collision_avoidance")
            )
        else:
            expand_collision_avoidance = copy.deepcopy(self._expand_collision_avoidance)
        tab_strip_density = str(shell.get("tab_strip_density", self._ui_state.tab_strip_density))
        status_bar_layout = normalize_status_bar_layout(
            shell.get("status_bar_layout", self._ui_state.status_bar_layout),
            self._ui_state.status_bar_layout,
        )
        show_fps_telemetry = bool(
            shell.get("show_fps_telemetry", self._ui_state.show_fps_telemetry)
        )
        property_pane_variant = normalize_property_pane_variant(
            shell.get("property_pane_variant", self._ui_state.property_pane_variant),
            self._ui_state.property_pane_variant,
        )
        passive_node_library_display_mode = normalize_passive_node_library_display_mode(
            shell.get(
                "passive_node_library_display_mode",
                self._ui_state.passive_node_library_display_mode,
            ),
            self._ui_state.passive_node_library_display_mode,
        )
        shell_panel_collapsed = normalize_shell_panel_collapsed(
            shell.get("panel_collapsed", self._ui_state.shell_panel_collapsed)
        )
        tooltip_categories = (
            normalize_tooltip_category_preferences(shell.get("tooltip_categories"))
            if "tooltip_categories" in shell
            else copy.deepcopy(self._ui_state.graphics_tooltip_categories)
        )
        active_theme_id = self._host.shell_host_presenter.apply_theme(
            theme.get("theme_id", self._ui_state.active_theme_id)
        )
        follow_shell_theme = graph_theme.get("follow_shell_theme")
        if not isinstance(follow_shell_theme, bool):
            follow_shell_theme = bool(DEFAULT_GRAPHICS_SETTINGS["graph_theme"]["follow_shell_theme"])
        custom_graph_themes = serialize_custom_graph_themes(graph_theme.get("custom_themes"))
        selected_graph_theme_id = resolve_graph_theme_id(
            graph_theme.get(
                "selected_theme_id",
                DEFAULT_GRAPHICS_SETTINGS["graph_theme"]["selected_theme_id"],
            ),
            custom_themes=custom_graph_themes,
        )
        normalized_graph_theme = {
            "follow_shell_theme": bool(follow_shell_theme),
            "selected_theme_id": selected_graph_theme_id,
            "custom_themes": custom_graph_themes,
        }
        previous_graph_theme_id = self._host.graph_theme_bridge.theme_id

        if self._ui_state.canvas_import_mode != canvas_import_mode:
            self._ui_state.canvas_import_mode = canvas_import_mode
            changed = True
        if self._ui_state.show_grid != show_grid:
            self._ui_state.show_grid = show_grid
            changed = True
        if self._ui_state.canvas_background_variant != canvas_background_variant:
            self._ui_state.canvas_background_variant = canvas_background_variant
            changed = True
        if self._ui_state.grid_style != grid_style:
            self._ui_state.grid_style = grid_style
            changed = True
        if self._ui_state.edge_crossing_style != edge_crossing_style:
            self._ui_state.edge_crossing_style = edge_crossing_style
            changed = True
        if self._ui_state.floating_toolbar_style != floating_toolbar_style:
            self._ui_state.floating_toolbar_style = floating_toolbar_style
            changed = True
        if self._ui_state.floating_toolbar_size != floating_toolbar_size:
            self._ui_state.floating_toolbar_size = floating_toolbar_size
            changed = True
        if (
            self._ui_state.node_floating_toolbar_opens_on_hover
            != node_floating_toolbar_opens_on_hover
        ):
            self._ui_state.node_floating_toolbar_opens_on_hover = node_floating_toolbar_opens_on_hover
            changed = True
        if self._ui_state.selection_toolbar_mode != selection_toolbar_mode:
            self._ui_state.selection_toolbar_mode = selection_toolbar_mode
            changed = True
        if (
            self._ui_state.selection_toolbar_minimal_menu_trigger
            != selection_toolbar_minimal_menu_trigger
        ):
            self._ui_state.selection_toolbar_minimal_menu_trigger = (
                selection_toolbar_minimal_menu_trigger
            )
            changed = True
        if self._ui_state.graph_label_pixel_size != graph_label_pixel_size:
            self._ui_state.graph_label_pixel_size = graph_label_pixel_size
            changed = True
        if self._ui_state.graph_node_icon_pixel_size_override != graph_node_icon_pixel_size_override:
            self._ui_state.graph_node_icon_pixel_size_override = graph_node_icon_pixel_size_override
            changed = True
        if self._ui_state.node_title_icon_pixel_size != node_title_icon_pixel_size:
            self._ui_state.node_title_icon_pixel_size = node_title_icon_pixel_size
            changed = True
        if self._ui_state.recent_text_colors != recent_text_colors:
            self._ui_state.recent_text_colors = list(recent_text_colors)
            changed = True
        if (
            self._ui_state.media_panel_default_show_title
            != media_panel_settings["show_title"]
        ):
            self._ui_state.media_panel_default_show_title = bool(
                media_panel_settings["show_title"]
            )
            changed = True
        if (
            self._ui_state.media_panel_default_show_frame
            != media_panel_settings["show_frame"]
        ):
            self._ui_state.media_panel_default_show_frame = bool(
                media_panel_settings["show_frame"]
            )
            changed = True
        if (
            self._ui_state.media_panel_autoplay_animations
            != media_panel_settings["autoplay_animations"]
        ):
            self._ui_state.media_panel_autoplay_animations = bool(
                media_panel_settings["autoplay_animations"]
            )
            changed = True
        if (
            self._ui_state.media_panel_source_input_exposed
            != media_panel_settings["source_input_exposed"]
        ):
            self._ui_state.media_panel_source_input_exposed = bool(
                media_panel_settings["source_input_exposed"]
            )
            changed = True
        if self._ui_state.folder_explorer_column_widths != folder_explorer_column_widths:
            self._ui_state.folder_explorer_column_widths = copy.deepcopy(folder_explorer_column_widths)
            changed = True
        if self._ui_state.lightweight_canvas != lightweight_canvas:
            self._ui_state.lightweight_canvas = lightweight_canvas
            changed = True
        if self._ui_state.plot_default_backend_per_type != plot_default_backend_per_type:
            self._ui_state.plot_default_backend_per_type = copy.deepcopy(
                plot_default_backend_per_type
            )
            changed = True
        if self._ui_state.show_minimap != show_minimap:
            self._ui_state.show_minimap = show_minimap
            changed = True
        if self._ui_state.show_canvas_options_button != show_canvas_options_button:
            self._ui_state.show_canvas_options_button = show_canvas_options_button
            changed = True
        if self._ui_state.show_port_labels != show_port_labels:
            self._ui_state.show_port_labels = show_port_labels
            changed = True
        if self._ui_state.notched_ports != notched_ports:
            self._ui_state.notched_ports = notched_ports
            changed = True
        if self._ui_state.keep_expanded_node_width != keep_expanded_node_width:
            self._ui_state.keep_expanded_node_width = keep_expanded_node_width
            changed = True
        if self._ui_state.node_elapsed_time_unit != node_elapsed_time_unit:
            self._ui_state.node_elapsed_time_unit = node_elapsed_time_unit
            changed = True
        if self._ui_state.node_elapsed_time_visibility != node_elapsed_time_visibility:
            self._ui_state.node_elapsed_time_visibility = node_elapsed_time_visibility
            changed = True
        if self._ui_state.node_comment_editor_default != node_comment_editor_default:
            self._ui_state.node_comment_editor_default = node_comment_editor_default
            changed = True
        if self._host.search_scope_state.graphics_minimap_expanded != minimap_expanded:
            self._host.search_scope_state.graphics_minimap_expanded = minimap_expanded
            changed = True
        if self._ui_state.node_shadow != node_shadow:
            self._ui_state.node_shadow = node_shadow
            changed = True
        if self._ui_state.shadow_strength != shadow_strength:
            self._ui_state.shadow_strength = shadow_strength
            changed = True
        if self._ui_state.shadow_softness != shadow_softness:
            self._ui_state.shadow_softness = shadow_softness
            changed = True
        if self._ui_state.shadow_offset != shadow_offset:
            self._ui_state.shadow_offset = shadow_offset
            changed = True
        if self._expand_collision_avoidance != expand_collision_avoidance:
            self._expand_collision_avoidance = copy.deepcopy(expand_collision_avoidance)
            changed = True
        if self._ui_state.tab_strip_density != tab_strip_density:
            self._ui_state.tab_strip_density = tab_strip_density
            changed = True
        if self._ui_state.status_bar_layout != status_bar_layout:
            self._ui_state.status_bar_layout = status_bar_layout
            changed = True
        if self._ui_state.show_fps_telemetry != show_fps_telemetry:
            self._ui_state.show_fps_telemetry = show_fps_telemetry
            changed = True
        if self._ui_state.property_pane_variant != property_pane_variant:
            self._ui_state.property_pane_variant = property_pane_variant
            changed = True
        if self._ui_state.passive_node_library_display_mode != passive_node_library_display_mode:
            self._ui_state.passive_node_library_display_mode = passive_node_library_display_mode
            changed = True
        if self._ui_state.shell_panel_collapsed != shell_panel_collapsed:
            self._ui_state.shell_panel_collapsed = copy.deepcopy(shell_panel_collapsed)
            changed = True
        self._host.shell_inspector_presenter.set_property_pane_variant(property_pane_variant)
        if self._ui_state.graphics_tooltip_categories != tooltip_categories:
            self._ui_state.graphics_tooltip_categories = copy.deepcopy(tooltip_categories)
            changed = True
        tooltip_manager = getattr(self._host, "tooltip_manager", None)
        if tooltip_manager is not None:
            tooltip_manager.set_tooltip_categories(tooltip_categories)
        if self._ui_state.active_theme_id != active_theme_id:
            self._ui_state.active_theme_id = active_theme_id
            changed = True
        self._host.graph_theme_bridge.apply_settings(
            shell_theme_id=active_theme_id,
            graph_theme_settings=normalized_graph_theme,
        )
        if previous_graph_theme_id != self._host.graph_theme_bridge.theme_id:
            changed = True

        self._host.search_scope_controller.set_snap_to_grid_enabled(
            bool(interaction.get("snap_to_grid", self._host.search_scope_state.snap_to_grid_enabled)),
            persist=False,
        )
        if changed:
            self._host.graphics_preferences_changed.emit()

        return {
            "canvas": {
                "background_variant": str(self._ui_state.canvas_background_variant),
                "show_grid": bool(self._ui_state.show_grid),
                "grid_style": str(self._ui_state.grid_style),
                "edge_crossing_style": str(self._ui_state.edge_crossing_style),
                "show_canvas_options_button": bool(
                    self._ui_state.show_canvas_options_button
                ),
                "show_minimap": bool(self._ui_state.show_minimap),
                "show_port_labels": bool(self._ui_state.show_port_labels),
                "notched_ports": bool(self._ui_state.notched_ports),
                "keep_expanded_node_width": bool(self._ui_state.keep_expanded_node_width),
                "node_elapsed_time_unit": str(self._ui_state.node_elapsed_time_unit),
                "node_elapsed_time_visibility": str(self._ui_state.node_elapsed_time_visibility),
                "node_comment_editor_default": str(self._ui_state.node_comment_editor_default),
                "minimap_expanded": bool(self._host.search_scope_state.graphics_minimap_expanded),
                "node_shadow": bool(self._ui_state.node_shadow),
                "shadow_strength": int(self._ui_state.shadow_strength),
                "shadow_softness": int(self._ui_state.shadow_softness),
                "shadow_offset": int(self._ui_state.shadow_offset),
                "floating_toolbar_style": str(self._ui_state.floating_toolbar_style),
                "floating_toolbar_size": str(self._ui_state.floating_toolbar_size),
                "node_floating_toolbar_opens_on_hover": bool(
                    self._ui_state.node_floating_toolbar_opens_on_hover
                ),
                "selection_toolbar_mode": str(self._ui_state.selection_toolbar_mode),
                "selection_toolbar_minimal_menu_trigger": str(
                    self._ui_state.selection_toolbar_minimal_menu_trigger
                ),
            },
            "interaction": {
                "snap_to_grid": bool(self._host.search_scope_state.snap_to_grid_enabled),
                "canvas_import_mode": self._ui_state.canvas_import_mode,
                "expand_collision_avoidance": copy.deepcopy(self._expand_collision_avoidance),
            },
            "shell": {
                "tab_strip_density": str(self._ui_state.tab_strip_density),
                "status_bar_layout": str(self._ui_state.status_bar_layout),
                "show_fps_telemetry": bool(self._ui_state.show_fps_telemetry),
                "property_pane_variant": str(self._ui_state.property_pane_variant),
                "passive_node_library_display_mode": str(
                    self._ui_state.passive_node_library_display_mode
                ),
                "panel_collapsed": copy.deepcopy(self._ui_state.shell_panel_collapsed),
                "tooltip_categories": copy.deepcopy(self._ui_state.graphics_tooltip_categories),
            },
            "theme": {
                "theme_id": str(self._ui_state.active_theme_id),
            },
            "typography": {
                "graph_label_pixel_size": int(self._ui_state.graph_label_pixel_size),
                "graph_node_icon_pixel_size_override": self._ui_state.graph_node_icon_pixel_size_override,
                "recent_text_colors": list(self._ui_state.recent_text_colors),
            },
            "media_panel": self.graphics_media_panel_defaults,
            "folder_explorer": {
                "column_widths": self.graphics_folder_explorer_column_widths,
            },
            "plot": {
                "lightweight_canvas": self.graphics_lightweight_canvas,
                "plot_default_backend_per_type": self.graphics_plot_default_backend_per_type,
            },
            "graph_theme": {
                "follow_shell_theme": bool(follow_shell_theme),
                "selected_theme_id": selected_graph_theme_id,
                "custom_themes": custom_graph_themes,
            },
        }


__all__ = ["ShellWorkspacePresenter"]
