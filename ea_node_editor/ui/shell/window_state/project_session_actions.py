from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import pyqtSlot

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


class ShellWindowProjectSessionActionsMixin:
    @pyqtSlot()
    def request_save_project(self: "ShellWindow") -> None:
        self._save_project()

    @pyqtSlot()
    def request_save_project_as(self: "ShellWindow") -> None:
        self._save_project_as()

    @pyqtSlot()
    def request_open_project(self: "ShellWindow") -> None:
        self._open_project()

    def _ensure_project_metadata_defaults(self: "ShellWindow"):
        return self.project_session_controller.ensure_project_metadata_defaults()

    def _workflow_settings_payload(self: "ShellWindow"):
        return self.project_session_controller.workflow_settings_payload()

    def _persist_script_editor_state(self: "ShellWindow"):
        return self.project_session_controller.persist_script_editor_state()

    def _restore_script_editor_state(self: "ShellWindow"):
        return self.project_session_controller.restore_script_editor_state()

    def _save_project(self: "ShellWindow"):
        return self.project_session_controller.save_project()

    def _save_project_as(self: "ShellWindow"):
        return self.project_session_controller.save_project_as()

    def _show_project_files(self: "ShellWindow"):
        return self.project_session_controller.show_project_files_dialog()

    def _new_project(self: "ShellWindow"):
        return self.project_session_controller.new_project()

    def _open_project(self: "ShellWindow"):
        return self.project_session_controller.open_project()

    def _open_project_path(self: "ShellWindow", path):
        return self.project_session_controller.open_project_path(path)



    def _clear_recent_projects(self: "ShellWindow"):
        return self.project_session_controller.clear_recent_projects()

    def _restore_session(self: "ShellWindow"):
        return self.project_session_controller.restore_session()

    def _discard_autosave_snapshot(self: "ShellWindow"):
        return self.project_session_controller.discard_autosave_snapshot()

    def _recover_autosave_if_newer(self: "ShellWindow"):
        return self.project_session_controller.recover_autosave_if_newer()

    def _process_deferred_autosave_recovery(self: "ShellWindow"):
        return self.project_session_controller.process_deferred_autosave_recovery()

    def _autosave_tick(self: "ShellWindow"):
        return self.project_session_controller.autosave_tick()

    def _persist_session(self: "ShellWindow", project_doc=None):
        return self.project_session_controller.persist_session(project_doc)

    def _prompt_recover_autosave(self: "ShellWindow", recovered_project=None):
        return self.project_session_controller.prompt_recover_autosave(recovered_project)


__all__ = [
    "ShellWindowProjectSessionActionsMixin",
]
