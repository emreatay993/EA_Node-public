from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import patch

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtQuick import QQuickItem
from PyQt6.QtWidgets import QWidget

from ea_node_editor.nodes.builtins.engineering_viewer import ENGINEERING_VIEWER_NODE_TYPE_ID
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.node_specs import (
    NodeRenderQualitySpec,
    NodeTypeSpec,
    PortSpec,
)
from ea_node_editor.ui_qml.embedded_viewer_overlay_manager import (
    EmbeddedViewerOverlayManager,
    EmbeddedViewerOverlaySpec,
    _OverlayRecord,
)
from ea_node_editor.ui_qml.qml_host_factory import QML_HOST_ENV, QML_HOST_QQUICKVIEW_CONTAINER
from tests.main_window_shell.base import MainWindowShellTestBase
from tests.qt_wait import wait_for_condition_or_raise


class _ViewerOverlayPlugin:
    def __init__(self, spec: NodeTypeSpec) -> None:
        self._spec = spec

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult()


def _viewer_overlay_spec() -> NodeTypeSpec:
    return NodeTypeSpec(
        type_id="tests.embedded_viewer_overlay",
        display_name="Embedded Viewer Overlay",
        category_path=("Tests",),
        icon="",
        ports=(
            PortSpec("scene", "in", "data", "COREX.Engineering.Scene", required=False),
            PortSpec("session", "out", "data", 'COREX.Viewer.Session'),
        ),
        properties=(),
        surface_family="viewer",
        render_quality=NodeRenderQualitySpec(
            supported_quality_tiers=("full", "proxy"),
        ),
    )


class _FakeOverlayWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.close_calls = 0

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self.close_calls += 1
        super().closeEvent(event)


class _CountingWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.move_calls = 0
        self.resize_calls = 0
        self.set_geometry_calls = 0
        self.raise_calls = 0

    def move(self, *args) -> None:  # noqa: ANN002
        self.move_calls += 1
        super().move(*args)

    def resize(self, *args) -> None:  # noqa: ANN002
        self.resize_calls += 1
        super().resize(*args)

    def setGeometry(self, *args) -> None:  # noqa: ANN002, N802
        self.set_geometry_calls += 1
        super().setGeometry(*args)

    def raise_(self) -> None:
        self.raise_calls += 1
        super().raise_()

    def reset_counts(self) -> None:
        self.move_calls = 0
        self.resize_calls = 0
        self.set_geometry_calls = 0
        self.raise_calls = 0


