from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QPointF, QRectF

from ea_node_editor.graph.effective_ports import port_direction
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.node_specs import NodeTypeSpec

from .anchors import flowchart_port_side, surface_port_local_point
from .standard_metrics import node_surface_metrics, resolved_node_surface_size

EDGE_PROXY_PERIMETER_INSET = 12.0
_CARDINAL_SIDES = frozenset({"top", "right", "bottom", "left"})


@dataclass(frozen=True, slots=True)
class _ResolvedEdgeEndpoint:
    anchor_node_id: str
    anchor_kind: str
    hidden_by_backdrop_id: str
    side: str
    point: QPointF
    bounds: QRectF


def node_size(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    show_port_labels: bool = True,
) -> tuple[float, float]:
    return resolved_node_surface_size(
        node,
        spec,
        workspace_nodes,
        show_port_labels=show_port_labels,
    )


def port_scene_pos(
    node: NodeInstance,
    spec: NodeTypeSpec,
    port_key: str,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    show_port_labels: bool = True,
    graph_label_pixel_size: object | None = None,
    graph_node_icon_pixel_size: object | None = None,
) -> QPointF:
    scoped_nodes = workspace_nodes or {node.node_id: node}
    metrics = node_surface_metrics(
        node,
        spec,
        scoped_nodes,
        show_port_labels=show_port_labels,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
    )
    width, height = node_size(
        node,
        spec,
        scoped_nodes,
        show_port_labels=show_port_labels,
    )

    if node.collapsed:
        direction = port_direction(node=node, spec=spec, workspace_nodes=scoped_nodes, port_key=port_key)
        if direction == "in":
            return QPointF(node.x, node.y + (metrics.collapsed_height * 0.5))
        return QPointF(node.x + width, node.y + (metrics.collapsed_height * 0.5))

    local_x, local_y = surface_port_local_point(
        node,
        spec,
        port_key,
        scoped_nodes,
        width=width,
        height=height,
        show_port_labels=show_port_labels,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
    )
    return QPointF(node.x + local_x, node.y + local_y)


def _is_flowchart_surface(spec: NodeTypeSpec) -> bool:
    return str(spec.surface_family or "").strip() == "flowchart"


def _flowchart_decision_source_fan_bias(spec: NodeTypeSpec, source_port_key: str) -> float:
    if not _is_flowchart_surface(spec):
        return 0.0
    if str(spec.surface_variant or "").strip() != "decision":
        return 0.0
    if source_port_key == "branch_a":
        return -12.0
    if source_port_key == "branch_b":
        return 12.0
    return 0.0


def _rect_center_x(bounds: QRectF) -> float:
    return float(bounds.left() + bounds.width() * 0.5)


def _rect_center(bounds: QRectF) -> QPointF:
    return QPointF(float(bounds.left() + bounds.width() * 0.5), float(bounds.top() + bounds.height() * 0.5))


def _node_bounds(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    show_port_labels: bool = True,
) -> QRectF:
    width, height = node_size(
        node,
        spec,
        workspace_nodes,
        show_port_labels=show_port_labels,
    )
    return QRectF(float(node.x), float(node.y), float(width), float(height))


def _presentation_bounds(
    presentation_facts_by_node_id: Mapping[str, Any] | None,
    node_id: str,
) -> QRectF | None:
    facts = None if presentation_facts_by_node_id is None else presentation_facts_by_node_id.get(node_id)
    bounds = getattr(facts, "bounds", None)
    if bounds is None:
        return None
    return QRectF(
        float(bounds.x),
        float(bounds.y),
        float(bounds.width),
        float(bounds.height),
    )


def _presentation_port_anchor(
    presentation_facts_by_node_id: Mapping[str, Any] | None,
    node_id: str,
    port_key: str,
) -> tuple[str, QPointF, QRectF] | None:
    facts = None if presentation_facts_by_node_id is None else presentation_facts_by_node_id.get(node_id)
    endpoint_by_port_key = getattr(facts, "endpoint_by_port_key", None)
    anchor = endpoint_by_port_key.get(str(port_key)) if isinstance(endpoint_by_port_key, Mapping) else None
    bounds = _presentation_bounds(presentation_facts_by_node_id, node_id)
    if anchor is None or bounds is None:
        return None
    return str(anchor.side), QPointF(float(anchor.x), float(anchor.y)), bounds


def _clamp(value: float, low: float, high: float) -> float:
    if low > high:
        return (low + high) * 0.5
    return min(high, max(low, value))


def _proxy_perimeter_side(bounds: QRectF, *, toward: QPointF | None) -> str:
    center = _rect_center(bounds)
    target = toward if toward is not None else center
    dx = float(target.x() - center.x())
    dy = float(target.y() - center.y())
    if abs(dx) >= abs(dy):
        return "right" if dx >= 0.0 else "left"
    return "bottom" if dy >= 0.0 else "top"


