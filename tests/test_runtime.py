from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import replace
import hashlib
import json
import queue
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from unittest.mock import patch

from ea_node_editor.execution.backends import (
    TRUSTED_IN_PROCESS_BACKEND,
    ExecutionBackendSelection,
)
from ea_node_editor.execution.client_generation import (
    ExecutionGenerationSnapshot,
    ExecutionRunReservation,
    ViewerInvalidationReservation,
    _ViewerInvalidationSnapshot,
)
from ea_node_editor.execution.compiler import compile_runtime_snapshot
from ea_node_editor.execution.execution_plan import ExecutionPlan
from ea_node_editor.execution.run_messages import (
    CancelRunPreflightCommand,
    CommitRunPreflightCommand,
)
from ea_node_editor.execution.viewer_messages import (
    OpenViewerSessionCommand,
    viewer_epoch_snapshot_digest,
)
from ea_node_editor.execution.protocol_codec import (
    command_to_dict,
)
from ea_node_editor.execution.runtime import CorexRuntime
from ea_node_editor.execution.runtime_requests import ExecutionRequest
from ea_node_editor.execution.prepared_execution import (
    AcceptedOutputPayload,
    PreparedAction,
    RecomputeMode,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.solution_backend import (
    DurableBackendOpenResult,
    DurableLookupResult,
    DurablePayloadResult,
    DurableStageResult,
)
from ea_node_editor.execution.solution_identity import canonical_digest
from ea_node_editor.execution.worker_runner import WorkflowRunner
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_builtin_registry, build_default_registry
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.persistence.solution_repository import SolutionRepositoryFactory
from ea_node_editor.runtime_contracts import DataTree
from ea_node_editor.runtime_contracts import DataTypeCatalogError
from ea_node_editor.runtime_contracts.settled_results import (
    SettledPortResult,
    settled_outputs_to_payload,
)
from ea_node_editor.runtime_contracts.solution_records import SolutionFreshness


def test_project_solution_save_candidate_is_prepared_then_adopted_without_io(
    tmp_path: Path,
) -> None:
    registry = build_default_registry()
    runtime = CorexRuntime(
        client=_PreparedClient(),
        registry=registry,
        solution_repository_factory=SolutionRepositoryFactory(),
    )
    try:
        project_id = "project-save"
        runtime.reset_project_session(project_id, "")
        runtime.bind_project_solution_store(project_id, "", None)
        source_store = ProjectArtifactStore(project_path=None, metadata=None)
        snapshot = runtime.capture_project_solution_save(
            project_id,
            "",
            (),
            source_store,
        )
        destination = tmp_path / "saved.cxproj"
        destination_store = ProjectArtifactStore(
            project_path=destination,
            metadata=None,
        )
        result = runtime.stage_project_solution_save(
            snapshot,
            str(destination),
            destination_store,
        )
        assert result.reason_code == "project_solution_save_staged"
        assert runtime.project_solution_save_snapshot_is_current(
            snapshot.snapshot_token
        )
        assert (
            runtime._project_solution_save_contexts[snapshot.snapshot_token].candidate  # noqa: SLF001
            is None
        )
        candidate = runtime.prepare_project_solution_adoption(
            result,
            project_id,
            str(destination),
            result.metadata_solution_store,
            destination_store,
        )
        assert candidate.prepared

        adoption = runtime.adopt_project_solution_save(
            result,
            project_id,
            str(destination),
            result.metadata_solution_store,
            destination_store,
        )

        assert adoption.adopted
        assert not runtime.project_solution_save_snapshot_is_current(
            snapshot.snapshot_token
        )
        assert runtime.solution_store.durable_status[0] == "durable_bound_active"
        gc_result = runtime.collect_project_solution_garbage(
            result,
            protect_previous_generation=True,
        )
        assert gc_result.reason_code in {
            "project_solution_gc_completed",
            "project_solution_gc_partial",
        }
    finally:
        runtime.shutdown()


def test_project_solution_binding_drift_invalidates_snapshot_before_staging(
    tmp_path: Path,
) -> None:
    registry = build_default_registry()
    runtime = CorexRuntime(
        client=_PreparedClient(),
        registry=registry,
        solution_repository_factory=SolutionRepositoryFactory(),
    )
    try:
        project_id = "project-drift"
        runtime.reset_project_session(project_id, "")
        runtime.bind_project_solution_store(project_id, "", None)
        snapshot = runtime.capture_project_solution_save(
            project_id,
            "",
            (),
            ProjectArtifactStore(project_path=None, metadata=None),
        )
        runtime.reset_project_session(project_id, "")
        assert not runtime.project_solution_save_snapshot_is_current(
            snapshot.snapshot_token
        )
        result = runtime.stage_project_solution_save(
            snapshot,
            str(tmp_path / "stale.cxproj"),
            ProjectArtifactStore(
                project_path=tmp_path / "stale.cxproj",
                metadata=None,
            ),
        )
        assert result.reason_code == "project_solution_save_snapshot_stale"
        assert not (tmp_path / "stale.data").exists()
    finally:
        runtime.shutdown()


def test_project_solution_snapshot_token_rejects_copied_token_with_altered_payload(
    tmp_path: Path,
) -> None:
    registry = build_default_registry()
    runtime = CorexRuntime(
        client=_PreparedClient(),
        registry=registry,
        solution_repository_factory=SolutionRepositoryFactory(),
    )
    try:
        project_id = "project-token"
        runtime.reset_project_session(project_id, "")
        runtime.bind_project_solution_store(project_id, "", None)
        snapshot = runtime.capture_project_solution_save(
            project_id,
            "",
            (),
            ProjectArtifactStore(project_path=None, metadata=None),
        )
        with pytest.raises(ValueError, match="token"):
            replace(
                snapshot,
                required_managed_artifact_ids=("altered",),
            )
        with pytest.raises(ValueError, match="source project path"):
            replace(snapshot, source_project_path=123)
        with pytest.raises(ValueError, match="binding revision"):
            replace(snapshot, binding_revision=True)
        with pytest.raises(ValueError, match="solution_namespace_id"):
            replace(snapshot, solution_namespace_id=" namespace")
        with pytest.raises(ValueError, match="artifact_id"):
            replace(snapshot, required_managed_artifact_ids=(" altered",))
        altered = copy.copy(snapshot)
        object.__setattr__(
            altered,
            "required_managed_artifact_ids",
            ("altered",),
        )
        stale = runtime.stage_project_solution_save(
            altered,
            str(tmp_path / "altered.cxproj"),
            ProjectArtifactStore(
                project_path=tmp_path / "altered.cxproj",
                metadata=None,
            ),
        )
        assert stale.reason_code == "project_solution_save_snapshot_stale"
        assert not (tmp_path / "altered.data").exists()
    finally:
        runtime.shutdown()


class _DurableLifecycleBackend:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1

    def lookup_record(self, workspace_id, node_id, solution_key, catalog):  # noqa: ANN001, ANN201
        del workspace_id, node_id, solution_key, catalog
        return DurableLookupResult(None, "durable_key_absent")

    def load_payload(self, record, catalog):  # noqa: ANN001, ANN201
        del record, catalog
        return DurablePayloadResult(None, "durable_payload_missing")

    def stage_record(self, record, canonical_payload, catalog):  # noqa: ANN001, ANN201
        del record, canonical_payload, catalog
        return DurableStageResult(None, "durable_stage_write_failed")


class _DurableLifecycleFactory:
    def __init__(self, backend: _DurableLifecycleBackend) -> None:
        self.backend = backend
        self.calls: list[tuple[str, str, object]] = []

    def open_backend(self, project_id, project_path, metadata, catalog):  # noqa: ANN001, ANN201
        del catalog
        self.calls.append((project_id, project_path, metadata))
        return DurableBackendOpenResult(
            self.backend,
            "stored-namespace",
            "durable_bound_active",
            active_generation_id="a" * 32,
            active_manifest_set_digest="b" * 64,
        )


class _PreparedClient:
    def __init__(self, *, cold: bool = False) -> None:
        self.selection = ExecutionBackendSelection()
        self.snapshot = ExecutionGenerationSnapshot(
            self.selection,
            0 if cold else 1,
            0 if cold else 1,
            "a" * 64,
            not cold,
            "execution_generation_unavailable" if cold else "",
        )
        self.callbacks: list[Any] = []
        self.generation_callbacks: list[Any] = []
        self.operations: list[str] = []
        self.commands: list[Any] = []
        self.legacy_starts = 0
        self.events_on_start: list[dict[str, Any]] = []
        self.raise_on_start = False
        self.emit_run_started_before_failure = False
        self.reservation_generation: int | None = None
        self.publication_lock = threading.RLock()
        self._next_run = 0
        self.viewer_reservations: dict[str, ViewerInvalidationReservation] = {}
        self.viewer_queries: list[tuple[Any, ...]] = []
        self.viewer_invalidations: list[tuple[str, object]] = []

    def subscribe(self, callback):  # noqa: ANN001, ANN201
        self.callbacks.append(callback)

    def subscribe_generation_events(self, callback):  # noqa: ANN001, ANN201
        self.generation_callbacks.append(callback)

    @contextmanager
    def registry_publication_guard(self):  # noqa: ANN201
        with self.publication_lock:
            yield

    def replace_registry(self, registry):  # noqa: ANN001, ANN201
        self.operations.append("publish_registry")
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
        self.operations.append("generation_snapshot")
        return self.snapshot

    def reserve_run(self, selection, workspace_id):  # noqa: ANN001, ANN201
        self.operations.append("reserve_run")
        if self.reservation_generation is not None:
            self.snapshot = replace(
                self.snapshot,
                backend_generation=self.reservation_generation,
                runtime_generation=self.reservation_generation,
                available=True,
                reason="",
            )
        if not self.snapshot.available:
            self.snapshot = replace(
                self.snapshot,
                backend_generation=1,
                runtime_generation=1,
                available=True,
                reason="",
            )
        self._next_run += 1
        return ExecutionRunReservation(
            f"run_{self._next_run}",
            workspace_id,
            selection,
            self.snapshot,
        )

    def start_reserved_run(self, reservation, command):  # noqa: ANN001, ANN201
        self.operations.append("start_reserved_run")
        self.commands.append(command)
        if self.raise_on_start:
            if self.emit_run_started_before_failure:
                self.emit(
                    {
                        "type": "run_started",
                        "run_id": reservation.run_id,
                        "workspace_id": reservation.workspace_id,
                    },
                    snapshot=reservation.generation_snapshot,
                )
            raise RuntimeError("start failed")
        self.emit(
            {
                "type": "run_preflight_accepted",
                "run_id": reservation.run_id,
                "workspace_id": reservation.workspace_id,
                "preparation_id": command.preparation_id,
                "viewer_invalidation_reservation_id": (
                    command.viewer_invalidation_reservation_id
                ),
                "viewer_epoch_snapshot_digest": (
                    command.viewer_epoch_snapshot_digest
                ),
            },
            snapshot=reservation.generation_snapshot,
        )
        viewer_reservation = self.viewer_reservations[
            command.viewer_invalidation_reservation_id
        ]
        projection = viewer_reservation.projection_snapshot
        self.emit(
            {
                "type": "viewer_invalidation_committed",
                "run_id": reservation.run_id,
                "workspace_id": reservation.workspace_id,
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
            snapshot=reservation.generation_snapshot,
        )
        self.viewer_reservations.pop(
            command.viewer_invalidation_reservation_id, None
        )
        decisions = {item.node_id: item for item in command.node_decisions}
        accepted = {item.node_id: item for item in command.accepted_output_payloads}
        for source in self.events_on_start:
            event = {
                **source,
                "run_id": reservation.run_id,
                "workspace_id": reservation.workspace_id,
            }
            if event.get("type") == "node_settled" and event.get("node_id") in decisions:
                decision = decisions[event["node_id"]]
                payload = accepted.get(decision.node_id)
                event.update(
                    {
                        "disposition": (
                            "reused" if payload is not None else "recomputed"
                        ),
                        "decision_reason": decision.reason_code,
                        "solution_key": decision.solution_key,
                        "record_id": payload.record_id if payload is not None else "",
                        "residency": (
                            payload.residency.value if payload is not None else ""
                        ),
                    }
                )
                if payload is not None:
                    event["status"] = payload.settlement_status
                    event["outputs"] = payload.decode_outputs(
                        catalog=self.registry.data_types
                    )
            self.emit(event, snapshot=reservation.generation_snapshot)
        return reservation.run_id

    def retire_workspace(self, workspace_id: str) -> int:
        self.operations.append("retire_workspace")
        return 0

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
        viewer_reservation = ViewerInvalidationReservation(
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
        self.viewer_reservations[viewer_reservation.reservation_id] = (
            viewer_reservation
        )
        return viewer_reservation

    def cancel_viewer_invalidation(self, reservation):  # noqa: ANN001
        self.viewer_reservations.pop(reservation.reservation_id, None)

    def start_run(self, *args, **kwargs) -> str:  # noqa: ANN002, ANN003
        del args, kwargs
        self.legacy_starts += 1
        return "legacy_run"

    def release_run_reservation(self, reservation, reason):  # noqa: ANN001, ANN201
        del reservation, reason
        self.operations.append("release_reservation")

    def emit(
        self,
        event: dict[str, Any],
        *,
        snapshot: ExecutionGenerationSnapshot | None = None,
    ) -> None:
        active_snapshot = snapshot or self.snapshot
        for callback in tuple(self.generation_callbacks):
            callback(dict(event), active_snapshot)
        for callback in tuple(self.callbacks):
            callback(dict(event))

    def query_viewer_session(self, *args, **kwargs) -> str:  # noqa: ANN002, ANN003
        self.viewer_queries.append((args, kwargs))
        return "viewer_query_1"

    def invalidate_viewer_requests(self, workspace_id, node_ids):  # noqa: ANN001, ANN201
        self.viewer_invalidations.append((workspace_id, node_ids))
        return 2


def _runtime_with_constant(*, cold: bool = False):  # noqa: ANN201
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Constant",
        0,
        0,
        properties={"value": "first"},
    )
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    client = _PreparedClient(cold=cold)
    runtime = CorexRuntime(client=client, registry=registry)
    return runtime, client, registry, model, workspace, node, snapshot


def _prepared_viewer_worker_command():  # noqa: ANN201
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    viewer = model.add_node(
        workspace.workspace_id,
        "model.viewer",
        "Viewer",
        0,
        0,
    )
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    client = _PreparedClient()
    runtime = CorexRuntime(client=client, registry=registry)
    prepared = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            recompute_mode=RecomputeMode.FORCE_RECOMPUTE,
        )
    )
    assert runtime.dispatch_prepared(prepared)
    return client.commands[-1], registry, viewer


