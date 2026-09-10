from __future__ import annotations

"""Per-node payload assembly factory."""


import copy
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any


from ea_node_editor.graph.boundary_adapters import GraphBoundaryAdapters
from ea_node_editor.graph.effective_ports import (
    EffectivePort,
    effective_ports,
    ordered_ports_for_display,
    port_layout_direction,
    port_side,
)
from ea_node_editor.graph.node_comments import node_comment_badge_payload, node_comments_to_payload
from ea_node_editor.graph.node_links import node_links_to_payload
from ea_node_editor.graph.transform_layout_ops import LayoutNodeBounds
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.nodes.builtins.subnode import is_subnode_shell_type
from ea_node_editor.nodes.plugin_contracts import PluginProvenance
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.addons.property_edit_adapters import (
    PropertyEditAdapterContext,
    build_property_items_with_adapters,
)
from ea_node_editor.settings import (
    DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
)
from ea_node_editor.ui.graph_theme import GraphThemeDefinition
from ea_node_editor.ui.port_availability import (
    port_availability_for_node,
)
from ea_node_editor.ui.support.node_presentation import (
    build_inline_property_items,
    project_port_data_type_presentation,
    qml_safe_spec_property_value,
)
from ea_node_editor.ui.support.port_flow_state import resolve_port_flow_state
from ea_node_editor.ui_qml.graph_geometry.standard_metrics import (
    node_surface_metrics as standard_node_surface_metrics,
    resolved_node_surface_size as resolved_standard_node_surface_size,
    standard_inline_label_anchor_offset,
    standard_inline_property_row_height,
    uses_content_sizing,
)
from ea_node_editor.ui_qml.graph_geometry.anchors import surface_port_local_point
from ea_node_editor.ui_qml.graph_geometry.surface_contract import CARDINAL_SIDES
from ea_node_editor.ui_qml.graph_surface_metrics import (
    node_surface_metrics as default_node_surface_metrics,
    resolved_node_surface_size as default_resolved_node_surface_size,
)
from ea_node_editor.ui_qml.node_title_icon_sources import (
    title_icon_presentation_for_node_payload,
)
from ea_node_editor.ui_qml.surface_contracts import (
    surface_spec_payload_for_values,
)

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge

from ea_node_editor.ui_qml.graph_scene_payload.kinds import kind_dispatch_for_spec
from ea_node_editor.ui_qml.graph_scene_payload.kinds.plot import _plot_type_from_node_payload
from ea_node_editor.ui_qml.graph_scene_payload.normalize import (
    _is_standard_surface,
    _surface_spec_payload_for_node,
    _uses_dynamic_title_band_surface,
)


_SETTINGS_BAND_BOTTOM_CLEARANCE = 18.0


@dataclass(frozen=True, slots=True)
class PayloadBuildContext:
    """Frozen per-node build inputs handed to kind contributors.

    New build inputs are added HERE once, not threaded through contributor
    signatures. `node` is the original graph node; `layout_node` is the
    payload-normalized clone the base assembly renders from.
    """

    node: Any
    layout_node: Any
    spec: NodeTypeSpec
    provenance: PluginProvenance | None
    workspace: WorkspaceData
    workspace_nodes: dict[str, Any]
    port_connection_counts: dict[tuple[str, str], int]
    graph_theme: GraphThemeDefinition
    graph_theme_bridge: "GraphThemeBridge | None"
    surface_metrics: Any
    width: float
    height: float
    hide_optional_ports: bool
    show_port_labels: bool
    graph_label_pixel_size: int
    graph_node_icon_pixel_size: int
    lightweight_canvas: bool
    boundary_adapters: GraphBoundaryAdapters
    previous_payload: Mapping[str, Any] | None = None
    changed_fields: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class _PortEndpointFacts:
    side: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class _PortPresentationItem:
    layout_row: int
    settings_group_id: str = ""
    settings_member_index: int = -1
    settings_property_key: str = ""
    handle_visible: bool = True
    presentation_anchor: _PortEndpointFacts | None = None


@dataclass(frozen=True, slots=True)
class _PortPresentationLayout:
    total_row_count: int
    item_by_port_key: Mapping[str, _PortPresentationItem]
    settings_band: Mapping[str, float]
    settings_groups: tuple[Mapping[str, Any], ...]
    grouped_property_keys: frozenset[str]


def _readiness_payload_for_spec(
    spec: NodeTypeSpec,
    ports: tuple[EffectivePort, ...],
) -> dict[str, Any]:
    """Project validated readiness metadata as QML-safe primitive values."""
    return {
        "ports": [
            {
                "key": str(port.key),
                "label": str(port.label or port.key),
                "direction": str(port.direction),
                "kind": str(port.kind),
                "required": port.required,
                "uses_property_default": bool(port.uses_property_default),
                "allow_empty_string": bool(port.allow_empty_string),
            }
            for port in ports
        ],
        "property_labels": {
            str(prop.key): str(prop.label or prop.key) for prop in spec.properties
        },
        "requirements": [
            {
                "any_of_ports": [str(key) for key in requirement.any_of_ports],
                "any_of_properties": [
                    str(key) for key in requirement.any_of_properties
                ],
                "when_ports_present": [
                    str(key) for key in requirement.when_ports_present
                ],
                "when_properties": [
                    {
                        "property_key": str(condition.property_key),
                        "values": copy.deepcopy(list(condition.values)),
                    }
                    for condition in requirement.when_properties
                ],
            }
            for requirement in getattr(spec, "readiness_requirements", ())
        ],
    }


def _dynamic_port_groups_payload(
    spec: NodeTypeSpec,
    ports: tuple[EffectivePort, ...],
    properties: Mapping[str, object],
) -> list[dict[str, Any]]:
    dynamic_ports = ports[len(spec.ports) :]
    payload: list[dict[str, Any]] = []
    for group in spec.dynamic_port_groups:
        group_ports = group.ports_resolver(properties) if group.property_editor is not None else dynamic_ports
        keys = [
            port.key
            for port in group_ports
            if port.direction == group.direction
        ]
        payload.append(
            {
                "id": group.group_id,
                "direction": group.direction,
                "port_keys": keys,
                "can_insert": group.maximum is None or len(keys) < group.maximum,
                "removable_port_keys": keys if len(keys) > group.minimum else [],
                "rename_mode": group.rename_mode,
            }
        )
    return payload


