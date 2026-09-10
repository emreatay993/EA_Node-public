from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

DEFAULT_NODE_RENDER_ACTIVATION_PADDING_PX = 240.0
MAX_NODE_RENDER_ACTIVATION_PADDING_PX = 640.0
DEFAULT_VIEWPORT_INDEX_CELL_SIZE = 512.0
DEFAULT_VIEWPORT_MODEL_HYSTERESIS_PADDING_PX = 160.0
DEFAULT_VIEWPORT_MODEL_BUCKET_PX = 128.0

SceneRect = tuple[float, float, float, float]


def normalize_node_id(value: object) -> str:
    return str(value or "").strip()


def payload_float(payload: dict[str, Any], key: str, fallback: float) -> float:
    try:
        value = float(payload.get(key, fallback))
    except (TypeError, ValueError):
        return fallback
    return value if math.isfinite(value) else fallback


def payload_scene_rect(payload: object) -> SceneRect | None:
    if not isinstance(payload, dict):
        return None
    x = payload_float(payload, "x", 0.0)
    y = payload_float(payload, "y", 0.0)
    width = max(1.0, payload_float(payload, "width", 1.0))
    height = max(1.0, payload_float(payload, "height", 1.0))
    return x, y, width, height


def visible_scene_rect(payload: object) -> SceneRect | None:
    if not isinstance(payload, dict):
        return None
    width = payload_float(payload, "width", 0.0)
    height = payload_float(payload, "height", 0.0)
    if width <= 0.0 or height <= 0.0:
        return None
    return (
        payload_float(payload, "x", 0.0),
        payload_float(payload, "y", 0.0),
        width,
        height,
    )


def scene_rect_payload(rect: SceneRect | None) -> dict[str, float]:
    if rect is None:
        return {}
    x, y, width, height = rect
    return {
        "x": float(x),
        "y": float(y),
        "width": float(max(0.0, width)),
        "height": float(max(0.0, height)),
    }


def inflate_scene_rect(
    rect: SceneRect,
    horizontal_padding: float,
    vertical_padding: float | None = None,
) -> SceneRect:
    resolved_horizontal_padding = float(horizontal_padding)
    if not math.isfinite(resolved_horizontal_padding) or resolved_horizontal_padding < 0.0:
        resolved_horizontal_padding = 0.0
    resolved_vertical_padding = (
        resolved_horizontal_padding if vertical_padding is None else float(vertical_padding)
    )
    if not math.isfinite(resolved_vertical_padding) or resolved_vertical_padding < 0.0:
        resolved_vertical_padding = 0.0
    x, y, width, height = rect
    return (
        x - resolved_horizontal_padding,
        y - resolved_vertical_padding,
        width + (resolved_horizontal_padding * 2.0),
        height + (resolved_vertical_padding * 2.0),
    )


def rect_contains(outer: SceneRect | None, inner: SceneRect | None, *, epsilon: float = 1e-6) -> bool:
    if outer is None or inner is None:
        return outer is None and inner is None
    outer_x, outer_y, outer_width, outer_height = outer
    inner_x, inner_y, inner_width, inner_height = inner
    return (
        inner_x >= outer_x - epsilon
        and inner_y >= outer_y - epsilon
        and inner_x + inner_width <= outer_x + outer_width + epsilon
        and inner_y + inner_height <= outer_y + outer_height + epsilon
    )


def rects_equal(first: SceneRect | None, second: SceneRect | None, *, epsilon: float = 1e-6) -> bool:
    if first is None or second is None:
        return first is None and second is None
    return all(abs(a - b) <= epsilon for a, b in zip(first, second, strict=True))


def scene_padding_for_viewport_pixels(padding_px: float, zoom: float) -> float:
    resolved_zoom = float(zoom)
    if not math.isfinite(resolved_zoom) or resolved_zoom <= 0.0001:
        resolved_zoom = 1.0
    resolved_padding = float(padding_px)
    if not math.isfinite(resolved_padding) or resolved_padding < 0.0:
        resolved_padding = 0.0
    return resolved_padding / resolved_zoom


def bucket_scene_rect(rect: SceneRect | None, bucket_scene_size: float) -> SceneRect | None:
    if rect is None:
        return None
    bucket = float(bucket_scene_size)
    if not math.isfinite(bucket) or bucket <= 0.0001:
        return rect

    x, y, width, height = rect
    left = math.floor(x / bucket) * bucket
    top = math.floor(y / bucket) * bucket
    right = math.ceil((x + max(0.0, width)) / bucket) * bucket
    bottom = math.ceil((y + max(0.0, height)) / bucket) * bucket
    return (
        left,
        top,
        max(0.0, right - left),
        max(0.0, bottom - top),
    )


