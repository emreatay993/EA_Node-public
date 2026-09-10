from __future__ import annotations

from pathlib import Path
import unittest
from tests.graph_surface.environment import *  # noqa: F403


class EmbeddedViewerOverlayGuardrailTests(unittest.TestCase):
    _OVERLAY_MANAGER = (
        Path(__file__).resolve().parents[2]
        / "ea_node_editor"
        / "ui_qml"
        / "embedded_viewer_overlay_manager.py"
    )

    def test_overlay_sync_requests_are_event_turn_coalesced(self) -> None:
        source = self._OVERLAY_MANAGER.read_text(encoding="utf-8")
        queue_body = source[source.index("    def _queue_sync(") : source.index("    @pyqtSlot()")]

        self.assertIn("if self._sync_queued:", queue_body)
        self.assertIn("if normalized_mode == _SYNC_MODE_FULL:", queue_body)
        self.assertIn("self._queued_sync_mode = _SYNC_MODE_FULL", queue_body)
        self.assertIn("QTimer.singleShot(0, self._run_queued_sync)", queue_body)

    def test_overlay_sync_culls_offscreen_nodes_before_item_tree_lookup(self) -> None:
        source = self._OVERLAY_MANAGER.read_text(encoding="utf-8")
        sync_body = source[source.index("    def _sync_impl(") : source.index("    def _root_item(")]

        self.assertLess(
            sync_body.index("self._overlay_is_outside_expanded_viewport("),
            sync_body.index("self._overlay_items("),
        )
        self.assertIn('metrics["skipped_offscreen_count"]', sync_body)
        self.assertIn("cached_only=transform_only", sync_body)
        self.assertIn('metrics["geometry_only_updates"]', sync_body)
        self.assertIn('metrics["content_updates"]', sync_body)


class PassiveGraphSurfaceMediaAndScopeTests(PassiveGraphSurfaceHostTestBase):
    def _run_shell_window_probe(self, label: str, body: str) -> None:
        run_qml_probe(
            self,
            label,
            """
            import gc
            from pathlib import Path
            from unittest.mock import patch

            from PyQt6.QtCore import QEvent, QUrl
            from PyQt6.QtWidgets import QApplication

            from ea_node_editor.graph.file_issue_state import encode_file_repair_request
            from ea_node_editor.common.artifact_refs import format_managed_artifact_ref
            from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
            from ea_node_editor.ui.shell.window import ShellWindow
            from tests.conftest import ShellTestEnvironment

            _REPO_ROOT = Path.cwd()

            def _flush_qt_events(app):
                app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()
                app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()

            def _destroy_shell_window(window, app):
                if window is None:
                    return
                for timer_name in ("metrics_timer", "graph_hint_timer", "autosave_timer"):
                    timer = getattr(window, timer_name, None)
                    if timer is not None:
                        timer.stop()
                window.close()
                quick_widget = getattr(window, "quick_widget", None)
                if quick_widget is not None:
                    window.takeCentralWidget()
                    quick_widget.setSource(QUrl())
                    quick_widget.hide()
                    quick_widget.deleteLater()
                    window.quick_widget = None
                window.deleteLater()
                _flush_qt_events(app)
                gc.collect()

            app = QApplication.instance() or QApplication([])
            app.setQuitOnLastWindowClosed(False)
            """,
            body,
        )

    def test_scope_capable_nodes_keep_header_clear_and_title_double_click_for_editing(self) -> None:
        self._run_qml_probe(
            "shared-header-title-rollout-no-open-badge",
            """
            payload = node_payload()
            payload["can_enter_scope"] = True

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            window = attach_host_to_window(host, width=640, height=480)
            try:
                header = host.findChild(QObject, "graphNodeHeaderLayer")
                title_item = host.findChild(QObject, "graphNodeTitle")
                editor = host.findChild(QObject, "graphNodeTitleEditor")
                open_badge = host.findChild(QObject, "graphNodeOpenBadge")
                assert header is not None
                assert title_item is not None
                assert editor is not None
                assert open_badge is None
                assert bool(host.property("sharedHeaderTitleEditable"))

                embedded_rects = variant_list(header.property("embeddedInteractiveRects"))
                assert embedded_rects == []

                common_actions = [variant_value(action) for action in variant_list(host.property("commonNodeActions"))]
                assert all(action.get("id") != "open_subnode_scope" for action in common_actions)

                context_actions = [variant_value(action) for action in variant_list(host.property("contextNodeActions"))]
                assert context_actions == [{
                    "id": "open_subnode_scope",
                    "label": "Enter Subnode",
                    "icon": "door-enter",
                    "kind": "scope",
                    "enabled": True,
                    "primary": False,
                }]
                available_actions = [variant_value(action) for action in variant_list(host.property("availableActions"))]
                assert available_actions[0]["id"] == "open_subnode_scope"

                committed = []
                events = host_pointer_events(host)
                host.inlinePropertyCommitted.connect(
                    lambda node_id, key, value: committed.append((node_id, key, variant_value(value)))
                )
                mouse_double_click(window, item_scene_point(title_item))
                settle_events(5)

                assert bool(editor.property("visible"))
                assert events["opened"] == []
                editing_rects = variant_list(header.property("embeddedInteractiveRects"))
                assert len(editing_rects) == 1

                editor.setProperty("text", " Scoped Logger ")
                app.processEvents()
                app.sendEvent(
                    editor,
                    QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
                )
                app.sendEvent(
                    editor,
                    QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
                )
                settle_events(5)

                assert committed == [("node_surface_host_test", "title", "Scoped Logger")]
                assert not bool(editor.property("visible"))
            finally:
                dispose_host_window(host, window)
            """,
        )



