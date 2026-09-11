from __future__ import annotations

from pathlib import Path
import unittest

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.excalidraw import (
    EXCALIDRAW_BOARD_TYPE_ID,
    EXCALIDRAW_PREVIEW_REF_PROPERTY,
    EXCALIDRAW_STATE_PROPERTY,
)
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from tests.graph_surface import (
    ExcalidrawWebBoardPassiveGraphHostTests,
    LockedPlaceholderGraphHostTests,
    PassiveGraphSurfaceHostBoundaryTests,
    PassiveGraphSurfaceHostTests,
    PassiveGraphSurfaceInlineEditorTests,
    PassiveGraphSurfaceMediaAndScopeTests,
)
from tests.graph_surface.environment import PassiveGraphSurfaceHostTestBase

PROJECT_ROOT = Path(__file__).resolve().parents[1]

__all__ = [
    "ExcalidrawWebBoardPassiveGraphHostTests",
    "LockedPlaceholderGraphHostTests",
    "PassiveGraphSurfaceHostBoundaryTests",
    "PassiveGraphSurfaceHostTests",
    "PassiveGraphSurfaceInlineEditorTests",
    "PassiveGraphSurfaceMediaAndScopeTests",
    "PortTypePresentationQmlTests",
    "FlowchartTimestampSurfaceQmlTests",
    "WebPageGenericSurfaceQmlTests",
]


class PortTypePresentationQmlTests(PassiveGraphSurfaceHostTestBase):
    def test_ports_use_projected_input_state_and_keep_edge_reason_out_of_port_text(self) -> None:
        self._run_qml_probe(
            "port-type-presentation-and-edge-reason-ownership",
            """
            from PyQt6.QtGui import QColor
            from PyQt6.QtQml import QQmlProperty

            component = QQmlComponent(engine)
            component.setData(
                b'''
                import QtQuick 2.15
                Item {
                    property var edgePayload: []
                    property var wireDragState: null
                    property var executionFacts: null
                    property QtObject prefs: QtObject {
                        property bool notchedPortsEnabled: false
                        property string canvasBackgroundVariant: "theme"
                    }
                    property QtObject sceneBridge: QtObject {
                        property var selected_node_lookup: ({})
                    }
                    property var sceneCommandBridge: null
                    property var canvasStateBridgeRef: null
                    property var activeToolbarHost: null
                    property var frameSceneRectPayload: null
                }
                ''',
                QUrl(),
            )
            assert component.status() == QQmlComponent.Status.Ready, [
                error.toString() for error in component.errors()
            ]
            canvas_stub = component.create()
            assert canvas_stub is not None
            canvas_stub._component_ref = component

            generation = "a" * 64
            payload = node_payload()
            payload["height"] = 145.0
            payload["ports"][0].update({
                "data_type": "COREX.DataTypes.String",
                "data_type_label": "String",
                "data_type_family": "scalar",
                "data_type_family_label": "Scalar",
                "data_type_color_token": "data.scalar",
                "accepted_data_type_labels": ["String", "Graph Data"],
                "data_access": "list",
                "catalog_generation": generation,
                "flow_state": "invalid",
            })
            payload["ports"][1].update({
                "data_type": "COREX.DataTypes.Int",
                "data_type_label": "Integer",
                "data_type_family": "scalar",
                "data_type_family_label": "Scalar",
                "data_type_color_token": "data.scalar",
                "accepted_data_type_labels": ["Integer"],
                "data_access": "tree",
                "catalog_generation": generation,
                "flow_state": "flowing",
            })
            payload["ports"].append({
                "key": "availability",
                "label": "Availability",
                "direction": "in",
                "kind": "data",
                "data_type": "COREX.DataTypes.String",
                "data_type_label": "String",
                "data_type_family": "scalar",
                "data_type_family_label": "Scalar",
                "data_type_color_token": "data.scalar",
                "accepted_data_type_labels": ["String"],
                "data_access": "item",
                "catalog_generation": generation,
                "flow_state": "waiting",
                "availability": "unavailable",
                "availability_reason": "Source temporarily unavailable",
                "inactive_reason": "Driven by an upstream value",
                "blocks_new_connections": True,
            })
            payload["ports"].append({
                "key": "normal",
                "label": "Normal",
                "direction": "out",
                "kind": "data",
                "data_type": "COREX.DataTypes.String",
                "data_type_label": "String",
                "data_type_family": "scalar",
                "data_type_family_label": "Scalar",
                "data_type_color_token": "data.scalar",
                "accepted_data_type_labels": ["String"],
                "data_access": "item",
                "catalog_generation": generation,
                "flow_state": "default",
                "connected": False,
            })
            canvas_stub.setProperty("edgePayload", [{
                "edge_id": "warning_edge",
                "source_node_id": "upstream",
                "source_port_key": "result",
                "target_node_id": payload["node_id"],
                "target_port_key": "payload",
                "data_type_warning": True,
                "data_type_warning_reason": "Integer cannot feed the current input",
                "availability_warning": False,
                "availability_reason": "",
            }])
            endpoint_lookup = {
                f"${len(payload['node_id'])}:{payload['node_id']}:7:payload": True,
            }
            canvas_stub.setProperty("wireDragState", {
                "active": True,
                "compatibility_snapshot_valid": True,
                "compatibility_catalog_generation": generation,
                "compatible_endpoint_lookup": endpoint_lookup,
            })

            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": payload, "canvasItem": canvas_stub},
            )
            window = attach_host_to_window(host)
            try:
                settle_events(5)
                input_dot = named_item(host, "graphNodeInputPortDot", "payload")
                availability_dot = named_item(host, "graphNodeInputPortDot", "availability")
                output_dot = named_item(host, "graphNodeOutputPortDot", "result")
                normal_dot = named_item(host, "graphNodeOutputPortDot", "normal")
                input_ring = named_item(input_dot, "graphNodeInputPortRing", "payload")
                input_mouse = named_item(input_dot, "graphNodeInputPortMouseArea", "payload")
                availability_mouse = named_item(
                    availability_dot,
                    "graphNodeInputPortMouseArea",
                    "availability",
                )
                output_mouse = named_item(output_dot, "graphNodeOutputPortMouseArea", "result")
                normal_mouse = named_item(normal_dot, "graphNodeOutputPortMouseArea", "normal")

                data_accent = QColor("#7AA8FF").name()
                waiting = QColor("#E8A838").name()
                invalid = QColor("#FF543E").name()
                assert QColor(normal_dot.property("portColor")).name() == data_accent
                assert QColor(QQmlProperty.read(normal_dot, "border.color")).name() == data_accent
                assert QColor(QQmlProperty.read(input_dot, "border.color")).name() == invalid
                assert bool(input_dot.property("compatibleTargetState")) is True
                assert QColor(QQmlProperty.read(input_ring, "border.color")).name() == invalid
                assert float(input_ring.property("width")) > float(input_dot.property("width"))
                assert QColor(QQmlProperty.read(availability_dot, "border.color")).name() == waiting
                assert bool(availability_dot.property("compatibleTargetState")) is False
                assert QColor(QQmlProperty.read(availability_dot, "border.color")).name() != invalid
                assert QColor(output_dot.property("color")).name() == QColor("#67D487").name()
                assert QColor(QQmlProperty.read(output_dot, "border.color")).name() == data_accent
                assert QColor(QQmlProperty.read(output_dot, "border.color")).name() != invalid

                input_accessible = str(input_mouse.property("accessiblePortText"))
                output_accessible = str(output_mouse.property("accessiblePortText"))
                normal_accessible = str(normal_mouse.property("accessiblePortText"))
                assert all(
                    text in input_accessible
                    for text in ("Payload", "Input", "Type String", "Family Scalar", "Access List")
                ), input_accessible
                assert all(
                    text in output_accessible
                    for text in ("Result", "Output", "Type Integer", "Family Scalar", "Access Tree")
                ), output_accessible
                assert all(
                    text in normal_accessible
                    for text in ("Normal", "Output", "Type String", "Family Scalar", "Access Item")
                ), normal_accessible

                assert str(availability_mouse.property("inactiveTooltipText")) == (
                    "Source temporarily unavailable"
                )
                input_help = str(input_mouse.property("portHelpTooltipText"))
                availability_help = str(availability_mouse.property("portHelpTooltipText"))
                output_help = str(output_mouse.property("portHelpTooltipText"))
                assert "Accepts: String, Graph Data" in input_help
                assert "Integer cannot feed the current input" not in input_help
                assert "Integer cannot feed the current input" not in output_help
                assert "Availability: Source temporarily unavailable" in availability_help
                assert "Inactive: Driven by an upstream value" in availability_help
                assert "Availability: Driven by an upstream value" not in availability_help
                assert "Integer cannot feed the current input" not in availability_help
                edge_payload = variant_value(canvas_stub.property("edgePayload")) or []
                assert edge_payload[0]["data_type_warning_reason"] == (
                    "Integer cannot feed the current input"
                )
            finally:
                dispose_host_window(host, window)
                canvas_stub.deleteLater()
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_family_accent_binding_updates_when_graph_theme_changes(self) -> None:
        self._run_qml_probe(
            "port-family-accent-reacts-to-graph-theme",
            """
            from PyQt6.QtGui import QColor
            from PyQt6.QtQml import QQmlProperty

            GraphThemeBridge = load_module(
                "ea_node_editor.ui_qml.graph_theme_bridge",
                Path("ea_node_editor/ui_qml/graph_theme_bridge.py"),
            ).GraphThemeBridge
            graph_theme_bridge = GraphThemeBridge(theme_id="graph_stitch_dark")
            reactive_shell_context = ShellContextStub(theme_bridge, graph_theme_bridge)
            engine.rootContext().setContextProperty(
                "shellContext",
                reactive_shell_context,
            )

            payload = node_payload()
            for port in payload["ports"]:
                port.update({
                    "data_type": "COREX.DataTypes.String",
                    "data_type_label": "String",
                    "data_type_family": "scalar",
                    "data_type_family_label": "Scalar",
                    "data_type_color_token": "data.scalar",
                    "accepted_data_type_labels": ["String"],
                    "data_access": "item",
                    "flow_state": "default",
                })

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            window = attach_host_to_window(host)
            try:
                settle_events(4)
                input_dot = named_item(host, "graphNodeInputPortDot", "payload")
                initial = QColor(input_dot.property("portColor")).name()
                assert initial == QColor(graph_theme_bridge.port_kind_palette["data"]).name()
                assert QColor(QQmlProperty.read(input_dot, "border.color")).name() == initial

                graph_theme_bridge.apply_theme("graph_ember_dark")
                settle_events(5)
                updated = QColor(graph_theme_bridge.port_kind_palette["data"]).name()
                assert updated != initial
                assert QColor(input_dot.property("portColor")).name() == updated
                assert QColor(QQmlProperty.read(input_dot, "border.color")).name() == updated
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )


class ExcalidrawWebBoardPreviewPayloadTests(unittest.TestCase):
    def test_web_board_preview_ref_payload_derives_uri_from_artifact_ref(self) -> None:
        model = GraphModel()
        registry = build_default_registry()
        workspace = model.active_workspace
        preview_ref = {
            "artifact_ref": "temp://pending_excalidraw_preview",
            "mime_type": "image/png",
            "status": "ready",
        }
        node = model.add_node(
            workspace.workspace_id,
            EXCALIDRAW_BOARD_TYPE_ID,
            "Board",
            120.0,
            80.0,
            properties={
                EXCALIDRAW_STATE_PROPERTY: {
                    "type": "excalidraw",
                    "elements": [],
                    "appState": {},
                    "files": {},
                },
                EXCALIDRAW_PREVIEW_REF_PROPERTY: preview_ref,
            },
        )

        nodes_payload, _backdrops, _minimap_nodes, _edges = GraphScenePayloadBuilder().rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )

        payload = next(item for item in nodes_payload if item["node_id"] == node.node_id)
        projected_ref = payload["properties"][EXCALIDRAW_PREVIEW_REF_PROPERTY]
        self.assertEqual(projected_ref["artifact_ref"], preview_ref["artifact_ref"])
        self.assertEqual(projected_ref["uri"], preview_ref["artifact_ref"])
        self.assertEqual(
            workspace.nodes[node.node_id].properties[EXCALIDRAW_PREVIEW_REF_PROPERTY],
            preview_ref,
        )

    def test_web_board_preview_viewport_renders_exported_artifact_refs(self) -> None:
        viewport_source = (
            PROJECT_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "passive"
            / "GraphWebBoardPreviewViewport.qml"
        ).read_text(encoding="utf-8")
        surface_source = (
            PROJECT_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "passive"
            / "GraphWebBoardSurface.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("GraphMediaPanelSourceUtils.js", viewport_source)
        self.assertIn("graphNodeWebBoardExportedPreviewImage", viewport_source)
        self.assertIn("SourceUtils.previewSourceUrl(previewSourceRef)", viewport_source)
        self.assertIn("previewRef.artifact_ref", viewport_source)
        self.assertIn('root.previewMode === "image"', viewport_source)
        self.assertNotIn("WebEngine", viewport_source)
        self.assertIn('text: "Open editor to retry"', viewport_source)
        self.assertIn("cache: false", viewport_source)
        self.assertIn("snapshotCurrent", viewport_source)
        self.assertIn('visible: root.previewMode === "image"', viewport_source)
        self.assertIn("previewRef.artifact_ref", surface_source)
        self.assertIn("overlayViewportRect", surface_source)
        self.assertIn("overlayContentRect", surface_source)
        self.assertIn("embeddedInteractiveRects", surface_source)
        self.assertIn("requestSurfaceContentFullscreen", surface_source)


class FlowchartTimestampSurfaceQmlTests(PassiveGraphSurfaceHostTestBase):
    def test_graph_canvas_hosts_timestamp_calendar_editor_from_toolbar_action(self) -> None:
        self._run_qml_probe(
            "timestamp-calendar-editor-overlay-window",
            """
            from PyQt6.QtCore import QMetaObject, QPointF
            from PyQt6.QtTest import QTest

            def node_card_for(canvas_item, node_id):
                for item in named_child_items(canvas_item, "graphNodeCard"):
                    node_data = variant_value(item.property("nodeData")) or {}
                    if str(node_data.get("node_id", "")) == str(node_id):
                        return item
                raise AssertionError(f"Missing node card for {node_id!r}")

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id

            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            node_id = scene.add_node_from_type("passive.flowchart.timestamp", 120.0, 90.0)
            scene.set_node_property(node_id, "body", "Mon Jan 02 2023 03:04:05")
            scene.select_node(node_id, False)

            view = ViewportBridge()
            view.set_viewport_size(760.0, 520.0)
            view.set_view_state(1.0, 250.0, 180.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 760.0,
                    "height": 520.0,
                },
            )
            window = attach_host_to_window(canvas, width=760, height=520)
            try:
                settle_events(10)
                card = node_card_for(canvas, node_id)
                surface = card.findChild(QObject, "graphNodeFlowchartSurface")
                live_button = named_item(canvas, "graphNodeFloatingToolbarAction_timestamp_toggle_live")
                update_button = named_item(canvas, "graphNodeFloatingToolbarAction_timestamp_update_now")
                manual_button = named_item(canvas, "graphNodeFloatingToolbarAction_timestamp_edit_manual")
                overlay_layer = named_item(canvas, "graphNodeTimestampOverlayLayer")
                popover = named_item(canvas, "graphNodeTimestampDateTimePopover")

                assert surface is not None
                assert live_button is not None
                assert update_button is not None
                assert manual_button is not None
                assert overlay_layer is not None
                assert popover is not None
                assert [action["id"] for action in variant_list(surface.property("surfaceActions"))] == [
                    "timestamp_toggle_live",
                    "timestamp_update_now",
                    "timestamp_edit_manual",
                ]

                QTest.mouseMove(window, item_scene_point(card, 0.5, 0.5))
                settle_events(5)
                assert bool(live_button.property("visible")), live_button.property("visible")
                assert bool(update_button.property("visible")), update_button.property("visible")
                assert bool(manual_button.property("visible")), manual_button.property("visible")

                scene.set_node_property(node_id, "live", False)
                scene.set_node_property(node_id, "body", "Mon Jan 02 2023 03:04:05")
                settle_events(10)
                card = node_card_for(canvas, node_id)
                surface = card.findChild(QObject, "graphNodeFlowchartSurface")
                manual_button = named_item(canvas, "graphNodeFloatingToolbarAction_timestamp_edit_manual")

                QTest.mouseMove(window, item_scene_point(card, 0.5, 0.5))
                settle_events(5)
                QTest.mouseClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(manual_button),
                )
                settle_events(5)

                assert bool(surface.property("timestampManualEditorOpen")), surface.property("timestampManualEditorOpen")
                assert bool(popover.property("visible")), popover.property("visible")
                assert bool(overlay_layer.property("visible")), overlay_layer.property("visible")
                assert popover.parentItem().objectName() == "graphNodeTimestampOverlayLayer"
                assert named_item(canvas, "graphNodeTimestampCalendarGrid") is not None
                day_two = named_item(canvas, "graphNodeTimestampDayButton_2")
                assert bool(day_two.property("selected")), day_two.property("selected")

                hour_field = named_item(canvas, "graphNodeTimestampHourField")
                minute_field = named_item(canvas, "graphNodeTimestampMinuteField")
                second_field = named_item(canvas, "graphNodeTimestampSecondField")
                hour_field.setProperty("text", "6")
                minute_field.setProperty("text", "7")
                second_field.setProperty("text", "8")
                QMetaObject.invokeMethod(popover, "acceptEdit")
                settle_events(5)

                assert not bool(surface.property("timestampManualEditorOpen"))
                assert not bool(popover.property("visible"))
                assert not bool(overlay_layer.property("visible"))
                stored = model.active_workspace.nodes[node_id].properties
                assert stored["live"] is False
                assert stored["body"] == "Mon Jan 02 2023 06:07:08", stored
            finally:
                dispose_host_window(canvas, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )


class WebPageGenericSurfaceQmlTests(PassiveGraphSurfaceHostTestBase):
    def test_graph_node_host_routes_web_page_surface_without_live_webengine(self) -> None:
        self._run_qml_probe(
            "web-page-graph-surface-no-webengine",
            """
            from PyQt6.QtCore import Q_ARG
            from PyQt6.QtGui import QColor

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

            web_payload = node_payload(surface_family="web", surface_variant="page_viewer")
            web_payload["node_id"] = "node_web_page_surface"
            web_payload["type_id"] = "web.page_viewer"
            web_payload["title"] = "Web Page Viewer"
            web_payload["runtime_behavior"] = "passive"
            web_payload["width"] = 380.0
            web_payload["height"] = 240.0
            web_payload["surface_spec"] = {
                "family": "web",
                "variant": "page_viewer",
                "component_key": "web_page",
                "qml_component": "../web/WebPageHost.qml",
                "fullscreen": {
                    "supported": True,
                    "content_kind": "web_page",
                    "action_id": "fullscreen",
                    "action_label": "Fullscreen",
                    "action_icon": "fullscreen",
                    "action_kind": "web_page",
                    "requires_bridge": True
                },
                "input_capabilities": {
                    "devices": ["mouse", "touch"],
                    "events": ["press", "release", "move", "wheel", "key"],
                    "hover": True,
                    "pressure": False,
                    "gestures": ["tap", "drag", "wheel"],
                    "plugin_gestures": []
                },
                "native_overlay": {"required": False, "target": "", "owner": ""},
                "layout": {"content_region": "host", "min_body_width": 260.0, "min_body_height": 150.0, "preferred_body_height": 180.0},
                "metadata": {"web_surface": "page_viewer", "qwebchannel_allowed": False}
            }
            web_payload["properties"] = {
                "start_location": "https://example.com"
            }
            web_payload["web_page_payload"] = {
                "workspace_id": "workspace_web",
                "node_id": "node_web_page_surface",
                "type_id": "web.page_viewer",
                "content_kind": "web_page",
                "title": "Web Page Viewer",
                "surface_family": "web",
                "surface_variant": "page_viewer",
                "surface_spec": web_payload["surface_spec"],
                "start_location": "https://example.com",
                "current_location": "https://example.com",
                "navigation_decision": {
                    "allowed": True,
                    "target_url": "https://example.com",
                    "reason": "",
                    "original_location": "https://example.com",
                    "scheme": "https",
                    "origin": "https://example.com",
                    "is_local": False,
                    "qwebchannel_allowed": False
                },
                "webengine_available": False,
                "webengine_reason": "Qt WebEngine is disabled for the offscreen Qt platform.",
                "qwebchannel_allowed": False
            }

            host = create_component(graph_node_host_qml_path, {"nodeData": web_payload})
            window = attach_host_to_window(host, width=760, height=520)
            try:
                loader = host.findChild(QObject, "graphNodeSurfaceLoader")
                surface = host.findChild(QObject, "graphNodeWebPageHost")
                status = host.findChild(QObject, "graphNodeWebPageStatusPane")
                viewport_frame = surface.findChild(QObject, "webPageViewportFrame") if surface is not None else None
                toolbar = host.findChild(QObject, "webPageToolbar")
                assert loader is not None
                assert surface is not None
                assert status is not None
                assert viewport_frame is not None
                if toolbar is not None:
                    assert not bool(toolbar.property("visible"))
                assert host.findChild(QObject, "webPageAddressPopover") is None
                settle_events(6)

                assert str(loader.property("loadedSurfaceKey")) == "web_page"
                assert str(surface.property("surfaceMode")) == "graph"
                assert bool(status.property("visible"))
                assert surface.findChild(QObject, "webPageHostWebEngineView") is None
                assert QColor(viewport_frame.property("color")).name().lower() == QColor(host.property("inlineInputBackgroundColor")).name().lower()

                actions = variant_list(loader.property("surfaceActions"))
                assert [action["id"] for action in actions] == [
                    "web_page_back",
                    "web_page_forward",
                    "web_page_reload_stop",
                    "web_page_edit_address",
                    "web_page_local_html",
                    "web_page_display_mode",
                    "toggle_content_only",
                    "toggle_title",
                    "toggle_frame",
                    "fullscreen",
                    "web_page_detach",
                ], actions
                for action in actions:
                    assert action["kind"] in ("web_page", "surface"), action
                actions_by_id = {action["id"]: action for action in actions}
                assert not bool(actions_by_id["web_page_back"]["enabled"])
                assert not bool(actions_by_id["web_page_forward"]["enabled"])
                assert bool(actions_by_id["web_page_reload_stop"]["enabled"])
                assert bool(actions_by_id["web_page_edit_address"]["enabled"])
                assert bool(actions_by_id["fullscreen"]["enabled"])
                assert bool(actions_by_id["web_page_detach"]["enabled"])
                assert variant_list(loader.property("embeddedInteractiveRects")) == []

                QMetaObject.invokeMethod(
                    surface,
                    "dispatchSurfaceAction",
                    Q_ARG("QVariant", "fullscreen"),
                )
                settle_events(3)
                assert bridge.toggle_calls == ["node_web_page_surface"]

                QMetaObject.invokeMethod(
                    surface,
                    "dispatchSurfaceAction",
                    Q_ARG("QVariant", "web_page_edit_address"),
                )
                settle_events(3)
                assert bool(surface.property("addressEditorOpen"))
                assert str(surface.property("addressEditorText")) == "https://example.com"
                assert variant_list(loader.property("embeddedInteractiveRects")) == []
                QMetaObject.invokeMethod(surface, "cancelAddressEdit")
                settle_events(3)
                assert not bool(surface.property("addressEditorOpen"))
                assert variant_list(loader.property("embeddedInteractiveRects")) == []
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_graph_canvas_hosts_web_page_address_editor_as_overlay_window(self) -> None:
        self._run_qml_probe(
            "web-page-address-editor-overlay-window",
            """
            from PyQt6.QtCore import Q_ARG, QPoint, QPointF
            from PyQt6.QtTest import QTest

            def node_card_for(canvas_item, node_id):
                for item in named_child_items(canvas_item, "graphNodeCard"):
                    node_data = variant_value(item.property("nodeData")) or {}
                    if str(node_data.get("node_id", "")) == str(node_id):
                        return item
                raise AssertionError(f"Missing node card for {node_id!r}")

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id

            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            node_id = scene.add_node_from_type("web.page_viewer", 120.0, 90.0)
            scene.set_node_property(node_id, "start_location", "https://example.com")
            scene.select_node(node_id, False)

            view = ViewportBridge()
            view.set_viewport_size(760.0, 520.0)
            view.set_view_state(1.0, 250.0, 180.0)

            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 760.0,
                    "height": 520.0,
                },
            )
            window = attach_host_to_window(canvas, width=760, height=520)
            try:
                settle_events(10)
                card = node_card_for(canvas, node_id)
                surface = card.findChild(QObject, "graphNodeWebPageHost")
                loader = card.findChild(QObject, "graphNodeSurfaceLoader")
                popover = named_item(canvas, "webPageAddressPopover")
                field = named_item(canvas, "webPageAddressPopoverField")
                address_button = named_item(canvas, "graphNodeFloatingToolbarAction_web_page_edit_address")
                overlay_layer = named_item(canvas, "webPageAddressOverlayLayer")

                assert surface is not None
                assert loader is not None
                assert popover is not None
                assert field is not None
                assert address_button is not None
                assert overlay_layer is not None
                assert str(surface.property("surfaceMode")) == "graph", surface.property("surfaceMode")
                assert [action["id"] for action in variant_list(surface.property("surfaceActions"))], surface.property("surfaceActions")
                assert not bool(popover.property("visible"))
                assert not bool(overlay_layer.property("visible"))
                assert surface.findChild(QObject, "webPageAddressPopover") is None

                QTest.mouseMove(window, item_scene_point(card, 0.5, 0.5))
                settle_events(5)
                assert bool(address_button.property("visible")), address_button.property("visible")
                assert bool(surface.dispatchSurfaceAction("web_page_edit_address"))
                settle_events(5)

                assert bool(surface.property("addressEditorOpen")), {
                    "addressEditorOpen": surface.property("addressEditorOpen"),
                    "addressEditorText": surface.property("addressEditorText"),
                    "currentUrl": surface.property("currentUrl"),
                }
                assert bool(popover.property("visible")), {
                    "popoverVisible": popover.property("visible"),
                    "addressEditorOpen": surface.property("addressEditorOpen"),
                    "addressEditorText": surface.property("addressEditorText"),
                    "currentUrl": surface.property("currentUrl"),
                }
                assert bool(overlay_layer.property("visible"))
                assert popover.parentItem().objectName() == "webPageAddressOverlayLayer", popover.parentItem().objectName()
                assert str(field.property("text")) == "https://example.com", field.property("text")
                assert variant_list(loader.property("embeddedInteractiveRects")) == []

                field.setProperty("text", "example.org/docs")
                QMetaObject.invokeMethod(popover, "acceptEdit")
                settle_events(5)
                assert not bool(surface.property("addressEditorOpen"))
                assert not bool(popover.property("visible"))
                assert not bool(overlay_layer.property("visible"))
                assert str(surface.property("currentUrl")) == "https://example.org/docs"
                stored_browser_state = model.active_workspace.nodes[node_id].properties.get("browser_state", {})
                assert stored_browser_state.get("current_url") == "https://example.org/docs", {
                    "stored_browser_state": stored_browser_state,
                    "surface_graphBrowserStateSink": surface.property("graphBrowserStateSink"),
                    "card_sceneCommandBridge": canvas.property("sceneCommandBridge"),
                    "surface_currentUrl": surface.property("currentUrl"),
                    "surface_graphSurface": surface.property("graphSurface"),
                }
                scene.resize_node(node_id, 460.0, 700.0)
                settle_events(10)
                card = node_card_for(canvas, node_id)
                surface = card.findChild(QObject, "graphNodeWebPageHost")
                loader = card.findChild(QObject, "graphNodeSurfaceLoader")
                popover = named_item(canvas, "webPageAddressPopover")
                field = named_item(canvas, "webPageAddressPopoverField")
                address_button = named_item(canvas, "graphNodeFloatingToolbarAction_web_page_edit_address")
                overlay_layer = named_item(canvas, "webPageAddressOverlayLayer")
                bottom_right_handle = next(
                    handle
                    for handle in named_child_items(card, "graphNodeResizeHandle")
                    if str(handle.property("cornerRole")) == "bottomRight"
                )
                bottom_right_area = bottom_right_handle.findChild(QObject, "graphNodeResizeDragArea")
                assert surface is not None
                assert loader is not None
                assert popover is not None
                assert field is not None
                assert address_button is not None
                assert overlay_layer is not None
                assert bottom_right_area is not None
                assert str(surface.property("currentUrl")) == "https://example.org/docs", {
                    "currentUrl": surface.property("currentUrl"),
                    "addressText": surface.property("addressText"),
                    "stored": model.active_workspace.nodes[node_id].properties,
                }
                refreshed_payload = next(item for item in scene.nodes_model if item["node_id"] == node_id)
                assert refreshed_payload["web_page_payload"]["current_location"] == "https://example.org/docs", refreshed_payload["web_page_payload"]
                assert refreshed_payload["web_page_payload"]["browser_state"]["current_url"] == "https://example.org/docs", refreshed_payload["web_page_payload"]

                QTest.mouseMove(window, item_scene_point(card, 0.5, 0.5))
                settle_events(5)
                assert bool(address_button.property("visible")), address_button.property("visible")
                assert bool(surface.dispatchSurfaceAction("web_page_edit_address"))
                settle_events(5)
                assert bool(popover.property("visible")), {
                    "popoverVisible": popover.property("visible"),
                    "surfaceAddressEditorOpen": surface.property("addressEditorOpen"),
                    "overlayLayerVisible": overlay_layer.property("visible"),
                    "buttonVisible": address_button.property("visible"),
                    "currentUrl": surface.property("currentUrl"),
                }
                assert bool(overlay_layer.property("visible")), overlay_layer.property("visible")
                assert popover.parentItem().objectName() == "webPageAddressOverlayLayer", popover.parentItem().objectName()
                assert surface.findChild(QObject, "webPageAddressPopover") is None, surface.findChild(QObject, "webPageAddressPopover")
                popover_bottom = popover.mapToItem(canvas, QPointF(0.0, float(popover.property("height")))).y()
                card_top = card.mapToItem(canvas, QPointF(0.0, 0.0)).y()
                assert popover_bottom <= card_top, {
                    "popover_bottom": popover_bottom,
                    "card_top": card_top,
                    "popover_parent": popover.parentItem().objectName(),
                    "popover_height": popover.property("height"),
                }
                field.setProperty("text", "https://discard.example")
                QTest.mouseClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    QPoint(4, 4),
                )
                settle_events(5)
                assert not bool(surface.property("addressEditorOpen")), surface.property("addressEditorOpen")
                assert not bool(popover.property("visible")), popover.property("visible")
                assert not bool(overlay_layer.property("visible")), overlay_layer.property("visible")
                assert str(surface.property("currentUrl")) == "https://example.org/docs", surface.property("currentUrl")

                QTest.mouseMove(window, QPoint(740, 500))
                settle_events(5)
                QTest.mouseMove(window, item_scene_point(card, 0.05, 0.05))
                settle_events(5)
                assert bool(bottom_right_area.property("enabled")), bottom_right_area.property("enabled")
                assert not bool(card.property("surfaceInteractionLocked")), card.property("surfaceInteractionLocked")
            finally:
                dispose_host_window(canvas, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_content_fullscreen_overlay_routes_web_page_separately_from_web_editor(self) -> None:
        self._run_qml_probe(
            "web-page-fullscreen-overlay-route",
            """
            from PyQt6.QtCore import pyqtSignal

            class WebPageFullscreenBridgeStub(QObject):
                content_fullscreen_changed = pyqtSignal()

                @pyqtProperty(bool, notify=content_fullscreen_changed)
                def open(self):
                    return True

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def node_id(self):
                    return "node_web_page_fullscreen"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def workspace_id(self):
                    return "workspace_web"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def content_kind(self):
                    return "web_page"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def title(self):
                    return "Web Page Viewer"

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def media_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def viewer_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def web_editor_payload(self):
                    return {"title": "Should not route"}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def web_page_payload(self):
                    return {
                        "workspace_id": "workspace_web",
                        "node_id": "node_web_page_fullscreen",
                        "type_id": "web.page_viewer",
                        "content_kind": "web_page",
                        "title": "Web Page Viewer",
                        "surface_spec": {
                            "fullscreen": {"supported": True, "content_kind": "web_page", "requires_bridge": True},
                            "input_capabilities": {"devices": ["mouse"], "events": ["press"], "hover": True}
                        },
                        "start_location": "https://example.com",
                        "current_location": "https://example.com",
                        "navigation_decision": {
                            "allowed": True,
                            "target_url": "https://example.com",
                            "reason": "",
                            "original_location": "https://example.com",
                            "scheme": "https",
                            "origin": "https://example.com",
                            "is_local": False,
                            "qwebchannel_allowed": False
                        },
                        "webengine_available": False,
                        "webengine_reason": "Qt WebEngine is disabled for the offscreen Qt platform.",
                        "qwebchannel_allowed": False
                    }

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def tabular_payload(self):
                    return {}

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def last_error(self):
                    return ""

                @pyqtProperty(QObject, notify=content_fullscreen_changed)
                def web_surface_bridge(self):
                    return None

                @pyqtSlot()
                def request_close(self):
                    pass

            bridge = WebPageFullscreenBridgeStub()
            overlay_path = repo_root / "ea_node_editor" / "ui_qml" / "ContentFullscreenOverlay.qml"
            overlay = create_component(
                overlay_path,
                {
                    "bridgeRef": bridge,
                    "width": 960.0,
                    "height": 640.0,
                },
            )
            window = attach_host_to_window(overlay, width=960, height=640)
            try:
                web_page_host = overlay.findChild(QObject, "contentFullscreenWebPageHost")
                web_editor_host = overlay.findChild(QObject, "contentFullscreenWebEditorHost")
                status = overlay.findChild(QObject, "contentFullscreenWebPageStatusPane")
                assert web_page_host is not None
                assert web_editor_host is not None
                assert status is not None
                settle_events(6)

                assert bool(web_page_host.property("visible"))
                assert not bool(web_editor_host.property("visible"))
                assert bool(status.property("visible"))
                assert web_page_host.findChild(QObject, "webPageHostWebEngineView") is None
            finally:
                dispose_host_window(overlay, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_content_fullscreen_overlay_borrows_live_web_page_host_when_available(self) -> None:
        self._run_qml_probe(
            "web-page-fullscreen-overlay-borrows-live-host",
            """
            from PyQt6.QtCore import pyqtSignal

            live_component = QQmlComponent(engine)
            live_component.setData(
                b'''
                import QtQuick 2.15
                Item {
                    objectName: "graphNodeWebPageHost"
                    property string nodeId: "node_web_page_fullscreen"
                    property int attachCalls: 0
                    property int releaseCalls: 0
                    property int flushCalls: 0
                    property string lastTargetObjectName: ""
                    property string lastNodeId: ""

                    function hasBorrowableWebEngineForFullscreen(nodeId) {
                        return String(nodeId || "") === "node_web_page_fullscreen";
                    }

                    function attachWebEngineToFullscreen(target, nodeId) {
                        attachCalls += 1;
                        lastTargetObjectName = target ? String(target.objectName || "") : "";
                        lastNodeId = String(nodeId || "");
                        return true;
                    }

                    function releaseFullscreenWebEngine() {
                        releaseCalls += 1;
                        return true;
                    }

                    function flushBrowserState() {
                        flushCalls += 1;
                        return true;
                    }
                }
                ''',
                QUrl(),
            )
            assert live_component.status() == QQmlComponent.Status.Ready, [
                error.toString() for error in live_component.errors()
            ]
            live_host = live_component.create()
            assert live_host is not None

            class WebPageFullscreenBridgeStub(QObject):
                content_fullscreen_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self._open = False
                    self.close_calls = 0

                @pyqtProperty(bool, notify=content_fullscreen_changed)
                def open(self):
                    return self._open

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def node_id(self):
                    return "node_web_page_fullscreen"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def workspace_id(self):
                    return "workspace_web"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def content_kind(self):
                    return "web_page"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def title(self):
                    return "Web Page Viewer"

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def media_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def viewer_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def web_editor_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def web_page_payload(self):
                    return {
                        "workspace_id": "workspace_web",
                        "node_id": "node_web_page_fullscreen",
                        "type_id": "web.page_viewer",
                        "content_kind": "web_page",
                        "title": "Web Page Viewer",
                        "surface_spec": {
                            "fullscreen": {"supported": True, "content_kind": "web_page", "requires_bridge": True},
                            "input_capabilities": {"devices": ["mouse"], "events": ["press"], "hover": True}
                        },
                        "start_location": "https://example.com",
                        "current_location": "https://example.com",
                        "navigation_decision": {
                            "allowed": True,
                            "target_url": "https://example.com",
                            "reason": "",
                            "original_location": "https://example.com",
                            "scheme": "https",
                            "origin": "https://example.com",
                            "is_local": False,
                            "qwebchannel_allowed": False
                        },
                        "webengine_available": True,
                        "webengine_reason": "",
                        "qwebchannel_allowed": False
                    }

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def tabular_payload(self):
                    return {}

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def last_error(self):
                    return ""

                @pyqtProperty(QObject, notify=content_fullscreen_changed)
                def web_surface_bridge(self):
                    return None

                @pyqtSlot()
                def request_close(self):
                    self._open = False
                    self.close_calls += 1
                    self.content_fullscreen_changed.emit()

            bridge = WebPageFullscreenBridgeStub()
            overlay_path = repo_root / "ea_node_editor" / "ui_qml" / "ContentFullscreenOverlay.qml"
            overlay = create_component(
                overlay_path,
                {
                    "bridgeRef": bridge,
                    "width": 960.0,
                    "height": 640.0,
                },
            )
            live_host.setParentItem(overlay)
            window = attach_host_to_window(overlay, width=960, height=640)
            bridge._open = True
            bridge.content_fullscreen_changed.emit()
            borrowed_viewport = overlay.findChild(QObject, "contentFullscreenBorrowedWebPageViewport")
            fallback_host = overlay.findChild(QObject, "contentFullscreenWebPageHost")
            assert borrowed_viewport is not None
            assert fallback_host is not None
            settle_events(6)

            assert bool(overlay.property("webPageBorrowedActive"))
            assert bool(borrowed_viewport.property("visible"))
            assert not bool(fallback_host.property("visible"))
            assert int(live_host.property("attachCalls")) == 1
            assert str(live_host.property("lastTargetObjectName")) == "contentFullscreenBorrowedWebPageViewport"
            assert str(live_host.property("lastNodeId")) == "node_web_page_fullscreen"

            QMetaObject.invokeMethod(overlay, "requestClose")
            settle_events(3)

            assert int(live_host.property("flushCalls")) == 1
            assert int(live_host.property("releaseCalls")) == 1
            assert bridge.close_calls == 1
            """,
        )


class TabularGraphSurfaceQmlTests(PassiveGraphSurfaceHostTestBase):
    def test_tabular_input_surface_refreshes_when_canvas_item_arrives_late(self) -> None:
        self._run_qml_probe(
            "tabular-input-surface-delayed-canvas-item",
            """
            class ContentFullscreenBridgeStub(QObject):
                @pyqtSlot(str, result=bool)
                def request_toggle_for_node(self, node_id):
                    return True

                @pyqtSlot(str, "QVariantMap", result="QVariantMap")
                def export_tabular_visible_rows_for_node(self, node_id, payload):
                    return {"ok": True, "path": "C:/tmp/stations-visible.csv", "error": ""}

            class DelayedTabularCanvasItem(PassiveSurfaceCanvasItem):
                def __init__(self):
                    super().__init__()
                    self.requests = []

                @pyqtSlot("QVariantMap", "QVariantMap", result="QVariantMap")
                def describeNodeSurfaceTabularPreview(self, properties, request):
                    self.requests.append((dict(properties or {}), dict(request or {})))
                    return {
                        "state": "ready",
                        "message": "Tabular data preview is ready.",
                        "content_kind": "tabular",
                        "preview_kind": "table",
                        "source": {
                            "path": str((properties or {}).get("path", "")),
                            "resolved_path": str((properties or {}).get("path", "")),
                            "format_id": "csv",
                            "size_class": "small",
                        },
                        "selector": {
                            "selected_object": "",
                            "requires_selection": False,
                            "objects": [],
                        },
                        "metadata": {"backend": "fixture"},
                        "ref": {"resolver_id": "tabular.cache", "object_id": "table"},
                        "window": {
                            "columns": ["station", "temp"],
                            "rows": [{"station": "S0", "temp": "20.0"}],
                            "row_offset": 0,
                            "column_offset": 0,
                            "total_rows": 1,
                            "total_columns": 2,
                            "bounded": True,
                            "client_side_full_scan": False,
                            "request": dict(request or {}),
                        },
                    }

            engine.rootContext().setContextProperty("contentFullscreenBridge", ContentFullscreenBridgeStub())

            tabular_payload = node_payload()
            tabular_payload["node_id"] = "node_tabular_delayed_canvas"
            tabular_payload["type_id"] = "tabular.input"
            tabular_payload["title"] = "Tabular Data Input"
            tabular_payload["surface_spec"] = surface_spec_payload_for_values(type_id="tabular.input")
            tabular_payload["width"] = 360.0
            tabular_payload["height"] = 220.0
            tabular_payload["runtime_behavior"] = "active"
            tabular_payload["surface_metrics"] = {
                "default_width": 360.0,
                "default_height": 220.0,
                "min_width": 240.0,
                "min_height": 140.0,
                "collapsed_width": 160.0,
                "collapsed_height": 36.0,
                "header_height": 24.0,
                "header_top_margin": 4.0,
                "body_top": 30.0,
                "body_height": 158.0,
                "body_left_margin": 10.0,
                "body_right_margin": 10.0,
                "body_bottom_margin": 10.0,
                "port_top": 190.0,
                "port_height": 18.0,
                "port_center_offset": 6.0,
                "port_side_margin": 8.0,
                "port_dot_radius": 3.5,
                "resize_handle_size": 16.0,
            }
            tabular_payload["properties"] = {
                "path": "C:/tmp/stations.csv",
                "cache_policy": "app_managed_parquet",
                "selected_object": "",
            }
            tabular_payload["preview"] = {
                "state": "placeholder",
                "message": "Open fullscreen to resolve a bounded tabular preview window.",
                "content_kind": "tabular",
                "preview_kind": "",
                "source": {"path": "C:/tmp/stations.csv"},
                "selector": {},
            }
            tabular_payload["inline_properties"] = []
            tabular_payload["ports"] = []

            host = create_component(graph_node_host_qml_path, {"nodeData": tabular_payload})
            window = attach_host_to_window(host, width=640, height=420)
            try:
                surface = host.findChild(QObject, "graphNodeTabularSurface")
                assert surface is not None
                settle_events(4)
                assert str(surface.property("previewState")) == "placeholder"

                canvas_item = DelayedTabularCanvasItem()
                host.setProperty("canvasItem", canvas_item)
                settle_events(6)

                assert str(surface.property("previewState")) == "ready"
                assert str(surface.property("previewKind")) == "table"
                assert len(canvas_item.requests) >= 1
                assert canvas_item.requests[0][1]["row_limit"] == 50
                assert canvas_item.requests[0][1]["column_limit"] == 50
            finally:
                window.close()
            """,
        )

    def test_tabular_input_surface_resolves_stale_embedded_preview(self) -> None:
        self._run_qml_probe(
            "tabular-input-surface-stale-embedded-preview",
            """
            class ContentFullscreenBridgeStub(QObject):
                @pyqtSlot(str, result=bool)
                def request_toggle_for_node(self, node_id):
                    return True

                @pyqtSlot(str, "QVariantMap", result="QVariantMap")
                def export_tabular_visible_rows_for_node(self, node_id, payload):
                    return {"ok": True, "path": "C:/tmp/stations-visible.csv", "error": ""}

            class TabularCanvasItem(PassiveSurfaceCanvasItem):
                def __init__(self):
                    super().__init__()
                    self.requests = []

                @pyqtSlot("QVariantMap", "QVariantMap", result="QVariantMap")
                def describeNodeSurfaceTabularPreview(self, properties, request):
                    self.requests.append((dict(properties or {}), dict(request or {})))
                    return {
                        "state": "ready",
                        "message": "Tabular data preview is ready.",
                        "content_kind": "tabular",
                        "preview_kind": "table",
                        "source": {
                            "path": str((properties or {}).get("path", "")),
                            "resolved_path": str((properties or {}).get("path", "")),
                            "format_id": "csv",
                            "size_class": "small",
                        },
                        "selector": {
                            "selected_object": "",
                            "requires_selection": False,
                            "objects": [],
                        },
                        "metadata": {"backend": "fixture"},
                        "ref": {"resolver_id": "tabular.cache", "object_id": "table"},
                        "window": {
                            "columns": ["station", "temp"],
                            "rows": [{"station": "S0", "temp": "20.0"}],
                            "row_offset": 0,
                            "column_offset": 0,
                            "total_rows": 1,
                            "total_columns": 2,
                            "bounded": True,
                            "client_side_full_scan": False,
                            "request": dict(request or {}),
                        },
                    }

            engine.rootContext().setContextProperty("contentFullscreenBridge", ContentFullscreenBridgeStub())

            tabular_payload = node_payload()
            tabular_payload["node_id"] = "node_tabular_stale_preview"
            tabular_payload["type_id"] = "tabular.input"
            tabular_payload["title"] = "Renamed Tabular Data"
            tabular_payload["surface_spec"] = surface_spec_payload_for_values(type_id="tabular.input")
            tabular_payload["width"] = 360.0
            tabular_payload["height"] = 220.0
            tabular_payload["runtime_behavior"] = "active"
            tabular_payload["surface_metrics"] = {
                "default_width": 360.0,
                "default_height": 220.0,
                "min_width": 240.0,
                "min_height": 140.0,
                "collapsed_width": 160.0,
                "collapsed_height": 36.0,
                "header_height": 24.0,
                "header_top_margin": 4.0,
                "body_top": 30.0,
                "body_height": 158.0,
                "body_left_margin": 10.0,
                "body_right_margin": 10.0,
                "body_bottom_margin": 10.0,
                "port_top": 190.0,
                "port_height": 18.0,
                "port_center_offset": 6.0,
                "port_side_margin": 8.0,
                "port_dot_radius": 3.5,
                "resize_handle_size": 16.0,
            }
            tabular_payload["properties"] = {
                "path": "C:/tmp/stations.csv",
                "cache_policy": "app_managed_parquet",
                "selected_object": "",
            }
            tabular_payload["preview"] = {
                "state": "placeholder",
                "message": "Preview not yet resolved",
                "content_kind": "tabular",
                "preview_kind": "",
                "source": {"path": "C:/tmp/stations.csv"},
                "selector": {},
            }
            tabular_payload["inline_properties"] = []
            tabular_payload["ports"] = []

            host = create_component(graph_node_host_qml_path, {"nodeData": tabular_payload})
            window = attach_host_to_window(host, width=640, height=420)
            try:
                surface = host.findChild(QObject, "graphNodeTabularSurface")
                assert surface is not None
                settle_events(4)
                assert str(surface.property("previewState")) == "placeholder"

                canvas_item = TabularCanvasItem()
                host.setProperty("canvasItem", canvas_item)
                settle_events(6)
                state = str(surface.property("previewState"))
                kind = str(surface.property("previewKind"))
                assert state == "ready", (state, kind, canvas_item.requests)
                assert kind == "table", (state, kind, canvas_item.requests)
                assert len(canvas_item.requests) >= 1, (state, kind)
                assert canvas_item.requests[0][0]["path"] == "C:/tmp/stations.csv"
                assert canvas_item.requests[0][1]["row_limit"] == 50
                assert canvas_item.requests[0][1]["column_limit"] == 50
            finally:
                window.close()
            """,
        )

    def test_tabular_input_surface_refreshes_when_source_path_changes(self) -> None:
        self._run_qml_probe(
            "tabular-input-surface-source-path-change",
            """
            qml = '''
            import QtQuick 2.15
            import "graph/tabular" as Tabular

            Item {
                id: root
                width: 360
                height: 220
                property alias sourcePathValue: nodeProps.path
                property alias previewState: surface.previewState
                property alias previewKind: surface.previewKind
                property int requestCount: canvas.requests.length

                QtObject {
                    id: nodeProps
                    property string path: ""
                    property string cache_policy: "app_managed_parquet"
                    property string selected_object: ""
                }

                Item {
                    id: canvas
                    property var requests: []
                    function describeNodeSurfaceTabularPreview(properties, request) {
                        var path = String(properties.path || "");
                        requests = requests.concat([{"path": path, "request": request}]);
                        if (!path.length) {
                            return {
                                "state": "placeholder",
                                "message": "Choose a tabular data file to preview it here.",
                                "content_kind": "tabular",
                                "preview_kind": "",
                                "source": {"path": ""},
                                "selector": {}
                            };
                        }
                        return {
                            "state": "ready",
                            "message": "Tabular data preview is ready.",
                            "content_kind": "tabular",
                            "preview_kind": "table",
                            "source": {
                                "path": path,
                                "resolved_path": path,
                                "format_id": "tsv",
                                "size_class": "small"
                            },
                            "selector": {
                                "selected_object": "",
                                "requires_selection": false,
                                "objects": []
                            },
                            "metadata": {"backend": "fixture"},
                            "ref": {"resolver_id": "tabular.cache", "object_id": "table"},
                            "window": {
                                "columns": ["A", "B"],
                                "rows": [{"A": "1", "B": "2"}],
                                "row_offset": 0,
                                "column_offset": 0,
                                "total_rows": 1,
                                "total_columns": 2,
                                "bounded": true,
                                "client_side_full_scan": false,
                                "request": request
                            }
                        };
                    }
                }

                Item {
                    id: fakeHost
                    property var nodeData: ({
                        "node_id": "node_tabular_clipboard_source_path",
                        "properties": nodeProps
                    })
                    property Item canvasItem: canvas
                    property var surfaceLayout: ({})
                    property var surfaceMetrics: {
                        "body_left_margin": 10,
                        "body_right_margin": 10,
                        "body_top": 30,
                        "body_bottom_margin": 10,
                        "body_height": 158
                    }
                    property var surfaceFullscreenBridgeRef: null
                    property bool hasPassiveFillOverride: false
                    property bool hasPassiveBorderOverride: false
                    property bool isSelected: false
                    property color surfaceColor: "#1b1f2a"
                    property color outlineColor: "#3a4355"
                    property color themeSelectedOutlineColor: "#5da9ff"
                    property color inlineInputTextColor: "#eef3ff"
                    property color inlineDrivenTextColor: "#95a0b8"
                    property color selectedOutlineColor: "#60cdff"
                    property color warningOutlineColor: "#e8a838"
                    property real resolvedCornerRadius: 6
                    property real resolvedBorderWidth: 1
                }

                Tabular.GraphTabularPreviewSurface {
                    id: surface
                    anchors.fill: parent
                    host: fakeHost
                }
            }
            '''
            component = QQmlComponent(engine)
            component.setData(qml.encode("utf-8"), QUrl.fromLocalFile(str(components_dir / "tabular_source_probe.qml")))
            if component.status() != QQmlComponent.Status.Ready:
                raise AssertionError("\\n".join(error.toString() for error in component.errors()))
            probe = component.create()
            if probe is None:
                raise AssertionError("\\n".join(error.toString() for error in component.errors()))
            try:
                settle_events(4)
                assert str(probe.property("previewState")) == "placeholder"
                initial_requests = int(probe.property("requestCount"))

                probe.setProperty("sourcePathValue", "temp://clipboard_table/clipboard-table.tsv")
                settle_events(6)

                assert str(probe.property("previewState")) == "ready"
                assert str(probe.property("previewKind")) == "table"
                assert int(probe.property("requestCount")) > initial_requests
            finally:
                probe.deleteLater()
                app.processEvents()
            """,
        )

    def test_tabular_input_surface_renders_bounded_preview_and_fullscreen_action(self) -> None:
        self._run_qml_probe(
            "tabular-input-surface-preview-action",
            """
            from PyQt6.QtCore import Q_ARG, pyqtSignal

            class ContentFullscreenBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.toggle_calls = []
                    self.export_calls = []

                @pyqtSlot(str, result=bool)
                def request_toggle_for_node(self, node_id):
                    self.toggle_calls.append(str(node_id or ""))
                    return True

                @pyqtSlot(str, "QVariantMap", result="QVariantMap")
                def export_tabular_visible_rows_for_node(self, node_id, payload):
                    self.export_calls.append((str(node_id or ""), dict(payload or {})))
                    return {"ok": True, "path": "C:/tmp/stations-visible.csv", "error": ""}

            class TabularCanvasItem(PassiveSurfaceCanvasItem):
                def __init__(self):
                    super().__init__()
                    self.requests = []
                    self.browse_requests = []

                @pyqtSlot("QVariantMap", "QVariantMap", result="QVariantMap")
                def describeNodeSurfaceTabularPreview(self, properties, request):
                    self.requests.append((dict(properties or {}), dict(request or {})))
                    return {
                        "state": "ready",
                        "message": "Tabular data preview is ready.",
                        "content_kind": "tabular",
                        "preview_kind": "table",
                        "source": {
                            "path": str((properties or {}).get("path", "")),
                            "resolved_path": str((properties or {}).get("path", "")),
                            "format_id": "csv",
                            "size_class": "small"
                        },
                        "selector": {
                            "selected_object": "",
                            "requires_selection": False,
                            "objects": []
                        },
                        "metadata": {"backend": "fixture"},
                        "ref": {"resolver_id": "tabular.cache", "object_id": "table"},
                        "window": {
                            "columns": ["station", "temp", "count"],
                            "rows": [
                                {"station": "S0", "temp": "20.0", "count": "0"},
                                {"station": "S1", "temp": "20.1", "count": "1"}
                            ],
                            "row_offset": 0,
                            "column_offset": 0,
                            "total_rows": 120,
                            "total_columns": 3,
                            "bounded": True,
                            "client_side_full_scan": False,
                            "request": dict(request or {})
                        },
                        "request_contracts": {
                            "table_window": {
                                "slot": "request_tabular_window",
                                "bounded": True,
                                "client_side_full_scan": False
                            }
                        }
                    }

                @pyqtSlot(str, str, str, result=str)
                @pyqtSlot(str, str, str, str, result=str)
                def browseNodePropertyPath(self, node_id, key, current_path, source_mode=""):
                    self.browse_requests.append((
                        str(node_id or ""),
                        str(key or ""),
                        str(current_path or ""),
                        str(source_mode or ""),
                    ))
                    if str(source_mode or "") == "managed_copy":
                        return "temp://managed-tabular-source"
                    return "C:/tmp/updated-stations.csv"

            bridge = ContentFullscreenBridgeStub()
            engine.rootContext().setContextProperty("contentFullscreenBridge", bridge)

            tabular_payload = node_payload()
            tabular_payload["node_id"] = "node_tabular_surface"
            tabular_payload["type_id"] = "tabular.input"
            tabular_payload["title"] = "Tabular Data Input"
            tabular_payload["surface_spec"] = surface_spec_payload_for_values(type_id="tabular.input")
            tabular_payload["width"] = 360.0
            tabular_payload["height"] = 220.0
            tabular_payload["runtime_behavior"] = "active"
            tabular_payload["surface_metrics"] = {
                "default_width": 360.0,
                "default_height": 220.0,
                "min_width": 240.0,
                "min_height": 140.0,
                "collapsed_width": 160.0,
                "collapsed_height": 36.0,
                "header_height": 24.0,
                "header_top_margin": 4.0,
                "body_top": 30.0,
                "body_height": 158.0,
                "body_left_margin": 10.0,
                "body_right_margin": 10.0,
                "body_bottom_margin": 10.0,
                "port_top": 190.0,
                "port_height": 18.0,
                "port_center_offset": 6.0,
                "port_side_margin": 8.0,
                "port_dot_radius": 3.5,
                "resize_handle_size": 16.0
            }
            tabular_payload["properties"] = {
                "path": "C:/tmp/stations.csv",
                "cache_policy": "app_managed_parquet",
                "selected_object": ""
            }
            tabular_payload["inline_properties"] = []
            tabular_payload["ports"] = []

            canvas_item = TabularCanvasItem()
            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": tabular_payload,
                    "canvasItem": canvas_item,
                },
            )
            window = attach_host_to_window(host, width=640, height=420)
            try:
                loader = host.findChild(QObject, "graphNodeSurfaceLoader")
                surface = host.findChild(QObject, "graphNodeTabularSurface")
                status_summary = host.findChild(QObject, "graphNodeTabularStatusSummary")
                window_summary = host.findChild(QObject, "graphNodeTabularWindowSummary")
                grid = host.findChild(QObject, "graphNodeTabularPreviewGrid")
                table_view = host.findChild(QObject, "graphNodeTabularPreviewTableView")
                horizontal_header = host.findChild(QObject, "graphNodeTabularPreviewHorizontalHeaderView")
                vertical_header = host.findChild(QObject, "graphNodeTabularPreviewVerticalHeaderView")
                assert loader is not None
                assert surface is not None
                assert status_summary is not None
                assert window_summary is not None
                assert grid is not None
                assert table_view is not None
                assert horizontal_header is not None
                assert vertical_header is not None
                assert host.findChild(QObject, "graphNodeTabularFullscreenButton") is None

                settle_events(6)

                assert str(loader.property("loadedSurfaceKey")) == "tabular"
                assert str(surface.property("previewState")) == "ready"
                assert str(surface.property("previewKind")) == "table"
                assert bool(status_summary.property("visible"))
                assert bool(window_summary.property("visible"))
                assert float(window_summary.property("x")) == 8.0
                assert bool(grid.property("visible"))
                assert int(grid.property("rowCount")) == 2
                assert int(grid.property("columnCount")) == 3
                assert bool(table_view.property("reuseItems"))
                assert int(table_view.property("rows")) == 2
                assert int(table_view.property("columns")) == 3
                assert not bool(loader.property("blocksHostInteraction"))
                assert len(variant_list(loader.property("embeddedInteractiveRects"))) >= 1

                actions = variant_list(loader.property("surfaceActions"))
                assert [action["id"] for action in actions] == ["editSource", "exportVisibleRows", "fullscreen"], actions
                source_action = actions[0]
                assert source_action["kind"] == "surface"
                assert source_action["icon"] == "search"
                assert not bool(source_action["primary"])
                assert source_action["popover_layout"] == "source_storage"
                source_storage_actions = variant_list(source_action["popoverActions"])
                assert [action["id"] for action in source_storage_actions] == [
                    "editSourceExternalLink",
                    "editSourceManagedCopy",
                ]
                assert source_storage_actions[0]["source_mode"] == "external_link"
                assert source_storage_actions[0]["toolbar_text"] == "External"
                assert bool(source_storage_actions[0]["checked"])
                assert source_storage_actions[1]["source_mode"] == "managed_copy"
                assert source_storage_actions[1]["toolbar_text"] == "Internal"
                export_action = actions[1]
                assert export_action["kind"] == "surface"
                assert export_action["icon"] == "file-text"
                assert bool(export_action["enabled"])
                assert actions[2]["kind"] == "tabular"
                assert bool(actions[2]["enabled"])
                assert canvas_item.requests[0][1]["row_limit"] == 50
                assert canvas_item.requests[0][1]["column_limit"] == 50

                QMetaObject.invokeMethod(
                    surface,
                    "dispatchSurfaceAction",
                    Q_ARG("QVariant", "editSource"),
                )
                settle_events(3)
                assert canvas_item.browse_requests == [
                    ("node_tabular_surface", "path", "C:/tmp/stations.csv", "external_link")
                ]
                assert canvas_item.last_committed_node_id == "node_tabular_surface"
                assert canvas_item.last_committed_properties == {"path": "C:/tmp/updated-stations.csv"}
                canvas_item.browse_requests.clear()

                QMetaObject.invokeMethod(
                    surface,
                    "dispatchSurfaceAction",
                    Q_ARG("QVariant", "exportVisibleRows"),
                )
                settle_events(3)
                assert bridge.export_calls == [
                    (
                        "node_tabular_surface",
                        {
                            "preview_kind": "table",
                            "request": {"row_limit": 50, "column_limit": 50},
                        },
                    )
                ]

                QMetaObject.invokeMethod(
                    surface,
                    "dispatchSurfaceAction",
                    Q_ARG("QVariant", "editSourceManagedCopy"),
                )
                settle_events(3)
                assert canvas_item.browse_requests == [
                    ("node_tabular_surface", "path", "C:/tmp/stations.csv", "managed_copy")
                ]
                assert canvas_item.last_committed_node_id == "node_tabular_surface"
                assert canvas_item.last_committed_properties == {"path": "temp://managed-tabular-source"}

                QMetaObject.invokeMethod(
                    surface,
                    "dispatchSurfaceAction",
                    Q_ARG("QVariant", "fullscreen"),
                )
                settle_events(3)
                assert bridge.toggle_calls == ["node_tabular_surface"]
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_tabular_empty_state_omits_inline_buttons(self) -> None:
        self._run_qml_probe(
            "tabular-empty-state-no-inline-buttons",
            """
            tabular_payload = node_payload()
            tabular_payload["node_id"] = "node_tabular_empty_surface"
            tabular_payload["type_id"] = "tabular.input"
            tabular_payload["title"] = "Tabular Data Input"
            tabular_payload["surface_spec"] = surface_spec_payload_for_values(type_id="tabular.input")
            tabular_payload["width"] = 360.0
            tabular_payload["height"] = 220.0
            tabular_payload["runtime_behavior"] = "active"
            tabular_payload["surface_metrics"] = {
                "default_width": 360.0,
                "default_height": 220.0,
                "min_width": 240.0,
                "min_height": 140.0,
                "collapsed_width": 160.0,
                "collapsed_height": 36.0,
                "header_height": 24.0,
                "header_top_margin": 4.0,
                "body_top": 30.0,
                "body_height": 158.0,
                "body_left_margin": 10.0,
                "body_right_margin": 10.0,
                "body_bottom_margin": 10.0,
                "port_top": 190.0,
                "port_height": 18.0,
                "port_center_offset": 6.0,
                "port_side_margin": 8.0,
                "port_dot_radius": 3.5,
                "resize_handle_size": 16.0
            }
            tabular_payload["properties"] = {
                "path": "",
                "cache_policy": "app_managed_parquet",
                "selected_object": ""
            }
            tabular_payload["inline_properties"] = []
            tabular_payload["ports"] = []

            host = create_component(graph_node_host_qml_path, {"nodeData": tabular_payload})
            window = attach_host_to_window(host, width=640, height=420)
            try:
                loader = host.findChild(QObject, "graphNodeSurfaceLoader")
                surface = host.findChild(QObject, "graphNodeTabularSurface")
                status_summary = host.findChild(QObject, "graphNodeTabularStatusSummary")
                status_text = host.findChild(QObject, "graphNodeTabularStatusText")
                window_summary = host.findChild(QObject, "graphNodeTabularWindowSummary")
                placeholder = host.findChild(QObject, "graphNodeTabularPreviewPlaceholder")
                grid = host.findChild(QObject, "graphNodeTabularPreviewGrid")
                empty_cta = host.findChild(QObject, "graphNodeTabularEmptyStateAction")

                assert loader is not None
                assert surface is not None
                assert status_summary is not None
                assert status_text is not None
                assert window_summary is not None
                assert placeholder is not None
                assert grid is not None
                assert host.findChild(QObject, "graphNodeTabularFullscreenButton") is None
                settle_events(6)

                assert str(loader.property("loadedSurfaceKey")) == "tabular"
                assert str(surface.property("previewState")) == "placeholder"
                assert not bool(status_summary.property("visible"))
                assert not bool(status_text.property("visible"))
                assert str(status_text.property("text")) == ""
                assert not bool(window_summary.property("visible"))
                assert str(window_summary.property("text")) == ""
                assert bool(placeholder.property("visible"))
                assert not bool(grid.property("visible"))
                assert int(grid.property("rowCount")) == 0
                assert int(grid.property("columnCount")) == 0
                assert empty_cta is None

                actions = variant_list(loader.property("surfaceActions"))
                assert [action["id"] for action in actions] == ["editSource", "exportVisibleRows", "fullscreen"], actions
                assert bool(actions[0]["enabled"])
                assert bool(actions[0]["primary"])
                assert actions[0]["popover_layout"] == "source_storage"
                assert not bool(actions[1]["enabled"])
                assert not bool(actions[2]["enabled"])
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_tabular_fullscreen_surface_requests_bounded_windows_and_preserves_overlay_close_keys(self) -> None:
        self._run_qml_probe(
            "tabular-fullscreen-window-requests",
            """
            from PyQt6.QtCore import Q_ARG, pyqtSignal

            class TabularFullscreenBridgeStub(QObject):
                content_fullscreen_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self.window_requests = []
                    self.export_requests = []
                    self.close_calls = 0

                @pyqtProperty(bool, notify=content_fullscreen_changed)
                def open(self):
                    return True

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def node_id(self):
                    return "node_tabular_fullscreen"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def workspace_id(self):
                    return "workspace_tabular"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def content_kind(self):
                    return "tabular"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def title(self):
                    return "Tabular Data Input"

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def media_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def viewer_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def web_editor_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def tabular_payload(self):
                    return {
                        "workspace_id": "workspace_tabular",
                        "node_id": "node_tabular_fullscreen",
                        "type_id": "tabular.input",
                        "title": "Tabular Data Input",
                        "surface_spec": {
                            "fullscreen": {
                                "supported": True,
                                "content_kind": "tabular",
                                "action_kind": "tabular",
                                "requires_bridge": True
                            },
                            "input_capabilities": {
                                "devices": ["mouse", "touch"],
                                "events": ["press", "release", "move", "wheel", "key"],
                                "hover": True,
                                "pressure": False,
                                "gestures": ["tap", "drag", "wheel"],
                                "plugin_gestures": []
                            }
                        },
                        "properties": {"path": "C:/tmp/stations.csv"},
                        "preview": self._preview(0, 0)
                    }

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def last_error(self):
                    return ""

                @pyqtProperty(QObject, notify=content_fullscreen_changed)
                def web_surface_bridge(self):
                    return None

                def _preview(self, row_offset, column_offset):
                    columns = ["station", "temp", "count"][int(column_offset):int(column_offset) + 3]
                    if not columns:
                        columns = ["station", "temp", "count"]
                    rows = []
                    for index in range(2):
                        row_index = int(row_offset) + index
                        rows.append({
                            "station": f"S{row_index}",
                            "temp": f"{20 + row_index / 10:.1f}",
                            "count": str(row_index)
                        })
                    return {
                        "state": "ready",
                        "message": "Tabular data preview is ready.",
                        "content_kind": "tabular",
                        "preview_kind": "table",
                        "source": {"path": "C:/tmp/stations.csv", "resolved_path": "C:/tmp/stations.csv", "format_id": "csv"},
                        "selector": {"selected_object": "", "requires_selection": False, "objects": []},
                        "metadata": {"backend": "fixture"},
                        "ref": {"resolver_id": "tabular.cache", "object_id": "table"},
                        "schema": {"columns": [{"name": "station", "dtype": "str"}, {"name": "temp", "dtype": "float64"}]},
                        "window": {
                            "columns": columns,
                            "rows": rows,
                            "row_offset": int(row_offset),
                            "column_offset": int(column_offset),
                            "total_rows": 120,
                            "total_columns": 3,
                            "bounded": True,
                            "client_side_full_scan": False,
                            "request": {
                                "row_offset": int(row_offset),
                                "row_limit": 50,
                                "column_offset": int(column_offset),
                                "column_limit": 50
                            }
                        }
                    }

                @pyqtSlot("QVariantMap", result="QVariantMap")
                def request_tabular_window(self, request):
                    payload = dict(request or {})
                    self.window_requests.append(payload)
                    preview = self._preview(payload.get("row_offset", 0), payload.get("column_offset", 0))
                    preview["window"]["request"].update(payload)
                    return preview

                @pyqtSlot("QVariantMap", result="QVariantMap")
                def export_tabular_visible_rows(self, payload):
                    self.export_requests.append(dict(payload or {}))
                    return {"ok": True, "path": "C:/tmp/stations-visible.csv", "error": ""}

                @pyqtSlot()
                def request_close(self):
                    self.close_calls += 1

            bridge = TabularFullscreenBridgeStub()
            overlay_path = repo_root / "ea_node_editor" / "ui_qml" / "ContentFullscreenOverlay.qml"
            overlay = create_component(
                overlay_path,
                {
                    "bridgeRef": bridge,
                    "width": 960.0,
                    "height": 640.0,
                },
            )
            window = attach_host_to_window(overlay, width=960, height=640)
            try:
                surface = overlay.findChild(QObject, "contentFullscreenTabularSurface")
                grid = overlay.findChild(QObject, "contentFullscreenTabularGrid")
                table_view = overlay.findChild(QObject, "contentFullscreenTabularTableView")
                horizontal_header = overlay.findChild(QObject, "contentFullscreenTabularHorizontalHeaderView")
                vertical_header = overlay.findChild(QObject, "contentFullscreenTabularVerticalHeaderView")
                sidebar = overlay.findChild(QObject, "contentFullscreenTabularMetadataSidebar")
                assert surface is not None
                assert grid is not None
                assert table_view is not None
                assert horizontal_header is not None
                assert vertical_header is not None
                assert sidebar is not None
                settle_events(6)

                assert bool(surface.property("ready"))
                assert str(surface.property("previewKind")) == "table"
                assert int(grid.property("rowCount")) == 2
                assert int(grid.property("columnCount")) == 3
                assert int(table_view.property("rows")) == 2
                assert int(table_view.property("columns")) == 3

                QMetaObject.invokeMethod(surface, "requestNextRows")
                settle_events(3)
                assert bridge.window_requests[-1]["row_offset"] == 50
                assert bridge.window_requests[-1]["row_limit"] == 50
                assert bridge.window_requests[-1]["column_limit"] == 50
                assert int(surface.property("rowOffset")) == 50
                assert int(grid.property("rowCount")) == 2

                search_field = overlay.findChild(QObject, "contentFullscreenTabularSearchField")
                assert search_field is not None
                search_field.setProperty("text", "S61")
                settle_events(2)
                QMetaObject.invokeMethod(surface, "applyQuery")
                settle_events(3)
                assert bridge.window_requests[-1]["search"] == "S61"

                export_button = overlay.findChild(QObject, "contentFullscreenTabularExportButton")
                assert export_button is not None
                assert bool(export_button.property("enabled"))
                QMetaObject.invokeMethod(surface, "exportVisibleRows")
                settle_events(3)
                assert bridge.export_requests[-1]["preview_kind"] == "table"
                assert bridge.export_requests[-1]["request"]["search"] == "S61"
                assert bridge.export_requests[-1]["request"]["row_offset"] == 50

                app.sendEvent(
                    overlay,
                    QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F11, Qt.KeyboardModifier.NoModifier),
                )
                app.sendEvent(
                    overlay,
                    QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_F11, Qt.KeyboardModifier.NoModifier),
                )
                settle_events(3)
                assert bridge.close_calls == 1
            finally:
                dispose_host_window(overlay, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_tabular_fullscreen_surface_requests_array_slices_and_populates_table_model(self) -> None:
        self._run_qml_probe(
            "tabular-fullscreen-array-slice-requests",
            """
            from PyQt6.QtCore import pyqtSignal

            class TabularArrayFullscreenBridgeStub(QObject):
                content_fullscreen_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self.slice_requests = []

                @pyqtProperty(bool, notify=content_fullscreen_changed)
                def open(self):
                    return True

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def node_id(self):
                    return "node_tabular_array_fullscreen"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def workspace_id(self):
                    return "workspace_tabular"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def content_kind(self):
                    return "tabular"

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def title(self):
                    return "Tabular Data Input"

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def media_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def viewer_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def web_editor_payload(self):
                    return {}

                @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
                def tabular_payload(self):
                    return {
                        "workspace_id": "workspace_tabular",
                        "node_id": "node_tabular_array_fullscreen",
                        "type_id": "tabular.input",
                        "title": "Tabular Data Input",
                        "surface_spec": {
                            "fullscreen": {
                                "supported": True,
                                "content_kind": "tabular",
                                "action_kind": "tabular",
                                "requires_bridge": True
                            },
                            "input_capabilities": {
                                "devices": ["mouse", "touch"],
                                "events": ["press", "release", "move", "wheel", "key"],
                                "hover": True,
                                "pressure": False,
                                "gestures": ["tap", "drag", "wheel"],
                                "plugin_gestures": []
                            }
                        },
                        "properties": {"path": "C:/tmp/array.npy"},
                        "preview": self._preview(0, 0)
                    }

                @pyqtProperty(str, notify=content_fullscreen_changed)
                def last_error(self):
                    return ""

                @pyqtProperty(QObject, notify=content_fullscreen_changed)
                def web_surface_bridge(self):
                    return None

                def _preview(self, row_offset, column_offset):
                    row_offset = int(row_offset)
                    column_offset = int(column_offset)
                    return {
                        "state": "ready",
                        "message": "Dense array preview is ready.",
                        "content_kind": "tabular",
                        "preview_kind": "array",
                        "source": {"path": "C:/tmp/array.npy", "resolved_path": "C:/tmp/array.npy", "format_id": "npy"},
                        "selector": {"selected_object": "", "requires_selection": False, "objects": []},
                        "metadata": {"backend": "fixture"},
                        "ref": {"resolver_id": "tabular.cache", "object_id": "array"},
                        "array": {"shape": [120, 80], "dtype": "float64", "object_id": "array"},
                        "slice_2d": {
                            "values": [
                                [row_offset + column_offset, row_offset + column_offset + 1, row_offset + column_offset + 2],
                                [row_offset + column_offset + 3, row_offset + column_offset + 4, row_offset + column_offset + 5]
                            ],
                            "row_offset": row_offset,
                            "column_offset": column_offset,
                            "shape": [120, 80],
                            "bounded": True,
                            "client_side_full_scan": False,
                            "request": {
                                "row_offset": row_offset,
                                "row_limit": 50,
                                "column_offset": column_offset,
                                "column_limit": 50
                            }
                        }
                    }

                @pyqtSlot("QVariantMap", result="QVariantMap")
                def request_tabular_slice_2d(self, request):
                    payload = dict(request or {})
                    self.slice_requests.append(payload)
                    return self._preview(payload.get("row_offset", 0), payload.get("column_offset", 0))

                @pyqtSlot()
                def request_close(self):
                    pass

            bridge = TabularArrayFullscreenBridgeStub()
            overlay_path = repo_root / "ea_node_editor" / "ui_qml" / "ContentFullscreenOverlay.qml"
            overlay = create_component(
                overlay_path,
                {
                    "bridgeRef": bridge,
                    "width": 960.0,
                    "height": 640.0,
                },
            )
            window = attach_host_to_window(overlay, width=960, height=640)
            try:
                surface = overlay.findChild(QObject, "contentFullscreenTabularSurface")
                grid = overlay.findChild(QObject, "contentFullscreenTabularGrid")
                table_view = overlay.findChild(QObject, "contentFullscreenTabularTableView")
                array_controls = overlay.findChild(QObject, "contentFullscreenTabularArraySliceControls")
                sort_combo = overlay.findChild(QObject, "contentFullscreenTabularSortColumnCombo")
                sort_button = overlay.findChild(QObject, "contentFullscreenTabularSortDirectionButton")
                assert surface is not None
                assert grid is not None
                assert table_view is not None
                assert array_controls is not None
                assert sort_combo is not None
                assert sort_button is not None
                settle_events(6)

                assert str(surface.property("previewKind")) == "array"
                assert bool(surface.property("arrayMode"))
                assert not bool(surface.property("tableMode"))
                assert bool(array_controls.property("visible"))
                assert not bool(sort_combo.property("enabled"))
                assert not bool(sort_button.property("enabled"))
                assert int(grid.property("rowCount")) == 2
                assert int(grid.property("columnCount")) == 3
                assert int(table_view.property("rows")) == 2
                assert int(table_view.property("columns")) == 3

                QMetaObject.invokeMethod(surface, "requestNextRows")
                settle_events(3)
                assert bridge.slice_requests[-1]["row_offset"] == 50

                QMetaObject.invokeMethod(surface, "requestNextColumns")
                settle_events(3)
                assert bridge.slice_requests[-1]["column_offset"] == 50
            finally:
                dispose_host_window(overlay, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )


if __name__ == "__main__":
    unittest.main()
