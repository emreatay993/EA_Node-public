from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Mapping

from PyQt6.QtCore import QTimer, pyqtProperty, pyqtSignal, pyqtSlot
from ea_node_editor.ui_qml.bridge_runtime import (
    copy_dict as _copy_dict,
)
from ea_node_editor.ui_qml.graph_canvas_viewport_index import (
    normalize_node_id,
)

from ea_node_editor.ui_qml.bridge_runtime import (
    copy_dict as _copy_dict,
    copy_list as _copy_list,
    invoke_bool as _invoke_bool,
    invoke_value as _invoke_value,
    source_attr as _source_attr,
)
if TYPE_CHECKING:
    pass


_MINIMAP_EMPTY_BOUNDS_PAYLOAD = {"x": -1600.0, "y": -900.0, "width": 3200.0, "height": 1800.0}


_MINIMAP_PADDING = 220.0


_MINIMAP_MIN_WIDTH = 3200.0


_MINIMAP_MIN_HEIGHT = 1800.0


def _finite_float(value: object, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) else default


def _minimap_bounds_payload(payloads: list[dict[str, Any]]) -> dict[str, float]:
    min_x: float | None = None
    min_y: float | None = None
    max_x: float | None = None
    max_y: float | None = None
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        x = _finite_float(payload.get("x"))
        y = _finite_float(payload.get("y"))
        width = _finite_float(payload.get("width"))
        height = _finite_float(payload.get("height"))
        if width <= 0.0 or height <= 0.0:
            continue
        right = x + width
        bottom = y + height
        min_x = x if min_x is None else min(min_x, x)
        min_y = y if min_y is None else min(min_y, y)
        max_x = right if max_x is None else max(max_x, right)
        max_y = bottom if max_y is None else max(max_y, bottom)

    if min_x is None or min_y is None or max_x is None or max_y is None:
        return dict(_MINIMAP_EMPTY_BOUNDS_PAYLOAD)

    padded_x = min_x - _MINIMAP_PADDING
    padded_y = min_y - _MINIMAP_PADDING
    padded_width = max(0.0, max_x - min_x) + (_MINIMAP_PADDING * 2.0)
    padded_height = max(0.0, max_y - min_y) + (_MINIMAP_PADDING * 2.0)
    width = max(padded_width, _MINIMAP_MIN_WIDTH)
    height = max(padded_height, _MINIMAP_MIN_HEIGHT)
    center_x = padded_x + padded_width * 0.5
    center_y = padded_y + padded_height * 0.5
    return {
        "x": center_x - width * 0.5,
        "y": center_y - height * 0.5,
        "width": width,
        "height": height,
    }


def _locked_node_status_summary(payloads: list[Any]) -> dict[str, Any]:
    locked_node_count = 0
    focus_addon_ids: list[str] = []
    seen_focus_addon_ids: set[str] = set()
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        if not bool(payload.get("read_only")) or not bool(payload.get("unresolved")):
            continue
        locked_node_count += 1
        locked_state = payload.get("locked_state")
        focus_addon_id = ""
        if isinstance(locked_state, Mapping):
            focus_addon_id = str(locked_state.get("focus_addon_id") or "").strip()
        if not focus_addon_id:
            focus_addon_id = str(payload.get("addon_id") or "").strip()
        if not focus_addon_id or focus_addon_id in seen_focus_addon_ids:
            continue
        seen_focus_addon_ids.add(focus_addon_id)
        focus_addon_ids.append(focus_addon_id)
    return {
        "lockedNodeCount": locked_node_count,
        "missingAddonCount": len(focus_addon_ids),
        "focusAddonIds": focus_addon_ids,
        "focusAddonId": focus_addon_ids[0] if len(focus_addon_ids) == 1 else "",
    }


_EDGE_ENDPOINT_NODE_KEYS = (
    "node_id",
    "x",
    "y",
    "width",
    "height",
    "collapsed",
    "read_only",
    "unresolved",
    "surface_family",
    "surface_variant",
    "surface_metrics",
)
_EDGE_ENDPOINT_PORT_KEYS = (
    "key",
    "direction",
    "side",
    "exposed",
    "layout_row",
    "handle_visible",
    "presentation_anchor",
)


