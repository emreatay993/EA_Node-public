from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import pyqtProperty, pyqtSignal, pyqtSlot
from ea_node_editor.app_preferences import (
    effective_graph_node_icon_pixel_size,
    normalize_folder_explorer_column_widths,
    normalize_media_panel_settings,
    normalize_graph_node_icon_pixel_size_override,
    normalize_node_comment_editor_default,
    normalize_node_elapsed_time_unit,
    normalize_node_elapsed_time_visibility,
    normalize_status_bar_layout,
    normalize_plot_settings,
)
from ea_node_editor.settings import DEFAULT_GRAPH_LABEL_PIXEL_SIZE, DEFAULT_GRAPHICS_SETTINGS
from ea_node_editor.text_style import normalize_recent_text_colors
from ea_node_editor.ui.shell.tooltip_policy import (
    TOOLTIP_CATEGORY_NAMES,
    TOOLTIP_CATEGORY_GENERAL,
    normalize_tooltip_category_name,
    normalize_tooltip_category_preferences,
    tooltip_category_effectively_visible,
)
from ea_node_editor.ui_qml.bridge_runtime import (
    copy_dict as _copy_dict,
    source_attr as _source_attr,
)

if TYPE_CHECKING:
    pass


def _tooltip_category_visibility_payload(
    *,
    tooltip_categories: object,
) -> dict[str, bool]:
    return {
        category: tooltip_category_effectively_visible(
            category,
            tooltip_categories=tooltip_categories,
        )
        for category in TOOLTIP_CATEGORY_NAMES
    }


