from __future__ import annotations

import time
import unittest
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PyQt6.QtCore import QCoreApplication, QObject, QPoint, QPointF, Qt, QUrl, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QWheelEvent
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtQuick import QQuickItem, QQuickWindow
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_canvas_viewport_index import payload_scene_rect, rect_contains
from ea_node_editor.ui_qml.graph_canvas_visible_model import GraphCanvasVisibleModel
from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
from ea_node_editor.ui_qml.theme_bridge import ThemeBridge
from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge
from ea_node_editor.ui.theme.tokens import STITCH_LIGHT_V1

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _node_payload(
    node_id: str,
    *,
    x: float,
    y: float,
    width: float = 180.0,
    height: float = 96.0,
    surface_family: str = "standard",
    surface_variant: str = "default",
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "type_id": "tests.viewport_node",
        "title": node_id,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "ports": [],
        "properties": {},
        "runtime_behavior": "passive" if surface_family == "group_backdrop" else "active",
        "surface_family": surface_family,
        "surface_variant": surface_variant,
        "read_only": False,
        "unresolved": False,
        "can_enter_scope": False,
    }


def _backdrop_payload(node_id: str, *, x: float, y: float) -> dict[str, Any]:
    payload = _node_payload(
        node_id,
        x=x,
        y=y,
        width=320.0,
        height=180.0,
        surface_family="group_backdrop",
        surface_variant="group_backdrop",
    )
    payload["member_node_ids"] = []
    payload["member_backdrop_ids"] = []
    return payload


def _edge_payload(
    edge_id: str,
    *,
    sx: float = 80.0,
    sy: float = 100.0,
    tx: float = 240.0,
    ty: float = 100.0,
    label: str = "",
) -> dict[str, Any]:
    return {
        "edge_id": edge_id,
        "source_node_id": "source",
        "source_port_key": "value",
        "target_node_id": "target",
        "target_port_key": "payload",
        "source_port_kind": "data",
        "target_port_kind": "data",
        "edge_family": "standard",
        "label": label,
        "visual_style": {},
        "flow_style": {},
        "source_port_side": "right",
        "target_port_side": "left",
        "source_anchor_side": "right",
        "target_anchor_side": "left",
        "source_anchor_kind": "scene",
        "target_anchor_kind": "scene",
        "source_anchor_node_id": "source",
        "target_anchor_node_id": "target",
        "source_hidden_by_backdrop_id": "",
        "target_hidden_by_backdrop_id": "",
        "source_anchor_bounds": None,
        "target_anchor_bounds": None,
        "lane_bias": 0.0,
        "sx": sx,
        "sy": sy,
        "tx": tx,
        "ty": ty,
        "c1x": sx + 72.0,
        "c1y": sy,
        "c2x": tx - 72.0,
        "c2y": ty,
        "route": "bezier",
        "pipe_points": [],
        "color": "#7AA8FF",
        "data_type_warning": False,
    }


def _edge_ids(value: object) -> list[str]:
    payloads = _variant_value(value)
    if not isinstance(payloads, list):
        return []
    return [str(item.get("edge_id", "")) for item in payloads if isinstance(item, dict)]


def _visible_node_ids(bridge: GraphCanvasStateBridge) -> set[str]:
    return {
        str(payload.get("node_id", ""))
        for payload in bridge.visible_nodes_model.payloads()
        if isinstance(payload, dict)
    }


def _node_delta(
    payloads: list[dict[str, Any]],
    *,
    reason: str = "node_position_delta",
    added_node_ids: list[str] | None = None,
    removed_node_ids: list[str] | None = None,
    visibility_may_change: bool = True,
) -> dict[str, Any]:
    return {
        "kind": "node_delta",
        "reason": reason,
        "nodes": payloads,
        "backdrop_nodes": [],
        "removed_node_ids": list(removed_node_ids or []),
        "added_node_ids": list(added_node_ids or []),
        "visibility_may_change": visibility_may_change,
    }


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


def _color_name(value: object) -> str:
    return QColor(value).name(QColor.NameFormat.HexRgb)


def _item_scene_point(item: QQuickItem, x_factor: float = 0.5, y_factor: float = 0.5) -> QPoint:
    scene_point = item.mapToScene(QPointF(item.width() * x_factor, item.height() * y_factor))
    return QPoint(round(scene_point.x()), round(scene_point.y()))


def _variant_value(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


def _node_host(canvas: QObject, node_id: str, *, object_name: str = "graphNodeCard") -> QQuickItem | None:
    normalized = str(node_id)
    for item in _named_child_items(canvas, object_name):
        payload = _variant_value(item.property("nodeData"))
        if isinstance(payload, dict) and str(payload.get("node_id", "")) == normalized:
            return item
    return None


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


class _ViewportBridgeStub(QObject):
    view_state_changed = pyqtSignal()

    def __init__(self, payload: dict[str, float] | None = None) -> None:
        super().__init__()
        self._payload = payload or {"x": -480.0, "y": -360.0, "width": 960.0, "height": 720.0}
        self._zoom = 1.0
        self.zoom_adjust_calls: list[tuple[float, float | None, float | None]] = []

    @pyqtProperty(float, notify=view_state_changed)
    def center_x(self) -> float:
        return 0.0

    @pyqtProperty(float, notify=view_state_changed)
    def center_y(self) -> float:
        return 0.0

    @pyqtProperty(float, notify=view_state_changed)
    def zoom_value(self) -> float:
        return self._zoom

    @pyqtProperty("QVariantMap", notify=view_state_changed)
    def visible_scene_rect_payload(self) -> dict[str, float]:
        return dict(self._payload)

    @pyqtProperty("QVariantMap", notify=view_state_changed)
    def visible_scene_rect_payload_cached(self) -> dict[str, float]:
        return self.visible_scene_rect_payload

    def set_visible_scene_rect(self, payload: dict[str, float]) -> None:
        self._payload = dict(payload)
        self.view_state_changed.emit()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = float(zoom)
        self.view_state_changed.emit()

    def adjust_zoom(self, factor: float) -> None:
        self.zoom_adjust_calls.append((float(factor), None, None))

    def adjust_zoom_at_viewport_point(self, factor: float, viewport_x: float, viewport_y: float) -> bool:
        self.zoom_adjust_calls.append((float(factor), float(viewport_x), float(viewport_y)))
        return True


class _SceneSource(QObject):
    graphics_preferences_changed = pyqtSignal()
    snap_to_grid_changed = pyqtSignal()
    nodes_changed = pyqtSignal()
    edges_changed = pyqtSignal()
    selection_changed = pyqtSignal()
    workspace_changed = pyqtSignal()

    def __init__(
        self,
        *,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]] | None = None,
        backdrops: list[dict[str, Any]] | None = None,
        selected_node_ids: set[str] | None = None,
    ) -> None:
        super().__init__()
        self.workspace_id = "workspace-viewport"
        self.hide_optional_ports = False
        self._nodes = list(nodes)
        self._edges = list(edges or [])
        self._edge_delta_payload: dict[str, Any] = {}
        self._node_delta_payload: dict[str, Any] = {}
        self._backdrops = list(backdrops or [])
        self._selected_node_ids = set(selected_node_ids or set())

    @pyqtProperty("QVariantList", notify=nodes_changed)
    def nodes_model(self) -> list[dict[str, Any]]:
        return list(self._nodes)

    @pyqtProperty("QVariantList", notify=nodes_changed)
    def minimap_nodes_model(self) -> list[dict[str, Any]]:
        return [
            {
                key: payload[key]
                for key in ("node_id", "x", "y", "width", "height")
            }
            for payload in (*self._nodes, *self._backdrops)
        ]

    @pyqtProperty("QVariantList", notify=nodes_changed)
    def backdrop_nodes_model(self) -> list[dict[str, Any]]:
        return list(self._backdrops)

    @pyqtProperty("QVariantMap", notify=nodes_changed)
    def node_delta_payload(self) -> dict[str, Any]:
        return dict(self._node_delta_payload)

    @pyqtProperty("QVariantMap", notify=nodes_changed)
    def workspace_scene_bounds_payload(self) -> dict[str, float]:
        return {"x": -480.0, "y": -360.0, "width": 5200.0, "height": 1200.0}

    @pyqtProperty("QVariantList", notify=edges_changed)
    def edges_model(self) -> list[dict[str, Any]]:
        return list(self._edges)

    @pyqtProperty("QVariantMap", notify=edges_changed)
    def edge_delta_payload(self) -> dict[str, Any]:
        return dict(self._edge_delta_payload)

    @pyqtProperty("QVariantMap", notify=selection_changed)
    def selected_node_lookup(self) -> dict[str, bool]:
        return {node_id: True for node_id in self._selected_node_ids}

    def select_node(self, node_id: str) -> None:
        self._selected_node_ids = {node_id}
        self.selection_changed.emit()

    def set_nodes(self, nodes: list[dict[str, Any]], node_delta_payload: dict[str, Any] | None = None) -> None:
        self._nodes = list(nodes)
        self._node_delta_payload = dict(node_delta_payload or {})
        self.nodes_changed.emit()

    def set_edges(self, edges: list[dict[str, Any]], delta_payload: dict[str, Any]) -> None:
        self._edges = list(edges)
        self._edge_delta_payload = dict(delta_payload)
        self.edges_changed.emit()


@dataclass(slots=True)
class _RunState:
    failed_node_id: str = ""
    failed_node_title: str = ""
    failed_workspace_id: str = "workspace-viewport"
    node_execution_workspace_id: str = "workspace-viewport"
    running_node_ids: set[str] = field(default_factory=set)
    completed_node_ids: set[str] = field(default_factory=set)
    warning_node_ids: set[str] = field(default_factory=set)
    running_node_started_at_epoch_ms_by_node_id: dict[str, float] = field(default_factory=dict)
    cached_node_elapsed_ms_by_workspace_id: dict[str, dict[str, float]] = field(default_factory=dict)
    selected_run_preview_workspace_id: str = "workspace-viewport"
    selected_run_preview_rows: tuple[dict[str, Any], ...] = ()
    selected_run_preview_node_lookup: dict[str, str] = field(default_factory=dict)
    selected_run_preview_revision: int = 0
    node_execution_revision: int = 0


class _ExecutionSource(QObject):
    run_failure_changed = pyqtSignal()
    node_execution_state_changed = pyqtSignal()

    def __init__(self, run_state: _RunState) -> None:
        super().__init__()
        self.run_state = run_state


class GraphCanvasViewportVirtualizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_viewport_bridge_buckets_node_render_activation_rect(self) -> None:
        view = ViewportBridge()
        self.addCleanup(view.deleteLater)
        view.set_viewport_size(800.0, 600.0)
        view.set_view_state(1.0, 0.0, 0.0)

        events: list[dict[str, float]] = []
        view.node_render_activation_scene_rect_changed.connect(
            lambda: events.append(dict(view.node_render_activation_scene_rect_payload))
        )
        first_payload = dict(view.node_render_activation_scene_rect_payload)

        view.pan_by(1.0, 0.0)

        self.assertEqual(events, [])
        self.assertEqual(dict(view.node_render_activation_scene_rect_payload), first_payload)
        self.assertTrue(
            rect_contains(
                payload_scene_rect(view.node_render_activation_scene_rect_payload),
                payload_scene_rect(view.expanded_visible_scene_rect_payload),
            )
        )

        view.pan_by(200.0, 0.0)

        self.assertEqual(len(events), 1)
        self.assertNotEqual(dict(view.node_render_activation_scene_rect_payload), first_payload)
        self.assertTrue(
            rect_contains(
                payload_scene_rect(view.node_render_activation_scene_rect_payload),
                payload_scene_rect(view.expanded_visible_scene_rect_payload),
            )
        )

    def test_viewport_bridge_uses_axis_aware_padding_across_zoom_and_resize(self) -> None:
        view = ViewportBridge()
        self.addCleanup(view.deleteLater)

        view.set_viewport_size(1600.0, 400.0)
        view.set_view_state(1.0, 0.0, 0.0)
        self.assertEqual(
            payload_scene_rect(view.expanded_visible_scene_rect_payload),
            (-1440.0, -440.0, 2880.0, 880.0),
        )

        view.set_view_state(2.0, 0.0, 0.0)
        self.assertEqual(
            payload_scene_rect(view.expanded_visible_scene_rect_payload),
            (-720.0, -220.0, 1440.0, 440.0),
        )
        self.assertEqual(
            payload_scene_rect(view.node_render_activation_scene_rect_payload),
            (-832.0, -320.0, 1664.0, 640.0),
        )

        view.set_viewport_size(400.0, 1600.0)
        self.assertEqual(
            payload_scene_rect(view.expanded_visible_scene_rect_payload),
            (-220.0, -720.0, 440.0, 1440.0),
        )
        self.assertEqual(
            payload_scene_rect(view.node_render_activation_scene_rect_payload),
            (-320.0, -832.0, 640.0, 1664.0),
        )

        view.set_viewport_size(800.0, 1000.0)
        self.assertEqual(
            payload_scene_rect(view.expanded_visible_scene_rect_payload),
            (-400.0, -500.0, 800.0, 1000.0),
        )

    def test_visible_model_refreshes_when_lookahead_safety_band_reaches_exact_query_edge(self) -> None:
        scene = _SceneSource(
            nodes=[
                _node_payload("visible", x=0.0, y=0.0),
                _node_payload("upcoming", x=1500.0, y=0.0),
            ]
        )
        view = _ViewportBridgeStub({"x": 0.0, "y": 0.0, "width": 800.0, "height": 600.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)

        visible_nodes_model = bridge.visible_nodes_model
        self.assertTrue(bridge.force_visible_scene_models_exact())
        exact_diagnostics = bridge.visible_scene_model_diagnostics
        exact_query_count = exact_diagnostics["query_count"]
        self.assertEqual(exact_diagnostics["query_rect"]["x"], -400.0)
        self.assertEqual(exact_diagnostics["query_rect"]["width"], 1600.0)

        view.set_visible_scene_rect({"x": 271.0, "y": 0.0, "width": 800.0, "height": 600.0})
        contained_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertEqual(contained_diagnostics["query_count"], exact_query_count)
        self.assertNotIn("upcoming", {payload["node_id"] for payload in visible_nodes_model})

        view.set_visible_scene_rect({"x": 273.0, "y": 0.0, "width": 800.0, "height": 600.0})
        scheduled_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertEqual(scheduled_diagnostics["query_count"], exact_query_count)
        self.assertTrue(scheduled_diagnostics["view_refresh_pending"])
        self.assertNotEqual(scheduled_diagnostics["pending_query_rect"], {})

        _wait_for(
            lambda: bridge.visible_scene_model_diagnostics["query_count"] > exact_query_count,
            app=self.app,
            message="Timed out waiting for the coalesced look-ahead refresh.",
        )
        refreshed_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertGreater(refreshed_diagnostics["query_count"], exact_query_count)
        self.assertFalse(refreshed_diagnostics["dirty"])
        self.assertFalse(refreshed_diagnostics["deferred"])
        self.assertFalse(refreshed_diagnostics["view_refresh_pending"])
        self.assertIn("upcoming", {payload["node_id"] for payload in visible_nodes_model})

    def test_visible_model_coalesces_fast_pan_burst_to_latest_retained_bucket(self) -> None:
        scene = _SceneSource(
            nodes=[
                _node_payload("visible", x=0.0, y=0.0),
                _node_payload("upcoming", x=1500.0, y=0.0),
            ]
        )
        view = _ViewportBridgeStub({"x": 0.0, "y": 0.0, "width": 800.0, "height": 600.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        self.addCleanup(bridge.deleteLater)

        visible_nodes_model = bridge.visible_nodes_model
        self.assertTrue(bridge.force_visible_scene_models_exact())
        exact_query_count = bridge.visible_scene_model_diagnostics["query_count"]
        notifications: list[bool] = []
        bridge.visible_scene_models_changed.connect(lambda: notifications.append(True))

        for x in (273.0, 320.0, 350.0):
            view.set_visible_scene_rect({"x": x, "y": 0.0, "width": 800.0, "height": 600.0})

        scheduled_diagnostics = bridge.visible_scene_model_diagnostics
        latest_pending_rect = scheduled_diagnostics["pending_query_rect"]
        self.assertEqual(scheduled_diagnostics["query_count"], exact_query_count)
        self.assertEqual(notifications, [])
        self.assertTrue(scheduled_diagnostics["view_refresh_pending"])

        _wait_for(
            lambda: bridge.visible_scene_model_diagnostics["query_count"] > exact_query_count,
            app=self.app,
            message="Timed out waiting for the fast-pan burst refresh.",
        )
        refreshed_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertEqual(refreshed_diagnostics["query_count"], exact_query_count + 2)
        self.assertEqual(refreshed_diagnostics["query_rect"], latest_pending_rect)
        self.assertEqual(notifications, [True])
        self.assertIn("upcoming", {payload["node_id"] for payload in visible_nodes_model})

    def test_visible_model_drops_stale_pan_refresh_after_direction_reversal(self) -> None:
        scene = _SceneSource(nodes=[_node_payload("visible", x=0.0, y=0.0)])
        view = _ViewportBridgeStub({"x": 0.0, "y": 0.0, "width": 800.0, "height": 600.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        self.addCleanup(bridge.deleteLater)

        _ = bridge.visible_nodes_model
        self.assertTrue(bridge.force_visible_scene_models_exact())
        exact_diagnostics = bridge.visible_scene_model_diagnostics
        exact_query_count = exact_diagnostics["query_count"]
        exact_query_rect = exact_diagnostics["query_rect"]

        view.set_visible_scene_rect({"x": 273.0, "y": 0.0, "width": 800.0, "height": 600.0})
        self.assertTrue(bridge.visible_scene_model_diagnostics["view_refresh_pending"])
        view.set_visible_scene_rect({"x": 0.0, "y": 0.0, "width": 800.0, "height": 600.0})
        QTest.qWait(30)
        self.app.processEvents()

        settled_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertEqual(settled_diagnostics["query_count"], exact_query_count)
        self.assertEqual(settled_diagnostics["query_rect"], exact_query_rect)
        self.assertEqual(settled_diagnostics["pending_query_rect"], {})
        self.assertFalse(settled_diagnostics["view_refresh_pending"])

    def test_visible_model_refreshes_synchronously_if_fast_pan_exits_retained_region(self) -> None:
        scene = _SceneSource(
            nodes=[
                _node_payload("visible", x=0.0, y=0.0),
                _node_payload("jump-target", x=1500.0, y=0.0),
            ]
        )
        view = _ViewportBridgeStub({"x": 0.0, "y": 0.0, "width": 800.0, "height": 600.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        self.addCleanup(bridge.deleteLater)

        visible_nodes_model = bridge.visible_nodes_model
        self.assertTrue(bridge.force_visible_scene_models_exact())
        exact_query_count = bridge.visible_scene_model_diagnostics["query_count"]

        view.set_visible_scene_rect({"x": 1000.0, "y": 0.0, "width": 800.0, "height": 600.0})

        jumped_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertGreater(jumped_diagnostics["query_count"], exact_query_count)
        self.assertFalse(jumped_diagnostics["view_refresh_pending"])
        self.assertIn("jump-target", {payload["node_id"] for payload in visible_nodes_model})

    def test_qml_node_host_hides_empty_node_identity(self) -> None:
        engine = QQmlEngine()
        theme_bridge = ThemeBridge(theme_id="stitch_light")
        graph_theme_bridge = GraphThemeBridge(theme_id="graph_stitch_light")
        self.addCleanup(theme_bridge.deleteLater)
        self.addCleanup(graph_theme_bridge.deleteLater)
        engine.rootContext().setContextProperty("themeBridge", theme_bridge)
        engine.rootContext().setContextProperty("graphThemeBridge", graph_theme_bridge)
        component = QQmlComponent(
            engine,
            QUrl.fromLocalFile(str(_REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph" / "GraphNodeHost.qml")),
        )
        if component.status() != QQmlComponent.Status.Ready:
            errors = "\n".join(error.toString() for error in component.errors())
            self.fail(f"Failed to load GraphNodeHost.qml:\n{errors}")

        host = component.create()
        self.addCleanup(lambda: host.deleteLater() if host is not None else None)
        if host is None:
            errors = "\n".join(error.toString() for error in component.errors())
            self.fail(f"Failed to instantiate GraphNodeHost.qml:\n{errors}")

        self.app.processEvents()
        self.assertFalse(bool(_variant_value(host.property("hasNodeIdentity"))))
        self.assertFalse(bool(_variant_value(host.property("visible"))))
        self.assertFalse(bool(_variant_value(host.property("enabled"))))

        host.setProperty("nodeData", _node_payload("visible", x=0.0, y=0.0))
        self.app.processEvents()
        self.assertTrue(bool(_variant_value(host.property("hasNodeIdentity"))))
        self.assertEqual(_variant_value(host.property("nodeId")), "visible")
        self.assertTrue(bool(_variant_value(host.property("enabled"))))

        host.setProperty("nodeData", {"title": "Missing id", "ports": []})
        self.app.processEvents()
        self.assertFalse(bool(_variant_value(host.property("hasNodeIdentity"))))
        self.assertFalse(bool(_variant_value(host.property("visible"))))
        self.assertFalse(bool(_variant_value(host.property("enabled"))))

    def test_visible_model_syncs_unique_node_payloads_without_model_reset(self) -> None:
        model = GraphCanvasVisibleModel()
        self.addCleanup(model.deleteLater)
        events: list[str] = []
        model.modelReset.connect(lambda: events.append("reset"))
        model.rowsInserted.connect(lambda *_args: events.append("insert"))
        model.rowsRemoved.connect(lambda *_args: events.append("remove"))
        model.rowsMoved.connect(lambda *_args: events.append("move"))
        model.dataChanged.connect(lambda *_args: events.append("data"))

        model.sync_payloads(
            [
                _node_payload("a", x=0.0, y=0.0),
                _node_payload("b", x=100.0, y=0.0),
                _node_payload("c", x=200.0, y=0.0),
            ]
        )
        self.assertEqual(model.rowCount(), 3)
        self.assertEqual(events, ["insert"])

        events.clear()
        model.sync_payloads(
            [
                _node_payload("a", x=12.0, y=0.0),
                _node_payload("c", x=200.0, y=0.0),
                _node_payload("b", x=100.0, y=18.0),
                _node_payload("d", x=300.0, y=0.0),
            ]
        )
        self.assertNotIn("reset", events)
        self.assertIn("data", events)
        self.assertIn("move", events)
        self.assertIn("insert", events)
        self.assertEqual([payload["node_id"] for payload in model.payloads()], ["a", "c", "b", "d"])

        events.clear()
        model.sync_payloads([])
        self.assertEqual(model.rowCount(), 0)
        self.assertEqual(events, ["remove"])

        events.clear()
        model.sync_payloads([{"node_id": ""}])
        self.assertIn("reset", events)

    def test_visible_model_appends_new_payload_batch_with_one_row_transaction(self) -> None:
        model = GraphCanvasVisibleModel()
        self.addCleanup(model.deleteLater)
        model.sync_payloads([_node_payload("a", x=0.0, y=0.0)])
        inserted_ranges: list[tuple[int, int]] = []
        resets: list[str] = []
        model.rowsInserted.connect(lambda _parent, first, last: inserted_ranges.append((first, last)))
        model.modelReset.connect(lambda: resets.append("reset"))

        appended = model.append_new_payloads(
            [
                _node_payload("b", x=100.0, y=0.0),
                _node_payload("c", x=200.0, y=0.0),
            ]
        )

        self.assertEqual(appended, 2)
        self.assertEqual(inserted_ranges, [(1, 2)])
        self.assertEqual(resets, [])
        self.assertEqual([payload["node_id"] for payload in model.payloads()], ["a", "b", "c"])
        self.assertIsNone(model.append_new_payloads([_node_payload("b", x=999.0, y=0.0)]))

    def test_visible_model_defers_reentrant_append_and_reports_duplicate_after_transactions(self) -> None:
        model = GraphCanvasVisibleModel()
        self.addCleanup(model.deleteLater)
        model.sync_payloads([_node_payload("a", x=0.0, y=0.0)])
        active_transactions = 0
        nested_transactions: list[str] = []
        duplicate_events: list[tuple[int, list[str]]] = []
        append_results: list[int | None] = []
        reentrant_append_requested = False

        def begin_transaction() -> None:
            nonlocal active_transactions
            if active_transactions:
                nested_transactions.append("insert")
            active_transactions += 1

        def end_transaction() -> None:
            nonlocal active_transactions
            active_transactions -= 1

        def request_reentrant_append(*_args: object) -> None:
            nonlocal reentrant_append_requested
            if reentrant_append_requested:
                return
            reentrant_append_requested = True
            payload = _node_payload("c", x=200.0, y=0.0)
            append_results.append(model.append_new_payloads([payload, dict(payload, title="duplicate")]))

        model.rowsAboutToBeInserted.connect(lambda *_args: begin_transaction())
        model.rowsInserted.connect(lambda *_args: end_transaction())
        model.rowsAboutToBeInserted.connect(request_reentrant_append)
        model.duplicate_node_ids_detected.connect(
            lambda node_ids: duplicate_events.append((active_transactions, list(node_ids)))
        )

        self.assertEqual(model.append_new_payloads([_node_payload("b", x=100.0, y=0.0)]), 1)

        self.assertEqual(append_results, [1])
        self.assertEqual(nested_transactions, [])
        self.assertEqual(active_transactions, 0)
        self.assertEqual(duplicate_events, [(0, ["c"])])
        self.assertEqual([payload["node_id"] for payload in model.payloads()], ["a", "b", "c"])

    def test_visible_model_replaces_existing_payloads_in_contiguous_ranges(self) -> None:
        model = GraphCanvasVisibleModel()
        self.addCleanup(model.deleteLater)
        initial = [
            _node_payload(node_id, x=float(row * 100), y=0.0)
            for row, node_id in enumerate(("a", "b", "c", "d", "e"))
        ]
        model.sync_payloads(initial)
        structural_events: list[str] = []
        changed_ranges: list[tuple[int, int]] = []
        model.modelReset.connect(lambda: structural_events.append("reset"))
        model.rowsInserted.connect(lambda *_args: structural_events.append("insert"))
        model.rowsRemoved.connect(lambda *_args: structural_events.append("remove"))
        model.rowsMoved.connect(lambda *_args: structural_events.append("move"))
        model.dataChanged.connect(
            lambda first, last, _roles: changed_ranges.append((first.row(), last.row()))
        )

        updated_b = dict(initial[1], title="updated-b")
        updated_c = dict(initial[2], title="updated-c")
        updated_e = dict(initial[4], title="updated-e")
        replaced = model.replace_existing_payloads(
            [initial[0], updated_b, updated_c, updated_e]
        )

        self.assertEqual(replaced, 3)
        self.assertEqual(changed_ranges, [(1, 2), (4, 4)])
        self.assertEqual(structural_events, [])
        self.assertEqual(
            [payload["title"] for payload in model.payloads()],
            ["a", "updated-b", "updated-c", "d", "updated-e"],
        )

        snapshot = model.payloads()
        changed_ranges.clear()
        self.assertIsNone(
            model.replace_existing_payloads(
                [dict(updated_b, title="must-not-apply"), _node_payload("missing", x=0.0, y=0.0)]
            )
        )
        self.assertIsNone(model.replace_existing_payloads([updated_b, dict(updated_b)]))
        self.assertIsNone(model.replace_existing_payloads([{"node_id": "", "title": "invalid"}]))
        self.assertEqual(model.payloads(), snapshot)
        self.assertEqual(changed_ranges, [])

    def test_visible_model_reentrant_replace_uses_latest_pending_snapshot(self) -> None:
        model = GraphCanvasVisibleModel()
        self.addCleanup(model.deleteLater)
        model.sync_payloads(
            [
                _node_payload("a", x=0.0, y=0.0),
                _node_payload("b", x=100.0, y=0.0),
            ]
        )
        active_transactions = 0
        nested_transactions: list[str] = []
        replace_results: list[int | None] = []
        detected: list[tuple[int, list[str]]] = []
        reentrant_update_requested = False

        def begin_transaction(name: str) -> None:
            nonlocal active_transactions
            if active_transactions:
                nested_transactions.append(name)
            active_transactions += 1

        def end_transaction() -> None:
            nonlocal active_transactions
            active_transactions -= 1

        def request_reentrant_update(*_args: object) -> None:
            nonlocal reentrant_update_requested
            if reentrant_update_requested:
                return
            reentrant_update_requested = True
            pending_d = _node_payload("d", x=300.0, y=0.0)
            model.sync_payloads(
                [
                    _node_payload("a", x=0.0, y=0.0),
                    _node_payload("b", x=100.0, y=0.0),
                    _node_payload("c", x=200.0, y=0.0),
                    pending_d,
                    _node_payload("a", x=999.0, y=0.0),
                ]
            )
            replace_results.append(
                model.replace_existing_payloads([dict(pending_d, title="latest-d")])
            )

        model.rowsAboutToBeInserted.connect(lambda *_args: begin_transaction("insert"))
        model.rowsInserted.connect(lambda *_args: end_transaction())
        model.rowsAboutToBeInserted.connect(request_reentrant_update)
        model.duplicate_node_ids_detected.connect(
            lambda node_ids: detected.append((active_transactions, list(node_ids)))
        )

        model.sync_payloads(
            [
                _node_payload("a", x=0.0, y=0.0),
                _node_payload("b", x=100.0, y=0.0),
                _node_payload("c", x=200.0, y=0.0),
            ]
        )

        self.assertEqual(replace_results, [1])
        self.assertEqual(nested_transactions, [])
        self.assertEqual(active_transactions, 0)
        self.assertEqual(detected, [(0, ["a"])])
        self.assertEqual(
            [payload["node_id"] for payload in model.payloads()],
            ["a", "b", "c", "d"],
        )
        self.assertEqual(model.payloads()[-1]["title"], "latest-d")

    def test_visible_model_defers_reentrant_syncs_until_row_transaction_finishes(self) -> None:
        model = GraphCanvasVisibleModel()
        self.addCleanup(model.deleteLater)
        active_transactions = 0
        nested_transactions: list[str] = []
        reentrant_sync_requested = False

        def begin_transaction(name: str) -> None:
            nonlocal active_transactions
            if active_transactions:
                nested_transactions.append(name)
            active_transactions += 1

        def end_transaction() -> None:
            nonlocal active_transactions
            active_transactions -= 1

        def request_reentrant_sync(*_args: object) -> None:
            nonlocal reentrant_sync_requested
            if reentrant_sync_requested:
                return
            reentrant_sync_requested = True
            model.sync_payloads(
                [
                    _node_payload("a", x=0.0, y=0.0),
                    _node_payload("b", x=100.0, y=0.0),
                    _node_payload("c", x=200.0, y=0.0),
                    _node_payload("d", x=300.0, y=0.0),
                ]
            )

        model.rowsAboutToBeInserted.connect(lambda *_args: begin_transaction("insert"))
        model.rowsInserted.connect(lambda *_args: end_transaction())
        model.rowsAboutToBeRemoved.connect(lambda *_args: begin_transaction("remove"))
        model.rowsRemoved.connect(lambda *_args: end_transaction())
        model.rowsAboutToBeMoved.connect(lambda *_args: begin_transaction("move"))
        model.rowsMoved.connect(lambda *_args: end_transaction())
        model.modelAboutToBeReset.connect(lambda: begin_transaction("reset"))
        model.modelReset.connect(lambda: end_transaction())
        model.rowsAboutToBeInserted.connect(request_reentrant_sync)

        model.sync_payloads(
            [
                _node_payload("a", x=0.0, y=0.0),
                _node_payload("stale", x=100.0, y=0.0),
            ]
        )

        self.assertTrue(reentrant_sync_requested)
        self.assertEqual(nested_transactions, [])
        self.assertEqual(active_transactions, 0)
        self.assertEqual(
            [payload["node_id"] for payload in model.payloads()],
            ["a", "b", "c", "d"],
        )

    def test_state_bridge_applies_targeted_visible_node_delta_without_viewport_requery(self) -> None:
        visible = _node_payload("visible", x=10.0, y=10.0)
        offscreen = _node_payload("offscreen", x=3000.0, y=0.0)
        scene = _SceneSource(nodes=[visible, offscreen])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)

        visible_nodes_model = bridge.visible_nodes_model
        diagnostics = bridge.visible_scene_model_diagnostics
        query_count = diagnostics["query_count"]
        rebuild_count = diagnostics["nodes"]["rebuild_count"]
        events: list[str] = []
        visible_nodes_model.modelReset.connect(lambda: events.append("reset"))
        visible_nodes_model.rowsInserted.connect(lambda *_args: events.append("insert"))
        visible_nodes_model.rowsRemoved.connect(lambda *_args: events.append("remove"))
        visible_nodes_model.rowsMoved.connect(lambda *_args: events.append("move"))
        visible_nodes_model.dataChanged.connect(lambda *_args: events.append("data"))

        renamed_visible = dict(visible)
        renamed_visible["title"] = "Visible renamed"
        scene.set_nodes(
            [renamed_visible, offscreen],
            node_delta_payload={
                "kind": "node_delta",
                "reason": "targeted_node_payload",
                "nodes": [renamed_visible],
                "backdrop_nodes": [],
                "removed_node_ids": [],
                "added_node_ids": [],
                "visibility_may_change": False,
            },
        )

        self.assertIs(visible_nodes_model, bridge.visible_nodes_model)
        self.assertEqual(visible_nodes_model.payloads()[0]["title"], "Visible renamed")
        self.assertEqual(events, ["data"])
        delta_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertEqual(delta_diagnostics["query_count"], query_count)
        self.assertEqual(delta_diagnostics["nodes"]["rebuild_count"], rebuild_count)
        self.assertEqual(delta_diagnostics["delta_update_count"], 1)
        self.assertEqual(delta_diagnostics["delta_row_update_count"], 1)

    def test_offscreen_title_delta_is_noop_for_visible_and_projection_models(self) -> None:
        visible = _node_payload("visible", x=10.0, y=10.0)
        offscreen = _node_payload("offscreen", x=3000.0, y=0.0)
        scene = _SceneSource(nodes=[visible, offscreen])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        bridge.visible_nodes_model
        endpoint_before = bridge.edge_endpoint_nodes_model
        minimap_before = bridge.minimap_nodes_model
        bridge.locked_node_status_summary
        diagnostics_before = bridge.visible_scene_model_diagnostics
        endpoint_signals: list[str] = []
        minimap_signals: list[str] = []
        locked_signals: list[str] = []
        bridge.edge_endpoint_nodes_changed.connect(lambda: endpoint_signals.append("endpoint"))
        bridge.minimap_scene_model_changed.connect(lambda: minimap_signals.append("minimap"))
        bridge.locked_node_status_changed.connect(lambda: locked_signals.append("locked"))

        renamed_offscreen = dict(offscreen, title="Offscreen renamed")
        scene.set_nodes(
            [visible, renamed_offscreen],
            node_delta_payload=_node_delta(
                [renamed_offscreen],
                reason="title_payload_delta",
                visibility_may_change=False,
            ),
        )
        self.app.processEvents()

        diagnostics_after = bridge.visible_scene_model_diagnostics
        self.assertEqual(diagnostics_after["query_count"], diagnostics_before["query_count"])
        self.assertEqual(diagnostics_after["nodes"]["rebuild_count"], diagnostics_before["nodes"]["rebuild_count"])
        self.assertEqual(diagnostics_after["delta_fallback_count"], diagnostics_before["delta_fallback_count"])
        self.assertEqual(endpoint_signals, [])
        self.assertEqual(minimap_signals, [])
        self.assertEqual(locked_signals, [])
        self.assertEqual(bridge.edge_endpoint_nodes_model, endpoint_before)
        self.assertEqual(bridge.minimap_nodes_model, minimap_before)

    def test_stable_position_delta_updates_targeted_projections_with_data_only(self) -> None:
        visible = _node_payload("visible", x=10.0, y=10.0)
        offscreen = _node_payload("offscreen", x=3000.0, y=0.0)
        scene = _SceneSource(nodes=[visible, offscreen])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        visible_model = bridge.visible_nodes_model
        bridge.edge_endpoint_nodes_model
        bridge.minimap_nodes_model
        bridge.locked_node_status_summary
        model_events: list[str] = []
        endpoint_signals: list[str] = []
        minimap_signals: list[str] = []
        locked_signals: list[str] = []
        visible_model.dataChanged.connect(lambda *_args: model_events.append("data"))
        visible_model.modelReset.connect(lambda: model_events.append("reset"))
        visible_model.rowsInserted.connect(lambda *_args: model_events.append("insert"))
        visible_model.rowsRemoved.connect(lambda *_args: model_events.append("remove"))
        visible_model.rowsMoved.connect(lambda *_args: model_events.append("move"))
        bridge.edge_endpoint_nodes_changed.connect(lambda: endpoint_signals.append("endpoint"))
        bridge.minimap_scene_model_changed.connect(lambda: minimap_signals.append("minimap"))
        bridge.locked_node_status_changed.connect(lambda: locked_signals.append("locked"))

        moved_visible = dict(visible, x=48.0, y=32.0)
        scene.set_nodes(
            [moved_visible, offscreen],
            node_delta_payload=_node_delta([moved_visible]),
        )
        self.app.processEvents()

        self.assertEqual(model_events, ["data"])
        self.assertEqual(endpoint_signals, [])
        self.assertEqual(minimap_signals, ["minimap"])
        self.assertEqual(locked_signals, [])
        endpoint = next(payload for payload in bridge.edge_endpoint_nodes_model if payload["node_id"] == "visible")
        minimap = next(payload for payload in bridge.minimap_nodes_model if payload["node_id"] == "visible")
        self.assertEqual((endpoint["x"], endpoint["y"]), (48.0, 32.0))
        self.assertEqual((minimap["x"], minimap["y"]), (48.0, 32.0))

    def test_pure_addition_delta_appends_targeted_projections_without_endpoint_rebind(self) -> None:
        existing = _node_payload("existing", x=10.0, y=10.0)
        scene = _SceneSource(nodes=[existing])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 900.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        visible_model = bridge.visible_nodes_model
        bridge.edge_endpoint_nodes_model
        bridge.minimap_nodes_model
        bridge.locked_node_status_summary
        diagnostics_before = bridge.visible_scene_model_diagnostics
        inserted_ranges: list[tuple[int, int]] = []
        reset_events: list[str] = []
        endpoint_signals: list[str] = []
        minimap_signals: list[str] = []
        locked_signals: list[str] = []
        visible_model.rowsInserted.connect(
            lambda _parent, first, last: inserted_ranges.append((first, last))
        )
        visible_model.modelReset.connect(lambda: reset_events.append("reset"))
        bridge.edge_endpoint_nodes_changed.connect(lambda: endpoint_signals.append("endpoint"))
        bridge.minimap_scene_model_changed.connect(lambda: minimap_signals.append("minimap"))
        bridge.locked_node_status_changed.connect(lambda: locked_signals.append("locked"))

        first = _node_payload("first-added", x=220.0, y=10.0)
        second = _node_payload("second-added", x=440.0, y=10.0)
        scene.set_nodes(
            [existing, first, second],
            node_delta_payload=_node_delta(
                [first, second],
                reason="fragment_addition_delta",
                added_node_ids=["first-added", "second-added"],
                visibility_may_change=True,
            ),
        )
        self.app.processEvents()

        diagnostics_after = bridge.visible_scene_model_diagnostics
        self.assertEqual(inserted_ranges, [(1, 2)])
        self.assertEqual(reset_events, [])
        self.assertEqual(endpoint_signals, [])
        self.assertEqual(minimap_signals, ["minimap"])
        self.assertEqual(locked_signals, [])
        self.assertEqual(
            [payload["node_id"] for payload in bridge.edge_endpoint_nodes_model],
            ["existing", "first-added", "second-added"],
        )
        self.assertEqual(
            [payload["node_id"] for payload in bridge.minimap_nodes_model],
            ["existing", "first-added", "second-added"],
        )
        self.assertEqual(diagnostics_after["query_count"], diagnostics_before["query_count"])
        self.assertEqual(
            diagnostics_after["nodes"]["rebuild_count"],
            diagnostics_before["nodes"]["rebuild_count"],
        )

    def test_selection_reuses_inserted_rows_and_only_queries_for_missing_offscreen_nodes(self) -> None:
        visible = _node_payload("visible", x=10.0, y=10.0)
        offscreen = _node_payload("offscreen", x=4000.0, y=10.0)
        scene = _SceneSource(
            nodes=[visible, offscreen],
            selected_node_ids={"offscreen"},
        )
        view = _ViewportBridgeStub(
            {"x": -100.0, "y": -100.0, "width": 700.0, "height": 500.0}
        )
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        visible_model = bridge.visible_nodes_model
        query_count = bridge.visible_scene_model_diagnostics["query_count"]
        self.assertIn("offscreen", {payload["node_id"] for payload in visible_model})

        added = _node_payload("added", x=240.0, y=10.0)
        scene._selected_node_ids = {"added"}
        scene.set_nodes(
            [visible, offscreen, added],
            node_delta_payload=_node_delta(
                [added],
                reason="node_addition_delta",
                added_node_ids=["added"],
                visibility_may_change=True,
            ),
        )
        scene.selection_changed.emit()

        self.assertEqual(
            bridge.visible_scene_model_diagnostics["query_count"], query_count
        )
        self.assertEqual(
            {payload["node_id"] for payload in visible_model}, {"visible", "added"}
        )

        scene.select_node("offscreen")
        query_count_after_offscreen_selection = bridge.visible_scene_model_diagnostics[
            "query_count"
        ]
        self.assertGreater(query_count_after_offscreen_selection, query_count)
        self.assertIn("offscreen", {payload["node_id"] for payload in visible_model})

        scene.select_node("visible")
        self.assertEqual(
            bridge.visible_scene_model_diagnostics["query_count"],
            query_count_after_offscreen_selection,
        )
        self.assertNotIn("offscreen", {payload["node_id"] for payload in visible_model})

    def test_mixed_addition_delta_keeps_full_projection_fallback(self) -> None:
        existing = _node_payload("existing", x=10.0, y=10.0)
        scene = _SceneSource(nodes=[existing])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 700.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        bridge.visible_nodes_model
        bridge.edge_endpoint_nodes_model
        bridge.minimap_nodes_model
        bridge.locked_node_status_summary
        endpoint_signals: list[str] = []
        bridge.edge_endpoint_nodes_changed.connect(lambda: endpoint_signals.append("endpoint"))

        updated_existing = dict(existing, title="Existing updated")
        added = _node_payload("added", x=240.0, y=10.0)
        scene.set_nodes(
            [updated_existing, added],
            node_delta_payload=_node_delta(
                [updated_existing, added],
                reason="group_backdrop_addition_delta",
                added_node_ids=["added"],
                visibility_may_change=True,
            ),
        )

        self.assertEqual(endpoint_signals, ["endpoint"])
        self.assertEqual(
            [payload["node_id"] for payload in bridge.edge_endpoint_nodes_model],
            ["existing", "added"],
        )

    def test_state_bridge_groups_targeted_row_changes_without_structure_signals(self) -> None:
        first = _node_payload("first", x=10.0, y=10.0)
        second = _node_payload("second", x=220.0, y=10.0)
        scene = _SceneSource(nodes=[first, second])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 600.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        visible_model = bridge.visible_nodes_model
        structural_events: list[str] = []
        changed_ranges: list[tuple[int, int]] = []
        visible_model.modelReset.connect(lambda: structural_events.append("reset"))
        visible_model.rowsInserted.connect(lambda *_args: structural_events.append("insert"))
        visible_model.rowsRemoved.connect(lambda *_args: structural_events.append("remove"))
        visible_model.rowsMoved.connect(lambda *_args: structural_events.append("move"))
        visible_model.dataChanged.connect(
            lambda first_index, last_index, _roles: changed_ranges.append(
                (first_index.row(), last_index.row())
            )
        )

        updated_first = dict(first, title="First updated")
        updated_second = dict(second, title="Second updated")
        scene.set_nodes(
            [updated_first, updated_second],
            node_delta_payload=_node_delta(
                [updated_first, updated_second],
                visibility_may_change=False,
            ),
        )

        self.assertEqual(changed_ranges, [(0, 1)])
        self.assertEqual(structural_events, [])
        self.assertEqual(
            [payload["title"] for payload in visible_model.payloads()],
            ["First updated", "Second updated"],
        )

    def test_state_bridge_publishes_sparse_visible_badge_model(self) -> None:
        plain = _node_payload("plain", x=10.0, y=10.0)
        comment = dict(_node_payload("comment", x=220.0, y=10.0), comment_count=1, link_count=0)
        link = dict(_node_payload("link", x=10.0, y=140.0), comment_count=0, link_count=2)
        offscreen = dict(
            _node_payload("offscreen", x=3000.0, y=0.0),
            comment_count=1,
            link_count=1,
        )
        scene = _SceneSource(nodes=[plain, comment, link, offscreen])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 600.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)

        badge_model = bridge.visible_badge_nodes_model
        self.assertEqual(
            {payload["node_id"] for payload in badge_model.payloads()},
            {"comment", "link"},
        )
        self.assertEqual(_visible_node_ids(bridge), {"plain", "comment", "link"})
        self.assertEqual(bridge.visible_scene_node_payload("plain")["node_id"], "plain")

        badged_plain = dict(plain, comment_count=2, link_count=0)
        scene.set_nodes(
            [badged_plain, comment, link, offscreen],
            node_delta_payload=_node_delta([badged_plain], visibility_may_change=False),
        )

        self.assertIs(badge_model, bridge.visible_badge_nodes_model)
        self.assertEqual(
            {payload["node_id"] for payload in badge_model.payloads()},
            {"plain", "comment", "link"},
        )

        cleared_comment = dict(comment, comment_count=0)
        scene.set_nodes(
            [badged_plain, cleared_comment, link, offscreen],
            node_delta_payload=_node_delta([cleared_comment], visibility_may_change=False),
        )

        self.assertEqual(
            {payload["node_id"] for payload in badge_model.payloads()},
            {"plain", "link"},
        )

    def test_state_bridge_emits_workspace_changing_before_visible_model_clear(self) -> None:
        visible = _node_payload("visible", x=10.0, y=10.0)
        scene = _SceneSource(nodes=[visible])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        visible_model = bridge.visible_nodes_model
        self.assertEqual(visible_model.rowCount(), 1)

        events: list[tuple[str, str, int]] = []
        bridge.scene_workspace_changing.connect(
            lambda workspace_id: events.append(
                ("changing", str(workspace_id), visible_model.rowCount())
            )
        )
        bridge.scene_workspace_changed.connect(
            lambda: events.append(("changed", "", visible_model.rowCount()))
        )

        scene.workspace_id = "workspace-next"
        scene.workspace_changed.emit()

        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0], ("changing", "workspace-next", 1))
        self.assertEqual(events[1], ("changed", "", 0))

    def test_state_bridge_removes_visible_node_without_viewport_requery(self) -> None:
        visible = _node_payload("visible", x=10.0, y=10.0)
        offscreen = _node_payload("offscreen", x=3000.0, y=0.0)
        scene = _SceneSource(nodes=[visible, offscreen])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        visible_model = bridge.visible_nodes_model
        structural_events: list[str] = []
        visible_model.rowsRemoved.connect(lambda *_args: structural_events.append("remove"))
        visible_model.modelReset.connect(lambda: structural_events.append("reset"))

        self.assertEqual(_visible_node_ids(bridge), {"visible"})
        diagnostics = bridge.visible_scene_model_diagnostics
        query_count = diagnostics["query_count"]
        rebuild_count = diagnostics["nodes"]["rebuild_count"]

        moved_visible = dict(visible)
        moved_visible["x"] = 3000.0
        scene.set_nodes([moved_visible, offscreen], node_delta_payload=_node_delta([moved_visible]))

        self.assertEqual(_visible_node_ids(bridge), set())
        delta_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertEqual(delta_diagnostics["query_count"], query_count)
        self.assertEqual(delta_diagnostics["nodes"]["rebuild_count"], rebuild_count)
        self.assertEqual(delta_diagnostics["delta_update_count"], 1)
        self.assertEqual(delta_diagnostics["delta_fallback_count"], 0)
        self.assertEqual(structural_events, ["remove"])

    def test_state_bridge_updates_visible_node_with_visibility_flag_without_viewport_requery(self) -> None:
        visible = _node_payload("visible", x=10.0, y=10.0)
        offscreen = _node_payload("offscreen", x=3000.0, y=0.0)
        scene = _SceneSource(nodes=[visible, offscreen])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)

        visible_nodes_model = bridge.visible_nodes_model
        diagnostics = bridge.visible_scene_model_diagnostics
        query_count = diagnostics["query_count"]
        rebuild_count = diagnostics["nodes"]["rebuild_count"]

        moved_visible = dict(visible)
        moved_visible["x"] = 48.0
        moved_visible["title"] = "Still visible"
        scene.set_nodes([moved_visible, offscreen], node_delta_payload=_node_delta([moved_visible]))

        self.assertIs(visible_nodes_model, bridge.visible_nodes_model)
        self.assertEqual(_visible_node_ids(bridge), {"visible"})
        self.assertEqual(bridge.visible_nodes_model.payloads()[0]["title"], "Still visible")
        delta_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertEqual(delta_diagnostics["query_count"], query_count)
        self.assertEqual(delta_diagnostics["nodes"]["rebuild_count"], rebuild_count)
        self.assertEqual(delta_diagnostics["delta_update_count"], 1)
        self.assertEqual(delta_diagnostics["delta_fallback_count"], 0)

    def test_state_bridge_ignores_offscreen_to_offscreen_delta_without_viewport_requery(self) -> None:
        visible = _node_payload("visible", x=10.0, y=10.0)
        offscreen = _node_payload("offscreen", x=3000.0, y=0.0)
        scene = _SceneSource(nodes=[visible, offscreen])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)

        self.assertEqual(_visible_node_ids(bridge), {"visible"})
        diagnostics = bridge.visible_scene_model_diagnostics
        query_count = diagnostics["query_count"]
        rebuild_count = diagnostics["nodes"]["rebuild_count"]

        moved_offscreen = dict(offscreen)
        moved_offscreen["x"] = 3200.0
        scene.set_nodes([visible, moved_offscreen], node_delta_payload=_node_delta([moved_offscreen]))

        self.assertEqual(_visible_node_ids(bridge), {"visible"})
        delta_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertEqual(delta_diagnostics["query_count"], query_count)
        self.assertEqual(delta_diagnostics["nodes"]["rebuild_count"], rebuild_count)
        self.assertEqual(delta_diagnostics["delta_update_count"], 1)
        self.assertEqual(delta_diagnostics["delta_row_update_count"], 0)
        self.assertEqual(delta_diagnostics["delta_fallback_count"], 0)

    def test_state_bridge_falls_back_for_existing_offscreen_node_that_becomes_visible(self) -> None:
        visible = _node_payload("visible", x=10.0, y=10.0)
        offscreen = _node_payload("offscreen", x=3000.0, y=0.0)
        scene = _SceneSource(nodes=[visible, offscreen])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)

        self.assertEqual(_visible_node_ids(bridge), {"visible"})
        query_count = bridge.visible_scene_model_diagnostics["query_count"]

        moved_offscreen = dict(offscreen)
        moved_offscreen["x"] = 40.0
        scene.set_nodes([visible, moved_offscreen], node_delta_payload=_node_delta([moved_offscreen]))

        self.assertEqual(_visible_node_ids(bridge), {"visible", "offscreen"})
        fallback_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertGreater(fallback_diagnostics["query_count"], query_count)
        self.assertEqual(fallback_diagnostics["delta_fallback_count"], 1)

    def test_state_bridge_inserts_added_visible_node_without_viewport_requery(self) -> None:
        visible = _node_payload("visible", x=10.0, y=10.0)
        added = _node_payload("added", x=48.0, y=120.0)
        scene = _SceneSource(nodes=[visible])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        visible_nodes_model = bridge.visible_nodes_model

        diagnostics = bridge.visible_scene_model_diagnostics
        query_count = diagnostics["query_count"]
        rebuild_count = diagnostics["nodes"]["rebuild_count"]

        with patch.object(
            visible_nodes_model,
            "sync_payloads",
            side_effect=AssertionError("ordinary additions must not recompose the visible model"),
        ):
            scene.set_nodes([visible, added], node_delta_payload=_node_delta([added], added_node_ids=["added"]))

        self.assertEqual(_visible_node_ids(bridge), {"visible", "added"})
        delta_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertEqual(delta_diagnostics["query_count"], query_count)
        self.assertEqual(delta_diagnostics["nodes"]["rebuild_count"], rebuild_count)
        self.assertEqual(delta_diagnostics["delta_update_count"], 1)
        self.assertEqual(delta_diagnostics["delta_row_update_count"], 1)
        self.assertEqual(delta_diagnostics["delta_fallback_count"], 0)

    def test_qml_drop_preview_rejects_blank_payload_and_clears_on_scene_changes(self) -> None:
        scene = _SceneSource(nodes=[_node_payload("visible", x=0.0, y=0.0)])
        view = _ViewportBridgeStub({"x": -480.0, "y": -360.0, "width": 960.0, "height": 720.0})
        state_bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        command_bridge = GraphCanvasCommandBridge(view_bridge=view)

        engine = QQmlEngine()
        theme_bridge = ThemeBridge(theme_id="stitch_light")
        graph_theme_bridge = GraphThemeBridge(theme_id="graph_stitch_light")
        self.addCleanup(theme_bridge.deleteLater)
        self.addCleanup(graph_theme_bridge.deleteLater)
        engine.rootContext().setContextProperty("themeBridge", theme_bridge)
        engine.rootContext().setContextProperty("graphThemeBridge", graph_theme_bridge)
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

        drop_preview = canvas.findChild(QQuickItem, "graphCanvasDropPreview")
        self.assertIsNotNone(drop_preview)

        canvas.setProperty("dropPreviewNodePayload", {"ports": [], "properties": {}})
        self.app.processEvents()
        self.assertFalse(bool(_variant_value(drop_preview.property("visible"))))

        canvas.updateLibraryDropPreview(120.0, 140.0, {"ports": [], "properties": {}})
        self.app.processEvents()
        self.assertIsNone(_variant_value(canvas.property("dropPreviewNodePayload")))
        self.assertFalse(bool(_variant_value(drop_preview.property("visible"))))

        valid_payload = {"type_id": "io.path_pointer", "display_name": "Path Pointer", "ports": [], "properties": {}}

        canvas.updateLibraryDropPreview(120.0, 140.0, valid_payload)
        self.app.processEvents()
        self.assertIsNotNone(_variant_value(canvas.property("dropPreviewNodePayload")))
        self.assertTrue(bool(_variant_value(drop_preview.property("visible"))))

        scene.set_nodes([_node_payload("visible", x=24.0, y=0.0)])
        _wait_for(
            lambda: _variant_value(canvas.property("dropPreviewNodePayload")) is None,
            app=self.app,
            message="Scene node changes should clear stale drop-preview node cards.",
        )

        canvas.updateLibraryDropPreview(120.0, 140.0, valid_payload)
        self.app.processEvents()
        self.assertIsNotNone(_variant_value(canvas.property("dropPreviewNodePayload")))

        scene.set_edges([], {})
        _wait_for(
            lambda: _variant_value(canvas.property("dropPreviewNodePayload")) is None,
            app=self.app,
            message="Scene edge changes should clear stale drop-preview node cards.",
        )

        canvas.updateLibraryDropPreview(120.0, 140.0, valid_payload)
        self.app.processEvents()
        self.assertIsNotNone(_variant_value(canvas.property("dropPreviewNodePayload")))

        scene.workspace_changed.emit()
        _wait_for(
            lambda: _variant_value(canvas.property("dropPreviewNodePayload")) is None,
            app=self.app,
            message="Workspace changes should clear stale drop-preview node cards.",
        )

    def test_state_bridge_exposes_viewport_filtered_models_with_active_exceptions(self) -> None:
        scene = _SceneSource(
            nodes=[
                _node_payload("visible", x=10.0, y=10.0),
                _node_payload("padding-only", x=620.0, y=0.0),
                _node_payload("offscreen", x=3000.0, y=0.0),
                _node_payload("lookahead-only", x=3600.0, y=0.0),
                _node_payload("selected-offscreen", x=3400.0, y=0.0),
                _node_payload("failed-offscreen", x=3800.0, y=0.0),
                _node_payload("running-offscreen", x=4600.0, y=0.0),
                _node_payload("warning-offscreen", x=5000.0, y=0.0),
                _node_payload("hovered-offscreen", x=5400.0, y=0.0),
                _node_payload("context-offscreen", x=5800.0, y=0.0),
                _node_payload("pending-wire-offscreen", x=6200.0, y=0.0),
                _node_payload("drop-candidate-offscreen", x=6600.0, y=0.0),
                _node_payload("live-drag-offscreen", x=7000.0, y=0.0),
                _node_payload("resize-offscreen", x=7400.0, y=0.0),
            ],
            backdrops=[
                _backdrop_payload("backdrop-visible", x=-30.0, y=-30.0),
                _backdrop_payload("backdrop-offscreen", x=4200.0, y=0.0),
            ],
            selected_node_ids={"selected-offscreen"},
        )
        execution = _ExecutionSource(
            _RunState(
                failed_node_id="failed-offscreen",
                failed_node_title="Failed",
                running_node_ids={"running-offscreen"},
                warning_node_ids={"warning-offscreen"},
            )
        )
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(
            scene_bridge=scene,
            view_bridge=view,
            execution_source=execution,
        )
        bridge.set_visible_model_active_node_ids(
            [
                "hovered-offscreen",
                "context-offscreen",
                "pending-wire-offscreen",
                "drop-candidate-offscreen",
                "live-drag-offscreen",
                "resize-offscreen",
            ]
        )

        visible_nodes_model = bridge.visible_nodes_model
        self.assertEqual(
            {payload["node_id"] for payload in visible_nodes_model},
            {
                "visible",
                "padding-only",
                "selected-offscreen",
                "failed-offscreen",
                "running-offscreen",
                "warning-offscreen",
                "hovered-offscreen",
                "context-offscreen",
                "pending-wire-offscreen",
                "drop-candidate-offscreen",
                "live-drag-offscreen",
                "resize-offscreen",
            },
        )
        self.assertIs(visible_nodes_model, bridge.visible_nodes_model)
        self.assertEqual(visible_nodes_model.rowCount(), 12)
        self.assertEqual(
            {payload["node_id"] for payload in bridge.visible_backdrop_nodes_model},
            {"backdrop-visible"},
        )
        diagnostics = bridge.visible_scene_model_diagnostics
        self.assertEqual(diagnostics["nodes"]["full_count"], 14)
        self.assertEqual(diagnostics["nodes"]["visible_count"], 12)
        self.assertEqual(diagnostics["nodes"]["forced_visible_count"], 10)
        self.assertEqual(diagnostics["backdrops"]["full_count"], 2)
        self.assertEqual(diagnostics["backdrops"]["visible_count"], 1)
        self.assertGreaterEqual(diagnostics["query_count"], 2)
        self.assertEqual(diagnostics["cache_misses"], 2)
        self.assertGreaterEqual(diagnostics["query_ms"], 0.0)
        self.assertGreaterEqual(diagnostics["rebuild_ms"], 0.0)

        rebuild_count = diagnostics["nodes"]["rebuild_count"]
        query_count = diagnostics["query_count"]
        skipped_view_changes = diagnostics["skipped_view_change_count"]
        view.set_visible_scene_rect({"x": -80.0, "y": -100.0, "width": 500.0, "height": 500.0})
        self.assertIs(visible_nodes_model, bridge.visible_nodes_model)
        self.assertIn("visible", {payload["node_id"] for payload in bridge.visible_nodes_model})
        panned_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertEqual(panned_diagnostics["nodes"]["rebuild_count"], rebuild_count)
        self.assertEqual(panned_diagnostics["query_count"], query_count)
        self.assertGreater(
            panned_diagnostics["skipped_view_change_count"],
            skipped_view_changes,
        )
        self.assertFalse(panned_diagnostics["deferred"])

        view.set_visible_scene_rect({"x": 2800.0, "y": -100.0, "width": 500.0, "height": 500.0})
        motion_diagnostics = bridge.visible_scene_model_diagnostics
        motion_node_ids = {payload["node_id"] for payload in bridge.visible_nodes_model}
        self.assertFalse(motion_diagnostics["dirty"])
        self.assertFalse(motion_diagnostics["deferred"])
        self.assertGreater(motion_diagnostics["query_count"], query_count)
        self.assertIn("offscreen", motion_node_ids)
        self.assertIn("lookahead-only", motion_node_ids)
        self.assertNotIn("visible", motion_node_ids)
        self.assertIs(visible_nodes_model, bridge.visible_nodes_model)

        self.assertTrue(bridge.force_visible_scene_models_exact())
        exact_diagnostics = bridge.visible_scene_model_diagnostics
        self.assertFalse(exact_diagnostics["dirty"])
        self.assertFalse(exact_diagnostics["deferred"])
        self.assertGreater(exact_diagnostics["query_count"], query_count)
        self.assertGreaterEqual(exact_diagnostics["exact_refresh_count"], 1)
        self.assertIn("offscreen", {payload["node_id"] for payload in bridge.visible_nodes_model})
        self.assertNotIn("lookahead-only", {payload["node_id"] for payload in bridge.visible_nodes_model})
        self.assertNotIn("visible", {payload["node_id"] for payload in bridge.visible_nodes_model})
        self.assertLess(
            exact_diagnostics["query_rect"]["width"],
            motion_diagnostics["query_rect"]["width"],
        )
        self.assertLess(
            exact_diagnostics["query_rect"]["height"],
            motion_diagnostics["query_rect"]["height"],
        )

        self.assertEqual(
            {payload["node_id"] for payload in bridge.minimap_nodes_model},
            {
                "visible",
                "padding-only",
                "offscreen",
                "lookahead-only",
                "selected-offscreen",
                "failed-offscreen",
                "running-offscreen",
                "warning-offscreen",
                "hovered-offscreen",
                "context-offscreen",
                "pending-wire-offscreen",
                "drop-candidate-offscreen",
                "live-drag-offscreen",
                "resize-offscreen",
                "backdrop-visible",
                "backdrop-offscreen",
            },
        )

        view.set_visible_scene_rect({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge.force_visible_scene_models_exact()
        scene.set_nodes([_node_payload("replacement-visible", x=0.0, y=0.0)])
        self.assertEqual(
            {payload["node_id"] for payload in bridge.visible_nodes_model},
            {"replacement-visible"},
        )
        self.assertGreater(
            bridge.visible_scene_model_diagnostics["nodes"]["rebuild_count"],
            rebuild_count,
        )

    def test_state_bridge_caches_minimap_bounds_from_payloads(self) -> None:
        scene = _SceneSource(
            nodes=[
                _node_payload("a", x=0.0, y=0.0, width=100.0, height=50.0),
                _node_payload("b", x=300.0, y=200.0, width=100.0, height=100.0),
            ],
        )
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)

        self.assertEqual(
            bridge.workspace_scene_bounds_payload,
            {"x": -1400.0, "y": -750.0, "width": 3200.0, "height": 1800.0},
        )

        scene.set_nodes([_node_payload("c", x=1000.0, y=1000.0, width=200.0, height=100.0)])

        self.assertEqual(
            bridge.workspace_scene_bounds_payload,
            {"x": -500.0, "y": 150.0, "width": 3200.0, "height": 1800.0},
        )

    def test_state_bridge_edge_endpoint_model_is_compact_all_node_projection(self) -> None:
        visible = _node_payload("visible", x=0.0, y=0.0)
        visible.update(
            {
                "display_name": "Visible Node",
                "properties": {"title": "Visible"},
                "visual_style": {"fill": "#ffffff"},
                "render_quality": {"supported_quality_tiers": ["full", "proxy"]},
                "viewer_surface": {"width": 320.0},
                "surface_metrics": {"port_top": 40.0, "port_height": 20.0, "port_side_margin": 8.0},
                "ports": [
                    {
                        "key": "value",
                        "label": "Value",
                        "direction": "out",
                        "kind": "data",
                        "data_type": "any",
                        "side": "right",
                        "exposed": True,
                        "layout_row": 3,
                        "handle_visible": False,
                        "presentation_anchor": {"side": "left", "x": 0.0, "y": 72.0, "aggregate": True},
                        "connection_count": 1,
                    }
                ],
            }
        )
        offscreen = _node_payload("offscreen", x=5000.0, y=5000.0)
        scene = _SceneSource(nodes=[visible, offscreen])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 500.0, "height": 500.0})
        bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)

        endpoints = bridge.edge_endpoint_nodes_model

        self.assertEqual({payload["node_id"] for payload in endpoints}, {"visible", "offscreen"})
        visible_endpoint = next(payload for payload in endpoints if payload["node_id"] == "visible")
        for key in (
            "node_id",
            "x",
            "y",
            "width",
            "height",
            "collapsed",
            "read_only",
            "unresolved",
            "surface_family",
            "surface_variant",
            "surface_metrics",
            "ports",
        ):
            self.assertIn(key, visible_endpoint)
        self.assertEqual(
            visible_endpoint["ports"],
            [
                {
                    "key": "value",
                    "direction": "out",
                    "side": "right",
                    "exposed": True,
                    "layout_row": 3,
                    "handle_visible": False,
                    "presentation_anchor": {"side": "left", "x": 0.0, "y": 72.0, "aggregate": True},
                }
            ],
        )
        for heavy_key in (
            "title",
            "display_name",
            "properties",
            "visual_style",
            "render_quality",
            "viewer_surface",
            "icon_source",
        ):
            self.assertNotIn(heavy_key, visible_endpoint)

    def test_selected_run_preview_overlay_shrinks_and_expands_overflow_rows(self) -> None:
        preview_rows = (
            {"section": "Will run", "title": "Publish Report", "tone": "run"},
            {"section": "Will run", "title": "Generate report", "tone": "run"},
            {"section": "Will run", "title": "Run solver", "tone": "run"},
            {"section": "Will run", "title": "Fetch inputs", "tone": "run"},
            {"section": "Will run", "title": "Normalize inputs", "tone": "run"},
            {"section": "Will run", "title": "Load geometry", "tone": "run"},
            {"section": "Will run", "title": "Read settings", "tone": "run"},
            {"section": "Will run", "title": "Validate inputs", "tone": "run"},
            {"section": "Will run", "title": "Prepare output", "tone": "run"},
            {"section": "Will run", "title": "Save report", "tone": "run"},
        )
        scene = _SceneSource(nodes=[_node_payload("visible", x=0.0, y=0.0)])
        execution = _ExecutionSource(
            _RunState(
                selected_run_preview_rows=preview_rows,
                selected_run_preview_node_lookup={"visible": "run"},
                selected_run_preview_revision=1,
            )
        )
        view = _ViewportBridgeStub({"x": -480.0, "y": -360.0, "width": 960.0, "height": 720.0})
        state_bridge = GraphCanvasStateBridge(
            scene_bridge=scene,
            view_bridge=view,
            execution_source=execution,
        )
        command_bridge = GraphCanvasCommandBridge(view_bridge=view)

        engine = QQmlEngine()
        theme_bridge = ThemeBridge(theme_id="stitch_light")
        graph_theme_bridge = GraphThemeBridge(theme_id="graph_stitch_light")
        self.addCleanup(theme_bridge.deleteLater)
        self.addCleanup(graph_theme_bridge.deleteLater)
        engine.rootContext().setContextProperty("themeBridge", theme_bridge)
        engine.rootContext().setContextProperty("graphThemeBridge", graph_theme_bridge)
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

        overlay = canvas.findChild(QObject, "selectedRunPreviewOverlay")
        more_toggle = canvas.findChild(QQuickItem, "selectedRunPreviewMoreToggle")
        more_text = canvas.findChild(QQuickItem, "selectedRunPreviewMoreText")
        row_list = canvas.findChild(QQuickItem, "selectedRunPreviewList")
        self.assertIsNotNone(overlay)
        self.assertIsNotNone(more_toggle)
        self.assertIsNotNone(more_text)
        self.assertIsNotNone(row_list)

        _wait_for(
            lambda: bool(overlay.property("visible")),
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for selected run preview overlay.",
        )
        row_labels = _named_child_items(canvas, "selectedRunPreviewRowLabel")
        self.assertGreater(len(row_labels), 0)
        row_label = row_labels[0]

        self.assertLess(float(overlay.property("width")), 400.0)
        self.assertFalse(bool(overlay.property("expanded")))
        self.assertEqual(int(overlay.property("hiddenRowCount")), 2)
        self.assertEqual(len(list(_variant_value(overlay.property("visibleRows")))), 8)
        self.assertEqual(str(more_text.property("text")), "+2 more")
        self.assertEqual(_color_name(row_label.property("color")), STITCH_LIGHT_V1.panel_fg)

        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            _item_scene_point(more_toggle),
        )
        _wait_for(
            lambda: bool(overlay.property("expanded")),
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for selected run preview overflow expansion.",
        )

        self.assertEqual(len(list(_variant_value(overlay.property("visibleRows")))), len(preview_rows))
        self.assertEqual(str(more_text.property("text")), "Show fewer")
        self.assertGreater(float(row_list.property("contentHeight")), float(row_list.property("height")))
        self.assertTrue(bool(row_list.property("interactive")))

        before_content_y = float(row_list.property("contentY"))
        wheel_point = _item_scene_point(row_list)
        wheel_event = QWheelEvent(
            QPointF(float(wheel_point.x()), float(wheel_point.y())),
            QPointF(float(wheel_point.x()), float(wheel_point.y())),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QCoreApplication.sendEvent(window, wheel_event)
        self.app.processEvents()

        self.assertTrue(wheel_event.isAccepted())
        self.assertGreater(float(row_list.property("contentY")), before_content_y)
        self.assertEqual(view.zoom_adjust_calls, [])

    def test_qml_world_layers_use_bridge_visible_delegate_models_and_host_map(self) -> None:
        root_layers_source = (
            _REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph_canvas"
            / "GraphCanvasRootLayers.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("visible_nodes_model", root_layers_source)
        self.assertIn("visible_backdrop_nodes_model", root_layers_source)
        self.assertIn("set_visible_model_active_node_ids", root_layers_source)
        self.assertIn("force_visible_scene_models_exact", root_layers_source)
        self.assertIn("visibleModelIdleRefreshTimer", root_layers_source)
        self.assertNotIn("selected_node_lookup", root_layers_source)
        self.assertIn("edge_endpoint_nodes_model", root_layers_source)
        self.assertIn("stable_edge_endpoint_nodes_model", root_layers_source)
        self.assertIn("node_delta_payload", root_layers_source)
        self.assertIn("root.sceneStateBridge.nodes_model", root_layers_source)
        self.assertNotIn("fullNodesModel", root_layers_source)
        self.assertNotIn("fullBackdropNodesModel", root_layers_source)
        self.assertNotIn("_filteredVisibleNodeModel", root_layers_source)

        edge_layer_source = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph" / "EdgeLayer.qml"
        ).read_text(encoding="utf-8")
        edge_cache_source = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph" / "EdgeSnapshotCache.js"
        ).read_text(encoding="utf-8")
        self.assertIn("onNodeDeltaPayloadChanged", edge_layer_source)
        self.assertIn("applyNodePayloadDelta", edge_cache_source)

        canvas_source = (
            _REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "GraphCanvas.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("locked_node_status_summary", canvas_source)
        self.assertNotIn("sceneNodesModel", canvas_source)

        world_layer_source = (
            _REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph_canvas"
            / "GraphCanvasWorldLayer.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("root._hostByNodeId[nodeId] = item", world_layer_source)
        self.assertIn("delete root._hostByNodeId[nodeId]", world_layer_source)

        visible_id = "visible"
        lookahead_id = "lookahead"
        offscreen_id = "offscreen"
        selected_id = "selected-offscreen"
        context_id = "context-offscreen"
        backdrop_visible_id = "backdrop-visible"
        backdrop_offscreen_id = "backdrop-offscreen"
        scene = _SceneSource(
            nodes=[
                _node_payload(visible_id, x=0.0, y=0.0),
                _node_payload(lookahead_id, x=1080.0, y=0.0),
                _node_payload(offscreen_id, x=4600.0, y=0.0),
                _node_payload(selected_id, x=5000.0, y=0.0),
                _node_payload(context_id, x=5400.0, y=0.0),
            ],
            backdrops=[
                _backdrop_payload(backdrop_visible_id, x=40.0, y=40.0),
                _backdrop_payload(backdrop_offscreen_id, x=5800.0, y=0.0),
            ],
            selected_node_ids={selected_id},
        )
        view = _ViewportBridgeStub({"x": -480.0, "y": -360.0, "width": 960.0, "height": 720.0})
        state_bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        command_bridge = GraphCanvasCommandBridge(view_bridge=view)

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

        canvas.setProperty("nodeContextNodeId", context_id)
        canvas.setProperty("nodeContextVisible", True)
        root_layers = canvas.findChild(QObject, "graphCanvasRootLayers")
        self.assertIsNotNone(root_layers)

        _wait_for(
            lambda: int(root_layers.property("profileVisibleNodeDelegateCount")) == 3
            and int(root_layers.property("profileVisibleBackdropDelegateCount")) == 1,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for viewport-filtered node delegates.",
        )

        self.assertEqual(int(root_layers.property("profileTotalNodeCount")), 7)
        self.assertEqual(int(root_layers.property("profileVisibleNodeDelegateCount")), 3)
        self.assertEqual(int(root_layers.property("profileVisibleBackdropDelegateCount")), 1)
        self.assertGreaterEqual(float(root_layers.property("profileLastVisibleModelQueryMs")), 0.0)
        self.assertGreaterEqual(int(root_layers.property("profileVisibleModelQueryCount")), 1)
        self.assertGreaterEqual(int(root_layers.property("profileDelegateCreateCount")), 4)
        self.assertGreaterEqual(int(root_layers.property("profileDelegateDestroyCount")), 0)
        self.assertIsNotNone(_node_host(canvas, visible_id))
        self.assertIsNotNone(_node_host(canvas, selected_id))
        self.assertIsNotNone(_node_host(canvas, context_id))
        self.assertIsNotNone(_node_host(canvas, backdrop_visible_id))
        self.assertIsNotNone(
            _node_host(canvas, backdrop_visible_id, object_name="graphGroupBackdropInputCard")
        )
        self.assertIsNone(_node_host(canvas, offscreen_id))
        self.assertIsNone(_node_host(canvas, lookahead_id))
        self.assertIsNone(_node_host(canvas, backdrop_offscreen_id))

        host_for_visible = canvas.hostForNodeId(visible_id)
        host_for_offscreen = canvas.hostForNodeId(offscreen_id)
        self.assertIsNotNone(host_for_visible)
        self.assertIsNone(host_for_offscreen)

        initial_create_count = int(root_layers.property("profileDelegateCreateCount"))
        initial_destroy_count = int(root_layers.property("profileDelegateDestroyCount"))
        view.set_visible_scene_rect({"x": 0.0, "y": -360.0, "width": 960.0, "height": 720.0})
        _wait_for(
            lambda: _node_host(canvas, lookahead_id) is not None,
            app=self.app,
            message="Timed out waiting for the look-ahead host to preload.",
        )
        lookahead_host = _node_host(canvas, lookahead_id)
        self.assertIsNotNone(lookahead_host)
        self.assertFalse(bool(lookahead_host.property("inVisibleViewport")))
        lookahead_loader = lookahead_host.findChild(QObject, "graphNodeSurfaceLoader")
        self.assertIsNotNone(lookahead_loader)
        _wait_for(
            lambda: bool(lookahead_loader.property("surfaceLoaded"))
            and lookahead_host.findChild(QObject, "graphNodeStandardSurface") is not None,
            app=self.app,
            message="Timed out waiting for the look-ahead surface to preload asynchronously.",
        )
        lookahead_surface = lookahead_host.findChild(QObject, "graphNodeStandardSurface")
        self.assertIsNotNone(lookahead_surface)
        self.assertTrue(bool(lookahead_loader.property("surfaceLoaded")))
        self.assertIs(_node_host(canvas, visible_id), host_for_visible)
        self.assertGreater(int(root_layers.property("profileDelegateCreateCount")), initial_create_count)
        self.assertEqual(int(root_layers.property("profileDelegateDestroyCount")), initial_destroy_count)

        preloaded_create_count = int(root_layers.property("profileDelegateCreateCount"))
        preloaded_destroy_count = int(root_layers.property("profileDelegateDestroyCount"))
        view.set_visible_scene_rect({"x": 200.0, "y": -360.0, "width": 960.0, "height": 720.0})
        _wait_for(
            lambda: bool(lookahead_host.property("inVisibleViewport"))
            and not bool(host_for_visible.property("inVisibleViewport")),
            app=self.app,
            message="Timed out waiting for exact viewport facts to cross the preloaded hosts.",
        )
        self.assertIs(_node_host(canvas, lookahead_id), lookahead_host)
        self.assertIs(lookahead_host.findChild(QObject, "graphNodeStandardSurface"), lookahead_surface)
        self.assertTrue(bool(lookahead_loader.property("surfaceLoaded")))
        self.assertIs(_node_host(canvas, visible_id), host_for_visible)
        self.assertEqual(int(root_layers.property("profileDelegateCreateCount")), preloaded_create_count)
        self.assertEqual(int(root_layers.property("profileDelegateDestroyCount")), preloaded_destroy_count)

        view.set_visible_scene_rect({"x": 2800.0, "y": -360.0, "width": 960.0, "height": 720.0})
        _wait_for(
            lambda: _node_host(canvas, visible_id) is None
            and _node_host(canvas, lookahead_id) is None,
            app=self.app,
            message="Timed out waiting for far-behind hosts to unload.",
        )
        self.assertGreater(int(root_layers.property("profileDelegateDestroyCount")), preloaded_destroy_count)

    def test_qml_node_only_scene_mutation_does_not_replace_edge_payload(self) -> None:
        source_node = _node_payload("source", x=0.0, y=0.0)
        target_node = _node_payload("target", x=320.0, y=0.0)
        edge_a = _edge_payload("edge-a")
        scene = _SceneSource(nodes=[source_node, target_node], edges=[edge_a])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 640.0, "height": 480.0})
        state_bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        command_bridge = GraphCanvasCommandBridge(view_bridge=view)

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
            "width": 640.0,
            "height": 480.0,
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
        window.resize(640, 480)
        canvas.setParentItem(window.contentItem())
        window.show()
        self.addCleanup(window.close)

        edge_layer = canvas.findChild(QObject, "graphCanvasEdgeLayer")
        self.assertIsNotNone(edge_layer)
        root_layers = canvas.findChild(QObject, "graphCanvasRootLayers")
        self.assertIsNotNone(root_layers)
        _wait_for(
            lambda: _edge_ids(canvas.property("edgePayload")) == ["edge-a"]
            and _edge_ids(edge_layer.property("edges")) == ["edge-a"],
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for initial edge payload assignment.",
        )

        edge_payload_replacements: list[list[str]] = []
        endpoint_projection_rebinds: list[str] = []
        canvas.edgePayloadChanged.connect(  # type: ignore[attr-defined]
            lambda: edge_payload_replacements.append(_edge_ids(canvas.property("edgePayload")))
        )
        edge_layer.nodesChanged.connect(lambda: endpoint_projection_rebinds.append("nodes"))  # type: ignore[attr-defined]
        delegate_create_count = int(root_layers.property("profileDelegateCreateCount"))
        delegate_destroy_count = int(root_layers.property("profileDelegateDestroyCount"))

        renamed_target = dict(target_node)
        renamed_target["title"] = "Target renamed"
        scene.set_nodes(
            [source_node, renamed_target],
            node_delta_payload={
                "kind": "node_delta",
                "reason": "title_payload_delta",
                "nodes": [renamed_target],
                "backdrop_nodes": [],
                "removed_node_ids": [],
                "added_node_ids": [],
                "visibility_may_change": False,
            },
        )

        _wait_for(
            lambda: (
                (host := _node_host(canvas, "target")) is not None
                and _variant_value(host.property("nodeData")).get("title") == "Target renamed"
            ),
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for node-only payload update.",
        )
        self.assertEqual(_edge_ids(canvas.property("edgePayload")), ["edge-a"])
        self.assertEqual(_edge_ids(edge_layer.property("edges")), ["edge-a"])
        self.assertEqual(edge_payload_replacements, [])
        self.assertEqual(endpoint_projection_rebinds, [])
        node_delta_by_id = _variant_value(edge_layer.property("_nodePayloadDeltaById"))
        self.assertEqual(node_delta_by_id["target"]["title"], "Target renamed")
        self.assertEqual(int(root_layers.property("profileDelegateCreateCount")), delegate_create_count)
        self.assertEqual(int(root_layers.property("profileDelegateDestroyCount")), delegate_destroy_count)

        state_bridge.edge_endpoint_nodes_model
        state_bridge.minimap_nodes_model
        state_bridge.locked_node_status_summary
        added_node = _node_payload("added", x=160.0, y=180.0)
        scene.set_nodes(
            [source_node, renamed_target, added_node],
            node_delta_payload=_node_delta(
                [added_node],
                reason="node_addition_delta",
                added_node_ids=["added"],
                visibility_may_change=True,
            ),
        )
        _wait_for(
            lambda: _node_host(canvas, "added") is not None,
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for the incrementally added node delegate.",
        )
        self.assertEqual(endpoint_projection_rebinds, [])
        node_delta_by_id = _variant_value(edge_layer.property("_nodePayloadDeltaById"))
        self.assertEqual(node_delta_by_id["added"]["node_id"], "added")
        self.assertEqual(int(root_layers.property("profileDelegateDestroyCount")), delegate_destroy_count)

    def test_qml_edge_payload_structural_deltas_mutate_in_place_without_payload_reset(self) -> None:
        source_node = _node_payload("source", x=0.0, y=0.0)
        target_node = _node_payload("target", x=320.0, y=0.0)
        port_metrics = {
            "body_top": 0.0,
            "body_height": 0.0,
            "port_top": 20.0,
            "port_height": 20.0,
            "port_center_offset": 10.0,
            "port_side_margin": 8.0,
            "port_dot_radius": 4.0,
        }
        source_node["surface_metrics"] = dict(port_metrics)
        source_node["ports"] = [
            {"key": "value", "direction": "out", "side": "", "exposed": True, "layout_row": 0}
        ]
        target_node["surface_metrics"] = dict(port_metrics)
        target_node["ports"] = [
            {"key": "payload", "direction": "in", "side": "", "exposed": True, "layout_row": 2},
            {
                "key": "path",
                "direction": "in",
                "side": "",
                "exposed": True,
                "layout_row": 0,
                "handle_visible": False,
                "presentation_anchor": {"side": "left", "x": 0.0, "y": 75.0, "aggregate": True},
            },
        ]
        edge_a = _edge_payload("edge-a")
        scene = _SceneSource(nodes=[source_node, target_node], edges=[edge_a])
        view = _ViewportBridgeStub({"x": -100.0, "y": -100.0, "width": 640.0, "height": 480.0})
        state_bridge = GraphCanvasStateBridge(scene_bridge=scene, view_bridge=view)
        command_bridge = GraphCanvasCommandBridge(view_bridge=view)

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
            "width": 640.0,
            "height": 480.0,
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
        window.resize(640, 480)
        canvas.setParentItem(window.contentItem())
        window.show()
        self.addCleanup(window.close)

        edge_layer = canvas.findChild(QObject, "graphCanvasEdgeLayer")
        self.assertIsNotNone(edge_layer)
        _wait_for(
            lambda: _edge_ids(canvas.property("edgePayload")) == ["edge-a"]
            and _edge_ids(edge_layer.property("edges")) == ["edge-a"],
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for initial edge payload assignment.",
        )

        edge_payload_replacements: list[list[str]] = []
        canvas.edgePayloadChanged.connect(  # type: ignore[attr-defined]
            lambda: edge_payload_replacements.append(_edge_ids(canvas.property("edgePayload")))
        )

        def _delta(
            sequence: int,
            *,
            edge_count_after: int,
            added_edges: list[dict[str, Any]] | None = None,
            updated_edges: list[dict[str, Any]] | None = None,
            removed_edge_ids: list[str] | None = None,
        ) -> dict[str, Any]:
            added_edge_ids = [str(entry["edge_id"]) for entry in added_edges or []]
            updated_edge_ids = [str(entry["edge_id"]) for entry in updated_edges or []]
            removed_ids = list(removed_edge_ids or [])
            return {
                "schema": "graph_scene_edge_structural_delta",
                "version": 1,
                "sequence": sequence,
                "reason": "edge_topology",
                "requires_full_refresh": False,
                "edge_count_after": edge_count_after,
                "added_edge_ids": added_edge_ids,
                "updated_edge_ids": updated_edge_ids,
                "removed_edge_ids": removed_ids,
                "dirty_edge_ids": [*added_edge_ids, *updated_edge_ids, *removed_ids],
                "dirty_node_ids": ["source", "target"],
                "removed_node_ids": [],
                "affected_node_ids": ["source", "target"],
                "added_edges": added_edges or [],
                "updated_edges": updated_edges or [],
                "removed_edges": [{"edge_id": edge_id} for edge_id in removed_ids],
            }

        def _entry(index: int, payload: dict[str, Any]) -> dict[str, Any]:
            return {"edge_id": payload["edge_id"], "index": index, "payload": payload}

        def _wait_for_edge_ids(expected: list[str]) -> None:
            _wait_for(
                lambda: _edge_ids(canvas.property("edgePayload")) == expected
                and _edge_ids(edge_layer.property("edges")) == expected,
                timeout_ms=1500,
                app=self.app,
                message=f"Timed out waiting for edge payload ids {expected!r}.",
            )

        edge_b = _edge_payload("edge-b", sy=160.0, ty=160.0)
        edge_b.update(
            {
                "source_anchor_kind": "node",
                "target_anchor_kind": "node",
                "target_port_key": "path",
            }
        )
        scene.set_edges(
            [edge_a, edge_b],
            _delta(1, edge_count_after=2, added_edges=[_entry(1, edge_b)]),
        )
        _wait_for_edge_ids(["edge-a", "edge-b"])
        _wait_for(
            lambda: isinstance(_variant_value(edge_layer._visibleEdgeSnapshot("edge-b")), dict),
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for the newly added edge snapshot.",
        )
        edge_b_snapshot = _variant_value(edge_layer._visibleEdgeSnapshot("edge-b"))
        self.assertAlmostEqual(float(edge_b_snapshot["geometry"]["ty"]), 75.0, places=6)

        moved_edge_a = dict(edge_a)
        moved_edge_a["label"] = "Updated edge"
        moved_edge_a["tx"] = 280.0
        moved_edge_a["c2x"] = 208.0
        scene.set_edges(
            [moved_edge_a, edge_b],
            _delta(2, edge_count_after=2, updated_edges=[_entry(0, moved_edge_a)]),
        )
        _wait_for(
            lambda: _variant_value(canvas.property("edgePayload"))[0]["label"] == "Updated edge",
            timeout_ms=1500,
            app=self.app,
            message="Timed out waiting for in-place edge payload update.",
        )

        scene.set_edges(
            [moved_edge_a],
            _delta(3, edge_count_after=1, removed_edge_ids=["edge-b"]),
        )
        _wait_for_edge_ids(["edge-a"])

        scene.set_edges([], _delta(4, edge_count_after=0, removed_edge_ids=["edge-a"]))
        _wait_for_edge_ids([])

        edge_c = _edge_payload("edge-c", sy=220.0, ty=220.0)
        scene.set_edges(
            [edge_c],
            _delta(5, edge_count_after=1, added_edges=[_entry(0, edge_c)]),
        )
        _wait_for_edge_ids(["edge-c"])

        self.assertEqual(edge_payload_replacements, [])


if __name__ == "__main__":
    unittest.main()
