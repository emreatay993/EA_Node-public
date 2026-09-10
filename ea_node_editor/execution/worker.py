from __future__ import annotations

import traceback
from multiprocessing import Queue

from ea_node_editor.execution.run_messages import (
    PauseRunCommand,
    ResumeRunCommand,
    RunFailedEvent,
    RetireWorkspaceCommand,
    ShutdownCommand,
    StartRunCommand,
    StopRunCommand,
    WorkspaceRetiredEvent,
)
from ea_node_editor.execution.worker_protocol import (
    decode_command_payload,
    dispatch_viewer_command,
    emit,
    emit_protocol_error,
    emit_run_state,
    is_viewer_command,
)
from ea_node_editor.execution.worker_runner import WorkflowRunner
from ea_node_editor.execution.worker_services import WorkerServices


def run_workflow(
    command: StartRunCommand,
    event_queue: Queue,
    command_queue: Queue | None = None,
    worker_services: WorkerServices | None = None,
) -> None:
    WorkflowRunner(
        command,
        event_queue,
        command_queue=command_queue,
        worker_services=worker_services,
    ).run()


def worker_main(
    command_queue: Queue,
    event_queue: Queue,
    worker_services: WorkerServices | None = None,
) -> None:
    services = worker_services or WorkerServices()
    needs_final_reset = True
    try:
        while True:
            raw_command = command_queue.get()
            command = decode_command_payload(
                raw_command,
                event_queue=event_queue,
                worker_services=services,
            )
            if command is None:
                continue

            if isinstance(command, ShutdownCommand):
                break
            if isinstance(command, RetireWorkspaceCommand):
                retired = services.mechanical_session_service.retire_workspace(
                    command.workspace_id
                )
                emit(
                    event_queue,
                    WorkspaceRetiredEvent(
                        request_id=command.request_id,
                        workspace_id=command.workspace_id,
                        retired_count=str(retired),
                    ),
                    catalog=(
                        services.data_types
                        if services.handle_registry.is_catalog_bound
                        else None
                    ),
                )
                continue
            needs_final_reset = True
            if isinstance(command, StartRunCommand):
                try:
                    run_workflow(
                        command,
                        event_queue,
                        command_queue=command_queue,
                        worker_services=services,
                    )
                except Exception as exc:  # noqa: BLE001
                    services.reset()
                    needs_final_reset = False
                    emit(
                        event_queue,
                        RunFailedEvent(
                            run_id=command.run_id,
                            workspace_id=command.workspace_id,
                            error=str(exc),
                            traceback=traceback.format_exc(),
                        ),
                        catalog=services.data_types,
                    )
                    emit_run_state(
                        event_queue,
                        run_id=command.run_id,
                        workspace_id=command.workspace_id,
                        state="error",
                        transition="fail",
                        reason="worker_exception",
                        catalog=services.data_types,
                    )
            elif isinstance(command, StopRunCommand):
                emit_protocol_error(
                    event_queue,
                    "No active run to stop.",
                    run_id=command.run_id,
                    workspace_id=command.workspace_id,
                    request_id=getattr(command, "request_id", ""),
                    command=command.type,
                )
            elif isinstance(command, (PauseRunCommand, ResumeRunCommand)):
                emit_protocol_error(
                    event_queue,
                    "No active run for command.",
                    run_id=command.run_id,
                    workspace_id="",
                    request_id=getattr(command, "request_id", ""),
                    command=command.type,
                )
            elif is_viewer_command(command):
                dispatch_viewer_command(
                    command,
                    event_queue=event_queue,
                    worker_services=services,
                )
            else:
                emit_protocol_error(
                    event_queue,
                    "Unknown command type.",
                    run_id=getattr(command, "run_id", ""),
                    workspace_id=getattr(command, "workspace_id", ""),
                    request_id=getattr(command, "request_id", ""),
                    command=getattr(command, "type", ""),
                )
    finally:
        if needs_final_reset:
            services.reset()
