from __future__ import annotations

import queue
import tempfile
from pathlib import Path
from unittest import mock

from ea_node_editor.execution.run_messages import (
    TriggerCaptureSettledEvent,
    TriggerPublishedEvent,
)
from ea_node_editor.execution.protocol_codec import (
    coerce_start_run_command,
    dict_to_event,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.worker import run_workflow
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.integrations_file_io import execute_file_write
from ea_node_editor.nodes.decorators import node_type
from ea_node_editor.nodes.execution_context import (
    ExecutionContext,
    NodeResult,
)
from ea_node_editor.nodes.node_specs import (
    DynamicPortGroupSpec,
    PortSpec,
    PropertySpec,
    PropertyConditionSpec,
    ReadinessRequirementSpec,
)
from ea_node_editor.runtime_contracts.value_codec import (
    deserialize_runtime_value,
)
from ea_node_editor.runtime_contracts import DataTree


@node_type(
    type_id="tests.dataflow_tree_source",
    display_name="Dataflow Tree Source",
    category_path=("Tests",),
    icon="",
    ports=(
        PortSpec(
            "tree",
            "out",
            "data",
            "COREX.DataTypes.Any",
            data_access="tree",
        ),
    ),
    properties=(PropertySpec("branches", "json", [], "Branches"),),
)
class _TreeSourcePlugin:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult(
            outputs={
                "tree": DataTree(
                    (tuple(path), tuple(items))
                    for path, items in ctx.properties["branches"]
                )
            }
        )


@node_type(
    type_id="tests.dataflow_probe",
    display_name="Dataflow Probe",
    category_path=("Tests",),
    icon="",
    ports=(
        PortSpec(
            "principal",
            "in",
            "data",
            "COREX.DataTypes.Any",
            required=True,
        ),
        PortSpec("repeated", "in", "data", "COREX.DataTypes.Int", required=True),
        PortSpec(
            "branch",
            "in",
            "data",
            "COREX.DataTypes.Any",
            required=True,
            data_access="list",
        ),
        PortSpec(
            "full",
            "in",
            "data",
            "COREX.DataTypes.Any",
            required=True,
            data_access="tree",
        ),
        PortSpec("result", "out", "data", "COREX.DataTypes.Any"),
    ),
    properties=(),
)
class _ProbePlugin:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        full = ctx.inputs["full"]
        return NodeResult(
            outputs={
                "result": (
                    ctx.inputs["principal"],
                    ctx.inputs["repeated"],
                    tuple(ctx.inputs["branch"]),
                    full.branch_count,
                    ctx.target_iteration,
                    ctx.iteration_count,
                )
            }
        )


@node_type(
    type_id="tests.dataflow_fail_second",
    display_name="Dataflow Fail Second",
    category_path=("Tests",),
    icon="",
    ports=(
        PortSpec(
            "value",
            "in",
            "data",
            "COREX.DataTypes.Any",
            required=True,
        ),
        PortSpec("result", "out", "data", "COREX.DataTypes.Any"),
    ),
    properties=(),
)
class _FailSecondPlugin:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        if ctx.inputs["value"] == "bad":
            raise RuntimeError("second iteration failed")
        return NodeResult(outputs={"result": ctx.inputs["value"]})


@node_type(
    type_id="tests.dataflow_item_sink",
    display_name="Dataflow Item Sink",
    category_path=("Tests",),
    icon="",
    ports=(
        PortSpec(
            "value",
            "in",
            "data",
            "COREX.DataTypes.Any",
            required=True,
        ),
        PortSpec("result", "out", "data", "COREX.DataTypes.Any"),
    ),
    properties=(),
)
class _ItemSinkPlugin:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={"result": ctx.inputs["value"]})


@node_type(
    type_id="tests.dataflow_tree_sink",
    display_name="Dataflow Tree Sink",
    category_path=("Tests",),
    icon="",
    ports=(
        PortSpec(
            "value",
            "in",
            "data",
            "COREX.DataTypes.Any",
            required=True,
            data_access="tree",
        ),
        PortSpec(
            "result",
            "out",
            "data",
            "COREX.DataTypes.Any",
            data_access="tree",
        ),
    ),
    properties=(),
)
class _TreeSinkPlugin:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={"result": ctx.inputs["value"]})


@node_type(
    type_id="tests.dataflow_bad_list",
    display_name="Dataflow Bad List",
    category_path=("Tests",),
    icon="",
    ports=(
        PortSpec(
            "result",
            "out",
            "data",
            "COREX.DataTypes.Any",
            data_access="list",
        ),
    ),
    properties=(),
)
class _BadListPlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={"result": "not a list"})


@node_type(
    type_id="tests.dataflow_none_source",
    display_name="Dataflow None Source",
    category_path=("Tests",),
    icon="",
    ports=(PortSpec("result", "out", "data", "COREX.DataTypes.Any"),),
    properties=(),
)
class _NoneSourcePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={"result": None})


@node_type(
    type_id="tests.dataflow_empty_source",
    display_name="Dataflow Empty Source",
    category_path=("Tests",),
    icon="",
    ports=(PortSpec("result", "out", "data", "COREX.DataTypes.Any"),),
    properties=(),
)
class _EmptySourcePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


@node_type(
    type_id="tests.dataflow_fail_source",
    display_name="Dataflow Fail Source",
    category_path=("Tests",),
    icon="",
    ports=(PortSpec("result", "out", "data", "COREX.DataTypes.Any"),),
    properties=(),
)
class _FailSourcePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        raise RuntimeError("capture source failed")


