# Purpose: Validate prepared execution and run demanded nodes or current data reads.
# Map: subsystems/execution.md
# Tests: tests/test_execution_worker.py, tests/test_runtime_current_results.py
# Landmarks: NodeExecutor; WorkflowRunner; _validate_prepared_command
from __future__ import annotations

import asyncio
import hashlib
import json
import queue
import time
import traceback
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from multiprocessing import Queue
from types import MappingProxyType
from typing import Any

from ea_node_editor.execution.run_messages import (
    CancelRunPreflightCommand,
    CommitRunPreflightCommand,
    PauseRunCommand,
    ResumeRunCommand,
    RetireWorkspaceCommand,
    RunCompletedEvent,
    RunFailedEvent,
    RunPreflightAcceptedEvent,
    RunStartedEvent,
    RunStoppedEvent,
    ShutdownCommand,
    StartRunCommand,
    StopRunCommand,
    WorkspaceRetiredEvent,
    TriggerCaptureSettledEvent,
    TriggerPublishedEvent,
)
from ea_node_editor.execution.protocol_codec import (
    WorkerCommand,
    WorkerEvent,
)
from ea_node_editor.execution.registry_agreement import (
    catalog_mismatch_message,
)
from ea_node_editor.runtime_contracts.settled_results import (
    RootExecutionError,
    SettledPortResult,
    settled_outputs_to_payload,
)
from ea_node_editor.execution.prepared_execution import (
    AcceptedOutputPayload,
    PreparedAction,
    PreparedNodeDecision,
    RecomputeMode,
    validate_current_output_payload,
)
from ea_node_editor.execution.solution_identity import (
    assemble_node_solution,
    canonical_digest,
)
from ea_node_editor.execution.runtime_snapshot import (
    RuntimeSnapshot,
    RuntimeSnapshotContext,
)
from ea_node_editor.execution.worker_protocol import (
    command_payload_type,
    decode_command_payload,
    dispatch_viewer_command,
    emit,
    emit_protocol_error,
    emit_run_state,
    is_viewer_command,
)
from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.execution_plan import ExecutionPlan
from ea_node_editor.execution.worker_runtime import (
    DEFAULT_RUNTIME_PREPARATION_CACHE,
    RuntimeArtifactService,
    prepare_runtime,
)
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.nodes.execution_context import (
    ExecutionContext,
    NodeInputNotReadyError,
)
from ea_node_editor.nodes.readiness import (
    evaluate_node_readiness,
    readiness_value_is_present,
)
from ea_node_editor.nodes.instance_resolution import resolve_instance_ports
from ea_node_editor.runtime_contracts import (
    DataTree,
    DataTypeCatalog,
    DataTypeCatalogError,
    RuntimeArtifactRef,
    RuntimeHandleRef,
    TypedInlineValue,
)

_RUN_PREFLIGHT_COMMIT_TIMEOUT_SEC = 30.0

_CONTEXT_SEMANTIC_LINK_FIELDS = (
    "id",
    "kind",
    "title",
    "target",
    "subtitle",
    "target_workspace_id",
    "target_node_id",
)


def _immutable_semantic_links(node: Any) -> tuple[Mapping[str, Any], ...]:
    raw_links = node.extra_fields.get("links", ())
    if not isinstance(raw_links, Sequence) or isinstance(raw_links, (str, bytes)):
        return ()
    return tuple(
        MappingProxyType(
            {
                field_name: (
                    raw_link.get(field_name, "")
                    if isinstance(raw_link.get(field_name, ""), str)
                    else ""
                )
                for field_name in _CONTEXT_SEMANTIC_LINK_FIELDS
            }
        )
        for raw_link in raw_links
        if isinstance(raw_link, Mapping)
    )


class _CatalogAgreementMismatch(DataTypeCatalogError):
    pass


class RunControl:
    def __init__(
        self,
        command_queue: Queue | None,
        event_queue: Queue,
        *,
        run_id: str,
        workspace_id: str,
        data_types: DataTypeCatalog | None = None,
        viewer_command_handler: Callable[[WorkerCommand], None] | None = None,
        workspace_retirement_handler: Callable[[str], int] | None = None,
    ) -> None:
        self._command_queue = command_queue
        self._event_queue = event_queue
        self.run_id = run_id
        self.workspace_id = workspace_id
        self._data_types = data_types
        self._viewer_command_handler = viewer_command_handler
        self._workspace_retirement_handler = workspace_retirement_handler
        self.paused = False
        self.stop_requested = False
        self.shutdown_requested = False
        self.stop_reason = ""
        self._cancel_callbacks: list[Callable[[], None]] = []

    def register_cancel_callback(self, callback: Callable[[], None]) -> None:
        if not callable(callback):
            return
        self._cancel_callbacks.append(callback)

    def _invoke_cancel_callbacks(self) -> None:
        callbacks = list(self._cancel_callbacks)
        self._cancel_callbacks.clear()
        for callback in callbacks:
            try:
                callback()
            except Exception:  # noqa: BLE001
                continue

    def clear_cancel_callbacks(self) -> None:
        self._cancel_callbacks.clear()

    def _handle_command(self, command: WorkerCommand) -> None:
        command_type = command.type
        command_run_id = getattr(command, "run_id", "")
        command_workspace_id = getattr(command, "workspace_id", "")
        command_request_id = getattr(command, "request_id", "")

        if isinstance(command, ShutdownCommand):
            self.shutdown_requested = True
            self.stop_requested = True
            self.stop_reason = "shutdown_requested"
            self._invoke_cancel_callbacks()
            return

        if isinstance(command, RetireWorkspaceCommand):
            if self._workspace_retirement_handler is None:
                emit_protocol_error(
                    self._event_queue,
                    "Workspace retirement handler is unavailable.",
                    workspace_id=command.workspace_id,
                    request_id=command.request_id,
                    command=command.type,
                    catalog=self._data_types,
                )
                return
            retired = self._workspace_retirement_handler(command.workspace_id)
            emit(
                self._event_queue,
                WorkspaceRetiredEvent(
                    request_id=command.request_id,
                    workspace_id=command.workspace_id,
                    retired_count=str(retired),
                ),
                catalog=self._data_types,
            )
            return

        if command_run_id and command_run_id != self.run_id:
            emit_protocol_error(
                self._event_queue,
                "Ignoring command for inactive run.",
                run_id=command_run_id,
                workspace_id=command_workspace_id,
                request_id=command_request_id,
                command=command_type,
                catalog=self._data_types,
            )
            return

        if isinstance(command, PauseRunCommand):
            if not self.paused:
                self.paused = True
                emit_run_state(
                    self._event_queue,
                    run_id=self.run_id,
                    workspace_id=self.workspace_id,
                    state="paused",
                    transition="pause",
                    reason="pause_requested",
                    catalog=self._data_types,
                )
            return

        if isinstance(command, ResumeRunCommand):
            if self.paused:
                self.paused = False
                emit_run_state(
                    self._event_queue,
                    run_id=self.run_id,
                    workspace_id=self.workspace_id,
                    state="running",
                    transition="resume",
                    reason="resume_requested",
                    catalog=self._data_types,
                )
            return

        if isinstance(command, StopRunCommand):
            self.stop_requested = True
            self.stop_reason = "stop_requested"
            self._invoke_cancel_callbacks()
            return

        if is_viewer_command(command):
            if self._viewer_command_handler is None:
                emit_protocol_error(
                    self._event_queue,
                    "Viewer command handler is unavailable.",
                    workspace_id=command_workspace_id,
                    request_id=command_request_id,
                    command=command_type,
                    catalog=self._data_types,
                )
                return
            self._viewer_command_handler(command)
            return

        if isinstance(command, StartRunCommand):
            emit_protocol_error(
                self._event_queue,
                "Worker already has an active run.",
                run_id=command_run_id,
                workspace_id=command_workspace_id,
                request_id=command_request_id,
                command=command_type,
                catalog=self._data_types,
            )
            return

        emit_protocol_error(
            self._event_queue,
            "Unsupported command while run is active.",
            run_id=command_run_id or self.run_id,
            workspace_id=command_workspace_id or self.workspace_id,
            request_id=command_request_id,
            command=command_type,
            catalog=self._data_types,
        )

    def poll_commands(self) -> None:
        if self._command_queue is None:
            return
        while True:
            try:
                raw_command = self._command_queue.get_nowait()
            except queue.Empty:
                return
            if command_payload_type(raw_command) == "start_run":
                emit_protocol_error(
                    self._event_queue,
                    "Worker already has an active run.",
                    command="start_run",
                    catalog=self._data_types,
                )
                continue
            command = decode_command_payload(
                raw_command,
                event_queue=self._event_queue,
                catalog=self._data_types,
            )
            if command is None:
                continue
            self._handle_command(command)

    def wait_until_runnable(self) -> None:
        while self.paused and not self.stop_requested and not self.shutdown_requested:
            time.sleep(0.05)
            self.poll_commands()

    def should_stop(self) -> bool:
        self.poll_commands()
        return self.stop_requested or self.shutdown_requested


