# Purpose: Multiprocessing execution-client transport, listener, timeout, death, and recovery behavior.
# Map: subsystems/execution.md
from __future__ import annotations

import queue
import sys
import threading
import unittest
from unittest.mock import Mock

from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.common.scene_protocol import (
    COREX_SCENE_HANDLE_KIND,
    ENGINEERING_VIEWER_BACKEND_ID,
)
from ea_node_editor.execution.protocol_codec import (
    event_to_dict,
)
from ea_node_editor.execution.run_messages import (
    NodeSettledEvent,
    NodeStartedEvent,
    ProtocolErrorEvent,
    RunCompletedEvent,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.viewer_messages import (
    ViewerSessionOpenedEvent,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import (
    build_default_registry,
)
from ea_node_editor.runtime_contracts import (
    ARRAY_DATA_REF_TYPE_ID,
    PATH_DATA_TYPE_ID,
    TABULAR_DATA_REF_TYPE_ID,
    ArrayDataRef,
    DataTree,
    ENGINEERING_SCENE_DATA_TYPE_ID,
    ImageValue,
    TabularDataRef,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.runtime_contracts.value_codec import deserialize_runtime_value
from ea_node_editor.runtime_contracts.value_refs import (
    RuntimeArtifactRef,
    RuntimeHandleRef,
)
from tests.execution_client_fixtures import (
    ProcessClientTestHarness,
    _revision_catalog,
)


class ProcessClientContractTests(unittest.TestCase):
    def test_fresh_physical_generation_skips_retirement_until_run_dispatch(self) -> None:
        client = ProcessExecutionClient()
        process = Mock(pid=123)
        process.is_alive.return_value = True
        retire = Mock(return_value=3)
        try:
            client._process = process  # noqa: SLF001
            client._retire_workspace_via_transport = retire  # type: ignore[method-assign]  # noqa: SLF001
            self.assertEqual(client.retire_workspace("workspace"), 0)
            retire.assert_not_called()
            client._physical_generation_run_dispatched = True  # noqa: SLF001
            self.assertEqual(client.retire_workspace("workspace"), 3)
            retire.assert_called_once_with("workspace")
        finally:
            client._process = None  # noqa: SLF001
            client.shutdown()

    def test_process_viewer_command_captures_epoch_after_worker_ensure(self) -> None:
        client = ProcessExecutionClient()
        commands = []

        def ensure_process() -> None:
            with client._viewer_request_lock:  # noqa: SLF001
                client._workspace_viewer_epochs["ws_main"] = 1  # noqa: SLF001

        client._ensure_process = ensure_process  # type: ignore[method-assign]  # noqa: SLF001
        client._try_post_command = (  # type: ignore[method-assign]  # noqa: SLF001
            lambda command: (commands.append(command) is None, "")
        )
        try:
            request_id = client.open_viewer_session(
                "ws_main", "viewer_a", session_id="session_a"
            )
            self.assertTrue(request_id)
            self.assertEqual(commands[-1].workspace_invalidation_epoch, 1)
            self.assertEqual(
                client._pending_viewer_requests[  # noqa: SLF001
                    request_id
                ].workspace_invalidation_epoch,
                1,
            )
        finally:
            client.shutdown()

    def test_process_respawn_advances_generation_and_replaces_queues(
        self,
    ) -> None:
        class FakeProcess:
            def __init__(self) -> None:
                self.alive = False

            def start(self) -> None:
                self.alive = True

            def is_alive(self) -> bool:
                return self.alive

            def join(self, timeout=None) -> None:  # noqa: ANN001, ARG002
                return None

            def terminate(self) -> None:
                self.alive = False

            def kill(self) -> None:
                self.alive = False

        class FakeContext:
            def __init__(self) -> None:
                self.queues: list[queue.Queue] = []
                self.processes: list[FakeProcess] = []

            def Queue(self):  # noqa: N802, ANN201
                created_queue = queue.Queue()
                self.queues.append(created_queue)
                return created_queue

            def Process(self, **_kwargs):  # noqa: N802, ANN201
                created_process = FakeProcess()
                self.processes.append(created_process)
                return created_process

        client = ProcessExecutionClient()
        fake_context = FakeContext()
        client._ctx = fake_context  # noqa: SLF001
        client._catalog_generation_token = 1  # noqa: SLF001
        events: list[dict] = []
        client.subscribe(events.append)

        try:
            client._ensure_process()  # noqa: SLF001
            first_process = client._process  # noqa: SLF001
            first_command_queue = client._command_queue  # noqa: SLF001
            first_event_queue = client._event_queue  # noqa: SLF001
            first_listener = client._listener_thread  # noqa: SLF001
            client._active_run_id = "run_first"  # noqa: SLF001
            client._active_workspace_id = "ws_first"  # noqa: SLF001
            client._run_generation_tokens["run_first"] = 1  # noqa: SLF001
            client._physical_generation_run_dispatched = True  # noqa: SLF001
            first_process.alive = False

            request_id = client.open_viewer_session(
                "ws_viewer",
                "node_viewer",
            )

            self.assertEqual(client._catalog_generation_token, 2)  # noqa: SLF001
            self.assertEqual(client._physical_generation_token, 2)  # noqa: SLF001
            self.assertFalse(client._physical_generation_run_dispatched)  # noqa: SLF001
            self.assertEqual(client._active_run_id, "")  # noqa: SLF001
            self.assertNotIn("run_first", client._run_generation_tokens)  # noqa: SLF001
            self.assertIsNot(client._process, first_process)  # noqa: SLF001
            self.assertIsNot(client._command_queue, first_command_queue)  # noqa: SLF001
            self.assertIsNot(client._event_queue, first_event_queue)  # noqa: SLF001
            self.assertFalse(first_listener.is_alive())
            self.assertTrue(
                any(
                    event.get("type") == "run_failed"
                    and event.get("run_id") == "run_first"
                    for event in events
                )
            )
            self.assertTrue(
                any(
                    event.get("type") == "run_state"
                    and event.get("run_id") == "run_first"
                    and event.get("reason") == "worker_terminated"
                    for event in events
                )
            )
            self.assertEqual(  # noqa: SLF001
                client._pending_viewer_requests[request_id].generation_token,
                2,
            )
            self.assertEqual(  # noqa: SLF001
                client._command_queue.get_nowait()["request_id"],
                request_id,
            )
        finally:
            client.shutdown()

    def test_first_catalog_pin_reuses_viewer_started_process_generation(
        self,
    ) -> None:
        client = ProcessExecutionClient()
        process = Mock()
        process.is_alive.return_value = True
        client._process = process  # noqa: SLF001
        client._catalog_generation_token = 1  # noqa: SLF001
        client._physical_generation_token = 1  # noqa: SLF001
        client._accepted_physical_generation_token = 1  # noqa: SLF001
        session_key = ("ws_viewer", "session_viewer")
        client._viewer_session_ids.add(session_key)  # noqa: SLF001
        client._viewer_session_generations[session_key] = 1  # noqa: SLF001
        client._viewer_session_node_ids[session_key] = "node_viewer"  # noqa: SLF001

        try:
            self.assertTrue(
                client._prepare_start_run(  # noqa: SLF001
                    "run_first",
                    "ws_viewer",
                    _revision_catalog("first-pin"),
                )
            )
            self.assertEqual(client._catalog_generation_token, 1)  # noqa: SLF001
            self.assertEqual(  # noqa: SLF001
                client._run_generation_tokens["run_first"],
                1,
            )
            self.assertEqual(  # noqa: SLF001
                client._viewer_session_generations[session_key],
                1,
            )
            self.assertTrue(  # noqa: SLF001
                client._source_generation_is_current(1)
            )
        finally:
            client._process = None  # noqa: SLF001
            client.shutdown()

    def test_retiring_process_generation_cannot_mutate_viewer_state(
        self,
    ) -> None:
        client = ProcessExecutionClient()
        client._data_types = _revision_catalog("retiring-source")  # noqa: SLF001
        client._catalog_generation_token = 1  # noqa: SLF001
        client._physical_generation_token = 1  # noqa: SLF001
        client._accepted_physical_generation_token = 1  # noqa: SLF001
        retiring_events = queue.Queue()
        retiring_events.put(
            event_to_dict(
                ViewerSessionOpenedEvent(
                    request_id="viewer_retired",
                    workspace_id="ws_retired",
                    session_id="session_retired",
                ),
                catalog=client._data_types,  # noqa: SLF001
            )
        )
        retiring_events.put({"type": "__listener_shutdown__"})

        try:
            client._invalidate_physical_generation()  # noqa: SLF001
            client._event_listener(retiring_events, None, 1)  # noqa: SLF001
            self.assertNotIn(  # noqa: SLF001
                ("ws_retired", "session_retired"),
                client._viewer_session_ids,
            )
        finally:
            client.shutdown()

    def test_dead_process_health_cannot_clear_a_pending_successor_start(
        self,
    ) -> None:
        client = ProcessExecutionClient()
        process = Mock()
        process.is_alive.return_value = False
        client._process = process  # noqa: SLF001
        client._catalog_generation_token = 1  # noqa: SLF001
        client._physical_generation_token = 1  # noqa: SLF001
        client._accepted_physical_generation_token = 1  # noqa: SLF001
        client._active_run_id = "run_successor"  # noqa: SLF001
        client._start_run_pending_id = "run_successor"  # noqa: SLF001

        try:
            client._check_worker_health(process, 1)  # noqa: SLF001
            self.assertEqual(client._active_run_id, "run_successor")  # noqa: SLF001
            process.join.assert_not_called()
        finally:
            client._process = None  # noqa: SLF001
            client.shutdown()

    def test_process_timeout_revalidates_before_terminating_successor(
        self,
    ) -> None:
        client = ProcessExecutionClient()
        process = Mock()
        process.is_alive.return_value = True
        client._process = process  # noqa: SLF001
        client._catalog_generation_token = 1  # noqa: SLF001
        client._physical_generation_token = 1  # noqa: SLF001
        client._accepted_physical_generation_token = 1  # noqa: SLF001
        client._active_run_id = "run_old"  # noqa: SLF001
        client._active_workspace_id = "ws_old"  # noqa: SLF001
        client._active_node_id = "node_old"  # noqa: SLF001
        transition_started = threading.Event()

        def terminate_old_run() -> None:
            transition_started.set()
            client._terminate_timed_out_worker(  # noqa: SLF001
                process,
                run_id="run_old",
                workspace_id="ws_old",
                node_id="node_old",
                timeout_sec=1.0,
                generation_token=1,
            )

        try:
            with client._start_lock:  # noqa: SLF001
                monitor = threading.Thread(target=terminate_old_run)
                monitor.start()
                self.assertTrue(transition_started.wait(timeout=1.0))
                monitor.join(timeout=0.1)
                self.assertTrue(monitor.is_alive())
                with client._state_lock:  # noqa: SLF001
                    client._active_run_id = "run_successor"  # noqa: SLF001
                    client._active_workspace_id = "ws_successor"  # noqa: SLF001
                    client._start_run_pending_id = "run_successor"  # noqa: SLF001
                    client._active_node_id = ""  # noqa: SLF001
            monitor.join(timeout=1.0)
            self.assertFalse(monitor.is_alive())
            process.terminate.assert_not_called()
            self.assertEqual(client._active_run_id, "run_successor")  # noqa: SLF001
            self.assertEqual(  # noqa: SLF001
                client._accepted_physical_generation_token,
                1,
            )
        finally:
            client._process = None  # noqa: SLF001
            client.shutdown()


class ProcessClientTests(ProcessClientTestHarness):
    def test_current_trigger_capture_roundtrips_without_running_upstream(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        source = model.add_node(
            workspace.workspace_id,
            "core.constant",
            "Source",
            0,
            0,
            properties={"value": "upstream"},
        )
        trigger = model.add_node(
            workspace.workspace_id,
            "core.trigger",
            "Trigger",
            100,
            0,
        )
        model.add_edge(
            workspace.workspace_id, source.node_id, "value", trigger.node_id, "input"
        )
        runtime_snapshot = build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=build_default_registry(),
        )
        captured = SettledPortResult(
            status="value",
            value=DataTree.from_item("captured"),
        )

        run_id = self.client.start_run(
            project_path="",
            workspace_id=workspace.workspace_id,
            trigger={"kind": "trigger", "runtime_snapshot": runtime_snapshot},
            target_node_ids=(trigger.node_id,),
            trigger_captures={trigger.node_id: captured},
            clicked_trigger_node_id=trigger.node_id,
            data_types=self.data_types,
            plugin_bundles=self.registry.plugin_bundle_refs(),
            plugin_fingerprint=self.registry.plugin_fingerprint(),
            registry_contract_fingerprint=self.registry.contract_fingerprint(),
            addon_runtime_config=self.registry.addon_runtime_config(),
        )
        published = self._wait_for_event(
            lambda event: (
                event.get("type") == "trigger_published"
                and event.get("run_id") == run_id
            ),
            timeout=30.0,
        )
        completed = self._wait_for_event(
            lambda event: (
                event.get("type") == "run_completed" and event.get("run_id") == run_id
            ),
            timeout=12.0,
        )

        self.assertIsNotNone(published)
        self.assertIsNotNone(completed)
        if published is None:
            self.fail("trigger publication was not received")
        self.assertEqual(
            deserialize_runtime_value(published["result"]["value"]),
            DataTree.from_item("captured"),
        )
        with self._events_lock:
            self.assertFalse(
                any(
                    event.get("type") == "node_started"
                    and event.get("run_id") == run_id
                    and event.get("node_id") == source.node_id
                    for event in self._events
                )
            )

    def test_signal_plot_image_value_survives_real_process_queue_transport(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        source = model.add_node(
            workspace.workspace_id,
            "data.number_slider",
            "Value",
            0,
            0,
            properties={"value": 5.0},
        )
        signal = model.add_node(
            workspace.workspace_id,
            "plot.signal",
            "Signal Plot",
            220,
            0,
            properties={"marker_shapes": [0]},
        )
        model.add_edge(
            workspace.workspace_id, source.node_id, "value", signal.node_id, "values"
        )
        runtime_snapshot = build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=registry,
        )
        run_id = self.client.start_run(
            project_path="",
            workspace_id=workspace.workspace_id,
            trigger={"kind": "manual", "runtime_snapshot": runtime_snapshot},
            target_node_ids=(signal.node_id,),
            data_types=registry.data_types,
            plugin_bundles=registry.plugin_bundle_refs(),
            plugin_fingerprint=registry.plugin_fingerprint(),
            registry_contract_fingerprint=registry.contract_fingerprint(),
            addon_runtime_config=registry.addon_runtime_config(),
        )
        settled = self._wait_for_event(
            lambda event: (
                event.get("type") == "node_settled"
                and event.get("run_id") == run_id
                and event.get("node_id") == signal.node_id
            ),
            timeout=30.0,
        )
        completed = self._wait_for_event(
            lambda event: (
                event.get("type") == "run_completed" and event.get("run_id") == run_id
            ),
            timeout=12.0,
        )
        self.assertIsNotNone(settled)
        self.assertIsNotNone(completed)
        if settled is None:
            self.fail("Signal Plot node_settled event was not received")
        image_tree = deserialize_runtime_value(
            settled["outputs"]["image"]["value"],
            catalog=registry.data_types,
        )
        image = image_tree.branches[0][1][0]
        self.assertIs(type(image), ImageValue)
        self.assertEqual((image.width, image.height), (600, 400))

    def test_invalid_worker_payload_emits_protocol_error(self) -> None:
        self.client._event_queue.put("not-a-dict")  # noqa: SLF001

        event = self._wait_for_event(
            lambda payload: (
                payload.get("type") == "protocol_error"
                and "non-dictionary event" in str(payload.get("error", ""))
            ),
            timeout=3.0,
        )

        self.assertIsNotNone(event)

    def test_client_listener_preserves_structured_artifact_ref_event_payloads(
        self,
    ) -> None:
        self.client._event_queue.put(
            event_to_dict(
                NodeSettledEvent(
                    run_id="run_artifact",
                    workspace_id="ws_main",
                    node_id="node_process",
                    outputs={
                        "stdout": SettledPortResult(
                            status="value",
                            value=DataTree.from_item(
                                RuntimeArtifactRef.staged(
                                    "stored_stdout",
                                    data_type_id=PATH_DATA_TYPE_ID,
                                    schema_version=1,
                                    format="txt",
                                    size_bytes=0,
                                    sha256="0" * 64,
                                    provenance="corex.test.fixture",
                                )
                            ),
                        ),
                        "preview": SettledPortResult(
                            status="value",
                            value=DataTree.from_item("ok"),
                        ),
                    },
                ),
                catalog=self.client._data_types,  # noqa: SLF001
            )
        )  # noqa: SLF001

        event = self._wait_for_event(
            lambda payload: (
                payload.get("type") == "node_settled"
                and payload.get("run_id") == "run_artifact"
            ),
            timeout=3.0,
        )

        self.assertIsNotNone(event)
        if event is None:
            self.fail("node_settled event was not received")
        stdout_tree = deserialize_runtime_value(
            event["outputs"]["stdout"]["value"],
            catalog=self.client._data_types,  # noqa: SLF001
        )
        preview_tree = deserialize_runtime_value(event["outputs"]["preview"]["value"])
        self.assertEqual(
            stdout_tree,
            DataTree.from_item(
                RuntimeArtifactRef.staged(
                    "stored_stdout",
                    data_type_id=PATH_DATA_TYPE_ID,
                    schema_version=1,
                    format="txt",
                    size_bytes=0,
                    sha256="0" * 64,
                    provenance="corex.test.fixture",
                )
            ),
        )
        self.assertEqual(preview_tree, DataTree.from_item("ok"))

    def test_persistent_node_elapsed_time_protocol_client_listener_preserves_timing_fields(
        self,
    ) -> None:
        self.client._event_queue.put(
            event_to_dict(
                NodeStartedEvent(
                    run_id="run_timing",
                    workspace_id="ws_main",
                    node_id="node_timing",
                    started_at_epoch_ms=1234.5,
                )
            )
        )  # noqa: SLF001
        self.client._event_queue.put(
            event_to_dict(
                NodeSettledEvent(
                    run_id="run_timing",
                    workspace_id="ws_main",
                    node_id="node_timing",
                    elapsed_ms=45.25,
                    outputs={
                        "status": SettledPortResult(
                            status="value",
                            value=DataTree.from_item("ok"),
                        )
                    },
                )
            )
        )  # noqa: SLF001

        started = self._wait_for_event(
            lambda payload: (
                payload.get("type") == "node_started"
                and payload.get("run_id") == "run_timing"
            ),
            timeout=3.0,
        )
        completed = self._wait_for_event(
            lambda payload: (
                payload.get("type") == "node_settled"
                and payload.get("run_id") == "run_timing"
            ),
            timeout=3.0,
        )

        self.assertIsNotNone(started)
        self.assertIsNotNone(completed)
        if started is None or completed is None:
            self.fail("timing events were not received")
        self.assertEqual(started["started_at_epoch_ms"], 1234.5)
        self.assertEqual(completed["elapsed_ms"], 45.25)
        self.assertEqual(completed["outputs"]["status"]["status"], "value")

    def test_persistent_node_elapsed_time_protocol_client_listener_defaults_legacy_timing_fields(
        self,
    ) -> None:
        self.client._event_queue.put(
            {
                "type": "node_started",
                "run_id": "run_legacy",
                "workspace_id": "ws_main",
                "node_id": "node_legacy",
            }
        )  # noqa: SLF001
        legacy_settled = event_to_dict(
            NodeSettledEvent(
                run_id="run_legacy",
                workspace_id="ws_main",
                node_id="node_legacy",
                outputs={"status": SettledPortResult(status="empty")},
            )
        )
        legacy_settled.pop("elapsed_ms")
        self.client._event_queue.put(legacy_settled)  # noqa: SLF001

        started = self._wait_for_event(
            lambda payload: (
                payload.get("type") == "node_started"
                and payload.get("run_id") == "run_legacy"
            ),
            timeout=3.0,
        )
        completed = self._wait_for_event(
            lambda payload: (
                payload.get("type") == "node_settled"
                and payload.get("run_id") == "run_legacy"
            ),
            timeout=3.0,
        )

        self.assertIsNotNone(started)
        self.assertIsNotNone(completed)
        if started is None or completed is None:
            self.fail("legacy timing events were not received")
        self.assertEqual(started["started_at_epoch_ms"], 0.0)
        self.assertEqual(completed["elapsed_ms"], 0.0)
        self.assertEqual(completed["outputs"]["status"]["status"], "empty")

    def test_worker_death_emits_failure_and_next_run_recovers(self) -> None:
        workspace_id, long_runtime_snapshot = self._build_runtime_snapshot(
            with_sleep_script=True
        )
        first_run_id = self.client.start_run(
            project_path="",
            workspace_id=workspace_id,
            trigger={"kind": "manual", "runtime_snapshot": long_runtime_snapshot},
            data_types=self.data_types,
            plugin_bundles=self.registry.plugin_bundle_refs(),
            plugin_fingerprint=self.registry.plugin_fingerprint(),
            registry_contract_fingerprint=self.registry.contract_fingerprint(),
            addon_runtime_config=self.registry.addon_runtime_config(),
        )
        self.assertTrue(first_run_id)

        started = self._wait_for_event(
            lambda event: (
                event.get("type") == "run_started"
                and event.get("run_id") == first_run_id
            ),
            timeout=12.0,
        )
        self.assertIsNotNone(started)

        process = self.client._process  # noqa: SLF001
        self.assertIsNotNone(process)
        if process is not None:
            process.terminate()
            process.join(timeout=1.0)

        failed = self._wait_for_event(
            lambda event: (
                event.get("type") == "run_failed"
                and event.get("run_id") == first_run_id
                and bool(event.get("fatal"))
            ),
            timeout=5.0,
        )
        self.assertIsNotNone(failed)

        recovery_workspace_id, recovery_runtime_snapshot = self._build_runtime_snapshot(
            with_sleep_script=False
        )
        second_run_id = self.client.start_run(
            project_path="",
            workspace_id=recovery_workspace_id,
            trigger={"kind": "manual", "runtime_snapshot": recovery_runtime_snapshot},
            data_types=self.data_types,
            plugin_bundles=self.registry.plugin_bundle_refs(),
            plugin_fingerprint=self.registry.plugin_fingerprint(),
            registry_contract_fingerprint=self.registry.contract_fingerprint(),
            addon_runtime_config=self.registry.addon_runtime_config(),
        )
        self.assertTrue(second_run_id)
        self.assertNotEqual(first_run_id, second_run_id)

        completed = self._wait_for_event(
            lambda event: (
                event.get("type") == "run_completed"
                and event.get("run_id") == second_run_id
            ),
            timeout=12.0,
        )
        self.assertIsNotNone(completed)

    def test_worker_death_emits_failure_with_running_python_script_node_id(
        self,
    ) -> None:
        workspace_id, script_id, runtime_snapshot = self._build_script_runtime_snapshot(
            "import os, time\ntime.sleep(0.2)\nos._exit(17)"
        )
        run_id = self.client.start_run(
            project_path="",
            workspace_id=workspace_id,
            trigger={"kind": "manual", "runtime_snapshot": runtime_snapshot},
            data_types=self.data_types,
            plugin_bundles=self.registry.plugin_bundle_refs(),
            plugin_fingerprint=self.registry.plugin_fingerprint(),
            registry_contract_fingerprint=self.registry.contract_fingerprint(),
            addon_runtime_config=self.registry.addon_runtime_config(),
        )
        self.assertTrue(run_id)

        started = self._wait_for_event(
            lambda event: (
                event.get("type") == "node_started"
                and event.get("run_id") == run_id
                and event.get("node_id") == script_id
            ),
            timeout=12.0,
        )
        self.assertIsNotNone(started)

        failed = self._wait_for_event(
            lambda event: (
                event.get("type") == "run_failed"
                and event.get("run_id") == run_id
                and bool(event.get("fatal"))
                and event.get("node_id") == script_id
            ),
            timeout=8.0,
        )
        self.assertIsNotNone(failed)
        self.assertIn("terminated unexpectedly", str(failed.get("error", "")))

    def test_python_script_timeout_terminates_worker_with_node_id(self) -> None:
        workspace_id, script_id, runtime_snapshot = self._build_script_runtime_snapshot(
            "while True:\n    pass",
            timeout_sec=0.25,
        )
        run_id = self.client.start_run(
            project_path="",
            workspace_id=workspace_id,
            trigger={"kind": "manual", "runtime_snapshot": runtime_snapshot},
            data_types=self.data_types,
            plugin_bundles=self.registry.plugin_bundle_refs(),
            plugin_fingerprint=self.registry.plugin_fingerprint(),
            registry_contract_fingerprint=self.registry.contract_fingerprint(),
            addon_runtime_config=self.registry.addon_runtime_config(),
        )
        self.assertTrue(run_id)

        failed = self._wait_for_event(
            lambda event: (
                event.get("type") == "run_failed"
                and event.get("run_id") == run_id
                and bool(event.get("fatal"))
                and event.get("node_id") == script_id
                and "timed out" in str(event.get("error", ""))
            ),
            timeout=8.0,
        )
        self.assertIsNotNone(failed)
        timeout_state = self._wait_for_event(
            lambda event: (
                event.get("type") == "run_state"
                and event.get("run_id") == run_id
                and event.get("state") == "error"
                and event.get("reason") == "python_script_timeout"
            ),
            timeout=3.0,
        )
        self.assertIsNotNone(timeout_state)

    def test_client_receives_streamed_process_output_events(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        process_node = model.add_node(
            workspace.workspace_id,
            "io.process_run",
            "Process",
            100,
            0,
            properties={
                "command": sys.executable,
                "args": [
                    "-c",
                    (
                        "import sys, time\n"
                        "print('tick_client_0', flush=True)\n"
                        "time.sleep(0.15)\n"
                        "print('warn_client_0', file=sys.stderr, flush=True)\n"
                        "time.sleep(0.15)\n"
                        "print('tick_client_1', flush=True)\n"
                    ),
                ],
                "timeout_sec": 5.0,
                "shell": False,
                "fail_on_nonzero": True,
                "env": {},
                "encoding": "utf-8",
                "cwd": "",
            },
        )
        runtime_snapshot = build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=build_default_registry(),
        )

        run_id = self.client.start_run(
            project_path="",
            workspace_id=workspace.workspace_id,
            trigger={"kind": "manual", "runtime_snapshot": runtime_snapshot},
            data_types=self.data_types,
            plugin_bundles=self.registry.plugin_bundle_refs(),
            plugin_fingerprint=self.registry.plugin_fingerprint(),
            registry_contract_fingerprint=self.registry.contract_fingerprint(),
            addon_runtime_config=self.registry.addon_runtime_config(),
        )
        self.assertTrue(run_id)

        first_stream_event = self._wait_for_event(
            lambda event: (
                event.get("type") == "log"
                and event.get("run_id") == run_id
                and "tick_client_0" in str(event.get("message", ""))
            ),
            timeout=30.0,
        )
        self.assertIsNotNone(first_stream_event)

        completed = self._wait_for_event(
            lambda event: (
                event.get("type") == "run_completed" and event.get("run_id") == run_id
            ),
            timeout=30.0,
        )
        self.assertIsNotNone(completed)

        with self._events_lock:
            run_events = [
                event for event in self._events if event.get("run_id") == run_id
            ]

        stream_messages = [
            str(event.get("message", ""))
            for event in run_events
            if event.get("type") == "log"
        ]
        self.assertTrue(any("tick_client_0" in message for message in stream_messages))
        self.assertTrue(any("tick_client_1" in message for message in stream_messages))
        self.assertTrue(any("warn_client_0" in message for message in stream_messages))

    def test_client_requires_runtime_snapshot_trigger(self) -> None:
        workspace_id, _runtime_snapshot = self._build_runtime_snapshot(
            with_sleep_script=False
        )

        run_id = self.client.start_run(
            project_path="",
            workspace_id=workspace_id,
            trigger={
                "kind": "manual",
                "workflow_settings": {"general": {"project_name": "Demo"}},
            },
            data_types=self.data_types,
            plugin_bundles=self.registry.plugin_bundle_refs(),
            plugin_fingerprint=self.registry.plugin_fingerprint(),
            registry_contract_fingerprint=self.registry.contract_fingerprint(),
            addon_runtime_config=self.registry.addon_runtime_config(),
        )
        self.assertEqual(run_id, "")

        protocol_error = self._wait_for_event(
            lambda event: (
                event.get("type") == "protocol_error"
                and event.get("command") == "start_run"
                and "requires runtime_snapshot" in str(event.get("error", ""))
            ),
            timeout=3.0,
        )
        self.assertIsNotNone(protocol_error)
        self.assertIsNone(self.client._process)  # noqa: SLF001

    def test_open_viewer_session_enqueues_correlated_runtime_ref_payload(self) -> None:
        self.client._ensure_process = lambda: None  # type: ignore[method-assign]  # noqa: SLF001

        request_id = self.client.open_viewer_session(
            "ws_main",
            "node_viewer",
            session_id="session_existing",
            backend_id=ENGINEERING_VIEWER_BACKEND_ID,
            data_refs={
                "dataset": RuntimeHandleRef(
                    data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
                    schema_version=1,
                    handle_id="viewer_dataset_live",
                    kind=COREX_SCENE_HANDLE_KIND,
                    owner_scope="viewer:session_existing",
                    worker_generation=3,
                ),
                "preview": RuntimeArtifactRef.staged(
                    "viewer_preview_png",
                    data_type_id=PATH_DATA_TYPE_ID,
                    schema_version=1,
                    format="png",
                    size_bytes=0,
                    sha256="0" * 64,
                    provenance="corex.test.fixture",
                ),
                "table": TabularDataRef(
                    ref_id="table_runtime_client",
                    resolver_id="tabular.cache",
                    backend_id="duckdb",
                    row_count=50,
                    column_count=3,
                ),
                "array": ArrayDataRef(
                    ref_id="array_runtime_client",
                    resolver_id="tabular.cache",
                    backend_id="npy_mmap",
                    shape=(20, 10),
                    dtype="float32",
                ),
            },
            transport={
                "kind": "scene_handle_refs",
                "version": 1,
            },
            transport_revision=5,
            live_open_status="ready",
            camera_state={"position": [1.0, 2.0, 3.0]},
            playback_state={"state": "paused", "step_index": 1},
            summary={"result_name": "displacement", "set_ids": [1, 2]},
            options={"live_mode": "proxy"},
        )

        payload = self.client._command_queue.get(timeout=1.0)  # noqa: SLF001

        self.assertEqual(payload["type"], "open_viewer_session")
        self.assertEqual(payload["request_id"], request_id)
        self.assertEqual(payload["workspace_id"], "ws_main")
        self.assertEqual(payload["node_id"], "node_viewer")
        self.assertEqual(payload["session_id"], "session_existing")
        self.assertEqual(payload["backend_id"], ENGINEERING_VIEWER_BACKEND_ID)
        self.assertEqual(
            payload["transport"], {"kind": "scene_handle_refs", "version": 1}
        )
        self.assertEqual(payload["transport_revision"], 5)
        self.assertEqual(payload["live_open_status"], "ready")
        self.assertEqual(payload["camera_state"], {"position": [1.0, 2.0, 3.0]})
        self.assertEqual(
            payload["playback_state"], {"state": "paused", "step_index": 1}
        )
        self.assertEqual(
            payload["data_refs"]["dataset"],
            {
                "__ea_runtime_value__": "handle_ref",
                "data_type_id": ENGINEERING_SCENE_DATA_TYPE_ID,
                "schema_version": 1,
                "handle_id": "viewer_dataset_live",
                "kind": COREX_SCENE_HANDLE_KIND,
                "owner_scope": "viewer:session_existing",
                "worker_generation": 3,
            },
        )
        self.assertEqual(
            payload["data_refs"]["preview"],
            {
                "__ea_runtime_value__": "artifact_ref",
                "ref": "temp://viewer_preview_png",
                "artifact_id": "viewer_preview_png",
                "scope": "staged",
                "data_type_id": PATH_DATA_TYPE_ID,
                "schema_version": 1,
                "format": "png",
                "size_bytes": 0,
                "sha256": "0" * 64,
                "provenance": "corex.test.fixture",
            },
        )
        self.assertEqual(
            payload["data_refs"]["table"],
            {
                "__ea_runtime_value__": "tabular_data_ref",
                "data_type_id": TABULAR_DATA_REF_TYPE_ID,
                "schema_version": 1,
                "ref_id": "table_runtime_client",
                "resolver_id": "tabular.cache",
                "backend_id": "duckdb",
                "row_count": 50,
                "column_count": 3,
            },
        )
        self.assertEqual(
            payload["data_refs"]["array"],
            {
                "__ea_runtime_value__": "array_data_ref",
                "data_type_id": ARRAY_DATA_REF_TYPE_ID,
                "schema_version": 1,
                "ref_id": "array_runtime_client",
                "resolver_id": "tabular.cache",
                "backend_id": "npy_mmap",
                "shape": [20, 10],
                "dtype": "float32",
            },
        )
        self.assertEqual(
            payload["summary"], {"result_name": "displacement", "set_ids": [1, 2]}
        )
        self.assertEqual(payload["options"], {"live_mode": "proxy"})

    def test_viewer_protocol_error_uses_request_id_instead_of_command_order(
        self,
    ) -> None:
        self.client._ensure_process = lambda: None  # type: ignore[method-assign]  # noqa: SLF001

        first_request_id = self.client.update_viewer_session(
            "ws_main",
            "node_viewer",
            "session_live",
            options={"selection": {"set_ids": [1]}},
        )
        second_request_id = self.client.update_viewer_session(
            "ws_main",
            "node_viewer",
            "session_live",
            options={"selection": {"set_ids": [2]}},
        )
        self.client._command_queue.get(timeout=1.0)  # noqa: SLF001
        self.client._command_queue.get(timeout=1.0)  # noqa: SLF001

        self.client._event_queue.put(
            event_to_dict(
                ProtocolErrorEvent(
                    request_id=second_request_id,
                    workspace_id="ws_main",
                    command="update_viewer_session",
                    error="Unknown command type.",
                )
            )
        )  # noqa: SLF001

        failure = self._wait_for_event(
            lambda event: (
                event.get("type") == "viewer_session_failed"
                and event.get("request_id") == second_request_id
            ),
            timeout=3.0,
        )
        protocol_error = self._wait_for_event(
            lambda event: (
                event.get("type") == "protocol_error"
                and event.get("command") == "update_viewer_session"
                and event.get("request_id") == second_request_id
            ),
            timeout=3.0,
        )

        self.assertIsNotNone(protocol_error)
        self.assertIsNotNone(failure)
        if failure is None:
            self.fail("viewer_session_failed event was not received")
        self.assertEqual(failure["workspace_id"], "ws_main")
        self.assertEqual(failure["node_id"], "node_viewer")
        self.assertEqual(failure["session_id"], "session_live")
        self.assertEqual(failure["command"], "update_viewer_session")
        self.assertEqual(failure["error"], "Unknown command type.")
        with self.client._viewer_request_lock:  # noqa: SLF001
            self.assertIn(first_request_id, self.client._pending_viewer_requests)  # noqa: SLF001
            self.assertNotIn(second_request_id, self.client._pending_viewer_requests)  # noqa: SLF001

    def test_viewer_success_event_coexists_with_run_terminal_state_reset(self) -> None:
        self.client._ensure_process = lambda: None  # type: ignore[method-assign]  # noqa: SLF001

        request_id = self.client.open_viewer_session(
            "ws_main",
            "node_viewer",
            summary={"result_name": "displacement"},
        )
        self.client._command_queue.get(timeout=1.0)  # noqa: SLF001

        with self.client._state_lock:  # noqa: SLF001
            self.client._active_run_id = "run_demo"  # noqa: SLF001
            self.client._active_workspace_id = "ws_main"  # noqa: SLF001

        self.client._event_queue.put(
            event_to_dict(
                ViewerSessionOpenedEvent(
                    request_id=request_id,
                    workspace_id="ws_main",
                    node_id="node_viewer",
                    session_id="session_live",
                    summary={"dataset_type": "UnstructuredGrid"},
                    options={"live_mode": "proxy"},
                )
            )
        )  # noqa: SLF001
        self.client._event_queue.put(
            event_to_dict(
                RunCompletedEvent(
                    run_id="run_demo",
                    workspace_id="ws_main",
                )
            )
        )  # noqa: SLF001

        opened = self._wait_for_event(
            lambda event: (
                event.get("type") == "viewer_session_opened"
                and event.get("request_id") == request_id
            ),
            timeout=3.0,
        )
        completed = self._wait_for_event(
            lambda event: (
                event.get("type") == "run_completed"
                and event.get("run_id") == "run_demo"
            ),
            timeout=3.0,
        )

        self.assertIsNotNone(opened)
        self.assertIsNotNone(completed)
        with self.client._state_lock:  # noqa: SLF001
            self.assertEqual(self.client._active_run_id, "")  # noqa: SLF001
            self.assertEqual(self.client._active_workspace_id, "")  # noqa: SLF001
        with self.client._viewer_request_lock:  # noqa: SLF001
            self.assertNotIn(request_id, self.client._pending_viewer_requests)  # noqa: SLF001
