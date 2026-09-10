from __future__ import annotations

import copy
import json
import math
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ea_node_editor.common.coercions import normalize_path_text
from ea_node_editor.common.payload_tools import write_json_atomic
from ea_node_editor.graph_theme_defaults import DEFAULT_GRAPH_THEME_ID
from ea_node_editor.settings import (
    APP_PREFERENCES_KIND,
    APP_PREFERENCES_VERSION,
    DEFAULT_ADDON_SETTINGS,
    DEFAULT_ADDON_STATE,
    DEFAULT_APP_PREFERENCES,
    DEFAULT_CANVAS_BACKGROUND_VARIANT,
    DEFAULT_CANVAS_IMPORT_MODE,
    DEFAULT_EDGE_CROSSING_STYLE,
    DEFAULT_ENGINEERING_VIEWER_SETTINGS,
    DEFAULT_EXPAND_COLLISION_AVOIDANCE_GAP_PRESET,
    DEFAULT_EXPAND_COLLISION_AVOIDANCE_LOCAL_RADIUS_PRESET,
    DEFAULT_EXPAND_COLLISION_AVOIDANCE_RADIUS_MODE,
    DEFAULT_EXPAND_COLLISION_AVOIDANCE_SCOPE,
    DEFAULT_EXPAND_COLLISION_AVOIDANCE_STRATEGY,
    DEFAULT_FOLDER_EXPLORER_SETTINGS,
    DEFAULT_FLOATING_TOOLBAR_SIZE,
    DEFAULT_FLOATING_TOOLBAR_STYLE,
    DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    DEFAULT_STATUS_BAR_LAYOUT,
    DEFAULT_GRID_OVERLAY_STYLE,
    DEFAULT_GRAPHICS_SETTINGS,
    DEFAULT_MEDIA_PANEL_SETTINGS,
    DEFAULT_NODE_COMMENT_EDITOR_DEFAULT,
    DEFAULT_NODE_ELAPSED_TIME_UNIT,
    DEFAULT_NODE_ELAPSED_TIME_VISIBILITY,
    DEFAULT_PASSIVE_NODE_LIBRARY_DISPLAY_MODE,
    DEFAULT_PLOT_SETTINGS,
    DEFAULT_PLUGIN_SETTINGS,
    DEFAULT_PYTHON_RUNTIME_SETTINGS,
    DEFAULT_PROPERTY_PANE_VARIANT,
    DEFAULT_SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER,
    DEFAULT_SELECTION_TOOLBAR_MODE,
    DEFAULT_SHELL_PANEL_COLLAPSED,
    DEFAULT_SOURCE_IMPORT_MODE,
    DEFAULT_SOURCE_IMPORT_SETTINGS,
    DEFAULT_SELECTED_RUN_SETTINGS,
    DEFAULT_SOLUTION_SETTINGS,
    EDGE_CROSSING_STYLE_CHOICES,
    EXPAND_COLLISION_AVOIDANCE_GAP_PRESET_CHOICES,
    EXPAND_COLLISION_AVOIDANCE_LOCAL_RADIUS_PRESET_CHOICES,
    EXPAND_COLLISION_AVOIDANCE_RADIUS_MODE_CHOICES,
    EXPAND_COLLISION_AVOIDANCE_SCOPE_CHOICES,
    EXPAND_COLLISION_AVOIDANCE_STRATEGY_CHOICES,
    FOLDER_EXPLORER_COLUMN_WIDTH_KEYS,
    FOLDER_EXPLORER_COLUMN_WIDTH_MAX,
    FOLDER_EXPLORER_COLUMN_WIDTH_MIN,
    FLOATING_TOOLBAR_SIZE_CHOICES,
    FLOATING_TOOLBAR_STYLE_CHOICES,
    GRAPH_LABEL_PIXEL_SIZE_MAX,
    GRAPH_LABEL_PIXEL_SIZE_MIN,
    GRAPH_NODE_ICON_PIXEL_SIZE_MAX,
    NODE_ELAPSED_TIME_UNIT_CHOICES,
    NODE_ELAPSED_TIME_VISIBILITY_CHOICES,
    NODE_COMMENT_EDITOR_DEFAULT_CHOICES,
    STATUS_BAR_LAYOUT_CHOICES,
    GRID_OVERLAY_STYLE_CHOICES,
    CANVAS_BACKGROUND_VARIANT_CHOICES,
    CANVAS_IMPORT_MODE_CHOICES,
    PASSIVE_NODE_LIBRARY_DISPLAY_MODE_CHOICES,
    PROPERTY_PANE_VARIANT_CHOICES,
    SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER_CHOICES,
    SELECTION_TOOLBAR_MODE_CHOICES,
    SOURCE_IMPORT_MODE_CHOICES,
    TAB_STRIP_DENSITY_CHOICES,
    app_preferences_path,
)
from ea_node_editor.text_style import normalize_recent_text_colors
from ea_node_editor.ui.graph_theme.registry import (
    is_known_graph_theme_id,
    resolve_graph_theme_id,
    serialize_custom_graph_themes,
)
from ea_node_editor.ui.shell.tooltip_policy import (
    normalize_tooltip_category_preferences,
)
from ea_node_editor.ui.theme.registry import DEFAULT_THEME_ID, is_known_theme_id, resolve_theme_id


