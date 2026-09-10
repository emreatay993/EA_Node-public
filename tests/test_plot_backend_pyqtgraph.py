from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette

from ea_node_editor.execution.plot_backend import PlotRenderRequest
from ea_node_editor.execution.plot_backend_pyqtgraph import PyQtGraphLive2DPlotBackend


pytest.importorskip("pyqtgraph")


def test_pyqtgraph_heatmap_accepts_json_safe_grid_series(qapp) -> None:  # noqa: ANN001
    backend = PyQtGraphLive2DPlotBackend()
    widget = backend.create_widget()

    backend.render_widget(
        widget,
        PlotRenderRequest(
            plot_type="heatmap",
            series=({"values": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]},),
            title="Heatmap",
        ),
    )

    plot_item = widget.getPlotItem()
    image_items = [item for item in plot_item.items if item.__class__.__name__ == "ImageItem"]

    assert len(image_items) == 1
    assert image_items[0].image.shape == (2, 3)
    assert widget.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
    assert widget.viewport().testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
    assert plot_item.getAxis("left").fixedWidth == 58
    assert plot_item.getAxis("bottom").fixedHeight == 32


def test_pyqtgraph_live_axis_layout_is_stable_for_title_and_x_axis(qapp) -> None:  # noqa: ANN001
    backend = PyQtGraphLive2DPlotBackend()
    widget = backend.create_widget()

    backend.render_widget(
        widget,
        PlotRenderRequest(
            plot_type="line",
            series=({"x": [0, 1, 2], "y": [1.0, 12.0, 300.0]},),
            title="Line Plot",
            x_label="time",
            y_label="efficiency",
        ),
    )

    plot_item = widget.getPlotItem()

    assert plot_item.getAxis("left").fixedWidth == 58
    assert plot_item.getAxis("bottom").fixedHeight == 32


def test_pyqtgraph_live_theme_and_investigation_overlay_items(qapp) -> None:  # noqa: ANN001
    backend = PyQtGraphLive2DPlotBackend()
    widget = backend.create_widget()

    backend.render_widget(
        widget,
        PlotRenderRequest(
            plot_type="line",
            series=({"label": "sample", "x": [0, 1, 2], "y": [1.0, 2.0, 4.0]},),
            title="Line Plot",
            options={
                "plot_theme": "light",
                "hover_readout": True,
                "vertical_guide": True,
                "crosshair": True,
            },
        ),
    )

    assert widget.palette().color(QPalette.ColorRole.Window).name().lower() == "#ffffff"
    state = getattr(widget, "_ea_plot_investigation_state")
    item_types = [item.__class__.__name__ for item in state["items"]]
    assert item_types.count("InfiniteLine") == 2
    assert item_types.count("TextItem") == 1
    assert len(state["points"]) == 3

    backend.render_widget(
        widget,
        PlotRenderRequest(
            plot_type="line",
            series=({"x": [0, 1], "y": [1.0, 2.0]},),
            title="Line Plot",
        ),
    )

    assert not hasattr(widget, "_ea_plot_investigation_state")


def test_pyqtgraph_heatmap_rejects_flat_grid(qapp) -> None:  # noqa: ANN001
    backend = PyQtGraphLive2DPlotBackend()
    widget = backend.create_widget()

    with pytest.raises(ValueError, match="2D values grid"):
        backend.render_widget(
            widget,
            PlotRenderRequest(
                plot_type="heatmap",
                series=({"values": [1.0, 2.0, 3.0]},),
                title="Heatmap",
            ),
        )
