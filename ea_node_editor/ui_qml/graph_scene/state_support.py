from __future__ import annotations

from bisect import bisect_left
from contextlib import contextmanager
from dataclasses import dataclass, field
import json
import time
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, QPointF, QRectF, pyqtProperty, pyqtSignal, pyqtSlot

from ea_node_editor.app_preferences import (
    effective_graph_node_icon_pixel_size,
    normalize_graph_label_pixel_size,
)
from ea_node_editor.graph.hierarchy import ScopePath, scope_breadcrumb_payload
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.settings import DEFAULT_GRAPH_LABEL_PIXEL_SIZE
from ea_node_editor.ui.shell.runtime_history import history_entry_title_only_node_id
from ea_node_editor.ui_qml.graph_scene.command_bridge import GraphSceneCommandBridge
from ea_node_editor.ui_qml.graph_scene.policy_bridge import GraphScenePolicyBridge
from ea_node_editor.ui_qml.graph_scene.read_bridge import GraphSceneReadBridge

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
    from ea_node_editor.ui_qml.graph_scene_scope_selection import (
        _NodeItemProxy,
        _SelectedNodeProxy,
    )
    from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge

_SNAP_GRID_SIZE = 20.0
_MUTATION_TIMING_PHASE_KEYS = (
    "command_dispatch_ms",
    "history_capture_ms",
    "history_apply_ms",
    "graph_model_mutation_ms",
    "payload_rebuild_ms",
    "scene_publish_ms",
    "visible_node_model_update_ms",
    "edge_payload_update_ms",
    "render_callback_wait_ms",
    "readback_grab_ms",
    "post_readback_event_drain_ms",
    "first_frame_after_mutation_ms",
)
_EDGE_STRUCTURAL_DELTA_SCHEMA = "graph_scene_edge_structural_delta"
_EDGE_STRUCTURAL_DELTA_VERSION = 1


def _mutation_phase_timings_payload() -> dict[str, float]:
    return {key: 0.0 for key in _MUTATION_TIMING_PHASE_KEYS}


def _payload_size_bytes(value: Any) -> int:
    try:
        encoded = json.dumps(
            value, default=str, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError):
        return 0
    return len(encoded)


def _copy_mutation_timing_record(record: dict[str, Any]) -> dict[str, Any]:
    copied = dict(record)
    copied["phase_timings_ms"] = dict(record.get("phase_timings_ms", {}))
    graph_size = record.get("graph_size", {})
    copied["graph_size"] = dict(graph_size) if isinstance(graph_size, dict) else {}
    samples = record.get("mutation_wall_clock_samples_ms", [])
    copied["mutation_wall_clock_samples_ms"] = (
        list(samples) if isinstance(samples, list) else []
    )
    publication_paths = record.get("scene_publication_paths", [])
    copied["scene_publication_paths"] = (
        list(publication_paths) if isinstance(publication_paths, list) else []
    )
    counters = record.get("mutation_counters", {})
    copied["mutation_counters"] = dict(counters) if isinstance(counters, dict) else {}
    counter_reasons = record.get("mutation_counter_reasons", {})
    copied["mutation_counter_reasons"] = (
        {
            str(counter): dict(reasons)
            for counter, reasons in counter_reasons.items()
            if isinstance(reasons, dict)
        }
        if isinstance(counter_reasons, dict)
        else {}
    )
    return copied


