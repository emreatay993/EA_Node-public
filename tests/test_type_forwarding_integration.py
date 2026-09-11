# Purpose: Prove forwarding contracts across graph edits, compilation, persistence and runtime identity.
# Map: subsystems/graph_domain.md
# Tests: this file

from dataclasses import replace

import pytest

from ea_node_editor.execution.compiler import compile_runtime_workspace_snapshot
from ea_node_editor.execution.execution_plan import ExecutionPlan
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.solution_identity import assemble_node_solution
from ea_node_editor.execution.worker_runner import NodeExecutor
from ea_node_editor.graph.fragment_payloads import build_graph_fragment_payload, graph_fragment_payload_is_valid
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import EdgeInstance
from ea_node_editor.graph.record_payloads import node_instance_to_mapping
from ea_node_editor.graph.registry_normalization import normalize_project_for_registry
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import (
    DOUBLE_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID, INTEGER_DATA_TYPE_ID, STRING_DATA_TYPE_ID,
    DataConversionSpec, DataTree,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory

IMAGE = "COREX.DataTypes.Image"


@pytest.fixture
def graph():
    registry = build_builtin_registry()
    for name, type_id, direction in (("image", IMAGE, "out"), ("integer", INTEGER_DATA_TYPE_ID, "out"),
                                     ("decimal", DOUBLE_DATA_TYPE_ID, "out"), ("any", GRAPH_DATA_TYPE_ID, "out"),
                                     ("image_sink", IMAGE, "in"), ("number_sink", DOUBLE_DATA_TYPE_ID, "in")):
        spec = NodeTypeSpec(type_id=f"tests.{name}", display_name=name, category_path=("Tests",), icon="",
                            ports=(PortSpec("value", direction, "data", type_id,
                                            required=True if direction == "in" else None,
                                            accepted_data_types=(INTEGER_DATA_TYPE_ID,) if name == "number_sink" else ()),),
                            properties=())
        class Plugin:
            def __init__(self, declared):
                self.declared = declared

            def spec(self):
                return self.declared
        registry.register(lambda declared=spec: Plugin(declared))
    model = GraphModel()
    workspace = model.active_workspace
    mutation = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    return registry, model, workspace, mutation


def add(mutation, name, **kwargs):
    return mutation.add_node(type_id=name if "." in name else f"tests.{name}", title=name, x=0, y=0, **kwargs)


def wire(mutation, source, target, source_port="value", target_port="input", **kwargs):
    return mutation.add_edge(source_node_id=source.node_id, source_port_key=source_port,
                             target_node_id=target.node_id, target_port_key=target_port, **kwargs)


def runtime(registry, model):
    workspace_id = model.active_workspace.workspace_id
    return build_runtime_snapshot(model.project, workspace_id=workspace_id, registry=registry).workspace(workspace_id)


def test_replace_and_append_prune_whole_chain_in_one_undo(graph):
    registry, model, workspace, mutation = graph
    image, integer = add(mutation, "image"), add(mutation, "integer")
    panel, trigger = add(mutation, "data.panel"), add(mutation, "core.trigger")
    sink = add(mutation, "image_sink")
    original = wire(mutation, image, panel)
    wire(mutation, panel, trigger, "output")
    downstream = wire(mutation, trigger, sink, "output", "value")
    history = RuntimeGraphHistory()
    before = history.capture_workspace(workspace)
    replacement = wire(mutation, integer, panel)
    history.record_action(workspace.workspace_id, "Connect", before, workspace)
    assert original.edge_id not in workspace.edges
    assert downstream.edge_id not in workspace.edges
    assert replacement.edge_id in workspace.edges
    assert history.undo_depth(workspace.workspace_id) == 1
    history.undo_workspace(workspace.workspace_id, workspace)
    assert {original.edge_id, downstream.edge_id} <= workspace.edges.keys()
    assert mutation.kernel.type_resolver().source_contract(trigger.node_id, "output").type_ids == (IMAGE,)
    history.redo_workspace(workspace.workspace_id, workspace)
    assert downstream.edge_id not in workspace.edges
    history.undo_workspace(workspace.workspace_id, workspace)
    wire(mutation, integer, panel, append_requested=True)
    assert original.edge_id in workspace.edges
    assert downstream.edge_id not in workspace.edges


def test_mixed_union_is_accepted_and_failed_connection_is_atomic(graph):
    _, _, workspace, mutation = graph
    integer, decimal, image = (add(mutation, name) for name in ("integer", "decimal", "image"))
    relay, sink = add(mutation, "core.trigger"), add(mutation, "number_sink")
    wire(mutation, integer, relay)
    wire(mutation, decimal, relay, append_requested=True)
    accepted = wire(mutation, relay, sink, "output", "value")
    before = workspace.capture_snapshot()
    with pytest.raises(ValueError, match="Incompatible data types"):
        wire(mutation, image, sink, target_port="value")
    assert workspace.capture_snapshot() == before
    assert accepted.edge_id in workspace.edges


def test_disable_enable_and_batch_preflight_use_proposed_topology(graph):
    _, _, workspace, mutation = graph
    image, integer = add(mutation, "image"), add(mutation, "integer")
    relay, sink = add(mutation, "core.trigger"), add(mutation, "image_sink")
    upstream = wire(mutation, image, relay)
    downstream = wire(mutation, relay, sink, "output", "value")
    assert mutation.set_edge_enabled(upstream.edge_id, False)
    assert mutation.kernel.type_resolver().source_contract(relay.node_id, "output").type_ids == (GRAPH_DATA_TYPE_ID,)
    assert downstream.edge_id in workspace.edges
    integer_edge = EdgeInstance("integer-disabled", integer.node_id, "value", relay.node_id, "input", enabled=False)
    workspace.edges[integer_edge.edge_id] = integer_edge
    assert mutation.set_edge_enabled(integer_edge.edge_id, True)
    assert downstream.edge_id not in workspace.edges
    # Re-enabling an incompatible downstream wire in the same batch fails atomically.
    downstream.enabled = False
    workspace.edges[downstream.edge_id] = downstream
    before = workspace.capture_snapshot()
    assert not mutation.set_edges_enabled([upstream.edge_id, downstream.edge_id], True)
    assert workspace.capture_snapshot() == before


def test_rewire_batch_prunes_downstream_and_keeps_edge_identity(graph):
    _, _, workspace, mutation = graph
    image, integer = add(mutation, "image"), add(mutation, "integer")
    relay, sink = add(mutation, "core.trigger"), add(mutation, "image_sink")
    upstream = wire(mutation, image, relay)
    downstream = wire(mutation, relay, sink, "output", "value")
    assert mutation.rewire_edges([upstream.edge_id], "source", integer.node_id, "value") == (upstream.edge_id,)
    assert workspace.edges[upstream.edge_id].source_node_id == integer.node_id
    assert downstream.edge_id not in workspace.edges


def test_script_apply_prunes_through_boundaries_and_generic_disconnect_recovers(graph):
    _, _, workspace, mutation = graph
    script = '@corex.node\n@corex.output("value", value_type=corex.Image)\ndef run(ctx):\n    return {}\n'
    source = add(mutation, "core.python_script", properties={"script": script})
    shell = add(mutation, "core.subnode")
    pin = add(mutation, "core.subnode_input", parent_node_id=shell.node_id)
    relay = add(mutation, "core.trigger", parent_node_id=shell.node_id)
    out = add(mutation, "core.subnode_output", parent_node_id=shell.node_id)
    sink = add(mutation, "image_sink")
    upstream = wire(mutation, source, shell, target_port=pin.node_id)
    wire(mutation, pin, relay, "pin")
    wire(mutation, relay, out, "output", "pin")
    downstream = wire(mutation, shell, sink, out.node_id, "value")
    mutation.apply_python_script(source.node_id, script.replace("corex.Image", "str"))
    assert downstream.edge_id not in workspace.edges
    assert mutation.kernel.type_resolver().source_contract(shell.node_id, out.node_id).type_ids == (STRING_DATA_TYPE_ID,)
    mutation.remove_edge(upstream.edge_id)
    assert mutation.kernel.type_resolver().source_contract(shell.node_id, out.node_id).type_ids == (GRAPH_DATA_TYPE_ID,)


def test_normalization_compile_and_persistence_prune_invalid_forwarded_edges(graph):
    registry, model, workspace, mutation = graph
    image, relay, sink = add(mutation, "image"), add(mutation, "core.trigger"), add(mutation, "number_sink")
    wire(mutation, image, relay)
    invalid = EdgeInstance("invalid", relay.node_id, "output", sink.node_id, "value")
    workspace.edges[invalid.edge_id] = invalid
    fragment = build_graph_fragment_payload(
        nodes=[dict(node_instance_to_mapping(node), ref_id=node.node_id) for node in workspace.nodes.values()],
        edges=[{"source_ref_id": edge.source_node_id, "source_port_key": edge.source_port_key,
                "target_ref_id": edge.target_node_id, "target_port_key": edge.target_port_key}
               for edge in workspace.edges.values()],
    )
    assert not graph_fragment_payload_is_valid(fragment_payload=fragment, registry=registry)
    compiled = compile_runtime_workspace_snapshot(runtime(registry, model), registry)
    assert "invalid" not in {edge.edge_id for edge in compiled.edges}
    # Missing runtime edge IDs cannot make an unrelated valid edge disappear.
    anonymous = replace(runtime(registry, model), edges=tuple(replace(edge, edge_id="") for edge in runtime(registry, model).edges))
    assert len(compile_runtime_workspace_snapshot(anonymous, registry).edges) == 1
    serializer = JsonProjectSerializer(registry)
    loaded = serializer.from_document(serializer.to_persistent_document(model.project))
    assert invalid.edge_id not in loaded.workspaces[workspace.workspace_id].edges
    normalize_project_for_registry(model.project, registry)
    assert invalid.edge_id not in workspace.edges


def test_retained_trigger_value_is_runtime_checked_despite_inferred_image(graph):
    registry, model, _, mutation = graph
    image, trigger, sink = add(mutation, "image"), add(mutation, "core.trigger"), add(mutation, "image_sink")
    wire(mutation, image, trigger)
    wire(mutation, trigger, sink, "output", "value")
    plan = ExecutionPlan(runtime(registry, model), registry)
    assert plan.source_contracts[(trigger.node_id, "output")].type_ids == (IMAGE,)
    assert plan.ports_by_key[trigger.node_id]["output"].data_type == GRAPH_DATA_TYPE_ID
    executor = object.__new__(NodeExecutor)
    executor._data_types, executor._plan = registry.data_types, plan
    executor.node_outputs = {trigger.node_id: {"output": SettledPortResult(status="value", value=DataTree((((0,), (42,)),)))}}
    with pytest.raises(ValueError, match="Image"):
        executor._input_result(sink.node_id, plan.ports_by_key[sink.node_id]["value"], {})


def test_consumer_identity_changes_without_new_trigger_publication(graph, monkeypatch):
    monkeypatch.setattr("ea_node_editor.execution.solution_identity.implementation_digest", lambda *args: "b" * 64)
    registry, model, _, mutation = graph
    integer, decimal = add(mutation, "integer"), add(mutation, "decimal")
    trigger, sink = add(mutation, "core.trigger"), add(mutation, "number_sink")
    wire(mutation, integer, trigger)
    wire(mutation, trigger, sink, "output", "value")

    def identity():
        plan = ExecutionPlan(runtime(registry, model), registry)
        assembled = assemble_node_solution(preparation_id="prep", solution_namespace_id="namespace",
            workspace_solution_revision=0, plan=plan, registry=registry, node_id=sink.node_id,
            keys_by_node={}, execution_environment_digest="a" * 64,
            trigger_publication_generations={trigger.node_id: 7})
        assert assembled.reason_code == ""
        return assembled.solution_key, plan

    first, first_plan = identity()
    assert identity()[0] == first
    wire(mutation, decimal, trigger)
    second, second_plan = identity()
    assert second != first
    assert first_plan.workflow_interface_digest != second_plan.workflow_interface_digest
    assert first_plan.fingerprint != second_plan.fingerprint
    assert identity()[0] == second


def test_mixed_forwarded_values_convert_per_actual_item_and_each_revision_changes_identity(graph, monkeypatch):
    from ea_node_editor.nodes.plugin_contracts import PluginContractManifest

    monkeypatch.setattr("ea_node_editor.execution.solution_identity.implementation_digest", lambda *args: "b" * 64)
    registry, model, _, mutation = graph
    calls = []

    def install(int_version="1", double_version="1", replace_owner=False):
        registry.register_plugin_bundle(PluginContractManifest(data_conversions=(
            DataConversionSpec(INTEGER_DATA_TYPE_ID, STRING_DATA_TYPE_ID,
                               lambda value: calls.append("integer") or f"int:{value}", int_version),
            DataConversionSpec(DOUBLE_DATA_TYPE_ID, STRING_DATA_TYPE_ID,
                               lambda value: calls.append("decimal") or f"float:{value}", double_version),
        )), (), owner_id="tests.conversions", replace_owner=replace_owner)

    install()
    integer, decimal, trigger = add(mutation, "integer"), add(mutation, "decimal"), add(mutation, "core.trigger")
    script = '@corex.node\n@corex.input("value", value_type=str)\ndef run(ctx, value):\n    return {}\n'
    sink = add(mutation, "core.python_script", properties={"script": script})
    wire(mutation, integer, trigger)
    wire(mutation, decimal, trigger, append_requested=True)
    wire(mutation, trigger, sink, "output", "value")

    def prepare():
        plan = ExecutionPlan(runtime(registry, model), registry)
        assembled = assemble_node_solution(preparation_id="prep", solution_namespace_id="namespace",
            workspace_solution_revision=0, plan=plan, registry=registry, node_id=sink.node_id,
            keys_by_node={}, execution_environment_digest="a" * 64,
            trigger_publication_generations={trigger.node_id: 7})
        assert assembled.reason_code == ""
        return assembled.solution_key, plan

    first, plan = prepare()
    executor = object.__new__(NodeExecutor)
    executor._data_types, executor._plan = registry.data_types, plan
    executor.node_outputs = {trigger.node_id: {"output": SettledPortResult(
        status="value", value=DataTree((((0,), (2, 3.5, 4)),)),
    )}}
    result = executor._input_result(sink.node_id, plan.ports_by_key[sink.node_id]["value"], {})
    assert result.value == DataTree((((0,), ("int:2", "float:3.5", "int:4")),))
    assert calls == ["integer", "decimal", "integer"]
    install(int_version="2", replace_owner=True)
    second, _ = prepare()
    assert second != first
    install(int_version="2", double_version="2", replace_owner=True)
    third, _ = prepare()
    assert third != second
    assert prepare()[0] == third