@node_type(
    type_id="tests.dataflow_passthrough",
    display_name="Dataflow Passthrough",
    category_path=("Tests",),
    icon="",
    ports=(
        PortSpec(
            "value",
            "in",
            "data",
            "COREX.DataTypes.Any",
            required=True,
        ),
        PortSpec("result", "out", "data", "COREX.DataTypes.Any"),
    ),
    properties=(),
)
class _PassthroughPlugin:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={"result": ctx.inputs["value"]})


@node_type(
    type_id="tests.dataflow_optional_default",
    display_name="Dataflow Optional Default",
    category_path=("Tests",),
    icon="",
    ports=(
        PortSpec(
            "value",
            "in",
            "data",
            "COREX.DataTypes.Any",
            required=False,
        ),
        PortSpec("result", "out", "data", "COREX.DataTypes.Any"),
    ),
    properties=(PropertySpec("fallback", "str", "fallback", "Fallback"),),
)
class _OptionalDefaultPlugin:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult(
            outputs={"result": ctx.inputs.get("value", ctx.properties["fallback"])}
        )


def _required_dynamic_inputs(properties) -> tuple[PortSpec, ...]:  # noqa: ANN001
    return tuple(
        PortSpec(
            str(key),
            "in",
            "data",
            "COREX.DataTypes.Any",
            label=str(key).replace("_", " ").title(),
            required=True,
        )
        for key in properties["input_names"]
    )


def _next_required_dynamic_input(properties) -> str:  # noqa: ANN001
    used = set(properties["input_names"])
    suffix = 1
    while f"input{suffix}" in used:
        suffix += 1
    return f"input{suffix}"


@node_type(
    type_id="tests.dataflow_dynamic_required",
    display_name="Dataflow Dynamic Required",
    category_path=("Tests",),
    icon="",
    ports=(PortSpec("result", "out", "data", "COREX.DataTypes.Any"),),
    properties=(
        PropertySpec(
            "input_names",
            "json",
            ["payload"],
            "Inputs",
            inspector_visible=False,
        ),
    ),
    dynamic_port_groups=(
        DynamicPortGroupSpec(
            "inputs",
            "input_names",
            "in",
            _required_dynamic_inputs,
            _next_required_dynamic_input,
        ),
    ),
)
class _DynamicRequiredPlugin:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={"result": ctx.inputs["payload"]})


@node_type(
    type_id="tests.dataflow_declarative_readiness",
    display_name="Dataflow Declarative Readiness",
    category_path=("Tests",),
    icon="",
    ports=(
        PortSpec(
            "primary",
            "in",
            "data",
            "COREX.DataTypes.Any",
            label="Primary",
            required=False,
        ),
        PortSpec(
            "alternate",
            "in",
            "data",
            "COREX.DataTypes.Any",
            label="Alternate",
            required=False,
        ),
        PortSpec(
            "conditional",
            "in",
            "data",
            "COREX.DataTypes.Any",
            label="Conditional",
            required=False,
        ),
        PortSpec(
            "fallback",
            "in",
            "data",
            "COREX.DataTypes.String",
            label="Fallback",
            required=True,
            uses_property_default=True,
        ),
        PortSpec("result", "out", "data", "COREX.DataTypes.Any"),
    ),
    properties=(
        PropertySpec("fallback", "str", "configured", "Fallback"),
        PropertySpec("mode", "str", "inactive", "Mode"),
    ),
    readiness_requirements=(
        ReadinessRequirementSpec(any_of_ports=("primary", "alternate")),
        ReadinessRequirementSpec(
            any_of_ports=("conditional",),
            when_properties=(PropertyConditionSpec("mode", ("active",)),),
        ),
    ),
)
class _DeclarativeReadinessPlugin:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        if ctx.inputs.get("primary") == "invalid":
            raise ValueError("invalid supplied value")
        return NodeResult(outputs={"result": ctx.inputs["fallback"]})


@node_type(
    type_id="tests.dataflow_diamond_join",
    display_name="Dataflow Diamond Join",
    category_path=("Tests",),
    icon="",
    ports=(
        PortSpec(
            "left", "in", "data", "COREX.DataTypes.Any", required=True
        ),
        PortSpec(
            "right",
            "in",
            "data",
            "COREX.DataTypes.Any",
            required=True,
        ),
        PortSpec("result", "out", "data", "COREX.DataTypes.Any"),
    ),
    properties=(),
)
class _DiamondJoinPlugin:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={"result": (ctx.inputs["left"], ctx.inputs["right"])})


_TEST_PLUGINS = (
    _TreeSourcePlugin,
    _ProbePlugin,
    _FailSecondPlugin,
    _ItemSinkPlugin,
    _TreeSinkPlugin,
    _BadListPlugin,
    _NoneSourcePlugin,
    _EmptySourcePlugin,
    _FailSourcePlugin,
    _PassthroughPlugin,
    _OptionalDefaultPlugin,
    _DynamicRequiredPlugin,
    _DeclarativeReadinessPlugin,
    _DiamondJoinPlugin,
)


def _registry():
    registry = build_default_registry()
    for plugin in _TEST_PLUGINS:
        registry.register(plugin)
    return registry