def _compact_edge_endpoint_port_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    compact = {key: payload.get(key) for key in _EDGE_ENDPOINT_PORT_KEYS if key in payload}
    if "exposed" not in compact:
        compact["exposed"] = True
    presentation_anchor = compact.get("presentation_anchor")
    if isinstance(presentation_anchor, Mapping):
        compact["presentation_anchor"] = dict(presentation_anchor)
    return compact


def _compact_edge_endpoint_node_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    node_id = normalize_node_id(payload.get("node_id"))
    if not node_id:
        return {}
    compact: dict[str, Any] = {key: payload.get(key) for key in _EDGE_ENDPOINT_NODE_KEYS if key in payload}
    compact["node_id"] = node_id
    compact.setdefault("collapsed", False)
    compact.setdefault("read_only", False)
    compact.setdefault("unresolved", False)
    compact.setdefault("surface_family", "standard")
    compact.setdefault("surface_variant", "")
    surface_metrics = compact.get("surface_metrics")
    if isinstance(surface_metrics, Mapping):
        compact["surface_metrics"] = dict(surface_metrics)
    ports = payload.get("ports")
    if isinstance(ports, list):
        compact["ports"] = [
            port_payload
            for port in ports
            if (port_payload := _compact_edge_endpoint_port_payload(port))
        ]
    else:
        compact["ports"] = []
    return compact


def _edge_endpoint_nodes_payload(payloads: list[Any]) -> list[dict[str, Any]]:
    return [
        compact
        for payload in payloads
        if (compact := _compact_edge_endpoint_node_payload(payload))
    ]