def _settled(node_id: str, value: str = "first") -> dict[str, Any]:
    return {
        "type": "node_settled",
        "node_id": node_id,
        "status": "completed",
        "outputs": {
            "value": SettledPortResult(
                status="value",
                value=DataTree.from_item(value),
            )
        },
    }


def _wait_for_backend_run_cleanup(
    runtime: CorexRuntime, *, timeout: float = 30.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        client = runtime._client  # noqa: SLF001
        active_clients = getattr(client, "_active_clients", {})
        if not active_clients:
            return
        time.sleep(0.01)
    raise AssertionError("execution backend did not retire the completed run")


def test_headless_viewer_query_and_invalidation_delegate_exact_arguments() -> None:
    runtime, client, *_rest = _runtime_with_constant()

    assert (
        runtime.query_viewer_session(
            "ws_main",
            "viewer_a",
            "session_a",
            run_id="run_a",
            backend_id="scene",
            query_type="bounds",
            payload={"role": "primary"},
            options={"precision": 3},
        )
        == "viewer_query_1"
    )
    assert runtime.invalidate_viewer_requests("ws_main", ("viewer_a",)) == 2
    assert client.viewer_queries == [
        (
            ("ws_main", "viewer_a", "session_a"),
            {
                "run_id": "run_a",
                "backend_id": "scene",
                "query_type": "bounds",
                "payload": {"role": "primary"},
                "options": {"precision": 3},
            },
        )
    ]
    assert client.viewer_invalidations == [("ws_main", ("viewer_a",))]


def test_worker_preflight_timeout_and_cancel_leave_viewer_service_unchanged() -> None:
    command, _registry, viewer = _prepared_viewer_worker_command()
    for acknowledgment in (None, "cancel", "wrong"):
        services = WorkerServices()
        service = services.viewer_session_service
        service.open_session(
            OpenViewerSessionCommand(
                workspace_id=command.workspace_id,
                node_id=viewer.node_id,
                session_id="session_before_preflight",
                data_refs={"source": "retained"},
                transport={"kind": "mock_live", "revision": 1},
            )
        )
        before = service._sessions[  # noqa: SLF001
            (command.workspace_id, "session_before_preflight")
        ].public_projection()
        command_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        if acknowledgment == "cancel":
            command_queue.put(
                command_to_dict(
                    CancelRunPreflightCommand(
                        run_id=command.run_id,
                        viewer_invalidation_reservation_id=(
                            command.viewer_invalidation_reservation_id
                        ),
                        viewer_epoch_snapshot_digest=(
                            command.viewer_epoch_snapshot_digest
                        ),
                    )
                )
            )
        elif acknowledgment == "wrong":
            command_queue.put(
                command_to_dict(
                    CommitRunPreflightCommand(
                        run_id=command.run_id,
                        viewer_invalidation_reservation_id="wrong_reservation",
                        viewer_epoch_snapshot_digest="0" * 64,
                    )
                )
            )
        event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        with patch(
            "ea_node_editor.execution.worker_runner._RUN_PREFLIGHT_COMMIT_TIMEOUT_SEC",
            0.05,
        ):
            WorkflowRunner(
                command,
                event_queue,
                command_queue=command_queue,
                worker_services=services,
            ).run()
        events = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())
        event_types = [event["type"] for event in events]
        assert event_types[0] == "run_preflight_accepted"
        assert "run_started" not in event_types
        assert "viewer_session_opened" not in event_types
        if acknowledgment == "wrong":
            assert "protocol_error" in event_types
        assert service._sessions[  # noqa: SLF001
            (command.workspace_id, "session_before_preflight")
        ].public_projection() == before
        assert service._workspace_invalidation_epochs == {}  # noqa: SLF001
        assert service._node_invalidation_epochs == {}  # noqa: SLF001


def test_worker_preflight_commit_adopts_before_buffered_viewer_response() -> None:
    command, registry, viewer = _prepared_viewer_worker_command()
    del registry
    services = WorkerServices()
    service = services.viewer_session_service
    service.open_session(
        OpenViewerSessionCommand(
            workspace_id=command.workspace_id,
            node_id=viewer.node_id,
            session_id="session_before_preflight",
            data_refs={"source": "retained"},
            transport={"kind": "mock_live", "revision": 1},
        )
    )
    command_queue: queue.Queue[dict[str, Any]] = queue.Queue()
    command_queue.put(
        command_to_dict(
            OpenViewerSessionCommand(
                request_id="buffered_open",
                workspace_id=command.workspace_id,
                node_id=viewer.node_id,
                session_id="session_recomputed",
                data_refs={"source": "recomputed"},
                transport={"kind": "mock_live", "revision": 2},
                workspace_invalidation_epoch=(
                    command.viewer_workspace_invalidation_epoch
                ),
                node_invalidation_epoch=dict(
                    command.viewer_node_invalidation_epochs
                )[viewer.node_id],
            )
        )
    )
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
    event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
    WorkflowRunner(
        command,
        event_queue,
        command_queue=command_queue,
        worker_services=services,
    ).run()
    events = []
    while not event_queue.empty():
        events.append(event_queue.get_nowait())
    event_types = [event["type"] for event in events]
    assert event_types[0] == "run_preflight_accepted"
    assert event_types.index("run_started") < event_types.index(
        "viewer_session_opened"
    )
    assert service._node_invalidation_epochs[  # noqa: SLF001
        (command.workspace_id, viewer.node_id)
    ] == dict(command.viewer_node_invalidation_epochs)[viewer.node_id]
    assert service._sessions[  # noqa: SLF001
        (command.workspace_id, "session_before_preflight")
    ].invalidated_reason == "workspace_rerun"


def test_worker_post_ack_cleanup_failure_is_started_and_committed() -> None:
    command, _registry, _viewer = _prepared_viewer_worker_command()
    services = WorkerServices()
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
    event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
    with patch.object(
        services.viewer_session_service,
        "adopt_invalidation_snapshot",
        side_effect=RuntimeError("cleanup failed"),
    ):
        WorkflowRunner(
            command,
            event_queue,
            command_queue=command_queue,
            worker_services=services,
        ).run()
    events = []
    while not event_queue.empty():
        events.append(event_queue.get_nowait())
    event_types = [event["type"] for event in events]
    assert event_types[0] == "run_preflight_accepted"
    assert event_types.index("run_started") < event_types.index("run_failed")


def test_worker_preflight_failure_emits_no_acceptance_or_viewer_mutation() -> None:
    command, _registry, viewer = _prepared_viewer_worker_command()
    command = replace(command, execution_plan_fingerprint="0" * 64)
    services = WorkerServices()
    service = services.viewer_session_service
    service.open_session(
        OpenViewerSessionCommand(
            workspace_id=command.workspace_id,
            node_id=viewer.node_id,
            session_id="session_before_failure",
            data_refs={"source": "retained"},
            transport={"kind": "mock_live"},
        )
    )
    before = service._sessions[  # noqa: SLF001
        (command.workspace_id, "session_before_failure")
    ].public_projection()
    event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
    WorkflowRunner(
        command,
        event_queue,
        command_queue=queue.Queue(),
        worker_services=services,
    ).run()
    events = []
    while not event_queue.empty():
        events.append(event_queue.get_nowait())
    event_types = [event["type"] for event in events]
    assert event_types[0] == "run_failed"
    assert "run_preflight_accepted" not in event_types
    assert "run_started" not in event_types
    assert service._sessions[  # noqa: SLF001
        (command.workspace_id, "session_before_failure")
    ].public_projection() == before
    assert service._node_invalidation_epochs == {}  # noqa: SLF001


def test_empty_filter_run_baselines_a_fresh_recycled_service_epoch() -> None:
    runtime, client, _registry, _model, workspace, _node, snapshot = (
        _runtime_with_constant()
    )
    prepared = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
        )
    )
    assert runtime.dispatch_prepared(prepared)
    command = client.commands[-1]
    command = replace(
        command,
        viewer_workspace_invalidation_epoch=3,
        viewer_epoch_snapshot_digest=viewer_epoch_snapshot_digest(
            workspace_id=command.workspace_id,
            node_ids=(),
            workspace_epoch=3,
            node_epochs=(),
        ),
    )
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
    services = WorkerServices()
    event_queue: queue.Queue[dict[str, Any]] = queue.Queue()

    WorkflowRunner(
        command,
        event_queue,
        command_queue=command_queue,
        worker_services=services,
    ).run()

    events = []
    while not event_queue.empty():
        events.append(event_queue.get_nowait())
    event_types = [event["type"] for event in events]
    assert event_types[0] == "run_preflight_accepted"
    assert "run_started" in event_types
    assert "run_completed" in event_types
    service = services.viewer_session_service
    assert service._workspace_invalidation_epochs == {  # noqa: SLF001
        command.workspace_id: 3
    }
    assert service._node_invalidation_epochs == {}  # noqa: SLF001


def test_prepare_is_private_and_dispatch_registers_context_before_sync_events() -> None:
    runtime, client, _registry, model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    prepared = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            recompute_mode=RecomputeMode.FORCE_RECOMPUTE,
        )
    )
    assert "publish_registry" not in client.operations
    assert prepared.node_decisions[0].action is PreparedAction.EXECUTE
    assert runtime.solution_facts(
        model.project.project_id,
        workspace.workspace_id,
    ) == ()
    client.operations.clear()
    client.events_on_start = [
        _settled(node.node_id),
        {"type": "run_completed"},
    ]

    assert runtime.dispatch_prepared(prepared) == "run_1"
    assert client.operations == [
        "publish_registry",
        "generation_snapshot",
        "reserve_run",
        "retire_workspace",
        "generation_snapshot",
        "start_reserved_run",
    ]
    fact = runtime.solution_facts(
        model.project.project_id,
        workspace.workspace_id,
    )[0]
    assert fact.freshness is SolutionFreshness.CURRENT
    assert runtime.solution_store.stats()["runs"] == 0
    with pytest.raises(ValueError, match="preparation_consumed"):
        runtime.dispatch_prepared(prepared)


