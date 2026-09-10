from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QPointF, QRectF

from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.runtime_contracts import DataTypeCatalog
from ea_node_editor.ui.graph_theme import GraphThemeDefinition

from ea_node_editor.ui_qml.graph_geometry.route_endpoints import (
    node_size as _node_size_impl,
    port_scene_pos as _port_scene_pos_impl,
)
from ea_node_editor.ui_qml.graph_geometry.route_payload import (
    _EdgeLaneOffsets as _EdgeLaneOffsetsImpl,
    _ResolvedEdgePayloadContext as _ResolvedEdgePayloadContextImpl,
    _ResolvedEdgeRoute as _ResolvedEdgeRouteImpl,
    _build_edge_payload_item as _build_edge_payload_item_impl,
    _edge_payload_lane_offsets as _edge_payload_lane_offsets_impl,
    _resolve_edge_payload_context as _resolve_edge_payload_context_impl,
    _resolve_edge_route as _resolve_edge_route_impl,
    build_edge_payload as _build_edge_payload_impl,
)
from ea_node_editor.ui_qml.graph_geometry.route_pipe import (
    edge_control_points as _edge_control_points_impl,
    edge_pipe_points as _edge_pipe_points_impl,
)
from ea_node_editor.ui_qml.graph_geometry.route_styles import (
    edge_lane_offsets as _edge_lane_offsets_impl,
    normalize_flow_edge_visual_style_payload as _normalize_flow_edge_visual_style_payload_impl,
)


@dataclass(frozen=True, slots=True)
class _EdgeLaneOffsets:
    pair_by_edge_id: Mapping[str, float]
    source_by_edge_id: Mapping[str, float]
    target_by_edge_id: Mapping[str, float]

    def values_for(self, edge_id: str) -> tuple[float, float, float]:
        return (
            float(self.pair_by_edge_id.get(edge_id, 0.0)),
            float(self.source_by_edge_id.get(edge_id, 0.0)),
            float(self.target_by_edge_id.get(edge_id, 0.0)),
        )


@dataclass(frozen=True, slots=True)
class _ResolvedEdgeRoute:
    route_mode: str
    pipe_points: list[dict[str, float]]
    c1x: float
    c1y: float
    c2x: float
    c2y: float


@dataclass(frozen=True, slots=True)
class _ResolvedEdgePayloadContext:
    source_node: NodeInstance
    target_node: NodeInstance
    source_spec: NodeTypeSpec
    target_spec: NodeTypeSpec
    source_endpoint: Any
    target_endpoint: Any
    source_port_kind: str
    target_port_kind: str
    source_port_side: str
    target_port_side: str
    edge_family: str
    pair_lane: float
    source_fan: float
    target_fan: float
    lane_bias: float
    route_source_side: str
    route_target_side: str
    data_type_warning: bool
    data_type_warning_reason: str = ""


def _wrap_lane_offsets(offsets: _EdgeLaneOffsetsImpl) -> _EdgeLaneOffsets:
    return _EdgeLaneOffsets(
        pair_by_edge_id=offsets.pair_by_edge_id,
        source_by_edge_id=offsets.source_by_edge_id,
        target_by_edge_id=offsets.target_by_edge_id,
    )


def _wrap_route(route: _ResolvedEdgeRouteImpl) -> _ResolvedEdgeRoute:
    return _ResolvedEdgeRoute(
        route_mode=route.route_mode,
        pipe_points=route.pipe_points,
        c1x=route.c1x,
        c1y=route.c1y,
        c2x=route.c2x,
        c2y=route.c2y,
    )


