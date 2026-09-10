from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import Mock, patch

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.plot.generic import TABULAR_PLOT_MAX_POINTS_PER_SERIES
from ea_node_editor.ui_qml.graph_scene_payload.builder import GraphScenePayloadBuilder
from ea_node_editor.ui_qml import plot_auto_preview_service as preview_module
from ea_node_editor.ui_qml.plot_auto_preview_service import (
    PlotAutoPreviewService,
    PlotRenderRequestCache,
    shared_plot_render_request_cache,
)


class _SceneContextStub:
    def __init__(self, model: GraphModel, registry, workspace_id: str) -> None:  # noqa: ANN001
        self._model = model
        self.registry = registry
        self._workspace_id = workspace_id
        self.graph_theme_bridge = None
        self.published_node_ids: list[str] = []

    def workspace_or_none(self):  # noqa: ANN201
        return self._model.project.workspaces.get(self._workspace_id)

    def publish_node_title_payload_delta(self, node_id: str, *, publication_path: str = "") -> bool:
        self.published_node_ids.append(node_id)
        return True


class _SceneBridgeStub(QObject):
    nodes_changed = pyqtSignal()

    def __init__(self, model: GraphModel, registry, workspace_id: str) -> None:  # noqa: ANN001
        super().__init__()
        self.workspace_id = workspace_id
        self._model = model
        self._registry = registry
        self._scene_context = _SceneContextStub(model, registry, workspace_id)
        self.nodes_model: list[dict] = []

    def rebuild(self) -> None:
        nodes_payload, _minimap, _edges = GraphScenePayloadBuilder().rebuild_models(
            model=self._model,
            registry=self._registry,
            workspace_id=self.workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )
        self.nodes_model = nodes_payload


def _workflow(tmp_path: Path, *, rows: int = 9000, source_port: str = "table_data"):
    source = tmp_path / "wave.csv"
    lines = ["time,value"]
    lines.extend(f"{index},{(index % 50) * 0.5}" for index in range(rows))
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")

    registry = build_default_registry()
    model = GraphModel()
    workspace_id = model.active_workspace.workspace_id
    tabular = model.add_node(
        workspace_id, "tabular.input", "Tabular", 0.0, 0.0, properties={"path": str(source)}
    )
    plot = model.add_node(
        workspace_id,
        "plot.scatter",
        "Line Plot",
        300.0,
        0.0,
        properties={"tabular_mapping": {"x": "time", "y": ["value"]}},
    )
    model.add_edge(workspace_id, tabular.node_id, source_port, plot.node_id, "series")
    return registry, model, workspace_id, plot.node_id


def _wait_for(condition, *, timeout_s: float = 20.0) -> bool:  # noqa: ANN001
    app = QApplication.instance()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_worker_pool_is_lazy_reused_and_preserves_max_threads() -> None:
    pool = Mock()
    with patch.object(preview_module, "QThreadPool", return_value=pool) as pool_factory:
        service = PlotAutoPreviewService(scene_bridge=None, cache=PlotRenderRequestCache(), max_threads=3)
        assert service._thread_pool is None  # noqa: SLF001
        assert service.schedule_build("ws", "missing", "sig-0") is False
        pool_factory.assert_not_called()

        snapshot = ("plot.scatter", {}, {"source_node_id": "source"}, "source")
        with patch.object(service, "_build_snapshot", return_value=snapshot):
            assert service.schedule_build("ws", "plot-1", "sig-1") is True
            assert service.schedule_build("ws", "plot-1", "sig-1") is False
            assert service.schedule_build("ws", "plot-2", "sig-2") is True

        pool_factory.assert_called_once_with(service)
        pool.setMaxThreadCount.assert_called_once_with(3)
        assert pool.start.call_count == 2
        service.shutdown()
        pool.clear.assert_called_once_with()
        pool.waitForDone.assert_called_once_with(2000)


def test_shutdown_before_worker_pool_initialization_allocates_nothing() -> None:
    with patch.object(preview_module, "QThreadPool") as pool_factory:
        service = PlotAutoPreviewService(scene_bridge=None, cache=PlotRenderRequestCache())
        service.shutdown()
        assert service.schedule_build("ws", "plot", "sig") is False

    pool_factory.assert_not_called()


