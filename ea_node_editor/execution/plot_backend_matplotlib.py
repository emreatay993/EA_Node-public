from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ea_node_editor.execution.plot_backend import (
    PLOT_SURFACE_DATA_EXPORT,
    PLOT_SURFACE_LIVE,
    PLOT_SURFACE_STATIC_EXPORT,
    PLOT_TYPE_BAR,
    PLOT_TYPE_CONTOUR,
    PLOT_TYPE_HEATMAP,
    PLOT_TYPE_HISTOGRAM,
    PLOT_TYPE_LINE,
    PLOT_TYPE_SCATTER,
    PlotBackendRecord,
    PlotCapability,
    PlotDataExportRequest,
    PlotExportResult,
    PlotRenderRequest,
    PlotStaticExportRequest,
)

MATPLOTLIB_PLOT_BACKEND_ID = "matplotlib"
MATPLOTLIB_PLOT_BACKEND_DISPLAY_NAME = "Matplotlib Agg"
MATPLOTLIB_STATIC_EXPORT_FORMATS = ("png", "svg", "pdf")
MATPLOTLIB_DATA_EXPORT_FORMATS = ("csv",)
MATPLOTLIB_2D_PLOT_TYPES = (
    PLOT_TYPE_LINE,
    PLOT_TYPE_SCATTER,
    PLOT_TYPE_BAR,
    PLOT_TYPE_HISTOGRAM,
    PLOT_TYPE_HEATMAP,
    PLOT_TYPE_CONTOUR,
)


def _pyplot():
    import matplotlib

    matplotlib.use("Agg", force=True)
    from matplotlib import pyplot

    return pyplot


def _qt_canvas_classes() -> tuple[Any, Any]:
    try:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib Qt live rendering requires matplotlib's QtAgg backend. "
            "Install the viewer optional dependencies to enable embedded matplotlib plots."
        ) from exc
    return Figure, FigureCanvasQTAgg


class _FigureColorbar:
    @staticmethod
    def colorbar(mappable: Any, *, ax: Any) -> Any:
        return ax.figure.colorbar(mappable, ax=ax)