@dataclass(frozen=True, slots=True)
class _NodePresentationFacts:
    original_node: Any
    payload_node: Any
    final_node: Any
    spec: NodeTypeSpec
    provenance: PluginProvenance | None
    visible_ports: tuple[EffectivePort, ...]
    visible_port_by_key: Mapping[str, EffectivePort]
    surface_metrics: Any
    width: float
    height: float
    bounds: LayoutNodeBounds
    expanded_bounds: LayoutNodeBounds
    minimap_bounds: LayoutNodeBounds
    membership_width: float
    membership_height: float
    port_presentation: _PortPresentationLayout
    inline_properties: tuple[Mapping[str, Any], ...]
    endpoint_by_port_key: Mapping[str, _PortEndpointFacts]
    icon_source: str
    icon_theme_aware: bool
    is_group_backdrop: bool


class _GraphSceneNodePayloadFactory:
    def __init__(self, boundary_adapters: GraphBoundaryAdapters, current_input_provider: Any = None, property_edit_adapters: Any = (), *, keep_expanded_node_width_provider: Callable[[], bool] | None = None) -> None:
        self._boundary_adapters = boundary_adapters
        self._current_input_provider = current_input_provider
        self._property_edit_adapters = tuple(property_edit_adapters or ())
        self._keep_expanded_node_width_provider = keep_expanded_node_width_provider

    def _surface_metrics(
        self,
        *,
        node,
        spec: NodeTypeSpec,
        workspace_nodes: dict[str, Any],
        show_port_labels: bool,
        graph_label_pixel_size: int,
        graph_node_icon_pixel_size: int,
        visible_ports_override: tuple[EffectivePort, ...] | None = None,
    ):
        if _is_standard_surface(spec):
            return standard_node_surface_metrics(
                node,
                spec,
                workspace_nodes,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                visible_ports_override=visible_ports_override,
                keep_expanded_node_width=(
                    bool(self._keep_expanded_node_width_provider())
                    if self._keep_expanded_node_width_provider is not None else False
                ),
            )
        return default_node_surface_metrics(
            node,
            spec,
            workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            visible_ports_override=visible_ports_override,
        )

    @staticmethod
    def _port_connection_count(
        *,
        node_id: str,
        port_key: str,
        port_connection_counts: Mapping[tuple[str, str], int],
    ) -> int:
        return int(
            port_connection_counts.get(
                (node_id, port_key),
                port_connection_counts.get((str(node_id), str(port_key)), 0),
            )
        )

    @classmethod
    def _port_presentation_layout(
        cls,
        *,
        node,
        spec: NodeTypeSpec,
        visible_ports: tuple[EffectivePort, ...],
        inline_property_by_key: Mapping[str, Mapping[str, Any]],
        port_connection_counts: Mapping[tuple[str, str], int],
        surface_metrics: Any,
        graph_label_pixel_size: int,
        settings_band_top: float = 0.0,
        node_width: float = 0.0,
    ) -> _PortPresentationLayout:
        ordered_ports = ordered_ports_for_display(visible_ports)
        settings_groups = tuple(getattr(spec, "settings_groups", ()) or ())
        grouped_port_keys = {
            str(item.port_key)
            for group in settings_groups
            for item in group.items
            if str(item.port_key)
        }
        default_property_keys = frozenset(
            str(port.key)
            for port in spec.ports
            if str(port.direction) == "in" and bool(port.uses_property_default)
        )
        grouped_property_keys = frozenset(
            str(item.property_key)
            for group in settings_groups
            for item in group.items
            if str(item.property_key) and str(item.property_key) not in default_property_keys
        )
        item_by_key: dict[str, _PortPresentationItem] = {}
        row_by_direction = {"in": 0, "out": 0}
        max_row = -1
        for port in ordered_ports:
            if str(port.key) in grouped_port_keys:
                continue
            direction = port_layout_direction(port)
            if direction not in row_by_direction:
                direction = "out"
            row = row_by_direction[direction]
            default_payload = (
                inline_property_by_key.get(str(port.key))
                if str(port.key) in default_property_keys
                else None
            )
            editor = str((default_payload or {}).get("inline_editor", "")).strip().lower()
            base_port_height = max(1.0, float(surface_metrics.port_height))
            editor_row_height = standard_inline_property_row_height(
                editor,
                graph_label_pixel_size=graph_label_pixel_size,
                list_value=(
                    default_payload.get("display_value", default_payload.get("value"))
                    if default_payload is not None
                    else None
                ),
            )
            row_height = (
                max(base_port_height, editor_row_height)
                if default_payload
                else base_port_height
            )
            row_span = max(1, int(math.ceil(row_height / base_port_height)))
            presentation_anchor = None
            if row_span > 1 and node_width > 0.0:
                presentation_anchor = _PortEndpointFacts(
                    side="left" if direction == "in" else "right",
                    x=0.0 if direction == "in" else float(node_width),
                    y=(
                        float(surface_metrics.port_top)
                        + float(surface_metrics.port_height) * row
                        + standard_inline_label_anchor_offset(graph_label_pixel_size)
                    ),
                )
            item_by_key[str(port.key)] = _PortPresentationItem(
                row,
                presentation_anchor=presentation_anchor,
            )
            row_by_direction[direction] = row + row_span
            max_row = max(max_row, row + row_span - 1)

        if not settings_groups:
            return _PortPresentationLayout(
                total_row_count=max_row + 1,
                item_by_port_key=MappingProxyType(item_by_key),
                settings_band=MappingProxyType({}),
                settings_groups=(),
                grouped_property_keys=frozenset(),
            )

        visible_port_by_key = {str(port.key): port for port in ordered_ports}
        expanded_group_ids = {
            str(group_id)
            for group_id in getattr(node, "expanded_settings_group_ids", ()) or ()
        }
        band_visible = not bool(getattr(node, "collapsed", False))
        header_height = max(1.0, float(surface_metrics.port_height))
        cursor_y = float(settings_band_top)
        groups_payload: list[Mapping[str, Any]] = []
        node_id = str(getattr(node, "node_id", ""))

        for group in settings_groups:
            group_id = str(group.group_id)
            expanded = group_id in expanded_group_ids
            effective_expanded = expanded and band_visible
            header_y = cursor_y
            if band_visible:
                cursor_y += header_height
            group_port_keys = tuple(
                str(item.port_key)
                for item in group.items
                if str(item.port_key) in visible_port_by_key
            )
            aggregate_anchor = (
                {
                    "side": "left",
                    "x": 0.0,
                    "y": header_y + header_height * 0.5,
                    "aggregate": True,
                    "connected_count": sum(
                        cls._port_connection_count(
                            node_id=node_id,
                            port_key=port_key,
                            port_connection_counts=port_connection_counts,
                        )
                        for port_key in group_port_keys
                    ),
                }
                if group_port_keys
                else None
            )
            items_payload: list[dict[str, Any]] = []
            for member_index, item in enumerate(group.items):
                port_key = str(item.port_key)
                property_key = str(item.property_key)
                if property_key in default_property_keys:
                    property_key = ""
                property_payload = inline_property_by_key.get(property_key)
                if port_key and port_key not in visible_port_by_key and not property_key:
                    continue
                default_payload = (
                    inline_property_by_key.get(port_key)
                    if port_key in default_property_keys
                    else None
                )
                editor_payload = property_payload or default_payload
                editor = str((editor_payload or {}).get("inline_editor", "")).strip().lower()
                property_height = standard_inline_property_row_height(
                    editor,
                    graph_label_pixel_size=graph_label_pixel_size,
                    list_value=(
                        editor_payload.get("display_value", editor_payload.get("value"))
                        if editor_payload is not None
                        else None
                    ),
                )
                row_height = (
                    max(header_height, property_height)
                    if editor_payload is not None
                    else header_height
                )
                item_y = cursor_y
                item_visible = bool(effective_expanded)
                if item_visible:
                    cursor_y += row_height
                kind = "paired" if port_key and property_key else ("port" if port_key else "property")
                item_payload: dict[str, Any] = {
                    "kind": kind,
                    "port_key": port_key,
                    "property_key": property_key,
                    "y": float(item_y),
                    "height": float(row_height),
                    "visible": item_visible,
                }
                if property_payload is not None:
                    item_payload["property"] = dict(property_payload)
                items_payload.append(item_payload)

                if port_key and port_key in visible_port_by_key:
                    anchor_payload = (
                        {
                            "side": "left",
                            "x": 0.0,
                            "y": item_y
                            + (
                                standard_inline_label_anchor_offset(graph_label_pixel_size)
                                if property_payload is not None or default_payload is not None
                                else row_height * 0.5
                            ),
                            "aggregate": False,
                        }
                        if item_visible
                        else aggregate_anchor
                    )
                    item_by_key[port_key] = _PortPresentationItem(
                        layout_row=-1,
                        settings_group_id=group_id,
                        settings_member_index=member_index,
                        settings_property_key=property_key,
                        handle_visible=item_visible,
                        presentation_anchor=(
                            _PortEndpointFacts(
                                side=str(anchor_payload["side"]),
                                x=float(anchor_payload["x"]),
                                y=float(anchor_payload["y"]),
                            )
                            if anchor_payload is not None
                            else None
                        ),
                    )
            groups_payload.append(
                MappingProxyType(
                    {
                        "group_id": group_id,
                        "label": str(group.label),
                        "expanded": expanded,
                        "header": {
                            "x": 0.0,
                            "y": float(header_y),
                            "width": max(0.0, float(node_width)),
                            "height": float(header_height),
                        },
                        "aggregate_anchor": aggregate_anchor,
                        "items": items_payload,
                    }
                )
            )

        band_height = (
            max(0.0, cursor_y - float(settings_band_top))
            + _SETTINGS_BAND_BOTTOM_CLEARANCE
            if band_visible
            else 0.0
        )
        return _PortPresentationLayout(
            total_row_count=max_row + 1,
            item_by_port_key=MappingProxyType(item_by_key),
            settings_band=MappingProxyType(
                {"top": float(settings_band_top), "height": float(band_height)}
            ),
            settings_groups=tuple(groups_payload),
            grouped_property_keys=grouped_property_keys,
        )

    def build_inline_properties_payload(
        self,
        *,
        node,
        spec: NodeTypeSpec,
        workspace_nodes: Mapping[str, Any],
        enabled_input_port_keys: set[str] | frozenset[str],
        port_connection_counts: Mapping[tuple[str, str], int],
    ) -> list[dict[str, Any]]:
        if not spec.properties:
            return []
        items = build_inline_property_items(
            node=node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            enabled_input_port_keys=enabled_input_port_keys,
            port_connection_counts=port_connection_counts,
        )
        return build_property_items_with_adapters(
            self._property_edit_adapters,
            PropertyEditAdapterContext(
                node=node,
                spec=spec,
                workspace_nodes=workspace_nodes,
                workspace_edges=getattr(self, "_workspace_edges", ()),
                current_output_provider=self._current_input_provider,
            ),
            items,
        )

    @classmethod
    def view_visible_ports(
        cls,
        *,
        node,
        spec: NodeTypeSpec,
        workspace_nodes: dict[str, Any],
        port_connection_counts: Mapping[tuple[str, str], int],
        hide_optional_ports: bool,
    ) -> tuple[EffectivePort, ...]:
        node_id = str(node.node_id)
        return tuple(
            port
            for port in effective_ports(
                node=node,
                spec=spec,
                workspace_nodes=workspace_nodes,
            )
            if port.exposed
            and (
                not hide_optional_ports
                or port.required
                or cls._port_connection_count(
                    node_id=node_id,
                    port_key=str(port.key),
                    port_connection_counts=port_connection_counts,
                )
                > 0
            )
        )

    @staticmethod
    def _layout_ports_override(
        *,
        visible_ports: tuple[EffectivePort, ...],
        hide_optional_ports: bool,
    ) -> tuple[EffectivePort, ...] | None:
        if hide_optional_ports:
            return visible_ports
        return None

    @staticmethod
    def _metrics_with_row_count(
        metrics,
        *,
        visible_ports_override: tuple[EffectivePort, ...] | None,
        row_count_override: int | None,
        extra_height: float = 0.0,
    ):
        counts = {"in": 0, "out": 0}
        for port in visible_ports_override or ():
            direction = port_layout_direction(port)
            if direction in counts:
                counts[direction] += 1
        current_rows = max(counts.values(), default=0)
        row_delta = (
            int(row_count_override) - current_rows
            if visible_ports_override is not None and row_count_override is not None
            else 0
        )
        height_delta = float(metrics.port_height) * row_delta + max(0.0, float(extra_height))
        if height_delta == 0.0:
            return metrics
        return replace(
            metrics,
            default_height=max(1.0, float(metrics.default_height) + height_delta),
            min_height=max(1.0, float(metrics.min_height) + height_delta),
        )

    def _filtered_layout_node(
        self,
        *,
        node,
        spec: NodeTypeSpec,
        workspace_nodes: dict[str, Any],
        show_port_labels: bool,
        graph_label_pixel_size: int,
        graph_node_icon_pixel_size: int,
        visible_ports_override: tuple[EffectivePort, ...] | None,
        row_count_override: int | None = None,
    ):
        if visible_ports_override is None or bool(getattr(node, "collapsed", False)):
            return node
        if getattr(node, "custom_height", None) is None:
            return node

        baseline_node = node.clone()
        baseline_node.custom_height = None
        unfiltered_metrics = self._surface_metrics(
            node=baseline_node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
        filtered_metrics = self._surface_metrics(
            node=baseline_node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            visible_ports_override=visible_ports_override,
        )
        filtered_metrics = self._metrics_with_row_count(
            filtered_metrics,
            visible_ports_override=visible_ports_override,
            row_count_override=(
                None
                if _is_standard_surface(spec)
                else row_count_override
            ),
        )
        removed_height = max(0.0, float(unfiltered_metrics.default_height) - float(filtered_metrics.default_height))
        if removed_height <= 0.0:
            return node

        layout_node = node.clone()
        layout_node.custom_height = max(
            float(filtered_metrics.min_height),
            float(node.custom_height) - removed_height,
        )
        return layout_node

    def _layout_metrics_and_size(
        self,
        *,
        node,
        spec: NodeTypeSpec,
        workspace_nodes: dict[str, Any],
        show_port_labels: bool,
        graph_label_pixel_size: int,
        graph_node_icon_pixel_size: int,
        visible_ports_override: tuple[EffectivePort, ...] | None,
        row_count_override: int | None = None,
        settings_band_height: float = 0.0,
    ):
        layout_node = self._filtered_layout_node(
            node=node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            visible_ports_override=visible_ports_override,
            row_count_override=None,
        )
        metrics_node = layout_node
        if (
            settings_band_height > 0.0
            and not bool(getattr(layout_node, "collapsed", False))
            and getattr(layout_node, "custom_height", None) is not None
        ):
            metrics_node = layout_node.clone()
            metrics_node.custom_height = max(
                1.0,
                float(layout_node.custom_height) - float(settings_band_height),
            )
        surface_metrics = self._surface_metrics(
            node=metrics_node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            visible_ports_override=visible_ports_override,
        )
        surface_metrics = self._metrics_with_row_count(
            surface_metrics,
            visible_ports_override=visible_ports_override,
            row_count_override=(
                None
                if _is_standard_surface(spec)
                else row_count_override
            ),
            extra_height=settings_band_height,
        )
        if visible_ports_override is None and not uses_content_sizing(spec):
            width, height = self._boundary_adapters.node_size(
                layout_node,
                spec,
                workspace_nodes,
                show_port_labels=show_port_labels,
            )
        else:
            width, height = default_resolved_node_surface_size(
                layout_node,
                spec,
                workspace_nodes,
                show_port_labels=show_port_labels,
                surface_metrics=surface_metrics,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                visible_ports_override=visible_ports_override,
            )
        return layout_node, surface_metrics, width, height

    def _presentation_layout_and_size(
        self,
        *,
        node,
        spec: NodeTypeSpec,
        workspace_nodes: dict[str, Any],
        enabled_input_port_keys: set[str] | frozenset[str],
        port_connection_counts: Mapping[tuple[str, str], int],
        visible_ports: tuple[EffectivePort, ...],
        show_port_labels: bool,
        graph_label_pixel_size: int,
        graph_node_icon_pixel_size: int,
    ):
        inline_properties = tuple(
            self.build_inline_properties_payload(
                node=node,
                spec=spec,
                workspace_nodes=workspace_nodes,
                enabled_input_port_keys=enabled_input_port_keys,
                port_connection_counts=port_connection_counts,
            )
        )
        inline_property_by_key = {
            str(item.get("key", "")): item
            for item in inline_properties
            if str(item.get("key", ""))
        }
        initial_metrics = self._surface_metrics(
            node=node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            visible_ports_override=visible_ports,
        )
        preliminary_layout = self._port_presentation_layout(
            node=node,
            spec=spec,
            visible_ports=visible_ports,
            inline_property_by_key=inline_property_by_key,
            port_connection_counts=port_connection_counts,
            surface_metrics=initial_metrics,
            graph_label_pixel_size=graph_label_pixel_size,
        )
        settings_band_height = float(preliminary_layout.settings_band.get("height", 0.0))
        layout_node, surface_metrics, width, height = self._layout_metrics_and_size(
            node=node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            visible_ports_override=visible_ports,
            row_count_override=preliminary_layout.total_row_count,
            settings_band_height=settings_band_height,
        )
        port_presentation = self._port_presentation_layout(
            node=layout_node,
            spec=spec,
            visible_ports=visible_ports,
            inline_property_by_key=inline_property_by_key,
            port_connection_counts=port_connection_counts,
            surface_metrics=surface_metrics,
            graph_label_pixel_size=graph_label_pixel_size,
            settings_band_top=max(0.0, float(height) - settings_band_height),
            node_width=float(width),
        )
        return (
            layout_node,
            surface_metrics,
            float(width),
            float(height),
            port_presentation,
            inline_properties,
        )

    def _resolved_payload_node(
        self,
        *,
        node,
        spec: NodeTypeSpec,
        workspace_nodes: dict[str, Any],
        show_port_labels: bool,
        graph_label_pixel_size: int,
        graph_node_icon_pixel_size: int,
    ):
        payload_node = self.payload_node(node, spec)
        if not _uses_dynamic_title_band_surface(spec):
            return payload_node
        if payload_node is node:
            payload_node = node.clone()
        surface_metrics = self._surface_metrics(
            node=payload_node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
        width, height = resolved_standard_node_surface_size(
            payload_node,
            spec,
            workspace_nodes,
            show_port_labels=show_port_labels,
            surface_metrics=surface_metrics,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
        payload_node.custom_width = float(width)
        payload_node.custom_height = float(height)
        return payload_node

    def build_presentation_facts(
        self,
        *,
        node,
        spec: NodeTypeSpec,
        provenance: PluginProvenance | None,
        workspace_nodes: dict[str, Any],
        enabled_input_port_keys: set[str] | frozenset[str],
        port_connection_counts: Mapping[tuple[str, str], int],
        hide_optional_ports: bool,
        show_port_labels: bool,
        graph_label_pixel_size: int,
        graph_node_icon_pixel_size: int,
    ) -> _NodePresentationFacts:
        payload_node = self.payload_node(node, spec)
        node_id = str(node.node_id)
        workspace_nodes[node_id] = payload_node
        visible_ports = self.view_visible_ports(
            node=payload_node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            port_connection_counts=port_connection_counts,
            hide_optional_ports=hide_optional_ports,
        )
        (
            final_node,
            surface_metrics,
            width,
            height,
            port_presentation,
            inline_properties,
        ) = self._presentation_layout_and_size(
            node=payload_node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            enabled_input_port_keys=enabled_input_port_keys,
            port_connection_counts=port_connection_counts,
            visible_ports=visible_ports,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
        bounds = LayoutNodeBounds(
            node_id=node_id,
            x=float(final_node.x),
            y=float(final_node.y),
            width=max(1.0, float(width)),
            height=max(1.0, float(height)),
        )
        expanded_bounds = self._expanded_bounds_for_facts(
            original_node=node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            enabled_input_port_keys=enabled_input_port_keys,
            port_connection_counts=port_connection_counts,
            hide_optional_ports=hide_optional_ports,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            fallback=bounds,
        )
        endpoint_by_port_key = MappingProxyType(
            {
                str(port.key): self._endpoint_facts(
                    node=final_node,
                    spec=spec,
                    port=port,
                    workspace_nodes=workspace_nodes,
                    visible_ports=visible_ports,
                    presentation_item=port_presentation.item_by_port_key[str(port.key)],
                    surface_metrics=surface_metrics,
                    width=float(width),
                    height=float(height),
                    show_port_labels=show_port_labels,
                    graph_label_pixel_size=graph_label_pixel_size,
                    graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                )
                for port in visible_ports
            }
        )
        icon = title_icon_presentation_for_node_payload(spec, provenance=provenance)
        is_group_backdrop = self.is_group_backdrop_spec(spec)
        return _NodePresentationFacts(
            original_node=node,
            payload_node=payload_node,
            final_node=final_node,
            spec=spec,
            provenance=provenance,
            visible_ports=visible_ports,
            visible_port_by_key=MappingProxyType({str(port.key): port for port in visible_ports}),
            surface_metrics=surface_metrics,
            width=float(width),
            height=float(height),
            bounds=bounds,
            expanded_bounds=expanded_bounds,
            minimap_bounds=bounds,
            membership_width=(float(expanded_bounds.width) if is_group_backdrop else float(width)),
            membership_height=(float(expanded_bounds.height) if is_group_backdrop else float(height)),
            port_presentation=port_presentation,
            inline_properties=inline_properties,
            endpoint_by_port_key=endpoint_by_port_key,
            icon_source=icon.source,
            icon_theme_aware=icon.theme_aware,
            is_group_backdrop=is_group_backdrop,
        )

    def _expanded_bounds_for_facts(
        self,
        *,
        original_node,
        spec: NodeTypeSpec,
        workspace_nodes: dict[str, Any],
        enabled_input_port_keys: set[str] | frozenset[str],
        port_connection_counts: Mapping[tuple[str, str], int],
        hide_optional_ports: bool,
        show_port_labels: bool,
        graph_label_pixel_size: int,
        graph_node_icon_pixel_size: int,
        fallback: LayoutNodeBounds,
    ) -> LayoutNodeBounds:
        if not bool(original_node.collapsed):
            return fallback
        expanded_node = original_node.clone()
        expanded_node.collapsed = False
        scoped_nodes = dict(workspace_nodes)
        expanded_payload_node = self.payload_node(expanded_node, spec)
        scoped_nodes[str(original_node.node_id)] = expanded_payload_node
        visible_ports = self.view_visible_ports(
            node=expanded_payload_node,
            spec=spec,
            workspace_nodes=scoped_nodes,
            port_connection_counts=port_connection_counts,
            hide_optional_ports=hide_optional_ports,
        )
        final_node, _surface_metrics, width, height, _port_presentation, _inline_properties = (
            self._presentation_layout_and_size(
                node=expanded_payload_node,
                spec=spec,
                workspace_nodes=scoped_nodes,
                enabled_input_port_keys=enabled_input_port_keys,
                port_connection_counts=port_connection_counts,
                visible_ports=visible_ports,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            )
        )
        return LayoutNodeBounds(
            node_id=str(original_node.node_id),
            x=float(final_node.x),
            y=float(final_node.y),
            width=max(1.0, float(width)),
            height=max(1.0, float(height)),
        )

    @classmethod
    def _endpoint_facts(
        cls,
        *,
        node,
        spec: NodeTypeSpec,
        port: EffectivePort,
        presentation_item: _PortPresentationItem,
        workspace_nodes: dict[str, Any],
        visible_ports: tuple[EffectivePort, ...],
        surface_metrics: Any,
        width: float,
        height: float,
        show_port_labels: bool,
        graph_label_pixel_size: int,
        graph_node_icon_pixel_size: int,
    ) -> _PortEndpointFacts:
        side = port_side(port)
        port_key = str(port.key)
        if not side and port_key.strip().lower() in CARDINAL_SIDES:
            side = port_key.strip().lower()
        if not bool(node.collapsed) and presentation_item.presentation_anchor is not None:
            side = str(presentation_item.presentation_anchor.side or side)
            local_x = float(presentation_item.presentation_anchor.x)
            local_y = float(presentation_item.presentation_anchor.y)
        elif (
            not bool(node.collapsed)
            and not side
            and str(spec.runtime_behavior or "").strip().lower() == "active"
            and str(spec.surface_family or "").strip().lower() != "flowchart"
            and all(
                port_layout_direction(item) in {"in", "out"} and not port_side(item)
                for item in visible_ports
            )
        ):
            direction = port_layout_direction(port)
            local_x = (
                float(surface_metrics.port_side_margin) + float(surface_metrics.port_dot_radius)
                if direction == "in"
                else float(width) - float(surface_metrics.port_side_margin) - float(surface_metrics.port_dot_radius)
            )
            local_y = (
                float(surface_metrics.port_top)
                + float(surface_metrics.port_center_offset)
                + float(surface_metrics.port_height) * int(presentation_item.layout_row)
            )
        else:
            local_x, local_y = surface_port_local_point(
                node,
                spec,
                port_key,
                workspace_nodes,
                width=width,
                height=height,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                surface_metrics=surface_metrics,
                visible_ports_override=visible_ports,
            )
        return _PortEndpointFacts(
            side=side,
            x=float(node.x) + float(local_x),
            y=float(node.y) + float(local_y),
        )

    def build_node_payload(
        self,
        *,
        node,
        spec: NodeTypeSpec,
        provenance: PluginProvenance | None,
        workspace: WorkspaceData,
        workspace_nodes: dict[str, Any],
        port_connection_counts: dict[tuple[str, str], int],
        graph_theme: GraphThemeDefinition,
        graph_theme_bridge: GraphThemeBridge | None = None,
        hide_optional_ports: bool = False,
        show_port_labels: bool = True,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        lightweight_canvas: bool = False,
        previous_payload: Mapping[str, Any] | None = None,
        changed_fields: set[str] | frozenset[str] | tuple[str, ...] | None = None,
        presentation_facts: _NodePresentationFacts | None = None,
        data_type_projection: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._workspace_edges = workspace.edges
        if presentation_facts is None:
            enabled_input_port_keys = {
                str(edge.target_port_key)
                for edge in workspace.edges.values()
                if bool(edge.enabled)
                and str(edge.target_node_id) == str(node.node_id)
            }
            visible_ports = self.view_visible_ports(
                node=node,
                spec=spec,
                workspace_nodes=workspace_nodes,
                port_connection_counts=port_connection_counts,
                hide_optional_ports=hide_optional_ports,
            )
            (
                layout_node,
                surface_metrics,
                width,
                height,
                port_presentation,
                inline_properties,
            ) = self._presentation_layout_and_size(
                node=node,
                spec=spec,
                workspace_nodes=workspace_nodes,
                enabled_input_port_keys=enabled_input_port_keys,
                port_connection_counts=port_connection_counts,
                visible_ports=visible_ports,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            )
            icon = title_icon_presentation_for_node_payload(spec, provenance=provenance)
        else:
            node = presentation_facts.payload_node
            spec = presentation_facts.spec
            provenance = presentation_facts.provenance
            visible_ports = presentation_facts.visible_ports
            layout_node = presentation_facts.final_node
            surface_metrics = presentation_facts.surface_metrics
            width = presentation_facts.width
            height = presentation_facts.height
            port_presentation = presentation_facts.port_presentation
            inline_properties = presentation_facts.inline_properties
            icon = None
        inline_property_by_key = {
            str(item.get("key", "")): item
            for item in inline_properties
            if str(item.get("key", ""))
        }
        default_property_keys = {
            str(port.key)
            for port in spec.ports
            if str(port.direction) == "in" and bool(port.uses_property_default)
        }
        inline_properties_payload = [
            dict(item)
            for item in inline_properties
            if str(item.get("key", "")) not in port_presentation.grouped_property_keys
            and str(item.get("key", "")) not in default_property_keys
        ]
        plot_surface_variant = _plot_type_from_node_payload(node=layout_node, spec=spec)
        surface_family = "plot" if plot_surface_variant else spec.surface_family
        surface_variant = plot_surface_variant if plot_surface_variant else spec.surface_variant
        surface_spec_payload = (
            surface_spec_payload_for_values(
                type_id=node.type_id,
                family=surface_family,
                variant=surface_variant,
            )
            if plot_surface_variant
            else _surface_spec_payload_for_node(type_id=node.type_id, spec=spec)
        )
        all_ports = effective_ports(
            node=layout_node,
            spec=spec,
            workspace_nodes=workspace_nodes,
        )
        ports_payload = self.build_ports_payload(
            node=layout_node,
            spec=spec,
            workspace=workspace,
            workspace_nodes=workspace_nodes,
            port_connection_counts=port_connection_counts,
            hide_optional_ports=hide_optional_ports,
            visible_ports=visible_ports,
            port_presentation=port_presentation,
            inline_property_by_key=inline_property_by_key,
            data_type_projection=data_type_projection,
        )
        properties_payload = copy.deepcopy(layout_node.properties)
        for property_spec in spec.properties:
            if property_spec.key in properties_payload:
                properties_payload[property_spec.key] = qml_safe_spec_property_value(
                    property_spec,
                    properties_payload[property_spec.key]
                )
        payload = {
            "node_id": node.node_id,
            "type_id": layout_node.type_id,
            "title": layout_node.title,
            "display_name": spec.display_name,
            "category_path": list(spec.category_path),
            "keywords": list(getattr(spec, "keywords", ()) or ()),
            "help_text": str(getattr(spec, "description", "") or "").strip(),
            "properties": properties_payload,
            "x": float(layout_node.x),
            "y": float(layout_node.y),
            "width": float(width),
            "height": float(height),
            "collapsible": bool(spec.collapsible),
            "collapsed": bool(node.collapsed),
            "locked": bool(node.locked),
            "runtime_behavior": spec.runtime_behavior,
            "show_title_icon": bool(getattr(spec, "show_title_icon", False)),
            "icon_source": (
                presentation_facts.icon_source if presentation_facts is not None else icon.source
            ),
            "icon_theme_aware": (
                presentation_facts.icon_theme_aware if presentation_facts is not None else icon.theme_aware
            ),
            "surface_family": surface_family,
            "surface_variant": surface_variant,
            "surface_spec": surface_spec_payload,
            "render_quality": spec.render_quality.to_payload(),
            "surface_metrics": surface_metrics.to_payload(),
            "link_count": len(node.links),
            "links": node_links_to_payload(list(node.links), source_workspace_id=workspace.workspace_id),
            "comment_count": len(node.comments),
            "comments": node_comments_to_payload(list(node.comments)),
            "comment_badge": node_comment_badge_payload(list(node.comments)),
            "can_enter_scope": is_subnode_shell_type(node.type_id),
            "unresolved": False,
            "read_only": False,
            "addon_id": "",
            "addon_display_name": "",
            "addon_version": "",
            "addon_apply_policy": "",
            "addon_status": "",
            "unavailable_reason": "",
            "locked_state": {},
            "ports": ports_payload,
            "readiness": _readiness_payload_for_spec(spec, all_ports),
            "inline_properties": inline_properties_payload,
        }
        if spec.dynamic_port_groups:
            payload["dynamic_port_groups"] = _dynamic_port_groups_payload(
                spec,
                all_ports,
                node.properties,
            )
        if port_presentation.settings_groups:
            payload["port_presentation"] = {
                "total_row_count": int(port_presentation.total_row_count),
            }
            payload["settings_band"] = dict(port_presentation.settings_band)
            payload["settings_groups"] = [
                copy.deepcopy(dict(group_payload))
                for group_payload in port_presentation.settings_groups
            ]
        if str(spec.runtime_behavior or "").strip().lower() == "passive":
            payload["visual_style"] = copy.deepcopy(node.visual_style)
        context = PayloadBuildContext(
            node=node,
            layout_node=layout_node,
            spec=spec,
            provenance=provenance,
            workspace=workspace,
            workspace_nodes=workspace_nodes,
            port_connection_counts=port_connection_counts,
            graph_theme=graph_theme,
            graph_theme_bridge=graph_theme_bridge,
            surface_metrics=surface_metrics,
            width=float(width),
            height=float(height),
            hide_optional_ports=hide_optional_ports,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            lightweight_canvas=bool(lightweight_canvas),
            boundary_adapters=self._boundary_adapters,
            previous_payload=previous_payload,
            changed_fields=(
                frozenset(str(field) for field in changed_fields)
                if changed_fields is not None
                else None
            ),
        )
        for contribute in kind_dispatch_for_spec(type_id=node.type_id, spec=spec).contributors:
            contribute(payload, context)
        return payload

    def payload_node(self, node, spec: NodeTypeSpec):
        properties = self.payload_properties(node=node, spec=spec)
        if properties == node.properties:
            return node
        payload_node = node.clone()
        payload_node.properties = properties
        return payload_node

    def payload_properties(self, *, node, spec: NodeTypeSpec) -> dict[str, Any]:
        properties = copy.deepcopy(node.properties)
        for normalize_properties in kind_dispatch_for_spec(
            type_id=node.type_id, spec=spec
        ).property_normalizers:
            properties = normalize_properties(
                properties,
                node=node,
                spec=spec,
                boundary_adapters=self._boundary_adapters,
            )
        return properties

    def build_minimap_node_payload(
        self,
        *,
        node,
        spec: NodeTypeSpec,
        workspace: WorkspaceData,
        workspace_nodes: dict[str, Any],
        show_port_labels: bool = True,
        port_connection_counts: Mapping[tuple[str, str], int] | None = None,
        hide_optional_ports: bool = False,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        presentation_facts: _NodePresentationFacts | None = None,
    ) -> dict[str, float | str]:
        del workspace
        if presentation_facts is not None:
            bounds = presentation_facts.minimap_bounds
            return {
                "node_id": str(bounds.node_id),
                "x": float(bounds.x),
                "y": float(bounds.y),
                "width": float(bounds.width),
                "height": float(bounds.height),
            }
        visible_ports_override: tuple[EffectivePort, ...] | None = None
        if port_connection_counts is not None:
            visible_ports = self.view_visible_ports(
                node=node,
                spec=spec,
                workspace_nodes=workspace_nodes,
                port_connection_counts=port_connection_counts,
                hide_optional_ports=hide_optional_ports,
            )
            visible_ports_override = self._layout_ports_override(
                visible_ports=visible_ports,
                hide_optional_ports=hide_optional_ports,
            )
        layout_node, _surface_metrics, width, height = self._layout_metrics_and_size(
            node=node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            visible_ports_override=visible_ports_override,
        )
        return {
            "node_id": layout_node.node_id,
            "x": float(layout_node.x),
            "y": float(layout_node.y),
            "width": float(width),
            "height": float(height),
        }

    def build_ports_payload(
        self,
        *,
        node,
        spec: NodeTypeSpec,
        workspace: WorkspaceData,
        workspace_nodes: dict[str, Any],
        port_connection_counts: dict[tuple[str, str], int],
        hide_optional_ports: bool,
        visible_ports: tuple[EffectivePort, ...] | None = None,
        port_presentation: _PortPresentationLayout | None = None,
        inline_property_by_key: Mapping[str, Mapping[str, Any]] | None = None,
        data_type_projection: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self._workspace_edges = workspace.edges
        ports_payload: list[dict[str, Any]] = []
        availability_by_key = port_availability_for_node(
            workspace=workspace,
            node=node,
            spec=spec,
        )
        if visible_ports is None:
            visible_ports = self.view_visible_ports(
                node=node,
                spec=spec,
                workspace_nodes=workspace_nodes,
                port_connection_counts=port_connection_counts,
                hide_optional_ports=hide_optional_ports,
            )
        enabled_input_port_keys: set[str] | frozenset[str] = frozenset()
        if port_presentation is None or inline_property_by_key is None:
            enabled_input_port_keys = {
                str(edge.target_port_key)
                for edge in workspace.edges.values()
                if bool(edge.enabled) and str(edge.target_node_id) == str(node.node_id)
            }
        if port_presentation is None:
            (
                _layout_node,
                _surface_metrics,
                _width,
                _height,
                port_presentation,
                _inline_properties,
            ) = self._presentation_layout_and_size(
                node=node,
                spec=spec,
                workspace_nodes=workspace_nodes,
                enabled_input_port_keys=enabled_input_port_keys,
                port_connection_counts=port_connection_counts,
                visible_ports=visible_ports,
                show_port_labels=True,
                graph_label_pixel_size=DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
                graph_node_icon_pixel_size=DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
            )
        if inline_property_by_key is None:
            inline_property_by_key = {
                str(item.get("key", "")): item
                for item in self.build_inline_properties_payload(
                    node=node,
                    spec=spec,
                    workspace_nodes=workspace_nodes,
                    enabled_input_port_keys=enabled_input_port_keys,
                    port_connection_counts=port_connection_counts,
                )
                if str(item.get("key", ""))
            }
        for port in ordered_ports_for_display(visible_ports):
            data_access = str(getattr(port, "data_access", "item") or "item").strip().lower()
            if data_access not in {"item", "list", "tree"}:
                data_access = "item"
            port_key = str(port.key)
            connection_count = self._port_connection_count(
                node_id=str(node.node_id),
                port_key=port_key,
                port_connection_counts=port_connection_counts,
            )
            availability = availability_by_key.get(str(port.key))
            availability_state = availability.availability if availability is not None else "available"
            availability_reason = availability.reason if availability is not None else ""
            availability_inactive = bool(availability is not None and availability.unavailable)
            inactive_reason = availability_reason if availability_inactive else ""
            display_tier = str(getattr(port, "display_tier", "") or "").strip().lower()
            if display_tier not in {"simple", "advanced"}:
                display_tier = "visible"
            advanced_only = display_tier == "advanced"
            presentation_item = port_presentation.item_by_port_key[str(port.key)]
            if advanced_only:
                display_state = "advanced-only"
            elif display_tier == "simple":
                display_state = "simple"
            else:
                display_state = "visible"
            default_property = None
            if (
                str(port.direction) == "in"
                and bool(port.uses_property_default)
                and port_key in inline_property_by_key
            ):
                default_property = copy.deepcopy(
                    dict(inline_property_by_key[port_key])
                )
            port_payload = {
                    "key": port.key,
                    "label": str(port.label),
                    "direction": port.direction,
                    "kind": port.kind,
                    **project_port_data_type_presentation(
                        data_type=port.data_type,
                        accepted_data_types=tuple(
                            getattr(port, "accepted_data_types", ()) or ()
                        ),
                        data_access=data_access,
                        kind=port.kind,
                        projection=data_type_projection,
                    ),
                    "modifiers": list(node.port_modifiers.get(port_key, ())),
                    "principal": node.principal_input_port_id == port_key,
                    "principal_eligible": bool(
                        str(port.kind) == "data"
                        and str(port.direction) == "in"
                        and data_access != "tree"
                    ),
                    "help_text": str(getattr(port, "description", "") or "").strip(),
                    "side": port.side,
                    "exposed": bool(port.exposed),
                    "allow_multiple_connections": bool(port.allow_multiple_connections),
                    "connection_count": int(connection_count),
                    "connected": bool(connection_count),
                    "optional": not bool(port.required),
                    "uses_property_default": bool(port.uses_property_default),
                    "allow_empty_string": bool(port.allow_empty_string),
                    "availability": availability_state,
                    "availability_reason": availability_reason,
                    "blocks_new_connections": bool(
                        availability is not None and availability.blocks_new_connections
                    ),
                    "inactive": availability_inactive,
                    "flow_state": resolve_port_flow_state(
                        direction=str(port.direction),
                        kind=str(port.kind),
                        connected=bool(connection_count),
                        required=bool(port.required),
                        inactive=availability_inactive,
                        has_default=default_property is not None,
                    ),
                    "inactive_reason": inactive_reason,
                    "display_tier": display_tier,
                    "display_state": display_state,
                    "advanced_only": advanced_only,
                    "layout_row": int(presentation_item.layout_row),
                }
            if default_property is not None:
                port_payload["default_property"] = default_property
            if presentation_item.presentation_anchor is not None:
                port_payload["presentation_anchor"] = {
                    "side": str(presentation_item.presentation_anchor.side),
                    "x": float(presentation_item.presentation_anchor.x),
                    "y": float(presentation_item.presentation_anchor.y),
                    "aggregate": not bool(presentation_item.handle_visible),
                }
            if presentation_item.settings_group_id:
                port_payload.update(
                    {
                        "settings_group_id": presentation_item.settings_group_id,
                        "settings_member_index": int(presentation_item.settings_member_index),
                        "handle_visible": bool(presentation_item.handle_visible),
                        "presentation_anchor": port_payload.get("presentation_anchor"),
                    }
                )
                if presentation_item.settings_property_key:
                    port_payload["settings_property_key"] = presentation_item.settings_property_key
            ports_payload.append(port_payload)
        return ports_payload

    @staticmethod
    def is_group_backdrop_spec(spec: NodeTypeSpec) -> bool:
        return str(spec.surface_family or "").strip() == "group_backdrop"

    def membership_candidate_size(
        self,
        *,
        node,
        spec: NodeTypeSpec,
        workspace: WorkspaceData,
        workspace_nodes: dict[str, Any],
        is_group_backdrop: bool,
        show_port_labels: bool = True,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        port_connection_counts: Mapping[tuple[str, str], int] | None = None,
        hide_optional_ports: bool = False,
        presentation_facts: _NodePresentationFacts | None = None,
    ) -> tuple[float, float]:
        if presentation_facts is not None:
            return presentation_facts.membership_width, presentation_facts.membership_height
        if not is_group_backdrop:
            visible_ports_override: tuple[EffectivePort, ...] | None = None
            if port_connection_counts is not None:
                visible_ports = self.view_visible_ports(
                    node=node,
                    spec=spec,
                    workspace_nodes=workspace_nodes,
                    port_connection_counts=port_connection_counts,
                    hide_optional_ports=hide_optional_ports,
                )
                visible_ports_override = self._layout_ports_override(
                    visible_ports=visible_ports,
                    hide_optional_ports=hide_optional_ports,
                )
            _layout_node, _surface_metrics, width, height = self._layout_metrics_and_size(
                node=node,
                spec=spec,
                workspace_nodes=workspace_nodes,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                visible_ports_override=visible_ports_override,
            )
            return width, height
        surface_metrics = self._surface_metrics(
            node=node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
        # Backdrop membership keeps the expanded surface envelope so collapsed
        # backdrops still own and serialize their descendants.
        width = node.custom_width if node.custom_width is not None else surface_metrics.default_width
        height = node.custom_height if node.custom_height is not None else surface_metrics.default_height
        return max(float(surface_metrics.min_width), float(width)), float(height)

    def layout_bounds(
        self,
        *,
        node,
        spec: NodeTypeSpec,
        workspace_nodes: dict[str, Any],
        show_port_labels: bool = True,
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        expanded: bool = False,
        port_connection_counts: Mapping[tuple[str, str], int] | None = None,
        hide_optional_ports: bool = False,
        presentation_facts: _NodePresentationFacts | None = None,
    ) -> LayoutNodeBounds:
        if presentation_facts is not None:
            return presentation_facts.expanded_bounds if expanded else presentation_facts.bounds
        payload_node = node.clone()
        if expanded:
            payload_node.collapsed = False
        scoped_nodes = dict(workspace_nodes)
        scoped_nodes[node.node_id] = payload_node
        resolved_node = self._resolved_payload_node(
            node=payload_node,
            spec=spec,
            workspace_nodes=scoped_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
        scoped_nodes[node.node_id] = resolved_node
        visible_ports_override: tuple[EffectivePort, ...] | None = None
        if port_connection_counts is not None:
            visible_ports = self.view_visible_ports(
                node=resolved_node,
                spec=spec,
                workspace_nodes=scoped_nodes,
                port_connection_counts=port_connection_counts,
                hide_optional_ports=hide_optional_ports,
            )
            visible_ports_override = self._layout_ports_override(
                visible_ports=visible_ports,
                hide_optional_ports=hide_optional_ports,
            )
        _layout_node, _surface_metrics, width, height = self._layout_metrics_and_size(
            node=resolved_node,
            spec=spec,
            workspace_nodes=scoped_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            visible_ports_override=visible_ports_override,
        )
        return LayoutNodeBounds(
            node_id=node.node_id,
            x=float(node.x),
            y=float(node.y),
            width=max(1.0, float(width)),
            height=max(1.0, float(height)),
        )
