from __future__ import annotations

import pytest

from ea_node_editor.nodes.bootstrap import build_builtin_registry, build_default_registry
from ea_node_editor.nodes.builtins.core import (
    DEFAULT_STREAM_GATE_OUTPUT_IDS,
    PYTHON_SCRIPT_DEFAULT_SOURCE,
    STREAM_GATE_OUTPUT_IDS_PROPERTY,
    PythonScriptNodePlugin,
    StreamGateNodePlugin,
    TriggerNodePlugin,
    normalize_stream_gate_output_ids,
    stream_gate_index,
)
from ea_node_editor.nodes.builtins.icon_catalog import BUILTIN_NODE_ICONS
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.subnode_contract import (
    SUBNODE_INPUT_TYPE_ID,
    SUBNODE_OUTPUT_TYPE_ID,
    SUBNODE_PIN_DATA_ACCESS_PROPERTY,
    SUBNODE_PIN_DATA_ACCESS_VALUES,
)
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.instance_resolution import resolve_instance_ports
from ea_node_editor.runtime_contracts import DataTree


def _context(
    *,
    inputs: dict[str, object] | None = None,
    properties: dict[str, object] | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="node",
        workspace_id="workspace",
        inputs=dict(inputs or {}),
        properties=dict(properties or {}),
        emit_log=lambda _level, _message: None,
    )


def test_builtin_catalog_contains_only_data_and_passive_flow_ports() -> None:
    registry = build_builtin_registry()
    specs = registry.all_specs()
    type_ids = {spec.type_id for spec in specs}

    assert {"core.trigger", "core.if", "core.stream_gate"} <= type_ids
    retired = {"core.start", "core.end", "core.branch", "core.on_failure", "hpc.on_status"}
    assert not retired & type_ids
    assert not retired & set(BUILTIN_NODE_ICONS)
    assert "core.trigger" not in BUILTIN_NODE_ICONS
    assert {port.kind for spec in specs for port in spec.ports} <= {"data", "flow"}


def test_full_default_registry_has_no_control_ports_or_active_multi_connection_flags() -> None:
    specs = build_default_registry().all_specs()
    ports = tuple(port for spec in specs for port in spec.ports)

    assert {port.kind for port in ports} <= {"data", "flow"}
    assert all(not port.allow_multiple_connections or port.kind == "flow" for port in ports)


def test_trigger_is_iconless_compact_tree_boundary() -> None:
    plugin = TriggerNodePlugin()
    spec = plugin.spec()
    ports = {port.key: port for port in spec.ports}

    assert spec.icon == ""
    assert spec.collapsible is False
    assert spec.surface_variant == "trigger"
    assert ports["input"].data_access == "tree"
    assert ports["input"].required is False
    assert ports["output"].data_access == "tree"

    unconnected = plugin.execute(_context()).outputs["output"]
    assert unconnected == DataTree.from_item(True)
    tree = DataTree({(2,): ("latest",)})
    assert plugin.execute(_context(inputs={"input": tree})).outputs == {"output": tree}


def test_subnode_pin_descriptors_publish_hidden_data_access_metadata() -> None:
    registry = build_builtin_registry()

    for type_id in (SUBNODE_INPUT_TYPE_ID, SUBNODE_OUTPUT_TYPE_ID):
        spec = registry.get_spec(type_id)
        properties = {prop.key: prop for prop in spec.properties}
        access = properties[SUBNODE_PIN_DATA_ACCESS_PROPERTY]
        assert access.type == "enum"
        assert access.default == "item"
        assert access.enum_values == SUBNODE_PIN_DATA_ACCESS_VALUES
        assert access.inspector_visible is False


def test_python_script_default_source_declares_instance_ports() -> None:
    registry = build_builtin_registry()
    spec = registry.get_spec("core.python_script")
    properties = {prop.key: prop for prop in spec.properties}

    assert spec.ports == ()
    assert set(properties) == {"script", "timeout_sec"}
    assert "@corex.node" in PYTHON_SCRIPT_DEFAULT_SOURCE
    for decorator in (
        "input",
        "output",
        "text",
        "number",
        "switch",
        "dropdown",
        "slider",
        "color",
        "path",
        "text_area",
        "interval",
        "list",
    ):
        assert f"# @corex.{decorator}" in PYTHON_SCRIPT_DEFAULT_SOURCE
    assert "uncomment a line" in PYTHON_SCRIPT_DEFAULT_SOURCE
    assert "add its name to run(ctx, ...)" in PYTHON_SCRIPT_DEFAULT_SOURCE
    assert spec.dynamic_port_groups == ()
    assert spec.instance_spec_resolver is not None

    defaults = registry.default_properties("core.python_script")
    assert [port.key for port in resolve_instance_ports(spec, defaults)] == [
        "payload",
        "result",
    ]
    resolved = registry.resolve_spec("core.python_script", defaults)
    assert resolved.instance_spec_resolver is None
    assert [port.direction for port in resolved.ports] == ["in", "out"]


