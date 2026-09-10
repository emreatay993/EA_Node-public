# Purpose: External-Python stdio transport, preflight, reuse, switching, and recovery behavior.
# Map: subsystems/execution.md
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ea_node_editor.execution.backend_client import ExecutionBackendClient
from ea_node_editor.execution.backends import (
    EXTERNAL_SUBPROCESS_BACKEND,
)
from ea_node_editor.execution.external_python_client import (
    ExternalPythonExecutionClient,
)
from ea_node_editor.execution.managed_runtime import (
    resolve_managed_runtime_paths,
)
from ea_node_editor.execution.protocol_codec import (
    event_to_dict,
)
from ea_node_editor.execution.python_environment import (
    resolve_python_environment,
    workflow_python_path_from_snapshot,
)
from ea_node_editor.execution.viewer_messages import (
    ViewerSessionOpenedEvent,
)
from tests.execution_client_fixtures import (
    ProcessClientTestHarness,
    _default_registry_agreement,
    _external_process_mock,
    _external_selection,
    _revision_catalog,
    _seed_external_generation,
    _simple_runtime_snapshot,
)


class ExternalPythonClientTests(unittest.TestCase):
    def test_external_respawn_settles_dead_run_and_ignores_old_stdout(
        self,
    ) -> None:
        first_process = _external_process_mock()
        second_process = _external_process_mock()
        client = ExternalPythonExecutionClient()
        client._data_types = _revision_catalog("external-respawn")  # noqa: SLF001
        client._catalog_generation_token = 1  # noqa: SLF001
        events: list[dict] = []
        client.subscribe(events.append)

        try:
            with (
                patch.object(client, "_verify_runtime_available"),
                patch(
                    "ea_node_editor.execution.external_python_client.subprocess.Popen",
                    side_effect=(first_process, second_process),
                ),
            ):
                client._ensure_process("python-a")  # noqa: SLF001
                client._active_run_id = "run_second"  # noqa: SLF001
                client._active_workspace_id = "ws_second"  # noqa: SLF001
                client._run_generation_tokens["run_second"] = 1  # noqa: SLF001
                first_process.returncode = 1
                client._ensure_process("python-a")  # noqa: SLF001

            self.assertEqual(client._catalog_generation_token, 2)  # noqa: SLF001
            self.assertIs(client._process, second_process)  # noqa: SLF001
            self.assertEqual(client._active_run_id, "")  # noqa: SLF001
            self.assertNotIn("run_second", client._run_generation_tokens)  # noqa: SLF001
            self.assertTrue(
                any(
                    event.get("type") == "run_failed"
                    and event.get("run_id") == "run_second"
                    for event in events
                )
            )
            self.assertTrue(
                any(
                    event.get("type") == "run_state"
                    and event.get("run_id") == "run_second"
                    and event.get("reason") == "external_python_worker_terminated"
                    for event in events
                )
            )
            events_before_stale_stdout = list(events)
            client._handle_stdout_line(  # noqa: SLF001
                json.dumps(
                    event_to_dict(
                        ViewerSessionOpenedEvent(
                            request_id="viewer_old",
                            workspace_id="ws_old",
                            session_id="session_old",
                        ),
                        catalog=client._data_types,  # noqa: SLF001
                    )
                ),
                generation_token=1,
            )
            self.assertEqual(events, events_before_stale_stdout)
            self.assertNotIn(  # noqa: SLF001
                ("ws_old", "session_old"),
                client._viewer_session_ids,
            )
        finally:
            client.shutdown()

    def test_external_python_same_live_worker_skips_preflight_and_generation_change(
        self,
    ) -> None:
        registry, workspace_id, runtime_snapshot = _simple_runtime_snapshot()
        process = _external_process_mock()
        client = ExternalPythonExecutionClient()
        _seed_external_generation(
            client,
            process,
            python_executable=sys.executable,
        )

        try:
            with (
                patch.object(client, "_verify_runtime_available") as verify,
                patch(
                    "ea_node_editor.execution.external_python_client.subprocess.Popen"
                ) as popen,
                patch.object(client, "_post_command", return_value=True),
            ):
                run_id = client.start_run(
                    "",
                    workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    execution_backend=_external_selection(sys.executable),
                    data_types=registry.data_types,
                    plugin_bundles=registry.plugin_bundle_refs(),
                    plugin_fingerprint=registry.plugin_fingerprint(),
                    registry_contract_fingerprint=registry.contract_fingerprint(),
                    addon_runtime_config=registry.addon_runtime_config(),
                )

            self.assertTrue(run_id)
            verify.assert_not_called()
            popen.assert_not_called()
            self.assertIs(client._process, process)  # noqa: SLF001
            self.assertEqual(client._physical_generation_token, 1)  # noqa: SLF001
            self.assertEqual(client._accepted_physical_generation_token, 1)  # noqa: SLF001
            client._release_start_run(run_id)  # noqa: SLF001
        finally:
            client.shutdown()

    def test_external_python_dead_same_path_preflights_before_run_reservation(
        self,
    ) -> None:
        registry, workspace_id, runtime_snapshot = _simple_runtime_snapshot()
        process = _external_process_mock()
        process.returncode = 1
        client = ExternalPythonExecutionClient()
        _seed_external_generation(
            client,
            process,
            python_executable=sys.executable,
        )
        order: list[str] = []
        prepare_start_run = client._prepare_start_run  # noqa: SLF001

        def prepare(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            order.append("prepare")
            return prepare_start_run(*args, **kwargs)

        try:
            with (
                patch.object(
                    client,
                    "_verify_runtime_available",
                    side_effect=lambda _python: order.append("preflight"),
                ) as verify,
                patch.object(client, "_prepare_start_run", side_effect=prepare),
                patch.object(client, "_ensure_process"),
                patch.object(client, "_post_command", return_value=True),
            ):
                run_id = client.start_run(
                    "",
                    workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    execution_backend=_external_selection(sys.executable),
                    data_types=registry.data_types,
                    plugin_bundles=registry.plugin_bundle_refs(),
                    plugin_fingerprint=registry.plugin_fingerprint(),
                    registry_contract_fingerprint=registry.contract_fingerprint(),
                    addon_runtime_config=registry.addon_runtime_config(),
                )

            self.assertTrue(run_id)
            self.assertEqual(order[:2], ["preflight", "prepare"])
            verify.assert_called_once_with(sys.executable)
            client._release_start_run(run_id)  # noqa: SLF001
        finally:
            client.shutdown()

    def test_external_python_viewer_guard_precedes_switched_path_preflight(
        self,
    ) -> None:
        registry, workspace_id, runtime_snapshot = _simple_runtime_snapshot()
        process = _external_process_mock()
        client = ExternalPythonExecutionClient()
        _seed_external_generation(
            client,
            process,
            python_executable="python-a",
        )
        client._viewer_session_ids.add((workspace_id, "session"))  # noqa: SLF001
        events: list[dict] = []
        client.subscribe(events.append)

        try:
            with (
                patch.object(client, "_verify_runtime_available") as verify,
                patch.object(client, "_prepare_start_run") as prepare,
                patch.object(client, "_ensure_process") as ensure,
            ):
                run_id = client.start_run(
                    "",
                    workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    execution_backend=_external_selection("python-b"),
                    data_types=registry.data_types,
                    registry_contract_fingerprint=registry.contract_fingerprint(),
                )

            self.assertEqual(run_id, "")
            verify.assert_not_called()
            prepare.assert_not_called()
            ensure.assert_not_called()
            self.assertIs(client._process, process)  # noqa: SLF001
            self.assertEqual(client._accepted_physical_generation_token, 1)  # noqa: SLF001
            self.assertTrue(
                any(
                    "viewer requests or sessions" in str(event.get("error", ""))
                    for event in events
                )
            )
        finally:
            client.shutdown()

    def test_external_python_import_incompatible_switch_preserves_live_worker(
        self,
    ) -> None:
        registry, workspace_id, runtime_snapshot = _simple_runtime_snapshot()
        process = _external_process_mock()
        client = ExternalPythonExecutionClient()
        _seed_external_generation(
            client,
            process,
            python_executable="python-a",
        )
        events: list[dict] = []
        client.subscribe(events.append)

        try:
            with (
                patch.object(
                    client,
                    "_verify_runtime_available",
                    side_effect=RuntimeError(
                        "Configured Python executable cannot import "
                        "ea_node_editor.execution.stdio_worker."
                    ),
                ),
                patch.object(client, "_prepare_start_run") as prepare,
                patch.object(client, "_ensure_process") as ensure,
            ):
                run_id = client.start_run(
                    "",
                    workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    execution_backend=_external_selection("python-b"),
                    data_types=registry.data_types,
                    registry_contract_fingerprint=registry.contract_fingerprint(),
                )

            self.assertEqual(run_id, "")
            prepare.assert_not_called()
            ensure.assert_not_called()
            self.assertIs(client._process, process)  # noqa: SLF001
            self.assertEqual(client._physical_generation_token, 1)  # noqa: SLF001
            self.assertEqual(client._accepted_physical_generation_token, 1)  # noqa: SLF001
            self.assertEqual(client._active_run_id, "")  # noqa: SLF001
            self.assertTrue(
                any("cannot import" in str(event.get("error", "")) for event in events)
            )
        finally:
            client.shutdown()

    def test_external_python_valid_switch_advances_generation_after_preflight(
        self,
    ) -> None:
        registry, workspace_id, runtime_snapshot = _simple_runtime_snapshot()
        old_process = _external_process_mock()
        new_process = _external_process_mock()
        client = ExternalPythonExecutionClient()
        _seed_external_generation(
            client,
            old_process,
            python_executable="python-a",
        )

        try:
            with (
                patch.object(client, "_verify_runtime_available") as verify,
                patch(
                    "ea_node_editor.execution.external_python_client.subprocess.Popen",
                    return_value=new_process,
                ),
                patch.object(client, "_post_command", return_value=True),
            ):
                run_id = client.start_run(
                    "",
                    workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    execution_backend=_external_selection("python-b"),
                    data_types=registry.data_types,
                    plugin_bundles=registry.plugin_bundle_refs(),
                    plugin_fingerprint=registry.plugin_fingerprint(),
                    registry_contract_fingerprint=registry.contract_fingerprint(),
                    addon_runtime_config=registry.addon_runtime_config(),
                )

            self.assertTrue(run_id)
            verify.assert_called_once_with("python-b")
            self.assertIs(client._process, new_process)  # noqa: SLF001
            self.assertEqual(client._python_executable, "python-b")  # noqa: SLF001
            self.assertEqual(client._physical_generation_token, 2)  # noqa: SLF001
            self.assertEqual(client._accepted_physical_generation_token, 2)  # noqa: SLF001
            client._release_start_run(run_id)  # noqa: SLF001
        finally:
            client.shutdown()

    def test_external_python_cold_popen_failure_releases_and_recovers(
        self,
    ) -> None:
        registry, workspace_id, runtime_snapshot = _simple_runtime_snapshot()
        recovered_process = _external_process_mock()
        client = ExternalPythonExecutionClient()
        events: list[dict] = []
        client.subscribe(events.append)

        try:
            with (
                patch.object(client, "_verify_runtime_available") as verify,
                patch(
                    "ea_node_editor.execution.external_python_client.subprocess.Popen",
                    side_effect=(OSError("launch failed"), recovered_process),
                ),
                patch.object(client, "_post_command", return_value=True),
            ):
                failed_run = client.start_run(
                    "",
                    workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    execution_backend=_external_selection("python-a"),
                    data_types=registry.data_types,
                    plugin_bundles=registry.plugin_bundle_refs(),
                    plugin_fingerprint=registry.plugin_fingerprint(),
                    registry_contract_fingerprint=registry.contract_fingerprint(),
                    addon_runtime_config=registry.addon_runtime_config(),
                )
                self.assertEqual(failed_run, "")
                self.assertIsNone(client._process)  # noqa: SLF001
                self.assertEqual(client._physical_generation_token, 0)  # noqa: SLF001
                self.assertEqual(client._accepted_physical_generation_token, -1)  # noqa: SLF001
                self.assertEqual(client._active_run_id, "")  # noqa: SLF001
                self.assertEqual(client._start_run_pending_id, "")  # noqa: SLF001
                self.assertEqual(client._run_generation_tokens, {})  # noqa: SLF001

                recovered_run = client.start_run(
                    "",
                    workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    execution_backend=_external_selection("python-a"),
                    data_types=registry.data_types,
                    plugin_bundles=registry.plugin_bundle_refs(),
                    plugin_fingerprint=registry.plugin_fingerprint(),
                    registry_contract_fingerprint=registry.contract_fingerprint(),
                    addon_runtime_config=registry.addon_runtime_config(),
                )

            self.assertTrue(recovered_run)
            self.assertEqual(verify.call_count, 2)
            self.assertIs(client._process, recovered_process)  # noqa: SLF001
            self.assertEqual(client._physical_generation_token, 1)  # noqa: SLF001
            self.assertEqual(client._accepted_physical_generation_token, 1)  # noqa: SLF001
            self.assertTrue(
                any("launch failed" in str(event.get("error", "")) for event in events)
            )
            client._release_start_run(recovered_run)  # noqa: SLF001
        finally:
            client.shutdown()

    def test_external_python_switched_popen_failure_releases_and_recovers(
        self,
    ) -> None:
        registry, workspace_id, runtime_snapshot = _simple_runtime_snapshot()
        old_process = _external_process_mock()
        recovered_process = _external_process_mock()
        client = ExternalPythonExecutionClient()
        _seed_external_generation(
            client,
            old_process,
            python_executable="python-a",
        )

        try:
            with (
                patch.object(client, "_verify_runtime_available") as verify,
                patch(
                    "ea_node_editor.execution.external_python_client.subprocess.Popen",
                    side_effect=(OSError("switch launch failed"), recovered_process),
                ),
                patch.object(client, "_post_command", return_value=True),
            ):
                failed_run = client.start_run(
                    "",
                    workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    execution_backend=_external_selection("python-b"),
                    data_types=registry.data_types,
                    plugin_bundles=registry.plugin_bundle_refs(),
                    plugin_fingerprint=registry.plugin_fingerprint(),
                    registry_contract_fingerprint=registry.contract_fingerprint(),
                    addon_runtime_config=registry.addon_runtime_config(),
                )
                self.assertEqual(failed_run, "")
                self.assertIsNone(client._process)  # noqa: SLF001
                self.assertEqual(client._physical_generation_token, 1)  # noqa: SLF001
                self.assertEqual(client._accepted_physical_generation_token, -1)  # noqa: SLF001
                self.assertEqual(client._active_run_id, "")  # noqa: SLF001
                self.assertEqual(client._start_run_pending_id, "")  # noqa: SLF001
                self.assertEqual(client._run_generation_tokens, {})  # noqa: SLF001

                recovered_run = client.start_run(
                    "",
                    workspace_id,
                    {"runtime_snapshot": runtime_snapshot},
                    execution_backend=_external_selection("python-b"),
                    data_types=registry.data_types,
                    plugin_bundles=registry.plugin_bundle_refs(),
                    plugin_fingerprint=registry.plugin_fingerprint(),
                    registry_contract_fingerprint=registry.contract_fingerprint(),
                    addon_runtime_config=registry.addon_runtime_config(),
                )

            self.assertTrue(recovered_run)
            self.assertEqual(verify.call_count, 2)
            self.assertIs(client._process, recovered_process)  # noqa: SLF001
            self.assertEqual(client._physical_generation_token, 2)  # noqa: SLF001
            self.assertEqual(client._accepted_physical_generation_token, 2)  # noqa: SLF001
            client._release_start_run(recovered_run)  # noqa: SLF001
        finally:
            client.shutdown()

    def test_external_python_preflight_only_checks_stdio_worker_import(self) -> None:
        client = ExternalPythonExecutionClient()
        try:
            with patch(
                "ea_node_editor.execution.external_python_client.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                ),
            ) as run:
                client._verify_runtime_available("python-a")  # noqa: SLF001
                client._verify_runtime_available("python-a")  # noqa: SLF001

            self.assertEqual(run.call_count, 2)
            run.assert_called_with(
                [
                    "python-a",
                    "-c",
                    "import ea_node_editor.execution.stdio_worker",
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=10.0,
            )
        finally:
            client.shutdown()

    def test_external_executable_switch_rejects_live_viewer_generation(
        self,
    ) -> None:
        client = ExternalPythonExecutionClient()
        process = Mock()
        process.poll.return_value = None
        client._process = process  # noqa: SLF001
        client._python_executable = "python-a"  # noqa: SLF001
        client._catalog_generation_token = 1  # noqa: SLF001
        client._physical_generation_token = 1  # noqa: SLF001
        client._viewer_session_ids.add(("ws", "session"))  # noqa: SLF001

        try:
            with (
                patch.object(client, "_terminate_process") as terminate,
                self.assertRaisesRegex(
                    RuntimeError,
                    "viewer requests or sessions remain active",
                ),
            ):
                client._ensure_process("python-b")  # noqa: SLF001
            terminate.assert_not_called()
            self.assertIs(client._process, process)  # noqa: SLF001
            self.assertEqual(client._catalog_generation_token, 1)  # noqa: SLF001
        finally:
            client._process = None  # noqa: SLF001
            client.shutdown()

    def test_external_timeout_monitor_resnapshots_under_transition_lock(
        self,
    ) -> None:
        client = ExternalPythonExecutionClient()
        process = Mock()
        process.poll.return_value = None
        client._process = process  # noqa: SLF001
        client._catalog_generation_token = 1  # noqa: SLF001
        client._physical_generation_token = 1  # noqa: SLF001
        client._accepted_physical_generation_token = 1  # noqa: SLF001
        client._active_run_id = "run_old"  # noqa: SLF001
        client._active_node_id = "node_old"  # noqa: SLF001
        client._active_node_deadline = time.monotonic() - 1.0  # noqa: SLF001
        check_started = threading.Event()

        def check_health() -> None:
            check_started.set()
            client._check_worker_health()  # noqa: SLF001

        try:
            with (
                patch.object(client, "_terminate_process") as terminate,
                client._start_lock,  # noqa: SLF001
            ):
                monitor = threading.Thread(target=check_health)
                monitor.start()
                self.assertTrue(check_started.wait(timeout=1.0))
                client._active_run_id = "run_successor"  # noqa: SLF001
                client._active_node_id = ""  # noqa: SLF001
                client._active_node_deadline = 0.0  # noqa: SLF001
            monitor.join(timeout=1.0)
            self.assertFalse(monitor.is_alive())
            terminate.assert_not_called()
            self.assertEqual(client._active_run_id, "run_successor")  # noqa: SLF001
        finally:
            client._process = None  # noqa: SLF001
            client.shutdown()


class ExternalPythonSelectionTests(ProcessClientTestHarness):
    def test_workflow_python_environment_resolver_handles_configured_paths(
        self,
    ) -> None:
        _workspace_id, default_snapshot = self._build_runtime_snapshot()

        default_environment = resolve_python_environment(
            workflow_python_path_from_snapshot(default_snapshot)
        )

        self.assertFalse(default_environment.configured)
        self.assertTrue(default_environment.valid)

        _workspace_id, current_snapshot = self._build_runtime_snapshot(
            workflow_python_path=f'"{sys.executable}"'
        )
        current_path = workflow_python_path_from_snapshot(current_snapshot)
        current_environment = resolve_python_environment(current_path)

        self.assertEqual(current_path, sys.executable)
        self.assertTrue(current_environment.configured)
        self.assertTrue(current_environment.valid)
        self.assertTrue(current_environment.is_current_python)
        self.assertEqual(
            Path(current_environment.python_executable).resolve(),
            Path(sys.executable).resolve(),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_python = Path(tmp_dir) / "missing_python.exe"
            _workspace_id, invalid_snapshot = self._build_runtime_snapshot(
                workflow_python_path=str(missing_python)
            )

            invalid_environment = resolve_python_environment(
                workflow_python_path_from_snapshot(invalid_snapshot)
            )

        self.assertTrue(invalid_environment.configured)
        self.assertFalse(invalid_environment.valid)
        self.assertIn("does not exist", invalid_environment.error)

        with tempfile.TemporaryDirectory() as tmp_dir:
            directory_environment = resolve_python_environment(tmp_dir)
            candidate_file = Path(tmp_dir) / "python.exe"
            candidate_file.write_text("", encoding="utf-8")
            resolved_candidate = candidate_file.resolve()
            with patch(
                "ea_node_editor.execution.python_environment.os.access",
                side_effect=lambda path, _mode: path != resolved_candidate,
            ):
                non_executable_environment = resolve_python_environment(
                    str(candidate_file)
                )

        self.assertFalse(directory_environment.valid)
        self.assertIn("not a file", directory_environment.error)
        self.assertFalse(non_executable_environment.valid)
        self.assertIn("not executable", non_executable_environment.error)

        for malformed_path in (
            "bad\x00python.exe",
            f"C:\\{'nested-' * 2000}python.exe",
        ):
            with self.subTest(malformed=malformed_path[:20]):
                malformed_environment = resolve_python_environment(malformed_path)
                self.assertTrue(malformed_environment.configured)
                self.assertFalse(malformed_environment.valid)
                self.assertLessEqual(len(malformed_environment.python_executable), 600)
                self.assertLessEqual(len(malformed_environment.error), 1100)
                self.assertIn(
                    "Configured Python executable", malformed_environment.error
                )

        with tempfile.TemporaryDirectory() as tmp_dir:
            managed_paths = resolve_managed_runtime_paths(data_dir=tmp_dir)
            managed_paths.python_executable.parent.mkdir(parents=True, exist_ok=True)
            managed_paths.python_executable.write_text("", encoding="utf-8")
            managed_paths.python_executable.chmod(0o755)
            _workspace_id, managed_snapshot = self._build_runtime_snapshot(
                workflow_python_path=str(managed_paths.python_executable)
            )

            managed_environment = resolve_python_environment(
                workflow_python_path_from_snapshot(managed_snapshot),
                current_executable=Path(tmp_dir) / "other_python.exe",
            )

        self.assertTrue(managed_environment.configured)
        self.assertTrue(managed_environment.valid)
        self.assertFalse(managed_environment.is_current_python)
        self.assertEqual(
            Path(managed_environment.python_executable),
            managed_paths.python_executable.resolve(),
        )

    def test_external_python_malformed_paths_fail_closed_before_worker(self) -> None:
        backend_client = ExecutionBackendClient()
        events: list[dict] = []
        backend_client.subscribe(events.append)
        workspace_id, runtime_snapshot = self._build_runtime_snapshot()

        try:
            with patch.object(
                backend_client._external_python_client,  # noqa: SLF001
                "start_run",
            ) as external_start:
                for malformed_path in (
                    "bad\x00python.exe",
                    f"C:\\{'nested-' * 2000}python.exe",
                ):
                    with self.subTest(malformed=malformed_path[:20]):
                        events.clear()
                        external_start.reset_mock()
                        run_id = backend_client.start_run(
                            project_path="",
                            workspace_id=workspace_id,
                            trigger={"runtime_snapshot": runtime_snapshot},
                            execution_backend={
                                "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
                                "allow_external_subprocess": True,
                                "python_executable": malformed_path,
                            },
                            **_default_registry_agreement(),
                        )

                        self.assertEqual(run_id, "")
                        external_start.assert_not_called()
                        protocol_errors = [
                            event
                            for event in events
                            if event.get("type") == "protocol_error"
                        ]
                        self.assertEqual(len(protocol_errors), 1)
                        self.assertLessEqual(
                            len(str(protocol_errors[0].get("error", ""))),
                            1100,
                        )
        finally:
            backend_client.shutdown()

    def test_external_python_invalid_replacement_preserves_worker_generation(
        self,
    ) -> None:
        backend_client = ExecutionBackendClient()
        process = _external_process_mock()
        _seed_external_generation(
            backend_client._external_python_client,  # noqa: SLF001
            process,
            python_executable=sys.executable,
        )
        workspace_id, runtime_snapshot = self._build_runtime_snapshot()

        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_python = Path(tmp_dir) / "missing-python.exe"
            try:
                with (
                    patch.object(
                        backend_client._external_python_client,  # noqa: SLF001
                        "start_run",
                    ) as external_start,
                    patch(
                        "ea_node_editor.execution.external_python_client.subprocess.Popen"
                    ) as popen,
                ):
                    run_id = backend_client.start_run(
                        project_path="",
                        workspace_id=workspace_id,
                        trigger={"runtime_snapshot": runtime_snapshot},
                        execution_backend={
                            "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
                            "allow_external_subprocess": True,
                            "python_executable": str(missing_python),
                            "reason": "application_default_python_executable",
                        },
                        **_default_registry_agreement(),
                    )

                self.assertEqual(run_id, "")
                external_start.assert_not_called()
                popen.assert_not_called()
                external_client = backend_client._external_python_client  # noqa: SLF001
                self.assertIs(external_client._process, process)  # noqa: SLF001
                self.assertEqual(external_client._physical_generation_token, 1)  # noqa: SLF001
                self.assertEqual(external_client._accepted_physical_generation_token, 1)  # noqa: SLF001
            finally:
                backend_client.shutdown()

    def test_execution_backend_client_uses_workflow_python_executable_for_external_worker(
        self,
    ) -> None:
        self._assert_external_python_executable(
            workflow_python_path=sys.executable,
        )

    def test_execution_backend_client_uses_application_default_python_policy_for_external_worker(
        self,
    ) -> None:
        self._assert_external_python_executable(
            execution_backend={
                "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
                "allow_external_subprocess": True,
                "python_executable": sys.executable,
                "reason": "application_default_python_executable",
            },
        )
