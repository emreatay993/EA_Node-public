from __future__ import annotations

import gc
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtQuick import QQuickItem
from PyQt6.QtWidgets import QApplication, QWidget

from ea_node_editor.execution.compiler import compile_runtime_snapshot
from ea_node_editor.execution.execution_plan import ExecutionPlan
from ea_node_editor.execution.prepared_execution import InvalidationResult
from ea_node_editor.execution.project_solution import (
    ProjectSolutionAdoptionResult,
    ProjectSolutionCandidateResult,
    ProjectSolutionGcResult,
    ProjectSolutionSaveResult,
    ProjectSolutionSaveSnapshot,
    project_solution_snapshot_token,
)
from ea_node_editor.runtime_contracts import GRAPH_DATA_TYPE_ID
from ea_node_editor.telemetry.frame_rate import FrameRateSampler
from ea_node_editor.ui.shell.window import ShellWindow
from scripts import verification_manifest as manifest
from tests.conftest import ShellTestEnvironment


class _ShellTestExecutionClient:
    def __init__(self, registry: object | None = None) -> None:
        self._callbacks: list[object] = []
        self._registry = registry
        self._solution_revisions: dict[str, int] = {}
        self._solution_node_ids_by_workspace: dict[str, set[str]] = {}
        self._project_solution_binding_revision = 0
        self._project_solution_save_contexts: dict[str, dict[str, object]] = {}

    def subscribe(self, callback) -> None:  # noqa: ANN001
        self._callbacks.append(callback)

    def prepare_execution(self, request):  # noqa: ANN001, ANN201
        return SimpleNamespace(
            request=request,
            recompute_node_ids=tuple(request.target_node_ids),
        )

    def dispatch_prepared(self, _prepared) -> str:  # noqa: ANN001
        return ""

    def solution_facts(self, _project_id: str, _workspace_id: str) -> tuple:
        return ()

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
            registry=self._registry,
        )
        plan = ExecutionPlan.for_invalidation(workspace, self._registry)
        closure = plan.affected_downstream_closure(tuple(changed_root_node_ids))
        known_node_ids = self._solution_node_ids_by_workspace.setdefault(
            workspace_id,
            set(),
        )
        active_node_ids = {
            node_id
            for node_id in plan.execution_order
            if plan.node_specs[node_id].runtime_behavior == "active"
        }
        removed_node_ids = tuple(sorted(known_node_ids.difference(active_node_ids)))
        known_node_ids.difference_update(removed_node_ids)
        known_node_ids.update(closure)
        self._solution_revisions[workspace_id] = (
            self._solution_revisions.get(workspace_id, 0) + 1
        )
        return InvalidationResult(
            project_id=project_id,
            workspace_id=workspace_id,
            solution_revision=self._solution_revisions[workspace_id],
            changed_root_node_ids=tuple(changed_root_node_ids),
            expired_node_ids=tuple(closure),
            removed_node_ids=removed_node_ids,
            reason_code=reason_code,
        )

    def capture_project_solution_save(
        self,
        project_id: str,
        source_project_path: str,
        retained_owner_ids,
        source_artifact_context,
    ) -> ProjectSolutionSaveSnapshot:
        if self._registry is None:
            raise ValueError("project_solution_save_source_invalid")
        context_digest = getattr(
            source_artifact_context,
            "project_save_context_digest",
            None,
        )
        if not callable(context_digest):
            raise ValueError("project_solution_save_source_invalid")
        normalized_project_id = str(project_id).strip()
        normalized_source_path = (
            os.path.normcase(os.path.abspath(source_project_path))
            if str(source_project_path).strip()
            else ""
        )
        if normalized_source_path and not os.path.exists(normalized_source_path):
            Path(normalized_source_path).touch()
        owners = tuple(sorted(set(retained_owner_ids)))
        snapshot = ProjectSolutionSaveSnapshot.create(
            project_id=normalized_project_id,
            source_project_path=normalized_source_path,
            solution_namespace_id=f"shell-test:{normalized_project_id}",
            binding_revision=self._project_solution_binding_revision,
            registry_contract_fingerprint=(
                self._registry.contract_fingerprint()
            ),
            source_artifact_context_digest=context_digest(),
            source_generation_id="",
            source_manifest_set_digest="",
            retained_owner_ids=owners,
            supplemental_records=(),
            required_managed_artifact_ids=(),
            estimated_copy_bytes=0,
        )
        self._project_solution_save_contexts[snapshot.snapshot_token] = {
            "snapshot": snapshot,
            "binding_revision": self._project_solution_binding_revision,
            "state": "captured",
            "destination_project_path": "",
            "result": None,
        }
        return snapshot

    def project_solution_save_snapshot_is_current(self, snapshot_token: str) -> bool:
        context = self._project_solution_save_contexts.get(
            str(snapshot_token).strip()
        )
        if context is None:
            return False
        snapshot = context["snapshot"]
        return bool(
            isinstance(snapshot, ProjectSolutionSaveSnapshot)
            and project_solution_snapshot_token(snapshot)
            == snapshot.snapshot_token
            and context["binding_revision"]
            == self._project_solution_binding_revision
            and context["state"] in {"captured", "staged", "candidate"}
        )

    def stage_project_solution_save(
        self,
        snapshot: ProjectSolutionSaveSnapshot,
        destination_project_path: str,
        _destination_artifact_context,
    ) -> ProjectSolutionSaveResult:
        context = self._project_solution_save_contexts.get(
            snapshot.snapshot_token
        )
        if (
            context is None
            or context["snapshot"] != snapshot
            or context["state"] != "captured"
            or not self.project_solution_save_snapshot_is_current(
                snapshot.snapshot_token
            )
        ):
            return ProjectSolutionSaveResult(
                snapshot_token=snapshot.snapshot_token,
                solution_namespace_id=snapshot.solution_namespace_id,
                reason_code="project_solution_save_snapshot_stale",
                diagnostic="The project solution snapshot changed before staging.",
            )
        candidate_generation_id = snapshot.snapshot_token[:32]
        candidate_manifest_set_digest = snapshot.snapshot_token
        result = ProjectSolutionSaveResult(
            snapshot_token=snapshot.snapshot_token,
            solution_namespace_id=snapshot.solution_namespace_id,
            candidate_generation_id=candidate_generation_id,
            candidate_manifest_set_digest=candidate_manifest_set_digest,
            initially_protected_generations=(
                (candidate_generation_id, candidate_manifest_set_digest),
            ),
            estimated_copy_bytes=0,
            staged_new_bytes=0,
        )
        context["destination_project_path"] = os.path.normcase(
            os.path.abspath(destination_project_path)
        )
        context["result"] = result
        context["state"] = "staged"
        return result

    def prepare_project_solution_adoption(
        self,
        result: ProjectSolutionSaveResult,
        project_id: str,
        destination_project_path: str,
        metadata_solution_store: object,
        _destination_artifact_context: object,
    ) -> ProjectSolutionCandidateResult:
        context = self._project_solution_save_contexts.get(result.snapshot_token)
        snapshot = context["snapshot"] if context is not None else None
        valid = bool(
            context is not None
            and isinstance(snapshot, ProjectSolutionSaveSnapshot)
            and context["state"] == "staged"
            and context["result"] == result
            and self.project_solution_save_snapshot_is_current(
                result.snapshot_token
            )
            and snapshot.project_id == str(project_id).strip()
            and context["destination_project_path"]
            == os.path.normcase(os.path.abspath(destination_project_path))
            and result.metadata_solution_store == metadata_solution_store
        )
        if not valid:
            return ProjectSolutionCandidateResult(
                False,
                "project_solution_candidate_snapshot_stale",
                "The project solution snapshot changed before candidate reopen.",
            )
        context["state"] = "candidate"
        return ProjectSolutionCandidateResult(
            True,
            "project_solution_candidate_prepared",
        )

    def adopt_project_solution_save(
        self,
        result: ProjectSolutionSaveResult,
        project_id: str,
        destination_project_path: str,
        metadata_solution_store: object,
        _destination_artifact_context: object,
    ) -> ProjectSolutionAdoptionResult:
        context = self._project_solution_save_contexts.get(result.snapshot_token)
        snapshot = context["snapshot"] if context is not None else None
        if (
            context is None
            or not isinstance(snapshot, ProjectSolutionSaveSnapshot)
            or context["state"] != "candidate"
            or context["binding_revision"]
            != self._project_solution_binding_revision
        ):
            return ProjectSolutionAdoptionResult(
                False,
                "project_solution_adoption_snapshot_stale",
                "The project solution snapshot changed before adoption.",
            )
        if (
            snapshot.project_id != str(project_id).strip()
            or context["destination_project_path"]
            != os.path.normcase(os.path.abspath(destination_project_path))
            or result.solution_namespace_id != snapshot.solution_namespace_id
        ):
            return ProjectSolutionAdoptionResult(
                False,
                "project_solution_adoption_namespace_mismatch",
                "The project solution namespace changed before adoption.",
            )
        if context["result"] != result or (
            result.metadata_solution_store != metadata_solution_store
        ):
            return ProjectSolutionAdoptionResult(
                False,
                "project_solution_adoption_candidate_invalid",
                "The prepared project solution candidate is invalid.",
            )
        context["state"] = "adopted"
        self._project_solution_binding_revision += 1
        context["binding_revision"] = self._project_solution_binding_revision
        return ProjectSolutionAdoptionResult(
            True,
            "project_solution_adopted",
        )

    def cancel_project_solution_save(self, snapshot_token: str) -> None:
        self._project_solution_save_contexts.pop(str(snapshot_token).strip(), None)

    def collect_project_solution_garbage(
        self,
        result: ProjectSolutionSaveResult,
        *,
        protect_previous_generation: bool,
        limit: int = 10_000,
    ) -> ProjectSolutionGcResult:
        del limit
        context = self._project_solution_save_contexts.get(result.snapshot_token)
        if (
            context is None
            or context["state"] != "adopted"
            or context["result"] != result
        ):
            return ProjectSolutionGcResult(
                (),
                (),
                False,
                "project_solution_gc_skipped_invalid",
            )
        gc_result = ProjectSolutionGcResult(
            (),
            (),
            False,
            "project_solution_gc_completed",
        )
        if not protect_previous_generation:
            self._project_solution_save_contexts.pop(result.snapshot_token, None)
        return gc_result

    def pause_run(self, run_id: str) -> None:
        return None

    def resume_run(self, run_id: str) -> None:
        return None

    def stop_run(self, run_id: str) -> None:
        return None

    def shutdown(self) -> None:
        self._callbacks.clear()
        self._solution_node_ids_by_workspace.clear()
        self._project_solution_binding_revision += 1
        self._project_solution_save_contexts.clear()

    def retire_workspace(self, _workspace_id: str) -> int:
        return 0


