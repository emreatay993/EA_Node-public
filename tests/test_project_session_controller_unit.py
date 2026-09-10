from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.persistence.serializer import ProjectDocumentSnapshot
from ea_node_editor.persistence.session_store import RecentSessionEnvelope
from ea_node_editor.ui.dialogs.project_files_dialog import ProjectFilesBrokenEntry
from ea_node_editor.ui.shell.controllers.project_session_controller import (
    ProjectSessionController,
)
from ea_node_editor.ui.shell.controllers.run_projection_controller import (
    RunProjectionController,
)
from ea_node_editor.ui.shell.state import ShellProjectSessionState, ShellRunState
from ea_node_editor.workspace.manager import WorkspaceManager


class _ScriptEditorStub:
    def __init__(self) -> None:
        self.visible = False
        self.floating = False
        self.panel_width = 0.0
        self.focus_calls = 0
        self.nodes = []

    def set_visible(self, value: bool) -> None:
        self.visible = bool(value)

    def set_floating(self, value: bool) -> None:
        self.floating = bool(value)

    def set_width(self, value: float) -> None:
        self.panel_width = float(value)

    def focus_editor(self) -> None:
        self.focus_calls += 1

    def set_node(self, node) -> None:  # noqa: ANN001
        self.nodes.append(node)


class _ActionToggleStub:
    def __init__(self) -> None:
        self.checked = False

    def setChecked(self, value: bool) -> None:  # noqa: N802
        self.checked = bool(value)


class _SceneStub:
    def __init__(self, selected_node_id: str = "") -> None:
        self._selected_node_id = selected_node_id
        self.property_changes: list[tuple[str, str, object]] = []

    def selected_node_id(self) -> str:
        return self._selected_node_id

    def set_node_property(self, node_id: str, key: str, value: object) -> None:
        self.property_changes.append((node_id, key, value))



class _WorkspaceNavigationControllerStub:
    def __init__(self) -> None:
        self.save_active_view_state_calls = 0
        self.refresh_workspace_tabs_calls = 0
        self.switch_workspace_calls: list[str] = []

    def save_active_view_state(self) -> None:
        self.save_active_view_state_calls += 1

    def refresh_workspace_tabs(self) -> None:
        self.refresh_workspace_tabs_calls += 1

    def switch_workspace(self, workspace_id: str) -> None:
        self.switch_workspace_calls.append(str(workspace_id))


class _RuntimeHistoryStub:
    def __init__(self) -> None:
        self.clear_all_calls = 0

    def clear_all(self) -> None:
        self.clear_all_calls += 1


class _RunControllerStub:
    def __init__(self, host) -> None:  # noqa: ANN001
        self._host = host
        self.reset_runtime_solution_state_calls = 0
        self.models_seen_at_reset: list[GraphModel] = []
        self.evaluate_workspace_on_open_calls: list[str] = []
        self.selected_workspaces_seen_at_evaluation: list[str] = []

    def reset_runtime_solution_state(self) -> None:
        self.reset_runtime_solution_state_calls += 1
        self.models_seen_at_reset.append(self._host.model)

    def evaluate_workspace_on_open(self, workspace_id: str) -> None:
        self.evaluate_workspace_on_open_calls.append(str(workspace_id))
        selected = self._host.workspace_navigation_controller.switch_workspace_calls
        self.selected_workspaces_seen_at_evaluation.append(
            selected[-1] if selected else ""
        )


class _SignalStub:
    def __init__(self) -> None:
        self.emit_calls: list[tuple[object, ...]] = []

    def emit(self, *args) -> None:  # noqa: ANN002
        self.emit_calls.append(tuple(args))


class _ViewerSessionBridgeStub:
    def __init__(self, install_events: list[tuple[str, str]]) -> None:
        self._install_events = install_events
        self.project_loaded_calls: list[dict] = []

    def project_loaded(
        self, project, registry, *, reseed_on_next_reset: bool = False
    ) -> None:  # noqa: ANN001
        self._install_events.append(("viewer_project_loaded", ""))
        self.project_loaded_calls.append(
            {
                "project": project,
                "registry": registry,
                "reseed_on_next_reset": bool(reseed_on_next_reset),
            }
        )


