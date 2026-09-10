from __future__ import annotations

import copy
from unittest.mock import patch

from PyQt6.QtCore import QObject, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QWidget

from ea_node_editor.ui.plot_preview_cache_provider import PlotPreviewCacheImageProvider
from ea_node_editor.ui_qml import plot_host_service as plot_host_module
from ea_node_editor.ui_qml.plot_host_service import PlotHostService
from ea_node_editor.ui_qml.native_overlay_owners import PLOT_HOST_OVERLAY_OWNER
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

    def __init__(self) -> None:
        super().__init__()
        self.open = False
        self.content_kind = ""
        self.workspace_id = ""
        self.node_id = ""
        self.plot_payload: dict[str, object] = {}

    def open_plot(self, payload: dict[str, object]) -> None:
        self.open = True
        self.content_kind = "plot"
        self.workspace_id = str(payload["workspace_id"])
        self.node_id = str(payload["node_id"])
        self.plot_payload = dict(payload)
        self.content_fullscreen_changed.emit()


class _FakeOverlayManager:
    def __init__(self) -> None:
        self.content_fullscreen_target = None
        self.active_specs: list[object] = []
        self.active_specs_by_owner: dict[str, list[object]] = {}
        self.containers: dict[tuple[str, str], QWidget] = {}
        self.widgets: dict[tuple[str, str], QWidget] = {}
        self.geometry_ready: set[tuple[str, str]] = set()
        self.sync_calls = 0

    def set_content_fullscreen_target(self, overlay) -> None:  # noqa: ANN001
        self.content_fullscreen_target = overlay

    def set_active_overlays(self, overlays) -> None:  # noqa: ANN001
        self.active_specs = list(overlays)
        self.active_specs_by_owner["default"] = list(self.active_specs)
        self._reconcile_active_specs(self.active_specs)

    def set_active_overlays_for_owner(self, owner: str, overlays) -> None:  # noqa: ANN001
        self.active_specs = list(overlays)
        self.active_specs_by_owner[str(owner)] = list(self.active_specs)
        self._reconcile_active_specs(self.active_specs)

    def _reconcile_active_specs(self, overlays: list[object]) -> None:
        desired = {
            (str(overlay.workspace_id), str(overlay.node_id))
            for overlay in overlays
        }
        for key in desired:
            self.containers.setdefault(key, QWidget())
        for key in list(self.containers):
            if key not in desired:
                self.containers.pop(key, None)
                self.widgets.pop(key, None)
                self.geometry_ready.discard(key)

    def overlay_container(self, node_id: str, *, workspace_id: str = "") -> QWidget | None:
        return self.containers.get((workspace_id, node_id))

    def overlay_widget(self, node_id: str, *, workspace_id: str = "") -> QWidget | None:
        return self.widgets.get((workspace_id, node_id))

    def overlay_geometry_ready(self, node_id: str, *, workspace_id: str = "") -> bool:
        return (workspace_id, node_id) in self.geometry_ready

    def attach_overlay_widget(self, node_id: str, widget: QWidget, *, workspace_id: str = "") -> bool:
        key = (workspace_id, node_id)
        self.widgets[key] = widget
        self.geometry_ready.discard(key)
        container = self.containers.get(key)
        if container is not None and widget.parent() is not container:
            widget.setParent(container)
        return True

    def detach_overlay_widget(self, node_id: str, *, workspace_id: str = "") -> None:
        key = (workspace_id, node_id)
        self.widgets.pop(key, None)
        self.geometry_ready.discard(key)

    def sync(self) -> None:
        self.sync_calls += 1
        for key in self.widgets:
            if key in self.containers:
                self.geometry_ready.add(key)


