from __future__ import annotations

from tests.graph_surface.environment import *  # noqa: F403

pytestmark = pytest.mark.xdist_group("p03_graph_surface")  # noqa: F405

class GraphSurfaceInputContractTests(GraphSurfaceInputContractTestBase):
    def test_graph_surface_pointer_audit_rejects_hover_proxy_shims_and_untracked_surface_mouse_areas(self) -> None:
        failures = self._graph_surface_pointer_audit_failures_with_fallback()
        if failures:
            self.fail("\n\n".join(failures))

    def test_surface_loader_forwards_embedded_interactive_rects_for_inline_properties(self) -> None:
        self._run_qml_probe(
            "loader-embedded-rects",
            """
            host = create_component(graph_node_host_qml_path, {"nodeData": node_payload()})
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            assert loader is not None

            embedded_rects = variant_list(loader.property("embeddedInteractiveRects"))

            assert len(embedded_rects) == 1
            assert rect_field(embedded_rects[0], "x") > 80.0
            assert rect_field(embedded_rects[0], "y") >= 30.0
            assert rect_field(embedded_rects[0], "width") > 80.0
            assert rect_field(embedded_rects[0], "width") < 120.0
            assert rect_field(embedded_rects[0], "height") >= 18.0
            """,
        )

    def test_surface_loader_tracks_control_scoped_rects_for_all_core_inline_editors(self) -> None:
        self._run_qml_probe(
            "loader-core-inline-editor-rects",
            """
            payload = node_payload()
            payload["inline_properties"] = [
                {
                    "key": "enabled",
                    "label": "Enabled",
                    "inline_editor": "toggle",
                    "value": True,
                    "overridden_by_input": False,
                    "input_port_label": "enabled",
                },
                {
                    "key": "mode",
                    "label": "Mode",
                    "inline_editor": "enum",
                    "value": "two",
                    "enum_values": ["one", "two", "three"],
                    "overridden_by_input": False,
                    "input_port_label": "mode",
                },
                {
                    "key": "message",
                    "label": "Message",
                    "inline_editor": "text",
                    "value": "log message",
                    "overridden_by_input": False,
                    "input_port_label": "message",
                },
                {
                    "key": "count",
                    "label": "Count",
                    "inline_editor": "number",
                    "value": "5",
                    "overridden_by_input": False,
                    "input_port_label": "count",
                },
            ]

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            assert loader is not None

            embedded_rects = variant_list(loader.property("embeddedInteractiveRects"))
            assert len(embedded_rects) == 4

            xs = [rect_field(rect, "x") for rect in embedded_rects]
            widths = [rect_field(rect, "width") for rect in embedded_rects]
            ys = [rect_field(rect, "y") for rect in embedded_rects]

            assert all(x > 80.0 for x in xs)
            assert widths[0] < 40.0
            assert all(width > 80.0 for width in widths[1:])
            assert ys == sorted(ys)
            """,
        )

    def test_host_body_interactions_yield_inside_embedded_rects_but_still_work_adjacent_to_them(self) -> None:
        self._run_qml_probe(
            "embedded-rect-hit-testing",
            """
            host = create_component(graph_node_host_qml_path, {"nodeData": node_payload()})
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            gesture_layer = host.findChild(QObject, "graphNodeHostGestureLayer")
            drag_area = host.findChild(QObject, "graphNodeDragArea")
            assert loader is not None
            assert gesture_layer is not None
            assert drag_area is not None
            assert drag_area.parentItem().objectName() == "graphNodeHostGestureLayer"

            embedded_rects = variant_list(loader.property("embeddedInteractiveRects"))
            assert len(embedded_rects) == 1
            row_rect = embedded_rects[0]
            assert rect_field(row_rect, "x") > 80.0

            window = attach_host_to_window(host)

            inside_point = host_scene_point(
                host,
                rect_field(row_rect, "x") + 8.0,
                rect_field(row_rect, "y") + rect_field(row_rect, "height") * 0.5,
            )
            body_local_x = rect_field(row_rect, "x") - 8.0
            body_local_y = rect_field(row_rect, "y") + rect_field(row_rect, "height") * 0.5
            body_point = host_scene_point(host, body_local_x, body_local_y)

            QTest.mouseMove(window, inside_point)
            settle_events(2)
            assert drag_area.property("cursorShape") == Qt.CursorShape.ArrowCursor

            QTest.mouseMove(window, body_point)
            settle_events(2)
            assert drag_area.property("cursorShape") == Qt.CursorShape.OpenHandCursor

            assert_host_pointer_routing(
                host,
                window,
                inside_point,
                body_point,
                "node_surface_contract_test",
                expected_body_local=(body_local_x, body_local_y),
            )

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_host_drag_release_over_embedded_rect_still_finishes_drag(self) -> None:
        self._run_qml_probe(
            "embedded-rect-release-finishes-drag",
            """
            payload = node_payload()
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            drag_area = host.findChild(QObject, "graphNodeDragArea")
            assert loader is not None
            assert drag_area is not None

            embedded_rects = variant_list(loader.property("embeddedInteractiveRects"))
            assert len(embedded_rects) == 1
            row_rect = embedded_rects[0]

            offset_events = []
            finish_events = []
            cancel_events = []
            host.dragOffsetChanged.connect(
                lambda node_id, dx, dy: offset_events.append((str(node_id), float(dx), float(dy)))
            )
            host.dragFinished.connect(
                lambda node_id, final_x, final_y, moved: finish_events.append(
                    (str(node_id), float(final_x), float(final_y), bool(moved))
                )
            )
            host.dragCanceled.connect(lambda node_id: cancel_events.append(str(node_id)))

            window = attach_host_to_window(host)
            body_point = host_scene_point(
                host,
                max(12.0, rect_field(row_rect, "x") - 20.0),
                rect_field(row_rect, "y") + rect_field(row_rect, "height") * 0.5,
            )
            control_point = host_scene_point(
                host,
                rect_field(row_rect, "x") + 12.0,
                rect_field(row_rect, "y") + rect_field(row_rect, "height") * 0.5,
            )

            QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, body_point)
            settle_events(2)
            QTest.mouseMove(window, control_point)
            settle_events(2)
            QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, control_point)
            settle_events(2)

            assert offset_events, "drag did not emit a live offset before release"
            assert finish_events == [("node_surface_contract_test", 152.0, 120.0, True)]
            assert cancel_events == []
            assert not bool(drag_area.property("manualDragActive"))

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_deactivates_far_offscreen_node_surfaces_but_keeps_force_active_exceptions(self) -> None:
        self._run_qml_probe(
            "graph-canvas-offscreen-render-activation",
            """
            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            def node_card_or_none(node_id):
                for item in named_child_items(canvas, "graphNodeCard"):
                    node_data = variant_value(item.property("nodeData")) or {}
                    if str(node_data.get("node_id", "")) == str(node_id):
                        return item
                return None

            def node_card_for(node_id):
                item = node_card_or_none(node_id)
                if item is not None:
                    return item
                raise AssertionError(f"Missing node card for {node_id!r}")

            def visible_node_ids():
                return {
                    str(payload.get("node_id", ""))
                    for payload in canvas_state_bridge.visible_nodes_payloads
                    if isinstance(payload, dict)
                }

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id

            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)

            padded_node_id = scene.add_node_from_type("core.logger", 340.0, 40.0)
            offscreen_node_id = scene.add_node_from_type("core.logger", 900.0, 620.0)
            scene.clear_selection()

            view = ViewportBridge()
            view.set_viewport_size(640.0, 480.0)
            view.set_view_state(1.0, 0.0, 0.0)
            canvas_state_bridge, canvas_command_bridge = build_canvas_bridges(
                scene_bridge=scene,
                view_bridge=view,
            )

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 640.0,
                    "height": 480.0,
                },
            )
            settle_events(3)

            padded_card = node_card_for(padded_node_id)
            padded_loader = padded_card.findChild(QObject, "graphNodeSurfaceLoader")

            assert padded_loader is not None
            assert bool(padded_card.property("renderActive"))
            assert bool(padded_loader.property("renderActive"))
            assert bool(padded_loader.property("surfaceLoaded"))
            assert padded_node_id in visible_node_ids(), visible_node_ids()
            assert offscreen_node_id not in visible_node_ids(), visible_node_ids()

            canvas_state_bridge.set_visible_model_active_node_ids([offscreen_node_id])
            settle_events(3)

            assert offscreen_node_id in visible_node_ids(), visible_node_ids()

            canvas_state_bridge.clear_visible_model_active_node_ids()
            settle_events(3)

            assert offscreen_node_id not in visible_node_ids(), visible_node_ids()

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_pendingConnectionPort_request_connect_ports_preserves_flowchart_gesture_order(self) -> None:
        self._run_qml_probe(
            "graph-canvas-flowchart-gesture-order",
            """
            from PyQt6.QtCore import QObject, pyqtProperty, pyqtSlot

            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.ui.graph_interactions import GraphInteractions
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            class FlowchartShellBridgeStub(QObject):
                def __init__(self, interactions):
                    super().__init__()
                    self._interactions = interactions
                    self.connect_calls = []

                @pyqtProperty(bool, constant=True)
                def graphics_minimap_expanded(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_grid(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_minimap(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_node_shadow(self):
                    return True

                @pyqtProperty(int, constant=True)
                def graphics_shadow_strength(self):
                    return 70

                @pyqtProperty(int, constant=True)
                def graphics_shadow_softness(self):
                    return 50

                @pyqtProperty(int, constant=True)
                def graphics_shadow_offset(self):
                    return 4

                @pyqtProperty(bool, constant=True)
                def snap_to_grid_enabled(self):
                    return False

                @pyqtProperty(float, constant=True)
                def snap_grid_size(self):
                    return 20.0

                @pyqtSlot(str, str, str, str, bool, result=bool)
                def request_connect_ports(self, node_a_id, port_a, node_b_id, port_b, append):
                    assert not bool(append)
                    request = (
                        str(node_a_id or ""),
                        str(port_a or ""),
                        str(node_b_id or ""),
                        str(port_b or ""),
                    )
                    self.connect_calls.append(request)
                    result = self._interactions.connect_ports(*request)
                    return bool(result.ok)

            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, model.active_workspace.workspace_id)
            interactions = GraphInteractions(scene, registry)
            shell_bridge = FlowchartShellBridgeStub(interactions)
            view = ViewportBridge()
            view.set_viewport_size(640.0, 480.0)
            canvas_state_bridge, canvas_command_bridge = build_canvas_bridges(
                shell_bridge=shell_bridge,
                scene_bridge=scene,
                view_bridge=view,
            )
            canvas_command_bridge._search_scope_controller = shell_bridge
            canvas_command_bridge._app_preferences_source = shell_bridge
            canvas_command_bridge._run_controller = shell_bridge
            canvas_command_bridge._inspector_source = shell_bridge
            canvas_command_bridge._library_source = shell_bridge
            canvas_command_bridge._workspace_edit_controller = shell_bridge
            canvas_command_bridge._workspace_drop_connect_controller = shell_bridge

            first_source_id = scene.add_node_from_type("passive.flowchart.process", 20.0, 20.0)
            first_target_id = scene.add_node_from_type("passive.flowchart.process", 360.0, 160.0)
            second_source_id = scene.add_node_from_type("passive.flowchart.process", 20.0, 300.0)
            second_target_id = scene.add_node_from_type("passive.flowchart.process", 360.0, 300.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 640.0,
                    "height": 480.0,
                },
            )

            canvas.handlePortClick(first_source_id, "right", "neutral", 120.0, 90.0, 0)
            app.processEvents()

            pending = variant_value(canvas.property("pendingConnectionPort"))
            assert pending is not None, variant_value(canvas._scenePortData(first_source_id, "right"))
            assert pending["direction"] == "neutral"
            assert pending["origin_side"] == "right"

            canvas.handlePortClick(first_target_id, "top", "neutral", 460.0, 200.0, 0)
            app.processEvents()

            assert shell_bridge.connect_calls and shell_bridge.connect_calls[0] == (
                first_source_id,
                "right",
                first_target_id,
                "top",
            ), (
                variant_value(canvas._scenePortData(first_source_id, "right")),
                variant_value(canvas._scenePortData(first_target_id, "top")),
                variant_value(canvas.property("pendingConnectionPort")),
            )
            assert canvas.property("pendingConnectionPort") is None

            canvas.handlePortClick(second_target_id, "left", "neutral", 1160.0, 230.0, 0)
            app.processEvents()

            pending = variant_value(canvas.property("pendingConnectionPort"))
            assert pending is not None
            assert pending["direction"] == "neutral"
            assert pending["origin_side"] == "left"

            canvas.handlePortClick(second_source_id, "bottom", "neutral", 820.0, 150.0, 0)
            app.processEvents()

            assert shell_bridge.connect_calls[1] == (
                second_target_id,
                "left",
                second_source_id,
                "bottom",
            )

            workspace = model.active_workspace
            stored_edges = {
                (edge.source_node_id, edge.source_port_key, edge.target_node_id, edge.target_port_key)
                for edge in workspace.edges.values()
            }
            assert (
                first_source_id,
                "right",
                first_target_id,
                "top",
            ) in stored_edges
            assert (
                second_target_id,
                "left",
                second_source_id,
                "bottom",
            ) in stored_edges

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_pendingConnectionPort_rejects_same_node_passive_flow_edge(self) -> None:
        self._run_qml_probe_with_retry(
            "graph-canvas-same-node-passive-flow-rejected",
            """
            from PyQt6.QtCore import QObject, pyqtProperty, pyqtSlot

            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            class FlowShellBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.connect_calls = []

                @pyqtProperty(bool, constant=True)
                def graphics_minimap_expanded(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_grid(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_minimap(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_node_shadow(self):
                    return True

                @pyqtProperty(int, constant=True)
                def graphics_shadow_strength(self):
                    return 70

                @pyqtProperty(int, constant=True)
                def graphics_shadow_softness(self):
                    return 50

                @pyqtProperty(int, constant=True)
                def graphics_shadow_offset(self):
                    return 4

                @pyqtProperty(bool, constant=True)
                def snap_to_grid_enabled(self):
                    return False

                @pyqtProperty(float, constant=True)
                def snap_grid_size(self):
                    return 20.0

                @pyqtSlot(str, str, str, str, bool, result=bool)
                def request_connect_ports(self, node_a_id, port_a, node_b_id, port_b, append):
                    self.connect_calls.append(
                        (
                            str(node_a_id or ""),
                            str(port_a or ""),
                            str(node_b_id or ""),
                            str(port_b or ""),
                            bool(append),
                        )
                    )
                    return True

            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, model.active_workspace.workspace_id)
            shell_bridge = FlowShellBridgeStub()
            view = ViewportBridge()
            view.set_viewport_size(640.0, 480.0)
            canvas_state_bridge, canvas_command_bridge = build_canvas_bridges(
                shell_bridge=shell_bridge,
                scene_bridge=scene,
                view_bridge=view,
            )
            canvas_command_bridge._search_scope_controller = shell_bridge
            canvas_command_bridge._app_preferences_source = shell_bridge
            canvas_command_bridge._run_controller = shell_bridge
            canvas_command_bridge._inspector_source = shell_bridge
            canvas_command_bridge._library_source = shell_bridge
            canvas_command_bridge._workspace_edit_controller = shell_bridge
            canvas_command_bridge._workspace_drop_connect_controller = shell_bridge

            node_id = scene.add_node_from_type("passive.flowchart.process", 20.0, 20.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 640.0,
                    "height": 480.0,
                },
            )

            canvas.handlePortClick(node_id, "top", "neutral", 40.0, 84.0, 0)
            app.processEvents()

            pending = variant_value(canvas.property("pendingConnectionPort"))
            assert pending is not None, variant_value(canvas._scenePortData(node_id, "top"))
            assert pending["node_id"] == node_id
            assert pending["port_key"] == "top"

            canvas.handlePortClick(node_id, "right", "neutral", 220.0, 84.0, 0)
            app.processEvents()

            assert shell_bridge.connect_calls == [], shell_bridge.connect_calls
            pending = variant_value(canvas.property("pendingConnectionPort"))
            assert pending is not None, pending
            assert pending["node_id"] == node_id
            assert pending["port_key"] == "top"

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_projects_active_view_optional_filter_and_plain_double_click_opens_quick_insert(self) -> None:
        self._run_qml_probe(
            "graph-canvas-optional-filter-projection-and-plain-double-click",
            """
            from PyQt6.QtCore import QObject, pyqtProperty, pyqtSlot
            from PyQt6.QtTest import QTest

            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            class CanvasShellBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.quick_insert_calls = []

                @pyqtProperty(bool, constant=True)
                def graphics_minimap_expanded(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_grid(self):
                    return True

                @pyqtProperty(str, constant=True)
                def graphics_grid_style(self):
                    return "lines"

                @pyqtProperty(str, constant=True)
                def graphics_edge_crossing_style(self):
                    return "none"

                @pyqtProperty(bool, constant=True)
                def graphics_show_minimap(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_port_labels(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_node_shadow(self):
                    return True

                @pyqtProperty(int, constant=True)
                def graphics_shadow_strength(self):
                    return 70

                @pyqtProperty(int, constant=True)
                def graphics_shadow_softness(self):
                    return 50

                @pyqtProperty(int, constant=True)
                def graphics_shadow_offset(self):
                    return 4

                @pyqtProperty(bool, constant=True)
                def snap_to_grid_enabled(self):
                    return False

                @pyqtProperty(float, constant=True)
                def snap_grid_size(self):
                    return 20.0

                @pyqtSlot(float, float, float, float)
                def request_open_canvas_quick_insert(self, scene_x, scene_y, overlay_x, overlay_y):
                    self.quick_insert_calls.append(
                        (
                            float(scene_x),
                            float(scene_y),
                            float(overlay_x),
                            float(overlay_y),
                        )
                    )

            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, model.active_workspace.workspace_id)
            view = ViewportBridge()
            view.set_viewport_size(640.0, 480.0)
            shell_bridge = CanvasShellBridgeStub()
            canvas_state_bridge, canvas_command_bridge = build_canvas_bridges(
                shell_bridge=shell_bridge,
                scene_bridge=scene,
                view_bridge=view,
            )

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 640.0,
                    "height": 480.0,
                },
            )
            window = attach_host_to_window(canvas, width=640, height=480)

            try:
                input_layers = canvas.findChild(QObject, "graphCanvasInputLayers")
                marquee_area = canvas.findChild(QObject, "graphCanvasMarqueeArea")
                assert input_layers is not None
                assert marquee_area is not None
                assert not bool(canvas.property("hideOptionalPorts"))

                scene.set_hide_optional_ports(True)
                settle_events(3)
                assert bool(canvas.property("hideOptionalPorts"))

                point = QPoint(160, 120)
                QTest.mouseDClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
                settle_events(3)

                assert len(shell_bridge.quick_insert_calls) == 1
                assert bool(canvas.property("hideOptionalPorts"))
            finally:
                dispose_host_window(canvas, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_graph_canvas_middle_right_chord_toggles_optional_filter_without_pan_or_box_zoom(self) -> None:
        self._run_qml_probe(
            "graph-canvas-optional-filter-middle-right-chord",
            """
            from PyQt6.QtCore import QObject, pyqtProperty
            from PyQt6.QtTest import QTest

            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            class CanvasShellBridgeStub(QObject):
                @pyqtProperty(bool, constant=True)
                def graphics_minimap_expanded(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_grid(self):
                    return True

                @pyqtProperty(str, constant=True)
                def graphics_grid_style(self):
                    return "lines"

                @pyqtProperty(str, constant=True)
                def graphics_edge_crossing_style(self):
                    return "none"

                @pyqtProperty(bool, constant=True)
                def graphics_show_minimap(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_port_labels(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_node_shadow(self):
                    return True

                @pyqtProperty(int, constant=True)
                def graphics_shadow_strength(self):
                    return 70

                @pyqtProperty(int, constant=True)
                def graphics_shadow_softness(self):
                    return 50

                @pyqtProperty(int, constant=True)
                def graphics_shadow_offset(self):
                    return 4

                @pyqtProperty(bool, constant=True)
                def snap_to_grid_enabled(self):
                    return False

                @pyqtProperty(float, constant=True)
                def snap_grid_size(self):
                    return 20.0

            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, model.active_workspace.workspace_id)
            view = ViewportBridge()
            view.set_viewport_size(640.0, 480.0)
            view.set_view_state(1.0, 0.0, 0.0)
            shell_bridge = CanvasShellBridgeStub()
            canvas_state_bridge, canvas_command_bridge = build_canvas_bridges(
                shell_bridge=shell_bridge,
                scene_bridge=scene,
                view_bridge=view,
            )

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 640.0,
                    "height": 480.0,
                },
            )
            window = attach_host_to_window(canvas, width=640, height=480)

            try:
                pan_area = canvas.findChild(QObject, "graphCanvasPanArea")
                marquee_area = canvas.findChild(QObject, "graphCanvasMarqueeArea")
                assert pan_area is not None
                assert marquee_area is not None

                baseline_zoom = float(view.zoom_value)
                baseline_center_x = float(view.center_x)
                baseline_center_y = float(view.center_y)

                right_point = QPoint(240, 220)

                QTest.mousePress(window, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, right_point)
                QTest.mousePress(window, Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier, right_point)
                settle_events(3)
                QTest.mouseRelease(window, Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier, right_point)
                QTest.mouseRelease(window, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, right_point)
                settle_events(3)

                assert bool(canvas.property("hideOptionalPorts"))
                assert not bool(marquee_area.property("selecting"))
                assert not bool(pan_area.property("panning"))
                assert float(view.zoom_value) == baseline_zoom
                assert float(view.center_x) == baseline_center_x
                assert float(view.center_y) == baseline_center_y
            finally:
                dispose_host_window(canvas, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_graph_canvas_left_drag_selection_uses_directional_marquee_modes(self) -> None:
        self._run_qml_probe(
            "graph-canvas-directional-marquee-selection",
            """
            from PyQt6.QtCore import QObject, QPoint, pyqtProperty
            from PyQt6.QtTest import QTest

            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            class CanvasShellBridgeStub(QObject):
                @pyqtProperty(bool, constant=True)
                def graphics_minimap_expanded(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_grid(self):
                    return True

                @pyqtProperty(str, constant=True)
                def graphics_grid_style(self):
                    return "lines"

                @pyqtProperty(str, constant=True)
                def graphics_edge_crossing_style(self):
                    return "none"

                @pyqtProperty(bool, constant=True)
                def graphics_show_minimap(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_port_labels(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_node_shadow(self):
                    return True

                @pyqtProperty(int, constant=True)
                def graphics_shadow_strength(self):
                    return 70

                @pyqtProperty(int, constant=True)
                def graphics_shadow_softness(self):
                    return 50

                @pyqtProperty(int, constant=True)
                def graphics_shadow_offset(self):
                    return 4

                @pyqtProperty(bool, constant=True)
                def snap_to_grid_enabled(self):
                    return False

                @pyqtProperty(float, constant=True)
                def snap_grid_size(self):
                    return 20.0

            def point_for_scene(canvas, scene_x, scene_y):
                return QPoint(
                    int(round(float(canvas.sceneToScreenX(scene_x)))),
                    int(round(float(canvas.sceneToScreenY(scene_y)))),
                )

            def drag_marquee(canvas, window, scene_x1, scene_y1, scene_x2, scene_y2, modifier):
                start = point_for_scene(canvas, scene_x1, scene_y1)
                end = point_for_scene(canvas, scene_x2, scene_y2)
                mid = QPoint(
                    int(round((start.x() + end.x()) * 0.5)),
                    int(round((start.y() + end.y()) * 0.5)),
                )
                for point in (start, mid, end):
                    assert 0 <= point.x() <= int(window.width())
                    assert 0 <= point.y() <= int(window.height())
                QTest.mousePress(window, Qt.MouseButton.LeftButton, modifier, start)
                settle_events(1)
                QTest.mouseMove(window, mid)
                settle_events(1)
                QTest.mouseMove(window, end)
                settle_events(1)
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, modifier, end)
                settle_events(4)

            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, model.active_workspace.workspace_id)
            view = ViewportBridge()
            view.set_viewport_size(640.0, 480.0)
            view.set_view_state(1.0, 0.0, 0.0)
            shell_bridge = CanvasShellBridgeStub()
            canvas_state_bridge, canvas_command_bridge = build_canvas_bridges(
                shell_bridge=shell_bridge,
                scene_bridge=scene,
                view_bridge=view,
            )

            enclosed_node = scene.add_node_from_type("core.constant", -140.0, -60.0)
            crossing_node = scene.add_node_from_type("core.if", 120.0, -60.0)
            retained_node = scene.add_node_from_type("core.logger", -140.0, 180.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 640.0,
                    "height": 480.0,
                },
            )
            window = attach_host_to_window(canvas, width=640, height=480)

            try:
                marquee_area = canvas.findChild(QObject, "graphCanvasMarqueeArea")
                assert marquee_area is not None

                enclosed_bounds = scene.node_bounds(enclosed_node)
                crossing_bounds = scene.node_bounds(crossing_node)
                assert enclosed_bounds is not None
                assert crossing_bounds is not None

                min_x = enclosed_bounds.x() - 24.0
                max_x = crossing_bounds.x() + min(36.0, crossing_bounds.width() * 0.5)
                min_y = min(enclosed_bounds.y(), crossing_bounds.y()) - 24.0
                max_y = max(
                    enclosed_bounds.y() + enclosed_bounds.height(),
                    crossing_bounds.y() + crossing_bounds.height(),
                ) + 24.0

                scene.clear_selection()
                drag_marquee(canvas, window, min_x, min_y, max_x, max_y, Qt.KeyboardModifier.NoModifier)
                assert set(scene.selected_node_lookup) == {enclosed_node}
                assert not bool(marquee_area.property("selecting"))

                scene.clear_selection()
                drag_marquee(canvas, window, max_x, max_y, min_x, min_y, Qt.KeyboardModifier.NoModifier)
                assert set(scene.selected_node_lookup) == {enclosed_node, crossing_node}

                scene.select_node(retained_node)
                drag_marquee(canvas, window, max_x, max_y, min_x, min_y, Qt.KeyboardModifier.ControlModifier)
                assert set(scene.selected_node_lookup) == {enclosed_node, crossing_node, retained_node}
            finally:
                dispose_host_window(canvas, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )
