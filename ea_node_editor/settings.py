from __future__ import annotations

import os
from pathlib import Path

from ea_node_editor.graph_theme_defaults import DEFAULT_GRAPH_THEME_ID
from ea_node_editor.ui.shell.tooltip_policy import default_tooltip_category_preferences

APP_NAME = "COREX Node Editor"
APP_ID = "com.corex.node_editor"
APP_DATA_DIR_NAME = "COREX_Node_Editor"
LEGACY_APP_DATA_DIR_NAME = "EA_Node_Editor"
PROJECT_EXTENSION = ".cxproj"
PROJECT_DATA_DIR_SUFFIX = ".data"
PROJECT_ARTIFACT_STORE_METADATA_KEY = "artifact_store"
PROJECT_MANAGED_WORKSPACES_DIRNAME = "workspaces"
PROJECT_MANAGED_NODES_DIRNAME = "nodes"
PROJECT_NODE_INPUTS_DIRNAME = "in"
PROJECT_NODE_OUTPUTS_DIRNAME = "out"
PROJECT_NODE_TEMP_DIRNAME = "tmp"
PROJECT_ARTIFACT_SESSION_STAGING_DIRNAME = "project_artifact_staging"
SCHEMA_VERSION = 5
AUTOSAVE_INTERVAL_MS = 30_000
APP_PREFERENCES_KIND = "ea-node-editor/app-preferences"
APP_PREFERENCES_VERSION = 8

DEFAULT_WORKFLOW_SETTINGS = {
    "general": {
        "project_name": "",
        "author": "",
        "description": "",
    },
    "solver_config": {
        "enable_parallel": True,
        "thread_count": 8,
        "memory_limit_gb": 12,
    },
    "environment": {
        "python_path": "",
        "working_directory": "",
    },
    "plugins": {
        "enabled": [],
    },
    "logging": {
        "level": "info",
        "capture_console": True,
    },
}

DEFAULT_UI_STATE = {
    "script_editor": {
        "visible": False,
        "floating": False,
    },
    "passive_style_presets": {
        "node_presets": [],
        "edge_presets": [],
    },
}

TAB_STRIP_DENSITY_CHOICES = (
    ("compact", "Compact"),
    ("regular", "Regular"),
)

PROPERTY_PANE_VARIANT_CHOICES = (
    ("smart_groups", "Smart Groups"),
    ("accordion_cards", "Accordion Cards"),
    ("palette", "Palette"),
)
DEFAULT_PROPERTY_PANE_VARIANT = "smart_groups"
PASSIVE_NODE_LIBRARY_DISPLAY_MODE_CHOICES = (
    ("text", "Text"),
    ("icon", "Icon"),
    ("text_icon", "Text + Icon"),
)
DEFAULT_PASSIVE_NODE_LIBRARY_DISPLAY_MODE = "text"
DEFAULT_SHELL_PANEL_COLLAPSED = {
    "node_library": False,
    "property_pane": False,
    "output_panel": False,
}

