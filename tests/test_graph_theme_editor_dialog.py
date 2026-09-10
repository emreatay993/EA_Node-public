from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QCheckBox, QComboBox, QLineEdit, QMessageBox, QWidget

from ea_node_editor.settings import DEFAULT_APP_PREFERENCES
from ea_node_editor.ui.dialogs.graph_theme_editor_dialog import GraphThemeEditorDialog
from ea_node_editor.ui.graph_theme import GRAPH_THEME_REGISTRY, resolve_graph_theme
from ea_node_editor.ui.shell.tooltip_policy import TOOLTIP_CATEGORY_GENERAL
from tests.main_window_shell.base import MainWindowShellTestBase

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _custom_theme(theme_id: str = "custom_graph_theme_deadbeef", label: str = "Ocean Wire") -> dict[str, object]:
    custom_theme = copy.deepcopy(resolve_graph_theme("graph_stitch_light").as_dict())
    custom_theme["theme_id"] = theme_id
    custom_theme["label"] = label
    return custom_theme


class GraphThemeEditorDialogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])

    def test_dialog_imports_split_support_module_for_tree_preview_and_widget_helpers(self) -> None:
        dialog_text = (
            _REPO_ROOT / "ea_node_editor" / "ui" / "dialogs" / "graph_theme_editor_dialog.py"
        ).read_text(encoding="utf-8")
        support_text = (
            _REPO_ROOT / "ea_node_editor" / "ui" / "dialogs" / "graph_theme_editor_support.py"
        ).read_text(encoding="utf-8")

        self.assertIn("from ea_node_editor.ui.dialogs.graph_theme_editor_support import (", dialog_text)
        self.assertIn("build_theme_tree_items", dialog_text)
        self.assertIn("resolve_preview_metadata", dialog_text)
        self.assertIn("resolve_theme_action_state", dialog_text)
        self.assertIn("resolve_theme_ids_after_delete", dialog_text)
        self.assertIn("update_custom_theme_token", dialog_text)
        self.assertIn("validate_custom_theme_tokens", dialog_text)
        self.assertIn("class CollapsibleSection(QWidget):", support_text)
        self.assertIn("def build_theme_tree_items(", support_text)
        self.assertIn("def resolve_preview_metadata(", support_text)
        self.assertIn("class GraphThemeActionState:", support_text)
        self.assertIn("class GraphThemeValidationResult:", support_text)
        self.assertIn("def resolve_theme_action_state(", support_text)
        self.assertIn("def resolve_theme_ids_after_delete(", support_text)
        self.assertIn("def update_custom_theme_token(", support_text)
        self.assertIn("def validate_custom_theme_tokens(", support_text)

    def test_dialog_groups_built_in_and_custom_themes_and_only_custom_tokens_are_editable(self) -> None:
        custom_theme = _custom_theme()
        custom_theme["node_tokens"].update(
            {
                "header_bg": "#223344",
                "header_gradient_enabled": True,
                "header_gradient_color": "#334455",
                "header_gradient_direction": "west",
            }
        )
        custom_theme["category_accent_tokens"] = {"core": "#44AAFF"}
        dialog = GraphThemeEditorDialog(
            initial_settings={
                "follow_shell_theme": True,
                "selected_theme_id": "graph_stitch_dark",
                "custom_themes": [custom_theme],
            }
        )
        try:
            self.assertEqual(dialog.theme_tree.topLevelItemCount(), 2)
            self.assertEqual(dialog.theme_tree.topLevelItem(0).text(0), "Built-in Themes")
            self.assertEqual(dialog.theme_tree.topLevelItem(1).text(0), "Custom Themes")
            self.assertEqual(dialog.theme_tree.topLevelItem(0).childCount(), len(GRAPH_THEME_REGISTRY))
            self.assertEqual(dialog.theme_tree.topLevelItem(1).childCount(), 1)

            card_bg_value = dialog.findChild(QLineEdit, "node_tokens_card_bg_value")
            header_fg_value = dialog.findChild(QLineEdit, "node_tokens_header_fg_value")
            self.assertIsNotNone(card_bg_value)
            self.assertIsNotNone(header_fg_value)
            self.assertEqual(dialog.theme_id_field.text(), "graph_stitch_dark")
            self.assertEqual(dialog.theme_mode_field.text(), "Built-in theme (read-only)")
            self.assertFalse(dialog.rename_button.isEnabled())
            self.assertFalse(dialog.delete_button.isEnabled())
            self.assertTrue(dialog.duplicate_button.isEnabled())
            self.assertTrue(dialog.use_selected_button.isEnabled())
            self.assertTrue(card_bg_value.isReadOnly())
            self.assertEqual(card_bg_value.text(), resolve_graph_theme("graph_stitch_dark").node_tokens.card_bg)

            dialog.theme_tree.setCurrentItem(dialog._theme_items[custom_theme["theme_id"]])
            self.assertEqual(dialog.theme_mode_field.text(), "Custom theme (editable)")
            self.assertFalse(card_bg_value.isReadOnly())

            card_bg_value.setText("#123456")
            card_gradient_enabled = dialog.findChild(QCheckBox, "node_tokens_card_gradient_enabled_value")
            card_gradient_color = dialog.findChild(QLineEdit, "node_tokens_card_gradient_color_value")
            card_gradient_direction = dialog.findChild(QComboBox, "node_tokens_card_gradient_direction_value")
            self.assertIsNotNone(card_gradient_enabled)
            self.assertIsNotNone(card_gradient_color)
            self.assertIsNotNone(card_gradient_direction)
            self.assertIsNone(dialog.findChild(QLineEdit, "node_tokens_header_bg_value"))
            self.assertIsNone(dialog.findChild(QCheckBox, "node_tokens_header_gradient_enabled_value"))
            self.assertEqual(dict(dialog._TOKEN_SECTIONS)["node_tokens"], "Passive Node Defaults")
            self.assertNotIn("category_accent_tokens", dict(dialog._TOKEN_SECTIONS))
            self.assertEqual(
                dialog.preview_note.text(),
                "Editing tokens applies live to passive node defaults when this is the active theme.",
            )
            card_gradient_enabled.setChecked(True)
            card_gradient_color.setText("#445566")
            card_gradient_direction.setCurrentIndex(card_gradient_direction.findData("radial"))

            settings = dialog.graph_theme_settings()
            self.assertEqual(settings["selected_theme_id"], "graph_stitch_dark")
            self.assertEqual(settings["custom_themes"][0]["node_tokens"]["card_bg"], "#123456")
            self.assertTrue(settings["custom_themes"][0]["node_tokens"]["card_gradient_enabled"])
            self.assertEqual(settings["custom_themes"][0]["node_tokens"]["card_gradient_color"], "#445566")
            self.assertEqual(settings["custom_themes"][0]["node_tokens"]["card_gradient_direction"], "radial")
            self.assertNotIn("header_bg", settings["custom_themes"][0]["node_tokens"])
            self.assertNotIn("header_gradient_enabled", settings["custom_themes"][0]["node_tokens"])
            self.assertNotIn("header_gradient_color", settings["custom_themes"][0]["node_tokens"])
            self.assertNotIn("header_gradient_direction", settings["custom_themes"][0]["node_tokens"])
            self.assertNotIn("category_accent_tokens", settings["custom_themes"][0])
        finally:
            dialog.close()

    def test_library_management_commands_update_custom_theme_list(self) -> None:
        dialog = GraphThemeEditorDialog(
            initial_settings={
                "follow_shell_theme": True,
                "selected_theme_id": "graph_stitch_dark",
                "custom_themes": [],
            }
        )
        try:
            dialog.duplicate_button.click()
            self.assertEqual(dialog.theme_tree.topLevelItem(1).childCount(), 1)
            duplicated_theme_id = dialog.theme_id_field.text()
            self.assertTrue(duplicated_theme_id.startswith("custom_graph_theme_"))
            self.assertEqual(dialog.theme_name_field.text(), "Graph Stitch Dark Copy")
            self.assertTrue(dialog.rename_button.isEnabled())
            self.assertTrue(dialog.delete_button.isEnabled())

            with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("Ocean Wire", True)):
                dialog.rename_button.click()
            self.assertEqual(dialog.theme_name_field.text(), "Ocean Wire")

            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                dialog.delete_button.click()
            self.assertEqual(dialog.theme_tree.topLevelItem(1).childCount(), 0)
            self.assertEqual(dialog.theme_id_field.text(), "graph_stitch_dark")
            self.assertFalse(dialog.rename_button.isEnabled())
            self.assertFalse(dialog.delete_button.isEnabled())

            dialog.new_button.click()
            self.assertEqual(dialog.theme_tree.topLevelItem(1).childCount(), 1)
            self.assertTrue(dialog.theme_id_field.text().startswith("custom_graph_theme_"))
            self.assertEqual(dialog.theme_name_field.text(), "Custom Graph Theme")
        finally:
            dialog.close()

    def test_use_selected_returns_explicit_graph_theme_settings(self) -> None:
        custom_theme = _custom_theme()
        dialog = GraphThemeEditorDialog(
            initial_settings={
                "follow_shell_theme": True,
                "selected_theme_id": "graph_stitch_dark",
                "custom_themes": [custom_theme],
            }
        )
        try:
            dialog.theme_tree.setCurrentItem(dialog._theme_items[custom_theme["theme_id"]])
            dialog.use_selected_button.click()

            self.assertTrue(dialog.use_selected_requested)
            self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)
            settings = dialog.graph_theme_settings()
            self.assertFalse(settings["follow_shell_theme"])
            self.assertEqual(settings["selected_theme_id"], custom_theme["theme_id"])
            self.assertEqual(settings["custom_themes"][0]["label"], custom_theme["label"])
        finally:
            dialog.close()

    def test_invalid_custom_hex_color_blocks_close_until_fixed(self) -> None:
        custom_theme = _custom_theme()
        dialog = GraphThemeEditorDialog(
            initial_settings={
                "follow_shell_theme": False,
                "selected_theme_id": custom_theme["theme_id"],
                "custom_themes": [custom_theme],
            }
        )
        try:
            warning_stroke_value = dialog.findChild(QLineEdit, "edge_tokens_warning_stroke_value")
            self.assertIsNotNone(warning_stroke_value)
            self.assertFalse(warning_stroke_value.isReadOnly())

            warning_stroke_value.setText("#12345")
            with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok) as warning:
                dialog.close_button.click()

            warning.assert_called_once()
            self.assertNotEqual(dialog.result(), dialog.DialogCode.Accepted)
            self.assertFalse(dialog.validation_message.isHidden())

            warning_stroke_value.setText("#123456")
            dialog.close_button.click()

            self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)
        finally:
            dialog.close()

    def test_clicking_built_in_theme_swatch_duplicates_theme_and_updates_value(self) -> None:
        dialog = GraphThemeEditorDialog(
            initial_settings={
                "follow_shell_theme": True,
                "selected_theme_id": "graph_stitch_dark",
                "custom_themes": [],
            }
        )
        try:
            swatch = dialog.findChild(QWidget, "node_tokens_card_bg_swatch")
            field = dialog.findChild(QLineEdit, "node_tokens_card_bg_value")

            self.assertIsNotNone(swatch)
            self.assertIsNotNone(field)
            self.assertEqual(dialog.theme_mode_field.text(), "Built-in theme (read-only)")
            self.assertEqual(dialog.theme_tree.topLevelItem(1).childCount(), 0)

            with patch(
                "ea_node_editor.ui.dialogs.passive_style_controls.QColorDialog.getColor",
                return_value=QColor("#AA5500"),
            ) as get_color:
                QTest.mouseClick(swatch, Qt.MouseButton.LeftButton)
                self.app.processEvents()

            get_color.assert_called_once()
            self.assertEqual(dialog.theme_mode_field.text(), "Custom theme (editable)")
            self.assertFalse(field.isReadOnly())
            self.assertEqual(field.text(), "#AA5500")
            self.assertEqual(dialog.theme_tree.topLevelItem(1).childCount(), 1)
            self.assertEqual(
                dialog.graph_theme_settings()["custom_themes"][0]["node_tokens"]["card_bg"],
                "#AA5500",
            )
        finally:
            dialog.close()

    def test_live_apply_callback_only_runs_for_active_explicit_custom_theme(self) -> None:
        active_theme = _custom_theme("custom_graph_theme_deadbeef", "Ocean Wire")
        inactive_theme = _custom_theme("custom_graph_theme_feedf00d", "Mint Wire")
        live_apply_calls: list[dict[str, object]] = []
        dialog = GraphThemeEditorDialog(
            initial_settings={
                "follow_shell_theme": False,
                "selected_theme_id": active_theme["theme_id"],
                "custom_themes": [active_theme, inactive_theme],
            },
            live_apply_callback=lambda settings: live_apply_calls.append(copy.deepcopy(settings)),
        )
        try:
            warning_stroke_value = dialog.findChild(QLineEdit, "edge_tokens_warning_stroke_value")
            self.assertIsNotNone(warning_stroke_value)

            warning_stroke_value.setText("#1188CC")
            self.assertEqual(len(live_apply_calls), 1)
            self.assertEqual(
                live_apply_calls[0]["custom_themes"][0]["edge_tokens"]["warning_stroke"],
                "#1188CC",
            )

            dialog.theme_tree.setCurrentItem(dialog._theme_items[inactive_theme["theme_id"]])
            warning_stroke_value.setText("#44AA22")
            self.assertEqual(len(live_apply_calls), 1)

            follow_shell_dialog = GraphThemeEditorDialog(
                initial_settings={
                    "follow_shell_theme": True,
                    "selected_theme_id": active_theme["theme_id"],
                    "custom_themes": [active_theme],
                },
                live_apply_callback=lambda settings: live_apply_calls.append(copy.deepcopy(settings)),
            )
            try:
                follow_shell_warning_value = follow_shell_dialog.findChild(QLineEdit, "edge_tokens_warning_stroke_value")
                self.assertIsNotNone(follow_shell_warning_value)
                follow_shell_warning_value.setText("#AA2299")
                self.assertEqual(len(live_apply_calls), 1)
            finally:
                follow_shell_dialog.close()
        finally:
            dialog.close()

    def test_reject_keeps_library_changes_for_close_style_exit(self) -> None:
        dialog = GraphThemeEditorDialog(
            initial_settings={
                "follow_shell_theme": True,
                "selected_theme_id": "graph_stitch_dark",
                "custom_themes": [],
            }
        )
        try:
            dialog.new_button.click()
            created_theme_id = dialog.theme_id_field.text()

            dialog.reject()

            self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)
            self.assertFalse(dialog.use_selected_requested)
            settings = dialog.graph_theme_settings()
            self.assertEqual(len(settings["custom_themes"]), 1)
            self.assertEqual(settings["custom_themes"][0]["theme_id"], created_theme_id)
            self.assertTrue(settings["follow_shell_theme"])
            self.assertEqual(settings["selected_theme_id"], "graph_stitch_dark")
        finally:
            dialog.close()


