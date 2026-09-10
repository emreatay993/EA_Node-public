from __future__ import annotations

from pathlib import Path
import unittest
from tests.graph_surface.environment import *  # noqa: F403


class EmbeddedViewerOverlayHostBoundaryTests(unittest.TestCase):
    _REPO_ROOT = Path(__file__).resolve().parents[2]

    def test_qquickwidget_host_exposes_widget_as_overlay_parent_and_event_filter(self) -> None:
        source = (
            self._REPO_ROOT / "ea_node_editor" / "ui_qml" / "qml_host_factory.py"
        ).read_text(encoding="utf-8")
        widget_host = source[source.index("class QQuickWidgetHost:") : source.index("class QQuickViewContainerHost:")]

        self.assertIn("self.container_widget = self.widget", widget_host)
        self.assertIn("self.overlay_parent_widget = self.widget", widget_host)
        self.assertIn("self.event_filter_widget = self.widget", widget_host)

    def test_qquickview_host_routes_overlays_and_events_through_container_widget(self) -> None:
        host_source = (
            self._REPO_ROOT / "ea_node_editor" / "ui_qml" / "qml_host_factory.py"
        ).read_text(encoding="utf-8")
        shell_source = (self._REPO_ROOT / "ea_node_editor" / "ui" / "shell" / "window.py").read_text(
            encoding="utf-8"
        )
        view_host = host_source[
            host_source.index("class QQuickViewContainerHost:") : host_source.index("def create_shell_qml_host(")
        ]
        manager_factory = shell_source[
            shell_source.index("    def _ensure_embedded_viewer_overlay_manager(") : shell_source.index(
                "    def setCentralWidget("
            )
        ]

        self.assertIn("self.container_widget = QWidget.createWindowContainer(self.view, parent)", view_host)
        self.assertIn("self.overlay_parent_widget = self.container_widget", view_host)
        self.assertIn("self.event_filter_widget = self.container_widget", view_host)
        self.assertIn('overlay_parent_widget = getattr(qml_host, "overlay_parent_widget", None)', manager_factory)
        self.assertIn('event_filter_widget = getattr(qml_host, "event_filter_widget", None)', manager_factory)
        self.assertIn("overlay_parent_widget=overlay_parent_widget", manager_factory)
        self.assertIn("event_filter_widget=event_filter_widget", manager_factory)