class SceneModelsProps:
    """Scene model projections: nodes/edges/minimap/backdrop models, locked-node
    summary, selection lookups, view-local port filters, and scene policy
    forwards. Properties + cache refresh plumbing only."""

    scene_nodes_changed = pyqtSignal()
    scene_edges_changed = pyqtSignal()
    scene_selection_changed = pyqtSignal()
    scene_workspace_changing = pyqtSignal(str)
    scene_workspace_changed = pyqtSignal()
    edge_endpoint_nodes_changed = pyqtSignal()
    minimap_scene_model_changed = pyqtSignal()
    locked_node_status_changed = pyqtSignal()

    def _handle_scene_nodes_changed(self) -> None:
        self._node_model_revision += 1
        targeted, minimap_changed = self._apply_targeted_projection_delta()
        if not targeted:
            self._mark_minimap_scene_model_dirty()
            self._mark_edge_endpoint_nodes_model_dirty()
            self._mark_locked_node_status_summary_dirty()
            self._schedule_locked_node_status_changed()
        self.scene_nodes_changed.emit()
        if not targeted:
            self.edge_endpoint_nodes_changed.emit()
        if minimap_changed or not targeted:
            self._schedule_minimap_scene_model_changed()
        if self._apply_visible_scene_node_delta():
            return
        self._invalidate_visible_scene_models()

    def _handle_scene_workspace_changed(self, workspace_id: str = "") -> None:
        next_workspace_id = str(
            workspace_id or _source_attr(self._scene_state_source, "workspace_id", "") or ""
        ).strip()
        self.scene_workspace_changing.emit(next_workspace_id)
        self._node_model_revision += 1
        self._mark_minimap_scene_model_dirty()
        self._mark_edge_endpoint_nodes_model_dirty()
        self._minimap_node_index_by_id = {}
        self._edge_endpoint_node_index_by_id = {}
        self._mark_locked_node_status_summary_dirty()
        self._schedule_locked_node_status_changed()
        self.failure_highlight_changed.emit()
        self.node_execution_state_changed.emit()
        self._visible_node_index.reset()
        self._visible_backdrop_index.reset()
        self._visible_nodes_model.sync_payloads([])
        self._visible_badge_nodes_model.sync_payloads([])
        self._visible_backdrop_nodes_model.sync_payloads([])
        self._visible_scene_models_dirty = True
        self._visible_scene_models_deferred = False
        self._visible_scene_query_rect = None
        self._pending_visible_scene_query_rect = None
        self.scene_workspace_changed.emit()
        self.edge_endpoint_nodes_changed.emit()
        self.visible_scene_models_changed.emit()
        self._schedule_minimap_scene_model_changed()

    def _mark_minimap_scene_model_dirty(self) -> None:
        self._minimap_scene_model_dirty = True

    def _mark_edge_endpoint_nodes_model_dirty(self) -> None:
        self._edge_endpoint_nodes_model_dirty = True

    def _refresh_edge_endpoint_nodes_model_cache(self) -> None:
        if not self._edge_endpoint_nodes_model_dirty:
            return
        self._edge_endpoint_nodes_model_dirty = False
        payloads = _copy_list(_source_attr(self._scene_state_source, "nodes_model", []))
        self._edge_endpoint_nodes_model_cache = _edge_endpoint_nodes_payload(payloads)
        self._edge_endpoint_node_index_by_id = {
            node_id: index
            for index, payload in enumerate(self._edge_endpoint_nodes_model_cache)
            if (node_id := normalize_node_id(payload.get("node_id")))
        }

    def _refresh_minimap_scene_model_cache(self) -> None:
        if not self._minimap_scene_model_dirty:
            return
        self._minimap_scene_model_dirty = False
        payloads = _copy_list(_source_attr(self._scene_state_source, "minimap_nodes_model", []))
        self._minimap_nodes_model_cache = [payload for payload in payloads if isinstance(payload, dict)]
        self._minimap_node_index_by_id = {
            node_id: index
            for index, payload in enumerate(self._minimap_nodes_model_cache)
            if (node_id := normalize_node_id(payload.get("node_id")))
        }
        self._workspace_scene_bounds_payload_cache = _minimap_bounds_payload(self._minimap_nodes_model_cache)

    @staticmethod
    def _is_targeted_projection_delta(delta: dict[str, Any]) -> bool:
        if str(delta.get("kind", "")).strip() != "node_delta":
            return False
        if delta.get("added_node_ids") or delta.get("removed_node_ids"):
            return False
        reason = str(delta.get("reason", "")).strip()
        return reason.endswith(("position_delta", "title_payload_delta", "geometry_delta"))

    def _replace_targeted_endpoint_payloads(self, payloads: list[dict[str, Any]]) -> bool:
        if self._edge_endpoint_nodes_model_dirty:
            return False
        replacements: list[tuple[int, dict[str, Any]]] = []
        for payload in payloads:
            compact = _compact_edge_endpoint_node_payload(payload)
            node_id = normalize_node_id(compact.get("node_id"))
            index = self._edge_endpoint_node_index_by_id.get(node_id)
            if not node_id or index is None:
                return False
            replacements.append((index, compact))
        for index, compact in replacements:
            self._edge_endpoint_nodes_model_cache[index] = compact
        return True

    def _append_targeted_endpoint_payloads(self, payloads: list[dict[str, Any]]) -> bool:
        if self._edge_endpoint_nodes_model_dirty:
            return False
        additions: list[tuple[str, dict[str, Any]]] = []
        for payload in payloads:
            compact = _compact_edge_endpoint_node_payload(payload)
            node_id = normalize_node_id(compact.get("node_id"))
            if not node_id or node_id in self._edge_endpoint_node_index_by_id:
                return False
            additions.append((node_id, compact))
        start_index = len(self._edge_endpoint_nodes_model_cache)
        self._edge_endpoint_nodes_model_cache.extend(compact for _, compact in additions)
        for offset, (node_id, _) in enumerate(additions):
            self._edge_endpoint_node_index_by_id[node_id] = start_index + offset
        return True

    def _targeted_minimap_payloads(self, node_ids: list[str]) -> list[dict[str, Any]] | None:
        loader = getattr(self._scene_state_source, "minimap_payloads_for_node_ids", None)
        if callable(loader):
            return loader(node_ids)
        wanted = set(node_ids)
        payloads = [
            payload
            for payload in _copy_list(_source_attr(self._scene_state_source, "minimap_nodes_model", []))
            if isinstance(payload, dict) and normalize_node_id(payload.get("node_id")) in wanted
        ]
        return payloads if len(payloads) == len(wanted) else None

    def _replace_targeted_minimap_payloads(self, node_ids: list[str]) -> tuple[bool, bool]:
        if self._minimap_scene_model_dirty:
            return False, False
        payloads = self._targeted_minimap_payloads(node_ids)
        if payloads is None:
            return False, False
        replacements: list[tuple[int, dict[str, Any]]] = []
        changed = False
        for payload in payloads:
            node_id = normalize_node_id(payload.get("node_id"))
            index = self._minimap_node_index_by_id.get(node_id)
            if not node_id or index is None:
                return False, False
            replacement = dict(payload)
            changed = changed or self._minimap_nodes_model_cache[index] != replacement
            replacements.append((index, replacement))
        for index, replacement in replacements:
            self._minimap_nodes_model_cache[index] = replacement
        if changed:
            self._workspace_scene_bounds_payload_cache = _minimap_bounds_payload(self._minimap_nodes_model_cache)
        return True, changed

    def _append_targeted_minimap_payloads(self, node_ids: list[str]) -> tuple[bool, bool]:
        if self._minimap_scene_model_dirty:
            return False, False
        payloads = self._targeted_minimap_payloads(node_ids)
        if payloads is None:
            return False, False
        additions: list[tuple[str, dict[str, Any]]] = []
        for payload in payloads:
            node_id = normalize_node_id(payload.get("node_id"))
            if not node_id or node_id in self._minimap_node_index_by_id:
                return False, False
            additions.append((node_id, dict(payload)))
        if len(additions) != len(node_ids) or {node_id for node_id, _ in additions} != set(node_ids):
            return False, False
        start_index = len(self._minimap_nodes_model_cache)
        self._minimap_nodes_model_cache.extend(payload for _, payload in additions)
        for offset, (node_id, _) in enumerate(additions):
            self._minimap_node_index_by_id[node_id] = start_index + offset
        self._workspace_scene_bounds_payload_cache = _minimap_bounds_payload(
            self._minimap_nodes_model_cache
        )
        return True, bool(additions)

    def _apply_targeted_projection_delta(self) -> tuple[bool, bool]:
        delta = _copy_dict(_source_attr(self._scene_state_source, "node_delta_payload", {}))
        if str(delta.get("kind", "")).strip() != "node_delta":
            return False, False
        raw_node_payloads = delta.get("nodes")
        raw_backdrop_payloads = delta.get("backdrop_nodes")
        if not isinstance(raw_node_payloads, list) or not isinstance(raw_backdrop_payloads, list):
            return False, False
        node_payloads = [payload for payload in raw_node_payloads if isinstance(payload, dict)]
        backdrop_payloads = [payload for payload in raw_backdrop_payloads if isinstance(payload, dict)]
        all_payloads = [*node_payloads, *backdrop_payloads]
        node_ids = [
            node_id
            for payload in all_payloads
            if (node_id := normalize_node_id(payload.get("node_id")))
        ]
        if len(node_ids) != len(all_payloads) or len(set(node_ids)) != len(node_ids):
            return False, False

        raw_added_node_ids = list(delta.get("added_node_ids") or [])
        added_node_ids = [normalize_node_id(value) for value in raw_added_node_ids]
        if raw_added_node_ids:
            if (
                delta.get("removed_node_ids")
                or len(added_node_ids) != len(raw_added_node_ids)
                or any(not node_id for node_id in added_node_ids)
                or len(set(added_node_ids)) != len(added_node_ids)
                or len(node_ids) != len(added_node_ids)
                or set(node_ids) != set(added_node_ids)
                or self._locked_node_status_summary_dirty
                or _locked_node_status_summary(node_payloads)["lockedNodeCount"]
            ):
                return False, False
            if not self._append_targeted_endpoint_payloads(node_payloads):
                return False, False
            return self._append_targeted_minimap_payloads(added_node_ids)

        if not self._is_targeted_projection_delta(delta):
            return False, False
        if node_payloads and not self._replace_targeted_endpoint_payloads(node_payloads):
            return False, False
        minimap_handled, minimap_changed = self._replace_targeted_minimap_payloads(node_ids)
        return minimap_handled, minimap_changed

    def _schedule_minimap_scene_model_changed(self) -> None:
        if self._minimap_scene_model_notify_pending:
            return
        self._minimap_scene_model_notify_pending = True
        QTimer.singleShot(0, self._emit_minimap_scene_model_changed)

    def _emit_minimap_scene_model_changed(self) -> None:
        self._minimap_scene_model_notify_pending = False
        self._refresh_minimap_scene_model_cache()
        self.minimap_scene_model_changed.emit()

    def _mark_locked_node_status_summary_dirty(self) -> None:
        self._locked_node_status_summary_dirty = True

    def _refresh_locked_node_status_summary(self) -> None:
        if not self._locked_node_status_summary_dirty:
            return
        self._locked_node_status_summary_dirty = False
        payloads = _copy_list(_source_attr(self._scene_state_source, "nodes_model", []))
        self._locked_node_status_summary_cache = _locked_node_status_summary(payloads)

    def _schedule_locked_node_status_changed(self) -> None:
        if self._locked_node_status_notify_pending:
            return
        self._locked_node_status_notify_pending = True
        QTimer.singleShot(0, self._emit_locked_node_status_changed)

    def _emit_locked_node_status_changed(self) -> None:
        self._locked_node_status_notify_pending = False
        self._refresh_locked_node_status_summary()
        self.locked_node_status_changed.emit()

    def _hide_optional_ports(self) -> bool:
        state_source = self._scene_state_source
        hide_optional_ports = getattr(state_source, "hide_optional_ports", None) if state_source is not None else None
        if hide_optional_ports is not None:
            return bool(hide_optional_ports)

        workspace = _invoke_value(self._scene_bridge, "_workspace_or_none")
        if workspace is None:
            try:
                workspace = _invoke_value(self._scene_bridge, "current_workspace")
            except RuntimeError:
                return False
        if workspace is None:
            return False
        views = getattr(workspace, "views", None)
        if not isinstance(views, dict) or not views:
            return False
        active_view_id = str(getattr(workspace, "active_view_id", "") or "")
        active_view = views.get(active_view_id)
        if active_view is None:
            active_view = next(iter(views.values()), None)
        if active_view is None:
            return False
        return bool(getattr(active_view, "hide_optional_ports", False))

    def _set_active_view_filter(self, name: str, value: bool) -> bool:
        scene_bridge = self._scene_bridge
        if scene_bridge is None:
            return False
        command_source = getattr(scene_bridge, "command_bridge", scene_bridge)
        return _invoke_bool(command_source, name, bool(value))

    def _record_mutation_timing_phase(self, phase_name: str, elapsed_ms: float) -> None:
        recorder = getattr(self._scene_bridge, "record_mutation_timing_phase", None)
        if callable(recorder):
            recorder(phase_name, elapsed_ms)

    def _record_mutation_counter(self, counter_name: str, amount: int = 1, *, reason: str = "") -> None:
        recorder = getattr(self._scene_bridge, "record_mutation_counter", None)
        if callable(recorder):
            recorder(counter_name, amount, reason=reason)

    @pyqtProperty(bool, notify=scene_nodes_changed)
    def hide_optional_ports(self) -> bool:
        return self._hide_optional_ports()

    @pyqtProperty("QVariantList", notify=scene_nodes_changed)
    def nodes_model(self) -> list[dict]:
        return _copy_list(_source_attr(self._scene_state_source, "nodes_model", []))

    @pyqtProperty("QVariantMap", notify=scene_nodes_changed)
    def node_delta_payload(self) -> dict[str, Any]:
        return _copy_dict(_source_attr(self._scene_state_source, "node_delta_payload", {}))

    @pyqtProperty("QVariantList", notify=scene_nodes_changed)
    def edge_endpoint_nodes_model(self) -> list[dict]:
        self._refresh_edge_endpoint_nodes_model_cache()
        return list(self._edge_endpoint_nodes_model_cache)

    @pyqtProperty("QVariantList", notify=edge_endpoint_nodes_changed)
    def stable_edge_endpoint_nodes_model(self) -> list[dict]:
        return self.edge_endpoint_nodes_model

    @pyqtProperty("QVariantMap", notify=locked_node_status_changed)
    def locked_node_status_summary(self) -> dict[str, Any]:
        self._refresh_locked_node_status_summary()
        return dict(self._locked_node_status_summary_cache)

    @pyqtProperty("QVariantList", notify=minimap_scene_model_changed)
    def minimap_nodes_model(self) -> list[dict]:
        self._refresh_minimap_scene_model_cache()
        return list(self._minimap_nodes_model_cache)

    @pyqtProperty("QVariantList", notify=scene_nodes_changed)
    def backdrop_nodes_model(self) -> list[dict]:
        return _copy_list(_source_attr(self._scene_state_source, "backdrop_nodes_model", []))

    @pyqtProperty("QVariantMap", notify=minimap_scene_model_changed)
    def workspace_scene_bounds_payload(self) -> dict[str, Any]:
        self._refresh_minimap_scene_model_cache()
        return dict(self._workspace_scene_bounds_payload_cache)

    @pyqtProperty("QVariantList", notify=scene_edges_changed)
    def edges_model(self) -> list[dict]:
        return _copy_list(_source_attr(self._scene_state_source, "edges_model", []))

    @pyqtProperty("QVariantMap", notify=scene_edges_changed)
    def edge_delta_payload(self) -> dict[str, Any]:
        return _copy_dict(_source_attr(self._scene_state_source, "edge_delta_payload", {}))

    @pyqtProperty("QVariantMap", notify=scene_selection_changed)
    def selected_node_lookup(self) -> dict[str, bool]:
        return _copy_dict(_source_attr(self._scene_state_source, "selected_node_lookup", {}))

    @pyqtProperty("QVariantList", notify=scene_selection_changed)
    def selected_node_ids(self) -> list[str]:
        selected: list[str] = []
        for node_id in _copy_list(_source_attr(self._scene_state_source, "selected_node_ids", [])):
            normalized = str(node_id or "").strip()
            if normalized:
                selected.append(normalized)
        return selected

    @pyqtProperty(bool, constant=True)
    def selected_node_lookup_authoritative(self) -> bool:
        return True

    @pyqtSlot(bool, result=bool)
    def set_hide_optional_ports(self, hide_optional_ports: bool) -> bool:
        return self._set_active_view_filter("set_hide_optional_ports", hide_optional_ports)

    @pyqtSlot(str, str, result=bool)
    def are_port_kinds_compatible(self, source_kind: str, target_kind: str) -> bool:
        return _invoke_bool(
            self._scene_policy_source,
            "are_port_kinds_compatible",
            source_kind,
            target_kind,
        )

    @pyqtSlot(str, str, str, result="QVariantMap")
    def compatible_endpoint_snapshot(
        self,
        anchor_node_id: str,
        anchor_port_key: str,
        candidate_role: str,
    ) -> dict[str, Any]:
        value = _invoke_value(
            self._scene_policy_source,
            "compatible_endpoint_snapshot",
            anchor_node_id,
            anchor_port_key,
            candidate_role,
        )
        return dict(value) if isinstance(value, Mapping) else {}

    @pyqtSlot("QVariantList", str, result="QVariantMap")
    @pyqtSlot("QVariantList", str, bool, bool, result="QVariantMap")
    def compatible_rewire_endpoint_snapshot(
        self,
        edge_ids: list[Any],
        endpoint: str,
        copy_requested: bool = False,
        append_requested: bool = False,
    ) -> dict[str, Any]:
        value = _invoke_value(
            self._scene_policy_source,
            "compatible_rewire_endpoint_snapshot",
            list(edge_ids or []),
            endpoint,
            bool(copy_requested),
            bool(append_requested),
        )
        return dict(value) if isinstance(value, Mapping) else {}

    @pyqtSlot(str, str, result=bool)
    def are_data_types_compatible(self, source_type: str, target_type: str) -> bool:
        return _invoke_bool(
            self._scene_policy_source,
            "are_data_types_compatible",
            source_type,
            target_type,
        )