def test_pending_signature_builds_and_refreshes_payload(tmp_path: Path) -> None:
    registry, model, workspace_id, plot_node_id = _workflow(tmp_path)
    bridge = _SceneBridgeStub(model, registry, workspace_id)
    cache = shared_plot_render_request_cache()
    service = PlotAutoPreviewService(scene_bridge=bridge, cache=cache)
    try:
        bridge.rebuild()
        payload = next(item for item in bridge.nodes_model if item["node_id"] == plot_node_id)
        assert payload["plot_surface"]["auto_preview_pending"] is True
        signature = payload["plot_surface"]["series_signature"]

        scheduled = service.scan_pending()
        assert scheduled == 1
        assert _wait_for(lambda: cache.get(workspace_id, plot_node_id) is not None)

        entry = cache.get(workspace_id, plot_node_id)
        assert entry.signature == signature
        assert entry.error == ""
        assert entry.revision > 0
        series = entry.request_payload["series"]
        assert series and len(series[0]["y"]) <= TABULAR_PLOT_MAX_POINTS_PER_SERIES
        assert series[0]["decimation"]["original_rows"] == 9000
        assert bridge._scene_context.published_node_ids == [plot_node_id]

        # A second scan with an unchanged signature schedules nothing.
        assert service.scan_pending() == 0
    finally:
        service.shutdown()


def test_build_error_is_cached_and_published(tmp_path: Path) -> None:
    registry, model, workspace_id, plot_node_id = _workflow(tmp_path, rows=10)
    workspace = model.project.workspaces[workspace_id]
    workspace.nodes[plot_node_id].properties["tabular_mapping"] = {"x": "time", "y": ["missing"]}

    bridge = _SceneBridgeStub(model, registry, workspace_id)
    cache = shared_plot_render_request_cache()
    service = PlotAutoPreviewService(scene_bridge=bridge, cache=cache)
    try:
        bridge.rebuild()
        assert service.scan_pending() == 1
        assert _wait_for(lambda: cache.get(workspace_id, plot_node_id) is not None)
        entry = cache.get(workspace_id, plot_node_id)
        assert "missing" in entry.error

        bridge.rebuild()
        payload = next(item for item in bridge.nodes_model if item["node_id"] == plot_node_id)
        assert "missing" in payload["plot_surface"]["auto_preview_error"]
        assert payload["plot_surface"]["render_revision"] == 0
    finally:
        service.shutdown()


def test_build_error_when_tabular_input_output_port_does_not_match_source(tmp_path: Path) -> None:
    registry, model, workspace_id, plot_node_id = _workflow(tmp_path, rows=10, source_port="array_data")
    bridge = _SceneBridgeStub(model, registry, workspace_id)
    cache = PlotRenderRequestCache()
    service = PlotAutoPreviewService(scene_bridge=bridge, cache=cache)
    try:
        bridge.rebuild()
        assert service.scan_pending() == 1
        assert _wait_for(lambda: cache.get(workspace_id, plot_node_id) is not None)
        entry = cache.get(workspace_id, plot_node_id)
        assert entry is not None
        assert "array_data" in entry.error
    finally:
        service.shutdown()


def test_stale_build_completion_does_not_replace_latest_signature(tmp_path: Path) -> None:
    registry, model, workspace_id, plot_node_id = _workflow(tmp_path, rows=10)
    bridge = _SceneBridgeStub(model, registry, workspace_id)
    cache = PlotRenderRequestCache()
    service = PlotAutoPreviewService(scene_bridge=bridge, cache=cache)
    try:
        key = (workspace_id, plot_node_id)
        service._latest_signatures[key] = "sig-b"  # noqa: SLF001
        service._in_flight[key] = "sig-b"  # noqa: SLF001

        service._on_build_finished(  # noqa: SLF001
            workspace_id,
            plot_node_id,
            "sig-b",
            {"plot_type": "line", "series": [{"label": "b", "x": [0], "y": [2]}]},
            (),
            "",
            "source",
        )
        service._on_build_finished(  # noqa: SLF001
            workspace_id,
            plot_node_id,
            "sig-a",
            {"plot_type": "line", "series": [{"label": "a", "x": [0], "y": [1]}]},
            (),
            "",
            "source",
        )

        entry = cache.get(workspace_id, plot_node_id)
        assert entry is not None
        assert entry.signature == "sig-b"
        assert entry.request_payload["series"][0]["label"] == "b"
        assert bridge._scene_context.published_node_ids == [plot_node_id]
    finally:
        service.shutdown()


def test_cache_is_lru_bounded() -> None:
    cache = PlotRenderRequestCache(limit=2)
    cache.store("ws", "a", signature="s1")
    cache.store("ws", "b", signature="s2")
    cache.store("ws", "c", signature="s3")
    assert cache.get("ws", "a") is None
    assert cache.get("ws", "b") is not None
    assert cache.get("ws", "c") is not None
