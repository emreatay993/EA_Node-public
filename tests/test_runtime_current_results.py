# Purpose: Prove partial consumers use current results without executing their producers.
# Map: subsystems/execution.md
# Tests: this file
from __future__ import annotations

from dataclasses import replace
import base64
import hashlib
import json
import queue
from types import SimpleNamespace

import pytest

from ea_node_editor.execution.prepared_execution import (
    AcceptedOutputPayload,
    PreparedAction,
    RecomputeMode,
    validate_current_output_payload,
)
from ea_node_editor.execution.runtime import CorexRuntime
from ea_node_editor.execution.runtime_requests import ExecutionRequest
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.worker_runner import WorkflowRunner
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.execution.worker_runtime import DEFAULT_RUNTIME_PREPARATION_CACHE
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtin_functions import data_control
from ea_node_editor.runtime_contracts import DataTree, ImageValue, Interval1D
from ea_node_editor.runtime_contracts.scientific_values import snapshot_scientific_value
from ea_node_editor.runtime_contracts.settled_results import (
    SettledPortResult,
    settled_outputs_to_payload,
)
from ea_node_editor.runtime_contracts.solution_records import (
    SolutionFreshness,
    SolutionResidency,
)
from tests.test_runtime import _PreparedClient, _wait_for_backend_run_cleanup
from tests.test_solution_store_session import _preflight_commit_queue


def _settlement(node_id, **outputs):
    return {
        "type": "node_settled",
        "node_id": node_id,
        "status": "completed",
        "outputs": {
            key: SettledPortResult(status="value", value=DataTree.from_item(value))
            for key, value in outputs.items()
        },
    }


