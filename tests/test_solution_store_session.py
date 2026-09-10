from __future__ import annotations

import base64
import queue
import struct
import zlib
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from ea_node_editor.execution.backends import ExecutionBackendSelection
from ea_node_editor.execution.client_generation import (
    ExecutionGenerationSnapshot,
    ExecutionRunReservation,
    ViewerInvalidationReservation,
    _ViewerInvalidationSnapshot,
)
from ea_node_editor.execution.runtime_requests import (
    CancellationRequest,
    ExecutionRequest,
)
from ea_node_editor.execution.runtime import CorexRuntime
from ea_node_editor.execution.prepared_execution import PreparedAction, RecomputeMode
from ea_node_editor.execution.protocol_codec import (
    command_to_dict,
)
from ea_node_editor.execution.run_messages import (
    CommitRunPreflightCommand,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.solution_backend import (
    DurableBackendOpenResult,
    DurableLookupResult,
    DurablePayloadResult,
    DurableStageResult,
)
from ea_node_editor.execution.solution_store import (
    SolutionStore,
    SolutionStoreLimits,
)
from ea_node_editor.execution.viewer_messages import (
    viewer_epoch_snapshot_digest,
)
from ea_node_editor.execution.worker_runner import WorkflowRunner
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtin_functions import core_value
from ea_node_editor.nodes.output_artifacts import register_staged_artifact
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.persistence.solution_repository import (
    SolutionRepository,
    SolutionRepositoryFactory,
)
from ea_node_editor.runtime_contracts import (
    COREX_VIEWER_SESSION_HANDLE_KIND,
    PATH_DATA_TYPE_ID,
    VIEWER_SESSION_DATA_TYPE_ID,
    DataTree,
    ImageValue,
    RuntimeArtifactRef,
    RuntimeHandleRef,
    TabularDataRef,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.runtime_contracts.solution_records import (
    SolutionDisposition,
    SolutionFreshness,
    SolutionResidency,
)
from ea_node_editor.settings import PROJECT_ARTIFACT_STORE_METADATA_KEY, plugin_generations_dir


class _Client:
    def __init__(self) -> None:
        self.selection = ExecutionBackendSelection()
        self.snapshot = ExecutionGenerationSnapshot(
            self.selection,
            1,
            1,
            "b" * 64,
            True,
            "",
        )
        self.callbacks: list[Any] = []
        self.generation_callbacks: list[Any] = []
        self.runs: dict[str, tuple[ExecutionRunReservation, Any]] = {}
        self.lease_resources = False
        self.released_resources: list[Any] = []
        self._next_run = 0
        self.viewer_reservations: dict[str, ViewerInvalidationReservation] = {}

    def subscribe(self, callback):  # noqa: ANN001, ANN201
        self.callbacks.append(callback)

    def subscribe_generation_events(self, callback):  # noqa: ANN001, ANN201
        self.generation_callbacks.append(callback)

    @contextmanager
    def registry_publication_guard(self):  # noqa: ANN201
        yield

    def replace_registry(self, registry):  # noqa: ANN001, ANN201
        self.registry = registry
        return False

    def resolve_execution_selection(self, policy, snapshot):  # noqa: ANN001, ANN201
        del policy, snapshot
        return self.selection

    def execution_generation_snapshot(  # noqa: ANN201
        self,
        selection,  # noqa: ANN001
        *,
        registry_contract_fingerprint="",  # noqa: ANN001
    ):
        del registry_contract_fingerprint
        assert selection == self.selection
        return self.snapshot

    def reserve_run(self, selection, workspace_id):  # noqa: ANN001, ANN201
        self._next_run += 1
        return ExecutionRunReservation(
            f"run_{self._next_run}",
            workspace_id,
            selection,
            self.snapshot,
        )

    @staticmethod
    def retire_workspace(_workspace_id):  # noqa: ANN001, ANN205
        return 0

    def start_reserved_run(self, reservation, command):  # noqa: ANN001, ANN201
        self.runs[reservation.run_id] = (reservation, command)
        self.emit(
            reservation.run_id,
            {
                "type": "run_preflight_accepted",
                "preparation_id": command.preparation_id,
                "viewer_invalidation_reservation_id": (
                    command.viewer_invalidation_reservation_id
                ),
                "viewer_epoch_snapshot_digest": (
                    command.viewer_epoch_snapshot_digest
                ),
            },
        )
        viewer_reservation = self.viewer_reservations[
            command.viewer_invalidation_reservation_id
        ]
        projection = viewer_reservation.projection_snapshot
        self.emit(
            reservation.run_id,
            {
                "type": "viewer_invalidation_committed",
                "viewer_invalidation_node_ids": list(
                    command.viewer_invalidation_node_ids or ()
                ),
                "viewer_workspace_invalidation_epoch": projection.workspace_epoch,
                "viewer_node_invalidation_epochs": [
                    list(item) for item in projection.node_epochs
                ],
                "viewer_invalidation_reservation_id": (
                    command.viewer_invalidation_reservation_id
                ),
                "viewer_epoch_snapshot_digest": projection.snapshot_digest,
                "retired_request_count": 0,
                "reason": "workspace_rerun",
            },
        )
        self.viewer_reservations.pop(
            command.viewer_invalidation_reservation_id, None
        )
        return reservation.run_id

    def reserve_viewer_invalidation(
        self, run_reservation, preparation_id, node_ids  # noqa: ANN001, ANN201
    ):
        normalized_node_ids = tuple(node_ids)
        node_epochs = tuple((node_id, 1) for node_id in normalized_node_ids)
        digest = viewer_epoch_snapshot_digest(
            workspace_id=run_reservation.workspace_id,
            node_ids=normalized_node_ids,
            workspace_epoch=0,
            node_epochs=node_epochs,
        )
        concrete_snapshot = _ViewerInvalidationSnapshot(
            generation=run_reservation.generation_snapshot.backend_generation,
            workspace_epoch=0,
            node_epochs=node_epochs,
            snapshot_digest=digest,
        )
        reservation = ViewerInvalidationReservation(
            reservation_id=f"viewer_inv_{run_reservation.run_id}",
            run_id=run_reservation.run_id,
            preparation_id=preparation_id,
            workspace_id=run_reservation.workspace_id,
            node_ids=normalized_node_ids,
            process_snapshot=concrete_snapshot,
            trusted_snapshot=concrete_snapshot,
            external_snapshot=concrete_snapshot,
            projection_snapshot=replace(concrete_snapshot, generation=None),
            selected_snapshot=concrete_snapshot,
            client=self,
        )
        self.viewer_reservations[reservation.reservation_id] = reservation
        return reservation

    def cancel_viewer_invalidation(self, reservation):  # noqa: ANN001
        self.viewer_reservations.pop(reservation.reservation_id, None)

    def release_run_reservation(self, reservation, reason):  # noqa: ANN001, ANN201
        del reason
        self.runs.pop(reservation.run_id, None)

    def lease_solution_resource(
        self,
        run_id: str,
        value: Any,
        *,
        owner_scope: str,
    ) -> tuple[Any, tuple[str, str]] | None:
        if not self.lease_resources:
            return None
        token = (run_id, owner_scope)
        return value, token

    def release_solution_resource(self, lease: Any) -> None:
        self.released_resources.append(lease)

    def stop_run(self, run_id: str) -> None:
        self.emit(run_id, {"type": "run_stopped", "reason": "stop_requested"})

    def emit(self, run_id: str, event: dict[str, Any]) -> None:
        reservation, command = self.runs[run_id]
        payload = {
            **event,
            "run_id": run_id,
            "workspace_id": reservation.workspace_id,
        }
        if payload.get("type") == "node_settled":
            decisions = {item.node_id: item for item in command.node_decisions}
            decision = decisions.get(payload.get("node_id"))
            if decision is not None:
                accepted = {
                    item.node_id: item for item in command.accepted_output_payloads
                }.get(decision.node_id)
                payload.setdefault(
                    "disposition",
                    (
                        "reused"
                        if accepted is not None
                        else (
                            "blocked"
                            if payload.get("status") == "blocked"
                            else "recomputed"
                        )
                    ),
                )
                payload.setdefault("decision_reason", decision.reason_code)
                payload.setdefault("solution_key", decision.solution_key)
                payload.setdefault(
                    "record_id", accepted.record_id if accepted is not None else ""
                )
                payload.setdefault(
                    "residency",
                    accepted.residency.value if accepted is not None else "",
                )
        for callback in tuple(self.generation_callbacks):
            callback(dict(payload), reservation.generation_snapshot)
        for callback in tuple(self.callbacks):
            callback(dict(payload))


def _runtime(
    model: GraphModel,
    *,
    limits: SolutionStoreLimits | None = None,
    registry: NodeRegistry | None = None,
):  # noqa: ANN201
    if registry is None:
        registry = build_default_registry()
    client = _Client()
    runtime = CorexRuntime(
        client=client,
        registry=registry,
        solution_store=SolutionStore(limits=limits),
    )
    return runtime, client, registry


def _typed_session_producer_registry(
    monkeypatch: pytest.MonkeyPatch, data_type_id: str, *, generation_root: Path
) -> NodeRegistry:
    monkeypatch.setattr(
        core_value,
        "SOURCE",
        core_value.SOURCE + f'''
@corex.node(
    id="tests.typed_session_value", name="Typed Session Value",
    category=("Tests",), _solution_reuse_scope="session",
)
@corex.output("value", value_type={data_type_id!r})
def typed_session_value(ctx):
    raise AssertionError("Reuse-validation fixture must not execute")
''',
    )
    registry = build_default_registry(
        include_public_plugins=False, generation_root=generation_root
    )
    monkeypatch.setattr(
        "ea_node_editor.nodes.bootstrap.build_default_registry",
        lambda **_kwargs: registry,
    )
    return registry


def _snapshot(model: GraphModel, registry, workspace_id: str):  # noqa: ANN001, ANN201
    return build_runtime_snapshot(
        model.project,
        workspace_id=workspace_id,
        registry=registry,
    )


def _preflight_commit_queue(command):  # noqa: ANN001, ANN201
    command_queue: queue.Queue[dict[str, Any]] = queue.Queue()
    command_queue.put(
        command_to_dict(
            CommitRunPreflightCommand(
                run_id=command.run_id,
                viewer_invalidation_reservation_id=(
                    command.viewer_invalidation_reservation_id
                ),
                viewer_epoch_snapshot_digest=command.viewer_epoch_snapshot_digest,
            )
        )
    )
    return command_queue


def _settle(
    client: _Client,
    run_id: str,
    node_id: str,
    *,
    port_key: str = "value",
    value: Any = "value",
) -> None:
    client.emit(
        run_id,
        {
            "type": "node_settled",
            "node_id": node_id,
            "status": "completed",
            "outputs": {
                port_key: SettledPortResult(
                    status="value",
                    value=DataTree.from_item(value),
                )
            },
        },
    )


def _terminal(client: _Client, run_id: str, event_type: str = "run_completed") -> None:
    client.emit(run_id, {"type": event_type})


def test_deleted_fact_record_index_and_pin_are_removed_with_revision_tombstone() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Deleted",
        0,
        0,
    )
    before_delete = workspace.capture_snapshot()
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    _settle(client, run_id, node.node_id)
    current = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    record_id = current.retained_record_id
    assert record_id is not None

    model.remove_node(workspace.workspace_id, node.node_id)
    deleted_snapshot = _snapshot(model, registry, workspace.workspace_id)
    removed = runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        deleted_snapshot,
        (),
        "node_removed",
    )
    assert removed.changed_root_node_ids == ()
    assert removed.expired_node_ids == ()
    assert removed.removed_node_ids == (node.node_id,)
    assert runtime.solution_facts(model.project.project_id, workspace.workspace_id) == ()
    assert runtime.solution_record(record_id) is None

    workspace.restore_snapshot(before_delete)
    restored_snapshot = _snapshot(model, registry, workspace.workspace_id)
    runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        restored_snapshot,
        (node.node_id,),
        "history_restored",
    )
    _settle(client, run_id, node.node_id, value="late")
    restored = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    assert restored.freshness is SolutionFreshness.EXPIRED
    assert restored.retained_record_id is None
    assert runtime.solution_store.stats()["records"] == 0
    prepared_after_restore = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=restored_snapshot,
            workspace_id=workspace.workspace_id,
        )
    )
    assert prepared_after_restore.node_decisions[0].action is PreparedAction.EXECUTE


