from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from scipy.stats import linregress


TIME_COLUMN = "Time"
PAD_VALUE = 1e-8


class SensorDataError(ValueError):
    """Raised when sensor comparison inputs are not usable."""


@dataclass(frozen=True)
class DatasetSpec:
    path: Path
    display_name: str
    frame: pd.DataFrame

    @property
    def channels(self) -> list[str]:
        return [column for column in self.frame.columns if column != TIME_COLUMN]

    @property
    def row_count(self) -> int:
        return int(len(self.frame))

    @property
    def time_min(self) -> float:
        return float(self.frame[TIME_COLUMN].min())

    @property
    def time_max(self) -> float:
        return float(self.frame[TIME_COLUMN].max())


@dataclass(frozen=True)
class MainCompOverlayPairs:
    dataset1_columns: tuple[str, ...]
    dataset2_columns: tuple[str, ...]
    final_names: tuple[str, ...]
    ignored_columns: tuple[str, ...]


@dataclass(frozen=True)
class ColumnMatch:
    dataset1_column: str
    dataset2_column: str
    final_name: str


@dataclass(frozen=True)
class PreparedComparison:
    dataset1: DatasetSpec
    dataset2: DatasetSpec
    matches: tuple[ColumnMatch, ...]
    dataset1_prepared: pd.DataFrame
    dataset2_prepared: pd.DataFrame
    dataset1_aligned: pd.DataFrame
    dataset2_aligned: pd.DataFrame

    @property
    def channels(self) -> list[str]:
        return [column for column in self.dataset1_aligned.columns if column != TIME_COLUMN]

    @property
    def time_min(self) -> float:
        return float(self.dataset1_aligned[TIME_COLUMN].min())

    @property
    def time_max(self) -> float:
        return float(self.dataset1_aligned[TIME_COLUMN].max())


@dataclass(frozen=True)
class SignAgreementResult:
    metrics: list[dict[str, float | str]]
    status_frame: pd.DataFrame


@dataclass(frozen=True)
class ResidualDiagnosticsResult:
    metrics: list[dict[str, float | str]]
    residual_frame: pd.DataFrame


@dataclass(frozen=True)
class RollingDiagnosticsResult:
    window_size: int
    frame: pd.DataFrame


@dataclass(frozen=True)
class LagDiagnosticsResult:
    metrics: list[dict[str, float | str]]
    correlations: pd.DataFrame


@dataclass(frozen=True)
class EventDiagnosticsResult:
    metrics: list[dict[str, float | str]]


@dataclass(frozen=True)
class DataQualityResult:
    rows: list[dict[str, float | str]]


@dataclass(frozen=True)
class CalibrationDiagnosticsResult:
    metrics: list[dict[str, float | str]]


@dataclass(frozen=True)
class FrequencyDiagnosticsResult:
    available: bool
    reason: str
    metrics: list[dict[str, float | str]]
    spectrum_frame: pd.DataFrame


@dataclass(frozen=True)
class MetricDiagnostics:
    sign: SignAgreementResult
    residual: ResidualDiagnosticsResult
    lag: LagDiagnosticsResult
    events: EventDiagnosticsResult
    quality: DataQualityResult
    calibration: CalibrationDiagnosticsResult
    frequency: FrequencyDiagnosticsResult


def display_name_from_path(path: str | Path, fallback: str) -> str:
    stem = Path(path).stem.strip()
    return stem or fallback


def load_dataset(path: str | Path, display_name: str = "") -> DatasetSpec:
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise SensorDataError(f"Dataset file does not exist: {dataset_path}")
    if not dataset_path.is_file():
        raise SensorDataError(f"Dataset path is not a file: {dataset_path}")

    frame = _read_dataset_frame(dataset_path)
    validate_dataset_frame(frame, dataset_path.name)
    name = display_name.strip() or display_name_from_path(dataset_path, dataset_path.name)
    return DatasetSpec(path=dataset_path, display_name=name, frame=frame)


def _read_dataset_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".html", ".htm"}:
        return _read_plotly_html_frame(path)
    return pd.read_csv(path)


def _read_plotly_html_frame(path: Path) -> pd.DataFrame:
    try:
        html_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        html_text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SensorDataError(f"Could not read Plotly HTML dataset {path.name}: {exc}") from exc

    data_candidates: list[list[dict[str, Any]]] = []
    for args in _iter_plotly_new_plot_args(html_text):
        if len(args) < 2:
            continue
        try:
            data_arg = json.loads(args[1])
        except json.JSONDecodeError:
            continue
        if isinstance(data_arg, list):
            traces = [trace for trace in data_arg if isinstance(trace, dict)]
            if traces:
                data_candidates.append(traces)

    # A Plotly HTML file can contain more than one ``Plotly.newPlot`` call (the
    # real data plot plus library/template artifacts). Try the data plots in
    # reverse document order — the real figure is emitted last — and don't let
    # one candidate that raises abort the search for a usable one.
    first_trace_error: SensorDataError | None = None
    for traces in reversed(data_candidates):
        try:
            frame = _plotly_traces_to_frame(traces)
        except SensorDataError as exc:
            if first_trace_error is None:
                first_trace_error = exc
            continue
        if frame is not None:
            return frame

    if first_trace_error is not None:
        raise first_trace_error
    raise SensorDataError(f"{path.name} does not contain usable Plotly trace data.")


def _iter_plotly_new_plot_args(html_text: str) -> list[list[str]]:
    argument_lists: list[list[str]] = []
    marker = "Plotly.newPlot("
    search_from = 0
    while True:
        call_start = html_text.find(marker, search_from)
        if call_start == -1:
            break
        args_start = call_start + len(marker)
        call_body = _extract_balanced_call_body(html_text, args_start)
        if call_body is not None:
            argument_lists.append(_split_top_level_arguments(call_body))
        search_from = args_start
    return argument_lists


def _extract_balanced_call_body(text: str, start: int) -> str | None:
    depth = 1
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start:index]
    return None


def _split_top_level_arguments(call_body: str) -> list[str]:
    args: list[str] = []
    depth = 0
    quote: str | None = None
    escaped = False
    arg_start = 0
    for index, char in enumerate(call_body):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in {"'", '"', "`"}:
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            args.append(call_body[arg_start:index].strip())
            arg_start = index + 1
    args.append(call_body[arg_start:].strip())
    return args


def _time_axes_align(reference: np.ndarray, candidate: np.ndarray, rel_tol: float = 1e-6) -> bool:
    """Return True when two trace x-axes describe the same Time sampling.

    The comparison is relative to the axis span so that axes which are physically
    identical but differ by floating-point noise (CSV round-trips, interpolation
    onto a "common" grid, float32 storage) are accepted, while genuinely
    different sampling (e.g. ``[0, 1]`` vs ``[0, 2]``) is still rejected.
    """
    if len(reference) != len(candidate):
        return False
    if len(reference) == 0:
        return True
    span = float(np.ptp(reference))
    tolerance = rel_tol * span if span > 0 else rel_tol
    return bool(np.max(np.abs(reference - candidate)) <= tolerance + 1e-9)


def _plotly_traces_to_frame(traces: list[dict[str, Any]]) -> pd.DataFrame | None:
    collected: list[tuple[str, np.ndarray, np.ndarray]] = []
    for trace_index, trace in enumerate(traces, start=1):
        x_values = _coerce_plotly_numeric_array(trace.get("x"))
        y_values = _coerce_plotly_numeric_array(trace.get("y"))
        if x_values is None or y_values is None:
            continue
        if len(x_values) != len(y_values):
            raise SensorDataError(
                f"Plotly trace {trace_index} has different x and y lengths."
            )
        collected.append((_plotly_trace_name(trace, trace_index), x_values, y_values))

    if not collected:
        return None

    reference_axis = collected[0][1]
    if all(_time_axes_align(reference_axis, axis) for _, axis, _ in collected):
        # Every trace already shares one Time axis (the common case).
        time_values = reference_axis
        series = [(name, y_values) for name, _, y_values in collected]
    else:
        # Traces are sampled at different time points. This is what
        # plotly-resampler produces: each channel is LTTB-downsampled
        # independently, so the curves share a time *range* but not the exact
        # sample points. Re-align them onto a shared grid instead of refusing
        # the file outright.
        time_values, series = _align_traces_to_common_axis(collected)

    unique_names = _deduplicate_names([name for name, _ in series])
    data: dict[str, Any] = {TIME_COLUMN: time_values}
    for name, (_, values) in zip(unique_names, series):
        data[name] = values
    return pd.DataFrame(data)


