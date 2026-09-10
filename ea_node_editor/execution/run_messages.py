# Purpose: Define run, control, node-settlement, trigger, log, and protocol-error messages.
# Map: subsystems/execution.md
# Tests: tests/test_run_messages.py, tests/test_protocol_codec.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ea_node_editor.execution.backends import ExecutionBackendSelection
from ea_node_editor.execution.prepared_execution import (
    AcceptedOutputPayload,
    PreparedNodeDecision,
)
from ea_node_editor.execution.registry_agreement import (
    CatalogRevisionRecord,
    EMPTY_REGISTRY_CONTRACT_FINGERPRINT,
)
from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot
from ea_node_editor.nodes.function_plugin import PluginBundleRef
from ea_node_editor.runtime_contracts import settled_results as _settled

EngineState = Literal["ready", "running", "paused", "error"]
RunTransition = Literal["start", "pause", "resume", "stop", "complete", "fail"]
NodeSettlementStatus = Literal["completed", "empty", "failed", "blocked"]


@dataclass(frozen=True)
class StartRunCommand:
    type: Literal["start_run"] = "start_run"
    run_id: str = ""
    project_path: str = ""
    workspace_id: str = ""
    trigger: dict[str, Any] = field(default_factory=dict)
    runtime_snapshot: RuntimeSnapshot | None = None
    execution_backend: ExecutionBackendSelection = field(
        default_factory=ExecutionBackendSelection
    )
    target_node_ids: tuple[str, ...] = ()
    recompute_mode: str = "reuse_valid"
    trigger_publications: dict[str, _settled.SettledPortResult] = field(
        default_factory=dict
    )
    trigger_captures: dict[str, _settled.SettledPortResult] = field(
        default_factory=dict
    )
    clicked_trigger_node_id: str = ""
    developer_mode: bool = False
    catalog_fingerprint: str = ""
    catalog_revisions: tuple[CatalogRevisionRecord, ...] = ()
    plugin_bundles: tuple[PluginBundleRef, ...] = ()
    plugin_fingerprint: str = ""
    runtime_registry_fingerprint: str = ""
    registry_contract_fingerprint: str = EMPTY_REGISTRY_CONTRACT_FINGERPRINT
    addon_runtime_config: tuple[tuple[str, bool], ...] = ()
    preparation_id: str = ""
    solution_namespace_id: str = ""
    execution_affecting_workspace_revision: int = 0
    dispatch_runtime_generation: int = 0
    runtime_snapshot_fingerprint: str = ""
    execution_plan_fingerprint: str = ""
    workflow_interface_revision: int = 0
    workflow_interface_digest: str = ""
    execution_environment_digest: str = ""
    trigger_publication_generations: tuple[tuple[str, int], ...] = ()
    node_decisions: tuple[PreparedNodeDecision, ...] = ()
    accepted_output_payloads: tuple[AcceptedOutputPayload, ...] = ()
    viewer_invalidation_node_ids: tuple[str, ...] | None = None
    viewer_workspace_invalidation_epoch: int = 0
    viewer_node_invalidation_epochs: tuple[tuple[str, int], ...] = ()
    viewer_invalidation_reservation_id: str = ""
    viewer_epoch_snapshot_digest: str = ""


@dataclass(frozen=True)
class StopRunCommand:
    type: Literal["stop_run"] = "stop_run"
    run_id: str = ""
    workspace_id: str = ""


@dataclass(frozen=True)
class PauseRunCommand:
    type: Literal["pause_run"] = "pause_run"
    run_id: str = ""


@dataclass(frozen=True)
class ResumeRunCommand:
    type: Literal["resume_run"] = "resume_run"
    run_id: str = ""


@dataclass(frozen=True)
class ShutdownCommand:
    type: Literal["shutdown"] = "shutdown"


@dataclass(frozen=True)
class RetireWorkspaceCommand:
    type: Literal["retire_workspace"] = "retire_workspace"
    request_id: str = ""
    workspace_id: str = ""


@dataclass(frozen=True)
class WorkspaceRetiredEvent:
    type: Literal["workspace_retired"] = "workspace_retired"
    request_id: str = ""
    workspace_id: str = ""
    retired_count: str = "0"


@dataclass(frozen=True)
class CommitRunPreflightCommand:
    type: Literal["commit_run_preflight"] = "commit_run_preflight"
    run_id: str = ""
    viewer_invalidation_reservation_id: str = ""
    viewer_epoch_snapshot_digest: str = ""


@dataclass(frozen=True)
class CancelRunPreflightCommand:
    type: Literal["cancel_run_preflight"] = "cancel_run_preflight"
    run_id: str = ""
    viewer_invalidation_reservation_id: str = ""
    viewer_epoch_snapshot_digest: str = ""


