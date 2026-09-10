from __future__ import annotations

from dataclasses import replace

import pytest

from ea_node_editor.execution.compiler import compile_runtime_snapshot
from ea_node_editor.execution.execution_plan import ExecutionPlan
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry


def _workspace(model: GraphModel, registry):  # noqa: ANN001
    workspace_id = model.active_workspace.workspace_id
    return build_runtime_snapshot(
        model.project,
        workspace_id=workspace_id,
        registry=registry,
    ).workspace(workspace_id)


def _compiled_workspace(model: GraphModel, registry):  # noqa: ANN001
    workspace_id = model.active_workspace.workspace_id
    return compile_runtime_snapshot(
        build_runtime_snapshot(
            model.project,
            workspace_id=workspace_id,
            registry=registry,
        ),
        workspace_id=workspace_id,
        registry=registry,
    )


def _decorated_script(output_key: str) -> str:
    return (
        "@corex.node\n"
        f'@corex.output("{output_key}", value_type=corex.Any)\n'
        "def run(ctx):\n"
        f"    return {{'{output_key}': 'value'}}\n"
    )


def test_selected_plan_excludes_sibling_and_disabled_upstream() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = build_default_registry()
    enabled = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Enabled",
        0,
        0,
        properties={"value": "enabled"},
    )
    disabled = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Disabled",
        0,
        100,
        properties={"value": "disabled"},
    )
    sibling = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Sibling",
        0,
        200,
    )
    sink = model.add_node(
        workspace.workspace_id,
        "core.logger",
        "Sink",
        200,
        0,
    )
    enabled_edge = model.add_edge(
        workspace.workspace_id,
        enabled.node_id,
        "value",
        sink.node_id,
        "message",
    )
    enabled_edge.input_order = 4
    disabled_edge = model.add_edge(
        workspace.workspace_id,
        disabled.node_id,
        "value",
        sink.node_id,
        "message",
    )
    disabled_edge.input_order = 2
    disabled_edge.enabled = False

    plan = ExecutionPlan(
        _workspace(model, registry),
        registry,
        target_node_ids=(sink.node_id,),
    )

    assert plan.scheduled_node_ids == {enabled.node_id, sink.node_id}
    assert plan.execution_order == (enabled.node_id, sink.node_id)
    assert tuple(edge.source_node_id for edge in plan.dependency_edges()) == (
        enabled.node_id,
    )
    assert disabled.node_id not in plan.scheduled_node_ids
    assert sibling.node_id not in plan.scheduled_node_ids
    assert plan.hidden_ordering_pairs == ()
    assert plan.workflow_interface_revision == 2
    assert len(plan.workflow_interface_digest) == 64


def test_topology_fingerprint_ignores_ui_facts_and_disabled_edges() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = build_default_registry()
    source = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Source",
        0,
        0,
        properties={"value": "value"},
    )
    sink = model.add_node(
        workspace.workspace_id,
        "core.logger",
        "Sink",
        200,
        0,
    )
    enabled_edge = model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "value",
        sink.node_id,
        "message",
    )
    disabled_source = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Disabled",
        0,
        100,
    )
    disabled_edge = model.add_edge(
        workspace.workspace_id,
        disabled_source.node_id,
        "value",
        sink.node_id,
        "message",
    )
    disabled_edge.enabled = False
    baseline_plan = ExecutionPlan(
        _workspace(model, registry),
        registry,
        target_node_ids=(sink.node_id,),
    )
    baseline = baseline_plan.fingerprint
    baseline_interface = baseline_plan.workflow_interface_digest

    source.title = "Renamed"
    source.x = 900
    source.y = 700
    source.collapsed = True
    source.visual_style["color"] = "red"
    enabled_edge.label = "presentation only"
    enabled_edge.visual_style["color"] = "blue"
    disabled_edge.input_order = 99
    disabled_source.properties["value"] = "ignored disabled source"

    changed_plan = ExecutionPlan(
        _workspace(model, registry),
        registry,
        target_node_ids=(sink.node_id,),
    )
    changed = changed_plan.fingerprint
    assert changed == baseline
    assert changed_plan.workflow_interface_digest == baseline_interface

    runtime_workspace = _workspace(model, registry)
    reordered_workspace = replace(
        runtime_workspace,
        edges=tuple(
            replace(edge, input_order=3)
            if edge.source_node_id == source.node_id
            else edge
            for edge in runtime_workspace.edges
        ),
    )
    reordered_plan = ExecutionPlan(
        reordered_workspace,
        registry,
        target_node_ids=(sink.node_id,),
    )
    reordered = reordered_plan.fingerprint
    assert reordered != changed
    assert reordered_plan.workflow_interface_digest == baseline_interface


