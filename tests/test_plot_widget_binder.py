from __future__ import annotations

import numpy
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QWidget

from ea_node_editor.execution.plot_backend import PlotRenderRequest
from ea_node_editor.ui_qml.plot_widget_binder import (
    MatplotlibPlotWidgetBinder,
    PlotWidgetBindRequest,
    PlotWidgetReleaseRequest,
    PyQtGraphPlotWidgetBinder,
    PyVistaPlotWidgetBinder,
)


class _FakePlotWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.clear_count = 0
        self.view_box = _FakeViewBox()

    def clear(self) -> None:
        self.clear_count += 1

    def getPlotItem(self) -> "_FakePlotItem":  # noqa: N802
        return _FakePlotItem(self.view_box)


class _FakePlotItem:
    def __init__(self, view_box: "_FakeViewBox") -> None:
        self._view_box = view_box

    def getViewBox(self) -> "_FakeViewBox":  # noqa: N802
        return self._view_box


class _FakeViewBox:
    def __init__(self) -> None:
        self.state = {"viewRange": [[1.0, 4.0], [2.0, 8.0]], "locked": False}
        self.restored_state = None

    def getState(self, copy: bool = True):  # noqa: A002, ANN001, N802
        return dict(self.state) if copy else self.state

    def setState(self, state) -> None:  # noqa: ANN001, N802
        self.restored_state = state


class _FakePyQtGraphBackend:
    def __init__(self) -> None:
        self.render_calls: list[tuple[QWidget, PlotRenderRequest]] = []

    def render_widget(self, widget: QWidget, request: PlotRenderRequest) -> None:
        self.render_calls.append((widget, request))


class _FakeMatplotlibFigure:
    def __init__(self) -> None:
        self.clear_count = 0

    def clear(self) -> None:
        self.clear_count += 1


class _FakeMatplotlibWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.figure = _FakeMatplotlibFigure()
        self.draw_idle_count = 0

    def draw_idle(self) -> None:
        self.draw_idle_count += 1


class _FakeMatplotlibBackend:
    def __init__(self) -> None:
        self.render_calls: list[tuple[QWidget, PlotRenderRequest]] = []

    def render_widget(self, widget: QWidget, request: PlotRenderRequest) -> None:
        self.render_calls.append((widget, request))


class _FakePyVistaWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.clear_count = 0
        self.render_count = 0
        self.finalize_count = 0
        self.close_count = 0
        self.screenshot_data = None
        self.camera_position = ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        self.camera = _FakeCamera()

    def clear(self) -> None:
        self.clear_count += 1

    def render(self) -> None:
        self.render_count += 1

    def Finalize(self) -> None:  # noqa: N802
        self.finalize_count += 1

    def close(self) -> bool:
        self.close_count += 1
        return super().close()

    def screenshot(self, *, return_img: bool = False):  # noqa: ANN001
        assert return_img is True
        return self.screenshot_data


class _FakeCamera:
    def __init__(self) -> None:
        self.position = (1.0, 2.0, 3.0)
        self.focal_point = (0.0, 0.0, 0.0)
        self.view_up = (0.0, 1.0, 0.0)
        self.clipping_range = (0.1, 100.0)
        self.parallel_scale = 2.5
        self.parallel_projection = False


class _FakePyVistaBackend:
    def __init__(self) -> None:
        self.render_calls: list[tuple[QWidget, PlotRenderRequest]] = []

    def render_widget(self, widget: QWidget, request: PlotRenderRequest) -> None:
        self.render_calls.append((widget, request))


def _render_request() -> PlotRenderRequest:
    return PlotRenderRequest(
        plot_type="line",
        series=({"x": [0, 1, 2], "y": [1.0, 2.0, 4.0]},),
        title="Packet Plot",
        x_label="x",
        y_label="y",
        options={"grid": True},
    )


def _bind_request(
    *,
    container: QWidget,
    current_widget: QWidget | None = None,
    revision: int = 1,
) -> PlotWidgetBindRequest:
    return PlotWidgetBindRequest(
        workspace_id="ws-plot",
        node_id="node-plot",
        plot_type="line",
        backend_id="pyqtgraph",
        render_request=_render_request(),
        render_revision=revision,
        properties={"title": "Packet Plot"},
        plot_surface={"plot_type": "line"},
        container=container,
        current_widget=current_widget,
    )


