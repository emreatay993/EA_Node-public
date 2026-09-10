from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from tempfile import NamedTemporaryFile
from time import perf_counter
from typing import Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative
from plotly.subplots import make_subplots

try:
    from plotly_resampler import FigureResampler
except ImportError:  # pragma: no cover - requirements include it, but keep static fallback.
    FigureResampler = None  # type: ignore[assignment]


DEFAULT_LEGEND_POSITION = "default"
DEFAULT_RESAMPLER_SAMPLES = 2500
DEFAULT_HOVER_ANNOTATION_STYLE = "sensor"
OVERLAY_WEBGL_POINT_THRESHOLD = DEFAULT_RESAMPLER_SAMPLES * 10
# Calibration scatter is a density cloud, not a time series, so its non-monotonic X
# bars it from the time-series resampler and every raw point is built and serialized.
# Cap the markers per channel: thousands of overlapping points are visually redundant
# and dominate both go.Scatter construction and HTML serialization.
CALIB_SCATTER_POINT_CAP = 2000
WE_DAVIS_HOVER_ANNOTATION_STYLE = "we_davis"
HOVER_ANNOTATION_STYLES = (
    DEFAULT_HOVER_ANNOTATION_STYLE,
    WE_DAVIS_HOVER_ANNOTATION_STYLE,
)
HOVER_ANNOTATION_STYLE_LABELS = {
    DEFAULT_HOVER_ANNOTATION_STYLE: "Sensor",
    WE_DAVIS_HOVER_ANNOTATION_STYLE: "WE-DAVIS",
}
LEGEND_POSITIONS = (
    DEFAULT_LEGEND_POSITION,
    "top left",
    "top right",
    "bottom right",
    "bottom left",
)
SG_OVERLAY_COLORS = qualitative.Light24
LOGGER = logging.getLogger(__name__)

PLOT_COLORS = {
    "blue": "#2f6fbb",
    "teal": "#178f8f",
    "green": "#3a8f5a",
    "amber": "#b67818",
    "red": "#b64a4a",
    "purple": "#6f5ab8",
    "slate": "#526070",
    "cyan": "#3d90b7",
    "gray": "#9aa7b5",
}

HOVER_LABEL_STYLE = {
    "bgcolor": "rgba(255, 255, 255, 0.78)",
    "bordercolor": "rgba(36, 49, 63, 0.32)",
    "font": {"family": "Segoe UI, Arial, sans-serif", "size": 12, "color": "#1e2a36"},
}

WE_DAVIS_HOVER_LABEL_STYLE = {
    "bgcolor": "rgba(240, 240, 240, 0.9)",
    "font": {"family": "Open Sans, Segoe UI, Arial, sans-serif", "size": 15, "color": "#000000"},
}
WE_DAVIS_HOVER_TEMPLATE_TRACE_TYPES = {"bar", "scatter", "scattergl"}

METRIC_GROUPS = {
    "Error": [
        "RMSE",
        "MAE",
        "Mean Bias",
        "Max Abs Error",
        "P95 Abs Error",
        "P99 Abs Error",
        "MSE",
        "Absolute Error",
        "Percentage Error",
        "SMAPE",
        "WMAPE",
        "Within Tolerance Abs (%)",
        "Within Tolerance Rel (%)",
        "Robust NMAE (%)",
    ],
    "Correlation": [
        "Max Correlation",
        "Pearson Correlation",
        "Coefficient of Determination",
        "Lag at Max Correlation (samples)",
        "Time Shift (s)",
    ],
    "Polarity": [
        "Sign Agreement (%)",
        "Sign Mismatch (%)",
        "Sign Deadband (%)",
        "Polarity Score",
        "Longest Sign Mismatch (s)",
    ],
    "Lag": ["Best Lag (samples)", "Best Lag (s)", "Max Lag Correlation"],
    "Event": ["Mean Event Timing Error (s)", "Max Event Timing Error (s)", "Event Count Delta"],
    "Quality": ["Data Quality Warnings"],
    "Calibration": ["Calibration Slope", "Calibration Offset", "Calibration R^2", "Residual Std"],
    "Frequency": ["Dominant Freq Delta", "Spectral Energy Ratio"],
    "Certification": ["Certification Score", "Peak Error (%)", "Slope Error (%)", "Envelope NMAE (%)"],
}

DEFAULT_METRIC_KEYS = [
    "Max Correlation",
    "Pearson Correlation",
    "Coefficient of Determination",
    "RMSE",
    "MAE",
    "Robust NMAE (%)",
    "Sign Agreement (%)",
    "Mean Bias",
    "Best Lag (s)",
]

METRIC_SPECS = {
    "Max Correlation": ("Max Correlation", "bar", PLOT_COLORS["blue"], "solid"),
    "Lag at Max Correlation (samples)": ("Lag at Max Corr (Samples)", "bar", PLOT_COLORS["red"], "solid"),
    "Time Shift (s)": ("Time Shift (s)", "bar", PLOT_COLORS["amber"], "solid"),
    "Coefficient of Determination": ("Coefficient of Determination", "bar", PLOT_COLORS["purple"], "solid"),
    "Pearson Correlation": ("Pearson R", "bar", PLOT_COLORS["teal"], "solid"),
    "MSE": ("MSE", "line", PLOT_COLORS["slate"], "solid"),
    "RMSE": ("RMSE", "line", PLOT_COLORS["cyan"], "solid"),
    "Absolute Error": ("Absolute Error", "line", PLOT_COLORS["amber"], "dot"),
    "Percentage Error": ("Percentage Error (%)", "line", PLOT_COLORS["green"], "dash"),
    "SMAPE": ("SMAPE", "line", PLOT_COLORS["blue"], "dash"),
    "WMAPE": ("WMAPE", "line", PLOT_COLORS["red"], "dot"),
    "Within Tolerance Abs (%)": ("Within Tolerance Abs (%)", "line", PLOT_COLORS["green"], "solid"),
    "Within Tolerance Rel (%)": ("Within Tolerance Rel (%)", "line", PLOT_COLORS["teal"], "dash"),
    "Robust NMAE (%)": ("Robust NMAE (%)", "line", PLOT_COLORS["cyan"], "dash"),
    "Sign Agreement (%)": ("Sign Agreement (%)", "line", PLOT_COLORS["green"], "solid"),
    "Sign Mismatch (%)": ("Sign Mismatch (%)", "line", PLOT_COLORS["red"], "dash"),
    "Sign Deadband (%)": ("Sign Deadband (%)", "line", PLOT_COLORS["gray"], "dot"),
    "Polarity Score": ("Polarity Score", "line", PLOT_COLORS["purple"], "dash"),
    "Longest Sign Mismatch (s)": ("Longest Sign Mismatch (s)", "line", PLOT_COLORS["red"], "longdash"),
    "Mean Bias": ("Mean Bias", "line", PLOT_COLORS["purple"], "solid"),
    "MAE": ("MAE", "line", PLOT_COLORS["amber"], "solid"),
    "Max Abs Error": ("Max Abs Error", "line", PLOT_COLORS["red"], "solid"),
    "P95 Abs Error": ("P95 Abs Error", "line", PLOT_COLORS["cyan"], "dash"),
    "P99 Abs Error": ("P99 Abs Error", "line", PLOT_COLORS["red"], "dash"),
    "Best Lag (samples)": ("Best Lag (samples)", "bar", PLOT_COLORS["slate"], "solid"),
    "Best Lag (s)": ("Best Lag (s)", "bar", PLOT_COLORS["amber"], "solid"),
    "Max Lag Correlation": ("Max Lag Correlation", "line", PLOT_COLORS["blue"], "dash"),
    "Mean Event Timing Error (s)": ("Mean Event Timing Error (s)", "line", PLOT_COLORS["amber"], "dot"),
    "Max Event Timing Error (s)": ("Max Event Timing Error (s)", "line", PLOT_COLORS["red"], "dot"),
    "Event Count Delta": ("Event Count Delta", "bar", PLOT_COLORS["purple"], "solid"),
    "Data Quality Warnings": ("Data Quality Warnings", "bar", PLOT_COLORS["red"], "solid"),
    "Calibration Slope": ("Calibration Slope", "line", PLOT_COLORS["blue"], "solid"),
    "Calibration Offset": ("Calibration Offset", "line", PLOT_COLORS["purple"], "dash"),
    "Calibration R^2": ("Calibration R^2", "line", PLOT_COLORS["teal"], "solid"),
    "Residual Std": ("Residual Std", "line", PLOT_COLORS["slate"], "dash"),
    "Dominant Freq Delta": ("Dominant Freq Delta", "line", PLOT_COLORS["cyan"], "dash"),
    "Spectral Energy Ratio": ("Spectral Energy Ratio", "line", PLOT_COLORS["green"], "solid"),
    "Certification Score": ("Certification Score", "bar", PLOT_COLORS["green"], "solid"),
    "Peak Error (%)": ("Peak Error (%)", "line", PLOT_COLORS["red"], "solid"),
    "Slope Error (%)": ("Slope Error (%)", "line", PLOT_COLORS["amber"], "dash"),
    "Envelope NMAE (%)": ("Envelope NMAE (%)", "line", PLOT_COLORS["purple"], "dot"),
}