def test_late_settlement_is_node_revision_safe_and_unrelated_branch_stays_current() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    changed = model.add_node(
        workspace.workspace_id, "core.constant", "Changed", 0, 0
    )
    downstream = model.add_node(
        workspace.workspace_id, "core.logger", "Downstream", 200, 0
    )
    unrelated = model.add_node(
        workspace.workspace_id, "core.constant", "Unrelated", 0, 200
    )
    model.add_edge(
        workspace.workspace_id,
        changed.node_id,
        "value",
        downstream.node_id,
        "message",
    )
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    with pytest.raises(ValueError, match="reason_code"):
        runtime.invalidate_solution(
            model.project.project_id,
            workspace.workspace_id,
            snapshot,
            (changed.node_id,),
            "",
        )
    assert runtime.solution_store.workspace_revision(
        model.project.project_id, workspace.workspace_id
    ) == 0
    invalidation = runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        snapshot,
        (changed.node_id,),
        "property_changed",
    )
    assert set(invalidation.expired_node_ids) == {changed.node_id, downstream.node_id}

    _settle(client, run_id, changed.node_id, value="late")
    _settle(client, run_id, unrelated.node_id, value="unrelated")
    _terminal(client, run_id)
    facts = {
        fact.node_id: fact
        for fact in runtime.solution_facts(
            model.project.project_id,
            workspace.workspace_id,
        )
    }
    assert facts[changed.node_id].freshness is SolutionFreshness.EXPIRED
    assert facts[downstream.node_id].freshness is SolutionFreshness.EXPIRED
    assert facts[unrelated.node_id].freshness is SolutionFreshness.CURRENT
    assert runtime.solution_store.stats()["records"] == 1


def test_active_run_observation_invalidation_preserves_pending_settlement_revisions() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    root = model.add_node(workspace.workspace_id, "core.constant", "Root", 0, 0)
    requester = model.add_node(workspace.workspace_id, "data.panel", "Mutator", 200, 0)
    sibling = model.add_node(workspace.workspace_id, "data.panel", "Old reader", 200, 150)
    downstream = model.add_node(workspace.workspace_id, "data.panel", "Reader", 400, 0)
    unrelated = model.add_node(workspace.workspace_id, "core.constant", "Unrelated", 0, 200)
    model.add_edge(workspace.workspace_id, root.node_id, "value", requester.node_id, "input")
    model.add_edge(workspace.workspace_id, root.node_id, "value", sibling.node_id, "input")
    model.add_edge(workspace.workspace_id, requester.node_id, "output", downstream.node_id, "input")
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    run_id = runtime.dispatch_prepared(
        runtime.prepare_execution(
            ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
        )
    )
    events = []
    unsubscribe = runtime.subscribe(events.append)
    _settle(client, run_id, root.node_id)
    _settle(client, run_id, sibling.node_id, port_key="output", value="old")
    _settle(client, run_id, unrelated.node_id)
    client.emit(
        run_id,
        {
            "type": "observation_invalidation_requested",
            "node_id": requester.node_id,
            "root_node_id": root.node_id,
            "reason_code": "mechanical_model_mutated",
        },
    )
    facts_after_invalidation = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )
    revision_after_invalidation = runtime.solution_store.workspace_revision(
        model.project.project_id, workspace.workspace_id
    )
    changed_count = len(
        [event for event in events if event.get("type") == "solution_state_changed"]
    )
    for changes, generation in (
        ({}, client.snapshot),
        ({"run_id": "wrong"}, client.snapshot),
        ({"workspace_id": "wrong"}, client.snapshot),
        ({"node_id": "missing"}, client.snapshot),
        ({"root_node_id": "missing"}, client.snapshot),
        ({}, replace(client.snapshot, runtime_generation=2)),
    ):
        runtime._handle_generation_event(  # noqa: SLF001 - exact stale-event gate
            {
                "type": "observation_invalidation_requested",
                "run_id": run_id,
                "workspace_id": workspace.workspace_id,
                "node_id": requester.node_id,
                "root_node_id": root.node_id,
                "reason_code": "mechanical_model_mutated",
                **changes,
            },
            generation,
        )
    assert runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    ) == facts_after_invalidation
    assert runtime.solution_store.workspace_revision(
        model.project.project_id, workspace.workspace_id
    ) == revision_after_invalidation
    assert len(
        [event for event in events if event.get("type") == "solution_state_changed"]
    ) == changed_count
    _settle(client, run_id, requester.node_id, port_key="output", value="mutated")
    _settle(client, run_id, downstream.node_id, port_key="output", value="fresh")
    _terminal(client, run_id)
    unsubscribe()
    facts = {
        fact.node_id: fact
        for fact in runtime.solution_facts(model.project.project_id, workspace.workspace_id)
    }
    assert facts[root.node_id].freshness is SolutionFreshness.EXPIRED
    assert facts[root.node_id].expiration_reason_code == "mechanical_model_mutated"
    assert facts[sibling.node_id].freshness is SolutionFreshness.EXPIRED
    assert facts[requester.node_id].freshness is SolutionFreshness.CURRENT
    assert facts[downstream.node_id].freshness is SolutionFreshness.CURRENT
    assert facts[unrelated.node_id].freshness is SolutionFreshness.CURRENT
    changed = [event for event in events if event.get("type") == "solution_state_changed"]
    assert changed[-1]["expired_node_ids"] == [
        root.node_id,
        sibling.node_id,
    ]
    assert not any(event.get("type") == "observation_invalidation_requested" for event in events)


