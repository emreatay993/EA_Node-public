# Purpose: Prove scientific Signal Plot examples, process pipelines and reuse budgets.
# Map: feature_routes/plotter_nodes.md
# Tests: tests/test_signal_plot_scientific_integration.py
from __future__ import annotations

import json

import numpy as np
import pytest

from ea_node_editor.execution.prepared_execution import (
    MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES,
    PreparedAction,
)
from ea_node_editor.execution.runtime import CorexRuntime
from ea_node_editor.execution.runtime_requests import ExecutionRequest
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import ImageValue
from ea_node_editor.runtime_contracts.scientific_values import ArrayValue
from scripts.benchmark_signal_plot import (
    _measure,
    scientific_benchmark,
    settled_item,
    wait_for_runtime_idle,
)
from scripts.generate_signal_plot_scientific_example import (
    add_signal_chain,
    generate_example,
)


@pytest.mark.parametrize("kind", ["numpy", "pandas"])
@pytest.mark.parametrize("backend", ["process", "runtime"])
def test_native_scientific_signal_pipeline_repeats_with_complete_source(kind, backend):
    report = scientific_benchmark(kind, 4100, backend=backend)
    assert len(report["runs"]) == 2
    assert all(
        run["full_source_verified"] and max(run["rendered_points"]) <= 4000
        for run in report["runs"]
    )


@pytest.mark.parametrize("interpretation,value", [("auto", "1\n2\n3\n7"), ("number", "1\n2\n\n7")])
def test_panel_interpretation_signal_plot_media_pipeline(interpretation, value):
    registry = build_default_registry(include_public_plugins=False)
    model = GraphModel()
    workspace_id = model.active_workspace.workspace_id
    mutation = model.validated_mutations(workspace_id, registry)
    panel = mutation.add_node(type_id="data.panel", title="Panel", x=0, y=0,
        properties={"mode": 1, "value": value, "interpretation": interpretation})
    plot = mutation.add_node(type_id="plot.signal", title="Signal", x=300, y=0)
    media = mutation.add_node(type_id="media.panel", title="Media", x=600, y=0)
    mutation.add_edge(source_node_id=panel.node_id, source_port_key="output",
        target_node_id=plot.node_id, target_port_key="values")
    mutation.add_edge(source_node_id=plot.node_id, source_port_key="image",
        target_node_id=media.node_id, target_port_key="source")
    runtime = CorexRuntime(registry=registry)
    try:
        result = runtime.run(ExecutionRequest(workspace_id=workspace_id,
            runtime_snapshot=build_runtime_snapshot(model.project, workspace_id=workspace_id, registry=registry)), timeout=60)
        assert result.status == "completed", (result.error, result.traceback)
        settled = {event["node_id"]: event for event in result.events if event.get("type") == "node_settled"}
        assert isinstance(settled_item(settled[media.node_id], "_surface_source", registry.data_types), ImageValue)
    finally:
        runtime.shutdown()


def test_generated_csv_numpy_pandas_project_loads_and_runs(tmp_path):
    project_path = generate_example(tmp_path / "scientific.cxproj")
    registry = build_default_registry(include_public_plugins=False)
    project = JsonProjectSerializer(registry).load(str(project_path))
    workspace = project.workspaces[project.active_workspace_id]
    snapshot = build_runtime_snapshot(
        project, workspace_id=workspace.workspace_id, registry=registry
    )
    runtime = CorexRuntime(registry=registry)
    try:
        result = runtime.run(
            ExecutionRequest(
                project_path=project_path,
                runtime_snapshot=snapshot,
                workspace_id=workspace.workspace_id,
            ),
            timeout=60,
        )
        assert result.status == "completed", (result.error, result.traceback)
        plots = {
            node.node_id
            for node in workspace.nodes.values()
            if node.type_id == "plot.signal"
        }
        settled = {
            e["node_id"]: e for e in result.events if e.get("type") == "node_settled"
        }
        assert len(plots) == 3
        assert (
            sum(node.type_id == "media.panel" for node in workspace.nodes.values()) == 3
        )
        for plot_id in plots:
            assert isinstance(
                settled_item(settled[plot_id], "image", registry.data_types), ImageValue
            )
        for node in workspace.nodes.values():
            if node.type_id == "media.panel":
                assert isinstance(
                    settled_item(
                        settled[node.node_id], "_surface_source", registry.data_types
                    ),
                    ImageValue,
                )
    finally:
        runtime.shutdown()


