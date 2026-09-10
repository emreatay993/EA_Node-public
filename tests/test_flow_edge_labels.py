from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time
import unittest
from unittest.mock import patch

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.decorators import in_port, node_type, out_port
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ISOLATED_SUBPROCESS_TIMEOUT_SECONDS = 180


def _normalize_partial_process_output(output: str | bytes | None) -> str:
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    return output.strip() if output else ""


def _run_isolated_probe(label: str, script: str, env: dict[str, str]) -> None:
    command = [sys.executable, "-c", script]
    started_at = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=_ISOLATED_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started_at
        stdout = _normalize_partial_process_output(exc.stdout)
        stderr = _normalize_partial_process_output(exc.stderr)
        raise AssertionError(
            f"{label} probe timed out after "
            f"{_ISOLATED_SUBPROCESS_TIMEOUT_SECONDS} seconds (elapsed={elapsed:.3f}s)\n"
            f"command: {command!r}\n"
            f"stdout: {stdout or '<empty>'}\n"
            f"stderr: {stderr or '<empty>'}"
        ) from exc

    if result.returncode != 0:
        details = "\n".join(
            part for part in (result.stdout.strip(), result.stderr.strip()) if part
        )
        raise AssertionError(
            f"{label} probe failed with exit code {result.returncode}\n{details}"
        )


class IsolatedProbeRunnerTests(unittest.TestCase):
    def test_timeout_reports_limit_and_normalized_partial_output(self) -> None:
        env = {"QT_QPA_PLATFORM": "offscreen"}
        timeout = subprocess.TimeoutExpired(
            cmd=[sys.executable, "-c", "pass"],
            timeout=_ISOLATED_SUBPROCESS_TIMEOUT_SECONDS,
            output=b"  partial stdout\r\n",
            stderr="  partial stderr\n",
        )

        monotonic_values = iter((100.0, 280.25))
        with (
            patch.object(time, "monotonic", side_effect=lambda: next(monotonic_values, 280.25)),
            patch.object(subprocess, "run", side_effect=timeout) as run,
        ):
            with self.assertRaises(AssertionError) as raised:
                _run_isolated_probe("mock", "pass", env)

        self.assertEqual(
            str(raised.exception),
            "mock probe timed out after 180 seconds (elapsed=180.250s)\n"
            f"command: {[sys.executable, '-c', 'pass']!r}\n"
            "stdout: partial stdout\n"
            "stderr: partial stderr",
        )
        run.assert_called_once_with(
            [sys.executable, "-c", "pass"],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )


@node_type(
    type_id="tests.flow_edge_label_node",
    display_name="Flow Edge Label Node",
    category_path=("Tests",),
    icon="branch",
    ports=(
        in_port("data_in"),
        out_port("data_out"),
        in_port("flow_in", kind="flow"),
        out_port("flow_out", kind="flow"),
    ),
    properties=(),
    runtime_behavior="passive",
    surface_family="annotation",
    surface_variant="sticky_note",
)
class _FlowEdgeLabelNode:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


@node_type(
    type_id="tests.compile_wire_node",
    display_name="Compile Wire Node",
    category_path=("Tests",),
    icon="branch",
    ports=(in_port("data_in"), out_port("data_out")),
    properties=(),
    runtime_behavior="compile_only",
)
class _CompileWireNode:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


def _build_registry() -> NodeRegistry:
    registry = build_default_registry()
    registry.register(_FlowEdgeLabelNode)
    registry.register(_CompileWireNode)
    return registry


class FlowEdgeLabelPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _build_registry()
        self.model = GraphModel()
        self.workspace = self.model.active_workspace
        self.scene = GraphSceneBridge()
        self.scene.set_workspace(self.model, self.registry, self.workspace.workspace_id)

    def test_edge_layer_splits_viewport_style_label_and_renderer_helpers(self) -> None:
        graph_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph"
        edge_layer_path = graph_dir / "EdgeLayer.qml"
        edge_layer_text = edge_layer_path.read_text(encoding="utf-8")
        helper_paths = {
            "EdgeCanvasLayer.qml": graph_dir / "EdgeCanvasLayer.qml",
            "EdgePaintPolicy.js": graph_dir / "EdgePaintPolicy.js",
            "EdgeFlowLabelLayer.qml": graph_dir / "EdgeFlowLabelLayer.qml",
            "EdgeHitTestOverlay.qml": graph_dir / "EdgeHitTestOverlay.qml",
            "GraphEdgeFloatingToolbar.qml": graph_dir
            / "overlay"
            / "GraphEdgeFloatingToolbar.qml",
            "EdgeViewportMath.js": graph_dir / "EdgeViewportMath.js",
            "EdgeSnapshotCache.js": graph_dir / "EdgeSnapshotCache.js",
        }

        self.assertIn('"EdgeViewportMath.js" as EdgeViewportMath', edge_layer_text)
        self.assertIn('"EdgePaintPolicy.js" as EdgePaintPolicy', edge_layer_text)
        self.assertIn('"EdgeSnapshotCache.js" as EdgeSnapshotCache', edge_layer_text)
        self.assertIn("EdgeCanvasLayer {", edge_layer_text)
        self.assertIn("EdgeFlowLabelLayer {", edge_layer_text)
        self.assertIn("EdgeHitTestOverlay {", edge_layer_text)
        self.assertIn(
            "EdgeSnapshotCache.refreshVisibleEdgeSnapshots(root, edgeCanvasLayer, flowLabelLayer)",
            edge_layer_text,
        )
        self.assertIn(
            "return EdgeSnapshotCache.edgeAtScreen(root, edgeCanvasLayer, flowLabelLayer, screenX, screenY);",
            edge_layer_text,
        )
        self.assertNotIn("id: viewportMath", edge_layer_text)
        self.assertNotIn("id: flowStylePolicy", edge_layer_text)
        self.assertNotIn("id: edgeRenderer", edge_layer_text)
        self.assertNotIn("id: edgeCrossingPolicy", edge_layer_text)
        self.assertNotIn("id: flowLabelPolicy", edge_layer_text)

        for helper_name, helper_path in helper_paths.items():
            with self.subTest(helper=helper_name):
                self.assertTrue(
                    helper_path.exists(), msg=f"missing helper {helper_name}"
                )

    def test_edge_paint_policy_is_stateless_and_renderer_neutral(self) -> None:
        graph_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph"
        policy_text = (graph_dir / "EdgePaintPolicy.js").read_text(encoding="utf-8")
        edge_layer_text = (graph_dir / "EdgeLayer.qml").read_text(encoding="utf-8")
        canvas_text = (graph_dir / "EdgeCanvasLayer.qml").read_text(encoding="utf-8")
        retained_text = (graph_dir / "EdgeRetainedLayer.qml").read_text(encoding="utf-8")
        snapshot_text = (graph_dir / "EdgeSnapshotCache.js").read_text(encoding="utf-8")
        label_text = (graph_dir / "EdgeFlowLabelLayer.qml").read_text(encoding="utf-8")
        math_text = (graph_dir / "EdgeMath.js").read_text(encoding="utf-8")
        scenegraph_text = (graph_dir / "EdgeScenegraphLayer.qml").read_text(
            encoding="utf-8"
        )

        self.assertTrue(policy_text.startswith(".pragma library\n"))
        for forbidden in ("Item {", "QtObject {", "Timer {", "Loader {"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, policy_text)
        self.assertNotIn("canvasLayer", policy_text)
        self.assertNotIn("property Item canvasLayer", retained_text)
        self.assertNotIn("root.canvasLayer", retained_text)
        self.assertIn(
            "EdgePaintPolicy.standardEdgePaintState(", retained_text
        )
        self.assertIn("EdgeMath.edgeAnchor(sourceGeometry, 0.5)", retained_text)
        self.assertIn('"EdgePaintPolicy.js" as EdgePaintPolicy', canvas_text)
        self.assertIn('"EdgePaintPolicy.js" as EdgePaintPolicy', edge_layer_text)
        self.assertIn('.import "EdgePaintPolicy.js" as EdgePaintPolicy', snapshot_text)
        self.assertIn('"EdgePaintPolicy.js" as EdgePaintPolicy', label_text)
        self.assertIn("function edgeAnchor(geometry, fraction)", math_text)
        self.assertNotIn("function edgeAnchor(geometry, fraction)", canvas_text)
        self.assertEqual(
            scenegraph_text,
            """import QtQuick 2.15

Item {
    id: root
    objectName: \"graphCanvasEdgeScenegraphLayer\"
    property Item edgeLayer: null
    readonly property bool rendererSupported: false
    property real profileLastPaintMs: 0.0
    property int profilePaintCount: 0
    readonly property string fallbackReason: \"native_scenegraph_renderer_unavailable\"

    function requestScenegraphPaint() {
        root.profileLastPaintMs = 0.0;
        root.profilePaintCount += 1;
    }
}
""",
        )

    def test_data_tree_wire_contract_threads_previews_and_renderer_metadata(
        self,
    ) -> None:
        graph_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph"
        graph_canvas_dir = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph_canvas"
        )
        root_layers_text = (graph_canvas_dir / "GraphCanvasRootLayers.qml").read_text(
            encoding="utf-8"
        )
        input_layers_text = (graph_canvas_dir / "GraphCanvasInputLayers.qml").read_text(
            encoding="utf-8"
        )
        edge_layer_text = (graph_dir / "EdgeLayer.qml").read_text(encoding="utf-8")
        canvas_layer_text = (graph_dir / "EdgeCanvasLayer.qml").read_text(
            encoding="utf-8"
        )
        retained_layer_text = (graph_dir / "EdgeRetainedLayer.qml").read_text(
            encoding="utf-8"
        )
        policy_text = (graph_dir / "EdgePaintPolicy.js").read_text(encoding="utf-8")
        hit_overlay_text = (graph_dir / "EdgeHitTestOverlay.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "outputPreviewLookup: root.canvasItem && root.canvasItem.executionFacts",
            root_layers_text,
        )
        self.assertIn("property var outputPreviewLookup: ({})", edge_layer_text)
        self.assertIn("function standardEdgeStructure(edgeLayer, edge)", policy_text)
        self.assertIn(
            "function standardEdgeStrokeCount(edge, structure)", policy_text
        )
        self.assertIn(
            '"strokeOffsetsScreenPx": standardEdgeStrokeOffsetsScreenPx(edge, structure)',
            policy_text,
        )
        self.assertIn(
            "retainedEdgeDelegate.edgeEntry.strokeOffsets", retained_layer_text
        )
        self.assertIn("ShapePath.DashLine", retained_layer_text)
        self.assertIn('objectName: "graphEdgeValuePreviewToolTip"', hit_overlay_text)
        self.assertIn("popupType: Popup.Item", hit_overlay_text)
        self.assertIn(
            'marqueeArea.marqueeMode === "edge_selection"', input_layers_text
        )
        self.assertIn('ctx.setLineDash([1, 3])', input_layers_text)
        combined = "\n".join(
            (root_layers_text, edge_layer_text, canvas_layer_text, retained_layer_text)
        )
        self.assertNotIn("progressedExecutionEdgeLookup", combined)
        self.assertNotIn("executionFlash", combined)

    def test_edge_routing_facade_stays_within_packet_budget_and_helper_split(
        self,
    ) -> None:
        ui_qml_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml"
        graph_geometry_dir = ui_qml_dir / "graph_geometry"
        facade_path = ui_qml_dir / "edge_routing.py"
        facade_text = facade_path.read_text(encoding="utf-8")
        helper_paths = {
            "route_endpoints.py": graph_geometry_dir / "route_endpoints.py",
            "route_pipe.py": graph_geometry_dir / "route_pipe.py",
            "route_payload.py": graph_geometry_dir / "route_payload.py",
            "route_styles.py": graph_geometry_dir / "route_styles.py",
        }

        for snippet in (
            "graph_geometry.route_endpoints",
            "graph_geometry.route_payload",
            "graph_geometry.route_pipe",
            "graph_geometry.route_styles",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, facade_text)

        for helper_name, helper_path in helper_paths.items():
            with self.subTest(helper=helper_name):
                self.assertTrue(
                    helper_path.exists(), msg=f"missing helper {helper_name}"
                )

    def test_flow_edge_payload_normalizes_render_metadata(self) -> None:
        source_id = self.scene.add_node_from_type(
            "tests.flow_edge_label_node", 20.0, 20.0
        )
        target_id = self.scene.add_node_from_type(
            "tests.flow_edge_label_node", 340.0, 110.0
        )
        edge_id = self.scene.add_edge(source_id, "flow_out", target_id, "flow_in")
        self.workspace.edges[edge_id].label = "Primary path"
        self.workspace.edges[edge_id].visual_style = {
            "stroke": "dashed",
            "stroke_color": "#335577",
            "stroke_width": "3.5",
            "arrow": {"kind": "open"},
            "label_text_color": "#f0f4fb",
            "label_background_color": "#223344",
        }

        self.scene.refresh_workspace_from_model(self.workspace.workspace_id)

        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}[
            edge_id
        ]
        self.assertEqual(edge_payload["edge_family"], "flow")
        self.assertEqual(edge_payload["label"], "Primary path")
        self.assertEqual(
            edge_payload["flow_style"],
            {
                "stroke_color": "#335577",
                "stroke_width": 3.5,
                "stroke_pattern": "dashed",
                "arrow_head": "open",
                "label_text_color": "#f0f4fb",
                "label_background_color": "#223344",
            },
        )

    def test_active_data_wire_classification_normalizes_display_mode_without_changing_passive_or_flow_edges(
        self,
    ) -> None:
        source_id = self.scene.add_node_from_type("core.trigger", 0.0, 0.0)
        target_id = self.scene.add_node_from_type("core.if", 260.0, 0.0)
        edge_id = self.scene.add_edge(source_id, "output", target_id, "true_value")

        compile_source_id = self.scene.add_node_from_type(
            "tests.compile_wire_node", 0.0, 120.0
        )
        passive_target_id = self.scene.add_node_from_type(
            "tests.flow_edge_label_node", 260.0, 120.0
        )
        compile_edge_id = self.scene.add_edge(
            compile_source_id, "data_out", passive_target_id, "data_in"
        )
        self.workspace.edges[compile_edge_id].visual_style = {
            "display_mode": "unsupported"
        }

        passive_source_id = self.scene.add_node_from_type(
            "tests.flow_edge_label_node", 0.0, 240.0
        )
        passive_data_target_id = self.scene.add_node_from_type(
            "tests.flow_edge_label_node", 260.0, 240.0
        )
        passive_edge_id = self.scene.add_edge(
            passive_source_id, "data_out", passive_data_target_id, "data_in"
        )
        flow_edge_id = self.scene.add_edge(
            passive_source_id, "flow_out", passive_data_target_id, "flow_in"
        )

        self.scene.refresh_workspace_from_model(self.workspace.workspace_id)
        payloads = {item["edge_id"]: item for item in self.scene.edges_model}

        edge_payload = payloads[edge_id]
        self.assertEqual(edge_payload["edge_family"], "standard")
        self.assertEqual(edge_payload["flow_style"], {})
        self.assertEqual(edge_payload["source_port_kind"], "data")
        self.assertEqual(edge_payload["target_port_kind"], "data")
        self.assertEqual(edge_payload["data_access"], "tree")
        self.assertTrue(edge_payload["active_data_wire"])
        self.assertNotIn("stroke_count", edge_payload)
        self.assertEqual(edge_payload["visual_style"]["display_mode"], "default")

        compile_payload = payloads[compile_edge_id]
        self.assertTrue(compile_payload["active_data_wire"])
        self.assertNotIn("stroke_count", compile_payload)
        self.assertEqual(compile_payload["visual_style"]["display_mode"], "default")

        passive_payload = payloads[passive_edge_id]
        self.assertFalse(passive_payload["active_data_wire"])
        self.assertEqual(passive_payload["stroke_count"], 1)

        flow_payload = payloads[flow_edge_id]
        self.assertEqual(flow_payload["edge_family"], "flow")
        self.assertFalse(flow_payload["active_data_wire"])
        self.assertEqual(flow_payload["stroke_count"], 1)

    def test_backward_flow_edges_publish_orthogonal_pipe_polylines(self) -> None:
        source_id = self.scene.add_node_from_type(
            "tests.flow_edge_label_node", 380.0, 130.0
        )
        target_id = self.scene.add_node_from_type(
            "tests.flow_edge_label_node", 40.0, 30.0
        )
        edge_id = self.scene.add_edge(source_id, "flow_out", target_id, "flow_in")

        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}[
            edge_id
        ]
        self.assertEqual(edge_payload["edge_family"], "flow")
        self.assertEqual(edge_payload["route"], "pipe")
        self.assertGreaterEqual(len(edge_payload["pipe_points"]), 4)
        self.assertEqual(
            edge_payload["pipe_points"][0],
            {"x": edge_payload["sx"], "y": edge_payload["sy"]},
        )
        self.assertEqual(
            edge_payload["pipe_points"][-1],
            {"x": edge_payload["tx"], "y": edge_payload["ty"]},
        )
        for index in range(1, len(edge_payload["pipe_points"])):
            start = edge_payload["pipe_points"][index - 1]
            end = edge_payload["pipe_points"][index]
            self.assertTrue(
                abs(start["x"] - end["x"]) < 0.001
                or abs(start["y"] - end["y"]) < 0.001,
                msg=f"segment {index - 1}->{index} is not orthogonal: {start} -> {end}",
            )


