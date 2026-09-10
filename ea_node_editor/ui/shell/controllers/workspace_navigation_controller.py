# Purpose: Own workspace/view navigation, framing, search, and failure focus.
# Map: feature_routes/workspace_tabs_library_context_menus
# Tests: tests/test_workspace_navigation_controller.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QRectF

from ea_node_editor.ui.shell.controllers.dialog_support import resolve_dialog_parent
from ea_node_editor.ui.shell.controllers.workspace_view_nav_ops import WorkspaceViewNavOps

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow

logger = logging.getLogger(__name__)


class WorkspaceNavigationController:
    def __init__(self, host: ShellWindow) -> None:
        self._host = host
        self._ops = WorkspaceViewNavOps(host, self)

    def switch_workspace_by_offset(self, offset: int) -> None:
        self._ops.switch_workspace_by_offset(offset)

    def refresh_workspace_tabs(self) -> None:
        self._ops.refresh_workspace_tabs()

    def switch_workspace(self, workspace_id: str) -> None:
        self._ops.switch_workspace(workspace_id)

    def move_workspace(self, from_index: int, to_index: int) -> bool:
        refs = self._host.workspace_manager.list_workspaces()
        if len(refs) < 2:
            return False
        if from_index < 0 or from_index >= len(refs):
            return False
        bounded_index = max(0, min(int(to_index), len(refs) - 1))
        if from_index == bounded_index:
            return False
        self._host.workspace_manager.move_workspace(from_index, bounded_index)
        self.refresh_workspace_tabs()
        return True

    def save_active_view_state(self) -> None:
        self._ops.save_active_view_state()

    def restore_active_view_state(self) -> None:
        self._ops.restore_active_view_state()

    def visible_scene_rect(self) -> QRectF:
        return self._ops.visible_scene_rect()

    def current_workspace_scene_bounds(self) -> QRectF | None:
        return self._ops.current_workspace_scene_bounds()

    def selection_bounds(self) -> QRectF | None:
        return self._ops.selection_bounds()

    def frame_all(self) -> bool:
        return self._ops.frame_all()

    def frame_selection(self) -> bool:
        return self._ops.frame_selection()

    def frame_node(self, node_id: str) -> bool:
        return self._ops.frame_node(node_id)

    def center_on_node(self, node_id: str) -> bool:
        return self._ops.center_on_node(node_id)

    def center_on_selection(self) -> bool:
        return self._ops.center_on_selection()

    def frame_scene_bounds(self, bounds: QRectF | None) -> bool:
        return self._ops.frame_scene_bounds(bounds)

    @staticmethod
    def graph_search_rank(
        query: str,
        *,
        title: str,
        display_name: str,
        type_id: str,
    ) -> int | None:
        return WorkspaceViewNavOps.graph_search_rank(
            query,
            title=title,
            display_name=display_name,
            type_id=type_id,
        )

    def search_graph_nodes(
        self,
        query: str,
        limit: int,
        *,
        enabled_scopes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        return self._ops.search_graph_nodes(query, limit, enabled_scopes=enabled_scopes)

    def jump_to_graph_node(self, workspace_id: str, node_id: str) -> bool:
        return self._ops.jump_to_graph_node(workspace_id, node_id)

    def create_view(self) -> None:
        self._ops.create_view()

    def switch_view(self, view_id: str) -> None:
        self._ops.switch_view(view_id)

    def create_workspace(self) -> None:
        presenter = getattr(self._host, "shell_host_presenter", None)
        prompt_text_value = getattr(presenter, "prompt_text_value", None)
        if callable(prompt_text_value):
            name, ok = prompt_text_value(title="New Workspace", label="Workspace name:")
        else:
            from PyQt6.QtWidgets import QInputDialog

            name, ok = QInputDialog.getText(self._dialog_parent(), "New Workspace", "Workspace name:")
        if not ok:
            return
        workspace_id = self._host.workspace_manager.create_workspace(name=name or None)
        self._host.runtime_history.clear_workspace(workspace_id)
        self.refresh_workspace_tabs()
        self.switch_workspace(workspace_id)

    def rename_active_workspace(self) -> None:
        index = self._host.workspace_tabs.currentIndex()
        if index < 0:
            return
        workspace_id = self._host.workspace_tabs.tabData(index)
        self.rename_workspace_by_id(workspace_id)

    def rename_workspace_by_id(self, workspace_id: str) -> bool:
        normalized_workspace_id = str(workspace_id or "").strip()
        if not normalized_workspace_id:
            return False
        workspace = self._host.model.project.workspaces.get(normalized_workspace_id)
        if workspace is None:
            return False
        presenter = getattr(self._host, "shell_host_presenter", None)
        prompt_text_value = getattr(presenter, "prompt_text_value", None)
        if callable(prompt_text_value):
            name, ok = prompt_text_value(
                title="Rename Workspace",
                label="New name:",
                text=workspace.name,
            )
        else:
            from PyQt6.QtWidgets import QInputDialog

            name, ok = QInputDialog.getText(self._dialog_parent(), "Rename Workspace", "New name:", text=workspace.name)
        normalized_name = str(name or "").strip()
        if not ok or not normalized_name or normalized_name == workspace.name:
            return False
        old_name = workspace.name
        self._host.workspace_manager.rename_workspace(normalized_workspace_id, normalized_name)
        project_session_controller = getattr(self._host, "project_session_controller", None)
        store_provider = getattr(project_session_controller, "project_artifact_store", None)
        store_setter = getattr(project_session_controller, "replace_project_artifact_store", None)
        if callable(store_provider) and callable(store_setter):
            store = store_provider()
            if store.rename_workspace_artifact_folder(
                workspace_id=normalized_workspace_id,
                old_name=old_name,
                new_name=normalized_name,
            ):
                store_setter(store)
        self.refresh_workspace_tabs()
        return True

    def duplicate_active_workspace(self) -> None:
        index = self._host.workspace_tabs.currentIndex()
        if index < 0:
            return
        workspace_id = self._host.workspace_tabs.tabData(index)
        if not workspace_id:
            return
        duplicated_id = self._host.workspace_manager.duplicate_workspace(workspace_id)
        self._host.runtime_history.clear_workspace(duplicated_id)
        self.refresh_workspace_tabs()
        self.switch_workspace(duplicated_id)

    def close_active_workspace(self) -> None:
        index = self._host.workspace_tabs.currentIndex()
        if index >= 0:
            self.on_workspace_tab_close(index)

    def close_workspace_by_id(self, workspace_id: str) -> bool:
        normalized_workspace_id = str(workspace_id or "").strip()
        if not normalized_workspace_id:
            return False
        target_index = -1
        for index in range(self._host.workspace_tabs.count()):
            if self._host.workspace_tabs.tabData(index) != normalized_workspace_id:
                continue
            target_index = index
            break
        if target_index < 0:
            return False
        self.on_workspace_tab_close(target_index)
        return normalized_workspace_id not in self._host.model.project.workspaces

    def _dialog_parent(self):
        # The controller's host is an adapter, not a QWidget; QMessageBox/QDialog
        # require a real QWidget (or None) parent or they raise TypeError.
        return resolve_dialog_parent(self._host)

    def close_view(self, view_id: str) -> bool:
        from PyQt6.QtWidgets import QMessageBox

        workspace_id = self._host.workspace_manager.active_workspace_id()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        normalized_view_id = str(view_id or "").strip()
        if workspace is None or not normalized_view_id:
            return False
        mutation_service = self._host.model.workspace_view_mutations(workspace_id)
        mutation_service.active_view_state()
        if normalized_view_id not in workspace.views:
            return False
        if len(workspace.views) == 1:
            QMessageBox.warning(self._dialog_parent(), "View", "Cannot close the last view.")
            return False

        active_view_closed = workspace.active_view_id == normalized_view_id
        mutation_service.close_view(normalized_view_id)
        if active_view_closed:
            self.restore_active_view_state()
            self._host.scene.sync_scope_with_active_view()
            self._host.search_scope_controller.restore_scope_camera()

        self._host.search_scope_controller.discard_scope_camera_for_view(workspace_id, normalized_view_id)
        self._host.workspace_state_changed.emit()
        return True

    def rename_view(self, view_id: str) -> bool:
        workspace_id = self._host.workspace_manager.active_workspace_id()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        normalized_view_id = str(view_id or "").strip()
        if workspace is None or not normalized_view_id:
            return False
        mutation_service = self._host.model.workspace_view_mutations(workspace_id)
        mutation_service.active_view_state()
        view = workspace.views.get(normalized_view_id)
        if view is None:
            return False

        presenter = getattr(self._host, "shell_host_presenter", None)
        prompt_text_value = getattr(presenter, "prompt_text_value", None)
        if callable(prompt_text_value):
            name, ok = prompt_text_value(
                title="Rename View",
                label="New name:",
                text=view.name,
            )
        else:
            from PyQt6.QtWidgets import QInputDialog

            name, ok = QInputDialog.getText(self._dialog_parent(), "Rename View", "New name:", text=view.name)
        if not ok:
            return False
        normalized_name = str(name or "").strip()
        if not normalized_name or normalized_name == view.name:
            return False

        mutation_service.rename_view(normalized_view_id, normalized_name)
        self._host.workspace_state_changed.emit()
        return True

    def move_view(self, from_index: int, to_index: int) -> bool:
        workspace_id = self._host.workspace_manager.active_workspace_id()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if workspace is None:
            return False
        mutation_service = self._host.model.workspace_view_mutations(workspace_id)
        mutation_service.active_view_state()
        if len(workspace.views) < 2:
            return False
        if from_index < 0 or from_index >= len(workspace.views):
            return False
        bounded_index = max(0, min(int(to_index), len(workspace.views) - 1))
        if from_index == bounded_index:
            return False
        mutation_service.move_view(from_index, bounded_index)
        self._host.workspace_state_changed.emit()
        return True

    def on_workspace_tab_changed(self, index: int) -> None:
        if index < 0:
            return
        workspace_id = self._host.workspace_tabs.tabData(index)
        if workspace_id:
            self.switch_workspace(workspace_id)

    def on_workspace_tab_close(self, index: int) -> None:
        from PyQt6.QtWidgets import QMessageBox

        workspace_id = self._host.workspace_tabs.tabData(index)
        if not workspace_id:
            return
        workspace = self._host.model.project.workspaces[workspace_id]
        if workspace.dirty:
            reply = QMessageBox.question(
                self._dialog_parent(),
                "Unsaved Changes",
                f"Workspace '{workspace.name}' has unsaved changes. Close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            self._host.workspace_manager.close_workspace(workspace_id)
        except ValueError:
            QMessageBox.warning(self._dialog_parent(), "Workspace", "Cannot close the last workspace.")
            return
        retirement_error = ""
        try:
            self._host.execution_client.retire_workspace(workspace_id)
        except Exception as exc:  # noqa: BLE001
            retirement_error = str(exc).strip() or "unknown cleanup error"
            logger.exception("Workspace runtime retirement failed after close")
        self._host.runtime_history.clear_workspace(workspace_id)
        self.refresh_workspace_tabs()
        self.switch_workspace(self._host.workspace_manager.active_workspace_id())
        if retirement_error:
            QMessageBox.warning(
                self._dialog_parent(),
                "Workspace Cleanup",
                f"The workspace closed, but runtime cleanup failed: {retirement_error}",
            )

    def focus_failed_node(self, workspace_id: str, node_id: str) -> None:
        self._ops.focus_failed_node(workspace_id, node_id)

    def reveal_parent_chain(self, workspace_id: str, node_id: str) -> list[str]:
        return self._ops.reveal_parent_chain(workspace_id, node_id)
