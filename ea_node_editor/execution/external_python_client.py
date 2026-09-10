# Purpose: External-Python stdio execution transport lifecycle and health management.
# Map: subsystems/execution.md
# Tests: tests/test_external_python_client.py
# Landmarks: ExternalPythonExecutionClient
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from ea_node_editor.execution.backends import (
    ExecutionBackendSelection,
    coerce_execution_backend_selection,
)
from ea_node_editor.execution.client_common import (
    _ExecutionClientCommon,
    _PendingViewerRequest,
    _python_script_timeout_by_node_id,
    _registry_admitted,
)
from ea_node_editor.execution.protocol_codec import (
    WorkerCommand,
    coerce_start_run_command,
    event_to_dict,
)
from ea_node_editor.execution.registry_agreement import (
    EMPTY_REGISTRY_CONTRACT_FINGERPRINT,
)
from ea_node_editor.execution.run_messages import (
    RunFailedEvent,
    RunStateEvent,
    ShutdownCommand,
    StartRunCommand,
)
from ea_node_editor.execution.viewer_messages import (
    VIEWER_RESPONSE_EVENT_TYPES,
)
from ea_node_editor.nodes.function_plugin import (
    EMPTY_PLUGIN_FINGERPRINT,
    PluginBundleRef,
)
from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    DataTypeCatalogError,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult


class ExternalPythonExecutionClient(_ExecutionClientCommon):
    _RUNTIME_IMPORT_CHECK = "import ea_node_editor.execution.stdio_worker"

    def __init__(self) -> None:
        self._data_types: DataTypeCatalog | None = None
        self._catalog_generation_fingerprint = ""
        self._plugin_bundles: tuple[PluginBundleRef, ...] = ()
        self._plugin_fingerprint = EMPTY_PLUGIN_FINGERPRINT
        self._runtime_registry_generation_fingerprint = ""
        self._registry_contract_generation_fingerprint = ""
        self._addon_runtime_config: tuple[tuple[str, bool], ...] = ()
        self._catalog_generation_token = 0
        self._physical_generation_token = 0
        self._accepted_physical_generation_token = 0
        self._run_generation_tokens: dict[str, int] = {}
        self._process: subprocess.Popen | None = None
        self._python_executable = ""
        self._stdin_lock = threading.Lock()
        self._start_lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._generation_callbacks: list[Callable[..., None]] = []
        self._active_run_id = ""
        self._active_workspace_id = ""
        self._start_run_pending_id = ""
        self._active_node_id = ""
        self._active_node_deadline = 0.0
        self._active_node_timeout_sec = 0.0
        self._script_timeout_by_node_id: dict[str, float] = {}
        self._viewer_request_lock = threading.Lock()
        self._pending_viewer_requests: dict[str, _PendingViewerRequest] = {}
        self._viewer_session_ids: set[tuple[str, str]] = set()
        self._viewer_session_generations: dict[tuple[str, str], int] = {}
        self._viewer_session_node_ids: dict[tuple[str, str], str] = {}
        self._workspace_viewer_epochs: dict[str, int] = {}
        self._node_viewer_epochs: dict[tuple[str, str], int] = {}
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._running = True
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="external-python-monitor",
        )
        self._monitor_thread.start()

    def _viewer_generation_is_live(self) -> bool:
        with self._state_lock:
            process = self._process
            physical_generation = self._physical_generation_token
            accepted_generation = self._accepted_physical_generation_token
        return bool(
            process is not None
            and physical_generation > 0
            and accepted_generation == physical_generation
            and process.poll() is None
        )

    def _verify_runtime_available(self, python_executable: str) -> None:
        try:
            result = subprocess.run(
                [python_executable, "-c", self._RUNTIME_IMPORT_CHECK],
                capture_output=True,
                check=False,
                text=True,
                timeout=10.0,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Configured Python executable timed out while checking "
                "for the COREX runtime package."
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"Failed to launch configured Python executable: {str(exc)[:1200]}"
            ) from exc
        if result.returncode != 0:
            stderr_tail = (result.stderr or result.stdout or "").strip()[-1200:]
            detail = f" Details: {stderr_tail}" if stderr_tail else ""
            raise RuntimeError(
                "Configured Python executable cannot import "
                "ea_node_editor.execution.stdio_worker. Install a compatible "
                "COREX runtime package in that environment, or use Workflow "
                "Settings > Environment > Create / Repair Managed Runtime to create a "
                f"managed environment.{detail}"
            )

    def _process_start_required(
        self,
        python_executable: str,
        registry_contract_fingerprint: str,
    ) -> bool:
        with self._state_lock:
            process = self._process
            current_python = self._python_executable
            pinned_contract = self._registry_contract_generation_fingerprint
        return bool(
            process is None
            or process.poll() is not None
            or current_python != python_executable
            or (
                pinned_contract
                and pinned_contract != str(registry_contract_fingerprint)
            )
        )

    def _assert_process_transition_allowed(self) -> None:
        with self._state_lock:
            process = self._process
        if process is None or process.poll() is not None:
            return
        with self._viewer_request_lock:
            if self._pending_viewer_requests or self._viewer_session_ids:
                raise RuntimeError(
                    "Cannot replace the external Python worker while viewer "
                    "requests or sessions remain active."
                )

    def _ensure_process(self, python_executable: str) -> None:
        normalized_python = str(python_executable or "").strip()
        if not normalized_python:
            raise RuntimeError("External Python execution requires python_executable.")
        with self._start_lock:
            with self._state_lock:
                process = self._process
                current_python = self._python_executable
                physical_generation = self._physical_generation_token
            if (
                process is not None
                and process.poll() is None
                and current_python == normalized_python
            ):
                return
            if process is not None and process.poll() is None:
                with self._state_lock:
                    with self._viewer_request_lock:
                        if self._pending_viewer_requests or self._viewer_session_ids:
                            raise RuntimeError(
                                "Cannot replace the external Python worker while "
                                "viewer requests or sessions remain active."
                            )
                        retiring_generation = self._physical_generation_token
                        self._accepted_physical_generation_token = -1
                try:
                    self._stop_external_process(process, graceful=True)
                except Exception:
                    self._restore_physical_generation(retiring_generation)
                    raise
            else:
                if process is not None:
                    self._check_worker_health_locked()
                retiring_generation = self._invalidate_physical_generation()
                try:
                    if physical_generation > 0:
                        self._drop_stale_viewer_generation(
                            "The external Python worker generation ended before "
                            "the viewer request completed."
                        )
                    self._retire_external_resources(process)
                except Exception:
                    self._restore_physical_generation(retiring_generation)
                    raise

            from ea_node_editor.execution.managed_runtime import (
                ADDON_RUNTIME_PYTHON_ENV,
                resolve_addon_runtime_paths,
            )

            worker_environment = os.environ.copy()
            worker_environment[ADDON_RUNTIME_PYTHON_ENV] = str(
                resolve_addon_runtime_paths().python_executable
            )
            try:
                new_process = subprocess.Popen(
                    [
                        normalized_python,
                        "-u",
                        "-m",
                        "ea_node_editor.execution.stdio_worker",
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=worker_environment,
                )
            except OSError as exc:
                raise RuntimeError(
                    "Failed to start external Python workflow worker: "
                    f"{str(exc)[:1200]}"
                ) from exc
            generation_token = self._install_physical_generation()
            stdout_thread = threading.Thread(
                target=self._stdout_listener,
                args=(new_process, generation_token),
                daemon=True,
                name="external-python-stdout-listener",
            )
            stderr_thread = threading.Thread(
                target=self._stderr_listener,
                args=(new_process, generation_token),
                daemon=True,
                name="external-python-stderr-listener",
            )
            with self._state_lock:
                self._process = new_process
                self._python_executable = normalized_python
                self._stderr_tail.clear()
                self._stdout_thread = stdout_thread
                self._stderr_thread = stderr_thread
            stdout_thread.start()
            stderr_thread.start()

    def _recycle_catalog_generation(self) -> None:
        with self._start_lock:
            with self._state_lock:
                process = self._process
                with self._viewer_request_lock:
                    if self._pending_viewer_requests or self._viewer_session_ids:
                        raise DataTypeCatalogError(
                            "Cannot recycle the external Python worker while "
                            "viewer requests or sessions remain active."
                        )
                    retiring_generation = self._physical_generation_token
                    self._accepted_physical_generation_token = -1
            try:
                self._stop_external_process(process, graceful=True)
            except Exception:
                self._restore_physical_generation(retiring_generation)
                raise

    def _try_post_command(self, command: WorkerCommand) -> tuple[bool, str]:
        try:
            payload = self._encode_command(command)
            line = json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n"
            with self._stdin_lock:
                process = self._process
                if (
                    process is None
                    or process.poll() is not None
                    or process.stdin is None
                ):
                    raise RuntimeError(
                        "External Python workflow worker is not running."
                    )
                process.stdin.write(line)
                process.stdin.flush()
            return True, ""
        except Exception as exc:  # noqa: BLE001
            message = f"Failed to dispatch command to external Python worker: {exc}"
            self._emit_protocol_error(
                message,
                run_id=getattr(command, "run_id", ""),
                request_id=getattr(command, "request_id", ""),
                command=getattr(command, "type", ""),
            )
            return False, message

    def _post_command(self, command: WorkerCommand) -> bool:
        success, _message = self._try_post_command(command)
        return success

    def retire_workspace(self, workspace_id: str) -> int:
        with self._state_lock:
            process = self._process
        if (
            process is None
            or process.poll() is not None
            or not isinstance(getattr(process, "pid", None), int)
        ):
            return 0
        return self._retire_workspace_via_transport(workspace_id)

    def _encode_run_preflight_command(self, command: WorkerCommand) -> str:
        payload = self._encode_command(command)
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n"

    def _pin_run_preflight_transport_locked(self) -> subprocess.Popen | None:
        return self._process

    def _deliver_encoded_run_preflight_command(
        self, payload: str, transport: subprocess.Popen | None
    ) -> tuple[bool, str]:
        try:
            with self._stdin_lock:
                if (
                    transport is None
                    or transport.poll() is not None
                    or transport.stdin is None
                ):
                    raise RuntimeError(
                        "External Python workflow worker is not running."
                    )
                transport.stdin.write(payload)
                transport.stdin.flush()
            return True, ""
        except Exception as exc:  # noqa: BLE001
            return False, str(exc) or "Failed to deliver run preflight command."

    @_registry_admitted
    def start_run(
        self,
        project_path: str,
        workspace_id: str,
        trigger: dict[str, Any] | None = None,
        *,
        execution_backend: ExecutionBackendSelection | dict[str, Any] | None = None,
        target_node_ids: tuple[str, ...] | list[str] | None = None,
        trigger_publications: dict[str, SettledPortResult] | None = None,
        trigger_captures: dict[str, SettledPortResult] | None = None,
        clicked_trigger_node_id: str = "",
        data_types: DataTypeCatalog | None = None,
        plugin_bundles: tuple[PluginBundleRef, ...] = (),
        plugin_fingerprint: str = EMPTY_PLUGIN_FINGERPRINT,
        registry_contract_fingerprint: str = EMPTY_REGISTRY_CONTRACT_FINGERPRINT,
        addon_runtime_config: tuple[tuple[str, bool], ...] = (),
        _reserved_run_id: str = "",
        _reservation_prepared: bool = False,
        _prepared_command: StartRunCommand | None = None,
    ) -> str:
        trigger_payload = dict(trigger or {})
        run_id = _reserved_run_id or f"run_{uuid.uuid4().hex[:8]}"
        runtime_snapshot = trigger_payload.pop("runtime_snapshot", None)
        command_target_node_ids = trigger_payload.pop(
            "target_node_ids", target_node_ids or ()
        )
        command_trigger_publications = trigger_payload.pop(
            "trigger_publications", trigger_publications or {}
        )
        command_trigger_captures = trigger_payload.pop(
            "trigger_captures", trigger_captures or {}
        )
        command_clicked_trigger_node_id = trigger_payload.pop(
            "clicked_trigger_node_id", clicked_trigger_node_id
        )
        command_developer_mode = trigger_payload.pop("developer_mode", False)
        selection = coerce_execution_backend_selection(execution_backend)
        python_executable = str(selection.python_executable or "").strip()
        if not python_executable:
            self._emit_protocol_error(
                "External Python workflow execution requires python_executable.",
                run_id=run_id,
                command="start_run",
            )
            return ""
        with self._start_lock:
            with self._state_lock:
                active_run = bool(self._active_run_id)
            if active_run and not _reservation_prepared:
                self._emit_protocol_error(
                    "External Python worker already has an active run.",
                    run_id=run_id,
                    command="start_run",
                )
                return ""
            try:
                if self._process_start_required(
                    python_executable,
                    registry_contract_fingerprint,
                ):
                    self._assert_process_transition_allowed()
                    self._verify_runtime_available(python_executable)
                prepared_start = _reservation_prepared or self._prepare_start_run(
                    run_id,
                    workspace_id,
                    data_types,
                    plugin_bundles,
                    plugin_fingerprint,
                    registry_contract_fingerprint,
                    addon_runtime_config,
                )
            except (RuntimeError, TypeError, ValueError) as exc:
                self._emit_protocol_error(str(exc), run_id=run_id, command="start_run")
                return ""
            if not prepared_start:
                self._emit_protocol_error(
                    "External Python worker already has an active run.",
                    run_id=run_id,
                    command="start_run",
                )
                return ""
            try:
                catalog_fingerprint, catalog_revisions = self._catalog_agreement()
                (
                    command_plugin_bundles,
                    command_plugin_fingerprint,
                    runtime_fingerprint,
                ) = self._plugin_agreement()
                contract_fingerprint, command_addon_runtime_config = (
                    self._registry_contract_agreement()
                )
                command_source: StartRunCommand | dict[str, Any] = (
                    _prepared_command
                    if _prepared_command is not None
                    else {
                        "run_id": run_id,
                        "project_path": project_path,
                        "workspace_id": workspace_id,
                        "trigger": trigger_payload,
                        "runtime_snapshot": runtime_snapshot,
                        "execution_backend": selection.to_payload(),
                        "target_node_ids": command_target_node_ids,
                        "trigger_publications": command_trigger_publications,
                        "trigger_captures": command_trigger_captures,
                        "clicked_trigger_node_id": command_clicked_trigger_node_id,
                        "developer_mode": command_developer_mode,
                        "catalog_fingerprint": catalog_fingerprint,
                        "catalog_revisions": catalog_revisions,
                        "plugin_bundles": command_plugin_bundles,
                        "plugin_fingerprint": command_plugin_fingerprint,
                        "runtime_registry_fingerprint": runtime_fingerprint,
                        "registry_contract_fingerprint": contract_fingerprint,
                        "addon_runtime_config": command_addon_runtime_config,
                    }
                )
                command = coerce_start_run_command(
                    command_source,
                    catalog=self._data_types,
                )
                if (
                    command.run_id != run_id
                    or command.workspace_id != workspace_id
                    or command.execution_backend != selection
                ):
                    raise ValueError(
                        "prepared command does not match reserved external run"
                    )
            except (TypeError, ValueError) as exc:
                self._release_start_run(run_id)
                self._emit_protocol_error(str(exc), run_id=run_id, command="start_run")
                return ""
            try:
                self._ensure_process(python_executable)
            except RuntimeError as exc:
                self._release_start_run(run_id)
                self._emit_protocol_error(str(exc), run_id=run_id, command="start_run")
                return ""

            with self._state_lock:
                self._script_timeout_by_node_id = _python_script_timeout_by_node_id(
                    command.runtime_snapshot,
                    workspace_id,
                )
                self._clear_active_node_state_locked()
            if not self._post_command(command):
                self._release_start_run(run_id)
                return ""
            self._mark_start_run_dispatched(run_id)
        return run_id

    def _send_viewer_command(
        self,
        command: WorkerCommand,
        *,
        require_session_id: bool = False,
    ) -> str:
        with self._start_lock:
            with self._state_lock:
                python_executable = self._python_executable
            try:
                if python_executable:
                    self._ensure_process(python_executable)
                workspace_epoch, node_epoch = self._viewer_epochs(
                    str(getattr(command, "workspace_id", "")),
                    str(getattr(command, "node_id", "")),
                )
                command = replace(
                    command,
                    workspace_invalidation_epoch=workspace_epoch,
                    node_invalidation_epoch=node_epoch,
                )
                command = self._decode_command(self._encode_command(command))
            except (RuntimeError, TypeError, ValueError) as exc:
                pending = self._pending_viewer_request(command)
                self._dispatch_viewer_request_failure(pending, str(exc))
                return pending.request_id
            request_id = str(getattr(command, "request_id", ""))
            pending = self._pending_viewer_request(command)
            if require_session_id and not pending.session_id:
                self._dispatch_viewer_request_failure(
                    pending, "session_id is required."
                )
                return request_id
            self._track_viewer_request(pending)
            if not self._post_command(command):
                self._complete_viewer_request(request_id)
                self._dispatch_viewer_request_failure(
                    pending, "Failed to dispatch command."
                )
        return request_id

    def _stdout_listener(
        self,
        process: subprocess.Popen,
        generation_token: int,
    ) -> None:
        stdout = process.stdout
        if stdout is None:
            return
        while self._running:
            try:
                line = stdout.readline()
            except OSError:
                return
            if line == "":
                return
            self._handle_stdout_line(
                line,
                generation_token=generation_token,
            )

    def _stderr_listener(
        self,
        process: subprocess.Popen,
        generation_token: int,
    ) -> None:
        stderr = process.stderr
        if stderr is None:
            return
        while self._running:
            try:
                line = stderr.readline()
            except OSError:
                return
            if line == "":
                return
            text = line.strip()
            if text and self._source_generation_is_current(generation_token):
                with self._state_lock:
                    self._stderr_tail.append(text)

    def _handle_stdout_line(
        self,
        line: str,
        *,
        generation_token: int | None = None,
    ) -> None:
        source_generation = (
            self._catalog_generation_token_value()
            if generation_token is None
            else int(generation_token)
        )
        if not self._source_generation_is_current(source_generation):
            return
        text = line.strip()
        if not text:
            return
        try:
            event = json.loads(text)
        except json.JSONDecodeError as exc:
            if self._source_generation_is_current(source_generation):
                self._emit_protocol_error(
                    f"Received invalid JSON event from external Python worker: {exc}"
                )
            return
        if not isinstance(event, dict):
            if self._source_generation_is_current(source_generation):
                self._emit_protocol_error(
                    "Received non-dictionary event from external Python worker."
                )
            return
        try:
            typed_event = self._decode_event(dict(event))
        except (TypeError, ValueError) as exc:
            if self._source_generation_is_current(source_generation):
                self._emit_protocol_error(
                    f"Received invalid external Python worker event: {exc}"
                )
            return

        if not self._source_generation_is_current(source_generation):
            return
        payload = event_to_dict(typed_event, catalog=self._data_types)
        event_type = payload.get("type", "")
        event_run_id = payload.get("run_id", "")
        viewer_failure_event = None
        if event_type == "protocol_error":
            viewer_failure_event = self._viewer_protocol_error_failure(
                payload,
                expected_generation_token=source_generation,
            )
        elif event_type in VIEWER_RESPONSE_EVENT_TYPES:
            response_generation = self._record_viewer_response_state(
                payload,
                default_generation_token=source_generation,
                expected_generation_token=source_generation,
            )
            if response_generation != source_generation:
                return
        self._record_execution_event_state(
            payload,
            expected_generation_token=source_generation,
        )
        if not self._source_generation_is_current(source_generation):
            return
        self._dispatch_event(
            typed_event,
            generation_token=source_generation,
        )
        if viewer_failure_event is not None:
            self._dispatch_event(
                viewer_failure_event,
                generation_token=source_generation,
            )

        if event_type in self._TERMINAL_EVENT_TYPES:
            with self._state_lock:
                if self._accepted_physical_generation_token == source_generation and (
                    not self._active_run_id or self._active_run_id == event_run_id
                ):
                    self._clear_active_run_state_locked()

    def _stderr_tail_text(self) -> str:
        with self._state_lock:
            return "\n".join(self._stderr_tail)[-2000:]

    def _monitor_loop(self) -> None:
        while self._running:
            self._check_worker_health()
            time.sleep(0.2)

    def _check_worker_health(self) -> None:
        with self._start_lock:
            self._check_worker_health_locked()

    def _check_worker_health_locked(self) -> None:
        with self._state_lock:
            process = self._process
            generation_token = self._physical_generation_token
            if (
                process is not None
                and self._accepted_physical_generation_token != generation_token
            ):
                return
            active_run_id = self._active_run_id
            if active_run_id and self._start_run_pending_id == active_run_id:
                return
            workspace_id = self._active_workspace_id
            active_node_id = self._active_node_id
            active_deadline = self._active_node_deadline
            active_timeout_sec = self._active_node_timeout_sec
        if process is None:
            return
        if process.poll() is None:
            if (
                active_run_id
                and active_node_id
                and active_deadline > 0.0
                and time.monotonic() >= active_deadline
            ):
                self._terminate_timed_out_worker(
                    process,
                    run_id=active_run_id,
                    workspace_id=workspace_id,
                    node_id=active_node_id,
                    timeout_sec=active_timeout_sec,
                    generation_token=generation_token,
                )
            return

        self._fail_workspace_retirements(
            "External Python workflow worker terminated unexpectedly"
        )

        with self._state_lock:
            if (
                self._process is not process
                or self._physical_generation_token != generation_token
                or self._accepted_physical_generation_token != generation_token
            ):
                return
            run_id = self._active_run_id
            run_workspace = self._active_workspace_id
            failed_node_id = self._active_node_id
            self._accepted_physical_generation_token = -1
            self._clear_active_run_state_locked()

        self._notify_generation_change(
            reason="external_python_worker_terminated",
            generation_token=generation_token,
        )

        if active_run_id and run_id == active_run_id:
            stderr_tail = self._stderr_tail_text()
            detail = f"\n{stderr_tail}" if stderr_tail else ""
            self._dispatch_event(
                RunFailedEvent(
                    run_id=active_run_id,
                    workspace_id=workspace_id or run_workspace,
                    node_id=failed_node_id,
                    error="External Python workflow worker terminated unexpectedly.",
                    traceback=detail,
                    fatal=True,
                ),
                generation_token=generation_token,
            )
            self._dispatch_event(
                RunStateEvent(
                    run_id=active_run_id,
                    workspace_id=workspace_id or run_workspace,
                    state="error",
                    transition="fail",
                    reason="external_python_worker_terminated",
                ),
                generation_token=generation_token,
            )

    def _terminate_timed_out_worker(
        self,
        process: subprocess.Popen,
        *,
        run_id: str,
        workspace_id: str,
        node_id: str,
        timeout_sec: float,
        generation_token: int,
    ) -> None:
        with self._state_lock:
            if (
                self._active_run_id != run_id
                or self._process is not process
                or self._physical_generation_token != generation_token
                or self._accepted_physical_generation_token != generation_token
            ):
                return
            self._accepted_physical_generation_token = -1
        try:
            self._terminate_process(process)
        except RuntimeError as exc:
            self._restore_physical_generation(generation_token)
            self._emit_protocol_error(
                f"Failed to terminate timed-out external Python worker: {exc}",
                run_id=run_id,
                command="start_run",
            )
            return
        with self._state_lock:
            if (
                self._active_run_id != run_id
                or self._process is not process
                or self._physical_generation_token != generation_token
                or self._accepted_physical_generation_token != -1
            ):
                return
            run_workspace = self._active_workspace_id
            self._clear_active_run_state_locked()

        error = f"Python Script timed out after {timeout_sec:.2f} seconds."
        self._dispatch_event(
            RunFailedEvent(
                run_id=run_id,
                workspace_id=workspace_id or run_workspace,
                node_id=node_id,
                error=error,
                traceback="",
                fatal=True,
            ),
            generation_token=generation_token,
        )
        self._dispatch_event(
            RunStateEvent(
                run_id=run_id,
                workspace_id=workspace_id or run_workspace,
                state="error",
                transition="fail",
                reason="python_script_timeout",
            ),
            generation_token=generation_token,
        )

    def _terminate_process(self, process: subprocess.Popen) -> None:
        try:
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except OSError:
                    pass
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=0.5)
        except Exception as exc:
            raise RuntimeError(
                "the external Python worker could not be terminated"
            ) from exc
        if process.poll() is None:
            raise RuntimeError("the external Python worker did not terminate")

    def _retire_external_resources(
        self,
        process: subprocess.Popen | None,
    ) -> None:
        if process is not None and process.poll() is None:
            raise RuntimeError("cannot retire a live external Python worker")
        with self._state_lock:
            stdout_thread = self._stdout_thread
            stderr_thread = self._stderr_thread
        for thread in (stdout_thread, stderr_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.0)
        if any(
            thread is not None and thread.is_alive()
            for thread in (stdout_thread, stderr_thread)
        ):
            raise RuntimeError("the external Python worker listeners did not terminate")
        with self._state_lock:
            if self._process is process:
                self._process = None
            if self._stdout_thread is stdout_thread:
                self._stdout_thread = None
            if self._stderr_thread is stderr_thread:
                self._stderr_thread = None

    def _stop_external_process(
        self,
        process: subprocess.Popen | None,
        *,
        graceful: bool,
    ) -> None:
        retiring_generation = self._invalidate_physical_generation()
        try:
            if process is None:
                self._retire_external_resources(None)
                return
            if process.poll() is None and graceful:
                self._post_command(ShutdownCommand())
                try:
                    process.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    self._terminate_process(process)
            elif process.poll() is None:
                self._terminate_process(process)
            if process.poll() is None:
                raise RuntimeError(
                    "the previous external Python worker did not terminate"
                )
            self._retire_external_resources(process)
        except Exception:
            self._restore_physical_generation(retiring_generation)
            raise

    def shutdown(self) -> None:
        with self._start_lock:
            with self._state_lock:
                process = self._process
                self._clear_active_run_state_locked()
            try:
                self._stop_external_process(process, graceful=True)
            except RuntimeError:
                pass
            self._running = False
        with self._viewer_request_lock:
            self._pending_viewer_requests.clear()
            self._viewer_session_ids.clear()
            self._viewer_session_generations.clear()
            self._viewer_session_node_ids.clear()
        for thread in (self._stdout_thread, self._stderr_thread, self._monitor_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.0)