def expanded_visible_scene_rect(
    payload: object,
    *,
    zoom: float,
) -> SceneRect | None:
    rect = visible_scene_rect(payload)
    if rect is None:
        return None
    resolved_zoom = float(zoom)
    if not math.isfinite(resolved_zoom) or resolved_zoom <= 0.0001:
        resolved_zoom = 1.0
    horizontal_padding_px = min(
        MAX_NODE_RENDER_ACTIVATION_PADDING_PX,
        max(DEFAULT_NODE_RENDER_ACTIVATION_PADDING_PX, rect[2] * resolved_zoom * 0.5),
    )
    vertical_padding_px = min(
        MAX_NODE_RENDER_ACTIVATION_PADDING_PX,
        max(DEFAULT_NODE_RENDER_ACTIVATION_PADDING_PX, rect[3] * resolved_zoom * 0.5),
    )
    return inflate_scene_rect(
        rect,
        scene_padding_for_viewport_pixels(horizontal_padding_px, resolved_zoom),
        scene_padding_for_viewport_pixels(vertical_padding_px, resolved_zoom),
    )


def bucketed_hysteresis_visible_scene_rect(
    payload: object,
    *,
    zoom: float,
    hysteresis_padding_px: float = DEFAULT_VIEWPORT_MODEL_HYSTERESIS_PADDING_PX,
    bucket_px: float = DEFAULT_VIEWPORT_MODEL_BUCKET_PX,
) -> SceneRect | None:
    exact_rect = expanded_visible_scene_rect(payload, zoom=zoom)
    if exact_rect is None:
        return None
    hysteresis_padding = scene_padding_for_viewport_pixels(hysteresis_padding_px, zoom)
    bucket_size = scene_padding_for_viewport_pixels(bucket_px, zoom)
    return bucket_scene_rect(inflate_scene_rect(exact_rect, hysteresis_padding), bucket_size)


def lookahead_visible_scene_rect(
    payload: object,
    *,
    zoom: float,
    lookahead_px: float = DEFAULT_VIEWPORT_MODEL_BUCKET_PX,
) -> SceneRect | None:
    rect = visible_scene_rect(payload)
    if rect is None:
        return None
    lookahead_padding = scene_padding_for_viewport_pixels(lookahead_px, zoom)
    return inflate_scene_rect(rect, lookahead_padding)


def rects_intersect(first: SceneRect, second: SceneRect) -> bool:
    first_x, first_y, first_width, first_height = first
    second_x, second_y, second_width, second_height = second
    return (
        first_x < second_x + second_width
        and first_x + first_width > second_x
        and first_y < second_y + second_height
        and first_y + first_height > second_y
    )


@dataclass(slots=True)
class _IndexedPayload:
    order: int
    node_id: str
    rect: SceneRect | None
    payload: Any


@dataclass(slots=True)
class ViewportIndexDiagnostics:
    full_count: int = 0
    visible_count: int = 0
    forced_visible_count: int = 0
    query_count: int = 0
    rebuild_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    query_ms: float = 0.0
    rebuild_ms: float = 0.0
    cache_hit: bool = False
    cache_miss: bool = False

    def as_payload(self) -> dict[str, Any]:
        return {
            "full_count": self.full_count,
            "visible_count": self.visible_count,
            "forced_visible_count": self.forced_visible_count,
            "query_count": self.query_count,
            "rebuild_count": self.rebuild_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "query_ms": self.query_ms,
            "rebuild_ms": self.rebuild_ms,
            "cache_hit": self.cache_hit,
            "cache_miss": self.cache_miss,
        }


