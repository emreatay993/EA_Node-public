# Purpose: Own project-file inspection, synchronous staged payload writes, and metadata publication.
# Map: feature_routes/project_session_files_managed_artifacts.md
# Tests: tests/test_project_file_staging.py, tests/test_project_session_controller_unit.py, tests/test_canvas_import_runtime.py

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from ea_node_editor.graph.file_issue_state import collect_workspace_file_issue_map
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.nodes.output_artifacts import register_staged_artifact
from ea_node_editor.runtime_contracts import PATH_DATA_TYPE_ID
from ea_node_editor.settings import (
    PROJECT_ARTIFACT_STORE_METADATA_KEY,
    PROJECT_MANAGED_WORKSPACES_DIRNAME,
    PROJECT_NODE_INPUTS_DIRNAME,
)
from ea_node_editor.ui.dialogs.project_files_dialog import (
    ProjectFilesBrokenEntry,
    ProjectFilesDialog,
    ProjectFilesManagedEntry,
    ProjectFilesSnapshot,
    ProjectFilesStagedEntry,
)
from ea_node_editor.ui.shell.controllers.project_session_services_support.shared import (
    _NodePropertyPathBrowserProtocol,
    _ProjectFilesHostProtocol,
    _ProjectSessionHostProtocol,
    _WorkspaceSessionProtocol,
    normalize_project_path_value,
)