def _wrap_context(context: _ResolvedEdgePayloadContextImpl | None) -> _ResolvedEdgePayloadContext | None:
    if context is None:
        return None
    return _ResolvedEdgePayloadContext(
        source_node=context.source_node,
        target_node=context.target_node,
        source_spec=context.source_spec,
        target_spec=context.target_spec,
        source_endpoint=context.source_endpoint,
        target_endpoint=context.target_endpoint,
        source_port_kind=context.source_port_kind,
        target_port_kind=context.target_port_kind,
        source_port_side=context.source_port_side,
        target_port_side=context.target_port_side,
        edge_family=context.edge_family,
        pair_lane=context.pair_lane,
        source_fan=context.source_fan,
        target_fan=context.target_fan,
        lane_bias=context.lane_bias,
        route_source_side=context.route_source_side,
        route_target_side=context.route_target_side,
        data_type_warning=context.data_type_warning,
        data_type_warning_reason=context.data_type_warning_reason,
    )


def node_size(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    show_port_labels: bool = True,
) -> tuple[float, float]:
    return _node_size_impl(node, spec, workspace_nodes, show_port_labels=show_port_labels)


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
    return _port_scene_pos_impl(
        node,
        spec,
        port_key,
        workspace_nodes,
        show_port_labels=show_port_labels,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
    )


def edge_lane_offsets(edges: list[EdgeInstance], grouping_key, spacing: float) -> dict[str, float]:
    return _edge_lane_offsets_impl(edges, grouping_key, spacing)


def edge_control_points(
    source: QPointF,
    target: QPointF,
    source_bounds: QRectF,
    target_bounds: QRectF,
    *,
    pair_lane: float,
    source_fan: float,
    target_fan: float,
    source_side: str = '',
    target_side: str = '',
) -> tuple[float, float, float, float]:
    return _edge_control_points_impl(
        source,
        target,
        source_bounds,
        target_bounds,
        pair_lane=pair_lane,
        source_fan=source_fan,
        target_fan=target_fan,
        source_side=source_side,
        target_side=target_side,
    )


def edge_pipe_points(
    source: QPointF,
    target: QPointF,
    source_bounds: QRectF,
    target_bounds: QRectF,
    *,
    pair_lane: float,
    source_fan: float,
    target_fan: float,
    source_side: str = '',
    target_side: str = '',
) -> list[dict[str, float]]:
    return _edge_pipe_points_impl(
        source,
        target,
        source_bounds,
        target_bounds,
        pair_lane=pair_lane,
        source_fan=source_fan,
        target_fan=target_fan,
        source_side=source_side,
        target_side=target_side,
    )


def normalize_flow_edge_visual_style_payload(visual_style: Any) -> dict[str, Any]:
    return _normalize_flow_edge_visual_style_payload_impl(visual_style)


def _edge_payload_lane_offsets(workspace_edges: list[EdgeInstance]) -> _EdgeLaneOffsets:
    return _wrap_lane_offsets(_edge_payload_lane_offsets_impl(workspace_edges))


def _resolve_edge_payload_context(
    *,
    edge: EdgeInstance,
    workspace_nodes: Mapping[str, NodeInstance],
    node_specs: Mapping[str, NodeTypeSpec],
    data_types: DataTypeCatalog,
    collapsed_proxy_backdrop_by_node_id: Mapping[str, str],
    lane_offsets: _EdgeLaneOffsets,
    show_port_labels: bool,
    graph_label_pixel_size: object | None = None,
    graph_node_icon_pixel_size: object | None = None,
    presentation_facts_by_node_id: Mapping[str, Any] | None = None,
) -> _ResolvedEdgePayloadContext | None:
    impl_lane_offsets = _EdgeLaneOffsetsImpl(
        pair_by_edge_id=lane_offsets.pair_by_edge_id,
        source_by_edge_id=lane_offsets.source_by_edge_id,
        target_by_edge_id=lane_offsets.target_by_edge_id,
    )
    return _wrap_context(
        _resolve_edge_payload_context_impl(
            edge=edge,
            workspace_nodes=workspace_nodes,
            node_specs=node_specs,
            data_types=data_types,
            collapsed_proxy_backdrop_by_node_id=collapsed_proxy_backdrop_by_node_id,
            lane_offsets=impl_lane_offsets,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            presentation_facts_by_node_id=presentation_facts_by_node_id,
        )
    )


