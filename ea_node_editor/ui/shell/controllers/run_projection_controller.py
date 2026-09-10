# Purpose: Own shell-side execution status, output, solution-fact, availability,
#          elapsed, warning, and failure-focus projections.
# Map: feature_routes/run_controller_selected_workspace_state
# Tests: tests/test_run_projection_controller.py
# Landmarks: RunProjectionController
from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Literal, Protocol

from ea_node_editor.execution.prepared_execution import SolutionStateChangedEvent
from ea_node_editor.runtime_contracts.settled_results import (
    RootExecutionError,
    SettledPortResult,
    normalize_root_execution_errors,
    normalize_settled_output_mapping,
)
from ea_node_editor.ui.icon_registry import qicon
from ea_node_editor.ui.port_availability import (
    clear_port_availability_runtime_node,
    clear_port_availability_runtime_workspace,
    observe_node_outputs,
)
from ea_node_editor.ui.shell.run_flow import selected_workspace_run_control_state
from ea_node_editor.ui.shell.state import ShellRunState
from ea_node_editor.ui.support.solution_output_cache import (
    cache_accepted_output_record,
    remove_cached_nodes,
)


class _RunProjectionHostProtocol(Protocol):
    run_state: ShellRunState
    workspace_manager: Any
    model: Any
    registry: Any
    execution_client: Any
    action_run: Any
    action_stop: Any
    action_pause: Any
    run_controls_changed: Any
    run_failure_changed: Any
    node_execution_state_changed: Any

    def update_engine_status(self, state: str, details: str) -> None: ...

    def update_job_counters(
        self, running: int, queued: int, done: int, failed: int
    ) -> None: ...


