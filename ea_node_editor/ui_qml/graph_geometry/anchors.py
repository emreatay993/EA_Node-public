# Purpose: Resolve port anchors using node surface geometry.
# Map: feature_routes/graph_scene_payload_and_projection.md
# Tests: tests/test_graph_scene_presentation_facts.py, tests/test_graph_surface_input_controls.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ea_node_editor.graph.effective_ports import (
    EffectivePort,
    find_port,
    port_direction,
    port_layout_direction,
    port_side,
    visible_ports,
)
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.node_specs import NodeTypeSpec

from .flowchart_metrics import _flowchart_horizontal_bounds, normalize_flowchart_variant
from .standard_metrics import node_surface_metrics, resolved_node_surface_size, uses_content_sizing
from .surface_contract import CARDINAL_SIDES, FLOWCHART_OUTLINE_INSET, _FlowchartBounds, _resolved_dimensions


def _flowchart_bounds(width: float, height: float) -> _FlowchartBounds:
    if width <= 0.0 or height <= 0.0:
        return _FlowchartBounds(
            left=0.0,
            top=0.0,
            right=max(0.0, width),
            bottom=max(0.0, height),
            width=max(1.0, width),
            height=max(1.0, height),
            center_x=max(0.0, width) * 0.5,
            center_y=max(0.0, height) * 0.5,
        )

    inset = FLOWCHART_OUTLINE_INSET
    left = inset
    top = inset
    right = max(left + 1.0, width - inset)
    bottom = max(top + 1.0, height - inset)
    width_value = max(1.0, right - left)
    height_value = max(1.0, bottom - top)
    return _FlowchartBounds(
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        width=width_value,
        height=height_value,
        center_x=(left + right) * 0.5,
        center_y=(top + bottom) * 0.5,
    )


