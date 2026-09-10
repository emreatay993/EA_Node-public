from __future__ import annotations

"""Payload-cache synchronization for the graph scene context.

Single home for cached node/edge payload replacement, removal, rebuild, and
inline-title sync. The scene context owns publish_* orchestration (delta
classification, signal emission) and delegates cache mutation here, so
payload-cache staleness is a one-file investigation.
"""

import copy
from typing import TYPE_CHECKING, Any

from ea_node_editor.graph.group_backdrop_geometry import (
    GroupBackdropCandidate,
    build_group_backdrop_occupied_bounds,
    compute_group_backdrop_membership,
)
from ea_node_editor.graph.effective_ports import is_subnode_shell_type
from ea_node_editor.graph.hierarchy import node_scope_path
from ea_node_editor.settings import DEFAULT_GRAPH_LABEL_PIXEL_SIZE
from ea_node_editor.ui_qml.graph_scene_payload.backdrop_partitioner import _GraphSceneBackdropPartitioner

_EDGE_ENDPOINT_FIELDS = (
    "source_node_id",
    "source_port_key",
    "target_node_id",
    "target_port_key",
)

if TYPE_CHECKING:
    from ea_node_editor.graph.records import NodeInstance
    from ea_node_editor.ui_qml.graph_scene.context import _GraphSceneContext