def test_active_run_observation_invalidation_ignores_known_unscheduled_nodes() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    root = model.add_node(workspace.workspace_id, "core.constant", "Root", 0, 0)
    requester = model.add_node(workspace.workspace_id, "data.panel", "Requester", 200, 0)
    unscheduled = model.add_node(workspace.workspace_id, "core.constant", "Other", 0, 200)
    model.add_edge(workspace.workspace_id, root.node_id, "value", requester.node_id, "input")
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    run_id = runtime.dispatch_prepared(
        runtime.prepare_execution(
            ExecutionRequest(
                runtime_snapshot=snapshot,
                workspace_id=workspace.workspace_id,
                target_node_ids=(requester.node_id,),
            )
        )
    )
    _settle(client, run_id, root.node_id)
    before = runtime.solution_facts(model.project.project_id, workspace.workspace_id)
    revision = runtime.solution_store.workspace_revision(
        model.project.project_id, workspace.workspace_id
    )
    for node_id, root_node_id in (
        (requester.node_id, unscheduled.node_id),
        (unscheduled.node_id, root.node_id),
    ):
        runtime._handle_generation_event(  # noqa: SLF001 - exact unscheduled-event gate
            {
                "type": "observation_invalidation_requested",
                "run_id": run_id,
                "workspace_id": workspace.workspace_id,
                "node_id": node_id,
                "root_node_id": root_node_id,
                "reason_code": "mechanical_model_mutated",
            },
            client.snapshot,
        )
    assert runtime.solution_facts(model.project.project_id, workspace.workspace_id) == before
    assert runtime.solution_store.workspace_revision(
        model.project.project_id, workspace.workspace_id
    ) == revision


def test_late_reused_settlement_cannot_restore_current() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, "core.constant", "Constant", 0, 0
    )
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    first = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    first_run = runtime.dispatch_prepared(first)
    _settle(client, first_run, node.node_id)
    _terminal(client, first_run)
    reused = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    assert reused.node_decisions[0].action is PreparedAction.REUSE
    reused_run = runtime.dispatch_prepared(reused)
    runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        snapshot,
        (node.node_id,),
        "property_changed",
    )
    _settle(client, reused_run, node.node_id)
    _terminal(client, reused_run)
    fact = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    assert fact.freshness is SolutionFreshness.EXPIRED
    assert fact.expiration_reason_code == "property_changed"
    assert runtime.solution_store.stats()["records"] == 1


def test_expired_query_preserves_execution_plan_order_not_lexical_order() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(
        workspace.workspace_id, "core.constant", "Source", 0, 0
    )
    workspace.nodes.pop(source.node_id)
    source.node_id = "z_source"
    workspace.nodes[source.node_id] = source
    target = model.add_node(
        workspace.workspace_id, "core.logger", "Target", 200, 0
    )
    workspace.nodes.pop(target.node_id)
    target.node_id = "a_target"
    workspace.nodes[target.node_id] = target
    model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "value",
        target.node_id,
        "message",
    )
    runtime, _client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    invalidation = runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        snapshot,
        (source.node_id,),
        "property_changed",
    )
    assert invalidation.expired_node_ids == (source.node_id, target.node_id)
    assert runtime.expired_node_ids(
        model.project.project_id,
        workspace.workspace_id,
    ) == (source.node_id, target.node_id)
    runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            target_node_ids=(source.node_id,),
        )
    )
    assert runtime.expired_node_ids(
        model.project.project_id,
        workspace.workspace_id,
    ) == (source.node_id, target.node_id)
    runtime.solution_store._workspace_execution_orders[  # noqa: SLF001
        (model.project.project_id, workspace.workspace_id)
    ] = (source.node_id,)
    assert runtime.expired_node_ids(
        model.project.project_id,
        workspace.workspace_id,
    ) == (source.node_id, target.node_id)


def test_same_key_different_result_reports_nondeterminism_and_preserves_record() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Constant",
        0,
        0,
        properties={"value": "one"},
    )
    runtime, client, registry = _runtime(model)
    events: list[dict[str, Any]] = []
    runtime.subscribe(events.append)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    first = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    first_run = runtime.dispatch_prepared(first)
    _settle(client, first_run, node.node_id, value="one")
    _terminal(client, first_run)
    first_fact = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    first_record = runtime.solution_record(first_fact.retained_record_id or "")
    assert first_record is not None

    forced = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            recompute_mode=RecomputeMode.FORCE_RECOMPUTE,
        )
    )
    forced_run = runtime.dispatch_prepared(forced)
    _settle(client, forced_run, node.node_id, value="different")
    _terminal(client, forced_run)
    fact = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    assert fact.freshness is SolutionFreshness.EXPIRED
    assert runtime.solution_record(first_record.record_id) == first_record
    assert runtime.solution_store.stats()["records"] == 1
    assert any(event.get("type") == "solution_nondeterminism" for event in events)


def test_identical_force_recompute_retains_the_established_record() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Constant",
        0,
        0,
        properties={"value": "same"},
    )
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    first = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    first_run = runtime.dispatch_prepared(first)
    _settle(client, first_run, node.node_id, value="same")
    _terminal(client, first_run)
    before = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]

    forced = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            recompute_mode=RecomputeMode.FORCE_RECOMPUTE,
        )
    )
    forced_run = runtime.dispatch_prepared(forced)
    _settle(client, forced_run, node.node_id, value="same")
    _terminal(client, forced_run)
    after = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    assert after.retained_record_id == before.retained_record_id
    assert after.last_disposition is SolutionDisposition.RECOMPUTED
    assert runtime.solution_store.stats()["records"] == 1