STATUS_BAR_LAYOUT_CHOICES = (
    ("option_1", "Option 1"),
    ("option_2", "Option 2"),
)
GRID_OVERLAY_STYLE_CHOICES = (
    ("lines", "Lines"),
    ("points", "Points"),
)
CANVAS_BACKGROUND_VARIANT_CHOICES = (
    ("theme", "Follow Theme"),
    ("dark", "Dark"),
    ("white", "White"),
)
CANVAS_IMPORT_MODE_CHOICES = (
    ("automatic", "Automatic"),
    ("ask", "Ask every time"),
)
FLOATING_TOOLBAR_STYLE_CHOICES = (
    ("compact_pill", "Compact pill"),
    ("segmented_bar", "Segmented bar"),
    ("minimal_ghost", "Minimal ghost"),
)
FLOATING_TOOLBAR_SIZE_CHOICES = (
    ("small", "Small"),
    ("medium", "Medium"),
    ("large", "Large"),
)
SELECTION_TOOLBAR_MODE_CHOICES = (
    ("minimal_ghost_menu", "Minimal Ghost + Menu"),
    ("side_rail", "Side Rail"),
)
SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER_CHOICES = (
    ("click_affordance", "Click affordance"),
    ("right_click", "Right-click only"),
)
NODE_ELAPSED_TIME_UNIT_CHOICES = (
    ("seconds", "Seconds"),
    ("milliseconds", "Milliseconds"),
)
NODE_ELAPSED_TIME_VISIBILITY_CHOICES = (
    ("off", "Off"),
    ("during_run", "During run"),
    ("always", "Always"),
)
NODE_COMMENT_EDITOR_DEFAULT_CHOICES = (
    ("canvas_popover", "Canvas popover"),
    ("inspector", "Inspector"),
)
EDGE_CROSSING_STYLE_CHOICES = (
    ("none", "None"),
    ("gap_break", "Gap break"),
)
EXPAND_COLLISION_AVOIDANCE_STRATEGY_CHOICES = (
    ("nearest", "Nearest"),
)
EXPAND_COLLISION_AVOIDANCE_SCOPE_CHOICES = (
    ("all_movable", "All movable items"),
)
EXPAND_COLLISION_AVOIDANCE_RADIUS_MODE_CHOICES = (
    ("local", "Local"),
    ("unbounded", "Unbounded"),
)
EXPAND_COLLISION_AVOIDANCE_LOCAL_RADIUS_PRESET_CHOICES = (
    ("small", "Small"),
    ("medium", "Medium"),
    ("large", "Large"),
)
EXPAND_COLLISION_AVOIDANCE_GAP_PRESET_CHOICES = (
    ("tight", "Tight"),
    ("normal", "Normal"),
    ("loose", "Loose"),
)
SOURCE_IMPORT_MODE_CHOICES = (
    ("external_link", "External Link"),
    ("managed_copy", "Managed Copy"),
)
DEFAULT_STATUS_BAR_LAYOUT = STATUS_BAR_LAYOUT_CHOICES[0][0]
DEFAULT_GRID_OVERLAY_STYLE = GRID_OVERLAY_STYLE_CHOICES[0][0]
DEFAULT_CANVAS_BACKGROUND_VARIANT = CANVAS_BACKGROUND_VARIANT_CHOICES[0][0]
DEFAULT_CANVAS_IMPORT_MODE = CANVAS_IMPORT_MODE_CHOICES[0][0]
DEFAULT_FLOATING_TOOLBAR_STYLE = FLOATING_TOOLBAR_STYLE_CHOICES[0][0]
DEFAULT_FLOATING_TOOLBAR_SIZE = FLOATING_TOOLBAR_SIZE_CHOICES[0][0]
DEFAULT_NODE_FLOATING_TOOLBAR_OPENS_ON_HOVER = False
DEFAULT_SELECTION_TOOLBAR_MODE = SELECTION_TOOLBAR_MODE_CHOICES[0][0]
DEFAULT_SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER = (
    SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER_CHOICES[0][0]
)
DEFAULT_NODE_ELAPSED_TIME_UNIT = NODE_ELAPSED_TIME_UNIT_CHOICES[0][0]
DEFAULT_NODE_ELAPSED_TIME_VISIBILITY = "always"
DEFAULT_NODE_COMMENT_EDITOR_DEFAULT = NODE_COMMENT_EDITOR_DEFAULT_CHOICES[0][0]
DEFAULT_EDGE_CROSSING_STYLE = EDGE_CROSSING_STYLE_CHOICES[0][0]
DEFAULT_EXPAND_COLLISION_AVOIDANCE_STRATEGY = EXPAND_COLLISION_AVOIDANCE_STRATEGY_CHOICES[0][0]
DEFAULT_EXPAND_COLLISION_AVOIDANCE_SCOPE = EXPAND_COLLISION_AVOIDANCE_SCOPE_CHOICES[0][0]
DEFAULT_EXPAND_COLLISION_AVOIDANCE_RADIUS_MODE = EXPAND_COLLISION_AVOIDANCE_RADIUS_MODE_CHOICES[0][0]
DEFAULT_EXPAND_COLLISION_AVOIDANCE_LOCAL_RADIUS_PRESET = "medium"
DEFAULT_EXPAND_COLLISION_AVOIDANCE_GAP_PRESET = "normal"
DEFAULT_SOURCE_IMPORT_MODE = "external_link"
DEFAULT_SELECTED_RUN_PREVIEW_BEFORE_RUN = True
DEFAULT_PLOT_LIGHTWEIGHT_CANVAS = False
DEFAULT_PLOT_BACKEND_PER_TYPE = {
    "line": "matplotlib",
    "scatter": "matplotlib",
    "bar": "matplotlib",
    "histogram": "matplotlib",
    "heatmap": "matplotlib",
    "contour": "matplotlib",
}
GRAPH_LABEL_PIXEL_SIZE_MIN = 8
GRAPH_LABEL_PIXEL_SIZE_MAX = 50
GRAPH_NODE_ICON_PIXEL_SIZE_MAX = 50
DEFAULT_GRAPH_LABEL_PIXEL_SIZE = 10
TABULAR_DATA_BACKEND_POLICY_REVISION = "tabular-data-backend-policy-v2"
TABULAR_DATA_SMALL_FILE_BYTES = 100 * 1024 * 1024
# Text/Excel sources at or below this size may convert to the managed parquet
# cache synchronously on the calling thread; larger sources convert on worker
# threads so interactive callers can surface a loading state instead.
TABULAR_DATA_INLINE_CONVERSION_BYTES = 8 * 1024 * 1024
# Soft cap for the managed parquet cache directory; least-recently-used cache
# entries are evicted past this size.
TABULAR_DATA_CACHE_MAX_BYTES = 20 * 1024 * 1024 * 1024
TABULAR_DATA_LARGE_WARNING_BYTES = 1024 * 1024 * 1024
TABULAR_DATA_EXPLICIT_MATERIALIZATION_BYTES = 5 * 1024 * 1024 * 1024
TABULAR_DATA_DEFAULT_PREVIEW_ROWS = 50
TABULAR_DATA_DEFAULT_PREVIEW_COLUMNS = 50
TABULAR_DATA_CACHE_DIRNAME = "tabular_data_cache"
TABULAR_DATA_CACHE_FORMAT = "parquet"

