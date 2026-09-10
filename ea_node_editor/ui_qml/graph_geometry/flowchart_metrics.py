from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from ea_node_editor.graph.effective_ports import EffectivePort
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.node_specs import NodeTypeSpec

from .standard_metrics import standard_inline_body_height
from .surface_contract import (
    FLOWCHART_COLLAPSED_HEIGHT,
    FLOWCHART_COLLAPSED_WIDTH,
    FLOWCHART_INLINE_GAP,
    FLOWCHART_PORT_CENTER_OFFSET,
    FLOWCHART_PORT_DOT_RADIUS,
    FLOWCHART_PORT_HEIGHT,
    FLOWCHART_PORT_SECTION_TOP,
    FLOWCHART_RESIZE_HANDLE_SIZE,
    FLOWCHART_TITLE_HEIGHT,
    FLOWCHART_VARIANT_LAYOUTS,
    GraphNodeSurfaceMetrics,
    _FlowchartVariantLayout,
    _resolved_dimensions,
    _visible_port_count,
)


@dataclass(frozen=True, slots=True)
class _FlowchartMetricLayoutState:
    default_width: float
    default_height: float
    min_width: float
    title_top: float
    body_top: float
    body_height: float
    port_top: float


def normalize_flowchart_variant(variant: str) -> str:
    normalized = str(variant or "").strip().lower()
    return normalized if normalized in FLOWCHART_VARIANT_LAYOUTS else "process"


def _flowchart_surface_metrics(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
) -> GraphNodeSurfaceMetrics:
    layout = FLOWCHART_VARIANT_LAYOUTS[normalize_flowchart_variant(spec.surface_variant)]
    layout_state = _resolve_flowchart_metric_layout_state(
        node,
        spec,
        layout,
        workspace_nodes,
        visible_ports_override=visible_ports_override,
    )
    return GraphNodeSurfaceMetrics(
        default_width=layout_state.default_width,
        default_height=layout_state.default_height,
        min_width=layout_state.min_width,
        min_height=layout.min_height,
        collapsed_width=FLOWCHART_COLLAPSED_WIDTH,
        collapsed_height=FLOWCHART_COLLAPSED_HEIGHT,
        header_height=0.0,
        header_top_margin=0.0,
        body_top=layout_state.body_top,
        body_height=layout_state.body_height,
        port_top=layout_state.port_top,
        port_height=FLOWCHART_PORT_HEIGHT,
        port_center_offset=FLOWCHART_PORT_CENTER_OFFSET,
        port_side_margin=0.0,
        port_dot_radius=FLOWCHART_PORT_DOT_RADIUS,
        resize_handle_size=FLOWCHART_RESIZE_HANDLE_SIZE,
        title_top=layout_state.title_top,
        title_height=FLOWCHART_TITLE_HEIGHT,
        title_left_margin=layout.title_left_margin,
        title_right_margin=layout.title_right_margin,
        title_centered=True,
        body_left_margin=layout.body_left_margin,
        body_right_margin=layout.body_right_margin,
        body_bottom_margin=layout.body_bottom_margin,
        use_host_chrome=False,
    )


def _resolve_flowchart_metric_layout_state(
    node: NodeInstance,
    spec: NodeTypeSpec,
    layout: _FlowchartVariantLayout,
    workspace_nodes: Mapping[str, NodeInstance] | None,
    *,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
) -> _FlowchartMetricLayoutState:
    body_height = standard_inline_body_height(spec)
    port_count = _visible_port_count(
        node,
        spec,
        workspace_nodes,
        visible_ports_override=visible_ports_override,
    )
    base_port_section_top = (
        layout.title_top + FLOWCHART_TITLE_HEIGHT + FLOWCHART_INLINE_GAP + body_height + FLOWCHART_INLINE_GAP
        if body_height > 0.0
        else FLOWCHART_PORT_SECTION_TOP
    )
    default_height = max(
        layout.min_height,
        base_port_section_top + port_count * FLOWCHART_PORT_HEIGHT + layout.body_bottom_margin,
    )
    default_width = layout.default_width
    min_width = layout.min_width
    if layout.square:
        default_width = max(default_width, default_height)
        min_width = max(min_width, layout.min_height)

    _active_width, active_height = _resolved_dimensions(
        node,
        default_width=default_width,
        default_height=default_height,
    )
    title_top = (
        layout.title_top
        if body_height > 0.0
        else max(12.0, (active_height - FLOWCHART_TITLE_HEIGHT) * 0.5)
    )
    body_top = title_top + FLOWCHART_TITLE_HEIGHT + FLOWCHART_INLINE_GAP
    port_section_top = (
        body_top + body_height + FLOWCHART_INLINE_GAP if body_height > 0.0 else FLOWCHART_PORT_SECTION_TOP
    )
    available_port_height = max(
        port_count * FLOWCHART_PORT_HEIGHT,
        active_height - port_section_top - layout.body_bottom_margin,
    )
    port_top = port_section_top + max(0.0, (available_port_height - port_count * FLOWCHART_PORT_HEIGHT) * 0.5)
    return _FlowchartMetricLayoutState(
        default_width=default_width,
        default_height=default_height,
        min_width=min_width,
        body_top=body_top,
        body_height=body_height,
        port_top=port_top,
        title_top=title_top,
    )


def _flowchart_horizontal_bounds(
    variant: str,
    width: float,
    height: float,
    local_y: float,
) -> tuple[float, float]:
    if width <= 0.0 or height <= 0.0:
        return 0.0, max(0.0, width)
    y_value = max(0.0, min(height, local_y))
    if variant in {"start", "end"}:
        radius = min(width * 0.5, height * 0.5)
        cy = height * 0.5
        dy = max(-radius, min(radius, y_value - cy))
        dx = math.sqrt(max(0.0, radius * radius - dy * dy))
        left = radius - dx
        return left, width - left
    if variant == "decision":
        left = abs((height * 0.5) - y_value) * width / height
        return left, width - left
    if variant == "connector":
        rx = width * 0.5
        ry = height * 0.5
        cy = height * 0.5
        dy = max(-ry, min(ry, y_value - cy))
        if ry <= 0.0:
            return 0.0, width
        factor = math.sqrt(max(0.0, 1.0 - (dy * dy) / (ry * ry)))
        dx = rx * factor
        return rx - dx, rx + dx
    if variant == "input_output":
        slant = min(width * 0.13, height * 0.26)
        left = max(0.0, slant * (1.0 - (y_value / height)))
        return left, width - left
    return 0.0, width
