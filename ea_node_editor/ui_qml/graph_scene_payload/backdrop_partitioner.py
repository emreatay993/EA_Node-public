from __future__ import annotations

"""Group-backdrop partitioning of scene payload models."""


import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any


from ea_node_editor.graph.group_backdrop_geometry import (
    GroupBackdropCandidate,
    GroupBackdropMembership,
    build_group_backdrop_occupied_bounds,
    compute_group_backdrop_membership,
)
from ea_node_editor.graph.hierarchy import ScopePath
from ea_node_editor.graph.hierarchy import node_scope_path, scope_edges, scope_node_ids
from ea_node_editor.graph.transform_layout_ops import LayoutNodeBounds
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.settings import (
    DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
)
from ea_node_editor.ui.graph_theme import (
    GraphThemeDefinition,
)
from ea_node_editor.ui.support.node_presentation import build_data_type_ui_projection
from ea_node_editor.ui_qml.edge_routing import build_edge_payload

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge

from ea_node_editor.ui_qml.graph_scene_payload.normalize import (
    _annotate_edge_payload_availability,
)
from ea_node_editor.ui_qml.graph_scene_payload.factory import (
    _GraphSceneNodePayloadFactory,
    _NodePresentationFacts,
)


class _GraphSceneBackdropPartitioner:
    def __init__(self, node_payload_factory: _GraphSceneNodePayloadFactory) -> None:
        self._node_payload_factory = node_payload_factory
        self._mutation_timing_enabled = False
        self._last_mutation_phase_timings_ms: dict[str, float] = {}

    def set_mutation_timing_enabled(self, enabled: bool) -> None:
        self._mutation_timing_enabled = bool(enabled)
        if not self._mutation_timing_enabled:
            self._last_mutation_phase_timings_ms = {}

    def mutation_phase_timings_ms(self) -> dict[str, float]:
        return dict(self._last_mutation_phase_timings_ms)

    @staticmethod
    def active_view_hide_optional_ports(workspace: WorkspaceData) -> bool:
        if not workspace.views:
            return False
        active_view = workspace.views.get(workspace.active_view_id)
        if active_view is None:
            active_view = next(iter(workspace.views.values()), None)
        if active_view is None:
            return False
        return bool(active_view.hide_optional_ports)

    def build_payload_models(
        self,
        *,
        workspace: WorkspaceData,
        registry: NodeRegistry,
        scope_path: ScopePath,
        graph_theme: GraphThemeDefinition,
        graph_theme_bridge: GraphThemeBridge | None = None,
        comment_peek_node_id: str = "",
        graph_label_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        graph_node_icon_pixel_size: int = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
        lightweight_canvas: bool = False,
        show_port_labels: bool = True,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        visible_node_ids = scope_node_ids(workspace, scope_path)
        comment_peek_node_id = str(comment_peek_node_id or "").strip()
        workspace_edges = scope_edges(workspace, scope_path)
        port_connection_counts = self.port_connection_counts(workspace_edges)
        enabled_input_port_keys_by_node = self.enabled_input_port_keys_by_node(
            workspace_edges
        )
        workspace_nodes = dict(workspace.nodes)
        hide_optional_ports = self.active_view_hide_optional_ports(workspace)
        data_type_projection = build_data_type_ui_projection(registry.data_types)

        nodes_payload: list[dict[str, Any]] = []
        backdrop_nodes_payload: list[dict[str, Any]] = []
        minimap_nodes_payload: list[dict[str, Any]] = []
        node_specs: dict[str, NodeTypeSpec] = {}
        presentation_facts_by_node_id: dict[str, _NodePresentationFacts] = {}
        node_payload_by_id: dict[str, dict[str, Any]] = {}
        minimap_payload_by_id: dict[str, dict[str, float | str]] = {}
        group_backdrop_ids: set[str] = set()
        membership_candidates: list[GroupBackdropCandidate] = []

        for node_id in visible_node_ids:
            node = workspace.nodes[node_id]
            provenance = None
            descriptor_or_none = getattr(registry, "descriptor_or_none", None)
            descriptor = descriptor_or_none(node.type_id) if callable(descriptor_or_none) else None
            spec = descriptor.spec if descriptor is not None else None
            if descriptor is not None:
                provenance = descriptor.provenance
            if spec is None:
                spec = registry.spec_or_none(node.type_id)
            if provenance is None:
                provenance_or_none = getattr(registry, "provenance_or_none", None)
                if callable(provenance_or_none):
                    provenance = provenance_or_none(node.type_id)
            if spec is None:
                continue
            spec = registry.resolve_spec(node.type_id, node.properties)
            node_specs[node_id] = spec
            presentation_facts = self._node_payload_factory.build_presentation_facts(
                node=node,
                spec=spec,
                provenance=provenance,
                workspace_nodes=workspace_nodes,
                enabled_input_port_keys=enabled_input_port_keys_by_node.get(
                    str(node_id), frozenset()
                ),
                port_connection_counts=port_connection_counts,
                hide_optional_ports=hide_optional_ports,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            )
            presentation_facts_by_node_id[node_id] = presentation_facts
            node_payload = self._node_payload_factory.build_node_payload(
                node=node,
                spec=spec,
                provenance=provenance,
                workspace=workspace,
                workspace_nodes=workspace_nodes,
                port_connection_counts=port_connection_counts,
                graph_theme=graph_theme,
                graph_theme_bridge=graph_theme_bridge,
                hide_optional_ports=hide_optional_ports,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                lightweight_canvas=lightweight_canvas,
                presentation_facts=presentation_facts,
                data_type_projection=data_type_projection,
            )
            node_payload_by_id[node_id] = node_payload
            is_group_backdrop = presentation_facts.is_group_backdrop
            if is_group_backdrop:
                group_backdrop_ids.add(node_id)
            membership_width, membership_height = self._node_payload_factory.membership_candidate_size(
                node=node,
                spec=spec,
                workspace=workspace,
                workspace_nodes=workspace_nodes,
                is_group_backdrop=is_group_backdrop,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                port_connection_counts=port_connection_counts,
                hide_optional_ports=hide_optional_ports,
                presentation_facts=presentation_facts,
            )
            membership_candidates.append(
                GroupBackdropCandidate(
                    node_id=node_id,
                    scope_path=node_scope_path(workspace, node_id),
                    is_backdrop=is_group_backdrop,
                    x=float(presentation_facts.bounds.x),
                    y=float(presentation_facts.bounds.y),
                    width=float(membership_width),
                    height=float(membership_height),
                )
            )
            minimap_payload_by_id[node_id] = self._node_payload_factory.build_minimap_node_payload(
                node=node,
                spec=spec,
                workspace=workspace,
                workspace_nodes=workspace_nodes,
                show_port_labels=show_port_labels,
                port_connection_counts=port_connection_counts,
                hide_optional_ports=hide_optional_ports,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                presentation_facts=presentation_facts,
            )

        membership_by_node_id = compute_group_backdrop_membership(membership_candidates)
        comment_peek_visible_node_ids = self.comment_peek_visible_node_ids(
            comment_peek_node_id=comment_peek_node_id,
            visible_node_ids=visible_node_ids,
            membership_by_node_id=membership_by_node_id,
            workspace=workspace,
            group_backdrop_ids=group_backdrop_ids,
        )
        render_node_ids = set(comment_peek_visible_node_ids) if comment_peek_visible_node_ids else set(visible_node_ids)
        self.apply_expanded_occupied_bounds_payload(
            node_payload_by_id=node_payload_by_id,
            node_specs=node_specs,
            workspace=workspace,
            workspace_nodes=workspace_nodes,
            membership_by_node_id=membership_by_node_id,
            group_backdrop_ids=group_backdrop_ids,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            port_connection_counts=port_connection_counts,
            hide_optional_ports=hide_optional_ports,
            presentation_facts_by_node_id=presentation_facts_by_node_id,
        )
        collapsed_proxy_backdrop_by_node_id = self.collapsed_proxy_backdrop_by_node_id(
            visible_node_ids=visible_node_ids,
            membership_by_node_id=membership_by_node_id,
            workspace=workspace,
            group_backdrop_ids=group_backdrop_ids,
            comment_peek_node_id=comment_peek_node_id if comment_peek_visible_node_ids else "",
        )
        for node_id in visible_node_ids:
            if node_id not in render_node_ids:
                continue
            if collapsed_proxy_backdrop_by_node_id.get(node_id):
                continue
            if node_id not in node_payload_by_id or node_id not in minimap_payload_by_id:
                continue
            node_payload = node_payload_by_id[node_id]
            is_group_backdrop = node_id in group_backdrop_ids
            self.apply_group_backdrop_membership_payload(
                node_payload,
                membership_by_node_id.get(node_id),
                is_group_backdrop=is_group_backdrop,
            )
            if is_group_backdrop:
                backdrop_nodes_payload.append(node_payload)
            else:
                nodes_payload.append(node_payload)
            minimap_nodes_payload.append(minimap_payload_by_id[node_id])

        render_workspace_edges = [
            edge
            for edge in workspace_edges
            if edge.source_node_id in render_node_ids and edge.target_node_id in render_node_ids
        ]
        self._last_mutation_phase_timings_ms = {}
        edge_start = time.perf_counter()
        edges_payload = build_edge_payload(
            graph_theme=graph_theme,
            workspace_edges=render_workspace_edges,
            workspace_nodes=workspace_nodes,
            node_specs=node_specs,
            data_types=registry.data_types,
            collapsed_proxy_backdrop_by_node_id=collapsed_proxy_backdrop_by_node_id,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            presentation_facts_by_node_id=presentation_facts_by_node_id,
        )
        edges_by_id = {edge.edge_id: edge for edge in render_workspace_edges}
        for payload_item in edges_payload:
            edge = edges_by_id.get(str(payload_item.get("edge_id", "")))
            if edge is not None:
                _annotate_edge_payload_availability(
                    payload_item,
                    workspace=workspace,
                    edge=edge,
                    workspace_nodes=workspace_nodes,
                    node_specs=node_specs,
                )
        if self._mutation_timing_enabled:
            self._last_mutation_phase_timings_ms["edge_payload_update_ms"] = max(
                0.0,
                (time.perf_counter() - edge_start) * 1000.0,
            )
        return nodes_payload, backdrop_nodes_payload, minimap_nodes_payload, edges_payload

    @staticmethod
    def comment_peek_visible_node_ids(
        *,
        comment_peek_node_id: str,
        visible_node_ids: list[str],
        membership_by_node_id: dict[str, GroupBackdropMembership],
        workspace: WorkspaceData,
        group_backdrop_ids: set[str],
    ) -> set[str]:
        normalized = str(comment_peek_node_id or "").strip()
        if not normalized or normalized not in visible_node_ids or normalized not in group_backdrop_ids:
            return set()
        node = workspace.nodes.get(normalized)
        if node is None or not bool(node.collapsed):
            return set()
        membership = membership_by_node_id.get(normalized)
        direct_member_ids = [] if membership is None else [*membership.member_node_ids, *membership.member_backdrop_ids]
        visible_set = set(visible_node_ids)
        return {
            node_id
            for node_id in [normalized, *direct_member_ids]
            if node_id in visible_set and node_id in workspace.nodes
        }

    @staticmethod
    def collapsed_proxy_backdrop_by_node_id(
        *,
        visible_node_ids: list[str],
        membership_by_node_id: dict[str, GroupBackdropMembership],
        workspace: WorkspaceData,
        group_backdrop_ids: set[str],
        comment_peek_node_id: str = "",
    ) -> dict[str, str]:
        collapsed_backdrop_ids = {
            node_id
            for node_id in group_backdrop_ids
            if bool(workspace.nodes.get(node_id) is not None and workspace.nodes[node_id].collapsed)
        }
        if comment_peek_node_id:
            collapsed_backdrop_ids.discard(str(comment_peek_node_id))
        owner_backdrop_by_node_id = {
            node_id: str(membership.owner_backdrop_id or "")
            for node_id, membership in membership_by_node_id.items()
        }
        proxy_backdrop_by_node_id: dict[str, str] = {}
        for node_id in visible_node_ids:
            proxy_backdrop_id = ""
            owner_backdrop_id = owner_backdrop_by_node_id.get(node_id, "")
            while owner_backdrop_id:
                if owner_backdrop_id in collapsed_backdrop_ids:
                    proxy_backdrop_id = owner_backdrop_id
                owner_backdrop_id = owner_backdrop_by_node_id.get(owner_backdrop_id, "")
            proxy_backdrop_by_node_id[node_id] = proxy_backdrop_id
        return proxy_backdrop_by_node_id

    @staticmethod
    def apply_group_backdrop_membership_payload(
        node_payload: dict[str, Any],
        membership: GroupBackdropMembership | None,
        *,
        is_group_backdrop: bool,
    ) -> None:
        node_payload["owner_backdrop_id"] = str(membership.owner_backdrop_id or "") if membership is not None else ""
        node_payload["backdrop_depth"] = int(membership.backdrop_depth) if membership is not None else 0
        if membership is None or not is_group_backdrop:
            node_payload["member_node_ids"] = []
            node_payload["member_backdrop_ids"] = []
            node_payload["contained_node_ids"] = []
            node_payload["contained_backdrop_ids"] = []
            return
        node_payload["member_node_ids"] = list(membership.member_node_ids)
        node_payload["member_backdrop_ids"] = list(membership.member_backdrop_ids)
        node_payload["contained_node_ids"] = list(membership.contained_node_ids)
        node_payload["contained_backdrop_ids"] = list(membership.contained_backdrop_ids)

    def apply_expanded_occupied_bounds_payload(
        self,
        *,
        node_payload_by_id: dict[str, dict[str, Any]],
        node_specs: dict[str, NodeTypeSpec],
        workspace: WorkspaceData,
        workspace_nodes: dict[str, Any],
        membership_by_node_id: dict[str, GroupBackdropMembership],
        group_backdrop_ids: set[str],
        show_port_labels: bool,
        graph_label_pixel_size: int,
        graph_node_icon_pixel_size: int,
        port_connection_counts: Mapping[tuple[str, str], int],
        hide_optional_ports: bool,
        presentation_facts_by_node_id: Mapping[str, _NodePresentationFacts],
    ) -> None:
        for node_id, node_payload in node_payload_by_id.items():
            node = workspace.nodes.get(node_id)
            spec = node_specs.get(node_id)
            if node is None or spec is None:
                continue
            bounds = self._node_payload_factory.layout_bounds(
                node=node,
                spec=spec,
                workspace_nodes=workspace_nodes,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=graph_label_pixel_size,
                graph_node_icon_pixel_size=graph_node_icon_pixel_size,
                expanded=True,
                port_connection_counts=port_connection_counts,
                hide_optional_ports=hide_optional_ports,
                presentation_facts=presentation_facts_by_node_id.get(node_id),
            )
            if node_id in group_backdrop_ids:
                membership = membership_by_node_id.get(node_id)
                direct_member_ids = (
                    []
                    if membership is None
                    else [*membership.member_node_ids, *membership.member_backdrop_ids]
                )
                member_candidates = [
                    self._payload_candidate(
                        member_payload,
                        is_backdrop=str(member_id) in group_backdrop_ids,
                        workspace=workspace,
                    )
                    for member_id in direct_member_ids
                    if (member_payload := node_payload_by_id.get(member_id)) is not None
                ]
                occupied = build_group_backdrop_occupied_bounds(
                    self._bounds_candidate(bounds, is_backdrop=True, workspace=workspace),
                    member_candidates,
                )
                node_payload["expanded_occupied_bounds"] = {
                    "x": float(occupied.x),
                    "y": float(occupied.y),
                    "width": float(occupied.width),
                    "height": float(occupied.height),
                }
                continue
            node_payload["expanded_occupied_bounds"] = {
                "x": float(bounds.x),
                "y": float(bounds.y),
                "width": float(bounds.width),
                "height": float(bounds.height),
            }

    @staticmethod
    def _bounds_candidate(
        bounds: LayoutNodeBounds,
        *,
        is_backdrop: bool,
        workspace: WorkspaceData,
    ) -> GroupBackdropCandidate:
        return GroupBackdropCandidate(
            node_id=str(bounds.node_id),
            scope_path=node_scope_path(workspace, str(bounds.node_id)),
            is_backdrop=is_backdrop,
            x=float(bounds.x),
            y=float(bounds.y),
            width=float(bounds.width),
            height=float(bounds.height),
        )

    @staticmethod
    def _payload_candidate(
        node_payload: dict[str, Any],
        *,
        is_backdrop: bool,
        workspace: WorkspaceData,
    ) -> GroupBackdropCandidate:
        node_id = str(node_payload.get("node_id", ""))
        return GroupBackdropCandidate(
            node_id=node_id,
            scope_path=node_scope_path(workspace, node_id),
            is_backdrop=is_backdrop,
            x=float(node_payload.get("x", 0.0)),
            y=float(node_payload.get("y", 0.0)),
            width=float(node_payload.get("width", 1.0)),
            height=float(node_payload.get("height", 1.0)),
        )

    @staticmethod
    def port_connection_counts(workspace_edges: list[Any]) -> dict[tuple[str, str], int]:
        counts: dict[tuple[str, str], int] = {}
        for edge in workspace_edges:
            source_key = (edge.source_node_id, edge.source_port_key)
            target_key = (edge.target_node_id, edge.target_port_key)
            counts[source_key] = counts.get(source_key, 0) + 1
            counts[target_key] = counts.get(target_key, 0) + 1
        return counts

    @staticmethod
    def enabled_input_port_keys_by_node(
        workspace_edges: list[Any],
    ) -> dict[str, frozenset[str]]:
        keys_by_node: dict[str, set[str]] = {}
        for edge in workspace_edges:
            if not bool(edge.enabled):
                continue
            keys_by_node.setdefault(str(edge.target_node_id), set()).add(
                str(edge.target_port_key)
            )
        return {
            node_id: frozenset(port_keys)
            for node_id, port_keys in keys_by_node.items()
        }
