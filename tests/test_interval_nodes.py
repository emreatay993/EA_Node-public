from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import queue
from unittest import mock

import pytest

from ea_node_editor.execution.run_messages import (
    StartRunCommand,
)
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.worker import run_workflow
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtin_functions.unit_math import SOURCE
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import (
    INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    PythonFunctionAdapter,
)
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.registry import PythonFunctionEntry
from ea_node_editor.runtime_contracts import (
    DOUBLE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
    INTEGER_DATA_TYPE_ID,
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    DataTree,
    Interval1D,
    deserialize_runtime_value,
)
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog

CONSTRUCT_INTERVAL_TYPE_ID = "math.construct_interval"
DECONSTRUCT_INTERVAL_TYPE_ID = "math.deconstruct_interval"
_INTERVAL_DECLARATIONS = {
    declaration.spec.type_id: declaration
    for declaration in discover_plugin_declarations(
        SOURCE,
        filename="unit_math.py",
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
    if declaration.spec.type_id
    in {CONSTRUCT_INTERVAL_TYPE_ID, DECONSTRUCT_INTERVAL_TYPE_ID}
}
_FUNCTIONS: dict[str, object] = {"__name__": "tests.unit_math_interval_function"}
exec(compile(SOURCE, "unit_math.py", "exec"), _FUNCTIONS)  # noqa: S102


def _interval_plugin(type_id: str) -> PythonFunctionAdapter:
    declaration = _INTERVAL_DECLARATIONS[type_id]
    return PythonFunctionAdapter(
        declaration.spec,
        _FUNCTIONS[declaration.function_name],  # type: ignore[arg-type]
    )


def _context(
    *,
    inputs: dict[str, object] | None = None,
    properties: dict[str, object] | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        run_id="interval-run",
        node_id="interval-node",
        workspace_id="interval-workspace",
        inputs=dict(inputs or {}),
        properties=dict(properties or {}),
        emit_log=lambda _level, _message: None,
    )


def _run(model: GraphModel, registry) -> list[dict[str, object]]:  # noqa: ANN001
    workspace_id = model.active_workspace.workspace_id
    snapshot = build_runtime_snapshot(
        model.project, workspace_id=workspace_id, registry=registry
    )
    catalog_fingerprint, revisions = catalog_agreement(registry.data_types)
    plugin_digest = registry.plugin_fingerprint()
    event_queue: queue.Queue = queue.Queue()
    with mock.patch(
        "ea_node_editor.nodes.bootstrap.build_default_registry",
        return_value=registry,
    ):
        run_workflow(
            StartRunCommand(
                run_id="interval-run",
                workspace_id=workspace_id,
                runtime_snapshot=snapshot,
                catalog_fingerprint=catalog_fingerprint,
                catalog_revisions=revisions,
                plugin_bundles=registry.plugin_bundle_refs(),
                plugin_fingerprint=plugin_digest,
                runtime_registry_fingerprint=runtime_registry_fingerprint(
                    catalog_fingerprint,
                    plugin_digest,
                ),
                registry_contract_fingerprint=registry.contract_fingerprint(),
                addon_runtime_config=registry.addon_runtime_config(),
            ),
            event_queue,
        )
    events: list[dict[str, object]] = []
    while not event_queue.empty():
        events.append(event_queue.get())
    return events


def _settled(events: list[dict[str, object]], node_id: str) -> dict[str, object]:
    return next(
        event
        for event in events
        if event.get("type") == "node_settled" and event.get("node_id") == node_id
    )


def _output_tree(event: dict[str, object], port_key: str) -> DataTree:
    outputs = event["outputs"]
    assert isinstance(outputs, dict)
    result = outputs[port_key]
    assert isinstance(result, dict)
    assert result["status"] == "value"
    tree = deserialize_runtime_value(result["value"])
    assert isinstance(tree, DataTree)
    return tree


def test_interval_node_specs_register_with_numeric_defaults_and_icon(
    tmp_path: Path,
) -> None:
    registry = build_builtin_registry(generation_root=tmp_path / "generations")
    construct = registry.get_spec(CONSTRUCT_INTERVAL_TYPE_ID)
    deconstruct = registry.get_spec(DECONSTRUCT_INTERVAL_TYPE_ID)
    construct_ports = {port.key: port for port in construct.ports}
    deconstruct_ports = {port.key: port for port in deconstruct.ports}

    assert construct.category_path == deconstruct.category_path == ("Math", "Interval")
    assert construct.icon == deconstruct.icon == "core/data_object.svg"
    assert registry.default_properties(CONSTRUCT_INTERVAL_TYPE_ID) == {
        "start": 0.0,
        "end": 1.0,
    }
    assert (
        construct_ports["start"].data_type,
        construct_ports["start"].accepted_data_types,
    ) == (
        DOUBLE_DATA_TYPE_ID,
        (INTEGER_DATA_TYPE_ID,),
    )
    assert construct_ports["start"].uses_property_default is True
    assert construct_ports["end"].uses_property_default is True
    assert construct_ports["interval"].data_type == INTERVAL_1D_GRAPH_DATA_TYPE_ID
    assert deconstruct_ports["interval"].required is True
    assert deconstruct_ports["interval"].data_type == INTERVAL_1D_GRAPH_DATA_TYPE_ID
    assert (
        deconstruct_ports["start"].data_type,
        deconstruct_ports["end"].data_type,
    ) == (
        DOUBLE_DATA_TYPE_ID,
        DOUBLE_DATA_TYPE_ID,
    )
    assert isinstance(registry.get_entry(CONSTRUCT_INTERVAL_TYPE_ID), PythonFunctionEntry)
    assert isinstance(registry.get_entry(DECONSTRUCT_INTERVAL_TYPE_ID), PythonFunctionEntry)
    assert registry.descriptor_or_none(CONSTRUCT_INTERVAL_TYPE_ID) is None
    assert registry.descriptor_or_none(DECONSTRUCT_INTERVAL_TYPE_ID) is None


def test_interval_specs_match_golden(tmp_path: Path) -> None:
    expected = {
        item["spec"]["type_id"]: item["spec"]
        for item in load_current_repo_owned_catalog()
    }
    registry = build_builtin_registry(generation_root=tmp_path / "generations")

    for type_id in (CONSTRUCT_INTERVAL_TYPE_ID, DECONSTRUCT_INTERVAL_TYPE_ID):
        assert json.loads(json.dumps(asdict(registry.get_spec(type_id)))) == expected[type_id]


@pytest.mark.parametrize(
    ("start", "end"),
    ((0.0, 10.0), (10.0, 0.0), (5.0, 5.0)),
)
def test_construct_interval_preserves_order_from_property_defaults(
    start: float, end: float
) -> None:
    result = _interval_plugin(CONSTRUCT_INTERVAL_TYPE_ID).execute(
        _context(properties={"start": start, "end": end})
    )
    assert result.outputs == {"interval": Interval1D(start, end)}


@pytest.mark.parametrize(
    "interval",
    (Interval1D(0.0, 10.0), Interval1D(10.0, 0.0), Interval1D(5.0, 5.0)),
)
def test_deconstruct_interval_recovers_original_order(interval: Interval1D) -> None:
    result = _interval_plugin(DECONSTRUCT_INTERVAL_TYPE_ID).execute(
        _context(inputs={"interval": interval})
    )
    assert result.outputs == {"start": interval.start, "end": interval.end}


@pytest.mark.parametrize("invalid", ({"start": 10.0, "end": 0.0}, [10.0, 0.0]))
def test_deconstruct_interval_rejects_untyped_pairs(invalid: object) -> None:
    with pytest.raises(TypeError, match="Interval1D instances"):
        _interval_plugin(DECONSTRUCT_INTERVAL_TYPE_ID).execute(
            _context(inputs={"interval": invalid})
        )


def test_construct_to_deconstruct_graph_converts_integer_inputs_and_preserves_decreasing_order() -> (
    None
):
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    start = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Start",
        0.0,
        0.0,
        properties={"value": 10},
    )
    end = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "End",
        0.0,
        120.0,
        properties={"value": 0},
    )
    construct = model.add_node(
        workspace.workspace_id,
        CONSTRUCT_INTERVAL_TYPE_ID,
        "Construct Interval",
        200.0,
        0.0,
    )
    deconstruct = model.add_node(
        workspace.workspace_id,
        DECONSTRUCT_INTERVAL_TYPE_ID,
        "Deconstruct Interval",
        400.0,
        0.0,
    )
    model.add_edge(
        workspace.workspace_id, start.node_id, "value", construct.node_id, "start"
    )
    model.add_edge(
        workspace.workspace_id, end.node_id, "value", construct.node_id, "end"
    )
    model.add_edge(
        workspace.workspace_id,
        construct.node_id,
        "interval",
        deconstruct.node_id,
        "interval",
    )

    events = _run(model, registry)

    assert _output_tree(
        _settled(events, construct.node_id), "interval"
    ) == DataTree.from_item(Interval1D(10.0, 0.0))
    assert _output_tree(
        _settled(events, deconstruct.node_id), "start"
    ) == DataTree.from_item(10.0)
    assert _output_tree(
        _settled(events, deconstruct.node_id), "end"
    ) == DataTree.from_item(0.0)