def _run(
    model: GraphModel,
    registry,
    *,
    run_id: str,
    target_node_ids: tuple[str, ...] = (),
    clicked_trigger_node_id: str = "",
    trigger_publications: dict[str, SettledPortResult] | None = None,
    trigger_captures: dict[str, SettledPortResult] | None = None,
) -> list[dict[str, object]]:
    workspace_id = model.active_workspace.workspace_id
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace_id,
        registry=registry,
    )
    event_queue: queue.Queue = queue.Queue()
    with mock.patch(
        "ea_node_editor.nodes.bootstrap.build_default_registry",
        return_value=registry,
    ):
        run_workflow(
            coerce_start_run_command(
                {
                    "run_id": run_id,
                    "workspace_id": workspace_id,
                    "runtime_snapshot": snapshot,
                    "target_node_ids": target_node_ids,
                    "clicked_trigger_node_id": clicked_trigger_node_id,
                    "trigger_publications": trigger_publications or {},
                    "trigger_captures": trigger_captures or {},
                    "trigger": {},
                    "plugin_bundles": registry.plugin_bundle_refs(),
                    "plugin_fingerprint": registry.plugin_fingerprint(),
                    "registry_contract_fingerprint": registry.contract_fingerprint(),
                    "addon_runtime_config": registry.addon_runtime_config(),
                },
                catalog=registry.data_types,
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


def _output_result(event: dict[str, object], port_key: str) -> dict[str, object]:
    outputs = event["outputs"]
    assert isinstance(outputs, dict)
    result = outputs[port_key]
    assert isinstance(result, dict)
    return result


def _output_tree(event: dict[str, object], port_key: str) -> DataTree:
    result = _output_result(event, port_key)
    assert result["status"] == "value"
    tree = deserialize_runtime_value(result["value"])
    assert isinstance(tree, DataTree)
    return tree


def _source(
    model: GraphModel, title: str, branches: list[list[object]], x: float = 0.0
):
    workspace = model.active_workspace
    return model.add_node(
        workspace.workspace_id,
        "tests.dataflow_tree_source",
        title,
        x,
        0,
        properties={"branches": branches},
    )


def _wire_probe(model: GraphModel, source, repeated, probe) -> None:  # noqa: ANN001
    workspace_id = model.active_workspace.workspace_id
    model.add_edge(workspace_id, source.node_id, "tree", probe.node_id, "principal")
    model.add_edge(workspace_id, repeated.node_id, "tree", probe.node_id, "repeated")
    model.add_edge(workspace_id, source.node_id, "tree", probe.node_id, "branch")
    model.add_edge(workspace_id, source.node_id, "tree", probe.node_id, "full")


def _readiness_target(
    model: GraphModel,
    *,
    properties: dict[str, object] | None = None,
):
    workspace = model.active_workspace
    return model.add_node(
        workspace.workspace_id,
        "tests.dataflow_declarative_readiness",
        "Readiness",
        180,
        0,
        properties=properties or {},
    )


def test_matching_modifiers_repeat_last_and_principal_selection() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    source = _source(
        model,
        "Principal",
        [[[1, 0], ["a", "b"]], [[2, 0], ["c"]]],
    )
    repeated = _source(model, "Repeated", [[[0], [10]]], 80)
    automatic = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_probe",
        "Automatic Principal",
        180,
        0,
    )
    explicit = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_probe",
        "Explicit Principal",
        180,
        120,
    )
    _wire_probe(model, source, repeated, automatic)
    _wire_probe(model, source, repeated, explicit)
    workspace.nodes[automatic.node_id].port_modifiers = {
        "principal": ("reverse",),
        "result": ("reverse",),
    }
    workspace.nodes[explicit.node_id].principal_input_port_id = "repeated"

    events = _run(model, registry, run_id="matching")

    assert _output_tree(_settled(events, automatic.node_id), "result") == DataTree(
        {
            (1, 0): (
                ["a", 10, ["a", "b"], 2, 1, 3],
                ["b", 10, ["a", "b"], 2, 0, 3],
            ),
            (2, 0): (["c", 10, ["c"], 2, 2, 3],),
        }
    )
    assert _output_tree(_settled(events, explicit.node_id), "result") == DataTree(
        {(0,): (["a", 10, ["a", "b"], 2, 0, 1],)}
    )


def test_ordered_shift_fan_in_and_disabled_wire_exclusion() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    first = _source(model, "First", [[[0], ["first"]]])
    second = _source(model, "Second", [[[0], ["second"]]], 80)
    sink = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_tree_sink",
        "Sink",
        180,
        0,
    )
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    first_edge = mutations.add_edge(
        source_node_id=first.node_id,
        source_port_key="tree",
        target_node_id=sink.node_id,
        target_port_key="value",
    )
    mutations.add_edge(
        source_node_id=second.node_id,
        source_port_key="tree",
        target_node_id=sink.node_id,
        target_port_key="value",
        append_requested=True,
    )

    events = _run(model, registry, run_id="fanin")
    assert _output_tree(_settled(events, sink.node_id), "result") == DataTree(
        {(0,): ("first", "second")}
    )

    mutations.set_edge_enabled(first_edge.edge_id, False)
    events = _run(model, registry, run_id="fanin_disabled")
    assert _output_tree(_settled(events, sink.node_id), "result") == DataTree.from_item(
        "second"
    )