_STATUS_BAR_LAYOUT_VALUES = {
    str(choice[0]).strip().lower() for choice in STATUS_BAR_LAYOUT_CHOICES
}
_GRID_OVERLAY_STYLE_VALUES = {
    str(choice[0]).strip().lower() for choice in GRID_OVERLAY_STYLE_CHOICES
}
_CANVAS_BACKGROUND_VARIANT_VALUES = {
    str(choice[0]).strip().lower() for choice in CANVAS_BACKGROUND_VARIANT_CHOICES
}
_FLOATING_TOOLBAR_STYLE_VALUES = {
    str(choice[0]).strip().lower() for choice in FLOATING_TOOLBAR_STYLE_CHOICES
}
_FLOATING_TOOLBAR_SIZE_VALUES = {
    str(choice[0]).strip().lower() for choice in FLOATING_TOOLBAR_SIZE_CHOICES
}
_SELECTION_TOOLBAR_MODE_VALUES = {
    str(choice[0]).strip().lower() for choice in SELECTION_TOOLBAR_MODE_CHOICES
}
_SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER_VALUES = {
    str(choice[0]).strip().lower()
    for choice in SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER_CHOICES
}
_NODE_ELAPSED_TIME_UNIT_VALUES = {
    str(choice[0]).strip().lower() for choice in NODE_ELAPSED_TIME_UNIT_CHOICES
}
_NODE_ELAPSED_TIME_VISIBILITY_VALUES = {
    str(choice[0]).strip().lower() for choice in NODE_ELAPSED_TIME_VISIBILITY_CHOICES
}
_NODE_COMMENT_EDITOR_DEFAULT_VALUES = {
    str(choice[0]).strip().lower() for choice in NODE_COMMENT_EDITOR_DEFAULT_CHOICES
}
_EDGE_CROSSING_STYLE_VALUES = {
    str(choice[0]).strip().lower() for choice in EDGE_CROSSING_STYLE_CHOICES
}
_EXPAND_COLLISION_AVOIDANCE_STRATEGY_VALUES = {
    str(choice[0]).strip().lower() for choice in EXPAND_COLLISION_AVOIDANCE_STRATEGY_CHOICES
}
_EXPAND_COLLISION_AVOIDANCE_SCOPE_VALUES = {
    str(choice[0]).strip().lower() for choice in EXPAND_COLLISION_AVOIDANCE_SCOPE_CHOICES
}
_EXPAND_COLLISION_AVOIDANCE_RADIUS_MODE_VALUES = {
    str(choice[0]).strip().lower() for choice in EXPAND_COLLISION_AVOIDANCE_RADIUS_MODE_CHOICES
}
_EXPAND_COLLISION_AVOIDANCE_LOCAL_RADIUS_PRESET_VALUES = {
    str(choice[0]).strip().lower() for choice in EXPAND_COLLISION_AVOIDANCE_LOCAL_RADIUS_PRESET_CHOICES
}
_EXPAND_COLLISION_AVOIDANCE_GAP_PRESET_VALUES = {
    str(choice[0]).strip().lower() for choice in EXPAND_COLLISION_AVOIDANCE_GAP_PRESET_CHOICES
}
_SOURCE_IMPORT_MODE_VALUES = {
    str(choice[0]).strip().lower() for choice in SOURCE_IMPORT_MODE_CHOICES
}
NODE_LIBRARY_USAGE_HISTORY_LIMIT = 64