ALL_METRIC_KEYS = [metric for metrics in METRIC_GROUPS.values() for metric in metrics]
COMPACT_SOURCE_LABEL_MAX_LENGTH = 36


@dataclass(frozen=True)
class SignAgreementPlotData:
    status_frame: pd.DataFrame
    metrics: list[dict[str, float | str]]
    reference_name: str
    target_name: str
    deadband: float


def is_resampled_figure(fig: object) -> bool:
    return FigureResampler is not None and isinstance(fig, FigureResampler)


def next_legend_position(current_position: str) -> str:
    try:
        index = LEGEND_POSITIONS.index(current_position)
    except ValueError:
        return DEFAULT_LEGEND_POSITION
    return LEGEND_POSITIONS[(index + 1) % len(LEGEND_POSITIONS)]


def next_hover_annotation_style(current_style: str) -> str:
    try:
        index = HOVER_ANNOTATION_STYLES.index(current_style)
    except ValueError:
        return DEFAULT_HOVER_ANNOTATION_STYLE
    return HOVER_ANNOTATION_STYLES[(index + 1) % len(HOVER_ANNOTATION_STYLES)]


def hover_annotation_style_label(style: str) -> str:
    return HOVER_ANNOTATION_STYLE_LABELS.get(style, HOVER_ANNOTATION_STYLE_LABELS[DEFAULT_HOVER_ANNOTATION_STYLE])


def write_offline_plot_html(fig: go.Figure) -> str:
    html = fig.to_html(
        full_html=True,
        include_plotlyjs=True,
        config={"responsive": True, "displaylogo": False},
    )
    html = html.replace(":focus-visible", ":focus")
    with NamedTemporaryFile("w", delete=False, suffix=".html", encoding="utf-8") as temp_file:
        temp_file.write(html)
        return temp_file.name


def _legend_layout(position: str) -> dict[str, object]:
    common: dict[str, object] = {
        "font": {"size": 11},
        "itemsizing": "constant",
        "traceorder": "normal",
        "bgcolor": "rgba(255, 255, 255, 0.96)",
        "bordercolor": "rgba(203, 213, 223, 0.95)",
        "borderwidth": 1,
    }
    if position == "top left":
        return common | {
            "orientation": "v",
            "x": 0.01,
            "y": 0.99,
            "xanchor": "left",
            "yanchor": "top",
            "maxheight": 0.82,
        }
    if position == "top right":
        return common | {
            "orientation": "v",
            "x": 0.99,
            "y": 0.99,
            "xanchor": "right",
            "yanchor": "top",
            "maxheight": 0.82,
        }
    if position == "bottom right":
        return common | {
            "orientation": "v",
            "x": 0.99,
            "y": 0.01,
            "xanchor": "right",
            "yanchor": "bottom",
            "maxheight": 0.82,
        }
    if position == "bottom left":
        return common | {
            "orientation": "v",
            "x": 0.01,
            "y": 0.01,
            "xanchor": "left",
            "yanchor": "bottom",
            "maxheight": 0.82,
        }
    return common | {
        "orientation": "v",
        "x": 1.02,
        "y": 1,
        "xanchor": "left",
        "yanchor": "top",
        "maxheight": 0.92,
    }


def _plot_margin(position: str) -> dict[str, int]:
    if position == DEFAULT_LEGEND_POSITION:
        return {"l": 58, "r": 260, "t": 58, "b": 54}
    return {"l": 58, "r": 28, "t": 58, "b": 54}


def _compact_source_label(name: str, fallback: str) -> str:
    candidate = name.strip()
    if not candidate:
        return fallback
    if len(candidate) <= COMPACT_SOURCE_LABEL_MAX_LENGTH and "__" not in candidate and "/" not in candidate and "\\" not in candidate:
        return candidate
    return fallback


def _hover_layout(unified_hover: bool, hover_annotation_style: str) -> dict[str, object]:
    if hover_annotation_style == WE_DAVIS_HOVER_ANNOTATION_STYLE:
        return {
            "hovermode": "closest",
            "hoverlabel": WE_DAVIS_HOVER_LABEL_STYLE,
        }
    return {
        "hovermode": "x unified" if unified_hover else "closest",
        "hoverlabel": HOVER_LABEL_STYLE,
    }


def _we_davis_hover_template(x_title: str, y_title: str) -> str:
    x_label = x_title or "X"
    value_label = y_title or "Value"
    return f"%{{fullData.name}}<br>{x_label}: %{{x}}<br>{value_label}: %{{y:.3f}}<extra></extra>"


def _apply_we_davis_hover_template(fig: go.Figure, x_title: str, y_title: str, hover_annotation_style: str) -> None:
    if hover_annotation_style != WE_DAVIS_HOVER_ANNOTATION_STYLE:
        return
    hover_template = _we_davis_hover_template(x_title, y_title)
    for trace in fig.data:
        if getattr(trace, "type", None) in WE_DAVIS_HOVER_TEMPLATE_TRACE_TYPES:
            trace.hovertemplate = hover_template


def _apply_common_layout(
    fig: go.Figure,
    title: str,
    x_title: str,
    y_title: str,
    *,
    grouped_bars: bool = False,
    unified_hover: bool = True,
    legend_position: str = DEFAULT_LEGEND_POSITION,
    hover_annotation_style: str = DEFAULT_HOVER_ANNOTATION_STYLE,
) -> go.Figure:
    hover_layout = _hover_layout(unified_hover, hover_annotation_style)
    fig.update_layout(
        title={"text": title, "x": 0.02, "xanchor": "left", "font": {"size": 16}},
        template="plotly_white",
        autosize=True,
        margin=_plot_margin(legend_position),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"family": "Segoe UI, Arial, sans-serif", "size": 12, "color": "#24313f"},
        legend=_legend_layout(legend_position),
        hovermode=hover_layout["hovermode"],
        hoverlabel=hover_layout["hoverlabel"],
    )
    fig.update_xaxes(
        title=x_title,
        showgrid=True,
        gridcolor="#edf1f5",
        zeroline=False,
        linecolor="#cbd5df",
    )
    fig.update_yaxes(
        title=y_title,
        showgrid=True,
        gridcolor="#edf1f5",
        zeroline=True,
        zerolinecolor="#d7dee8",
        linecolor="#cbd5df",
        nticks=11,
    )
    if grouped_bars:
        fig.update_layout(barmode="group")
    _apply_we_davis_hover_template(fig, x_title, y_title, hover_annotation_style)
    return fig


