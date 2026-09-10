# Purpose: Prove native scientific script interfaces and isolation in real workers.
# Map: subsystems/execution.md
# Tests: tests/test_scientific_worker_transport.py

from __future__ import annotations

import sys
import threading

import pytest

from ea_node_editor.execution.external_python_client import (
    ExternalPythonExecutionClient,
)
from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.runtime_contracts.scientific_values import ArrayValue, TableValue
from ea_node_editor.runtime_contracts.value_codec import deserialize_runtime_value
from tests.execution_client_fixtures import _external_selection


@pytest.mark.parametrize("external", [False, True], ids=["process", "external"])
def test_repeated_scientific_script_graph_transports_owned_values_and_isolates_consumers(
    external, monkeypatch,
):
    # Like the import probes, isolate this test from foreign embedded-Python state.
    for key in ("PYTHONHOME", "PYTHONPATH"):
        monkeypatch.delenv(key, raising=False)
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    source_code = """@corex.node
@corex.output("array", value_type="COREX.DataTypes.ArrayValue")
@corex.output("frame", value_type="COREX.DataTypes.TableValue")
@corex.output("series", value_type="COREX.DataTypes.SeriesValue")
def run(ctx):
    import numpy as np, pandas as pd
    return {'array': np.arange(8.0), 'frame': pd.DataFrame({'y': [1, 2, 3]}), 'series': pd.Series([1, None, 3], dtype='Int64', name='signal')}
"""
    consumer_code = """@corex.node
@corex.input("array", value_type="COREX.DataTypes.ArrayValue")
@corex.input("frame", value_type="COREX.DataTypes.TableValue")
@corex.input("series", value_type="COREX.DataTypes.SeriesValue")
@corex.output("result", value_type=corex.Any)
def run(ctx, array, frame, series):
    import numpy as np, pandas as pd
    assert type(array) is np.ndarray and type(frame) is pd.DataFrame and type(series) is pd.Series
    assert array[0] == 0 and frame.iloc[0, 0] == 1 and series.iloc[0] == 1
    array[0] = 999
    frame.iloc[0, 0] = 999
    series.iloc[0] = 999
    return {'result': 'native-and-isolated'}
"""
    source = model.add_node(
        workspace.workspace_id,
        "core.python_script",
        "Scientific source",
        0,
        0,
        properties={"script": source_code},
    )
    consumers = [
        model.add_node(
            workspace.workspace_id,
            "core.python_script",
            f"Consumer {i}",
            200,
            i * 100,
            properties={"script": consumer_code},
        )
        for i in range(2)
    ]
    for consumer in consumers:
        for key in ("array", "frame", "series"):
            model.add_edge(
                workspace.workspace_id, source.node_id, key, consumer.node_id, key
            )
    snapshot = build_runtime_snapshot(
        model.project, workspace_id=workspace.workspace_id, registry=registry
    )
    client = ExternalPythonExecutionClient() if external else ProcessExecutionClient()
    condition = threading.Condition()
    events = []

    def on_event(event):
        with condition:
            events.append(event)
            condition.notify_all()

    client.subscribe(on_event)
    try:
        for _ in range(2):
            options = (
                {"execution_backend": _external_selection(sys.executable)}
                if external
                else {}
            )
            run_id = client.start_run(
                project_path="",
                workspace_id=workspace.workspace_id,
                trigger={"kind": "manual", "runtime_snapshot": snapshot},
                data_types=registry.data_types,
                plugin_bundles=registry.plugin_bundle_refs(),
                plugin_fingerprint=registry.plugin_fingerprint(),
                registry_contract_fingerprint=registry.contract_fingerprint(),
                addon_runtime_config=registry.addon_runtime_config(),
                **options,
            )
            assert run_id, [
                (e.get("type"), e.get("error"), e.get("message"), e.get("reason"))
                for e in events
                if e.get("type") == "protocol_error"
            ]
            with condition:
                assert condition.wait_for(
                    lambda: any(
                        e.get("run_id") == run_id
                        and e.get("type") in {"run_completed", "run_failed", "protocol_error"}
                        for e in events
                    ),
                    timeout=45,
                ), events
                run_events = [e for e in events if e.get("run_id") == run_id]
            assert not any(e.get("type") == "protocol_error" for e in run_events), [
                (e.get("type"), e.get("error"), e.get("message"), e.get("reason"))
                for e in run_events
            ]
            assert not any(e.get("type") == "run_failed" for e in run_events), (
                run_events
            )
            settled = {
                e["node_id"]: e for e in run_events if e.get("type") == "node_settled"
            }
            for consumer in consumers:
                result = settled[consumer.node_id]["outputs"]["result"]
                assert result["status"] == "value", settled[consumer.node_id]
                assert (
                    deserialize_runtime_value(
                        result["value"], catalog=registry.data_types
                    )[(0,)][0]
                    == "native-and-isolated"
                )
            values = {
                key: deserialize_runtime_value(
                    value["value"], catalog=registry.data_types
                )[(0,)][0]
                for key, value in settled[source.node_id]["outputs"].items()
            }
            assert (
                type(values["array"]) is ArrayValue
                and values["array"].to_numpy()[0] == 0
            )
            assert (
                type(values["frame"]) is TableValue
                and values["frame"].column_values(0)[0] == 1
            )
            assert (
                values["series"].kind == "series"
                and values["series"].column_values(0)[0] == 1
            )
    finally:
        client.shutdown()