@dataclass
class _GraphScenePayloadCache:
    nodes: list[dict[str, Any]] = field(default_factory=list)
    backdrop_nodes: list[dict[str, Any]] = field(default_factory=list)
    minimap_nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    edge_delta_payload: dict[str, Any] = field(default_factory=dict)
    edge_delta_sequence: int = 0
    dirty: bool = True
    active_view_id: str = ""
    hide_optional_ports: bool = False
    comment_peek_node_id: str = ""
    node_payload_location_by_id: dict[str, tuple[str, int]] = field(
        default_factory=dict
    )
    minimap_node_index_by_id: dict[str, int] = field(default_factory=dict)
    edge_payload_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    edge_index_by_id: dict[str, int] = field(default_factory=dict)
    edge_order: list[str] = field(default_factory=list)
    incident_edge_ids_by_node_id: dict[str, set[str]] = field(default_factory=dict)
    edge_ids_by_pair: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    edge_ids_by_source_port: dict[tuple[str, str], set[str]] = field(
        default_factory=dict
    )
    edge_ids_by_target_port: dict[tuple[str, str], set[str]] = field(
        default_factory=dict
    )
    indexes_valid: bool = False
    rebuild_index_call_count: int = 0
    edge_only_reindex_call_count: int = 0
    slot_identity_mismatch_count: int = 0

    def update(
        self,
        *,
        nodes: list[dict[str, Any]],
        backdrop_nodes: list[dict[str, Any]],
        minimap_nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        active_view_id: str | None = None,
        hide_optional_ports: bool | None = None,
        comment_peek_node_id: str | None = None,
    ) -> None:
        self.nodes = nodes
        self.backdrop_nodes = backdrop_nodes
        self.minimap_nodes = minimap_nodes
        self.edges = edges
        self.edge_delta_payload = {}
        self.dirty = False
        self.rebuild_indexes()
        if active_view_id is not None:
            self.active_view_id = str(active_view_id or "")
        if hide_optional_ports is not None:
            self.hide_optional_ports = bool(hide_optional_ports)
        if comment_peek_node_id is not None:
            self.comment_peek_node_id = str(comment_peek_node_id or "")

    def set_active_view_filters(
        self,
        *,
        active_view_id: str,
        hide_optional_ports: bool,
    ) -> None:
        self.active_view_id = str(active_view_id or "")
        self.hide_optional_ports = bool(hide_optional_ports)

    def mark_dirty(self) -> None:
        self.nodes = []
        self.backdrop_nodes = []
        self.minimap_nodes = []
        self.edges = []
        self.edge_delta_payload = {}
        self.clear_indexes()
        self.dirty = True

    def clear_indexes(self) -> None:
        self.node_payload_location_by_id = {}
        self.minimap_node_index_by_id = {}
        self.edge_payload_by_id = {}
        self.edge_index_by_id = {}
        self.edge_order = []
        self.incident_edge_ids_by_node_id = {}
        self.edge_ids_by_pair = {}
        self.edge_ids_by_source_port = {}
        self.edge_ids_by_target_port = {}
        self.indexes_valid = False

    def rebuild_indexes(self) -> None:
        self.rebuild_index_call_count += 1
        self.node_payload_location_by_id = {}
        for collection_name, payloads in (
            ("nodes", self.nodes),
            ("backdrop_nodes", self.backdrop_nodes),
        ):
            for index, payload in enumerate(payloads):
                node_id = str(payload.get("node_id", "") or "").strip()
                if node_id:
                    self.node_payload_location_by_id[node_id] = (collection_name, index)

        self.minimap_node_index_by_id = {}
        for index, payload in enumerate(self.minimap_nodes):
            node_id = str(payload.get("node_id", "") or "").strip()
            if node_id:
                self.minimap_node_index_by_id[node_id] = index

        self._rebuild_edge_indexes()
        self.indexes_valid = True

    def reindex_edges_only(self) -> None:
        self.edge_only_reindex_call_count += 1
        self._rebuild_edge_indexes()
        self.indexes_valid = True

    def _edge_slots_are_canonical(self) -> bool:
        if not self.indexes_valid:
            return False
        edge_count = len(self.edges)
        if not (
            len(self.edge_order) == edge_count
            and len(self.edge_payload_by_id) == edge_count
            and len(self.edge_index_by_id) == edge_count
        ):
            return False
        previous_edge_id = ""
        for index, payload in enumerate(self.edges):
            edge_id = str(payload.get("edge_id", "") or "").strip()
            if not edge_id or (previous_edge_id and edge_id <= previous_edge_id):
                return False
            if self.edge_order[index] != edge_id:
                return False
            if self.edge_index_by_id.get(edge_id) != index:
                return False
            if self.edge_payload_by_id.get(edge_id) is not payload:
                return False
            previous_edge_id = edge_id
        return True

    def _insert_edge_payload(self, payload: dict[str, Any]) -> bool:
        edge_id = str(payload.get("edge_id", "") or "").strip()
        if (
            not edge_id
            or edge_id in self.edge_payload_by_id
            or not self._edge_slots_are_canonical()
        ):
            return False
        index = bisect_left(self.edge_order, edge_id)
        self.edges.insert(index, payload)
        self.edge_order.insert(index, edge_id)
        self.edge_payload_by_id[edge_id] = payload
        for shifted_index in range(index, len(self.edge_order)):
            self.edge_index_by_id[self.edge_order[shifted_index]] = shifted_index
        self._add_edge_routing_indexes(payload)
        return True

    def _remove_edge_payload(self, edge_id: str) -> bool:
        normalized_edge_id = str(edge_id or "").strip()
        if not normalized_edge_id or not self._edge_slots_are_canonical():
            return False
        index = self.edge_index_by_id.get(normalized_edge_id)
        if index is None:
            return False
        payload = self.edges[index]
        self.edges.pop(index)
        self.edge_order.pop(index)
        self.edge_payload_by_id.pop(normalized_edge_id, None)
        self.edge_index_by_id.pop(normalized_edge_id, None)
        for shifted_index in range(index, len(self.edge_order)):
            self.edge_index_by_id[self.edge_order[shifted_index]] = shifted_index
        self._remove_edge_routing_indexes(payload)
        return True

    def _add_edge_routing_indexes(self, payload: dict[str, Any]) -> None:
        edge_id = str(payload.get("edge_id", "") or "").strip()
        source_node_id = str(payload.get("source_node_id", "") or "").strip()
        target_node_id = str(payload.get("target_node_id", "") or "").strip()
        source_port_key = str(payload.get("source_port_key", "") or "").strip()
        target_port_key = str(payload.get("target_port_key", "") or "").strip()
        for node_id in (source_node_id, target_node_id):
            if node_id:
                self.incident_edge_ids_by_node_id.setdefault(node_id, set()).add(
                    edge_id
                )
        if source_node_id and target_node_id:
            self.edge_ids_by_pair.setdefault(
                (source_node_id, target_node_id), set()
            ).add(edge_id)
        if source_node_id and source_port_key:
            self.edge_ids_by_source_port.setdefault(
                (source_node_id, source_port_key), set()
            ).add(edge_id)
        if target_node_id and target_port_key:
            self.edge_ids_by_target_port.setdefault(
                (target_node_id, target_port_key), set()
            ).add(edge_id)

    def _remove_edge_routing_indexes(self, payload: dict[str, Any]) -> None:
        edge_id = str(payload.get("edge_id", "") or "").strip()
        source_node_id = str(payload.get("source_node_id", "") or "").strip()
        target_node_id = str(payload.get("target_node_id", "") or "").strip()
        source_port_key = str(payload.get("source_port_key", "") or "").strip()
        target_port_key = str(payload.get("target_port_key", "") or "").strip()
        keys_by_index = (
            (self.incident_edge_ids_by_node_id, source_node_id),
            (self.incident_edge_ids_by_node_id, target_node_id),
            (self.edge_ids_by_pair, (source_node_id, target_node_id)),
            (self.edge_ids_by_source_port, (source_node_id, source_port_key)),
            (self.edge_ids_by_target_port, (target_node_id, target_port_key)),
        )
        for edge_index, key in keys_by_index:
            if not key or (isinstance(key, tuple) and not all(key)):
                continue
            indexed_edge_ids = edge_index.get(key)
            if indexed_edge_ids is None:
                continue
            indexed_edge_ids.discard(edge_id)
            if not indexed_edge_ids:
                edge_index.pop(key, None)

    def resolve_node_payload_slot(
        self, node_id: str
    ) -> tuple[str, tuple[str, int] | None]:
        """Resolve ``node_id`` through the location index, verifying the slot
        still holds that node's payload.

        Returns ``("ok", location)``, ``("absent", None)``, or
        ``("mismatch", None)``. A mismatch means the index is stale relative
        to the payload collections — the duplicate/phantom-node corruption
        signature — so callers must fall back to a full rebuild instead of
        clobbering another node's slot with a keyed write.
        """
        location = self.node_payload_location_by_id.get(node_id)
        if location is None:
            return "absent", None
        collection_name, index = location
        collection = self.nodes if collection_name == "nodes" else self.backdrop_nodes
        if 0 <= index < len(collection):
            payload = collection[index]
            payload_node_id = (
                str(payload.get("node_id", "") or "").strip()
                if isinstance(payload, dict)
                else ""
            )
            if payload_node_id == node_id:
                return "ok", location
        self.slot_identity_mismatch_count += 1
        return "mismatch", None

    def resolve_minimap_payload_slot(self, node_id: str) -> tuple[str, int | None]:
        """Minimap counterpart of :meth:`resolve_node_payload_slot`."""
        index = self.minimap_node_index_by_id.get(node_id)
        if index is None:
            return "absent", None
        if 0 <= index < len(self.minimap_nodes):
            payload = self.minimap_nodes[index]
            payload_node_id = (
                str(payload.get("node_id", "") or "").strip()
                if isinstance(payload, dict)
                else ""
            )
            if payload_node_id == node_id:
                return "ok", index
        self.slot_identity_mismatch_count += 1
        return "mismatch", None

    def port_connection_counts_for_nodes(
        self, node_ids: set[str]
    ) -> dict[tuple[str, str], int]:
        requested_node_ids = {
            node_id for value in node_ids if (node_id := str(value or "").strip())
        }
        if not requested_node_ids:
            return {}
        if not self.indexes_valid:
            self.rebuild_indexes()
        counts: dict[tuple[str, str], int] = {}
        for node_id in sorted(requested_node_ids):
            for edge_id in self.incident_edge_ids_by_node_id.get(node_id, set()):
                edge_payload = self.edge_payload_by_id.get(edge_id)
                if edge_payload is None:
                    continue
                source_node_id = str(
                    edge_payload.get("source_node_id", "") or ""
                ).strip()
                if source_node_id == node_id:
                    source_port_key = str(
                        edge_payload.get("source_port_key", "") or ""
                    ).strip()
                    if source_port_key:
                        key = (node_id, source_port_key)
                        counts[key] = counts.get(key, 0) + 1
                target_node_id = str(
                    edge_payload.get("target_node_id", "") or ""
                ).strip()
                if target_node_id == node_id:
                    target_port_key = str(
                        edge_payload.get("target_port_key", "") or ""
                    ).strip()
                    if target_port_key:
                        key = (node_id, target_port_key)
                        counts[key] = counts.get(key, 0) + 1
        return counts

    def _rebuild_edge_indexes(self) -> None:
        self.edge_payload_by_id = {}
        self.edge_index_by_id = {}
        self.edge_order = []
        self.incident_edge_ids_by_node_id = {}
        self.edge_ids_by_pair = {}
        self.edge_ids_by_source_port = {}
        self.edge_ids_by_target_port = {}
        for index, payload in enumerate(self.edges):
            edge_id = str(payload.get("edge_id", "") or "").strip()
            if not edge_id:
                continue
            source_node_id = str(payload.get("source_node_id", "") or "").strip()
            target_node_id = str(payload.get("target_node_id", "") or "").strip()
            source_port_key = str(payload.get("source_port_key", "") or "").strip()
            target_port_key = str(payload.get("target_port_key", "") or "").strip()
            self.edge_payload_by_id[edge_id] = payload
            self.edge_index_by_id[edge_id] = index
            self.edge_order.append(edge_id)
            for node_id in (source_node_id, target_node_id):
                if node_id:
                    self.incident_edge_ids_by_node_id.setdefault(node_id, set()).add(
                        edge_id
                    )
            if source_node_id and target_node_id:
                self.edge_ids_by_pair.setdefault(
                    (source_node_id, target_node_id), set()
                ).add(edge_id)
            if source_node_id and source_port_key:
                self.edge_ids_by_source_port.setdefault(
                    (source_node_id, source_port_key), set()
                ).add(edge_id)
            if target_node_id and target_port_key:
                self.edge_ids_by_target_port.setdefault(
                    (target_node_id, target_port_key), set()
                ).add(edge_id)

    def next_edge_delta_sequence(self) -> int:
        self.edge_delta_sequence += 1
        return self.edge_delta_sequence

    def edge_delta_base_payload(
        self,
        *,
        reason: str,
        requires_full_refresh: bool,
        edge_count_after: int,
    ) -> dict[str, Any]:
        return {
            "schema": _EDGE_STRUCTURAL_DELTA_SCHEMA,
            "version": _EDGE_STRUCTURAL_DELTA_VERSION,
            "sequence": self.next_edge_delta_sequence(),
            "reason": str(reason or "").strip(),
            "requires_full_refresh": bool(requires_full_refresh),
            "edge_count_after": max(0, int(edge_count_after)),
            "added_edge_ids": [],
            "updated_edge_ids": [],
            "removed_edge_ids": [],
            "dirty_edge_ids": [],
            "dirty_node_ids": [],
            "removed_node_ids": [],
            "affected_node_ids": [],
            "added_edges": [],
            "updated_edges": [],
            "removed_edges": [],
        }


