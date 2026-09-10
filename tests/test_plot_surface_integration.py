from __future__ import annotations

import unittest
from pathlib import Path

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from ea_node_editor.ui_qml.surface_contracts import surface_spec_payload_for_values
from tests.graph_surface_pointer_regression import (
    QML_POINTER_REGRESSION_HELPERS,
    run_qml_probe,
)


class _PlotGraphThemeBridge:
    theme = "graph_stitch_dark"


def _plot_scene_payload(
    *,
    properties: dict[str, object] | None = None,
    lightweight_canvas: bool = False,
) -> dict[str, object]:
    model = GraphModel()
    registry = build_default_registry()
    workspace_id = model.active_workspace.workspace_id
    node = model.add_node(
        workspace_id,
        "plot.scatter",
        "Scatter Plot",
        64.0,
        96.0,
        properties=properties,
    )
    nodes_payload, _minimap_payload, _edges_payload = GraphScenePayloadBuilder().rebuild_models(
        model=model,
        registry=registry,
        workspace_id=workspace_id,
        scope_path=(),
        graph_theme_bridge=_PlotGraphThemeBridge(),
        lightweight_canvas=lightweight_canvas,
    )
    return next(item for item in nodes_payload if item["node_id"] == node.node_id)


def test_plot_nodes_publish_plot_surface_spec_for_live_2d_canvas() -> None:
    payload = _plot_scene_payload(properties={"render_in_canvas": True})

    assert payload["surface_family"] == "plot"
    assert payload["surface_variant"] == "scatter"
    assert payload["surface_spec"] == surface_spec_payload_for_values(
        type_id="plot.scatter",
        family="plot",
        variant="scatter",
    )
    assert payload["surface_spec"]["component_key"] == "plot"
    assert payload["surface_spec"]["qml_component"] == "plot/GraphPlotSurface.qml"
    assert payload["surface_spec"]["fullscreen"]["content_kind"] == "plot"
    assert payload["surface_spec"]["native_overlay"] == {
        "required": True,
        "target": "body",
        "owner": "plot_host",
    }


def test_plot_surface_payload_preserves_p03_sink_mode_contract() -> None:
    default_payload = _plot_scene_payload()
    disabled_payload = _plot_scene_payload(properties={"render_in_canvas": False})
    enabled_payload = _plot_scene_payload(properties={"render_in_canvas": True})

    assert default_payload["plot_surface"] == {
        "plot_type": "scatter",
        "live_backend_id": "pyqtgraph",
        "render_in_canvas": True,
        "lightweight_canvas": False,
        "embedded_rendering_suppressed": False,
        "embedded_rendering_suppressed_by": [],
    }
    assert default_payload["embedded_rendering_suppressed"] is False
    assert default_payload["embedded_rendering_suppressed_by"] == []
    assert disabled_payload["plot_surface"]["embedded_rendering_suppressed"] is True
    assert disabled_payload["embedded_rendering_suppressed_by"] == ["render_in_canvas"]
    assert enabled_payload["plot_surface"]["embedded_rendering_suppressed"] is False
    assert enabled_payload["embedded_rendering_suppressed_by"] == []


def test_plot_surface_exposes_detached_window_action_contract_without_session_action() -> None:
    surface_source = (
        Path(__file__).resolve().parents[1]
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "graph"
        / "plot"
        / "GraphPlotSurfaceBody.qml"
    ).read_text(encoding="utf-8")

    assert '"id": "plot_detach"' in surface_source
    assert '"kind": "plot"' in surface_source
    assert "requestDetachedWindow" in surface_source
    assert "open_detached_plot(surface.plotNodeId)" in surface_source
    assert '"id": "plot_add_to_session"' not in surface_source
    assert "requestPlotSession" not in surface_source
    assert "add_plot_to_session(surface.plotNodeId)" not in surface_source


def test_plot_surface_keeps_original_inline_live_preview_policy() -> None:
    surface_source = (
        Path(__file__).resolve().parents[1]
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "graph"
        / "plot"
        / "GraphPlotSurfaceBody.qml"
    ).read_text(encoding="utf-8")

    assert "surface.hostSurfaceActive || surface.viewportHoverActive || autoPreviewPulse.running" in surface_source
    assert "auto_preview_active" in surface_source
    assert "readonly property string plotLiveBackendId" in surface_source
    assert 'plotLiveBackendId === "pyqtgraph"' in surface_source
    assert "readonly property bool liveSurfaceSizeViable" in surface_source
    assert "&& surface.liveSurfaceSizeViable" in surface_source
    assert "host.currentViewportZoom()" in surface_source
    assert "readonly property bool externalPresentationActive" not in surface_source
    assert "session_plot_active(surface.plotNodeId)" not in surface_source
    assert "onExternalPresentationActiveChanged" not in surface_source


def test_plot_surface_prefers_cached_real_preview_over_spline_placeholder() -> None:
    surface_source = (
        Path(__file__).resolve().parents[1]
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "graph"
        / "plot"
        / "GraphPlotSurfaceBody.qml"
    ).read_text(encoding="utf-8")

    assert "readonly property string cachedPreviewSource" in surface_source
    assert "readonly property bool cachedPreviewVisible" in surface_source
    assert "readonly property bool contentFullscreenOpen" in surface_source
    assert "cached_preview_source(surface.plotNodeId)" in surface_source
    assert "embedded_live_overlay_ready(surface.plotNodeId)" in surface_source
    assert "plot_overlay_revision" in surface_source
    assert "readonly property bool liveOverlayReady" in surface_source
    assert "readonly property bool proxySurfaceActive: !surface.liveOverlayReady" in surface_source
    assert "readonly property bool placeholderPreviewVisible" in surface_source
    assert 'objectName: "graphNodePlotCachedPreviewImage"' in surface_source
    assert 'source: surface._cachedPreviewImageSource' in surface_source
    assert "_clearCachedPreviewImage" in surface_source
    assert "cache: false" in surface_source
    assert "visible: surface.placeholderPreviewVisible" in surface_source


