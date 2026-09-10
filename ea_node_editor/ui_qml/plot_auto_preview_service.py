"""Async plot auto-preview builds with a render-request cache.

Scene payload contributors publish only a cheap ``series_signature`` for plot
nodes with a connected tabular source (zero data I/O on the UI thread — see
``graph_scene_payload/kinds/plot.py``). This service watches scene payloads
for pending signatures, resolves the tabular ref and builds the decimated
render request on a private thread pool, stores the result in the process-wide
:class:`PlotRenderRequestCache`, and refreshes that node's payload so QML and
the plot host pick up the new ``render_revision``.

Workers never touch QObjects; results cross threads via queued signals only.
"""
from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal, pyqtSlot

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

_CACHE_LIMIT = 32
_CacheKey = tuple[str, str]


@dataclass(slots=True, frozen=True)
class PlotRenderRequestEntry:
    signature: str
    revision: int
    request_payload: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    error: str = ""
    source_node_id: str = ""


class PlotRenderRequestCache:
    """Thread-safe LRU cache of built plot render requests."""

    def __init__(self, *, limit: int = _CACHE_LIMIT) -> None:
        self._limit = max(1, int(limit))
        self._entries: dict[_CacheKey, PlotRenderRequestEntry] = {}
        self._revision_counter = 0
        self._lock = threading.Lock()

    def get(self, workspace_id: str, node_id: str) -> PlotRenderRequestEntry | None:
        key = (str(workspace_id), str(node_id))
        with self._lock:
            entry = self._entries.pop(key, None)
            if entry is not None:
                self._entries[key] = entry  # LRU touch
            return entry

    def store(
        self,
        workspace_id: str,
        node_id: str,
        *,
        signature: str,
        request_payload: Mapping[str, Any] | None = None,
        warnings: tuple[str, ...] = (),
        error: str = "",
        source_node_id: str = "",
    ) -> PlotRenderRequestEntry:
        key = (str(workspace_id), str(node_id))
        with self._lock:
            self._revision_counter += 1
            entry = PlotRenderRequestEntry(
                signature=str(signature),
                revision=self._revision_counter,
                request_payload=dict(request_payload or {}),
                warnings=tuple(warnings),
                error=str(error),
                source_node_id=str(source_node_id),
            )
            self._entries.pop(key, None)
            self._entries[key] = entry
            while len(self._entries) > self._limit:
                self._entries.pop(next(iter(self._entries)), None)
            return entry

    def discard(self, workspace_id: str, node_id: str) -> None:
        with self._lock:
            self._entries.pop((str(workspace_id), str(node_id)), None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_shared_cache_guard = threading.Lock()
_shared_cache: PlotRenderRequestCache | None = None


def shared_plot_render_request_cache() -> PlotRenderRequestCache:
    global _shared_cache
    with _shared_cache_guard:
        if _shared_cache is None:
            _shared_cache = PlotRenderRequestCache()
        return _shared_cache


def reset_shared_plot_render_request_cache() -> None:
    """Drop the process-wide cache (test isolation hook)."""

    global _shared_cache
    with _shared_cache_guard:
        _shared_cache = None


def build_plot_render_request_payload(
    *,
    node_type_id: str,
    properties: Mapping[str, Any],
    source_descriptor: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Resolve the tabular ref for ``source_descriptor`` and build the
    decimated render request. Heavy: run on a worker (or harness) thread.
    """

    from ea_node_editor.execution.plot_backend import plot_render_request_to_payload
    from ea_node_editor.nodes.builtins.plot.generic import build_generic_plot_render_request

    series_input = _resolve_series_input(source_descriptor)
    render_request, warnings = build_generic_plot_render_request(
        node_type_id=node_type_id,
        properties=properties,
        series_input=series_input,
    )
    return plot_render_request_to_payload(render_request), tuple(warnings)


def _resolve_series_input(descriptor: Mapping[str, Any]) -> Any:
    from ea_node_editor.addons.tabular_data.input_node import (
        _ref_with_node_metadata,
        tabular_load_options_from_node_properties,
    )
    from ea_node_editor.addons.tabular_data.loader_cache_service import (
        shared_tabular_loader_cache_service,
    )
    from ea_node_editor.runtime_contracts import ArrayDataRef, TabularDataRef
    from pathlib import Path

    kind = str(descriptor.get("kind", "") or "")
    input_descriptor = descriptor.get("input") if kind != "tabular_input" else descriptor
    if not isinstance(input_descriptor, Mapping):
        raise ValueError("plot auto preview source descriptor has no tabular input")
    properties = input_descriptor.get("properties")
    if not isinstance(properties, Mapping):
        raise ValueError("plot auto preview source descriptor has no input properties")
    resolved_path = str(input_descriptor.get("resolved_path", "") or "")
    if not resolved_path:
        raise ValueError("The tabular source path could not be resolved.")

    service = shared_tabular_loader_cache_service()
    options = tabular_load_options_from_node_properties(properties)
    ref = service.open_source(resolved_path, options)
    ref, _warning_codes = _ref_with_node_metadata(
        ref,
        source_path=Path(resolved_path),
        properties=properties,
    )

    if kind == "tabular_input":
        source_port_key = str(input_descriptor.get("source_port_key", "") or "")
        if source_port_key == "table_data" and isinstance(ref, TabularDataRef):
            return ref
        if source_port_key == "array_data" and isinstance(ref, ArrayDataRef):
            return ref
        raise ValueError(f"Connected tabular input port {source_port_key!r} does not provide this source.")

    node_properties = descriptor.get("properties")
    node_properties = dict(node_properties) if isinstance(node_properties, Mapping) else {}
    if kind == "table_filter":
        from ea_node_editor.addons.tabular_data.extraction_nodes import (
            _table_window_ref_from_properties,
        )

        return _table_window_ref_from_properties(ref, node_properties)
    if kind == "array_slice_2d":
        from ea_node_editor.addons.tabular_data.extraction_nodes import (
            _array_slice_ref_from_properties,
        )

        return _array_slice_ref_from_properties(ref, node_properties)
    raise ValueError(f"Unknown plot auto preview source kind: {kind!r}")


class _BuildSignals(QObject):
    finished = pyqtSignal(str, str, str, dict, tuple, str, str)
    """(workspace_id, node_id, signature, request_payload, warnings, error, source_node_id)"""


class _BuildRunnable(QRunnable):
    def __init__(
        self,
        *,
        signals: _BuildSignals,
        workspace_id: str,
        node_id: str,
        signature: str,
        node_type_id: str,
        properties: dict[str, Any],
        source_descriptor: dict[str, Any],
        source_node_id: str,
    ) -> None:
        super().__init__()
        self._signals = signals
        self._workspace_id = workspace_id
        self._node_id = node_id
        self._signature = signature
        self._node_type_id = node_type_id
        self._properties = properties
        self._source_descriptor = source_descriptor
        self._source_node_id = source_node_id

    def run(self) -> None:  # noqa: D102 - QRunnable contract
        try:
            request_payload, warnings = build_plot_render_request_payload(
                node_type_id=self._node_type_id,
                properties=self._properties,
                source_descriptor=self._source_descriptor,
            )
            error = ""
        except Exception as exc:  # noqa: BLE001 - surfaced as auto_preview_error
            request_payload, warnings, error = {}, (), str(exc)
        self._signals.finished.emit(
            self._workspace_id,
            self._node_id,
            self._signature,
            request_payload,
            tuple(warnings),
            error,
            self._source_node_id,
        )


class PlotAutoPreviewService(QObject):
    """Builds decimated plot auto-preview render requests off the UI thread."""

    render_request_ready = pyqtSignal(str, str, int)
    """(workspace_id, node_id, render_revision)"""

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        scene_bridge: "GraphSceneBridge | None" = None,
        cache: PlotRenderRequestCache | None = None,
        max_threads: int = 2,
    ) -> None:
        super().__init__(parent)
        self._scene_bridge = scene_bridge
        self._cache = cache or shared_plot_render_request_cache()
        self._thread_pool: QThreadPool | None = None
        self._max_threads = max(1, int(max_threads))
        self._signals = _BuildSignals(self)
        self._signals.finished.connect(self._on_build_finished)
        self._in_flight: dict[_CacheKey, str] = {}
        self._latest_signatures: dict[_CacheKey, str] = {}
        self._scan_queued = False
        self._shutdown = False
        if scene_bridge is not None:
            nodes_changed = getattr(scene_bridge, "nodes_changed", None)
            if nodes_changed is not None and hasattr(nodes_changed, "connect"):
                nodes_changed.connect(self._on_nodes_changed)

    def _ensure_thread_pool(self) -> QThreadPool | None:
        if self._shutdown:
            return None
        pool = self._thread_pool
        if pool is None:
            pool = QThreadPool(self)
            pool.setMaxThreadCount(self._max_threads)
            self._thread_pool = pool
        return pool

    @property
    def cache(self) -> PlotRenderRequestCache:
        return self._cache

    def shutdown(self) -> None:
        self._shutdown = True
        if self._thread_pool is not None:
            self._thread_pool.clear()
            self._thread_pool.waitForDone(2000)
        self._in_flight.clear()
        self._latest_signatures.clear()

    @pyqtSlot()
    def _on_nodes_changed(self) -> None:
        if self._shutdown or self._scan_queued:
            return
        self._scan_queued = True
        QTimer.singleShot(0, self._run_queued_scan)

    @pyqtSlot()
    def _run_queued_scan(self) -> None:
        self._scan_queued = False
        if self._shutdown:
            return
        self.scan_pending()

    def scan_pending(self) -> int:
        """Schedule builds for plot payloads whose signature has no cache entry.

        Returns the number of builds scheduled.
        """

        if self._shutdown or self._scene_bridge is None:
            return 0
        workspace_id = str(getattr(self._scene_bridge, "workspace_id", "") or "")
        if not workspace_id:
            return 0
        try:
            payloads = list(getattr(self._scene_bridge, "nodes_model", []) or [])
        except Exception:  # noqa: BLE001
            return 0
        scheduled = 0
        for payload in payloads:
            if not isinstance(payload, Mapping):
                continue
            plot_surface = payload.get("plot_surface")
            if not isinstance(plot_surface, Mapping):
                continue
            signature = str(plot_surface.get("series_signature", "") or "")
            if not signature or not plot_surface.get("auto_preview_pending"):
                continue
            node_id = str(payload.get("node_id", "") or "")
            if not node_id:
                continue
            if self.schedule_build(workspace_id, node_id, signature):
                scheduled += 1
        return scheduled

    def schedule_build(self, workspace_id: str, node_id: str, signature: str) -> bool:
        if self._shutdown:
            return False
        key = (workspace_id, node_id)
        entry = self._cache.get(workspace_id, node_id)
        if entry is not None and entry.signature == signature:
            return False
        if self._in_flight.get(key) == signature:
            return False
        snapshot = self._build_snapshot(node_id)
        if snapshot is None:
            return False
        node_type_id, properties, descriptor, source_node_id = snapshot
        self._latest_signatures[key] = signature
        self._in_flight[key] = signature
        runnable = _BuildRunnable(
            signals=self._signals,
            workspace_id=workspace_id,
            node_id=node_id,
            signature=signature,
            node_type_id=node_type_id,
            properties=properties,
            source_descriptor=descriptor,
            source_node_id=source_node_id,
        )
        pool = self._ensure_thread_pool()
        if pool is None:
            self._in_flight.pop(key, None)
            self._latest_signatures.pop(key, None)
            return False
        pool.start(runnable)
        return True

    def _build_snapshot(
        self,
        node_id: str,
    ) -> tuple[str, dict[str, Any], dict[str, Any], str] | None:
        """Capture everything the worker needs as plain data (UI thread)."""

        from ea_node_editor.ui_qml.graph_scene_payload.kinds.plot import (
            _node_properties_with_defaults,
            _plot_series_source_descriptor,
        )

        scene_context = getattr(self._scene_bridge, "_scene_context", None)
        workspace = scene_context.workspace_or_none() if scene_context is not None else None
        if workspace is None:
            return None
        node = workspace.nodes.get(node_id)
        if node is None:
            return None
        registry = getattr(scene_context, "registry", None)
        spec = registry.spec_or_none(str(node.type_id)) if registry is not None else None
        if spec is None:
            return None
        graph_theme_bridge = getattr(scene_context, "graph_theme_bridge", None)
        descriptor = _plot_series_source_descriptor(
            node=node,
            workspace=workspace,
            graph_theme_bridge=graph_theme_bridge,
        )
        if descriptor is None:
            return None
        properties = _node_properties_with_defaults(node=node, spec=spec)
        return (
            str(node.type_id),
            copy.deepcopy(properties),
            copy.deepcopy(descriptor),
            str(descriptor.get("source_node_id", "") or ""),
        )

    @pyqtSlot(str, str, str, dict, tuple, str, str)
    def _on_build_finished(
        self,
        workspace_id: str,
        node_id: str,
        signature: str,
        request_payload: dict,
        warnings: tuple,
        error: str,
        source_node_id: str,
    ) -> None:
        key = (workspace_id, node_id)
        if self._in_flight.get(key) == signature:
            self._in_flight.pop(key, None)
        if self._shutdown:
            return
        if self._latest_signatures.get(key) != signature:
            return
        entry = self._cache.store(
            workspace_id,
            node_id,
            signature=signature,
            request_payload=request_payload,
            warnings=tuple(warnings),
            error=error,
            source_node_id=source_node_id,
        )
        self._refresh_node_payload(node_id)
        self.render_request_ready.emit(workspace_id, node_id, entry.revision)

    def _refresh_node_payload(self, node_id: str) -> None:
        scene_context = getattr(self._scene_bridge, "_scene_context", None)
        if scene_context is None:
            return
        publish = getattr(scene_context, "publish_node_title_payload_delta", None)
        if callable(publish):
            publish(node_id, publication_path="plot_auto_preview_ready")


__all__ = [
    "PlotAutoPreviewService",
    "PlotRenderRequestCache",
    "PlotRenderRequestEntry",
    "build_plot_render_request_payload",
    "reset_shared_plot_render_request_cache",
    "shared_plot_render_request_cache",
]