class RunEventPublisher:
    def __init__(
        self,
        event_queue: Queue,
        *,
        run_id: str,
        workspace_id: str,
        data_types: DataTypeCatalog | None = None,
    ) -> None:
        self._event_queue = event_queue
        self.run_id = run_id
        self.workspace_id = workspace_id
        self._data_types = data_types

    def emit(self, event: WorkerEvent) -> None:
        emit(self._event_queue, event, catalog=self._data_types)

    def emit_run_started(self) -> None:
        self.emit(RunStartedEvent(run_id=self.run_id, workspace_id=self.workspace_id))
        self.emit_run_state(state="running", transition="start", reason="run_started")

    def emit_run_preflight_accepted(
        self,
        *,
        preparation_id: str,
        reservation_id: str,
        snapshot_digest: str,
    ) -> None:
        self.emit(
            RunPreflightAcceptedEvent(
                run_id=self.run_id,
                workspace_id=self.workspace_id,
                preparation_id=preparation_id,
                viewer_invalidation_reservation_id=reservation_id,
                viewer_epoch_snapshot_digest=snapshot_digest,
            )
        )

    def emit_run_state(self, *, state: str, transition: str, reason: str) -> None:
        emit_run_state(
            self._event_queue,
            run_id=self.run_id,
            workspace_id=self.workspace_id,
            state=state,
            transition=transition,
            reason=reason,
            catalog=self._data_types,
        )

    def emit_run_completed(self) -> None:
        self.emit(RunCompletedEvent(run_id=self.run_id, workspace_id=self.workspace_id))
        self.emit_run_state(
            state="ready", transition="complete", reason="run_completed"
        )

    def emit_run_stopped(self, reason: str) -> None:
        self.emit(
            RunStoppedEvent(
                run_id=self.run_id,
                workspace_id=self.workspace_id,
                reason=reason,
            )
        )
        self.emit_run_state(state="ready", transition="stop", reason=reason)

    def emit_run_failed(
        self,
        *,
        node_id: str,
        error: str,
        traceback_text: str,
        reason: str,
    ) -> None:
        self.emit(
            RunFailedEvent(
                run_id=self.run_id,
                workspace_id=self.workspace_id,
                node_id=node_id,
                error=error,
                traceback=traceback_text,
            )
        )
        self.emit_run_state(state="error", transition="fail", reason=reason)

    def emit_node_started(
        self, node_id: str, *, started_at_epoch_ms: float = 0.0
    ) -> None:
        from ea_node_editor.execution.run_messages import (
            NodeStartedEvent,
        )

        self.emit(
            NodeStartedEvent(
                run_id=self.run_id,
                workspace_id=self.workspace_id,
                node_id=node_id,
                started_at_epoch_ms=started_at_epoch_ms,
            )
        )

    def emit_node_settled(
        self,
        node_id: str,
        status: str,
        outputs: Mapping[str, SettledPortResult],
        *,
        elapsed_ms: float = 0.0,
        errors: Iterable[RootExecutionError] = (),
        warnings: Iterable[str] = (),
        disposition: str = "",
        decision_reason: str = "legacy_direct_run",
        solution_key: str = "",
        record_id: str = "",
        residency: str = "",
    ) -> None:
        from ea_node_editor.execution.run_messages import (
            NodeSettledEvent,
        )

        normalized_warnings = _normalize_warning_messages(warnings)
        self.emit(
            NodeSettledEvent(
                run_id=self.run_id,
                workspace_id=self.workspace_id,
                node_id=node_id,
                status=status,
                elapsed_ms=elapsed_ms,
                outputs=dict(outputs),
                errors=tuple(errors),
                warnings=normalized_warnings,
                disposition=disposition,
                decision_reason=decision_reason,
                solution_key=solution_key,
                record_id=record_id,
                residency=residency,
            )
        )

    def emit_observation_invalidation(
        self, node_id: str, root_node_id: str, reason_code: str
    ) -> None:
        from ea_node_editor.execution.run_messages import (
            ObservationInvalidationRequestedEvent,
        )

        self.emit(
            ObservationInvalidationRequestedEvent(
                run_id=self.run_id,
                workspace_id=self.workspace_id,
                node_id=node_id,
                root_node_id=root_node_id,
                reason_code=reason_code,
            )
        )

    def emit_trigger_capture_settled(
        self, node_id: str, result: SettledPortResult
    ) -> None:
        self.emit(
            TriggerCaptureSettledEvent(
                run_id=self.run_id,
                workspace_id=self.workspace_id,
                trigger_node_id=node_id,
                result=result,
            )
        )

    def emit_trigger_published(self, node_id: str, result: SettledPortResult) -> None:
        self.emit(
            TriggerPublishedEvent(
                run_id=self.run_id,
                workspace_id=self.workspace_id,
                trigger_node_id=node_id,
                result=result,
            )
        )

    def emit_log(self, level: str, message: str, *, node_id: str = "") -> None:
        from ea_node_editor.execution.run_messages import (
            LogEvent,
        )

        self.emit(
            LogEvent(
                run_id=self.run_id,
                workspace_id=self.workspace_id,
                node_id=node_id,
                level=level,
                message=message,
            )
        )


def _normalize_warning_messages(warnings: Iterable[str] | object) -> tuple[str, ...]:
    if warnings is None:
        return ()
    if isinstance(warnings, str):
        candidates = (warnings,)
    else:
        try:
            candidates = tuple(warnings)  # type: ignore[arg-type]
        except TypeError:
            candidates = (warnings,)
    return tuple(str(warning).strip() for warning in candidates if str(warning).strip())


def _exception_message(exc: BaseException) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