def test_topology_fingerprint_changes_for_enabled_order_target_and_dynamic_ports() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = build_default_registry()
    script = model.add_node(
        workspace.workspace_id,
        "core.python_script",
        "Script",
        0,
        0,
        properties={"script": _decorated_script("first")},
    )
    logger = model.add_node(
        workspace.workspace_id,
        "core.logger",
        "Logger",
        200,
        0,
    )
    model.add_edge(
        workspace.workspace_id,
        script.node_id,
        "first",
        logger.node_id,
        "message",
    )
    baseline_plan = ExecutionPlan(
        _workspace(model, registry),
        registry,
        target_node_ids=(logger.node_id,),
    )
    baseline = baseline_plan.fingerprint

    script.properties["script"] = _decorated_script("second")
    dynamic_plan = ExecutionPlan(
        _workspace(model, registry),
        registry,
        target_node_ids=(logger.node_id,),
    )
    dynamic_ports = dynamic_plan.fingerprint
    assert dynamic_ports != baseline
    assert dynamic_plan.workflow_interface_digest != (
        baseline_plan.workflow_interface_digest
    )

    script_only = ExecutionPlan(
        _workspace(model, registry),
        registry,
        target_node_ids=(script.node_id,),
    ).fingerprint
    assert script_only != dynamic_ports


def test_clicked_trigger_capture_and_next_trigger_boundaries_are_preserved() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = build_default_registry()
    source = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Source",
        0,
        0,
    )
    first = model.add_node(
        workspace.workspace_id,
        "core.trigger",
        "First",
        100,
        0,
    )
    second = model.add_node(
        workspace.workspace_id,
        "core.trigger",
        "Second",
        200,
        0,
    )
    sink = model.add_node(
        workspace.workspace_id,
        "core.logger",
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
        workspace.workspace_id, second.node_id, "output", sink.node_id, "message"
    )

    plan = ExecutionPlan(
        _workspace(model, registry),
        registry,
        target_node_ids=(first.node_id,),
        clicked_trigger_node_id=first.node_id,
        trigger_capture_node_ids=(first.node_id,),
    )

    assert plan.execution_order == (first.node_id,)
    assert source.node_id not in plan.scheduled_node_ids
    assert second.node_id not in plan.scheduled_node_ids
    assert sink.node_id not in plan.scheduled_node_ids


