from __future__ import annotations

import unittest

from PyQt6.QtWidgets import QApplication

from ea_node_editor.ui.dialogs.selected_run_settings_dialog import SelectedRunSettingsDialog


class SelectedRunSettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_defaults_to_preview_before_run_enabled(self) -> None:
        dialog = SelectedRunSettingsDialog()
        try:
            self.assertEqual(dialog.windowTitle(), "Run Settings")
            self.assertEqual(
                dialog.preview_before_run_check.objectName(),
                "selectedRunSettingsPreviewBeforeRunCheck",
            )
            self.assertTrue(dialog.preview_before_run_check.isChecked())
            self.assertEqual(dialog.values(), {"preview_before_run": True})
        finally:
            dialog.close()

    def test_dialog_values_round_trip_preview_toggle(self) -> None:
        dialog = SelectedRunSettingsDialog({"preview_before_run": False})
        try:
            self.assertFalse(dialog.preview_before_run_check.isChecked())
            self.assertFalse(dialog.selected_run_preview_before_run())
            dialog.preview_before_run_check.setChecked(True)
            self.assertEqual(dialog.values(), {"preview_before_run": True})
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
