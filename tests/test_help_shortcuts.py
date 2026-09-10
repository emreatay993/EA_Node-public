from __future__ import annotations

import pytest
from PyQt6.QtCore import QMetaObject, QObject, QPoint, QPointF, Qt
from PyQt6.QtQuick import QQuickItem
from PyQt6.QtTest import QTest

from tests.main_window_shell.base import SharedMainWindowShellTestBase, _action_shortcuts
from tests.qt_wait import wait_for_condition_or_raise

pytestmark = pytest.mark.xdist_group("p03_main_window_shell")


class HelpShortcutShellTests(SharedMainWindowShellTestBase):
    def _walk_items(self, item: QQuickItem):
        yield item
        for child in item.childItems():
            yield from self._walk_items(child)

    def _inspector_pane(self) -> QObject:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        pane = root_object.findChild(QObject, "inspectorPane")
        self.assertIsNotNone(pane)
        return pane

    def _item_widget_point(self, item: QQuickItem, x: float, y: float) -> QPoint:
        item_window = item.window()
        self.assertIsNotNone(item_window)
        scene_point = item.mapToScene(QPointF(x, y))
        global_point = item_window.mapToGlobal(
            QPoint(round(scene_point.x()), round(scene_point.y()))
        )
        return self.window.quick_widget.mapFromGlobal(global_point)

    def _find_visible_text_item(self, root: QObject, text: str) -> QQuickItem:
        self.assertIsInstance(root, QQuickItem)
        for item in self._walk_items(root):
            if str(item.property("text") or "") != text:
                continue
            if item.property("visible") is False:
                continue
            return item
        self.fail(f"Could not find visible text item {text!r}.")

    def test_help_tab_click_loads_docs_for_selected_node_when_available(self) -> None:
        inspector_pane = self._inspector_pane()
        node_id = self.window.scene.add_node_from_type("core.logger", x=120.0, y=80.0)
        self.app.processEvents()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        self.assertEqual(self.window.scene.selected_node_id(), node_id)
        inspector_pane.setProperty("activeTabIndex", 0)
        self.window.help_bridge.close_help()
        self.app.processEvents()

        help_label = self._find_visible_text_item(inspector_pane, "Help")
        help_tab = help_label.parentItem()
        self.assertIsNotNone(help_tab)

        QTest.mouseClick(
            self.window.quick_widget,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            self._item_widget_point(
                help_tab,
                float(help_tab.width()) * 0.5,
                float(help_tab.height()) * 0.5,
            ),
        )
        wait_for_condition_or_raise(
            lambda: (
                int(inspector_pane.property("activeTabIndex")) == 1
                and self.window.help_bridge.visible
                and self.window.help_bridge.title == "Logger"
            ),
            timeout_ms=1200,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Help tab click did not activate the Help pane and load structured help.",
        )

        self.assertIn("# Logger", self.window.help_bridge.markdown)
        self.assertIn("**Keywords:** log, message, diagnostics", self.window.help_bridge.markdown)
        self.assertEqual(self.window.help_bridge.type_id, "core.logger")

    def test_f1_shortcut_switches_to_structured_node_help(self) -> None:
        inspector_pane = self._inspector_pane()
        node_id = self.window.scene.add_node_from_type("core.logger", x=120.0, y=80.0)
        self.app.processEvents()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        self.assertEqual(self.window.scene.selected_node_id(), node_id)
        self.assertIn("F1", _action_shortcuts(self.window.action_show_help))
        inspector_pane.setProperty("activeTabIndex", 0)
        self.window.help_bridge.close_help()
        self.app.processEvents()

        self.window.activateWindow()
        self.window.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        QMetaObject.invokeMethod(inspector_pane, "forceActiveFocus")
        QTest.keyClick(self.window, Qt.Key.Key_F1)
        wait_for_condition_or_raise(
            lambda: int(inspector_pane.property("activeTabIndex")) == 1,
            timeout_ms=1200,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="F1 did not switch the inspector to the Help tab.",
        )

        self.assertTrue(self.window.help_bridge.visible)
        self.assertEqual(self.window.help_bridge.title, "Logger")
        self.assertEqual(self.window.help_bridge.type_id, "core.logger")
        self.assertIn(
            "Writes an informational, warning, or error message",
            self.window.help_bridge.markdown,
        )
        self.assertIn("**Keywords:** log, message, diagnostics", self.window.help_bridge.markdown)
        self.assertIn("## Inputs", self.window.help_bridge.markdown)
        self.assertIn(
            "Message to log; overrides the configured Message property when connected.",
            self.window.help_bridge.markdown,
        )
        message_port = self.window.registry.get_spec("core.logger").ports[0]
        self.assertEqual(
            ("message", "in", "data", "tree"),
            (message_port.key, message_port.direction, message_port.kind, message_port.data_access),
        )
        self.assertNotIn("Starts logging when execution reaches this node.", self.window.help_bridge.markdown)
        self.assertNotIn("Continues execution after the message is written.", self.window.help_bridge.markdown)
        self.assertNotIn("## Outputs", self.window.help_bridge.markdown)