def test_python_script_apply_reconciles_decorated_settings_and_ports() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    node = mutations.add_node(
        type_id="core.python_script",
        title="Script",
        x=0,
        y=0,
        properties={},
    )
    source = '''@corex.node
@corex.input("values", value_type=float, structure="tree", required=True, section="Data")
@corex.output("result", value_type=float)
@corex.dropdown("mode", default="Mean", options=("Mean", "Max"), section="Settings", port=True)
@corex.slider("scale", default=2.0, minimum=0.5, maximum=8.0, step=0.5, section="Settings", port=True)
def run(ctx, values, mode, scale):
    return {"result": scale}
'''
    reset_keys, removed_edges = mutations.apply_python_script(node.node_id, source)
    assert reset_keys == ()
    assert removed_edges == ()
    assert node.properties["mode"] == "Mean"
    assert node.properties["scale"] == 2.0
    resolved = registry.resolve_spec(node.type_id, node.properties)
    assert [port.key for port in resolved.ports] == ["values", "result", "mode", "scale"]
    assert [(group.group_id, group.label) for group in resolved.settings_groups] == [
        ("data", "Data"),
        ("settings", "Settings"),
    ]


def test_python_script_executes_decorated_run_function() -> None:
    plugin = PythonScriptNodePlugin()
    assert plugin.execute(
        _context(
            inputs={"payload": "default"},
            properties={"script": PYTHON_SCRIPT_DEFAULT_SOURCE},
        )
    ).outputs == {"result": "default"}

    properties = {"script": '''@corex.node
@corex.input("payload", value_type=int)
@corex.output("result", value_type=corex.Any)
@corex.output("explicit_none", value_type=corex.Any)
@corex.output("unassigned", value_type=corex.Any)
@corex.number("factor", default=3, port=True)
def run(ctx, payload, factor):
    return {"result": [payload * item for item in range(factor)], "explicit_none": None}
''', "factor": 3}
    assert plugin.execute(
        _context(inputs={"payload": 4}, properties=properties)
    ).outputs == {
        "result": [0, 4, 8],
        "explicit_none": None,
    }
    with pytest.raises(RuntimeError, match="undeclared outputs"):
        plugin.execute(
            _context(
                properties={
                    "script": '''@corex.node
@corex.output("result", value_type=corex.Any)
def run(ctx):
    return {"unknown": 1}
'''
                }
            )
        )


def test_stream_gate_uses_stable_output_ids_and_publishes_only_selected_tree() -> None:
    plugin = StreamGateNodePlugin()
    spec = plugin.spec()
    properties = {prop.key: prop for prop in spec.properties}
    ports = {
        port.key: port
        for port in resolve_instance_ports(
            spec,
            {STREAM_GATE_OUTPUT_IDS_PROPERTY: properties[STREAM_GATE_OUTPUT_IDS_PROPERTY].default},
        )
    }

    assert tuple(port_id for port_id in DEFAULT_STREAM_GATE_OUTPUT_IDS) == ("output_0", "output_1")
    assert properties[STREAM_GATE_OUTPUT_IDS_PROPERTY].default == ["output_0", "output_1"]
    assert properties[STREAM_GATE_OUTPUT_IDS_PROPERTY].inspector_visible is False
    assert tuple(port.key for port in spec.ports) == ("stream", "gate")
    assert len(spec.dynamic_port_groups) == 1
    group = spec.dynamic_port_groups[0]
    assert (group.group_id, group.property_key, group.direction) == (
        "outputs",
        STREAM_GATE_OUTPUT_IDS_PROPERTY,
        "out",
    )
    assert group.minimum == 1
    assert group.maximum is None
    assert group.rename_mode == "label"
    assert ports["stream"].data_access == "tree"
    assert ports["gate"].data_access == "item"
    assert ports["output_0"].data_access == "tree"
    assert ports["output_1"].data_access == "tree"
    assert ports["output_0"].label == "Output 0"
    assert ports["output_1"].label == "Output 1"
    assert normalize_stream_gate_output_ids(None) == DEFAULT_STREAM_GATE_OUTPUT_IDS
    assert normalize_stream_gate_output_ids(("only",)) == DEFAULT_STREAM_GATE_OUTPUT_IDS
    assert normalize_stream_gate_output_ids([]) == DEFAULT_STREAM_GATE_OUTPUT_IDS
    assert normalize_stream_gate_output_ids(["  "]) == DEFAULT_STREAM_GATE_OUTPUT_IDS
    assert normalize_stream_gate_output_ids(["only"]) == ("only",)

    tree = DataTree({(3, 2): ("value",)})
    result = plugin.execute(
        _context(
            inputs={"stream": tree, "gate": 1.5},
            properties={STREAM_GATE_OUTPUT_IDS_PROPERTY: ["stable-a", "stable-b", "stable-c"]},
        )
    )
    assert result.outputs == {"stable-c": tree}


@pytest.mark.parametrize(
    ("value", "expected"),
    ((0.49, 0), (0.5, 1), (1.5, 2), (-0.49, 0), (-0.5, -1), (-1.5, -2)),
)
def test_stream_gate_rounds_midpoints_away_from_zero(value: float, expected: int) -> None:
    assert stream_gate_index(value) == expected


@pytest.mark.parametrize("value", (True, False, float("inf"), float("nan"), "1", "not-a-number"))
def test_stream_gate_rejects_non_numeric_or_non_finite_gate(value: object) -> None:
    with pytest.raises(ValueError):
        stream_gate_index(value)


def test_stream_gate_fails_for_out_of_range_output() -> None:
    with pytest.raises(ValueError, match="outside 0..1"):
        StreamGateNodePlugin().execute(
            _context(inputs={"stream": DataTree.from_item("value"), "gate": -0.5})
        )
