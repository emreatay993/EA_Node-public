# Purpose: Direct owner tests for shell run-state, output, availability, timing, warning, and failure projections.
# Map: feature_routes/run_controller_selected_workspace_state
# Tests: tests/test_run_projection_controller.py
from __future__ import annotations

import unittest
from unittest import mock

from ea_node_editor.execution.protocol_codec import event_to_dict
from ea_node_editor.execution.run_messages import (
    NodeSettledEvent,
    TriggerCaptureSettledEvent,
)
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.runtime_contracts import ImageValue
from ea_node_editor.runtime_contracts.settled_results import RootExecutionError
from ea_node_editor.runtime_contracts.solution_records import (
    NodeSolutionFact,
    SolutionDisposition,
    SolutionFreshness,
    SolutionResidency,
)
from ea_node_editor.runtime_contracts.value_refs import RuntimeHandleRef
from ea_node_editor.ui.shell.state import ShellRunState
from ea_node_editor.ui.support.solution_output_cache import (
    cache_accepted_output_record,
    retained_output_record,
    retained_output_records_by_node,
)
from tests.test_run_controller_unit import (
    _PNG_BYTES,
    _RunHostStub,
    _accepted_settlement,
    _run_controller,
    _script_result,
    _value_outputs,
    _value_result,
)


