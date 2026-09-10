from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget

from ea_node_editor.ui_qml.plot_host_service import PlotHostService
from ea_node_editor.ui_qml.plot_widget_binder import (
    PlotWidgetBindRequest,
    PlotWidgetReleaseRequest,
)
from ea_node_editor.ui_qml.surface_contracts import surface_spec_payload_for_values


class _FakeSceneBridge(QObject):
    workspace_changed = pyqtSignal(str)
    nodes_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.workspace_id = "ws-plot"
        self.nodes_model: list[dict[str, object]] = []


class _FakeContentFullscreenBridge(QObject):
    content_fullscreen_changed = pyqtSignal()
    open = False
    content_kind = ""
    workspace_id = ""
    node_id = ""
    plot_payload: dict[str, object] = {}


class _FakeOverlayManager:
    def __init__(self) -> None:
        self.content_fullscreen_target = None
        self.active_specs: list[object] = []
        self.containers: dict[tuple[str, str], QWidget] = {}
        self.widgets: dict[tuple[str, str], QWidget] = {}
        self.detach_calls: list[tuple[str, str]] = []
        self.take_calls: list[tuple[str, str]] = []

    def set_content_fullscreen_target(self, overlay) -> None:  # noqa: ANN001
        self.content_fullscreen_target = overlay

    def set_active_overlays(self, overlays) -> None:  # noqa: ANN001
        self.active_specs = list(overlays)
        desired = {
            (str(overlay.workspace_id), str(overlay.node_id))
            for overlay in self.active_specs
        }
        for key in desired:
            self.containers.setdefault(key, QWidget())
        for key in list(self.containers):
            if key not in desired:
                self.containers.pop(key, None)
                self.widgets.pop(key, None)

    def overlay_container(self, node_id: str, *, workspace_id: str = "") -> QWidget | None:
        return self.containers.get((workspace_id, node_id))

    def overlay_widget(self, node_id: str, *, workspace_id: str = "") -> QWidget | None:
        return self.widgets.get((workspace_id, node_id))

    def attach_overlay_widget(self, node_id: str, widget: QWidget, *, workspace_id: str = "") -> bool:
        self.widgets[(workspace_id, node_id)] = widget
        container = self.containers.get((workspace_id, node_id))
        if container is not None and widget.parent() is not container:
            widget.setParent(container)
        return True

    def detach_overlay_widget(self, node_id: str, *, workspace_id: str = "") -> None:
        key = (workspace_id, node_id)
        self.detach_calls.append(key)
        widget = self.widgets.pop(key, None)
        if widget is not None:
            widget.close()

    def take_overlay_widget(self, node_id: str, *, workspace_id: str = "") -> QWidget | None:
        key = (workspace_id, node_id)
        self.take_calls.append(key)
        return self.widgets.pop(key, None)


class _CloseTrackingWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.close_calls = 0

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        self.close_calls += 1
        super().closeEvent(event)


class _FakePlotBinder:
    def __init__(self) -> None:
        self.bind_calls: list[PlotWidgetBindRequest] = []
        self.release_calls: list[PlotWidgetReleaseRequest] = []

    def bind_widget(self, request: PlotWidgetBindRequest) -> QWidget:
        self.bind_calls.append(request)
        if isinstance(request.current_widget, QWidget):
            if request.container is not None and request.current_widget.parent() is not request.container:
                request.current_widget.setParent(request.container)
            return request.current_widget
        return _CloseTrackingWidget(request.container)

    def release_widget(self, request: PlotWidgetReleaseRequest) -> None:
        self.release_calls.append(request)