class NodeExecutor:
    def __init__(
        self,
        execution_plan: ExecutionPlan,
        registry: Any,
        control: RunControl,
        publisher: RunEventPublisher,
        *,
        artifact_service: RuntimeArtifactService,
        worker_services: WorkerServices,
        project_path: str,
        runtime_snapshot: RuntimeSnapshot,
        runtime_context: RuntimeSnapshotContext,
        plugin_runtime: WorkerPluginRuntime,
        trigger: dict[str, Any],
        trigger_publications: Mapping[str, SettledPortResult] | None = None,
        trigger_captures: Mapping[str, SettledPortResult] | None = None,
        node_decisions: Mapping[str, PreparedNodeDecision] | None = None,
        developer_mode: bool = False,
    ) -> None:
        self._plan = execution_plan
        self._registry = registry
        self._data_types = registry.data_types
        self._control = control
        self._publisher = publisher
        self._artifact_service = artifact_service
        self._worker_services = worker_services
        self._artifact_context_project_path = str(project_path).strip()
        self._runtime_snapshot = runtime_snapshot
        self._runtime_context = runtime_context
        self._plugin_runtime = plugin_runtime
        self._trigger = trigger
        self._developer_mode = bool(developer_mode)
        self._trigger_publications = dict(trigger_publications or {})
        self._trigger_captures = dict(trigger_captures or {})
        self._node_decisions = dict(node_decisions or {})
        self._workspace_node_types: Mapping[str, str] = MappingProxyType(
            {
                node_id: node.type_id
                for node_id, node in self._plan.nodes.items()
            }
        )

        self._semantic_links_by_node = {
            node_id: _immutable_semantic_links(node)
            for node_id, node in self._plan.nodes.items()
        }
        self._run_state: dict[str, Any] = {}
        self.node_outputs: dict[str, dict[str, SettledPortResult]] = {}
        self.executed: set[str] = set()
        self.pending_trigger_publication: tuple[str, SettledPortResult] | None = None
        try:
            runtime_workspace = self._runtime_snapshot.workspace(
                self._publisher.workspace_id
            )
            self._workspace_name = str(
                runtime_workspace.document_fields.get("name", "") or ""
            ).strip()
        except KeyError:
            self._workspace_name = ""

    def clear_run_state(self) -> None:
        self._run_state.clear()

    def _publish_node_state(self, node_id: str, value: Any) -> None:
        self._run_state[node_id] = value

    def _read_node_state(self, node_id: str) -> Any | None:
        return self._run_state.get(node_id)

    def run_node(self, node_id: str) -> str:
        if node_id in self.executed:
            return "ok"
        status = self._await_runnable()
        if status is not None:
            return status
        if self._plan.is_trigger(node_id):
            return self._execute_trigger(node_id)
        return self._execute_node(node_id)

    def validate_reused_output(
        self,
        payload: AcceptedOutputPayload,
        *,
        port_keys: tuple[str, ...] | None = None,
    ) -> tuple[dict[str, SettledPortResult], dict[str, SettledPortResult]]:
        node_id = payload.node_id
        expected_ports = {
            port.key: port
            for port in self._plan.output_ports(node_id)
            if port.kind == "data"
        }
        if port_keys is not None:
            if not set(port_keys).issubset(expected_ports):
                raise ValueError("current result has unknown output ports")
            expected_ports = {key: expected_ports[key] for key in port_keys}
        event_outputs = payload.decode_outputs(catalog=self._data_types)
        if payload.settlement_status == "completed":
            if set(event_outputs) != set(expected_ports):
                raise ValueError("reused outputs do not match actual output ports")
        elif event_outputs and (
            set(event_outputs) != set(expected_ports)
            or any(result.status != "empty" for result in event_outputs.values())
        ):
            raise ValueError("empty reused outputs do not match actual output ports")
        if any(result.status == "failed" for result in event_outputs.values()):
            raise ValueError("reused outputs cannot contain failed results")
        for port_key, result in event_outputs.items():
            if result.status != "value" or not isinstance(result.value, DataTree):
                continue
            port = expected_ports[port_key]
            for _path, items in result.value.branches:
                for item in items:
                    for candidate in self._candidate_type_ids(port):
                        try:
                            self._data_types.validate_carrier(candidate, item)
                        except DataTypeCatalogError:
                            continue
                        break
                    else:
                        raise ValueError(
                            "reused output item does not match the active catalog"
                        )

        def validate_resource(value: Any, *, port_key: str) -> None:
            if isinstance(value, RuntimeArtifactRef):
                self._artifact_service.resolve_path(value)
                return
            if isinstance(value, RuntimeHandleRef):
                port = expected_ports[port_key]
                self._worker_services.resolve_handle(
                    value,
                    expected_data_type=port.data_type,
                    expected_kind=value.kind,
                )
                return
            if isinstance(value, DataTree):
                for _path, items in value.branches:
                    for item in items:
                        validate_resource(item, port_key=port_key)

        for port_key, result in event_outputs.items():
            if result.status == "value":
                validate_resource(result.value, port_key=port_key)
        installed_outputs = (
            {
                port_key: event_outputs.get(
                    port_key,
                    SettledPortResult(status="empty"),
                )
                for port_key in expected_ports
            }
            if payload.settlement_status == "empty"
            else dict(event_outputs)
        )
        return installed_outputs, event_outputs

    def install_accepted_output(
        self,
        decision: PreparedNodeDecision,
        payload: AcceptedOutputPayload,
        installed_outputs: Mapping[str, SettledPortResult],
        event_outputs: Mapping[str, SettledPortResult],
    ) -> str:
        status = self._await_runnable()
        if status is not None:
            return status
        if decision.node_id in self.executed:
            raise ValueError("reused node was installed more than once")
        self.node_outputs[decision.node_id] = dict(installed_outputs)
        self.executed.add(decision.node_id)
        if decision.action is PreparedAction.READ_CURRENT:
            # Reading data does not republish or refresh its producer's current fact.
            return "ok"
        self._publisher.emit_node_settled(
            decision.node_id,
            payload.settlement_status,
            event_outputs,
            disposition="reused",
            decision_reason=decision.reason_code,
            solution_key=decision.solution_key,
            record_id=payload.record_id,
            residency=payload.residency.value,
        )
        return "ok"

    def _await_runnable(self) -> str | None:
        self._control.poll_commands()
        if self._control.shutdown_requested or self._control.stop_requested:
            return "stopped"
        self._control.wait_until_runnable()
        if self._control.shutdown_requested or self._control.stop_requested:
            return "stopped"
        return None

    def _execute_node(self, node_id: str) -> str:
        node = self._plan.nodes[node_id]
        node_type_id = node.type_id
        started_at_epoch_ms = time.time() * 1000.0
        self._publisher.emit_node_started(
            node_id, started_at_epoch_ms=started_at_epoch_ms
        )
        try:
            preflight_error = self._plan.node_preflight_errors.get(node_id)
            if preflight_error is not None:
                raise preflight_error
            properties = self._registry.normalize_properties(
                node_type_id,
                dict(node.properties),
            )
            properties = self._artifact_service.materialize_authored_properties(properties)
            input_results = self._input_results(node_id, properties)
            errors = self._errors_from_results(input_results.values())
            if errors:
                return self._settle_failed(
                    node_id,
                    errors,
                    status="blocked",
                    started_at_epoch_ms=started_at_epoch_ms,
                )
            spec = self._plan.node_specs[node_id]
            readiness_issues = evaluate_node_readiness(
                replace(spec, ports=resolve_instance_ports(spec, properties)),
                port_has_value={
                    port_key: result.status == "value"
                    and isinstance(result.value, DataTree)
                    and any(
                            readiness_value_is_present(
                                item,
                                allow_empty_string=next(
                                    (
                                        port.allow_empty_string
                                        for port in spec.ports
                                        if port.key == port_key
                                    ),
                                    False,
                                ),
                            )
                        for _path, items in result.value.branches
                        for item in items
                    )
                    for port_key, result in input_results.items()
                },
                overridden_port_keys={
                    edge.target_port_key
                    for edge in self._plan.incoming_edges_for(node_id)
                },
                properties=properties,
            )
            if readiness_issues:
                warnings = tuple(issue.message for issue in readiness_issues)
                for warning in warnings:
                    self._publisher.emit_log("warning", warning, node_id=node_id)
                return self._settle_empty(
                    node_id,
                    started_at_epoch_ms=started_at_epoch_ms,
                    warnings=warnings,
                )

            principal = self._principal_port(node_id, input_results)
            iterations = self._iteration_targets(principal, input_results)
            if not iterations:
                return self._settle_empty(
                    node_id, started_at_epoch_ms=started_at_epoch_ms
                )

            function_ref = self._registry.python_function_ref_or_none(node_type_id)
            plugin = (
                self._registry.create(node_type_id)
                if function_ref is None
                else self._plugin_runtime.create_adapter(
                    function_ref,
                    spec,
                    unavailable_reason=self._registry.unavailable_reason(node_type_id),
                )
            )
            aggregates: dict[str, DataTree] = {}
            warnings: list[str] = []
            for iteration, (target_path, branch_ordinal, item_ordinal) in enumerate(
                iterations
            ):
                status = self._await_runnable()
                if status is not None:
                    return status
                inputs, required_missing = self._match_inputs(
                    node_id,
                    input_results,
                    branch_ordinal=branch_ordinal,
                    item_ordinal=item_ordinal,
                )
                if required_missing:
                    return self._settle_empty(
                        node_id, started_at_epoch_ms=started_at_epoch_ms
                    )
                ctx = self._execution_context(
                    node_id,
                    inputs,
                    properties,
                    target_path=target_path,
                    target_iteration=iteration,
                    iteration_count=len(iterations),
                )
                try:
                    if spec.is_async and callable(
                        getattr(plugin, "async_execute", None)
                    ):
                        result = asyncio.run(plugin.async_execute(ctx))
                    else:
                        result = plugin.execute(ctx)
                finally:
                    self._control.clear_cancel_callbacks()
                if self._control.should_stop():
                    return "stopped"
                raw_outputs = getattr(result, "outputs", None)
                if not isinstance(raw_outputs, Mapping):
                    raise TypeError("Node results must expose an output mapping.")
                normalized_outputs = self._artifact_service.normalize_outputs(
                    dict(raw_outputs)
                )
                iteration_outputs = self._validate_outputs(
                    node_id,
                    normalized_outputs,
                    target_path=target_path,
                )
                for port_key, tree in iteration_outputs.items():
                    previous = aggregates.get(port_key)
                    aggregates[port_key] = (
                        tree if previous is None else previous.merge(tree)
                    )
                warnings.extend(
                    _normalize_warning_messages(getattr(result, "warnings", ()))
                )

            outputs = self._settled_outputs(node_id, aggregates)
            elapsed_ms = max(0.0, (time.time() * 1000.0) - started_at_epoch_ms)
            for warning in warnings:
                self._publisher.emit_log(
                    "warning",
                    f"Node completed with warning: {warning}",
                    node_id=node_id,
                )
            status = (
                "completed"
                if not outputs
                or any(result.status == "value" for result in outputs.values())
                else "empty"
            )
            return self._settle(
                node_id,
                outputs,
                status=status,
                elapsed_ms=elapsed_ms,
                warnings=warnings,
            )
        except InterruptedError as exc:
            if self._control.should_stop():
                return "stopped"
            return self._fail_node(
                node_id, exc, started_at_epoch_ms=started_at_epoch_ms
            )
        except NodeInputNotReadyError as exc:
            warning = str(exc)
            self._publisher.emit_log("warning", warning, node_id=node_id)
            return self._settle_empty(
                node_id,
                started_at_epoch_ms=started_at_epoch_ms,
                warnings=(warning,),
            )
        except Exception as exc:  # noqa: BLE001
            return self._fail_node(
                node_id, exc, started_at_epoch_ms=started_at_epoch_ms
            )
        except BaseException as exc:  # noqa: BLE001
            return self._fail_node(
                node_id, exc, started_at_epoch_ms=started_at_epoch_ms
            )
        finally:
            self._control.clear_cancel_callbacks()

    def _execute_trigger(self, node_id: str) -> str:
        started_at_epoch_ms = time.time() * 1000.0
        self._publisher.emit_node_started(
            node_id, started_at_epoch_ms=started_at_epoch_ms
        )
        clicked = node_id == self._plan.clicked_trigger_node_id
        try:
            if clicked:
                properties = self._registry.normalize_properties(
                    self._plan.nodes[node_id].type_id,
                    dict(self._plan.nodes[node_id].properties),
                )
                properties = self._artifact_service.materialize_authored_properties(
                    properties
                )
                edges = self._plan.incoming_edges_for(node_id, "input")
                if not edges:
                    captured = SettledPortResult(
                        status="value",
                        value=DataTree.from_item(True),
                    )
                elif node_id in self._trigger_captures:
                    captured = self._trigger_captures[node_id]
                else:
                    port = self._plan.ports_by_key[node_id]["input"]
                    captured = self._input_result(node_id, port, properties)
                    self._publisher.emit_trigger_capture_settled(node_id, captured)
                result = self._apply_result_modifiers(node_id, "output", captured)
                self.pending_trigger_publication = (node_id, result)
            else:
                result = self._trigger_publications.get(
                    node_id, SettledPortResult(status="empty")
                )
            status = {
                "value": "completed",
                "empty": "empty",
                "failed": "blocked",
            }.get(str(result.status), "empty")
            errors = result.errors if result.status == "failed" else ()
            return self._settle(
                node_id,
                {"output": result},
                status=status,
                elapsed_ms=max(0.0, (time.time() * 1000.0) - started_at_epoch_ms),
                errors=errors,
            )
        except Exception as exc:  # noqa: BLE001
            if not clicked:
                return self._fail_node(
                    node_id, exc, started_at_epoch_ms=started_at_epoch_ms
                )
            result = self._error_result(node_id, exc)
            self.pending_trigger_publication = (node_id, result)
            return self._settle(
                node_id,
                {"output": result},
                status="failed",
                elapsed_ms=max(0.0, (time.time() * 1000.0) - started_at_epoch_ms),
                errors=result.errors,
            )

    def refresh_trigger_captures(self) -> None:
        for node_id in self._plan.nodes:
            if (
                not self._plan.is_trigger(node_id)
                or node_id == self._plan.clicked_trigger_node_id
            ):
                continue
            edges = self._plan.incoming_edges_for(node_id, "input")
            if not edges or any(
                edge.source_node_id not in self.executed
                or edge.source_port_key
                not in self.node_outputs.get(edge.source_node_id, {})
                for edge in edges
            ):
                continue
            try:
                properties = self._registry.normalize_properties(
                    self._plan.nodes[node_id].type_id,
                    dict(self._plan.nodes[node_id].properties),
                )
                properties = self._artifact_service.materialize_authored_properties(
                    properties
                )
                port = self._plan.ports_by_key[node_id]["input"]
                result = self._input_result(node_id, port, properties)
            except Exception as exc:  # noqa: BLE001
                result = self._error_result(node_id, exc)
            self._publisher.emit_trigger_capture_settled(node_id, result)

    def publish_pending_trigger(self) -> None:
        if self.pending_trigger_publication is None:
            return
        node_id, result = self.pending_trigger_publication
        self._publisher.emit_trigger_published(node_id, result)
        self.pending_trigger_publication = None

    def _input_results(
        self,
        node_id: str,
        properties: Mapping[str, Any],
    ) -> dict[str, SettledPortResult]:
        return {
            port.key: self._input_result(node_id, port, properties)
            for port in self._plan.input_ports(node_id)
        }

    def _input_result(
        self,
        node_id: str,
        port: Any,
        properties: Mapping[str, Any],
    ) -> SettledPortResult:
        node = self._plan.nodes[node_id]
        edges = self._plan.incoming_edges_for(node_id, port.key)
        if not edges and port.uses_property_default:
            if port.key not in properties:
                return SettledPortResult(status="empty")
            value = properties[port.key]
            if isinstance(value, DataTree):
                tree = value
            elif str(port.data_access) == "list" and self._is_sequence(value):
                tree = DataTree.from_list(value)
            else:
                tree = DataTree.from_item(value)
            tree = self._prepare_untyped_tree(node_id, port, tree)
            return self._apply_input_modifiers(node, port.key, tree)

        raw_results = [
            self.node_outputs.get(edge.source_node_id, {}).get(
                edge.source_port_key,
                SettledPortResult(status="empty"),
            )
            for edge in edges
        ]
        errors = self._errors_from_results(raw_results)
        if errors:
            return SettledPortResult(status="failed", errors=errors)

        results = []
        for edge, result in zip(edges, raw_results, strict=True):
            if result.status == "value" and isinstance(result.value, DataTree):
                result = SettledPortResult(
                    status="value",
                    value=self._prepare_wired_tree(node_id, port, edge, result.value),
                )
            results.append(result)
        trees = [
            result.value
            for result in results
            if result.status == "value" and isinstance(result.value, DataTree)
        ]
        if not trees:
            return SettledPortResult(status="empty")
        tree = trees[0].merge(*trees[1:])
        return self._apply_input_modifiers(node, port.key, tree)

    @staticmethod
    def _candidate_type_ids(port: Any) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                (
                    str(port.data_type).strip(),
                    *(str(value).strip() for value in port.accepted_data_types),
                )
            )
        )

    def _prepare_wired_tree(
        self,
        node_id: str,
        port: Any,
        edge: Any,
        tree: DataTree,
    ) -> DataTree:
        source_port = self._plan.ports_by_key.get(edge.source_node_id, {}).get(
            edge.source_port_key
        )
        if source_port is None:
            raise ValueError(
                self._typed_value_error(
                    node_id,
                    port,
                    source_type_id="<unresolved>",
                    value=None,
                    path=(),
                    item_index=0,
                    reason=(
                        f"source port {edge.source_node_id!r}/"
                        f"{edge.source_port_key!r} is absent from the execution plan"
                    ),
                )
            )
        source_type_id = str(source_port.data_type).strip()
        return DataTree(
            (
                path,
                tuple(
                    self._prepare_wired_item(
                        node_id,
                        port,
                        source_type_id,
                        item,
                        path=path,
                        item_index=item_index,
                    )
                    for item_index, item in enumerate(items)
                ),
            )
            for path, items in tree.branches
        )

    def _prepare_wired_item(
        self,
        node_id: str,
        port: Any,
        source_type_id: str,
        value: Any,
        *,
        path: tuple[int, ...],
        item_index: int,
    ) -> Any:
        if value is None:
            return None
        candidates = self._candidate_type_ids(port)
        decisions = tuple(
            (
                candidate,
                self._data_types.compatibility(source_type_id, candidate),
            )
            for candidate in candidates
        )
        for _candidate, decision in decisions:
            if decision.status == "assignable":
                return value

        runtime_reasons: list[str] = []
        for candidate, decision in decisions:
            if decision.status != "runtime_check":
                continue
            try:
                return self._data_types.convert_typed_input(
                    source_type_id,
                    candidate,
                    value,
                )
            except DataTypeCatalogError as exc:
                runtime_reasons.append(f"{candidate}: {exc}")

        convertible = next(
            (
                candidate
                for candidate, decision in decisions
                if decision.status == "convertible"
            ),
            None,
        )
        if convertible is not None:
            try:
                return self._data_types.convert_typed_input(
                    source_type_id,
                    convertible,
                    value,
                )
            except DataTypeCatalogError as exc:
                raise ValueError(
                    self._typed_value_error(
                        node_id,
                        port,
                        source_type_id=source_type_id,
                        value=value,
                        path=path,
                        item_index=item_index,
                        reason=str(exc),
                    )
                ) from exc

        decision_reasons = [
            f"{candidate}: {decision.status}/{decision.reason_code}"
            for candidate, decision in decisions
        ]
        raise ValueError(
            self._typed_value_error(
                node_id,
                port,
                source_type_id=source_type_id,
                value=value,
                path=path,
                item_index=item_index,
                reason="; ".join((*runtime_reasons, *decision_reasons)),
            )
        )

    def _prepare_untyped_tree(
        self,
        node_id: str,
        port: Any,
        tree: DataTree,
    ) -> DataTree:
        return DataTree(
            (
                path,
                tuple(
                    self._prepare_untyped_item(
                        node_id,
                        port,
                        item,
                        path=path,
                        item_index=item_index,
                    )
                    for item_index, item in enumerate(items)
                ),
            )
            for path, items in tree.branches
        )

    def _prepare_untyped_item(
        self,
        node_id: str,
        port: Any,
        value: Any,
        *,
        path: tuple[int, ...],
        item_index: int,
    ) -> Any:
        if value is None:
            return None
        candidates = self._candidate_type_ids(port)
        if type(value) is TypedInlineValue:
            validation_reasons: list[str] = []
            for candidate in candidates:
                try:
                    self._data_types.validate_carrier(candidate, value)
                    return value
                except DataTypeCatalogError as exc:
                    validation_reasons.append(f"{candidate}: {exc}")
            raise ValueError(
                self._typed_value_error(
                    node_id,
                    port,
                    source_type_id=value.data_type_id,
                    value=value,
                    path=path,
                    item_index=item_index,
                    reason="; ".join(validation_reasons),
                )
            )
        validation_reasons: list[str] = []
        for candidate in candidates:
            try:
                self._data_types.validate_output(candidate, value)
                return value
            except DataTypeCatalogError as exc:
                validation_reasons.append(f"{candidate}: {exc}")
        coercion_reasons: list[str] = []
        for candidate in candidates:
            try:
                return self._data_types.prepare_untyped_input(candidate, value)
            except DataTypeCatalogError as exc:
                coercion_reasons.append(f"{candidate}: {exc}")
        raise ValueError(
            self._typed_value_error(
                node_id,
                port,
                source_type_id="untyped",
                value=value,
                path=path,
                item_index=item_index,
                reason="; ".join((*validation_reasons, *coercion_reasons)),
            )
        )

    def _typed_value_error(
        self,
        node_id: str,
        port: Any,
        *,
        source_type_id: str,
        value: Any,
        path: tuple[int, ...],
        item_index: int,
        reason: str,
    ) -> str:
        node = self._plan.nodes[node_id]
        concrete_type = f"{type(value).__module__}.{type(value).__qualname__}"
        return (
            f"Node type {node.type_id!r} ID {node_id!r} input port {port.key!r}; "
            f"declared candidates {self._candidate_type_ids(port)!r}; "
            f"source semantic type {source_type_id!r}; concrete Python type "
            f"{concrete_type}; DataPath {path!r}; item index {item_index}; "
            f"catalog reason: {reason}"
        )

    @staticmethod
    def _apply_input_modifiers(
        node: Any, port_key: str, tree: DataTree
    ) -> SettledPortResult:
        modified = tree.apply_modifiers(node.port_modifiers.get(port_key, ()))
        if not modified.branch_count:
            return SettledPortResult(status="empty")
        return SettledPortResult(status="value", value=modified)

    def _apply_result_modifiers(
        self,
        node_id: str,
        port_key: str,
        result: SettledPortResult,
    ) -> SettledPortResult:
        if result.status != "value" or not isinstance(result.value, DataTree):
            return result
        return self._apply_input_modifiers(
            self._plan.nodes[node_id], port_key, result.value
        )

    def _principal_port(
        self,
        node_id: str,
        input_results: Mapping[str, SettledPortResult],
    ) -> Any | None:
        candidates = [
            port
            for port in self._plan.input_ports(node_id)
            if str(port.data_access) != "tree"
            and input_results[port.key].status == "value"
        ]
        if not candidates:
            return None
        explicit = self._plan.nodes[node_id].principal_input_port_id
        for port in candidates:
            if port.key == explicit:
                return port
        if len(candidates) == 1:
            return candidates[0]

        def _score(item: tuple[int, Any]) -> tuple[int, int, int]:
            ordinal, port = item
            tree = input_results[port.key].value
            assert isinstance(tree, DataTree)
            depth = max((len(path) for path in tree.paths), default=0)
            first_index_sum = sum(path[0] if path else 0 for path in tree.paths)
            return depth, first_index_sum, -ordinal

        return max(enumerate(candidates), key=_score)[1]

    @staticmethod
    def _iteration_targets(
        principal: Any | None,
        input_results: Mapping[str, SettledPortResult],
    ) -> list[tuple[tuple[int, ...], int, int]]:
        if principal is None:
            return [((0,), 0, 0)]
        tree = input_results[principal.key].value
        assert isinstance(tree, DataTree)
        if str(principal.data_access) == "list":
            return [
                (path, branch_ordinal, 0)
                for branch_ordinal, (path, _items) in enumerate(tree.branches)
            ]
        return [
            (path, branch_ordinal, item_ordinal)
            for branch_ordinal, (path, items) in enumerate(tree.branches)
            for item_ordinal, _item in enumerate(items)
        ]

    def _match_inputs(
        self,
        node_id: str,
        input_results: Mapping[str, SettledPortResult],
        *,
        branch_ordinal: int,
        item_ordinal: int,
    ) -> tuple[dict[str, Any], bool]:
        inputs: dict[str, Any] = {}
        for port in self._plan.input_ports(node_id):
            result = input_results[port.key]
            if result.status != "value" or not isinstance(result.value, DataTree):
                continue
            tree = result.value
            access = str(port.data_access)
            if access == "tree":
                inputs[port.key] = tree
                continue
            branch = self._branch_at(tree, branch_ordinal)
            if branch is None:
                if port.required:
                    return {}, True
                continue
            if access == "list":
                inputs[port.key] = list(branch)
                continue
            if not branch:
                if port.required:
                    return {}, True
                continue
            inputs[port.key] = branch[min(item_ordinal, len(branch) - 1)]
        return inputs, False

    @staticmethod
    def _branch_at(tree: DataTree, branch_ordinal: int) -> tuple[Any, ...] | None:
        if not tree.branches:
            return None
        return tree.branches[min(branch_ordinal, len(tree.branches) - 1)][1]

    def _validate_outputs(
        self,
        node_id: str,
        outputs: Mapping[str, Any],
        *,
        target_path: tuple[int, ...],
    ) -> dict[str, DataTree]:
        ports = {port.key: port for port in self._plan.output_ports(node_id)}
        unknown = sorted(set(outputs).difference(ports))
        if unknown:
            raise ValueError(f"Node returned undeclared outputs: {', '.join(unknown)}")
        validated: dict[str, DataTree] = {}
        for port_key, value in outputs.items():
            port = ports[port_key]
            access = str(port.data_access)
            if access == "tree":
                if not isinstance(value, DataTree):
                    raise TypeError(f"Output {port_key!r} requires a DataTree.")
                tree = value
            elif access == "list":
                if not self._is_sequence(value):
                    raise TypeError(
                        f"Output {port_key!r} requires a non-string sequence."
                    )
                tree = DataTree.from_list(value, path=target_path)
            else:
                tree = DataTree.from_item(value, path=target_path)
            for path, items in tree.branches:
                for item_index, item in enumerate(items):
                    candidates = self._candidate_type_ids(port)
                    actual_type_id = str(
                        getattr(item, "data_type_id", "") or ""
                    ).strip()
                    if actual_type_id:
                        candidates = tuple(
                            sorted(
                                candidates,
                                key=lambda candidate: (
                                    0
                                    if candidate == actual_type_id
                                    else (
                                        1
                                        if self._data_types.is_assignable(
                                            actual_type_id,
                                            candidate,
                                        )
                                        else 2
                                    ),
                                    candidates.index(candidate),
                                ),
                            )
                        )
                    reasons: list[str] = []
                    for candidate in candidates:
                        try:
                            self._data_types.validate_carrier(candidate, item)
                        except DataTypeCatalogError as exc:
                            reasons.append(f"{candidate}: {exc}")
                        else:
                            break
                    else:
                        node = self._plan.nodes[node_id]
                        source_semantic_type = actual_type_id or "untyped"
                        concrete_type = (
                            f"{type(item).__module__}.{type(item).__qualname__}"
                        )
                        raise ValueError(
                            f"Node type {node.type_id!r} ID {node_id!r} output "
                            f"port {port.key!r}; declared candidates "
                            f"{self._candidate_type_ids(port)!r}; source semantic "
                            f"type {source_semantic_type!r}; concrete Python type "
                            f"{concrete_type}; "
                            f"DataPath {path!r}; item index {item_index}; catalog "
                            f"reasons: {'; '.join(reasons)}"
                        )
            if tree.branch_count:
                validated[port_key] = tree
        return validated

    def _settled_outputs(
        self,
        node_id: str,
        aggregates: Mapping[str, DataTree],
    ) -> dict[str, SettledPortResult]:
        outputs: dict[str, SettledPortResult] = {}
        node = self._plan.nodes[node_id]
        for port in self._plan.output_ports(node_id):
            tree = aggregates.get(port.key)
            if tree is None:
                outputs[port.key] = SettledPortResult(status="empty")
                continue
            modified = tree.apply_modifiers(node.port_modifiers.get(port.key, ()))
            outputs[port.key] = (
                SettledPortResult(status="value", value=modified)
                if modified.branch_count
                else SettledPortResult(status="empty")
            )
        return outputs

    def _execution_context(
        self,
        node_id: str,
        inputs: dict[str, Any],
        properties: Mapping[str, Any],
        *,
        target_path: tuple[int, ...],
        target_iteration: int,
        iteration_count: int,
    ) -> ExecutionContext:
        node = self._plan.nodes[node_id]
        node_spec = self._plan.node_specs[node_id]
        display_name = str(
            getattr(node_spec, "display_name", "")
            or getattr(node_spec, "name", "")
            or node.type_id
        )
        return ExecutionContext(
            run_id=self._publisher.run_id,
            node_id=node_id,
            workspace_id=self._publisher.workspace_id,
            inputs=inputs,
            properties=dict(properties),
            emit_log=lambda level, message: self._publisher.emit_log(
                level,
                message,
                node_id=node_id,
            ),
            trigger=self._trigger,
            target_path=target_path,
            target_iteration=target_iteration,
            iteration_count=iteration_count,
            should_stop=self._control.should_stop,
            register_cancel=self._control.register_cancel_callback,
            project_path=self._artifact_context_project_path,
            workspace_name=self._workspace_name,
            runtime_snapshot=self._runtime_snapshot,
            runtime_snapshot_context=self._runtime_context,
            path_resolver=self._artifact_service.resolve_path,
            worker_services=self._worker_services,
            developer_mode=self._developer_mode,
            node_title=node.title,
            node_type_id=node.type_id,
            node_type_display_name=display_name,
            node_port_labels=dict(node.port_labels),
            semantic_links=self._semantic_links_by_node[node_id],
            workspace_node_types=self._workspace_node_types,
            _publish_node_state=self._publish_node_state,
            _read_node_state=self._read_node_state,
            _request_observation_invalidation=lambda root_node_id, reason_code: (
                self._publisher.emit_observation_invalidation(
                    node_id, root_node_id, reason_code
                )
            ),
        )

    def _settle_empty(
        self,
        node_id: str,
        *,
        started_at_epoch_ms: float,
        warnings: Iterable[str] = (),
    ) -> str:
        return self._settle(
            node_id,
            {
                port.key: SettledPortResult(status="empty")
                for port in self._plan.output_ports(node_id)
            },
            status="empty",
            elapsed_ms=max(0.0, (time.time() * 1000.0) - started_at_epoch_ms),
            warnings=warnings,
            disposition="skipped",
        )

    def _settle_failed(
        self,
        node_id: str,
        errors: tuple[RootExecutionError, ...],
        *,
        status: str,
        started_at_epoch_ms: float,
    ) -> str:
        result = SettledPortResult(status="failed", errors=errors)
        return self._settle(
            node_id,
            {port.key: result for port in self._plan.output_ports(node_id)},
            status=status,
            elapsed_ms=max(0.0, (time.time() * 1000.0) - started_at_epoch_ms),
            errors=errors,
        )

    def _settle(
        self,
        node_id: str,
        outputs: Mapping[str, SettledPortResult],
        *,
        status: str,
        elapsed_ms: float,
        errors: Iterable[RootExecutionError] = (),
        warnings: Iterable[str] = (),
        disposition: str = "",
    ) -> str:
        settled = dict(outputs)
        self.node_outputs[node_id] = settled
        self.executed.add(node_id)
        decision = self._node_decisions.get(node_id)
        if decision is None:
            identity_fields = {}
        else:
            resolved_disposition = disposition or (
                "blocked" if status == "blocked" else "recomputed"
            )
            identity_fields = {
                "disposition": resolved_disposition,
                "decision_reason": decision.reason_code,
                "solution_key": decision.solution_key,
            }
        self._publisher.emit_node_settled(
            node_id,
            status,
            settled,
            elapsed_ms=elapsed_ms,
            errors=errors,
            warnings=warnings,
            **identity_fields,
        )
        return "ok"

    def _fail_node(
        self,
        node_id: str,
        exc: BaseException,
        *,
        started_at_epoch_ms: float,
    ) -> str:
        result = self._error_result(node_id, exc)
        self._publisher.emit_log("error", result.errors[0].error, node_id=node_id)
        return self._settle_failed(
            node_id,
            result.errors,
            status="failed",
            started_at_epoch_ms=started_at_epoch_ms,
        )

    def _error_result(self, node_id: str, exc: BaseException) -> SettledPortResult:
        traceback_text = (
            traceback.format_exc()
            if self._developer_mode
            else getattr(exc, "user_traceback", None) or traceback.format_exc()
        )
        return SettledPortResult(
            status="failed",
            errors=(
                RootExecutionError(
                    node_id=node_id,
                    error=_exception_message(exc),
                    traceback=traceback_text,
                ),
            ),
        )

    @staticmethod
    def _errors_from_results(
        results: Iterable[SettledPortResult],
    ) -> tuple[RootExecutionError, ...]:
        errors: list[RootExecutionError] = []
        seen: set[tuple[str, str, str]] = set()
        for result in results:
            if result.status != "failed":
                continue
            for error in result.errors:
                key = (error.node_id, error.error, error.traceback)
                if key in seen:
                    continue
                seen.add(key)
                errors.append(error)
        return tuple(errors)

    @staticmethod
    def _is_sequence(value: Any) -> bool:
        return isinstance(value, Sequence) and not isinstance(
            value,
            (str, bytes, bytearray),
        )


