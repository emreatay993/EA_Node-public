from __future__ import annotations

import copy
import json
import os
import shutil
import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.graph.registry_normalization import normalize_project_for_registry
from ea_node_editor.common.payload_tools import artifact_content_integrity
from ea_node_editor.persistence.artifact_store import (
    ProjectArtifactSaveStage,
    ProjectArtifactLayout,
    ProjectArtifactStore,
    validate_owned_artifact_path,
)
from ea_node_editor.persistence.image_blobs import collect_project_image_garbage
from ea_node_editor.persistence.project_codec import (
    collect_project_artifact_references,
    rewrite_project_artifact_refs,
)
from ea_node_editor.persistence.serializer import (
    ProjectDocumentSnapshot,
    ProjectSessionMetadata,
    StagedProjectDocument,
)
from ea_node_editor.persistence.session_store import SessionAutosaveStore
from ea_node_editor.settings import PROJECT_ARTIFACT_STORE_METADATA_KEY
from ea_node_editor.ui.shell.controllers.project_session_services_support.project_files_service import (
    ProjectFilesService,
)
from ea_node_editor.ui.shell.controllers.project_session_services_support.session_lifecycle_service import (
    ProjectSessionLifecycleService,
)
from ea_node_editor.ui.shell.controllers.project_session_services_support.shared import (
    _ProjectDocumentIOHostProtocol,
    _ProjectSessionHostProtocol,
    _ScriptEditorPanelProtocol,
    _ViewerProjectLoaderProtocol,
    _WorkspaceSessionProtocol,
    normalize_project_path_value,
)
from ea_node_editor.ui.shell.workspace_flow import ShellWorkspaceManagerAdapter
from ea_node_editor.workspace.manager import WorkspaceManager

SAVE_FREE_SPACE_RESERVE_BYTES = 16_777_216
_SAVE_STATUSES = frozenset({"cancelled", "saved", "failed", "committed_not_adopted"})
_SAVE_REASON_CODES = frozenset(
    {
        "save_cancelled",
        "save_succeeded",
        "save_in_progress",
        "save_destination_invalid",
        "save_destination_exists",
        "save_destination_sidecar_exists",
        "save_destination_unsafe",
        "save_destination_overlaps_source",
        "save_destination_space_insufficient",
        "save_source_changed",
        "save_document_invalid",
        "save_artifact_stage_failed",
        "save_solution_stage_failed",
        "save_image_digest_conflict",
        "save_project_stage_failed",
        "save_project_commit_failed",
        "save_committed_not_adopted_source_changed",
        "save_committed_not_adopted_reopen_failed",
        "save_committed_not_adopted_verification_failed",
        "save_committed_not_adopted_binding_failed",
    }
)


@dataclass(frozen=True, slots=True)
class ProjectSaveToken:
    save_id: str
    project_object_identity: int
    project_id: str
    normalized_source_path: str
    project_document_epoch: tuple[Any, ...]
    persistent_document_fingerprint: str
    solution_snapshot_token: str

    def __post_init__(self) -> None:
        if (
            len(self.save_id) != 32
            or any(character not in "0123456789abcdef" for character in self.save_id)
            or type(self.project_object_identity) is not int
            or self.project_object_identity < 0
            or not isinstance(self.project_id, str)
            or not self.project_id.strip()
            or not isinstance(self.project_document_epoch, tuple)
            or not isinstance(self.normalized_source_path, str)
            or len(self.persistent_document_fingerprint) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.persistent_document_fingerprint
            )
            or len(self.solution_snapshot_token) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.solution_snapshot_token
            )
        ):
            raise ValueError("project save token is invalid")


@dataclass(frozen=True, slots=True)
class ProjectSaveResult:
    status: str
    reason_code: str
    target_path: str

    def __post_init__(self) -> None:
        if self.status not in _SAVE_STATUSES or self.reason_code not in _SAVE_REASON_CODES:
            raise ValueError("project save result is invalid")
        if (
            (self.status == "cancelled") != (self.reason_code == "save_cancelled")
            or (self.status == "saved") != (self.reason_code == "save_succeeded")
            or (
                self.status == "committed_not_adopted"
                and not self.reason_code.startswith("save_committed_not_adopted_")
            )
            or (
                self.status == "failed"
                and self.reason_code.startswith("save_committed_not_adopted_")
            )
        ):
            raise ValueError("project save result status is inconsistent")


@dataclass(slots=True)
class _SaveCoreOutcome:
    result: ProjectSaveResult
    runtime_document: dict[str, Any] | None = None


def _save_path_identity(path: Path, *, content_sensitive: bool) -> tuple[int, ...] | None:
    try:
        path_stat = os.lstat(path)
    except FileNotFoundError:
        return None
    identity = (
        int(path_stat.st_dev),
        int(path_stat.st_ino),
        int(path_stat.st_mode),
        int(getattr(path_stat, "st_file_attributes", 0)),
    )
    if not content_sensitive:
        return identity
    return (*identity, int(path_stat.st_size), int(path_stat.st_mtime_ns))



