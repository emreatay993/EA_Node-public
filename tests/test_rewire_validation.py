# Purpose: Prove shared rewire previews preserve proposed-topology validation and linear snapshot preparation.
# Map: subsystems/graph_domain.md
# Tests: this file

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ea_node_editor.graph.type_forwarding import GraphTypeResolver
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
from ea_node_editor.runtime_contracts import GRAPH_DATA_TYPE_ID
from ea_node_editor.ui_qml.graph_scene_mutation.policy import compatible_rewire_endpoint_snapshot
from tests.test_type_forwarding_integration import IMAGE, add, graph, wire


def _full_proposal_resolver(registry, workspace, prepared, proposal):
    removed = proposal.replaced_edge_ids | (
        set() if prepared.copy_requested else {edge.edge_id for edge in prepared.requested_edges}
    )
    final_edges = [edge for edge in workspace.edges.values() if edge.edge_id not in removed]
    final_edges.extend(proposal.candidates)
    return GraphTypeResolver(registry=registry, workspace_nodes=workspace.nodes, workspace_edges=final_edges)


@pytest.mark.parametrize("role", ["source", "target"])
@pytest.mark.parametrize("copy_requested,append_requested", [(False, False), (False, True), (True, False)])
def test_candidate_overlay_matches_complete_graph_resolution(graph, role, copy_requested, append_requested):
    registry, _, workspace, mutation = graph
    image, integer = add(mutation, "image"), add(mutation, "integer")
    first, second, third = [add(mutation, "core.trigger") for _ in range(3)]
    image_sink, number_sink = add(mutation, "image_sink"), add(mutation, "number_sink")
    moved = wire(mutation, image, first)
    wire(mutation, first, second, "output")
    wire(mutation, second, third, "output")
    wire(mutation, integer, first, append_requested=True)
    disabled = wire(mutation, integer, second, append_requested=True)
    mutation.set_edge_enabled(disabled.edge_id, False)
    shell = add(mutation, "core.subnode")
    input_pin = add(mutation, "core.subnode_input", parent_node_id=shell.node_id)
    output_pin = add(mutation, "core.subnode_output", parent_node_id=shell.node_id)
    wire(mutation, image, shell, target_port=input_pin.node_id)
    wire(mutation, input_pin, output_pin, "pin", "pin")
    prepared = mutation.prepare_rewire_edges(
        [moved.edge_id], role, copy_requested=copy_requested, append_requested=append_requested,
    )
    before = workspace.capture_snapshot()
    original_overlay = GraphTypeResolver.with_input_connections
    observed = []

    def capture_overlay(self, inputs):
        resolver = original_overlay(self, inputs)
        observed.append(resolver)
        return resolver

    with patch.object(GraphTypeResolver, "with_input_connections", capture_overlay):
        for node_id in workspace.nodes:
            for port in prepared.resolver.ports_for_node(node_id):
                try:
                    proposal = prepared.validate(node_id, port.key)
                except (ValueError, KeyError):
                    continue
                if proposal is not None:
                    expected = _full_proposal_resolver(registry, workspace, prepared, proposal)
                    assert observed[-1].source_contracts == expected.source_contracts
    assert observed
    assert workspace.capture_snapshot() == before


def test_target_replacement_removes_old_type_before_inference_and_preserves_order(graph):
    _, _, workspace, mutation = graph
    image, integer = add(mutation, "image"), add(mutation, "integer")
    origin, target, downstream = [add(mutation, "core.trigger") for _ in range(3)]
    moved = wire(mutation, image, origin)
    replaced = wire(mutation, integer, target)
    wire(mutation, target, downstream, "output")
    prepared = mutation.prepare_rewire_edges([moved.edge_id], "target")
    proposal = prepared.validate(target.node_id, "input")
    assert proposal.replaced_edge_ids == {replaced.edge_id}
    assert proposal.candidates[0].input_order == 0
    resolver = _full_proposal_resolver(mutation.registry, workspace, prepared, proposal)
    assert resolver.source_contract(downstream.node_id, "output").type_ids == (IMAGE,)
    assert mutation.rewire_edges([moved.edge_id], "target", target.node_id, "input") == (moved.edge_id,)
    assert replaced.edge_id not in workspace.edges


def test_source_bundle_and_disabled_copy_use_atomic_gate_and_preserve_metadata(graph):
    _, _, workspace, mutation = graph
    image, integer = add(mutation, "image"), add(mutation, "integer")
    first, second = add(mutation, "core.trigger"), add(mutation, "image_sink")
    edge = wire(mutation, image, first, label="retained metadata", visual_style={"color": "#123456"})
    sink_edge = wire(mutation, image, second, target_port="value")
    prepared = mutation.prepare_rewire_edges([edge.edge_id, sink_edge.edge_id], "source")
    assert not prepared.can_rewire(integer.node_id, "value")
    before = workspace.capture_snapshot()
    with pytest.raises(ValueError, match="Incompatible data types"):
        mutation.rewire_edges([edge.edge_id, sink_edge.edge_id], "source", integer.node_id, "value")
    assert workspace.capture_snapshot() == before
    assert not mutation.prepare_rewire_edges(
        [edge.edge_id, sink_edge.edge_id], "source", copy_requested=True,
    ).can_rewire(integer.node_id, "value")
    mutation.set_edge_enabled(edge.edge_id, False)
    copy_session = mutation.prepare_rewire_edges([edge.edge_id], "source", copy_requested=True)
    proposal = copy_session.validate(integer.node_id, "value")
    copied, = proposal.candidates
    assert not copied.enabled
    assert copied.label == edge.label and copied.visual_style == edge.visual_style
    assert copied.input_order == edge.input_order + 1
    copied_id, = mutation.rewire_edges([edge.edge_id], "source", integer.node_id, "value", copy_requested=True)
    assert edge.edge_id in workspace.edges and copied_id != edge.edge_id
    assert not workspace.edges[copied_id].enabled