def _action_shortcuts(action) -> set[str]:  # noqa: ANN001
    return {
        sequence.toString(QKeySequence.SequenceFormat.PortableText)
        for sequence in action.shortcuts()
    }


def _flush_shell_qt_events(app: QApplication) -> None:
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _prepare_shell_test_process(app: QApplication) -> None:
    _flush_shell_qt_events(app)
    gc.collect()


def _destroy_shell_window(window: ShellWindow | None) -> None:
    if window is None:
        return
    window.close()
    window.deleteLater()


def _create_shell_window(app: QApplication) -> ShellWindow:
    window = ShellWindow()
    window.resize(1200, 800)
    window.show()
    _flush_shell_qt_events(app)
    return window


class MainWindowShellTestBase(unittest.TestCase):
    """Base class for tests that need a full ``ShellWindow`` environment.

    Provides ``self.app``, ``self.window``, and convenient path accessors
    via ``self._env``.
    """

    def setUp(self) -> None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
        self.app = QApplication.instance() or QApplication([])
        self.app.setQuitOnLastWindowClosed(False)
        _prepare_shell_test_process(self.app)
        self._env = ShellTestEnvironment()
        self._env.start()
        self._execution_client_patch = patch(
            "ea_node_editor.ui.shell.composition.controllers._create_shell_execution_client",
            _ShellTestExecutionClient,
        )
        self._execution_client_patch.start()
        self._temp_dir = self._env._temp_dir
        self._session_path = self._env.session_path
        self._autosave_path = self._env.autosave_path
        self._app_preferences_path = self._env.app_preferences_path
        self._global_custom_workflows_path = self._env.global_custom_workflows_path
        self.window = _create_shell_window(self.app)

    def tearDown(self) -> None:
        window = self.window
        _destroy_shell_window(window)
        self.window = None
        _flush_shell_qt_events(self.app)
        self._env.stop()
        self._execution_client_patch.stop()
        gc.collect()

    def _active_workspace(self):
        workspace_id = self.window.workspace_manager.active_workspace_id()
        return workspace_id, self.window.model.project.workspaces[workspace_id]

    def _qml_host(self):
        return getattr(self.window, "qml_host", None) or self.window.quick_widget

    def _qml_root_object(self) -> QObject:
        qml_host = self._qml_host()
        root_object_getter = getattr(qml_host, "root_object", None)
        root_object = (
            root_object_getter()
            if callable(root_object_getter)
            else qml_host.rootObject()
        )
        self.assertIsNotNone(root_object)
        return root_object

    def _qml_root_context(self):
        qml_host = self._qml_host()
        context_getter = getattr(qml_host, "root_context", None)
        return context_getter() if callable(context_getter) else qml_host.rootContext()

    def _qml_input_widget(self) -> QWidget:
        qml_host = self._qml_host()
        input_widget = getattr(qml_host, "event_filter_widget", None)
        return input_widget or self.window.quick_widget

    def _workspace_state(self) -> dict[str, object]:
        _workspace_id, workspace = self._active_workspace()
        nodes = {
            node_id: {
                "type_id": node.type_id,
                "title": node.title,
                "x": float(node.x),
                "y": float(node.y),
                "collapsed": bool(node.collapsed),
                "properties": dict(node.properties),
                "exposed_ports": dict(node.exposed_ports),
            }
            for node_id, node in workspace.nodes.items()
        }
        edges = {
            edge_id: (
                edge.source_node_id,
                edge.source_port_key,
                edge.target_node_id,
                edge.target_port_key,
            )
            for edge_id, edge in workspace.edges.items()
        }
        return {"nodes": nodes, "edges": edges}

    def _graph_canvas_item(self) -> QObject:
        root_object = self._qml_root_object()
        graph_canvas = root_object.findChild(QObject, "graphCanvas")
        self.assertIsNotNone(graph_canvas)
        return graph_canvas

    def _hold_qml_ref(self, item: QQuickItem) -> QQuickItem:
        return item

    def _walk_items(self, item: QQuickItem):
        yield item
        for child in item.childItems():
            yield from self._walk_items(child)

    def _find_qml_item(self, object_name: str) -> QQuickItem | None:
        for item in self._walk_items(self._qml_root_object()):
            if item.objectName() == object_name:
                return self._hold_qml_ref(item)
        return None

    def _open_inspector_property_group(self, property_key: str) -> None:
        self.window.shell_inspector_presenter.set_property_pane_variant("smart_groups")
        self.app.processEvents()

        property_items = {
            str(item["key"]): item
            for item in self.window.selected_node_property_items
        }
        property_item = property_items[property_key]
        group_name = str(property_item.get("group") or "Properties")
        smart_groups_body = self._find_qml_item("inspectorSmartGroupsBody")
        self.assertIsNotNone(smart_groups_body)
        assert smart_groups_body is not None
        smart_groups_body.setProperty("expandedMap", {f"static:{group_name}": True})
        self.app.processEvents()

    def _inspector_property_object(
        self, object_name: str, property_key: str
    ) -> QQuickItem:
        self._open_inspector_property_group(property_key)
        for item in self._walk_items(self._qml_root_object()):
            if item.objectName() != object_name:
                continue
            if str(item.property("propertyKey")) != property_key:
                continue
            if not bool(item.property("visible")):
                continue
            return self._hold_qml_ref(item)
        self.fail(f"Could not find {object_name!r} for property {property_key!r}.")

    def _graph_node_card(self, node_id: str) -> QQuickItem:
        for item in self._walk_items(self._graph_canvas_item()):
            if item.objectName() != "graphNodeCard":
                continue
            node_data = item.property("nodeData") or {}
            if str(node_data.get("node_id", "")) == node_id:
                return self._hold_qml_ref(item)
        self.fail(f"Could not find graphNodeCard for node {node_id!r}.")

    def _library_pane_item(self) -> QObject:
        root_object = self._qml_root_object()
        library_pane = root_object.findChild(QObject, "libraryPane")
        self.assertIsNotNone(library_pane)
        return library_pane

    def _create_publishable_subnode(
        self, *, shell_title: str, output_label: str
    ) -> tuple[str, str]:
        shell_id = self.window.scene.add_node_from_type(
            "core.subnode", x=220.0, y=120.0
        )
        self.window.scene.set_node_title(shell_id, shell_title)
        self.assertTrue(self.window.request_open_subnode_scope(shell_id))
        output_pin_id = self.window.scene.add_node_from_type(
            "core.subnode_output", x=180.0, y=90.0
        )
        self.window.scene.set_node_property(output_pin_id, "label", output_label)
        self.window.scene.set_node_property(output_pin_id, "kind", "data")
        self.window.scene.set_node_property(output_pin_id, "data_type", GRAPH_DATA_TYPE_ID)
        self.assertTrue(self.window.request_navigate_scope_parent())
        self.window.scene.focus_node(shell_id)
        self.app.processEvents()
        return shell_id, output_pin_id

    def _create_nested_outer_inner_subnodes(self) -> tuple[str, str]:
        outer_id = self.window.scene.add_node_from_type(
            "core.subnode", x=120.0, y=100.0
        )
        self.window.scene.set_node_title(outer_id, "Outer")
        self.assertTrue(self.window.request_open_subnode_scope(outer_id))

        outer_input_id = self.window.scene.add_node_from_type(
            "core.subnode_input", x=20.0, y=80.0
        )
        self.window.scene.set_node_property(outer_input_id, "label", "Outer In")
        self.window.scene.set_node_property(outer_input_id, "kind", "data")
        self.window.scene.set_node_property(outer_input_id, "data_type", GRAPH_DATA_TYPE_ID)

        outer_output_id = self.window.scene.add_node_from_type(
            "core.subnode_output", x=420.0, y=80.0
        )
        self.window.scene.set_node_property(outer_output_id, "label", "Outer Out")
        self.window.scene.set_node_property(outer_output_id, "kind", "data")
        self.window.scene.set_node_property(outer_output_id, "data_type", GRAPH_DATA_TYPE_ID)

        inner_id = self.window.scene.add_node_from_type(
            "core.subnode", x=220.0, y=160.0
        )
        self.window.scene.set_node_title(inner_id, "Inner")

        self.assertTrue(self.window.request_open_subnode_scope(inner_id))
        inner_input_id = self.window.scene.add_node_from_type(
            "core.subnode_input", x=20.0, y=80.0
        )
        self.window.scene.set_node_property(inner_input_id, "label", "Inner In")
        self.window.scene.set_node_property(inner_input_id, "kind", "data")
        self.window.scene.set_node_property(inner_input_id, "data_type", GRAPH_DATA_TYPE_ID)

        inner_output_id = self.window.scene.add_node_from_type(
            "core.subnode_output", x=420.0, y=80.0
        )
        self.window.scene.set_node_property(inner_output_id, "label", "Inner Out")
        self.window.scene.set_node_property(inner_output_id, "kind", "data")
        self.window.scene.set_node_property(inner_output_id, "data_type", GRAPH_DATA_TYPE_ID)

        script_id = self.window.scene.add_node_from_type(
            "core.python_script", x=220.0, y=160.0
        )
        self.window.scene.add_edge(inner_input_id, "pin", script_id, "payload")
        self.window.scene.add_edge(script_id, "result", inner_output_id, "pin")

        self.assertTrue(self.window.request_navigate_scope_parent())
        self.window.scene.add_edge(outer_input_id, "pin", inner_id, inner_input_id)
        self.window.scene.add_edge(inner_id, inner_output_id, outer_output_id, "pin")

        self.assertTrue(self.window.request_navigate_scope_parent())
        self.window.scene.focus_node(outer_id)
        self.app.processEvents()
        return outer_id, inner_id


