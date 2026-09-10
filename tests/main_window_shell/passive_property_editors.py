from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QMetaObject
from PyQt6.QtGui import QColor

from ea_node_editor.persistence.serializer import JsonProjectSerializer
from tests.main_window_shell.base import *  # noqa: F401,F403
from tests.passive_property_editor_fixtures import register_passive_editor_fixture


class MainWindowShellPassivePropertyEditorsTests(SharedMainWindowShellTestBase):
    def setUp(self) -> None:
        super().setUp()
        register_passive_editor_fixture(self.window.registry)

    def test_collapsed_inspector_skips_selection_and_runtime_property_projection(self) -> None:
        pane = self._find_qml_item("inspectorPane")
        pane.setProperty("paneCollapsed", True)
        node_ids = [
            self.window.scene.create_node_from_type(
                type_id=type_id, x=index * 250, y=0,
                parent_node_id=None, select_node=False,
            )
            for index, type_id in enumerate(("plot.signal", "core.constant"))
        ]
        self.window.scene.clear_selection()
        self.app.processEvents()
        presenter = self.window.shell_inspector_presenter
        try:
            with patch.object(
                presenter, "_build_selected_node_property_items",
                wraps=presenter._build_selected_node_property_items,
            ) as projection:
                for node_id in node_ids * 3:
                    self.window.scene.select_node(node_id)
                    presenter._on_current_output_changed()
                    self.app.processEvents()
                    self.assertFalse(any(
                        item.objectName() == "inspectorPropertyEditor"
                        for item in self._walk_items(pane)
                    ))
                projection.assert_not_called()
                pane.setProperty("paneCollapsed", False)
                self.app.processEvents()
                self.assertGreater(projection.call_count, 0)
                self.assertEqual(pane.property("selectedNodeId"), node_ids[-1])
        finally:
            pane.setProperty("paneCollapsed", False)

    def test_inspector_hide_retains_draft_and_hidden_selection_retires_context(self) -> None:
        first_id = self.window.scene.add_node_from_type("tests.passive_editor_fixture", 0, 0)
        self.window.scene.focus_node(first_id)
        textarea = self._inspector_property_object("inspectorTextareaEditor", "notes_blob")
        textarea.setProperty("text", "unfinished draft")
        pane = self._find_qml_item("inspectorPane")
        try:
            for property_name, hidden, shown in (("paneCollapsed", True, False), ("activeTabIndex", 1, 0)):
                pane.setProperty(property_name, hidden)
                self.app.processEvents()
                self.window.shell_inspector_presenter._on_current_output_changed()
                pane.setProperty(property_name, shown)
                self.app.processEvents()
                self.assertEqual(self._find_qml_item("inspectorTextareaEditor"), textarea)
                self.assertEqual(textarea.property("text"), "unfinished draft")
            pane.setProperty("paneCollapsed", True)
            second_id = self.window.scene.add_node_from_type("tests.passive_editor_fixture", 250, 0)
            self.window.scene.focus_node(second_id)
            self.app.processEvents()
            self.assertIsNone(self._find_qml_item("inspectorTextareaEditor"))
            pane.setProperty("paneCollapsed", False)
            self.app.processEvents()
            replacement = self._inspector_property_object("inspectorTextareaEditor", "notes_blob")
            self.assertNotEqual(replacement.property("text"), "unfinished draft")
        finally:
            pane.setProperty("activeTabIndex", 0)
            pane.setProperty("paneCollapsed", False)

    def test_qml_textarea_editor_uses_explicit_apply_commit(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("tests.passive_editor_fixture", x=120.0, y=80.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        textarea = self._inspector_property_object("inspectorTextareaEditor", "notes_blob")
        apply_button = self._inspector_property_object("inspectorTextareaApplyButton", "notes_blob")
        updated_text = "Alpha\nBeta\nGamma"

        textarea.setProperty("text", updated_text)
        self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertNotEqual(node.properties["notes_blob"], updated_text)

        QMetaObject.invokeMethod(apply_button, "click")
        self.app.processEvents()

        self.assertEqual(node.properties["notes_blob"], updated_text)

    def test_qml_path_editor_browse_commits_selected_path(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("tests.passive_editor_fixture", x=120.0, y=80.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        picked_path = Path(self._env.temp_path) / "picked-asset.txt"
        picked_path.write_text("fixture", encoding="utf-8")

        path_editor = self._inspector_property_object("inspectorPathEditor", "media_ref")
        browse_button = self._inspector_property_object("inspectorPathBrowseButton", "media_ref")

        with patch("ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName", return_value=(str(picked_path), "")):
            QMetaObject.invokeMethod(browse_button, "click")
            self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertEqual(node.properties["media_ref"], str(picked_path))
        self.assertEqual(str(path_editor.property("text")), str(picked_path))

    def test_path_pointer_file_mode_browse_uses_file_picker(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("io.path_pointer", x=120.0, y=80.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        picked_path = Path(self._env.temp_path) / "picked-path-pointer.txt"
        picked_path.write_text("fixture", encoding="utf-8")

        path_editor = self._inspector_property_object("inspectorPathEditor", "path")
        browse_button = self._inspector_property_object("inspectorPathBrowseButton", "path")

        with (
            patch(
                "ea_node_editor.ui.shell.host_presenter.QFileDialog.getOpenFileName",
                return_value=(str(picked_path), ""),
            ) as open_file_dialog,
            patch("ea_node_editor.ui.shell.host_presenter.QFileDialog.getExistingDirectory") as open_directory_dialog,
        ):
            QMetaObject.invokeMethod(browse_button, "click")
            self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertEqual(node.properties["path"], str(picked_path))
        self.assertEqual(str(path_editor.property("text")), str(picked_path))
        open_file_dialog.assert_called_once()
        open_directory_dialog.assert_not_called()

    def test_path_pointer_folder_mode_browse_uses_directory_picker(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("io.path_pointer", x=120.0, y=80.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()
        self.window.set_selected_node_property("mode", "folder")
        self.app.processEvents()

        picked_directory = Path(self._env.temp_path) / "picked-path-pointer-folder"
        picked_directory.mkdir(parents=True, exist_ok=True)

        path_editor = self._inspector_property_object("inspectorPathEditor", "path")
        browse_button = self._inspector_property_object("inspectorPathBrowseButton", "path")

        with (
            patch("ea_node_editor.ui.shell.host_presenter.QFileDialog.getOpenFileName") as open_file_dialog,
            patch(
                "ea_node_editor.ui.shell.host_presenter.QFileDialog.getExistingDirectory",
                return_value=str(picked_directory),
            ) as open_directory_dialog,
        ):
            QMetaObject.invokeMethod(browse_button, "click")
            self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertEqual(node.properties["path"], str(picked_directory))
        self.assertEqual(str(path_editor.property("text")), str(picked_directory))
        open_directory_dialog.assert_called_once()
        open_file_dialog.assert_not_called()

    def test_folder_explorer_current_path_browse_uses_directory_picker(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("io.folder_explorer", x=120.0, y=80.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        property_items = {
            str(item["key"]): item
            for item in self.window.selected_node_property_items
        }
        self.assertEqual(property_items["current_path"]["editor_mode"], "path")
        self.assertEqual(property_items["current_path"]["path_dialog_mode"], "folder")

        picked_directory = Path(self._env.temp_path) / "picked-folder-explorer-root"
        picked_directory.mkdir(parents=True, exist_ok=True)

        path_editor = self._inspector_property_object("inspectorPathEditor", "current_path")
        browse_button = self._inspector_property_object("inspectorPathBrowseButton", "current_path")

        self.assertEqual(str(path_editor.property("pathDialogMode")), "folder")
        self.assertEqual(str(browse_button.property("pathDialogMode")), "folder")

        with (
            patch("ea_node_editor.ui.shell.host_presenter.QFileDialog.getOpenFileName") as open_file_dialog,
            patch(
                "ea_node_editor.ui.shell.host_presenter.QFileDialog.getExistingDirectory",
                return_value=str(picked_directory),
            ) as open_directory_dialog,
        ):
            QMetaObject.invokeMethod(browse_button, "click")
            self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertEqual(node.properties["current_path"], str(picked_directory))
        self.assertEqual(str(path_editor.property("text")), str(picked_directory))
        open_directory_dialog.assert_called_once()
        open_file_dialog.assert_not_called()

        document = JsonProjectSerializer(self.window.registry).to_persistent_document(self.window.model.project)
        workspace_doc = next(ws for ws in document["workspaces"] if ws["workspace_id"] == workspace_id)
        node_doc = next(node for node in workspace_doc["nodes"] if node["node_id"] == node_id)
        self.assertEqual(node_doc["properties"], {"current_path": str(picked_directory)})

    def test_qml_color_editor_picker_commits_selected_hex(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("tests.passive_editor_fixture", x=120.0, y=80.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        property_items = {
            str(item["key"]): item
            for item in self.window.selected_node_property_items
        }
        self.assertEqual(
            property_items["accent_color"]["editor_mode"],
            "color",
        )

        color_editor = self._inspector_property_object("inspectorColorEditor", "accent_color")
        pick_button = self._inspector_property_object("inspectorColorPickerButton", "accent_color")

        with patch(
            "ea_node_editor.ui.shell.host_presenter.QColorDialog.getColor",
            return_value=QColor("#AA5500"),
        ):
            QMetaObject.invokeMethod(pick_button, "click")
            self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertEqual(node.properties["accent_color"], "#AA5500")
        self.assertEqual(str(color_editor.property("text")), "#AA5500")

    def test_qml_color_editor_manual_hex_entry_commits_rgb_and_argb_values(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("tests.passive_editor_fixture", x=120.0, y=80.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        color_editor = self._inspector_property_object("inspectorColorEditor", "accent_color")
        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]

        color_editor.setProperty("text", "#112233")
        self.app.processEvents()
        QMetaObject.invokeMethod(color_editor, "editingFinished")
        self.app.processEvents()
        self.assertEqual(node.properties["accent_color"], "#112233")

        color_editor = self._inspector_property_object("inspectorColorEditor", "accent_color")
        color_editor.setProperty("text", "#80112233")
        self.app.processEvents()
        QMetaObject.invokeMethod(color_editor, "editingFinished")
        self.app.processEvents()
        self.assertEqual(node.properties["accent_color"], "#80112233")

    def test_qml_font_family_editor_commits_installed_font_and_default(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("passive.annotation.text", x=120.0, y=80.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        property_items = {
            str(item["key"]): item
            for item in self.window.selected_node_property_items
        }
        self.assertEqual(property_items["font_family"]["editor_mode"], "font_family")

        font_editor = self._inspector_property_object("inspectorFontFamilyEditor", "font_family")
        self.assertGreater(int(font_editor.property("optionCount")), 1)
        self.assertEqual(str(font_editor.property("firstOptionValue")), "Default")

        target_family = str(font_editor.property("secondOptionValue")).strip()
        self.assertTrue(target_family)
        font_editor.setProperty("editText", target_family)
        QMetaObject.invokeMethod(font_editor, "accepted")
        self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertEqual(node.properties["font_family"], target_family)

        font_editor = self._inspector_property_object("inspectorFontFamilyEditor", "font_family")
        font_editor.setProperty("editText", "Default")
        QMetaObject.invokeMethod(font_editor, "accepted")
        self.app.processEvents()

        self.assertEqual(node.properties["font_family"], "")
