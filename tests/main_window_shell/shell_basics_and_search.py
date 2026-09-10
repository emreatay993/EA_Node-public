from __future__ import annotations

import copy
import json
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import Q_ARG, QMetaObject, QObject, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtQml import QJSValue
from PyQt6.QtQuick import QQuickItem
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMenu, QMessageBox

from ea_node_editor.nodes.builtins.core import PYTHON_SCRIPT_DEFAULT_SOURCE
from ea_node_editor.ui.dialogs.input_reference_dialog import (
    INPUT_REFERENCE_SECTIONS,
    InputReferenceDialog,
    iter_input_reference_entries,
)
from ea_node_editor.ui_qml.shell_addon_manager_bridge import ShellAddOnManagerBridge
from tests.main_window_shell.base import *  # noqa: F401,F403
from tests.main_window_shell.base import _action_shortcuts
from tests.qt_wait import wait_for_condition_or_raise


def _color_name(value: object, *, include_alpha: bool = False) -> str:
    name_format = QColor.NameFormat.HexArgb if include_alpha else QColor.NameFormat.HexRgb
    return QColor(value).name(name_format)


def _alpha_color_name(value: str, alpha: float) -> str:
    color = QColor(value)
    color.setAlphaF(alpha)
    return _color_name(color, include_alpha=True)


def _capture_graphics_fanout(window) -> dict[str, int]:  # noqa: ANN001
    events = {"host": 0, "workspace": 0, "state": 0, "nodes": 0, "edges": 0}
    for name, signal in (
        ("host", window.graphics_preferences_changed),
        ("workspace", window.shell_workspace_presenter.graphics_preferences_changed),
        ("state", window.graph_canvas_state_bridge.graphics_preferences_changed),
        ("nodes", window.scene.nodes_changed),
        ("edges", window.scene.edges_changed),
    ):
        signal.connect(lambda name=name: events.__setitem__(name, events[name] + 1))
    return events


@contextmanager
def _patched_graphics_settings_dialog(dialog_type):
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "ea_node_editor.ui.dialogs.graphics_settings_dialog.GraphicsSettingsDialog",
                dialog_type,
            )
        )
        stack.enter_context(patch("ea_node_editor.ui.dialogs.GraphicsSettingsDialog", dialog_type))
        yield


@contextmanager
def _patched_selected_run_settings_dialog(dialog_type):
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "ea_node_editor.ui.dialogs.selected_run_settings_dialog.SelectedRunSettingsDialog",
                dialog_type,
            )
        )
        stack.enter_context(patch("ea_node_editor.ui.dialogs.SelectedRunSettingsDialog", dialog_type))
        yield


def _named_child_items(root: QObject, object_name: str) -> list[QQuickItem]:
    matches: list[QQuickItem] = []

    def _visit(item: QObject) -> None:
        if not isinstance(item, QQuickItem):
            return
        if item.objectName() == object_name:
            matches.append(item)
        for child in item.childItems():
            _visit(child)

    _visit(root)
    return matches


def _active_tab_label(strip: QObject) -> tuple[QQuickItem, QObject]:
    slots = strip.property("tabSlots")
    if isinstance(slots, QJSValue):
        slots = slots.toVariant()
    slot_items = [slot for slot in (slots or []) if isinstance(slot, QQuickItem)]
    if not slot_items:
        raise AssertionError("Expected at least one tab slot.")

    for slot in slot_items:
        button = next(
            (
                child
                for child in slot.children()
                if isinstance(child, QQuickItem) and child.property("active") is not None
            ),
            None,
        )
        if button is None or not bool(button.property("active")):
            continue
        label = next(
            (
                child
                for child in button.children()
                if child.metaObject().className() == "QQuickText" and str(child.property("text") or "").strip()
            ),
            None,
        )
        if label is None:
            raise AssertionError("Expected an active tab label text item.")
        return button, label

    raise AssertionError("Expected at least one active tab button.")


def _tab_button_labels_by_label(strip: QObject) -> dict[str, tuple[QQuickItem, QObject]]:
    slots = strip.property("tabSlots")
    if isinstance(slots, QJSValue):
        slots = slots.toVariant()
    slot_items = [slot for slot in (slots or []) if isinstance(slot, QQuickItem)]
    entries_by_label: dict[str, tuple[QQuickItem, QObject]] = {}

    for slot in slot_items:
        button = next(
            (
                child
                for child in slot.children()
                if isinstance(child, QQuickItem) and child.property("itemData") is not None
            ),
            None,
        )
        if button is None:
            continue
        label = next(
            (
                child
                for child in button.children()
                if child.metaObject().className() == "QQuickText" and str(child.property("text") or "").strip()
            ),
            None,
        )
        if label is None:
            continue
        entries_by_label[str(label.property("text"))] = (button, label)

    return entries_by_label


def _tab_buttons_by_label(strip: QObject) -> dict[str, QQuickItem]:
    return {
        label_text: button
        for label_text, (button, _label_item) in _tab_button_labels_by_label(strip).items()
    }


def _input_reference_visible_rows(dialog: InputReferenceDialog) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    tree = dialog.reference_tree
    for section_index in range(tree.topLevelItemCount()):
        section_item = tree.topLevelItem(section_index)
        if section_item.isHidden():
            continue
        for child_index in range(section_item.childCount()):
            child = section_item.child(child_index)
            if child.isHidden():
                continue
            rows.append((child.text(0), child.text(1), child.text(2)))
    return rows


def _strip_child(strip: QObject, object_name: str) -> QObject:
    child = strip.findChild(QObject, object_name)
    if child is None:
        raise AssertionError(f"Expected child {object_name!r} under strip {strip.objectName()!r}.")
    return child