def test_maximum_durable_scope_publishes_conditionally_and_detects_conflict(
    tmp_path,
) -> None:  # noqa: ANN001
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "data.boolean_toggle",
        "Toggle",
        0,
        0,
    )
    runtime, client, registry = _runtime(model)
    project_path = tmp_path / "project.cxproj"
    runtime.reset_project_session(model.project.project_id, str(project_path))
    repository = SolutionRepository.create_empty(
        project_id=model.project.project_id,
        project_path=project_path,
        solution_namespace_id=model.project.project_id,
        catalog=registry.data_types,
    )
    runtime.solution_store.install_durable_backend(
        model.project.project_id,
        DurableBackendOpenResult(
            repository,
            model.project.project_id,
            "durable_bound_active",
            active_generation_id="a" * 32,
            active_manifest_set_digest="b" * 64,
        ),
    )
    snapshot = _snapshot(model, registry, workspace.workspace_id)

    first = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    first_run = runtime.dispatch_prepared(first)
    _settle(
        client,
        first_run,
        node.node_id,
        port_key="boolean",
        value=True,
    )
    _terminal(client, first_run)
    fact = runtime.solution_facts(model.project.project_id, workspace.workspace_id)[0]
    record = runtime.solution_record(fact.retained_record_id or "")
    assert fact.residency is SolutionResidency.DURABLE
    assert record is not None and record.residency is SolutionResidency.DURABLE
    assert runtime.solution_store.last_durable_reason_code == "durable_stage_published"

    second = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    assert second.node_decisions[0].action is PreparedAction.REUSE
    runtime.solution_store.discard_preparation(second.preparation_id, "test_probe")

    forced = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            recompute_mode=RecomputeMode.FORCE_RECOMPUTE,
        )
    )
    forced_run = runtime.dispatch_prepared(forced)
    _settle(
        client,
        forced_run,
        node.node_id,
        port_key="boolean",
        value=False,
    )
    _terminal(client, forced_run)
    conflict_fact = runtime.solution_facts(
        model.project.project_id,
        workspace.workspace_id,
    )[0]
    assert conflict_fact.freshness is SolutionFreshness.EXPIRED
    assert conflict_fact.expiration_reason_code == "nondeterministic_solution_result"
    assert runtime.solution_store.stats()["records"] == 1

    quarantined = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    assert quarantined.node_decisions[0].action is PreparedAction.EXECUTE
    assert quarantined.node_decisions[0].reason_code == "no_reusable_record"
    runtime.solution_store.discard_preparation(
        quarantined.preparation_id,
        "test_probe",
    )

    model.set_node_property(workspace.workspace_id, node.node_id, "value", True)
    changed_snapshot = _snapshot(model, registry, workspace.workspace_id)
    runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        changed_snapshot,
        (node.node_id,),
        "property_changed",
    )
    changed = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=changed_snapshot,
            workspace_id=workspace.workspace_id,
        )
    )
    assert changed.node_decisions[0].action is PreparedAction.EXECUTE
    changed_run = runtime.dispatch_prepared(changed)
    _settle(
        client,
        changed_run,
        node.node_id,
        port_key="boolean",
        value=True,
    )
    _terminal(client, changed_run)
    recovered_fact = runtime.solution_facts(
        model.project.project_id,
        workspace.workspace_id,
    )[0]
    assert recovered_fact.freshness is SolutionFreshness.CURRENT
    assert recovered_fact.retained_solution_key != record.solution_key
    recovered = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=changed_snapshot,
            workspace_id=workspace.workspace_id,
        )
    )
    assert recovered.node_decisions[0].action is PreparedAction.REUSE
    runtime.solution_store.discard_preparation(recovered.preparation_id, "test_probe")


def test_maximum_durable_scope_falls_back_to_session_without_backend() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "data.boolean_toggle",
        "Toggle",
        0,
        0,
    )
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    _settle(client, run_id, node.node_id, port_key="boolean", value=True)
    _terminal(client, run_id)
    fact = runtime.solution_facts(model.project.project_id, workspace.workspace_id)[0]
    assert fact.residency is SolutionResidency.SESSION
    assert runtime.solution_store.last_durable_reason_code == "durable_not_bound"


@pytest.mark.parametrize("replacement_kind", ["session_only", "backend_b"])
def test_durable_backend_rebind_evicts_only_previous_durable_state(
    tmp_path,
    replacement_kind: str,
) -> None:  # noqa: ANN001
    model = GraphModel()
    workspace = model.active_workspace
    durable_node = model.add_node(
        workspace.workspace_id,
        "data.boolean_toggle",
        "Toggle",
        0,
        0,
    )
    session_node = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Constant",
        200,
        0,
    )
    runtime, client, registry = _runtime(model)
    project_path = tmp_path / "backend-a.cxproj"
    runtime.reset_project_session(model.project.project_id, str(project_path))
    backend_a = SolutionRepository.create_empty(
        project_id=model.project.project_id,
        project_path=project_path,
        solution_namespace_id=model.project.project_id,
        catalog=registry.data_types,
    )
    runtime.solution_store.install_durable_backend(
        model.project.project_id,
        DurableBackendOpenResult(
            backend_a,
            model.project.project_id,
            "durable_bound_active",
            active_generation_id="a" * 32,
            active_manifest_set_digest="b" * 64,
        ),
    )
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    _settle(
        client,
        run_id,
        durable_node.node_id,
        port_key="boolean",
        value=True,
    )
    _settle(client, run_id, session_node.node_id, value="session")
    _terminal(client, run_id)
    facts = {
        fact.node_id: fact
        for fact in runtime.solution_facts(
            model.project.project_id,
            workspace.workspace_id,
        )
    }
    durable_record_id = facts[durable_node.node_id].retained_record_id or ""
    durable_record = runtime.solution_record(durable_record_id)
    session_record_id = facts[session_node.node_id].retained_record_id or ""
    session_record = runtime.solution_record(session_record_id)
    assert durable_record is not None
    assert durable_record.residency is SolutionResidency.DURABLE
    assert session_record is not None
    assert session_record.residency is SolutionResidency.SESSION

    if replacement_kind == "backend_b":
        backend_b = SolutionRepository.create_empty(
            project_id=model.project.project_id,
            project_path=tmp_path / "backend-b.cxproj",
            solution_namespace_id=model.project.project_id,
            catalog=registry.data_types,
        )
        replacement = DurableBackendOpenResult(
            backend_b,
            model.project.project_id,
            "durable_bound_active",
            active_generation_id="c" * 32,
            active_manifest_set_digest="d" * 64,
        )
    else:
        backend_b = None
        replacement = DurableBackendOpenResult(
            None,
            model.project.project_id,
            "durable_session_only_metadata_absent",
            "No committed durable generation is available.",
        )
    previous = runtime.solution_store.install_durable_backend(
        model.project.project_id,
        replacement,
    )
    assert previous is backend_a
    previous.close()

    remaining_facts = {
        fact.node_id: fact
        for fact in runtime.solution_facts(
            model.project.project_id,
            workspace.workspace_id,
        )
    }
    assert durable_node.node_id not in remaining_facts
    assert remaining_facts[session_node.node_id].retained_record_id == session_record_id
    assert runtime.solution_record(durable_record_id) is None
    assert runtime.solution_record(session_record_id) == session_record
    assert durable_record.solution_key not in runtime.solution_store._reuse_index  # noqa: SLF001
    assert runtime.solution_store.select_record(
        solution_key=durable_record.solution_key,
        project_id=model.project.project_id,
        workspace_id=workspace.workspace_id,
        node_id=durable_node.node_id,
        runtime_generation=client.snapshot.runtime_generation,
        catalog=registry.data_types,
    ) is None
    runtime.shutdown()


def test_all_29_maximum_durable_rows_share_conditional_store_publication() -> None:
    registry = build_default_registry()
    durable_rows = tuple(
        spec.type_id
        for spec in registry.all_specs()
        if spec.runtime_behavior == "active"
        and spec.solution_reuse_scope == "durable"
    )
    assert len(durable_rows) == 29
    assert "data.boolean_toggle" in durable_rows


def test_durable_stage_failure_falls_back_to_valid_session_record() -> None:
    class FailingBackend:
        def lookup_record(self, workspace_id, node_id, solution_key, catalog):  # noqa: ANN001, ANN201
            del workspace_id, node_id, solution_key, catalog
            return DurableLookupResult(None, "durable_key_absent")

        def stage_record(self, record, canonical_payload, catalog):  # noqa: ANN001, ANN201
            del record, canonical_payload, catalog
            return DurableStageResult(None, "durable_stage_write_failed")

        def load_payload(self, record, catalog):  # noqa: ANN001, ANN201
            del record, catalog
            return DurablePayloadResult(None, "durable_payload_missing")

        def close(self) -> None:
            return None

    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "data.boolean_toggle",
        "Toggle",
        0,
        0,
    )
    runtime, client, registry = _runtime(model)
    runtime.solution_store.install_durable_backend(
        model.project.project_id,
        DurableBackendOpenResult(
            FailingBackend(),
            model.project.project_id,
            "durable_bound_active",
            active_generation_id="a" * 32,
            active_manifest_set_digest="b" * 64,
        ),
    )
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    _settle(client, run_id, node.node_id, port_key="boolean", value=True)
    _terminal(client, run_id)
    fact = runtime.solution_facts(model.project.project_id, workspace.workspace_id)[0]
    assert fact.residency is SolutionResidency.SESSION
    assert runtime.solution_store.last_durable_reason_code == "durable_stage_write_failed"


