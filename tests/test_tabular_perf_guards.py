"""Regression guards for the gigabyte-tabular performance contract.

These pin the mechanisms that made the 30 MB benchmark unusable (full-table
materialization per scene rebuild, re-scan/re-conversion per call, unbounded
plot series):

* a repeated scene payload build must not re-scan or re-convert the source,
* plot auto-previews never exceed the decimation budget,
* managed-cache reads never stream the text source through the python reader.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import ea_node_editor.addons.tabular_data.loader_cache_service as loader_module
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.plot.generic import TABULAR_PLOT_MAX_POINTS_PER_SERIES
from ea_node_editor.ui_qml.graph_scene_payload.builder import GraphScenePayloadBuilder
from scripts.verify_tabular_perf import _benchmark_node_ids

_ROWS = 12_000


def test_perf_harness_selects_only_registered_generic_plot_nodes() -> None:
    nodes = {
        "tabular": SimpleNamespace(type_id="tabular.input"),
        "signal": SimpleNamespace(type_id="plot.signal"),
        "scatter": SimpleNamespace(type_id="plot.scatter"),
    }
    assert _benchmark_node_ids(nodes) == ("tabular", "scatter")


@pytest.fixture()
def plot_workflow(tmp_path: Path):
    source = tmp_path / "wave.csv"
    lines = ["time,value"]
    lines.extend(f"{index},{(index % 100) * 0.25}" for index in range(_ROWS))
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
        "Scatter Plot",
        300.0,
        0.0,
        properties={"tabular_mapping": {"x": "time", "y": ["value"]}},
    )
    model.add_edge(workspace_id, tabular.node_id, "table_data", plot.node_id, "series")
    return registry, model, workspace_id, plot.node_id


class _IoCounters:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.uncached_scans = 0
        self.conversions = 0
        self.python_text_reads = 0
        service_cls = loader_module.TabularLoaderCacheService
        counters = self

        original_scan = service_cls._scan_uncached
        original_convert = service_cls._write_parquet_cache
        original_iter = service_cls._iter_text_records

        def counted_scan(self, *args, **kwargs):  # noqa: ANN001
            counters.uncached_scans += 1
            return original_scan(self, *args, **kwargs)

        def counted_convert(self, *args, **kwargs):  # noqa: ANN001
            counters.conversions += 1
            return original_convert(self, *args, **kwargs)

        def counted_iter(self, *args, **kwargs):  # noqa: ANN001
            counters.python_text_reads += 1
            return original_iter(self, *args, **kwargs)

        monkeypatch.setattr(service_cls, "_scan_uncached", counted_scan)
        monkeypatch.setattr(service_cls, "_write_parquet_cache", counted_convert)
        monkeypatch.setattr(service_cls, "_iter_text_records", counted_iter)

    def reset(self) -> None:
        self.uncached_scans = 0
        self.conversions = 0
        self.python_text_reads = 0


def _build(registry, model, workspace_id):  # noqa: ANN001
    return GraphScenePayloadBuilder().rebuild_models(
        model=model,
        registry=registry,
        workspace_id=workspace_id,
        scope_path=(),
        graph_theme_bridge=None,
    )


def test_payload_builds_perform_no_source_io_at_all(
    plot_workflow,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, model, workspace_id, _plot_node_id = plot_workflow
    counters = _IoCounters(monkeypatch)

    _build(registry, model, workspace_id)
    # The tabular input node's port-kind resolution reads the header once
    # (bounded, no row scan); nothing converts or streams rows.
    assert counters.uncached_scans <= 1
    assert counters.conversions == 0
    assert counters.python_text_reads == 0

    counters.reset()
    _build(registry, model, workspace_id)

    # Steady-state rebuilds are pure metadata: zero tabular I/O of any kind.
    assert counters.uncached_scans == 0
    assert counters.conversions == 0
    assert counters.python_text_reads == 0


def test_async_auto_preview_build_converts_once_and_respects_budget(
    plot_workflow,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ea_node_editor.ui_qml.graph_scene_payload.kinds.plot import (
        _plot_series_source_descriptor,
    )
    from ea_node_editor.ui_qml.plot_auto_preview_service import (
        build_plot_render_request_payload,
        shared_plot_render_request_cache,
    )

    registry, model, workspace_id, plot_node_id = plot_workflow
    counters = _IoCounters(monkeypatch)
    nodes_payload, _minimap, _edges = _build(registry, model, workspace_id)
    payload = next(item for item in nodes_payload if item["node_id"] == plot_node_id)
    assert payload["plot_surface"]["auto_preview_pending"] is True
    signature = payload["plot_surface"]["series_signature"]

    workspace = model.project.workspaces[workspace_id]
    descriptor = _plot_series_source_descriptor(
        node=workspace.nodes[plot_node_id],
        workspace=workspace,
        graph_theme_bridge=None,
    )
    request_payload, _warnings = build_plot_render_request_payload(
        node_type_id="plot.scatter",
        properties=dict(workspace.nodes[plot_node_id].properties),
        source_descriptor=descriptor,
    )
    assert counters.conversions == 1

    series = request_payload["series"]
    assert series
    for item in series:
        assert len(item["y"]) <= TABULAR_PLOT_MAX_POINTS_PER_SERIES
        assert item["decimation"]["original_rows"] == _ROWS
        assert item["decimation"]["points"] == len(item["y"])

    # Once cached, rebuilding publishes the ready revision without new I/O.
    shared_plot_render_request_cache().store(
        workspace_id, plot_node_id, signature=signature, request_payload=request_payload
    )
    counters.reset()
    nodes_payload, _minimap, _edges = _build(registry, model, workspace_id)
    refreshed = next(item for item in nodes_payload if item["node_id"] == plot_node_id)
    assert refreshed["plot_surface"]["auto_preview_active"] is True
    assert refreshed["plot_surface"]["render_revision"] > 0
    assert counters.uncached_scans == 0
    assert counters.conversions == 0
    assert counters.python_text_reads == 0


def test_managed_cache_reads_never_use_python_text_reader(
    plot_workflow,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, model, workspace_id, _plot_node_id = plot_workflow
    counters = _IoCounters(monkeypatch)

    _build(registry, model, workspace_id)

    # The conversion itself streams arrow blocks; the python csv reader must
    # stay untouched on managed-cache reads.
    assert counters.python_text_reads == 0
