from __future__ import annotations

import unittest

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_surface_metrics import node_surface_metrics
from tests.graph_surface_pointer_regression import run_qml_probe


class FlowchartVisualPolishMetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()

    def _metrics_for(self, type_id: str):
        spec = self.registry.get_spec(type_id)
        node = NodeInstance(
            node_id=f"node_{type_id.rsplit('.', 1)[-1]}",
            type_id=type_id,
            title=spec.display_name,
            x=20.0,
            y=30.0,
        )
        return node_surface_metrics(node, spec, {node.node_id: node})

    def test_polished_flowchart_variants_use_roomier_layout_metrics(self) -> None:
        decision = self._metrics_for("passive.flowchart.decision")
        document = self._metrics_for("passive.flowchart.document")
        connector = self._metrics_for("passive.flowchart.connector")
        input_output = self._metrics_for("passive.flowchart.input_output")
        predefined = self._metrics_for("passive.flowchart.predefined_process")
        database = self._metrics_for("passive.flowchart.database")
        card = self._metrics_for("passive.flowchart.card")
        callout = self._metrics_for("passive.flowchart.callout")
        timestamp = self._metrics_for("passive.flowchart.timestamp")
        isometric_cube = self._metrics_for("passive.flowchart.isometric_cube")

        self.assertEqual((decision.default_width, decision.min_width, decision.min_height), (236.0, 192.0, 128.0))
        self.assertEqual((decision.title_left_margin, decision.title_right_margin), (66.0, 66.0))
        self.assertEqual((document.default_width, document.min_height, document.body_bottom_margin), (228.0, 104.0, 24.0))
        self.assertEqual((connector.default_width, connector.min_width, connector.min_height), (108.0, 92.0, 92.0))
        self.assertEqual((input_output.default_width, input_output.title_left_margin), (236.0, 34.0))
        self.assertEqual((predefined.default_width, predefined.title_left_margin), (236.0, 36.0))
        self.assertEqual((database.default_width, database.min_width, database.min_height), (228.0, 180.0, 128.0))
        self.assertEqual((card.default_width, card.min_width, card.min_height), (132.0, 132.0, 200.0))
        self.assertEqual((callout.default_width, callout.min_width, callout.min_height), (260.0, 196.0, 120.0))
        self.assertEqual((timestamp.default_width, timestamp.min_width, timestamp.min_height), (300.0, 220.0, 72.0))
        self.assertEqual(
            (isometric_cube.default_width, isometric_cube.min_width, isometric_cube.min_height),
            (188.0, 160.0, 160.0),
        )


class FlowchartVisualPolishRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()
        self.model = GraphModel()
        self.workspace = self.model.active_workspace
        self.scene = GraphSceneBridge()
        self.scene.set_workspace(self.model, self.registry, self.workspace.workspace_id)

    def _assert_orthogonal_polyline(self, points: list[dict[str, float]]) -> None:
        self.assertGreaterEqual(len(points), 2)
        for index in range(1, len(points)):
            start = points[index - 1]
            end = points[index]
            self.assertTrue(
                abs(start["x"] - end["x"]) < 0.001 or abs(start["y"] - end["y"]) < 0.001,
                msg=f"segment {index - 1}->{index} is not orthogonal: {start} -> {end}",
            )

    def _assert_monotone_axis(self, points: list[dict[str, float]], axis: str, direction: str) -> None:
        last_value = points[0][axis]
        for point in points[1:]:
            current = point[axis]
            if direction == "increasing":
                self.assertGreaterEqual(current + 0.001, last_value)
            else:
                self.assertLessEqual(current - 0.001, last_value)
            last_value = current

    def test_vertical_flowchart_edges_prefer_pipe_routes(self) -> None:
        source_id = self.scene.add_node_from_type("passive.flowchart.process", 40.0, 40.0)
        target_id = self.scene.add_node_from_type("passive.flowchart.process", 64.0, 250.0)
        edge_id = self.scene.add_edge(source_id, "bottom", target_id, "top")

        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]

        self.assertEqual(edge_payload["route"], "pipe")
        self.assertEqual(edge_payload["source_port_side"], "bottom")
        self.assertEqual(edge_payload["target_port_side"], "top")
        pipe_points = edge_payload["pipe_points"]
        self._assert_orthogonal_polyline(pipe_points)
        self.assertEqual(pipe_points[0], {"x": edge_payload["sx"], "y": edge_payload["sy"]})
        self.assertEqual(pipe_points[-1], {"x": edge_payload["tx"], "y": edge_payload["ty"]})
        self._assert_monotone_axis(pipe_points, "y", "increasing")
        self.assertGreaterEqual(min(point["x"] for point in pipe_points) + 0.001, min(edge_payload["sx"], edge_payload["tx"]))
        self.assertLessEqual(max(point["x"] for point in pipe_points) - 0.001, max(edge_payload["sx"], edge_payload["tx"]))

    def test_offset_vertical_flowchart_edges_stay_inside_the_inter_node_corridor(self) -> None:
        source_id = self.scene.add_node_from_type("passive.flowchart.connector", 250.0, 40.0)
        target_id = self.scene.add_node_from_type("passive.flowchart.document", 125.0, 330.0)
        edge_id = self.scene.add_edge(source_id, "bottom", target_id, "top")

        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]
        pipe_points = edge_payload["pipe_points"]

        self.assertEqual(edge_payload["route"], "pipe")
        self.assertEqual(edge_payload["source_port_side"], "bottom")
        self.assertEqual(edge_payload["target_port_side"], "top")
        self._assert_orthogonal_polyline(pipe_points)
        self._assert_monotone_axis(pipe_points, "y", "increasing")
        self.assertGreaterEqual(min(point["x"] for point in pipe_points) + 0.001, min(edge_payload["sx"], edge_payload["tx"]))
        self.assertLessEqual(max(point["x"] for point in pipe_points) - 0.001, max(edge_payload["sx"], edge_payload["tx"]))

    def test_wide_left_to_right_flowchart_edges_keep_bezier_routes(self) -> None:
        source_id = self.scene.add_node_from_type("passive.flowchart.process", 20.0, 40.0)
        target_id = self.scene.add_node_from_type("passive.flowchart.process", 420.0, 72.0)
        edge_id = self.scene.add_edge(source_id, "right", target_id, "left")

        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]

        self.assertEqual(edge_payload["route"], "bezier")
        self.assertEqual(edge_payload["pipe_points"], [])
        self.assertEqual(edge_payload["source_port_side"], "right")
        self.assertEqual(edge_payload["target_port_side"], "left")
        self.assertGreater(edge_payload["c1x"], edge_payload["sx"])
        self.assertLess(edge_payload["c2x"], edge_payload["tx"])

    def test_edge_path_mode_pipe_forces_orthogonal_route(self) -> None:
        source_id = self.scene.add_node_from_type("passive.flowchart.process", 20.0, 40.0)
        target_id = self.scene.add_node_from_type("passive.flowchart.process", 420.0, 72.0)
        edge_id = self.scene.add_edge(source_id, "right", target_id, "left")

        self.scene.set_edge_visual_style(edge_id, {"path_mode": "pipe"})
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]

        self.assertEqual(edge_payload["path_mode"], "pipe")
        self.assertEqual(edge_payload["route"], "pipe")
        self._assert_orthogonal_polyline(edge_payload["pipe_points"])

    def test_edge_path_mode_bezier_overrides_auto_pipe_route(self) -> None:
        source_id = self.scene.add_node_from_type("passive.flowchart.process", 40.0, 40.0)
        target_id = self.scene.add_node_from_type("passive.flowchart.process", 64.0, 250.0)
        edge_id = self.scene.add_edge(source_id, "bottom", target_id, "top")

        self.scene.set_edge_visual_style(edge_id, {"path_mode": "bezier"})
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]

        self.assertEqual(edge_payload["path_mode"], "bezier")
        self.assertEqual(edge_payload["route"], "bezier")
        self.assertEqual(edge_payload["pipe_points"], [])

    def test_cardinal_flowchart_edges_publish_side_normals_and_oriented_leads(self) -> None:
        decision_id = self.scene.add_node_from_type("passive.flowchart.decision", 40.0, 40.0)
        right_target = self.scene.add_node_from_type("passive.flowchart.process", 340.0, 96.0)
        bottom_target = self.scene.add_node_from_type("passive.flowchart.process", 120.0, 320.0)
        edge_right = self.scene.add_edge(decision_id, "right", right_target, "left")
        edge_bottom = self.scene.add_edge(decision_id, "bottom", bottom_target, "top")

        payload = {item["edge_id"]: item for item in self.scene.edges_model}

        self.assertEqual(payload[edge_right]["source_port_side"], "right")
        self.assertEqual(payload[edge_right]["target_port_side"], "left")
        self.assertEqual((payload[edge_right]["source_normal_x"], payload[edge_right]["source_normal_y"]), (1.0, 0.0))
        self.assertGreater(payload[edge_right]["c1x"], payload[edge_right]["sx"])

        self.assertEqual(payload[edge_bottom]["route"], "pipe")
        self.assertEqual(payload[edge_bottom]["source_port_side"], "bottom")
        self.assertEqual(payload[edge_bottom]["target_port_side"], "top")
        self.assertEqual((payload[edge_bottom]["source_normal_x"], payload[edge_bottom]["source_normal_y"]), (0.0, 1.0))
        self.assertEqual(payload[edge_bottom]["pipe_points"][0], {"x": payload[edge_bottom]["sx"], "y": payload[edge_bottom]["sy"]})
        self.assertEqual(payload[edge_bottom]["pipe_points"][-1], {"x": payload[edge_bottom]["tx"], "y": payload[edge_bottom]["ty"]})

    def test_mixed_flowchart_pipe_routes_do_not_add_redundant_reverse_legs(self) -> None:
        bottom_left_source_id = self.scene.add_node_from_type("passive.flowchart.process", 250.0, 40.0)
        bottom_left_target_id = self.scene.add_node_from_type("passive.flowchart.process", 125.0, 330.0)
        right_top_source_id = self.scene.add_node_from_type("passive.flowchart.process", 40.0, 240.0)
        right_top_target_id = self.scene.add_node_from_type("passive.flowchart.process", 260.0, 60.0)

        bottom_left_edge_id = self.scene.add_edge(bottom_left_source_id, "bottom", bottom_left_target_id, "left")
        right_top_edge_id = self.scene.add_edge(right_top_source_id, "right", right_top_target_id, "top")
        payload = {item["edge_id"]: item for item in self.scene.edges_model}

        bottom_left_points = payload[bottom_left_edge_id]["pipe_points"]
        right_top_points = payload[right_top_edge_id]["pipe_points"]

        self.assertEqual(payload[bottom_left_edge_id]["route"], "pipe")
        self.assertEqual(payload[right_top_edge_id]["route"], "pipe")
        self._assert_orthogonal_polyline(bottom_left_points)
        self._assert_orthogonal_polyline(right_top_points)
        self.assertLessEqual(len(bottom_left_points), 5)
        self.assertLessEqual(len(right_top_points), 5)