DEFAULT_EXPAND_COLLISION_AVOIDANCE_SETTINGS = {
    "enabled": True,
    "strategy": DEFAULT_EXPAND_COLLISION_AVOIDANCE_STRATEGY,
    "scope": DEFAULT_EXPAND_COLLISION_AVOIDANCE_SCOPE,
    "radius_mode": DEFAULT_EXPAND_COLLISION_AVOIDANCE_RADIUS_MODE,
    "local_radius_preset": DEFAULT_EXPAND_COLLISION_AVOIDANCE_LOCAL_RADIUS_PRESET,
    "gap_preset": DEFAULT_EXPAND_COLLISION_AVOIDANCE_GAP_PRESET,
    "animate": True,
}

DEFAULT_MEDIA_PANEL_SETTINGS = {
    "show_title": True,
    "show_frame": True,
    "autoplay_animations": True,
    "source_input_exposed": True,
}

DEFAULT_PLOT_SETTINGS = {
    "lightweight_canvas": DEFAULT_PLOT_LIGHTWEIGHT_CANVAS,
    "plot_default_backend_per_type": DEFAULT_PLOT_BACKEND_PER_TYPE,
}

DEFAULT_ENGINEERING_VIEWER_SETTINGS = {
    "tangent_selection_angle_degrees": 5.0,
}

FOLDER_EXPLORER_COLUMN_WIDTH_KEYS = ("name", "modified", "type", "size")
FOLDER_EXPLORER_COLUMN_WIDTH_MIN = 48
FOLDER_EXPLORER_COLUMN_WIDTH_MAX = 1200
DEFAULT_FOLDER_EXPLORER_COLUMN_WIDTHS = {}
DEFAULT_FOLDER_EXPLORER_SETTINGS = {
    "column_widths": DEFAULT_FOLDER_EXPLORER_COLUMN_WIDTHS,
}

DEFAULT_GRAPHICS_SETTINGS = {
    "canvas": {
        "background_variant": DEFAULT_CANVAS_BACKGROUND_VARIANT,
        "show_grid": True,
        "grid_style": DEFAULT_GRID_OVERLAY_STYLE,
        "edge_crossing_style": DEFAULT_EDGE_CROSSING_STYLE,
        "show_canvas_options_button": True,
        "show_minimap": True,
        "show_port_labels": True,
        "notched_ports": True,
        "keep_expanded_node_width": False,
        "minimap_expanded": True,
        "node_shadow": True,
        "shadow_strength": 70,
        "shadow_softness": 50,
        "shadow_offset": 4,
        "floating_toolbar_style": DEFAULT_FLOATING_TOOLBAR_STYLE,
        "floating_toolbar_size": DEFAULT_FLOATING_TOOLBAR_SIZE,
        "node_floating_toolbar_opens_on_hover": DEFAULT_NODE_FLOATING_TOOLBAR_OPENS_ON_HOVER,
        "selection_toolbar_mode": DEFAULT_SELECTION_TOOLBAR_MODE,
        "selection_toolbar_minimal_menu_trigger": (
            DEFAULT_SELECTION_TOOLBAR_MINIMAL_MENU_TRIGGER
        ),
        "node_elapsed_time_unit": DEFAULT_NODE_ELAPSED_TIME_UNIT,
        "node_elapsed_time_visibility": DEFAULT_NODE_ELAPSED_TIME_VISIBILITY,
        "node_comment_editor_default": DEFAULT_NODE_COMMENT_EDITOR_DEFAULT,
    },
    "interaction": {
        "snap_to_grid": False,
        "canvas_import_mode": DEFAULT_CANVAS_IMPORT_MODE,
        "expand_collision_avoidance": DEFAULT_EXPAND_COLLISION_AVOIDANCE_SETTINGS,
    },
    "shell": {
        "tab_strip_density": "compact",
        "status_bar_layout": DEFAULT_STATUS_BAR_LAYOUT,
        "show_fps_telemetry": True,
        "property_pane_variant": DEFAULT_PROPERTY_PANE_VARIANT,
        "passive_node_library_display_mode": DEFAULT_PASSIVE_NODE_LIBRARY_DISPLAY_MODE,
        "panel_collapsed": DEFAULT_SHELL_PANEL_COLLAPSED,
        "tooltip_categories": default_tooltip_category_preferences(),
        "node_library_usage": [],
    },
    "theme": {
        "theme_id": "stitch_dark",
    },
    "typography": {
        "graph_label_pixel_size": DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        "graph_node_icon_pixel_size_override": None,
        "recent_text_colors": [],
    },
    "media_panel": DEFAULT_MEDIA_PANEL_SETTINGS,
    "plot": DEFAULT_PLOT_SETTINGS,
    "engineering_viewer": DEFAULT_ENGINEERING_VIEWER_SETTINGS,
    "folder_explorer": DEFAULT_FOLDER_EXPLORER_SETTINGS,
    "graph_theme": {
        "follow_shell_theme": True,
        "selected_theme_id": DEFAULT_GRAPH_THEME_ID,
        "custom_themes": [],
    },
}