def test_side_effect_tree_input_invokes_once_and_preserves_single_item_behavior() -> (
    None
):
    original_execute = execute_file_write
    received_inputs: list[object] = []

    def counted_execute(ctx):  # noqa: ANN001
        received_inputs.append(ctx.inputs["text"])
        return original_execute(ctx)

    with (
        tempfile.TemporaryDirectory() as temp_dir,
        mock.patch(
            "ea_node_editor.nodes.builtins.integrations_file_io.execute_file_write",
            counted_execute,
        ),
    ):
        output_path = Path(temp_dir) / "output.txt"
        model = GraphModel()
        workspace = model.active_workspace
        registry = _registry()
        source = _source(model, "Ambiguous", [[[0], ["first", "second"]]])
        writer = model.add_node(
            workspace.workspace_id,
            "io.file_write",
            "Writer",
            180,
            0,
            properties={"path": str(output_path), "as_json": False},
        )
        model.add_edge(
            workspace.workspace_id, source.node_id, "tree", writer.node_id, "text"
        )

        events = _run(model, registry, run_id="side_effect_ambiguous")

        assert len(received_inputs) == 1
        assert isinstance(received_inputs[0], DataTree)
        assert _settled(events, writer.node_id)["status"] == "failed"
        assert not output_path.exists()

        received_inputs.clear()
        model = GraphModel()
        workspace = model.active_workspace
        source = _source(model, "Single", [[[0], ["only once"]]])
        writer = model.add_node(
            workspace.workspace_id,
            "io.file_write",
            "Writer",
            180,
            0,
            properties={"path": str(output_path), "as_json": False},
        )
        model.add_edge(
            workspace.workspace_id, source.node_id, "tree", writer.node_id, "text"
        )

        events = _run(model, registry, run_id="side_effect_single")

        assert len(received_inputs) == 1
        assert _settled(events, writer.node_id)["status"] == "completed"
        assert output_path.read_text(encoding="utf-8") == "only once"


def test_unresolved_required_input_settles_empty_without_invoking_plugin() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    node = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_item_sink",
        "Unresolved",
        0,
        0,
    )

    with mock.patch.object(_ItemSinkPlugin, "execute", autospec=True) as execute:
        events = _run(model, registry, run_id="unresolved_required")

    execute.assert_not_called()
    settled = _settled(events, node.node_id)
    assert settled["status"] == "empty"
    assert _output_result(settled, "result")["status"] == "empty"
    assert not any(event["type"] == "run_failed" for event in events)


def test_required_dynamic_input_matches_static_readiness_behavior() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    node = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_dynamic_required",
        "Dynamic",
        180,
        0,
    )

    with mock.patch.object(_DynamicRequiredPlugin, "execute", autospec=True) as execute:
        events = _run(model, registry, run_id="dynamic_required_unwired")

    execute.assert_not_called()
    settled = _settled(events, node.node_id)
    assert settled["status"] == "empty"
    assert "Payload" in " ".join(settled["warnings"])
    assert not any(event["type"] == "run_failed" for event in events)

    source = _source(model, "Source", [[[0], ["ready"]]])
    model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "tree",
        node.node_id,
        "payload",
    )

    settled = _settled(
        _run(model, registry, run_id="dynamic_required_connected"),
        node.node_id,
    )
    assert settled["status"] == "completed"
    assert _output_tree(settled, "result") == DataTree.from_item("ready")


def test_python_script_decorated_ports_execute_and_settle_declared_outputs() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    script = mutations.add_node(
        type_id="core.python_script",
        title="Dynamic Script",
        x=0,
        y=0,
        properties={
            "script": '''@corex.node
@corex.input("missing", value_type=corex.Any)
@corex.output("values", value_type=corex.Any)
@corex.output("explicit_none", value_type=corex.Any)
@corex.output("unassigned", value_type=corex.Any)
def run(ctx, missing):
    return {"values": [number * number for number in range(3)], "explicit_none": missing}
''',
        },
    )
    no_ports = mutations.add_node(
        type_id="core.python_script",
        title="No Ports",
        x=180,
        y=0,
        properties={
            "script": "@corex.node\ndef run(ctx):\n    return {}\n",
        },
    )

    events = _run(model, registry, run_id="python_dynamic_ports")
    settled = _settled(events, script.node_id)
    assert settled["status"] == "completed"
    assert _output_tree(settled, "values") == DataTree.from_item([0, 1, 4])
    assert _output_tree(settled, "explicit_none") == DataTree.from_item(None)
    assert _output_result(settled, "unassigned")["status"] == "empty"

    no_ports_settled = _settled(events, no_ports.node_id)
    assert no_ports_settled["status"] == "completed"
    assert no_ports_settled["outputs"] == {}


def test_python_script_list_and_tree_access_round_trip_through_output_validation() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    list_source = _source(model, "List", [[[2], [1, 2, 3]]])
    tree_source = _source(
        model,
        "Tree",
        [[[5], ["a", "b"]], [[6], ["c"]]],
        x=100.0,
    )
    script = mutations.add_node(
        type_id="core.python_script",
        title="Access Script",
        x=240.0,
        y=0.0,
        properties={
            "script": '''@corex.node
@corex.input("values", value_type=corex.Any, structure="list", required=True)
@corex.input("tree", value_type=corex.Any, structure="tree", required=True)
@corex.output("list_out", value_type=corex.Any, structure="list")
@corex.output("tree_out", value_type=corex.Any, structure="tree")
def run(ctx, values, tree):
    if not isinstance(values, list):
        raise TypeError("values did not resolve as a list")
    if not hasattr(tree, "branches"):
        raise TypeError("tree did not resolve as a DataTree")
    return {"list_out": values, "tree_out": tree}
''',
        },
    )
    mutations.add_edge(
        source_node_id=list_source.node_id,
        source_port_key="tree",
        target_node_id=script.node_id,
        target_port_key="values",
    )
    mutations.add_edge(
        source_node_id=tree_source.node_id,
        source_port_key="tree",
        target_node_id=script.node_id,
        target_port_key="tree",
    )

    settled = _settled(
        _run(model, registry, run_id="python_list_tree_access"),
        script.node_id,
    )

    assert settled["status"] == "completed"
    assert _output_tree(settled, "list_out") == DataTree({(2,): (1, 2, 3)})
    assert _output_tree(settled, "tree_out") == DataTree(
        {(5,): ("a", "b"), (6,): ("c",)}
    )


