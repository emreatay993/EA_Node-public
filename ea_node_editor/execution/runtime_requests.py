# Purpose: Headless runtime load/workspace/cancellation/execution request and result records.
# Map: subsystems/execution.md
# Tests: tests/test_runtime_requests.py
# Landmarks: ExecutionRequest; ExecutionResult; ProjectLoadRequest
"""Qt-free Corex runtime API and CLI entry point."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ea_node_editor.execution.backends import (
    ExecutionBackendPolicy,
)
from ea_node_editor.execution.prepared_execution import (
    RecomputeMode,
)
from ea_node_editor.execution.runtime_snapshot import (
    RuntimeSnapshot,
)
from ea_node_editor.runtime_contracts.settled_results import (
    SettledPortResult,
)

ExecutionStatus = Literal["completed", "failed", "stopped", "timeout"]


ExecutionEvent = dict[str, Any]


ExecutionEventCallback = Callable[[ExecutionEvent], None]


@dataclass(frozen=True, slots=True)
class ProjectLoadRequest:
    project_path: str | Path
    extra_plugin_dirs: tuple[Path, ...] = field(default_factory=tuple)

    def normalized_path(self) -> Path:
        return Path(self.project_path).expanduser()


@dataclass(frozen=True, slots=True)
class WorkspaceSelection:
    workspace_id: str = ""


@dataclass(frozen=True, slots=True)
class CancellationRequest:
    run_id: str
    reason: str = "user"


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    project_path: str | Path = ""
    workspace_id: str = ""
    trigger: Mapping[str, Any] = field(default_factory=dict)
    runtime_snapshot: RuntimeSnapshot | Mapping[str, Any] | None = None
    execution_backend: ExecutionBackendPolicy | Mapping[str, Any] | str | None = None
    target_node_ids: tuple[str, ...] = field(default_factory=tuple)
    trigger_publications: Mapping[str, SettledPortResult] = field(default_factory=dict)
    trigger_captures: Mapping[str, SettledPortResult] = field(default_factory=dict)
    clicked_trigger_node_id: str = ""
    recompute_mode: RecomputeMode = RecomputeMode.REUSE_VALID

    def trigger_without_runtime_snapshot(
        self,
    ) -> tuple[
        dict[str, Any],
        RuntimeSnapshot | Mapping[str, Any] | None,
        ExecutionBackendPolicy | Mapping[str, Any] | str | None,
    ]:
        trigger_source = dict(self.trigger)
        snapshot = self.runtime_snapshot
        if snapshot is None:
            snapshot = trigger_source.pop("runtime_snapshot", None)
        else:
            trigger_source.pop("runtime_snapshot", None)
        execution_backend = self.execution_backend
        if execution_backend is None:
            execution_backend = trigger_source.pop("execution_backend", None)
        else:
            trigger_source.pop("execution_backend", None)
        trigger = copy.deepcopy(trigger_source)
        return trigger, snapshot, execution_backend


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    run_id: str
    workspace_id: str
    status: ExecutionStatus
    events: tuple[ExecutionEvent, ...] = field(default_factory=tuple)
    terminal_event: ExecutionEvent = field(default_factory=dict)
    error: str = ""
    traceback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workspace_id": self.workspace_id,
            "status": self.status,
            "error": self.error,
            "traceback": self.traceback,
            "terminal_event": copy.deepcopy(self.terminal_event),
            "events": [copy.deepcopy(event) for event in self.events],
        }
