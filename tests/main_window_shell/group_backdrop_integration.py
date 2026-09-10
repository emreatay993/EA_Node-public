# Purpose: Mounted-shell integration checks that cannot be proven by graph or QML owners alone.
# Map: feature_routes/group_backdrops_peek_membership
# Tests: tests/test_shell_isolation_phase.py
from __future__ import annotations

import gc

from PyQt6.QtCore import QObject, QPoint, QPointF, Qt
from PyQt6.QtQuick import QQuickItem
from PyQt6.QtTest import QTest

from tests.main_window_shell.base import MainWindowShellTestBase, _action_shortcuts
from tests.qt_wait import wait_for_condition_or_raise

GROUP_BACKDROP_TYPE_ID = "passive.annotation.group_backdrop"
LOGGER_TYPE_ID = "core.logger"


def _menu_action_texts(menu: QObject) -> list[str]:
    actions = menu.property("visibleActions") or []
    if hasattr(actions, "toVariant"):
        actions = actions.toVariant()
    return [
        str(
            action.toVariant().get("text", "")
            if hasattr(action, "toVariant")
            else action.get("text", "")
        )
        for action in actions
        if hasattr(action, "toVariant") or isinstance(action, dict)
    ]


class MainWindowShellGroupBackdropIntegrationTests(MainWindowShellTestBase):
    def setUp(self) -> None:
        super().setUp()
        self._held_qml_refs: list[QQuickItem] = []

    def tearDown(self) -> None:
        try:
            super().tearDown()
        finally:
            self._held_qml_refs = []
            gc.collect()

    def _walk_items(self, item: QQuickItem):
        yield item
        for child in item.childItems():
            yield from self._walk_items(child)

    def _node_child(self, node_id: str, object_name: str) -> QQuickItem:
        graph_canvas = self._graph_canvas_item()
        for card in self._walk_items(graph_canvas):
            if card.objectName() != "graphNodeCard":
                continue
            if str((card.property("nodeData") or {}).get("node_id", "")) != node_id:
                continue
            for child in self._walk_items(card):
                if child.objectName() == object_name:
                    self._held_qml_refs.extend((card, child))
                    return child
        self.fail(f"Missing {object_name!r} for {node_id!r}.")

    def _add_group(self, x: float, y: float, width: float, height: float) -> str:
        node_id = self.window.scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, x=x, y=y)
        self.window.scene.set_node_geometry(node_id, x, y, width, height)
        return node_id

    @staticmethod
    def _payload_ids(payloads) -> set[str]:  # noqa: ANN001
        return {str(item.get("node_id", "")) for item in payloads}

    def test_group_library_add_drop_and_current_empty_title_fallback(self) -> None:
        workspace = self.window.model.active_workspace
        self.window.set_library_query("group")
        self.window.set_library_category("")
        self.window.set_library_data_type("")
        self.window.set_library_direction("")
        self.app.processEvents()

        self.assertEqual(
            [
                item["type_id"]
                for item in self.window.filtered_node_library_items
                if item["type_id"] == GROUP_BACKDROP_TYPE_ID
            ],
            [GROUP_BACKDROP_TYPE_ID],
        )

        before = set(workspace.nodes)
        self.window.request_add_node_from_library(GROUP_BACKDROP_TYPE_ID)
        self.app.processEvents()
        [added_id] = set(workspace.nodes) - before

        before = set(workspace.nodes)
        self.assertTrue(
            self.window.request_drop_node_from_library(
                GROUP_BACKDROP_TYPE_ID, 420.0, 300.0, "", "", "", ""
            )
        )
        self.app.processEvents()
        [dropped_id] = set(workspace.nodes) - before

        for node_id in (added_id, dropped_id):
            node = workspace.nodes[node_id]
            self.assertEqual(node.type_id, GROUP_BACKDROP_TYPE_ID)
            self.assertEqual(node.title, "")
            self.assertEqual(node.properties, {"title": ""})
            self.assertIn(
                node_id, self._payload_ids(self.window.scene.backdrop_nodes_model)
            )
        self.assertAlmostEqual(float(workspace.nodes[dropped_id].x), 420.0)
        self.assertAlmostEqual(float(workspace.nodes[dropped_id].y), 300.0)

        self.window.scene.set_node_collapsed(added_id, True)
        self.window.scene.clear_selection()
        self.app.processEvents()
        title = self._node_child(added_id, "graphNodeTitle")
        group_icon = self._node_child(added_id, "graphNodeGroupTitleIcon")
        title_icon = self._node_child(added_id, "graphNodeTitleIcon")
        wait_for_condition_or_raise(
            lambda: bool(group_icon.property("visible")),
            timeout_ms=500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Timed out waiting for the collapsed Group icon.",
        )
        self.assertEqual(str(title.property("text") or ""), "Group")
        self.assertTrue(bool(group_icon.property("visible")))
        self.assertFalse(bool(title_icon.property("visible")))

    def test_plain_c_wrap_shortcut_does_not_collide_with_group_shortcuts(self) -> None:
        workspace = self.window.model.active_workspace
        first_id = self.window.scene.add_node_from_type(
            LOGGER_TYPE_ID, x=140.0, y=120.0
        )
        second_id = self.window.scene.add_node_from_type(
            LOGGER_TYPE_ID, x=360.0, y=250.0
        )
        self.window.scene.select_node(first_id, False)
        self.window.scene.select_node(second_id, True)
        self.app.processEvents()

        self.assertIn(
            "C", _action_shortcuts(self.window.action_wrap_selection_in_group_backdrop)
        )
        self.assertIn(
            "Ctrl+Alt+G", _action_shortcuts(self.window.action_group_selection)
        )
        self.assertIn(
            "Ctrl+Shift+G", _action_shortcuts(self.window.action_ungroup_selection)
        )

        before = set(workspace.nodes)
        self.window.quick_widget.setFocus()
        QTest.keyClick(self.window.quick_widget, Qt.Key.Key_C)
        self.app.processEvents()
        wait_for_condition_or_raise(
            lambda: len(set(workspace.nodes) - before) == 1,
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Timed out waiting for plain C to wrap the selection.",
        )
        [backdrop_id] = set(workspace.nodes) - before
        self.assertEqual(workspace.nodes[backdrop_id].type_id, GROUP_BACKDROP_TYPE_ID)
        self.assertEqual(self.window.scene.selected_node_lookup, {backdrop_id: True})

    def test_peek_inside_action_is_collapsed_group_only(self) -> None:
        graph_canvas = self._graph_canvas_item()
        menu = graph_canvas.findChild(QObject, "graphCanvasNodeContextPopup")
        self.assertIsNotNone(menu)
        group_id = self._add_group(160.0, 120.0, 380.0, 260.0)
        logger_id = self.window.scene.add_node_from_type(
            LOGGER_TYPE_ID, x=720.0, y=180.0
        )
        self.app.processEvents()

        graph_canvas.setProperty("nodeContextNodeId", group_id)
        self.app.processEvents()
        self.assertNotIn("Peek Inside", _menu_action_texts(menu))

        self.window.scene.set_node_collapsed(group_id, True)
        graph_canvas.setProperty("nodeContextNodeId", "")
        self.app.processEvents()
        graph_canvas.setProperty("nodeContextNodeId", group_id)
        self.app.processEvents()
        self.assertIn("Peek Inside", _menu_action_texts(menu))

        graph_canvas.setProperty("nodeContextNodeId", logger_id)
        self.app.processEvents()
        self.assertNotIn("Peek Inside", _menu_action_texts(menu))

    def test_comment_peek_filters_members_keeps_scope_and_supports_both_exit_paths(
        self,
    ) -> None:
        workspace = self.window.model.active_workspace
        active_view = workspace.views[workspace.active_view_id]
        graph_canvas = self._graph_canvas_item()
        menu = graph_canvas.findChild(QObject, "graphCanvasNodeContextPopup")
        self.assertIsNotNone(menu)

        outer_id = self._add_group(60.0, 60.0, 760.0, 520.0)
        inner_id = self._add_group(170.0, 150.0, 320.0, 240.0)
        direct_id = self.window.scene.add_node_from_type(
            LOGGER_TYPE_ID, x=520.0, y=240.0
        )
        nested_id = self.window.scene.add_node_from_type(
            LOGGER_TYPE_ID, x=230.0, y=220.0
        )
        outside_id = self.window.scene.add_node_from_type(
            LOGGER_TYPE_ID, x=980.0, y=240.0
        )
        self.window.scene.set_node_collapsed(outer_id, True)
        self.app.processEvents()

        graph_canvas.setProperty("nodeContextNodeId", outer_id)
        graph_canvas.setProperty("nodeContextVisible", True)
        self.app.processEvents()
        menu.actionTriggered.emit("open_comment_peek")
        self.app.processEvents()
        wait_for_condition_or_raise(
            lambda: self.window.scene.active_comment_peek_node_id == outer_id,
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Timed out waiting for comment peek.",
        )

        visible_nodes = self._payload_ids(self.window.scene.nodes_model)
        visible_backdrops = self._payload_ids(self.window.scene.backdrop_nodes_model)
        self.assertIn(direct_id, visible_nodes)
        self.assertIn(nested_id, visible_nodes)
        self.assertNotIn(outside_id, visible_nodes)
        self.assertEqual(visible_backdrops, {outer_id, inner_id})
        self.assertEqual(self.window.scene.active_scope_path, [])
        self.assertEqual(active_view.scope_path, [])

        self.window.scene.move_node(direct_id, 540.0, 260.0)
        self.app.processEvents()
        self.assertAlmostEqual(float(workspace.nodes[direct_id].x), 540.0)
        self.assertEqual(self.window.scene.active_comment_peek_node_id, outer_id)

        graph_canvas.setProperty("nodeContextNodeId", outer_id)
        graph_canvas.setProperty("nodeContextVisible", True)
        self.app.processEvents()
        self.assertIn("Exit Peek", _menu_action_texts(menu))
        menu.actionTriggered.emit("close_comment_peek")
        self.app.processEvents()
        wait_for_condition_or_raise(
            lambda: self.window.scene.active_comment_peek_node_id == "",
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Timed out waiting for explicit Exit Peek.",
        )

        self.assertTrue(self.window.scene.open_comment_peek(outer_id))
        self.app.processEvents()
        scene_point = graph_canvas.mapToScene(QPointF(12.0, 12.0))
        QTest.mouseClick(
            self.window.quick_widget,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(round(scene_point.x()), round(scene_point.y())),
        )
        self.app.processEvents()
        wait_for_condition_or_raise(
            lambda: self.window.scene.active_comment_peek_node_id == "",
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Timed out waiting for click-away dismissal.",
        )
        self.assertEqual(self.window.scene.active_scope_path, [])
        self.assertEqual(active_view.scope_path, [])


__all__ = ["MainWindowShellGroupBackdropIntegrationTests"]
