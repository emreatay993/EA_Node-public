from __future__ import annotations

import json
import re
import sys
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from PyQt6.QtCore import QMetaObject, QObject
from PyQt6.QtQuick import QQuickItem
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMessageBox

from ea_node_editor.execution.compiler import compile_runtime_snapshot
from ea_node_editor.execution.execution_plan import ExecutionPlan
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.execution.prepared_execution import InvalidationResult
from ea_node_editor.execution.viewer_messages import (
    CloseViewerSessionCommand,
    OpenViewerSessionCommand,
    ViewerSessionFailedEvent,
    viewer_epoch_snapshot_digest,
)
from ea_node_editor.execution.viewer_backend_engineering import (
    ENGINEERING_VIEWER_BACKEND_ID,
)
from ea_node_editor.runtime_contracts import DataTree
from ea_node_editor.runtime_contracts.solution_records import (
    NodeSolutionFact,
    SolutionDisposition,
    SolutionFreshness,
    SolutionResidency,
)
from ea_node_editor.ui.icon_registry import icon_path
from ea_node_editor.ui_qml.shell_inspector_bridge import ShellInspectorBridge
from ea_node_editor.ui_qml.shell_library_bridge import ShellLibraryBridge
from ea_node_editor.ui_qml.shell_workspace_bridge import ShellWorkspaceBridge
from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge
from tests.main_window_shell.base import MainWindowShellTestBase
from tests.qt_wait import wait_for_condition_or_raise
from tests.shell_isolation_runtime import format_child_output
from tests.shell_isolation_runtime import run_shell_isolation_target
from tests.shell_isolation_runtime import ShellIsolationTarget
from tests.shell_isolation_runtime import ShellIsolationTargetTimeout
from tests.typed_handle_support import core_worker_services

_SHELL_TEST_RUNNER = (
    "import sys, unittest; "
    "target = sys.argv[1]; "
    "suite = unittest.defaultTestLoader.loadTestsFromName(target); "
    "result = unittest.TextTestRunner(verbosity=2).run(suite); "
    "sys.exit(0 if result.wasSuccessful() else 1)"
)


def _value_outputs(**values: object) -> dict[str, SettledPortResult]:
    return {
        key: SettledPortResult(status="value", value=DataTree.from_item(value))
        for key, value in values.items()
    }


class _ViewerExecutionClientStub:
    def __init__(self, registry) -> None:  # noqa: ANN001
        self.registry = registry
        self.next_run_id = "run_live"
        self.start_calls: list[dict] = []
        self.pause_calls: list[str] = []
        self.resume_calls: list[str] = []
        self.stop_calls: list[str] = []
        self.open_calls: list[dict] = []
        self.update_calls: list[dict] = []
        self.close_calls: list[dict] = []
        self.invalidate_viewer_calls: list[tuple[str, tuple[str, ...] | None]] = []
        self.solution_facts_by_workspace: dict[str, tuple[NodeSolutionFact, ...]] = {}
        self.invalidate_calls: list[InvalidationResult] = []
        self._request_counter = 0
        self._solution_revisions: dict[str, int] = {}

    def _next_request_id(self, prefix: str) -> str:
        self._request_counter += 1
        return f"{prefix}_{self._request_counter}"

    def prepare_execution(self, request):  # noqa: ANN001, ANN201
        plan = ExecutionPlan(
            request.runtime_snapshot.workspace(request.workspace_id), self.registry
        )
        facts = {
            fact.node_id: fact
            for fact in self.solution_facts_by_workspace.get(request.workspace_id, ())
        }
        requested = set(request.target_node_ids)
        recompute_node_ids = tuple(
            node_id
            for node_id in plan.execution_order
            if node_id in requested
            and (
                node_id not in facts
                or facts[node_id].freshness is not SolutionFreshness.CURRENT
            )
        )
        viewer_invalidation_node_ids = tuple(
            node_id
            for node_id in recompute_node_ids
            if plan.node_specs[node_id].surface_family == "viewer"
        )
        return SimpleNamespace(
            request=request,
            recompute_node_ids=recompute_node_ids,
            viewer_invalidation_node_ids=viewer_invalidation_node_ids,
        )

    def dispatch_prepared(self, prepared) -> str:  # noqa: ANN001
        request = prepared.request
        trigger = dict(request.trigger)
        trigger["runtime_snapshot"] = request.runtime_snapshot
        self.start_calls.append(
            {
                "project_path": str(request.project_path),
                "workspace_id": request.workspace_id,
                "trigger": trigger,
                "execution_backend": request.execution_backend,
                "target_node_ids": tuple(request.target_node_ids),
                "trigger_publications": dict(request.trigger_publications),
                "trigger_captures": dict(request.trigger_captures),
                "clicked_trigger_node_id": request.clicked_trigger_node_id,
                "recompute_node_ids": tuple(prepared.recompute_node_ids),
                "viewer_invalidation_node_ids": tuple(
                    prepared.viewer_invalidation_node_ids
                ),
            }
        )
        return self.next_run_id

    def solution_facts(self, project_id: str, workspace_id: str):  # noqa: ANN201
        del project_id
        return self.solution_facts_by_workspace.get(workspace_id, ())

    def invalidate_solution(
        self,
        project_id: str,
        workspace_id: str,
        runtime_snapshot,
        changed_root_node_ids,
        reason_code: str,
    ) -> InvalidationResult:
        workspace = compile_runtime_snapshot(
            runtime_snapshot,
            workspace_id=workspace_id,
            registry=self.registry,
        )
        plan = ExecutionPlan.for_invalidation(workspace, self.registry)
        closure = plan.affected_downstream_closure(tuple(changed_root_node_ids))
        active_ids = {
            node_id
            for node_id in plan.execution_order
            if plan.node_specs[node_id].runtime_behavior == "active"
        }
        removed = tuple(
            fact.node_id
            for fact in self.solution_facts_by_workspace.get(workspace_id, ())
            if fact.node_id not in active_ids
        )
        self._solution_revisions[workspace_id] = (
            self._solution_revisions.get(workspace_id, 0) + 1
        )
        result = InvalidationResult(
            project_id=project_id,
            workspace_id=workspace_id,
            solution_revision=self._solution_revisions[workspace_id],
            changed_root_node_ids=tuple(changed_root_node_ids),
            expired_node_ids=tuple(closure),
            removed_node_ids=removed,
            reason_code=reason_code,
        )
        updated_facts = []
        for fact in self.solution_facts_by_workspace.get(workspace_id, ()):
            if fact.node_id in removed:
                continue
            if fact.node_id in closure:
                fact = NodeSolutionFact(
                    project_id=fact.project_id,
                    workspace_id=fact.workspace_id,
                    node_id=fact.node_id,
                    freshness=SolutionFreshness.EXPIRED,
                    revision=fact.revision + 1,
                    retained_record_id=fact.retained_record_id,
                    retained_solution_key=fact.retained_solution_key,
                    residency=fact.residency,
                    expiration_reason_code=reason_code,
                    expiration_root_node_ids=closure[fact.node_id],
                    last_disposition=fact.last_disposition,
                )
            updated_facts.append(fact)
        self.solution_facts_by_workspace[workspace_id] = tuple(updated_facts)
        self.invalidate_calls.append(result)
        return result

    def pause_run(self, run_id: str) -> None:
        self.pause_calls.append(str(run_id))

    def resume_run(self, run_id: str) -> None:
        self.resume_calls.append(str(run_id))

    def stop_run(self, run_id: str) -> None:
        self.stop_calls.append(str(run_id))

    def invalidate_viewer_requests(self, workspace_id: str, node_ids) -> int:
        normalized = None if node_ids is None else tuple(dict.fromkeys(node_ids))
        self.invalidate_viewer_calls.append((workspace_id, normalized))
        return 0

    def open_viewer_session(
        self,
        *,
        workspace_id: str,
        node_id: str,
        session_id: str = "",
        backend_id: str = "",
        data_refs: dict | None = None,
        camera_state: dict | None = None,
        playback_state: dict | None = None,
        summary: dict | None = None,
        options: dict | None = None,
        **extra,
    ) -> str:
        request_id = self._next_request_id("open")
        self.open_calls.append(
            {
                "request_id": request_id,
                "workspace_id": workspace_id,
                "node_id": node_id,
                "session_id": session_id,
                "backend_id": backend_id,
                "data_refs": dict(data_refs or {}),
                "camera_state": dict(camera_state or {}),
                "playback_state": dict(playback_state or {}),
                "summary": dict(summary or {}),
                "options": dict(options or {}),
                "extra": dict(extra),
            }
        )
        return request_id

    def update_viewer_session(
        self,
        *,
        workspace_id: str,
        node_id: str,
        session_id: str,
        backend_id: str = "",
        camera_state: dict | None = None,
        playback_state: dict | None = None,
        summary: dict | None = None,
        options: dict | None = None,
        **extra,
    ) -> str:
        request_id = self._next_request_id("update")
        self.update_calls.append(
            {
                "request_id": request_id,
                "workspace_id": workspace_id,
                "node_id": node_id,
                "session_id": session_id,
                "backend_id": backend_id,
                "camera_state": dict(camera_state or {}),
                "playback_state": dict(playback_state or {}),
                "summary": dict(summary or {}),
                "options": dict(options or {}),
                "extra": dict(extra),
            }
        )
        return request_id

    def close_viewer_session(
        self,
        *,
        workspace_id: str,
        node_id: str,
        session_id: str,
        options: dict | None = None,
        **extra,
    ) -> str:
        request_id = self._next_request_id("close")
        self.close_calls.append(
            {
                "request_id": request_id,
                "workspace_id": workspace_id,
                "node_id": node_id,
                "session_id": session_id,
                "options": dict(options or {}),
                "extra": dict(extra),
            }
        )
        return request_id

    def shutdown(self) -> None:
        return None


