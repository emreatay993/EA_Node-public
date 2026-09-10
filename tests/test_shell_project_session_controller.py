from __future__ import annotations

import importlib
import gc
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from PyQt6.QtCore import QEvent, QUrl
from PyQt6.QtWidgets import QMessageBox

from ea_node_editor.addons.catalog import AddOnRegistration
from ea_node_editor.app_preferences import (
    default_app_preferences_document,
    set_addon_state,
)
from ea_node_editor.common.scene_protocol import ENGINEERING_VIEWER_BACKEND_ID
from ea_node_editor.execution.runtime import CorexRuntime
from ea_node_editor.execution.prepared_execution import InvalidationResult
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.nodes.plugin_contracts import (
    AddOnManifest,
    PluginAvailability,
    PluginBackendDescriptor,
    PluginDescriptor,
)
from ea_node_editor.common.artifact_refs import (
    format_managed_artifact_ref,
    format_staged_artifact_ref,
)
from ea_node_editor.persistence.artifact_store import (
    ProjectArtifactStore,
    format_workspace_artifact_folder,
)
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.persistence.solution_repository import SolutionRepositoryFactory
from ea_node_editor.ui.shell.composition import create_shell_window
from ea_node_editor.ui.shell.window import ShellWindow
from tests.main_window_shell.base import MainWindowShellTestBase
from tests.shell_isolation_runtime import format_child_output
from tests.shell_isolation_runtime import run_shell_isolation_target
from tests.shell_isolation_runtime import ShellIsolationTarget
from tests.shell_isolation_runtime import ShellIsolationTargetTimeout

_SCENARIO_ARG = "--scenario"
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FAKE_REOPEN_ADDON_ID = "tests.addons.reopen_lock"
_FAKE_REOPEN_BACKEND_MODULE = "tests.addons.reopen_lock.module"
_FAKE_REOPEN_NODE_TYPE_ID = "tests.addons.reopen_lock.node"


def _fake_reopen_plugin_descriptor() -> PluginDescriptor:
    class _FakeReopenPlugin:
        def spec(self) -> NodeTypeSpec:
            return NodeTypeSpec(
                type_id=_FAKE_REOPEN_NODE_TYPE_ID,
                display_name="Reopen Lock Node",
                category_path=("Tests", "Add-Ons"),
                icon="",
                ports=(
                    PortSpec(
                        "message",
                        "in",
                        "data",
                        "COREX.DataTypes.String",
                        "Message",
                        required=False,
                    ),
                ),
                properties=(PropertySpec("message", "str", "", "Message"),),
            )

        def execute(self, ctx):  # noqa: ANN001
            from ea_node_editor.nodes.execution_context import NodeResult

            return NodeResult()

    return PluginDescriptor(spec=_FakeReopenPlugin().spec(), factory=_FakeReopenPlugin)


def _fake_reopen_addon_registration() -> AddOnRegistration:
    return AddOnRegistration(
        manifest=AddOnManifest(
            addon_id=_FAKE_REOPEN_ADDON_ID,
            display_name="Reopen Lock Add-On",
            apply_policy="hot_apply",
            vendor="Tests",
            summary="Synthetic hot-apply add-on used for startup reopen coverage.",
            details="Provides a single synthetic node type for reopen-state regression coverage.",
        ),
        backend_module=_FAKE_REOPEN_BACKEND_MODULE,
        backend_id=_FAKE_REOPEN_ADDON_ID,
    )


def _fake_reopen_addon_module(registration: AddOnRegistration) -> SimpleNamespace:
    backend = PluginBackendDescriptor(
        plugin_id=registration.manifest.addon_id,
        display_name=registration.manifest.display_name,
        get_availability=lambda: PluginAvailability.available("ready"),
        load_descriptors=lambda: (_fake_reopen_plugin_descriptor(),),
        addon_manifest=registration.manifest,
    )
    return SimpleNamespace(PLUGIN_BACKENDS=(backend,))


class _ViewerExecutionClientStub:
    def __init__(self) -> None:
        self.open_calls: list[dict[str, Any]] = []
        self.start_calls: list[dict[str, Any]] = []
        self._callbacks: list[object] = []
        self._request_counter = 0
        self._solution_revisions: dict[str, int] = {}

    def subscribe(self, callback) -> None:  # noqa: ANN001
        self._callbacks.append(callback)

    def _next_request_id(self) -> str:
        self._request_counter += 1
        return f"viewer_open_{self._request_counter}"

    def open_viewer_session(
        self,
        *,
        workspace_id: str,
        node_id: str,
        session_id: str = "",
        backend_id: str = "",
        data_refs: dict[str, Any] | None = None,
        camera_state: dict[str, Any] | None = None,
        playback_state: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        **extra: Any,
    ) -> str:
        request_id = self._next_request_id()
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

    def start_run(
        self,
        project_path: str,
        workspace_id: str,
        trigger: dict[str, Any] | None = None,
        *,
        execution_backend: Any = None,
        target_node_ids: tuple[str, ...] = (),
        trigger_publications: dict[str, Any] | None = None,
        trigger_captures: dict[str, Any] | None = None,
        clicked_trigger_node_id: str = "",
    ) -> str:
        self.start_calls.append(
            {
                "project_path": project_path,
                "workspace_id": workspace_id,
                "trigger": dict(trigger or {}),
                "execution_backend": execution_backend,
                "target_node_ids": tuple(target_node_ids),
                "trigger_publications": dict(trigger_publications or {}),
                "trigger_captures": dict(trigger_captures or {}),
                "clicked_trigger_node_id": clicked_trigger_node_id,
            }
        )
        return f"run_{len(self.start_calls)}"

    def prepare_execution(self, request):  # noqa: ANN001, ANN201
        return SimpleNamespace(
            request=request,
            recompute_node_ids=tuple(request.target_node_ids),
        )

    def dispatch_prepared(self, prepared) -> str:  # noqa: ANN001
        request = prepared.request
        return self.start_run(
            str(request.project_path),
            request.workspace_id,
            dict(request.trigger),
            execution_backend=request.execution_backend,
            target_node_ids=tuple(request.target_node_ids),
            trigger_publications=dict(request.trigger_publications),
            trigger_captures=dict(request.trigger_captures),
            clicked_trigger_node_id=request.clicked_trigger_node_id,
        )

    def solution_facts(self, project_id: str, workspace_id: str):  # noqa: ANN201
        del project_id, workspace_id
        return ()

    def invalidate_solution(
        self,
        project_id: str,
        workspace_id: str,
        runtime_snapshot,
        changed_root_node_ids,
        reason_code: str,
    ) -> InvalidationResult:
        del runtime_snapshot
        revision = self._solution_revisions.get(workspace_id, 0) + 1
        self._solution_revisions[workspace_id] = revision
        roots = tuple(changed_root_node_ids)
        return InvalidationResult(
            project_id=project_id,
            workspace_id=workspace_id,
            solution_revision=revision,
            changed_root_node_ids=roots,
            expired_node_ids=roots,
            removed_node_ids=(),
            reason_code=reason_code,
        )

    def pause_run(self, run_id: str) -> None:
        return None

    def resume_run(self, run_id: str) -> None:
        return None

    def stop_run(self, run_id: str) -> None:
        return None

    def shutdown(self) -> None:
        return None