def _resolve_edge_route(*, context: _ResolvedEdgePayloadContext) -> _ResolvedEdgeRoute:
    impl_context = _ResolvedEdgePayloadContextImpl(
        source_node=context.source_node,
        target_node=context.target_node,
        source_spec=context.source_spec,
        target_spec=context.target_spec,
        source_endpoint=context.source_endpoint,
        target_endpoint=context.target_endpoint,
        source_port_kind=context.source_port_kind,
        target_port_kind=context.target_port_kind,
        source_port_side=context.source_port_side,
        target_port_side=context.target_port_side,
        edge_family=context.edge_family,
        pair_lane=context.pair_lane,
        source_fan=context.source_fan,
        target_fan=context.target_fan,
        lane_bias=context.lane_bias,
        route_source_side=context.route_source_side,
        route_target_side=context.route_target_side,
        data_type_warning=context.data_type_warning,
        data_type_warning_reason=context.data_type_warning_reason,
    )
    return _wrap_route(_resolve_edge_route_impl(context=impl_context))


def _build_edge_payload_item(
    *,
    edge: EdgeInstance,
    graph_theme: GraphThemeDefinition | object,
    workspace_nodes: Mapping[str, NodeInstance],
    node_specs: Mapping[str, NodeTypeSpec],
    data_types: DataTypeCatalog,
    collapsed_proxy_backdrop_by_node_id: Mapping[str, str],
    lane_offsets: _EdgeLaneOffsets,
    show_port_labels: bool,
    graph_label_pixel_size: object | None = None,
    graph_node_icon_pixel_size: object | None = None,
    presentation_facts_by_node_id: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    impl_lane_offsets = _EdgeLaneOffsetsImpl(
        pair_by_edge_id=lane_offsets.pair_by_edge_id,
        source_by_edge_id=lane_offsets.source_by_edge_id,
        target_by_edge_id=lane_offsets.target_by_edge_id,
    )
    return _build_edge_payload_item_impl(
        edge=edge,
        graph_theme=graph_theme,
        workspace_nodes=workspace_nodes,
        node_specs=node_specs,
        data_types=data_types,
        collapsed_proxy_backdrop_by_node_id=collapsed_proxy_backdrop_by_node_id,
        lane_offsets=impl_lane_offsets,
        show_port_labels=show_port_labels,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        presentation_facts_by_node_id=presentation_facts_by_node_id,
    )


def build_edge_payload(
    *,
    graph_theme: GraphThemeDefinition | object,
    workspace_edges: list[EdgeInstance],
    workspace_nodes: dict[str, NodeInstance],
    node_specs: dict[str, NodeTypeSpec],
    data_types: DataTypeCatalog,
    collapsed_proxy_backdrop_by_node_id: Mapping[str, str] | None = None,
    show_port_labels: bool = True,
    graph_label_pixel_size: object | None = None,
    graph_node_icon_pixel_size: object | None = None,
    presentation_facts_by_node_id: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return _build_edge_payload_impl(
        graph_theme=graph_theme,
        workspace_edges=workspace_edges,
        workspace_nodes=workspace_nodes,
        node_specs=node_specs,
        data_types=data_types,
        collapsed_proxy_backdrop_by_node_id=collapsed_proxy_backdrop_by_node_id,
        show_port_labels=show_port_labels,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        presentation_facts_by_node_id=presentation_facts_by_node_id,
    )


__all__ = [
    '_EdgeLaneOffsets',
    '_ResolvedEdgePayloadContext',
    '_ResolvedEdgeRoute',
    '_build_edge_payload_item',
    '_edge_payload_lane_offsets',
    '_resolve_edge_payload_context',
    '_resolve_edge_route',
    'build_edge_payload',
    'edge_control_points',
    'edge_lane_offsets',
    'edge_pipe_points',
    'node_size',
    'normalize_flow_edge_visual_style_payload',
    'port_scene_pos',
]