class TrackBQmlPreferencePacketBoundaryTests(unittest.TestCase):
    def test_track_b_qml_entrypoint_keeps_edge_gap_break_coverage_packetized(
        self,
    ) -> None:
        module = importlib.import_module("tests.graph_track_b.qml_preference_bindings")
        package_root = _REPO_ROOT / "tests" / "graph_track_b"
        entry_text = (package_root / "qml_preference_bindings.py").read_text(
            encoding="utf-8"
        )
        rendering_text = (package_root / "qml_preference_rendering_suite.py").read_text(
            encoding="utf-8"
        )
        performance_text = (
            package_root / "qml_preference_performance_suite.py"
        ).read_text(encoding="utf-8")

        self.assertIn("qml_preference_rendering_suite", entry_text)
        self.assertIn("qml_preference_performance_suite", entry_text)
        self.assertIn(
            "def test_edge_layer_gap_break_marks_only_under_edge_for_pipe_pipe_crossings",
            rendering_text,
        )
        self.assertIn(
            "def test_edge_layer_gap_break_metadata_persists_during_viewport_interaction",
            performance_text,
        )
        self.assertIn(
            "def test_graph_canvas_coalesces_view_state_redraw_requests_per_commit",
            performance_text,
        )
        self.assertEqual(
            {
                base.__module__
                for base in module.GraphCanvasQmlPreferenceBindingTests.__bases__
            },
            {
                "tests.graph_track_b.qml_preference_rendering_suite",
                "tests.graph_track_b.qml_preference_performance_suite",
            },
        )