def _plot_payload(
    *,
    node_id: str = "node-plot",
    suppressed: bool = True,
) -> dict[str, object]:
    return {
        "workspace_id": "ws-plot",
        "node_id": node_id,
        "type_id": "plot.scatter",
        "title": "Line Plot",
        "surface_family": "plot",
        "surface_variant": "line",
        "surface_spec": surface_spec_payload_for_values(type_id="plot.scatter", family="plot", variant="scatter"),
        "properties": {
            "backend": "auto",
            "title": "Line Plot",
            "series": [{"x": [0, 1], "y": [1.0, 2.0]}],
        },
        "plot_surface": {
            "plot_type": "line",
            "render_in_canvas": not suppressed,
            "lightweight_canvas": False,
            "embedded_rendering_suppressed": suppressed,
            "embedded_rendering_suppressed_by": ["render_in_canvas"] if suppressed else [],
        },
    }


def _service(
    *,
    scene: _FakeSceneBridge,
    overlay_manager: _FakeOverlayManager,
    binder: _FakePlotBinder,
) -> PlotHostService:
    service = PlotHostService(
        active_workspace_id_provider=lambda: scene.workspace_id,
        scene_bridge=scene,
        content_fullscreen_bridge=_FakeContentFullscreenBridge(),  # type: ignore[arg-type]
        overlay_manager=overlay_manager,  # type: ignore[arg-type]
    )
    service.register_binder("pyqtgraph", binder)
    return service


def test_detached_window_hosts_suppressed_plot_without_overlay_duplicate(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    scene.nodes_model = [_plot_payload(suppressed=True)]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    service = _service(scene=scene, overlay_manager=overlay_manager, binder=binder)

    assert service.open_detached_plot("node-plot") is True
    service.sync()

    assert service.detached_window_count == 1
    assert service.active_overlay_count == 1
    assert overlay_manager.active_specs == []
    assert overlay_manager.widgets == {}
    assert len(binder.bind_calls) == 1
    window = service._detached_windows[("ws-plot", "node-plot")]  # noqa: SLF001
    assert window.widget is not None
    assert window.widget.parent() is window.container

    assert service.open_detached_plot("node-plot") is True
    service.sync()

    assert service.detached_window_count == 1
    assert service.active_overlay_count == 1
    assert len(binder.bind_calls) == 1


def test_detached_window_retargets_existing_embedded_widget_without_second_host(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    scene.nodes_model = [_plot_payload(suppressed=False)]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    service = _service(scene=scene, overlay_manager=overlay_manager, binder=binder)

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()
    embedded_widget = overlay_manager.widgets[("ws-plot", "node-plot")]

    assert service.open_detached_plot("node-plot") is True
    service.sync()

    window = service._detached_windows[("ws-plot", "node-plot")]  # noqa: SLF001
    assert service.active_overlay_count == 1
    assert len(binder.bind_calls) == 1
    assert window.widget is embedded_widget
    assert embedded_widget.parent() is window.container
    assert overlay_manager.widgets == {}
    assert overlay_manager.take_calls == [("ws-plot", "node-plot")]
    assert overlay_manager.detach_calls == []
    assert isinstance(embedded_widget, _CloseTrackingWidget)
    assert embedded_widget.close_calls == 0


def test_detached_window_cleans_up_on_node_removal_workspace_change_and_shutdown(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    scene.nodes_model = [_plot_payload(suppressed=True)]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    service = _service(scene=scene, overlay_manager=overlay_manager, binder=binder)

    assert service.open_detached_plot("node-plot") is True
    service.sync()
    scene.nodes_model = []
    service.sync()

    assert service.detached_window_count == 0
    assert service.active_overlay_count == 0
    assert len(binder.release_calls) == 1

    scene.nodes_model = [_plot_payload(suppressed=True)]
    assert service.open_detached_plot("node-plot") is True
    service.sync()
    scene.workspace_id = "ws-other"
    scene.workspace_changed.emit("ws-other")
    service.sync()

    assert service.detached_window_count == 0
    assert service.active_overlay_count == 0

    scene.workspace_id = "ws-plot"
    scene.nodes_model = [_plot_payload(suppressed=True)]
    assert service.open_detached_plot("node-plot") is True
    service.sync()
    service.shutdown(reason="test_shutdown")

    assert service.detached_window_count == 0
    assert service.active_overlay_count == 0