def _as_resampled_figure(fig: go.Figure) -> go.Figure:
    if FigureResampler is None or not _has_resample_candidate(fig):
        return fig
    started = perf_counter()
    resampled = FigureResampler(fig, default_n_shown_samples=DEFAULT_RESAMPLER_SAMPLES)
    LOGGER.info("Wrapped %d traces with Plotly Resampler in %.3fs", len(fig.data), perf_counter() - started)
    return resampled


def _has_resample_candidate(fig: go.Figure) -> bool:
    has_candidate = False
    for trace in fig.data:
        if getattr(trace, "type", None) not in {"scatter", "scattergl"}:
            continue
        trace_points = max(
            _trace_length(getattr(trace, "x", None)),
            _trace_length(getattr(trace, "y", None)),
        )
        if trace_points <= DEFAULT_RESAMPLER_SAMPLES:
            continue
        if not _trace_x_is_monotonic(getattr(trace, "x", None)):
            return False
        has_candidate = True
    return has_candidate


def _trace_x_is_monotonic(values: object) -> bool:
    if _trace_length(values) <= 1:
        return True
    try:
        return bool(pd.Index(values).is_monotonic_increasing)
    except Exception:
        return False


def _trace_length(values: object) -> int:
    if values is None:
        return 0
    try:
        return len(values)  # type: ignore[arg-type]
    except TypeError:
        return 0


def _can_register_overlay_hf_data(columns: Sequence[str], time_arrays: Sequence[object]) -> bool:
    if FigureResampler is None or not columns:
        return False
    if not any(_trace_length(values) > DEFAULT_RESAMPLER_SAMPLES for values in time_arrays):
        return False
    monotonic_by_id: dict[int, bool] = {}
    for values in time_arrays:
        key = id(values)
        if key not in monotonic_by_id:
            monotonic_by_id[key] = _trace_x_is_monotonic(values)
        if not monotonic_by_id[key]:
            return False
    return True


def _overlay_trace_type(render_mode: str, raw_points: int):
    if render_mode == "webgl" or (render_mode == "auto" and raw_points > OVERLAY_WEBGL_POINT_THRESHOLD):
        return go.Scattergl
    if render_mode in {"auto", "svg"}:
        return go.Scatter
    raise ValueError(f"Unknown overlay render mode: {render_mode}")


def _line_trace(x, y, name: str, *, mode: str = "lines", line: dict | None = None, **extra) -> dict:
    """Build a scatter trace as a plain dict instead of constructing a ``go.Scatter``.

    Adding these via a single ``fig.add_traces([...])`` still validates the data once,
    but skips the per-object ``go.Scatter.__init__`` validation that dominates builders
    with hundreds of traces (each eager construction re-runs Plotly's property
    validators, and ``add_traces`` then validates a second time). One validation pass
    instead of two, and no throwaway graph-object overhead.
    """
    trace: dict[str, object] = {"type": "scatter", "x": x, "y": y, "mode": mode, "name": name}
    if line is not None:
        trace["line"] = line
    trace.update(extra)
    return trace


def build_metrics_figure(
    metrics: list[dict[str, float | str]],
    dataset1_name: str,
    dataset2_name: str,
    *,
    selected_metric_keys: list[str] | None = None,
    legend_position: str = DEFAULT_LEGEND_POSITION,
    hover_annotation_style: str = DEFAULT_HOVER_ANNOTATION_STYLE,
) -> go.Figure:
    channels = [str(metric["Channel"]) for metric in metrics]
    fig = go.Figure()
    selected_keys = selected_metric_keys if selected_metric_keys is not None else DEFAULT_METRIC_KEYS
    for key in selected_keys:
        if key not in METRIC_SPECS:
            continue
        trace_name, trace_type, color, dash = METRIC_SPECS[key]
        if trace_type == "bar":
            fig.add_trace(
                go.Bar(
                    x=channels,
                    y=[metric.get(key) for metric in metrics],
                    name=trace_name,
                    marker_color=color,
                )
            )
        else:
            fig.add_trace(
                go.Scatter(
                    x=channels,
                    y=[metric.get(key) for metric in metrics],
                    name=trace_name,
                    mode="lines+markers",
                    line={"color": color, "dash": dash},
                )
            )
    if not fig.data:
        fig.add_annotation(
            text="No aggregate metrics selected.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"size": 14, "color": "#647386"},
        )

    return _apply_common_layout(
        fig,
        f"Statistical Metrics - {dataset1_name} vs {dataset2_name}",
        "Channel",
        "Metric Value",
        grouped_bars=True,
        legend_position=legend_position,
        hover_annotation_style=hover_annotation_style,
    )


CERTIFICATION_GRADE_COLORS = {
    "A": PLOT_COLORS["green"],
    "B": PLOT_COLORS["blue"],
    "C": PLOT_COLORS["amber"],
    "Reject": PLOT_COLORS["red"],
}
CERTIFICATION_MAX_PEAK_ERROR_PCT = 25.0
CERTIFICATION_MAX_ENVELOPE_NMAE_PCT = 20.0
CERTIFICATION_LABEL_MODES = {"auto", "none", "rejected", "selected"}


