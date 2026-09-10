# Purpose: Shared concrete execution-client agreement, admission, run-control, and viewer-request contracts.
# Map: subsystems/execution.md
from __future__ import annotations

import queue
import sys
import threading
import unittest
from unittest.mock import Mock, patch

from ea_node_editor.execution.backend_client import ExecutionBackendClient
from ea_node_editor.execution.backends import (
    EXTERNAL_SUBPROCESS_BACKEND,
    ExecutionBackendSelection,
)
from ea_node_editor.execution.client_common import (
    _ExecutionClientCommon,
)
from ea_node_editor.execution.external_python_client import (
    ExternalPythonExecutionClient,
)
from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.protocol_codec import (
    event_to_dict,
)
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
)
from ea_node_editor.execution.run_messages import (
    CommitRunPreflightCommand,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.trusted_client import TrustedInProcessExecutionClient
from ea_node_editor.execution.viewer_messages import (
    ViewerSessionOpenedEvent,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import (
    build_builtin_registry,
    build_default_registry,
)
from ea_node_editor.runtime_contracts import (
    DataTypeCatalogError,
)
from tests.execution_client_fixtures import (
    _catalog_contract_fingerprint,
    _revision_catalog,
)


class ClientCommonContractTests(unittest.TestCase):
    def test_scoped_viewer_request_invalidation_captures_epochs_and_counts_once(
        self,
    ) -> None:
        client = ProcessExecutionClient()
        commands = []
        client._ensure_process = lambda: None  # type: ignore[method-assign]  # noqa: SLF001
        client._try_post_command = (  # type: ignore[method-assign]  # noqa: SLF001
            lambda command: (commands.append(command) is None, "")
        )
        try:
            request_a = client.open_viewer_session(
                "ws_main", "viewer_a", session_id="session_a"
            )
            request_b = client.open_viewer_session(
                "ws_main", "viewer_b", session_id="session_b"
            )
            self.assertEqual(
                client.invalidate_viewer_requests("ws_main", ("viewer_a", "viewer_a")),
                1,
            )
            self.assertNotIn(request_a, client._pending_viewer_requests)  # noqa: SLF001
            self.assertIn(request_b, client._pending_viewer_requests)  # noqa: SLF001
            self.assertEqual(
                client._record_viewer_response_state(  # noqa: SLF001
                    event_to_dict(
                        ViewerSessionOpenedEvent(
                            request_id=request_a,
                            workspace_id="ws_main",
                            node_id="viewer_a",
                            session_id="session_a",
                        )
                    ),
                    default_generation_token=0,
                ),
                -1,
            )
            self.assertNotIn(
                ("ws_main", "session_a"),
                client._viewer_session_ids,  # noqa: SLF001
            )
            client.close_viewer_session("ws_main", "viewer_a", "session_a")
            self.assertEqual(commands[-1].workspace_invalidation_epoch, 0)
            self.assertEqual(commands[-1].node_invalidation_epoch, 1)
            self.assertEqual(client.invalidate_viewer_requests("ws_main", ()), 0)
            with self.assertRaises(TypeError):
                client.invalidate_viewer_requests("ws_main", "viewer_a")
            self.assertEqual(client.invalidate_viewer_requests("ws_main", None), 2)
            self.assertEqual(client._workspace_viewer_epochs["ws_main"], 1)  # noqa: SLF001
            self.assertNotIn(("ws_main", "viewer_a"), client._node_viewer_epochs)  # noqa: SLF001
        finally:
            client.shutdown()

    def test_concrete_registry_publication_is_noop_before_live_viewer_guard(
        self,
    ) -> None:
        registry = build_default_registry()
        fingerprint = registry.contract_fingerprint()
        for client_type in (
            ProcessExecutionClient,
            TrustedInProcessExecutionClient,
            ExternalPythonExecutionClient,
        ):
            client = client_type()
            session_key = ("ws_main", "session_live")
            client._registry_contract_generation_fingerprint = fingerprint  # noqa: SLF001
            client._viewer_session_ids.add(session_key)  # noqa: SLF001
            client._viewer_session_generations[session_key] = 0  # noqa: SLF001
            client._viewer_session_node_ids[session_key] = "viewer_live"  # noqa: SLF001
            before_generation = client._catalog_generation_token  # noqa: SLF001
            try:
                self.assertFalse(client.replace_registry(registry))
                self.assertEqual(
                    client._catalog_generation_token,  # noqa: SLF001
                    before_generation,
                )
                self.assertIn(session_key, client._viewer_session_ids)  # noqa: SLF001
                different = build_builtin_registry()
                with self.assertRaises(DataTypeCatalogError):
                    client.replace_registry(different)
                self.assertIn(session_key, client._viewer_session_ids)  # noqa: SLF001
            finally:
                client.shutdown()

    def test_preflight_delivery_helpers_do_not_reacquire_state_or_viewer_locks(
        self,
    ) -> None:
        class ExplodingLock:
            def __enter__(self):  # noqa: ANN204
                raise AssertionError("delivery reacquired a participant lock")

            def __exit__(self, *_args):  # noqa: ANN002, ANN204
                return None

            def acquire(self, *_args, **_kwargs):  # noqa: ANN002, ANN202
                raise AssertionError("delivery reacquired a participant lock")

            def release(self) -> None:
                raise AssertionError("delivery released an unowned participant lock")

        command = CommitRunPreflightCommand(
            run_id="run_delivery_lock_test",
            viewer_invalidation_reservation_id="viewer_inv_delivery_lock_test",
            viewer_epoch_snapshot_digest="a" * 64,
        )
        clients = (
            ProcessExecutionClient(),
            TrustedInProcessExecutionClient(),
            ExternalPythonExecutionClient(),
        )
        try:
            for client in clients:
                with self.subTest(client=type(client).__name__):
                    payload = client._encode_run_preflight_command(command)  # noqa: SLF001
                    if isinstance(client, ExternalPythonExecutionClient):
                        transport = Mock()
                        transport.poll.return_value = None
                        transport.stdin = Mock()
                    else:
                        transport = queue.Queue()
                    state_lock = client._state_lock  # noqa: SLF001
                    viewer_lock = client._viewer_request_lock  # noqa: SLF001
                    try:
                        client._state_lock = ExplodingLock()  # type: ignore[assignment]  # noqa: SLF001
                        client._viewer_request_lock = ExplodingLock()  # type: ignore[assignment]  # noqa: SLF001
                        self.assertEqual(
                            client._deliver_encoded_run_preflight_command(  # noqa: SLF001
                                payload,
                                transport,
                            ),
                            (True, ""),
                        )
                    finally:
                        client._state_lock = state_lock  # type: ignore[assignment]  # noqa: SLF001
                        client._viewer_request_lock = viewer_lock  # type: ignore[assignment]  # noqa: SLF001
        finally:
            for client in clients:
                client.shutdown()

    def test_common_preflight_orchestration_preserves_each_backend_transport(
        self,
    ) -> None:
        command = CommitRunPreflightCommand(
            run_id="run_common_preflight",
            viewer_invalidation_reservation_id="viewer_inv_common_preflight",
            viewer_epoch_snapshot_digest="a" * 64,
        )
        clients = (
            ProcessExecutionClient(),
            ExternalPythonExecutionClient(),
            TrustedInProcessExecutionClient(),
        )
        try:
            for client in clients:
                with self.subTest(client=type(client).__name__):
                    order: list[str] = []
                    if isinstance(client, ExternalPythonExecutionClient):
                        transport = Mock()
                        transport.poll.return_value = None
                        transport.stdin = Mock()
                        transport_patch = patch.object(client, "_process", transport)
                    else:
                        transport = queue.Queue()
                        transport_patch = patch.object(
                            client, "_command_queue", transport
                        )
                    encode = client._encode_run_preflight_command  # noqa: SLF001
                    pin = client._pin_run_preflight_transport_locked  # noqa: SLF001
                    deliver = client._deliver_encoded_run_preflight_command  # noqa: SLF001

                    def encode_once(value):  # noqa: ANN001, ANN202
                        order.append("encode")
                        return encode(value)

                    def pin_once():  # noqa: ANN202
                        order.append("pin")
                        return pin()

                    def deliver_once(payload, pinned):  # noqa: ANN001, ANN202
                        order.append("deliver")
                        return deliver(payload, pinned)

                    with (
                        transport_patch,
                        patch.object(
                            client,
                            "_encode_run_preflight_command",
                            side_effect=encode_once,
                        ),
                        patch.object(
                            client,
                            "_pin_run_preflight_transport_locked",
                            side_effect=pin_once,
                        ),
                        patch.object(
                            client,
                            "_deliver_encoded_run_preflight_command",
                            side_effect=deliver_once,
                        ) as deliver_mock,
                    ):
                        self.assertEqual(
                            client._deliver_run_preflight_command(command),  # noqa: SLF001
                            (True, ""),
                        )

                    self.assertEqual(order, ["encode", "pin", "deliver"])
                    payload, pinned = deliver_mock.call_args.args
                    self.assertIs(pinned, transport)
                    if isinstance(client, ExternalPythonExecutionClient):
                        transport.stdin.write.assert_called_once_with(payload)
                        transport.stdin.flush.assert_called_once_with()
                    else:
                        self.assertEqual(transport.get_nowait(), payload)
        finally:
            for client in clients:
                client.shutdown()

    def test_common_methods_and_commands_are_shared_across_backends(self) -> None:
        common_methods = (
            "subscribe",
            "_dispatch_event",
            "_clear_active_node_state_locked",
            "_clear_active_run_state_locked",
            "_record_execution_event_state",
            "_emit_protocol_error",
            "_deliver_run_preflight_command",
            "_next_viewer_request_id",
            "_track_viewer_request",
            "_complete_viewer_request",
            "_dispatch_viewer_request_failure",
            "_viewer_protocol_error_failure",
            "pause_run",
            "resume_run",
            "stop_run",
            "open_viewer_session",
            "update_viewer_session",
            "close_viewer_session",
            "materialize_viewer_data",
            "query_viewer_session",
        )
        for client_type in (
            ProcessExecutionClient,
            ExternalPythonExecutionClient,
            TrustedInProcessExecutionClient,
        ):
            with self.subTest(client_type=client_type.__name__):
                for method_name in common_methods:
                    self.assertNotIn(method_name, client_type.__dict__)
                    self.assertIs(
                        getattr(client_type, method_name),
                        getattr(_ExecutionClientCommon, method_name),
                    )

                client = object.__new__(client_type)
                client._callbacks = []  # noqa: SLF001
                client._start_lock = threading.RLock()  # noqa: SLF001
                client._state_lock = threading.Lock()  # noqa: SLF001
                client._active_run_id = ""  # noqa: SLF001
                client._active_workspace_id = ""  # noqa: SLF001
                client._active_node_id = ""  # noqa: SLF001
                client._active_node_deadline = 0.0  # noqa: SLF001
                client._active_node_timeout_sec = 0.0  # noqa: SLF001
                client._script_timeout_by_node_id = {}  # noqa: SLF001
                client._viewer_request_lock = threading.Lock()  # noqa: SLF001
                client._pending_viewer_requests = {}  # noqa: SLF001
                posted_commands = []
                viewer_commands = []

                def post_command(command):  # noqa: ANN001
                    posted_commands.append(command)
                    return True

                def send_viewer_command(command, *, require_session_id=False):  # noqa: ANN001
                    viewer_commands.append((command, require_session_id))
                    return command.request_id

                client._post_command = post_command  # type: ignore[method-assign]  # noqa: SLF001
                client._send_viewer_command = send_viewer_command  # type: ignore[method-assign]  # noqa: SLF001

                client.pause_run("run_demo")
                client.resume_run("run_demo")
                client.stop_run("run_demo")
                self.assertEqual(
                    [command.type for command in posted_commands],
                    ["pause_run", "resume_run", "stop_run"],
                )
                self.assertEqual(
                    [command.run_id for command in posted_commands], ["run_demo"] * 3
                )

                request_ids = (
                    client.open_viewer_session(
                        "ws", "node", session_id="session", backend_id="backend"
                    ),
                    client.update_viewer_session(
                        "ws", "node", "session", backend_id="backend"
                    ),
                    client.close_viewer_session("ws", "node", "session"),
                    client.materialize_viewer_data(
                        "ws", "node", "session", backend_id="backend"
                    ),
                    client.query_viewer_session(
                        "ws",
                        "node",
                        "session",
                        backend_id="backend",
                        query_type="camera",
                    ),
                )
                self.assertEqual(
                    request_ids,
                    tuple(command.request_id for command, _ in viewer_commands),
                )
                self.assertTrue(
                    all(request_id.startswith("viewer_") for request_id in request_ids)
                )
                self.assertEqual(
                    [
                        (command.type, requires_session)
                        for command, requires_session in viewer_commands
                    ],
                    [
                        ("open_viewer_session", False),
                        ("update_viewer_session", True),
                        ("close_viewer_session", True),
                        ("materialize_viewer_data", True),
                        ("query_viewer_session", True),
                    ],
                )
                self.assertTrue(
                    all(command.workspace_id == "ws" for command, _ in viewer_commands)
                )
                self.assertTrue(
                    all(command.node_id == "node" for command, _ in viewer_commands)
                )
                self.assertEqual(viewer_commands[-1][0].query_type, "camera")

    def test_each_public_start_requires_a_new_explicit_catalog(self) -> None:
        registry = build_default_registry()
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
        clients = (
            (
                ProcessExecutionClient(),
                {},
            ),
            (
                ExternalPythonExecutionClient(),
                {
                    "execution_backend": ExecutionBackendSelection(
                        backend_id=EXTERNAL_SUBPROCESS_BACKEND,
                        isolation="external_subprocess",
                        external_subprocess=True,
                        python_executable=sys.executable,
                    )
                },
            ),
            (
                TrustedInProcessExecutionClient(),
                {},
            ),
        )
        try:
            for client, extra_kwargs in clients:
                with self.subTest(client=type(client).__name__):
                    client._data_types = registry.data_types  # noqa: SLF001
                    events: list[dict] = []
                    client.subscribe(lambda event, target=events: target.append(event))
                    run_id = client.start_run(
                        "",
                        workspace.workspace_id,
                        {"runtime_snapshot": runtime_snapshot},
                        data_types=None,
                        **extra_kwargs,
                    )
                    self.assertEqual(run_id, "")
                    self.assertTrue(
                        any(
                            "authoritative data-type catalog"
                            in str(event.get("error", ""))
                            for event in events
                        )
                    )
        finally:
            for client, _extra_kwargs in clients:
                client.shutdown()

        backend = ExecutionBackendClient()
        try:
            backend._process_client._data_types = registry.data_types  # noqa: SLF001
            backend_events: list[dict] = []
            backend.subscribe(backend_events.append)
            self.assertEqual(
                backend.start_run(
                    "",
                    workspace.workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    data_types=None,
                ),
                "",
            )
            self.assertTrue(
                any(
                    "authoritative data-type catalog" in str(event.get("error", ""))
                    for event in backend_events
                )
            )
        finally:
            backend.shutdown()

    def test_second_start_with_different_catalog_cannot_rebind_active_client(
        self,
    ) -> None:
        registry = build_default_registry()
        active_catalog = registry.data_types
        competing_catalog = _revision_catalog("competing-v2")
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
        client = ProcessExecutionClient()
        events: list[dict] = []
        commands = []
        client.subscribe(events.append)

        try:
            with (
                patch.object(client, "_ensure_process"),
                patch.object(
                    client,
                    "_post_command",
                    side_effect=lambda command: commands.append(command) or True,
                ),
            ):
                active_run_id = client.start_run(
                    "",
                    workspace.workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    data_types=active_catalog,
                    registry_contract_fingerprint=_catalog_contract_fingerprint(
                        active_catalog
                    ),
                )
                self.assertTrue(active_run_id)
                self.assertEqual(
                    client.start_run(
                        "",
                        workspace.workspace_id,
                        {"runtime_snapshot": runtime_snapshot},
                        data_types=competing_catalog,
                        registry_contract_fingerprint=_catalog_contract_fingerprint(
                            competing_catalog
                        ),
                    ),
                    "",
                )

            self.assertIs(client._data_types, active_catalog)  # noqa: SLF001
            self.assertEqual(len(commands), 1)
            expected_fingerprint, expected_revisions = catalog_agreement(active_catalog)
            self.assertEqual(
                commands[0].catalog_fingerprint,
                expected_fingerprint,
            )
            self.assertEqual(commands[0].catalog_revisions, expected_revisions)
            self.assertTrue(
                any(
                    "already has an active run" in str(event.get("error", ""))
                    for event in events
                )
            )
        finally:
            if "active_run_id" in locals():
                client._release_start_run(active_run_id)  # noqa: SLF001
            client.shutdown()

    def test_stale_generation_run_controls_are_not_dispatched(
        self,
    ) -> None:
        backend = ExecutionBackendClient()
        client = backend._process_client  # noqa: SLF001
        client._catalog_generation_token = 2  # noqa: SLF001
        backend._active_clients["run_stale"] = client  # noqa: SLF001
        backend._run_clients["run_stale"] = client  # noqa: SLF001
        backend._run_client_generations["run_stale"] = 1  # noqa: SLF001
        backend._run_workspace_ids["run_stale"] = "ws_stale"  # noqa: SLF001

        try:
            with (
                patch.object(client, "pause_run") as pause,
                patch.object(client, "resume_run") as resume,
                patch.object(client, "stop_run") as stop,
            ):
                backend.pause_run("run_stale")
                backend.resume_run("run_stale")
                backend.stop_run("run_stale")
            pause.assert_not_called()
            resume.assert_not_called()
            stop.assert_not_called()
            self.assertNotIn("run_stale", backend._active_clients)  # noqa: SLF001
            self.assertNotIn("run_stale", backend._run_clients)  # noqa: SLF001
        finally:
            backend.shutdown()