class FlowEdgeLabelQmlTests(unittest.TestCase):
    def _run_edge_layer_probe(self, label: str, body: str) -> None:
        script = (
            textwrap.dedent(
                """
            from pathlib import Path

            from PyQt6.QtCore import QObject, QPoint, QUrl
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.nodes.decorators import in_port, node_type, out_port
            from ea_node_editor.nodes.registry import NodeRegistry
            from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            @node_type(
                type_id="tests.flow_edge_label_probe_node",
                display_name="Flow Edge Label Probe",
                category="Tests",
                icon="branch",
                ports=(in_port("flow_in", kind="flow"), out_port("flow_out", kind="flow")),
                properties=(),
                runtime_behavior="passive",
                surface_family="annotation",
                surface_variant="sticky_note",
            )
            class _FlowEdgeLabelProbeNode:
                def execute(self, _ctx: ExecutionContext) -> NodeResult:
                    return NodeResult(outputs={})

            def build_registry() -> NodeRegistry:
                registry = build_default_registry()
                registry.register(_FlowEdgeLabelProbeNode)
                return registry

            def to_variant(value):
                return value.toVariant() if hasattr(value, "toVariant") else value

            def snapshot(edge_layer, edge_id):
                result = to_variant(edge_layer._visibleEdgeSnapshot(edge_id))
                assert result is not None, edge_id
                return result

            def refresh(edge_layer):
                edge_layer.requestRedraw()
                app.processEvents()
                return to_variant(edge_layer.property("_visibleEdgeSnapshots"))

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            component = QQmlComponent(
                engine,
                QUrl.fromLocalFile(
                    str(Path.cwd() / "ea_node_editor" / "ui_qml" / "components" / "graph" / "EdgeLayer.qml")
                ),
            )
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError(f"Failed to load EdgeLayer.qml:\\n{errors}")

            view = ViewportBridge()
            view.set_viewport_size(1280.0, 720.0)
            view.centerOn(240.0, 180.0)
            edge_layer = component.createWithInitialProperties(
                {
                    "width": 1280.0,
                    "height": 720.0,
                    "viewBridge": view,
                }
            ) if hasattr(component, "createWithInitialProperties") else component.create()
            if edge_layer is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError(f"Failed to instantiate EdgeLayer.qml:\\n{errors}")
            if not hasattr(component, "createWithInitialProperties"):
                edge_layer.setProperty("width", 1280.0)
                edge_layer.setProperty("height", 720.0)
                edge_layer.setProperty("viewBridge", view)
            app.processEvents()
            """
            )
            + "\n"
            + textwrap.dedent(body)
            + "\napp.processEvents()\napp.processEvents()\nimport os\nos._exit(0)\n"
        )
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
        _run_isolated_probe(label, script, env)

    def _run_qml_probe(self, label: str, body: str) -> None:
        script = (
            textwrap.dedent(
                """
            from pathlib import Path

            from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtQuick import QQuickItem
            from PyQt6.QtTest import QTest
            from PyQt6.QtWidgets import QApplication

            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.nodes.decorators import in_port, node_type, out_port
            from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
            from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
            from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
            from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
            from ea_node_editor.ui_qml.theme_bridge import ThemeBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            @node_type(
                type_id="tests.flow_edge_label_probe_node",
                display_name="Flow Edge Label Probe",
                category="Tests",
                icon="branch",
                ports=(in_port("flow_in", kind="flow"), out_port("flow_out", kind="flow")),
                properties=(),
                runtime_behavior="passive",
                surface_family="annotation",
                surface_variant="sticky_note",
            )
            class _FlowEdgeLabelProbeNode:
                def execute(self, _ctx: ExecutionContext) -> NodeResult:
                    return NodeResult(outputs={})

            def build_registry():
                registry = build_default_registry()
                registry.register(_FlowEdgeLabelProbeNode)
                return registry

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

            def edges_by_id(scene):
                return {item["edge_id"]: item for item in scene.edges_model}

            def to_variant(value):
                return value.toVariant() if hasattr(value, "toVariant") else value

            def assert_edge_screen_hit(edge_layer, edge_id, anchor):
                screen_x = edge_layer.sceneToScreenX(anchor["x"])
                screen_y = edge_layer.sceneToScreenY(anchor["y"])
                normal_x = -anchor["dy"]
                normal_y = anchor["dx"]

                assert edge_layer.edgeAtScreen(screen_x, screen_y) == edge_id
                assert edge_layer.edgeAtScreen(
                    screen_x + normal_x * 6.0,
                    screen_y + normal_y * 6.0,
                ) == edge_id
                assert edge_layer.edgeAtScreen(
                    screen_x + normal_x * 10.0,
                    screen_y + normal_y * 10.0,
                ) == ""

            def assert_flow_label_snapshot_consistency(edge_layer, label_item, edge_id):
                snapshot = to_variant(edge_layer._visibleEdgeSnapshot(edge_id))
                assert snapshot is not None
                assert snapshot["edgeId"] == edge_id
                assert label_item.property("snapshotRevision") == snapshot["revision"]
                assert label_item.property("labelMode") == snapshot["labelMode"]

                label_requested = label_item.property("labelMode") != "hidden"
                geometry = to_variant(label_item.property("geometry"))
                label_anchor_scene = to_variant(label_item.property("labelAnchorScene"))

                if not label_requested:
                    assert geometry is None
                    assert label_anchor_scene is None
                    return snapshot

                assert bool(label_item.property("culledByViewport")) == bool(snapshot["culled"])
                if snapshot["culled"]:
                    assert geometry is None
                    assert label_anchor_scene is None
                    return snapshot

                assert geometry == snapshot["geometry"]
                assert label_anchor_scene == snapshot["labelAnchorScene"]
                expected_screen_x = edge_layer.sceneToScreenX(label_anchor_scene["x"])
                expected_screen_y = edge_layer.sceneToScreenY(label_anchor_scene["y"])
                assert abs(label_item.property("anchorScreenX") - expected_screen_x) < 0.001
                assert abs(label_item.property("anchorScreenY") - expected_screen_y) < 0.001
                return snapshot

            class CanvasShellBridge(QObject):
                graphics_preferences_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self._graphics_graph_label_pixel_size = 10

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

                @pyqtProperty(int, notify=graphics_preferences_changed)
                def graphics_graph_label_pixel_size(self):
                    return int(self._graphics_graph_label_pixel_size)

                @pyqtProperty(bool, constant=True)
                def snap_to_grid_enabled(self):
                    return False

                @pyqtProperty(float, constant=True)
                def snap_grid_size(self):
                    return 20.0

                def set_graphics_graph_label_pixel_size_value(self, value):
                    normalized = max(8, min(int(value), 50))
                    if self._graphics_graph_label_pixel_size == normalized:
                        return
                    self._graphics_graph_label_pixel_size = normalized
                    self.graphics_preferences_changed.emit()

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            engine.rootContext().setContextProperty("themeBridge", ThemeBridge(theme_id="stitch_dark"))
            engine.rootContext().setContextProperty("graphThemeBridge", GraphThemeBridge(theme_id="graph_stitch_dark"))

            graph_canvas_qml_path = Path.cwd() / "ea_node_editor" / "ui_qml" / "components" / "GraphCanvas.qml"

            component = QQmlComponent(engine, QUrl.fromLocalFile(str(graph_canvas_qml_path)))
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError(f"Failed to load GraphCanvas.qml:\\n{errors}")

            model = GraphModel()
            scene = GraphSceneBridge()
            scene.set_workspace(model, build_registry(), model.active_workspace.workspace_id)
            source_id = scene.add_node_from_type("tests.flow_edge_label_probe_node", 40.0, 30.0)
            target_id = scene.add_node_from_type("tests.flow_edge_label_probe_node", 380.0, 130.0)
            edge_id = scene.add_edge(source_id, "flow_out", target_id, "flow_in")
            scene.set_edge_label(edge_id, "Primary path")
            scene.set_edge_visual_style(
                edge_id,
                {
                    "stroke_pattern": "dashed",
                    "arrow_head": "open",
                    "stroke_width": 3,
                    "stroke_color": "#335577",
                    "label_text_color": "#f0f4fb",
                    "label_background_color": "#223344",
                },
            )

            view = ViewportBridge()
            view.set_viewport_size(1280.0, 720.0)
            view.centerOn(240.0, 90.0)
            shell_bridge = CanvasShellBridge()
            canvas_state_bridge = GraphCanvasStateBridge(
                session_state=shell_bridge,
                snap_to_grid_changed_signal=getattr(
                    shell_bridge, "snap_to_grid_changed", None
                ),
                snap_grid_size=float(getattr(shell_bridge, "snap_grid_size", 20.0)),
                app_preferences_source=shell_bridge,
                graphics_source=shell_bridge,
                scene_bridge=scene,
                view_bridge=view,
            )
            canvas_command_bridge = GraphCanvasCommandBridge(
                search_scope_controller=shell_bridge,
                app_preferences_source=shell_bridge,
                run_controller=shell_bridge,
                inspector_source=shell_bridge,
                library_source=shell_bridge,
                workspace_edit_controller=shell_bridge,
                workspace_drop_connect_controller=shell_bridge,
                scene_bridge=scene,
                view_bridge=view,
            )

            canvas = component.createWithInitialProperties(
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 1280.0,
                    "height": 720.0,
                }
            ) if hasattr(component, "createWithInitialProperties") else component.create()
            if canvas is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError(f"Failed to instantiate GraphCanvas.qml:\\n{errors}")
            if not hasattr(component, "createWithInitialProperties"):
                canvas.setProperty("canvasStateBridge", canvas_state_bridge)
                canvas.setProperty("canvasCommandBridge", canvas_command_bridge)
                canvas.setProperty("width", 1280.0)
                canvas.setProperty("height", 720.0)
            app.processEvents()
            edge_layer = canvas.findChild(QObject, "graphCanvasEdgeLayer")
            if edge_layer is None:
                raise AssertionError("graphCanvasEdgeLayer not found")

            frame_scheduler = canvas.findChild(QObject, "graphCanvasFrameScheduler")

            def settle_canvas_redraw():
                app.processEvents()
                if frame_scheduler is not None and hasattr(frame_scheduler, "flushPendingRedraws"):
                    frame_scheduler.flushPendingRedraws()
                app.processEvents()
                QTest.qWait(1)
                app.processEvents()
            """
            )
            + "\n"
            + textwrap.dedent(body)
            + "\napp.processEvents()\napp.processEvents()\nimport os\nos._exit(0)\n"
        )
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
        _run_isolated_probe(label, script, env)

    def test_active_data_wire_renderers_match_structure_display_selection_and_error_matrix(
        self,
    ) -> None:
        self._run_edge_layer_probe(
            "active-data-wire-renderers",
            """
            from PyQt6.QtQuick import QQuickWindow
            from PyQt6.QtTest import QTest

            window = QQuickWindow()
            window.resize(1280, 720)
            edge_layer.setParentItem(window.contentItem())
            window.show()
            app.processEvents()

            def bezier_edge(
                edge_id,
                source_node_id,
                y,
                *,
                access="item",
                enabled=True,
                warning=False,
                flow=False,
                active=True,
                display_mode="default",
            ):
                edge = {
                    "edge_id": edge_id,
                    "source_node_id": source_node_id,
                    "source_port_key": "out",
                    "target_node_id": edge_id + "_target",
                    "target_port_key": "in",
                    "source_port_kind": "flow" if flow else "data",
                    "target_port_kind": "flow" if flow else "data",
                    "edge_family": "flow" if flow else "standard",
                    "enabled": enabled,
                    "data_access": access,
                    "active_data_wire": bool(active and not flow),
                    "label": "",
                    "visual_style": {"display_mode": display_mode},
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
                    "sx": 80.0,
                    "sy": y,
                    "tx": 320.0,
                    "ty": y,
                    "c1x": 152.0,
                    "c1y": y,
                    "c2x": 248.0,
                    "c2y": y,
                    "route": "bezier",
                    "pipe_points": [],
                    "color": "#D94F4F" if warning else "#7AA8FF",
                    "data_type_warning": warning,
                }
                if not edge["active_data_wire"]:
                    edge["stroke_count"] = {"item": 1, "list": 2, "tree": 3}[access]
                return edge

            standard_edges = [
                bezier_edge("item", "item_source", 80.0),
                bezier_edge("faint_list", "faint_list_source", 120.0, access="list", display_mode="faint"),
                bezier_edge("tree", "tree_source", 160.0, access="tree"),
                bezier_edge("empty", "empty_source", 200.0, access="tree"),
                bezier_edge("disabled", "disabled_source", 240.0, access="list", enabled=False),
                bezier_edge("selected_hidden", "selected_hidden_source", 280.0, access="tree", display_mode="hidden"),
                bezier_edge("passive", "passive_source", 320.0, access="list", active=False),
                bezier_edge("passive_disabled", "passive_disabled_source", 340.0, enabled=False, active=False),
                bezier_edge("replacement_hidden", "replacement_source", 360.0, access="tree", display_mode="hidden"),
                bezier_edge("selected_disabled", "selected_disabled_source", 380.0, enabled=False),
            ]
            canvas_only_edges = [
                bezier_edge("hidden", "hidden_source", 400.0, display_mode="hidden"),
                bezier_edge("invalid", "invalid_source", 440.0, warning=True),
                bezier_edge("selected_endpoint", "selected_source", 480.0, access="list"),
                bezier_edge("selected_invalid", "selected_source", 520.0, access="tree", warning=True),
                bezier_edge("flow", "flow_source", 560.0, flow=True, active=False),
                bezier_edge("flow_disabled", "flow_disabled_source", 600.0, flow=True, enabled=False, active=False),
            ]
            edge_layer.setProperty(
                "outputPreviewLookup",
                {
                    "item_source": {"out": {
                        "state": "current",
                        "tooltip_text": "Current\\nCurrent item",
                        "rows": [
                            {"kind": "branch", "path": "0"},
                            {"kind": "item", "path": "0", "index": 0, "text": "Current item"},
                        ],
                    }},
                    "faint_list_source": {"out": {
                        "state": "current",
                        "tooltip_text": "Current\\nList: 3 items\\n[0] A\\n[1] B\\n[2] C",
                        "rows": [
                            {"kind": "branch", "path": "0"},
                            {"kind": "item", "path": "0", "index": 0, "text": "A"},
                            {"kind": "item", "path": "0", "index": 1, "text": "B"},
                            {"kind": "item", "path": "0", "index": 2, "text": "C"},
                        ],
                    }},
                    "tree_source": {"out": {
                        "state": "current",
                        "tooltip_text": "Current\\nTree: 2 branches, 2 items\\n{0}\\n  [0] A\\n{1}\\n  [0] B",
                        "rows": [
                            {"kind": "branch", "path": "0"},
                            {"kind": "item", "path": "0", "index": 0, "text": "A"},
                            {"kind": "branch", "path": "1"},
                            {"kind": "item", "path": "1", "index": 0, "text": "B"},
                        ],
                    }},
                    "empty_source": {"out": {"state": "empty", "tooltip_text": "Empty"}},
                    "disabled_source": {"out": {"state": "current", "tooltip_text": "Current"}},
                    "selected_hidden_source": {"out": {"state": "current", "tooltip_text": "Selected"}},
                    "passive_source": {"out": {"state": "current", "tooltip_text": "Passive"}},
                    "passive_disabled_source": {"out": {"state": "current", "tooltip_text": "Passive disabled"}},
                    "replacement_source": {"out": {"state": "current", "tooltip_text": "Replacing"}},
                    "selected_disabled_source": {"out": {"state": "current", "tooltip_text": "Selected disabled"}},
                    "hidden_source": {"out": {"state": "current", "tooltip_text": "Hidden"}},
                    "invalid_source": {"out": {"state": "empty", "tooltip_text": "Empty"}},
                    "selected_source": {"out": {"state": "current", "tooltip_text": "Current"}},
                },
            )
            edge_layer.setProperty("selectedEdgeIds", ["selected_hidden", "selected_disabled"])
            edge_layer.setProperty("selectedNodeIds", ["selected_source"])
            edge_layer.setProperty("replacementPreviewEdgeIds", ["replacement_hidden"])
            view.set_zoom(0.5)
            app.processEvents()

            def paint(edge_id):
                diagnostics = to_variant(edge_layer.property("activeEdgePaintDiagnosticsByEdgeId")) or {}
                if not isinstance(diagnostics, dict):
                    diagnostics = dict(diagnostics)
                value = to_variant(diagnostics.get(edge_id))
                return value if isinstance(value, dict) else (dict(value) if value is not None else None)

            def color_name(value):
                return value.name().lower() if hasattr(value, "name") else str(value).lower()

            def settle_renderer(renderer, edges):
                edge_layer.setProperty("edgeRendererPreference", renderer)
                edge_layer.setProperty("edges", edges)
                expected_ids = [edge["edge_id"] for edge in edges]
                for _attempt in range(30):
                    refresh(edge_layer)
                    QTest.qWait(5)
                    app.processEvents()
                    if str(edge_layer.property("edgeRendererKind")) == renderer and all(
                        paint(edge_id) is not None for edge_id in expected_ids
                    ):
                        return
                raise AssertionError((
                    renderer,
                    edge_layer.property("edgeRendererKind"),
                    [edge_id for edge_id in expected_ids if paint(edge_id) is None],
                ))

            for renderer, edges in (
                ("retained_qml", list(standard_edges)),
                ("canvas", list(standard_edges) + canvas_only_edges),
            ):
                settle_renderer(renderer, edges)

                item_paint = paint("item")
                assert item_paint["activeDataWire"] is True
                assert item_paint["dataAccess"] == "item"
                assert item_paint["displayMode"] == "default"
                assert item_paint["structure"] == "single"
                assert int(item_paint["strokeCount"]) == 1
                assert len(item_paint["strokeOffsetsScreenPx"]) == 1
                assert len(item_paint["dashPatternScreenPx"]) == 0
                assert color_name(item_paint["baseColor"]) == color_name(
                    edge_layer.property("activeDefaultStrokeColor")
                )
                assert color_name(item_paint["strokeColor"]) == color_name(
                    edge_layer.property("activeDefaultStrokeColor")
                )
                assert abs(float(item_paint["strokeWidthScreenPx"]) - 2.0) < 0.001

                faint_paint = paint("faint_list")
                assert faint_paint["structure"] == "list"
                assert faint_paint["displayMode"] == "faint"
                assert int(faint_paint["strokeCount"]) == 1
                assert list(faint_paint["dashPatternScreenPx"]) == [1.0, 4.0]
                assert abs(float(faint_paint["strokeAlpha"]) - 0.30) < 0.001

                tree_paint = paint("tree")
                assert tree_paint["structure"] == "tree"
                assert int(tree_paint["strokeCount"]) == 1
                assert list(tree_paint["dashPatternScreenPx"]) == [8.0, 5.0]

                empty_paint = paint("empty")
                assert empty_paint["structure"] == "empty"
                assert len(empty_paint["strokeOffsetsScreenPx"]) == 2
                assert len(empty_paint["dashPatternScreenPx"]) == 0
                assert empty_paint["disabledMarkerVisible"] is False
                assert abs(float(empty_paint["strokeAlpha"]) - 1.0) < 0.001

                disabled_paint = paint("disabled")
                assert disabled_paint["structure"] == "list"
                assert disabled_paint["disabledMarkerVisible"] is True
                assert list(disabled_paint["dashPatternScreenPx"]) == [1.0, 4.0]
                assert color_name(disabled_paint["disabledMarkerColor"]) == color_name(
                    edge_layer.property("dangerStrokeColor")
                )
                assert color_name(edge_layer.property("dangerStrokeColor")) == "#ff543e"
                assert abs(float(disabled_paint["disabledMarkerAlpha"]) - 1.0) < 0.001
                assert abs(float(disabled_paint["strokeAlpha"]) - 1.0) < 0.001

                selected_disabled_paint = paint("selected_disabled")
                assert selected_disabled_paint["disabledMarkerVisible"] is True
                assert color_name(selected_disabled_paint["disabledMarkerColor"]) == "#75b4e7"
                assert abs(float(selected_disabled_paint["disabledMarkerAlpha"]) - 1.0) < 0.001

                selected_hidden_paint = paint("selected_hidden")
                assert selected_hidden_paint["selected"] is True
                assert selected_hidden_paint["displayMode"] == "hidden"
                assert selected_hidden_paint["bodyVisible"] is True
                assert selected_hidden_paint["endpointArcsVisible"] is False
                assert selected_hidden_paint["structure"] == "tree"
                assert abs(float(selected_hidden_paint["strokeAlpha"]) - 1.0) < 0.001
                assert color_name(selected_hidden_paint["strokeColor"]) == color_name(
                    edge_layer.property("activeSelectedStrokeColor")
                )
                assert color_name(edge_layer.property("activeSelectedStrokeColor")) == "#75b4e7"
                assert abs(float(selected_hidden_paint["strokeWidthScreenPx"]) - 2.0) < 0.001

                passive_paint = paint("passive")
                assert passive_paint["activeDataWire"] is False
                assert int(passive_paint["strokeCount"]) == 2
                assert abs(float(passive_paint["strokeWidthScreenPx"]) - 1.0) < 0.001
                passive_disabled_paint = paint("passive_disabled")
                assert passive_disabled_paint["activeDataWire"] is False
                assert abs(float(passive_disabled_paint["strokeAlpha"]) - 1.0) < 0.001
                assert passive_disabled_paint["disabledMarkerVisible"] is False

                replacement_paint = paint("replacement_hidden")
                assert replacement_paint["replacementPreviewed"] is True
                assert replacement_paint["displayMode"] == "hidden"
                assert replacement_paint["bodyVisible"] is True
                assert replacement_paint["endpointArcsVisible"] is False
                assert abs(float(replacement_paint["strokeAlpha"]) - 0.30) < 0.001
                assert list(replacement_paint["dashPatternScreenPx"]) == [1.0, 4.0]

                item_tooltip = str(edge_layer.edgeTooltipText("item"))
                assert item_tooltip == "Current item", item_tooltip
                faint_tooltip = str(edge_layer.edgeTooltipText("faint_list"))
                assert faint_tooltip == "List: 3 items\\n[0]  A\\n[1]  B\\n[2]  C", faint_tooltip
                tree_tooltip = str(edge_layer.edgeTooltipText("tree"))
                assert tree_tooltip == "Tree: 2 branches, 2 items\\n{0}\\n  [0]  A\\n{1}\\n  [0]  B", tree_tooltip
                passive_tooltip = str(edge_layer.edgeTooltipText("passive"))
                assert passive_tooltip == "List data\\nPassive", passive_tooltip
                passive_disabled_tooltip = str(edge_layer.edgeTooltipText("passive_disabled"))
                assert passive_disabled_tooltip == "Item data\\nDisabled\\nPassive disabled", passive_disabled_tooltip
                assert " data" not in faint_tooltip
                assert "Current\\n" not in faint_tooltip

                for edge_id, y in (
                    ("item", 80.0),
                    ("faint_list", 120.0),
                    ("tree", 160.0),
                    ("empty", 200.0),
                    ("disabled", 240.0),
                    ("selected_hidden", 280.0),
                ):
                    hit = edge_layer.edgeAtScreen(
                        edge_layer.sceneToScreenX(200.0),
                        edge_layer.sceneToScreenY(y),
                    )
                    assert hit == edge_id, (renderer, edge_id, hit)

                if renderer == "canvas":
                    canvas_layer = edge_layer.findChild(QObject, "graphCanvasEdgeCanvasLayer")
                    assert canvas_layer is not None
                    assert list(to_variant(canvas_layer.hiddenEndpointArcRadiiScreenPx())) == [9.0, 12.0, 15.0]
                    hidden_paint = paint("hidden")
                    assert hidden_paint["displayMode"] == "hidden"
                    assert hidden_paint["bodyVisible"] is False
                    assert hidden_paint["endpointArcsVisible"] is True
                    hidden_geometry = snapshot(edge_layer, "hidden")["geometry"]
                    center = to_variant(edge_layer._edgeAnchor(hidden_geometry, 0.5))
                    endpoint = to_variant(edge_layer._edgeAnchor(hidden_geometry, 0.02))
                    assert edge_layer.edgeAtScreen(
                        edge_layer.sceneToScreenX(center["x"]),
                        edge_layer.sceneToScreenY(center["y"]),
                    ) == ""
                    assert edge_layer.edgeAtScreen(
                        edge_layer.sceneToScreenX(endpoint["x"]),
                        edge_layer.sceneToScreenY(endpoint["y"]),
                    ) == "hidden"
                    scene_rect_hits = to_variant(edge_layer.edgeIdsIntersectingSceneRect(
                        center["x"] - 2.0,
                        center["y"] - 2.0,
                        4.0,
                        4.0,
                    ))
                    assert "hidden" in scene_rect_hits
                    center_screen_x = edge_layer.sceneToScreenX(center["x"])
                    center_screen_y = edge_layer.sceneToScreenY(center["y"])
                    screen_rect_hits = to_variant(edge_layer.edgeIdsIntersectingScreenRect(
                        center_screen_x - 2.0,
                        center_screen_y - 2.0,
                        4.0,
                        4.0,
                    ))
                    assert "hidden" in screen_rect_hits
                    assert "Hidden" in str(edge_layer.edgeTooltipText("hidden"))

                    hidden_revision = int(edge_layer.property("_visibleEdgeSnapshotRevision"))
                    hidden_key = str(edge_layer.property("_lastVisibleEdgeSetKey"))
                    edge_layer.setProperty("wireSelectionModeHeld", True)
                    refresh(edge_layer)
                    QTest.qWait(5)
                    app.processEvents()
                    assert int(edge_layer.property("_visibleEdgeSnapshotRevision")) > hidden_revision
                    assert str(edge_layer.property("_lastVisibleEdgeSetKey")) != hidden_key
                    assert str(edge_layer.property("_lastVisibleEdgeSetKey")).startswith("w|")
                    w_hidden_snapshot = snapshot(edge_layer, "hidden")
                    assert w_hidden_snapshot["hiddenUnrevealed"] is False
                    w_revealed_paint = paint("hidden")
                    assert w_revealed_paint["bodyVisible"] is True
                    assert w_revealed_paint["endpointArcsVisible"] is False
                    assert color_name(w_revealed_paint["strokeColor"]) == color_name(
                        edge_layer.property("activeDefaultStrokeColor")
                    )
                    edge_layer.setProperty(
                        "selectedEdgeIds",
                        ["selected_hidden", "selected_disabled", "hidden"],
                    )
                    refresh(edge_layer)
                    QTest.qWait(5)
                    app.processEvents()
                    selected_w_paint = paint("hidden")
                    assert color_name(selected_w_paint["strokeColor"]) == "#75b4e7"
                    edge_layer.setProperty("wireSelectionModeHeld", False)
                    edge_layer.setProperty("selectedEdgeIds", ["selected_hidden", "selected_disabled"])
                    refresh(edge_layer)

                    invalid_paint = paint("invalid")
                    assert invalid_paint["invalidGradient"] is True
                    assert invalid_paint["nodeSelectionGradient"] is False
                    assert invalid_paint["structure"] == "empty"
                    assert invalid_paint["bodyVisible"] is False
                    selected_endpoint_paint = paint("selected_endpoint")
                    assert selected_endpoint_paint["nodeSelectionGradient"] is True
                    assert selected_endpoint_paint["invalidGradient"] is False
                    selected_invalid_paint = paint("selected_invalid")
                    assert selected_invalid_paint["nodeSelectionGradient"] is True
                    assert selected_invalid_paint["invalidGradient"] is True
                    assert str(selected_invalid_paint["gradientKind"]) not in {"", "none"}

                    assert int(paint("flow")["strokeCount"]) == 1
                    assert abs(float(paint("flow")["strokeWidthScreenPx"]) - 1.0) < 0.001
                    assert abs(float(paint("flow_disabled")["strokeAlpha"]) - 1.0) < 0.001

                tooltip = edge_layer.findChild(QObject, "graphEdgeValuePreviewToolTip")
                assert tooltip is not None
                assert tooltip.property("screenStablePlacement") == "below"
                assert int(tooltip.property("delay")) == 400
                assert int(tooltip.property("maximumTextWidth")) == 360
                QTest.mouseMove(window, QPoint(
                    round(edge_layer.sceneToScreenX(200.0)),
                    round(edge_layer.sceneToScreenY(120.0)),
                ))
                QTest.qWait(450)
                app.processEvents()
                assert bool(tooltip.property("active"))
                assert str(tooltip.property("text")).startswith("List: 3 items")
                QTest.mouseMove(window, QPoint(8, 8))
                app.processEvents()
                assert not bool(tooltip.property("active"))

            culled_edge = bezier_edge("culled", "culled_source", 5000.0)
            edge_layer.setProperty("selectedEdgeIds", [])
            edge_layer.setProperty("selectedNodeIds", [])
            edge_layer.setProperty("replacementPreviewEdgeIds", [])
            edge_layer.setProperty("edges", [culled_edge])
            refresh(edge_layer)
            culled_snapshot = snapshot(edge_layer, "culled")
            assert culled_snapshot["culled"] is True
            assert culled_snapshot["geometry"] is None
            source_point = to_variant(edge_layer.edgeEndpointScenePoint("culled", "source"))
            target_point = to_variant(edge_layer.edgeEndpointScenePoint("culled", "target"))
            assert source_point == {"x": 80.0, "y": 5000.0}
            assert target_point == {"x": 320.0, "y": 5000.0}

            """,
        )

    def test_active_data_wire_base_color_is_neutral_and_contrast_safe_across_canvas_palettes(
        self,
    ) -> None:
        self._run_edge_layer_probe(
            "active-data-wire-crossed-palette-contrast",
            """
            edge_canvas = edge_layer.findChild(QObject, "graphCanvasEdgeCanvasLayer")
            assert edge_canvas is not None

            from PyQt6.QtGui import QColor
            from PyQt6.QtQuick import QQuickWindow
            from PyQt6.QtTest import QTest

            window = QQuickWindow()
            window.resize(1280, 720)
            edge_layer.setParentItem(window.contentItem())
            window.show()
            app.processEvents()

            def color_name(value):
                return value.name().lower() if hasattr(value, "name") else str(value).lower()

            assert color_name(edge_layer.neutralActiveStrokeColor(QColor("#F7FAFC"))) == "#6b7277"
            assert color_name(edge_layer.neutralActiveStrokeColor(QColor("#151821"))) == "#a7adb2"

            fixtures = (
                {
                    "name": "light_canvas_dark_shell",
                    "canvas_bg": "#F7FAFC",
                    "shell_muted": "#98A2B3",
                    "edge_color": "#253247",
                },
                {
                    "name": "dark_canvas_light_shell",
                    "canvas_bg": "#151821",
                    "shell_muted": "#5B6474",
                    "edge_color": "#E5E7EB",
                },
            )

            def active_edge(edge_id, source_id, color, *, enabled=True, warning=False):
                return {
                    "edge_id": edge_id,
                    "source_node_id": source_id,
                    "source_port_key": "out",
                    "target_node_id": edge_id + "_target",
                    "target_port_key": "in",
                    "source_port_kind": "data",
                    "target_port_kind": "data",
                    "edge_family": "standard",
                    "active_data_wire": True,
                    "enabled": enabled,
                    "data_access": "item",
                    "visual_style": {"display_mode": "default"},
                    "color": color,
                    "data_type_warning": warning,
                }

            previews = {}
            cases = []
            for fixture in fixtures:
                assert fixture["edge_color"].lower() != fixture["shell_muted"].lower()
                assert fixture["edge_color"].lower() != fixture["canvas_bg"].lower()
                prefix = fixture["name"]
                previews[prefix + "_normal"] = {"out": {"state": "current"}}
                previews[prefix + "_empty"] = {"out": {"state": "empty"}}
                previews[prefix + "_disabled"] = {"out": {"state": "current"}}
                previews[prefix + "_invalid"] = {"out": {"state": "current"}}
                cases.append((fixture, {
                    "normal": active_edge(prefix + "_normal_edge", prefix + "_normal", fixture["edge_color"]),
                    "empty": active_edge(prefix + "_empty_edge", prefix + "_empty", fixture["edge_color"]),
                    "disabled": active_edge(prefix + "_disabled_edge", prefix + "_disabled", fixture["edge_color"], enabled=False),
                    "invalid": active_edge(prefix + "_invalid_edge", prefix + "_invalid", fixture["edge_color"], warning=True),
                }))
            edge_layer.setProperty("outputPreviewLookup", previews)

            all_edges = [edge for _fixture, states in cases for edge in states.values()]
            selected_edge_ids = [states["normal"]["edge_id"] for _fixture, states in cases]
            edge_layer.setProperty("edgeRendererPreference", "canvas")
            edge_layer.setProperty("selectedEdgeIds", selected_edge_ids)
            edge_layer.setProperty("edges", all_edges)
            refresh(edge_layer)
            QTest.qWait(5)
            app.processEvents()

            def paint(edge_payload):
                diagnostics = to_variant(
                    edge_layer.property("activeEdgePaintDiagnosticsByEdgeId")
                ) or {}
                value = to_variant(diagnostics.get(edge_payload["edge_id"]))
                return value if isinstance(value, dict) else dict(value)

            for fixture, edges in cases:
                expected_base = color_name(edge_layer.property("activeDefaultStrokeColor"))
                for state in ("normal", "empty", "disabled", "invalid"):
                    state_paint = paint(edges[state])
                    assert color_name(state_paint["baseColor"]) == expected_base, (fixture["name"], state, state_paint)
                    if state != "normal":
                        assert color_name(state_paint["strokeColor"]) == expected_base, (fixture["name"], state, state_paint)
                    assert color_name(state_paint["baseColor"]) != fixture["edge_color"].lower()

                selected_paint = paint(edges["normal"])
                assert color_name(selected_paint["strokeColor"]) == color_name(
                    edge_layer.property("activeSelectedStrokeColor")
                )

                invalid_paint = paint(edges["invalid"])
                assert invalid_paint["invalidGradient"] is True
                assert invalid_paint["gradientKind"] == "invalid_target"
                assert color_name(invalid_paint["baseColor"]) != color_name(
                    edge_layer.property("dangerStrokeColor")
                )
                assert color_name(invalid_paint["strokeColor"]) != color_name(
                    edge_layer.property("dangerStrokeColor")
                )

                assert paint(edges["empty"])["structure"] == "empty"
                assert abs(float(paint(edges["empty"])["strokeAlpha"]) - 1.0) < 0.001
                assert abs(float(paint(edges["disabled"])["strokeAlpha"]) - 1.0) < 0.001
            """,
        )

    def test_graph_canvas_flow_edge_labels_render_and_reduce_at_low_zoom(self) -> None:
        self._run_qml_probe(
            "flow-edge-label-zoom",
            """
            labels = named_child_items(edge_layer, "graphEdgeFlowLabelItem")
            assert len(labels) == 1, len(labels)
            label_item = labels[0]
            initial_snapshot = assert_flow_label_snapshot_consistency(edge_layer, label_item, edge_id)
            initial_revision = int(edge_layer.property("_visibleEdgeSnapshotRevision"))
            assert initial_revision == initial_snapshot["revision"]
            assert label_item.isVisible()
            assert label_item.property("labelMode") == "pill"
            label_text = label_item.findChild(QObject, "graphEdgeFlowLabelText")
            label_pill = label_item.findChild(QObject, "graphEdgeFlowLabelPill")
            assert label_text is not None
            assert label_pill is not None
            assert label_text.property("text") == "Primary path"
            assert bool(label_pill.property("visible"))
            assert bool(label_item.property("hitTestMatches"))

            def color_alpha(value):
                return value.alphaF() if hasattr(value, "alphaF") else 1.0

            def assert_label_gap_break(edge_snapshot):
                label_anchor = edge_snapshot["labelAnchorScene"]
                breaks = edge_snapshot["crossingBreaks"]
                assert label_anchor is not None
                assert len(breaks) >= 1
                assert any(
                    abs(float(item["centerX"]) - float(label_anchor["x"])) < 16.0
                    and abs(float(item["centerY"]) - float(label_anchor["y"])) < 16.0
                    for item in breaks
                )

            assert abs(color_alpha(label_pill.property("color")) - 1.0) < 0.001
            assert_label_gap_break(initial_snapshot)

            default_source_id = scene.add_node_from_type("tests.flow_edge_label_probe_node", 40.0, 250.0)
            default_target_id = scene.add_node_from_type("tests.flow_edge_label_probe_node", 380.0, 310.0)
            default_edge_id = scene.add_edge(default_source_id, "flow_out", default_target_id, "flow_in")
            scene.set_edge_label(default_edge_id, "Default backing")
            settle_canvas_redraw()

            labels_by_text = {
                item.property("labelText"): item
                for item in named_child_items(edge_layer, "graphEdgeFlowLabelItem")
            }
            default_label_item = labels_by_text.get("Default backing")
            assert default_label_item is not None
            default_label_pill = default_label_item.findChild(QObject, "graphEdgeFlowLabelPill")
            assert default_label_pill is not None
            assert bool(default_label_pill.property("visible"))
            assert abs(color_alpha(default_label_pill.property("color"))) < 0.001
            assert_label_gap_break(to_variant(edge_layer._visibleEdgeSnapshot(default_edge_id)))

            view.set_zoom(0.7)
            settle_canvas_redraw()
            simplified_snapshot = assert_flow_label_snapshot_consistency(edge_layer, label_item, edge_id)
            simplified_revision = int(edge_layer.property("_visibleEdgeSnapshotRevision"))
            assert simplified_revision > initial_revision
            assert simplified_revision == simplified_snapshot["revision"]
            assert label_item.isVisible()
            assert label_item.property("labelMode") == "text"
            assert bool(label_pill.property("visible"))
            assert float(label_item.property("labelScale")) == 1.0
            assert float(label_item.property("horizontalPadding")) >= 8.0
            assert float(label_item.property("verticalPadding")) >= 3.0
            assert float(label_pill.property("radius")) <= 2.0

            view.set_zoom(0.5)
            settle_canvas_redraw()
            minimap_snapshot = assert_flow_label_snapshot_consistency(edge_layer, label_item, edge_id)
            minimap_revision = int(edge_layer.property("_visibleEdgeSnapshotRevision"))
            assert minimap_revision > simplified_revision
            assert minimap_revision == minimap_snapshot["revision"]
            assert label_item.isVisible()
            assert minimap_snapshot["labelMode"] == "text"
            assert minimap_snapshot["labelAnchorScene"] is not None
            assert bool(label_pill.property("visible"))
            assert 0.35 <= float(label_item.property("labelScale")) < 1.0
            assert len(named_child_items(edge_layer, "graphEdgeFlowLabelItem")) >= 2

            """,
        )

    def test_graph_canvas_passive_standard_and_flow_styles_and_markers_stay_legacy(
        self,
    ) -> None:
        self._run_qml_probe(
            "flow-edge-selected-stroke-color",
            """
            def color_name(value):
                return value.name().lower() if hasattr(value, "name") else str(value).lower()

            edge_canvas = edge_layer.findChild(QObject, "graphCanvasEdgeCanvasLayer")
            assert edge_canvas is not None
            from PyQt6.QtQuick import QQuickWindow
            window = QQuickWindow()
            window.resize(1280, 720)
            canvas.setParentItem(window.contentItem())
            window.show()
            app.processEvents()
            edge_layer.setProperty("edgeRendererPreference", "canvas")

            def paint(edge_id_value):
                for _attempt in range(30):
                    diagnostics = to_variant(
                        edge_layer.property("activeEdgePaintDiagnosticsByEdgeId")
                    ) or {}
                    value = to_variant(diagnostics.get(edge_id_value))
                    if value is not None:
                        return value if isinstance(value, dict) else dict(value)
                    settle_canvas_redraw()
                    QTest.qWait(5)
                    app.processEvents()
                raise AssertionError((edge_id_value, diagnostics))

            edge_layer.setProperty("selectedEdgeIds", [edge_id])
            settle_canvas_redraw()
            selected_flow_paint = paint(edge_id)
            assert color_name(selected_flow_paint["strokeColor"]) == "#335577"

            scene.set_edge_visual_style(edge_id, {})
            settle_canvas_redraw()
            QTest.qWait(5)
            app.processEvents()
            default_selected_flow_paint = paint(edge_id)
            assert color_name(default_selected_flow_paint["strokeColor"]) == color_name(
                edge_layer.property("selectedStrokeColor")
            )

            edge_layer.setProperty(
                "outputPreviewLookup",
                {
                    "passive_standard_source": {"out": {"state": "current", "tooltip_text": "Current"}},
                    "passive_disabled_source": {"out": {"state": "current", "tooltip_text": "Current"}},
                },
            )
            passive_standard = {
                "edge_id": "passive_standard",
                "source_node_id": "passive_standard_source",
                "source_port_key": "out",
                "target_node_id": "passive_standard_target",
                "target_port_key": "in",
                "edge_family": "standard",
                "enabled": True,
                "active_data_wire": False,
                "data_access": "item",
                "stroke_count": 1,
                "visual_style": {},
                "color": "#445566",
                "data_type_warning": False,
            }
            disabled_standard = dict(passive_standard)
            disabled_standard["edge_id"] = "passive_disabled"
            disabled_standard["source_node_id"] = "passive_disabled_source"
            disabled_standard["target_node_id"] = "passive_disabled_target"
            disabled_standard["enabled"] = False
            view.set_zoom(0.5)
            edge_layer.setProperty("selectedEdgeIds", ["passive_standard"])
            edge_layer.setProperty("edges", [passive_standard, disabled_standard])
            settle_canvas_redraw()
            selected_standard_paint = paint("passive_standard")
            assert color_name(selected_standard_paint["strokeColor"]) == color_name(
                edge_layer.property("selectedStrokeColor")
            )
            assert abs(float(selected_standard_paint["strokeWidthScreenPx"]) - 1.5) < 0.001
            disabled_standard_paint = paint("passive_disabled")
            assert abs(float(disabled_standard_paint["strokeAlpha"]) - 1.0) < 0.001
            assert disabled_standard_paint["disabledMarkerVisible"] is False

            redraw_count = int(edge_layer.property("_redrawRequestCount"))
            edge_layer.setProperty("dragConnection", {
                "connection_mode": "append",
                "source_kind": "flow",
                "active_data_wire": False,
                "valid_drop": True,
                "start_x": 80.0,
                "start_y": 80.0,
                "target_x": 240.0,
                "target_y": 120.0,
            })
            settle_canvas_redraw()
            QTest.qWait(5)
            app.processEvents()
            assert str(edge_layer.property("edgeRendererKind")) == "canvas"
            assert int(edge_layer.property("_redrawRequestCount")) > redraw_count
            """,
        )

    def test_graph_canvas_flow_edge_toolbar_edits_labels_inline(self) -> None:
        script = textwrap.dedent(
            """
            import sys
            from pathlib import Path
            from PyQt6.QtCore import QObject, QUrl
            from PyQt6.QtGui import QGuiApplication
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtQuick import QQuickWindow
            from ea_node_editor.ui.icon_registry import UiIconRegistryBridge

            app = QGuiApplication.instance() or QGuiApplication([])
            engine = QQmlEngine()
            engine.rootContext().setContextProperty("uiIcons", UiIconRegistryBridge())
            qml = b'''
            import QtQuick 2.15
            import "ea_node_editor/ui_qml/components/graph/overlay" as Overlay
            Item {
                id: root
                width: 800
                height: 600
                property string committedLabel: ""
                property string committedStyleEdgeId: ""
                property string committedStrokeColor: ""
                property string committedStrokePattern: ""
                property string committedArrowHead: ""
                property string committedPathMode: ""
                property string currentStrokePattern: "solid"
                property string currentArrowHead: "filled"
                property string currentPathMode: "auto"
                property string currentLabelBackgroundColor: "#DDEEFF"
                property bool commandBridgeEnabled: true
                function applyColorChoice() { return toolbar._setFlowEdgeVisualStyle({"stroke_color": "#E06C75"}); }
                function applyPatternChoice() { return toolbar._setFlowEdgeVisualStyle({"stroke_pattern": "dashed"}); }
                function applyArrowChoice() { return toolbar._setFlowEdgeVisualStyle({"arrow_head": "open"}); }
                function applyPathModeChoice(pathMode) { return toolbar._setEdgePathMode(pathMode); }
                function openPathModePopupForTest() { toolbar._handleToolbarAction({"id": "path_mode", "popover": "path_mode"}, popupAnchor); }
                function openPatternPopupForTest() { toolbar._handleToolbarAction({"id": "stroke_pattern", "popover": "pattern"}, popupAnchor); }
                function openArrowPopupForTest() { toolbar._handleToolbarAction({"id": "arrow_head", "popover": "arrow"}, popupAnchor); }
                function pathModeButtonActiveForTest() { return toolbar._buttonActive({"id": "path_mode"}); }
                function patternButtonActiveForTest() { return toolbar._buttonActive({"id": "stroke_pattern"}); }
                function arrowButtonActiveForTest() { return toolbar._buttonActive({"id": "arrow_head"}); }
                function clearEdgeSelectionForTest() { canvas.selectedEdgeIds = []; }
                function restoreEdgeSelectionForTest() { canvas.selectedEdgeIds = ["edge-1"]; }
                function selectStandardEdgeForTest() { canvas.selectedEdgeIds = ["edge-2"]; }
                function edgeRedrawRequestsForTest() { return canvas.edgeRedrawRequests; }
                QtObject {
                    id: commandBridge
                    function set_edge_label(edgeId, label) { root.committedLabel = String(edgeId) + ":" + String(label); }
                    function clear_edge_label(edgeId) { root.committedLabel = String(edgeId) + ":"; }
                    function set_edge_visual_style(edgeId, style) {
                        root.committedStyleEdgeId = String(edgeId);
                        root.committedStrokeColor = String(style.stroke_color || "");
                        root.committedStrokePattern = String(style.stroke_pattern || "");
                        root.committedArrowHead = String(style.arrow_head || "");
                        root.committedPathMode = String(style.path_mode || "auto");
                        if (style.stroke_pattern !== undefined)
                            root.currentStrokePattern = String(style.stroke_pattern || "solid");
                        if (style.arrow_head !== undefined)
                            root.currentArrowHead = String(style.arrow_head || "filled");
                        root.currentPathMode = String(style.path_mode || "auto");
                    }
                }
                Item {
                    id: canvas
                    property int graphLabelPixelSize: 10
                    property var selectedEdgeIds: ["edge-1"]
                    property bool edgeContextVisible: false
                    property bool nodeContextVisible: false
                    property bool selectionContextVisible: false
                    property int edgeRedrawRequests: 0
                    property var sceneCommandBridge: root.commandBridgeEnabled ? commandBridge : null
                    function _edgeSupportsFlowStyle(edgeId) { return String(edgeId) === "edge-1"; }
                    function _sceneEdgePayload(edgeId) {
                        var style = {"stroke_color": "#61AFEF", "stroke_pattern": root.currentStrokePattern, "arrow_head": root.currentArrowHead, "label_text_color": "#123456"};
                        if (root.currentPathMode !== "auto")
                            style.path_mode = root.currentPathMode;
                        if (String(edgeId) === "edge-2")
                            return {"edge_id": String(edgeId), "edge_family": "standard", "label": "", "visual_style": style};
                        if (root.currentLabelBackgroundColor.length)
                            style.label_background_color = root.currentLabelBackgroundColor;
                        return {"edge_id": String(edgeId), "edge_family": "flow", "label": "Go", "visual_style": style, "flow_style": style};
                    }
                    function setExclusiveEdgeSelection(edgeId) { selectedEdgeIds = [String(edgeId)]; }
                    function requestEdgeRedraw() { edgeRedrawRequests += 1; }
                    function frameSceneRectPayload(rectLike, paddingPx) { return true; }
                }
                Item {
                    id: edgeLayer
                    property color flowDefaultLabelTextColor: "#334455"
                    property color flowDefaultLabelBackgroundColor: "#EEF3F8"
                    property var shellPalette: {"canvas_bg": "#F7FAFC"}
                    function _visibleEdgeSnapshot(edgeId) { return {"culled": false, "labelMode": "pill", "geometry": {"route": "bezier", "sx": 120, "sy": 100, "c1x": 160, "c1y": 100, "c2x": 220, "c2y": 100, "tx": 260, "ty": 100}}; }
                    function _edgeAnchor(geometry, fraction) { return {"x": 190, "y": 100, "dx": 1, "dy": 0, "angle": 0}; }
                    function sceneToScreenX(value) { return Number(value); }
                    function sceneToScreenY(value) { return Number(value); }
                }
                Item {
                    id: popupAnchor
                    width: 24
                    height: 24
                    x: 320
                    y: 140
                }
                Overlay.GraphEdgeFloatingToolbar {
                    id: toolbar
                    objectName: "toolbarUnderTest"
                    anchors.fill: parent
                    canvasItem: canvas
                    edgeLayer: edgeLayer
                    themePalette: {"panel_bg": "#20242d", "panel_title_fg": "#f0f4fb", "muted_fg": "#98a2b3", "border": "#4b5568", "canvas_bg": "#F7FAFC"}
                }
            }
            '''
            component = QQmlComponent(engine)
            component.setData(qml, QUrl.fromLocalFile(str(Path.cwd() / "toolbar_probe.qml")))
            if component.status() != QQmlComponent.Status.Ready:
                raise AssertionError("\\n".join(error.toString() for error in component.errors()))
            root = component.create()
            if root is None:
                raise AssertionError("\\n".join(error.toString() for error in component.errors()))
            window = QQuickWindow()
            window.setWidth(800)
            window.setHeight(600)
            root.setParentItem(window.contentItem())
            window.show()
            app.processEvents()
            toolbar = root.findChild(QObject, "toolbarUnderTest")
            if toolbar is None:
                raise AssertionError("toolbar missing")
            if not bool(toolbar.property("toolbarVisible")):
                raise AssertionError("toolbar not visible")
            if not bool(toolbar.beginLabelEdit("edge-1")):
                raise AssertionError("beginLabelEdit failed")
            app.processEvents()
            editor = toolbar.findChild(QObject, "graphEdgeLabelInlineEditor")
            editor_frame = toolbar.findChild(QObject, "graphEdgeLabelInlineEditorFrame")
            editor_background = toolbar.findChild(QObject, "graphEdgeLabelInlineEditorBackground")
            typography = toolbar.findChild(QObject, "graphEdgeLabelEditorSharedTypography")
            pattern_popup = toolbar.findChild(QObject, "graphEdgePatternPopup")
            arrow_popup = toolbar.findChild(QObject, "graphEdgeArrowPopup")
            path_mode_popup = toolbar.findChild(QObject, "graphEdgePathModePopup")
            if editor is None:
                raise AssertionError("editor missing")
            if editor_frame is None:
                raise AssertionError("editor frame missing")
            if editor_background is None:
                raise AssertionError("editor background missing")
            if typography is None:
                raise AssertionError("editor typography missing")
            if pattern_popup is None:
                raise AssertionError("pattern popup missing")
            if arrow_popup is None:
                raise AssertionError("arrow popup missing")
            if path_mode_popup is None:
                raise AssertionError("path mode popup missing")
            if toolbar.property("toolbarPathMode") != "auto":
                raise AssertionError("toolbar path mode did not start as auto")
            if toolbar.property("toolbarPatternGlyphKind") != "solid":
                raise AssertionError("toolbar pattern glyph did not start as solid")
            if toolbar.property("toolbarArrowGlyphKind") != "filled":
                raise AssertionError("toolbar arrow glyph did not start as filled")
            if toolbar.property("toolbarPatternIconName") != "edge-path-solid":
                raise AssertionError("toolbar pattern icon did not start with the solid asset")
            if toolbar.property("toolbarArrowIconName") != "edge-arrow-filled":
                raise AssertionError("toolbar arrow icon did not start with the filled asset")
            if editor.property("text") != "Go":
                raise AssertionError(f"unexpected editor text {editor.property('text')!r}")
            def color_name(value):
                return value.name().lower() if hasattr(value, "name") else str(value).lower()
            editor_font = editor.property("font")
            if editor_font.pixelSize() != int(typography.property("edgePillPixelSize")):
                raise AssertionError("editor font size does not match edge pill typography")
            if editor_font.weight() != int(typography.property("edgePillFontWeight")):
                raise AssertionError("editor font weight does not match edge pill typography")
            if color_name(editor.property("color")) != "#123456":
                raise AssertionError(f"unexpected editor text color {color_name(editor.property('color'))!r}")
            if color_name(editor_background.property("color")) != "#ddeeff":
                raise AssertionError(f"unexpected editor background color {color_name(editor_background.property('color'))!r}")
            def color_alpha(value):
                return value.alphaF() if hasattr(value, "alphaF") else 1.0
            if int(editor_background.property("effectiveBorderWidth")) != 0:
                raise AssertionError("editor background should not draw field chrome border")
            if not bool(toolbar.cancelLabelEdit()):
                raise AssertionError("cancelLabelEdit failed")
            root.setProperty("currentLabelBackgroundColor", "")
            if not bool(toolbar.beginLabelEdit("edge-1")):
                raise AssertionError("beginLabelEdit without a label background failed")
            app.processEvents()
            if abs(color_alpha(editor_background.property("color"))) >= 0.001:
                raise AssertionError("default editor background should be transparent")
            if float(editor_frame.property("width")) >= 128.0:
                raise AssertionError(f"editor kept the old wide field minimum: {editor_frame.property('width')!r}")
            if float(editor_frame.property("height")) >= 34.0:
                raise AssertionError(f"editor kept the old tall field minimum: {editor_frame.property('height')!r}")
            root.setProperty("commandBridgeEnabled", False)
            editor.setProperty("text", "Draft that should remain")
            if bool(toolbar.commitLabelEdit()):
                raise AssertionError("commitLabelEdit unexpectedly succeeded without a command bridge")
            if toolbar.property("editingEdgeId") != "edge-1":
                raise AssertionError("failed commit cleared the active edge draft")
            if editor.property("text") != "Draft that should remain":
                raise AssertionError("failed commit discarded the editor text")
            root.setProperty("commandBridgeEnabled", True)
            editor.setProperty("text", "Loop branch")
            if not bool(toolbar.commitLabelEdit()):
                raise AssertionError("commitLabelEdit failed")
            if root.property("committedLabel") != "edge-1:Loop branch":
                raise AssertionError(f"unexpected committed label {root.property('committedLabel')!r}")
            if int(root.edgeRedrawRequestsForTest()) < 1:
                raise AssertionError("label commit did not request an edge redraw")
            if not bool(toolbar._stylePopupClosesOutsidePopup()):
                raise AssertionError("style popups should close on presses outside the popup, not only outside the parent overlay")
            root.openPathModePopupForTest()
            app.processEvents()
            if not bool(path_mode_popup.property("opened")):
                raise AssertionError("path mode popup did not open")
            if not bool(root.pathModeButtonActiveForTest()):
                raise AssertionError("path mode button should be active only while its popup is open")
            root.openPathModePopupForTest()
            app.processEvents()
            if bool(path_mode_popup.property("opened")):
                raise AssertionError("re-clicking an open path mode popup should close it")
            if bool(root.pathModeButtonActiveForTest()):
                raise AssertionError("path mode button stayed active after its popup closed")
            root.openPatternPopupForTest()
            app.processEvents()
            if not bool(pattern_popup.property("opened")):
                raise AssertionError("pattern popup did not open")
            if not bool(root.patternButtonActiveForTest()):
                raise AssertionError("pattern button should be active only while its popup is open")
            root.openPatternPopupForTest()
            app.processEvents()
            if bool(pattern_popup.property("opened")):
                raise AssertionError("re-clicking an open pattern popup should close it")
            if bool(root.patternButtonActiveForTest()):
                raise AssertionError("pattern button stayed active after its popup closed")
            root.openPatternPopupForTest()
            app.processEvents()
            if not bool(pattern_popup.property("opened")):
                raise AssertionError("pattern popup did not reopen")
            root.openArrowPopupForTest()
            app.processEvents()
            if bool(pattern_popup.property("opened")) or not bool(arrow_popup.property("opened")):
                raise AssertionError("opening arrow popup should close the pattern popup")
            if bool(root.patternButtonActiveForTest()) or not bool(root.arrowButtonActiveForTest()):
                raise AssertionError("only the open arrow popup should mark a style button active")
            root.clearEdgeSelectionForTest()
            app.processEvents()
            if bool(path_mode_popup.property("opened")) or bool(pattern_popup.property("opened")) or bool(arrow_popup.property("opened")):
                raise AssertionError("toolbar popups should close when the active edge disappears")
            if bool(root.pathModeButtonActiveForTest()) or bool(root.patternButtonActiveForTest()) or bool(root.arrowButtonActiveForTest()):
                raise AssertionError("style buttons stayed active after popups closed")
            root.restoreEdgeSelectionForTest()
            app.processEvents()
            redraw_before_path = int(root.edgeRedrawRequestsForTest())
            if not bool(root.applyPathModeChoice("pipe")):
                raise AssertionError("path mode update failed")
            if root.property("committedStyleEdgeId") != "edge-1" or root.property("committedPathMode") != "pipe":
                raise AssertionError("unexpected path mode payload")
            if int(root.edgeRedrawRequestsForTest()) <= redraw_before_path:
                raise AssertionError("path mode update did not request an edge redraw")
            app.processEvents()
            if toolbar.property("toolbarPathMode") != "pipe":
                raise AssertionError("toolbar path mode did not follow selected pipe mode")
            if not bool(root.applyPathModeChoice("auto")):
                raise AssertionError("path mode reset failed")
            if root.property("committedPathMode") != "auto" or toolbar.property("toolbarPathMode") != "auto":
                raise AssertionError("auto path mode did not clear the override")
            redraw_before_color = int(root.edgeRedrawRequestsForTest())
            if not bool(root.applyColorChoice()):
                raise AssertionError("color style update failed")
            if root.property("committedStyleEdgeId") != "edge-1" or root.property("committedStrokeColor") != "#E06C75":
                raise AssertionError("unexpected color style payload")
            if int(root.edgeRedrawRequestsForTest()) <= redraw_before_color:
                raise AssertionError("color style update did not request an edge redraw")
            redraw_before_pattern = int(root.edgeRedrawRequestsForTest())
            if not bool(root.applyPatternChoice()):
                raise AssertionError("pattern style update failed")
            if root.property("committedStyleEdgeId") != "edge-1" or root.property("committedStrokePattern") != "dashed":
                raise AssertionError("unexpected pattern style payload")
            if int(root.edgeRedrawRequestsForTest()) <= redraw_before_pattern:
                raise AssertionError("pattern style update did not request an edge redraw")
            app.processEvents()
            if toolbar.property("toolbarPatternGlyphKind") != "dashed":
                raise AssertionError("toolbar pattern glyph did not follow selected dashed style")
            if toolbar.property("toolbarPatternIconName") != "edge-path-dashed":
                raise AssertionError("toolbar pattern icon did not follow selected dashed asset")
            if bool(root.patternButtonActiveForTest()):
                raise AssertionError("non-default path style should not leave the toolbar button active")
            redraw_before_arrow = int(root.edgeRedrawRequestsForTest())
            if not bool(root.applyArrowChoice()):
                raise AssertionError("arrow style update failed")
            if root.property("committedStyleEdgeId") != "edge-1" or root.property("committedArrowHead") != "open":
                raise AssertionError("unexpected arrow style payload")
            if int(root.edgeRedrawRequestsForTest()) <= redraw_before_arrow:
                raise AssertionError("arrow style update did not request an edge redraw")
            app.processEvents()
            if toolbar.property("toolbarArrowGlyphKind") != "open":
                raise AssertionError("toolbar arrow glyph did not follow selected open style")
            if toolbar.property("toolbarArrowIconName") != "edge-arrow-open":
                raise AssertionError("toolbar arrow icon did not follow selected open asset")
            if bool(root.arrowButtonActiveForTest()):
                raise AssertionError("non-default arrow style should not leave the toolbar button active")
            root.selectStandardEdgeForTest()
            app.processEvents()
            if not bool(toolbar.property("toolbarVisible")):
                raise AssertionError("standard selected edge should show the path toolbar")
            standard_actions = toolbar.property("toolbarActions")
            if hasattr(standard_actions, "toVariant"):
                standard_actions = standard_actions.toVariant()
            normalized_standard_actions = []
            for action in standard_actions:
                if hasattr(action, "toVariant"):
                    action = action.toVariant()
                normalized_standard_actions.append(action)
            standard_action_ids = [str(action.get("id", "")) for action in normalized_standard_actions]
            if "path_mode" not in standard_action_ids:
                raise AssertionError(f"standard edge toolbar missing path mode action: {standard_action_ids!r}")
            if "edge_color" in standard_action_ids or "edit_flow_edge_style" in standard_action_ids:
                raise AssertionError(f"standard edge toolbar exposed flow-only actions: {standard_action_ids!r}")
            window.hide()
            root.deleteLater()
            window.deleteLater()
            """
        )
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
        _run_isolated_probe("flow-edge-toolbar-inline-label-edit", script, env)

    def test_graph_typography_inline_edge_flow_edge_labels_follow_shared_roles_in_pill_and_text_modes(
        self,
    ) -> None:
        self._run_qml_probe(
            "flow-edge-label-typography",
            """
            labels = named_child_items(edge_layer, "graphEdgeFlowLabelItem")
            assert len(labels) == 1
            label_item = labels[0]
            label_text = label_item.findChild(QObject, "graphEdgeFlowLabelText")
            typography = edge_layer.findChild(QObject, "graphEdgeSharedTypography")

            assert label_text is not None
            assert typography is not None
            assert label_item.property("labelMode") == "pill", label_item.property("labelMode")
            assert label_text.property("font").pixelSize() == int(typography.property("edgePillPixelSize")), (
                label_text.property("font").pixelSize(),
                int(typography.property("edgePillPixelSize")),
            )
            assert label_text.property("font").weight() == int(typography.property("edgePillFontWeight")), (
                label_text.property("font").weight(),
                int(typography.property("edgePillFontWeight")),
            )

            view.set_zoom(0.7)
            settle_canvas_redraw()

            assert label_item.property("labelMode") == "text", label_item.property("labelMode")
            assert label_text.property("font").pixelSize() == int(typography.property("edgeLabelPixelSize")), (
                label_text.property("font").pixelSize(),
                int(typography.property("edgeLabelPixelSize")),
            )
            assert label_text.property("font").weight() == int(typography.property("edgeLabelFontWeight")), (
                label_text.property("font").weight(),
                int(typography.property("edgeLabelFontWeight")),
            )

            shell_bridge.set_graphics_graph_label_pixel_size_value(16)
            app.processEvents()
            app.processEvents()

            assert int(typography.property("edgeLabelPixelSize")) == 17, int(typography.property("edgeLabelPixelSize"))
            assert int(typography.property("edgePillPixelSize")) == 18, int(typography.property("edgePillPixelSize"))
            assert label_text.property("font").pixelSize() == 17, label_text.property("font").pixelSize()
            assert label_text.property("font").weight() == int(typography.property("edgeLabelFontWeight")), (
                label_text.property("font").weight(),
                int(typography.property("edgeLabelFontWeight")),
            )

            view.set_zoom(1.0)
            settle_canvas_redraw()

            assert label_item.property("labelMode") == "pill", label_item.property("labelMode")
            assert label_text.property("font").pixelSize() == 18, label_text.property("font").pixelSize()
            assert label_text.property("font").weight() == int(typography.property("edgePillFontWeight")), (
                label_text.property("font").weight(),
                int(typography.property("edgePillFontWeight")),
            )
            """,
        )

    def test_graph_canvas_flow_edge_labels_cull_offscreen_edges_until_viewport_moves(
        self,
    ) -> None:
        self._run_qml_probe(
            "flow-edge-label-viewport-cull",
            """
            off_source_id = scene.add_node_from_type("tests.flow_edge_label_probe_node", 4200.0, 3300.0)
            off_target_id = scene.add_node_from_type("tests.flow_edge_label_probe_node", 4680.0, 3420.0)
            off_edge_id = scene.add_edge(off_source_id, "flow_out", off_target_id, "flow_in")
            scene.set_edge_label(off_edge_id, "Offscreen path")
            scene.set_edge_visual_style(
                off_edge_id,
                {
                    "stroke_pattern": "dashed",
                    "arrow_head": "open",
                    "stroke_width": 3,
                    "stroke_color": "#335577",
                    "label_text_color": "#f0f4fb",
                    "label_background_color": "#223344",
                },
            )
            app.processEvents()
            settle_canvas_redraw()

            labels = named_child_items(edge_layer, "graphEdgeFlowLabelItem")
            assert len(labels) == 1
            labels_by_text = {item.property("labelText"): item for item in labels}
            assert set(labels_by_text) == {"Primary path"}
            snapshots = to_variant(edge_layer.property("_visibleEdgeSnapshots"))
            assert len(snapshots) == 1

            visible_label = labels_by_text["Primary path"]
            visible_snapshot = assert_flow_label_snapshot_consistency(edge_layer, visible_label, edge_id)
            culled_snapshot = to_variant(edge_layer._visibleEdgeSnapshot(off_edge_id))
            assert visible_snapshot["culled"] is False
            assert culled_snapshot is not None
            assert culled_snapshot["culled"] is True
            assert visible_label.isVisible()
            assert "Offscreen path" not in labels_by_text
            assert edge_layer.edgeAtScreen(edge_layer.sceneToScreenX(4440.0), edge_layer.sceneToScreenY(3360.0)) == ""

            view.centerOn(4440.0, 3360.0)
            settle_canvas_redraw()

            labels = named_child_items(edge_layer, "graphEdgeFlowLabelItem")
            labels_by_text = {item.property("labelText"): item for item in labels}
            assert set(labels_by_text) == {"Offscreen path"}
            revealed_label = labels_by_text["Offscreen path"]
            revealed_snapshot = assert_flow_label_snapshot_consistency(edge_layer, revealed_label, off_edge_id)
            revealed_anchor = to_variant(edge_layer._edgeAnchor(revealed_snapshot["geometry"], 0.5))
            assert revealed_anchor is not None
            assert revealed_snapshot["culled"] is False
            assert revealed_label.isVisible()
            assert not bool(revealed_label.property("culledByViewport"))
            assert revealed_label.property("geometry") is not None
            assert revealed_label.property("labelAnchor") is not None
            assert revealed_label.property("labelAnchorScene") is not None
            primary_snapshot = to_variant(edge_layer._visibleEdgeSnapshot(edge_id))
            assert primary_snapshot is not None
            assert primary_snapshot["culled"] is True
            assert "Primary path" not in labels_by_text
            assert edge_layer.edgeAtScreen(
                edge_layer.sceneToScreenX(revealed_anchor["x"]),
                edge_layer.sceneToScreenY(revealed_anchor["y"]),
            ) == off_edge_id

            """,
        )

    def test_graph_canvas_flow_edge_hit_testing_keeps_screen_pick_threshold_across_zoom(
        self,
    ) -> None:
        self._run_qml_probe(
            "flow-edge-hit-threshold",
            """
            labels = named_child_items(edge_layer, "graphEdgeFlowLabelItem")
            assert len(labels) == 1
            geometry = to_variant(labels[0].property("geometry"))
            assert geometry is not None
            anchor = to_variant(edge_layer._edgeAnchor(geometry, 0.5))
            assert anchor is not None

            view.centerOn(anchor["x"], anchor["y"])
            app.processEvents()
            app.processEvents()
            assert_edge_screen_hit(edge_layer, edge_id, anchor)

            view.set_zoom(2.0)
            app.processEvents()
            app.processEvents()
            assert_edge_screen_hit(edge_layer, edge_id, anchor)

            view.set_zoom(0.5)
            app.processEvents()
            app.processEvents()
            assert_edge_screen_hit(edge_layer, edge_id, anchor)

            """,
        )

    def test_graph_canvas_pipe_flow_edge_hit_testing_keeps_screen_pick_threshold_across_zoom(
        self,
    ) -> None:
        self._run_qml_probe(
            "flow-pipe-edge-hit-threshold",
            """
            pipe_source_id = scene.add_node_from_type("passive.flowchart.process", 520.0, 40.0)
            pipe_target_id = scene.add_node_from_type("passive.flowchart.process", 544.0, 260.0)
            pipe_edge_id = scene.add_edge(pipe_source_id, "bottom", pipe_target_id, "top")
            app.processEvents()
            settle_canvas_redraw()

            pipe_payload = edges_by_id(scene)[pipe_edge_id]
            pipe_snapshot = to_variant(edge_layer._visibleEdgeSnapshot(pipe_edge_id))
            assert pipe_snapshot is not None
            pipe_geometry = pipe_snapshot["geometry"]
            assert pipe_geometry["route"] == "pipe"
            assert pipe_geometry["pipe_points"] == pipe_payload["pipe_points"]
            anchor = to_variant(edge_layer._edgeAnchor(pipe_geometry, 0.5))
            assert anchor is not None

            def assert_pipe_edge_screen_hit(edge_id, anchor_payload):
                screen_x = edge_layer.sceneToScreenX(anchor_payload["x"])
                screen_y = edge_layer.sceneToScreenY(anchor_payload["y"])
                normal_x = -anchor_payload["dy"]
                normal_y = anchor_payload["dx"]
                assert edge_layer.edgeAtScreen(screen_x, screen_y) == edge_id
                assert edge_layer.edgeAtScreen(
                    screen_x + normal_x * 6.0,
                    screen_y + normal_y * 6.0,
                ) == edge_id

            view.centerOn(anchor["x"], anchor["y"])
            settle_canvas_redraw()
            assert_pipe_edge_screen_hit(pipe_edge_id, anchor)

            view.set_zoom(2.0)
            settle_canvas_redraw()
            assert_pipe_edge_screen_hit(pipe_edge_id, anchor)

            view.set_zoom(0.5)
            settle_canvas_redraw()
            assert_pipe_edge_screen_hit(pipe_edge_id, anchor)

            """,
        )

    def test_graph_canvas_flow_edge_path_mode_command_updates_keep_label_editing(
        self,
    ) -> None:
        self._run_qml_probe(
            "flow-path-mode-command-label-editing",
            """
            toolbar = canvas.findChild(QObject, "graphEdgeFloatingToolbar")
            assert toolbar is not None

            # Prime the payload cache before replacing rebuild_models with a recorder.
            assert edges_by_id(scene)[edge_id]["edge_id"] == edge_id

            rebuild_calls = []
            original_rebuild_models = scene._scene_context.rebuild_models

            def recording_rebuild_models():
                rebuild_calls.append(True)
                original_rebuild_models()

            scene._scene_context.rebuild_models = recording_rebuild_models
            try:
                def assert_updated_edge_delta(expected_mode=None, expected_label=None):
                    delta = scene.edge_delta_payload
                    assert delta["schema"] == "graph_scene_edge_structural_delta"
                    assert delta["updated_edge_ids"] == [edge_id], delta
                    assert delta["added_edge_ids"] == [], delta
                    assert delta["removed_edge_ids"] == [], delta
                    assert delta["dirty_edge_ids"] == [edge_id], delta
                    assert sorted(delta["dirty_node_ids"]) == sorted([source_id, target_id]), delta
                    assert len(delta["updated_edges"]) == 1, delta
                    payload = delta["updated_edges"][0]["payload"]
                    assert payload["edge_id"] == edge_id, payload
                    if expected_mode is not None:
                        assert payload["path_mode"] == expected_mode, payload
                        assert payload["visual_style"].get("path_mode") == expected_mode, payload
                    if expected_label is not None:
                        assert payload["label"] == expected_label, payload
                    return payload

                def assert_path_mode_update(mode):
                    assert canvas_command_bridge.set_edge_visual_style(edge_id, {"path_mode": mode})
                    assert_updated_edge_delta(expected_mode=mode)
                    app.processEvents()
                    settle_canvas_redraw()
                    payload = edges_by_id(scene)[edge_id]
                    assert payload["path_mode"] == mode, payload
                    assert payload["route"] == mode, payload
                    snapshot = to_variant(edge_layer._visibleEdgeSnapshot(edge_id))
                    assert snapshot is not None, mode
                    geometry = snapshot["geometry"]
                    assert geometry is not None, mode
                    assert geometry["route"] == mode, geometry
                    anchor = to_variant(edge_layer._edgeAnchor(geometry, 0.5))
                    assert anchor is not None, mode
                    assert_edge_screen_hit(edge_layer, edge_id, anchor)
                    assert toolbar.beginLabelEdit(edge_id), mode
                    assert toolbar.property("editingEdgeId") == edge_id
                    assert toolbar.cancelLabelEdit()

                assert_path_mode_update("bezier")
                assert_path_mode_update("pipe")

                assert canvas_command_bridge.set_edge_label(edge_id, "Forced path label")
                assert_updated_edge_delta(expected_label="Forced path label")
                app.processEvents()
                settle_canvas_redraw()
                assert edges_by_id(scene)[edge_id]["label"] == "Forced path label"
                assert toolbar.beginLabelEdit(edge_id)
                assert toolbar.property("editingEdgeId") == edge_id
                assert toolbar.cancelLabelEdit()
            finally:
                scene._scene_context.rebuild_models = original_rebuild_models

            assert rebuild_calls == []

            """,
        )

    def test_edge_layer_gap_break_uses_payload_order_for_plain_bezier_crossings(
        self,
    ) -> None:
        self._run_edge_layer_probe(
            "edge-layer-gap-break-bezier-payload-order",
            """
            def bezier_edge(edge_id, sx, sy, tx, ty):
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

            edge_layer.setProperty(
                "edges",
                [
                    bezier_edge("payload_first", 80.0, 80.0, 320.0, 320.0),
                    bezier_edge("payload_second", 80.0, 320.0, 320.0, 80.0),
                ],
            )
            edge_layer.setProperty("edgeCrossingStyle", "gap_break")
            refresh(edge_layer)

            first = snapshot(edge_layer, "payload_first")
            second = snapshot(edge_layer, "payload_second")
            assert first["drawOrderIndex"] == 0
            assert second["drawOrderIndex"] == 1
            assert len(first["crossingBreaks"]) >= 1
            assert second["crossingBreaks"] == []
            assert first["crossingSamplePoints"]
            assert first["crossingBreaks"][0]["centerDistance"] > first["crossingBreaks"][0]["startDistance"]

            hidden_over = bezier_edge("hidden_over", 80.0, 320.0, 320.0, 80.0)
            hidden_over.update({
                "active_data_wire": True,
                "enabled": True,
                "data_access": "item",
                "visual_style": {"display_mode": "hidden"},
            })
            edge_layer.setProperty(
                "edges",
                [
                    bezier_edge("visible_under", 80.0, 80.0, 320.0, 320.0),
                    hidden_over,
                ],
            )
            refresh(edge_layer)
            assert snapshot(edge_layer, "visible_under")["crossingBreaks"] == []
            assert snapshot(edge_layer, "hidden_over")["crossingBreaks"] == []

            edge_layer.setProperty("selectedEdgeIds", ["hidden_over"])
            refresh(edge_layer)
            assert snapshot(edge_layer, "visible_under")["crossingBreaks"] == []
            assert snapshot(edge_layer, "hidden_over")["crossingBreaks"] == []

            edge_layer.setProperty("selectedEdgeIds", [])
            edge_layer.setProperty("wireSelectionModeHeld", True)
            refresh(edge_layer)
            assert snapshot(edge_layer, "hidden_over")["hiddenUnrevealed"] is False
            assert snapshot(edge_layer, "visible_under")["crossingBreaks"] == []
            assert snapshot(edge_layer, "hidden_over")["crossingBreaks"] == []

            """,
        )

    def test_edge_layer_gap_break_preserves_bezier_hit_testing_inside_visual_gap(
        self,
    ) -> None:
        self._run_edge_layer_probe(
            "edge-layer-gap-break-bezier-hit-testing",
            """
            def bezier_edge(edge_id, sx, sy, tx, ty):
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

            under_edge_id = "bezier_under"
            over_edge_id = "bezier_over"
            edge_layer.setProperty(
                "edges",
                [
                    bezier_edge(under_edge_id, 80.0, 80.0, 320.0, 320.0),
                    bezier_edge(over_edge_id, 80.0, 320.0, 320.0, 80.0),
                ],
            )
            edge_layer.setProperty("edgeCrossingStyle", "gap_break")
            view.centerOn(200.0, 200.0)
            refresh(edge_layer)

            under = snapshot(edge_layer, under_edge_id)
            over = snapshot(edge_layer, over_edge_id)
            assert under["drawOrderIndex"] == 0
            assert over["drawOrderIndex"] == 1
            assert len(under["crossingBreaks"]) >= 1
            assert over["crossingBreaks"] == []

            center_break = under["crossingBreaks"][0]
            center_screen_x = edge_layer.sceneToScreenX(center_break["centerX"])
            center_screen_y = edge_layer.sceneToScreenY(center_break["centerY"])
            assert edge_layer.edgeAtScreen(center_screen_x, center_screen_y) == over_edge_id

            for zoom in (1.0, 2.0, 0.5):
                view.set_zoom(zoom)
                app.processEvents()
                refresh(edge_layer)
                under = snapshot(edge_layer, under_edge_id)
                center_break = under["crossingBreaks"][0]
                scene_offset = 3.0 / float(view.zoom_value)
                gap_scene_x = center_break["centerX"] + center_break["tangentX"] * scene_offset
                gap_scene_y = center_break["centerY"] + center_break["tangentY"] * scene_offset
                gap_screen_x = edge_layer.sceneToScreenX(gap_scene_x)
                gap_screen_y = edge_layer.sceneToScreenY(gap_scene_y)
                assert edge_layer.edgeAtScreen(gap_screen_x, gap_screen_y) == under_edge_id

            """,
        )

    def test_graph_canvas_flow_edge_preview_geometry_uses_origin_side_for_neutral_flowchart_ports(
        self,
    ) -> None:
        self._run_qml_probe(
            "flowchart-preview-origin-side",
            """
            flow_source_id = scene.add_node_from_type("passive.flowchart.process", 520.0, 40.0)
            flow_target_id = scene.add_node_from_type("passive.flowchart.process", 760.0, 220.0)
            app.processEvents()

            nodes_by_id = {item["node_id"]: item for item in scene.nodes_model}
            source_point = to_variant(edge_layer._portScenePoint(nodes_by_id[flow_source_id], "top"))
            target_point = to_variant(edge_layer._portScenePoint(nodes_by_id[flow_target_id], "left"))
            assert source_point is not None
            assert target_point is not None

            canvas.beginPortWireDrag(
                flow_source_id,
                "top",
                "neutral",
                source_point["x"],
                source_point["y"],
                320.0,
                180.0,
                0,
            )
            canvas.updatePortWireDrag(
                flow_source_id,
                "top",
                "neutral",
                source_point["x"],
                source_point["y"],
                420.0,
                260.0,
                True,
                0,
            )
            canvas.setProperty(
                "wireDropCandidate",
                {
                    "node_id": flow_target_id,
                    "port_key": "left",
                    "direction": "neutral",
                    "side": "left",
                    "scene_x": target_point["x"],
                    "scene_y": target_point["y"],
                    "valid_drop": True,
                },
            )
            app.processEvents()

            preview = to_variant(canvas.wireDragPreviewConnection())
            assert preview is not None
            assert preview["origin_side"] == "top"
            assert preview["target_side"] == "left"
            assert bool(preview["valid_drop"])

            geometry = to_variant(edge_layer._dragGeometry(preview))
            assert geometry is not None
            assert geometry["route"] == "pipe"
            assert abs(geometry["sx"] - source_point["x"]) < 0.001
            assert abs(geometry["sy"] - source_point["y"]) < 0.001
            pipe_points = geometry["pipe_points"]
            assert pipe_points[0] == {"x": source_point["x"], "y": source_point["y"]}
            assert pipe_points[-1] == {"x": target_point["x"], "y": target_point["y"]}
            assert abs(pipe_points[1]["x"] - source_point["x"]) < 0.001
            assert pipe_points[1]["y"] < source_point["y"]
            assert pipe_points[-2]["x"] < target_point["x"]
            assert abs(pipe_points[-2]["y"] - target_point["y"]) < 0.001

            assert canvas.cancelWireDrag()
            app.processEvents()
            app.processEvents()

            """,
        )

if __name__ == "__main__":
    unittest.main()
