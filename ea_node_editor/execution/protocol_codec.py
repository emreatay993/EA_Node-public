# Purpose: Encode and decode typed worker commands and events at transport boundaries.
# Map: subsystems/execution.md
# Tests: tests/test_protocol_codec.py, tests/test_execution_viewer_protocol.py
# Landmarks: command_to_dict; event_to_dict; coerce_start_run_command; dict_to_command; dict_to_event

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, replace
import json
from typing import Any, TypeAlias

from ea_node_editor.common.payload_tools import copy_json_safe
from ea_node_editor.execution.backends import (
    ExecutionBackendSelection,
    coerce_execution_backend_selection,
)
from ea_node_editor.execution.prepared_execution import (
    MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION,
    MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES,
    MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION,
    MAX_PREPARED_NODES,
    AcceptedOutputPayload,
    PreparedAction,
    PreparedNodeDecision,
    RecomputeMode,
    normalize_trigger_publication_generations,
)
from ea_node_editor.execution.registry_agreement import (
    _addon_runtime_config_payload,
    _bounded_catalog_text,
    _catalog_fingerprint,
    _catalog_revision_payload,
    _plugin_agreement,
    _plugin_bundle_payload,
    _plugin_fingerprint,
    _sha256_digest,
    catalog_agreement,
    catalog_agreement_from_payload,
    catalog_mismatch_message,
    normalize_addon_runtime_config,
    normalize_catalog_revisions,
    normalize_plugin_bundle_refs,
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.run_messages import (
    CancelRunPreflightCommand,
    CommitRunPreflightCommand,
    LogEvent,
    NodeSettledEvent,
    NodeStartedEvent,
    ObservationInvalidationRequestedEvent,
    PauseRunCommand,
    ProtocolErrorEvent,
    ResumeRunCommand,
    RetireWorkspaceCommand,
    RunCompletedEvent,
    RunFailedEvent,
    RunPreflightAcceptedEvent,
    RunStartedEvent,
    RunStateEvent,
    RunStoppedEvent,
    ShutdownCommand,
    StartRunCommand,
    StopRunCommand,
    WorkspaceRetiredEvent,
    TriggerCaptureSettledEvent,
    TriggerPublishedEvent,
    normalize_target_node_ids,
)
from ea_node_editor.execution.viewer_messages import (
    CloseViewerSessionCommand,
    MaterializeViewerDataCommand,
    OpenViewerSessionCommand,
    QueryViewerSessionCommand,
    UpdateViewerSessionCommand,
    ViewerDataMaterializedEvent,
    ViewerQueryResultEvent,
    ViewerSessionClosedEvent,
    ViewerSessionFailedEvent,
    ViewerSessionOpenedEvent,
    ViewerSessionUpdatedEvent,
    normalize_viewer_invalidation_fields,
)
from ea_node_editor.execution.runtime_snapshot import coerce_runtime_snapshot
from ea_node_editor.nodes.function_plugin import EMPTY_PLUGIN_FINGERPRINT
from ea_node_editor.runtime_contracts import (
    DataTree,
    DataTypeCatalog,
    deserialize_runtime_value,
    serialize_runtime_value,
)
from ea_node_editor.runtime_contracts import settled_results as _settled
from ea_node_editor.runtime_contracts.solution_records import SolutionResidency
from ea_node_editor.execution.transport_fields import (
    bool_field as _bool_field,
    float_field as _float_field,
    nonnegative_int_field as _nonnegative_int_field,
    string_field as _string_field,
    string_list_field as _string_list_field,
    bool_value as _bool_value,
    float_value as _float_value,
    nonnegative_int_value as _nonnegative_int_value,
    string_value as _string_value,
)

WorkerCommand: TypeAlias = (
    StartRunCommand
    | StopRunCommand
    | PauseRunCommand
    | ResumeRunCommand
    | ShutdownCommand
    | CommitRunPreflightCommand
    | CancelRunPreflightCommand
    | RetireWorkspaceCommand
    | OpenViewerSessionCommand
    | UpdateViewerSessionCommand
    | CloseViewerSessionCommand
    | QueryViewerSessionCommand
    | MaterializeViewerDataCommand
)
WorkerEvent: TypeAlias = (
    RunPreflightAcceptedEvent
    | RunStartedEvent
    | RunStateEvent
    | RunCompletedEvent
    | RunFailedEvent
    | RunStoppedEvent
    | NodeStartedEvent
    | NodeSettledEvent
    | ObservationInvalidationRequestedEvent
    | TriggerCaptureSettledEvent
    | TriggerPublishedEvent
    | LogEvent
    | ProtocolErrorEvent
    | WorkspaceRetiredEvent
    | ViewerSessionOpenedEvent
    | ViewerSessionUpdatedEvent
    | ViewerSessionClosedEvent
    | ViewerDataMaterializedEvent
    | ViewerQueryResultEvent
    | ViewerSessionFailedEvent
)

_RUNTIME_VALUE_MARKER_KEY = "__ea_runtime_value__"
_VIEWER_RUNTIME_MARKERS = frozenset(
    {
        "artifact_ref",
        "handle_ref",
        "tabular_data_ref",
        "array_data_ref",
        "tabular_window_ref",
        "array_slice_2d_ref",
        "data_tree",
    }
)
_SCALAR_PROTOCOL_TYPES = frozenset(
    {
        StopRunCommand,
        PauseRunCommand,
        ResumeRunCommand,
        ShutdownCommand,
        CommitRunPreflightCommand,
        CancelRunPreflightCommand,
        RetireWorkspaceCommand,
        RunPreflightAcceptedEvent,
        RunStartedEvent,
        RunStateEvent,
        RunCompletedEvent,
        RunFailedEvent,
        RunStoppedEvent,
        NodeStartedEvent,
        ObservationInvalidationRequestedEvent,
        LogEvent,
        ProtocolErrorEvent,
        WorkspaceRetiredEvent,
        ViewerSessionFailedEvent,
    }
)
_ENGINE_STATE_VALUES = frozenset({"ready", "running", "paused", "error"})
_RUN_TRANSITION_VALUES = frozenset(
    {"", "start", "pause", "resume", "stop", "complete", "fail"}
)
_FIXED_RUN_EVENT_STATES = {
    RunCompletedEvent: "ready",
    RunFailedEvent: "error",
    RunStoppedEvent: "ready",
}


def _execution_backend_from_payload(
    payload: Mapping[str, Any],
) -> ExecutionBackendSelection:
    if "execution_backend" not in payload:
        return ExecutionBackendSelection()
    value = payload["execution_backend"]
    if not isinstance(value, Mapping):
        raise ValueError("execution_backend must be a mapping.")
    normalized = {
        "backend_id": _string_field(
            value,
            "backend_id",
            default=ExecutionBackendSelection().backend_id,
            strip=True,
        ),
        "isolation": _string_field(
            value,
            "isolation",
            default="process",
            strip=True,
        ),
        "reason": _string_field(value, "reason", strip=True),
        "trusted_in_process": _bool_field(value, "trusted_in_process"),
        "external_subprocess": _bool_field(value, "external_subprocess"),
        "python_executable": _string_field(
            value,
            "python_executable",
            strip=True,
        ),
        "runtime_backend_ids": _string_list_field(value, "runtime_backend_ids"),
    }
    return coerce_execution_backend_selection(normalized)


def _literal_value(
    value: Any,
    *,
    field_name: str,
    allowed_values: frozenset[str],
) -> str:
    normalized = _string_value(value, field_name=field_name)
    if normalized not in allowed_values:
        raise ValueError(f"invalid {field_name}: {normalized!r}")
    return normalized


def _literal_field(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    allowed_values: frozenset[str],
    default: str,
) -> str:
    return _literal_value(
        _string_field(payload, field_name, default=default),
        field_name=field_name,
        allowed_values=allowed_values,
    )


def _settlement_identity_fields(
    *,
    status: str,
    disposition: Any,
    decision_reason: Any,
    solution_key: Any,
    record_id: Any,
    residency: Any,
) -> dict[str, str]:
    normalized_disposition = (
        _string_value(disposition, field_name="disposition").strip().lower()
    )
    reason = _string_value(decision_reason, field_name="decision_reason").strip()
    key = _string_value(solution_key, field_name="solution_key").strip()
    normalized_record_id = _string_value(record_id, field_name="record_id").strip()
    normalized_residency = _string_value(residency, field_name="residency").strip()
    if not normalized_disposition:
        if (
            reason != "legacy_direct_run"
            or key
            or normalized_record_id
            or normalized_residency
        ):
            raise ValueError("legacy settlement identity fields are invalid")
    else:
        if normalized_disposition not in {
            "reused",
            "recomputed",
            "skipped",
            "blocked",
        }:
            raise ValueError(
                f"invalid solution disposition: {normalized_disposition!r}"
            )
        if not reason:
            raise ValueError("prepared settlements require decision_reason")
        key = _sha256_digest(key, field_name="solution_key")
        if normalized_disposition == "reused":
            if status not in {"completed", "empty"}:
                raise ValueError("reused settlements must be completed or empty")
            if not normalized_record_id or normalized_residency not in {
                "session",
                "durable",
            }:
                raise ValueError("reused settlements require record_id and residency")
        else:
            if normalized_record_id or normalized_residency:
                raise ValueError(
                    "non-reused settlements forbid record_id and residency"
                )
            if normalized_disposition == "recomputed" and status not in {
                "completed",
                "empty",
                "failed",
            }:
                raise ValueError("recomputed settlement status is invalid")
            if normalized_disposition == "skipped" and status != "empty":
                raise ValueError("skipped settlements must be empty")
            if normalized_disposition == "blocked" and status != "blocked":
                raise ValueError("blocked dispositions require blocked status")
    return {
        "disposition": normalized_disposition,
        "decision_reason": reason,
        "solution_key": key,
        "record_id": normalized_record_id,
        "residency": normalized_residency,
    }


def _fixed_run_event_state(
    payload: Mapping[str, Any],
    *,
    expected: str,
) -> str:
    state = _string_field(payload, "state", default=expected)
    if state != expected:
        raise ValueError(f"state must be {expected!r}.")
    return state


def _serialize_scalar_payload(
    value: Any,
    *,
    catalog: DataTypeCatalog | None,
) -> dict[str, Any]:
    if type(value) not in _SCALAR_PROTOCOL_TYPES:
        raise TypeError(f"Unsupported protocol DTO: {type(value).__name__}")
    if type(value) is RunStateEvent:
        _literal_value(
            value.state,
            field_name="state",
            allowed_values=_ENGINE_STATE_VALUES,
        )
        _literal_value(
            value.transition,
            field_name="transition",
            allowed_values=_RUN_TRANSITION_VALUES,
        )
    expected_state = _FIXED_RUN_EVENT_STATES.get(type(value))
    if expected_state is not None and value.state != expected_state:
        actual_state = _string_value(value.state, field_name="state")
        raise ValueError(
            f"state must be {expected_state!r}; received {actual_state!r}."
        )
    payload: dict[str, Any] = {}
    for field_info in fields(value):
        field_value = getattr(value, field_info.name)
        if field_info.name == "fatal":
            field_value = _bool_value(field_value, field_name=field_info.name)
        elif field_info.name == "started_at_epoch_ms":
            field_value = _float_value(field_value, field_name=field_info.name)
        else:
            field_value = _string_value(field_value, field_name=field_info.name)
        payload[field_info.name] = serialize_runtime_value(
            field_value,
            catalog=catalog,
        )
    return payload


def _serialize_viewer_value(
    value: Any,
    *,
    field_name: str,
    catalog: DataTypeCatalog | None,
) -> Any:
    try:
        serialized = serialize_runtime_value(value, catalog=catalog)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be JSON-safe: {exc}") from exc
    if serialized is None or isinstance(serialized, (str, int, float, bool)):
        return serialized
    if isinstance(serialized, list):
        return [
            _serialize_viewer_value(item, field_name=field_name, catalog=catalog)
            for item in serialized
        ]
    if isinstance(serialized, tuple):
        return [
            _serialize_viewer_value(item, field_name=field_name, catalog=catalog)
            for item in serialized
        ]
    if isinstance(serialized, Mapping):
        marker = serialized.get(_RUNTIME_VALUE_MARKER_KEY)
        if marker in _VIEWER_RUNTIME_MARKERS:
            return dict(serialized)
        normalized: dict[str, Any] = {}
        for key, item in serialized.items():
            if not isinstance(key, str):
                raise TypeError(f"{field_name} keys must be strings.")
            normalized[key] = _serialize_viewer_value(
                item,
                field_name=field_name,
                catalog=catalog,
            )
        return normalized
    raise TypeError(
        f"{field_name} must be JSON-safe and may only contain scalar values, lists, "
        "dictionaries, runtime handle refs, or runtime artifact refs."
    )


def _serialize_viewer_mapping(
    value: Any,
    *,
    field_name: str,
    catalog: DataTypeCatalog | None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a dictionary payload.")
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{field_name} keys must be strings.")
        normalized[key] = _serialize_viewer_value(
            item,
            field_name=field_name,
            catalog=catalog,
        )
    return normalized


def _deserialize_viewer_mapping(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    catalog: DataTypeCatalog | None,
) -> dict[str, Any]:
    if field_name not in payload:
        return {}
    value = payload[field_name]
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a dictionary payload.")
    decoded = deserialize_runtime_value(value, catalog=catalog)
    if not isinstance(decoded, Mapping):
        raise ValueError(f"{field_name} must decode to a dictionary payload.")
    if any(not isinstance(key, str) for key in decoded):
        raise ValueError(f"{field_name} keys must be strings.")
    return dict(decoded)


def _prepared_node_decisions(value: Any) -> tuple[PreparedNodeDecision, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("node_decisions must be a list")
    if len(value) > MAX_PREPARED_NODES:
        raise ValueError(f"node_decisions exceeds maximum count {MAX_PREPARED_NODES}")
    decisions = tuple(
        PreparedNodeDecision.from_payload(
            item.to_payload() if isinstance(item, PreparedNodeDecision) else item
        )
        for item in value
    )
    node_ids = tuple(item.node_id for item in decisions)
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("node_decisions must not contain duplicate node IDs")
    solution_keys = tuple(item.solution_key for item in decisions)
    if len(solution_keys) != len(set(solution_keys)):
        raise ValueError("node_decisions cannot share cross-node solution keys")
    return decisions


def _accepted_output_payloads(
    value: Any,
    *,
    catalog: DataTypeCatalog | None,
) -> tuple[AcceptedOutputPayload, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("accepted_output_payloads must be a list")
    if len(value) > MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION:
        raise ValueError(
            "accepted_output_payloads exceeds maximum count "
            f"{MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION}"
        )
    accepted = tuple(
        AcceptedOutputPayload.from_payload(
            item.to_payload(catalog=catalog)
            if isinstance(item, AcceptedOutputPayload)
            else item,
            catalog=catalog,
        )
        for item in value
    )
    if (
        sum(item.output_count for item in accepted)
        > MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION
    ):
        raise ValueError(
            "accepted output port results exceed maximum count "
            f"{MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION}"
        )
    encoded_size = len(
        json.dumps(
            {
                "accepted_output_payloads": [
                    item.to_payload(catalog=catalog) for item in accepted
                ]
            },
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    if encoded_size > MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES:
        raise ValueError(
            "accepted_output_payloads exceeds maximum encoded size "
            f"{MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES} bytes"
        )
    return accepted


def _normalize_prepared_start_fields(
    *,
    preparation_id: Any,
    solution_namespace_id: Any,
    execution_affecting_workspace_revision: Any,
    dispatch_runtime_generation: Any,
    runtime_snapshot_fingerprint: Any,
    execution_plan_fingerprint: Any,
    workflow_interface_revision: Any,
    workflow_interface_digest: Any,
    execution_environment_digest: Any,
    trigger_publication_generations: Any,
    node_decisions: Any,
    accepted_output_payloads: Any,
    catalog: DataTypeCatalog | None,
) -> dict[str, Any]:
    if type(preparation_id) is not str:
        raise TypeError("preparation_id must be a string")
    preparation_id = _bounded_catalog_text(
        preparation_id,
        field_name="preparation_id",
        max_length=1024,
        allow_empty=True,
    )
    revision = _nonnegative_int_value(
        execution_affecting_workspace_revision,
        field_name="execution_affecting_workspace_revision",
    )
    runtime_generation = _nonnegative_int_value(
        dispatch_runtime_generation,
        field_name="dispatch_runtime_generation",
    )
    interface_revision = _nonnegative_int_value(
        workflow_interface_revision,
        field_name="workflow_interface_revision",
    )
    trigger_generations = normalize_trigger_publication_generations(
        trigger_publication_generations
    )
    decisions = _prepared_node_decisions(node_decisions)
    accepted = _accepted_output_payloads(
        accepted_output_payloads,
        catalog=catalog,
    )
    if not preparation_id:
        legacy_strings = {
            "solution_namespace_id": solution_namespace_id,
            "runtime_snapshot_fingerprint": runtime_snapshot_fingerprint,
            "execution_plan_fingerprint": execution_plan_fingerprint,
            "workflow_interface_digest": workflow_interface_digest,
            "execution_environment_digest": execution_environment_digest,
        }
        if any(type(value) is not str for value in legacy_strings.values()):
            raise TypeError("legacy prepared-only text fields must be strings")
        if (
            any(value != "" for value in legacy_strings.values())
            or revision != 0
            or runtime_generation != 0
            or interface_revision != 0
            or trigger_generations
            or decisions
            or accepted
        ):
            raise ValueError("legacy start_run forbids prepared execution fields")
        return {
            "preparation_id": "",
            "solution_namespace_id": "",
            "execution_affecting_workspace_revision": 0,
            "dispatch_runtime_generation": 0,
            "runtime_snapshot_fingerprint": "",
            "execution_plan_fingerprint": "",
            "workflow_interface_revision": 0,
            "workflow_interface_digest": "",
            "execution_environment_digest": "",
            "trigger_publication_generations": (),
            "node_decisions": (),
            "accepted_output_payloads": (),
        }
    namespace_id = _bounded_catalog_text(
        solution_namespace_id,
        field_name="solution_namespace_id",
        max_length=1024,
    )
    if runtime_generation <= 0:
        raise ValueError("prepared start_run requires a positive runtime generation")
    if interface_revision <= 0:
        raise ValueError("prepared start_run requires a positive workflow revision")
    normalized_digests = {
        field_name: _sha256_digest(value, field_name=field_name)
        for field_name, value in (
            ("runtime_snapshot_fingerprint", runtime_snapshot_fingerprint),
            ("execution_plan_fingerprint", execution_plan_fingerprint),
            ("workflow_interface_digest", workflow_interface_digest),
            ("execution_environment_digest", execution_environment_digest),
        )
    }
    accepted_by_node = {item.node_id: item for item in accepted}
    if len(accepted_by_node) != len(accepted):
        raise ValueError("accepted_output_payloads must not contain duplicate nodes")
    reuse_node_ids = {
        item.node_id for item in decisions if item.action.uses_accepted_output
    }
    if set(accepted_by_node) != reuse_node_ids:
        raise ValueError(
            "accepted output payloads require exactly the matching reuse decisions"
        )
    for decision in decisions:
        payload = accepted_by_node.get(decision.node_id)
        if payload is None:
            continue
        if (
            payload.record_id != decision.accepted_record_id
            or payload.solution_key != decision.solution_key
            or payload.commitment_digest() != decision.accepted_payload_digest
        ):
            raise ValueError(
                "accepted output payload must match decision record and solution key"
            )
        if (
            payload.residency is SolutionResidency.SESSION
            and payload.runtime_generation != runtime_generation
        ):
            raise ValueError(
                "session accepted output generation must match command generation"
            )
    return {
        "preparation_id": preparation_id,
        "solution_namespace_id": namespace_id,
        "execution_affecting_workspace_revision": revision,
        "dispatch_runtime_generation": runtime_generation,
        "workflow_interface_revision": interface_revision,
        "trigger_publication_generations": trigger_generations,
        "node_decisions": decisions,
        "accepted_output_payloads": accepted,
        **normalized_digests,
    }


def _root_error_to_dict(error: _settled.RootExecutionError) -> dict[str, str]:
    return error.to_payload()


def _settled_port_to_dict(
    result: _settled.SettledPortResult,
    *,
    catalog: DataTypeCatalog | None,
) -> dict[str, Any]:
    return result.to_payload(catalog=catalog)


def _settled_outputs_to_dict(
    values: Mapping[str, _settled.SettledPortResult],
    *,
    catalog: DataTypeCatalog | None,
) -> dict[str, Any]:
    return _settled.settled_outputs_to_payload(values, catalog=catalog)


def command_to_dict(
    command: WorkerCommand,
    *,
    catalog: DataTypeCatalog | None = None,
) -> dict[str, Any]:
    if isinstance(command, StartRunCommand):
        if (
            catalog is not None
            and not command.catalog_fingerprint
            and not command.catalog_revisions
        ):
            fingerprint, revisions = catalog_agreement(catalog)
            command = replace(
                command,
                catalog_fingerprint=fingerprint,
                catalog_revisions=revisions,
            )
        command = coerce_start_run_command(command, catalog=catalog)
        execution_backend = _execution_backend_from_payload(
            {"execution_backend": command.execution_backend.to_payload()}
        )
        payload = {
            "type": _string_value(command.type, field_name="type"),
            "run_id": _string_value(command.run_id, field_name="run_id"),
            "project_path": _string_value(
                command.project_path,
                field_name="project_path",
            ),
            "workspace_id": _string_value(
                command.workspace_id,
                field_name="workspace_id",
            ),
            "trigger": serialize_runtime_value(command.trigger, catalog=catalog),
            "runtime_snapshot": command.runtime_snapshot.to_document(catalog=catalog),
            "execution_backend": execution_backend.to_payload(),
            "target_node_ids": list(command.target_node_ids),
            "recompute_mode": RecomputeMode(command.recompute_mode).value,
            "trigger_publications": _settled_outputs_to_dict(
                command.trigger_publications,
                catalog=catalog,
            ),
            "trigger_captures": _settled_outputs_to_dict(
                command.trigger_captures,
                catalog=catalog,
            ),
            "clicked_trigger_node_id": _string_value(
                command.clicked_trigger_node_id,
                field_name="clicked_trigger_node_id",
            ),
            "developer_mode": _bool_value(
                command.developer_mode,
                field_name="developer_mode",
            ),
            "catalog_fingerprint": command.catalog_fingerprint,
            "catalog_revisions": [
                _catalog_revision_payload(record)
                for record in command.catalog_revisions
            ],
            "plugin_bundles": [
                _plugin_bundle_payload(bundle) for bundle in command.plugin_bundles
            ],
            "plugin_fingerprint": command.plugin_fingerprint,
            "runtime_registry_fingerprint": command.runtime_registry_fingerprint,
            "registry_contract_fingerprint": command.registry_contract_fingerprint,
            "addon_runtime_config": _addon_runtime_config_payload(
                command.addon_runtime_config
            ),
            "preparation_id": command.preparation_id,
            "solution_namespace_id": command.solution_namespace_id,
            "execution_affecting_workspace_revision": (
                command.execution_affecting_workspace_revision
            ),
            "dispatch_runtime_generation": command.dispatch_runtime_generation,
            "runtime_snapshot_fingerprint": command.runtime_snapshot_fingerprint,
            "execution_plan_fingerprint": command.execution_plan_fingerprint,
            "workflow_interface_revision": command.workflow_interface_revision,
            "workflow_interface_digest": command.workflow_interface_digest,
            "execution_environment_digest": command.execution_environment_digest,
            "trigger_publication_generations": [
                [node_id, generation]
                for node_id, generation in command.trigger_publication_generations
            ],
            "node_decisions": [
                decision.to_payload() for decision in command.node_decisions
            ],
            "accepted_output_payloads": [
                accepted.to_payload(catalog=catalog)
                for accepted in command.accepted_output_payloads
            ],
            "viewer_invalidation_node_ids": (
                None
                if command.viewer_invalidation_node_ids is None
                else list(command.viewer_invalidation_node_ids)
            ),
            "viewer_workspace_invalidation_epoch": (
                command.viewer_workspace_invalidation_epoch
            ),
            "viewer_node_invalidation_epochs": [
                [node_id, epoch]
                for node_id, epoch in command.viewer_node_invalidation_epochs
            ],
            "viewer_invalidation_reservation_id": (
                command.viewer_invalidation_reservation_id
            ),
            "viewer_epoch_snapshot_digest": command.viewer_epoch_snapshot_digest,
        }
        dict_to_command(payload, catalog=catalog)
        return payload
    if isinstance(command, QueryViewerSessionCommand):
        return {
            "type": _string_value(command.type, field_name="type"),
            "request_id": _string_value(
                command.request_id,
                field_name="request_id",
            ),
            "workspace_id": _string_value(
                command.workspace_id,
                field_name="workspace_id",
            ),
            "node_id": _string_value(command.node_id, field_name="node_id"),
            "session_id": _string_value(
                command.session_id,
                field_name="session_id",
            ),
            "backend_id": _string_value(
                command.backend_id,
                field_name="backend_id",
            ),
            "query_type": _string_value(
                command.query_type,
                field_name="query_type",
            ),
            "payload": _serialize_viewer_mapping(
                command.payload,
                field_name="payload",
                catalog=catalog,
            ),
            "options": _serialize_viewer_mapping(
                command.options,
                field_name="options",
                catalog=catalog,
            ),
            "workspace_invalidation_epoch": _nonnegative_int_value(
                command.workspace_invalidation_epoch,
                field_name="workspace_invalidation_epoch",
            ),
            "node_invalidation_epoch": _nonnegative_int_value(
                command.node_invalidation_epoch,
                field_name="node_invalidation_epoch",
            ),
        }
    if isinstance(command, (OpenViewerSessionCommand, UpdateViewerSessionCommand)):
        return {
            "type": _string_value(command.type, field_name="type"),
            "request_id": _string_value(
                command.request_id,
                field_name="request_id",
            ),
            "workspace_id": _string_value(
                command.workspace_id,
                field_name="workspace_id",
            ),
            "node_id": _string_value(command.node_id, field_name="node_id"),
            "session_id": _string_value(
                command.session_id,
                field_name="session_id",
            ),
            "backend_id": _string_value(
                command.backend_id,
                field_name="backend_id",
            ),
            "data_refs": _serialize_viewer_mapping(
                command.data_refs, field_name="data_refs", catalog=catalog
            ),
            "transport": _serialize_viewer_mapping(
                command.transport, field_name="transport", catalog=catalog
            ),
            "transport_revision": _nonnegative_int_value(
                command.transport_revision,
                field_name="transport_revision",
            ),
            "live_open_status": _string_value(
                command.live_open_status,
                field_name="live_open_status",
            ),
            "live_open_blocker": _serialize_viewer_mapping(
                command.live_open_blocker,
                field_name="live_open_blocker",
                catalog=catalog,
            ),
            "camera_state": _serialize_viewer_mapping(
                command.camera_state, field_name="camera_state", catalog=catalog
            ),
            "playback_state": _serialize_viewer_mapping(
                command.playback_state, field_name="playback_state", catalog=catalog
            ),
            "summary": _serialize_viewer_mapping(
                command.summary, field_name="summary", catalog=catalog
            ),
            "options": _serialize_viewer_mapping(
                command.options, field_name="options", catalog=catalog
            ),
            "workspace_invalidation_epoch": _nonnegative_int_value(
                command.workspace_invalidation_epoch,
                field_name="workspace_invalidation_epoch",
            ),
            "node_invalidation_epoch": _nonnegative_int_value(
                command.node_invalidation_epoch,
                field_name="node_invalidation_epoch",
            ),
        }
    if isinstance(command, CloseViewerSessionCommand):
        return {
            "type": _string_value(command.type, field_name="type"),
            "request_id": _string_value(
                command.request_id,
                field_name="request_id",
            ),
            "workspace_id": _string_value(
                command.workspace_id,
                field_name="workspace_id",
            ),
            "node_id": _string_value(command.node_id, field_name="node_id"),
            "session_id": _string_value(
                command.session_id,
                field_name="session_id",
            ),
            "options": _serialize_viewer_mapping(
                command.options, field_name="options", catalog=catalog
            ),
            "workspace_invalidation_epoch": _nonnegative_int_value(
                command.workspace_invalidation_epoch,
                field_name="workspace_invalidation_epoch",
            ),
            "node_invalidation_epoch": _nonnegative_int_value(
                command.node_invalidation_epoch,
                field_name="node_invalidation_epoch",
            ),
        }
    if isinstance(command, MaterializeViewerDataCommand):
        return {
            "type": _string_value(command.type, field_name="type"),
            "request_id": _string_value(
                command.request_id,
                field_name="request_id",
            ),
            "workspace_id": _string_value(
                command.workspace_id,
                field_name="workspace_id",
            ),
            "node_id": _string_value(command.node_id, field_name="node_id"),
            "session_id": _string_value(
                command.session_id,
                field_name="session_id",
            ),
            "backend_id": _string_value(
                command.backend_id,
                field_name="backend_id",
            ),
            "options": _serialize_viewer_mapping(
                command.options, field_name="options", catalog=catalog
            ),
            "workspace_invalidation_epoch": _nonnegative_int_value(
                command.workspace_invalidation_epoch,
                field_name="workspace_invalidation_epoch",
            ),
            "node_invalidation_epoch": _nonnegative_int_value(
                command.node_invalidation_epoch,
                field_name="node_invalidation_epoch",
            ),
        }
    return _serialize_scalar_payload(command, catalog=catalog)


def event_to_dict(
    event: WorkerEvent,
    *,
    catalog: DataTypeCatalog | None = None,
) -> dict[str, Any]:
    if isinstance(event, NodeSettledEvent):
        status = _string_value(event.status, field_name="status").strip().lower()
        if status not in {"completed", "empty", "failed", "blocked"}:
            raise ValueError(f"invalid node settlement status: {status!r}")
        warnings = _string_list_field(
            {"warnings": event.warnings},
            "warnings",
        )
        errors = _settled.normalize_root_execution_errors(event.errors)
        identity_fields = _settlement_identity_fields(
            status=status,
            disposition=event.disposition,
            decision_reason=event.decision_reason,
            solution_key=event.solution_key,
            record_id=event.record_id,
            residency=event.residency,
        )
        return {
            "type": _string_value(event.type, field_name="type"),
            "run_id": _string_value(event.run_id, field_name="run_id"),
            "workspace_id": _string_value(
                event.workspace_id,
                field_name="workspace_id",
            ),
            "node_id": _string_value(event.node_id, field_name="node_id"),
            "status": status,
            "elapsed_ms": _float_value(
                event.elapsed_ms,
                field_name="elapsed_ms",
            ),
            "outputs": _settled_outputs_to_dict(event.outputs, catalog=catalog),
            "errors": [_root_error_to_dict(error) for error in errors],
            "warnings": list(warnings),
            **identity_fields,
        }
    if isinstance(event, (TriggerCaptureSettledEvent, TriggerPublishedEvent)):
        return {
            "type": _string_value(event.type, field_name="type"),
            "run_id": _string_value(event.run_id, field_name="run_id"),
            "workspace_id": _string_value(
                event.workspace_id,
                field_name="workspace_id",
            ),
            "trigger_node_id": _string_value(
                event.trigger_node_id,
                field_name="trigger_node_id",
            ),
            "result": _settled_port_to_dict(event.result, catalog=catalog),
        }
    if isinstance(event, ViewerQueryResultEvent):
        return {
            "type": _string_value(event.type, field_name="type"),
            "request_id": _string_value(
                event.request_id,
                field_name="request_id",
            ),
            "workspace_id": _string_value(
                event.workspace_id,
                field_name="workspace_id",
            ),
            "node_id": _string_value(event.node_id, field_name="node_id"),
            "session_id": _string_value(
                event.session_id,
                field_name="session_id",
            ),
            "backend_id": _string_value(
                event.backend_id,
                field_name="backend_id",
            ),
            "query_type": _string_value(
                event.query_type,
                field_name="query_type",
            ),
            "supported": _bool_value(event.supported, field_name="supported"),
            "value": _serialize_viewer_mapping(
                event.value, field_name="value", catalog=catalog
            ),
            "explanation": _string_value(
                event.explanation,
                field_name="explanation",
            ),
            "workspace_invalidation_epoch": _nonnegative_int_value(
                event.workspace_invalidation_epoch,
                field_name="workspace_invalidation_epoch",
            ),
            "node_invalidation_epoch": _nonnegative_int_value(
                event.node_invalidation_epoch,
                field_name="node_invalidation_epoch",
            ),
        }
    if isinstance(
        event,
        (
            ViewerSessionOpenedEvent,
            ViewerSessionUpdatedEvent,
            ViewerDataMaterializedEvent,
        ),
    ):
        return {
            "type": _string_value(event.type, field_name="type"),
            "request_id": _string_value(
                event.request_id,
                field_name="request_id",
            ),
            "workspace_id": _string_value(
                event.workspace_id,
                field_name="workspace_id",
            ),
            "node_id": _string_value(event.node_id, field_name="node_id"),
            "session_id": _string_value(
                event.session_id,
                field_name="session_id",
            ),
            "backend_id": _string_value(
                event.backend_id,
                field_name="backend_id",
            ),
            "data_refs": _serialize_viewer_mapping(
                event.data_refs, field_name="data_refs", catalog=catalog
            ),
            "transport": _serialize_viewer_mapping(
                event.transport, field_name="transport", catalog=catalog
            ),
            "transport_revision": _nonnegative_int_value(
                event.transport_revision,
                field_name="transport_revision",
            ),
            "live_open_status": _string_value(
                event.live_open_status,
                field_name="live_open_status",
            ),
            "live_open_blocker": _serialize_viewer_mapping(
                event.live_open_blocker,
                field_name="live_open_blocker",
                catalog=catalog,
            ),
            "camera_state": _serialize_viewer_mapping(
                event.camera_state, field_name="camera_state", catalog=catalog
            ),
            "playback_state": _serialize_viewer_mapping(
                event.playback_state, field_name="playback_state", catalog=catalog
            ),
            "summary": _serialize_viewer_mapping(
                event.summary, field_name="summary", catalog=catalog
            ),
            "options": _serialize_viewer_mapping(
                event.options, field_name="options", catalog=catalog
            ),
            "workspace_invalidation_epoch": _nonnegative_int_value(
                event.workspace_invalidation_epoch,
                field_name="workspace_invalidation_epoch",
            ),
            "node_invalidation_epoch": _nonnegative_int_value(
                event.node_invalidation_epoch,
                field_name="node_invalidation_epoch",
            ),
        }
    if isinstance(event, ViewerSessionClosedEvent):
        return {
            "type": _string_value(event.type, field_name="type"),
            "request_id": _string_value(
                event.request_id,
                field_name="request_id",
            ),
            "workspace_id": _string_value(
                event.workspace_id,
                field_name="workspace_id",
            ),
            "node_id": _string_value(event.node_id, field_name="node_id"),
            "session_id": _string_value(
                event.session_id,
                field_name="session_id",
            ),
            "backend_id": _string_value(
                event.backend_id,
                field_name="backend_id",
            ),
            "transport": _serialize_viewer_mapping(
                event.transport, field_name="transport", catalog=catalog
            ),
            "transport_revision": _nonnegative_int_value(
                event.transport_revision,
                field_name="transport_revision",
            ),
            "live_open_status": _string_value(
                event.live_open_status,
                field_name="live_open_status",
            ),
            "live_open_blocker": _serialize_viewer_mapping(
                event.live_open_blocker,
                field_name="live_open_blocker",
                catalog=catalog,
            ),
            "camera_state": _serialize_viewer_mapping(
                event.camera_state, field_name="camera_state", catalog=catalog
            ),
            "playback_state": _serialize_viewer_mapping(
                event.playback_state, field_name="playback_state", catalog=catalog
            ),
            "summary": _serialize_viewer_mapping(
                event.summary, field_name="summary", catalog=catalog
            ),
            "options": _serialize_viewer_mapping(
                event.options, field_name="options", catalog=catalog
            ),
            "workspace_invalidation_epoch": _nonnegative_int_value(
                event.workspace_invalidation_epoch,
                field_name="workspace_invalidation_epoch",
            ),
            "node_invalidation_epoch": _nonnegative_int_value(
                event.node_invalidation_epoch,
                field_name="node_invalidation_epoch",
            ),
        }
    if isinstance(event, ViewerSessionFailedEvent):
        return {
            "type": _string_value(event.type, field_name="type"),
            "request_id": _string_value(
                event.request_id,
                field_name="request_id",
            ),
            "workspace_id": _string_value(
                event.workspace_id,
                field_name="workspace_id",
            ),
            "node_id": _string_value(event.node_id, field_name="node_id"),
            "session_id": _string_value(
                event.session_id,
                field_name="session_id",
            ),
            "command": _string_value(event.command, field_name="command"),
            "error": _string_value(event.error, field_name="error"),
            "workspace_invalidation_epoch": _nonnegative_int_value(
                event.workspace_invalidation_epoch,
                field_name="workspace_invalidation_epoch",
            ),
            "node_invalidation_epoch": _nonnegative_int_value(
                event.node_invalidation_epoch,
                field_name="node_invalidation_epoch",
            ),
        }
    return _serialize_scalar_payload(event, catalog=catalog)


def _start_run_command_from_payload(
    payload: Mapping[str, Any],
    *,
    catalog: DataTypeCatalog | None,
) -> StartRunCommand:
    required_plugin_fields = {
        "plugin_bundles",
        "plugin_fingerprint",
        "runtime_registry_fingerprint",
        "registry_contract_fingerprint",
        "addon_runtime_config",
    }
    if missing_plugin_fields := required_plugin_fields - set(payload):
        raise ValueError(
            "start_run requires plugin agreement fields: "
            + ", ".join(sorted(missing_plugin_fields))
        )
    prepared_field_names = {
        "preparation_id",
        "solution_namespace_id",
        "execution_affecting_workspace_revision",
        "dispatch_runtime_generation",
        "runtime_snapshot_fingerprint",
        "execution_plan_fingerprint",
        "workflow_interface_revision",
        "workflow_interface_digest",
        "execution_environment_digest",
        "trigger_publication_generations",
        "node_decisions",
        "accepted_output_payloads",
        "viewer_invalidation_node_ids",
        "viewer_workspace_invalidation_epoch",
        "viewer_node_invalidation_epochs",
        "viewer_invalidation_reservation_id",
        "viewer_epoch_snapshot_digest",
    }
    if str(payload.get("preparation_id", "")).strip():
        if missing_prepared_fields := prepared_field_names - set(payload):
            raise ValueError(
                "prepared start_run requires fields: "
                + ", ".join(sorted(missing_prepared_fields))
            )
    if not isinstance(payload["plugin_bundles"], list):
        raise ValueError("start_run plugin_bundles must be a list")
    _plugin_fingerprint(payload["plugin_fingerprint"])
    _sha256_digest(
        payload["runtime_registry_fingerprint"],
        field_name="runtime_registry_fingerprint",
    )
    registry_contract_fingerprint = _sha256_digest(
        payload["registry_contract_fingerprint"],
        field_name="registry_contract_fingerprint",
    )
    addon_runtime_config = normalize_addon_runtime_config(
        payload["addon_runtime_config"]
    )
    catalog_fingerprint, catalog_revisions = catalog_agreement_from_payload(payload)
    if catalog is not None:
        mismatch = catalog_mismatch_message(
            catalog_fingerprint,
            catalog_revisions,
            catalog,
        )
        if mismatch:
            raise ValueError(mismatch)
    plugin_bundles, plugin_fingerprint, runtime_fingerprint = _plugin_agreement(
        payload.get("plugin_bundles", ()),
        payload.get("plugin_fingerprint", ""),
        payload.get("runtime_registry_fingerprint", ""),
        catalog_fingerprint=catalog_fingerprint,
    )
    raw_trigger = payload.get("trigger", {})
    if not isinstance(raw_trigger, Mapping):
        raise ValueError("trigger must be a mapping.")
    trigger_payload = deserialize_runtime_value(raw_trigger, catalog=catalog)
    if not isinstance(trigger_payload, Mapping):
        raise ValueError("trigger must decode to a mapping.")
    runtime_snapshot_payload = payload.get("runtime_snapshot")
    if not isinstance(runtime_snapshot_payload, Mapping):
        raise ValueError("start_run requires runtime_snapshot.")
    runtime_snapshot = coerce_runtime_snapshot(
        runtime_snapshot_payload,
        catalog=catalog,
    )
    if runtime_snapshot is None:
        raise ValueError("start_run requires runtime_snapshot.")
    prepared_fields = _normalize_prepared_start_fields(
        preparation_id=payload.get("preparation_id", ""),
        solution_namespace_id=payload.get("solution_namespace_id", ""),
        execution_affecting_workspace_revision=payload.get(
            "execution_affecting_workspace_revision", 0
        ),
        dispatch_runtime_generation=payload.get("dispatch_runtime_generation", 0),
        runtime_snapshot_fingerprint=payload.get("runtime_snapshot_fingerprint", ""),
        execution_plan_fingerprint=payload.get("execution_plan_fingerprint", ""),
        workflow_interface_revision=payload.get("workflow_interface_revision", 0),
        workflow_interface_digest=payload.get("workflow_interface_digest", ""),
        execution_environment_digest=payload.get("execution_environment_digest", ""),
        trigger_publication_generations=payload.get(
            "trigger_publication_generations", ()
        ),
        node_decisions=payload.get("node_decisions", ()),
        accepted_output_payloads=payload.get("accepted_output_payloads", ()),
        catalog=catalog,
    )
    viewer_fields = normalize_viewer_invalidation_fields(
        preparation_id=prepared_fields["preparation_id"],
        workspace_id=_string_field(payload, "workspace_id"),
        node_ids=payload.get("viewer_invalidation_node_ids"),
        workspace_epoch=payload.get("viewer_workspace_invalidation_epoch", 0),
        node_epochs=payload.get("viewer_node_invalidation_epochs", ()),
        reservation_id=payload.get("viewer_invalidation_reservation_id", ""),
        snapshot_digest=payload.get("viewer_epoch_snapshot_digest", ""),
    )
    return StartRunCommand(
        run_id=_string_field(payload, "run_id"),
        project_path=_string_field(payload, "project_path"),
        workspace_id=_string_field(payload, "workspace_id"),
        trigger=dict(trigger_payload),
        runtime_snapshot=runtime_snapshot,
        execution_backend=_execution_backend_from_payload(payload),
        target_node_ids=normalize_target_node_ids(payload.get("target_node_ids", ())),
        recompute_mode=RecomputeMode(payload.get("recompute_mode", "reuse_valid")).value,
        trigger_publications=_settled.settled_output_mapping_from_payload(
            payload.get("trigger_publications", {}),
            catalog=catalog,
        ),
        trigger_captures=_settled.settled_output_mapping_from_payload(
            payload.get("trigger_captures", {}),
            catalog=catalog,
        ),
        clicked_trigger_node_id=_string_field(
            payload,
            "clicked_trigger_node_id",
            strip=True,
        ),
        developer_mode=_bool_field(payload, "developer_mode"),
        catalog_fingerprint=catalog_fingerprint,
        catalog_revisions=catalog_revisions,
        plugin_bundles=plugin_bundles,
        plugin_fingerprint=plugin_fingerprint,
        runtime_registry_fingerprint=runtime_fingerprint,
        registry_contract_fingerprint=registry_contract_fingerprint,
        addon_runtime_config=addon_runtime_config,
        **prepared_fields,
        **viewer_fields,
    )


def coerce_start_run_command(
    command: StartRunCommand | Mapping[str, Any],
    *,
    catalog: DataTypeCatalog | None = None,
) -> StartRunCommand:
    if isinstance(command, StartRunCommand):
        if command.runtime_snapshot is None:
            raise ValueError("start_run requires runtime_snapshot.")
        if not isinstance(command.trigger, Mapping):
            raise ValueError("trigger must be a mapping.")
        if not isinstance(command.execution_backend, ExecutionBackendSelection):
            raise ValueError("execution_backend must be an ExecutionBackendSelection.")
        if not isinstance(command.developer_mode, bool):
            raise ValueError("developer_mode must be a boolean.")
        catalog_fingerprint = _catalog_fingerprint(command.catalog_fingerprint)
        catalog_revisions = normalize_catalog_revisions(command.catalog_revisions)
        if catalog is not None:
            mismatch = catalog_mismatch_message(
                catalog_fingerprint,
                catalog_revisions,
                catalog,
            )
            if mismatch:
                raise ValueError(mismatch)
        plugin_bundles, plugin_fingerprint, runtime_fingerprint = _plugin_agreement(
            command.plugin_bundles,
            command.plugin_fingerprint,
            command.runtime_registry_fingerprint,
            catalog_fingerprint=catalog_fingerprint,
        )
        registry_contract_fingerprint = _sha256_digest(
            command.registry_contract_fingerprint,
            field_name="registry_contract_fingerprint",
        )
        addon_runtime_config = normalize_addon_runtime_config(
            command.addon_runtime_config
        )
        prepared_fields = _normalize_prepared_start_fields(
            preparation_id=command.preparation_id,
            solution_namespace_id=command.solution_namespace_id,
            execution_affecting_workspace_revision=(
                command.execution_affecting_workspace_revision
            ),
            dispatch_runtime_generation=command.dispatch_runtime_generation,
            runtime_snapshot_fingerprint=command.runtime_snapshot_fingerprint,
            execution_plan_fingerprint=command.execution_plan_fingerprint,
            workflow_interface_revision=command.workflow_interface_revision,
            workflow_interface_digest=command.workflow_interface_digest,
            execution_environment_digest=command.execution_environment_digest,
            trigger_publication_generations=(command.trigger_publication_generations),
            node_decisions=command.node_decisions,
            accepted_output_payloads=command.accepted_output_payloads,
            catalog=catalog,
        )
        viewer_fields = normalize_viewer_invalidation_fields(
            preparation_id=prepared_fields["preparation_id"],
            workspace_id=command.workspace_id,
            node_ids=command.viewer_invalidation_node_ids,
            workspace_epoch=command.viewer_workspace_invalidation_epoch,
            node_epochs=command.viewer_node_invalidation_epochs,
            reservation_id=command.viewer_invalidation_reservation_id,
            snapshot_digest=command.viewer_epoch_snapshot_digest,
        )
        return StartRunCommand(
            run_id=_string_field({"run_id": command.run_id}, "run_id"),
            project_path=_string_field(
                {"project_path": command.project_path},
                "project_path",
            ),
            workspace_id=_string_field(
                {"workspace_id": command.workspace_id},
                "workspace_id",
            ),
            trigger=dict(command.trigger),
            runtime_snapshot=command.runtime_snapshot,
            execution_backend=command.execution_backend,
            target_node_ids=normalize_target_node_ids(command.target_node_ids),
            recompute_mode=RecomputeMode(command.recompute_mode).value,
            trigger_publications=_settled.normalize_settled_output_mapping(
                command.trigger_publications,
                catalog=catalog,
            ),
            trigger_captures=_settled.normalize_settled_output_mapping(
                command.trigger_captures,
                catalog=catalog,
            ),
            clicked_trigger_node_id=_string_field(
                {"clicked_trigger_node_id": command.clicked_trigger_node_id},
                "clicked_trigger_node_id",
                strip=True,
            ),
            developer_mode=command.developer_mode,
            catalog_fingerprint=catalog_fingerprint,
            catalog_revisions=catalog_revisions,
            plugin_bundles=plugin_bundles,
            plugin_fingerprint=plugin_fingerprint,
            runtime_registry_fingerprint=runtime_fingerprint,
            registry_contract_fingerprint=registry_contract_fingerprint,
            addon_runtime_config=addon_runtime_config,
            **prepared_fields,
            **viewer_fields,
        )

    if (
        catalog is not None
        and "catalog_fingerprint" not in command
        and "catalog_revisions" not in command
    ):
        catalog_fingerprint, catalog_revisions = catalog_agreement(catalog)
    else:
        catalog_fingerprint, catalog_revisions = catalog_agreement_from_payload(command)
    if catalog is not None:
        mismatch = catalog_mismatch_message(
            catalog_fingerprint,
            catalog_revisions,
            catalog,
        )
        if mismatch:
            raise ValueError(mismatch)
    plugin_bundles, plugin_fingerprint, runtime_fingerprint = _plugin_agreement(
        command.get("plugin_bundles", ()),
        command.get("plugin_fingerprint", ""),
        command.get("runtime_registry_fingerprint", ""),
        catalog_fingerprint=catalog_fingerprint,
    )
    registry_contract_fingerprint = _sha256_digest(
        command.get("registry_contract_fingerprint", ""),
        field_name="registry_contract_fingerprint",
    )
    addon_runtime_config = normalize_addon_runtime_config(
        command.get("addon_runtime_config", ())
    )
    raw_trigger = command.get("trigger", {})
    if not isinstance(raw_trigger, Mapping):
        raise ValueError("trigger must be a mapping.")
    runtime_snapshot = coerce_runtime_snapshot(
        command.get("runtime_snapshot"),
        catalog=catalog,
    )
    if runtime_snapshot is None:
        raise ValueError("start_run requires runtime_snapshot.")
    prepared_fields = _normalize_prepared_start_fields(
        preparation_id=command.get("preparation_id", ""),
        solution_namespace_id=command.get("solution_namespace_id", ""),
        execution_affecting_workspace_revision=command.get(
            "execution_affecting_workspace_revision", 0
        ),
        dispatch_runtime_generation=command.get("dispatch_runtime_generation", 0),
        runtime_snapshot_fingerprint=command.get("runtime_snapshot_fingerprint", ""),
        execution_plan_fingerprint=command.get("execution_plan_fingerprint", ""),
        workflow_interface_revision=command.get("workflow_interface_revision", 0),
        workflow_interface_digest=command.get("workflow_interface_digest", ""),
        execution_environment_digest=command.get("execution_environment_digest", ""),
        trigger_publication_generations=command.get(
            "trigger_publication_generations", ()
        ),
        node_decisions=command.get("node_decisions", ()),
        accepted_output_payloads=command.get("accepted_output_payloads", ()),
        catalog=catalog,
    )
    viewer_fields = normalize_viewer_invalidation_fields(
        preparation_id=prepared_fields["preparation_id"],
        workspace_id=_string_field(command, "workspace_id"),
        node_ids=command.get("viewer_invalidation_node_ids"),
        workspace_epoch=command.get("viewer_workspace_invalidation_epoch", 0),
        node_epochs=command.get("viewer_node_invalidation_epochs", ()),
        reservation_id=command.get("viewer_invalidation_reservation_id", ""),
        snapshot_digest=command.get("viewer_epoch_snapshot_digest", ""),
    )
    return StartRunCommand(
        run_id=_string_field(command, "run_id"),
        project_path=_string_field(command, "project_path"),
        workspace_id=_string_field(command, "workspace_id"),
        trigger=dict(raw_trigger),
        runtime_snapshot=runtime_snapshot,
        execution_backend=_execution_backend_from_payload(command),
        target_node_ids=normalize_target_node_ids(command.get("target_node_ids", ())),
        recompute_mode=RecomputeMode(command.get("recompute_mode", "reuse_valid")).value,
        trigger_publications=_settled.normalize_settled_output_mapping(
            command.get("trigger_publications", {}),
            catalog=catalog,
        ),
        trigger_captures=_settled.normalize_settled_output_mapping(
            command.get("trigger_captures", {}),
            catalog=catalog,
        ),
        clicked_trigger_node_id=_string_field(
            command,
            "clicked_trigger_node_id",
            strip=True,
        ),
        developer_mode=_bool_field(command, "developer_mode"),
        catalog_fingerprint=catalog_fingerprint,
        catalog_revisions=catalog_revisions,
        plugin_bundles=plugin_bundles,
        plugin_fingerprint=plugin_fingerprint,
        runtime_registry_fingerprint=runtime_fingerprint,
        registry_contract_fingerprint=registry_contract_fingerprint,
        addon_runtime_config=addon_runtime_config,
        **prepared_fields,
        **viewer_fields,
    )


def dict_to_command(
    payload: dict[str, Any],
    *,
    catalog: DataTypeCatalog | None = None,
) -> WorkerCommand:
    payload = dict(copy_json_safe(payload, field_name="worker command"))
    command_type = _string_field(payload, "type")
    if command_type == "start_run":
        return _start_run_command_from_payload(payload, catalog=catalog)
    if command_type == "stop_run":
        return StopRunCommand(
            run_id=_string_field(payload, "run_id"),
            workspace_id=_string_field(payload, "workspace_id"),
        )
    if command_type == "pause_run":
        return PauseRunCommand(run_id=_string_field(payload, "run_id"))
    if command_type == "resume_run":
        return ResumeRunCommand(run_id=_string_field(payload, "run_id"))
    if command_type == "shutdown":
        return ShutdownCommand()
    if command_type == "retire_workspace":
        return RetireWorkspaceCommand(
            request_id=_string_field(payload, "request_id", strip=True),
            workspace_id=_string_field(payload, "workspace_id", strip=True),
        )
    if command_type == "commit_run_preflight":
        return CommitRunPreflightCommand(
            run_id=_string_field(payload, "run_id", strip=True),
            viewer_invalidation_reservation_id=_string_field(
                payload, "viewer_invalidation_reservation_id", strip=True
            ),
            viewer_epoch_snapshot_digest=_sha256_digest(
                payload.get("viewer_epoch_snapshot_digest", ""),
                field_name="viewer_epoch_snapshot_digest",
            ),
        )
    if command_type == "cancel_run_preflight":
        return CancelRunPreflightCommand(
            run_id=_string_field(payload, "run_id", strip=True),
            viewer_invalidation_reservation_id=_string_field(
                payload, "viewer_invalidation_reservation_id", strip=True
            ),
            viewer_epoch_snapshot_digest=_sha256_digest(
                payload.get("viewer_epoch_snapshot_digest", ""),
                field_name="viewer_epoch_snapshot_digest",
            ),
        )
    if command_type == "open_viewer_session":
        return OpenViewerSessionCommand(
            request_id=_string_field(payload, "request_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            session_id=_string_field(payload, "session_id"),
            backend_id=_string_field(payload, "backend_id"),
            data_refs=_deserialize_viewer_mapping(
                payload, "data_refs", catalog=catalog
            ),
            transport=_deserialize_viewer_mapping(
                payload, "transport", catalog=catalog
            ),
            transport_revision=_nonnegative_int_field(
                payload,
                "transport_revision",
            ),
            live_open_status=_string_field(payload, "live_open_status"),
            live_open_blocker=_deserialize_viewer_mapping(
                payload, "live_open_blocker", catalog=catalog
            ),
            camera_state=_deserialize_viewer_mapping(
                payload, "camera_state", catalog=catalog
            ),
            playback_state=_deserialize_viewer_mapping(
                payload, "playback_state", catalog=catalog
            ),
            summary=_deserialize_viewer_mapping(payload, "summary", catalog=catalog),
            options=_deserialize_viewer_mapping(payload, "options", catalog=catalog),
            workspace_invalidation_epoch=_nonnegative_int_field(
                payload, "workspace_invalidation_epoch"
            ),
            node_invalidation_epoch=_nonnegative_int_field(
                payload, "node_invalidation_epoch"
            ),
        )
    if command_type == "update_viewer_session":
        return UpdateViewerSessionCommand(
            request_id=_string_field(payload, "request_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            session_id=_string_field(payload, "session_id"),
            backend_id=_string_field(payload, "backend_id"),
            data_refs=_deserialize_viewer_mapping(
                payload, "data_refs", catalog=catalog
            ),
            transport=_deserialize_viewer_mapping(
                payload, "transport", catalog=catalog
            ),
            transport_revision=_nonnegative_int_field(
                payload,
                "transport_revision",
            ),
            live_open_status=_string_field(payload, "live_open_status"),
            live_open_blocker=_deserialize_viewer_mapping(
                payload, "live_open_blocker", catalog=catalog
            ),
            camera_state=_deserialize_viewer_mapping(
                payload, "camera_state", catalog=catalog
            ),
            playback_state=_deserialize_viewer_mapping(
                payload, "playback_state", catalog=catalog
            ),
            summary=_deserialize_viewer_mapping(payload, "summary", catalog=catalog),
            options=_deserialize_viewer_mapping(payload, "options", catalog=catalog),
            workspace_invalidation_epoch=_nonnegative_int_field(
                payload, "workspace_invalidation_epoch"
            ),
            node_invalidation_epoch=_nonnegative_int_field(
                payload, "node_invalidation_epoch"
            ),
        )
    if command_type == "close_viewer_session":
        return CloseViewerSessionCommand(
            request_id=_string_field(payload, "request_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            session_id=_string_field(payload, "session_id"),
            options=_deserialize_viewer_mapping(payload, "options", catalog=catalog),
            workspace_invalidation_epoch=_nonnegative_int_field(
                payload, "workspace_invalidation_epoch"
            ),
            node_invalidation_epoch=_nonnegative_int_field(
                payload, "node_invalidation_epoch"
            ),
        )
    if command_type == "materialize_viewer_data":
        return MaterializeViewerDataCommand(
            request_id=_string_field(payload, "request_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            session_id=_string_field(payload, "session_id"),
            backend_id=_string_field(payload, "backend_id"),
            options=_deserialize_viewer_mapping(payload, "options", catalog=catalog),
            workspace_invalidation_epoch=_nonnegative_int_field(
                payload, "workspace_invalidation_epoch"
            ),
            node_invalidation_epoch=_nonnegative_int_field(
                payload, "node_invalidation_epoch"
            ),
        )
    if command_type == "query_viewer_session":
        return QueryViewerSessionCommand(
            request_id=_string_field(payload, "request_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            session_id=_string_field(payload, "session_id"),
            backend_id=_string_field(payload, "backend_id"),
            query_type=_string_field(payload, "query_type"),
            payload=_deserialize_viewer_mapping(payload, "payload", catalog=catalog),
            options=_deserialize_viewer_mapping(payload, "options", catalog=catalog),
            workspace_invalidation_epoch=_nonnegative_int_field(
                payload, "workspace_invalidation_epoch"
            ),
            node_invalidation_epoch=_nonnegative_int_field(
                payload, "node_invalidation_epoch"
            ),
        )
    raise ValueError(f"Unknown command type: {command_type!r}")


def dict_to_event(
    payload: dict[str, Any],
    *,
    catalog: DataTypeCatalog | None = None,
) -> WorkerEvent:
    payload = dict(copy_json_safe(payload, field_name="worker event"))
    event_type = _string_field(payload, "type")
    if event_type == "run_preflight_accepted":
        return RunPreflightAcceptedEvent(
            run_id=_string_field(payload, "run_id", strip=True),
            workspace_id=_string_field(payload, "workspace_id", strip=True),
            preparation_id=_string_field(payload, "preparation_id", strip=True),
            viewer_invalidation_reservation_id=_string_field(
                payload, "viewer_invalidation_reservation_id", strip=True
            ),
            viewer_epoch_snapshot_digest=_sha256_digest(
                payload.get("viewer_epoch_snapshot_digest", ""),
                field_name="viewer_epoch_snapshot_digest",
            ),
        )
    if event_type == "workspace_retired":
        return WorkspaceRetiredEvent(
            request_id=_string_field(payload, "request_id", strip=True),
            workspace_id=_string_field(payload, "workspace_id", strip=True),
            retired_count=_string_field(payload, "retired_count", strip=True),
        )
    if event_type == "run_started":
        return RunStartedEvent(
            run_id=_string_field(payload, "run_id"),
            workspace_id=_string_field(payload, "workspace_id"),
        )
    if event_type == "run_state":
        return RunStateEvent(
            run_id=_string_field(payload, "run_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            state=_literal_field(  # type: ignore[arg-type]
                payload,
                "state",
                allowed_values=_ENGINE_STATE_VALUES,
                default="ready",
            ),
            transition=_literal_field(
                payload,
                "transition",
                allowed_values=_RUN_TRANSITION_VALUES,
                default="",
            ),
            reason=_string_field(payload, "reason"),
        )
    if event_type == "run_completed":
        _fixed_run_event_state(payload, expected="ready")
        return RunCompletedEvent(
            run_id=_string_field(payload, "run_id"),
            workspace_id=_string_field(payload, "workspace_id"),
        )
    if event_type == "run_failed":
        _fixed_run_event_state(payload, expected="error")
        return RunFailedEvent(
            run_id=_string_field(payload, "run_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            error=_string_field(payload, "error"),
            traceback=_string_field(payload, "traceback"),
            fatal=_bool_field(payload, "fatal"),
        )
    if event_type == "run_stopped":
        _fixed_run_event_state(payload, expected="ready")
        return RunStoppedEvent(
            run_id=_string_field(payload, "run_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            reason=_string_field(payload, "reason"),
        )
    if event_type == "node_started":
        return NodeStartedEvent(
            run_id=_string_field(payload, "run_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            started_at_epoch_ms=_float_field(payload, "started_at_epoch_ms"),
        )
    if event_type == "node_settled":
        warnings = _string_list_field(payload, "warnings")
        status = _string_field(
            payload,
            "status",
            default="completed",
            strip=True,
        ).lower()
        if status not in {"completed", "empty", "failed", "blocked"}:
            raise ValueError(f"invalid node settlement status: {status!r}")
        identity_fields = _settlement_identity_fields(
            status=status,
            disposition=payload.get("disposition", ""),
            decision_reason=payload.get("decision_reason", "legacy_direct_run"),
            solution_key=payload.get("solution_key", ""),
            record_id=payload.get("record_id", ""),
            residency=payload.get("residency", ""),
        )
        return NodeSettledEvent(
            run_id=_string_field(payload, "run_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            status=status,
            elapsed_ms=_float_field(payload, "elapsed_ms"),
            outputs=_settled.settled_output_mapping_from_payload(
                payload.get("outputs", {}),
                catalog=catalog,
            ),
            errors=_settled.root_execution_errors_from_payload(
                payload.get("errors", ())
            ),
            warnings=warnings,
            **identity_fields,
        )
    if event_type == "observation_invalidation_requested":
        values = {
            field: _string_field(payload, field, strip=True)
            for field in (
                "run_id",
                "workspace_id",
                "node_id",
                "root_node_id",
                "reason_code",
            )
        }
        if any(not value or len(value) > 256 for value in values.values()):
            raise ValueError(
                "observation invalidation identities must be bounded non-empty strings"
            )
        return ObservationInvalidationRequestedEvent(**values)
    if event_type in {"trigger_capture_settled", "trigger_published"}:
        event_type_args = {
            "run_id": _string_field(payload, "run_id"),
            "workspace_id": _string_field(payload, "workspace_id"),
            "trigger_node_id": _string_field(payload, "trigger_node_id"),
            "result": _settled.SettledPortResult.from_payload(
                payload.get(
                    "result",
                    {"status": "empty", "value": None, "errors": ()},
                ),
                catalog=catalog,
            ),
        }
        if event_type == "trigger_capture_settled":
            return TriggerCaptureSettledEvent(**event_type_args)
        return TriggerPublishedEvent(**event_type_args)
    if event_type == "log":
        return LogEvent(
            run_id=_string_field(payload, "run_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            level=_string_field(payload, "level", default="info"),
            message=_string_field(payload, "message"),
        )
    if event_type == "protocol_error":
        return ProtocolErrorEvent(
            run_id=_string_field(payload, "run_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            request_id=_string_field(payload, "request_id"),
            command=_string_field(payload, "command"),
            error=_string_field(payload, "error"),
        )
    if event_type == "viewer_session_opened":
        return ViewerSessionOpenedEvent(
            request_id=_string_field(payload, "request_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            session_id=_string_field(payload, "session_id"),
            backend_id=_string_field(payload, "backend_id"),
            data_refs=_deserialize_viewer_mapping(
                payload, "data_refs", catalog=catalog
            ),
            transport=_deserialize_viewer_mapping(
                payload, "transport", catalog=catalog
            ),
            transport_revision=_nonnegative_int_field(
                payload,
                "transport_revision",
            ),
            live_open_status=_string_field(payload, "live_open_status"),
            live_open_blocker=_deserialize_viewer_mapping(
                payload, "live_open_blocker", catalog=catalog
            ),
            camera_state=_deserialize_viewer_mapping(
                payload, "camera_state", catalog=catalog
            ),
            playback_state=_deserialize_viewer_mapping(
                payload, "playback_state", catalog=catalog
            ),
            summary=_deserialize_viewer_mapping(payload, "summary", catalog=catalog),
            options=_deserialize_viewer_mapping(payload, "options", catalog=catalog),
            workspace_invalidation_epoch=_nonnegative_int_field(
                payload, "workspace_invalidation_epoch"
            ),
            node_invalidation_epoch=_nonnegative_int_field(
                payload, "node_invalidation_epoch"
            ),
        )
    if event_type == "viewer_session_updated":
        return ViewerSessionUpdatedEvent(
            request_id=_string_field(payload, "request_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            session_id=_string_field(payload, "session_id"),
            backend_id=_string_field(payload, "backend_id"),
            data_refs=_deserialize_viewer_mapping(
                payload, "data_refs", catalog=catalog
            ),
            transport=_deserialize_viewer_mapping(
                payload, "transport", catalog=catalog
            ),
            transport_revision=_nonnegative_int_field(
                payload,
                "transport_revision",
            ),
            live_open_status=_string_field(payload, "live_open_status"),
            live_open_blocker=_deserialize_viewer_mapping(
                payload, "live_open_blocker", catalog=catalog
            ),
            camera_state=_deserialize_viewer_mapping(
                payload, "camera_state", catalog=catalog
            ),
            playback_state=_deserialize_viewer_mapping(
                payload, "playback_state", catalog=catalog
            ),
            summary=_deserialize_viewer_mapping(payload, "summary", catalog=catalog),
            options=_deserialize_viewer_mapping(payload, "options", catalog=catalog),
            workspace_invalidation_epoch=_nonnegative_int_field(
                payload, "workspace_invalidation_epoch"
            ),
            node_invalidation_epoch=_nonnegative_int_field(
                payload, "node_invalidation_epoch"
            ),
        )
    if event_type == "viewer_session_closed":
        return ViewerSessionClosedEvent(
            request_id=_string_field(payload, "request_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            session_id=_string_field(payload, "session_id"),
            backend_id=_string_field(payload, "backend_id"),
            transport=_deserialize_viewer_mapping(
                payload, "transport", catalog=catalog
            ),
            transport_revision=_nonnegative_int_field(
                payload,
                "transport_revision",
            ),
            live_open_status=_string_field(payload, "live_open_status"),
            live_open_blocker=_deserialize_viewer_mapping(
                payload, "live_open_blocker", catalog=catalog
            ),
            camera_state=_deserialize_viewer_mapping(
                payload, "camera_state", catalog=catalog
            ),
            playback_state=_deserialize_viewer_mapping(
                payload, "playback_state", catalog=catalog
            ),
            summary=_deserialize_viewer_mapping(payload, "summary", catalog=catalog),
            options=_deserialize_viewer_mapping(payload, "options", catalog=catalog),
            workspace_invalidation_epoch=_nonnegative_int_field(
                payload, "workspace_invalidation_epoch"
            ),
            node_invalidation_epoch=_nonnegative_int_field(
                payload, "node_invalidation_epoch"
            ),
        )
    if event_type == "viewer_data_materialized":
        return ViewerDataMaterializedEvent(
            request_id=_string_field(payload, "request_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            session_id=_string_field(payload, "session_id"),
            backend_id=_string_field(payload, "backend_id"),
            data_refs=_deserialize_viewer_mapping(
                payload, "data_refs", catalog=catalog
            ),
            transport=_deserialize_viewer_mapping(
                payload, "transport", catalog=catalog
            ),
            transport_revision=_nonnegative_int_field(
                payload,
                "transport_revision",
            ),
            live_open_status=_string_field(payload, "live_open_status"),
            live_open_blocker=_deserialize_viewer_mapping(
                payload, "live_open_blocker", catalog=catalog
            ),
            camera_state=_deserialize_viewer_mapping(
                payload, "camera_state", catalog=catalog
            ),
            playback_state=_deserialize_viewer_mapping(
                payload, "playback_state", catalog=catalog
            ),
            summary=_deserialize_viewer_mapping(payload, "summary", catalog=catalog),
            options=_deserialize_viewer_mapping(payload, "options", catalog=catalog),
            workspace_invalidation_epoch=_nonnegative_int_field(
                payload, "workspace_invalidation_epoch"
            ),
            node_invalidation_epoch=_nonnegative_int_field(
                payload, "node_invalidation_epoch"
            ),
        )
    if event_type == "viewer_query_result":
        return ViewerQueryResultEvent(
            request_id=_string_field(payload, "request_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            session_id=_string_field(payload, "session_id"),
            backend_id=_string_field(payload, "backend_id"),
            query_type=_string_field(payload, "query_type"),
            supported=_bool_field(payload, "supported"),
            value=_deserialize_viewer_mapping(payload, "value", catalog=catalog),
            explanation=_string_field(payload, "explanation"),
            workspace_invalidation_epoch=_nonnegative_int_field(
                payload, "workspace_invalidation_epoch"
            ),
            node_invalidation_epoch=_nonnegative_int_field(
                payload, "node_invalidation_epoch"
            ),
        )
    if event_type == "viewer_session_failed":
        return ViewerSessionFailedEvent(
            request_id=_string_field(payload, "request_id"),
            workspace_id=_string_field(payload, "workspace_id"),
            node_id=_string_field(payload, "node_id"),
            session_id=_string_field(payload, "session_id"),
            command=_string_field(payload, "command"),
            error=_string_field(payload, "error"),
            workspace_invalidation_epoch=_nonnegative_int_field(
                payload, "workspace_invalidation_epoch"
            ),
            node_invalidation_epoch=_nonnegative_int_field(
                payload, "node_invalidation_epoch"
            ),
        )
    raise ValueError(f"Unknown event type: {event_type!r}")


__all__ = [
    "WorkerCommand",
    "WorkerEvent",
    "coerce_start_run_command",
    "command_to_dict",
    "dict_to_command",
    "dict_to_event",
    "event_to_dict",
]
