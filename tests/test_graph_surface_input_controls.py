from __future__ import annotations

from pathlib import Path
import unittest

from PyQt6.QtCore import QObject, pyqtSignal

from ea_node_editor.graph.effective_ports import visible_ports
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.node_specs import (
    NodeRenderQualitySpec,
    NodeTypeSpec,
    PortSpec,
    PropertySpec,
)
from ea_node_editor.ui.shell.presenters.state import build_default_shell_workspace_ui_state
from ea_node_editor.ui.shell.presenters.workspace_presenter import ShellWorkspacePresenter
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from ea_node_editor.ui_qml.graph_geometry.standard_metrics import (
    node_surface_metrics,
    resolved_node_surface_size,
    standard_inline_body_height,
    standard_inline_label_anchor_offset,
    standard_inline_row_height,
    standard_inline_slider_row_height,
    standard_inline_stacked_row_height,
    standard_inline_textarea_row_height,
)
from ea_node_editor.ui_qml.graph_geometry.surface_contract import (
    STANDARD_BOTTOM_PADDING,
    STANDARD_COLLAPSED_WIDTH,
    STANDARD_DEFAULT_WIDTH,
    VIEWER_LEGACY_DEFAULT_BODY_HEIGHTS,
)
from ea_node_editor.ui_qml.graph_surface_metrics import surface_port_local_point
from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
from ea_node_editor.ui_qml.surface_contracts import surface_spec_payload_for_node_type
from tests.graph_surface.environment import GraphSurfaceInputContractTestBase

_REPO_ROOT = Path(__file__).resolve().parents[1]


class _ViewerSurfacePlugin:
    def __init__(self, spec: NodeTypeSpec) -> None:
        self._spec = spec

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult()


