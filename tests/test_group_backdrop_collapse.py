from __future__ import annotations

import time
import unittest
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtQuick import QQuickItem, QQuickWindow
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.decorators import in_port, node_type, out_port
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
from ea_node_editor.ui_qml.theme_bridge import ThemeBridge

GROUP_BACKDROP_TYPE_ID = "passive.annotation.group_backdrop"
TEST_NODE_TYPE_ID = "tests.group_backdrop_collapse_node"
_REPO_ROOT = Path(__file__).resolve().parents[1]


@node_type(
    type_id=TEST_NODE_TYPE_ID,
    display_name="Group Collapse Node",
    category_path=("Tests",),
    icon="",
    ports=(
        in_port("payload", required=False),
        out_port("result"),
    ),
    properties=(),
    runtime_behavior="active",
    surface_family="annotation",
    surface_variant="sticky_note",
)
class _GroupBackdropCollapseNode:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={"result": ctx.inputs.get("payload")})


def _build_registry() -> NodeRegistry:
    registry = build_default_registry()
    registry.register(_GroupBackdropCollapseNode)
    return registry


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


def _wait_for(predicate, *, timeout_ms: int = 1500, app: QApplication, message: str) -> None:
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


def _geometry_start_point(geometry: dict[str, object]) -> tuple[float, float]:
    pipe_points = geometry.get("pipe_points") or []
    if pipe_points:
        first = pipe_points[0]
        return float(first["x"]), float(first["y"])
    return float(geometry["sx"]), float(geometry["sy"])


def _assert_point_on_perimeter(
    test_case: unittest.TestCase,
    *,
    point_x: float,
    point_y: float,
    bounds: dict[str, float],
    side: str,
) -> None:
    x = float(bounds["x"])
    y = float(bounds["y"])
    width = float(bounds["width"])
    height = float(bounds["height"])
    right = x + width
    bottom = y + height
    side = str(side)
    if side == "left":
        test_case.assertAlmostEqual(point_x, x, places=6)
        test_case.assertGreaterEqual(point_y + 1e-6, y)
        test_case.assertLessEqual(point_y - 1e-6, bottom)
        return
    if side == "right":
        test_case.assertAlmostEqual(point_x, right, places=6)
        test_case.assertGreaterEqual(point_y + 1e-6, y)
        test_case.assertLessEqual(point_y - 1e-6, bottom)
        return
    if side == "top":
        test_case.assertAlmostEqual(point_y, y, places=6)
        test_case.assertGreaterEqual(point_x + 1e-6, x)
        test_case.assertLessEqual(point_x - 1e-6, right)
        return
    test_case.assertEqual(side, "bottom")
    test_case.assertAlmostEqual(point_y, bottom, places=6)
    test_case.assertGreaterEqual(point_x + 1e-6, x)
    test_case.assertLessEqual(point_x - 1e-6, right)


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


class GroupBackdropCollapseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.registry = _build_registry()
        self.model = GraphModel()
        self.workspace_id = self.model.active_workspace.workspace_id
        self.scene = GraphSceneBridge()
        self.scene.set_workspace(self.model, self.registry, self.workspace_id)
        self.view = _ViewportBridgeStub()
        self._canvas_refs: list[object] = []

    def _workspace(self):
        return self.model.project.workspaces[self.workspace_id]

    def _add_node(self, x: float, y: float) -> str:
        return self.scene.add_node_from_type(TEST_NODE_TYPE_ID, x, y)

    def _add_group_backdrop(self, x: float, y: float, width: float, height: float) -> str:
        node_id = self.scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, x, y)
        self.scene.set_node_geometry(node_id, x, y, width, height)
        return node_id

    def _edge_payload(self, edge_id: str) -> dict[str, object]:
        for payload in self.scene.edges_model:
            if str(payload["edge_id"]) == str(edge_id):
                return payload
        raise AssertionError(f"Edge payload {edge_id!r} was not found.")

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

    def test_collapsing_group_backdrop_hides_descendants_and_suppresses_internal_edges_without_mutating_workspace(self) -> None:
        outer_id = self._add_group_backdrop(80.0, 80.0, 720.0, 420.0)
        inner_id = self._add_group_backdrop(180.0, 140.0, 420.0, 280.0)
        internal_source_id = self._add_node(230.0, 180.0)
        internal_target_id = self._add_node(280.0, 240.0)
        boundary_source_id = self._add_node(500.0, 220.0)
        outside_target_id = self._add_node(980.0, 220.0)

        internal_edge_id = self.scene.add_edge(internal_source_id, "result", internal_target_id, "payload")
        boundary_edge_id = self.scene.add_edge(boundary_source_id, "result", outside_target_id, "payload")

        payload_by_id = {
            item["node_id"]: item for item in [*self.scene.nodes_model, *self.scene.backdrop_nodes_model]
        }
        self.assertEqual(payload_by_id[inner_id]["owner_backdrop_id"], outer_id)
        self.assertEqual(payload_by_id[internal_source_id]["owner_backdrop_id"], inner_id)
        self.assertEqual(payload_by_id[internal_target_id]["owner_backdrop_id"], inner_id)
        self.assertEqual(payload_by_id[boundary_source_id]["owner_backdrop_id"], outer_id)
        self.assertEqual(payload_by_id[outside_target_id]["owner_backdrop_id"], "")

        self.scene.set_node_collapsed(outer_id, True)

        workspace = self._workspace()
        self.assertTrue(workspace.nodes[outer_id].collapsed)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].x), 80.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].y), 80.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].custom_width), 720.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[outer_id].custom_height), 420.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_id].x), 180.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[internal_source_id].x), 230.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[boundary_source_id].x), 500.0, places=6)

        self.assertEqual({item["node_id"] for item in self.scene.nodes_model}, {outside_target_id})
        self.assertEqual({item["node_id"] for item in self.scene.backdrop_nodes_model}, {outer_id})
        self.assertEqual({item["node_id"] for item in self.scene.minimap_nodes_model}, {outer_id, outside_target_id})

        edges_by_id = {item["edge_id"]: item for item in self.scene.edges_model}
        self.assertNotIn(internal_edge_id, edges_by_id)
        self.assertIn(boundary_edge_id, edges_by_id)

        outer_payload = self.scene.backdrop_nodes_model[0]
        boundary_payload = edges_by_id[boundary_edge_id]
        self.assertEqual(boundary_payload["source_hidden_by_backdrop_id"], outer_id)
        self.assertEqual(boundary_payload["source_anchor_kind"], "collapsed_backdrop")
        self.assertEqual(boundary_payload["source_anchor_node_id"], outer_id)
        self.assertEqual(boundary_payload["target_hidden_by_backdrop_id"], "")
        self.assertEqual(
            boundary_payload["source_anchor_bounds"],
            {
                "x": float(outer_payload["x"]),
                "y": float(outer_payload["y"]),
                "width": float(outer_payload["width"]),
                "height": float(outer_payload["height"]),
            },
        )
        _assert_point_on_perimeter(
            self,
            point_x=float(boundary_payload["sx"]),
            point_y=float(boundary_payload["sy"]),
            bounds=boundary_payload["source_anchor_bounds"],
            side=str(boundary_payload["source_anchor_side"]),
        )

        self.scene.set_node_collapsed(outer_id, False)

        self.assertEqual(
            {item["node_id"] for item in self.scene.nodes_model},
            {internal_source_id, internal_target_id, boundary_source_id, outside_target_id},
        )
        self.assertEqual({item["node_id"] for item in self.scene.backdrop_nodes_model}, {outer_id, inner_id})
        restored_edges = {item["edge_id"]: item for item in self.scene.edges_model}
        self.assertEqual(set(restored_edges), {internal_edge_id, boundary_edge_id})
        restored_boundary_payload = restored_edges[boundary_edge_id]
        self.assertEqual(restored_boundary_payload["source_hidden_by_backdrop_id"], "")
        self.assertEqual(restored_boundary_payload["source_anchor_kind"], "node")
        self.assertEqual(restored_boundary_payload["source_anchor_node_id"], boundary_source_id)

    def test_nested_collapsed_group_backdrops_proxy_to_outermost_visible_collapsed_ancestor(self) -> None:
        outer_id = self._add_group_backdrop(60.0, 60.0, 760.0, 460.0)
        inner_id = self._add_group_backdrop(170.0, 140.0, 440.0, 280.0)
        inner_boundary_source_id = self._add_node(230.0, 180.0)
        inner_internal_source_id = self._add_node(300.0, 240.0)
        outer_target_id = self._add_node(540.0, 240.0)
        outside_target_id = self._add_node(1040.0, 240.0)

        edge_to_outside_id = self.scene.add_edge(inner_boundary_source_id, "result", outside_target_id, "payload")
        edge_to_outer_id = self.scene.add_edge(inner_internal_source_id, "result", outer_target_id, "payload")

        payload_by_id = {
            item["node_id"]: item for item in [*self.scene.nodes_model, *self.scene.backdrop_nodes_model]
        }
        self.assertEqual(payload_by_id[inner_id]["owner_backdrop_id"], outer_id)
        self.assertEqual(payload_by_id[inner_boundary_source_id]["owner_backdrop_id"], inner_id)
        self.assertEqual(payload_by_id[inner_internal_source_id]["owner_backdrop_id"], inner_id)
        self.assertEqual(payload_by_id[outer_target_id]["owner_backdrop_id"], outer_id)
        self.assertEqual(payload_by_id[outside_target_id]["owner_backdrop_id"], "")

        self.scene.set_node_collapsed(inner_id, True)

        collapsed_inner_edges = {item["edge_id"]: item for item in self.scene.edges_model}
        self.assertEqual({item["node_id"] for item in self.scene.backdrop_nodes_model}, {outer_id, inner_id})
        self.assertEqual(collapsed_inner_edges[edge_to_outside_id]["source_hidden_by_backdrop_id"], inner_id)
        self.assertEqual(collapsed_inner_edges[edge_to_outside_id]["source_anchor_node_id"], inner_id)
        self.assertIn(edge_to_outer_id, collapsed_inner_edges)
        self.assertEqual(collapsed_inner_edges[edge_to_outer_id]["source_hidden_by_backdrop_id"], inner_id)

        self.scene.set_node_collapsed(outer_id, True)

        collapsed_outer_edges = {item["edge_id"]: item for item in self.scene.edges_model}
        self.assertEqual({item["node_id"] for item in self.scene.backdrop_nodes_model}, {outer_id})
        self.assertEqual(collapsed_outer_edges[edge_to_outside_id]["source_hidden_by_backdrop_id"], outer_id)
        self.assertEqual(collapsed_outer_edges[edge_to_outside_id]["source_anchor_node_id"], outer_id)
        self.assertNotIn(edge_to_outer_id, collapsed_outer_edges)

    def test_edge_layer_redraw_uses_collapsed_group_backdrop_proxy_geometry(self) -> None:
        outer_id = self._add_group_backdrop(80.0, 80.0, 520.0, 320.0)
        inside_source_id = self._add_node(190.0, 180.0)
        outside_target_id = self._add_node(760.0, 200.0)
        edge_id = self.scene.add_edge(inside_source_id, "result", outside_target_id, "payload")
        self.scene.set_node_collapsed(outer_id, True)

        canvas, _window = self._create_canvas()
        edge_layer = canvas.findChild(QObject, "graphCanvasEdgeLayer")
        self.assertIsNotNone(edge_layer)

        _wait_for(
            lambda: len(_named_child_items(canvas, "graphNodeCard")) == 2,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for the collapsed backdrop canvas hosts.",
        )
        _wait_for(
            lambda: _variant_value(edge_layer._visibleEdgeSnapshot(edge_id)) is not None,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for the collapsed boundary edge snapshot.",
        )

        edge_payload = self._edge_payload(edge_id)
        initial_snapshot = _variant_value(edge_layer._visibleEdgeSnapshot(edge_id))
        initial_geometry = initial_snapshot["geometry"]
        initial_start = _geometry_start_point(initial_geometry)
        self.assertAlmostEqual(initial_start[0], float(edge_payload["sx"]), places=6)
        self.assertAlmostEqual(initial_start[1], float(edge_payload["sy"]), places=6)

        initial_revision = int(edge_layer.property("_visibleEdgeSnapshotRevision"))
        canvas.setLiveDragOffset(outer_id, 70.0, 25.0)
        edge_layer.requestRedraw()

        _wait_for(
            lambda: int(edge_layer.property("_visibleEdgeSnapshotRevision")) > initial_revision,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for the edge layer to redraw after the collapsed backdrop moved.",
        )

        moved_snapshot = _variant_value(edge_layer._visibleEdgeSnapshot(edge_id))
        moved_geometry = moved_snapshot["geometry"]
        moved_start = _geometry_start_point(moved_geometry)
        self.assertAlmostEqual(moved_start[0], float(edge_payload["sx"]) + 70.0, places=6)
        self.assertAlmostEqual(moved_start[1], float(edge_payload["sy"]) + 25.0, places=6)


if __name__ == "__main__":
    unittest.main()
