from __future__ import annotations

import hashlib
from pathlib import Path

from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui_qml.graph_surface_metrics import node_surface_metrics, surface_port_local_point
from ea_node_editor.ui_qml.graph_scene.command_bridge import GraphSceneCommandBridge
from ea_node_editor.ui_qml.surface_contracts import surface_spec_for_values
from tests.graph_surface.environment import PassiveGraphSurfaceHostTestBase


# Generated once with FFmpeg 8.1.1 for deterministic decoded-media tests:
# ffmpeg -f lavfi -i testsrc2=size=160x90:rate=30 -t 5 -c:v libx264 -preset veryslow -crf 30 -pix_fmt yuv420p -movflags +faststart -an video-playback.mp4
_REAL_VIDEO_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "media" / "video-playback.mp4"
_REAL_VIDEO_FIXTURE_SHA256 = "8e57fae7a077c667a4f922762fb344a9fd073a78037df676144a7469bfd6f9b4"


class MediaPanelQmlSurfaceTests(PassiveGraphSurfaceHostTestBase):
    def test_media_panel_uses_stable_panel_contract(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec("media.panel")
        node = NodeInstance(
            node_id="media",
            type_id="media.panel",
            title="Media Panel",
            x=0.0,
            y=0.0,
        )
        metrics = node_surface_metrics(node, spec)
        surface = surface_spec_for_values(
            type_id="media.panel",
            family="media",
            variant="media_panel",
        )

        assert (metrics.default_width, metrics.default_height) == (340.0, 306.0)
        assert (metrics.min_width, metrics.min_height) == (260.0, 272.0)
        assert metrics.body_height == 232.0
        assert metrics.port_height == 18.0
        assert metrics.port_center_offset == 9.0
        assert metrics.port_top + metrics.port_height + metrics.body_bottom_margin == metrics.default_height
        _source_x, source_y = surface_port_local_point(node, spec, "source", {node.node_id: node})
        assert source_y - metrics.port_dot_radius >= metrics.port_top
        hidden_source_node = node.clone()
        hidden_source_node.exposed_ports = {"source": False}
        hidden_source_metrics = node_surface_metrics(hidden_source_node, spec)
        assert hidden_source_metrics.default_height == 288.0
        assert surface.fullscreen.content_kind == "media"
        assert surface.metadata == {"panel_like": True, "suppress_run_action": True}

        repo_root = Path(__file__).resolve().parents[1]
        resize_source = (
            repo_root
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "GraphNodeResizeHandle.qml"
        ).read_text(encoding="utf-8")
        assert "loadedSurfaceItem.aspectRatioLocked" in resize_source
        assert "isImagePanelSurface" not in resize_source
        host_source = (
            repo_root
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "GraphNodeHost.qml"
        ).read_text(encoding="utf-8")
        preference_source = (
            repo_root
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph_canvas"
            / "GraphCanvasPreferenceFacts.qml"
        ).read_text(encoding="utf-8")
        normalize_source = (
            repo_root
            / "ea_node_editor"
            / "ui_qml"
            / "graph_scene_payload"
            / "normalize.py"
        ).read_text(encoding="utf-8")
        assert "isMediaPanelSurface" not in host_source
        assert "mediaPanelSourceInputExposed" not in preference_source
        assert "mediaPanelAutoplayAnimations" in preference_source
        assert "_normalized_unfocused_behavior" not in normalize_source
        assert "_VIDEO_UNFOCUSED_BEHAVIORS" not in normalize_source
        action_router_source = (
            repo_root
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph_canvas"
            / "GraphCanvasActionRouter.qml"
        ).read_text(encoding="utf-8")
        assert "_isReadyPdfMediaPayload" in action_router_source
        assert 'String(payload.type_id || "") === "media.panel"' in action_router_source
        assert "sourceResolution.resolved_source_url" in action_router_source
        assert (
            GraphSceneCommandBridge.staticMetaObject.indexOfMethod(
                b"set_exposed_port(QString,QString,bool)"
            )
            >= 0
        )

    def test_exposed_source_port_stays_below_the_viewport_with_a_full_hit_target(self) -> None:
        self._run_qml_probe(
            "media-panel-exposed-source-port-body-spacing",
            """
            from PyQt6.QtCore import QPointF, pyqtProperty
            from PyQt6.QtGui import QColor, QImage
            from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder

            class MediaCanvas(QQuickItem):
                def __init__(self, node_id, image_url):
                    super().__init__()
                    self._node_id = node_id
                    self._image_url = image_url

                @pyqtProperty("QVariantMap", constant=True)
                def executionFacts(self):
                    return {
                        "mediaPanelSourceLookup": {
                            self._node_id: {
                                "authority": "input",
                                "input_exposed": True,
                                "input_connected": True,
                                "state": "ready",
                                "media_kind": "image",
                                "resolved_source_url": self._image_url,
                                "preview_source_url": self._image_url,
                            }
                        },
                        "portFlowStateLookup": {},
                    }

            image_path = Path.cwd() / "artifacts" / "media-panel-port-spacing.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image = QImage(8, 6, QImage.Format.Format_ARGB32)
            image.fill(QColor("#5da9ff"))
            assert image.save(str(image_path))

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            node = model.add_node(workspace_id, "media.panel", "Media Panel", 0.0, 0.0)
            payload = GraphScenePayloadBuilder().rebuild_models(
                model=model,
                registry=registry,
                workspace_id=workspace_id,
                scope_path=(),
                graph_theme_bridge=None,
            )[0][0]
            assert payload["node_id"] == node.node_id

            canvas = MediaCanvas(node.node_id, QUrl.fromLocalFile(str(image_path)).toString())
            host = create_component(graph_node_host_qml_path, {"nodeData": payload, "canvasItem": canvas})
            host.setWidth(float(payload["width"]))
            host.setHeight(float(payload["height"]))
            window = attach_host_to_window(host, 480, 360)
            try:
                settle_events(10)
                viewport = named_item(host, "graphNodeMediaPreviewViewport")
                source_dot = named_item(host, "graphNodeInputPortDot", "source")
                source_mouse = named_item(host, "graphNodeInputPortMouseArea", "source")
                viewport_bottom = viewport.mapToItem(host, QPointF(0.0, viewport.height())).y()
                source_top = source_dot.mapToItem(host, QPointF(0.0, 0.0)).y()
                source_center = source_dot.mapToItem(
                    host,
                    QPointF(source_dot.width() * 0.5, source_dot.height() * 0.5),
                )
                assert abs(viewport_bottom - float(payload["surface_metrics"]["port_top"])) < 0.1
                assert viewport_bottom <= source_top
                assert source_center.y() > host.height() * 0.75
                assert source_mouse.property("enabled")
                assert source_mouse.width() >= 24.0
                assert source_mouse.height() >= 24.0
                clicked_ports = []
                host.portClicked.connect(
                    lambda _node_id, port_key, direction, *_rest: clicked_ports.append(
                        (port_key, direction)
                    )
                )
                mouse_click(window, item_scene_point(source_mouse))
                assert clicked_ports == [("source", "in")]
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_fullscreen_qml_dispatches_only_from_media_payload_kind(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "ea_node_editor"
            / "ui_qml"
            / "ContentFullscreenOverlay.qml"
        ).read_text(encoding="utf-8")

        assert 'readonly property bool mediaContentActive: root.contentKind === "media"' in source
        assert 'String(root.mediaPayload.media_kind || "")' in source
        assert "PassiveComponents.GraphMediaVideoFullscreenRenderer" in source
        assert 'root.contentKind === "image"' not in source
        assert 'root.contentKind === "pdf"' not in source
        assert 'root.contentKind === "video"' not in source

        passive_root = (
            Path(__file__).resolve().parents[1]
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "passive"
        )
        dispatcher_source = (passive_root / "GraphMediaPanelSurface.qml").read_text(
            encoding="utf-8"
        )
        image_source = (passive_root / "GraphMediaImageRenderer.qml").read_text(
            encoding="utf-8"
        )
        video_source = (passive_root / "GraphMediaVideoRenderer.qml").read_text(
            encoding="utf-8"
        )
        fullscreen_video_source = (
            passive_root / "GraphMediaVideoFullscreenRenderer.qml"
        ).read_text(encoding="utf-8")
        playback_core_source = (
            passive_root / "GraphMediaVideoPlaybackCore.qml"
        ).read_text(encoding="utf-8")
        assert "if (sourceInputExposed || !cropToolAvailable" in image_source
        assert "if (sourceInputExposed || !localSourceActive" in video_source
        assert "if (sourceInputExposed\n" in fullscreen_video_source
        assert "function _saveTrimmedClipCopy()" in video_source
        assert "function _saveTrimmedClipCopy()" in fullscreen_video_source
        assert "onFullscreenOpened" not in dispatcher_source
        assert "GraphMediaVideoPlaybackCore" in video_source
        assert "GraphMediaVideoPlaybackCore" in fullscreen_video_source
        assert "MediaPlayer {" not in video_source
        assert "MediaPlayer {" not in fullscreen_video_source
        assert playback_core_source.count("MediaPlayer {") == 1
        assert "onMediaStatusChanged: root._scheduleSourceReadiness()" in playback_core_source
        assert "onSourceActiveChanged: _scheduleSourceReadiness()" in playback_core_source
        assert "thumbnailPrimingEnabled: root.initialPositionMs <= 0" in fullscreen_video_source
        assert "function normalizedTimelineBookmarks(value)" in playback_core_source
        assert "function enforceClipRange()" in playback_core_source

    def test_dispatcher_switches_renderers_and_routes_source_exposure(self) -> None:
        assert (
            hashlib.sha256(_REAL_VIDEO_FIXTURE.read_bytes()).hexdigest()
            == _REAL_VIDEO_FIXTURE_SHA256
        )
        self._run_qml_probe(
            "unified-media-panel-dispatch",
            """
            from PyQt6.QtCore import Q_ARG, pyqtProperty, pyqtSignal, pyqtSlot, qInstallMessageHandler
            from PyQt6.QtGui import QColor, QImage
            from PyQt6.QtMultimedia import QMediaPlayer
            from PyQt6.QtQuick import QQuickWindow
            import time

            messages = []
            previous_handler = qInstallMessageHandler(
                lambda _kind, _context, message: messages.append(str(message))
            )

            class ExposureBridge(QObject):
                def __init__(self):
                    super().__init__()
                    self.calls = []

                @pyqtSlot(str, str, bool, result=bool)
                def set_exposed_port(self, node_id, key, exposed):
                    self.calls.append((str(node_id), str(key), bool(exposed)))
                    return True

            class InlineFullscreenBridge(QObject):
                changed = pyqtSignal()
                videoFullscreenClosed = pyqtSignal(str, "QVariantMap")

                def __init__(self):
                    super().__init__()
                    self._open = False
                    self._node_id = ""
                    self._source_url = ""
                    self._transient_state = {}

                @pyqtProperty(bool, notify=changed)
                def open(self):
                    return self._open

                @pyqtProperty(str, notify=changed)
                def node_id(self):
                    return self._node_id

                @pyqtProperty(str, notify=changed)
                def content_kind(self):
                    return "media" if self._open else ""

                @pyqtProperty(str, notify=changed)
                def title(self):
                    return "Media Panel"

                @pyqtProperty("QVariantMap", notify=changed)
                def media_payload(self):
                    return {
                        "media_kind": "video",
                        "source_state": "ready",
                        "resolved_source_url": self._source_url,
                        "auto_play": False,
                        "loop": False,
                        "muted": True,
                        "volume": 1.0,
                        "playback_rate": 1.0,
                        "position_ms": 0,
                        "timeline_bookmarks": [],
                        "clip_enabled": False,
                        "clip_start_ms": 0,
                        "clip_end_ms": 0,
                        "transient_state": dict(self._transient_state),
                    } if self._open else {}

                def open_video(self, node_id, source_url, transient_state=None):
                    self._node_id = str(node_id)
                    self._source_url = str(source_url)
                    self._transient_state = dict(transient_state or {})
                    self._open = True
                    self.changed.emit()

                def close_video(self, state):
                    node_id = self._node_id
                    self._open = False
                    self._node_id = ""
                    self._source_url = ""
                    self._transient_state = {}
                    self.changed.emit()
                    self.videoFullscreenClosed.emit(node_id, dict(state))

                @pyqtSlot()
                def request_close(self):
                    self.close_video({})

                @pyqtSlot("QVariantMap", result=bool)
                def request_close_with_state(self, state):
                    self.close_video(state)
                    return True

            class RenameBridge(QObject):
                managedArtifactRenameReleaseRequested = pyqtSignal(str)
                managedArtifactRenameReleaseFinished = pyqtSignal(str)

            class MediaCanvas(PassiveSurfaceCanvasItem):
                executionFactsChanged = pyqtSignal()

                def __init__(self, resolution, node_id="node_surface_host_test"):
                    super().__init__()
                    self._resolution = dict(resolution)
                    self._node_id = str(node_id)
                    self.exposure_bridge = ExposureBridge()
                    self.rename_bridge = RenameBridge()
                    self.browse_calls = []
                    self.open_calls = []
                    self.browse_result = "C:/tmp/replacement-media.png"

                @pyqtProperty("QVariantMap", notify=executionFactsChanged)
                def executionFacts(self):
                    return {
                        "failedNodeLookup": {},
                        "runningNodeLookup": {},
                        "completedNodeLookup": {},
                        "warningNodeLookup": {},
                        "runningNodeStartedAtMsLookup": {},
                        "nodeElapsedMsLookup": {},
                        "nodeRunCountLookup": {},
                        "freshRunNodeLookup": {},
                        "propertyPresentationLookup": {},
                        "portFlowStateLookup": {},
                        "portValuePreviewLookup": {},
                        "nodeDiagnosticLookup": {},
                        "dpfWorkflowSummaryLookup": {},
                        "mediaPanelSourceLookup": {self._node_id: self._resolution},
                        "nodeExecutionRevision": 0,
                        "selectedRunPreviewVisible": False,
                        "selectedRunPreviewRows": [],
                        "selectedRunPreviewNodeLookup": {},
                    }

                @pyqtProperty(QObject, constant=True)
                def sceneCommandBridge(self):
                    return self.exposure_bridge

                @pyqtProperty(QObject, constant=True)
                def canvasCommandBridgeRef(self):
                    return self.rename_bridge

                def set_resolution(self, resolution):
                    self._resolution = dict(resolution)
                    self.executionFactsChanged.emit()

                @pyqtSlot(str, str, str, result=str)
                @pyqtSlot(str, str, str, str, result=str)
                def browseNodePropertyPath(self, node_id, key, current_path, source_mode=""):
                    self.browse_calls.append((
                        str(node_id),
                        str(key),
                        str(current_path),
                        str(source_mode),
                    ))
                    return self.browse_result

                @pyqtSlot(str, bool, result="QVariantMap")
                def openNodeSurfaceLocalFileSource(self, source, chooser):
                    self.open_calls.append((str(source), bool(chooser)))
                    return {"success": True}

            def resolution(
                kind,
                source_url,
                *,
                exposed=False,
                state="ready",
                message="",
                source_ref=None,
            ):
                return {
                    "authority": "input" if exposed else "property",
                    "input_exposed": exposed,
                    "input_connected": exposed,
                    "state": state,
                    "media_kind": kind if state == "ready" else "",
                    "source_ref": (
                        source_url if source_ref is None else source_ref
                    ) if state == "ready" else "",
                    "resolved_source_url": source_url if state == "ready" else "",
                    "preview_source_url": source_url if state == "ready" else "",
                    "message": message,
                }

            def wait_for_named(root, name, present=True, attempts=200):
                for _attempt in range(attempts):
                    settle_events(2)
                    candidate = root.findChild(QObject, name)
                    if (candidate is not None) == present:
                        return candidate
                raise AssertionError(
                    f"{name!r} present={present} did not settle; messages={messages}"
                )

            def wait_for_condition(predicate, label, attempts=400, details=None):
                for _attempt in range(attempts):
                    settle_events(2)
                    if predicate():
                        return
                    time.sleep(0.01)
                detail = details() if details is not None else None
                raise AssertionError(f"{label} did not settle; details={detail}; messages={messages}")

            image_path = Path.cwd() / "artifacts" / "media-panel-qml-test.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image = QImage(8, 6, QImage.Format.Format_ARGB32)
            image.fill(QColor("#5da9ff"))
            assert image.save(str(image_path))
            image_url = QUrl.fromLocalFile(str(image_path)).toString()
            video_path = Path.cwd() / "tests" / "fixtures" / "media" / "video-playback.mp4"
            assert video_path.is_file()
            video_url = QUrl.fromLocalFile(str(video_path)).toString()

            fullscreen_bridge = InlineFullscreenBridge()
            engine.rootContext().setContextProperty("contentFullscreenBridge", fullscreen_bridge)
            engine.rootContext().setContextProperty("tooltipCopyBridge", None)
            overlay_path = Path.cwd() / "ea_node_editor" / "ui_qml" / "ContentFullscreenOverlay.qml"
            overlay = create_component(overlay_path, {"bridgeRef": fullscreen_bridge})
            probe_window = QQuickWindow()
            probe_window.resize(900, 640)
            overlay.setParentItem(probe_window.contentItem())
            overlay.setWidth(900)
            overlay.setHeight(640)
            probe_window.show()
            settle_events(6)

            payload = node_payload(surface_family="media", surface_variant="media_panel")
            payload.update({
                "type_id": "media.panel",
                "title": "Media Panel",
                "display_name": "Media Panel",
                "runtime_behavior": "active",
                "selected": True,
                "width": 340.0,
                "height": 288.0,
                "surface_spec": surface_spec_payload_for_values(
                    type_id="media.panel",
                    family="media",
                    variant="media_panel",
                ),
                "surface_metrics": {
                    "default_width": 340.0,
                    "default_height": 288.0,
                    "min_width": 260.0,
                    "min_height": 216.0,
                    "collapsed_width": 130.0,
                    "collapsed_height": 36.0,
                    "header_height": 24.0,
                    "header_top_margin": 4.0,
                    "body_top": 44.0,
                    "body_height": 232.0,
                    "port_top": 0.0,
                    "port_height": 18.0,
                    "port_center_offset": 6.0,
                    "port_side_margin": 8.0,
                    "port_dot_radius": 5.0,
                    "resize_handle_size": 16.0,
                    "title_top": 12.0,
                    "title_height": 24.0,
                    "title_left_margin": 14.0,
                    "title_right_margin": 46.0,
                    "body_left_margin": 14.0,
                    "body_right_margin": 14.0,
                    "body_bottom_margin": 12.0,
                    "use_host_chrome": True,
                    "use_host_shadow": True,
                },
                "properties": {
                    "source": str(image_path),
                    "show_title": True,
                    "show_frame": True,
                    "fit_mode": "contain",
                    "animation_playback_mode": "pause",
                    "lock_aspect_ratio": True,
                    "page_number": 1,
                    "auto_play": False,
                    "loop": False,
                    "muted": True,
                    "volume": 1.0,
                    "playback_rate": 1.0,
                    "position_ms": 0,
                    "timeline_bookmarks": [],
                    "clip_enabled": False,
                    "clip_start_ms": 0,
                    "clip_end_ms": 0,
                },
                "ports": [],
                "inline_properties": [],
            })

            canvas = MediaCanvas(resolution("image", image_url))
            host = create_component(graph_node_host_qml_path, {"nodeData": payload, "canvasItem": canvas})
            host.setParentItem(probe_window.contentItem())
            host.setX(24)
            host.setY(24)
            settle_events(6)
            surface = wait_for_named(host, "graphNodeMediaSurface")
            image_renderer = wait_for_named(host, "graphNodeMediaImageRenderer")
            commits = []
            host.inlinePropertyCommitted.connect(
                lambda node_id, key, value: commits.append(
                    (str(node_id), str(key), str(value))
                )
            )

            def apply_committed_chrome(expected):
                assert canvas.last_committed_node_id == "node_surface_host_test"
                assert canvas.last_committed_properties == expected
                payload["properties"] = {**payload["properties"], **expected}
                assert host.setProperty("nodeData", dict(payload))
                settle_events(4)

            def assert_renderer_chrome(renderer, *, title, frame):
                actual = (
                    bool(renderer.property("surfaceShowTitle")),
                    bool(renderer.property("surfaceShowFrame")),
                    bool(renderer.property("surfaceContentOnly")),
                )
                assert actual == (title, frame, not (title or frame)), actual

            assert bool(surface.property("aspectRatioLocked"))
            assert bool(host.property("panelLikeSurface"))
            assert bool(host.property("suppressRunAction"))
            assert not bool(host.property("runnableNode"))
            assert abs(float(host.width()) - 340.0) < 0.01
            assert abs(float(host.height()) - 288.0) < 0.01
            assert_renderer_chrome(image_renderer, title=True, frame=True)

            QMetaObject.invokeMethod(
                surface,
                "dispatchSurfaceAction",
                Q_ARG("QVariant", "toggle_frame"),
            )
            apply_committed_chrome({"show_title": True, "show_frame": False})
            image_renderer = surface.property("loadedRenderer")
            assert_renderer_chrome(image_renderer, title=True, frame=False)

            QMetaObject.invokeMethod(
                surface,
                "dispatchSurfaceAction",
                Q_ARG("QVariant", "toggle_frame"),
            )
            apply_committed_chrome({"show_title": True, "show_frame": True})
            image_renderer = surface.property("loadedRenderer")
            assert_renderer_chrome(image_renderer, title=True, frame=True)

            QMetaObject.invokeMethod(
                surface,
                "dispatchSurfaceAction",
                Q_ARG("QVariant", "toggle_content_only"),
            )
            apply_committed_chrome({"show_title": False, "show_frame": False})
            image_renderer = surface.property("loadedRenderer")
            assert_renderer_chrome(image_renderer, title=False, frame=False)

            image_renderer.setProperty("cropModeActive", True)
            settle_events(3)
            assert bool(surface.property("blocksHostInteraction"))
            assert bool(host.property("surfaceInteractionLocked"))
            image_renderer.setProperty("cropModeActive", False)
            settle_events(3)
            assert not bool(surface.property("blocksHostInteraction"))

            QMetaObject.invokeMethod(
                host,
                "nodeOpenRequested",
                Q_ARG("QString", "node_surface_host_test"),
            )
            settle_events(3)
            assert len(canvas.browse_calls) == 1
            assert canvas.browse_calls[0][1] == "source"
            assert commits[-1] == (
                "node_surface_host_test",
                "source",
                canvas.browse_result,
            )

            canvas.set_resolution(resolution("image", image_url, exposed=True))
            QMetaObject.invokeMethod(
                host,
                "nodeOpenRequested",
                Q_ARG("QString", "node_surface_host_test"),
            )
            settle_events(3)
            assert len(canvas.browse_calls) == 1
            assert len(commits) == 1
            actions = variant_list(surface.property("surfaceActions"))
            open_action = next(action for action in actions if action["id"] == "openSourceMenu")
            assert bool(open_action["enabled"])

            canvas.set_resolution(resolution("image", image_url))
            actions = variant_list(surface.property("surfaceActions"))
            open_action = next(action for action in actions if action["id"] == "openSourceMenu")
            assert bool(open_action["enabled"])
            QMetaObject.invokeMethod(
                surface,
                "dispatchSurfaceAction",
                Q_ARG("QVariant", "openSource"),
            )
            settle_events(3)
            assert canvas.open_calls[-1] == (image_url, False)

            canvas.set_resolution(
                resolution("image", image_url, source_ref="temp://managed-media")
            )
            actions = variant_list(surface.property("surfaceActions"))
            open_action = next(action for action in actions if action["id"] == "openSourceMenu")
            assert bool(open_action["enabled"])
            QMetaObject.invokeMethod(
                surface,
                "dispatchSurfaceAction",
                Q_ARG("QVariant", "openSourceWith"),
            )
            settle_events(3)
            assert canvas.open_calls[-1] == (image_url, True)

            remote_url = "https://example.invalid/media.png"
            canvas.set_resolution(resolution("image", remote_url))
            actions = variant_list(surface.property("surfaceActions"))
            open_action = next(action for action in actions if action["id"] == "openSourceMenu")
            assert not bool(open_action["enabled"])
            open_call_count = len(canvas.open_calls)
            QMetaObject.invokeMethod(
                surface,
                "dispatchSurfaceAction",
                Q_ARG("QVariant", "openSource"),
            )
            settle_events(3)
            assert len(canvas.open_calls) == open_call_count

            canvas.set_resolution(resolution("image", image_url))

            actions = variant_list(surface.property("surfaceActions"))
            source_action = next(action for action in actions if action["id"] == "editSource")
            exposure_action = next(action for action in actions if action["id"] == "toggle_source_input")
            assert bool(source_action["enabled"])
            assert not bool(exposure_action["checked"])
            QMetaObject.invokeMethod(
                surface,
                "dispatchSurfaceAction",
                Q_ARG("QVariant", "toggle_source_input"),
            )
            settle_events(3)
            assert canvas.exposure_bridge.calls == [("node_surface_host_test", "source", True)]

            canvas.set_resolution(resolution("image", image_url, exposed=True))
            actions = variant_list(surface.property("surfaceActions"))
            exposure_action = next(action for action in actions if action["id"] == "toggle_source_input")
            assert bool(exposure_action["checked"])
            assert exposure_action["label"] == "Hide Source Input"
            QMetaObject.invokeMethod(
                surface,
                "dispatchSurfaceAction",
                Q_ARG("QVariant", "toggle_source_input"),
            )
            settle_events(3)
            assert canvas.exposure_bridge.calls == [
                ("node_surface_host_test", "source", True),
                ("node_surface_host_test", "source", False),
            ]

            canvas.set_resolution(resolution("pdf", image_url, exposed=True))
            pdf_renderer = wait_for_named(host, "graphNodeMediaPdfRenderer")
            pdf_preview = wait_for_named(host, "graphNodeMediaPdfPreviewImage")
            assert bool(image_renderer.property("rendererReleased"))
            pdf_source_size = pdf_preview.property("sourceSize")
            assert pdf_source_size.width() >= round(float(pdf_preview.width()))
            assert pdf_source_size.height() >= round(float(pdf_preview.height()))
            actions = variant_list(surface.property("surfaceActions"))
            source_action = next(action for action in actions if action["id"] == "editSource")
            exposure_action = next(action for action in actions if action["id"] == "toggle_source_input")
            assert not bool(source_action["enabled"])
            assert bool(exposure_action["checked"])
            assert abs(float(host.width()) - 340.0) < 0.01
            assert abs(float(host.height()) - 288.0) < 0.01
            assert_renderer_chrome(pdf_renderer, title=False, frame=False)

            canvas.set_resolution(resolution("video", video_url, exposed=True))
            wait_for_named(host, "graphNodeMediaVideoRenderer")
            video_renderer = surface.property("loadedRenderer")
            video_player = wait_for_named(video_renderer, "graphNodeVideoMediaPlayer")
            video_core = wait_for_named(video_renderer, "graphMediaVideoPlaybackCore")
            assert bool(pdf_renderer.property("rendererReleased"))
            assert_renderer_chrome(video_renderer, title=False, frame=False)
            wait_for_condition(
                lambda: bool(video_core.property("readyOrPlaying")),
                "inline video readiness",
            )
            wait_for_condition(
                lambda: bool(video_core.property("thumbnailPrimerComplete"))
                    and not bool(video_core.property("thumbnailPrimerActive"))
                    and video_player.property("playbackState") != QMediaPlayer.PlaybackState.PlayingState,
                "inline thumbnail primer completion",
                details=lambda: {
                    "enabled": bool(video_core.property("thumbnailPrimingEnabled")),
                    "complete": bool(video_core.property("thumbnailPrimerComplete")),
                    "active": bool(video_core.property("thumbnailPrimerActive")),
                    "allowed": bool(video_core.property("playbackAllowed")),
                    "should_resume": bool(video_core.property("shouldResumePlaying")),
                    "error": bool(video_core.property("errorActive")),
                    "ready": bool(video_core.property("readyOrPlaying")),
                    "status": str(video_player.property("mediaStatus")),
                    "playback": str(video_player.property("playbackState")),
                    "position": int(video_player.property("position")),
                },
            )
            assert 0 < int(video_player.property("position")) < 1200, (
                "inline-primer-position",
                int(video_player.property("position")),
            )
            assert str(video_player.property("source").toString()) == video_url, (
                "first-inline-source",
                str(video_player.property("source").toString()),
                video_url,
                bool(video_core.property("sourceActive")),
                str(video_core.property("sourceUrl")),
                bool(video_renderer.property("rendererReleased")),
                str(video_renderer.property("resolvedSourceUrl")),
                dict(video_renderer.property("sourceResolution") or {}),
            )

            second_payload = dict(payload)
            second_payload["node_id"] = "second_video_node"
            second_payload["properties"] = {
                **payload["properties"],
                "auto_play": True,
                "position_ms": 1200,
            }
            second_canvas = MediaCanvas(
                resolution("video", video_url, exposed=True),
                "second_video_node",
            )
            second_host = create_component(
                graph_node_host_qml_path,
                {"nodeData": second_payload, "canvasItem": second_canvas},
            )
            second_host.setParentItem(probe_window.contentItem())
            second_host.setX(420)
            second_host.setY(24)
            settle_events(6)
            second_player = wait_for_named(second_host, "graphNodeVideoMediaPlayer")
            second_core = wait_for_named(second_host, "graphMediaVideoPlaybackCore")
            wait_for_condition(
                lambda: second_player.property("playbackState") == QMediaPlayer.PlaybackState.PlayingState
                    and int(second_player.property("position")) >= 1100,
                "autoplay from authored initial position",
            )
            second_started_at = int(second_player.property("position"))
            wait_for_condition(
                lambda: int(second_player.property("position")) > second_started_at + 50,
                "inline autoplay advancement",
            )
            assert not bool(second_core.property("thumbnailPrimerComplete")), "inline-autoplay-skipped-primer"
            assert str(second_player.property("source").toString()) == video_url, "second-inline-source"

            fullscreen_bridge.open_video(
                "node_surface_host_test",
                video_url,
                {"position_ms": 2200, "playing": False},
            )
            settle_events(8)
            fullscreen_loader = wait_for_named(overlay, "contentFullscreenVideoSurfaceLoader")
            for _attempt in range(200):
                settle_events(2)
                if fullscreen_loader.property("item") is not None:
                    break
            fullscreen_surface = fullscreen_loader.property("item")
            assert fullscreen_surface is not None
            fullscreen_player = wait_for_named(fullscreen_surface, "contentFullscreenVideoMediaPlayer")
            fullscreen_core = wait_for_named(fullscreen_surface, "graphMediaVideoPlaybackCore")
            assert bool(video_renderer.property("fullscreenOwnsPlayback")), "fullscreen-owner"
            assert not bool(video_core.property("sourceActive")), "inline-core-released"
            assert str(video_player.property("source").toString()) == "", "inline-player-released"
            wait_for_condition(
                lambda: bool(fullscreen_core.property("readyOrPlaying"))
                    and abs(int(fullscreen_player.property("position")) - 2200) <= 120,
                "paused fullscreen initial position",
            )
            assert fullscreen_player.property("playbackState") != QMediaPlayer.PlaybackState.PlayingState, "paused-fullscreen"
            assert not bool(fullscreen_core.property("thumbnailPrimerComplete")), "nonzero-fullscreen-skipped-primer"
            assert str(fullscreen_player.property("source").toString()) == video_url, "fullscreen-source-owned"
            assert str(second_player.property("source").toString()) == video_url, "parallel-inline-retained"

            fullscreen_bridge.close_video({"position_ms": 2400, "playing": False})
            settle_events(8)
            assert not bool(video_renderer.property("fullscreenOwnsPlayback")), "fullscreen-owner-cleared"
            assert str(video_player.property("source").toString()) == video_url, "inline-source-restored"
            assert str(fullscreen_player.property("source").toString()) == "", "fullscreen-source-released"
            assert int(video_core.property("restorePositionMs")) == 2400, "inline-position-restored"
            assert not bool(video_core.property("restorePlaying")), "inline-pause-restored"

            fullscreen_bridge.open_video(
                "node_surface_host_test",
                video_url,
                {"position_ms": 1200, "playing": True},
            )
            settle_events(8)
            reopened_surface = fullscreen_loader.property("item")
            assert reopened_surface is not None
            reopened_player = wait_for_named(reopened_surface, "contentFullscreenVideoMediaPlayer")
            reopened_core = wait_for_named(reopened_surface, "graphMediaVideoPlaybackCore")
            assert str(video_player.property("source").toString()) == "", "reopen-inline-released"
            wait_for_condition(
                lambda: reopened_player.property("playbackState") == QMediaPlayer.PlaybackState.PlayingState
                    and int(reopened_player.property("position")) >= 1100,
                "fullscreen resumed playback",
            )
            reopened_started_at = int(reopened_player.property("position"))
            wait_for_condition(
                lambda: int(reopened_player.property("position")) > reopened_started_at + 50,
                "fullscreen resume advancement",
            )
            assert not bool(reopened_core.property("thumbnailPrimerComplete")), "fullscreen-resume-skipped-primer"
            assert str(reopened_player.property("source").toString()) == video_url, "reopen-fullscreen-owned"
            fullscreen_bridge.close_video({"position_ms": 1300, "playing": False})
            settle_events(8)
            assert str(reopened_player.property("source").toString()) == "", "reopen-fullscreen-released"
            assert str(video_player.property("source").toString()) == video_url, "reopen-inline-restored"
            assert int(video_core.property("restorePositionMs")) == 1300, "reopen-position-restored"

            canvas.rename_bridge.managedArtifactRenameReleaseRequested.emit(
                "node_surface_host_test"
            )
            settle_events(6)
            assert bool(video_renderer.property("artifactRenameReleaseActive")), "rename-release-active"
            assert str(video_player.property("source").toString()) == "", "rename-source-released"
            canvas.rename_bridge.managedArtifactRenameReleaseFinished.emit(
                "node_surface_host_test"
            )
            settle_events(8)
            assert not bool(video_renderer.property("artifactRenameReleaseActive")), "rename-release-cleared"
            assert str(video_player.property("source").toString()) == video_url, "rename-source-restored"

            QMetaObject.invokeMethod(
                surface,
                "dispatchSurfaceAction",
                Q_ARG("QVariant", "toggle_content_only"),
            )
            apply_committed_chrome({"show_title": True, "show_frame": True})
            video_renderer = surface.property("loadedRenderer")
            assert_renderer_chrome(video_renderer, title=True, frame=True)

            waiting_message = "Connected source is waiting for a run."
            canvas.set_resolution(
                resolution("", "", exposed=True, state="waiting", message=waiting_message)
            )
            assert bool(video_renderer.property("rendererReleased"))
            placeholder = wait_for_named(host, "graphNodeMediaStatePlaceholder")
            message = wait_for_named(host, "graphNodeMediaStateMessage")
            assert bool(placeholder.property("visible"))
            assert str(message.property("text")) == waiting_message
            assert not bool(surface.property("aspectRatioLocked"))

            binding_failures = [
                message for message in messages
                if ("GraphMedia" in message or "ContentFullscreen" in message)
                and (
                    "Binding loop" in message
                    or "ReferenceError" in message
                    or "Unable to assign" in message
                )
            ]
            assert not binding_failures, binding_failures

            host.deleteLater()
            second_host.deleteLater()
            overlay.deleteLater()
            probe_window.close()
            probe_window.deleteLater()
            second_canvas.deleteLater()
            canvas.deleteLater()
            fullscreen_bridge.deleteLater()
            qInstallMessageHandler(previous_handler)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_fullscreen_media_switch_releases_video_and_keeps_waiting_open(self) -> None:
        self._run_qml_probe(
            "unified-media-fullscreen-dispatch",
            """
            from PyQt6.QtCore import pyqtProperty, pyqtSignal, pyqtSlot
            from PyQt6.QtGui import QColor, QImage

            class FullThemeBridge(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def palette(self):
                    return {
                        "accent": "#5da9ff",
                        "border": "#3a4355",
                        "hover": "#33405c",
                        "input_bg": "#18202d",
                        "input_border": "#465066",
                        "input_fg": "#eef3ff",
                        "muted_fg": "#95a0b8",
                        "panel_bg": "#1b1f2a",
                        "panel_fg": "#eef3ff",
                        "panel_title_fg": "#eef3ff",
                        "pressed": "#22304a",
                        "toolbar_bg": "#202635",
                    }

            class FullscreenBridge(QObject):
                changed = pyqtSignal()

                def __init__(self, payload):
                    super().__init__()
                    self._payload = dict(payload)
                    self.closed = False

                @pyqtProperty(bool, notify=changed)
                def open(self):
                    return not self.closed

                @pyqtProperty(str, notify=changed)
                def node_id(self):
                    return "node_surface_host_test"

                @pyqtProperty(str, notify=changed)
                def content_kind(self):
                    return "media"

                @pyqtProperty(str, notify=changed)
                def title(self):
                    return "Media Panel"

                @pyqtProperty("QVariantMap", notify=changed)
                def media_payload(self):
                    return self._payload

                @pyqtSlot()
                def request_close(self):
                    self.closed = True
                    self.changed.emit()

                @pyqtSlot("QVariantMap", result=bool)
                def request_close_with_state(self, _state):
                    self.request_close()
                    return True

                def set_payload(self, payload):
                    self._payload = dict(payload)
                    self.changed.emit()

            class RenameBridge(QObject):
                managedArtifactRenameReleaseRequested = pyqtSignal(str)

            def payload(kind, source_url, *, state="ready", message="", controls=None):
                value = {
                    "media_kind": kind if state == "ready" else "",
                    "source_state": state,
                    "source_message": message,
                    "resolved_source_url": source_url if state == "ready" else "",
                    "preview_url": source_url if state == "ready" else "",
                    "source_pixel_width": 8,
                    "source_pixel_height": 6,
                    "fit_mode": "contain",
                    "crop": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
                    "rotation_degrees": 0,
                    "mirror_horizontal": False,
                    "mirror_vertical": False,
                    "auto_play": False,
                    "loop": False,
                    "muted": True,
                    "volume": 1.0,
                    "playback_rate": 1.0,
                    "position_ms": 0,
                    "timeline_bookmarks": [],
                    "clip_enabled": False,
                    "clip_start_ms": 0,
                    "clip_end_ms": 0,
                }
                value.update(dict(controls or {}))
                return value

            def wait_for_named(root, name, attempts=200):
                for _attempt in range(attempts):
                    settle_events(2)
                    candidate = root.findChild(QObject, name)
                    if candidate is not None:
                        return candidate
                raise AssertionError(f"{name!r} did not load")

            image_path = Path.cwd() / "artifacts" / "media-panel-fullscreen-test.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image = QImage(8, 6, QImage.Format.Format_ARGB32)
            image.fill(QColor("#5da9ff"))
            assert image.save(str(image_path))
            image_url = QUrl.fromLocalFile(str(image_path)).toString()
            second_image_path = Path.cwd() / "artifacts" / "media-panel-fullscreen-test-2.png"
            second_image = QImage(8, 6, QImage.Format.Format_ARGB32)
            second_image.fill(QColor("#ff995d"))
            assert second_image.save(str(second_image_path))
            second_image_url = QUrl.fromLocalFile(str(second_image_path)).toString()

            full_theme = FullThemeBridge()
            rename_bridge = RenameBridge()
            engine.rootContext().setContextProperty("themeBridge", full_theme)
            engine.rootContext().setContextProperty("tooltipCopyBridge", None)
            engine.rootContext().setContextProperty("graphCanvasCommandBridge", rename_bridge)
            bridge = FullscreenBridge(payload("image", image_url))
            overlay_path = Path.cwd() / "ea_node_editor" / "ui_qml" / "ContentFullscreenOverlay.qml"
            overlay = create_component(overlay_path, {"bridgeRef": bridge})
            wait_for_named(overlay, "contentFullscreenMediaImage")

            bridge.set_payload(payload("video", image_url))
            video_loader = wait_for_named(overlay, "contentFullscreenVideoSurfaceLoader")
            for _attempt in range(200):
                settle_events(2)
                if video_loader.property("item") is not None:
                    break
            assert video_loader.property("item") is not None
            video_surface = video_loader.property("item")
            video_player = wait_for_named(video_surface, "contentFullscreenVideoMediaPlayer")

            local_bookmarks = [{"id": "local", "label": "Local", "position_ms": 1200}]
            video_surface.setProperty("mutedValue", False)
            video_surface.setProperty("volumeValue", 0.35)
            video_surface.setProperty("playbackRateValue", 1.5)
            video_surface.setProperty("loopValue", True)
            video_surface.setProperty("fitModeValue", "cover")
            video_surface.setProperty("timelineBookmarksValue", local_bookmarks)
            video_surface.setProperty("clipEnabledValue", True)
            video_surface.setProperty("clipStartValue", 1000)
            video_surface.setProperty("clipEndValue", 4000)

            bridge.set_payload(payload("video", image_url, controls={
                "muted": True,
                "volume": 0.9,
                "playback_rate": 0.5,
                "loop": False,
                "fit_mode": "contain",
                "timeline_bookmarks": [],
                "clip_enabled": False,
                "clip_start_ms": 0,
                "clip_end_ms": 0,
            }))
            settle_events(6)
            assert video_loader.property("item") is video_surface
            assert not bool(video_surface.property("mutedValue"))
            assert abs(float(video_surface.property("volumeValue")) - 0.35) < 0.001
            assert abs(float(video_surface.property("playbackRateValue")) - 1.5) < 0.001
            assert bool(video_surface.property("loopValue"))
            assert str(video_surface.property("fitModeValue")) == "cover"
            assert variant_list(video_surface.property("timelineBookmarksValue"))[0]["id"] == "local"
            assert bool(video_surface.property("clipEnabledValue"))
            assert int(video_surface.property("clipStartValue")) == 1000
            assert int(video_surface.property("clipEndValue")) == 4000

            replacement_bookmarks = [
                {"id": "same", "label": "Later", "position_ms": 2500},
                {"id": "same", "label": "Duplicate", "position_ms": 1},
                {"id": "", "label": "", "position_ms": 1000},
                {"id": "alpha", "label": "alpha", "position_ms": 2500},
                "invalid",
            ]
            bridge.set_payload(payload("video", second_image_url, controls={
                "muted": True,
                "volume": 0.8,
                "playback_rate": 1.25,
                "loop": False,
                "fit_mode": "contain",
                "timeline_bookmarks": replacement_bookmarks,
                "clip_enabled": True,
                "clip_start_ms": 2000,
                "clip_end_ms": 6000,
            }))
            settle_events(6)
            assert bool(video_surface.property("mutedValue"))
            assert abs(float(video_surface.property("volumeValue")) - 0.8) < 0.001
            assert abs(float(video_surface.property("playbackRateValue")) - 1.25) < 0.001
            assert not bool(video_surface.property("loopValue"))
            assert str(video_surface.property("fitModeValue")) == "contain"
            assert variant_list(video_surface.property("timelineBookmarksValue")) == [
                {"id": "bookmark-1000-2", "label": "0:01", "position_ms": 1000},
                {"id": "alpha", "label": "alpha", "position_ms": 2500},
                {"id": "same", "label": "Later", "position_ms": 2500},
            ]
            assert bool(video_surface.property("clipEnabledValue"))
            assert int(video_surface.property("clipStartValue")) == 2000
            assert int(video_surface.property("clipEndValue")) == 6000

            waiting_message = "The connected media input is running."
            bridge.set_payload(payload("", "", state="running", message=waiting_message))
            placeholder = wait_for_named(overlay, "contentFullscreenMediaStatePlaceholder")
            settle_events(6)
            assert bool(placeholder.property("visible"))
            assert str(placeholder.property("text")) == waiting_message
            assert video_loader.property("item") is None
            assert bool(video_surface.property("rendererReleased"))
            assert str(video_player.property("source").toString()) == ""
            assert bool(overlay.property("visible"))

            bridge.set_payload(payload("video", second_image_url))
            for _attempt in range(200):
                settle_events(2)
                if video_loader.property("item") is not None:
                    break
            renamed_video_surface = video_loader.property("item")
            assert renamed_video_surface is not None
            renamed_video_player = wait_for_named(
                renamed_video_surface,
                "contentFullscreenVideoMediaPlayer",
            )
            rename_bridge.managedArtifactRenameReleaseRequested.emit(
                "node_surface_host_test"
            )
            settle_events(8)
            assert bridge.closed
            assert video_loader.property("item") is None
            assert bool(renamed_video_surface.property("rendererReleased"))
            assert str(renamed_video_player.property("source").toString()) == ""
            assert not bool(overlay.property("visible"))

            overlay.deleteLater()
            bridge.deleteLater()
            rename_bridge.deleteLater()
            full_theme.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )
