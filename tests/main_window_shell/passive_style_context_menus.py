from __future__ import annotations

from unittest.mock import patch

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QColor
from PyQt6.QtQuick import QQuickItem

from ea_node_editor.ui.shell.graph_action_contracts import GraphActionId
from tests.main_window_shell.base import SharedMainWindowShellTestBase


def _menu_action_texts(menu: QObject) -> list[str]:
    actions = menu.property("visibleActions") or []
    if hasattr(actions, "toVariant"):
        actions = actions.toVariant()
    texts: list[str] = []
    for action in actions:
        if hasattr(action, "toVariant"):
            action = action.toVariant()
        if isinstance(action, dict):
            texts.append(str(action.get("text", "")))
    return texts


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


def _node_card_for(graph_canvas: QObject, node_id: str) -> QQuickItem | None:
    for item in _named_child_items(graph_canvas, "graphNodeCard"):
        node_data = item.property("nodeData")
        if isinstance(node_data, dict) and str(node_data.get("node_id", "")) == str(node_id):
            return item
    return None


class MainWindowShellPassiveStyleContextMenuTests(SharedMainWindowShellTestBase):
    def test_passive_node_context_menu_exposes_style_actions_only_for_supported_passive_nodes(self) -> None:
        graph_canvas = self._graph_canvas_item()
        node_context_popup = graph_canvas.findChild(QObject, "graphCanvasNodeContextPopup")
        self.assertIsNotNone(node_context_popup)

        passive_id = self.window.scene.add_node_from_type("passive.planning.task_card", 120.0, 80.0)
        text_id = self.window.scene.add_node_from_type("passive.annotation.text", 320.0, 80.0)
        standard_id = self.window.scene.add_node_from_type("core.logger", 420.0, 80.0)
        self.app.processEvents()

        graph_canvas.setProperty("nodeContextNodeId", passive_id)
        self.app.processEvents()
        passive_actions = _menu_action_texts(node_context_popup)
        self.assertIn("Edit Style...", passive_actions)
        self.assertIn("Reset Style", passive_actions)
        self.assertIn("Copy Style", passive_actions)
        self.assertIn("Paste Style", passive_actions)
        self.assertIn("Propagate Style", passive_actions)

        graph_canvas.setProperty("nodeContextNodeId", text_id)
        self.app.processEvents()
        text_actions = _menu_action_texts(node_context_popup)
        self.assertNotIn("Edit Style...", text_actions)
        self.assertNotIn("Reset Style", text_actions)
        self.assertNotIn("Copy Style", text_actions)
        self.assertNotIn("Paste Style", text_actions)
        self.assertNotIn("Propagate Style", text_actions)

        graph_canvas.setProperty("nodeContextNodeId", standard_id)
        self.app.processEvents()
        standard_actions = _menu_action_texts(node_context_popup)
        self.assertNotIn("Edit Style...", standard_actions)
        self.assertNotIn("Reset Style", standard_actions)
        self.assertNotIn("Copy Style", standard_actions)
        self.assertNotIn("Paste Style", standard_actions)
        self.assertNotIn("Propagate Style", standard_actions)
        graph_canvas.setProperty("nodeContextNodeId", "")
        graph_canvas.setProperty("nodeContextVisible", False)
        self.app.processEvents()

    def test_flow_edge_context_menu_leaves_flow_style_actions_to_toolbar(self) -> None:
        graph_canvas = self._graph_canvas_item()
        edge_context_popup = graph_canvas.findChild(QObject, "graphCanvasEdgeContextPopup")
        self.assertIsNotNone(edge_context_popup)

        source_id = self.window.scene.add_node_from_type("passive.flowchart.process", 80.0, 60.0)
        target_id = self.window.scene.add_node_from_type("passive.flowchart.decision", 360.0, 60.0)
        flow_edge_id = self.window.scene.add_edge(source_id, "top", target_id, "bottom")

        constant_id = self.window.scene.add_node_from_type("core.constant", 80.0, 260.0)
        logger_id = self.window.scene.add_node_from_type("core.logger", 380.0, 260.0)
        data_edge_id = self.window.scene.add_edge(constant_id, "as_text", logger_id, "message")
        self.app.processEvents()

        graph_canvas.setProperty("edgeContextEdgeId", flow_edge_id)
        self.app.processEvents()
        flow_actions = _menu_action_texts(edge_context_popup)
        self.assertIn("Path: Auto", flow_actions)
        self.assertIn("Path: Pipe", flow_actions)
        self.assertIn("Path: Bezier", flow_actions)
        self.assertNotIn("Edit Flow Edge...", flow_actions)
        self.assertNotIn("Edit Label...", flow_actions)
        self.assertNotIn("Reset Style", flow_actions)
        self.assertNotIn("Copy Style", flow_actions)
        self.assertNotIn("Paste Style", flow_actions)
        self.assertIn("Remove Connection", flow_actions)

        graph_canvas.setProperty("edgeContextEdgeId", data_edge_id)
        self.app.processEvents()
        data_actions = _menu_action_texts(edge_context_popup)
        self.assertIn("Path: Auto", data_actions)
        self.assertIn("Path: Pipe", data_actions)
        self.assertIn("Path: Bezier", data_actions)
        self.assertNotIn("Edit Flow Edge...", data_actions)
        self.assertNotIn("Edit Label...", data_actions)
        self.assertNotIn("Reset Style", data_actions)
        self.assertNotIn("Copy Style", data_actions)
        self.assertNotIn("Paste Style", data_actions)
        graph_canvas.setProperty("edgeContextEdgeId", "")
        graph_canvas.setProperty("edgeContextVisible", False)
        self.app.processEvents()

    def test_graph_action_bridge_routes_style_to_graph_canvas_host_presenter(self) -> None:
        workspace = self.window.model.project.workspaces[self.window.workspace_manager.active_workspace_id()]
        node_id = self.window.scene.add_node_from_type("passive.annotation.sticky_note", 120.0, 80.0)
        self.app.processEvents()
        style = {
            "fill_color": "#112233",
            "text_color": "#F0F4FB",
            "border_width": 2.0,
            "corner_radius": 18.0,
        }

        with patch.object(
            self.window.graph_canvas_host_presenter,
            "edit_passive_node_style",
            return_value=style,
        ) as edit_style:
            self.assertTrue(
                self.window.graph_action_bridge.trigger_graph_action(
                    GraphActionId.EDIT_PASSIVE_NODE_STYLE.value,
                    {"node_id": node_id},
                )
            )

        edit_style.assert_called_once_with(node_id)
        self.assertEqual(workspace.nodes[node_id].visual_style, style)
        self.app.processEvents()
        card = _node_card_for(self._graph_canvas_item(), node_id)
        self.assertIsNotNone(card)
        self.assertEqual(QColor(card.property("color")).name(), "#112233")
        self.assertEqual(QColor(card.property("headerTextColor")).name(), "#f0f4fb")
        self.assertEqual(int(round(float(card.property("radius")))), 18)