class FlowchartVisualPolishQmlTests(unittest.TestCase):
    def _run_qml_probe(self, label: str, body: str) -> None:
        run_qml_probe(
            self,
            label,
            """
            from pathlib import Path

            from PyQt6.QtCore import QObject, QUrl
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtQuick import QQuickItem
            from PyQt6.QtWidgets import QApplication

            from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
            from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
            from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
            from ea_node_editor.ui_qml.surface_contracts import surface_spec_payload_for_values
            from ea_node_editor.ui_qml.theme_bridge import ThemeBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            engine.rootContext().setContextProperty("themeBridge", ThemeBridge(theme_id="stitch_dark"))
            engine.rootContext().setContextProperty("graphThemeBridge", GraphThemeBridge(theme_id="graph_stitch_dark"))

            repo_root = Path.cwd()
            components_dir = repo_root / "ea_node_editor" / "ui_qml" / "components"
            graph_canvas_qml_path = components_dir / "GraphCanvas.qml"

            def _graph_canvas_initial_properties(path, initial_properties):
                normalized = dict(initial_properties)
                if path != graph_canvas_qml_path:
                    return normalized, []
                if "canvasStateBridge" in normalized or "canvasCommandBridge" in normalized:
                    refs = [
                        normalized.get("canvasStateBridge"),
                        normalized.get("canvasCommandBridge"),
                    ]
                    return normalized, [ref for ref in refs if ref is not None]
                view_bridge = normalized.pop("viewBridge", None)
                state_bridge = GraphCanvasStateBridge(view_bridge=view_bridge)
                command_bridge = GraphCanvasCommandBridge(view_bridge=view_bridge)
                normalized["canvasStateBridge"] = state_bridge
                normalized["canvasCommandBridge"] = command_bridge
                refs = [state_bridge, command_bridge]
                if view_bridge is not None:
                    refs.append(view_bridge)
                return normalized, refs

            def create_component(path, initial_properties):
                initial_properties, persistent_refs = _graph_canvas_initial_properties(path, initial_properties)
                component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
                if component.status() != QQmlComponent.Status.Ready:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to load {path.name}:\\n{errors}")
                if hasattr(component, "createWithInitialProperties"):
                    obj = component.createWithInitialProperties(initial_properties)
                else:
                    obj = component.create()
                    for key, value in initial_properties.items():
                        obj.setProperty(key, value)
                if obj is None:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to instantiate {path.name}:\\n{errors}")
                if persistent_refs:
                    setattr(obj, "_graph_canvas_refs", persistent_refs)
                app.processEvents()
                return obj

            def named_child_items(root, object_name):
                matches = []

                def visit(item):
                    if not isinstance(item, QQuickItem):
                        return
                    if item.objectName() == object_name:
                        matches.append(item)
                    for child in item.childItems():
                        visit(child)

                visit(root)
                return matches

            def flowchart_payload(variant, *, title="Decision", display_name="Decision", properties=None, visual_style=None):
                resolved_properties = {
                    "title": title,
                    "body": "Review the incoming data and choose the next branch.",
                }
                if properties:
                    resolved_properties.update(properties)
                resolved_visual_style = {}
                if visual_style:
                    resolved_visual_style.update(visual_style)
                return {
                    "node_id": "node_flowchart_visual_polish",
                    "type_id": "tests.flowchart_visual_polish",
                    "title": title,
                    "display_name": display_name,
                    "x": 120.0,
                    "y": 120.0,
                    "width": 236.0,
                    "height": 128.0,
                    "accent": "#2F89FF",
                    "collapsed": False,
                    "selected": False,
                    "runtime_behavior": "passive",
                    "surface_family": "flowchart",
                    "surface_variant": variant,
                    "surface_spec": surface_spec_payload_for_values(
                        type_id="tests.flowchart_visual_polish",
                        family="flowchart",
                        variant=variant,
                    ),
                    "visual_style": resolved_visual_style,
                    "can_enter_scope": False,
                    "ports": [
                        {
                            "key": "top",
                            "label": "top",
                            "direction": "neutral",
                            "kind": "flow",
                            "data_type": "flow",
                            "exposed": True,
                            "connected": False,
                        },
                        {
                            "key": "right",
                            "label": "right",
                            "direction": "neutral",
                            "kind": "flow",
                            "data_type": "flow",
                            "exposed": True,
                            "connected": False,
                        },
                        {
                            "key": "bottom",
                            "label": "bottom",
                            "direction": "neutral",
                            "kind": "flow",
                            "data_type": "flow",
                            "exposed": True,
                            "connected": False,
                        },
                        {
                            "key": "left",
                            "label": "left",
                            "direction": "neutral",
                            "kind": "flow",
                            "data_type": "flow",
                            "exposed": True,
                            "connected": False,
                        },
                    ],
                    "inline_properties": [],
                    "properties": resolved_properties,
                }
            """,
            body,
        )

    def test_flowchart_drop_preview_matches_family_and_hides_port_labels(self) -> None:
        self._run_qml_probe(
            "flowchart-drop-preview-polish",
            """
            view = ViewportBridge()
            view.set_viewport_size(1280.0, 720.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "viewBridge": view,
                    "width": 1280.0,
                    "height": 720.0,
                },
            )
            canvas.setProperty("dropPreviewNodePayload", flowchart_payload("document"))
            canvas.setProperty("dropPreviewScreenX", 180.0)
            canvas.setProperty("dropPreviewScreenY", 220.0)
            app.processEvents()
            drop_preview = canvas.findChild(QObject, "graphCanvasDropPreview")
            assert drop_preview is not None
            assert bool(drop_preview.property("previewIsFlowchart"))
            assert not bool(drop_preview.property("previewUsesHostChrome"))
            assert not bool(drop_preview.property("previewPortLabelsEnabled"))
            assert len(named_child_items(drop_preview, "graphFlowchartSilhouette")) >= 1
            assert len(named_child_items(drop_preview, "graphFlowchartVectorShape")) >= 1
            assert len(named_child_items(drop_preview, "graphCanvasDropPreviewInputPortDot")) == 2
            assert len(named_child_items(drop_preview, "graphCanvasDropPreviewOutputPortDot")) == 2
            assert not any(item.isVisible() for item in named_child_items(drop_preview, "graphCanvasDropPreviewInputPortLabel"))
            assert not any(item.isVisible() for item in named_child_items(drop_preview, "graphCanvasDropPreviewOutputPortLabel"))

            window = canvas.window()
            canvas.setParentItem(None)
            canvas.deleteLater()
            app.processEvents()
            if window is not None:
                window.close()
                window.deleteLater()
                app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )


if __name__ == "__main__":
    unittest.main()
