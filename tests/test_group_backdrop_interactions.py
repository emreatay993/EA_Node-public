from __future__ import annotations

import time
import unittest
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtQuick import QQuickItem, QQuickWindow
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
from ea_node_editor.ui_qml.theme_bridge import ThemeBridge
from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

GROUP_BACKDROP_TYPE_ID = "passive.annotation.group_backdrop"
LOGGER_TYPE_ID = "core.logger"
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
            "x": -640.0,
            "y": -480.0,
            "width": 1280.0,
            "height": 960.0,
        }

    @pyqtProperty("QVariantMap", constant=True)
    def visible_scene_rect_payload_cached(self) -> dict[str, float]:
        return self.visible_scene_rect_payload


class GroupBackdropInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.registry = build_default_registry()
        self.model = GraphModel()
        self.workspace_id = self.model.active_workspace.workspace_id
        self.scene = GraphSceneBridge()
        self.scene.set_workspace(self.model, self.registry, self.workspace_id)
        self.history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(self.history)
        self.view = _ViewportBridgeStub()
        self._canvas_refs: list[object] = []

    def _workspace(self):
        return self.model.project.workspaces[self.workspace_id]

    def _workspace_node(self, node_id: str):
        return self._workspace().nodes[node_id]

    def _scene_payload(self, node_id: str) -> dict[str, object]:
        for payload in [*self.scene.nodes_model, *self.scene.backdrop_nodes_model]:
            if str(payload["node_id"]) == str(node_id):
                return payload
        raise AssertionError(f"Node payload {node_id!r} was not found.")

    def _add_group_backdrop(self, x: float, y: float, width: float, height: float) -> str:
        node_id = self.scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, x, y)
        self.scene.set_node_geometry(node_id, x, y, width, height)
        return node_id

    def _create_canvas(self) -> tuple[QObject, QQuickWindow]:
        state_bridge = GraphCanvasStateBridge(scene_bridge=self.scene, view_bridge=self.view)
        command_bridge = GraphCanvasCommandBridge(scene_bridge=self.scene, view_bridge=self.view)

        engine = QQmlEngine()
        engine.rootContext().setContextProperty("themeBridge", ThemeBridge(theme_id="stitch_dark"))
        engine.rootContext().setContextProperty("graphThemeBridge", GraphThemeBridge(theme_id="graph_stitch_dark"))
        self.addCleanup(engine.deleteLater)
        self._canvas_refs.extend([state_bridge, command_bridge, engine])

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
            "width": 1280.0,
            "height": 960.0,
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
        window.resize(1280, 960)
        canvas.setParentItem(window.contentItem())
        window.show()
        self.addCleanup(window.close)
        self.addCleanup(window.deleteLater)
        return canvas, window

    def test_graph_canvas_group_backdrop_allows_edge_click_passthrough(self) -> None:
        backdrop_id = self._add_group_backdrop(-560.0, -420.0, 1120.0, 840.0)
        source_id = self.scene.add_node_from_type("core.constant", -460.0, -340.0)
        target_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 120.0, -320.0)
        edge_id = self.scene.add_edge(source_id, "value", target_id, "message")
        second_source_id = self.scene.add_node_from_type("core.constant", -460.0, 240.0)
        second_target_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 120.0, 260.0)
        second_edge_id = self.scene.add_edge(
            second_source_id,
            "value",
            second_target_id,
            "message",
        )

        canvas, window = self._create_canvas()

        _wait_for(
            lambda: len(_named_child_items(canvas, "graphGroupBackdropInputCard")) == 1,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for the group input host to appear.",
        )
        edge_layer = canvas.findChild(QObject, "graphCanvasEdgeLayer")
        self.assertIsNotNone(edge_layer)
        backdrop_input_host = _node_host(canvas, backdrop_id, object_name="graphGroupBackdropInputCard")
        backdrop_drag_area = backdrop_input_host.findChild(QObject, "graphNodeDragArea")
        self.assertIsNotNone(backdrop_drag_area)
        backdrop_clicks: list[tuple[str, bool]] = []
        backdrop_input_host.nodeClicked.connect(
            lambda node_id, additive: backdrop_clicks.append((str(node_id), bool(additive)))
        )

        def _edge_click_point(candidate_edge_id: str) -> QPoint | None:
            snapshot = _variant_value(edge_layer._visibleEdgeSnapshot(candidate_edge_id))
            if not isinstance(snapshot, dict):
                return None
            geometry = _variant_value(snapshot.get("geometry"))
            if not isinstance(geometry, dict):
                return None
            anchor = _variant_value(edge_layer._edgeAnchor(geometry, 0.5))
            if not isinstance(anchor, dict):
                return None
            screen_x = float(edge_layer.sceneToScreenX(float(anchor["x"])))
            screen_y = float(edge_layer.sceneToScreenY(float(anchor["y"])))
            point = QPoint(round(screen_x), round(screen_y))
            if str(edge_layer.edgeAtScreen(point.x(), point.y())) != candidate_edge_id:
                return None
            return point

        click_points: dict[str, QPoint] = {}

        def _edge_ready() -> bool:
            first_point = _edge_click_point(edge_id)
            second_point = _edge_click_point(second_edge_id)
            if first_point is None or second_point is None:
                return False
            click_points[edge_id] = first_point
            click_points[second_edge_id] = second_point
            return True

        _wait_for(
            _edge_ready,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for the edge inside the group to become hittable.",
        )

        QTest.mouseMove(window, click_points[edge_id])
        _wait_for(
            lambda: backdrop_drag_area.property("cursorShape") == Qt.CursorShape.ArrowCursor,
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for edge hover inside the backdrop to use the edge cursor.",
        )

        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            click_points[edge_id],
        )
        _wait_for(
            lambda: _variant_value(canvas.property("selectedEdgeIds")) == [edge_id],
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for the edge click inside the backdrop to select the edge.",
        )
        self.assertEqual(backdrop_clicks, [])
        self.assertEqual(
            str(
                edge_layer.edgeAtScreen(
                    click_points[second_edge_id].x(),
                    click_points[second_edge_id].y(),
                )
            ),
            second_edge_id,
        )

        QTest.mouseMove(window, click_points[second_edge_id])
        self.app.processEvents()
        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ShiftModifier,
            click_points[second_edge_id],
        )
        _wait_for(
            lambda: _variant_value(canvas.property("selectedEdgeIds")) == [edge_id, second_edge_id],
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for Shift-click to add the second edge.",
        )

        QTest.mouseMove(window, click_points[edge_id])
        self.app.processEvents()
        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ShiftModifier,
            click_points[edge_id],
        )
        _wait_for(
            lambda: _variant_value(canvas.property("selectedEdgeIds")) == [second_edge_id],
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for Shift-click to toggle the first edge off.",
        )

        backdrop_body_point = QPoint(
            round(float(canvas.sceneToScreenX(-520.0))),
            round(float(canvas.sceneToScreenY(-380.0))),
        )
        self.assertEqual(str(edge_layer.edgeAtScreen(backdrop_body_point.x(), backdrop_body_point.y())), "")

        QTest.mouseMove(window, backdrop_body_point)
        _wait_for(
            lambda: backdrop_drag_area.property("cursorShape") == Qt.CursorShape.OpenHandCursor,
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for empty backdrop hover to keep the drag cursor.",
        )

        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            backdrop_body_point,
        )
        _wait_for(
            lambda: backdrop_clicks == [(backdrop_id, False)],
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for a non-edge backdrop click to select the backdrop.",
        )
        self.assertEqual(_variant_value(canvas.property("selectedEdgeIds")), [])

    def test_graph_canvas_wire_marquee_hidden_reveal_and_endpoint_navigation(self) -> None:
        self.view = ViewportBridge()
        self.view.set_viewport_size(1280.0, 960.0)
        source_id = self.scene.add_node_from_type("core.constant", -460.0, -180.0)
        target_id = self.scene.add_node_from_type("core.python_script", 120.0, -160.0)
        edge_id = self.scene.add_edge(source_id, "value", target_id, "payload")
        hidden_source_id = self.scene.add_node_from_type("core.constant", -460.0, 120.0)
        hidden_target_id = self.scene.add_node_from_type("core.python_script", 120.0, 140.0)
        hidden_edge_id = self.scene.add_edge(
            hidden_source_id,
            "value",
            hidden_target_id,
            "payload",
        )
        self.assertTrue(self.scene.set_edges_display_mode([hidden_edge_id], "hidden"))

        canvas, window = self._create_canvas()
        edge_layer = canvas.findChild(QObject, "graphCanvasEdgeLayer")
        menus = canvas.findChild(QObject, "graphCanvasContextMenus")
        self.assertIsNotNone(edge_layer)
        self.assertIsNotNone(menus)

        def _edge_anchor(edge: str, fraction: float = 0.5) -> QPoint | None:
            snapshot = _variant_value(edge_layer._visibleEdgeSnapshot(edge))
            geometry = _variant_value(snapshot.get("geometry")) if isinstance(snapshot, dict) else None
            if not isinstance(geometry, dict):
                return None
            anchor = _variant_value(edge_layer._edgeAnchor(geometry, fraction))
            if not isinstance(anchor, dict):
                return None
            return QPoint(
                round(float(edge_layer.sceneToScreenX(float(anchor["x"])))),
                round(float(edge_layer.sceneToScreenY(float(anchor["y"])))),
            )

        anchors: dict[str, QPoint] = {}

        def _edges_ready() -> bool:
            default_anchor = _edge_anchor(edge_id)
            hidden_anchor = _edge_anchor(hidden_edge_id)
            if default_anchor is None or hidden_anchor is None:
                return False
            anchors[edge_id] = default_anchor
            anchors[hidden_edge_id] = hidden_anchor
            return True

        _wait_for(
            _edges_ready,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for wire-marquee edge geometry.",
        )
        self.assertEqual(
            str(edge_layer.edgeAtScreen(anchors[hidden_edge_id].x(), anchors[hidden_edge_id].y())),
            "",
        )

        def _wire_marquee(center: QPoint, modifiers: Qt.KeyboardModifier, expected: list[str]) -> None:
            start = QPoint(center.x() - 34, center.y() - 22)
            end = QPoint(center.x() + 34, center.y() + 22)
            canvas.forceActiveFocus()
            QTest.keyPress(window, Qt.Key.Key_W)
            _wait_for(
                lambda: bool(canvas.property("wireSelectionModeHeld")),
                timeout_ms=500,
                app=self.app,
                message="Timed out waiting for held-W wire selection mode.",
            )
            QTest.mousePress(window, Qt.MouseButton.LeftButton, modifiers, start)
            QTest.mouseMove(window, end)
            _wait_for(
                lambda: _variant_value(canvas.property("selectedEdgeIds")) == expected,
                timeout_ms=500,
                app=self.app,
                message="Timed out waiting for live wire-marquee selection.",
            )
            marquee = canvas.findChild(QObject, "graphCanvasMarqueeRect")
            self.assertIsNotNone(marquee)
            self.assertTrue(bool(marquee.property("visible")))
            QTest.mouseRelease(window, Qt.MouseButton.LeftButton, modifiers, end)
            QTest.keyRelease(window, Qt.Key.Key_W)
            _wait_for(
                lambda: not bool(canvas.property("wireSelectionModeHeld")),
                timeout_ms=500,
                app=self.app,
                message="Timed out waiting for held-W mode to clear.",
            )
            self.assertEqual(_variant_value(canvas.property("selectedEdgeIds")), expected)

        _wire_marquee(
            anchors[edge_id],
            Qt.KeyboardModifier.NoModifier,
            [edge_id],
        )
        _wire_marquee(
            anchors[hidden_edge_id],
            Qt.KeyboardModifier.ShiftModifier,
            [edge_id, hidden_edge_id],
        )
        def _hidden_wire_revealed() -> bool:
            snapshot = _variant_value(edge_layer._visibleEdgeSnapshot(hidden_edge_id))
            return bool(
                isinstance(snapshot, dict)
                and snapshot.get("selected")
                and not snapshot.get("hiddenUnrevealed", True)
            )

        _wait_for(
            _hidden_wire_revealed,
            timeout_ms=1000,
            app=self.app,
            message="Timed out waiting for the selected hidden wire to reveal its full route.",
        )

        focus_sink = QQuickItem(window.contentItem())
        focus_sink.setParentItem(window.contentItem())
        focus_sink.setFocus(True)
        window.requestActivate()
        _wait_for(
            window.isActive,
            timeout_ms=500,
            app=self.app,
            message="Timed out activating the graph window.",
        )
        canvas.forceActiveFocus()
        QTest.keyPress(window, Qt.Key.Key_W)
        _wait_for(
            lambda: bool(canvas.property("wireSelectionModeHeld")),
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for W mode before focus loss.",
        )
        focus_sink.forceActiveFocus()
        _wait_for(
            lambda: not bool(canvas.property("wireSelectionModeHeld")),
            timeout_ms=500,
            app=self.app,
            message="Held-W wire selection survived canvas focus loss.",
        )
        QTest.keyRelease(window, Qt.Key.Key_W)

        canvas.forceActiveFocus()
        QTest.keyPress(window, Qt.Key.Key_W)
        _wait_for(
            lambda: bool(canvas.property("wireSelectionModeHeld")),
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for W mode before window deactivation.",
        )
        other_window = QQuickWindow()
        other_window.resize(200, 120)
        other_window.show()
        other_window.requestActivate()
        _wait_for(
            lambda: other_window.isActive()
            and not window.isActive()
            and not bool(canvas.property("wireSelectionModeHeld")),
            timeout_ms=500,
            app=self.app,
            message="Held-W wire selection survived window deactivation.",
        )
        other_window.close()
        other_window.deleteLater()
        window.requestActivate()
        _wait_for(
            window.isActive,
            timeout_ms=500,
            app=self.app,
            message="Timed out reactivating the graph window.",
        )
        canvas.forceActiveFocus()
        QTest.keyRelease(window, Qt.Key.Key_W)
        self.app.processEvents()

        canvas.setProperty("selectedEdgeIds", [edge_id])
        canvas.forceActiveFocus()
        source_point = _variant_value(edge_layer.edgeEndpointScenePoint(edge_id, "source"))
        target_point = _variant_value(edge_layer.edgeEndpointScenePoint(edge_id, "target"))
        self.assertIsInstance(source_point, dict)
        self.assertIsInstance(target_point, dict)
        original_zoom = self.view.zoom_value

        canvas._openEdgeContext(edge_id, anchors[edge_id].x(), anchors[edge_id].y())
        self.assertTrue(bool(menus._handleEdgeNavigationAction("jump_edge_start")))
        _wait_for(
            lambda: (
                abs(self.view.center_x - float(source_point["x"])) < 0.01
                and abs(self.view.center_y - float(source_point["y"])) < 0.01
            ),
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for Jump to Start.",
        )
        self.assertEqual(self.view.zoom_value, original_zoom)
        self.assertEqual(_variant_value(canvas.property("selectedEdgeIds")), [edge_id])

        QTest.keyClick(window, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
        _wait_for(
            lambda: (
                abs(self.view.center_x - float(target_point["x"])) < 0.01
                and abs(self.view.center_y - float(target_point["y"])) < 0.01
            ),
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for Ctrl+Right endpoint navigation.",
        )
        self.assertEqual(self.view.zoom_value, original_zoom)
        self.assertEqual(_variant_value(canvas.property("selectedEdgeIds")), [edge_id])

        center_before_rejected_jump = (self.view.center_x, self.view.center_y)
        canvas.setProperty("selectedEdgeIds", [edge_id, hidden_edge_id])

        def _send_ctrl_arrow(key: Qt.Key) -> bool:
            event = QKeyEvent(
                QEvent.Type.KeyPress,
                key,
                Qt.KeyboardModifier.ControlModifier,
            )
            event.setAccepted(False)
            QApplication.sendEvent(window, event)
            self.app.processEvents()
            return event.isAccepted()

        canvas.forceActiveFocus()
        self.assertFalse(_send_ctrl_arrow(Qt.Key.Key_Left))
        self.app.processEvents()
        self.assertEqual((self.view.center_x, self.view.center_y), center_before_rejected_jump)

        canvas.setProperty("selectedEdgeIds", [])
        self.assertFalse(_send_ctrl_arrow(Qt.Key.Key_Right))
        self.assertEqual((self.view.center_x, self.view.center_y), center_before_rejected_jump)

        focus_sink.forceActiveFocus()
        self.assertFalse(_send_ctrl_arrow(Qt.Key.Key_Left))
        self.assertEqual((self.view.center_x, self.view.center_y), center_before_rejected_jump)
        focus_sink.deleteLater()

    def test_graph_canvas_group_backdrop_live_drag_offsets_visual_and_input_hosts(self) -> None:
        backdrop_id = self._add_group_backdrop(40.0, 40.0, 760.0, 420.0)
        self.scene.select_node(backdrop_id, False)
        canvas, _window = self._create_canvas()

        _wait_for(
            lambda: len(_named_child_items(canvas, "graphGroupBackdropInputCard")) == 1,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for the group input host to appear.",
        )
        backdrop_visual_host = _node_host(canvas, backdrop_id)
        backdrop_input_host = _node_host(canvas, backdrop_id, object_name="graphGroupBackdropInputCard")

        backdrop_input_host.dragOffsetChanged.emit(backdrop_id, 64.0, 48.0)

        _wait_for(
            lambda: (
                abs(float(backdrop_visual_host.property("liveDragDx")) - 64.0) < 0.01
                and abs(float(backdrop_visual_host.property("liveDragDy")) - 48.0) < 0.01
                and abs(float(backdrop_input_host.property("liveDragDx")) - 64.0) < 0.01
                and abs(float(backdrop_input_host.property("liveDragDy")) - 48.0) < 0.01
            ),
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for group live-drag offsets to reach both hosts.",
        )
        self.assertTrue(_variant_value(canvas.property("liveDragNodeLookup"))[backdrop_id])
        self.assertAlmostEqual(float(canvas.property("liveDragDx")), 64.0)
        self.assertAlmostEqual(float(canvas.property("liveDragDy")), 48.0)

        backdrop_input_host.dragCanceled.emit(backdrop_id)

        _wait_for(
            lambda: (
                abs(float(backdrop_visual_host.property("liveDragDx"))) < 0.01
                and abs(float(backdrop_visual_host.property("liveDragDy"))) < 0.01
                and abs(float(backdrop_input_host.property("liveDragDx"))) < 0.01
                and abs(float(backdrop_input_host.property("liveDragDy"))) < 0.01
            ),
            timeout_ms=500,
            app=self.app,
            message="Timed out waiting for group live-drag offsets to clear from both hosts.",
        )

    def test_graph_canvas_scene_state_redraws_group_backdrop_live_resize_only_for_connected_ports(self) -> None:
        class _EdgeLayerCounter(QObject):
            def __init__(self) -> None:
                super().__init__()
                self.request_count = 0

            @pyqtSlot()
            def requestRedraw(self) -> None:
                self.request_count += 1

        class _SceneStateBridgeStub(QObject):
            def __init__(self, nodes_model: list[dict], backdrop_nodes_model: list[dict]) -> None:
                super().__init__()
                self._nodes_model = list(nodes_model)
                self._backdrop_nodes_model = list(backdrop_nodes_model)

            @pyqtProperty("QVariantList", constant=True)
            def nodes_model(self) -> list[dict]:
                return self._nodes_model

            @pyqtProperty("QVariantList", constant=True)
            def backdrop_nodes_model(self) -> list[dict]:
                return self._backdrop_nodes_model

        class _CanvasItemStub(QObject):
            def __init__(self, scene_state_bridge: QObject) -> None:
                super().__init__()
                self._scene_state_bridge = scene_state_bridge

            @pyqtProperty(QObject, constant=True)
            def _canvasSceneStateBridgeRef(self) -> QObject:
                return self._scene_state_bridge

            @pyqtProperty("QVariantList", constant=True)
            def edgePayload(self) -> list[dict]:
                return []

        graph_canvas_scene_state_qml = (
            _REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph_canvas"
            / "GraphCanvasSceneState.qml"
        )
        standard_payload = {
            "node_id": "standard_resize_node",
            "surface_family": "standard",
            "ports": [
                {
                    "key": "payload",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "any",
                    "data_access": "item",
                    "connected": False,
                },
                {
                    "key": "result",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "any",
                    "data_access": "item",
                    "connected": False,
                },
            ],
        }

        def _group_backdrop_ports(connected_key: str = "") -> list[dict]:
            ports: list[dict] = []
            for key in ("top", "right", "bottom", "left"):
                ports.append(
                    {
                        "key": key,
                        "direction": "neutral",
                        "kind": "flow",
                        "data_type": "flow",
                        "side": key,
                        "exposed": True,
                        "allow_multiple_connections": True,
                        "connected": key == connected_key,
                        "connection_count": 1 if key == connected_key else 0,
                    }
                )
            return ports

        group_backdrop_payload = {
            "node_id": "group_backdrop_resize_node",
            "surface_family": "group_backdrop",
            "surface_variant": "group_backdrop",
            "ports": _group_backdrop_ports(),
        }
        connected_group_backdrop_payload = {
            "node_id": "connected_group_backdrop_resize_node",
            "surface_family": "group_backdrop",
            "surface_variant": "group_backdrop",
            "ports": _group_backdrop_ports("right"),
        }

        scene_state_bridge = _SceneStateBridgeStub(
            [standard_payload],
            [group_backdrop_payload, connected_group_backdrop_payload],
        )
        canvas_item = _CanvasItemStub(scene_state_bridge)
        edge_counter = _EdgeLayerCounter()

        engine = QQmlEngine()
        self.addCleanup(engine.deleteLater)
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(graph_canvas_scene_state_qml)))
        if component.status() != QQmlComponent.Status.Ready:
            errors = "\n".join(error.toString() for error in component.errors())
            self.fail(f"Failed to load GraphCanvasSceneState.qml:\n{errors}")
        state = component.createWithInitialProperties(
            {
                "canvasItem": canvas_item,
                "edgeLayerItem": edge_counter,
            }
        )
        self.addCleanup(lambda: state.deleteLater() if state is not None else None)
        if state is None:
            errors = "\n".join(error.toString() for error in component.errors())
            self.fail(f"Failed to instantiate GraphCanvasSceneState.qml:\n{errors}")

        state.setLiveNodeGeometry("group_backdrop_resize_node", 18.0, 26.0, 320.0, 180.0, True)
        self.app.processEvents()
        self.assertEqual(
            _variant_value(state.property("liveNodeGeometry"))["group_backdrop_resize_node"],
            {
                "x": 18.0,
                "y": 26.0,
                "width": 320.0,
                "height": 180.0,
            },
        )
        self.assertEqual(edge_counter.request_count, 0)

        state.setLiveNodeGeometry("group_backdrop_resize_node", 18.0, 26.0, 320.0, 180.0, False)
        self.app.processEvents()
        self.assertEqual(_variant_value(state.property("liveNodeGeometry")), {})
        self.assertEqual(edge_counter.request_count, 0)

        state.setLiveNodeGeometry("connected_group_backdrop_resize_node", 24.0, 34.0, 380.0, 220.0, True)
        self.app.processEvents()
        self.assertEqual(
            _variant_value(state.property("liveNodeGeometry"))["connected_group_backdrop_resize_node"],
            {
                "x": 24.0,
                "y": 34.0,
                "width": 380.0,
                "height": 220.0,
            },
        )
        self.assertEqual(edge_counter.request_count, 1)

        state.setLiveNodeGeometry("connected_group_backdrop_resize_node", 24.0, 34.0, 380.0, 220.0, False)
        self.app.processEvents()
        self.assertEqual(_variant_value(state.property("liveNodeGeometry")), {})
        self.assertEqual(edge_counter.request_count, 2)

        state.setLiveNodeGeometry("standard_resize_node", 42.0, 64.0, 260.0, 120.0, True)
        self.app.processEvents()
        self.assertEqual(
            _variant_value(state.property("liveNodeGeometry"))["standard_resize_node"],
            {
                "x": 42.0,
                "y": 64.0,
                "width": 260.0,
                "height": 120.0,
            },
        )
        self.assertEqual(edge_counter.request_count, 3)

        state.setLiveNodeGeometry("standard_resize_node", 42.0, 64.0, 260.0, 120.0, False)
        self.app.processEvents()
        self.assertEqual(_variant_value(state.property("liveNodeGeometry")), {})
        self.assertEqual(edge_counter.request_count, 4)

    def test_graph_canvas_dragging_group_backdrop_moves_nested_descendants_once_and_preserves_selection(self) -> None:
        outer_id = self._add_group_backdrop(40.0, 40.0, 760.0, 520.0)
        inner_id = self._add_group_backdrop(140.0, 130.0, 320.0, 240.0)
        inner_logger_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 190.0, 180.0)
        outer_logger_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 520.0, 260.0)
        outside_logger_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 880.0, 220.0)

        self.assertEqual(self._scene_payload(inner_id)["owner_backdrop_id"], outer_id)
        self.assertEqual(self._scene_payload(inner_logger_id)["owner_backdrop_id"], inner_id)
        self.assertEqual(self._scene_payload(outer_logger_id)["owner_backdrop_id"], outer_id)
        self.assertEqual(self._scene_payload(outside_logger_id)["owner_backdrop_id"], "")

        self.scene.select_node(outer_id, False)
        self.history.clear_workspace(self.workspace_id)
        workspace = self._workspace()
        canvas, _window = self._create_canvas()

        _wait_for(
            lambda: len(_named_child_items(canvas, "graphGroupBackdropInputCard")) == 2,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for group input hosts to appear.",
        )
        outer_input_host = _node_host(canvas, outer_id, object_name="graphGroupBackdropInputCard")
        drag_node_ids = list(_variant_value(canvas.dragNodeIdsForAnchor(outer_id)) or [])
        self.assertEqual(drag_node_ids[0], outer_id)
        self.assertEqual(set(drag_node_ids), {outer_id, inner_id, inner_logger_id, outer_logger_id})

        outer_input_host.dragFinished.emit(outer_id, 120.0, 90.0, True)

        _wait_for(
            lambda: abs(float(workspace.nodes[outer_id].x) - 120.0) < 0.01,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for backdrop drag to commit.",
        )

        self.assertAlmostEqual(float(workspace.nodes[outer_id].x), 120.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].y), 90.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_id].x), 220.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_id].y), 180.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_logger_id].x), 270.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_logger_id].y), 230.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_logger_id].x), 600.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_logger_id].y), 310.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outside_logger_id].x), 880.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outside_logger_id].y), 220.0, places=6)
        self.assertEqual(self.scene.selected_node_lookup, {outer_id: True})
        self.assertEqual(self._scene_payload(inner_id)["owner_backdrop_id"], outer_id)
        self.assertEqual(self._scene_payload(inner_logger_id)["owner_backdrop_id"], inner_id)
        self.assertEqual(self.history.undo_depth(self.workspace_id), 1)

        self.assertIsNotNone(self.history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].x), 40.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].y), 40.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_id].x), 140.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_id].y), 130.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_logger_id].x), 190.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_logger_id].y), 180.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_logger_id].x), 520.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_logger_id].y), 260.0, places=6)

        self.assertIsNotNone(self.history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].x), 120.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].y), 90.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_id].x), 220.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_id].y), 180.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_logger_id].x), 270.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_logger_id].y), 230.0, places=6)

    def test_graph_canvas_live_resize_mirrors_geometry_without_group_shadow(self) -> None:
        backdrop_id = self._add_group_backdrop(160.0, 120.0, 380.0, 260.0)
        self.scene.select_node(backdrop_id, False)
        workspace = self._workspace()
        canvas, _window = self._create_canvas()

        _wait_for(
            lambda: len(_named_child_items(canvas, "graphGroupBackdropInputCard")) == 1,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for the selected group input host to appear.",
        )

        backdrop_host = _node_host(canvas, backdrop_id)
        backdrop_input_host = _node_host(canvas, backdrop_id, object_name="graphGroupBackdropInputCard")
        preview_shadow = backdrop_host.findChild(QObject, "graphGroupBackdropLivePreviewShadow")
        surface = backdrop_input_host.findChild(QObject, "graphNodeGroupBackdropSurface")
        self.assertIsNone(backdrop_input_host.findChild(QObject, "graphGroupBackdropBodyEditor"))
        self.assertIsNone(backdrop_input_host.findChild(QObject, "graphNodeGroupBackdropBodyText"))
        self.assertIsNone(preview_shadow)
        self.assertIsNotNone(surface)
        self.assertFalse(bool(backdrop_host.property("_shadowVisible")))
        self.assertFalse(bool(backdrop_host.property("_backgroundShadowVisible")))

        backdrop_input_host.resizePreviewChanged.emit(backdrop_id, 190.0, 140.0, 420.0, 310.0, True)

        _wait_for(
            lambda: (
                bool(backdrop_host.property("_liveGeometryActive"))
                and bool(backdrop_input_host.property("_liveGeometryActive"))
            ),
            timeout_ms=1000,
            app=self.app,
            message="Timed out waiting for group live-resize preview to activate.",
        )

        live_geometry = _variant_value(canvas.property("liveNodeGeometry"))
        self.assertEqual(
            live_geometry[backdrop_id],
            {
                "x": 190.0,
                "y": 140.0,
                "width": 420.0,
                "height": 310.0,
            },
        )
        self.assertAlmostEqual(float(backdrop_host.property("_liveX")), 190.0, places=6)
        self.assertAlmostEqual(float(backdrop_host.property("_liveY")), 140.0, places=6)
        self.assertAlmostEqual(float(backdrop_host.property("_liveWidth")), 420.0, places=6)
        self.assertAlmostEqual(float(backdrop_host.property("_liveHeight")), 310.0, places=6)
        self.assertAlmostEqual(float(backdrop_input_host.property("_liveWidth")), 420.0, places=6)
        self.assertAlmostEqual(float(backdrop_input_host.property("_liveHeight")), 310.0, places=6)
        self.assertFalse(bool(backdrop_host.property("_shadowVisible")))
        self.assertFalse(bool(backdrop_host.property("_backgroundShadowVisible")))

        backdrop_input_host.resizeFinished.emit(backdrop_id, 190.0, 140.0, 420.0, 310.0)

        _wait_for(
            lambda: (
                _variant_value(canvas.property("liveNodeGeometry")) == {}
                and abs(float(workspace.nodes[backdrop_id].x) - 190.0) < 0.01
                and abs(float(workspace.nodes[backdrop_id].y) - 140.0) < 0.01
            ),
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for group live-resize preview to settle.",
        )

        refreshed_backdrop_host = _node_host(canvas, backdrop_id)
        refreshed_backdrop_input_host = _node_host(canvas, backdrop_id, object_name="graphGroupBackdropInputCard")
        refreshed_preview_shadow = refreshed_backdrop_host.findChild(QObject, "graphGroupBackdropLivePreviewShadow")
        self.assertIsNone(refreshed_backdrop_input_host.findChild(QObject, "graphGroupBackdropBodyEditor"))
        self.assertIsNone(refreshed_backdrop_input_host.findChild(QObject, "graphNodeGroupBackdropBodyText"))
        self.assertIsNone(refreshed_preview_shadow)

        self.assertFalse(bool(refreshed_backdrop_host.property("_liveGeometryActive")))
        self.assertFalse(bool(refreshed_backdrop_input_host.property("_liveGeometryActive")))
        self.assertFalse(bool(refreshed_backdrop_host.property("_shadowVisible")))
        self.assertFalse(bool(refreshed_backdrop_host.property("_backgroundShadowVisible")))
        self.assertAlmostEqual(float(workspace.nodes[backdrop_id].x), 190.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[backdrop_id].y), 140.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[backdrop_id].custom_width or 0.0), 420.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[backdrop_id].custom_height or 0.0), 310.0, places=6)

    def test_scene_resize_group_backdrop_recomputes_nested_membership_without_moving_other_nodes(self) -> None:
        outer_id = self._add_group_backdrop(100.0, 100.0, 760.0, 520.0)
        inner_id = self._add_group_backdrop(220.0, 170.0, 320.0, 240.0)
        inner_logger_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 260.0, 220.0)
        outside_logger_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 980.0, 220.0)

        self.assertEqual(self._scene_payload(inner_id)["owner_backdrop_id"], outer_id)
        self.assertEqual(self._scene_payload(inner_logger_id)["owner_backdrop_id"], inner_id)
        self.assertEqual(self._scene_payload(outside_logger_id)["owner_backdrop_id"], "")

        workspace = self._workspace()
        self.history.clear_workspace(self.workspace_id)
        self.scene.set_node_geometry(outer_id, 100.0, 100.0, 240.0, 160.0)

        outer_payload = self._scene_payload(outer_id)
        inner_payload = self._scene_payload(inner_id)
        inner_logger_payload = self._scene_payload(inner_logger_id)
        outside_logger_payload = self._scene_payload(outside_logger_id)

        self.assertAlmostEqual(float(workspace.nodes[outer_id].x), 100.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].y), 100.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].custom_width or 0.0), 260.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].custom_height or 0.0), 180.0, places=6)
        self.assertEqual(outer_payload["member_backdrop_ids"], [])
        self.assertEqual(outer_payload["contained_backdrop_ids"], [])
        self.assertEqual(inner_payload["owner_backdrop_id"], "")
        self.assertEqual(inner_logger_payload["owner_backdrop_id"], inner_id)
        self.assertEqual(outside_logger_payload["owner_backdrop_id"], "")
        self.assertAlmostEqual(float(workspace.nodes[inner_id].x), 220.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_id].y), 170.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_logger_id].x), 260.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_logger_id].y), 220.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outside_logger_id].x), 980.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outside_logger_id].y), 220.0, places=6)
        self.assertEqual(self.history.undo_depth(self.workspace_id), 1)

        self.assertIsNotNone(self.history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(self._scene_payload(inner_id)["owner_backdrop_id"], outer_id)
        self.assertEqual(self._scene_payload(inner_logger_id)["owner_backdrop_id"], inner_id)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].custom_width or 0.0), 760.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].custom_height or 0.0), 520.0, places=6)

        self.assertIsNotNone(self.history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(self._scene_payload(inner_id)["owner_backdrop_id"], "")
        self.assertEqual(self._scene_payload(inner_logger_id)["owner_backdrop_id"], inner_id)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].custom_width or 0.0), 260.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].custom_height or 0.0), 180.0, places=6)


if __name__ == "__main__":
    unittest.main()