def test_deconstruct_interval_without_input_uses_required_input_readiness() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    deconstruct = model.add_node(
        workspace.workspace_id,
        DECONSTRUCT_INTERVAL_TYPE_ID,
        "Deconstruct Interval",
        0.0,
        0.0,
    )

    event = _settled(_run(model, registry), deconstruct.node_id)

    assert event["status"] == "empty"
    warnings = event.get("warnings")
    assert isinstance(warnings, list)
    assert len(warnings) == 1
    assert "Interval input did not receive any data yet" in warnings[0]


def test_deconstruct_interval_invalid_connected_value_reports_runtime_diagnostic() -> (
    None
):
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(
        workspace.workspace_id,
        "core.python_script",
        "Empty interval",
        0.0,
        0.0,
        properties={"script": '''@corex.node
@corex.output("value", value_type=corex.Any)
def run(ctx):
    return {"value": {}}
'''},
    )
    deconstruct = model.add_node(
        workspace.workspace_id,
        DECONSTRUCT_INTERVAL_TYPE_ID,
        "Deconstruct Interval",
        200.0,
        0.0,
    )
    model.add_edge(
        workspace.workspace_id, source.node_id, "value", deconstruct.node_id, "interval"
    )

    event = _settled(_run(model, registry), deconstruct.node_id)

    assert event["status"] == "failed"
    errors = event.get("errors")
    assert isinstance(errors, list)
    assert len(errors) == 1
    message = errors[0]["error"]
    for expected in (
        DECONSTRUCT_INTERVAL_TYPE_ID,
        deconstruct.node_id,
        "input port 'interval'",
        INTERVAL_1D_GRAPH_DATA_TYPE_ID,
        GRAPH_DATA_TYPE_ID,
        "builtins.dict",
        "DataPath (0,)",
        "item index 0",
        "runtime_check/abstract_source_descendant",
    ):
        assert expected in message