class _ViewerHostServiceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def suspend_sync(self, *, reason: str = "") -> None:
        self.calls.append(("suspend_sync", str(reason)))

    def resume_sync(self) -> None:
        self.calls.append(("resume_sync", ""))

    def reset(self, *, reason: str = "") -> None:
        self.calls.append(("reset", str(reason)))

    def sync(self) -> None:
        self.calls.append(("sync", ""))


def _viewer_opened_event(
    *,
    request_id: str,
    workspace_id: str,
    node_id: str,
    session_id: str,
    **overrides,
) -> dict:
    payload = {
        "type": "viewer_session_opened",
        "request_id": request_id,
        "workspace_id": workspace_id,
        "node_id": node_id,
        "session_id": session_id,
        "data_refs": {},
        "summary": {
            "cache_state": "proxy_ready",
            "result_name": "displacement",
        },
        "options": {
            "session_state": "open",
            "cache_state": "proxy_ready",
            "playback_state": "paused",
            "live_mode": "proxy",
        },
    }
    payload.update(overrides)
    return payload


def _graph_node_card(graph_canvas: QObject, node_id: str) -> QObject | None:
    match: QObject | None = None

    def _walk(item: QObject | None) -> None:
        nonlocal match
        if item is None or match is not None:
            return
        if item.objectName() == "graphNodeCard":
            node_data = item.property("nodeData")
            if isinstance(node_data, dict) and str(node_data.get("node_id", "")) == str(node_id):
                match = item
                return
        child_items = getattr(item, "childItems", None)
        if callable(child_items):
            for child in child_items():
                _walk(child)

    _walk(graph_canvas)
    return match


def _graph_node_child(graph_canvas: QObject, node_id: str, object_name: str) -> QObject | None:
    node_card = _graph_node_card(graph_canvas, node_id)
    if node_card is None:
        return None
    return node_card.findChild(QObject, object_name)


def _graph_node_children(graph_canvas: QObject, node_id: str, object_name: str) -> list[QObject]:
    node_card = _graph_node_card(graph_canvas, node_id)
    if node_card is None:
        return []

    matches: list[QObject] = []

    def _walk(item: QObject | None) -> None:
        if item is None:
            return
        if item.objectName() == object_name:
            matches.append(item)
        child_items = getattr(item, "childItems", None)
        if callable(child_items):
            for child in child_items():
                _walk(child)

    _walk(node_card)
    return matches


def _named_qquick_item(root: QObject, object_name: str) -> QQuickItem | None:
    match: QQuickItem | None = None

    def _walk(item: QObject | None) -> None:
        nonlocal match
        if item is None or match is not None or not isinstance(item, QQuickItem):
            return
        if item.objectName() == object_name:
            match = item
            return
        for child in item.childItems():
            _walk(child)

    _walk(root)
    return match