def _metric_float(metric: dict[str, float | str], key: str) -> float:
    value = metric.get(key)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def _certification_sorted_metrics(metrics: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    grade_order = {"A": 0, "B": 1, "C": 2, "Reject": 3}
    return sorted(
        metrics,
        key=lambda row: (
            grade_order.get(str(row.get("Evidence Grade", "")), 4),
            -_metric_float(row, "Certification Score"),
            str(row.get("Channel", "")),
        ),
    )


def _certification_is_warning(row: dict[str, float | str]) -> bool:
    if str(row.get("Evidence Grade", "")) in {"B", "C"}:
        return True
    return _metric_float(row, "Data Quality Warnings") > 0


def _certification_label_channels(
    ranked: list[dict[str, float | str]],
    highlighted_channels: set[str],
    label_mode: str,
    max_labels: int,
) -> set[str]:
    label_mode = label_mode if label_mode in CERTIFICATION_LABEL_MODES else "auto"
    max_labels = max(0, int(max_labels))
    if label_mode == "none" or max_labels == 0:
        return set()

    labels: list[str] = []

    def add(channel: str) -> None:
        if channel and channel not in labels and len(labels) < max_labels:
            labels.append(channel)

    for channel in sorted(highlighted_channels):
        add(channel)
    if label_mode == "selected":
        return set(labels)

    for row in ranked:
        if str(row.get("Evidence Grade", "")) == "Reject":
            add(str(row.get("Channel", "")))
    if label_mode == "rejected":
        return set(labels)

    for key in ("Peak Error (%)", "Envelope NMAE (%)"):
        for row in sorted(ranked, key=lambda item: _metric_float(item, key), reverse=True):
            add(str(row.get("Channel", "")))
    return set(labels)


def _certification_summary_text(ranked: list[dict[str, float | str]]) -> str:
    eligible = sum(1 for row in ranked if str(row.get("Certification Eligible", "")) == "Yes")
    rejected = sum(1 for row in ranked if str(row.get("Evidence Grade", "")) == "Reject")
    warnings = sum(1 for row in ranked if str(row.get("Evidence Grade", "")) != "Reject" and _certification_is_warning(row))
    peak_errors = [_metric_float(row, "Peak Error (%)") for row in ranked]
    nmae_values = [_metric_float(row, "Envelope NMAE (%)") for row in ranked]
    worst_peak = max((value for value in peak_errors if math.isfinite(value)), default=math.nan)
    worst_nmae = max((value for value in nmae_values if math.isfinite(value)), default=math.nan)

    def fmt(value: float) -> str:
        return f"{value:.3g}%" if math.isfinite(value) else "n/a"

    return (
        f"Channels: {len(ranked)} | Eligible: {eligible} | Reject: {rejected} | "
        f"Warning: {warnings} | Worst peak error: {fmt(worst_peak)} | Worst envelope NMAE: {fmt(worst_nmae)}"
    )


def build_certification_ranking_figure(
    metrics: list[dict[str, float | str]],
    dataset1_name: str,
    dataset2_name: str,
    *,
    legend_position: str = DEFAULT_LEGEND_POSITION,
    hover_annotation_style: str = DEFAULT_HOVER_ANNOTATION_STYLE,
    highlighted_channels: Sequence[str] = (),
    label_mode: str = "none",
    max_labels: int = 12,
) -> go.Figure:
    ranked = _certification_sorted_metrics(metrics)
    fig = make_subplots(
        rows=1,
        cols=3,
        subplot_titles=("Evidence score", "Peak parity", "Error screen"),
        horizontal_spacing=0.08,
    )
    if not ranked:
        fig.add_annotation(text="No channels selected.", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        return _apply_common_layout(
            fig,
            f"Certification Ranking - {dataset1_name} vs {dataset2_name}",
            "Channel",
            "Metric Value",
            legend_position=legend_position,
            hover_annotation_style=hover_annotation_style,
        )

    channels = [str(row["Channel"]) for row in ranked]
    grades = [str(row.get("Evidence Grade", "")) for row in ranked]
    colors = [CERTIFICATION_GRADE_COLORS.get(grade, PLOT_COLORS["gray"]) for grade in grades]
    highlighted = {str(channel) for channel in highlighted_channels}
    normalized_label_mode = label_mode if label_mode in CERTIFICATION_LABEL_MODES else "auto"
    label_channels = _certification_label_channels(ranked, highlighted, normalized_label_mode, max_labels)
    labels = [channel if channel in label_channels else "" for channel in channels]
    scatter_mode = "markers+text" if any(labels) else "markers"
    # The grade letters on the evidence bars are permanent text too, so keep them in step
    # with the scatter labels: "No labels" (the default) yields a fully hover-only figure.
    # The grade still reaches the tooltip via %{text}, and the bar colour already encodes it.
    grade_textposition = "none" if normalized_label_mode == "none" else "auto"
    marker_sizes = [13 if channel in highlighted else 8 for channel in channels]
    marker_opacity = [1.0 if not highlighted or channel in highlighted else 0.42 for channel in channels]
    marker_lines = {
        "color": [PLOT_COLORS["slate"] if channel in highlighted else "#ffffff" for channel in channels],
        "width": [2.4 if channel in highlighted else 0.8 for channel in channels],
    }
    hover_data = [
        [
            str(row.get("Channel", "")),
            str(row.get("Evidence Grade", "")),
            _metric_float(row, "Certification Score"),
            _metric_float(row, "Peak Error (%)"),
            _metric_float(row, "Envelope NMAE (%)"),
            str(row.get("Certification Eligible", "")),
            str(row.get("Exclusion Reason", "")),
        ]
        for row in ranked
    ]
    fig.add_trace(
        go.Bar(
            x=channels,
            y=[_metric_float(row, "Certification Score") for row in ranked],
            text=grades,
            textposition=grade_textposition,
            name="Evidence Grade",
            marker_color=colors,
            hovertemplate=(
                "Channel: %{x}<br>Score: %{y:.3g}<br>Grade: %{text}<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )

    peak_x = [_metric_float(row, "Peak Strain Test") for row in ranked]
    peak_y = [_metric_float(row, "Peak Strain FEA") for row in ranked]
    fig.add_trace(
        go.Scatter(
            x=peak_x,
            y=peak_y,
            mode=scatter_mode,
            text=labels,
            textposition="top center",
            name="Peak parity",
            customdata=hover_data,
            hovertemplate=(
                "Channel: %{customdata[0]}<br>"
                f"{dataset1_name} peak: %{{x:.4g}}<br>"
                f"{dataset2_name} peak: %{{y:.4g}}<br>"
                "Score: %{customdata[2]:.3g}<br>"
                "Grade: %{customdata[1]}<br>"
                "Eligible: %{customdata[5]}<br>"
                "%{customdata[6]}<extra></extra>"
            ),
            marker={
                "size": marker_sizes,
                "color": colors,
                "opacity": marker_opacity,
                "line": marker_lines,
            },
        ),
        row=1,
        col=2,
    )
    finite_peaks = [value for value in [*peak_x, *peak_y] if math.isfinite(value)]
    if finite_peaks:
        low = min(finite_peaks)
        high = max(finite_peaks)
        if low == high:
            low -= 1.0
            high += 1.0
        for factor, name, dash, color in [
            (1.0, "Identity", "solid", PLOT_COLORS["slate"]),
            (1.10, "+10%", "dash", PLOT_COLORS["green"]),
            (0.90, "-10%", "dash", PLOT_COLORS["green"]),
            (1.20, "+20%", "dot", PLOT_COLORS["amber"]),
            (0.80, "-20%", "dot", PLOT_COLORS["amber"]),
        ]:
            fig.add_trace(
                go.Scatter(
                    x=[low, high],
                    y=[low * factor, high * factor],
                    mode="lines",
                    name=name,
                    line={"color": color, "dash": dash, "width": 1},
                ),
                row=1,
                col=2,
            )

    error_x = [_metric_float(row, "Envelope NMAE (%)") for row in ranked]
    error_y = [_metric_float(row, "Peak Error (%)") for row in ranked]
    finite_error_x = [value for value in error_x if math.isfinite(value)]
    finite_error_y = [value for value in error_y if math.isfinite(value)]
    x_high = max([CERTIFICATION_MAX_ENVELOPE_NMAE_PCT, *finite_error_x], default=CERTIFICATION_MAX_ENVELOPE_NMAE_PCT)
    y_high = max([CERTIFICATION_MAX_PEAK_ERROR_PCT, *finite_error_y], default=CERTIFICATION_MAX_PEAK_ERROR_PCT)
    x_high = x_high * 1.08 if x_high > 0 else 1.0
    y_high = y_high * 1.08 if y_high > 0 else 1.0
    fig.add_shape(
        type="rect",
        x0=0,
        x1=CERTIFICATION_MAX_ENVELOPE_NMAE_PCT,
        y0=0,
        y1=CERTIFICATION_MAX_PEAK_ERROR_PCT,
        fillcolor=PLOT_COLORS["green"],
        opacity=0.06,
        line={"width": 0},
        layer="below",
        row=1,
        col=3,
    )
    fig.add_vrect(
        x0=CERTIFICATION_MAX_ENVELOPE_NMAE_PCT,
        x1=x_high,
        fillcolor=PLOT_COLORS["amber"],
        opacity=0.05,
        line_width=0,
        layer="below",
        row=1,
        col=3,
    )
    fig.add_hrect(
        y0=CERTIFICATION_MAX_PEAK_ERROR_PCT,
        y1=y_high,
        fillcolor=PLOT_COLORS["red"],
        opacity=0.05,
        line_width=0,
        layer="below",
        row=1,
        col=3,
    )
    fig.add_trace(
        go.Scatter(
            x=error_x,
            y=error_y,
            mode=scatter_mode,
            text=labels,
            textposition="top center",
            name="Error screen",
            customdata=hover_data,
            hovertemplate=(
                "Channel: %{customdata[0]}<br>"
                "Envelope NMAE: %{x:.3g}%<br>"
                "Peak error: %{y:.3g}%<br>"
                "Score: %{customdata[2]:.3g}<br>"
                "Grade: %{customdata[1]}<br>"
                "Eligible: %{customdata[5]}<br>"
                "%{customdata[6]}<extra></extra>"
            ),
            marker={
                "size": marker_sizes,
                "color": colors,
                "opacity": marker_opacity,
                "line": marker_lines,
            },
        ),
        row=1,
        col=3,
    )
    fig.add_hline(
        y=CERTIFICATION_MAX_PEAK_ERROR_PCT,
        line={"color": PLOT_COLORS["red"], "dash": "dot", "width": 1},
        row=1,
        col=3,
    )
    fig.add_vline(
        x=CERTIFICATION_MAX_ENVELOPE_NMAE_PCT,
        line={"color": PLOT_COLORS["red"], "dash": "dot", "width": 1},
        row=1,
        col=3,
    )
    _apply_common_layout(
        fig,
        f"Certification Ranking - {dataset1_name} vs {dataset2_name}",
        "Channel",
        "Metric Value",
        legend_position=legend_position,
        hover_annotation_style=hover_annotation_style,
    )
    margin = fig.layout.margin.to_plotly_json()
    margin["t"] = 112
    fig.update_layout(margin=margin)
    fig.add_annotation(
        text=_certification_summary_text(ranked),
        x=0,
        y=1.13,
        xref="paper",
        yref="paper",
        showarrow=False,
        align="left",
        xanchor="left",
        font={"size": 12, "color": PLOT_COLORS["slate"]},
        bgcolor="rgba(255, 255, 255, 0.82)",
        bordercolor="rgba(82, 96, 112, 0.22)",
        borderwidth=1,
        borderpad=4,
    )
    fig.update_xaxes(title_text="Channel", row=1, col=1)
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_yaxes(title_text="Score", range=[0, 105], row=1, col=1)
    fig.update_xaxes(title_text=f"{dataset1_name} peak", row=1, col=2)
    fig.update_yaxes(title_text=f"{dataset2_name} peak", row=1, col=2)
    fig.update_xaxes(title_text="Envelope NMAE (%)", row=1, col=3)
    fig.update_yaxes(title_text="Peak Error (%)", row=1, col=3)
    return fig


def build_residual_figure(
    residual_frame: pd.DataFrame,
    residual_metrics: list[dict[str, float | str]],
    reference_name: str,
    target_name: str,
    *,
    reference_frame: pd.DataFrame | None = None,
    absolute_tolerance: float = 0.0,
    relative_tolerance_pct: float = 0.0,
    legend_position: str = DEFAULT_LEGEND_POSITION,
    hover_annotation_style: str = DEFAULT_HOVER_ANNOTATION_STYLE,
) -> go.Figure:
    fig = go.Figure()
    channels = [column for column in residual_frame.columns if column != "Time"]
    metrics_by_channel = {str(metric["Channel"]): metric for metric in residual_metrics}
    tolerance_active = absolute_tolerance > 0 or relative_tolerance_pct > 0
    time_values = residual_frame["Time"].to_numpy(copy=False)
    traces: list[dict] = []
    for index, channel in enumerate(channels):
        color = list(PLOT_COLORS.values())[index % len(PLOT_COLORS)]
        metric = metrics_by_channel.get(channel, {})
        residual_values = residual_frame[channel].to_numpy(dtype=float)
        traces.append(
            _line_trace(
                time_values,
                residual_values,
                f"{channel} residual",
                line={"color": color, "width": 1.8},
                hovertemplate=(
                    "Time: %{x}<br>Residual: %{y}<br>"
                    f"Mean bias: {float(metric.get('Mean Bias', 0.0)):.4g}<br>"
                    f"MAE: {float(metric.get('MAE', 0.0)):.4g}<extra>{channel}</extra>"
                ),
            )
        )
        if not tolerance_active or reference_frame is None or channel not in reference_frame:
            continue
        if len(reference_frame[channel]) != len(residual_values):
            continue
        reference_values = reference_frame[channel].to_numpy(dtype=float)
        tolerance_band = np.maximum(absolute_tolerance, np.abs(reference_values) * relative_tolerance_pct / 100.0)
        outside = np.abs(residual_values) > tolerance_band
        for sign, name in [(1, "upper tolerance"), (-1, "lower tolerance")]:
            traces.append(
                _line_trace(
                    time_values,
                    tolerance_band * sign,
                    f"{channel} {name}",
                    line={"color": color, "width": 1.0, "dash": "dot"},
                    opacity=0.55,
                    hovertemplate="Time: %{x}<br>Tolerance: %{y}<extra>" + channel + "</extra>",
                )
            )
        traces.append(
            _line_trace(
                time_values[outside],
                residual_values[outside],
                f"{channel} outside tolerance",
                mode="markers",
                marker={"color": PLOT_COLORS["red"], "size": 7, "symbol": "x"},
                hovertemplate="Time: %{x}<br>Residual: %{y}<br>Outside tolerance<extra>" + channel + "</extra>",
            )
        )
    if traces:
        fig.add_traces(traces)
    fig.add_hline(y=0, line_dash="dash", line_color="#526070", opacity=0.7)
    fig = _apply_common_layout(
        fig,
        f"Residual Diagnostics - {target_name} minus {reference_name}",
        "Time",
        "Residual",
        legend_position=legend_position,
        hover_annotation_style=hover_annotation_style,
    )
    return _as_resampled_figure(fig)


def build_rolling_metrics_figure(
    rolling_frame: pd.DataFrame,
    window_size: int,
    *,
    legend_position: str = DEFAULT_LEGEND_POSITION,
    hover_annotation_style: str = DEFAULT_HOVER_ANNOTATION_STYLE,
) -> go.Figure:
    fig = go.Figure()
    metric_colors = {
        "Rolling RMSE": PLOT_COLORS["cyan"],
        "Rolling Bias": PLOT_COLORS["purple"],
        "Rolling Pearson R": PLOT_COLORS["teal"],
        "Rolling Sign Agreement": PLOT_COLORS["green"],
    }
    metric_dashes = {
        "Rolling RMSE": "solid",
        "Rolling Bias": "dash",
        "Rolling Pearson R": "dot",
        "Rolling Sign Agreement": "dashdot",
    }
    time_values = rolling_frame["Time"].to_numpy(copy=False)
    traces: list[dict] = []
    for column in [column for column in rolling_frame.columns if column != "Time"]:
        metric_name = next((name for name in metric_colors if column.endswith(name)), "Rolling Metric")
        traces.append(
            _line_trace(
                time_values,
                rolling_frame[column].to_numpy(copy=False),
                column,
                line={"color": metric_colors.get(metric_name, PLOT_COLORS["slate"]), "dash": metric_dashes.get(metric_name, "solid")},
            )
        )
    if traces:
        fig.add_traces(traces)
    fig = _apply_common_layout(
        fig,
        f"Rolling Diagnostics - {window_size} sample window",
        "Time",
        "Rolling Metric Value",
        legend_position=legend_position,
        hover_annotation_style=hover_annotation_style,
    )
    return _as_resampled_figure(fig)


def build_lag_figure(
    correlations: pd.DataFrame,
    lag_metrics: list[dict[str, float | str]],
    *,
    legend_position: str = DEFAULT_LEGEND_POSITION,
    hover_annotation_style: str = DEFAULT_HOVER_ANNOTATION_STYLE,
) -> go.Figure:
    fig = go.Figure()
    best_by_channel = {str(metric["Channel"]): metric for metric in lag_metrics}
    lag_seconds = correlations["Lag (s)"].to_numpy(copy=False)
    traces: list[dict] = []
    shapes: list[dict] = []
    for index, channel in enumerate([column for column in correlations.columns if column not in {"Lag (samples)", "Lag (s)"}]):
        color = list(PLOT_COLORS.values())[index % len(PLOT_COLORS)]
        traces.append(
            _line_trace(
                lag_seconds,
                correlations[channel].to_numpy(copy=False),
                f"{channel} correlation",
                mode="lines+markers",
                line={"color": color},
            )
        )
        best = best_by_channel.get(channel)
        if best:
            best_lag = float(best["Best Lag (s)"])
            # Equivalent to fig.add_vline(...), but accumulated and applied in one
            # update_layout below. Calling add_vline per channel re-validates the whole
            # shapes tuple each time (O(n^2)); for hundreds of channels that alone cost
            # several seconds.
            shapes.append(
                {
                    "type": "line",
                    "x0": best_lag,
                    "x1": best_lag,
                    "xref": "x",
                    "y0": 0,
                    "y1": 1,
                    "yref": "y domain",
                    "line": {"color": color, "dash": "dot"},
                    "opacity": 0.45,
                }
            )
    if traces:
        fig.add_traces(traces)
    if shapes:
        fig.update_layout(shapes=shapes)
    fig = _apply_common_layout(
        fig,
        "Lag / Phase Diagnostics",
        "Lag (s)",
        "Correlation",
        legend_position=legend_position,
        hover_annotation_style=hover_annotation_style,
    )
    return _as_resampled_figure(fig)


def build_events_figure(event_metrics: list[dict[str, float | str]]) -> go.Figure:
    values = [[row.get(column, "") for row in event_metrics] for column in [
        "Channel",
        "Event",
        "Reference Count",
        "Target Count",
        "Mean Timing Error (s)",
        "Max Timing Error (s)",
        "Count Difference",
    ]]
    fig = go.Figure(
        data=[
            go.Table(
                header={"values": ["Channel", "Event", "Reference", "Target", "Mean Error (s)", "Max Error (s)", "Count Delta"], "fill_color": "#e8eef5"},
                cells={"values": values, "fill_color": "#ffffff", "height": 24},
            )
        ]
    )
    fig.update_layout(
        title={"text": "Event Timing Diagnostics", "x": 0.02, "xanchor": "left", "font": {"size": 16}},
        margin={"l": 24, "r": 24, "t": 58, "b": 24},
        paper_bgcolor="#ffffff",
        font={"family": "Segoe UI, Arial, sans-serif", "size": 12, "color": "#24313f"},
    )
    return fig


def build_data_quality_figure(rows: list[dict[str, float | str]]) -> go.Figure:
    columns = [
        "Dataset",
        "Channel",
        "Warning Count",
        "NaN Count",
        "Inf Count",
        "Duplicate Timestamps",
        "Time Step Jitter (%)",
        "Flatline Segments",
        "Clipping Candidates",
        "Spike Count",
    ]
    values = [[row.get(column, "") for row in rows] for column in columns]
    warning_colors = ["#fbe9e9" if float(row.get("Warning Count", 0)) else "#ffffff" for row in rows]
    fig = go.Figure(
        data=[
            go.Table(
                header={"values": columns, "fill_color": "#e8eef5"},
                cells={"values": values, "fill_color": [warning_colors] * len(columns), "height": 24},
            )
        ]
    )
    fig.update_layout(
        title={"text": "Data Quality Checks", "x": 0.02, "xanchor": "left", "font": {"size": 16}},
        margin={"l": 24, "r": 24, "t": 58, "b": 24},
        paper_bgcolor="#ffffff",
        font={"family": "Segoe UI, Arial, sans-serif", "size": 12, "color": "#24313f"},
    )
    return fig


def _decimate_calibration_cloud(
    x: np.ndarray, y: np.ndarray, cap: int
) -> tuple[np.ndarray, np.ndarray]:
    """Thin a calibration marker cloud to ``cap`` points, preserving its envelope.

    Uniform-stride index sampling plus mandatory retention of the four extreme points
    (min/max of x and y), so the visible extent of the cloud is unchanged. The returned
    arrays are an exact subset of the inputs (no interpolated/synthetic points). The fit
    and identity lines are computed from the FULL data by the caller and are unaffected.
    """
    n = len(x)
    if n <= cap:
        return x, y
    keep = np.linspace(0, n - 1, cap).round().astype(np.int64)
    finite = np.isfinite(x) & np.isfinite(y)
    if finite.any():
        finite_idx = np.flatnonzero(finite)
        extremes = np.array(
            [
                finite_idx[np.argmin(x[finite_idx])],
                finite_idx[np.argmax(x[finite_idx])],
                finite_idx[np.argmin(y[finite_idx])],
                finite_idx[np.argmax(y[finite_idx])],
            ],
            dtype=np.int64,
        )
        keep = np.concatenate([keep, extremes])
    idx = np.unique(keep)
    return x[idx], y[idx]


def build_calibration_figure(
    reference_df: pd.DataFrame,
    target_df: pd.DataFrame,
    calibration_metrics: list[dict[str, float | str]],
    reference_name: str,
    target_name: str,
    *,
    legend_position: str = DEFAULT_LEGEND_POSITION,
    hover_annotation_style: str = DEFAULT_HOVER_ANNOTATION_STYLE,
) -> go.Figure:
    fig = go.Figure()
    metrics_by_channel = {str(metric["Channel"]): metric for metric in calibration_metrics}
    traces: list[dict] = []
    for index, channel in enumerate([column for column in reference_df.columns if column != "Time"]):
        color = list(PLOT_COLORS.values())[index % len(PLOT_COLORS)]
        reference_series = reference_df[channel]
        x = reference_series.to_numpy(dtype=float)
        y = target_df[channel].to_numpy(dtype=float)
        x_dec, y_dec = _decimate_calibration_cloud(x, y, CALIB_SCATTER_POINT_CAP)
        traces.append(
            _line_trace(
                x_dec,
                y_dec,
                f"{channel} samples",
                mode="markers",
                marker={"color": color, "size": 6, "opacity": 0.65},
            )
        )
        metric = metrics_by_channel[channel]
        x_line = [float(reference_series.min()), float(reference_series.max())]
        slope = float(metric["Calibration Slope"])
        offset = float(metric["Calibration Offset"])
        if pd.notna(slope) and pd.notna(offset):
            traces.append(
                _line_trace(
                    [x_line[0], x_line[1]],
                    [slope * x_line[0] + offset, slope * x_line[1] + offset],
                    f"{channel} fit",
                    line={"color": color, "dash": "dash"},
                )
            )
    all_reference = reference_df[[column for column in reference_df.columns if column != "Time"]].to_numpy().ravel()
    finite = all_reference[pd.notna(all_reference)]
    if len(finite):
        limits = [float(finite.min()), float(finite.max())]
        traces.append(
            _line_trace([limits[0], limits[1]], [limits[0], limits[1]], "Identity", line={"color": PLOT_COLORS["slate"], "dash": "dot"})
        )
    if traces:
        fig.add_traces(traces)
    fig = _apply_common_layout(
        fig,
        f"Calibration Scatter - {target_name} vs {reference_name}",
        f"{reference_name}",
        f"{target_name}",
        unified_hover=False,
        legend_position=legend_position,
        hover_annotation_style=hover_annotation_style,
    )
    return _as_resampled_figure(fig)


def build_frequency_figure(
    frequency_result: object,
    *,
    legend_position: str = DEFAULT_LEGEND_POSITION,
    hover_annotation_style: str = DEFAULT_HOVER_ANNOTATION_STYLE,
) -> go.Figure:
    available = bool(getattr(frequency_result, "available"))
    reason = str(getattr(frequency_result, "reason"))
    spectrum_frame = getattr(frequency_result, "spectrum_frame")
    fig = go.Figure()
    if not available:
        fig.add_annotation(text=reason, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font={"size": 14, "color": "#647386"})
    else:
        frequency_values = spectrum_frame["Frequency"].to_numpy(copy=False)
        traces = [
            _line_trace(
                frequency_values,
                spectrum_frame[column].to_numpy(copy=False),
                column,
                line={"color": list(PLOT_COLORS.values())[index % len(PLOT_COLORS)]},
            )
            for index, column in enumerate([column for column in spectrum_frame.columns if column != "Frequency"])
        ]
        if traces:
            fig.add_traces(traces)
    fig = _apply_common_layout(
        fig,
        "Frequency Comparison",
        "Frequency",
        "Magnitude",
        unified_hover=False,
        legend_position=legend_position,
        hover_annotation_style=hover_annotation_style,
    )
    return _as_resampled_figure(fig)


def build_scale_offset_figure(
    metrics: list[dict[str, float | str]],
    reference_name: str,
    *,
    legend_position: str = DEFAULT_LEGEND_POSITION,
    hover_annotation_style: str = DEFAULT_HOVER_ANNOTATION_STYLE,
) -> go.Figure:
    channels = [str(metric["Channel"]) for metric in metrics]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=channels,
            y=[metric["Scale"] for metric in metrics],
            name="Scale",
            marker_color=PLOT_COLORS["blue"],
        )
    )
    fig.add_trace(
        go.Bar(
            x=channels,
            y=[metric["Offset"] for metric in metrics],
            name="Offset",
            marker_color=PLOT_COLORS["purple"],
        )
    )
    fig.add_hline(
        y=1,
        line_dash="dash",
        line_color=PLOT_COLORS["slate"],
        opacity=0.75,
        annotation_text="Scale = 1",
        annotation_position="top left",
    )
    return _apply_common_layout(
        fig,
        f"Scale and Offset Coefficients - {reference_name} as Reference",
        "Channel",
        "Coefficient Value",
        grouped_bars=True,
        legend_position=legend_position,
        hover_annotation_style=hover_annotation_style,
    )


def build_sign_agreement_plot_data(
    status_frame: pd.DataFrame,
    sign_metrics: list[dict[str, float | str]],
    reference_name: str,
    target_name: str,
    *,
    deadband: float = 0.0,
) -> SignAgreementPlotData:
    return SignAgreementPlotData(
        status_frame=status_frame.copy(),
        metrics=[dict(metric) for metric in sign_metrics],
        reference_name=reference_name,
        target_name=target_name,
        deadband=deadband,
    )


def build_sign_agreement_figure(
    status_frame: pd.DataFrame,
    sign_metrics: list[dict[str, float | str]],
    reference_name: str,
    target_name: str,
    *,
    deadband: float = 0.0,
    hover_annotation_style: str = DEFAULT_HOVER_ANNOTATION_STYLE,
) -> go.Figure:
    channels = [column for column in status_frame.columns if column != "Time"]
    status_labels = {-1: "Opposite sign", 0: "Deadband or zero", 1: "Same sign"}
    status_colors = {
        "Opposite": "#b64a4a",
        "Deadband": "#a7b4c2",
        "Same": "#3a8f5a",
    }
    status_matrix = status_frame[channels].to_numpy(dtype=int).T if channels else np.empty((0, len(status_frame)), dtype=int)
    z_values = np.clip(status_matrix + 1, 0, 2)
    status_text = np.empty(status_matrix.shape, dtype=object)
    status_text[status_matrix < 0] = status_labels[-1]
    status_text[status_matrix == 0] = status_labels[0]
    status_text[status_matrix > 0] = status_labels[1]

    agreement_lookup = {
        str(metric["Channel"]): (
            float(metric["Sign Agreement (%)"]),
            float(metric["Sign Mismatch (%)"]),
            float(metric["Sign Deadband (%)"]),
            float(metric["Longest Sign Mismatch (s)"]),
        )
        for metric in sign_metrics
    }
    summary_by_channel = [
        agreement_lookup.get(channel, (0.0, 0.0, 0.0, 0.0))
        for channel in channels
    ]
    summary_matrix = np.asarray(summary_by_channel, dtype=float) if summary_by_channel else np.empty((0, 4), dtype=float)
    hover_summary = np.empty((len(channels), len(status_frame), 5), dtype=object)
    if len(channels) and len(status_frame):
        hover_summary[:, :, 0] = status_text
        for summary_index in range(4):
            hover_summary[:, :, summary_index + 1] = summary_matrix[:, summary_index, None]

    fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "heatmap"}, {"type": "table"}]],
        column_widths=[0.74, 0.26],
        horizontal_spacing=0.045,
    )
    fig.add_trace(
        go.Heatmap(
            x=status_frame["Time"],
            y=channels,
            z=z_values,
            zmin=0,
            zmax=2,
            colorscale=[
                [0.0, status_colors["Opposite"]],
                [0.333, status_colors["Opposite"]],
                [0.334, status_colors["Deadband"]],
                [0.666, status_colors["Deadband"]],
                [0.667, status_colors["Same"]],
                [1.0, status_colors["Same"]],
            ],
            showscale=False,
            xgap=1,
            ygap=5,
            customdata=hover_summary,
            hovertemplate=(
                "Time: %{x}<br>Channel: %{y}<br>"
                "Status: %{customdata[0]}<br>"
                "Same: %{customdata[1]:.1f}%<br>"
                "Opposite: %{customdata[2]:.1f}%<br>"
                "Deadband: %{customdata[3]:.1f}%<br>"
                "Max mismatch: %{customdata[4]:g}s<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )

    for label, color in [
        ("Same", status_colors["Same"]),
        ("Deadband", status_colors["Deadband"]),
        ("Opposite", status_colors["Opposite"]),
    ]:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker={"symbol": "square", "size": 11, "color": color},
                name=label,
                hoverinfo="skip",
                showlegend=True,
            ),
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Table(
            columnwidth=[1.6, 0.9, 0.9, 0.9, 1.1],
            header={
                "values": ["Channel", "Same", "Opposite", "Deadband", "Max Mismatch"],
                "fill_color": "#e8eef5",
                "align": ["left", "right", "right", "right", "right"],
                "font": {"color": "#1e2a36", "size": 11},
                "height": 28,
            },
            cells={
                "values": [
                    channels,
                    [f"{values[0]:.1f}%" for values in summary_by_channel],
                    [f"{values[1]:.1f}%" for values in summary_by_channel],
                    [f"{values[2]:.1f}%" for values in summary_by_channel],
                    [f"{values[3]:g}s" for values in summary_by_channel],
                ],
                "fill_color": "#ffffff",
                "align": ["left", "right", "right", "right", "right"],
                "font": {"color": "#24313f", "size": 10},
                "height": 25,
            },
        ),
        row=1,
        col=2,
    )

    if deadband == 0:
        subtitle = "Zero-valued samples are shown as deadband/neutral. Increase the deadband to ignore small noise around zero."
        fig.add_annotation(
            x=0.0,
            y=1.035,
            xref="paper",
            yref="paper",
            text=subtitle,
            showarrow=False,
            xanchor="left",
            align="left",
            font={"size": 10, "color": "#647386"},
        )

    hover_layout = _hover_layout(False, hover_annotation_style)
    fig.update_layout(
        title={
            "text": f"Sign Agreement - {reference_name} vs {target_name} (deadband +/- {deadband:g})",
            "x": 0.02,
            "xanchor": "left",
            "font": {"size": 16},
        },
        template="plotly_white",
        autosize=True,
        showlegend=True,
        legend={
            "orientation": "h",
            "x": 0.0,
            "y": 1.105,
            "xanchor": "left",
            "yanchor": "bottom",
            "font": {"size": 11},
            "itemsizing": "constant",
        },
        margin={"l": 110, "r": 24, "t": 92, "b": 58},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8fafc",
        font={"family": "Segoe UI, Arial, sans-serif", "size": 12, "color": "#24313f"},
        hovermode=hover_layout["hovermode"],
        hoverlabel=hover_layout["hoverlabel"],
    )
    fig.update_xaxes(
        title="Time",
        showgrid=False,
        zeroline=False,
        linecolor="#cbd5df",
    )
    fig.update_yaxes(
        title="Channel",
        showgrid=False,
        zeroline=False,
        linecolor="#cbd5df",
        autorange="reversed",
    )
    return fig


def build_overlay_figure(
    reference_df: pd.DataFrame,
    target_df: pd.DataFrame,
    scaled_only_df: pd.DataFrame,
    offset_only_df: pd.DataFrame,
    scaled_offset_df: pd.DataFrame,
    reference_name: str,
    target_name: str,
    *,
    hide_transforms: bool = False,
    channels: Sequence[str] | None = None,
    render_mode: str = "auto",
    legend_position: str = DEFAULT_LEGEND_POSITION,
    hover_annotation_style: str = DEFAULT_HOVER_ANNOTATION_STYLE,
) -> go.Figure:
    started = perf_counter()
    all_columns = [column for column in reference_df.columns if column != "Time"]
    requested_channels = set(channels) if channels is not None else None
    columns = [column for column in all_columns if requested_channels is None or column in requested_channels]
    reference_label = _compact_source_label(reference_name, "Reference")
    target_label = _compact_source_label(target_name, "Checked")
    reference_time = reference_df["Time"].to_numpy(copy=False)
    target_time = target_df["Time"].to_numpy(copy=False)
    scaled_time = scaled_only_df["Time"].to_numpy(copy=False)
    offset_time = offset_only_df["Time"].to_numpy(copy=False)
    scaled_offset_time = scaled_offset_df["Time"].to_numpy(copy=False)
    trace_roles = 2 if hide_transforms else 5
    raw_points = max(
        len(reference_time),
        len(target_time),
        len(scaled_time),
        len(offset_time),
        len(scaled_offset_time),
    ) * len(columns) * trace_roles
    trace_type = _overlay_trace_type(render_mode, raw_points)
    traces = []
    time_arrays = (reference_time, target_time, scaled_time, offset_time, scaled_offset_time)
    register_hf_data = _can_register_overlay_hf_data(columns, time_arrays)
    fig = (
        FigureResampler(go.Figure(), default_n_shown_samples=DEFAULT_RESAMPLER_SAMPLES)
        if register_hf_data and FigureResampler is not None
        else go.Figure()
    )
    trace_count = 0

    def add_trace(x_values, y_values, **trace_kwargs) -> None:
        nonlocal trace_count
        trace = trace_type(**trace_kwargs)
        if register_hf_data:
            fig.add_trace(trace, hf_x=x_values, hf_y=y_values)
        else:
            trace.x = x_values
            trace.y = y_values
            traces.append(trace)
        trace_count += 1

    for index, column in enumerate(all_columns):
        if requested_channels is not None and column not in requested_channels:
            continue
        base_color = (
            SG_OVERLAY_COLORS[index % len(SG_OVERLAY_COLORS)]
            if hide_transforms
            else list(PLOT_COLORS.values())[index % len(PLOT_COLORS)]
        )
        target_line = (
            {"color": base_color, "width": 1.6, "dash": "dash"}
            if hide_transforms
            else {"color": PLOT_COLORS["slate"], "width": 1.6}
        )
        add_trace(
            reference_time,
            reference_df[column].to_numpy(copy=False),
            mode="lines",
            name=f"{reference_label} - {column}",
            legendgroup=column,
            meta={"overlay_channel": column, "overlay_role": "reference"},
            line={"color": base_color, "width": 2.1},
        )
        add_trace(
            target_time,
            target_df[column].to_numpy(copy=False),
            mode="lines",
            name=f"{target_label} - {column}" if hide_transforms else f"{target_label} Original - {column}",
            legendgroup=column,
            meta={"overlay_channel": column, "overlay_role": "target"},
            line=target_line,
        )
        if not hide_transforms:
            add_trace(
                scaled_time,
                scaled_only_df[column].to_numpy(copy=False),
                mode="lines",
                name=f"{target_label} Scaled - {column}",
                legendgroup=column,
                meta={"overlay_channel": column, "overlay_role": "scaled"},
                line={"color": PLOT_COLORS["green"], "dash": "dash"},
            )
            add_trace(
                offset_time,
                offset_only_df[column].to_numpy(copy=False),
                mode="lines",
                name=f"{target_label} Offset - {column}",
                legendgroup=column,
                meta={"overlay_channel": column, "overlay_role": "offset"},
                line={"color": PLOT_COLORS["amber"], "dash": "dashdot"},
            )
            add_trace(
                scaled_offset_time,
                scaled_offset_df[column].to_numpy(copy=False),
                mode="lines",
                name=f"{target_label} Scaled + Offset - {column}",
                legendgroup=column,
                meta={"overlay_channel": column, "overlay_role": "scaled_offset"},
                line={"color": PLOT_COLORS["purple"], "dash": "longdash"},
            )
    if traces:
        fig.add_traces(traces)

    fig = _apply_common_layout(
        fig,
        f"Overlay Plot - Reference: {reference_label}, Checked: {target_label}",
        "Time",
        "Sensor Value",
        legend_position=legend_position,
        hover_annotation_style=hover_annotation_style,
    )
    result = fig if register_hf_data else _as_resampled_figure(fig)
    LOGGER.info(
        "Built overlay figure in %.3fs (%d/%d channels, %d traces, %d raw points, %s, hf=%s)",
        perf_counter() - started,
        len(columns),
        len(all_columns),
        trace_count,
        raw_points,
        trace_type.__name__,
        register_hf_data,
    )
    return result


def apply_overlay_channel_visibility(figure: go.Figure, channels: Sequence[str] | None) -> tuple[bool, ...]:
    visible_channels = set(channels) if channels is not None else None
    mask: list[bool] = []
    for trace in figure.data:
        meta = getattr(trace, "meta", None)
        channel = meta.get("overlay_channel") if isinstance(meta, dict) else None
        visible = visible_channels is None or channel is None or channel in visible_channels
        trace.visible = visible
        mask.append(visible)
    return tuple(mask)