class ScenePayloadCacheSync:
    """Cache-mutation collaborator owned by ``_GraphSceneContext``."""

    def __init__(self, context: "_GraphSceneContext") -> None:
        self._context = context

    def _graphics_payload_facts(self) -> tuple[bool, int, int, bool]:
        return (
            bool(getattr(self._context, "graphics_show_port_labels", True)),
            int(
                getattr(
                    self._context,
                    "graphics_graph_label_pixel_size",
                    DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
                )
            ),
            int(
                getattr(
                    self._context,
                    "graphics_node_title_icon_pixel_size",
                    DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
                )
            ),
            bool(getattr(self._context, "graphics_lightweight_canvas", False)),
        )

    def payload_cache_matches_active_view(self) -> bool:
        cache = self._context._bridge._payload_cache
        active_view_id, hide_optional_ports = self._context._active_view_filter_state()
        return (
            cache.active_view_id == active_view_id
            and cache.hide_optional_ports == hide_optional_ports
            and cache.comment_peek_node_id == self._context._validated_comment_peek_node_id()
        )

    def cached_node_payload_ids(self) -> set[str]:
        cache = self._context._bridge._payload_cache
        node_ids: set[str] = set()
        for collection in (cache.nodes, cache.backdrop_nodes):
            for payload in collection:
                node_id = str(payload.get("node_id", "") or "").strip()
                if node_id:
                    node_ids.add(node_id)
        return node_ids

    def append_added_node_payloads(
        self,
        *,
        nodes_payload: list[dict[str, Any]],
        backdrop_nodes_payload: list[dict[str, Any]],
        minimap_nodes_payload: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], set[str]] | None:
        """Append visible additions, refreshing expanded-backdrop membership.

        ``None`` means the cache cannot be updated safely and the caller must
        rebuild the complete scene payload.
        """
        workspace = self._context.workspace_or_none()
        if workspace is None:
            return None
        cache = self._context._bridge._payload_cache
        if cache.comment_peek_node_id:
            return None
        if not cache.indexes_valid:
            cache.rebuild_indexes()

        added_node_ids = [
            str(payload.get("node_id", "") or "").strip()
            for payload in (*nodes_payload, *backdrop_nodes_payload)
        ]
        added_minimap_ids = [
            str(payload.get("node_id", "") or "").strip()
            for payload in minimap_nodes_payload
        ]
        if (
            not added_node_ids
            or any(not node_id for node_id in added_node_ids)
            or len(set(added_node_ids)) != len(added_node_ids)
            or set(added_minimap_ids) != set(added_node_ids)
            or len(added_minimap_ids) != len(added_node_ids)
            or set(added_node_ids) & self.cached_node_payload_ids()
        ):
            return None

        cached_node_ids = [
            str(payload.get("node_id", "") or "").strip()
            for payload in (*cache.nodes, *cache.backdrop_nodes)
        ]
        cached_minimap_ids = [
            str(payload.get("node_id", "") or "").strip()
            for payload in cache.minimap_nodes
        ]
        if (
            any(not node_id for node_id in cached_node_ids)
            or len(set(cached_node_ids)) != len(cached_node_ids)
            or set(cache.node_payload_location_by_id) != set(cached_node_ids)
            or any(not node_id for node_id in cached_minimap_ids)
            or len(set(cached_minimap_ids)) != len(cached_minimap_ids)
            or set(cached_minimap_ids) != set(cached_node_ids)
            or set(cache.minimap_node_index_by_id) != set(cached_minimap_ids)
            or any(node_id not in workspace.nodes for node_id in (*cached_node_ids, *added_node_ids))
        ):
            return None
        for collection_name, payloads in (("nodes", cache.nodes), ("backdrop_nodes", cache.backdrop_nodes)):
            for index, payload in enumerate(payloads):
                node_id = str(payload.get("node_id", "") or "").strip()
                if cache.node_payload_location_by_id.get(node_id) != (collection_name, index):
                    return None
        for index, node_id in enumerate(cached_minimap_ids):
            if cache.minimap_node_index_by_id.get(node_id) != index:
                return None

        if not cache.backdrop_nodes and not backdrop_nodes_payload:
            added_nodes = [dict(payload) for payload in nodes_payload]
            node_start_index = len(cache.nodes)
            minimap_start_index = len(cache.minimap_nodes)
            cache.nodes.extend(added_nodes)
            cache.minimap_nodes.extend(dict(payload) for payload in minimap_nodes_payload)
            for offset, payload in enumerate(added_nodes):
                node_id = str(payload.get("node_id", "") or "").strip()
                cache.node_payload_location_by_id[node_id] = ("nodes", node_start_index + offset)
            for offset, payload in enumerate(minimap_nodes_payload):
                node_id = str(payload.get("node_id", "") or "").strip()
                cache.minimap_node_index_by_id[node_id] = minimap_start_index + offset
            cache.edge_delta_payload = {}
            cache.indexes_valid = True
            return added_nodes, set(added_node_ids)

        all_node_payloads = [dict(payload) for payload in (*cache.nodes, *nodes_payload)]
        all_backdrop_payloads = [dict(payload) for payload in (*cache.backdrop_nodes, *backdrop_nodes_payload)]
        if all_backdrop_payloads:
            if self._cached_backdrop_candidates() is None:
                return None
            for payload in backdrop_nodes_payload:
                node_id = str(payload.get("node_id", "") or "").strip()
                node = workspace.nodes.get(node_id)
                if node is None or bool(node.collapsed):
                    return None

            candidates: list[GroupBackdropCandidate] = []
            candidate_by_id: dict[str, GroupBackdropCandidate] = {}
            for is_backdrop, payloads in ((False, all_node_payloads), (True, all_backdrop_payloads)):
                for payload in payloads:
                    candidate = self._payload_candidate_from_payload(
                        payload,
                        workspace=workspace,
                        is_backdrop=is_backdrop,
                    )
                    if candidate is None or candidate.node_id in candidate_by_id:
                        return None
                    candidates.append(candidate)
                    candidate_by_id[candidate.node_id] = candidate

            membership_by_id = compute_group_backdrop_membership(candidates)
            for is_backdrop, payloads in ((False, all_node_payloads), (True, all_backdrop_payloads)):
                for payload in payloads:
                    node_id = str(payload.get("node_id", "") or "").strip()
                    _GraphSceneBackdropPartitioner.apply_group_backdrop_membership_payload(
                        payload,
                        membership_by_id.get(node_id),
                        is_group_backdrop=is_backdrop,
                    )

            for payload in all_backdrop_payloads:
                backdrop_id = str(payload.get("node_id", "") or "").strip()
                backdrop_candidate = candidate_by_id.get(backdrop_id)
                membership = membership_by_id.get(backdrop_id)
                if backdrop_candidate is None or membership is None:
                    return None
                direct_member_ids = (*membership.member_node_ids, *membership.member_backdrop_ids)
                if any(member_id not in candidate_by_id for member_id in direct_member_ids):
                    return None
                occupied = build_group_backdrop_occupied_bounds(
                    backdrop_candidate,
                    [candidate_by_id[member_id] for member_id in direct_member_ids],
                )
                payload["expanded_occupied_bounds"] = {
                    "x": float(occupied.x),
                    "y": float(occupied.y),
                    "width": float(occupied.width),
                    "height": float(occupied.height),
                }

        existing_node_count = len(cache.nodes)
        existing_backdrop_count = len(cache.backdrop_nodes)
        changed_payloads: list[dict[str, Any]] = []
        for index, replacement in enumerate(all_node_payloads[:existing_node_count]):
            if replacement != cache.nodes[index]:
                cache.nodes[index] = replacement
                changed_payloads.append(replacement)
        for index, replacement in enumerate(all_backdrop_payloads[:existing_backdrop_count]):
            if replacement != cache.backdrop_nodes[index]:
                cache.backdrop_nodes[index] = replacement
                changed_payloads.append(replacement)

        added_nodes = all_node_payloads[existing_node_count:]
        added_backdrops = all_backdrop_payloads[existing_backdrop_count:]
        node_start_index = len(cache.nodes)
        backdrop_start_index = len(cache.backdrop_nodes)
        minimap_start_index = len(cache.minimap_nodes)
        cache.nodes.extend(added_nodes)
        cache.backdrop_nodes.extend(added_backdrops)
        cache.minimap_nodes.extend(dict(payload) for payload in minimap_nodes_payload)
        for offset, payload in enumerate(added_nodes):
            node_id = str(payload.get("node_id", "") or "").strip()
            cache.node_payload_location_by_id[node_id] = ("nodes", node_start_index + offset)
        for offset, payload in enumerate(added_backdrops):
            node_id = str(payload.get("node_id", "") or "").strip()
            cache.node_payload_location_by_id[node_id] = ("backdrop_nodes", backdrop_start_index + offset)
        for offset, payload in enumerate(minimap_nodes_payload):
            node_id = str(payload.get("node_id", "") or "").strip()
            cache.minimap_node_index_by_id[node_id] = minimap_start_index + offset
        cache.edge_delta_payload = {}
        cache.indexes_valid = True
        return [*changed_payloads, *added_nodes, *added_backdrops], set(added_node_ids)

    def _cached_port_connection_counts_for_nodes(self, node_ids: set[str]) -> dict[tuple[str, str], int] | None:
        cache = self._context._bridge._payload_cache
        if cache.backdrop_nodes or cache.comment_peek_node_id:
            return None
        if not cache.indexes_valid:
            cache.rebuild_indexes()
        return cache.port_connection_counts_for_nodes(node_ids)

    def can_apply_backdrop_position_delta(self, node_ids: set[str]) -> bool:
        workspace = self._context.workspace_or_none()
        if workspace is None or not node_ids:
            return False
        cache = self._context._bridge._payload_cache
        if cache.comment_peek_node_id:
            return False
        if not cache.backdrop_nodes:
            return True
        if not cache.indexes_valid:
            cache.rebuild_indexes()

        backdrop_candidates = self._cached_backdrop_candidates()
        if backdrop_candidates is None:
            return False
        for node_id in sorted(node_ids):
            status, location = cache.resolve_node_payload_slot(node_id)
            if status != "ok" or location is None:
                return False
            collection_name, index = location
            if collection_name != "nodes":
                return False
            payload = cache.nodes[index]
            node = workspace.nodes.get(node_id)
            if node is None:
                return False
            if is_subnode_shell_type(node.type_id):
                return False
            old_owner_id = str(payload.get("owner_backdrop_id", "") or "").strip()
            candidate = self._payload_candidate_from_payload(
                payload,
                workspace=workspace,
                x=float(node.x),
                y=float(node.y),
                is_backdrop=False,
            )
            if candidate is None:
                return False
            membership = compute_group_backdrop_membership([*backdrop_candidates, candidate]).get(node_id)
            new_owner_id = "" if membership is None else str(membership.owner_backdrop_id or "").strip()
            if new_owner_id != old_owner_id:
                return False
        return True

    def refresh_cached_backdrop_occupied_bounds_for_node_ids(
        self,
        node_ids: set[str],
    ) -> list[dict[str, Any]] | None:
        workspace = self._context.workspace_or_none()
        if workspace is None or not node_ids:
            return []
        cache = self._context._bridge._payload_cache
        if not cache.backdrop_nodes:
            return []
        if not cache.indexes_valid:
            cache.rebuild_indexes()

        owner_backdrop_ids: set[str] = set()
        for node_id in sorted(node_ids):
            status, location = cache.resolve_node_payload_slot(node_id)
            if status != "ok" or location is None:
                return None
            collection_name, index = location
            collection = cache.nodes if collection_name == "nodes" else cache.backdrop_nodes
            owner_id = str(collection[index].get("owner_backdrop_id", "") or "").strip()
            if owner_id:
                owner_backdrop_ids.add(owner_id)

        updated_backdrops: list[dict[str, Any]] = []
        for backdrop_id in sorted(owner_backdrop_ids):
            status, location = cache.resolve_node_payload_slot(backdrop_id)
            if status != "ok" or location is None:
                return None
            collection_name, index = location
            if collection_name != "backdrop_nodes":
                return None
            backdrop_payload = cache.backdrop_nodes[index]
            backdrop_candidate = self._payload_candidate_from_payload(
                backdrop_payload,
                workspace=workspace,
                is_backdrop=True,
            )
            if backdrop_candidate is None:
                return None
            member_candidates: list[GroupBackdropCandidate] = []
            direct_member_ids = [
                *list(backdrop_payload.get("member_node_ids", []) or []),
                *list(backdrop_payload.get("member_backdrop_ids", []) or []),
            ]
            for member_id_value in direct_member_ids:
                member_id = str(member_id_value or "").strip()
                if not member_id:
                    continue
                member_status, member_location = cache.resolve_node_payload_slot(member_id)
                if member_status != "ok" or member_location is None:
                    return None
                member_collection_name, member_index = member_location
                member_collection = cache.nodes if member_collection_name == "nodes" else cache.backdrop_nodes
                member_candidate = self._payload_candidate_from_payload(
                    member_collection[member_index],
                    workspace=workspace,
                    is_backdrop=member_collection_name == "backdrop_nodes",
                )
                if member_candidate is None:
                    return None
                member_candidates.append(member_candidate)
            occupied = build_group_backdrop_occupied_bounds(backdrop_candidate, member_candidates)
            replacement = dict(backdrop_payload)
            replacement["expanded_occupied_bounds"] = {
                "x": float(occupied.x),
                "y": float(occupied.y),
                "width": float(occupied.width),
                "height": float(occupied.height),
            }
            cache.backdrop_nodes[index] = replacement
            updated_backdrops.append(replacement)
        return updated_backdrops

    def _cached_backdrop_candidates(self) -> list[GroupBackdropCandidate] | None:
        workspace = self._context.workspace_or_none()
        if workspace is None:
            return None
        cache = self._context._bridge._payload_cache
        candidates: list[GroupBackdropCandidate] = []
        for payload in cache.backdrop_nodes:
            node_id = str(payload.get("node_id", "") or "").strip()
            node = workspace.nodes.get(node_id)
            if node is None or bool(node.collapsed):
                return None
            candidate = self._payload_candidate_from_payload(
                payload,
                workspace=workspace,
                is_backdrop=True,
            )
            if candidate is None:
                return None
            candidates.append(candidate)
        return candidates

    @staticmethod
    def _payload_candidate_from_payload(
        payload: dict[str, Any],
        *,
        workspace,
        is_backdrop: bool,
        x: float | None = None,
        y: float | None = None,
    ) -> GroupBackdropCandidate | None:
        node_id = str(payload.get("node_id", "") or "").strip()
        if not node_id:
            return None
        try:
            width = float(payload.get("width", 0.0))
            height = float(payload.get("height", 0.0))
            candidate_x = float(payload.get("x", 0.0) if x is None else x)
            candidate_y = float(payload.get("y", 0.0) if y is None else y)
        except (TypeError, ValueError):
            return None
        return GroupBackdropCandidate(
            node_id=node_id,
            scope_path=node_scope_path(workspace, node_id),
            is_backdrop=bool(is_backdrop),
            x=candidate_x,
            y=candidate_y,
            width=width,
            height=height,
        )

    def replace_cached_node_position_payloads(
        self,
        node_ids: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
        """Returns ``None`` when a location-index slot no longer holds the
        node it is keyed for (stale index): writing through it would clobber
        another node's payload and leave a duplicate, so callers must fall
        back to a full rebuild."""
        workspace = self._context.workspace_or_none()
        if workspace is None or not node_ids:
            return [], []
        cache = self._context._bridge._payload_cache
        if not cache.indexes_valid:
            cache.rebuild_indexes()
        updated_nodes: list[dict[str, Any]] = []
        updated_minimap_nodes: list[dict[str, Any]] = []

        def _replace_position_fields(payload: dict[str, Any], node: NodeInstance) -> dict[str, Any]:
            replacement = dict(payload)
            replacement["x"] = float(node.x)
            replacement["y"] = float(node.y)
            return replacement

        for collection in (cache.nodes, cache.backdrop_nodes):
            collection_name = "nodes" if collection is cache.nodes else "backdrop_nodes"
            for node_id in sorted(node_ids):
                status, location = cache.resolve_node_payload_slot(node_id)
                if status == "mismatch":
                    return None
                if location is None:
                    continue
                location_collection, index = location
                if location_collection != collection_name:
                    continue
                payload = collection[index]
                node = workspace.nodes.get(node_id)
                if node is None:
                    continue
                replacement = _replace_position_fields(payload, node)
                collection[index] = replacement
                updated_nodes.append(replacement)

        for node_id in sorted(node_ids):
            status, index = cache.resolve_minimap_payload_slot(node_id)
            if status == "mismatch":
                return None
            if index is None:
                continue
            payload = cache.minimap_nodes[index]
            node = workspace.nodes.get(node_id)
            if node is None:
                continue
            replacement = _replace_position_fields(payload, node)
            cache.minimap_nodes[index] = replacement
            updated_minimap_nodes.append(replacement)

        return updated_nodes, updated_minimap_nodes

    def replace_cached_full_node_payloads(
        self,
        node_ids: set[str],
        *,
        changed_fields_by_node_id: dict[str, set[str] | frozenset[str] | tuple[str, ...] | None] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
        workspace = self._context.workspace_or_none()
        if workspace is None or not node_ids:
            return [], []
        node_ids = {
            normalized
            for value in node_ids
            if (normalized := str(value or "").strip())
        }
        if not node_ids:
            return [], []
        cache = self._context._bridge._payload_cache
        if not cache.indexes_valid:
            cache.rebuild_indexes()
        previous_payloads_by_id: dict[str, dict[str, Any]] = {}
        for node_id in sorted(node_ids):
            status, location = cache.resolve_node_payload_slot(node_id)
            if status == "mismatch":
                return None
            if location is None:
                continue
            collection_name, index = location
            collection = cache.nodes if collection_name == "nodes" else cache.backdrop_nodes
            previous_payloads_by_id[node_id] = collection[index]

        show_port_labels, label_size, icon_size, lightweight_canvas = (
            self._graphics_payload_facts()
        )
        nodes_payload, backdrop_nodes_payload, minimap_nodes_payload = (
            self._context._payload_builder.build_node_payloads_for_ids(
                model=self._context.model,
                registry=self._context.registry,
                workspace_id=self._context.workspace_id,
                scope_path=self._context.scope_path,
                node_ids=node_ids,
                graph_theme_bridge=self._context.graph_theme_bridge,
                show_port_labels=show_port_labels,
                graph_label_pixel_size=label_size,
                graph_node_icon_pixel_size=icon_size,
                lightweight_canvas=lightweight_canvas,
                port_connection_counts=self._cached_port_connection_counts_for_nodes(node_ids),
                previous_payloads_by_id=previous_payloads_by_id,
                changed_fields_by_node_id=changed_fields_by_node_id,
            )
        )
        payload_by_id = {
            node_id: payload
            for payload in (*nodes_payload, *backdrop_nodes_payload)
            if (node_id := str(payload.get("node_id", "") or "").strip())
        }
        minimap_payload_by_id = {
            node_id: payload
            for payload in minimap_nodes_payload
            if (node_id := str(payload.get("node_id", "") or "").strip())
        }
        if set(payload_by_id) != set(node_ids) or set(minimap_payload_by_id) != set(node_ids):
            return None

        updated_nodes: list[dict[str, Any]] = []
        updated_minimap_nodes: list[dict[str, Any]] = []
        for node_id in sorted(node_ids):
            status, location = cache.resolve_node_payload_slot(node_id)
            if status != "ok" or location is None:
                return None
            collection_name, index = location
            collection = cache.nodes if collection_name == "nodes" else cache.backdrop_nodes
            replacement = payload_by_id[node_id]
            collection[index] = replacement
            updated_nodes.append(replacement)

            minimap_status, minimap_index = cache.resolve_minimap_payload_slot(node_id)
            if minimap_status != "ok" or minimap_index is None:
                return None
            minimap_replacement = minimap_payload_by_id[node_id]
            cache.minimap_nodes[minimap_index] = minimap_replacement
            updated_minimap_nodes.append(minimap_replacement)

        return updated_nodes, updated_minimap_nodes

    def replace_cached_connection_node_payloads(self, node_ids: set[str]) -> list[dict[str, Any]] | None:
        """Returns ``None`` on a stale location-index slot (see
        :meth:`replace_cached_node_position_payloads`)."""
        show_port_labels, label_size, icon_size, lightweight_canvas = (
            self._graphics_payload_facts()
        )
        payload_updates = self._context._payload_builder.build_node_connection_payloads_for_ids(
            model=self._context.model,
            registry=self._context.registry,
            workspace_id=self._context.workspace_id,
            scope_path=self._context.scope_path,
            node_ids=node_ids,
            graph_theme_bridge=self._context.graph_theme_bridge,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=label_size,
            graph_node_icon_pixel_size=icon_size,
            lightweight_canvas=lightweight_canvas,
            port_connection_counts=self._cached_port_connection_counts_for_nodes(node_ids),
        )
        if not payload_updates:
            return []
        updated_payloads: list[dict[str, Any]] = []
        cache = self._context._bridge._payload_cache
        if not cache.indexes_valid:
            cache.rebuild_indexes()
        for node_id, update in payload_updates.items():
            status, location = cache.resolve_node_payload_slot(node_id)
            if status == "mismatch":
                return None
            if location is None:
                continue
            collection_name, index = location
            collection = cache.nodes if collection_name == "nodes" else cache.backdrop_nodes
            payload = collection[index]
            if (
                float(update.get("width", payload.get("width", 0.0)) or 0.0)
                != float(payload.get("width", 0.0) or 0.0)
                or float(update.get("height", payload.get("height", 0.0)) or 0.0)
                != float(payload.get("height", 0.0) or 0.0)
            ):
                return None
            replacement = dict(payload)
            replacement["ports"] = copy.deepcopy(update.get("ports", []))
            replacement["inline_properties"] = copy.deepcopy(update.get("inline_properties", []))
            for key in (
                "surface_metrics",
                "width",
                "height",
            ):
                if key in update:
                    replacement[key] = copy.deepcopy(update[key])
            if "plot_surface" in update:
                replacement["plot_surface"] = copy.deepcopy(update.get("plot_surface", {}))
                replacement["embedded_rendering_suppressed"] = bool(
                    update.get("embedded_rendering_suppressed", False)
                )
                replacement["embedded_rendering_suppressed_by"] = copy.deepcopy(
                    update.get("embedded_rendering_suppressed_by", [])
                )
            collection[index] = replacement
            updated_payloads.append(replacement)
        return updated_payloads

    def remove_cached_node_payloads(self, node_ids: set[str]) -> int:
        if not node_ids:
            return 0
        cache = self._context._bridge._payload_cache

        def _retain_node_payloads(payloads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
            retained: list[dict[str, Any]] = []
            removed_count = 0
            for payload in payloads:
                node_id = str(payload.get("node_id", "") or "").strip()
                if node_id in node_ids:
                    removed_count += 1
                    continue
                retained.append(payload)
            return retained, removed_count

        cache.nodes, removed_nodes = _retain_node_payloads(cache.nodes)
        cache.backdrop_nodes, removed_backdrops = _retain_node_payloads(cache.backdrop_nodes)
        cache.minimap_nodes, removed_minimap = _retain_node_payloads(cache.minimap_nodes)
        if removed_nodes or removed_backdrops or removed_minimap:
            cache.node_payload_location_by_id = {}
            for collection_name, payloads in (("nodes", cache.nodes), ("backdrop_nodes", cache.backdrop_nodes)):
                for index, payload in enumerate(payloads):
                    payload_node_id = str(payload.get("node_id", "") or "").strip()
                    if payload_node_id:
                        cache.node_payload_location_by_id[payload_node_id] = (collection_name, index)
            cache.minimap_node_index_by_id = {}
            for index, payload in enumerate(cache.minimap_nodes):
                payload_node_id = str(payload.get("node_id", "") or "").strip()
                if payload_node_id:
                    cache.minimap_node_index_by_id[payload_node_id] = index
        return removed_nodes + removed_backdrops + removed_minimap

    def replace_cached_edge_payloads(
        self,
        edge_ids: set[str],
        removed_edge_ids: set[str],
        *,
        reuse_existing_payloads: bool = False,
    ) -> list[dict[str, Any]]:
        workspace = self._context.workspace_or_none()
        if workspace is None:
            return []
        normalized_edge_ids = self._context._normalized_id_set(list(edge_ids))
        normalized_removed_ids = self._context._normalized_id_set(list(removed_edge_ids))
        if not normalized_edge_ids and not normalized_removed_ids:
            return []
        cache = self._context._bridge._payload_cache
        if not cache.indexes_valid:
            cache.rebuild_indexes()
        used_builder_fallback = False
        if reuse_existing_payloads:
            updated_payloads = [
                copy.deepcopy(payload)
                for edge_id in sorted(normalized_edge_ids, key=lambda value: cache.edge_index_by_id.get(value, len(cache.edges)))
                if (payload := cache.edge_payload_by_id.get(edge_id)) is not None
            ]
        else:
            updated_payloads = self.build_cached_edge_payloads_for_ids(normalized_edge_ids)
            if updated_payloads is None:
                used_builder_fallback = True
                self._context.record_mutation_counter("cached_edge_payload_fallback", reason="targeted_builder")
                show_port_labels, label_size, icon_size, lightweight_canvas = (
                    self._graphics_payload_facts()
                )
                updated_payloads = self._context._payload_builder.build_edge_payloads_for_ids(
                    model=self._context.model,
                    registry=self._context.registry,
                    workspace_id=self._context.workspace_id,
                    scope_path=self._context.scope_path,
                    edge_ids=normalized_edge_ids,
                    graph_theme_bridge=self._context.graph_theme_bridge,
                    comment_peek_node_id=self._context._validated_comment_peek_node_id(),
                    show_port_labels=show_port_labels,
                    graph_label_pixel_size=label_size,
                    graph_node_icon_pixel_size=icon_size,
                    lightweight_canvas=lightweight_canvas,
                )

        fallback_reason = ""
        updated_by_id = {
            self._context._edge_payload_id(payload): payload
            for payload in updated_payloads
            if self._context._edge_payload_id(payload)
        }
        slots_by_id: dict[str, int] = {}
        missing_edge_ids: set[str] = set()
        if len(updated_by_id) != len(updated_payloads) or set(updated_by_id) != normalized_edge_ids:
            fallback_reason = "partial_result"
        elif len(cache.edge_order) != len(cache.edges):
            fallback_reason = "order_mismatch"
        else:
            for edge_id in normalized_edge_ids:
                index = cache.edge_index_by_id.get(edge_id)
                if index is None:
                    missing_edge_ids.add(edge_id)
                    continue
                if not 0 <= index < len(cache.edges):
                    fallback_reason = "missing_slot"
                    break
                cached_payload = cache.edges[index]
                if self._context._edge_payload_id(cached_payload) != edge_id:
                    fallback_reason = "missing_slot"
                    break
                if cache.edge_order[index] != edge_id:
                    fallback_reason = "order_mismatch"
                    break
                if cache.edge_payload_by_id.get(edge_id) is not cached_payload:
                    fallback_reason = "cache_identity_mismatch"
                    break
                replacement = updated_by_id[edge_id]
                if any(replacement.get(field) != cached_payload.get(field) for field in _EDGE_ENDPOINT_FIELDS):
                    fallback_reason = "endpoint_change"
                    break
                slots_by_id[edge_id] = index

        if not fallback_reason:
            for edge_id, index in slots_by_id.items():
                replacement = updated_by_id[edge_id]
                cache.edges[index] = replacement
                cache.edge_payload_by_id[edge_id] = replacement
            if not missing_edge_ids and not normalized_removed_ids:
                self._context.record_mutation_counter(
                    "cached_edge_payload_in_place",
                    len(updated_payloads),
                )
                return updated_payloads

            if (
                not used_builder_fallback
                and len(missing_edge_ids) == 1
                and not normalized_removed_ids
            ):
                added_edge_id = next(iter(missing_edge_ids))
                if added_edge_id in workspace.edges and cache._insert_edge_payload(updated_by_id[added_edge_id]):
                    self._context.record_mutation_counter(
                        "cached_edge_payload_structural_incremental",
                        reason="added_edge",
                    )
                    return updated_payloads
                fallback_reason = "missing_slot"
            elif (
                not used_builder_fallback
                and len(normalized_removed_ids) == 1
                and not missing_edge_ids
            ):
                removed_edge_id = next(iter(normalized_removed_ids))
                if removed_edge_id not in workspace.edges and cache._remove_edge_payload(removed_edge_id):
                    self._context.record_mutation_counter(
                        "cached_edge_payload_structural_incremental",
                        reason="removed_edge",
                    )
                    return updated_payloads
                fallback_reason = "removed_edge"
            elif normalized_removed_ids:
                fallback_reason = "removed_edge"
            else:
                fallback_reason = "missing_slot"

        self._context.record_mutation_counter(
            "cached_edge_payload_in_place_fallback",
            reason=fallback_reason,
        )
        existing_by_id = {
            edge_id: payload
            for edge_id, payload in cache.edge_payload_by_id.items()
            if edge_id not in normalized_removed_ids
        }
        for edge_id in normalized_edge_ids:
            existing_by_id.pop(edge_id, None)
        for payload in updated_payloads:
            edge_id = self._context._edge_payload_id(payload)
            if edge_id:
                existing_by_id[edge_id] = payload
        ordered_edges: list[dict[str, Any]] = []
        seen_edge_ids: set[str] = set()
        for edge_id in cache.edge_order:
            payload = existing_by_id.get(edge_id)
            if payload is not None:
                ordered_edges.append(payload)
                seen_edge_ids.add(edge_id)
        for edge_id in workspace.edges:
            if edge_id in seen_edge_ids:
                continue
            payload = existing_by_id.get(edge_id)
            if payload is not None:
                ordered_edges.append(payload)
                seen_edge_ids.add(edge_id)
        cache.edges = ordered_edges
        cache.reindex_edges_only()
        return updated_payloads

    def build_cached_edge_payloads_for_ids(self, edge_ids: set[str]) -> list[dict[str, Any]] | None:
        workspace = self._context.workspace_or_none()
        registry = self._context.registry
        if workspace is None or registry is None or not edge_ids:
            return []
        cache = self._context._bridge._payload_cache
        if cache.backdrop_nodes or self._context._validated_comment_peek_node_id():
            self._context.record_mutation_counter("cached_edge_payload_fallback", reason="backdrop_or_comment_peek")
            return None
        if not cache.indexes_valid:
            cache.rebuild_indexes()

        show_port_labels, label_size, icon_size, lightweight_canvas = (
            self._graphics_payload_facts()
        )
        return self._context._payload_builder.build_unobscured_edge_payloads_for_ids(
            model=self._context.model,
            registry=registry,
            workspace_id=self._context.workspace_id,
            scope_path=self._context.scope_path,
            edge_ids=edge_ids,
            graph_theme_bridge=self._context.graph_theme_bridge,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=label_size,
            graph_node_icon_pixel_size=icon_size,
            lightweight_canvas=lightweight_canvas,
        )

    def replace_cached_node_payload(self, node_id: str, node: NodeInstance) -> list[dict[str, Any]] | None:
        """Returns ``None`` on a stale location-index slot (see
        :meth:`replace_cached_node_position_payloads`)."""
        del node
        replacement = self.replace_cached_full_node_payloads({node_id})
        if replacement is None:
            return None
        updated_payloads, _updated_minimap_payloads = replacement
        return updated_payloads