class PlotSurfaceInteractionQmlTests(unittest.TestCase):
    def _run_qml_probe(self, label: str, body: str) -> None:
        run_qml_probe(
            self,
            label,
            QML_POINTER_REGRESSION_HELPERS,
            body,
        )

    def test_selected_plot_surface_uses_cached_preview_during_transient_interaction(self) -> None:
        self._run_qml_probe(
            "plot-surface-transient-interaction-preview",
            """
            from pathlib import Path

            from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            class PlotHostServiceStub(QObject):
                activeOverlayCountChanged = pyqtSignal()
                previewCacheRevisionChanged = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self.calls = []
                    self._active_nodes = set()
                    self._preview_cache_revision = 1

                @pyqtProperty(int, notify=activeOverlayCountChanged)
                def active_overlay_count(self):
                    return len(self._active_nodes)

                @pyqtProperty(int, notify=previewCacheRevisionChanged)
                def preview_cache_revision(self):
                    return self._preview_cache_revision

                @pyqtSlot(str, bool)
                def set_embedded_interaction_active(self, node_id, active):
                    normalized = str(node_id)
                    enabled = bool(active)
                    self.calls.append((normalized, enabled))
                    before_count = len(self._active_nodes)
                    if enabled:
                        self._active_nodes.add(normalized)
                    else:
                        self._active_nodes.discard(normalized)
                        self._preview_cache_revision += 1
                        self.previewCacheRevisionChanged.emit()
                    if len(self._active_nodes) != before_count:
                        self.activeOverlayCountChanged.emit()

                @pyqtSlot(str, result=str)
                def cached_preview_source(self, node_id):
                    return "image://plot-preview-cache/ws/" + str(node_id)

                @pyqtSlot(str, result=bool)
                def embedded_live_overlay_ready(self, node_id):
                    return str(node_id) in self._active_nodes

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            service = PlotHostServiceStub()
            engine.rootContext().setContextProperty("plotHostService", service)

            plot_dir = Path.cwd() / "ea_node_editor" / "ui_qml" / "components" / "graph" / "plot"
            qml = '''
            import QtQuick 2.15

            Item {
                id: root
                width: 360
                height: 260

                Item {
                    id: probeHost
                    objectName: "probeHost"
                    property bool hoverActive: false
                    property bool isSelected: true
                    property bool viewportInteractionCacheActive: false
                    property bool hostDragActive: false
                    property var nodeData: ({
                        "node_id": "node-plot",
                        "surface_variant": "line",
                        "plot_surface": {
                            "plot_type": "line",
                            "live_backend_id": "pyqtgraph",
                            "embedded_rendering_suppressed": false
                        }
                    })
                    property var surfaceMetrics: ({
                        "body_left_margin": 0.0,
                        "body_top": 0.0,
                        "body_right_margin": 0.0,
                        "body_height": 220.0
                    })
                    property real resolvedCornerRadius: 6.0
                    property color inlineInputBackgroundColor: "#18202d"
                    property color selectedOutlineColor: "#5da9ff"
                    property color outlineColor: "#414a5d"
                    property color inlineDrivenTextColor: "#aeb8ce"
                    property color surfaceColor: "#1f2431"
                    property color headerTextColor: "#eef3ff"
                    property int nodeTextRenderType: Text.CurveRendering
                    property bool surfaceFullscreenAvailable: false
                    function surfaceFullscreenAction(_enabled, _primary) { return null; }
                    function requestSurfaceContentFullscreen() { return false; }
                }

                GraphPlotSurfaceBody {
                    id: surface
                    objectName: "graphNodePlotSurfaceProbe"
                    anchors.fill: parent
                    host: probeHost
                }
            }
            '''
            component = QQmlComponent(engine)
            component.setData(qml.encode("utf-8"), QUrl.fromLocalFile(str(plot_dir / "PlotSurfaceProbe.qml")))
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load plot surface probe:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate plot surface probe:\\n" + errors)

            def settle(cycles=8):
                for _index in range(cycles):
                    app.processEvents()

            window = attach_host_to_window(probe)
            settle()
            host = probe.findChild(QObject, "probeHost")
            surface = probe.findChild(QObject, "graphNodePlotSurfaceProbe")
            assert host is not None
            assert surface is not None

            assert bool(surface.property("liveSurfaceActive"))
            assert bool(surface.property("liveOverlayReady"))
            assert not bool(surface.property("proxySurfaceActive"))
            assert len(variant_list(surface.property("embeddedInteractiveRects"))) == 1
            assert "node-plot" in service._active_nodes

            actions = variant_list(surface.property("surfaceActions"))
            probe.setProperty("visible", False)
            settle()
            assert not surface.property("liveSurfaceActive"), "Hidden plot kept live surface active"
            assert "node-plot" not in service._active_nodes, "Hidden plot stayed active in service"
            assert variant_list(surface.property("surfaceActions")) == actions, "Hidden plot lost its actions"
            probe.setProperty("visible", True)
            settle()
            assert surface.property("liveSurfaceActive"), "Showing plot did not restore live activity"

            host.setProperty("viewportInteractionCacheActive", True)
            settle()
            assert not bool(surface.property("liveSurfaceActive"))
            assert not bool(surface.property("liveOverlayReady"))
            assert bool(surface.property("proxySurfaceActive"))
            assert bool(surface.property("cachedPreviewVisible"))
            assert variant_list(surface.property("embeddedInteractiveRects")) == []
            assert "node-plot" not in service._active_nodes

            host.setProperty("viewportInteractionCacheActive", False)
            settle()
            assert bool(surface.property("liveSurfaceActive"))
            assert bool(surface.property("liveOverlayReady"))
            assert not bool(surface.property("proxySurfaceActive"))
            assert "node-plot" in service._active_nodes

            host.setProperty("hostDragActive", True)
            settle()
            assert not bool(surface.property("liveSurfaceActive"))
            assert bool(surface.property("proxySurfaceActive"))
            assert "node-plot" not in service._active_nodes

            dispose_host_window(probe, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_plot_surface_live_preview_requires_viable_screen_size(self) -> None:
        self._run_qml_probe(
            "plot-surface-live-preview-size-gate",
            """
            from pathlib import Path

            from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            class PlotHostServiceStub(QObject):
                activeOverlayCountChanged = pyqtSignal()
                previewCacheRevisionChanged = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self._active_nodes = set()
                    self.calls = []

                @pyqtProperty(int, notify=activeOverlayCountChanged)
                def active_overlay_count(self):
                    return len(self._active_nodes)

                @pyqtProperty(int, notify=previewCacheRevisionChanged)
                def preview_cache_revision(self):
                    return 0

                @pyqtSlot(str, bool)
                def set_embedded_interaction_active(self, node_id, active):
                    normalized = str(node_id)
                    enabled = bool(active)
                    self.calls.append((normalized, enabled))
                    before_count = len(self._active_nodes)
                    if enabled:
                        self._active_nodes.add(normalized)
                    else:
                        self._active_nodes.discard(normalized)
                    if len(self._active_nodes) != before_count:
                        self.activeOverlayCountChanged.emit()

                @pyqtSlot(str, result=str)
                def cached_preview_source(self, node_id):
                    return ""

                @pyqtSlot(str, result=bool)
                def embedded_live_overlay_ready(self, node_id):
                    return str(node_id) in self._active_nodes

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            service = PlotHostServiceStub()
            engine.rootContext().setContextProperty("plotHostService", service)

            plot_dir = Path.cwd() / "ea_node_editor" / "ui_qml" / "components" / "graph" / "plot"
            qml = '''
            import QtQuick 2.15

            Item {
                id: root
                width: 360
                height: 260

                Item {
                    id: probeHost
                    objectName: "probeHost"
                    property bool hoverActive: false
                    property bool isSelected: true
                    property bool viewportInteractionCacheActive: false
                    property bool hostDragActive: false
                    property real currentZoom: 0.5
                    property var nodeData: ({
                        "node_id": "node-plot",
                        "surface_variant": "line",
                        "plot_surface": {
                            "plot_type": "line",
                            "live_backend_id": "pyqtgraph",
                            "embedded_rendering_suppressed": false
                        }
                    })
                    property var surfaceMetrics: ({
                        "body_left_margin": 0.0,
                        "body_top": 0.0,
                        "body_right_margin": 0.0,
                        "body_height": 220.0
                    })
                    property real resolvedCornerRadius: 6.0
                    property color inlineInputBackgroundColor: "#18202d"
                    property color selectedOutlineColor: "#5da9ff"
                    property color outlineColor: "#414a5d"
                    property color inlineDrivenTextColor: "#aeb8ce"
                    property color surfaceColor: "#1f2431"
                    property color headerTextColor: "#eef3ff"
                    property int nodeTextRenderType: Text.CurveRendering
                    property bool surfaceFullscreenAvailable: false
                    function surfaceFullscreenAction(_enabled, _primary) { return null; }
                    function requestSurfaceContentFullscreen() { return false; }
                    function currentViewportZoom() { return currentZoom; }
                }

                GraphPlotSurfaceBody {
                    id: surface
                    objectName: "graphNodePlotSurfaceProbe"
                    anchors.fill: parent
                    host: probeHost
                }
            }
            '''
            component = QQmlComponent(engine)
            component.setData(qml.encode("utf-8"), QUrl.fromLocalFile(str(plot_dir / "PlotSurfaceSizeGateProbe.qml")))
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load plot surface probe:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate plot surface probe:\\n" + errors)

            def settle(cycles=8):
                for _index in range(cycles):
                    app.processEvents()

            settle()
            host = probe.findChild(QObject, "probeHost")
            surface = probe.findChild(QObject, "graphNodePlotSurfaceProbe")
            assert host is not None
            assert surface is not None

            assert not bool(surface.property("liveSurfaceSizeViable"))
            assert not bool(surface.property("liveSurfaceActive"))
            assert "node-plot" not in service._active_nodes

            host.setProperty("currentZoom", 1.0)
            settle()
            assert bool(surface.property("liveSurfaceSizeViable"))
            assert bool(surface.property("liveSurfaceActive"))
            assert "node-plot" in service._active_nodes

            host.setProperty("currentZoom", 0.25)
            settle()
            assert not bool(surface.property("liveSurfaceSizeViable"))
            assert not bool(surface.property("liveSurfaceActive"))
            assert "node-plot" not in service._active_nodes
            assert ("node-plot", False) in service.calls

            probe.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_plot_surface_size_gate_is_pyqtgraph_only(self) -> None:
        self._run_qml_probe(
            "plot-surface-live-preview-size-gate-backend-aware",
            """
            from pathlib import Path

            from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            class PlotHostServiceStub(QObject):
                activeOverlayCountChanged = pyqtSignal()
                previewCacheRevisionChanged = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self._active_nodes = set()

                @pyqtProperty(int, notify=activeOverlayCountChanged)
                def active_overlay_count(self):
                    return len(self._active_nodes)

                @pyqtProperty(int, notify=previewCacheRevisionChanged)
                def preview_cache_revision(self):
                    return 0

                @pyqtSlot(str, bool)
                def set_embedded_interaction_active(self, node_id, active):
                    normalized = str(node_id)
                    before_count = len(self._active_nodes)
                    if bool(active):
                        self._active_nodes.add(normalized)
                    else:
                        self._active_nodes.discard(normalized)
                    if len(self._active_nodes) != before_count:
                        self.activeOverlayCountChanged.emit()

                @pyqtSlot(str, result=str)
                def cached_preview_source(self, node_id):
                    return ""

                @pyqtSlot(str, result=bool)
                def embedded_live_overlay_ready(self, node_id):
                    return str(node_id) in self._active_nodes

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            service = PlotHostServiceStub()
            engine.rootContext().setContextProperty("plotHostService", service)

            plot_dir = Path.cwd() / "ea_node_editor" / "ui_qml" / "components" / "graph" / "plot"
            qml = '''
            import QtQuick 2.15

            Item {
                id: root
                width: 360
                height: 260

                Item {
                    id: probeHost
                    objectName: "probeHost"
                    property bool hoverActive: false
                    property bool isSelected: true
                    property bool viewportInteractionCacheActive: false
                    property bool hostDragActive: false
                    property real currentZoom: 0.25
                    property var nodeData: ({
                        "node_id": "node-plot",
                        "surface_variant": "surface",
                        "plot_surface": {
                            "plot_type": "surface",
                            "live_backend_id": "pyvista",
                            "embedded_rendering_suppressed": false
                        }
                    })
                    property var surfaceMetrics: ({
                        "body_left_margin": 0.0,
                        "body_top": 0.0,
                        "body_right_margin": 0.0,
                        "body_height": 220.0
                    })
                    property real resolvedCornerRadius: 6.0
                    property color inlineInputBackgroundColor: "#18202d"
                    property color selectedOutlineColor: "#5da9ff"
                    property color outlineColor: "#414a5d"
                    property color inlineDrivenTextColor: "#aeb8ce"
                    property color surfaceColor: "#1f2431"
                    property color headerTextColor: "#eef3ff"
                    property int nodeTextRenderType: Text.CurveRendering
                    property bool surfaceFullscreenAvailable: false
                    function surfaceFullscreenAction(_enabled, _primary) { return null; }
                    function requestSurfaceContentFullscreen() { return false; }
                    function currentViewportZoom() { return currentZoom; }
                }

                GraphPlotSurfaceBody {
                    id: surface
                    objectName: "graphNodePlotSurfaceProbe"
                    anchors.fill: parent
                    host: probeHost
                }
            }
            '''
            component = QQmlComponent(engine)
            component.setData(qml.encode("utf-8"), QUrl.fromLocalFile(str(plot_dir / "PlotSurfaceBackendGateProbe.qml")))
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load plot surface probe:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate plot surface probe:\\n" + errors)

            def settle(cycles=8):
                for _index in range(cycles):
                    app.processEvents()

            settle()
            surface = probe.findChild(QObject, "graphNodePlotSurfaceProbe")
            assert surface is not None

            assert not bool(surface.property("liveSurfaceSizeGateRequired"))
            assert bool(surface.property("liveSurfaceSizeViable"))
            assert bool(surface.property("liveSurfaceActive"))
            assert "node-plot" in service._active_nodes

            probe.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_plot_surface_blanks_cached_image_on_node_change_and_fullscreen_open(self) -> None:
        self._run_qml_probe(
            "plot-surface-cached-image-blanking",
            """
            from pathlib import Path

            from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            class PlotHostServiceStub(QObject):
                activeOverlayCountChanged = pyqtSignal()
                plotOverlayRevisionChanged = pyqtSignal()
                previewCacheRevisionChanged = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self.calls = []
                    self._preview_cache_revision = 1

                @pyqtProperty(int, notify=activeOverlayCountChanged)
                def active_overlay_count(self):
                    return 0

                @pyqtProperty(int, notify=plotOverlayRevisionChanged)
                def plot_overlay_revision(self):
                    return 0

                @pyqtProperty(int, notify=previewCacheRevisionChanged)
                def preview_cache_revision(self):
                    return self._preview_cache_revision

                @pyqtSlot(str, bool)
                def set_embedded_interaction_active(self, node_id, active):
                    self.calls.append((str(node_id), bool(active)))

                @pyqtSlot(str, result=str)
                def cached_preview_source(self, node_id):
                    return "image://plot-preview-cache/ws/" + str(node_id)

                @pyqtSlot(str, result=bool)
                def embedded_live_overlay_ready(self, node_id):
                    return False

            class FullscreenBridgeStub(QObject):
                contentFullscreenChanged = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self._open = False

                @pyqtProperty(bool, notify=contentFullscreenChanged)
                def open(self):
                    return self._open

                def set_open(self, value):
                    self._open = bool(value)
                    self.contentFullscreenChanged.emit()

            def source_text(item):
                value = item.property("source")
                return value.toString() if hasattr(value, "toString") else str(value)

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            service = PlotHostServiceStub()
            fullscreen_bridge = FullscreenBridgeStub()
            engine.rootContext().setContextProperty("plotHostService", service)
            engine.rootContext().setContextProperty("contentFullscreenBridge", fullscreen_bridge)

            plot_dir = Path.cwd() / "ea_node_editor" / "ui_qml" / "components" / "graph" / "plot"
            qml = '''
            import QtQuick 2.15

            Item {
                id: root
                width: 360
                height: 260

                Item {
                    id: probeHost
                    objectName: "probeHost"
                    property bool hoverActive: false
                    property bool isSelected: true
                    property bool viewportInteractionCacheActive: false
                    property bool hostDragActive: false
                    property var nodeData: ({
                        "node_id": "plot-a",
                        "surface_variant": "line",
                        "plot_surface": {
                            "plot_type": "line",
                            "live_backend_id": "pyqtgraph",
                            "embedded_rendering_suppressed": false
                        }
                    })
                    property var surfaceMetrics: ({
                        "body_left_margin": 0.0,
                        "body_top": 0.0,
                        "body_right_margin": 0.0,
                        "body_height": 220.0
                    })
                    property real resolvedCornerRadius: 6.0
                    property color inlineInputBackgroundColor: "#18202d"
                    property color selectedOutlineColor: "#5da9ff"
                    property color outlineColor: "#414a5d"
                    property color inlineDrivenTextColor: "#aeb8ce"
                    property color surfaceColor: "#1f2431"
                    property color headerTextColor: "#eef3ff"
                    property int nodeTextRenderType: Text.CurveRendering
                    property bool surfaceFullscreenAvailable: false
                    function surfaceFullscreenAction(_enabled, _primary) { return null; }
                    function requestSurfaceContentFullscreen() { return false; }
                }

                GraphPlotSurfaceBody {
                    id: surface
                    objectName: "graphNodePlotSurfaceProbe"
                    anchors.fill: parent
                    host: probeHost
                }
            }
            '''
            component = QQmlComponent(engine)
            component.setData(qml.encode("utf-8"), QUrl.fromLocalFile(str(plot_dir / "PlotSurfaceBlankingProbe.qml")))
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load plot surface probe:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate plot surface probe:\\n" + errors)

            def settle(cycles=8):
                for _index in range(cycles):
                    app.processEvents()

            settle()
            host = probe.findChild(QObject, "probeHost")
            surface = probe.findChild(QObject, "graphNodePlotSurfaceProbe")
            cached_image = probe.findChild(QObject, "graphNodePlotCachedPreviewImage")
            assert host is not None
            assert surface is not None
            assert cached_image is not None

            assert bool(surface.property("cachedPreviewVisible"))
            assert source_text(cached_image).endswith("/plot-a")
            assert ("plot-a", True) in service.calls

            host.setProperty("nodeData", {
                "node_id": "plot-b",
                "surface_variant": "line",
                "plot_surface": {
                    "plot_type": "line",
                    "live_backend_id": "pyqtgraph",
                    "embedded_rendering_suppressed": False,
                },
            })
            assert source_text(cached_image) == ""
            assert ("plot-a", False) in service.calls
            settle()
            assert bool(surface.property("cachedPreviewVisible"))
            assert source_text(cached_image).endswith("/plot-b")

            fullscreen_bridge.set_open(True)
            settle()
            assert not bool(surface.property("cachedPreviewVisible"))
            assert not bool(surface.property("placeholderPreviewVisible"))
            assert source_text(cached_image) == ""
            assert ("plot-b", False) in service.calls

            probe.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_plot_surface_rechecks_overlay_readiness_when_revision_changes_but_count_does_not(self) -> None:
        self._run_qml_probe(
            "plot-surface-overlay-revision-refresh",
            """
            from pathlib import Path

            from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            class PlotHostServiceStub(QObject):
                activeOverlayCountChanged = pyqtSignal()
                plotOverlayRevisionChanged = pyqtSignal()
                previewCacheRevisionChanged = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self._plot_overlay_revision = 1
                    self._preview_cache_revision = 1
                    self._ready_nodes = set()
                    self.ready_calls = []

                @pyqtProperty(int, notify=activeOverlayCountChanged)
                def active_overlay_count(self):
                    return 1

                @pyqtProperty(int, notify=plotOverlayRevisionChanged)
                def plot_overlay_revision(self):
                    return self._plot_overlay_revision

                @pyqtProperty(int, notify=previewCacheRevisionChanged)
                def preview_cache_revision(self):
                    return self._preview_cache_revision

                @pyqtSlot(str, bool)
                def set_embedded_interaction_active(self, node_id, active):
                    pass

                @pyqtSlot(str, result=str)
                def cached_preview_source(self, node_id):
                    return "image://plot-preview-cache/ws/" + str(node_id)

                @pyqtSlot(str, result=bool)
                def embedded_live_overlay_ready(self, node_id):
                    normalized = str(node_id)
                    self.ready_calls.append(normalized)
                    return normalized in self._ready_nodes

                def mark_ready(self, node_id):
                    self._ready_nodes.add(str(node_id))
                    self._plot_overlay_revision += 1
                    self.plotOverlayRevisionChanged.emit()

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            service = PlotHostServiceStub()
            engine.rootContext().setContextProperty("plotHostService", service)

            plot_dir = Path.cwd() / "ea_node_editor" / "ui_qml" / "components" / "graph" / "plot"
            qml = '''
            import QtQuick 2.15

            Item {
                id: root
                width: 360
                height: 260

                Item {
                    id: probeHost
                    objectName: "probeHost"
                    property bool hoverActive: true
                    property bool isSelected: false
                    property bool viewportInteractionCacheActive: false
                    property bool hostDragActive: false
                    property var nodeData: ({
                        "node_id": "node-plot",
                        "surface_variant": "line",
                        "plot_surface": {
                            "plot_type": "line",
                            "live_backend_id": "pyqtgraph",
                            "embedded_rendering_suppressed": false
                        }
                    })
                    property var surfaceMetrics: ({
                        "body_left_margin": 0.0,
                        "body_top": 0.0,
                        "body_right_margin": 0.0,
                        "body_height": 220.0
                    })
                    property real resolvedCornerRadius: 6.0
                    property color inlineInputBackgroundColor: "#18202d"
                    property color selectedOutlineColor: "#5da9ff"
                    property color outlineColor: "#414a5d"
                    property color inlineDrivenTextColor: "#aeb8ce"
                    property color surfaceColor: "#1f2431"
                    property color headerTextColor: "#eef3ff"
                    property int nodeTextRenderType: Text.CurveRendering
                    property bool surfaceFullscreenAvailable: false
                    function surfaceFullscreenAction(_enabled, _primary) { return null; }
                    function requestSurfaceContentFullscreen() { return false; }
                }

                GraphPlotSurfaceBody {
                    id: surface
                    objectName: "graphNodePlotSurfaceProbe"
                    anchors.fill: parent
                    host: probeHost
                }
            }
            '''
            component = QQmlComponent(engine)
            component.setData(qml.encode("utf-8"), QUrl.fromLocalFile(str(plot_dir / "PlotSurfaceRevisionProbe.qml")))
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load plot surface probe:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate plot surface probe:\\n" + errors)

            def settle(cycles=8):
                for _index in range(cycles):
                    app.processEvents()

            settle()
            surface = probe.findChild(QObject, "graphNodePlotSurfaceProbe")
            assert surface is not None
            assert not bool(surface.property("liveOverlayReady"))
            calls_before = len(service.ready_calls)

            service.mark_ready("node-plot")
            settle()

            assert bool(surface.property("liveOverlayReady"))
            assert len(service.ready_calls) > calls_before

            probe.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_wheel_zoom_controller_enters_cache_window_for_live_plots_and_viewers(self) -> None:
        self._run_qml_probe(
            "plot-wheel-zoom-viewport-cache-eligibility",
            """
            from pathlib import Path

            from PyQt6.QtCore import QUrl
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()

            graph_canvas_dir = Path.cwd() / "ea_node_editor" / "ui_qml" / "components" / "graph_canvas"
            qml = '''
            import QtQuick 2.15
            import QtQml 2.15

            Item {
                id: root

                QtObject {
                    id: activePlotBridge
                    property var nodes_model: [{
                        "surface_family": "plot",
                        "plot_surface": {"embedded_rendering_suppressed": false}
                    }]
                }
                Item {
                    id: activePlotCanvas
                    property var sceneStateBridge: activePlotBridge
                }
                GraphCanvasViewportController {
                    id: activePlotController
                    canvasItem: activePlotCanvas
                }
                property bool activePlotCache: activePlotController.shouldUseViewportInteractionQualityForWheelZoom()

                QtObject {
                    id: suppressedPlotBridge
                    property var nodes_model: [{
                        "surface_family": "plot",
                        "plot_surface": {"embedded_rendering_suppressed": true}
                    }]
                }
                Item {
                    id: suppressedPlotCanvas
                    property var sceneStateBridge: suppressedPlotBridge
                }
                GraphCanvasViewportController {
                    id: suppressedPlotController
                    canvasItem: suppressedPlotCanvas
                }
                property bool suppressedPlotCache: suppressedPlotController.shouldUseViewportInteractionQualityForWheelZoom()

                QtObject {
                    id: activeViewerBridge
                    property var nodes_model: [{
                        "surface_family": "viewer",
                        "viewer_surface": {"live_surface_supported": true}
                    }]
                }
                Item {
                    id: activeViewerCanvas
                    property var sceneStateBridge: activeViewerBridge
                }
                GraphCanvasViewportController {
                    id: activeViewerController
                    canvasItem: activeViewerCanvas
                }
                property bool activeViewerCache: activeViewerController.shouldUseViewportInteractionQualityForWheelZoom()

                QtObject {
                    id: nonPlotBridge
                    property var nodes_model: [{
                        "surface_family": "media",
                        "render_quality": {"supported_quality_tiers": ["full", "proxy"]}
                    }]
                }
                Item {
                    id: nonPlotCanvas
                    property var sceneStateBridge: nonPlotBridge
                }
                GraphCanvasViewportController {
                    id: nonPlotController
                    canvasItem: nonPlotCanvas
                }
                property bool nonPlotCache: nonPlotController.shouldUseViewportInteractionQualityForWheelZoom()
            }
            '''
            component = QQmlComponent(engine)
            component.setData(qml.encode("utf-8"), QUrl.fromLocalFile(str(graph_canvas_dir / "ViewportControllerProbe.qml")))
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load viewport controller probe:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate viewport controller probe:\\n" + errors)
            app.processEvents()

            assert bool(probe.property("activePlotCache"))
            assert not bool(probe.property("suppressedPlotCache"))
            assert bool(probe.property("activeViewerCache"))
            assert not bool(probe.property("nonPlotCache"))

            probe.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_live_surface_deactivation_survives_synchronous_state_flip_without_binding_loop(self) -> None:
        self._run_qml_probe(
            "plot-surface-embedded-interaction-no-binding-loop",
            """
            from pathlib import Path

            from PyQt6.QtCore import (
                QObject,
                QUrl,
                pyqtProperty,
                pyqtSignal,
                pyqtSlot,
                qInstallMessageHandler,
            )
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            qt_messages = []

            def capture_qt_message(_message_type, _context, message):
                qt_messages.append(str(message))

            previous_message_handler = qInstallMessageHandler(capture_qt_message)

            class PlotHostServiceStub(QObject):
                # Mirrors the real PlotHostService signal wiring: a single
                # state_changed notifies plot_overlay_revision and
                # active_overlay_count, and a separate preview_cache_changed
                # notifies preview_cache_revision. Deactivation re-emits both
                # synchronously, the same way _capture_cached_live_state_for_key
                # and _release_inactive_embedded_overlay do in production.
                state_changed = pyqtSignal()
                preview_cache_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self.calls = []
                    self._active_nodes = set()
                    self._preview_cache_revision = 0
                    self._plot_overlay_revision = 0

                @pyqtProperty(int, notify=state_changed)
                def active_overlay_count(self):
                    return len(self._active_nodes)

                @pyqtProperty(int, notify=state_changed)
                def plot_overlay_revision(self):
                    return self._plot_overlay_revision

                @pyqtProperty(int, notify=preview_cache_changed)
                def preview_cache_revision(self):
                    return self._preview_cache_revision

                @pyqtSlot(str, bool)
                def set_embedded_interaction_active(self, node_id, active):
                    normalized = str(node_id)
                    enabled = bool(active)
                    self.calls.append((normalized, enabled))
                    if enabled:
                        self._active_nodes.add(normalized)
                        return
                    if normalized not in self._active_nodes:
                        return
                    self._active_nodes.discard(normalized)
                    self._preview_cache_revision += 1
                    self.preview_cache_changed.emit()
                    self._plot_overlay_revision += 1
                    self.state_changed.emit()

                @pyqtSlot(str, result=str)
                def cached_preview_source(self, node_id):
                    return "image://plot-preview-cache/ws/" + str(node_id)

                @pyqtSlot(str, result=bool)
                def embedded_live_overlay_ready(self, node_id):
                    return str(node_id) in self._active_nodes

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            service = PlotHostServiceStub()
            engine.rootContext().setContextProperty("plotHostService", service)

            plot_dir = Path.cwd() / "ea_node_editor" / "ui_qml" / "components" / "graph" / "plot"
            qml = '''
            import QtQuick 2.15

            Item {
                id: root
                width: 360
                height: 260

                Item {
                    id: probeHost
                    objectName: "probeHost"
                    property bool hoverActive: false
                    property bool isSelected: true
                    property bool viewportInteractionCacheActive: false
                    property bool hostDragActive: false
                    property var nodeData: ({
                        "node_id": "node-plot",
                        "surface_variant": "line",
                        "plot_surface": {
                            "plot_type": "line",
                            "live_backend_id": "pyqtgraph",
                            "embedded_rendering_suppressed": false
                        }
                    })
                    property var surfaceMetrics: ({
                        "body_left_margin": 0.0,
                        "body_top": 0.0,
                        "body_right_margin": 0.0,
                        "body_height": 220.0
                    })
                    property real resolvedCornerRadius: 6.0
                    property color inlineInputBackgroundColor: "#18202d"
                    property color selectedOutlineColor: "#5da9ff"
                    property color outlineColor: "#414a5d"
                    property color inlineDrivenTextColor: "#aeb8ce"
                    property color surfaceColor: "#1f2431"
                    property color headerTextColor: "#eef3ff"
                    property int nodeTextRenderType: Text.CurveRendering
                    property bool surfaceFullscreenAvailable: false
                    function surfaceFullscreenAction(_enabled, _primary) { return null; }
                    function requestSurfaceContentFullscreen() { return false; }
                }

                GraphPlotSurfaceBody {
                    id: surface
                    objectName: "graphNodePlotSurfaceProbe"
                    anchors.fill: parent
                    host: probeHost
                }
            }
            '''
            component = QQmlComponent(engine)
            component.setData(qml.encode("utf-8"), QUrl.fromLocalFile(str(plot_dir / "PlotSurfaceBindingLoopProbe.qml")))
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load plot surface probe:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate plot surface probe:\\n" + errors)

            def settle(cycles=8):
                for _index in range(cycles):
                    app.processEvents()

            try:
                settle()
                host = probe.findChild(QObject, "probeHost")
                surface = probe.findChild(QObject, "graphNodePlotSurfaceProbe")
                assert host is not None
                assert surface is not None
                assert bool(surface.property("liveSurfaceActive"))
                assert "node-plot" in service._active_nodes
                qt_messages.clear()

                # A transient-interaction change handler (onLiveSurfaceActiveChanged)
                # calls _syncEmbeddedInteraction synchronously, which deactivates the
                # embedded overlay and re-emits state_changed/preview_cache_changed
                # from inside that same call. That must not re-enter a binding that
                # is still being evaluated.
                host.setProperty("viewportInteractionCacheActive", True)
                settle()

                assert not bool(surface.property("liveSurfaceActive"))
                assert "node-plot" not in service._active_nodes
                assert service.calls[-1] == ("node-plot", False)

                host.setProperty("viewportInteractionCacheActive", False)
                settle()
                assert bool(surface.property("liveSurfaceActive"))
                assert "node-plot" in service._active_nodes
            finally:
                probe.deleteLater()
                engine.deleteLater()
                app.processEvents()
                qInstallMessageHandler(previous_message_handler)

            binding_loop_messages = [
                message for message in qt_messages if "Binding loop detected" in message
            ]
            assert not binding_loop_messages, qt_messages
            """,
        )

    def test_plot_surface_confirms_cached_preview_swap_to_host_service(self) -> None:
        self._run_qml_probe(
            "plot-surface-preview-swap-confirmation",
            """
            from pathlib import Path

            from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            class PlotHostServiceStub(QObject):
                state_changed = pyqtSignal()
                preview_cache_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self.preview_swap_calls = []
                    self._preview_cache_revision = 1

                @pyqtProperty(int, notify=state_changed)
                def active_overlay_count(self):
                    return 0

                @pyqtProperty(int, notify=state_changed)
                def plot_overlay_revision(self):
                    return 0

                @pyqtProperty(int, notify=preview_cache_changed)
                def preview_cache_revision(self):
                    return self._preview_cache_revision

                @pyqtSlot(str, bool)
                def set_embedded_interaction_active(self, node_id, active):
                    pass

                @pyqtSlot(str, result=str)
                def cached_preview_source(self, node_id):
                    return (
                        "image://plot-preview-cache/preview?workspace=ws-plot&node="
                        + str(node_id)
                        + "&revision="
                        + str(self._preview_cache_revision)
                    )

                @pyqtSlot(str, result=bool)
                def embedded_live_overlay_ready(self, node_id):
                    return False

                @pyqtSlot(str, str)
                def notify_cached_preview_swapped(self, node_id, source):
                    self.preview_swap_calls.append((str(node_id), str(source)))

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            service = PlotHostServiceStub()
            engine.rootContext().setContextProperty("plotHostService", service)

            plot_dir = Path.cwd() / "ea_node_editor" / "ui_qml" / "components" / "graph" / "plot"
            qml = '''
            import QtQuick 2.15

            Item {
                id: root
                width: 360
                height: 260

                Item {
                    id: probeHost
                    objectName: "probeHost"
                    property bool hoverActive: false
                    property bool isSelected: false
                    property bool viewportInteractionCacheActive: false
                    property bool hostDragActive: false
                    property var nodeData: ({
                        "node_id": "node-plot",
                        "surface_variant": "line",
                        "plot_surface": {
                            "plot_type": "line",
                            "live_backend_id": "pyqtgraph",
                            "embedded_rendering_suppressed": false
                        }
                    })
                    property var surfaceMetrics: ({
                        "body_left_margin": 0.0,
                        "body_top": 0.0,
                        "body_right_margin": 0.0,
                        "body_height": 220.0
                    })
                    property real resolvedCornerRadius: 6.0
                    property color inlineInputBackgroundColor: "#18202d"
                    property color selectedOutlineColor: "#5da9ff"
                    property color outlineColor: "#414a5d"
                    property color inlineDrivenTextColor: "#aeb8ce"
                    property color surfaceColor: "#1f2431"
                    property color headerTextColor: "#eef3ff"
                    property int nodeTextRenderType: Text.CurveRendering
                    property bool surfaceFullscreenAvailable: false
                    function surfaceFullscreenAction(_enabled, _primary) { return null; }
                    function requestSurfaceContentFullscreen() { return false; }
                }

                GraphPlotSurfaceBody {
                    id: surface
                    objectName: "graphNodePlotSurfaceProbe"
                    anchors.fill: parent
                    host: probeHost
                }
            }
            '''
            component = QQmlComponent(engine)
            component.setData(qml.encode("utf-8"), QUrl.fromLocalFile(str(plot_dir / "PlotSurfacePreviewSwapProbe.qml")))
            if component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to load plot surface probe:\\n" + errors)
            probe = component.create()
            if probe is None:
                errors = "\\n".join(error.toString() for error in component.errors())
                raise AssertionError("Failed to instantiate plot surface probe:\\n" + errors)

            def settle(cycles=8):
                for _index in range(cycles):
                    app.processEvents()

            def image_source_text(image):
                value = image.property("source")
                return value.toString() if hasattr(value, "toString") else str(value)

            try:
                settle()
                surface = probe.findChild(QObject, "graphNodePlotSurfaceProbe")
                cached_image = probe.findChild(QObject, "graphNodePlotCachedPreviewImage")
                assert surface is not None
                assert cached_image is not None
                assert bool(surface.property("cachedPreviewVisible"))
                initial_source = service.cached_preview_source("node-plot")
                assert service.preview_swap_calls[-1] == (
                    "node-plot",
                    initial_source,
                ), service.preview_swap_calls

                # A live-exit capture publishes a new revision; the surface
                # must confirm the swapped source back to the host service.
                service._preview_cache_revision += 1
                service.preview_cache_changed.emit()
                settle()

                swapped_source = service.cached_preview_source("node-plot")
                assert swapped_source != initial_source
                assert service.preview_swap_calls[-1] == (
                    "node-plot",
                    swapped_source,
                ), service.preview_swap_calls
                assert image_source_text(cached_image) == swapped_source
            finally:
                probe.deleteLater()
                engine.deleteLater()
                app.processEvents()
            """,
        )
