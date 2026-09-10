from __future__ import annotations

from contextlib import contextmanager, nullcontext
import time
from typing import TYPE_CHECKING, Any, Callable

from ea_node_editor.app_preferences import (
    normalize_expand_collision_avoidance_settings,
    normalize_media_panel_settings,
)
from ea_node_editor.graph.hierarchy import ScopePath, is_node_in_scope
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.workspace_state import WorkspaceData, WorkspaceSnapshot
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.ui.graph_theme import GraphThemeDefinition
from ea_node_editor.ui_qml.graph_scene.payload_cache_sync import ScenePayloadCacheSync
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory, WorkspaceSnapshot
    from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


def _surface_title_sync_enabled(spec: NodeTypeSpec) -> bool:
    family = str(spec.surface_family or "").strip()
    return family in {"flowchart", "planning", "annotation", "group_backdrop"} and any(
        prop.key == "title" for prop in spec.properties
    )


def _synced_surface_title(node: NodeInstance, spec: NodeTypeSpec) -> str:
    if not _surface_title_sync_enabled(spec):
        return str(node.title).strip() or str(spec.display_name).strip()
    title_property = next(prop for prop in spec.properties if prop.key == "title")
    return str(node.properties.get("title", title_property.default)).strip()


def _sync_surface_title(node: NodeInstance, spec: NodeTypeSpec) -> None:
    if not _surface_title_sync_enabled(spec):
        return
    node.title = _synced_surface_title(node, spec)