def test_original_socket_duplicates_disconnect_and_latest_commit_validation(graph):
    _, _, workspace, mutation = graph
    image, integer = add(mutation, "image"), add(mutation, "integer")
    relay, sink, other = add(mutation, "core.trigger"), add(mutation, "image_sink"), add(mutation, "image_sink")
    upstream = wire(mutation, image, relay)
    edge = wire(mutation, relay, sink, "output", "value")
    prepared = mutation.prepare_rewire_edges([edge.edge_id], "target")
    assert not prepared.can_rewire(sink.node_id, "value")
    assert prepared.can_rewire(other.node_id, "value")
    assert prepared.can_rewire("", "")
    assert not prepared.can_rewire("missing", "value")
    assert not prepared.can_rewire(sink.node_id, "")
    wire(mutation, relay, other, "output", "value")
    assert prepared.can_rewire(other.node_id, "value")  # Snapshot does not mutate.
    assert not mutation.can_rewire_edges([edge.edge_id], "target", other.node_id, "value")
    mutation.rewire_edges([upstream.edge_id], "source", integer.node_id, "value")
    assert edge.edge_id not in workspace.edges
    assert not mutation.rewire_edges([edge.edge_id], "target", other.node_id, "value")
    assert mutation.rewire_edges([upstream.edge_id], "target", "", "") == (upstream.edge_id,)


def test_proposed_feedback_resolves_again_instead_of_reusing_baseline(graph):
    registry, _, workspace, mutation = graph
    image = add(mutation, "image")
    first, second = add(mutation, "core.trigger"), add(mutation, "core.trigger")
    moved = wire(mutation, image, first)
    wire(mutation, first, second, "output")
    prepared = mutation.prepare_rewire_edges([moved.edge_id], "source")
    assert prepared.resolver.source_contract(second.node_id, "output").type_ids == (IMAGE,)
    proposal = prepared.validate(second.node_id, "output")
    expected = _full_proposal_resolver(registry, workspace, prepared, proposal)
    changed = prepared.resolver.with_input_connections({
        (first.node_id, "input"): ((second.node_id, "output"),),
    })
    assert changed.source_contract(second.node_id, "output").type_ids == (GRAPH_DATA_TYPE_ID,)
    assert changed.source_contracts == expected.source_contracts


def test_flow_capacity_direction_exposure_and_self_connections_remain_authoritative(graph):
    registry, _, _, mutation = graph
    spec = NodeTypeSpec(
        type_id="tests.flow", display_name="Flow", category_path=("Tests",), icon="", properties=(),
        ports=(PortSpec("in", "in", "flow", "flow"),
               PortSpec("out", "out", "flow", "flow"),
               PortSpec("hidden", "out", "flow", "flow", exposed=False)),
    )
    class Plugin:
        def spec(self):
            return spec
    registry.register(Plugin)
    source, origin, occupied, other = [add(mutation, "tests.flow") for _ in range(4)]
    moved = wire(mutation, source, origin, "out", "in")
    wire(mutation, other, occupied, "out", "in")
    replacing = mutation.prepare_rewire_edges([moved.edge_id], "target")
    assert replacing.can_rewire(occupied.node_id, "in")
    assert not mutation.prepare_rewire_edges([moved.edge_id], "target", append_requested=True).can_rewire(occupied.node_id, "in")
    assert not mutation.prepare_rewire_edges([moved.edge_id], "target", copy_requested=True).can_rewire(occupied.node_id, "in")
    assert not replacing.can_rewire(source.node_id, "in")
    assert not replacing.can_rewire(other.node_id, "out")
    moving_source = mutation.prepare_rewire_edges([moved.edge_id], "source")
    assert not moving_source.can_rewire(other.node_id, "hidden")
    assert not moving_source.can_rewire(other.node_id, "in")


@pytest.mark.parametrize("count", [100, 200])
def test_preview_prepares_one_snapshot_and_visits_only_source_ancestors(graph, count):
    registry, model, workspace, mutation = graph
    plot = add(mutation, "plot.signal")
    relays = [add(mutation, "core.trigger") for _ in range(count)]
    edge = wire(mutation, plot, relays[0], "image")
    host = SimpleNamespace(_scene_context=SimpleNamespace(
        model=model, registry=registry, workspace_id=workspace.workspace_id, scope_path=(),
    ))
    resolution_sizes = []
    original_resolve = GraphTypeResolver._resolve
    def observe(dependencies, seeds):
        resolution_sizes.append(len(dependencies))
        return original_resolve(dependencies, seeds)
    with patch("ea_node_editor.graph.invariant_kernel.GraphTypeResolver", wraps=GraphTypeResolver) as snapshots, \
         patch.object(GraphTypeResolver, "_resolve", side_effect=observe), \
         patch.object(registry, "resolve_spec", wraps=registry.resolve_spec) as declarations:
        snapshot = compatible_rewire_endpoint_snapshot(host, [edge.edge_id], "target")
    assert snapshots.call_count == 1
    assert declarations.call_count == len(workspace.nodes)
    assert resolution_sizes[0] >= count
    assert max(resolution_sizes[1:]) == 1
    assert sum(resolution_sizes[1:]) <= 2 * count
    assert len(snapshot["compatible_endpoint_ids"]) >= count - 1
