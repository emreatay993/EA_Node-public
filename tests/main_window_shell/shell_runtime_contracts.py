from __future__ import annotations

import os
import unittest
from pathlib import Path

from tests.main_window_shell.base import MainWindowShellTestBase, SharedMainWindowShellTestBase
from tests.main_window_shell.bridge_contracts import (
    FrameRateSampler,
    GraphCanvasCommandBridge,
    GraphCanvasStateBridge,
    QObject,
    ShellInspectorBridge,
    ShellLibraryBridge,
    ShellWorkspaceBridge,
    _GRAPH_CANVAS_HOST_DIRECT_ENV,
    _REPO_ROOT,
    _named_child_items,
    build_graph_fragment_payload,
    serialize_graph_fragment_payload,
)
from ea_node_editor.ui_qml.content_fullscreen_bridge import ContentFullscreenBridge
from ea_node_editor.ui_qml.graph_action_bridge import GraphActionBridge
from ea_node_editor.ui_qml.shell_context_bootstrap import ShellContextBundle
from ea_node_editor.ui_qml.viewer_host_service import ViewerHostService
from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge


_CONTENT_FULLSCREEN_PACKET_FILES = (
    _REPO_ROOT / "ea_node_editor" / "ui_qml" / "MainShell.qml",
    _REPO_ROOT / "ea_node_editor" / "ui_qml" / "ContentFullscreenOverlay.qml",
    _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "shell" / "PythonScriptGuidePane.qml",
    _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "shell" / "ScriptCodeEditorPane.qml",
)


def _packet_file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class FrameRateSamplerTests(unittest.TestCase):
    def test_snapshot_is_zero_without_enough_frames(self) -> None:
        sampler = FrameRateSampler(window_seconds=1.0)

        self.assertEqual(sampler.snapshot(timestamp=1.0).fps, 0.0)

        sampler.record_frame(timestamp=1.25)
        sample = sampler.snapshot(timestamp=1.25)
        self.assertEqual(sample.fps, 0.0)
        self.assertEqual(sample.sample_count, 1)

    def test_snapshot_reports_average_fps_within_recent_window(self) -> None:
        sampler = FrameRateSampler(window_seconds=1.0)
        for timestamp in (10.0, 10.2, 10.4, 10.6):
            sampler.record_frame(timestamp=timestamp)

        sample = sampler.snapshot(timestamp=10.6)

        self.assertAlmostEqual(sample.fps, 5.0, places=4)
        self.assertEqual(sample.sample_count, 4)

    def test_snapshot_drops_stale_frames_and_returns_idle_zero(self) -> None:
        sampler = FrameRateSampler(window_seconds=0.5)
        for timestamp in (20.0, 20.1, 20.2):
            sampler.record_frame(timestamp=timestamp)

        self.assertGreater(sampler.snapshot(timestamp=20.2).fps, 0.0)
        self.assertEqual(sampler.snapshot(timestamp=20.8).fps, 0.0)