class _GraphScenePendingSurfaceAction:
    def __init__(self) -> None:
        self.node_id = ""

    def set(self, node_id: str) -> bool:
        normalized = str(node_id or "")
        if self.node_id == normalized:
            return False
        self.node_id = normalized
        return True

    def consume(self, node_id: str) -> bool:
        normalized = str(node_id or "")
        if not normalized or self.node_id != normalized:
            return False
        self.node_id = ""
        return True


class GraphSceneBridgeBase(QObject):
    node_selected = pyqtSignal(str)
    workspace_changed = pyqtSignal(str)
    scope_changed = pyqtSignal()
    nodes_changed = pyqtSignal()
    edges_changed = pyqtSignal()
    selection_changed = pyqtSignal()
    interact_with_locked_objects_changed = pyqtSignal()
    pending_surface_action_changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._graphics_preferences_source: object | None = None
        self._scene_payload_graphics_preferences: tuple[bool, int, int, bool, bool] | None = None
        self._mutation_timing_enabled = False
        self._mutation_timing_records: list[dict[str, Any]] = []
        self._active_mutation_timing_record: dict[str, Any] | None = None
        self._active_mutation_timing_started_at = 0.0

    def _mutation_cache_counter_payload(self) -> dict[str, int]:
        cache = getattr(self, "_payload_cache", None)
        if cache is None:
            return {
                "payload_cache_rebuild_indexes": 0,
                "payload_cache_edge_only_reindexes": 0,
                "payload_cache_slot_identity_mismatches": 0,
            }
        return {
            "payload_cache_rebuild_indexes": max(
                0, int(getattr(cache, "rebuild_index_call_count", 0))
            ),
            "payload_cache_edge_only_reindexes": max(
                0, int(getattr(cache, "edge_only_reindex_call_count", 0))
            ),
            "payload_cache_slot_identity_mismatches": max(
                0, int(getattr(cache, "slot_identity_mismatch_count", 0))
            ),
        }

    def bind_graphics_preferences_source(self, source: object | None) -> bool:
        if source is not None:
            signal = getattr(source, "graphics_preferences_changed", None)
            if not callable(getattr(signal, "connect", None)) or not callable(
                getattr(signal, "disconnect", None)
            ):
                raise TypeError(
                    "graphics preferences source must expose graphics_preferences_changed"
                )
        if self._graphics_preferences_source is source:
            return False
        previous_source = self._graphics_preferences_source
        if previous_source is not None:
            try:
                previous_source.graphics_preferences_changed.disconnect(
                    self._on_graphics_preferences_changed
                )
            except (AttributeError, RuntimeError, TypeError):
                pass
        self._graphics_preferences_source = source
        if source is not None:
            source.graphics_preferences_changed.connect(
                self._on_graphics_preferences_changed
            )
        current_preferences = self._current_scene_payload_graphics_preferences()
        changed = self._scene_payload_graphics_preferences != current_preferences
        self._scene_payload_graphics_preferences = current_preferences
        if changed and getattr(self, "_model", None) is not None:
            self._scene_context.rebuild_models()
        return True

    def _current_scene_payload_graphics_preferences(self) -> tuple[bool, int, int, bool, bool]:
        source = self._graphics_preferences_source
        if source is None:
            return (
                True,
                DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
                effective_graph_node_icon_pixel_size(
                    DEFAULT_GRAPH_LABEL_PIXEL_SIZE, None
                ),
                False,
                False,
            )
        graph_label_pixel_size = normalize_graph_label_pixel_size(
            getattr(
                source,
                "graphics_graph_label_pixel_size",
                DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
            )
        )
        node_icon_pixel_size = getattr(
            source, "graphics_node_title_icon_pixel_size", None
        )
        if node_icon_pixel_size is None or isinstance(node_icon_pixel_size, bool):
            node_icon_pixel_size = effective_graph_node_icon_pixel_size(
                graph_label_pixel_size,
                getattr(source, "graphics_graph_node_icon_pixel_size_override", None),
            )
        else:
            try:
                node_icon_pixel_size = int(node_icon_pixel_size)
            except (TypeError, ValueError):
                node_icon_pixel_size = effective_graph_node_icon_pixel_size(
                    graph_label_pixel_size,
                    getattr(
                        source, "graphics_graph_node_icon_pixel_size_override", None
                    ),
                )
        return (
            bool(getattr(source, "graphics_show_port_labels", True)),
            graph_label_pixel_size,
            int(node_icon_pixel_size),
            bool(getattr(source, "graphics_lightweight_canvas", False)),
            bool(getattr(source, "graphics_keep_expanded_node_width", False)),
        )

    def _remember_scene_payload_graphics_preferences(self) -> None:
        self._scene_payload_graphics_preferences = (
            self._current_scene_payload_graphics_preferences()
        )

    def _effective_scene_payload_graphics_preferences(
        self,
    ) -> tuple[bool, int, int, bool, bool]:
        if self._scene_payload_graphics_preferences is None:
            self._remember_scene_payload_graphics_preferences()
        assert self._scene_payload_graphics_preferences is not None
        return self._scene_payload_graphics_preferences

    def _active_view_filter_state(self) -> tuple[str, bool]:
        workspace = self._workspace_or_none()
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

    def _ensure_payload_cache_current(self) -> None:
        active_view_id, hide_optional_ports = (
            self._active_view_filter_state()
        )
        comment_peek_node_id = self._scope_selection.validated_comment_peek_node_id()
        if (
            not self._payload_cache.dirty
            and self._payload_cache.active_view_id == active_view_id
            and self._payload_cache.hide_optional_ports == hide_optional_ports
            and self._payload_cache.comment_peek_node_id == comment_peek_node_id
        ):
            return
        (
            nodes_payload,
            backdrop_nodes_payload,
            minimap_nodes_payload,
            edges_payload,
        ) = self._scene_context._payload_builder.rebuild_partitioned_models(
            model=self._scene_context.model,
            registry=self._scene_context.registry,
            workspace_id=self._scene_context.workspace_id,
            scope_path=self._scene_context.scope_path,
            comment_peek_node_id=comment_peek_node_id,
            graph_theme_bridge=self._scene_context.graph_theme_bridge,
            show_port_labels=self._scene_context.graphics_show_port_labels,
            graph_label_pixel_size=self._scene_context.graphics_graph_label_pixel_size,
            graph_node_icon_pixel_size=self._scene_context.graphics_node_title_icon_pixel_size,
            lightweight_canvas=self._scene_context.graphics_lightweight_canvas,
        )
        self._payload_cache.update(
            nodes=nodes_payload,
            backdrop_nodes=backdrop_nodes_payload,
            minimap_nodes=minimap_nodes_payload,
            edges=edges_payload,
            active_view_id=active_view_id,
            hide_optional_ports=hide_optional_ports,
            comment_peek_node_id=comment_peek_node_id,
        )

    @property
    def graphics_show_port_labels(self) -> bool:
        return self._effective_scene_payload_graphics_preferences()[0]

    @property
    def graphics_graph_label_pixel_size(self) -> int:
        return self._effective_scene_payload_graphics_preferences()[1]

    @property
    def graphics_node_title_icon_pixel_size(self) -> int:
        return self._effective_scene_payload_graphics_preferences()[2]

    @property
    def graphics_lightweight_canvas(self) -> bool:
        return self._effective_scene_payload_graphics_preferences()[3]

    @property
    def graphics_keep_expanded_node_width(self) -> bool:
        return self._effective_scene_payload_graphics_preferences()[4]

    @property
    def _workspace_id(self) -> str:
        return self._scope_selection.workspace_id

    @_workspace_id.setter
    def _workspace_id(self, value: str) -> None:
        self._scope_selection.workspace_id = str(value or "")

    @property
    def _scope_path(self) -> ScopePath:
        return self._scope_selection.scope_path

    @_scope_path.setter
    def _scope_path(self, value: ScopePath) -> None:
        self._scope_selection.scope_path = tuple(
            str(node_id) for node_id in tuple(value or ())
        )

    @property
    def _selected_node_ids(self) -> list[str]:
        return self._scope_selection.selected_node_ids

    @_selected_node_ids.setter
    def _selected_node_ids(self, value: list[str]) -> None:
        self._scope_selection.selected_node_ids = [
            str(node_id) for node_id in list(value or [])
        ]

    @property
    def _selected_node_lookup(self) -> dict[str, bool]:
        return self._scope_selection.selected_node_lookup

    @_selected_node_lookup.setter
    def _selected_node_lookup(self, value: dict[str, bool]) -> None:
        self._scope_selection.selected_node_lookup = {
            str(node_id): bool(selected)
            for node_id, selected in dict(value or {}).items()
        }

    @property
    def workspace_id(self) -> str:
        return self._workspace_id

    @property
    def state_bridge(self) -> GraphSceneReadBridge:
        return self._state_bridge

    @property
    def command_bridge(self) -> GraphSceneCommandBridge:
        return self._command_bridge

    @property
    def policy_bridge(self) -> GraphScenePolicyBridge:
        return self._policy_bridge

    @pyqtProperty("QVariantList", notify=nodes_changed)
    def nodes_model(self) -> list[dict[str, Any]]:
        self._ensure_payload_cache_current()
        return self._payload_cache.nodes

    @pyqtProperty("QVariantList", notify=nodes_changed)
    def backdrop_nodes_model(self) -> list[dict[str, Any]]:
        self._ensure_payload_cache_current()
        return self._payload_cache.backdrop_nodes

    @pyqtProperty("QVariantList", notify=edges_changed)
    def edges_model(self) -> list[dict[str, Any]]:
        self._ensure_payload_cache_current()
        return self._payload_cache.edges

    @pyqtProperty("QVariantMap", notify=edges_changed)
    def edge_delta_payload(self) -> dict[str, Any]:
        return self._payload_cache.edge_delta_payload

    @pyqtProperty(str, notify=pending_surface_action_changed)
    def pending_surface_action_node_id(self) -> str:
        return self._command_bridge.pending_surface_action_node_id

    @pyqtSlot(str)
    def set_pending_surface_action(self, node_id: str) -> None:
        self._command_bridge.set_pending_surface_action(node_id)

    @pyqtSlot(str, result=bool)
    def consume_pending_surface_action(self, node_id: str) -> bool:
        return self._command_bridge.consume_pending_surface_action(node_id)

    @pyqtProperty("QVariantList", notify=nodes_changed)
    def minimap_nodes_model(self) -> list[dict[str, Any]]:
        self._ensure_payload_cache_current()
        return self._payload_cache.minimap_nodes

    @pyqtProperty("QVariantMap", notify=nodes_changed)
    def workspace_scene_bounds_payload(self) -> dict[str, float]:
        return self._rect_payload(self.workspace_scene_bounds_with_fallback())

    @pyqtProperty(str, notify=node_selected)
    def selected_node_id_value(self) -> str:
        selected = self.selected_node_id()
        return selected or ""

    @pyqtProperty("QVariantMap", notify=selection_changed)
    def selected_node_lookup(self) -> dict[str, bool]:
        return self._selected_node_lookup

    @pyqtProperty("QVariantList", notify=selection_changed)
    def selected_node_ids(self) -> list[str]:
        return list(self._selected_node_ids)

    @pyqtProperty(bool, notify=interact_with_locked_objects_changed)
    def interact_with_locked_objects(self) -> bool:
        return self._scope_selection.interact_with_locked_objects

    @pyqtProperty("QVariantList", notify=scope_changed)
    def active_scope_path(self) -> list[str]:
        return list(self._scope_path)

    @pyqtProperty("QVariantList", notify=scope_changed)
    def scope_breadcrumb_model(self) -> list[dict[str, str]]:
        workspace = self._workspace_or_none()
        if workspace is None:
            return []
        return scope_breadcrumb_payload(workspace, self._scope_path)

    @pyqtProperty(bool, notify=scope_changed)
    def can_navigate_scope_parent(self) -> bool:
        return bool(self._scope_path)

    @pyqtProperty(str, notify=nodes_changed)
    def active_comment_peek_node_id(self) -> str:
        return self._scope_selection.validated_comment_peek_node_id()

    @pyqtProperty(bool, notify=nodes_changed)
    def comment_peek_active(self) -> bool:
        return bool(self.active_comment_peek_node_id)

    def _workspace_or_none(self) -> WorkspaceData | None:
        return self._scene_context.workspace_or_none()

    def mutation_timing_enabled(self) -> bool:
        return bool(self._mutation_timing_enabled)

    def mutation_timing_active(self) -> bool:
        return self._active_mutation_timing_record is not None

    @pyqtSlot(bool)
    def set_mutation_timing_enabled(self, enabled: bool) -> None:
        self._mutation_timing_enabled = bool(enabled)
        if not self._mutation_timing_enabled:
            self._active_mutation_timing_record = None
            self._active_mutation_timing_started_at = 0.0

    @pyqtSlot()
    def clear_mutation_timing_samples(self) -> None:
        self._mutation_timing_records.clear()

    def mutation_timing_samples(self) -> list[dict[str, Any]]:
        return [
            _copy_mutation_timing_record(record)
            for record in self._mutation_timing_records
        ]

    def _mutation_graph_size_payload(self) -> dict[str, int]:
        workspace = self._workspace_or_none()
        if workspace is None:
            return {"nodes": 0, "edges": 0}
        return {"nodes": len(workspace.nodes), "edges": len(workspace.edges)}

    def record_mutation_timing_phase(self, phase_name: str, elapsed_ms: float) -> None:
        record = self._active_mutation_timing_record
        if record is None:
            return
        phase_timings = record["phase_timings_ms"]
        key = str(phase_name or "").strip()
        if not key:
            return
        phase_timings[key] = max(
            0.0, float(phase_timings.get(key, 0.0)) + max(0.0, float(elapsed_ms))
        )

    def record_mutation_counter(
        self, counter_name: str, amount: int = 1, *, reason: str = ""
    ) -> None:
        record = self._active_mutation_timing_record
        if record is None:
            return
        key = str(counter_name or "").strip()
        if not key:
            return
        count = max(0, int(amount))
        if count <= 0:
            return
        counters = record.setdefault("mutation_counters", {})
        counters[key] = max(0, int(counters.get(key, 0))) + count
        normalized_reason = str(reason or "").strip()
        if normalized_reason:
            counter_reasons = record.setdefault("mutation_counter_reasons", {})
            reasons = counter_reasons.setdefault(key, {})
            reasons[normalized_reason] = (
                max(0, int(reasons.get(normalized_reason, 0))) + count
            )

    def record_mutation_payload_metrics(
        self,
        *,
        nodes_payload: list[dict[str, Any]] | None = None,
        backdrop_nodes_payload: list[dict[str, Any]] | None = None,
        minimap_nodes_payload: list[dict[str, Any]] | None = None,
        edges_payload: list[dict[str, Any]] | None = None,
        dirty_node_count: int | None = None,
        dirty_edge_count: int | None = None,
        model_delta_dirty_node_count: int | None = None,
        model_delta_dirty_edge_count: int | None = None,
        scene_publication_dirty_node_count: int | None = None,
        scene_publication_dirty_edge_count: int | None = None,
        scene_publication_path: str | None = None,
        graph_delta_payload: Any | None = None,
    ) -> None:
        record = self._active_mutation_timing_record
        if record is None:
            return
        nodes = list(nodes_payload or [])
        backdrops = list(backdrop_nodes_payload or [])
        minimap_nodes = list(minimap_nodes_payload or [])
        edges = list(edges_payload or [])
        if nodes or backdrops or minimap_nodes or edges:
            record["scene_payload_bytes"] = max(
                int(record.get("scene_payload_bytes", 0)),
                _payload_size_bytes(
                    {
                        "nodes": nodes,
                        "backdrop_nodes": backdrops,
                        "minimap_nodes": minimap_nodes,
                        "edges": edges,
                    }
                ),
            )
        if dirty_node_count is None and (nodes or backdrops):
            dirty_node_count = len(nodes) + len(backdrops)
        if dirty_edge_count is None and edges:
            dirty_edge_count = len(edges)
        if dirty_node_count is not None:
            record["dirty_node_count"] = max(
                int(record.get("dirty_node_count", 0)), max(0, int(dirty_node_count))
            )
        if dirty_edge_count is not None:
            record["dirty_edge_count"] = max(
                int(record.get("dirty_edge_count", 0)), max(0, int(dirty_edge_count))
            )
        if model_delta_dirty_node_count is not None:
            record["model_delta_dirty_node_count"] = max(
                int(record.get("model_delta_dirty_node_count", 0)),
                max(0, int(model_delta_dirty_node_count)),
            )
        if model_delta_dirty_edge_count is not None:
            record["model_delta_dirty_edge_count"] = max(
                int(record.get("model_delta_dirty_edge_count", 0)),
                max(0, int(model_delta_dirty_edge_count)),
            )
        if scene_publication_dirty_node_count is not None:
            record["scene_publication_dirty_node_count"] = max(
                int(record.get("scene_publication_dirty_node_count", 0)),
                max(0, int(scene_publication_dirty_node_count)),
            )
        if scene_publication_dirty_edge_count is not None:
            record["scene_publication_dirty_edge_count"] = max(
                int(record.get("scene_publication_dirty_edge_count", 0)),
                max(0, int(scene_publication_dirty_edge_count)),
            )
        normalized_publication_path = str(scene_publication_path or "").strip()
        if normalized_publication_path:
            paths = record.setdefault("scene_publication_paths", [])
            if normalized_publication_path not in paths:
                paths.append(normalized_publication_path)
        if graph_delta_payload is not None:
            record["graph_delta_payload_bytes"] = max(
                int(record.get("graph_delta_payload_bytes", 0)),
                _payload_size_bytes(graph_delta_payload),
            )
        record["graph_size"] = self._mutation_graph_size_payload()

    @contextmanager
    def mutation_timing_scope(
        self,
        scenario: str,
        *,
        command_payload: Any | None = None,
        fixture_checksum_sha256: str = "",
    ):
        if not self._mutation_timing_enabled:
            yield
            return
        previous_record = self._active_mutation_timing_record
        previous_start = self._active_mutation_timing_started_at
        record = {
            "scenario": str(scenario or "unspecified"),
            "operation_iteration": len(self._mutation_timing_records),
            "mutation_wall_clock_samples_ms": [],
            "phase_timings_ms": _mutation_phase_timings_payload(),
            "_cache_counter_baseline": self._mutation_cache_counter_payload(),
            "fixture_checksum_sha256": str(fixture_checksum_sha256 or ""),
            "graph_size": self._mutation_graph_size_payload(),
            "dirty_node_count": 0,
            "dirty_edge_count": 0,
            "model_delta_dirty_node_count": 0,
            "model_delta_dirty_edge_count": 0,
            "scene_publication_dirty_node_count": 0,
            "scene_publication_dirty_edge_count": 0,
            "scene_publication_paths": [],
            "mutation_counters": {},
            "mutation_counter_reasons": {},
            "command_payload_bytes": _payload_size_bytes(command_payload),
            "graph_delta_payload_bytes": 0,
            "scene_payload_bytes": 0,
            "first_frame_after_mutation_ms": 0.0,
        }
        self._active_mutation_timing_record = record
        self._active_mutation_timing_started_at = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = max(
                0.0,
                (time.perf_counter() - self._active_mutation_timing_started_at)
                * 1000.0,
            )
            record["mutation_wall_clock_samples_ms"] = [elapsed_ms]
            phase_timings = record["phase_timings_ms"]
            if float(phase_timings.get("first_frame_after_mutation_ms", 0.0)) <= 0.0:
                phase_timings["first_frame_after_mutation_ms"] = elapsed_ms
            record["first_frame_after_mutation_ms"] = max(
                0.0,
                float(phase_timings.get("first_frame_after_mutation_ms", 0.0)),
            )
            baseline = record.pop("_cache_counter_baseline", {})
            if isinstance(baseline, dict):
                for (
                    counter_name,
                    current_value,
                ) in self._mutation_cache_counter_payload().items():
                    delta = max(
                        0, int(current_value) - int(baseline.get(counter_name, 0))
                    )
                    if delta:
                        self.record_mutation_counter(counter_name, delta)
            record["graph_size"] = self._mutation_graph_size_payload()
            self._mutation_timing_records.append(_copy_mutation_timing_record(record))
            self._active_mutation_timing_record = previous_record
            self._active_mutation_timing_started_at = previous_start

    @pyqtSlot(result=bool)
    def sync_scope_with_active_view(self) -> bool:
        return self._scope_selection.sync_scope_with_active_view()

    @pyqtSlot(str, result=bool)
    def open_subnode_scope(self, node_id: str) -> bool:
        return self._scope_selection.open_subnode_scope(node_id)

    @pyqtSlot(str, result=bool)
    def can_open_comment_peek(self, node_id: str) -> bool:
        return self._scope_selection.can_open_comment_peek(node_id)

    @pyqtSlot(str, result=bool)
    def open_comment_peek(self, node_id: str) -> bool:
        return self._scope_selection.open_comment_peek(node_id)

    @pyqtSlot(result=bool)
    def close_comment_peek(self) -> bool:
        return self._scope_selection.close_comment_peek()

    @pyqtSlot(str, result=bool)
    def open_scope_for_node(self, node_id: str) -> bool:
        return self._scope_selection.open_scope_for_node(node_id)

    @pyqtSlot(result=bool)
    def navigate_scope_parent(self) -> bool:
        return self._scope_selection.navigate_scope_parent()

    @pyqtSlot(result=bool)
    def navigate_scope_root(self) -> bool:
        return self._scope_selection.navigate_scope_root()

    @pyqtSlot(str, result=bool)
    def navigate_scope_to(self, node_id: str) -> bool:
        return self._scope_selection.navigate_scope_to(node_id)

    def bind_runtime_history(self, history: RuntimeGraphHistory | None) -> None:
        self._history = history

    def bind_graph_theme_bridge(
        self, graph_theme_bridge: GraphThemeBridge | None
    ) -> None:
        if self._graph_theme_bridge is graph_theme_bridge:
            return
        if self._graph_theme_bridge is not None:
            try:
                self._graph_theme_bridge.changed.disconnect(
                    self._on_graph_theme_changed
                )
            except (RuntimeError, TypeError):
                pass
        self._graph_theme_bridge = graph_theme_bridge
        if self._graph_theme_bridge is not None:
            self._graph_theme_bridge.changed.connect(self._on_graph_theme_changed)
        self._scene_context.rebuild_models()
        self._remember_scene_payload_graphics_preferences()

    def _on_graph_theme_changed(self) -> None:
        self._remember_scene_payload_graphics_preferences()
        self._scene_context.rebuild_models()

    def _on_graphics_preferences_changed(self) -> None:
        current_preferences = self._current_scene_payload_graphics_preferences()
        if self._scene_payload_graphics_preferences == current_preferences:
            return
        self._scene_payload_graphics_preferences = current_preferences
        scene_context = getattr(self, "_scene_context", None)
        if scene_context is not None:
            scene_context.rebuild_models()

    def set_workspace(
        self, model: GraphModel, registry: NodeRegistry, workspace_id: str
    ) -> None:
        normalized_workspace_id = str(workspace_id)
        if (
            getattr(self, "_model", None) is model
            and self._workspace_id == normalized_workspace_id
        ):
            # Scene already shows this exact (model, workspace); skip the full
            # teardown+rebuild. The delete/duplicate flows call switch_workspace
            # twice for the same destination (once re-entrantly via
            # refresh_workspace_tabs -> set_tabs -> current_index_changed, once
            # explicitly), so this halves their cost. The model-identity check
            # still forces a rebuild on project reload, where a fresh GraphModel
            # reuses the same workspace id.
            return
        self._model = model
        self._registry = registry
        self._scope_selection.workspace_id = normalized_workspace_id
        workspace = model.project.workspaces[self._scope_selection.workspace_id]
        self._scope_selection.comment_peek_node_id = ""
        self._scope_selection.restore_scope_path_from_view(workspace)
        self._selected_node_ids = []
        self._selected_node_lookup = {}
        self._payload_cache.mark_dirty()
        self._remember_scene_payload_graphics_preferences()
        self._scene_context.emit_workspace_changed()
        self._scene_context.emit_scope_changed()
        self._scene_context.rebuild_models()

    def current_workspace(self) -> WorkspaceData:
        return self._scene_context.current_workspace()

    def refresh_workspace_from_model(self, workspace_id: str) -> None:
        normalized_workspace_id = str(workspace_id).strip()
        history = self._scene_context.history
        consume_last_applied_entry = (
            None
            if history is None
            else getattr(history, "consume_last_applied_entry", None)
        )
        entry = (
            consume_last_applied_entry(normalized_workspace_id)
            if callable(consume_last_applied_entry)
            else None
        )
        if entry is not None and normalized_workspace_id == self._workspace_id:
            workspace = self._workspace_or_none()
            if workspace is not None:
                self._scope_selection.validated_comment_peek_node_id()
                self._scope_selection.set_selected_node_ids(
                    self._selected_node_ids, workspace=workspace
                )
                renamed_node_id = history_entry_title_only_node_id(entry)
                if (
                    renamed_node_id
                    and self._scene_context.publish_node_title_payload_delta(
                        renamed_node_id,
                        publication_path="history_title_payload_delta",
                        changed_fields={"node.title"},
                    )
                ):
                    return
                if self._scene_context.publish_history_entry_delta(entry):
                    return
        self._scope_selection.refresh_workspace_from_model(workspace_id)

    def selected_node_id(self) -> str | None:
        return self._scope_selection.selected_node_id()

    def selectedItems(self) -> list[_SelectedNodeProxy]:
        return self._scope_selection.selected_items()

    def workspace_scene_bounds(self) -> QRectF | None:
        return self._scope_selection.workspace_scene_bounds()

    def workspace_scene_bounds_with_fallback(self) -> QRectF:
        return self._scope_selection.workspace_scene_bounds_with_fallback()

    def _rect_payload(self, rect: QRectF) -> dict[str, float]:
        return self._scope_selection.rect_payload(rect)

    @pyqtSlot(result="QVariantMap")
    def workspace_scene_bounds_map(self) -> dict[str, float]:
        return self._scope_selection.workspace_scene_bounds_map()

    def selection_bounds(self) -> QRectF | None:
        return self._scope_selection.selection_bounds()

    def clearSelection(self) -> None:
        self._command_bridge.clearSelection()

    @pyqtSlot()
    def clear_selection(self) -> None:
        self._command_bridge.clear_selection()

    @pyqtSlot(str)
    @pyqtSlot(str, bool)
    def select_node(self, node_id: str, additive: bool = False) -> None:
        self._command_bridge.select_node(node_id, additive=additive)

    @pyqtSlot(float, float, float, float)
    @pyqtSlot(float, float, float, float, bool)
    def select_nodes_in_rect(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        additive: bool = False,
    ) -> None:
        self._command_bridge.select_nodes_in_rect(x1, y1, x2, y2, additive)

    def node_item(self, node_id: str) -> _NodeItemProxy | None:
        return self._scope_selection.node_item(node_id)

    def node_bounds(self, node_id: str) -> QRectF | None:
        return self._scope_selection.node_bounds(node_id)

    def edge_item(self, edge_id: str) -> dict[str, Any] | None:
        return self._scene_context.edge_item(edge_id)

    @pyqtSlot(str, float, float, result=str)
    def add_node_from_type(self, type_id: str, x: float = 0.0, y: float = 0.0) -> str:
        return self._command_bridge.add_node_from_type(type_id, x, y)

    def create_node_from_type(
        self,
        *,
        type_id: str,
        x: float,
        y: float,
        parent_node_id: str | None,
        select_node: bool,
        property_overrides: dict[str, Any] | None = None,
        exposed_port_overrides: dict[str, bool] | None = None,
        initial_title: str | None = None,
        custom_width: float | None = None,
        custom_height: float | None = None,
        after_create=None,  # noqa: ANN001
    ) -> str:
        return self._command_bridge.create_node_from_type(
            type_id=type_id,
            x=x,
            y=y,
            parent_node_id=parent_node_id,
            select_node=select_node,
            property_overrides=property_overrides,
            exposed_port_overrides=exposed_port_overrides,
            initial_title=initial_title,
            custom_width=custom_width,
            custom_height=custom_height,
            after_create=after_create,
        )

    def add_subnode_shell_pin(self, shell_node_id: str, pin_type_id: str) -> str:
        return self._command_bridge.add_subnode_shell_pin(shell_node_id, pin_type_id)

    @pyqtSlot(str, str, str, str, result=bool)
    def are_ports_compatible(
        self,
        source_node_id: str,
        source_port: str,
        target_node_id: str,
        target_port: str,
    ) -> bool:
        return self._policy_bridge.are_ports_compatible(
            source_node_id,
            source_port,
            target_node_id,
            target_port,
        )

    @pyqtSlot(str, str, result=bool)
    def are_port_kinds_compatible(self, source_kind: str, target_kind: str) -> bool:
        return self._policy_bridge.are_port_kinds_compatible(source_kind, target_kind)

    @pyqtSlot(str, str, result=bool)
    def are_data_types_compatible(self, source_type: str, target_type: str) -> bool:
        return self._policy_bridge.are_data_types_compatible(source_type, target_type)

    def add_edge(
        self,
        source_node_id: str,
        source_port: str,
        target_node_id: str,
        target_port: str,
        append_requested: bool = False,
    ) -> str:
        return self._command_bridge.add_edge(
            source_node_id,
            source_port,
            target_node_id,
            target_port,
            append_requested,
        )

    @pyqtSlot("QVariantList", str, str, str, bool, bool, result=bool)
    def request_rewire_edges(
        self,
        edge_ids: list[Any],
        endpoint: str,
        node_id: str,
        port_key: str,
        copy_requested: bool = False,
        append_requested: bool = False,
    ) -> bool:
        return self._command_bridge.request_rewire_edges(
            edge_ids,
            endpoint,
            node_id,
            port_key,
            copy_requested,
            append_requested,
        )

    @pyqtSlot(str, str, result=str)
    def connect_nodes(self, node_a_id: str, node_b_id: str) -> str:
        return self._command_bridge.connect_nodes(node_a_id, node_b_id)

    def remove_edge(self, edge_id: str) -> None:
        self._command_bridge.remove_edge(edge_id)

    def _remove_node(self, node_id: str, *, require_visible: bool) -> bool:
        return self._authoring_boundary.remove_node_with_policy(
            node_id, require_visible=require_visible
        )

    def remove_node(self, node_id: str) -> None:
        self._command_bridge.remove_node(node_id)

    def remove_workspace_node(self, node_id: str) -> bool:
        return self._command_bridge.remove_workspace_node(node_id)

    @pyqtSlot(str)
    def focus_node_slot(self, node_id: str) -> None:
        self._command_bridge.focus_node_slot(node_id)

    def focus_node(self, node_id: str) -> QPointF | None:
        return self._command_bridge.focus_node(node_id)

    @pyqtSlot(str, bool, result=bool)
    def set_node_collapsed(self, node_id: str, collapsed: bool) -> bool:
        return self._command_bridge.set_node_collapsed(node_id, collapsed)

    @pyqtSlot(str, str, bool, result=bool)
    def set_node_settings_group_expanded(
        self,
        node_id: str,
        group_id: str,
        expanded: bool,
    ) -> bool:
        return self._command_bridge.set_node_settings_group_expanded(
            node_id,
            group_id,
            expanded,
        )

    def set_node_locked(self, node_id: str, locked: bool) -> bool:
        return self._command_bridge.set_node_locked(node_id, locked)

    @pyqtSlot(bool, result=bool)
    def set_interact_with_locked_objects(self, enabled: bool) -> bool:
        return self._command_bridge.set_interact_with_locked_objects(enabled)

    @pyqtSlot(str, str, str)
    def set_node_port_label(self, node_id: str, port_key: str, label: str) -> None:
        self._command_bridge.set_node_port_label(node_id, port_key, label)

    @pyqtSlot(str, str, "QVariant")
    def set_node_property(self, node_id: str, key: str, value: Any) -> None:
        self._command_bridge.set_node_property(node_id, key, value)

    @pyqtSlot(str, str, str, result=bool)
    def set_node_secret(self, node_id: str, key: str, plaintext: str) -> bool:
        return self._command_bridge.set_node_secret(node_id, key, plaintext)

    @pyqtSlot(str, str, result=bool)
    def clear_node_secret(self, node_id: str, key: str) -> bool:
        return self._command_bridge.clear_node_secret(node_id, key)

    @pyqtSlot(str, "QVariantMap", result=bool)
    def set_node_properties(self, node_id: str, values: dict[str, Any]) -> bool:
        return self._command_bridge.set_node_properties(node_id, values)

    @pyqtSlot(str, str, str, str, str, str, result=str)
    @pyqtSlot(str, str, str, str, str, str, str, str, result=str)
    def upsert_node_link(
        self,
        node_id: str,
        link_id: str,
        kind: str,
        title: str,
        target: str,
        subtitle: str = "",
        target_workspace_id: str = "",
        target_node_id: str = "",
    ) -> str:
        return self._command_bridge.upsert_node_link(
            node_id,
            link_id,
            kind,
            title,
            target,
            subtitle,
            target_workspace_id,
            target_node_id,
        )

    @pyqtSlot(str, str, result=bool)
    def remove_node_link(self, node_id: str, link_id: str) -> bool:
        return self._command_bridge.remove_node_link(node_id, link_id)

    @pyqtSlot(str, str, int, result=bool)
    def move_node_link(self, node_id: str, link_id: str, offset: int) -> bool:
        return self._command_bridge.move_node_link(node_id, link_id, offset)

    @pyqtSlot(str, str, str, result=str)
    @pyqtSlot(str, str, str, str, str, bool, bool, bool, result=str)
    def upsert_node_comment(
        self,
        node_id: str,
        comment_id: str,
        body: str,
        author: str = "",
        parent_id: str = "",
        resolved: bool = False,
        unread: bool = True,
        pinned: bool = False,
    ) -> str:
        return self._command_bridge.upsert_node_comment(
            node_id,
            comment_id,
            body,
            author,
            parent_id,
            resolved,
            unread,
            pinned,
        )

    @pyqtSlot(str, str, result=bool)
    def remove_node_comment(self, node_id: str, comment_id: str) -> bool:
        return self._command_bridge.remove_node_comment(node_id, comment_id)

    @pyqtSlot(str, str, bool, result=bool)
    def set_node_comment_resolved(
        self, node_id: str, comment_id: str, resolved: bool
    ) -> bool:
        return self._command_bridge.set_node_comment_resolved(
            node_id, comment_id, resolved
        )

    @pyqtSlot(str, str, bool, result=bool)
    def set_node_comment_pinned(
        self, node_id: str, comment_id: str, pinned: bool
    ) -> bool:
        return self._command_bridge.set_node_comment_pinned(node_id, comment_id, pinned)

    @pyqtSlot(str, result=bool)
    def resolve_all_node_comments(self, node_id: str) -> bool:
        return self._command_bridge.resolve_all_node_comments(node_id)

    @pyqtSlot(str, result=bool)
    def mark_node_comments_read(self, node_id: str) -> bool:
        return self._command_bridge.mark_node_comments_read(node_id)

    @pyqtSlot(str, str, result=bool)
    def open_node_link(self, node_id: str, link_id: str) -> bool:
        return self._command_bridge.open_node_link(node_id, link_id)

    @pyqtSlot("QVariant", result="QVariantMap")
    def normalize_node_visual_style(self, visual_style: Any) -> dict[str, Any]:
        return self._command_bridge.normalize_node_visual_style(visual_style)

    @pyqtSlot(str, "QVariant")
    def set_node_visual_style(self, node_id: str, visual_style: Any) -> None:
        self._command_bridge.set_node_visual_style(node_id, visual_style)

    @pyqtSlot(str)
    def clear_node_visual_style(self, node_id: str) -> None:
        self._command_bridge.clear_node_visual_style(node_id)

    @pyqtSlot(str, result=bool)
    def propagate_passive_node_style(self, node_id: str) -> bool:
        return self._command_bridge.propagate_passive_node_style(node_id)

    def set_node_title(self, node_id: str, title: str) -> None:
        self._command_bridge.set_node_title(node_id, title)

    @pyqtSlot("QVariant", result=str)
    def normalize_edge_label(self, label: Any) -> str:
        return self._command_bridge.normalize_edge_label(label)

    @pyqtSlot(str, "QVariant")
    def set_edge_label(self, edge_id: str, label: Any) -> None:
        self._command_bridge.set_edge_label(edge_id, label)

    @pyqtSlot(str)
    def clear_edge_label(self, edge_id: str) -> None:
        self._command_bridge.clear_edge_label(edge_id)

    @pyqtSlot("QVariant", result="QVariantMap")
    def normalize_edge_visual_style(self, visual_style: Any) -> dict[str, Any]:
        return self._command_bridge.normalize_edge_visual_style(visual_style)

    @pyqtSlot(str, "QVariant")
    def set_edge_visual_style(self, edge_id: str, visual_style: Any) -> None:
        self._command_bridge.set_edge_visual_style(edge_id, visual_style)

    @pyqtSlot(str)
    def clear_edge_visual_style(self, edge_id: str) -> None:
        self._command_bridge.clear_edge_visual_style(edge_id)

    @pyqtSlot(str, bool, result=bool)
    def set_edge_enabled(self, edge_id: str, enabled: bool) -> bool:
        return self._command_bridge.set_edge_enabled(edge_id, enabled)

    @pyqtSlot("QVariantList", bool, result=bool)
    def set_edges_enabled(self, edge_ids: list[Any], enabled: bool) -> bool:
        return self._command_bridge.set_edges_enabled(edge_ids, enabled)

    @pyqtSlot("QVariantList", str, result=bool)
    def set_edges_display_mode(self, edge_ids: list[Any], mode: str) -> bool:
        return self._command_bridge.set_edges_display_mode(edge_ids, mode)

    @pyqtSlot(str, str, "QVariantList", result=bool)
    def set_port_modifiers(
        self, node_id: str, port_key: str, modifiers: list[Any]
    ) -> bool:
        return self._command_bridge.set_port_modifiers(node_id, port_key, modifiers)

    @pyqtSlot(str, str, result=bool)
    def set_principal_input_port(self, node_id: str, port_key: str) -> bool:
        return self._command_bridge.set_principal_input_port(node_id, port_key)

    @pyqtSlot(str, str, int, result=str)
    def insert_dynamic_port(
        self,
        node_id: str,
        group_id: str,
        ordinal: int,
    ) -> str:
        return self._command_bridge.insert_dynamic_port(node_id, group_id, ordinal)

    @pyqtSlot(str, str, str, result="QVariantMap")
    def remove_dynamic_port(
        self,
        node_id: str,
        group_id: str,
        port_key: str,
    ) -> dict[str, Any]:
        return self._command_bridge.remove_dynamic_port(node_id, group_id, port_key)

    @pyqtSlot(str, str, str, str, result="QVariantMap")
    def rename_dynamic_port(
        self,
        node_id: str,
        group_id: str,
        port_key: str,
        value: str,
    ) -> dict[str, Any]:
        return self._command_bridge.rename_dynamic_port(
            node_id,
            group_id,
            port_key,
            value,
        )

    @pyqtSlot(bool, result=bool)
    def set_hide_optional_ports(self, hide_optional_ports: bool) -> bool:
        return self._command_bridge.set_hide_optional_ports(hide_optional_ports)

    def set_exposed_port(self, node_id: str, key: str, exposed: bool) -> None:
        self._command_bridge.set_exposed_port(node_id, key, exposed)

    @pyqtSlot(str, float, float)
    def move_node(self, node_id: str, x: float, y: float) -> None:
        self._command_bridge.move_node(node_id, x, y)

    @pyqtSlot(str, float, float)
    def resize_node(self, node_id: str, width: float, height: float) -> None:
        self._command_bridge.resize_node(node_id, width, height)

    @pyqtSlot(str, float, float, float, float)
    def set_node_geometry(
        self, node_id: str, x: float, y: float, width: float, height: float
    ) -> None:
        self._command_bridge.set_node_geometry(node_id, x, y, width, height)

    @pyqtSlot("QVariantList", float, float, result=bool)
    def move_nodes_by_delta(self, node_ids: list[Any], dx: float, dy: float) -> bool:
        return self._command_bridge.move_nodes_by_delta(node_ids, dx, dy)

    def align_selected_nodes(
        self,
        alignment: str,
        *,
        snap_to_grid: bool = False,
        grid_size: float = _SNAP_GRID_SIZE,
    ) -> bool:
        return self._command_bridge.align_selected_nodes(
            alignment,
            snap_to_grid=snap_to_grid,
            grid_size=grid_size,
        )

    def distribute_selected_nodes(
        self,
        orientation: str,
        *,
        snap_to_grid: bool = False,
        grid_size: float = _SNAP_GRID_SIZE,
    ) -> bool:
        return self._command_bridge.distribute_selected_nodes(
            orientation,
            snap_to_grid=snap_to_grid,
            grid_size=grid_size,
        )

    def set_selected_same_type_size(self, node_ids: list[Any], dimension: str) -> bool:
        return self._command_bridge.set_selected_same_type_size(node_ids, dimension)

    def straighten_selected_connections(self) -> bool:
        return self._command_bridge.straighten_selected_connections()

    @pyqtSlot("QVariantList", result=str)
    def wrap_node_ids_in_group_backdrop(self, node_ids: list[Any]) -> str:
        return self._command_bridge.wrap_node_ids_in_group_backdrop(node_ids)

    @pyqtSlot(result=bool)
    def wrap_selected_nodes_in_group_backdrop(self) -> bool:
        return self._command_bridge.wrap_selected_nodes_in_group_backdrop()

    @pyqtSlot(result=bool)
    def group_selected_nodes(self) -> bool:
        return self._command_bridge.group_selected_nodes()

    @pyqtSlot(result=bool)
    def ungroup_selected_subnode(self) -> bool:
        return self._command_bridge.ungroup_selected_subnode()

    @pyqtSlot(result=bool)
    def duplicate_selected_subgraph(self) -> bool:
        return self._command_bridge.duplicate_selected_subgraph()

    def serialize_selected_subgraph_fragment(self) -> dict[str, Any] | None:
        return self._command_bridge.serialize_selected_subgraph_fragment()

    def fragment_bounds_center(
        self, fragment_payload: Any
    ) -> tuple[float, float] | None:
        return self._command_bridge.fragment_bounds_center(fragment_payload)

    def paste_subgraph_fragment(
        self, fragment_payload: Any, center_x: float, center_y: float
    ) -> bool:
        return self._command_bridge.paste_subgraph_fragment(
            fragment_payload, center_x, center_y
        )

    def delete_selected_graph_items(self, edge_ids: list[Any]) -> bool:
        return self._command_bridge.delete_selected_graph_items(edge_ids)


__all__ = [
    "GraphSceneBridgeBase",
    "_GraphScenePayloadCache",
    "_GraphScenePendingSurfaceAction",
]