class EmbeddedViewerOverlayManagerTests(MainWindowShellTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.window.registry.register(lambda: _ViewerOverlayPlugin(_viewer_overlay_spec()))
        self.manager = self.window.embedded_viewer_overlay_manager
        self.assertIsNotNone(self.manager)
        self.workspace_id = self.window.workspace_manager.active_workspace_id()

    def _graph_canvas_quick_item(self) -> QQuickItem:
        canvas = self._graph_canvas_item()
        self.assertIsInstance(canvas, QQuickItem)
        return canvas

    def _walk_items(self, item: QQuickItem):
        yield item
        for child in item.childItems():
            if isinstance(child, QQuickItem):
                yield from self._walk_items(child)

    def _graph_node_card(self, node_id: str) -> QQuickItem:
        for item in self._walk_items(self._graph_canvas_quick_item()):
            if item.objectName() != "graphNodeCard":
                continue
            node_data = item.property("nodeData") or {}
            if str(node_data.get("node_id", "")) == node_id:
                return item
        self.fail(f"Missing graphNodeCard for {node_id!r}")

    def _graph_viewer_body_frame(self, node_id: str) -> QQuickItem:
        node_card = self._graph_node_card(node_id)
        for item in self._walk_items(node_card):
            if item.objectName() == "graphNodeViewerBodyFrame":
                return item
        self.fail(f"Missing graphNodeViewerBodyFrame for {node_id!r}")

    def _graph_viewer_viewport(self, node_id: str) -> QQuickItem:
        node_card = self._graph_node_card(node_id)
        for item in self._walk_items(node_card):
            if item.objectName() == "graphNodeViewerViewport":
                return item
        self.fail(f"Missing graphNodeViewerViewport for {node_id!r}")

    def _content_fullscreen_viewer_viewport(self) -> QQuickItem:
        root_item = self.window.quick_widget.rootObject()
        self.assertIsInstance(root_item, QQuickItem)
        item = root_item.findChild(QObject, "contentFullscreenViewerViewport")
        self.assertIsInstance(item, QQuickItem)
        return item

    def _add_viewer_node(
        self,
        *,
        x: float = 160.0,
        y: float = 90.0,
        width: float = 360.0,
        height: float = 280.0,
    ) -> str:
        node_id = self.window.scene.add_node_from_type("tests.embedded_viewer_overlay", x=x, y=y)
        self.window.scene.resize_node(node_id, width, height)
        self.window.view.set_view_state(1.0, x + (width * 0.5), y + (height * 0.5))
        self.app.processEvents()
        return node_id

    def _add_viewer_node(
        self,
        *,
        x: float = 160.0,
        y: float = 90.0,
        width: float = 360.0,
        height: float = 280.0,
    ) -> str:
        node_id = self.window.scene.add_node_from_type(ENGINEERING_VIEWER_NODE_TYPE_ID, x=x, y=y)
        self.window.scene.resize_node(node_id, width, height)
        self.window.view.set_view_state(1.0, x + (width * 0.5), y + (height * 0.5))
        self.app.processEvents()
        return node_id

    def _add_plot_node(
        self,
        *,
        x: float = 160.0,
        y: float = 90.0,
        width: float = 360.0,
        height: float = 280.0,
    ) -> str:
        node_id = self.window.scene.add_node_from_type("plot.scatter", x=x, y=y)
        self.window.scene.resize_node(node_id, width, height)
        self.window.view.set_view_state(1.0, x + (width * 0.5), y + (height * 0.5))
        self.app.processEvents()
        return node_id

    def _node_payload(self, node_id: str) -> dict[str, Any]:
        for payload in self.window.scene.nodes_model:
            if str(payload.get("node_id", "")) == node_id:
                return dict(payload)
        self.fail(f"Missing node payload for {node_id}")

    def _mapping(self, value: Any) -> dict[str, Any]:
        normalized = value.toVariant() if hasattr(value, "toVariant") else value
        if isinstance(normalized, dict):
            return dict(normalized)
        if hasattr(normalized, "items"):
            try:
                return dict(normalized.items())
            except Exception:  # noqa: BLE001
                return {}
        return {}

    def _expected_node_scene_geometry(self, node_id: str) -> dict[str, float]:
        node_payload = self._node_payload(node_id)
        scene_x = float(node_payload.get("x", 0.0))
        scene_y = float(node_payload.get("y", 0.0))
        scene_width = max(0.0, float(node_payload.get("width", 0.0)))
        scene_height = max(0.0, float(node_payload.get("height", 0.0)))

        graph_canvas = self._graph_canvas_quick_item()
        live_geometry_by_id = self._mapping(graph_canvas.property("liveNodeGeometry"))
        live_geometry = self._mapping(live_geometry_by_id.get(node_id))
        if live_geometry:
            return {
                "x": float(live_geometry.get("x", scene_x)),
                "y": float(live_geometry.get("y", scene_y)),
                "width": max(0.0, float(live_geometry.get("width", scene_width))),
                "height": max(0.0, float(live_geometry.get("height", scene_height))),
            }

        live_drag_node_lookup = self._mapping(graph_canvas.property("liveDragNodeLookup"))
        if live_drag_node_lookup.get(node_id):
            return {
                "x": scene_x + float(graph_canvas.property("liveDragDx") or 0.0),
                "y": scene_y + float(graph_canvas.property("liveDragDy") or 0.0),
                "width": scene_width,
                "height": scene_height,
            }

        node_card = self._graph_node_card(node_id)
        if bool(node_card.property("_liveGeometryActive")):
            return {
                "x": float(node_card.property("_liveX")),
                "y": float(node_card.property("_liveY")),
                "width": max(0.0, float(node_card.property("_liveWidth"))),
                "height": max(0.0, float(node_card.property("_liveHeight"))),
            }

        world_offset = float(node_card.property("worldOffset") or 0.0)
        return {
            "x": float(node_card.x()) - world_offset + float(node_card.property("liveDragDx") or 0.0),
            "y": float(node_card.y()) - world_offset + float(node_card.property("liveDragDy") or 0.0),
            "width": max(0.0, float(node_card.width())),
            "height": max(0.0, float(node_card.height())),
        }

    def _activate_overlay(
        self,
        node_id: str,
        *,
        session_id: str = "",
        widget: QWidget | None = None,
    ) -> QWidget:
        widget = widget or _FakeOverlayWidget()
        self.manager.set_active_overlays(
            (
                EmbeddedViewerOverlaySpec(
                    workspace_id=self.workspace_id,
                    node_id=node_id,
                    session_id=session_id or f"session::{node_id}",
                ),
            )
        )
        self.assertTrue(
            self.manager.attach_overlay_widget(
                node_id,
                widget,
                workspace_id=self.workspace_id,
            )
        )
        self.app.processEvents()
        return widget

    def _expected_overlay_rect(
        self,
        node_id: str,
        *,
        scene_x: float | None = None,
        scene_y: float | None = None,
        scene_width: float | None = None,
        scene_height: float | None = None,
    ):
        viewport_frame = self._graph_viewer_viewport(node_id)
        node_card = self._graph_node_card(node_id)
        graph_canvas = self._graph_canvas_quick_item()
        root_item = self.window.quick_widget.rootObject()
        self.assertIsInstance(root_item, QQuickItem)

        if scene_x is None or scene_y is None or scene_width is None or scene_height is None:
            scene_geometry = self._expected_node_scene_geometry(node_id)
            scene_x = scene_geometry["x"] if scene_x is None else scene_x
            scene_y = scene_geometry["y"] if scene_y is None else scene_y
            scene_width = scene_geometry["width"] if scene_width is None else scene_width
            scene_height = scene_geometry["height"] if scene_height is None else scene_height

        top_left = viewport_frame.mapToItem(node_card, QPointF(0.0, 0.0))
        bottom_right = viewport_frame.mapToItem(
            node_card,
            QPointF(viewport_frame.width(), viewport_frame.height()),
        )
        node_local_rect = QRectF(top_left, bottom_right).normalized()
        canvas_origin = graph_canvas.mapToItem(root_item, QPointF(0.0, 0.0))
        zoom = float(self.window.view.zoom_value)
        center_x = float(self.window.view.center_x)
        center_y = float(self.window.view.center_y)
        viewport_rect = QRectF(
            float(canvas_origin.x()) + (float(graph_canvas.width()) * 0.5) + ((scene_x + node_local_rect.x() - center_x) * zoom),
            float(canvas_origin.y()) + (float(graph_canvas.height()) * 0.5) + ((scene_y + node_local_rect.y() - center_y) * zoom),
            float(node_local_rect.width()) * zoom,
            float(node_local_rect.height()) * zoom,
        )
        canvas_rect = QRectF(
            float(canvas_origin.x()),
            float(canvas_origin.y()),
            float(graph_canvas.width()),
            float(graph_canvas.height()),
        )
        viewport_rect = viewport_rect.intersected(canvas_rect)
        left = float(viewport_rect.x())
        top = float(viewport_rect.y())
        width = float(viewport_rect.width())
        height = float(viewport_rect.height())
        return (left, top, width, height)

    def _assert_rect_close(
        self,
        widget: QWidget,
        node_id: str,
        *,
        scene_x: float | None = None,
        scene_y: float | None = None,
        scene_width: float | None = None,
        scene_height: float | None = None,
        delta: float = 1.1,
    ) -> None:
        left, top, width, height = self._expected_overlay_rect(
            node_id,
            scene_x=scene_x,
            scene_y=scene_y,
            scene_width=scene_width,
            scene_height=scene_height,
        )
        geometry = widget.geometry()
        self.assertAlmostEqual(float(geometry.x()), left, delta=delta)
        self.assertAlmostEqual(float(geometry.y()), top, delta=delta)
        self.assertAlmostEqual(float(geometry.width()), width, delta=delta)
        self.assertAlmostEqual(float(geometry.height()), height, delta=delta)

    def _assert_rect_matches_item(self, widget: QWidget, item: QQuickItem, *, delta: float = 1.1) -> None:
        root_item = self.window.quick_widget.rootObject()
        self.assertIsInstance(root_item, QQuickItem)
        top_left = item.mapToItem(root_item, QPointF(0.0, 0.0))
        bottom_right = item.mapToItem(root_item, QPointF(item.width(), item.height()))
        expected = QRectF(top_left, bottom_right).normalized()
        geometry = widget.geometry()
        self.assertAlmostEqual(float(geometry.x()), float(expected.x()), delta=delta)
        self.assertAlmostEqual(float(geometry.y()), float(expected.y()), delta=delta)
        self.assertAlmostEqual(float(geometry.width()), float(expected.width()), delta=delta)
        self.assertAlmostEqual(float(geometry.height()), float(expected.height()), delta=delta)

    def test_shell_window_creates_overlay_manager_parented_to_qquickwidget(self) -> None:
        self.assertIs(self.manager.parent(), self.window.quick_widget)
        self.assertIs(self.manager.quick_widget, self.window.quick_widget)
        self.assertIs(self.manager.overlay_parent_widget, self.window.quick_widget)

    def test_live_overlay_geometry_tracks_pan_zoom_and_node_move_resize(self) -> None:
        node_id = self._add_viewer_node()
        widget = self._activate_overlay(node_id)

        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)
        self.assertIs(self.manager.overlay_widget(node_id, workspace_id=self.workspace_id), widget)
        self.assertTrue(container.isVisible())
        self.assertTrue(widget.isVisible())
        self.assertTrue(self.manager.overlay_geometry_ready(node_id, workspace_id=self.workspace_id))
        self._assert_rect_close(container, node_id)
        self.assertEqual(widget.geometry(), container.rect())

        geometry_service = self.manager._geometry_service
        with (
            patch.object(self.manager, "sync", wraps=self.manager.sync) as sync_spy,
            patch.object(
                self.manager,
                "sync_transform_only",
                wraps=self.manager.sync_transform_only,
            ) as transform_sync_spy,
            patch.object(
                geometry_service,
                "overlay_geometry_from_viewport_item",
                wraps=geometry_service.overlay_geometry_from_viewport_item,
            ) as root_viewport_geometry_spy,
        ):
            self.window.view.set_view_state(1.15, 320.0, 220.0)
            sync_spy.assert_not_called()
            self.assertTrue(self.manager._sync_queued)
            self.app.processEvents()
            transform_sync_spy.assert_called_once_with()
            root_viewport_geometry_spy.assert_not_called()
        self.assertTrue(container.isVisible())
        self._assert_rect_close(container, node_id, delta=2.0)
        self.assertEqual(widget.geometry(), container.rect())

    def test_live_overlay_geometry_tracks_rendered_node_position_changes(self) -> None:
        node_id = self._add_viewer_node()
        widget = self._activate_overlay(node_id)
        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)
        node_card = self._graph_node_card(node_id)
        initial_geometry = container.geometry()

        self.assertTrue(node_card.setProperty("x", float(node_card.x()) + 48.0))
        self.assertTrue(node_card.setProperty("y", float(node_card.y()) + 26.0))
        self.app.processEvents()

        moved_geometry = container.geometry()
        self.assertAlmostEqual(float(moved_geometry.x()), float(initial_geometry.x()) + 48.0, delta=1.1)
        self.assertAlmostEqual(float(moved_geometry.y()), float(initial_geometry.y()) + 26.0, delta=1.1)
        self.assertAlmostEqual(float(moved_geometry.width()), float(initial_geometry.width()), delta=1.1)
        self.assertAlmostEqual(float(moved_geometry.height()), float(initial_geometry.height()), delta=1.1)
        self.assertEqual(widget.geometry(), container.rect())

    def test_native_window_overlay_hides_during_canvas_live_drag_preview_and_restores(self) -> None:
        node_id = self._add_viewer_node()
        widget = _CountingWidget()
        self._activate_overlay(node_id, widget=widget)
        widget.setProperty("ea.nativeWindowOverlay", True)
        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)
        canvas = self._graph_canvas_quick_item()
        self.assertTrue(container.isVisible())
        self.assertTrue(widget.isVisible())
        widget.reset_counts()

        with patch.object(self.manager, "_node_payloads_by_id", wraps=self.manager._node_payloads_by_id) as payload_lookup:
            canvas.setLiveDragOffset(node_id, 48.0, 26.0)
            wait_for_condition_or_raise(
                lambda: not container.isVisible(),
                timeout_ms=500,
                app=self.app,
                timeout_message="Timed out waiting for native viewer overlay to hide during drag.",
            )
            payload_lookup.assert_not_called()

        self.assertFalse(container.isVisible())
        self.assertFalse(widget.isVisible())
        self.assertFalse(widget.updatesEnabled())
        self.assertEqual(widget.move_calls, 0)
        self.assertEqual(widget.resize_calls, 0)
        self.assertEqual(widget.set_geometry_calls, 0)

        canvas.clearLiveDragOffset()
        self.app.processEvents()

        self.assertTrue(container.isVisible())
        self.assertTrue(widget.isVisible())
        self.assertTrue(widget.updatesEnabled())
        self._assert_rect_close(container, node_id)

    def test_native_window_overlay_hides_during_viewport_interaction_and_restores(self) -> None:
        node_id = self._add_viewer_node()
        widget = self._activate_overlay(node_id)
        widget.setProperty("ea.nativeWindowOverlay", True)
        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)
        canvas = self._graph_canvas_quick_item()
        self.assertTrue(container.isVisible())
        self.assertTrue(widget.isVisible())

        self.assertTrue(canvas.setProperty("interactionActive", True))
        self.app.processEvents()

        self.assertFalse(container.isVisible())
        self.assertFalse(widget.isVisible())

        self.assertTrue(canvas.setProperty("interactionActive", False))
        self.app.processEvents()

        self.assertTrue(container.isVisible())
        self.assertTrue(widget.isVisible())
        self._assert_rect_close(container, node_id)

    def test_node_delta_sync_skips_unrelated_nodes_and_routes_viewer_geometry(self) -> None:
        node_id = self._add_viewer_node()
        self._activate_overlay(node_id)
        state_bridge = self.window.scene.state_bridge

        with (
            patch.object(self.manager, "_schedule_sync") as full_sync,
            patch.object(self.manager, "_schedule_transform_sync") as transform_sync,
        ):
            state_bridge.node_delta_payload = {
                "kind": "node_delta",
                "reason": "node_property_payload_delta",
                "nodes": [{"node_id": "unrelated"}],
                "backdrop_nodes": [],
                "added_node_ids": [],
                "removed_node_ids": [],
                "visibility_may_change": True,
            }
            self.manager._on_scene_nodes_changed()
            full_sync.assert_not_called()
            transform_sync.assert_not_called()

            state_bridge.node_delta_payload = {
                "kind": "node_delta",
                "reason": "node_position_delta",
                "nodes": [{"node_id": node_id}],
                "backdrop_nodes": [],
                "added_node_ids": [],
                "removed_node_ids": [],
                "visibility_may_change": True,
            }
            self.manager._on_scene_nodes_changed()
            transform_sync.assert_called_once_with()

            state_bridge.node_delta_payload = {
                "kind": "node_delta",
                "reason": "node_property_payload_delta",
                "nodes": [{"node_id": node_id}],
                "backdrop_nodes": [],
                "added_node_ids": [],
                "removed_node_ids": [],
                "visibility_may_change": False,
            }
            self.manager._on_scene_nodes_changed()
            full_sync.assert_called_once_with()

    def test_live_overlay_geometry_tracks_rendered_resize_preview_state(self) -> None:
        node_id = self._add_viewer_node()
        widget = self._activate_overlay(node_id)
        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)
        node_card = self._graph_node_card(node_id)

        self.assertTrue(node_card.setProperty("_liveGeometryActive", True))
        self.assertTrue(node_card.setProperty("_liveX", 214.0))
        self.assertTrue(node_card.setProperty("_liveY", 142.0))
        self.assertTrue(node_card.setProperty("_liveWidth", 472.0))
        self.assertTrue(node_card.setProperty("_liveHeight", 338.0))
        self.app.processEvents()
        self._assert_rect_close(
            container,
            node_id,
            scene_x=214.0,
            scene_y=142.0,
            scene_width=472.0,
            scene_height=338.0,
        )
        self.assertEqual(widget.geometry(), container.rect())

        self.assertTrue(node_card.setProperty("_liveGeometryActive", False))
        self.app.processEvents()
        self.app.processEvents()
        self._assert_rect_close(container, node_id)

    def test_live_overlay_geometry_uses_inner_viewport_instead_of_full_body_frame(self) -> None:
        node_id = self._add_viewer_node()
        self._activate_overlay(node_id)
        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)
        body_frame = self._graph_viewer_body_frame(node_id)
        viewport_frame = self._graph_viewer_viewport(node_id)

        body_top_left = body_frame.mapToItem(self.window.quick_widget.rootObject(), QPointF(0.0, 0.0))
        viewport_top_left = viewport_frame.mapToItem(self.window.quick_widget.rootObject(), QPointF(0.0, 0.0))

        self.assertAlmostEqual(float(container.geometry().width()), float(viewport_frame.width()), delta=1.1)
        self.assertAlmostEqual(float(container.geometry().height()), float(viewport_frame.height()), delta=1.1)
        self.assertGreater(float(container.geometry().y()), float(body_top_left.y()))
        self.assertGreater(float(viewport_top_left.y()), float(body_top_left.y()))

    def test_plot_live_overlay_stays_hidden_until_exact_viewport_geometry(self) -> None:
        node_id = self._add_viewer_node()
        body_frame = self._graph_viewer_body_frame(node_id)
        widget = _FakeOverlayWidget()
        widget.setProperty("ea.plotLiveOverlay", True)

        self.manager.set_active_overlays(
            (
                EmbeddedViewerOverlaySpec(
                    workspace_id=self.workspace_id,
                    node_id=node_id,
                    session_id=f"plot::{node_id}",
                ),
            )
        )
        with patch.object(self.manager, "_viewer_geometry_item", return_value=body_frame):
            self.assertTrue(
                self.manager.attach_overlay_widget(
                    node_id,
                    widget,
                    workspace_id=self.workspace_id,
                )
            )
            self.manager.sync()

        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)
        self.assertFalse(container.isVisible())
        self.assertFalse(widget.isVisible())
        self.assertFalse(self.manager.overlay_geometry_ready(node_id, workspace_id=self.workspace_id))

        self.manager.sync()

        self.assertTrue(container.isVisible())
        self.assertTrue(widget.isVisible())
        self.assertTrue(self.manager.overlay_geometry_ready(node_id, workspace_id=self.workspace_id))
        self.assertEqual(widget.geometry(), container.rect())
        self._assert_rect_close(container, node_id)

    def test_content_fullscreen_target_moves_live_overlay_to_shell_viewport_and_restores(self) -> None:
        self.window.viewer_host_service.suspend_sync(reason="manager_content_fullscreen_geometry_test")
        node_id = self._add_viewer_node()
        widget = self._activate_overlay(node_id)
        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)
        node_geometry = container.geometry()

        self.assertTrue(self.window.content_fullscreen_bridge.request_open_node(node_id))
        self.manager.set_content_fullscreen_target(
            EmbeddedViewerOverlaySpec(
                workspace_id=self.workspace_id,
                node_id=node_id,
                session_id=f"session::{node_id}",
            )
        )
        self.app.processEvents()
        self.app.processEvents()

        viewer_viewport = self._content_fullscreen_viewer_viewport()
        self.assertTrue(viewer_viewport.isVisible())
        self.assertIs(self.manager.overlay_widget(node_id, workspace_id=self.workspace_id), widget)
        self._assert_rect_matches_item(container, viewer_viewport)
        self.assertGreater(container.geometry().width(), node_geometry.width())
        self.assertGreater(container.geometry().height(), node_geometry.height())

        root_item = self.window.quick_widget.rootObject()
        quick_controls = root_item.findChild(QObject, "viewerQuickControls")
        self.assertIsInstance(quick_controls, QQuickItem)
        self.assertTrue(quick_controls.isVisible())
        self.assertLessEqual(quick_controls.height(), 72.0)

        self.window.content_fullscreen_bridge.request_close()
        self.manager.set_content_fullscreen_target(None)
        self.app.processEvents()
        self.app.processEvents()

        self.assertIs(self.manager.overlay_widget(node_id, workspace_id=self.workspace_id), widget)
        self._assert_rect_close(container, node_id)
        self.assertEqual(widget.geometry(), container.rect())
        self.window.viewer_host_service.resume_sync()

    def test_plot_fullscreen_target_moves_live_overlay_to_shell_viewport(self) -> None:
        self.window.plot_host_service.suspend_sync(reason="manager_plot_fullscreen_geometry_test")
        try:
            node_id = self._add_plot_node()
            overlay = EmbeddedViewerOverlaySpec(
                workspace_id=self.workspace_id,
                node_id=node_id,
                session_id=f"plot::{node_id}",
            )
            widget = _FakeOverlayWidget()
            widget.setProperty("ea.plotLiveOverlay", True)

            self.manager.set_active_overlays_for_owner("plot_host", (overlay,))
            self.assertTrue(
                self.manager.attach_overlay_widget(
                    node_id,
                    widget,
                    workspace_id=self.workspace_id,
                )
            )
            self.manager.sync()
            container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
            self.assertIsNotNone(container)
            inline_geometry = container.geometry()

            self.assertTrue(self.window.content_fullscreen_bridge.request_open_node(node_id))
            self.manager.set_content_fullscreen_target(overlay)
            self.app.processEvents()
            self.app.processEvents()

            viewer_viewport = self._content_fullscreen_viewer_viewport()
            self.assertTrue(viewer_viewport.isVisible())
            self.assertTrue(self.manager.overlay_geometry_ready(node_id, workspace_id=self.workspace_id))
            self._assert_rect_matches_item(container, viewer_viewport)
            self.assertEqual(widget.geometry(), container.rect())
            self.assertGreater(container.geometry().width(), inline_geometry.width())
            self.assertGreater(container.geometry().height(), inline_geometry.height())
        finally:
            self.window.content_fullscreen_bridge.request_close()
            self.manager.set_content_fullscreen_target(None)
            self.window.plot_host_service.resume_sync()

    def test_plot_fullscreen_target_waits_for_shell_viewport_instead_of_inline_fallback(self) -> None:
        self.window.plot_host_service.suspend_sync(reason="manager_plot_fullscreen_wait_test")
        try:
            node_id = self._add_plot_node()
            overlay = EmbeddedViewerOverlaySpec(
                workspace_id=self.workspace_id,
                node_id=node_id,
                session_id=f"plot::{node_id}",
            )
            widget = _FakeOverlayWidget()
            widget.setProperty("ea.plotLiveOverlay", True)

            self.manager.set_active_overlays_for_owner("plot_host", (overlay,))
            self.assertTrue(
                self.manager.attach_overlay_widget(
                    node_id,
                    widget,
                    workspace_id=self.workspace_id,
                )
            )
            self.manager.set_content_fullscreen_target(overlay)
            self.app.processEvents()
            self.app.processEvents()

            container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
            self.assertIsNotNone(container)
            self.assertFalse(container.isVisible())
            self.assertFalse(widget.isVisible())
            self.assertFalse(self.manager.overlay_geometry_ready(node_id, workspace_id=self.workspace_id))
        finally:
            self.manager.set_content_fullscreen_target(None)
            self.window.plot_host_service.resume_sync()

    def test_content_fullscreen_target_falls_back_to_node_viewport_when_shell_viewport_hidden(self) -> None:
        node_id = self._add_viewer_node()
        widget = self._activate_overlay(node_id)
        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)

        self.manager.set_content_fullscreen_target(
            EmbeddedViewerOverlaySpec(
                workspace_id=self.workspace_id,
                node_id=node_id,
                session_id=f"session::{node_id}",
            )
        )
        self.app.processEvents()
        self.app.processEvents()

        self.assertIs(self.manager.overlay_widget(node_id, workspace_id=self.workspace_id), widget)
        self._assert_rect_close(container, node_id)
        self.assertTrue(container.isVisible())
        self.assertTrue(widget.isVisible())

    def test_offscreen_culling_hides_overlay_reuses_widget_and_tears_down_when_deactivated(self) -> None:
        node_id = self._add_viewer_node(x=120.0, y=80.0)
        widget = self._activate_overlay(node_id)

        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)
        self.assertTrue(container.isVisible())

        self.window.view.set_view_state(1.0, 6000.0, 6000.0)
        record = self.manager._overlay_records[(self.workspace_id, node_id)]
        record.node_card_item = None
        record.viewer_geometry_item = None
        with patch.object(self.manager, "_walk_items", wraps=self.manager._walk_items) as walk_spy:
            self.app.processEvents()
            walk_spy.assert_not_called()
        self.assertFalse(container.isVisible())
        self.assertFalse(widget.isVisible())
        metrics = self.manager.overlay_metrics_snapshot()
        self.assertEqual(metrics["total_count"], 1)
        self.assertEqual(metrics["visible_count"], 0)
        self.assertEqual(metrics["skipped_offscreen_count"], 1)

        node_payload = self._node_payload(node_id)
        self.window.view.set_view_state(
            1.0,
            float(node_payload["x"]) + (float(node_payload["width"]) * 0.5),
            float(node_payload["y"]) + (float(node_payload["height"]) * 0.5),
        )
        self.app.processEvents()
        self.assertTrue(container.isVisible())
        self.assertTrue(widget.isVisible())

        self.manager.set_active_overlays(())
        self.app.processEvents()
        self.assertIsNone(self.manager.overlay_container(node_id, workspace_id=self.workspace_id))
        self.assertIsNone(self.manager.overlay_widget(node_id, workspace_id=self.workspace_id))
        self.assertEqual(widget.close_calls, 1)

    def test_detach_overlay_widget_keeps_active_container_ready_for_clean_rebind(self) -> None:
        node_id = self._add_viewer_node()
        first_widget = self._activate_overlay(node_id)

        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)
        self.assertIs(self.manager.overlay_widget(node_id, workspace_id=self.workspace_id), first_widget)

        self.manager.detach_overlay_widget(node_id, workspace_id=self.workspace_id)
        self.app.processEvents()

        self.assertEqual(first_widget.close_calls, 1)
        self.assertIsNone(self.manager.overlay_widget(node_id, workspace_id=self.workspace_id))
        rebound_container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIs(rebound_container, container)
        self.assertFalse(rebound_container.isVisible())

        second_widget = _FakeOverlayWidget()
        self.assertTrue(
            self.manager.attach_overlay_widget(
                node_id,
                second_widget,
                workspace_id=self.workspace_id,
            )
        )
        self.assertFalse(self.manager.overlay_geometry_ready(node_id, workspace_id=self.workspace_id))
        self.app.processEvents()

        self.assertIs(self.manager.overlay_widget(node_id, workspace_id=self.workspace_id), second_widget)
        self.assertIs(self.manager.overlay_container(node_id, workspace_id=self.workspace_id), container)
        self.assertTrue(container.isVisible())
        self.assertTrue(second_widget.isVisible())
        self.assertTrue(self.manager.overlay_geometry_ready(node_id, workspace_id=self.workspace_id))
        self._assert_rect_close(container, node_id)
        self.assertEqual(second_widget.geometry(), container.rect())

    def test_take_overlay_widget_removes_live_record_without_closing_widget(self) -> None:
        node_id = self._add_viewer_node()
        widget = self._activate_overlay(node_id)

        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)
        self.assertIs(self.manager.overlay_widget(node_id, workspace_id=self.workspace_id), widget)
        self.assertTrue(container.isVisible())

        self.manager.set_active_overlays(
            (
                EmbeddedViewerOverlaySpec(
                    workspace_id=self.workspace_id,
                    node_id=node_id,
                    session_id=f"session::{node_id}",
                    visible=False,
                ),
            )
        )
        self.app.processEvents()
        self.assertFalse(widget.updatesEnabled())

        taken = self.manager.take_overlay_widget(node_id, workspace_id=self.workspace_id)
        self.app.processEvents()

        self.assertIs(taken, widget)
        self.assertTrue(widget.updatesEnabled())
        self.assertEqual(widget.close_calls, 0)
        self.assertIsNone(self.manager.overlay_widget(node_id, workspace_id=self.workspace_id))
        self.assertIs(self.manager.overlay_container(node_id, workspace_id=self.workspace_id), container)
        self.assertFalse(container.isVisible())
        self.assertFalse(self.manager.overlay_geometry_ready(node_id, workspace_id=self.workspace_id))

    def test_hidden_retained_overlay_survives_missing_scene_payload(self) -> None:
        node_id = self._add_viewer_node()
        widget = self._activate_overlay(node_id)
        self.manager.set_active_overlays(
            (
                EmbeddedViewerOverlaySpec(
                    workspace_id=self.workspace_id,
                    node_id=node_id,
                    session_id=f"session::{node_id}",
                    visible=False,
                ),
            )
        )
        self.app.processEvents()

        with patch.object(self.manager, "_node_payloads_by_id", return_value={}):
            self.manager.sync()

        self.assertEqual(widget.close_calls, 0)
        self.assertIs(
            self.manager.overlay_widget(node_id, workspace_id=self.workspace_id),
            widget,
        )
        self.assertFalse(widget.isVisible())

    def test_paint_and_update_request_events_do_not_queue_overlay_sync(self) -> None:
        self.app.processEvents()
        self.manager._sync_queued = False
        self.manager.eventFilter(self.window.quick_widget, QEvent(QEvent.Type.Paint))
        self.assertFalse(self.manager._sync_queued)
        self.manager.eventFilter(self.window.quick_widget, QEvent(QEvent.Type.UpdateRequest))
        self.assertFalse(self.manager._sync_queued)

    def test_layout_request_during_native_overlay_suppression_does_not_queue_full_sync(self) -> None:
        node_id = self._add_viewer_node()
        widget = self._activate_overlay(node_id)
        widget.setProperty("ea.nativeWindowOverlay", True)
        canvas = self._graph_canvas_quick_item()
        canvas.setLiveDragOffset(node_id, 12.0, 8.0)
        self.app.processEvents()
        self.manager._sync_queued = False

        self.manager.eventFilter(
            self.window.quick_widget,
            QEvent(QEvent.Type.LayoutRequest),
        )

        self.assertFalse(self.manager._sync_queued)
        with patch.object(self.manager, "_queue_sync") as queue_sync:
            self.manager._schedule_sync()
            queue_sync.assert_called_once_with("transform")
        canvas.clearLiveDragOffset()

    def test_quick_widget_mouse_event_inside_native_overlay_is_consumed(self) -> None:
        node_id = self._add_viewer_node()
        widget = self._activate_overlay(node_id)
        widget.setProperty("ea.nativeWindowOverlay", True)
        container = self.manager.overlay_container(node_id, workspace_id=self.workspace_id)
        self.assertIsNotNone(container)
        self.assertTrue(container.isVisible())

        inside = QPointF(container.geometry().center())
        inside_event = QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            inside,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.assertTrue(self.manager.eventFilter(self.window.quick_widget, inside_event))
        self.assertTrue(inside_event.isAccepted())

        outside = QPointF(container.geometry().right() + 24.0, container.geometry().bottom() + 24.0)
        outside_event = QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            outside,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.assertFalse(self.manager.eventFilter(self.window.quick_widget, outside_event))

    def test_run_queued_sync_does_not_requeue_without_new_work(self) -> None:
        self.manager._sync_queued = True

        with patch.object(self.manager, "sync") as sync_mock:
            self.manager._run_queued_sync()

        sync_mock.assert_called_once_with()
        self.assertFalse(self.manager._sync_queued)

    def test_view_state_changes_coalesce_to_one_transform_sync(self) -> None:
        node_id = self._add_viewer_node()
        self._activate_overlay(node_id)
        self.app.processEvents()

        with (
            patch.object(self.manager, "sync", wraps=self.manager.sync) as sync_spy,
            patch.object(
                self.manager,
                "sync_transform_only",
                wraps=self.manager.sync_transform_only,
            ) as transform_sync_spy,
        ):
            self.window.view.set_view_state(1.05, 315.0, 215.0)
            self.window.view.set_view_state(1.10, 330.0, 225.0)
            self.window.view.set_view_state(1.15, 345.0, 235.0)
            self.assertTrue(self.manager._sync_queued)
            self.app.processEvents()

        sync_spy.assert_not_called()
        transform_sync_spy.assert_called_once_with()
        metrics = self.manager.overlay_metrics_snapshot()
        self.assertEqual(metrics["sync_mode"], "transform")
        self.assertEqual(metrics["geometry_only_updates"], 1)
        self.assertEqual(metrics["content_updates"], 0)

    def test_show_record_avoids_restack_on_geometry_only_updates(self) -> None:
        container = _CountingWidget(self.window.quick_widget)
        widget = _CountingWidget(container)
        record = _OverlayRecord(
            workspace_id=self.workspace_id,
            node_id="node_counting_overlay",
            session_id="session::counting",
            container=container,
            overlay_widget=widget,
        )

        EmbeddedViewerOverlayManager._show_record(record, QRectF(12.0, 18.0, 240.0, 160.0).toRect())
        self.app.processEvents()
        container.reset_counts()
        widget.reset_counts()

        EmbeddedViewerOverlayManager._show_record(record, QRectF(48.0, 72.0, 240.0, 160.0).toRect())
        self.assertEqual(container.move_calls, 1)
        self.assertEqual(container.resize_calls, 0)
        self.assertEqual(container.set_geometry_calls, 0)
        self.assertEqual(container.raise_calls, 0)
        self.assertEqual(widget.move_calls, 0)
        self.assertEqual(widget.resize_calls, 0)
        self.assertEqual(widget.set_geometry_calls, 0)
        self.assertEqual(widget.raise_calls, 0)

        container.reset_counts()
        widget.reset_counts()

        EmbeddedViewerOverlayManager._show_record(record, QRectF(48.0, 72.0, 300.0, 210.0).toRect())
        self.assertEqual(container.move_calls, 0)
        self.assertEqual(container.resize_calls, 1)
        self.assertEqual(container.set_geometry_calls, 0)
        self.assertEqual(container.raise_calls, 0)
        self.assertEqual(widget.move_calls, 0)
        self.assertEqual(widget.resize_calls, 1)
        self.assertEqual(widget.set_geometry_calls, 0)
        self.assertEqual(widget.raise_calls, 0)

    def test_show_record_focus_restack_raises_container_only(self) -> None:
        container = _CountingWidget(self.window.quick_widget)
        widget = _CountingWidget(container)
        record = _OverlayRecord(
            workspace_id=self.workspace_id,
            node_id="node_focus_overlay",
            session_id="session::focus",
            container=container,
            overlay_widget=widget,
        )

        EmbeddedViewerOverlayManager._show_record(record, QRectF(20.0, 24.0, 220.0, 140.0).toRect())
        self.app.processEvents()
        container.reset_counts()
        widget.reset_counts()

        EmbeddedViewerOverlayManager._show_record(record, container.geometry(), focus=True)
        self.assertEqual(container.raise_calls, 1)
        self.assertEqual(widget.raise_calls, 0)