def test_declarative_any_of_readiness_settles_before_plugin_creation() -> None:
    model = GraphModel()
    registry = _registry()
    node = _readiness_target(model)

    with mock.patch.object(registry, "create", wraps=registry.create) as create:
        events = _run(model, registry, run_id="readiness_any_of")

    create.assert_not_called()
    settled = _settled(events, node.node_id)
    assert settled["status"] == "empty"
    assert _output_result(settled, "result")["status"] == "empty"
    assert "Primary, Alternate" in " ".join(settled["warnings"])
    assert any(
        event.get("type") == "log" and event.get("level") == "warning"
        for event in events
    )
    assert not any(
        event.get("type") == "log" and event.get("level") == "error" for event in events
    )
    assert not any(event["type"] == "run_failed" for event in events)


def test_declarative_conditional_readiness_only_applies_when_active() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    source = _source(model, "Primary", [[[0], ["ready"]]])
    node = _readiness_target(model, properties={"mode": "active"})
    model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "tree",
        node.node_id,
        "primary",
    )

    with mock.patch.object(
        _DeclarativeReadinessPlugin, "execute", autospec=True
    ) as execute:
        events = _run(model, registry, run_id="readiness_conditional")

    execute.assert_not_called()
    settled = _settled(events, node.node_id)
    assert settled["status"] == "empty"
    assert "Conditional" in " ".join(settled["warnings"])
    assert not any(
        event.get("type") == "log" and event.get("level") == "error" for event in events
    )
    assert not any(event["type"] == "run_failed" for event in events)


def test_required_port_uses_nonblank_property_fallback() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    source = _source(model, "Primary", [[[0], ["ready"]]])
    node = _readiness_target(model, properties={"fallback": "from-property"})
    model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "tree",
        node.node_id,
        "primary",
    )

    events = _run(model, registry, run_id="readiness_property_fallback")

    settled = _settled(events, node.node_id)
    assert settled["status"] == "completed"
    assert _output_tree(settled, "result") == DataTree.from_item("from-property")


def test_enabled_empty_wire_overrides_required_property_fallback() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    source = _source(model, "Primary", [[[0], ["ready"]]])
    empty = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_empty_source",
        "Empty Override",
        0,
        100,
    )
    node = _readiness_target(model, properties={"fallback": "from-property"})
    model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "tree",
        node.node_id,
        "primary",
    )
    model.add_edge(
        workspace.workspace_id,
        empty.node_id,
        "result",
        node.node_id,
        "fallback",
    )

    with mock.patch.object(
        _DeclarativeReadinessPlugin, "execute", autospec=True
    ) as execute:
        events = _run(model, registry, run_id="readiness_empty_override")

    execute.assert_not_called()
    settled = _settled(events, node.node_id)
    assert settled["status"] == "empty"
    assert "Fallback" in " ".join(settled["warnings"])
    assert not any(
        event.get("type") == "log" and event.get("level") == "error" for event in events
    )
    assert not any(event["type"] == "run_failed" for event in events)


def test_invalid_supplied_value_remains_a_real_failure() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    source = _source(model, "Primary", [[[0], ["invalid"]]])
    node = _readiness_target(model)
    model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "tree",
        node.node_id,
        "primary",
    )

    events = _run(model, registry, run_id="readiness_invalid_supplied")

    settled = _settled(events, node.node_id)
    assert settled["status"] == "failed"
    assert "invalid supplied value" in settled["errors"][0]["error"]
    assert any(
        event.get("type") == "log" and event.get("level") == "error" for event in events
    )
    assert not any(event["type"] == "run_failed" for event in events)


def test_missing_default_path_settles_empty_with_warning() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    node = ValidatedGraphMutation(model, workspace.workspace_id, registry).add_node(
        type_id="io.file_read",
        title="Missing Path",
        x=0,
        y=0,
        properties={"path": ""},
    )

    events = _run(model, registry, run_id="missing_locked_path")

    settled = _settled(events, node.node_id)
    assert settled["status"] == "empty"
    assert _output_result(settled, "text")["status"] == "empty"
    assert tuple(settled["warnings"]) == (
        "The node has not been computed because the Path input did not receive any "
        "data yet. Please provide data for all mandatory inputs and check your upstream "
        "workflow for errors or missing wires.",
    )
    assert not any(event["type"] == "run_failed" for event in events)


def test_nonexistent_supplied_path_remains_a_real_failure(tmp_path: Path) -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    node = ValidatedGraphMutation(model, workspace.workspace_id, registry).add_node(
        type_id="io.file_read",
        title="Bad Path",
        x=0,
        y=0,
        properties={"path": str(tmp_path / "missing.txt")},
    )

    events = _run(model, registry, run_id="nonexistent_path")

    settled = _settled(events, node.node_id)
    assert settled["status"] == "failed"
    assert "does not exist" in settled["errors"][0]["error"]
    assert _output_result(settled, "text")["status"] == "failed"