def _first_present(series: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in series and series[key] is not None:
            return series[key]
    return None


def _as_sequence(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _series_label(series: Mapping[str, Any], index: int) -> str:
    label = str(_first_present(series, "label", "name") or "").strip()
    if label:
        return label
    return f"series_{index + 1}" if index > 0 else ""


def _xy_values(series: Mapping[str, Any]) -> tuple[list[Any], list[Any]]:
    raw_y = _first_present(series, "y", "values", "data")
    y_values = _as_sequence(raw_y)
    if y_values is None:
        raise ValueError("line, scatter, and bar plots require series 'y' or 'values'")
    x_values = _as_sequence(_first_present(series, "x"))
    if x_values is None:
        x_values = list(range(len(y_values)))
    if len(x_values) != len(y_values):
        raise ValueError("plot series 'x' and 'y' values must have the same length")
    return x_values, y_values


def _histogram_values(series: Mapping[str, Any]) -> list[Any]:
    values = _as_sequence(_first_present(series, "values", "y", "x", "data"))
    if values is None:
        raise ValueError("histogram plots require series 'values'")
    return values


def _grid_values(series: Mapping[str, Any]) -> Any:
    values = _first_present(series, "values", "z", "data")
    if values is None:
        raise ValueError("heatmap and contour plots require series 'values' or 'z'")
    return values


def _grid_rows(values: Any) -> list[list[Any]]:
    rows = _as_sequence(values)
    if rows is None:
        return []
    normalized: list[list[Any]] = []
    for row in rows:
        if isinstance(row, (str, bytes, bytearray)):
            normalized.append([row])
            continue
        try:
            normalized.append(list(row))
        except TypeError:
            normalized.append([row])
    return normalized


def _resolve_format(
    output_path: Path,
    requested_format: str,
    *,
    supported_formats: tuple[str, ...],
) -> str:
    resolved = requested_format or output_path.suffix.lower().lstrip(".")
    if not resolved:
        raise ValueError("plot export format is required when output path has no suffix")
    if resolved not in supported_formats:
        supported = ", ".join(supported_formats)
        raise ValueError(f"Unsupported plot export format {resolved!r}; supported formats: {supported}")
    return resolved


def _prepare_output_path(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def _apply_axes_metadata(axis: Any, render_request: PlotRenderRequest) -> None:
    if render_request.title:
        axis.set_title(render_request.title)
    if render_request.x_label:
        axis.set_xlabel(render_request.x_label)
    if render_request.y_label:
        axis.set_ylabel(render_request.y_label)


def _legend_needed(render_request: PlotRenderRequest) -> bool:
    return any(str(_first_present(series, "label", "name") or "").strip() for series in render_request.series)


class MatplotlibPlotBackend:
    backend_id = MATPLOTLIB_PLOT_BACKEND_ID

    def create_widget(self, parent: Any = None) -> Any:
        return MatplotlibLive2DPlotBackend().create_widget(parent)

    def render_widget(self, widget: Any, request: PlotRenderRequest) -> None:
        MatplotlibLive2DPlotBackend().render_widget(widget, request)

    def clear_widget(self, widget: Any) -> None:
        MatplotlibLive2DPlotBackend().clear_widget(widget)

    def export_static(self, request: PlotStaticExportRequest) -> PlotExportResult:
        render_request = request.render_request
        if render_request.plot_type not in MATPLOTLIB_2D_PLOT_TYPES:
            raise ValueError(f"Matplotlib static export does not support {render_request.plot_type!r}.")
        if not render_request.series:
            raise ValueError("plot export requires at least one data series")

        output_path = _prepare_output_path(Path(request.output_path))
        export_format = _resolve_format(
            output_path,
            request.format,
            supported_formats=MATPLOTLIB_STATIC_EXPORT_FORMATS,
        )
        pyplot = _pyplot()
        figure, axis = pyplot.subplots(
            figsize=(request.width_inches, request.height_inches),
            dpi=request.dpi,
        )
        try:
            self._draw(axis, render_request, pyplot=pyplot)
            _apply_axes_metadata(axis, render_request)
            if _legend_needed(render_request):
                axis.legend()
            figure.tight_layout()
            figure.savefig(
                output_path,
                format=export_format,
                dpi=request.dpi,
                transparent=request.transparent,
            )
        finally:
            pyplot.close(figure)

        return PlotExportResult(
            backend_id=self.backend_id,
            output_path=output_path,
            format=export_format,
            metadata={
                "plot_type": render_request.plot_type,
                "series_count": len(render_request.series),
                "headless_safe": True,
            },
        )

    def export_data(self, request: PlotDataExportRequest) -> PlotExportResult:
        render_request = request.render_request
        if render_request.plot_type not in MATPLOTLIB_2D_PLOT_TYPES:
            raise ValueError(f"Matplotlib data export does not support {render_request.plot_type!r}.")
        if not render_request.series:
            raise ValueError("plot data export requires at least one data series")

        output_path = _prepare_output_path(Path(request.output_path))
        export_format = _resolve_format(
            output_path,
            request.format,
            supported_formats=MATPLOTLIB_DATA_EXPORT_FORMATS,
        )
        rows = self._data_rows(render_request)
        with output_path.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(
                output_file,
                fieldnames=("series", "index", "x", "y", "value", "row", "column"),
            )
            writer.writeheader()
            writer.writerows(rows)

        return PlotExportResult(
            backend_id=self.backend_id,
            output_path=output_path,
            format=export_format,
            metadata={
                "plot_type": render_request.plot_type,
                "row_count": len(rows),
                "headless_safe": True,
            },
        )

    def _draw(self, axis: Any, render_request: PlotRenderRequest, *, pyplot: Any) -> None:
        plot_type = render_request.plot_type
        if plot_type == PLOT_TYPE_LINE:
            for index, series in enumerate(render_request.series):
                x_values, y_values = _xy_values(series)
                axis.plot(x_values, y_values, label=_series_label(series, index))
            return
        if plot_type == PLOT_TYPE_SCATTER:
            for index, series in enumerate(render_request.series):
                x_values, y_values = _xy_values(series)
                axis.scatter(x_values, y_values, label=_series_label(series, index))
            return
        if plot_type == PLOT_TYPE_BAR:
            for index, series in enumerate(render_request.series):
                x_values, y_values = _xy_values(series)
                axis.bar(x_values, y_values, label=_series_label(series, index))
            return
        if plot_type == PLOT_TYPE_HISTOGRAM:
            bins = int(render_request.options.get("bins", 10))
            for index, series in enumerate(render_request.series):
                axis.hist(
                    _histogram_values(series),
                    bins=int(series.get("bins", bins)),
                    label=_series_label(series, index),
                )
            return
        if plot_type == PLOT_TYPE_HEATMAP:
            image = axis.imshow(
                _grid_values(render_request.series[0]),
                aspect=str(render_request.options.get("aspect", "auto")),
                cmap=str(render_request.options.get("cmap", "viridis")),
            )
            pyplot.colorbar(image, ax=axis)
            return
        if plot_type == PLOT_TYPE_CONTOUR:
            series = render_request.series[0]
            z_values = _grid_values(series)
            x_values = _first_present(series, "x")
            y_values = _first_present(series, "y")
            if x_values is not None and y_values is not None:
                contour = axis.contourf(
                    x_values,
                    y_values,
                    z_values,
                    cmap=str(render_request.options.get("cmap", "viridis")),
                )
            else:
                contour = axis.contourf(z_values, cmap=str(render_request.options.get("cmap", "viridis")))
            pyplot.colorbar(contour, ax=axis)
            return
        raise ValueError(f"Matplotlib static export does not support {plot_type!r}.")

    def _data_rows(self, render_request: PlotRenderRequest) -> list[dict[str, Any]]:
        if render_request.plot_type in {PLOT_TYPE_LINE, PLOT_TYPE_SCATTER, PLOT_TYPE_BAR}:
            return self._xy_data_rows(render_request)
        if render_request.plot_type == PLOT_TYPE_HISTOGRAM:
            return self._histogram_data_rows(render_request)
        if render_request.plot_type in {PLOT_TYPE_HEATMAP, PLOT_TYPE_CONTOUR}:
            return self._grid_data_rows(render_request)
        raise ValueError(f"Matplotlib data export does not support {render_request.plot_type!r}.")

    @staticmethod
    def _xy_data_rows(render_request: PlotRenderRequest) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for series_index, series in enumerate(render_request.series):
            x_values, y_values = _xy_values(series)
            series_name = _series_label(series, series_index) or f"series_{series_index + 1}"
            for index, (x_value, y_value) in enumerate(zip(x_values, y_values)):
                rows.append(
                    {
                        "series": series_name,
                        "index": index,
                        "x": x_value,
                        "y": y_value,
                        "value": y_value,
                        "row": "",
                        "column": "",
                    }
                )
        return rows

    @staticmethod
    def _histogram_data_rows(render_request: PlotRenderRequest) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for series_index, series in enumerate(render_request.series):
            series_name = _series_label(series, series_index) or f"series_{series_index + 1}"
            for index, value in enumerate(_histogram_values(series)):
                rows.append(
                    {
                        "series": series_name,
                        "index": index,
                        "x": "",
                        "y": "",
                        "value": value,
                        "row": "",
                        "column": "",
                    }
                )
        return rows

    @staticmethod
    def _grid_data_rows(render_request: PlotRenderRequest) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for series_index, series in enumerate(render_request.series):
            series_name = _series_label(series, series_index) or f"series_{series_index + 1}"
            x_values = _as_sequence(_first_present(series, "x")) or []
            y_values = _as_sequence(_first_present(series, "y")) or []
            for row_index, row in enumerate(_grid_rows(_grid_values(series))):
                for column_index, value in enumerate(row):
                    rows.append(
                        {
                            "series": series_name,
                            "index": len(rows),
                            "x": x_values[column_index] if column_index < len(x_values) else "",
                            "y": y_values[row_index] if row_index < len(y_values) else "",
                            "value": value,
                            "row": row_index,
                            "column": column_index,
                        }
                    )
        return rows


class MatplotlibLive2DPlotBackend:
    backend_id = MATPLOTLIB_PLOT_BACKEND_ID

    def create_widget(self, parent: Any = None) -> Any:
        Figure, FigureCanvasQTAgg = _qt_canvas_classes()
        figure = Figure(figsize=(6.4, 4.8), dpi=100)
        canvas = FigureCanvasQTAgg(figure)
        if parent is not None:
            canvas.setParent(parent)
        return canvas

    def render_widget(self, widget: Any, request: PlotRenderRequest) -> None:
        if request.plot_type not in MATPLOTLIB_2D_PLOT_TYPES:
            raise ValueError(f"Matplotlib live rendering does not support {request.plot_type!r}.")
        figure = self._figure(widget)
        figure.clear()
        axis = figure.add_subplot(111)
        if request.series:
            MatplotlibPlotBackend()._draw(axis, request, pyplot=_FigureColorbar())
        _apply_axes_metadata(axis, request)
        if _legend_needed(request):
            axis.legend()
        tight_layout = getattr(figure, "tight_layout", None)
        if callable(tight_layout):
            tight_layout()
        self._draw_idle(widget)

    def clear_widget(self, widget: Any) -> None:
        figure = self._figure(widget)
        figure.clear()
        self._draw_idle(widget)

    @staticmethod
    def _figure(widget: Any) -> Any:
        figure = getattr(widget, "figure", None)
        if figure is None:
            raise TypeError("matplotlib live widget must expose a figure.")
        return figure

    @staticmethod
    def _draw_idle(widget: Any) -> None:
        draw_idle = getattr(widget, "draw_idle", None)
        if callable(draw_idle):
            draw_idle()
            return
        draw = getattr(widget, "draw", None)
        if callable(draw):
            draw()


def create_matplotlib_plot_backend_record() -> PlotBackendRecord:
    capabilities = tuple(
        PlotCapability(plot_type=plot_type, surface=surface)
        for plot_type in MATPLOTLIB_2D_PLOT_TYPES
        for surface in (PLOT_SURFACE_LIVE, PLOT_SURFACE_STATIC_EXPORT, PLOT_SURFACE_DATA_EXPORT)
    )
    return PlotBackendRecord(
        backend_id=MATPLOTLIB_PLOT_BACKEND_ID,
        display_name=MATPLOTLIB_PLOT_BACKEND_DISPLAY_NAME,
        factory=MatplotlibPlotBackend,
        capabilities=capabilities,
        headless_safe_surfaces=(PLOT_SURFACE_STATIC_EXPORT, PLOT_SURFACE_DATA_EXPORT),
        metadata={
            "static_export_formats": MATPLOTLIB_STATIC_EXPORT_FORMATS,
            "data_export_formats": MATPLOTLIB_DATA_EXPORT_FORMATS,
            "live_renderer": True,
            "qt_required": True,
            "renderer": "Agg",
        },
    )


__all__ = [
    "MATPLOTLIB_2D_PLOT_TYPES",
    "MATPLOTLIB_DATA_EXPORT_FORMATS",
    "MATPLOTLIB_PLOT_BACKEND_DISPLAY_NAME",
    "MATPLOTLIB_PLOT_BACKEND_ID",
    "MATPLOTLIB_STATIC_EXPORT_FORMATS",
    "MatplotlibLive2DPlotBackend",
    "MatplotlibPlotBackend",
    "create_matplotlib_plot_backend_record",
]
