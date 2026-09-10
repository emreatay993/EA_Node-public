from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from ea_node_editor.common.protocols import SignalLike as _SignalLike


if TYPE_CHECKING:
    pass


class _GraphCanvasProjectSource(Protocol):
    model: object
    project_path: str


class _GraphCanvasGraphicsSource(Protocol):
    graphics_preferences_changed: _SignalLike
    graphics_show_grid: bool
    graphics_canvas_background_variant: str
    graphics_canvas_import_mode: str
    graphics_grid_style: str
    graphics_edge_crossing_style: str
    graphics_graph_label_pixel_size: int
    graphics_tooltip_categories: dict[str, bool]
    graphics_tooltip_category_visibility: dict[str, bool]
    graphics_expand_collision_avoidance: dict[str, Any]
    graphics_lightweight_canvas: bool
    graphics_plot_default_backend_per_type: dict[str, str]
    graphics_graph_node_icon_pixel_size_override: int | None
    graphics_node_title_icon_pixel_size: int
    graphics_recent_text_colors: list[str]
    graphics_media_panel_defaults: dict[str, bool]
    graphics_media_panel_default_show_title: bool
    graphics_media_panel_default_show_frame: bool
    graphics_media_panel_autoplay_animations: bool
    graphics_media_panel_source_input_exposed: bool
    graphics_folder_explorer_column_widths: dict[str, int]
    graphics_show_minimap: bool
    graphics_show_canvas_options_button: bool
    graphics_show_port_labels: bool
    graphics_notched_ports: bool
    graphics_node_elapsed_time_unit: str
    graphics_node_elapsed_time_visibility: str
    graphics_node_comment_editor_default: str
    graphics_node_shadow: bool
    graphics_shadow_strength: int
    graphics_shadow_softness: int
    graphics_shadow_offset: int
    graphics_status_bar_layout: str
    graphics_show_fps_telemetry: bool
    graphics_floating_toolbar_style: str
    graphics_floating_toolbar_size: str
    graphics_node_floating_toolbar_opens_on_hover: bool
    graphics_selection_toolbar_mode: str
    graphics_selection_toolbar_minimal_menu_trigger: str
    active_theme_id: str
    graphics_graph_follow_shell_theme: bool
    graphics_selected_graph_theme_id: str


class _GraphCanvasExecutionSource(Protocol):
    run_failure_changed: _SignalLike
    node_execution_state_changed: _SignalLike
    run_state: object


class _GraphCanvasSceneStateSource(Protocol):
    nodes_changed: _SignalLike
    edges_changed: _SignalLike
    selection_changed: _SignalLike
    workspace_changed: _SignalLike
    workspace_id: str
    nodes_model: list[dict[str, Any]]
    minimap_nodes_model: list[dict[str, Any]]
    backdrop_nodes_model: list[dict[str, Any]]
    node_delta_payload: dict[str, Any]
    workspace_scene_bounds_payload: dict[str, Any]
    edges_model: list[dict[str, Any]]
    edge_delta_payload: dict[str, Any]
    selected_node_ids: list[str]
    selected_node_lookup: dict[str, bool]
    hide_optional_ports: bool


class _GraphCanvasScenePolicySource(Protocol):
    def compatible_endpoint_snapshot(
        self,
        anchor_node_id: str,
        anchor_port_key: str,
        candidate_role: str,
    ) -> dict[str, Any]: ...

    def compatible_rewire_endpoint_snapshot(
        self,
        edge_ids: list[object],
        endpoint: str,
        copy_requested: bool = False,
        append_requested: bool = False,
    ) -> dict[str, Any]: ...

    def are_port_kinds_compatible(self, source_kind: str, target_kind: str) -> bool: ...

    def are_data_types_compatible(self, source_type: str, target_type: str) -> bool: ...
