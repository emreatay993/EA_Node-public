# Purpose: Prove topology-derived forwarding contracts without changing runtime declarations.
# Map: subsystems/graph_domain.md
# Tests: this file

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from ea_node_editor.graph.effective_ports import EffectivePort, port_compatibility
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.graph.type_forwarding import (
    GraphTypeResolver, ResolvedSourceContract, source_port_compatibility,
)
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.node_specs import PortSpec
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    DataConversionSpec,
    DOUBLE_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID, INTEGER_DATA_TYPE_ID, STRING_DATA_TYPE_ID,
)

IMAGE = "COREX.DataTypes.Image"
ANY = GRAPH_DATA_TYPE_ID


@pytest.fixture(scope="module")
def registry():
    return build_builtin_registry()


def _node(key, type_id="core.trigger", **kwargs):
    return NodeInstance(key, type_id, key, 0, 0, **kwargs)


def _edge(source, target, *, source_port="output", target_port="input", enabled=True):
    return EdgeInstance(f"{source}:{source_port}>{target}:{target_port}", source, source_port,
                        target, target_port, enabled=enabled)


def _source_port(type_id):
    return EffectivePort("output", "Output", "out", "data", type_id, data_access="tree")


def _resolve(registry, nodes, edges, **kwargs):
    return GraphTypeResolver(registry=registry, workspace_nodes={node.node_id: node for node in nodes},
                             workspace_edges=edges, **kwargs)


def test_plot_panel_trigger_and_stream_gate_preserve_image_but_not_input_acceptance(registry):
    nodes = [_node("plot", "plot.signal"), _node("panel", "data.panel"), _node("trigger"),
             _node("gate", "core.stream_gate", properties={"output_port_ids": ["left", "right", "extra"]})]
    edges = [_edge("plot", "panel", source_port="image"), _edge("panel", "trigger"),
             _edge("trigger", "gate", target_port="stream")]
    resolver = _resolve(registry, nodes, edges)
    assert resolver.source_contract("plot", "image").type_ids == (IMAGE,)
    for node, key in (("panel", "output"), ("trigger", "output"), ("gate", "left"),
                      ("gate", "right"), ("gate", "extra")):
        assert resolver.source_contract(node, key) == ResolvedSourceContract((IMAGE,))
        assert resolver.port(node, key).data_type == ANY
    assert resolver.port("panel", "input").data_type == ANY
    assert resolver.port("trigger", "input").accepted_data_types == ()
    assert resolver.port("gate", "left").type_from_input == "stream"


def test_mixed_sources_are_distinct_and_every_member_must_match_target_union(registry):
    nodes = [_node("int", "test.source"), _node("double", "test.source"), _node("join"), _node("next")]
    edges = [_edge("int", "join"), _edge("double", "join"), _edge("join", "next")]
    resolver = _resolve(registry, nodes, edges, ports_by_node_id={
        "int": (_source_port(INTEGER_DATA_TYPE_ID),), "double": (_source_port(DOUBLE_DATA_TYPE_ID),),
    })
    contract = resolver.source_contract("next", "output")
    assert contract.type_ids == tuple(sorted((INTEGER_DATA_TYPE_ID, DOUBLE_DATA_TYPE_ID)))
    target = PortSpec("value", "in", "data", DOUBLE_DATA_TYPE_ID,
                      required=True, accepted_data_types=(INTEGER_DATA_TYPE_ID,))
    result = resolver.compatibility("next", "output", target)
    assert result.status == "assignable"
    assert result.is_compatible
    assert len(result.members) == 2
    assert {member.reason_code for member in result.members} == {"exact"}
    assert {member.matched_type_id for member in result.members} == set(contract.type_ids)
    mixed = replace(contract, type_ids=(IMAGE, INTEGER_DATA_TYPE_ID))
    for target_type in (IMAGE, DOUBLE_DATA_TYPE_ID):
        result = source_port_compatibility(_source_port(ANY), replace(target, data_type=target_type,
                                            accepted_data_types=()), data_types=registry.data_types,
                                            source_contract=mixed)
        assert result.status == "incompatible"
        assert not result.is_compatible


def test_single_source_retains_exact_catalog_conversion_and_runtime_check_evidence(registry):
    target = PortSpec("value", "in", "data", DOUBLE_DATA_TYPE_ID, required=True)
    for type_id in (INTEGER_DATA_TYPE_ID, DOUBLE_DATA_TYPE_ID, ANY, IMAGE, "Missing.Type"):
        source = _source_port(type_id)
        scalar = port_compatibility(source, target, data_types=registry.data_types)
        result = source_port_compatibility(source, target, data_types=registry.data_types)
        assert result.members == (scalar,)
        assert result.worst_match == scalar
        assert result.is_compatible == scalar.is_compatible
    conversion_registry = NodeRegistry()
    conversion_registry.data_types.register_many(
        conversions=(DataConversionSpec(INTEGER_DATA_TYPE_ID, DOUBLE_DATA_TYPE_ID, float),),
        owner_id="tests.forwarding_conversion",
    )
    converted = source_port_compatibility(_source_port(INTEGER_DATA_TYPE_ID), target,
                                         data_types=conversion_registry.data_types)
    assert converted.status == "convertible"
    assert converted.worst_match.reason_code == "direct_conversion"
    flow = PortSpec("flow", "out", "flow", "flow")
    flow_target = replace(flow, direction="in")
    assert source_port_compatibility(flow, flow_target, data_types=registry.data_types).members == (
        port_compatibility(flow, flow_target, data_types=registry.data_types),
    )
    assert not source_port_compatibility(flow, target, data_types=registry.data_types).is_compatible


