from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from ea_node_editor.graph.effective_ports import EffectivePort
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.settings import DEFAULT_GRAPH_LABEL_PIXEL_SIZE
from .standard_metrics import collapsed_node_title_width, standard_viewer_port_row_height
from .surface_contract import (
    ANNOTATION_VARIANT_LAYOUTS,
    GROUP_BACKDROP_VARIANT_LAYOUTS,
    MEDIA_VARIANT_LAYOUTS,
    PASSIVE_PORT_DOT_RADIUS,
    PASSIVE_PORT_SIDE_MARGIN,
    PASSIVE_SURFACE_RESIZE_HANDLE_SIZE,
    PLANNING_VARIANT_LAYOUTS,
    STANDARD_COLLAPSED_HEIGHT,
    STANDARD_COLLAPSED_WIDTH,
    GraphNodeSurfaceMetrics,
    _PassivePanelLayout,
    _resolved_dimensions,
    _visible_port_count,
)


def normalize_planning_variant(variant: str) -> str:
    normalized = str(variant or "").strip().lower()
    return normalized if normalized in PLANNING_VARIANT_LAYOUTS else "task_card"


def normalize_annotation_variant(variant: str) -> str:
    normalized = str(variant or "").strip().lower()
    return normalized if normalized in ANNOTATION_VARIANT_LAYOUTS else "sticky_note"


def normalize_group_backdrop_variant(variant: str) -> str:
    normalized = str(variant or "").strip().lower()
    return normalized if normalized in GROUP_BACKDROP_VARIANT_LAYOUTS else "group_backdrop"


def normalize_media_variant(variant: str) -> str:
    normalized = str(variant or "").strip().lower()
    return normalized if normalized in MEDIA_VARIANT_LAYOUTS else "media_panel"


def _build_panel_surface_metrics(
    *,
    default_width: float,
    default_height: float,
    min_width: float,
    min_height: float,
    active_height: float,
    body_top: float,
    body_height: float,
    title_top: float,
    title_height: float,
    title_left_margin: float,
    title_right_margin: float,
    title_centered: bool,
    body_left_margin: float,
    body_right_margin: float,
    body_bottom_margin: float,
    use_host_chrome: bool,
    use_host_shadow: bool = True,
    collapsed_width: float = STANDARD_COLLAPSED_WIDTH,
) -> GraphNodeSurfaceMetrics:
    return GraphNodeSurfaceMetrics(
        default_width=default_width,
        default_height=default_height,
        min_width=min_width,
        min_height=min_height,
        collapsed_width=collapsed_width,
        collapsed_height=STANDARD_COLLAPSED_HEIGHT,
        header_height=0.0,
        header_top_margin=0.0,
        body_top=body_top,
        body_height=body_height,
        port_top=active_height - body_bottom_margin,
        port_height=0.0,
        port_center_offset=0.0,
        port_side_margin=PASSIVE_PORT_SIDE_MARGIN,
        port_dot_radius=PASSIVE_PORT_DOT_RADIUS,
        resize_handle_size=PASSIVE_SURFACE_RESIZE_HANDLE_SIZE,
        title_top=title_top,
        title_height=title_height,
        title_left_margin=title_left_margin,
        title_right_margin=title_right_margin,
        title_centered=title_centered,
        body_left_margin=body_left_margin,
        body_right_margin=body_right_margin,
        body_bottom_margin=body_bottom_margin,
        use_host_chrome=use_host_chrome,
        use_host_shadow=use_host_shadow,
    )


def _passive_panel_surface_metrics(
    node: NodeInstance,
    layout: _PassivePanelLayout,
) -> GraphNodeSurfaceMetrics:
    _active_width, active_height = _resolved_dimensions(
        node,
        default_width=layout.default_width,
        default_height=layout.default_height,
    )
    body_height = max(layout.body_height, active_height - layout.body_top - layout.body_bottom_margin)
    return _build_panel_surface_metrics(
        default_width=layout.default_width,
        default_height=layout.default_height,
        min_width=layout.min_width,
        min_height=layout.min_height,
        active_height=active_height,
        body_top=layout.body_top,
        body_height=body_height,
        title_top=layout.title_top,
        title_height=layout.title_height,
        title_left_margin=layout.title_left_margin,
        title_right_margin=layout.title_right_margin,
        title_centered=layout.title_centered,
        body_left_margin=layout.body_left_margin,
        body_right_margin=layout.body_right_margin,
        body_bottom_margin=layout.body_bottom_margin,
        use_host_chrome=layout.use_host_chrome,
        use_host_shadow=layout.use_host_shadow,
    )


