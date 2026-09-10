# Purpose: Backend selection, run generation, reservation, viewer ownership, invalidation, and headless routing behavior.
# Map: subsystems/execution.md
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from ea_node_editor.execution.backend_client import ExecutionBackendClient
from ea_node_editor.execution.backends import (
    EXTERNAL_SUBPROCESS_BACKEND,
    PROCESS_ISOLATED_BACKEND,
    TRUSTED_IN_PROCESS_BACKEND,
    ExecutionBackendOrchestrator,
    ExecutionBackendSelection,
)
from ea_node_editor.execution.client_common import (
    _PendingViewerRequest,
)
from ea_node_editor.execution.client_generation import (
    ExecutionGenerationSnapshot,
    ExecutionRunReservation,
)
from ea_node_editor.execution.external_python_client import (
    ExternalPythonExecutionClient,
)
from ea_node_editor.execution.runtime import CorexRuntime
from ea_node_editor.execution.runtime_requests import (
    ExecutionRequest,
    WorkspaceSelection,
)
from ea_node_editor.execution.project_loader import (
    load_project,
    select_workspace,
)
from ea_node_editor.execution.prepared_execution import (
    AcceptedOutputPayload,
    PreparedAction,
    PreparedNodeDecision,
)
from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.protocol_codec import (
    event_to_dict,
)
from ea_node_editor.execution.python_environment import (
    resolve_python_environment,
)
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
)
from ea_node_editor.execution.run_messages import (
    RunPreflightAcceptedEvent,
    StartRunCommand,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.solution_identity import canonical_digest
from ea_node_editor.execution.trusted_client import TrustedInProcessExecutionClient
from ea_node_editor.execution.viewer_messages import (
    OpenViewerSessionCommand,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import (
    build_default_registry,
)
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import (
    COREX_VIEWER_SESSION_HANDLE_KIND,
    VIEWER_SESSION_DATA_TYPE_ID,
    DataTypeCatalogError,
)
from ea_node_editor.runtime_contracts.solution_records import SolutionResidency
from tests.execution_client_fixtures import (
    ProcessClientTestHarness,
    _catalog_contract_fingerprint,
    _default_registry_agreement,
    _revision_catalog,
    _RoutingClient,
)


class BackendRouterTests(unittest.TestCase):
    def test_backend_viewer_forwarding_has_exact_query_and_empty_invalidation_contract(
        self,
    ) -> None:
        backend = ExecutionBackendClient()
        try:
            self.assertEqual(
                backend.query_viewer_session(
                    "ws_missing",
                    "viewer_missing",
                    "session_missing",
                    query_type="bounds",
                ),
                "",
            )
            self.assertEqual(backend.invalidate_viewer_requests("ws_missing", ()), 0)
            with self.assertRaises(TypeError):
                backend.invalidate_viewer_requests("ws_missing", "viewer")
            owner = backend._process_client  # noqa: SLF001
            for node_id in ("viewer_a", "viewer_b"):
                session_key = ("ws_main", f"session_{node_id}")
                backend._session_clients[session_key] = owner  # noqa: SLF001
                backend._session_client_generations[session_key] = 0  # noqa: SLF001
                backend._session_node_ids[session_key] = node_id  # noqa: SLF001
            backend._workspace_clients["ws_main"] = owner  # noqa: SLF001
            backend._workspace_client_generations["ws_main"] = 0  # noqa: SLF001

            backend.invalidate_viewer_requests("ws_main", ("viewer_a",))

            self.assertNotIn(
                ("ws_main", "session_viewer_a"),
                backend._session_clients,  # noqa: SLF001
            )
            self.assertIn(
                ("ws_main", "session_viewer_b"),
                backend._session_clients,  # noqa: SLF001
            )
            self.assertIs(
                backend._workspace_clients["ws_main"],  # noqa: SLF001
                owner,
            )
        finally:
            backend.shutdown()

    def test_viewer_invalidation_reservation_stages_then_commits_once(self) -> None:
        backend = ExecutionBackendClient()
        selection = ExecutionBackendSelection()
        process = backend._process_client  # noqa: SLF001
        snapshot = ExecutionGenerationSnapshot(
            selection=selection,
            backend_generation=0,
            runtime_generation=0,
            environment_digest="a" * 64,
            available=True,
        )
        run_reservation = ExecutionRunReservation(
            run_id="run_viewer_commit",
            workspace_id="ws_main",
            selection=selection,
            generation_snapshot=snapshot,
        )
        for child in (
            backend._process_client,  # noqa: SLF001
            backend._trusted_client,  # noqa: SLF001
            backend._external_python_client,  # noqa: SLF001
        ):
            child._pending_viewer_requests["same_request"] = _PendingViewerRequest(  # noqa: SLF001
                request_id="same_request",
                command="open_viewer_session",
                workspace_id="ws_main",
                node_id="viewer_a",
                session_id="session_a",
            )
        session_key = ("ws_main", "session_a")
        backend._session_clients[session_key] = process  # noqa: SLF001
        backend._session_client_generations[session_key] = 0  # noqa: SLF001
        backend._session_node_ids[session_key] = "viewer_a"  # noqa: SLF001
        before = tuple(
            (
                dict(child._workspace_viewer_epochs),  # noqa: SLF001
                dict(child._node_viewer_epochs),  # noqa: SLF001
                set(child._pending_viewer_requests),  # noqa: SLF001
            )
            for child in (
                backend._process_client,  # noqa: SLF001
                backend._trusted_client,  # noqa: SLF001
                backend._external_python_client,  # noqa: SLF001
            )
        )
        try:
            staged = backend.reserve_viewer_invalidation(
                run_reservation, "prepared_viewer_commit", ("viewer_a",)
            )
            self.assertEqual(
                tuple(
                    (
                        dict(child._workspace_viewer_epochs),  # noqa: SLF001
                        dict(child._node_viewer_epochs),  # noqa: SLF001
                        set(child._pending_viewer_requests),  # noqa: SLF001
                    )
                    for child in (
                        backend._process_client,  # noqa: SLF001
                        backend._trusted_client,  # noqa: SLF001
                        backend._external_python_client,  # noqa: SLF001
                    )
                ),
                before,
            )
            backend.cancel_viewer_invalidation(staged)
            self.assertEqual(backend._viewer_invalidation_reservations, {})  # noqa: SLF001

            staged = backend.reserve_viewer_invalidation(
                run_reservation, "prepared_viewer_commit", ("viewer_a",)
            )
            backend._active_clients[run_reservation.run_id] = process  # noqa: SLF001
            posted_payloads = []
            process._deliver_encoded_run_preflight_command = (  # type: ignore[method-assign]  # noqa: SLF001
                lambda payload, _transport: (
                    posted_payloads.append(payload) is None,
                    "",
                )
            )
            events: list[dict[str, object]] = []
            backend.subscribe(lambda event: events.append(dict(event)))

            backend._dispatch_client_event(  # noqa: SLF001
                process,
                event_to_dict(
                    RunPreflightAcceptedEvent(
                        run_id=staged.run_id,
                        workspace_id=staged.workspace_id,
                        preparation_id=staged.preparation_id,
                        viewer_invalidation_reservation_id=staged.reservation_id,
                        viewer_epoch_snapshot_digest=staged.snapshot_digest,
                    )
                ),
                generation_token=0,
            )

            self.assertEqual(
                [event["type"] for event in events],
                ["run_preflight_accepted", "viewer_invalidation_committed"],
            )
            self.assertEqual(events[-1]["retired_request_count"], 1)
            self.assertEqual(posted_payloads[-1]["type"], "commit_run_preflight")
            self.assertEqual(backend._viewer_invalidation_reservations, {})  # noqa: SLF001
            self.assertNotIn(session_key, backend._session_node_ids)  # noqa: SLF001
            for child in (
                backend._process_client,  # noqa: SLF001
                backend._trusted_client,  # noqa: SLF001
                backend._external_python_client,  # noqa: SLF001
            ):
                self.assertEqual(
                    child._node_viewer_epochs[("ws_main", "viewer_a")],  # noqa: SLF001
                    1,
                )
                self.assertNotIn("same_request", child._pending_viewer_requests)  # noqa: SLF001
        finally:
            backend.shutdown()

    def test_preflight_commit_delivery_failure_is_invisible_for_every_backend(
        self,
    ) -> None:
        selections = (
            ExecutionBackendSelection(),
            ExecutionBackendSelection(
                backend_id=TRUSTED_IN_PROCESS_BACKEND,
                isolation="in_process",
                trusted_in_process=True,
            ),
            ExecutionBackendSelection(
                backend_id=EXTERNAL_SUBPROCESS_BACKEND,
                isolation="external_subprocess",
                external_subprocess=True,
                python_executable="C:/python.exe",
            ),
        )

        def visible_state(backend):  # noqa: ANN001, ANN202
            children = (
                backend._process_client,  # noqa: SLF001
                backend._trusted_client,  # noqa: SLF001
                backend._external_python_client,  # noqa: SLF001
            )
            return (
                tuple(
                    (
                        dict(child._workspace_viewer_epochs),  # noqa: SLF001
                        dict(child._node_viewer_epochs),  # noqa: SLF001
                        dict(child._pending_viewer_requests),  # noqa: SLF001
                        set(child._viewer_session_ids),  # noqa: SLF001
                        dict(child._viewer_session_generations),  # noqa: SLF001
                        dict(child._viewer_session_node_ids),  # noqa: SLF001
                    )
                    for child in children
                ),
                dict(backend._workspace_viewer_epochs),  # noqa: SLF001
                dict(backend._node_viewer_epochs),  # noqa: SLF001
                dict(backend._workspace_clients),  # noqa: SLF001
                dict(backend._session_clients),  # noqa: SLF001
                dict(backend._session_node_ids),  # noqa: SLF001
                dict(backend._provisional_request_sessions),  # noqa: SLF001
            )

        for selection in selections:
            for failure_mode in ("false", "raise"):
                with self.subTest(
                    backend=selection.backend_id, failure_mode=failure_mode
                ):
                    backend = ExecutionBackendClient()
                    selected = backend._client_for_selection(selection)  # noqa: SLF001
                    run_reservation = ExecutionRunReservation(
                        run_id="run_delivery_failure",
                        workspace_id="ws_main",
                        selection=selection,
                        generation_snapshot=ExecutionGenerationSnapshot(
                            selection,
                            0,
                            0,
                            "a" * 64,
                            True,
                        ),
                    )
                    pending = _PendingViewerRequest(
                        request_id="pending_delivery",
                        command="open_viewer_session",
                        workspace_id="ws_main",
                        node_id="viewer_a",
                        session_id="session_a",
                    )
                    for child in (
                        backend._process_client,  # noqa: SLF001
                        backend._trusted_client,  # noqa: SLF001
                        backend._external_python_client,  # noqa: SLF001
                    ):
                        child._pending_viewer_requests[pending.request_id] = pending  # noqa: SLF001
                    service = (
                        backend._trusted_client._worker_services.viewer_session_service  # noqa: SLF001
                    )
                    service.open_session(
                        OpenViewerSessionCommand(
                            workspace_id="ws_main",
                            node_id="viewer_a",
                            session_id="service_session",
                            transport={"kind": "mock_live"},
                        )
                    )
                    service_before = service._sessions[  # noqa: SLF001
                        ("ws_main", "service_session")
                    ].public_projection()
                    reservation = backend.reserve_viewer_invalidation(
                        run_reservation,
                        "prepared_delivery_failure",
                        ("viewer_a",),
                    )
                    before = visible_state(backend)
                    selected._post_command = lambda _command: True  # type: ignore[method-assign]  # noqa: SLF001
                    if failure_mode == "false":
                        selected._deliver_encoded_run_preflight_command = (  # type: ignore[method-assign]  # noqa: SLF001
                            lambda _payload, _transport: (False, "delivery failed")
                        )
                    else:
                        selected._deliver_encoded_run_preflight_command = Mock(  # type: ignore[method-assign]  # noqa: SLF001
                            side_effect=RuntimeError("delivery exploded")
                        )
                    events = []
                    backend.subscribe(events.append)
                    try:
                        backend._dispatch_client_event(  # noqa: SLF001
                            selected,
                            event_to_dict(
                                RunPreflightAcceptedEvent(
                                    run_id=reservation.run_id,
                                    workspace_id=reservation.workspace_id,
                                    preparation_id=reservation.preparation_id,
                                    viewer_invalidation_reservation_id=(
                                        reservation.reservation_id
                                    ),
                                    viewer_epoch_snapshot_digest=(
                                        reservation.snapshot_digest
                                    ),
                                )
                            ),
                            generation_token=0,
                        )
                        self.assertEqual(visible_state(backend), before)
                        self.assertEqual(
                            service._sessions[  # noqa: SLF001
                                ("ws_main", "service_session")
                            ].public_projection(),
                            service_before,
                        )
                        self.assertFalse(
                            any(
                                event.get("type") == "viewer_invalidation_committed"
                                for event in events
                            )
                        )
                        self.assertTrue(
                            any(
                                event.get("type") == "protocol_error"
                                for event in events
                            )
                        )
                    finally:
                        backend.shutdown()

    def test_empty_reservation_is_participant_local_and_projection_is_independent(
        self,
    ) -> None:
        selections = (
            ExecutionBackendSelection(),
            ExecutionBackendSelection(
                backend_id=TRUSTED_IN_PROCESS_BACKEND,
                isolation="in_process",
                trusted_in_process=True,
            ),
            ExecutionBackendSelection(
                backend_id=EXTERNAL_SUBPROCESS_BACKEND,
                isolation="external_subprocess",
                external_subprocess=True,
                python_executable="C:/python.exe",
            ),
        )
        for selection in selections:
            with self.subTest(backend=selection.backend_id):
                backend = ExecutionBackendClient()
                children = (
                    backend._process_client,  # noqa: SLF001
                    backend._trusted_client,  # noqa: SLF001
                    backend._external_python_client,  # noqa: SLF001
                )
                selected = backend._client_for_selection(selection)  # noqa: SLF001
                owner = next(child for child in children if child is not selected)
                for child, epoch in zip(children, (1, 3, 5), strict=True):
                    child._workspace_viewer_epochs["ws_main"] = epoch  # noqa: SLF001
                backend._workspace_viewer_epochs["ws_main"] = 7  # noqa: SLF001
                pending = _PendingViewerRequest(
                    request_id="unrelated_pending",
                    command="open_viewer_session",
                    workspace_id="ws_main",
                    node_id="viewer_b",
                    session_id="session_b",
                )
                owner._pending_viewer_requests[pending.request_id] = pending  # noqa: SLF001
                session_key = ("ws_main", "session_b")
                owner._viewer_session_ids.add(session_key)  # noqa: SLF001
                owner._viewer_session_generations[session_key] = 0  # noqa: SLF001
                owner._viewer_session_node_ids[session_key] = "viewer_b"  # noqa: SLF001
                backend._workspace_clients["ws_main"] = owner  # noqa: SLF001
                backend._workspace_client_generations["ws_main"] = 0  # noqa: SLF001
                backend._session_clients[session_key] = owner  # noqa: SLF001
                backend._session_client_generations[session_key] = 0  # noqa: SLF001
                backend._session_node_ids[session_key] = "viewer_b"  # noqa: SLF001

                def visible_state():  # noqa: ANN202
                    return (
                        tuple(
                            (
                                dict(child._workspace_viewer_epochs),  # noqa: SLF001
                                dict(child._node_viewer_epochs),  # noqa: SLF001
                                dict(child._pending_viewer_requests),  # noqa: SLF001
                                set(child._viewer_session_ids),  # noqa: SLF001
                                dict(child._viewer_session_generations),  # noqa: SLF001
                                dict(child._viewer_session_node_ids),  # noqa: SLF001
                            )
                            for child in children
                        ),
                        dict(backend._workspace_viewer_epochs),  # noqa: SLF001
                        dict(backend._node_viewer_epochs),  # noqa: SLF001
                        dict(backend._workspace_clients),  # noqa: SLF001
                        dict(backend._session_clients),  # noqa: SLF001
                        dict(backend._session_node_ids),  # noqa: SLF001
                    )

                run_reservation = ExecutionRunReservation(
                    run_id=f"run_empty_{selection.backend_id}",
                    workspace_id="ws_main",
                    selection=selection,
                    generation_snapshot=ExecutionGenerationSnapshot(
                        selection, 0, 0, "a" * 64, True
                    ),
                )
                reservation = backend.reserve_viewer_invalidation(
                    run_reservation,
                    "prepared_empty",
                    (),
                )
                before = visible_state()
                delivered_payloads = []
                selected._deliver_encoded_run_preflight_command = (  # type: ignore[method-assign]  # noqa: SLF001
                    lambda payload, _transport: (
                        delivered_payloads.append(payload) is None,
                        "",
                    )
                )
                events = []
                backend.subscribe(events.append)
                try:
                    backend._dispatch_client_event(  # noqa: SLF001
                        selected,
                        event_to_dict(
                            RunPreflightAcceptedEvent(
                                run_id=reservation.run_id,
                                workspace_id=reservation.workspace_id,
                                preparation_id=reservation.preparation_id,
                                viewer_invalidation_reservation_id=(
                                    reservation.reservation_id
                                ),
                                viewer_epoch_snapshot_digest=(
                                    reservation.snapshot_digest
                                ),
                            )
                        ),
                        generation_token=0,
                    )
                    self.assertEqual(visible_state(), before)
                    committed = events[-1]
                    self.assertEqual(committed["retired_request_count"], 0)
                    self.assertEqual(
                        committed["viewer_workspace_invalidation_epoch"], 7
                    )
                    self.assertEqual(
                        committed["viewer_epoch_snapshot_digest"],
                        reservation.projection_snapshot.snapshot_digest,
                    )
                    payload = delivered_payloads[-1]
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    self.assertEqual(
                        payload["viewer_epoch_snapshot_digest"],
                        reservation.snapshot_digest,
                    )
                    self.assertNotEqual(
                        reservation.snapshot_digest,
                        reservation.projection_snapshot.snapshot_digest,
                    )
                finally:
                    backend.shutdown()

    def test_global_reservation_advances_each_participant_once(self) -> None:
        backend = ExecutionBackendClient()
        children = (
            backend._process_client,  # noqa: SLF001
            backend._trusted_client,  # noqa: SLF001
            backend._external_python_client,  # noqa: SLF001
        )
        process = children[0]
        for child, epoch in zip(children, (1, 3, 5), strict=True):
            child._workspace_viewer_epochs["ws_main"] = epoch  # noqa: SLF001
            child._node_viewer_epochs[("ws_main", "viewer_a")] = epoch + 10  # noqa: SLF001
            child._pending_viewer_requests["same_request"] = _PendingViewerRequest(  # noqa: SLF001
                request_id="same_request",
                command="open_viewer_session",
                workspace_id="ws_main",
                node_id="viewer_a",
                session_id="session_a",
            )
            child._viewer_session_ids.add(("ws_main", "session_a"))  # noqa: SLF001
            child._viewer_session_generations[("ws_main", "session_a")] = 0  # noqa: SLF001
            child._viewer_session_node_ids[("ws_main", "session_a")] = "viewer_a"  # noqa: SLF001
        backend._workspace_viewer_epochs["ws_main"] = 7  # noqa: SLF001
        backend._node_viewer_epochs[("ws_main", "viewer_a")] = 19  # noqa: SLF001
        backend._session_clients[("ws_main", "session_a")] = process  # noqa: SLF001
        backend._session_client_generations[("ws_main", "session_a")] = 0  # noqa: SLF001
        backend._session_node_ids[("ws_main", "session_a")] = "viewer_a"  # noqa: SLF001
        selection = ExecutionBackendSelection()
        run_reservation = ExecutionRunReservation(
            run_id="run_global_local_epochs",
            workspace_id="ws_main",
            selection=selection,
            generation_snapshot=ExecutionGenerationSnapshot(
                selection, 0, 0, "a" * 64, True
            ),
        )
        reservation = backend.reserve_viewer_invalidation(
            run_reservation,
            "prepared_global",
            None,
        )
        process._deliver_encoded_run_preflight_command = (  # type: ignore[method-assign]  # noqa: SLF001
            lambda _payload, _transport: (True, "")
        )
        events = []
        backend.subscribe(events.append)
        try:
            backend._dispatch_client_event(  # noqa: SLF001
                process,
                event_to_dict(
                    RunPreflightAcceptedEvent(
                        run_id=reservation.run_id,
                        workspace_id=reservation.workspace_id,
                        preparation_id=reservation.preparation_id,
                        viewer_invalidation_reservation_id=reservation.reservation_id,
                        viewer_epoch_snapshot_digest=reservation.snapshot_digest,
                    )
                ),
                generation_token=0,
            )
            self.assertEqual(
                [child._workspace_viewer_epochs["ws_main"] for child in children],  # noqa: SLF001
                [2, 4, 6],
            )
            self.assertEqual(backend._workspace_viewer_epochs["ws_main"], 8)  # noqa: SLF001
            for child in children:
                self.assertNotIn(("ws_main", "viewer_a"), child._node_viewer_epochs)  # noqa: SLF001
                self.assertEqual(child._pending_viewer_requests, {})  # noqa: SLF001
                self.assertEqual(child._viewer_session_ids, set())  # noqa: SLF001
            self.assertNotIn(("ws_main", "viewer_a"), backend._node_viewer_epochs)  # noqa: SLF001
            self.assertEqual(events[-1]["retired_request_count"], 1)
            self.assertEqual(events[-1]["viewer_workspace_invalidation_epoch"], 8)
        finally:
            backend.shutdown()

    def test_scoped_reservation_translates_concrete_response_epochs(self) -> None:
        backend = ExecutionBackendClient()
        process = backend._process_client  # noqa: SLF001
        trusted = backend._trusted_client  # noqa: SLF001
        external = backend._external_python_client  # noqa: SLF001
        children = (process, trusted, external)
        for child, workspace_epoch, node_epoch in zip(
            children, (1, 3, 5), (2, 4, 6), strict=True
        ):
            child._workspace_viewer_epochs["ws_main"] = workspace_epoch  # noqa: SLF001
            child._node_viewer_epochs[("ws_main", "viewer_a")] = node_epoch  # noqa: SLF001
            child._node_viewer_epochs[("ws_main", "viewer_b")] = node_epoch + 9  # noqa: SLF001
            child._pending_viewer_requests["same_request"] = _PendingViewerRequest(  # noqa: SLF001
                request_id="same_request",
                command="open_viewer_session",
                workspace_id="ws_main",
                node_id="viewer_a",
                session_id="session_a",
            )
        backend._workspace_viewer_epochs["ws_main"] = 7  # noqa: SLF001
        backend._node_viewer_epochs[("ws_main", "viewer_a")] = 8  # noqa: SLF001
        backend._node_viewer_epochs[("ws_main", "viewer_b")] = 17  # noqa: SLF001
        session_b = ("ws_main", "session_b")
        backend._workspace_clients["ws_main"] = trusted  # noqa: SLF001
        backend._workspace_client_generations["ws_main"] = 0  # noqa: SLF001
        backend._session_clients[session_b] = trusted  # noqa: SLF001
        backend._session_client_generations[session_b] = 0  # noqa: SLF001
        backend._session_node_ids[session_b] = "viewer_b"  # noqa: SLF001
        selection = ExecutionBackendSelection()
        run_reservation = ExecutionRunReservation(
            run_id="run_scoped_translation",
            workspace_id="ws_main",
            selection=selection,
            generation_snapshot=ExecutionGenerationSnapshot(
                selection, 0, 0, "a" * 64, True
            ),
        )
        reservation = backend.reserve_viewer_invalidation(
            run_reservation,
            "prepared_scoped",
            ("viewer_a",),
        )
        process._deliver_encoded_run_preflight_command = (  # type: ignore[method-assign]  # noqa: SLF001
            lambda _payload, _transport: (True, "")
        )
        events = []
        backend.subscribe(events.append)
        try:
            backend._dispatch_client_event(  # noqa: SLF001
                process,
                event_to_dict(
                    RunPreflightAcceptedEvent(
                        run_id=reservation.run_id,
                        workspace_id=reservation.workspace_id,
                        preparation_id=reservation.preparation_id,
                        viewer_invalidation_reservation_id=reservation.reservation_id,
                        viewer_epoch_snapshot_digest=reservation.snapshot_digest,
                    )
                ),
                generation_token=0,
            )
            self.assertEqual(
                [
                    child._node_viewer_epochs[("ws_main", "viewer_a")]  # noqa: SLF001
                    for child in children
                ],
                [3, 5, 7],
            )
            self.assertEqual(backend._node_viewer_epochs[("ws_main", "viewer_a")], 9)  # noqa: SLF001
            self.assertIs(backend._session_clients[session_b], trusted)  # noqa: SLF001
            events.clear()
            backend._dispatch_client_event(  # noqa: SLF001
                trusted,
                {
                    "type": "viewer_session_updated",
                    "workspace_id": "ws_main",
                    "node_id": "viewer_b",
                    "session_id": "session_b",
                    "request_id": "",
                    "workspace_invalidation_epoch": 3,
                    "node_invalidation_epoch": 13,
                },
                generation_token=0,
            )
            self.assertEqual(events[-1]["workspace_invalidation_epoch"], 7)
            self.assertEqual(events[-1]["node_invalidation_epoch"], 17)
            backend._dispatch_client_event(  # noqa: SLF001
                process,
                {
                    "type": "viewer_session_opened",
                    "workspace_id": "ws_main",
                    "node_id": "viewer_a",
                    "session_id": "session_a_new",
                    "request_id": "",
                    "workspace_invalidation_epoch": 1,
                    "node_invalidation_epoch": 3,
                },
                generation_token=0,
            )
            self.assertEqual(events[-1]["workspace_invalidation_epoch"], 7)
            self.assertEqual(events[-1]["node_invalidation_epoch"], 9)
        finally:
            backend.shutdown()

    def test_commit_waits_state_before_viewer_without_deadlock_or_locked_callback(
        self,
    ) -> None:
        class BarrierLock:
            def __init__(self) -> None:
                self._lock = threading.Lock()
                self.waiting = threading.Event()

            def acquire(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN202
                if self._lock.locked():
                    self.waiting.set()
                return self._lock.acquire(*args, **kwargs)

            def release(self) -> None:
                self._lock.release()

            def locked(self) -> bool:
                return self._lock.locked()

            def __enter__(self):  # noqa: ANN204
                self.acquire()
                return self

            def __exit__(self, *_args):  # noqa: ANN002, ANN204
                self.release()

        backend = ExecutionBackendClient()
        process = backend._process_client  # noqa: SLF001
        process_state_lock = BarrierLock()
        process._state_lock = process_state_lock  # type: ignore[assignment]  # noqa: SLF001
        selection = ExecutionBackendSelection()
        run_reservation = ExecutionRunReservation(
            run_id="run_lock_barrier",
            workspace_id="ws_main",
            selection=selection,
            generation_snapshot=ExecutionGenerationSnapshot(
                selection, 0, 0, "a" * 64, True
            ),
        )
        reservation = backend.reserve_viewer_invalidation(
            run_reservation,
            "prepared_lock_barrier",
            ("viewer_a",),
        )
        callback_events = []
        backend.subscribe(callback_events.append)
        delivery_observations = []

        def deliver(_payload, _transport):  # noqa: ANN001, ANN202
            delivery_observations.append(
                (
                    process._state_lock.locked(),  # noqa: SLF001
                    process._viewer_request_lock.locked(),  # noqa: SLF001
                    bool(callback_events),
                )
            )
            return True, ""

        process._deliver_encoded_run_preflight_command = deliver  # type: ignore[method-assign]  # noqa: SLF001
        response_holds_state = threading.Event()
        response_done = threading.Event()
        commit_done = threading.Event()
        commit_errors = []
        process._viewer_request_lock.acquire()  # noqa: SLF001

        def response_ingress() -> None:
            with process._state_lock:  # noqa: SLF001
                response_holds_state.set()
                with process._viewer_request_lock:  # noqa: SLF001
                    response_done.set()

        def commit() -> None:
            try:
                backend.commit_viewer_invalidation(reservation)
            except Exception as exc:  # noqa: BLE001
                commit_errors.append(exc)
            finally:
                commit_done.set()

        response_thread = threading.Thread(target=response_ingress)
        commit_thread = threading.Thread(target=commit)
        try:
            response_thread.start()
            self.assertTrue(response_holds_state.wait(1.0))
            commit_thread.start()
            self.assertTrue(process_state_lock.waiting.wait(1.0))
            process._viewer_request_lock.release()  # noqa: SLF001
            self.assertTrue(response_done.wait(1.0))
            self.assertTrue(commit_done.wait(1.0))
            response_thread.join(timeout=1.0)
            commit_thread.join(timeout=1.0)
            self.assertFalse(response_thread.is_alive())
            self.assertFalse(commit_thread.is_alive())
            self.assertEqual(commit_errors, [])
            self.assertEqual(delivery_observations, [(True, True, False)])
        finally:
            if process._viewer_request_lock.locked():  # noqa: SLF001
                process._viewer_request_lock.release()  # noqa: SLF001
            backend.shutdown()

    def test_commit_finalizer_survives_generation_drift_raising_subscriber_and_buffers(
        self,
    ) -> None:
        for generation_drift in (False, True):
            with self.subTest(generation_drift=generation_drift):
                backend = ExecutionBackendClient()
                process = backend._process_client  # noqa: SLF001
                selection = ExecutionBackendSelection()
                generation_snapshot = ExecutionGenerationSnapshot(
                    selection, 0, 0, "a" * 64, True
                )
                run_reservation = ExecutionRunReservation(
                    run_id=f"run_finalizer_{generation_drift}",
                    workspace_id="ws_main",
                    selection=selection,
                    generation_snapshot=generation_snapshot,
                )
                reservation = backend.reserve_viewer_invalidation(
                    run_reservation,
                    "prepared_finalizer",
                    ("viewer_a",),
                )
                backend._run_generation_snapshots[reservation.run_id] = (  # noqa: SLF001
                    generation_snapshot
                )

                def deliver(_payload, _transport):  # noqa: ANN001, ANN202
                    if generation_drift:
                        process._catalog_generation_token += 1  # noqa: SLF001
                        process._accepted_physical_generation_token += 1  # noqa: SLF001
                    return True, ""

                process._deliver_encoded_run_preflight_command = deliver  # type: ignore[method-assign]  # noqa: SLF001
                observed = []

                def buffer_run_events(event):  # noqa: ANN001, ANN202
                    if event.get("type") != "run_preflight_accepted":
                        return
                    for event_type in ("run_started", "run_completed"):
                        backend._dispatch_client_event(  # noqa: SLF001
                            process,
                            {
                                "type": event_type,
                                "run_id": reservation.run_id,
                                "workspace_id": "ws_main",
                            },
                            generation_token=0,
                        )

                def raising_subscriber(event):  # noqa: ANN001, ANN202
                    if event.get("type") == "viewer_invalidation_committed":
                        raise RuntimeError("subscriber failed")

                backend.subscribe(buffer_run_events)
                backend.subscribe(raising_subscriber)
                backend.subscribe(lambda event: observed.append(dict(event)))
                try:
                    backend._dispatch_client_event(  # noqa: SLF001
                        process,
                        event_to_dict(
                            RunPreflightAcceptedEvent(
                                run_id=reservation.run_id,
                                workspace_id=reservation.workspace_id,
                                preparation_id=reservation.preparation_id,
                                viewer_invalidation_reservation_id=(
                                    reservation.reservation_id
                                ),
                                viewer_epoch_snapshot_digest=(
                                    reservation.snapshot_digest
                                ),
                            )
                        ),
                        generation_token=0,
                    )
                    event_types = [event["type"] for event in observed]
                    self.assertEqual(
                        event_types[:2],
                        ["run_preflight_accepted", "viewer_invalidation_committed"],
                    )
                    self.assertEqual(
                        event_types.count("viewer_invalidation_committed"),
                        1,
                    )
                    if generation_drift:
                        self.assertEqual(event_types, event_types[:2])
                        self.assertEqual(
                            observed[1]["reason"],
                            "execution_generation_retired",
                        )
                        self.assertIsNone(observed[1]["viewer_invalidation_node_ids"])
                    else:
                        self.assertEqual(
                            event_types,
                            [
                                "run_preflight_accepted",
                                "viewer_invalidation_committed",
                                "run_started",
                                "run_completed",
                            ],
                        )
                    self.assertNotIn(
                        reservation.run_id,
                        backend._viewer_commit_publication_pending,  # noqa: SLF001
                    )
                    self.assertNotIn(
                        reservation.run_id,
                        backend._viewer_commit_event_buffers,  # noqa: SLF001
                    )
                finally:
                    backend.shutdown()

    def test_stale_participant_rejects_before_delivery_without_partial_commit(
        self,
    ) -> None:
        for stale_participant in ("process", "trusted", "external", "backend"):
            with self.subTest(stale_participant=stale_participant):
                backend = ExecutionBackendClient()
                process = backend._process_client  # noqa: SLF001
                run_reservation = ExecutionRunReservation(
                    run_id=f"run_stale_{stale_participant}",
                    workspace_id="ws_main",
                    selection=ExecutionBackendSelection(),
                    generation_snapshot=ExecutionGenerationSnapshot(
                        ExecutionBackendSelection(),
                        0,
                        0,
                        "a" * 64,
                        True,
                    ),
                )
                reservation = backend.reserve_viewer_invalidation(
                    run_reservation,
                    "prepared_stale_participant",
                    ("viewer_a",),
                )
                participant = {
                    "process": backend._process_client,  # noqa: SLF001
                    "trusted": backend._trusted_client,  # noqa: SLF001
                    "external": backend._external_python_client,  # noqa: SLF001
                    "backend": backend,
                }[stale_participant]
                participant._node_viewer_epochs[("ws_main", "viewer_a")] = 2  # noqa: SLF001
                before = tuple(
                    dict(child._node_viewer_epochs)  # noqa: SLF001
                    for child in (
                        backend._process_client,  # noqa: SLF001
                        backend._trusted_client,  # noqa: SLF001
                        backend._external_python_client,  # noqa: SLF001
                    )
                ) + (dict(backend._node_viewer_epochs),)  # noqa: SLF001
                delivery = Mock(return_value=(True, ""))
                process._deliver_encoded_run_preflight_command = delivery  # type: ignore[method-assign]  # noqa: SLF001
                process._post_command = lambda _command: True  # type: ignore[method-assign]  # noqa: SLF001
                try:
                    backend._dispatch_client_event(  # noqa: SLF001
                        process,
                        event_to_dict(
                            RunPreflightAcceptedEvent(
                                run_id=reservation.run_id,
                                workspace_id=reservation.workspace_id,
                                preparation_id=reservation.preparation_id,
                                viewer_invalidation_reservation_id=(
                                    reservation.reservation_id
                                ),
                                viewer_epoch_snapshot_digest=(
                                    reservation.snapshot_digest
                                ),
                            )
                        ),
                        generation_token=0,
                    )
                    after = tuple(
                        dict(child._node_viewer_epochs)  # noqa: SLF001
                        for child in (
                            backend._process_client,  # noqa: SLF001
                            backend._trusted_client,  # noqa: SLF001
                            backend._external_python_client,  # noqa: SLF001
                        )
                    ) + (dict(backend._node_viewer_epochs),)  # noqa: SLF001
                    self.assertEqual(after, before)
                    delivery.assert_not_called()
                finally:
                    backend.shutdown()

    def test_all_backend_start_paths_derive_agreement_from_supplied_catalog(
        self,
    ) -> None:
        registry = build_default_registry()
        catalog = registry.data_types
        expected_fingerprint, expected_revisions = catalog_agreement(catalog)
        stale_catalog = _revision_catalog("stale-v1")
        model = GraphModel()
        workspace = model.active_workspace
        model.add_node(
            workspace.workspace_id,
            "core.constant",
            "Constant",
            0,
            0,
            properties={"value": 1},
        )
        runtime_snapshot = build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=registry,
        )

        process = ProcessExecutionClient()
        external = ExternalPythonExecutionClient()
        trusted = TrustedInProcessExecutionClient()
        clients = (process, external, trusted)
        try:
            process._data_types = stale_catalog  # noqa: SLF001
            process_commands = []
            with (
                patch.object(process, "_ensure_process"),
                patch.object(
                    process,
                    "_post_command",
                    side_effect=lambda command: (
                        process_commands.append(command) or True
                    ),
                ),
            ):
                self.assertTrue(
                    process.start_run(
                        "",
                        workspace.workspace_id,
                        {"runtime_snapshot": runtime_snapshot},
                        data_types=catalog,
                        registry_contract_fingerprint=_catalog_contract_fingerprint(
                            catalog
                        ),
                    )
                )

            external._data_types = stale_catalog  # noqa: SLF001
            external_commands = []
            with (
                patch.object(external, "_ensure_process"),
                patch.object(
                    external,
                    "_post_command",
                    side_effect=lambda command: (
                        external_commands.append(command) or True
                    ),
                ),
            ):
                self.assertTrue(
                    external.start_run(
                        "",
                        workspace.workspace_id,
                        {"runtime_snapshot": runtime_snapshot},
                        execution_backend=ExecutionBackendSelection(
                            backend_id=EXTERNAL_SUBPROCESS_BACKEND,
                            isolation="external_subprocess",
                            external_subprocess=True,
                            python_executable=sys.executable,
                        ),
                        data_types=catalog,
                        registry_contract_fingerprint=_catalog_contract_fingerprint(
                            catalog
                        ),
                    )
                )

            trusted._data_types = stale_catalog  # noqa: SLF001
            trusted_commands = []
            trusted._run_workflow_thread = (  # type: ignore[method-assign]  # noqa: SLF001
                lambda command, _generation: trusted_commands.append(command)
            )
            self.assertTrue(
                trusted.start_run(
                    "",
                    workspace.workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    data_types=catalog,
                    registry_contract_fingerprint=_catalog_contract_fingerprint(
                        catalog
                    ),
                )
            )
            trusted._run_thread.join(timeout=2.0)  # noqa: SLF001

            commands = (
                *process_commands,
                *external_commands,
                *trusted_commands,
            )
            self.assertEqual(len(commands), 3)
            for command in commands:
                self.assertEqual(
                    command.catalog_fingerprint,
                    expected_fingerprint,
                )
                self.assertEqual(command.catalog_revisions, expected_revisions)
        finally:
            for client in clients:
                client.shutdown()

    def test_post_terminal_catalog_change_recycles_each_backend_generation(
        self,
    ) -> None:
        registry = build_default_registry()
        first_catalog = _revision_catalog("generation-v1")
        second_catalog = _revision_catalog("generation-v2")
        model = GraphModel()
        workspace = model.active_workspace
        model.add_node(
            workspace.workspace_id,
            "core.constant",
            "Constant",
            0,
            0,
            properties={"value": 1},
        )
        runtime_snapshot = build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=registry,
        )
        external_selection = ExecutionBackendSelection(
            backend_id=EXTERNAL_SUBPROCESS_BACKEND,
            isolation="external_subprocess",
            external_subprocess=True,
            python_executable=sys.executable,
        )

        for client in (
            ProcessExecutionClient(),
            ExternalPythonExecutionClient(),
            TrustedInProcessExecutionClient(),
        ):
            with self.subTest(client_type=type(client).__name__):
                commands = []
                if isinstance(client, TrustedInProcessExecutionClient):
                    client._run_workflow_thread = (  # type: ignore[method-assign]  # noqa: SLF001
                        lambda command, _generation: commands.append(command)
                    )
                    ensure_context = nullcontext()
                elif isinstance(client, ExternalPythonExecutionClient):
                    ensure_context = patch.object(client, "_ensure_process")
                else:
                    ensure_context = patch.object(client, "_ensure_process")
                try:
                    with (
                        ensure_context,
                        patch.object(
                            client,
                            "_post_command",
                            side_effect=lambda command: (
                                commands.append(command) or True
                            ),
                        ),
                        patch.object(
                            client,
                            "_recycle_catalog_generation",
                        ) as recycle,
                    ):
                        first_run_id = client.start_run(
                            "",
                            workspace.workspace_id,
                            {"runtime_snapshot": runtime_snapshot},
                            execution_backend=(
                                external_selection
                                if isinstance(
                                    client,
                                    ExternalPythonExecutionClient,
                                )
                                else None
                            ),
                            data_types=first_catalog,
                            registry_contract_fingerprint=_catalog_contract_fingerprint(
                                first_catalog
                            ),
                        )
                        self.assertTrue(first_run_id)
                        if isinstance(client, TrustedInProcessExecutionClient):
                            client._run_thread.join(timeout=2.0)  # noqa: SLF001
                        client._release_start_run(first_run_id)  # noqa: SLF001

                        second_run_id = client.start_run(
                            "",
                            workspace.workspace_id,
                            {"runtime_snapshot": runtime_snapshot},
                            execution_backend=(
                                external_selection
                                if isinstance(
                                    client,
                                    ExternalPythonExecutionClient,
                                )
                                else None
                            ),
                            data_types=second_catalog,
                            registry_contract_fingerprint=_catalog_contract_fingerprint(
                                second_catalog
                            ),
                        )
                        self.assertTrue(second_run_id)
                        if isinstance(client, TrustedInProcessExecutionClient):
                            client._run_thread.join(timeout=2.0)  # noqa: SLF001

                    recycle.assert_called_once_with()
                    self.assertIs(client._data_types, second_catalog)  # noqa: SLF001
                    self.assertEqual(  # noqa: SLF001
                        client._catalog_generation_fingerprint,
                        second_catalog.fingerprint(),
                    )
                    client._release_start_run(second_run_id)  # noqa: SLF001
                finally:
                    client.shutdown()

    def test_catalog_recycle_failure_preserves_old_worker_and_catalog_pin(
        self,
    ) -> None:
        first_catalog = _revision_catalog("stubborn-v1")
        second_catalog = _revision_catalog("stubborn-v2")

        process_client = ProcessExecutionClient()
        process_worker = Mock()
        process_worker.is_alive.return_value = True
        process_client._process = process_worker  # noqa: SLF001

        external_client = ExternalPythonExecutionClient()
        external_worker = Mock()
        external_worker.poll.return_value = None
        external_worker.wait.side_effect = subprocess.TimeoutExpired(
            cmd="external-worker",
            timeout=1.5,
        )
        external_client._process = external_worker  # noqa: SLF001

        cases = (
            (process_client, process_worker, None),
            (external_client, external_worker, "_terminate_process"),
        )
        try:
            for client, worker, termination_method in cases:
                with self.subTest(client_type=type(client).__name__):
                    client._data_types = first_catalog  # noqa: SLF001
                    client._catalog_generation_fingerprint = (  # noqa: SLF001
                        first_catalog.fingerprint()
                    )
                    client._registry_contract_generation_fingerprint = (  # noqa: SLF001
                        _catalog_contract_fingerprint(first_catalog)
                    )
                    client._catalog_generation_token = 7  # noqa: SLF001
                    termination_context = (
                        patch.object(client, termination_method)
                        if termination_method is not None
                        else nullcontext()
                    )
                    with (
                        patch.object(client, "_post_command", return_value=True),
                        termination_context as terminate,
                    ):
                        with self.assertRaisesRegex(
                            DataTypeCatalogError,
                            "Failed to recycle the idle worker generation",
                        ):
                            client._prepare_start_run(  # noqa: SLF001
                                "run_stubborn",
                                "ws_stubborn",
                                second_catalog,
                            )
                    if termination_method is not None:
                        terminate.assert_called_once_with(worker)
                    self.assertIs(client._process, worker)  # noqa: SLF001
                    self.assertIs(client._data_types, first_catalog)  # noqa: SLF001
                    self.assertEqual(  # noqa: SLF001
                        client._catalog_generation_fingerprint,
                        first_catalog.fingerprint(),
                    )
                    self.assertEqual(client._catalog_generation_token, 7)  # noqa: SLF001
                    self.assertEqual(client._active_run_id, "")  # noqa: SLF001
        finally:
            process_client._process = None  # noqa: SLF001
            external_client._process = None  # noqa: SLF001
            process_client.shutdown()
            external_client.shutdown()

    def test_catalog_change_preserves_active_viewer_session_and_routing(
        self,
    ) -> None:
        registry = build_default_registry()
        first_catalog = _revision_catalog("viewer-v1")
        second_catalog = _revision_catalog("viewer-v2")
        model = GraphModel()
        workspace = model.active_workspace
        runtime_snapshot = build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=registry,
        )
        backend = ExecutionBackendClient()
        client = backend._process_client  # noqa: SLF001
        client._data_types = first_catalog  # noqa: SLF001
        client._catalog_generation_fingerprint = (  # noqa: SLF001
            first_catalog.fingerprint()
        )
        client._registry_contract_generation_fingerprint = (  # noqa: SLF001
            _catalog_contract_fingerprint(first_catalog)
        )
        process = Mock()
        process.is_alive.return_value = True
        client._process = process  # noqa: SLF001
        client._catalog_generation_token = 1  # noqa: SLF001
        client._physical_generation_token = 1  # noqa: SLF001
        client._accepted_physical_generation_token = 1  # noqa: SLF001
        session_key = (workspace.workspace_id, "session_retained")
        client._viewer_session_ids.add(session_key)  # noqa: SLF001
        backend._session_clients[session_key] = client  # noqa: SLF001
        backend._workspace_clients[workspace.workspace_id] = client  # noqa: SLF001
        events: list[dict] = []
        backend.subscribe(events.append)

        try:
            with (
                patch.object(client, "_recycle_catalog_generation") as recycle,
                patch.object(
                    client,
                    "update_viewer_session",
                    return_value="viewer_preserved",
                ) as update_viewer,
            ):
                self.assertEqual(
                    backend.start_run(
                        "",
                        workspace.workspace_id,
                        {"runtime_snapshot": runtime_snapshot},
                        data_types=second_catalog,
                        registry_contract_fingerprint=_catalog_contract_fingerprint(
                            second_catalog
                        ),
                    ),
                    "",
                )
                request_id = backend.update_viewer_session(
                    workspace.workspace_id,
                    "node_viewer",
                    "session_retained",
                )

            recycle.assert_not_called()
            self.assertEqual(request_id, "viewer_preserved")
            update_viewer.assert_called_once_with(
                workspace.workspace_id,
                "node_viewer",
                "session_retained",
            )
            self.assertIs(client._data_types, first_catalog)  # noqa: SLF001
            self.assertIn(session_key, client._viewer_session_ids)  # noqa: SLF001
            self.assertIs(  # noqa: SLF001
                backend._session_clients[session_key],
                client,
            )
            self.assertTrue(
                any(
                    "viewer requests or sessions" in str(event.get("error", ""))
                    for event in events
                )
            )
        finally:
            client._viewer_session_ids.clear()  # noqa: SLF001
            client._process = None  # noqa: SLF001
            backend.shutdown()

    def test_dead_worker_viewer_state_does_not_block_catalog_change(
        self,
    ) -> None:
        first_catalog = _revision_catalog("dead-viewer-v1")
        second_catalog = _revision_catalog("dead-viewer-v2")
        process_client = ProcessExecutionClient()
        process = Mock()
        process.is_alive.return_value = False
        process_client._process = process  # noqa: SLF001
        external_client = ExternalPythonExecutionClient()
        external_process = Mock()
        external_process.poll.return_value = 1
        external_client._process = external_process  # noqa: SLF001

        try:
            for client in (process_client, external_client):
                with self.subTest(client_type=type(client).__name__):
                    client._data_types = first_catalog  # noqa: SLF001
                    client._catalog_generation_fingerprint = (  # noqa: SLF001
                        first_catalog.fingerprint()
                    )
                    client._registry_contract_generation_fingerprint = (  # noqa: SLF001
                        _catalog_contract_fingerprint(first_catalog)
                    )
                    client._catalog_generation_token = 1  # noqa: SLF001
                    client._physical_generation_token = 1  # noqa: SLF001
                    client._accepted_physical_generation_token = 1  # noqa: SLF001
                    session_key = ("ws_dead", "session_dead")
                    client._viewer_session_ids.add(session_key)  # noqa: SLF001
                    client._viewer_session_generations[session_key] = 1  # noqa: SLF001

                    with patch.object(
                        client,
                        "_recycle_catalog_generation",
                    ) as recycle:
                        self.assertTrue(
                            client._prepare_start_run(  # noqa: SLF001
                                "run_after_dead_viewer",
                                "ws_dead",
                                second_catalog,
                            )
                        )

                    recycle.assert_called_once_with()
                    self.assertEqual(client._viewer_session_ids, set())  # noqa: SLF001
                    self.assertEqual(  # noqa: SLF001
                        client._viewer_session_generations,
                        {},
                    )
                    self.assertEqual(  # noqa: SLF001
                        client._accepted_physical_generation_token,
                        -1,
                    )
                    self.assertEqual(client._catalog_generation_token, 2)  # noqa: SLF001
                    self.assertEqual(  # noqa: SLF001
                        client._start_run_pending_id,
                        "run_after_dead_viewer",
                    )
                    client._release_start_run(  # noqa: SLF001
                        "run_after_dead_viewer"
                    )
        finally:
            process_client._process = None  # noqa: SLF001
            external_client._process = None  # noqa: SLF001
            process_client.shutdown()
            external_client.shutdown()

    def test_backend_routes_are_generation_owned_and_ignore_delayed_events(
        self,
    ) -> None:
        backend = ExecutionBackendClient()
        client = backend._process_client  # noqa: SLF001
        client._catalog_generation_token = 1  # noqa: SLF001
        session_key = ("ws_old", "session_old")
        backend._active_clients["run_old"] = client  # noqa: SLF001
        backend._run_clients["run_old"] = client  # noqa: SLF001
        backend._run_client_generations["run_old"] = 1  # noqa: SLF001
        backend._run_workspace_ids["run_old"] = "ws_old"  # noqa: SLF001
        backend._workspace_clients["ws_old"] = client  # noqa: SLF001
        backend._workspace_client_generations["ws_old"] = 1  # noqa: SLF001
        backend._session_clients[session_key] = client  # noqa: SLF001
        backend._session_client_generations[session_key] = 1  # noqa: SLF001
        backend._session_node_ids[session_key] = "viewer_old"  # noqa: SLF001
        events: list[dict] = []
        backend.subscribe(events.append)

        try:
            client._catalog_generation_token = 2  # noqa: SLF001
            with backend._active_lock:  # noqa: SLF001
                backend._forget_client_generation_locked(client)  # noqa: SLF001

            self.assertNotIn("run_old", backend._active_clients)  # noqa: SLF001
            self.assertNotIn("run_old", backend._run_clients)  # noqa: SLF001
            self.assertNotIn("ws_old", backend._workspace_clients)  # noqa: SLF001
            self.assertNotIn(session_key, backend._session_clients)  # noqa: SLF001
            self.assertNotIn(session_key, backend._session_node_ids)  # noqa: SLF001

            backend._dispatch_client_event(  # noqa: SLF001
                client,
                {
                    "type": "viewer_session_opened",
                    "workspace_id": "ws_old",
                    "session_id": "session_old",
                },
                generation_token=1,
            )
            self.assertEqual(events, [])
            self.assertNotIn("ws_old", backend._workspace_clients)  # noqa: SLF001
            self.assertNotIn(session_key, backend._session_clients)  # noqa: SLF001
        finally:
            backend.shutdown()

    def test_failed_viewer_open_releases_only_the_requested_session_owner(
        self,
    ) -> None:
        backend = ExecutionBackendClient()
        client = backend._process_client  # noqa: SLF001
        retained_client = backend._trusted_client  # noqa: SLF001
        client._catalog_generation_token = 1  # noqa: SLF001
        failed_key = ("ws_viewer", "session_failed")
        live_key = ("ws_viewer", "session_live")
        request_id = "viewer_failed_open"

        try:
            backend._run_clients["run_retained"] = retained_client  # noqa: SLF001
            backend._run_client_generations["run_retained"] = 0  # noqa: SLF001
            backend._run_workspace_ids["run_retained"] = failed_key[0]  # noqa: SLF001
            backend._workspace_clients[failed_key[0]] = retained_client  # noqa: SLF001
            backend._workspace_client_generations[failed_key[0]] = 0  # noqa: SLF001
            backend._session_clients[failed_key] = retained_client  # noqa: SLF001
            backend._session_client_generations[failed_key] = 0  # noqa: SLF001
            backend._remember_requested_session_owner(  # noqa: SLF001
                client=client,
                workspace_id=failed_key[0],
                session_id=failed_key[1],
                request_id=request_id,
            )
            client._catalog_generation_token = 2  # noqa: SLF001
            backend._dispatch_client_event(  # noqa: SLF001
                client,
                {
                    "type": "viewer_session_failed",
                    "request_id": request_id,
                    "workspace_id": failed_key[0],
                    "session_id": failed_key[1],
                    "command": "open_viewer_session",
                },
                generation_token=2,
            )
            self.assertIs(backend._session_clients[failed_key], retained_client)  # noqa: SLF001
            self.assertIs(  # noqa: SLF001
                backend._workspace_clients[failed_key[0]],
                retained_client,
            )
            self.assertIs(  # noqa: SLF001
                backend._run_clients["run_retained"],
                retained_client,
            )

            backend._session_clients[live_key] = client  # noqa: SLF001
            backend._session_client_generations[live_key] = 2  # noqa: SLF001
            backend._workspace_clients[live_key[0]] = client  # noqa: SLF001
            backend._workspace_client_generations[live_key[0]] = 2  # noqa: SLF001
            backend._dispatch_client_event(  # noqa: SLF001
                client,
                {
                    "type": "viewer_session_failed",
                    "workspace_id": live_key[0],
                    "session_id": live_key[1],
                    "command": "update_viewer_session",
                },
                generation_token=2,
            )
            self.assertIs(backend._session_clients[live_key], client)  # noqa: SLF001
            self.assertIs(  # noqa: SLF001
                backend._workspace_clients[live_key[0]],
                client,
            )
        finally:
            backend.shutdown()

    def test_concurrent_failed_opens_restore_the_preexisting_session_owner(
        self,
    ) -> None:
        backend = ExecutionBackendClient()
        proposed_client = backend._process_client  # noqa: SLF001
        baseline_client = backend._trusted_client  # noqa: SLF001
        proposed_client._catalog_generation_token = 1  # noqa: SLF001
        session_key = ("ws_viewer", "session_shared")
        backend._session_clients[session_key] = baseline_client  # noqa: SLF001
        backend._session_client_generations[session_key] = 0  # noqa: SLF001

        try:
            for request_id in ("viewer_open_a", "viewer_open_b"):
                backend._remember_requested_session_owner(  # noqa: SLF001
                    client=proposed_client,
                    workspace_id=session_key[0],
                    session_id=session_key[1],
                    request_id=request_id,
                )

            backend._dispatch_client_event(  # noqa: SLF001
                proposed_client,
                {
                    "type": "viewer_session_failed",
                    "request_id": "viewer_open_a",
                    "workspace_id": session_key[0],
                    "session_id": session_key[1],
                    "command": "open_viewer_session",
                },
                generation_token=1,
            )
            self.assertIs(  # noqa: SLF001
                backend._session_clients[session_key],
                proposed_client,
            )

            backend._dispatch_client_event(  # noqa: SLF001
                proposed_client,
                {
                    "type": "viewer_session_failed",
                    "request_id": "viewer_open_b",
                    "workspace_id": session_key[0],
                    "session_id": session_key[1],
                    "command": "open_viewer_session",
                },
                generation_token=1,
            )
            self.assertIs(  # noqa: SLF001
                backend._session_clients[session_key],
                baseline_client,
            )
        finally:
            backend.shutdown()

    def test_stale_viewer_controls_do_not_fall_through_to_successor(
        self,
    ) -> None:
        backend = ExecutionBackendClient()
        stale_client = backend._process_client  # noqa: SLF001
        successor = backend._trusted_client  # noqa: SLF001
        stale_client._catalog_generation_token = 2  # noqa: SLF001
        controls = (
            ("update_viewer_session", {}),
            ("close_viewer_session", {}),
            ("materialize_viewer_data", {}),
            ("query_viewer_session", {"query_type": "camera"}),
        )

        try:
            for route_kind in ("run", "session", "workspace"):
                for method_name, extra_kwargs in controls:
                    with self.subTest(
                        route_kind=route_kind,
                        method_name=method_name,
                    ):
                        backend._clear_viewer_owners()  # noqa: SLF001
                        backend._active_clients["run_successor"] = successor  # noqa: SLF001
                        kwargs = dict(extra_kwargs)
                        if route_kind == "run":
                            backend._run_clients["run_stale"] = stale_client  # noqa: SLF001
                            backend._run_client_generations["run_stale"] = 1  # noqa: SLF001
                            kwargs["run_id"] = "run_stale"
                        elif route_kind == "session":
                            session_key = ("ws_stale", "session_stale")
                            backend._session_clients[session_key] = stale_client  # noqa: SLF001
                            backend._session_client_generations[session_key] = 1  # noqa: SLF001
                        else:
                            backend._workspace_clients["ws_stale"] = stale_client  # noqa: SLF001
                            backend._workspace_client_generations["ws_stale"] = 1  # noqa: SLF001

                        with (
                            patch.object(stale_client, method_name) as stale_call,
                            patch.object(successor, method_name) as successor_call,
                        ):
                            result = getattr(backend, method_name)(
                                "ws_stale",
                                "node_stale",
                                "session_stale",
                                **kwargs,
                            )

                        self.assertEqual(result, "")
                        stale_call.assert_not_called()
                        successor_call.assert_not_called()

            backend._clear_viewer_owners()  # noqa: SLF001
            session_key = ("ws_stale", "session_stale")
            backend._session_clients[session_key] = successor  # noqa: SLF001
            backend._session_client_generations[session_key] = 1  # noqa: SLF001
            with patch.object(backend._process_client, "query_viewer_session") as query:  # noqa: SLF001
                self.assertEqual(
                    backend.query_viewer_session(
                        "ws_stale",
                        "node_stale",
                        "session_stale",
                        query_type="camera",
                    ),
                    "",
                )
            query.assert_not_called()
        finally:
            backend.shutdown()

    def test_unowned_viewer_open_keeps_active_and_default_fallbacks(
        self,
    ) -> None:
        backend = ExecutionBackendClient()
        active_client = backend._trusted_client  # noqa: SLF001

        try:
            backend._active_clients["run_active"] = active_client  # noqa: SLF001
            with patch.object(
                active_client,
                "open_viewer_session",
                return_value="viewer_active",
            ) as active_open:
                self.assertEqual(
                    backend.open_viewer_session(
                        "ws_active",
                        "node_active",
                        session_id="session_active",
                    ),
                    "viewer_active",
                )
            active_open.assert_called_once()

            backend._clear_viewer_owners()  # noqa: SLF001
            backend._process_client._catalog_generation_token = 2  # noqa: SLF001
            backend._workspace_clients["ws_stale"] = backend._process_client  # noqa: SLF001
            backend._workspace_client_generations["ws_stale"] = 1  # noqa: SLF001
            backend._active_clients["run_active"] = active_client  # noqa: SLF001
            with patch.object(
                active_client,
                "open_viewer_session",
                return_value="viewer_after_stale",
            ) as stale_fallback_open:
                self.assertEqual(
                    backend.open_viewer_session(
                        "ws_stale",
                        "node_stale",
                        session_id="session_stale",
                    ),
                    "viewer_after_stale",
                )
            stale_fallback_open.assert_called_once()

            backend._clear_viewer_owners()  # noqa: SLF001
            with patch.object(
                backend._process_client,  # noqa: SLF001
                "open_viewer_session",
                return_value="viewer_default",
            ) as default_open:
                self.assertEqual(
                    backend.open_viewer_session(
                        "ws_default",
                        "node_default",
                        session_id="session_default",
                    ),
                    "viewer_default",
                )
            default_open.assert_called_once()
        finally:
            backend.shutdown()

    def test_newer_open_success_survives_older_late_success(self) -> None:
        backend = ExecutionBackendClient()
        older_client = backend._process_client  # noqa: SLF001
        newer_client = backend._trusted_client  # noqa: SLF001
        baseline_client = backend._external_python_client  # noqa: SLF001
        older_client._catalog_generation_token = 1  # noqa: SLF001
        newer_client._catalog_generation_token = 1  # noqa: SLF001
        baseline_client._catalog_generation_token = 1  # noqa: SLF001
        session_key = ("ws_viewer", "session_shared")
        backend._session_clients[session_key] = baseline_client  # noqa: SLF001
        backend._session_client_generations[session_key] = 1  # noqa: SLF001
        backend._workspace_clients[session_key[0]] = baseline_client  # noqa: SLF001
        backend._workspace_client_generations[session_key[0]] = 1  # noqa: SLF001

        try:
            backend._remember_requested_session_owner(  # noqa: SLF001
                client=older_client,
                workspace_id=session_key[0],
                session_id=session_key[1],
                request_id="viewer_open_older",
            )
            backend._remember_requested_session_owner(  # noqa: SLF001
                client=newer_client,
                workspace_id=session_key[0],
                session_id=session_key[1],
                request_id="viewer_open_newer",
            )

            backend._dispatch_client_event(  # noqa: SLF001
                newer_client,
                {
                    "type": "viewer_session_opened",
                    "request_id": "viewer_open_newer",
                    "workspace_id": session_key[0],
                    "session_id": session_key[1],
                },
                generation_token=1,
            )
            self.assertIs(  # noqa: SLF001
                backend._session_clients[session_key],
                newer_client,
            )
            self.assertIs(  # noqa: SLF001
                backend._workspace_clients[session_key[0]],
                newer_client,
            )

            backend._dispatch_client_event(  # noqa: SLF001
                older_client,
                {
                    "type": "viewer_session_opened",
                    "request_id": "viewer_open_older",
                    "workspace_id": session_key[0],
                    "session_id": session_key[1],
                },
                generation_token=1,
            )
            self.assertIs(  # noqa: SLF001
                backend._session_clients[session_key],
                newer_client,
            )
            self.assertIs(  # noqa: SLF001
                backend._workspace_clients[session_key[0]],
                newer_client,
            )
            self.assertEqual(backend._provisional_viewer_routes, {})  # noqa: SLF001
            self.assertEqual(backend._provisional_request_sessions, {})  # noqa: SLF001
        finally:
            backend.shutdown()

    def test_backend_routes_post_terminal_viewer_sessions_to_run_owners(
        self,
    ) -> None:
        process = _RoutingClient("process")
        external = _RoutingClient("external")
        trusted = _RoutingClient("trusted")
        backend = object.__new__(ExecutionBackendClient)
        backend._process_client = process  # noqa: SLF001
        backend._external_python_client = external  # noqa: SLF001
        backend._trusted_client = trusted  # noqa: SLF001
        backend._callbacks = []  # noqa: SLF001
        backend._active_lock = threading.Lock()  # noqa: SLF001
        backend._active_clients = {  # noqa: SLF001
            "run_external": external,
            "run_trusted": trusted,
        }
        backend._run_clients = dict(backend._active_clients)  # noqa: SLF001
        backend._run_workspace_ids = {  # noqa: SLF001
            "run_external": "ws_shared",
            "run_trusted": "ws_trusted",
        }
        backend._workspace_clients = {  # noqa: SLF001
            "ws_shared": external,
            "ws_trusted": trusted,
        }
        backend._session_clients = {}  # noqa: SLF001
        backend._terminal_run_ids_seen = set()  # noqa: SLF001

        backend._dispatch_client_event(  # noqa: SLF001
            external,
            {
                "type": "run_completed",
                "run_id": "run_external",
                "workspace_id": "ws_shared",
            },
        )
        backend._dispatch_client_event(  # noqa: SLF001
            trusted,
            {
                "type": "run_completed",
                "run_id": "run_trusted",
                "workspace_id": "ws_trusted",
            },
        )
        self.assertEqual(backend._active_clients, {})  # noqa: SLF001

        backend.open_viewer_session(
            "ws_shared",
            "node_external",
            session_id="session_external",
        )
        backend.open_viewer_session(
            "ws_trusted",
            "node_trusted",
            session_id="session_trusted",
        )
        backend.update_viewer_session(
            "ws_shared",
            "node_external",
            "session_external",
        )
        backend.query_viewer_session(
            "ws_shared",
            "node_external",
            "session_external",
            query_type="camera",
        )
        backend.update_viewer_session(
            "ws_trusted",
            "node_trusted",
            "session_trusted",
        )
        backend.query_viewer_session(
            "ws_trusted",
            "node_trusted",
            "session_trusted",
            query_type="camera",
        )

        self.assertEqual(
            [call[0] for call in external.calls],
            ["open", "update", "query"],
        )
        self.assertEqual(
            [call[0] for call in trusted.calls],
            ["open", "update", "query"],
        )
        self.assertEqual(process.calls, [])

        # A run ID disambiguates concurrent ownership even if workspaces collide.
        backend._run_clients["run_trusted_shared"] = trusted  # noqa: SLF001
        backend._run_workspace_ids["run_trusted_shared"] = "ws_shared"  # noqa: SLF001
        backend.open_viewer_session(
            "ws_shared",
            "node_trusted_shared",
            session_id="session_trusted_shared",
            run_id="run_trusted_shared",
        )
        self.assertEqual(trusted.calls[-1][0], "open")

        backend._dispatch_client_event(  # noqa: SLF001
            external,
            {
                "type": "viewer_session_closed",
                "workspace_id": "ws_shared",
                "session_id": "session_external",
            },
        )
        self.assertNotIn(
            ("ws_shared", "session_external"),
            backend._session_clients,  # noqa: SLF001
        )

    def test_backend_routes_same_session_id_by_workspace_and_run_precedence(
        self,
    ) -> None:
        process = _RoutingClient("process")
        external = _RoutingClient("external")
        trusted = _RoutingClient("trusted")
        backend = object.__new__(ExecutionBackendClient)
        backend._process_client = process  # noqa: SLF001
        backend._external_python_client = external  # noqa: SLF001
        backend._trusted_client = trusted  # noqa: SLF001
        backend._callbacks = []  # noqa: SLF001
        backend._active_lock = threading.Lock()  # noqa: SLF001
        backend._active_clients = {}  # noqa: SLF001
        backend._run_clients = {  # noqa: SLF001
            "run_external": external,
            "run_trusted": trusted,
        }
        backend._run_workspace_ids = {  # noqa: SLF001
            "run_external": "ws_external",
            "run_trusted": "ws_trusted",
        }
        backend._workspace_clients = {  # noqa: SLF001
            "ws_external": external,
            "ws_trusted": trusted,
        }
        backend._session_clients = {}  # noqa: SLF001
        backend._terminal_run_ids_seen = set()  # noqa: SLF001

        backend.open_viewer_session(
            "ws_external",
            "node_external",
            session_id="shared_session",
        )
        backend.open_viewer_session(
            "ws_trusted",
            "node_trusted",
            session_id="shared_session",
        )
        backend.update_viewer_session(
            "ws_external",
            "node_external",
            "shared_session",
        )
        backend.query_viewer_session(
            "ws_trusted",
            "node_trusted",
            "shared_session",
            query_type="camera",
        )
        self.assertEqual(
            [call[0] for call in external.calls],
            ["open", "update"],
        )
        self.assertEqual(
            [call[0] for call in trusted.calls],
            ["open", "query"],
        )

        # An explicit run owner wins even when the composite session points
        # at another backend.
        backend.update_viewer_session(
            "ws_external",
            "node_external",
            "shared_session",
            run_id="run_trusted",
        )
        self.assertEqual(trusted.calls[-1][0], "update")

        backend.close_viewer_session(
            "ws_external",
            "node_external",
            "shared_session",
        )
        backend._dispatch_client_event(  # noqa: SLF001
            external,
            {
                "type": "viewer_session_closed",
                "workspace_id": "ws_external",
                "session_id": "shared_session",
            },
        )
        self.assertNotIn(
            ("ws_external", "shared_session"),
            backend._session_clients,  # noqa: SLF001
        )
        self.assertIn(
            ("ws_trusted", "shared_session"),
            backend._session_clients,  # noqa: SLF001
        )
        backend.query_viewer_session(
            "ws_trusted",
            "node_trusted",
            "shared_session",
            query_type="camera",
        )
        self.assertEqual(trusted.calls[-1][0], "query")
        self.assertEqual(process.calls, [])

    def test_backend_bounds_completed_run_owners_with_open_session(self) -> None:
        process = _RoutingClient("process")
        external = _RoutingClient("external")
        trusted = _RoutingClient("trusted")
        backend = object.__new__(ExecutionBackendClient)
        backend._process_client = process  # noqa: SLF001
        backend._external_python_client = external  # noqa: SLF001
        backend._trusted_client = trusted  # noqa: SLF001
        backend._callbacks = []  # noqa: SLF001
        backend._active_lock = threading.Lock()  # noqa: SLF001
        backend._active_clients = {}  # noqa: SLF001
        backend._run_clients = {}  # noqa: SLF001
        backend._run_workspace_ids = {}  # noqa: SLF001
        backend._workspace_clients = {"ws_shared": external}  # noqa: SLF001
        backend._session_clients = {  # noqa: SLF001
            ("ws_shared", "live_session"): external,
        }
        backend._terminal_run_ids_seen = set()  # noqa: SLF001

        for index in range(70):
            run_id = f"run_{index:03d}"
            owner = external if index < 69 else trusted
            backend._active_clients[run_id] = owner  # noqa: SLF001
            backend._run_clients[run_id] = owner  # noqa: SLF001
            backend._run_workspace_ids[run_id] = "ws_shared"  # noqa: SLF001
            backend._workspace_clients["ws_shared"] = owner  # noqa: SLF001
            backend._dispatch_client_event(  # noqa: SLF001
                owner,
                {
                    "type": "run_completed",
                    "run_id": run_id,
                    "workspace_id": "ws_shared",
                },
            )

        self.assertLessEqual(
            len(backend._run_clients),  # noqa: SLF001
            backend._RETAINED_VIEWER_RUN_LIMIT,  # noqa: SLF001
        )
        self.assertLessEqual(
            len(backend._run_workspace_ids),  # noqa: SLF001
            backend._RETAINED_VIEWER_RUN_LIMIT,  # noqa: SLF001
        )
        backend.query_viewer_session(
            "ws_shared",
            "node",
            "live_session",
            query_type="camera",
        )
        self.assertEqual(external.calls[-1][0], "query")
        backend.open_viewer_session("ws_shared", "node")
        self.assertEqual(trusted.calls[-1][0], "open")

        backend._dispatch_client_event(  # noqa: SLF001
            external,
            {
                "type": "viewer_session_closed",
                "workspace_id": "ws_shared",
                "session_id": "live_session",
            },
        )
        self.assertEqual(backend._session_clients, {})  # noqa: SLF001
        self.assertEqual(backend._run_clients, {})  # noqa: SLF001
        self.assertEqual(backend._run_workspace_ids, {})  # noqa: SLF001
        self.assertEqual(backend._workspace_clients, {})  # noqa: SLF001

        backend._run_clients["run_after_close"] = trusted  # noqa: SLF001
        backend._run_workspace_ids["run_after_close"] = "ws_after"  # noqa: SLF001
        backend._workspace_clients["ws_after"] = trusted  # noqa: SLF001
        backend._session_clients[("ws_after", "session_after")] = trusted  # noqa: SLF001
        backend.shutdown()
        self.assertEqual(backend._run_clients, {})  # noqa: SLF001
        self.assertEqual(backend._run_workspace_ids, {})  # noqa: SLF001
        self.assertEqual(backend._workspace_clients, {})  # noqa: SLF001
        self.assertEqual(backend._session_clients, {})  # noqa: SLF001


class BackendSelectionIntegrationTests(ProcessClientTestHarness):
    def test_execution_backend_client_workflow_python_selection_truth_table(
        self,
    ) -> None:
        backend_client = ExecutionBackendClient()
        events: list[dict] = []
        backend_client.subscribe(events.append)
        workspace_id, blank_snapshot = self._build_runtime_snapshot()
        _workspace_id, project_snapshot = self._build_runtime_snapshot(
            workflow_python_path=f' "{sys.executable}" '
        )
        _workspace_id, invalid_project_snapshot = self._build_runtime_snapshot(
            workflow_python_path="missing-project-python"
        )
        process_start = patch.object(
            backend_client._process_client,  # noqa: SLF001
            "start_run",
            return_value="run_process",
        )
        trusted_start = patch.object(
            backend_client._trusted_client,  # noqa: SLF001
            "start_run",
            return_value="run_trusted",
        )
        external_start = patch.object(
            backend_client._external_python_client,  # noqa: SLF001
            "start_run",
            return_value="run_external",
        )

        cases = (
            (
                "explicit process",
                invalid_project_snapshot,
                {"requested_backend": PROCESS_ISOLATED_BACKEND},
                "process",
                0,
            ),
            (
                "explicit auto",
                invalid_project_snapshot,
                {"requested_backend": "auto"},
                "process",
                0,
            ),
            (
                "explicit trusted",
                invalid_project_snapshot,
                {
                    "requested_backend": TRUSTED_IN_PROCESS_BACKEND,
                    "allow_trusted_in_process": True,
                },
                "trusted",
                0,
            ),
            (
                "explicit external path",
                invalid_project_snapshot,
                {
                    "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
                    "allow_external_subprocess": True,
                    "python_executable": f' "{sys.executable}" ',
                },
                "external",
                1,
            ),
            (
                "explicit external project fallback",
                project_snapshot,
                {
                    "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
                    "allow_external_subprocess": True,
                },
                "external",
                1,
            ),
            (
                "quoted-empty double external project fallback",
                project_snapshot,
                {
                    "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
                    "allow_external_subprocess": True,
                    "python_executable": '""',
                },
                "external",
                1,
            ),
            (
                "quoted-empty single external project fallback",
                project_snapshot,
                {
                    "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
                    "allow_external_subprocess": True,
                    "python_executable": "''",
                },
                "external",
                1,
            ),
            (
                "implicit project",
                project_snapshot,
                None,
                "external",
                1,
            ),
            ("implicit built-in", blank_snapshot, None, "process", 0),
        )

        try:
            with (
                process_start as process,
                trusted_start as trusted,
                external_start as external,
                patch(
                    "ea_node_editor.execution.backend_client.resolve_python_environment",
                    wraps=resolve_python_environment,
                ) as resolve_python,
            ):
                clients = {
                    "process": process,
                    "trusted": trusted,
                    "external": external,
                }
                for label, snapshot, policy, expected_client, validations in cases:
                    with self.subTest(case=label):
                        for client_start in clients.values():
                            client_start.reset_mock()
                        resolve_python.reset_mock()

                        run_id = backend_client.start_run(
                            project_path="",
                            workspace_id=workspace_id,
                            trigger={"runtime_snapshot": snapshot},
                            execution_backend=policy,
                            **_default_registry_agreement(),
                        )

                        self.assertTrue(run_id)
                        clients[expected_client].assert_called_once()
                        self.assertEqual(resolve_python.call_count, validations)
                        if expected_client == "external":
                            selection = external.call_args.kwargs["execution_backend"]
                            self.assertEqual(
                                Path(selection.python_executable),
                                Path(sys.executable).resolve(),
                            )
                            self.assertNotIn(
                                "python_executable",
                                repr(snapshot.to_document()),
                            )

                for client_start in clients.values():
                    client_start.reset_mock()
                resolve_python.reset_mock()
                for pathless_value in (None, '""', "''"):
                    with self.subTest(pathless=pathless_value):
                        events.clear()
                        policy = {
                            "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
                            "allow_external_subprocess": True,
                        }
                        if pathless_value is not None:
                            policy["python_executable"] = pathless_value
                        self.assertEqual(
                            backend_client.start_run(
                                project_path="",
                                workspace_id=workspace_id,
                                trigger={"runtime_snapshot": blank_snapshot},
                                execution_backend=policy,
                                **_default_registry_agreement(),
                            ),
                            "",
                        )
                        self.assertEqual(resolve_python.call_count, 0)
                        self.assertEqual(
                            len(
                                [
                                    event
                                    for event in events
                                    if event.get("type") == "protocol_error"
                                ]
                            ),
                            1,
                        )
                        error = str(events[-1].get("error", ""))
                        self.assertIn("requires python_executable", error)
                        self.assertIn("Workflow Override", error)
                        self.assertIn("Create / Repair Managed Runtime", error)
                        for client_start in clients.values():
                            client_start.assert_not_called()
        finally:
            backend_client.shutdown()

    def test_backend_orchestrator_defaults_to_process_and_requires_trusted_opt_in(
        self,
    ) -> None:
        orchestrator = ExecutionBackendOrchestrator()

        default_selection = orchestrator.select()
        self.assertEqual(default_selection.backend_id, PROCESS_ISOLATED_BACKEND)
        self.assertEqual(default_selection.reason, "process_isolation_default")

        plugin_heavy_selection = orchestrator.select(
            {
                "runtime_backends": [
                    {
                        "backend_id": "packet.external",
                        "kind": "external_process",
                    }
                ]
            }
        )
        self.assertEqual(plugin_heavy_selection.backend_id, PROCESS_ISOLATED_BACKEND)
        self.assertEqual(
            plugin_heavy_selection.reason,
            "process_isolation_for_external_runtime_contracts",
        )

        with self.assertRaisesRegex(ValueError, "allow_trusted_in_process=True"):
            orchestrator.select(TRUSTED_IN_PROCESS_BACKEND)

        trusted_selection = orchestrator.select(
            {
                "requested_backend": TRUSTED_IN_PROCESS_BACKEND,
                "allow_trusted_in_process": True,
            }
        )
        self.assertEqual(trusted_selection.backend_id, TRUSTED_IN_PROCESS_BACKEND)
        self.assertTrue(trusted_selection.trusted_in_process)

        external_selection = orchestrator.select(
            {
                "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
                "runtime_backends": [
                    {
                        "backend_id": "packet.external",
                        "kind": "external_process",
                    }
                ],
            }
        )
        self.assertEqual(external_selection.backend_id, EXTERNAL_SUBPROCESS_BACKEND)
        self.assertTrue(external_selection.external_subprocess)

        python_selection = orchestrator.select(
            {
                "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
                "python_executable": sys.executable,
            }
        )
        self.assertEqual(python_selection.backend_id, EXTERNAL_SUBPROCESS_BACKEND)
        self.assertEqual(python_selection.python_executable, sys.executable)

    def test_execution_backend_client_rejects_invalid_workflow_python_executable(
        self,
    ) -> None:
        backend_client = ExecutionBackendClient()
        events: list[dict] = []
        events_lock = threading.Lock()

        def _on_event(event: dict) -> None:
            with events_lock:
                events.append(dict(event))

        def _wait_for_event(predicate, timeout: float = 6.0) -> dict | None:  # noqa: ANN001
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                with events_lock:
                    for event in events:
                        if predicate(event):
                            return event
                time.sleep(0.05)
            return None

        backend_client.subscribe(_on_event)
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_python = Path(tmp_dir) / "missing_python.exe"
            workspace_id, runtime_snapshot = self._build_runtime_snapshot(
                workflow_python_path=str(missing_python)
            )
            try:
                run_id = backend_client.start_run(
                    project_path="",
                    workspace_id=workspace_id,
                    trigger={"kind": "manual", "runtime_snapshot": runtime_snapshot},
                    **_default_registry_agreement(),
                )
                self.assertEqual(run_id, "")
                rejected = _wait_for_event(
                    lambda event: (
                        event.get("type") == "protocol_error"
                        and "does not exist" in str(event.get("error", ""))
                    ),
                    timeout=3.0,
                )
                self.assertIsNotNone(rejected)
            finally:
                backend_client.shutdown()

    def test_headless_runtime_loads_project_selects_workspace_and_runs_without_qapplication(
        self,
    ) -> None:
        qt_widgets = sys.modules.get("PyQt6.QtWidgets")
        qapplication_before = (
            qt_widgets.QApplication.instance() if qt_widgets is not None else None
        )
        model = GraphModel()
        workspace = model.active_workspace
        logger = model.add_node(
            workspace.workspace_id,
            "core.logger",
            "Logger",
            100,
            0,
            properties={"message": "headless ok"},
        )

        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_path = Path(tmp_dir) / "headless_runtime.cxproj"
            JsonProjectSerializer(registry).save(str(project_path), model.project)
            loaded = load_project(project_path, registry=registry)
            selected = select_workspace(loaded, WorkspaceSelection())
            self.assertEqual(selected.workspace_id, workspace.workspace_id)

            runtime = CorexRuntime(registry=registry)
            streamed_events: list[dict] = []
            try:
                result = runtime.run(
                    ExecutionRequest(
                        project_path=project_path, workspace_id=selected.workspace_id
                    ),
                    timeout=12.0,
                    on_event=streamed_events.append,
                )
            finally:
                runtime.shutdown()

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.workspace_id, workspace.workspace_id)
        self.assertIn("run_started", {event.get("type") for event in streamed_events})
        self.assertEqual(result.terminal_event.get("type"), "run_completed")
        qt_widgets = sys.modules.get("PyQt6.QtWidgets")
        qapplication_after = (
            qt_widgets.QApplication.instance() if qt_widgets is not None else None
        )
        self.assertIs(qapplication_after, qapplication_before)

    def test_corex_runtime_exposes_only_prepared_run_entrypoints(
        self,
    ) -> None:
        registry = build_default_registry()
        backend_client = Mock()
        runtime = CorexRuntime(client=backend_client, registry=registry)
        self.assertTrue(callable(runtime.prepare_execution))
        self.assertTrue(callable(runtime.dispatch_prepared))
        self.assertFalse(hasattr(runtime, "start_run"))
        self.assertFalse(hasattr(runtime, "_start_legacy"))