def test_disconnected_disabled_and_authored_values_remain_generic(registry):
    nodes = [_node("plot", "plot.signal"), _node("panel", "data.panel", properties={"value": "123"})]
    resolver = _resolve(registry, nodes, [_edge("plot", "panel", source_port="image", enabled=False)])
    assert resolver.source_contract("panel", "output") == ResolvedSourceContract((ANY,))
    target = PortSpec("image", "in", "data", IMAGE, required=True)
    assert resolver.compatibility("panel", "output", target).status == "runtime_check"


def test_unresolved_source_metadata_does_not_become_any(registry):
    nodes = [_node("plot", "plot.signal"), _node("trigger")]
    resolver = _resolve(registry, nodes, [_edge("plot", "trigger", source_port="image"),
                                         _edge("missing", "trigger")])
    contract = resolver.source_contract("trigger", "output")
    assert contract.type_ids == (IMAGE,)
    assert contract.has_unresolved_sources
    assert resolver.compatibility("trigger", "output", _source_port(IMAGE)).status == "unresolved"
    assert resolver.source_contract("missing", "output") == ResolvedSourceContract((), True)
    unknown = _resolve(registry, [_node("source", "test.source"), _node("trigger")],
                       [_edge("source", "trigger")],
                       ports_by_node_id={"source": (_source_port("Missing.Type"),)})
    assert unknown.source_contract("trigger", "output").type_ids == ("Missing.Type",)
    assert unknown.compatibility("trigger", "output", _source_port(ANY)).status == "unresolved"


def test_cycles_are_conservative_and_independent_of_node_order(registry):
    nodes = [_node("plot", "plot.signal"), _node("a"), _node("b"), _node("c")]
    edges = [_edge("plot", "a", source_port="image"), _edge("a", "b"),
             _edge("b", "a"), _edge("b", "c")]
    for ordered_nodes in (nodes, list(reversed(nodes))):
        resolver = _resolve(registry, ordered_nodes, edges)
        for key in ("a", "b", "c"):
            assert resolver.source_contract(key, "output") == ResolvedSourceContract((ANY, IMAGE))


def test_long_chain_resolves_without_recursion_and_reuses_snapshot(registry):
    nodes = [_node("plot", "plot.signal")] + [_node(str(index)) for index in range(1500)]
    edges = [_edge("plot", "0", source_port="image")] + [
        _edge(str(index), str(index + 1)) for index in range(1499)
    ]
    with patch.object(registry, "resolve_spec", wraps=registry.resolve_spec) as resolve_spec:
        resolver = _resolve(registry, list(reversed(nodes)), edges)
        before = resolve_spec.call_count
        contract = resolver.source_contract("1499", "output")
        assert contract == ResolvedSourceContract((IMAGE,))
        for _ in range(40):
            assert resolver.source_contract("1499", "output") is contract
            assert resolver.compatibility("1499", "output", _source_port(IMAGE)).is_compatible
        assert resolve_spec.call_count == before == len(nodes)
    edges[0].enabled = False
    assert resolver.source_contract("1499", "output") == contract
    assert _resolve(registry, nodes, edges).source_contract("1499", "output").type_ids == (ANY,)


def test_nested_any_subnode_boundaries_forward_and_typed_boundaries_remain_declared(registry):
    nodes = [_node("plot", "plot.signal"), _node("shell", "core.subnode"),
             _node("in_pin", "core.subnode_input", parent_node_id="shell"),
             _node("nested", "core.subnode", parent_node_id="shell"),
             _node("nested_in", "core.subnode_input", parent_node_id="nested"),
             _node("relay", parent_node_id="nested"),
             _node("nested_out", "core.subnode_output", parent_node_id="nested"),
             _node("out_pin", "core.subnode_output", parent_node_id="shell"), _node("tail")]
    edges = [_edge("plot", "shell", source_port="image", target_port="in_pin"),
             _edge("in_pin", "nested", source_port="pin", target_port="nested_in"),
             _edge("nested_in", "relay", source_port="pin"),
             _edge("relay", "nested_out", target_port="pin"),
             _edge("nested", "out_pin", source_port="nested_out", target_port="pin"),
             _edge("shell", "tail", source_port="out_pin")]
    resolver = _resolve(registry, nodes, edges)
    assert resolver.source_contract("tail", "output").type_ids == (IMAGE,)
    assert resolver.source_contract("nested_in", "pin").type_ids == (IMAGE,)
    nodes[-2].properties["data_type"] = STRING_DATA_TYPE_ID
    assert _resolve(registry, nodes, edges).source_contract("tail", "output").type_ids == (STRING_DATA_TYPE_ID,)
    orphan = _resolve(registry, [_node("orphan", "core.subnode_input")], [])
    assert orphan.source_contract("orphan", "pin").has_unresolved_sources


def test_instance_script_opt_in_is_static_and_other_scripts_remain_generic(registry):
    source = '''@corex.node
@corex.input("input", value_type=corex.Any, structure="tree")
@corex.output("output", value_type=corex.Any, structure="tree", type_from_input="input")
def run(ctx, input):
    raise AssertionError("Type inference must not execute this source")
'''
    nodes = [_node("plot", "plot.signal"), _node("script", "core.python_script", properties={"script": source})]
    edges = [_edge("plot", "script", source_port="image")]
    assert _resolve(registry, nodes, edges).source_contract("script", "output").type_ids == (IMAGE,)
    nodes[1].properties["script"] = source.replace(', type_from_input="input"', '')
    assert _resolve(registry, nodes, edges).source_contract("script", "output").type_ids == (ANY,)