@dataclass(frozen=True)
class RunPreflightAcceptedEvent:
    type: Literal["run_preflight_accepted"] = "run_preflight_accepted"
    run_id: str = ""
    workspace_id: str = ""
    preparation_id: str = ""
    viewer_invalidation_reservation_id: str = ""
    viewer_epoch_snapshot_digest: str = ""


@dataclass(frozen=True)
class RunStartedEvent:
    type: Literal["run_started"] = "run_started"
    run_id: str = ""
    workspace_id: str = ""


@dataclass(frozen=True)
class RunStateEvent:
    type: Literal["run_state"] = "run_state"
    run_id: str = ""
    workspace_id: str = ""
    state: EngineState = "ready"
    transition: RunTransition | str = ""
    reason: str = ""


@dataclass(frozen=True)
class RunCompletedEvent:
    type: Literal["run_completed"] = "run_completed"
    run_id: str = ""
    workspace_id: str = ""
    state: Literal["ready"] = "ready"


@dataclass(frozen=True)
class RunFailedEvent:
    type: Literal["run_failed"] = "run_failed"
    run_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    error: str = ""
    traceback: str = ""
    state: Literal["error"] = "error"
    fatal: bool = False


@dataclass(frozen=True)
class RunStoppedEvent:
    type: Literal["run_stopped"] = "run_stopped"
    run_id: str = ""
    workspace_id: str = ""
    reason: str = ""
    state: Literal["ready"] = "ready"


@dataclass(frozen=True)
class NodeStartedEvent:
    type: Literal["node_started"] = "node_started"
    run_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    started_at_epoch_ms: float = 0.0


@dataclass(frozen=True)
class NodeSettledEvent:
    type: Literal["node_settled"] = "node_settled"
    run_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    status: NodeSettlementStatus | str = "completed"
    elapsed_ms: float = 0.0
    outputs: dict[str, _settled.SettledPortResult] = field(default_factory=dict)
    errors: tuple[_settled.RootExecutionError, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    disposition: str = ""
    decision_reason: str = "legacy_direct_run"
    solution_key: str = ""
    record_id: str = ""
    residency: str = ""


@dataclass(frozen=True)
class ObservationInvalidationRequestedEvent:
    type: Literal["observation_invalidation_requested"] = (
        "observation_invalidation_requested"
    )
    run_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    root_node_id: str = ""
    reason_code: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "run_id",
            "workspace_id",
            "node_id",
            "root_node_id",
            "reason_code",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 256:
                raise ValueError(
                    "observation invalidation identities must be bounded non-empty strings"
                )
            object.__setattr__(self, field_name, value.strip())


@dataclass(frozen=True)
class TriggerCaptureSettledEvent:
    type: Literal["trigger_capture_settled"] = "trigger_capture_settled"
    run_id: str = ""
    workspace_id: str = ""
    trigger_node_id: str = ""
    result: _settled.SettledPortResult = field(
        default_factory=_settled.SettledPortResult
    )


@dataclass(frozen=True)
class TriggerPublishedEvent:
    type: Literal["trigger_published"] = "trigger_published"
    run_id: str = ""
    workspace_id: str = ""
    trigger_node_id: str = ""
    result: _settled.SettledPortResult = field(
        default_factory=_settled.SettledPortResult
    )


@dataclass(frozen=True)
class LogEvent:
    type: Literal["log"] = "log"
    run_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    level: str = "info"
    message: str = ""


@dataclass(frozen=True)
class ProtocolErrorEvent:
    type: Literal["protocol_error"] = "protocol_error"
    run_id: str = ""
    workspace_id: str = ""
    request_id: str = ""
    command: str = ""
    error: str = ""


def normalize_target_node_ids(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        candidates = tuple(value)
    else:
        raise ValueError("target_node_ids must be a list.")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, str):
            raise ValueError(f"target_node_ids[{index}] must be a string.")
        node_id = candidate.strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        normalized.append(node_id)
    return tuple(normalized)


__all__ = [
    "CancelRunPreflightCommand",
    "CommitRunPreflightCommand",
    "EngineState",
    "LogEvent",
    "NodeSettlementStatus",
    "NodeSettledEvent",
    "NodeStartedEvent",
    "ObservationInvalidationRequestedEvent",
    "PauseRunCommand",
    "ProtocolErrorEvent",
    "ResumeRunCommand",
    "RunCompletedEvent",
    "RunFailedEvent",
    "RunPreflightAcceptedEvent",
    "RunStartedEvent",
    "RunStateEvent",
    "RunStoppedEvent",
    "RunTransition",
    "ShutdownCommand",
    "StartRunCommand",
    "RetireWorkspaceCommand",
    "WorkspaceRetiredEvent",
    "StopRunCommand",
    "TriggerCaptureSettledEvent",
    "TriggerPublishedEvent",
    "normalize_target_node_ids",
]
