from __future__ import annotations

import unittest

from tests.graph_surface.environment import GraphSurfaceInputContractTestBase


class LockedPlaceholderGraphHostTests(GraphSurfaceInputContractTestBase):
    def test_locked_placeholder_routes_to_addon_manager_and_blocks_mutations(self) -> None:
        self._run_qml_probe(
            "locked-placeholder-host-contract",
            """
            from PyQt6.QtCore import QObject, pyqtSlot

            class AddonManagerBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.requests = []

                @pyqtSlot(str)
                def requestOpen(self, focus_addon_id):
                    self.requests.append(str(focus_addon_id))

            addon_bridge = AddonManagerBridgeStub()
            shell_context._addon_manager_bridge = addon_bridge

            payload = node_payload()
            payload["read_only"] = True
            payload["unresolved"] = True
            payload["addon_id"] = "tests.addons.signal_pack"
            payload["addon_display_name"] = "Signal Pack"
            payload["addon_version"] = "2.4.1"
            payload["unavailable_reason"] = "Install Signal Pack 2.4.1 to restore this node."
            payload["ports"] = [
                {"key": "message", "label": "Message", "direction": "in", "kind": "data", "data_type": "str", "connected": False},
                {"key": "result", "label": "Result", "direction": "out", "kind": "data", "data_type": "str", "connected": False},
            ]
            payload["inline_properties"] = [{"key": "message", "label": "Message", "inline_editor": "text", "value": "log message", "overridden_by_input": False, "input_port_label": "message"}]
            payload["locked_state"] = {
                "reason": "missing_addon",
                "label": "Requires add-on",
                "summary": "Install Signal Pack 2.4.1 to restore this node.",
                "focus_addon_id": "tests.addons.signal_pack",
            }

            host = create_component(graph_node_host_qml_path, {"nodeData": payload, "graphLabelPixelSize": 16})
            typography = host.findChild(QObject, "graphSharedTypography")
            locked_chip = named_item(host, "graphNodeLockedChip")
            locked_title_icon = named_item(host, "graphNodeLockedTitleIcon")
            locked_stripe = named_item(host, "graphNodeLockedAccentStripe")
            locked_ribbon = named_item(host, "graphNodeLockedPlaceholderRibbon")
            plug_icon = named_item(host, "graphNodeLockedPlaceholderPlugIcon")
            locked_label = named_item(host, "graphNodeLockedPlaceholderLabel")
            package_label = named_item(host, "graphNodeLockedPlaceholderPackage")
            manager_button = named_item(host, "graphNodeLockedPlaceholderButton")
            manager_button_text = named_item(host, "graphNodeLockedPlaceholderButtonText")
            locked_overlay = named_item(host, "graphNodeLockedOverlay")
            input_padlock = named_item(host, "graphNodeInputPortPadlock", "message")
            output_padlock = named_item(host, "graphNodeOutputPortPadlock", "result")
            input_label = named_item(host, "graphNodeInputPortLabel", "message")
            output_label = named_item(host, "graphNodeOutputPortLabel", "result")

            assert bool(host.property("graphReadOnly")) is True
            assert bool(host.property("lockedPlaceholderActive")) is True
            assert typography is not None
            assert bool(host.property("surfaceInteractionLocked")) is True
            assert bool(host.property("sharedHeaderTitleEditable")) is False
            assert bool(host.property("canEnterScope")) is False
            assert str(host.property("lockedPlaceholderPackageText") or "") == "Signal Pack v2.4.1"
            assert bool(locked_chip.property("visible")) is True
            assert int(locked_title_icon.property("width")) == int(typography.property("nodeTitleIconPixelSize")), (
                locked_title_icon.property("width"),
                typography.property("nodeTitleIconPixelSize"),
            )
            assert int(locked_title_icon.property("height")) == int(typography.property("nodeTitleIconPixelSize")), (
                locked_title_icon.property("height"),
                typography.property("nodeTitleIconPixelSize"),
            )
            assert bool(locked_stripe.property("visible")) is True
            assert bool(locked_ribbon.property("visible")) is True
            assert int(plug_icon.property("width")) == int(typography.property("badgeIconPixelSize")), (
                plug_icon.property("width"),
                typography.property("badgeIconPixelSize"),
            )
            assert int(plug_icon.property("height")) == int(typography.property("badgeIconPixelSize")), (
                plug_icon.property("height"),
                typography.property("badgeIconPixelSize"),
            )
            assert str(locked_label.property("text") or "") == "Requires add-on"
            assert locked_label.property("font").pixelSize() == int(typography.property("badgePixelSize")), (
                locked_label.property("font").pixelSize(),
                typography.property("badgePixelSize"),
            )
            assert locked_label.property("font").weight() == int(typography.property("badgeFontWeight")), (
                locked_label.property("font").weight(),
                typography.property("badgeFontWeight"),
            )
            assert str(package_label.property("text") or "") == "Signal Pack v2.4.1"
            assert package_label.property("font").pixelSize() == int(typography.property("inlinePropertyPixelSize")), (
                package_label.property("font").pixelSize(),
                typography.property("inlinePropertyPixelSize"),
            )
            assert bool(manager_button.property("visible")) is True
            assert str(manager_button_text.property("text") or "") == "Load..."
            assert manager_button_text.property("font").pixelSize() == int(typography.property("inlinePropertyPixelSize")), (
                manager_button_text.property("font").pixelSize(),
                typography.property("inlinePropertyPixelSize"),
            )
            assert bool(locked_overlay.property("visible")) is True
            assert bool(input_padlock.property("visible")) is True
            assert bool(output_padlock.property("visible")) is True
            assert float(input_label.property("opacity")) < 0.7
            assert float(output_label.property("opacity")) < 0.7

            common_actions = [variant_value(action) for action in variant_list(host.property("commonNodeActions"))]
            assert [action["id"] for action in common_actions] == [
                "frame_node",
                "open_addon_manager_for_node",
            ]
            assert common_actions[0]["label"] == "Zoom to node"
            assert common_actions[0]["icon"] == "zoom-fit"
            assert common_actions[0]["enabled"] is True
            assert common_actions[1]["label"] == "Load..."
            assert common_actions[1]["enabled"] is True

            requested_actions = []
            host.nodeActionRequested.connect(lambda node_id, action_id, action_payload: requested_actions.append((node_id, action_id, action_payload)))
            assert bool(host.beginInlineTitleEdit()) is False
            assert bool(host.dispatchSurfaceAction("run")) is False

            host.dispatchNodeAction("remove_node", {"reason": "blocked"})
            settle_events(2)
            assert requested_actions == []

            host.dispatchNodeAction("open_addon_manager_for_node", None)
            settle_events(2)
            assert addon_bridge.requests == ["tests.addons.signal_pack"]

            action_rect = variant_value(host.property("lockedPlaceholderActionRect"))
            assert rect_field(action_rect, "width") > 0.0
            assert rect_field(action_rect, "height") > 0.0

            events = host_pointer_events(host)
            window = attach_host_to_window(host, 520, 360)
            action_point = host_scene_point(
                host,
                rect_field(action_rect, "x") + rect_field(action_rect, "width") * 0.5,
                rect_field(action_rect, "y") + rect_field(action_rect, "height") * 0.5,
            )
            mouse_click(window, action_point)
            settle_events(4)

            assert events["clicked"] == [("node_surface_contract_test", False)]
            assert events["opened"] == []
            assert len(addon_bridge.requests) == 2
            assert addon_bridge.requests[-1] == "tests.addons.signal_pack"

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )


class ExcalidrawWebBoardPassiveGraphHostTests(GraphSurfaceInputContractTestBase):
    def test_excalidraw_web_board_fallback_is_passive_and_preserves_host_gestures(self) -> None:
        self._run_qml_probe(
            "excalidraw-web-board-passive-fallback-host",
            """
            from PyQt6.QtCore import pyqtSlot

            engine.rootContext().setContextProperty("graphWebBoardForceFallback", True)

            class ContentFullscreenBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.toggle_calls = []
                    self.open_calls = []

                @pyqtSlot(str, result=bool)
                def request_toggle_for_node(self, node_id):
                    self.toggle_calls.append(str(node_id))
                    return True

                @pyqtSlot(str, result=bool)
                def request_open_node(self, node_id):
                    self.open_calls.append(str(node_id))
                    return True

            content_fullscreen_bridge = ContentFullscreenBridgeStub()
            engine.rootContext().setContextProperty("contentFullscreenBridge", content_fullscreen_bridge)

            payload = node_payload("web", "excalidraw_board")
            payload["node_id"] = "excalidraw_surface_host_test"
            payload["type_id"] = "excalidraw.board"
            payload["title"] = "Sprint board"
            payload["runtime_behavior"] = "passive"
            payload["width"] = 320.0
            payload["height"] = 184.0
            payload["inline_properties"] = []
            payload["surface_metrics"].update({
                "body_left_margin": 10.0,
                "body_right_margin": 10.0,
                "body_top": 32.0,
                "body_height": 136.0,
                "body_bottom_margin": 12.0,
                "port_top": 172.0,
                "port_height": 0.0,
                "port_center_offset": 0.0,
            })
            initial_state = {
                "type": "excalidraw",
                "appState": {"name": "Sprint map"},
                "elements": [
                    {"id": "note-1", "type": "text"},
                    {"id": "frame-1", "type": "rectangle"},
                ],
                "files": {},
            }
            payload["properties"] = {
                "excalidraw_state": initial_state,
                "excalidraw_preview_ref": "",
            }

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            settle_events(4)

            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            surface = host.findChild(QObject, "graphNodeWebBoardSurface")
            fallback = host.findChild(QObject, "graphNodeWebBoardFallbackPanel")
            fullscreen_button = host.findChild(QObject, "graphNodeWebBoardFullscreenButton")
            assert loader is not None
            assert surface is not None
            assert fallback is not None
            assert fullscreen_button is not None
            assert str(loader.property("loadedSurfaceKey")) == "web_excalidraw_board"
            assert str(surface.property("previewMode")) == "fallback"
            assert bool(fallback.property("visible")) is True
            assert bool(fullscreen_button.property("enabled")) is True
            assert str(surface.property("webEngineFallbackReason")).startswith("Qt WebEngine preview is disabled")

            committed = []
            host.inlinePropertyCommitted.connect(lambda node_id, key, value: committed.append((node_id, key, variant_value(value))))
            events = host_pointer_events(host)
            window = attach_host_to_window(host, width=520, height=360)

            body_point = host_scene_point(host, 36.0, 88.0)
            mouse_click(window, body_point)
            settle_events(2)
            assert events["clicked"] == [("excalidraw_surface_host_test", False)]

            mouse_double_click(window, body_point)
            settle_events(2)
            assert events["opened"] == ["excalidraw_surface_host_test"]

            embedded_rects = variant_list(loader.property("embeddedInteractiveRects"))
            assert len(embedded_rects) == 1
            button_rect = embedded_rects[0]
            assert rect_field(button_rect, "width") >= 24.0
            assert rect_field(button_rect, "height") >= 24.0
            assert rect_field(button_rect, "width") < 40.0
            assert rect_field(button_rect, "height") < 40.0

            assert bool(host.dispatchSurfaceAction("fullscreen")) is True
            assert content_fullscreen_bridge.toggle_calls == ["excalidraw_surface_host_test"]
            assert content_fullscreen_bridge.open_calls == []
            assert committed == []
            assert payload["properties"]["excalidraw_state"] == initial_state

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )


__all__ = [
    "ExcalidrawWebBoardPassiveGraphHostTests",
    "LockedPlaceholderGraphHostTests",
]

if __name__ == "__main__":
    unittest.main()