class RunProjectionControllerTests(unittest.TestCase):
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

    def test_failure_focus_is_direct_idempotent_projection_state(self) -> None:
        host = _RunHostStub()
        _run_controller(host)
        projection = host.run_projection_controller

        projection.set_run_failure_focus("workspace", "node", node_title="Failed Node")
        projection.set_run_failure_focus("workspace", "node", node_title="Failed Node")

        self.assertEqual(host.run_state.failed_workspace_id, "workspace")
        self.assertEqual(host.run_state.failed_node_id, "node")
        self.assertEqual(host.run_state.failed_node_title, "Failed Node")
        self.assertEqual(host.run_failure_changed.calls, 1)

        projection.clear_run_failure_focus()
        self.assertEqual(host.run_state.failed_workspace_id, "")
        self.assertEqual(host.run_state.failed_node_id, "")
        self.assertEqual(host.run_state.failed_node_title, "")
        self.assertEqual(host.run_failure_changed.calls, 2)

    def test_ui_solution_cache_is_bounded_and_run_count_is_monotonic(self) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        node = host.model.add_node(workspace_id, "core.constant", "Cached", 0, 0)
        run_controller = _run_controller(host)
        projection = host.run_projection_controller
        for run_id in ("run_1", "run_2", "run_3"):
            host.run_state.active_run_id = run_id
            host.run_state.active_run_workspace_id = workspace_id
            event = _accepted_settlement(
                host,
                workspace_id=workspace_id,
                node_id=node.node_id,
                run_id=run_id,
                outputs=_value_outputs(value=run_id),
            )
            projection.project_node_settled(
                event,
                workspace_id=workspace_id,
                node_id=node.node_id,
            )
        records = host.run_state.cached_node_output_records_by_workspace_id[
            workspace_id
        ][node.node_id]
        self.assertEqual(len(records), 2)
        self.assertEqual(
            host.run_state.node_output_run_counts_by_workspace_id[workspace_id][
                node.node_id
            ],
            3,
        )
        retained = retained_output_record(host.run_state, workspace_id, node.node_id)
        self.assertIsNotNone(retained)
        self.assertEqual(retained["run_id"], "run_3")

    def test_ui_solution_cache_global_eviction_and_metadata_only_fallback(self) -> None:
        state = ShellRunState()
        catalog = build_default_registry().data_types

        def cache(workspace_id: str, node_id: str, record_id: str) -> None:
            state.node_solution_facts_by_workspace_id[workspace_id] = {
                node_id: NodeSolutionFact(
                    project_id="project",
                    workspace_id=workspace_id,
                    node_id=node_id,
                    freshness=SolutionFreshness.CURRENT,
                    revision=1,
                    retained_record_id=record_id,
                    retained_solution_key="a" * 64,
                    residency=SolutionResidency.SESSION,
                    last_disposition=SolutionDisposition.RECOMPUTED,
                )
            }
            self.assertTrue(
                cache_accepted_output_record(
                    state,
                    workspace_id=workspace_id,
                    node_id=node_id,
                    event={
                        "record_id": record_id,
                        "solution_key": "a" * 64,
                        "result_digest": "b" * 64,
                        "disposition": "recomputed",
                        "run_id": record_id,
                    },
                    outputs=_value_outputs(value=record_id),
                    catalog=catalog,
                )
            )

        with mock.patch(
            "ea_node_editor.ui.support.solution_output_cache.MAX_RECORDS_GLOBAL", 2
        ):
            cache("ws_1", "node_1", "record_1")
            state.node_solution_facts_by_workspace_id["ws_1"] = {}
            cache("ws_2", "node_2", "record_2")
            state.node_solution_facts_by_workspace_id["ws_2"] = {}
            cache("ws_3", "node_3", "record_3")
        self.assertNotIn("ws_1", state.cached_node_output_records_by_workspace_id)
        self.assertEqual(
            set(state.cached_node_output_records_by_workspace_id), {"ws_2", "ws_3"}
        )

        metadata_state = ShellRunState()
        state = metadata_state
        with mock.patch(
            "ea_node_editor.ui.support.solution_output_cache.MAX_PAYLOAD_BYTES_GLOBAL",
            1,
        ):
            cache("ws_meta", "node_meta", "record_meta")
        metadata = metadata_state.cached_node_output_records_by_workspace_id["ws_meta"][
            "node_meta"
        ]["record_meta"]
        self.assertFalse(metadata["outputs_available"])
        self.assertEqual(metadata["outputs"], {})
        self.assertFalse(
            retained_output_records_by_node(metadata_state, "ws_meta")["node_meta"][
                "record_meta"
            ]["outputs_available"]
        )

    def test_solution_state_events_filter_project_and_monotonic_revision(self) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        node = host.model.add_node(workspace_id, "core.constant", "State", 0, 0)
        _run_controller(host)
        projection = host.run_projection_controller
        fact = NodeSolutionFact(
            project_id=host.model.project.project_id,
            workspace_id=workspace_id,
            node_id=node.node_id,
            freshness=SolutionFreshness.CURRENT,
            revision=1,
            retained_record_id="record_current",
            retained_solution_key="a" * 64,
            residency=SolutionResidency.SESSION,
            last_disposition=SolutionDisposition.RECOMPUTED,
        )
        host.execution_client.solution_facts_by_workspace[workspace_id] = (fact,)
        event = {
            "type": "solution_state_changed",
            "project_id": host.model.project.project_id,
            "workspace_id": workspace_id,
            "solution_revision": 1,
            "expired_node_ids": [],
            "removed_node_ids": [],
            "reason_code": "registry_generation_replaced",
        }
        projection.handle_solution_state_changed({**event, "project_id": "other"})
        self.assertNotIn(workspace_id, host.run_state.solution_revision_by_workspace_id)
        projection.handle_solution_state_changed(event)
        self.assertIs(
            host.run_state.node_solution_facts_by_workspace_id[workspace_id][
                node.node_id
            ].freshness,
            SolutionFreshness.CURRENT,
        )
        host.execution_client.solution_facts_by_workspace[workspace_id] = (
            NodeSolutionFact(
                project_id=fact.project_id,
                workspace_id=workspace_id,
                node_id=node.node_id,
                freshness=SolutionFreshness.EXPIRED,
                revision=2,
                retained_record_id=fact.retained_record_id,
                retained_solution_key=fact.retained_solution_key,
                residency=fact.residency,
                expiration_reason_code="late_duplicate",
                expiration_root_node_ids=(node.node_id,),
                last_disposition=fact.last_disposition,
            ),
        )
        projection.handle_solution_state_changed(
            {**event, "expired_node_ids": [node.node_id]}
        )
        self.assertIs(
            host.run_state.node_solution_facts_by_workspace_id[workspace_id][
                node.node_id
            ].freshness,
            SolutionFreshness.CURRENT,
        )

    def test_reset_before_settlement_keeps_current_cache_and_availability(self) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        node = host.model.add_node(workspace_id, "core.constant", "State", 0, 0)
        _run_controller(host)
        projection = host.run_projection_controller
        host.execution_client.solution_facts_by_workspace[workspace_id] = (
            NodeSolutionFact(
                project_id=host.model.project.project_id,
                workspace_id=workspace_id,
                node_id=node.node_id,
                freshness=SolutionFreshness.EXPIRED,
                revision=1,
                expiration_reason_code="runtime_generation_replaced",
                expiration_root_node_ids=(node.node_id,),
            ),
        )
        projection.handle_solution_state_changed(
            {
                "type": "solution_state_changed",
                "project_id": host.model.project.project_id,
                "workspace_id": workspace_id,
                "solution_revision": 1,
                "expired_node_ids": [node.node_id],
                "removed_node_ids": [],
                "reason_code": "runtime_generation_replaced",
            }
        )
        host.run_state.active_run_id = "run_after_reset"
        host.run_state.active_run_workspace_id = workspace_id
        settled = _accepted_settlement(
            host,
            workspace_id=workspace_id,
            node_id=node.node_id,
            run_id="run_after_reset",
            outputs=_value_outputs(value="current"),
        )

        with mock.patch(
            "ea_node_editor.ui.shell.controllers.run_projection_controller.observe_node_outputs"
        ) as observe:
            projection.project_node_settled(
                settled,
                workspace_id=workspace_id,
                node_id=node.node_id,
            )

        observe.assert_called_once()
        self.assertIn(node.node_id, host.run_state.completed_node_ids)
        self.assertIn(
            node.node_id,
            host.run_state.cached_node_output_records_by_workspace_id[workspace_id],
        )

    def test_semantic_runtime_carrier_settlements_use_active_catalog(self) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        signal = host.model.add_node(workspace_id, "plot.signal", "Signal Plot", 0, 0)
        trigger = host.model.add_node(workspace_id, "core.trigger", "Trigger", 200, 0)
        run_controller = _run_controller(host)
        projection = host.run_projection_controller
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id

        projection.mark_node_execution_running(
            workspace_id,
            signal.node_id,
            started_at_epoch_ms=1.0,
        )
        image_result = _value_result(ImageValue.from_png(_PNG_BYTES))
        settled_event = event_to_dict(
            NodeSettledEvent(
                run_id="run_live",
                workspace_id=workspace_id,
                node_id=signal.node_id,
                elapsed_ms=25.0,
                outputs={"image": image_result},
            ),
            catalog=host.registry.data_types,
        )
        projection.project_node_settled(
            settled_event,
            workspace_id=workspace_id,
            node_id=signal.node_id,
        )

        self.assertNotIn(signal.node_id, host.run_state.running_node_ids)
        self.assertIn(signal.node_id, host.run_state.completed_node_ids)
        self.assertEqual(
            host.run_state.cached_node_elapsed_ms_by_workspace_id[workspace_id][
                signal.node_id
            ],
            25.0,
        )

        host.run_event_controller.handle_execution_event(
            event_to_dict(
                TriggerCaptureSettledEvent(
                    run_id="run_live",
                    workspace_id=workspace_id,
                    trigger_node_id=trigger.node_id,
                    result=image_result,
                ),
                catalog=host.registry.data_types,
            )
        )
        self.assertEqual(
            host.run_state.latest_trigger_inputs_by_workspace_id[workspace_id][
                trigger.node_id
            ],
            image_result,
        )

    def test_node_settled_caches_typed_outputs_by_workspace_node_and_run(self) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        script = host.model.add_node(
            workspace_id,
            "core.python_script",
            "Script",
            0,
            0,
            properties={"script": _script_result("'fresh'")},
        )
        _run_controller(host)
        projection = host.run_projection_controller

        with mock.patch.object(
            projection,
            "_current_epoch_ms",
            side_effect=[1000.0, 2000.0],
        ):
            for run_id, result in (("run_1", "first"), ("run_2", "second")):
                host.run_state.active_run_id = run_id
                host.run_state.active_run_workspace_id = workspace_id
                event = _accepted_settlement(
                    host,
                    workspace_id=workspace_id,
                    node_id=script.node_id,
                    run_id=run_id,
                    outputs=_value_outputs(result=result),
                )
                projection.project_node_settled(
                    event,
                    workspace_id=workspace_id,
                    node_id=script.node_id,
                )

        records = host.run_state.cached_node_output_records_by_workspace_id[
            workspace_id
        ][script.node_id]
        self.assertEqual(len(records), 2)
        self.assertEqual(
            {
                next(iter(record["outputs"].values())).value.branches[0][1][0]
                for record in records.values()
            },
            {"first", "second"},
        )
        self.assertEqual(
            host.run_state.node_output_run_counts_by_workspace_id[workspace_id][
                script.node_id
            ],
            2,
        )

    def test_invalidated_accepted_settlement_cannot_restore_cache_or_availability(
        self,
    ) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        node = host.model.add_node(workspace_id, "core.constant", "Constant", 0, 0)
        _run_controller(host)
        projection = host.run_projection_controller
        event = _accepted_settlement(
            host,
            workspace_id=workspace_id,
            node_id=node.node_id,
            run_id="run_late",
            outputs=_value_outputs(value="late"),
        )
        accepted = host.execution_client.solution_facts_by_workspace[workspace_id][0]
        host.execution_client.solution_facts_by_workspace[workspace_id] = (
            NodeSolutionFact(
                project_id=accepted.project_id,
                workspace_id=accepted.workspace_id,
                node_id=accepted.node_id,
                freshness=SolutionFreshness.EXPIRED,
                revision=accepted.revision + 1,
                retained_record_id=accepted.retained_record_id,
                retained_solution_key=accepted.retained_solution_key,
                residency=accepted.residency,
                expiration_reason_code="graph_changed",
                expiration_root_node_ids=(node.node_id,),
                last_disposition=accepted.last_disposition,
            ),
        )

        with mock.patch(
            "ea_node_editor.ui.shell.controllers.run_projection_controller.observe_node_outputs"
        ) as observe:
            projection.project_node_settled(
                event,
                workspace_id=workspace_id,
                node_id=node.node_id,
            )

        observe.assert_not_called()
        self.assertNotIn(
            workspace_id,
            host.run_state.cached_node_output_records_by_workspace_id,
        )

    def test_unenriched_settlement_cannot_publish_output_cache_or_availability(
        self,
    ) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        node = host.model.add_node(workspace_id, "core.constant", "Constant", 0, 0)
        _run_controller(host)
        projection = host.run_projection_controller
        event = {
            "type": "node_settled",
            "status": "completed",
            "run_id": "run_raw",
            "workspace_id": workspace_id,
            "node_id": node.node_id,
            "outputs": _value_outputs(value="raw"),
        }

        with (
            mock.patch(
                "ea_node_editor.ui.shell.controllers.run_projection_controller.observe_node_outputs"
            ) as observe,
            mock.patch(
                "ea_node_editor.ui.shell.controllers.run_projection_controller.cache_accepted_output_record"
            ) as cache,
        ):
            projection.project_node_settled(
                event,
                workspace_id=workspace_id,
                node_id=node.node_id,
            )

        observe.assert_not_called()
        cache.assert_not_called()
        self.assertNotIn(
            workspace_id,
            host.run_state.cached_node_output_records_by_workspace_id,
        )

    def test_update_run_actions_idle_selected_workspace_enables_only_run(self) -> None:
        host = _RunHostStub()
        controller = _run_controller(host)  # type: ignore[arg-type]

        host.run_projection_controller.update_run_actions()

        self.assert_run_controls(
            host,
            run_enabled=True,
            pause_enabled=False,
            stop_enabled=False,
            pause_label="Pause",
        )
        self.assertEqual(host.run_controls_changed.calls, 1)

    def test_update_run_actions_selected_workspace_owner_running_disables_run_and_enables_pause_stop(
        self,
    ) -> None:
        host = _RunHostStub()
        controller = _run_controller(host)  # type: ignore[arg-type]
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = (
            host.model.active_workspace.workspace_id
        )
        host.run_state.engine_state_value = "running"

        host.run_projection_controller.update_run_actions()

        self.assert_run_controls(
            host,
            run_enabled=False,
            pause_enabled=True,
            stop_enabled=True,
            pause_label="Pause",
        )
        self.assertEqual(host.run_controls_changed.calls, 1)

    def test_update_run_actions_selected_workspace_owner_paused_uses_resume_label(
        self,
    ) -> None:
        host = _RunHostStub()
        controller = _run_controller(host)  # type: ignore[arg-type]
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = (
            host.model.active_workspace.workspace_id
        )
        host.run_state.engine_state_value = "paused"

        host.run_projection_controller.update_run_actions()

        self.assert_run_controls(
            host,
            run_enabled=False,
            pause_enabled=True,
            stop_enabled=True,
            pause_label="Resume",
        )
        self.assertEqual(host.run_controls_changed.calls, 1)

    def test_update_run_actions_non_owning_selected_workspace_disables_pause_and_stop(
        self,
    ) -> None:
        host = _RunHostStub()
        controller = _run_controller(host)  # type: ignore[arg-type]
        owning_workspace_id = host.model.active_workspace.workspace_id
        other_workspace = host.model.create_workspace(name="Second Workspace")
        host.workspace_manager.set_active_workspace(other_workspace.workspace_id)
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = owning_workspace_id
        host.run_state.engine_state_value = "running"

        host.run_projection_controller.update_run_actions()

        self.assert_run_controls(
            host,
            run_enabled=True,
            pause_enabled=False,
            stop_enabled=False,
            pause_label="Pause",
        )
        self.assertEqual(host.run_controls_changed.calls, 1)

    def test_node_execution_bridge_run_events_project_running_and_completed_nodes(
        self,
    ) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id
        host.run_state.node_execution_workspace_id = workspace_id
        host.run_state.running_node_ids.add("node_stale")
        host.run_state.failed_workspace_id = workspace_id
        host.run_state.failed_node_id = "node_failed"
        host.run_state.failed_node_title = "Failed Node"
        host.run_state.node_execution_revision = 4
        controller = _run_controller(host)  # type: ignore[arg-type]

        host.run_event_controller.handle_execution_event(
            {
                "type": "run_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
            }
        )

        self.assertEqual(host.run_failure_changed.calls, 1)
        self.assertEqual(host.run_state.failed_workspace_id, "")
        self.assertEqual(host.run_state.failed_node_id, "")
        self.assertEqual(host.run_state.failed_node_title, "")
        self.assertEqual(host.run_state.running_node_ids, set())
        self.assertEqual(host.run_state.completed_node_ids, set())
        self.assertEqual(host.run_state.node_execution_revision, 5)

        host.run_event_controller.handle_execution_event(
            {
                "type": "node_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": "node_1",
            }
        )

        self.assertEqual(host.run_state.node_execution_workspace_id, workspace_id)
        self.assertEqual(host.run_state.running_node_ids, {"node_1"})
        self.assertEqual(host.run_state.completed_node_ids, set())
        self.assertEqual(host.run_state.node_execution_revision, 6)

        host.run_event_controller.handle_execution_event(
            {
                "type": "node_settled",
                "status": "completed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": "node_1",
            }
        )

        self.assertEqual(host.run_state.running_node_ids, set())
        self.assertEqual(host.run_state.completed_node_ids, {"node_1"})
        self.assertEqual(host.run_state.node_execution_revision, 7)
        self.assertEqual(host._engine_status, ("running", "Running"))

    def test_node_settled_projects_empty_failed_blocked_and_original_root_errors(
        self,
    ) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        node = host.model.add_node(workspace_id, "core.logger", "Logger", 0, 0)
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id
        controller = _run_controller(host)  # type: ignore[arg-type]
        root_error = RootExecutionError(
            node_id="node_root",
            error="root failure",
            traceback="root trace",
        )

        host.run_event_controller.handle_execution_event(
            {
                "type": "node_settled",
                "status": "failed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": node.node_id,
                "errors": (root_error,),
            }
        )
        self.assertEqual(host.run_state.failed_node_ids, {node.node_id})
        self.assertEqual(
            host.run_state.root_errors_by_node_id[node.node_id], (root_error,)
        )
        self.assertEqual(host.run_state.completed_node_ids, set())
        self.assertEqual(
            host.workspace_navigation_controller.focus_calls,
            [(workspace_id, node.node_id)],
        )

        host.run_event_controller.handle_execution_event(
            {
                "type": "node_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": node.node_id,
            }
        )
        host.run_event_controller.handle_execution_event(
            {
                "type": "node_settled",
                "status": "empty",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": node.node_id,
            }
        )
        self.assertEqual(host.run_state.empty_node_ids, {node.node_id})
        self.assertNotIn(node.node_id, host.run_state.root_errors_by_node_id)
        self.assertEqual(
            host.workspace_navigation_controller.focus_calls,
            [(workspace_id, node.node_id)],
        )

        host.run_event_controller.handle_execution_event(
            {
                "type": "node_settled",
                "status": "blocked",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": node.node_id,
                "errors": (root_error,),
            }
        )
        self.assertEqual(host.run_state.blocked_node_ids, {node.node_id})
        self.assertEqual(
            host.run_state.root_errors_by_node_id[node.node_id], (root_error,)
        )
        self.assertEqual(host.run_state.empty_node_ids, set())
        self.assertEqual(
            host.workspace_navigation_controller.focus_calls,
            [(workspace_id, node.node_id)],
        )

    def test_runtime_warning_messages_persist_until_node_rerun_or_graph_invalidation(
        self,
    ) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        node = host.model.add_node(
            workspace_id,
            "core.python_script",
            "Script",
            0,
            0,
            properties={"script": _script_result("1")},
        )
        controller = _run_controller(host)  # type: ignore[arg-type]
        host.run_state.active_run_id = "run_warning"
        host.run_state.active_run_workspace_id = workspace_id

        host.run_event_controller.handle_execution_event(
            {
                "type": "node_settled",
                "status": "completed",
                "run_id": "run_warning",
                "workspace_id": workspace_id,
                "node_id": node.node_id,
                "warnings": [
                    "  Mesh quality was reduced.  ",
                    "Mesh quality was reduced.",
                ],
            }
        )
        self.assertEqual(
            host.run_state.runtime_warning_messages_by_workspace_id,
            {workspace_id: {node.node_id: ("Mesh quality was reduced.",)}},
        )

        host.run_event_controller.handle_execution_event(
            {
                "type": "run_completed",
                "run_id": "run_warning",
                "workspace_id": workspace_id,
            }
        )
        self.assertIn(
            node.node_id,
            host.run_state.runtime_warning_messages_by_workspace_id[workspace_id],
        )

        host.run_projection_controller.mark_node_execution_running(
            workspace_id, node.node_id
        )
        self.assertNotIn(
            workspace_id, host.run_state.runtime_warning_messages_by_workspace_id
        )

        host.run_projection_controller.mark_node_execution_settled(
            workspace_id,
            node.node_id,
            status="completed",
            warning=True,
            warning_messages=("Review the result.",),
        )
        before_snapshot = host.model.active_workspace.capture_snapshot()
        host.model.set_node_property(
            workspace_id, node.node_id, "script", _script_result("2")
        )
        after_snapshot = host.model.active_workspace.capture_snapshot()
        controller.invalidate_solution_for_history_action(
            workspace_id,
            "edit-node-property",
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )
        self.assertNotIn(
            workspace_id, host.run_state.runtime_warning_messages_by_workspace_id
        )

        host.run_state.active_run_id = "run_invalidated"
        host.run_state.active_run_workspace_id = workspace_id
        host.run_projection_controller.mark_node_execution_running(
            workspace_id, node.node_id
        )
        before_snapshot = host.model.active_workspace.capture_snapshot()
        host.model.set_node_property(
            workspace_id, node.node_id, "script", _script_result("3")
        )
        after_snapshot = host.model.active_workspace.capture_snapshot()
        controller.invalidate_solution_for_history_action(
            workspace_id,
            "edit-node-property",
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )
        host.run_event_controller.handle_execution_event(
            {
                "type": "node_settled",
                "status": "completed",
                "run_id": "run_invalidated",
                "workspace_id": workspace_id,
                "node_id": node.node_id,
                "warnings": ("Stale warning must not survive.",),
            }
        )
        self.assertNotIn(
            workspace_id, host.run_state.runtime_warning_messages_by_workspace_id
        )
        self.assertNotIn(node.node_id, host.run_state.warning_node_ids)

    def test_persistent_node_elapsed_state_projects_fallback_started_at_and_cached_elapsed_by_workspace(
        self,
    ) -> None:
        host = _RunHostStub()
        workspace_id = host.model.active_workspace.workspace_id
        host.run_state.active_run_id = "run_live"
        host.run_state.active_run_workspace_id = workspace_id
        host.run_state.node_execution_workspace_id = workspace_id
        host.run_state.running_node_ids.add("node_stale")
        host.run_state.running_node_started_at_epoch_ms_by_node_id["node_stale"] = 500.0
        host.run_state.cached_node_elapsed_ms_by_workspace_id = {
            "ws_previous": {
                "node_cached": 12.5,
            }
        }
        host.run_state.node_execution_revision = 4
        controller = _run_controller(host)  # type: ignore[arg-type]

        host.run_event_controller.handle_execution_event(
            {
                "type": "run_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
            }
        )

        self.assertEqual(host.run_state.running_node_ids, set())
        self.assertEqual(host.run_state.completed_node_ids, set())
        self.assertEqual(host.run_state.running_node_started_at_epoch_ms_by_node_id, {})
        self.assertEqual(
            host.run_state.cached_node_elapsed_ms_by_workspace_id,
            {"ws_previous": {"node_cached": 12.5}},
        )

        with mock.patch(
            "ea_node_editor.ui.shell.controllers.run_projection_controller.time.time",
            return_value=100.0,
        ):
            host.run_event_controller.handle_execution_event(
                {
                    "type": "node_started",
                    "run_id": "run_live",
                    "workspace_id": workspace_id,
                    "node_id": "node_1",
                    "started_at_epoch_ms": 0.0,
                }
            )

        self.assertEqual(
            host.run_state.running_node_started_at_epoch_ms_by_node_id,
            {"node_1": 100000.0},
        )

        with mock.patch(
            "ea_node_editor.ui.shell.controllers.run_projection_controller.time.time",
            return_value=100.04525,
        ):
            host.run_event_controller.handle_execution_event(
                {
                    "type": "node_settled",
                    "status": "completed",
                    "run_id": "run_live",
                    "workspace_id": workspace_id,
                    "node_id": "node_1",
                    "elapsed_ms": 0.0,
                }
            )

        self.assertEqual(host.run_state.running_node_ids, set())
        self.assertEqual(host.run_state.completed_node_ids, {"node_1"})
        self.assertEqual(host.run_state.running_node_started_at_epoch_ms_by_node_id, {})
        self.assertEqual(
            host.run_state.cached_node_elapsed_ms_by_workspace_id["ws_previous"],
            {"node_cached": 12.5},
        )
        self.assertAlmostEqual(
            host.run_state.cached_node_elapsed_ms_by_workspace_id[workspace_id][
                "node_1"
            ],
            45.25,
            places=2,
        )

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
            host.run_state.cached_node_elapsed_ms_by_workspace_id["ws_previous"],
            {"node_cached": 12.5},
        )
        self.assertAlmostEqual(
            host.run_state.cached_node_elapsed_ms_by_workspace_id[workspace_id][
                "node_1"
            ],
            45.25,
            places=2,
        )
