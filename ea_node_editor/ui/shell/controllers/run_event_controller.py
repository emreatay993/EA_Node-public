# Purpose: Sole shell intake for decoded runtime execution events and terminal routing.
# Map: feature_routes/run_controller_selected_workspace_state
# Tests: tests/test_run_event_controller.py
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Protocol

from ea_node_editor.runtime_contracts.settled_results import (
    normalize_settled_port_result,
)
from ea_node_editor.ui.shell.controllers.run_controller import RunController
from ea_node_editor.ui.shell.controllers.run_projection_controller import (
    RunProjectionController,
)
from ea_node_editor.ui.shell.run_flow import event_targets_active_run
from ea_node_editor.ui.shell.state import ShellRunState

logger = logging.getLogger(__name__)


class _RunEventHostProtocol(Protocol):
    run_state: ShellRunState
    registry: Any
    console_panel: Any
    workspace_navigation_controller: Any
    viewer_session_bridge: Any
    _RUN_SCOPED_EVENT_TYPES: set[str]

    def update_notification_counters(
        self, warning_count: int, error_count: int
    ) -> None: ...


class RunEventController:
    def __init__(
        self,
        host: _RunEventHostProtocol,
        *,
        run_controller: RunController,
        projection_controller: RunProjectionController,
    ) -> None:
        self._host = host
        self._run_controller = run_controller
        self._projection = projection_controller

    @property
    def _state(self) -> ShellRunState:
        return self._host.run_state

    def handle_execution_event(self, event: dict[str, Any]) -> None:
        try:
            self._route_execution_event(event)
        except Exception:
            event_type = (
                event.get("type", "")
                if isinstance(event, Mapping)
                else type(event).__name__
            )
            logger.exception(
                "Error handling execution event (%s); keeping the app alive.",
                event_type,
            )
        self._deliver_viewer_execution_event(event)

    def _route_execution_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type", ""))
        if (
            event_type
            in {
                "run_preflight_accepted",
                "viewer_invalidation_committed",
            }
            and str(event.get("run_id", "")) != self._state.active_run_id
        ):
            return
        if not event_targets_active_run(
            event,
            active_run_id=self._state.active_run_id,
            run_scoped_event_types=self._host._RUN_SCOPED_EVENT_TYPES,
        ):
            return
        if event_type == "solution_state_changed":
            self._projection.handle_solution_state_changed(event)
            return
        if event_type == "viewer_invalidation_committed":
            self._adopt_committed_viewer_invalidation(event)
            return

        if event_type == "run_started":
            workspace_id = self._event_workspace_id(event)
            if workspace_id:
                self._state.active_run_workspace_id = workspace_id
            self._projection.clear_node_execution_visualization_state()
            self._projection.clear_run_failure_focus()
            self._run_controller.consume_run_start_runtime_snapshot(
                str(event.get("run_id", ""))
            )
        elif event_type == "node_started":
            self._projection.mark_node_execution_running(
                self._event_workspace_id(event),
                str(event.get("node_id", "")),
                started_at_epoch_ms=float(event.get("started_at_epoch_ms", 0.0) or 0.0),
            )
        elif event_type == "node_settled":
            workspace_id = self._event_workspace_id(event)
            node_id = str(event.get("node_id", ""))
            status = self._projection.project_node_settled(
                event,
                workspace_id=workspace_id,
                node_id=node_id,
                invalidated_during_run=self._run_controller.node_invalidated_during_active_run(
                    workspace_id,
                    node_id,
                ),
            )
            if status == "failed":
                self._host.workspace_navigation_controller.focus_failed_node(
                    workspace_id,
                    node_id,
                )
        elif event_type in {"trigger_capture_settled", "trigger_published"}:
            self._project_trigger_settlement(event_type, event)

        if event_type == "run_started" or (
            event_type
            in {
                "node_started",
                "node_settled",
                "trigger_capture_settled",
                "trigger_published",
            }
            and self._state.engine_state_value != "paused"
        ):
            self._projection.set_run_ui_state("running", "Running", 1, 0, 0, 0)

        if event_type == "log":
            self._host.console_panel.append_log(
                event.get("level", "info"), event.get("message", "")
            )
            self._update_notification_counters()
        elif event_type == "run_completed":
            self._projection.set_run_ui_state(
                "ready",
                "Completed",
                0,
                0,
                1,
                0,
                clear_active_run=self._run_controller.clear_active_run,
            )
            self._run_controller.drain_pending_auto_run()
        elif event_type == "run_failed":
            self._handle_run_failed(event)
        elif event_type == "run_stopped":
            self._projection.clear_node_execution_visualization_state()
            self._run_controller.clear_pending_auto_run()
            self._projection.set_run_ui_state(
                "ready",
                "Stopped",
                0,
                0,
                0,
                0,
                clear_active_run=self._run_controller.clear_active_run,
            )
        elif event_type == "run_state":
            self._handle_run_state(event)
        elif event_type == "protocol_error":
            self._run_controller.clear_pending_auto_run()
            self._host.console_panel.append_log(
                "error", event.get("error", "Execution protocol error.")
            )
            self._update_notification_counters()

    def _project_trigger_settlement(
        self, event_type: str, event: Mapping[str, Any]
    ) -> None:
        workspace_id = self._event_workspace_id(event)
        trigger_node_id = str(event.get("trigger_node_id", "") or "").strip()
        if not workspace_id or not trigger_node_id:
            return
        result = normalize_settled_port_result(
            event.get("result", {}),
            catalog=self._host.registry.data_types,
        )
        if event_type == "trigger_capture_settled":
            self._state.latest_trigger_inputs_by_workspace_id.setdefault(
                workspace_id, {}
            )[trigger_node_id] = result
            current_capture_ids = (
                self._state.current_trigger_capture_node_ids_by_workspace_id.setdefault(
                    workspace_id, set()
                )
            )
            if self._run_controller.node_invalidated_during_active_run(
                workspace_id,
                trigger_node_id,
            ):
                current_capture_ids.discard(trigger_node_id)
            else:
                current_capture_ids.add(trigger_node_id)
            if not current_capture_ids:
                self._state.current_trigger_capture_node_ids_by_workspace_id.pop(
                    workspace_id, None
                )
        else:
            self._state.trigger_publications_by_workspace_id.setdefault(
                workspace_id, {}
            )[trigger_node_id] = result
        self._projection.commit_node_execution_state_change()

    def _handle_run_failed(self, event: Mapping[str, Any]) -> None:
        self._projection.clear_node_execution_visualization_state()
        self._projection.set_run_ui_state("error", "Failed", 0, 0, 0, 1)
        self._host.console_panel.append_log(
            "error", event.get("error", "Unknown failure")
        )
        self._host.console_panel.append_log("error", event.get("traceback", ""))
        self._update_notification_counters()
        self._host.workspace_navigation_controller.focus_failed_node(
            event.get("workspace_id", ""),
            event.get("node_id", ""),
        )
        if bool(event.get("fatal", False)):
            self._invalidate_viewer_sessions_for_worker_reset()
        self._run_controller.clear_active_run()
        self._projection.update_run_actions()
        self._run_controller.clear_pending_auto_run()

    def _handle_run_state(self, event: Mapping[str, Any]) -> None:
        state = event.get("state", "ready")
        transition = str(event.get("transition", ""))
        if state == "paused" or transition == "pause":
            self._projection.set_run_ui_state("paused", "Paused", 1, 0, 0, 0)
        elif state == "running":
            self._projection.set_run_ui_state("running", "Running", 1, 0, 0, 0)
        elif transition == "stop":
            self._projection.clear_node_execution_visualization_state()
            self._run_controller.clear_pending_auto_run()
            self._projection.set_run_ui_state(
                "ready",
                "Stopped",
                0,
                0,
                0,
                0,
                clear_active_run=self._run_controller.clear_active_run,
            )
        elif state == "error":
            self._run_controller.clear_pending_auto_run()
            self._projection.set_run_ui_state("error", "Failed", 0, 0, 0, 1)

    def _event_workspace_id(self, event: Mapping[str, Any]) -> str:
        workspace_id = str(event.get("workspace_id", "") or "").strip()
        if workspace_id:
            return workspace_id
        return str(self._state.active_run_workspace_id or "").strip()

    def _adopt_committed_viewer_invalidation(self, event: Mapping[str, Any]) -> None:
        viewer_session_bridge = getattr(self._host, "viewer_session_bridge", None)
        if viewer_session_bridge is None:
            return
        adopt = getattr(viewer_session_bridge, "adopt_committed_invalidation", None)
        if not callable(adopt):
            return
        adopt(
            workspace_id=str(event.get("workspace_id", "")),
            node_ids=event.get("viewer_invalidation_node_ids"),
            workspace_epoch=event.get("viewer_workspace_invalidation_epoch", 0),
            node_epochs=event.get("viewer_node_invalidation_epochs", ()),
            snapshot_digest=str(event.get("viewer_epoch_snapshot_digest", "")),
            reason=str(event.get("reason", "workspace_rerun")),
            run_id=str(event.get("run_id", "")),
        )

    def _invalidate_viewer_sessions_for_worker_reset(self) -> None:
        viewer_session_bridge = getattr(self._host, "viewer_session_bridge", None)
        if viewer_session_bridge is None:
            return
        project_all_run_required = getattr(
            viewer_session_bridge, "project_all_run_required", None
        )
        if callable(project_all_run_required):
            project_all_run_required(reason="worker_reset")

    def _update_notification_counters(self) -> None:
        self._host.update_notification_counters(
            self._host.console_panel.warning_count,
            self._host.console_panel.error_count,
        )

    def _deliver_viewer_execution_event(self, event: dict[str, Any]) -> None:
        viewer_session_bridge = getattr(self._host, "viewer_session_bridge", None)
        if viewer_session_bridge is None:
            return
        consume = getattr(viewer_session_bridge, "handle_viewer_execution_event", None)
        if not callable(consume):
            return
        try:
            consume(event)
        except Exception:
            event_type = (
                event.get("type", "")
                if isinstance(event, Mapping)
                else type(event).__name__
            )
            logger.exception(
                "Error projecting viewer execution event (%s); "
                "run-state handling already completed.",
                event_type,
            )


__all__ = ["RunEventController"]
