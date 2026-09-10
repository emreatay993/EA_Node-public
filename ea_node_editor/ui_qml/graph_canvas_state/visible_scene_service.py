from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Iterable, Mapping

from PyQt6.QtCore import QObject, QTimer, pyqtProperty, pyqtSignal, pyqtSlot
from ea_node_editor.ui_qml.bridge_runtime import (
    copy_dict as _copy_dict,
)
from ea_node_editor.ui_qml.graph_canvas_viewport_index import (
    DEFAULT_VIEWPORT_MODEL_BUCKET_PX,
    DEFAULT_VIEWPORT_MODEL_HYSTERESIS_PADDING_PX,
    GraphCanvasViewportIndex,
    SceneRect,
    bucketed_hysteresis_visible_scene_rect,
    expanded_visible_scene_rect,
    lookahead_visible_scene_rect,
    normalize_node_id,
    payload_scene_rect,
    rect_contains,
    rects_intersect,
    rects_equal,
    scene_rect_payload,
)
from ea_node_editor.ui_qml.graph_canvas_visible_model import GraphCanvasVisibleModel

from ea_node_editor.ui_qml.bridge_runtime import (
    copy_dict as _copy_dict,
    copy_list as _copy_list,
    source_attr as _source_attr,
)
from ea_node_editor.ui_qml.graph_canvas_state.execution_state_props import (
    _lookup_node_ids,
    _node_ids_from_values,
)
if TYPE_CHECKING:
    pass