@dataclass(slots=True)
class GraphCanvasViewportIndex:
    cell_size: float = DEFAULT_VIEWPORT_INDEX_CELL_SIZE
    _workspace_id: str = ""
    _model_revision: int = -1
    _records: list[_IndexedPayload] = field(default_factory=list)
    _records_by_node_id: dict[str, _IndexedPayload] = field(default_factory=dict)
    _cells: dict[tuple[int, int], list[int]] = field(default_factory=dict)
    _diagnostics: ViewportIndexDiagnostics = field(default_factory=ViewportIndexDiagnostics)

    @property
    def diagnostics(self) -> ViewportIndexDiagnostics:
        return self._diagnostics

    def reset(self) -> None:
        self._workspace_id = ""
        self._model_revision = -1
        self._records.clear()
        self._records_by_node_id.clear()
        self._cells.clear()
        self._diagnostics = ViewportIndexDiagnostics()

    def query(
        self,
        *,
        workspace_id: str,
        model_revision: int,
        source_loader: Callable[[], Iterable[Any]],
        visible_rect: SceneRect | None,
        active_node_ids: set[str],
    ) -> list[Any]:
        started = time.perf_counter()
        rebuilt = False
        if self._workspace_id != workspace_id or self._model_revision != model_revision:
            rebuild_started = time.perf_counter()
            self._rebuild(workspace_id, model_revision, source_loader())
            self._diagnostics.rebuild_ms = _elapsed_ms(rebuild_started)
            self._diagnostics.rebuild_count += 1
            self._diagnostics.cache_misses += 1
            rebuilt = True
        else:
            self._diagnostics.rebuild_ms = 0.0
            self._diagnostics.cache_hits += 1

        self._diagnostics.cache_hit = not rebuilt
        self._diagnostics.cache_miss = rebuilt
        self._diagnostics.query_count += 1
        visible_records = self._visible_records(visible_rect, active_node_ids)
        self._diagnostics.full_count = len(self._records)
        self._diagnostics.visible_count = len(visible_records)
        self._diagnostics.forced_visible_count = _forced_visible_count(
            visible_records,
            visible_rect,
            active_node_ids,
        )
        self._diagnostics.query_ms = _elapsed_ms(started)
        return [record.payload for record in visible_records]

    def _rebuild(self, workspace_id: str, model_revision: int, source: Iterable[Any]) -> None:
        self._workspace_id = workspace_id
        self._model_revision = model_revision
        self._records = []
        self._records_by_node_id = {}
        self._cells = {}
        for order, payload in enumerate(source):
            node_id = normalize_node_id(payload.get("node_id")) if isinstance(payload, dict) else ""
            record = _IndexedPayload(
                order=order,
                node_id=node_id,
                rect=payload_scene_rect(payload),
                payload=payload,
            )
            self._records.append(record)
            if node_id:
                self._records_by_node_id[node_id] = record
            if record.rect is None:
                continue
            for key in self._cell_keys(record.rect):
                self._cells.setdefault(key, []).append(order)

    def _visible_records(
        self,
        visible_rect: SceneRect | None,
        active_node_ids: set[str],
    ) -> list[_IndexedPayload]:
        if visible_rect is None:
            return list(self._records)

        candidate_orders: set[int] = set()
        for key in self._cell_keys(visible_rect):
            candidate_orders.update(self._cells.get(key, ()))
        for node_id in active_node_ids:
            record = self._records_by_node_id.get(node_id)
            if record is not None:
                candidate_orders.add(record.order)

        visible: list[_IndexedPayload] = []
        for order in sorted(candidate_orders):
            record = self._records[order]
            if record.node_id and record.node_id in active_node_ids:
                visible.append(record)
            elif record.rect is not None and rects_intersect(record.rect, visible_rect):
                visible.append(record)
        return visible

    def _cell_keys(self, rect: SceneRect) -> Iterable[tuple[int, int]]:
        x, y, width, height = rect
        cell_size = max(1.0, float(self.cell_size))
        min_x = math.floor(x / cell_size)
        max_x = math.floor((x + max(0.0, width)) / cell_size)
        min_y = math.floor(y / cell_size)
        max_y = math.floor((y + max(0.0, height)) / cell_size)
        for cell_x in range(min_x, max_x + 1):
            for cell_y in range(min_y, max_y + 1):
                yield cell_x, cell_y


def _forced_visible_count(
    records: list[_IndexedPayload],
    visible_rect: SceneRect | None,
    active_node_ids: set[str],
) -> int:
    if visible_rect is None or not active_node_ids:
        return 0
    count = 0
    for record in records:
        if not record.node_id or record.node_id not in active_node_ids:
            continue
        if record.rect is None or not rects_intersect(record.rect, visible_rect):
            count += 1
    return count


def _elapsed_ms(started: float) -> float:
    return max(0.0, (time.perf_counter() - started) * 1000.0)


__all__ = [
    "DEFAULT_NODE_RENDER_ACTIVATION_PADDING_PX",
    "MAX_NODE_RENDER_ACTIVATION_PADDING_PX",
    "DEFAULT_VIEWPORT_MODEL_BUCKET_PX",
    "DEFAULT_VIEWPORT_MODEL_HYSTERESIS_PADDING_PX",
    "GraphCanvasViewportIndex",
    "SceneRect",
    "bucket_scene_rect",
    "bucketed_hysteresis_visible_scene_rect",
    "expanded_visible_scene_rect",
    "inflate_scene_rect",
    "lookahead_visible_scene_rect",
    "normalize_node_id",
    "payload_scene_rect",
    "rect_contains",
    "rects_equal",
    "rects_intersect",
    "scene_padding_for_viewport_pixels",
    "scene_rect_payload",
    "visible_scene_rect",
]