def test_empty_required_input_skips_consumer_and_propagates_empty() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    source = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_empty_source",
        "Empty",
        0,
        0,
    )
    middle = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_passthrough",
        "Skipped",
        100,
        0,
    )
    sink = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_item_sink",
        "Propagated Empty",
        200,
        0,
    )
    model.add_edge(
        workspace.workspace_id, source.node_id, "result", middle.node_id, "value"
    )
    model.add_edge(
        workspace.workspace_id, middle.node_id, "result", sink.node_id, "value"
    )

    events = _run(model, registry, run_id="required_empty")

    for node, port_key in ((source, "result"), (middle, "result"), (sink, "result")):
        event = _settled(events, node.node_id)
        assert event["status"] == "empty"
        assert _output_result(event, port_key)["status"] == "empty"
    assert not any(event["type"] == "run_failed" for event in events)


def test_empty_optional_input_is_omitted_so_plugin_default_is_used() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    source = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_empty_source",
        "Empty",
        0,
        0,
    )
    consumer = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_optional_default",
        "Optional Default",
        100,
        0,
        properties={"fallback": "used-default"},
    )
    model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "result",
        consumer.node_id,
        "value",
    )

    events = _run(model, registry, run_id="optional_empty")

    assert _output_tree(
        _settled(events, consumer.node_id), "result"
    ) == DataTree.from_item("used-default")


def test_atomic_failure_blocks_dependents_without_cascade_or_run_failure() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    source = _source(model, "Source", [[[0], ["ok", "bad"]]])
    failing = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_fail_second",
        "Failing",
        100,
        0,
    )
    sink = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_item_sink",
        "Blocked Sink",
        200,
        0,
    )
    independent = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Independent",
        300,
        0,
        properties={"value": "independent"},
    )
    model.add_edge(
        workspace.workspace_id, source.node_id, "tree", failing.node_id, "value"
    )
    model.add_edge(
        workspace.workspace_id, failing.node_id, "result", sink.node_id, "value"
    )

    events = _run(model, registry, run_id="atomic_failure")
    failing_event = _settled(events, failing.node_id)
    sink_event = _settled(events, sink.node_id)

    assert failing_event["status"] == "failed"
    assert _output_result(failing_event, "result")["status"] == "failed"
    assert sink_event["status"] == "blocked"
    sink_errors = sink_event["errors"]
    assert isinstance(sink_errors, (list, tuple))
    assert [error["node_id"] for error in sink_errors] == [failing.node_id]
    assert _output_tree(
        _settled(events, independent.node_id), "value"
    ) == DataTree.from_item("independent")
    event_types = [event["type"] for event in events]
    assert "run_completed" in event_types
    assert "run_failed" not in event_types


def test_diamond_failure_deduplicates_root_error_and_independent_continues() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    failing = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_fail_source",
        "Root Failure",
        0,
        0,
    )
    left = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_passthrough",
        "Left",
        100,
        0,
    )
    right = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_passthrough",
        "Right",
        100,
        100,
    )
    join = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_diamond_join",
        "Join",
        200,
        0,
    )
    independent = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Independent",
        300,
        0,
        properties={"value": "independent"},
    )
    model.add_edge(
        workspace.workspace_id, failing.node_id, "result", left.node_id, "value"
    )
    model.add_edge(
        workspace.workspace_id, failing.node_id, "result", right.node_id, "value"
    )
    model.add_edge(workspace.workspace_id, left.node_id, "result", join.node_id, "left")
    model.add_edge(
        workspace.workspace_id, right.node_id, "result", join.node_id, "right"
    )

    events = _run(model, registry, run_id="diamond_failure")

    for branch in (left, right):
        branch_event = _settled(events, branch.node_id)
        assert branch_event["status"] == "blocked"
        assert [error["node_id"] for error in branch_event["errors"]] == [
            failing.node_id
        ]
    join_event = _settled(events, join.node_id)
    assert join_event["status"] == "blocked"
    assert [(error["node_id"], error["error"]) for error in join_event["errors"]] == [
        (failing.node_id, "capture source failed")
    ]
    assert _output_tree(
        _settled(events, independent.node_id), "value"
    ) == DataTree.from_item("independent")
    event_types = [event["type"] for event in events]
    assert "run_completed" in event_types
    assert "run_failed" not in event_types


def test_item_none_is_value_and_bad_list_output_fails_strict_validation() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    none_source = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_none_source",
        "None",
        0,
        0,
    )
    bad_list = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_bad_list",
        "Bad List",
        100,
        0,
    )

    events = _run(model, registry, run_id="strict_outputs")

    assert _output_tree(
        _settled(events, none_source.node_id), "result"
    ) == DataTree.from_item(None)
    bad_event = _settled(events, bad_list.node_id)
    assert bad_event["status"] == "failed"
    assert "non-string sequence" in bad_event["errors"][0]["error"]