def test_npy_reference_pipeline_honors_explicit_input_rows_and_repeats(tmp_path):
    data_path = tmp_path / "source.npy"
    np.save(
        data_path,
        np.arange(4100 * 4, dtype=np.float64).reshape(4100, 4),
        allow_pickle=False,
    )
    registry = build_default_registry(include_public_plugins=False)
    model = GraphModel()
    source, plot, output = add_signal_chain(
        model, registry, kind="npy", rows=4100, path=str(data_path)
    )
    workspace_id = model.active_workspace.workspace_id
    snapshot = build_runtime_snapshot(
        model.project, workspace_id=workspace_id, registry=registry
    )
    runtime = CorexRuntime(registry=registry)
    try:
        request = ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace_id)
        first = runtime.run(request, timeout=60)
        assert first.status == "completed", (first.error, first.traceback)
        settled = {
            e["node_id"]: e for e in first.events if e.get("type") == "node_settled"
        }
        ref = settled_item(settled[source.node_id], output, registry.data_types)
        assert ref.shape == (4100, 4)
        assert len(settled[plot.node_id]["warnings"]) == 3
        assert all(
            "from 4100 to" in warning for warning in settled[plot.node_id]["warnings"]
        )
        wait_for_runtime_idle(runtime)
        repeated = runtime.run(request, timeout=60)
        assert repeated.status == "completed", (repeated.error, repeated.traceback)
        repeated_settled = {
            e["node_id"]: e for e in repeated.events if e.get("type") == "node_settled"
        }
        assert (
            repeated_settled[source.node_id]["decision_reason"] == "no_reusable_record"
        )
        assert (
            repeated_settled[plot.node_id]["decision_reason"]
            == "upstream_recompute_required"
        )
        assert isinstance(
            settled_item(repeated_settled[plot.node_id], "image", registry.data_types),
            ImageValue,
        )
        assert len(repeated_settled[plot.node_id]["warnings"]) == 3
    finally:
        runtime.shutdown()


@pytest.mark.parametrize(
    "type_id",
    [
        "COREX.DataTypes.ArrayValue",
        "COREX.DataTypes.TableValue",
        "COREX.DataTypes.SeriesValue",
        "COREX.DataTypes.Any",
        "COREX.Runtime.TabularDataRef",
        "COREX.Runtime.TabularWindowRef",
        "COREX.Runtime.ArrayDataRef",
        "COREX.Runtime.ArraySlice2DRef",
        "COREX.DataTypes.GraphArray",
    ],
)
def test_scientific_and_reference_connections_are_legal(type_id):
    registry = build_default_registry(include_public_plugins=False)
    model = GraphModel()
    mutation = model.validated_mutations(model.active_workspace.workspace_id, registry)
    source = mutation.add_node(
        type_id="core.python_script",
        title="Source",
        x=0,
        y=0,
        properties={
            "script": f'@corex.node\n@corex.output("result", value_type={type_id!r})\ndef run(ctx):\n    return {{}}\n'
        },
    )
    plot = mutation.add_node(type_id="plot.signal", title="Plot", x=200, y=0)
    mutation.add_edge(
        source_node_id=source.node_id,
        source_port_key="result",
        target_node_id=plot.node_id,
        target_port_key="values",
    )


