# Purpose: Trusted in-process thread, listener, reset, and explicit selection behavior.
# Map: subsystems/execution.md
from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import Mock, patch

from ea_node_editor.execution.backend_client import ExecutionBackendClient
from ea_node_editor.execution.backends import (
    TRUSTED_IN_PROCESS_BACKEND,
)
from ea_node_editor.execution.client_common import (
    _PendingViewerRequest,
)
from ea_node_editor.execution.protocol_codec import (
    event_to_dict,
)
from ea_node_editor.execution.run_messages import (
    ProtocolErrorEvent,
    RunCompletedEvent,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.trusted_client import TrustedInProcessExecutionClient
from ea_node_editor.execution.worker_runtime import (
    DEFAULT_RUNTIME_PREPARATION_CACHE,
)
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import (
    build_default_registry,
)
from tests.execution_client_fixtures import (
    ProcessClientTestHarness,
    _catalog_contract_fingerprint,
    _revision_catalog,
    _trusted_registry_agreement,
)


class TrustedClientTests(unittest.TestCase):
    def test_trusted_catalog_recycle_resets_services_and_runtime_cache(
        self,
    ) -> None:
        registry = build_default_registry()
        first_catalog = _revision_catalog("trusted-v1")
        second_catalog = _revision_catalog("trusted-v2")
        model = GraphModel()
        workspace = model.active_workspace
        runtime_snapshot = build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=registry,
        )
        services = WorkerServices()
        services.bind_data_types(first_catalog)
        client = TrustedInProcessExecutionClient(worker_services=services)
        client._data_types = first_catalog  # noqa: SLF001
        client._catalog_generation_fingerprint = (  # noqa: SLF001
            first_catalog.fingerprint()
        )
        client._registry_contract_generation_fingerprint = (  # noqa: SLF001
            _catalog_contract_fingerprint(first_catalog)
        )
        client._run_workflow_thread = (  # type: ignore[method-assign]  # noqa: SLF001
            lambda _command, _generation: None
        )
        initial_generation = services.worker_generation

        try:
            with patch.object(
                DEFAULT_RUNTIME_PREPARATION_CACHE,
                "clear",
                wraps=DEFAULT_RUNTIME_PREPARATION_CACHE.clear,
            ) as clear_cache:
                run_id = client.start_run(
                    "",
                    workspace.workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    data_types=second_catalog,
                    registry_contract_fingerprint=_catalog_contract_fingerprint(
                        second_catalog
                    ),
                )
                self.assertTrue(run_id)
                client._run_thread.join(timeout=2.0)  # noqa: SLF001

            clear_cache.assert_called_once_with()
            self.assertEqual(services.worker_generation, initial_generation + 1)
            self.assertIs(client._data_types, second_catalog)  # noqa: SLF001
            client._release_start_run(run_id)  # noqa: SLF001
        finally:
            client.shutdown()

    def test_trusted_reset_retires_viewers_and_allows_catalog_change(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        runtime_snapshot = build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=registry,
        )
        first_catalog = _revision_catalog("trusted-reset-v1")
        second_catalog = _revision_catalog("trusted-reset-v2")
        services = WorkerServices()
        services.bind_data_types(first_catalog)
        client = TrustedInProcessExecutionClient(worker_services=services)
        client._data_types = first_catalog  # noqa: SLF001
        client._catalog_generation_fingerprint = (  # noqa: SLF001
            first_catalog.fingerprint()
        )
        client._registry_contract_generation_fingerprint = (  # noqa: SLF001
            _catalog_contract_fingerprint(first_catalog)
        )
        client._catalog_generation_token = 1  # noqa: SLF001
        client._accepted_physical_generation_token = 1  # noqa: SLF001
        client._active_run_id = "run_failed"  # noqa: SLF001
        client._active_workspace_id = workspace.workspace_id  # noqa: SLF001
        client._run_generation_tokens["run_failed"] = 1  # noqa: SLF001
        session_key = (workspace.workspace_id, "session_live")
        client._viewer_session_ids.add(session_key)  # noqa: SLF001
        client._viewer_session_generations[session_key] = 1  # noqa: SLF001
        pending_request = _PendingViewerRequest(
            request_id="viewer_pending",
            command="open_viewer_session",
            workspace_id=workspace.workspace_id,
            node_id="node_viewer",
            session_id="session_pending",
            generation_token=1,
        )
        client._pending_viewer_requests[pending_request.request_id] = (  # noqa: SLF001
            pending_request
        )
        terminal_received = threading.Event()
        events: list[dict] = []

        def record_event(event: dict) -> None:
            events.append(event)
            if (
                event.get("type") == "run_failed"
                and event.get("run_id") == "run_failed"
            ):
                terminal_received.set()

        client.subscribe(record_event)
        failed_command = Mock(
            run_id="run_failed",
            workspace_id=workspace.workspace_id,
        )
        initial_worker_generation = services.worker_generation

        try:
            with patch(
                "ea_node_editor.execution.trusted_client.run_workflow",
                side_effect=RuntimeError("trusted failure"),
            ):
                client._run_workflow_thread(  # noqa: SLF001
                    failed_command,
                    1,
                )
            self.assertTrue(terminal_received.wait(timeout=1.0))
            self.assertNotIn(session_key, client._viewer_session_ids)  # noqa: SLF001
            self.assertNotIn(  # noqa: SLF001
                session_key,
                client._viewer_session_generations,
            )
            self.assertNotIn(  # noqa: SLF001
                session_key,
                client._viewer_session_node_ids,
            )
            self.assertNotIn(  # noqa: SLF001
                pending_request.request_id,
                client._pending_viewer_requests,
            )
            self.assertTrue(
                any(
                    event.get("type") == "viewer_session_failed"
                    and event.get("request_id") == pending_request.request_id
                    for event in events
                )
            )
            self.assertGreater(client._catalog_generation_token, 1)  # noqa: SLF001
            self.assertGreater(
                services.worker_generation,
                initial_worker_generation,
            )

            client._run_workflow_thread = (  # type: ignore[method-assign]  # noqa: SLF001
                lambda _command, _generation: None
            )
            successor_run_id = client.start_run(
                "",
                workspace.workspace_id,
                {"runtime_snapshot": runtime_snapshot},
                data_types=second_catalog,
                registry_contract_fingerprint=_catalog_contract_fingerprint(
                    second_catalog
                ),
            )
            self.assertTrue(successor_run_id)
            client._run_thread.join(timeout=1.0)  # noqa: SLF001
            client._release_start_run(successor_run_id)  # noqa: SLF001
        finally:
            client.shutdown()

    def test_trusted_listener_drops_retired_generation_events(
        self,
    ) -> None:
        client = TrustedInProcessExecutionClient()
        client._data_types = _revision_catalog("trusted-events")  # noqa: SLF001
        client._catalog_generation_token = 2  # noqa: SLF001
        client._accepted_physical_generation_token = 2  # noqa: SLF001
        client._active_run_id = "run_current"  # noqa: SLF001
        client._active_workspace_id = "ws_current"  # noqa: SLF001
        client._run_generation_tokens["run_current"] = 2  # noqa: SLF001
        events: list[dict] = []
        current_received = threading.Event()

        def record_event(event: dict) -> None:
            events.append(event)
            if (
                event.get("type") == "run_completed"
                and event.get("run_id") == "run_current"
            ):
                current_received.set()

        client.subscribe(record_event)

        try:
            client._event_queue.put(  # noqa: SLF001
                (
                    1,
                    event_to_dict(
                        ProtocolErrorEvent(
                            command="stale",
                            error="stale generation event",
                        )
                    ),
                )
            )
            client._event_queue.put(  # noqa: SLF001
                (
                    2,
                    event_to_dict(
                        RunCompletedEvent(
                            run_id="run_current",
                            workspace_id="ws_current",
                        )
                    ),
                )
            )

            self.assertTrue(current_received.wait(timeout=1.0))
            self.assertFalse(any(event.get("command") == "stale" for event in events))
        finally:
            client.shutdown()


