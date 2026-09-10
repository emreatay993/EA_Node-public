# Purpose: Render normalized numeric and datetime signals with XY's PNG backend.
# Map: feature_routes/plotter_nodes
# Tests: tests/test_signal_plot_renderer.py
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

import numpy as np
import xy

from ea_node_editor.execution.plot_series_decimation import decimate_xy
from ea_node_editor.execution.signal_plot_inputs import normalize_signal_inputs
from ea_node_editor.runtime_contracts import ImageValue, Interval1D, TypedInlineValue

CATEGORY10 = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
)
LEGEND_LABELS = (
    "Upper left",
    "Upper center",
    "Upper right",
    "Middle left",
    "Middle center",
    "Middle right",
    "Lower left",
    "Lower center",
    "Lower right",
)
LEGEND_LOCATIONS = (
    "upper left",
    "upper center",
    "upper right",
    "center left",
    "center",
    "center right",
    "lower left",
    "lower center",
    "lower right",
)
LINE_DASHES: tuple[str | Sequence[float] | None, ...] = (
    None,
    "solid",
    "dashed",
    "dashdot",
    (6.0, 3.0, 1.0, 3.0, 1.0, 3.0),
    "dotted",
)
# XY has no distinct Hashtag or legacy Tri glyph. Those codes use the nearest
# native symbols; filled/open variants preserve COREX's fill semantics.
MARKERS: tuple[tuple[str, bool] | None, ...] = (
    None,
    ("circle", False),
    ("square", False),
    ("circle", True),
    ("square", True),
    ("diamond", False),
    ("diamond", True),
    ("star", False),
    ("plus_line", False),
    ("cross", False),
    ("x", False),
    ("vertical_line", False),
    ("triangle", False),
    ("triangle_down", False),
    ("triangle", False),
    ("triangle_down", False),
    ("triangle", True),
    ("triangle_down", True),
)


def _list(value: object, name: str, *, allow_empty: bool) -> list[Any]:
    if isinstance(value, np.ndarray):
        result = value.tolist()
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result = list(value)
    elif value is None:
        result = []
    else:
        result = [value]
    if not allow_empty and not result:
        raise ValueError(f"{name} must contain at least one item")
    return result


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}") from exc
    if isinstance(value, (float, np.floating)) and result != value:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    if result < minimum or result > maximum:
        raise ValueError(f"{name} must be from {minimum} to {maximum}")
    return result


def _interval(value: object, name: str, *, logarithmic: bool = False) -> tuple[float, float] | None:
    if value is None or value == "":
        return None
    if isinstance(value, Interval1D):
        start, end = value.start, value.end
    elif isinstance(value, Mapping):
        start, end = value.get("start"), value.get("end")
    else:
        raise ValueError(f"{name} must be an Interval1D or automatic")
    try:
        bounds = float(start), float(end)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} endpoints must be finite numbers") from exc
    if not all(math.isfinite(item) for item in bounds) or bounds[0] >= bounds[1]:
        raise ValueError(f"{name} must have finite increasing endpoints")
    if logarithmic and bounds[0] <= 0:
        raise ValueError("Y axis interval must be positive for logarithmic Y")
    return bounds


def _color(value: object, name: str) -> str:
    if isinstance(value, TypedInlineValue):
        value = value.payload
    if isinstance(value, str):
        text = value.strip()
        if len(text) in {7, 9} and text.startswith("#"):
            try:
                int(text[1:], 16)
            except ValueError:
                pass
            else:
                return text.lower()
    if isinstance(value, Mapping) and all(key in value for key in ("R", "G", "B")):
        if value.get("IsValid") is False:
            raise ValueError(f"{name} is marked invalid")
        channels = []
        for key in ("R", "G", "B"):
            number = float(value[key])
            if not math.isfinite(number):
                raise ValueError(f"{name} contains a non-finite channel")
            channels.append(round(max(0.0, min(1.0, number)) * 255.0))
        if "A" in value:
            alpha = float(value["A"])
            if not math.isfinite(alpha):
                raise ValueError(f"{name} contains a non-finite alpha channel")
            channels.append(round(max(0.0, min(1.0, alpha)) * 255.0))
        return "#" + "".join(f"{channel:02x}" for channel in channels)
    raise ValueError(f"{name} must be a COREX Color or #RRGGBB value")


