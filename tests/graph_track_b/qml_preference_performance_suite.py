from __future__ import annotations

from tests.graph_track_b.qml_support import (
    GraphCanvasQmlPreferenceTestBase,
    QObject,
    QPoint,
    QQuickWindow,
    QTest,
    Qt,
    wait_for_condition_or_raise,
)

_CANVAS_IDLE_SETTLE_TIMEOUT_MS = 6500


class GraphCanvasQmlPreferencePerformanceTests(GraphCanvasQmlPreferenceTestBase):
    __test__ = True

    def test_viewport_applies_zoom_and_center_updates_without_forcing_viewport_cache_mode(self) -> None:
        world = self.canvas.findChild(QObject, "graphCanvasWorld")
        self.assertIsNotNone(world)
        self.assertFalse(bool(self.canvas.property("interactionActive")))
        self.assertFalse(bool(self.canvas.property("viewportInteractionWorldCacheActive")))

        self.view.set_zoom(2.5)
        self.view.centerOn(12.0, 18.0)
        self.app.processEvents()

        self.assertFalse(bool(self.canvas.property("interactionActive")))
        self.assertFalse(bool(self.canvas.property("viewportInteractionWorldCacheActive")))
        self.assertAlmostEqual(float(world.property("scale")), 2.5, places=6)
        expected_x = 1280.0 * 0.5 - ((12.0 + float(self.canvas.property("worldOffset"))) * 2.5)
        expected_y = 720.0 * 0.5 - ((18.0 + float(self.canvas.property("worldOffset"))) * 2.5)
        self.assertAlmostEqual(float(world.property("x")), expected_x, places=6)
        self.assertAlmostEqual(float(world.property("y")), expected_y, places=6)

    def test_graph_canvas_visible_models_refresh_on_idle_settle_not_view_commit(self) -> None:
        root_layers = self.canvas.findChild(QObject, "graphCanvasRootLayers")
        self.assertIsNotNone(root_layers)

        baseline_queries = int(root_layers.property("profileVisibleModelQueryCount") or 0)
        baseline_exact_refreshes = int(root_layers.property("profileVisibleModelExactRefreshCount") or 0)

        self.view.centerOn(8.0, 0.0)
        self.app.processEvents()

        self.assertEqual(
            int(root_layers.property("profileVisibleModelQueryCount") or 0),
            baseline_queries,
        )
        wait_for_condition_or_raise(
            lambda: int(root_layers.property("profileVisibleModelExactRefreshCount") or 0)
            > baseline_exact_refreshes,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for idle exact visible-model refresh.",
        )
        self.assertGreater(
            int(root_layers.property("profileVisibleModelQueryCount") or 0),
            baseline_queries,
        )

    def test_graph_canvas_wheel_zoom_keeps_cursor_anchor_with_single_viewport_commit(self) -> None:
        self.view.centerOn(60.0, -30.0)
        self.app.processEvents()

        commits = 0

        def _count_commit() -> None:
            nonlocal commits
            commits += 1

        self.view.view_state_changed.connect(_count_commit)

        cursor_x = 920.0
        cursor_y = 410.0
        scene_before_x = float(self.canvas.screenToSceneX(cursor_x))
        scene_before_y = float(self.canvas.screenToSceneY(cursor_y))

        applied = self.canvas.applyWheelZoom(
            {"x": cursor_x, "y": cursor_y, "angleDelta": {"y": 120}, "inverted": False}
        )
        self.assertTrue(applied)
        self.app.processEvents()

        scene_after_x = float(self.canvas.screenToSceneX(cursor_x))
        scene_after_y = float(self.canvas.screenToSceneY(cursor_y))
        self.assertEqual(commits, 1)
        self.assertAlmostEqual(float(self.view.zoom_value), 1.15, places=6)
        self.assertAlmostEqual(scene_before_x, scene_after_x, places=6)
        self.assertAlmostEqual(scene_before_y, scene_after_y, places=6)

    def test_graph_canvas_right_hold_box_zoom_frames_viewport_rect(self) -> None:
        window = QQuickWindow()
        window.resize(1280, 720)
        self.canvas.setParentItem(window.contentItem())
        window.show()
        self.app.processEvents()

        start = QPoint(200, 120)
        end = QPoint(700, 370)

        try:
            QTest.mousePress(window, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, start)
            QTest.mouseMove(window, end)
            self.app.processEvents()

            wait_for_condition_or_raise(
                lambda: bool(self.canvas.property("interactionActive")),
                timeout_ms=500,
                app=self.app,
                timeout_message="Timed out waiting for graph canvas box-zoom drag to arm.",
            )

            QTest.mouseRelease(window, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, end)
            self.app.processEvents()

            self.assertAlmostEqual(float(self.view.zoom_value), 2.464, places=3)
            self.assertAlmostEqual(float(self.view.center_x), -190.0, places=3)
            self.assertAlmostEqual(float(self.view.center_y), -115.0, places=3)

            wait_for_condition_or_raise(
                lambda: not bool(self.canvas.property("interactionActive")),
                timeout_ms=_CANVAS_IDLE_SETTLE_TIMEOUT_MS,
                app=self.app,
                timeout_message="Timed out waiting for graph canvas box-zoom interaction to settle.",
            )
        finally:
            self.canvas.setParentItem(None)
            window.close()
            window.deleteLater()
            self.app.processEvents()



    def test_edge_layer_gap_break_metadata_persists_during_viewport_interaction(self) -> None:
        edge_layer = self._create_edge_layer({"viewBridge": self.view})
        self.view.centerOn(200.0, 200.0)
        self.app.processEvents()

        def _bezier_edge(edge_id: str, sx: float, sy: float, tx: float, ty: float) -> dict[str, object]:
            return {
                "edge_id": edge_id,
                "source_node_id": "",
                "source_port_key": "",
                "target_node_id": "",
                "target_port_key": "",
                "source_port_kind": "data",
                "target_port_kind": "data",
                "edge_family": "standard",
                "label": "",
                "visual_style": {},
                "flow_style": {},
                "source_port_side": "right",
                "target_port_side": "left",
                "source_anchor_side": "right",
                "target_anchor_side": "left",
                "source_anchor_kind": "scene",
                "target_anchor_kind": "scene",
                "source_anchor_node_id": "",
                "target_anchor_node_id": "",
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

        selected_edge_id = "selected_over"
        plain_edge_id = "plain_under"
        edge_layer.setProperty(
            "edges",
            [
                _bezier_edge(selected_edge_id, 80.0, 320.0, 320.0, 80.0),
                _bezier_edge(plain_edge_id, 80.0, 80.0, 320.0, 320.0),
            ],
        )
        edge_layer.setProperty("selectedEdgeIds", [selected_edge_id])
        self.app.processEvents()
        edge_layer.requestRedraw()
        self.app.processEvents()

        baseline_under = edge_layer._visibleEdgeSnapshot(plain_edge_id).toVariant()
        baseline_selected = edge_layer._visibleEdgeSnapshot(selected_edge_id).toVariant()
        self.assertEqual(baseline_under["drawOrderIndex"], 0)
        self.assertEqual(baseline_selected["drawOrderIndex"], 1)
        self.assertEqual(baseline_under["crossingBreaks"], [])
        self.assertEqual(baseline_selected["crossingBreaks"], [])

        edge_layer.setProperty("edgeCrossingStyle", "gap_break")
        self.app.processEvents()
        edge_layer.requestRedraw()
        self.app.processEvents()

        decorated_under = edge_layer._visibleEdgeSnapshot(plain_edge_id).toVariant()
        decorated_selected = edge_layer._visibleEdgeSnapshot(selected_edge_id).toVariant()
        self.assertEqual(decorated_under["drawOrderIndex"], 0)
        self.assertEqual(decorated_selected["drawOrderIndex"], 1)
        self.assertGreaterEqual(len(decorated_under["crossingBreaks"]), 1)
        self.assertEqual(decorated_selected["crossingBreaks"], [])
        self.assertIn("centerX", decorated_under["crossingBreaks"][0])
        self.assertIn("tangentX", decorated_under["crossingBreaks"][0])

        self.view.set_zoom(2.0)
        edge_layer.setProperty("viewportInteractionActive", True)
        self.app.processEvents()
        edge_layer.requestRedraw()
        self.app.processEvents()

        active_under = edge_layer._visibleEdgeSnapshot(plain_edge_id).toVariant()
        active_selected = edge_layer._visibleEdgeSnapshot(selected_edge_id).toVariant()
        self.assertEqual(active_under["crossingBreaks"], decorated_under["crossingBreaks"])
        self.assertEqual(active_under["crossingSamplePoints"], decorated_under["crossingSamplePoints"])
        self.assertEqual(active_selected["crossingBreaks"], [])

        edge_layer.setProperty("viewportInteractionActive", False)
        self.app.processEvents()
        edge_layer.requestRedraw()
        self.app.processEvents()

        settled_under = edge_layer._visibleEdgeSnapshot(plain_edge_id).toVariant()
        settled_selected = edge_layer._visibleEdgeSnapshot(selected_edge_id).toVariant()
        self.assertGreaterEqual(len(settled_under["crossingBreaks"]), 1)
        self.assertNotEqual(
            settled_under["crossingBreaks"][0]["startDistance"],
            decorated_under["crossingBreaks"][0]["startDistance"],
        )
        self.assertNotEqual(settled_under["crossingSamplePoints"], decorated_under["crossingSamplePoints"])
        self.assertEqual(settled_selected["crossingBreaks"], [])

        edge_layer.deleteLater()
        self.app.processEvents()

    def test_graph_canvas_grid_uses_one_render_item_without_simplifying_visuals(self) -> None:
        background = self.canvas.findChild(QObject, "graphCanvasBackground")
        shader_renderer = self.canvas.findChild(QObject, "graphCanvasGridShaderRenderer")
        self.assertIsNotNone(background)
        self.assertIsNotNone(shader_renderer)
        for style in ("points", "lines"):
            self.bridge.set_graphics_grid_style_value(style)
            self.app.processEvents()
            self.assertTrue(bool(background.property("effectiveShowGrid")))
            self.assertEqual(int(background.property("profileGridItemCount")), 1)
            self.assertEqual(shader_renderer.childItems(), [])

    def test_graph_canvas_minimap_static_cache_is_decoupled_from_viewport_rect_updates(self) -> None:
        minimap_overlay = self.canvas.findChild(QObject, "graphCanvasMinimapOverlay")
        minimap_viewport = self.canvas.findChild(QObject, "graphCanvasMinimapViewport")
        minimap_viewport_rect = self.canvas.findChild(QObject, "graphCanvasMinimapViewportRect")
        self.assertIsNotNone(minimap_overlay)
        self.assertIsNotNone(minimap_viewport)
        self.assertIsNotNone(minimap_viewport_rect)

        wait_for_condition_or_raise(
            lambda: int(minimap_overlay.property("profileMinimapStaticUpdateCount") or 0) >= 1,
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for minimap static cache profiling to initialize.",
        )

        static_updates = int(minimap_overlay.property("profileMinimapStaticUpdateCount") or 0)
        viewport_updates = int(minimap_overlay.property("profileMinimapViewportUpdateCount") or 0)

        self.view.centerOn(260.0, -180.0)
        wait_for_condition_or_raise(
            lambda: int(minimap_overlay.property("profileMinimapViewportUpdateCount") or 0) > viewport_updates,
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for minimap viewport-rectangle profiling to update.",
        )

        self.assertEqual(
            int(minimap_overlay.property("profileMinimapStaticUpdateCount") or 0),
            static_updates,
        )
        self.assertGreater(
            int(minimap_viewport_rect.property("_geometryUpdateCount") or 0),
            0,
        )
        self.assertTrue(bool(minimap_overlay.property("minimapContentVisible")))
        self.assertTrue(bool(minimap_viewport.property("visible")))
        self.assertGreaterEqual(float(minimap_overlay.property("profileLastMinimapStaticUpdateMs") or 0.0), 0.0)
        self.assertGreaterEqual(float(minimap_overlay.property("profileLastMinimapViewportUpdateMs") or 0.0), 0.0)

    def test_graph_canvas_coalesces_view_state_redraw_requests_per_commit(self) -> None:
        background = self.canvas.findChild(QObject, "graphCanvasBackground")
        edge_layer = self.canvas.findChild(QObject, "graphCanvasEdgeLayer")
        retained_layer = edge_layer.findChild(QObject, "graphCanvasEdgeRetainedLayer") if edge_layer else None

        self.assertIsNotNone(background)
        self.assertIsNotNone(edge_layer)
        self.assertIsNotNone(retained_layer)

        background_redraws = int(background.property("_redrawRequestCount"))
        edge_redraws = int(edge_layer.property("_redrawRequestCount"))
        background_grid_updates = int(background.property("profileGridUpdateCount"))
        self.assertIn(str(background.property("profileGridRendererKind")), ("shader", "canvas"))

        zoom_before = float(self.view.zoom_value)
        self.view.set_zoom(1.4)
        self.assertEqual(int(background.property("_redrawRequestCount")) - background_redraws, 0)
        self.assertEqual(int(edge_layer.property("_redrawRequestCount")) - edge_redraws, 0)
        self.assertAlmostEqual(
            float(retained_layer.property("viewportTransformCompensationScale")),
            1.4 / zoom_before,
            places=5,
        )
        wait_for_condition_or_raise(
            lambda: int(background.property("_redrawRequestCount")) - background_redraws == 1
            and int(edge_layer.property("_redrawRequestCount")) - edge_redraws == 1,
            timeout_ms=120,
            app=self.app,
            timeout_message="Timed out waiting for deferred zoom redraw flush.",
        )

        self.assertEqual(int(background.property("_redrawRequestCount")) - background_redraws, 1)
        self.assertEqual(int(edge_layer.property("_redrawRequestCount")) - edge_redraws, 1)
        self.assertEqual(int(background.property("profileGridUpdateCount")) - background_grid_updates, 1)
        self.assertAlmostEqual(float(retained_layer.property("viewportTransformCompensationScale")), 1.0, places=5)

        background_redraws = int(background.property("_redrawRequestCount"))
        edge_redraws = int(edge_layer.property("_redrawRequestCount"))
        background_grid_updates = int(background.property("profileGridUpdateCount"))

        self.view.centerOn(18.0, -22.0)
        self.assertEqual(int(background.property("_redrawRequestCount")) - background_redraws, 0)
        self.assertEqual(int(edge_layer.property("_redrawRequestCount")) - edge_redraws, 0)
        pan_compensation = abs(float(retained_layer.property("viewportTransformCompensationX"))) + abs(
            float(retained_layer.property("viewportTransformCompensationY"))
        )
        self.assertGreater(pan_compensation, 0.1)
        wait_for_condition_or_raise(
            lambda: int(background.property("_redrawRequestCount")) - background_redraws == 1
            and int(edge_layer.property("_redrawRequestCount")) - edge_redraws == 1,
            timeout_ms=120,
            app=self.app,
            timeout_message="Timed out waiting for deferred pan redraw flush.",
        )

        self.assertEqual(int(background.property("_redrawRequestCount")) - background_redraws, 1)
        self.assertEqual(int(edge_layer.property("_redrawRequestCount")) - edge_redraws, 1)
        self.assertEqual(int(background.property("profileGridUpdateCount")) - background_grid_updates, 1)
        self.assertAlmostEqual(float(retained_layer.property("viewportTransformCompensationX")), 0.0, places=5)
        self.assertAlmostEqual(float(retained_layer.property("viewportTransformCompensationY")), 0.0, places=5)

        commits = 0

        def _count_commit() -> None:
            nonlocal commits
            commits += 1

        self.view.view_state_changed.connect(_count_commit)
        background_redraws = int(background.property("_redrawRequestCount"))
        edge_redraws = int(edge_layer.property("_redrawRequestCount"))

        applied = self.canvas.applyWheelZoom(
            {"x": 920.0, "y": 410.0, "angleDelta": {"y": 120}, "inverted": False}
        )

        self.assertTrue(applied)
        self.assertEqual(commits, 1)
        self.assertEqual(int(background.property("_redrawRequestCount")) - background_redraws, 0)
        self.assertEqual(int(edge_layer.property("_redrawRequestCount")) - edge_redraws, 0)
        wait_for_condition_or_raise(
            lambda: int(background.property("_redrawRequestCount")) - background_redraws == 1
            and int(edge_layer.property("_redrawRequestCount")) - edge_redraws == 1,
            timeout_ms=120,
            app=self.app,
            timeout_message="Timed out waiting for deferred wheel redraw flush.",
        )

        self.assertEqual(int(background.property("_redrawRequestCount")) - background_redraws, 1)
        self.assertEqual(int(edge_layer.property("_redrawRequestCount")) - edge_redraws, 1)

    def test_graph_canvas_coalesces_direct_edge_redraw_requests_per_frame(self) -> None:
        scheduler = self.canvas.findChild(QObject, "graphCanvasFrameScheduler")
        edge_layer = self.canvas.findChild(QObject, "graphCanvasEdgeLayer")

        self.assertIsNotNone(scheduler)
        self.assertIsNotNone(edge_layer)

        requested_redraws = int(scheduler.property("requestedRedrawCount"))
        coalesced_redraws = int(scheduler.property("coalescedRedrawRequestCount"))
        flushed_frames = int(scheduler.property("flushedFrameCount"))
        edge_redraws = int(edge_layer.property("_redrawRequestCount"))

        self.canvas.requestEdgeRedraw()
        self.canvas.requestEdgeRedraw()
        self.canvas.requestEdgeRedraw()

        self.assertEqual(int(edge_layer.property("_redrawRequestCount")) - edge_redraws, 0)
        self.assertEqual(int(scheduler.property("requestedRedrawCount")) - requested_redraws, 3)
        self.assertGreaterEqual(
            int(scheduler.property("coalescedRedrawRequestCount")) - coalesced_redraws,
            2,
        )
        wait_for_condition_or_raise(
            lambda: int(edge_layer.property("_redrawRequestCount")) - edge_redraws == 1
            and int(scheduler.property("flushedFrameCount")) > flushed_frames,
            timeout_ms=120,
            app=self.app,
            timeout_message="Timed out waiting for coalesced direct edge redraw flush.",
        )

        self.assertEqual(int(edge_layer.property("_redrawRequestCount")) - edge_redraws, 1)

    def test_graph_canvas_coalesces_view_state_and_edge_redraws_in_one_frame(self) -> None:
        scheduler = self.canvas.findChild(QObject, "graphCanvasFrameScheduler")
        background = self.canvas.findChild(QObject, "graphCanvasBackground")
        edge_layer = self.canvas.findChild(QObject, "graphCanvasEdgeLayer")

        self.assertIsNotNone(scheduler)
        self.assertIsNotNone(background)
        self.assertIsNotNone(edge_layer)

        background_redraws = int(background.property("_redrawRequestCount"))
        edge_redraws = int(edge_layer.property("_redrawRequestCount"))
        flushed_frames = int(scheduler.property("flushedFrameCount"))

        self.view.set_zoom(1.7)
        self.canvas.requestEdgeRedraw()
        self.canvas.requestEdgeRedraw()

        self.assertEqual(int(background.property("_redrawRequestCount")) - background_redraws, 0)
        self.assertEqual(int(edge_layer.property("_redrawRequestCount")) - edge_redraws, 0)
        wait_for_condition_or_raise(
            lambda: int(background.property("_redrawRequestCount")) - background_redraws == 1
            and int(edge_layer.property("_redrawRequestCount")) - edge_redraws == 1
            and int(scheduler.property("flushedFrameCount")) > flushed_frames,
            timeout_ms=120,
            app=self.app,
            timeout_message="Timed out waiting for combined view-state and edge redraw flush.",
        )

        self.assertEqual(int(background.property("_redrawRequestCount")) - background_redraws, 1)
        self.assertEqual(int(edge_layer.property("_redrawRequestCount")) - edge_redraws, 1)

    def test_graph_canvas_input_layers_disable_full_canvas_hover_tracking(self) -> None:
        marquee_area = self.canvas.findChild(QObject, "graphCanvasMarqueeArea")
        pan_area = self.canvas.findChild(QObject, "graphCanvasPanArea")

        self.assertIsNotNone(marquee_area)
        self.assertIsNotNone(pan_area)
        self.assertFalse(bool(marquee_area.property("hoverEnabled")))
        self.assertFalse(bool(pan_area.property("hoverEnabled")))

__all__ = ['GraphCanvasQmlPreferencePerformanceTests']