class PreparedRunReservationTests(unittest.TestCase):
    def test_run_events_keep_reserved_snapshot_when_prepare_changes_selection(
        self,
    ) -> None:
        backend = ExecutionBackendClient()
        process = backend._process_client  # noqa: SLF001
        selection_a = ExecutionBackendSelection(reason="run-a")
        selection_b = ExecutionBackendSelection(reason="prepare-only-b")
        snapshot_a = ExecutionGenerationSnapshot(
            selection_a,
            1,
            1,
            "a" * 64,
            True,
            "",
        )
        received = []
        backend.subscribe_generation_events(
            lambda _event, generation: received.append(generation)
        )
        try:
            with backend._active_lock:  # noqa: SLF001
                backend._run_clients["run-a"] = process  # noqa: SLF001
                backend._run_client_generations["run-a"] = 1  # noqa: SLF001
                backend._run_generation_snapshots["run-a"] = snapshot_a  # noqa: SLF001
                backend._run_workspace_ids["run-a"] = "ws_main"  # noqa: SLF001
            backend._client_selections[id(process)] = selection_b  # noqa: SLF001
            process._catalog_generation_token = 1  # noqa: SLF001
            with patch.object(
                backend,
                "_generation_snapshot_for_client",
                return_value=snapshot_a,
            ):
                backend._dispatch_client_event(  # noqa: SLF001
                    process,
                    {
                        "type": "node_settled",
                        "run_id": "run-a",
                        "workspace_id": "ws_main",
                        "node_id": "node-a",
                    },
                    generation_token=1,
                )
            self.assertEqual(received, [snapshot_a])
        finally:
            backend.shutdown()

    def test_retired_terminal_never_republishes_old_available_snapshot(self) -> None:
        backend = ExecutionBackendClient()
        process = backend._process_client  # noqa: SLF001
        selection = ExecutionBackendSelection()
        pinned = ExecutionGenerationSnapshot(
            selection,
            1,
            1,
            "a" * 64,
            True,
            "",
        )
        availability = []
        shell_events = []
        backend.subscribe_generation_events(
            lambda _event, generation: availability.append(generation.available)
        )
        backend.subscribe(shell_events.append)
        with backend._active_lock:  # noqa: SLF001
            backend._run_clients["run-retired"] = process  # noqa: SLF001
            backend._run_generation_snapshots["run-retired"] = pinned  # noqa: SLF001
            backend._run_client_generations["run-retired"] = 0  # noqa: SLF001
        try:
            backend._dispatch_client_event(  # noqa: SLF001
                process,
                {
                    "type": "execution_generation_changed",
                    "reason": "worker_terminated",
                },
                generation_token=0,
            )
            backend._dispatch_client_event(  # noqa: SLF001
                process,
                {
                    "type": "run_failed",
                    "run_id": "run-retired",
                    "workspace_id": "ws",
                },
                generation_token=0,
            )
            self.assertEqual(availability, [False, False])
            self.assertEqual(
                [event["type"] for event in shell_events],
                ["run_failed"],
            )
        finally:
            backend.shutdown()

    def test_cold_route_reservation_binds_generation_and_forwards_snapshot(
        self,
    ) -> None:
        backend = ExecutionBackendClient()
        registry = build_default_registry()
        selection = ExecutionBackendSelection()
        snapshots = []
        backend.subscribe_generation_events(
            lambda _event, generation: snapshots.append(generation)
        )
        try:
            backend.replace_registry(registry)
            self.assertFalse(backend.execution_generation_snapshot(selection).available)
            process = backend._process_client  # noqa: SLF001
            with (
                patch.object(
                    process,
                    "_ensure_process",
                    side_effect=process._install_physical_generation,  # noqa: SLF001
                ),
                patch.object(process, "_viewer_generation_is_live", return_value=True),
            ):
                reservation = backend.reserve_run(selection, "ws_main")
                self.assertTrue(reservation.generation_snapshot.available)
                self.assertEqual(
                    reservation.generation_snapshot.backend_generation,
                    reservation.generation_snapshot.runtime_generation,
                )
                self.assertEqual(
                    process._execution_environment_registry_fingerprint,  # noqa: SLF001
                    registry.contract_fingerprint(),
                )
                self.assertEqual(
                    len(process._execution_environment_digest),  # noqa: SLF001
                    64,
                )
                alternate_reason = replace(
                    selection,
                    reason="explanatory-text-only",
                )
                alternate_snapshot = backend.execution_generation_snapshot(
                    alternate_reason,
                    registry_contract_fingerprint=registry.contract_fingerprint(),
                )
                self.assertTrue(alternate_snapshot.available)
                self.assertEqual(
                    alternate_snapshot.environment_digest,
                    reservation.generation_snapshot.environment_digest,
                )
                self.assertTrue(
                    alternate_snapshot.compatible_with(reservation.generation_snapshot)
                )
                backend.release_run_reservation(reservation, "test")
                backend._dispatch_client_event(  # noqa: SLF001
                    process,
                    {
                        "type": "run_completed",
                        "run_id": "unregistered",
                        "workspace_id": "ws_main",
                    },
                    generation_token=reservation.generation_snapshot.backend_generation,
                )
            self.assertEqual(snapshots[-1], reservation.generation_snapshot)
        finally:
            backend.shutdown()

    def test_reserved_start_rejects_tampered_prepared_generation_and_environment(
        self,
    ) -> None:
        backend = ExecutionBackendClient()
        registry = build_default_registry()
        selection = ExecutionBackendSelection()
        backend.replace_registry(registry)
        process = backend._process_client  # noqa: SLF001

        def command_for(
            reservation: ExecutionRunReservation,
            *,
            runtime_generation: int,
            environment_digest: str,
            decision: PreparedNodeDecision,
            accepted: tuple[AcceptedOutputPayload, ...] = (),
        ) -> StartRunCommand:
            return StartRunCommand(
                run_id=reservation.run_id,
                workspace_id=reservation.workspace_id,
                execution_backend=reservation.selection,
                preparation_id="prepared-tamper-probe",
                solution_namespace_id="namespace",
                execution_affecting_workspace_revision=0,
                dispatch_runtime_generation=runtime_generation,
                runtime_snapshot_fingerprint="1" * 64,
                execution_plan_fingerprint="2" * 64,
                workflow_interface_revision=1,
                workflow_interface_digest="3" * 64,
                execution_environment_digest=environment_digest,
                node_decisions=(decision,),
                accepted_output_payloads=accepted,
            )

        try:
            with (
                patch.object(
                    process,
                    "_ensure_process",
                    side_effect=process._install_physical_generation,  # noqa: SLF001
                ),
                patch.object(process, "_viewer_generation_is_live", return_value=True),
            ):
                generation_reservation = backend.reserve_run(selection, "ws_main")
                stale_generation = (
                    generation_reservation.generation_snapshot.runtime_generation + 1
                )
                accepted = AcceptedOutputPayload(
                    node_id="node",
                    record_id="record",
                    solution_key="4" * 64,
                    settlement_status="completed",
                    result_digest="5" * 64,
                    residency=SolutionResidency.SESSION,
                    runtime_generation=stale_generation,
                    outputs={},
                )
                reused = PreparedNodeDecision(
                    node_id="node",
                    action=PreparedAction.REUSE,
                    reason_code="reusable_record_accepted",
                    solution_key="4" * 64,
                    dependency_solution_keys=(),
                    accepted_record_id="record",
                    accepted_payload_digest=accepted.commitment_digest(),
                )
                with self.assertRaisesRegex(ValueError, "generation does not match"):
                    backend.start_reserved_run(
                        generation_reservation,
                        command_for(
                            generation_reservation,
                            runtime_generation=stale_generation,
                            environment_digest=(
                                generation_reservation.generation_snapshot.environment_digest
                            ),
                            decision=reused,
                            accepted=(accepted,),
                        ),
                    )

                environment_reservation = backend.reserve_run(selection, "ws_main")
                tampered_environment = "f" * 64
                recomputed_key = canonical_digest(
                    {"execution_environment_digest": tampered_environment}
                )
                execute = PreparedNodeDecision(
                    node_id="node",
                    action=PreparedAction.EXECUTE,
                    reason_code="no_reusable_record",
                    solution_key=recomputed_key,
                    dependency_solution_keys=(),
                )
                with self.assertRaisesRegex(ValueError, "generation does not match"):
                    backend.start_reserved_run(
                        environment_reservation,
                        command_for(
                            environment_reservation,
                            runtime_generation=(
                                environment_reservation.generation_snapshot.runtime_generation
                            ),
                            environment_digest=tampered_environment,
                            decision=execute,
                        ),
                    )
                self.assertEqual(backend._active_clients, {})  # noqa: SLF001
                self.assertEqual(backend._run_clients, {})  # noqa: SLF001
        finally:
            backend.shutdown()

    def test_live_generation_without_environment_handshake_is_unavailable(self) -> None:
        backend = ExecutionBackendClient()
        process = backend._process_client  # noqa: SLF001
        try:
            process._catalog_generation_token = 1  # noqa: SLF001
            process._physical_generation_token = 1  # noqa: SLF001
            process._accepted_physical_generation_token = 1  # noqa: SLF001
            with patch.object(process, "_viewer_generation_is_live", return_value=True):
                snapshot = backend.execution_generation_snapshot(
                    ExecutionBackendSelection(),
                    registry_contract_fingerprint="a" * 64,
                )
            self.assertFalse(snapshot.available)
            self.assertEqual(snapshot.reason, "execution_environment_unavailable")
        finally:
            backend.shutdown()

    def test_trusted_solution_handle_requires_live_registry_entry_and_leases_it(
        self,
    ) -> None:
        backend = ExecutionBackendClient()
        trusted = backend._trusted_client  # noqa: SLF001
        registry = build_default_registry()
        trusted._worker_services.bind_data_types(registry.data_types)  # noqa: SLF001
        live = trusted._worker_services.register_handle(  # noqa: SLF001
            object(),
            data_type_id=VIEWER_SESSION_DATA_TYPE_ID,
            kind=COREX_VIEWER_SESSION_HANDLE_KIND,
            run_id="run-live",
        )
        snapshot = ExecutionGenerationSnapshot(
            ExecutionBackendSelection(
                backend_id=TRUSTED_IN_PROCESS_BACKEND,
                isolation="in_process",
                trusted_in_process=True,
            ),
            live.worker_generation,
            live.worker_generation,
            "a" * 64,
            True,
            "",
        )
        with backend._active_lock:  # noqa: SLF001
            backend._run_clients["run-live"] = trusted  # noqa: SLF001
            backend._run_generation_snapshots["run-live"] = snapshot  # noqa: SLF001
        try:
            fabricated = replace(live, handle_id="missing-handle")
            self.assertIsNone(
                backend.lease_solution_resource(
                    "run-live",
                    fabricated,
                    owner_scope="solution:missing",
                )
            )
            leased = backend.lease_solution_resource(
                "run-live",
                live,
                owner_scope="solution:live",
            )
            self.assertIsNotNone(leased)
            assert leased is not None
            backend.release_solution_resource(leased[1])
        finally:
            backend.shutdown()

    def test_idle_process_and_external_death_emit_generation_notification(self) -> None:
        process_client = ProcessExecutionClient()
        process_events = []
        process_client.subscribe(
            lambda event, generation: process_events.append((event, generation)),
            include_generation=True,
        )
        process = Mock()
        process.is_alive.return_value = False
        process_client._process = process  # noqa: SLF001
        process_client._catalog_generation_token = 1  # noqa: SLF001
        process_client._physical_generation_token = 1  # noqa: SLF001
        process_client._accepted_physical_generation_token = 1  # noqa: SLF001
        process_client._check_worker_health(process, 1)  # noqa: SLF001
        self.assertEqual(
            process_events[-1][0]["type"],
            "execution_generation_changed",
        )
        process_client._process = None  # noqa: SLF001
        process_client.shutdown()

        external_client = ExternalPythonExecutionClient()
        external_events = []
        external_client.subscribe(
            lambda event, generation: external_events.append((event, generation)),
            include_generation=True,
        )
        external = Mock()
        external.poll.return_value = 1
        external_client._process = external  # noqa: SLF001
        external_client._catalog_generation_token = 1  # noqa: SLF001
        external_client._physical_generation_token = 1  # noqa: SLF001
        external_client._accepted_physical_generation_token = 1  # noqa: SLF001
        external_client._check_worker_health()  # noqa: SLF001
        self.assertEqual(
            external_events[-1][0]["type"],
            "execution_generation_changed",
        )
        external_client._process = None  # noqa: SLF001
        external_client.shutdown()