DEFAULT_SOURCE_IMPORT_SETTINGS = {
    "default_mode": DEFAULT_SOURCE_IMPORT_MODE,
}

DEFAULT_SELECTED_RUN_SETTINGS = {
    "preview_before_run": DEFAULT_SELECTED_RUN_PREVIEW_BEFORE_RUN,
}

DEFAULT_SOLUTION_SETTINGS = {
    "default_mode": "auto",
}

DEFAULT_TABULAR_DATA_SETTINGS = {
    "backend_policy_revision": TABULAR_DATA_BACKEND_POLICY_REVISION,
    "cache_format": TABULAR_DATA_CACHE_FORMAT,
    "cache_dirname": TABULAR_DATA_CACHE_DIRNAME,
    "small_file_bytes": TABULAR_DATA_SMALL_FILE_BYTES,
    "large_warning_bytes": TABULAR_DATA_LARGE_WARNING_BYTES,
    "explicit_materialization_bytes": TABULAR_DATA_EXPLICIT_MATERIALIZATION_BYTES,
    "preview_rows": TABULAR_DATA_DEFAULT_PREVIEW_ROWS,
    "preview_columns": TABULAR_DATA_DEFAULT_PREVIEW_COLUMNS,
}

DEFAULT_ADDON_STATE = {
    "enabled": True,
    "pending_restart": False,
}

DEFAULT_ADDON_SETTINGS = {
    "states": {},
}

DEFAULT_PLUGIN_SETTINGS = {}

DEFAULT_PYTHON_RUNTIME_SETTINGS = {
    "default_executable": "",
}

DEFAULT_APP_PREFERENCES = {
    "kind": APP_PREFERENCES_KIND,
    "version": APP_PREFERENCES_VERSION,
    "graphics": DEFAULT_GRAPHICS_SETTINGS,
    "addons": DEFAULT_ADDON_SETTINGS,
    "plugins": DEFAULT_PLUGIN_SETTINGS,
    "source_import": DEFAULT_SOURCE_IMPORT_SETTINGS,
    "selected_run": DEFAULT_SELECTED_RUN_SETTINGS,
    "solution": DEFAULT_SOLUTION_SETTINGS,
    "python_runtime": DEFAULT_PYTHON_RUNTIME_SETTINGS,
}


def user_data_dir() -> Path:
    app_data = os.environ.get("APPDATA")
    if app_data:
        base_dir = Path(app_data)
    else:
        base_dir = Path.home() / ".config"
    preferred_dir = base_dir / APP_DATA_DIR_NAME
    legacy_dir = base_dir / LEGACY_APP_DATA_DIR_NAME
    data_dir = preferred_dir if preferred_dir.exists() or not legacy_dir.exists() else legacy_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def recent_session_path() -> Path:
    return user_data_dir() / "last_session.json"


def app_preferences_path() -> Path:
    return user_data_dir() / "app_preferences.json"


def autosave_project_path() -> Path:
    return user_data_dir() / f"autosave{PROJECT_EXTENSION}"


def plugins_dir() -> Path:
    plugin_path = user_data_dir() / "plugins"
    plugin_path.mkdir(parents=True, exist_ok=True)
    return plugin_path


def plugin_generations_dir() -> Path:
    generation_path = user_data_dir() / "runtime" / "plugin_generations"
    generation_path.mkdir(parents=True, exist_ok=True)
    return generation_path


def tabular_data_cache_dir() -> Path:
    override = os.environ.get("EA_TABULAR_CACHE_DIR", "").strip()
    cache_path = Path(override) if override else user_data_dir() / TABULAR_DATA_CACHE_DIRNAME
    cache_path.mkdir(parents=True, exist_ok=True)
    return cache_path
