from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

PauseLabel = Literal["Pause", "Resume"]
_LEGACY_SELECTED_WORKSPACE_ID = "__legacy_selected_workspace__"


@dataclass(frozen=True, slots=True)
class SelectedWorkspaceRunControlState:
    selected_workspace_owns_active_run: bool
    can_run_active_workspace: bool
    can_pause_active_workspace: bool
    can_stop_active_workspace: bool
    pause_label: PauseLabel


def event_targets_active_run(
    event: dict[str, Any],
    *,
    active_run_id: str,
    run_scoped_event_types: set[str] | frozenset[str],
) -> bool:
    event_type = str(event.get("type", ""))
    if event_type not in run_scoped_event_types:
        return True
    event_run_id = str(event.get("run_id", ""))
    return bool(active_run_id and event_run_id and event_run_id == active_run_id)


def selected_workspace_run_control_state(
    *,
    selected_workspace_id: str,
    active_run_id: str,
    active_run_workspace_id: str,
    engine_state: str,
) -> SelectedWorkspaceRunControlState:
    normalized_selected_workspace_id = str(selected_workspace_id or "").strip()
    normalized_active_run_id = str(active_run_id or "").strip()
    normalized_active_run_workspace_id = str(active_run_workspace_id or "").strip()
    normalized_engine_state = str(engine_state or "").strip()
    selected_workspace_owns_active_run = bool(normalized_active_run_id) and (
        normalized_selected_workspace_id == normalized_active_run_workspace_id
    )
    can_pause_active_workspace = selected_workspace_owns_active_run and normalized_engine_state in {"running", "paused"}
    pause_label: PauseLabel = (
        "Resume" if selected_workspace_owns_active_run and normalized_engine_state == "paused" else "Pause"
    )
    return SelectedWorkspaceRunControlState(
        selected_workspace_owns_active_run=selected_workspace_owns_active_run,
        can_run_active_workspace=not selected_workspace_owns_active_run,
        can_pause_active_workspace=can_pause_active_workspace,
        can_stop_active_workspace=selected_workspace_owns_active_run,
        pause_label=pause_label,
    )


def run_action_state(active_run_id: str, engine_state: str) -> tuple[bool, str]:
    # Keep the legacy two-value QAction seam available until later packets switch
    # callers onto the full selected-workspace projection.
    state = selected_workspace_run_control_state(
        selected_workspace_id=_LEGACY_SELECTED_WORKSPACE_ID,
        active_run_id=active_run_id,
        active_run_workspace_id=_LEGACY_SELECTED_WORKSPACE_ID if str(active_run_id or "").strip() else "",
        engine_state=engine_state,
    )
    return state.can_pause_active_workspace, state.pause_label
