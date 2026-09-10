from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

from ea_node_editor.execution.plot_backend import (
    PLOT_SURFACE_LIVE,
    PLOT_TYPE_BAR,
    PLOT_TYPE_CONTOUR,
    PLOT_TYPE_HEATMAP,
    PLOT_TYPE_HISTOGRAM,
    PLOT_TYPE_LINE,
    PLOT_TYPE_SCATTER,
    PlotBackendRecord,
    PlotCapability,
    PlotRenderRequest,
)

PYQTGRAPH_PLOT_BACKEND_ID = "pyqtgraph"
PYQTGRAPH_PLOT_BACKEND_DISPLAY_NAME = "pyqtgraph Live 2D"
PYQTGRAPH_LIVE_2D_PLOT_TYPES = (
    PLOT_TYPE_LINE,
    PLOT_TYPE_SCATTER,
    PLOT_TYPE_BAR,
    PLOT_TYPE_HISTOGRAM,
    PLOT_TYPE_HEATMAP,
    PLOT_TYPE_CONTOUR,
)
_PLOT_WIDGET_BACKGROUND = "#05070a"
_LEFT_AXIS_WIDTH = 58
_BOTTOM_AXIS_HEIGHT = 32
_INVESTIGATION_STATE_ATTR = "_ea_plot_investigation_state"
_PLOT_THEMES = {
    "dark": {
        "background": "#05070a",
        "foreground": "#d8e4f0",
        "axis": "#9fb2c6",
        "grid": "#263140",
        "guide": "#58a6ff",
        "crosshair": "#f2cc60",
        "readout_background": "#111827",
    },
    "light": {
        "background": "#ffffff",
        "foreground": "#1f2937",
        "axis": "#475569",
        "grid": "#cbd5e1",
        "guide": "#2563eb",
        "crosshair": "#b45309",
        "readout_background": "#f8fafc",
    },
}
_PLOT_THEME_VALUES = frozenset({"system", "dark", "light"})


def _pyqtgraph():
    try:
        import pyqtgraph as pg
    except ImportError as exc:
        raise RuntimeError(
            "pyqtgraph is required for live 2D plot rendering. "
            "Install the viewer optional dependencies to enable embedded plot widgets."
        ) from exc
    return pg


def _numpy():
    try:
        import numpy
    except ImportError as exc:
        raise RuntimeError("numpy is required for pyqtgraph image plot rendering.") from exc
    return numpy


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
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        value = tolist()
    try:
        return list(value)
    except TypeError:
        return [value]


def _series_label(series: Mapping[str, Any], index: int) -> str:
    label = str(_first_present(series, "label", "name") or "").strip()
    return label or (f"series_{index + 1}" if index > 0 else "")


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


def _grid_array(series: Mapping[str, Any]) -> Any:
    numpy = _numpy()
    grid = numpy.asarray(_grid_values(series), dtype=float)
    if grid.ndim != 2:
        raise ValueError("heatmap and contour plots require a 2D values grid")
    if grid.shape[0] <= 0 or grid.shape[1] <= 0:
        raise ValueError("heatmap and contour plots require a non-empty values grid")
    return grid


def _numeric_values(values: Sequence[Any]) -> list[float]:
    normalized: list[float] = []
    for value in values:
        try:
            normalized.append(float(value))
        except (TypeError, ValueError):
            continue
    return normalized


