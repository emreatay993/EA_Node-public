from __future__ import annotations

import time
import unittest
from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, QPointF, Qt, QUrl, pyqtProperty, pyqtSignal
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtQuick import QQuickItem, QQuickWindow
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
from ea_node_editor.ui_qml.theme_bridge import ThemeBridge

GROUP_BACKDROP_TYPE_ID = "passive.annotation.group_backdrop"
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _walk_items(root: QObject) -> list[QQuickItem]:
    items: list[QQuickItem] = []

    def _visit(item: QObject) -> None:
        if not isinstance(item, QQuickItem):
            return
        items.append(item)
        for child in item.childItems():
            _visit(child)

    _visit(root)
    return items


def _named_child_items(root: QObject, object_name: str) -> list[QQuickItem]:
    return [item for item in _walk_items(root) if item.objectName() == object_name]


def _variant_value(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


def _node_host(canvas: QObject, node_id: str, *, object_name: str = "graphNodeCard") -> QQuickItem:
    normalized = str(node_id)
    for item in _named_child_items(canvas, object_name):
        payload = _variant_value(item.property("nodeData"))
        if isinstance(payload, dict) and str(payload.get("node_id", "")) == normalized:
            return item
    raise AssertionError(f"Could not find {object_name} for node {node_id!r}.")


def _scene_point(item: QQuickItem, x_factor: float = 0.5, y_factor: float = 0.5) -> QPoint:
    scene_point = item.mapToScene(QPointF(item.width() * x_factor, item.height() * y_factor))
    return QPoint(round(scene_point.x()), round(scene_point.y()))


def _wait_for(predicate, *, timeout_ms: int = 1000, app: QApplication, message: str) -> None:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    app.processEvents()
    if predicate():
        return
    raise AssertionError(message)


class _ViewportBridgeStub(QObject):
    view_state_changed = pyqtSignal()

    @pyqtProperty(float, constant=True)
    def center_x(self) -> float:
        return 0.0

    @pyqtProperty(float, constant=True)
    def center_y(self) -> float:
        return 0.0

    @pyqtProperty(float, constant=True)
    def zoom_value(self) -> float:
        return 1.0

    @pyqtProperty("QVariantMap", constant=True)
    def visible_scene_rect_payload(self) -> dict[str, float]:
        return {
            "x": -480.0,
            "y": -360.0,
            "width": 960.0,
            "height": 720.0,
        }

    @pyqtProperty("QVariantMap", constant=True)
    def visible_scene_rect_payload_cached(self) -> dict[str, float]:
        return self.visible_scene_rect_payload


class GroupBackdropLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.registry = build_default_registry()
        self.model = GraphModel()
        self.workspace_id = self.model.active_workspace.workspace_id
        self.scene = GraphSceneBridge()
        self.scene.set_workspace(self.model, self.registry, self.workspace_id)
        self.view = _ViewportBridgeStub()

    def test_graph_scene_bridge_splits_group_backdrops_into_dedicated_payload_model(self) -> None:
        logger_id = self.scene.add_node_from_type("core.logger", 40.0, 60.0)
        backdrop_id = self.scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, 20.0, 20.0)

        regular_ids = {item["node_id"] for item in self.scene.nodes_model}
        backdrop_ids = {item["node_id"] for item in self.scene.backdrop_nodes_model}
        minimap_ids = {item["node_id"] for item in self.scene.minimap_nodes_model}

        self.assertIn(logger_id, regular_ids)
        self.assertNotIn(backdrop_id, regular_ids)
        self.assertEqual(backdrop_ids, {backdrop_id})
        self.assertEqual(minimap_ids, {logger_id, backdrop_id})

        backdrop_payload = self.scene.backdrop_nodes_model[0]
        self.assertEqual(backdrop_payload["surface_family"], "group_backdrop")
        self.assertEqual(backdrop_payload["surface_variant"], "group_backdrop")
        self.assertEqual([port["key"] for port in backdrop_payload["ports"]], ["top", "right", "bottom", "left"])
        self.assertTrue(all(port["direction"] == "neutral" for port in backdrop_payload["ports"]))

    def test_graph_canvas_renders_group_backdrops_on_dedicated_under_edge_layer(self) -> None:
        logger_id = self.scene.add_node_from_type("core.logger", 40.0, 80.0)
        backdrop_id = self.scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, -40.0, 20.0)

        state_bridge = GraphCanvasStateBridge(scene_bridge=self.scene, view_bridge=self.view)
        command_bridge = GraphCanvasCommandBridge(scene_bridge=self.scene, view_bridge=self.view)

        engine = QQmlEngine()
        engine.rootContext().setContextProperty("themeBridge", ThemeBridge(theme_id="stitch_dark"))
        engine.rootContext().setContextProperty("graphThemeBridge", GraphThemeBridge(theme_id="graph_stitch_dark"))

        component = QQmlComponent(
            engine,
            QUrl.fromLocalFile(str(_REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "GraphCanvas.qml")),
        )
        if component.status() != QQmlComponent.Status.Ready:
            errors = "\n".join(error.toString() for error in component.errors())
            self.fail(f"Failed to load GraphCanvas.qml:\n{errors}")

        initial_properties = {
            "canvasStateBridge": state_bridge,
            "canvasCommandBridge": command_bridge,
            "width": 960.0,
            "height": 720.0,
        }
        if hasattr(component, "createWithInitialProperties"):
            canvas = component.createWithInitialProperties(initial_properties)
        else:
            canvas = component.create()
            for key, value in initial_properties.items():
                canvas.setProperty(key, value)
        self.addCleanup(lambda: canvas.deleteLater() if canvas is not None else None)
        if canvas is None:
            errors = "\n".join(error.toString() for error in component.errors())
            self.fail(f"Failed to instantiate GraphCanvas.qml:\n{errors}")

        window = QQuickWindow()
        self.addCleanup(window.deleteLater)
        window.resize(960, 720)
        canvas.setParentItem(window.contentItem())
        window.show()
        self.addCleanup(window.close)

        backdrop_layer = canvas.findChild(QObject, "graphCanvasBackdropLayer")
        edge_layer = canvas.findChild(QObject, "graphCanvasEdgeLayer")
        backdrop_input_layer = canvas.findChild(QObject, "graphCanvasBackdropInputLayer")
        world = canvas.findChild(QObject, "graphCanvasWorld")
        self.assertIsNotNone(backdrop_layer)
        self.assertIsNotNone(edge_layer)
        self.assertIsNotNone(backdrop_input_layer)
        self.assertIsNotNone(world)

        _wait_for(
            lambda: len(_named_child_items(canvas, "graphNodeCard")) == 2,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for graph canvas node hosts to appear.",
        )

        backdrop_host = _node_host(canvas, backdrop_id)
        backdrop_input_host = _node_host(canvas, backdrop_id, object_name="graphGroupBackdropInputCard")
        logger_host = _node_host(canvas, logger_id)

        self.assertIs(backdrop_host.parentItem(), backdrop_layer)
        self.assertIs(logger_host.parentItem(), world)
        self.assertFalse(bool(backdrop_host.property("showShadow")))
        self.assertFalse(bool(backdrop_input_host.property("showShadow")))
        self.assertTrue(bool(logger_host.property("showShadow")))
        self.assertFalse(bool(backdrop_host.property("_backgroundShadowVisible")))
        self.assertFalse(bool(backdrop_host.property("_shadowVisible")))
        self.assertEqual(state_bridge.backdrop_nodes_model, self.scene.backdrop_nodes_model)
        self.assertIsNotNone(backdrop_host.findChild(QObject, "graphNodeHeaderLayer"))
        self.assertIsNotNone(backdrop_host.findChild(QObject, "graphNodeResizeHandle"))
        self.assertEqual(backdrop_input_host.parentItem().objectName(), "graphCanvasBackdropInputLayer")
        self.assertEqual(len(_named_child_items(backdrop_host, "graphNodeInputPortMouseArea")), 0)
        self.assertEqual(len(_named_child_items(backdrop_host, "graphNodeOutputPortMouseArea")), 0)
        self.assertEqual(len(_named_child_items(backdrop_input_host, "graphNodeInputPortMouseArea")), 2)
        self.assertEqual(len(_named_child_items(backdrop_input_host, "graphNodeOutputPortMouseArea")), 2)

        layer_parent = backdrop_layer.parentItem()
        self.assertIs(layer_parent, edge_layer.parentItem())
        self.assertIs(layer_parent, backdrop_input_layer.parentItem())
        self.assertIs(layer_parent, world.parentItem())
        child_items = list(layer_parent.childItems())
        self.assertLess(child_items.index(backdrop_layer), child_items.index(edge_layer))
        self.assertLess(child_items.index(edge_layer), child_items.index(backdrop_input_layer))
        self.assertLess(child_items.index(backdrop_input_layer), child_items.index(world))
        self.assertLess(child_items.index(edge_layer), child_items.index(world))

        clicked: list[tuple[str, bool]] = []
        backdrop_input_host.nodeClicked.connect(lambda node_id, additive: clicked.append((str(node_id), bool(additive))))

        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            # Stay near the border so this verifies the backdrop layer host.
            _scene_point(backdrop_host, 0.1, 0.1),
        )
        _wait_for(
            lambda: bool(clicked),
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for group clicks to route through the dedicated layer host.",
        )

        self.assertEqual(clicked, [(backdrop_id, False)])


if __name__ == "__main__":
    unittest.main()