class _ViewerHostServiceStub:
    def __init__(self, install_events: list[tuple[str, str]]) -> None:
        self._install_events = install_events
        self.reset_calls: list[str] = []

    def reset(self, *, reason: str = "") -> None:
        normalized = str(reason or "")
        self.reset_calls.append(normalized)
        self._install_events.append(("viewer_host_reset", normalized))


class _RegistryStub:
    def normalize_properties(
        self, _type_id: str, properties: dict, *, include_defaults: bool = False
    ) -> dict:
        return copy.deepcopy(properties)


class _SerializerStub:
    def __init__(self) -> None:
        self.to_document_calls = 0

    def to_document(self, project) -> dict:  # noqa: ANN001
        self.to_document_calls += 1
        return {
            "project_id": project.project_id,
            "name": project.name,
            "metadata": copy.deepcopy(project.metadata),
        }


class _SessionStoreStub:
    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path
        self.discard_calls = 0
        self.persist_calls: list[dict] = []
        self.autosave_calls: list[dict] = []

    def staging_workspace_root(self) -> Path:
        root = self._base_path / "session_staging"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def discard_autosave_snapshot(self) -> None:
        self.discard_calls += 1

    def autosave_if_changed(self, **kwargs) -> str:  # noqa: ANN003
        self.autosave_calls.append(dict(kwargs))
        return str(kwargs.get("last_fingerprint") or "stub-autosave-fingerprint")

    def persist_session(self, **kwargs) -> None:  # noqa: ANN003
        self.persist_calls.append(copy.deepcopy(kwargs))


class _ProjectHostStub:
    def __init__(self, base_path: Path | None = None) -> None:
        self.project_session_state = ShellProjectSessionState()
        self.run_state = ShellRunState()
        self.model = GraphModel()
        self.workspace_manager = WorkspaceManager(self.model)
        self.registry = _RegistryStub()
        self.script_editor = _ScriptEditorStub()
        self.action_toggle_script_editor = _ActionToggleStub()
        self.scene = _SceneStub()
        self.project_path = ""
        self.session_store = _SessionStoreStub(base_path or Path.cwd())
        self.serializer = _SerializerStub()
        self.workspace_navigation_controller = _WorkspaceNavigationControllerStub()
        self.shell_inspector_presenter = self
        self.runtime_history = _RuntimeHistoryStub()
        self.run_controller = _RunControllerStub(self)
        self.execution_client = mock.Mock()
        self.install_events: list[tuple[str, str]] = []
        self.viewer_host_service = _ViewerHostServiceStub(self.install_events)
        self.viewer_session_bridge = _ViewerSessionBridgeStub(self.install_events)
        self.library_pane_reset_requested = _SignalStub()
        self.node_library_changed = _SignalStub()
        self.node_execution_state_changed = _SignalStub()
        self.run_failure_changed = _SignalStub()
        self.project_meta_changed = _SignalStub()
        self.app_preferences_controller = mock.Mock()
        self.app_preferences_controller.default_python_executable.return_value = ""
        self.app_preferences_controller.set_default_python_executable.side_effect = (
            lambda value: value
        )
        self.run_projection_controller = RunProjectionController(self)  # type: ignore[arg-type]
        self.refresh_calls = 0
        self.browse_calls: list[tuple[str, str, str]] = []
        self.browse_result = ""

    def _refresh_recent_projects_menu(self) -> None:
        self.refresh_calls += 1

    def browse_node_property_path(
        self, node_id: str, key: str, current_path: str
    ) -> str:
        self.browse_calls.append((node_id, key, current_path))
        return self.browse_result or current_path

    def _commit_node_execution_state_change(self) -> None:
        self.run_state.node_execution_revision += 1
        self.node_execution_state_changed.emit()