class ProjectFilesService:
    def __init__(
        self,
        host: _ProjectFilesHostProtocol,
        *,
        dialog_parent_source: _ProjectSessionHostProtocol,
        path_browser: _NodePropertyPathBrowserProtocol,
        workspace_session: _WorkspaceSessionProtocol,
    ) -> None:
        self._host = host
        self._dialog_parent_source = dialog_parent_source
        self._path_browser = path_browser
        self._workspace_session = workspace_session

    @staticmethod
    def _count_text(count: int, noun: str) -> str:
        suffix = "" if count == 1 else "s"
        return f"{count} {noun}{suffix}"

    def project_artifact_store(self) -> ProjectArtifactStore:
        metadata = self._host.model.project.metadata if isinstance(self._host.model.project.metadata, dict) else {}
        return ProjectArtifactStore.from_project_metadata(
            project_path=self._host.project_path,
            project_metadata=metadata,
        )

    def replace_project_artifact_store(self, store: ProjectArtifactStore) -> bool:
        metadata = self._host.model.project.metadata if isinstance(self._host.model.project.metadata, dict) else {}
        updated_metadata = dict(metadata)
        updated_metadata[PROJECT_ARTIFACT_STORE_METADATA_KEY] = store.metadata
        return self._host.model.project.replace_metadata(updated_metadata)

    def ensure_project_staging_root(self) -> Path:
        store = self.project_artifact_store()
        staging_root = store.ensure_staging_root(
            temporary_root_parent=self._host.session_store.staging_workspace_root(),
        )
        self.replace_project_artifact_store(store)
        return staging_root

    def discard_staged_scratch_data(self) -> None:
        store = self.project_artifact_store()
        store.discard_staged_payloads()
        self.replace_project_artifact_store(store)

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
        source = Path(source_path).expanduser()
        if not source.is_file():
            return ""
        normalized_id = str(artifact_id or "").strip() or (
            f"{str(artifact_prefix or 'artifact').strip() or 'artifact'}_{uuid4().hex}"
        )

        def copy_source(destination: Path) -> None:
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)

        return self._stage_node_artifact(
            artifact_id=normalized_id,
            io_dir=io_dir,
            subdirectory=subdirectory,
            filename=filename or source.name,
            entry_metadata=entry_metadata,
            node_id=node_id,
            node_title=node_title,
            node_type=node_type,
            writer=copy_source,
        )

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
        raw_data = bytes(data or b"")
        if not raw_data:
            return ""
        normalized_prefix = str(artifact_prefix or "clipboard").strip() or "clipboard"
        artifact_id = f"{normalized_prefix}_{uuid4().hex}"
        return self._stage_node_artifact(
            artifact_id=artifact_id,
            io_dir=PROJECT_NODE_INPUTS_DIRNAME,
            subdirectory=subdirectory or "clipboard",
            filename=filename or artifact_id,
            entry_metadata={
                "artifact_kind": str(artifact_kind or "clipboard_source"),
                "mime_type": str(mime_type or "").strip(),
                "size": len(raw_data),
                "sha256": hashlib.sha256(raw_data).hexdigest(),
            },
            node_id=node_id,
            node_title=node_title,
            node_type=node_type,
            writer=lambda destination: destination.write_bytes(raw_data),
        )

    def create_blank_notebook_artifact(
        self,
        node_id: str = "",
        *,
        kernel_name: str = "",
    ) -> str:
        artifact_id = f"jupyter_notebook_{uuid4().hex}"

        def write_notebook(destination: Path) -> None:
            from ea_node_editor.jupyter_host.notebook_files import create_blank_notebook

            create_blank_notebook(destination, kernel_name=kernel_name)

        return self._stage_node_artifact(
            artifact_id=artifact_id,
            io_dir=PROJECT_NODE_INPUTS_DIRNAME,
            subdirectory="jupyter/notebooks",
            filename="notebook.ipynb",
            entry_metadata={"artifact_kind": "jupyter_notebook"},
            node_id=node_id,
            node_title="",
            node_type="code.jupyter_notebook",
            writer=write_notebook,
        )

    def _stage_node_artifact(
        self,
        *,
        artifact_id: str,
        io_dir: str,
        subdirectory: str,
        filename: str,
        entry_metadata: Mapping[str, Any] | None,
        node_id: str,
        node_title: str,
        node_type: str,
        writer: Callable[[Path], None],
    ) -> str:
        store = self.project_artifact_store()
        staging_root = store.ensure_staging_root(
            temporary_root_parent=self._host.session_store.staging_workspace_root(),
        )
        workspace_id, workspace_name, resolved_node_id, resolved_title, resolved_type = (
            self._node_artifact_context(
                node_id=node_id,
                node_title=node_title,
                node_type=node_type,
            )
        )
        paths = store.node_artifact_paths(
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            node_id=resolved_node_id,
            node_title=resolved_title,
            node_type=resolved_type,
            io_dir=io_dir,
            subdirectory=subdirectory,
            filename=filename,
        )
        destination = store.staged_target_path(paths.staged_relative_path)
        destination_existed = destination.exists()
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            writer(destination)
            path_type = self._host.registry.data_types.require(PATH_DATA_TYPE_ID)
            register_staged_artifact(
                store=store,
                artifact_id=artifact_id,
                payload_path=destination,
                relative_path=paths.staged_relative_path,
                slot=None,
                data_type_id=PATH_DATA_TYPE_ID,
                schema_version=path_type.payload_schema_version,
                format=destination.suffix.lstrip(".") or "bin",
                provenance="corex.project.import",
                entry_metadata={**dict(entry_metadata or {}), **paths.metadata},
            )
            if not self.replace_project_artifact_store(store):
                self._host.model.project.touch_metadata()
        except Exception:
            if not destination_existed:
                self._discard_new_staged_candidate(destination, staging_root)
            raise
        return store.staged_ref(artifact_id)

    def _node_artifact_context(
        self,
        *,
        node_id: str = "",
        node_title: str = "",
        node_type: str = "",
    ) -> tuple[str, str, str, str, str]:
        workspace_id = str(self._host.workspace_manager.active_workspace_id() or "").strip()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        workspace_name = str(getattr(workspace, "name", "") or "").strip()
        resolved_node_id = str(node_id or "").strip()
        if not resolved_node_id:
            selected_node_id = getattr(self._host.scene, "selected_node_id", lambda: "")()
            resolved_node_id = str(selected_node_id or "").strip()
        node = workspace.nodes.get(resolved_node_id) if workspace is not None and resolved_node_id else None
        resolved_title = str(node_title or "").strip() or str(getattr(node, "title", "") or "").strip()
        resolved_type = str(node_type or "").strip()
        if node is not None and not resolved_type:
            try:
                spec = self._host.registry.get_spec(node.type_id)
                resolved_type = str(getattr(spec, "display_name", "") or node.type_id)
            except Exception:  # noqa: BLE001 - use the stored node type as the stable fallback
                resolved_type = str(node.type_id)
        return (
            workspace_id,
            workspace_name,
            resolved_node_id or "project",
            resolved_title or "Project",
            resolved_type or "Project",
        )

    @staticmethod
    def _discard_new_staged_candidate(destination: Path, staging_root: Path) -> None:
        try:
            if destination.is_file():
                destination.unlink()
        except OSError:
            return
        parent = destination.parent
        while parent != staging_root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def build_project_files_snapshot(
        self,
        *,
        project: ProjectData | None = None,
        project_path: str | Path | None = None,
    ) -> ProjectFilesSnapshot:
        current_project = project if project is not None else self._host.model.project
        resolved_project_path = normalize_project_path_value(
            project_path if project_path is not None else self._host.project_path
        )
        metadata = current_project.metadata if isinstance(current_project.metadata, dict) else {}
        store = ProjectArtifactStore.from_project_metadata(
            project_path=resolved_project_path,
            project_metadata=metadata,
        )
        layout = store.layout

        managed_entries = tuple(
            ProjectFilesManagedEntry(
                artifact_id=entry.artifact_id,
                relative_path=entry.relative_path,
                absolute_path=str(resolved_path) if resolved_path is not None else "",
                exists=bool(resolved_path is not None and resolved_path.exists() and resolved_path.is_file()),
            )
            for entry in store.state.artifacts.values()
            for resolved_path in (store.resolve_managed_path(entry.artifact_id),)
        )
        staged_entries = tuple(
            ProjectFilesStagedEntry(
                artifact_id=entry.artifact_id,
                relative_path=entry.relative_path or "",
                absolute_path=str(resolved_path) if resolved_path is not None else "",
                slot=entry.slot or "",
                exists=bool(resolved_path is not None and resolved_path.exists() and resolved_path.is_file()),
            )
            for entry in store.state.staged.values()
            for resolved_path in (store.resolve_staged_path(entry.artifact_id),)
        )

        broken_entries: list[ProjectFilesBrokenEntry] = []
        for workspace in current_project.workspaces.values():
            issue_map = collect_workspace_file_issue_map(
                workspace=workspace,
                registry=self._host.registry,
                project_path=resolved_project_path or None,
                project_metadata=metadata,
            )
            for (_node_id, _property_key), issue in sorted(
                issue_map.items(),
                key=lambda item: (
                    str(workspace.name or workspace.workspace_id),
                    str(item[1].node_id),
                    str(item[1].property_key),
                ),
            ):
                node = workspace.nodes.get(issue.node_id)
                broken_entries.append(
                    ProjectFilesBrokenEntry(
                        workspace_id=str(workspace.workspace_id),
                        workspace_name=str(workspace.name),
                        node_id=str(issue.node_id),
                        node_title=str(node.title) if node is not None else str(issue.node_id),
                        property_key=str(issue.property_key),
                        property_label=str(issue.property_label),
                        current_value=str(issue.property_value),
                        issue_kind=str(issue.issue_kind),
                        source_kind=str(issue.source_kind),
                        source_mode=str(issue.source_mode),
                        message=str(issue.message),
                    )
                )

        staging_root_path = ""
        if store.state.staged:
            if layout is not None:
                staging_root_path = str(layout.workspaces_root)
            elif store.staging_root_hint is not None:
                staging_root_path = str(store.staging_root_hint.as_path() / PROJECT_MANAGED_WORKSPACES_DIRNAME)

        return ProjectFilesSnapshot(
            project_path=resolved_project_path,
            data_root_path=str(layout.sidecar_root) if layout is not None else "",
            staging_root_path=staging_root_path,
            managed_entries=managed_entries,
            staged_entries=staged_entries,
            broken_entries=tuple(broken_entries),
        )

    @staticmethod
    def _project_files_prompt_headline(snapshot: ProjectFilesSnapshot) -> str:
        if snapshot.staged_count and snapshot.broken_count:
            return "This project contains temporary files and broken file entries."
        if snapshot.staged_count:
            return "This project contains temporary files."
        return "This project contains broken file entries."

    @classmethod
    def _project_files_prompt_details(cls, *, context_key: str, snapshot: ProjectFilesSnapshot) -> str:
        lines = [snapshot.summary_text]
        if snapshot.staged_count:
            staged_text = cls._count_text(snapshot.staged_count, "temporary file").capitalize()
            if context_key in {"save", "save_as"}:
                lines.append(
                    f"{staged_text} stays in node tmp folders until a project save moves the referenced items to in/out folders."
                )
            elif context_key == "open":
                lines.append(
                    f"{staged_text} is still in node tmp folders. Save the project after opening if you want it moved to in/out folders."
                )
            else:
                lines.append(
                    f"{staged_text} will be restored in node tmp folders if you recover this autosave."
                )
        if snapshot.broken_count:
            broken_text = cls._count_text(snapshot.broken_count, "broken file entry").capitalize()
            lines.append(f"{broken_text} will remain unresolved until repaired.")
        lines.append("Choose Project Files... to inspect the full list.")
        return "\n\n".join(lines)

    def _dialog_parent(self):
        return self._dialog_parent_source.dialog_parent()

    def prompt_project_files_action(
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
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QMessageBox

        while True:
            if not always_prompt and not snapshot.has_prompt_context:
                return True

            dialog = QMessageBox(self._dialog_parent())
            dialog.setWindowTitle(title)
            dialog.setIcon(QMessageBox.Icon.Warning if snapshot.broken_count else QMessageBox.Icon.Information)
            dialog.setText(text)
            if snapshot.has_prompt_context:
                dialog.setInformativeText(self._project_files_prompt_details(context_key=context_key, snapshot=snapshot))
            continue_button = dialog.addButton(continue_label, QMessageBox.ButtonRole.AcceptRole)
            details_button = None
            if snapshot.has_prompt_context:
                details_button = dialog.addButton("Project Files...", QMessageBox.ButtonRole.ActionRole)
            dialog.addButton(cancel_standard_button)
            dialog.setDefaultButton(continue_button)
            dialog.setWindowModality(Qt.WindowModality.WindowModal)
            dialog.exec()
            if details_button is not None and dialog.clickedButton() is details_button:
                self.show_project_files_dialog(snapshot=snapshot, allow_repair=allow_repair)
                if allow_repair:
                    snapshot = self.build_project_files_snapshot()
                continue
            return dialog.clickedButton() is continue_button

    def show_project_files_dialog(
        self,
        *,
        snapshot: ProjectFilesSnapshot | None = None,
        allow_repair: bool | None = None,
    ) -> None:
        current_snapshot = snapshot if snapshot is not None else self.build_project_files_snapshot()
        repair_enabled = bool(allow_repair) if allow_repair is not None else snapshot is None
        dialog = ProjectFilesDialog(
            snapshot=current_snapshot,
            repair_callback=self.repair_project_file_issue if repair_enabled else None,
            refresh_snapshot_callback=self.build_project_files_snapshot if repair_enabled else None,
            parent=self._dialog_parent(),
        )
        dialog.exec()

    def repair_project_file_issue(self, issue: ProjectFilesBrokenEntry) -> bool:
        workspace_id = str(issue.workspace_id or "").strip()
        current_workspace_id = str(self._host.workspace_manager.active_workspace_id() or "").strip()
        if not workspace_id or workspace_id not in self._host.model.project.workspaces:
            return False
        switched_workspace = workspace_id != current_workspace_id
        if switched_workspace:
            self._workspace_session.switch_workspace(workspace_id)
        try:
            repaired_value = self._path_browser.browse_node_property_path(
                issue.node_id,
                issue.property_key,
                issue.repair_request,
            )
            if not repaired_value:
                return False
            self._host.scene.set_node_property(issue.node_id, issue.property_key, repaired_value)
            return True
        finally:
            if switched_workspace and current_workspace_id:
                self._workspace_session.switch_workspace(current_workspace_id)


__all__ = ["ProjectFilesService"]