def test_trigger_sample_hold_unconnected_true_and_cycle_boundary() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    source = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Source",
        0,
        0,
        properties={"value": 1},
    )
    trigger = model.add_node(
        workspace.workspace_id,
        "core.trigger",
        "Trigger",
        100,
        0,
    )
    sink = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_tree_sink",
        "Sink",
        200,
        0,
    )
    model.add_edge(
        workspace.workspace_id, source.node_id, "value", trigger.node_id, "input"
    )
    model.add_edge(
        workspace.workspace_id, trigger.node_id, "output", sink.node_id, "value"
    )

    initial = _run(model, registry, run_id="trigger_initial")
    assert _settled(initial, trigger.node_id)["status"] == "empty"
    assert _settled(initial, sink.node_id)["status"] == "empty"
    capture = dict_to_event(
        next(event for event in initial if event["type"] == "trigger_capture_settled")
    )
    assert isinstance(capture, TriggerCaptureSettledEvent)
    assert capture.result.value == DataTree.from_item(1)
    assert not any(event["type"] == "trigger_published" for event in initial)

    clicked = _run(
        model,
        registry,
        run_id="trigger_clicked",
        target_node_ids=(trigger.node_id,),
        clicked_trigger_node_id=trigger.node_id,
        trigger_captures={trigger.node_id: capture.result},
    )
    published = dict_to_event(
        next(event for event in clicked if event["type"] == "trigger_published")
    )
    assert isinstance(published, TriggerPublishedEvent)
    assert published.result.value == DataTree.from_item(1)
    assert _output_tree(
        _settled(clicked, sink.node_id), "result"
    ) == DataTree.from_item(1)
    assert not any(
        event.get("type") == "node_started" and event.get("node_id") == source.node_id
        for event in clicked
    )

    workspace.nodes[source.node_id].properties["value"] = 2
    held = _run(
        model,
        registry,
        run_id="trigger_held",
        trigger_publications={trigger.node_id: published.result},
    )
    assert _output_tree(_settled(held, sink.node_id), "result") == DataTree.from_item(1)
    latest = dict_to_event(
        next(event for event in held if event["type"] == "trigger_capture_settled")
    )
    assert isinstance(latest, TriggerCaptureSettledEvent)
    assert latest.result.value == DataTree.from_item(2)

    stale_clicked = _run(
        model,
        registry,
        run_id="trigger_stale_clicked",
        target_node_ids=(trigger.node_id,),
        clicked_trigger_node_id=trigger.node_id,
        trigger_publications={trigger.node_id: published.result},
    )
    assert any(
        event.get("type") == "node_started" and event.get("node_id") == source.node_id
        for event in stale_clicked
    )
    stale_publication = dict_to_event(
        next(event for event in stale_clicked if event["type"] == "trigger_published")
    )
    assert isinstance(stale_publication, TriggerPublishedEvent)
    assert stale_publication.result.value == DataTree.from_item(2)

    unconnected_model = GraphModel()
    unconnected = unconnected_model.add_node(
        unconnected_model.active_workspace.workspace_id,
        "core.trigger",
        "Unconnected",
        0,
        0,
    )
    unconnected_events = _run(
        unconnected_model,
        registry,
        run_id="trigger_true",
        target_node_ids=(unconnected.node_id,),
        clicked_trigger_node_id=unconnected.node_id,
    )
    unconnected_publication = dict_to_event(
        next(
            event
            for event in unconnected_events
            if event["type"] == "trigger_published"
        )
    )
    assert isinstance(unconnected_publication, TriggerPublishedEvent)
    assert unconnected_publication.result.value == DataTree.from_item(True)

    cycle_model = GraphModel()
    cycle_workspace = cycle_model.active_workspace
    cycle_trigger = cycle_model.add_node(
        cycle_workspace.workspace_id,
        "core.trigger",
        "Cycle Trigger",
        0,
        0,
    )
    passthrough = cycle_model.add_node(
        cycle_workspace.workspace_id,
        "tests.dataflow_passthrough",
        "Passthrough",
        100,
        0,
    )
    cycle_model.add_edge(
        cycle_workspace.workspace_id,
        cycle_trigger.node_id,
        "output",
        passthrough.node_id,
        "value",
    )
    cycle_model.add_edge(
        cycle_workspace.workspace_id,
        passthrough.node_id,
        "result",
        cycle_trigger.node_id,
        "input",
    )
    cycle_events = _run(cycle_model, registry, run_id="trigger_cycle")
    assert "run_completed" in [event["type"] for event in cycle_events]
    assert "run_failed" not in [event["type"] for event in cycle_events]


def test_trigger_partial_fan_in_refreshes_complete_ordered_capture() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    first = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "First",
        0,
        0,
        properties={"value": "first"},
    )
    second = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Second",
        0,
        100,
        properties={"value": "second"},
    )
    trigger = model.add_node(
        workspace.workspace_id,
        "core.trigger",
        "Trigger",
        150,
        0,
    )
    model.add_edge(
        workspace.workspace_id, first.node_id, "value", trigger.node_id, "input"
    )
    model.add_edge(
        workspace.workspace_id, second.node_id, "value", trigger.node_id, "input"
    )

    workspace.nodes[first.node_id].properties["value"] = "changed"
    events = _run(
        model,
        registry,
        run_id="trigger_partial_fan_in",
        target_node_ids=(first.node_id, trigger.node_id),
    )

    assert any(
        event.get("type") == "node_started" and event.get("node_id") == second.node_id
        for event in events
    )
    capture = dict_to_event(
        next(event for event in events if event["type"] == "trigger_capture_settled")
    )
    assert isinstance(capture, TriggerCaptureSettledEvent)
    assert capture.result.value == DataTree((((0,), ("changed", "second")),))
    assert not any(event["type"] == "trigger_published" for event in events)


