from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ea_node_editor.graph.effective_ports import EffectivePort
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.settings import DEFAULT_GRAPH_LABEL_PIXEL_SIZE

from ea_node_editor.ui_qml.graph_geometry.anchors import (
    flowchart_anchor_local_point as _flowchart_anchor_local_point_impl,
    flowchart_anchor_normal as _flowchart_anchor_normal_impl,
    flowchart_anchor_tangent as _flowchart_anchor_tangent_impl,
    flowchart_port_side as _flowchart_port_side_impl,
    surface_port_local_point as _surface_port_local_point_impl,
)
from ea_node_editor.ui_qml.graph_geometry.flowchart_metrics import (
    _resolve_flowchart_metric_layout_state as _resolve_flowchart_metric_layout_state_impl,
    normalize_flowchart_variant as _normalize_flowchart_variant_impl,
)
from ea_node_editor.ui_qml.graph_geometry.panel_metrics import (
    _build_panel_surface_metrics as _build_panel_surface_metrics_impl,
    normalize_annotation_variant as _normalize_annotation_variant_impl,
    normalize_group_backdrop_variant as _normalize_group_backdrop_variant_impl,
    normalize_media_variant as _normalize_media_variant_impl,
    normalize_planning_variant as _normalize_planning_variant_impl,
)
from ea_node_editor.ui_qml.graph_geometry.standard_metrics import (
    node_surface_metrics as _node_surface_metrics_impl,
    resolved_node_surface_size as _resolved_node_surface_size_impl,
    standard_inline_body_height as _standard_inline_body_height_impl,
)
from ea_node_editor.ui_qml.graph_geometry.surface_contract import (
    GraphNodeSurfaceMetrics,
    _FlowchartVariantLayout,
)
from ea_node_editor.ui_qml.graph_geometry.viewer_metrics import (
    viewer_surface_contract_payload as _viewer_surface_contract_payload_impl,
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


def standard_inline_body_height(
    spec: NodeTypeSpec,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
) -> float:
    return _standard_inline_body_height_impl(
        spec,
        graph_label_pixel_size=graph_label_pixel_size,
    )


def normalize_flowchart_variant(variant: str) -> str:
    return _normalize_flowchart_variant_impl(variant)


def normalize_planning_variant(variant: str) -> str:
    return _normalize_planning_variant_impl(variant)


def normalize_annotation_variant(variant: str) -> str:
    return _normalize_annotation_variant_impl(variant)


def normalize_group_backdrop_variant(variant: str) -> str:
    return _normalize_group_backdrop_variant_impl(variant)


def normalize_media_variant(variant: str) -> str:
    return _normalize_media_variant_impl(variant)


def flowchart_anchor_local_point(
    variant: str,
    width: float,
    height: float,
    side: str,
) -> tuple[float, float]:
    return _flowchart_anchor_local_point_impl(variant, width, height, side)


def flowchart_anchor_normal(side: str) -> tuple[float, float]:
    return _flowchart_anchor_normal_impl(side)


def flowchart_anchor_tangent(side: str) -> tuple[float, float]:
    return _flowchart_anchor_tangent_impl(side)


def flowchart_port_side(
    node: NodeInstance,
    spec: NodeTypeSpec,
    port_key: str,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
) -> str:
    return _flowchart_port_side_impl(node, spec, port_key, workspace_nodes)


def _resolve_flowchart_metric_layout_state(
    node: NodeInstance,
    spec: NodeTypeSpec,
    layout: _FlowchartVariantLayout,
    workspace_nodes: Mapping[str, NodeInstance] | None,
) -> _FlowchartMetricLayoutState:
    state = _resolve_flowchart_metric_layout_state_impl(node, spec, layout, workspace_nodes)
    return _FlowchartMetricLayoutState(
        default_width=state.default_width,
        default_height=state.default_height,
        min_width=state.min_width,
        title_top=state.title_top,
        body_top=state.body_top,
        body_height=state.body_height,
        port_top=state.port_top,
    )


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
) -> GraphNodeSurfaceMetrics:
    return _build_panel_surface_metrics_impl(
        default_width=default_width,
        default_height=default_height,
        min_width=min_width,
        min_height=min_height,
        active_height=active_height,
        body_top=body_top,
        body_height=body_height,
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


def resolved_node_surface_size(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    show_port_labels: bool = True,
    surface_metrics: GraphNodeSurfaceMetrics | None = None,
    clamp_height: bool = False,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
) -> tuple[float, float]:
    return _resolved_node_surface_size_impl(
        node,
        spec,
        workspace_nodes,
        show_port_labels=show_port_labels,
        surface_metrics=surface_metrics,
        clamp_height=clamp_height,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        visible_ports_override=visible_ports_override,
    )


def node_surface_metrics(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    show_port_labels: bool = True,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
) -> GraphNodeSurfaceMetrics:
    return _node_surface_metrics_impl(
        node,
        spec,
        workspace_nodes,
        show_port_labels=show_port_labels,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        visible_ports_override=visible_ports_override,
    )


def viewer_surface_contract_payload(
    *,
    width: float,
    height: float,
    surface_metrics: GraphNodeSurfaceMetrics,
) -> dict[str, Any]:
    return _viewer_surface_contract_payload_impl(
        width=width,
        height=height,
        surface_metrics=surface_metrics,
    )


def surface_port_local_point(
    node: NodeInstance,
    spec: NodeTypeSpec,
    port_key: str,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    width: float | None = None,
    height: float | None = None,
    show_port_labels: bool = True,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
) -> tuple[float, float]:
    return _surface_port_local_point_impl(
        node,
        spec,
        port_key,
        workspace_nodes,
        width=width,
        height=height,
        show_port_labels=show_port_labels,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
    )


__all__ = [
    'GraphNodeSurfaceMetrics',
    '_FlowchartMetricLayoutState',
    '_build_panel_surface_metrics',
    '_resolve_flowchart_metric_layout_state',
    'flowchart_anchor_local_point',
    'flowchart_anchor_normal',
    'flowchart_anchor_tangent',
    'flowchart_port_side',
    'node_surface_metrics',
    'normalize_annotation_variant',
    'normalize_group_backdrop_variant',
    'normalize_flowchart_variant',
    'normalize_media_variant',
    'normalize_planning_variant',
    'resolved_node_surface_size',
    'standard_inline_body_height',
    'surface_port_local_point',
    'viewer_surface_contract_payload',
]
