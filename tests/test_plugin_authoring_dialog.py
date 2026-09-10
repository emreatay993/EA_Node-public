from __future__ import annotations

import unittest

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ea_node_editor.nodes.plugin_authoring import (
    PluginAuthoringDiagnostic,
    PluginAuthoringSummary,
    PluginIdentity,
    PluginValidationReport,
)
from ea_node_editor.ui.dialogs.plugin_authoring_dialog import (
    PluginAuthoringDialog,
    PluginAuthoringDraft,
)
from ea_node_editor.ui.editor.code_editor import PythonCodeEditor, PythonSyntaxHighlighter


class PluginAuthoringDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.source = "def run(value):\n    return {'result': value}\n"
        self.dialog = PluginAuthoringDialog(
            identity=PluginIdentity(
                visible_name="Scale Value",
                slug="scale_value",
                filename="scale_value.py",
                function_name="scale_value",
                node_id="custom.scale_value.a1b2c3d4",
            ),
            source=self.source,
        )
        self.addCleanup(self.dialog.deleteLater)

    def test_uses_existing_python_editor_and_highlighter(self) -> None:
        self.assertIsInstance(self.dialog.editor, PythonCodeEditor)
        self.assertIsInstance(self.dialog.editor._highlighter, PythonSyntaxHighlighter)
        self.assertTrue(self.dialog.node_id_edit.isReadOnly())
        self.assertEqual(
            self.dialog.draft(),
            PluginAuthoringDraft(
                visible_name="Scale Value",
                filename="scale_value.py",
                function_name="scale_value",
                node_id="custom.scale_value.a1b2c3d4",
                source=self.source,
            ),
        )

    def test_action_buttons_emit_controller_intents_without_closing(self) -> None:
        emitted: list[str] = []
        self.dialog.save_requested.connect(lambda: emitted.append("save"))
        self.dialog.validate_requested.connect(lambda: emitted.append("validate"))
        self.dialog.reload_requested.connect(lambda: emitted.append("reload"))
        self.dialog.open_plugins_folder_requested.connect(lambda: emitted.append("open"))

        self.dialog.save_button.click()
        self.dialog.validate_button.click()
        self.dialog.reload_button.click()
        self.dialog.open_plugins_folder_button.click()

        self.assertEqual(emitted, ["save", "validate", "reload", "open"])
        self.assertEqual(self.dialog.result(), 0)

    def test_dirty_source_blocks_reload_until_marked_saved(self) -> None:
        self.assertFalse(self.dialog.dirty)
        self.assertTrue(self.dialog.reload_button.isEnabled())

        self.dialog.editor.appendPlainText("# changed")

        self.assertTrue(self.dialog.dirty)
        self.assertFalse(self.dialog.reload_button.isEnabled())
        self.assertEqual(self.dialog.reload_status_label.text(), "Save changes before reloading.")

        self.dialog.mark_saved()

        self.assertFalse(self.dialog.dirty)
        self.assertTrue(self.dialog.reload_button.isEnabled())
        self.assertEqual(self.dialog.reload_status_label.text(), "")
        self.dialog.mark_current()
        self.assertEqual(self.dialog.status_label.text(), "Plugins are current.")

    def test_report_projects_summary_and_all_diagnostic_fields(self) -> None:
        report = PluginValidationReport(
            success=True,
            diagnostics=(
                PluginAuthoringDiagnostic(
                    filename="scale_value.py",
                    line=2,
                    column=5,
                    severity="warning",
                    message="numpy is not included in this COREX bundle.",
                    node_id="custom.scale_value.a1b2c3d4",
                    digest="abc123",
                    unavailable_reason="numpy is not included in this COREX bundle.",
                ),
            ),
            summary=PluginAuthoringSummary(
                bundle_count=1,
                node_count=1,
                plugin_digest="abc123",
                unavailable_node_count=1,
            ),
        )

        self.dialog.set_report(report)

        self.assertEqual(self.dialog.diagnostics_tree.topLevelItemCount(), 1)
        item = self.dialog.diagnostics_tree.topLevelItem(0)
        self.assertEqual(
            [item.text(column) for column in range(8)],
            [
                "scale_value.py",
                "2",
                "5",
                "warning",
                "custom.scale_value.a1b2c3d4",
                "abc123",
                "Unavailable",
                "numpy is not included in this COREX bundle.",
            ],
        )
        self.assertIn("1 bundle(s), 1 node(s)", self.dialog.summary_label.text())
        self.assertIn("abc123", self.dialog.summary_label.text())
        self.assertIn("1 unavailable", self.dialog.summary_label.text())

    def test_selecting_diagnostic_moves_cursor_and_focuses_editor(self) -> None:
        self.dialog.set_report(
            PluginValidationReport(
                success=False,
                diagnostics=(
                    PluginAuthoringDiagnostic(
                        filename="scale_value.py",
                        line=2,
                        column=5,
                        severity="error",
                        message="bad return",
                    ),
                ),
                summary=PluginAuthoringSummary(0, 0, "", 0),
            )
        )
        self.dialog.show()
        self.app.processEvents()

        self.dialog.focus_diagnostic(0)
        self.app.processEvents()

        cursor = self.dialog.editor.textCursor()
        self.assertEqual(cursor.blockNumber(), 1)
        self.assertEqual(cursor.columnNumber(), 4)
        self.assertTrue(self.dialog.editor.hasFocus())

    def test_foreign_diagnostic_does_not_move_or_focus_editor(self) -> None:
        self.dialog.set_report(
            PluginValidationReport(
                success=False,
                diagnostics=(
                    PluginAuthoringDiagnostic(
                        filename="other_plugin.py",
                        line=2,
                        column=5,
                        severity="error",
                        message="other plugin failed",
                    ),
                ),
                summary=PluginAuthoringSummary(0, 0, "", 0),
            )
        )
        self.dialog.show()
        self.app.processEvents()
        self.dialog.filename_edit.setFocus()
        initial_position = self.dialog.editor.textCursor().position()

        self.dialog.focus_diagnostic(0)
        self.app.processEvents()

        self.assertEqual(self.dialog.editor.textCursor().position(), initial_position)
        self.assertTrue(self.dialog.filename_edit.hasFocus())

    def test_same_basename_foreign_paths_do_not_move_or_focus_editor(self) -> None:
        self.dialog.set_report(
            PluginValidationReport(
                success=False,
                diagnostics=(
                    PluginAuthoringDiagnostic(
                        filename="package/scale_value.py",
                        line=2,
                        column=5,
                        severity="error",
                        message="bad return",
                    ),
                    PluginAuthoringDiagnostic(
                        filename=r"C:\Other\scale_value.py",
                        line=2,
                        column=5,
                        severity="error",
                        message="other plugin failed",
                    ),
                ),
                summary=PluginAuthoringSummary(0, 0, "", 0),
            )
        )
        self.dialog.show()
        self.app.processEvents()
        self.dialog.filename_edit.setFocus()
        initial_position = self.dialog.editor.textCursor().position()

        for index in range(2):
            self.dialog.focus_diagnostic(index)
            self.app.processEvents()

            self.assertEqual(self.dialog.editor.textCursor().position(), initial_position)
            self.assertTrue(self.dialog.filename_edit.hasFocus())

    def test_enter_edits_source_focus_starts_in_editor_and_close_is_explicit(self) -> None:
        self.dialog.show()
        self.app.processEvents()
        self.assertTrue(self.dialog.editor.hasFocus())
        before = self.dialog.editor.toPlainText()

        QTest.keyClick(self.dialog.editor, Qt.Key.Key_Return)
        self.app.processEvents()

        self.assertTrue(self.dialog.isVisible())
        self.assertEqual(len(self.dialog.editor.toPlainText()), len(before) + 1)
        self.dialog.close_button.click()
        self.app.processEvents()
        self.assertFalse(self.dialog.isVisible())

    def test_window_scoped_ctrl_s_saves_from_each_draft_field_once(self) -> None:
        emitted: list[str] = []
        self.dialog.save_requested.connect(lambda: emitted.append("save"))
        self.dialog.show()
        self.app.processEvents()

        for widget in (
            self.dialog.editor,
            self.dialog.visible_name_edit,
            self.dialog.filename_edit,
        ):
            widget.setFocus()
            self.app.processEvents()
            before = len(emitted)
            QTest.keyClick(widget, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
            self.app.processEvents()
            self.assertEqual(len(emitted), before + 1)

        self.dialog.editor.setFocus()
        self.dialog.editor.selectAll()
        QTest.keyClick(self.dialog.editor, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.app.processEvents()

        self.assertEqual(emitted, ["save", "save", "save"])
        self.assertTrue(self.dialog.editor.textCursor().hasSelection())


if __name__ == "__main__":
    unittest.main()
