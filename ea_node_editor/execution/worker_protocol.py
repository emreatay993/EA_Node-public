from __future__ import annotations

from multiprocessing import Queue
from typing import Any

from ea_node_editor.common.payload_tools import copy_json_safe
from ea_node_editor.execution.viewer_messages import (
    CloseViewerSessionCommand,
    MaterializeViewerDataCommand,
    OpenViewerSessionCommand,
    UpdateViewerSessionCommand,
    ViewerSessionFailedEvent,
)
from ea_node_editor.execution.run_messages import (
    ProtocolErrorEvent,
    RunFailedEvent,
    RunStateEvent,
)
from ea_node_editor.execution.protocol_codec import (
    WorkerCommand,
    WorkerEvent,
    dict_to_command,
    event_to_dict,
)
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement_from_payload,
    catalog_mismatch_message,
    normalize_addon_runtime_config,
)
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.runtime_contracts import DataTypeCatalog
_CORRELATION_TEXT_LIMIT = 256


def emit(
    event_queue: Queue,
    event: WorkerEvent,
    *,
    catalog: DataTypeCatalog | None = None,
) -> None:
    event_queue.put(event_to_dict(event, catalog=catalog))


def emit_run_state(
    event_queue: Queue,
    *,
    run_id: str,
    workspace_id: str,
    state: str,
    transition: str,
    reason: str,
    catalog: DataTypeCatalog | None = None,
) -> None:
    emit(
        event_queue,
        RunStateEvent(
            run_id=run_id,
            workspace_id=workspace_id,
            state=state,  # type: ignore[arg-type]
            transition=transition,
            reason=reason,
        ),
        catalog=catalog,
    )


def emit_protocol_error(
    event_queue: Queue,
    message: str,
    *,
    run_id: str = "",
    workspace_id: str = "",
    request_id: str = "",
    command: str = "",
    catalog: DataTypeCatalog | None = None,
) -> None:
    emit(
        event_queue,
        ProtocolErrorEvent(
            run_id=run_id,
            workspace_id=workspace_id,
            request_id=request_id,
            command=command,
            error=message,
        ),
        catalog=catalog,
    )


def is_viewer_command(command: WorkerCommand) -> bool:
    return isinstance(
        command,
        (
            OpenViewerSessionCommand,
            UpdateViewerSessionCommand,
            CloseViewerSessionCommand,
            MaterializeViewerDataCommand,
        ),
    )


def command_payload_type(raw_command: Any) -> str:
    """Read only the command discriminator without decoding runtime payloads."""

    if not isinstance(raw_command, dict):
        return ""
    command_type = raw_command.get("type")
    if not isinstance(command_type, str):
        return ""
    return command_type.strip()


def _safe_correlation_text(raw_command: dict[str, Any], field_name: str) -> str:
    value = raw_command.get(field_name)
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        return ""
    return value[:_CORRELATION_TEXT_LIMIT]


def dispatch_viewer_command(
    command: WorkerCommand,
    *,
    event_queue: Queue,
    worker_services: WorkerServices,
) -> None:
    data_types: DataTypeCatalog | None = None
    try:
        data_types = worker_services.data_types
        event = worker_services.viewer_session_service.handle_command(command)
    except Exception as exc:  # noqa: BLE001
        event = ViewerSessionFailedEvent(
            request_id=str(getattr(command, "request_id", "")).strip(),
            workspace_id=str(getattr(command, "workspace_id", "")).strip(),
            node_id=str(getattr(command, "node_id", "")).strip(),
            session_id=str(getattr(command, "session_id", "")).strip(),
            command=str(getattr(command, "type", "")).strip(),
            error=str(exc).strip() or "viewer session dispatch failed",
            workspace_invalidation_epoch=int(
                getattr(command, "workspace_invalidation_epoch", 0)
            ),
            node_invalidation_epoch=int(
                getattr(command, "node_invalidation_epoch", 0)
            ),
        )
    emit(event_queue, event, catalog=data_types)