def test_affected_downstream_closure_uses_enabled_hidden_and_trigger_boundaries() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = build_default_registry()
    first = model.add_node(
        workspace.workspace_id, "core.constant", "First", 0, 0
    )
    second = model.add_node(
        workspace.workspace_id, "core.constant", "Second", 0, 100
    )
    merged = model.add_node(
        workspace.workspace_id, "core.stream_gate", "Merged", 200, 0
    )
    trigger = model.add_node(
        workspace.workspace_id, "core.trigger", "Trigger", 300, 0
    )
    beyond = model.add_node(
        workspace.workspace_id, "core.logger", "Beyond", 400, 0
    )
    disabled = model.add_node(
        workspace.workspace_id, "core.logger", "Disabled", 200, 100
    )
    model.add_edge(
        workspace.workspace_id, first.node_id, "value", merged.node_id, "stream"
    )
    disabled_edge = model.add_edge(
        workspace.workspace_id, second.node_id, "value", disabled.node_id, "message"
    )
    disabled_edge.enabled = False
    model.add_edge(
        workspace.workspace_id, merged.node_id, "output_0", trigger.node_id, "input"
    )
    model.add_edge(
        workspace.workspace_id, trigger.node_id, "output", beyond.node_id, "message"
    )
    plan = ExecutionPlan(_workspace(model, registry), registry)
    plan._hidden_ordering_pairs = (  # noqa: SLF001
        *plan.hidden_ordering_pairs,
        (second.node_id, merged.node_id),
    )

    closure = plan.affected_downstream_closure(
        (second.node_id, first.node_id, first.node_id)
    )

    expected_nodes = {first.node_id, second.node_id, merged.node_id, trigger.node_id}
    expected_order = tuple(
        node_id for node_id in plan.execution_order if node_id in expected_nodes
    )
    expected_roots = tuple(
        node_id
        for node_id in plan.execution_order
        if node_id in {first.node_id, second.node_id}
    )
    assert tuple(closure) == expected_order
    assert closure[merged.node_id] == expected_roots
    assert closure[trigger.node_id] == expected_roots
    assert beyond.node_id not in closure
    assert disabled.node_id not in closure
    assert plan.affected_downstream_closure((trigger.node_id,)) == {
        trigger.node_id: (trigger.node_id,)
    }
    assert plan.affected_downstream_closure(()) == {}


def test_invalidation_plan_falls_back_to_compiled_declaration_order_for_cycle() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = build_default_registry()
    first = model.add_node(
        workspace.workspace_id, "core.python_script", "First", 0, 0
    )
    second = model.add_node(
        workspace.workspace_id, "core.python_script", "Second", 200, 0
    )
    model.add_edge(
        workspace.workspace_id,
        first.node_id,
        "result",
        second.node_id,
        "payload",
    )
    model.add_edge(
        workspace.workspace_id,
        second.node_id,
        "result",
        first.node_id,
        "payload",
    )
    compiled = _compiled_workspace(model, registry)

    with pytest.raises(ValueError, match="Cycle detected among nodes:"):
        ExecutionPlan(compiled, registry)

    plan = ExecutionPlan.for_invalidation(compiled, registry)

    assert plan.execution_order == tuple(node.node_id for node in compiled.nodes)
    assert plan.affected_downstream_closure((first.node_id,)) == {
        first.node_id: (first.node_id,),
        second.node_id: (first.node_id,),
    }


def test_compiled_out_filtered_targets_schedule_nothing_and_reject_invalidation_roots() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    registry = build_default_registry()
    first = model.add_node(
        workspace.workspace_id,
        "passive.flowchart.process",
        "First",
        0,
        0,
    )
    second = model.add_node(
        workspace.workspace_id,
        "passive.flowchart.process",
        "Second",
        200,
        0,
    )
    model.add_edge(
        workspace.workspace_id,
        first.node_id,
        "right",
        second.node_id,
        "left",
    )
    model.add_edge(
        workspace.workspace_id,
        second.node_id,
        "right",
        first.node_id,
        "left",
    )
    compiled = _compiled_workspace(model, registry)

    assert compiled.nodes == ()
    assert compiled.edges == ()
    plan = ExecutionPlan(
        compiled,
        registry,
        target_node_ids=(first.node_id,),
    )
    assert plan.target_nodes == (first.node_id,)
    assert plan.scheduled_node_ids == set()
    assert plan.execution_order == ()

    invalidation_plan = ExecutionPlan.for_invalidation(compiled, registry)
    with pytest.raises(ValueError, match="Unknown invalidation root node"):
        invalidation_plan.affected_downstream_closure((first.node_id,))
    with pytest.raises(ValueError, match="Unknown invalidation root node"):
        invalidation_plan.affected_downstream_closure(("missing",))