def _planning_surface_metrics(node: NodeInstance, spec: NodeTypeSpec) -> GraphNodeSurfaceMetrics:
    layout = PLANNING_VARIANT_LAYOUTS[normalize_planning_variant(spec.surface_variant)]
    return _passive_panel_surface_metrics(node, layout)


def _annotation_surface_metrics(node: NodeInstance, spec: NodeTypeSpec) -> GraphNodeSurfaceMetrics:
    layout = ANNOTATION_VARIANT_LAYOUTS[normalize_annotation_variant(spec.surface_variant)]
    return _passive_panel_surface_metrics(node, layout)


def _group_backdrop_surface_metrics(
    node: NodeInstance,
    spec: NodeTypeSpec,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
) -> GraphNodeSurfaceMetrics:
    layout = GROUP_BACKDROP_VARIANT_LAYOUTS[normalize_group_backdrop_variant(spec.surface_variant)]
    _active_width, active_height = _resolved_dimensions(
        node,
        default_width=layout.default_width,
        default_height=layout.default_height,
    )
    body_height = max(0.0, active_height - layout.body_top - layout.body_bottom_margin)
    return _build_panel_surface_metrics(
        default_width=layout.default_width,
        default_height=layout.default_height,
        min_width=layout.min_width,
        min_height=layout.min_height,
        active_height=active_height,
        body_top=layout.body_top,
        body_height=body_height,
        title_top=layout.title_top,
        title_height=layout.title_height,
        title_left_margin=layout.title_left_margin,
        title_right_margin=layout.title_right_margin,
        title_centered=layout.title_centered,
        body_left_margin=layout.body_left_margin,
        body_right_margin=layout.body_right_margin,
        body_bottom_margin=layout.body_bottom_margin,
        use_host_chrome=layout.use_host_chrome,
        use_host_shadow=layout.use_host_shadow,
        collapsed_width=collapsed_node_title_width(
            node,
            spec,
            STANDARD_COLLAPSED_WIDTH,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        ),
    )


def _media_surface_metrics(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
) -> GraphNodeSurfaceMetrics:
    variant = normalize_media_variant(spec.surface_variant)
    layout = MEDIA_VARIANT_LAYOUTS[variant]
    default_width = float(layout.default_width)
    port_count = _visible_port_count(
        node,
        spec,
        workspace_nodes,
        visible_ports_override=visible_ports_override,
    )
    port_height = standard_viewer_port_row_height(
        graph_label_pixel_size=graph_label_pixel_size,
    )
    default_body_height = max(
        layout.min_body_height,
        float(layout.default_height) - layout.body_top - layout.body_bottom_margin,
    )
    default_height = (
        layout.body_top
        + default_body_height
        + port_count * port_height
        + layout.body_bottom_margin
    )
    min_height = max(
        layout.min_height,
        layout.body_top
        + layout.min_body_height
        + port_count * port_height
        + layout.body_bottom_margin,
    )
    _active_width, active_height = _resolved_dimensions(
        node,
        default_width=default_width,
        default_height=default_height,
    )
    body_height = max(
        layout.min_body_height,
        active_height
        - layout.body_top
        - port_count * port_height
        - layout.body_bottom_margin,
    )
    return replace(
        _build_panel_surface_metrics(
        default_width=default_width,
        default_height=default_height,
        min_width=layout.min_width,
        min_height=min_height,
        active_height=active_height,
        body_top=layout.body_top,
        body_height=body_height,
        title_top=layout.title_top,
        title_height=layout.title_height,
        title_left_margin=layout.title_left_margin,
        title_right_margin=layout.title_right_margin,
        title_centered=layout.title_centered,
        body_left_margin=layout.body_left_margin,
        body_right_margin=layout.body_right_margin,
        body_bottom_margin=layout.body_bottom_margin,
        use_host_chrome=True,
        ),
        port_top=layout.body_top + body_height,
        port_height=port_height,
        port_center_offset=port_height * 0.5,
    )