def _normalized_cardinal_side(side: str, *, fallback: str = "") -> str:
    normalized = str(side or "").strip().lower()
    if normalized in _CARDINAL_SIDES:
        return normalized
    return fallback


def _flow_pipe_route_sides(source_side: str = "", target_side: str = "") -> tuple[str, str]:
    return (
        _normalized_cardinal_side(source_side, fallback="right"),
        _normalized_cardinal_side(target_side, fallback="left"),
    )


def _proxy_anchor_point(bounds: QRectF, side: str, *, toward: QPointF | None) -> QPointF:
    normalized_side = _normalized_cardinal_side(side, fallback="right")
    target = toward if toward is not None else _rect_center(bounds)
    inset_x = min(EDGE_PROXY_PERIMETER_INSET, max(0.0, float(bounds.width()) * 0.5))
    inset_y = min(EDGE_PROXY_PERIMETER_INSET, max(0.0, float(bounds.height()) * 0.5))
    min_x = float(bounds.left()) + inset_x
    max_x = float(bounds.right()) - inset_x
    min_y = float(bounds.top()) + inset_y
    max_y = float(bounds.bottom()) - inset_y
    if normalized_side == "left":
        return QPointF(float(bounds.left()), _clamp(float(target.y()), min_y, max_y))
    if normalized_side == "right":
        return QPointF(float(bounds.right()), _clamp(float(target.y()), min_y, max_y))
    if normalized_side == "top":
        return QPointF(_clamp(float(target.x()), min_x, max_x), float(bounds.top()))
    return QPointF(_clamp(float(target.x()), min_x, max_x), float(bounds.bottom()))


def _rect_payload(bounds: QRectF) -> dict[str, float]:
    return {
        "x": float(bounds.left()),
        "y": float(bounds.top()),
        "width": float(bounds.width()),
        "height": float(bounds.height()),
    }


def _resolve_edge_endpoint(
    *,
    node_id: str,
    port_key: str,
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
    node_specs: Mapping[str, NodeTypeSpec],
    hidden_by_backdrop_id: str = "",
    opposite_point: QPointF | None = None,
    show_port_labels: bool = True,
    graph_label_pixel_size: object | None = None,
    graph_node_icon_pixel_size: object | None = None,
    presentation_facts_by_node_id: Mapping[str, Any] | None = None,
) -> _ResolvedEdgeEndpoint:
    normalized_hidden_by_backdrop_id = str(hidden_by_backdrop_id or "").strip()
    if normalized_hidden_by_backdrop_id:
        backdrop_node = workspace_nodes.get(normalized_hidden_by_backdrop_id)
        backdrop_spec = node_specs.get(normalized_hidden_by_backdrop_id)
        if backdrop_node is not None and backdrop_spec is not None:
            backdrop_bounds = _presentation_bounds(
                presentation_facts_by_node_id,
                normalized_hidden_by_backdrop_id,
            )
            if backdrop_bounds is None:
                backdrop_bounds = _node_bounds(
                    backdrop_node,
                    backdrop_spec,
                    workspace_nodes,
                    show_port_labels=show_port_labels,
                )
            anchor_side = _proxy_perimeter_side(backdrop_bounds, toward=opposite_point)
            anchor_point = _proxy_anchor_point(backdrop_bounds, anchor_side, toward=opposite_point)
            return _ResolvedEdgeEndpoint(
                anchor_node_id=normalized_hidden_by_backdrop_id,
                anchor_kind="collapsed_backdrop",
                hidden_by_backdrop_id=normalized_hidden_by_backdrop_id,
                side=anchor_side,
                point=anchor_point,
                bounds=backdrop_bounds,
            )

    presentation_anchor = _presentation_port_anchor(
        presentation_facts_by_node_id,
        node_id,
        port_key,
    )
    if presentation_anchor is not None:
        anchor_side, anchor_point, anchor_bounds = presentation_anchor
        return _ResolvedEdgeEndpoint(
            anchor_node_id=node_id,
            anchor_kind="node",
            hidden_by_backdrop_id="",
            side=anchor_side,
            point=anchor_point,
            bounds=anchor_bounds,
        )

    anchor_side = flowchart_port_side(node, spec, port_key, workspace_nodes)
    return _ResolvedEdgeEndpoint(
        anchor_node_id=node_id,
        anchor_kind="node",
        hidden_by_backdrop_id="",
        side=anchor_side,
        point=port_scene_pos(
            node,
            spec,
            port_key,
            workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        ),
        bounds=_node_bounds(
            node,
            spec,
            workspace_nodes,
            show_port_labels=show_port_labels,
        ),
    )