class PassiveGraphSurfaceHostBoundaryTests(PassiveGraphSurfaceHostTestBase):
    def test_node_comment_count_pill_clears_bottom_neutral_handle(self) -> None:
        qml_text = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/graph/overlay/GraphNodeCommentPopoverLayer.qml"
        ).read_text(encoding="utf-8")

        for snippet in (
            "height: 18",
            "radius: 9",
            "width: pillRow.implicitWidth + 16",
            "spacing: 4",
            "readonly property real badgeGap: 6",
            "readonly property real bottomNeutralPortClearance: 12",
            "readonly property real groupWidth: hasLinkBadge ? linkBadgeWidth + root.badgeGap + ownBadgeWidth : ownBadgeWidth",
            "GraphNodeSurfaceMetrics.nodeHasBottomNeutralFlowHandle(modelData)",
            "? groupWidth * 0.5 + root.bottomNeutralPortClearance : 0",
            "root.nodeX(modelData) + (root.nodeWidth(modelData) - groupWidth) / 2",
            "root.nodeY(modelData) + root.nodeHeight(modelData) - height / 2",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, qml_text)

    def test_graph_node_host_routes_theme_and_layout_derivations_through_split_helpers(self) -> None:
        host_text = (_REPO_ROOT / "ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml").read_text(encoding="utf-8")
        theme_text = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/graph/GraphNodeHostTheme.qml"
        ).read_text(encoding="utf-8")
        layout_text = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/graph/GraphNodeHostLayout.qml"
        ).read_text(encoding="utf-8")
        render_quality_text = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/graph/GraphNodeHostRenderQuality.qml"
        ).read_text(encoding="utf-8")
        scene_access_text = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/graph/GraphNodeHostSceneAccess.qml"
        ).read_text(encoding="utf-8")
        interaction_text = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/graph/GraphNodeHostInteractionState.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("GraphNodeHostTheme {", host_text)
        self.assertIn("GraphNodeHostLayout {", host_text)
        self.assertIn("GraphNodeHostRenderQuality {", host_text)
        self.assertIn("GraphNodeHostSceneAccess {", host_text)
        self.assertIn("GraphNodeHostInteractionState {", host_text)
        self.assertIn("readonly property color surfaceColor: themeState.surfaceColor", host_text)
        self.assertIn("readonly property bool _useHostChrome: chromeLayout.useHostChrome", host_text)
        self.assertIn("readonly property var renderQuality: renderQualityState.renderQuality", host_text)
        self.assertIn("return sceneAccess.localPortPoint(direction, rowIndex);", host_text)
        self.assertIn(
            "return sceneAccess.localPortPointForPort(direction, rowIndex, portData);",
            host_text,
        )
        self.assertIn("return interactionState.requestInlineTitleEditAt(localX, localY);", host_text)
        self.assertIn("readonly property color surfaceColor:", theme_text)
        self.assertIn("readonly property bool useHostChrome:", layout_text)
        self.assertIn("readonly property string chromeShadowCacheKey:", layout_text)
        self.assertIn('readonly property string resolvedQualityTier:', render_quality_text)
        self.assertIn("function localPortPoint(direction, rowIndex) {", scene_access_text)
        self.assertIn(
            "function localPortPointForPort(direction, rowIndex, portData) {",
            scene_access_text,
        )
        self.assertIn("readonly property bool inlineEditingActive:", interaction_text)
        self.assertIn("function pointInEmbeddedInteractiveRect(localX, localY) {", interaction_text)

    def test_active_graph_node_host_has_no_resize_targets_and_ports_remain_clickable(self) -> None:
        self._run_qml_probe(
            "active-host-no-resize-targets",
            """
            payload = node_payload()
            payload["ports"] = [
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
                    "allow_multiple_connections": False,
                },
                {
                    "key": "summary",
                    "label": "Summary",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                },
                {
                    "key": "result",
                    "label": "Result",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                    "allow_multiple_connections": False,
                },
            ]
            payload["inline_properties"] = [
                {
                    "key": "message",
                    "label": "Message",
                    "inline_editor": "text",
                    "value": "log message",
                    "overridden_by_input": False,
                    "input_port_label": "message",
                }
            ]

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            handles = named_child_items(host, "graphNodeResizeHandle")
            assert len(handles) == 4
            input_mouse = named_item(host, "graphNodeInputPortMouseArea", "message")
            output_mouse = max(
                named_child_items(host, "graphNodeOutputPortMouseArea"),
                key=lambda item: item.mapToScene(QPointF(item.width() * 0.5, item.height() * 0.5)).y(),
            )

            window = attach_host_to_window(host, 520, 320)
            hover_host_local_point(window, host, host.width() * 0.5, host.height() * 0.5)

            assert all(bool(handle.property("visible")) is False for handle in handles)

            input_center_in_host = input_mouse.mapToItem(
                host,
                QPointF(input_mouse.width() * 0.5, input_mouse.height() * 0.5),
            )
            output_center_in_host = output_mouse.mapToItem(
                host,
                QPointF(output_mouse.width() * 0.5, output_mouse.height() * 0.5),
            )

            assert host._isResizeHandlePoint(float(input_center_in_host.x()), float(input_center_in_host.y())) is False
            assert host._isResizeHandlePoint(float(output_center_in_host.x()), float(output_center_in_host.y())) is False
            assert host._isResizeHandlePoint(1.0, float(host.height()) - 1.0) is False
            assert host._isResizeHandlePoint(float(host.width()) - 1.0, float(host.height()) - 1.0) is False

            clicked_ports = []
            preview_events = []
            host.portClicked.connect(
                lambda node_id, port_key, direction, scene_x, scene_y, modifiers: clicked_ports.append((port_key, direction))
            )
            host.resizePreviewChanged.connect(
                lambda node_id, x, y, width, height, active: preview_events.append(active)
            )

            mouse_click(window, item_scene_point(input_mouse))
            mouse_click(window, item_scene_point(output_mouse))

            assert ("message", "in") in clicked_ports
            assert ("result", "out") in clicked_ports
            assert preview_events == []
            """,
        )

    def test_node_card_wrapper_uses_projected_surface_contract(self) -> None:
        self._run_qml_probe(
            "node-card-wrapper",
            """
            payload = node_payload(surface_family="annotation", surface_variant="sticky_note")
            payload["type_id"] = "passive.annotation.sticky_note"
            payload["runtime_behavior"] = "passive"
            payload["properties"] = {"body": "Sticky note"}
            payload["surface_spec"] = surface_spec_payload_for_values(
                type_id="passive.annotation.sticky_note",
                family="annotation",
                variant="sticky_note",
            )
            node_card = create_component(
                node_card_qml_path,
                {"nodeData": payload},
            )
            assert node_card.objectName() == "graphNodeCard"
            assert node_card.property("surfaceFamily") == "annotation"
            assert node_card.property("surfaceVariant") == "sticky_note"
            assert node_card.findChild(QObject, "graphNodeSurfaceLoader") is not None
            assert node_card.findChild(QObject, "graphNodeAnnotationSurface") is not None
            """,
        )

    def test_graph_canvas_keeps_graph_node_card_discoverability_through_host_delegate(self) -> None:
        self._run_qml_probe(
            "graph-canvas-host",
            """
            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            scene.add_node_from_type("core.logger", 120.0, 140.0)

            view = ViewportBridge()
            view.set_viewport_size(1280.0, 720.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 1280.0,
                    "height": 720.0,
                },
            )
            node_cards = named_child_items(canvas, "graphNodeCard")
            assert len(node_cards) >= 1
            assert node_cards[0].findChild(QObject, "graphNodeStandardSurface") is not None
            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )

class GraphSurfaceBoundaryContractTests(GraphSurfaceInputContractTestBase):
    def test_passive_graph_surface_host_entrypoint_stays_packetized(self) -> None:
        entrypoint_path = _REPO_ROOT / "tests" / "test_passive_graph_surface_host.py"
        entrypoint_text = entrypoint_path.read_text(encoding="utf-8")

        self.assertIn("from tests.graph_surface import (", entrypoint_text)
        self.assertIn("PassiveGraphSurfaceHostBoundaryTests", entrypoint_text)
        self.assertIn("PassiveGraphSurfaceHostTests", entrypoint_text)
        self.assertIn("PassiveGraphSurfaceInlineEditorTests", entrypoint_text)
        self.assertIn("PassiveGraphSurfaceMediaAndScopeTests", entrypoint_text)
        self.assertNotIn("def _run_qml_probe(", entrypoint_text)

    def test_graph_surface_input_contract_entrypoint_stays_packetized(self) -> None:
        entrypoint_path = _REPO_ROOT / "tests" / "test_graph_surface_input_contract.py"
        entrypoint_text = entrypoint_path.read_text(encoding="utf-8")

        self.assertIn("from tests.graph_surface import (", entrypoint_text)
        self.assertIn("GraphSurfaceBoundaryContractTests", entrypoint_text)
        self.assertIn("GraphSurfaceInputContractTests", entrypoint_text)
        self.assertIn("GraphSurfaceInlineEditorContractTests", entrypoint_text)
        self.assertIn("GraphSurfaceMediaAndScopeContractTests", entrypoint_text)
        self.assertNotIn("def _run_qml_probe(", entrypoint_text)

    def test_graph_canvas_root_packetization_keeps_helper_split_and_stable_public_contract(self) -> None:
        graph_canvas_path = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "GraphCanvas.qml"
        root_layers_path = graph_canvas_path.parent / "graph_canvas" / "GraphCanvasRootLayers.qml"
        root_api_path = graph_canvas_path.parent / "graph_canvas" / "GraphCanvasRootApi.js"

        graph_canvas_text = graph_canvas_path.read_text(encoding="utf-8")
        root_layers_text = root_layers_path.read_text(encoding="utf-8")
        root_api_text = root_api_path.read_text(encoding="utf-8")

        self.assertTrue(root_layers_path.exists())
        self.assertTrue(root_api_path.exists())

        for snippet in (
            'import "graph_canvas/GraphCanvasRootApi.js" as GraphCanvasRootApi',
            "GraphCanvasComponents.GraphCanvasRootLayers {",
            "function toggleMinimapExpanded() {",
            "function clearLibraryDropPreview() {",
            "function updateLibraryDropPreview(screenX, screenY, payload) {",
            "function isPointInCanvas(screenX, screenY) {",
            "function performLibraryDrop(screenX, screenY, payload) {",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, graph_canvas_text)

        for snippet in (
            "GraphCanvasBackground {",
            "GraphComponents.EdgeLayer {",
            "GraphCanvasMinimapOverlay {",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, root_layers_text)

        for snippet in (
            "function invoke(target, methodName, args, fallbackValue) {",
            "function snapToGridValue(canvasStateBridge, value) {",
            "function clampMenuPosition(canvasItem, x, y, menuWidth, menuHeight) {",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, root_api_text)

    def test_graph_scene_payload_builder_publishes_normalized_render_quality_metadata(self) -> None:
        registry: NodeRegistry = build_default_registry()
        spec = NodeTypeSpec(
            type_id="tests.render_quality_payload",
            display_name="Render Quality Payload",
            category_path=("Tests",),
            icon="",
            ports=(),
            properties=(),
            render_quality={
                "supported_quality_tiers": ["full", "proxy"],
            },  # type: ignore[arg-type]
        )
        registry.register(lambda: _RenderQualityPayloadPlugin(spec))

        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        model.add_node(
            workspace_id,
            spec.type_id,
            spec.display_name,
            80.0,
            120.0,
        )

        builder = GraphScenePayloadBuilder()
        nodes_payload, _minimap_payload, _edges_payload = builder.rebuild_models(
            model=model,
            registry=registry,
            workspace_id=workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )

        payload = next(item for item in nodes_payload if item["type_id"] == spec.type_id)
        self.assertEqual(
            payload["render_quality"],
            {
                "supported_quality_tiers": ["full", "proxy"],
            },
        )

    def test_graph_scene_payload_builder_preserves_declared_data_port_order(self) -> None:
        registry: NodeRegistry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        model.add_node(
            workspace_id,
            "io.excel_read",
            "Excel Read",
            80.0,
            120.0,
        )
        model.add_node(
            workspace_id,
            "io.excel_write",
            "Excel Write",
            280.0,
            120.0,
        )

        builder = GraphScenePayloadBuilder()
        nodes_payload, _minimap_payload, _edges_payload = builder.rebuild_models(
            model=model,
            registry=registry,
            workspace_id=workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )

        payloads_by_type = {str(item["type_id"]): item for item in nodes_payload}

        excel_read_ports = payloads_by_type["io.excel_read"]["ports"]
        excel_read_output_keys = [
            str(port["key"])
            for port in excel_read_ports
            if str(port["direction"]) == "out"
        ]
        self.assertEqual(excel_read_output_keys, ["rows"])

        excel_write_ports = payloads_by_type["io.excel_write"]["ports"]
        excel_write_input_keys = [
            str(port["key"])
            for port in excel_write_ports
            if str(port["direction"]) == "in"
        ]
        excel_write_output_keys = [
            str(port["key"])
            for port in excel_write_ports
            if str(port["direction"]) == "out"
        ]
        self.assertEqual(excel_write_input_keys, ["rows", "path"])
        self.assertEqual(excel_write_output_keys, ["written_path"])
        excel_write_ports_by_key = {str(port["key"]): port for port in excel_write_ports}
        self.assertEqual(
            excel_write_ports_by_key["path"]["default_property"]["key"],
            "path",
        )
        self.assertNotIn("locked", excel_write_ports_by_key["path"])
        self.assertNotIn("lockable", excel_write_ports_by_key["path"])

    def test_graph_scene_payload_builder_projects_defaults_and_applies_optional_port_filter(self) -> None:
        registry: NodeRegistry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        workspace = model.project.workspaces[workspace_id]
        logger = model.validated_mutations(workspace_id, registry).add_node(
            type_id="core.logger",
            title="Logger",
            x=80.0,
            y=120.0,
        )

        builder = GraphScenePayloadBuilder()

        def _logger_ports() -> list[dict[str, object]]:
            nodes_payload, _minimap_payload, _edges_payload = builder.rebuild_models(
                model=model,
                registry=registry,
                workspace_id=workspace_id,
                scope_path=(),
                graph_theme_bridge=None,
            )
            payload = next(item for item in nodes_payload if item["node_id"] == logger.node_id)
            return payload["ports"]

        ports_by_key = {str(port["key"]): port for port in _logger_ports()}
        self.assertEqual(ports_by_key["message"]["flow_state"], "default")
        self.assertEqual(ports_by_key["message"]["default_property"]["key"], "message")
        self.assertFalse(ports_by_key["message"]["default_property"]["overridden_by_input"])
        self.assertNotIn("locked", ports_by_key["message"])
        self.assertNotIn("lockable", ports_by_key["message"])
        self.assertTrue(bool(ports_by_key["message"]["optional"]))

        active_view = workspace.views[workspace.active_view_id]
        active_view.hide_optional_ports = True
        hidden_optional_keys = [str(port["key"]) for port in _logger_ports()]
        self.assertEqual(hidden_optional_keys, [])

    def test_graph_scene_bridge_exposes_set_node_property_as_qml_slot(self) -> None:
        from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

        bridge = GraphSceneBridge()
        meta_object = bridge.metaObject()
        for signature in (
            b"set_node_property(QString,QString,QVariant)",
            b"set_hide_optional_ports(bool)",
        ):
            with self.subTest(signature=signature):
                self.assertGreaterEqual(meta_object.indexOfMethod(signature), 0)
        for retired_signature in (
            b"set_port_locked(QString,QString,bool)",
            b"set_hide_locked_ports(bool)",
        ):
            with self.subTest(retired_signature=retired_signature):
                self.assertLess(meta_object.indexOfMethod(retired_signature), 0)
