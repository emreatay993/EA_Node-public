from __future__ import annotations

from tests.graph_track_b.qml_support import (
    GraphCanvasCommandBridge,
    GraphCanvasQmlPreferenceTestBase,
    GraphCanvasStateBridge,
    GraphModel,
    GraphSceneBridge,
    QObject,
    QMetaObject,
    QQmlComponent,
    QQuickWindow,
    QTest,
    Qt,
    QUrl,
    ViewportBridge,
    _GRAPH_CANVAS_QML_PATH,
    _NODE_CARD_QML_PATH,
    _GraphCanvasPreferenceBridge,
    _GraphCanvasSessionBridge,
    build_default_registry,
    _build_edge_crossing_pipe_registry,
    _named_child_items,
    pyqtProperty,
    pyqtSignal,
    wait_for_condition_or_raise,
)
from tests.graph_track_b.theme_support import (
    STITCH_DARK_V1,
    STITCH_LIGHT_V1,
    _alpha_color_name,
    _color_name,
)
from ea_node_editor.ui.shell.tooltip_policy import (
    TOOLTIP_CATEGORY_NAMES,
    default_tooltip_category_preferences,
    tooltip_category_effectively_visible,
)


class GraphCanvasQmlPreferenceRenderingTests(GraphCanvasQmlPreferenceTestBase):
    def test_graph_canvas_properties_follow_runtime_preference_updates(self) -> None:
        edge_layer = self.canvas.findChild(QObject, "graphCanvasEdgeLayer")
        self.assertIsNotNone(edge_layer)
        self.assertTrue(bool(self.canvas.property("showGrid")))
        self.assertEqual(str(self.canvas.property("gridStyle")), "lines")
        self.assertEqual(str(self.canvas.property("edgeCrossingStyle")), "none")
        self.assertTrue(bool(self.canvas.property("minimapVisible")))
        self.assertTrue(bool(self.canvas.property("minimapExpanded")))
        self.assertTrue(bool(self.canvas.property("showPortLabels")))
        self.assertEqual(str(self.canvas.property("nodeElapsedTimeUnit")), "seconds")
        self.assertEqual(str(edge_layer.property("edgeCrossingStyle")), "none")

        self.bridge.set_graphics_show_grid_value(False)
        self.bridge.set_graphics_show_minimap_value(False)
        self.canvas_source.set_graphics_minimap_expanded_value(False)
        self.bridge.set_graphics_show_port_labels_value(False)
        self.bridge.set_graphics_node_elapsed_time_unit_value("milliseconds")
        self.bridge.set_graphics_edge_crossing_style_value("gap_break")
        self.app.processEvents()

        self.assertFalse(bool(self.canvas.property("showGrid")))
        self.assertFalse(bool(self.canvas.property("minimapVisible")))
        self.assertFalse(bool(self.canvas.property("minimapExpanded")))
        self.assertFalse(bool(self.canvas.property("showPortLabels")))
        self.assertEqual(str(self.canvas.property("nodeElapsedTimeUnit")), "milliseconds")
        self.assertEqual(str(self.canvas.property("edgeCrossingStyle")), "gap_break")
        self.assertEqual(str(edge_layer.property("edgeCrossingStyle")), "gap_break")

    def test_graph_canvas_root_packetization_helpers_remain_registered(self) -> None:
        graph_canvas_text = _GRAPH_CANVAS_QML_PATH.read_text(encoding="utf-8")
        root_layers_text = (_GRAPH_CANVAS_QML_PATH.parent / "graph_canvas" / "GraphCanvasRootLayers.qml").read_text(
            encoding="utf-8"
        )
        background_text = (_GRAPH_CANVAS_QML_PATH.parent / "graph_canvas" / "GraphCanvasBackground.qml").read_text(
            encoding="utf-8"
        )
        root_api_text = (_GRAPH_CANVAS_QML_PATH.parent / "graph_canvas" / "GraphCanvasRootApi.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('import "graph_canvas/GraphCanvasRootApi.js" as GraphCanvasRootApi', graph_canvas_text)
        self.assertIn("GraphCanvasComponents.GraphCanvasRootLayers {", graph_canvas_text)
        self.assertIn("readonly property var canvasStateBridgeRef: root.canvasStateBridge || null", graph_canvas_text)
        self.assertIn("GraphCanvasGridShader {", background_text)
        self.assertIn("function snapToGridValue(canvasStateBridge, value) {", root_api_text)

    def test_graph_node_semantic_palette_replaces_execution_glows(self) -> None:
        chrome_text = (_GRAPH_CANVAS_QML_PATH.parent / "graph" / "GraphNodeChromeBackground.qml").read_text(
            encoding="utf-8"
        )
        theme_text = (_GRAPH_CANVAS_QML_PATH.parent / "graph" / "GraphNodeHostTheme.qml").read_text(
            encoding="utf-8"
        )
        flowchart_text = (
            _GRAPH_CANVAS_QML_PATH.parent / "graph" / "passive" / "GraphFlowchartNodeSurface.qml"
        ).read_text(encoding="utf-8")

        for object_name in (
            "graphNodeFailureHalo",
            "graphNodeFailurePulseHalo",
            "graphNodeRunningHalo",
            "graphNodeRunningPulseHalo",
            "graphNodeCompletedFlashHalo",
            "graphNodeSelectedRunPreviewHalo",
            "graphNodeRunFreshHalo",
        ):
            self.assertNotIn(f'objectName: "{object_name}"', chrome_text)
        self.assertNotIn('objectName: "graphNodeFlowchartRunFreshHalo"', flowchart_text)
        self.assertIn('objectName: "graphNodeSelectedHalo"', chrome_text)
        self.assertIn('objectName: "graphNodeFlowchartSelectedHalo"', flowchart_text)
        for color in (
            "#F6F8F8", "#F9FBFC", "#6B7277", "#17174B", "#43436D",
            "#FADB8E", "#FCDD90", "#F0B72D", "#FAA59A", "#FCA79C", "#E15949",
            "#CDD0D1", "#CFD2D3", "#BDC3C7", "#9697A8", "#A2A4B2",
            "#ACDCF0", "#ADDDF1", "#009EE0",
            "#403C2D", "#3A372A", "#81795C", "#F3F3F1", "#D7D5CE",
            "#5A4A28", "#4E4024", "#D9A93C", "#F8F4E8", "#E6D6B1",
            "#5D2F30", "#51292A", "#E36155", "#FBEAE8", "#E7C2BE",
            "#404244", "#393B3D", "#5D6164", "#B3B7BC", "#9EA3A8",
            "#1F5369", "#1A485B", "#00A5E4", "#F2F7FA", "#C9E8F3",
        ):
            self.assertIn(color, theme_text)

    def test_graph_canvas_background_switches_between_line_point_and_fallback_renderer_modes(self) -> None:
        background = self.canvas.findChild(QObject, "graphCanvasBackground")
        shader_renderer = self.canvas.findChild(QObject, "graphCanvasGridShaderRenderer")
        canvas_fallback = self.canvas.findChild(QObject, "graphCanvasGridCanvasFallback")
        self.assertIsNotNone(background)
        self.assertIsNotNone(shader_renderer)
        self.assertIsNotNone(canvas_fallback)
        self.assertEqual(str(background.property("gridStyle")), "lines")
        self.assertEqual(str(background.property("effectiveGridStyle")), "lines")
        renderer_kind = str(background.property("profileGridRendererKind"))
        self.assertIn(renderer_kind, ("shader", "canvas"))
        self.assertEqual(bool(shader_renderer.property("visible")), renderer_kind == "shader")
        self.assertEqual(bool(canvas_fallback.property("visible")), renderer_kind == "canvas")

        self.bridge.set_graphics_grid_style_value("points")
        self.app.processEvents()

        self.assertEqual(str(self.canvas.property("gridStyle")), "points")
        self.assertEqual(str(background.property("gridStyle")), "points")
        self.assertEqual(str(background.property("effectiveGridStyle")), "points")
        self.assertEqual(str(shader_renderer.property("gridStyle")), "points")
        self.assertEqual(str(background.property("profileGridRendererKind")), renderer_kind)

        background.setProperty("gridRendererPreference", "canvas")
        self.app.processEvents()

        self.assertEqual(str(background.property("profileGridRendererKind")), "canvas")
        self.assertFalse(bool(shader_renderer.property("visible")))
        self.assertTrue(bool(canvas_fallback.property("visible")))

    def test_edge_layer_reports_retained_renderer_and_fallback_renderer_contract(self) -> None:
        edge_layer = self._create_edge_layer({"edgeRendererPreference": "retained_qml"})
        retained_layer = edge_layer.findChild(QObject, "graphCanvasEdgeRetainedLayer")
        canvas_layer = edge_layer.findChild(QObject, "graphCanvasEdgeCanvasLayer")
        scenegraph_layer = edge_layer.findChild(QObject, "graphCanvasEdgeScenegraphLayer")
        self.assertIsNotNone(retained_layer)
        self.assertIsNotNone(canvas_layer)
        self.assertIsNotNone(scenegraph_layer)
        if retained_layer is None or canvas_layer is None or scenegraph_layer is None:
            self.fail("Expected all edge renderer layers to be present")

        edge_layer.setProperty(
            "edges",
            [
                {
                    "edge_id": "retained_edge",
                    "source_node_id": "source",
                    "source_port_key": "out",
                    "target_node_id": "target",
                    "target_port_key": "in",
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
                    "source_anchor_kind": "node",
                    "target_anchor_kind": "node",
                    "source_anchor_node_id": "",
                    "target_anchor_node_id": "",
                    "source_hidden_by_backdrop_id": "",
                    "target_hidden_by_backdrop_id": "",
                    "source_anchor_bounds": {"x": 80.0, "y": 80.0, "width": 40.0, "height": 40.0},
                    "target_anchor_bounds": {"x": 320.0, "y": 80.0, "width": 40.0, "height": 40.0},
                    "lane_bias": 0.0,
                    "sx": 80.0,
                    "sy": 80.0,
                    "tx": 320.0,
                    "ty": 80.0,
                    "c1x": 160.0,
                    "c1y": 80.0,
                    "c2x": 240.0,
                    "c2y": 80.0,
                    "route": "bezier",
                    "pipe_points": [],
                    "color": "#55AA66",
                    "data_type_warning": False,
                }
            ],
        )
        edge_layer.requestRedraw()
        self.app.processEvents()

        def _variant(value):
            if hasattr(value, "toVariant"):
                value = value.toVariant()
            return value

        def _active_paint(edge_id: str) -> dict[str, object] | None:
            diagnostics = _variant(edge_layer.property("activeEdgePaintDiagnosticsByEdgeId")) or {}
            if not isinstance(diagnostics, dict):
                diagnostics = dict(diagnostics)
            payload = _variant(diagnostics.get(edge_id))
            if payload is None:
                return None
            return payload if isinstance(payload, dict) else dict(payload)

        wait_for_condition_or_raise(
            lambda: str(edge_layer.property("edgeRendererKind")) == "retained_qml"
            and _active_paint("retained_edge") is not None,
            timeout_ms=400,
            app=self.app,
            timeout_message="Timed out waiting for retained edge renderer diagnostics.",
        )

        self.assertEqual(str(edge_layer.property("edgeRendererRequestedKind")), "retained_qml")
        self.assertEqual(str(edge_layer.property("edgeRendererKind")), "retained_qml")
        self.assertFalse(bool(edge_layer.property("edgeRendererCanvasFallbackActive")))
        self.assertEqual(str(edge_layer.property("edgeRendererFallbackReason")), "")
        self.assertTrue(bool(retained_layer.property("visible")))
        self.assertFalse(bool(canvas_layer.property("visible")))
        self.assertEqual(int(retained_layer.property("retainedEdgeCount")), 1)
        retained_paint = _active_paint("retained_edge")
        self.assertIsNotNone(retained_paint)
        if retained_paint is None:
            self.fail("Expected retained renderer diagnostics")
        self.assertFalse(bool(retained_paint["flowEdge"]))
        self.assertEqual(float(retained_paint["strokeAlpha"]), 1.0)
        self.assertAlmostEqual(float(retained_paint["strokeWidthScreenPx"]), 2.0, places=6)

        edge_layer.setProperty("edgeRendererPreference", "native_scenegraph")
        edge_layer.requestRedraw()
        self.app.processEvents()

        self.assertEqual(str(edge_layer.property("edgeRendererRequestedKind")), "native_scenegraph")
        self.assertEqual(str(edge_layer.property("edgeRendererKind")), "canvas")
        self.assertTrue(bool(edge_layer.property("edgeRendererCanvasFallbackActive")))
        self.assertEqual(
            str(edge_layer.property("edgeRendererFallbackReason")),
            "native_scenegraph_renderer_unavailable",
        )
        self.assertTrue(bool(canvas_layer.property("visible")))
        self.assertFalse(bool(retained_layer.property("visible")))

        edge_layer.setProperty("edgeRendererPreference", "canvas")
        edge_layer.requestRedraw()
        self.app.processEvents()

        self.assertEqual(str(edge_layer.property("edgeRendererRequestedKind")), "canvas")
        self.assertEqual(str(edge_layer.property("edgeRendererKind")), "canvas")
        self.assertFalse(bool(edge_layer.property("edgeRendererCanvasFallbackActive")))

        edge_layer.deleteLater()
        self.app.processEvents()

    def test_graph_canvas_passes_port_label_preference_into_graph_node_hosts(self) -> None:
        from PyQt6.QtCore import pyqtProperty, pyqtSignal

        node_payload = {
            "node_id": "node_port_label_preference_test",
            "type_id": "core.logger",
            "title": "Logger",
            "x": 120.0,
            "y": 140.0,
            "width": 210.0,
            "height": 88.0,
            "accent": "#2F89FF",
            "collapsed": False,
            "selected": False,
            "can_enter_scope": False,
            "surface_family": "standard",
            "surface_variant": "",
            "ports": [
                {
                    "key": "payload",
                    "label": "Payload",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "any",
                    "connected": False,
                },
                {
                    "key": "result",
                    "label": "Result",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "any",
                    "connected": False,
                },
            ],
            "inline_properties": [],
            "surface_metrics": {
                "default_width": 210.0,
                "default_height": 88.0,
                "min_width": 120.0,
                "min_height": 50.0,
                "collapsed_width": 130.0,
                "collapsed_height": 36.0,
                "header_height": 24.0,
                "header_top_margin": 4.0,
                "body_top": 30.0,
                "body_height": 30.0,
                "port_top": 60.0,
                "port_height": 18.0,
                "port_center_offset": 6.0,
                "port_side_margin": 8.0,
                "port_dot_radius": 3.5,
                "resize_handle_size": 16.0,
            },
        }

        class CanvasStateBridgeStub(QObject):
            graphics_preferences_changed = pyqtSignal()
            scene_nodes_changed = pyqtSignal()

            def __init__(
                self,
                preference_bridge: _GraphCanvasPreferenceBridge,
                canvas_source: object,
            ) -> None:
                super().__init__()
                self._preference_bridge = preference_bridge
                self._canvas_source = canvas_source
                self._nodes_model = [dict(node_payload)]
                self._preference_bridge.graphics_preferences_changed.connect(self.graphics_preferences_changed.emit)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_minimap_expanded(self) -> bool:
                return bool(self._canvas_source.graphics_minimap_expanded)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_grid(self) -> bool:
                return bool(self._preference_bridge.graphics_show_grid)

            @pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_grid_style(self) -> str:
                return str(self._preference_bridge.graphics_grid_style)

            @pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_edge_crossing_style(self) -> str:
                return str(self._preference_bridge.graphics_edge_crossing_style)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_minimap(self) -> bool:
                return bool(self._preference_bridge.graphics_show_minimap)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_port_labels(self) -> bool:
                return bool(self._preference_bridge.graphics_show_port_labels)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_node_shadow(self) -> bool:
                return True

            @pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_strength(self) -> int:
                return 70

            @pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_softness(self) -> int:
                return 50

            @pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_offset(self) -> int:
                return 4

            @pyqtProperty("QVariantList", notify=scene_nodes_changed)
            def nodes_model(self) -> list[dict[str, object]]:
                return list(self._nodes_model)

        self.canvas.deleteLater()
        self.app.processEvents()

        canvas_state_bridge = CanvasStateBridgeStub(self.bridge, self.canvas_source)
        canvas_command_bridge = GraphCanvasCommandBridge(
            search_scope_controller=self.canvas_source,  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            run_controller=self.canvas_source,  # type: ignore[arg-type]
            inspector_source=self.canvas_source,  # type: ignore[arg-type]
            library_source=self.canvas_source,  # type: ignore[arg-type]
            workspace_edit_controller=self.canvas_source,  # type: ignore[arg-type]
            workspace_drop_connect_controller=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=self.bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        self.canvas = self._create_canvas(
            {
                "canvasStateBridge": canvas_state_bridge,
                "canvasCommandBridge": canvas_command_bridge,
                "width": 1280.0,
                "height": 720.0,
            }
        )

        wait_for_condition_or_raise(
            lambda: len(_named_child_items(self.canvas, "graphNodeCard")) == 1,
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for graph canvas node host to appear.",
        )
        node_card = _named_child_items(self.canvas, "graphNodeCard")[0]

        self.assertTrue(bool(self.canvas.property("showPortLabels")))
        self.assertTrue(bool(node_card.property("showPortLabelsPreference")))
        self.assertFalse(bool(node_card.property("_tooltipOnlyPortLabelsActive")))

        self.bridge.set_graphics_show_port_labels_value(False)
        wait_for_condition_or_raise(
            lambda: (
                not bool(self.canvas.property("showPortLabels"))
                and not bool(node_card.property("showPortLabelsPreference"))
            ),
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for graph canvas port-label preference propagation.",
        )

        self.assertTrue(bool(node_card.property("_tooltipOnlyPortLabelsActive")))

    def test_graph_canvas_port_label_general_tooltips_follow_policy_but_inactive_reason_tooltips_remain_visible(
        self,
    ) -> None:
        from PyQt6.QtCore import QPoint, QPointF, pyqtProperty, pyqtSignal

        node_payload = {
            "node_id": "node_tooltip_policy_test",
            "type_id": "core.logger",
            "title": "Logger",
            "x": 120.0,
            "y": 140.0,
            "width": 210.0,
            "height": 88.0,
            "accent": "#2F89FF",
            "collapsed": False,
            "selected": False,
            "can_enter_scope": False,
            "surface_family": "standard",
            "surface_variant": "",
            "ports": [
                {
                    "key": "path",
                    "label": "Primary Input Payload",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "path",
                    "connected": False,
                    "inactive": True,
                    "inactive_reason": "Driven by result_file",
                },
                {
                    "key": "result",
                    "label": "Dispatch Result Token",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "any",
                    "connected": False,
                },
            ],
            "inline_properties": [],
            "surface_metrics": {
                "default_width": 210.0,
                "default_height": 88.0,
                "min_width": 120.0,
                "min_height": 50.0,
                "collapsed_width": 130.0,
                "collapsed_height": 36.0,
                "header_height": 24.0,
                "header_top_margin": 4.0,
                "body_top": 30.0,
                "body_height": 30.0,
                "port_top": 60.0,
                "port_height": 18.0,
                "port_center_offset": 6.0,
                "port_side_margin": 8.0,
                "port_dot_radius": 3.5,
                "resize_handle_size": 16.0,
            },
        }

        class TooltipPreferenceBridge(QObject):
            graphics_preferences_changed = pyqtSignal()

            def __init__(self) -> None:
                super().__init__()
                self._graphics_show_grid = True
                self._graphics_grid_style = "lines"
                self._graphics_show_minimap = True
                self._graphics_minimap_expanded = True
                self._graphics_show_port_labels = False
                self._graphics_tooltip_categories = default_tooltip_category_preferences()
                self._graphics_node_shadow = True
                self._graphics_shadow_strength = 70
                self._graphics_shadow_softness = 50
                self._graphics_shadow_offset = 4
            @property
            def graphics_show_grid(self) -> bool:
                return bool(self._graphics_show_grid)

            @property
            def graphics_grid_style(self) -> str:
                return str(self._graphics_grid_style)

            @property
            def graphics_show_minimap(self) -> bool:
                return bool(self._graphics_show_minimap)

            @property
            def graphics_minimap_expanded(self) -> bool:
                return bool(self._graphics_minimap_expanded)

            @property
            def graphics_show_port_labels(self) -> bool:
                return bool(self._graphics_show_port_labels)

            @property
            def graphics_show_tooltips(self) -> bool:
                return bool(self._graphics_tooltip_categories["general"])

            @property
            def graphics_tooltip_categories(self) -> dict[str, bool]:
                return dict(self._graphics_tooltip_categories)

            @property
            def graphics_tooltip_category_visibility(self) -> dict[str, bool]:
                return {
                    category: tooltip_category_effectively_visible(
                        category,
                        tooltip_categories=self._graphics_tooltip_categories,
                    )
                    for category in TOOLTIP_CATEGORY_NAMES
                }

            def tooltip_category_enabled(self, category: str) -> bool:
                return tooltip_category_effectively_visible(
                    category,
                    tooltip_categories=self._graphics_tooltip_categories,
                )

            @property
            def graphics_node_shadow(self) -> bool:
                return bool(self._graphics_node_shadow)

            @property
            def graphics_shadow_strength(self) -> int:
                return int(self._graphics_shadow_strength)

            @property
            def graphics_shadow_softness(self) -> int:
                return int(self._graphics_shadow_softness)

            @property
            def graphics_shadow_offset(self) -> int:
                return int(self._graphics_shadow_offset)

            def set_general_tooltips_value(self, value: bool) -> None:
                normalized = bool(value)
                if self._graphics_tooltip_categories["general"] == normalized:
                    return
                self._graphics_tooltip_categories["general"] = normalized
                self.graphics_preferences_changed.emit()

            def set_graphics_tooltip_category_value(self, category: str, value: bool) -> None:
                if category not in self._graphics_tooltip_categories:
                    return
                normalized = bool(value)
                if self._graphics_tooltip_categories[category] == normalized:
                    return
                self._graphics_tooltip_categories[category] = normalized
                self.graphics_preferences_changed.emit()

        class CanvasStateBridgeStub(QObject):
            graphics_preferences_changed = pyqtSignal()
            scene_nodes_changed = pyqtSignal()
            failure_highlight_changed = pyqtSignal()
            node_execution_state_changed = pyqtSignal()

            def __init__(self, preference_bridge: TooltipPreferenceBridge) -> None:
                super().__init__()
                self._preference_bridge = preference_bridge
                self._nodes_model = [dict(node_payload)]
                self._preference_bridge.graphics_preferences_changed.connect(self.graphics_preferences_changed.emit)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_minimap_expanded(self) -> bool:
                return bool(self._preference_bridge.graphics_minimap_expanded)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_grid(self) -> bool:
                return bool(self._preference_bridge.graphics_show_grid)

            @pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_grid_style(self) -> str:
                return str(self._preference_bridge.graphics_grid_style)

            @pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_edge_crossing_style(self) -> str:
                return "none"

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_minimap(self) -> bool:
                return bool(self._preference_bridge.graphics_show_minimap)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_port_labels(self) -> bool:
                return bool(self._preference_bridge.graphics_show_port_labels)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_tooltips(self) -> bool:
                return bool(self._preference_bridge.graphics_show_tooltips)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_node_shadow(self) -> bool:
                return bool(self._preference_bridge.graphics_node_shadow)

            @pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_strength(self) -> int:
                return int(self._preference_bridge.graphics_shadow_strength)

            @pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_softness(self) -> int:
                return int(self._preference_bridge.graphics_shadow_softness)

            @pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_offset(self) -> int:
                return int(self._preference_bridge.graphics_shadow_offset)

            @pyqtProperty("QVariantList", notify=scene_nodes_changed)
            def nodes_model(self) -> list[dict[str, object]]:
                return list(self._nodes_model)

            @pyqtProperty("QVariantList", constant=True)
            def backdrop_nodes_model(self) -> list[dict[str, object]]:
                return []

            @pyqtProperty("QVariantList", constant=True)
            def edges_model(self) -> list[dict[str, object]]:
                return []

            @pyqtProperty("QVariantMap", constant=True)
            def selected_node_lookup(self) -> dict[str, bool]:
                return {}

            @pyqtProperty("QVariantMap", constant=True)
            def workspace_scene_bounds_payload(self) -> dict[str, float]:
                return {}

            @pyqtProperty("QVariantMap", notify=graphics_preferences_changed)
            def graphics_tooltip_categories(self) -> dict[str, bool]:
                return dict(self._preference_bridge.graphics_tooltip_categories)

            @pyqtProperty("QVariantMap", notify=graphics_preferences_changed)
            def graphics_tooltip_category_visibility(self) -> dict[str, bool]:
                return dict(self._preference_bridge.graphics_tooltip_category_visibility)

            @pyqtProperty("QVariantMap", notify=failure_highlight_changed)
            def failed_node_lookup(self) -> dict[str, bool]:
                return {}

            @pyqtProperty(str, notify=failure_highlight_changed)
            def failed_node_title(self) -> str:
                return ""

            @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def running_node_lookup(self) -> dict[str, bool]:
                return {}

            @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def completed_node_lookup(self) -> dict[str, bool]:
                return {}

            @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def running_node_started_at_ms_lookup(self) -> dict[str, float]:
                return {}

            @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def node_elapsed_ms_lookup(self) -> dict[str, float]:
                return {}

            @pyqtProperty(int, notify=node_execution_state_changed)
            def node_execution_revision(self) -> int:
                return 0

        def item_scene_point(item: QObject) -> QPoint:
            scene_point = item.mapToScene(QPointF(item.width() * 0.5, item.height() * 0.5))
            return QPoint(round(scene_point.x()), round(scene_point.y()))

        self.canvas.deleteLater()
        self.app.processEvents()

        preference_bridge = TooltipPreferenceBridge()
        canvas_state_bridge = CanvasStateBridgeStub(preference_bridge)
        canvas_command_bridge = GraphCanvasCommandBridge(
            search_scope_controller=self.canvas_source,  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            run_controller=self.canvas_source,  # type: ignore[arg-type]
            inspector_source=self.canvas_source,  # type: ignore[arg-type]
            library_source=self.canvas_source,  # type: ignore[arg-type]
            workspace_edit_controller=self.canvas_source,  # type: ignore[arg-type]
            workspace_drop_connect_controller=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=preference_bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        self.canvas = self._create_canvas(
            {
                "canvasStateBridge": canvas_state_bridge,
                "canvasCommandBridge": canvas_command_bridge,
                "width": 1280.0,
                "height": 720.0,
            }
        )

        wait_for_condition_or_raise(
            lambda: len(_named_child_items(self.canvas, "graphNodeInputPortMouseArea")) == 1,
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for graph canvas tooltip-policy input port to appear.",
        )
        node_card = _named_child_items(self.canvas, "graphNodeCard")[0]
        input_mouse = _named_child_items(self.canvas, "graphNodeInputPortMouseArea")[0]

        window = QQuickWindow()
        window.resize(1280, 720)
        self.canvas.setParentItem(window.contentItem())
        window.show()
        self.app.processEvents()
        try:
            self.assertTrue(bool(node_card.property("_tooltipOnlyPortLabelsActive")))
            self.assertEqual(input_mouse.property("inactiveTooltipText"), "Driven by result_file")
            QTest.mouseMove(window, item_scene_point(input_mouse))
            wait_for_condition_or_raise(
                lambda: bool(input_mouse.property("containsMouse")),
                timeout_ms=300,
                app=self.app,
                timeout_message="Timed out waiting for graph canvas tooltip-policy hover state.",
            )

            self.assertTrue(bool(input_mouse.property("infoTooltipsEnabled")))
            self.assertTrue(bool(input_mouse.property("tooltipVisible")))
            self.assertTrue(bool(input_mouse.property("inactiveTooltipVisible")))

            preference_bridge.set_general_tooltips_value(False)
            wait_for_condition_or_raise(
                lambda: not bool(input_mouse.property("infoTooltipsEnabled")),
                timeout_ms=300,
                app=self.app,
                timeout_message="Timed out waiting for graph canvas tooltip policy update to reach port hover state.",
            )

            self.assertFalse(bool(input_mouse.property("tooltipVisible")))
            self.assertTrue(bool(input_mouse.property("inactiveTooltipVisible")))

            preference_bridge.set_graphics_tooltip_category_value("inactive", False)
            wait_for_condition_or_raise(
                lambda: not bool(input_mouse.property("inactiveTooltipsEnabled")),
                timeout_ms=300,
                app=self.app,
                timeout_message="Timed out waiting for inactive tooltip category policy update.",
            )

            self.assertFalse(bool(input_mouse.property("inactiveTooltipVisible")))
        finally:
            window.close()
            self.app.processEvents()

    def test_node_execution_visualization_graph_canvas_host_chrome_follows_bridge_state_priority(self) -> None:
        node_id = "node_execution_visualization"
        node_payload = {
            "node_id": node_id,
            "type_id": "core.logger",
            "title": "Logger",
            "x": 120.0,
            "y": 140.0,
            "width": 210.0,
            "height": 88.0,
            "accent": "#2F89FF",
            "collapsed": False,
            "selected": False,
            "can_enter_scope": False,
            "surface_family": "standard",
            "surface_variant": "",
            "ports": [
                {
                    "key": "payload",
                    "label": "Payload",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "any",
                    "connected": False,
                    "flow_state": "waiting",
                },
                {
                    "key": "result",
                    "label": "Result",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "any",
                    "connected": False,
                    "flow_state": "flowing",
                },
            ],
            "inline_properties": [],
            "surface_metrics": {
                "default_width": 210.0,
                "default_height": 88.0,
                "min_width": 120.0,
                "min_height": 50.0,
                "collapsed_width": 130.0,
                "collapsed_height": 36.0,
                "header_height": 24.0,
                "header_top_margin": 4.0,
                "body_top": 30.0,
                "body_height": 30.0,
                "port_top": 60.0,
                "port_height": 18.0,
                "port_center_offset": 6.0,
                "port_side_margin": 8.0,
                "port_dot_radius": 3.5,
                "resize_handle_size": 16.0,
            },
        }

        class CanvasStateBridgeStub(QObject):
            graphics_preferences_changed = pyqtSignal()
            scene_nodes_changed = pyqtSignal()
            failure_highlight_changed = pyqtSignal()
            node_execution_state_changed = pyqtSignal()
            selection_state_changed = pyqtSignal()

            def __init__(
                self,
                preference_bridge: _GraphCanvasPreferenceBridge,
                canvas_source: object,
                view_bridge: ViewportBridge,
            ) -> None:
                super().__init__()
                self._preference_bridge = preference_bridge
                self._canvas_source = canvas_source
                self._view_bridge = view_bridge
                self._nodes_model = [dict(node_payload)]
                self._running_node_lookup: dict[str, bool] = {}
                self._running_node_started_at_ms_lookup: dict[str, float] = {}
                self._completed_node_lookup: dict[str, bool] = {}
                self._fresh_run_node_lookup: dict[str, bool] = {}
                self._node_elapsed_ms_lookup: dict[str, float] = {}
                self._failed_node_lookup: dict[str, bool] = {}
                self._warning_node_lookup: dict[str, bool] = {}
                self._selected_node_lookup: dict[str, bool] = {}
                self._node_execution_revision = 0
                self._preference_bridge.graphics_preferences_changed.connect(self.graphics_preferences_changed.emit)

            @pyqtProperty(QObject, constant=True)
            def viewport_bridge(self) -> ViewportBridge:
                return self._view_bridge

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_minimap_expanded(self) -> bool:
                return bool(self._canvas_source.graphics_minimap_expanded)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_grid(self) -> bool:
                return bool(self._preference_bridge.graphics_show_grid)

            @pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_grid_style(self) -> str:
                return str(self._preference_bridge.graphics_grid_style)

            @pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_edge_crossing_style(self) -> str:
                return str(self._preference_bridge.graphics_edge_crossing_style)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_minimap(self) -> bool:
                return bool(self._preference_bridge.graphics_show_minimap)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_port_labels(self) -> bool:
                return bool(self._preference_bridge.graphics_show_port_labels)

            @pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_node_shadow(self) -> bool:
                return True

            @pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_strength(self) -> int:
                return 70

            @pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_softness(self) -> int:
                return 50

            @pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_offset(self) -> int:
                return 4

            @pyqtProperty("QVariantList", notify=scene_nodes_changed)
            def nodes_model(self) -> list[dict[str, object]]:
                return list(self._nodes_model)

            @pyqtProperty("QVariantList", constant=True)
            def backdrop_nodes_model(self) -> list[dict[str, object]]:
                return []

            @pyqtProperty("QVariantList", constant=True)
            def edges_model(self) -> list[dict[str, object]]:
                return []

            @pyqtProperty("QVariantMap", notify=selection_state_changed)
            def selected_node_lookup(self) -> dict[str, bool]:
                return dict(self._selected_node_lookup)

            @pyqtProperty("QVariantMap", constant=True)
            def workspace_scene_bounds_payload(self) -> dict[str, float]:
                return {}

            @pyqtProperty("QVariantMap", notify=failure_highlight_changed)
            def failed_node_lookup(self) -> dict[str, bool]:
                return dict(self._failed_node_lookup)

            @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def warning_node_lookup(self) -> dict[str, bool]:
                return dict(self._warning_node_lookup)

            @pyqtProperty(str, notify=failure_highlight_changed)
            def failed_node_title(self) -> str:
                return "Logger" if self._failed_node_lookup else ""

            @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def running_node_lookup(self) -> dict[str, bool]:
                return dict(self._running_node_lookup)

            @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def completed_node_lookup(self) -> dict[str, bool]:
                return dict(self._completed_node_lookup)

            @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def running_node_started_at_ms_lookup(self) -> dict[str, float]:
                return dict(self._running_node_started_at_ms_lookup)

            @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def node_elapsed_ms_lookup(self) -> dict[str, float]:
                return dict(self._node_elapsed_ms_lookup)

            @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def fresh_run_node_lookup(self) -> dict[str, bool]:
                return dict(self._fresh_run_node_lookup)

            @pyqtProperty(int, notify=node_execution_state_changed)
            def node_execution_revision(self) -> int:
                return int(self._node_execution_revision)

            def set_running_node_state(self, tracked_node_id: str) -> None:
                self._running_node_lookup = {str(tracked_node_id): True}
                self._running_node_started_at_ms_lookup = {str(tracked_node_id): 1000.0}
                self._completed_node_lookup = {}
                self._node_execution_revision += 1
                self.node_execution_state_changed.emit()

            def set_completed_node_state(self, tracked_node_id: str) -> None:
                self._running_node_lookup = {}
                self._running_node_started_at_ms_lookup = {}
                self._completed_node_lookup = {str(tracked_node_id): True}
                self._fresh_run_node_lookup = {str(tracked_node_id): True}
                self._node_execution_revision += 1
                self.node_execution_state_changed.emit()

            def set_fresh_run_node_state(self, tracked_node_id: str) -> None:
                self._running_node_lookup = {}
                self._running_node_started_at_ms_lookup = {}
                self._completed_node_lookup = {}
                self._fresh_run_node_lookup = {str(tracked_node_id): True}
                self._node_execution_revision += 1
                self.node_execution_state_changed.emit()

            def set_failed_node_state(self, tracked_node_id: str) -> None:
                self._failed_node_lookup = {str(tracked_node_id): True}
                self.failure_highlight_changed.emit()

            def set_warning_node_state(self, tracked_node_id: str) -> None:
                self._warning_node_lookup = {str(tracked_node_id): True}
                self.node_execution_state_changed.emit()

            def set_selected_node_state(self, tracked_node_id: str) -> None:
                self._selected_node_lookup = {str(tracked_node_id): True}
                self.selection_state_changed.emit()

            def clear_selected_node_state(self) -> None:
                self._selected_node_lookup = {}
                self.selection_state_changed.emit()

        self.canvas.deleteLater()
        self.app.processEvents()

        canvas_state_bridge = CanvasStateBridgeStub(
            self.bridge,
            self.canvas_source,
            self.view,
        )
        canvas_command_bridge = GraphCanvasCommandBridge(
            search_scope_controller=self.canvas_source,  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            run_controller=self.canvas_source,  # type: ignore[arg-type]
            inspector_source=self.canvas_source,  # type: ignore[arg-type]
            library_source=self.canvas_source,  # type: ignore[arg-type]
            workspace_edit_controller=self.canvas_source,  # type: ignore[arg-type]
            workspace_drop_connect_controller=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=self.bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        self.canvas = self._create_canvas(
            {
                "canvasStateBridge": canvas_state_bridge,
                "canvasCommandBridge": canvas_command_bridge,
                "canvasLifecycleBridge": canvas_state_bridge,
                "width": 1280.0,
                "height": 720.0,
            }
        )

        wait_for_condition_or_raise(
            lambda: len(_named_child_items(self.canvas, "graphNodeCard")) == 1,
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for graph canvas execution-visualization node host to appear.",
        )
        node_card = _named_child_items(self.canvas, "graphNodeCard")[0]
        background_layer = node_card.findChild(QObject, "graphNodeChromeBackgroundLayer")
        selected_halo = node_card.findChild(QObject, "graphNodeSelectedHalo")
        elapsed_timer = node_card.findChild(QObject, "graphNodeElapsedTimer")
        failure_badge = node_card.findChild(QObject, "graphNodeFailureBadge")
        input_port_dot = node_card.findChild(QObject, "graphNodeInputPortDot")
        output_port_dot = node_card.findChild(QObject, "graphNodeOutputPortDot")
        self.assertIsNotNone(background_layer)
        self.assertIsNotNone(selected_halo)
        self.assertIsNotNone(elapsed_timer)
        self.assertIsNotNone(failure_badge)
        self.assertIsNotNone(input_port_dot)
        self.assertIsNotNone(output_port_dot)
        for removed_name in (
            "graphNodeFailureHalo",
            "graphNodeFailurePulseHalo",
            "graphNodeRunningHalo",
            "graphNodeRunningPulseHalo",
            "graphNodeCompletedFlashHalo",
            "graphNodeSelectedRunPreviewHalo",
            "graphNodeRunFreshHalo",
        ):
            self.assertIsNone(node_card.findChild(QObject, removed_name))

        self.assertEqual(str(background_layer.property("effectiveBorderState")), "idle")
        self.assertEqual(_color_name(node_card.property("surfaceColor")), _color_name("#403C2D"))
        self.assertEqual(_color_name(node_card.property("bodyGradientEndColor")), _color_name("#3A372A"))
        self.assertEqual(_color_name(node_card.property("outlineColor")), _color_name("#81795C"))
        self.assertEqual(_color_name(node_card.property("headerTextColor")), _color_name("#F3F3F1"))
        self.assertEqual(_color_name(node_card.property("portLabelColor")), _color_name("#D7D5CE"))
        self.assertEqual(dict(self.canvas.property("runningNodeLookup")), {})
        self.assertEqual(dict(self.canvas.property("completedNodeLookup")), {})
        self.assertFalse(bool(elapsed_timer.property("visible")))
        input_port_fill = _color_name(input_port_dot.property("color"))
        output_port_fill = _color_name(output_port_dot.property("color"))
        self.assertEqual(input_port_fill, _color_name(node_card.property("themeSurfaceColor")))
        self.assertEqual(output_port_fill, _color_name("#67D487"))

        idle_key = str(background_layer.property("cacheKey") or "")

        # Active selection is a fixed blue body and outline, with no aura.
        self.assertFalse(bool(selected_halo.property("visible")))
        canvas_state_bridge.set_selected_node_state(node_id)
        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isSelected"))
            and str(background_layer.property("effectiveBorderState")) == "selected",
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for fixed selected chrome on graph canvas host.",
        )
        self.assertFalse(bool(selected_halo.property("visible")))
        self.assertEqual(_color_name(node_card.property("surfaceColor")), _color_name("#1F5369"))
        self.assertEqual(_color_name(node_card.property("bodyGradientEndColor")), _color_name("#1A485B"))
        self.assertEqual(_color_name(background_layer.property("effectiveOutlineColor")), _color_name("#00A5E4"))
        self.assertEqual(_color_name(input_port_dot.property("color")), input_port_fill)
        self.assertEqual(_color_name(output_port_dot.property("color")), output_port_fill)

        canvas_state_bridge.clear_selected_node_state()
        wait_for_condition_or_raise(
            lambda: not bool(node_card.property("isSelected"))
            and str(background_layer.property("effectiveBorderState")) == "idle",
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for active node selection to clear.",
        )

        canvas_state_bridge.set_running_node_state(node_id)
        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isRunningNode"))
            and str(background_layer.property("effectiveBorderState")) == "idle"
            and bool(elapsed_timer.property("visible")),
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for neutral running chrome on graph canvas host.",
        )

        self.assertTrue(bool(node_card.property("renderActive")))
        self.assertEqual(int(node_card.property("z")), 31)
        self.assertEqual(dict(self.canvas.property("runningNodeLookup")), {node_id: True})
        self.assertEqual(
            _color_name(background_layer.property("effectiveOutlineColor")),
            _color_name("#81795C"),
        )
        self.assertEqual(_color_name(node_card.property("surfaceColor")), _color_name("#403C2D"))
        self.assertFalse(bool(selected_halo.property("visible")))

        running_key = str(background_layer.property("cacheKey") or "")
        self.assertEqual(running_key, idle_key)

        wait_for_condition_or_raise(
            lambda: str(elapsed_timer.property("text") or "") != "0.0s",
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for graph canvas elapsed timer to advance.",
        )

        canvas_state_bridge.set_completed_node_state(node_id)
        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isCompletedNode"))
            and not bool(node_card.property("isRunningNode"))
            and str(background_layer.property("effectiveBorderState")) == "idle"
            and not bool(elapsed_timer.property("visible")),
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for neutral completed chrome on graph canvas host.",
        )

        self.assertEqual(int(node_card.property("z")), 30)
        self.assertEqual(dict(self.canvas.property("runningNodeLookup")), {})
        self.assertEqual(dict(self.canvas.property("completedNodeLookup")), {node_id: True})
        self.assertEqual(dict(self.canvas.property("freshRunNodeLookup")), {node_id: True})
        self.assertEqual(
            _color_name(background_layer.property("effectiveOutlineColor")),
            _color_name("#81795C"),
        )
        self.assertEqual(_color_name(node_card.property("surfaceColor")), _color_name("#403C2D"))

        completed_key = str(background_layer.property("cacheKey") or "")
        self.assertEqual(completed_key, running_key)

        canvas_state_bridge.set_fresh_run_node_state(node_id)
        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isFreshRunNode"))
            and not bool(node_card.property("isCompletedNode"))
            and str(background_layer.property("effectiveBorderState")) == "idle",
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for neutral fresh-run chrome on graph canvas host.",
        )
        self.assertEqual(int(node_card.property("z")), 29)
        self.assertEqual(dict(self.canvas.property("completedNodeLookup")), {})
        self.assertEqual(dict(self.canvas.property("freshRunNodeLookup")), {node_id: True})
        self.assertEqual(
            _color_name(background_layer.property("effectiveOutlineColor")),
            _color_name("#81795C"),
        )
        fresh_key = str(background_layer.property("cacheKey") or "")
        self.assertEqual(fresh_key, completed_key)

        canvas_state_bridge.set_warning_node_state(node_id)
        wait_for_condition_or_raise(
            lambda: str(background_layer.property("effectiveBorderState")) == "warning",
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for warning chrome on graph canvas host.",
        )
        self.assertEqual(_color_name(input_port_dot.property("color")), input_port_fill)
        self.assertEqual(_color_name(output_port_dot.property("color")), output_port_fill)

        canvas_state_bridge.set_failed_node_state(node_id)
        wait_for_condition_or_raise(
            lambda: str(background_layer.property("effectiveBorderState")) == "failed",
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for failure priority to override execution chrome.",
        )

        self.assertEqual(dict(self.canvas.property("failedNodeLookup")), {node_id: True})
        self.assertEqual(
            _color_name(background_layer.property("effectiveOutlineColor")),
            _color_name("#E36155"),
        )
        self.assertEqual(_color_name(node_card.property("surfaceColor")), _color_name("#5D2F30"))
        self.assertEqual(_color_name(node_card.property("bodyGradientEndColor")), _color_name("#51292A"))
        self.assertTrue(bool(failure_badge.property("visible")))
        self.assertIn("|error|", str(background_layer.property("cacheKey") or ""))
        self.assertEqual(_color_name(input_port_dot.property("color")), input_port_fill)
        self.assertEqual(_color_name(output_port_dot.property("color")), output_port_fill)

        canvas_state_bridge.set_selected_node_state(node_id)
        wait_for_condition_or_raise(
            lambda: str(background_layer.property("effectiveBorderState")) == "selected",
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for selected state to override error chrome.",
        )
        self.assertEqual(_color_name(node_card.property("surfaceColor")), _color_name("#1F5369"))
        self.assertEqual(_color_name(background_layer.property("effectiveOutlineColor")), _color_name("#00A5E4"))
        self.assertTrue(bool(failure_badge.property("visible")))
        self.assertFalse(bool(selected_halo.property("visible")))
        self.assertEqual(_color_name(input_port_dot.property("color")), input_port_fill)
        self.assertEqual(_color_name(output_port_dot.property("color")), output_port_fill)

    def test_toggle_minimap_expanded_routes_through_bridge_slot(self) -> None:
        self.assertEqual(self.canvas_source.minimap_update_history, [])
        self.assertTrue(bool(self.canvas.property("minimapExpanded")))

        QMetaObject.invokeMethod(
            self.canvas,
            "toggleMinimapExpanded",
            Qt.ConnectionType.DirectConnection,
        )
        self.app.processEvents()

        self.assertEqual(self.canvas_source.minimap_update_history, [False])
        self.assertFalse(self.canvas_source.graphics_minimap_expanded)
        self.assertFalse(bool(self.canvas.property("minimapExpanded")))

    def test_canvas_qml_theme_surfaces_follow_runtime_theme_changes(self) -> None:
        background = self.canvas.findChild(QObject, "graphCanvasBackground")
        shader_renderer = self.canvas.findChild(QObject, "graphCanvasGridShaderRenderer")
        minimap_overlay = self.canvas.findChild(QObject, "graphCanvasMinimapOverlay")
        minimap_toggle = self.canvas.findChild(QObject, "graphCanvasMinimapToggle")
        minimap_viewport_rect = self.canvas.findChild(QObject, "graphCanvasMinimapViewportRect")
        drop_preview = self.canvas.findChild(QObject, "graphCanvasDropPreview")
        edge_layer = self.canvas.findChild(QObject, "graphCanvasEdgeLayer")
        marquee_rect = self.canvas.findChild(QObject, "graphCanvasMarqueeRect")

        self.assertIsNotNone(background)
        self.assertIsNotNone(shader_renderer)
        self.assertIsNotNone(minimap_overlay)
        self.assertIsNotNone(minimap_toggle)
        self.assertIsNotNone(minimap_viewport_rect)
        self.assertIsNotNone(drop_preview)
        self.assertIsNotNone(edge_layer)
        self.assertIsNotNone(marquee_rect)

        self.assertEqual(_color_name(background.property("backgroundFillColor")), STITCH_DARK_V1.canvas_bg)
        self.assertEqual(_color_name(background.property("minorGridColor")), STITCH_DARK_V1.canvas_minor_grid)
        self.assertEqual(_color_name(shader_renderer.property("minorGridColor")), STITCH_DARK_V1.canvas_minor_grid)
        self.assertEqual(_color_name(shader_renderer.property("majorGridColor")), STITCH_DARK_V1.canvas_major_grid)
        self.assertEqual(
            _color_name(minimap_overlay.property("color"), include_alpha=True),
            _alpha_color_name(STITCH_DARK_V1.panel_bg, 0.64),
        )
        self.assertEqual(_color_name(minimap_toggle.property("color")), STITCH_DARK_V1.toolbar_bg)
        self.assertEqual(
            _color_name(minimap_viewport_rect.property("color"), include_alpha=True),
            _alpha_color_name(STITCH_DARK_V1.accent, 0.18),
        )
        self.assertEqual(
            _color_name(drop_preview.property("color"), include_alpha=True),
            _alpha_color_name(STITCH_DARK_V1.panel_bg, 0.66),
        )
        self.assertEqual(
            _color_name(edge_layer.property("selectedStrokeColor")),
            self.graph_theme_bridge.edge_palette["selected_stroke"],
        )
        self.assertEqual(
            _color_name(edge_layer.property("invalidDragStrokeColor")),
            self.graph_theme_bridge.edge_palette["invalid_drag_stroke"],
        )
        self.assertEqual(_color_name(edge_layer.property("flowDefaultStrokeColor")), STITCH_DARK_V1.muted_fg)
        self.assertEqual(_color_name(edge_layer.property("flowDefaultLabelTextColor")), STITCH_DARK_V1.panel_title_fg)
        self.assertEqual(
            _color_name(edge_layer.property("flowDefaultLabelBackgroundColor")),
            STITCH_DARK_V1.panel_bg,
        )
        self.assertEqual(
            _color_name(marquee_rect.property("color"), include_alpha=True),
            _alpha_color_name(STITCH_DARK_V1.accent, 0.2),
        )

        self.theme_bridge.apply_theme("stitch_light")
        self.graph_theme_bridge.apply_theme("graph_stitch_light")
        self.app.processEvents()

        self.assertEqual(_color_name(background.property("backgroundFillColor")), STITCH_LIGHT_V1.canvas_bg)
        self.assertEqual(_color_name(background.property("minorGridColor")), STITCH_LIGHT_V1.canvas_minor_grid)
        self.assertEqual(_color_name(shader_renderer.property("minorGridColor")), STITCH_LIGHT_V1.canvas_minor_grid)
        self.assertEqual(_color_name(shader_renderer.property("majorGridColor")), STITCH_LIGHT_V1.canvas_major_grid)
        self.assertEqual(
            _color_name(minimap_overlay.property("color"), include_alpha=True),
            _alpha_color_name(STITCH_LIGHT_V1.panel_bg, 0.64),
        )
        self.assertEqual(_color_name(minimap_toggle.property("color")), STITCH_LIGHT_V1.toolbar_bg)
        self.assertEqual(
            _color_name(minimap_viewport_rect.property("color"), include_alpha=True),
            _alpha_color_name(STITCH_LIGHT_V1.accent, 0.18),
        )
        self.assertEqual(
            _color_name(drop_preview.property("color"), include_alpha=True),
            _alpha_color_name(STITCH_LIGHT_V1.panel_bg, 0.66),
        )
        self.assertEqual(
            _color_name(edge_layer.property("selectedStrokeColor")),
            self.graph_theme_bridge.edge_palette["selected_stroke"],
        )
        self.assertEqual(
            _color_name(edge_layer.property("invalidDragStrokeColor")),
            self.graph_theme_bridge.edge_palette["invalid_drag_stroke"],
        )
        self.assertEqual(_color_name(edge_layer.property("flowDefaultStrokeColor")), STITCH_LIGHT_V1.muted_fg)
        self.assertEqual(_color_name(edge_layer.property("flowDefaultLabelTextColor")), STITCH_LIGHT_V1.panel_title_fg)
        self.assertEqual(
            _color_name(edge_layer.property("flowDefaultLabelBackgroundColor")),
            STITCH_LIGHT_V1.panel_bg,
        )
        self.assertEqual(
            _color_name(marquee_rect.property("color"), include_alpha=True),
            _alpha_color_name(STITCH_LIGHT_V1.accent, 0.2),
        )

        background.setProperty("canvasBackgroundVariant", "white")
        self.app.processEvents()

        self.assertEqual(_color_name(background.property("backgroundFillColor")), "#ffffff")
        self.assertEqual(_color_name(background.property("minorGridColor")), STITCH_LIGHT_V1.canvas_minor_grid)
        self.assertEqual(_color_name(shader_renderer.property("minorGridColor")), STITCH_LIGHT_V1.canvas_minor_grid)
        self.assertEqual(_color_name(shader_renderer.property("majorGridColor")), STITCH_LIGHT_V1.canvas_major_grid)

    def test_graph_canvas_world_stacks_above_edge_layer(self) -> None:
        edge_layer = self.canvas.findChild(QObject, "graphCanvasEdgeLayer")
        world = self.canvas.findChild(QObject, "graphCanvasWorld")

        self.assertIsNotNone(edge_layer)
        self.assertIsNotNone(world)
        parent_item = world.parentItem()
        self.assertIsNotNone(parent_item)
        self.assertIs(parent_item, edge_layer.parentItem())
        sibling_items = list(parent_item.childItems())
        self.assertIn(edge_layer, sibling_items)
        self.assertIn(world, sibling_items)
        self.assertLess(sibling_items.index(edge_layer), sibling_items.index(world))

    def test_production_canvas_settings_group_click_routes_through_command_facade(self) -> None:
        from PyQt6.QtCore import QPointF

        from ea_node_editor.persistence.serializer import JsonProjectSerializer

        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        scene = GraphSceneBridge()
        scene.bind_graphics_preferences_source(self.bridge)
        scene.set_workspace(model, registry, workspace.workspace_id)
        node_id = scene.add_node_from_type("plot.signal", 120.0, 120.0)
        node = workspace.nodes[node_id]
        refresh_events: list[str] = []
        scene.nodes_changed.connect(lambda: refresh_events.append("nodes"))

        self.canvas.deleteLater()
        self.app.processEvents()
        state_bridge = GraphCanvasStateBridge(
            session_state=self.canvas_source,  # type: ignore[arg-type]
            snap_to_grid_changed_signal=getattr(self.canvas_source, "snap_to_grid_changed", None),  # type: ignore[arg-type]
            snap_grid_size=float(getattr(self.canvas_source, "snap_grid_size", 20.0)),  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=self.bridge,  # type: ignore[arg-type]
            scene_bridge=scene,
            view_bridge=self.view,
        )
        command_bridge = GraphCanvasCommandBridge(
            search_scope_controller=self.canvas_source,  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            run_controller=self.canvas_source,  # type: ignore[arg-type]
            inspector_source=self.canvas_source,  # type: ignore[arg-type]
            library_source=self.canvas_source,  # type: ignore[arg-type]
            workspace_edit_controller=self.canvas_source,  # type: ignore[arg-type]
            workspace_drop_connect_controller=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=self.bridge,  # type: ignore[arg-type]
            scene_bridge=scene,
            view_bridge=self.view,
        )
        self.canvas = self._create_canvas(
            {
                "canvasStateBridge": state_bridge,
                "canvasCommandBridge": command_bridge,
                "canvasLifecycleBridge": state_bridge,
                "width": 1280.0,
                "height": 900.0,
            }
        )
        wait_for_condition_or_raise(
            lambda: len(_named_child_items(self.canvas, "graphNodeSettingsGroupHeader")) == 2,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for production Signal Plot settings headers.",
        )
        node_card = _named_child_items(self.canvas, "graphNodeCard")[0]
        baseline_height = float(node_card.height())

        def header(group_id: str) -> QObject:
            return next(
                item
                for item in _named_child_items(self.canvas, "graphNodeSettingsGroupHeader")
                if str(item.property("groupId")) == group_id
            )

        def click(item: QObject, window: QQuickWindow) -> None:
            point = item.mapToScene(
                QPointF(float(item.width()) * 0.5, float(item.height()) * 0.5)
            )
            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                point.toPoint(),
            )
            self.app.processEvents()

        window = QQuickWindow()
        window.resize(1280, 900)
        self.canvas.setParentItem(window.contentItem())
        window.show()
        self.app.processEvents()
        try:
            click(header("general_options"), window)
            self.assertEqual(node.expanded_settings_group_ids, ("general_options",))
            self.assertTrue(bool(node_card.property("settingsGroupAnimationRunning")))
            self.assertGreaterEqual(len(refresh_events), 1)
            expanded_payload = next(
                item for item in scene.nodes_model if item["node_id"] == node_id
            )
            general_payload = next(
                group
                for group in expanded_payload["settings_groups"]
                if group["group_id"] == "general_options"
            )
            self.assertTrue(general_payload["expanded"])
            self.assertGreater(float(expanded_payload["height"]), baseline_height)
            persisted = JsonProjectSerializer(registry).to_persistent_document(model.project)
            persisted_node = next(
                item
                for item in persisted["workspaces"][0]["nodes"]
                if item["node_id"] == node_id
            )
            self.assertEqual(
                persisted_node["expanded_settings_group_ids"],
                ["general_options"],
            )

            QTest.qWait(60)
            self.app.processEvents()
            intermediate_height = float(node_card.height())
            self.assertGreater(intermediate_height, baseline_height)
            self.assertLess(intermediate_height, float(expanded_payload["height"]))
            wait_for_condition_or_raise(
                lambda: not bool(node_card.property("settingsGroupAnimationRunning")),
                timeout_ms=400,
                app=self.app,
                timeout_message="Timed out waiting for production settings expansion animation.",
            )
            self.assertAlmostEqual(
                float(node_card.height()),
                float(expanded_payload["height"]),
                delta=0.75,
            )

            click(header("general_options"), window)
            self.assertEqual(node.expanded_settings_group_ids, ())
            self.assertTrue(bool(node_card.property("settingsGroupAnimationRunning")))
            wait_for_condition_or_raise(
                lambda: not bool(node_card.property("settingsGroupAnimationRunning")),
                timeout_ms=400,
                app=self.app,
                timeout_message="Timed out waiting for production settings collapse animation.",
            )
            collapsed_payload = next(
                item for item in scene.nodes_model if item["node_id"] == node_id
            )
            self.assertFalse(
                next(
                    group
                    for group in collapsed_payload["settings_groups"]
                    if group["group_id"] == "general_options"
                )["expanded"]
            )
            self.assertAlmostEqual(float(node_card.height()), baseline_height, delta=0.75)
            self.assertGreaterEqual(len(refresh_events), 2)
        finally:
            window.close()
            self.app.processEvents()

    def test_graph_canvas_live_resize_geometry_propagates_to_edge_layer(self) -> None:
        edge_layer = self.canvas.findChild(QObject, "graphCanvasEdgeLayer")
        self.assertIsNotNone(edge_layer)

        payload = {"node_resize_test": {"x": 180.0, "y": 120.0, "width": 260.0, "height": 144.0}}
        self.canvas.setProperty("liveNodeGeometry", payload)
        self.app.processEvents()

        self.assertEqual(self.canvas.property("liveNodeGeometry"), payload)
        self.assertEqual(edge_layer.property("liveNodeGeometry"), payload)

    def test_edge_layer_applies_live_drag_offsets_to_recomputed_node_port_geometry(self) -> None:
        edge_layer = self._create_edge_layer()

        surface_metrics = {
            "default_width": 210.0,
            "default_height": 88.0,
            "min_width": 120.0,
            "min_height": 50.0,
            "collapsed_width": 130.0,
            "collapsed_height": 36.0,
            "header_height": 24.0,
            "header_top_margin": 4.0,
            "body_top": 30.0,
            "body_height": 30.0,
            "port_top": 60.0,
            "port_height": 18.0,
            "port_center_offset": 6.0,
            "port_side_margin": 8.0,
            "port_dot_radius": 3.5,
            "resize_handle_size": 16.0,
        }
        nodes = [
            {
                "node_id": "source",
                "type_id": "core.logger",
                "title": "Source",
                "x": 100.0,
                "y": 100.0,
                "width": 210.0,
                "height": 88.0,
                "surface_family": "standard",
                "surface_variant": "",
                "collapsed": False,
                "ports": [
                    {
                        "key": "out",
                        "label": "Out",
                        "direction": "out",
                        "kind": "data",
                        "data_type": "str",
                        "connected": False,
                        "side": "right",
                    }
                ],
                "surface_metrics": surface_metrics,
            },
            {
                "node_id": "target",
                "type_id": "core.logger",
                "title": "Target",
                "x": 400.0,
                "y": 100.0,
                "width": 210.0,
                "height": 88.0,
                "surface_family": "standard",
                "surface_variant": "",
                "collapsed": False,
                "ports": [
                    {
                        "key": "in",
                        "label": "In",
                        "direction": "in",
                        "kind": "data",
                        "data_type": "str",
                        "connected": False,
                        "side": "left",
                    }
                ],
                "surface_metrics": surface_metrics,
            },
        ]
        edge_payload = {
            "edge_id": "edge_drag_offset_test",
            "source_node_id": "source",
            "source_port_key": "out",
            "target_node_id": "target",
            "target_port_key": "in",
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
            "source_anchor_kind": "node",
            "target_anchor_kind": "node",
            "source_anchor_node_id": "source",
            "target_anchor_node_id": "target",
            "source_hidden_by_backdrop_id": "",
            "target_hidden_by_backdrop_id": "",
            "source_anchor_bounds": {"x": 100.0, "y": 100.0, "width": 210.0, "height": 88.0},
            "target_anchor_bounds": {"x": 400.0, "y": 100.0, "width": 210.0, "height": 88.0},
            "lane_bias": 0.0,
            "sx": 310.0,
            "sy": 144.0,
            "tx": 400.0,
            "ty": 144.0,
            "c1x": 366.0,
            "c1y": 144.0,
            "c2x": 344.0,
            "c2y": 144.0,
            "route": "bezier",
            "pipe_points": [],
            "color": "#7AA8FF",
            "data_type_warning": False,
        }

        edge_layer.setProperty("nodes", nodes)
        edge_layer.setProperty("edges", [edge_payload])
        self.app.processEvents()
        edge_layer.requestRedraw()
        self.app.processEvents()

        baseline_snapshot = edge_layer._visibleEdgeSnapshot("edge_drag_offset_test").toVariant()
        baseline_geometry = dict(baseline_snapshot["geometry"])
        baseline_redraws = int(edge_layer.property("_redrawRequestCount"))

        edge_layer.setProperty("dragNodeLookup", {"source": True})
        edge_layer.setProperty("dragDx", 40.0)
        edge_layer.setProperty("dragDy", 20.0)
        edge_layer.setProperty("dragRevision", 1)
        wait_for_condition_or_raise(
            lambda: int(edge_layer.property("_redrawRequestCount")) > baseline_redraws,
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for edge-layer drag offset redraw.",
        )

        offset_snapshot = edge_layer._visibleEdgeSnapshot("edge_drag_offset_test").toVariant()
        offset_geometry = dict(offset_snapshot["geometry"])
        self.assertAlmostEqual(offset_geometry["sx"], baseline_geometry["sx"] + 40.0, places=6)
        self.assertAlmostEqual(offset_geometry["sy"], baseline_geometry["sy"] + 20.0, places=6)
        self.assertAlmostEqual(offset_geometry["c1x"], baseline_geometry["c1x"] + 40.0, places=6)
        self.assertAlmostEqual(offset_geometry["c1y"], baseline_geometry["c1y"] + 20.0, places=6)
        self.assertAlmostEqual(offset_geometry["tx"], baseline_geometry["tx"], places=6)
        self.assertAlmostEqual(offset_geometry["ty"], baseline_geometry["ty"], places=6)

        edge_layer.deleteLater()
        self.app.processEvents()

    def test_edge_layer_gap_break_marks_only_under_edge_for_pipe_pipe_crossings(self) -> None:
        edge_layer = self._create_edge_layer({"viewBridge": self.view})
        self.view.centerOn(280.0, 220.0)
        self.app.processEvents()

        model = GraphModel()
        scene = GraphSceneBridge()
        scene.bind_graphics_preferences_source(self.bridge)
        scene.set_workspace(
            model,
            _build_edge_crossing_pipe_registry(),
            model.active_workspace.workspace_id,
        )
        upper_right_id = scene.add_node_from_type("tests.edge_crossing_pipe_probe_node", 420.0, 40.0)
        lower_left_id = scene.add_node_from_type("tests.edge_crossing_pipe_probe_node", 40.0, 300.0)
        lower_right_id = scene.add_node_from_type("tests.edge_crossing_pipe_probe_node", 420.0, 300.0)
        upper_left_id = scene.add_node_from_type("tests.edge_crossing_pipe_probe_node", 40.0, 40.0)
        under_edge_id = scene.add_edge(upper_right_id, "flow_out", lower_left_id, "flow_in")
        over_edge_id = scene.add_edge(lower_right_id, "flow_out", upper_left_id, "flow_in")

        edge_layer.setProperty("nodes", scene.nodes_model)
        edge_layer.setProperty("edges", scene.edges_model)
        edge_layer.setProperty("edgeCrossingStyle", "gap_break")
        self.app.processEvents()
        edge_layer.requestRedraw()
        self.app.processEvents()

        snapshots = [
            edge_layer._visibleEdgeSnapshot(under_edge_id).toVariant(),
            edge_layer._visibleEdgeSnapshot(over_edge_id).toVariant(),
        ]
        snapshots.sort(key=lambda payload: payload["drawOrderIndex"])
        lower_snapshot, upper_snapshot = snapshots
        self.assertEqual(lower_snapshot["geometry"]["route"], "pipe")
        self.assertEqual(upper_snapshot["geometry"]["route"], "pipe")
        self.assertEqual(lower_snapshot["drawOrderIndex"], 0)
        self.assertEqual(upper_snapshot["drawOrderIndex"], 1)
        self.assertGreaterEqual(len(lower_snapshot["crossingBreaks"]), 1)
        self.assertEqual(upper_snapshot["crossingBreaks"], [])
        self.assertIn("centerDistance", lower_snapshot["crossingBreaks"][0])
        self.assertIn("tangentY", lower_snapshot["crossingBreaks"][0])

        edge_layer.deleteLater()
        self.app.processEvents()

    def test_active_node_card_uses_fixed_dark_and_light_semantic_neutrals(self) -> None:
        component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(_NODE_CARD_QML_PATH)))
        if component.status() != QQmlComponent.Status.Ready:
            errors = "\n".join(str(error) for error in component.errors())
            self.fail(f"Failed to load NodeCard.qml:\n{errors}")
        node_payload = {
            "node_id": "node_theme_test",
            "type_id": "core.logger",
            "title": "Logger",
            "x": 120.0,
            "y": 120.0,
            "width": 210.0,
            "height": 132.0,
            "accent": "#2F89FF",
            "collapsed": False,
            "selected": False,
            "can_enter_scope": False,
            "ports": [
                {
                    "key": "payload",
                    "label": "Payload",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "any",
                    "connected": False,
                },
                {
                    "key": "message",
                    "label": "Message",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                },
                {
                    "key": "result",
                    "label": "Result",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "any",
                    "connected": False,
                },
            ],
            "inline_properties": [
                {
                    "key": "message",
                    "label": "Message",
                    "inline_editor": "text",
                    "value": "log message",
                    "overridden_by_input": False,
                    "input_port_label": "message",
                },
                {
                    "key": "level",
                    "label": "Level",
                    "inline_editor": "enum",
                    "value": "info",
                    "enum_values": ["info", "warning", "error"],
                    "overridden_by_input": False,
                    "input_port_label": "",
                },
            ],
        }
        if hasattr(component, "createWithInitialProperties"):
            node_card = component.createWithInitialProperties({"nodeData": node_payload})
        else:
            node_card = component.create()
            node_card.setProperty("nodeData", node_payload)
        if node_card is None:
            errors = "\n".join(str(error) for error in component.errors())
            self.fail(f"Failed to instantiate NodeCard.qml:\n{errors}")
        self.app.processEvents()

        self.assertEqual(_color_name(node_card.property("color")), "#403c2d")
        self.assertEqual(_color_name(node_card.property("bodyGradientEndColor")), "#3a372a")
        self.assertEqual(_color_name(node_card.property("outlineColor")), "#81795c")
        self.assertEqual(_color_name(node_card.property("headerTextColor")), "#f3f3f1")
        self.assertEqual(_color_name(node_card.property("inlineRowColor")), "#282b32")
        self.assertEqual(_color_name(node_card.property("inlineInputBackgroundColor")), "#24272e")
        self.assertEqual(_color_name(node_card.property("portLabelColor")), "#d7d5ce")
        self.assertEqual(set(self.graph_theme_bridge.port_kind_palette), {"data", "flow"})
        self.assertEqual(
            _color_name(node_card.basePortColor("data")),
            _color_name(self.graph_theme_bridge.port_kind_palette["data"]),
        )

        self.graph_theme_bridge.apply_theme("graph_stitch_light")
        self.app.processEvents()

        self.assertEqual(_color_name(node_card.property("color")), "#403c2d")
        self.assertEqual(_color_name(node_card.property("outlineColor")), "#81795c")

        self.theme_bridge.apply_theme("stitch_light")
        self.app.processEvents()

        self.assertEqual(_color_name(node_card.property("color")), "#f6f8f8")
        self.assertEqual(_color_name(node_card.property("bodyGradientEndColor")), "#f9fbfc")
        self.assertEqual(_color_name(node_card.property("outlineColor")), "#6b7277")
        self.assertEqual(_color_name(node_card.property("headerTextColor")), "#17174b")
        self.assertEqual(_color_name(node_card.property("inlineRowColor")), "#ffffff")
        self.assertEqual(_color_name(node_card.property("inlineInputBackgroundColor")), "#ffffff")
        self.assertEqual(_color_name(node_card.property("portLabelColor")), "#43436d")
        self.assertEqual(set(self.graph_theme_bridge.port_kind_palette), {"data", "flow"})
        self.assertEqual(
            _color_name(node_card.basePortColor("data")),
            _color_name(self.graph_theme_bridge.port_kind_palette["data"]),
        )

        node_card.deleteLater()
        self.app.processEvents()

    def test_passive_selected_glow_without_style_uses_graph_theme_selected_color(self) -> None:
        model = GraphModel()
        scene = GraphSceneBridge()
        scene.bind_graphics_preferences_source(self.bridge)
        scene.set_workspace(
            model,
            _build_edge_crossing_pipe_registry(),
            model.active_workspace.workspace_id,
        )
        node_id = scene.add_node_from_type("passive.planning.task_card", 120.0, 120.0)
        scene.clear_selection()

        self.canvas.deleteLater()
        self.app.processEvents()

        canvas_state_bridge = GraphCanvasStateBridge(
            session_state=self.canvas_source,  # type: ignore[arg-type]
            snap_to_grid_changed_signal=getattr(self.canvas_source, "snap_to_grid_changed", None),  # type: ignore[arg-type]
            snap_grid_size=float(getattr(self.canvas_source, "snap_grid_size", 20.0)),  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=self.bridge,  # type: ignore[arg-type]
            scene_bridge=scene,
            view_bridge=self.view,
        )
        canvas_command_bridge = GraphCanvasCommandBridge(
            search_scope_controller=self.canvas_source,  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            run_controller=self.canvas_source,  # type: ignore[arg-type]
            inspector_source=self.canvas_source,  # type: ignore[arg-type]
            library_source=self.canvas_source,  # type: ignore[arg-type]
            workspace_edit_controller=self.canvas_source,  # type: ignore[arg-type]
            workspace_drop_connect_controller=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=self.bridge,  # type: ignore[arg-type]
            scene_bridge=scene,
            view_bridge=self.view,
        )
        self.canvas = self._create_canvas(
            {
                "canvasStateBridge": canvas_state_bridge,
                "canvasCommandBridge": canvas_command_bridge,
                "canvasLifecycleBridge": canvas_state_bridge,
                "width": 1280.0,
                "height": 720.0,
            }
        )

        wait_for_condition_or_raise(
            lambda: len(_named_child_items(self.canvas, "graphNodeCard")) == 1,
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for passive graph canvas node host to appear.",
        )
        node_card = _named_child_items(self.canvas, "graphNodeCard")[0]
        self.assertEqual(str(node_card.property("surfaceFamily")), "planning")
        self.assertTrue(bool(node_card.property("isPassiveNode")))
        selected_halo = node_card.findChild(QObject, "graphNodeSelectedHalo")
        selected_glow_source = node_card.findChild(QObject, "graphNodeSelectedGlowSource")
        self.assertIsNotNone(selected_halo)
        self.assertIsNotNone(selected_glow_source)
        self.assertFalse(bool(selected_halo.property("visible")))

        scene.select_node(node_id)
        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isSelected")) and bool(selected_halo.property("visible")),
            timeout_ms=250,
            app=self.app,
            timeout_message="Timed out waiting for passive selected glow halo on graph canvas host.",
        )

        self.assertEqual(
            _color_name(node_card.property("selectedOutlineColor")),
            _color_name(self.graph_theme_bridge.node_palette["card_selected_border"]),
        )
        self.assertEqual(
            _color_name(selected_glow_source.property("color")),
            _color_name(node_card.property("selectedGlowColor")),
        )

        self.theme_bridge.apply_theme("stitch_light")
        self.graph_theme_bridge.apply_theme("graph_stitch_light")
        wait_for_condition_or_raise(
            lambda: _color_name(node_card.property("selectedOutlineColor"))
            == _color_name(self.graph_theme_bridge.node_palette["card_selected_border"]),
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for passive selected glow to follow graph theme update.",
        )
        self.assertTrue(bool(selected_halo.property("visible")))
        self.assertEqual(
            _color_name(selected_glow_source.property("color")),
            _color_name(node_card.property("selectedGlowColor")),
        )

    def test_styled_passive_selected_glow_uses_graph_theme_selected_color(self) -> None:
        model = GraphModel()
        scene = GraphSceneBridge()
        scene.bind_graphics_preferences_source(self.bridge)
        scene.set_workspace(
            model,
            _build_edge_crossing_pipe_registry(),
            model.active_workspace.workspace_id,
        )
        node_id = scene.add_node_from_type("passive.planning.task_card", 120.0, 120.0)
        scene.set_node_visual_style(
            node_id,
            {
                "fill_color": "#FFF4E7",
                "border_color": "#C97A2B",
                "text_color": "#4D2D12",
                "accent_color": "#E2A35D",
                "header_color": "#FFE8CF",
                "border_width": 2.0,
                "corner_radius": 18.0,
            },
        )
        scene.clear_selection()

        self.canvas.deleteLater()
        self.app.processEvents()

        canvas_state_bridge = GraphCanvasStateBridge(
            session_state=self.canvas_source,  # type: ignore[arg-type]
            snap_to_grid_changed_signal=getattr(self.canvas_source, "snap_to_grid_changed", None),  # type: ignore[arg-type]
            snap_grid_size=float(getattr(self.canvas_source, "snap_grid_size", 20.0)),  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=self.bridge,  # type: ignore[arg-type]
            scene_bridge=scene,
            view_bridge=self.view,
        )
        canvas_command_bridge = GraphCanvasCommandBridge(
            search_scope_controller=self.canvas_source,  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            run_controller=self.canvas_source,  # type: ignore[arg-type]
            inspector_source=self.canvas_source,  # type: ignore[arg-type]
            library_source=self.canvas_source,  # type: ignore[arg-type]
            workspace_edit_controller=self.canvas_source,  # type: ignore[arg-type]
            workspace_drop_connect_controller=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=self.bridge,  # type: ignore[arg-type]
            scene_bridge=scene,
            view_bridge=self.view,
        )
        self.canvas = self._create_canvas(
            {
                "canvasStateBridge": canvas_state_bridge,
                "canvasCommandBridge": canvas_command_bridge,
                "canvasLifecycleBridge": canvas_state_bridge,
                "width": 1280.0,
                "height": 720.0,
            }
        )

        wait_for_condition_or_raise(
            lambda: len(_named_child_items(self.canvas, "graphNodeCard")) == 1,
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for styled passive graph canvas node host to appear.",
        )
        node_card = _named_child_items(self.canvas, "graphNodeCard")[0]
        self.assertEqual(str(node_card.property("surfaceFamily")), "planning")
        self.assertTrue(bool(node_card.property("isPassiveNode")))
        selected_halo = node_card.findChild(QObject, "graphNodeSelectedHalo")
        selected_glow_source = node_card.findChild(QObject, "graphNodeSelectedGlowSource")
        self.assertIsNotNone(selected_halo)
        self.assertIsNotNone(selected_glow_source)
        self.assertFalse(bool(node_card.property("isSelected")))
        self.assertEqual(_color_name(node_card.property("outlineColor")), _color_name("#C97A2B"))
        self.assertAlmostEqual(float(node_card.property("resolvedBorderWidth")), 2.0, places=6)

        scene.select_node(node_id)
        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isSelected")) and bool(selected_halo.property("visible")),
            timeout_ms=250,
            app=self.app,
            timeout_message="Timed out waiting for styled passive selected glow halo on graph canvas host.",
        )

        self.assertEqual(
            _color_name(node_card.property("selectedOutlineColor")),
            _color_name(self.graph_theme_bridge.node_palette["card_selected_border"]),
        )
        self.assertNotEqual(
            _color_name(node_card.property("selectedOutlineColor")),
            _color_name("#E2A35D"),
        )
        self.assertNotEqual(
            _color_name(node_card.property("selectedOutlineColor")),
            _color_name("#C97A2B"),
        )
        self.assertAlmostEqual(float(node_card.property("resolvedBorderWidth")), 3.0, places=6)
        self.assertEqual(
            _color_name(selected_glow_source.property("color")),
            _color_name(node_card.property("selectedGlowColor")),
        )

    def test_flowchart_selected_glow_uses_graph_theme_selected_color(self) -> None:
        model = GraphModel()
        scene = GraphSceneBridge()
        scene.bind_graphics_preferences_source(self.bridge)
        scene.set_workspace(
            model,
            _build_edge_crossing_pipe_registry(),
            model.active_workspace.workspace_id,
        )
        node_id = scene.add_node_from_type("passive.flowchart.process", 120.0, 120.0)
        scene.set_node_visual_style(
            node_id,
            {
                "fill_color": "#FFF4E7",
                "border_color": "#C97A2B",
                "accent_color": "#E2A35D",
                "border_width": 2.0,
            },
        )
        scene.clear_selection()

        self.canvas.deleteLater()
        self.app.processEvents()

        canvas_state_bridge = GraphCanvasStateBridge(
            session_state=self.canvas_source,  # type: ignore[arg-type]
            snap_to_grid_changed_signal=getattr(self.canvas_source, "snap_to_grid_changed", None),  # type: ignore[arg-type]
            snap_grid_size=float(getattr(self.canvas_source, "snap_grid_size", 20.0)),  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=self.bridge,  # type: ignore[arg-type]
            scene_bridge=scene,
            view_bridge=self.view,
        )
        canvas_command_bridge = GraphCanvasCommandBridge(
            search_scope_controller=self.canvas_source,  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            run_controller=self.canvas_source,  # type: ignore[arg-type]
            inspector_source=self.canvas_source,  # type: ignore[arg-type]
            library_source=self.canvas_source,  # type: ignore[arg-type]
            workspace_edit_controller=self.canvas_source,  # type: ignore[arg-type]
            workspace_drop_connect_controller=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=self.bridge,  # type: ignore[arg-type]
            scene_bridge=scene,
            view_bridge=self.view,
        )
        self.canvas = self._create_canvas(
            {
                "canvasStateBridge": canvas_state_bridge,
                "canvasCommandBridge": canvas_command_bridge,
                "canvasLifecycleBridge": canvas_state_bridge,
                "width": 1280.0,
                "height": 720.0,
            }
        )

        wait_for_condition_or_raise(
            lambda: len(_named_child_items(self.canvas, "graphNodeCard")) == 1,
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for styled flowchart graph canvas node host to appear.",
        )
        node_card = _named_child_items(self.canvas, "graphNodeCard")[0]
        self.assertTrue(bool(node_card.property("isFlowchartSurface")))
        self.assertTrue(bool(node_card.property("isPassiveNode")))
        selected_halo = node_card.findChild(QObject, "graphNodeFlowchartSelectedHalo")
        self.assertIsNotNone(selected_halo)
        self.assertFalse(bool(node_card.property("isSelected")))
        self.assertEqual(_color_name(node_card.property("outlineColor")), _color_name("#C97A2B"))
        self.assertAlmostEqual(float(node_card.property("resolvedBorderWidth")), 2.0, places=6)

        scene.select_node(node_id)
        wait_for_condition_or_raise(
            lambda: bool(node_card.property("isSelected")) and bool(selected_halo.property("visible")),
            timeout_ms=250,
            app=self.app,
            timeout_message="Timed out waiting for styled flowchart selected glow halo on graph canvas host.",
        )

        self.assertEqual(
            _color_name(node_card.property("selectedOutlineColor")),
            _color_name(self.graph_theme_bridge.node_palette["card_selected_border"]),
        )
        self.assertNotEqual(
            _color_name(node_card.property("selectedOutlineColor")),
            _color_name("#E2A35D"),
        )
        self.assertNotEqual(
            _color_name(node_card.property("selectedOutlineColor")),
            _color_name("#C97A2B"),
        )
        self.assertAlmostEqual(float(node_card.property("resolvedBorderWidth")), 3.0, places=6)

    def test_passive_node_card_exposes_only_body_gradient_properties(self) -> None:
        component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(_NODE_CARD_QML_PATH)))
        if component.status() != QQmlComponent.Status.Ready:
            errors = "\n".join(str(error) for error in component.errors())
            self.fail(f"Failed to load NodeCard.qml:\n{errors}")
        node_payload = {
            "node_id": "node_gradient_test",
            "type_id": "tests.passive_gradient",
            "title": "Gradient",
            "x": 120.0,
            "y": 120.0,
            "width": 210.0,
            "height": 132.0,
            "accent": "#2F89FF",
            "collapsed": False,
            "selected": False,
            "runtime_behavior": "passive",
            "surface_family": "standard",
            "visual_style": {
                "fill_color": "#112233",
                "gradient_enabled": True,
                "gradient_color": "#445566",
                "gradient_direction": "radial",
            },
            "ports": [],
            "inline_properties": [],
        }
        if hasattr(component, "createWithInitialProperties"):
            node_card = component.createWithInitialProperties({"nodeData": node_payload})
        else:
            node_card = component.create()
            node_card.setProperty("nodeData", node_payload)
        if node_card is None:
            errors = "\n".join(str(error) for error in component.errors())
            self.fail(f"Failed to instantiate NodeCard.qml:\n{errors}")
        self.app.processEvents()

        self.assertTrue(node_card.property("bodyGradientActive"))
        self.assertEqual(_color_name(node_card.property("bodyGradientStartColor")), "#112233")
        self.assertEqual(_color_name(node_card.property("bodyGradientEndColor")), "#445566")
        self.assertEqual(node_card.property("bodyGradientDirection"), "radial")
        self.assertIsNone(node_card.property("headerColor"))
        self.assertIsNone(node_card.property("headerGradientActive"))
        self.assertIsNone(node_card.findChild(QObject, "graphNodeHeaderGradientFill"))

        node_card.deleteLater()
        self.app.processEvents()

__all__ = ['GraphCanvasQmlPreferenceRenderingTests']
