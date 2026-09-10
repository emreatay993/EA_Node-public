from __future__ import annotations

import unittest
from pathlib import Path

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.node_specs import (
    NodeRenderQualitySpec,
    NodeTypeSpec,
    PortSpec,
    SettingsGroupItemSpec,
    SettingsGroupSpec,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    GRAPH_DATA_TYPE_ID,
    VIEWER_SESSION_DATA_TYPE_ID,
)
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from ea_node_editor.ui_qml.graph_surface_metrics import (
    node_surface_metrics,
    viewer_surface_contract_payload,
)
from tests.graph_surface_pointer_regression import (
    QML_POINTER_REGRESSION_HELPERS,
    run_qml_probe,
)


class _ViewerSurfacePlugin:
    def __init__(self, spec: NodeTypeSpec) -> None:
        self._spec = spec

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult()


def _viewer_surface_spec() -> NodeTypeSpec:
    return NodeTypeSpec(
        type_id="tests.viewer_surface_contract",
        display_name="Viewer Contract",
        category_path=("Tests",),
        icon="",
        ports=(
            PortSpec("fields", "in", "data", GRAPH_DATA_TYPE_ID, required=False),
            PortSpec("session", "out", "data", VIEWER_SESSION_DATA_TYPE_ID),
        ),
        properties=(),
        surface_family="viewer",
        render_quality=NodeRenderQualitySpec(
            supported_quality_tiers=("full", "proxy"),
        ),
    )