def _cubic_bezier_coordinate(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    omt = 1.0 - t
    return (
        (omt * omt * omt * p0)
        + (3.0 * omt * omt * t * p1)
        + (3.0 * omt * t * t * p2)
        + (t * t * t * p3)
    )


def _solve_monotonic_bezier_t_for_coordinate(
    target: float,
    p0: float,
    p1: float,
    p2: float,
    p3: float,
) -> float:
    increasing = p3 >= p0
    low = 0.0
    high = 1.0
    for _ in range(32):
        mid = (low + high) * 0.5
        value = _cubic_bezier_coordinate(p0, p1, p2, p3, mid)
        if (value < target) == increasing:
            low = mid
        else:
            high = mid
    return (low + high) * 0.5


def _document_bottom_anchor(bounds: _FlowchartBounds) -> tuple[float, float]:
    wave_depth = min(bounds.height * 0.11, 11.5)
    wave_base = bounds.bottom - wave_depth * 0.58
    wave_crest = bounds.bottom - wave_depth * 1.08
    wave_trough = bounds.bottom - wave_depth * 0.12
    middle_x = bounds.left + bounds.width * 0.52
    target_x = bounds.center_x

    if target_x >= middle_x:
        p0x = bounds.right
        p1x = bounds.right - bounds.width * 0.17
        p2x = bounds.left + bounds.width * 0.7
        p3x = middle_x
        p0y = wave_base
        p1y = wave_trough
        p2y = wave_trough
        p3y = wave_base - wave_depth * 0.34
    else:
        p0x = middle_x
        p1x = bounds.left + bounds.width * 0.33
        p2x = bounds.left + bounds.width * 0.14
        p3x = bounds.left
        p0y = wave_base - wave_depth * 0.34
        p1y = wave_crest
        p2y = wave_crest
        p3y = wave_base

    t = _solve_monotonic_bezier_t_for_coordinate(target_x, p0x, p1x, p2x, p3x)
    return target_x, _cubic_bezier_coordinate(p0y, p1y, p2y, p3y, t)


def _rectilinear_flowchart_anchor(bounds: _FlowchartBounds, side: str) -> tuple[float, float]:
    if side == "top":
        return bounds.center_x, bounds.top
    if side == "right":
        return bounds.right, bounds.center_y
    if side == "bottom":
        return bounds.center_x, bounds.bottom
    return bounds.left, bounds.center_y


def _input_output_flowchart_anchor(bounds: _FlowchartBounds, side: str) -> tuple[float, float]:
    slant = min(bounds.width * 0.13, bounds.height * 0.26)
    if side == "top":
        return bounds.center_x, bounds.top
    if side == "right":
        return bounds.right - (slant * 0.5), bounds.center_y
    if side == "bottom":
        return bounds.center_x, bounds.bottom
    return bounds.left + (slant * 0.5), bounds.center_y


def _database_flowchart_anchor(bounds: _FlowchartBounds, side: str) -> tuple[float, float]:
    return _rectilinear_flowchart_anchor(bounds, side)


def _document_flowchart_anchor(bounds: _FlowchartBounds, side: str) -> tuple[float, float]:
    if side == "bottom":
        return _document_bottom_anchor(bounds)
    return _rectilinear_flowchart_anchor(bounds, side)


_FLOWCHART_ANCHOR_RESOLVERS = {
    "database": _database_flowchart_anchor,
    "document": _document_flowchart_anchor,
    "input_output": _input_output_flowchart_anchor,
}


def flowchart_anchor_local_point(
    variant: str,
    width: float,
    height: float,
    side: str,
) -> tuple[float, float]:
    normalized_variant = normalize_flowchart_variant(variant)
    normalized_side = str(side or "").strip().lower()
    bounds = _flowchart_bounds(width, height)
    if normalized_side not in CARDINAL_SIDES:
        return bounds.center_x, bounds.center_y

    resolver = _FLOWCHART_ANCHOR_RESOLVERS.get(normalized_variant, _rectilinear_flowchart_anchor)
    return resolver(bounds, normalized_side)


def flowchart_anchor_normal(side: str) -> tuple[float, float]:
    normalized_side = str(side or "").strip().lower()
    if normalized_side == "top":
        return 0.0, -1.0
    if normalized_side == "right":
        return 1.0, 0.0
    if normalized_side == "bottom":
        return 0.0, 1.0
    if normalized_side == "left":
        return -1.0, 0.0
    return 0.0, 0.0


def flowchart_anchor_tangent(side: str) -> tuple[float, float]:
    normalized_side = str(side or "").strip().lower()
    if normalized_side in {"top", "bottom"}:
        return 1.0, 0.0
    if normalized_side in {"left", "right"}:
        return 0.0, 1.0
    return 0.0, 0.0


def flowchart_port_side(
    node: NodeInstance,
    spec: NodeTypeSpec,
    port_key: str,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
) -> str:
    scoped_nodes = workspace_nodes or {node.node_id: node}
    port = find_port(
        node=node,
        spec=spec,
        workspace_nodes=scoped_nodes,
        port_key=port_key,
    )
    if port is not None:
        explicit_side = port_side(port)
        if explicit_side:
            return explicit_side
    normalized_key = str(port_key or "").strip().lower()
    return normalized_key if normalized_key in CARDINAL_SIDES else ""


def _rect_anchor_local_point(width: float, height: float, side: str) -> tuple[float, float]:
    safe_width = max(1.0, float(width))
    safe_height = max(1.0, float(height))
    left = 0.5
    top = 0.5
    right = max(left + 1.0, safe_width - 0.5)
    bottom = max(top + 1.0, safe_height - 0.5)
    center_x = (left + right) * 0.5
    center_y = (top + bottom) * 0.5
    normalized_side = str(side or "").strip().lower()
    if normalized_side == "top":
        return center_x, top
    if normalized_side == "right":
        return right, center_y
    if normalized_side == "bottom":
        return center_x, bottom
    return left, center_y


def surface_port_local_point(
    node: NodeInstance,
    spec: NodeTypeSpec,
    port_key: str,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    width: float | None = None,
    height: float | None = None,
    show_port_labels: bool = True,
    graph_label_pixel_size: object | None = None,
    graph_node_icon_pixel_size: object | None = None,
    surface_metrics: Any | None = None,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
) -> tuple[float, float]:
    scoped_nodes = workspace_nodes or {node.node_id: node}
    metrics = surface_metrics or node_surface_metrics(
        node,
        spec,
        scoped_nodes,
        show_port_labels=show_port_labels,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        visible_ports_override=visible_ports_override,
    )
    resolved_width, resolved_height = _resolved_dimensions(
        node,
        default_width=metrics.default_width,
        default_height=metrics.default_height,
    )
    if uses_content_sizing(spec):
        resolved_width, resolved_height = resolved_node_surface_size(
            node, spec, scoped_nodes, surface_metrics=metrics,
        )
    width_value = float(width) if width is not None else resolved_width
    height_value = float(height) if height is not None else resolved_height

    resolved_port = next(
        (port for port in visible_ports_override or () if str(port.key) == str(port_key)),
        None,
    )
    direction = (
        port_layout_direction(resolved_port)
        if resolved_port is not None
        else port_direction(node=node, spec=spec, workspace_nodes=scoped_nodes, port_key=port_key)
    )
    if node.collapsed:
        return (
            0.0 if direction == "in" else width_value,
            metrics.collapsed_height * 0.5,
        )

    if visible_ports_override is None:
        in_ports, out_ports = visible_ports(node=node, spec=spec, workspace_nodes=scoped_nodes)
        visible = in_ports if direction == "in" else out_ports
    else:
        visible = tuple(
            port
            for port in visible_ports_override
            if port_layout_direction(port) == direction
        )
    row_index = 0
    for index, port in enumerate(visible):
        if port.key == port_key:
            row_index = index
            break
    local_y = metrics.port_top + metrics.port_center_offset + metrics.port_height * row_index
    family = str(spec.surface_family or "standard").strip() or "standard"
    side = flowchart_port_side(node, spec, port_key, scoped_nodes)
    if side:
        if family == "flowchart":
            return flowchart_anchor_local_point(
                spec.surface_variant,
                width_value,
                height_value,
                side,
            )
        return _rect_anchor_local_point(width_value, height_value, side)
    if family == "flowchart":
        left, right = _flowchart_horizontal_bounds(
            normalize_flowchart_variant(spec.surface_variant),
            width_value,
            height_value,
            local_y,
        )
        return (left if direction == "in" else right), local_y
    # Grips sit centered on the card border (half outside), matching the
    # collapsed-node anchors above; the ring visually punches through the edge.
    if direction == "in":
        return 0.0, local_y
    return width_value, local_y
