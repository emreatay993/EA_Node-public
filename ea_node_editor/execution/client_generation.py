# Purpose: Frozen execution-generation, run/viewer reservation, and resource-lease records.
# Map: subsystems/execution.md
# Tests: tests/test_backend_client.py
# Landmarks: ExecutionGenerationSnapshot, ExecutionRunReservation, ViewerInvalidationReservation, ExecutionResourceLease
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ea_node_editor.execution.backends import (
    ExecutionBackendSelection,
)
from ea_node_editor.execution.solution_identity import canonical_digest
from ea_node_editor.execution.viewer_messages import (
    viewer_epoch_snapshot_digest,
)
from ea_node_editor.runtime_contracts import (
    RuntimeHandleRef,
)


@dataclass(frozen=True, slots=True)
class _ViewerInvalidationSnapshot:
    generation: int | None
    workspace_epoch: int
    node_epochs: tuple[tuple[str, int], ...]
    snapshot_digest: str


@dataclass(frozen=True, slots=True)
class ExecutionGenerationSnapshot:
    selection: ExecutionBackendSelection
    backend_generation: int
    runtime_generation: int
    environment_digest: str
    available: bool
    reason: str = ""

    def route_compatible_with(self, selection: ExecutionBackendSelection) -> bool:
        return _result_affecting_selection_payload(self.selection) == (
            _result_affecting_selection_payload(selection)
        )

    def compatible_with(self, other: object) -> bool:
        return bool(
            isinstance(other, ExecutionGenerationSnapshot)
            and self.route_compatible_with(other.selection)
            and self.backend_generation == other.backend_generation
            and self.runtime_generation == other.runtime_generation
            and self.environment_digest == other.environment_digest
            and self.available == other.available
        )


@dataclass(frozen=True, slots=True)
class ExecutionRunReservation:
    run_id: str
    workspace_id: str
    selection: ExecutionBackendSelection
    generation_snapshot: ExecutionGenerationSnapshot


@dataclass(frozen=True, slots=True)
class ViewerInvalidationReservation:
    reservation_id: str
    run_id: str
    preparation_id: str
    workspace_id: str
    node_ids: tuple[str, ...] | None
    process_snapshot: _ViewerInvalidationSnapshot
    trusted_snapshot: _ViewerInvalidationSnapshot
    external_snapshot: _ViewerInvalidationSnapshot
    projection_snapshot: _ViewerInvalidationSnapshot
    selected_snapshot: _ViewerInvalidationSnapshot
    client: Any

    @property
    def workspace_epoch(self) -> int:
        return self.selected_snapshot.workspace_epoch

    @property
    def node_epochs(self) -> tuple[tuple[str, int], ...]:
        return self.selected_snapshot.node_epochs

    @property
    def snapshot_digest(self) -> str:
        return self.selected_snapshot.snapshot_digest

    @property
    def backend_generation(self) -> int:
        return int(self.selected_snapshot.generation or 0)


def _participant_viewer_snapshot(
    *,
    workspace_id: str,
    node_ids: tuple[str, ...] | None,
    workspace_epochs: Mapping[str, int],
    node_epochs: Mapping[tuple[str, str], int],
    generation: int | None,
) -> _ViewerInvalidationSnapshot:
    workspace_epoch = int(workspace_epochs.get(workspace_id, 0))
    if node_ids is None:
        workspace_epoch += 1
        planned_node_epochs: tuple[tuple[str, int], ...] = ()
    else:
        planned_node_epochs = tuple(
            (
                node_id,
                int(node_epochs.get((workspace_id, node_id), 0)) + 1,
            )
            for node_id in node_ids
        )
    return _ViewerInvalidationSnapshot(
        generation=generation,
        workspace_epoch=workspace_epoch,
        node_epochs=planned_node_epochs,
        snapshot_digest=viewer_epoch_snapshot_digest(
            workspace_id=workspace_id,
            node_ids=node_ids,
            workspace_epoch=workspace_epoch,
            node_epochs=planned_node_epochs,
        ),
    )


@dataclass(frozen=True, slots=True)
class ExecutionResourceLease:
    client: Any
    value: RuntimeHandleRef


def _result_affecting_selection_payload(
    selection: ExecutionBackendSelection,
) -> dict[str, object]:
    return {
        "backend_id": selection.backend_id,
        "isolation": selection.isolation,
        "trusted_in_process": selection.trusted_in_process,
        "external_subprocess": selection.external_subprocess,
        "python_executable_digest": canonical_digest(
            str(selection.python_executable or "")
        ),
        "runtime_backend_ids": selection.runtime_backend_ids,
    }