class MainWindowShellBasicsAndSearchTests(SharedMainWindowShellTestBase):
    def _reopen_window(self) -> None:
        self._reopen_shared_window()

    def _set_graph_search_scopes(self, enabled_scopes: set[str]) -> None:
        ordered_scopes = [scope_id for scope_id in ("title", "type", "content", "port") if scope_id in enabled_scopes]
        for scope_id in ("title", "type", "content", "port"):
            if scope_id in enabled_scopes:
                self.window.set_graph_search_scope_enabled(scope_id, True)
        for scope_id in ("title", "type", "content", "port"):
            if scope_id not in enabled_scopes:
                self.window.set_graph_search_scope_enabled(scope_id, False)
        self.app.processEvents()
        self.assertEqual(self.window.graph_search_enabled_scopes, ordered_scopes)

    def test_menu_bar_exposes_settings_menu_for_workflow_preferences(self) -> None:
        menu_actions = {
            action.text(): action.menu()
            for action in self.window.menuBar().actions()
            if action.menu() is not None
        }

        self.assertIn("&Settings", menu_actions)
        self.assertNotIn("&Tools", menu_actions)

        settings_entries = [
            action.text()
            for action in menu_actions["&Settings"].actions()
            if not action.isSeparator()
        ]
        self.assertEqual(settings_entries, ["Workflow Settings", "Graphics Settings"])

    def test_menu_bar_exposes_help_menu_for_keyboard_mouse_reference(self) -> None:
        menu_actions = {
            action.text(): action.menu()
            for action in self.window.menuBar().actions()
            if action.menu() is not None
        }

        self.assertIn("&Help", menu_actions)
        help_entries = [
            action.text()
            for action in menu_actions["&Help"].actions()
            if not action.isSeparator()
        ]
        self.assertEqual(help_entries, ["Keyboard and Mouse Reference", "Third-Party Notices"])
        self.assertIs(menu_actions["&Help"].actions()[0], self.window.action_keyboard_mouse_reference)
        self.assertIs(menu_actions["&Help"].actions()[1], self.window.action_third_party_notices)

    def test_view_menu_exposes_node_browser(self) -> None:
        view_menu = next(
            action.menu()
            for action in self.window.menuBar().actions()
            if action.text() == "&View"
        )
        actions = [action for action in view_menu.actions() if not action.isSeparator()]

        self.assertIn("Node Browser", [action.text() for action in actions])
        self.assertIs(actions[0], self.window.action_node_browser)

    def test_file_menu_exposes_project_review_deck_export_next_to_canvas_export(self) -> None:
        menu_actions = {
            action.text(): action.menu()
            for action in self.window.menuBar().actions()
            if action.menu() is not None
        }

        file_actions = [
            action
            for action in menu_actions["&File"].actions()
            if not action.isSeparator()
        ]
        file_entries = [action.text() for action in file_actions]

        self.assertIn("Export Canvas Views...", file_entries)
        self.assertIn("Export Project Review Deck...", file_entries)
        canvas_index = file_entries.index("Export Canvas Views...")
        self.assertEqual(file_entries[canvas_index + 1], "Export Project Review Deck...")
        self.assertIs(file_actions[canvas_index + 1], self.window.action_export_project_review_deck)
        self.assertIsNotNone(self.window.project_review_deck_presenter)

    def test_keyboard_mouse_reference_dialog_lists_user_inputs(self) -> None:
        dialog = InputReferenceDialog(parent=self.window)
        try:
            self.assertEqual(dialog.reference_tree.topLevelItemCount(), len(INPUT_REFERENCE_SECTIONS))

            entries = {(entry.context, entry.input): entry.action for entry in iter_input_reference_entries()}
            self.assertGreaterEqual(len(entries), 100)
            self.assertEqual(entries[("Project", "Ctrl+N")], "Create a new project.")
            self.assertEqual(entries[("Node Browser", "Ctrl+B")], "Open the node browser.")
            self.assertEqual(
                entries[("Selected edge", "Ctrl+Left or Ctrl+Right")],
                "Center the view on the edge start or end.",
            )
            self.assertEqual(
                entries[("Empty canvas", "W+left-drag")],
                "Select wires crossed by the marquee.",
            )
            self.assertEqual(
                entries[("Empty canvas", "W+Shift+left-drag")],
                "Add crossed wires to the current selection.",
            )
            self.assertEqual(
                entries[("Connected port", "Ctrl+drag")],
                "Reconnect the incident wire endpoints as one operation.",
            )
            self.assertEqual(
                entries[("Connected port", "Ctrl+drag to empty canvas")],
                "Disconnect the incident wires as one operation.",
            )
            self.assertEqual(
                entries[("Connected port", "Ctrl+Shift+drag")],
                "Copy the sole or selected incident wire to a compatible endpoint.",
            )
            self.assertEqual(
                entries[("Viewport", "Middle+right click")],
                "Toggle unused optional data ports for the active view.",
            )
            self.assertEqual(
                entries[("Node body", "Right-click")],
                "Open the node context menu, including Add Link and Add Comment for editable nodes.",
            )
            self.assertEqual(
                entries[("Panel", "Double-click")],
                "Open the Panel Text/Data editor.",
            )
            self.assertEqual(
                entries[("Panel", "Right-click")],
                "Open Edit values and interpretation..., Copy, and Copy as tree actions.",
            )
            self.assertEqual(
                entries[("Media Panel (PDF mode)", "Left or Right")],
                "Move the selected PDF-mode Media Panel to the previous or next page.",
            )
            self.assertEqual(
                entries[("PDF fullscreen", "Left or Right")],
                "Move to the previous or next PDF page.",
            )
            self.assertEqual(
                entries[("PDF fullscreen", "Mouse wheel")],
                "Move to the previous or next PDF page.",
            )
            self.assertEqual(
                entries[("PDF fullscreen", "Page Up or Page Down")],
                "Move to the previous or next PDF page.",
            )
            self.assertEqual(
                entries[("PDF fullscreen", "Home or End")],
                "Move to the first or last PDF page.",
            )
            self.assertEqual(entries[("PDF fullscreen", "Ctrl+F")], "Open PDF text search.")
            self.assertEqual(
                entries[("PDF fullscreen search", "Enter or Shift+Enter")],
                "Move to the next or previous PDF search match.",
            )
            self.assertEqual(
                entries[("PDF fullscreen", "Ctrl+Plus or Ctrl+Minus")],
                "Zoom the PDF in or out.",
            )
            self.assertEqual(entries[("PDF fullscreen", "Ctrl+0")], "Reset the PDF to actual size.")
            self.assertEqual(
                entries[("PDF fullscreen", "R or Shift+R")],
                "Rotate the PDF clockwise or counter-clockwise.",
            )
            self.assertEqual(
                entries[("Port drag", "Release on empty canvas")],
                "Open connection quick insert for compatible nodes.",
            )
            self.assertEqual(entries[("Video fullscreen", "Space")], "Play or pause the video.")
            for input_name in ("Space", "Left or Right", "Home", "R"):
                with self.subTest(context="Viewer fullscreen", input=input_name):
                    self.assertIn(("Viewer fullscreen", input_name), entries)
        finally:
            dialog.close()

    def test_keyboard_mouse_reference_dialog_filters_by_context_and_action(self) -> None:
        dialog = InputReferenceDialog(parent=self.window)
        try:
            all_rows = _input_reference_visible_rows(dialog)
            self.assertGreaterEqual(len(all_rows), 100)
            context_options = {
                dialog.context_filter_combo.itemText(index)
                for index in range(dialog.context_filter_combo.count())
            }
            action_options = {
                dialog.action_filter_combo.itemText(index)
                for index in range(dialog.action_filter_combo.count())
            }
            self.assertIn("Video fullscreen", context_options)
            self.assertIn("Seek backward or forward ten seconds.", action_options)

            dialog.context_filter_combo.setEditText("Video fullscreen")
            self.app.processEvents()

            context_rows = _input_reference_visible_rows(dialog)
            self.assertGreater(len(context_rows), 1)
            self.assertEqual({context for context, _input, _action in context_rows}, {"Video fullscreen"})

            dialog.action_filter_combo.setEditText("seek")
            self.app.processEvents()

            self.assertEqual(
                _input_reference_visible_rows(dialog),
                [("Video fullscreen", "Left or Right", "Seek backward or forward ten seconds.")],
            )

            dialog.clear_filters()
            self.app.processEvents()
            self.assertEqual(len(_input_reference_visible_rows(dialog)), len(all_rows))

            dialog.action_filter_combo.setEditText("optional")
            self.app.processEvents()
            self.assertIn(
                (
                    "Viewport",
                    "Middle+right click",
                    "Toggle unused optional data ports for the active view.",
                ),
                _input_reference_visible_rows(dialog),
            )
        finally:
            dialog.close()

    def test_menu_bar_exposes_top_level_addon_manager_entry_before_settings(self) -> None:
        top_level_entries = [
            action.text()
            for action in self.window.menuBar().actions()
            if not action.isSeparator()
        ]

        self.assertEqual(
            top_level_entries,
            ["&File", "&Edit", "&View", "&Run", "&Workspace", "Add-On Manager", "&Settings", "&Help"],
        )
        self.assertIs(self.window.menuBar().actions()[5], self.window.action_addon_manager)
        self.assertIsNone(self.window.action_addon_manager.menu())

    def test_view_menu_exposes_port_labels_and_tooltip_toggles(self) -> None:
        menu_actions = {
            action.text(): action.menu()
            for action in self.window.menuBar().actions()
            if action.menu() is not None
        }

        view_entries = [
            action.text()
            for action in menu_actions["&View"].actions()
            if not action.isSeparator()
        ]
        self.assertEqual(
            view_entries,
            [
                "Node Browser",
                "Script Editor",
                "Port Labels",
                "General Help Tooltips",
                "Frame All",
                "Frame Selection",
                "Center Selection",
                "Scope Parent",
                "Scope Root",
            ],
        )
        self.assertTrue(self.window.action_show_port_labels.isCheckable())
        self.assertTrue(self.window.action_show_port_labels.isChecked())
        self.assertTrue(self.window.action_general_help_tooltips.isCheckable())
        self.assertTrue(self.window.action_general_help_tooltips.isChecked())

    def test_addon_manager_action_updates_request_state_and_variant4_surface_focus(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        initial_serial = int(self.window.addon_manager_request_serial)
        self.assertIsNotNone(root_object)
        if root_object is None:
            self.fail("Expected the shell root object to be available.")

        loader = root_object.findChild(QObject, "addonManagerPaneLoader")
        surface = root_object.findChild(QObject, "addonManagerPane")
        scrim = root_object.findChild(QObject, "addonManagerScrim")
        workspace_row = root_object.findChild(QObject, "shellWorkspaceRow")
        controller = root_object.findChild(QObject, "shellAddOnManagerBridge")
        detail_title = root_object.findChild(QObject, "addonManagerDetailTitle")
        self.assertIsNotNone(loader)
        self.assertIsNone(surface)
        self.assertIsNotNone(scrim)
        self.assertIsNotNone(workspace_row)
        self.assertIsNone(controller)
        self.assertIsNone(detail_title)

        self.assertFalse(self.window.addon_manager_open)
        self.assertEqual(self.window.addon_manager_focus_addon_id, "")
        self.assertEqual(self.window.addon_manager_request_serial, initial_serial)
        self.assertTrue(bool(workspace_row.property("visible")))

        self.window.action_addon_manager.trigger()
        self.app.processEvents()

        surface = root_object.findChild(QObject, "addonManagerPane")
        controller = root_object.findChild(QObject, "shellAddOnManagerBridge")
        detail_title = root_object.findChild(QObject, "addonManagerDetailTitle")
        self.assertIsNotNone(surface)
        self.assertIsNotNone(controller)
        self.assertIsNotNone(detail_title)
        self.assertIsInstance(controller, ShellAddOnManagerBridge)
        if surface is None or controller is None or detail_title is None:
            self.fail("Expected the loaded Add-On Manager surface to exist.")

        self.assertTrue(self.window.addon_manager_open)
        self.assertEqual(self.window.addon_manager_focus_addon_id, "")
        self.assertEqual(self.window.addon_manager_request_serial, initial_serial + 1)
        self.assertEqual(
            self.window.addon_manager_request,
            {"open": True, "focus_addon_id": "", "request_serial": initial_serial + 1},
        )
        self.assertTrue(bool(surface.property("visible")))
        self.assertTrue(bool(surface.property("activeFocus")))
        self.assertTrue(bool(scrim.property("visible")))
        self.assertGreater(float(surface.property("height")), 0.0)
        self.assertGreater(float(scrim.property("height")), 0.0)
        self.assertTrue(bool(workspace_row.property("visible")))
        self.assertGreaterEqual(controller.rowCount, 1)
        self.assertEqual(controller.selectedAddonId, "mars.corex")

        self.window.request_open_addon_manager("ea_node_editor.builtins.tabular_data")
        self.app.processEvents()

        self.assertTrue(self.window.addon_manager_open)
        self.assertEqual(self.window.addon_manager_focus_addon_id, "ea_node_editor.builtins.tabular_data")
        self.assertEqual(self.window.addon_manager_request_serial, initial_serial + 2)
        self.assertEqual(
            self.window.addon_manager_request,
            {"open": True, "focus_addon_id": "ea_node_editor.builtins.tabular_data", "request_serial": initial_serial + 2},
        )
        self.assertEqual(controller.selectedAddonId, "ea_node_editor.builtins.tabular_data")
        self.assertEqual(str(detail_title.property("text")), "Tabular Data")
        self.assertTrue(bool(workspace_row.property("visible")))

        self.window.request_close_addon_manager()
        self.app.processEvents()

        self.assertFalse(self.window.addon_manager_open)
        self.assertEqual(self.window.addon_manager_focus_addon_id, "")
        self.assertEqual(self.window.addon_manager_request_serial, initial_serial + 2)
        self.assertEqual(
            self.window.addon_manager_request,
            {"open": False, "focus_addon_id": "", "request_serial": initial_serial + 2},
        )
        self.assertFalse(bool(surface.property("visible")))
        self.assertFalse(bool(scrim.property("visible")))
        self.assertTrue(bool(workspace_row.property("visible")))
        self.assertIs(root_object.findChild(QObject, "addonManagerPane"), surface)

        self.window.request_open_addon_manager()
        self.app.processEvents()

        self.assertIs(root_object.findChild(QObject, "addonManagerPane"), surface)
        self.assertTrue(bool(surface.property("visible")))
        self.window.request_close_addon_manager()
        self.app.processEvents()

    def test_graphics_settings_properties_are_exposed_to_qml(self) -> None:
        meta = self.window.metaObject()
        self.assertGreaterEqual(meta.indexOfProperty("graphics_show_grid"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_grid_style"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_edge_crossing_style"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_show_minimap"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_show_canvas_options_button"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_notched_ports"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_node_elapsed_time_unit"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_minimap_expanded"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_show_tooltips"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_tooltip_categories"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_tooltip_category_visibility"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_status_bar_layout"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_show_fps_telemetry"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_selection_toolbar_mode"), 0)
        self.assertGreaterEqual(
            meta.indexOfProperty("graphics_selection_toolbar_minimal_menu_trigger"),
            0,
        )
        self.assertGreaterEqual(meta.indexOfProperty("graphics_folder_explorer_column_widths"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("graphics_tab_strip_density"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("active_theme_id"), 0)
        self.assertGreaterEqual(meta.indexOfProperty("snap_to_grid_enabled"), 0)
        self.assertTrue(self.window.graphics_show_grid)
        self.assertEqual(self.window.graphics_grid_style, "lines")
        self.assertEqual(self.window.graphics_edge_crossing_style, "none")
        self.assertTrue(self.window.graphics_show_minimap)
        self.assertTrue(self.window.graphics_show_canvas_options_button)
        self.assertTrue(self.window.graphics_notched_ports)
        self.assertEqual(self.window.graphics_node_elapsed_time_unit, "seconds")
        self.assertTrue(self.window.graphics_minimap_expanded)
        self.assertTrue(self.window.graphics_show_tooltips)
        self.assertEqual(
            self.window.graphics_tooltip_category_visibility,
            {
                "general": True,
                "tutorial": True,
                "advanced": False,
                "warning": True,
                "inactive": True,
                "critical": True,
            },
        )
        self.assertTrue(self.window.tooltip_category_enabled("critical"))
        self.assertFalse(self.window.tooltip_category_enabled("unknown"))
        self.assertEqual(self.window.graphics_status_bar_layout, "option_1")
        self.assertTrue(self.window.graphics_show_fps_telemetry)
        self.assertEqual(self.window.graphics_selection_toolbar_mode, "minimal_ghost_menu")
        self.assertEqual(
            self.window.graphics_selection_toolbar_minimal_menu_trigger,
            "click_affordance",
        )
        self.assertEqual(self.window.graphics_folder_explorer_column_widths, {})
        self.assertEqual(self.window.graphics_tab_strip_density, "compact")
        self.assertEqual(self.window.active_theme_id, "stitch_dark")
        self.assertFalse(self.window.snap_to_grid_enabled)

    def test_graphics_settings_dialog_and_view_toggle_share_port_label_preference(self) -> None:
        self.assertTrue(self.window.graphics_show_port_labels)
        self.assertTrue(self.window.action_show_port_labels.isChecked())

        self.window.action_show_port_labels.trigger()
        self.app.processEvents()

        self.assertFalse(self.window.graphics_show_port_labels)
        self.assertFalse(self.window.action_show_port_labels.isChecked())
        persisted = json.loads(self._app_preferences_path.read_text(encoding="utf-8"))
        self.assertFalse(persisted["graphics"]["canvas"]["show_port_labels"])

        captured_initial_settings: list[dict[str, object]] = []

        class RejectingDialog:
            class DialogCode:
                Rejected = 0
                Accepted = 1

            def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
                captured_initial_settings.append(copy.deepcopy(kwargs["initial_settings"]))

            def exec(self) -> int:
                return self.DialogCode.Rejected

        with _patched_graphics_settings_dialog(RejectingDialog):
            self.window.show_graphics_settings_dialog()

        self.assertEqual(len(captured_initial_settings), 1)
        self.assertFalse(captured_initial_settings[0]["canvas"]["show_port_labels"])
        self.assertFalse(self.window.action_show_port_labels.isChecked())

        accepted_values = self.window.app_preferences_controller.graphics_settings()
        accepted_values["canvas"]["show_port_labels"] = True

        class AcceptingDialog(RejectingDialog):
            def exec(self) -> int:
                return self.DialogCode.Accepted

            def values(self) -> dict[str, object]:
                return copy.deepcopy(accepted_values)

        with _patched_graphics_settings_dialog(AcceptingDialog):
            self.window.show_graphics_settings_dialog()
            self.app.processEvents()

        self.assertTrue(self.window.graphics_show_port_labels)
        self.assertTrue(self.window.action_show_port_labels.isChecked())
        persisted = json.loads(self._app_preferences_path.read_text(encoding="utf-8"))
        self.assertTrue(persisted["graphics"]["canvas"]["show_port_labels"])

    def test_selected_run_settings_dialog_persists_preview_preference(self) -> None:
        captured_initial_settings: list[dict[str, object]] = []

        class AcceptingDialog:
            class DialogCode:
                Rejected = 0
                Accepted = 1

            def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
                captured_initial_settings.append(copy.deepcopy(kwargs["initial_settings"]))

            def exec(self) -> int:
                return self.DialogCode.Accepted

            def selected_run_preview_before_run(self) -> bool:
                return False

        self.assertTrue(
            self.window.app_preferences_controller.selected_run_preview_before_run()
        )
        with _patched_selected_run_settings_dialog(AcceptingDialog):
            self.window.show_selected_run_settings_dialog()
            self.app.processEvents()

        self.assertEqual(captured_initial_settings, [{"preview_before_run": True}])
        self.assertFalse(
            self.window.app_preferences_controller.selected_run_preview_before_run()
        )
        persisted = json.loads(self._app_preferences_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["selected_run"], {"preview_before_run": False})

    def test_view_tooltip_toggle_persists_shell_preference_and_recent_project_action_tooltips(self) -> None:
        alpha_path = Path(self._temp_dir.name) / "projects" / "alpha_project.cxproj"
        alpha_path.parent.mkdir(parents=True, exist_ok=True)

        self.window.project_path = str(alpha_path)
        self.window._save_project()
        self.window._refresh_recent_projects_menu()
        self.app.processEvents()

        recent_actions = [action for action in self.window.menu_recent_projects.actions() if not action.isSeparator()]
        self.assertEqual(recent_actions[0].toolTip(), str(alpha_path))
        self.assertTrue(self.window.graphics_show_tooltips)
        self.assertTrue(self.window.action_general_help_tooltips.isChecked())

        self.window.action_general_help_tooltips.trigger()
        self.app.processEvents()

        recent_actions = [action for action in self.window.menu_recent_projects.actions() if not action.isSeparator()]
        self.assertFalse(self.window.graphics_show_tooltips)
        self.assertFalse(self.window.tooltip_category_enabled("general"))
        self.assertTrue(self.window.tooltip_category_enabled("warning"))
        self.assertTrue(self.window.tooltip_category_enabled("critical"))
        self.assertFalse(self.window.action_general_help_tooltips.isChecked())
        self.assertEqual(recent_actions[0].toolTip().strip(), "")
        persisted = json.loads(self._app_preferences_path.read_text(encoding="utf-8"))
        self.assertNotIn("show_tooltips", persisted["graphics"]["shell"])
        self.assertEqual(
            persisted["graphics"]["shell"]["tooltip_categories"],
            {
                "general": False,
                "tutorial": True,
                "advanced": False,
                "warning": True,
                "inactive": True,
            },
        )

        self._reopen_window()
        self.window._refresh_recent_projects_menu()
        restored_actions = [action for action in self.window.menu_recent_projects.actions() if not action.isSeparator()]
        self.assertFalse(self.window.graphics_show_tooltips)
        self.assertFalse(self.window.action_general_help_tooltips.isChecked())
        self.assertEqual(restored_actions[0].toolTip().strip(), "")

    def test_graphics_settings_dialog_persists_tooltip_categories_through_shell_window(self) -> None:
        captured_initial_settings: list[dict[str, object]] = []
        accepted_values = self.window.app_preferences_controller.graphics_settings()
        accepted_categories = {
            "general": False,
            "tutorial": True,
            "advanced": True,
            "warning": False,
            "inactive": True,
        }
        accepted_values["shell"]["tooltip_categories"] = copy.deepcopy(accepted_categories)

        class AcceptingDialog:
            class DialogCode:
                Rejected = 0
                Accepted = 1

            def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
                captured_initial_settings.append(copy.deepcopy(kwargs["initial_settings"]))

            def exec(self) -> int:
                return self.DialogCode.Accepted

            def values(self) -> dict[str, object]:
                return copy.deepcopy(accepted_values)

        with _patched_graphics_settings_dialog(AcceptingDialog):
            self.window.show_graphics_settings_dialog()
            self.app.processEvents()

        self.assertEqual(len(captured_initial_settings), 1)
        self.assertNotIn("show_tooltips", captured_initial_settings[0]["shell"])
        self.assertEqual(
            captured_initial_settings[0]["shell"]["tooltip_categories"],
            {
                "general": True,
                "tutorial": True,
                "advanced": False,
                "warning": True,
                "inactive": True,
            },
        )
        self.assertFalse(self.window.graphics_show_tooltips)
        self.assertFalse(self.window.action_general_help_tooltips.isChecked())
        self.assertEqual(self.window.graphics_tooltip_categories, accepted_categories)
        self.assertFalse(self.window.tooltip_category_enabled("general"))
        self.assertTrue(self.window.tooltip_category_enabled("advanced"))
        self.assertFalse(self.window.tooltip_category_enabled("warning"))
        self.assertTrue(self.window.tooltip_category_enabled("inactive"))
        self.assertTrue(self.window.tooltip_category_enabled("critical"))

        persisted = json.loads(self._app_preferences_path.read_text(encoding="utf-8"))
        self.assertNotIn("show_tooltips", persisted["graphics"]["shell"])
        self.assertEqual(persisted["graphics"]["shell"]["tooltip_categories"], accepted_categories)

        self._reopen_window()
        self.assertFalse(self.window.graphics_show_tooltips)
        self.assertFalse(self.window.action_general_help_tooltips.isChecked())
        self.assertEqual(self.window.graphics_tooltip_categories, accepted_categories)

    def test_graphics_settings_dialog_persists_edge_crossing_style_through_shell_window(self) -> None:
        captured_initial_settings: list[dict[str, object]] = []
        accepted_values = self.window.app_preferences_controller.graphics_settings()
        accepted_values["canvas"]["edge_crossing_style"] = "gap_break"

        class AcceptingDialog:
            class DialogCode:
                Rejected = 0
                Accepted = 1

            def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
                captured_initial_settings.append(copy.deepcopy(kwargs["initial_settings"]))

            def exec(self) -> int:
                return self.DialogCode.Accepted

            def values(self) -> dict[str, object]:
                return copy.deepcopy(accepted_values)

        with _patched_graphics_settings_dialog(AcceptingDialog):
            self.window.show_graphics_settings_dialog()
            self.app.processEvents()

        graph_canvas = self._graph_canvas_item()
        edge_layer = graph_canvas.findChild(QObject, "graphCanvasEdgeLayer")

        self.assertEqual(len(captured_initial_settings), 1)
        self.assertEqual(captured_initial_settings[0]["canvas"]["edge_crossing_style"], "none")
        self.assertIsNotNone(edge_layer)
        self.assertEqual(self.window.graphics_edge_crossing_style, "gap_break")
        self.assertEqual(str(graph_canvas.property("edgeCrossingStyle")), "gap_break")
        self.assertEqual(str(edge_layer.property("edgeCrossingStyle")), "gap_break")
        persisted = json.loads(self._app_preferences_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["graphics"]["canvas"]["edge_crossing_style"], "gap_break")

    def test_graph_typography_dialog_persists_graph_label_pixel_size_through_shell_window(self) -> None:
        graph_canvas = self._graph_canvas_item()
        self.window.scene.add_node_from_type("core.logger", x=180.0, y=120.0)
        self.app.processEvents()

        node_cards = _named_child_items(graph_canvas, "graphNodeCard")
        self.assertGreaterEqual(len(node_cards), 1)
        node_card = node_cards[0]
        title = node_card.findChild(QObject, "graphNodeTitle")
        typography = node_card.findChild(QObject, "graphSharedTypography")
        self.assertIsNotNone(title)
        self.assertIsNotNone(typography)
        if title is None or typography is None:
            self.fail("Expected graph node typography items to exist on the graph canvas.")

        self.assertEqual(self.window.graphics_graph_label_pixel_size, 10)
        self.assertEqual(int(typography.property("graphLabelPixelSize")), 10)
        self.assertEqual(title.property("font").pixelSize(), 12)

        captured_initial_settings: list[dict[str, object]] = []
        accepted_values = self.window.app_preferences_controller.graphics_settings()
        accepted_values["typography"]["graph_label_pixel_size"] = 16

        class AcceptingDialog:
            class DialogCode:
                Rejected = 0
                Accepted = 1

            def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
                captured_initial_settings.append(copy.deepcopy(kwargs["initial_settings"]))

            def exec(self) -> int:
                return self.DialogCode.Accepted

            def values(self) -> dict[str, object]:
                return copy.deepcopy(accepted_values)

        with _patched_graphics_settings_dialog(AcceptingDialog):
            self.window.show_graphics_settings_dialog()
            self.app.processEvents()

        updated_title: QObject | None = None
        updated_typography: QObject | None = None

        def _typography_updated() -> bool:
            nonlocal updated_title, updated_typography
            for updated_node_card in _named_child_items(graph_canvas, "graphNodeCard"):
                candidate_title = updated_node_card.findChild(QObject, "graphNodeTitle")
                candidate_typography = updated_node_card.findChild(QObject, "graphSharedTypography")
                if candidate_title is None or candidate_typography is None:
                    continue
                if int(candidate_typography.property("graphLabelPixelSize")) != 16:
                    continue
                if candidate_title.property("font").pixelSize() != 18:
                    continue
                updated_title = candidate_title
                updated_typography = candidate_typography
                return True
            return False

        wait_for_condition_or_raise(
            _typography_updated,
            app=self.app,
            timeout_message="Expected graph typography bindings to refresh after accepting graphics settings.",
        )
        self.assertIsNotNone(updated_title)
        self.assertIsNotNone(updated_typography)
        if updated_title is None or updated_typography is None:
            self.fail("Expected refreshed graph typography items after accepting graphics settings.")

        self.assertEqual(len(captured_initial_settings), 1)
        self.assertEqual(captured_initial_settings[0]["typography"]["graph_label_pixel_size"], 10)
        self.assertEqual(self.window.graphics_graph_label_pixel_size, 16)
        self.assertEqual(
            self.window.app_preferences_controller.graphics_settings()["typography"]["graph_label_pixel_size"],
            16,
        )
        self.assertEqual(int(updated_typography.property("graphLabelPixelSize")), 16)
        self.assertEqual(int(updated_typography.property("nodeTitlePixelSize")), 18)
        self.assertEqual(updated_title.property("font").pixelSize(), 18)
        persisted = json.loads(self._app_preferences_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["graphics"]["typography"]["graph_label_pixel_size"], 16)

    def test_graph_label_pixel_size_preference_change_rebuilds_active_scene_payload(self) -> None:
        events = _capture_graphics_fanout(self.window)

        self.window.app_preferences_controller.update_graphics_settings(
            {"typography": {"graph_label_pixel_size": 16}},
            host=self.window,
        )
        self.app.processEvents()
        self.assertEqual(events, {"host": 1, "workspace": 1, "state": 1, "nodes": 1, "edges": 1})

        self.window.app_preferences_controller.update_graphics_settings(
            {"typography": {"graph_label_pixel_size": 10}},
            host=self.window,
        )
        self.app.processEvents()
        self.assertEqual(events, {"host": 2, "workspace": 2, "state": 2, "nodes": 2, "edges": 2})

    def test_graph_typography_preference_change_rebuilds_standard_node_widths_without_manual_scene_refresh(
        self,
    ) -> None:
        graph_canvas = self._graph_canvas_item()
        node_id = self.window.scene.add_node_from_type("core.python_script", x=180.0, y=120.0)
        self.window.scene.set_node_title(
            node_id,
            "Logger With An Extremely Long Title For Typography Growth",
        )
        self.window.scene.set_node_port_label(
            node_id,
            "payload",
            "Primary Input Payload With A Very Long Label To Force Reflow",
        )
        self.window.scene.set_node_port_label(
            node_id,
            "result",
            "Dispatch Result Token With Additional Details",
        )
        self.app.processEvents()

        node_cards = _named_child_items(graph_canvas, "graphNodeCard")
        self.assertGreaterEqual(len(node_cards), 1)
        baseline_node_card = node_cards[0]
        baseline_payload = next(item for item in self.window.scene.nodes_model if item["node_id"] == node_id)
        baseline_width = float(baseline_node_card.property("width"))
        baseline_payload_width = float(baseline_payload["width"])
        baseline_metric_width = float(baseline_payload["surface_metrics"]["standard_port_label_min_width"])

        self.window.app_preferences_controller.update_graphics_settings(
            {"typography": {"graph_label_pixel_size": 16}},
            host=self.window,
        )
        self.app.processEvents()

        updated_node_cards = _named_child_items(graph_canvas, "graphNodeCard")
        self.assertGreaterEqual(len(updated_node_cards), 1)
        updated_node_card = updated_node_cards[0]
        updated_payload = next(item for item in self.window.scene.nodes_model if item["node_id"] == node_id)
        updated_width = float(updated_node_card.property("width"))
        updated_payload_width = float(updated_payload["width"])
        updated_metric_width = float(updated_payload["surface_metrics"]["standard_port_label_min_width"])

        self.assertGreater(updated_width, baseline_width)
        self.assertGreater(updated_payload_width, baseline_payload_width)
        self.assertGreater(updated_metric_width, baseline_metric_width)
        self.assertAlmostEqual(updated_width, updated_payload_width, places=6)

    def test_port_labels_setting_persists_across_window_restart(self) -> None:
        self.assertTrue(self.window.graphics_show_port_labels)
        self.assertTrue(self.window.action_show_port_labels.isChecked())

        self.window.action_show_port_labels.trigger()
        self.app.processEvents()

        self.assertFalse(self.window.graphics_show_port_labels)
        self.assertFalse(self.window.action_show_port_labels.isChecked())
        persisted = json.loads(self._app_preferences_path.read_text(encoding="utf-8"))
        self.assertFalse(persisted["graphics"]["canvas"]["show_port_labels"])

        self._reopen_window()

        self.assertFalse(self.window.graphics_show_port_labels)
        self.assertFalse(self.window.action_show_port_labels.isChecked())

    def test_port_label_preference_change_rebuilds_active_scene_payload(self) -> None:
        events = _capture_graphics_fanout(self.window)

        self.window.action_show_port_labels.trigger()
        self.app.processEvents()
        self.assertEqual(events, {"host": 1, "workspace": 1, "state": 1, "nodes": 1, "edges": 1})

        self.window.app_preferences_controller.set_graphics_settings(
            {
                "canvas": {
                    "show_grid": True,
                    "show_minimap": True,
                    "show_port_labels": True,
                    "minimap_expanded": True,
                },
                "interaction": {
                    "snap_to_grid": False,
                },
                "theme": {
                    "theme_id": "stitch_dark",
                },
            },
            host=self.window,
        )
        self.app.processEvents()
        self.assertEqual(events, {"host": 2, "workspace": 2, "state": 2, "nodes": 2, "edges": 2})

    def test_qml_shell_and_bridges_are_present(self) -> None:
        self.assertIsNotNone(self.window.quick_widget)
        self.assertIs(self.window.centralWidget(), self.window.quick_widget)
        self.assertIsNotNone(self.window.quick_widget.rootObject())
        self.assertIsNotNone(self.window.scene)
        self.assertIsNotNone(self.window.view)
        self.assertGreaterEqual(self.window.workspace_tabs.count(), 1)

    def test_qml_shell_surfaces_start_on_active_theme_palette(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        library_pane = root_object.findChild(QObject, "libraryPane")
        quick_insert_overlay = root_object.findChild(QObject, "connectionQuickInsertOverlay")
        node_browser_overlay = root_object.findChild(QObject, "nodeBrowserOverlay")
        node_browser_panel = root_object.findChild(QObject, "nodeBrowserPanel")
        graph_hint_overlay = root_object.findChild(QObject, "graphHintOverlay")
        self.assertIsNotNone(library_pane)
        self.assertIsNotNone(quick_insert_overlay)
        self.assertIsNotNone(node_browser_overlay)
        self.assertIsNotNone(node_browser_panel)
        self.assertIsNotNone(graph_hint_overlay)

        palette = self.window.theme_bridge.palette
        self.assertEqual(_color_name(root_object.property("color")), palette["app_bg"])
        self.assertEqual(_color_name(library_pane.property("color")), palette["panel_alt_bg"])
        self.assertEqual(_color_name(quick_insert_overlay.property("color")), palette["panel_alt_bg"])
        self.assertEqual(
            _color_name(graph_hint_overlay.property("color"), include_alpha=True),
            _alpha_color_name(palette["panel_bg"], 0.8),
        )

    def test_node_browser_filters_and_inserts_selected_node_with_keyboard(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        overlay = root_object.findChild(QObject, "nodeBrowserOverlay")
        search_field = root_object.findChild(QObject, "nodeBrowserSearchField")
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        before_node_ids = set(workspace.nodes)

        self.window.shell_library_bridge.request_open_node_browser()
        self.app.processEvents()
        overlay.setProperty("queryText", "core.logger")
        overlay.setProperty("sceneAnchorActive", True)
        overlay.setProperty("sceneAnchorX", 312.0)
        overlay.setProperty("sceneAnchorY", 184.0)
        self.app.processEvents()

        filtered_items = overlay.property("filteredItems")
        if isinstance(filtered_items, QJSValue):
            filtered_items = filtered_items.toVariant()
        self.assertEqual([item["type_id"] for item in filtered_items], ["core.logger"])
        self.assertTrue(bool(search_field.property("activeFocus")))

        QTest.keyClick(self.window.quick_widget, Qt.Key.Key_Return)
        self.app.processEvents()

        self.assertFalse(bool(overlay.property("visible")))
        created_node_ids = set(workspace.nodes) - before_node_ids
        self.assertEqual(len(created_node_ids), 1)
        created = workspace.nodes[next(iter(created_node_ids))]
        self.assertEqual(created.type_id, "core.logger")
        self.assertAlmostEqual(created.x, 312.0)
        self.assertAlmostEqual(created.y, 184.0)

    def test_node_browser_slider_expression_inserts_preconfigured_number_slider(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        overlay = root_object.findChild(QObject, "nodeBrowserOverlay")
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        before_node_ids = set(workspace.nodes)

        self.window.shell_library_bridge.request_open_node_browser()
        self.app.processEvents()
        overlay.setProperty("queryText", "0<5<10")
        overlay.setProperty("sceneAnchorActive", True)
        overlay.setProperty("sceneAnchorX", 320.0)
        overlay.setProperty("sceneAnchorY", 200.0)
        self.app.processEvents()

        filtered_items = overlay.property("filteredItems")
        if isinstance(filtered_items, QJSValue):
            filtered_items = filtered_items.toVariant()
        self.assertTrue(filtered_items)
        first = filtered_items[0]
        self.assertEqual(first["type_id"], "data.number_slider")
        self.assertIn("0 < 5 < 10", first["display_name"])
        self.assertEqual(first["smart_insert_properties"]["rounding"], "integer")
        self.assertEqual(float(first["smart_insert_properties"]["value"]), 5.0)
        self.assertEqual(int(overlay.property("selectedIndex")), 0)

        QTest.keyClick(self.window.quick_widget, Qt.Key.Key_Return)
        self.app.processEvents()

        self.assertFalse(bool(overlay.property("visible")))
        created_node_ids = set(workspace.nodes) - before_node_ids
        self.assertEqual(len(created_node_ids), 1)
        created = workspace.nodes[next(iter(created_node_ids))]
        self.assertEqual(created.type_id, "data.number_slider")
        self.assertAlmostEqual(created.x, 320.0)
        self.assertAlmostEqual(created.y, 200.0)
        self.assertEqual(created.properties["minimum"], 0.0)
        self.assertEqual(created.properties["value"], 5.0)
        self.assertEqual(created.properties["maximum"], 10.0)
        self.assertEqual(created.properties["rounding"], "integer")

        self.window.shell_library_bridge.request_open_node_browser()
        self.app.processEvents()
        overlay.setProperty("queryText", "number slider")
        self.app.processEvents()
        keyword_items = overlay.property("filteredItems")
        if isinstance(keyword_items, QJSValue):
            keyword_items = keyword_items.toVariant()
        self.assertIn("data.number_slider", [item["type_id"] for item in keyword_items])
        QTest.keyClick(self.window.quick_widget, Qt.Key.Key_Escape)
        self.app.processEvents()

    def test_node_browser_boolean_literals_insert_preconfigured_toggle(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        overlay = root_object.findChild(QObject, "nodeBrowserOverlay")
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]

        for query, expected in (("true", True), ("false", False)):
            before_node_ids = set(workspace.nodes)
            self.window.shell_library_bridge.request_open_node_browser()
            self.app.processEvents()
            overlay.setProperty("queryText", query)
            overlay.setProperty("sceneAnchorActive", True)
            overlay.setProperty("sceneAnchorX", 320.0)
            overlay.setProperty("sceneAnchorY", 200.0)
            self.app.processEvents()

            filtered_items = overlay.property("filteredItems")
            if isinstance(filtered_items, QJSValue):
                filtered_items = filtered_items.toVariant()
            self.assertTrue(filtered_items)
            self.assertEqual(filtered_items[0]["type_id"], "data.boolean_toggle")
            self.assertEqual(filtered_items[0]["smart_insert_properties"], {"value": expected})
            self.assertEqual(
                [item["type_id"] for item in filtered_items].count("data.boolean_toggle"),
                1,
            )

            QTest.keyClick(self.window.quick_widget, Qt.Key.Key_Return)
            self.app.processEvents()

            created_node_ids = set(workspace.nodes) - before_node_ids
            self.assertEqual(len(created_node_ids), 1)
            created = workspace.nodes[next(iter(created_node_ids))]
            self.assertEqual(created.type_id, "data.boolean_toggle")
            self.assertIs(created.properties["value"], expected)

    def test_node_browser_panel_shortcuts_promote_and_author_panel(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        overlay = root_object.findChild(QObject, "nodeBrowserOverlay")
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]

        for alias in ("number", "expression"):
            self.window.shell_library_bridge.request_open_node_browser()
            self.app.processEvents()
            overlay.setProperty("queryText", alias)
            self.app.processEvents()
            filtered_items = overlay.property("filteredItems")
            if isinstance(filtered_items, QJSValue):
                filtered_items = filtered_items.toVariant()
            self.assertTrue(filtered_items)
            self.assertEqual(filtered_items[0]["type_id"], "data.panel")
            QTest.keyClick(self.window.quick_widget, Qt.Key.Key_Escape)
            self.app.processEvents()

        before_node_ids = set(workspace.nodes)
        self.window.shell_library_bridge.request_open_node_browser()
        self.app.processEvents()
        overlay.setProperty("queryText", '"faithful text')
        overlay.setProperty("sceneAnchorActive", True)
        overlay.setProperty("sceneAnchorX", 320.0)
        overlay.setProperty("sceneAnchorY", 200.0)
        self.app.processEvents()

        filtered_items = overlay.property("filteredItems")
        if isinstance(filtered_items, QJSValue):
            filtered_items = filtered_items.toVariant()
        self.assertTrue(filtered_items)
        self.assertEqual(filtered_items[0]["type_id"], "data.panel")
        self.assertEqual(
            filtered_items[0]["smart_insert_properties"],
            {"value": "faithful text", "mode": 0},
        )

        QTest.keyClick(self.window.quick_widget, Qt.Key.Key_Return)
        self.app.processEvents()
        created_node_ids = set(workspace.nodes) - before_node_ids
        self.assertEqual(len(created_node_ids), 1)
        created = workspace.nodes[next(iter(created_node_ids))]
        self.assertEqual(created.type_id, "data.panel")
        self.assertEqual(created.properties["value"], "faithful text")
        self.assertEqual(created.properties["mode"], 0)

    def test_node_browser_limits_categories_and_port_search_direction(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        overlay = root_object.findChild(QObject, "nodeBrowserOverlay")

        self.window.shell_library_bridge.request_open_node_browser()
        self.app.processEvents()

        root_categories = overlay.property("rootCategoryOptions")
        if isinstance(root_categories, QJSValue):
            root_categories = root_categories.toVariant()
        self.assertTrue(root_categories)
        self.assertTrue(all(not row.get("value") or row.get("depth", 0) == 0 for row in root_categories))

        grouped_rows = overlay.property("groupedRows")
        if isinstance(grouped_rows, QJSValue):
            grouped_rows = grouped_rows.toVariant()
        self.assertTrue(any(row.get("kind") == "category" for row in grouped_rows))
        self.assertTrue(
            all(len(row.get("indices", [])) <= 2 for row in grouped_rows if row.get("kind") == "nodes")
        )
        initial_results = overlay.property("filteredItems")
        if isinstance(initial_results, QJSValue):
            initial_results = initial_results.toVariant()
        self.assertGreater(len(initial_results), 1)
        QTest.keyClick(self.window.quick_widget, Qt.Key.Key_Down)
        self.app.processEvents()
        selected_item = overlay.property("selectedItem")
        if isinstance(selected_item, QJSValue):
            selected_item = selected_item.toVariant()
        self.assertEqual(int(overlay.property("selectedIndex")), 1)
        self.assertEqual(selected_item["type_id"], initial_results[1]["type_id"])

        overlay.setProperty("queryText", "value")
        overlay.setProperty("directionFilter", "in")
        self.app.processEvents()
        input_results = overlay.property("filteredItems")
        if isinstance(input_results, QJSValue):
            input_results = input_results.toVariant()
        self.assertNotIn("core.constant", [row["type_id"] for row in input_results])

        overlay.setProperty("directionFilter", "out")
        self.app.processEvents()
        output_results = overlay.property("filteredItems")
        if isinstance(output_results, QJSValue):
            output_results = output_results.toVariant()
        self.assertIn("core.constant", [row["type_id"] for row in output_results])

        overlay.setProperty("visible", False)

    def test_node_browser_request_carries_anchor_and_ctrl_b_opens_canvas_quick_insert(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        overlay = root_object.findChild(QObject, "nodeBrowserOverlay")
        quick_insert_overlay = root_object.findChild(QObject, "connectionQuickInsertOverlay")

        self.window.shell_library_bridge.request_open_node_browser("logger", 312.0, 184.0)
        self.app.processEvents()
        self.assertTrue(bool(overlay.property("visible")))
        self.assertEqual(overlay.property("queryText"), "logger")
        self.assertTrue(bool(overlay.property("sceneAnchorActive")))
        self.assertAlmostEqual(float(overlay.property("sceneAnchorX")), 312.0)
        self.assertAlmostEqual(float(overlay.property("sceneAnchorY")), 184.0)
        overlay.setProperty("visible", False)

        self.window.action_node_browser.trigger()
        self.app.processEvents()

        self.assertFalse(bool(overlay.property("visible")))
        self.assertTrue(self.window.connection_quick_insert_open)
        self.assertTrue(self.window.connection_quick_insert_is_canvas_mode)
        self.assertTrue(bool(quick_insert_overlay.property("visible")))
        self.window.request_close_connection_quick_insert()
        self.app.processEvents()
        self.assertFalse(self.window.connection_quick_insert_open)
        self.assertFalse(bool(quick_insert_overlay.property("visible")))

    def test_qml_active_workspace_and_view_tab_labels_use_selected_theme_foreground(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        view_controls_strip = root_object.findChild(QObject, "viewControlsStrip")
        workspace_controls_strip = root_object.findChild(QObject, "workspaceControlsStrip")
        self.assertIsNotNone(view_controls_strip)
        self.assertIsNotNone(workspace_controls_strip)

        palette = self.window.theme_bridge.palette
        for strip in (view_controls_strip, workspace_controls_strip):
            button, label = _active_tab_label(strip)
            self.assertTrue(bool(button.property("active")))
            self.assertEqual(_color_name(label.property("color")), palette["tab_selected_fg"])
            self.assertTrue(label.property("font").bold())

    def test_qml_workspace_tabs_size_each_chip_from_its_own_label(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        workspace_controls_strip = root_object.findChild(QObject, "workspaceControlsStrip")
        self.assertIsNotNone(workspace_controls_strip)

        short_name = "ws2"
        long_name = "Demo 1 - Static Displacement Viewer"
        self.window.workspace_manager.create_workspace(short_name)
        self.window.workspace_manager.create_workspace(long_name)
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.app.processEvents()

        def _has_expected_tab_buttons() -> bool:
            buttons_by_label = _tab_buttons_by_label(workspace_controls_strip)
            return short_name in buttons_by_label and long_name in buttons_by_label

        wait_for_condition_or_raise(
            _has_expected_tab_buttons,
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace tab strip did not expose the expected tab buttons.",
        )

        buttons_by_label = _tab_buttons_by_label(workspace_controls_strip)
        short_width = float(buttons_by_label[short_name].property("width"))
        long_width = float(buttons_by_label[long_name].property("width"))

        self.assertLess(short_width, long_width)

    def test_qml_workspace_tab_renders_full_long_label_without_eliding(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        workspace_controls_strip = root_object.findChild(QObject, "workspaceControlsStrip")
        self.assertIsNotNone(workspace_controls_strip)

        long_name = (
            "Multi-stage Cyclic Symmetric Workspace Results Overview "
            "With Repeated Loading Conditions And Postprocessing Branches "
            "For The Full Assembly Verification Pass"
        )
        workspace_id = self.window.workspace_manager.create_workspace(long_name)
        self.window.workspace_tabs.activate_workspace(workspace_id)
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.app.processEvents()

        def _has_long_tab_label() -> bool:
            return long_name in _tab_button_labels_by_label(workspace_controls_strip)

        wait_for_condition_or_raise(
            _has_long_tab_label,
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace tab strip did not expose the long workspace label.",
        )

        button, label = _tab_button_labels_by_label(workspace_controls_strip)[long_name]

        self.assertFalse(bool(label.property("truncated")))
        self.assertGreaterEqual(
            float(button.property("width")),
            float(label.property("implicitWidth")) + 12.0,
        )

    def test_qml_view_tabs_size_each_chip_from_its_own_label(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        view_controls_strip = root_object.findChild(QObject, "viewControlsStrip")
        self.assertIsNotNone(view_controls_strip)

        short_name = "v2"
        long_name = "Demo 2 - Static Stress Norm Export"
        with patch.object(
            self.window.shell_host_presenter,
            "prompt_text_value",
            side_effect=[(short_name, True), (long_name, True)],
        ):
            self.window.request_create_view()
            self.window.request_create_view()
        self.app.processEvents()

        def _has_expected_tab_buttons() -> bool:
            buttons_by_label = _tab_buttons_by_label(view_controls_strip)
            return short_name in buttons_by_label and long_name in buttons_by_label

        wait_for_condition_or_raise(
            _has_expected_tab_buttons,
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="View tab strip did not expose the expected tab buttons.",
        )

        buttons_by_label = _tab_buttons_by_label(view_controls_strip)
        short_width = float(buttons_by_label[short_name].property("width"))
        long_width = float(buttons_by_label[long_name].property("width"))

        self.assertLess(short_width, long_width)

    def test_qml_workspace_tab_strip_only_shows_overflow_controls_when_needed(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        workspace_controls_strip = root_object.findChild(QObject, "workspaceControlsStrip")
        self.assertIsNotNone(workspace_controls_strip)

        backward_button = _strip_child(workspace_controls_strip, "tabStripScrollBackwardButton")
        forward_button = _strip_child(workspace_controls_strip, "tabStripScrollForwardButton")
        create_button = _strip_child(workspace_controls_strip, "tabStripCreateButton")

        self.assertFalse(bool(workspace_controls_strip.property("tabsOverflowActive")))
        self.assertFalse(bool(backward_button.property("visible")))
        self.assertFalse(bool(forward_button.property("visible")))
        self.assertTrue(bool(create_button.property("visible")))

        for index in range(8):
            self.window.workspace_manager.create_workspace(
                f"Overflow Workspace {index} - Static Displacement Viewer"
            )
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(workspace_controls_strip.property("tabsOverflowActive")),
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace strip did not enter overflow mode.",
        )

        self.assertTrue(bool(backward_button.property("visible")))
        self.assertTrue(bool(forward_button.property("visible")))
        self.assertTrue(bool(create_button.property("visible")))
        self.assertLess(
            float(workspace_controls_strip.property("width")),
            float(workspace_controls_strip.property("implicitWidth")),
        )
        self.assertGreater(float(workspace_controls_strip.property("tabsMaxContentX")), 0.0)

    def test_qml_view_create_button_matches_workspace_create_button_style(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        workspace_controls_strip = root_object.findChild(QObject, "workspaceControlsStrip")
        view_controls_strip = root_object.findChild(QObject, "viewControlsStrip")
        self.assertIsNotNone(workspace_controls_strip)
        self.assertIsNotNone(view_controls_strip)

        workspace_create_button = _strip_child(workspace_controls_strip, "tabStripCreateButton")
        view_create_button = _strip_child(view_controls_strip, "tabStripCreateButton")

        self.assertEqual(
            bool(view_create_button.property("accentOutline")),
            bool(workspace_create_button.property("accentOutline")),
        )

    def test_qml_view_tab_strip_caps_width_and_keeps_create_visible_under_overflow(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        view_controls_strip = root_object.findChild(QObject, "viewControlsStrip")
        self.assertIsNotNone(view_controls_strip)

        create_button = _strip_child(view_controls_strip, "tabStripCreateButton")

        view_names = [
            f"View {index} - Static Stress Norm Export"
            for index in range(2, 10)
        ]
        with patch.object(
            self.window.shell_host_presenter,
            "prompt_text_value",
            side_effect=[(name, True) for name in view_names],
        ):
            for _name in view_names:
                self.window.request_create_view()
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: bool(view_controls_strip.property("tabsOverflowActive")),
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="View strip did not enter overflow mode.",
        )

        self.assertTrue(bool(create_button.property("visible")))
        self.assertLess(
            float(view_controls_strip.property("width")),
            float(view_controls_strip.property("implicitWidth")),
        )
        self.assertGreater(float(view_controls_strip.property("tabsViewportWidth")), 0.0)

    def test_qml_canvas_surfaces_start_on_active_theme_palette(self) -> None:
        graph_canvas = self._graph_canvas_item()
        background = graph_canvas.findChild(QObject, "graphCanvasBackground")
        minimap_overlay = graph_canvas.findChild(QObject, "graphCanvasMinimapOverlay")
        minimap_toggle = graph_canvas.findChild(QObject, "graphCanvasMinimapToggle")
        drop_preview = graph_canvas.findChild(QObject, "graphCanvasDropPreview")
        edge_layer = graph_canvas.findChild(QObject, "graphCanvasEdgeLayer")
        marquee_rect = graph_canvas.findChild(QObject, "graphCanvasMarqueeRect")
        edge_context_popup = graph_canvas.findChild(QObject, "graphCanvasEdgeContextPopup")
        node_context_popup = graph_canvas.findChild(QObject, "graphCanvasNodeContextPopup")

        self.assertIsNotNone(background)
        self.assertIsNotNone(minimap_overlay)
        self.assertIsNotNone(minimap_toggle)
        self.assertIsNotNone(drop_preview)
        self.assertIsNotNone(edge_layer)
        self.assertIsNotNone(marquee_rect)
        self.assertIsNotNone(edge_context_popup)
        self.assertIsNotNone(node_context_popup)

        palette = self.window.theme_bridge.palette
        self.assertEqual(_color_name(background.property("backgroundFillColor")), palette["canvas_bg"])
        self.assertEqual(_color_name(background.property("majorGridColor")), palette["canvas_major_grid"])
        self.assertEqual(
            _color_name(minimap_overlay.property("color"), include_alpha=True),
            _alpha_color_name(palette["panel_bg"], 0.64),
        )
        self.assertEqual(_color_name(minimap_toggle.property("color")), palette["toolbar_bg"])
        self.assertEqual(
            _color_name(drop_preview.property("color"), include_alpha=True),
            _alpha_color_name(palette["panel_bg"], 0.66),
        )
        self.assertEqual(
            _color_name(edge_layer.property("selectedStrokeColor")),
            self.window.graph_theme_bridge.edge_palette["selected_stroke"],
        )
        self.assertEqual(
            _color_name(edge_layer.property("invalidDragStrokeColor")),
            self.window.graph_theme_bridge.edge_palette["invalid_drag_stroke"],
        )
        self.assertEqual(
            _color_name(marquee_rect.property("color"), include_alpha=True),
            _alpha_color_name(palette["accent"], 0.2),
        )
        self.assertEqual(_color_name(edge_context_popup.property("color")), palette["panel_bg"])
        self.assertEqual(_color_name(node_context_popup.property("color")), palette["panel_bg"])

    def test_graph_canvas_keeps_graph_node_card_discoverability_after_host_refactor(self) -> None:
        graph_canvas = self._graph_canvas_item()
        self.window.scene.add_node_from_type("core.logger", 180.0, 120.0)
        self.app.processEvents()

        node_cards = _named_child_items(graph_canvas, "graphNodeCard")
        self.assertGreaterEqual(len(node_cards), 1)
        self.assertIsNotNone(node_cards[0].findChild(QObject, "graphNodeStandardSurface"))

    def test_qml_canvas_runtime_preferences_follow_shell_state(self) -> None:
        graph_canvas = self._graph_canvas_item()
        background = graph_canvas.findChild(QObject, "graphCanvasBackground")
        minimap_overlay = graph_canvas.findChild(QObject, "graphCanvasMinimapOverlay")
        edge_layer = graph_canvas.findChild(QObject, "graphCanvasEdgeLayer")
        self.assertIsNotNone(background)
        self.assertIsNotNone(minimap_overlay)
        self.assertIsNotNone(edge_layer)

        self.assertTrue(bool(graph_canvas.property("showGrid")))
        self.assertEqual(str(graph_canvas.property("gridStyle")), "lines")
        self.assertEqual(str(graph_canvas.property("edgeCrossingStyle")), "none")
        self.assertTrue(bool(background.property("showGrid")))
        self.assertEqual(str(background.property("gridStyle")), "lines")
        self.assertTrue(bool(graph_canvas.property("minimapVisible")))
        self.assertTrue(bool(minimap_overlay.property("visible")))
        self.assertTrue(bool(graph_canvas.property("minimapExpanded")))
        self.assertEqual(str(edge_layer.property("edgeCrossingStyle")), "none")

        self.window.app_preferences_controller.set_graphics_settings(
            {
                "canvas": {
                    "show_grid": False,
                    "grid_style": "points",
                    "edge_crossing_style": "gap_break",
                    "show_minimap": False,
                    "minimap_expanded": False,
                },
                "interaction": {
                    "snap_to_grid": False,
                },
                "theme": {
                    "theme_id": "stitch_dark",
                },
            },
            host=self.window,
        )
        self.app.processEvents()

        self.assertFalse(self.window.graphics_show_grid)
        self.assertEqual(self.window.graphics_grid_style, "points")
        self.assertEqual(self.window.graphics_edge_crossing_style, "gap_break")
        self.assertFalse(self.window.graphics_show_minimap)
        self.assertFalse(self.window.graphics_minimap_expanded)
        self.assertFalse(bool(graph_canvas.property("showGrid")))
        self.assertEqual(str(graph_canvas.property("gridStyle")), "points")
        self.assertEqual(str(graph_canvas.property("edgeCrossingStyle")), "gap_break")
        self.assertFalse(bool(background.property("showGrid")))
        self.assertEqual(str(background.property("gridStyle")), "points")
        self.assertFalse(bool(graph_canvas.property("minimapVisible")))
        self.assertFalse(bool(minimap_overlay.property("visible")))
        self.assertFalse(bool(graph_canvas.property("minimapExpanded")))
        self.assertEqual(str(edge_layer.property("edgeCrossingStyle")), "gap_break")

    def test_qml_tab_strip_density_follows_shell_state(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        view_controls_strip = root_object.findChild(QObject, "viewControlsStrip")
        workspace_controls_strip = root_object.findChild(QObject, "workspaceControlsStrip")
        self.assertIsNotNone(view_controls_strip)
        self.assertIsNotNone(workspace_controls_strip)
        self.assertEqual(view_controls_strip.property("densityPreset"), "compact")
        self.assertEqual(workspace_controls_strip.property("densityPreset"), "compact")

        self.window.app_preferences_controller.set_graphics_settings(
            {
                "canvas": {
                    "show_grid": True,
                    "show_minimap": True,
                    "minimap_expanded": True,
                },
                "interaction": {
                    "snap_to_grid": False,
                },
                "shell": {
                    "tab_strip_density": "regular",
                },
                "theme": {
                    "theme_id": "stitch_dark",
                },
            },
            host=self.window,
        )
        self.app.processEvents()

        self.assertEqual(self.window.graphics_tab_strip_density, "regular")
        self.assertEqual(view_controls_strip.property("densityPreset"), "regular")
        self.assertEqual(workspace_controls_strip.property("densityPreset"), "regular")

    def test_qml_minimap_expansion_persists_across_window_restart(self) -> None:
        graph_canvas = self._graph_canvas_item()
        self.assertTrue(bool(graph_canvas.property("minimapExpanded")))

        QMetaObject.invokeMethod(
            graph_canvas,
            "toggleMinimapExpanded",
            Qt.ConnectionType.DirectConnection,
        )
        self.app.processEvents()

        self.assertFalse(self.window.graphics_minimap_expanded)
        self.assertFalse(bool(graph_canvas.property("minimapExpanded")))
        persisted = json.loads(self._app_preferences_path.read_text(encoding="utf-8"))
        self.assertFalse(persisted["graphics"]["canvas"]["minimap_expanded"])

        self._reopen_window()

        graph_canvas = self._graph_canvas_item()
        self.assertFalse(self.window.graphics_minimap_expanded)
        self.assertFalse(bool(graph_canvas.property("minimapExpanded")))

    def test_graphics_status_bar_layout_persists_across_window_restart(self) -> None:
        self.assertEqual(self.window.graphics_status_bar_layout, "option_1")

        self.window.app_preferences_controller.update_graphics_settings(
            {"shell": {"status_bar_layout": "option_2", "show_fps_telemetry": False}},
            host=self.window,
        )
        self.app.processEvents()

        self.assertEqual(self.window.graphics_status_bar_layout, "option_2")
        self.assertEqual(
            self.window.shell_workspace_presenter.graphics_status_bar_layout,
            "option_2",
        )
        self.assertEqual(self.window.graph_canvas_state_bridge.graphics_status_bar_layout, "option_2")
        self.assertFalse(self.window.graphics_show_fps_telemetry)
        persisted = json.loads(self._app_preferences_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["graphics"]["shell"]["status_bar_layout"], "option_2")
        self.assertFalse(persisted["graphics"]["shell"]["show_fps_telemetry"])

        self._reopen_window()

        self.assertEqual(self.window.graphics_status_bar_layout, "option_2")
        self.assertFalse(self.window.graphics_show_fps_telemetry)

    def test_qml_invokable_slots_exist_for_shell_buttons(self) -> None:
        meta = self.window.metaObject()
        self.assertGreaterEqual(meta.indexOfMethod("show_workflow_settings_dialog()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("show_graphics_settings_dialog()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("show_selected_run_settings_dialog()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("show_keyboard_mouse_reference_dialog()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("set_graphics_minimap_expanded(bool)"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("set_graphics_selection_toolbar_mode(QString)"), 0)
        self.assertGreaterEqual(
            meta.indexOfMethod("set_graphics_selection_toolbar_minimal_menu_trigger(QString)"),
            0,
        )
        self.assertGreaterEqual(meta.indexOfMethod("set_script_editor_panel_visible()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("set_script_editor_panel_visible(bool)"), 0)
        command_meta = self.window.graph_canvas_command_bridge.metaObject()
        self.assertGreaterEqual(
            command_meta.indexOfMethod(
                "request_connect_ports(QString,QString,QString,QString,bool)"
            ),
            0,
        )
        self.assertGreaterEqual(meta.indexOfMethod("request_remove_edge(QString)"), 0)
        self.assertGreaterEqual(
            meta.indexOfMethod(
                "request_rewire_edges(QVariantList,QString,QString,QString,bool,bool)"
            ),
            0,
        )
        self.assertGreaterEqual(meta.indexOfMethod("request_remove_node(QString)"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_rename_node(QString)"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_delete_selected_graph_items(QVariantList)"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_duplicate_selected_nodes()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_group_selected_nodes()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_ungroup_selected_nodes()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_copy_selected_nodes()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_cut_selected_nodes()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_paste_selected_nodes()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_undo()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_redo()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_align_selection_left()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_align_selection_right()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_align_selection_top()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_align_selection_bottom()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_distribute_selection_horizontally()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_distribute_selection_vertically()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_straighten_selection_connections()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_toggle_snap_to_grid()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_open_subnode_scope(QString)"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_open_scope_breadcrumb(QString)"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_navigate_scope_parent()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_navigate_scope_root()"), 0)
        self.assertGreaterEqual(
            command_meta.indexOfMethod(
                "request_drop_node_from_library(QString,double,double,QString,QString,QString,QString)"
            ),
            0,
        )
        self.assertGreaterEqual(meta.indexOfMethod("request_publish_custom_workflow_from_selected()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_publish_custom_workflow_from_scope()"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_rename_custom_workflow_from_library(QString)"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_rename_custom_workflow_from_library(QString,QString)"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_delete_custom_workflow_from_library(QString)"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_delete_custom_workflow_from_library(QString,QString)"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_set_custom_workflow_scope(QString,QString)"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_rename_workspace_by_id(QString)"), 0)
        self.assertGreaterEqual(meta.indexOfMethod("request_rename_view(QString)"), 0)

        with patch("ea_node_editor.ui.dialogs.workflow_settings_dialog.WorkflowSettingsDialog.exec", return_value=0):
            QMetaObject.invokeMethod(
                self.window,
                "show_workflow_settings_dialog",
                Qt.ConnectionType.DirectConnection,
            )
        with (
            patch("ea_node_editor.ui.dialogs.graphics_settings_dialog.GraphicsSettingsDialog.exec", return_value=0),
            patch("ea_node_editor.ui.dialogs.GraphicsSettingsDialog.exec", return_value=0),
        ):
            QMetaObject.invokeMethod(
                self.window,
                "show_graphics_settings_dialog",
                Qt.ConnectionType.DirectConnection,
            )
        with patch("ea_node_editor.ui.dialogs.input_reference_dialog.InputReferenceDialog.exec", return_value=0):
            QMetaObject.invokeMethod(
                self.window,
                "show_keyboard_mouse_reference_dialog",
                Qt.ConnectionType.DirectConnection,
            )
        QMetaObject.invokeMethod(
            self.window,
            "set_script_editor_panel_visible",
            Qt.ConnectionType.DirectConnection,
            Q_ARG(bool, False),
        )
        self.app.processEvents()
        self.assertFalse(self.window.script_editor.visible)

    def test_request_rename_workspace_by_id_updates_target_workspace_label(self) -> None:
        original_workspace_id = self.window.workspace_manager.active_workspace_id()
        renamed_workspace_id = self.window.workspace_manager.create_workspace("Second")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(original_workspace_id)
        self.app.processEvents()

        with patch.object(
            self.window.shell_host_presenter,
            "prompt_text_value",
            return_value=("Renamed Space", True),
        ):
            renamed = self.window.request_rename_workspace_by_id(renamed_workspace_id)
        self.app.processEvents()

        self.assertTrue(renamed)
        self.assertEqual(
            self.window.model.project.workspaces[renamed_workspace_id].name,
            "Renamed Space",
        )
        target_tabs = [
            tab for tab in self.window.workspace_tabs.tabs
            if tab.get("workspace_id") == renamed_workspace_id
        ]
        self.assertEqual(len(target_tabs), 1)
        self.assertEqual(target_tabs[0]["label"], "Renamed Space")

    def test_new_workspace_action_creates_and_activates_workspace_via_shell_prompt(self) -> None:
        with patch.object(
            self.window.shell_host_presenter,
            "prompt_text_value",
            return_value=("Created Workspace", True),
        ) as prompt_text_value:
            self.window.action_new_workspace.trigger()
            self.app.processEvents()

        self.assertEqual(len(self.window.model.project.workspaces), 2)
        prompt_text_value.assert_called_once_with(title="New Workspace", label="Workspace name:")
        self.assertEqual(self.window.active_workspace_name, "Created Workspace")

    def test_status_api_contract_updates_visible_values(self) -> None:
        self.window.update_engine_status("running", "Job #12")
        self.window.update_job_counters(2, 3, 4, 1)
        self.window.update_system_metrics(37.0, 4.3, 16.0)
        self.window.update_notification_counters(5, 2)
        self.app.processEvents()

        self.assertEqual(self.window.status_engine.icon(), "Run")
        self.assertEqual(self.window.status_engine.text(), "Running (Job #12)")
        self.assertEqual(self.window.status_jobs.text(), "R:2 Q:3 D:4 F:1")
        self.assertEqual(
            self.window.status_metrics.text(),
            "FPS:0 CPU:37% RAM:4.3/16.0 GB Disk R:0.0 W:0.0 MB/s",
        )
        self.assertEqual(self.window.status_notifications.text(), "W:5 E:2")

    def test_command_actions_and_workspace_shortcuts_are_wired(self) -> None:
        self.window.workspace_manager.create_workspace("Second")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_tabs.setCurrentIndex(0)
        self.app.processEvents()

        self.window.action_next_workspace.trigger()
        self.app.processEvents()
        self.assertEqual(self.window.workspace_tabs.currentIndex(), 1)

        self.window.action_prev_workspace.trigger()
        self.app.processEvents()
        self.assertEqual(self.window.workspace_tabs.currentIndex(), 0)

        self.assertIn("Ctrl+Tab", _action_shortcuts(self.window.action_next_workspace))
        self.assertIn("Ctrl+PgDown", _action_shortcuts(self.window.action_next_workspace))
        self.assertIn("Ctrl+Shift+Tab", _action_shortcuts(self.window.action_prev_workspace))
        self.assertIn("Ctrl+PgUp", _action_shortcuts(self.window.action_prev_workspace))
        self.assertIn("A", _action_shortcuts(self.window.action_frame_all))
        self.assertIn("F", _action_shortcuts(self.window.action_frame_selection))
        self.assertIn("Shift+F", _action_shortcuts(self.window.action_center_selection))
        self.assertIn("Ctrl+Z", _action_shortcuts(self.window.action_undo))
        self.assertIn("Ctrl+Shift+Z", _action_shortcuts(self.window.action_redo))
        self.assertIn("Ctrl+Y", _action_shortcuts(self.window.action_redo))
        self.assertIn("Ctrl+K", _action_shortcuts(self.window.action_graph_search))
        self.assertIn("Ctrl+B", _action_shortcuts(self.window.action_node_browser))
        self.assertIn("Ctrl+D", _action_shortcuts(self.window.action_duplicate_selection))
        self.assertIn("Ctrl+Alt+G", _action_shortcuts(self.window.action_group_selection))
        self.assertIn("Ctrl+Shift+G", _action_shortcuts(self.window.action_ungroup_selection))
        self.assertIn("Ctrl+C", _action_shortcuts(self.window.action_copy_selection))
        self.assertIn("Ctrl+X", _action_shortcuts(self.window.action_cut_selection))
        self.assertIn("Ctrl+V", _action_shortcuts(self.window.action_paste_selection))
        self.assertIn("Alt+Left", _action_shortcuts(self.window.action_scope_parent))
        self.assertIn("Alt+Home", _action_shortcuts(self.window.action_scope_root))
        self.assertTrue(self.window.action_snap_to_grid.isCheckable())
        self.assertFalse(self.window.snap_to_grid_enabled)
        self.assertFalse(self.window.action_snap_to_grid.isChecked())
        self.assertTrue(self.window.action_run.isEnabled())
        self.assertFalse(self.window.action_pause.isEnabled())
        self.assertFalse(self.window.action_stop.isEnabled())

        root_object = self.window.quick_widget.rootObject()
        node_browser_overlay = root_object.findChild(QObject, "nodeBrowserOverlay")
        quick_insert_overlay = root_object.findChild(QObject, "connectionQuickInsertOverlay")
        self.assertFalse(bool(node_browser_overlay.property("visible")))
        self.assertFalse(self.window.connection_quick_insert_open)
        self.window.action_node_browser.trigger()
        self.app.processEvents()
        self.assertFalse(bool(node_browser_overlay.property("visible")))
        self.assertTrue(self.window.connection_quick_insert_open)
        self.assertTrue(self.window.connection_quick_insert_is_canvas_mode)
        self.assertTrue(bool(quick_insert_overlay.property("visible")))
        self.window.request_close_connection_quick_insert()
        self.app.processEvents()
        self.assertFalse(self.window.connection_quick_insert_open)
        self.assertFalse(bool(quick_insert_overlay.property("visible")))

        with patch.object(
            self.window.execution_client,
            "dispatch_prepared",
            return_value="run_test",
        ) as dispatch_prepared:
            self.window.action_run.trigger()
            self.app.processEvents()
            dispatch_prepared.assert_called_once()
        self.assertFalse(self.window.action_run.isEnabled())
        self.assertTrue(self.window.action_pause.isEnabled())
        self.assertTrue(self.window.action_stop.isEnabled())

        self.window._active_run_id = "run_test"
        with patch.object(self.window.execution_client, "stop_run") as stop_run:
            self.window.action_stop.trigger()
            self.app.processEvents()
            stop_run.assert_called_once_with("run_test")

        self.window._engine_state_value = "running"
        self.window.run_projection_controller.update_run_actions()
        with patch.object(self.window.execution_client, "pause_run") as pause_run:
            self.window.action_pause.trigger()
            self.app.processEvents()
            pause_run.assert_called_once_with("run_test")

        self.window._engine_state_value = "paused"
        self.window.run_projection_controller.update_run_actions()
        with patch.object(self.window.execution_client, "resume_run") as resume_run:
            self.window.action_pause.trigger()
            self.app.processEvents()
            resume_run.assert_called_once_with("run_test")

    def test_layout_actions_and_snap_toggle_are_undoable(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        node_a = self.window.scene.add_node_from_type("core.constant", x=20.0, y=40.0)
        node_b = self.window.scene.add_node_from_type("core.python_script", x=320.0, y=180.0)
        node_c = self.window.scene.add_node_from_type("core.logger", x=640.0, y=80.0)
        self.window.scene.select_node(node_a, False)
        self.window.scene.select_node(node_b, True)
        self.window.scene.select_node(node_c, True)
        self.window.runtime_history.clear_workspace(workspace_id)
        before_state = self._workspace_state()

        self.window.action_distribute_horizontally.trigger()
        self.app.processEvents()
        after_distribute = self._workspace_state()
        self.assertNotEqual(after_distribute, before_state)
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), 1)

        distributed_bounds = sorted(
            (self.window.scene.node_bounds(node_id) for node_id in (node_a, node_b, node_c)),
            key=lambda bounds: float(bounds.x()) if bounds is not None else 0.0,
        )
        self.assertTrue(all(bounds is not None for bounds in distributed_bounds))
        gap_01 = distributed_bounds[1].x() - (distributed_bounds[0].x() + distributed_bounds[0].width())
        gap_12 = distributed_bounds[2].x() - (distributed_bounds[1].x() + distributed_bounds[1].width())
        self.assertAlmostEqual(gap_01, gap_12, places=6)

        self.window.action_undo.trigger()
        self.app.processEvents()
        self.assertEqual(self._workspace_state(), before_state)
        self.window.action_redo.trigger()
        self.app.processEvents()
        self.assertEqual(self._workspace_state(), after_distribute)

        self.window.scene.move_node(node_a, 13.0, 17.0)
        self.window.scene.move_node(node_b, 171.0, 83.0)
        self.window.scene.select_node(node_a, False)
        self.window.scene.select_node(node_b, True)
        self.window.runtime_history.clear_workspace(workspace_id)

        self.assertFalse(self.window.snap_to_grid_enabled)
        self.window.action_snap_to_grid.trigger()
        self.assertTrue(self.window.snap_to_grid_enabled)
        self.assertTrue(self.window.action_snap_to_grid.isChecked())

        before_snap_layout = self._workspace_state()
        self.window.action_align_top.trigger()
        self.app.processEvents()
        after_snap_layout = self._workspace_state()
        self.assertNotEqual(after_snap_layout, before_snap_layout)
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), 1)

        for node_id in (node_a, node_b):
            node = workspace.nodes[node_id]
            self.assertAlmostEqual(float(node.x) / 20.0, round(float(node.x) / 20.0), places=6)
            self.assertAlmostEqual(float(node.y) / 20.0, round(float(node.y) / 20.0), places=6)

        self.window.action_undo.trigger()
        self.app.processEvents()
        self.assertEqual(self._workspace_state(), before_snap_layout)

        self.window.action_snap_to_grid.trigger()
        self.assertFalse(self.window.snap_to_grid_enabled)
        self.assertFalse(self.window.action_snap_to_grid.isChecked())

    def test_snap_to_grid_setting_persists_across_window_restart(self) -> None:
        self.assertFalse(self.window.snap_to_grid_enabled)
        self.assertFalse(self.window.action_snap_to_grid.isChecked())

        self.window.set_snap_to_grid_enabled(True)
        self.app.processEvents()

        self.assertTrue(self.window.snap_to_grid_enabled)
        self.assertTrue(self.window.action_snap_to_grid.isChecked())
        persisted = json.loads(self._app_preferences_path.read_text(encoding="utf-8"))
        self.assertTrue(persisted["graphics"]["interaction"]["snap_to_grid"])

        self._reopen_window()

        self.assertTrue(self.window.snap_to_grid_enabled)
        self.assertTrue(self.window.action_snap_to_grid.isChecked())

    def test_locked_object_interaction_action_is_session_only_and_uses_ctrl_l(self) -> None:
        action = self.window.action_interact_with_locked_objects
        self.assertEqual(action.text(), "Interact with Locked Objects")
        self.assertTrue(action.isCheckable())
        self.assertFalse(action.isChecked())
        self.assertIn("Ctrl+L", _action_shortcuts(action))
        self.assertIn("Ctrl+Shift+L", _action_shortcuts(self.window.action_connect_selected))

        edit_menu = next(menu for menu in self.window.menuBar().findChildren(QMenu) if menu.title() == "&Edit")
        self.assertIs(edit_menu.actions()[-1], action)
        self.assertFalse(self.window.scene.interact_with_locked_objects)

        action.trigger()
        self.assertTrue(action.isChecked())
        self.assertTrue(self.window.scene.interact_with_locked_objects)
        action.trigger()
        self.assertFalse(action.isChecked())
        self.assertFalse(self.window.scene.interact_with_locked_objects)

    def test_align_overlap_posts_tidy_hint(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        _workspace = self.window.model.project.workspaces[workspace_id]
        node_a = self.window.scene.add_node_from_type("core.constant", x=20.0, y=60.0)
        node_b = self.window.scene.add_node_from_type("core.python_script", x=340.0, y=60.0)
        node_c = self.window.scene.add_node_from_type("core.logger", x=680.0, y=60.0)
        self.window.scene.select_node(node_a, False)
        self.window.scene.select_node(node_b, True)
        self.window.scene.select_node(node_c, True)
        self.window.clear_graph_hint()
        self.assertFalse(self.window.graph_hint_visible)

        aligned = self.window.request_align_selection_right()
        self.assertTrue(aligned)
        self.app.processEvents()

        self.assertTrue(self.window.graph_hint_visible)
        self.assertEqual(
            self.window.graph_hint_message,
            "3 overlaps created. Press Distribute Vertically to tidy.",
        )

        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        graph_hint_overlay = root_object.findChild(QObject, "graphHintOverlay")
        self.assertIsNotNone(graph_hint_overlay)
        self.assertTrue(bool(graph_hint_overlay.property("visible")))

        self.window.clear_graph_hint()
        self.app.processEvents()
        self.assertFalse(self.window.graph_hint_visible)

    def test_graph_search_ranking_prefers_title_matches_and_limits_to_ten_results(self) -> None:
        workspace_a_id = self.window.workspace_manager.active_workspace_id()
        self.window.workspace_manager.rename_workspace(workspace_a_id, "Alpha Space")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(workspace_a_id)

        prefix_id = self.window.scene.add_node_from_type("core.constant", x=20.0, y=20.0)
        self.window.scene.set_node_title(prefix_id, "core. prefix title")
        substring_id = self.window.scene.add_node_from_type("core.constant", x=220.0, y=20.0)
        self.window.scene.set_node_title(substring_id, "alpha core. substring")
        type_alpha_id = self.window.scene.add_node_from_type("core.constant", x=420.0, y=20.0)
        self.window.scene.set_node_title(type_alpha_id, "Alpha")
        type_zulu_id = self.window.scene.add_node_from_type("core.constant", x=620.0, y=20.0)
        self.window.scene.set_node_title(type_zulu_id, "Zulu")

        workspace_b_id = self.window.workspace_manager.create_workspace("Beta Space")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(workspace_b_id)
        for index in range(12):
            node_id = self.window.scene.add_node_from_type("core.constant", x=20.0 * index, y=120.0)
            self.window.scene.set_node_title(node_id, f"Node {index:02d}")
        self.app.processEvents()

        self.window.action_graph_search.trigger()
        self.window.set_graph_search_query("CORE.")
        self.app.processEvents()

        results = self.window.graph_search_results
        self.assertEqual(len(results), 10)
        self.assertEqual(results[0]["node_id"], prefix_id)
        self.assertEqual(results[1]["node_id"], substring_id)

        tail_keys = [(item["workspace_name"], item["node_title"]) for item in results[2:]]
        self.assertEqual(
            tail_keys,
            sorted(tail_keys, key=lambda value: (value[0].lower(), value[1].lower())),
        )

    def test_graph_search_ignores_internal_node_ids_and_empty_or_missing_queries_are_safe_noops(self) -> None:
        node_id = self.window.scene.add_node_from_type("core.constant", x=30.0, y=30.0)
        self.window.scene.set_node_title(node_id, "Plain Title")
        display_name_id = self.window.scene.add_node_from_type("core.python_script", x=260.0, y=40.0)
        self.window.scene.set_node_title(display_name_id, "Custom Script Title")
        self.app.processEvents()

        self.window.action_graph_search.trigger()
        self.window.set_graph_search_query(node_id[-6:].upper())
        self.app.processEvents()

        self.assertEqual(self.window.graph_search_results, [])
        self.assertFalse(self.window.request_graph_search_accept())

        self.window.set_graph_search_query("PyThOn ScRiPt")
        self.app.processEvents()
        self.assertIn(display_name_id, {item["node_id"] for item in self.window.graph_search_results})

        self.window.set_graph_search_query("")
        self.assertEqual(self.window.graph_search_results, [])
        self.assertFalse(self.window.request_graph_search_accept())

        before_workspace_id = self.window.workspace_manager.active_workspace_id()
        before_selected_id = self.window.scene.selected_node_id()
        self.window.set_graph_search_query("zzzzz_missing_node_query")
        self.assertEqual(self.window.graph_search_results, [])
        self.assertFalse(self.window.request_graph_search_accept())
        self.assertEqual(self.window.workspace_manager.active_workspace_id(), before_workspace_id)
        self.assertEqual(self.window.scene.selected_node_id(), before_selected_id)

    def test_graph_search_scopes_filter_matches_and_report_metadata(self) -> None:
        title_node_id = self.window.scene.add_node_from_type("core.constant", x=40.0, y=40.0)
        self.window.scene.set_node_title(title_node_id, "Python Title Result")

        type_node_id = self.window.scene.add_node_from_type("core.python_script", x=240.0, y=40.0)
        self.window.scene.set_node_title(type_node_id, "Zulu Type Result")

        content_node_id = self.window.scene.add_node_from_type("core.logger", x=440.0, y=40.0)
        self.window.scene.set_node_title(content_node_id, "Zulu Content Result")
        active_workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[active_workspace_id]
        workspace.nodes[content_node_id].properties["message"] = "Python content note"

        port_node_id = self.window.scene.add_node_from_type("core.logger", x=640.0, y=40.0)
        self.window.scene.set_node_title(port_node_id, "Zulu Port Result")
        workspace.nodes[port_node_id].port_labels["message"] = "Python Port Label"
        self.window.scene.refresh_workspace_from_model(active_workspace_id)
        self.app.processEvents()

        self.window.action_graph_search.trigger()
        self.window.set_graph_search_query("python")
        self.app.processEvents()

        all_results = self.window.graph_search_results
        self.assertEqual(
            [item["node_id"] for item in all_results[:4]],
            [title_node_id, type_node_id, content_node_id, port_node_id],
        )
        self.assertEqual([item["match_scope"] for item in all_results[:4]], ["title", "type", "content", "port"])
        self.assertEqual(all_results[0]["match_label"], "Title")
        self.assertEqual(all_results[1]["match_label"], "Node Type")
        self.assertEqual(all_results[1]["match_preview"], "Python Script")
        self.assertEqual(all_results[2]["match_label"], "Message")
        self.assertEqual(all_results[2]["match_preview"], "Python content note")
        self.assertEqual(all_results[3]["match_label"], "Port Label")
        self.assertEqual(all_results[3]["match_preview"], "Python Port Label")

        self._set_graph_search_scopes({"title"})
        title_results = self.window.graph_search_results
        self.assertEqual([item["node_id"] for item in title_results], [title_node_id])
        self.assertEqual(title_results[0]["match_scope"], "title")

        self._set_graph_search_scopes({"type"})
        type_results = self.window.graph_search_results
        self.assertEqual([item["node_id"] for item in type_results], [type_node_id])
        self.assertEqual(type_results[0]["match_scope"], "type")
        self.assertEqual(type_results[0]["match_preview"], "Python Script")

        self._set_graph_search_scopes({"content"})
        content_results = self.window.graph_search_results
        self.assertEqual([item["node_id"] for item in content_results], [content_node_id])
        self.assertEqual(content_results[0]["match_scope"], "content")
        self.assertEqual(content_results[0]["match_label"], "Message")

        self._set_graph_search_scopes({"port"})
        port_results = self.window.graph_search_results
        self.assertEqual([item["node_id"] for item in port_results], [port_node_id])
        self.assertEqual(port_results[0]["match_scope"], "port")
        self.assertEqual(port_results[0]["match_preview"], "Python Port Label")

    def test_graph_search_content_scope_skips_sensitive_and_structural_string_fields(self) -> None:
        allowed_node_id = self.window.scene.add_node_from_type("core.logger", x=40.0, y=40.0)
        self.window.scene.set_node_title(allowed_node_id, "Allowed Content Result")
        script_node_id = self.window.scene.add_node_from_type("core.python_script", x=240.0, y=40.0)
        self.window.scene.set_node_title(script_node_id, "Script Content Result")
        path_node_id = self.window.scene.add_node_from_type("io.file_read", x=440.0, y=40.0)
        self.window.scene.set_node_title(path_node_id, "Path Content Result")
        command_node_id = self.window.scene.add_node_from_type("io.process_run", x=640.0, y=40.0)
        self.window.scene.set_node_title(command_node_id, "Command Content Result")
        password_node_id = self.window.scene.add_node_from_type("io.email_send", x=840.0, y=40.0)
        self.window.scene.set_node_title(password_node_id, "Password Content Result")

        query = "sensitive scope marker"
        active_workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[active_workspace_id]
        workspace.nodes[allowed_node_id].properties["message"] = query
        workspace.nodes[script_node_id].properties["script"] = (
            PYTHON_SCRIPT_DEFAULT_SOURCE + f"# {query}\n"
        )
        workspace.nodes[path_node_id].properties["path"] = query
        workspace.nodes[command_node_id].properties["command"] = query
        workspace.nodes[password_node_id].properties["password"] = query
        self.app.processEvents()

        self.window.action_graph_search.trigger()
        self.window.set_graph_search_query(query)
        self._set_graph_search_scopes({"content"})

        results = self.window.graph_search_results
        self.assertEqual([item["node_id"] for item in results], [allowed_node_id])
        self.assertEqual(results[0]["match_scope"], "content")
        self.assertEqual(results[0]["match_label"], "Message")
        self.assertEqual(results[0]["match_preview"], query)

    def test_graph_search_jump_switches_workspace_reveals_parent_chain_and_centers_selection(self) -> None:
        source_workspace_id = self.window.workspace_manager.active_workspace_id()
        target_workspace_id = self.window.workspace_manager.create_workspace("Target Space")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(target_workspace_id)

        parent_id = self.window.scene.add_node_from_type("core.constant", x=140.0, y=80.0)
        child_id = self.window.scene.add_node_from_type("core.logger", x=640.0, y=360.0)
        target_workspace = self.window.model.project.workspaces[target_workspace_id]
        target_workspace.nodes[child_id].parent_node_id = parent_id
        self.window.scene.set_node_collapsed(parent_id, True)
        self.window.scene.set_node_title(child_id, "Needle Jump Node")
        self.app.processEvents()

        self.window.workspace_navigation_controller.switch_workspace(source_workspace_id)
        self.window.view.set_zoom(0.65)
        self.window.view.centerOn(-420.0, -260.0)

        self.window.action_graph_search.trigger()
        self.window.set_graph_search_query("needle jump")
        self.app.processEvents()
        self.assertEqual(self.window.graph_search_highlight_index, 0)

        jumped = self.window.request_graph_search_accept()
        self.assertTrue(jumped)
        self.app.processEvents()

        self.assertEqual(self.window.workspace_manager.active_workspace_id(), target_workspace_id)
        self.assertFalse(target_workspace.nodes[parent_id].collapsed)
        self.assertEqual(self.window.scene.selected_node_id(), child_id)

        bounds = self.window.scene.node_bounds(child_id)
        self.assertIsNotNone(bounds)
        target_workspace.ensure_default_view()
        target_view = target_workspace.views[target_workspace.active_view_id]
        self.assertAlmostEqual(self.window.view.zoom, target_view.zoom, places=6)
        self.assertAlmostEqual(self.window.view.center_x, bounds.center().x(), places=6)
        self.assertAlmostEqual(self.window.view.center_y, bounds.center().y(), places=6)

        self.assertFalse(self.window.graph_search_open)
        self.assertEqual(self.window.graph_search_query, "")
        self.assertEqual(self.window.graph_search_results, [])

    def test_graph_search_jump_opens_subnode_scope_for_nested_match(self) -> None:
        source_workspace_id = self.window.workspace_manager.active_workspace_id()
        target_workspace_id = self.window.workspace_manager.create_workspace("Scoped Search Target")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(target_workspace_id)

        shell_id = self.window.scene.add_node_from_type("core.subnode", x=260.0, y=150.0)
        nested_node_id = self.window.scene.add_node_from_type("core.logger", x=120.0, y=100.0)
        target_workspace = self.window.model.project.workspaces[target_workspace_id]
        target_workspace.nodes[nested_node_id].parent_node_id = shell_id
        self.window.scene.refresh_workspace_from_model(target_workspace_id)
        self.window.scene.set_node_title(nested_node_id, "Nested Needle Result")
        self.app.processEvents()

        self.window.workspace_navigation_controller.switch_workspace(source_workspace_id)
        self.window.action_graph_search.trigger()
        self.window.set_graph_search_query("nested needle")
        self.app.processEvents()

        jumped = self.window.request_graph_search_accept()
        self.assertTrue(jumped)
        self.app.processEvents()

        self.assertEqual(self.window.workspace_manager.active_workspace_id(), target_workspace_id)
        self.assertEqual(self.window.scene.active_scope_path, [shell_id])
        self.assertEqual(self.window.scene.selected_node_id(), nested_node_id)
        visible_node_ids = {item["node_id"] for item in self.window.scene.nodes_model}
        self.assertIn(nested_node_id, visible_node_ids)
        self.assertNotIn(shell_id, visible_node_ids)

    def test_failure_focus_opens_scope_for_nested_node(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        shell_id = self.window.scene.add_node_from_type("core.subnode", x=220.0, y=110.0)
        nested_node_id = self.window.scene.add_node_from_type("core.python_script", x=120.0, y=90.0)
        workspace = self.window.model.project.workspaces[workspace_id]
        workspace.nodes[nested_node_id].parent_node_id = shell_id
        self.window.scene.refresh_workspace_from_model(workspace_id)
        self.app.processEvents()

        self.assertEqual(self.window.scene.active_scope_path, [])
        self.window.workspace_navigation_controller.focus_failed_node(
            workspace_id, nested_node_id
        )
        self.app.processEvents()

        self.assertEqual(self.window.scene.active_scope_path, [shell_id])
        self.assertEqual(self.window.scene.selected_node_id(), nested_node_id)
        bounds = self.window.scene.selection_bounds()
        self.assertIsNotNone(bounds)
        self.assertAlmostEqual(self.window.view.center_x, bounds.center().x(), places=6)
        self.assertAlmostEqual(self.window.view.center_y, bounds.center().y(), places=6)

    def test_run_failed_event_for_nested_node_opens_scope_and_focuses_inner_node(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        shell_id = self.window.scene.add_node_from_type("core.subnode", x=260.0, y=120.0)
        nested_node_id = self.window.scene.add_node_from_type("core.python_script", x=120.0, y=90.0)
        workspace = self.window.model.project.workspaces[workspace_id]
        workspace.nodes[nested_node_id].parent_node_id = shell_id
        self.window.scene.refresh_workspace_from_model(workspace_id)
        self.app.processEvents()

        self.window._active_run_id = "run_live"
        self.window._active_run_workspace_id = workspace_id
        self.window.run_projection_controller.set_run_ui_state("running", "Running", 1, 0, 0, 0)

        with patch.object(QMessageBox, "critical"):
            self.window.execution_event.emit(
                {
                    "type": "run_failed",
                    "run_id": "run_live",
                    "workspace_id": workspace_id,
                    "node_id": nested_node_id,
                    "error": "RuntimeError: nested failure",
                    "traceback": "traceback: nested",
                }
            )
            self.app.processEvents()

        self.assertEqual(self.window.scene.active_scope_path, [shell_id])
        self.assertEqual(self.window.scene.selected_node_id(), nested_node_id)
        self.assertEqual(self.window._active_run_id, "")

    def test_graph_search_keyboard_navigation_and_close_behavior(self) -> None:
        node_a_id = self.window.scene.add_node_from_type("core.constant", x=50.0, y=50.0)
        node_b_id = self.window.scene.add_node_from_type("core.constant", x=250.0, y=50.0)
        self.window.scene.set_node_title(node_a_id, "Search Candidate A")
        self.window.scene.set_node_title(node_b_id, "Search Candidate B")
        self.app.processEvents()

        self.window.action_graph_search.trigger()
        self.assertTrue(self.window.graph_search_open)
        self.window.set_graph_search_query("search candidate")
        self.app.processEvents()
        self.assertGreaterEqual(len(self.window.graph_search_results), 2)
        self.assertEqual(self.window.graph_search_highlight_index, 0)

        self.window.request_graph_search_move(1)
        self.assertEqual(self.window.graph_search_highlight_index, 1)
        self.window.request_graph_search_move(1)
        self.assertEqual(self.window.graph_search_highlight_index, 1)
        self.window.request_graph_search_move(-1)
        self.assertEqual(self.window.graph_search_highlight_index, 0)
        self.window.request_graph_search_move(-1)
        self.assertEqual(self.window.graph_search_highlight_index, 0)

        self.window.request_close_graph_search()
        self.assertFalse(self.window.graph_search_open)
        self.assertEqual(self.window.graph_search_query, "")
        self.assertEqual(self.window.graph_search_enabled_scopes, ["title", "type", "content", "port"])
        self.assertEqual(self.window.graph_search_results, [])
        self.assertEqual(self.window.graph_search_highlight_index, -1)

    def test_graph_search_filter_ui_resets_on_reopen_and_keeps_one_scope_enabled(self) -> None:
        self.window.action_graph_search.trigger()
        self.assertEqual(self.window.graph_search_enabled_scopes, ["title", "type", "content", "port"])

        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        filter_button = root_object.findChild(QObject, "graphSearchFilterButton")
        self.assertIsNotNone(filter_button)
        self.assertFalse(bool(filter_button.property("selectedStyle")))

        self.window.set_graph_search_scope_enabled("title", False)
        self.window.set_graph_search_scope_enabled("type", False)
        self.window.set_graph_search_scope_enabled("content", False)
        self.app.processEvents()

        self.assertEqual(self.window.graph_search_enabled_scopes, ["port"])
        self.assertTrue(bool(filter_button.property("selectedStyle")))

        self.window.set_graph_search_scope_enabled("port", False)
        self.app.processEvents()
        self.assertEqual(self.window.graph_search_enabled_scopes, ["port"])

        self.window.request_close_graph_search()
        self.assertFalse(self.window.graph_search_open)
        self.assertEqual(self.window.graph_search_enabled_scopes, ["title", "type", "content", "port"])

        self.window.action_graph_search.trigger()
        self.app.processEvents()
        self.assertEqual(self.window.graph_search_enabled_scopes, ["title", "type", "content", "port"])
        self.assertFalse(bool(filter_button.property("selectedStyle")))