class EmbeddedViewerOverlayManagerQQuickViewHostTests(MainWindowShellTestBase):
    def setUp(self) -> None:
        self._qml_host_env_patch = patch.dict(os.environ, {QML_HOST_ENV: QML_HOST_QQUICKVIEW_CONTAINER})
        self._qml_host_env_patch.start()
        try:
            super().setUp()
        except Exception:
            self._qml_host_env_patch.stop()
            raise
        self.manager = self.window.embedded_viewer_overlay_manager
        self.assertIsNotNone(self.manager)
        self.workspace_id = self.window.workspace_manager.active_workspace_id()

    def tearDown(self) -> None:
        try:
            super().tearDown()
        finally:
            self._qml_host_env_patch.stop()

    def test_qquickview_container_host_parents_overlays_to_container_widget(self) -> None:
        qml_host = self.window.qml_host
        self.assertEqual(qml_host.host_kind, QML_HOST_QQUICKVIEW_CONTAINER)
        self.assertIs(self.manager.parent(), qml_host.container_widget)
        self.assertIs(self.manager.overlay_parent_widget, qml_host.container_widget)
        self.assertIs(self.manager.event_filter_widget, qml_host.container_widget)

        record = self.manager._ensure_record(key=(self.workspace_id, "qquickview-node"), session_id="session-1")

        self.assertIsNotNone(record)
        self.assertIs(record.container.parent(), qml_host.container_widget)
        self.manager._sync_queued = False
        self.manager.eventFilter(qml_host.container_widget, QEvent(QEvent.Type.Resize))
        self.assertTrue(self.manager._sync_queued)


if __name__ == "__main__":
    unittest.main()