class ProjectDocumentIOService:
    def __init__(
        self,
        host: _ProjectDocumentIOHostProtocol,
        *,
        project_files: ProjectFilesService,
        session: ProjectSessionLifecycleService,
        dialog_parent_source: _ProjectSessionHostProtocol,
        workspace_session: _WorkspaceSessionProtocol,
        script_editor_panel: _ScriptEditorPanelProtocol,
        viewer_project_loader: _ViewerProjectLoaderProtocol,
    ) -> None:
        self._host = host
        self._project_files = project_files
        self._session = session
        self._dialog_parent_source = dialog_parent_source
        self._workspace_session = workspace_session
        self._script_editor_panel = script_editor_panel
        self._viewer_project_loader = viewer_project_loader
        self._save_guard = threading.Lock()
        self._deferred_artifact_cleanup: dict[str, tuple[str, ...]] = {}
        self._deferred_image_cleanup: dict[str, tuple[str, ...]] = {}
        self._deferred_solution_cleanup: dict[str, Any] = {}

    def _dialog_parent(self) -> object | None:
        return self._dialog_parent_source.dialog_parent()

    def _confirm_project_replacement(
        self,
        *,
        title: str,
        action_text: str,
    ) -> bool:
        if not any(
            bool(workspace.dirty)
            for workspace in self._host.model.project.workspaces.values()
        ):
            return True

        from PyQt6.QtWidgets import QMessageBox

        dialog = QMessageBox(self._dialog_parent())
        dialog.setWindowTitle(title)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText("The current project has unsaved changes.")
        dialog.setInformativeText(f"Discard those changes and {action_text}?")
        discard_button = dialog.addButton(
            "Discard Changes",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        return dialog.clickedButton() is discard_button

    def ensure_project_metadata_defaults(self) -> None:
        session_metadata = ProjectSessionMetadata.from_mapping(
            self._host.model.project.metadata
        )
        self._host.model.project.replace_metadata(session_metadata.to_mapping())

    def workflow_settings_payload(self) -> dict[str, Any]:
        session_metadata = ProjectSessionMetadata.from_mapping(
            self._host.model.project.metadata
        )
        self._host.model.project.replace_metadata(session_metadata.to_mapping())
        return copy.deepcopy(session_metadata.workflow_settings)

    def _metadata_with_script_editor_state(
        self,
        metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        session_metadata = ProjectSessionMetadata.from_mapping(metadata)
        return session_metadata.with_script_editor_state(
            visible=self._script_editor_panel.visible,
            floating=self._script_editor_panel.floating,
            width=self._script_editor_panel.width,
        ).to_mapping()

    def persist_script_editor_state(self) -> None:
        updated_metadata = self._metadata_with_script_editor_state(
            self._host.model.project.metadata
        )
        self._host.model.project.replace_metadata(updated_metadata)

    def restore_script_editor_state(self) -> None:
        session_metadata = ProjectSessionMetadata.from_mapping(
            self._host.model.project.metadata
        )
        self._host.model.project.replace_metadata(session_metadata.to_mapping())
        state = session_metadata.ui.script_editor
        selected_node_id = self._host.scene.selected_node_id() or ""
        can_show_editor = bool(selected_node_id)
        visible = state.visible and can_show_editor
        floating = state.floating
        self._script_editor_panel.set_floating(floating)
        self._script_editor_panel.set_width(state.width)
        self._script_editor_panel.set_visible(visible)
        self._script_editor_panel.set_checked(visible)

    def _project_viewer_bridge_loaded(self, *, reseed_on_next_reset: bool) -> None:
        self._viewer_project_loader.project_loaded(
            self._host.model.project,
            self._host.registry,
            reseed_on_next_reset=reseed_on_next_reset,
        )

    def _reset_viewer_host_service_for_project_install(self) -> None:
        reset = getattr(getattr(self._host, "viewer_host_service", None), "reset", None)
        if callable(reset):
            reset(reason="project_install")

    def _clear_node_timing_and_warning_state_for_project_install(self) -> None:
        self._host.run_projection_controller.clear_node_timing_and_warning_state()

    def show_workflow_settings_dialog(self) -> None:
        from ea_node_editor.ui.dialogs.workflow_settings_dialog import (
            WorkflowSettingsDialog,
        )

        project = self._host.model.project
        session_metadata = ProjectSessionMetadata.from_mapping(
            copy.deepcopy(project.metadata)
        )
        dialog = WorkflowSettingsDialog(
            initial_settings=copy.deepcopy(session_metadata.workflow_settings),
            application_default_python_executable=(
                self._host.app_preferences_controller.default_python_executable()
            ),
            parent=self._dialog_parent(),
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._host.app_preferences_controller.set_default_python_executable(
                dialog.application_default_python_executable()
            )
        except Exception as exc:  # noqa: BLE001
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self._dialog_parent(),
                "Workflow Settings",
                f"Could not save the application Python runtime.\n{str(exc)[:500]}",
            )
            return
        updated_metadata = session_metadata.with_workflow_settings(
            dialog.values()
        ).to_mapping()
        project.replace_metadata(updated_metadata)
        self._session.persist_session()

    def set_script_editor_panel_visible(self, checked: bool | None = None) -> None:
        target_visible = (
            bool(checked)
            if checked is not None
            else not self._script_editor_panel.visible
        )
        self._script_editor_panel.set_visible(target_visible)
        self._script_editor_panel.set_checked(target_visible)
        self.persist_script_editor_state()
        if target_visible:
            node_id = self._host.scene.selected_node_id()
            if node_id:
                workspace = self._host.model.project.workspaces[
                    self._host.workspace_manager.active_workspace_id()
                ]
                self._script_editor_panel.set_node(workspace.nodes.get(node_id))
            self._script_editor_panel.focus_editor()

    def _install_project(
        self,
        project: ProjectData,
        *,
        project_path: str,
        reseed_viewer_projection_on_next_reset: bool = False,
        _save_guard_held: bool = False,
    ) -> None:
        if not _save_guard_held:
            if not self._save_guard.acquire(blocking=False):
                raise RuntimeError("save_in_progress")
            try:
                self._install_project(
                    project,
                    project_path=project_path,
                    reseed_viewer_projection_on_next_reset=(
                        reseed_viewer_projection_on_next_reset
                    ),
                    _save_guard_held=True,
                )
            finally:
                self._save_guard.release()
            return
        self._clear_node_timing_and_warning_state_for_project_install()
        normalize_project_for_registry(project, self._host.registry)
        run_controller = getattr(self._host, "run_controller", None)
        reset_runtime_solution_state = getattr(
            run_controller,
            "reset_runtime_solution_state",
            None,
        )
        if callable(reset_runtime_solution_state):
            reset_runtime_solution_state()
        execution_client = getattr(self._host, "execution_client", None)
        reset_project_session = getattr(
            execution_client,
            "reset_project_session",
            None,
        )
        if callable(reset_project_session):
            reset_project_session(project.project_id, project_path)
        bind_project_solution_store = getattr(
            execution_client,
            "bind_project_solution_store",
            None,
        )
        if callable(bind_project_solution_store):
            metadata = project.metadata if isinstance(project.metadata, Mapping) else {}
            bind_project_solution_store(
                project.project_id,
                project_path,
                metadata.get("solution_store"),
            )
        self._host.model = GraphModel(project)
        self._host.workspace_manager = ShellWorkspaceManagerAdapter(
            WorkspaceManager(self._host.model), self._host.model
        )
        self._host.runtime_history.clear_all()
        self._host.project_path = project_path
        self._reset_viewer_host_service_for_project_install()
        self._project_viewer_bridge_loaded(
            reseed_on_next_reset=reseed_viewer_projection_on_next_reset,
        )
        self._host.library_pane_reset_requested.emit()
        self._host.node_library_changed.emit()

    def _finalize_loaded_project(
        self,
        project: ProjectData,
        *,
        project_path: str,
        _save_guard_held: bool = False,
    ) -> None:
        if not _save_guard_held:
            if not self._save_guard.acquire(blocking=False):
                raise RuntimeError("save_in_progress")
            try:
                self._finalize_loaded_project(
                    project,
                    project_path=project_path,
                    _save_guard_held=True,
                )
            finally:
                self._save_guard.release()
            return
        resolved_path = Path(project_path)
        self._install_project(
            project,
            project_path=str(resolved_path),
            reseed_viewer_projection_on_next_reset=True,
            _save_guard_held=True,
        )
        self.ensure_project_metadata_defaults()
        try:
            self._session._session_state.last_manual_save_ts = (
                resolved_path.stat().st_mtime
            )
        except OSError:
            self._session._session_state.last_manual_save_ts = time.time()
        self._session.discard_autosave_snapshot()
        self._session.add_recent_project_path(str(resolved_path), persist=False)
        self._workspace_session.refresh_workspace_tabs()
        self._workspace_session.switch_workspace(
            self._host.model.active_workspace.workspace_id
        )
        self.restore_script_editor_state()
        self._workspace_session.save_active_view_state()
        runtime_document = self._host.serializer.to_document(self._host.model.project)
        self._session._session_state.last_autosave_fingerprint = (
            SessionAutosaveStore.document_fingerprint(runtime_document)
        )
        self._session.persist_session(runtime_document)
        self._host.project_meta_changed.emit()

    def _finalize_unsaved_project(
        self,
        project: ProjectData,
        *,
        create_resume_snapshot: bool,
        _save_guard_held: bool = False,
    ) -> None:
        if not _save_guard_held:
            if not self._save_guard.acquire(blocking=False):
                raise RuntimeError("save_in_progress")
            try:
                self._finalize_unsaved_project(
                    project,
                    create_resume_snapshot=create_resume_snapshot,
                    _save_guard_held=True,
                )
            finally:
                self._save_guard.release()
            return
        self._install_project(
            project,
            project_path="",
            reseed_viewer_projection_on_next_reset=True,
            _save_guard_held=True,
        )
        self._finalize_installed_unsaved_project(
            create_resume_snapshot=create_resume_snapshot
        )

    def _finalize_installed_unsaved_project(
        self,
        *,
        create_resume_snapshot: bool,
    ) -> None:
        self.ensure_project_metadata_defaults()
        self._session._session_state.last_manual_save_ts = 0.0
        self._session.discard_autosave_snapshot()
        self._workspace_session.refresh_workspace_tabs()
        self._workspace_session.switch_workspace(
            self._host.model.active_workspace.workspace_id
        )
        self.restore_script_editor_state()
        self._workspace_session.save_active_view_state()
        self._session._session_state.last_autosave_fingerprint = ""
        if create_resume_snapshot:
            runtime_document = self._host.serializer.to_document(
                self._host.model.project
            )
            self._session.persist_session(runtime_document)
        else:
            self._session._persist_recent_session_payload(
                autosave_resume_fingerprint=""
            )
        self._host.project_meta_changed.emit()

    def _default_save_as_path(self) -> str:
        current_project_path = normalize_project_path_value(self._host.project_path)
        if current_project_path:
            return current_project_path
        project_name = (
            str(getattr(self._host.model.project, "name", "")).strip() or "untitled"
        )
        return str(Path(project_name).with_suffix(".cxproj"))

    def _rewrite_live_project_artifact_refs(self, replacements: dict[str, str]) -> None:
        if not replacements:
            return
        project = self._host.model.project
        project.replace_metadata(
            rewrite_project_artifact_refs(project.metadata, replacements)
        )
        for workspace in project.workspaces.values():
            for node in workspace.nodes.values():
                node.properties = rewrite_project_artifact_refs(
                    node.properties, replacements
                )

    @staticmethod
    def _normalized_absolute_path(path: str | Path | object) -> str:
        text = normalize_project_path_value(path)
        if not text:
            return ""
        return os.path.normcase(os.path.abspath(text))

    def _project_save_token_is_current(self, token: ProjectSaveToken) -> bool:
        project = self._host.model.project
        if (
            id(project) != token.project_object_identity
            or project.project_id != token.project_id
            or self._normalized_absolute_path(self._host.project_path)
            != token.normalized_source_path
            or project.document_epoch() != token.project_document_epoch
        ):
            return False
        try:
            current_document = self._host.serializer.to_persistent_document(project)
            current_fingerprint = ProjectDocumentSnapshot.from_mapping(
                current_document
            ).fingerprint
        except Exception:  # noqa: BLE001 - source drift fails closed.
            return False
        token_check = getattr(
            self._host.execution_client,
            "project_solution_save_snapshot_is_current",
            None,
        )
        return bool(
            current_fingerprint == token.persistent_document_fingerprint
            and callable(token_check)
            and token_check(token.solution_snapshot_token)
        )

    def _validate_save_destination(
        self,
        target: Path,
        *,
        commit_mode: str,
        source_store: ProjectArtifactStore,
        required_bytes: int,
        staged_sidecar_allowed: bool = False,
    ) -> None:
        target = Path(os.path.abspath(target))
        parent = target.parent
        validate_owned_artifact_path(
            parent.parent,
            parent.name,
            leaf_kind="directory",
        )
        layout = ProjectArtifactLayout.from_project_path(target)
        source_path = self._normalized_absolute_path(self._host.project_path)
        target_path = self._normalized_absolute_path(target)
        if commit_mode == "replace_current":
            if not source_path or target_path != source_path:
                raise ValueError("save_destination_invalid")
            validate_owned_artifact_path(parent, target.name)
            if layout.sidecar_root.exists():
                validate_owned_artifact_path(
                    layout.sidecar_root.parent,
                    layout.sidecar_root.name,
                    leaf_kind="directory",
                )
        else:
            if target.exists():
                raise FileExistsError("save_destination_exists")
            if layout.sidecar_root.exists():
                if not staged_sidecar_allowed:
                    raise FileExistsError("save_destination_sidecar_exists")
                validate_owned_artifact_path(
                    layout.sidecar_root.parent,
                    layout.sidecar_root.name,
                    leaf_kind="directory",
                )
            validate_owned_artifact_path(parent, target.name, allow_missing=True)
            validate_owned_artifact_path(
                layout.sidecar_root.parent,
                layout.sidecar_root.name,
                allow_missing=True,
                leaf_kind="directory",
            )
        source_layout = (
            ProjectArtifactLayout.from_project_path(self._host.project_path)
            if source_path
            else None
        )
        destination_root = os.path.normcase(os.path.abspath(layout.sidecar_root))
        forbidden_roots: list[str] = []
        if source_layout is not None and commit_mode == "create_new":
            forbidden_roots.append(
                os.path.normcase(os.path.abspath(source_layout.sidecar_root))
            )
        staging_root = source_store.active_staging_root()
        if staging_root is not None and commit_mode == "create_new":
            forbidden_roots.append(os.path.normcase(os.path.abspath(staging_root)))
        for root in forbidden_roots:
            try:
                overlaps = os.path.commonpath((destination_root, root)) in {
                    destination_root,
                    root,
                }
            except ValueError:
                overlaps = False
            if overlaps:
                raise ValueError("save_destination_overlaps_source")
        if shutil.disk_usage(parent).free < required_bytes + SAVE_FREE_SPACE_RESERVE_BYTES:
            raise OSError("save_destination_space_insufficient")

    @staticmethod
    def _artifact_copy_estimate(
        store: ProjectArtifactStore,
        artifact_ids: Iterable[str],
    ) -> int:
        total = 0
        for artifact_id in sorted(set(artifact_ids)):
            path = store.resolve_managed_path(artifact_id) or store.resolve_staged_path(
                artifact_id
            )
            if path is None or not path.exists():
                continue
            total += artifact_content_integrity(path.parent, path.name)[0]
        return total

    def _apply_save_adoption(
        self,
        *,
        adopted_metadata: dict[str, Any],
        adopted_properties: dict[tuple[str, str], dict[str, Any]],
        adopted_artifact_store: ProjectArtifactStore,
        target: Path,
        last_manual_save_ts: float,
        runtime_document: dict[str, Any],
    ) -> None:
        live_project = self._host.model.project
        live_project.replace_metadata(adopted_metadata)
        for workspace_id, live_workspace in live_project.workspaces.items():
            for node_id, live_node in live_workspace.nodes.items():
                live_node.properties = adopted_properties[(workspace_id, node_id)]
            live_workspace.dirty = False
        self._project_files.replace_project_artifact_store(
            adopted_artifact_store
        )
        self._host.project_path = str(target)
        self._session._session_state.last_manual_save_ts = last_manual_save_ts
        self._session._session_state.last_autosave_fingerprint = (
            SessionAutosaveStore.document_fingerprint(runtime_document)
        )
        remember_epoch = getattr(self._session, "_remember_current_document_epoch", None)
        if callable(remember_epoch):
            remember_epoch()

    def _cleanup_after_success(
        self,
        *,
        target: Path,
        artifact_stage: ProjectArtifactSaveStage,
        document_stage: StagedProjectDocument,
        solution_result: Any,
    ) -> None:
        target_key = self._normalized_absolute_path(target)
        artifact_candidates = tuple(
            sorted(
                {
                    *self._deferred_artifact_cleanup.get(target_key, ()),
                    *artifact_stage.cleanup_candidates,
                }
            )
        )
        try:
            artifact_gc = ProjectArtifactStore.collect_project_save_garbage(
                project_path=target,
                candidate_relative_paths=artifact_candidates,
                protected_relative_paths=(
                    *artifact_stage.previous_relative_paths,
                    *artifact_stage.retained_relative_paths,
                ),
            )
            remaining = tuple(
                sorted(
                    set(artifact_gc.remaining_relative_paths).difference(
                        artifact_stage.retained_relative_paths
                    )
                )
            )
            if remaining:
                self._deferred_artifact_cleanup[target_key] = remaining
            else:
                self._deferred_artifact_cleanup.pop(target_key, None)
        except Exception:  # noqa: BLE001 - GC never changes save success.
            if artifact_candidates:
                self._deferred_artifact_cleanup[target_key] = artifact_candidates
        image_candidates = tuple(
            sorted(
                {
                    *self._deferred_image_cleanup.get(target_key, ()),
                    *document_stage.image_stage.cleanup_candidates,
                }
            )
        )
        try:
            image_gc = collect_project_image_garbage(
                project_path=target,
                candidate_digests=image_candidates,
                protected_digests=(
                    document_stage.image_stage.previous_digests
                    | document_stage.image_stage.retained_digests
                ),
            )
            remaining_digests = tuple(
                sorted(
                    set(image_gc.remaining_digests).difference(
                        document_stage.image_stage.retained_digests
                    )
                )
            )
            if remaining_digests:
                self._deferred_image_cleanup[target_key] = remaining_digests
            else:
                self._deferred_image_cleanup.pop(target_key, None)
        except Exception:  # noqa: BLE001 - GC never changes save success.
            if image_candidates:
                self._deferred_image_cleanup[target_key] = image_candidates
        collect_solution_gc = getattr(
            self._host.execution_client,
            "collect_project_solution_garbage",
            None,
        )
        if callable(collect_solution_gc):
            self._deferred_solution_cleanup[
                solution_result.snapshot_token
            ] = solution_result
            for snapshot_token, pending_result in tuple(
                self._deferred_solution_cleanup.items()
            ):
                protect_previous = snapshot_token == solution_result.snapshot_token
                try:
                    gc_result = collect_solution_gc(
                        pending_result,
                        protect_previous_generation=protect_previous,
                    )
                except Exception:  # noqa: BLE001 - retry the original result later.
                    continue
                if not protect_previous and not gc_result.has_more:
                    self._deferred_solution_cleanup.pop(snapshot_token, None)

    def _run_project_save(
        self,
        target: Path,
        *,
        commit_mode: str,
    ) -> _SaveCoreOutcome:
        project = self._host.model.project
        target = Path(os.path.abspath(target.with_suffix(".cxproj")))
        source_path = self._normalized_absolute_path(self._host.project_path)
        source_store = ProjectArtifactStore.from_project_metadata(
            project_path=self._host.project_path or None,
            project_metadata=project.metadata,
        )
        solution_snapshot: Any | None = None
        document_stage: StagedProjectDocument | None = None
        committed = False
        try:
            self._workspace_session.save_active_view_state()
            self.persist_script_editor_state()
            try:
                persistent_document = self._host.serializer.to_persistent_document(project)
            except Exception:
                raise RuntimeError("save_document_invalid") from None
            persistent_snapshot = ProjectDocumentSnapshot.from_mapping(
                persistent_document
            )
            retained_owner_ids = tuple(
                sorted(
                    (workspace_id, node_id)
                    for workspace_id, workspace in project.workspaces.items()
                    for node_id in workspace.nodes
                )
            )
            capture_solution = getattr(
                self._host.execution_client,
                "capture_project_solution_save",
                None,
            )
            if not callable(capture_solution):
                raise ValueError("save_solution_stage_failed")
            try:
                solution_snapshot = capture_solution(
                    project.project_id,
                    str(self._host.project_path or ""),
                    retained_owner_ids,
                    source_store,
                )
            except Exception:
                raise RuntimeError("save_solution_stage_failed") from None
            save_token = ProjectSaveToken(
                save_id=uuid4().hex,
                project_object_identity=id(project),
                project_id=project.project_id,
                normalized_source_path=source_path,
                project_document_epoch=project.document_epoch(),
                persistent_document_fingerprint=persistent_snapshot.fingerprint,
                solution_snapshot_token=solution_snapshot.snapshot_token,
            )
            refs = collect_project_artifact_references(persistent_document)
            required_ids = set(refs.managed_ids) | set(
                solution_snapshot.required_managed_artifact_ids
            )
            try:
                artifact_copy_bytes = self._artifact_copy_estimate(
                    source_store,
                    (*required_ids, *refs.staged_ids),
                )
            except Exception:
                raise RuntimeError("save_artifact_stage_failed") from None
            required_bytes = (
                len(persistent_snapshot.encoded_payload.encode("utf-8"))
                + solution_snapshot.estimated_copy_bytes
                + artifact_copy_bytes
            )
            self._validate_save_destination(
                target,
                commit_mode=commit_mode,
                source_store=source_store,
                required_bytes=required_bytes,
            )
            target_layout = ProjectArtifactLayout.from_project_path(target)
            initial_parent_identity = _save_path_identity(
                target.parent,
                content_sensitive=False,
            )
            initial_target_identity = _save_path_identity(
                target,
                content_sensitive=True,
            )
            initial_sidecar_identity = _save_path_identity(
                target_layout.sidecar_root,
                content_sensitive=False,
            )
            if initial_sidecar_identity is None:
                try:
                    os.mkdir(target_layout.sidecar_root)
                except FileExistsError:
                    raise RuntimeError("save_destination_sidecar_exists") from None
                validate_owned_artifact_path(
                    target_layout.sidecar_root.parent,
                    target_layout.sidecar_root.name,
                    leaf_kind="directory",
                )
            try:
                artifact_stage = source_store.stage_project_save(
                    destination_project_path=target,
                    workspaces=project.workspaces,
                    referenced_managed_ids=refs.managed_ids,
                    referenced_staged_ids=refs.staged_ids,
                    required_managed_artifact_ids=(
                        solution_snapshot.required_managed_artifact_ids
                    ),
                )
            except Exception:
                raise RuntimeError("save_artifact_stage_failed") from None
            candidate_document = rewrite_project_artifact_refs(
                copy.deepcopy(persistent_document),
                artifact_stage.ref_replacements,
            )
            metadata = (
                dict(candidate_document.get("metadata", {}))
                if isinstance(candidate_document.get("metadata"), Mapping)
                else {}
            )
            metadata[PROJECT_ARTIFACT_STORE_METADATA_KEY] = (
                artifact_stage.destination_store.metadata
            )
            candidate_document["metadata"] = metadata
            stage_solution = getattr(
                self._host.execution_client,
                "stage_project_solution_save",
                None,
            )
            if not callable(stage_solution):
                raise ValueError("save_solution_stage_failed")
            try:
                solution_result = stage_solution(
                    solution_snapshot,
                    str(target),
                    artifact_stage.destination_store,
                )
            except Exception:
                raise RuntimeError("save_solution_stage_failed") from None
            if solution_result.reason_code != "project_solution_save_staged":
                raise ValueError("save_solution_stage_failed")
            metadata["solution_store"] = solution_result.metadata_solution_store
            candidate_document["metadata"] = metadata
            for workspace_document in candidate_document.get("workspaces", ()):
                if isinstance(workspace_document, dict):
                    workspace_document["dirty"] = False
            try:
                document_stage = self._host.serializer.stage_document(
                    target,
                    candidate_document,
                    commit_mode,
                )
            except Exception as exc:
                raise RuntimeError(
                    "save_image_digest_conflict"
                    if "image digest conflict" in str(exc)
                    else "save_project_stage_failed"
                ) from None
            staged_sidecar_identity = _save_path_identity(
                target_layout.sidecar_root,
                content_sensitive=False,
            )
            if not self._project_save_token_is_current(save_token):
                raise RuntimeError("save_source_changed")
            self._validate_save_destination(
                target,
                commit_mode=commit_mode,
                source_store=source_store,
                required_bytes=len(document_stage.canonical_bytes),
                staged_sidecar_allowed=True,
            )
            if (
                _save_path_identity(target.parent, content_sensitive=False)
                != initial_parent_identity
                or _save_path_identity(target, content_sensitive=True)
                != initial_target_identity
                or _save_path_identity(
                    target_layout.sidecar_root,
                    content_sensitive=False,
                )
                != staged_sidecar_identity
            ):
                raise RuntimeError("save_destination_unsafe")
            try:
                publication = self._host.serializer.commit_staged_document(
                    document_stage
                )
            except Exception:
                raise RuntimeError("save_project_commit_failed") from None
            committed = bool(publication.committed)
            if not committed:
                if commit_mode == "create_new" and target.exists():
                    raise RuntimeError("save_destination_exists")
                raise RuntimeError("save_project_commit_failed")
            try:
                self._host.serializer.verify_committed_document(document_stage)
            except Exception:
                raise RuntimeError("save_committed_not_adopted_verification_failed")
            candidate_project = self._host.serializer.load(str(target))
            if (
                candidate_project.project_id != project.project_id
                or candidate_project.schema_version
                != document_stage.prepared_document.get("schema_version")
            ):
                raise RuntimeError("save_committed_not_adopted_verification_failed")
            candidate_metadata = (
                candidate_project.metadata
                if isinstance(candidate_project.metadata, Mapping)
                else {}
            )
            if candidate_metadata.get("solution_store") != solution_result.metadata_solution_store:
                raise RuntimeError("save_committed_not_adopted_verification_failed")
            reopened_document = json.loads(
                document_stage.canonical_bytes.decode("utf-8")
            )
            reopened_refs = collect_project_artifact_references(reopened_document)
            if reopened_refs.staged_ids:
                raise RuntimeError("save_committed_not_adopted_verification_failed")
            reopened_store = ProjectArtifactStore.from_project_metadata(
                project_path=target,
                project_metadata=candidate_metadata,
            )
            expected_artifact_ids = tuple(
                sorted(
                    set(reopened_refs.managed_ids).union(
                        solution_snapshot.required_managed_artifact_ids
                    )
                )
            )
            expected_fact_ids = tuple(
                fact.artifact_id
                for fact in artifact_stage.expected_integrity_facts
            )
            if expected_artifact_ids != expected_fact_ids:
                raise RuntimeError("save_committed_not_adopted_verification_failed")
            try:
                reopened_facts = reopened_store.expected_integrity_facts(
                    expected_artifact_ids
                )
            except Exception:
                raise RuntimeError(
                    "save_committed_not_adopted_verification_failed"
                ) from None
            if reopened_facts != artifact_stage.expected_integrity_facts:
                raise RuntimeError("save_committed_not_adopted_verification_failed")
            prepare_adoption = getattr(
                self._host.execution_client,
                "prepare_project_solution_adoption",
                None,
            )
            if not callable(prepare_adoption):
                raise RuntimeError("save_committed_not_adopted_binding_failed")
            candidate_preparation = prepare_adoption(
                solution_result,
                project.project_id,
                str(target),
                solution_result.metadata_solution_store,
                reopened_store,
            )
            if not candidate_preparation.prepared:
                raise RuntimeError(
                    "save_committed_not_adopted_verification_failed"
                )
            runtime_document = self._host.serializer.to_document(candidate_project)
            if set(candidate_project.workspaces) != set(project.workspaces) or any(
                set(candidate_project.workspaces[workspace_id].nodes)
                != set(project.workspaces[workspace_id].nodes)
                for workspace_id in project.workspaces
            ):
                raise RuntimeError("save_committed_not_adopted_verification_failed")
            adopted_metadata = copy.deepcopy(candidate_project.metadata)
            adopted_properties = {
                (workspace_id, node_id): copy.deepcopy(candidate_node.properties)
                for workspace_id, candidate_workspace in candidate_project.workspaces.items()
                for node_id, candidate_node in candidate_workspace.nodes.items()
            }
            try:
                last_manual_save_ts = target.stat().st_mtime
            except OSError:
                last_manual_save_ts = time.time()
            if not self._project_save_token_is_current(save_token):
                raise RuntimeError("save_committed_not_adopted_source_changed")
            adopt_solution = getattr(
                self._host.execution_client,
                "adopt_project_solution_save",
                None,
            )
            if not callable(adopt_solution):
                raise RuntimeError("save_committed_not_adopted_binding_failed")
            adoption = adopt_solution(
                solution_result,
                project.project_id,
                str(target),
                solution_result.metadata_solution_store,
                reopened_store,
            )
            if not adoption.adopted:
                raise RuntimeError("save_committed_not_adopted_binding_failed")
            self._apply_save_adoption(
                adopted_metadata=adopted_metadata,
                adopted_properties=adopted_properties,
                adopted_artifact_store=reopened_store,
                target=target,
                last_manual_save_ts=last_manual_save_ts,
                runtime_document=runtime_document,
            )
            self._cleanup_after_success(
                target=target,
                artifact_stage=artifact_stage,
                document_stage=document_stage,
                solution_result=solution_result,
            )
            return _SaveCoreOutcome(
                ProjectSaveResult("saved", "save_succeeded", str(target)),
                runtime_document,
            )
        except Exception as exc:  # noqa: BLE001 - map the transaction boundary once.
            reason = str(exc)
            if committed:
                reason_code = (
                    reason
                    if reason.startswith("save_committed_not_adopted_")
                    else "save_committed_not_adopted_reopen_failed"
                )
                status = "committed_not_adopted"
            else:
                known = {
                    "save_destination_invalid",
                    "save_destination_exists",
                    "save_destination_sidecar_exists",
                    "save_destination_unsafe",
                    "save_destination_overlaps_source",
                    "save_destination_space_insufficient",
                    "save_source_changed",
                    "save_document_invalid",
                    "save_artifact_stage_failed",
                    "save_solution_stage_failed",
                    "save_image_digest_conflict",
                    "save_project_stage_failed",
                    "save_project_commit_failed",
                }
                reason_code = reason if reason in known else (
                    "save_image_digest_conflict"
                    if "image digest conflict" in reason
                    else "save_artifact_stage_failed"
                    if "artifact" in reason
                    else "save_project_stage_failed"
                )
                status = "failed"
            cancel_solution = getattr(
                self._host.execution_client,
                "cancel_project_solution_save",
                None,
            )
            if solution_snapshot is not None and callable(cancel_solution):
                cancel_solution(solution_snapshot.snapshot_token)
            return _SaveCoreOutcome(
                ProjectSaveResult(status, reason_code, str(target))
            )
        finally:
            if document_stage is not None:
                self._host.serializer.discard_staged_document(document_stage)

    def _finish_save_outcome(self, outcome: _SaveCoreOutcome) -> None:
        if outcome.result.status == "saved" and outcome.runtime_document is not None:
            for callback in (
                self._workspace_session.refresh_workspace_tabs,
                self._session.discard_autosave_snapshot,
            ):
                try:
                    callback()
                except Exception:  # noqa: BLE001 - notification failures do not undo save.
                    pass
            try:
                self._session.add_recent_project_path(
                    outcome.result.target_path,
                    persist=False,
                )
                self._session.persist_session(outcome.runtime_document)
                self._host.project_meta_changed.emit()
            except Exception:  # noqa: BLE001 - core save already succeeded.
                pass
            return
        if outcome.result.status in {"failed", "committed_not_adopted"}:
            from PyQt6.QtWidgets import QMessageBox

            text = (
                "The project was committed to disk, but this window kept its previous live state."
                if outcome.result.status == "committed_not_adopted"
                else "The project could not be saved."
            )
            QMessageBox.warning(
                self._dialog_parent(),
                "Save Project",
                f"{text}\n{outcome.result.reason_code}",
            )

    def save_project(self) -> ProjectSaveResult:
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        if not self._save_guard.acquire(blocking=False):
            return ProjectSaveResult(
                "failed",
                "save_in_progress",
                "",
            )
        try:
            snapshot = self._project_files.build_project_files_snapshot()
            if not self._project_files.prompt_project_files_action(
                title="Save Project",
                text=self._project_files._project_files_prompt_headline(snapshot),
                continue_label="Save Project",
                cancel_standard_button=QMessageBox.StandardButton.Cancel,
                snapshot=snapshot,
                context_key="save",
                allow_repair=True,
            ):
                outcome = _SaveCoreOutcome(
                    ProjectSaveResult("cancelled", "save_cancelled", "")
                )
            else:
                path = self._host.project_path
                if not path:
                    path, _ = QFileDialog.getSaveFileName(
                        self._dialog_parent(),
                        "Save Project",
                        "",
                        "COREX Project (*.cxproj)",
                    )
                if not path:
                    outcome = _SaveCoreOutcome(
                        ProjectSaveResult("cancelled", "save_cancelled", "")
                    )
                else:
                    outcome = self._run_project_save(
                        Path(path),
                        commit_mode=(
                            "replace_current" if self._host.project_path else "create_new"
                        ),
                    )
        finally:
            self._save_guard.release()
        self._finish_save_outcome(outcome)
        return outcome.result

    def save_project_as(self) -> ProjectSaveResult:
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        if not self._save_guard.acquire(blocking=False):
            return ProjectSaveResult(
                "failed",
                "save_in_progress",
                "",
            )
        try:
            snapshot = self._project_files.build_project_files_snapshot()
            if not self._project_files.prompt_project_files_action(
                title="Save Project As",
                text=self._project_files._project_files_prompt_headline(snapshot),
                continue_label="Save Project As",
                cancel_standard_button=QMessageBox.StandardButton.Cancel,
                snapshot=snapshot,
                context_key="save_as",
                allow_repair=True,
            ):
                outcome = _SaveCoreOutcome(
                    ProjectSaveResult("cancelled", "save_cancelled", "")
                )
            else:
                path, _ = QFileDialog.getSaveFileName(
                    self._dialog_parent(),
                    "Save Project As",
                    self._default_save_as_path(),
                    "COREX Project (*.cxproj)",
                )
                normalized_path = normalize_project_path_value(path)
                if not normalized_path:
                    outcome = _SaveCoreOutcome(
                        ProjectSaveResult("cancelled", "save_cancelled", "")
                    )
                else:
                    target = Path(normalized_path)
                    same_path = bool(
                        self._host.project_path
                        and self._normalized_absolute_path(target)
                        == self._normalized_absolute_path(self._host.project_path)
                    )
                    outcome = self._run_project_save(
                        target,
                        commit_mode=("replace_current" if same_path else "create_new"),
                    )
        finally:
            self._save_guard.release()
        self._finish_save_outcome(outcome)
        return outcome.result

    def new_project(self) -> bool:
        if not self._save_guard.acquire(blocking=False):
            return False
        try:
            if not self._confirm_project_replacement(
                title="New Project",
                action_text="create a new project",
            ):
                return False
            project = ProjectData(project_id="proj_local", name="untitled")
            self._finalize_unsaved_project(
                project,
                create_resume_snapshot=False,
                _save_guard_held=True,
            )
            return True
        finally:
            self._save_guard.release()

    def open_project(self) -> bool:
        from PyQt6.QtWidgets import QFileDialog

        if not self._save_guard.acquire(blocking=False):
            return False
        try:
            path, _ = QFileDialog.getOpenFileName(
                self._dialog_parent(), "Open Project", "", "COREX Project (*.cxproj)"
            )
            if not path:
                return False
            return self._open_project_path_unlocked(path, show_errors=True)
        finally:
            self._save_guard.release()

    def open_project_path(self, path: str | Path, *, show_errors: bool = True) -> bool:
        if not self._save_guard.acquire(blocking=False):
            return False
        try:
            return self._open_project_path_unlocked(path, show_errors=show_errors)
        finally:
            self._save_guard.release()

    def _open_project_path_unlocked(
        self,
        path: str | Path,
        *,
        show_errors: bool,
    ) -> bool:
        from PyQt6.QtWidgets import QMessageBox

        normalized_path = normalize_project_path_value(path)
        if not normalized_path:
            return False
        resolved_path = Path(normalized_path)
        if not resolved_path.is_file():
            if show_errors:
                QMessageBox.warning(
                    self._dialog_parent(),
                    "Open Project",
                    f"Project file not found.\n{resolved_path}",
                )
            return False
        if not self._confirm_project_replacement(
            title="Open Project",
            action_text="open the selected project",
        ):
            return False
        try:
            project = self._host.serializer.load(str(resolved_path))
        except Exception as exc:  # noqa: BLE001
            if show_errors:
                QMessageBox.warning(
                    self._dialog_parent(),
                    "Open Project",
                    f"Could not open project file.\n{exc}",
                )
            return False
        snapshot = self._project_files.build_project_files_snapshot(
            project=project, project_path=resolved_path
        )
        if not self._project_files.prompt_project_files_action(
            title="Open Project",
            text=self._project_files._project_files_prompt_headline(snapshot),
            continue_label="Open Project",
            cancel_standard_button=QMessageBox.StandardButton.Cancel,
            snapshot=snapshot,
            context_key="open",
            allow_repair=False,
        ):
            return False
        self._finalize_loaded_project(
            project,
            project_path=str(resolved_path),
            _save_guard_held=True,
        )
        self._show_migration_report(project)
        return True
    def _show_migration_report(self, project: ProjectData) -> None:
        report = sorted(
            {
                str(entry or "").strip()
                for entry in getattr(project, "migration_report", ())
                if str(entry or "").strip()
            }
        )
        if not report:
            return
        from PyQt6.QtWidgets import QMessageBox

        source_version = int(
            getattr(project, "migration_source_schema_version", 0) or 0
        )
        heading = (
            f"This project was opened from schema v{source_version} and updated in memory."
            if source_version > 0
            else "This project was updated in memory."
        )
        QMessageBox.information(
            self._dialog_parent(),
            "Project Migration Report",
            "\n".join(
                [
                    heading,
                    "The source file has not been overwritten. Review the changes, then Save when ready.",
                    "",
                    *(f"- {entry}" for entry in report),
                ]
            ),
        )


__all__ = ["ProjectDocumentIOService"]