def test_large_durable_image_falls_back_to_session_without_repository_bytes(
    tmp_path,
) -> None:  # noqa: ANN001
    small_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
    )
    ancillary_payload = b"x" * 1_048_576
    ancillary = (
        struct.pack(">I", len(ancillary_payload))
        + b"tEXt"
        + ancillary_payload
        + struct.pack(">I", zlib.crc32(b"tEXt" + ancillary_payload) & 0xFFFFFFFF)
    )
    image = ImageValue.from_png(small_png[:-12] + ancillary + small_png[-12:])

    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "plot.signal",
        "Signal Plot",
        0,
        0,
    )
    runtime, client, registry = _runtime(model)
    project_path = tmp_path / "large-image.cxproj"
    runtime.reset_project_session(model.project.project_id, str(project_path))
    repository = SolutionRepository.create_empty(
        project_id=model.project.project_id,
        project_path=project_path,
        solution_namespace_id=model.project.project_id,
        catalog=registry.data_types,
    )
    runtime.solution_store.install_durable_backend(
        model.project.project_id,
        DurableBackendOpenResult(
            repository,
            model.project.project_id,
            "durable_bound_active",
            active_generation_id="a" * 32,
            active_manifest_set_digest="b" * 64,
        ),
    )
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    _settle(client, run_id, node.node_id, port_key="image", value=image)
    _terminal(client, run_id)

    fact = runtime.solution_facts(model.project.project_id, workspace.workspace_id)[0]
    record = runtime.solution_record(fact.retained_record_id or "")
    assert record is not None and record.residency is SolutionResidency.SESSION
    assert record.reuse_eligible
    assert runtime.solution_store.last_durable_reason_code == "durable_value_ineligible"
    assert repository._staged_records == {}  # noqa: SLF001
    assert not repository._root.exists()  # noqa: SLF001
    runtime.shutdown()


def test_solution_repository_restart_payload_failure_installs_no_partial_record_index_or_fact(
    tmp_path,
) -> None:  # noqa: ANN001
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "data.boolean_toggle",
        "Toggle",
        0,
        0,
    )
    project_path = tmp_path / "restart.cxproj"
    runtime, client, registry = _runtime(model)
    runtime.reset_project_session(model.project.project_id, str(project_path))
    repository = SolutionRepository.create_empty(
        project_id=model.project.project_id,
        project_path=project_path,
        solution_namespace_id=model.project.project_id,
        catalog=registry.data_types,
    )
    runtime.solution_store.install_durable_backend(
        model.project.project_id,
        DurableBackendOpenResult(
            repository,
            model.project.project_id,
            "durable_bound_active",
            active_generation_id="a" * 32,
            active_manifest_set_digest="b" * 64,
        ),
    )
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    _settle(client, run_id, node.node_id, port_key="boolean", value=True)
    _terminal(client, run_id)
    fact = runtime.solution_facts(model.project.project_id, workspace.workspace_id)[0]
    durable = runtime.solution_record(fact.retained_record_id or "")
    assert durable is not None and durable.residency is SolutionResidency.DURABLE
    generation = repository.build_candidate_generation((durable,))
    metadata = generation.metadata_solution_store
    runtime.shutdown()
    assert not project_path.exists()

    restarted, _restarted_client, restarted_registry = _runtime(model)
    restarted.reset_project_session(model.project.project_id, str(project_path))
    opened = SolutionRepositoryFactory().open_backend(
        model.project.project_id,
        str(project_path),
        metadata,
        restarted_registry.data_types,
    )
    assert opened.backend is not None
    restarted.solution_store.install_durable_backend(
        model.project.project_id,
        opened,
    )
    successful = restarted.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    assert successful.node_decisions[0].action is PreparedAction.REUSE
    lazy_fact = restarted.solution_facts(
        model.project.project_id,
        workspace.workspace_id,
    )[0]
    assert lazy_fact.freshness is SolutionFreshness.CURRENT
    assert lazy_fact.retained_record_id == durable.record_id
    assert lazy_fact.retained_solution_key == durable.solution_key
    assert lazy_fact.residency is SolutionResidency.DURABLE
    assert lazy_fact.last_disposition is SolutionDisposition.REUSED
    assert restarted.solution_record(durable.record_id) == durable
    assert restarted.solution_store._reuse_index[durable.solution_key] == (  # noqa: SLF001
        durable.record_id
    )
    restarted.solution_store.discard_preparation(
        successful.preparation_id,
        "test_probe",
    )
    restarted.shutdown()

    assert durable.payload_locator is not None
    blob = (
        project_path.with_name(f"{project_path.stem}.data")
        / "solutions"
        / "v1"
        / "blobs"
        / "sha256"
        / durable.payload_locator.reference_id[:2]
        / durable.payload_locator.reference_id
    )
    blob.write_bytes(blob.read_bytes()[:-1])

    failed, _failed_client, failed_registry = _runtime(model)
    failed.reset_project_session(model.project.project_id, str(project_path))
    failed_open = SolutionRepositoryFactory().open_backend(
        model.project.project_id,
        str(project_path),
        metadata,
        failed_registry.data_types,
    )
    assert failed_open.backend is not None
    failed.solution_store.install_durable_backend(
        model.project.project_id,
        failed_open,
    )
    restarted_prepared = failed.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    assert restarted_prepared.node_decisions[0].action is PreparedAction.EXECUTE
    assert failed.solution_store.last_durable_reason_code == (
        "durable_payload_digest_mismatch"
    )
    assert failed.solution_store.stats()["records"] == 0
    assert failed.solution_facts(
        model.project.project_id,
        workspace.workspace_id,
    ) == ()
    assert durable.solution_key not in failed.solution_store._reuse_index  # noqa: SLF001
    failed.solution_store.discard_preparation(
        restarted_prepared.preparation_id,
        "test_probe",
    )
    failed.shutdown()


def test_empty_eligible_settlement_reuses_without_a_new_record() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, "core.constant", "Constant", 0, 0
    )
    runtime, client, registry = _runtime(model)
    events: list[dict[str, Any]] = []
    runtime.subscribe(events.append)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    empty_outputs = {
        "value": SettledPortResult(status="empty"),
        "as_text": SettledPortResult(status="empty"),
    }
    first = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    first_run = runtime.dispatch_prepared(first)
    client.emit(
        first_run,
        {
            "type": "node_settled",
            "node_id": node.node_id,
            "status": "empty",
            "outputs": empty_outputs,
        },
    )
    _terminal(client, first_run)
    before = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    second = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    assert second.node_decisions[0].action is PreparedAction.REUSE
    assert second.accepted_output_payloads[0].decode_outputs(
        catalog=registry.data_types
    ) == empty_outputs
    second_run = runtime.dispatch_prepared(second)
    worker_events: queue.Queue = queue.Queue()
    worker_command = client.runs[second_run][1]
    worker = WorkflowRunner(
        worker_command,
        worker_events,
        command_queue=_preflight_commit_queue(worker_command),
    )
    worker.run()
    worker_emitted = []
    while not worker_events.empty():
        worker_emitted.append(worker_events.get())
    worker_reused = next(
        (
            event
            for event in worker_emitted
            if event.get("type") == "node_settled"
        ),
        None,
    )
    assert worker_reused is not None, [
        (event.get("type"), event.get("error"), event.get("reason"))
        for event in worker_emitted
    ]
    assert worker_reused["disposition"] == "reused"
    assert {
        port_key: result["status"]
        for port_key, result in worker_reused["outputs"].items()
    } == {"value": "empty", "as_text": "empty"}
    client.emit(
        second_run,
        {
            "type": "node_settled",
            "node_id": node.node_id,
            "status": "empty",
            "outputs": empty_outputs,
        },
    )
    _terminal(client, second_run)
    after = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    assert after.retained_record_id == before.retained_record_id
    assert after.last_disposition is SolutionDisposition.REUSED
    assert runtime.solution_store.stats()["records"] == 1
    record = runtime.solution_record(after.retained_record_id or "")
    assert record is not None
    assert [
        (descriptor.port_key, descriptor.status)
        for descriptor in record.output_descriptors
    ] == [("value", "empty"), ("as_text", "empty")]
    reused_event = next(
        event
        for event in events
        if event.get("type") == "node_settled"
        and event.get("run_id") == second_run
    )
    assert reused_event["outputs"] == empty_outputs