class ViewerSurfaceContractTests(unittest.TestCase):
    def test_graph_viewer_surface_facade_uses_body_surface(self) -> None:
        viewer_dir = Path(__file__).resolve().parents[1] / "ea_node_editor" / "ui_qml" / "components" / "graph" / "viewer"
        facade_path = viewer_dir / "GraphViewerSurface.qml"
        body_path = viewer_dir / "GraphViewerSurfaceBody.qml"
        legacy_content_path = viewer_dir / "GraphViewerSurfaceContent.qml"
        facade_text = facade_path.read_text(encoding="utf-8")

        self.assertFalse(legacy_content_path.exists())
        self.assertTrue(body_path.exists())
        self.assertIn("GraphViewerSurfaceBody.qml", facade_text)
        self.assertIn("dispatchSurfaceAction", facade_text)
        self.assertIn("surfaceActions", facade_text)
        self.assertNotIn("triggerHoverAction", facade_text)


    def test_graph_surface_metrics_facade_uses_helper_split(self) -> None:
        ui_qml_dir = Path(__file__).resolve().parents[1] / "ea_node_editor" / "ui_qml"
        graph_geometry_dir = ui_qml_dir / "graph_geometry"
        facade_path = ui_qml_dir / "graph_surface_metrics.py"
        facade_text = facade_path.read_text(encoding="utf-8")
        helper_paths = {
            "anchors.py": graph_geometry_dir / "anchors.py",
            "flowchart_metrics.py": graph_geometry_dir / "flowchart_metrics.py",
            "panel_metrics.py": graph_geometry_dir / "panel_metrics.py",
            "standard_metrics.py": graph_geometry_dir / "standard_metrics.py",
            "surface_contract.py": graph_geometry_dir / "surface_contract.py",
            "viewer_metrics.py": graph_geometry_dir / "viewer_metrics.py",
        }

        for snippet in (
            "graph_geometry.anchors",
            "graph_geometry.flowchart_metrics",
            "graph_geometry.panel_metrics",
            "graph_geometry.standard_metrics",
            "graph_geometry.surface_contract",
            "graph_geometry.viewer_metrics",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, facade_text)

        for helper_name, helper_path in helper_paths.items():
            with self.subTest(helper=helper_name):
                self.assertTrue(helper_path.exists(), msg=f"missing helper {helper_name}")

    def _run_qml_probe(self, label: str, body: str) -> None:
        run_qml_probe(
            self,
            label,
            """
            from pathlib import Path

            from PyQt6.QtCore import QObject, QUrl, pyqtProperty
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            from ea_node_editor.ui.icon_registry import (
                UI_ICON_PROVIDER_ID,
                UiIconImageProvider,
                UiIconRegistryBridge,
            )
            from ea_node_editor.ui.media_preview_provider import (
                LOCAL_MEDIA_PREVIEW_PROVIDER_ID,
                LocalMediaPreviewImageProvider,
            )
            from ea_node_editor.ui_qml.surface_contracts import surface_spec_payload_for_values

            class ThemeBridgeStub(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def palette(self):
                    return {
                        "accent": "#2F89FF",
                        "border": "#3a4355",
                        "canvas_bg": "#151821",
                        "canvas_major_grid": "#2f3644",
                        "canvas_minor_grid": "#222833",
                        "group_title_fg": "#d5dbea",
                        "hover": "#33405c",
                        "muted_fg": "#95a0b8",
                        "panel_bg": "#1b1f2a",
                        "panel_title_fg": "#eef3ff",
                        "pressed": "#22304a",
                        "toolbar_bg": "#202635",
                    }

            class GraphThemeBridgeStub(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def node_palette(self):
                    return {
                        "card_bg": "#1f2431",
                        "card_border": "#414a5d",
                        "card_selected_border": "#5da9ff",
                        "header_bg": "#252c3c",
                        "header_fg": "#eef3ff",
                        "inline_driven_fg": "#aeb8ce",
                        "inline_input_bg": "#18202d",
                        "inline_input_border": "#465066",
                        "inline_input_fg": "#eef3ff",
                        "inline_label_fg": "#d5dbea",
                        "inline_row_bg": "#202635",
                        "inline_row_border": "#3a4355",
                        "port_interactive_border": "#8ca0c7",
                        "port_interactive_fill": "#101521",
                        "port_interactive_ring_border": "#7fb2ff",
                        "port_interactive_ring_fill": "#1a2233",
                        "port_label_fg": "#d5dbea",
                        "scope_badge_bg": "#1f3657",
                        "scope_badge_border": "#4c7bc0",
                        "scope_badge_fg": "#eef3ff",
                    }

                @pyqtProperty("QVariantMap", constant=True)
                def port_kind_palette(self):
                    return {
                        "data": "#7AA8FF",
                        "flow": "#67D487",
                    }

                @pyqtProperty("QVariantMap", constant=True)
                def edge_palette(self):
                    return {
                        "invalid_drag_stroke": "#D94F4F",
                        "preview_stroke": "#95a0b8",
                        "selected_stroke": "#5da9ff",
                        "valid_drag_stroke": "#67D487",
                    }

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            engine.addImageProvider(UI_ICON_PROVIDER_ID, UiIconImageProvider())
            engine.addImageProvider(LOCAL_MEDIA_PREVIEW_PROVIDER_ID, LocalMediaPreviewImageProvider())
            engine.rootContext().setContextProperty("uiIcons", UiIconRegistryBridge())
            engine.rootContext().setContextProperty("themeBridge", ThemeBridgeStub())
            engine.rootContext().setContextProperty("graphThemeBridge", GraphThemeBridgeStub())

            repo_root = Path.cwd()
            graph_node_host_qml_path = repo_root / "ea_node_editor" / "ui_qml" / "components" / "graph" / "GraphNodeHost.qml"

            def create_component(path, initial_properties):
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
                app.processEvents()
                return obj

            def viewer_payload():
                return {
                    "node_id": "node_viewer_surface_contract",
                    "type_id": "tests.viewer_surface_contract",
                    "title": "Viewer Contract",
                    "x": 120.0,
                    "y": 90.0,
                    "width": 296.0,
                    "height": 236.0,
                    "accent": "#2F89FF",
                    "collapsed": False,
                    "selected": False,
                    "runtime_behavior": "active",
                    "surface_family": "viewer",
                    "surface_variant": "",
                    "surface_spec": surface_spec_payload_for_values(
                        type_id="tests.viewer_surface_contract",
                        family="viewer",
                        variant="",
                    ),
                    "render_quality": {
                        "supported_quality_tiers": ["full", "proxy"],
                    },
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
                        "title_top": 4.0,
                        "title_height": 24.0,
                        "title_left_margin": 10.0,
                        "title_right_margin": 42.0,
                        "title_centered": False,
                        "body_left_margin": 14.0,
                        "body_right_margin": 14.0,
                        "body_bottom_margin": 12.0,
                        "use_host_chrome": True,
                        "standard_title_full_width": 0.0,
                        "standard_left_label_width": 0.0,
                        "standard_right_label_width": 0.0,
                        "standard_port_gutter": 21.5,
                        "standard_center_gap": 24.0,
                        "standard_port_label_min_width": 0.0,
                    },
                    "viewer_surface": {
                        "body_rect": {"x": 14.0, "y": 30.0, "width": 312.0, "height": 176.0},
                        "proxy_rect": {"x": 14.0, "y": 30.0, "width": 312.0, "height": 176.0},
                        "live_rect": {"x": 14.0, "y": 30.0, "width": 312.0, "height": 176.0},
                        "overlay_target": "body",
                        "proxy_surface_supported": True,
                        "live_surface_supported": True,
                    },
                    "visual_style": {},
                    "can_enter_scope": False,
                    "ports": [
                        {
                            "key": "fields",
                            "label": "Fields",
                            "direction": "in",
                            "kind": "data",
                            "data_type": "COREX.Engineering.Scene",
                            "connected": False,
                        },
                        {
                            "key": "session",
                            "label": "Session",
                            "direction": "out",
                            "kind": "data",
                            "data_type": "viewer_session",
                            "connected": False,
                        },
                    ],
                    "inline_properties": [],
                }
            """,
            QML_POINTER_REGRESSION_HELPERS,
            body,
        )

    def test_registry_accepts_viewer_surface_family(self) -> None:
        registry = NodeRegistry()
        spec = _viewer_surface_spec()

        registry.register(lambda: _ViewerSurfacePlugin(spec))

        self.assertEqual(registry.get_spec(spec.type_id).surface_family, "viewer")

    def test_model_viewer_dynamic_port_controls_and_geometry_match_python(self) -> None:
        self._run_qml_probe(
            "model-viewer-dynamic-ports",
            """
            from PyQt6.QtCore import pyqtSlot
            from ea_node_editor.graph.model import GraphModel
            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, model.active_workspace.workspace_id)
            node_id = scene.add_node_from_type("model.viewer", 50.0, 40.0)
            node = model.active_workspace.nodes[node_id]

            class CanvasStub(QQuickItem):
                @pyqtProperty(QObject, constant=True)
                def sceneCommandBridge(self):
                    return scene.command_bridge

                @pyqtProperty(QObject, constant=True)
                def sceneBridge(self):
                    return scene

            canvas = CanvasStub()

            def payload():
                return next(item for item in scene.nodes_model if item["node_id"] == node_id)

            host = create_component(graph_node_host_qml_path, {"nodeData": payload(), "canvasItem": canvas})
            scene.nodes_changed.connect(lambda: host.setProperty("nodeData", payload()))
            window = attach_host_to_window(host, 650, 600)
            settle_events(5)

            def assert_metrics():
                projected = variant_value(host.property("nodeData"))["surface_metrics"]
                rendered = variant_value(host.property("surfaceMetrics"))
                for key in ("default_height", "min_height", "body_height", "port_top", "body_bottom_margin"):
                    assert abs(float(projected[key]) - float(rendered[key])) < 0.1, (key, projected, rendered)
                terminal_key = variant_value(host.property("nodeData"))["dynamic_port_groups"][0]["port_keys"][-1]
                host.setProperty("hoveredPort", {
                    "node_id": node_id,
                    "port_key": terminal_key,
                    "direction": "in",
                })
                settle_events(2)
                button = named_item(host, "graphNodeDynamicPortAdd_scenes")
                assert button is not None and button.property("visible")
                circle = named_item(button, "graphNodeDynamicPortAddCircle")
                bottom = circle.mapToItem(host, QPointF(0, circle.height())).y()
                assert bottom <= host.height() + 2.0, (bottom, host.height())
                return button

            assert node.properties["scene_input_ids"] == ["scene_1"]
            for count in (2, 3, 4):
                button = assert_metrics()
                mouse_click(window, item_scene_point(button))
                settle_events(5)
                assert len(node.properties["scene_input_ids"]) == count, node.properties
            assert_metrics()
            scene_ids = list(node.properties["scene_input_ids"])
            layer = named_item(host, "graphNodePortsLayer")
            renamed = variant_value(layer._renameDynamicPort("scenes", scene_ids[1], "Housing"))
            settle_events(5)
            assert renamed["port_key"] == scene_ids[1]
            assert node.port_labels[scene_ids[1]] == "Housing"
            remove = named_item(host, "graphNodeDynamicPortRemove_" + scene_ids[1])
            mouse_click(window, item_scene_point(remove))
            settle_events(5)
            assert node.properties["scene_input_ids"] == [scene_ids[0], *scene_ids[2:]]
            assert_metrics()
            dispose_host_window(host, window)
            """,
        )

    def test_scene_sidebar_selects_styles_queries_and_visibility_by_id(self) -> None:
        self._run_qml_probe(
            "model-viewer-scene-sidebar",
            """
            from PyQt6.QtCore import QMetaObject, Q_ARG, pyqtSignal, pyqtSlot

            class ControlStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.styles = []
                    self.queries = []

                @pyqtSlot(str, str, str, "QVariant", result=bool)
                def set_scene_style(self, node, scene, key, value):
                    self.styles.append((node, scene, key, value))
                    return True

                @pyqtSlot(str, str, "QVariantMap", result="QVariantMap")
                def query_viewer(self, node, query, payload):
                    self.queries.append((node, query, payload))
                    return {"supported": True, "value": {}}

            class HostStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.visibility = []
                    self.isolated = []

                @pyqtSlot(str, result="QVariantMap")
                def viewer_render_stats(self, node):
                    return {"layers": [{"id": "scene_1", "name": "Same", "visible": True},
                                       {"id": "scene_2", "name": "Same", "visible": False}]}

                @pyqtSlot(str, str, bool, result=bool)
                def set_viewer_layer_visibility(self, node, scene, visible):
                    self.visibility.append((node, scene, visible))
                    return True

                @pyqtSlot(str, str, result=bool)
                def isolate_viewer_layer(self, node, scene):
                    self.isolated.append((node, scene))
                    return True

            bridge = ControlStub()
            host_service = HostStub()
            layers = [
                {"id": "scene_1", "name": "Same", "result_name": "CAD", "capabilities": {"measure": True}},
                {"id": "scene_2", "name": "Same", "result_name": "Stress", "unit": "MPa", "capabilities": {"measure": False}},
                {"id": "scene_3", "name": "Last", "result_name": "Displacement", "unit": "mm"},
            ]
            panel = create_component(repo_root / "ea_node_editor/ui_qml/components/graph/viewer/ViewerSidePanel.qml", {
                "nodeId": "viewer", "bridgeRef": bridge, "hostServiceRef": host_service, "panelCollapsed": False,
                "sessionState": {"summary": {"viewer_kind": "engineering_scene", "scene_layers": layers,
                    "capabilities": {"scene_layers": True, "model_tree": True, "live_query_transport": True}},
                    "options": {"scene_styles": {"scene_2": {"opacity": 0.4, "color": "#123456"}}}},
                "width": 288, "height": 900,
            })
            selector = panel.findChild(QObject, "viewerSidePanelSceneSelector")
            assert selector is not None
            assert int(selector.property("count")) == 3
            selector.activated.emit(1)
            settle_events(3)
            assert panel.property("selectedSceneId") == "scene_2"
            assert panel.property("supportsMeasurements") is False
            opacity = panel.findChild(QObject, "viewerSidePanelSceneOpacityField")
            color = panel.findChild(QObject, "viewerSidePanelSceneColorField")
            assert opacity.property("text") == "0.4"
            assert color.property("text") == "#123456"
            assert panel.findChild(QObject, "viewerSidePanelResultValue").property("text") == "Stress"
            opacity.setProperty("text", "0.25")
            opacity.editingFinished.emit()
            color.setProperty("text", "#abcdef")
            color.editingFinished.emit()
            auto = panel.findChild(QObject, "viewerSidePanelSceneColorAutoButton")
            auto.clicked.emit()
            panel.runEngineeringQuery("bounds")
            assert bridge.styles == [("viewer", "scene_2", "opacity", "0.25"),
                ("viewer", "scene_2", "color", "#abcdef"), ("viewer", "scene_2", "color", "")], bridge.styles
            assert bridge.queries == [("viewer", "bounds", {"layer_id": "scene_2"})], bridge.queries
            scene_row = next(item for item in walk_items(panel) if item.property("layerId") == "scene_2")
            show = next(item for item in walk_items(scene_row) if item.property("text") == "Show")
            show.clicked.emit()
            isolate = next(item for item in walk_items(scene_row) if item.property("text") == "Iso")
            isolate.clicked.emit()
            assert host_service.visibility == [("viewer", "scene_2", True)], host_service.visibility
            assert host_service.isolated == [("viewer", "scene_2")], host_service.isolated
            panel.deleteLater()
            settle_events(2)
            """,
        )

    def test_viewer_surface_metrics_publish_reserved_body_contract(self) -> None:
        spec = _viewer_surface_spec()
        node = NodeInstance(
            node_id="node_viewer_surface_contract",
            type_id=spec.type_id,
            title="Viewer Contract",
            x=24.0,
            y=18.0,
        )

        metrics = node_surface_metrics(node, spec, {node.node_id: node})
        contract = viewer_surface_contract_payload(
            width=metrics.default_width,
            height=metrics.default_height,
            surface_metrics=metrics,
        )

        self.assertEqual(metrics.default_width, 340.0)
        self.assertEqual(metrics.default_height, 236.0)
        self.assertEqual(metrics.min_width, 320.0)
        self.assertEqual(metrics.min_height, 208.0)
        self.assertEqual(metrics.body_top, 30.0)
        self.assertEqual(metrics.body_height, 176.0)
        self.assertEqual(metrics.port_top, 206.0)
        self.assertEqual(metrics.title_right_margin, 42.0)
        self.assertNotIn("show_header_background", metrics.to_payload())
        self.assertNotIn("show_accent_bar", metrics.to_payload())
        self.assertTrue(metrics.use_host_chrome)
        self.assertEqual(
            contract,
            {
                "body_rect": {"x": 14.0, "y": 30.0, "width": 312.0, "height": 176.0},
                "proxy_rect": {"x": 14.0, "y": 30.0, "width": 312.0, "height": 176.0},
                "live_rect": {"x": 14.0, "y": 30.0, "width": 312.0, "height": 176.0},
                "overlay_target": "body",
                "proxy_surface_supported": True,
                "live_surface_supported": True,
            },
        )

    def test_surface_metrics_payload_publishes_floating_toolbar_block(self) -> None:
        spec = _viewer_surface_spec()
        node = NodeInstance(
            node_id="node_viewer_surface_contract",
            type_id=spec.type_id,
            title="Viewer Contract",
            x=24.0,
            y=18.0,
        )

        metrics = node_surface_metrics(node, spec, {node.node_id: node})
        payload = metrics.to_payload()

        self.assertIn("floating_toolbar", payload)
        toolbar = payload["floating_toolbar"]
        self.assertIsInstance(toolbar, dict)
        for key in (
            "toolbar_height",
            "button_size",
            "button_gap",
            "internal_padding",
            "gap_from_node",
            "safety_margin",
        ):
            with self.subTest(key=key):
                self.assertIn(key, toolbar)
                self.assertGreater(float(toolbar[key]), 0.0)
        self.assertEqual(float(toolbar["toolbar_height"]), 32.0)
        self.assertEqual(float(toolbar["button_size"]), 24.0)
        self.assertEqual(float(toolbar["button_gap"]), 4.0)
        self.assertEqual(float(toolbar["internal_padding"]), 4.0)
        self.assertEqual(float(toolbar["gap_from_node"]), 6.0)
        self.assertEqual(float(toolbar["safety_margin"]), 8.0)

    def test_graph_scene_payload_builder_publishes_viewer_surface_payload(self) -> None:
        registry = NodeRegistry()
        spec = _viewer_surface_spec()
        registry.register(lambda: _ViewerSurfacePlugin(spec))

        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        model.add_node(
            workspace_id,
            spec.type_id,
            spec.display_name,
            64.0,
            96.0,
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
        self.assertEqual(payload["surface_family"], "viewer")
        self.assertEqual(payload["surface_spec"]["component_key"], "viewer")
        self.assertEqual(payload["surface_spec"]["qml_component"], "viewer/GraphViewerSurface.qml")
        self.assertEqual(payload["surface_spec"]["fullscreen"]["content_kind"], "viewer")
        self.assertTrue(payload["surface_spec"]["native_overlay"]["required"])
        self.assertIn("stylus", payload["surface_spec"]["input_capabilities"]["devices"])
        self.assertEqual(payload["surface_metrics"]["default_height"], 236.0)
        self.assertEqual(payload["viewer_surface"]["overlay_target"], "body")
        self.assertEqual(payload["viewer_surface"]["live_rect"]["x"], 14.0)
        self.assertEqual(payload["viewer_surface"]["live_rect"]["y"], 30.0)
        self.assertGreater(payload["viewer_surface"]["live_rect"]["width"], 0.0)
        self.assertGreater(payload["viewer_surface"]["live_rect"]["height"], 0.0)
        self.assertEqual(
            payload["render_quality"],
            {
                "supported_quality_tiers": ["full", "proxy"],
            },
        )

    def test_viewer_settings_group_band_preserves_specialized_body_height(self) -> None:
        spec = NodeTypeSpec(
            type_id="tests.viewer_settings_groups",
            display_name="Viewer Settings Groups",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "fields",
                    "in",
                    "data",
                    GRAPH_DATA_TYPE_ID,
                    required=False,
                ),
                PortSpec(
                    "session",
                    "out",
                    "data",
                    VIEWER_SESSION_DATA_TYPE_ID,
                ),
            ),
            properties=(),
            surface_family="viewer",
            settings_groups=(
                SettingsGroupSpec(
                    group_id="general",
                    label="General Options",
                    items=(SettingsGroupItemSpec(port_key="fields"),),
                ),
            ),
        )
        registry = NodeRegistry()
        registry.register(lambda: _ViewerSurfacePlugin(spec))
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            spec.type_id,
            spec.display_name,
            64.0,
            96.0,
        )
        builder = GraphScenePayloadBuilder()

        def payload() -> dict[str, object]:
            nodes, _minimap, _edges = builder.rebuild_models(
                model=model,
                registry=registry,
                workspace_id=workspace.workspace_id,
                scope_path=(),
                graph_theme_bridge=None,
            )
            return next(item for item in nodes if item["node_id"] == node.node_id)

        collapsed_group_payload = payload()
        node.expanded_settings_group_ids = ("general",)
        expanded_group_payload = payload()

        self.assertEqual(collapsed_group_payload["height"], 272.0)
        self.assertEqual(expanded_group_payload["height"], 290.0)
        self.assertEqual(collapsed_group_payload["settings_band"]["height"], 36.0)
        self.assertEqual(expanded_group_payload["settings_band"]["height"], 54.0)
        self.assertEqual(collapsed_group_payload["surface_metrics"]["body_height"], 176.0)
        self.assertEqual(expanded_group_payload["surface_metrics"]["body_height"], 176.0)
        self.assertEqual(
            collapsed_group_payload["viewer_surface"]["body_rect"],
            expanded_group_payload["viewer_surface"]["body_rect"],
        )
        output_port = next(
            port for port in expanded_group_payload["ports"] if port["key"] == "session"
        )
        self.assertNotIn("settings_group_id", output_port)

    def test_graph_node_host_routes_viewer_surface_family_through_loader(self) -> None:
        self._run_qml_probe(
            "viewer-surface-loader-contract",
            """
            from PyQt6.QtCore import QPointF

            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": viewer_payload(),
                    "snapshotReuseActive": True,
                },
            )
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            viewport = host.findChild(QObject, "graphNodeViewerViewport")
            assert loader is not None
            assert surface is not None
            assert viewport is not None

            assert host.property("surfaceFamily") == "viewer"
            assert loader.property("loadedSurfaceKey") == "viewer"
            input_capabilities = variant_value(loader.property("inputCapabilities"))
            assert "stylus" in input_capabilities["devices"], input_capabilities
            assert "viewer.pluginGesture" in input_capabilities["plugin_gestures"], input_capabilities
            assert host.property("resolvedQualityTier") == "proxy"
            assert bool(surface.property("proxySurfaceActive"))
            assert not bool(surface.property("liveSurfaceActive"))

            contract = variant_value(loader.property("viewerSurfaceContract"))
            assert contract["overlay_target"] == "body"
            assert bool(contract["proxy_surface_supported"])
            assert bool(contract["live_surface_supported"])

            body_rect = loader.property("viewerBodyRect")
            live_rect = loader.property("viewerLiveSurfaceRect")
            assert rect_field(body_rect, "x") == 14.0
            assert rect_field(body_rect, "y") == 30.0
            assert rect_field(body_rect, "width") == 312.0
            assert rect_field(body_rect, "height") == 176.0
            top_left = viewport.mapToItem(surface, QPointF(0.0, 0.0))
            bottom_right = viewport.mapToItem(
                surface,
                QPointF(float(viewport.property("width")), float(viewport.property("height"))),
            )
            assert abs(rect_field(live_rect, "x") - float(top_left.x())) < 0.1
            assert abs(rect_field(live_rect, "y") - float(top_left.y())) < 0.1
            assert abs(rect_field(live_rect, "width") - (float(bottom_right.x()) - float(top_left.x()))) < 0.1
            assert abs(rect_field(live_rect, "height") - (float(bottom_right.y()) - float(top_left.y()))) < 0.1
            assert rect_field(live_rect, "y") > rect_field(body_rect, "y")
            assert rect_field(live_rect, "height") < rect_field(body_rect, "height")
            """,
        )

    def test_viewer_ports_follow_live_resize_preview(self) -> None:
        self._run_qml_probe(
            "viewer-live-resize-port-preview",
            """
            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": viewer_payload(),
                    "snapshotReuseActive": True,
                },
            )

            initial_metrics = variant_value(host.property("surfaceMetrics"))
            initial_point = variant_value(host.localPortPoint("in", 0))
            assert abs(float(initial_metrics["body_height"]) - 176.0) < 0.1
            assert abs(float(initial_metrics["port_top"]) - 206.0) < 0.1
            assert abs(float(initial_point["y"]) - 212.0) < 0.1

            host.setProperty("_liveWidth", 296.0)
            host.setProperty("_liveHeight", 320.0)
            host.setProperty("_liveGeometryActive", True)
            app.processEvents()

            live_metrics = variant_value(host.property("surfaceMetrics"))
            live_point = variant_value(host.localPortPoint("in", 0))
            assert abs(float(live_metrics["body_height"]) - 260.0) < 0.1
            assert abs(float(live_metrics["port_top"]) - 290.0) < 0.1
            assert abs(float(live_point["y"]) - 296.0) < 0.1
            assert float(live_point["y"]) > float(initial_point["y"])
            """,
        )

    def test_viewer_ports_stay_within_shell_when_height_is_reduced_above_minimum(self) -> None:
        self._run_qml_probe(
            "viewer-mid-height-port-fit",
            """
            payload = viewer_payload()
            payload["height"] = 254.0
            payload["surface_metrics"]["default_height"] = 272.0
            payload["surface_metrics"]["min_height"] = 244.0
            payload["surface_metrics"]["body_height"] = 176.0
            payload["surface_metrics"]["port_top"] = 206.0
            payload["ports"] = [
                {"port_id": "field", "label": "field", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene"},
                {"port_id": "model", "label": "model", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene"},
                {"port_id": "mesh", "label": "mesh", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene"},
                {"port_id": "session", "label": "session", "direction": "out", "kind": "data", "data_type": "viewer_session"},
            ]

            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": payload,
                    "snapshotReuseActive": True,
                },
            )

            reduced_metrics = variant_value(host.property("surfaceMetrics"))
            reduced_point = variant_value(host.localPortPoint("in", 2))
            assert abs(float(reduced_metrics["body_height"]) - 158.0) < 0.1
            assert abs(float(reduced_metrics["port_top"]) - 188.0) < 0.1
            assert (
                float(reduced_metrics["port_top"])
                + 3.0 * float(reduced_metrics["port_height"])
                + float(reduced_metrics["body_bottom_margin"])
            ) <= 254.1
            assert float(reduced_point["y"]) <= 254.0
            """,
        )

    def test_viewer_host_clamps_short_payload_height_to_live_surface_minimum(self) -> None:
        self._run_qml_probe(
            "viewer-short-payload-height-clamp",
            """
            payload = viewer_payload()
            payload["height"] = 236.0
            payload["surface_metrics"]["default_height"] = 290.0
            payload["surface_metrics"]["min_height"] = 262.0
            payload["surface_metrics"]["body_height"] = 176.0
            payload["surface_metrics"]["port_top"] = 206.0
            payload["ports"] = [
                {"key": "metadata", "label": "metadata", "direction": "in", "kind": "data", "data_type": "dict", "exposed": True},
                {"key": "preview", "label": "preview", "direction": "out", "kind": "data", "data_type": "viewer_preview", "exposed": True},
                {"key": "field", "label": "field", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene", "exposed": True},
                {"key": "model", "label": "model", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene", "exposed": True},
                {"key": "mesh", "label": "mesh", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene", "exposed": True},
                {"key": "session", "label": "session", "direction": "out", "kind": "data", "data_type": "viewer_session", "exposed": True},
            ]

            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": payload,
                    "snapshotReuseActive": True,
                },
            )

            host_height = float(host.property("height"))
            clamped_metrics = variant_value(host.property("surfaceMetrics"))
            last_input_point = variant_value(host.localPortPoint("in", 3))
            last_output_point = variant_value(host.localPortPoint("out", 1))

            assert abs(host_height - 262.0) < 0.1
            assert abs(float(clamped_metrics["min_height"]) - 262.0) < 0.1
            assert float(last_input_point["y"]) <= host_height
            assert float(last_output_point["y"]) <= host_height
            """,
        )

    def test_viewer_host_heals_stale_default_height_without_explicit_node_height(self) -> None:
        self._run_qml_probe(
            "viewer-stale-default-height-heal",
            """
            payload = viewer_payload()
            del payload["height"]
            payload["surface_metrics"]["default_height"] = 290.0
            payload["surface_metrics"]["min_height"] = 262.0
            payload["surface_metrics"]["body_height"] = 176.0
            payload["surface_metrics"]["port_top"] = 206.0
            payload["ports"] = [
                {"key": "metadata", "label": "metadata", "direction": "in", "kind": "data", "data_type": "dict", "exposed": True},
                {"key": "preview", "label": "preview", "direction": "out", "kind": "data", "data_type": "viewer_preview", "exposed": True},
                {"key": "field", "label": "field", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene", "exposed": True},
                {"key": "model", "label": "model", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene", "exposed": True},
                {"key": "mesh", "label": "mesh", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene", "exposed": True},
                {"key": "session", "label": "session", "direction": "out", "kind": "data", "data_type": "viewer_session", "exposed": True},
            ]

            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": payload,
                    "snapshotReuseActive": True,
                    "graphLabelPixelSize": 16,
                },
            )

            host_height = float(host.property("height"))
            metrics = variant_value(host.property("surfaceMetrics"))
            mesh_row = named_item(host, "graphNodeInputPortRow", "mesh")
            mesh_row_bottom = float(mesh_row.y()) + float(mesh_row.height())

            assert abs(host_height - 314.0) < 0.1
            assert abs(float(metrics["default_height"]) - 314.0) < 0.1
            assert abs(float(metrics["port_height"]) - 24.0) < 0.1
            assert mesh_row_bottom <= host_height - 0.1
            """,
        )

    def test_viewer_host_respects_payload_body_top_when_title_icon_increases_header(self) -> None:
        self._run_qml_probe(
            "viewer-body-top-consistency-with-large-header",
            """
            payload = viewer_payload()
            payload["height"] = 320.0
            payload["surface_metrics"]["default_height"] = 320.0
            payload["surface_metrics"]["min_height"] = 292.0
            payload["surface_metrics"]["header_height"] = 54.0
            payload["surface_metrics"]["title_height"] = 54.0
            payload["surface_metrics"]["body_top"] = 60.0
            payload["surface_metrics"]["body_height"] = 176.0
            payload["surface_metrics"]["port_top"] = 236.0
            payload["surface_metrics"]["port_height"] = 24.0
            payload["ports"] = [
                {"key": "metadata", "label": "metadata", "direction": "in", "kind": "data", "data_type": "dict", "exposed": True},
                {"key": "field", "label": "field", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene", "exposed": True},
                {"key": "model", "label": "model", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene", "exposed": True},
            ]

            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": payload,
                    "snapshotReuseActive": True,
                    "graphLabelPixelSize": 16,
                },
            )

            host_height = float(host.property("height"))
            metrics = variant_value(host.property("surfaceMetrics"))
            model_row = named_item(host, "graphNodeInputPortRow", "model")
            model_row_bottom = float(model_row.y()) + float(model_row.height())
            model_point = variant_value(host.localPortPoint("in", 2))

            assert abs(host_height - 320.0) < 0.1
            assert abs(float(metrics["body_height"]) - 176.0) < 0.1
            assert abs(float(metrics["port_top"]) - 236.0) < 0.1
            assert abs(float(model_point["y"]) - 290.0) < 0.1
            assert model_row_bottom <= host_height - 0.1
            """,
        )

    def test_viewer_port_rows_stay_inside_shell_for_large_graph_labels(self) -> None:
        self._run_qml_probe(
            "viewer-large-graph-label-port-fit",
            """
            payload = viewer_payload()
            payload["height"] = 236.0
            payload["surface_metrics"]["default_height"] = 290.0
            payload["surface_metrics"]["min_height"] = 262.0
            payload["surface_metrics"]["body_height"] = 176.0
            payload["surface_metrics"]["port_top"] = 206.0
            payload["ports"] = [
                {"key": "metadata", "label": "metadata", "direction": "in", "kind": "data", "data_type": "dict", "exposed": True},
                {"key": "preview", "label": "preview", "direction": "out", "kind": "data", "data_type": "viewer_preview", "exposed": True},
                {"key": "field", "label": "field", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene", "exposed": True},
                {"key": "model", "label": "model", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene", "exposed": True},
                {"key": "mesh", "label": "mesh", "direction": "in", "kind": "data", "data_type": "COREX.Engineering.Scene", "exposed": True},
                {"key": "session", "label": "session", "direction": "out", "kind": "data", "data_type": "viewer_session", "exposed": True},
            ]

            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": payload,
                    "snapshotReuseActive": True,
                    "graphLabelPixelSize": 16,
                },
            )

            host_height = float(host.property("height"))
            metrics = variant_value(host.property("surfaceMetrics"))
            mesh_row = named_item(host, "graphNodeInputPortRow", "mesh")
            mesh_row_bottom = float(mesh_row.y()) + float(mesh_row.height())

            assert abs(host_height - 286.0) < 0.1
            assert abs(float(metrics["min_height"]) - 286.0) < 0.1
            assert abs(float(metrics["port_height"]) - 24.0) < 0.1
            assert mesh_row_bottom <= host_height - 0.1
            """,
        )

    def test_graph_viewer_surface_contract_includes_bridge_binding_and_control_rects(self) -> None:
        self._run_qml_probe(
            "viewer-surface-bridge-contract",
            """
            from PyQt6.QtCore import pyqtSignal

            class ViewerSessionBridgeStub(QObject):
                sessions_changed = pyqtSignal()

                @pyqtProperty("QVariantList", notify=sessions_changed)
                def sessions_model(self):
                    return [
                        {
                            "workspace_id": "ws_main",
                            "node_id": "node_viewer_surface_contract",
                            "session_id": "session::viewer-contract",
                            "phase": "closed",
                            "request_id": "req::open",
                            "last_command": "open",
                            "last_error": "",
                            "playback_state": "playing",
                            "step_index": 99,
                            "cache_state": "live_ready",
                            "backend_id": "backend.legacy",
                            "transport_revision": 99,
                            "live_open_status": "blocked",
                            "live_open_blocker": {"code": "legacy_blocked"},
                            "invalidated_reason": "legacy_invalidated",
                            "close_reason": "legacy_close",
                            "data_refs": {"fields": {"kind": "handle_ref", "handle_id": "handle::fields"}},
                            "transport": {
                                "kind": "bundle",
                                "backend_id": "backend.legacy",
                                "bundle_path": "C:/temp/viewer_bundle",
                            },
                            "summary": {
                                "result_name": "Legacy Displacement",
                                "set_label": "Legacy Set",
                                "cache_state": "live_ready",
                                "backend_id": "backend.legacy",
                                "transport_revision": 99,
                                "live_open_status": "blocked",
                            },
                            "options": {
                                "live_mode": "full",
                                "playback_state": "playing",
                                "step_index": 99,
                                "backend_id": "backend.legacy",
                                "transport_revision": 99,
                                "live_open_status": "blocked",
                            },
                            "session_model": {
                                "workspace_id": "ws_main",
                                "node_id": "node_viewer_surface_contract",
                                "session_id": "session::viewer-contract",
                                "phase": "open",
                                "request_id": "req::open",
                                "last_command": "open",
                                "last_error": "",
                                "playback_state": "paused",
                                "step_index": 2,
                                "playback": {"state": "paused", "step_index": 2},
                                "cache_state": "proxy_ready",
                                "backend_id": "backend.viewer",
                                "transport_revision": 7,
                                "live_mode": "proxy",
                                "live_open_status": "ready",
                                "live_open_blocker": {},
                                "invalidated_reason": "",
                                "close_reason": "",
                                "data_refs": {"fields": {"kind": "handle_ref", "handle_id": "handle::fields"}},
                                "transport": {
                                    "kind": "bundle",
                                    "backend_id": "backend.viewer",
                                    "bundle_path": "C:/temp/viewer_bundle",
                                },
                                "summary": {
                                    "result_name": "Displacement",
                                    "set_label": "Set 2",
                                    "cache_state": "proxy_ready",
                                    "backend_id": "backend.viewer",
                                    "transport_revision": 7,
                                    "live_open_status": "ready",
                                },
                                "options": {
                                    "live_mode": "proxy",
                                    "playback_state": "paused",
                                    "step_index": 2,
                                    "backend_id": "backend.viewer",
                                    "transport_revision": 7,
                                    "live_open_status": "ready",
                                },
                            },
                        }
                    ]

                @pyqtProperty(str, constant=True)
                def last_error(self):
                    return ""

            bridge = ViewerSessionBridgeStub()
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)
            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            assert surface is not None

            interactive_rects = variant_list(surface.property("viewerInteractiveRects"))
            assert interactive_rects == [], interactive_rects

            actions = variant_list(surface.property("surfaceActions"))
            action_ids = [str(action["id"]) for action in actions]
            assert action_ids == ["openSession", "playPause", "step", "camera", "screenshot", "copyImage", "detach", "fullscreen"], action_ids

            camera_action = next(action for action in actions if action["id"] == "camera")
            popover_actions = list(camera_action["popoverActions"])
            popover_ids = [str(action["id"]) for action in popover_actions]
            assert popover_ids == ["cameraFit", "cameraIso", "cameraXy", "cameraXz", "cameraYz"], popover_ids
            assert not bool(camera_action["enabled"])
            """,
        )

    def test_shared_viewer_controls_execute_group_overflow_selection_and_fullscreen_shortcuts(
        self,
    ) -> None:
        self._run_qml_probe(
            "shared-viewer-controls-runtime-contract",
            """
            from PyQt6.QtCore import (
                Q_ARG,
                QMetaObject,
                QPointF,
                QObject,
                Qt,
                pyqtProperty,
                pyqtSignal,
                pyqtSlot,
            )
            from PyQt6.QtQuick import QQuickWindow
            from PyQt6.QtTest import QTest

            class OverlayThemeBridgeStub(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def palette(self):
                    return {
                        "accent": "#2F89FF",
                        "accent_strong": "#187fc4",
                        "app_bg": "#151821",
                        "border": "#3a4355",
                        "hover": "#33405c",
                        "input_bg": "#18202d",
                        "input_border": "#465066",
                        "muted_fg": "#95a0b8",
                        "panel_bg": "#1b1f2a",
                        "panel_title_fg": "#eef3ff",
                        "pressed": "#22304a",
                        "tab_bg": "#252b33",
                        "tab_fg": "#eef3ff",
                        "tab_selected_fg": "#ffffff",
                        "toolbar_bg": "#202635",
                    }

            class FullscreenBridgeStub(QObject):
                content_fullscreen_changed = pyqtSignal()

                @pyqtProperty(bool, notify=content_fullscreen_changed)
                def open(self):
                    return True

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def node_id(self):
                    return "node_viewer_surface_contract"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def content_kind(self):
                    return "viewer"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def title(self):
                    return "Engineering Viewer"

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def media_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def viewer_payload(self):
                    return {
                        "title": "Engineering Viewer",
                        "surface_spec": {},
                    }

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def web_editor_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def web_page_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def plot_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def tabular_payload(self):
                    return {}

                @pyqtProperty(QObject, notify=content_fullscreen_changed)
                def web_surface_bridge(self):
                    return None

                @pyqtSlot()
                def request_close(self):
                    return None

                @pyqtSlot(str, result=bool)
                def request_toggle_for_node(self, _node_id):
                    return True

            supported_filters = [
                {
                    "id": value,
                    "available": value != "fe_element",
                    "unsupported_reason": (
                        "No finite elements." if value == "fe_element" else ""
                    ),
                }
                for value in (
                    "cad_vertex",
                    "cad_edge",
                    "cad_face",
                    "cad_body",
                    "fe_node",
                    "fe_element_face",
                    "fe_element",
                )
            ]
            session_state = {
                "workspace_id": "ws_main",
                "node_id": "node_viewer_surface_contract",
                "session_id": "session::viewer-controls",
                "phase": "open",
                "playback_state": "paused",
                "options": {
                    "representation": "surface",
                    "parallel_projection": False,
                    "show_mesh_edges": False,
                    "show_attribute_colors": False,
                },
                "summary": {
                    "viewer_kind": "engineering_scene",
                    "capabilities": {
                        "playback": False,
                        "supported_render_modes": [
                            "wireframe",
                            "wireframe_visible_edges",
                            "surface",
                            "surface_with_edges",
                        ],
                        "wireframe_visible_edges": True,
                        "topological_edges": True,
                        "mesh_edges": {
                            "available": False,
                            "reason": "No mesh layer.",
                        },
                        "attribute_colors": {
                            "available": False,
                            "reason": "No source colors.",
                        },
                        "projection": True,
                        "fit_selection": True,
                        "selection_isolate": True,
                        "camera_bookmarks": True,
                        "supported_selection_filters": supported_filters,
                    },
                },
            }

            class ViewerSessionBridgeStub(QObject):
                sessions_changed = pyqtSignal()

                @pyqtProperty("QVariantList", notify=sessions_changed)
                def sessions_model(self):
                    return [session_state]

                @pyqtSlot(str, result="QVariantMap")
                def session_state(self, _node_id):
                    return session_state

            class ViewerControlBridgeStub(QObject):
                viewer_control_changed = pyqtSignal(str)
                viewer_tangent_selection_angle_changed = pyqtSignal(float)

                def __init__(self):
                    super().__init__()
                    self.cycle_calls = []
                    self.angle_calls = []

                @pyqtSlot(str, result="QVariantList")
                def viewer_camera_bookmarks(self, _node_id):
                    return [{"name": "Front"}, {"name": "Rear"}]

                @pyqtSlot(str, result=int)
                def viewer_camera_bookmark_current_index(self, _node_id):
                    return 0

                @pyqtSlot(str, int, result=bool)
                def cycle_viewer_camera_bookmark(self, _node_id, delta):
                    self.cycle_calls.append(int(delta))
                    return True

                @pyqtSlot(result=float)
                def viewer_tangent_selection_angle_degrees(self):
                    return 27.0

                @pyqtSlot(float, result=bool)
                def set_viewer_tangent_selection_angle_degrees(self, value):
                    self.angle_calls.append(float(value))
                    return True

            class ViewerHostServiceStub(QObject):
                revision_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self.filter_calls = []

                @pyqtProperty(int, notify=revision_changed)
                def viewer_overlay_revision(self):
                    return 1

                @pyqtSlot(str, result="QVariantMap")
                def viewer_selection_snapshot(self, _node_id):
                    return {
                        "entities": [
                            {
                                "entity_kind": "cad_face",
                                "entity_id": "part:1/face:2",
                            }
                        ],
                        "isolate_active": True,
                        "selection_filter": "cad_face",
                    }

                @pyqtSlot(str, str, result=bool)
                def set_viewer_selection_filter(self, node_id, value):
                    self.filter_calls.append((str(node_id), str(value)))
                    return True

                @pyqtSlot(str, result=bool)
                def detached_viewer_active(self, _node_id):
                    return False

            theme = OverlayThemeBridgeStub()
            bridge = FullscreenBridgeStub()
            sessions = ViewerSessionBridgeStub()
            controls_bridge = ViewerControlBridgeStub()
            host = ViewerHostServiceStub()
            engine.rootContext().setContextProperty("themeBridge", theme)
            engine.rootContext().setContextProperty("viewerSessionBridge", sessions)
            engine.rootContext().setContextProperty("viewerControlBridge", controls_bridge)
            engine.rootContext().setContextProperty("viewerHostService", host)

            overlay_path = repo_root / "ea_node_editor" / "ui_qml" / "ContentFullscreenOverlay.qml"
            overlay = create_component(overlay_path, {"bridgeRef": bridge})
            window = QQuickWindow()
            window.setGeometry(0, 0, 380, 720)
            overlay.setParentItem(window.contentItem())
            overlay.setWidth(380)
            overlay.setHeight(720)
            window.show()
            window.requestActivate()
            overlay.forceActiveFocus()
            app.processEvents()

            def child(name):
                item = overlay.findChild(QObject, name)
                assert item is not None, name
                return item

            quick = child("viewerQuickControls")
            ordered = [
                child("viewerRenderWireframeButton"),
                child("viewerFitAllButton"),
                child("viewerProjectionButton"),
                child("viewerDetachDockButton"),
            ]
            positions = [item.mapToItem(quick, QPointF()).x() for item in ordered]
            assert positions == sorted(positions), positions

            flickable = child("viewerQuickControlsFlickable")
            right_chevron = child("viewerQuickControlsRightChevron")
            left_chevron = child("viewerQuickControlsLeftChevron")
            assert float(flickable.property("contentWidth")) > float(flickable.property("width"))
            assert bool(right_chevron.property("visible"))
            flickable.setProperty("contentX", 50.0)
            app.processEvents()
            assert bool(left_chevron.property("visible"))

            assert int(quick.property("currentBookmarkIndex")) == 0
            assert len(variant_list(quick.property("cameraBookmarks"))) == 2
            for name in (
                "viewerSavedViewsPopup",
                "viewerSaveCurrentViewButton",
                "viewerNextSavedViewButton",
                "viewerPreviousSavedViewButton",
            ):
                child(name)
            assert bool(quick.property("isolateActive"))
            assert bool(child("viewerIsolateSelectionButton").property("selectedStyle"))

            selection = child("viewerSelectionControls")
            assert bool(selection.property("visible"))
            supported_buttons = (
                "viewerSelectCadVertexButton",
                "viewerSelectCadEdgeButton",
                "viewerSelectCadFaceButton",
                "viewerSelectCadBodyButton",
                "viewerSelectFeNodeButton",
                "viewerSelectFeElementFaceButton",
            )
            assert all(bool(child(name).property("actionEnabled")) for name in supported_buttons)
            unsupported = child("viewerSelectFeElementButton")
            assert not bool(unsupported.property("actionEnabled"))
            assert str(unsupported.property("tooltipText")) == "No finite elements."
            assert abs(float(selection.property("tangentAngleDegrees")) - 27.0) < 0.001
            tangent = child("viewerSelectionTangentAngleSpinBox")
            assert int(tangent.property("from")) == 0
            assert int(tangent.property("to")) == 90
            assert int(tangent.property("value")) == 27
            QMetaObject.invokeMethod(
                selection,
                "setSelectionFilter",
                Q_ARG("QVariant", "cad_edge"),
            )
            QMetaObject.invokeMethod(
                selection,
                "setTangentAngle",
                Q_ARG("QVariant", 42.0),
            )
            app.processEvents()
            assert host.filter_calls == [
                ("node_viewer_surface_contract", "cad_edge")
            ], host.filter_calls
            assert controls_bridge.angle_calls == [42.0], controls_bridge.angle_calls

            shaded = child("viewerRenderShadedButton")
            assert str(shaded.property("accessibleName")) == "Shaded"
            assert bool(shaded.property("checkable"))
            assert int(shaded.property("buttonHeight")) == 34
            assert bool(shaded.property("selectedStyle"))

            viewport = child("contentFullscreenViewerViewport")
            quick_top = quick.mapToItem(overlay, QPointF()).y()
            viewport_bottom = (
                viewport.mapToItem(overlay, QPointF()).y() + float(viewport.property("height"))
            )
            assert abs(quick_top - viewport_bottom) < 1.1, (quick_top, viewport_bottom)

            overlay.forceActiveFocus()
            app.processEvents()
            QTest.keyClick(window, Qt.Key.Key_PageUp)
            QTest.keyClick(window, Qt.Key.Key_PageDown)
            app.processEvents()
            assert controls_bridge.cycle_calls == [-1, 1], controls_bridge.cycle_calls

            window.close()
            overlay.setParentItem(None)
            overlay.deleteLater()
            window.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_viewer_surface_fullscreen_action_routes_bridge(self) -> None:
        self._run_qml_probe(
            "viewer-content-fullscreen-action",
            """
            from PyQt6.QtCore import QMetaObject, Q_ARG, pyqtSlot

            class ContentFullscreenBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.toggle_calls = []

                @pyqtSlot(str, result=bool)
                def request_toggle_for_node(self, node_id):
                    self.toggle_calls.append(str(node_id or ""))
                    return True

            bridge = ContentFullscreenBridgeStub()
            engine.rootContext().setContextProperty("contentFullscreenBridge", bridge)

            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            assert surface is not None
            assert host.findChild(QObject, "graphNodeViewerMoreButton") is None

            actions = variant_list(surface.property("surfaceActions"))
            fullscreen_action = next(action for action in actions if action["id"] == "fullscreen")
            assert bool(fullscreen_action["enabled"])

            QMetaObject.invokeMethod(surface, "dispatchSurfaceAction", Q_ARG("QVariant", "fullscreen"))
            app.processEvents()
            assert bridge.toggle_calls == ["node_viewer_surface_contract"]
            """,
        )

    def test_graph_viewer_surface_has_no_footer_meta_and_dispatches_camera(self) -> None:
        self._run_qml_probe(
            "viewer-no-footer-meta-camera-dispatch",
            """
            from PyQt6.QtCore import QMetaObject, Q_ARG, pyqtSignal, pyqtSlot

            class ViewerSessionBridgeStub(QObject):
                sessions_changed = pyqtSignal()
                source_kind = "fe"

                def _projection(self):
                    return {
                        "workspace_id": "ws_main",
                        "node_id": "node_viewer_surface_contract",
                        "session_id": "session::viewer-meta",
                        "phase": "open",
                        "last_error": "",
                        "playback_state": "paused",
                        "step_index": 1,
                        "cache_state": "proxy_ready",
                        "backend_id": "backend.viewer",
                        "transport_revision": 3,
                        "live_mode": "proxy",
                        "live_open_status": "ready",
                        "live_open_blocker": {},
                        "transport": {"kind": "bundle"},
                        "summary": {
                            "source_kind": self.source_kind,
                            "result_name": "Displacement",
                            "set_label": "Set 2",
                            "unit": "mm",
                            "time_values": [1.0, 2.5],
                            "value_ranges": [
                                {"min": 0.0, "max": 0.5, "component_min": [0.0], "component_max": [0.5]},
                                {"min": 0.001, "max": 0.0421553, "component_min": [0.001], "component_max": [0.0421553]},
                            ],
                        },
                        "options": {
                            "live_mode": "proxy",
                            "playback_state": "paused",
                            "step_index": 1,
                            "result_component": "magnitude",
                        },
                    }

                @pyqtProperty("QVariantList", notify=sessions_changed)
                def sessions_model(self):
                    return [self._projection()]

                @pyqtSlot(str, result="QVariantMap")
                def session_state(self, node_id):
                    if str(node_id) != "node_viewer_surface_contract":
                        return {}
                    return self._projection()

                @pyqtProperty(str, constant=True)
                def last_error(self):
                    return ""

            class ViewerHostServiceStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.standard_view_calls = []
                    self.reset_calls = []
                    self.detach_calls = []

                @pyqtSlot(str, str, result=bool)
                def apply_standard_view(self, node_id, view_id):
                    self.standard_view_calls.append((str(node_id), str(view_id)))
                    return True

                @pyqtSlot(str, result=bool)
                def reset_overlay_camera(self, node_id):
                    self.reset_calls.append(str(node_id))
                    return True

                @pyqtSlot(str, result=bool)
                def open_detached_viewer(self, node_id):
                    self.detach_calls.append(str(node_id))
                    return True

            bridge = ViewerSessionBridgeStub()
            host_service = ViewerHostServiceStub()
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)
            engine.rootContext().setContextProperty("viewerHostService", host_service)

            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            assert surface is not None

            assert surface.property("viewerFooterMetaModel") is None
            for object_name in (
                "graphNodeViewerSceneCountMeta",
                "graphNodeViewerResultMeta",
                "graphNodeViewerSelectionMeta",
                "graphNodeViewerStepMeta",
                "graphNodeViewerMinMeta",
                "graphNodeViewerMaxMeta",
                "graphNodeViewerTimeMeta",
                "graphNodeViewerStatusMeta",
            ):
                assert host.findChild(QObject, object_name) is None

            QMetaObject.invokeMethod(surface, "dispatchSurfaceAction", Q_ARG("QVariant", "cameraIso"))
            QMetaObject.invokeMethod(surface, "dispatchSurfaceAction", Q_ARG("QVariant", "cameraFit"))
            QMetaObject.invokeMethod(surface, "dispatchSurfaceAction", Q_ARG("QVariant", "detach"))
            app.processEvents()
            assert host_service.standard_view_calls == [("node_viewer_surface_contract", "iso")], host_service.standard_view_calls
            assert host_service.reset_calls == ["node_viewer_surface_contract"], host_service.reset_calls
            assert host_service.detach_calls == ["node_viewer_surface_contract"], host_service.detach_calls
            """,
        )