class _FakePlotBinder:
    def __init__(self) -> None:
        self.bind_calls: list[PlotWidgetBindRequest] = []
        self.release_calls: list[PlotWidgetReleaseRequest] = []
        self.release_widget_visible_states: list[bool] = []
        self.capture_preview_calls: list[QWidget] = []
        self.captured_preview_image = QImage()
        self.capture_view_state_calls: list[QWidget] = []
        self.captured_view_state: object | None = None
        self.restore_view_state_calls: list[tuple[QWidget, object]] = []
        self.refresh_after_attach_calls: list[QWidget] = []

    def bind_widget(self, request: PlotWidgetBindRequest) -> QWidget:
        self.bind_calls.append(request)
        if isinstance(request.current_widget, QWidget):
            return request.current_widget
        return QWidget(request.container)

    def release_widget(self, request: PlotWidgetReleaseRequest) -> None:
        self.release_calls.append(request)
        self.release_widget_visible_states.append(
            bool(request.widget.isVisible()) if isinstance(request.widget, QWidget) else False
        )

    def capture_preview_image(self, widget: QWidget) -> QImage:
        self.capture_preview_calls.append(widget)
        return self.captured_preview_image.copy()

    def refresh_after_attach(self, widget: QWidget) -> None:
        self.refresh_after_attach_calls.append(widget)

    def capture_view_state(self, widget: QWidget) -> object | None:
        self.capture_view_state_calls.append(widget)
        return self.captured_view_state

    def restore_view_state(self, widget: QWidget, state: object) -> bool:
        self.restore_view_state_calls.append((widget, state))
        return True


def _plot_payload(
    *,
    node_id: str = "node-plot",
    suppressed: bool = False,
    backend: str = "auto",
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
            "backend": backend,
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
    fullscreen_bridge: _FakeContentFullscreenBridge | None = None,
    binder: _FakePlotBinder,
    preview_cache_provider: PlotPreviewCacheImageProvider | None = None,
) -> PlotHostService:
    resolved_fullscreen_bridge = fullscreen_bridge or _FakeContentFullscreenBridge()
    service = PlotHostService(
        active_workspace_id_provider=lambda: scene.workspace_id,
        scene_bridge=scene,
        content_fullscreen_bridge=resolved_fullscreen_bridge,  # type: ignore[arg-type]
        overlay_manager=overlay_manager,  # type: ignore[arg-type]
        preview_cache_provider=preview_cache_provider,
    )
    service.register_binder("pyqtgraph", binder)
    return service