class ShellRunControllerTests(MainWindowShellTestBase):
    def test_disconnected_toggle_auto_run_preserves_current_viewer_until_separate_same_node_invalidation(
        self,
    ) -> None:
        execution_client = _ViewerExecutionClientStub(self.window.registry)
        self.window.execution_client = execution_client
        self.window.run_controller.set_auto_run_enabled(False)
        bridge = self.window.viewer_session_bridge
        workspace_id = self.window.workspace_manager.active_workspace_id()
        project_id = self.window.model.project.project_id

        cad_id = self.window.scene.add_node_from_type(
            "engineering.cad_import", x=40.0, y=40.0
        )
        viewer_id = self.window.scene.add_node_from_type(
            "model.viewer", x=300.0, y=40.0
        )
        toggle_id = self.window.scene.add_node_from_type(
            "data.boolean_toggle", x=40.0, y=260.0
        )
        self.window.scene.add_edge(cad_id, "scene", viewer_id, "scene_1")
        self.app.processEvents()

        viewer_fact = NodeSolutionFact(
            project_id=project_id,
            workspace_id=workspace_id,
            node_id=viewer_id,
            freshness=SolutionFreshness.CURRENT,
            revision=0,
            retained_record_id="record_viewer_current",
            retained_solution_key="a" * 64,
            residency=SolutionResidency.SESSION,
            last_disposition=SolutionDisposition.RECOMPUTED,
        )
        toggle_fact = NodeSolutionFact(
            project_id=project_id,
            workspace_id=workspace_id,
            node_id=toggle_id,
            freshness=SolutionFreshness.CURRENT,
            revision=0,
            retained_record_id="record_toggle_current",
            retained_solution_key="b" * 64,
            residency=SolutionResidency.SESSION,
            last_disposition=SolutionDisposition.RECOMPUTED,
        )
        execution_client.solution_facts_by_workspace[workspace_id] = (
            viewer_fact,
            toggle_fact,
        )
        self.window.execution_event.emit(
            {
                "type": "solution_state_changed",
                "project_id": project_id,
                "workspace_id": workspace_id,
                "solution_revision": 0,
                "expired_node_ids": [],
                "removed_node_ids": [],
                "reason_code": "settled",
            }
        )

        session_id = "viewer_session_disconnected_acceptance"
        session_payload = {
            "scene": {"kind": "prepared_scene", "handle_id": "scene_current"}
        }
        transport = {
            "kind": "engineering_scene",
            "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
            "revision": 7,
        }
        summary = {
            "cache_state": "live_ready",
            "result_name": "prepared_scene",
            "preview": {"source": "image://viewer-preview/current"},
        }
        session_id = bridge.open(
            viewer_id,
            {
                "session_id": session_id,
                "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
                "data_refs": session_payload,
                "summary": summary,
            },
        )
        open_call = execution_client.open_calls[-1]
        self.window.execution_event.emit(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id=workspace_id,
                node_id=viewer_id,
                session_id=session_id,
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                data_refs=session_payload,
                transport=transport,
                transport_revision=7,
                live_open_status="ready",
                summary=summary,
                options={"session_state": "open", "live_mode": "full"},
            )
        )
        self.app.processEvents()

        worker_services = core_worker_services()
        service = worker_services.viewer_session_service
        service.install_workspace_context(workspace_id=workspace_id)
        service_opened = service.open_session(
            OpenViewerSessionCommand(
                request_id="service_open_current",
                workspace_id=workspace_id,
                node_id=viewer_id,
                session_id=session_id,
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                data_refs=session_payload,
                transport=transport,
                transport_revision=7,
                live_open_status="ready",
                summary=summary,
                options={"session_state": "open", "live_mode": "full"},
            )
        )
        self.assertEqual(service_opened.live_open_status, "ready")

        bridge_before = bridge.session_state(viewer_id)
        bridge_bytes = json.dumps(
            bridge_before, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        service_key = (workspace_id, session_id)
        service_before = service._sessions[service_key].public_projection()  # noqa: SLF001
        service_bytes = json.dumps(
            service_before, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        owner_scope = service._sessions[service_key].owner_scope  # noqa: SLF001
        handle_counts = (
            worker_services.handle_registry.active_handle_count,
            worker_services.handle_registry.active_lease_count,
        )
        observed_events: list[dict] = []
        self.window.execution_event.connect(
            lambda event: observed_events.append(dict(event))
        )

        def assert_viewer_unchanged() -> None:
            current_bridge = bridge.session_state(viewer_id)
            self.assertEqual(
                json.dumps(
                    current_bridge, sort_keys=True, separators=(",", ":")
                ).encode("utf-8"),
                bridge_bytes,
            )
            self.assertEqual(current_bridge["phase"], "open")
            self.assertEqual(current_bridge["live_open_status"], "ready")
            self.assertEqual(current_bridge["transport_revision"], 7)
            self.assertEqual(current_bridge["data_refs"], session_payload)
            self.assertEqual(current_bridge["transport"], transport)
            self.assertEqual(current_bridge["summary"]["preview"], summary["preview"])
            current_service = service._sessions[service_key]  # noqa: SLF001
            self.assertEqual(current_service.owner_scope, owner_scope)
            self.assertEqual(
                json.dumps(
                    current_service.public_projection(),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
                service_bytes,
            )
            self.assertIs(
                self.window.run_state.node_solution_facts_by_workspace_id[
                    workspace_id
                ][viewer_id].freshness,
                SolutionFreshness.CURRENT,
            )

        self.window.run_controller.set_auto_run_enabled(True)
        with patch.object(
            service, "_release_owner_scope", wraps=service._release_owner_scope
        ) as owner_release, patch.object(
            service, "_release_live_transport", wraps=service._release_live_transport
        ) as transport_release:
            self.window.scene.set_node_property(toggle_id, "value", True)
            self.app.processEvents()

            self.assertEqual(
                execution_client.start_calls[-1]["target_node_ids"], (toggle_id,)
            )
            self.assertEqual(
                execution_client.invalidate_calls[-1].expired_node_ids,
                (toggle_id,),
            )
            self.assertEqual(
                execution_client.start_calls[-1]["recompute_node_ids"],
                (toggle_id,),
            )
            self.assertEqual(
                execution_client.start_calls[-1]["viewer_invalidation_node_ids"],
                (),
            )
            solution_facts = self.window.run_state.node_solution_facts_by_workspace_id[
                workspace_id
            ]
            self.assertIs(
                solution_facts[toggle_id].freshness, SolutionFreshness.EXPIRED
            )
            self.assertIs(
                solution_facts[viewer_id].freshness, SolutionFreshness.CURRENT
            )
            self.assertEqual(execution_client.invalidate_viewer_calls, [])

            workspace_epoch, node_epoch = bridge._viewer_epochs(  # noqa: SLF001
                workspace_id, viewer_id
            )
            self.assertEqual(node_epoch, 0)
            empty_digest = viewer_epoch_snapshot_digest(
                workspace_id=workspace_id,
                node_ids=(),
                workspace_epoch=workspace_epoch,
                node_epochs=(),
            )
            self.assertTrue(
                bridge.adopt_committed_invalidation(
                    workspace_id=workspace_id,
                    node_ids=(),
                    workspace_epoch=workspace_epoch,
                    node_epochs=(),
                    snapshot_digest=empty_digest,
                    reason="workspace_rerun",
                    run_id="run_live",
                )
            )
            self.assertEqual(
                service.adopt_invalidation_snapshot(
                    workspace_id=workspace_id,
                    node_ids=(),
                    workspace_epoch=workspace_epoch,
                    node_epochs=(),
                    snapshot_digest=empty_digest,
                    reason="workspace_rerun",
                ),
                0,
            )
            assert_viewer_unchanged()

            for event in (
                {
                    "type": "run_started",
                    "run_id": "run_live",
                    "workspace_id": workspace_id,
                },
                {
                    "type": "node_started",
                    "run_id": "run_live",
                    "workspace_id": workspace_id,
                    "node_id": toggle_id,
                },
                {
                    "type": "node_settled",
                    "status": "completed",
                    "run_id": "run_live",
                    "workspace_id": workspace_id,
                    "node_id": toggle_id,
                    "outputs": _value_outputs(boolean=True),
                },
                {
                    "type": "run_completed",
                    "run_id": "run_live",
                    "workspace_id": workspace_id,
                },
            ):
                self.window.execution_event.emit(event)
                self.app.processEvents()
                assert_viewer_unchanged()

            owner_release.assert_not_called()
            transport_release.assert_not_called()

        self.assertFalse(
            any(
                event.get("type") == "node_started"
                and event.get("node_id") == viewer_id
                for event in observed_events
            )
        )
        self.assertEqual(
            (
                worker_services.handle_registry.active_handle_count,
                worker_services.handle_registry.active_lease_count,
            ),
            handle_counts,
        )

        runtime_snapshot = execution_client.start_calls[-1]["trigger"][
            "runtime_snapshot"
        ]
        connected_result = execution_client.invalidate_solution(
            project_id,
            workspace_id,
            runtime_snapshot,
            (cad_id,),
            "connected_upstream_changed",
        )
        connected_prepared = execution_client.prepare_execution(
            SimpleNamespace(
                runtime_snapshot=runtime_snapshot,
                workspace_id=workspace_id,
                target_node_ids=connected_result.expired_node_ids,
            )
        )
        self.assertEqual(connected_result.expired_node_ids, (cad_id, viewer_id))
        self.assertIn(viewer_id, connected_prepared.recompute_node_ids)
        self.assertEqual(
            connected_prepared.viewer_invalidation_node_ids, (viewer_id,)
        )

        node_epochs = ((viewer_id, node_epoch + 1),)
        scoped_digest = viewer_epoch_snapshot_digest(
            workspace_id=workspace_id,
            node_ids=(viewer_id,),
            workspace_epoch=workspace_epoch,
            node_epochs=node_epochs,
        )
        self.assertTrue(
            bridge.adopt_committed_invalidation(
                workspace_id=workspace_id,
                node_ids=(viewer_id,),
                workspace_epoch=workspace_epoch,
                node_epochs=node_epochs,
                snapshot_digest=scoped_digest,
                reason="same_node_changed",
            )
        )
        self.assertEqual(
            service.adopt_invalidation_snapshot(
                workspace_id=workspace_id,
                node_ids=(viewer_id,),
                workspace_epoch=workspace_epoch,
                node_epochs=node_epochs,
                snapshot_digest=scoped_digest,
                reason="same_node_changed",
            ),
            1,
        )
        self.window.execution_event.emit(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id=workspace_id,
                node_id=viewer_id,
                session_id=session_id,
                data_refs={"scene": "delayed"},
                transport={"kind": "delayed"},
                workspace_invalidation_epoch=workspace_epoch,
                node_invalidation_epoch=node_epoch,
            )
        )
        delayed_close = service.close_session(
            CloseViewerSessionCommand(
                request_id="delayed_close",
                workspace_id=workspace_id,
                node_id=viewer_id,
                session_id=session_id,
                workspace_invalidation_epoch=workspace_epoch,
                node_invalidation_epoch=node_epoch,
            )
        )
        self.app.processEvents()
        self.assertEqual(bridge.session_state(viewer_id)["phase"], "blocked")
        self.assertIsInstance(delayed_close, ViewerSessionFailedEvent)
        self.assertIn("newer epoch", delayed_close.error)

    def test_node_execution_visualization_shell_events_drive_graph_node_chrome_states(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.logger", x=120.0, y=40.0)
        self.window._active_run_id = "run_live"
        self.window._active_run_workspace_id = workspace_id
        self.window.run_projection_controller.set_run_ui_state("running", "Running", 1, 0, 0, 0)
        self.app.processEvents()

        graph_canvas = self._graph_canvas_item()
        wait_for_condition_or_raise(
            lambda: _graph_node_card(graph_canvas, node_id) is not None,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for graph node card to appear.",
        )
        node_card = _graph_node_card(graph_canvas, node_id)
        self.assertIsNotNone(node_card)
        if node_card is None:
            self.fail("Expected graph node card to exist")

        elapsed_timer = node_card.findChild(QObject, "graphNodeElapsedTimer")
        self.assertIsNotNone(elapsed_timer)
        self.assertFalse(bool(node_card.property("isRunningNode")))
        self.assertFalse(bool(node_card.property("isCompletedNode")))
        self.assertEqual(dict(graph_canvas.property("runningNodeLookup")), {})
        self.assertEqual(dict(graph_canvas.property("completedNodeLookup")), {})

        self.window.execution_event.emit(
            {
                "type": "run_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
            }
        )
        self.window.execution_event.emit(
            {
                "type": "node_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": node_id,
            }
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isRunningNode")) and bool(elapsed_timer.property("visible")),
            timeout_ms=400,
            app=self.app,
            timeout_message="Timed out waiting for running-node execution chrome.",
        )
        self.assertTrue(bool(node_card.property("renderActive")))
        self.assertEqual(int(node_card.property("z")), 31)
        self.assertEqual(dict(graph_canvas.property("runningNodeLookup")), {node_id: True})
        self.assertTrue(bool(elapsed_timer.property("liveElapsedActive")))
        self.assertGreater(float(elapsed_timer.property("startedAtMs")), 0.0)

        QTest.qWait(160)
        self.app.processEvents()
        elapsed_text = str(elapsed_timer.property("text") or "")
        self.assertRegex(elapsed_text, re.compile(r"^\d+\.\ds$"))
        self.assertNotEqual(elapsed_text, "0.0s")

        self.window.execution_event.emit(
            {
                "type": "node_settled",
                "status": "completed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": node_id,
                "outputs": _value_outputs(exit_code=0),
            }
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isCompletedNode"))
            and not bool(node_card.property("isRunningNode"))
            and bool(elapsed_timer.property("visible"))
            and bool(elapsed_timer.property("cachedElapsedActive")),
            timeout_ms=400,
            app=self.app,
            timeout_message="Timed out waiting for completed-node execution chrome.",
        )
        self.assertIn(int(node_card.property("z")), {29, 30})
        self.assertEqual(dict(graph_canvas.property("runningNodeLookup")), {})
        self.assertEqual(dict(graph_canvas.property("completedNodeLookup")), {node_id: True})
        self.assertFalse(bool(elapsed_timer.property("liveElapsedActive")))
        self.assertGreaterEqual(float(elapsed_timer.property("cachedElapsedMilliseconds")), 0.0)

        self.window.execution_event.emit(
            {
                "type": "run_completed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
            }
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isCompletedNode"))
            and not bool(node_card.property("isRunningNode"))
            and bool(elapsed_timer.property("cachedElapsedActive")),
            timeout_ms=400,
            app=self.app,
            timeout_message="Timed out waiting for settled node state after run completion.",
        )
        self.assertEqual(dict(graph_canvas.property("runningNodeLookup")), {})
        self.assertEqual(dict(graph_canvas.property("completedNodeLookup")), {node_id: True})
        self.assertEqual(dict(graph_canvas.property("freshRunNodeLookup")), {})
        self.assertFalse(bool(node_card.property("isFreshRunNode")))
        self.assertTrue(bool(elapsed_timer.property("visible")))
        self.assertTrue(bool(elapsed_timer.property("cachedElapsedActive")))

        self.window.scene.set_node_property(node_id, "message", "Invalidate cached elapsed footer")
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: (
                (_graph_node_child(graph_canvas, node_id, "graphNodeElapsedTimer") is not None)
                and not bool(_graph_node_child(graph_canvas, node_id, "graphNodeElapsedTimer").property("visible"))
            ),
            timeout_ms=400,
            app=self.app,
            timeout_message="Timed out waiting for cached elapsed footer invalidation.",
        )
        self.assertEqual(dict(graph_canvas.property("freshRunNodeLookup")), {})

    def test_warning_node_settled_event_marks_golden_chrome_and_logs_without_failure_focus(
        self,
    ) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.logger", x=160.0, y=60.0)
        self.window._active_run_id = "run_warning"
        self.window._active_run_workspace_id = workspace_id
        self.window.run_projection_controller.set_run_ui_state("running", "Running", 1, 0, 0, 0)
        self.app.processEvents()

        graph_canvas = self._graph_canvas_item()
        wait_for_condition_or_raise(
            lambda: _graph_node_card(graph_canvas, node_id) is not None,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for graph node card to appear.",
        )
        node_card = _graph_node_card(graph_canvas, node_id)
        self.assertIsNotNone(node_card)
        if node_card is None:
            self.fail("Expected graph node card to exist")
        elapsed_timer = node_card.findChild(QObject, "graphNodeElapsedTimer")
        self.assertIsNotNone(elapsed_timer)
        if elapsed_timer is None:
            self.fail("Expected warning chrome probes to exist")

        center_before = (self.window.view.center_x, self.window.view.center_y)
        selected_before = self.window.scene.selected_node_id()
        warning_text = "Tabular large-data warning: source_larger_than_1_gib"
        with patch.object(QMessageBox, "critical") as critical:
            self.window.execution_event.emit(
                {
                    "type": "log",
                    "run_id": "run_warning",
                    "workspace_id": workspace_id,
                    "node_id": node_id,
                    "level": "warning",
                    "message": warning_text,
                }
            )
            self.window.execution_event.emit(
                {
                    "type": "node_settled",
                    "status": "completed",
                    "run_id": "run_warning",
                    "workspace_id": workspace_id,
                    "node_id": node_id,
                    "elapsed_ms": 1234.0,
                    "outputs": _value_outputs(message=warning_text),
                    "warnings": [
                        warning_text,
                        "Tabular selector-required warning: selector_required",
                        "Tabular backend-fallback warning: backend_fallback_to_python_text_stream",
                        "Tabular NPZ-gated warning: large_npz_preview_requires_explicit_opt_in",
                    ],
                }
            )
            self.app.processEvents()
            critical.assert_not_called()

        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isWarningNode"))
            and bool(node_card.property("isCompletedNode"))
            and bool(elapsed_timer.property("cachedElapsedActive")),
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for warning-node execution chrome.",
        )
        self.assertEqual(dict(graph_canvas.property("warningNodeLookup")), {node_id: True})
        self.assertEqual(dict(graph_canvas.property("completedNodeLookup")), {node_id: True})
        self.assertEqual(dict(graph_canvas.property("failedNodeLookup")), {})
        self.assertEqual(self.window.run_state.failed_node_id, "")
        self.assertEqual(self.window.scene.selected_node_id(), selected_before)
        self.assertEqual((self.window.view.center_x, self.window.view.center_y), center_before)
        self.assertIn(warning_text, self.window.console_panel.output_text)
        self.assertIn(warning_text, self.window.console_panel.warnings_text)
        self.assertNotIn(warning_text, self.window.console_panel.errors_text)
        self.assertEqual(
            float(elapsed_timer.property("opacity")),
            float(node_card.property("warningElapsedFooterOpacity")),
        )

    def test_persistent_node_elapsed_footer_shell_events_render_live_then_cached_until_invalidation(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.logger", x=180.0, y=80.0)
        self.window._active_run_id = "run_live"
        self.window._active_run_workspace_id = workspace_id
        self.window.run_projection_controller.set_run_ui_state("running", "Running", 1, 0, 0, 0)
        self.app.processEvents()

        graph_canvas = self._graph_canvas_item()
        wait_for_condition_or_raise(
            lambda: _graph_node_card(graph_canvas, node_id) is not None,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for graph node card to appear.",
        )
        node_card = _graph_node_card(graph_canvas, node_id)
        self.assertIsNotNone(node_card)
        if node_card is None:
            self.fail("Expected graph node card to exist")

        elapsed_timer = node_card.findChild(QObject, "graphNodeElapsedTimer")
        self.assertIsNotNone(elapsed_timer)
        if elapsed_timer is None:
            self.fail("Expected graph node execution chrome items to exist")

        started_at_ms = (time.time() * 1000.0) - 2400.0
        completed_elapsed_ms = 3456.7

        self.window.execution_event.emit(
            {
                "type": "run_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
            }
        )
        self.window.execution_event.emit(
            {
                "type": "node_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": node_id,
                "started_at_epoch_ms": started_at_ms,
            }
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isRunningNode"))
            and bool(elapsed_timer.property("visible"))
            and bool(elapsed_timer.property("liveElapsedActive"))
            and abs(float(elapsed_timer.property("startedAtMs")) - started_at_ms) < 16.0
            and float(elapsed_timer.property("elapsedMilliseconds")) >= 2000.0,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for lookup-backed live elapsed footer rendering.",
        )
        self.assertEqual(
            graph_canvas.property("runningNodeStartedAtMsLookup"),
            {node_id: started_at_ms},
        )
        self.window.execution_event.emit(
            {
                "type": "node_settled",
                "status": "completed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": node_id,
                "elapsed_ms": completed_elapsed_ms,
                "outputs": _value_outputs(exit_code=0),
            }
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: not bool(node_card.property("isRunningNode"))
            and bool(node_card.property("isCompletedNode"))
            and bool(elapsed_timer.property("visible"))
            and bool(elapsed_timer.property("cachedElapsedActive"))
            and abs(float(elapsed_timer.property("cachedElapsedMilliseconds")) - completed_elapsed_ms) < 0.01
            and str(elapsed_timer.property("text") or "") == "3.5s",
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for cached elapsed footer rendering after completion.",
        )
        self.assertEqual(
            graph_canvas.property("nodeElapsedMsLookup"),
            {node_id: completed_elapsed_ms},
        )
        self.assertEqual(graph_canvas.property("freshRunNodeLookup"), {})

        self.window.execution_event.emit(
            {
                "type": "run_completed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
            }
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: not bool(node_card.property("isRunningNode"))
            and bool(node_card.property("isCompletedNode"))
            and bool(elapsed_timer.property("visible"))
            and bool(elapsed_timer.property("cachedElapsedActive"))
            and str(elapsed_timer.property("text") or "") == "3.5s",
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for cached elapsed footer persistence after run completion.",
        )
        self.assertEqual(graph_canvas.property("freshRunNodeLookup"), {})
        self.assertFalse(bool(node_card.property("isFreshRunNode")))

        self.window.scene.set_node_title(node_id, "Retained Footer")
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: (
                (_graph_node_child(graph_canvas, node_id, "graphNodeElapsedTimer") is not None)
                and bool(_graph_node_child(graph_canvas, node_id, "graphNodeElapsedTimer").property("visible"))
                and bool(_graph_node_child(graph_canvas, node_id, "graphNodeElapsedTimer").property("cachedElapsedActive"))
                and str(_graph_node_child(graph_canvas, node_id, "graphNodeElapsedTimer").property("text") or "") == "3.5s"
            ),
            timeout_ms=400,
            app=self.app,
            timeout_message="Timed out waiting for cached elapsed footer to survive cosmetic title edits.",
        )
        node_card = _graph_node_card(graph_canvas, node_id)
        elapsed_timer = _graph_node_child(graph_canvas, node_id, "graphNodeElapsedTimer")
        self.assertIsNotNone(node_card)
        self.assertIsNotNone(elapsed_timer)
        if node_card is None or elapsed_timer is None:
            self.fail("Expected graph node card and elapsed timer to survive cosmetic title edits")
        self.assertFalse(bool(node_card.property("isFreshRunNode")))
        self.assertTrue(bool(node_card.property("isCompletedNode")))

        self.window.scene.set_node_property(node_id, "message", "Invalidate cached elapsed footer")
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: (
                (_graph_node_child(graph_canvas, node_id, "graphNodeElapsedTimer") is not None)
                and not bool(_graph_node_child(graph_canvas, node_id, "graphNodeElapsedTimer").property("visible"))
                and not bool(_graph_node_child(graph_canvas, node_id, "graphNodeElapsedTimer").property("cachedElapsedActive"))
                and not bool(_graph_node_card(graph_canvas, node_id).property("isFreshRunNode"))
            ),
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for cached elapsed footer invalidation.",
        )
        self.assertEqual(graph_canvas.property("nodeElapsedMsLookup"), {})
        self.assertEqual(graph_canvas.property("freshRunNodeLookup"), {})

    def test_persistent_node_elapsed_footer_failure_priority_hides_failed_running_live_timer(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.logger", x=220.0, y=140.0)
        self.window._active_run_id = "run_live"
        self.window._active_run_workspace_id = workspace_id
        self.window.run_projection_controller.set_run_ui_state("running", "Running", 1, 0, 0, 0)
        self.app.processEvents()

        graph_canvas = self._graph_canvas_item()
        wait_for_condition_or_raise(
            lambda: _graph_node_card(graph_canvas, node_id) is not None,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for graph node card to appear.",
        )
        node_card = _graph_node_card(graph_canvas, node_id)
        self.assertIsNotNone(node_card)
        if node_card is None:
            self.fail("Expected graph node card to exist")

        elapsed_timer = node_card.findChild(QObject, "graphNodeElapsedTimer")
        self.assertIsNotNone(elapsed_timer)
        if elapsed_timer is None:
            self.fail("Expected graph node execution chrome items to exist")

        started_at_ms = (time.time() * 1000.0) - 1800.0
        self.window.execution_event.emit(
            {
                "type": "run_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
            }
        )
        self.window.execution_event.emit(
            {
                "type": "node_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": node_id,
                "started_at_epoch_ms": started_at_ms,
            }
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isRunningNode"))
            and bool(elapsed_timer.property("visible"))
            and bool(elapsed_timer.property("liveElapsedActive"))
            and float(elapsed_timer.property("elapsedMilliseconds")) >= 1400.0,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for running-node live elapsed footer to appear.",
        )

        with patch.object(QMessageBox, "critical"):
            self.window.execution_event.emit(
                {
                    "type": "run_failed",
                    "run_id": "run_live",
                    "workspace_id": workspace_id,
                    "node_id": node_id,
                    "error": "boom",
                    "traceback": "traceback: line 1",
                    "fatal": False,
                }
            )
            self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isFailedNode"))
            and not bool(elapsed_timer.property("visible"))
            and not bool(elapsed_timer.property("liveElapsedActive"))
            and not bool(elapsed_timer.property("cachedElapsedActive")),
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for failure-priority elapsed footer cleanup.",
        )
        self.assertEqual(graph_canvas.property("runningNodeStartedAtMsLookup"), {})

    def test_graph_typography_host_chrome_shell_events_apply_shared_roles_and_preserve_elapsed_footer_semantics(
        self,
    ) -> None:
        resolved = self.window.app_preferences_controller.update_graphics_settings(
            {"typography": {"graph_label_pixel_size": 16}},
            host=self.window,
        )
        self.app.processEvents()
        self.assertEqual(resolved["typography"]["graph_label_pixel_size"], 16)

        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.python_script", x=180.0, y=80.0)
        self.window._active_run_id = "run_live"
        self.window._active_run_workspace_id = workspace_id
        self.window.run_projection_controller.set_run_ui_state("running", "Running", 1, 0, 0, 0)
        self.app.processEvents()

        graph_canvas = self._graph_canvas_item()
        wait_for_condition_or_raise(
            lambda: _graph_node_card(graph_canvas, node_id) is not None,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for graph node card to appear.",
        )
        node_card = _graph_node_card(graph_canvas, node_id)
        self.assertIsNotNone(node_card)
        if node_card is None:
            self.fail("Expected graph node card to exist")

        title = node_card.findChild(QObject, "graphNodeTitle")
        typography = node_card.findChild(QObject, "graphSharedTypography")
        elapsed_timer = node_card.findChild(QObject, "graphNodeElapsedTimer")
        input_labels = _graph_node_children(graph_canvas, node_id, "graphNodeInputPortLabel")
        output_labels = _graph_node_children(graph_canvas, node_id, "graphNodeOutputPortLabel")
        data_input_label = next(
            (label for label in input_labels if str(label.property("text") or "") != "\u27A1"),
            None,
        )
        data_output_label = next(iter(output_labels), None)

        self.assertIsNotNone(title)
        self.assertIsNotNone(typography)
        self.assertIsNotNone(elapsed_timer)
        self.assertIsNotNone(data_input_label)
        self.assertIsNotNone(data_output_label)
        if (
            title is None
            or typography is None
            or elapsed_timer is None
            or data_input_label is None
            or data_output_label is None
        ):
            self.fail("Expected standard host chrome typography items to exist")

        wait_for_condition_or_raise(
            lambda: title.property("font").pixelSize() == int(typography.property("nodeTitlePixelSize"))
            and data_input_label.property("font").pixelSize() == int(typography.property("portLabelPixelSize"))
            and data_output_label.property("font").pixelSize() == int(typography.property("portLabelPixelSize")),
            timeout_ms=400,
            app=self.app,
            timeout_message="Timed out waiting for shared host chrome typography to apply on the shell node card.",
        )

        self.assertEqual(title.property("font").pixelSize(), 18)
        self.assertEqual(title.property("font").weight(), int(typography.property("nodeTitleFontWeight")))
        self.assertEqual(data_input_label.property("font").pixelSize(), 16)
        self.assertEqual(data_input_label.property("font").weight(), int(typography.property("portLabelFontWeight")))
        self.assertEqual(data_output_label.property("font").pixelSize(), 16)
        self.assertEqual(data_output_label.property("font").weight(), int(typography.property("portLabelFontWeight")))

        started_at_ms = (time.time() * 1000.0) - 2400.0
        completed_elapsed_ms = 3456.7
        self.window.execution_event.emit(
            {
                "type": "run_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
            }
        )
        self.window.execution_event.emit(
            {
                "type": "node_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": node_id,
                "started_at_epoch_ms": started_at_ms,
            }
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(elapsed_timer.property("visible"))
            and bool(elapsed_timer.property("liveElapsedActive"))
            and abs(float(elapsed_timer.property("startedAtMs")) - started_at_ms) < 16.0,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for shared-typography live elapsed footer rendering.",
        )
        self.assertEqual(
            elapsed_timer.property("font").pixelSize(),
            int(typography.property("elapsedFooterPixelSize")),
        )

        self.window.execution_event.emit(
            {
                "type": "node_settled",
                "status": "completed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": node_id,
                "elapsed_ms": completed_elapsed_ms,
                "outputs": _value_outputs(exit_code=0),
            }
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(elapsed_timer.property("visible"))
            and bool(elapsed_timer.property("cachedElapsedActive"))
            and not bool(elapsed_timer.property("liveElapsedActive"))
            and str(elapsed_timer.property("text") or "") == "3.5s",
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for shared-typography cached elapsed footer rendering.",
        )
        self.assertEqual(
            elapsed_timer.property("font").pixelSize(),
            int(typography.property("elapsedFooterPixelSize")),
        )

    def test_node_execution_visualization_failure_priority_overrides_completed_chrome(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.logger", x=180.0, y=120.0)
        graph_canvas = self._graph_canvas_item()

        wait_for_condition_or_raise(
            lambda: _graph_node_card(graph_canvas, node_id) is not None,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for graph node card to appear.",
        )
        node_card = _graph_node_card(graph_canvas, node_id)
        self.assertIsNotNone(node_card)
        if node_card is None:
            self.fail("Expected graph node card to exist")

        self.window.run_projection_controller.mark_node_execution_settled(workspace_id, node_id)
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isCompletedNode")),
            timeout_ms=400,
            app=self.app,
            timeout_message="Timed out waiting for completed execution chrome before failure priority check.",
        )

        with patch.object(QMessageBox, "critical"):
            self.window._focus_failed_node(workspace_id, node_id)
        self.app.processEvents()

        self.assertTrue(bool(node_card.property("isFailedNode")))
        self.assertEqual(dict(graph_canvas.property("failedNodeLookup")), {node_id: True})

    def test_node_settled_failure_hides_elapsed_timer_for_failed_running_node(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.logger", x=220.0, y=140.0)
        self.window._active_run_id = "run_live"
        self.window._active_run_workspace_id = workspace_id
        self.window.run_projection_controller.set_run_ui_state("running", "Running", 1, 0, 0, 0)
        self.app.processEvents()

        graph_canvas = self._graph_canvas_item()
        wait_for_condition_or_raise(
            lambda: _graph_node_card(graph_canvas, node_id) is not None,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for graph node card to appear.",
        )
        node_card = _graph_node_card(graph_canvas, node_id)
        self.assertIsNotNone(node_card)
        if node_card is None:
            self.fail("Expected graph node card to exist")

        elapsed_timer = node_card.findChild(QObject, "graphNodeElapsedTimer")
        self.assertIsNotNone(elapsed_timer)

        self.window.execution_event.emit(
            {
                "type": "run_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
            }
        )
        self.window.execution_event.emit(
            {
                "type": "node_started",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": node_id,
            }
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isRunningNode")) and bool(elapsed_timer.property("visible")),
            timeout_ms=400,
            app=self.app,
            timeout_message="Timed out waiting for running-node elapsed timer to appear.",
        )

        QTest.qWait(160)
        self.app.processEvents()
        self.assertNotEqual(str(elapsed_timer.property("text") or ""), "0.0s")

        with patch.object(QMessageBox, "critical"):
            self.window.execution_event.emit(
                {
                    "type": "node_settled",
                    "status": "failed",
                    "run_id": "run_live",
                    "workspace_id": workspace_id,
                    "node_id": node_id,
                    "errors": (
                        {
                            "node_id": node_id,
                            "error": "boom",
                            "traceback": "traceback: line 1",
                        },
                    ),
                }
            )
            self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isFailedNode")) and not bool(elapsed_timer.property("visible")),
            timeout_ms=400,
            app=self.app,
            timeout_message="Timed out waiting for failed-node timer cleanup.",
        )
        self.assertEqual(dict(graph_canvas.property("failedNodeLookup")), {node_id: True})

    def test_viewer_session_bridge_context_property_exists_and_rerun_invalidates_current_workspace(self) -> None:
        execution_client = _ViewerExecutionClientStub(self.window.registry)
        self.window.execution_client = execution_client
        self.window.run_controller.set_auto_run_enabled(False)

        bridge = self.window.quick_widget.rootContext().contextProperty("viewerSessionBridge")
        self.assertIsInstance(bridge, ViewerSessionBridge)
        self.assertIs(bridge, self.window.viewer_session_bridge)

        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("model.viewer", x=120.0, y=40.0)
        session_id = bridge.open(
            node_id,
            {
                "data_refs": {"fields_container": "fields_ref"},
                "summary": {"result_name": "displacement"},
            },
        )
        open_call = execution_client.open_calls[-1]
        self.window.execution_event.emit(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=session_id,
            )
        )
        self.app.processEvents()

        self.window.run_controller.run_workflow()
        self.app.processEvents()

        workspace_epoch, node_epoch = bridge._viewer_epochs(  # noqa: SLF001
            workspace_id, node_id
        )
        digest = viewer_epoch_snapshot_digest(
            workspace_id=workspace_id,
            node_ids=(node_id,),
            workspace_epoch=workspace_epoch,
            node_epochs=((node_id, node_epoch + 1),),
        )
        self.window.execution_event.emit(
            {
                "type": "viewer_invalidation_committed",
                "run_id": self.window.run_state.active_run_id,
                "workspace_id": workspace_id,
                "viewer_invalidation_node_ids": [node_id],
                "viewer_workspace_invalidation_epoch": workspace_epoch,
                "viewer_node_invalidation_epochs": [[node_id, node_epoch + 1]],
                "viewer_epoch_snapshot_digest": digest,
                "reason": "workspace_rerun",
            }
        )
        self.app.processEvents()

        state = bridge.session_state(node_id)
        self.assertEqual(state["phase"], "blocked")
        self.assertEqual(state["live_open_status"], "blocked")
        self.assertTrue(state["live_open_blocker"]["rerun_required"])
        self.assertEqual(state["summary"]["run_id"], "run_live")
        self.assertEqual(self.window.run_state.active_run_id, "run_live")
        self.assertEqual(self.window.run_state.active_run_workspace_id, workspace_id)

    def test_successful_dispatch_invalidates_exact_viewers_without_host_reset(self) -> None:
        execution_client = _ViewerExecutionClientStub(self.window.registry)
        self.window.execution_client = execution_client
        self.window.run_controller.set_auto_run_enabled(False)
        viewer_host_service = _ViewerHostServiceStub()
        self.window.viewer_host_service = viewer_host_service

        bridge = self.window.viewer_session_bridge
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("model.viewer", x=120.0, y=40.0)
        session_id = bridge.open(
            node_id,
            {
                "backend_id": "corex_scene",
                "data_refs": {"fields_container": "fields_ref"},
            },
        )
        open_call = execution_client.open_calls[-1]
        self.window.execution_event.emit(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=session_id,
                backend_id="corex_scene",
                live_open_status="ready",
                transport={"kind": "bundle", "backend_id": "corex_scene"},
                summary={"cache_state": "live_ready"},
                options={"live_mode": "full"},
            )
        )
        self.app.processEvents()
        self.assertTrue(
            bridge.set_embedded_interaction_active(
                node_id, True, {"workspace_id": workspace_id}
            )
        )
        self.app.processEvents()

        self.window.run_controller.run_workflow()
        self.app.processEvents()

        workspace_epoch, node_epoch = bridge._viewer_epochs(  # noqa: SLF001
            workspace_id, node_id
        )
        snapshot_digest = viewer_epoch_snapshot_digest(
            workspace_id=workspace_id,
            node_ids=(node_id,),
            workspace_epoch=workspace_epoch,
            node_epochs=((node_id, node_epoch + 1),),
        )
        self.window.execution_event.emit(
            {
                "type": "viewer_invalidation_committed",
                "run_id": self.window.run_state.active_run_id,
                "workspace_id": workspace_id,
                "viewer_invalidation_node_ids": [node_id],
                "viewer_workspace_invalidation_epoch": workspace_epoch,
                "viewer_node_invalidation_epochs": [[node_id, node_epoch + 1]],
                "viewer_epoch_snapshot_digest": snapshot_digest,
                "reason": "workspace_rerun",
            }
        )
        self.app.processEvents()

        self.assertEqual(viewer_host_service.calls, [])
        self.assertEqual(execution_client.start_calls[-1]["workspace_id"], workspace_id)
        self.assertEqual(execution_client.invalidate_viewer_calls, [])
        self.assertEqual(bridge.session_state(node_id)["phase"], "blocked")

    def test_failed_dispatch_leaves_viewer_host_and_epochs_untouched(self) -> None:
        execution_client = _ViewerExecutionClientStub(self.window.registry)
        execution_client.next_run_id = ""
        self.window.execution_client = execution_client
        self.window.run_controller.set_auto_run_enabled(False)
        viewer_host_service = _ViewerHostServiceStub()
        self.window.viewer_host_service = viewer_host_service

        bridge = self.window.viewer_session_bridge
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("model.viewer", x=120.0, y=40.0)
        session_id = bridge.open(
            node_id,
            {
                "backend_id": "corex_scene",
                "data_refs": {"fields_container": "fields_ref"},
            },
        )
        open_call = execution_client.open_calls[-1]
        self.window.execution_event.emit(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=session_id,
                backend_id="corex_scene",
                live_open_status="ready",
                transport={"kind": "bundle", "backend_id": "corex_scene"},
                summary={"cache_state": "live_ready"},
                options={"live_mode": "full"},
            )
        )
        self.app.processEvents()
        self.assertTrue(
            bridge.set_embedded_interaction_active(
                node_id, True, {"workspace_id": workspace_id}
            )
        )
        self.app.processEvents()

        self.window.run_controller.run_workflow()
        self.app.processEvents()

        self.assertEqual(viewer_host_service.calls, [])
        self.assertEqual(execution_client.invalidate_viewer_calls, [])
        self.assertEqual(self.window.run_state.engine_state_value, "error")

    def test_shell_context_bridge_explicit_sources_wrap_shell_window_with_focused_sources(self) -> None:
        library_bridge = ShellLibraryBridge(
            self.window,
            shell_window=self.window,
            library_source=self.window.shell_library_presenter,
        )
        workspace_bridge = ShellWorkspaceBridge(
            self.window,
            shell_window=self.window,
            workspace_source=self.window.shell_workspace_presenter,
            scene_bridge=self.window.scene,
            view_bridge=self.window.view,
            console_bridge=self.window.console_panel,
            workspace_tabs_bridge=self.window.workspace_tabs,
        )
        inspector_bridge = ShellInspectorBridge(
            self.window,
            shell_window=self.window,
            inspector_source=self.window.shell_inspector_presenter,
            scene_bridge=self.window.scene,
        )

        self.assertIsNot(library_bridge.library_source, self.window)
        self.assertIsNot(workspace_bridge.workspace_source, self.window)
        self.assertIsNot(inspector_bridge.inspector_source, self.window)
        self.assertEqual(library_bridge.graph_search_query, self.window.shell_library_presenter.graph_search_query)
        self.assertEqual(workspace_bridge.project_display_name, self.window.shell_workspace_presenter.project_display_name)
        self.assertEqual(inspector_bridge.selected_node_title, self.window.shell_inspector_presenter.selected_node_title)

    def test_selected_workspace_toolbar_buttons_follow_run_owner_state_and_warning_path(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        if root_object is None:
            self.fail("Expected main shell root object to exist")

        run_control_button = _named_qquick_item(root_object, "shellRunToolbarRunPauseResumeButton")
        stop_button = _named_qquick_item(root_object, "shellRunToolbarStopButton")
        auto_button = _named_qquick_item(root_object, "shellRunToolbarAutoButton")
        self.assertIsNone(_named_qquick_item(root_object, "shellRunToolbarRunButton"))
        self.assertIsNone(_named_qquick_item(root_object, "shellRunToolbarPauseButton"))
        self.assertIsNotNone(run_control_button)
        self.assertIsNotNone(stop_button)
        self.assertIsNotNone(auto_button)
        if run_control_button is None or stop_button is None or auto_button is None:
            self.fail("Expected shell toolbar run controls to expose stable object names")

        workspace_a_id = self.window.workspace_manager.active_workspace_id()
        workspace_b_id = self.window.workspace_manager.create_workspace("Second Workspace")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(workspace_a_id)
        self.app.processEvents()

        bridge = self.window.quick_widget.rootContext().contextProperty("shellWorkspaceBridge")
        self.assertIsInstance(bridge, ShellWorkspaceBridge)
        if not isinstance(bridge, ShellWorkspaceBridge):
            self.fail("Expected shellWorkspaceBridge context property to exist")
        self.assertTrue(bridge.auto_run_enabled)
        self.assertTrue(bool(auto_button.property("selectedStyle")))
        QMetaObject.invokeMethod(auto_button, "clicked")
        self.app.processEvents()
        self.assertFalse(bridge.auto_run_enabled)
        self.assertFalse(bool(auto_button.property("selectedStyle")))

        wait_for_condition_or_raise(
            lambda: bool(run_control_button.property("enabled"))
            and str(run_control_button.property("iconName")) == "run"
            and not bool(stop_button.property("enabled")),
            timeout_ms=400,
            app=self.app,
            timeout_message="Timed out waiting for idle toolbar run controls.",
        )

        with (
            patch.object(self.window.execution_client, "dispatch_prepared", return_value="run_owner") as dispatch_prepared,
            patch.object(self.window.execution_client, "pause_run") as pause_run,
            patch.object(self.window.execution_client, "resume_run") as resume_run,
        ):
            QMetaObject.invokeMethod(run_control_button, "clicked")
            self.app.processEvents()

            wait_for_condition_or_raise(
                lambda: bool(run_control_button.property("enabled"))
                and str(run_control_button.property("iconName")) == "pause"
                and bool(stop_button.property("enabled")),
                timeout_ms=400,
                app=self.app,
                timeout_message="Timed out waiting for owning-workspace toolbar run controls.",
            )
            self.assertEqual(self.window.run_state.active_run_id, "run_owner")
            self.assertEqual(self.window.run_state.active_run_workspace_id, workspace_a_id)
            QMetaObject.invokeMethod(auto_button, "clicked")
            self.app.processEvents()
            self.assertTrue(bridge.auto_run_enabled)
            self.assertTrue(bool(auto_button.property("selectedStyle")))
            self.assertEqual(self.window.run_state.active_run_id, "run_owner")
            self.assertEqual(dispatch_prepared.call_count, 1)

            self.window.workspace_navigation_controller.switch_workspace(workspace_b_id)
            self.app.processEvents()

            wait_for_condition_or_raise(
                lambda: bool(run_control_button.property("enabled"))
                and str(run_control_button.property("iconName")) == "run"
                and not bool(stop_button.property("enabled")),
                timeout_ms=400,
                app=self.app,
                timeout_message="Timed out waiting for non-owning workspace toolbar run controls.",
            )

            warnings_before = self.window.console_panel.warning_count
            QMetaObject.invokeMethod(run_control_button, "clicked")
            self.app.processEvents()

            self.assertEqual(dispatch_prepared.call_count, 1)
            self.assertEqual(self.window.run_state.active_run_id, "run_owner")
            self.assertEqual(self.window.run_state.active_run_workspace_id, workspace_a_id)
            self.assertEqual(self.window.console_panel.warning_count, warnings_before + 1)
            self.assertIn("A workflow run is already active.", self.window.console_panel.warnings_text)

            self.window.workspace_navigation_controller.switch_workspace(workspace_a_id)
            self.app.processEvents()

            wait_for_condition_or_raise(
                lambda: bool(run_control_button.property("enabled"))
                and str(run_control_button.property("iconName")) == "pause"
                and bool(stop_button.property("enabled")),
                timeout_ms=400,
                app=self.app,
                timeout_message="Timed out waiting for owning-workspace toolbar run controls to restore.",
            )
            QMetaObject.invokeMethod(run_control_button, "clicked")
            self.app.processEvents()
            pause_run.assert_called_once_with("run_owner")

            self.window.execution_event.emit(
                {
                    "type": "run_state",
                    "run_id": "run_owner",
                    "workspace_id": workspace_a_id,
                    "state": "paused",
                    "transition": "pause",
                }
            )
            self.app.processEvents()

            wait_for_condition_or_raise(
                lambda: bool(run_control_button.property("enabled"))
                and str(run_control_button.property("iconName")) == "resume"
                and bool(stop_button.property("enabled")),
                timeout_ms=400,
                app=self.app,
                timeout_message="Timed out waiting for paused toolbar run controls.",
            )
            self.assertEqual(icon_path("resume"), icon_path("run"))
            QMetaObject.invokeMethod(run_control_button, "clicked")
            self.app.processEvents()
            resume_run.assert_called_once_with("run_owner")

            self.window.execution_event.emit(
                {
                    "type": "run_completed",
                    "run_id": "run_owner",
                    "workspace_id": workspace_a_id,
                }
            )
            self.app.processEvents()

            wait_for_condition_or_raise(
                lambda: bool(run_control_button.property("enabled"))
                and str(run_control_button.property("iconName")) == "run"
                and not bool(stop_button.property("enabled")),
                timeout_ms=400,
                app=self.app,
                timeout_message="Timed out waiting for completed toolbar run controls.",
            )

    def test_fatal_run_failed_event_invalidates_viewer_sessions_as_worker_reset(self) -> None:
        execution_client = _ViewerExecutionClientStub(self.window.registry)
        self.window.execution_client = execution_client
        self.window.run_controller.set_auto_run_enabled(False)

        bridge = self.window.viewer_session_bridge
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.logger", x=160.0, y=80.0)
        session_id = bridge.open(node_id, {"data_refs": {"fields_container": "fields_ref"}})
        open_call = execution_client.open_calls[-1]
        self.window.execution_event.emit(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=session_id,
            )
        )
        self.app.processEvents()

        self.window._active_run_id = "run_live"
        self.window._active_run_workspace_id = workspace_id
        self.window.run_projection_controller.set_run_ui_state("running", "Running", 1, 0, 0, 0)
        with patch.object(QMessageBox, "critical"):
            self.window.execution_event.emit(
                {
                    "type": "run_failed",
                    "run_id": "run_live",
                    "workspace_id": workspace_id,
                    "node_id": node_id,
                    "error": "Execution worker terminated unexpectedly.",
                    "traceback": "",
                    "fatal": True,
                }
            )
            self.app.processEvents()

        state = bridge.session_state(node_id)
        self.assertEqual(state["phase"], "blocked")
        self.assertEqual(state["live_open_status"], "blocked")
        self.assertTrue(state["live_open_blocker"]["rerun_required"])
        self.assertEqual(state["summary"]["live_transport_release_reason"], "worker_reset")
        self.assertEqual(self.window.run_state.active_run_id, "")
        graph_canvas = self._graph_canvas_item()
        self.assertEqual(dict(graph_canvas.property("failedNodeLookup")), {node_id: True})

    def test_node_settled_artifact_ref_payload_keeps_run_ui_running(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        self.window._active_run_id = "run_live"
        self.window._active_run_workspace_id = workspace_id
        self.window.run_projection_controller.set_run_ui_state("running", "Running", 1, 0, 0, 0)
        initial_output_text = self.window.console_panel.output_text
        initial_error_count = self.window.console_panel.error_count

        self.window.execution_event.emit(
            {
                "type": "node_settled",
                "status": "completed",
                "run_id": "run_live",
                "workspace_id": workspace_id,
                "node_id": "node_process",
                "outputs": _value_outputs(
                    stdout={
                        "__ea_runtime_value__": "artifact_ref",
                        "ref": "temp://stored_stdout",
                        "artifact_id": "stored_stdout",
                        "scope": "staged",
                    },
                    stderr={
                        "__ea_runtime_value__": "artifact_ref",
                        "ref": "temp://stored_stderr",
                        "artifact_id": "stored_stderr",
                        "scope": "staged",
                    },
                    exit_code=0,
                ),
            }
        )
        self.app.processEvents()

        self.assertEqual(self.window._active_run_id, "run_live")
        self.assertEqual(self.window._engine_state_value, "running")
        self.assertEqual(self.window.status_jobs.text(), "R:1 Q:0 D:0 F:0")
        self.assertEqual(self.window.console_panel.output_text, initial_output_text)
        self.assertEqual(self.window.console_panel.error_count, initial_error_count)
        self.assertEqual(self.window.run_state.active_run_id, "run_live")
        self.assertEqual(self.window.run_state.active_run_workspace_id, workspace_id)
        self.assertEqual(self.window.run_state.engine_state_value, "running")

    def test_new_run_clears_failed_node_highlight_before_start(self) -> None:
        execution_client = _ViewerExecutionClientStub(self.window.registry)
        self.window.execution_client = execution_client
        self.window.run_controller.set_auto_run_enabled(False)

        workspace_id = self.window.workspace_manager.active_workspace_id()
        failed_node_id = self.window.scene.add_node_from_type("core.logger", x=240.0, y=180.0)
        self.window.scene.set_node_title(failed_node_id, "Previous Failure")

        with patch.object(QMessageBox, "critical"):
            self.window._focus_failed_node(workspace_id, failed_node_id)
        self.app.processEvents()

        self.assertEqual(self.window.run_state.failed_node_id, failed_node_id)
        graph_canvas = self._graph_canvas_item()
        self.assertEqual(dict(graph_canvas.property("failedNodeLookup")), {failed_node_id: True})

        self.window.run_controller.run_workflow()
        self.app.processEvents()

        self.assertEqual(self.window.run_state.failed_node_id, "")
        self.assertEqual(self.window.run_state.failed_workspace_id, "")
        self.assertEqual(dict(graph_canvas.property("failedNodeLookup")), {})

    def test_developer_mode_toggle_is_gated_by_capability(self) -> None:
        self.assertFalse(self.window.run_state.developer_mode_active)
        with patch(
            "ea_node_editor.ui.shell.window_state.run_and_style_state.developer_mode_capability_enabled",
            return_value=False,
        ):
            self.window._toggle_developer_mode()
        self.assertFalse(self.window.run_state.developer_mode_active)

        with patch(
            "ea_node_editor.ui.shell.window_state.run_and_style_state.developer_mode_capability_enabled",
            return_value=True,
        ):
            self.window._toggle_developer_mode()
            self.assertTrue(self.window.run_state.developer_mode_active)
            self.window._toggle_developer_mode()
            self.assertFalse(self.window.run_state.developer_mode_active)

    def test_run_carries_developer_mode_only_when_capability_and_active(self) -> None:
        with patch.object(
            self.window.execution_client,
            "prepare_execution",
            wraps=self.window.execution_client.prepare_execution,
        ) as prepare_mock:
            with patch(
                "ea_node_editor.ui.shell.controllers.run_controller.developer_mode_capability_enabled",
                return_value=True,
            ):
                self.window.run_state.developer_mode_active = True
                self.window.run_controller.run_workflow()
        self.assertTrue(prepare_mock.call_args.args[0].trigger["developer_mode"])

        with patch.object(
            self.window.execution_client,
            "prepare_execution",
            wraps=self.window.execution_client.prepare_execution,
        ) as prepare_mock:
            with patch(
                "ea_node_editor.ui.shell.controllers.run_controller.developer_mode_capability_enabled",
                return_value=False,
            ):
                self.window.run_state.developer_mode_active = True
                self.window.run_controller.run_workflow()
        self.assertFalse(prepare_mock.call_args.args[0].trigger["developer_mode"])


class _SubprocessShellWindowTest(unittest.TestCase):
    __test__ = False

    def __init__(self, target: str) -> None:
        super().__init__(methodName="runTest")
        self._target = target

    def id(self) -> str:
        return self._target

    def __str__(self) -> str:
        return self._target

    def shortDescription(self) -> str:
        return self._target

    def runTest(self) -> None:
        target = ShellIsolationTarget(
            target_id=self._target,
            command=(sys.executable, "-c", _SHELL_TEST_RUNNER, self._target),
        )
        try:
            result = run_shell_isolation_target(target)
        except ShellIsolationTargetTimeout as exc:
            self.fail(str(exc))
        if result.returncode == 0:
            return
        self.fail(
            f"Subprocess shell test failed for {self._target} "
            f"(exit={result.returncode}).\n{format_child_output(result)}"
        )


def load_tests(loader: unittest.TestLoader, _tests, _pattern):  # noqa: ANN001
    suite = unittest.TestSuite()
    for test_name in loader.getTestCaseNames(ShellRunControllerTests):
        target = f"{ShellRunControllerTests.__module__}.{ShellRunControllerTests.__qualname__}.{test_name}"
        suite.addTest(_SubprocessShellWindowTest(target))
    return suite


if __name__ == "__main__":
    unittest.main()