class ProjectSessionControllerUnitTests(unittest.TestCase):
    def test_replace_project_artifact_store_updates_metadata_revision_and_signal_once(
        self,
    ) -> None:
        host = _ProjectHostStub()
        host.model.project.metadata = {"custom": "preserve-me"}
        controller = ProjectSessionController(host)  # type: ignore[arg-type]
        store = ProjectArtifactStore(project_path=None, metadata=None)
        before_revision = host.model.project.project_document_revision
        self.assertFalse(hasattr(controller, "_set_project_artifact_store"))
        self.assertFalse(
            hasattr(
                controller._project_files_service,  # noqa: SLF001
                "_set_project_artifact_store",
            )
        )

        self.assertTrue(controller.replace_project_artifact_store(store))
        self.assertEqual(
            host.model.project.project_document_revision,
            before_revision + 1,
        )
        self.assertEqual(host.project_meta_changed.emit_calls, [()])
        self.assertEqual(host.model.project.metadata["custom"], "preserve-me")
        self.assertEqual(
            host.model.project.metadata["artifact_store"],
            store.metadata,
        )

        unchanged_revision = host.model.project.project_document_revision
        self.assertFalse(controller.replace_project_artifact_store(store))
        self.assertEqual(
            host.model.project.project_document_revision,
            unchanged_revision,
        )
        self.assertEqual(host.project_meta_changed.emit_calls, [()])

    def test_metadata_defaults_are_merged_without_dropping_existing_values(
        self,
    ) -> None:
        host = _ProjectHostStub()
        host.model.project.metadata = {
            "workflow_settings": {
                "solver_config": {"thread_count": 16},
            },
            "ui": {
                "script_editor": {"visible": True},
            },
        }
        controller = ProjectSessionController(host)  # type: ignore[arg-type]

        controller.ensure_project_metadata_defaults()

        metadata = host.model.project.metadata
        self.assertEqual(
            metadata["workflow_settings"]["solver_config"]["thread_count"], 16
        )
        self.assertIn("memory_limit_gb", metadata["workflow_settings"]["solver_config"])
        self.assertTrue(metadata["ui"]["script_editor"]["visible"])
        self.assertIn("floating", metadata["ui"]["script_editor"])
        self.assertIn("passive_style_presets", metadata["ui"])

    def test_workflow_settings_cancel_leaves_both_stores_and_project_unchanged(self) -> None:
        host = _ProjectHostStub()
        host.model.project.metadata = {
            "custom": "preserve-me",
            "workflow_settings": {"solver_config": {"thread_count": 16}},
        }
        host.app_preferences_controller.default_python_executable.return_value = (
            r"C:\application\python.exe"
        )
        controller = ProjectSessionController(host)  # type: ignore[arg-type]
        before_metadata = copy.deepcopy(host.model.project.metadata)
        before_epoch = host.model.project.document_epoch()
        before_revision = host.model.project.project_document_revision
        dialog = mock.Mock()
        dialog.DialogCode.Accepted = 1
        dialog.exec.return_value = 0

        with (
            mock.patch(
                "ea_node_editor.ui.dialogs.workflow_settings_dialog.WorkflowSettingsDialog",
                return_value=dialog,
            ) as dialog_class,
            mock.patch.object(controller._session_service, "persist_session") as persist_session,
        ):
            controller.show_workflow_settings_dialog()

        dialog_class.assert_called_once_with(
            initial_settings=mock.ANY,
            application_default_python_executable=r"C:\application\python.exe",
            parent=None,
        )
        self.assertEqual(host.model.project.metadata, before_metadata)
        self.assertEqual(host.model.project.project_document_revision, before_revision)
        self.assertEqual(host.model.project.document_epoch(), before_epoch)
        host.app_preferences_controller.set_default_python_executable.assert_not_called()
        persist_session.assert_not_called()

    def test_workflow_settings_app_write_failure_leaves_project_and_session_unchanged(self) -> None:
        host = _ProjectHostStub()
        host.model.project.metadata = {
            "custom": "preserve-me",
            "workflow_settings": {"environment": {"python_path": "workflow-old"}},
        }
        host.app_preferences_controller.set_default_python_executable.side_effect = OSError(
            "write failed"
        )
        controller = ProjectSessionController(host)  # type: ignore[arg-type]
        before_metadata = copy.deepcopy(host.model.project.metadata)
        before_epoch = host.model.project.document_epoch()
        before_revision = host.model.project.project_document_revision
        dialog = mock.Mock()
        dialog.DialogCode.Accepted = 1
        dialog.exec.return_value = 1
        dialog.application_default_python_executable.return_value = "application-new"
        dialog.values.return_value = {
            "environment": {"python_path": "workflow-new"}
        }

        with (
            mock.patch(
                "ea_node_editor.ui.dialogs.workflow_settings_dialog.WorkflowSettingsDialog",
                return_value=dialog,
            ),
            mock.patch.object(controller._session_service, "persist_session") as persist_session,
            mock.patch("PyQt6.QtWidgets.QMessageBox.warning") as warning,
        ):
            controller.show_workflow_settings_dialog()

        host.app_preferences_controller.set_default_python_executable.assert_called_once_with(
            "application-new"
        )
        self.assertEqual(host.model.project.metadata, before_metadata)
        self.assertEqual(host.model.project.project_document_revision, before_revision)
        self.assertEqual(host.model.project.document_epoch(), before_epoch)
        persist_session.assert_not_called()
        warning.assert_called_once()
        self.assertIn("Could not save", warning.call_args.args[2])

    def test_workflow_settings_persist_app_first_then_project_once(self) -> None:
        host = _ProjectHostStub()
        host.model.project.metadata = {
            "custom": "preserve-me",
            "workflow_settings": {"environment": {"python_path": "workflow-old"}},
        }
        controller = ProjectSessionController(host)  # type: ignore[arg-type]
        before_metadata = copy.deepcopy(host.model.project.metadata)
        events: list[tuple[str, dict]] = []

        def persist_app(value: str) -> str:
            events.append(("app", copy.deepcopy(host.model.project.metadata)))
            return value

        def persist_session() -> None:
            events.append(("session", copy.deepcopy(host.model.project.metadata)))

        host.app_preferences_controller.set_default_python_executable.side_effect = persist_app
        dialog = mock.Mock()
        dialog.DialogCode.Accepted = 1
        dialog.exec.return_value = 1
        dialog.application_default_python_executable.return_value = "application-new"
        dialog.values.return_value = {
            "environment": {
                "python_path": "workflow-new",
                "working_directory": "",
            }
        }

        with (
            mock.patch(
                "ea_node_editor.ui.dialogs.workflow_settings_dialog.WorkflowSettingsDialog",
                return_value=dialog,
            ),
            mock.patch.object(
                controller._session_service,
                "persist_session",
                side_effect=persist_session,
            ) as session_persist,
        ):
            controller.show_workflow_settings_dialog()

        self.assertEqual([event[0] for event in events], ["app", "session"])
        self.assertEqual(events[0][1], before_metadata)
        self.assertEqual(
            events[1][1]["workflow_settings"]["environment"]["python_path"],
            "workflow-new",
        )
        self.assertEqual(host.model.project.metadata["custom"], "preserve-me")
        self.assertEqual(
            host.model.project.metadata["workflow_settings"]["environment"]["python_path"],
            "workflow-new",
        )
        session_persist.assert_called_once_with()
        self.assertEqual(host.run_controller.reset_runtime_solution_state_calls, 0)

    def test_recent_project_paths_are_normalized_deduplicated_and_capped(self) -> None:
        host = _ProjectHostStub()
        controller = ProjectSessionController(host)  # type: ignore[arg-type]

        normalized = controller.set_recent_project_paths(
            [
                " first_project ",
                "first_project.cxproj",
                "",
                ".",
                *(f"project_{index}" for index in range(2, 20)),
            ],
            persist=False,
        )

        self.assertEqual(normalized[0], "first_project.cxproj")
        self.assertEqual(len(normalized), 10)
        self.assertEqual(len(set(normalized)), len(normalized))
        self.assertEqual(host.project_session_state.recent_project_paths, normalized)
        self.assertEqual(host.refresh_calls, 1)

    def test_recent_session_envelope_requires_list_recent_project_paths(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "recent_project_paths must be a JSON array"
        ):
            RecentSessionEnvelope.from_mapping(
                {
                    "project_path": "active.cxproj",
                    "last_manual_save_ts": 0.0,
                    "recent_project_paths": {
                        "first": "alpha.cxproj",
                    },
                }
            )

    def test_add_and_remove_recent_project_paths_normalize_suffixes(self) -> None:
        host = _ProjectHostStub()
        controller = ProjectSessionController(host)  # type: ignore[arg-type]

        with mock.patch.object(
            controller._session_service, "persist_session"
        ) as persist_session:
            controller.set_recent_project_paths(
                ["alpha.cxproj", "beta.cxproj"], persist=False
            )
            updated = controller.add_recent_project_path("beta", persist=True)
            self.assertEqual(updated[:2], ["beta.cxproj", "alpha.cxproj"])

            updated = controller.remove_recent_project_path("alpha", persist=True)
            self.assertEqual(updated, ["beta.cxproj"])
            self.assertEqual(persist_session.call_count, 2)

    def test_controller_routes_project_session_actions_through_service_authorities(
        self,
    ) -> None:
        host = _ProjectHostStub()
        controller = ProjectSessionController(host)  # type: ignore[arg-type]
        snapshot = mock.sentinel.snapshot
        issue = mock.sentinel.issue
        recovered_project = host.model.project

        with (
            mock.patch.object(
                controller._document_service, "save_project"
            ) as save_project,
            mock.patch.object(
                controller._document_service, "save_project_as"
            ) as save_project_as,
            mock.patch.object(
                controller._document_service,
                "open_project",
                return_value=False,
            ) as open_project,
            mock.patch.object(
                controller._document_service,
                "open_project_path",
                return_value=True,
            ) as open_project_path,
            mock.patch.object(
                controller._project_files_service,
                "prompt_project_files_action",
                return_value=True,
            ) as prompt_project_files_action,
            mock.patch.object(
                controller._project_files_service, "show_project_files_dialog"
            ) as show_project_files_dialog,
            mock.patch.object(
                controller._project_files_service,
                "repair_project_file_issue",
                return_value=True,
            ) as repair_project_file_issue,
            mock.patch.object(
                controller._session_service,
                "prompt_recover_autosave",
                return_value=mock.sentinel.choice,
            ) as prompt_recover_autosave,
        ):
            controller.save_project()
            controller.save_project_as()
            controller.open_project()
            self.assertTrue(
                controller.open_project_path("example.cxproj", show_errors=False)
            )
            self.assertTrue(
                controller._prompt_project_files_action(
                    title="Save Project",
                    text="summary",
                    continue_label="Save Project",
                    cancel_standard_button=object(),
                    snapshot=snapshot,
                    context_key="save",
                    allow_repair=True,
                    always_prompt=True,
                )
            )
            controller.show_project_files_dialog(snapshot=snapshot, allow_repair=True)
            self.assertTrue(controller._repair_project_file_issue(issue))
            self.assertIs(
                controller.prompt_recover_autosave(recovered_project),
                mock.sentinel.choice,
            )

        save_project.assert_called_once_with()
        save_project_as.assert_called_once_with()
        open_project.assert_called_once_with()
        open_project_path.assert_called_once_with("example.cxproj", show_errors=False)
        self.assertEqual(
            host.run_controller.evaluate_workspace_on_open_calls,
            [host.workspace_manager.active_workspace_id()],
        )
        prompt_project_files_action.assert_called_once_with(
            title="Save Project",
            text="summary",
            continue_label="Save Project",
            cancel_standard_button=mock.ANY,
            snapshot=snapshot,
            context_key="save",
            allow_repair=True,
            always_prompt=True,
        )
        show_project_files_dialog.assert_called_once_with(
            snapshot=snapshot, allow_repair=True
        )
        repair_project_file_issue.assert_called_once_with(issue)
        prompt_recover_autosave.assert_called_once_with(recovered_project)


    def test_node_property_path_browser_uses_inspector_presenter_surface(
        self,
    ) -> None:
        host = _ProjectHostStub()
        presenter = mock.Mock()
        presenter.browse_node_property_path.return_value = "presenter-path"
        host.shell_inspector_presenter = presenter
        controller = ProjectSessionController(host)  # type: ignore[arg-type]

        resolved = (
            controller._project_files_service._path_browser.browse_node_property_path(  # noqa: SLF001
                "node-1",
                "source_path",
                "current.png",
            )
        )

        self.assertEqual(resolved, "presenter-path")
        presenter.browse_node_property_path.assert_called_once_with(
            "node-1", "source_path", "current.png"
        )
        self.assertEqual(host.browse_calls, [])

    def test_persist_session_prefers_workspace_navigation_surface_over_umbrella_controller(
        self,
    ) -> None:
        host = _ProjectHostStub()
        host.workspace_navigation_controller = _WorkspaceNavigationControllerStub()
        self.assertFalse(hasattr(host, "workspace_library_controller"))
        controller = ProjectSessionController(host)  # type: ignore[arg-type]

        controller.persist_session()

        self.assertEqual(
            host.workspace_navigation_controller.save_active_view_state_calls, 1
        )

    def test_new_project_prefers_workspace_navigation_surface_over_umbrella_controller(
        self,
    ) -> None:
        host = _ProjectHostStub()
        host.workspace_navigation_controller = _WorkspaceNavigationControllerStub()
        self.assertFalse(hasattr(host, "workspace_library_controller"))
        controller = ProjectSessionController(host)  # type: ignore[arg-type]

        controller.new_project()

        self.assertEqual(
            host.workspace_navigation_controller.save_active_view_state_calls, 1
        )
        self.assertEqual(
            host.workspace_navigation_controller.refresh_workspace_tabs_calls, 1
        )
        self.assertEqual(
            len(host.workspace_navigation_controller.switch_workspace_calls), 1
        )

    def test_project_file_repair_prefers_workspace_navigation_surface_over_umbrella_controller(
        self,
    ) -> None:
        host = _ProjectHostStub()
        host.workspace_navigation_controller = _WorkspaceNavigationControllerStub()
        current_workspace_id = host.workspace_manager.active_workspace_id()
        alternate_workspace_id = host.workspace_manager.create_workspace("Other")
        host.workspace_manager.set_active_workspace(current_workspace_id)
        repaired_node = host.model.add_node(
            alternate_workspace_id,
            "media.panel",
            "Broken Image",
            40.0,
            60.0,
            properties={"source": "missing.png"},
        )
        self.assertFalse(hasattr(host, "workspace_library_controller"))
        host.browse_result = "repaired.png"
        controller = ProjectSessionController(host)  # type: ignore[arg-type]
        issue = ProjectFilesBrokenEntry(
            workspace_id=alternate_workspace_id,
            workspace_name="Other",
            node_id=repaired_node.node_id,
            node_title="Broken Image",
            property_key="source",
            property_label="Source Path",
            current_value="missing.png",
            issue_kind="missing_file",
            source_kind="path",
            source_mode="file",
            message="missing",
        )

        repaired = controller._project_files_service.repair_project_file_issue(issue)

        self.assertTrue(repaired)
        self.assertEqual(
            host.workspace_navigation_controller.switch_workspace_calls,
            [alternate_workspace_id, current_workspace_id],
        )
        self.assertEqual(
            host.browse_calls,
            [(repaired_node.node_id, "source", issue.repair_request)],
        )
        self.assertEqual(
            host.scene.property_changes,
            [(repaired_node.node_id, "source", "repaired.png")],
        )

    def test_document_service_solution_bind_seeds_viewer_projection_when_installing_project(
        self,
    ) -> None:
        host = _ProjectHostStub()
        controller = ProjectSessionController(host)  # type: ignore[arg-type]
        project = GraphModel().project
        solution_pointer = {
            "schema_version": 1,
            "solution_namespace_id": "namespace",
            "active_generation_id": "a" * 32,
            "active_manifest_set_digest": "b" * 64,
        }
        project.replace_metadata(
            {**project.metadata, "solution_store": solution_pointer}
        )
        previous_model = host.model

        controller._document_service._install_project(  # noqa: SLF001
            project,
            project_path="example.cxproj",
            reseed_viewer_projection_on_next_reset=True,
        )

        self.assertEqual(len(host.viewer_session_bridge.project_loaded_calls), 1)
        call = host.viewer_session_bridge.project_loaded_calls[0]
        self.assertIs(call["project"], host.model.project)
        self.assertIs(call["registry"], host.registry)
        self.assertTrue(call["reseed_on_next_reset"])
        self.assertEqual(host.runtime_history.clear_all_calls, 1)
        self.assertEqual(host.run_controller.reset_runtime_solution_state_calls, 1)
        host.execution_client.reset_project_session.assert_called_once_with(
            project.project_id,
            "example.cxproj",
        )
        host.execution_client.bind_project_solution_store.assert_called_once_with(
            project.project_id,
            "example.cxproj",
            solution_pointer,
        )
        self.assertEqual(host.run_controller.models_seen_at_reset, [previous_model])
        self.assertIsNot(host.model, previous_model)
        self.assertEqual(host.viewer_host_service.reset_calls, ["project_install"])
        self.assertEqual(
            host.install_events[:2],
            [("viewer_host_reset", "project_install"), ("viewer_project_loaded", "")],
        )
        self.assertEqual(len(host.library_pane_reset_requested.emit_calls), 1)
        self.assertEqual(len(host.node_library_changed.emit_calls), 1)

    def test_install_project_clears_retained_node_timing_and_warning_state(
        self,
    ) -> None:
        host = _ProjectHostStub()
        controller = ProjectSessionController(host)  # type: ignore[arg-type]
        project = GraphModel().project
        host.run_state.running_node_started_at_epoch_ms_by_node_id = {
            "node_live": 1200.0,
        }
        host.run_state.cached_node_elapsed_ms_by_workspace_id = {
            "ws_a": {
                "node_1": 15.5,
            }
        }
        host.run_state.runtime_warning_messages_by_workspace_id = {
            "ws_a": {
                "node_1": ("Review the previous result.",),
            }
        }
        host.run_state.node_execution_revision = 7

        controller._document_service._install_project(  # noqa: SLF001
            project,
            project_path="example.cxproj",
            reseed_viewer_projection_on_next_reset=False,
        )

        self.assertEqual(host.run_state.running_node_started_at_epoch_ms_by_node_id, {})
        self.assertEqual(host.run_state.cached_node_elapsed_ms_by_workspace_id, {})
        self.assertEqual(host.run_state.runtime_warning_messages_by_workspace_id, {})
        self.assertEqual(host.run_state.node_execution_revision, 8)
        self.assertEqual(len(host.node_execution_state_changed.emit_calls), 1)

    def test_new_project_seeds_viewer_projection_for_pending_reset_restore(
        self,
    ) -> None:
        host = _ProjectHostStub()
        controller = ProjectSessionController(host)  # type: ignore[arg-type]

        controller.new_project()

        self.assertEqual(len(host.viewer_session_bridge.project_loaded_calls), 1)
        call = host.viewer_session_bridge.project_loaded_calls[0]
        self.assertIs(call["project"], host.model.project)
        self.assertTrue(call["reseed_on_next_reset"])
        self.assertEqual(host.runtime_history.clear_all_calls, 1)
        self.assertEqual(
            host.workspace_navigation_controller.refresh_workspace_tabs_calls, 1
        )
        self.assertEqual(
            len(host.workspace_navigation_controller.switch_workspace_calls), 1
        )
        active_workspace_id = host.workspace_manager.active_workspace_id()
        self.assertEqual(
            host.run_controller.evaluate_workspace_on_open_calls,
            [active_workspace_id],
        )
        self.assertEqual(
            host.run_controller.selected_workspaces_seen_at_evaluation,
            [active_workspace_id],
        )
        self.assertEqual(
            host.project_session_state.last_autosave_fingerprint,
            "",
        )
        self.assertEqual(host.session_store.autosave_calls, [])
        self.assertEqual(len(host.session_store.persist_calls), 1)
        self.assertEqual(
            host.session_store.persist_calls[0]["autosave_resume_fingerprint"],
            "",
        )
        self.assertEqual(len(host.project_meta_changed.emit_calls), 1)

    def test_restore_script_editor_state_requires_selected_node_for_visibility(
        self,
    ) -> None:
        host = _ProjectHostStub()
        host.model.project.metadata = {
            "ui": {
                "script_editor": {
                    "visible": True,
                    "floating": True,
                    "width": 612.0,
                }
            }
        }
        controller = ProjectSessionController(host)  # type: ignore[arg-type]

        controller.restore_script_editor_state()
        self.assertTrue(host.script_editor.floating)
        self.assertEqual(host.script_editor.panel_width, 612.0)
        self.assertFalse(host.script_editor.visible)
        self.assertFalse(host.action_toggle_script_editor.checked)

        host.scene = _SceneStub(selected_node_id="node_1")
        controller.restore_script_editor_state()
        self.assertTrue(host.script_editor.visible)
        self.assertTrue(host.action_toggle_script_editor.checked)

    def test_close_session_discards_staged_scratch_and_persists_lightweight_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            host = _ProjectHostStub(Path(temp_dir))
            staging_root = host.session_store.staging_workspace_root() / "project-123"
            payload_path = (
                staging_root
                / "nodes"
                / "Image Panel [11111111]"
                / "tmp"
                / "out"
                / "outputs"
                / "run.txt"
            )
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            payload_path.write_text("payload", encoding="utf-8")
            host.model.project.metadata = {
                "artifact_store": {
                    "staging_root": {
                        "kind": "session_temp",
                        "absolute_path": str(staging_root),
                    },
                    "staged": {
                        "pending_output": {
                            "relative_path": "nodes/Image Panel [11111111]/tmp/out/outputs/run.txt",
                            "slot": "process_run.stdout",
                        }
                    },
                }
            }
            controller = ProjectSessionController(host)  # type: ignore[arg-type]

            controller.close_session()

            self.assertFalse(staging_root.exists())
            self.assertEqual(host.session_store.discard_calls, 1)
            self.assertEqual(len(host.session_store.persist_calls), 1)
            self.assertNotIn("project_doc", host.session_store.persist_calls[0])
            self.assertNotIn(
                "staging_root", host.model.project.metadata["artifact_store"]
            )
            self.assertIn(
                "pending_output",
                host.model.project.metadata["artifact_store"]["staged"],
            )
            self.assertEqual(
                host.workspace_navigation_controller.save_active_view_state_calls, 1
            )

    def test_persist_session_omits_project_doc_from_recent_session_payload(
        self,
    ) -> None:
        host = _ProjectHostStub()
        host.project_session_state.recent_project_paths = ["alpha.cxproj"]
        controller = ProjectSessionController(host)  # type: ignore[arg-type]

        controller.persist_session()

        self.assertEqual(len(host.session_store.persist_calls), 1)
        persisted_session = host.session_store.persist_calls[0]
        self.assertEqual(persisted_session["recent_project_paths"], ["alpha.cxproj"])
        self.assertNotIn("project_doc", persisted_session)

    def test_autosave_tick_skips_document_build_when_document_epoch_is_unchanged(
        self,
    ) -> None:
        host = _ProjectHostStub()
        controller = ProjectSessionController(host)  # type: ignore[arg-type]

        controller.autosave_tick()
        controller.autosave_tick()

        self.assertEqual(host.serializer.to_document_calls, 1)
        self.assertEqual(len(host.session_store.autosave_calls), 1)
        self.assertEqual(len(host.session_store.persist_calls), 2)
        self.assertEqual(
            host.workspace_navigation_controller.save_active_view_state_calls, 2
        )

    def test_autosave_tick_rebuilds_after_document_epoch_sources_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            host = _ProjectHostStub(Path(temp_dir))
            controller = ProjectSessionController(host)  # type: ignore[arg-type]

            controller.autosave_tick()
            self.assertEqual(host.serializer.to_document_calls, 1)

            host.model.add_node(
                host.model.active_workspace.workspace_id,
                "core.constant",
                "Constant",
                10.0,
                20.0,
            )
            controller.autosave_tick()
            self.assertEqual(host.serializer.to_document_calls, 2)

            host.model.workspace_view_mutations(
                host.model.active_workspace.workspace_id
            ).save_active_view_state(
                zoom=1.25,
                pan_x=10.0,
                pan_y=-5.0,
            )
            controller.autosave_tick()
            self.assertEqual(host.serializer.to_document_calls, 3)

            host.model.project.replace_metadata({"custom": "value"})
            controller.autosave_tick()
            self.assertEqual(host.serializer.to_document_calls, 4)

            host.script_editor.set_width(640.0)
            controller.autosave_tick()
            self.assertEqual(host.serializer.to_document_calls, 5)

            controller.ensure_project_staging_root()
            controller.autosave_tick()
            self.assertEqual(host.serializer.to_document_calls, 6)

            host.workspace_manager.create_workspace("Second")
            controller.autosave_tick()
            self.assertEqual(host.serializer.to_document_calls, 7)

            controller.autosave_tick()
            self.assertEqual(host.serializer.to_document_calls, 7)

    def test_persist_session_uses_supplied_project_doc_for_autosave(self) -> None:
        host = _ProjectHostStub()
        host.project_session_state.last_autosave_fingerprint = "previous-fingerprint"
        supplied_doc = {
            "project_id": "supplied_project",
            "name": "Supplied Project",
            "metadata": {"source": "caller-owned"},
        }
        controller = ProjectSessionController(host)  # type: ignore[arg-type]

        controller.persist_session(supplied_doc)

        self.assertEqual(host.serializer.to_document_calls, 0)
        self.assertEqual(len(host.session_store.autosave_calls), 1)
        autosave_call = host.session_store.autosave_calls[0]
        self.assertNotIn("project_doc", autosave_call)
        self.assertEqual(autosave_call["last_fingerprint"], "previous-fingerprint")
        snapshot = autosave_call["project_snapshot"]
        self.assertIsInstance(snapshot, ProjectDocumentSnapshot)
        self.assertIs(snapshot.document, supplied_doc)
        self.assertEqual(len(host.session_store.persist_calls), 1)
        self.assertNotIn("project_doc", host.session_store.persist_calls[0])


if __name__ == "__main__":
    unittest.main()