class GraphicsPreferencesProps:
    """Graphics/preference read-only projections (graphics_* properties and
    their notify signals). Properties only - computation belongs in the
    preference sources or visible_scene_service."""

    graphics_preferences_changed = pyqtSignal()
    snap_to_grid_changed = pyqtSignal()

    def _handle_graphics_preferences_changed(self) -> None:
        self.graphics_preferences_changed.emit()

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_minimap_expanded(self) -> bool:
        return bool(_source_attr(self._session_state, "graphics_minimap_expanded", True))

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_grid(self) -> bool:
        return bool(_source_attr(self._graphics_source, "graphics_show_grid", True))

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_canvas_import_mode(self) -> str:
        return str(_source_attr(self._graphics_source, "graphics_canvas_import_mode", "automatic"))

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_canvas_background_variant(self) -> str:
        return str(_source_attr(self._graphics_source, "graphics_canvas_background_variant", "theme"))

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_grid_style(self) -> str:
        return str(_source_attr(self._graphics_source, "graphics_grid_style", "lines"))

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_edge_crossing_style(self) -> str:
        return str(_source_attr(self._graphics_source, "graphics_edge_crossing_style", "none"))

    @pyqtProperty(int, notify=graphics_preferences_changed)
    def graphics_graph_label_pixel_size(self) -> int:
        return int(
            _source_attr(
                self._graphics_source,
                "graphics_graph_label_pixel_size",
                DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
            )
        )

    @pyqtProperty("QVariant", notify=graphics_preferences_changed)
    def graphics_graph_node_icon_pixel_size_override(self) -> int | None:
        value = _source_attr(
            self._graphics_source,
            "graphics_graph_node_icon_pixel_size_override",
            None,
        )
        return normalize_graph_node_icon_pixel_size_override(value)

    @pyqtProperty(int, notify=graphics_preferences_changed)
    def graphics_node_title_icon_pixel_size(self) -> int:
        value = _source_attr(
            self._graphics_source,
            "graphics_node_title_icon_pixel_size",
            None,
        )
        return effective_graph_node_icon_pixel_size(
            self.graphics_graph_label_pixel_size,
            self.graphics_graph_node_icon_pixel_size_override if value is None else value,
        )

    @pyqtProperty("QVariantList", notify=graphics_preferences_changed)
    def graphics_recent_text_colors(self) -> list[str]:
        value = _source_attr(
            self._graphics_source,
            "graphics_recent_text_colors",
            DEFAULT_GRAPHICS_SETTINGS["typography"]["recent_text_colors"],
        )
        return normalize_recent_text_colors(value)

    @pyqtProperty("QVariantMap", notify=graphics_preferences_changed)
    def graphics_media_panel_defaults(self) -> dict[str, bool]:
        value = _source_attr(
            self._graphics_source,
            "graphics_media_panel_defaults",
            DEFAULT_GRAPHICS_SETTINGS["media_panel"],
        )
        return normalize_media_panel_settings(value)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_media_panel_default_show_title(self) -> bool:
        value = _source_attr(
            self._graphics_source,
            "graphics_media_panel_default_show_title",
            self.graphics_media_panel_defaults["show_title"],
        )
        return (
            bool(value)
            if isinstance(value, bool)
            else self.graphics_media_panel_defaults["show_title"]
        )

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_media_panel_default_show_frame(self) -> bool:
        value = _source_attr(
            self._graphics_source,
            "graphics_media_panel_default_show_frame",
            self.graphics_media_panel_defaults["show_frame"],
        )
        return (
            bool(value)
            if isinstance(value, bool)
            else self.graphics_media_panel_defaults["show_frame"]
        )

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_media_panel_autoplay_animations(self) -> bool:
        value = _source_attr(
            self._graphics_source,
            "graphics_media_panel_autoplay_animations",
            self.graphics_media_panel_defaults["autoplay_animations"],
        )
        return (
            bool(value)
            if isinstance(value, bool)
            else self.graphics_media_panel_defaults["autoplay_animations"]
        )

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_media_panel_source_input_exposed(self) -> bool:
        value = _source_attr(
            self._graphics_source,
            "graphics_media_panel_source_input_exposed",
            self.graphics_media_panel_defaults["source_input_exposed"],
        )
        return (
            bool(value)
            if isinstance(value, bool)
            else self.graphics_media_panel_defaults["source_input_exposed"]
        )

    @pyqtProperty("QVariantMap", notify=graphics_preferences_changed)
    def graphics_folder_explorer_column_widths(self) -> dict[str, int]:
        value = _source_attr(
            self._graphics_source,
            "graphics_folder_explorer_column_widths",
            DEFAULT_GRAPHICS_SETTINGS["folder_explorer"]["column_widths"],
        )
        return normalize_folder_explorer_column_widths(value)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_minimap(self) -> bool:
        return bool(_source_attr(self._graphics_source, "graphics_show_minimap", True))

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_canvas_options_button(self) -> bool:
        return bool(
            _source_attr(self._graphics_source, "graphics_show_canvas_options_button", True)
        )

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_port_labels(self) -> bool:
        return bool(_source_attr(self._graphics_source, "graphics_show_port_labels", True))

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_notched_ports(self) -> bool:
        return bool(
            _source_attr(
                self._graphics_source,
                "graphics_notched_ports",
                DEFAULT_GRAPHICS_SETTINGS["canvas"]["notched_ports"],
            )
        )

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_node_elapsed_time_unit(self) -> str:
        value = _source_attr(
            self._graphics_source,
            "graphics_node_elapsed_time_unit",
            DEFAULT_GRAPHICS_SETTINGS["canvas"]["node_elapsed_time_unit"],
        )
        return normalize_node_elapsed_time_unit(value)

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_node_elapsed_time_visibility(self) -> str:
        value = _source_attr(
            self._graphics_source,
            "graphics_node_elapsed_time_visibility",
            DEFAULT_GRAPHICS_SETTINGS["canvas"]["node_elapsed_time_visibility"],
        )
        return normalize_node_elapsed_time_visibility(value)

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_node_comment_editor_default(self) -> str:
        value = _source_attr(
            self._graphics_source,
            "graphics_node_comment_editor_default",
            DEFAULT_GRAPHICS_SETTINGS["canvas"]["node_comment_editor_default"],
        )
        return normalize_node_comment_editor_default(value)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def selected_run_preview_before_run(self) -> bool:
        getter = getattr(
            self._app_preferences_source,
            "selected_run_preview_before_run",
            None,
        )
        return bool(getter() if callable(getter) else getter if getter is not None else True)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_tooltips(self) -> bool:
        return bool(self.tooltip_category_enabled(TOOLTIP_CATEGORY_GENERAL))

    @pyqtProperty("QVariantMap", notify=graphics_preferences_changed)
    def graphics_tooltip_categories(self) -> dict[str, bool]:
        value = _source_attr(
            self._graphics_source,
            "graphics_tooltip_categories",
            None,
        )
        if isinstance(value, dict):
            return dict(value)
        return normalize_tooltip_category_preferences(
            DEFAULT_GRAPHICS_SETTINGS["shell"]["tooltip_categories"]
        )

    @pyqtProperty("QVariantMap", notify=graphics_preferences_changed)
    def graphics_tooltip_category_visibility(self) -> dict[str, bool]:
        value = _source_attr(
            self._graphics_source,
            "graphics_tooltip_category_visibility",
            None,
        )
        if isinstance(value, dict):
            return dict(value)
        return _tooltip_category_visibility_payload(
            tooltip_categories=self.graphics_tooltip_categories
        )

    @pyqtSlot(str, result=bool)
    def tooltip_category_enabled(self, category: str) -> bool:
        enabled = getattr(self._graphics_source, "tooltip_category_enabled", None)
        if callable(enabled):
            return bool(enabled(category))
        return bool(
            self.graphics_tooltip_category_visibility.get(
                normalize_tooltip_category_name(category), False
            )
        )

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_node_shadow(self) -> bool:
        return bool(_source_attr(self._graphics_source, "graphics_node_shadow", True))

    @pyqtProperty(int, notify=graphics_preferences_changed)
    def graphics_shadow_strength(self) -> int:
        return int(_source_attr(self._graphics_source, "graphics_shadow_strength", 70))

    @pyqtProperty(int, notify=graphics_preferences_changed)
    def graphics_shadow_softness(self) -> int:
        return int(_source_attr(self._graphics_source, "graphics_shadow_softness", 50))

    @pyqtProperty(int, notify=graphics_preferences_changed)
    def graphics_shadow_offset(self) -> int:
        return int(_source_attr(self._graphics_source, "graphics_shadow_offset", 4))

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_status_bar_layout(self) -> str:
        return normalize_status_bar_layout(
            _source_attr(self._graphics_source, "graphics_status_bar_layout", "option_1")
        )

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_fps_telemetry(self) -> bool:
        return bool(_source_attr(self._graphics_source, "graphics_show_fps_telemetry", True))

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_floating_toolbar_style(self) -> str:
        return str(
            _source_attr(
                self._graphics_source,
                "graphics_floating_toolbar_style",
                "compact_pill",
            )
        )

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_floating_toolbar_size(self) -> str:
        return str(
            _source_attr(
                self._graphics_source,
                "graphics_floating_toolbar_size",
                "small",
            )
        )

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_node_floating_toolbar_opens_on_hover(self) -> bool:
        return bool(
            _source_attr(
                self._graphics_source,
                "graphics_node_floating_toolbar_opens_on_hover",
                False,
            )
        )

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_selection_toolbar_mode(self) -> str:
        return str(
            _source_attr(
                self._graphics_source,
                "graphics_selection_toolbar_mode",
                "minimal_ghost_menu",
            )
        )

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_selection_toolbar_minimal_menu_trigger(self) -> str:
        return str(
            _source_attr(
                self._graphics_source,
                "graphics_selection_toolbar_minimal_menu_trigger",
                "click_affordance",
            )
        )

    @pyqtProperty("QVariantMap", notify=graphics_preferences_changed)
    def graphics_expand_collision_avoidance(self) -> dict[str, Any]:
        default = DEFAULT_GRAPHICS_SETTINGS["interaction"]["expand_collision_avoidance"]
        value = _source_attr(
            self._graphics_source,
            "graphics_expand_collision_avoidance",
            default,
        )
        return _copy_dict(value)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_lightweight_canvas(self) -> bool:
        default = bool(DEFAULT_GRAPHICS_SETTINGS["plot"]["lightweight_canvas"])
        value = _source_attr(
            self._graphics_source,
            "graphics_lightweight_canvas",
            default,
        )
        return bool(value) if isinstance(value, bool) else bool(default)

    @pyqtProperty("QVariantMap", notify=graphics_preferences_changed)
    def graphics_plot_default_backend_per_type(self) -> dict[str, str]:
        default = DEFAULT_GRAPHICS_SETTINGS["plot"]["plot_default_backend_per_type"]
        value = _source_attr(
            self._graphics_source,
            "graphics_plot_default_backend_per_type",
            default,
        )
        return dict(normalize_plot_settings({"plot_default_backend_per_type": value})["plot_default_backend_per_type"])

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def active_theme_id(self) -> str:
        return str(_source_attr(self._graphics_source, "active_theme_id", "stitch_dark"))

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_graph_follow_shell_theme(self) -> bool:
        default = bool(DEFAULT_GRAPHICS_SETTINGS["graph_theme"]["follow_shell_theme"])
        return bool(_source_attr(self._graphics_source, "graphics_graph_follow_shell_theme", default))

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_selected_graph_theme_id(self) -> str:
        default = str(DEFAULT_GRAPHICS_SETTINGS["graph_theme"]["selected_theme_id"])
        return str(_source_attr(self._graphics_source, "graphics_selected_graph_theme_id", default))

    @pyqtProperty(bool, notify=snap_to_grid_changed)
    def snap_to_grid_enabled(self) -> bool:
        return bool(_source_attr(self._session_state, "snap_to_grid_enabled", False))

    @pyqtProperty(float, notify=snap_to_grid_changed)
    def snap_grid_size(self) -> float:
        return float(self._snap_grid_size)