def test_stale_nondeterminism_diagnostic_cannot_expire_newer_current_fact() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, "core.constant", "Constant", 0, 0
    )
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    stale = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    stale_run = runtime.dispatch_prepared(stale)
    runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        snapshot,
        (node.node_id,),
        "property_changed",
    )
    newer = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    newer_run = runtime.dispatch_prepared(newer)
    _settle(client, newer_run, node.node_id, value="newer")
    _terminal(client, newer_run)
    current = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    assert current.freshness is SolutionFreshness.CURRENT

    _settle(client, stale_run, node.node_id, value="stale-different")
    _terminal(client, stale_run)
    after_stale = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    assert after_stale == current


def test_stale_capacity_failure_cannot_expire_newer_current_fact() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Constant",
        0,
        0,
        properties={"value": "old"},
    )
    runtime, client, registry = _runtime(model)
    old_snapshot = _snapshot(model, registry, workspace.workspace_id)
    stale = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=old_snapshot,
            workspace_id=workspace.workspace_id,
        )
    )
    stale_run = runtime.dispatch_prepared(stale)
    node.properties["value"] = "new"
    new_snapshot = _snapshot(model, registry, workspace.workspace_id)
    runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        new_snapshot,
        (node.node_id,),
        "property_changed",
    )
    newer = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=new_snapshot,
            workspace_id=workspace.workspace_id,
        )
    )
    newer_run = runtime.dispatch_prepared(newer)
    _settle(client, newer_run, node.node_id, value="new")
    _terminal(client, newer_run)
    current = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    runtime.solution_store._limits = replace(  # noqa: SLF001
        runtime.solution_store._limits,  # noqa: SLF001
        records_per_runtime=1,
    )

    _settle(client, stale_run, node.node_id, value="old")
    _terminal(client, stale_run)
    assert runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0] == current


def test_failed_recompute_leaves_prior_record_expired_and_intact() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, "core.constant", "Constant", 0, 0
    )
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    first = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    first_run = runtime.dispatch_prepared(first)
    _settle(client, first_run, node.node_id)
    _terminal(client, first_run)
    current = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    record_id = current.retained_record_id or ""

    forced = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            recompute_mode=RecomputeMode.FORCE_RECOMPUTE,
        )
    )
    forced_run = runtime.dispatch_prepared(forced)
    _terminal(client, forced_run, "run_failed")
    failed = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    assert failed.freshness is SolutionFreshness.EXPIRED
    assert failed.expiration_reason_code == "recompute_started"
    assert failed.retained_record_id == record_id
    assert runtime.solution_record(record_id) is not None


def test_never_scope_publishes_non_reusable_observation_record() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, "core.logger", "Logger", 0, 0
    )
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    client.emit(
        run_id,
        {
            "type": "node_settled",
            "node_id": node.node_id,
            "status": "completed",
            "outputs": {},
        },
    )
    _terminal(client, run_id)
    fact = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    record = runtime.solution_record(fact.retained_record_id or "")
    assert record is not None and not record.reuse_eligible
    second = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    assert second.node_decisions[0].action is PreparedAction.EXECUTE


@pytest.mark.parametrize(
    "limits",
    (
        SolutionStoreLimits(payload_bytes_per_workspace=1),
        SolutionStoreLimits(payload_bytes_per_runtime=1),
    ),
)
def test_payload_capacity_fails_closed(limits: SolutionStoreLimits) -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, "core.constant", "Constant", 0, 0
    )
    runtime, client, registry = _runtime(model, limits=limits)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    _settle(client, run_id, node.node_id)
    _terminal(client, run_id)
    fact = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    assert fact.freshness is SolutionFreshness.EXPIRED
    assert fact.expiration_reason_code == "session_store_capacity_exceeded"
    assert runtime.solution_store.stats()["records"] == 0


def test_workspace_and_runtime_record_caps_keep_current_records_pinned() -> None:
    model = GraphModel()
    first_workspace = model.active_workspace
    first = model.add_node(
        first_workspace.workspace_id, "core.constant", "First", 0, 0
    )
    second = model.add_node(
        first_workspace.workspace_id, "core.constant", "Second", 0, 100
    )
    limits = SolutionStoreLimits(records_per_workspace=1, records_per_runtime=10)
    runtime, client, registry = _runtime(model, limits=limits)
    snapshot = _snapshot(model, registry, first_workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=first_workspace.workspace_id,
        )
    )
    run_id = runtime.dispatch_prepared(prepared)
    _settle(client, run_id, first.node_id, value="first")
    _settle(client, run_id, second.node_id, value="second")
    _terminal(client, run_id)
    facts = {
        fact.node_id: fact
        for fact in runtime.solution_facts(
            model.project.project_id, first_workspace.workspace_id
        )
    }
    assert sum(
        fact.freshness is SolutionFreshness.CURRENT for fact in facts.values()
    ) == 1
    assert any(
        fact.expiration_reason_code == "session_store_capacity_exceeded"
        for fact in facts.values()
    )
    assert runtime.solution_store.stats()["records"] == 1


    other_workspace = model.create_workspace("Other")
    other = model.add_node(
        other_workspace.workspace_id, "core.constant", "Other", 0, 0
    )
    global_runtime, global_client, global_registry = _runtime(
        model,
        limits=SolutionStoreLimits(
            records_per_workspace=10,
            records_per_runtime=1,
        ),
    )
    first_snapshot = _snapshot(model, global_registry, first_workspace.workspace_id)
    first_prepared = global_runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=first_snapshot,
            workspace_id=first_workspace.workspace_id,
            target_node_ids=(first.node_id,),
        )
    )
    first_run = global_runtime.dispatch_prepared(first_prepared)
    _settle(global_client, first_run, first.node_id)
    _terminal(global_client, first_run)
    other_snapshot = _snapshot(model, global_registry, other_workspace.workspace_id)
    other_prepared = global_runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=other_snapshot,
            workspace_id=other_workspace.workspace_id,
        )
    )
    other_run = global_runtime.dispatch_prepared(other_prepared)
    _settle(global_client, other_run, other.node_id)
    _terminal(global_client, other_run)
    other_fact = global_runtime.solution_facts(
        model.project.project_id, other_workspace.workspace_id
    )[0]
    assert other_fact.expiration_reason_code == "session_store_capacity_exceeded"
    assert global_runtime.solution_store.stats()["records"] == 1


def test_cancelled_recompute_preserves_the_prior_record() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, "core.constant", "Constant", 0, 0
    )
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    first = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    first_run = runtime.dispatch_prepared(first)
    _settle(client, first_run, node.node_id)
    _terminal(client, first_run)
    before = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    forced = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            recompute_mode=RecomputeMode.FORCE_RECOMPUTE,
        )
    )
    forced_run = runtime.dispatch_prepared(forced)
    runtime.cancel(CancellationRequest(run_id=forced_run))
    after = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    assert after.freshness is SolutionFreshness.EXPIRED
    assert after.retained_record_id == before.retained_record_id
    assert runtime.solution_store.stats()["records"] == 1
    assert runtime.solution_store.stats()["runs"] == 0


def test_per_node_retention_keeps_current_plus_newest_history() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Constant",
        0,
        0,
        properties={"value": "one"},
    )
    runtime, client, registry = _runtime(
        model,
        limits=SolutionStoreLimits(records_per_node=2),
    )
    for value in ("one", "two", "three"):
        node.properties["value"] = value
        snapshot = _snapshot(model, registry, workspace.workspace_id)
        if value != "one":
            runtime.invalidate_solution(
                model.project.project_id,
                workspace.workspace_id,
                snapshot,
                (node.node_id,),
                "property_changed",
            )
        prepared = runtime.prepare_execution(
            ExecutionRequest(
                runtime_snapshot=snapshot,
                workspace_id=workspace.workspace_id,
            )
        )
        run_id = runtime.dispatch_prepared(prepared)
        _settle(client, run_id, node.node_id, value=value)
        _terminal(client, run_id)
    assert runtime.solution_store.stats()["records"] == 2
    assert runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0].freshness is SolutionFreshness.CURRENT