@pytest.mark.parametrize(
    "type_id",
    [
        "COREX.DataTypes.String",
        "COREX.DataTypes.Image",
        "COREX.DataTypes.Path",
        "COREX.DataTypes.Bool",
    ],
)
def test_signal_rejects_unrelated_declared_sources(type_id):
    registry = build_default_registry(include_public_plugins=False)
    model = GraphModel()
    mutation = model.validated_mutations(model.active_workspace.workspace_id, registry)
    source = mutation.add_node(
        type_id="core.python_script",
        title="Source",
        x=0,
        y=0,
        properties={
            "script": f'@corex.node\n@corex.output("result", value_type={type_id!r})\ndef run(ctx):\n    return {{}}\n'
        },
    )
    plot = mutation.add_node(type_id="plot.signal", title="Plot", x=200, y=0)
    with pytest.raises(ValueError, match="[Ii]ncompatible"):
        mutation.add_edge(
            source_node_id=source.node_id,
            source_port_key="result",
            target_node_id=plot.node_id,
            target_port_key="values",
        )


@pytest.mark.parametrize(
    "rows",
    [32, pytest.param(2_000_000, marks=pytest.mark.slow)],
    ids=["small_reuse", "two_million_budget"],
)
def test_trusted_scientific_result_preserves_64_mib_reuse_budget(
    monkeypatch, tmp_path, rows
):
    from tests.test_solution_store_session import (
        _runtime,
        _settle,
        _terminal,
        _typed_session_producer_registry,
    )
    from ea_node_editor.settings import plugin_generations_dir

    registry = _typed_session_producer_registry(
        monkeypatch,
        "COREX.DataTypes.ArrayValue",
        generation_root=plugin_generations_dir(),
    )
    model = GraphModel()
    workspace_id = model.active_workspace.workspace_id
    node = model.validated_mutations(workspace_id, registry).add_node(
        type_id="tests.typed_session_value", title="Trusted fixture", x=0, y=0
    )
    runtime, client, registry = _runtime(model, registry=registry)
    request = ExecutionRequest(
        runtime_snapshot=build_runtime_snapshot(
            model.project, workspace_id=workspace_id, registry=registry
        ),
        workspace_id=workspace_id,
    )
    value = ArrayValue.from_numpy(
        np.arange(rows * 4, dtype=np.float64).reshape(rows, 4)
    )
    decisions = []
    try:
        initial = runtime.prepare_execution(request)
        run_id = runtime.dispatch_prepared(initial)
        _settle(client, run_id, node.node_id, value=value)
        _terminal(client, run_id)
        fact = runtime.solution_facts(model.project.project_id, workspace_id)[0]
        record = runtime.solution_record(fact.retained_record_id)
        assert record is not None and record.reuse_eligible
        expected = (
            "reusable_record_accepted"
            if rows == 32
            else "reuse_payload_budget_exceeded"
        )
        assert MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES == 67_108_864
        times, peak = _measure(
            lambda: decisions.append(runtime.prepare_execution(request)),
            warmups=0,
            measurements=1,
            include_children=True,
        )
        prepared = decisions[0]
        assert prepared.node_decisions[0].reason_code == expected
        assert prepared.node_decisions[0].action is (
            PreparedAction.REUSE if rows == 32 else PreparedAction.EXECUTE
        )
        assert bool(prepared.accepted_output_payloads) == (rows == 32)
        repeated_id = runtime.dispatch_prepared(prepared)
        _settle(client, repeated_id, node.node_id, value=value)
        _terminal(client, repeated_id)
        np.testing.assert_array_equal(
            value.to_numpy(), np.arange(rows * 4).reshape(rows, 4)
        )
        print(
            json.dumps(
                {
                    "trusted_fixture_rows": rows,
                    "columns": 4,
                    "limit_bytes": MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES,
                    "decision": expected,
                    "preparation_seconds": times[0],
                    "peak_combined_rss_bytes": peak,
                }
            )
        )
    finally:
        runtime.shutdown()