def decode_command_payload(
    raw_command: Any,
    *,
    event_queue: Queue,
    catalog: DataTypeCatalog | None = None,
    runtime_cache: Any = None,
    worker_services: WorkerServices | None = None,
) -> WorkerCommand | None:
    if not isinstance(raw_command, dict):
        emit_protocol_error(event_queue, "Command payload must be a dictionary.")
        return None
    try:
        payload = copy_json_safe(raw_command, field_name="worker command")
        command_type = str(payload.get("type", "")).strip()
        request_id = str(payload.get("request_id", "")).strip()
        active_catalog = catalog
        if active_catalog is None and worker_services is not None:
            try:
                active_catalog = worker_services.data_types
            except ValueError:
                pass
        if command_type == "start_run":
            raw_snapshot = payload.get("runtime_snapshot")
            if not isinstance(raw_snapshot, dict):
                raise ValueError("start_run requires runtime_snapshot.")
            raw_run_id = payload.get("run_id")
            if not isinstance(raw_run_id, str) or not raw_run_id.strip():
                raise ValueError("start_run requires a string run_id.")
            raw_workspace_id = payload.get("workspace_id")
            if not isinstance(raw_workspace_id, str) or not raw_workspace_id.strip():
                raise ValueError("start_run requires a string workspace_id.")
            from ea_node_editor.execution.worker_runtime import (
                DEFAULT_RUNTIME_PREPARATION_CACHE,
            )

            cache = runtime_cache or DEFAULT_RUNTIME_PREPARATION_CACHE
            addon_runtime_config = normalize_addon_runtime_config(
                payload.get("addon_runtime_config", ())
            )
            registry = cache.default_registry(addon_runtime_config)
            active_catalog = registry.data_types
            expected_fingerprint, expected_revisions = (
                catalog_agreement_from_payload(payload)
            )
            mismatch = catalog_mismatch_message(
                expected_fingerprint,
                expected_revisions,
                active_catalog,
            )
            if mismatch:
                emit(
                    event_queue,
                    RunFailedEvent(
                        run_id=raw_run_id.strip(),
                        workspace_id=raw_workspace_id.strip(),
                        error=mismatch,
                    ),
                )
                emit_run_state(
                    event_queue,
                    run_id=raw_run_id.strip(),
                    workspace_id=raw_workspace_id.strip(),
                    state="error",
                    transition="fail",
                    reason="catalog_mismatch",
                )
                return None
            command = dict_to_command(dict(payload), catalog=active_catalog)
            if worker_services is not None:
                worker_services.bind_data_types(active_catalog)
            return command
        return dict_to_command(dict(payload), catalog=active_catalog)
    except (TypeError, ValueError) as exc:
        command_type = _safe_correlation_text(raw_command, "type")
        run_id = _safe_correlation_text(raw_command, "run_id")
        workspace_id = _safe_correlation_text(raw_command, "workspace_id")
        emit_protocol_error(
            event_queue,
            (
                "Invalid start_run command payload."
                if command_type == "start_run"
                else f"Invalid command payload: {exc}"
            ),
            run_id=run_id,
            workspace_id=workspace_id,
            request_id=_safe_correlation_text(raw_command, "request_id"),
            command=command_type,
        )
        if command_type == "start_run" and run_id:
            emit(
                event_queue,
                RunFailedEvent(
                    run_id=run_id,
                    workspace_id=workspace_id,
                    error="Invalid start_run command payload.",
                ),
            )
            emit_run_state(
                event_queue,
                run_id=run_id,
                workspace_id=workspace_id,
                state="error",
                transition="fail",
                reason="invalid_start_run",
            )
        return None


__all__ = [
    "command_payload_type",
    "decode_command_payload",
    "dispatch_viewer_command",
    "emit",
    "emit_protocol_error",
    "emit_run_state",
    "is_viewer_command",
]