def render_signal_plot(inputs: Mapping[str, Any]) -> tuple[ImageValue, tuple[str, ...]]:
    logarithmic = bool(inputs.get("logarithmic_y_axis", False))
    signals = normalize_signal_inputs(
        inputs.get("values"),
        x_mode=inputs.get("x_mode", "auto"),
        x_column=inputs.get("x_column", ""),
        y_columns=inputs.get("y_columns", ()),
        logarithmic_y=logarithmic,
    )
    x_kinds = {signal.x_kind for signal in signals}
    if len(x_kinds) != 1:
        raise ValueError("Signal Plot cannot mix numeric and datetime X axes; use Sample index or compatible X columns.")
    datetime_x = x_kinds == {"datetime"}
    count = len(signals)
    max_points = _integer(inputs.get("max_points", 4000), "Maximum rendered points", 0, 2**31 - 1)
    width = _integer(inputs.get("width", 600), "Width", 1, 16384)
    height = _integer(inputs.get("height", 400), "Height", 1, 16384)
    if width * height > 64_000_000:
        raise ValueError("Signal Plot dimensions must not exceed 64 megapixels")
    font_size = _integer(inputs.get("font_size", 12), "Font size", 1, 72)
    legend_alignment = _integer(inputs.get("legend_alignment", 8), "Legend alignment", 0, 8)

    labels = [str(item) for item in _list(inputs.get("labels", []), "Labels", allow_empty=True)]
    if labels and len(labels) != count:
        raise ValueError("Labels must be empty or contain exactly one label per plotted trace")
    if not labels:
        labels = [signal.label for signal in signals]
    colors = _list(inputs.get("colors", []), "Colors", allow_empty=True)
    palette = [_color(item, "Colors") for item in colors] if colors else list(CATEGORY10)
    line_styles = [
        _integer(item, "Line styles", 0, len(LINE_DASHES) - 1)
        for item in _list(inputs.get("line_styles", [1]), "Line styles", allow_empty=False)
    ]
    line_widths = [
        _integer(item, "Line widths", 0, 5)
        for item in _list(inputs.get("line_widths", [1]), "Line widths", allow_empty=False)
    ]
    marker_shapes = [
        _integer(item, "Marker shapes", 0, len(MARKERS) - 1)
        for item in _list(inputs.get("marker_shapes", [1]), "Marker shapes", allow_empty=False)
    ]
    marker_sizes = [
        _integer(item, "Marker sizes", 1, 72)
        for item in _list(inputs.get("marker_sizes", [10]), "Marker sizes", allow_empty=False)
    ]
    x_bounds = _interval(inputs.get("x_axis_interval"), "X axis interval")
    datetime_bounds = (inputs.get("x_datetime_start", ""), inputs.get("x_datetime_end", ""))
    if datetime_x and x_bounds:
        raise ValueError("Datetime X requires ISO-8601 datetime bounds; clear the numeric X axis interval.")
    if any(datetime_bounds) and not datetime_x:
        raise ValueError("Datetime bounds require a typed datetime X column.")
    y_bounds = _interval(inputs.get("y_axis_interval"), "Y axis interval", logarithmic=logarithmic)
    image_background = _color(inputs.get("image_background_color", "#ffffff"), "Image background color")
    data_background = _color(inputs.get("data_background_color", "#ffffff"), "Data background color")

    warnings: list[str] = []
    marks: list[Any] = []
    datetime_extents: list[tuple[float, float]] = []
    for index, signal in enumerate(signals):
        values = signal.y
        x_values = signal.x
        if datetime_x:
            missing_x = np.isnat(x_values)
            milliseconds = x_values.astype("datetime64[ms]")
            fractional_ms = (x_values - milliseconds).astype("timedelta64[ns]").astype(np.float64) / 1_000_000
            x_values = milliseconds.astype(np.float64) + fractional_ms
            x_values[missing_x] = np.nan
            finite_x = x_values[np.isfinite(x_values)]
            if len(finite_x):
                datetime_extents.append((float(finite_x.min()), float(finite_x.max())))
        finite = np.isfinite(values) & np.isfinite(x_values)
        if logarithmic:
            valid = finite & (values > 0.0)
            if not np.any(valid):
                raise ValueError(f"Values branch {index} has no positive finite samples for logarithmic Y")
            if not np.all(valid):
                values = values.astype(np.float64, copy=True)
                values[~valid] = np.nan
                if not warnings:
                    warnings.append("Non-positive or non-finite samples were rendered as gaps on logarithmic Y.")
        elif not np.all(finite):
            values = values.astype(np.float64, copy=True)
            values[~finite] = np.nan
            if not warnings:
                warnings.append("Non-finite samples were rendered as gaps.")

        if max_points and len(values) > max_points:
            x_values, values, reduction = decimate_xy(x_values, values, max_points, preserve_gaps=True)
            warnings.append(
                f"Trace {index + 1} reduced from {reduction['original_rows']} to {reduction['points']} rendered points; source data is unchanged."
            )
        color = palette[index % len(palette)]
        label = labels[index] or None
        line_code = line_styles[index % len(line_styles)]
        marker_code = marker_shapes[index % len(marker_shapes)]
        line_width = line_widths[index % len(line_widths)]
        if line_code and line_width > 0:
            marks.append(
                xy.line(
                    x_values,
                    values,
                    name=label,
                    color=color,
                    width=float(line_width),
                    dash=LINE_DASHES[line_code],
                )
            )
        marker = MARKERS[marker_code]
        if marker is not None:
            symbol, open_marker = marker
            marks.append(
                xy.scatter(
                    x_values,
                    values,
                    name=label if not (line_code and line_width > 0) else None,
                    color=data_background if open_marker else color,
                    size=float(marker_sizes[index % len(marker_sizes)]),
                    symbol=symbol,
                    stroke=color,
                    stroke_width=1.0 if open_marker else 0.0,
                    opacity=1.0,
                )
            )

    if datetime_x and any(datetime_bounds):
        if not datetime_extents:
            raise ValueError("Datetime X has no finite values for its axis bounds.")
        limits = [min(item[0] for item in datetime_extents), max(item[1] for item in datetime_extents)]
        for index, value in enumerate(datetime_bounds):
            if value:
                try:
                    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    limits[index] = parsed.replace(tzinfo=timezone.utc).timestamp() * 1000 if parsed.tzinfo is None else parsed.timestamp() * 1000
                except (ValueError, OverflowError) as exc:
                    raise ValueError("Datetime bounds must use ISO-8601 dates or timestamps.") from exc
        if limits[0] >= limits[1]:
            raise ValueError("Datetime bounds must have increasing endpoints.")
        x_bounds = (limits[0], limits[1])
    axis_style = {"tick_label_size": float(font_size), "label_size": float(font_size)}
    x_label = str(inputs.get("x_axis_label", "") or "")
    if datetime_x:
        x_label = f"{x_label} (UTC)" if x_label else "UTC"
    components: list[Any] = [
        *marks,
        xy.x_axis(label=x_label, type_="time" if datetime_x else None, bounds=x_bounds, domain=x_bounds, style=axis_style),
        xy.y_axis(
            label=str(inputs.get("y_axis_label", "") or ""),
            bounds=y_bounds,
            type_="log" if logarithmic else None,
            nonpositive="mask" if logarithmic else None,
            style=axis_style,
        ),
        xy.theme(background=image_background, plot_background=data_background),
    ]
    if any(labels) and bool(inputs.get("show_legend", False)):
        components.append(xy.legend(show=True, loc=LEGEND_LOCATIONS[legend_alignment]))
    chart = xy.chart(
        *components,
        width=width,
        height=height,
        title=str(inputs.get("title", "") or ""),
        style={"font-size": f"{font_size}px"},
    )
    png = chart.to_png(width=width, height=height, scale=1.0)
    return ImageValue.from_png(png), tuple(warnings)


__all__ = [
    "CATEGORY10",
    "LEGEND_LABELS",
    "LEGEND_LOCATIONS",
    "LINE_DASHES",
    "MARKERS",
    "render_signal_plot",
]