class RunProjectionController:
    def __init__(self, host: _RunProjectionHostProtocol) -> None:
        self._host = host

    @property
    def _state(self) -> ShellRunState:
        return self._host.run_state

    def reset_runtime_projection(self) -> None:
        from ea_node_editor.ui.image_value_preview_provider import (
            clear_image_value_previews,
        )

        clear_image_value_previews()
        state = self._state
        for workspace_id in tuple(self._host.model.project.workspaces):
            clear_port_availability_runtime_workspace(workspace_id)
        state.cached_node_output_records_by_workspace_id.clear()
        state.node_output_run_counts_by_workspace_id.clear()
        state.node_output_cache_sequence = 0
        state.cached_node_elapsed_ms_by_workspace_id.clear()
        state.solution_project_id = ""
        state.solution_revision_by_workspace_id.clear()
        state.node_solution_facts_by_workspace_id.clear()
        state.runtime_warning_messages_by_workspace_id.clear()
        self.clear_node_execution_visualization_state()

    def prune_runtime_projection(self) -> None:
        state = self._state
        workspaces = self._host.model.project.workspaces
        workspace_ids = set(workspaces)
        for mapping in (
            state.cached_node_output_records_by_workspace_id,
            state.node_output_run_counts_by_workspace_id,
            state.cached_node_elapsed_ms_by_workspace_id,
            state.solution_revision_by_workspace_id,
            state.node_solution_facts_by_workspace_id,
            state.runtime_warning_messages_by_workspace_id,
        ):
            for workspace_id in tuple(mapping):
                if workspace_id not in workspace_ids:
                    mapping.pop(workspace_id, None)
        if (
            state.node_execution_workspace_id
            and state.node_execution_workspace_id not in workspace_ids
        ):
            self.clear_node_execution_visualization_state()

    @staticmethod
    def clear_port_availability_for_nodes(
        workspace_id: str, node_ids: Iterable[object]
    ) -> None:
        for node_id in node_ids:
            clear_port_availability_runtime_node(
                str(workspace_id or "").strip(),
                str(node_id or "").strip(),
            )

    def project_node_settled(
        self,
        event: Mapping[str, Any],
        *,
        workspace_id: str,
        node_id: str,
        invalidated_during_run: bool = False,
    ) -> str:
        status = str(event.get("status", "completed") or "completed").strip().lower()
        warning_messages = self._normalize_warning_messages(event.get("warnings", ()))
        outputs = normalize_settled_output_mapping(
            event.get("outputs", {}),
            catalog=self._host.registry.data_types,
        )
        errors = normalize_root_execution_errors(event.get("errors", ()))
        settled_event = dict(event)
        settled_event["outputs"] = outputs
        self.sync_solution_facts(workspace_id, emit=False)
        if self._accepted_settlement_is_current(
            workspace_id,
            node_id,
            settled_event,
        ):
            self._observe_node_port_availability(workspace_id, node_id, settled_event)
            self._cache_node_outputs(workspace_id, node_id, settled_event)
        self.mark_node_execution_settled(
            workspace_id,
            node_id,
            status=status,
            errors=errors,
            elapsed_ms=float(event.get("elapsed_ms", 0.0) or 0.0),
            warning=bool(warning_messages),
            warning_messages=warning_messages,
            invalidated_during_run=invalidated_during_run,
        )
        return status

    def _observe_node_port_availability(
        self, workspace_id: str, node_id: str, event: Mapping[str, Any]
    ) -> None:
        workspace = self._host.model.project.workspaces.get(
            str(workspace_id or "").strip()
        )
        if workspace is None:
            return
        node = workspace.nodes.get(str(node_id or "").strip())
        if node is None:
            return
        outputs = event.get("outputs")
        if not isinstance(outputs, Mapping):
            return
        value_outputs = {
            str(port_key): result
            for port_key, result in outputs.items()
            if isinstance(result, SettledPortResult) and result.status == "value"
        }
        observe_node_outputs(
            workspace_id=workspace.workspace_id,
            node_id=node.node_id,
            node_type_id=node.type_id,
            outputs=value_outputs,
        )

    def _accepted_settlement_is_current(
        self,
        workspace_id: str,
        node_id: str,
        event: Mapping[str, Any],
    ) -> bool:
        if not bool(event.get("accepted_solution_record", False)):
            return False
        expected_record_id = str(event.get("record_id", "") or "").strip()
        expected_solution_key = str(event.get("solution_key", "") or "").strip()
        expected_revision = event.get("solution_fact_revision")
        if (
            not expected_record_id
            or not expected_solution_key
            or isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
        ):
            return False
        project_id = str(getattr(self._host.model.project, "project_id", "") or "")
        query = getattr(self._host.execution_client, "solution_facts", None)
        if not project_id or not callable(query):
            return False
        for fact in query(project_id, str(workspace_id or "").strip()):
            if str(getattr(fact, "node_id", "") or "") != str(node_id or ""):
                continue
            return (
                str(getattr(getattr(fact, "freshness", ""), "value", "")) == "current"
                and getattr(fact, "revision", None) == expected_revision
                and getattr(fact, "retained_record_id", None) == expected_record_id
                and getattr(fact, "retained_solution_key", None)
                == expected_solution_key
            )
        return False

    def _cache_node_outputs(
        self, workspace_id: str, node_id: str, event: Mapping[str, Any]
    ) -> None:
        normalized_workspace_id = str(workspace_id or "").strip()
        normalized_node_id = str(node_id or "").strip()
        if not normalized_workspace_id or not normalized_node_id:
            return
        outputs = event.get("outputs")
        if not isinstance(outputs, Mapping):
            return
        typed_outputs = normalize_settled_output_mapping(outputs)
        observed_at_epoch_ms = self._current_epoch_ms()
        enriched_event = dict(event)
        enriched_event["observed_at_epoch_ms"] = observed_at_epoch_ms
        cache_accepted_output_record(
            self._state,
            workspace_id=normalized_workspace_id,
            node_id=normalized_node_id,
            event=enriched_event,
            outputs=typed_outputs,
            catalog=self._host.registry.data_types,
        )

    def set_run_ui_state(
        self,
        state: Literal["ready", "running", "paused", "error"],
        details: str,
        running: int,
        queued: int,
        done: int,
        failed: int,
        *,
        clear_active_run: Callable[[], None] | None = None,
    ) -> None:
        self._state.engine_state_value = state
        self._host.update_engine_status(state, details)
        self._host.update_job_counters(running, queued, done, failed)
        if clear_active_run is not None:
            clear_active_run()
        self.update_run_actions()

    def update_run_actions(self) -> None:
        projection = selected_workspace_run_control_state(
            selected_workspace_id=self._host.workspace_manager.active_workspace_id(),
            active_run_id=self._state.active_run_id,
            active_run_workspace_id=self._state.active_run_workspace_id,
            engine_state=self._state.engine_state_value,
        )
        self._host.action_run.setEnabled(projection.can_run_active_workspace)
        self._host.action_stop.setEnabled(projection.can_stop_active_workspace)
        self._host.action_pause.setEnabled(projection.can_pause_active_workspace)
        self._host.action_pause.setText(projection.pause_label)
        if hasattr(self._host.action_pause, "setIcon"):
            self._host.action_pause.setIcon(
                qicon("resume" if projection.pause_label == "Resume" else "pause")
            )
        self._host.run_controls_changed.emit()

    def normalize_node_execution_workspace_id(self, workspace_id: str) -> str:
        normalized_workspace_id = str(workspace_id or "").strip()
        if normalized_workspace_id:
            return normalized_workspace_id
        for candidate in (
            self._state.active_run_workspace_id,
            self._state.node_execution_workspace_id,
        ):
            normalized_candidate = str(candidate or "").strip()
            if normalized_candidate:
                return normalized_candidate
        return ""

    def commit_node_execution_state_change(self) -> None:
        self._state.node_execution_revision += 1
        self._host.node_execution_state_changed.emit()

    def mark_node_execution_running(
        self,
        workspace_id: str,
        node_id: str,
        *,
        started_at_epoch_ms: float = 0.0,
    ) -> None:
        normalized_node_id = str(node_id or "").strip()
        if not normalized_node_id:
            return
        normalized_workspace_id = self.normalize_node_execution_workspace_id(
            workspace_id
        )
        if not normalized_workspace_id:
            return
        resolved_started_at_epoch_ms = self._coerce_nonnegative_timing_ms(
            started_at_epoch_ms
        )
        if resolved_started_at_epoch_ms <= 0.0:
            resolved_started_at_epoch_ms = self._current_epoch_ms()
        state = self._state
        changed = False
        workspace_warnings = state.runtime_warning_messages_by_workspace_id.get(
            normalized_workspace_id
        )
        if workspace_warnings is not None and self._discard_node_ids_from_mapping(
            workspace_warnings,
            {normalized_node_id},
        ):
            if not workspace_warnings:
                state.runtime_warning_messages_by_workspace_id.pop(
                    normalized_workspace_id, None
                )
            changed = True
        if state.node_execution_workspace_id != normalized_workspace_id:
            state.node_execution_workspace_id = normalized_workspace_id
            state.running_node_ids.clear()
            state.completed_node_ids.clear()
            state.empty_node_ids.clear()
            state.failed_node_ids.clear()
            state.blocked_node_ids.clear()
            state.root_errors_by_node_id.clear()
            state.warning_node_ids.clear()
            state.running_node_started_at_epoch_ms_by_node_id.clear()
            changed = True
        for settled_ids in (
            state.completed_node_ids,
            state.empty_node_ids,
            state.failed_node_ids,
            state.blocked_node_ids,
        ):
            if normalized_node_id in settled_ids:
                settled_ids.discard(normalized_node_id)
                changed = True
        if normalized_node_id in state.root_errors_by_node_id:
            state.root_errors_by_node_id.pop(normalized_node_id, None)
            changed = True
        if normalized_node_id in state.warning_node_ids:
            state.warning_node_ids.discard(normalized_node_id)
            changed = True
        if normalized_node_id not in state.running_node_ids:
            state.running_node_ids.add(normalized_node_id)
            changed = True
        if (
            state.running_node_started_at_epoch_ms_by_node_id.get(normalized_node_id)
            != resolved_started_at_epoch_ms
        ):
            state.running_node_started_at_epoch_ms_by_node_id[normalized_node_id] = (
                resolved_started_at_epoch_ms
            )
            changed = True
        if changed:
            self.commit_node_execution_state_change()

    def mark_node_execution_settled(
        self,
        workspace_id: str,
        node_id: str,
        *,
        status: str = "completed",
        errors: tuple[RootExecutionError, ...] = (),
        elapsed_ms: float = 0.0,
        warning: bool = False,
        warning_messages: object = (),
        invalidated_during_run: bool = False,
    ) -> None:
        normalized_node_id = str(node_id or "").strip()
        if not normalized_node_id:
            return
        normalized_workspace_id = self.normalize_node_execution_workspace_id(
            workspace_id
        )
        if not normalized_workspace_id:
            return
        state = self._state
        normalized_status = str(status or "completed").strip().lower()
        if normalized_status not in {"completed", "empty", "failed", "blocked"}:
            normalized_status = "completed"
        normalized_warning_messages = self._normalize_warning_messages(warning_messages)
        changed = False
        if state.node_execution_workspace_id != normalized_workspace_id:
            state.node_execution_workspace_id = normalized_workspace_id
            state.running_node_ids.clear()
            state.completed_node_ids.clear()
            state.empty_node_ids.clear()
            state.failed_node_ids.clear()
            state.blocked_node_ids.clear()
            state.root_errors_by_node_id.clear()
            state.warning_node_ids.clear()
            state.running_node_started_at_epoch_ms_by_node_id.clear()
            changed = True
        started_at_lookup = state.running_node_started_at_epoch_ms_by_node_id
        had_started_at = normalized_node_id in started_at_lookup
        started_at_epoch_ms = started_at_lookup.pop(normalized_node_id, 0.0)
        if had_started_at:
            changed = True
        if normalized_node_id in state.running_node_ids:
            state.running_node_ids.discard(normalized_node_id)
            changed = True
        settled_ids_by_status = {
            "completed": state.completed_node_ids,
            "empty": state.empty_node_ids,
            "failed": state.failed_node_ids,
            "blocked": state.blocked_node_ids,
        }
        for candidate_status, settled_ids in settled_ids_by_status.items():
            should_contain = candidate_status == normalized_status
            if should_contain and normalized_node_id not in settled_ids:
                settled_ids.add(normalized_node_id)
                changed = True
            elif not should_contain and normalized_node_id in settled_ids:
                settled_ids.discard(normalized_node_id)
                changed = True
        if errors:
            if state.root_errors_by_node_id.get(normalized_node_id) != errors:
                state.root_errors_by_node_id[normalized_node_id] = errors
                changed = True
        elif normalized_node_id in state.root_errors_by_node_id:
            state.root_errors_by_node_id.pop(normalized_node_id, None)
            changed = True
        if warning and not invalidated_during_run:
            if normalized_node_id not in state.warning_node_ids:
                state.warning_node_ids.add(normalized_node_id)
                changed = True
        elif normalized_node_id in state.warning_node_ids:
            state.warning_node_ids.discard(normalized_node_id)
            changed = True
        workspace_warnings = state.runtime_warning_messages_by_workspace_id.get(
            normalized_workspace_id
        )
        if normalized_warning_messages and not invalidated_during_run:
            if workspace_warnings is None:
                workspace_warnings = {}
                state.runtime_warning_messages_by_workspace_id[
                    normalized_workspace_id
                ] = workspace_warnings
            if (
                workspace_warnings.get(normalized_node_id)
                != normalized_warning_messages
            ):
                workspace_warnings[normalized_node_id] = normalized_warning_messages
                changed = True
        elif workspace_warnings is not None and self._discard_node_ids_from_mapping(
            workspace_warnings,
            {normalized_node_id},
        ):
            if not workspace_warnings:
                state.runtime_warning_messages_by_workspace_id.pop(
                    normalized_workspace_id, None
                )
            changed = True
        worker_elapsed_ms = self._coerce_nonnegative_timing_ms(elapsed_ms)
        should_cache_elapsed = False
        resolved_elapsed_ms = 0.0
        if worker_elapsed_ms > 0.0:
            resolved_elapsed_ms = worker_elapsed_ms
            should_cache_elapsed = True
        elif started_at_epoch_ms > 0.0:
            resolved_elapsed_ms = max(
                0.0, self._current_epoch_ms() - started_at_epoch_ms
            )
            should_cache_elapsed = True
        if should_cache_elapsed and not invalidated_during_run:
            workspace_cache = state.cached_node_elapsed_ms_by_workspace_id.setdefault(
                normalized_workspace_id,
                {},
            )
            if workspace_cache.get(normalized_node_id) != resolved_elapsed_ms:
                workspace_cache[normalized_node_id] = resolved_elapsed_ms
                changed = True
        if changed:
            self.commit_node_execution_state_change()

    def handle_solution_state_changed(self, event: Mapping[str, Any]) -> None:
        try:
            changed = SolutionStateChangedEvent.from_payload(event)
        except (TypeError, ValueError):
            return
        project_id = str(getattr(self._host.model.project, "project_id", "") or "")
        if changed.project_id != project_id:
            return
        state = self._state
        previous_revision = int(
            state.solution_revision_by_workspace_id.get(changed.workspace_id, -1)
        )
        if changed.solution_revision <= previous_revision:
            return
        state.solution_project_id = changed.project_id
        state.solution_revision_by_workspace_id[changed.workspace_id] = (
            changed.solution_revision
        )
        self.sync_solution_facts(changed.workspace_id, emit=False)
        expired = set(changed.expired_node_ids)
        removed = set(changed.removed_node_ids)
        self.clear_node_projection_state(
            changed.workspace_id,
            expired | removed,
            removed_node_ids=removed,
        )
        for node_id in expired | removed:
            clear_port_availability_runtime_node(changed.workspace_id, node_id)
        self.commit_node_execution_state_change()
        if changed.reason_code == "project_session_reset":
            state.solution_revision_by_workspace_id.pop(changed.workspace_id, None)

    def sync_solution_facts(self, workspace_id: str, *, emit: bool = True) -> None:
        workspace_key = str(workspace_id or "").strip()
        project_id = str(getattr(self._host.model.project, "project_id", "") or "")
        query = getattr(self._host.execution_client, "solution_facts", None)
        if not workspace_key or not project_id or not callable(query):
            return
        facts = tuple(query(project_id, workspace_key))
        self._state.solution_project_id = project_id
        if facts:
            self._state.node_solution_facts_by_workspace_id[workspace_key] = {
                fact.node_id: fact for fact in facts
            }
        else:
            self._state.node_solution_facts_by_workspace_id.pop(workspace_key, None)
        if emit:
            self.commit_node_execution_state_change()

    def clear_node_projection_state(
        self,
        workspace_id: str,
        node_ids: set[str],
        *,
        removed_node_ids: set[str] | None = None,
    ) -> None:
        if not node_ids:
            return
        state = self._state
        if state.node_execution_workspace_id == workspace_id:
            self._discard_node_ids_from_mapping(
                state.running_node_started_at_epoch_ms_by_node_id, node_ids
            )
            for values in (
                state.running_node_ids,
                state.completed_node_ids,
                state.empty_node_ids,
                state.failed_node_ids,
                state.blocked_node_ids,
                state.warning_node_ids,
            ):
                values.difference_update(node_ids)
            self._discard_node_ids_from_mapping(state.root_errors_by_node_id, node_ids)
        warnings = state.runtime_warning_messages_by_workspace_id.get(workspace_id)
        if warnings is not None:
            self._discard_node_ids_from_mapping(warnings, node_ids)
            if not warnings:
                state.runtime_warning_messages_by_workspace_id.pop(workspace_id, None)
        elapsed = state.cached_node_elapsed_ms_by_workspace_id.get(workspace_id)
        if elapsed is not None:
            self._discard_node_ids_from_mapping(elapsed, node_ids)
            if not elapsed:
                state.cached_node_elapsed_ms_by_workspace_id.pop(workspace_id, None)
        if removed_node_ids:
            remove_cached_nodes(state, workspace_id, removed_node_ids)

    def clear_node_execution_visualization_state(self) -> None:
        state = self._state
        changed = False
        if (
            state.node_execution_workspace_id
            or state.running_node_ids
            or state.completed_node_ids
            or state.empty_node_ids
            or state.failed_node_ids
            or state.blocked_node_ids
            or state.root_errors_by_node_id
            or state.warning_node_ids
            or state.running_node_started_at_epoch_ms_by_node_id
        ):
            state.node_execution_workspace_id = ""
            state.running_node_ids.clear()
            state.completed_node_ids.clear()
            state.empty_node_ids.clear()
            state.failed_node_ids.clear()
            state.blocked_node_ids.clear()
            state.root_errors_by_node_id.clear()
            state.warning_node_ids.clear()
            state.running_node_started_at_epoch_ms_by_node_id.clear()
            changed = True
        if changed:
            self.commit_node_execution_state_change()

    def clear_node_timing_and_warning_state(self) -> None:
        state = self._state
        changed = False
        for mapping in (
            state.running_node_started_at_epoch_ms_by_node_id,
            state.cached_node_elapsed_ms_by_workspace_id,
            state.runtime_warning_messages_by_workspace_id,
        ):
            if mapping:
                mapping.clear()
                changed = True
        if changed:
            self.commit_node_execution_state_change()

    def set_run_failure_focus(
        self,
        workspace_id: str,
        node_id: str,
        *,
        node_title: str = "",
    ) -> None:
        normalized_workspace_id = str(workspace_id or "").strip()
        normalized_node_id = str(node_id or "").strip()
        normalized_node_title = str(node_title or "").strip()
        state = self._state
        if (
            state.failed_workspace_id == normalized_workspace_id
            and state.failed_node_id == normalized_node_id
            and state.failed_node_title == normalized_node_title
        ):
            return
        state.failed_workspace_id = normalized_workspace_id
        state.failed_node_id = normalized_node_id
        state.failed_node_title = normalized_node_title
        self._host.run_failure_changed.emit()

    def clear_run_failure_focus(self) -> None:
        state = self._state
        if not (
            state.failed_workspace_id or state.failed_node_id or state.failed_node_title
        ):
            return
        state.failed_workspace_id = ""
        state.failed_node_id = ""
        state.failed_node_title = ""
        self._host.run_failure_changed.emit()

    @staticmethod
    def _discard_node_ids_from_mapping(
        mapping: dict[str, Any], node_ids: set[str]
    ) -> bool:
        changed = False
        for node_id in tuple(node_ids):
            if node_id in mapping:
                mapping.pop(node_id, None)
                changed = True
        return changed

    @staticmethod
    def _normalize_warning_messages(warnings: object) -> tuple[str, ...]:
        if isinstance(warnings, str):
            values: Iterable[object] = (warnings,)
        elif isinstance(warnings, (list, tuple, set, frozenset)):
            values = warnings
        else:
            return ()
        normalized: list[str] = []
        for warning in values:
            message = " ".join(str(warning or "").split())
            if not message or message in normalized:
                continue
            normalized.append(message[:240])
            if len(normalized) == 3:
                break
        return tuple(normalized)

    @staticmethod
    def _coerce_nonnegative_timing_ms(value: object) -> float:
        try:
            normalized = float(value)
        except (TypeError, ValueError):
            return 0.0
        return normalized if normalized >= 0.0 else 0.0

    @staticmethod
    def _current_epoch_ms() -> float:
        return time.time() * 1000.0


__all__ = ["RunProjectionController"]
