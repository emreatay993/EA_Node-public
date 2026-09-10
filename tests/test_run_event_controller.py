# Purpose: Direct owner tests for shell runtime-event filtering, routing, and terminal transitions.
# Map: feature_routes/run_controller_selected_workspace_state
# Tests: tests/test_run_event_controller.py
from __future__ import annotations

import unittest
from unittest import mock

from PyQt6.QtCore import QCoreApplication, QObject, Qt, pyqtSignal

from tests.test_run_controller_unit import _RunHostStub, _run_controller


class _ViewerSessionBridgeStub:
    def __init__(self, host: _RunHostStub) -> None:
        self._host = host
        self.adoptions: list[dict] = []
        self.reset_reasons: list[str] = []
        self.execution_events: list[dict] = []
        self.completed_node_snapshots: list[set[str]] = []
        self.raise_on_delivery = False

    def adopt_committed_invalidation(self, **payload) -> None:  # noqa: ANN003
        self.adoptions.append(dict(payload))

    def project_all_run_required(self, *, reason: str) -> None:
        self.reset_reasons.append(reason)

    def handle_viewer_execution_event(self, event: dict) -> None:
        self.execution_events.append(dict(event))
        self.completed_node_snapshots.append(
            set(self._host.run_state.completed_node_ids)
        )
        if self.raise_on_delivery:
            raise RuntimeError("viewer projection exploded")


class _ExecutionEventEmitter(QObject):
    execution_event = pyqtSignal(dict)


