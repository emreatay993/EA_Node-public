# Purpose: Prove public and dynamic type-forwarding declaration validation and identities.
# Map: subsystems/nodes_registry_builtins.md
# Tests: this file

from __future__ import annotations

from dataclasses import replace

import corex
import pytest

from ea_node_editor.nodes.builtins.core import StreamGateNodePlugin, TriggerNodePlugin
from ea_node_editor.nodes.instance_resolution import resolve_instance_ports
from ea_node_editor.nodes.node_specs import DynamicPortGroupSpec, NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.nodes.plugin_declaration import PluginDeclarationError, discover_plugin_declarations
from ea_node_editor.nodes.python_script_declaration import PythonScriptDeclarationError, resolve_python_script_spec
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.spec_validation import validate_node_spec
from ea_node_editor.runtime_contracts import GRAPH_DATA_TYPE_ID, STRING_DATA_TYPE_ID

ANY = GRAPH_DATA_TYPE_ID


def _spec(ports=None, **kwargs):
    return NodeTypeSpec("tests.forwarding", "Forwarding", ("Tests",), "", ports or (
        PortSpec("input", "in", "data", ANY, required=False, data_access="tree"),
        PortSpec("output", "out", "data", ANY, data_access="tree", type_from_input="input"),
    ), (), **kwargs)


def test_forwarding_default_and_runtime_decorator():
    assert PortSpec("output", "out", "data", ANY).type_from_input == ""

    @corex.output("output", value_type=corex.Any, type_from_input="input")
    def forward(value):
        return value

    assert forward(42) == 42


@pytest.mark.parametrize("invalid", [None, 1, " input "])
def test_forwarding_requires_trimmed_string(invalid):
    with pytest.raises((TypeError, ValueError), match="type_from_input"):
        PortSpec("output", "out", "data", ANY, type_from_input=invalid)


@pytest.mark.parametrize("change, expected", [
    ({"type_from_input": "missing"}, "missing input"),
    ({"type_from_input": "output"}, "Any data input"),
    ({"direction": "in", "required": False}, "Any data output"),
    ({"kind": "flow"}, "Any data output"),
    ({"data_type": STRING_DATA_TYPE_ID}, "Any data output"),
    ({"data_access": "item"}, "matching"),
])
def test_static_forwarding_rejects_invalid_output_relationships(change, expected):
    spec = _spec()
    spec = replace(spec, ports=(spec.ports[0], replace(spec.ports[1], **change)))
    with pytest.raises(ValueError, match=expected):
        validate_node_spec(spec, data_types=NodeRegistry().data_types)


@pytest.mark.parametrize("change", [
    {"direction": "out", "required": False}, {"kind": "flow", "required": False},
    {"data_type": STRING_DATA_TYPE_ID},
])
def test_static_forwarding_rejects_non_any_data_inputs(change):
    spec = _spec()
    spec = replace(spec, ports=(replace(spec.ports[0], **change), spec.ports[1]))
    with pytest.raises(ValueError, match="Any data input"):
        resolve_instance_ports(spec, {})


def test_dynamic_forwarding_checks_actual_resolved_ports_and_cross_group_references():
    def inputs(properties):
        return (PortSpec(properties["input_ids"][0], "in", "data", ANY, required=False),)

    def outputs(properties):
        return (PortSpec("output", "out", "data", ANY, type_from_input="input"),)

    spec = NodeTypeSpec("tests.dynamic_forward", "Dynamic", ("Tests",), "", (), (
        PropertySpec("input_ids", "json", ["input"], "Inputs", inspector_visible=False),
        PropertySpec("output_ids", "json", ["output"], "Outputs", inspector_visible=False),
    ), dynamic_port_groups=(
        DynamicPortGroupSpec("outputs", "output_ids", "out", outputs, lambda _: "output"),
        DynamicPortGroupSpec("inputs", "input_ids", "in", inputs, lambda _: "input"),
    ))
    validate_node_spec(spec, data_types=NodeRegistry().data_types)
    assert resolve_instance_ports(spec, {})[0].type_from_input == "input"
    with pytest.raises(ValueError, match="missing input"):
        resolve_instance_ports(spec, {"input_ids": ["renamed"]})


def _source(*, relationship="input", output_type="corex.Any", output_structure="tree", script=False):
    node = "@corex.node" if script else '@corex.node(id="custom.forward.a1234567", name="Forward", category=("Tests",))'
    name = "run" if script else "forward"
    return f'''import corex
{node}
@corex.input("input", value_type=corex.Any, structure="tree")
@corex.output("output", value_type={output_type}, structure="{output_structure}", type_from_input="{relationship}")
def {name}(ctx, input):
    raise AssertionError("Declaration discovery must not execute the source")
'''


@pytest.mark.parametrize("script", [False, True])
def test_public_and_script_declarations_support_forwarding(script):
    source = _source(script=script)
    if script:
        spec = resolve_python_script_spec(_spec(), {"script": source})
    else:
        spec = discover_plugin_declarations(source)[0].spec
    assert spec.ports[1].type_from_input == "input"
    assert spec.ports[1].data_type == ANY


@pytest.mark.parametrize("script", [False, True])
@pytest.mark.parametrize("kwargs, expected", [
    ({"relationship": "missing"}, "missing input"),
    ({"output_type": "str"}, "Any data output"),
    ({"output_structure": "item"}, "matching"),
])
def test_public_and_script_declarations_reject_invalid_forwarding_at_discovery(script, kwargs, expected):
    source = _source(script=script, **kwargs)
    if script:
        with pytest.raises(PythonScriptDeclarationError, match=expected):
            resolve_python_script_spec(_spec(), {"script": source})
    else:
        with pytest.raises(PluginDeclarationError, match=expected):
            discover_plugin_declarations(source)


class _Plugin:
    def __init__(self, spec):
        self._spec = spec

    def spec(self):
        return self._spec

    def execute(self, _ctx):
        raise AssertionError("Registry identity must not execute nodes")


def _registry(spec):
    registry = NodeRegistry()
    registry.register(lambda: _Plugin(spec))
    return registry


def test_registry_fingerprint_includes_static_forwarding():
    spec = _spec()
    plain = replace(spec, ports=(spec.ports[0], replace(spec.ports[1], type_from_input="")))
    assert _registry(spec).contract_fingerprint() != _registry(plain).contract_fingerprint()


def test_registry_fingerprint_includes_default_resolved_stream_gate_forwarding():
    forwarding = False
    spec = StreamGateNodePlugin().spec()
    original_outputs = spec.dynamic_port_groups[0].ports_resolver

    def outputs(properties):
        return tuple(
            replace(port, type_from_input=port.type_from_input if forwarding else "")
            for port in original_outputs(properties)
        )

    spec = replace(spec, dynamic_port_groups=(replace(spec.dynamic_port_groups[0], ports_resolver=outputs),))
    before = _registry(spec).contract_fingerprint()
    forwarding = True
    after = _registry(spec).contract_fingerprint()
    assert before != after


def test_trigger_and_every_stream_gate_output_declare_forwarding():
    assert TriggerNodePlugin().spec().ports[1].type_from_input == "input"
    gate = StreamGateNodePlugin().spec()
    for keys in (["output_0", "output_1"], ["one", "two", "three"]):
        outputs = [port for port in resolve_instance_ports(gate, {"output_port_ids": keys}) if port.direction == "out"]
        assert [port.key for port in outputs] == keys
        assert {port.type_from_input for port in outputs} == {"stream"}