def test_start_and_run_use_prepared_dispatch_and_legacy_entrypoints_are_absent() -> None:
    runtime, client, _registry, _model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    request = ExecutionRequest(
        runtime_snapshot=snapshot,
        workspace_id=workspace.workspace_id,
    )
    client.events_on_start = [_settled(node.node_id), {"type": "run_completed"}]
    assert runtime.start(request) == "run_1"
    assert client.commands[-1].preparation_id
    assert client.legacy_starts == 0

    original_prepare = runtime.prepare_execution

    def prepare_with_early_event(value):  # noqa: ANN001, ANN202
        runtime.events.publish({"type": "log", "message": "before_prepare"})
        return original_prepare(value)

    runtime.prepare_execution = prepare_with_early_event  # type: ignore[method-assign]
    result = runtime.run(request, timeout=2.0)
    assert result.status == "completed"
    assert any(event.get("message") == "before_prepare" for event in result.events)
    assert client.commands[-1].preparation_id
    assert client.legacy_starts == 0
    assert not hasattr(runtime, "start_run")
    assert not hasattr(runtime, "_start_legacy")


def test_runtime_enriches_only_store_accepted_settlements() -> None:
    runtime, client, _registry, model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    events: list[dict[str, Any]] = []
    runtime.subscribe(events.append)
    client.events_on_start = [_settled(node.node_id), {"type": "run_completed"}]
    runtime.start(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    settled = next(event for event in events if event.get("type") == "node_settled")
    fact = runtime.solution_facts(model.project.project_id, workspace.workspace_id)[0]
    assert settled["accepted_solution_record"] is True
    assert settled["record_id"] == fact.retained_record_id
    assert settled["solution_key"] == fact.retained_solution_key
    assert len([event for event in events if event.get("type") == "node_settled"]) == 1

    events.clear()
    client.events_on_start = []
    prepared = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            recompute_mode=RecomputeMode.FORCE_RECOMPUTE,
        )
    )
    run_id = runtime.dispatch_prepared(prepared)
    runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        snapshot,
        (node.node_id,),
        "graph_changed",
    )
    decision = prepared.node_decisions[0]
    late = _settled(node.node_id, "late")
    late.update(
        {
            "run_id": run_id,
            "workspace_id": workspace.workspace_id,
            "disposition": "recomputed",
            "decision_reason": decision.reason_code,
            "solution_key": decision.solution_key,
            "record_id": "",
            "residency": "",
        }
    )
    client.emit(late)
    rejected = next(event for event in events if event.get("type") == "node_settled")
    assert rejected["accepted_solution_record"] is False
    assert rejected["record_id"] == ""
    assert rejected["result_digest"] == ""


def test_failed_start_restores_current_fact_but_started_failure_does_not() -> None:
    runtime, client, _registry, model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    client.events_on_start = [_settled(node.node_id), {"type": "run_completed"}]
    runtime.start(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    before = runtime.solution_facts(model.project.project_id, workspace.workspace_id)[0]
    assert before.freshness is SolutionFreshness.CURRENT

    force = ExecutionRequest(
        runtime_snapshot=snapshot,
        workspace_id=workspace.workspace_id,
        recompute_mode=RecomputeMode.FORCE_RECOMPUTE,
    )
    client.events_on_start = []
    client.raise_on_start = True
    with pytest.raises(RuntimeError, match="start failed"):
        runtime.dispatch_prepared(runtime.prepare_execution(force))
    restored = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    assert restored == before
    assert client.viewer_reservations == {}

    client.emit_run_started_before_failure = True
    with pytest.raises(RuntimeError, match="start failed"):
        runtime.dispatch_prepared(runtime.prepare_execution(force))
    started_then_failed = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0]
    assert started_then_failed.freshness is SolutionFreshness.EXPIRED
    assert started_then_failed.retained_record_id == before.retained_record_id
    assert started_then_failed.expiration_reason_code == "recompute_started"
    assert client.viewer_reservations == {}

    client.emit_run_started_before_failure = False
    client.raise_on_start = False
    client.events_on_start = [{"type": "run_failed", "error": "boom"}]
    runtime.dispatch_prepared(runtime.prepare_execution(force))
    failed = runtime.solution_facts(model.project.project_id, workspace.workspace_id)[0]
    assert failed.freshness is SolutionFreshness.EXPIRED
    assert failed.retained_record_id == before.retained_record_id
    assert failed.expiration_reason_code == "recompute_started"


def test_generation_and_project_resets_publish_solution_state_events() -> None:
    runtime, client, _registry, model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    events: list[dict[str, Any]] = []
    runtime.subscribe(events.append)
    client.events_on_start = [_settled(node.node_id), {"type": "run_completed"}]
    runtime.start(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    events.clear()

    replacement = replace(
        client.snapshot,
        backend_generation=client.snapshot.backend_generation + 1,
        runtime_generation=client.snapshot.runtime_generation + 1,
    )
    client.snapshot = replacement
    client.emit({"type": "execution_generation_changed"}, snapshot=replacement)
    generation_event = next(
        event for event in events if event.get("type") == "solution_state_changed"
    )
    assert generation_event["project_id"] == model.project.project_id
    assert generation_event["workspace_id"] == workspace.workspace_id
    assert generation_event["expired_node_ids"] == [node.node_id]
    assert generation_event["removed_node_ids"] == []
    assert generation_event["reason_code"] == "runtime_generation_replaced"

    events.clear()
    runtime.reset_project_session("replacement", "")
    project_event = next(
        event for event in events if event.get("type") == "solution_state_changed"
    )
    assert project_event["expired_node_ids"] == []
    assert project_event["removed_node_ids"] == [node.node_id]
    assert project_event["reason_code"] == "project_session_reset"

def test_dispatch_rejects_revision_and_generation_drift_and_releases_start() -> None:
    runtime, client, _registry, model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        snapshot,
        (node.node_id,),
        "property_changed",
    )
    with pytest.raises(ValueError, match="workspace_revision"):
        runtime.dispatch_prepared(prepared)
    assert "release_reservation" in client.operations
    assert runtime.solution_store.stats()["runs"] == 0

    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    client.snapshot = replace(
        client.snapshot,
        backend_generation=2,
        runtime_generation=2,
    )
    with pytest.raises(ValueError, match="runtime_generation"):
        runtime.dispatch_prepared(prepared)


def test_warm_reservation_rejects_a_successor_generation_before_start() -> None:
    runtime, client, _registry, _model, workspace, _node, snapshot = (
        _runtime_with_constant()
    )
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    client.reservation_generation = 2
    with pytest.raises(ValueError, match="prepared_runtime_generation_changed"):
        runtime.dispatch_prepared(prepared)
    assert "start_reserved_run" not in client.operations
    assert runtime.solution_store.stats()["runs"] == 0


@pytest.mark.parametrize("change", ["revision", "generation", "failure"])
def test_retirement_revalidates_dispatch_and_releases_failed_reservations(
    change: str,
) -> None:
    runtime, client, _registry, model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )

    def retire(workspace_id: str) -> int:
        assert workspace_id == workspace.workspace_id
        if change == "revision":
            runtime.invalidate_solution(
                model.project.project_id, workspace_id, snapshot,
                (node.node_id,), "property_changed",
            )
        elif change == "generation":
            client.snapshot = replace(
                client.snapshot, backend_generation=2, runtime_generation=2,
            )
        else:
            raise TimeoutError("retirement failed")
        return 0

    try:
        with patch.object(client, "retire_workspace", retire):
            with pytest.raises(
                (ValueError, TimeoutError),
                match="prepared_dispatch_changed_before_start|retirement failed",
            ):
                runtime.dispatch_prepared(prepared)
        assert "start_reserved_run" not in client.operations
        assert "release_reservation" in client.operations
        assert not client.viewer_reservations
        assert runtime.solution_store.stats()["runs"] == 0
        assert not runtime._run_artifact_services  # noqa: SLF001
    finally:
        runtime.shutdown()


