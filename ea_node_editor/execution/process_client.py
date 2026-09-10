# Purpose: Multiprocessing execution transport lifecycle and queue delivery.
# Map: subsystems/execution.md
# Tests: tests/test_process_client.py
# Landmarks: ProcessExecutionClient
from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from ea_node_editor.execution.backends import (
    ExecutionBackendSelection,
    coerce_execution_backend_selection,
)
from ea_node_editor.execution.client_common import (
    _LISTENER_SHUTDOWN_SENTINEL,
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
from ea_node_editor.execution.worker import worker_main
from ea_node_editor.nodes.function_plugin import (
    EMPTY_PLUGIN_FINGERPRINT,
    PluginBundleRef,
)
from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    DataTypeCatalogError,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult


class ProcessExecutionClient(_ExecutionClientCommon):
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
        self._physical_generation_run_dispatched = False
        self._run_generation_tokens: dict[str, int] = {}
        self._ctx = mp.get_context("spawn")
        self._command_queue: mp.Queue = self._ctx.Queue()
        self._event_queue: mp.Queue = self._ctx.Queue()
        self._process: mp.Process | None = None
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
        self._listener_thread = threading.Thread(
            target=self._event_listener,
            args=(self._event_queue, None, 0),
            daemon=True,
            name="execution-event-listener",
        )
        self._running = True
        self._listener_thread.start()

    def _viewer_generation_is_live(self) -> bool:
        with self._state_lock:
            process = self._process
            physical_generation = self._physical_generation_token
            accepted_generation = self._accepted_physical_generation_token
        return bool(
            process is not None
            and physical_generation > 0
            and accepted_generation == physical_generation
            and process.is_alive()
        )

    def _ensure_process(self) -> None:
        with self._start_lock:
            with self._state_lock:
                process = self._process
                physical_generation = self._physical_generation_token
            if process is not None and process.is_alive():
                return
            if process is not None:
                self._check_worker_health(process, physical_generation)
            retiring_generation = self._invalidate_physical_generation()
            try:
                if physical_generation > 0:
                    self._drop_stale_viewer_generation(
                        "The execution worker generation ended before the viewer "
                        "request completed."
                    )
                if process is not None:
                    process.join(timeout=0.1)
                self._retire_process_resources(process)
            except Exception:
                self._restore_physical_generation(retiring_generation)
                raise

            command_queue = self._ctx.Queue()
            event_queue = self._ctx.Queue()
            new_process = self._ctx.Process(
                target=worker_main,
                args=(command_queue, event_queue),
                daemon=True,
                name="ea-node-exec-worker",
            )
            try:
                new_process.start()
            except Exception:
                self._close_queue(command_queue)
                self._close_queue(event_queue)
                raise
            generation_token = self._install_physical_generation()
            listener_thread = threading.Thread(
                target=self._event_listener,
                args=(event_queue, new_process, generation_token),
                daemon=True,
                name="execution-event-listener",
            )
            with self._state_lock:
                self._command_queue = command_queue
                self._event_queue = event_queue
                self._process = new_process
                self._listener_thread = listener_thread
                self._physical_generation_run_dispatched = False
            listener_thread.start()

    def _recycle_catalog_generation(self) -> None:
        with self._start_lock:
            with self._state_lock:
                process = self._process
                with self._viewer_request_lock:
                    if self._pending_viewer_requests or self._viewer_session_ids:
                        raise DataTypeCatalogError(
                            "Cannot recycle the execution worker while viewer "
                            "requests or sessions remain active."
                        )
                    retiring_generation = self._physical_generation_token
                    self._accepted_physical_generation_token = -1
            try:
                if process is not None and process.is_alive():
                    self._post_command(ShutdownCommand())
                    process.join(timeout=1.5)
                if process is not None and process.is_alive():
                    process.terminate()
                    process.join(timeout=0.5)
                if process is not None and process.is_alive():
                    try:
                        process.kill()
                        process.join(timeout=0.5)
                    except Exception:
                        pass
                if process is not None and process.is_alive():
                    raise DataTypeCatalogError(
                        "the previous execution worker did not terminate"
                    )
                self._retire_process_resources(process)
            except Exception:
                self._restore_physical_generation(retiring_generation)
                raise

    def _try_post_command(self, command: WorkerCommand) -> tuple[bool, str]:
        try:
            payload = self._encode_command(command)
            with self._state_lock:
                command_queue = self._command_queue
            if command_queue is None:
                raise RuntimeError("Execution worker is not running.")
            command_queue.put(payload)
            return True, ""
        except Exception as exc:  # noqa: BLE001
            message = f"Failed to dispatch command: {exc}"
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
        with self._start_lock:
            with self._state_lock:
                process = self._process
                run_dispatched = self._physical_generation_run_dispatched
            # A generation that has never received StartRun cannot own sessions.
            if (
                process is None
                or not process.is_alive()
                or not isinstance(getattr(process, "pid", None), int)
                or not run_dispatched
            ):
                return 0
            return self._retire_workspace_via_transport(workspace_id)

    def _encode_run_preflight_command(self, command: WorkerCommand) -> dict[str, Any]:
        return self._encode_command(command)

    def _pin_run_preflight_transport_locked(self) -> mp.Queue | None:
        return self._command_queue

    @staticmethod
    def _deliver_encoded_run_preflight_command(
        payload: dict[str, Any], transport: mp.Queue | None
    ) -> tuple[bool, str]:
        try:
            if transport is None:
                raise RuntimeError("Execution worker is not running.")
            transport.put(payload)
            return True, ""
        except Exception as exc:  # noqa: BLE001
            return False, str(exc) or "Failed to deliver run preflight command."

    def _send_viewer_command(
        self,
        command: WorkerCommand,
        *,
        require_session_id: bool = False,
    ) -> str:
        with self._start_lock:
            try:
                self._ensure_process()
            except Exception as exc:  # noqa: BLE001
                pending = self._pending_viewer_request(command)
                self._dispatch_viewer_request_failure(
                    pending,
                    f"Failed to start worker process: {exc}",
                )
                return pending.request_id
            workspace_epoch, node_epoch = self._viewer_epochs(
                str(getattr(command, "workspace_id", "")),
                str(getattr(command, "node_id", "")),
            )
            command = replace(
                command,
                workspace_invalidation_epoch=workspace_epoch,
                node_invalidation_epoch=node_epoch,
            )
            try:
                command = self._decode_command(self._encode_command(command))
            except (TypeError, ValueError) as exc:
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
            success, error_message = self._try_post_command(command)
            if not success:
                self._complete_viewer_request(request_id)
                self._dispatch_viewer_request_failure(pending, error_message)
        return request_id

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
        try:
            prepared_start = _reservation_prepared or self._prepare_start_run(
                run_id,
                workspace_id,
                data_types,
                plugin_bundles,
                plugin_fingerprint,
                registry_contract_fingerprint,
                addon_runtime_config,
            )
        except (TypeError, ValueError) as exc:
            self._emit_protocol_error(str(exc), run_id=run_id, command="start_run")
            return ""
        if not prepared_start:
            self._emit_protocol_error(
                "Execution worker already has an active run.",
                run_id=run_id,
                command="start_run",
            )
            return ""
        try:
            catalog_fingerprint, catalog_revisions = self._catalog_agreement()
            command_plugin_bundles, command_plugin_fingerprint, runtime_fingerprint = (
                self._plugin_agreement()
            )
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
                raise ValueError("prepared command does not match reserved process run")
        except (TypeError, ValueError) as exc:
            self._release_start_run(run_id)
            self._emit_protocol_error(str(exc), run_id=run_id, command="start_run")
            return ""

        with self._start_lock:
            try:
                self._ensure_process()
            except Exception as exc:  # noqa: BLE001
                self._release_start_run(run_id)
                self._emit_protocol_error(
                    f"Failed to start worker process: {exc}", command="start_run"
                )
                return ""
            with self._state_lock:
                self._script_timeout_by_node_id = _python_script_timeout_by_node_id(
                    command.runtime_snapshot,
                    workspace_id,
                )
                self._clear_active_node_state_locked()
                self._physical_generation_run_dispatched = True
            if not self._post_command(command):
                self._release_start_run(run_id)
                return ""
            self._mark_start_run_dispatched(run_id)
        return run_id

    def shutdown(self) -> None:
        with self._start_lock:
            with self._state_lock:
                process = self._process
                self._clear_active_run_state_locked()
            self._invalidate_physical_generation()
            if process and process.is_alive():
                self._post_command(ShutdownCommand())
                process.join(timeout=1.5)
            if process and process.is_alive():
                process.terminate()
                process.join(timeout=0.5)
            if process and process.is_alive():
                try:
                    process.kill()
                    process.join(timeout=0.5)
                except Exception:
                    pass
            self._running = False
            if process is None or not process.is_alive():
                self._retire_process_resources(process)
        with self._viewer_request_lock:
            self._pending_viewer_requests.clear()
            self._viewer_session_ids.clear()
            self._viewer_session_generations.clear()
            self._viewer_session_node_ids.clear()

    def _check_worker_health(
        self,
        process: mp.Process | None,
        generation_token: int,
    ) -> None:
        with self._state_lock:
            if (
                process is None
                or self._process is not process
                or self._physical_generation_token != generation_token
                or self._accepted_physical_generation_token != generation_token
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
        if process.is_alive():
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

        process.join(timeout=0.1)
        self._fail_workspace_retirements("Execution worker terminated unexpectedly")
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
            reason="worker_terminated",
            generation_token=generation_token,
        )

        if active_run_id and run_id == active_run_id:
            self._dispatch_event(
                RunFailedEvent(
                    run_id=active_run_id,
                    workspace_id=workspace_id or run_workspace,
                    node_id=failed_node_id,
                    error="Execution worker terminated unexpectedly.",
                    traceback="",
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
                    reason="worker_terminated",
                ),
                generation_token=generation_token,
            )

    def _terminate_timed_out_worker(
        self,
        process: mp.Process,
        *,
        run_id: str,
        workspace_id: str,
        node_id: str,
        timeout_sec: float,
        generation_token: int,
    ) -> None:
        with self._start_lock:
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
                process.terminate()
                process.join(timeout=1.0)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=0.5)
            except Exception:
                pass
            if process.is_alive():
                self._restore_physical_generation(generation_token)
                self._emit_protocol_error(
                    "Failed to terminate timed-out execution worker.",
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

    def _event_listener(
        self,
        event_queue: mp.Queue,
        process: mp.Process | None,
        generation_token: int,
    ) -> None:
        while self._running:
            try:
                event = event_queue.get(timeout=0.2)
            except queue.Empty:
                self._check_worker_health(process, generation_token)
                continue
            except (EOFError, OSError):
                self._fail_workspace_retirements("Execution worker transport closed")
                self._check_worker_health(process, generation_token)
                continue

            if event == _LISTENER_SHUTDOWN_SENTINEL:
                break
            if not self._source_generation_is_current(generation_token):
                continue
            if not isinstance(event, dict):
                self._emit_protocol_error("Received non-dictionary event from worker.")
                continue

            try:
                typed_event = self._decode_event(dict(event))
            except (TypeError, ValueError) as exc:
                if self._source_generation_is_current(generation_token):
                    self._emit_protocol_error(f"Received invalid worker event: {exc}")
                continue

            if not self._source_generation_is_current(generation_token):
                continue
            payload = event_to_dict(typed_event, catalog=self._data_types)
            event_type = payload.get("type", "")
            event_run_id = payload.get("run_id", "")
            viewer_failure_event = None
            if event_type == "protocol_error":
                viewer_failure_event = self._viewer_protocol_error_failure(
                    payload,
                    expected_generation_token=generation_token,
                )
            elif event_type in VIEWER_RESPONSE_EVENT_TYPES:
                response_generation = self._record_viewer_response_state(
                    payload,
                    default_generation_token=generation_token,
                    expected_generation_token=generation_token,
                )
                if response_generation != generation_token:
                    continue
            self._record_execution_event_state(
                payload,
                expected_generation_token=generation_token,
            )
            if not self._source_generation_is_current(generation_token):
                continue
            self._dispatch_event(
                typed_event,
                generation_token=generation_token,
            )
            if viewer_failure_event is not None:
                self._dispatch_event(
                    viewer_failure_event,
                    generation_token=generation_token,
                )

            if event_type in self._TERMINAL_EVENT_TYPES:
                with self._state_lock:
                    if (
                        self._accepted_physical_generation_token == generation_token
                        and (
                            not self._active_run_id
                            or self._active_run_id == event_run_id
                        )
                    ):
                        self._clear_active_run_state_locked()

    def _retire_process_resources(self, process: mp.Process | None) -> None:
        with self._state_lock:
            command_queue = self._command_queue
            event_queue = self._event_queue
            listener_thread = self._listener_thread
        try:
            event_queue.put_nowait(dict(_LISTENER_SHUTDOWN_SENTINEL))
        except Exception:
            pass
        if listener_thread is not None and listener_thread.is_alive():
            listener_thread.join(timeout=1.0)
        if listener_thread is not None and listener_thread.is_alive():
            raise DataTypeCatalogError(
                "the previous execution worker listener did not terminate"
            )
        self._close_queue(command_queue)
        self._close_queue(event_queue)
        with self._state_lock:
            if self._process is process:
                self._process = None
            if self._command_queue is command_queue:
                self._command_queue = None
            if self._event_queue is event_queue:
                self._event_queue = None
            if self._listener_thread is listener_thread:
                self._listener_thread = None

    @staticmethod
    def _close_queue(queue_obj: mp.Queue | None) -> None:
        if queue_obj is None:
            return
        try:
            queue_obj.close()
        except Exception:
            pass
        try:
            queue_obj.join_thread()
        except Exception:
            pass
