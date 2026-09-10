from __future__ import annotations

import pytest

from ea_node_editor.execution.plot_backend import PlotRenderRequest, PlotStaticExportRequest
from ea_node_editor.execution.plot_backend_matplotlib import MatplotlibLive2DPlotBackend, MatplotlibPlotBackend


pytest.importorskip("matplotlib.backends.backend_qtagg")


def test_matplotlib_live_backend_renders_line_plot_on_qt_canvas(qapp) -> None:  # noqa: ANN001
    backend = MatplotlibLive2DPlotBackend()
    widget = backend.create_widget()

    backend.render_widget(
        widget,
        PlotRenderRequest(
            plot_type="line",
            series=({"x": [0, 1, 2], "y": [1.0, 2.0, 4.0], "label": "speed"},),
            title="Line Plot",
            x_label="time",
            y_label="value",
        ),
    )

    assert len(widget.figure.axes) == 1
    axis = widget.figure.axes[0]
    assert axis.get_title() == "Line Plot"
    assert axis.get_xlabel() == "time"
    assert axis.get_ylabel() == "value"
    assert len(axis.lines) == 1


def test_matplotlib_live_backend_still_works_after_agg_static_export(qapp, tmp_path) -> None:  # noqa: ANN001
    request = PlotRenderRequest(
        plot_type="line",
        series=({"x": [0, 1], "y": [1.0, 2.0]},),
        title="Agg Then Qt",
    )
    output_path = tmp_path / "plot.png"

    MatplotlibPlotBackend().export_static(
        PlotStaticExportRequest(render_request=request, output_path=output_path, format="png")
    )
    widget = MatplotlibLive2DPlotBackend().create_widget()
    MatplotlibLive2DPlotBackend().render_widget(widget, request)

    assert output_path.exists()
    assert len(widget.figure.axes) == 1
    assert widget.figure.axes[0].get_title() == "Agg Then Qt"