def test_cold_successor_adopts_generation_before_synchronous_terminal() -> None:
    runtime, client, _registry, model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    events: list[dict[str, Any]] = []
    runtime.subscribe(events.append)
    first = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    client.events_on_start = [
        _settled(node.node_id),
        {"type": "run_completed"},
    ]
    runtime.dispatch_prepared(first)
    assert runtime.solution_store.stats()["records"] == 1
    events.clear()

    client.snapshot = replace(
        client.snapshot,
        available=False,
        reason="execution_generation_unavailable",
    )
    client.reservation_generation = 2
    client.events_on_start = [_settled(node.node_id), {"type": "run_completed"}]
    cold = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    assert all(
        decision.action is PreparedAction.EXECUTE
        for decision in cold.node_decisions
    )
    runtime.dispatch_prepared(cold)
    fact = runtime.solution_facts(
        model.project.project_id,
        workspace.workspace_id,
    )[0]
    assert fact.freshness is SolutionFreshness.CURRENT
    assert runtime.solution_store.stats()["records"] == 1
    assert runtime.solution_store.stats()["runs"] == 0
    assert any(
        event.get("type") == "solution_state_changed"
        and event.get("reason_code") == "runtime_generation_replaced"
        for event in events
    )
    reset_index = next(
        index
        for index, event in enumerate(events)
        if event.get("type") == "solution_state_changed"
    )
    settled_index = next(
        index
        for index, event in enumerate(events)
        if event.get("type") == "node_settled"
    )
    terminal_index = next(
        index
        for index, event in enumerate(events)
        if event.get("type") == "run_completed"
    )
    assert reset_index < settled_index < terminal_index


def test_registry_generation_adoption_publishes_solution_state_after_dispatch() -> None:
    runtime, client, _registry, model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    client.events_on_start = [_settled(node.node_id), {"type": "run_completed"}]
    runtime.start(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    events: list[dict[str, Any]] = []
    runtime.subscribe(events.append)
    prepared = runtime.prepare_execution(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            recompute_mode=RecomputeMode.FORCE_RECOMPUTE,
        )
    )
    runtime._registry = type(  # noqa: SLF001
        "PreviousRegistry",
        (),
        {"contract_fingerprint": lambda self: "previous-registry"},
    )()
    client.events_on_start = [_settled(node.node_id), {"type": "run_completed"}]

    runtime.dispatch_prepared(prepared)

    assert any(
        event.get("type") == "solution_state_changed"
        and event.get("project_id") == model.project.project_id
        and event.get("workspace_id") == workspace.workspace_id
        and event.get("reason_code") == "registry_generation_replaced"
        for event in events
    )
    assert runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0].freshness is SolutionFreshness.CURRENT
    reset_index = next(
        index
        for index, event in enumerate(events)
        if event.get("type") == "solution_state_changed"
    )
    settled_index = next(
        index
        for index, event in enumerate(events)
        if event.get("type") == "node_settled"
    )
    assert reset_index < settled_index


def test_first_unsaved_invalidation_initializes_a_blank_solution_session() -> None:
    runtime, client, _registry, model, workspace, node, snapshot = (
        _runtime_with_constant()
    )

    result = runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        snapshot,
        (node.node_id,),
        "property_changed",
    )
    assert result.expired_node_ids == (node.node_id,)
    first = runtime.solution_facts(model.project.project_id, workspace.workspace_id)[0]
    assert first.freshness is SolutionFreshness.EXPIRED
    assert first.retained_record_id is None

    client.events_on_start = [_settled(node.node_id), {"type": "run_completed"}]
    runtime.start(
        ExecutionRequest(
            runtime_snapshot=snapshot,
            workspace_id=workspace.workspace_id,
            recompute_mode=RecomputeMode.FORCE_RECOMPUTE,
        )
    )
    record_id = runtime.solution_facts(
        model.project.project_id, workspace.workspace_id
    )[0].retained_record_id
    assert record_id is not None

    runtime.reset_project_session(model.project.project_id, "")
    runtime.invalidate_solution(
        model.project.project_id,
        workspace.workspace_id,
        snapshot,
        (node.node_id,),
        "property_changed",
    )
    reset = runtime.solution_facts(model.project.project_id, workspace.workspace_id)[0]
    assert reset.freshness is SolutionFreshness.EXPIRED
    assert reset.retained_record_id is None
    assert runtime.solution_record(record_id) is None