def _viewer_opened_event(
    *,
    request_id: str,
    workspace_id: str,
    node_id: str,
    session_id: str,
    **overrides: Any,
) -> dict[str, Any]:
    summary = {
        "cache_state": "live_ready",
        "result_name": "Displacement",
        "set_label": "Set 4",
    }
    summary.update(dict(overrides.pop("summary", {})))
    options = {
        "session_state": "open",
        "cache_state": summary["cache_state"],
        "playback_state": "paused",
        "step_index": 4,
        "live_mode": "full",
    }
    options.update(dict(overrides.pop("options", {})))
    payload = {
        "type": "viewer_session_opened",
        "request_id": request_id,
        "workspace_id": workspace_id,
        "node_id": node_id,
        "session_id": session_id,
        "data_refs": dict(overrides.pop("data_refs", {})),
        "summary": summary,
        "options": options,
    }
    payload.update(overrides)
    return payload


def _run_named_scenario(name: str) -> int:
    suite = unittest.TestSuite([_ShellProjectSessionControllerScenarios(name)])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


class _ShellProjectSessionControllerScenarios(MainWindowShellTestBase):
    __test__ = False

    def setUp(self) -> None:
        super().setUp()
        self.window.autosave_timer.stop()

    def tearDown(self) -> None:
        app = self.app
        try:
            super().tearDown()
        finally:
            for widget in list(app.topLevelWidgets()):
                widget.close()
                widget.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            gc.collect()

    def _dispose_secondary_window(self, window: ShellWindow) -> None:
        for timer_name in ("metrics_timer", "graph_hint_timer", "autosave_timer"):
            timer = getattr(window, timer_name, None)
            if timer is not None:
                timer.stop()
        window.close()
        quick_widget = getattr(window, "quick_widget", None)
        if quick_widget is not None:
            window.takeCentralWidget()
            quick_widget.setSource(QUrl())
            quick_widget.hide()
            quick_widget.deleteLater()
            window.quick_widget = None
        window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def _workspace_relative(
        self, relative_path: str, *, workspace_id: str | None = None
    ) -> str:
        normalized_workspace_id = (
            workspace_id or self.window.workspace_manager.active_workspace_id()
        )
        workspace = self.window.model.project.workspaces.get(normalized_workspace_id)
        workspace_folder = format_workspace_artifact_folder(
            workspace_id=normalized_workspace_id,
            workspace_name=str(getattr(workspace, "name", "") or ""),
        )
        return f"workspaces/{workspace_folder}/{relative_path}"

    def _workspace_path(
        self, sidecar_root: Path, relative_path: str, *, workspace_id: str | None = None
    ) -> Path:
        return sidecar_root.joinpath(
            *Path(
                self._workspace_relative(relative_path, workspace_id=workspace_id)
            ).parts
        )

    def _add_browse_media_panel(self, *, x: float, y: float) -> str:
        node_id = self.window.scene.add_node_from_type("media.panel", x=x, y=y)
        self.window.scene.set_exposed_port(node_id, "source", False)
        return node_id

    def _install_solution_save_runtime(self) -> None:
        runtime = CorexRuntime(
            registry=self.window.registry,
            solution_repository_factory=SolutionRepositoryFactory(),
        )
        project = self.window.model.project
        runtime.reset_project_session(project.project_id, self.window.project_path)
        runtime.bind_project_solution_store(
            project.project_id,
            self.window.project_path,
            project.metadata.get("solution_store"),
        )
        self.window.execution_client = runtime
        self.addCleanup(runtime.shutdown)

    def _attach_unsaved_staged_output(self) -> tuple[str, str, Path]:
        artifact_id = "pending_output"
        staged_ref = format_staged_artifact_ref(artifact_id)
        staging_root = (
            self._session_path.parent / "project_artifact_staging" / "project-123"
        )
        staged_path = (
            staging_root
            / "nodes"
            / "Image Panel [11111111]"
            / "tmp"
            / "out"
            / "outputs"
            / "run.txt"
        )
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_text("staged output", encoding="utf-8")
        node_id = self._add_browse_media_panel(x=40.0, y=60.0)
        self.window.scene.set_node_property(node_id, "source", staged_ref)
        self.window.model.project.metadata["artifact_store"] = {
            "staging_root": {
                "kind": "session_temp",
                "absolute_path": str(staging_root),
            },
            "staged": {
                artifact_id: {
                    "relative_path": "nodes/Image Panel [11111111]/tmp/out/outputs/run.txt",
                    "slot": "process_run.stdout",
                }
            },
        }
        self.app.processEvents()
        return node_id, staged_ref, staged_path

    def _write_session_payload(
        self,
        *,
        project_path: str = "",
        last_manual_save_ts: float = 0.0,
        recent_project_paths: list[str] | None = None,
    ) -> None:
        self._session_path.write_text(
            json.dumps(
                {
                    "project_path": project_path,
                    "last_manual_save_ts": last_manual_save_ts,
                    "recent_project_paths": list(recent_project_paths or []),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def _seed_saved_session_from_current_project(
        self, filename: str
    ) -> tuple[Path, dict[str, object]]:
        project_path = Path(self._temp_dir.name) / "projects" / filename
        project_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_doc = self.window.serializer.to_document(self.window.model.project)
        self.window.serializer.save_document(str(project_path), baseline_doc)
        saved_path = project_path.with_suffix(".cxproj")
        self._write_session_payload(
            project_path=str(saved_path),
            last_manual_save_ts=saved_path.stat().st_mtime,
        )
        return saved_path, baseline_doc

    def _assert_absent_or_current_autosave(self, window: ShellWindow) -> None:
        if not self._autosave_path.exists():
            return
        autosave_doc = json.loads(self._autosave_path.read_text(encoding="utf-8"))
        self.assertEqual(
            autosave_doc, window.serializer.to_document(window.model.project)
        )

    def test_open_project_rejects_saved_node_when_startup_preferences_disable_addon(
        self,
    ) -> None:
        registration = _fake_reopen_addon_registration()
        fake_module = _fake_reopen_addon_module(registration)
        disabled_preferences = set_addon_state(
            default_app_preferences_document(),
            registration.manifest.addon_id,
            enabled=False,
            pending_restart=False,
        )
        real_import_module = importlib.import_module

        def _import_fake_module(module_name: str):
            if module_name == registration.backend_module:
                return fake_module
            return real_import_module(module_name)

        project_path = (
            Path(self._temp_dir.name) / "projects" / "disabled_addon_reopen.cxproj"
        )
        project_path.parent.mkdir(parents=True, exist_ok=True)

        with (
            patch(
                "ea_node_editor.addons.catalog.REGISTERED_ADDON_REGISTRATIONS",
                (registration,),
            ),
            patch(
                "ea_node_editor.addons.catalog.importlib.import_module",
                side_effect=_import_fake_module,
            ),
        ):
            enabled_registry = build_default_registry()
            self.assertIsNotNone(
                enabled_registry.spec_or_none(_FAKE_REOPEN_NODE_TYPE_ID)
            )
            serializer = JsonProjectSerializer(enabled_registry)
            model = GraphModel()
            workspace = model.active_workspace
            node = model.add_node(
                workspace.workspace_id,
                _FAKE_REOPEN_NODE_TYPE_ID,
                "Reopen Lock Node",
                120.0,
                80.0,
                properties={"message": "locked"},
            )
            serializer.save_document(
                str(project_path), serializer.to_document(model.project)
            )

            reopened_window = create_shell_window(
                preferences_document=disabled_preferences
            )
            reopened_window.resize(1200, 800)
            reopened_window.show()
            self.app.processEvents()
            try:
                for workspace in reopened_window.model.project.workspaces.values():
                    workspace.dirty = False
                self.assertFalse(
                    reopened_window.project_session_controller.open_project_path(
                        str(project_path),
                        show_errors=False,
                    )
                )
                self.app.processEvents()

                reopened_workspace = reopened_window.model.active_workspace
                self.assertNotIn(node.node_id, reopened_workspace.nodes)
                self.assertEqual(reopened_workspace.nodes, {})
            finally:
                self._dispose_secondary_window(reopened_window)

    def test_saved_project_reopen_seeds_run_required_viewer_projection_without_persisting_live_transport(
        self,
    ) -> None:
        self.window.execution_client = _ViewerExecutionClientStub()
        bridge = self.window.viewer_session_bridge
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("model.viewer", x=80.0, y=60.0)
        session_id = bridge.open(
            node_id,
            {
                "data_refs": {
                    "fields": {"kind": "handle_ref", "handle_id": "handle::fields"}
                },
                "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
                "camera_state": {"zoom": 1.5},
                "playback_state": {"state": "paused", "step_index": 4},
                "summary": {
                    "result_name": "Displacement",
                    "set_label": "Set 4",
                },
                "options": {"live_mode": "full"},
            },
        )
        open_call = self.window.execution_client.open_calls[-1]
        bundle_path = Path(self._temp_dir.name) / "viewer_bundle" / "bundle.vtp"
        self.window.execution_event.emit(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=session_id,
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                transport_revision=9,
                live_open_status="ready",
                transport={
                    "kind": "bundle",
                    "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
                    "bundle_path": str(bundle_path),
                },
                camera_state={"zoom": 1.5},
                data_refs={
                    "fields": {"kind": "handle_ref", "handle_id": "handle::fields"}
                },
            )
        )
        self.app.processEvents()

        project_path = (
            Path(self._temp_dir.name) / "projects" / "viewer_projection_restore.cxproj"
        )
        project_path.parent.mkdir(parents=True, exist_ok=True)
        self.window.serializer.save_document(
            str(project_path),
            self.window.serializer.to_document(self.window.model.project),
        )
        saved_text = project_path.read_text(encoding="utf-8")
        self.assertNotIn(str(bundle_path), saved_text)
        self.assertNotIn("bundle_path", saved_text)
        self.window.execution_client.start_calls.clear()
        with patch.object(
            self.window.project_session_controller._document_service,
            "_confirm_project_replacement",
            return_value=True,
        ):
            self.assertTrue(self.window._open_project_path(str(project_path)))
        self.app.processEvents()

        self.assertEqual(len(self.window.execution_client.start_calls), 1)

        reopened_state = bridge.session_state(node_id)
        self.assertEqual(reopened_state["phase"], "blocked")
        self.assertEqual(reopened_state["backend_id"], ENGINEERING_VIEWER_BACKEND_ID)
        self.assertEqual(reopened_state["transport_revision"], 9)
        self.assertEqual(reopened_state["live_open_status"], "blocked")
        self.assertTrue(reopened_state["live_open_blocker"]["rerun_required"])
        self.assertEqual(
            reopened_state["summary"]["live_transport_release_reason"],
            "project_reload",
        )
        self.assertEqual(
            reopened_state["transport"],
            {"kind": "bundle", "backend_id": ENGINEERING_VIEWER_BACKEND_ID},
        )
        self.assertEqual(reopened_state["data_refs"], {})

    def test_session_restore_recovers_workspace_order_active_workspace_and_view_camera(
        self,
    ) -> None:
        first_workspace_id = self.window.workspace_manager.active_workspace_id()
        second_workspace_id = self.window.workspace_manager.create_workspace("Second")
        third_workspace_id = self.window.workspace_manager.create_workspace("Third")
        self.window.workspace_manager.move_workspace(2, 1)
        self.window.workspace_navigation_controller.refresh_workspace_tabs()

        self.window.workspace_navigation_controller.switch_workspace(third_workspace_id)
        third_v2_id = self.window.workspace_manager.create_view(
            third_workspace_id, name="V2"
        )
        self.window.workspace_navigation_controller.switch_view(third_v2_id)
        self.window.view.set_zoom(1.65)
        self.window.view.centerOn(222.0, -111.0)
        self.window._persist_session()
        self.app.processEvents()

        expected_order = [
            self.window.workspace_tabs.tabData(index)
            for index in range(self.window.workspace_tabs.count())
        ]
        self.assertEqual(
            expected_order,
            [first_workspace_id, third_workspace_id, second_workspace_id],
        )

        restored = ShellWindow()
        restored.resize(1200, 800)
        restored.show()
        self.app.processEvents()
        try:
            restored_order = [
                restored.workspace_tabs.tabData(index)
                for index in range(restored.workspace_tabs.count())
            ]
            self.assertEqual(restored_order, expected_order)
            self.assertEqual(
                restored.workspace_manager.active_workspace_id(), third_workspace_id
            )
            self.assertEqual(
                restored.model.project.workspaces[third_workspace_id].active_view_id,
                third_v2_id,
            )
            self.assertAlmostEqual(restored.view.zoom, 1.65, places=2)
            self.assertAlmostEqual(restored.view.center_x, 222.0, delta=3.0)
            self.assertAlmostEqual(restored.view.center_y, -111.0, delta=3.0)
        finally:
            self._dispose_secondary_window(restored)

    def test_autosave_tick_writes_snapshot_and_keeps_valid_project_doc(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.constant", x=5.0, y=7.0)
        self.app.processEvents()

        self.window._autosave_tick()
        self.assertTrue(self._autosave_path.exists())
        self.assertTrue(self.window.project_session_state.last_autosave_fingerprint)
        session_payload = json.loads(self._session_path.read_text(encoding="utf-8"))
        self.assertNotIn("project_doc", session_payload)

        autosave_doc = json.loads(self._autosave_path.read_text(encoding="utf-8"))
        workspace_docs = {
            workspace["workspace_id"]: workspace
            for workspace in autosave_doc.get("workspaces", [])
        }
        self.assertIn(workspace_id, workspace_docs)
        saved_nodes = {
            node["node_id"] for node in workspace_docs[workspace_id].get("nodes", [])
        }
        self.assertIn(node_id, saved_nodes)

    def test_session_restore_recovers_unsaved_temp_staged_refs_without_autosave(
        self,
    ) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        active_node_id = self.window.scene.add_node_from_type(
            "core.constant", x=10.0, y=20.0
        )
        node_id, staged_ref, staged_path = self._attach_unsaved_staged_output()
        self.window._persist_session()
        session_payload = json.loads(self._session_path.read_text(encoding="utf-8"))
        self.assertNotIn("project_doc", session_payload)

        execution_client = _ViewerExecutionClientStub()
        with patch(
            "ea_node_editor.ui.shell.composition.controllers._create_shell_execution_client",
            return_value=execution_client,
        ):
            restored = ShellWindow()
        restored.resize(1200, 800)
        restored.show()
        self.app.processEvents()
        try:
            restored_workspace = restored.model.project.workspaces[workspace_id]
            self.assertEqual(
                restored_workspace.nodes[node_id].properties["source"], staged_ref
            )
            store = ProjectArtifactStore.from_project_metadata(
                project_path=restored.project_path,
                project_metadata=restored.model.project.metadata,
            )
            self.assertEqual(store.resolve_staged_path(staged_ref), staged_path)
            self.assertEqual(len(execution_client.start_calls), 1)
            self.assertEqual(
                set(execution_client.start_calls[0]["target_node_ids"]),
                {active_node_id, node_id},
            )
        finally:
            self._dispose_secondary_window(restored)

    def test_recovery_prompt_accept_loads_newer_autosave(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        _saved_path, _baseline_doc = self._seed_saved_session_from_current_project(
            "recovery_accept.cxproj"
        )

        recovered_node_id = self.window.scene.add_node_from_type(
            "core.constant", x=20.0, y=30.0
        )
        recovered_doc = self.window.serializer.to_document(self.window.model.project)
        self._autosave_path.write_text(
            json.dumps(recovered_doc, indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )

        execution_client = _ViewerExecutionClientStub()
        with (
            patch.object(
                ShellWindow,
                "_prompt_recover_autosave",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "ea_node_editor.ui.shell.composition.controllers._create_shell_execution_client",
                return_value=execution_client,
            ),
        ):
            restored = ShellWindow()
            restored.resize(1200, 800)
            restored.show()
            self.app.processEvents()
            try:
                restored_workspace = restored.model.project.workspaces[workspace_id]
                self.assertIn(recovered_node_id, restored_workspace.nodes)
                self._assert_absent_or_current_autosave(restored)
                self.assertEqual(len(execution_client.start_calls), 1)
                self.assertEqual(
                    execution_client.start_calls[0]["target_node_ids"],
                    (recovered_node_id,),
                )
            finally:
                self._dispose_secondary_window(restored)

    def test_recovery_prompt_accept_recovers_unsaved_temp_staged_refs(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        _saved_path, _baseline_doc = self._seed_saved_session_from_current_project(
            "recovery_accept_staged.cxproj"
        )
        node_id, staged_ref, staged_path = self._attach_unsaved_staged_output()
        autosave_doc = self.window.serializer.to_document(self.window.model.project)
        self._autosave_path.write_text(
            json.dumps(autosave_doc, indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )

        with patch.object(
            ShellWindow,
            "_prompt_recover_autosave",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            restored = ShellWindow()
            restored.resize(1200, 800)
            restored.show()
            self.app.processEvents()
            try:
                restored_workspace = restored.model.project.workspaces[workspace_id]
                self.assertEqual(
                    restored_workspace.nodes[node_id].properties["source"],
                    staged_ref,
                )
                store = ProjectArtifactStore.from_project_metadata(
                    project_path=restored.project_path,
                    project_metadata=restored.model.project.metadata,
                )
                self.assertEqual(store.resolve_staged_path(staged_ref), staged_path)
                self._assert_absent_or_current_autosave(restored)
            finally:
                self._dispose_secondary_window(restored)

    def test_recovery_prompt_reject_keeps_empty_startup_project_and_discards_autosave(
        self,
    ) -> None:
        baseline_node_id = self.window.scene.add_node_from_type(
            "core.constant", x=10.0, y=10.0
        )
        _saved_path, _baseline_doc = self._seed_saved_session_from_current_project(
            "recovery_reject.cxproj"
        )

        self.window.scene.add_node_from_type("core.logger", x=120.0, y=10.0)
        autosave_doc = self.window.serializer.to_document(self.window.model.project)
        self._autosave_path.write_text(
            json.dumps(autosave_doc, indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )

        with patch.object(
            ShellWindow,
            "_prompt_recover_autosave",
            return_value=QMessageBox.StandardButton.No,
        ):
            restored = ShellWindow()
            restored.resize(1200, 800)
            restored.show()
            self.app.processEvents()
            try:
                restored_workspace = restored.model.project.workspaces[
                    restored.workspace_manager.active_workspace_id()
                ]
                self.assertNotIn(baseline_node_id, restored_workspace.nodes)
                self.assertEqual(restored.project_path, "")
                self.assertFalse(self._autosave_path.exists())
            finally:
                self._dispose_secondary_window(restored)

    def test_session_restore_keeps_saved_project_recent_but_starts_empty(self) -> None:
        saved_node_id = self.window.scene.add_node_from_type(
            "core.constant", x=10.0, y=10.0
        )
        saved_path, baseline_doc = self._seed_saved_session_from_current_project(
            "recovery_skip_prompt.cxproj"
        )
        self._autosave_path.write_text(
            json.dumps(baseline_doc, indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )

        with patch.object(ShellWindow, "_prompt_recover_autosave") as prompt:
            restored = ShellWindow()
            restored.resize(1200, 800)
            restored.show()
            self.app.processEvents()
            try:
                self.assertEqual(prompt.call_count, 0)
                self.assertEqual(restored.project_path, "")
                self.assertEqual(restored.recent_project_paths[0], str(saved_path))
                restored_workspace = restored.model.project.workspaces[
                    restored.workspace_manager.active_workspace_id()
                ]
                self.assertNotIn(saved_node_id, restored_workspace.nodes)
            finally:
                self._dispose_secondary_window(restored)

    def test_restore_session_handles_corrupted_session_and_autosave_files(self) -> None:
        self._session_path.write_text("{bad json", encoding="utf-8")
        self._autosave_path.write_text("{bad json", encoding="utf-8")
        os.utime(self._autosave_path, None)

        with patch.object(
            ShellWindow,
            "_prompt_recover_autosave",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            restored = ShellWindow()
            restored.resize(1200, 800)
            restored.show()
            self.app.processEvents()
            try:
                self.assertGreaterEqual(len(restored.model.project.workspaces), 1)
                self.assertFalse(self._autosave_path.exists())
            finally:
                self._dispose_secondary_window(restored)

    def test_recovery_prompt_is_deferred_until_main_window_is_visible(self) -> None:
        _saved_path, _baseline_doc = self._seed_saved_session_from_current_project(
            "recovery_deferred.cxproj"
        )

        self.window.scene.add_node_from_type("core.constant", x=20.0, y=30.0)
        recovered_doc = self.window.serializer.to_document(self.window.model.project)
        self._autosave_path.write_text(
            json.dumps(recovered_doc, indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )

        with patch.object(
            ShellWindow,
            "_prompt_recover_autosave",
            return_value=QMessageBox.StandardButton.No,
        ) as prompt:
            restored = ShellWindow()
            self.assertEqual(prompt.call_count, 0)
            restored.resize(1200, 800)
            restored.show()
            self.app.processEvents()
            try:
                self.assertGreaterEqual(prompt.call_count, 1)
                self.assertFalse(self._autosave_path.exists())
            finally:
                self._dispose_secondary_window(restored)

    def test_clean_close_discards_staged_scratch_and_clears_unsaved_root_hint(
        self,
    ) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id, staged_ref, staged_path = self._attach_unsaved_staged_output()

        self.window.close()
        self.app.processEvents()

        self.assertFalse(staged_path.exists())
        self.assertFalse(self._autosave_path.exists())

        with patch.object(ShellWindow, "_prompt_recover_autosave") as prompt:
            restored = ShellWindow()
            restored.resize(1200, 800)
            restored.show()
            self.app.processEvents()
            try:
                restored_workspace = restored.model.project.workspaces[
                    restored.workspace_manager.active_workspace_id()
                ]
                self.assertNotIn(node_id, restored_workspace.nodes)
                store = ProjectArtifactStore.from_project_metadata(
                    project_path=restored.project_path,
                    project_metadata=restored.model.project.metadata,
                )
                self.assertIsNone(store.resolve_staged_path(staged_ref))
                self.assertNotIn(
                    "staging_root",
                    restored.model.project.metadata.get("artifact_store", {}),
                )
                self.assertEqual(prompt.call_count, 0)
            finally:
                self._dispose_secondary_window(restored)

    def test_explicit_save_promotes_referenced_staged_refs(
        self,
    ) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id, _staged_ref, staged_path = self._attach_unsaved_staged_output()
        save_target = Path(self._temp_dir.name) / "projects" / "saved_project"
        save_target.parent.mkdir(parents=True, exist_ok=True)
        saved_path = save_target.with_suffix(".cxproj")
        sidecar_root = saved_path.with_name("saved_project.data")
        self.window.model.project.metadata["artifact_store"]["artifacts"] = {
            "pending_output": {
                "relative_path": "nodes/Image Panel [11111111]/out/outputs/run.txt",
            },
        }

        self._install_solution_save_runtime()
        with (
            patch.object(
                self.window.project_session_controller._project_files_service,
                "prompt_project_files_action",
                return_value=True,
            ),
            patch(
                "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                return_value=(str(save_target), "COREX Project (*.cxproj)"),
            ),
            patch("PyQt6.QtWidgets.QMessageBox.warning"),
        ):
            result = self.window.project_session_controller.save_project()
        self.assertEqual(result.status, "saved", result.reason_code)
        self.app.processEvents()

        workspace = self.window.model.project.workspaces[workspace_id]
        saved_doc = json.loads(saved_path.read_text(encoding="utf-8"))
        workspace_doc = next(
            item
            for item in saved_doc["workspaces"]
            if item["workspace_id"] == workspace_id
        )
        saved_node = next(
            item for item in workspace_doc["nodes"] if item["node_id"] == node_id
        )

        self.assertEqual(self.window.project_path, str(saved_path))
        self.assertEqual(
            workspace.nodes[node_id].properties["source"],
            format_managed_artifact_ref("pending_output"),
        )
        self.assertEqual(
            saved_node["properties"]["source"],
            format_managed_artifact_ref("pending_output"),
        )
        artifact_store = saved_doc["metadata"]["artifact_store"]
        managed_path = sidecar_root.joinpath(
            *Path(
                artifact_store["artifacts"]["pending_output"]["relative_path"]
            ).parts
        )
        self.assertEqual(managed_path.read_text(encoding="utf-8"), "staged output")
        self.assertEqual(staged_path.read_text(encoding="utf-8"), "staged output")
        self.assertEqual(artifact_store["staged"], {})
        self.assertEqual(
            artifact_store["artifacts"]["pending_output"]["slot"], "process_run.stdout"
        )

    def test_save_as_default_copy_switches_project_path_and_excludes_staging(
        self,
    ) -> None:
        managed_artifact_id = "managed_image"
        managed_ref = format_managed_artifact_ref(managed_artifact_id)
        source_project = (
            Path(self._temp_dir.name) / "projects" / "source_project.cxproj"
        )
        managed_path = (
            source_project.with_name("source_project.data")
            / "nodes"
            / "Image Panel [11111111]"
            / "in"
            / "media"
            / "diagram.png"
        )
        managed_path.parent.mkdir(parents=True, exist_ok=True)
        managed_path.write_text("managed image", encoding="utf-8")

        staging_root = (
            self._session_path.parent / "project_artifact_staging" / "save-as-project"
        )
        staged_path = (
            staging_root
            / "nodes"
            / "Image Panel - Staged [22222222]"
            / "tmp"
            / "out"
            / "outputs"
            / "run.txt"
        )
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_text("staged output", encoding="utf-8")

        self.window.project_path = str(source_project)
        managed_node_id = self._add_browse_media_panel(x=40.0, y=60.0)
        self.window.scene.set_node_property(managed_node_id, "source", managed_ref)
        staged_node_id = self._add_browse_media_panel(x=220.0, y=60.0)
        self.window.scene.set_node_property(
            staged_node_id, "source", format_staged_artifact_ref("pending_output")
        )
        self.window.model.project.metadata["artifact_store"] = {
            "artifacts": {
                managed_artifact_id: {
                    "relative_path": "nodes/Image Panel [11111111]/in/media/diagram.png",
                }
            },
            "staging_root": {
                "kind": "session_temp",
                "absolute_path": str(staging_root),
            },
            "staged": {
                "pending_output": {
                    "relative_path": "nodes/Image Panel - Staged [22222222]/tmp/out/outputs/run.txt",
                    "slot": "process_run.stdout",
                }
            },
        }

        save_target = Path(self._temp_dir.name) / "copies" / "cloned_project"
        stale_managed_path = (
            save_target.with_suffix(".data")
            / "nodes"
            / "Old Node [99999999]"
            / "out"
            / "stale.txt"
        )
        stale_staging_path = (
            save_target.with_suffix(".data")
            / "nodes"
            / "Old Node [99999999]"
            / "tmp"
            / "out"
            / "outputs"
            / "old.txt"
        )
        save_target.parent.mkdir(parents=True, exist_ok=True)

        self._install_solution_save_runtime()
        with (
            patch.object(
                self.window.project_session_controller._project_files_service,
                "prompt_project_files_action",
                return_value=True,
            ),
            patch(
                "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                return_value=(str(save_target), "COREX Project (*.cxproj)"),
            ),
        ):
            self.window._save_project_as()
        self.app.processEvents()

        saved_path = save_target.with_suffix(".cxproj")
        saved_doc = json.loads(saved_path.read_text(encoding="utf-8"))
        target_sidecar = saved_path.with_name("cloned_project.data")
        copied_managed_path = self._workspace_path(
            target_sidecar,
            "nodes/Image Panel [11111111]/in/media/diagram.png",
        )
        copied_output_path = self._workspace_path(
            target_sidecar,
            "nodes/Image Panel - Staged [22222222]/out/outputs/run.txt",
        )
        copied_temp_path = self._workspace_path(
            target_sidecar,
            "nodes/Image Panel - Staged [22222222]/tmp/out/outputs/run.txt",
        )

        self.assertEqual(
            self.window.action_save_project_as.text(), "Save Project As..."
        )
        self.assertEqual(self.window.project_path, str(saved_path))
        self.assertEqual(
            copied_managed_path.read_text(encoding="utf-8"), "managed image"
        )
        self.assertEqual(
            copied_output_path.read_text(encoding="utf-8"), "staged output"
        )
        self.assertFalse(copied_temp_path.exists())
        self.assertFalse(stale_managed_path.exists())
        self.assertFalse(stale_staging_path.exists())
        self.assertTrue(staged_path.exists())
        artifact_store = saved_doc["metadata"]["artifact_store"]
        self.assertEqual(artifact_store["staged"], {})
        self.assertEqual(
            artifact_store["artifacts"][managed_artifact_id]["relative_path"],
            self._workspace_relative(
                "nodes/Image Panel [11111111]/in/media/diagram.png"
            ),
        )
        self.assertEqual(
            artifact_store["artifacts"]["pending_output"]["relative_path"],
            self._workspace_relative(
                "nodes/Image Panel - Staged [22222222]/out/outputs/run.txt"
            ),
        )
        self.assertEqual(
            artifact_store["artifacts"]["pending_output"]["slot"], "process_run.stdout"
        )
        workspace_doc = next(
            item
            for item in saved_doc["workspaces"]
            if item["workspace_id"]
            == self.window.workspace_manager.active_workspace_id()
        )
        saved_nodes = {node["node_id"]: node for node in workspace_doc["nodes"]}
        self.assertEqual(
            saved_nodes[managed_node_id]["properties"]["source"], managed_ref
        )
        self.assertEqual(
            saved_nodes[staged_node_id]["properties"]["source"],
            format_managed_artifact_ref("pending_output"),
        )

    def test_new_project_uses_navigation_controller_surface_without_workspace_library_facade(
        self,
    ) -> None:
        original_save_active_view_state = (
            self.window.workspace_navigation_controller.save_active_view_state
        )
        original_refresh_workspace_tabs = (
            self.window.workspace_navigation_controller.refresh_workspace_tabs
        )
        original_switch_workspace = (
            self.window.workspace_navigation_controller.switch_workspace
        )
        save_calls: list[str] = []
        refresh_calls: list[str] = []
        switch_calls: list[str] = []

        def _record_save_active_view_state() -> None:
            save_calls.append("save")
            original_save_active_view_state()

        def _record_refresh_workspace_tabs() -> None:
            refresh_calls.append("refresh")
            original_refresh_workspace_tabs()

        def _record_switch_workspace(workspace_id: str) -> None:
            switch_calls.append(str(workspace_id))
            original_switch_workspace(workspace_id)

        for workspace in self.window.model.project.workspaces.values():
            workspace.dirty = False
        self.assertFalse(hasattr(self.window, "workspace_library_controller"))
        with (
            patch.object(
                self.window.workspace_navigation_controller,
                "save_active_view_state",
                side_effect=_record_save_active_view_state,
            ),
            patch.object(
                self.window.workspace_navigation_controller,
                "refresh_workspace_tabs",
                side_effect=_record_refresh_workspace_tabs,
            ),
            patch.object(
                self.window.workspace_navigation_controller,
                "switch_workspace",
                side_effect=_record_switch_workspace,
            ),
        ):
            self.window.project_session_controller.new_project()
            self.app.processEvents()

        self.assertGreaterEqual(len(save_calls), 1)
        self.assertGreaterEqual(len(refresh_calls), 1)
        self.assertGreaterEqual(len(switch_calls), 1)
        self.assertEqual(self.window.project_path, "")
        self.assertEqual(self.window.model.project.name, "untitled")

    def test_project_files_menu_action_triggers_dialog(self) -> None:
        with patch.object(
            self.window.project_session_controller, "show_project_files_dialog"
        ) as show_dialog:
            self.window.action_project_files.trigger()
            self.app.processEvents()

        self.assertEqual(self.window.action_project_files.text(), "Project Files...")
        self.assertEqual(show_dialog.call_count, 1)


    def test_save_prompt_receives_project_file_summary_before_saving(self) -> None:
        self._attach_unsaved_staged_output()
        missing_path = str(Path(self._temp_dir.name) / "missing-image.png")
        broken_node_id = self._add_browse_media_panel(x=220.0, y=160.0)
        self.window.scene.set_node_property(broken_node_id, "source", missing_path)
        save_target = Path(self._temp_dir.name) / "projects" / "prompted_save"

        self._install_solution_save_runtime()
        with (
            patch.object(
                self.window.project_session_controller._project_files_service,
                "prompt_project_files_action",
                return_value=True,
            ) as prompt,
            patch(
                "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                return_value=(str(save_target), "COREX Project (*.cxproj)"),
            ),
            patch("PyQt6.QtWidgets.QMessageBox.warning"),
        ):
            self.window._save_project()
        self.app.processEvents()

        self.assertEqual(prompt.call_count, 1)
        snapshot = prompt.call_args.kwargs["snapshot"]
        self.assertEqual(snapshot.staged_count, 1)
        self.assertEqual(snapshot.broken_count, 1)

    def test_open_project_path_can_abort_when_project_files_summary_has_staged_and_broken_entries(
        self,
    ) -> None:
        baseline_node_id = self.window.scene.add_node_from_type(
            "core.constant", x=20.0, y=20.0
        )
        self.app.processEvents()

        project_path = (
            Path(self._temp_dir.name) / "projects" / "open_with_summary.cxproj"
        )
        project_path.parent.mkdir(parents=True, exist_ok=True)

        model = GraphModel()
        workspace = model.active_workspace
        model.add_node(
            workspace.workspace_id,
            "media.panel",
            "Broken",
            220.0,
            60.0,
            properties={
                "source": str(Path(self._temp_dir.name) / "missing-open-image.png")
            },
            exposed_ports={"source": False},
        )
        self.window.serializer.save_document(
            str(project_path), self.window.serializer.to_document(model.project)
        )

        with (
            patch.object(
                self.window.project_session_controller._document_service,
                "_confirm_project_replacement",
                return_value=True,
            ),
            patch.object(
                self.window.project_session_controller._project_files_service,
                "prompt_project_files_action",
                return_value=False,
            ) as prompt,
        ):
            result = self.window._open_project_path(str(project_path))
        self.app.processEvents()

        self.assertFalse(result)
        self.assertEqual(prompt.call_count, 1)
        snapshot = prompt.call_args.kwargs["snapshot"]
        self.assertEqual(snapshot.staged_count, 0)
        self.assertEqual(snapshot.broken_count, 1)
        workspace = self.window.model.project.workspaces[
            self.window.workspace_manager.active_workspace_id()
        ]
        self.assertIn(baseline_node_id, workspace.nodes)

    def test_recovery_prompt_receives_project_file_summary_for_recovered_project(
        self,
    ) -> None:
        recovered_project_path = (
            Path(self._temp_dir.name) / "projects" / "recovered_project.cxproj"
        )
        recovered_staging_path = (
            recovered_project_path.with_name("recovered_project.data")
            / "nodes"
            / "Image Panel - Recovered Staged [44444444]"
            / "tmp"
            / "out"
            / "outputs"
            / "run.txt"
        )
        recovered_staging_path.parent.mkdir(parents=True, exist_ok=True)
        recovered_staging_path.write_text("staged output", encoding="utf-8")
        self.window.project_path = str(recovered_project_path)

        recovered_model = GraphModel()
        workspace = recovered_model.active_workspace
        recovered_model.add_node(
            workspace.workspace_id,
            "media.panel",
            "Recovered Staged",
            80.0,
            60.0,
            properties={"source": format_staged_artifact_ref("pending_output")},
            exposed_ports={"source": False},
        )
        recovered_model.add_node(
            workspace.workspace_id,
            "media.panel",
            "Recovered Broken",
            220.0,
            60.0,
            properties={
                "source": str(
                    Path(self._temp_dir.name) / "missing-recovered-image.png"
                )
            },
            exposed_ports={"source": False},
        )
        recovered_model.project.metadata = {
            "artifact_store": {
                "staged": {
                    "pending_output": {
                        "relative_path": "nodes/Image Panel - Recovered Staged [44444444]/tmp/out/outputs/run.txt",
                        "slot": "process_run.stdout",
                    }
                }
            }
        }

        with patch.object(
            self.window.project_session_controller._project_files_service,
            "prompt_project_files_action",
            return_value=True,
        ) as prompt:
            choice = self.window.project_session_controller.prompt_recover_autosave(
                recovered_model.project
            )

        self.assertEqual(choice, QMessageBox.StandardButton.Yes)
        self.assertEqual(prompt.call_count, 1)
        snapshot = prompt.call_args.kwargs["snapshot"]
        self.assertEqual(snapshot.staged_count, 1)
        self.assertEqual(snapshot.broken_count, 1)


class ShellProjectSessionControllerTests(unittest.TestCase):
    maxDiff = None

    def _run_scenario(self, scenario_name: str) -> None:
        target = ShellIsolationTarget.project_session_scenario(
            scenario_name,
            target_id=f"manual-project-session::{scenario_name}",
        )
        try:
            completed = run_shell_isolation_target(target)
        except ShellIsolationTargetTimeout as exc:
            self.fail(str(exc))
        self.assertEqual(
            completed.returncode,
            0,
            format_child_output(completed),
        )

    def test_session_restore_recovers_workspace_order_active_workspace_and_view_camera(
        self,
    ) -> None:
        self._run_scenario(
            "test_session_restore_recovers_workspace_order_active_workspace_and_view_camera"
        )

    def test_autosave_tick_writes_snapshot_and_keeps_valid_project_doc(self) -> None:
        self._run_scenario(
            "test_autosave_tick_writes_snapshot_and_keeps_valid_project_doc"
        )

    def test_saved_project_reopen_seeds_run_required_viewer_projection_without_persisting_live_transport(
        self,
    ) -> None:
        self._run_scenario(
            "test_saved_project_reopen_seeds_run_required_viewer_projection_without_persisting_live_transport"
        )

    def test_open_project_rejects_saved_node_when_startup_preferences_disable_addon(
        self,
    ) -> None:
        self._run_scenario(
            "test_open_project_rejects_saved_node_when_startup_preferences_disable_addon"
        )

    def test_session_restore_recovers_unsaved_temp_staged_refs_without_autosave(
        self,
    ) -> None:
        self._run_scenario(
            "test_session_restore_recovers_unsaved_temp_staged_refs_without_autosave"
        )

    def test_recovery_prompt_accept_loads_newer_autosave(self) -> None:
        self._run_scenario("test_recovery_prompt_accept_loads_newer_autosave")

    def test_recovery_prompt_accept_recovers_unsaved_temp_staged_refs(self) -> None:
        self._run_scenario(
            "test_recovery_prompt_accept_recovers_unsaved_temp_staged_refs"
        )

    def test_recovery_prompt_reject_keeps_empty_startup_project_and_discards_autosave(
        self,
    ) -> None:
        self._run_scenario(
            "test_recovery_prompt_reject_keeps_empty_startup_project_and_discards_autosave"
        )

    def test_session_restore_keeps_saved_project_recent_but_starts_empty(self) -> None:
        self._run_scenario(
            "test_session_restore_keeps_saved_project_recent_but_starts_empty"
        )

    def test_restore_session_handles_corrupted_session_and_autosave_files(self) -> None:
        self._run_scenario(
            "test_restore_session_handles_corrupted_session_and_autosave_files"
        )

    def test_recovery_prompt_is_deferred_until_main_window_is_visible(self) -> None:
        self._run_scenario(
            "test_recovery_prompt_is_deferred_until_main_window_is_visible"
        )

    def test_clean_close_discards_staged_scratch_and_clears_unsaved_root_hint(
        self,
    ) -> None:
        self._run_scenario(
            "test_clean_close_discards_staged_scratch_and_clears_unsaved_root_hint"
        )

    def test_explicit_save_promotes_referenced_staged_refs(self) -> None:
        self._run_scenario(
            "test_explicit_save_promotes_referenced_staged_refs"
        )

    def test_save_as_default_copy_switches_project_path_and_excludes_staging(
        self,
    ) -> None:
        self._run_scenario(
            "test_save_as_default_copy_switches_project_path_and_excludes_staging"
        )

    def test_new_project_uses_navigation_controller_surface_without_workspace_library_facade(
        self,
    ) -> None:
        self._run_scenario(
            "test_new_project_uses_navigation_controller_surface_without_workspace_library_facade"
        )

    def test_project_files_menu_action_triggers_dialog(self) -> None:
        self._run_scenario("test_project_files_menu_action_triggers_dialog")


    def test_save_prompt_receives_project_file_summary_before_saving(self) -> None:
        self._run_scenario(
            "test_save_prompt_receives_project_file_summary_before_saving"
        )

    def test_open_project_path_can_abort_when_project_files_summary_has_staged_and_broken_entries(
        self,
    ) -> None:
        self._run_scenario(
            "test_open_project_path_can_abort_when_project_files_summary_has_staged_and_broken_entries"
        )

    def test_recovery_prompt_receives_project_file_summary_for_recovered_project(
        self,
    ) -> None:
        self._run_scenario(
            "test_recovery_prompt_receives_project_file_summary_for_recovered_project"
        )


class ProjectSessionServiceFacadeBoundaryTests(unittest.TestCase):
    def test_project_session_service_split_uses_support_package_surface(self) -> None:
        facade_path = (
            _PROJECT_ROOT
            / "ea_node_editor"
            / "ui"
            / "shell"
            / "controllers"
            / "project_session_services.py"
        )
        support_root = facade_path.parent / "project_session_services_support"

        self.assertTrue(support_root.is_dir())
        for relative_path in (
            "__init__.py",
            "shared.py",
            "project_files_service.py",
            "session_lifecycle_service.py",
            "document_io_service.py",
        ):
            with self.subTest(path=relative_path):
                self.assertTrue((support_root / relative_path).is_file())
        self.assertTrue(facade_path.is_file())

        module = importlib.import_module(
            "ea_node_editor.ui.shell.controllers.project_session_services"
        )
        self.assertEqual(
            module.ProjectFilesService.__module__,
            "ea_node_editor.ui.shell.controllers.project_session_services_support.project_files_service",
        )
        self.assertEqual(
            module.ProjectSessionLifecycleService.__module__,
            "ea_node_editor.ui.shell.controllers.project_session_services_support.session_lifecycle_service",
        )
        self.assertEqual(
            module.ProjectDocumentIOService.__module__,
            "ea_node_editor.ui.shell.controllers.project_session_services_support.document_io_service",
        )
        self.assertEqual(
            module.normalize_project_path_value.__module__,
            "ea_node_editor.ui.shell.controllers.project_session_services_support.shared",
        )


def load_tests(loader, _tests, _pattern):  # noqa: ANN001
    suite = unittest.TestSuite()
    suite.addTests(
        loader.loadTestsFromTestCase(ProjectSessionServiceFacadeBoundaryTests)
    )
    suite.addTests(loader.loadTestsFromTestCase(ShellProjectSessionControllerTests))
    return suite


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == _SCENARIO_ARG:
        raise SystemExit(_run_named_scenario(sys.argv[2]))
    unittest.main()