def normalize_node_library_usage(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    normalized = [type_id.strip() for type_id in value if isinstance(type_id, str)]
    return [type_id for type_id in normalized if type_id][-NODE_LIBRARY_USAGE_HISTORY_LIMIT:]


_TAB_STRIP_DENSITY_VALUES = {str(choice[0]).strip().lower() for choice in TAB_STRIP_DENSITY_CHOICES}
_PROPERTY_PANE_VARIANT_VALUES = {
    str(choice[0]).strip().lower() for choice in PROPERTY_PANE_VARIANT_CHOICES
}
_PASSIVE_NODE_LIBRARY_DISPLAY_MODE_VALUES = {
    str(choice[0]).strip().lower() for choice in PASSIVE_NODE_LIBRARY_DISPLAY_MODE_CHOICES
}
_AUTO_PLOT_BACKEND_ID = "auto"
_V1_PLOT_TYPES = {
    "line",
    "scatter",
    "bar",
    "histogram",
    "heatmap",
    "contour",
    "surface",
    "point_cloud",
    "streamlines",
}


def _normalize_plot_type(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _default_plot_backend_registry() -> Any | None:
    try:
        from ea_node_editor.execution.plot_backend import create_plot_backend_registry
    except Exception:  # noqa: BLE001
        return None
    try:
        return create_plot_backend_registry()
    except Exception:  # noqa: BLE001
        return None


def _plot_backend_supports_plot_type(backend_registry: Any | None, backend_id: str, plot_type: str) -> bool:
    if backend_registry is None:
        return True
    try:
        record = backend_registry.get_record(backend_id)
    except Exception:  # noqa: BLE001
        return False
    capabilities = getattr(record, "capabilities", ())
    return any(str(getattr(capability, "plot_type", "") or "") == plot_type for capability in capabilities)


def default_app_preferences_document() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_APP_PREFERENCES)


def normalize_graph_theme_settings(payload: Any) -> dict[str, Any]:
    defaults = DEFAULT_GRAPHICS_SETTINGS["graph_theme"]
    if not isinstance(payload, Mapping):
        return copy.deepcopy(defaults)

    normalized = copy.deepcopy(defaults)
    normalized["follow_shell_theme"] = _normalize_bool(
        payload.get("follow_shell_theme"),
        defaults["follow_shell_theme"],
    )
    normalized["custom_themes"] = serialize_custom_graph_themes(payload.get("custom_themes"))
    normalized["selected_theme_id"] = _normalize_graph_theme_id(
        payload.get("selected_theme_id"),
        defaults["selected_theme_id"],
        custom_themes=normalized["custom_themes"],
    )
    return normalized


def normalize_expand_collision_avoidance_settings(payload: Any) -> dict[str, Any]:
    defaults = DEFAULT_GRAPHICS_SETTINGS["interaction"]["expand_collision_avoidance"]
    if not isinstance(payload, Mapping):
        return copy.deepcopy(defaults)

    normalized = copy.deepcopy(defaults)
    normalized["enabled"] = _normalize_bool(payload.get("enabled"), defaults["enabled"])
    normalized["strategy"] = _normalize_choice(
        payload.get("strategy"),
        defaults["strategy"],
        _EXPAND_COLLISION_AVOIDANCE_STRATEGY_VALUES,
        DEFAULT_EXPAND_COLLISION_AVOIDANCE_STRATEGY,
    )
    normalized["scope"] = _normalize_choice(
        payload.get("scope"),
        defaults["scope"],
        _EXPAND_COLLISION_AVOIDANCE_SCOPE_VALUES,
        DEFAULT_EXPAND_COLLISION_AVOIDANCE_SCOPE,
    )
    normalized["radius_mode"] = _normalize_choice(
        payload.get("radius_mode"),
        defaults["radius_mode"],
        _EXPAND_COLLISION_AVOIDANCE_RADIUS_MODE_VALUES,
        DEFAULT_EXPAND_COLLISION_AVOIDANCE_RADIUS_MODE,
    )
    normalized["local_radius_preset"] = _normalize_choice(
        payload.get("local_radius_preset"),
        defaults["local_radius_preset"],
        _EXPAND_COLLISION_AVOIDANCE_LOCAL_RADIUS_PRESET_VALUES,
        DEFAULT_EXPAND_COLLISION_AVOIDANCE_LOCAL_RADIUS_PRESET,
    )
    normalized["gap_preset"] = _normalize_choice(
        payload.get("gap_preset"),
        defaults["gap_preset"],
        _EXPAND_COLLISION_AVOIDANCE_GAP_PRESET_VALUES,
        DEFAULT_EXPAND_COLLISION_AVOIDANCE_GAP_PRESET,
    )
    normalized["animate"] = _normalize_bool(payload.get("animate"), defaults["animate"])
    return normalized


def normalize_media_panel_settings(payload: Any) -> dict[str, bool]:
    defaults = DEFAULT_MEDIA_PANEL_SETTINGS
    if not isinstance(payload, Mapping):
        return copy.deepcopy(defaults)

    normalized = copy.deepcopy(defaults)
    normalized["show_title"] = _normalize_bool(payload.get("show_title"), defaults["show_title"])
    normalized["show_frame"] = _normalize_bool(payload.get("show_frame"), defaults["show_frame"])
    normalized["autoplay_animations"] = _normalize_bool(
        payload.get("autoplay_animations"),
        defaults["autoplay_animations"],
    )
    normalized["source_input_exposed"] = _normalize_bool(
        payload.get("source_input_exposed"),
        defaults["source_input_exposed"],
    )
    return normalized


def normalize_plot_default_backend_per_type(
    payload: Any,
    *,
    registry: Any | None = None,
) -> dict[str, str]:
    defaults = DEFAULT_PLOT_SETTINGS["plot_default_backend_per_type"]
    normalized = copy.deepcopy(defaults)
    if not isinstance(payload, Mapping):
        return normalized

    backend_registry = registry
    if backend_registry is None:
        backend_registry = _default_plot_backend_registry()
    backend_ids = set(getattr(backend_registry, "backend_ids", ()))
    for raw_plot_type, raw_backend_id in payload.items():
        plot_type = _normalize_plot_type(raw_plot_type)
        if plot_type not in _V1_PLOT_TYPES:
            continue
        backend_id = str(raw_backend_id or "").strip()
        if not backend_id or backend_id.lower() == _AUTO_PLOT_BACKEND_ID:
            continue
        if backend_ids and backend_id not in backend_ids:
            continue
        if not _plot_backend_supports_plot_type(backend_registry, backend_id, plot_type):
            continue
        normalized[plot_type] = backend_id
    return normalized


def normalize_plot_settings(payload: Any) -> dict[str, Any]:
    defaults = DEFAULT_PLOT_SETTINGS
    if not isinstance(payload, Mapping):
        return copy.deepcopy(defaults)

    normalized = copy.deepcopy(defaults)
    normalized["lightweight_canvas"] = _normalize_bool(
        payload.get("lightweight_canvas"),
        defaults["lightweight_canvas"],
    )
    normalized["plot_default_backend_per_type"] = normalize_plot_default_backend_per_type(
        payload.get("plot_default_backend_per_type")
    )
    return normalized


def normalize_engineering_viewer_settings(payload: Any) -> dict[str, float]:
    default_angle = float(
        DEFAULT_ENGINEERING_VIEWER_SETTINGS["tangent_selection_angle_degrees"]
    )
    if not isinstance(payload, Mapping):
        return {"tangent_selection_angle_degrees": default_angle}
    value = payload.get("tangent_selection_angle_degrees")
    if isinstance(value, bool):
        angle = default_angle
    else:
        try:
            angle = float(value)
        except (TypeError, ValueError):
            angle = default_angle
    if not math.isfinite(angle):
        angle = default_angle
    return {"tangent_selection_angle_degrees": min(90.0, max(0.0, angle))}


def engineering_viewer_tangent_selection_angle(document: Any) -> float:
    normalized = normalize_app_preferences_document(document)
    return float(
        normalized["graphics"]["engineering_viewer"][
            "tangent_selection_angle_degrees"
        ]
    )


def normalize_folder_explorer_column_widths(payload: Any) -> dict[str, int]:
    if not isinstance(payload, Mapping):
        return {}

    normalized: dict[str, int] = {}
    for key in FOLDER_EXPLORER_COLUMN_WIDTH_KEYS:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            width = value
        elif isinstance(value, float) and math.isfinite(value):
            width = int(round(value))
        else:
            continue
        normalized[key] = max(
            FOLDER_EXPLORER_COLUMN_WIDTH_MIN,
            min(width, FOLDER_EXPLORER_COLUMN_WIDTH_MAX),
        )
    return normalized


def normalize_folder_explorer_settings(payload: Any) -> dict[str, Any]:
    defaults = DEFAULT_FOLDER_EXPLORER_SETTINGS
    if not isinstance(payload, Mapping):
        return copy.deepcopy(defaults)

    normalized = copy.deepcopy(defaults)
    normalized["column_widths"] = normalize_folder_explorer_column_widths(
        payload.get("column_widths")
    )
    return normalized


def normalize_shell_panel_collapsed(payload: Any) -> dict[str, bool]:
    defaults = DEFAULT_SHELL_PANEL_COLLAPSED
    if not isinstance(payload, Mapping):
        return copy.deepcopy(defaults)

    normalized = copy.deepcopy(defaults)
    for key, default in defaults.items():
        normalized[key] = _normalize_bool(payload.get(key), default)
    return normalized


def normalize_graphics_settings(payload: Any) -> dict[str, Any]:
    defaults = DEFAULT_GRAPHICS_SETTINGS
    if not isinstance(payload, Mapping):
        return copy.deepcopy(defaults)

    canvas_payload = payload.get("canvas")
    interaction_payload = payload.get("interaction")
    shell_payload = payload.get("shell")
    theme_payload = payload.get("theme")
    typography_payload = payload.get("typography")
    media_panel_payload = payload.get("media_panel")
    plot_payload = payload.get("plot")
    engineering_viewer_payload = payload.get("engineering_viewer")
    folder_explorer_payload = payload.get("folder_explorer")
    graph_theme_payload = payload.get("graph_theme")

    normalized = copy.deepcopy(defaults)
    if isinstance(canvas_payload, Mapping):
        normalized["canvas"]["background_variant"] = normalize_canvas_background_variant(
            canvas_payload.get("background_variant"),
            defaults["canvas"]["background_variant"],
        )
        normalized["canvas"]["show_grid"] = _normalize_bool(
            canvas_payload.get("show_grid"),
            defaults["canvas"]["show_grid"],
        )
        normalized["canvas"]["grid_style"] = normalize_grid_overlay_style(
            canvas_payload.get("grid_style"),
            defaults["canvas"]["grid_style"],
        )
        normalized["canvas"]["edge_crossing_style"] = normalize_edge_crossing_style(
            canvas_payload.get("edge_crossing_style"),
            defaults["canvas"]["edge_crossing_style"],
        )
        normalized["canvas"]["show_canvas_options_button"] = _normalize_bool(
            canvas_payload.get("show_canvas_options_button"),
            defaults["canvas"]["show_canvas_options_button"],
        )
        normalized["canvas"]["show_minimap"] = _normalize_bool(
            canvas_payload.get("show_minimap"),
            defaults["canvas"]["show_minimap"],
        )
        normalized["canvas"]["show_port_labels"] = _normalize_bool(
            canvas_payload.get("show_port_labels"),
            defaults["canvas"]["show_port_labels"],
        )
        normalized["canvas"]["notched_ports"] = _normalize_bool(
            canvas_payload.get("notched_ports"),
            defaults["canvas"]["notched_ports"],
        )
        normalized["canvas"]["keep_expanded_node_width"] = _normalize_bool(
            canvas_payload.get("keep_expanded_node_width"),
            defaults["canvas"]["keep_expanded_node_width"],
        )
        normalized["canvas"]["minimap_expanded"] = _normalize_bool(
            canvas_payload.get("minimap_expanded"),
            defaults["canvas"]["minimap_expanded"],
        )
        normalized["canvas"]["node_shadow"] = _normalize_bool(
            canvas_payload.get("node_shadow"),
            defaults["canvas"]["node_shadow"],
        )
        normalized["canvas"]["shadow_strength"] = _normalize_int(
            canvas_payload.get("shadow_strength"),
            defaults["canvas"]["shadow_strength"],
            0,
            100,
        )
        normalized["canvas"]["shadow_softness"] = _normalize_int(
            canvas_payload.get("shadow_softness"),
            defaults["canvas"]["shadow_softness"],
            0,
            100,
        )
        normalized["canvas"]["shadow_offset"] = _normalize_int(
            canvas_payload.get("shadow_offset"),
            defaults["canvas"]["shadow_offset"],
            0,
            20,
        )
        normalized["canvas"]["floating_toolbar_style"] = normalize_floating_toolbar_style(
            canvas_payload.get("floating_toolbar_style"),
            defaults["canvas"]["floating_toolbar_style"],
        )
        normalized["canvas"]["floating_toolbar_size"] = normalize_floating_toolbar_size(
            canvas_payload.get("floating_toolbar_size"),
            defaults["canvas"]["floating_toolbar_size"],
        )
        normalized["canvas"]["node_floating_toolbar_opens_on_hover"] = (
            _normalize_bool(
                canvas_payload.get("node_floating_toolbar_opens_on_hover"),
                defaults["canvas"]["node_floating_toolbar_opens_on_hover"],
            )
        )
        normalized["canvas"]["selection_toolbar_mode"] = normalize_selection_toolbar_mode(
            canvas_payload.get("selection_toolbar_mode"),
            defaults["canvas"]["selection_toolbar_mode"],
        )
        normalized["canvas"]["selection_toolbar_minimal_menu_trigger"] = (
            normalize_selection_toolbar_minimal_menu_trigger(
                canvas_payload.get("selection_toolbar_minimal_menu_trigger"),
                defaults["canvas"]["selection_toolbar_minimal_menu_trigger"],
            )
        )
        normalized["canvas"]["node_elapsed_time_unit"] = normalize_node_elapsed_time_unit(
            canvas_payload.get("node_elapsed_time_unit"),
            defaults["canvas"]["node_elapsed_time_unit"],
        )
        normalized["canvas"]["node_elapsed_time_visibility"] = normalize_node_elapsed_time_visibility(
            canvas_payload.get("node_elapsed_time_visibility"),
            defaults["canvas"]["node_elapsed_time_visibility"],
        )
        normalized["canvas"]["node_comment_editor_default"] = normalize_node_comment_editor_default(
            canvas_payload.get("node_comment_editor_default"),
            defaults["canvas"]["node_comment_editor_default"],
        )
    if isinstance(interaction_payload, Mapping):
        normalized["interaction"]["canvas_import_mode"] = normalize_canvas_import_mode(
            interaction_payload.get("canvas_import_mode")
        )
        normalized["interaction"]["snap_to_grid"] = _normalize_bool(
            interaction_payload.get("snap_to_grid"),
            defaults["interaction"]["snap_to_grid"],
        )
        normalized["interaction"]["expand_collision_avoidance"] = (
            normalize_expand_collision_avoidance_settings(
                interaction_payload.get("expand_collision_avoidance")
            )
        )
    if isinstance(shell_payload, Mapping):
        normalized["shell"]["tab_strip_density"] = _normalize_tab_strip_density(
            shell_payload.get("tab_strip_density"),
            defaults["shell"]["tab_strip_density"],
        )
        normalized["shell"]["status_bar_layout"] = normalize_status_bar_layout(
            shell_payload.get("status_bar_layout"),
            defaults["shell"]["status_bar_layout"],
        )
        normalized["shell"]["show_fps_telemetry"] = _normalize_bool(
            shell_payload.get("show_fps_telemetry"),
            defaults["shell"]["show_fps_telemetry"],
        )
        normalized["shell"]["property_pane_variant"] = normalize_property_pane_variant(
            shell_payload.get("property_pane_variant"),
            defaults["shell"]["property_pane_variant"],
        )
        normalized["shell"]["passive_node_library_display_mode"] = (
            normalize_passive_node_library_display_mode(
                shell_payload.get("passive_node_library_display_mode"),
                defaults["shell"]["passive_node_library_display_mode"],
            )
        )
        normalized["shell"]["panel_collapsed"] = normalize_shell_panel_collapsed(
            shell_payload.get("panel_collapsed")
        )
        normalized["shell"]["tooltip_categories"] = normalize_tooltip_category_preferences(
            shell_payload.get("tooltip_categories")
        )
        normalized["shell"]["node_library_usage"] = normalize_node_library_usage(
            shell_payload.get("node_library_usage")
        )
    if isinstance(theme_payload, Mapping):
        normalized["theme"]["theme_id"] = _normalize_theme_id(
            theme_payload.get("theme_id"),
            defaults["theme"]["theme_id"],
        )
    if isinstance(typography_payload, Mapping):
        graph_label_pixel_size = normalize_graph_label_pixel_size(
            typography_payload.get("graph_label_pixel_size"),
            defaults["typography"]["graph_label_pixel_size"],
        )
        graph_node_icon_pixel_size_override = normalize_graph_node_icon_pixel_size_override(
            typography_payload.get("graph_node_icon_pixel_size_override")
        )
        normalized["typography"]["graph_label_pixel_size"] = graph_label_pixel_size
        normalized["typography"]["graph_node_icon_pixel_size_override"] = graph_node_icon_pixel_size_override
        normalized["typography"]["recent_text_colors"] = normalize_recent_text_colors(
            typography_payload.get("recent_text_colors")
        )
    normalized["media_panel"] = normalize_media_panel_settings(media_panel_payload)
    normalized["plot"] = normalize_plot_settings(plot_payload)
    normalized["engineering_viewer"] = normalize_engineering_viewer_settings(
        engineering_viewer_payload
    )
    normalized["folder_explorer"] = normalize_folder_explorer_settings(folder_explorer_payload)
    normalized["graph_theme"] = normalize_graph_theme_settings(graph_theme_payload)
    return normalized


def normalize_source_import_settings(payload: Any) -> dict[str, Any]:
    defaults = DEFAULT_SOURCE_IMPORT_SETTINGS
    if not isinstance(payload, Mapping):
        return copy.deepcopy(defaults)

    normalized = copy.deepcopy(defaults)
    normalized["default_mode"] = normalize_source_import_mode(
        payload.get("default_mode"),
        defaults["default_mode"],
    )
    return normalized


def normalize_selected_run_settings(payload: Any) -> dict[str, Any]:
    defaults = DEFAULT_SELECTED_RUN_SETTINGS
    if not isinstance(payload, Mapping):
        return copy.deepcopy(defaults)

    normalized = copy.deepcopy(defaults)
    normalized["preview_before_run"] = _normalize_bool(
        payload.get("preview_before_run"),
        defaults["preview_before_run"],
    )
    return normalized


def normalize_solution_settings(payload: Any) -> dict[str, str]:
    default_mode = DEFAULT_SOLUTION_SETTINGS["default_mode"]
    if not isinstance(payload, Mapping):
        return {"default_mode": default_mode}
    mode = str(payload.get("default_mode", default_mode)).strip().lower()
    return {"default_mode": mode if mode in {"auto", "manual"} else default_mode}


def normalize_addon_state(payload: Any) -> dict[str, bool]:
    defaults = DEFAULT_ADDON_STATE
    if not isinstance(payload, Mapping):
        return copy.deepcopy(defaults)

    normalized = copy.deepcopy(defaults)
    normalized["enabled"] = _normalize_bool(payload.get("enabled"), defaults["enabled"])
    normalized["pending_restart"] = _normalize_bool(
        payload.get("pending_restart"),
        defaults["pending_restart"],
    )
    return normalized


def normalize_addon_settings(payload: Any) -> dict[str, Any]:
    defaults = DEFAULT_ADDON_SETTINGS
    if not isinstance(payload, Mapping):
        return copy.deepcopy(defaults)

    normalized = copy.deepcopy(defaults)
    states_payload = payload.get("states")
    normalized_states: dict[str, dict[str, bool]] = {}
    if isinstance(states_payload, Mapping):
        for raw_addon_id, raw_state in states_payload.items():
            addon_id = _normalize_preference_key(raw_addon_id)
            if not addon_id:
                continue
            normalized_states[addon_id] = normalize_addon_state(raw_state)
    normalized["states"] = normalized_states
    return normalized


def normalize_plugin_settings(payload: Any) -> dict[str, Any]:
    del payload
    return copy.deepcopy(DEFAULT_PLUGIN_SETTINGS)


def normalize_python_runtime_settings(payload: Any) -> dict[str, str]:
    normalized = copy.deepcopy(DEFAULT_PYTHON_RUNTIME_SETTINGS)
    if isinstance(payload, Mapping):
        normalized["default_executable"] = normalize_path_text(
            payload.get("default_executable")
        )
    return normalized


def normalize_app_preferences_document(payload: Any) -> dict[str, Any]:
    normalized = default_app_preferences_document()
    if not isinstance(payload, Mapping):
        return normalized

    kind = str(payload.get("kind", "")).strip()
    try:
        version = int(payload.get("version", 0) or 0)
    except (TypeError, ValueError):
        return normalized

    if kind != APP_PREFERENCES_KIND:
        return normalized
    if version in {5, 6, 7}:
        payload = copy.deepcopy(dict(payload))
        graphics = payload.get("graphics")
        if isinstance(graphics, Mapping):
            graphics = copy.deepcopy(dict(graphics))
            if "media_panel" not in graphics and "image_nodes" in graphics:
                graphics["media_panel"] = graphics.get("image_nodes")
            graphics.pop("image_nodes", None)
            payload["graphics"] = graphics
        payload["version"] = APP_PREFERENCES_VERSION
        if version in {5, 6}:
            payload["python_runtime"] = copy.deepcopy(DEFAULT_PYTHON_RUNTIME_SETTINGS)
        version = APP_PREFERENCES_VERSION
    if version != APP_PREFERENCES_VERSION:
        return normalized

    normalized["graphics"] = normalize_graphics_settings(payload.get("graphics"))
    normalized["addons"] = normalize_addon_settings(payload.get("addons"))
    normalized["plugins"] = normalize_plugin_settings(payload.get("plugins"))
    normalized["source_import"] = normalize_source_import_settings(payload.get("source_import"))
    normalized["selected_run"] = normalize_selected_run_settings(payload.get("selected_run"))
    normalized["solution"] = normalize_solution_settings(payload.get("solution"))
    normalized["python_runtime"] = normalize_python_runtime_settings(
        payload.get("python_runtime")
    )
    return normalized


class AppPreferencesStore:
    def __init__(
        self,
        *,
        path_provider: Callable[[], Path] | None = None,
    ) -> None:
        self._path_provider = path_provider or app_preferences_path

    def load_document(self) -> dict[str, Any]:
        path = self._path_provider()
        if not path.exists():
            return default_app_preferences_document()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return default_app_preferences_document()
        normalized = normalize_app_preferences_document(payload)
        try:
            needs_migration = (
                isinstance(payload, Mapping)
                and str(payload.get("kind", "")).strip() == APP_PREFERENCES_KIND
                and int(payload.get("version", 0) or 0) in {5, 6, 7}
            )
        except (TypeError, ValueError):
            needs_migration = False
        return self.persist_document(normalized) if needs_migration else normalized

    def persist_document(self, document: Any) -> dict[str, Any]:
        normalized = normalize_app_preferences_document(document)
        write_json_atomic(self._path_provider(), normalized)
        return normalized


def addon_state(document: Any, addon_id: Any) -> dict[str, bool]:
    normalized = normalize_app_preferences_document(document)
    normalized_addon_id = _normalize_preference_key(addon_id)
    if not normalized_addon_id:
        return copy.deepcopy(DEFAULT_ADDON_STATE)
    stored_state = normalized["addons"]["states"].get(normalized_addon_id)
    if stored_state is None:
        return copy.deepcopy(DEFAULT_ADDON_STATE)
    return copy.deepcopy(stored_state)


def set_addon_state(
    document: Any,
    addon_id: Any,
    *,
    enabled: Any,
    pending_restart: Any,
) -> dict[str, Any]:
    normalized_addon_id = _normalize_preference_key(addon_id)
    if not normalized_addon_id:
        raise ValueError("addon_id must be a non-empty string")
    normalized = normalize_app_preferences_document(document)
    normalized["addons"]["states"][normalized_addon_id] = normalize_addon_state(
        {
            "enabled": enabled,
            "pending_restart": pending_restart,
        }
    )
    return normalized


def resolve_startup_theme_id(
    *,
    store: AppPreferencesStore | None = None,
    graphics: Any | None = None,
) -> str:
    try:
        resolved_graphics = normalize_graphics_settings(graphics)
        if graphics is None:
            document = (store or AppPreferencesStore()).load_document()
            resolved_graphics = normalize_graphics_settings(document.get("graphics"))
    except Exception:  # noqa: BLE001
        return DEFAULT_THEME_ID

    theme = resolved_graphics.get("theme", {})
    if not isinstance(theme, Mapping):
        return DEFAULT_THEME_ID
    return resolve_theme_id(theme.get("theme_id", DEFAULT_THEME_ID))


def _normalize_bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _normalize_preference_key(value: Any) -> str:
    return str(value).strip()


def _normalize_int(value: Any, default: int, lo: int, hi: int) -> int:
    if isinstance(value, int) and lo <= value <= hi:
        return value
    return default


def normalize_graph_label_pixel_size(
    value: Any,
    default: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(GRAPH_LABEL_PIXEL_SIZE_MIN, min(value, GRAPH_LABEL_PIXEL_SIZE_MAX))
    return default


def normalize_graph_node_icon_pixel_size_override(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return max(GRAPH_LABEL_PIXEL_SIZE_MIN, min(value, GRAPH_NODE_ICON_PIXEL_SIZE_MAX))
    return None


def effective_graph_node_icon_pixel_size(
    graph_label_pixel_size: Any,
    graph_node_icon_pixel_size_override: Any,
) -> int:
    normalized_override = normalize_graph_node_icon_pixel_size_override(
        graph_node_icon_pixel_size_override
    )
    if normalized_override is not None:
        return normalized_override
    return normalize_graph_label_pixel_size(graph_label_pixel_size)


def _normalize_theme_id(value: Any, default: str) -> str:
    normalized = str(value).strip()
    if is_known_theme_id(normalized):
        return normalized
    if is_known_theme_id(default):
        return default
    return DEFAULT_THEME_ID


def _normalize_graph_theme_id(value: Any, default: str, *, custom_themes: Any = None) -> str:
    normalized = str(value).strip()
    if is_known_graph_theme_id(normalized, custom_themes=custom_themes):
        return normalized
    resolved_default = resolve_graph_theme_id(default, custom_themes=custom_themes)
    if is_known_graph_theme_id(resolved_default, custom_themes=custom_themes):
        return resolved_default
    return DEFAULT_GRAPH_THEME_ID


def _normalize_tab_strip_density(value: Any, default: str) -> str:
    normalized = str(value).strip().lower()
    if normalized in _TAB_STRIP_DENSITY_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _TAB_STRIP_DENSITY_VALUES:
        return resolved_default
    return str(DEFAULT_GRAPHICS_SETTINGS["shell"]["tab_strip_density"])


def _normalize_choice(value: Any, default: str, choices: set[str], fallback: str) -> str:
    normalized = str(value).strip().lower()
    if normalized in choices:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in choices:
        return resolved_default
    return fallback


def normalize_status_bar_layout(value: Any, default: str = DEFAULT_STATUS_BAR_LAYOUT) -> str:
    normalized = str(value).strip().lower()
    if normalized in _STATUS_BAR_LAYOUT_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _STATUS_BAR_LAYOUT_VALUES:
        return resolved_default
    return DEFAULT_STATUS_BAR_LAYOUT


def normalize_grid_overlay_style(value: Any, default: str = DEFAULT_GRID_OVERLAY_STYLE) -> str:
    normalized = str(value).strip().lower()
    if normalized in _GRID_OVERLAY_STYLE_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _GRID_OVERLAY_STYLE_VALUES:
        return resolved_default
    return DEFAULT_GRID_OVERLAY_STYLE


def normalize_canvas_background_variant(
    value: Any, default: str = DEFAULT_CANVAS_BACKGROUND_VARIANT
) -> str:
    normalized = str(value).strip().lower()
    if normalized in _CANVAS_BACKGROUND_VARIANT_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _CANVAS_BACKGROUND_VARIANT_VALUES:
        return resolved_default
    return DEFAULT_CANVAS_BACKGROUND_VARIANT


def normalize_floating_toolbar_style(
    value: Any, default: str = DEFAULT_FLOATING_TOOLBAR_STYLE
) -> str:
    normalized = str(value).strip().lower()
    if normalized in _FLOATING_TOOLBAR_STYLE_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _FLOATING_TOOLBAR_STYLE_VALUES:
        return resolved_default
    return DEFAULT_FLOATING_TOOLBAR_STYLE


def normalize_floating_toolbar_size(
    value: Any, default: str = DEFAULT_FLOATING_TOOLBAR_SIZE
) -> str:
    normalized = str(value).strip().lower()
    if normalized in _FLOATING_TOOLBAR_SIZE_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _FLOATING_TOOLBAR_SIZE_VALUES:
        return resolved_default
    return DEFAULT_FLOATING_TOOLBAR_SIZE


def normalize_selection_toolbar_mode(
    value: Any, default: str = DEFAULT_SELECTION_TOOLBAR_MODE
) -> str:
    normalized = str(value).strip().lower()
    if normalized in _SELECTION_TOOLBAR_MODE_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _SELECTION_TOOLBAR_MODE_VALUES:
        return resolved_default
    return DEFAULT_SELECTION_TOOLBAR_MODE


def normalize_selection_toolbar_minimal_menu_trigger(
    value: Any,
    default: str = DEFAULT_SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER,
) -> str:
    normalized = str(value).strip().lower()
    if normalized in _SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER_VALUES:
        return resolved_default
    return DEFAULT_SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER


def normalize_node_elapsed_time_unit(
    value: Any,
    default: str = DEFAULT_NODE_ELAPSED_TIME_UNIT,
) -> str:
    normalized = str(value).strip().lower()
    aliases = {
        "ms": "milliseconds",
        "millisecond": "milliseconds",
        "milliseconds": "milliseconds",
        "s": "seconds",
        "sec": "seconds",
        "secs": "seconds",
        "second": "seconds",
        "seconds": "seconds",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in _NODE_ELAPSED_TIME_UNIT_VALUES:
        return normalized
    resolved_default = aliases.get(str(default).strip().lower(), str(default).strip().lower())
    if resolved_default in _NODE_ELAPSED_TIME_UNIT_VALUES:
        return resolved_default
    return DEFAULT_NODE_ELAPSED_TIME_UNIT


def normalize_node_elapsed_time_visibility(
    value: Any,
    default: str = DEFAULT_NODE_ELAPSED_TIME_VISIBILITY,
) -> str:
    normalized = str(value).strip().lower()
    if normalized in _NODE_ELAPSED_TIME_VISIBILITY_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _NODE_ELAPSED_TIME_VISIBILITY_VALUES:
        return resolved_default
    return DEFAULT_NODE_ELAPSED_TIME_VISIBILITY


def normalize_canvas_import_mode(value: Any) -> str:
    normalized = str(value).strip().lower()
    return (
        normalized
        if normalized in {choice[0] for choice in CANVAS_IMPORT_MODE_CHOICES}
        else DEFAULT_CANVAS_IMPORT_MODE
    )


def normalize_node_comment_editor_default(
    value: Any,
    default: str = DEFAULT_NODE_COMMENT_EDITOR_DEFAULT,
) -> str:
    normalized = str(value).strip().lower()
    aliases = {
        "popover": "canvas_popover",
        "canvas": "canvas_popover",
        "canvas-popover": "canvas_popover",
        "canvas_popover": "canvas_popover",
        "inspector": "inspector",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in _NODE_COMMENT_EDITOR_DEFAULT_VALUES:
        return normalized
    resolved_default = aliases.get(str(default).strip().lower(), str(default).strip().lower())
    if resolved_default in _NODE_COMMENT_EDITOR_DEFAULT_VALUES:
        return resolved_default
    return DEFAULT_NODE_COMMENT_EDITOR_DEFAULT


def normalize_edge_crossing_style(value: Any, default: str = DEFAULT_EDGE_CROSSING_STYLE) -> str:
    normalized = str(value).strip().lower()
    if normalized in _EDGE_CROSSING_STYLE_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _EDGE_CROSSING_STYLE_VALUES:
        return resolved_default
    return DEFAULT_EDGE_CROSSING_STYLE


def normalize_property_pane_variant(
    value: Any, default: str = DEFAULT_PROPERTY_PANE_VARIANT
) -> str:
    normalized = str(value).strip().lower()
    if normalized in _PROPERTY_PANE_VARIANT_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _PROPERTY_PANE_VARIANT_VALUES:
        return resolved_default
    return DEFAULT_PROPERTY_PANE_VARIANT


def normalize_passive_node_library_display_mode(
    value: Any,
    default: str = DEFAULT_PASSIVE_NODE_LIBRARY_DISPLAY_MODE,
) -> str:
    normalized = str(value).strip().lower()
    if normalized in _PASSIVE_NODE_LIBRARY_DISPLAY_MODE_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _PASSIVE_NODE_LIBRARY_DISPLAY_MODE_VALUES:
        return resolved_default
    return DEFAULT_PASSIVE_NODE_LIBRARY_DISPLAY_MODE


def normalize_source_import_mode(value: Any, default: str = DEFAULT_SOURCE_IMPORT_MODE) -> str:
    normalized = str(value).strip().lower()
    if normalized in _SOURCE_IMPORT_MODE_VALUES:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _SOURCE_IMPORT_MODE_VALUES:
        return resolved_default
    return DEFAULT_SOURCE_IMPORT_MODE


__all__ = [
    "normalize_canvas_import_mode",
    "AppPreferencesStore",
    "addon_state",
    "default_app_preferences_document",
    "engineering_viewer_tangent_selection_angle",
    "normalize_app_preferences_document",
    "normalize_addon_settings",
    "normalize_addon_state",
    "normalize_canvas_background_variant",
    "normalize_edge_crossing_style",
    "normalize_engineering_viewer_settings",
    "normalize_expand_collision_avoidance_settings",
    "normalize_folder_explorer_column_widths",
    "normalize_folder_explorer_settings",
    "normalize_floating_toolbar_size",
    "normalize_floating_toolbar_style",
    "normalize_graph_label_pixel_size",
    "effective_graph_node_icon_pixel_size",
    "normalize_graph_node_icon_pixel_size_override",
    "normalize_graph_theme_settings",
    "normalize_grid_overlay_style",
    "normalize_node_elapsed_time_unit",
    "normalize_node_elapsed_time_visibility",
    "normalize_node_comment_editor_default",
    "normalize_status_bar_layout",
    "normalize_selection_toolbar_minimal_menu_trigger",
    "normalize_selection_toolbar_mode",
    "normalize_graphics_settings",
    "normalize_media_panel_settings",
    "normalize_plot_default_backend_per_type",
    "normalize_plot_settings",
    "normalize_passive_node_library_display_mode",
    "normalize_plugin_settings",
    "normalize_property_pane_variant",
    "normalize_python_runtime_settings",
    "normalize_source_import_mode",
    "normalize_source_import_settings",
    "normalize_selected_run_settings",
    "normalize_solution_settings",
    "normalize_shell_panel_collapsed",
    "resolve_startup_theme_id",
    "set_addon_state",
]