def test_preparation_eviction_and_trigger_reservation_cleanup_commit_and_discard() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    trigger = model.add_node(
        workspace.workspace_id, "core.trigger", "Trigger", 0, 0
    )
    runtime, client, registry = _runtime(
        model,
        limits=SolutionStoreLimits(preparations_per_runtime=2),
    )
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    preparations = [
        runtime.prepare_execution(
            ExecutionRequest(
                runtime_snapshot=snapshot,
                workspace_id=workspace.workspace_id,
            )
        )
        for _index in range(3)
    ]
    with pytest.raises(ValueError, match="preparation_evicted"):
        runtime.dispatch_prepared(preparations[0])
    assert runtime.solution_store.stats()["preparations"] == 2

    runtime.solution_store.discard_preparation(
        preparations[1].preparation_id,
        "discarded",
    )
    clicked = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            clicked_trigger_node_id=trigger.node_id,
            target_node_ids=(trigger.node_id,),
        )
    )
    assert runtime.solution_store.stats()["trigger_reservations"] == 1
    runtime.solution_store.discard_preparation(clicked.preparation_id, "discarded")
    assert runtime.solution_store.stats()["trigger_reservations"] == 0
    assert runtime.solution_store.trigger_generation(
        model.project.project_id, workspace.workspace_id, trigger.node_id
    ) == 0

    clicked = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            clicked_trigger_node_id=trigger.node_id,
            target_node_ids=(trigger.node_id,),
        )
    )
    run_id = runtime.dispatch_prepared(clicked)
    client.emit(
        run_id,
        {"type": "trigger_published", "trigger_node_id": trigger.node_id},
    )
    _terminal(client, run_id)
    assert runtime.solution_store.trigger_generation(
        model.project.project_id, workspace.workspace_id, trigger.node_id
    ) == 1
    assert runtime.solution_store.stats()["trigger_reservations"] == 0


def test_preparation_byte_capacity_evicts_oldest_unconsumed() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    model.add_node(workspace.workspace_id, "core.constant", "Constant", 0, 0)
    probe_runtime, _probe_client, probe_registry = _runtime(model)
    snapshot = _snapshot(model, probe_registry, workspace.workspace_id)
    probe_runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    one_preparation_bytes = probe_runtime.solution_store.stats()["preparation_bytes"]

    runtime, _client, registry = _runtime(
        model,
        limits=SolutionStoreLimits(
            preparation_bytes_per_runtime=one_preparation_bytes + 16
        ),
    )
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    first = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    with pytest.raises(ValueError, match="preparation_evicted"):
        runtime.dispatch_prepared(first)
    assert runtime.solution_store.stats()["preparations"] == 1


def test_mixed_output_descriptor_records_concrete_types_and_carriers() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, "core.constant", "Constant", 0, 0
    )
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    handle = RuntimeHandleRef(
        data_type_id=VIEWER_SESSION_DATA_TYPE_ID,
        schema_version=1,
        handle_id="handle_1",
        kind=COREX_VIEWER_SESSION_HANDLE_KIND,
        owner_scope="run_1",
        worker_generation=1,
    )
    client.emit(
        run_id,
        {
            "type": "node_settled",
            "node_id": node.node_id,
            "status": "completed",
            "outputs": {
                "value": SettledPortResult(
                    status="value",
                    value=DataTree.from_list(("text", handle)),
                )
            },
        },
    )
    _terminal(client, run_id)
    fact = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    record = runtime.solution_record(fact.retained_record_id or "")
    assert record is not None
    descriptor = record.output_descriptors[0]
    assert descriptor.payload_kinds == ("handle_ref", "inline")
    assert VIEWER_SESSION_DATA_TYPE_ID in descriptor.concrete_data_type_ids
    assert not record.reuse_eligible
    again = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    assert again.node_decisions[0].action is PreparedAction.EXECUTE


def test_live_resource_lease_is_released_on_project_reset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    registry = _typed_session_producer_registry(
        monkeypatch, VIEWER_SESSION_DATA_TYPE_ID, generation_root=plugin_generations_dir()
    )
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, "tests.typed_session_value", "Session", 0, 0
    )
    runtime, client, registry = _runtime(model, registry=registry)
    client.lease_resources = True
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    handle = RuntimeHandleRef(
        data_type_id=VIEWER_SESSION_DATA_TYPE_ID,
        schema_version=1,
        handle_id="handle_live",
        kind=COREX_VIEWER_SESSION_HANDLE_KIND,
        owner_scope=run_id,
        worker_generation=1,
    )
    _settle(client, run_id, node.node_id, value=handle)
    _terminal(client, run_id)
    fact = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    record = runtime.solution_record(fact.retained_record_id or "")
    assert record is not None and record.reuse_eligible
    reusable = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    assert reusable.node_decisions[0].action is PreparedAction.REUSE
    reused_run = runtime.dispatch_prepared(reusable)
    command = client.runs[reused_run][1]
    worker_events: queue.Queue = queue.Queue()
    runner = WorkflowRunner(
        command,
        worker_events,
        command_queue=_preflight_commit_queue(command),
    )
    runner.run()
    emitted = []
    while not worker_events.empty():
        emitted.append(worker_events.get())
    assert any(event.get("type") == "run_failed" for event in emitted)
    assert not any(event.get("type") == "node_settled" for event in emitted)
    failure = next(event for event in emitted if event.get("type") == "run_failed")
    assert "Runtime handle ref is stale or unknown: 'handle_live'" in failure["error"]
    runtime.reset_project_session("replacement", "")
    assert len(client.released_resources) == 1


def test_never_observation_releases_acquired_lease_immediately() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "security.windows_authentication",
        "Authentication",
        0,
        0,
    )
    runtime, client, registry = _runtime(model)
    client.lease_resources = True
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    handle = RuntimeHandleRef(
        data_type_id=VIEWER_SESSION_DATA_TYPE_ID,
        schema_version=1,
        handle_id="handle_observation",
        kind=COREX_VIEWER_SESSION_HANDLE_KIND,
        owner_scope=run_id,
        worker_generation=1,
    )
    client.emit(
        run_id,
        {
            "type": "node_settled",
            "node_id": node.node_id,
            "status": "completed",
            "outputs": {
                "authentication": SettledPortResult(
                    status="value",
                    value=DataTree.from_item(handle),
                )
            },
        },
    )
    assert len(client.released_resources) == 1
    _terminal(client, run_id)
    fact = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    record = runtime.solution_record(fact.retained_record_id or "")
    assert record is not None and not record.reuse_eligible


def test_live_resource_lease_is_released_on_record_eviction() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    first = model.add_node(
        workspace.workspace_id, "core.constant", "First", 0, 0
    )
    second = model.add_node(
        workspace.workspace_id, "core.constant", "Second", 0, 100
    )
    runtime, client, registry = _runtime(
        model,
        limits=SolutionStoreLimits(records_per_workspace=1),
    )
    client.lease_resources = True
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            target_node_ids=(first.node_id,),
        )
    )
    run_id = runtime.dispatch_prepared(prepared)
    handle = RuntimeHandleRef(
        data_type_id=VIEWER_SESSION_DATA_TYPE_ID,
        schema_version=1,
        handle_id="handle_evict",
        kind=COREX_VIEWER_SESSION_HANDLE_KIND,
        owner_scope=run_id,
        worker_generation=1,
    )
    _settle(client, run_id, first.node_id, value=handle)
    _terminal(client, run_id)
    runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        snapshot,
        (first.node_id,),
        "property_changed",
    )
    prepared = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            target_node_ids=(second.node_id,),
        )
    )
    run_id = runtime.dispatch_prepared(prepared)
    _settle(client, run_id, second.node_id, value="second")
    _terminal(client, run_id)
    assert len(client.released_resources) == 1