class MainWindowShellTelemetryTests(SharedMainWindowShellTestBase):
    def test_update_system_metrics_can_render_explicit_fps_value(self) -> None:
        self.window.update_system_metrics(37.0, 4.3, 16.0, fps=58.0, disk_read_mb_s=12.4, disk_write_mb_s=2.6)
        self.app.processEvents()

        self.assertEqual(
            self.window.status_metrics.text(),
            "FPS:58 CPU:37% RAM:4.3/16.0 GB Disk R:12.4 W:2.6 MB/s",
        )

    def test_update_system_metrics_can_hide_fps_while_showing_disk_rates(self) -> None:
        self.window.update_system_metrics(
            37.0,
            4.3,
            16.0,
            fps=58.0,
            disk_read_mb_s=12.4,
            disk_write_mb_s=2.6,
            show_fps=False,
        )
        self.app.processEvents()

        self.assertEqual(
            self.window.status_metrics.text(),
            "CPU:37% RAM:4.3/16.0 GB Disk R:12.4 W:2.6 MB/s",
        )

    def test_status_items_can_jump_to_running_and_failed_nodes(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        running_id = self.window.scene.add_node_from_type("core.logger", x=40.0, y=40.0)
        failed_id = self.window.scene.add_node_from_type("core.python_script", x=320.0, y=120.0)
        self.app.processEvents()

        self.window.run_projection_controller.mark_node_execution_running(workspace_id, running_id, started_at_epoch_ms=12.5)
        self.window.status_jobs.requestAction("running")
        self.app.processEvents()

        self.assertEqual(self.window.scene.selected_node_id(), running_id)

        self.window.run_projection_controller.set_run_failure_focus(workspace_id, failed_id, node_title="Failed Script")
        self.window.status_notifications.requestAction("failed")
        self.app.processEvents()

        self.assertEqual(self.window.scene.selected_node_id(), failed_id)


class MainWindowShellBootstrapCompositionTests(SharedMainWindowShellTestBase):
    def test_bootstrap_starts_runtime_timers_with_expected_modes(self) -> None:
        self.assertTrue(self.window.metrics_timer.isActive())
        self.assertEqual(self.window.metrics_timer.interval(), 1000)
        self.assertFalse(self.window.graph_hint_timer.isActive())
        self.assertTrue(self.window.graph_hint_timer.isSingleShot())
        self.assertTrue(self.window.autosave_timer.isActive())


class MainWindowShellContextBootstrapTests(SharedMainWindowShellTestBase):
    def test_qml_context_removes_raw_canvas_globals_and_registers_bridge_first_facades(self) -> None:
        context = self.window.quick_widget.rootContext()
        services = self.window.shell_services

        expected_context_names = (
            "shellContext",
            "scriptEditorBridge",
            "scriptHighlighterBridge",
            "themeBridge",
            "graphThemeBridge",
            "uiIcons",
            "statusEngine",
            "statusJobs",
            "statusMetrics",
            "statusNotifications",
            "shellLibraryBridge",
            "shellWorkspaceBridge",
            "shellInspectorBridge",
            "graphCanvasStateBridge",
            "graphCanvasCommandBridge",
            "contentFullscreenBridge",
            "viewerSessionBridge",
            "viewerHostService",
        )
        for name in expected_context_names:
            with self.subTest(name=name):
                self.assertIsNotNone(context.contextProperty(name))

        for name in (
            "mainWindow",
            "sceneBridge",
            "viewBridge",
            "consoleBridge",
            "workspaceTabsBridge",
        ):
            with self.subTest(name=name, expectation="removed"):
                self.assertIsNone(context.contextProperty(name))

        shell_library_bridge = context.contextProperty("shellLibraryBridge")
        shell_context = context.contextProperty("shellContext")
        self.assertIsInstance(shell_context, ShellContextBundle)
        self.assertIs(shell_context, services.qml_context.qml_context_bundle)
        self.assertIsInstance(shell_library_bridge, ShellLibraryBridge)
        self.assertIsNone(shell_library_bridge.shell_window)
        self.assertIs(shell_library_bridge.library_source, self.window.shell_library_presenter)

        shell_workspace_bridge = context.contextProperty("shellWorkspaceBridge")
        self.assertIsInstance(shell_workspace_bridge, ShellWorkspaceBridge)
        self.assertIs(shell_workspace_bridge.shell_window, self.window)
        self.assertIs(shell_workspace_bridge.workspace_source, self.window.shell_workspace_presenter)
        self.assertIs(shell_workspace_bridge.scene_bridge, self.window.scene)
        self.assertIs(shell_workspace_bridge.view_bridge, self.window.view)
        self.assertIs(shell_workspace_bridge.console_bridge, self.window.console_panel)
        self.assertIs(shell_workspace_bridge.workspace_tabs_bridge, self.window.workspace_tabs)

        shell_inspector_bridge = context.contextProperty("shellInspectorBridge")
        self.assertIsInstance(shell_inspector_bridge, ShellInspectorBridge)
        self.assertIsNone(shell_inspector_bridge.shell_window)
        self.assertIs(shell_inspector_bridge.inspector_source, self.window.shell_inspector_presenter)
        self.assertIs(shell_inspector_bridge.scene_bridge, self.window.scene)

        graph_canvas_state_bridge = context.contextProperty("graphCanvasStateBridge")
        self.assertIsInstance(graph_canvas_state_bridge, GraphCanvasStateBridge)
        self.assertIs(graph_canvas_state_bridge.parent(), self.window)
        self.assertIs(graph_canvas_state_bridge._session_state, self.window.search_scope_state)
        self.assertIs(
            graph_canvas_state_bridge._app_preferences_source,
            self.window.app_preferences_controller,
        )
        self.assertIs(graph_canvas_state_bridge.graphics_source, self.window.shell_workspace_presenter)
        self.assertIs(graph_canvas_state_bridge.execution_source, self.window)
        self.assertIs(graph_canvas_state_bridge.project_source, self.window)
        self.assertIs(graph_canvas_state_bridge.scene_bridge, self.window.scene)
        self.assertIs(graph_canvas_state_bridge.view_bridge, self.window.view)

        graph_canvas_command_bridge = context.contextProperty("graphCanvasCommandBridge")
        self.assertIsInstance(graph_canvas_command_bridge, GraphCanvasCommandBridge)
        self.assertIs(graph_canvas_command_bridge.parent(), self.window)
        self.assertIs(
            graph_canvas_command_bridge._run_controller,
            self.window.run_controller,
        )
        self.assertIs(
            graph_canvas_command_bridge._workspace_edit_controller,
            self.window.workspace_edit_controller,
        )
        self.assertIs(
            graph_canvas_command_bridge.media_action_source,
            self.window.media_panel_action_service,
        )
        self.assertIs(
            graph_canvas_command_bridge.graphics_source,
            self.window.shell_workspace_presenter,
        )
        self.assertIs(graph_canvas_command_bridge.host_source, self.window.graph_canvas_host_presenter)
        self.assertIs(graph_canvas_command_bridge.scene_bridge, self.window.scene)
        self.assertIs(graph_canvas_command_bridge.view_bridge, self.window.view)
        self.assertIs(
            self.window.scene._graphics_preferences_source,
            self.window.shell_workspace_presenter,
        )

        content_fullscreen_bridge = context.contextProperty("contentFullscreenBridge")
        self.assertIsInstance(content_fullscreen_bridge, ContentFullscreenBridge)
        self.assertIs(content_fullscreen_bridge, services.runtime.content_fullscreen_bridge)
        self.assertEqual(content_fullscreen_bridge.tabular_payload, {})

        viewer_session_bridge = context.contextProperty("viewerSessionBridge")
        self.assertIsInstance(viewer_session_bridge, ViewerSessionBridge)
        self.assertIs(viewer_session_bridge.parent(), self.window)
        self.assertEqual(
            viewer_session_bridge.active_workspace_id,
            self.window.workspace_manager.active_workspace_id(),
        )

        viewer_host_service = context.contextProperty("viewerHostService")
        self.assertIsInstance(viewer_host_service, ViewerHostService)
        self.assertIs(viewer_host_service.parent(), self.window)
        self.assertIs(viewer_host_service.overlay_manager, self.window.embedded_viewer_overlay_manager)

        context_bindings = dict(services.qml_context.qml_context_property_bindings)
        self.assertIs(context_bindings["shellContext"], shell_context)
        self.assertIs(context_bindings["shellLibraryBridge"], shell_library_bridge)
        self.assertIs(context_bindings["shellWorkspaceBridge"], shell_workspace_bridge)
        self.assertIs(context_bindings["shellInspectorBridge"], shell_inspector_bridge)
        self.assertIs(context_bindings["graphCanvasStateBridge"], graph_canvas_state_bridge)
        self.assertIs(context_bindings["graphCanvasCommandBridge"], graph_canvas_command_bridge)
        self.assertIs(context_bindings["viewerSessionBridge"], viewer_session_bridge)
        self.assertIs(context_bindings["viewerHostService"], viewer_host_service)

    def test_shell_window_keeps_services_bundle_in_sync_with_context_bundle(self) -> None:
        services = self.window.shell_services
        bridges = services.context_bridges.shell_context_bridges
        context_bindings = dict(services.qml_context.qml_context_property_bindings)

        self.assertIs(self.window.shell_library_bridge, bridges.shell_library_bridge)
        self.assertIs(self.window.shell_workspace_bridge, bridges.shell_workspace_bridge)
        self.assertIs(self.window.shell_inspector_bridge, bridges.shell_inspector_bridge)
        self.assertIs(self.window.graph_canvas_state_bridge, bridges.graph_canvas_state_bridge)
        self.assertIs(self.window.graph_canvas_command_bridge, bridges.graph_canvas_command_bridge)
        self.assertIs(
            services.runtime.viewer_session_bridge,
            context_bindings["viewerSessionBridge"],
        )
        self.assertIs(
            services.runtime.viewer_host_service,
            context_bindings["viewerHostService"],
        )


class MainWindowShellContentFullscreenStaticContractsTests(unittest.TestCase):
    def test_content_fullscreen_overlay_is_shell_owned_and_bridge_gated(self) -> None:
        main_shell = _packet_file_text(_CONTENT_FULLSCREEN_PACKET_FILES[0])
        overlay = _packet_file_text(_CONTENT_FULLSCREEN_PACKET_FILES[1])
        guide = _packet_file_text(_CONTENT_FULLSCREEN_PACKET_FILES[2])
        script_pane = _packet_file_text(_CONTENT_FULLSCREEN_PACKET_FILES[3])

        self.assertNotIn("ContentFullscreenOverlay {", main_shell)
        self.assertNotIn("sourceComponent:", main_shell)
        self.assertIn('objectName: "contentFullscreenOverlayLoader"', main_shell)
        self.assertIn("property bool contentFullscreenLoaderActivated:", main_shell)
        self.assertIn("function onContent_fullscreen_changed()", main_shell)
        self.assertIn("active: root.contentFullscreenLoaderActivated", main_shell)
        self.assertIn('source: Qt.resolvedUrl("ContentFullscreenOverlay.qml")', main_shell)
        self.assertIn("item.bridgeRef = root.contentFullscreenBridgeRef", main_shell)
        self.assertIn("item.scriptEditorBridgeRef = root.scriptEditorBridgeRef", main_shell)
        self.assertIn("item.scriptHighlighterBridgeRef = root.scriptHighlighterBridgeRef", main_shell)
        self.assertIn('objectName: "contentFullscreenOverlay"', overlay)
        self.assertIn("readonly property bool bridgeOpen", overlay)
        self.assertIn("root.bridgeRef.open", overlay)
        self.assertIn("root.bridgeRef.request_close()", overlay)
        self.assertIn("property var scriptEditorBridgeRef", overlay)
        self.assertIn("property var scriptHighlighterBridgeRef", overlay)
        self.assertIn('objectName: "contentFullscreenScriptEditorPane"', overlay)
        self.assertIn('visible: root.contentKind === "script_editor"', overlay)
        self.assertIn("ScriptCodeEditorPane {", overlay)
        self.assertIn('objectName: "contentFullscreenPythonScriptGuidePane"', overlay)
        self.assertIn("guideButtonVisible: true", overlay)
        self.assertIn("onGuideRequested: root.scriptGuideVisible", overlay)
        self.assertIn("PythonScriptGuidePane {", overlay)
        self.assertIn('objectName: "pythonScriptGuideButton"', script_pane)
        self.assertIn("visible: root.guideButtonVisible", script_pane)
        self.assertIn("selectedStyle: root.guideButtonSelected", script_pane)
        self.assertIn('objectName: "pythonScriptDecoratorGuideText"', guide)
        self.assertIn("textFormat: TextEdit.RichText", guide)
        self.assertIn("<html><head><style>", guide)
        self.assertIn("class='hero'", guide)
        self.assertIn("<table>", guide)
        self.assertIn("@corex.slider", guide)
        self.assertIn("port=True", guide)

    def test_content_fullscreen_overlay_declares_media_modes_and_viewer_viewport(self) -> None:
        overlay = _packet_file_text(_CONTENT_FULLSCREEN_PACKET_FILES[1])

        for snippet in (
            "import QtQuick.Pdf",
            'objectName: "contentFullscreenMediaViewport"',
            'objectName: "contentFullscreenMediaImage"',
            'objectName: "contentFullscreenPdfDocument"',
            'objectName: "contentFullscreenPdfMultiPageView"',
            "document: pdfDocument",
            'objectName: "contentFullscreenDisplayModeFitButton"',
            'objectName: "contentFullscreenDisplayModeFillButton"',
            'objectName: "contentFullscreenDisplayModeActualButton"',
            'objectName: "contentFullscreenPdfNavigationControls"',
            'objectName: "contentFullscreenPdfPreviousButton"',
            'iconName: "navigate-previous"',
            'objectName: "contentFullscreenPdfPageField"',
            'objectName: "contentFullscreenPdfNextButton"',
            'iconName: "navigate-next"',
            'objectName: "contentFullscreenPdfReaderControls"',
            'objectName: "contentFullscreenPdfSearchButton"',
            'objectName: "contentFullscreenPdfZoomOutButton"',
            'objectName: "contentFullscreenPdfZoomLabel"',
            'objectName: "contentFullscreenPdfZoomInButton"',
            'objectName: "contentFullscreenPdfFitPageButton"',
            'objectName: "contentFullscreenPdfFitWidthButton"',
            'objectName: "contentFullscreenPdfActualSizeButton"',
            'objectName: "contentFullscreenPdfRotateClockwiseButton"',
            'iconName: "rotate-clockwise"',
            'objectName: "contentFullscreenPdfSearchControls"',
            'objectName: "contentFullscreenPdfSearchField"',
            'objectName: "contentFullscreenPdfSearchPreviousButton"',
            'objectName: "contentFullscreenPdfSearchNextButton"',
            'objectName: "contentFullscreenPdfSearchClearButton"',
            'objectName: "contentFullscreenMailReaderControls"',
            'objectName: "contentFullscreenMailZoomOutButton"',
            'objectName: "contentFullscreenMailZoomLabel"',
            'objectName: "contentFullscreenMailZoomInButton"',
            'objectName: "contentFullscreenMailFitPageButton"',
            'objectName: "contentFullscreenMailFitWidthButton"',
            'objectName: "contentFullscreenMailActualSizeButton"',
            'objectName: "contentFullscreenMailViewport"',
            'objectName: "contentFullscreenMailWebEngineLayer"',
            'objectName: "contentFullscreenMailPlaceholder"',
            'objectName: \\"contentFullscreenMailWebEngineView\\"',
            'objectName: \\"contentFullscreenMailWebEngineProfile\\"',
            "root.contentKind === \"mail\"",
            "root.previewSourceUrl",
            "function _applyMailFitMode",
            "function _applyMailFitZoomForMetrics",
            "requestContentMetrics()",
            "contentMetricsReady",
            "pageZoom",
            "searchString: root.pdfSearchText",
            "root.pdfMultiPageViewHandle.scaleToPage",
            "root.pdfMultiPageViewHandle.scaleToWidth",
            "root.pdfMultiPageViewHandle.pageRotation",
            "event.key === Qt.Key_F && root._controlOnlyKeyEvent(event)",
            "event.key === Qt.Key_PageUp",
            "event.key === Qt.Key_PageDown",
            "event.key === Qt.Key_Home",
            "event.key === Qt.Key_End",
            "root.bridgeRef.request_pdf_page_number",
            'objectName: "contentFullscreenViewerViewport"',
            "GraphMediaPanelGeometry.sourceClipRectFromNormalized",
            'objectName: "contentFullscreenMediaImageViewport"',
            'objectName: "contentFullscreenMediaImageTransformFrame"',
            'objectName: "contentFullscreenMediaImageMirrorFrame"',
            "readonly property rect mediaImageSourceClipRect: root._sourceClipRect()",
            "x: Number(root.mediaImageOffsetX || 0)",
            "width: Math.max(0, Number(root.mediaImageFullFrameWidth || 0))",
            "root.mediaPayload.resolved_source_url",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, overlay)

    def test_content_fullscreen_overlay_blocks_background_and_handles_close_keys(self) -> None:
        overlay = _packet_file_text(_CONTENT_FULLSCREEN_PACKET_FILES[1])

        for snippet in (
            'objectName: "contentFullscreenInteractionBlocker"',
            "acceptedButtons: Qt.AllButtons",
            "event.key === Qt.Key_Escape",
            "event.key === Qt.Key_F11",
            "event.key === Qt.Key_Left || event.key === Qt.Key_PageUp",
            "root._requestPdfPageDelta(-1)",
            "event.key === Qt.Key_Right || event.key === Qt.Key_PageDown",
            "root._requestPdfPageDelta(1)",
            "function _requestPdfPageDeltaFromWheel(wheel)",
            "root._requestPdfPageDeltaFromWheel(wheel)",
            'objectName: "contentFullscreenCloseButton"',
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, overlay)


class MainWindowShellHostProtocolStateTests(SharedMainWindowShellTestBase):
    def test_search_scope_state_tracks_graph_search_quick_insert_and_hints(self) -> None:
        self.window.action_graph_search.trigger()
        self.window.set_graph_search_query("core.constant")
        self.app.processEvents()

        graph_search_state = self.window.search_scope_state.graph_search
        self.assertTrue(graph_search_state.open)
        self.assertEqual(graph_search_state.query, "core.constant")
        self.assertEqual(graph_search_state.enabled_scopes, ["title", "type", "content", "port"])
        self.assertEqual(graph_search_state.results, self.window.graph_search_results)

        self.window.request_open_canvas_quick_insert(40.0, 55.0, 120.0, 180.0)
        self.app.processEvents()

        quick_insert_state = self.window.search_scope_state.connection_quick_insert
        self.assertTrue(quick_insert_state.open)
        self.assertEqual(quick_insert_state.context["mode"], "canvas_insert")
        self.assertEqual(quick_insert_state.context["overlay_x"], 120.0)
        self.assertEqual(quick_insert_state.results, [])
        self.assertEqual(quick_insert_state.highlight_index, -1)
        self.assertEqual(quick_insert_state.results, self.window.connection_quick_insert_results)

        self.window.set_connection_quick_insert_query("constant")
        self.app.processEvents()

        quick_insert_state = self.window.search_scope_state.connection_quick_insert
        self.assertEqual(quick_insert_state.query, "constant")
        self.assertEqual(quick_insert_state.highlight_index, 0)
        self.assertGreaterEqual(len(quick_insert_state.results), 1)
        self.assertIn(
            "core.constant",
            {str(item.get("type_id", "")) for item in quick_insert_state.results},
        )
        self.window.set_connection_quick_insert_query("   ")
        self.app.processEvents()

        quick_insert_state = self.window.search_scope_state.connection_quick_insert
        self.assertEqual(quick_insert_state.query, "   ")
        self.assertEqual(quick_insert_state.results, [])
        self.assertEqual(quick_insert_state.highlight_index, -1)

        self.window.show_graph_hint("Packet hint", 500)
        self.assertEqual(self.window.search_scope_state.graph_hint_message, "Packet hint")
        self.window.clear_graph_hint()
        self.assertEqual(self.window.search_scope_state.graph_hint_message, "")

    def test_scope_camera_cache_is_owned_by_search_scope_state(self) -> None:
        self.window.view.set_zoom(1.35)
        self.window.view.centerOn(140.0, -75.0)

        self.window._remember_scope_camera()

        key = self.window._active_scope_camera_key()
        self.assertIsNotNone(key)
        if key is None:
            self.fail("Expected active scope camera key")
        self.assertIn(key, self.window.search_scope_state.runtime_scope_camera)


class _MainWindowShellGraphCanvasHostDirectTests(MainWindowShellTestBase):
    __test__ = os.environ.get(_GRAPH_CANVAS_HOST_DIRECT_ENV) == "1"

    def test_graph_canvas_host_binds_split_canvas_bridge_refs_to_registered_context_bridges(self) -> None:
        graph_canvas = self._graph_canvas_item()
        context = self.window.quick_widget.rootContext()
        graph_action_bridge = context.contextProperty("graphActionBridge")
        graph_canvas_state_bridge = context.contextProperty("graphCanvasStateBridge")
        graph_canvas_command_bridge = context.contextProperty("graphCanvasCommandBridge")
        graph_canvas_view_bridge = context.contextProperty("graphCanvasViewBridge")
        canvas_graph_action_bridge = graph_canvas.property("graphActionBridge")
        canvas_state_bridge = graph_canvas.property("canvasStateBridge")
        canvas_command_bridge = graph_canvas.property("canvasCommandBridge")
        canvas_view_bridge = graph_canvas.property("canvasViewBridge")
        canvas_graph_action_bridge_ref = graph_canvas.property("graphActionBridgeRef")
        canvas_state_bridge_ref = graph_canvas.property("canvasStateBridgeRef")
        canvas_command_bridge_ref = graph_canvas.property("canvasCommandBridgeRef")
        canvas_view_bridge_ref = graph_canvas.property("canvasViewBridgeRef")

        self.assertIsNone(context.contextProperty("graphCanvasBridge"))
        self.assertIsInstance(graph_action_bridge, GraphActionBridge)
        self.assertIsInstance(graph_canvas_state_bridge, GraphCanvasStateBridge)
        self.assertIsInstance(graph_canvas_command_bridge, GraphCanvasCommandBridge)
        self.assertIs(graph_canvas_view_bridge, self.window.view)
        self.assertIs(self.window.graph_action_bridge, graph_action_bridge)
        self.assertIs(self.window.graph_canvas_state_bridge, graph_canvas_state_bridge)
        self.assertIs(self.window.graph_canvas_command_bridge, graph_canvas_command_bridge)
        self.assertEqual(graph_canvas.objectName(), "graphCanvas")
        self.assertIsInstance(canvas_graph_action_bridge, GraphActionBridge)
        self.assertIs(canvas_graph_action_bridge, graph_action_bridge)
        self.assertIsInstance(canvas_state_bridge, GraphCanvasStateBridge)
        self.assertIs(canvas_state_bridge, graph_canvas_state_bridge)
        self.assertIsInstance(canvas_command_bridge, GraphCanvasCommandBridge)
        self.assertIs(canvas_command_bridge, graph_canvas_command_bridge)
        self.assertIsNone(canvas_view_bridge)
        self.assertIsInstance(canvas_graph_action_bridge_ref, GraphActionBridge)
        self.assertIs(canvas_graph_action_bridge_ref, graph_action_bridge)
        self.assertIsInstance(canvas_state_bridge_ref, GraphCanvasStateBridge)
        self.assertIs(canvas_state_bridge_ref, graph_canvas_state_bridge)
        self.assertIsInstance(canvas_command_bridge_ref, GraphCanvasCommandBridge)
        self.assertIs(canvas_command_bridge_ref, graph_canvas_command_bridge)
        self.assertIs(canvas_view_bridge_ref, graph_canvas_view_bridge)
        self.assertIsNone(graph_canvas.property("canvasBridge"))
        self.assertIsNone(graph_canvas.property("canvasBridgeRef"))
        self.assertEqual(
            bool(graph_canvas.property("showGrid")),
            graph_canvas_state_bridge.graphics_show_grid,
        )
        self.assertEqual(
            bool(graph_canvas.property("minimapVisible")),
            graph_canvas_state_bridge.graphics_show_minimap,
        )
        self.assertEqual(
            bool(graph_canvas.property("minimapExpanded")),
            graph_canvas_state_bridge.graphics_minimap_expanded,
        )

    def test_graph_canvas_keeps_graph_node_card_discoverability_after_host_refactor(self) -> None:
        graph_canvas = self._graph_canvas_item()
        self.window.scene.add_node_from_type("core.logger", 180.0, 120.0)
        self.app.processEvents()

        node_cards = _named_child_items(graph_canvas, "graphNodeCard")
        self.assertGreaterEqual(len(node_cards), 1)
        self.assertIsNotNone(node_cards[0].findChild(QObject, "graphNodeStandardSurface"))

    def test_plain_text_graph_fragment_payload_is_ignored_by_paste(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        self.window.scene.add_node_from_type("core.constant", x=25.0, y=35.0)
        before_state = self._workspace_state()
        before_depth = self.window.runtime_history.undo_depth(workspace_id)
        clipboard = self.app.clipboard()

        valid_text_payload = serialize_graph_fragment_payload(
            build_graph_fragment_payload(
                nodes=[
                    {
                        "ref_id": "ref-start",
                        "type_id": "core.constant",
                        "title": "Constant",
                        "x": 0.0,
                        "y": 0.0,
                        "collapsed": False,
                        "properties": {},
                        "exposed_ports": {},
                        "visual_style": {},
                        "parent_node_id": None,
                    }
                ],
                edges=[],
            )
        )
        self.assertIsNotNone(valid_text_payload)
        clipboard.setText(str(valid_text_payload))

        pasted = self.window.request_paste_selected_nodes()
        self.assertFalse(pasted)
        self.assertEqual(self._workspace_state(), before_state)
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), before_depth)

    def test_graph_search_results_use_user_facing_instance_ids_for_duplicate_nodes(self) -> None:
        first_node_id = self.window.scene.add_node_from_type("core.constant", x=40.0, y=40.0)
        second_node_id = self.window.scene.add_node_from_type("core.constant", x=260.0, y=40.0)
        self.window.scene.set_node_title(first_node_id, "Duplicate Search Alpha")
        self.window.scene.set_node_title(second_node_id, "Duplicate Search Beta")
        self.app.processEvents()

        self.window.action_graph_search.trigger()
        self.window.set_graph_search_query("duplicate search")
        self.app.processEvents()

        results_by_id = {
            item["node_id"]: item
            for item in self.window.graph_search_results
        }
        self.assertEqual(results_by_id[first_node_id]["instance_number"], 1)
        self.assertEqual(results_by_id[first_node_id]["instance_label"], "ID 1")
        self.assertEqual(results_by_id[second_node_id]["instance_number"], 2)
        self.assertEqual(results_by_id[second_node_id]["instance_label"], "ID 2")
__all__ = [
    "FrameRateSamplerTests",
    "MainWindowShellTelemetryTests",
    "MainWindowShellBootstrapCompositionTests",
    "MainWindowShellContextBootstrapTests",
    "MainWindowShellContentFullscreenStaticContractsTests",
    "MainWindowShellHostProtocolStateTests",
    "_MainWindowShellGraphCanvasHostDirectTests",
]
