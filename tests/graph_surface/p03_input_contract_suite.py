from __future__ import annotations

import unittest
from pathlib import Path

import pytest

from tests.graph_surface.environment import GraphSurfaceInputContractTestBase

# GraphSurfaceInputContractTests remains covered in tests.graph_surface; this entrypoint stays packet-focused.
pytestmark = pytest.mark.xdist_group("p03_graph_surface")
REPO_ROOT = Path(__file__).resolve().parents[2]


class GraphSurfaceDefaultPropertyContractTests(GraphSurfaceInputContractTestBase):
    def test_supported_default_editors_register_controls_and_unknown_editors_keep_plain_grips(self) -> None:
        self._run_qml_probe(
            "default-property-editor-kind-contract",
            """
            from PyQt6.QtGui import QColor
            from PyQt6.QtQml import QQmlProperty

            editor_facts = [
                ("slider", "float", 0.5, {"minimum": 0.0, "maximum": 1.0, "step": 0.1}),
                ("toggle", "bool", False, {}),
                ("text", "str", "hello", {}),
                ("number", "int", 2, {}),
                ("enum", "str", "a", {"enum_values": ["a", "b"]}),
                ("path", "path", "C:/work", {"file_filter": "All files (*)"}),
                ("color", "str", "#67D487", {}),
                ("textarea", "str", "line one\\nline two", {}),
            ]
            ports = []
            for row_index, (editor_kind, value_type, value, metadata) in enumerate(editor_facts):
                key = "default_" + editor_kind
                descriptor = {
                    "key": key,
                    "label": editor_kind.title(),
                    "type": value_type,
                    "value": value,
                    "enum_values": [],
                    "minimum": None,
                    "maximum": None,
                    "step": None,
                    "inline_editor": editor_kind,
                    "file_filter": "",
                    "overridden_by_input": False,
                }
                descriptor.update(metadata)
                ports.append({
                    "key": key,
                    "label": editor_kind.title(),
                    "direction": "in",
                    "kind": "data",
                    "data_type": value_type,
                    "connected": False,
                    "flow_state": "default",
                    "layout_row": row_index,
                    "default_property": descriptor,
                })
            for offset, editor_kind in enumerate(("", "unsupported")):
                key = "plain_" + (editor_kind or "blank")
                ports.append({
                    "key": key,
                    "label": key,
                    "direction": "in",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                    "flow_state": "default",
                    "layout_row": len(editor_facts) + offset,
                    "default_property": {
                        "key": key,
                        "label": key,
                        "type": "str",
                        "value": "saved",
                        "enum_values": [],
                        "minimum": None,
                        "maximum": None,
                        "step": None,
                        "inline_editor": editor_kind,
                        "file_filter": "",
                        "overridden_by_input": False,
                    },
                })

            payload = node_payload()
            payload["height"] = 640.0
            payload["ports"] = ports
            payload["inline_properties"] = []
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            ports_layer = host.findChild(QObject, "graphNodePortsLayer")

            for editor_kind, _value_type, _value, _metadata in editor_facts:
                row = named_item(host, "graphNodeInputPortRow", "default_" + editor_kind)
                assert bool(row.property("defaultEditorVisible")) is True, editor_kind
            for key in ("plain_blank", "plain_unsupported"):
                row = named_item(host, "graphNodeInputPortRow", key)
                dot = named_item(host, "graphNodeInputPortDot", key)
                assert bool(row.property("defaultEditorVisible")) is False, key
                assert QColor(QQmlProperty.read(dot, "border.color")).name() == QColor("#67D487").name()

            editor_rects = variant_list(ports_layer.property("embeddedInteractiveRects"))
            assert len(editor_rects) == len(editor_facts), editor_rects
            textarea_row = named_item(host, "graphNodeInputPortRow", "default_textarea")
            text_row = named_item(host, "graphNodeInputPortRow", "default_text")
            assert float(textarea_row.height()) > float(text_row.height())
            host.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_node_host_renders_unwired_default_property_editor_without_padlock(self) -> None:
        self._run_qml_probe(
            "unwired-default-property-editor-contract",
            """
            payload = node_payload()
            payload["ports"] = [
                {
                    "key": "message",
                    "label": "Message",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                    "flow_state": "default",
                    "default_property": {
                        "key": "message",
                        "label": "Message",
                        "type": "str",
                        "value": "default text",
                        "enum_values": [],
                        "minimum": None,
                        "maximum": None,
                        "step": None,
                        "inline_editor": "text",
                        "file_filter": "",
                        "overridden_by_input": False,
                    },
                },
            ]
            payload["inline_properties"] = []
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            row = named_item(host, "graphNodeInputPortRow", "message")
            editor = named_item(host, "graphNodeInputDefaultProperty", "message")
            label = named_item(host, "graphNodeInputPortLabel", "message")
            padlock = named_item(host, "graphNodeInputPortPadlock", "message")
            ports_layer = host.findChild(QObject, "graphNodePortsLayer")
            assert bool(row.property("defaultEditorVisible")) is True
            assert editor is not None
            assert bool(label.property("visible")) is False
            assert bool(padlock.property("visible")) is False
            editor_rects = variant_list(ports_layer.property("embeddedInteractiveRects"))
            assert len(editor_rects) == 1, editor_rects
            assert float(editor_rects[0]["width"]) > 0
            assert float(editor_rects[0]["height"]) > 0
            host.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_enabled_input_override_keeps_disabled_default_editor_and_socket_usable(self) -> None:
        self._run_qml_probe(
            "overridden-default-property-contract",
            """
            payload = node_payload()
            payload["ports"] = [{
                "key": "message",
                "label": "Message",
                "direction": "in",
                "kind": "data",
                "data_type": "str",
                "connected": True,
                "flow_state": "active",
                "default_property": {
                    "key": "message",
                    "label": "Message",
                    "type": "str",
                    "value": "saved default",
                    "enum_values": [],
                    "minimum": None,
                    "maximum": None,
                    "step": None,
                    "inline_editor": "text",
                    "file_filter": "",
                    "overridden_by_input": True,
                },
            }]
            payload["inline_properties"] = []
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            row = named_item(host, "graphNodeInputPortRow", "message")
            editor = named_item(host, "graphNodeInputDefaultProperty", "message")
            value_editor = named_item(host, "graphNodeInlineValueEditor", "message")
            label = named_item(host, "graphNodeInputPortLabel", "message")
            padlock = named_item(host, "graphNodeInputPortPadlock", "message")
            input_dot = named_item(host, "graphNodeInputPortDot", "message")
            input_mouse = named_item(host, "graphNodeInputPortMouseArea", "message")
            ports_layer = host.findChild(QObject, "graphNodePortsLayer")
            assert bool(row.property("defaultEditorVisible")) is True
            assert bool(editor.property("visible")) is True
            assert bool(value_editor.property("visible")) is True
            assert bool(value_editor.property("enabled")) is False
            assert str(value_editor.property("text")) == "saved default"
            assert bool(label.property("visible")) is False
            assert bool(padlock.property("visible")) is False
            assert bool(input_dot.property("lockedState")) is False
            assert bool(input_dot.property("interactionBlockedState")) is False
            assert input_mouse.property("cursorShape") == Qt.CursorShape.PointingHandCursor
            assert variant_list(ports_layer.property("embeddedInteractiveRects")) == []
            host.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )


class GraphSurfaceFolderExplorerBridgeContractTests(unittest.TestCase):
    def test_node_surface_bridge_exposes_folder_explorer_action_routing_without_final_surface(self) -> None:
        components = REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph_canvas"
        surface_bridge = (components / "GraphCanvasNodeSurfaceBridge.qml").read_text(encoding="utf-8")
        action_router = (components / "GraphCanvasActionRouter.qml").read_text(encoding="utf-8")

        self.assertIn("function requestFolderExplorerAction(nodeId, command, payload)", surface_bridge)
        self.assertIn("root.prepareNodeSurfaceControlInteraction(normalizedNodeId);", surface_bridge)
        self.assertIn("requestPayload.node_id = normalizedNodeId;", surface_bridge)
        self.assertIn("router.requestFolderExplorerAction(root._folderExplorerActionId(command), requestPayload)", surface_bridge)
        self.assertIn("function folderExplorerActionId(key)", action_router)
        self.assertIn("function requestFolderExplorerAction(actionId, payload)", action_router)
        self.assertIn("request_folder_explorer_action", action_router)


class GraphSurfaceWebBoardLoaderContractTests(GraphSurfaceInputContractTestBase):
    def test_surface_loader_routes_excalidraw_web_board_to_passive_web_surface(self) -> None:
        self._run_qml_probe(
            "surface-loader-excalidraw-web-board",
            """

            payload = node_payload("web", "excalidraw_board")
            payload["node_id"] = "excalidraw_surface_loader_test"
            payload["type_id"] = "excalidraw.board"
            payload["title"] = "Architecture sketch"
            payload["runtime_behavior"] = "passive"
            payload["width"] = 300.0
            payload["height"] = 178.0
            payload["inline_properties"] = []
            payload["surface_metrics"].update({
                "body_left_margin": 10.0,
                "body_right_margin": 10.0,
                "body_top": 32.0,
                "body_height": 132.0,
                "body_bottom_margin": 12.0,
                "port_top": 166.0,
                "port_height": 0.0,
                "port_center_offset": 0.0,
            })
            payload["properties"] = {
                "excalidraw_state": {
                    "type": "excalidraw",
                    "appState": {"name": "Board from metadata"},
                    "elements": [
                        {"id": "rect-1", "type": "rectangle"},
                        {"id": "deleted-1", "type": "ellipse", "isDeleted": True},
                        {"id": "arrow-1", "type": "arrow"},
                    ],
                    "files": {"asset-a": {"mimeType": "image/png"}},
                },
                "excalidraw_preview_ref": {"status": "missing"},
            }

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            settle_events(4)

            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            surface = host.findChild(QObject, "graphNodeWebBoardSurface")
            viewport = host.findChild(QObject, "graphNodeWebBoardPreviewViewport")
            fallback = host.findChild(QObject, "graphNodeWebBoardSnapshotState")
            fullscreen_button = host.findChild(QObject, "graphNodeWebBoardFullscreenButton")

            assert loader is not None
            assert surface is not None
            assert viewport is not None
            assert fallback is not None
            assert fullscreen_button is not None
            assert bool(loader.property("surfaceLoaded")) is True
            assert str(loader.property("loadedSurfaceKey")) == "web_excalidraw_board"
            assert str(surface.property("boardTitle")) == "Board from metadata"
            assert int(surface.property("boardElementCount")) == 2
            assert int(surface.property("boardFileCount")) == 1
            assert str(surface.property("previewMode")) == "error"
            assert host.findChild(QObject, "graphNodeWebBoardWebEngineView") is None
            assert bool(fallback.property("visible")) is True
            assert str(viewport.property("previewImageSource")) == ""

            actions = variant_list(loader.property("surfaceActions"))
            assert len(actions) == 1
            assert actions[0]["id"] == "fullscreen"
            assert actions[0]["kind"] == "web_board"
            assert actions[0]["enabled"] is False

            embedded_rects = variant_list(loader.property("embeddedInteractiveRects"))
            assert len(embedded_rects) == 2
            assert rect_field(embedded_rects[0], "x") > 240.0
            assert rect_field(embedded_rects[0], "y") >= 38.0
            assert rect_field(embedded_rects[0], "width") >= 24.0
            assert rect_field(embedded_rects[0], "height") >= 24.0
            assert bool(loader.property("blocksHostInteraction")) is False
            assert bool(host.property("surfaceInteractionLocked")) is False
            assert bool(host.dispatchSurfaceAction("fullscreen")) is False

            host.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )


class GraphSurfaceWebPageLoaderContractTests(GraphSurfaceInputContractTestBase):
    def test_surface_loader_routes_web_page_viewer_to_live_canvas_surface(self) -> None:
        self._run_qml_probe(
            "surface-loader-web-page-canvas-live",
            """
            from PyQt6.QtCore import QPointF

            web_page_payload = {
                "workspace_id": "ws",
                "node_id": "web_page_surface_loader_test",
                "type_id": "web.page_viewer",
                "content_kind": "web_page",
                "title": "Docs Portal",
                "display_name": "Web Page Viewer",
                "surface_family": "web",
                "surface_variant": "page_viewer",
                "start_location": "https://example.com/start",
                "current_location": "",
                "persist_browser_state": True,
                "browser_state": {},
                "navigation_decision": {
                    "allowed": True,
                    "target_url": "https://example.com/start",
                    "reason": "",
                    "origin": "https://example.com",
                    "scheme": "https",
                    "is_local": False,
                    "qwebchannel_allowed": False,
                },
                "webengine_available": False,
                "webengine_reason": "WebEngine unavailable in headless probe",
                "qwebchannel_allowed": False,
            }

            payload = node_payload("web", "page_viewer")
            payload["node_id"] = "web_page_surface_loader_test"
            payload["type_id"] = "web.page_viewer"
            payload["title"] = "Docs Portal"
            payload["runtime_behavior"] = "passive"
            payload["width"] = 360.0
            payload["height"] = 300.0
            payload["selected"] = True
            payload["inline_properties"] = []
            payload["surface_metrics"].update({
                "default_width": 360.0,
                "default_height": 300.0,
                "body_left_margin": 8.0,
                "body_right_margin": 8.0,
                "body_top": 30.0,
                "body_height": 258.0,
                "port_top": 290.0,
                "port_height": 0.0,
                "port_center_offset": 0.0,
            })
            payload["properties"] = {
                "start_location": "https://example.com/start",
                "browser_state": {},
            }
            payload["web_page_payload"] = web_page_payload

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            window = attach_host_to_window(host, 480, 380)
            settle_events(8)

            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            web_host = host.findChild(QObject, "graphNodeWebPageHost")
            toolbar = host.findChild(QObject, "webPageToolbar")
            status_pane = host.findChild(QObject, "graphNodeWebPageStatusPane")
            viewport_frame = web_host.findChild(QObject, "webPageViewportFrame") if web_host is not None else None

            assert loader is not None
            assert web_host is not None
            assert status_pane is not None
            assert viewport_frame is not None
            assert bool(loader.property("surfaceLoaded")) is True
            assert str(loader.property("loadedSurfaceKey")) == "web_page"
            assert payload["surface_spec"]["layout"]["content_region"] == "body"
            assert str(loader.property("contentRegion")) == "body"

            metrics = variant_value(host.property("surfaceMetrics"))
            web_host_top_left = web_host.mapToItem(host, QPointF(0.0, 0.0))
            viewport_top_left = viewport_frame.mapToItem(host, QPointF(0.0, 0.0))
            assert abs(float(web_host_top_left.y()) - float(metrics["body_top"])) < 0.5, (
                float(web_host_top_left.y()),
                metrics,
            )
            assert float(viewport_top_left.y()) > float(web_host_top_left.y()), (
                float(viewport_top_left.y()),
                float(web_host_top_left.y()),
            )

            # Canvas no longer hard-blocks the live browser, and the old
            # static "graph_preview" placeholder state is gone for good.
            assert bool(web_host.property("graphSurface")) is True
            assert str(web_host.property("statusState")) != "graph_preview"
            assert str(web_host.property("statusState")) == "webengine_unavailable"
            assert bool(web_host.property("liveBrowserAllowed")) is False
            assert bool(web_host.property("shouldLoadWebEngine")) is False
            assert bool(status_pane.property("visible")) is True
            assert str(status_pane.property("state")) == "webengine_unavailable"

            # Graph mode uses the node floating toolbar instead of an embedded
            # full-width browser toolbar under the title.
            if toolbar is not None:
                assert not bool(toolbar.property("visible")), toolbar.property("visible")
            action_ids = [action["id"] for action in variant_list(loader.property("surfaceActions"))]
            assert action_ids == [
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
            ], action_ids
            for action in variant_list(loader.property("surfaceActions")):
                assert action["kind"] in ("web_page", "surface"), action
            embedded_rects = variant_list(loader.property("embeddedInteractiveRects"))
            assert embedded_rects == [], embedded_rects
            assert bool(loader.property("blocksHostInteraction")) is False
            assert bool(host.property("surfaceInteractionLocked")) is False

            from PyQt6.QtCore import Q_ARG, QMetaObject
            QMetaObject.invokeMethod(
                web_host,
                "dispatchSurfaceAction",
                Q_ARG("QVariant", "web_page_edit_address"),
            )
            settle_events(3)
            assert bool(web_host.property("addressEditorOpen")) is True
            assert str(web_host.property("addressEditorText")) == "https://example.com/start"
            assert variant_list(loader.property("embeddedInteractiveRects")) == []

            QMetaObject.invokeMethod(
                web_host,
                "acceptAddressEdit",
                Q_ARG("QVariant", "example.org/docs"),
            )
            settle_events(3)
            assert bool(web_host.property("addressEditorOpen")) is False
            assert str(web_host.property("currentUrl")) == "https://example.org/docs", web_host.property("currentUrl")
            assert variant_list(loader.property("embeddedInteractiveRects")) == [], variant_list(loader.property("embeddedInteractiveRects"))

            QMetaObject.invokeMethod(
                web_host,
                "dispatchSurfaceAction",
                Q_ARG("QVariant", "web_page_edit_address"),
            )
            settle_events(3)
            assert bool(web_host.property("addressEditorOpen")) is True
            QMetaObject.invokeMethod(web_host, "cancelAddressEdit")
            settle_events(3)
            assert bool(web_host.property("addressEditorOpen")) is False
            assert str(web_host.property("currentUrl")) == "https://example.org/docs", web_host.property("currentUrl")

            QMetaObject.invokeMethod(
                web_host,
                "dispatchSurfaceAction",
                Q_ARG("QVariant", "web_page_edit_address"),
            )
            settle_events(3)
            assert bool(web_host.property("addressEditorOpen")) is True
            QMetaObject.invokeMethod(
                web_host,
                "commitInlineEditFromExternalInteraction",
                Q_ARG("QVariant", 1.0),
                Q_ARG("QVariant", 1.0),
            )
            settle_events(3)
            assert bool(web_host.property("addressEditorOpen")) is False
            assert str(web_host.property("currentUrl")) == "https://example.org/docs", web_host.property("currentUrl")

            # Canvas browser-state persistence is wired end to end.
            assert host.property("graphBrowserStateSink") is not None
            assert loader.property("graphBrowserStateSink") is not None

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )


__all__ = [
    "GraphSurfaceFolderExplorerBridgeContractTests",
    "GraphSurfaceDefaultPropertyContractTests",
    "GraphSurfaceWebBoardLoaderContractTests",
    "GraphSurfaceWebPageLoaderContractTests",
]

if __name__ == "__main__":
    unittest.main()