def test_pyqtgraph_binder_binds_reuses_releases_and_captures(qapp) -> None:  # noqa: ANN001
    backend = _FakePyQtGraphBackend()
    created_widgets: list[_FakePlotWidget] = []
    binder = PyQtGraphPlotWidgetBinder(
        backend_factory=lambda: backend,  # type: ignore[arg-type]
        widget_factory=lambda parent: created_widgets.append(_FakePlotWidget(parent)) or created_widgets[-1],
    )
    container = QWidget()
    container.resize(120, 80)

    widget = binder.bind_widget(_bind_request(container=container))

    assert widget.parent() is container
    assert widget.property("ea.plotLiveOverlay") is True
    assert len(created_widgets) == 1
    assert backend.render_calls == [(widget, _render_request())]
    view_state = binder.capture_view_state(widget)
    assert view_state == {
        "kind": "pyqtgraph_viewbox",
        "state": {"viewRange": [[1.0, 4.0], [2.0, 8.0]], "locked": False},
    }

    reused = binder.bind_widget(
        _bind_request(
            container=container,
            current_widget=widget,
            revision=2,
        )
    )

    assert reused is widget
    assert len(created_widgets) == 1
    assert len(backend.render_calls) == 2

    binder.release_widget(
        PlotWidgetReleaseRequest(
            workspace_id="ws-plot",
            node_id="node-plot",
            plot_type="line",
            backend_id="pyqtgraph",
            widget=widget,
            container=container,
            reason="test",
        )
    )

    assert widget.clear_count == 1
    assert widget.property("ea.plotLiveOverlay") is False
    assert isinstance(binder.capture_preview_image(widget), QImage)
    assert binder.restore_view_state(widget, view_state) is True
    assert widget.view_box.restored_state == {"viewRange": [[1.0, 4.0], [2.0, 8.0]], "locked": False}


def test_pyqtgraph_binder_passes_live_investigation_options_to_backend(qapp) -> None:  # noqa: ANN001
    backend = _FakePyQtGraphBackend()
    binder = PyQtGraphPlotWidgetBinder(
        backend_factory=lambda: backend,  # type: ignore[arg-type]
        widget_factory=lambda parent: _FakePlotWidget(parent),
    )
    container = QWidget()

    widget = binder.bind_widget(
        PlotWidgetBindRequest(
            workspace_id="ws-plot",
            node_id="node-plot",
            plot_type="line",
            backend_id="pyqtgraph",
            render_request=PlotRenderRequest(
                plot_type="line",
                series=({"x": [0, 1], "y": [1.0, 2.0]},),
                options={"hover_readout": True, "vertical_guide": True, "crosshair": True, "plot_theme": "dark"},
            ),
            render_revision=1,
            container=container,
        )
    )

    assert backend.render_calls[-1][0] is widget
    assert backend.render_calls[-1][1].options["hover_readout"] is True
    assert backend.render_calls[-1][1].options["vertical_guide"] is True
    assert backend.render_calls[-1][1].options["crosshair"] is True
    assert backend.render_calls[-1][1].options["plot_theme"] == "dark"


def test_matplotlib_binder_binds_reuses_releases_and_captures(qapp) -> None:  # noqa: ANN001
    backend = _FakeMatplotlibBackend()
    created_widgets: list[_FakeMatplotlibWidget] = []
    binder = MatplotlibPlotWidgetBinder(
        backend_factory=lambda: backend,  # type: ignore[arg-type]
        widget_factory=lambda parent: created_widgets.append(_FakeMatplotlibWidget(parent)) or created_widgets[-1],
    )
    container = QWidget()
    container.resize(120, 80)

    widget = binder.bind_widget(_bind_request(container=container))

    assert widget.parent() is container
    assert widget.property("ea.plotLiveOverlay") is True
    assert len(created_widgets) == 1
    assert backend.render_calls == [(widget, _render_request())]

    reused = binder.bind_widget(
        _bind_request(
            container=container,
            current_widget=widget,
            revision=2,
        )
    )

    assert reused is widget
    assert len(created_widgets) == 1
    assert len(backend.render_calls) == 2

    binder.release_widget(
        PlotWidgetReleaseRequest(
            workspace_id="ws-plot",
            node_id="node-plot",
            plot_type="line",
            backend_id="matplotlib",
            widget=widget,
            container=container,
            reason="test",
        )
    )

    assert widget.figure.clear_count == 1
    assert widget.draw_idle_count == 1
    assert widget.property("ea.plotLiveOverlay") is False
    assert isinstance(binder.capture_preview_image(widget), QImage)