class GraphThemeEditorShellFlowTests(MainWindowShellTestBase):
    def test_dialog_uses_parent_tooltip_policy_for_use_selected_button_tooltip(self) -> None:
        self.window.tooltip_manager.set_tooltip_category_enabled(TOOLTIP_CATEGORY_GENERAL, False)
        dialog = GraphThemeEditorDialog(
            initial_settings=self.window.app_preferences_controller.graph_theme_settings(),
            parent=self.window,
        )
        try:
            self.assertEqual(dialog.use_selected_button.toolTip(), "")
        finally:
            dialog.close()

    def test_shell_flow_persists_manager_result(self) -> None:
        custom_theme = _custom_theme()
        updated_graph_theme = {
            "follow_shell_theme": False,
            "selected_theme_id": custom_theme["theme_id"],
            "custom_themes": [custom_theme],
        }

        with patch.object(
            self.window.shell_host_presenter,
            "edit_graph_theme_settings",
            return_value=updated_graph_theme,
        ):
            self.window.show_graph_theme_editor_dialog()
        self.app.processEvents()

        persisted = json.loads(self._app_preferences_path.read_text(encoding="utf-8"))
        expected_document = copy.deepcopy(DEFAULT_APP_PREFERENCES)
        expected_document["graphics"]["graph_theme"] = updated_graph_theme

        self.assertEqual(persisted["graphics"]["graph_theme"], expected_document["graphics"]["graph_theme"])
        self.assertEqual(self.window.graph_theme_bridge.theme_id, custom_theme["theme_id"])

    def test_live_custom_theme_edit_updates_bridge_and_scene_payloads(self) -> None:
        custom_theme = _custom_theme()
        updated_graphics = copy.deepcopy(DEFAULT_APP_PREFERENCES["graphics"])
        updated_graphics["graph_theme"] = {
            "follow_shell_theme": False,
            "selected_theme_id": custom_theme["theme_id"],
            "custom_themes": [custom_theme],
        }
        self.window.app_preferences_controller.set_graphics_settings(updated_graphics, host=self.window)
        self.app.processEvents()

        constant_id = self.window.scene.add_node_from_type("core.constant", 220.0, 20.0)
        if_id = self.window.scene.add_node_from_type("core.if", 500.0, 20.0)
        workspace_id, _workspace = self._active_workspace()
        edge_id = self.window.model._add_edge_record(
            workspace_id,
            source_node_id=constant_id,
            source_port_key="as_text",
            target_node_id=if_id,
            target_port_key="condition",
        ).edge_id
        self.window.scene.refresh_workspace_from_model(workspace_id)
        self.assertEqual(
            {item["edge_id"]: item for item in self.window.scene.edges_model}[edge_id]["color"],
            custom_theme["edge_tokens"]["warning_stroke"],
        )

        dialog = GraphThemeEditorDialog(
            initial_settings=self.window.app_preferences_controller.graph_theme_settings(),
            parent=self.window,
            live_apply_callback=self.window.preview_graph_theme_settings,
        )
        try:
            warning_stroke_value = dialog.findChild(QLineEdit, "edge_tokens_warning_stroke_value")
            self.assertIsNotNone(warning_stroke_value)

            warning_stroke_value.setText("#1188CC")
            self.app.processEvents()

            self.assertEqual(self.window.graph_theme_bridge.theme_id, custom_theme["theme_id"])
            self.assertEqual(self.window.graph_theme_bridge.edge_palette["warning_stroke"], "#1188CC")
            self.assertEqual(
                {item["edge_id"]: item for item in self.window.scene.edges_model}[edge_id]["color"],
                "#1188CC",
            )
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
