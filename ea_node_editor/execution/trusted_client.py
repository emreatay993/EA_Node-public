# Purpose: Trusted in-process execution thread, queue, and worker-service lifecycle.
# Map: subsystems/execution.md
# Tests: tests/test_trusted_client.py
# Landmarks: TrustedInProcessExecutionClient
from __future__ import annotations

import queue
import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from ea_node_editor.execution.backends import (
    TRUSTED_IN_PROCESS_BACKEND,
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
from ea_node_editor.execution.worker import run_workflow
from ea_node_editor.execution.worker_protocol import dispatch_viewer_command
from ea_node_editor.execution.worker_runtime import (
    DEFAULT_RUNTIME_PREPARATION_CACHE,
)
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.nodes.function_plugin import (
    EMPTY_PLUGIN_FINGERPRINT,
    INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    PluginBundleRef,
)
from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    DataTypeCatalogError,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult


@dataclass(frozen=True)
class _GenerationTaggedEventSink:
    event_queue: queue.Queue[Any]
    generation_token: int

    def put(self, event: Any) -> None:
        self.event_queue.put((self.generation_token, event))


class TrustedInProcessExecutionClient(_ExecutionClientCommon):
    def __init__(self, *, worker_services: WorkerServices | None = None) -> None:
        self._data_types: DataTypeCatalog | None = None
        self._catalog_generation_fingerprint = ""
        self._plugin_bundles: tuple[PluginBundleRef, ...] = ()
        self._plugin_fingerprint = EMPTY_PLUGIN_FINGERPRINT
        self._runtime_registry_generation_fingerprint = ""
        self._registry_contract_generation_fingerprint = ""
        self._addon_runtime_config: tuple[tuple[str, bool], ...] = ()
        self._catalog_generation_token = 0
        self._accepted_physical_generation_token = 0
        self._run_generation_tokens: dict[str, int] = {}
        self._command_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._event_queue: queue.Queue[Any] = queue.Queue()
        self._worker_services = worker_services or WorkerServices()
        self._run_thread: threading.Thread | None = None
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
            daemon=True,
            name="trusted-execution-event-listener",
        )
        self._running = True
        self._listener_thread.start()

    def _post_command(self, command: WorkerCommand) -> bool:
        try:
            self._command_queue.put(self._encode_command(command))
            return True
        except Exception as exc:  # noqa: BLE001
            self._emit_protocol_error(
                f"Failed to dispatch command: {exc}",
                run_id=getattr(command, "run_id", ""),
                request_id=getattr(command, "request_id", ""),
                command=getattr(command, "type", ""),
            )
            return False

    def retire_workspace(self, workspace_id: str) -> int:
        return self._worker_services.mechanical_session_service.retire_workspace(workspace_id)

    def _encode_run_preflight_command(self, command: WorkerCommand) -> dict[str, Any]:
        return self._encode_command(command)

    def _pin_run_preflight_transport_locked(self) -> queue.Queue[dict[str, Any]]:
        return self._command_queue

    @staticmethod
    def _deliver_encoded_run_preflight_command(
        payload: dict[str, Any], transport: queue.Queue[dict[str, Any]]
    ) -> tuple[bool, str]:
        try:
            transport.put(payload)
            return True, ""
        except Exception as exc:  # noqa: BLE001
            return False, str(exc) or "Failed to deliver run preflight command."

    def _drain_command_queue(self) -> None:
        while True:
            try:
                self._command_queue.get_nowait()
            except queue.Empty:
                return

    def _recycle_catalog_generation(self) -> None:
        with self._state_lock:
            run_thread = self._run_thread
            retiring_generation = self._catalog_generation_token
        if run_thread is not None and run_thread.is_alive():
            raise DataTypeCatalogError(
                "trusted worker generation cannot be recycled during an active run"
            )
        with self._state_lock:
            if self._catalog_generation_token == retiring_generation:
                self._accepted_physical_generation_token = -1
        try:
            self._worker_services.reset()
            DEFAULT_RUNTIME_PREPARATION_CACHE.clear()
        except BaseException:
            with self._state_lock:
                if self._catalog_generation_token == retiring_generation:
                    self._accepted_physical_generation_token = retiring_generation
            raise
        with self._state_lock:
            self._run_thread = None

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
        external_function_bundles = tuple(
            bundle
            for bundle in plugin_bundles
            if bundle.owner_id != INTERNAL_BUILTIN_FUNCTION_OWNER_ID
        )
        if external_function_bundles:
            self._emit_protocol_error(
                "External function nodes require process-isolated execution; "
                "trusted in-process execution is unavailable while external "
                "function generations are active.",
                run_id=run_id,
                command="start_run",
            )
            return ""
        selection = coerce_execution_backend_selection(
            execution_backend
            or ExecutionBackendSelection(
                backend_id=TRUSTED_IN_PROCESS_BACKEND,
                isolation="in_process",
                reason="trusted_in_process_opt_in",
                trusted_in_process=True,
            )
        )
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
                "Trusted in-process execution already has an active run.",
                run_id=run_id,
                command="start_run",
            )
            return ""
        with self._state_lock:
            generation_token = self._catalog_generation_token
            self._accepted_physical_generation_token = generation_token
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
                raise ValueError("prepared command does not match reserved trusted run")
            command = self._decode_command(self._encode_command(command))
        except (TypeError, ValueError) as exc:
            self._release_start_run(run_id)
            self._emit_protocol_error(str(exc), run_id=run_id, command="start_run")
            return ""

        script_timeouts = _python_script_timeout_by_node_id(
            command.runtime_snapshot,
            workspace_id,
        )
        if script_timeouts:
            self._release_start_run(run_id)
            self._emit_protocol_error(
                "Python Script timeouts require process-isolated execution; "
                "trusted in-process execution cannot force-stop Python threads.",
                run_id=run_id,
                command="start_run",
            )
            return ""

        try:
            with self._state_lock:
                self._script_timeout_by_node_id = {}
                self._clear_active_node_state_locked()
                self._drain_command_queue()
                self._run_thread = threading.Thread(
                    target=self._run_workflow_thread,
                    args=(command, generation_token),
                    daemon=True,
                    name=f"trusted-execution-{run_id}",
                )
                self._run_thread.start()
                self._start_run_pending_id = ""
        except Exception as exc:  # noqa: BLE001
            self._release_start_run(run_id)
            self._emit_protocol_error(
                f"Failed to start trusted execution thread: {exc}",
                run_id=run_id,
                command="start_run",
            )
            return ""
        return run_id

    def _run_workflow_thread(
        self,
        command,  # noqa: ANN001
        generation_token: int,
    ) -> None:
        event_sink = _GenerationTaggedEventSink(
            self._event_queue,
            generation_token,
        )
        try:
            run_workflow(
                command,
                event_sink,
                command_queue=self._command_queue,
                worker_services=self._worker_services,
            )
        except BaseException as exc:  # noqa: BLE001
            error = str(exc)
            traceback_text = traceback.format_exc()
            with self._start_lock:
                with self._state_lock:
                    if (
                        self._catalog_generation_token != generation_token
                        or self._accepted_physical_generation_token != generation_token
                    ):
                        return
                    failed_node_id = self._active_node_id
                    self._accepted_physical_generation_token = -1
                try:
                    self._worker_services.reset()
                except BaseException as reset_exc:  # noqa: BLE001
                    error = f"{error} (worker reset failed: {reset_exc})"
                with self._state_lock:
                    if self._catalog_generation_token != generation_token:
                        return
                    successor_generation = generation_token + 1
                    self._catalog_generation_token = successor_generation
                    self._accepted_physical_generation_token = successor_generation
                    self._run_generation_tokens.clear()
                    self._run_generation_tokens[command.run_id] = successor_generation
                    self._run_thread = None
                    with self._viewer_request_lock:
                        stale_pending = tuple(
                            pending
                            for pending in self._pending_viewer_requests.values()
                            if pending.generation_token == generation_token
                        )
                        for pending in stale_pending:
                            self._pending_viewer_requests.pop(
                                pending.request_id,
                                None,
                            )
                        stale_session_keys = tuple(
                            session_key
                            for session_key in (
                                self._viewer_session_ids
                                | self._viewer_session_generations.keys()
                            )
                            if self._viewer_session_generations.get(
                                session_key, generation_token
                            )
                            == generation_token
                        )
                        for session_key in stale_session_keys:
                            self._viewer_session_ids.discard(session_key)
                            self._viewer_session_generations.pop(
                                session_key,
                                None,
                            )
                            self._viewer_session_node_ids.pop(session_key, None)
            for pending in stale_pending:
                self._dispatch_viewer_request_failure(
                    pending,
                    "The trusted worker generation reset before the viewer "
                    "request completed.",
                    generation_token=successor_generation,
                )
            successor_sink = _GenerationTaggedEventSink(
                self._event_queue,
                successor_generation,
            )
            successor_sink.put(
                event_to_dict(
                    RunFailedEvent(
                        run_id=command.run_id,
                        workspace_id=command.workspace_id,
                        node_id=failed_node_id,
                        error=error,
                        traceback=traceback_text,
                    ),
                    catalog=self._data_types,
                )
            )
            successor_sink.put(
                event_to_dict(
                    RunStateEvent(
                        run_id=command.run_id,
                        workspace_id=command.workspace_id,
                        state="error",
                        transition="fail",
                        reason="trusted_in_process_exception",
                    ),
                    catalog=self._data_types,
                )
            )

    def _send_viewer_command(
        self,
        command: WorkerCommand,
        *,
        require_session_id: bool = False,
    ) -> str:
        with self._start_lock:
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
            self._track_viewer_request(pending)
            if require_session_id and not pending.session_id:
                self._complete_viewer_request(request_id)
                self._dispatch_viewer_request_failure(
                    pending,
                    "session_id is required.",
                )
                return request_id
            with self._state_lock:
                active_thread = self._run_thread
                generation_token = self._catalog_generation_token
            if active_thread is not None and active_thread.is_alive():
                if not self._post_command(command):
                    self._complete_viewer_request(request_id)
                    self._dispatch_viewer_request_failure(
                        pending, "Failed to dispatch command."
                    )
                return request_id
            dispatch_viewer_command(
                command,
                event_queue=_GenerationTaggedEventSink(
                    self._event_queue,
                    generation_token,
                ),
                worker_services=self._worker_services,
            )
        return request_id

    def shutdown(self) -> None:
        self._running = False
        self._event_queue.put(dict(_LISTENER_SHUTDOWN_SENTINEL))
        with self._state_lock:
            run_id = self._active_run_id
            thread = self._run_thread
        if run_id:
            self._post_command(ShutdownCommand())
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
        with self._state_lock:
            self._clear_active_run_state_locked()
            self._run_thread = None
        with self._viewer_request_lock:
            self._pending_viewer_requests.clear()
            self._viewer_session_ids.clear()
            self._viewer_session_generations.clear()
            self._viewer_session_node_ids.clear()
        if self._listener_thread.is_alive():
            self._listener_thread.join(timeout=1.0)
        self._worker_services.reset()

    def _check_worker_health(self) -> None:
        with self._state_lock:
            thread = self._run_thread
            active_run_id = self._active_run_id
            workspace_id = self._active_workspace_id
            active_node_id = self._active_node_id
        if thread is None or thread.is_alive() or not active_run_id:
            return
        thread.join(timeout=0.1)
        with self._state_lock:
            if self._active_run_id != active_run_id:
                return
            failed_node_id = self._active_node_id or active_node_id
            self._clear_active_run_state_locked()
            self._run_thread = None
        self._dispatch_event(
            RunFailedEvent(
                run_id=active_run_id,
                workspace_id=workspace_id,
                node_id=failed_node_id,
                error="Trusted in-process execution terminated unexpectedly.",
                traceback="",
                fatal=True,
            )
        )
        self._dispatch_event(
            RunStateEvent(
                run_id=active_run_id,
                workspace_id=workspace_id,
                state="error",
                transition="fail",
                reason="trusted_in_process_terminated",
            )
        )

    def _event_listener(self) -> None:
        while self._running:
            try:
                source_event = self._event_queue.get(timeout=0.2)
            except queue.Empty:
                self._check_worker_health()
                continue

            if source_event == _LISTENER_SHUTDOWN_SENTINEL:
                break
            if (
                not isinstance(source_event, tuple)
                or len(source_event) != 2
                or not isinstance(source_event[0], int)
            ):
                continue
            generation_token, event = source_event
            if not self._source_generation_is_current(generation_token):
                continue
            if not isinstance(event, dict):
                self._emit_protocol_error(
                    "Received non-dictionary event from trusted worker."
                )
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
