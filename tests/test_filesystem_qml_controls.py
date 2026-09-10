# Purpose: Prove filesystem controls through the actual registry-to-QML host route.
# Map: feature_routes/surface_input_and_inline_controls.md
# Tests: tests/test_filesystem_qml_controls.py

from __future__ import annotations

import json
import unittest

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from ea_node_editor.ui_qml.graph_canvas_state.execution_state_props import (
    _readiness_input_facts,
    _readiness_issues_for_payload,
)
from ea_node_editor.runtime_contracts import DataTree
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from tests import test_graph_surface_input_inline as _inline_tests


def test_filesystem_registry_payload_controls_commit_from_graph_node_host() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    nodes = [
        model.add_node(workspace.workspace_id, "io.contents_in_directory", "Contents", 0, 0),
        model.add_node(workspace.workspace_id, "io.move_file", "Move", 260, 0),
        model.add_node(workspace.workspace_id, "io.create_directory", "Create", 520, 0),
    ]
    payloads, _backdrops, _minimap = GraphScenePayloadBuilder().build_node_payloads_for_ids(
        model=model,
        registry=registry,
        workspace_id=workspace.workspace_id,
        scope_path=(),
        node_ids={node.node_id for node in nodes},
        graph_theme_bridge=None,
    )
    payload_by_type = {payload["type_id"]: payload for payload in payloads}
    encoded = json.dumps(payload_by_type)

    _inline_tests.GraphSurfaceInputInlineTests(methodName="runTest")._run_qml_probe(
        "filesystem-registry-controls",
        f"""
        import json
        payloads = json.loads({json.dumps(encoded)})
        committed = []

        def control(host, object_name, property_key):
            return next(
                item for item in named_child_items(host, object_name)
                if str(item.property("propertyKey") or "") == property_key
            )

        for type_id, object_name, key, value in (
            ("io.contents_in_directory", "graphNodeInlineSliderEditor", "subdirectory_levels", 3),
            ("io.contents_in_directory", "graphNodeInlineEnumEditor", "content_type", 2),
            ("io.move_file", "graphNodeInlineEnumEditor", "operation_mode", 1),
            ("io.move_file", "graphNodeInlineToggleEditor", "overwrite_target_file", True),
            ("io.create_directory", "graphNodeInlineToggleEditor", "create_recursive", True),
        ):
            host = create_component(graph_node_host_qml_path, {{"nodeData": payloads[type_id]}})
            try:
                host.inlinePropertyCommitted.connect(
                    lambda node_id, property_key, committed_value: committed.append(
                        (str(node_id), str(property_key), variant_value(committed_value))
                    )
                )
                editor = control(host, object_name, key)
                assert bool(editor.property("visible"))
                assert bool(editor.property("enabled"))
                if object_name == "graphNodeInlineSliderEditor":
                    assert (int(editor.property("from")), int(editor.property("to")), int(editor.property("stepSize"))) == (0, 10, 1)
                    editor.commitRequested.emit(value)
                elif object_name == "graphNodeInlineEnumEditor":
                    editor.activated.emit(value)
                else:
                    editor.setProperty("checked", value)
                    editor.clicked.emit()
                settle_events(2)
                assert committed[-1][1:] == (key, value)
            finally:
                host.deleteLater()
                app.processEvents()
        """,
    )


def test_canvas_readiness_applies_empty_string_allowance_per_target() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(workspace.workspace_id, "io.deconstruct_file_path", "Source", 0, 0, properties={"file_path": "plain"})
    allowed = model.add_node(workspace.workspace_id, "io.construct_file_path", "Allowed", 200, 0, properties={"directory": ".", "file_name": "plain", "file_extension": ".ignored"})
    ordinary = model.add_node(workspace.workspace_id, "io.deconstruct_file_path", "Ordinary", 400, 0, properties={"file_path": "ignored"})
    model.add_edge(workspace.workspace_id, source.node_id, "file_extension", allowed.node_id, "file_extension")
    model.add_edge(workspace.workspace_id, source.node_id, "file_extension", ordinary.node_id, "file_path")
    payloads, _backdrops, _minimap = GraphScenePayloadBuilder().build_node_payloads_for_ids(
        model=model, registry=registry, workspace_id=workspace.workspace_id, scope_path=(), node_ids={source.node_id, allowed.node_id, ordinary.node_id}, graph_theme_bridge=None
    )
    edges = [
        {"source_node_id": edge.source_node_id, "source_port_key": edge.source_port_key, "target_node_id": edge.target_node_id, "target_port_key": edge.target_port_key, "enabled": edge.enabled}
        for edge in workspace.edges.values()
    ]
    records = {source.node_id: {"run": {"record_id": "run", "observed_at_epoch_ms": 1.0, "outputs": {"file_extension": SettledPortResult(status="value", value=DataTree.from_item(""))}}}}
    presence, overridden = _readiness_input_facts(node_payloads=payloads, edge_payloads=edges, output_records_by_node=records)
    payload_by_id = {payload["node_id"]: payload for payload in payloads}

    assert _readiness_issues_for_payload(payload_by_id[allowed.node_id], {}, port_has_value=presence[allowed.node_id], overridden_port_keys=overridden[allowed.node_id]) == ()
    assert [issue.target_keys for issue in _readiness_issues_for_payload(payload_by_id[ordinary.node_id], {}, port_has_value=presence[ordinary.node_id], overridden_port_keys=overridden[ordinary.node_id])] == [("file_path",)]


def test_canvas_readiness_stops_scanning_after_first_present_value() -> None:
    class InspectionRaises(str):
        def strip(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("value after a present item was inspected")

    presence, _overridden = _readiness_input_facts(
        node_payloads=[],
        edge_payloads=[
            {
                "source_node_id": "source",
                "source_port_key": "output",
                "target_node_id": "target",
                "target_port_key": "input",
                "enabled": True,
            }
        ],
        output_records_by_node={
            "source": {
                "run": {
                    "record_id": "run",
                    "observed_at_epoch_ms": 1.0,
                    "outputs": {
                        "output": SettledPortResult(
                            status="value",
                            value=DataTree.from_list(["ready", InspectionRaises("boom")]),
                        )
                    },
                }
            }
        },
    )

    assert presence == {"target": {"input": True}}