def _preview_image(color: str = "#2f81f7") -> QImage:
    image = QImage(13, 7, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    return image


def test_content_fullscreen_signal_connects_once_and_disconnects_on_shutdown() -> None:
    bridge = _FakeContentFullscreenBridge()
    service = PlotHostService(
        active_workspace_id_provider=lambda: "",
        scene_bridge=None,
        content_fullscreen_bridge=bridge,  # type: ignore[arg-type]
    )
    assert bridge.receivers(bridge.content_fullscreen_changed) == 1
    service.shutdown()
    assert bridge.receivers(bridge.content_fullscreen_changed) == 0


def test_active_workspace_provider_is_lazy_and_cleared_on_shutdown() -> None:
    calls: list[str] = []
    service = PlotHostService(
        active_workspace_id_provider=lambda: calls.append("active") or "ws-provider",
        scene_bridge=None,
        content_fullscreen_bridge=_FakeContentFullscreenBridge(),  # type: ignore[arg-type]
    )
    assert service._active_workspace_id() == "ws-provider"  # noqa: SLF001
    assert service._active_workspace_id() == "ws-provider"  # noqa: SLF001
    assert calls == ["active", "active"]
    service.shutdown()
    assert service._active_workspace_id() == ""  # noqa: SLF001
    assert calls == ["active", "active"]


def test_binders_are_lazy_reused_and_custom_registration_survives_first_initialization(qapp) -> None:  # noqa: ANN001
    with (
        patch.object(plot_host_module, "MatplotlibPlotWidgetBinder") as matplotlib_binder,
        patch.object(plot_host_module, "PyQtGraphPlotWidgetBinder") as pyqtgraph_binder,
        patch.object(plot_host_module, "PyVistaPlotWidgetBinder") as pyvista_binder,
    ):
        unopened = PlotHostService(
            active_workspace_id_provider=lambda: "",
            scene_bridge=None,
            content_fullscreen_bridge=_FakeContentFullscreenBridge(),  # type: ignore[arg-type]
        )
        unopened.shutdown()
        assert unopened.binder_registry is unopened._binder_registry  # noqa: SLF001
        matplotlib_binder.assert_not_called()
        pyqtgraph_binder.assert_not_called()
        pyvista_binder.assert_not_called()

        service = PlotHostService(
            active_workspace_id_provider=lambda: "",
            scene_bridge=None,
            content_fullscreen_bridge=_FakeContentFullscreenBridge(),  # type: ignore[arg-type]
        )
        custom_binder = _FakePlotBinder()
        service.register_binder("tests.lazy.custom", custom_binder)
        matplotlib_binder.assert_not_called()
        pyqtgraph_binder.assert_not_called()
        pyvista_binder.assert_not_called()

        registry = service.binder_registry
        assert registry.lookup("tests.lazy.custom") is custom_binder
        assert service.binder_registry is registry
        matplotlib_binder.assert_called_once_with()
        pyqtgraph_binder.assert_called_once_with()
        pyvista_binder.assert_called_once_with()
        service.shutdown()


def test_embedded_live_plot_binds_only_while_interaction_is_active(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    scene.nodes_model = [_plot_payload(suppressed=False)]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    service = _service(scene=scene, overlay_manager=overlay_manager, binder=binder)

    service.sync()

    assert service.active_overlay_count == 0
    assert binder.bind_calls == []

    service.set_embedded_interaction_active("node-plot", True)
    assert service.embedded_live_overlay_ready("node-plot") is False
    service.sync()

    assert service.active_overlay_count == 1
    assert len(binder.bind_calls) == 1
    assert binder.bind_calls[0].render_request.plot_type == "line"
    assert ("ws-plot", "node-plot") in overlay_manager.widgets
    assert PLOT_HOST_OVERLAY_OWNER in overlay_manager.active_specs_by_owner
    assert overlay_manager.sync_calls >= 1
    assert service.embedded_live_overlay_ready("node-plot") is True
    assert binder.refresh_after_attach_calls == [overlay_manager.widgets[("ws-plot", "node-plot")]]

    service.set_embedded_interaction_active("node-plot", False)
    assert service.embedded_live_overlay_ready("node-plot") is False
    service.sync()

    assert service.active_overlay_count == 0
    assert len(binder.release_calls) == 1
    assert ("ws-plot", "node-plot") not in overlay_manager.widgets


def test_explicit_matplotlib_backend_binds_matplotlib_live_binder(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    scene.nodes_model = [_plot_payload(suppressed=False, backend="matplotlib")]
    overlay_manager = _FakeOverlayManager()
    pyqtgraph_binder = _FakePlotBinder()
    matplotlib_binder = _FakePlotBinder()
    service = _service(scene=scene, overlay_manager=overlay_manager, binder=pyqtgraph_binder)
    service.register_binder("matplotlib", matplotlib_binder)

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()

    assert pyqtgraph_binder.bind_calls == []
    assert len(matplotlib_binder.bind_calls) == 1
    assert matplotlib_binder.bind_calls[0].backend_id == "matplotlib"
    assert matplotlib_binder.bind_calls[0].render_request.plot_type == "line"


def test_embedded_live_exit_releases_overlay_before_queued_sync(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    scene.nodes_model = [_plot_payload(suppressed=False)]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    service = _service(scene=scene, overlay_manager=overlay_manager, binder=binder)

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()
    live_widget = overlay_manager.widgets[("ws-plot", "node-plot")]

    service.set_embedded_interaction_active("node-plot", False)

    assert service.active_overlay_count == 0
    assert overlay_manager.widgets == {}
    assert binder.release_calls[-1].widget is live_widget


def test_plot_overlay_revision_changes_even_when_overlay_count_returns_to_same_value(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    first_payload = _plot_payload(node_id="plot-a", suppressed=False)
    second_payload = _plot_payload(node_id="plot-b", suppressed=False)
    scene.nodes_model = [first_payload, second_payload]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    service = _service(scene=scene, overlay_manager=overlay_manager, binder=binder)

    service.set_embedded_interaction_active("plot-a", True)
    service.sync()
    first_revision = service.plot_overlay_revision
    assert service.active_overlay_count == 1
    assert service.embedded_live_overlay_ready("plot-a") is True

    service.set_embedded_interaction_active("plot-a", False)
    service.set_embedded_interaction_active("plot-b", True)
    service.sync()

    assert service.active_overlay_count == 1
    assert service.plot_overlay_revision > first_revision
    assert service.embedded_live_overlay_ready("plot-b") is True
    assert service.embedded_live_overlay_ready("plot-a") is False


def test_embedded_live_exit_captures_in_memory_raster_preview_cache(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    scene.nodes_model = [_plot_payload(suppressed=False)]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    provider = PlotPreviewCacheImageProvider()
    service = _service(
        scene=scene,
        overlay_manager=overlay_manager,
        binder=binder,
        preview_cache_provider=provider,
    )

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()
    live_widget = overlay_manager.widgets[("ws-plot", "node-plot")]
    live_widget.resize(13, 7)
    overlay_manager.containers[("ws-plot", "node-plot")].resize(13, 7)
    binder.captured_preview_image = _preview_image("#64d26f")

    service.set_embedded_interaction_active("node-plot", False)

    source = service.cached_preview_source("node-plot")
    assert binder.capture_preview_calls == [live_widget]
    assert source.startswith("image://plot-preview-cache/")
    assert service.preview_cache_revision == 1
    cached, cached_size = provider.requestImage(source.split("image://plot-preview-cache/", 1)[1], QSize())
    assert cached_size == QSize(13, 7)
    assert cached.pixelColor(0, 0) == QColor("#64d26f")

    # The overlay release now waits for the swapped preview frame; confirm
    # the handoff so the queued sync observes the demoted state.
    service.notify_cached_preview_swapped("node-plot", source)
    for _ in range(3):
        qapp.processEvents()
    service.sync()
    assert service.active_overlay_count == 0


def test_cached_preview_normalizes_to_overlay_container_size(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    scene.nodes_model = [_plot_payload(suppressed=False)]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    provider = PlotPreviewCacheImageProvider()
    service = _service(
        scene=scene,
        overlay_manager=overlay_manager,
        binder=binder,
        preview_cache_provider=provider,
    )

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()
    overlay_manager.containers[("ws-plot", "node-plot")].resize(26, 14)
    binder.captured_preview_image = _preview_image("#64d26f")

    service.set_embedded_interaction_active("node-plot", False)

    source = service.cached_preview_source("node-plot")
    cached, cached_size = provider.requestImage(source.split("image://plot-preview-cache/", 1)[1], QSize())
    assert cached_size == QSize(26, 14)
    assert cached.pixelColor(0, 0) == QColor("#64d26f")


def _live_plot_service_with_captured_preview() -> tuple[PlotHostService, _FakeOverlayManager, _FakePlotBinder]:
    scene = _FakeSceneBridge()
    scene.nodes_model = [_plot_payload(suppressed=False)]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    service = _service(
        scene=scene,
        overlay_manager=overlay_manager,
        binder=binder,
        preview_cache_provider=PlotPreviewCacheImageProvider(),
    )
    service.set_embedded_interaction_active("node-plot", True)
    service.sync()
    binder.captured_preview_image = _preview_image("#64d26f")
    return service, overlay_manager, binder


def test_embedded_live_exit_defers_demotion_until_preview_swap_renders(qapp) -> None:  # noqa: ANN001
    service, overlay_manager, binder = _live_plot_service_with_captured_preview()
    key = ("ws-plot", "node-plot")

    service.set_embedded_interaction_active("node-plot", False)

    # The overlay release (and with it the native hide) waits for the
    # swapped proxy frame instead of racing the reveal.
    handoff = service._native_presentation_handoff  # noqa: SLF001
    assert handoff.contains(key)
    assert binder.release_calls == []
    assert overlay_manager.overlay_widget("node-plot", workspace_id="ws-plot") is not None
    service.sync()
    assert service.active_overlay_count == 1

    source = service.cached_preview_source("node-plot")
    assert source.startswith("image://plot-preview-cache/")
    service.notify_cached_preview_swapped("node-plot", source)
    if handoff.contains(key):
        assert handoff.is_armed(key)
        # The fake overlay manager exposes no QQuickWindow, so the armed
        # completion runs through the queued-pass fallback.
        for _ in range(3):
            qapp.processEvents()

    assert not handoff.contains(key)
    assert len(binder.release_calls) == 1
    assert overlay_manager.overlay_widget("node-plot", workspace_id="ws-plot") is None
    assert handoff.render_gate_connected is False
    service.sync()
    assert service.active_overlay_count == 0


def test_embedded_live_reactivation_restores_cached_view_state(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    scene.nodes_model = [_plot_payload(suppressed=False)]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    service = _service(scene=scene, overlay_manager=overlay_manager, binder=binder)

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()
    first_widget = overlay_manager.widgets[("ws-plot", "node-plot")]
    binder.captured_view_state = {"viewRange": [[2.0, 5.0], [10.0, 20.0]]}

    service.set_embedded_interaction_active("node-plot", False)
    service.sync()

    assert binder.capture_view_state_calls == [first_widget]
    assert binder.restore_view_state_calls == []

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()
    second_widget = overlay_manager.widgets[("ws-plot", "node-plot")]

    assert len(binder.bind_calls) == 2
    assert binder.restore_view_state_calls == [
        (second_widget, {"viewRange": [[2.0, 5.0], [10.0, 20.0]]})
    ]


def test_detached_window_close_preserves_view_state_for_inline_reactivation(qapp) -> None:  # noqa: ANN001
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
    detached_window = service._detached_windows[("ws-plot", "node-plot")]  # noqa: SLF001
    detached_widget = detached_window.widget

    assert detached_widget is embedded_widget
    assert binder.capture_view_state_calls == []
    binder.captured_view_state = {"viewRange": [[7.0, 11.0], [13.0, 17.0]]}

    detached_window.close()
    service.sync()

    assert binder.capture_view_state_calls == [detached_widget]
    assert service.detached_window_count == 0
    assert service.active_overlay_count == 1
    rebound_widget = overlay_manager.widgets[("ws-plot", "node-plot")]

    assert binder.restore_view_state_calls == [
        (rebound_widget, {"viewRange": [[7.0, 11.0], [13.0, 17.0]]})
    ]


def test_preview_cache_invalidates_when_plot_render_revision_changes(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    scene.nodes_model = [_plot_payload(suppressed=False)]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    provider = PlotPreviewCacheImageProvider()
    service = _service(
        scene=scene,
        overlay_manager=overlay_manager,
        binder=binder,
        preview_cache_provider=provider,
    )

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()
    binder.captured_preview_image = _preview_image("#64d26f")
    service.set_embedded_interaction_active("node-plot", False)
    service.sync()

    assert provider.has_preview("ws-plot", "node-plot")
    assert service.cached_preview_source("node-plot")

    changed_payload = dict(scene.nodes_model[0])
    changed_payload["plot_render_revision"] = 2
    scene.nodes_model = [changed_payload]
    service.sync()

    assert not provider.has_preview("ws-plot", "node-plot")
    assert service.cached_preview_source("node-plot") == ""


def test_cached_view_state_invalidates_when_plot_render_revision_changes(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    scene.nodes_model = [_plot_payload(suppressed=False)]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    service = _service(scene=scene, overlay_manager=overlay_manager, binder=binder)

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()
    binder.captured_view_state = {"camera": "original"}
    service.set_embedded_interaction_active("node-plot", False)
    service.sync()

    changed_payload = dict(scene.nodes_model[0])
    changed_payload["plot_render_revision"] = 2
    scene.nodes_model = [changed_payload]
    service.sync()
    service.set_embedded_interaction_active("node-plot", True)
    service.sync()

    assert binder.restore_view_state_calls == []


def test_live_plot_rebinds_when_payload_title_fallback_changes(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    payload = _plot_payload(suppressed=False)
    payload["title"] = "First Title"
    payload["properties"] = {**payload["properties"], "title": ""}
    scene.nodes_model = [payload]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    service = _service(scene=scene, overlay_manager=overlay_manager, binder=binder)

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()

    assert len(binder.bind_calls) == 1
    assert binder.bind_calls[-1].render_request.title == "First Title"

    changed_payload = dict(payload)
    changed_payload["title"] = "Second Title"
    scene.nodes_model = [changed_payload]
    service.sync()

    assert len(binder.bind_calls) == 2
    assert binder.bind_calls[-1].render_request.title == "Second Title"


def test_live_plot_rebinds_when_investigation_option_changes_with_same_revision(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    payload = _plot_payload(suppressed=False)
    payload["plot_surface"] = {**payload["plot_surface"], "render_revision": 7}
    scene.nodes_model = [payload]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    service = _service(scene=scene, overlay_manager=overlay_manager, binder=binder)

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()

    assert len(binder.bind_calls) == 1

    changed_payload = copy.deepcopy(payload)
    changed_payload["properties"]["plot_options"] = {"crosshair": True}
    scene.nodes_model = [changed_payload]
    service.sync()

    assert len(binder.bind_calls) == 2
    assert binder.bind_calls[-1].render_request.options["crosshair"] is True


def test_sink_mode_suppresses_embedded_without_blocking_fullscreen(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    payload = _plot_payload(suppressed=True)
    scene.nodes_model = [payload]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    fullscreen_bridge = _FakeContentFullscreenBridge()
    fullscreen_bridge.open_plot(payload)
    service = _service(
        scene=scene,
        overlay_manager=overlay_manager,
        fullscreen_bridge=fullscreen_bridge,
        binder=binder,
    )

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()

    assert service.active_overlay_count == 1
    assert len(binder.bind_calls) == 1
    assert overlay_manager.content_fullscreen_target is not None
    assert overlay_manager.content_fullscreen_target.node_id == "node-plot"
    assert binder.bind_calls[0].plot_surface["embedded_rendering_suppressed"] is True


def test_fullscreen_retargets_existing_embedded_plot_without_duplicate_widget(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    payload = _plot_payload(suppressed=False)
    scene.nodes_model = [payload]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    fullscreen_bridge = _FakeContentFullscreenBridge()
    service = _service(
        scene=scene,
        overlay_manager=overlay_manager,
        fullscreen_bridge=fullscreen_bridge,
        binder=binder,
    )

    service.set_embedded_interaction_active("node-plot", True)
    service.sync()
    widget = overlay_manager.widgets[("ws-plot", "node-plot")]

    fullscreen_bridge.open_plot(payload)
    service.sync()

    assert service.active_overlay_count == 1
    assert len(binder.bind_calls) == 1
    assert overlay_manager.widgets[("ws-plot", "node-plot")] is widget
    assert overlay_manager.content_fullscreen_target is not None
    assert overlay_manager.content_fullscreen_target.node_id == "node-plot"


def test_fullscreen_targets_plot_even_when_native_overlay_policy_is_missing(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    payload = _plot_payload(suppressed=False)
    surface_spec = dict(payload["surface_spec"])
    surface_spec.pop("native_overlay", None)
    payload["surface_spec"] = surface_spec
    scene.nodes_model = [payload]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    fullscreen_bridge = _FakeContentFullscreenBridge()
    service = _service(
        scene=scene,
        overlay_manager=overlay_manager,
        fullscreen_bridge=fullscreen_bridge,
        binder=binder,
    )

    fullscreen_bridge.open_plot(payload)
    service.sync()

    assert service.active_overlay_count == 1
    assert overlay_manager.content_fullscreen_target is not None
    assert overlay_manager.content_fullscreen_target.node_id == "node-plot"
    assert [spec.node_id for spec in overlay_manager.active_specs_by_owner[PLOT_HOST_OVERLAY_OWNER]] == ["node-plot"]
    assert ("ws-plot", "node-plot") in overlay_manager.widgets


def test_fullscreen_open_suppresses_previous_embedded_plot_before_queued_sync(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    first_payload = _plot_payload(node_id="plot-a", suppressed=False)
    second_payload = _plot_payload(node_id="plot-b", suppressed=False)
    scene.nodes_model = [first_payload, second_payload]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    fullscreen_bridge = _FakeContentFullscreenBridge()
    service = _service(
        scene=scene,
        overlay_manager=overlay_manager,
        fullscreen_bridge=fullscreen_bridge,
        binder=binder,
    )

    service.set_embedded_interaction_active("plot-a", True)
    service.sync()
    embedded_widget = overlay_manager.widgets[("ws-plot", "plot-a")]

    fullscreen_bridge.open_plot(second_payload)

    assert service.active_overlay_count == 0
    assert ("ws-plot", "plot-a") not in overlay_manager.widgets
    assert binder.release_calls[-1].widget is embedded_widget
    assert overlay_manager.content_fullscreen_target is not None
    assert overlay_manager.content_fullscreen_target.node_id == "plot-b"
    assert [spec.node_id for spec in overlay_manager.active_specs_by_owner[PLOT_HOST_OVERLAY_OWNER]] == ["plot-b"]

    service.sync()

    assert service.active_overlay_count == 1
    assert ("ws-plot", "plot-a") not in overlay_manager.widgets
    assert ("ws-plot", "plot-b") in overlay_manager.widgets


def test_fullscreen_switch_retargets_next_plot_before_queued_sync(qapp) -> None:  # noqa: ANN001
    scene = _FakeSceneBridge()
    first_payload = _plot_payload(node_id="plot-a", suppressed=False)
    second_payload = _plot_payload(node_id="plot-b", suppressed=False)
    scene.nodes_model = [first_payload, second_payload]
    overlay_manager = _FakeOverlayManager()
    binder = _FakePlotBinder()
    fullscreen_bridge = _FakeContentFullscreenBridge()
    service = _service(
        scene=scene,
        overlay_manager=overlay_manager,
        fullscreen_bridge=fullscreen_bridge,
        binder=binder,
    )

    fullscreen_bridge.open_plot(first_payload)
    service.sync()
    assert overlay_manager.content_fullscreen_target is not None
    assert overlay_manager.content_fullscreen_target.node_id == "plot-a"
    first_revision = service.plot_overlay_revision

    fullscreen_bridge.open_plot(second_payload)

    assert overlay_manager.content_fullscreen_target is not None
    assert overlay_manager.content_fullscreen_target.node_id == "plot-b"
    assert service.active_overlay_count == 0
    assert service.plot_overlay_revision > first_revision

    service.sync()

    assert overlay_manager.content_fullscreen_target is not None
    assert overlay_manager.content_fullscreen_target.node_id == "plot-b"
