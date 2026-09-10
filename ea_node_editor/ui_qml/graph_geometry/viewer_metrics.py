from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ea_node_editor.graph.effective_ports import EffectivePort
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.settings import DEFAULT_GRAPH_LABEL_PIXEL_SIZE

from .standard_metrics import (
    _dynamic_port_bottom_padding,
    _standard_surface_min_width_contract,
    standard_body_top,
    standard_header_height,
    standard_inline_body_height,
    standard_viewer_port_row_height,
)
from .surface_contract import (
    STANDARD_COLLAPSED_HEIGHT,
    STANDARD_COLLAPSED_WIDTH,
    STANDARD_HEADER_TOP_MARGIN,
    STANDARD_PORT_CENTER_OFFSET,
    STANDARD_PORT_DOT_RADIUS,
    STANDARD_PORT_SIDE_MARGIN,
    STANDARD_RESIZE_HANDLE_SIZE,
    STANDARD_TITLE_LEFT_MARGIN,
    STANDARD_USE_HOST_CHROME,
    VIEWER_BODY_BOTTOM_PADDING,
    VIEWER_BODY_LEFT_MARGIN,
    VIEWER_BODY_RIGHT_MARGIN,
    VIEWER_DEFAULT_BODY_HEIGHT,
    VIEWER_DEFAULT_WIDTH,
    VIEWER_MIN_BODY_HEIGHT,
    VIEWER_MIN_WIDTH,
    VIEWER_TITLE_RIGHT_MARGIN,
    GraphNodeSurfaceMetrics,
    _resolved_dimensions,
    _safe_number,
    _visible_port_count,
)


def _viewer_surface_metrics(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    show_port_labels: bool = True,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
) -> GraphNodeSurfaceMetrics:
    port_count = _visible_port_count(
        node,
        spec,
        workspace_nodes,
        visible_ports_override=visible_ports_override,
    )
    port_row_height = standard_viewer_port_row_height(
        graph_label_pixel_size=graph_label_pixel_size,
    )
    bottom_padding = max(VIEWER_BODY_BOTTOM_PADDING, _dynamic_port_bottom_padding(
        node,
        spec,
        workspace_nodes,
        port_count=port_count,
        port_row_height=port_row_height,
        port_center_offset=STANDARD_PORT_CENTER_OFFSET,
        graph_label_pixel_size=graph_label_pixel_size,
        visible_ports_override=visible_ports_override,
    ))
    header_height = standard_header_height(
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
    )
    body_top = standard_body_top(
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
    )
    inline_body_height = standard_inline_body_height(
        spec,
        graph_label_pixel_size=graph_label_pixel_size,
    )
    default_body_height = max(VIEWER_DEFAULT_BODY_HEIGHT, inline_body_height)
    min_body_height = max(VIEWER_MIN_BODY_HEIGHT, inline_body_height)
    default_height = body_top + default_body_height + port_count * port_row_height + bottom_padding
    width_contract = _standard_surface_min_width_contract(
        node,
        spec,
        workspace_nodes,
        visible_ports_override=visible_ports_override,
    )
    min_width = max(
        VIEWER_MIN_WIDTH,
        width_contract.min_width_with_labels if show_port_labels else width_contract.min_width_without_labels,
    )
    min_height = body_top + min_body_height + port_count * port_row_height + bottom_padding
    _active_width, active_height = _resolved_dimensions(
        node,
        default_width=VIEWER_DEFAULT_WIDTH,
        default_height=default_height,
    )
    body_height = max(
        min_body_height,
        active_height - body_top - port_count * port_row_height - bottom_padding,
    )
    return GraphNodeSurfaceMetrics(
        default_width=VIEWER_DEFAULT_WIDTH,
        default_height=default_height,
        min_width=min_width,
        min_height=min_height,
        collapsed_width=STANDARD_COLLAPSED_WIDTH,
        collapsed_height=STANDARD_COLLAPSED_HEIGHT,
        header_height=header_height,
        header_top_margin=STANDARD_HEADER_TOP_MARGIN,
        body_top=body_top,
        body_height=body_height,
        port_top=body_top + body_height,
        port_height=port_row_height,
        port_center_offset=STANDARD_PORT_CENTER_OFFSET,
        port_side_margin=STANDARD_PORT_SIDE_MARGIN,
        port_dot_radius=STANDARD_PORT_DOT_RADIUS,
        resize_handle_size=STANDARD_RESIZE_HANDLE_SIZE,
        title_top=STANDARD_HEADER_TOP_MARGIN,
        title_height=header_height,
        title_left_margin=STANDARD_TITLE_LEFT_MARGIN,
        title_right_margin=VIEWER_TITLE_RIGHT_MARGIN,
        title_centered=False,
        body_left_margin=VIEWER_BODY_LEFT_MARGIN,
        body_right_margin=VIEWER_BODY_RIGHT_MARGIN,
        body_bottom_margin=bottom_padding,
        use_host_chrome=STANDARD_USE_HOST_CHROME,
        standard_title_full_width=width_contract.title_full_width,
        standard_left_label_width=width_contract.left_label_width,
        standard_right_label_width=width_contract.right_label_width,
        standard_port_gutter=width_contract.port_gutter,
        standard_center_gap=width_contract.center_gap,
        standard_port_label_min_width=width_contract.port_label_min_width,
    )


def viewer_surface_contract_payload(
    *,
    width: float,
    height: float,
    surface_metrics: GraphNodeSurfaceMetrics,
) -> dict[str, Any]:
    width_value = max(0.0, _safe_number(width, 0.0))
    height_value = max(0.0, _safe_number(height, 0.0))
    body_x = max(0.0, _safe_number(surface_metrics.body_left_margin, 0.0))
    body_y = max(0.0, _safe_number(surface_metrics.body_top, 0.0))
    body_width = max(
        0.0,
        width_value
        - body_x
        - max(0.0, _safe_number(surface_metrics.body_right_margin, 0.0)),
    )
    body_height = max(
        0.0,
        min(
            max(0.0, _safe_number(surface_metrics.body_height, 0.0)),
            max(0.0, height_value - body_y),
        ),
    )
    body_rect = {
        "x": body_x,
        "y": body_y,
        "width": body_width,
        "height": body_height,
    }
    return {
        "body_rect": dict(body_rect),
        "proxy_rect": dict(body_rect),
        "live_rect": dict(body_rect),
        "overlay_target": "body",
        "proxy_surface_supported": True,
        "live_surface_supported": True,
    }