def test_missing_artifact_payload_is_observed_but_never_indexed() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, "core.constant", "Constant", 0, 0
    )
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    missing = RuntimeArtifactRef.staged(
        "missing-artifact",
        data_type_id=PATH_DATA_TYPE_ID,
        schema_version=1,
        format="txt",
        size_bytes=3,
        sha256="a" * 64,
        provenance="test",
    )
    _settle(client, run_id, node.node_id, value=missing)
    _terminal(client, run_id)
    fact = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    record = runtime.solution_record(fact.retained_record_id or "")
    assert record is not None and not record.reuse_eligible


def test_preparation_revalidates_artifact_integrity_before_selecting_reuse(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    project_path = tmp_path / "artifact.cxproj"
    store = ProjectArtifactStore(project_path=project_path, metadata=None)
    store.ensure_staging_root(temporary_root_parent=tmp_path)
    paths = store.node_artifact_paths(
        artifact_id="prepared-artifact",
        workspace_id="ws",
        node_id="node",
        io_dir="out",
        filename="payload.bin",
    )
    payload_path = store.staged_target_path(paths.staged_relative_path)
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_bytes(b"payload")

    registry = _typed_session_producer_registry(
        monkeypatch, PATH_DATA_TYPE_ID, generation_root=plugin_generations_dir()
    )
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, "tests.typed_session_value", "Artifact", 0, 0
    )
    path_type = registry.data_types.require(PATH_DATA_TYPE_ID)
    runtime_ref = register_staged_artifact(
        store=store,
        artifact_id="prepared-artifact",
        payload_path=payload_path,
        relative_path=paths.staged_relative_path,
        slot=f"{workspace.workspace_id}:{node.node_id}:prepared-artifact",
        data_type_id=PATH_DATA_TYPE_ID,
        schema_version=path_type.payload_schema_version,
        format="bin",
        provenance="corex.test",
        entry_metadata=paths.metadata,
    )
    model.project.metadata[PROJECT_ARTIFACT_STORE_METADATA_KEY] = store.metadata
    client = _Client()
    runtime = CorexRuntime(client=client, registry=registry)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    request = ExecutionRequest(
        project_path=str(project_path),
        runtime_snapshot=snapshot,
        workspace_id=workspace.workspace_id,
    )
    first = runtime.prepare_execution(request)
    run_id = runtime.dispatch_prepared(first)
    _settle(client, run_id, node.node_id, value=runtime_ref)
    _terminal(client, run_id)
    fact = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    record = runtime.solution_record(fact.retained_record_id or "")
    assert record is not None and record.reuse_eligible

    reusable = runtime.prepare_execution(request)
    assert reusable.node_decisions[0].action is PreparedAction.REUSE
    reused_run = runtime.dispatch_prepared(reusable)
    command = client.runs[reused_run][1]
    payload_path.write_bytes(b"mutated")
    worker_events: queue.Queue = queue.Queue()
    runner = WorkflowRunner(
        command,
        worker_events,
        command_queue=_preflight_commit_queue(command),
    )
    runner.run()
    emitted = []
    while not worker_events.empty():
        emitted.append(worker_events.get())
    assert any(event.get("type") == "run_failed" for event in emitted)
    assert not any(event.get("type") == "node_settled" for event in emitted)
    failure = next(event for event in emitted if event.get("type") == "run_failed")
    assert f"artifact {runtime_ref.artifact_id!r} sha256 does not match" in failure["error"]

    prepared = runtime.prepare_execution(request)
    assert prepared.node_decisions[0].action is PreparedAction.EXECUTE
    assert prepared.node_decisions[0].reason_code == "accepted_output_invalid"
    assert prepared.recompute_node_ids == (node.node_id,)
    assert prepared.accepted_output_payloads == ()


def test_unresolved_runtime_resolver_ref_is_never_indexed() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, "core.constant", "Constant", 0, 0
    )
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    unresolved = TabularDataRef(
        ref_id="missing-ref",
        resolver_id="missing-resolver",
    )
    _settle(client, run_id, node.node_id, value=unresolved)
    _terminal(client, run_id)
    fact = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    record = runtime.solution_record(fact.retained_record_id or "")
    assert record is not None and not record.reuse_eligible


def test_project_save_exports_only_current_session_records_with_durable_maximum_scope() -> None:
    model = GraphModel()
    workspace = model.active_workspace
    durable_node = model.add_node(
        workspace.workspace_id,
        "data.boolean_toggle",
        "Toggle",
        0,
        0,
    )
    session_node = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Constant",
        200,
        0,
    )
    runtime, client, registry = _runtime(model)
    snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    run_id = runtime.dispatch_prepared(prepared)
    _settle(client, run_id, durable_node.node_id, port_key="boolean", value=True)
    _settle(client, run_id, session_node.node_id, value="session")
    _terminal(client, run_id)

    (
        _namespace,
        _generation_id,
        _manifest_digest,
        owners,
        exports,
        _artifact_ids,
        _estimated_bytes,
    ) = runtime.solution_store.project_solution_save_inputs(
        model.project.project_id,
        (
            (workspace.workspace_id, durable_node.node_id),
            (workspace.workspace_id, session_node.node_id),
        ),
        catalog=registry.data_types,
    )

    assert owners == tuple(sorted(owners))
    assert [item.record.node_id for item in exports] == [durable_node.node_id]
    assert exports[0].record.residency is SolutionResidency.SESSION
    assert exports[0].maximum_reuse_scope == "durable"
    assert exports[0].is_current


def test_first_save_preserves_unsaved_namespace_and_restart_prepares_reuse(
    tmp_path,
) -> None:  # noqa: ANN001
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "data.boolean_toggle",
        "Toggle",
        0,
        0,
    )
    registry = build_default_registry()
    client = _Client()
    runtime = CorexRuntime(
        client=client,
        registry=registry,
        solution_store=SolutionStore(),
        solution_repository_factory=SolutionRepositoryFactory(),
    )
    namespace = runtime.reset_project_session(model.project.project_id, "")
    runtime.bind_project_solution_store(model.project.project_id, "", None)
    runtime_snapshot = _snapshot(model, registry, workspace.workspace_id)
    prepared = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=runtime_snapshot,
            workspace_id=workspace.workspace_id,
        )
    )
    run_id = runtime.dispatch_prepared(prepared)
    _settle(client, run_id, node.node_id, port_key="boolean", value=True)
    _terminal(client, run_id)
    save_snapshot = runtime.capture_project_solution_save(
        model.project.project_id,
        "",
        ((workspace.workspace_id, node.node_id),),
        ProjectArtifactStore(project_path=None, metadata=None),
    )
    destination = tmp_path / "saved.cxproj"
    destination_store = ProjectArtifactStore(
        project_path=destination,
        metadata=None,
    )
    save_result = runtime.stage_project_solution_save(
        save_snapshot,
        str(destination),
        destination_store,
    )
    assert save_result.solution_namespace_id == namespace
    assert runtime.prepare_project_solution_adoption(
        save_result,
        model.project.project_id,
        str(destination),
        save_result.metadata_solution_store,
        destination_store,
    ).prepared
    assert runtime.adopt_project_solution_save(
        save_result,
        model.project.project_id,
        str(destination),
        save_result.metadata_solution_store,
        destination_store,
    ).adopted
    runtime.shutdown()

    restarted_client = _Client()
    restarted = CorexRuntime(
        client=restarted_client,
        registry=registry,
        solution_store=SolutionStore(),
        solution_repository_factory=SolutionRepositoryFactory(),
    )
    try:
        restarted.reset_project_session(model.project.project_id, str(destination))
        opened = restarted.bind_project_solution_store(
            model.project.project_id,
            str(destination),
            save_result.metadata_solution_store,
        )
        assert opened.solution_namespace_id == namespace
        reused = restarted.prepare_execution(
            ExecutionRequest(
                runtime_snapshot=runtime_snapshot,
                workspace_id=workspace.workspace_id,
            )
        )
        assert reused.node_decisions[0].action is PreparedAction.REUSE
        observed: list[dict[str, Any]] = []
        restarted.subscribe(observed.append)
        restarted.dispatch_prepared(reused)
        assert not any(event.get("type") == "node_started" for event in observed)
    finally:
        restarted.shutdown()