def _viewer_surface_spec() -> NodeTypeSpec:
    return NodeTypeSpec(
        type_id="tests.viewer_surface_input_controls",
        display_name="Viewer Controls",
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


class GraphSurfaceInputControlsTests(unittest.TestCase):
    def test_python_script_floating_toolbar_surface_fullscreen_action_contract(self) -> None:
        spec = build_default_registry().get_spec("core.python_script")
        payload = surface_spec_payload_for_node_type(type_id="core.python_script", spec=spec)
        surface_source = (_REPO_ROOT / "ea_node_editor/ui_qml/components/graph/GraphStandardNodeSurface.qml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(payload["qml_component"], "GraphStandardNodeSurface.qml")
        self.assertTrue(payload["fullscreen"]["supported"])
        self.assertEqual(payload["fullscreen"]["content_kind"], "script_editor")
        self.assertEqual(payload["fullscreen"]["action_label"], "Open script")
        self.assertEqual(payload["fullscreen"]["action_icon"], "code")
        self.assertIn("host.surfaceFullscreenAction", surface_source)
        self.assertIn("host.requestSurfaceContentFullscreen", surface_source)

    def test_python_script_decorator_ports_reserve_only_resting_add_dots(self) -> None:
        registry = build_default_registry()
        properties = registry.default_properties("core.python_script")
        spec = registry.resolve_spec("core.python_script", properties)
        node = NodeInstance(
            node_id="node_python_script_decorator_metrics",
            type_id=spec.type_id,
            title=spec.display_name,
            x=32.0,
            y=48.0,
            properties=properties,
        )
        metrics = node_surface_metrics(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
        )
        self.assertEqual([group.group_id for group in spec.dynamic_port_groups], ["inputs", "outputs"])
        self.assertAlmostEqual(
            metrics.body_bottom_margin,
            max(
                STANDARD_BOTTOM_PADDING,
                metrics.port_center_offset + 9.0 + 3.0 + 4.0 - metrics.port_height,
            ),
        )

        static_spec = NodeTypeSpec(
            type_id="tests.static_height_unchanged_by_dynamic_controls",
            display_name="Static Height",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec("payload", "in", "data", 'COREX.DataTypes.Any'),
                PortSpec("result", "out", "data", 'COREX.DataTypes.Any'),
            ),
            properties=(),
        )
        static_node = NodeInstance(
            node_id="node_static_height_unchanged_by_dynamic_controls",
            type_id=static_spec.type_id,
            title=static_spec.display_name,
            x=32.0,
            y=48.0,
        )
        static_metrics = node_surface_metrics(
            static_node,
            static_spec,
            {static_node.node_id: static_node},
            graph_label_pixel_size=16,
        )
        self.assertEqual(
            float(static_metrics.body_bottom_margin),
            float(STANDARD_BOTTOM_PADDING),
        )
        self.assertAlmostEqual(
            float(static_metrics.default_height),
            float(static_metrics.body_top)
            + float(static_metrics.body_height)
            + float(static_metrics.port_height)
            + float(STANDARD_BOTTOM_PADDING),
            places=6,
        )


class GraphNodeCommonActionTests(GraphSurfaceInputContractTestBase):
    def test_frame_node_common_action_frames_node_bounds_without_mutation_dispatch(self) -> None:
        self._run_qml_probe(
            "frame-node-common-action",
            """
            canvas_component = QQmlComponent(engine)
            canvas_component.setData(
                b'''
                import QtQuick 2.15

                Item {
                    objectName: "frameNodeCanvasStub"
                    property int frameCallCount: 0
                    property var lastFrameRect: ({})
                    property real lastFramePadding: -1.0

                    function frameSceneRectPayload(rectLike, paddingPx) {
                        frameCallCount += 1
                        lastFrameRect = {
                            "x": Number(rectLike.x),
                            "y": Number(rectLike.y),
                            "width": Number(rectLike.width),
                            "height": Number(rectLike.height)
                        }
                        lastFramePadding = Number(paddingPx)
                        return true
                    }
                }
                ''',
                QUrl.fromLocalFile(str(repo_root) + "/"),
            )
            if canvas_component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in canvas_component.errors())
                raise AssertionError("Failed to load canvas stub QML:\\n" + errors)
            canvas_item = canvas_component.create()
            if canvas_item is None:
                errors = "\\n".join(error.toString() for error in canvas_component.errors())
                raise AssertionError("Failed to instantiate canvas stub QML:\\n" + errors)

            payload = node_payload()
            payload["x"] = 123.5
            payload["y"] = 234.25
            payload["width"] = 210.0
            payload["height"] = 88.0
            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": payload, "canvasItem": canvas_item},
            )

            common_actions = [variant_value(action) for action in variant_list(host.property("commonNodeActions"))]
            assert common_actions[0]["id"] == "frame_node"
            assert common_actions[0]["label"] == "Zoom to node"
            assert common_actions[0]["icon"] == "zoom-fit"
            assert common_actions[0]["kind"] == "common"
            assert common_actions[0]["enabled"] is True

            requested_actions = []
            host.nodeActionRequested.connect(
                lambda node_id, action_id, action_payload: requested_actions.append((node_id, action_id, action_payload))
            )

            assert bool(host.frameNodeInView()) is True
            settle_events(2)
            frame_rect = variant_value(canvas_item.property("lastFrameRect"))
            assert int(canvas_item.property("frameCallCount")) == 1
            assert frame_rect == {"x": 123.5, "y": 234.25, "width": 210.0, "height": 88.0}, frame_rect
            assert float(canvas_item.property("lastFramePadding")) == 80.0
            assert requested_actions == []

            host.dispatchNodeAction("frame_node", {"ignored": True})
            settle_events(2)
            assert int(canvas_item.property("frameCallCount")) == 2
            assert requested_actions == []

            host.deleteLater()
            canvas_item.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )




class GraphSurfaceInlineMetricTypographyTests(unittest.TestCase):
    def _viewer_registry(self) -> tuple[NodeRegistry, NodeTypeSpec]:
        spec = _viewer_surface_spec()
        registry = build_default_registry()
        registry.register(lambda: _ViewerSurfacePlugin(spec))
        return registry, spec

    def test_standard_inline_enum_metrics_reserve_longest_option_width(self) -> None:
        spec = NodeTypeSpec(
            type_id="tests.standard_inline_enum_width",
            display_name="Inline Enum Width",
            category_path=("Tests",),
            icon="",
            ports=(),
            properties=(
                PropertySpec(
                    "mode",
                    "enum",
                    "short",
                    "Mode",
                    enum_values=("short", "super_long_option_value_here"),
                    inline_editor="enum",
                    inspector_editor="enum",
                ),
            ),
        )
        node = NodeInstance(
            node_id="node_standard_inline_enum_width",
            type_id=spec.type_id,
            title="Inline Enum Width",
            x=32.0,
            y=48.0,
        )

        metrics = node_surface_metrics(node, spec, {node.node_id: node})
        resolved_width, _height = resolved_node_surface_size(node, spec, {node.node_id: node})

        self.assertGreater(metrics.default_width, 210.0)
        self.assertGreater(metrics.min_width, 210.0)
        self.assertEqual(resolved_width, metrics.default_width)

        node.custom_width = 150.0
        clamped_width, _height = resolved_node_surface_size(node, spec, {node.node_id: node})
        self.assertEqual(clamped_width, metrics.min_width)

    def test_standard_node_default_width_grows_to_full_title_at_large_graph_label_size(self) -> None:
        spec = NodeTypeSpec(
            type_id="tests.standard_full_title_width",
            display_name="Materialize Filtered Table",
            category_path=("Tests",),
            icon="table",
            ports=(
                PortSpec("window", "in", "data", 'COREX.Runtime.TabularWindowRef', label="Window"),
                PortSpec("rows", "out", "data", "records", label="Rows"),
            ),
            properties=(),
        )
        node = NodeInstance(
            node_id="node_standard_full_title_width",
            type_id=spec.type_id,
            title=spec.display_name,
            x=32.0,
            y=48.0,
        )

        large_metrics = node_surface_metrics(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=16,
        )
        resolved_width, _height = resolved_node_surface_size(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=16,
            surface_metrics=large_metrics,
        )

        self.assertGreater(large_metrics.standard_title_full_width, 210.0)
        self.assertAlmostEqual(large_metrics.default_width, large_metrics.min_width, places=6)
        self.assertGreaterEqual(large_metrics.default_width, large_metrics.standard_title_full_width)
        self.assertAlmostEqual(resolved_width, large_metrics.default_width, places=6)

    def test_standard_node_title_metrics_shrink_after_shortened_title(self) -> None:
        spec = NodeTypeSpec(
            type_id="tests.standard_title_width_shrinks",
            display_name="Standard Title Width Shrinks",
            category_path=("Tests",),
            icon="",
            ports=(),
            properties=(),
        )
        node = NodeInstance(
            node_id="node_standard_title_width_shrinks",
            type_id=spec.type_id,
            title="Superconducting Cryogenic Feed Line Pressure Telemetry Resolver",
            x=32.0,
            y=48.0,
        )

        long_metrics = node_surface_metrics(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=16,
        )
        node.title = "Log"
        short_metrics = node_surface_metrics(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=16,
        )
        resolved_width, _height = resolved_node_surface_size(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=16,
            surface_metrics=short_metrics,
        )

        self.assertGreater(long_metrics.standard_title_full_width, STANDARD_DEFAULT_WIDTH)
        self.assertGreater(long_metrics.min_width, short_metrics.min_width)
        self.assertEqual(short_metrics.default_width, STANDARD_DEFAULT_WIDTH)
        self.assertAlmostEqual(resolved_width, short_metrics.default_width, places=6)

    def test_standard_node_initial_metrics_reserve_title_icon_ports_and_body_surface(self) -> None:
        registry = build_default_registry()
        script_spec = registry.get_spec("core.python_script")
        script_node = NodeInstance(
            node_id="node_python_script_initial_metrics",
            type_id=script_spec.type_id,
            title=script_spec.display_name,
            x=32.0,
            y=48.0,
        )

        baseline_script_metrics = node_surface_metrics(
            script_node,
            script_spec,
            {script_node.node_id: script_node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=16,
        )
        large_icon_script_metrics = node_surface_metrics(
            script_node,
            script_spec,
            {script_node.node_id: script_node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )

        self.assertEqual(large_icon_script_metrics.port_height, 24.0)
        self.assertEqual(large_icon_script_metrics.port_center_offset, 12.0)
        self.assertGreater(
            large_icon_script_metrics.standard_title_full_width,
            baseline_script_metrics.standard_title_full_width,
        )
        self.assertGreaterEqual(
            large_icon_script_metrics.min_width,
            large_icon_script_metrics.standard_title_full_width,
        )

        tabular_spec = registry.spec_or_none("tabular.input")
        if tabular_spec is None:
            self.skipTest("tabular.input add-on is not registered in the default registry")
        tabular_node = NodeInstance(
            node_id="node_tabular_input_initial_metrics",
            type_id=tabular_spec.type_id,
            title=tabular_spec.display_name,
            x=32.0,
            y=48.0,
        )

        tabular_metrics = node_surface_metrics(
            tabular_node,
            tabular_spec,
            {tabular_node.node_id: tabular_node},
            graph_label_pixel_size=10,
        )
        resolved_width, resolved_height = resolved_node_surface_size(
            tabular_node,
            tabular_spec,
            {tabular_node.node_id: tabular_node},
            graph_label_pixel_size=10,
        )
        input_ports, output_ports = visible_ports(
            node=tabular_node,
            spec=tabular_spec,
            workspace_nodes={tabular_node.node_id: tabular_node},
        )
        visible_port_count = max(len(input_ports), len(output_ports), 1)
        expected_height = (
            float(tabular_metrics.body_top)
            + float(tabular_metrics.body_height)
            + visible_port_count * float(tabular_metrics.port_height)
            + float(tabular_metrics.body_bottom_margin)
        )

        self.assertGreaterEqual(tabular_metrics.body_height, 128.0)
        self.assertGreaterEqual(tabular_metrics.default_width, 336.0)
        self.assertAlmostEqual(tabular_metrics.default_height, expected_height, places=6)
        self.assertEqual(tabular_metrics.min_height, tabular_metrics.default_height)
        self.assertEqual(resolved_width, tabular_metrics.default_width)
        self.assertEqual(resolved_height, tabular_metrics.default_height)

        resized_tabular_node = tabular_node.clone()
        resized_tabular_node.custom_height = tabular_metrics.default_height + 96.0
        resized_tabular_metrics = node_surface_metrics(
            resized_tabular_node,
            tabular_spec,
            {resized_tabular_node.node_id: resized_tabular_node},
            graph_label_pixel_size=10,
        )

        self.assertEqual(resized_tabular_metrics.default_height, tabular_metrics.default_height)
        self.assertEqual(resized_tabular_metrics.min_height, tabular_metrics.min_height)
        self.assertAlmostEqual(resized_tabular_metrics.body_height, tabular_metrics.body_height + 96.0, places=6)
        self.assertAlmostEqual(resized_tabular_metrics.port_top, tabular_metrics.port_top + 96.0, places=6)

    def test_standard_collapsed_width_grows_to_fit_long_title(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec("core.logger")
        short_node = NodeInstance(
            node_id="node_standard_collapsed_short_title",
            type_id=spec.type_id,
            title="Log",
            x=32.0,
            y=48.0,
        )
        long_node = NodeInstance(
            node_id="node_standard_collapsed_long_title",
            type_id=spec.type_id,
            title="Reaction Force Probe Result Summary",
            x=32.0,
            y=48.0,
        )

        short_metrics = node_surface_metrics(short_node, spec, {short_node.node_id: short_node})
        long_metrics = node_surface_metrics(long_node, spec, {long_node.node_id: long_node})

        # A short title keeps the compact standard collapsed chip width.
        self.assertEqual(short_metrics.collapsed_width, STANDARD_COLLAPSED_WIDTH)
        # A long title grows the collapsed chip so the full name stays visible.
        self.assertGreater(long_metrics.collapsed_width, STANDARD_COLLAPSED_WIDTH)
        self.assertGreater(long_metrics.collapsed_width, short_metrics.collapsed_width)

        # The resolved collapsed size feeds routing/hit-testing the same fitted width.
        collapsed_long_node = long_node.clone()
        collapsed_long_node.collapsed = True
        resolved_width, _height = resolved_node_surface_size(
            collapsed_long_node,
            spec,
            {collapsed_long_node.node_id: collapsed_long_node},
        )
        self.assertAlmostEqual(resolved_width, long_metrics.collapsed_width, places=6)

    def test_standard_inline_surface_metrics_exclude_port_defaults_and_follow_graph_label_size(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec("core.logger")

        default_body_height = standard_inline_body_height(spec, graph_label_pixel_size=10)
        large_body_height = standard_inline_body_height(spec, graph_label_pixel_size=16)

        self.assertEqual(standard_inline_row_height(10), 26.0)
        self.assertEqual(standard_inline_stacked_row_height(10), 56.0)
        self.assertEqual(standard_inline_slider_row_height(10), 66.0)
        self.assertEqual(standard_inline_label_anchor_offset(10), 13.0)
        self.assertEqual(standard_inline_textarea_row_height(10), 104.0)
        self.assertEqual(standard_inline_row_height(16), 32.0)
        self.assertEqual(standard_inline_stacked_row_height(16), 68.0)
        self.assertEqual(standard_inline_slider_row_height(16), 84.0)
        self.assertEqual(standard_inline_label_anchor_offset(16), 16.0)
        self.assertEqual(standard_inline_textarea_row_height(16), 128.0)
        self.assertEqual(default_body_height, 64.0)
        self.assertEqual(large_body_height, 76.0)
        self.assertGreater(large_body_height, default_body_height)

        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        node = model.add_node(workspace_id, "core.logger", "Logger", 32.0, 48.0)

        default_metrics = node_surface_metrics(node, spec, graph_label_pixel_size=10)
        large_metrics = node_surface_metrics(node, spec, graph_label_pixel_size=16)
        large_icon_metrics = node_surface_metrics(
            node,
            spec,
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )
        first_input_port_key = next(port.key for port in spec.ports if port.direction == "in")
        baseline_port_point = surface_port_local_point(
            node,
            spec,
            first_input_port_key,
            {node.node_id: node},
            graph_label_pixel_size=16,
        )
        large_icon_port_point = surface_port_local_point(
            node,
            spec,
            first_input_port_key,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )

        self.assertEqual(default_metrics.body_height, 64.0)
        self.assertEqual(large_metrics.body_height, 76.0)
        self.assertGreater(large_metrics.default_height, default_metrics.default_height)
        self.assertEqual(large_icon_metrics.header_height, 50.0)
        self.assertEqual(large_icon_metrics.title_height, 50.0)
        self.assertEqual(large_icon_metrics.body_top - large_metrics.body_top, 26.0)
        self.assertEqual(large_icon_metrics.port_top - large_metrics.port_top, 26.0)
        self.assertEqual(large_icon_metrics.default_height - large_metrics.default_height, 26.0)
        self.assertEqual(large_icon_port_point[1] - baseline_port_point[1], 26.0)

    def test_default_port_stacked_rows_anchor_grips_to_the_label_line(self) -> None:
        model = GraphModel()
        registry = build_default_registry()
        workspace_id = model.active_workspace.workspace_id
        model.add_node(
            workspace_id,
            "math.construct_interval",
            "Construct Interval",
            32.0,
            48.0,
        )

        builder = GraphScenePayloadBuilder()
        nodes_payload, _backdrops, _minimap, _edges = builder.rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )

        self.assertEqual(len(nodes_payload), 1)
        payload = nodes_payload[0]
        node = model.project.workspaces[workspace_id].nodes[payload["node_id"]]
        spec = registry.get_spec(node.type_id)
        resolved_width, resolved_height = resolved_node_surface_size(
            node,
            spec,
            {node.node_id: node},
        )
        inputs = {
            str(port["key"]): port
            for port in payload["ports"]
            if str(port["direction"]) == "in"
        }
        start_anchor = inputs["start"]["presentation_anchor"]
        end_anchor = inputs["end"]["presentation_anchor"]
        port_top = float(payload["surface_metrics"]["port_top"])
        label_offset = standard_inline_label_anchor_offset(10)

        self.assertEqual(inputs["start"]["default_property"]["inline_editor"], "number")
        self.assertEqual(float(payload["width"]), resolved_width)
        self.assertEqual(float(payload["height"]), resolved_height)
        self.assertEqual(float(start_anchor["x"]), 0.0)
        self.assertEqual(float(end_anchor["x"]), 0.0)
        self.assertEqual(float(start_anchor["y"]), port_top + label_offset)
        self.assertEqual(float(end_anchor["y"]), port_top + 4.0 * 18.0 + label_offset)

    def test_viewer_surface_metrics_follow_graph_title_icon_size(self) -> None:
        spec = _viewer_surface_spec()
        node = NodeInstance(
            node_id="node_viewer_surface_input_controls",
            type_id=spec.type_id,
            title="Viewer Controls",
            x=32.0,
            y=48.0,
        )

        default_metrics = node_surface_metrics(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
        )
        large_icon_metrics = node_surface_metrics(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )
        baseline_port_point = surface_port_local_point(
            node,
            spec,
            "scene",
            {node.node_id: node},
            graph_label_pixel_size=16,
        )
        large_icon_port_point = surface_port_local_point(
            node,
            spec,
            "scene",
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )

        self.assertEqual(default_metrics.header_height, 24.0)
        self.assertEqual(default_metrics.body_top, 30.0)
        self.assertEqual(large_icon_metrics.header_height, 50.0)
        self.assertEqual(large_icon_metrics.title_height, 50.0)
        self.assertEqual(large_icon_metrics.body_top - default_metrics.body_top, 26.0)
        self.assertEqual(large_icon_metrics.port_top - default_metrics.port_top, 26.0)
        self.assertEqual(large_icon_metrics.default_height - default_metrics.default_height, 26.0)
        self.assertEqual(large_icon_metrics.body_height, default_metrics.body_height)
        self.assertEqual(large_icon_port_point[1] - baseline_port_point[1], 26.0)

    def test_model_viewer_metrics_follow_graph_label_size_for_port_rows(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec("model.viewer")
        node = NodeInstance(
            node_id="node_model_viewer_input_controls",
            type_id=spec.type_id,
            title="Model Viewer",
            x=32.0,
            y=48.0,
        )

        default_metrics = node_surface_metrics(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=10,
            graph_node_icon_pixel_size=50,
        )
        large_metrics = node_surface_metrics(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )

        self.assertEqual(default_metrics.port_height, 18.0)
        self.assertEqual(large_metrics.port_height, 24.0)
        self.assertEqual(large_metrics.body_top, default_metrics.body_top)
        self.assertEqual(large_metrics.body_height, default_metrics.body_height)
        self.assertEqual(large_metrics.default_height - default_metrics.default_height, 12.0)
        self.assertEqual(large_metrics.min_height - default_metrics.min_height, 12.0)

    def test_scene_payload_builder_applies_title_icon_size_to_standard_nodes(self) -> None:
        class _ThemeSource:
            graphics_graph_label_pixel_size = 16
            graphics_node_title_icon_pixel_size = 50

        class _ThemeBridge:
            theme = "stitch_dark"

            def __init__(self, parent: object) -> None:
                self._parent = parent

            def parent(self) -> object:
                return self._parent

        model = GraphModel()
        registry = build_default_registry()
        workspace_id = model.active_workspace.workspace_id
        model.add_node(workspace_id, "core.logger", "Logger", 32.0, 48.0)

        builder = GraphScenePayloadBuilder()
        nodes_payload, backdrop_nodes_payload, _minimap_nodes_payload, _edges_payload = builder.rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace_id,
            scope_path=(),
            graph_theme_bridge=_ThemeBridge(_ThemeSource()),
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )

        self.assertEqual(len(backdrop_nodes_payload), 0)
        self.assertEqual(len(nodes_payload), 1)
        payload = nodes_payload[0]
        self.assertEqual(payload["surface_metrics"]["header_height"], 50.0)
        self.assertEqual(payload["surface_metrics"]["title_height"], 50.0)
        self.assertEqual(payload["surface_metrics"]["body_top"], 56.0)
        self.assertGreater(payload["height"], 50.0)

    def test_scene_payload_builder_applies_title_icon_size_to_viewer_nodes(self) -> None:
        class _ThemeSource:
            graphics_graph_label_pixel_size = 16
            graphics_node_title_icon_pixel_size = 50

        class _ThemeBridge:
            theme = "stitch_dark"

            def __init__(self, parent: object) -> None:
                self._parent = parent

            def parent(self) -> object:
                return self._parent

        registry, spec = self._viewer_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        model.add_node(workspace_id, spec.type_id, spec.display_name, 32.0, 48.0)

        builder = GraphScenePayloadBuilder()
        nodes_payload, backdrop_nodes_payload, _minimap_nodes_payload, _edges_payload = builder.rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace_id,
            scope_path=(),
            graph_theme_bridge=_ThemeBridge(_ThemeSource()),
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )

        self.assertEqual(len(backdrop_nodes_payload), 0)
        self.assertEqual(len(nodes_payload), 1)
        payload = nodes_payload[0]
        self.assertEqual(payload["surface_family"], "viewer")
        self.assertEqual(payload["surface_metrics"]["header_height"], 50.0)
        self.assertEqual(payload["surface_metrics"]["title_height"], 50.0)
        self.assertEqual(payload["surface_metrics"]["body_top"], 56.0)
        self.assertEqual(payload["viewer_surface"]["live_rect"]["y"], 56.0)
        self.assertEqual(payload["viewer_surface"]["live_rect"]["height"], 176.0)
        self.assertEqual(payload["surface_metrics"]["port_height"], 24.0)
        self.assertEqual(payload["height"], 268.0)

    def test_scene_payload_builder_reads_title_icon_size_from_workspace_presenter(self) -> None:
        class _Host(QObject):
            project_meta_changed = pyqtSignal()
            workspace_state_changed = pyqtSignal()
            graphics_preferences_changed = pyqtSignal()
            run_controls_changed = pyqtSignal()

            def __init__(self) -> None:
                super().__init__()
                self.workspace_ui_state = build_default_shell_workspace_ui_state(
                    {
                        "typography": {
                            "graph_label_pixel_size": 16,
                            "graph_node_icon_pixel_size_override": 50,
                        }
                    }
                )

        class _ThemeBridge:
            theme = "stitch_dark"

            def __init__(self, parent: object) -> None:
                self._parent = parent

            def parent(self) -> object:
                return self._parent

        host = _Host()
        workspace_presenter = ShellWorkspacePresenter(host)  # type: ignore[arg-type]
        model = GraphModel()
        registry = build_default_registry()
        workspace_id = model.active_workspace.workspace_id
        model.add_node(workspace_id, "core.logger", "Logger", 32.0, 48.0)

        builder = GraphScenePayloadBuilder()
        nodes_payload, _backdrop_nodes_payload, _minimap_nodes_payload, _edges_payload = builder.rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace_id,
            scope_path=(),
            graph_theme_bridge=_ThemeBridge(host),
            graph_label_pixel_size=workspace_presenter.graphics_graph_label_pixel_size,
            graph_node_icon_pixel_size=workspace_presenter.graphics_node_title_icon_pixel_size,
        )

        self.assertEqual(len(nodes_payload), 1)
        payload = nodes_payload[0]
        self.assertEqual(workspace_presenter.graphics_node_title_icon_pixel_size, 50)
        self.assertEqual(payload["surface_metrics"]["header_height"], 50.0)
        self.assertEqual(payload["surface_metrics"]["title_height"], 50.0)
        self.assertEqual(payload["surface_metrics"]["body_top"], 56.0)

    def test_scene_payload_builder_connection_refresh_uses_active_graph_typography(self) -> None:
        class _ThemeSource:
            graphics_graph_label_pixel_size = 16
            graphics_node_title_icon_pixel_size = 50

        class _ThemeBridge:
            theme = "stitch_dark"

            def __init__(self, parent: object) -> None:
                self._parent = parent

            def parent(self) -> object:
                return self._parent

        model = GraphModel()
        registry = build_default_registry()
        workspace_id = model.active_workspace.workspace_id
        node = model.add_node(workspace_id, "core.logger", "Logger", 32.0, 48.0)

        builder = GraphScenePayloadBuilder()
        factory = builder._node_payload_factory
        original_layout_metrics_and_size = factory._layout_metrics_and_size
        captured_sizes: list[tuple[int, int]] = []

        def capture_layout_metrics_and_size(**kwargs):  # noqa: ANN001, ANN202
            captured_sizes.append(
                (
                    int(kwargs["graph_label_pixel_size"]),
                    int(kwargs["graph_node_icon_pixel_size"]),
                )
            )
            return original_layout_metrics_and_size(**kwargs)

        factory._layout_metrics_and_size = capture_layout_metrics_and_size  # type: ignore[method-assign]

        payloads = builder.build_node_connection_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=workspace_id,
            scope_path=(),
            node_ids={node.node_id},
            graph_theme_bridge=_ThemeBridge(_ThemeSource()),
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )

        self.assertIn(node.node_id, payloads)
        self.assertEqual(captured_sizes, [(16, 50)])

    def test_viewer_surface_size_clamps_stale_custom_height_when_header_grows(self) -> None:
        spec = _viewer_surface_spec()
        node = NodeInstance(
            node_id="node_viewer_surface_input_controls",
            type_id=spec.type_id,
            title="Viewer Controls",
            x=32.0,
            y=48.0,
        )

        baseline_height = resolved_node_surface_size(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
        )[1]
        node.custom_height = float(baseline_height)

        grown_metrics = node_surface_metrics(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )
        grown_size = resolved_node_surface_size(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )

        self.assertGreater(grown_metrics.default_height, baseline_height)
        self.assertLess(grown_metrics.min_height, grown_metrics.default_height)
        self.assertEqual(grown_size[1], grown_metrics.default_height)

    def test_viewer_surface_size_clamps_legacy_default_height_when_body_chrome_grows(self) -> None:
        spec = _viewer_surface_spec()
        node = NodeInstance(
            node_id="node_viewer_surface_legacy_height",
            type_id=spec.type_id,
            title="Viewer Controls",
            x=32.0,
            y=48.0,
        )

        current_metrics = node_surface_metrics(node, spec, {node.node_id: node})
        legacy_body_height = float(VIEWER_LEGACY_DEFAULT_BODY_HEIGHTS[-1])
        legacy_height = (
            float(current_metrics.default_height)
            - (float(current_metrics.body_height) - legacy_body_height)
            + 0.5
        )
        node.custom_height = legacy_height

        resolved_size = resolved_node_surface_size(
            node,
            spec,
            {node.node_id: node},
        )

        self.assertGreater(legacy_height, current_metrics.default_height)
        self.assertEqual(resolved_size[1], current_metrics.default_height)

    def test_viewer_surface_metrics_shrink_body_to_fit_custom_height_between_minimum_and_default(self) -> None:
        spec = NodeTypeSpec(
            type_id="tests.viewer_surface_input_controls.multiport",
            display_name="Viewer Controls",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec("scene_a", "in", "data", "COREX.Engineering.Scene"),
                PortSpec("scene_b", "in", "data", "COREX.Engineering.Scene"),
                PortSpec("scene_c", "in", "data", "COREX.Engineering.Scene"),
                PortSpec("session", "out", "data", 'COREX.Viewer.Session'),
            ),
            properties=(),
            surface_family="viewer",
            render_quality=NodeRenderQualitySpec(
                supported_quality_tiers=("full", "proxy"),
            ),
        )
        node = NodeInstance(
            node_id="node_viewer_surface_input_controls_mid_height",
            type_id=spec.type_id,
            title="Viewer Controls",
            x=32.0,
            y=48.0,
        )

        default_metrics = node_surface_metrics(node, spec, {node.node_id: node})
        self.assertGreater(default_metrics.default_height, default_metrics.min_height)

        midway_height = float(default_metrics.default_height - 18.0)
        self.assertGreater(midway_height, float(default_metrics.min_height))
        node.custom_height = midway_height

        shrunk_metrics = node_surface_metrics(node, spec, {node.node_id: node})
        expected_body_height = (
            midway_height
            - float(shrunk_metrics.body_top)
            - 3.0 * float(shrunk_metrics.port_height)
            - float(shrunk_metrics.body_bottom_margin)
        )

        self.assertLess(shrunk_metrics.body_height, default_metrics.body_height)
        self.assertAlmostEqual(float(shrunk_metrics.body_height), expected_body_height, places=6)
        self.assertAlmostEqual(
            float(shrunk_metrics.port_top)
            + 3.0 * float(shrunk_metrics.port_height)
            + float(shrunk_metrics.body_bottom_margin),
            midway_height,
            places=6,
        )

    def test_standard_surface_size_clamps_stale_custom_height_when_header_grows(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec("core.logger")
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        node = model.add_node(workspace_id, "core.logger", "Logger", 32.0, 48.0)

        baseline_height = resolved_node_surface_size(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
        )[1]
        node.custom_height = float(baseline_height)

        grown_metrics = node_surface_metrics(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )
        grown_size = resolved_node_surface_size(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=50,
        )

        self.assertGreater(grown_metrics.default_height, baseline_height)
        self.assertEqual(grown_metrics.min_height, grown_metrics.default_height)
        self.assertEqual(grown_size[1], grown_metrics.default_height)

    def test_graph_scene_bridge_rebuilds_standard_node_metrics_when_icon_size_changes(self) -> None:
        class _SceneHost(QObject):
            graphics_preferences_changed = pyqtSignal()

            def __init__(self) -> None:
                super().__init__()
                self.graphics_graph_label_pixel_size = 16
                self.graphics_graph_node_icon_pixel_size_override = None
                self.graphics_node_title_icon_pixel_size = 16
                self.graphics_show_port_labels = True

        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        model.add_node(workspace_id, "core.logger", "Logger", 32.0, 48.0)

        host = _SceneHost()
        scene = GraphSceneBridge(host)
        scene.bind_graphics_preferences_source(host)
        scene.bind_graph_theme_bridge(GraphThemeBridge(host, theme_id="stitch_dark"))
        scene.set_workspace(model, registry, workspace_id)

        initial_payload = scene.nodes_model[0]
        self.assertEqual(initial_payload["surface_metrics"]["header_height"], 24.0)

        rebuild_events: list[str] = []
        scene.nodes_changed.connect(lambda: rebuild_events.append("nodes"))

        host.graphics_node_title_icon_pixel_size = 50
        host.graphics_preferences_changed.emit()

        updated_payload = scene.nodes_model[0]
        self.assertGreaterEqual(len(rebuild_events), 1)
        self.assertEqual(updated_payload["surface_metrics"]["header_height"], 50.0)
        self.assertEqual(updated_payload["surface_metrics"]["title_height"], 50.0)
        self.assertEqual(updated_payload["surface_metrics"]["body_top"], 56.0)
        self.assertGreater(updated_payload["height"], initial_payload["height"])


class GraphSurfaceCanvasInteractionTests(GraphSurfaceInputContractTestBase):
    def test_ports_with_hidden_default_editors_use_single_rows(self) -> None:
        self._run_qml_probe(
            "hidden-default-editor-port-spacing",
            '''
            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

            registry = build_default_registry()
            model = GraphModel()
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, model.active_workspace.workspace_id)
            for type_id, default_keys in (
                ("io.process_run", {"command", "args"}),
                ("io.email_send", {"subject", "body"}),
                ("optimization.construct_design", {"name"}),
            ):
                node_id = scene.add_node_from_type(type_id, 0, 0)
                payload = next(item for item in scene.nodes_model if item["node_id"] == node_id)
                ports = {port["key"]: port for port in payload["ports"]}
                for key in default_keys:
                    assert ports[key]["uses_property_default"]
                    assert ports[key]["default_property"]["inline_editor"] == ""
                host = create_component(graph_node_host_qml_path, {"nodeData": payload})
                window = attach_host_to_window(host, 700, 500)
                settle_events(4)
                counts = []
                for direction, name in (("in", "Input"), ("out", "Output")):
                    side_ports = [port for port in payload["ports"] if port["direction"] == direction]
                    assert [port["layout_row"] for port in side_ports] == list(range(len(side_ports))), type_id
                    counts.append(len(side_ports))
                    rows = named_child_items(host, "graphNode" + name + "PortRow")
                    points = sorted(float(variant_value(row.property("portPoint"))["y"]) for row in rows)
                    row_height = payload["surface_metrics"]["port_height"]
                    assert all(abs(b - a - row_height) < 0.1 for a, b in zip(points, points[1:])), (type_id, points)
                    assert all(not row.property("defaultEditorVisible") for row in rows)
                projected = payload["surface_metrics"]
                assert abs(projected["default_height"] - (
                    projected["body_top"] + projected["body_height"]
                    + max(counts) * projected["port_height"] + projected["body_bottom_margin"]
                )) < 0.1, type_id
                assert abs(host.height() - payload["height"]) < 0.1, type_id
                dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            ''',
        )

    def test_python_script_dynamic_handles_click_through_real_canvas_bridge(self) -> None:
        self._run_qml_probe(
            "python-script-dynamic-handles",
            '''
            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, model.active_workspace.workspace_id)
            view = ViewportBridge()
            view.set_viewport_size(980.0, 680.0)
            state, commands = build_canvas_bridges(scene_bridge=scene, view_bridge=view)
            node_id = scene.add_node_from_type("core.python_script", -200.0, -150.0)
            node = model.active_workspace.nodes[node_id]
            canvas = create_component(graph_canvas_qml_path, {
                "canvasStateBridge": state, "canvasCommandBridge": commands,
                "width": 980.0, "height": 680.0,
            })
            settle_events(8)
            window = attach_host_to_window(canvas, 1040, 740)
            settle_events(4)

            def host():
                return next(item for item in named_child_items(canvas, "graphNodeCard")
                    if variant_value(item.property("nodeData"))["node_id"] == node_id)

            def click(name, port_key=None, direction="Input"):
                if port_key is None:
                    QTest.mouseMove(window, QPoint(960, 650))
                    settle_events(1)
                    QTest.mouseMove(window, item_scene_point(host()))
                else:
                    QTest.mouseMove(window, QPoint(960, 650))
                    settle_events(1)
                    host().setProperty("hoveredPort", {
                        "node_id": node_id,
                        "port_key": port_key,
                        "direction": "in" if direction == "Input" else "out",
                    })
                settle_events(2)
                item = named_item(host(), name)
                assert item is not None and item.property("visible"), name
                QTest.mouseMove(window, item_scene_point(item))
                settle_events(2)
                QTest.mouseClick(window, Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier, item_scene_point(item))
                settle_events(6)

            original = node.properties["script"]
            def assert_compact_geometry():
                current = host()
                for direction in ("Input", "Output"):
                    for label in named_child_items(current, "graphNode" + direction + "PortLabel"):
                        assert not label.property("truncated"), (label.property("text"), label.width())
                    for row in named_child_items(current, "graphNode" + direction + "PortRow"):
                        remove = row.property("removeButtonItem")
                        if remove is not None and remove.property("visible"):
                            point = variant_value(row.property("portPoint"))
                            assert abs(abs(remove.x() + remove.width() / 2 - point["x"]) - 9) < 0.1
                            label = row.property("labelContainerItem")
                            label_gap = (
                                label.x() - (remove.x() + remove.width())
                                if direction == "Input"
                                else remove.x() - (label.x() + label.width())
                            )
                            assert abs(label_gap) < 0.1, label_gap
                projected = variant_value(current.property("nodeData"))["surface_metrics"]
                rendered = variant_value(current.property("surfaceMetrics"))
                assert abs(projected["body_bottom_margin"] - rendered["body_bottom_margin"]) < 0.1

            assert_compact_geometry()
            QTest.mouseMove(window, QPoint(960, 650))
            settle_events(2)
            assert all(
                not item.property("visible")
                for item in named_child_items(host(), "graphNodeDynamicPortAdd_inputs")
                + named_child_items(host(), "graphNodeDynamicPortAdd_outputs")
            )
            host().setProperty("hoveredPort", {
                "node_id": node_id,
                "port_key": "payload",
                "direction": "in",
            })
            settle_events(2)
            input_add = named_item(host(), "graphNodeDynamicPortAdd_inputs")
            input_mouse = named_item(
                host(),
                "graphNodeInputPortMouseArea",
                "payload",
            )
            handoff_overlap = input_mouse.mapToItem(
                input_add,
                QPointF(input_mouse.width() * 0.5, input_mouse.height()),
            ).y()
            assert 1.0 <= handoff_overlap <= 3.0, handoff_overlap
            click("graphNodeDynamicPortAdd_inputs", "payload")
            assert '@corex.input("input1", value_type=corex.Any)' in node.properties["script"], node.properties["script"]
            assert 'def run(ctx, payload, input1)' in node.properties["script"], node.properties["script"]
            click("graphNodeDynamicPortAdd_outputs", "result", "Output")
            assert '@corex.output("output1", value_type=corex.Any)' in node.properties["script"], node.properties["script"]
            assert_compact_geometry()
            click("graphNodeDynamicPortRemove_input1", "input1")
            click("graphNodeDynamicPortRemove_output1", "output1", "Output")
            assert "input1" not in node.properties["script"]
            assert "output1" not in node.properties["script"]
            assert original.split("def run", 1)[1].split(":", 1)[1] == node.properties["script"].split("def run", 1)[1].split(":", 1)[1]

            # The zero-port sides must still expose clickable green handles.
            click("graphNodeDynamicPortRemove_payload", "payload")
            click("graphNodeDynamicPortRemove_result", "result", "Output")
            spec = registry.resolve_spec(node.type_id, node.properties)
            assert not spec.ports
            click("graphNodeDynamicPortAdd_inputs")
            click("graphNodeDynamicPortAdd_outputs", "input1")
            assert {p.key for p in registry.resolve_spec(node.type_id, node.properties).ports} == {"input1", "output1"}
            scene.rename_dynamic_port(node_id, "inputs", "input1", "long_input_parameter_name")
            scene.rename_dynamic_port(node_id, "outputs", "output1", "long_output_parameter_name")
            settle_events(6)
            assert {label.property("text") for direction in ("Input", "Output")
                for label in named_child_items(host(), "graphNode" + direction + "PortLabel")} == {
                    "long_input_parameter_name", "long_output_parameter_name"}
            assert_compact_geometry()
            window.close()
            canvas.deleteLater()
            engine.deleteLater()
            app.processEvents()
            ''',
        )

    def test_collapsible_toolbar_action_reaches_scene_through_canvas_command_bridge(self) -> None:
        self._run_qml_probe(
            "collapsible-toolbar-canvas-command-route",
            """
            from PyQt6.QtCore import QObject, pyqtSlot
            from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge

            class CollapseSceneSource(QObject):
                def __init__(self):
                    super().__init__()
                    self.calls = []

                @pyqtSlot(str, bool, result=bool)
                def set_node_collapsed(self, node_id, collapsed):
                    self.calls.append((str(node_id), bool(collapsed)))
                    return True

            scene_source = CollapseSceneSource()
            canvas_command_bridge = GraphCanvasCommandBridge(scene_bridge=scene_source)
            engine.rootContext().setContextProperty("canvasCommandBridgeProbe", canvas_command_bridge)
            component = QQmlComponent(engine)
            component.setData(
                b'''
                import QtQuick 2.15
                import "ea_node_editor/ui_qml/components/graph_canvas" as GraphCanvasComponents

                Item {
                    id: probeRoot
                    property var sceneCommandBridge: canvasCommandBridgeProbe
                    property bool collapsed: false

                    function toggleCollapsed() {
                        return actionRouter.handleNodeDelegateAction(
                            nodeHost,
                            "node-1",
                            "toggle_node_collapsed"
                        );
                    }

                    QtObject {
                        id: nodeHost
                        property bool isCollapsed: probeRoot.collapsed
                    }

                    GraphCanvasComponents.GraphCanvasActionRouter {
                        id: actionRouter
                        canvasItem: probeRoot
                    }
                }
                ''',
                QUrl.fromLocalFile(str(repo_root) + "/"),
            )
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load collapse route probe:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate collapse route probe:\\n" + errors)

            assert probe.toggleCollapsed() is True
            probe.setProperty("collapsed", True)
            assert probe.toggleCollapsed() is True
            assert scene_source.calls == [("node-1", True), ("node-1", False)]

            probe.deleteLater()
            canvas_command_bridge.deleteLater()
            scene_source.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_trigger_rename_falls_back_when_inline_editor_is_unavailable(self) -> None:
        self._run_qml_probe(
            "trigger-rename-fallback",
            """
            component = QQmlComponent(engine)
            component.setData(
                b'''
                import QtQuick 2.15
                import "ea_node_editor/ui_qml/components/graph_canvas" as GraphCanvasComponents

                Item {
                    id: probeRoot
                    property string nodeContextNodeId: "trigger_node"
                    property bool inlineEditorAvailable: false
                    property int flaggedRenameCalls: 0
                    property int dialogRenameCalls: 0
                    property int contextInlineAttempts: 0
                    property int delegateInlineAttempts: 0
                    property int closeCalls: 0

                    function _closeContextMenus() { closeCalls += 1; }
                    function requestInlineRenameForNode(_nodeId) {
                        contextInlineAttempts += 1;
                        return inlineEditorAvailable;
                    }
                    function runContextRename() {
                        return actionRouter.handleNodeContextAction("rename_node");
                    }
                    function runToolbarRename() {
                        return actionRouter.handleNodeDelegateAction(triggerNodeHost, nodeContextNodeId, "rename_node");
                    }
                    function resetCalls() {
                        flaggedRenameCalls = 0;
                        dialogRenameCalls = 0;
                        contextInlineAttempts = 0;
                        delegateInlineAttempts = 0;
                        closeCalls = 0;
                    }

                    QtObject {
                        id: graphActionBridge
                        function trigger_graph_action(actionId, payload) {
                            if (actionId !== "rename_node" || payload.node_id !== probeRoot.nodeContextNodeId)
                                return false;
                            if (payload.inline_title_edit)
                                probeRoot.flaggedRenameCalls += 1;
                            else
                                probeRoot.dialogRenameCalls += 1;
                            return true;
                        }
                    }

                    QtObject {
                        id: triggerNodeHost
                        function beginInlineTitleEdit() {
                            probeRoot.delegateInlineAttempts += 1;
                            return probeRoot.inlineEditorAvailable;
                        }
                    }

                    GraphCanvasComponents.GraphCanvasActionRouter {
                        id: actionRouter
                        canvasItem: probeRoot
                        graphActionBridge: graphActionBridge
                    }
                }
                ''',
                QUrl.fromLocalFile(str(repo_root) + "/"),
            )
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load trigger rename probe:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate trigger rename probe:\\n" + errors)
            app.processEvents()

            assert probe.runContextRename() is True
            assert probe.runToolbarRename() is True
            assert int(probe.property("flaggedRenameCalls")) == 2
            assert int(probe.property("dialogRenameCalls")) == 2
            assert int(probe.property("contextInlineAttempts")) == 1
            assert int(probe.property("delegateInlineAttempts")) == 1
            assert int(probe.property("closeCalls")) == 1

            probe.resetCalls()
            probe.setProperty("inlineEditorAvailable", True)
            assert probe.runContextRename() is True
            assert probe.runToolbarRename() is True
            assert int(probe.property("flaggedRenameCalls")) == 2
            assert int(probe.property("dialogRenameCalls")) == 0

            probe.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_content_fullscreen_f11_routes_selection_and_hint_contract(self) -> None:
        self._run_qml_probe(
            "graph-canvas-content-fullscreen-shortcut",
            """
            from PyQt6.QtCore import QObject, pyqtProperty, pyqtSlot

            class ContentFullscreenBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.is_open = False
                    self.open_calls = []
                    self.close_calls = 0
                    self.eligible_node_ids = {"media_node"}
                    self.last_error_value = "The selected node does not support content fullscreen."

                @pyqtProperty(bool)
                def open(self):
                    return self.is_open

                @pyqtProperty(str)
                def last_error(self):
                    return self.last_error_value

                @pyqtSlot(str, result=bool)
                def can_open_node(self, node_id):
                    return str(node_id or "") in self.eligible_node_ids

                @pyqtSlot(str, result=bool)
                def request_open_node(self, node_id):
                    normalized = str(node_id or "")
                    self.open_calls.append(normalized)
                    if normalized in self.eligible_node_ids:
                        self.is_open = True
                        self.last_error_value = ""
                        return True
                    self.last_error_value = "The selected node does not support content fullscreen."
                    return False

                @pyqtSlot()
                def request_close(self):
                    self.close_calls += 1
                    self.is_open = False

            class ShellBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.hints = []

                @pyqtSlot(str, int)
                def show_graph_hint(self, message, timeout_ms):
                    self.hints.append((str(message or ""), int(timeout_ms)))

            class ShellContextStub(QObject):
                def __init__(self, content_fullscreen_bridge, shell_library_bridge):
                    super().__init__()
                    self._content_fullscreen_bridge = content_fullscreen_bridge
                    self._shell_library_bridge = shell_library_bridge

                @pyqtProperty(QObject, constant=True)
                def contentFullscreenBridge(self):
                    return self._content_fullscreen_bridge

                @pyqtProperty(QObject, constant=True)
                def shellLibraryBridge(self):
                    return self._shell_library_bridge

            bridge = ContentFullscreenBridgeStub()
            shell_bridge = ShellBridgeStub()
            shell_context = ShellContextStub(bridge, shell_bridge)
            engine.rootContext().setContextProperty("shellContext", shell_context)

            component = QQmlComponent(engine)
            component.setData(
                b'''
                import QtQuick 2.15
                import "ea_node_editor/ui_qml/components/graph_canvas" as GraphCanvasComponents

                Item {
                    id: probeRoot
                    objectName: "contentFullscreenShortcutProbe"
                    width: 400
                    height: 300
                    property var selectedIds: []

                    function selectedNodeIds() {
                        return selectedIds;
                    }

                    GraphCanvasComponents.GraphCanvasActionRouter {
                        id: actionRouter
                        canvasItem: probeRoot
                        contentFullscreenBridge: shellContext.contentFullscreenBridge
                        shellLibraryBridge: shellContext.shellLibraryBridge
                    }

                    GraphCanvasComponents.GraphCanvasInputLayers {
                        id: inputLayers
                        objectName: "graphCanvasInputLayers"
                        canvasItem: probeRoot
                        canvasActionRouter: actionRouter
                    }

                    function triggerShortcut() {
                        return inputLayers._handleContentFullscreenShortcut();
                    }
                }
                ''',
                QUrl.fromLocalFile(str(repo_root) + "/"),
            )
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load shortcut probe:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate shortcut probe:\\n" + errors)
            app.processEvents()

            probe.setProperty("selectedIds", ["media_node"])
            assert probe.triggerShortcut() is True
            app.processEvents()
            assert bridge.open_calls == ["media_node"]
            assert bridge.is_open is True
            assert shell_bridge.hints == []

            assert probe.triggerShortcut() is True
            app.processEvents()
            assert bridge.close_calls == 1
            assert bridge.is_open is False

            probe.setProperty("selectedIds", ["unsupported_node"])
            assert probe.triggerShortcut() is True
            app.processEvents()
            assert bridge.open_calls == ["media_node", "unsupported_node"]
            assert shell_bridge.hints[-1] == (
                "The selected node does not support content fullscreen.",
                2400,
            )

            probe.setProperty("selectedIds", ["media_node", "viewer_node"])
            assert probe.triggerShortcut() is True
            app.processEvents()
            assert bridge.open_calls == ["media_node", "unsupported_node"]
            assert shell_bridge.hints[-1] == (
                "Select one media or viewer node for fullscreen.",
                2400,
            )

            probe.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_action_router_navigates_selected_pdf_pages(self) -> None:
        self._run_qml_probe(
            "graph-canvas-selected-pdf-page-navigation",
            """
            component = QQmlComponent(engine)
            component.setData(
                b'''
                import QtQuick 2.15
                import "ea_node_editor/ui_qml/components/graph_canvas" as GraphCanvasComponents

                Item {
                    id: probeRoot
                    objectName: "selectedPdfNavigationProbe"
                    width: 400
                    height: 300
                    property var selectedIds: []
                    property var payloads: ({})
                    property string lastCommit: ""
                    property var executionFacts: ({
                        "mediaPanelSourceLookup": {
                            "pdf_node": {
                                "state": "ready",
                                "media_kind": "pdf",
                                "source_ref": "manual.pdf",
                                "resolved_source_url": "file:///manual.pdf"
                            },
                            "image_node": {
                                "state": "ready",
                                "media_kind": "image",
                                "source_ref": "image.png",
                                "resolved_source_url": "file:///image.png"
                            }
                        }
                    })

                    function selectedNodeIds() {
                        return selectedIds;
                    }

                    function _sceneNodePayload(nodeId) {
                        return payloads[String(nodeId || "")] || null;
                    }

                    function describeNodeSurfacePdfPreview(source, pageNumber) {
                        return {
                            "state": "ready",
                            "page_count": 3,
                            "requested_page_number": Number(pageNumber || 1),
                            "resolved_page_number": Math.max(1, Math.min(3, Number(pageNumber || 1))),
                            "preview_url": "image://local-pdf-preview/preview",
                            "resolved_source_url": "file:///manual.pdf"
                        };
                    }

                    function commitNodeSurfaceProperty(nodeId, key, value) {
                        lastCommit = String(nodeId || "") + "|" + String(key || "") + "|" + String(value);
                        return true;
                    }

                    function navigate(delta) {
                        return actionRouter.navigateSelectedPdfPage(delta);
                    }

                    GraphCanvasComponents.GraphCanvasActionRouter {
                        id: actionRouter
                        canvasItem: probeRoot
                    }
                }
                ''',
                QUrl.fromLocalFile(str(repo_root) + "/"),
            )
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load selected PDF navigation probe:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate selected PDF navigation probe:\\n" + errors)
            app.processEvents()

            probe.setProperty("payloads", {
                "pdf_node": {
                    "type_id": "media.panel",
                    "properties": {"source": "manual.pdf", "page_number": 1},
                },
                "image_node": {
                    "type_id": "media.panel",
                    "properties": {"source": "image.png"},
                },
            })
            probe.setProperty("selectedIds", ["pdf_node"])
            assert probe.navigate(1) is True
            assert str(probe.property("lastCommit")) == "pdf_node|page_number|2"

            probe.setProperty("lastCommit", "")
            probe.setProperty("payloads", {
                "pdf_node": {
                    "type_id": "media.panel",
                    "properties": {"source": "manual.pdf", "page_number": 3},
                },
                "image_node": {
                    "type_id": "media.panel",
                    "properties": {"source": "image.png"},
                },
            })
            assert probe.navigate(1) is True
            assert str(probe.property("lastCommit")) == ""

            probe.setProperty("selectedIds", ["image_node"])
            assert probe.navigate(1) is False
            probe.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_active_input_default_editor_stays_visible_but_disables_when_overridden(self) -> None:
        self._run_qml_probe(
            "active-input-default-property-editor",
            """
            payload = node_payload()
            payload["node_id"] = "node_default_property_editor"
            payload["ports"] = [
                {
                    "key": "message",
                    "label": "Message",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                    "default_property": {
                        "key": "message",
                        "label": "Message",
                        "type": "str",
                        "value": "default text",
                        "inline_editor": "text",
                        "overridden_by_input": False,
                    },
                },
                {
                    "key": "result",
                    "label": "Result",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                },
            ]
            payload["inline_properties"] = []

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            row = named_item(host, "graphNodeInputPortRow", "message")
            editor = named_item(host, "graphNodeInputDefaultProperty", "message")
            input_dot = named_item(host, "graphNodeInputPortDot", "message")
            input_mouse = named_item(host, "graphNodeInputPortMouseArea", "message")

            assert bool(row.property("defaultEditorVisible")) is True
            assert bool(editor.property("visible")) is True
            assert bool(input_dot.property("lockedState")) is False
            assert bool(input_dot.property("interactionBlockedState")) is False
            assert input_mouse.property("cursorShape") == Qt.CursorShape.PointingHandCursor

            port_clicks = []
            host.portClicked.connect(
                lambda node_id, port_key, direction, scene_x, scene_y, modifiers: port_clicks.append(
                    (node_id, port_key, direction)
                )
            )
            window = attach_host_to_window(host, 520, 320)
            property_label = named_item(
                host,
                "graphNodeInlinePropertyLabel",
                "message",
            )
            value_editor = named_item(host, "graphNodeInlineValueEditor", "message")
            editor_left = editor.mapToItem(host, QPointF(0.0, 0.0))
            editor_right = editor.mapToItem(
                host,
                QPointF(float(editor.width()), 0.0),
            )
            value_left = value_editor.mapToItem(host, QPointF(0.0, 0.0))
            value_right = value_editor.mapToItem(
                host,
                QPointF(float(value_editor.width()), 0.0),
            )
            surface_metrics = variant_value(host.property("surfaceMetrics"))
            expected_control_width = (
                float(host.width())
                - float(surface_metrics["body_left_margin"])
                - float(surface_metrics["body_right_margin"])
                - 12.0
            )
            assert abs(
                abs(float(editor_right.x()) - float(editor_left.x()))
                - float(host.width())
            ) < 0.5
            assert abs(
                abs(float(value_right.x()) - float(value_left.x()))
                - expected_control_width
            ) < 0.5
            dot_center = item_scene_point(input_dot)
            label_center = item_scene_point(property_label)
            assert abs(dot_center.y() - label_center.y()) < 0.5, (
                dot_center,
                label_center,
            )
            mouse_click(window, item_scene_point(input_mouse))
            settle_events(3)
            assert port_clicks == [("node_default_property_editor", "message", "in")]

            payload["ports"][0]["connected"] = True
            payload["ports"][0]["default_property"]["overridden_by_input"] = True
            host.setProperty("nodeData", payload)
            settle_events(3)

            row = named_item(host, "graphNodeInputPortRow", "message")
            editor = named_item(host, "graphNodeInputDefaultProperty", "message")
            value_editor = named_item(host, "graphNodeInlineValueEditor", "message")
            assert bool(row.property("defaultEditorVisible")) is True
            assert bool(editor.property("visible")) is True
            assert bool(value_editor.property("visible")) is True
            assert bool(value_editor.property("enabled")) is False
            assert str(value_editor.property("text")) == "default text"
            assert variant_list(editor.property("embeddedInteractiveRects")) == []

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_textarea_input_default_row_uses_the_label_line_presentation_anchor(self) -> None:
        self._run_qml_probe(
            "textarea-input-default-label-anchor",
            """
            payload = node_payload()
            payload["node_id"] = "node_textarea_default_property_editor"
            payload["height"] = 220.0
            payload["ports"] = [
                {
                    "key": "notes",
                    "label": "Notes",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                    "layout_row": -1,
                    "presentation_anchor": {
                        "side": "left",
                        "x": 13.0,
                        "y": 92.0,
                        "aggregate": False,
                    },
                    "default_property": {
                        "key": "notes",
                        "label": "Notes",
                        "type": "str",
                        "value": "saved notes",
                        "inline_editor": "textarea",
                        "overridden_by_input": False,
                    },
                },
                {
                    "key": "result",
                    "label": "Result",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                },
            ]
            payload["inline_properties"] = []

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            row = named_item(host, "graphNodeInputPortRow", "notes")
            editor = named_item(host, "graphNodeInputDefaultProperty", "notes")
            textarea = named_item(host, "graphNodeInlineTextareaEditor", "notes")
            input_dot = named_item(host, "graphNodeInputPortDot", "notes")
            window = attach_host_to_window(host, 520, 360)

            assert bool(row.property("defaultEditorVisible")) is True
            assert bool(editor.property("visible")) is True
            assert bool(textarea.property("visible")) is True
            assert abs(float(row.height()) - float(host.property("_inlineTextareaRowHeight"))) < 0.5

            row_top = item_scene_point(row, 0.0, 0.0)
            dot_center = item_scene_point(input_dot)
            label_anchor_y = (
                float(row_top.y()) + float(host.property("_inlineLabelAnchorOffset"))
            )
            assert abs(float(dot_center.y()) - label_anchor_y) < 0.5, (
                dot_center,
                row_top,
                label_anchor_y,
            )

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_ctrl_drag_reassigns_selected_or_sole_edge_endpoint_without_quick_insert(self) -> None:
        self._run_qml_probe(
            "ctrl-drag-edge-endpoint-reassignment",
            """
            from PyQt6.QtCore import QObject, pyqtProperty, pyqtSlot
            from PyQt6.QtQml import QQmlProperty

            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
            from ea_node_editor.nodes.registry import NodeRegistry
            from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            class EndpointMoveShellBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.rewire_calls = []
                    self.rewire_delegate = None
                    self.quick_insert_calls = []

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

                @pyqtSlot("QVariantList", str, str, str, bool, bool, result=bool)
                def request_rewire_edges(
                    self,
                    edge_ids,
                    endpoint,
                    node_id,
                    port_key,
                    copy_requested,
                    append_requested,
                ):
                    self.rewire_calls.append(
                        (
                            [str(edge_id or "") for edge_id in edge_ids],
                            str(endpoint or ""),
                            str(node_id or ""),
                            str(port_key or ""),
                            bool(copy_requested),
                            bool(append_requested),
                        )
                    )
                    if self.rewire_delegate is not None:
                        return bool(self.rewire_delegate.request_rewire_edges(
                            edge_ids,
                            endpoint,
                            node_id,
                            port_key,
                            copy_requested,
                            append_requested,
                        ))
                    return True

                @pyqtSlot(str, str, float, float, float, float, bool, result=bool)
                def request_open_connection_quick_insert(
                    self,
                    node_id,
                    port_key,
                    scene_x,
                    scene_y,
                    overlay_x,
                    overlay_y,
                    append,
                ):
                    self.quick_insert_calls.append(
                        (
                            str(node_id or ""),
                            str(port_key or ""),
                            float(scene_x),
                            float(scene_y),
                            float(overlay_x),
                            float(overlay_y),
                            bool(append),
                        )
                    )
                    return True

            source_spec = NodeTypeSpec(
                type_id="tests.ctrl_drag_source",
                display_name="Ctrl Drag Source",
                category_path=("Tests",),
                icon="",
                ports=(
                    PortSpec(
                        "out",
                        "out",
                        "data",
                        'COREX.DataTypes.String',
                        allow_multiple_connections=True,
                    ),
                ),
                properties=(),
            )
            target_spec = NodeTypeSpec(
                type_id="tests.ctrl_drag_target",
                display_name="Ctrl Drag Target",
                category_path=("Tests",),
                icon="",
                ports=(PortSpec("in", "in", "data", 'COREX.DataTypes.String', required=True),),
                properties=(),
            )
            incompatible_spec = NodeTypeSpec(
                type_id="tests.ctrl_drag_incompatible",
                display_name="Ctrl Drag Incompatible",
                category_path=("Tests",),
                icon="",
                ports=(
                    PortSpec("bad", "in", "data", 'COREX.DataTypes.Int', required=True),
                    PortSpec("bad_out", "out", "data", 'COREX.DataTypes.Int'),
                ),
                properties=(),
            )

            model = GraphModel()
            registry = NodeRegistry()
            for spec in (source_spec, target_spec, incompatible_spec):
                registry.register_descriptor(spec, lambda: None)
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, model.active_workspace.workspace_id)
            shell_bridge = EndpointMoveShellBridgeStub()

            view = ViewportBridge()
            view.set_viewport_size(900.0, 640.0)
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

            class SnapshotPolicyProbe:
                def __init__(self, delegate):
                    self.delegate = delegate
                    self.calls = []
                    self.mode = "normal"

                def compatible_endpoint_snapshot(self, node_id, port_key, candidate_role):
                    self.calls.append(("connect", str(node_id), str(port_key), str(candidate_role)))
                    snapshot = dict(
                        self.delegate.compatible_endpoint_snapshot(
                            node_id,
                            port_key,
                            candidate_role,
                        )
                    )
                    if self.mode == "generation_mismatch":
                        snapshot["catalog_generation"] = "0" * 64
                    elif self.mode == "malformed":
                        snapshot["compatible_endpoint_ids"] = [{"node_id": target_b_id}]
                    return snapshot

                def compatible_rewire_endpoint_snapshot(
                    self,
                    edge_ids,
                    endpoint,
                    copy_requested=False,
                    append_requested=False,
                ):
                    normalized_ids = [str(edge_id) for edge_id in edge_ids]
                    self.calls.append((
                        "rewire",
                        normalized_ids,
                        str(endpoint),
                        bool(copy_requested),
                        bool(append_requested),
                    ))
                    snapshot = dict(
                        self.delegate.compatible_rewire_endpoint_snapshot(
                            normalized_ids,
                            endpoint,
                            copy_requested,
                            append_requested,
                        )
                    )
                    if self.mode == "generation_mismatch":
                        snapshot["catalog_generation"] = "0" * 64
                    elif self.mode == "malformed":
                        snapshot["compatible_endpoint_ids"] = [{"node_id": target_b_id}]
                    return snapshot

                def are_port_kinds_compatible(self, source_kind, target_kind):
                    return self.delegate.are_port_kinds_compatible(source_kind, target_kind)

                def are_data_types_compatible(self, source_type, target_type):
                    return self.delegate.are_data_types_compatible(source_type, target_type)

            snapshot_policy = SnapshotPolicyProbe(scene.policy_bridge)
            canvas_state_bridge._scene_policy_source = snapshot_policy

            source_a_id = scene.add_node_from_type("tests.ctrl_drag_source", 40.0, 80.0)
            source_b_id = scene.add_node_from_type("tests.ctrl_drag_source", 40.0, 320.0)
            target_a_id = scene.add_node_from_type("tests.ctrl_drag_target", 420.0, 100.0)
            target_b_id = scene.add_node_from_type("tests.ctrl_drag_target", 420.0, 280.0)
            incompatible_id = scene.add_node_from_type("tests.ctrl_drag_incompatible", 700.0, 400.0)
            edge_a_id = scene.add_edge(source_a_id, "out", target_a_id, "in")
            edge_b_id = scene.add_edge(source_a_id, "out", target_b_id, "in")
            bundle_ids = sorted(
                (edge_a_id, edge_b_id),
                key=lambda edge_id: (
                    model.active_workspace.edges[edge_id].input_order,
                    edge_id,
                ),
            )

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 900.0,
                    "height": 640.0,
                },
            )
            settle_events(8)
            window = attach_host_to_window(canvas, 1040, 740)
            settle_events(4)

            def host_for(node_id):
                for host in named_child_items(canvas, "graphNodeCard"):
                    payload = variant_value(host.property("nodeData")) or {}
                    if str(payload.get("node_id", "")) == str(node_id):
                        return host
                raise AssertionError("missing graph-node host for " + str(node_id))

            def port_point(node_id, object_name, port_key):
                host = host_for(node_id)
                return item_scene_point(named_item(host, object_name, port_key))

            def begin_ctrl_drag(node_id, port_key, direction, modifiers):
                origin = port_point(
                    node_id,
                    "graphNodeInputPortDot" if direction == "in" else "graphNodeOutputPortDot",
                    port_key,
                )
                scene_x = canvas.screenToSceneX(origin.x())
                scene_y = canvas.screenToSceneY(origin.y())
                canvas.beginPortWireDrag(
                    node_id,
                    port_key,
                    direction,
                    scene_x,
                    scene_y,
                    origin.x(),
                    origin.y(),
                    modifiers,
                )
                return origin, scene_x, scene_y

            def finish_ctrl_drag(
                node_id,
                port_key,
                direction,
                origin,
                scene_x,
                scene_y,
                release,
                modifiers,
                compatible_dot=None,
                incompatible_dot=None,
            ):
                snapshot_call_count = len(snapshot_policy.calls)
                for _move_index in range(5):
                    canvas.updatePortWireDrag(
                        node_id,
                        port_key,
                        direction,
                        scene_x,
                        scene_y,
                        release.x(),
                        release.y(),
                        True,
                        modifiers,
                    )
                settle_events(2)
                active_state = variant_value(canvas.property("wireDragState"))
                active_preview = variant_value(canvas.wireDragPreviewConnection())
                assert len(snapshot_policy.calls) == snapshot_call_count + 1
                if compatible_dot is not None:
                    assert bool(compatible_dot.property("compatibleTargetState")) is True
                    ring_name = (
                        "graphNodeInputPortRing"
                        if str(compatible_dot.property("interactionDirection")) == "in"
                        else "graphNodeOutputPortRing"
                    )
                    ring = named_item(
                        compatible_dot,
                        ring_name,
                        str(compatible_dot.property("propertyKey")),
                    )
                    assert float(ring.property("width")) > float(compatible_dot.property("width"))
                    assert float(QQmlProperty.read(ring, "border.width")) > 0.0
                if incompatible_dot is not None:
                    assert bool(incompatible_dot.property("compatibleTargetState")) is False
                canvas.finishPortWireDrag(
                    node_id,
                    port_key,
                    direction,
                    scene_x,
                    scene_y,
                    release.x(),
                    release.y(),
                    True,
                    modifiers,
                )
                settle_events(2)
                assert len(snapshot_policy.calls) == snapshot_call_count + 1
                return active_state, active_preview

            window = attach_host_to_window(canvas, 960, 700)
            control = int(Qt.KeyboardModifier.ControlModifier.value)
            control_shift = control | int(Qt.KeyboardModifier.ShiftModifier.value)
            replacement_source_dot = named_item(
                host_for(source_b_id),
                "graphNodeOutputPortDot",
                "out",
            )
            replacement_source = item_scene_point(replacement_source_dot)

            def pointer_drag(node_id, direction, port_key, release, modifiers):
                dot_name = (
                    "graphNodeInputPortDot" if direction == "in" else "graphNodeOutputPortDot"
                )
                mouse_name = (
                    "graphNodeInputPortMouseArea" if direction == "in" else "graphNodeOutputPortMouseArea"
                )
                dot = named_item(host_for(node_id), dot_name, port_key)
                mouse_area = named_item(dot, mouse_name, port_key)
                start = item_scene_point(mouse_area)
                middle = QPoint(
                    round((start.x() + release.x()) * 0.5),
                    round((start.y() + release.y()) * 0.5),
                )
                QTest.mousePress(window, Qt.MouseButton.LeftButton, modifiers, start)
                QTest.mouseMove(window, middle)
                QTest.mouseMove(window, release)
                canvas.updatePortWireDrag(
                    node_id,
                    port_key,
                    direction,
                    canvas.screenToSceneX(start.x()),
                    canvas.screenToSceneY(start.y()),
                    release.x(),
                    release.y(),
                    True,
                    int(modifiers.value),
                )
                settle_events(4)
                return variant_value(canvas.property("wireDragState")), variant_value(
                    canvas.wireDragPreviewConnection()
                )

            canvas.setProperty("selectedEdgeIds", [])
            multi_state, multi_preview = pointer_drag(
                source_a_id,
                "out",
                "out",
                replacement_source,
                Qt.KeyboardModifier.ControlModifier,
            )
            assert multi_state["rewire"] is True
            assert multi_state["moving_edge_ids"] == bundle_ids, multi_state
            assert multi_state["moving_endpoint"] == "source"
            assert multi_state["copy_requested"] is False
            assert multi_state["append_requested"] is False
            assert len(multi_preview["connections"]) == 2, multi_preview
            assert all(
                connection["connection_mode"] == "rewire"
                and connection["valid_drop"] is True
                for connection in multi_preview["connections"]
            ), multi_preview
            assert shell_bridge.rewire_calls == []
            QTest.mouseRelease(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.ControlModifier,
                replacement_source,
            )
            settle_events(4)
            assert shell_bridge.rewire_calls == [
                (bundle_ids, "source", source_b_id, "out", False, False)
            ]
            assert shell_bridge.quick_insert_calls == []
            assert canvas.property("wireDragState") is None
            assert snapshot_policy.calls[-1] == (
                "rewire",
                bundle_ids,
                "source",
                False,
                False,
            )

            incompatible_source_dot = named_item(
                host_for(incompatible_id),
                "graphNodeOutputPortDot",
                "bad_out",
            )
            incompatible_source = item_scene_point(incompatible_source_dot)
            multi_origin, multi_x, multi_y = begin_ctrl_drag(
                source_a_id,
                "out",
                "out",
                control,
            )
            rejected_call_count = len(shell_bridge.rewire_calls)
            finish_ctrl_drag(
                source_a_id,
                "out",
                "out",
                multi_origin,
                multi_x,
                multi_y,
                incompatible_source,
                control,
                incompatible_dot=incompatible_source_dot,
            )
            assert len(shell_bridge.rewire_calls) == rejected_call_count

            canvas.setProperty("selectedEdgeIds", [])
            begin_ctrl_drag(source_a_id, "out", "out", control_shift)
            assert canvas.property("wireDragState") is None

            canvas.setProperty("selectedEdgeIds", [edge_a_id, edge_b_id])
            begin_ctrl_drag(source_a_id, "out", "out", control_shift)
            assert canvas.property("wireDragState") is None

            canvas.setProperty("selectedEdgeIds", [edge_a_id])
            copy_state, copy_preview = pointer_drag(
                source_a_id,
                "out",
                "out",
                replacement_source,
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            )
            assert copy_state["moving_edge_ids"] == [edge_a_id], copy_state
            assert copy_state["copy_requested"] is True
            assert copy_state["append_requested"] is True
            assert copy_preview["connection_mode"] == "copy", copy_preview
            assert copy_preview["valid_drop"] is True
            QTest.mouseRelease(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
                replacement_source,
            )
            settle_events(4)
            assert shell_bridge.rewire_calls[-1] == (
                [edge_a_id],
                "source",
                source_b_id,
                "out",
                True,
                True,
            )

            source_origin, source_x, source_y = begin_ctrl_drag(
                source_a_id,
                "out",
                "out",
                control_shift,
            )
            state = variant_value(canvas.property("wireDragState"))
            assert state["rewire"] is True
            assert state["moving_edge_ids"] == [edge_a_id]
            assert state["moving_endpoint"] == "source"
            assert state["origin_node_id"] == source_a_id
            assert state["origin_port_key"] == "out"
            source_active_state, source_preview = finish_ctrl_drag(
                source_a_id,
                "out",
                "out",
                source_origin,
                source_x,
                source_y,
                replacement_source,
                control_shift,
                replacement_source_dot,
            )
            assert source_active_state["compatibility_snapshot_valid"] is True
            assert source_active_state["compatibility_candidate_role"] == "source"
            assert len(source_active_state["compatibility_catalog_generation"]) == 64
            assert source_preview["connection_mode"] == "copy", source_preview
            assert shell_bridge.rewire_calls[-1] == (
                [edge_a_id], "source", source_b_id, "out", True, True
            )
            assert shell_bridge.quick_insert_calls == []
            assert canvas.property("wireDragState") is None
            assert snapshot_policy.calls[-1] == (
                "rewire", [edge_a_id], "source", True, True
            )

            canvas.setProperty("selectedEdgeIds", [])
            target_origin, target_x, target_y = begin_ctrl_drag(
                target_a_id,
                "in",
                "in",
                control,
            )
            target_state = variant_value(canvas.property("wireDragState"))
            assert target_state["rewire"] is True
            assert target_state["moving_edge_ids"] == [edge_a_id]
            assert target_state["moving_endpoint"] == "target"
            _target_active_state, target_preview = finish_ctrl_drag(
                target_a_id,
                "in",
                "in",
                target_origin,
                target_x,
                target_y,
                QPoint(850, 580),
                control,
            )
            assert target_preview["connection_mode"] == "disconnect", target_preview
            assert shell_bridge.rewire_calls[-1] == (
                [edge_a_id], "target", "", "", False, False
            )
            assert shell_bridge.quick_insert_calls == []
            assert snapshot_policy.calls[-1] == (
                "rewire", [edge_a_id], "target", False, False
            )

            no_op_count = len(shell_bridge.rewire_calls)
            original_target = port_point(target_a_id, "graphNodeInputPortDot", "in")
            target_origin, target_x, target_y = begin_ctrl_drag(
                target_a_id,
                "in",
                "in",
                control,
            )
            finish_ctrl_drag(
                target_a_id,
                "in",
                "in",
                target_origin,
                target_x,
                target_y,
                original_target,
                control,
            )
            assert len(shell_bridge.rewire_calls) == no_op_count

            incompatible_target = port_point(incompatible_id, "graphNodeInputPortDot", "bad")
            target_origin, target_x, target_y = begin_ctrl_drag(
                target_a_id,
                "in",
                "in",
                control,
            )
            finish_ctrl_drag(
                target_a_id,
                "in",
                "in",
                target_origin,
                target_x,
                target_y,
                incompatible_target,
                control,
            )
            assert len(shell_bridge.rewire_calls) == no_op_count

            begin_ctrl_drag(target_a_id, "in", "in", control)
            assert canvas.property("wireDragState") is not None
            canvas.cancelWireDrag()
            assert canvas.property("wireDragState") is None
            assert len(shell_bridge.rewire_calls) == no_op_count
            assert shell_bridge.quick_insert_calls == []

            def assert_fail_closed_snapshot(mode):
                snapshot_policy.mode = mode
                call_count = len(snapshot_policy.calls)
                origin, scene_x, scene_y = begin_ctrl_drag(
                    source_b_id,
                    "out",
                    "out",
                    0,
                )
                release = port_point(target_b_id, "graphNodeInputPortDot", "in")
                for _move_index in range(4):
                    canvas.updatePortWireDrag(
                        source_b_id,
                        "out",
                        "out",
                        scene_x,
                        scene_y,
                        release.x(),
                        release.y(),
                        True,
                        0,
                    )
                settle_events(2)
                state = variant_value(canvas.property("wireDragState"))
                preview = variant_value(canvas.wireDragPreviewConnection())
                assert state["compatibility_snapshot_loaded"] is True
                assert state["compatibility_snapshot_valid"] is False
                assert preview["valid_drop"] is False
                assert len(snapshot_policy.calls) == call_count + 1
                assert snapshot_policy.calls[-1] == (
                    "connect", source_b_id, "out", "target"
                )
                canvas.cancelWireDrag()

            assert_fail_closed_snapshot("generation_mismatch")
            assert_fail_closed_snapshot("malformed")
            snapshot_policy.mode = "normal"
            quick_origin, quick_scene_x, quick_scene_y = begin_ctrl_drag(
                source_b_id,
                "out",
                "out",
                0,
            )
            finish_ctrl_drag(
                source_b_id,
                "out",
                "out",
                quick_origin,
                quick_scene_x,
                quick_scene_y,
                QPoint(850, 40),
                0,
            )
            assert len(shell_bridge.quick_insert_calls) == 1
            assert shell_bridge.quick_insert_calls[0][0:2] == (source_b_id, "out")
            release_call_count = len(snapshot_policy.calls)
            _release_origin, release_scene_x, release_scene_y = begin_ctrl_drag(
                source_b_id,
                "out",
                "out",
                0,
            )
            canvas.finishPortWireDrag(
                source_b_id,
                "out",
                "out",
                release_scene_x,
                release_scene_y,
                850,
                40,
                True,
                0,
            )
            settle_events(2)
            assert len(snapshot_policy.calls) == release_call_count + 1
            assert len(shell_bridge.quick_insert_calls) == 2

            shell_bridge.rewire_delegate = scene
            edge_layer = named_item(canvas, "graphCanvasEdgeLayer")
            history = RuntimeGraphHistory()
            scene.bind_runtime_history(history)
            workspace_id = model.active_workspace.workspace_id
            topology_before_copy = model.active_workspace.capture_snapshot()
            history_before_copy = history.undo_depth(workspace_id)
            canvas.setProperty("selectedEdgeIds", [edge_a_id])
            copy_blank_origin, copy_blank_x, copy_blank_y = begin_ctrl_drag(
                source_a_id,
                "out",
                "out",
                control_shift,
            )
            _copy_blank_state, copy_blank_preview = finish_ctrl_drag(
                source_a_id,
                "out",
                "out",
                copy_blank_origin,
                copy_blank_x,
                copy_blank_y,
                QPoint(880, 30),
                control_shift,
            )
            assert copy_blank_preview["connection_mode"] == "noop", copy_blank_preview
            assert copy_blank_preview["active_data_wire"] is True
            assert model.active_workspace.capture_snapshot() == topology_before_copy
            assert history.undo_depth(workspace_id) == history_before_copy

            blank_origin, blank_x, blank_y = begin_ctrl_drag(
                source_a_id,
                "out",
                "out",
                control,
            )
            _blank_state, blank_preview = finish_ctrl_drag(
                source_a_id,
                "out",
                "out",
                blank_origin,
                blank_x,
                blank_y,
                QPoint(880, 30),
                control,
            )
            blank_connections = blank_preview["connections"]
            assert [connection["edge_id"] for connection in blank_connections] == bundle_ids
            assert all(
                connection["connection_mode"] == "disconnect"
                and connection["active_data_wire"] is True
                for connection in blank_connections
            ), blank_connections
            settle_events(4)
            assert all(edge_id not in model.active_workspace.edges for edge_id in bundle_ids)

            preserved_edge_ids = [
                scene.add_edge(source_a_id, "out", target_a_id, "in"),
                scene.add_edge(source_a_id, "out", target_b_id, "in"),
            ]
            preserved_edge_ids.sort(
                key=lambda edge_id: (
                    model.active_workspace.edges[edge_id].input_order,
                    edge_id,
                )
            )
            settle_events(4)
            incompatible_source = port_point(
                incompatible_id,
                "graphNodeOutputPortDot",
                "bad_out",
            )
            invalid_origin, invalid_x, invalid_y = begin_ctrl_drag(
                source_a_id,
                "out",
                "out",
                control,
            )
            _invalid_state, invalid_preview = finish_ctrl_drag(
                source_a_id,
                "out",
                "out",
                invalid_origin,
                invalid_x,
                invalid_y,
                incompatible_source,
                control,
            )
            invalid_connections = invalid_preview["connections"]
            assert [connection["edge_id"] for connection in invalid_connections] == preserved_edge_ids
            assert all(
                connection["connection_mode"] == "noop"
                and connection["active_data_wire"] is True
                for connection in invalid_connections
            ), invalid_connections
            assert all(edge_id in model.active_workspace.edges for edge_id in preserved_edge_ids)

            original_source = port_point(
                source_a_id,
                "graphNodeOutputPortDot",
                "out",
            )
            original_origin, original_x, original_y = begin_ctrl_drag(
                source_a_id,
                "out",
                "out",
                control,
            )
            _original_state, original_preview = finish_ctrl_drag(
                source_a_id,
                "out",
                "out",
                original_origin,
                original_x,
                original_y,
                original_source,
                control,
            )
            original_connections = original_preview["connections"]
            assert [connection["edge_id"] for connection in original_connections] == preserved_edge_ids
            assert all(
                connection["connection_mode"] == "noop"
                and connection["active_data_wire"] is True
                for connection in original_connections
            ), original_connections
            assert all(edge_id in model.active_workspace.edges for edge_id in preserved_edge_ids)

            dispose_host_window(canvas, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_display_mode_menus_target_only_active_data_wires(self) -> None:
        self._run_qml_probe(
            "display-mode-menu-active-wire-filtering",
            """
            import textwrap

            from PyQt6.QtCore import QObject, QUrl
            from PyQt6.QtQml import QQmlComponent

            canvas_component = QQmlComponent(engine)
            canvas_component.setData(
                textwrap.dedent(
                    '''
                    import QtQuick 2.15

                    Item {
                        id: root
                        width: 900
                        height: 700
                        property bool edgeContextVisible: true
                        property bool nodeContextVisible: false
                        property bool selectionContextVisible: false
                        property bool canvasOptionsVisible: false
                        property bool prefs: false
                        property var executionFacts: null
                        property var canvasStateBridgeRef: null
                        property string edgeContextEdgeId: "active_edge"
                        property var selectedEdgeIds: ["active_edge", "passive_edge", "flow_edge"]
                        property real contextMenuX: 180
                        property real contextMenuY: 120
                        property var displayCalls: []
                        property var edgePayloads: ({
                            "active_edge": {
                                "edge_id": "active_edge",
                                "active_data_wire": true,
                                "edge_family": "data",
                                "enabled": true,
                                "visual_style": {"display_mode": "faint"}
                            },
                            "passive_edge": {
                                "edge_id": "passive_edge",
                                "active_data_wire": false,
                                "edge_family": "data",
                                "enabled": true,
                                "visual_style": {"display_mode": "default"}
                            },
                            "flow_edge": {
                                "edge_id": "flow_edge",
                                "active_data_wire": false,
                                "edge_family": "flow",
                                "enabled": true,
                                "visual_style": {"display_mode": "default"}
                            }
                        })

                        function _normalizeEdgeIds(values) {
                            var result = [];
                            for (var i = 0; i < (values || []).length; ++i) {
                                var edgeId = String(values[i] || "");
                                if (edgeId.length && result.indexOf(edgeId) < 0)
                                    result.push(edgeId);
                            }
                            return result;
                        }
                        function _sceneEdgePayload(edgeId) {
                            return edgePayloads[String(edgeId || "")] || null;
                        }
                        function _liveEdgePayload(edgeId) {
                            return _sceneEdgePayload(edgeId);
                        }
                        function _edgeSupportsFlowStyle(edgeId) {
                            var payload = _sceneEdgePayload(edgeId);
                            return Boolean(payload && payload.edge_family === "flow");
                        }
                        function edgeSelectionAllEnabled(_edgeId) { return true; }
                        function setEdgesDisplayMode(edgeIds, mode) {
                            var next = displayCalls.slice(0);
                            next.push({"edge_ids": _normalizeEdgeIds(edgeIds), "mode": String(mode || "")});
                            displayCalls = next;
                            return true;
                        }
                        function _closeContextMenus() {
                            edgeContextVisible = false;
                            canvasOptionsVisible = false;
                        }
                        function snapToGridEnabled() { return false; }
                    }
                    '''
                ).encode("utf-8"),
                QUrl.fromLocalFile(str(repo_root) + "/"),
            )
            if canvas_component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in canvas_component.errors())
                raise AssertionError("Failed to load display-mode canvas stub:\\n" + errors)
            canvas_item = canvas_component.create()
            if canvas_item is None:
                errors = "\\n".join(error.toString() for error in canvas_component.errors())
                raise AssertionError("Failed to instantiate display-mode canvas stub:\\n" + errors)

            action_router = create_component(
                components_dir / "graph_canvas" / "GraphCanvasActionRouter.qml",
                {"canvasItem": canvas_item},
            )
            menus = create_component(
                components_dir / "graph_canvas" / "GraphCanvasContextMenus.qml",
                {
                    "canvasItem": canvas_item,
                    "canvasActionRouter": action_router,
                },
            )
            menus_window = attach_host_to_window(menus, 900, 700)
            settle_events(4)
            edge_popup = named_item(menus, "graphCanvasEdgeContextPopup")
            display_popup = named_item(menus, "graphCanvasEdgeDisplayModeContextPopup")
            active_actions = [variant_value(action) for action in variant_list(edge_popup.property("visibleActions"))]
            assert "Display Mode" in [str(action.get("text", "")) for action in active_actions], ("active actions", active_actions)

            edge_popup.actionTriggered.emit("edge_display_mode_menu")
            settle_events(2)
            assert bool(display_popup.property("visible")) is True, "display popup did not open"
            display_actions = [
                variant_value(action)
                for action in variant_list(display_popup.property("visibleActions"))
            ]
            assert [str(action.get("text", "")) for action in display_actions] == [
                "Default", "Faint", "Hidden"
            ], ("display actions", display_actions)
            assert [bool(action.get("checked")) for action in display_actions] == [False, True, False], ("display checks", display_actions)
            display_popup.actionTriggered.emit("edge_display_mode:hidden")
            settle_events(2)
            assert variant_value(canvas_item.property("displayCalls")) == [
                {"edge_ids": ["active_edge"], "mode": "hidden"}
            ], ("display calls after context", variant_value(canvas_item.property("displayCalls")))

            for unavailable_edge_id in ("passive_edge", "flow_edge"):
                canvas_item.setProperty("edgeContextEdgeId", unavailable_edge_id)
                canvas_item.setProperty("edgeContextVisible", True)
                settle_events(2)
                unavailable_actions = [
                    variant_value(action)
                    for action in variant_list(edge_popup.property("visibleActions"))
                ]
                assert "Display Mode" not in [
                    str(action.get("text", "")) for action in unavailable_actions
                ], (unavailable_edge_id, unavailable_actions)
            assert variant_value(canvas_item.property("displayCalls")) == [
                {"edge_ids": ["active_edge"], "mode": "hidden"}
            ], ("display calls after unavailable", variant_value(canvas_item.property("displayCalls")))

            dispose_host_window(menus, menus_window)
            options = create_component(
                components_dir / "graph_canvas" / "GraphCanvasOptionsMenu.qml",
                {"canvasItem": canvas_item},
            )
            options_window = attach_host_to_window(options, 900, 700)
            canvas_item.setProperty(
                "selectedEdgeIds",
                ["active_edge", "passive_edge", "flow_edge"],
            )
            settle_events(3)
            assert variant_list(options.property("selectedWireEdgeIds")) == ["active_edge"], ("selected ids", variant_list(options.property("selectedWireEdgeIds")))
            assert str(options.property("selectedWireDisplayModeValue")) == "faint", options.property("selectedWireDisplayModeValue")
            calls_before_batch = len(variant_list(canvas_item.property("displayCalls")))
            assert bool(options.setSelectedWiresDisplayMode("hidden")) is True, "selected display update rejected"
            settle_events(2)
            display_calls = [
                variant_value(call)
                for call in variant_list(canvas_item.property("displayCalls"))
            ]
            assert len(display_calls) == calls_before_batch + 1, ("batch count", display_calls)
            assert display_calls[-1] == {"edge_ids": ["active_edge"], "mode": "hidden"}, ("batch payload", display_calls)

            canvas_item.setProperty("selectedEdgeIds", ["passive_edge", "flow_edge"])
            settle_events(2)
            assert variant_list(options.property("selectedWireEdgeIds")) == [], ("empty selected ids", variant_list(options.property("selectedWireEdgeIds")))
            assert bool(options.setSelectedWiresDisplayMode("faint")) is False, "empty selection accepted"
            assert len(variant_list(canvas_item.property("displayCalls"))) == calls_before_batch + 1, variant_list(canvas_item.property("displayCalls"))

            dispose_host_window(options, options_window)
            action_router.deleteLater()
            canvas_item.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )


class GraphSurfaceLockedNodeCanvasRoutingTests(GraphSurfaceInputContractTestBase):
    def test_node_context_menu_routes_editors_and_preserves_locked_node_affordance(self) -> None:
        self._run_qml_probe(
            "node-context-menu-editor-routing",
            """
            import textwrap

            from PyQt6.QtCore import QObject, pyqtSlot, QUrl
            from PyQt6.QtQml import QQmlComponent
            from ea_node_editor.ui.tooltips import TooltipCopyBridge

            class AddonManagerBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.requests = []

                @pyqtSlot(str)
                def requestOpen(self, focus_addon_id):
                    self.requests.append(str(focus_addon_id))

            addon_bridge = AddonManagerBridgeStub()

            class GraphActionBridgeStub(QObject):
                def __init__(self, addon_manager_bridge):
                    super().__init__()
                    self._addon_manager_bridge = addon_manager_bridge
                    self.actions = []

                @pyqtSlot(str, "QVariantMap", result=bool)
                def trigger_graph_action(self, action_id, payload):
                    action_id = str(action_id or "")
                    self.actions.append((action_id, dict(payload or {})))
                    if action_id == "open_addon_manager_for_node":
                        self._addon_manager_bridge.requestOpen("tests.addons.signal_pack")
                        return True
                    return False

            graph_action_bridge = GraphActionBridgeStub(addon_bridge)

            class SettingsCommandBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.calls = []
                    self.dynamic_calls = []

                @pyqtSlot(str, str, bool, result=bool)
                def set_node_settings_group_expanded(self, node_id, group_id, expanded):
                    self.calls.append((str(node_id), str(group_id), bool(expanded)))
                    return True

                @pyqtSlot(str, str, int, result=str)
                def insert_dynamic_port(self, node_id, group_id, ordinal):
                    self.dynamic_calls.append((str(node_id), str(group_id), int(ordinal)))
                    return "input1"

            settings_bridge = SettingsCommandBridgeStub()
            engine.rootContext().setContextProperty("addonBridge", addon_bridge)
            engine.rootContext().setContextProperty("settingsBridge", settings_bridge)
            tooltip_copy_bridge = TooltipCopyBridge()
            engine.rootContext().setContextProperty("tooltipCopyBridge", tooltip_copy_bridge)
            shell_context_component = QQmlComponent(engine)
            shell_context_component.setData(
                b'''
                import QtQml 2.15
                QtObject {
                    property var addonManagerBridge: addonBridge
                }
                ''',
                QUrl.fromLocalFile(str(repo_root) + "/"),
            )
            if shell_context_component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in shell_context_component.errors())
                raise AssertionError("Failed to load shell context stub:\\n" + errors)
            shell_context = shell_context_component.create()
            if shell_context is None:
                errors = "\\n".join(error.toString() for error in shell_context_component.errors())
                raise AssertionError("Failed to instantiate shell context stub:\\n" + errors)

            engine.rootContext().setContextProperty("shellContext", shell_context)

            menus_qml_path = components_dir / "graph_canvas" / "GraphCanvasContextMenus.qml"
            editable_payload = node_payload()
            editable_payload["node_id"] = "node_locked_context"
            editable_payload["read_only"] = False
            editable_payload["runtime_behavior"] = "passive"
            editable_payload["surface_family"] = ""
            editable_payload["port_presentation"] = {}
            editable_payload["settings_groups"] = [
                {"group_id": "general", "label": "General Options", "expanded": False},
                {"group_id": "plot", "label": "Signal plot options", "expanded": True},
            ]
            editable_payload["dynamic_port_groups"] = [
                {
                    "id": "inputs",
                    "direction": "in",
                    "port_keys": [],
                    "can_insert": True,
                    "removable_port_keys": [],
                    "rename_mode": "key",
                },
                {
                    "id": "outputs",
                    "direction": "out",
                    "port_keys": ["result"],
                    "can_insert": True,
                    "removable_port_keys": ["result"],
                    "rename_mode": "key",
                },
            ]
            panel_payload = dict(editable_payload)
            panel_payload["type_id"] = "data.panel"
            panel_payload["properties"] = {"interpretation": "auto"}
            locked_payload = dict(editable_payload)
            locked_payload["read_only"] = True
            locked_payload["unresolved"] = True
            locked_payload["addon_id"] = "tests.addons.signal_pack"
            locked_payload["locked_state"] = {
                "focus_addon_id": "tests.addons.signal_pack",
                "label": "Requires add-on",
            }
            canvas_component = QQmlComponent(engine)
            canvas_component.setData(
                textwrap.dedent(
                    '''
                    import QtQuick 2.15

                    Item {
                        id: root
                        property bool nodeContextVisible: true
                        property real contextMenuX: 16
                        property real contextMenuY: 22
                        property string nodeContextNodeId: "node_locked_context"
                        property var payload: ({})
                        property int closeCalls: 0
                        property string linkPopoverNodeId: ""
                        property string linkPopoverWorkspaceId: ""
                        property string commentEditorNodeId: ""
                        property bool commentCompose: false
                        property string surfaceActions: ""
                        property string hostLookupNodeId: ""
                        property var sceneCommandBridge: settingsBridge
                        property var canvasViewBridgeRef: lowZoomView

                        QtObject {
                            id: lowZoomView
                            property real center_x: 0
                            property real center_y: 0
                            property real zoom_value: 0.5
                        }

                        Item {
                            id: surfaceHost

                            function dispatchSurfaceAction(actionId) {
                                root.surfaceActions += (root.surfaceActions.length ? "," : "") + String(actionId || "")
                                return true
                            }
                        }

                        function _sceneNodePayload(nodeId) {
                            return String(nodeId || "") === nodeContextNodeId ? payload : ({})
                        }

                        function _nodeCanEnterScope(nodeId) {
                            return false
                        }

                        function _nodeSupportsPassiveStyle(nodeId) {
                            return false
                        }

                        function selectedNodeIds() {
                            return []
                        }

                        function hostForNodeId(nodeId) {
                            hostLookupNodeId = String(nodeId || "")
                            return surfaceHost
                        }

                        function _closeContextMenus() {
                            closeCalls += 1
                            nodeContextVisible = false
                        }

                        function requestAddNodeLinkForNode(nodeId) {
                            var nodeData = _sceneNodePayload(nodeId)
                            return openNodeLinkEditor(nodeData, "workspace_context")
                        }

                        function openNodeLinkEditor(nodeData, workspaceId) {
                            linkPopoverNodeId = nodeData ? String(nodeData.node_id || "") : ""
                            linkPopoverWorkspaceId = String(workspaceId || "")
                            return linkPopoverNodeId.length > 0 && linkPopoverWorkspaceId.length > 0
                        }

                        function openNodeCommentEditor(nodeData, compose) {
                            commentEditorNodeId = nodeData ? String(nodeData.node_id || "") : ""
                            commentCompose = Boolean(compose)
                            return commentEditorNodeId.length > 0
                        }
                    }
                    '''
                ).encode("utf-8"),
                QUrl.fromLocalFile(str(repo_root) + "/"),
            )
            if canvas_component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in canvas_component.errors())
                raise AssertionError("Failed to load canvas stub QML:\\n" + errors)
            canvas_item = canvas_component.create()
            if canvas_item is None:
                errors = "\\n".join(error.toString() for error in canvas_component.errors())
                raise AssertionError("Failed to instantiate canvas stub QML:\\n" + errors)
            canvas_item.setProperty("payload", editable_payload)
            menus = create_component(
                menus_qml_path,
                {
                    "canvasItem": canvas_item,
                    "graphActionBridge": graph_action_bridge,
                },
            )
            popup = menus.findChild(QObject, "graphCanvasNodeContextPopup")
            settings_popup = menus.findChild(QObject, "graphCanvasNodeSettingsContextPopup")
            assert popup is not None
            assert settings_popup is not None

            visible_actions = [variant_value(action) for action in variant_list(popup.property("visibleActions"))]
            action_texts = [str(action.get("text", "")) for action in visible_actions]
            assert action_texts == [
                "Settings",
                "Add Input",
                "Add Output",
                "Add Link",
                "Add Comment",
                "Rename Node",
                "Remove Node",
            ], action_texts

            canvas_item.setProperty("payload", dict(editable_payload, runtime_behavior="action"))
            settle_events(2)
            visible_actions = [variant_value(action) for action in variant_list(popup.property("visibleActions"))]
            assert "Run Settings..." in [str(action.get("text", "")) for action in visible_actions]
            canvas_item.setProperty("payload", editable_payload)

            popup.actionTriggered.emit("node_context::add_link")
            settle_events(2)

            assert str(canvas_item.property("linkPopoverNodeId")) == "node_locked_context"
            assert str(canvas_item.property("linkPopoverWorkspaceId")) == "workspace_context"
            assert int(canvas_item.property("closeCalls")) == 1, canvas_item.property("closeCalls")
            assert bool(canvas_item.property("nodeContextVisible")) is False

            canvas_item.setProperty("nodeContextVisible", True)
            popup.actionTriggered.emit("node_context::add_comment")
            settle_events(2)

            assert str(canvas_item.property("commentEditorNodeId")) == "node_locked_context"
            assert bool(canvas_item.property("commentCompose")) is True
            assert int(canvas_item.property("closeCalls")) == 2, canvas_item.property("closeCalls")
            assert bool(canvas_item.property("nodeContextVisible")) is False

            canvas_item.setProperty("payload", panel_payload)
            canvas_item.setProperty("nodeContextVisible", True)
            settle_events(2)
            visible_actions = [variant_value(action) for action in variant_list(popup.property("visibleActions"))]
            panel_actions = [
                action for action in visible_actions
                if str(action.get("actionId", "")).startswith("panel_")
            ]
            assert [(action["actionId"], action["text"]) for action in panel_actions] == [
                ("panel_edit", "Edit values and interpretation..."),
                ("panel_copy", "Copy"),
                ("panel_copy_tree", "Copy as tree"),
            ], panel_actions
            assert "checked" not in panel_actions[0], panel_actions[0]

            for index, action_id in enumerate(("panel_edit", "panel_copy", "panel_copy_tree"), start=1):
                popup.actionTriggered.emit(action_id)
                settle_events(2)
                assert str(canvas_item.property("hostLookupNodeId")) == "node_locked_context"
                assert int(canvas_item.property("closeCalls")) == 2 + index
                if index < 3:
                    canvas_item.setProperty("nodeContextVisible", True)

            assert str(canvas_item.property("surfaceActions")) == (
                "panel_edit,panel_copy,panel_copy_tree"
            )

            canvas_item.setProperty("payload", editable_payload)
            canvas_item.setProperty("nodeContextVisible", True)
            popup.actionTriggered.emit("node_context::settings")
            settle_events(2)
            assert bool(settings_popup.property("visible")) is True
            settings_actions = [
                variant_value(action)
                for action in variant_list(settings_popup.property("visibleActions"))
            ]
            assert [action["text"] for action in settings_actions] == [
                "General Options",
                "Signal plot options",
            ], settings_actions
            assert [bool(action.get("checked")) for action in settings_actions] == [False, True]
            settings_popup.actionTriggered.emit("node_context::settings_group::general")
            settle_events(2)
            assert settings_bridge.calls == [
                ("node_locked_context", "general", True)
            ], settings_bridge.calls
            assert int(canvas_item.property("closeCalls")) == 6

            canvas_item.setProperty("nodeContextVisible", True)
            popup.actionTriggered.emit("node_context::dynamic_port_add::inputs")
            settle_events(2)
            assert settings_bridge.dynamic_calls == [
                ("node_locked_context", "inputs", 0)
            ], settings_bridge.dynamic_calls
            assert int(canvas_item.property("closeCalls")) == 7

            canvas_item.setProperty("payload", locked_payload)
            canvas_item.setProperty("nodeContextVisible", True)
            settle_events(2)
            visible_actions = [variant_value(action) for action in variant_list(popup.property("visibleActions"))]
            action_texts = [str(action.get("text", "")) for action in visible_actions]
            assert action_texts == ["Add Input", "Add Output", "Open Add-On Manager"], action_texts
            assert [bool(action.get("enabled", True)) for action in visible_actions[:2]] == [False, False]

            popup.actionTriggered.emit("open_addon_manager_for_node")
            settle_events(2)

            assert addon_bridge.requests == ["tests.addons.signal_pack"], addon_bridge.requests
            assert graph_action_bridge.actions[-1][0] == "open_addon_manager_for_node", graph_action_bridge.actions
            assert graph_action_bridge.actions[-1][1] == {"node_id": "node_locked_context"}, graph_action_bridge.actions
            assert int(canvas_item.property("closeCalls")) == 8, canvas_item.property("closeCalls")
            assert bool(canvas_item.property("nodeContextVisible")) is False, canvas_item.property("nodeContextVisible")

            menus.deleteLater()
            canvas_item.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_shared_node_link_editor_validates_targets_and_resets_only_after_save(self) -> None:
        self._run_qml_probe(
            "shared-node-link-editor-contract",
            """
            from PyQt6.QtCore import QMetaObject, QUrl
            from PyQt6.QtQml import QQmlComponent

            component = QQmlComponent(engine)
            component.setData(
                b'''
                import QtQuick 2.15
                import "ea_node_editor/ui_qml/components/common" as Common

                Item {
                    id: root
                    width: 360
                    height: 600

                    Common.NodeLinkEditorForm {
                        id: form
                        width: 320
                        objectNamePrefix: "probeNodeLink"
                        hideWhilePicking: true
                        nodeOptions: [{
                            "label": "Target node",
                            "subtitle": "Reports - Logger",
                            "target": "node_target",
                            "target_workspace_id": "workspace_reports",
                            "target_node_id": "node_target"
                        }]
                        workspaceOptions: [{
                            "label": "Reports",
                            "subtitle": "Workspace",
                            "target": "workspace_reports",
                            "target_workspace_id": "workspace_reports"
                        }]
                    }

                    function beginAdd() {
                        form.beginAdd()
                    }

                    function selectNodeTarget() {
                        form._setEditingKind("node", true)
                        form.selectTargetOption(form.nodeOptions[0])
                    }

                    function beginNodePick() {
                        form.requestPickTarget()
                    }

                    function resumeNodePick() {
                        form.resumeAfterPickCancel()
                    }

                    function requestSave() {
                        form.requestSave()
                    }

                    function failSave() {
                        form.completeSave("")
                    }

                    function finishSave() {
                        form.completeSave("stored-link")
                    }

                    function cancelEdit() {
                        form.cancelEdit()
                    }
                }
                ''',
                QUrl.fromLocalFile(str(repo_root) + "/"),
            )
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load shared node-link form:\\n" + errors)
            root = component.create()
            if root is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate shared node-link form:\\n" + errors)
            form = named_item(root, "probeNodeLinkEditorForm")
            save_button = named_item(root, "probeNodeLinkSaveButton")
            saves = []
            closes = []
            form.saveRequested.connect(lambda draft: saves.append(variant_value(draft)))
            form.editorClosed.connect(lambda saved: closes.append(bool(saved)))

            kinds = [
                (str(item["label"]), str(item["value"]))
                for item in variant_list(form.property("linkKindOptions"))
            ]
            assert kinds == [
                ("Web", "url"),
                ("File", "file"),
                ("Folder", "folder"),
                ("Workspace", "workspace"),
                ("Node", "node"),
            ], kinds

            QMetaObject.invokeMethod(root, "beginAdd")
            app.processEvents()
            assert bool(form.property("editorOpen")) is True
            assert bool(save_button.property("enabled")) is False
            QMetaObject.invokeMethod(root, "requestSave")
            assert saves == []

            QMetaObject.invokeMethod(root, "selectNodeTarget")
            app.processEvents()
            assert str(form.property("editingKind")) == "node"
            assert str(form.property("editingTarget")) == "node_target"
            assert str(form.property("editingTargetWorkspaceId")) == "workspace_reports"
            assert str(form.property("editingTargetNodeId")) == "node_target"
            assert bool(save_button.property("enabled")) is True

            QMetaObject.invokeMethod(root, "beginNodePick")
            app.processEvents()
            assert bool(form.property("pickModeActive")) is True
            assert bool(form.property("visible")) is False
            assert bool(form.property("editorOpen")) is True
            QMetaObject.invokeMethod(root, "resumeNodePick")
            app.processEvents()
            assert bool(form.property("pickModeActive")) is False
            assert bool(form.property("visible")) is True

            form.setProperty("editingTitle", "Draft report link")
            form.setProperty("editingSubtitle", "Keep this subtitle")
            QMetaObject.invokeMethod(root, "requestSave")
            app.processEvents()
            assert saves == [{
                "id": "",
                "kind": "node",
                "title": "Draft report link",
                "target": "node_target",
                "subtitle": "Keep this subtitle",
                "target_workspace_id": "workspace_reports",
                "target_node_id": "node_target",
            }], saves

            QMetaObject.invokeMethod(root, "failSave")
            app.processEvents()
            assert bool(form.property("editorOpen")) is True
            assert str(form.property("editingTitle")) == "Draft report link"
            assert closes == []

            QMetaObject.invokeMethod(root, "finishSave")
            app.processEvents()
            assert bool(form.property("editorOpen")) is False
            assert str(form.property("editingKind")) == "url"
            assert str(form.property("editingTitle")) == ""
            assert str(form.property("editingTargetWorkspaceId")) == ""
            assert str(form.property("editingTargetNodeId")) == ""
            assert closes == [True]

            QMetaObject.invokeMethod(root, "beginAdd")
            form.setProperty("editingTarget", "https://example.com")
            QMetaObject.invokeMethod(root, "cancelEdit")
            app.processEvents()
            assert bool(form.property("editorOpen")) is False
            assert str(form.property("editingTarget")) == ""
            assert closes == [True, False]

            root.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_context_menus_track_scene_anchor_after_view_pan_zoom(self) -> None:
        self._run_qml_probe(
            "context-menu-scene-anchor-tracking",
            """
            import textwrap

            from PyQt6.QtCore import QObject, QUrl
            from PyQt6.QtQml import QQmlComponent

            menus_qml_path = components_dir / "graph_canvas" / "GraphCanvasContextMenus.qml"
            canvas_component = QQmlComponent(engine)
            canvas_component.setData(
                textwrap.dedent(
                    '''
                    import QtQuick 2.15

                    Item {
                        id: root
                        width: 640
                        height: 480
                        property bool edgeContextVisible: true
                        property bool nodeContextVisible: true
                        property bool selectionContextVisible: true
                        property bool canvasOptionsVisible: true
                        property string edgeContextEdgeId: "edge_context"
                        property string nodeContextNodeId: "node_context"
                        property real contextMenuX: 24
                        property real contextMenuY: 36
                        property bool contextMenuSceneAnchorActive: true
                        property real contextMenuSceneAnchorX: 160
                        property real contextMenuSceneAnchorY: 110
                        property bool selectionContextSceneAnchorActive: false
                        property real selectionContextSceneAnchorX: contextMenuSceneAnchorX
                        property real selectionContextSceneAnchorY: contextMenuSceneAnchorY
                        property var canvasViewBridgeRef: viewBridge
                        property var canvasStateBridgeRef: null
                        property var selectedEdgeIds: []
                        property var edgePayload: [
                            ({
                                "edge_id": "edge_context",
                                "source_node_id": "node_a",
                                "target_node_id": "node_b",
                                "edge_family": "data"
                            })
                        ]
                        property var prefs: ({
                            "showGrid": true,
                            "nodeShadowEnabled": true,
                            "graphsFollowShellTheme": true,
                            "gridStyle": "lines",
                            "activeThemeId": "stitch_dark",
                            "canvasBackgroundVariant": "theme"
                        })
                        property var executionFacts: ({
                            "selectedRunPreviewBeforeRun": true,
                            "nodeElapsedTimeUnit": "seconds"
                        })

                        QtObject {
                            id: viewBridge
                            objectName: "viewBridge"
                            property real center_x: 100
                            property real center_y: 50
                            property real zoom_value: 1.25
                        }

                        function _sceneNodePayload(nodeId) {
                            return {
                                "node_id": String(nodeId || ""),
                                "title": String(nodeId || ""),
                                "type_id": "tests.menu_anchor",
                                "width": 180,
                                "height": 120,
                                "ports": []
                            }
                        }

                        function _sceneEdgePayload(edgeId) {
                            return String(edgeId || "") === "edge_context" ? edgePayload[0] : null
                        }

                        function _nodeCanEnterScope(_nodeId) { return false }
                        function _nodeSupportsPassiveStyle(_nodeId) { return false }
                        function _nodeCanPeekInside(_nodeId) { return false }
                        function _nodeSupportsHelp(_nodeId) { return false }
                        function _edgeSupportsFlowStyle(_edgeId) { return false }
                        function selectedNodeIds() { return ["node_a", "node_b"] }
                        function snapToGridEnabled() { return false }
                        function _closeContextMenus() {}
                    }
                    '''
                ).encode("utf-8"),
                QUrl.fromLocalFile(str(repo_root) + "/"),
            )
            if canvas_component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in canvas_component.errors())
                raise AssertionError("Failed to load canvas anchor stub QML:\\n" + errors)
            canvas_item = canvas_component.create()
            if canvas_item is None:
                errors = "\\n".join(error.toString() for error in canvas_component.errors())
                raise AssertionError("Failed to instantiate canvas anchor stub QML:\\n" + errors)

            menus = create_component(menus_qml_path, {"canvasItem": canvas_item})
            node_popup = menus.findChild(QObject, "graphCanvasNodeContextPopup")
            edge_popup = menus.findChild(QObject, "graphCanvasEdgeContextPopup")
            settings_popup = menus.findChild(QObject, "graphCanvasNodeSettingsContextPopup")
            selection_popup = menus.findChild(QObject, "graphCanvasSelectionContextPopup")
            canvas_options = menus.findChild(QObject, "graphCanvasOptionsPopup")
            assert node_popup is not None
            assert edge_popup is not None
            assert settings_popup is not None
            assert selection_popup is not None
            assert canvas_options is not None

            for popup in (node_popup, edge_popup, settings_popup, selection_popup):
                assert int(popup.property("rowHeight")) == 30
                assert int(popup.property("contentPadding")) == 4

            def expected_x(center_x, zoom):
                return 640 * 0.5 + (160 - center_x) * zoom

            def expected_y(center_y, zoom):
                return 480 * 0.5 + (110 - center_y) * zoom

            def assert_popup_position(label, popup, center_x, center_y, zoom):
                actual_x = float(popup.property("x"))
                actual_y = float(popup.property("y"))
                assert abs(actual_x - expected_x(center_x, zoom)) < 0.01, (
                    label,
                    actual_x,
                    expected_x(center_x, zoom),
                )
                assert abs(actual_y - expected_y(center_y, zoom)) < 0.01, (
                    label,
                    actual_y,
                    expected_y(center_y, zoom),
                )

            def assert_canvas_options_position(center_x, center_y, zoom):
                expected_anchor_x = expected_x(center_x, zoom)
                expected_anchor_y = expected_y(center_y, zoom)
                actual_anchor_x = float(canvas_options.property("anchorX"))
                actual_anchor_y = float(canvas_options.property("anchorY"))
                assert abs(actual_anchor_x - expected_anchor_x) < 0.01
                assert abs(actual_anchor_y - expected_anchor_y) < 0.01

                actual_x = float(canvas_options.property("x"))
                actual_y = float(canvas_options.property("y"))
                viewport_padding = float(canvas_options.property("viewportPadding"))
                popup_height = float(canvas_options.property("height"))
                canvas_height = float(canvas_item.property("height"))
                expected_visible_y = max(
                    viewport_padding,
                    min(
                        expected_anchor_y,
                        canvas_height - popup_height - viewport_padding,
                    ),
                )
                assert abs(actual_x - expected_anchor_x) < 0.01
                assert abs(actual_y - expected_visible_y) < 0.01
                assert actual_y >= viewport_padding
                assert actual_y + popup_height <= canvas_height - viewport_padding

            for label, popup in (
                ("node", node_popup),
                ("edge", edge_popup),
                ("selection", selection_popup),
            ):
                assert_popup_position(label, popup, 100, 50, 1.25)
            assert_canvas_options_position(100, 50, 1.25)

            view_bridge = canvas_item.property("canvasViewBridgeRef")
            view_bridge.setProperty("center_x", 120)
            view_bridge.setProperty("center_y", 80)
            view_bridge.setProperty("zoom_value", 0.5)
            settle_events(3)

            for label, popup in (
                ("node", node_popup),
                ("edge", edge_popup),
                ("selection", selection_popup),
            ):
                assert_popup_position(label, popup, 120, 80, 0.5)
            assert_canvas_options_position(120, 80, 0.5)

            menus.deleteLater()
            canvas_item.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_locked_node_surface_bridge_rejects_mutating_requests(self) -> None:
        self._run_qml_probe(
            "locked-node-surface-bridge-guards",
            """
            from PyQt6.QtCore import QObject, pyqtProperty, pyqtSlot

            class SceneCommandBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.select_calls = []
                    self.property_calls = []
                    self.port_label_calls = []
                    self.property_batch_calls = []
                    self.pending_calls = []

                @pyqtSlot(str, bool)
                def select_node(self, node_id, additive):
                    self.select_calls.append((str(node_id), bool(additive)))

                @pyqtSlot(str, str, "QVariant")
                def set_node_property(self, node_id, key, value):
                    self.property_calls.append((str(node_id), str(key), variant_value(value)))

                @pyqtSlot(str, str, str)
                def set_node_port_label(self, node_id, port_key, label):
                    self.port_label_calls.append((str(node_id), str(port_key), str(label)))

                @pyqtSlot(str, "QVariantMap", result=bool)
                def set_node_properties(self, node_id, properties):
                    self.property_batch_calls.append((str(node_id), dict(properties or {})))
                    return True

                @pyqtSlot(str)
                def set_pending_surface_action(self, node_id):
                    self.pending_calls.append(str(node_id))

                @pyqtSlot(str, result=bool)
                def consume_pending_surface_action(self, _node_id):
                    return False

            class ShellCommandBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.open_scope_calls = []
                    self.browse_calls = []
                    self.color_calls = []

                @pyqtSlot(str, result=bool)
                def request_open_subnode_scope(self, node_id):
                    self.open_scope_calls.append(str(node_id))
                    return True

                @pyqtSlot(str, str, str, result=str)
                def browse_node_property_path(self, node_id, key, current_path):
                    self.browse_calls.append((str(node_id), str(key), str(current_path)))
                    return "C:/tmp/example.txt"

                @pyqtSlot(str, str, str, result=str)
                def pick_node_property_color(self, node_id, key, current_value):
                    self.color_calls.append((str(node_id), str(key), str(current_value)))
                    return "#abcdef"

                @pyqtSlot(int)
                def set_graph_cursor_shape(self, _cursor_shape):
                    pass

                @pyqtSlot()
                def clear_graph_cursor_shape(self):
                    pass

                @pyqtSlot(str, "QVariant", result="QVariantMap")
                def describe_pdf_preview(self, _source, _page_number):
                    return {}

            class CanvasItemStub(QObject):
                def __init__(self, payload, scene_bridge, shell_bridge):
                    super().__init__()
                    self._payload = payload
                    self._scene_bridge = scene_bridge
                    self._shell_bridge = shell_bridge
                    self.close_calls = 0
                    self.pending_clear_calls = 0
                    self.edge_clear_calls = 0
                    self.cancel_wire_drag_calls = 0

                @pyqtProperty(QObject, constant=True)
                def _canvasSceneCommandBridgeRef(self):
                    return self._scene_bridge

                @pyqtProperty(QObject, constant=True)
                def _canvasShellCommandBridgeRef(self):
                    return self._shell_bridge

                @pyqtSlot(str, result="QVariantMap")
                def _sceneNodePayload(self, node_id):
                    if str(node_id) == "node_locked_bridge":
                        return self._payload
                    return {}

                @pyqtSlot()
                def _closeContextMenus(self):
                    self.close_calls += 1

                @pyqtSlot()
                def clearPendingConnection(self):
                    self.pending_clear_calls += 1

                @pyqtSlot()
                def clearEdgeSelection(self):
                    self.edge_clear_calls += 1

                @pyqtSlot()
                def cancelWireDrag(self):
                    self.cancel_wire_drag_calls += 1

                @pyqtSlot(result="QVariantList")
                def selectedNodeIds(self):
                    return []

            bridge_qml_path = components_dir / "graph_canvas" / "GraphCanvasNodeSurfaceBridge.qml"
            payload = node_payload()
            payload["node_id"] = "node_locked_bridge"
            payload["read_only"] = True
            payload["unresolved"] = True
            scene_bridge = SceneCommandBridgeStub()
            shell_bridge = ShellCommandBridgeStub()
            canvas_item = CanvasItemStub(payload, scene_bridge, shell_bridge)
            bridge = create_component(bridge_qml_path, {"canvasItem": canvas_item})

            assert bool(bridge.requestOpenSubnodeScope("node_locked_bridge")) is False
            assert bool(bridge.commitNodeSurfaceProperty("node_locked_bridge", "message", "blocked")) is False
            assert bool(bridge.commitNodePortLabel("node_locked_bridge", "message", "Blocked")) is False
            assert bool(bridge.requestNodeSurfaceCropEdit("node_locked_bridge")) is False
            assert bool(bridge.commitNodeSurfaceProperties("node_locked_bridge", {"message": "blocked"})) is False
            assert str(bridge.browseNodePropertyPath("node_locked_bridge", "source_path", "")) == ""
            assert str(bridge.pickNodePropertyColor("node_locked_bridge", "accent", "#000000")) == ""

            settle_events(2)

            assert scene_bridge.select_calls == []
            assert scene_bridge.property_calls == []
            assert scene_bridge.port_label_calls == []
            assert scene_bridge.property_batch_calls == []
            assert scene_bridge.pending_calls == []
            assert shell_bridge.open_scope_calls == []
            assert shell_bridge.browse_calls == []
            assert shell_bridge.color_calls == []
            assert canvas_item.close_calls == 0
            assert canvas_item.pending_clear_calls == 0
            assert canvas_item.edge_clear_calls == 0
            assert canvas_item.cancel_wire_drag_calls == 0

            bridge.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )


class GraphSurfaceDataflowAuthoringTests(GraphSurfaceInputContractTestBase):
    def test_dynamic_port_authoring_qml_is_metadata_driven_and_accessible(self) -> None:
        ports_source = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph/GraphNodePortsLayer.qml"
        ).read_text(encoding="utf-8")
        row_source = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph/GraphNodePortRow.qml"
        ).read_text(encoding="utf-8")
        menus_source = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasContextMenus.qml"
        ).read_text(encoding="utf-8")
        surface_metrics_source = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph/GraphNodeSurfaceMetrics.js"
        ).read_text(encoding="utf-8")
        standard_metrics_source = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/graph_geometry/standard_metrics.py"
        ).read_text(encoding="utf-8")
        compact_ports = " ".join(ports_source.split())
        compact_row = " ".join(row_source.split())
        compact_menus = " ".join(menus_source.split())
        port_ui_source = ports_source + row_source

        for obsolete in (
            "core.stream_gate",
            "core.python_script",
            "insert_stream_gate_output",
            "remove_stream_gate_output",
            "_insertStreamGateOutput",
            "_removeStreamGateOutput",
        ):
            self.assertNotIn(obsolete, ports_source)
            self.assertNotIn(obsolete, menus_source)

        for payload_key in (
            "dynamic_port_groups",
            "port_keys",
            "can_insert",
            "removable_port_keys",
            "rename_mode",
        ):
            self.assertIn(payload_key, compact_ports + compact_menus)
        self.assertIn(
            "bridge.insert_dynamic_port( root.contextNodeId, String(group.id || \"\"), Number(ordinal) )",
            compact_ports,
        )
        self.assertIn(
            "bridge.remove_dynamic_port( root.contextNodeId, String(group.id || \"\"), String(portKey || \"\") )",
            compact_ports,
        )
        self.assertIn(
            "bridge.rename_dynamic_port( root.contextNodeId, String(group.id || \"\"), String(portKey || \"\"), String(value || \"\") )",
            compact_ports,
        )
        self.assertIn(
            "bridge.insert_dynamic_port(nodeId, groupId, portKeys.length)",
            compact_menus,
        )
        self.assertEqual(ports_source.count('objectName: "graphNodeDynamicPortAdd_"'), 1)
        self.assertIn("model: root.dynamicPortGroups", ports_source)
        self.assertIn(
            "root.dynamicPortGroups = root._copyDynamicPortGroups(groups);",
            ports_source,
        )
        self.assertIn("property int dynamicPortGroupModelRevision: 0", ports_source)
        self.assertIn(
            "signal dynamicPortGroupsApplied(string nodeId, int revision)",
            ports_source,
        )
        self.assertIn("Qt.callLater(function()", ports_source)
        self.assertIn("function onNodes_changed()", ports_source)
        self.assertIn("onContextNodeIdChanged:", ports_source)
        self.assertIn("Number(root.host.floatingToolbarZoom || 1.0) >= 0.95", ports_source)
        self.assertIn("!Boolean(root.host.nodeData.collapsed)", ports_source)
        self.assertIn("root.host.graphReadOnly", ports_source)
        self.assertIn("!Boolean(root.host.nodeData.locked)", ports_source)
        dynamic_menu_source = menus_source.split(
            "function _dynamicPortGroupActions", 1
        )[1].split("function _triggerGraphAction", 1)[0]
        self.assertNotIn("viewZoom", dynamic_menu_source)
        self.assertIn("SurfaceControls.GraphSurfaceButton", row_source)
        self.assertIn("width: root.dynamicPortTargetDiameter", ports_source)
        self.assertIn("width: row.portsLayer.dynamicPortRemoveTargetWidth", row_source)
        self.assertGreaterEqual(port_ui_source.count("focusPolicy: Qt.TabFocus"), 2)
        self.assertGreaterEqual(port_ui_source.count("Accessible.name: tooltipText"), 2)
        self.assertIn('property color actionFillColor: "#55D65B"', ports_source)
        self.assertEqual(
            row_source.count('property color actionFillColor: "#FF5449"'),
            1,
        )
        self.assertIn('text: "+"', ports_source)
        self.assertEqual(row_source.count('text: "\\u2212"'), 1)
        self.assertEqual(port_ui_source.count("anchors.verticalCenterOffset: -1"), 2)
        self.assertIn('objectName: "graphNodeDynamicPortAddCircle"', ports_source)
        self.assertEqual(
            row_source.count('objectName: "graphNodeDynamicPortRemoveCircle"'),
            1,
        )
        self.assertGreaterEqual(
            port_ui_source.count("readonly property bool actionActive: hovered || activeFocus || down"),
            2,
        )
        for control_id in (
            "removeButton",
            "dynamicPortAddButton",
        ):
            self.assertIn(
                f"width: {control_id}.actionActive ? 14 : 6",
                port_ui_source,
            )
            self.assertIn(
                f"opacity: {control_id}.actionActive ? 1.0 : 0.0",
                port_ui_source,
            )
        self.assertGreaterEqual(port_ui_source.count("height: width"), 2)
        self.assertGreaterEqual(port_ui_source.count("radius: width * 0.5"), 2)
        self.assertIn("readonly property real dynamicPortControlCenterInterval:", ports_source)
        self.assertIn(
            "GraphNodeSurfaceMetrics.DYNAMIC_PORT_HANDLE_CENTER_INTERVAL",
            compact_ports,
        )
        self.assertIn(
            '"y": Number(lastPoint.y || 0) + root.dynamicPortControlCenterInterval',
            compact_ports,
        )
        self.assertIn(
            "(row.isInput ? 1 : -1) * row.portsLayer.dynamicPortRemoveCenterInterval",
            compact_row,
        )
        self.assertIn("DYNAMIC_PORT_HANDLE_CENTER_INTERVAL", surface_metrics_source)
        self.assertIn("_DYNAMIC_PORT_HANDLE_CENTER_INTERVAL", standard_metrics_source)
        self.assertIn("DYNAMIC_PORT_HANDLE_BOTTOM_INSET = 4.0", surface_metrics_source)
        self.assertIn("_DYNAMIC_PORT_HANDLE_BOTTOM_INSET = 4.0", standard_metrics_source)
        self.assertIn("x: Number(terminusPoint.x || 0) - width * 0.5", ports_source)
        self.assertIn("y: Number(terminusPoint.y || 0) - height * 0.5", ports_source)
        self.assertIn("activeFocus", port_ui_source)
        self.assertIn("hovered", port_ui_source)
        self.assertIn(".down", port_ui_source)
        self.assertIn("lists.push(groupControl.embeddedInteractiveRects)", ports_source)
        self.assertIn("row.host.surfaceControlInteractionStarted", row_source)

    def test_dataflow_port_and_edge_authoring_controls_route_real_mutations(self) -> None:
        self._run_qml_probe(
            "dataflow-port-and-edge-authoring-controls",
            """
            from PyQt6.QtCore import QMetaObject, QObject, pyqtProperty, pyqtSlot

            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            class DataflowShellBridgeStub(QObject):
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
                    self.connect_calls.append((
                        str(node_a_id),
                        str(port_a),
                        str(node_b_id),
                        str(port_b),
                        bool(append),
                    ))
                    return True

            model = GraphModel()
            registry = build_default_registry()
            registry.register_descriptor(
                NodeTypeSpec(
                    type_id="tests.dataflow_authoring",
                    display_name="Dataflow Authoring",
                    category_path=("Tests",),
                    icon="",
                    ports=(
                        PortSpec("a", "in", "data", 'COREX.DataTypes.Any', "A", required=True),
                        PortSpec("b", "in", "data", 'COREX.DataTypes.Any', "B", required=True),
                        PortSpec("result", "out", "data", 'COREX.DataTypes.Any', "Result"),
                    ),
                    properties=(),
                ),
                lambda: None,
            )
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, model.active_workspace.workspace_id)
            shell_bridge = DataflowShellBridgeStub()

            view = ViewportBridge()
            view.set_viewport_size(980.0, 680.0)
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
            source_a_id = scene.add_node_from_type("core.constant", 30.0, 30.0)
            source_b_id = scene.add_node_from_type("core.constant", 30.0, 190.0)
            target_id = scene.add_node_from_type("tests.dataflow_authoring", 390.0, 110.0)
            edge_id = scene.add_edge(source_a_id, "as_text", target_id, "a")
            authoring_id = target_id
            gate_id = scene.add_node_from_type("core.stream_gate", 390.0, 350.0)
            flow_id = scene.add_node_from_type("passive.flowchart.process", 700.0, 360.0)
            gate_edge_id = scene.add_edge(gate_id, "output_0", target_id, "b")

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 980.0,
                    "height": 680.0,
                },
            )
            settle_events(8)
            window = attach_host_to_window(canvas, 1040, 740)
            settle_events(4)

            def host_for(node_id):
                hosts = named_child_items(canvas, "graphNodeCard")
                for host in hosts:
                    payload = variant_value(host.property("nodeData")) or {}
                    if str(payload.get("node_id", "")) == str(node_id):
                        return host
                known_ids = [
                    str((variant_value(host.property("nodeData")) or {}).get("node_id", ""))
                    for host in hosts
                ]
                raise AssertionError(f"missing host for {node_id}; known={known_ids}")

            def layer_for(node_id):
                return named_item(host_for(node_id), "graphNodePortsLayer")

            def port_payload(node_id, port_key):
                payload = variant_value(host_for(node_id).property("nodeData")) or {}
                return next(
                    dict(port)
                    for port in payload.get("ports", [])
                    if str(port.get("key", "")) == str(port_key)
                )

            def port_dot(node_id, object_name, port_key):
                return named_item(host_for(node_id), object_name, str(port_key))

            authoring_layer = layer_for(authoring_id)
            authoring_layer.setProperty("contextPortData", port_payload(authoring_id, "a"))
            assert bool(authoring_layer._togglePortModifier("graft")) is True, (
                "graft toggle failed",
                authoring_layer.property("contextNodeId"),
                variant_value(authoring_layer.property("contextPortData")),
            )
            settle_events(4)
            authoring_node = model.active_workspace.nodes[authoring_id]
            assert authoring_node.port_modifiers == {"a": ("graft",)}, authoring_node.port_modifiers

            authoring_layer = layer_for(authoring_id)
            updated_a_payload = port_payload(authoring_id, "a")
            authoring_layer.setProperty("contextPortData", updated_a_payload)
            port_menu = authoring_layer.findChild(QObject, "graphNodePortContextMenu")
            graft_action = next(
                action for action in variant_value(port_menu.property("actions"))
                if action["actionId"] == "graft"
            )
            assert graft_action["checked"] is True, (graft_action, updated_a_payload)
            label_a = port_dot(authoring_id, "graphNodeInputPortLabel", "a")
            assert "[G]" in str(label_a.property("text")), label_a.property("text")

            assert bool(authoring_layer._togglePrincipal()) is True, "principal a toggle failed"
            settle_events(4)
            authoring_layer = layer_for(authoring_id)
            authoring_layer.setProperty("contextPortData", port_payload(authoring_id, "b"))
            assert bool(authoring_layer._togglePrincipal()) is True, "principal b toggle failed"
            settle_events(4)
            assert authoring_node.principal_input_port_id == "b", authoring_node.principal_input_port_id
            label_b = port_dot(authoring_id, "graphNodeInputPortLabel", "b")
            assert "[P]" in str(label_b.property("text")), label_b.property("text")

            flow_layer = layer_for(flow_id)
            flow_layer.setProperty("contextPortData", port_payload(flow_id, "top"))
            settle_events(2)
            assert bool(flow_layer._togglePortModifier("graft")) is False
            flow_menu = flow_layer.findChild(QObject, "graphNodePortContextMenu")
            assert not any(
                action.get("visible", True)
                for action in variant_value(flow_menu.property("actions"))
            )

            gate_layer = layer_for(gate_id)
            gate_payload = variant_value(host_for(gate_id).property("nodeData")) or {}
            gate_groups = gate_payload.get("dynamic_port_groups", [])
            assert gate_groups == [{
                "id": "outputs",
                "direction": "out",
                "port_keys": ["output_0", "output_1"],
                "can_insert": True,
                "removable_port_keys": ["output_0", "output_1"],
                "rename_mode": "label",
            }], gate_groups
            inserted_id = str(gate_layer._insertDynamicPort("outputs", 1))
            assert inserted_id
            settle_events(4)
            output_ids = model.active_workspace.nodes[gate_id].properties["output_port_ids"]
            assert len(output_ids) == 3 and output_ids[0] == "output_0" and output_ids[2] == "output_1"
            assert output_ids[1] == inserted_id
            gate_layer = layer_for(gate_id)
            remove_result = variant_value(
                gate_layer._removeDynamicPort("outputs", inserted_id)
            ) or {}
            assert remove_result.get("port_key") == inserted_id, remove_result
            settle_events(4)
            assert model.active_workspace.nodes[gate_id].properties["output_port_ids"] == ["output_0", "output_1"]
            assert inserted_id not in model.active_workspace.nodes[gate_id].properties["output_port_ids"]

            gate_layer = layer_for(gate_id)
            rename_result = variant_value(
                gate_layer._renameDynamicPort("outputs", "output_0", "Primary")
            ) or {}
            assert rename_result.get("previous_port_key") == "output_0", rename_result
            assert rename_result.get("port_key") == "output_0", rename_result
            settle_events(4)
            assert model.active_workspace.nodes[gate_id].port_labels["output_0"] == "Primary"
            assert model.active_workspace.nodes[gate_id].properties["output_port_ids"] == [
                "output_0",
                "output_1",
            ]
            assert gate_edge_id in model.active_workspace.edges

            def assert_remove_target_clearance(node_id, direction, port_key):
                mouse_name = (
                    "graphNodeInputPortMouseArea"
                    if direction == "in"
                    else "graphNodeOutputPortMouseArea"
                )
                dot_name = (
                    "graphNodeInputPortDot"
                    if direction == "in"
                    else "graphNodeOutputPortDot"
                )
                connector_dot = named_item(
                    host_for(node_id),
                    dot_name,
                    port_key,
                )
                host_for(node_id).setProperty("hoveredPort", {
                    "node_id": node_id,
                    "port_key": port_key,
                    "direction": direction,
                })
                settle_events(2)
                layer = layer_for(node_id)
                remove = named_item(
                    layer,
                    f"graphNodeDynamicPortRemove_{port_key}",
                )
                port_mouse = named_item(connector_dot, mouse_name)
                assert bool(remove.property("visible")) is True, (
                    "remove action did not reveal",
                    node_id,
                    direction,
                    port_key,
                    bool(remove.property("revealActive")),
                )
                remove_center = item_scene_point(remove)
                connector_center = item_scene_point(connector_dot)
                center_gap = abs(remove_center.x() - connector_center.x())
                mouse_edge = port_mouse.mapToItem(remove,
                    QPointF(port_mouse.width() if direction == "in" else 0, 0)).x()
                clear_gap = -mouse_edge if direction == "in" else mouse_edge - remove.width()
                assert abs(center_gap - 9.0) < 0.1, center_gap
                assert 1.0 <= -clear_gap <= 3.0, clear_gap
                return remove

            gate_layer = layer_for(gate_id)
            gate_remove = assert_remove_target_clearance(
                gate_id,
                "out",
                "output_0",
            )
            gate_remove_circle = gate_remove.findChild(
                QObject,
                "graphNodeDynamicPortRemoveCircle",
            )
            assert gate_remove_circle is not None
            gate_remove_glyph = next(
                child
                for child in gate_remove_circle.findChildren(QObject)
                if str(child.property("text")) == "\u2212"
            )
            assert int(gate_remove_circle.property("width")) == 6
            assert int(gate_remove_circle.property("height")) == 6
            assert float(gate_remove_circle.property("radius")) == 3.0
            assert gate_remove_circle.property("color").name().lower() == "#ff5449"
            assert float(gate_remove_glyph.property("opacity")) == 0.0
            gate_remove_rest_x = float(gate_remove.property("x"))
            gate_remove_rest_y = float(gate_remove.property("y"))
            gate_remove.forceActiveFocus()
            settle_events(2)
            assert bool(gate_remove.property("activeFocus")) is True
            assert int(gate_remove_circle.property("width")) == 14
            assert int(gate_remove_circle.property("height")) == 14
            assert float(gate_remove_circle.property("radius")) == 7.0
            assert float(gate_remove_glyph.property("opacity")) == 1.0
            assert float(gate_remove.property("x")) == gate_remove_rest_x
            assert float(gate_remove.property("y")) == gate_remove_rest_y
            assert int(gate_remove.property("width")) == 14
            assert int(gate_remove.property("height")) == 14
            remove_rect = variant_value(gate_remove.property("interactiveRect")) or {}
            assert float(remove_rect["width"]) == 14.0
            assert float(remove_rect["height"]) == 14.0
            embedded_rects = [
                variant_value(rect)
                for rect in variant_list(gate_layer.property("embeddedInteractiveRects"))
            ]
            assert any(
                float(rect.get("width", 0)) == 14.0
                and float(rect.get("height", 0)) == 14.0
                for rect in embedded_rects
            ), embedded_rects

            target_point = item_scene_point(port_dot(target_id, "graphNodeInputPortDot", "a"))
            shift_value = int(Qt.KeyboardModifier.ShiftModifier.value)

            def preview_and_release(source_id, modifiers, release):
                source_point = item_scene_point(port_dot(source_id, "graphNodeOutputPortDot", "as_text"))
                source_scene_x = canvas.screenToSceneX(source_point.x())
                source_scene_y = canvas.screenToSceneY(source_point.y())
                canvas.beginPortWireDrag(
                    source_id,
                    "as_text",
                    "out",
                    source_scene_x,
                    source_scene_y,
                    source_point.x(),
                    source_point.y(),
                    modifiers,
                )
                canvas.updatePortWireDrag(
                    source_id,
                    "as_text",
                    "out",
                    source_scene_x,
                    source_scene_y,
                    target_point.x(),
                    target_point.y(),
                    True,
                    modifiers,
                )
                settle_events(2)
                preview = variant_value(canvas.wireDragPreviewConnection())
                assert preview is not None and bool(preview["valid_drop"]) is True, preview
                if release:
                    canvas.finishPortWireDrag(
                        source_id,
                        "as_text",
                        "out",
                        source_scene_x,
                        source_scene_y,
                        target_point.x(),
                        target_point.y(),
                        True,
                        modifiers,
                    )
                    settle_events(2)
                else:
                    canvas.cancelWireDrag()
                return preview

            replacement_preview = preview_and_release(source_b_id, 0, True)
            assert replacement_preview["connection_mode"] == "replace", replacement_preview
            assert bool(replacement_preview["replaces_existing"]) is True
            assert shell_bridge.connect_calls[-1] == (
                source_b_id,
                "as_text",
                target_id,
                "a",
                False,
            )

            append_preview = preview_and_release(source_b_id, shift_value, True)
            assert append_preview["connection_mode"] == "append", append_preview
            assert bool(append_preview["append_requested"]) is True
            assert shell_bridge.connect_calls[-1] == (
                source_b_id,
                "as_text",
                target_id,
                "a",
                True,
            )

            duplicate_preview = preview_and_release(source_a_id, 0, False)
            assert duplicate_preview["connection_mode"] == "noop", duplicate_preview
            assert bool(duplicate_preview["duplicate"]) is True

            source_dot = port_dot(source_b_id, "graphNodeOutputPortDot", "as_text")
            source_mouse = named_item(source_dot, "graphNodeOutputPortMouseArea", "as_text")
            target_dot = port_dot(target_id, "graphNodeInputPortDot", "a")
            target_mouse = named_item(target_dot, "graphNodeInputPortMouseArea", "a")
            pointer_start = item_scene_point(source_mouse)
            pointer_end = item_scene_point(target_mouse)
            pointer_mid = QPoint(
                round((pointer_start.x() + pointer_end.x()) * 0.5),
                round((pointer_start.y() + pointer_end.y()) * 0.5),
            )

            def update_pointer_drag(end, modifiers):
                canvas.updatePortWireDrag(
                    source_b_id,
                    "as_text",
                    "out",
                    canvas.screenToSceneX(pointer_start.x()),
                    canvas.screenToSceneY(pointer_start.y()),
                    end.x(),
                    end.y(),
                    True,
                    modifiers,
                )

            QTest.mouseMove(window, QPoint(960, 650))
            settle_events(2)
            rest_diameter = float(source_dot.property("width"))
            QTest.mouseMove(window, pointer_start)
            settle_events(4)
            assert float(source_dot.property("width")) > rest_diameter
            QTest.mouseMove(window, QPoint(960, 650))
            settle_events(4)
            assert float(source_dot.property("width")) == rest_diameter

            edge_layer = named_item(canvas, "graphCanvasEdgeLayer")
            scene.remove_edge(edge_id)
            settle_events(4)
            single_call_count = len(shell_bridge.connect_calls)
            QTest.mousePress(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                pointer_start,
            )
            QTest.mouseMove(window, pointer_mid)
            QTest.mouseMove(window, pointer_end)
            update_pointer_drag(pointer_end, 0)
            settle_events(3)
            single_preview = variant_value(canvas.wireDragPreviewConnection())
            assert single_preview["connection_mode"] == "connect", single_preview
            assert single_preview["replacement_edge_ids"] == []
            assert len(shell_bridge.connect_calls) == single_call_count
            QTest.mouseRelease(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                pointer_end,
            )
            settle_events(4)
            assert shell_bridge.connect_calls[-1] == (
                source_b_id,
                "as_text",
                target_id,
                "a",
                False,
            )
            assert len(shell_bridge.connect_calls) == single_call_count + 1
            edge_id = scene.add_edge(source_a_id, "as_text", target_id, "a")
            settle_events(4)

            calls_before_pointer_drag = len(shell_bridge.connect_calls)
            QTest.mousePress(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                pointer_start,
            )
            QTest.mouseMove(window, pointer_mid)
            QTest.mouseMove(window, pointer_end)
            update_pointer_drag(pointer_end, 0)
            settle_events(4)
            pointer_preview = variant_value(canvas.wireDragPreviewConnection())
            assert pointer_preview["connection_mode"] == "replace", pointer_preview
            assert pointer_preview["replaces_existing"] is True
            assert len(shell_bridge.connect_calls) == calls_before_pointer_drag
            assert variant_value(edge_layer.property("replacementPreviewEdgeIds")) == [edge_id]
            settle_events(3)
            replacement_snapshot = variant_value(edge_layer._visibleEdgeSnapshot(edge_id))
            assert replacement_snapshot["replacementPreviewed"] is True, replacement_snapshot
            assert canvas.cancelWireDrag() is True
            settle_events(3)
            assert variant_value(edge_layer.property("replacementPreviewEdgeIds")) == []
            restored_snapshot = variant_value(edge_layer._visibleEdgeSnapshot(edge_id))
            assert restored_snapshot["replacementPreviewed"] is False, restored_snapshot
            QTest.mouseRelease(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                pointer_end,
            )

            QTest.mousePress(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                pointer_start,
            )
            QTest.mouseMove(window, pointer_mid)
            QTest.mouseMove(window, pointer_end)
            update_pointer_drag(pointer_end, 0)
            settle_events(3)
            assert len(shell_bridge.connect_calls) == calls_before_pointer_drag
            QTest.mouseRelease(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                pointer_end,
            )
            settle_events(4)
            assert shell_bridge.connect_calls[-1] == (
                source_b_id,
                "as_text",
                target_id,
                "a",
                False,
            )
            assert len(shell_bridge.connect_calls) == calls_before_pointer_drag + 1

            QTest.mousePress(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.ShiftModifier,
                pointer_start,
            )
            QTest.mouseMove(window, pointer_mid)
            QTest.mouseMove(window, pointer_end)
            settle_events(3)
            update_pointer_drag(pointer_end, shift_value)
            settle_events(1)
            shift_state = variant_value(canvas.property("wireDragState"))
            assert shift_state["append_requested"] is True, shift_state
            shift_preview = variant_value(canvas.wireDragPreviewConnection())
            assert shift_preview["connection_mode"] == "append", shift_preview
            assert shift_preview["append_requested"] is True
            assert variant_value(edge_layer.property("replacementPreviewEdgeIds")) == []
            QTest.mouseRelease(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.ShiftModifier,
                pointer_end,
            )
            settle_events(4)
            assert shell_bridge.connect_calls[-1] == (
                source_b_id,
                "as_text",
                target_id,
                "a",
                True,
            )

            canvas.setProperty("selectedEdgeIds", [edge_id])
            canvas.requestEdgeRedraw()
            canvas.forceActiveFocus()
            settle_events(8)
            QTest.keyClick(window, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
            settle_events(4)
            assert model.active_workspace.edges[edge_id].enabled is False

            enable_button = named_item(canvas, "graphEdgeFloatingToolbarAction_toggle_edge_enabled")
            assert bool(enable_button.property("visible")) is True
            assert str(enable_button.property("tooltipText")) == "Enable connection"
            assert bool(enable_button.property("checked")) is False
            mouse_click(window, item_scene_point(enable_button))
            settle_events(4)
            assert model.active_workspace.edges[edge_id].enabled is True

            enable_button = named_item(canvas, "graphEdgeFloatingToolbarAction_toggle_edge_enabled")
            assert str(enable_button.property("tooltipText")) == "Disable connection"
            assert bool(enable_button.property("checked")) is True

            display_button = named_item(canvas, "graphEdgeFloatingToolbarAction_display_mode")
            assert bool(display_button.property("visible")) is True
            assert str(display_button.property("tooltipText")) == "Display mode: Default"
            mouse_click(window, item_scene_point(display_button))
            settle_events(2)
            edge_toolbar = named_item(canvas, "graphEdgeFloatingToolbar")
            display_popup = edge_toolbar.findChild(QObject, "graphEdgeDisplayModePopup")
            assert display_popup is not None
            assert bool(display_popup.property("opened")) is True
            display_content = display_popup.property("contentItem")
            default_choice = named_item(display_content, "graphEdgeDisplayModeChoice_default")
            faint_choice = named_item(display_content, "graphEdgeDisplayModeChoice_faint")
            hidden_choice = named_item(display_content, "graphEdgeDisplayModeChoice_hidden")
            assert [
                bool(default_choice.property("checked")),
                bool(faint_choice.property("checked")),
                bool(hidden_choice.property("checked")),
            ] == [True, False, False]
            mouse_click(window, item_scene_point(faint_choice))
            settle_events(4)
            assert model.active_workspace.edges[edge_id].visual_style.get("display_mode") == "faint"

            display_button = named_item(canvas, "graphEdgeFloatingToolbarAction_display_mode")
            assert str(display_button.property("tooltipText")) == "Display mode: Faint"
            mouse_click(window, item_scene_point(display_button))
            settle_events(2)
            default_choice = named_item(display_content, "graphEdgeDisplayModeChoice_default")
            faint_choice = named_item(display_content, "graphEdgeDisplayModeChoice_faint")
            assert [
                bool(default_choice.property("checked")),
                bool(faint_choice.property("checked")),
            ] == [False, True]
            mouse_click(window, item_scene_point(default_choice))
            settle_events(4)
            assert "display_mode" not in model.active_workspace.edges[edge_id].visual_style
            display_button = named_item(canvas, "graphEdgeFloatingToolbarAction_display_mode")
            assert str(display_button.property("tooltipText")) == "Display mode: Default"

            assert scene.set_edge_enabled(gate_edge_id, False) is True
            settle_events(4)
            canvas.setProperty("selectedEdgeIds", [edge_id, gate_edge_id, "stale_edge"])
            canvas.forceActiveFocus()
            settle_events(2)
            QTest.keyClick(window, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
            settle_events(4)
            assert model.active_workspace.edges[edge_id].enabled is True, "mixed toggle did not enable the selected edge"
            assert model.active_workspace.edges[gate_edge_id].enabled is True, "mixed toggle did not enable the disabled edge"

            canvas.setProperty("selectedEdgeIds", [edge_id, gate_edge_id])
            canvas.forceActiveFocus()
            QTest.keyClick(window, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
            settle_events(4)
            assert model.active_workspace.edges[edge_id].enabled is False, "all-enabled toggle did not disable the selected edge"
            assert model.active_workspace.edges[gate_edge_id].enabled is False, "all-enabled toggle did not disable the selected gate edge"

            assert scene.set_edge_enabled(edge_id, True) is True
            settle_events(4)
            canvas.setProperty("selectedEdgeIds", [edge_id, gate_edge_id])
            toggle_edge_ids = variant_value(canvas.edgeIdsForEnableToggle(edge_id))
            assert toggle_edge_ids == [edge_id, gate_edge_id], toggle_edge_ids
            toggle_payloads = [variant_value(canvas._sceneEdgePayload(toggle_id)) for toggle_id in toggle_edge_ids]
            assert canvas.edgeSelectionAllEnabled(edge_id) is False, toggle_payloads
            canvas._openEdgeContext(edge_id, 200.0, 160.0)
            settle_events(3)
            edge_popup = named_item(canvas, "graphCanvasEdgeContextPopup")
            enabled_action = next(
                variant_value(action)
                for action in variant_list(edge_popup.property("visibleActions"))
                if str(variant_value(action).get("actionId", "")) == "toggle_edge_enabled"
            )
            assert bool(enabled_action.get("checked")) is False, enabled_action
            edge_popup.actionTriggered.emit("toggle_edge_enabled")
            settle_events(4)
            assert model.active_workspace.edges[edge_id].enabled is True, "context action did not keep the clicked edge enabled"
            assert model.active_workspace.edges[gate_edge_id].enabled is True, "context action did not re-enable the mixed selected edge"


            input_mouse = port_dot(authoring_id, "graphNodeInputPortMouseArea", "a")
            authoring_layer._openPortContext(
                updated_a_payload,
                input_mouse,
                float(input_mouse.width()) * 0.5,
                float(input_mouse.height()) * 0.5,
            )
            settle_events(3)
            port_menu = authoring_layer.findChild(QObject, "graphNodePortContextMenu")
            assert port_menu is not None and bool(port_menu.property("visible")) is True
            menu_content = port_menu.property("menuContent")
            actions = variant_value(menu_content.property("visibleActions"))
            menu_bounds = tuple(port_menu.property(key) for key in ("x", "y", "width", "height"))
            assert [action["actionId"] for action in actions] == [
                "access", "graft", "flatten", "simplify", "reverse", "clean",
                "principal",
            ], actions
            assert actions[0]["enabled"] is False
            assert actions[1]["checked"] is True and actions[1]["checkable"] is True, (actions[1], updated_a_payload)
            assert int(menu_content.property("rowHeight")) == 30
            assert int(menu_content.property("contentPadding")) == 4
            assert float(menu_content.property("scale")) == 1.0
            assert float(port_menu.property("x")) >= 4, menu_bounds
            assert float(port_menu.property("y")) >= 4, menu_bounds
            assert float(port_menu.property("x")) + float(port_menu.property("width")) <= window.width() - 4, (menu_bounds, window.width())
            assert float(port_menu.property("y")) + float(port_menu.property("height")) <= window.height() - 4, (menu_bounds, window.height())
            port_menu.close()
            settle_events(2)
            assert bool(port_menu.property("visible")) is False
            dispose_host_window(canvas, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

if __name__ == "__main__":
    unittest.main()