class GraphSurfaceMediaAndScopeContractTests(GraphSurfaceInputContractTestBase):
    _run_shell_window_probe = PassiveGraphSurfaceMediaAndScopeTests._run_shell_window_probe

    def test_graph_node_host_accepts_viewer_surface_family_without_canvas_special_cases(self) -> None:
        self._run_qml_probe(
            "viewer-surface-family-contract",
            """
            payload = node_payload(surface_family="viewer")
            payload["type_id"] = "tests.viewer_surface_contract"
            payload["title"] = "Viewer Contract"
            payload["width"] = 296.0
            payload["height"] = 236.0
            payload["ports"] = [
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
            ]
            payload["inline_properties"] = []
            payload["render_quality"] = {
                "supported_quality_tiers": ["full", "proxy"],
            }
            payload["surface_metrics"] = {
                "default_width": 296.0,
                "default_height": 236.0,
                "min_width": 220.0,
                "min_height": 208.0,
                "collapsed_width": 130.0,
                "collapsed_height": 36.0,
                "header_height": 24.0,
                "header_top_margin": 4.0,
                "body_left_margin": 14.0,
                "body_right_margin": 14.0,
                "body_top": 30.0,
                "body_height": 176.0,
                "body_bottom_margin": 12.0,
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
                "use_host_chrome": True,
                "standard_title_full_width": 0.0,
                "standard_left_label_width": 0.0,
                "standard_right_label_width": 0.0,
                "standard_port_gutter": 21.5,
                "standard_center_gap": 24.0,
                "standard_port_label_min_width": 0.0,
            }
            payload["viewer_surface"] = {
                "body_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
                "proxy_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
                "live_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
                "overlay_target": "body",
                "proxy_surface_supported": True,
                "live_surface_supported": True,
            }

            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": payload,
                    "snapshotReuseActive": True,
                },
            )
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            assert loader is not None
            assert surface is not None

            assert host.property("surfaceFamily") == "viewer"
            assert loader.property("loadedSurfaceKey") == "viewer"
            assert host.property("requestedQualityTier") == "reduced"
            assert host.property("resolvedQualityTier") == "proxy"
            assert bool(surface.property("proxySurfaceActive"))

            contract = variant_value(loader.property("viewerSurfaceContract"))
            assert contract["overlay_target"] == "body"

            live_rect = loader.property("viewerLiveSurfaceRect")
            assert rect_field(live_rect, "x") == float(contract["live_rect"]["x"])
            assert rect_field(live_rect, "y") == float(contract["live_rect"]["y"])
            assert rect_field(live_rect, "width") == float(contract["live_rect"]["width"])
            assert rect_field(live_rect, "height") == float(contract["live_rect"]["height"])
            """,
        )

    def test_viewer_surface_control_rects_flow_through_host_contract(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-contract",
            """
            from PyQt6.QtCore import pyqtSignal, pyqtSlot

            class ViewerSessionBridgeStub(QObject):
                sessions_changed = pyqtSignal()

                @staticmethod
                def _session_projection():
                    return {
                        "workspace_id": "ws_main",
                        "node_id": "node_surface_contract_test",
                        "session_id": "session::viewer-surface-pointer",
                        "phase": "open",
                        "request_id": "req::viewer-pointer",
                        "last_command": "open",
                        "last_error": "",
                        "live_mode": "proxy",
                        "playback_state": "paused",
                        "step_index": 1,
                        "cache_state": "proxy_ready",
                        "invalidated_reason": "",
                        "close_reason": "",
                        "data_refs": {},
                        "summary": {
                            "result_name": "Displacement",
                            "set_label": "Set 1",
                            "cache_state": "proxy_ready",
                        },
                        "options": {
                            "live_mode": "proxy",
                            "playback_state": "paused",
                            "step_index": 1,
                        },
                    }

                @pyqtProperty("QVariantList", notify=sessions_changed)
                def sessions_model(self):
                    return [self._session_projection()]

                @pyqtSlot(str, result="QVariantMap")
                def session_state(self, node_id):
                    if str(node_id or "") != "node_surface_contract_test":
                        return {}
                    return self._session_projection()

                @pyqtProperty(str, constant=True)
                def last_error(self):
                    return ""

            bridge = ViewerSessionBridgeStub()
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)

            payload = node_payload(surface_family="viewer")
            payload["type_id"] = "tests.viewer_surface_contract"
            payload["title"] = "Viewer Contract"
            payload["width"] = 296.0
            payload["height"] = 236.0
            payload["ports"] = [
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
            ]
            payload["inline_properties"] = []
            payload["render_quality"] = {
                "supported_quality_tiers": ["full", "proxy"],
            }
            payload["surface_metrics"] = {
                "default_width": 296.0,
                "default_height": 236.0,
                "min_width": 220.0,
                "min_height": 208.0,
                "collapsed_width": 130.0,
                "collapsed_height": 36.0,
                "header_height": 24.0,
                "header_top_margin": 4.0,
                "body_left_margin": 14.0,
                "body_right_margin": 14.0,
                "body_top": 30.0,
                "body_height": 176.0,
                "body_bottom_margin": 12.0,
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
                "use_host_chrome": True,
                "standard_title_full_width": 0.0,
                "standard_left_label_width": 0.0,
                "standard_right_label_width": 0.0,
                "standard_port_gutter": 21.5,
                "standard_center_gap": 24.0,
                "standard_port_label_min_width": 0.0,
            }
            payload["viewer_surface"] = {
                "body_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
                "proxy_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
                "live_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
                "overlay_target": "body",
                "proxy_surface_supported": True,
                "live_surface_supported": True,
            }

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            assert loader is not None
            assert surface is not None

            bridge_binding = variant_value(host.property("viewerBridgeBinding"))
            contract = variant_value(host.property("viewerSurfaceContract"))
            control_rects = variant_list(host.property("viewerInteractiveRects"))
            surface_actions = variant_list(loader.property("surfaceActions"))
            assert bridge_binding["phase"] == "open", bridge_binding
            assert bridge_binding["live_mode"] == "proxy", bridge_binding
            assert contract["bridge_binding"]["phase"] == "open", contract
            assert control_rects == [], control_rects
            assert variant_list(loader.property("embeddedInteractiveRects")) == [], variant_list(loader.property("embeddedInteractiveRects"))
            assert contract["interactive_rects"] == [], contract
            assert [action["id"] for action in surface_actions] == ["openSession", "playPause", "step", "camera", "screenshot", "copyImage", "detach", "fullscreen"], surface_actions
            assert rect_field(host.property("viewerBodyRect"), "x") == float(contract["body_rect"]["x"]), variant_value(host.property("viewerBodyRect"))
            assert rect_field(host.property("viewerLiveSurfaceRect"), "width") == float(contract["live_rect"]["width"]), variant_value(host.property("viewerLiveSurfaceRect"))
            assert rect_field(host.property("viewerLiveSurfaceRect"), "height") == float(contract["live_rect"]["height"]), variant_value(host.property("viewerLiveSurfaceRect"))
            """,
        )

    def test_graph_canvas_routes_scoped_toolbar_action_through_request_open_subnode_scope(self) -> None:
        self._run_qml_probe(
            "graph-canvas-scoped-toolbar-action-route",
            """
            from PyQt6.QtCore import QObject, QPointF, pyqtProperty, pyqtSignal, pyqtSlot

            scoped_payload = node_payload()
            scoped_payload["can_enter_scope"] = True

            class SceneBridgeStub(QObject):
                nodes_changed = pyqtSignal()
                edges_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self.select_calls = []
                    self.set_node_property_calls = []
                    self._nodes_model = [scoped_payload]
                    self._selected_node_lookup = {}

                @pyqtProperty("QVariantList", notify=nodes_changed)
                def nodes_model(self):
                    return self._nodes_model

                @pyqtProperty("QVariantList", notify=edges_changed)
                def edges_model(self):
                    return []

                @pyqtProperty("QVariantMap", notify=nodes_changed)
                def selected_node_lookup(self):
                    return self._selected_node_lookup

                @pyqtSlot(str)
                @pyqtSlot(str, bool)
                def select_node(self, node_id, additive=False):
                    normalized_node_id = str(node_id or "")
                    self.select_calls.append((normalized_node_id, bool(additive)))
                    self._selected_node_lookup = {normalized_node_id: True} if normalized_node_id else {}
                    self.nodes_changed.emit()

                @pyqtSlot(str, str, "QVariant")
                def set_node_property(self, node_id, key, value):
                    self.set_node_property_calls.append((str(node_id or ""), str(key or ""), variant_value(value)))

                @pyqtSlot(str, str, str)
                def set_node_port_label(self, node_id, port_key, label):
                    pass

                @pyqtSlot(str, str, result=bool)
                def are_port_kinds_compatible(self, _source_kind, _target_kind):
                    return True

                @pyqtSlot(str, str, result=bool)
                def are_data_types_compatible(self, _source_type, _target_type):
                    return True

            class MainWindowBridgeStub(QObject):
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

                def __init__(self):
                    super().__init__()
                    self.scope_open_calls = []

                @pyqtSlot(str, result=bool)
                def request_open_subnode_scope(self, node_id):
                    self.scope_open_calls.append(str(node_id or ""))
                    return True

            class GraphActionBridgeStub(QObject):
                def __init__(self):
                    super().__init__()
                    self.actions = []

                @pyqtSlot(str, "QVariantMap", result=bool)
                def trigger_graph_action(self, action_id, payload):
                    self.actions.append((str(action_id or ""), dict(payload or {})))
                    return True

            scene_bridge = SceneBridgeStub()
            window_bridge = MainWindowBridgeStub()
            graph_action_bridge = GraphActionBridgeStub()
            canvas_state_bridge, canvas_command_bridge = build_canvas_bridges(
                shell_bridge=window_bridge,
                scene_bridge=scene_bridge,
            )
            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "graphActionBridge": graph_action_bridge,
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 640.0,
                    "height": 480.0,
                },
            )
            try:
                node_card = next((item for item in walk_items(canvas) if item.objectName() == "graphNodeCard"), None)
                assert node_card is not None
                title_item = node_card.findChild(QObject, "graphNodeTitle")
                editor = node_card.findChild(QObject, "graphNodeTitleEditor")
                open_badge = node_card.findChild(QObject, "graphNodeOpenBadge")
                assert title_item is not None
                assert editor is not None
                assert open_badge is None
                assert bool(node_card.property("sharedHeaderTitleEditable"))

                common_actions = [variant_value(action) for action in variant_list(node_card.property("commonNodeActions"))]
                assert all(action.get("id") != "open_subnode_scope" for action in common_actions)

                context_actions = [variant_value(action) for action in variant_list(node_card.property("contextNodeActions"))]
                assert context_actions == [{
                    "id": "open_subnode_scope",
                    "label": "Enter Subnode",
                    "icon": "door-enter",
                    "kind": "scope",
                    "enabled": True,
                    "primary": False,
                }]
                available_actions = [variant_value(action) for action in variant_list(node_card.property("availableActions"))]
                assert available_actions[0]["id"] == "open_subnode_scope"

                title_point = title_item.mapToItem(
                    node_card,
                    QPointF(float(title_item.width()) * 0.5, float(title_item.height()) * 0.5),
                )

                assert not node_card.requestScopeOpenAt(title_point.x(), title_point.y())
                assert node_card.requestInlineTitleEditAt(title_point.x(), title_point.y())
                settle_events(5)

                assert bool(editor.property("visible"))
                assert scene_bridge.select_calls == []

                node_card.dispatchNodeAction("open_subnode_scope", None)
                settle_events(5)

                assert scene_bridge.select_calls == []
                assert graph_action_bridge.actions == [
                    ("open_subnode_scope", {"node_id": "node_surface_contract_test"})
                ]
                assert window_bridge.scope_open_calls == []
            finally:
                canvas.deleteLater()
                app.processEvents()
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_shell_window_browse_node_property_path_uses_explicit_node_id(self) -> None:
        self._run_shell_window_probe(
            "shell-window-browse-node-property-explicit-node-id",
            """
            test_env = ShellTestEnvironment()
            test_env.start()
            window = ShellWindow()
            try:
                window.app_preferences_controller.set_source_import_mode("external_link")
                image_node_id = window.scene.add_node_from_type("media.panel", x=120.0, y=80.0)
                logger_node_id = window.scene.add_node_from_type("core.logger", x=360.0, y=80.0)
                assert image_node_id
                assert logger_node_id
                window.scene.set_exposed_port(image_node_id, "source", False)
                app.processEvents()

                picked_path = str(_REPO_ROOT / "tests" / "fixtures" / "graph-surface-picked-path.png")
                with patch(
                    "ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName",
                    return_value=(picked_path, ""),
                ) as dialog_mock:
                    assert window.browse_selected_node_property_path("source", "") == ""
                    assert window.browse_node_property_path(image_node_id, "source", "") == picked_path
                    assert dialog_mock.call_count == 1

                assert window.browse_node_property_path(logger_node_id, "message", "") == ""
                assert "artifact_store" not in window.model.project.metadata
            finally:
                _destroy_shell_window(window, app)
                test_env.stop()
                _flush_qt_events(app)
            """,
        )

    def test_shell_window_browse_web_page_start_location_accepts_source_storage_modes(self) -> None:
        self._run_shell_window_probe(
            "shell-window-browse-web-page-start-location-source-storage",
            """
            test_env = ShellTestEnvironment()
            temp_root = test_env.start()
            window = ShellWindow()
            try:
                project_path = temp_root / "web-source-storage-demo.cxproj"
                window.project_path = str(project_path)
                web_node_id = window.scene.add_node_from_type("web.page_viewer", x=120.0, y=80.0)
                assert web_node_id
                app.processEvents()

                picked_path = str(_REPO_ROOT / "tests" / "fixtures" / "web_page_viewer" / "index.html")
                with patch(
                    "ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName",
                    return_value=(picked_path, ""),
                ) as dialog_mock:
                    external_path = window.browse_node_property_path(
                        web_node_id,
                        "start_location",
                        "https://example.com",
                        "external_link",
                    )
                    assert external_path == picked_path
                    assert dialog_mock.call_count == 1
                    assert dialog_mock.call_args.args[1] == "Choose Start Location"
                    assert "Web Page Files" in dialog_mock.call_args.args[3]

                with patch(
                    "ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName",
                    return_value=(picked_path, ""),
                ) as dialog_mock:
                    managed_ref = window.browse_node_property_path(
                        web_node_id,
                        "start_location",
                        "https://example.com",
                        "managed_copy",
                    )
                    assert managed_ref.startswith("temp://html_source_"), managed_ref
                    assert dialog_mock.call_count == 1

                store = ProjectArtifactStore.from_project_metadata(
                    project_path=window.project_path,
                    project_metadata=window.model.project.metadata,
                )
                staged_path = store.resolve_staged_path(managed_ref)
                assert staged_path is not None
                assert staged_path.exists()
                assert staged_path.name == "index.html", staged_path
                assert staged_path.read_text(encoding="utf-8").startswith("<!doctype html>")
            finally:
                _destroy_shell_window(window, app)
                test_env.stop()
                _flush_qt_events(app)
            """,
        )

    def test_shell_window_browse_node_property_path_stages_managed_copy_and_reuses_artifact_id(self) -> None:
        self._run_shell_window_probe(
            "shell-window-browse-node-property-stages-managed-copy",
            """
            test_env = ShellTestEnvironment()
            temp_root = test_env.start()
            window = ShellWindow()
            try:
                seed_fixture = _REPO_ROOT / "tests" / "fixtures" / "passive_nodes" / "reference_preview.png"
                replacement_fixture = temp_root / "replacement.png"
                replacement_fixture.write_bytes(b"replacement-image-bytes")
                project_path = temp_root / "managed-seed-demo.cxproj"
                managed_image_path = (
                    project_path.with_name("managed-seed-demo.data")
                    / "nodes"
                    / "Image Panel [11111111]"
                    / "in"
                    / "media"
                    / "seed.png"
                )
                managed_image_path.parent.mkdir(parents=True, exist_ok=True)
                managed_image_path.write_bytes(seed_fixture.read_bytes())
                managed_ref = format_managed_artifact_ref("managed_image")

                window.project_path = str(project_path)
                window.model.project.metadata = {
                    "artifact_store": {
                        "artifacts": {
                            "managed_image": {"relative_path": "nodes/Image Panel [11111111]/in/media/seed.png"},
                        }
                    }
                }

                image_node_id = window.scene.add_node_from_type("media.panel", x=120.0, y=80.0)
                assert image_node_id
                window.scene.set_exposed_port(image_node_id, "source", False)
                window.scene.set_node_property(image_node_id, "source", managed_ref)
                app.processEvents()

                with patch(
                    "ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName",
                    return_value=(str(replacement_fixture), ""),
                ) as dialog_mock:
                    staged_ref = window.browse_node_property_path(image_node_id, "source", managed_ref, "managed_copy")
                    assert staged_ref == "temp://managed_image"
                    assert dialog_mock.call_count == 1
                    assert dialog_mock.call_args.args[2] == str(managed_image_path)

                store = ProjectArtifactStore.from_project_metadata(
                    project_path=window.project_path,
                    project_metadata=window.model.project.metadata,
                )
                staged_path = store.resolve_staged_path(staged_ref)
                assert staged_path is not None
                assert staged_path.exists()
                assert staged_path.name == "replacement.png", staged_path
                assert staged_path.read_bytes() == replacement_fixture.read_bytes()

                with patch(
                    "ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName",
                    return_value=(str(seed_fixture), ""),
                ) as dialog_mock:
                    replacement_ref = window.browse_node_property_path(image_node_id, "source", staged_ref, "managed_copy")
                    assert replacement_ref == staged_ref
                    assert dialog_mock.call_count == 1
                    assert dialog_mock.call_args.args[2] == str(staged_path), dialog_mock.call_args.args

                store = ProjectArtifactStore.from_project_metadata(
                    project_path=window.project_path,
                    project_metadata=window.model.project.metadata,
                )
                replacement_path = store.resolve_staged_path(staged_ref)
                assert replacement_path is not None
                assert replacement_path != staged_path, (replacement_path, staged_path)
                assert replacement_path.exists()
                assert replacement_path.name == "reference_preview.png", replacement_path
                assert replacement_path.read_bytes() == seed_fixture.read_bytes()
                staged_entry = window.model.project.metadata["artifact_store"]["staged"]["managed_image"]
                assert "/tmp/in/" in staged_entry["relative_path"]
                assert staged_entry["relative_path"].endswith("/reference_preview.png"), staged_entry["relative_path"]
            finally:
                _destroy_shell_window(window, app)
                test_env.stop()
                _flush_qt_events(app)
            """,
        )

    def test_shell_window_internalize_node_property_path_stages_existing_external_file_without_dialog(self) -> None:
        self._run_shell_window_probe(
            "shell-window-internalize-node-property-stages-existing-external-file",
            """
            test_env = ShellTestEnvironment()
            temp_root = test_env.start()
            window = ShellWindow()
            try:
                external_fixture = temp_root / "external-image.png"
                external_fixture.write_bytes(b"external-image-bytes")
                project_path = temp_root / "internalize-demo.cxproj"
                window.project_path = str(project_path)

                image_node_id = window.scene.add_node_from_type("media.panel", x=120.0, y=80.0)
                assert image_node_id
                window.scene.set_exposed_port(image_node_id, "source", False)
                window.scene.set_node_property(image_node_id, "source", str(external_fixture))
                app.processEvents()

                with patch("ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName") as dialog_mock:
                    staged_ref = window.internalize_node_property_path(
                        image_node_id,
                        "source",
                        str(external_fixture),
                    )
                    dialog_mock.assert_not_called()

                assert staged_ref.startswith("temp://media_source_"), staged_ref
                store = ProjectArtifactStore.from_project_metadata(
                    project_path=window.project_path,
                    project_metadata=window.model.project.metadata,
                )
                staged_path = store.resolve_staged_path(staged_ref)
                assert staged_path is not None
                assert staged_path.exists()
                assert staged_path.name == external_fixture.name
                assert staged_path.read_bytes() == external_fixture.read_bytes()
                assert window.internalize_node_property_path(image_node_id, "source", staged_ref) == ""
                assert window.internalize_node_property_path(image_node_id, "source", "https://example.com/image.png") == ""
            finally:
                _destroy_shell_window(window, app)
                test_env.stop()
                _flush_qt_events(app)
            """,
        )

    def test_shell_window_selected_node_property_items_publish_file_issue_payload(self) -> None:
        self._run_shell_window_probe(
            "shell-window-selected-node-file-issue-payload",
            """
            test_env = ShellTestEnvironment()
            temp_root = test_env.start()
            window = ShellWindow()
            try:
                missing_path = str(temp_root / "missing-input.txt")
                node_id = window.scene.add_node_from_type("io.file_read", x=120.0, y=80.0)
                assert node_id
                window.scene.set_node_property(node_id, "path", missing_path)
                window.scene.select_node(node_id, False)
                app.processEvents()

                path_item = next(item for item in window.selected_node_property_items if item["key"] == "path")
                assert path_item["file_issue_active"]
                assert path_item["file_issue_kind"] == "external_missing"
                assert path_item["file_issue_supports_external_repair"]
                assert not path_item["file_issue_supports_managed_repair"]
                assert path_item["file_issue_request"] == encode_file_repair_request(missing_path)
            finally:
                _destroy_shell_window(window, app)
                test_env.stop()
                _flush_qt_events(app)
            """,
        )
