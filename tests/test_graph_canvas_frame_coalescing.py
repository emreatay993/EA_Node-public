from __future__ import annotations

import inspect
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, Qt, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtQuick import QQuickWindow
from PyQt6.QtTest import QSignalSpy, QTest

from ea_node_editor.nodes import decorators as _node_decorators
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui_qml.surface_contracts import surface_spec_payload_for_values

if "category" not in inspect.signature(_node_decorators.node_type).parameters:
    _original_node_type = _node_decorators.node_type

    def _compat_node_type(*args, category=None, **kwargs):
        if category is not None and "category_path" not in kwargs:
            if isinstance(category, (list, tuple)):
                kwargs["category_path"] = tuple(str(value) for value in category if str(value))
            else:
                normalized_category = str(category or "").strip()
                if normalized_category:
                    kwargs["category_path"] = (normalized_category,)
        return _original_node_type(*args, **kwargs)

    _node_decorators.node_type = _compat_node_type

from tests.graph_track_b.qml_support import (
    GraphCanvasCommandBridge,
    GraphCanvasQmlPreferenceTestBase,
    GraphCanvasStateBridge,
    GraphModel,
    GraphSceneBridge,
    QObject,
    ViewportBridge,
    wait_for_condition_or_raise,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


def _viewer_delegate_payload(node_id: str) -> dict[str, object]:
    return {
        "node_id": node_id,
        "type_id": "tests.viewer_canvas_boundary",
        "title": "Viewer",
        "x": -140.0,
        "y": -110.0,
        "width": 296.0,
        "height": 236.0,
        "collapsed": False,
        "runtime_behavior": "active",
        "surface_family": "viewer",
        "surface_variant": "",
        "surface_spec": surface_spec_payload_for_values(
            type_id="tests.viewer_canvas_boundary",
            family="viewer",
            variant="",
        ),
        "render_quality": {"supported_quality_tiers": ["full", "proxy"]},
        "surface_metrics": {
            "default_width": 296.0,
            "default_height": 236.0,
            "min_width": 220.0,
            "min_height": 208.0,
            "collapsed_width": 130.0,
            "collapsed_height": 36.0,
            "header_height": 24.0,
            "header_top_margin": 4.0,
            "body_top": 30.0,
            "body_height": 176.0,
            "port_top": 206.0,
            "port_height": 18.0,
            "port_center_offset": 6.0,
            "port_side_margin": 8.0,
            "port_dot_radius": 3.5,
            "resize_handle_size": 16.0,
            "body_left_margin": 14.0,
            "body_right_margin": 14.0,
            "body_bottom_margin": 12.0,
            "use_host_chrome": True,
        },
        "viewer_surface": {
            "body_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
            "proxy_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
            "live_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
            "overlay_target": "body",
            "proxy_surface_supported": True,
            "live_surface_supported": True,
        },
        "ports": [],
        "inline_properties": [],
        "visual_style": {},
        "can_enter_scope": False,
    }


class _PointerViewerSessionProbe(QObject):
    sessions_changed = pyqtSignal()
    last_error_changed = pyqtSignal()

    def __init__(self, node_id: str) -> None:
        super().__init__()
        self.node_id = node_id
        self.embedded_calls: list[tuple[str, bool]] = []
        self._state = {
            "workspace_id": "ws_main",
            "node_id": node_id,
            "session_id": f"session::{node_id}",
            "phase": "open",
            "request_id": "req::viewer",
            "last_command": "open",
            "last_error": "",
            "playback_state": "paused",
            "step_index": 0,
            "cache_state": "proxy_ready",
            "live_mode": "proxy",
            "backend_id": "tests.viewer_backend",
            "transport_revision": 1,
            "live_open_status": "ready",
            "live_open_blocker": {},
            "data_refs": {},
            "transport": {"kind": "bundle"},
            "summary": {"capabilities": {"playback": False}},
            "options": {"live_mode": "proxy"},
        }

    @pyqtProperty("QVariantList", notify=sessions_changed)
    def sessions_model(self):
        return [dict(self._state)]

    @pyqtProperty(str, notify=last_error_changed)
    def last_error(self) -> str:
        return ""

    @pyqtSlot(str, result="QVariantMap")
    def session_state(self, node_id: str):
        return dict(self._state) if str(node_id) == self.node_id else {}

    def set_embedded_active(self, node_id: str, active: bool) -> None:
        normalized = bool(active)
        self.embedded_calls.append((str(node_id), normalized))
        live_mode = "full" if normalized else "proxy"
        self._state["live_mode"] = live_mode
        self._state["options"] = {"live_mode": live_mode}
        self.sessions_changed.emit()


class _PointerViewerHostProbe(QObject):
    state_changed = pyqtSignal()
    preview_cache_changed = pyqtSignal()
    last_error_changed = pyqtSignal()

    def __init__(self, session_probe: _PointerViewerSessionProbe) -> None:
        super().__init__()
        self.session_probe = session_probe
        self.active_calls: list[tuple[str, bool]] = []
        self._active = False
        self._revision = 0

    @pyqtProperty(int, notify=state_changed)
    def active_overlay_count(self) -> int:
        return 1 if self._active else 0

    @pyqtProperty(int, notify=state_changed)
    def viewer_overlay_revision(self) -> int:
        return self._revision

    @pyqtProperty(int, notify=preview_cache_changed)
    def preview_cache_revision(self) -> int:
        return 0

    @pyqtProperty(str, notify=last_error_changed)
    def last_error(self) -> str:
        return ""

    @pyqtSlot(str, bool)
    def set_embedded_interaction_active(self, node_id: str, active: bool) -> None:
        self._active = bool(active)
        self._revision += 1
        self.active_calls.append((str(node_id), self._active))
        self.session_probe.set_embedded_active(node_id, self._active)
        self.state_changed.emit()

    @pyqtSlot(str, result=str)
    def cached_preview_source(self, _node_id: str) -> str:
        return ""

    @pyqtSlot(str, result=bool)
    def embedded_live_overlay_ready(self, node_id: str) -> bool:
        return str(node_id) == self.session_probe.node_id and self._active

    @pyqtSlot(str, str)
    def notify_cached_preview_swapped(self, _node_id: str, _source: str) -> None:
        return


class GraphCanvasFrameCoalescingTests(GraphCanvasQmlPreferenceTestBase):
    __test__ = True

    def _scheduler(self) -> QObject:
        scheduler = self.canvas.findChild(QObject, "graphCanvasFrameScheduler")
        self.assertIsNotNone(scheduler)
        return scheduler

    def test_scheduler_uses_frame_budget_by_default(self) -> None:
        scheduler = self._scheduler()

        self.assertEqual(int(scheduler.property("frameBudgetMs")), 16)

    def test_input_layers_use_published_scheduler_ref_without_tree_walk(self) -> None:
        input_layers_path = (
            _REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph_canvas"
            / "GraphCanvasInputLayers.qml"
        )
        input_layers_text = input_layers_path.read_text(encoding="utf-8")

        self.assertIn("root.canvasItem.frameSchedulerRef", input_layers_text)
        self.assertNotIn("_findFrameScheduler", input_layers_text)

    def test_explicit_viewport_interaction_hold_is_distinct_from_wheel_idle_recovery(self) -> None:
        self.canvas.beginViewportInteraction()
        self.app.processEvents()
        self.assertTrue(bool(self.canvas.property("interactionActive")))
        self.assertTrue(bool(self.canvas.property("viewportInteractionHeld")))

        self.canvas.noteViewportInteraction()
        self.app.processEvents()
        self.assertTrue(bool(self.canvas.property("viewportInteractionHeld")))

        self.canvas.finishViewportInteractionSoon()
        self.app.processEvents()
        self.assertFalse(bool(self.canvas.property("viewportInteractionHeld")))

    def test_wheel_event_suppresses_native_overlay_before_zoom_mutation(self) -> None:
        visible_model = self.canvas_state_bridge.visible_nodes_model
        visible_model.sync_payloads(
            [
                {
                    "node_id": "viewer_for_wheel_suppression",
                    "surface_family": "viewer",
                    "viewer_surface": {"live_surface_supported": True},
                }
            ]
        )
        self.assertTrue(bool(self.canvas.shouldUseViewportInteractionQualityForWheelZoom()))
        window = QQuickWindow()
        window.resize(1280, 720)
        self.canvas.setParentItem(window.contentItem())
        window.show()
        self.app.processEvents()

        try:
            mutation_suppression = []
            self.view.view_state_changed.connect(
                lambda: mutation_suppression.append(
                    bool(self.canvas.property("nativeOverlaySuppressionActive"))
                )
            )
            wheel_position = QPointF(640.0, 360.0)
            wheel_event = QWheelEvent(
                wheel_position,
                wheel_position,
                QPoint(),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.ScrollUpdate,
                False,
            )
            self.app.sendEvent(window, wheel_event)
            self.app.processEvents()

            self.assertTrue(wheel_event.isAccepted())
            self.assertTrue(mutation_suppression)
            self.assertTrue(mutation_suppression[0])
        finally:
            visible_model.sync_payloads([])
            self.canvas.setParentItem(None)
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_wheel_recovery_box_zoom_holds_suppression_until_release(self) -> None:
        window = QQuickWindow()
        window.resize(1280, 720)
        self.canvas.setParentItem(window.contentItem())
        window.show()
        self.app.processEvents()

        try:
            self.canvas.noteViewportInteraction()
            self.app.processEvents()
            self.assertTrue(bool(self.canvas.property("interactionActive")))
            self.assertFalse(bool(self.canvas.property("viewportInteractionHeld")))
            self.assertTrue(bool(self.canvas.property("nativeOverlaySuppressionActive")))

            start = QPoint(1080, 620)
            drag = QPoint(980, 520)
            QTest.mousePress(
                window,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
                start,
            )
            QTest.mouseMove(window, drag)
            wait_for_condition_or_raise(
                lambda: bool(self.canvas.property("viewportInteractionHeld")),
                timeout_ms=500,
                app=self.app,
                timeout_message="Timed out waiting for box zoom to acquire the viewport hold.",
            )

            QTest.qWait(int(self.canvas.property("transientRecoveryDelayMs")) + 50)
            self.assertTrue(bool(self.canvas.property("viewportInteractionHeld")))
            self.assertTrue(bool(self.canvas.property("interactionActive")))
            self.assertTrue(bool(self.canvas.property("nativeOverlaySuppressionActive")))

            QTest.mouseRelease(
                window,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
                drag,
            )
            self.app.processEvents()
            self.assertFalse(bool(self.canvas.property("viewportInteractionHeld")))

            wait_for_condition_or_raise(
                lambda: not bool(self.canvas.property("interactionActive")),
                timeout_ms=500,
                app=self.app,
                timeout_message="Timed out waiting for released box zoom suppression to recover.",
            )
            self.assertFalse(bool(self.canvas.property("nativeOverlaySuppressionActive")))
        finally:
            self.canvas.setParentItem(None)
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_deselected_proxy_pointer_sequence_has_no_latent_inline_request(self) -> None:
        model = GraphModel()
        registry = build_default_registry()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.bind_graphics_preferences_source(self.bridge)
        scene.set_workspace(model, registry, workspace_id)
        viewer_id = scene.add_node_from_type("model.viewer", -180.0, -100.0)
        other_id = scene.add_node_from_type("core.logger", 260.0, -80.0)
        scene.select_node(viewer_id, False)

        view = ViewportBridge()
        view.set_viewport_size(1280.0, 720.0)
        state_bridge = GraphCanvasStateBridge(
            session_state=self.canvas_source,
            snap_to_grid_changed_signal=getattr(self.canvas_source, "snap_to_grid_changed", None),
            snap_grid_size=float(getattr(self.canvas_source, "snap_grid_size", 20.0)),
            app_preferences_source=self.canvas_source,
            graphics_source=self.bridge,
            scene_bridge=scene,
            view_bridge=view,
        )
        command_bridge = GraphCanvasCommandBridge(
            search_scope_controller=self.canvas_source,
            app_preferences_source=self.canvas_source,
            run_controller=self.canvas_source,
            inspector_source=self.canvas_source,
            library_source=self.canvas_source,
            workspace_edit_controller=self.canvas_source,
            workspace_drop_connect_controller=self.canvas_source,
            graphics_source=self.bridge,
            scene_bridge=scene,
            view_bridge=view,
        )
        session_probe = _PointerViewerSessionProbe(viewer_id)
        host_probe = _PointerViewerHostProbe(session_probe)
        self.engine.rootContext().setContextProperty("viewerSessionBridge", session_probe)
        self.engine.rootContext().setContextProperty("viewerHostService", host_probe)
        canvas = self._create_canvas(
            {
                "canvasStateBridge": state_bridge,
                "canvasCommandBridge": command_bridge,
                "width": 1280.0,
                "height": 720.0,
            }
        )
        window = QQuickWindow()
        window.resize(1280, 720)
        canvas.setParentItem(window.contentItem())
        window.show()
        self.app.processEvents()

        def selected(node_id: str) -> bool:
            return bool(scene.selected_node_lookup.get(node_id, False))

        def window_point(item: QObject, local_x: float, local_y: float) -> QPoint:
            mapped = item.mapToItem(window.contentItem(), QPointF(local_x, local_y))
            return QPoint(round(mapped.x()), round(mapped.y()))

        def assert_explicit_live() -> None:
            self.assertTrue(selected(viewer_id))
            self.assertTrue(bool(surface.property("inlineLiveRequested")))
            self.assertEqual(session_probe._state["live_mode"], "full")

        def additive_marquee(modifiers: Qt.KeyboardModifier, start: QPoint, end: QPoint) -> None:
            QTest.mousePress(window, Qt.MouseButton.LeftButton, modifiers, start)
            QTest.mouseMove(window, end)
            QTest.mouseRelease(window, Qt.MouseButton.LeftButton, modifiers, end)
            self.app.processEvents()
            assert_explicit_live()

        try:
            world = canvas.findChild(QObject, "graphCanvasWorld")
            self.assertIsNotNone(world)
            wait_for_condition_or_raise(
                lambda: world.hostForNodeId(viewer_id) is not None
                and world.hostForNodeId(other_id) is not None,
                timeout_ms=1500,
                app=self.app,
                timeout_message="Timed out waiting for pointer-sequence node delegates.",
            )
            viewer_card = world.hostForNodeId(viewer_id)
            other_card = world.hostForNodeId(other_id)
            surface = viewer_card.findChild(QObject, "graphNodeViewerSurface")
            viewport = viewer_card.findChild(QObject, "graphNodeViewerViewport")
            self.assertIsNotNone(surface)
            self.assertIsNotNone(viewport)

            QTest.mouseDClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                window_point(viewport, viewport.width() * 0.5, viewport.height() * 0.5),
            )
            wait_for_condition_or_raise(
                lambda: bool(surface.property("inlineLiveRequested"))
                and session_probe._state["live_mode"] == "full",
                timeout_ms=1000,
                app=self.app,
                timeout_message="Selected proxy did not activate on double-click.",
            )

            additive_marquee(
                Qt.KeyboardModifier.ControlModifier,
                QPoint(40, 560),
                QPoint(140, 620),
            )
            additive_marquee(
                Qt.KeyboardModifier.ShiftModifier,
                QPoint(160, 560),
                QPoint(260, 620),
            )

            canvas.forceActiveFocus()
            QTest.keyPress(window, Qt.Key.Key_W, Qt.KeyboardModifier.NoModifier)
            wait_for_condition_or_raise(
                lambda: bool(canvas.property("wireSelectionModeHeld")),
                timeout_ms=500,
                app=self.app,
                timeout_message="Timed out waiting for additive wire-selection mode.",
            )
            try:
                additive_marquee(
                    Qt.KeyboardModifier.ShiftModifier,
                    QPoint(280, 560),
                    QPoint(380, 620),
                )
            finally:
                QTest.keyRelease(window, Qt.Key.Key_W, Qt.KeyboardModifier.NoModifier)
                self.app.processEvents()
            assert_explicit_live()

            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                window_point(other_card, 24.0, 12.0),
            )
            wait_for_condition_or_raise(
                lambda: selected(other_id) and not bool(surface.property("inlineLiveRequested")),
                timeout_ms=1000,
                app=self.app,
                timeout_message="Selecting the other node did not demote the viewer.",
            )

            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                window_point(viewport, viewport.width() * 0.5, viewport.height() * 0.5),
            )
            wait_for_condition_or_raise(
                lambda: selected(viewer_id),
                timeout_ms=1000,
                app=self.app,
                timeout_message="Proxy single-click did not select the viewer.",
            )
            self.assertFalse(bool(surface.property("inlineLiveRequested")))

            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(80, 650),
            )
            wait_for_condition_or_raise(
                lambda: not selected(viewer_id),
                timeout_ms=1000,
                app=self.app,
                timeout_message="Background click did not deselect the viewer.",
            )

            QTest.mouseDClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                window_point(viewport, viewport.width() * 0.5, viewport.height() * 0.5),
            )
            wait_for_condition_or_raise(
                lambda: selected(viewer_id) and bool(surface.property("inlineLiveRequested")),
                timeout_ms=1000,
                app=self.app,
                timeout_message="Deselected proxy did not select and activate on double-click.",
            )

            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(80, 650),
            )
            wait_for_condition_or_raise(
                lambda: not selected(viewer_id) and not bool(surface.property("inlineLiveRequested")),
                timeout_ms=1000,
                app=self.app,
                timeout_message="Second background click did not demote the viewer.",
            )
            self.assertEqual(session_probe._state["live_mode"], "proxy")

            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                window_point(viewer_card, 24.0, 12.0),
            )
            wait_for_condition_or_raise(
                lambda: selected(viewer_id),
                timeout_ms=1000,
                app=self.app,
                timeout_message="Viewer title click did not select the node.",
            )
            self.assertFalse(bool(surface.property("inlineLiveRequested")))
        finally:
            canvas.setParentItem(None)
            canvas.deleteLater()
            window.close()
            window.deleteLater()
            state_bridge.deleteLater()
            command_bridge.deleteLater()
            scene.deleteLater()
            self.engine.rootContext().setContextProperty("viewerSessionBridge", None)
            self.engine.rootContext().setContextProperty("viewerHostService", None)
            self.app.processEvents()

    def test_scheduler_coalesces_bursty_pan_deltas_into_one_view_commit(self) -> None:
        scheduler = self._scheduler()
        start_x = float(self.view.center_x)
        start_y = float(self.view.center_y)
        raw_before = int(scheduler.property("rawPanInputEventCount"))
        flushed_before = int(scheduler.property("flushedPanUpdateCount"))
        pan_flush_spy = QSignalSpy(
            getattr(scheduler, "flushedPanUpdateCountChanged")
        )

        deltas = [(3.0, -2.0), (4.5, 1.5), (-1.0, 5.0), (2.5, -3.0)]
        for dx, dy in deltas:
            self.assertTrue(scheduler.queuePanBy(self.view, dx, dy))

        self.assertEqual(int(scheduler.property("rawPanInputEventCount")) - raw_before, len(deltas))
        self.assertEqual(int(scheduler.property("flushedPanUpdateCount")), flushed_before)
        self.assertAlmostEqual(float(self.view.center_x), start_x + sum(dx for dx, _ in deltas), places=6)
        self.assertAlmostEqual(float(self.view.center_y), start_y + sum(dy for _, dy in deltas), places=6)

        self.assertTrue(
            pan_flush_spy.wait(500),
            "Timed out waiting for coalesced pan flush.",
        )

        self.assertAlmostEqual(float(self.view.center_x), start_x + sum(dx for dx, _ in deltas), places=6)
        self.assertAlmostEqual(float(self.view.center_y), start_y + sum(dy for _, dy in deltas), places=6)
        self.assertEqual(int(scheduler.property("flushedPanUpdateCount")) - flushed_before, 1)

    def test_scheduler_coalesces_wheel_zoom_steps_without_losing_cursor_anchor(self) -> None:
        scheduler = self._scheduler()
        cursor_x = 920.0
        cursor_y = 410.0
        scene_before_x = float(self.canvas.screenToSceneX(cursor_x))
        scene_before_y = float(self.canvas.screenToSceneY(cursor_y))
        raw_before = int(scheduler.property("rawZoomInputEventCount"))
        flushed_before = int(scheduler.property("flushedZoomUpdateCount"))
        zoom_flush_spy = QSignalSpy(
            getattr(scheduler, "flushedZoomUpdateCountChanged")
        )

        for _ in range(3):
            self.assertTrue(scheduler.queueWheelZoom(self.canvas, self.view, 120.0, cursor_x, cursor_y))

        self.assertEqual(int(scheduler.property("rawZoomInputEventCount")) - raw_before, 3)
        self.assertEqual(int(scheduler.property("flushedZoomUpdateCount")), flushed_before)
        self.assertAlmostEqual(float(self.view.zoom_value), 1.15 ** 3, places=6)
        self.assertAlmostEqual(float(self.canvas.screenToSceneX(cursor_x)), scene_before_x, places=5)
        self.assertAlmostEqual(float(self.canvas.screenToSceneY(cursor_y)), scene_before_y, places=5)

        self.assertTrue(
            zoom_flush_spy.wait(500),
            "Timed out waiting for coalesced wheel zoom flush.",
        )

        self.assertAlmostEqual(float(self.view.zoom_value), 1.15 ** 3, places=6)
        self.assertAlmostEqual(float(self.canvas.screenToSceneX(cursor_x)), scene_before_x, places=5)
        self.assertAlmostEqual(float(self.canvas.screenToSceneY(cursor_y)), scene_before_y, places=5)
        self.assertEqual(int(scheduler.property("flushedZoomUpdateCount")) - flushed_before, 1)

    def test_live_drag_scalars_keep_latest_values_and_flush_once_per_frame(self) -> None:
        scheduler = self._scheduler()
        raw_before = int(scheduler.property("rawLiveDragInputEventCount"))
        flushed_before = int(scheduler.property("flushedLiveDragUpdateCount"))
        profile_before = int(self.canvas.property("profileLiveDragOffsetUpdateCount"))
        membership_freezes_before = int(self.canvas.property("profileLiveDragMembershipFreezeCount"))

        self.canvas.setLiveDragOffset("node_a", 8.0, 2.0)
        frozen_ids = _variant(self.canvas.property("liveDragNodeIds"))
        frozen_lookup = _variant(self.canvas.property("liveDragNodeLookup"))
        self.canvas.setLiveDragOffset("node_a", 16.0, 6.0)
        self.canvas.setLiveDragOffset("node_a", 24.0, 10.0)

        self.assertEqual(int(scheduler.property("rawLiveDragInputEventCount")) - raw_before, 3)
        self.assertEqual(
            int(self.canvas.property("profileLiveDragMembershipFreezeCount")) - membership_freezes_before,
            1,
        )
        self.assertEqual(int(scheduler.property("flushedLiveDragUpdateCount")), flushed_before)
        self.assertEqual(frozen_ids, ["node_a"])
        self.assertEqual(frozen_lookup, {"node_a": True})
        self.assertEqual(_variant(self.canvas.property("liveDragNodeIds")), frozen_ids)
        self.assertEqual(_variant(self.canvas.property("liveDragNodeLookup")), frozen_lookup)
        self.assertEqual(float(self.canvas.property("liveDragDx")), 0.0)
        self.assertEqual(float(self.canvas.property("liveDragDy")), 0.0)

        edge_layer = self.canvas.findChild(QObject, "graphCanvasEdgeLayer")
        self.assertIsNotNone(edge_layer)
        if edge_layer is None:
            self.fail("Expected graph canvas edge layer")
        self.assertEqual(_variant(edge_layer.property("dragNodeLookup")), {"node_a": True})
        self.assertEqual(float(edge_layer.property("dragDx")), 0.0)
        self.assertEqual(float(edge_layer.property("dragDy")), 0.0)

        wait_for_condition_or_raise(
            lambda: int(scheduler.property("flushedLiveDragUpdateCount")) == flushed_before + 1,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for coalesced live-drag flush.",
        )

        self.assertEqual(_variant(self.canvas.property("liveDragNodeIds")), frozen_ids)
        self.assertEqual(_variant(self.canvas.property("liveDragNodeLookup")), frozen_lookup)
        self.assertEqual(float(self.canvas.property("liveDragDx")), 24.0)
        self.assertEqual(float(self.canvas.property("liveDragDy")), 10.0)
        self.assertEqual(_variant(edge_layer.property("dragNodeLookup")), frozen_lookup)
        self.assertEqual(float(edge_layer.property("dragDx")), 24.0)
        self.assertEqual(float(edge_layer.property("dragDy")), 10.0)
        self.assertEqual(int(self.canvas.property("profileLiveDragOffsetUpdateCount")) - profile_before, 1)

        self.canvas.clearLiveDragOffset()
        self.app.processEvents()
        self.assertEqual(_variant(self.canvas.property("liveDragNodeIds")), [])
        self.assertEqual(_variant(self.canvas.property("liveDragNodeLookup")), {})

    def test_native_overlay_suppression_tracks_live_drag_and_active_wire_drag(self) -> None:
        self.assertFalse(bool(self.canvas.property("nativeOverlaySuppressionActive")))

        self.canvas.beginViewportInteraction()
        self.app.processEvents()
        self.assertTrue(bool(self.canvas.property("nativeOverlaySuppressionActive")))
        self.canvas.finishViewportInteractionSoon()
        wait_for_condition_or_raise(
            lambda: not bool(self.canvas.property("nativeOverlaySuppressionActive")),
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for viewport suppression to recover.",
        )

        self.canvas.setLiveDragOffset("node_a", 8.0, 2.0)
        self.app.processEvents()
        self.assertTrue(bool(self.canvas.property("nativeOverlaySuppressionActive")))

        self.canvas.clearLiveDragOffset()
        self.app.processEvents()
        self.assertFalse(bool(self.canvas.property("nativeOverlaySuppressionActive")))

        self.canvas.setLiveNodeGeometry("node_a", 0.0, 0.0, 220.0, 180.0, True)
        self.app.processEvents()
        self.assertTrue(bool(self.canvas.property("nativeOverlaySuppressionActive")))

        self.canvas.setLiveNodeGeometry("node_a", 0.0, 0.0, 220.0, 180.0, False)
        self.app.processEvents()
        self.assertFalse(bool(self.canvas.property("nativeOverlaySuppressionActive")))

        self.assertTrue(self.canvas.setProperty("wireDragState", {"active": True}))
        self.app.processEvents()
        self.assertTrue(bool(self.canvas.property("nativeOverlaySuppressionActive")))

        self.assertTrue(self.canvas.setProperty("wireDragState", None))
        self.app.processEvents()
        self.assertFalse(bool(self.canvas.property("nativeOverlaySuppressionActive")))

    def test_node_drag_fast_path_keeps_anchor_motion_on_live_offset_scheduler(self) -> None:
        qml_root = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components"
        gesture_text = (qml_root / "graph" / "GraphNodeHostGestureLayer.qml").read_text(encoding="utf-8")
        host_text = (qml_root / "graph" / "GraphNodeHost.qml").read_text(encoding="utf-8")
        delegate_text = (qml_root / "graph_canvas" / "GraphCanvasNodeDelegate.qml").read_text(encoding="utf-8")

        self.assertIn("drag.target: null", gesture_text)
        self.assertIn("manualDragActive", gesture_text)
        self.assertIn("nodeDragArea.mapToItem", gesture_text)
        self.assertIn("_emitDragOffset(mouse, false)", gesture_text)
        self.assertIn("suppressNextClick", gesture_text)
        self.assertNotIn("root.host.x - root.host.worldOffset - root.host.nodeData.x", gesture_text)
        self.assertNotIn("mouse.x) - pressLocalX", gesture_text)
        self.assertIn("liveDragDx: 0.0", delegate_text)
        self.assertIn("liveDragDy: 0.0", delegate_text)
        self.assertNotIn("liveDragDxForNode", delegate_text)
        self.assertNotIn("liveDragDyForNode", delegate_text)
        self.assertIn("x: card.liveDragDx", host_text)
        self.assertIn("y: card.liveDragDy", host_text)
        self.assertIn("canvasItem.snappedDragDelta", delegate_text)
        self.assertIn("if (!movedByCommit)", delegate_text)
        self.assertIn("bridge.move_nodes_by_delta", delegate_text)
        self.assertIn("bridge.move_node(nodeId, finalSnappedX, finalSnappedY);", delegate_text)

    def test_drag_membership_and_host_timers_use_one_canvas_owner(self) -> None:
        qml_root = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components"
        state_text = (qml_root / "graph_canvas" / "GraphCanvasSceneState.qml").read_text(encoding="utf-8")
        host_text = (qml_root / "graph" / "GraphNodeHost.qml").read_text(encoding="utf-8")
        scheduler_text = (qml_root / "graph_canvas" / "GraphCanvasFrameScheduler.qml").read_text(encoding="utf-8")

        self.assertIn("function _freezeLiveDragMembership(anchorNodeId)", state_text)
        self.assertIn("property var liveDragNodeLookup", state_text)
        self.assertIn("property real liveDragDx", state_text)
        self.assertNotIn("liveDragOffsets", state_text)
        self.assertNotIn("Timer {", host_text)
        self.assertIn("scheduleToolbarGrace", scheduler_text)
        self.assertIn("registerElapsedHost", scheduler_text)