def test_pyvista_release_does_not_touch_hidden_interactor_context(qapp) -> None:  # noqa: ANN001
    backend = _FakePyVistaBackend()
    widget = _FakePyVistaWidget()
    binder = PyVistaPlotWidgetBinder(
        backend_factory=lambda: backend,  # type: ignore[arg-type]
        interactor_factory=lambda parent: widget,
    )
    container = QWidget()

    bound = binder.bind_widget(
        PlotWidgetBindRequest(
            workspace_id="ws-plot",
            node_id="node-plot",
            plot_type="surface",
            backend_id="pyvista",
            render_request=PlotRenderRequest(plot_type="surface", title="Surface"),
            container=container,
        )
    )
    assert bound is widget
    view_state = binder.capture_view_state(widget)
    assert view_state == {
        "kind": "pyvista_camera",
        "state": {
            "camera_position": ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            "camera": {
                "position": (1.0, 2.0, 3.0),
                "focal_point": (0.0, 0.0, 0.0),
                "view_up": (0.0, 1.0, 0.0),
                "clipping_range": (0.1, 100.0),
                "parallel_scale": 2.5,
                "parallel_projection": False,
            },
        },
    }
    widget.camera_position = ((9.0, 8.0, 7.0), (1.0, 1.0, 1.0), (0.0, 0.0, 1.0))
    widget.camera.position = (9.0, 8.0, 7.0)

    assert binder.restore_view_state(widget, view_state) is True

    assert widget.camera_position == ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    assert widget.camera.position == (1.0, 2.0, 3.0)
    assert widget.render_count == 1

    binder.release_widget(
        PlotWidgetReleaseRequest(
            workspace_id="ws-plot",
            node_id="node-plot",
            plot_type="surface",
            backend_id="pyvista",
            widget=widget,
            container=container,
            reason="session_closed",
        )
    )

    assert widget.clear_count == 0
    assert widget.render_count == 1
    assert widget.finalize_count == 1
    assert widget.close_count == 1
    assert widget.property("ea.plotLiveOverlay") is False


def test_pyvista_capture_preview_image_preserves_screenshot_orientation_and_colors(qapp) -> None:  # noqa: ANN001
    backend = _FakePyVistaBackend()
    widget = _FakePyVistaWidget()
    binder = PyVistaPlotWidgetBinder(
        backend_factory=lambda: backend,  # type: ignore[arg-type]
        interactor_factory=lambda parent: widget,
    )
    container = QWidget()
    binder.bind_widget(
        PlotWidgetBindRequest(
            workspace_id="ws-plot",
            node_id="node-plot",
            plot_type="surface",
            backend_id="pyvista",
            render_request=PlotRenderRequest(plot_type="surface", title="Surface"),
            container=container,
        )
    )
    rgba_buffer = numpy.array(
        [
            [[0, 0, 255, 11], [255, 255, 255, 12]],
            [[255, 0, 0, 13], [0, 255, 0, 14]],
        ],
        dtype=numpy.uint8,
    )
    widget.screenshot_data = rgba_buffer[::-1, :, :3]

    image = binder.capture_preview_image(widget)

    assert not image.isNull()
    assert image.width() == 2
    assert image.height() == 2
    assert image.pixelColor(0, 0) == QColor(255, 0, 0)
    assert image.pixelColor(1, 0) == QColor(0, 255, 0)
    assert image.pixelColor(0, 1) == QColor(0, 0, 255)
    assert image.pixelColor(1, 1) == QColor(255, 255, 255)


def test_pyvista_refresh_after_attach_renders_visible_overlay(qapp) -> None:  # noqa: ANN001
    backend = _FakePyVistaBackend()
    widget = _FakePyVistaWidget()
    binder = PyVistaPlotWidgetBinder(
        backend_factory=lambda: backend,  # type: ignore[arg-type]
        interactor_factory=lambda parent: widget,
    )
    container = QWidget()
    binder.bind_widget(
        PlotWidgetBindRequest(
            workspace_id="ws-plot",
            node_id="node-plot",
            plot_type="surface",
            backend_id="pyvista",
            render_request=PlotRenderRequest(plot_type="surface", title="Surface"),
            container=container,
        )
    )

    binder.refresh_after_attach(widget)

    assert widget.render_count == 1