class WorkflowRunner:
    def __init__(
        self,
        command: StartRunCommand,
        event_queue: Queue,
        command_queue: Queue | None = None,
        worker_services: WorkerServices | None = None,
    ) -> None:
        self._command = command
        self._command_queue = command_queue
        self._worker_services = worker_services or WorkerServices()
        self._preflight_error: tuple[str, str, str] | None = None
        self._plan: ExecutionPlan | None = None
        self._executor: NodeExecutor | None = None
        self._viewer_invalidation_node_ids: tuple[str, ...] | None = ()
        self._buffered_preflight_commands: list[WorkerCommand] = []
        self._viewer_workspace_context: tuple[str, RuntimeSnapshot, RuntimeSnapshotContext] | None = None
        self._pruned_node_ids: set[str] = set()
        self._reused_outputs: dict[
            str,
            tuple[
                PreparedNodeDecision,
                AcceptedOutputPayload,
                dict[str, SettledPortResult],
                dict[str, SettledPortResult],
            ],
        ] = {}
        prepared = None
        data_types: DataTypeCatalog | None = None
        try:
            preflight_catalog = (
                DEFAULT_RUNTIME_PREPARATION_CACHE.default_registry(
                    command.addon_runtime_config
                ).data_types
            )
            mismatch = catalog_mismatch_message(
                command.catalog_fingerprint,
                command.catalog_revisions,
                preflight_catalog,
            )
            if mismatch:
                raise _CatalogAgreementMismatch(mismatch)
            candidate = prepare_runtime(command)
            data_types = candidate.registry.data_types
            mismatch = catalog_mismatch_message(
                command.catalog_fingerprint,
                command.catalog_revisions,
                data_types,
            )
            if mismatch:
                raise _CatalogAgreementMismatch(mismatch)
            self._worker_services.bind_data_types(data_types)
            prepared = candidate
        except _CatalogAgreementMismatch as exc:
            self._preflight_error = (
                _exception_message(exc),
                "",
                "catalog_mismatch",
            )
        except Exception as exc:  # noqa: BLE001
            self._preflight_error = (
                _exception_message(exc),
                traceback.format_exc(),
                "preflight_failed",
            )

        self._control = RunControl(
            command_queue,
            event_queue,
            run_id=command.run_id,
            workspace_id=command.workspace_id,
            data_types=data_types,
            viewer_command_handler=lambda viewer_command: dispatch_viewer_command(
                viewer_command,
                event_queue=event_queue,
                worker_services=self._worker_services,
            ),
            workspace_retirement_handler=(
                self._worker_services.mechanical_session_service.retire_workspace
            ),
        )
        self._publisher = RunEventPublisher(
            event_queue,
            run_id=command.run_id,
            workspace_id=command.workspace_id,
            data_types=data_types,
        )
        if prepared is None:
            return
        try:
            self._plan = prepared.plan
            artifact_service = RuntimeArtifactService(
                runtime_context=prepared.runtime_context,
                data_types=prepared.registry.data_types,
            )
            self._executor = NodeExecutor(
                prepared.plan,
                prepared.registry,
                self._control,
                self._publisher,
                artifact_service=artifact_service,
                worker_services=self._worker_services,
                project_path=command.project_path,
                runtime_snapshot=prepared.runtime_snapshot,
                runtime_context=prepared.runtime_context,
                plugin_runtime=prepared.plugin_runtime,
                trigger=dict(command.trigger),
                trigger_publications=command.trigger_publications,
                trigger_captures=command.trigger_captures,
                node_decisions={
                    decision.node_id: decision
                    for decision in command.node_decisions
                },
                developer_mode=command.developer_mode,
            )
            self._validate_prepared_command(prepared)
            viewer_node_ids = (
                None
                if not command.preparation_id
                else tuple(
                    decision.node_id
                    for decision in command.node_decisions
                    if decision.action is PreparedAction.EXECUTE
                    and prepared.plan.node_specs[decision.node_id].surface_family
                    == "viewer"
                )
            )
            if command.preparation_id and (
                viewer_node_ids != command.viewer_invalidation_node_ids
            ):
                raise ValueError(
                    "prepared viewer invalidation filter changed"
                )
            self._viewer_invalidation_node_ids = viewer_node_ids
            self._viewer_workspace_context = (
                command.project_path,
                prepared.runtime_snapshot,
                prepared.runtime_context,
            )
            if command.preparation_id:
                self._worker_services.viewer_session_service.validate_invalidation_snapshot(
                    workspace_id=command.workspace_id,
                    node_ids=command.viewer_invalidation_node_ids,
                    workspace_epoch=command.viewer_workspace_invalidation_epoch,
                    node_epochs=command.viewer_node_invalidation_epochs,
                    snapshot_digest=command.viewer_epoch_snapshot_digest,
                )
        except Exception as exc:  # noqa: BLE001
            self._preflight_error = (
                _exception_message(exc),
                traceback.format_exc(),
                "preflight_failed",
            )

    def _validate_prepared_command(self, prepared: Any) -> None:
        command = self._command
        if not command.preparation_id:
            return
        assert self._plan is not None
        assert self._executor is not None
        registry = prepared.registry
        if registry.contract_fingerprint() != command.registry_contract_fingerprint:
            raise ValueError("prepared registry contract fingerprint changed")
        if (
            canonical_digest(
                prepared.runtime_snapshot.to_document(catalog=registry.data_types)
            )
            != command.runtime_snapshot_fingerprint
        ):
            raise ValueError("prepared runtime snapshot fingerprint changed")
        if self._plan.fingerprint != command.execution_plan_fingerprint:
            raise ValueError("prepared execution plan fingerprint changed")
        interface_plan = ExecutionPlan(
            prepared.workspace,
            registry,
        )
        if (
            interface_plan.workflow_interface_revision
            != command.workflow_interface_revision
            or interface_plan.workflow_interface_digest
            != command.workflow_interface_digest
        ):
            raise ValueError("prepared workflow interface changed")
        expected_trigger_ids = tuple(
            sorted(
                node_id
                for node_id in self._plan.nodes
                if self._plan.is_trigger(node_id)
            )
        )
        if (
            tuple(
                node_id
                for node_id, _generation in command.trigger_publication_generations
            )
            != expected_trigger_ids
        ):
            raise ValueError("prepared trigger publication generations changed")
        scheduled_node_ids = tuple(
            node_id
            for node_id in self._plan.execution_order
            if self._plan.node_specs[node_id].runtime_behavior == "active"
        )
        if (
            tuple(decision.node_id for decision in command.node_decisions)
            != scheduled_node_ids
        ):
            raise ValueError("prepared decisions do not match scheduled node order")
        keys_by_node: dict[str, str] = {}
        actions_by_node: dict[str, PreparedAction] = {}
        reusable_keys: dict[str, bool] = {}
        executing_ancestry: dict[str, bool] = {}
        force_recompute = (
            RecomputeMode(command.recompute_mode) is RecomputeMode.FORCE_RECOMPUTE
        )
        boundaries = frozenset(
            item.node_id
            for item in command.node_decisions
            if item.action is PreparedAction.READ_CURRENT
        )
        if boundaries and (
            not self._plan.target_nodes
            or self._plan.clicked_trigger_node_id
            or force_recompute
        ):
            raise ValueError("current results require a partial consumer run")
        if any(
            node_id in self._plan.target_nodes or self._plan.is_trigger(node_id)
            for node_id in boundaries
        ):
            raise ValueError(
                "explicit targets and triggers cannot read current results"
            )
        required = self._plan.required_node_ids(boundaries)
        current_ports = self._plan.current_result_ports(boundaries)
        expected_pruned = set(scheduled_node_ids).difference(required)
        self._pruned_node_ids = {
            item.node_id
            for item in command.node_decisions
            if item.action is PreparedAction.PRUNE
        }
        if self._pruned_node_ids != expected_pruned:
            raise ValueError(
                "pruned decisions do not match current-result dependencies"
            )
        if force_recompute and any(
            item.action is not PreparedAction.EXECUTE for item in command.node_decisions
        ):
            raise ValueError(
                "force recompute requires execution of every scheduled node"
            )
        trigger_generations = dict(command.trigger_publication_generations)
        for decision in command.node_decisions:
            assembled = assemble_node_solution(
                preparation_id=command.preparation_id,
                solution_namespace_id=command.solution_namespace_id,
                workspace_solution_revision=(
                    command.execution_affecting_workspace_revision
                ),
                plan=self._plan,
                registry=registry,
                node_id=decision.node_id,
                keys_by_node=keys_by_node,
                execution_environment_digest=(command.execution_environment_digest),
                trigger_publication_generations=trigger_generations,
            )
            if (
                assembled.solution_key != decision.solution_key
                or assembled.dependency_solution_keys
                != decision.dependency_solution_keys
            ):
                raise ValueError("prepared node solution identity changed")
            reusable_lineage = (
                not assembled.reason_code
                and self._plan.node_specs[decision.node_id].solution_reuse_scope
                != "never"
                and all(
                    reusable_keys[key] for key in assembled.dependency_solution_keys
                )
            )
            reusable_keys[assembled.solution_key] = reusable_lineage
            if decision.action is PreparedAction.REUSE and not reusable_lineage:
                raise ValueError("prepared node is not eligible for reuse")
            if decision.action is PreparedAction.READ_CURRENT and assembled.reason_code:
                raise ValueError("current result identity is unavailable")
            upstream_execute = any(
                actions_by_node.get(edge.source_node_id) is PreparedAction.EXECUTE
                for edge in self._plan.incoming_edges_for(decision.node_id)
                if not self._plan.is_trigger(edge.source_node_id)
            ) or any(
                target == decision.node_id
                and actions_by_node.get(source) is PreparedAction.EXECUTE
                for source, target in self._plan.hidden_ordering_pairs
            )
            ancestor_execute = (
                upstream_execute
                or any(
                    executing_ancestry.get(edge.source_node_id, False)
                    for edge in self._plan.incoming_edges_for(decision.node_id)
                    if not self._plan.is_trigger(edge.source_node_id)
                )
                or any(
                    target == decision.node_id and executing_ancestry.get(source, False)
                    for source, target in self._plan.hidden_ordering_pairs
                )
            )
            executing_ancestry[decision.node_id] = ancestor_execute
            if decision.action.uses_accepted_output and ancestor_execute:
                raise ValueError("retained output has a recomputing dependency")
            reason = decision.reason_code
            if force_recompute:
                reason_valid = reason == "force_recompute"
            elif decision.action is PreparedAction.PRUNE:
                reason_valid = reason == "dependency_not_required"
            elif decision.action is PreparedAction.READ_CURRENT:
                reason_valid = reason == "current_result_accepted"
            elif decision.action is PreparedAction.REUSE:
                reason_valid = reason == "reusable_record_accepted"
            elif reason == "force_recompute":
                reason_valid = False
            elif assembled.reason_code:
                reason_valid = reason == assembled.reason_code
            elif (
                self._plan.node_specs[decision.node_id].solution_reuse_scope == "never"
            ):
                reason_valid = reason == "solution_reuse_scope_never"
            elif reason in {
                "execution_generation_unavailable",
                "execution_environment_unavailable",
            }:
                reason_valid = True
            elif upstream_execute:
                reason_valid = reason == "upstream_recompute_required"
            elif not reusable_lineage:
                reason_valid = reason == "volatile_dependency"
            else:
                reason_valid = reason in {
                    "no_reusable_record",
                    "accepted_output_invalid",
                    "reuse_payload_budget_exceeded",
                }
            if not reason_valid:
                raise ValueError("prepared node action and reason are contradictory")
            keys_by_node[decision.node_id] = decision.solution_key
            actions_by_node[decision.node_id] = decision.action
        accepted_by_node = {
            item.node_id: AcceptedOutputPayload.from_payload(
                item.to_payload(catalog=registry.data_types),
                catalog=registry.data_types,
            )
            for item in command.accepted_output_payloads
        }
        for decision in command.node_decisions:
            if not decision.action.uses_accepted_output:
                continue
            payload = accepted_by_node[decision.node_id]
            if (
                payload.record_id != decision.accepted_record_id
                or payload.solution_key != decision.solution_key
                or payload.commitment_digest() != decision.accepted_payload_digest
            ):
                raise ValueError(
                    "accepted output does not match its decision commitments"
                )
            if decision.action is PreparedAction.READ_CURRENT:
                validate_current_output_payload(
                    payload,
                    catalog=registry.data_types,
                    port_keys=current_ports[decision.node_id],
                )
            elif payload.output_digest != payload.result_digest:
                raise ValueError("computation reuse requires complete recorded outputs")
            outputs_payload = settled_outputs_to_payload(
                payload.decode_outputs(catalog=registry.data_types),
                catalog=registry.data_types,
            )
            result_digest = hashlib.sha256(
                json.dumps(
                    outputs_payload,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            if result_digest != payload.output_digest:
                raise ValueError("prepared accepted output digest changed")
            installed, event_outputs = self._executor.validate_reused_output(
                payload,
                port_keys=current_ports.get(decision.node_id),
            )
            self._reused_outputs[decision.node_id] = (
                decision,
                payload,
                installed,
                event_outputs,
            )

    def _await_run_preflight_commit(self) -> tuple[bool, str]:
        command_queue = self._command_queue
        if command_queue is None:
            return False, "run_preflight_commit_queue_unavailable"
        deadline = time.monotonic() + _RUN_PREFLIGHT_COMMIT_TIMEOUT_SEC
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return False, "run_preflight_commit_timeout"
            try:
                raw_command = command_queue.get(timeout=min(remaining, 0.25))
            except queue.Empty:
                continue
            command = decode_command_payload(
                raw_command,
                event_queue=self._control._event_queue,  # noqa: SLF001
                catalog=self._control._data_types,  # noqa: SLF001
            )
            if command is None:
                continue
            if isinstance(command, (CommitRunPreflightCommand, CancelRunPreflightCommand)):
                matches = (
                    command.run_id == self._command.run_id
                    and command.viewer_invalidation_reservation_id
                    == self._command.viewer_invalidation_reservation_id
                    and command.viewer_epoch_snapshot_digest
                    == self._command.viewer_epoch_snapshot_digest
                )
                if not matches:
                    emit_protocol_error(
                        self._control._event_queue,  # noqa: SLF001
                        "Run preflight acknowledgment does not match the reservation.",
                        run_id=command.run_id,
                        workspace_id=self._command.workspace_id,
                        command=command.type,
                        catalog=self._control._data_types,  # noqa: SLF001
                    )
                    continue
                return (
                    isinstance(command, CommitRunPreflightCommand),
                    "" if isinstance(command, CommitRunPreflightCommand)
                    else "run_preflight_cancelled",
                )
            if isinstance(command, (ShutdownCommand, StopRunCommand)):
                self._control._handle_command(command)  # noqa: SLF001
                return False, self._control.stop_reason or "run_preflight_cancelled"
            if is_viewer_command(command):
                self._buffered_preflight_commands.append(command)
                continue
            self._control._handle_command(command)  # noqa: SLF001

    def _dispatch_buffered_preflight_commands(self) -> None:
        buffered = tuple(self._buffered_preflight_commands)
        self._buffered_preflight_commands.clear()
        for command in buffered:
            self._control._handle_command(command)  # noqa: SLF001

    def run(self) -> None:
        succeeded = False
        try:
            self._worker_services.mechanical_session_service.begin_run(
                self._command.run_id,
                self._command.workspace_id,
            )
            if self._preflight_error is not None:
                error, traceback_text, reason = self._preflight_error
                self._publisher.emit_run_failed(
                    node_id="",
                    error=error,
                    traceback_text=traceback_text,
                    reason=reason,
                )
                return
            assert self._plan is not None
            assert self._executor is not None
            if self._command.preparation_id:
                self._publisher.emit_run_preflight_accepted(
                    preparation_id=self._command.preparation_id,
                    reservation_id=(
                        self._command.viewer_invalidation_reservation_id
                    ),
                    snapshot_digest=self._command.viewer_epoch_snapshot_digest,
                )
                committed, cancel_reason = self._await_run_preflight_commit()
                if not committed:
                    self._buffered_preflight_commands.clear()
                    self._publisher.emit_run_failed(
                        node_id="",
                        error=cancel_reason,
                        traceback_text="",
                        reason=cancel_reason,
                    )
                    return
                assert self._viewer_workspace_context is not None
                project_path, runtime_snapshot, runtime_context = (
                    self._viewer_workspace_context
                )
                try:
                    self._worker_services.viewer_session_service.adopt_invalidation_snapshot(
                        workspace_id=self._command.workspace_id,
                        node_ids=self._command.viewer_invalidation_node_ids,
                        workspace_epoch=(
                            self._command.viewer_workspace_invalidation_epoch
                        ),
                        node_epochs=self._command.viewer_node_invalidation_epochs,
                        snapshot_digest=self._command.viewer_epoch_snapshot_digest,
                        reason="workspace_rerun",
                        buffered_viewer_commands=bool(
                            self._buffered_preflight_commands
                        ),
                    )
                except Exception:
                    self._publisher.emit_run_started()
                    raise
                self._publisher.emit_run_started()
                self._worker_services.viewer_session_service.install_workspace_context(
                    workspace_id=self._command.workspace_id,
                    project_path=project_path,
                    runtime_snapshot=runtime_snapshot,
                    runtime_snapshot_context=runtime_context,
                )
                self._dispatch_buffered_preflight_commands()
            else:
                assert self._viewer_workspace_context is not None
                project_path, runtime_snapshot, runtime_context = (
                    self._viewer_workspace_context
                )
                self._worker_services.viewer_session_service.install_workspace_context(
                    workspace_id=self._command.workspace_id,
                    project_path=project_path,
                    runtime_snapshot=runtime_snapshot,
                    runtime_snapshot_context=runtime_context,
                )
                self._worker_services.viewer_session_service.invalidate_workspace(
                    self._command.workspace_id,
                    reason="workspace_rerun",
                    node_ids=None,
                )
                self._publisher.emit_run_started()
            self._publisher.emit_log("info", "Workflow run started.")
            self._publisher.emit_log(
                "info",
                (
                    "Execution backend selected: "
                    f"{self._command.execution_backend.backend_id} "
                    f"({self._command.execution_backend.reason})."
                ),
            )
            for node_id in self._plan.execution_order:
                if node_id in self._pruned_node_ids:
                    continue
                reused = self._reused_outputs.get(node_id)
                status = (
                    self._executor.install_accepted_output(*reused)
                    if reused is not None
                    else self._executor.run_node(node_id)
                )
                if status == "stopped":
                    self._publisher.emit_run_stopped(
                        self._control.stop_reason or "stop_requested"
                    )
                    return
            self._executor.refresh_trigger_captures()
            if self._control.should_stop():
                self._publisher.emit_run_stopped(
                    self._control.stop_reason or "stop_requested"
                )
                return
            self._executor.publish_pending_trigger()
            self._publisher.emit_run_completed()
            succeeded = True
        except Exception as exc:  # noqa: BLE001
            self._publisher.emit_run_failed(
                node_id="",
                error=_exception_message(exc),
                traceback_text=traceback.format_exc(),
                reason="worker_exception",
            )
        finally:
            if self._executor is not None:
                self._executor.clear_run_state()
            self._worker_services.cleanup_run(
                self._command.run_id,
                succeeded=succeeded,
                warn=lambda message: self._publisher.emit_log(
                    "warning",
                    message,
                ),
            )


__all__ = [
    "NodeExecutor",
    "RunControl",
    "RunEventPublisher",
    "WorkflowRunner",
]
