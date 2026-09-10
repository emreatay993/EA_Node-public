# Purpose: Facade project-session actions and the public staged-artifact API.
# Map: feature_routes/project_session_files_managed_artifacts.md
# Tests: tests/test_project_file_staging.py, tests/test_project_session_controller_unit.py

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.ui.dialogs.project_files_dialog import ProjectFilesBrokenEntry, ProjectFilesSnapshot
from ea_node_editor.ui.shell.controllers.project_session_services import (
    ProjectDocumentIOService,
    ProjectFilesService,
    ProjectSessionLifecycleService,
    normalize_project_path_value,
    normalized_recent_project_paths_value,
)


class ProjectSessionController:
    _RECENT_PROJECT_LIMIT = 10

    def __init__(self, host: Any) -> None:
        self._host = host
        dialog_parent_source = _DialogParentSourceAdapter(host)
        workspace_session = _WorkspaceSessionAdapter(host)
        self._project_files_service = ProjectFilesService(
            host,
            dialog_parent_source=dialog_parent_source,
            path_browser=_NodePropertyPathBrowserAdapter(host),
            workspace_session=workspace_session,
        )
        self._session_service = ProjectSessionLifecycleService(
            host,
            project_files=self._project_files_service,
            workspace_session=workspace_session,
            recent_projects_menu=_RecentProjectsMenuAdapter(host),
            recovery_prompt=_AutosaveRecoveryPromptAdapter(host),
        )
        self._document_service = ProjectDocumentIOService(
            host,
            project_files=self._project_files_service,
            session=self._session_service,
            dialog_parent_source=dialog_parent_source,
            workspace_session=workspace_session,
            script_editor_panel=_ScriptEditorPanelAdapter(host),
            viewer_project_loader=_ViewerProjectLoaderAdapter(host),
        )
        self._session_service.bind_document_service(self._document_service)

    @classmethod
    def _normalize_project_path(cls, path: str | Path | object) -> str:
        return normalize_project_path_value(path)

    @classmethod
    def _normalized_recent_project_paths(cls, paths: Iterable[object]) -> list[str]:
        return normalized_recent_project_paths_value(paths, limit=cls._RECENT_PROJECT_LIMIT)

    def set_recent_project_paths(self, paths: Iterable[object], *, persist: bool = True) -> list[str]:
        return self._session_service.set_recent_project_paths(paths, persist=persist)

    def add_recent_project_path(self, path: str | Path, *, persist: bool = True) -> list[str]:
        return self._session_service.add_recent_project_path(path, persist=persist)

    def remove_recent_project_path(self, path: str | Path, *, persist: bool = True) -> list[str]:
        return self._session_service.remove_recent_project_path(path, persist=persist)

    def clear_recent_projects(self) -> None:
        self._session_service.clear_recent_projects()

    def project_artifact_store(self) -> ProjectArtifactStore:
        return self._project_files_service.project_artifact_store()

    def replace_project_artifact_store(self, store: ProjectArtifactStore) -> bool:
        changed = self._project_files_service.replace_project_artifact_store(store)
        if changed:
            self._host.project_meta_changed.emit()
        return changed

    def ensure_project_staging_root(self) -> Path:
        return self._project_files_service.ensure_project_staging_root()

    def discard_staged_scratch_data(self) -> None:
        self._project_files_service.discard_staged_scratch_data()

    def stage_node_artifact_file(
        self,
        source_path: str | Path,
        *,
        artifact_prefix: str,
        io_dir: str,
        artifact_id: str = "",
        subdirectory: str = "",
        filename: str = "",
        entry_metadata: Mapping[str, Any] | None = None,
        node_id: str = "",
        node_title: str = "",
        node_type: str = "",
    ) -> str:
        ref = self._project_files_service.stage_node_artifact_file(
            source_path,
            artifact_prefix=artifact_prefix,
            io_dir=io_dir,
            artifact_id=artifact_id,
            subdirectory=subdirectory,
            filename=filename,
            entry_metadata=entry_metadata,
            node_id=node_id,
            node_title=node_title,
            node_type=node_type,
        )
        if ref:
            self._host.project_meta_changed.emit()
        return ref

    def stage_node_artifact_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        mime_type: str,
        artifact_prefix: str,
        subdirectory: str,
        artifact_kind: str,
        node_id: str = "",
        node_title: str = "",
        node_type: str = "",
    ) -> str:
        try:
            ref = self._project_files_service.stage_node_artifact_bytes(
                data,
                filename=filename,
                mime_type=mime_type,
                artifact_prefix=artifact_prefix,
                subdirectory=subdirectory,
                artifact_kind=artifact_kind,
                node_id=node_id,
                node_title=node_title,
                node_type=node_type,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return ""
        if ref:
            self._host.project_meta_changed.emit()
        return ref

    def create_blank_notebook_artifact(
        self,
        node_id: str = "",
        *,
        kernel_name: str = "",
    ) -> str:
        ref = self._project_files_service.create_blank_notebook_artifact(
            node_id,
            kernel_name=kernel_name,
        )
        if ref:
            self._host.project_meta_changed.emit()
        return ref

    def ensure_project_metadata_defaults(self) -> None:
        self._document_service.ensure_project_metadata_defaults()

    def workflow_settings_payload(self) -> dict[str, Any]:
        return self._document_service.workflow_settings_payload()

    def persist_script_editor_state(self) -> None:
        self._document_service.persist_script_editor_state()

    def restore_script_editor_state(self) -> None:
        self._document_service.restore_script_editor_state()

    def show_workflow_settings_dialog(self) -> None:
        self._document_service.show_workflow_settings_dialog()

    def set_script_editor_panel_visible(self, checked: bool | None = None) -> None:
        self._document_service.set_script_editor_panel_visible(checked)

    def _install_project(self, project: ProjectData, *, project_path: str) -> None:
        self._document_service._install_project(project, project_path=project_path)

    def _finalize_loaded_project(self, project: ProjectData, *, project_path: str) -> None:
        self._document_service._finalize_loaded_project(project, project_path=project_path)

    def _default_save_as_path(self) -> str:
        return self._document_service._default_save_as_path()

    def build_project_files_snapshot(
        self,
        *,
        project: ProjectData | None = None,
        project_path: str | Path | None = None,
    ) -> ProjectFilesSnapshot:
        return self._project_files_service.build_project_files_snapshot(
            project=project,
            project_path=project_path,
        )

    @staticmethod
    def _count_text(count: int, noun: str) -> str:
        return ProjectFilesService._count_text(count, noun)

    @staticmethod
    def _project_files_prompt_headline(snapshot: ProjectFilesSnapshot) -> str:
        return ProjectFilesService._project_files_prompt_headline(snapshot)

    @classmethod
    def _project_files_prompt_details(cls, *, context_key: str, snapshot: ProjectFilesSnapshot) -> str:
        return ProjectFilesService._project_files_prompt_details(context_key=context_key, snapshot=snapshot)

    def _prompt_project_files_action(
        self,
        *,
        title: str,
        text: str,
        continue_label: str,
        cancel_standard_button,
        snapshot: ProjectFilesSnapshot,
        context_key: str,
        allow_repair: bool,
        always_prompt: bool = False,
    ) -> bool:
        return self._project_files_service.prompt_project_files_action(
            title=title,
            text=text,
            continue_label=continue_label,
            cancel_standard_button=cancel_standard_button,
            snapshot=snapshot,
            context_key=context_key,
            allow_repair=allow_repair,
            always_prompt=always_prompt,
        )

    def show_project_files_dialog(
        self,
        *,
        snapshot: ProjectFilesSnapshot | None = None,
        allow_repair: bool | None = None,
    ) -> None:
        self._project_files_service.show_project_files_dialog(
            snapshot=snapshot,
            allow_repair=allow_repair,
        )

    def _repair_project_file_issue(self, issue: ProjectFilesBrokenEntry) -> bool:
        return self._project_files_service.repair_project_file_issue(issue)

    def _rewrite_live_project_artifact_refs(self, replacements: dict[str, str]) -> None:
        self._document_service._rewrite_live_project_artifact_refs(replacements)

    def save_project(self):  # noqa: ANN201
        return self._document_service.save_project()

    def save_project_as(self):  # noqa: ANN201
        return self._document_service.save_project_as()

    def new_project(self) -> bool:
        replaced = bool(self._document_service.new_project())
        if replaced:
            self._reset_runtime_surfaces_after_project_change()
        return replaced

    def open_project(self) -> bool:
        opened = bool(self._document_service.open_project())
        if opened:
            self._reset_runtime_surfaces_after_project_change()
        return opened

    def open_project_path(self, path: str | Path, *, show_errors: bool = True) -> bool:
        opened = bool(self._document_service.open_project_path(path, show_errors=show_errors))
        if opened:
            self._reset_runtime_surfaces_after_project_change()
        return opened



    def restore_session(self) -> None:
        self._session_service.restore_session()

    def discard_autosave_snapshot(self) -> None:
        self._session_service.discard_autosave_snapshot()

    def recover_autosave_if_newer(self) -> ProjectData | None:
        return self._session_service.recover_autosave_if_newer()

    def prompt_recover_autosave(self, recovered_project: ProjectData | None = None):
        return self._session_service.prompt_recover_autosave(recovered_project)

    def process_deferred_autosave_recovery(self) -> None:
        before_project_object_id = id(self._host.model.project)
        self._session_service.process_deferred_autosave_recovery()
        if id(self._host.model.project) != before_project_object_id:
            self._reset_runtime_surfaces_after_project_change()

    def autosave_tick(self) -> None:
        self._session_service.autosave_tick()

    def close_session(self) -> None:
        self._session_service.close_session()

    def persist_session(self, project_doc: dict[str, Any] | None = None) -> None:
        self._session_service.persist_session(project_doc)

    def _reset_runtime_surfaces_after_project_change(self) -> None:
        self._host.run_projection_controller.clear_run_failure_focus()
        reset_viewer_session_bridge = getattr(self._host, "_reset_viewer_session_bridge", None)
        if callable(reset_viewer_session_bridge):
            reset_viewer_session_bridge(reason="project_close")
        workspace_id = str(self._host.workspace_manager.active_workspace_id() or "").strip()
        evaluate_workspace_on_open = getattr(
            getattr(self._host, "run_controller", None),
            "evaluate_workspace_on_open",
            None,
        )
        if workspace_id and callable(evaluate_workspace_on_open):
            evaluate_workspace_on_open(workspace_id)


class _DialogParentSourceAdapter:
    def __init__(self, host: Any) -> None:
        self._host = host

    def dialog_parent(self) -> object | None:
        from PyQt6.QtWidgets import QWidget

        dialog_parent_host = getattr(self._host, "dialog_parent_host", self._host)
        return dialog_parent_host if isinstance(dialog_parent_host, QWidget) else None


class _WorkspaceSessionAdapter:
    def __init__(self, host: Any) -> None:
        self._host = host

    def _navigation_surface(self) -> Any:
        navigation_controller = getattr(self._host, "workspace_navigation_controller", None)
        if navigation_controller is None:
            raise RuntimeError("Project session workspace surface is unavailable.")
        return navigation_controller

    def save_active_view_state(self) -> None:
        self._navigation_surface().save_active_view_state()

    def refresh_workspace_tabs(self) -> None:
        self._navigation_surface().refresh_workspace_tabs()

    def switch_workspace(self, workspace_id: str) -> None:
        self._navigation_surface().switch_workspace(workspace_id)


class _NodePropertyPathBrowserAdapter:
    def __init__(self, host: Any) -> None:
        self._host = host

    def browse_node_property_path(self, node_id: str, key: str, current_path: str) -> str:
        return str(
            self._host.shell_inspector_presenter.browse_node_property_path(
                node_id,
                key,
                current_path,
            )
            or ""
        )


class _RecentProjectsMenuAdapter:
    def __init__(self, host: Any) -> None:
        self._host = host

    def refresh_recent_projects_menu(self) -> None:
        refresh_menu = getattr(self._host, "_refresh_recent_projects_menu", None)
        if callable(refresh_menu):
            refresh_menu()


class _AutosaveRecoveryPromptAdapter:
    def __init__(self, host: Any) -> None:
        self._host = host

    def is_visible(self) -> bool:
        is_visible = getattr(self._host, "isVisible", None)
        if not callable(is_visible):
            return True
        return bool(is_visible())

    def prompt_recover_autosave(self, recovered_project=None):  # noqa: ANN001
        prompt = getattr(self._host, "_prompt_recover_autosave", None)
        if not callable(prompt):
            raise RuntimeError("Project session autosave recovery prompt is unavailable.")
        return prompt(recovered_project)


class _ScriptEditorPanelAdapter:
    def __init__(self, host: Any) -> None:
        self._host = host

    @property
    def visible(self) -> bool:
        return bool(self._host.script_editor.visible)

    @property
    def floating(self) -> bool:
        return bool(self._host.script_editor.floating)

    @property
    def width(self) -> float:
        return float(self._host.script_editor.panel_width)

    def set_floating(self, value: bool) -> None:
        self._host.script_editor.set_floating(value)

    def set_width(self, value: float) -> None:
        self._host.script_editor.set_width(value)

    def set_visible(self, value: bool) -> None:
        self._host.script_editor.set_visible(value)

    def set_checked(self, value: bool) -> None:
        self._host.action_toggle_script_editor.setChecked(value)

    def set_node(self, node: object) -> None:
        self._host.script_editor.set_node(node)

    def focus_editor(self) -> None:
        self._host.script_editor.focus_editor()


class _ViewerProjectLoaderAdapter:
    def __init__(self, host: Any) -> None:
        self._host = host

    def project_loaded(
        self,
        project,
        registry,
        *,
        reseed_on_next_reset: bool = False,
    ) -> None:  # noqa: ANN001
        viewer_session_bridge = getattr(self._host, "viewer_session_bridge", None)
        if viewer_session_bridge is None:
            return
        project_loaded = getattr(viewer_session_bridge, "project_loaded", None)
        if not callable(project_loaded):
            return
        project_loaded(
            project,
            registry,
            reseed_on_next_reset=reseed_on_next_reset,
        )