class TrustedBackendSelectionTests(ProcessClientTestHarness):
    def test_execution_backend_client_runs_trusted_in_process_only_with_explicit_opt_in(
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
        workspace_id, runtime_snapshot = self._build_runtime_snapshot(
            with_sleep_script=False
        )
        try:
            rejected_run_id = backend_client.start_run(
                project_path="",
                workspace_id=workspace_id,
                trigger={"kind": "manual", "runtime_snapshot": runtime_snapshot},
                execution_backend={"requested_backend": TRUSTED_IN_PROCESS_BACKEND},
                **_trusted_registry_agreement(),
            )
            self.assertEqual(rejected_run_id, "")
            rejected = _wait_for_event(
                lambda event: (
                    event.get("type") == "protocol_error"
                    and "allow_trusted_in_process=True" in str(event.get("error", ""))
                ),
                timeout=3.0,
            )
            self.assertIsNotNone(rejected, events)

            run_id = backend_client.start_run(
                project_path="",
                workspace_id=workspace_id,
                trigger={"kind": "manual", "runtime_snapshot": runtime_snapshot},
                execution_backend={
                    "requested_backend": TRUSTED_IN_PROCESS_BACKEND,
                    "allow_trusted_in_process": True,
                },
                **_trusted_registry_agreement(),
            )
            self.assertTrue(run_id, events)

            completed = _wait_for_event(
                lambda event: (
                    event.get("type") == "run_completed"
                    and event.get("run_id") == run_id
                ),
                timeout=8.0,
            )
            self.assertIsNotNone(completed)
            selected = _wait_for_event(
                lambda event: (
                    event.get("type") == "log"
                    and event.get("run_id") == run_id
                    and TRUSTED_IN_PROCESS_BACKEND in str(event.get("message", ""))
                ),
                timeout=3.0,
            )
            self.assertIsNotNone(selected)
            self.assertIsNone(backend_client._process_client._process)  # noqa: SLF001
        finally:
            backend_client.shutdown()

    def test_execution_backend_client_rejects_trusted_python_script_timeout(
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
        workspace_id, _script_id, runtime_snapshot = (
            self._build_script_runtime_snapshot(
                "while True:\n    pass",
                timeout_sec=1.0,
            )
        )
        try:
            run_id = backend_client.start_run(
                project_path="",
                workspace_id=workspace_id,
                trigger={"kind": "manual", "runtime_snapshot": runtime_snapshot},
                execution_backend={
                    "requested_backend": TRUSTED_IN_PROCESS_BACKEND,
                    "allow_trusted_in_process": True,
                },
                **_trusted_registry_agreement(),
            )
            self.assertEqual(run_id, "")
            rejected = _wait_for_event(
                lambda event: (
                    event.get("type") == "protocol_error"
                    and "Python Script timeouts require process-isolated execution"
                    in str(event.get("error", ""))
                ),
                timeout=3.0,
            )
            self.assertIsNotNone(rejected, events)
        finally:
            backend_client.shutdown()