def _bool_option(options: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = options.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _format_number(value: float) -> str:
    return f"{value:.5g}"


def _plot_theme_name(widget: Any, options: Mapping[str, Any]) -> str:
    theme = str(options.get("plot_theme") or "system").strip().casefold()
    if theme == "auto":
        theme = "system"
    if theme not in _PLOT_THEME_VALUES:
        theme = "system"
    if theme != "system":
        return theme

    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    palette = app.palette() if app is not None else widget.palette()
    window_color = palette.color(QPalette.ColorRole.Window)
    return "light" if window_color.lightness() >= 150 else "dark"


def _plot_theme(widget: Any, options: Mapping[str, Any]) -> dict[str, str]:
    return dict(_PLOT_THEMES[_plot_theme_name(widget, options)])


def _histogram_bins(values: Sequence[Any], bins: int) -> tuple[list[float], list[int], float]:
    numeric = _numeric_values(values)
    if not numeric:
        return [], [], 1.0
    bin_count = max(1, int(bins))
    minimum = min(numeric)
    maximum = max(numeric)
    if minimum == maximum:
        centers = [minimum]
        return centers, [len(numeric)], 1.0
    width = (maximum - minimum) / bin_count
    counts = [0 for _ in range(bin_count)]
    for value in numeric:
        index = min(bin_count - 1, max(0, int((value - minimum) / width)))
        counts[index] += 1
    centers = [minimum + (width * (index + 0.5)) for index in range(bin_count)]
    return centers, counts, width


def _readout_points(request: PlotRenderRequest) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    if request.plot_type in {PLOT_TYPE_LINE, PLOT_TYPE_SCATTER, PLOT_TYPE_BAR}:
        for series_index, series in enumerate(request.series):
            try:
                x_values, y_values = _xy_values(series)
            except ValueError:
                continue
            label = _series_label(series, series_index)
            for x_value, y_value in zip(x_values, y_values):
                x_number = _float_or_none(x_value)
                y_number = _float_or_none(y_value)
                if x_number is None or y_number is None:
                    continue
                points.append({"label": label, "x": x_number, "y": y_number, "kind": request.plot_type})
        return points
    if request.plot_type == PLOT_TYPE_HISTOGRAM:
        default_bins = int(request.options.get("bins", 10))
        for series_index, series in enumerate(request.series):
            centers, counts, width = _histogram_bins(
                _histogram_values(series),
                int(series.get("bins", default_bins)),
            )
            label = _series_label(series, series_index)
            for center, count in zip(centers, counts):
                points.append(
                    {
                        "label": label,
                        "x": center,
                        "y": float(count),
                        "kind": request.plot_type,
                        "count": int(count),
                        "range": (center - (width / 2.0), center + (width / 2.0)),
                    }
                )
    return points


def _nearest_readout_point(
    points: Sequence[Mapping[str, Any]],
    x_value: float,
    y_value: float,
    *,
    x_only: bool,
) -> Mapping[str, Any] | None:
    if not points:
        return None
    if x_only:
        return min(points, key=lambda point: abs(float(point.get("x", 0.0)) - x_value))
    return min(
        points,
        key=lambda point: (float(point.get("x", 0.0)) - x_value) ** 2
        + (float(point.get("y", 0.0)) - y_value) ** 2,
    )


def _readout_text(
    request: PlotRenderRequest,
    points: Sequence[Mapping[str, Any]],
    *,
    x_value: float,
    y_value: float,
    x_only: bool,
) -> str:
    nearest = _nearest_readout_point(points, x_value, y_value, x_only=x_only)
    if nearest is None:
        return f"x={_format_number(x_value)}, y={_format_number(y_value)}"
    label = str(nearest.get("label") or "").strip()
    prefix = f"{label}: " if label else ""
    if nearest.get("kind") == PLOT_TYPE_HISTOGRAM:
        low, high = nearest.get("range", (nearest.get("x", x_value), nearest.get("x", x_value)))
        return (
            f"{prefix}bin {_format_number(float(low))}..{_format_number(float(high))}, "
            f"count={int(nearest.get('count', nearest.get('y', 0)))}"
        )
    return f"{prefix}x={_format_number(float(nearest.get('x', x_value)))}, y={_format_number(float(nearest.get('y', y_value)))}"


class PyQtGraphLive2DPlotBackend:
    backend_id = PYQTGRAPH_PLOT_BACKEND_ID

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        pg = _pyqtgraph()
        widget = pg.PlotWidget(parent=parent)
        self._configure_widget_background(widget, _PLOT_THEMES["dark"])
        return widget

    def render_widget(self, widget: QWidget, request: PlotRenderRequest) -> None:
        if request.plot_type not in PYQTGRAPH_LIVE_2D_PLOT_TYPES:
            raise ValueError(f"pyqtgraph live rendering does not support {request.plot_type!r}.")
        theme = _plot_theme(widget, request.options)
        self._configure_widget_background(widget, theme)
        if not request.series:
            self._draw_empty(widget, request, theme)
            self._apply_investigation_overlay(widget, request, theme)
            return
        self._clear(widget)
        self._draw(widget, request)
        self._apply_axes_metadata(widget, request, theme)
        self._stabilize_axis_layout(widget)
        self._apply_investigation_overlay(widget, request, theme)

    def _draw_empty(self, widget: QWidget, request: PlotRenderRequest, theme: Mapping[str, str]) -> None:
        self._clear(widget)
        self._apply_axes_metadata(widget, request, theme)
        self._stabilize_axis_layout(widget)

    @staticmethod
    def _configure_widget_background(widget: QWidget, theme: Mapping[str, str]) -> None:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QPalette
        from PyQt6.QtWidgets import QWidget

        background_color = str(theme.get("background") or _PLOT_WIDGET_BACKGROUND)
        set_background = getattr(widget, "setBackground", None)
        if callable(set_background):
            set_background(background_color)
        widget.setAutoFillBackground(True)
        widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        palette = widget.palette()
        background = QColor(background_color)
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base):
            palette.setColor(role, background)
        widget.setPalette(palette)
        viewport_getter = getattr(widget, "viewport", None)
        viewport = viewport_getter() if callable(viewport_getter) else None
        if isinstance(viewport, QWidget):
            viewport.setAutoFillBackground(True)
            viewport.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            viewport.setPalette(palette)

    @staticmethod
    def _clear(widget: QWidget) -> None:
        PyQtGraphLive2DPlotBackend._clear_investigation_overlay(widget)
        clear = getattr(widget, "clear", None)
        if callable(clear):
            clear()

    @staticmethod
    def _apply_axes_metadata(widget: QWidget, request: PlotRenderRequest, theme: Mapping[str, str]) -> None:
        pg = _pyqtgraph()
        set_title = getattr(widget, "setTitle", None)
        if callable(set_title) and request.title:
            set_title(request.title, color=str(theme.get("foreground") or "#d8e4f0"))
        set_label = getattr(widget, "setLabel", None)
        if callable(set_label):
            if request.x_label:
                set_label("bottom", request.x_label, color=str(theme.get("foreground") or "#d8e4f0"))
            if request.y_label:
                set_label("left", request.y_label, color=str(theme.get("foreground") or "#d8e4f0"))
        show_grid = getattr(widget, "showGrid", None)
        if callable(show_grid):
            show_grid(x=bool(request.options.get("grid", True)), y=bool(request.options.get("grid", True)), alpha=0.25)
        plot_item = PyQtGraphLive2DPlotBackend._plot_item(widget)
        get_axis = getattr(plot_item, "getAxis", None) if plot_item is not None else None
        if not callable(get_axis):
            return
        axis_pen = pg.mkPen(str(theme.get("axis") or "#9fb2c6"))
        text_pen = pg.mkPen(str(theme.get("foreground") or "#d8e4f0"))
        for axis_name in ("left", "bottom"):
            try:
                axis = get_axis(axis_name)
            except Exception:  # noqa: BLE001
                continue
            set_pen = getattr(axis, "setPen", None)
            if callable(set_pen):
                set_pen(axis_pen)
            set_text_pen = getattr(axis, "setTextPen", None)
            if callable(set_text_pen):
                set_text_pen(text_pen)

    @staticmethod
    def _stabilize_axis_layout(widget: QWidget) -> None:
        plot_item = PyQtGraphLive2DPlotBackend._plot_item(widget)
        if plot_item is None:
            return
        get_axis = getattr(plot_item, "getAxis", None)
        if not callable(get_axis):
            return
        axes = (("left", "setWidth", _LEFT_AXIS_WIDTH), ("bottom", "setHeight", _BOTTOM_AXIS_HEIGHT))
        for axis_name, setter_name, value in axes:
            try:
                axis = get_axis(axis_name)
            except Exception:  # noqa: BLE001
                continue
            setter = getattr(axis, setter_name, None)
            if callable(setter):
                try:
                    setter(value)
                except Exception:  # noqa: BLE001
                    pass

    @staticmethod
    def _plot_item(widget: QWidget) -> Any | None:
        get_plot_item = getattr(widget, "getPlotItem", None)
        if not callable(get_plot_item):
            return None
        try:
            return get_plot_item()
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _clear_investigation_overlay(widget: QWidget) -> None:
        state = getattr(widget, _INVESTIGATION_STATE_ATTR, None)
        if not isinstance(state, Mapping):
            return
        signal = state.get("signal")
        callback = state.get("callback")
        if signal is not None and callback is not None:
            try:
                signal.disconnect(callback)
            except Exception:  # noqa: BLE001
                pass
        plot_item = PyQtGraphLive2DPlotBackend._plot_item(widget)
        remove_item = getattr(plot_item, "removeItem", None) if plot_item is not None else getattr(widget, "removeItem", None)
        if callable(remove_item):
            for item in state.get("items", ()):
                try:
                    remove_item(item)
                except Exception:  # noqa: BLE001
                    pass
        try:
            delattr(widget, _INVESTIGATION_STATE_ATTR)
        except AttributeError:
            pass

    @staticmethod
    def _apply_investigation_overlay(widget: QWidget, request: PlotRenderRequest, theme: Mapping[str, str]) -> None:
        hover_readout = _bool_option(request.options, "hover_readout")
        vertical_guide = _bool_option(request.options, "vertical_guide")
        crosshair = _bool_option(request.options, "crosshair")
        if not hover_readout and not vertical_guide and not crosshair:
            return
        pg = _pyqtgraph()
        plot_item = PyQtGraphLive2DPlotBackend._plot_item(widget)
        view_box_getter = getattr(plot_item, "getViewBox", None) if plot_item is not None else None
        view_box = view_box_getter() if callable(view_box_getter) else None
        add_item = getattr(widget, "addItem", None)
        if plot_item is None or view_box is None or not callable(add_item):
            return

        items: list[Any] = []
        vertical_line = None
        horizontal_line = None
        readout_item = None
        if vertical_guide or crosshair:
            vertical_line = pg.InfiniteLine(
                angle=90,
                movable=False,
                pen=pg.mkPen(str(theme.get("guide") or "#58a6ff"), width=1),
            )
            vertical_line.hide()
            add_item(vertical_line)
            items.append(vertical_line)
        if crosshair:
            horizontal_line = pg.InfiniteLine(
                angle=0,
                movable=False,
                pen=pg.mkPen(str(theme.get("crosshair") or "#f2cc60"), width=1),
            )
            horizontal_line.hide()
            add_item(horizontal_line)
            items.append(horizontal_line)
        if hover_readout:
            readout_item = pg.TextItem(
                text="",
                color=str(theme.get("foreground") or "#d8e4f0"),
                fill=pg.mkBrush(str(theme.get("readout_background") or "#111827")),
                anchor=(0, 1),
            )
            readout_item.hide()
            add_item(readout_item)
            items.append(readout_item)

        points = _readout_points(request)
        scene = getattr(widget, "scene", lambda: None)()
        signal = getattr(scene, "sigMouseMoved", None)
        if signal is None:
            setattr(widget, _INVESTIGATION_STATE_ATTR, {"items": items, "points": points})
            return

        def _set_visible(visible: bool) -> None:
            for item in (vertical_line, horizontal_line, readout_item):
                if item is None:
                    continue
                if visible:
                    item.show()
                else:
                    item.hide()

        def _on_mouse_moved(position: Any) -> None:
            if isinstance(position, (list, tuple)) and position:
                position = position[0]
            try:
                if not plot_item.sceneBoundingRect().contains(position):
                    _set_visible(False)
                    return
                mapped = view_box.mapSceneToView(position)
                x_value = float(mapped.x())
                y_value = float(mapped.y())
            except Exception:  # noqa: BLE001
                _set_visible(False)
                return
            if vertical_line is not None:
                vertical_line.setPos(x_value)
            if horizontal_line is not None:
                horizontal_line.setPos(y_value)
            if readout_item is not None:
                readout_item.setText(
                    _readout_text(
                        request,
                        points,
                        x_value=x_value,
                        y_value=y_value,
                        x_only=bool(vertical_guide and not crosshair),
                    )
                )
                readout_item.setPos(x_value, y_value)
            _set_visible(True)

        try:
            signal.connect(_on_mouse_moved)
        except Exception:  # noqa: BLE001
            return
        setattr(
            widget,
            _INVESTIGATION_STATE_ATTR,
            {"items": items, "points": points, "signal": signal, "callback": _on_mouse_moved},
        )

    def _draw(self, widget: QWidget, request: PlotRenderRequest) -> None:
        plot_type = request.plot_type
        if plot_type == PLOT_TYPE_LINE:
            self._draw_line(widget, request)
            return
        if plot_type == PLOT_TYPE_SCATTER:
            self._draw_scatter(widget, request)
            return
        if plot_type == PLOT_TYPE_BAR:
            self._draw_bar(widget, request)
            return
        if plot_type == PLOT_TYPE_HISTOGRAM:
            self._draw_histogram(widget, request)
            return
        if plot_type in {PLOT_TYPE_HEATMAP, PLOT_TYPE_CONTOUR}:
            self._draw_image(widget, request)
            return
        raise ValueError(f"pyqtgraph live rendering does not support {plot_type!r}.")

    @staticmethod
    def _draw_line(widget: QWidget, request: PlotRenderRequest) -> None:
        plot = getattr(widget, "plot", None)
        if not callable(plot):
            raise TypeError("pyqtgraph live widget must expose plot().")
        for index, series in enumerate(request.series):
            x_values, y_values = _xy_values(series)
            plot(x_values, y_values, name=_series_label(series, index))

    @staticmethod
    def _draw_scatter(widget: QWidget, request: PlotRenderRequest) -> None:
        plot = getattr(widget, "plot", None)
        if not callable(plot):
            raise TypeError("pyqtgraph live widget must expose plot().")
        for index, series in enumerate(request.series):
            x_values, y_values = _xy_values(series)
            plot(x_values, y_values, pen=None, symbol="o", name=_series_label(series, index))

    @staticmethod
    def _draw_bar(widget: QWidget, request: PlotRenderRequest) -> None:
        pg = _pyqtgraph()
        add_item = getattr(widget, "addItem", None)
        if not callable(add_item):
            raise TypeError("pyqtgraph live widget must expose addItem().")
        for series in request.series:
            x_values, y_values = _xy_values(series)
            add_item(pg.BarGraphItem(x=x_values, height=y_values, width=float(series.get("width", 0.8))))

    @staticmethod
    def _draw_histogram(widget: QWidget, request: PlotRenderRequest) -> None:
        pg = _pyqtgraph()
        add_item = getattr(widget, "addItem", None)
        if not callable(add_item):
            raise TypeError("pyqtgraph live widget must expose addItem().")
        default_bins = int(request.options.get("bins", 10))
        for series in request.series:
            centers, counts, width = _histogram_bins(
                _histogram_values(series),
                int(series.get("bins", default_bins)),
            )
            if centers:
                add_item(pg.BarGraphItem(x=centers, height=counts, width=width * 0.92))

    @staticmethod
    def _draw_image(widget: QWidget, request: PlotRenderRequest) -> None:
        pg = _pyqtgraph()
        add_item = getattr(widget, "addItem", None)
        if not callable(add_item):
            raise TypeError("pyqtgraph live widget must expose addItem().")
        image_item = pg.ImageItem(_grid_array(request.series[0]))
        add_item(image_item)
        auto_range = getattr(widget, "autoRange", None)
        if callable(auto_range):
            auto_range()


def create_pyqtgraph_plot_backend_record() -> PlotBackendRecord:
    capabilities = tuple(
        PlotCapability(plot_type=plot_type, surface=PLOT_SURFACE_LIVE)
        for plot_type in PYQTGRAPH_LIVE_2D_PLOT_TYPES
    )
    return PlotBackendRecord(
        backend_id=PYQTGRAPH_PLOT_BACKEND_ID,
        display_name=PYQTGRAPH_PLOT_BACKEND_DISPLAY_NAME,
        factory=PyQtGraphLive2DPlotBackend,
        capabilities=capabilities,
        metadata={
            "live_renderer": True,
            "qt_required": True,
            "headless_safe": False,
        },
    )


__all__ = [
    "PYQTGRAPH_LIVE_2D_PLOT_TYPES",
    "PYQTGRAPH_PLOT_BACKEND_DISPLAY_NAME",
    "PYQTGRAPH_PLOT_BACKEND_ID",
    "PyQtGraphLive2DPlotBackend",
    "create_pyqtgraph_plot_backend_record",
]