class SharedMainWindowShellTestBase(MainWindowShellTestBase):
    """Reuse a shell only within one already-isolated child process."""

    _SHELL_LIFECYCLE_NOTE = (
        f"{manifest.SHELL_LIFECYCLE_TRUTH} remains the outer contract; shared reuse is "
        f"limited to {manifest.SHELL_LIFECYCLE_SHARED_WINDOW_SCOPE}."
    )
    _shared_env: ShellTestEnvironment | None = None
    _shared_execution_client_patch = None
    _shared_window: ShellWindow | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        _prepare_shell_test_process(cls.app)
        cls._shared_env = ShellTestEnvironment()
        cls._shared_env.start()
        cls._shared_execution_client_patch = patch(
            "ea_node_editor.ui.shell.composition.controllers._create_shell_execution_client",
            _ShellTestExecutionClient,
        )
        cls._shared_execution_client_patch.start()
        cls._temp_dir = cls._shared_env._temp_dir
        cls._session_path = cls._shared_env.session_path
        cls._autosave_path = cls._shared_env.autosave_path
        cls._app_preferences_path = cls._shared_env.app_preferences_path
        cls._global_custom_workflows_path = cls._shared_env.global_custom_workflows_path
        cls._shared_window = cls._create_shared_window()
        cls.window = cls._shared_window

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            _destroy_shell_window(cls._shared_window)
            cls._shared_window = None
            cls.window = None
            _flush_shell_qt_events(cls.app)
            gc.collect()
        finally:
            if cls._shared_execution_client_patch is not None:
                cls._shared_execution_client_patch.stop()
                cls._shared_execution_client_patch = None
            if cls._shared_env is not None:
                cls._shared_env.stop()
                cls._shared_env = None
            gc.collect()

    @classmethod
    def _create_shared_window(cls) -> ShellWindow:
        return _create_shell_window(cls.app)

    def setUp(self) -> None:
        cls = self.__class__
        self.app = cls.app
        self._env = cls._shared_env
        self._temp_dir = cls._temp_dir
        self._session_path = cls._session_path
        self._autosave_path = cls._autosave_path
        self._app_preferences_path = cls._app_preferences_path
        self._global_custom_workflows_path = cls._global_custom_workflows_path
        self.window = cls._shared_window
        self._reset_shared_shell_state()

    def tearDown(self) -> None:
        _flush_shell_qt_events(self.app)

    def _reset_shared_shell_state(self) -> None:
        window = self.window
        self.assertIsNotNone(window)
        app = self.app
        _flush_shell_qt_events(app)
        from ea_node_editor.addons.tabular_data.loader_cache_service import (
            set_shared_tabular_ui_thread_conversion_allowed,
        )

        set_shared_tabular_ui_thread_conversion_allowed(False)
        clipboard = app.clipboard()
        clipboard.clear()

        window.console_panel.clear_all()
        window.update_notification_counters(0, 0)
        window.run_projection_controller.set_run_ui_state(
            "ready",
            "Idle",
            0,
            0,
            0,
            0,
            clear_active_run=window.run_controller.clear_active_run,
        )
        window.run_projection_controller.clear_run_failure_focus()
        window.clear_graph_hint()
        window._set_graph_search_state(
            open_=False, query="", results=[], highlight_index=-1
        )
        window._set_connection_quick_insert_state(
            open_=False,
            query="",
            results=[],
            highlight_index=-1,
            context=None,
        )
        window.graph_canvas_host_presenter.clear_graph_cursor_shape()
        window.search_scope_state.runtime_scope_camera.clear()
        window.set_library_query("")
        window.set_library_category("")
        window.set_library_data_type("")
        window.set_library_direction("")

        for path in (
            self._session_path,
            self._autosave_path,
            self._app_preferences_path,
            self._global_custom_workflows_path,
        ):
            if path is None:
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                pass

        window.app_preferences_controller.load_into_host(window, reload_from_store=True)
        for workspace in window.model.project.workspaces.values():
            workspace.dirty = False
        window._new_project()
        window._clear_recent_projects()
        window._frame_rate_sampler = FrameRateSampler()
        inspector_pane = self._qml_root_object().findChild(QObject, "inspectorPane")
        if inspector_pane is not None:
            inspector_pane.setProperty("activePortDirection", "in")
            inspector_pane.setProperty("selectedPortKey", "")
            inspector_pane.setProperty("editingPortKey", "")
            inspector_pane.setProperty("editingPortLabel", "")
        window.metrics_timer.start()
        window.autosave_timer.start()
        _flush_shell_qt_events(app)

    def _reopen_shared_window(self) -> None:
        cls = self.__class__
        old_window = cls._shared_window
        _destroy_shell_window(old_window)
        _flush_shell_qt_events(cls.app)
        new_window = cls._create_shared_window()
        cls._shared_window = new_window
        cls.window = new_window
        self.window = new_window