@pytest.fixture
def completed_prefix(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    # A real registered function with an intentionally volatile producer policy.
    original = 'id="data.number_slider",\n    _solution_reuse_scope="durable"'
    assert original in data_control.SOURCE
    monkeypatch.setattr(
        data_control,
        "SOURCE",
        data_control.SOURCE.replace(
            original,
            'id="data.number_slider",\n    _solution_reuse_scope="never"',
            1,
        ),
    )
    registry = build_default_registry(include_public_plugins=False)
    DEFAULT_RUNTIME_PREPARATION_CACHE.clear()
    monkeypatch.setattr(
        "ea_node_editor.nodes.bootstrap.build_default_registry",
        lambda **_kwargs: registry,
    )
    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(
        workspace.workspace_id,
        "data.number_slider",
        "Volatile source",
        0,
        0,
        properties={"value": 3.0},
    )
    boundary = model.add_node(
        workspace.workspace_id,
        "math.construct_interval",
        "Detached result",
        200,
        0,
        properties={"end": 5.0},
    )
    model.add_edge(
        workspace.workspace_id, source.node_id, "value", boundary.node_id, "start"
    )
    client = _PreparedClient()
    runtime = CorexRuntime(client=client, registry=registry)

    def request(*targets, force=False):
        return ExecutionRequest(
            runtime_snapshot=build_runtime_snapshot(
                model.project, workspace_id=workspace.workspace_id, registry=registry
            ),
            workspace_id=workspace.workspace_id,
            target_node_ids=targets,
            recompute_mode=RecomputeMode.FORCE_RECOMPUTE
            if force
            else RecomputeMode.REUSE_VALID,
        )

    first = runtime.prepare_execution(request())
    client.events_on_start = [
        _settlement(source.node_id, value=3.0),
        _settlement(boundary.node_id, interval=Interval1D(3.0, 5.0)),
        {"type": "run_completed"},
    ]
    runtime.dispatch_prepared(first)
    old_facts = {
        fact.node_id: fact
        for fact in runtime.solution_facts(
            model.project.project_id, workspace.workspace_id
        )
    }
    assert all(
        fact.freshness is SolutionFreshness.CURRENT for fact in old_facts.values()
    )
    yield SimpleNamespace(
        registry=registry,
        model=model,
        workspace=workspace,
        source=source,
        boundary=boundary,
        runtime=runtime,
        client=client,
        request=request,
        first=first,
        old_facts=old_facts,
    )
    runtime.shutdown()
    DEFAULT_RUNTIME_PREPARATION_CACHE.clear()


def _add_consumer(scene):
    consumer = scene.model.add_node(
        scene.workspace.workspace_id,
        "math.deconstruct_interval",
        "New consumer",
        400,
        0,
    )
    scene.model.add_edge(
        scene.workspace.workspace_id,
        scene.boundary.node_id,
        "interval",
        consumer.node_id,
        "interval",
    )
    request = scene.request(consumer.node_id)
    scene.runtime.invalidate_solution(
        scene.model.project.project_id,
        scene.workspace.workspace_id,
        request.runtime_snapshot,
        (consumer.node_id,),
        "graph_changed",
    )
    return consumer


def test_new_consumer_reads_current_result_and_prunes_volatile_ancestry(
    completed_prefix,
):
    scene = completed_prefix
    consumer = _add_consumer(scene)
    prepared = scene.runtime.prepare_execution(scene.request(consumer.node_id))
    assert [(d.node_id, d.action) for d in prepared.node_decisions] == [
        (scene.source.node_id, PreparedAction.PRUNE),
        (scene.boundary.node_id, PreparedAction.READ_CURRENT),
        (consumer.node_id, PreparedAction.EXECUTE),
    ]
    assert prepared.recompute_node_ids == (consumer.node_id,)
    assert prepared.reused_node_ids == (scene.boundary.node_id,)
    payload = prepared.accepted_output_payloads[0]
    assert (
        payload.record_id == scene.old_facts[scene.boundary.node_id].retained_record_id
    )
    assert payload.decode_outputs(catalog=scene.registry.data_types)[
        "interval"
    ].value == DataTree.from_item(Interval1D(3.0, 5.0))
    old_keys = {d.node_id: d.solution_key for d in scene.first.node_decisions}
    assert all(
        d.solution_key == old_keys[d.node_id] for d in prepared.node_decisions[:2]
    )
    assert prepared.workflow_interface_digest != scene.first.workflow_interface_digest


def test_current_result_does_not_make_volatile_lineage_computationally_reusable(
    completed_prefix,
):
    scene = completed_prefix
    for fact in scene.old_facts.values():
        assert not scene.runtime.solution_store.record(
            fact.retained_record_id
        ).reuse_eligible
    selected = scene.runtime.prepare_execution(scene.request(scene.source.node_id))
    assert all(d.action is PreparedAction.EXECUTE for d in selected.node_decisions)
    consumer = scene.runtime.prepare_execution(scene.request(scene.boundary.node_id))
    assert consumer.node_decisions[-1].action is PreparedAction.EXECUTE
    assert consumer.node_decisions[-1].reason_code == "volatile_dependency"


@pytest.mark.parametrize("mode", ["full", "force", "changed", "shared"])
def test_fresh_or_changed_required_ancestry_recomputes(completed_prefix, mode):
    scene = completed_prefix
    consumer = _add_consumer(scene)
    if mode == "changed":
        scene.model.validated_mutations(
            scene.workspace.workspace_id, scene.registry
        ).set_node_property(
            scene.source.node_id,
            "value",
            4.0,
        )
        scene.runtime.invalidate_solution(
            scene.model.project.project_id,
            scene.workspace.workspace_id,
            scene.request().runtime_snapshot,
            (scene.source.node_id,),
            "graph_changed",
        )
    targets = (
        ()
        if mode == "full"
        else (consumer.node_id, scene.source.node_id)
        if mode == "shared"
        else (consumer.node_id,)
    )
    prepared = scene.runtime.prepare_execution(
        scene.request(*targets, force=mode == "force")
    )
    assert all(d.action is PreparedAction.EXECUTE for d in prepared.node_decisions)
    assert not prepared.accepted_output_payloads


def test_generation_change_cannot_consume_old_current_data(completed_prefix):
    scene = completed_prefix
    consumer = _add_consumer(scene)
    scene.client.snapshot = replace(
        scene.client.snapshot, runtime_generation=2, backend_generation=2
    )
    prepared = scene.runtime.prepare_execution(scene.request(consumer.node_id))
    assert all(d.action is PreparedAction.EXECUTE for d in prepared.node_decisions)


def _run_worker(scene, command):
    events = queue.Queue()
    services = WorkerServices()
    try:
        WorkflowRunner(
            command,
            events,
            command_queue=_preflight_commit_queue(command),
            worker_services=services,
        ).run()
        return list(events.queue)
    finally:
        services.reset()


def test_worker_consumes_boundary_and_emits_no_events_for_pruned_source(
    completed_prefix,
):
    scene = completed_prefix
    consumer = _add_consumer(scene)
    prepared = scene.runtime.prepare_execution(scene.request(consumer.node_id))
    scene.client.events_on_start = []
    scene.runtime.dispatch_prepared(prepared)
    events = _run_worker(scene, scene.client.commands[-1])
    assert not any(e.get("type") == "run_failed" for e in events), events
    assert [e["node_id"] for e in events if e["type"] == "node_started"] == [
        consumer.node_id
    ]
    settled = [e for e in events if e["type"] == "node_settled"]
    assert [e["node_id"] for e in settled] == [consumer.node_id]
    for event in events:
        if event["type"] in {
            "run_started",
            "node_started",
            "node_settled",
            "run_completed",
        }:
            scene.client.emit(event)
    facts = {
        f.node_id: f
        for f in scene.runtime.solution_facts(
            scene.model.project.project_id, scene.workspace.workspace_id
        )
    }
    assert facts[consumer.node_id].freshness is SolutionFreshness.CURRENT
    assert facts[scene.source.node_id] == scene.old_facts[scene.source.node_id]
    assert (
        facts[scene.boundary.node_id].retained_record_id
        == scene.old_facts[scene.boundary.node_id].retained_record_id
    )


@pytest.mark.parametrize(
    "corruption",
    [
        "prune_target",
        "force",
        "upstream_execute",
        "interface",
        "digest",
        "substitution",
    ],
)
def test_worker_rejects_invalid_current_result_plans_before_node_events(
    completed_prefix, corruption
):
    scene = completed_prefix
    consumer = _add_consumer(scene)
    prepared = scene.runtime.prepare_execution(scene.request(consumer.node_id))
    scene.client.events_on_start = []
    scene.runtime.dispatch_prepared(prepared)
    command = scene.client.commands[-1]
    decisions = list(command.node_decisions)
    if corruption == "prune_target":
        decisions[-1] = replace(
            decisions[-1],
            action=PreparedAction.PRUNE,
            reason_code="dependency_not_required",
        )
        command = replace(command, node_decisions=tuple(decisions))
    elif corruption == "upstream_execute":
        decisions[0] = replace(
            decisions[0],
            action=PreparedAction.EXECUTE,
            reason_code="solution_reuse_scope_never",
        )
        command = replace(command, node_decisions=tuple(decisions))
    elif corruption == "force":
        command = replace(command, recompute_mode="force_recompute")
    elif corruption == "digest":
        payload = replace(
            command.accepted_output_payloads[0],
            output_digest="0" * 64,
            catalog=scene.registry.data_types,
        )
        command = replace(command, accepted_output_payloads=(payload,))
    elif corruption == "substitution":
        outputs = {
            "interval": SettledPortResult(
                status="value", value=DataTree.from_item(Interval1D(99.0, 100.0))
            )
        }
        encoded = json.dumps(
            settled_outputs_to_payload(outputs, catalog=scene.registry.data_types),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        payload = replace(
            command.accepted_output_payloads[0],
            outputs=encoded,
            output_digest=hashlib.sha256(encoded).hexdigest(),
            catalog=scene.registry.data_types,
        )
        command = replace(command, accepted_output_payloads=(payload,))
    else:
        command = replace(command, workflow_interface_digest="0" * 64)
    events = _run_worker(scene, command)
    assert any(e["type"] == "run_failed" for e in events), events
    assert not any(e["type"] in {"node_started", "node_settled"} for e in events)


def test_worker_rejects_relabeling_empty_session_outputs_as_durable(completed_prefix):
    scene = completed_prefix
    consumer = _add_consumer(scene)
    prepared = scene.runtime.prepare_execution(scene.request(consumer.node_id))
    scene.client.events_on_start = []
    scene.runtime.dispatch_prepared(prepared)
    command = scene.client.commands[-1]
    encoded = json.dumps(
        settled_outputs_to_payload({"interval": SettledPortResult(status="empty")}),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    empty = replace(
        command.accepted_output_payloads[0],
        settlement_status="empty",
        outputs=encoded,
        output_digest=hashlib.sha256(encoded).hexdigest(),
        catalog=scene.registry.data_types,
    )
    assert empty.residency is SolutionResidency.SESSION
    decisions = tuple(
        replace(decision, accepted_payload_digest=empty.commitment_digest())
        if decision.node_id == empty.node_id
        else decision
        for decision in command.node_decisions
    )
    forged = replace(
        empty,
        residency=SolutionResidency.DURABLE,
        runtime_generation=None,
        catalog=scene.registry.data_types,
    )
    assert forged.outputs == empty.outputs
    assert forged.output_digest == empty.output_digest
    assert forged.commitment_digest() != empty.commitment_digest()
    events = _run_worker(
        scene,
        replace(
            command,
            node_decisions=decisions,
            accepted_output_payloads=(forged,),
        ),
    )
    assert any(e["type"] == "run_failed" for e in events), events
    assert not any(e["type"] in {"node_started", "node_settled"} for e in events)


def test_fresh_volatile_values_replace_current_results_without_false_nondeterminism(
    completed_prefix,
):
    scene = completed_prefix
    events = []
    scene.runtime.events.subscribe(events.append)
    scene.client.events_on_start = [
        _settlement(scene.source.node_id, value=4.0),
        _settlement(scene.boundary.node_id, interval=Interval1D(4.0, 5.0)),
        {"type": "run_completed"},
    ]
    scene.runtime.dispatch_prepared(scene.runtime.prepare_execution(scene.request()))
    fact = scene.runtime.solution_store.fact(
        scene.model.project.project_id,
        scene.workspace.workspace_id,
        scene.boundary.node_id,
    )
    assert fact.freshness is SolutionFreshness.CURRENT
    assert (
        fact.retained_record_id
        != scene.old_facts[scene.boundary.node_id].retained_record_id
    )
    assert not any(e.get("type") == "solution_nondeterminism" for e in events)


def test_image_consumer_uses_existing_plot_image(completed_prefix):
    scene = completed_prefix
    image = ImageValue.from_png(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
        )
    )
    plot = scene.model.add_node(
        scene.workspace.workspace_id, "plot.signal", "Plot", 400, 0
    )
    scene.client.events_on_start = [
        _settlement(plot.node_id, image=image),
        {"type": "run_completed"},
    ]
    scene.runtime.dispatch_prepared(
        scene.runtime.prepare_execution(scene.request(plot.node_id))
    )
    panel = scene.model.add_node(
        scene.workspace.workspace_id, "media.panel", "Image consumer", 600, 0
    )
    scene.model.add_edge(
        scene.workspace.workspace_id, plot.node_id, "image", panel.node_id, "source"
    )
    prepared = scene.runtime.prepare_execution(scene.request(panel.node_id))
    assert [(d.node_id, d.action) for d in prepared.node_decisions] == [
        (plot.node_id, PreparedAction.READ_CURRENT),
        (panel.node_id, PreparedAction.EXECUTE),
    ]
    assert prepared.accepted_output_payloads[0].decode_outputs(
        catalog=scene.registry.data_types
    )["image"].value == DataTree.from_item(image)


def test_mixed_model_and_table_only_transfers_the_consumed_data_port(
    completed_prefix, monkeypatch
):
    import pandas as pd
    from tests.mechanical_catalogue.test_property_edit import _model

    scene = completed_prefix
    opened = scene.model.add_node(
        scene.workspace.workspace_id, "mechanical.open_model", "Model and data", 0, 200
    )
    table = snapshot_scientific_value(pd.DataFrame({"x": [0.0, 1.0], "y": [1.0, 2.0]}))
    scene.client.events_on_start = [
        _settlement(opened.node_id, model=_model(), info=table),
        {"type": "run_completed"},
    ]
    scene.runtime.dispatch_prepared(
        scene.runtime.prepare_execution(scene.request(opened.node_id))
    )
    plot = scene.model.add_node(
        scene.workspace.workspace_id, "plot.signal", "Table consumer", 300, 200
    )
    scene.model.add_edge(
        scene.workspace.workspace_id, opened.node_id, "info", plot.node_id, "values"
    )
    prepared = scene.runtime.prepare_execution(scene.request(plot.node_id))
    assert prepared.node_decisions[0].action is PreparedAction.READ_CURRENT
    payload = prepared.accepted_output_payloads[0]
    assert set(payload.decode_outputs(catalog=scene.registry.data_types)) == {"info"}
    assert payload.output_digest != payload.result_digest
    assert "handle_ref" not in payload.outputs.decode("utf-8")
    monkeypatch.setattr(
        WorkerServices,
        "resolve_handle",
        lambda *_a, **_k: pytest.fail("unused live handle resolved"),
    )
    scene.client.events_on_start = []
    scene.runtime.dispatch_prepared(prepared)
    events = _run_worker(scene, scene.client.commands[-1])
    assert not any(e["type"] == "run_failed" for e in events), events
    assert [e["node_id"] for e in events if e["type"] == "node_started"] == [
        plot.node_id
    ]

    reader = scene.model.add_node(
        scene.workspace.workspace_id,
        "mechanical.camera_views",
        "Live model reader",
        600,
        200,
    )
    scene.model.add_edge(
        scene.workspace.workspace_id, opened.node_id, "model", reader.node_id, "model"
    )
    fresh = scene.runtime.prepare_execution(scene.request(reader.node_id))
    assert all(d.action is PreparedAction.EXECUTE for d in fresh.node_decisions)
    shared = scene.runtime.prepare_execution(
        scene.request(plot.node_id, reader.node_id)
    )
    assert all(d.action is PreparedAction.EXECUTE for d in shared.node_decisions)


def test_hidden_ordering_requires_operation_not_a_current_value(
    completed_prefix, monkeypatch
):
    from ea_node_editor.execution.execution_plan import ExecutionPlan

    scene = completed_prefix
    consumer = _add_consumer(scene)
    original = ExecutionPlan._decode_hidden_ordering_pairs

    def ordering(plan):
        return (*original(plan), (scene.source.node_id, consumer.node_id))

    monkeypatch.setattr(ExecutionPlan, "_decode_hidden_ordering_pairs", ordering)
    prepared = scene.runtime.prepare_execution(scene.request(consumer.node_id))
    assert all(d.action is PreparedAction.EXECUTE for d in prepared.node_decisions)


def test_real_process_added_consumer_reads_current_result_without_upstream_events():
    registry = build_default_registry(include_public_plugins=False)
    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(
        workspace.workspace_id,
        "data.number_slider",
        "Source",
        0,
        0,
        properties={"value": 3.0},
    )
    boundary = model.add_node(
        workspace.workspace_id,
        "math.construct_interval",
        "Result",
        200,
        0,
        properties={"end": 5.0},
    )
    model.add_edge(
        workspace.workspace_id, source.node_id, "value", boundary.node_id, "start"
    )
    runtime = CorexRuntime(registry=registry)

    def request(*targets):
        return ExecutionRequest(
            runtime_snapshot=build_runtime_snapshot(
                model.project, workspace_id=workspace.workspace_id, registry=registry
            ),
            workspace_id=workspace.workspace_id,
            target_node_ids=targets,
        )

    try:
        first = runtime.run(request(), timeout=30.0)
        assert first.status == "completed", first.events
        _wait_for_backend_run_cleanup(runtime)
        facts = runtime.solution_facts(model.project.project_id, workspace.workspace_id)
        consumer = model.add_node(
            workspace.workspace_id, "math.deconstruct_interval", "New consumer", 400, 0
        )
        model.add_edge(
            workspace.workspace_id,
            boundary.node_id,
            "interval",
            consumer.node_id,
            "interval",
        )
        runtime.invalidate_solution(
            model.project.project_id,
            workspace.workspace_id,
            request().runtime_snapshot,
            (consumer.node_id,),
            "graph_changed",
        )
        second = runtime.run(request(consumer.node_id), timeout=30.0)
        assert second.status == "completed", second.events
        assert [
            e["node_id"] for e in second.events if e.get("type") == "node_started"
        ] == [consumer.node_id]
        settled = [e for e in second.events if e.get("type") == "node_settled"]
        assert [e["node_id"] for e in settled] == [consumer.node_id]
        outputs = settled[0]["outputs"]
        assert outputs["start"].value == DataTree.from_item(3.0)
        assert outputs["end"].value == DataTree.from_item(5.0)
        for fact in facts:
            assert (
                runtime.solution_store.fact(
                    model.project.project_id, workspace.workspace_id, fact.node_id
                )
                == fact
            )
    finally:
        runtime.shutdown()


def test_current_subset_can_be_empty_while_an_unrequested_port_has_a_value():
    registry = build_default_registry(include_public_plugins=False)
    outputs = {
        "empty": SettledPortResult(status="empty"),
        "other": SettledPortResult(status="value", value=DataTree.from_item(3.0)),
    }
    encoded = json.dumps(
        settled_outputs_to_payload(outputs, catalog=registry.data_types),
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    original = AcceptedOutputPayload(
        node_id="node",
        record_id="record",
        solution_key="a" * 64,
        settlement_status="completed",
        result_digest=hashlib.sha256(encoded).hexdigest(),
        residency=SolutionResidency.SESSION,
        runtime_generation=1,
        outputs=encoded,
        catalog=registry.data_types,
    )
    selected = original.select_ports(("empty",), catalog=registry.data_types)
    assert selected.settlement_status == "empty"
    assert selected.result_digest == original.result_digest
    assert selected.output_digest != original.output_digest
    assert selected.decode_outputs(catalog=registry.data_types) == {
        "empty": SettledPortResult(status="empty")
    }
    validate_current_output_payload(
        selected, catalog=registry.data_types, port_keys=("empty",)
    )