def test_trigger_publishes_current_empty_and_failure_results() -> None:
    registry = _registry()
    for type_id, expected_status in (
        ("tests.dataflow_empty_source", "empty"),
        ("tests.dataflow_fail_source", "failed"),
    ):
        model = GraphModel()
        workspace = model.active_workspace
        source = model.add_node(workspace.workspace_id, type_id, "Source", 0, 0)
        trigger = model.add_node(
            workspace.workspace_id,
            "core.trigger",
            "Trigger",
            100,
            0,
        )
        model.add_edge(
            workspace.workspace_id, source.node_id, "result", trigger.node_id, "input"
        )
        captured_events = _run(model, registry, run_id=f"capture_{expected_status}")
        capture = dict_to_event(
            next(
                event
                for event in captured_events
                if event["type"] == "trigger_capture_settled"
            )
        )
        assert isinstance(capture, TriggerCaptureSettledEvent)
        assert capture.result.status == expected_status

        clicked_events = _run(
            model,
            registry,
            run_id=f"publish_{expected_status}",
            target_node_ids=(trigger.node_id,),
            clicked_trigger_node_id=trigger.node_id,
            trigger_captures={trigger.node_id: capture.result},
        )
        publication = dict_to_event(
            next(
                event
                for event in clicked_events
                if event["type"] == "trigger_published"
            )
        )
        assert isinstance(publication, TriggerPublishedEvent)
        assert publication.result.status == expected_status
        assert not any(
            event.get("type") == "node_started"
            and event.get("node_id") == source.node_id
            for event in clicked_events
        )


def test_trigger_click_refreshes_next_boundary_without_republishing_it() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    source = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Source",
        0,
        0,
        properties={"value": "held"},
    )
    first = model.add_node(workspace.workspace_id, "core.trigger", "First", 100, 0)
    second = model.add_node(workspace.workspace_id, "core.trigger", "Second", 200, 0)
    sink = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_tree_sink",
        "Sink",
        300,
        0,
    )
    model.add_edge(
        workspace.workspace_id, source.node_id, "value", first.node_id, "input"
    )
    model.add_edge(
        workspace.workspace_id, first.node_id, "output", second.node_id, "input"
    )
    model.add_edge(
        workspace.workspace_id, second.node_id, "output", sink.node_id, "value"
    )
    initial = _run(model, registry, run_id="chained_initial")
    first_capture = dict_to_event(
        next(
            event
            for event in initial
            if event["type"] == "trigger_capture_settled"
            and event["trigger_node_id"] == first.node_id
        )
    )
    assert isinstance(first_capture, TriggerCaptureSettledEvent)

    first_click = _run(
        model,
        registry,
        run_id="chained_first_click",
        target_node_ids=(first.node_id,),
        clicked_trigger_node_id=first.node_id,
        trigger_captures={first.node_id: first_capture.result},
    )
    assert not any(
        event.get("type") == "node_started" and event.get("node_id") == second.node_id
        for event in first_click
    )
    assert not any(event.get("node_id") == sink.node_id for event in first_click)
    assert not any(
        event["type"] == "trigger_published"
        and event["trigger_node_id"] == second.node_id
        for event in first_click
    )
    second_capture = dict_to_event(
        next(
            event
            for event in first_click
            if event["type"] == "trigger_capture_settled"
            and event["trigger_node_id"] == second.node_id
        )
    )
    assert isinstance(second_capture, TriggerCaptureSettledEvent)
    assert second_capture.result.value == DataTree.from_item("held")

    second_click = _run(
        model,
        registry,
        run_id="chained_second_click",
        target_node_ids=(second.node_id,),
        clicked_trigger_node_id=second.node_id,
        trigger_publications={first.node_id: first_capture.result},
        trigger_captures={second.node_id: second_capture.result},
    )
    assert not any(
        event.get("type") == "node_started" and event.get("node_id") == first.node_id
        for event in second_click
    )
    assert _output_tree(
        _settled(second_click, sink.node_id), "result"
    ) == DataTree.from_item("held")


def test_trigger_pending_publication_is_cancelled_by_stop_or_infrastructure_failure() -> (
    None
):
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    trigger = model.add_node(workspace.workspace_id, "core.trigger", "Trigger", 0, 0)

    def request_stop(executor) -> None:  # noqa: ANN001
        executor._control.stop_requested = True  # noqa: SLF001
        executor._control.stop_reason = "test_stop"  # noqa: SLF001

    with mock.patch(
        "ea_node_editor.execution.worker_runner.NodeExecutor.refresh_trigger_captures",
        request_stop,
    ):
        stopped = _run(
            model,
            registry,
            run_id="trigger_cancel_stop",
            target_node_ids=(trigger.node_id,),
            clicked_trigger_node_id=trigger.node_id,
        )
    assert any(event["type"] == "run_stopped" for event in stopped)
    assert not any(event["type"] == "trigger_published" for event in stopped)

    with mock.patch(
        "ea_node_editor.execution.worker_runner.NodeExecutor.refresh_trigger_captures",
        side_effect=RuntimeError("infrastructure failure"),
    ):
        failed = _run(
            model,
            registry,
            run_id="trigger_cancel_failure",
            target_node_ids=(trigger.node_id,),
            clicked_trigger_node_id=trigger.node_id,
        )
    assert any(event["type"] == "run_failed" for event in failed)
    assert not any(event["type"] == "trigger_published" for event in failed)


def test_ordinary_cycle_is_rejected_before_execution() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = _registry()
    first = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_passthrough",
        "First",
        0,
        0,
    )
    second = model.add_node(
        workspace.workspace_id,
        "tests.dataflow_passthrough",
        "Second",
        100,
        0,
    )
    model.add_edge(
        workspace.workspace_id, first.node_id, "result", second.node_id, "value"
    )
    model.add_edge(
        workspace.workspace_id, second.node_id, "result", first.node_id, "value"
    )

    events = _run(model, registry, run_id="cycle")

    failed = next(event for event in events if event["type"] == "run_failed")
    assert "Cycle detected" in failed["error"]
    assert not any(event["type"] == "node_started" for event in events)
