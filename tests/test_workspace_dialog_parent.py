from __future__ import annotations

import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QMessageBox, QWidget

from ea_node_editor.ui.shell.controllers.dialog_support import resolve_dialog_parent
from tests.main_window_shell.base import MainWindowShellTestBase


class WorkspaceDeleteDialogParentTests(MainWindowShellTestBase):
    """Deleting a workspace must give its confirmation dialog a real QWidget parent.

    Shell controllers now receive the ``ShellWindow`` directly, which is a
    QWidget, so ``resolve_dialog_parent`` resolves it as the dialog parent.
    Historically the controllers received a non-QWidget host adapter; passing
    that as the ``QMessageBox`` parent raised ``TypeError`` before any dialog
    was shown, which (uncaught in a QML-invoked slot) aborted the app with
    0xC0000409. This test keeps the dialog-parent contract pinned either way.
    """

    def test_delete_dirty_workspace_passes_qwidget_dialog_parent(self) -> None:
        # Duplicating marks the new workspace dirty, so deleting it goes through
        # the unsaved-changes confirmation -- the exact crashing path.
        self.window.request_duplicate_workspace()
        self.app.processEvents()
        dup_id = self.window.workspace_manager.active_workspace_id()
        self.assertTrue(self.window.model.project.workspaces[dup_id].dirty)

        captured: dict[str, object] = {}

        def _capture_question(parent, *args, **kwargs):
            captured["parent"] = parent
            return QMessageBox.StandardButton.Yes

        with (
            patch.object(QMessageBox, "question", side_effect=_capture_question),
            patch.object(QMessageBox, "warning") as warning,
        ):
            self.window.request_close_workspace_by_id(dup_id)

        # The dialog must be reached and given a real QWidget parent (not the adapter).
        self.assertIn("parent", captured)
        self.assertIsInstance(captured["parent"], QWidget)
        warning.assert_not_called()
        self.assertNotIn(dup_id, self.window.model.project.workspaces)


class ResolveDialogParentTests(unittest.TestCase):
    """The shared resolver every shell controller uses to parent dialogs."""

    def test_returns_dialog_parent_host_when_it_is_a_qwidget(self) -> None:
        window = QWidget()

        class _Adapter:
            dialog_parent_host = window

        self.assertIs(resolve_dialog_parent(_Adapter()), window)

    def test_returns_host_itself_when_it_is_a_qwidget(self) -> None:
        widget = QWidget()
        self.assertIs(resolve_dialog_parent(widget), widget)

    def test_returns_none_for_non_qwidget_host(self) -> None:
        class _NotAWidget:
            pass

        self.assertIsNone(resolve_dialog_parent(_NotAWidget()))
