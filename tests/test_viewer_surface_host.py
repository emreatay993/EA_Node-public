from __future__ import annotations

import unittest

from tests.graph_surface_pointer_regression import (
    QML_POINTER_REGRESSION_HELPERS,
    run_qml_probe,
)


class ViewerSurfaceHostTests(unittest.TestCase):
    def _run_qml_probe(self, label: str, body: str) -> None:
        run_qml_probe(
            self,
            label,
            """
            from pathlib import Path

            from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
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
            from ea_node_editor.ui.plot_preview_cache_provider import (
                VIEWER_PREVIEW_CACHE_PROVIDER_ID,
                ViewerPreviewCacheImageProvider,
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

            class ViewerSessionBridgeStub(QObject):
                sessions_changed = pyqtSignal()
                last_error_changed = pyqtSignal()

                def __init__(self, parent=None):
                    super().__init__(parent)
                    self.open_calls = []
                    self.update_calls = []
                    self.close_calls = []
                    self.embedded_interaction_calls = []
                    self.session_state_calls = []
                    self._last_error = ""
                    self._state = self._build_state()

                def _build_state(
                    self,
                    *,
                    phase="open",
                    playback_state="paused",
                    step_index=3,
                    cache_state="proxy_ready",
                    live_mode="proxy",
                    session_id="session::node_viewer_surface_host",
                    last_command="open",
                    backend_id="backend.viewer",
                    transport_revision=7,
                    live_open_status="ready",
                    live_open_blocker=None,
                    transport=None,
                    data_refs=None,
                    invalidated_reason="",
                    close_reason="",
                ):
                    if live_open_blocker is None:
                        live_open_blocker = {}
                    if transport is None:
                        transport = {
                            "kind": "bundle",
                            "backend_id": backend_id,
                            "bundle_path": "C:/temp/viewer_bundle",
                        }
                    if data_refs is None:
                        data_refs = {
                            "fields": {"kind": "handle_ref", "handle_id": "handle::fields"},
                            "png": {
                                "__ea_runtime_value__": "artifact_ref",
                                "ref": "saved://viewer_proxy_png",
                                "artifact_id": "viewer_proxy_png",
                                "scope": "managed",
                            },
                        }
                    return {
                        "workspace_id": "ws_main",
                        "node_id": "node_viewer_surface_host",
                        "session_id": session_id,
                        "phase": phase,
                        "request_id": "req::viewer",
                        "last_command": last_command,
                        "last_error": self._last_error,
                        "playback_state": playback_state,
                        "step_index": step_index,
                        "cache_state": cache_state,
                        "live_mode": live_mode,
                        "backend_id": backend_id,
                        "transport_revision": transport_revision,
                        "live_open_status": live_open_status,
                        "live_open_blocker": dict(live_open_blocker),
                        "invalidated_reason": invalidated_reason,
                        "close_reason": close_reason,
                        "data_refs": dict(data_refs),
                        "transport": dict(transport),
                        "summary": {
                            "result_name": "Displacement",
                            "set_label": "Set 4",
                            "cache_state": cache_state,
                            "backend_id": backend_id,
                            "transport_revision": transport_revision,
                            "live_open_status": live_open_status,
                            "live_open_blocker": dict(live_open_blocker),
                        },
                        "options": {
                            "live_mode": live_mode,
                            "playback_state": playback_state,
                            "step_index": step_index,
                            "backend_id": backend_id,
                            "transport_revision": transport_revision,
                            "live_open_status": live_open_status,
                            "live_open_blocker": dict(live_open_blocker),
                        },
                    }

                def _set_state(self, **updates):
                    state = dict(self._state or self._build_state())
                    summary = dict(state.get("summary", {}))
                    options = dict(state.get("options", {}))
                    summary_updates = dict(updates.pop("summary", {}))
                    options_updates = dict(updates.pop("options", {}))
                    state.update(updates)
                    summary.update(summary_updates)
                    options.update(options_updates)
                    if "live_mode" in options_updates and "live_mode" not in updates:
                        state["live_mode"] = options_updates["live_mode"]
                    state["summary"] = summary
                    state["options"] = options
                    self._state = state
                    self.sessions_changed.emit()

                @pyqtProperty("QVariantList", notify=sessions_changed)
                def sessions_model(self):
                    return [dict(self._state)] if self._state is not None else []

                @pyqtProperty(str, notify=last_error_changed)
                def last_error(self):
                    return self._last_error

                @pyqtSlot(str, result="QVariantMap")
                def session_state(self, node_id):
                    self.session_state_calls.append(str(node_id))
                    if str(node_id) != "node_viewer_surface_host" or self._state is None:
                        return {}
                    return dict(self._state)

                @pyqtSlot(str, result=str)
                def open(self, node_id):
                    self.open_calls.append({"node_id": str(node_id)})
                    self._set_state(
                        phase="opening",
                        last_command="open",
                        close_reason="",
                        options={
                            "live_mode": "proxy",
                            "playback_state": "paused",
                        },
                    )
                    return "session::node_viewer_surface_host"

                @pyqtSlot(str, result=bool)
                def close(self, node_id):
                    self.close_calls.append({"node_id": str(node_id)})
                    self._set_state(
                        phase="closed",
                        last_command="close",
                        close_reason="user_close",
                        cache_state="proxy_ready",
                        options={
                            "live_mode": "proxy",
                            "playback_state": "paused",
                        },
                        summary={
                            "cache_state": "proxy_ready",
                            "close_reason": "user_close",
                        },
                    )
                    return True

                @pyqtSlot(str, result=bool)
                def play(self, node_id):
                    self.update_calls.append({"command": "play", "node_id": str(node_id)})
                    self._set_state(
                        playback_state="playing",
                        last_command="play",
                        options={"playback_state": "playing"},
                    )
                    return True

                @pyqtSlot(str, result=bool)
                def pause(self, node_id):
                    self.update_calls.append({"command": "pause", "node_id": str(node_id)})
                    self._set_state(
                        playback_state="paused",
                        last_command="pause",
                        options={"playback_state": "paused"},
                    )
                    return True

                @pyqtSlot(str, result=bool)
                def step(self, node_id):
                    self.update_calls.append({"command": "step", "node_id": str(node_id)})
                    next_step = int(self._state.get("step_index", 0)) + 1
                    self._set_state(
                        step_index=next_step,
                        playback_state="paused",
                        last_command="step",
                        options={
                            "step_index": next_step,
                            "playback_state": "paused",
                        },
                    )
                    return True

                @pyqtSlot(str, bool, result=bool)
                def set_embedded_interaction_active(self, node_id, active):
                    normalized = bool(active)
                    self.embedded_interaction_calls.append((str(node_id), normalized))
                    self._set_state(
                        live_mode="full" if normalized else "proxy",
                        options={"live_mode": "full" if normalized else "proxy"},
                    )
                    return True

            class ViewerHostServiceStub(QObject):
                state_changed = pyqtSignal()
                preview_cache_changed = pyqtSignal()
                last_error_changed = pyqtSignal()

                def __init__(self, parent=None):
                    super().__init__(parent)
                    self.active_calls = []
                    self.preview_swap_calls = []
                    self._overlay_ready = False
                    self._viewer_overlay_revision = 0
                    self._preview_cache_revision = 1
                    self._last_error = ""
                    self.session_bridge = None
                    self.detached_calls = []
                    self.standard_view_calls = []
                    self.reset_calls = []
                    self.screenshot_calls = []
                    self.copy_calls = []
                    self._cached_preview_source = "image://viewer-preview-cache/preview?workspace=ws_main&node=node_viewer_surface_host&revision=1"

                @pyqtProperty(int, notify=state_changed)
                def active_overlay_count(self):
                    return 1 if any(active for _node_id, active in self.active_calls[-1:]) else 0

                @pyqtProperty(int, notify=state_changed)
                def viewer_overlay_revision(self):
                    return self._viewer_overlay_revision

                @pyqtProperty(int, notify=preview_cache_changed)
                def preview_cache_revision(self):
                    return self._preview_cache_revision

                @pyqtProperty(str, notify=last_error_changed)
                def last_error(self):
                    return self._last_error

                @pyqtSlot(str, bool)
                def set_embedded_interaction_active(self, node_id, active):
                    self.active_calls.append((str(node_id), bool(active)))
                    if self.session_bridge is not None:
                        self.session_bridge.set_embedded_interaction_active(node_id, active)

                @pyqtSlot(str, result=str)
                def cached_preview_source(self, node_id):
                    if str(node_id) != "node_viewer_surface_host":
                        return ""
                    return self._cached_preview_source

                @pyqtSlot(str, result=bool)
                def embedded_live_overlay_ready(self, node_id):
                    return str(node_id) == "node_viewer_surface_host" and bool(self._overlay_ready)

                @pyqtSlot(str, str)
                def notify_cached_preview_swapped(self, node_id, source):
                    self.preview_swap_calls.append((str(node_id), str(source)))

                @pyqtSlot(str, result=bool)
                def open_detached_viewer(self, node_id):
                    self.detached_calls.append(str(node_id))
                    return True

                @pyqtSlot(str, str, result=bool)
                def apply_standard_view(self, node_id, view_id):
                    self.standard_view_calls.append((str(node_id), str(view_id)))
                    return True

                @pyqtSlot(str, result=bool)
                def reset_overlay_camera(self, node_id):
                    self.reset_calls.append(str(node_id))
                    return True

                @pyqtSlot(str, result="QVariantMap")
                def export_viewer_screenshot(self, node_id):
                    self.screenshot_calls.append(str(node_id))
                    return {"ok": True}

                @pyqtSlot(str, result=bool)
                def copy_viewer_screenshot_to_clipboard(self, node_id):
                    self.copy_calls.append(str(node_id))
                    return True

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            engine.addImageProvider(UI_ICON_PROVIDER_ID, UiIconImageProvider())
            engine.addImageProvider(LOCAL_MEDIA_PREVIEW_PROVIDER_ID, LocalMediaPreviewImageProvider())
            engine.addImageProvider(VIEWER_PREVIEW_CACHE_PROVIDER_ID, ViewerPreviewCacheImageProvider())
            engine.rootContext().setContextProperty("uiIcons", UiIconRegistryBridge())
            engine.rootContext().setContextProperty("themeBridge", ThemeBridgeStub())
            engine.rootContext().setContextProperty("graphThemeBridge", GraphThemeBridgeStub())
            viewerHostServiceStub = ViewerHostServiceStub()
            engine.rootContext().setContextProperty("viewerHostService", viewerHostServiceStub)

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

            def create_viewer_canvas(*, selected=True, zoom=1.0):
                component = QQmlComponent(engine)
                component.setData(
                    b'''
                    import QtQuick 2.15

                    Item {
                        QtObject {
                            id: viewBridgeObject
                            objectName: "viewerTestViewBridge"
                            property real zoom_value: 1.0
                        }
                        QtObject {
                            id: sceneBridgeObject
                            objectName: "viewerTestSceneBridge"
                            property var selected_node_lookup: ({})
                        }
                        property var viewBridge: viewBridgeObject
                        property var sceneBridge: sceneBridgeObject
                        property bool nativeOverlaySuppressionActive: false
                    }
                    ''',
                    QUrl("viewer-test-canvas.qml"),
                )
                if component.status() != QQmlComponent.Status.Ready:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError("Failed to load viewer canvas probe:\\n" + errors)
                canvas = component.create()
                if canvas is None:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError("Failed to instantiate viewer canvas probe:\\n" + errors)
                view = canvas.findChild(QObject, "viewerTestViewBridge")
                scene = canvas.findChild(QObject, "viewerTestSceneBridge")
                view.setProperty("zoom_value", float(zoom))
                scene.setProperty(
                    "selected_node_lookup",
                    {"node_viewer_surface_host": True} if selected else {},
                )
                return canvas, scene

            def viewer_payload():
                return {
                    "node_id": "node_viewer_surface_host",
                    "type_id": "tests.viewer_surface_host",
                    "title": "Viewer Host",
                    "x": 120.0,
                    "y": 90.0,
                    "width": 296.0,
                    "height": 236.0,
                    "accent": "#2F89FF",
                    "collapsed": False,
                    "selected": True,
                    "runtime_behavior": "active",
                    "surface_family": "viewer",
                    "surface_variant": "",
                    "surface_spec": surface_spec_payload_for_values(
                        type_id="tests.viewer_surface_host",
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
                        "body_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
                        "proxy_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
                        "live_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
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

    def test_viewer_surface_controls_follow_bridge_state_and_route_actions(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-actions",
            """
            from PyQt6.QtCore import QMetaObject, Q_ARG

            bridge = ViewerSessionBridgeStub()
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)

            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            cached_image = host.findChild(QObject, "graphNodeViewerCachedPreviewImage")
            status_text = host.findChild(QObject, "graphNodeViewerStatusText")
            mode_label = host.findChild(QObject, "graphNodeViewerSurfaceModeLabel")
            assert surface is not None
            assert host.findChild(QObject, "graphNodeViewerSessionButton") is None
            assert host.findChild(QObject, "graphNodeViewerPlayPauseButton") is None
            assert host.findChild(QObject, "graphNodeViewerStepButton") is None
            assert host.findChild(QObject, "graphNodeViewerMoreButton") is None
            assert host.findChild(QObject, "graphNodeViewerQuickActions") is None
            assert cached_image is not None
            assert status_text is not None
            assert mode_label is not None

            def dispatch(action_id):
                QMetaObject.invokeMethod(surface, "dispatchSurfaceAction", Q_ARG("QVariant", action_id))

            def action_by_id(actions, target_id):
                return next(action for action in actions if action["id"] == target_id)

            interactions = []
            host.surfaceControlInteractionStarted.connect(lambda node_id: interactions.append(node_id))
            pointer_events = host_pointer_events(host)
            window = attach_host_to_window(host, width=640, height=480)
            try:
                assert surface.property("viewerBridgeAvailable")
                assert surface.property("viewerPhase") == "open"
                assert surface.property("viewerPlaybackState") == "paused"
                assert surface.property("viewerLiveMode") == "proxy"
                assert bool(surface.property("proxySurfaceActive"))
                assert not bool(surface.property("liveSurfaceActive"))
                assert not bool(surface.property("viewerShowsPlaceholder"))
                assert status_text.property("text") == "Double-click the viewer for live mode"
                assert mode_label.property("text") == "Preview"
                assert variant_list(surface.property("viewerInteractiveRects")) == []

                actions = variant_list(surface.property("surfaceActions"))
                assert [action["id"] for action in actions] == ["openSession", "playPause", "step", "camera", "screenshot", "copyImage", "detach", "fullscreen"]
                assert action_by_id(actions, "openSession")["icon"] == "stop"
                assert action_by_id(actions, "playPause")["icon"] == "run"

                settle_events(2)
                assert bool(cached_image.property("visible"))
                cached_image_source = cached_image.property("source")
                cached_image_source_text = cached_image_source.toString() if hasattr(cached_image_source, "toString") else str(cached_image_source)
                assert cached_image_source_text.startswith("image://viewer-preview-cache/preview?")

                dispatch("detach")
                settle_events(2)
                assert viewerHostServiceStub.detached_calls == ["node_viewer_surface_host"]

                dispatch("playPause")
                settle_events(5)
                assert bridge.update_calls[-1]["command"] == "play"
                assert surface.property("viewerPlaybackState") == "playing"
                playing_actions = variant_list(surface.property("surfaceActions"))
                assert action_by_id(playing_actions, "playPause")["icon"] == "pause"

                dispatch("step")
                settle_events(5)
                assert bridge.update_calls[-1]["command"] == "step"
                assert int(surface.property("viewerStepIndex")) == 4
                assert viewerHostServiceStub.active_calls == []
                assert not bool(surface.property("inlineLiveRequested"))

                dispatch("openSession")
                settle_events(5)
                assert bridge.close_calls == [{"node_id": "node_viewer_surface_host"}]
                assert surface.property("viewerPhase") == "closed"
                assert bool(surface.property("viewerShowsPlaceholder"))
                closed_actions = variant_list(surface.property("surfaceActions"))
                assert action_by_id(closed_actions, "openSession")["icon"] == "open-session"
                assert status_text.property("text") == "Ready to open viewer session"
                assert mode_label.property("text") == "Overlay"

                dispatch("openSession")
                settle_events(5)
                assert bridge.open_calls == [{"node_id": "node_viewer_surface_host"}]
                assert surface.property("viewerPhase") == "opening"
                opening_actions = variant_list(surface.property("surfaceActions"))
                assert action_by_id(opening_actions, "openSession")["icon"] == "open-session"
                assert status_text.property("text") == "Opening viewer session"
                assert mode_label.property("text") == "Opening"
                assert len(interactions) >= 5
                assert all(node_id == "node_viewer_surface_host" for node_id in interactions)
                assert len(bridge.session_state_calls) >= 1
                assert all(node_id == "node_viewer_surface_host" for node_id in bridge.session_state_calls)
                assert pointer_events["clicked"] == []
                assert pointer_events["opened"] == []
                assert pointer_events["contexts"] == []
                assert viewerHostServiceStub.active_calls == []
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_viewer_surface_controls_and_presentations_preserve_inline_request(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-control-preserves-inline-live",
            """
            from PyQt6.QtCore import QMetaObject, Q_ARG, Qt, pyqtProperty, pyqtSignal, pyqtSlot
            from PyQt6.QtTest import QTest

            class ContentFullscreenBridgeStub(QObject):
                state_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self._open = False
                    self._node_id = ""

                @pyqtProperty(bool, notify=state_changed)
                def open(self):
                    return self._open

                @pyqtProperty(str, notify=state_changed)
                def node_id(self):
                    return self._node_id

                @pyqtSlot(str, result=bool)
                def request_toggle_for_node(self, node_id):
                    self._open = True
                    self._node_id = str(node_id)
                    self.state_changed.emit()
                    return True

                def close(self):
                    self._open = False
                    self.state_changed.emit()

            bridge = ViewerSessionBridgeStub()
            fullscreen_bridge = ContentFullscreenBridgeStub()
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)
            engine.rootContext().setContextProperty("contentFullscreenBridge", fullscreen_bridge)
            viewerHostServiceStub.session_bridge = bridge
            canvas_item, _scene_bridge = create_viewer_canvas(selected=True)
            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            host.setProperty("canvasItem", canvas_item)
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            viewport = host.findChild(QObject, "graphNodeViewerViewport")
            status_text = host.findChild(QObject, "graphNodeViewerStatusText")
            assert surface is not None
            assert viewport is not None
            assert status_text is not None

            def dispatch(action_id):
                QMetaObject.invokeMethod(surface, "dispatchSurfaceAction", Q_ARG("QVariant", action_id))

            window = attach_host_to_window(host, width=640, height=480)
            try:
                QTest.mouseDClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(viewport),
                )
                settle_events(8)
                viewerHostServiceStub._overlay_ready = True
                viewerHostServiceStub._viewer_overlay_revision += 1
                viewerHostServiceStub.state_changed.emit()
                settle_events(4)
                assert bool(surface.property("inlineLiveRequested"))
                assert bool(surface.property("liveSurfaceActive"))
                assert status_text.property("text") == "Live mode - click outside the node to return to preview"
                baseline_active_calls = list(viewerHostServiceStub.active_calls)
                baseline_session_calls = list(bridge.embedded_interaction_calls)

                for action_id in ("playPause", "step", "cameraIso", "cameraFit", "screenshot", "copyImage", "detach"):
                    dispatch(action_id)
                    settle_events(4)
                    assert bool(surface.property("inlineLiveRequested")), action_id
                    assert bool(surface.property("embeddedInteractionActive")), action_id
                    assert viewerHostServiceStub.active_calls == baseline_active_calls, action_id
                    assert bridge.embedded_interaction_calls == baseline_session_calls, action_id

                assert viewerHostServiceStub.detached_calls == ["node_viewer_surface_host"]
                assert bool(surface.property("liveSurfaceActive"))

                dispatch("fullscreen")
                settle_events(5)
                assert bool(fullscreen_bridge.open)
                assert bool(surface.property("inlineLiveRequested"))
                assert bool(surface.property("embeddedInteractionActive"))
                assert not bool(surface.property("liveSurfaceActive"))
                assert viewerHostServiceStub.active_calls == baseline_active_calls
                assert bridge.embedded_interaction_calls == baseline_session_calls

                fullscreen_bridge.close()
                settle_events(5)
                assert bool(surface.property("inlineLiveRequested"))
                assert bool(surface.property("embeddedInteractionActive"))
                assert bool(surface.property("liveSurfaceActive"))
                assert viewerHostServiceStub.active_calls == baseline_active_calls
                assert bridge.embedded_interaction_calls == baseline_session_calls

                action_ids = [action["id"] for action in variant_list(host.property("availableActions"))]
                host.setProperty("toolbarActive", True)
                payload = variant_value(host.property("nodeData"))
                payload["collapsed"] = True
                host.setProperty("nodeData", payload)
                settle_events(4)
                assert host.findChild(QObject, "graphNodeViewerSurface") is surface, "Collapsed viewer lost its action owner"
                assert not surface.isVisible()
                assert not surface.property("embeddedInteractionActive"), "Hidden viewer kept embedded interaction"
                assert not surface.property("liveSurfaceActive"), "Hidden viewer kept its native surface"
                assert [action["id"] for action in variant_list(host.property("availableActions"))] == action_ids
                payload["collapsed"] = False
                host.setProperty("nodeData", payload)
                settle_events(4)
                assert surface.isVisible(), "Expanded viewer body stayed hidden"
                assert [action["id"] for action in variant_list(host.property("availableActions"))] == action_ids
            finally:
                dispose_host_window(host, window)
                canvas_item.deleteLater()
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_viewer_surface_requires_proxy_viewport_double_click_for_inline_live(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-explicit-inline-live",
            """
            from PyQt6.QtCore import Qt
            from PyQt6.QtTest import QTest

            bridge = ViewerSessionBridgeStub()
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)
            viewerHostServiceStub.session_bridge = bridge
            viewerHostServiceStub._cached_preview_source = ""
            viewerHostServiceStub._preview_cache_revision = 0

            canvas_item, scene_bridge = create_viewer_canvas(selected=True, zoom=0.25)
            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            host.setProperty("canvasItem", canvas_item)
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            viewport = host.findChild(QObject, "graphNodeViewerViewport")
            headline = host.findChild(QObject, "graphNodeViewerSurfaceHeadline")
            assert surface is not None
            assert viewport is not None
            assert headline is not None

            interactions = []
            host.nodeClicked.connect(lambda node_id, additive: interactions.append((str(node_id), bool(additive))))

            window = attach_host_to_window(host, width=640, height=480)
            try:
                settle_events(8)
                assert bool(host.property("isSelected"))
                assert bool(surface.property("proxySurfaceActive"))
                assert bool(surface.property("viewerShowsPlaceholder"))
                assert headline.property("text") == "Double-click to activate 3D view"
                assert not bool(surface.property("inlineLiveRequested"))
                assert not bool(surface.property("embeddedInteractionActive"))
                assert viewerHostServiceStub.active_calls == []

                QTest.mouseMove(window, item_scene_point(viewport))
                settle_events(4)
                assert viewerHostServiceStub.active_calls == []

                QTest.mouseClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(viewport),
                )
                settle_events(4)
                assert interactions == [("node_viewer_surface_host", False)]
                assert not bool(surface.property("inlineLiveRequested"))
                assert viewerHostServiceStub.active_calls == []

                QTest.mouseDClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    host_scene_point(host, 24.0, 12.0),
                )
                settle_events(4)
                assert not bool(surface.property("inlineLiveRequested"))
                assert viewerHostServiceStub.active_calls == []

                QTest.mouseDClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(viewport),
                )
                settle_events(8)
                assert bool(surface.property("inlineLiveRequested"))
                assert bool(surface.property("embeddedInteractionActive"))
                assert viewerHostServiceStub.active_calls == [("node_viewer_surface_host", True)]
                assert bridge.embedded_interaction_calls == [("node_viewer_surface_host", True)]

                viewerHostServiceStub._overlay_ready = True
                viewerHostServiceStub._viewer_overlay_revision += 1
                viewerHostServiceStub.state_changed.emit()
                settle_events(4)
                assert bool(surface.property("liveSurfaceActive"))

                bridge._set_state(live_mode="proxy", options={"live_mode": "proxy"})
                settle_events(8)
                assert not bool(surface.property("inlineLiveRequested"))
                assert viewerHostServiceStub.active_calls[-1] == ("node_viewer_surface_host", False)

                QTest.mouseDClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(viewport),
                )
                settle_events(8)
                assert bool(surface.property("inlineLiveRequested"))

                scene_bridge.setProperty("selected_node_lookup", {})
                settle_events(8)
                assert not bool(surface.property("inlineLiveRequested"))
                assert not bool(surface.property("embeddedInteractionActive"))
                assert viewerHostServiceStub.active_calls[-1] == ("node_viewer_surface_host", False)

                QTest.mouseDClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(viewport),
                )
                settle_events(8)
                assert not bool(host.property("isSelected"))
                assert not bool(surface.property("inlineLiveRequested"))
                assert viewerHostServiceStub.active_calls.count(("node_viewer_surface_host", True)) == 2

                scene_bridge.setProperty(
                    "selected_node_lookup",
                    {"node_viewer_surface_host": True},
                )
                QTest.mouseMove(window, item_scene_point(viewport))
                settle_events(8)
                assert bool(host.property("isSelected"))
                assert not bool(surface.property("inlineLiveRequested"))
                assert viewerHostServiceStub.active_calls.count(("node_viewer_surface_host", True)) == 2

                QTest.mouseDClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(viewport),
                )
                settle_events(8)
                assert bool(surface.property("inlineLiveRequested"))
                bridge._set_state(session_id="session::replacement")
                settle_events(8)
                assert not bool(surface.property("inlineLiveRequested"))
                assert viewerHostServiceStub.active_calls[-1] == ("node_viewer_surface_host", False)

                QTest.mouseDClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(viewport),
                )
                settle_events(8)
                assert bool(surface.property("inlineLiveRequested"))
                bridge._set_state(
                    phase="blocked",
                    live_open_status="blocked",
                    live_open_blocker={"rerun_required": True},
                )
                settle_events(8)
                assert bool(surface.property("viewerRunRequired"))
                assert not bool(surface.property("inlineLiveRequested"))
                assert viewerHostServiceStub.active_calls[-1] == ("node_viewer_surface_host", False)
            finally:
                dispose_host_window(host, window)
                canvas_item.deleteLater()
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_viewer_surface_keeps_cached_preview_raster_during_drag(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-drag-keeps-proxy-image",
            """
            from PyQt6.QtCore import Qt
            from PyQt6.QtTest import QTest

            bridge = ViewerSessionBridgeStub()
            bridge._set_state(
                cache_state="live_ready",
                options={"live_mode": "proxy"},
                summary={"camera": {"zoom": 1.2}},
            )
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)
            viewerHostServiceStub.session_bridge = bridge

            canvas_item, _scene_bridge = create_viewer_canvas(selected=True)
            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            host.setProperty("canvasItem", canvas_item)
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            viewport = host.findChild(QObject, "graphNodeViewerViewport")
            cached_image = host.findChild(QObject, "graphNodeViewerCachedPreviewImage")
            assert surface is not None
            assert viewport is not None
            assert cached_image is not None
            assert host.findChild(QObject, "graphNodeViewerTransientProxyPane") is None

            def source_text():
                source = cached_image.property("source")
                return source.toString() if hasattr(source, "toString") else str(source)

            window = attach_host_to_window(host, width=640, height=480)
            try:
                settle_events(8)
                assert bool(surface.property("proxySurfaceActive"))
                assert bool(surface.property("cachedPreviewVisible"))
                cached_source_text = source_text()
                assert cached_source_text.startswith("image://viewer-preview-cache/preview?")
                assert bool(cached_image.property("visible"))

                QTest.mouseDClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(viewport),
                )
                settle_events(8)
                assert bool(surface.property("inlineLiveRequested"))

                viewerHostServiceStub._overlay_ready = True
                viewerHostServiceStub._viewer_overlay_revision += 1
                viewerHostServiceStub.state_changed.emit()
                settle_events(6)
                assert bool(surface.property("liveSurfaceActive"))
                assert not bool(surface.property("proxySurfaceActive"))
                assert not bool(surface.property("cachedPreviewVisible"))
                assert not bool(cached_image.property("visible"))
                assert source_text() == cached_source_text
                baseline_active_calls = list(viewerHostServiceStub.active_calls)
                baseline_session_calls = list(bridge.embedded_interaction_calls)

                header_point = host_scene_point(host, 18.0, 12.0)
                drag_point = header_point + QPoint(18, 0)
                QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, header_point)
                QTest.mouseMove(window, drag_point)
                assert bool(host.property("hostDragActive"))
                canvas_item.setProperty("nativeOverlaySuppressionActive", True)
                settle_events(3)
                assert bool(surface.property("embeddedInteractionActive"))
                assert not bool(surface.property("liveSurfaceActive"))
                assert bool(surface.property("proxySurfaceActive"))
                assert bool(surface.property("cachedPreviewVisible"))
                assert bool(cached_image.property("visible"))
                assert bool(cached_image.property("cache"))
                assert variant_list(surface.property("viewerInteractiveRects")) == []
                assert viewerHostServiceStub.active_calls == baseline_active_calls
                assert bridge.embedded_interaction_calls == baseline_session_calls
                assert source_text() == cached_source_text
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, drag_point)
                canvas_item.setProperty("nativeOverlaySuppressionActive", False)
                settle_events(8)
                assert bool(surface.property("inlineLiveRequested"))
                assert bool(surface.property("embeddedInteractionActive"))
                assert bool(surface.property("liveSurfaceActive"))
                assert viewerHostServiceStub.active_calls == baseline_active_calls
                assert bridge.embedded_interaction_calls == baseline_session_calls
            finally:
                dispose_host_window(host, window)
                canvas_item.deleteLater()
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_viewer_surface_transient_suppression_never_changes_explicit_session_state(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-local-transient-suppression",
            """
            from PyQt6.QtCore import Qt
            from PyQt6.QtTest import QTest

            bridge = ViewerSessionBridgeStub()
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)
            viewerHostServiceStub.session_bridge = bridge
            canvas_item, _scene_bridge = create_viewer_canvas(selected=True)
            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            host.setProperty("canvasItem", canvas_item)
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            viewport = host.findChild(QObject, "graphNodeViewerViewport")
            cached_image = host.findChild(QObject, "graphNodeViewerCachedPreviewImage")
            assert surface is not None
            assert viewport is not None
            assert cached_image is not None

            def source_text():
                source = cached_image.property("source")
                return source.toString() if hasattr(source, "toString") else str(source)

            window = attach_host_to_window(host, width=640, height=480)
            try:
                QTest.mouseDClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(viewport),
                )
                settle_events(8)
                viewerHostServiceStub._overlay_ready = True
                viewerHostServiceStub._viewer_overlay_revision += 1
                viewerHostServiceStub.state_changed.emit()
                settle_events(4)
                assert bool(surface.property("inlineLiveRequested"))
                assert bool(surface.property("embeddedInteractionActive"))
                assert bool(surface.property("liveSurfaceActive"))
                cached_source_text = source_text()
                assert cached_source_text.startswith("image://viewer-preview-cache/preview?")

                baseline_active_calls = list(viewerHostServiceStub.active_calls)
                baseline_session_calls = list(bridge.embedded_interaction_calls)
                baseline_updates = list(bridge.update_calls)
                for category in ("pan", "wheel", "box_zoom", "node_drag", "resize", "wire_drag"):
                    canvas_item.setProperty("nativeOverlaySuppressionActive", True)
                    settle_events(3)
                    assert bool(surface.property("inlineLiveRequested")), category
                    assert bool(surface.property("embeddedInteractionActive")), category
                    assert not bool(surface.property("liveSurfaceActive")), category
                    assert bool(cached_image.property("visible")), category
                    assert source_text() == cached_source_text, category
                    assert viewerHostServiceStub.active_calls == baseline_active_calls, category
                    assert bridge.embedded_interaction_calls == baseline_session_calls, category
                    assert bridge.update_calls == baseline_updates, category

                    if category == "wheel":
                        # A response from the superseded pre-fix proxy request may
                        # arrive during the canvas recovery window. It must not
                        # erase the explicit request or trigger another command.
                        bridge._set_state(live_mode="proxy", options={"live_mode": "proxy"})
                        settle_events(3)
                        assert bool(surface.property("inlineLiveRequested"))
                        bridge._set_state(live_mode="full", options={"live_mode": "full"})

                    canvas_item.setProperty("nativeOverlaySuppressionActive", False)
                    settle_events(5)
                    assert bool(surface.property("inlineLiveRequested")), category
                    assert bool(surface.property("embeddedInteractionActive")), category
                    assert bool(surface.property("liveSurfaceActive")), category
                    assert source_text() == cached_source_text, category
                    assert viewerHostServiceStub.active_calls == baseline_active_calls, category
                    assert bridge.embedded_interaction_calls == baseline_session_calls, category
                    assert bridge.update_calls == baseline_updates, category
            finally:
                dispose_host_window(host, window)
                canvas_item.deleteLater()
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_viewer_surface_defaults_to_closed_bridge_contract_without_context_property(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-default-contract",
            """
            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            status_text = host.findChild(QObject, "graphNodeViewerStatusText")
            mode_label = host.findChild(QObject, "graphNodeViewerSurfaceModeLabel")
            assert surface is not None
            assert host.findChild(QObject, "graphNodeViewerSessionButton") is None
            assert host.findChild(QObject, "graphNodeViewerMoreButton") is None
            assert status_text is not None
            assert mode_label is not None

            contract = variant_value(surface.property("viewerSurfaceContract"))
            bridge_binding = variant_value(surface.property("viewerBridgeBinding"))
            interactive_rects = variant_list(surface.property("viewerInteractiveRects"))
            actions = variant_list(surface.property("surfaceActions"))

            assert not bool(surface.property("viewerBridgeAvailable"))
            assert surface.property("viewerPhase") == "closed"
            assert bool(surface.property("viewerShowsPlaceholder"))
            assert status_text.property("text") == "Viewer bridge unavailable"
            assert mode_label.property("text") == "Overlay"
            assert contract["bridge_binding"]["phase"] == "closed"
            assert not bool(contract["bridge_binding"]["bridge_available"])
            assert bridge_binding["phase"] == "closed"
            assert interactive_rects == []
            open_session_action = next(action for action in actions if action["id"] == "openSession")
            assert not bool(open_session_action["enabled"])
            """,
        )

    def test_viewer_surface_contract_live_rect_tracks_inner_viewport_frame(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-live-rect-viewport",
            """
            bridge = ViewerSessionBridgeStub()
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)

            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            body_frame = host.findChild(QObject, "graphNodeViewerBodyFrame")
            viewport = host.findChild(QObject, "graphNodeViewerViewport")
            assert surface is not None
            assert body_frame is not None
            assert viewport is not None

            window = attach_host_to_window(host, width=640, height=480)
            try:
                contract = variant_value(surface.property("viewerSurfaceContract"))
                live_rect = contract["live_rect"]
                assert abs(float(live_rect["width"]) - float(viewport.property("width"))) <= 0.5
                assert abs(float(live_rect["height"]) - float(viewport.property("height"))) <= 0.5
                assert float(live_rect["y"]) > float(body_frame.property("y"))
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_viewer_surface_body_frame_uses_live_host_metrics_when_payload_rect_is_stale(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-stale-body-rect",
            """
            bridge = ViewerSessionBridgeStub()
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)

            payload = viewer_payload()
            payload["height"] = 320.0
            payload["viewer_surface"] = {
                "body_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
                "proxy_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
                "live_rect": {"x": 14.0, "y": 30.0, "width": 268.0, "height": 176.0},
                "overlay_target": "body",
                "proxy_surface_supported": True,
                "live_surface_supported": True,
            }

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            body_frame = host.findChild(QObject, "graphNodeViewerBodyFrame")
            assert surface is not None
            assert body_frame is not None

            window = attach_host_to_window(host, width=640, height=480)
            try:
                metrics = variant_value(host.property("surfaceMetrics"))
                contract = variant_value(surface.property("viewerSurfaceContract"))
                body_height = float(body_frame.property("height"))

                assert abs(float(metrics["body_height"]) - 260.0) < 0.1, metrics
                assert abs(body_height - float(metrics["body_height"])) < 0.1
                assert abs(float(contract["body_rect"]["height"]) - float(metrics["body_height"])) < 0.1
                assert float(contract["body_rect"]["height"]) > 176.0
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_viewer_surface_uses_viewer_preview_cache_when_png_ref_is_absent(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-preview-ref-fallback",
            """
            bridge = ViewerSessionBridgeStub()
            bridge._set_state(
                cache_state="proxy_ready",
                options={"live_mode": "proxy"},
                data_refs={"preview": "C:/legacy/viewer_preview_should_not_drive_qml.png"},
            )
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)

            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            cached_image = host.findChild(QObject, "graphNodeViewerCachedPreviewImage")
            assert surface is not None
            assert cached_image is not None

            window = attach_host_to_window(host, width=640, height=480)
            try:
                settle_events(5)
                assert surface.property("viewerLiveMode") == "proxy"
                assert not bool(surface.property("embeddedInteractionActive"))
                assert bool(surface.property("proxySurfaceActive"))
                assert bool(surface.property("viewerPreviewAvailable"))
                assert bool(cached_image.property("visible"))
                cached_image_source = cached_image.property("source")
                cached_image_source_text = cached_image_source.toString() if hasattr(cached_image_source, "toString") else str(cached_image_source)
                assert cached_image_source_text.startswith("image://viewer-preview-cache/preview?")
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_viewer_surface_confirms_cached_preview_swap_to_host_service(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-preview-swap-confirmation",
            """
            bridge = ViewerSessionBridgeStub()
            bridge._set_state(
                cache_state="proxy_ready",
                options={"live_mode": "proxy"},
            )
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)

            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            cached_image = host.findChild(QObject, "graphNodeViewerCachedPreviewImage")
            assert surface is not None
            assert cached_image is not None

            window = attach_host_to_window(host, width=640, height=480)
            try:
                settle_events(5)
                assert bool(surface.property("cachedPreviewVisible"))
                initial_source = viewerHostServiceStub._cached_preview_source
                assert viewerHostServiceStub.preview_swap_calls[-1] == (
                    "node_viewer_surface_host",
                    initial_source,
                ), viewerHostServiceStub.preview_swap_calls

                # A live-exit capture publishes a new revision; the surface
                # must confirm the swapped source back to the host service.
                swapped_source = (
                    "image://viewer-preview-cache/preview?workspace=ws_main"
                    "&node=node_viewer_surface_host&revision=2"
                )
                viewerHostServiceStub._cached_preview_source = swapped_source
                viewerHostServiceStub._preview_cache_revision += 1
                viewerHostServiceStub.preview_cache_changed.emit()
                settle_events(5)

                assert viewerHostServiceStub.preview_swap_calls[-1] == (
                    "node_viewer_surface_host",
                    swapped_source,
                ), viewerHostServiceStub.preview_swap_calls
                cached_image_source = cached_image.property("source")
                cached_image_source_text = cached_image_source.toString() if hasattr(cached_image_source, "toString") else str(cached_image_source)
                assert cached_image_source_text == swapped_source
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_session_projection_seed_survives_synchronous_state_flip_without_binding_loop(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-projection-seed-no-binding-loop",
            """
            from PyQt6.QtCore import Qt, qInstallMessageHandler
            from PyQt6.QtTest import QTest

            qt_messages = []
            def capture_qt_message(_message_type, _context, message):
                qt_messages.append(str(message))

            previous_message_handler = qInstallMessageHandler(capture_qt_message)
            bridge = ViewerSessionBridgeStub()
            bridge._set_state(
                backend_id="corex_scene",
                cache_state="proxy_ready",
                live_mode="proxy",
                data_refs={},
                options={"live_mode": "proxy"},
            )
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)
            viewerHostServiceStub._cached_preview_source = ""
            viewerHostServiceStub._preview_cache_revision = 0
            # Mirror the real service chain: set_embedded_interaction_active
            # forwards to the session bridge, which re-emits sessions_changed
            # synchronously.
            viewerHostServiceStub.session_bridge = bridge

            canvas_item, _scene_bridge = create_viewer_canvas(selected=True)
            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            host.setProperty("canvasItem", canvas_item)
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            viewport = host.findChild(QObject, "graphNodeViewerViewport")
            assert surface is not None
            assert viewport is not None

            window = attach_host_to_window(host, width=640, height=480)
            try:
                settle_events(8)
                assert viewerHostServiceStub.active_calls == []
                QTest.mouseDClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(viewport),
                )
                settle_events(8)
                assert bool(surface.property("embeddedInteractionActive")), (
                    "explicit request did not activate",
                    viewerHostServiceStub.active_calls,
                )
                qt_messages.clear()

                # A synchronous sessions_changed emission (execution event
                # closing the session) flips embeddedInteractionActive inside
                # the bridgeSessionProjectionSeed binding-update cascade. The
                # deactivation call must not re-enter sessions_changed while
                # that binding is still updating.
                bridge._set_state(phase="closing", last_command="close")
                settle_events(8)

                assert not bool(surface.property("embeddedInteractionActive"))
                assert viewerHostServiceStub.active_calls[-1] == ("node_viewer_surface_host", False), viewerHostServiceStub.active_calls
            finally:
                dispose_host_window(host, window)
                canvas_item.deleteLater()
                engine.deleteLater()
                app.processEvents()
                qInstallMessageHandler(previous_message_handler)
            assert not any(
                'Binding loop detected for property "bridgeSessionProjectionSeed"' in message
                for message in qt_messages
            ), qt_messages
            """,
        )

    def test_viewer_surface_compact_strip_reports_error_and_run_required_states(self) -> None:
        self._run_qml_probe(
            "viewer-surface-host-error-run-required",
            """
            bridge = ViewerSessionBridgeStub()
            engine.rootContext().setContextProperty("viewerSessionBridge", bridge)

            host = create_component(graph_node_host_qml_path, {"nodeData": viewer_payload()})
            surface = host.findChild(QObject, "graphNodeViewerSurface")
            status_text = host.findChild(QObject, "graphNodeViewerStatusText")
            mode_label = host.findChild(QObject, "graphNodeViewerSurfaceModeLabel")
            headline = host.findChild(QObject, "graphNodeViewerSurfaceHeadline")
            hint = host.findChild(QObject, "graphNodeViewerSurfaceHint")
            assert surface is not None
            assert host.findChild(QObject, "graphNodeViewerSessionButton") is None
            assert host.findChild(QObject, "graphNodeViewerMoreButton") is None
            assert status_text is not None
            assert mode_label is not None
            assert headline is not None
            assert hint is not None

            def open_session_action():
                actions = variant_list(surface.property("surfaceActions"))
                return next(action for action in actions if action["id"] == "openSession")

            window = attach_host_to_window(host, width=640, height=480)
            try:
                viewerHostServiceStub._last_error = "native viewer bind failed"
                viewerHostServiceStub.last_error_changed.emit()
                settle_events(5)
                assert surface.property("viewerLastError") == "native viewer bind failed"
                assert status_text.property("text") == "native viewer bind failed"

                viewerHostServiceStub._last_error = ""
                viewerHostServiceStub.last_error_changed.emit()
                bridge._last_error = "launch failed"
                bridge.last_error_changed.emit()
                bridge._set_state(phase="error", last_command="open")
                settle_events(5)
                assert bool(surface.property("viewerShowsPlaceholder"))
                assert status_text.property("text") == "launch failed"
                assert mode_label.property("text") == "Preview"
                assert headline.property("text") == "launch failed"
                assert hint.property("text") == "launch failed"

                bridge._last_error = ""
                bridge.last_error_changed.emit()
                bridge._set_state(
                    phase="blocked",
                    cache_state="proxy_ready",
                    live_mode="proxy",
                    live_open_status="blocked",
                    live_open_blocker={
                        "code": "rerun_required",
                        "reason": "Live viewer transport is unavailable and requires rerun.",
                        "rerun_required": True,
                    },
                    transport={"kind": "bundle", "backend_id": "backend.viewer"},
                    summary={
                        "result_name": "Displacement",
                        "set_label": "Set 4",
                        "rerun_required": True,
                        "live_transport_release_reason": "project_reload",
                    },
                    options={"rerun_required": True},
                )
                settle_events(5)
                assert bool(surface.property("viewerShowsPlaceholder"))
                assert not bool(open_session_action()["enabled"])
                assert status_text.property("text") == "Rerun required before live open"
                assert mode_label.property("text") == "Blocked"
                assert headline.property("text") == "Rerun required before live open"
                assert "requires rerun" in str(hint.property("text"))
                assert host.findChild(QObject, "graphNodeViewerResultMeta") is None
                assert host.findChild(QObject, "graphNodeViewerSelectionMeta") is None
                assert host.findChild(QObject, "graphNodeViewerStepMeta") is None
                assert host.findChild(QObject, "graphNodeViewerStatusMeta") is None
                assert variant_list(surface.property("viewerInteractiveRects")) == []
            finally:
                dispose_host_window(host, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )


if __name__ == "__main__":
    unittest.main()