def _align_traces_to_common_axis(
    collected: list[tuple[str, np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, list[tuple[str, np.ndarray]]]:
    """Resample differently-sampled traces onto one shared Time grid.

    Traces must cover the same Time *range* (as plotly-resampler output does);
    genuinely unrelated axes (e.g. ``[0, 1]`` vs ``[0, 2]``) are rejected so the
    importer never silently fabricates data across incompatible time spans.
    """
    minimums = [float(np.min(axis)) for _, axis, _ in collected]
    maximums = [float(np.max(axis)) for _, axis, _ in collected]
    span = max(maximums) - min(minimums)
    range_tolerance = 1e-3 * span if span > 0 else 1e-3
    if (max(minimums) - min(minimums) > range_tolerance) or (
        max(maximums) - min(maximums) > range_tolerance
    ):
        raise SensorDataError(
            "All imported Plotly traces must share the same Time axis "
            "(the traces cover different time ranges and cannot be aligned)."
        )

    grid = np.unique(np.concatenate([axis for _, axis, _ in collected]))
    series: list[tuple[str, np.ndarray]] = []
    for name, axis, y_values in collected:
        order = np.argsort(axis, kind="stable")
        series.append((name, np.interp(grid, axis[order], y_values[order])))
    return grid, series


def _coerce_plotly_numeric_array(value: Any) -> np.ndarray | None:
    if isinstance(value, dict) and {"dtype", "bdata"}.issubset(value):
        try:
            raw_data = base64.b64decode(str(value["bdata"]))
            array = np.frombuffer(raw_data, dtype=np.dtype(str(value["dtype"])))
            if "shape" in value:
                array = array.reshape(tuple(value["shape"]))
        except Exception:
            return None
    else:
        try:
            array = np.asarray(value, dtype=float)
        except (TypeError, ValueError):
            return None

    if array.ndim != 1:
        return None
    try:
        numeric = array.astype(float, copy=False)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric).all():
        return None
    return np.asarray(numeric)


# plotly-resampler rewrites each trace name as
# ``<b ...>[R]</b> <original name> <i ...>~<bin size></i>``. Strip that wrapper
# back to the original channel name (which carries the Main:/Comp:/Δ/% markers
# the importer relies on) rather than the undecorated ``meta``, which the
# producer does not always populate with the same marker.
_RESAMPLER_PREFIX_RE = re.compile(r"<b[^>]*>\s*\[R\]\s*</b>\s*")
_RESAMPLER_SUFFIX_RE = re.compile(r"\s*<i[^>]*>\s*~[^<]*</i>\s*$")


def _plotly_trace_name(trace: dict[str, Any], trace_index: int) -> str:
    raw_name = trace.get("name")
    name = str(raw_name).strip() if raw_name is not None else ""
    if name and _RESAMPLER_PREFIX_RE.search(name):
        name = _RESAMPLER_SUFFIX_RE.sub("", _RESAMPLER_PREFIX_RE.sub("", name)).strip()
    if not name:
        meta = trace.get("meta")
        name = str(meta).strip() if meta is not None else ""
    if not name:
        name = f"Trace {trace_index}"
    if name.startswith("*"):
        name = name[1:].strip() or f"Trace {trace_index}"
    return name


def _deduplicate_names(names: Sequence[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique_names: list[str] = []
    for name in names:
        count = seen.get(name, 0) + 1
        seen[name] = count
        unique_names.append(name if count == 1 else f"{name} ({count})")
    return unique_names


def detect_main_comp_overlay_pairs(dataset: DatasetSpec) -> MainCompOverlayPairs:
    main_columns: dict[str, str] = {}
    comp_columns: dict[str, str] = {}
    ignored_columns: list[str] = []

    for column in dataset.channels:
        role, base_name = _main_comp_role_and_base(column)
        if role == "main":
            if base_name in main_columns:
                ignored_columns.append(column)
            else:
                main_columns[base_name] = column
        elif role == "comp":
            if base_name in comp_columns:
                ignored_columns.append(column)
            else:
                comp_columns[base_name] = column
        else:
            ignored_columns.append(column)

    final_names: list[str] = []
    dataset1_columns: list[str] = []
    dataset2_columns: list[str] = []
    for base_name, main_column in main_columns.items():
        comp_column = comp_columns.get(base_name)
        if comp_column is None:
            ignored_columns.append(main_column)
            continue
        final_names.append(base_name)
        dataset1_columns.append(main_column)
        dataset2_columns.append(comp_column)

    paired_columns = set(dataset1_columns) | set(dataset2_columns)
    for comp_column in comp_columns.values():
        if comp_column not in paired_columns:
            ignored_columns.append(comp_column)

    if not dataset1_columns:
        raise SensorDataError(
            "Load an SG Plotly HTML overlay containing matched Main:/Comp: channels, "
            "or switch to separate dataset inputs."
        )

    return MainCompOverlayPairs(
        dataset1_columns=tuple(dataset1_columns),
        dataset2_columns=tuple(dataset2_columns),
        final_names=tuple(final_names),
        ignored_columns=tuple(dict.fromkeys(ignored_columns)),
    )


def _main_comp_role_and_base(column: str) -> tuple[str, str]:
    clean_column = column.strip()
    for prefix, role in [("Main:", "main"), ("Comp:", "comp")]:
        if clean_column.startswith(prefix):
            base_name = clean_column[len(prefix):].strip()
            if base_name:
                return role, base_name
    return "", clean_column


def validate_dataset_frame(frame: pd.DataFrame, label: str = "dataset") -> None:
    if frame.empty:
        raise SensorDataError(f"{label} is empty.")
    if len(frame.columns) < 2:
        raise SensorDataError(f"{label} must contain a Time column and at least one sensor channel.")
    if frame.columns[0] != TIME_COLUMN:
        raise SensorDataError(f"The first column of {label} must be named 'Time'.")
    duplicate_columns = [
        column for column in frame.columns if list(frame.columns).count(column) > 1
    ]
    if duplicate_columns:
        names = ", ".join(sorted(set(map(str, duplicate_columns))))
        raise SensorDataError(f"{label} contains duplicate columns: {names}")
    _require_numeric(frame, [TIME_COLUMN], label)
    _require_numeric(frame, [column for column in frame.columns if column != TIME_COLUMN], label)
    if frame[TIME_COLUMN].isna().any():
        raise SensorDataError(f"{label} contains missing Time values.")
    if not frame[TIME_COLUMN].is_monotonic_increasing:
        raise SensorDataError(f"{label} Time values must be sorted in ascending order.")


def _require_numeric(frame: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    bad_columns = [
        column
        for column in columns
        if not pd.api.types.is_numeric_dtype(frame[column])
    ]
    if bad_columns:
        names = ", ".join(bad_columns)
        raise SensorDataError(f"{label} contains non-numeric values in: {names}")


def prepare_comparison(
    dataset1: DatasetSpec,
    dataset2: DatasetSpec,
    dataset1_columns: Sequence[str],
    dataset2_columns: Sequence[str],
    final_names: Sequence[str],
) -> PreparedComparison:
    validate_column_mapping(dataset1, dataset2, dataset1_columns, dataset2_columns, final_names)

    clean_final_names = [name.strip() for name in final_names]
    frame1 = dataset1.frame[[TIME_COLUMN, *dataset1_columns]].copy()
    frame2 = dataset2.frame[[TIME_COLUMN, *dataset2_columns]].copy()
    frame1.columns = [TIME_COLUMN, *clean_final_names]
    frame2.columns = [TIME_COLUMN, *clean_final_names]
    aligned1, aligned2 = interpolate_and_align(frame1, frame2)
    matches = tuple(
        ColumnMatch(left, right, final)
        for left, right, final in zip(dataset1_columns, dataset2_columns, clean_final_names)
    )
    return PreparedComparison(
        dataset1=dataset1,
        dataset2=dataset2,
        matches=matches,
        dataset1_prepared=frame1,
        dataset2_prepared=frame2,
        dataset1_aligned=aligned1,
        dataset2_aligned=aligned2,
    )


def validate_column_mapping(
    dataset1: DatasetSpec,
    dataset2: DatasetSpec,
    dataset1_columns: Sequence[str],
    dataset2_columns: Sequence[str],
    final_names: Sequence[str],
) -> None:
    if not dataset1_columns or not dataset2_columns:
        raise SensorDataError("At least one channel must be matched.")
    if len(dataset1_columns) != len(dataset2_columns):
        raise SensorDataError("The matched channel lists must have the same length.")
    if len(final_names) != len(dataset1_columns):
        raise SensorDataError("Every matched channel pair must have a final name.")

    missing_left = [column for column in dataset1_columns if column not in dataset1.channels]
    missing_right = [column for column in dataset2_columns if column not in dataset2.channels]
    if missing_left:
        raise SensorDataError(f"Dataset 1 is missing matched columns: {', '.join(missing_left)}")
    if missing_right:
        raise SensorDataError(f"Dataset 2 is missing matched columns: {', '.join(missing_right)}")

    clean_final_names = [name.strip() for name in final_names]
    if any(not name for name in clean_final_names):
        raise SensorDataError("Final channel names cannot be blank.")
    duplicates = sorted({name for name in clean_final_names if clean_final_names.count(name) > 1})
    if duplicates:
        raise SensorDataError(f"Final channel names must be unique: {', '.join(duplicates)}")


def interpolate_and_align(df1: pd.DataFrame, df2: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    max_time = min(df1[TIME_COLUMN].max(), df2[TIME_COLUMN].max())
    trimmed1 = df1[df1[TIME_COLUMN] <= max_time]
    trimmed2 = df2[df2[TIME_COLUMN] <= max_time]
    if len(trimmed1) < 2 or len(trimmed2) < 2:
        raise SensorDataError("Both datasets must contain at least two rows in the overlapping time range.")

    time_dense = (
        trimmed1[TIME_COLUMN].values
        if len(trimmed1) > len(trimmed2)
        else trimmed2[TIME_COLUMN].values
    )
    aligned1 = pd.DataFrame({TIME_COLUMN: time_dense})
    aligned2 = pd.DataFrame({TIME_COLUMN: time_dense})

    for column in columns_without_time(trimmed1):
        interpolator1 = interp1d(
            trimmed1[TIME_COLUMN],
            trimmed1[column],
            kind="linear",
            fill_value="extrapolate",
        )
        interpolator2 = interp1d(
            trimmed2[TIME_COLUMN],
            trimmed2[column],
            kind="linear",
            fill_value="extrapolate",
        )
        aligned1[column] = interpolator1(time_dense)
        aligned2[column] = interpolator2(time_dense)

    return aligned1, aligned2


def columns_without_time(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if column != TIME_COLUMN]


def filter_time_range(
    frame: pd.DataFrame,
    start_time: float,
    end_time: float,
    columns: Sequence[str],
) -> pd.DataFrame:
    validate_time_range(frame, start_time, end_time)
    if not columns:
        raise SensorDataError("Select at least one channel.")
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise SensorDataError(f"Unknown selected channels: {', '.join(missing)}")
    filtered = frame[(frame[TIME_COLUMN] >= start_time) & (frame[TIME_COLUMN] <= end_time)]
    if filtered.empty:
        raise SensorDataError("The selected time range contains no samples.")
    return filtered[[TIME_COLUMN, *columns]]


def validate_time_range(frame: pd.DataFrame, start_time: float, end_time: float) -> None:
    if start_time > end_time:
        raise SensorDataError("Start time must be less than or equal to end time.")
    if start_time < float(frame[TIME_COLUMN].min()) or end_time > float(frame[TIME_COLUMN].max()):
        raise SensorDataError("Selected time range is outside the aligned data range.")


def reference_target_frames(
    prepared: PreparedComparison,
    dataset1_aligned: pd.DataFrame,
    dataset2_aligned: pd.DataFrame,
    reference_index: int,
) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    if reference_index == 0:
        return dataset1_aligned, dataset2_aligned, prepared.dataset1.display_name, prepared.dataset2.display_name
    if reference_index == 1:
        return dataset2_aligned, dataset1_aligned, prepared.dataset2.display_name, prepared.dataset1.display_name
    raise SensorDataError("Reference dataset must be Dataset 1 or Dataset 2.")


def calculate_metric_diagnostics(
    reference_df: pd.DataFrame,
    target_df: pd.DataFrame,
    *,
    sign_deadband: float = 0.0,
) -> MetricDiagnostics:
    return MetricDiagnostics(
        sign=calculate_sign_agreement(reference_df, target_df, deadband=sign_deadband),
        residual=calculate_residual_diagnostics(reference_df, target_df),
        lag=calculate_lag_diagnostics(reference_df, target_df),
        events=calculate_event_timing_diagnostics(reference_df, target_df),
        quality=calculate_data_quality(reference_df, target_df),
        calibration=calculate_calibration_diagnostics(reference_df, target_df),
        frequency=calculate_frequency_diagnostics(reference_df, target_df),
    )


def _negligible_mask(
    reference_values: np.ndarray,
    target_values: np.ndarray,
    noise_floor: float,
) -> np.ndarray:
    """Samples where both channels are below the noise floor and can be ignored."""
    if noise_floor <= 0:
        return np.zeros(np.shape(reference_values), dtype=bool)
    return (np.abs(reference_values) <= noise_floor) & (np.abs(target_values) <= noise_floor)


def _within_tolerance_absolute_percent(
    reference_values: np.ndarray,
    target_values: np.ndarray,
    *,
    absolute_tolerance: float,
    noise_floor: float,
) -> float:
    """Percent of samples within the absolute difference band, or below the noise floor."""
    if absolute_tolerance <= 0 and noise_floor <= 0:
        return np.nan
    abs_error = np.abs(reference_values - target_values)
    within = abs_error <= absolute_tolerance
    within |= _negligible_mask(reference_values, target_values, noise_floor)
    return float(np.mean(within) * 100.0)


def _within_tolerance_relative_percent(
    reference_values: np.ndarray,
    target_values: np.ndarray,
    *,
    relative_tolerance_pct: float,
    noise_floor: float,
) -> float:
    """Percent of samples within rel_tol% of the reference magnitude, or below the noise floor."""
    if relative_tolerance_pct <= 0 and noise_floor <= 0:
        return np.nan
    abs_error = np.abs(reference_values - target_values)
    tolerance_band = np.abs(reference_values) * relative_tolerance_pct / 100.0
    within = abs_error <= tolerance_band
    within |= _negligible_mask(reference_values, target_values, noise_floor)
    return float(np.mean(within) * 100.0)


# ponytail: fixed screening thresholds; make them project-configurable only when a real certification plan needs that.
CERTIFICATION_MIN_SIGN_AGREEMENT = 90.0
CERTIFICATION_MIN_PEARSON = 0.90
CERTIFICATION_MAX_PEAK_ERROR_PCT = 25.0
CERTIFICATION_MAX_SLOPE_ERROR_PCT = 20.0
CERTIFICATION_MAX_ENVELOPE_NMAE_PCT = 20.0
CERTIFICATION_SIGNAL_FLOOR = 1e-12


def _safe_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return np.nan
    return result if np.isfinite(result) else np.nan


def _signed_peak(values: np.ndarray) -> float:
    if values.size == 0:
        return np.nan
    finite_mask = np.isfinite(values)
    if not finite_mask.any():
        return np.nan
    finite_values = values[finite_mask]
    return float(finite_values[int(np.argmax(np.abs(finite_values)))])


def _unit_score(value: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return float(min(1.0, max(0.0, value)))


def _inverse_error_score(value: float, limit: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return float(min(1.0, max(0.0, 1.0 - max(0.0, value) / limit)))


def _certification_screen_metrics(
    reference_values: np.ndarray,
    target_values: np.ndarray,
    *,
    pearson_corr: float,
    robust_nmae_pct: float,
    sign_agreement_pct: float,
    calibration_slope: float,
    calibration_offset: float,
    data_quality_hard_warnings: float,
    data_quality_soft_warnings: float,
) -> dict[str, float | str]:
    reference_peak = _signed_peak(reference_values)
    target_peak = _signed_peak(target_values)
    peak_error_pct = (
        abs(target_peak - reference_peak) / abs(reference_peak) * 100.0
        if np.isfinite(reference_peak) and abs(reference_peak) > CERTIFICATION_SIGNAL_FLOOR
        else np.nan
    )
    slope_error_pct = abs(calibration_slope - 1.0) * 100.0 if np.isfinite(calibration_slope) else np.nan
    hard_warnings = int(max(0.0, data_quality_hard_warnings)) if np.isfinite(data_quality_hard_warnings) else 0
    soft_warnings = int(max(0.0, data_quality_soft_warnings)) if np.isfinite(data_quality_soft_warnings) else 0

    # Hard excludes: the comparison is invalid or mathematically undefined, not merely "poor".
    # Only these gate eligibility.
    exclusion_reasons: list[str] = []
    if not np.isfinite(reference_peak) or abs(reference_peak) <= CERTIFICATION_SIGNAL_FLOOR:
        exclusion_reasons.append("Low reference signal")
    if hard_warnings:
        exclusion_reasons.append("Invalid samples (NaN/Inf)")

    # Penalty flags: surfaced in the Exclusion Reason column for transparency, but they only
    # cost score points below -- a single threshold miss never auto-rejects an otherwise-good
    # channel.
    penalty_flags: list[str] = []
    if not np.isfinite(sign_agreement_pct) or sign_agreement_pct < CERTIFICATION_MIN_SIGN_AGREEMENT:
        penalty_flags.append("Sign agreement < 90%")
    if not np.isfinite(pearson_corr) or pearson_corr < CERTIFICATION_MIN_PEARSON:
        penalty_flags.append("Pearson correlation < 0.90")
    if not np.isfinite(peak_error_pct) or peak_error_pct > CERTIFICATION_MAX_PEAK_ERROR_PCT:
        penalty_flags.append("Peak error > 25%")
    if not np.isfinite(slope_error_pct) or slope_error_pct > CERTIFICATION_MAX_SLOPE_ERROR_PCT:
        penalty_flags.append("Slope error > 20%")
    if not np.isfinite(robust_nmae_pct) or robust_nmae_pct > CERTIFICATION_MAX_ENVELOPE_NMAE_PCT:
        penalty_flags.append("Envelope NMAE > 20%")
    if soft_warnings:
        penalty_flags.append("Data quality warnings")

    # Continuous score (weights sum to 100). Each metric degrades smoothly via _unit_score /
    # _inverse_error_score, so the grade reflects how good the channel is rather than a binary
    # pass/fail on any one threshold.
    score = (
        _unit_score(pearson_corr) * 25.0
        + _inverse_error_score(peak_error_pct, CERTIFICATION_MAX_PEAK_ERROR_PCT) * 20.0
        + _inverse_error_score(slope_error_pct, CERTIFICATION_MAX_SLOPE_ERROR_PCT) * 15.0
        + _unit_score(sign_agreement_pct / 100.0) * 20.0
        + _inverse_error_score(robust_nmae_pct, CERTIFICATION_MAX_ENVELOPE_NMAE_PCT) * 10.0
        + max(0.0, 10.0 - 5.0 * soft_warnings)
    )
    if exclusion_reasons:
        grade = "Reject"
    elif score >= 90.0:
        grade = "A"
    elif score >= 75.0:
        grade = "B"
    else:
        grade = "C"

    if exclusion_reasons:
        exclusion_reason = "; ".join(exclusion_reasons)
    elif penalty_flags:
        # Eligible, but list the checks that cost score points so the cell never contradicts
        # the "Certification Eligible = Yes" column.
        exclusion_reason = "Eligible (review: " + "; ".join(penalty_flags) + ")"
    else:
        exclusion_reason = "Eligible"

    return {
        "Validation Role": "Unassigned",
        "Certification Eligible": "No" if exclusion_reasons else "Yes",
        "Exclusion Reason": exclusion_reason,
        "Peak Strain Test": reference_peak,
        "Peak Strain FEA": target_peak,
        "Peak Error (%)": float(peak_error_pct),
        "Slope Error (%)": float(slope_error_pct),
        "Offset (signal units)": calibration_offset,
        "Envelope NMAE (%)": robust_nmae_pct,
        "Structural Relevance": "Unassigned",
        "Certification Score": float(round(score, 3)),
        "Evidence Grade": grade,
    }


def update_metric_tolerances(
    metrics: Sequence[dict[str, float | str]],
    reference_df: pd.DataFrame,
    target_df: pd.DataFrame,
    *,
    absolute_tolerance: float = 0.0,
    relative_tolerance_pct: float = 0.0,
    noise_floor: float = 0.0,
) -> list[dict[str, float | str]]:
    if absolute_tolerance < 0:
        raise SensorDataError("Absolute tolerance must be non-negative.")
    if relative_tolerance_pct < 0:
        raise SensorDataError("Relative tolerance must be non-negative.")
    if noise_floor < 0:
        raise SensorDataError("Noise floor must be non-negative.")
    updated: list[dict[str, float | str]] = []
    for metric in metrics:
        row = dict(metric)
        column = str(row["Channel"])
        reference_values = reference_df[column].to_numpy(dtype=float)
        target_values = target_df[column].to_numpy(dtype=float)
        row["Within Tolerance Abs (%)"] = _within_tolerance_absolute_percent(
            reference_values,
            target_values,
            absolute_tolerance=absolute_tolerance,
            noise_floor=noise_floor,
        )
        row["Within Tolerance Rel (%)"] = _within_tolerance_relative_percent(
            reference_values,
            target_values,
            relative_tolerance_pct=relative_tolerance_pct,
            noise_floor=noise_floor,
        )
        updated.append(row)
    return updated


def calculate_statistical_metrics(
    reference_df: pd.DataFrame,
    target_df: pd.DataFrame,
    *,
    sign_deadband: float = 0.0,
    absolute_tolerance: float = 0.0,
    relative_tolerance_pct: float = 0.0,
    noise_floor: float = 0.0,
    diagnostics: MetricDiagnostics | None = None,
) -> list[dict[str, float | str]]:
    if absolute_tolerance < 0:
        raise SensorDataError("Absolute tolerance must be non-negative.")
    if relative_tolerance_pct < 0:
        raise SensorDataError("Relative tolerance must be non-negative.")
    if noise_floor < 0:
        raise SensorDataError("Noise floor must be non-negative.")
    if diagnostics is None:
        diagnostics = calculate_metric_diagnostics(reference_df, target_df, sign_deadband=sign_deadband)
    metrics_list: list[dict[str, float | str]] = []
    columns = columns_without_time(reference_df)
    dt = reference_df[TIME_COLUMN].iloc[1] - reference_df[TIME_COLUMN].iloc[0] if len(reference_df) > 1 else 0.0
    sign_metrics = {
        str(metric["Channel"]): metric
        for metric in diagnostics.sign.metrics
    }
    residual_metrics = {str(metric["Channel"]): metric for metric in diagnostics.residual.metrics}
    lag_metrics = {str(metric["Channel"]): metric for metric in diagnostics.lag.metrics}
    calibration_metrics = {
        str(metric["Channel"]): metric for metric in diagnostics.calibration.metrics
    }
    event_metrics = _summarize_event_metrics(diagnostics.events.metrics)
    quality_metrics = _summarize_quality_metrics(diagnostics.quality.rows)
    frequency_metrics = {str(metric["Channel"]): metric for metric in diagnostics.frequency.metrics}

    for column in columns:
        x = reference_df[column].values
        y = target_df[column].values
        if len(x) != len(y):
            raise SensorDataError(f"Channel {column} has mismatched sample counts.")

        x_std = np.std(x)
        y_std = np.std(y)
        if x_std == 0 or y_std == 0:
            max_corr = np.nan
            lag_at_max_corr = 0
        else:
            x_norm = (x - np.mean(x)) / x_std
            y_norm = (y - np.mean(y)) / y_std
            cross_corr = np.correlate(x_norm, y_norm, mode="full") / len(x)
            max_corr = float(np.max(cross_corr))
            lag_at_max_corr = int(np.argmax(cross_corr) - (len(x) - 1))

        time_shift_sec = lag_at_max_corr * dt
        mse = float(np.mean((x - y) ** 2))
        rmse = float(np.sqrt(mse))
        ss_total = np.sum((x - np.mean(x)) ** 2)
        ss_residual = np.sum((x - y) ** 2)
        r_squared = float(1 - (ss_residual / ss_total)) if ss_total != 0 else np.nan
        pearson_corr = float(np.corrcoef(x, y)[0, 1]) if x_std != 0 and y_std != 0 else np.nan
        abs_error = np.abs(x - y)

        with np.errstate(divide="ignore", invalid="ignore"):
            perc_error = np.where(x != 0, np.abs((x - y) / x) * 100, np.nan)
            smape = np.nanmean(2 * np.abs(x - y) / (np.abs(x) + np.abs(y)) * 100)
            wmape = np.sum(abs_error) / np.sum(np.abs(x)) * 100 if np.sum(np.abs(x)) != 0 else np.nan
        finite_perc_error = perc_error[np.isfinite(perc_error)]
        percentage_error = float(np.mean(finite_perc_error)) if finite_perc_error.size else np.nan
        within_tolerance_abs_pct = _within_tolerance_absolute_percent(
            x,
            y,
            absolute_tolerance=absolute_tolerance,
            noise_floor=noise_floor,
        )
        within_tolerance_rel_pct = _within_tolerance_relative_percent(
            x,
            y,
            relative_tolerance_pct=relative_tolerance_pct,
            noise_floor=noise_floor,
        )
        robust_reference_scale = max(
            float(np.percentile(x, 95) - np.percentile(x, 5)),
            float(np.median(np.abs(x))),
        )
        robust_nmae_pct = (
            float(np.mean(abs_error) / robust_reference_scale * 100.0)
            if robust_reference_scale != 0
            else np.nan
        )

        sign_agreement_pct = _safe_float(sign_metrics[column]["Sign Agreement (%)"])
        calibration_slope = _safe_float(calibration_metrics[column]["Calibration Slope"])
        calibration_offset = _safe_float(calibration_metrics[column]["Calibration Offset"])
        quality_entry = quality_metrics.get(column, {"total": 0.0, "hard": 0.0, "soft": 0.0})
        data_quality_total = _safe_float(quality_entry.get("total", 0.0))
        data_quality_hard = _safe_float(quality_entry.get("hard", 0.0))
        data_quality_soft = _safe_float(quality_entry.get("soft", 0.0))
        row: dict[str, float | str] = {
            "Channel": column,
            "Max Correlation": max_corr,
            "Lag at Max Correlation (samples)": lag_at_max_corr,
            "Time Shift (s)": float(time_shift_sec),
            "MSE": mse,
            "RMSE": rmse,
            "Coefficient of Determination": r_squared,
            "Pearson Correlation": pearson_corr,
            "Absolute Error": float(abs_error.mean()),
            "Percentage Error": percentage_error,
            "SMAPE": float(smape),
            "WMAPE": float(wmape),
            "Within Tolerance Abs (%)": within_tolerance_abs_pct,
            "Within Tolerance Rel (%)": within_tolerance_rel_pct,
            "Robust NMAE (%)": robust_nmae_pct,
            "Sign Agreement (%)": sign_metrics[column]["Sign Agreement (%)"],
            "Sign Mismatch (%)": sign_metrics[column]["Sign Mismatch (%)"],
            "Sign Deadband (%)": sign_metrics[column]["Sign Deadband (%)"],
            "Polarity Score": sign_metrics[column]["Polarity Score"],
            "Longest Sign Mismatch (s)": sign_metrics[column]["Longest Sign Mismatch (s)"],
            "Mean Bias": residual_metrics[column]["Mean Bias"],
            "MAE": residual_metrics[column]["MAE"],
            "Max Abs Error": residual_metrics[column]["Max Abs Error"],
            "P95 Abs Error": residual_metrics[column]["P95 Abs Error"],
            "P99 Abs Error": residual_metrics[column]["P99 Abs Error"],
            "Best Lag (samples)": lag_metrics[column]["Best Lag (samples)"],
            "Best Lag (s)": lag_metrics[column]["Best Lag (s)"],
            "Max Lag Correlation": lag_metrics[column]["Max Lag Correlation"],
            "Calibration Slope": calibration_metrics[column]["Calibration Slope"],
            "Calibration Offset": calibration_metrics[column]["Calibration Offset"],
            "Calibration R^2": calibration_metrics[column]["Calibration R^2"],
            "Residual Std": calibration_metrics[column]["Residual Std"],
            "Mean Event Timing Error (s)": event_metrics.get(column, {}).get("Mean Event Timing Error (s)", np.nan),
            "Max Event Timing Error (s)": event_metrics.get(column, {}).get("Max Event Timing Error (s)", np.nan),
            "Event Count Delta": event_metrics.get(column, {}).get("Event Count Delta", np.nan),
            "Data Quality Warnings": data_quality_total,
            "Dominant Freq Delta": frequency_metrics.get(column, {}).get("Dominant Freq Delta", np.nan),
            "Spectral Energy Ratio": frequency_metrics.get(column, {}).get("Spectral Energy Ratio", np.nan),
        }
        row.update(
            _certification_screen_metrics(
                x,
                y,
                pearson_corr=pearson_corr,
                robust_nmae_pct=robust_nmae_pct,
                sign_agreement_pct=sign_agreement_pct,
                calibration_slope=calibration_slope,
                calibration_offset=calibration_offset,
                data_quality_hard_warnings=data_quality_hard,
                data_quality_soft_warnings=data_quality_soft,
            )
        )
        metrics_list.append(row)
    return metrics_list


def calculate_residual_diagnostics(reference_df: pd.DataFrame, target_df: pd.DataFrame) -> ResidualDiagnosticsResult:
    columns = columns_without_time(reference_df)
    residual_frame = pd.DataFrame({TIME_COLUMN: reference_df[TIME_COLUMN].to_numpy(dtype=float)})
    metrics: list[dict[str, float | str]] = []
    for column in columns:
        residual = target_df[column].to_numpy(dtype=float) - reference_df[column].to_numpy(dtype=float)
        abs_residual = np.abs(residual)
        residual_frame[column] = residual
        metrics.append(
            {
                "Channel": column,
                "Mean Bias": float(np.mean(residual)),
                "MAE": float(np.mean(abs_residual)),
                "Max Abs Error": float(np.max(abs_residual)),
                "P95 Abs Error": float(np.percentile(abs_residual, 95)),
                "P99 Abs Error": float(np.percentile(abs_residual, 99)),
            }
        )
    return ResidualDiagnosticsResult(metrics=metrics, residual_frame=residual_frame)


def default_rolling_window(sample_count: int) -> int:
    if sample_count <= 0:
        return 1
    return min(sample_count, max(5, int(round(sample_count * 0.05))))


def calculate_rolling_diagnostics(
    reference_df: pd.DataFrame,
    target_df: pd.DataFrame,
    *,
    sign_deadband: float = 0.0,
    window_size: int | None = None,
) -> RollingDiagnosticsResult:
    window = window_size or default_rolling_window(len(reference_df))
    window = max(1, min(window, len(reference_df)))
    min_periods = min(window, 2)
    result = pd.DataFrame({TIME_COLUMN: reference_df[TIME_COLUMN].to_numpy(dtype=float)})
    for column in columns_without_time(reference_df):
        reference = reference_df[column].astype(float)
        target = target_df[column].astype(float)
        residual = target - reference
        result[f"{column} Rolling RMSE"] = np.sqrt((residual**2).rolling(window, min_periods=min_periods).mean())
        result[f"{column} Rolling Bias"] = residual.rolling(window, min_periods=min_periods).mean()
        result[f"{column} Rolling Pearson R"] = reference.rolling(window, min_periods=min_periods).corr(target)
        reference_sign = pd.Series(_polarity(reference.to_numpy(dtype=float), sign_deadband))
        target_sign = pd.Series(_polarity(target.to_numpy(dtype=float), sign_deadband))
        valid = (reference_sign != 0) & (target_sign != 0)
        same = ((reference_sign == target_sign) & valid).astype(float)
        result[f"{column} Rolling Sign Agreement"] = same.rolling(window, min_periods=min_periods).mean() * 100.0
    return RollingDiagnosticsResult(window_size=window, frame=result)


def calculate_sign_agreement(
    reference_df: pd.DataFrame,
    target_df: pd.DataFrame,
    *,
    deadband: float = 0.0,
) -> SignAgreementResult:
    if deadband < 0:
        raise SensorDataError("Sign deadband must be non-negative.")
    if len(reference_df) != len(target_df):
        raise SensorDataError("Sign agreement requires aligned datasets with equal sample counts.")

    columns = columns_without_time(reference_df)
    time_values = reference_df[TIME_COLUMN].to_numpy(dtype=float)
    status_data: dict[str, np.ndarray] = {TIME_COLUMN: time_values}
    metrics: list[dict[str, float | str]] = []

    for column in columns:
        if column not in target_df.columns:
            raise SensorDataError(f"Target dataset is missing channel: {column}")
        reference_sign = _polarity(reference_df[column].to_numpy(dtype=float), deadband)
        target_sign = _polarity(target_df[column].to_numpy(dtype=float), deadband)
        valid_polarity = (reference_sign != 0) & (target_sign != 0)
        same_sign = valid_polarity & (reference_sign == target_sign)
        opposite_sign = valid_polarity & (reference_sign != target_sign)
        deadband_state = ~valid_polarity
        status = np.where(same_sign, 1, np.where(opposite_sign, -1, 0))
        status_data[column] = status
        sample_count = len(status)
        if sample_count == 0:
            agreement_pct = mismatch_pct = deadband_pct = polarity_score = np.nan
        else:
            agreement_pct = float(np.count_nonzero(same_sign) / sample_count * 100.0)
            mismatch_pct = float(np.count_nonzero(opposite_sign) / sample_count * 100.0)
            deadband_pct = float(np.count_nonzero(deadband_state) / sample_count * 100.0)
            polarity_score = float(np.mean(reference_sign * target_sign))
        metrics.append(
            {
                "Channel": column,
                "Sign Agreement (%)": agreement_pct,
                "Sign Mismatch (%)": mismatch_pct,
                "Sign Deadband (%)": deadband_pct,
                "Polarity Score": polarity_score,
                "Longest Sign Mismatch (s)": _longest_true_duration(time_values, opposite_sign),
            }
        )

    return SignAgreementResult(metrics=metrics, status_frame=pd.DataFrame(status_data))


def calculate_lag_diagnostics(
    reference_df: pd.DataFrame,
    target_df: pd.DataFrame,
    *,
    max_lag_samples: int | None = None,
) -> LagDiagnosticsResult:
    sample_count = len(reference_df)
    if sample_count < 2:
        raise SensorDataError("Lag diagnostics require at least two samples.")
    dt = _median_time_step(reference_df[TIME_COLUMN].to_numpy(dtype=float))
    max_lag = max_lag_samples if max_lag_samples is not None else max(1, int(round(sample_count * 0.10)))
    max_lag = max(1, min(max_lag, sample_count - 1))
    lags = np.arange(-max_lag, max_lag + 1)
    correlations = pd.DataFrame({"Lag (samples)": lags, "Lag (s)": lags * dt})
    metrics: list[dict[str, float | str]] = []
    for column in columns_without_time(reference_df):
        reference = reference_df[column].to_numpy(dtype=float)
        target = target_df[column].to_numpy(dtype=float)
        valid_values = _lagged_correlations(reference, target, lags)
        correlations[column] = valid_values
        if np.all(np.isnan(valid_values)):
            best_lag = 0
            best_corr = np.nan
        else:
            best_index = _best_lag_index(valid_values, lags)
            best_lag = int(lags[best_index])
            best_corr = float(valid_values[best_index])
        metrics.append(
            {
                "Channel": column,
                "Best Lag (samples)": best_lag,
                "Best Lag (s)": float(best_lag * dt),
                "Max Lag Correlation": best_corr,
            }
        )
    return LagDiagnosticsResult(metrics=metrics, correlations=correlations)


def calculate_event_timing_diagnostics(reference_df: pd.DataFrame, target_df: pd.DataFrame) -> EventDiagnosticsResult:
    rows: list[dict[str, float | str]] = []
    time_values = reference_df[TIME_COLUMN].to_numpy(dtype=float)
    for column in columns_without_time(reference_df):
        reference = reference_df[column].to_numpy(dtype=float)
        target = target_df[column].to_numpy(dtype=float)
        event_sets = {
            "Zero Crossing": (_zero_crossings(time_values, reference), _zero_crossings(time_values, target)),
            "Local Peak": (_local_extrema(time_values, reference, find_max=True), _local_extrema(time_values, target, find_max=True)),
            "Local Valley": (_local_extrema(time_values, reference, find_max=False), _local_extrema(time_values, target, find_max=False)),
        }
        for percentage in (10, 50, 90):
            threshold = float(np.nanmin(reference) + (np.nanmax(reference) - np.nanmin(reference)) * percentage / 100.0)
            event_sets[f"{percentage}% Threshold"] = (
                _threshold_crossings(time_values, reference, threshold),
                _threshold_crossings(time_values, target, threshold),
            )
        for event_name, (reference_events, target_events) in event_sets.items():
            paired_count = min(len(reference_events), len(target_events))
            timing_errors = (
                np.abs(np.array(target_events[:paired_count]) - np.array(reference_events[:paired_count]))
                if paired_count
                else np.array([], dtype=float)
            )
            rows.append(
                {
                    "Channel": column,
                    "Event": event_name,
                    "Reference Count": len(reference_events),
                    "Target Count": len(target_events),
                    "Mean Timing Error (s)": float(np.mean(timing_errors)) if len(timing_errors) else np.nan,
                    "Max Timing Error (s)": float(np.max(timing_errors)) if len(timing_errors) else np.nan,
                    "Count Difference": abs(len(reference_events) - len(target_events)),
                }
            )
    return EventDiagnosticsResult(metrics=rows)


def calculate_data_quality(
    reference_df: pd.DataFrame,
    target_df: pd.DataFrame,
    *,
    progress: Callable[[str], None] | None = None,
) -> DataQualityResult:
    rows: list[dict[str, float | str]] = []
    for dataset_name, frame in [("Reference", reference_df), ("Target", target_df)]:
        if progress is not None:
            progress(f"Checking {dataset_name} timestamps...")
        time_values = frame[TIME_COLUMN].to_numpy(dtype=float)
        duplicate_timestamps = int(pd.Series(time_values).duplicated().sum())
        jitter_pct = _time_step_jitter_percent(time_values)
        columns = columns_without_time(frame)
        for column_index, column in enumerate(columns, start=1):
            label = f"{dataset_name} channel {column_index}/{len(columns)}: {column}"
            values = frame[column].to_numpy(dtype=float)
            if progress is not None:
                progress(f"Checking {label} - NaN/Inf...")
            nan_count = int(np.isnan(values).sum())
            inf_count = int(np.isinf(values).sum())
            if progress is not None:
                progress(f"Checking {label} - flatlines...")
            flatline_segments = _flatline_segment_count(values)
            if progress is not None:
                progress(f"Checking {label} - clipping...")
            clipping_candidates = _clipping_candidate_count(values)
            if progress is not None:
                progress(f"Checking {label} - spikes...")
            spike_count = _spike_count(values)
            row = {
                "Dataset": dataset_name,
                "Channel": column,
                "NaN Count": nan_count,
                "Inf Count": inf_count,
                "Duplicate Timestamps": duplicate_timestamps,
                "Time Step Jitter (%)": jitter_pct,
                "Flatline Segments": flatline_segments,
                "Clipping Candidates": clipping_candidates,
                "Spike Count": spike_count,
            }
            row["Warning Count"] = float(
                int(row["NaN Count"] > 0)
                + int(row["Inf Count"] > 0)
                + int(row["Duplicate Timestamps"] > 0)
                + int(row["Time Step Jitter (%)"] > 1.0)
                + int(row["Flatline Segments"] > 0)
                + int(row["Clipping Candidates"] > 0)
                + int(row["Spike Count"] > 0)
            )
            rows.append(row)
    return DataQualityResult(rows=rows)


def calculate_calibration_diagnostics(reference_df: pd.DataFrame, target_df: pd.DataFrame) -> CalibrationDiagnosticsResult:
    metrics: list[dict[str, float | str]] = []
    for column in columns_without_time(reference_df):
        reference = reference_df[column].to_numpy(dtype=float)
        target = target_df[column].to_numpy(dtype=float)
        if np.std(reference) == 0:
            slope = np.nan
            offset = np.nan
            r_squared = np.nan
            residual_std = np.nan
        else:
            slope, offset, r_value, _, _ = linregress(reference, target)
            fitted = slope * reference + offset
            residual_std = float(np.std(target - fitted))
            r_squared = float(r_value**2)
        metrics.append(
            {
                "Channel": column,
                "Calibration Slope": float(slope),
                "Calibration Offset": float(offset),
                "Calibration R^2": r_squared,
                "Residual Std": residual_std,
            }
        )
    return CalibrationDiagnosticsResult(metrics=metrics)


def calculate_frequency_diagnostics(
    reference_df: pd.DataFrame,
    target_df: pd.DataFrame,
    *,
    jitter_tolerance_pct: float = 5.0,
) -> FrequencyDiagnosticsResult:
    time_values = reference_df[TIME_COLUMN].to_numpy(dtype=float)
    if len(time_values) < 4:
        return FrequencyDiagnosticsResult(False, "Frequency diagnostics require at least four samples.", [], pd.DataFrame())
    jitter_pct = _time_step_jitter_percent(time_values)
    if jitter_pct > jitter_tolerance_pct:
        return FrequencyDiagnosticsResult(
            False,
            f"Time step jitter is {jitter_pct:.2f}%, above the {jitter_tolerance_pct:g}% frequency limit.",
            [],
            pd.DataFrame(),
        )
    dt = _median_time_step(time_values)
    if dt <= 0:
        return FrequencyDiagnosticsResult(False, "Time step must be positive for frequency diagnostics.", [], pd.DataFrame())
    frequencies = np.fft.rfftfreq(len(time_values), d=dt)
    spectrum = pd.DataFrame({"Frequency": frequencies})
    metrics: list[dict[str, float | str]] = []
    for column in columns_without_time(reference_df):
        ref_mag = _fft_magnitude(reference_df[column].to_numpy(dtype=float))
        tgt_mag = _fft_magnitude(target_df[column].to_numpy(dtype=float))
        spectrum[f"{column} Reference"] = ref_mag
        spectrum[f"{column} Target"] = tgt_mag
        ref_peak = _dominant_frequency(frequencies, ref_mag)
        tgt_peak = _dominant_frequency(frequencies, tgt_mag)
        ref_energy = float(np.sum(ref_mag**2))
        tgt_energy = float(np.sum(tgt_mag**2))
        metrics.append(
            {
                "Channel": column,
                "Dominant Freq Ref": ref_peak,
                "Dominant Freq Target": tgt_peak,
                "Dominant Freq Delta": float(tgt_peak - ref_peak),
                "Spectral Energy Ratio": float(tgt_energy / ref_energy) if ref_energy else np.nan,
            }
        )
    return FrequencyDiagnosticsResult(True, "", metrics, spectrum)


def _polarity(values: np.ndarray, deadband: float) -> np.ndarray:
    return np.where(values > deadband, 1, np.where(values < -deadband, -1, 0))


def _longest_true_duration(time_values: np.ndarray, mask: np.ndarray) -> float:
    if len(time_values) == 0 or not np.any(mask):
        return 0.0
    positive_steps = np.diff(time_values)
    positive_steps = positive_steps[positive_steps > 0]
    sample_duration = float(np.median(positive_steps)) if len(positive_steps) else 0.0

    longest = 0.0
    start_index: int | None = None
    for index, is_active in enumerate(mask):
        if is_active and start_index is None:
            start_index = index
        at_last_sample = index == len(mask) - 1
        if start_index is not None and (not is_active or at_last_sample):
            end_index = index if is_active and at_last_sample else index - 1
            duration = float(time_values[end_index] - time_values[start_index] + sample_duration)
            longest = max(longest, duration)
            start_index = None
    return longest


def _median_time_step(time_values: np.ndarray) -> float:
    diffs = np.diff(time_values)
    diffs = diffs[diffs > 0]
    return float(np.median(diffs)) if len(diffs) else 0.0


def _lagged_correlation(reference: np.ndarray, target: np.ndarray, lag: int) -> float:
    if lag > 0:
        left = reference[:-lag]
        right = target[lag:]
    elif lag < 0:
        left = reference[-lag:]
        right = target[:lag]
    else:
        left = reference
        right = target
    if len(left) < 2 or np.std(left) == 0 or np.std(right) == 0:
        return np.nan
    return float(np.corrcoef(left, right)[0, 1])


def _lagged_correlations(reference: np.ndarray, target: np.ndarray, lags: np.ndarray) -> np.ndarray:
    if not np.isfinite(reference).all() or not np.isfinite(target).all():
        return np.array([_lagged_correlation(reference, target, int(lag)) for lag in lags], dtype=float)

    reference_sum = np.concatenate(([0.0], np.cumsum(reference)))
    target_sum = np.concatenate(([0.0], np.cumsum(target)))
    reference_sum_sq = np.concatenate(([0.0], np.cumsum(reference * reference)))
    target_sum_sq = np.concatenate(([0.0], np.cumsum(target * target)))
    values = np.full(len(lags), np.nan, dtype=float)

    for index, lag_value in enumerate(lags):
        lag = int(lag_value)
        if lag > 0:
            ref_start, ref_stop = 0, len(reference) - lag
            tgt_start, tgt_stop = lag, len(target)
        elif lag < 0:
            offset = -lag
            ref_start, ref_stop = offset, len(reference)
            tgt_start, tgt_stop = 0, len(target) - offset
        else:
            ref_start, ref_stop = 0, len(reference)
            tgt_start, tgt_stop = 0, len(target)

        count = ref_stop - ref_start
        if count < 2:
            continue

        ref_window_sum = reference_sum[ref_stop] - reference_sum[ref_start]
        tgt_window_sum = target_sum[tgt_stop] - target_sum[tgt_start]
        ref_window_sum_sq = reference_sum_sq[ref_stop] - reference_sum_sq[ref_start]
        tgt_window_sum_sq = target_sum_sq[tgt_stop] - target_sum_sq[tgt_start]
        ref_ss = ref_window_sum_sq - ref_window_sum * ref_window_sum / count
        tgt_ss = tgt_window_sum_sq - tgt_window_sum * tgt_window_sum / count
        if ref_ss <= 0 or tgt_ss <= 0:
            continue

        cross_sum = float(np.dot(reference[ref_start:ref_stop], target[tgt_start:tgt_stop]))
        covariance = cross_sum - ref_window_sum * tgt_window_sum / count
        values[index] = float(covariance / np.sqrt(ref_ss * tgt_ss))

    return values


def _best_lag_index(values: np.ndarray, lags: np.ndarray) -> int:
    best_value = float(np.nanmax(values))
    tied = np.flatnonzero(np.isclose(values, best_value, rtol=1e-12, atol=1e-12, equal_nan=False))
    if len(tied) == 0:
        return int(np.nanargmax(values))
    return int(tied[int(np.argmin(np.abs(lags[tied])))])


def _zero_crossings(time_values: np.ndarray, values: np.ndarray) -> list[float]:
    signs = np.sign(values)
    if len(signs) < 2:
        return []
    previous_signs = signs[:-1]
    current_signs = signs[1:]
    current_zero = current_signs == 0
    previous_zero = (~current_zero) & (previous_signs == 0)
    sign_change = (~current_zero) & (previous_signs != 0) & (previous_signs != current_signs)
    event_mask = current_zero | previous_zero | sign_change
    if not np.any(event_mask):
        return []

    x0 = time_values[:-1]
    x1 = time_values[1:]
    y0 = values[:-1]
    y1 = values[1:]
    event_times = np.empty(len(event_mask), dtype=float)
    event_times[current_zero] = x1[current_zero]
    event_times[previous_zero] = x0[previous_zero]

    crossing_denominator = np.abs(y0) + np.abs(y1)
    crossing_fraction = np.divide(
        np.abs(y0),
        crossing_denominator,
        out=np.zeros_like(crossing_denominator, dtype=float),
        where=crossing_denominator != 0,
    )
    event_times[sign_change] = x0[sign_change] + (x1[sign_change] - x0[sign_change]) * crossing_fraction[sign_change]
    return [float(value) for value in event_times[event_mask]]


def _threshold_crossings(time_values: np.ndarray, values: np.ndarray, threshold: float) -> list[float]:
    centered = values - threshold
    return _zero_crossings(time_values, centered)


def _local_extrema(time_values: np.ndarray, values: np.ndarray, *, find_max: bool) -> list[float]:
    if len(values) < 3:
        return []
    left = values[:-2]
    center = values[1:-1]
    right = values[2:]
    if find_max:
        event_indices = np.flatnonzero((center >= left) & (center >= right)) + 1
    else:
        event_indices = np.flatnonzero((center <= left) & (center <= right)) + 1
    return [float(value) for value in time_values[event_indices]]


def _time_step_jitter_percent(time_values: np.ndarray) -> float:
    diffs = np.diff(time_values)
    positive = diffs[diffs > 0]
    if len(positive) < 2:
        return 0.0
    median = float(np.median(positive))
    return float(np.std(positive) / median * 100.0) if median else 0.0


def _flatline_segment_count(values: np.ndarray, *, min_length: int = 3) -> int:
    if len(values) < min_length:
        return 0
    adjacent_equal = np.isclose(values[1:], values[:-1], rtol=1e-9, atol=1e-12)
    return _true_run_count(adjacent_equal, min_length=min_length - 1)


def _clipping_candidate_count(values: np.ndarray, *, min_length: int = 3) -> int:
    if len(values) < min_length:
        return 0
    if np.all(np.isnan(values)):
        return 0
    min_value = np.nanmin(values)
    max_value = np.nanmax(values)
    extrema = np.isclose(values, min_value) | np.isclose(values, max_value)
    adjacent_extrema_equal = (
        extrema[1:]
        & extrema[:-1]
        & np.isclose(values[1:], values[:-1], rtol=1e-9, atol=1e-12)
    )
    return _true_run_count(adjacent_extrema_equal, min_length=min_length - 1)


def _true_run_count(mask: np.ndarray, *, min_length: int) -> int:
    if len(mask) < min_length or not np.any(mask):
        return 0
    edges = np.diff(np.concatenate(([False], mask, [False])).astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    stops = np.flatnonzero(edges == -1)
    return int(np.count_nonzero(stops - starts >= min_length))


def _spike_count(values: np.ndarray) -> int:
    diffs = np.abs(np.diff(values))
    if len(diffs) < 3:
        return 0
    median = np.nanmedian(diffs)
    mad = np.nanmedian(np.abs(diffs - median))
    threshold = median + 6.0 * (mad if mad else np.nanstd(diffs))
    # On smooth / low-noise signals (typical of FEA output) the MAD collapses toward zero, so
    # the bare threshold flags ordinary signal variation as spikes. Floor it at a fraction of
    # the signal range: a genuine spike is a large single-step jump relative to the signal's
    # full amplitude, while a smooth ramp never clears this floor.
    finite = values[np.isfinite(values)]
    if finite.size:
        signal_range = float(np.nanmax(finite) - np.nanmin(finite))
        threshold = max(threshold, 0.05 * signal_range)
    return int(np.count_nonzero(diffs > threshold)) if np.isfinite(threshold) and threshold > 0 else 0


def _fft_magnitude(values: np.ndarray) -> np.ndarray:
    clean = np.nan_to_num(values.astype(float) - np.nanmean(values.astype(float)))
    return np.abs(np.fft.rfft(clean))


def _dominant_frequency(frequencies: np.ndarray, magnitude: np.ndarray) -> float:
    if len(frequencies) <= 1:
        return 0.0
    index = int(np.argmax(magnitude[1:]) + 1)
    return float(frequencies[index])


def _summarize_event_metrics(rows: list[dict[str, float | str]]) -> dict[str, dict[str, float]]:
    by_channel: dict[str, list[dict[str, float | str]]] = {}
    for row in rows:
        by_channel.setdefault(str(row["Channel"]), []).append(row)
    result: dict[str, dict[str, float]] = {}
    for channel, channel_rows in by_channel.items():
        mean_errors = [float(row["Mean Timing Error (s)"]) for row in channel_rows if not pd.isna(row["Mean Timing Error (s)"])]
        max_errors = [float(row["Max Timing Error (s)"]) for row in channel_rows if not pd.isna(row["Max Timing Error (s)"])]
        count_delta = sum(float(row["Count Difference"]) for row in channel_rows)
        result[channel] = {
            "Mean Event Timing Error (s)": float(np.mean(mean_errors)) if mean_errors else np.nan,
            "Max Event Timing Error (s)": float(np.max(max_errors)) if max_errors else np.nan,
            "Event Count Delta": float(count_delta),
        }
    return result


def _summarize_quality_metrics(rows: list[dict[str, float | str]]) -> dict[str, dict[str, float]]:
    # Per channel, split the summed warning count into "hard" defects (NaN/Inf -> the data is
    # invalid) and "soft" advisories (duplicate timestamps, jitter, flatline, clipping, spike
    # -> often benign features of real test/FEA traces). "total" preserves the original summed
    # value that the UI reads as "Data Quality Warnings".
    summary: dict[str, dict[str, float]] = {}
    for row in rows:
        channel = str(row["Channel"])
        entry = summary.setdefault(channel, {"total": 0.0, "hard": 0.0, "soft": 0.0})
        total = float(row["Warning Count"])
        hard = float(int(float(row["NaN Count"]) > 0) + int(float(row["Inf Count"]) > 0))
        entry["total"] += total
        entry["hard"] += hard
        entry["soft"] += max(0.0, total - hard)
    return summary


def calculate_scale_offset(predictor_df: pd.DataFrame, response_df: pd.DataFrame) -> list[dict[str, float | str]]:
    results: list[dict[str, float | str]] = []
    for column in columns_without_time(predictor_df):
        predictor = predictor_df[column].values
        response = response_df[column].values
        slope, intercept, _, _, _ = linregress(predictor, response)
        results.append({"Channel": column, "Scale": float(slope), "Offset": float(intercept)})
    return results


def apply_sample_shift(frame: pd.DataFrame, shift_seconds: float) -> tuple[pd.DataFrame, int]:
    if frame.empty:
        raise SensorDataError("Cannot shift an empty dataset.")
    if len(frame) < 2:
        raise SensorDataError("Not enough points to shift.")

    dt = frame[TIME_COLUMN].iloc[1] - frame[TIME_COLUMN].iloc[0]
    if dt == 0:
        raise SensorDataError("Cannot shift a dataset with zero time step.")
    shift_samples = int(round(shift_seconds / dt))
    if shift_samples == 0:
        return frame.copy(), 0

    row_count = len(frame)
    if abs(shift_samples) >= row_count:
        raise SensorDataError("Shift is too large for the dataset length.")

    shifted = frame.copy()
    data_columns = columns_without_time(frame)
    data_array = frame[data_columns].values

    if shift_samples > 0:
        pad_block = np.full((shift_samples, data_array.shape[1]), PAD_VALUE)
        shifted[data_columns] = np.vstack([pad_block, data_array[:-shift_samples]])
    else:
        shift_samples_abs = abs(shift_samples)
        pad_block = np.full((shift_samples_abs, data_array.shape[1]), PAD_VALUE)
        shifted[data_columns] = np.vstack([data_array[shift_samples_abs:], pad_block])

    return shifted, shift_samples


def build_overlay_transforms(
    reference_df: pd.DataFrame,
    target_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    scale_offset_metrics = calculate_scale_offset(reference_df, target_df)
    scaled_only_df = pd.DataFrame({TIME_COLUMN: target_df[TIME_COLUMN]})
    offset_only_df = pd.DataFrame({TIME_COLUMN: target_df[TIME_COLUMN]})
    scaled_offset_df = pd.DataFrame({TIME_COLUMN: target_df[TIME_COLUMN]})

    for metric in scale_offset_metrics:
        column = str(metric["Channel"])
        slope = float(metric["Scale"])
        intercept = float(metric["Offset"])
        scaled_only_df[column] = target_df[column] / slope if slope != 0 else np.nan
        offset_only_df[column] = target_df[column] - intercept
        scaled_offset_df[column] = target_df[column] / slope - intercept if slope != 0 else np.nan

    return scaled_only_df, offset_only_df, scaled_offset_df