def _payloads_from_delta(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [payload for payload in value if isinstance(payload, dict)]


def _payload_by_node_id(payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        node_id = normalize_node_id(payload.get("node_id"))
        if node_id:
            by_id[node_id] = payload
    return by_id


def _positive_count(value: Any) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _badge_node_payloads(payloads: Iterable[Any]) -> list[Any]:
    return [
        payload
        for payload in payloads
        if isinstance(payload, Mapping)
        and (
            _positive_count(payload.get("comment_count"))
            or _positive_count(payload.get("link_count"))
        )
    ]


class VisibleSceneModelOps:
    """Viewport virtualization (the visible scene model): hysteresis/bucketed
    query rects, viewport-indexed models, node-delta sync, invalidation,
    and the visible_* projections. This module owns the virtualization
    LOGIC; the other props modules stay projection-only."""

    visible_scene_models_changed = pyqtSignal()

    def _active_virtualization_node_ids(self) -> set[str]:
        active_ids: set[str] = set()
        active_ids.update(_lookup_node_ids(self.selected_node_lookup))
        active_ids.update(_lookup_node_ids(self.failed_node_lookup))
        active_ids.update(_lookup_node_ids(self.running_node_lookup))
        active_ids.update(_lookup_node_ids(self.warning_node_lookup))
        active_ids.update(_lookup_node_ids(self.selected_run_preview_node_lookup))
        active_ids.update(self._visible_model_active_node_ids)
        active_ids.update(_lookup_node_ids(_source_attr(self._scene_state_source, "active_virtualization_node_lookup", {})))
        active_ids.update(_lookup_node_ids(_source_attr(self._scene_state_source, "visible_model_active_node_lookup", {})))
        active_ids.update(_node_ids_from_values(_source_attr(self._scene_state_source, "visible_model_active_node_ids", ())))
        return active_ids

    def _visible_model_hysteresis_padding_px(self) -> float:
        view_bridge = self._view_bridge
        return float(
            _source_attr(
                view_bridge,
                "visible_model_hysteresis_padding_px",
                DEFAULT_VIEWPORT_MODEL_HYSTERESIS_PADDING_PX,
            )
        )

    def _visible_model_bucket_px(self) -> float:
        view_bridge = self._view_bridge
        return float(
            _source_attr(
                view_bridge,
                "visible_model_bucket_px",
                DEFAULT_VIEWPORT_MODEL_BUCKET_PX,
            )
        )

    def _exact_visible_scene_query_rect(self) -> SceneRect | None:
        return expanded_visible_scene_rect(
            self.visible_scene_rect_payload,
            zoom=self.zoom_value,
        )

    def _bucketed_visible_scene_query_rect(self) -> SceneRect | None:
        return bucketed_hysteresis_visible_scene_rect(
            self.visible_scene_rect_payload,
            zoom=self.zoom_value,
            hysteresis_padding_px=self._visible_model_hysteresis_padding_px(),
            bucket_px=self._visible_model_bucket_px(),
        )

    def _lookahead_visible_scene_query_rect(self) -> SceneRect | None:
        return lookahead_visible_scene_rect(
            self.visible_scene_rect_payload,
            zoom=self.zoom_value,
            lookahead_px=self._visible_model_bucket_px(),
        )

    def _current_visible_scene_query_rect(self, *, force_exact: bool) -> SceneRect | None:
        if force_exact:
            return self._exact_visible_scene_query_rect()
        if self._pending_visible_scene_query_rect is not None:
            return self._pending_visible_scene_query_rect
        exact_rect = self._exact_visible_scene_query_rect()
        if rect_contains(self._visible_scene_query_rect, exact_rect):
            return self._visible_scene_query_rect
        return self._bucketed_visible_scene_query_rect()

    def _viewport_indexed_model(
        self,
        source_name: str,
        index: GraphCanvasViewportIndex,
        *,
        visible_rect: SceneRect | None,
    ) -> list[Any]:
        active_ids = self._active_virtualization_node_ids()
        return index.query(
            workspace_id=self._active_workspace_id(),
            model_revision=self._node_model_revision,
            source_loader=lambda: _copy_list(_source_attr(self._scene_state_source, source_name, [])),
            visible_rect=visible_rect,
            active_node_ids=active_ids,
        )

    def _apply_visible_scene_node_delta(self) -> bool:
        delta = _copy_dict(_source_attr(self._scene_state_source, "node_delta_payload", {}))
        if not delta or str(delta.get("kind", "")).strip() != "node_delta":
            return False
        if self._visible_scene_models_dirty or self._visible_scene_models_deferred:
            self._record_visible_scene_model_delta_fallback("dirty_or_deferred")
            return False
        removed_node_ids = _node_ids_from_values(delta.get("removed_node_ids", ()))
        added_node_ids = _node_ids_from_values(delta.get("added_node_ids", ()))

        update_start = time.perf_counter()
        try:
            row_updates = self._sync_visible_model_node_delta(
                self._visible_nodes_model,
                _payloads_from_delta(delta.get("nodes")),
                added_node_ids=added_node_ids,
                removed_node_ids=removed_node_ids,
                visibility_may_change=bool(delta.get("visibility_may_change", False)),
            )
            if row_updates is None:
                self._record_visible_scene_model_delta_fallback("node_visibility_transition")
                return False
            backdrop_row_updates = self._sync_visible_model_node_delta(
                self._visible_backdrop_nodes_model,
                _payloads_from_delta(delta.get("backdrop_nodes")),
                added_node_ids=added_node_ids,
                removed_node_ids=removed_node_ids,
                visibility_may_change=bool(delta.get("visibility_may_change", False)),
            )
            if backdrop_row_updates is None:
                self._record_visible_scene_model_delta_fallback("backdrop_visibility_transition")
                return False
            self._sync_visible_badge_nodes_model()
        finally:
            self._record_mutation_timing_phase(
                "visible_node_model_update_ms",
                (time.perf_counter() - update_start) * 1000.0,
            )

        self._visible_scene_model_delta_update_count += 1
        self._visible_scene_model_delta_row_update_count += row_updates + backdrop_row_updates
        return True

    def _record_visible_scene_model_delta_fallback(self, reason: str) -> None:
        self._visible_scene_model_delta_fallback_count += 1
        self._record_mutation_counter("visible_model_delta_fallback", reason=reason)

    def _handle_visible_model_duplicate_node_ids(self, node_ids: list) -> None:
        """A visible model received duplicate node_ids: upstream payload-cache
        corruption (the duplicate/phantom-node bug). The model already deduped
        its rows; count the event and schedule a deferred full scene resync so
        the payload cache is rebuilt from the graph model (the ground truth).
        Deferred via a zero-timer because this can fire while a scene
        publication is still on the call stack."""
        ids = tuple(
            normalized
            for value in list(node_ids or [])
            if (normalized := normalize_node_id(value))
        )
        self._visible_scene_model_duplicate_count += 1
        self._visible_scene_model_duplicate_last_ids = ids
        self._record_mutation_counter("visible_model_duplicate_payloads", reason=",".join(ids))
        if self._visible_model_duplicate_resync_pending:
            return
        self._visible_model_duplicate_resync_pending = True
        QTimer.singleShot(0, self._resync_scene_after_duplicate_payloads)

    def _resync_scene_after_duplicate_payloads(self) -> None:
        self._visible_model_duplicate_resync_pending = False
        resync = getattr(self._scene_bridge, "resync_scene_payloads", None)
        if not callable(resync):
            return
        self._visible_scene_model_duplicate_resync_count += 1
        resync()

    def _sync_visible_model_node_delta(
        self,
        model: GraphCanvasVisibleModel,
        payloads: list[dict[str, Any]],
        *,
        added_node_ids: set[str],
        removed_node_ids: set[str],
        visibility_may_change: bool,
    ) -> int | None:
        if not added_node_ids and not removed_node_ids and not visibility_may_change:
            current_ids = {
                node_id
                for row in model.payloads()
                if isinstance(row, Mapping) and (node_id := normalize_node_id(row.get("node_id")))
            }
            visible_payloads: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for payload in payloads:
                node_id = normalize_node_id(payload.get("node_id"))
                if not node_id or node_id in seen_ids:
                    return None
                seen_ids.add(node_id)
                if node_id in current_ids:
                    visible_payloads.append(payload)
            return model.replace_existing_payloads(visible_payloads)
        if added_node_ids and not removed_node_ids:
            additions: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            can_append = True
            active_ids = self._active_virtualization_node_ids()
            for payload in payloads:
                node_id = normalize_node_id(payload.get("node_id"))
                if not node_id or node_id in seen_ids or node_id not in added_node_ids:
                    can_append = False
                    break
                seen_ids.add(node_id)
                if node_id not in active_ids and not self._payload_visible_in_current_query(payload):
                    can_append = False
                    break
                additions.append(payload)
            if can_append:
                appended = model.append_new_payloads(additions)
                if appended is not None:
                    return appended
        payload_by_id = _payload_by_node_id(payloads)
        if not payload_by_id and not removed_node_ids:
            return 0
        current_rows = model.payloads()
        active_ids = self._active_virtualization_node_ids()
        current_ids = {
            node_id
            for row in current_rows
            if isinstance(row, Mapping) and (node_id := normalize_node_id(row.get("node_id")))
        }
        next_rows: list[Any] = []
        changed_count = 0
        structural_change = False
        stable_replacements: list[dict[str, Any]] = []
        replaced_node_ids: set[str] = set()
        for row in current_rows:
            node_id = normalize_node_id(row.get("node_id")) if isinstance(row, Mapping) else ""
            if node_id and node_id in removed_node_ids:
                changed_count += 1
                structural_change = True
                continue
            replacement = payload_by_id.get(node_id)
            if replacement is None:
                next_rows.append(row)
                continue
            visible_after = node_id in active_ids or self._payload_visible_in_current_query(replacement)
            if not visible_after:
                if not visibility_may_change:
                    return None
                changed_count += 1
                structural_change = True
                continue
            next_rows.append(replacement)
            replaced_node_ids.add(node_id)
            if row != replacement:
                changed_count += 1
                stable_replacements.append(replacement)

        for node_id, payload in payload_by_id.items():
            if node_id in replaced_node_ids or node_id in current_ids:
                continue
            visible_after = node_id in active_ids or self._payload_visible_in_current_query(payload)
            if not visible_after:
                continue
            if node_id not in added_node_ids:
                return None
            next_rows.append(payload)
            changed_count += 1
            structural_change = True

        if not changed_count:
            return 0
        if not structural_change:
            return model.replace_existing_payloads(stable_replacements)
        model.sync_payloads(next_rows)
        return changed_count

    def _sync_visible_badge_nodes_model(self) -> None:
        self._visible_badge_nodes_model.sync_payloads(
            _badge_node_payloads(self._visible_nodes_model.payloads())
        )

    def _payload_visible_in_current_query(self, payload: dict[str, Any]) -> bool:
        visible_rect = self._visible_scene_query_rect
        if visible_rect is None:
            return True
        payload_rect = payload_scene_rect(payload)
        return payload_rect is not None and rects_intersect(payload_rect, visible_rect)

    def _handle_scene_selection_changed(self) -> None:
        selected_node_ids = _lookup_node_ids(self.selected_node_lookup)
        previous_selected_node_ids = self._visible_selection_node_ids
        self._visible_selection_node_ids = selected_node_ids
        if self._visible_scene_models_dirty or self._visible_scene_models_deferred:
            self._invalidate_visible_scene_models()
            return

        visible_node_ids = {
            node_id
            for model in (self._visible_nodes_model, self._visible_backdrop_nodes_model)
            for payload in model.payloads()
            if isinstance(payload, Mapping)
            and (node_id := normalize_node_id(payload.get("node_id")))
        }
        if not selected_node_ids.difference(previous_selected_node_ids).issubset(
            visible_node_ids
        ):
            self._invalidate_visible_scene_models()
            return

        deselected_node_ids = previous_selected_node_ids.difference(selected_node_ids)
        if not deselected_node_ids:
            return
        active_node_ids = self._active_virtualization_node_ids()
        changed = False
        for model in (self._visible_nodes_model, self._visible_backdrop_nodes_model):
            current_payloads = model.payloads()
            next_payloads = [
                payload
                for payload in current_payloads
                if not (
                    isinstance(payload, Mapping)
                    and (node_id := normalize_node_id(payload.get("node_id")))
                    and node_id in deselected_node_ids
                    and node_id not in active_node_ids
                    and not self._payload_visible_in_current_query(dict(payload))
                )
            ]
            if len(next_payloads) == len(current_payloads):
                continue
            model.sync_payloads(next_payloads)
            changed = True
        if changed:
            self._sync_visible_badge_nodes_model()
            self.visible_scene_models_changed.emit()

    def _invalidate_visible_scene_models(self) -> None:
        self._visible_scene_view_refresh_pending = False
        self._visible_scene_models_dirty = True
        self._visible_scene_models_deferred = False
        self._ensure_visible_scene_models_current(allow_deferred=True)
        self.visible_scene_models_changed.emit()

    def _handle_view_state_changed(self) -> None:
        lookahead_rect = self._lookahead_visible_scene_query_rect()
        if rect_contains(self._visible_scene_query_rect, lookahead_rect):
            self._visible_scene_model_skipped_view_change_count += 1
            return

        self._pending_visible_scene_query_rect = self._bucketed_visible_scene_query_rect()
        if rects_equal(self._pending_visible_scene_query_rect, self._visible_scene_query_rect):
            self._pending_visible_scene_query_rect = None
            self._visible_scene_model_skipped_view_change_count += 1
            return

        strict_viewport_rect = payload_scene_rect(self.visible_scene_rect_payload)
        if strict_viewport_rect is not None and not rect_contains(
            self._visible_scene_query_rect,
            strict_viewport_rect,
        ):
            self._invalidate_visible_scene_models()
            return

        if self._visible_scene_view_refresh_pending:
            return
        self._visible_scene_view_refresh_pending = True
        self._visible_scene_model_deferred_refresh_count += 1
        QTimer.singleShot(16, self._flush_pending_visible_scene_view_refresh)

    def _flush_pending_visible_scene_view_refresh(self) -> None:
        if not self._visible_scene_view_refresh_pending:
            return
        self._visible_scene_view_refresh_pending = False

        lookahead_rect = self._lookahead_visible_scene_query_rect()
        if rect_contains(self._visible_scene_query_rect, lookahead_rect):
            self._pending_visible_scene_query_rect = None
            self._visible_scene_model_skipped_view_change_count += 1
            return

        self._pending_visible_scene_query_rect = self._bucketed_visible_scene_query_rect()
        if rects_equal(self._pending_visible_scene_query_rect, self._visible_scene_query_rect):
            self._pending_visible_scene_query_rect = None
            self._visible_scene_model_skipped_view_change_count += 1
            return
        self._invalidate_visible_scene_models()

    def _ensure_visible_scene_models_current(
        self,
        *,
        allow_deferred: bool = False,
        force_exact: bool = False,
        force_refresh: bool = False,
    ) -> bool:
        if not self._visible_scene_models_dirty:
            if not force_refresh:
                return False
            if not force_exact:
                return False
            exact_rect = self._exact_visible_scene_query_rect()
            if rects_equal(self._visible_scene_query_rect, exact_rect):
                return False
        if self._visible_scene_models_deferred and not allow_deferred and not force_exact:
            return False
        query_rect = self._current_visible_scene_query_rect(force_exact=force_exact)
        self._visible_scene_models_dirty = False
        self._visible_scene_models_deferred = False
        self._visible_scene_query_rect = query_rect
        self._pending_visible_scene_query_rect = None
        if force_exact:
            self._visible_scene_model_exact_refresh_count += 1
        update_start = time.perf_counter()
        try:
            self._visible_nodes_model.sync_payloads(
                self._viewport_indexed_model("nodes_model", self._visible_node_index, visible_rect=query_rect)
            )
            self._sync_visible_badge_nodes_model()
            self._visible_backdrop_nodes_model.sync_payloads(
                self._viewport_indexed_model("backdrop_nodes_model", self._visible_backdrop_index, visible_rect=query_rect)
            )
        finally:
            self._record_mutation_timing_phase(
                "visible_node_model_update_ms",
                (time.perf_counter() - update_start) * 1000.0,
            )
        return True

    @pyqtSlot(result=bool)
    def force_visible_scene_models_exact(self) -> bool:
        self._visible_scene_view_refresh_pending = False
        refreshed = self._ensure_visible_scene_models_current(
            allow_deferred=True,
            force_exact=True,
            force_refresh=True,
        )
        if refreshed:
            self.visible_scene_models_changed.emit()
        return refreshed

    @pyqtProperty(QObject, notify=visible_scene_models_changed)
    def visible_nodes_model(self) -> GraphCanvasVisibleModel:
        self._ensure_visible_scene_models_current()
        return self._visible_nodes_model

    @pyqtProperty(QObject, notify=visible_scene_models_changed)
    def visible_backdrop_nodes_model(self) -> GraphCanvasVisibleModel:
        self._ensure_visible_scene_models_current()
        return self._visible_backdrop_nodes_model

    @pyqtProperty(QObject, notify=visible_scene_models_changed)
    def visible_badge_nodes_model(self) -> GraphCanvasVisibleModel:
        self._ensure_visible_scene_models_current()
        return self._visible_badge_nodes_model

    @pyqtProperty("QVariantList", notify=visible_scene_models_changed)
    def visible_nodes_payloads(self) -> list[Any]:
        self._ensure_visible_scene_models_current()
        return self._visible_nodes_model.payloads()

    @pyqtProperty("QVariantList", notify=visible_scene_models_changed)
    def visible_backdrop_nodes_payloads(self) -> list[Any]:
        self._ensure_visible_scene_models_current()
        return self._visible_backdrop_nodes_model.payloads()

    @pyqtSlot(str, result="QVariantMap")
    def visible_scene_node_payload(self, node_id: str) -> dict[str, Any]:
        normalized = normalize_node_id(node_id)
        if not normalized:
            return {}
        self._ensure_visible_scene_models_current()
        for payload in (*self._visible_nodes_model.payloads(), *self._visible_backdrop_nodes_model.payloads()):
            if isinstance(payload, Mapping) and normalize_node_id(payload.get("node_id")) == normalized:
                return dict(payload)
        return {}

    @pyqtProperty("QVariantMap", notify=visible_scene_models_changed)
    def visible_scene_model_diagnostics(self) -> dict[str, Any]:
        self._ensure_visible_scene_models_current()
        nodes = self._visible_node_index.diagnostics.as_payload()
        backdrops = self._visible_backdrop_index.diagnostics.as_payload()
        return {
            "nodes": nodes,
            "backdrops": backdrops,
            "full_count": int(nodes["full_count"]) + int(backdrops["full_count"]),
            "visible_count": int(nodes["visible_count"]) + int(backdrops["visible_count"]),
            "forced_visible_count": int(nodes["forced_visible_count"]) + int(backdrops["forced_visible_count"]),
            "query_ms": float(nodes["query_ms"]) + float(backdrops["query_ms"]),
            "query_count": int(nodes["query_count"]) + int(backdrops["query_count"]),
            "rebuild_ms": float(nodes["rebuild_ms"]) + float(backdrops["rebuild_ms"]),
            "cache_hits": int(nodes["cache_hits"]) + int(backdrops["cache_hits"]),
            "cache_misses": int(nodes["cache_misses"]) + int(backdrops["cache_misses"]),
            "dirty": self._visible_scene_models_dirty,
            "deferred": self._visible_scene_models_deferred,
            "view_refresh_pending": self._visible_scene_view_refresh_pending,
            "deferred_refresh_count": self._visible_scene_model_deferred_refresh_count,
            "skipped_view_change_count": self._visible_scene_model_skipped_view_change_count,
            "exact_refresh_count": self._visible_scene_model_exact_refresh_count,
            "delta_update_count": self._visible_scene_model_delta_update_count,
            "delta_fallback_count": self._visible_scene_model_delta_fallback_count,
            "delta_row_update_count": self._visible_scene_model_delta_row_update_count,
            "duplicate_payload_detection_count": self._visible_scene_model_duplicate_count,
            "duplicate_payload_last_node_ids": list(self._visible_scene_model_duplicate_last_ids),
            "duplicate_payload_resync_count": self._visible_scene_model_duplicate_resync_count,
            "query_rect": scene_rect_payload(self._visible_scene_query_rect),
            "pending_query_rect": scene_rect_payload(self._pending_visible_scene_query_rect),
        }

    @pyqtProperty("QVariantMap", notify=visible_scene_models_changed)
    def visible_model_active_node_lookup(self) -> dict[str, bool]:
        return {node_id: True for node_id in sorted(self._visible_model_active_node_ids)}

    @pyqtSlot("QVariantList")
    def set_visible_model_active_node_ids(self, node_ids: list[Any]) -> None:
        next_ids = _node_ids_from_values(node_ids)
        if next_ids == self._visible_model_active_node_ids:
            return
        self._visible_model_active_node_ids = next_ids
        self._invalidate_visible_scene_models()

    @pyqtSlot()
    def clear_visible_model_active_node_ids(self) -> None:
        if not self._visible_model_active_node_ids:
            return
        self._visible_model_active_node_ids.clear()
        self._invalidate_visible_scene_models()