class _GraphSceneContext:
    def __init__(self, bridge: GraphSceneBridge, payload_builder: GraphScenePayloadBuilder) -> None:
        self._bridge = bridge
        self._payload_builder = payload_builder
        self._payload_cache_sync = ScenePayloadCacheSync(self)
        self.workspace_id = ""
        self.scope_path: ScopePath = ()
        self.comment_peek_node_id = ""
        self.interact_with_locked_objects = False
        self.selected_node_ids: list[str] = []
        self.selected_node_lookup: dict[str, bool] = {}

    def _set_node_delta_payload(
        self,
        *,
        reason: str,
        node_payloads: list[dict[str, Any]],
        removed_node_ids: set[str] | None = None,
        added_node_ids: set[str] | None = None,
        visibility_may_change: bool = False,
    ) -> None:
        nodes_payload, backdrop_nodes_payload = self._split_node_payloads_by_collection(node_payloads)
        payload = {
            "kind": "node_delta",
            "reason": str(reason or "node_delta"),
            "nodes": list(nodes_payload),
            "backdrop_nodes": list(backdrop_nodes_payload),
            "removed_node_ids": sorted(str(node_id) for node_id in (removed_node_ids or set()) if str(node_id).strip()),
            "added_node_ids": sorted(str(node_id) for node_id in (added_node_ids or set()) if str(node_id).strip()),
            "visibility_may_change": bool(visibility_may_change),
        }
        setattr(self._bridge.state_bridge, "node_delta_payload", payload)

    def _clear_node_delta_payload(self) -> None:
        setattr(self._bridge.state_bridge, "node_delta_payload", {})

    def _split_node_payloads_by_collection(
        self,
        payloads: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        backdrop_ids = {
            str(payload.get("node_id", "") or "").strip()
            for payload in self._bridge._payload_cache.backdrop_nodes
            if str(payload.get("node_id", "") or "").strip()
        }
        nodes: list[dict[str, Any]] = []
        backdrops: list[dict[str, Any]] = []
        for payload in payloads:
            node_id = str(payload.get("node_id", "") or "").strip()
            if node_id in backdrop_ids:
                backdrops.append(payload)
            else:
                nodes.append(payload)
        return nodes, backdrops

    @property
    def model(self) -> GraphModel | None:
        return self._bridge._model

    @property
    def registry(self) -> NodeRegistry | None:
        return self._bridge._registry

    @property
    def history(self) -> RuntimeGraphHistory | None:
        return self._bridge._history

    @property
    def graph_theme_bridge(self) -> GraphThemeBridge | None:
        return self._bridge._graph_theme_bridge

    @property
    def graphics_show_port_labels(self) -> bool:
        return self._bridge.graphics_show_port_labels

    @property
    def graphics_graph_label_pixel_size(self) -> int:
        return self._bridge.graphics_graph_label_pixel_size

    @property
    def graphics_node_title_icon_pixel_size(self) -> int:
        return self._bridge.graphics_node_title_icon_pixel_size

    @property
    def graphics_lightweight_canvas(self) -> bool:
        return self._bridge.graphics_lightweight_canvas

    @property
    def graphics_expand_collision_avoidance(self) -> dict[str, Any]:
        source = self._bridge._graphics_preferences_source
        value = None if source is None else getattr(source, "graphics_expand_collision_avoidance", None)
        return normalize_expand_collision_avoidance_settings(value)

    @property
    def graphics_media_panel_defaults(self) -> dict[str, bool]:
        source = self._bridge._graphics_preferences_source
        value = (
            None
            if source is None
            else getattr(source, "graphics_media_panel_defaults", None)
        )
        return normalize_media_panel_settings(value)

    @property
    def backdrop_nodes_payload(self) -> list[dict[str, Any]]:
        return self._bridge._payload_cache.backdrop_nodes

    def require_bound(self) -> tuple[GraphModel, NodeRegistry]:
        if self.model is None or self.registry is None:
            raise RuntimeError("Scene is not bound")
        return self.model, self.registry

    def workspace_or_none(self) -> WorkspaceData | None:
        if self.model is None or not self.workspace_id:
            return None
        return self.model.project.workspaces.get(self.workspace_id)

    def current_workspace(self) -> WorkspaceData:
        if self.model is None:
            raise RuntimeError("Scene has no graph model")
        return self.model.project.workspaces[self.workspace_id]

    def _active_view_filter_state(self) -> tuple[str, bool]:
        workspace = self.workspace_or_none()
        if workspace is None:
            return "", False
        active_view = workspace.views.get(workspace.active_view_id)
        if active_view is None:
            active_view = next(iter(workspace.views.values()), None)
        if active_view is None:
            return "", False
        return (
            str(active_view.view_id),
            bool(active_view.hide_optional_ports),
        )

    def node(self, node_id: str) -> NodeInstance | None:
        workspace = self.workspace_or_none()
        if workspace is None:
            return None
        return workspace.nodes.get(node_id)

    def node_or_raise(self, node_id: str) -> NodeInstance:
        node = self.node(node_id)
        if node is None:
            raise KeyError(f"Unknown scene node: {node_id}")
        return node

    def find_model_edge_id(
        self,
        source_node_id: str,
        source_port: str,
        target_node_id: str,
        target_port: str,
    ) -> str | None:
        workspace = self.workspace_or_none()
        if workspace is None:
            return None
        for edge in workspace.edges.values():
            if (
                edge.source_node_id == source_node_id
                and edge.source_port_key == source_port
                and edge.target_node_id == target_node_id
                and edge.target_port_key == target_port
            ):
                return edge.edge_id
        return None

    @staticmethod
    def _normalized_id_set(values: set[str] | list[str] | tuple[str, ...]) -> set[str]:
        return {normalized for value in values if (normalized := str(value or "").strip())}

    @staticmethod
    def _edge_payload_id(payload: dict[str, Any]) -> str:
        return str(payload.get("edge_id", "") or "").strip()

    @staticmethod
    def _edge_payload_endpoint_node_ids(payload: dict[str, Any]) -> set[str]:
        return {
            node_id
            for key in ("source_node_id", "target_node_id")
            if (node_id := str(payload.get(key, "") or "").strip())
        }

    def _edge_delta_entries(self, edge_ids: set[str]) -> list[dict[str, Any]]:
        wanted_ids = self._normalized_id_set(list(edge_ids))
        if not wanted_ids:
            return []
        entries: list[dict[str, Any]] = []
        cache = self._bridge._payload_cache
        if not cache.indexes_valid:
            cache.rebuild_indexes()
        for edge_id in sorted(wanted_ids, key=lambda value: cache.edge_index_by_id.get(value, len(cache.edges))):
            payload = cache.edge_payload_by_id.get(edge_id)
            if payload is None:
                continue
            entries.append(
                {
                    "edge_id": edge_id,
                    "index": cache.edge_index_by_id.get(edge_id, len(cache.edges)),
                    "payload": dict(payload),
                }
            )
        return entries

    def _edge_structural_delta_payload(
        self,
        *,
        reason: str,
        added_edge_ids: set[str],
        updated_edge_ids: set[str],
        removed_edge_ids: set[str],
        dirty_node_ids: set[str],
        removed_node_ids: set[str],
    ) -> dict[str, Any]:
        cache = self._bridge._payload_cache
        dirty_edge_ids = added_edge_ids | updated_edge_ids | removed_edge_ids
        if not dirty_edge_ids:
            return {}
        added_edges = self._edge_delta_entries(added_edge_ids)
        updated_edges = self._edge_delta_entries(updated_edge_ids)
        affected_node_ids = set(dirty_node_ids) | set(removed_node_ids)
        for entry in (*added_edges, *updated_edges):
            payload = entry.get("payload", {})
            if isinstance(payload, dict):
                affected_node_ids.update(self._edge_payload_endpoint_node_ids(payload))
        delta_payload = cache.edge_delta_base_payload(
            reason=reason,
            requires_full_refresh=False,
            edge_count_after=len(cache.edges),
        )
        delta_payload.update(
            {
                "added_edge_ids": sorted(added_edge_ids),
                "updated_edge_ids": sorted(updated_edge_ids),
                "removed_edge_ids": sorted(removed_edge_ids),
                "dirty_edge_ids": sorted(dirty_edge_ids),
                "dirty_node_ids": sorted(dirty_node_ids),
                "removed_node_ids": sorted(removed_node_ids),
                "affected_node_ids": sorted(affected_node_ids),
                "added_edges": added_edges,
                "updated_edges": updated_edges,
                "removed_edges": [{"edge_id": edge_id} for edge_id in sorted(removed_edge_ids)],
            }
        )
        return delta_payload

    @staticmethod
    def _edge_lane_related(left: EdgeInstance, right: EdgeInstance) -> bool:
        return (
            (left.source_node_id, left.target_node_id) == (right.source_node_id, right.target_node_id)
            or (left.source_node_id, left.source_port_key) == (right.source_node_id, right.source_port_key)
            or (left.target_node_id, left.target_port_key) == (right.target_node_id, right.target_port_key)
        )

    @staticmethod
    def endpoint_node_ids_for_edges(edges: list[EdgeInstance]) -> set[str]:
        node_ids: set[str] = set()
        for edge in edges:
            node_ids.add(str(edge.source_node_id or ""))
            node_ids.add(str(edge.target_node_id or ""))
        return {node_id for node_id in node_ids if node_id}

    def incident_edges_for_node(self, node_id: str) -> list[EdgeInstance]:
        normalized_node_id = str(node_id or "").strip()
        workspace = self.workspace_or_none()
        if workspace is None or not normalized_node_id:
            return []
        cache = self._bridge._payload_cache
        if not cache.dirty and self._payload_cache_sync.payload_cache_matches_active_view():
            if not cache.indexes_valid:
                cache.rebuild_indexes()
            cached_edge_ids = cache.incident_edge_ids_by_node_id.get(normalized_node_id, set())
            return [
                edge
                for edge_id in cached_edge_ids
                if (edge := workspace.edges.get(edge_id)) is not None
            ]
        return [
            edge
            for edge in workspace.edges.values()
            if edge.source_node_id == normalized_node_id or edge.target_node_id == normalized_node_id
        ]

    def related_edge_ids_for_edges(self, edges: list[EdgeInstance]) -> set[str]:
        workspace = self.workspace_or_none()
        if workspace is None or not edges:
            return set()
        cache = self._bridge._payload_cache
        if not cache.dirty and self._payload_cache_sync.payload_cache_matches_active_view():
            if not cache.indexes_valid:
                cache.rebuild_indexes()
            related: set[str] = set()
            for edge in edges:
                edge_id = str(edge.edge_id or "").strip()
                if edge_id:
                    related.add(edge_id)
                source_node_id = str(edge.source_node_id or "").strip()
                target_node_id = str(edge.target_node_id or "").strip()
                source_port_key = str(edge.source_port_key or "").strip()
                target_port_key = str(edge.target_port_key or "").strip()
                if source_node_id and target_node_id:
                    related.update(cache.edge_ids_by_pair.get((source_node_id, target_node_id), set()))
                if source_node_id and source_port_key:
                    related.update(cache.edge_ids_by_source_port.get((source_node_id, source_port_key), set()))
                if target_node_id and target_port_key:
                    related.update(cache.edge_ids_by_target_port.get((target_node_id, target_port_key), set()))
            return {edge_id for edge_id in related if edge_id in workspace.edges}
        related: set[str] = set()
        for current in workspace.edges.values():
            if any(current.edge_id == edge.edge_id or self._edge_lane_related(current, edge) for edge in edges):
                related.add(current.edge_id)
        return related

    def edge_item(self, edge_id: str) -> dict[str, Any] | None:
        workspace = self.workspace_or_none()
        if workspace is None:
            return None
        return self._payload_builder.edge_item(
            workspace=workspace,
            scope_path=self.scope_path,
            edge_id=edge_id,
        )

    def publish_edge_topology_delta(
        self,
        *,
        added_edge_ids: set[str] | None = None,
        updated_edge_ids: set[str] | None = None,
        removed_edge_ids: set[str] | None = None,
        dirty_node_ids: set[str] | None = None,
        removed_node_ids: set[str] | None = None,
        publication_path: str = "edge_topology_delta",
    ) -> bool:
        workspace = self.workspace_or_none()
        if workspace is None:
            return False
        cache = self._bridge._payload_cache
        if cache.dirty or not self._payload_cache_sync.payload_cache_matches_active_view():
            self.rebuild_models()
            return True

        added_ids = self._normalized_id_set(list(added_edge_ids or set()))
        removed_ids = self._normalized_id_set(list(removed_edge_ids or set()))
        updated_ids = self._normalized_id_set(list(updated_edge_ids or set())) - removed_ids - added_ids
        removed_nodes = self._normalized_id_set(list(removed_node_ids or set()))
        dirty_nodes = self._normalized_id_set(list(dirty_node_ids or set())) | removed_nodes

        timing_enabled = self.mutation_timing_enabled()
        payload_start = time.perf_counter()
        removed_node_count = self._payload_cache_sync.remove_cached_node_payloads(removed_nodes)
        edge_payloads = self._payload_cache_sync.replace_cached_edge_payloads((added_ids | updated_ids) - removed_ids, removed_ids)
        node_payloads = self._payload_cache_sync.replace_cached_connection_node_payloads(dirty_nodes - removed_nodes)
        if node_payloads is None:
            self.record_mutation_counter("payload_cache_slot_identity_mismatch", reason=publication_path)
            self.rebuild_models()
            return True
        if timing_enabled:
            self.record_mutation_timing_phase(
                "payload_rebuild_ms",
                (time.perf_counter() - payload_start) * 1000.0,
            )

        dirty_edge_ids = added_ids | updated_ids | removed_ids
        delta_payload = self._edge_structural_delta_payload(
            reason="edge_topology",
            added_edge_ids=added_ids,
            updated_edge_ids=updated_ids,
            removed_edge_ids=removed_ids,
            dirty_node_ids=dirty_nodes,
            removed_node_ids=removed_nodes,
        )
        cache.edge_delta_payload = delta_payload
        if timing_enabled:
            self.record_mutation_payload_metrics(
                nodes_payload=node_payloads,
                edges_payload=edge_payloads,
                dirty_node_count=len(dirty_nodes),
                dirty_edge_count=len(dirty_edge_ids),
                scene_publication_dirty_node_count=len(dirty_nodes),
                scene_publication_dirty_edge_count=len(dirty_edge_ids),
                scene_publication_path=publication_path,
                graph_delta_payload=delta_payload,
            )

        publish_start = time.perf_counter()
        try:
            if dirty_nodes or removed_node_count:
                self._set_node_delta_payload(
                    reason=publication_path,
                    node_payloads=node_payloads,
                    removed_node_ids=removed_nodes,
                    visibility_may_change=bool(removed_nodes),
                )
            else:
                self._clear_node_delta_payload()
            if dirty_nodes or removed_node_count:
                self._bridge.nodes_changed.emit()
            if dirty_edge_ids:
                self._bridge.edges_changed.emit()
        finally:
            if timing_enabled:
                self.record_mutation_timing_phase(
                    "scene_publish_ms",
                    (time.perf_counter() - publish_start) * 1000.0,
                )
        return True

    def publish_node_addition_delta(
        self,
        node_id: str,
        *,
        publication_path: str = "node_addition_delta",
    ) -> bool:
        normalized_node_id = str(node_id or "").strip()
        workspace = self.workspace_or_none()
        if workspace is None or not normalized_node_id:
            return False
        node = workspace.nodes.get(normalized_node_id)
        if node is None:
            return False
        cache = self._bridge._payload_cache
        if not cache.dirty:
            if not cache.indexes_valid:
                cache.rebuild_indexes()
            if normalized_node_id in cache.node_payload_location_by_id:
                return self.publish_node_payload_update(
                    normalized_node_id,
                    publication_path=publication_path,
                )
        return self.publish_node_additions_delta(
            {normalized_node_id},
            publication_path=publication_path,
        )

    def publish_node_additions_delta(
        self,
        node_ids: set[str] | list[str] | tuple[str, ...],
        *,
        added_edge_ids: set[str] | list[str] | tuple[str, ...] = (),
        publication_path: str = "node_additions_delta",
    ) -> bool:
        workspace = self.workspace_or_none()
        requested_node_ids = self._normalized_id_set(list(node_ids))
        requested_edge_ids = self._normalized_id_set(list(added_edge_ids))
        if workspace is None or not requested_node_ids:
            return False
        if any(node_id not in workspace.nodes for node_id in requested_node_ids):
            return False
        cache = self._bridge._payload_cache
        if cache.dirty or not self._payload_cache_sync.payload_cache_matches_active_view():
            self.rebuild_models()
            return True
        if cache.comment_peek_node_id:
            self.rebuild_models()
            return True
        if not cache.indexes_valid:
            cache.rebuild_indexes()

        visible_added_node_ids = {
            node_id
            for node_id in requested_node_ids
            if is_node_in_scope(workspace, node_id, self.scope_path)
        }
        visible_added_edge_ids = {
            edge_id
            for edge_id in requested_edge_ids
            if (edge := workspace.edges.get(edge_id)) is not None
            and is_node_in_scope(workspace, edge.source_node_id, self.scope_path)
            and is_node_in_scope(workspace, edge.target_node_id, self.scope_path)
        }
        if not visible_added_node_ids:
            self._clear_node_delta_payload()
            cache.edge_delta_payload = {}
            return True

        timing_enabled = self.mutation_timing_enabled()
        payload_start = time.perf_counter()
        port_connection_counts = (
            None
            if visible_added_edge_ids
            else cache.port_connection_counts_for_nodes(visible_added_node_ids)
        )
        nodes_payload, backdrop_nodes_payload, minimap_nodes_payload = (
            self._payload_builder.build_added_node_payloads_for_ids(
                model=self.model,
                registry=self.registry,
                workspace_id=self.workspace_id,
                scope_path=self.scope_path,
                node_ids=visible_added_node_ids,
                graph_theme_bridge=self.graph_theme_bridge,
                show_port_labels=self.graphics_show_port_labels,
                graph_label_pixel_size=self.graphics_graph_label_pixel_size,
                graph_node_icon_pixel_size=self.graphics_node_title_icon_pixel_size,
                lightweight_canvas=self.graphics_lightweight_canvas,
                port_connection_counts=port_connection_counts,
            )
        )
        appended = self._payload_cache_sync.append_added_node_payloads(
            nodes_payload=nodes_payload,
            backdrop_nodes_payload=backdrop_nodes_payload,
            minimap_nodes_payload=minimap_nodes_payload,
        )
        if appended is None or appended[1] != visible_added_node_ids:
            self.record_mutation_counter("payload_cache_slot_identity_mismatch", reason=publication_path)
            self.rebuild_models()
            return True
        node_delta_payloads, appended_node_ids = appended

        edge_payloads = self._payload_cache_sync.replace_cached_edge_payloads(
            visible_added_edge_ids,
            set(),
        )
        published_edge_ids = {
            self._edge_payload_id(payload)
            for payload in edge_payloads
            if self._edge_payload_id(payload)
        }
        if published_edge_ids != visible_added_edge_ids:
            self.record_mutation_counter("payload_cache_slot_identity_mismatch", reason=publication_path)
            self.rebuild_models()
            return True
        if timing_enabled:
            self.record_mutation_timing_phase(
                "payload_rebuild_ms",
                (time.perf_counter() - payload_start) * 1000.0,
            )

        edge_delta_payload = self._edge_structural_delta_payload(
            reason=publication_path,
            added_edge_ids=visible_added_edge_ids,
            updated_edge_ids=set(),
            removed_edge_ids=set(),
            dirty_node_ids=appended_node_ids,
            removed_node_ids=set(),
        )
        cache.edge_delta_payload = edge_delta_payload
        if timing_enabled:
            self.record_mutation_payload_metrics(
                nodes_payload=node_delta_payloads,
                minimap_nodes_payload=minimap_nodes_payload,
                edges_payload=edge_payloads,
                dirty_node_count=len(node_delta_payloads),
                dirty_edge_count=len(visible_added_edge_ids),
                scene_publication_dirty_node_count=len(node_delta_payloads),
                scene_publication_dirty_edge_count=len(visible_added_edge_ids),
                scene_publication_path=publication_path,
                graph_delta_payload=edge_delta_payload,
            )

        publish_start = time.perf_counter()
        try:
            self._set_node_delta_payload(
                reason=publication_path,
                node_payloads=node_delta_payloads,
                added_node_ids=appended_node_ids,
                visibility_may_change=True,
            )
            self._bridge.nodes_changed.emit()
            if visible_added_edge_ids:
                self._bridge.edges_changed.emit()
        finally:
            if timing_enabled:
                self.record_mutation_timing_phase(
                    "scene_publish_ms",
                    (time.perf_counter() - publish_start) * 1000.0,
                )
        return True

    def publish_node_position_delta(
        self,
        node_ids: set[str] | list[str] | tuple[str, ...],
        *,
        publication_path: str = "node_position_delta",
    ) -> bool:
        workspace = self.workspace_or_none()
        if workspace is None:
            return False
        moved_node_ids = self._normalized_id_set(list(node_ids))
        if not moved_node_ids:
            return False
        cache = self._bridge._payload_cache
        if cache.dirty or not self._payload_cache_sync.payload_cache_matches_active_view():
            self.rebuild_models()
            return True
        if cache.comment_peek_node_id:
            self.rebuild_models()
            return True
        if cache.backdrop_nodes and not self._payload_cache_sync.can_apply_backdrop_position_delta(
            moved_node_ids
        ):
            self.rebuild_models()
            return True
        cached_node_ids = self._payload_cache_sync.cached_node_payload_ids()
        if not moved_node_ids.issubset(cached_node_ids):
            self.rebuild_models()
            return True

        incident_edges: list[EdgeInstance] = []
        for node_id in moved_node_ids:
            incident_edges.extend(self.incident_edges_for_node(node_id))
        dirty_edge_ids = self.related_edge_ids_for_edges(incident_edges)

        timing_enabled = self.mutation_timing_enabled()
        payload_start = time.perf_counter()
        position_replacements = self._payload_cache_sync.replace_cached_node_position_payloads(moved_node_ids)
        if position_replacements is None:
            self.record_mutation_counter("payload_cache_slot_identity_mismatch", reason=publication_path)
            self.rebuild_models()
            return True
        node_payloads, minimap_payloads = position_replacements
        backdrop_payloads: list[dict[str, Any]] = []
        if cache.backdrop_nodes:
            refreshed_backdrops = self._payload_cache_sync.refresh_cached_backdrop_occupied_bounds_for_node_ids(
                moved_node_ids
            )
            if refreshed_backdrops is None:
                self.rebuild_models()
                return True
            backdrop_payloads = refreshed_backdrops
        node_delta_payloads = [*node_payloads, *backdrop_payloads]
        edge_payloads = self._payload_cache_sync.replace_cached_edge_payloads(dirty_edge_ids, set())
        if timing_enabled:
            self.record_mutation_timing_phase(
                "payload_rebuild_ms",
                (time.perf_counter() - payload_start) * 1000.0,
            )

        delta_payload = self._edge_structural_delta_payload(
            reason="node_position",
            added_edge_ids=set(),
            updated_edge_ids=dirty_edge_ids,
            removed_edge_ids=set(),
            dirty_node_ids=moved_node_ids,
            removed_node_ids=set(),
        )
        cache.edge_delta_payload = delta_payload
        if timing_enabled:
            self.record_mutation_payload_metrics(
                nodes_payload=node_delta_payloads,
                minimap_nodes_payload=minimap_payloads,
                edges_payload=edge_payloads,
                dirty_node_count=len(moved_node_ids),
                dirty_edge_count=len(dirty_edge_ids),
                scene_publication_dirty_node_count=len(moved_node_ids) + len(backdrop_payloads),
                scene_publication_dirty_edge_count=len(dirty_edge_ids),
                scene_publication_path=publication_path,
                graph_delta_payload=delta_payload,
            )

        publish_start = time.perf_counter()
        try:
            self._set_node_delta_payload(
                reason=publication_path,
                node_payloads=node_delta_payloads,
                visibility_may_change=True,
            )
            self._bridge.nodes_changed.emit()
            if dirty_edge_ids:
                self._bridge.edges_changed.emit()
        finally:
            if timing_enabled:
                self.record_mutation_timing_phase(
                    "scene_publish_ms",
                    (time.perf_counter() - publish_start) * 1000.0,
                )
        return True

    def publish_node_geometry_delta(
        self,
        node_ids: set[str] | list[str] | tuple[str, ...],
        *,
        position_node_ids: set[str] | list[str] | tuple[str, ...] | None = None,
        publication_path: str = "node_geometry_delta",
    ) -> bool:
        workspace = self.workspace_or_none()
        if workspace is None:
            return False
        geometry_node_ids = self._normalized_id_set(list(node_ids))
        moved_node_ids = self._normalized_id_set(list(position_node_ids or ())) - geometry_node_ids
        changed_node_ids = geometry_node_ids | moved_node_ids
        if not changed_node_ids:
            return False
        cache = self._bridge._payload_cache
        if cache.dirty or not self._payload_cache_sync.payload_cache_matches_active_view():
            self.rebuild_models()
            return True
        if cache.backdrop_nodes or self._validated_comment_peek_node_id():
            self.rebuild_models()
            return True
        if self._node_geometry_delta_requires_full_rebuild(changed_node_ids):
            self.rebuild_models()
            return True
        cached_node_ids = self._payload_cache_sync.cached_node_payload_ids()
        if not changed_node_ids.issubset(cached_node_ids):
            self.rebuild_models()
            return True

        incident_edges: list[EdgeInstance] = []
        for node_id in sorted(changed_node_ids):
            incident_edges.extend(self.incident_edges_for_node(node_id))
        dirty_edge_ids = self.related_edge_ids_for_edges(incident_edges)

        timing_enabled = self.mutation_timing_enabled()
        payload_start = time.perf_counter()
        geometry_replacements = self._payload_cache_sync.replace_cached_full_node_payloads(geometry_node_ids)
        if geometry_replacements is None:
            self.rebuild_models()
            return True
        geometry_payloads, geometry_minimap_payloads = geometry_replacements
        position_replacements = self._payload_cache_sync.replace_cached_node_position_payloads(moved_node_ids)
        if position_replacements is None:
            self.record_mutation_counter("payload_cache_slot_identity_mismatch", reason=publication_path)
            self.rebuild_models()
            return True
        position_payloads, position_minimap_payloads = position_replacements
        node_payloads = [*geometry_payloads, *position_payloads]
        minimap_payloads = [*geometry_minimap_payloads, *position_minimap_payloads]
        edge_payloads = self._payload_cache_sync.replace_cached_edge_payloads(dirty_edge_ids, set())
        if timing_enabled:
            self.record_mutation_timing_phase(
                "payload_rebuild_ms",
                (time.perf_counter() - payload_start) * 1000.0,
            )

        delta_payload = self._edge_structural_delta_payload(
            reason="node_geometry",
            added_edge_ids=set(),
            updated_edge_ids=dirty_edge_ids,
            removed_edge_ids=set(),
            dirty_node_ids=changed_node_ids,
            removed_node_ids=set(),
        )
        cache.edge_delta_payload = delta_payload
        if timing_enabled:
            self.record_mutation_payload_metrics(
                nodes_payload=node_payloads,
                minimap_nodes_payload=minimap_payloads,
                edges_payload=edge_payloads,
                dirty_node_count=len(changed_node_ids),
                dirty_edge_count=len(dirty_edge_ids),
                scene_publication_dirty_node_count=len(node_payloads),
                scene_publication_dirty_edge_count=len(dirty_edge_ids),
                scene_publication_path=publication_path,
                graph_delta_payload=delta_payload,
            )

        publish_start = time.perf_counter()
        try:
            self._set_node_delta_payload(
                reason=publication_path,
                node_payloads=node_payloads,
                visibility_may_change=True,
            )
            self._bridge.nodes_changed.emit()
            if dirty_edge_ids:
                self._bridge.edges_changed.emit()
        finally:
            if timing_enabled:
                self.record_mutation_timing_phase(
                    "scene_publish_ms",
                    (time.perf_counter() - publish_start) * 1000.0,
                )
        return True

    def _node_geometry_delta_requires_full_rebuild(self, node_ids: set[str]) -> bool:
        workspace = self.workspace_or_none()
        registry = self.registry
        if workspace is None or registry is None:
            return True
        for node_id in node_ids:
            node = workspace.nodes.get(node_id)
            if node is None:
                return True
            spec = registry.spec_or_none(node.type_id)
            if spec is None:
                return True
            if str(spec.surface_family or "").strip() == "group_backdrop":
                return True
        return False

    def mutation_timing_enabled(self) -> bool:
        timing_enabled = getattr(self._bridge, "mutation_timing_enabled", None)
        return callable(timing_enabled) and bool(timing_enabled())

    def record_mutation_timing_phase(self, phase_name: str, elapsed_ms: float) -> None:
        recorder = getattr(self._bridge, "record_mutation_timing_phase", None)
        if callable(recorder):
            recorder(phase_name, elapsed_ms)

    def record_mutation_payload_metrics(self, **metrics: Any) -> None:
        recorder = getattr(self._bridge, "record_mutation_payload_metrics", None)
        if callable(recorder):
            recorder(**metrics)

    def record_mutation_counter(self, counter_name: str, amount: int = 1, *, reason: str = "") -> None:
        recorder = getattr(self._bridge, "record_mutation_counter", None)
        if callable(recorder):
            recorder(counter_name, amount, reason=reason)

    def rebuild_models(self) -> None:
        timing_enabled = self.mutation_timing_enabled()
        if timing_enabled:
            self.record_mutation_counter("scene_rebuild_models", reason="full_rebuild")
        self._payload_builder.set_mutation_timing_enabled(timing_enabled)
        payload_start = time.perf_counter()
        try:
            (
                nodes_payload,
                backdrop_nodes_payload,
                minimap_nodes_payload,
                edges_payload,
            ) = self._payload_builder.rebuild_partitioned_models(
                model=self.model,
                registry=self.registry,
                workspace_id=self.workspace_id,
                scope_path=self.scope_path,
                comment_peek_node_id=self._validated_comment_peek_node_id(),
                graph_theme_bridge=self.graph_theme_bridge,
                show_port_labels=self.graphics_show_port_labels,
                graph_label_pixel_size=self.graphics_graph_label_pixel_size,
                graph_node_icon_pixel_size=self.graphics_node_title_icon_pixel_size,
                lightweight_canvas=self.graphics_lightweight_canvas,
            )
        finally:
            self._payload_builder.set_mutation_timing_enabled(False)
        if timing_enabled:
            self.record_mutation_timing_phase(
                "payload_rebuild_ms",
                (time.perf_counter() - payload_start) * 1000.0,
            )
            for phase_name, elapsed_ms in self._payload_builder.mutation_phase_timings_ms().items():
                self.record_mutation_timing_phase(phase_name, elapsed_ms)
            self.record_mutation_payload_metrics(
                nodes_payload=nodes_payload,
                backdrop_nodes_payload=backdrop_nodes_payload,
                minimap_nodes_payload=minimap_nodes_payload,
                edges_payload=edges_payload,
                scene_publication_dirty_node_count=len(nodes_payload) + len(backdrop_nodes_payload),
                scene_publication_dirty_edge_count=len(edges_payload),
                scene_publication_path="full_rebuild",
            )
        publish_start = time.perf_counter()
        try:
            self._clear_node_delta_payload()
            active_view_id, hide_optional_ports = self._active_view_filter_state()
            self._bridge._payload_cache.update(
                nodes=nodes_payload,
                backdrop_nodes=backdrop_nodes_payload,
                minimap_nodes=minimap_nodes_payload,
                edges=edges_payload,
                active_view_id=active_view_id,
                hide_optional_ports=hide_optional_ports,
                comment_peek_node_id=self._validated_comment_peek_node_id(),
            )
            self._bridge.nodes_changed.emit()
            self._bridge.edges_changed.emit()
        finally:
            if timing_enabled:
                self.record_mutation_timing_phase(
                    "scene_publish_ms",
                    (time.perf_counter() - publish_start) * 1000.0,
                )

    def publish_node_payload_update(
        self,
        node_id: str,
        *,
        publication_path: str = "targeted_node_payload",
    ) -> bool:
        normalized_node_id = str(node_id or "").strip()
        workspace = self.workspace_or_none()
        if workspace is None or not normalized_node_id:
            return False
        node = workspace.nodes.get(normalized_node_id)
        if node is None:
            return False
        cache = self._bridge._payload_cache
        if cache.dirty or not self._payload_cache_sync.payload_cache_matches_active_view():
            self.rebuild_models()
            return True
        cache.edge_delta_payload = {}

        timing_enabled = self.mutation_timing_enabled()
        payload_start = time.perf_counter()
        updated_payloads = self._payload_cache_sync.replace_cached_node_payload(normalized_node_id, node)
        if updated_payloads is None:
            self.record_mutation_counter("payload_cache_slot_identity_mismatch", reason=publication_path)
            self.rebuild_models()
            return True
        if timing_enabled:
            self.record_mutation_timing_phase(
                "payload_rebuild_ms",
                (time.perf_counter() - payload_start) * 1000.0,
            )
            self.record_mutation_payload_metrics(
                nodes_payload=updated_payloads,
                dirty_node_count=1,
                dirty_edge_count=0,
                scene_publication_dirty_node_count=1,
                scene_publication_dirty_edge_count=0,
                scene_publication_path=publication_path,
            )

        if not updated_payloads:
            return True

        publish_start = time.perf_counter()
        try:
            self._bridge._payload_cache.edge_delta_payload = {}
            self._set_node_delta_payload(reason=publication_path, node_payloads=updated_payloads)
            self._bridge.nodes_changed.emit()
        finally:
            if timing_enabled:
                self.record_mutation_timing_phase(
                    "scene_publish_ms",
                    (time.perf_counter() - publish_start) * 1000.0,
                )
        return True

    @staticmethod
    def _node_geometry_signature(payload: dict[str, Any]) -> tuple[float, float, float, float]:
        values: list[float] = []
        for key in ("x", "y", "width", "height"):
            try:
                values.append(round(float(payload.get(key, 0.0)), 6))
            except (TypeError, ValueError):
                values.append(0.0)
        return values[0], values[1], values[2], values[3]

    def publish_node_title_payload_delta(
        self,
        node_id: str,
        *,
        publication_path: str = "title_payload_delta",
        changed_fields: set[str] | frozenset[str] | tuple[str, ...] | None = None,
    ) -> bool:
        normalized_node_id = str(node_id or "").strip()
        workspace = self.workspace_or_none()
        if workspace is None or not normalized_node_id:
            return False
        if normalized_node_id not in workspace.nodes:
            return False
        cache = self._bridge._payload_cache
        if cache.dirty or not self._payload_cache_sync.payload_cache_matches_active_view():
            self.rebuild_models()
            return True
        if not cache.indexes_valid:
            cache.rebuild_indexes()
        status, location = cache.resolve_node_payload_slot(normalized_node_id)
        if status != "ok" or location is None:
            if status == "mismatch":
                self.record_mutation_counter("payload_cache_slot_identity_mismatch", reason=publication_path)
            self.rebuild_models()
            return True
        collection_name, index = location
        collection = cache.nodes if collection_name == "nodes" else cache.backdrop_nodes
        previous_geometry = self._node_geometry_signature(collection[index])

        timing_enabled = self.mutation_timing_enabled()
        payload_start = time.perf_counter()
        changed_fields_by_node_id = (
            {normalized_node_id: changed_fields} if changed_fields is not None else None
        )
        replacements = self._payload_cache_sync.replace_cached_full_node_payloads(
            {normalized_node_id},
            changed_fields_by_node_id=changed_fields_by_node_id,
        )
        if replacements is None:
            self.rebuild_models()
            return True
        node_payloads, minimap_payloads = replacements
        current_geometry = (
            self._node_geometry_signature(node_payloads[0])
            if node_payloads
            else previous_geometry
        )
        geometry_changed = current_geometry != previous_geometry
        dirty_edge_ids: set[str] = set()
        edge_payloads: list[dict[str, Any]] = []
        if geometry_changed:
            incident_edges = self.incident_edges_for_node(normalized_node_id)
            dirty_edge_ids = self.related_edge_ids_for_edges(incident_edges)
            if dirty_edge_ids:
                edge_payloads = self._payload_cache_sync.replace_cached_edge_payloads(dirty_edge_ids, set())
                cache.edge_delta_payload = self._edge_structural_delta_payload(
                    reason="node_title",
                    added_edge_ids=set(),
                    updated_edge_ids=dirty_edge_ids,
                    removed_edge_ids=set(),
                    dirty_node_ids={normalized_node_id},
                    removed_node_ids=set(),
                )
            else:
                cache.edge_delta_payload = {}
        else:
            cache.edge_delta_payload = {}
        if timing_enabled:
            self.record_mutation_timing_phase(
                "payload_rebuild_ms",
                (time.perf_counter() - payload_start) * 1000.0,
            )
            self.record_mutation_payload_metrics(
                nodes_payload=node_payloads,
                minimap_nodes_payload=minimap_payloads,
                edges_payload=edge_payloads,
                dirty_node_count=1,
                dirty_edge_count=len(dirty_edge_ids),
                scene_publication_dirty_node_count=len(node_payloads),
                scene_publication_dirty_edge_count=len(dirty_edge_ids),
                scene_publication_path=publication_path,
                graph_delta_payload=cache.edge_delta_payload,
            )

        if not node_payloads:
            self._clear_node_delta_payload()
            return True

        publish_start = time.perf_counter()
        try:
            self._set_node_delta_payload(reason=publication_path, node_payloads=node_payloads)
            self._bridge.nodes_changed.emit()
            if dirty_edge_ids:
                self._bridge.edges_changed.emit()
        finally:
            if timing_enabled:
                self.record_mutation_timing_phase(
                    "scene_publish_ms",
                    (time.perf_counter() - publish_start) * 1000.0,
                )
        return True

    def publish_node_payload_delta(
        self,
        node_id: str,
        *,
        publication_path: str = "node_payload_delta",
        edge_delta_reason: str = "node_payload",
        changed_fields: set[str] | frozenset[str] | tuple[str, ...] | None = None,
    ) -> bool:
        normalized_node_id = str(node_id or "").strip()
        workspace = self.workspace_or_none()
        if workspace is None or not normalized_node_id:
            return False
        if normalized_node_id not in workspace.nodes:
            return False
        cache = self._bridge._payload_cache
        if cache.dirty or not self._payload_cache_sync.payload_cache_matches_active_view():
            self.rebuild_models()
            return True
        if not cache.indexes_valid:
            cache.rebuild_indexes()
        if normalized_node_id not in cache.node_payload_location_by_id:
            self.rebuild_models()
            return True

        incident_edges = self.incident_edges_for_node(normalized_node_id)
        dirty_edge_ids = self.related_edge_ids_for_edges(incident_edges)

        timing_enabled = self.mutation_timing_enabled()
        payload_start = time.perf_counter()
        changed_fields_by_node_id = (
            {normalized_node_id: changed_fields} if changed_fields is not None else None
        )
        replacements = self._payload_cache_sync.replace_cached_full_node_payloads(
            {normalized_node_id},
            changed_fields_by_node_id=changed_fields_by_node_id,
        )
        if replacements is None:
            self.rebuild_models()
            return True
        node_payloads, minimap_payloads = replacements
        edge_payloads = self._payload_cache_sync.replace_cached_edge_payloads(dirty_edge_ids, set())
        if timing_enabled:
            self.record_mutation_timing_phase(
                "payload_rebuild_ms",
                (time.perf_counter() - payload_start) * 1000.0,
            )

        delta_payload = self._edge_structural_delta_payload(
            reason=edge_delta_reason,
            added_edge_ids=set(),
            updated_edge_ids=dirty_edge_ids,
            removed_edge_ids=set(),
            dirty_node_ids={normalized_node_id},
            removed_node_ids=set(),
        )
        cache.edge_delta_payload = delta_payload
        if timing_enabled:
            self.record_mutation_payload_metrics(
                nodes_payload=node_payloads,
                minimap_nodes_payload=minimap_payloads,
                edges_payload=edge_payloads,
                dirty_node_count=1,
                dirty_edge_count=len(dirty_edge_ids),
                scene_publication_dirty_node_count=len(node_payloads),
                scene_publication_dirty_edge_count=len(dirty_edge_ids),
                scene_publication_path=publication_path,
                graph_delta_payload=delta_payload,
            )

        if not node_payloads:
            self._clear_node_delta_payload()
            return True

        publish_start = time.perf_counter()
        try:
            self._set_node_delta_payload(
                reason=publication_path,
                node_payloads=node_payloads,
                visibility_may_change=False,
            )
            self._bridge.nodes_changed.emit()
            if dirty_edge_ids:
                self._bridge.edges_changed.emit()
        finally:
            if timing_enabled:
                self.record_mutation_timing_phase(
                    "scene_publish_ms",
                    (time.perf_counter() - publish_start) * 1000.0,
                )
        return True

    def publish_node_property_delta(
        self,
        node_id: str,
        *,
        publication_path: str = "node_property_payload_delta",
        changed_fields: set[str] | frozenset[str] | tuple[str, ...] | None = None,
    ) -> bool:
        return self.publish_node_payload_delta(
            node_id,
            publication_path=publication_path,
            edge_delta_reason="node_property",
            changed_fields=changed_fields,
        )

    def publish_history_entry_delta(self, entry: Any) -> bool:
        replay = self._history_replay_snapshots(entry)
        if replay is None:
            return False
        source_snapshot, target_snapshot = replay
        if not self._history_replay_metadata_is_stable(source_snapshot, target_snapshot):
            return False
        return (
            self._publish_history_node_position_delta(source_snapshot, target_snapshot)
            or self._publish_history_edge_topology_delta(source_snapshot, target_snapshot)
        )

    def _history_replay_snapshots(
        self,
        entry: Any,
    ) -> tuple[WorkspaceSnapshot, WorkspaceSnapshot] | None:
        before_snapshot = getattr(entry, "before", None)
        after_snapshot = getattr(entry, "after", None)
        if not isinstance(before_snapshot, WorkspaceSnapshot) or not isinstance(after_snapshot, WorkspaceSnapshot):
            return None
        workspace = self.workspace_or_none()
        if workspace is None:
            return None
        if self._workspace_matches_snapshot(workspace, before_snapshot):
            return after_snapshot, before_snapshot
        if self._workspace_matches_snapshot(workspace, after_snapshot):
            return before_snapshot, after_snapshot
        return None

    @staticmethod
    def _workspace_matches_snapshot(workspace: WorkspaceData, snapshot: WorkspaceSnapshot) -> bool:
        return (
            workspace.nodes == snapshot.nodes
            and workspace.edges == snapshot.edges
            and workspace.views == snapshot.views
            and workspace.active_view_id == snapshot.active_view_id
        )

    @staticmethod
    def _history_replay_metadata_is_stable(
        source_snapshot: WorkspaceSnapshot,
        target_snapshot: WorkspaceSnapshot,
    ) -> bool:
        return (
            source_snapshot.name == target_snapshot.name
            and source_snapshot.views == target_snapshot.views
            and source_snapshot.active_view_id == target_snapshot.active_view_id
            and source_snapshot.extra_state == target_snapshot.extra_state
        )

    @staticmethod
    def _node_diff_is_position_only(source_node: NodeInstance, target_node: NodeInstance) -> bool:
        candidate = source_node.clone()
        candidate.x = float(target_node.x)
        candidate.y = float(target_node.y)
        return candidate == target_node

    def _publish_history_node_position_delta(
        self,
        source_snapshot: WorkspaceSnapshot,
        target_snapshot: WorkspaceSnapshot,
    ) -> bool:
        if source_snapshot.edges != target_snapshot.edges:
            return False
        if set(source_snapshot.nodes) != set(target_snapshot.nodes):
            return False
        moved_node_ids = {
            node_id
            for node_id in source_snapshot.nodes
            if source_snapshot.nodes[node_id] != target_snapshot.nodes[node_id]
        }
        if not moved_node_ids:
            return False
        for node_id in moved_node_ids:
            if not self._node_diff_is_position_only(source_snapshot.nodes[node_id], target_snapshot.nodes[node_id]):
                return False
        return self.publish_node_position_delta(
            moved_node_ids,
            publication_path="history_node_position_delta",
        )

    def _publish_history_edge_topology_delta(
        self,
        source_snapshot: WorkspaceSnapshot,
        target_snapshot: WorkspaceSnapshot,
    ) -> bool:
        source_node_ids = set(source_snapshot.nodes)
        target_node_ids = set(target_snapshot.nodes)
        added_node_ids = target_node_ids - source_node_ids
        removed_node_ids = source_node_ids - target_node_ids
        common_node_ids = source_node_ids & target_node_ids
        if added_node_ids:
            return False
        if any(source_snapshot.nodes[node_id] != target_snapshot.nodes[node_id] for node_id in common_node_ids):
            return False
        if removed_node_ids and set(self.scope_path) & removed_node_ids:
            return False

        source_edge_ids = set(source_snapshot.edges)
        target_edge_ids = set(target_snapshot.edges)
        added_edge_ids = target_edge_ids - source_edge_ids
        removed_edge_ids = source_edge_ids - target_edge_ids
        updated_edge_ids = {
            edge_id
            for edge_id in source_edge_ids & target_edge_ids
            if source_snapshot.edges[edge_id] != target_snapshot.edges[edge_id]
        }
        if not (added_edge_ids or removed_edge_ids or updated_edge_ids or removed_node_ids):
            return False

        if removed_node_ids:
            for edge_id in added_edge_ids | updated_edge_ids:
                edge = target_snapshot.edges.get(edge_id)
                if edge is not None and (
                    edge.source_node_id in removed_node_ids or edge.target_node_id in removed_node_ids
                ):
                    return False
            for edge_id in removed_edge_ids:
                edge = source_snapshot.edges.get(edge_id)
                if edge is None:
                    return False
                if edge.source_node_id not in removed_node_ids and edge.target_node_id not in removed_node_ids:
                    return False

        changed_edges = [
            edge
            for edge_id in added_edge_ids | updated_edge_ids
            if (edge := target_snapshot.edges.get(edge_id)) is not None
        ]
        removed_edges = [
            edge
            for edge_id in removed_edge_ids
            if (edge := source_snapshot.edges.get(edge_id)) is not None
        ]
        dirty_node_ids = self.endpoint_node_ids_for_edges(changed_edges + removed_edges) | removed_node_ids
        related_updated_edge_ids = self.related_edge_ids_for_edges(changed_edges + removed_edges)
        return self.publish_edge_topology_delta(
            added_edge_ids=added_edge_ids,
            updated_edge_ids=updated_edge_ids | related_updated_edge_ids,
            removed_edge_ids=removed_edge_ids,
            dirty_node_ids=dirty_node_ids,
            removed_node_ids=removed_node_ids,
            publication_path="history_edge_topology_delta",
        )

    def active_graph_theme(self) -> GraphThemeDefinition:
        return self._payload_builder.active_graph_theme(self.graph_theme_bridge)

    def _validated_comment_peek_node_id(self) -> str:
        scope_selection = getattr(self._bridge, "_scope_selection", None)
        if scope_selection is None:
            return ""
        validator = getattr(scope_selection, "validated_comment_peek_node_id", None)
        if not callable(validator):
            return ""
        return str(validator() or "")

    def capture_history_snapshot(self) -> WorkspaceSnapshot | None:
        workspace = self.workspace_or_none()
        if self.history is None or workspace is None:
            return None
        start = time.perf_counter()
        try:
            return self.history.capture_workspace(workspace)
        finally:
            if self.mutation_timing_enabled():
                self.record_mutation_timing_phase("history_capture_ms", (time.perf_counter() - start) * 1000.0)

    def _invalidate_solution_for_history_action(
        self,
        workspace_id: str,
        action_type: str,
        *,
        before_snapshot: WorkspaceSnapshot | None,
        after_snapshot: WorkspaceSnapshot | None,
    ) -> None:
        host = self._bridge.parent()
        hook = getattr(host, "invalidate_solution_for_history_action", None)
        if not callable(hook):
            return
        hook(
            workspace_id,
            action_type,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )

    def record_history(self, action_type: str, before_snapshot: WorkspaceSnapshot | None) -> None:
        workspace = self.workspace_or_none()
        if self.history is None or workspace is None or before_snapshot is None:
            return
        after_snapshot_start = time.perf_counter()
        after_snapshot = self.history.capture_workspace(workspace)
        if self.mutation_timing_enabled():
            self.record_mutation_timing_phase(
                "history_capture_ms",
                (time.perf_counter() - after_snapshot_start) * 1000.0,
            )
        start = time.perf_counter()
        try:
            entry = self.history.record_action_from_snapshots(
                self.workspace_id,
                action_type,
                before_snapshot,
                after_snapshot,
            )
            if entry is None:
                return
            self._invalidate_solution_for_history_action(
                self.workspace_id,
                action_type,
                before_snapshot=entry.before,
                after_snapshot=entry.after,
            )
        finally:
            if self.mutation_timing_enabled():
                self.record_mutation_timing_phase("history_apply_ms", (time.perf_counter() - start) * 1000.0)

    @contextmanager
    def grouped_history_action(
        self,
        action_type: str,
        workspace: WorkspaceData,
        *,
        commit_if: Callable[[], bool] | None = None,
    ):
        if self.history is None or not self.workspace_id:
            with nullcontext():
                yield
            return
        capture_start = time.perf_counter()
        before_snapshot = self.history.capture_workspace(workspace)
        if self.mutation_timing_enabled():
            self.record_mutation_timing_phase("history_capture_ms", (time.perf_counter() - capture_start) * 1000.0)
        skip_history_commit = False
        try:
            yield
        except BaseException:
            raise
        else:
            skip_history_commit = commit_if is not None and not commit_if()
        finally:
            if skip_history_commit:
                return
            after_capture_start = time.perf_counter()
            after_snapshot = self.history.capture_workspace(workspace)
            if self.mutation_timing_enabled():
                self.record_mutation_timing_phase(
                    "history_capture_ms",
                    (time.perf_counter() - after_capture_start) * 1000.0,
                )
            apply_start = time.perf_counter()
            try:
                entry = self.history.record_action_from_snapshots(
                    self.workspace_id,
                    action_type,
                    before_snapshot,
                    after_snapshot,
                )
                if entry is not None:
                    self._invalidate_solution_for_history_action(
                        self.workspace_id,
                        action_type,
                        before_snapshot=entry.before,
                        after_snapshot=entry.after,
                    )
            finally:
                if self.mutation_timing_enabled():
                    self.record_mutation_timing_phase("history_apply_ms", (time.perf_counter() - apply_start) * 1000.0)

    def emit_workspace_changed(self) -> None:
        self._bridge.workspace_changed.emit(self.workspace_id)

    def emit_scope_changed(self) -> None:
        self._bridge.scope_changed.emit()

    def emit_selection_changed(self, node_id: str) -> None:
        self._bridge.selection_changed.emit()
        self._bridge.node_selected.emit(node_id)

    def emit_node_selected(self, node_id: str) -> None:
        self._bridge.node_selected.emit(node_id)

    @staticmethod
    def surface_title_sync_enabled(spec: NodeTypeSpec) -> bool:
        return _surface_title_sync_enabled(spec)

    @staticmethod
    def synced_surface_title(node: NodeInstance, spec: NodeTypeSpec) -> str:
        return _synced_surface_title(node, spec)

    @staticmethod
    def sync_surface_title(node: NodeInstance, spec: NodeTypeSpec) -> None:
        _sync_surface_title(node, spec)


__all__ = ["_GraphSceneContext"]