class RunEventControllerTests(unittest.TestCase):
    def assert_run_controls(
        self,
        host: _RunHostStub,
        *,
        run_enabled: bool,
        pause_enabled: bool,
        stop_enabled: bool,
        pause_label: str,
    ) -> None:
        self.assertEqual(host.action_run.enabled, run_enabled)
        self.assertEqual(host.action_pause.enabled, pause_enabled)
        self.assertEqual(host.action_stop.enabled, stop_enabled)
        self.assertEqual(host.action_pause.text, pause_label)

    def test_stale_run_event_is_ignored(self) -> None:
        host = _RunHostStub()
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = (
            host.model.active_workspace.workspace_id
        )
        _run_controller(host)

        host.run_event_controller.handle_execution_event(
            {
                "type": "log",
                "run_id": "run_stale",
                "workspace_id": host.model.active_workspace.workspace_id,
                "level": "error",
                "message": "should be ignored",
            }
        )

        self.assertEqual(host.console_panel.logs, [])
        self.assertEqual(host.run_state.active_run_id, "run_live")

    def test_log_events_publish_only_for_the_active_run(self) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id
        host.run_state.engine_state_value = "running"
        _run_controller(host)

        for run_id, message in (
            ("run_live", "[stdout] tick_ui_0"),
            ("run_live", "[stderr] warn_ui_0"),
            ("run_stale", "[stdout] should_not_appear"),
        ):
            host.run_event_controller.handle_execution_event(
                {
                    "type": "log",
                    "run_id": run_id,
                    "workspace_id": workspace_id,
                    "node_id": "node_stream",
                    "level": "info",
                    "message": message,
                }
            )

        self.assertEqual(
            host.console_panel.logs,
            [
                ("info", "[stdout] tick_ui_0"),
                ("info", "[stderr] warn_ui_0"),
            ],
        )
        self.assertEqual(host.run_state.active_run_id, "run_live")
        self.assertEqual(host.run_state.active_run_workspace_id, workspace_id)
        self.assertEqual(host.run_state.engine_state_value, "running")

    def test_run_failed_event_focuses_node_logs_traceback_and_clears_active_run(
        self,
    ) -> None:
        host = _RunHostStub()
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = (
            host.model.active_workspace.workspace_id
        )
        host.run_state.engine_state_value = "running"
        _run_controller(host)

        host.run_event_controller.handle_execution_event(
            {
                "type": "run_failed",
                "run_id": "run_live",
                "workspace_id": host.model.active_workspace.workspace_id,
                "node_id": "node_1",
                "error": "boom",
                "traceback": "traceback: line 1",
            }
        )

        self.assertEqual(
            host.console_panel.logs[-2:],
            [("error", "boom"), ("error", "traceback: line 1")],
        )
        self.assertEqual(host._notifications, (0, 2))
        self.assertEqual(
            host.workspace_navigation_controller.focus_calls,
            [(host.model.active_workspace.workspace_id, "node_1")],
        )
        self.assertEqual(host.run_state.active_run_id, "")
        self.assertEqual(host.run_state.active_run_workspace_id, "")
        self.assertEqual(host.run_state.engine_state_value, "error")
        self.assert_run_controls(
            host,
            run_enabled=True,
            pause_enabled=False,
            stop_enabled=False,
            pause_label="Pause",
        )

    def test_protocol_error_is_logged(self) -> None:
        host = _RunHostStub()
        _run_controller(host)

        host.run_event_controller.handle_execution_event(
            {"type": "protocol_error", "error": "bad payload"}
        )

        self.assertEqual(host.console_panel.logs, [("error", "bad payload")])
        self.assertEqual(host._notifications, (0, 1))

    def test_node_settled_after_pause_preserves_paused_state_and_resume_action(
        self,
    ) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id
        host.run_state.engine_state_value = "running"
        run_controller = _run_controller(host)

        host.run_event_controller.handle_execution_event(
            {
                "type": "run_state",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "state": "paused",
                "transition": "pause",
            }
        )
        host.run_event_controller.handle_execution_event(
            {
                "type": "node_settled",
                "status": "completed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": "node_1",
            }
        )

        self.assertEqual(host.run_state.engine_state_value, "paused")
        self.assertEqual(host._engine_status, ("paused", "Paused"))
        self.assert_run_controls(
            host,
            run_enabled=False,
            pause_enabled=True,
            stop_enabled=True,
            pause_label="Resume",
        )

        run_controller.toggle_pause_resume()

        self.assertEqual(host.execution_client.resume_calls, ["run_live"])
        self.assertEqual(host._engine_status, ("running", "Resuming"))

    def test_persistent_node_elapsed_state_nonfatal_run_failed_clears_transient_execution_state_and_preserves_cache(
        self,
    ) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id
        host.run_state.node_execution_workspace_id = workspace_id
        host.run_state.running_node_ids.add("node_1")
        host.run_state.running_node_started_at_epoch_ms_by_node_id["node_1"] = 1000.0
        host.run_state.cached_node_elapsed_ms_by_workspace_id = {
            workspace_id: {"node_cached": 33.0}
        }
        host.run_state.node_execution_revision = 2
        _run_controller(host)

        host.run_event_controller.handle_execution_event(
            {
                "type": "run_failed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": "node_1",
                "error": "boom",
                "traceback": "traceback: line 1",
                "fatal": False,
            }
        )

        self.assertEqual(host.run_state.node_execution_workspace_id, "")
        self.assertEqual(host.run_state.running_node_ids, set())
        self.assertEqual(host.run_state.completed_node_ids, set())
        self.assertEqual(host.run_state.running_node_started_at_epoch_ms_by_node_id, {})
        self.assertEqual(
            host.run_state.cached_node_elapsed_ms_by_workspace_id,
            {workspace_id: {"node_cached": 33.0}},
        )
        self.assertEqual(host.run_state.node_execution_revision, 3)
        self.assertEqual(host.run_state.active_run_id, "")

    def test_run_completed_preserves_settled_state_while_stop_and_failure_clear_it(
        self,
    ) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        _run_controller(host)
        viewer = _ViewerSessionBridgeStub(host)
        host.viewer_session_bridge = viewer
        host.run_state.cached_node_elapsed_ms_by_workspace_id = {
            workspace_id: {"node_cached": 12.5},
            "ws_other": {"node_other": 8.0},
        }

        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id
        host.run_state.node_execution_workspace_id = workspace_id
        host.run_state.completed_node_ids.add("node_1")
        host.run_state.node_execution_revision = 1
        host.run_event_controller.handle_execution_event(
            {
                "type": "run_completed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
            }
        )

        self.assertEqual(host.run_state.node_execution_workspace_id, workspace_id)
        self.assertEqual(host.run_state.running_node_ids, set())
        self.assertEqual(host.run_state.completed_node_ids, {"node_1"})
        self.assertEqual(host.run_state.running_node_started_at_epoch_ms_by_node_id, {})
        self.assertEqual(
            host.run_state.cached_node_elapsed_ms_by_workspace_id,
            {
                workspace_id: {"node_cached": 12.5},
                "ws_other": {"node_other": 8.0},
            },
        )
        self.assertEqual(host.run_state.node_execution_revision, 1)

        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id
        host.run_state.node_execution_workspace_id = workspace_id
        host.run_state.completed_node_ids.add("node_2")
        host.run_state.running_node_started_at_epoch_ms_by_node_id["node_2"] = 2000.0
        host.run_event_controller.handle_execution_event(
            {
                "type": "run_stopped",
                "run_id": "run_live",
                "workspace_id": workspace_id,
            }
        )

        self.assertEqual(host.run_state.node_execution_workspace_id, "")
        self.assertEqual(host.run_state.running_node_ids, set())
        self.assertEqual(host.run_state.completed_node_ids, set())
        self.assertEqual(host.run_state.running_node_started_at_epoch_ms_by_node_id, {})
        self.assertEqual(
            host.run_state.cached_node_elapsed_ms_by_workspace_id,
            {
                workspace_id: {"node_cached": 12.5},
                "ws_other": {"node_other": 8.0},
            },
        )
        self.assertEqual(host.run_state.node_execution_revision, 2)

        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id
        host.run_state.node_execution_workspace_id = workspace_id
        host.run_state.running_node_ids.add("node_3")
        host.run_state.running_node_started_at_epoch_ms_by_node_id["node_3"] = 3000.0
        host.run_event_controller.handle_execution_event(
            {
                "type": "run_failed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": "node_3",
                "error": "fatal boom",
                "traceback": "traceback: line 9",
                "fatal": True,
            }
        )

        self.assertEqual(host.run_state.node_execution_workspace_id, "")
        self.assertEqual(host.run_state.running_node_ids, set())
        self.assertEqual(host.run_state.completed_node_ids, set())
        self.assertEqual(host.run_state.running_node_started_at_epoch_ms_by_node_id, {})
        self.assertEqual(host.run_state.node_execution_revision, 3)
        self.assertEqual(viewer.reset_reasons, ["worker_reset"])
        self.assertEqual(
            host.run_state.cached_node_elapsed_ms_by_workspace_id,
            {
                workspace_id: {"node_cached": 12.5},
                "ws_other": {"node_other": 8.0},
            },
        )

    def test_viewer_invalidation_is_adopted_only_for_active_run(self) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id
        _run_controller(host)
        viewer = _ViewerSessionBridgeStub(host)
        host.viewer_session_bridge = viewer
        event = {
            "type": "viewer_invalidation_committed",
            "workspace_id": workspace_id,
            "viewer_invalidation_node_ids": ["node_1"],
            "viewer_workspace_invalidation_epoch": 2,
            "viewer_node_invalidation_epochs": [("node_1", 3)],
            "viewer_epoch_snapshot_digest": "digest",
            "reason": "workspace_rerun",
        }

        host.run_event_controller.handle_execution_event(
            {**event, "run_id": "run_foreign"}
        )
        host.run_event_controller.handle_execution_event(
            {**event, "run_id": "run_live"}
        )

        self.assertEqual(len(viewer.adoptions), 1)
        self.assertEqual(viewer.adoptions[0]["run_id"], "run_live")
        self.assertEqual(viewer.adoptions[0]["node_ids"], ["node_1"])
        self.assertEqual(len(viewer.execution_events), 2)

    def test_event_handler_logs_its_own_exception_and_keeps_running(self) -> None:
        host = _RunHostStub()
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = (
            host.model.active_workspace.workspace_id
        )
        _run_controller(host)

        with (
            mock.patch.object(
                host.run_projection_controller,
                "mark_node_execution_running",
                side_effect=RuntimeError("projection exploded"),
            ),
            self.assertLogs(
                "ea_node_editor.ui.shell.controllers.run_event_controller",
                level="ERROR",
            ) as captured,
        ):
            result = host.run_event_controller.handle_execution_event(
                {
                    "type": "node_started",
                    "run_id": "run_live",
                    "workspace_id": host.model.active_workspace.workspace_id,
                    "node_id": "node_1",
                }
            )

        self.assertIsNone(result)
        self.assertIn("projection exploded", captured.output[0])

    def test_qt_queued_connection_defers_exactly_one_event_loop_hop(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        host = _RunHostStub()
        _run_controller(host)
        emitter = _ExecutionEventEmitter()
        emitter.execution_event.connect(
            host.run_event_controller.handle_execution_event,
            Qt.ConnectionType.QueuedConnection,
        )

        emitter.execution_event.emit(
            {"type": "protocol_error", "error": "queued payload"}
        )
        self.assertEqual(host.console_panel.logs, [])

        app.processEvents()

        self.assertEqual(host.console_panel.logs, [("error", "queued payload")])

    def test_node_settled_projects_run_state_before_single_viewer_delivery(
        self,
    ) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id
        _run_controller(host)
        viewer = _ViewerSessionBridgeStub(host)
        host.viewer_session_bridge = viewer

        host.run_event_controller.handle_execution_event(
            {
                "type": "node_settled",
                "status": "completed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": "node_1",
            }
        )

        self.assertEqual(len(viewer.execution_events), 1)
        self.assertEqual(viewer.completed_node_snapshots, [{"node_1"}])
        self.assertEqual(host.run_state.completed_node_ids, {"node_1"})

    def test_viewer_delivery_exception_is_logged_after_run_completion(self) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id
        host.run_state.engine_state_value = "running"
        _run_controller(host)
        viewer = _ViewerSessionBridgeStub(host)
        viewer.raise_on_delivery = True
        host.viewer_session_bridge = viewer

        with self.assertLogs(
            "ea_node_editor.ui.shell.controllers.run_event_controller",
            level="ERROR",
        ) as captured:
            host.run_event_controller.handle_execution_event(
                {
                    "type": "run_completed",
                    "run_id": "run_live",
                    "workspace_id": workspace_id,
                }
            )

        self.assertEqual(host.run_state.active_run_id, "")
        self.assertEqual(host.run_state.engine_state_value, "ready")
        self.assertEqual(len(viewer.execution_events), 1)
        self.assertIn("viewer projection exploded", captured.output[0])


if __name__ == "__main__":
    unittest.main()