@pytest.mark.parametrize("cycle_kind", ("self", "multi"))
def test_cycle_safe_invalidation_precedes_ordinary_prepare_rejection(
    cycle_kind: str,
) -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    first = model.add_node(
        workspace.workspace_id, "core.python_script", "First", 0, 0
    )
    cycle_node_ids = {first.node_id}
    if cycle_kind == "self":
        model.add_edge(
            workspace.workspace_id,
            first.node_id,
            "result",
            first.node_id,
            "payload",
        )
    else:
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
        cycle_node_ids.add(second.node_id)
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    compiled = compile_runtime_snapshot(
        snapshot,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    expected_expired = tuple(
        node.node_id for node in compiled.nodes if node.node_id in cycle_node_ids
    )
    runtime = CorexRuntime(client=_PreparedClient(), registry=registry)
    try:
        invalidated = runtime.invalidate_solution(
            model.project.project_id,
            workspace.workspace_id,
            snapshot,
            (first.node_id,),
            "graph_changed",
        )
        assert invalidated.expired_node_ids == expected_expired
        with pytest.raises(ValueError, match="Cycle detected among nodes:"):
            runtime.prepare_execution(
                ExecutionRequest(
                    runtime_snapshot=snapshot,
                    workspace_id=workspace.workspace_id,
                )
            )
    finally:
        runtime.shutdown()


def test_passive_flow_cycle_compiles_out_of_invalidation_and_preparation() -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
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
    active = model.add_node(
        workspace.workspace_id, "core.constant", "Active", 0, 200
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
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    runtime = CorexRuntime(client=_PreparedClient(), registry=registry)
    try:
        invalidated = runtime.invalidate_solution(
            model.project.project_id,
            workspace.workspace_id,
            snapshot,
            (active.node_id,),
            "graph_changed",
        )
        assert invalidated.expired_node_ids == (active.node_id,)
        filtered = runtime.prepare_execution(
            ExecutionRequest(
                runtime_snapshot=snapshot,
                workspace_id=workspace.workspace_id,
                target_node_ids=(first.node_id,),
            )
        )
        assert filtered.dispatch_envelope.target_node_ids == (first.node_id,)
        assert filtered.node_decisions == ()
        runtime.solution_store.discard_preparation(
            filtered.preparation_id,
            "test_probe",
        )
        prepared = runtime.prepare_execution(
            ExecutionRequest(
                runtime_snapshot=snapshot,
                workspace_id=workspace.workspace_id,
            )
        )
        assert tuple(item.node_id for item in prepared.node_decisions) == (
            active.node_id,
        )
    finally:
        runtime.shutdown()


def test_headless_boundaries_compile_once_and_preserve_authored_snapshot() -> None:
    import ea_node_editor.execution.runtime as runtime_module

    runtime, _client, registry, model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    compiled = compile_runtime_snapshot(
        snapshot,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    selected_plan = ExecutionPlan(
        compiled,
        registry,
        target_node_ids=(node.node_id,),
    )
    interface_plan = ExecutionPlan(compiled, registry)
    try:
        with patch.object(
            runtime_module,
            "compile_runtime_snapshot",
            wraps=compile_runtime_snapshot,
        ) as compile_mock:
            prepared = runtime.prepare_execution(
                ExecutionRequest(
                    runtime_snapshot=snapshot,
                    workspace_id=workspace.workspace_id,
                    target_node_ids=(node.node_id,),
                )
            )
            assert compile_mock.call_count == 1
            assert prepared.execution_plan_fingerprint == selected_plan.fingerprint
            assert prepared.workflow_interface_digest == (
                interface_plan.workflow_interface_digest
            )
            assert prepared.dispatch_envelope.decode_runtime_snapshot(
                catalog=registry.data_types
            ) == snapshot
            assert prepared.runtime_snapshot_fingerprint == canonical_digest(
                snapshot.to_document(catalog=registry.data_types)
            )

            assert runtime.dispatch_prepared(prepared) == "run_1"
            assert compile_mock.call_count == 2
            invalidated = runtime.invalidate_solution(
                model.project.project_id,
                workspace.workspace_id,
                snapshot,
                (node.node_id,),
                "graph_changed",
            )
            assert invalidated.expired_node_ids == (node.node_id,)
            assert compile_mock.call_count == 3
    finally:
        runtime.shutdown()


def test_prepared_reuse_consumes_the_preparation() -> None:
    runtime, client, _registry, _model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    first = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    client.events_on_start = [
        _settled(node.node_id),
        {"type": "run_completed"},
    ]
    runtime.dispatch_prepared(first)
    second = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    assert second.node_decisions[0].action is PreparedAction.REUSE
    assert runtime.dispatch_prepared(second) == "run_2"
    assert runtime.solution_store.stats()["preparations"] == 0
    assert runtime.solution_store.stats()["records"] == 1


def test_altered_reuse_dto_cannot_discard_the_registered_preparation() -> None:
    runtime, client, _registry, _model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    first = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    client.events_on_start = [
        _settled(node.node_id),
        {"type": "run_completed"},
    ]
    runtime.dispatch_prepared(first)
    reusable = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    altered = replace(
        reusable,
        node_decisions=(
            replace(reusable.node_decisions[0], reason_code="altered"),
        ),
    )
    with pytest.raises(ValueError, match="does not match registered state"):
        runtime.dispatch_prepared(altered)
    assert runtime.solution_store.stats()["preparations"] == 1
    assert runtime.dispatch_prepared(reusable) == "run_2"
    assert runtime.solution_store.stats()["preparations"] == 0


def test_worker_rejects_any_prepared_mismatch_before_node_events() -> None:
    runtime, client, registry, _model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    request = ExecutionRequest(
        runtime_snapshot=snapshot,
        workspace_id=workspace.workspace_id,
    )
    first = runtime.prepare_execution(request)
    client.events_on_start = [_settled(node.node_id), {"type": "run_completed"}]
    runtime.dispatch_prepared(first)
    second = runtime.prepare_execution(request)
    assert second.node_decisions[0].action is PreparedAction.REUSE
    client.events_on_start = [{"type": "run_completed"}]
    runtime.dispatch_prepared(second)
    command = client.commands[-1]
    accepted = command.accepted_output_payloads[0]
    bad_outputs = {
        "unknown": SettledPortResult(
            status="value",
            value=DataTree.from_item("cached"),
        )
    }
    encoded = settled_outputs_to_payload(
        bad_outputs,
        catalog=registry.data_types,
    )
    bad_digest = hashlib.sha256(
        json.dumps(
            encoded,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    bad_port_payload = AcceptedOutputPayload(
        node_id=accepted.node_id,
        record_id=accepted.record_id,
        solution_key=accepted.solution_key,
        settlement_status=accepted.settlement_status,
        result_digest=bad_digest,
        residency=accepted.residency,
        runtime_generation=accepted.runtime_generation,
        outputs=bad_outputs,
        catalog=registry.data_types,
    )
    mutations = (
        replace(command, runtime_snapshot_fingerprint="0" * 64),
        replace(command, execution_plan_fingerprint="0" * 64),
        replace(command, workflow_interface_digest="0" * 64),
        replace(command, solution_namespace_id="different-namespace"),
        replace(
            command,
            trigger_publication_generations=(("unknown-trigger", 1),),
        ),
        replace(
            command,
            node_decisions=(
                replace(command.node_decisions[0], solution_key="0" * 64),
            ),
        ),
        replace(
            command,
            node_decisions=(
                replace(command.node_decisions[0], reason_code="force_recompute"),
            ),
        ),
        replace(
            command,
            node_decisions=(
                replace(command.node_decisions[0], reason_code="no_reusable_record"),
            ),
        ),
        replace(
            command,
            accepted_output_payloads=(
                replace(accepted, result_digest="0" * 64),
            ),
        ),
        replace(command, accepted_output_payloads=(bad_port_payload,)),
    )
    for malformed in mutations:
        events: queue.Queue = queue.Queue()
        runner = WorkflowRunner(malformed, events)
        runner.run()
        emitted = []
        while not events.empty():
            emitted.append(events.get())
        assert any(event.get("type") == "run_failed" for event in emitted)
        assert not any(
            event.get("type") in {"node_started", "node_settled"}
            for event in emitted
        )


def test_evicted_reuse_preparation_reports_eviction() -> None:
    runtime, client, _registry, _model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    first = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    client.events_on_start = [
        _settled(node.node_id),
        {"type": "run_completed"},
    ]
    runtime.dispatch_prepared(first)
    runtime.solution_store._limits = replace(  # noqa: SLF001
        runtime.solution_store._limits,  # noqa: SLF001
        preparations_per_runtime=1,
    )
    evicted = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    with pytest.raises(ValueError, match="preparation_evicted"):
        runtime.dispatch_prepared(evicted)


def test_cold_route_uses_execute_only_key_and_failed_start_cleans_context() -> None:
    runtime, client, _registry, _model, workspace, node, snapshot = (
        _runtime_with_constant(cold=True)
    )
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    assert prepared.node_decisions[0].reason_code == "execution_generation_unavailable"
    client.raise_on_start = True
    with pytest.raises(RuntimeError, match="start failed"):
        runtime.dispatch_prepared(prepared)
    assert runtime.solution_store.stats()["runs"] == 0
    assert client.operations[-1] == "release_reservation"


def test_generation_replacement_evicts_records_and_project_reset_replaces_namespace() -> None:
    runtime, client, _registry, model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    client.events_on_start = [
        _settled(node.node_id),
        {"type": "run_completed"},
    ]
    runtime.dispatch_prepared(prepared)
    assert runtime.solution_store.stats()["records"] == 1
    client.snapshot = replace(
        client.snapshot,
        backend_generation=2,
        runtime_generation=2,
    )
    client.emit({"type": "run_completed", "run_id": "unregistered"})
    assert runtime.solution_store.stats()["records"] == 0
    assert runtime.solution_facts(
        model.project.project_id,
        workspace.workspace_id,
    )[0].freshness is SolutionFreshness.EXPIRED

    first_namespace = runtime.reset_project_session("new-project", "")
    assert runtime.reset_project_session("saved-project", "C:/work/saved.cxproj") == (
        "saved-project"
    )
    assert first_namespace != "new-project"
    assert runtime.solution_facts(model.project.project_id, workspace.workspace_id) == ()


def test_invalidation_holds_lifecycle_through_plan_and_store(
    monkeypatch,
) -> None:  # noqa: ANN001
    import ea_node_editor.execution.runtime as runtime_module

    runtime, _client, _registry, model, workspace, node, snapshot = (
        _runtime_with_constant()
    )
    runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    entered_plan = threading.Event()
    release_plan = threading.Event()
    reset_finished = threading.Event()
    errors: list[BaseException] = []
    real_plan = runtime_module.ExecutionPlan.for_invalidation

    def blocking_plan(_cls, *args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        entered_plan.set()
        assert release_plan.wait(5.0)
        return real_plan(*args, **kwargs)

    monkeypatch.setattr(
        runtime_module.ExecutionPlan,
        "for_invalidation",
        classmethod(blocking_plan),
    )

    def invalidate() -> None:
        try:
            runtime.invalidate_solution(
                model.project.project_id,
                workspace.workspace_id,
                snapshot,
                (node.node_id,),
                "property_changed",
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    invalidator = threading.Thread(target=invalidate)
    invalidator.start()
    assert entered_plan.wait(5.0)

    def reset() -> None:
        runtime.reset_project_session("replacement", "")
        reset_finished.set()

    replacer = threading.Thread(target=reset)
    replacer.start()
    assert not reset_finished.wait(0.1)
    release_plan.set()
    invalidator.join(5.0)
    replacer.join(5.0)
    assert not invalidator.is_alive() and not replacer.is_alive()
    assert errors == []
    assert runtime.solution_facts(
        model.project.project_id,
        workspace.workspace_id,
    ) == ()


def test_legacy_start_and_prepared_dispatch_share_one_lock_order() -> None:
    runtime, client, registry, _model, workspace, _node, snapshot = (
        _runtime_with_constant()
    )
    prepared = runtime.prepare_execution(
        ExecutionRequest(runtime_snapshot=snapshot, workspace_id=workspace.workspace_id)
    )
    launch = threading.Barrier(2)
    legacy_entered_client = threading.Event()
    dispatch_has_lifecycle = threading.Event()
    errors: list[BaseException] = []

    class OrderedLifecycleLock:
        def __init__(self) -> None:
            self._lock = threading.RLock()
            self._owners: dict[int, int] = {}

        def __enter__(self):  # noqa: ANN204
            self._lock.acquire()
            thread_id = threading.get_ident()
            self._owners[thread_id] = self._owners.get(thread_id, 0) + 1
            if threading.current_thread().name == "dispatch-thread":
                dispatch_has_lifecycle.set()
            return self

        def __exit__(self, *_args) -> None:  # noqa: ANN002
            thread_id = threading.get_ident()
            remaining = self._owners[thread_id] - 1
            if remaining:
                self._owners[thread_id] = remaining
            else:
                self._owners.pop(thread_id)
            self._lock.release()

        def owned_by_current_thread(self) -> bool:
            return threading.get_ident() in self._owners

    lifecycle_lock = OrderedLifecycleLock()
    runtime._lifecycle_lock = lifecycle_lock  # noqa: SLF001
    original_guard = client.registry_publication_guard

    @contextmanager
    def adversarial_guard():  # noqa: ANN202
        with original_guard():
            if threading.current_thread().name == "legacy-thread":
                legacy_entered_client.set()
                if not lifecycle_lock.owned_by_current_thread():
                    assert dispatch_has_lifecycle.wait(2.0)
            yield

    client.registry_publication_guard = adversarial_guard  # type: ignore[method-assign]

    def legacy_prepare(request):  # noqa: ANN001, ANN202
        runtime.replace_registry(registry)
        return request

    runtime.prepare_request = legacy_prepare  # type: ignore[method-assign]

    def legacy_start() -> None:
        try:
            launch.wait()
            runtime.start(
                ExecutionRequest(
                    runtime_snapshot=snapshot,
                    workspace_id=workspace.workspace_id,
                )
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def prepared_dispatch() -> None:
        try:
            launch.wait()
            assert legacy_entered_client.wait(2.0)
            runtime.dispatch_prepared(prepared)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    legacy_thread = threading.Thread(
        target=legacy_start,
        name="legacy-thread",
        daemon=True,
    )
    dispatch_thread = threading.Thread(
        target=prepared_dispatch,
        name="dispatch-thread",
        daemon=True,
    )
    legacy_thread.start()
    dispatch_thread.start()
    legacy_thread.join(5.0)
    dispatch_thread.join(5.0)
    assert not legacy_thread.is_alive() and not dispatch_thread.is_alive()
    assert errors == []


def test_trusted_reader_provenance_changes_keys_and_missing_paths_are_execute_only(
    tmp_path,
) -> None:  # noqa: ANN001
    source = tmp_path / "input.txt"
    source.write_text("first", encoding="utf-8")
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "io.file_read",
        "Read",
        0,
        0,
        properties={"path": str(source)},
    )
    client = _PreparedClient()
    runtime = CorexRuntime(client=client, registry=registry)

    def prepare():  # noqa: ANN202
        snapshot = build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=registry,
        )
        return runtime.prepare_execution(
            ExecutionRequest(
                runtime_snapshot=snapshot,
                workspace_id=workspace.workspace_id,
                target_node_ids=(node.node_id,),
            )
        )

    first = prepare()
    source.write_text("second", encoding="utf-8")
    second = prepare()
    assert first.node_decisions[0].solution_key != second.node_decisions[0].solution_key
    source.unlink()
    missing = prepare()
    repeated_missing = prepare()
    assert missing.node_decisions[0].reason_code != "no_reusable_record"
    assert missing.node_decisions[0].solution_key != (
        repeated_missing.node_decisions[0].solution_key
    )


def test_real_process_prepared_dispatch_smoke() -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Constant",
        0,
        0,
        properties={"value": "smoke"},
    )
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    runtime = CorexRuntime(registry=registry)
    terminal = threading.Event()
    terminal_types: list[str] = []

    def capture(event: dict[str, Any]) -> None:
        event_type = str(event.get("type", ""))
        if event_type in {"run_completed", "run_failed", "run_stopped"}:
            terminal_types.append(event_type)
            terminal.set()

    runtime.subscribe(capture)
    try:
        prepared = runtime.prepare_execution(
            ExecutionRequest(
                runtime_snapshot=snapshot,
                workspace_id=workspace.workspace_id,
            )
        )
        assert runtime.dispatch_prepared(prepared)
        assert terminal.wait(45.0)
        assert terminal_types == ["run_completed"]
        assert runtime.solution_facts(
            model.project.project_id,
            workspace.workspace_id,
        )[0].freshness is SolutionFreshness.CURRENT
    finally:
        runtime.shutdown()


def test_project_solution_binding_reset_detach_and_shutdown_lifecycle() -> None:
    backend = _DurableLifecycleBackend()
    factory = _DurableLifecycleFactory(backend)
    runtime = CorexRuntime(
        client=_PreparedClient(),
        registry=build_default_registry(),
        solution_repository_factory=factory,
    )
    runtime.reset_project_session("project", "C:/project.cxproj")
    result = runtime.bind_project_solution_store(
        "project",
        "C:/project.cxproj",
        {"schema_version": 1},
    )
    assert result.status_code == "durable_bound_active"
    assert runtime.solution_store.solution_namespace_id("project") == "stored-namespace"
    assert backend.close_calls == 0

    runtime.solution_store.reset_runtime_generation("test_generation")
    assert runtime.solution_store.durable_status == ("durable_bound_active", "")
    assert backend.close_calls == 0

    runtime.detach_project_solution_store("project", "project_replaced")
    assert backend.close_calls == 1
    assert runtime.solution_store.stats()["records"] == 0
    runtime.shutdown()
    assert backend.close_calls == 1


def test_project_solution_factory_failure_falls_back_without_partial_binding() -> None:
    class MalformedFactory:
        @staticmethod
        def open_backend(project_id, project_path, metadata, catalog):  # noqa: ANN001, ANN201
            del project_id, project_path, metadata, catalog
            return object()

    runtime = CorexRuntime(
        client=_PreparedClient(),
        registry=build_default_registry(),
        solution_repository_factory=MalformedFactory(),
    )
    assert runtime.reset_project_session("project", "C:/project.cxproj") == "project"
    result = runtime.bind_project_solution_store(
        "project",
        "C:/project.cxproj",
        {"schema_version": 1},
    )
    assert result.status_code == "durable_session_only_io_error"
    assert result.backend is None
    assert runtime.solution_store.solution_namespace_id("project") == "project"
    assert runtime.solution_store.stats()["records"] == 0
    runtime.shutdown()


@pytest.mark.parametrize(
    "operation", ["dispatch", "retire", "cancel_reservation", "cancel_viewer"],
)
def test_workspace_retirement_allows_an_earlier_reader_callback(operation: str) -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    model.add_node(workspace.workspace_id, "core.constant", "Constant", 0, 0)
    request = ExecutionRequest(
        runtime_snapshot=build_runtime_snapshot(
            model.project, workspace_id=workspace.workspace_id, registry=registry,
        ),
        workspace_id=workspace.workspace_id,
    )
    runtime = CorexRuntime(registry=registry)
    backend = runtime._client  # noqa: SLF001
    process = backend._process_client  # noqa: SLF001
    reader_entered = threading.Event()

    def observe(event: dict[str, Any]) -> None:
        if event.get("reason") == "retirement_reader_race":
            reader_entered.set()

    process.subscribe(observe)
    retire = backend.retire_workspace
    try:
        first = runtime.run(request, timeout=30.0)
        assert first.status == "completed"
        _wait_for_backend_run_cleanup(runtime)

        def retire_after_ordinary_event(workspace_id: str) -> int:
            process._event_queue.put({  # noqa: SLF001
                "type": "run_state",
                "run_id": first.run_id,
                "workspace_id": workspace_id,
                "state": "ready",
                "transition": "",
                "reason": "retirement_reader_race",
            })
            assert reader_entered.wait(5.0)
            count = retire(workspace_id)
            if operation == "cancel_reservation":
                reservation, _client = next(iter(backend._run_reservations.values()))  # noqa: SLF001
                backend.release_run_reservation(reservation, "cancelled")
            elif operation == "cancel_viewer":
                reservation = next(iter(backend._viewer_invalidation_reservations.values()))  # noqa: SLF001
                backend.cancel_viewer_invalidation(reservation)
            return count

        with patch.object(backend, "retire_workspace", retire_after_ordinary_event):
            if operation == "dispatch":
                assert runtime.run(request, timeout=30.0).status == "completed"
            elif operation == "retire":
                assert runtime.retire_workspace(workspace.workspace_id) == 0
            else:
                with patch.object(process, "start_run") as start_run:
                    with pytest.raises(ValueError, match="reservation"):
                        runtime.run(request, timeout=30.0)
                start_run.assert_not_called()
                assert not backend._run_reservations  # noqa: SLF001
                assert not backend._viewer_invalidation_reservations  # noqa: SLF001
                assert not process._active_run_id  # noqa: SLF001
                assert runtime.solution_store.stats()["runs"] == 0
    finally:
        runtime.shutdown()


def test_real_process_second_run_reuses_without_node_started() -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Constant",
        0,
        0,
        properties={"value": "cached"},
    )
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    runtime = CorexRuntime(registry=registry)
    request = ExecutionRequest(
        runtime_snapshot=snapshot,
        workspace_id=workspace.workspace_id,
    )
    try:
        first = runtime.run(request, timeout=30.0)
        _wait_for_backend_run_cleanup(runtime)
        second = runtime.run(request, timeout=30.0)
        assert first.status == "completed"
        assert second.status == "completed"
        for result in (first, second):
            event_types = [event.get("type") for event in result.events]
            self_scoped = [
                event_type
                for event_type in event_types
                if event_type in {
                    "run_preflight_accepted",
                    "viewer_invalidation_committed",
                    "run_started",
                    "node_started",
                    "node_settled",
                    "run_completed",
                }
            ]
            assert self_scoped[0] == "run_preflight_accepted"
            assert event_types.index("viewer_invalidation_committed") < (
                event_types.index("run_started")
            )
        assert runtime._client._viewer_invalidation_reservations == {}  # noqa: SLF001
        assert not any(
            event.get("type") == "node_started"
            and event.get("node_id") == node.node_id
            for event in second.events
        )
        settled = [
            event
            for event in second.events
            if event.get("type") == "node_settled"
            and event.get("node_id") == node.node_id
        ]
        assert len(settled) == 1
        assert settled[0]["disposition"] == "reused"
        assert runtime.solution_store.stats()["records"] == 1
    finally:
        runtime.shutdown()


def test_trusted_viewer_run_commits_identical_client_service_and_event_epochs() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    viewer = model.add_node(
        workspace.workspace_id,
        "model.viewer",
        "Viewer",
        0,
        0,
    )
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    runtime = CorexRuntime(registry=registry)
    try:
        result = runtime.run(
            ExecutionRequest(
                runtime_snapshot=snapshot,
                workspace_id=workspace.workspace_id,
                execution_backend={
                    "requested_backend": TRUSTED_IN_PROCESS_BACKEND,
                    "allow_trusted_in_process": True,
                },
                recompute_mode=RecomputeMode.FORCE_RECOMPUTE,
            ),
            timeout=30.0,
        )
        assert result.status == "completed", [
            (event.get("type"), event.get("error"), event.get("reason"))
            for event in result.events
        ]
        committed = next(
            event
            for event in result.events
            if event.get("type") == "viewer_invalidation_committed"
        )
        expected_epoch = dict(committed["viewer_node_invalidation_epochs"])[
            viewer.node_id
        ]
        backend = runtime._client  # noqa: SLF001
        trusted = backend._trusted_client  # noqa: SLF001
        key = (workspace.workspace_id, viewer.node_id)
        assert backend._node_viewer_epochs[key] == expected_epoch  # noqa: SLF001
        assert trusted._node_viewer_epochs[key] == expected_epoch  # noqa: SLF001
        assert (
            trusted._worker_services.viewer_session_service._node_invalidation_epochs[  # noqa: SLF001
                key
            ]
            == expected_epoch
        )
        assert backend._viewer_invalidation_reservations == {}  # noqa: SLF001
    finally:
        runtime.shutdown()


def test_real_dispatch_same_registry_bypasses_live_viewer_replaceability_guard() -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Constant",
        0,
        0,
    )
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    runtime = CorexRuntime(registry=registry)
    request = ExecutionRequest(
        runtime_snapshot=snapshot,
        workspace_id=workspace.workspace_id,
    )
    try:
        assert runtime.run(request, timeout=30.0).status == "completed"
        backend = runtime._client  # noqa: SLF001
        process = backend._process_client  # noqa: SLF001
        session_key = (workspace.workspace_id, "session_live")
        generation = process._catalog_generation_token_value()  # noqa: SLF001
        backend._session_clients[session_key] = process  # noqa: SLF001
        backend._session_client_generations[session_key] = generation  # noqa: SLF001
        backend._session_node_ids[session_key] = "viewer_live"  # noqa: SLF001
        process._viewer_session_ids.add(session_key)  # noqa: SLF001
        process._viewer_session_generations[session_key] = generation  # noqa: SLF001
        process._viewer_session_node_ids[session_key] = "viewer_live"  # noqa: SLF001

        second = runtime.run(request, timeout=30.0)

        assert second.status == "completed", second.events
        assert any(
            event.get("type") == "run_preflight_accepted"
            for event in second.events
        )
        assert session_key in backend._session_clients  # noqa: SLF001
        with pytest.raises(DataTypeCatalogError, match="viewer routes"):
            backend.replace_registry(build_builtin_registry())
        assert session_key in backend._session_clients  # noqa: SLF001
    finally:
        runtime.shutdown()


def test_selected_and_diamond_reuse_preserve_plan_order() -> None:
    registry = build_default_registry()
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
    left = model.add_node(
        workspace.workspace_id,
        "math.construct_interval",
        "Left",
        200,
        -100,
        properties={"end": 1.0},
    )
    right = model.add_node(
        workspace.workspace_id,
        "math.construct_interval",
        "Right",
        200,
        100,
        properties={"end": 2.0},
    )
    left_parts = model.add_node(
        workspace.workspace_id,
        "math.deconstruct_interval",
        "Left Parts",
        400,
        -100,
    )
    right_parts = model.add_node(
        workspace.workspace_id,
        "math.deconstruct_interval",
        "Right Parts",
        400,
        100,
    )
    point = model.add_node(
        workspace.workspace_id,
        "reference.construct_point",
        "Point",
        600,
        0,
    )
    for target in (left, right):
        model.add_edge(
            workspace.workspace_id,
            source.node_id,
            "value",
            target.node_id,
            "start",
        )
    model.add_edge(
        workspace.workspace_id,
        left.node_id,
        "interval",
        left_parts.node_id,
        "interval",
    )
    model.add_edge(
        workspace.workspace_id,
        right.node_id,
        "interval",
        right_parts.node_id,
        "interval",
    )
    model.add_edge(
        workspace.workspace_id,
        left_parts.node_id,
        "end",
        point.node_id,
        "x",
    )
    model.add_edge(
        workspace.workspace_id,
        right_parts.node_id,
        "end",
        point.node_id,
        "y",
    )
    model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "value",
        point.node_id,
        "z",
    )
    runtime = CorexRuntime(registry=registry)
    def request(*targets: str) -> ExecutionRequest:
        return ExecutionRequest(
            runtime_snapshot=build_runtime_snapshot(
                model.project,
                workspace_id=workspace.workspace_id,
                registry=registry,
            ),
            workspace_id=workspace.workspace_id,
            target_node_ids=targets,
        )

    try:
        first = runtime.run(request(point.node_id), timeout=30.0)
        assert first.status == "completed", [
            (event.get("type"), event.get("error"), event.get("reason"))
            for event in first.events
        ]
        _wait_for_backend_run_cleanup(runtime)
        second = runtime.run(request(point.node_id), timeout=30.0)
        first_point = next(
            event
            for event in first.events
            if event.get("type") == "node_settled"
            and event.get("node_id") == point.node_id
        )
        second_settled = [
            event for event in second.events if event.get("type") == "node_settled"
        ]
        assert second.status == "completed", second.events
        assert not any(event.get("type") == "node_started" for event in second.events)
        # Current inputs are consumed without republishing their producer facts.
        assert [event["node_id"] for event in second_settled] == [point.node_id]
        assert all(event["disposition"] == "reused" for event in second_settled)
        assert second_settled[-1]["outputs"] == first_point["outputs"]

        left.properties["end"] = 9.0
        selected_probe = runtime.prepare_execution(request(left.node_id))
        assert [
            (item.node_id, item.action.value, item.reason_code)
            for item in selected_probe.node_decisions
        ] == [
            (source.node_id, "read_current", "current_result_accepted"),
            (left.node_id, "execute", "no_reusable_record"),
        ]
        runtime.solution_store.discard_preparation(
            selected_probe.preparation_id, "test_probe"
        )
        _wait_for_backend_run_cleanup(runtime)
        selected = runtime.run(request(left.node_id), timeout=30.0)
        assert selected.status == "completed"
        assert [
            event["node_id"]
            for event in selected.events
            if event.get("type") == "node_started"
        ] == [left.node_id]
        assert [
            (event["node_id"], event["disposition"])
            for event in selected.events
            if event.get("type") == "node_settled"
        ] == [(left.node_id, "recomputed")]
    finally:
        runtime.shutdown()
