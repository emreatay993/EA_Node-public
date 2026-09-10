"""SG CSV <-> Plotly HTML converter (PyQt6 Fusion GUI).

Bidirectional, per-file 1:1 converter between the two artifact families produced
by ``plot_SG_calculations_FEA``:

* **CSV** -- the full data table written by ``write_full_data_to_csv``: a ``Time``
  column first, then one column per channel/result. Comparison columns keep their
  ``Delta`` / ``%`` prefixes verbatim. Encoding is ``utf-8-sig`` with no index.
* **Plotly HTML** -- a per *group x suffix* figure written via
  ``plotly.offline.plot``. Each figure is a set of ``Scattergl`` traces that share
  one ``Time`` x-axis; the x/y samples are embedded as base64 typed arrays.

The conversion is *lossless at the table level*: every trace name becomes a CSV
column header verbatim (including the ``*``, ``Delta``, ``%``, ``Main:`` and
``Comp:`` markers and the ``[ue] [MPa] [deg]`` unit suffixes) and vice-versa, so a
CSV -> HTML -> CSV (or HTML -> CSV -> HTML) round trip reproduces the same data.

The CSVs use ``SG_calculations``-style headers, so they are read directly by the
SG-annotations script (``examples/ANSYS_SG_Postprocessing/show_SG_annotations_*.py``).
A ``main_and_compared_data`` overlay (which carries both a ``Main:`` and a
``Comp:`` series) is split on import into **two** standalone CSVs --
``…__main.csv`` and ``…__compared_data.csv`` -- each with clean base
``SG<n>_<token>`` headers, so both datasets are independently annotation-readable.
For the remaining single-dataset families only ``compared_data``'s display-only
``*`` is stripped (and re-applied on the way back to HTML); ``Δ`` / ``%`` headers
are kept verbatim, as the annotator understands them.

The module is layered so the conversion engine has no Qt dependency and can be
exercised head-less by ``test_sg_csv_html_converter.py``; the GUI is a thin shell
on top of it.

Run the GUI::

    .\\venv\\Scripts\\python.exe scripts\\sg_csv_html_converter.py

Or convert from the command line (no Qt needed)::

    python scripts/sg_csv_html_converter.py --to-csv  fig.html      [out_dir]
    python scripts/sg_csv_html_converter.py --to-html table.csv     [out_dir]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Format constants (verified against plot_SG_calculations_FEA_v0.79.1.3.py)
# --------------------------------------------------------------------------- #

TIME_COLUMN = "Time"
CSV_ENCODING = "utf-8-sig"

# Plotly's qualitative "Light24" palette, inlined so the engine does not import
# plotly just to cycle colours. Order matches ``plotly.express.colors.qualitative.Light24``.
LIGHT24 = [
    "#FD3216", "#00FE35", "#6A76FC", "#FED4C4", "#FE00CE", "#0DF9FF",
    "#F6F926", "#FF9616", "#479B55", "#EEA6FB", "#DC587D", "#D626FF",
    "#6E899C", "#00B5F7", "#B68E00", "#C9FBE5", "#FF0092", "#22FFA7",
    "#E3EE9E", "#86CE00", "#BC7196", "#7E7DCD", "#FC6955", "#E48F72",
]

# Known export suffixes (the trailing ``__<suffix>`` token of an HTML filename).
SUFFIX_MAIN = "main"
SUFFIX_COMPARED = "compared_data"
SUFFIX_OVERLAY = "main_and_compared_data"
SUFFIX_COMPARISON = "comparison"
SUFFIX_COMPARISON_PCT = "comparison_percent"

# Ordered longest-first so ``main_and_compared_data`` is matched before ``main``
# and ``compared_data`` when scanning a filename.
KNOWN_SUFFIXES = [
    SUFFIX_OVERLAY,
    SUFFIX_COMPARISON_PCT,
    SUFFIX_COMPARED,
    SUFFIX_COMPARISON,
    SUFFIX_MAIN,
]

FILENAME_PREFIX = "SG_Calculations"

_HOVER_DATA = "%{meta}<br>Time = %{x:.2f} s<br>Data = %{y:.1f}<extra></extra>"
_HOVER_PERCENT = "%{meta}<br>Time = %{x:.2f} s<br>Data = %{y:.1f}%<extra></extra>"


@dataclass(frozen=True)
class SuffixStyle:
    """Per-suffix figure styling, faithful to the real script's five tabs."""

    suffix: str
    title_prefix: str          # e.g. "SG Calculations"
    title_template: str        # how the scenario/group are joined into the title
    hovertemplate: str
    yaxis_title: str = "Data"
    overlay: bool = False      # main_and_compared_data pairs Main:/Comp: traces


# The exact title strings the real script emits (note the spacing differences
# between the ``main`` tab and the rest -- reproduced verbatim). The trace-name
# marker that the real script uses per tab (``*`` for compared_data, ``Δ`` for
# comparison, ``%`` for percent, ``Main:``/``Comp:`` for overlay) is NOT applied
# here: that marker is already part of the CSV column header, so the writer keeps
# names verbatim and the suffix only controls title / yaxis / hover / dash.
SUFFIX_STYLES: dict[str, SuffixStyle] = {
    SUFFIX_MAIN: SuffixStyle(
        suffix=SUFFIX_MAIN,
        title_prefix="SG Calculations",
        title_template="{prefix} : {scenario} ( {group} )",
        hovertemplate=_HOVER_DATA,
    ),
    SUFFIX_COMPARED: SuffixStyle(
        suffix=SUFFIX_COMPARED,
        title_prefix="Compared Data",
        title_template="{prefix} : {scenario}  ({group})",
        hovertemplate=_HOVER_DATA,
    ),
    SUFFIX_OVERLAY: SuffixStyle(
        suffix=SUFFIX_OVERLAY,
        title_prefix="Overlay Plot",
        title_template="{prefix} : {scenario}  ({group})",
        hovertemplate=_HOVER_DATA,
        overlay=True,
    ),
    SUFFIX_COMPARISON: SuffixStyle(
        suffix=SUFFIX_COMPARISON,
        title_prefix="Comparison",
        title_template="{prefix} : {scenario}  ({group})",
        hovertemplate=_HOVER_DATA,
    ),
    SUFFIX_COMPARISON_PCT: SuffixStyle(
        suffix=SUFFIX_COMPARISON_PCT,
        title_prefix="Comparison",
        title_template="{prefix} : {scenario}  ({group})",
        hovertemplate=_HOVER_PERCENT,
    ),
}


class ConversionError(ValueError):
    """Raised when a file cannot be parsed or converted."""


# --------------------------------------------------------------------------- #
# HTML -> table parsing
#
# The structural parser is reused from the Sensor Data Comparison Tool's
# ``logic.py`` when importable; a self-contained fallback (the same algorithm,
# depending only on numpy/json/base64/re) keeps this script runnable even when
# that package -- or its scipy dependency -- is unavailable. The trace-name
# reader here intentionally PRESERVES the leading ``*`` marker (logic.py strips
# it) so ``compared_data`` files round-trip byte-for-byte.
# --------------------------------------------------------------------------- #

def _import_logic_helpers() -> dict[str, Callable] | None:
    tool_dir = Path(__file__).resolve().parent / "Sensor_Data_Comparison_Tool"
    if not tool_dir.exists():
        return None
    inserted = str(tool_dir) not in sys.path
    if inserted:
        sys.path.insert(0, str(tool_dir))
    # The attribute access is kept inside the try so a renamed/removed private
    # helper degrades to the vendored fallback instead of crashing this import.
    try:
        from sensor_compare_tool import logic as _logic  # type: ignore
        # Only the structural parser is reused. The numeric coercion is kept
        # local because logic.py rejects non-finite traces (NaN/inf) -- a
        # converter must preserve them (Biaxiality_Ratio = σ2/σ1, percent, ...).
        return {"iter_args": _logic._iter_plotly_new_plot_args}
    except Exception:
        return None


_LOGIC = _import_logic_helpers()


def _iter_plotly_new_plot_args(html_text: str) -> list[list[str]]:
    if _LOGIC is not None:
        return _LOGIC["iter_args"](html_text)
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


def _coerce_plotly_numeric_array(value: Any) -> np.ndarray | None:
    """Decode a Plotly x/y value (base64 typed array or plain list) to a 1-D
    float array. Unlike the comparison tool's importer, non-finite values
    (NaN/inf) are PRESERVED so they survive the round trip."""
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
    return np.asarray(numeric)


# plotly-resampler rewrites each trace name as
# ``<b ...>[R]</b> <original name> <i ...>~<bin size></i>``. Strip that wrapper
# back to the original channel name while keeping the leading marker intact.
_RESAMPLER_PREFIX_RE = re.compile(r"<b[^>]*>\s*\[R\]\s*</b>\s*")
_RESAMPLER_SUFFIX_RE = re.compile(r"\s*<i[^>]*>\s*~[^<]*</i>\s*$")


def _trace_name_preserving(trace: dict[str, Any], trace_index: int) -> str:
    """Return the trace name with all markers preserved (``*`` kept)."""
    raw_name = trace.get("name")
    name = str(raw_name).strip() if raw_name is not None else ""
    if name and _RESAMPLER_PREFIX_RE.search(name):
        name = _RESAMPLER_SUFFIX_RE.sub("", _RESAMPLER_PREFIX_RE.sub("", name)).strip()
    if not name:
        meta = trace.get("meta")
        name = str(meta).strip() if meta is not None else ""
    if not name:
        name = f"Trace {trace_index}"
    return name


def _deduplicate_names(names: Sequence[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique: list[str] = []
    for name in names:
        count = seen.get(name, 0) + 1
        seen[name] = count
        unique.append(name if count == 1 else f"{name} ({count})")
    return unique


def _time_axes_align(reference: np.ndarray, candidate: np.ndarray, rel_tol: float = 1e-6) -> bool:
    if len(reference) != len(candidate):
        return False
    if len(reference) == 0:
        return True
    # Bit-identical axes (incl. matching NaN positions) align trivially -- this
    # is the common case (every trace shares one Time array) and keeps a NaN in
    # Time from being mangled by the interpolation fallback.
    if np.array_equal(reference, candidate, equal_nan=True):
        return True
    # NaN must sit in the same positions on both axes; compare the finite rest.
    ref_nan, cand_nan = np.isnan(reference), np.isnan(candidate)
    if not np.array_equal(ref_nan, cand_nan):
        return False
    finite = ~ref_nan
    if not finite.any():
        return True
    ref_f, cand_f = reference[finite], candidate[finite]
    span = float(np.ptp(ref_f))
    tolerance = rel_tol * span if span > 0 else rel_tol
    return bool(np.max(np.abs(ref_f - cand_f)) <= tolerance + 1e-9)


def _align_traces_to_common_axis(
    collected: list[tuple[str, np.ndarray, np.ndarray]],
    warn: Callable[[str], None] | None = None,
) -> tuple[np.ndarray, list[tuple[str, np.ndarray]]]:
    minimums = [float(np.min(axis)) for _, axis, _ in collected]
    maximums = [float(np.max(axis)) for _, axis, _ in collected]
    span = max(maximums) - min(minimums)
    range_tolerance = 1e-3 * span if span > 0 else 1e-3
    if (max(minimums) - min(minimums) > range_tolerance) or (
        max(maximums) - min(maximums) > range_tolerance
    ):
        raise ConversionError(
            "All imported Plotly traces must share the same Time axis "
            "(the traces cover different time ranges and cannot be aligned)."
        )
    grid = np.unique(np.concatenate([axis for _, axis, _ in collected]))
    # The traces share a Time *range* but not the exact sample points -- this is
    # what plotly-resampler emits (each channel LTTB-decimated independently).
    # Re-aligning onto a common grid interpolates interior values, which is NOT
    # lossless, so the caller is warned loudly rather than silently fabricating.
    if warn is not None:
        warn(
            f"  WARNING: traces have different Time sampling; interpolated onto a "
            f"shared {len(grid)}-point grid. Interior values are reconstructed "
            f"(not lossless) -- typical of plotly-resampler exports."
        )
    series: list[tuple[str, np.ndarray]] = []
    for name, axis, y_values in collected:
        order = np.argsort(axis, kind="stable")
        series.append((name, np.interp(grid, axis[order], y_values[order])))
    return grid, series


def _traces_to_frame(
    traces: list[dict[str, Any]],
    warn: Callable[[str], None] | None = None,
) -> pd.DataFrame | None:
    collected: list[tuple[str, np.ndarray, np.ndarray]] = []
    for trace_index, trace in enumerate(traces, start=1):
        x_values = _coerce_plotly_numeric_array(trace.get("x"))
        y_values = _coerce_plotly_numeric_array(trace.get("y"))
        if x_values is None or y_values is None:
            continue
        if len(x_values) != len(y_values):
            raise ConversionError(f"Plotly trace {trace_index} has different x and y lengths.")
        collected.append((_trace_name_preserving(trace, trace_index), x_values, y_values))

    if not collected:
        return None

    reference_axis = collected[0][1]
    if all(_time_axes_align(reference_axis, axis) for _, axis, _ in collected):
        time_values = reference_axis
        series = [(name, y_values) for name, _, y_values in collected]
    else:
        time_values, series = _align_traces_to_common_axis(collected, warn=warn)

    unique_names = _deduplicate_names([name for name, _ in series])
    data: dict[str, Any] = {TIME_COLUMN: time_values}
    for name, (_, values) in zip(unique_names, series):
        data[name] = values
    return pd.DataFrame(data)


def html_to_dataframe(
    path: str | Path,
    warn: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """Parse a Plotly HTML figure into a ``Time``-first DataFrame.

    ``warn`` (if given) receives a message when traces had to be interpolated
    onto a shared Time grid (a lossy operation), so the caller can surface it.
    """
    path = Path(path)
    try:
        html_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        html_text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ConversionError(f"Could not read HTML file {path.name}: {exc}") from exc

    candidates: list[list[dict[str, Any]]] = []
    for args in _iter_plotly_new_plot_args(html_text):
        if len(args) < 2:
            continue
        try:
            data_arg = json.loads(args[1])
        except json.JSONDecodeError:
            continue
        if isinstance(data_arg, list):
            traces = [t for t in data_arg if isinstance(t, dict)]
            if traces:
                candidates.append(traces)

    # The real data figure is emitted last; library/template artifacts come
    # first. Try candidates in reverse and don't let one bad block abort.
    first_error: ConversionError | None = None
    for traces in reversed(candidates):
        try:
            frame = _traces_to_frame(traces, warn=warn)
        except ConversionError as exc:
            if first_error is None:
                first_error = exc
            continue
        if frame is not None:
            return frame
    if first_error is not None:
        raise first_error
    raise ConversionError(f"{path.name} does not contain usable Plotly trace data.")


# --------------------------------------------------------------------------- #
# CSV <-> table
# --------------------------------------------------------------------------- #

def csv_to_dataframe(path: str | Path) -> pd.DataFrame:
    """Read an SG CSV into a ``Time``-first DataFrame."""
    path = Path(path)
    try:
        frame = pd.read_csv(path)
    except Exception as exc:  # pragma: no cover - pandas raises many types
        raise ConversionError(f"Could not read CSV file {path.name}: {exc}") from exc
    frame = _drop_unnamed_index(frame)
    if TIME_COLUMN not in frame.columns:
        raise ConversionError(
            f"{path.name} has no '{TIME_COLUMN}' column; not a valid SG data CSV."
        )
    ordered = [TIME_COLUMN] + [c for c in frame.columns if c != TIME_COLUMN]
    return frame[ordered]


_UNNAMED_RE = re.compile(r"^Unnamed: \d+$")


def _drop_unnamed_index(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop a stray pandas index column saved by ``to_csv(index=True)``.

    Only an ``Unnamed: N`` column that carries no real data (all-NaN) or is a
    plain ``0..n-1`` range index is removed -- a *value* trace that happens to be
    named ``Unnamed: 7`` (verbatim header from an external producer) is kept.
    """
    drop: list[str] = []
    n = len(frame)
    for col in frame.columns:
        if not _UNNAMED_RE.match(str(col)):
            continue
        series = frame[col]
        if series.isna().all():
            drop.append(col)
            continue
        try:
            values = series.to_numpy(dtype=float)
        except (TypeError, ValueError):
            continue
        if n and np.array_equal(values, np.arange(n, dtype=float)):
            drop.append(col)
    return frame.drop(columns=drop) if drop else frame


def dataframe_to_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    """Write the table as an SG CSV (``utf-8-sig``, no index, Time first)."""
    path = Path(path)
    ordered = [TIME_COLUMN] + [c for c in frame.columns if c != TIME_COLUMN]
    path.parent.mkdir(parents=True, exist_ok=True)
    frame[ordered].to_csv(path, index=False, encoding=CSV_ENCODING)
    return path


# --------------------------------------------------------------------------- #
# table -> HTML
# --------------------------------------------------------------------------- #

def _strip_known_marker(column: str) -> str:
    """Remove a leading suffix marker (``*`` / ``Delta`` / ``%`` / ``Main:`` / ``Comp:``)."""
    for marker in ("Main:", "Comp:"):
        if column.startswith(marker):
            return column[len(marker):].strip()
    if column[:1] in {"*", "Δ", "%"}:
        return column[1:].strip()
    return column


_OVERLAY_MAIN = "Main: "
_OVERLAY_COMP = "Comp: "

# Filename token for the optional percentage/full-data CSV produced from an
# overlay. Deliberately NOT a member of ``KNOWN_SUFFIXES`` so it never alters the
# round-trip semantics of the five real export suffixes.
SUFFIX_COMPARISON_FULL = "comparison_full"


def build_comparison_full_frame(frame: pd.DataFrame) -> pd.DataFrame | None:
    """Build the ``plot_SG_calculations_FEA`` full-data table from an overlay.

    An overlay frame carries paired ``Main: <col>`` / ``Comp: <col>`` value
    columns sharing one ``Time`` axis. This reproduces the exact layout written
    by ``write_full_data_to_csv``::

        Time | <clean main cols> | Δ<col> … | %<col> …

    where, for every channel common to both series (paired by the base header
    after the marker is stripped):

    * ``Δ<col> = Main − Comp``                  (prefix ``Δ`` = U+0394)
    * ``%<col> = ((Main / Comp) − 1) * 100``    (raw division; ``inf``/``NaN`` kept)

    The main block keeps *all* ``Main:`` columns (mirroring plot_SG's
    ``output_data``); the ``Δ``/``%`` blocks cover only the Main∩Comp
    intersection. Returns ``None`` when no channel is shared (nothing to compute).
    """
    value_columns = [c for c in frame.columns if c != TIME_COLUMN]
    main_cols = [c for c in value_columns if str(c).startswith(_OVERLAY_MAIN)]
    comp_by_base: dict[str, Any] = {
        str(c)[len(_OVERLAY_COMP):]: c
        for c in value_columns if str(c).startswith(_OVERLAY_COMP)
    }

    main_bases = [(str(c)[len(_OVERLAY_MAIN):], c) for c in main_cols]
    common = [(base, mcol, comp_by_base[base])
              for base, mcol in main_bases if base in comp_by_base]
    if not common:
        return None

    data: dict[str, Any] = {TIME_COLUMN: frame[TIME_COLUMN].to_numpy()}
    # Main block: every Main: column, marker stripped, in original order.
    for base, mcol in main_bases:
        data[base] = frame[mcol].to_numpy()
    # Δ block (main − comp), then % block (((main/comp) − 1) * 100); both ordered
    # like the main columns and emitted as two separate blocks to match plot_SG.
    for base, mcol, ccol in common:
        data["Δ" + base] = frame[mcol].to_numpy() - frame[ccol].to_numpy()
    for base, mcol, ccol in common:
        with np.errstate(divide="ignore", invalid="ignore"):
            data["%" + base] = (frame[mcol].to_numpy() / frame[ccol].to_numpy() - 1.0) * 100.0
    return pd.DataFrame(data)


def header_to_trace_name(column: str, suffix: str) -> str:
    """Map a CSV column header to its HTML trace name for the given suffix.

    Only ``compared_data`` adds a display-only marker (a leading ``*``); we store
    the base ``SG<n>_<token>`` header in the CSV (so SG_calculations consumers such
    as the SG-annotations script can read it) and re-apply the ``*`` here. ``Δ`` /
    ``%`` and any literal ``Main:`` / ``Comp:`` headers are kept verbatim.

    (Overlay HTML is split into separate main + compared_data CSVs on import, so
    the normal flow never round-trips an overlay through a single CSV.)
    """
    column = str(column)
    if suffix == SUFFIX_COMPARED and not column.startswith("*"):
        return "*" + column
    return column


def trace_name_to_header(name: str, suffix: str) -> str:
    """Inverse of :func:`header_to_trace_name`: strip the ``compared_data`` ``*``
    so the CSV header is a clean ``SG_calculations``-style column."""
    name = str(name)
    if suffix == SUFFIX_COMPARED and name.startswith("*"):
        return name[1:]
    return name


def infer_group_from_columns(frame: pd.DataFrame) -> str:
    """Best-effort label family for the title, derived from the value columns.

    e.g. ``SG57_von_Mises [MPa]`` -> ``von_Mises [MPa]``. Falls back to a generic
    label when the columns are heterogeneous (mixed channels).
    """
    families: set[str] = set()
    for col in frame.columns:
        if col == TIME_COLUMN:
            continue
        base = _strip_known_marker(str(col))
        match = re.match(r"^SG\d+_(.*)$", base)
        family = match.group(1) if match else base
        # raw strain channels look like ``SG57_1`` -> family ``1``; collapse those.
        if family.isdigit():
            family = "Raw Strain Data"
        families.add(family.strip())
    if len(families) == 1:
        return next(iter(families))
    return "Mixed Test Channels"


def build_figure(
    frame: pd.DataFrame,
    *,
    scenario: str,
    group: str,
    suffix: str,
):
    """Construct a Plotly figure faithful to ``plot_SG_calculations_FEA``."""
    import plotly.graph_objects as go

    style = SUFFIX_STYLES.get(suffix, SUFFIX_STYLES[SUFFIX_MAIN])
    value_columns = [c for c in frame.columns if c != TIME_COLUMN]
    x = frame[TIME_COLUMN].to_numpy()

    fig = go.Figure()

    def add(name: str, y: np.ndarray, color: str, dash: str | None = None) -> None:
        line = dict(color=color, dash=dash) if dash else dict(color=color)
        fig.add_trace(go.Scattergl(
            x=x,
            y=y,
            name=name,
            line=line,
            hovertemplate=style.hovertemplate,
            hoverlabel=dict(font_size=14, bgcolor="rgba(255, 255, 255, 0.5)"),
            meta=name,
        ))

    # The trace name is the column header, with the suffix's display marker
    # re-applied (only ``compared_data`` adds one: a leading ``*``). ``Δ``/``%``
    # and ``Main:``/``Comp:`` are already part of the header verbatim, so the
    # round trip stays lossless while the CSV keeps annotation-friendly headers.
    for idx, col in enumerate(value_columns):
        color = LIGHT24[idx % len(LIGHT24)]
        dash = "dash" if (style.overlay and str(col).startswith("Comp:")) else None
        add(header_to_trace_name(col, suffix), frame[col].to_numpy(), color, dash)

    title = style.title_template.format(
        prefix=style.title_prefix, scenario=scenario, group=group
    )
    fig.update_layout(
        title_text=title,
        title_x=0.45,
        title_y=0.95,
        legend_title_text="Result",
        template="plotly_white",
        plot_bgcolor="rgba(0,0,0,0.005)",
        xaxis_title="Time [s]",
        yaxis_title=style.yaxis_title,
        font=dict(family="Arial, sans-serif", size=12, color="#0077B6"),
        xaxis=dict(showline=True, showgrid=True, showticklabels=True, linewidth=2,
                   tickfont=dict(family="Arial, sans-serif", size=12),
                   tickmode="auto", nticks=30),
        yaxis=dict(showgrid=True, zeroline=False, showline=False, showticklabels=True,
                   linecolor="rgb(204, 204, 204)", tickmode="auto", nticks=30),
        hovermode="closest",
        margin=dict(t=40, b=0),
    )
    return fig


def dataframe_to_html(
    frame: pd.DataFrame,
    path: str | Path,
    *,
    scenario: str,
    group: str,
    suffix: str,
) -> Path:
    """Write the table as a self-contained Plotly HTML figure."""
    from plotly.offline import plot

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = build_figure(frame, scenario=scenario, group=group, suffix=suffix)
    plot(fig, filename=str(path), output_type="file", auto_open=False)
    return path


# --------------------------------------------------------------------------- #
# Filename <-> metadata
# --------------------------------------------------------------------------- #

@dataclass
class ExportMeta:
    scenario: str
    group: str
    suffix: str
    matched: bool = True       # whether the source filename followed the convention


def _sanitize_token(text: str) -> str:
    """Filename-safe token (mirrors the real script's sanitisation)."""
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_")
    return cleaned or "data"


def parse_export_filename(path: str | Path) -> ExportMeta:
    """Recover (scenario, group, suffix) from an ``SG_Calculations__...`` stem."""
    stem = Path(path).stem
    parts = stem.split("__")
    if len(parts) >= 4 and parts[0] == FILENAME_PREFIX and parts[-1] in KNOWN_SUFFIXES:
        # ``group`` is the single sanitised token immediately before the suffix;
        # everything between the prefix and the group is the scenario. (The
        # writer sanitises both to single ``__``-free tokens, so round-tripping
        # our own filenames is exact; this split only matters for hand-named
        # files whose scenario contains ``__``.)
        suffix = parts[-1]
        group = parts[-2]
        scenario = "__".join(parts[1:-2])
        return ExportMeta(scenario=scenario, group=group, suffix=suffix, matched=True)
    # Non-conforming name: keep the stem as the scenario, default suffix/group.
    return ExportMeta(scenario=stem, group="data", suffix=SUFFIX_MAIN, matched=False)


def build_export_stem(meta: ExportMeta) -> str:
    return "__".join([
        FILENAME_PREFIX,
        _sanitize_token(meta.scenario),
        _sanitize_token(meta.group),
        meta.suffix,
    ])


def title_scenario(scenario: str) -> str:
    """Scenario as shown in the figure title (underscores -> spaces)."""
    return scenario.replace("_", " ")


# --------------------------------------------------------------------------- #
# High-level conversions
# --------------------------------------------------------------------------- #

@dataclass
class ConversionResult:
    source: Path
    outputs: list[Path] = field(default_factory=list)
    ok: bool = False
    messages: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def output(self) -> Path | None:
        """First output path (back-compat; a split overlay produces two)."""
        return self.outputs[0] if self.outputs else None

    def log(self, message: str) -> None:
        self.messages.append(message)


def convert_html_to_csv(
    source: str | Path,
    out_dir: str | Path,
    *,
    do_percentage: bool = False,
    progress: Callable[[str], None] | None = None,
    self_check: bool = True,
) -> ConversionResult:
    source = Path(source)
    result = ConversionResult(source=source)
    emit = _make_emitter(progress, result)
    try:
        emit(f"Reading HTML: {source.name}")
        frame = html_to_dataframe(source, warn=emit)
        n_traces = len(frame.columns) - 1
        emit(f"  parsed {n_traces} trace(s), {len(frame)} time points")
        meta = parse_export_filename(source)
        emit(f"  detected scenario='{meta.scenario}', group='{meta.group}', "
             f"suffix='{meta.suffix}'" + ("" if meta.matched else "  (filename not conventional)"))
        out_dir = Path(out_dir)

        value_cols = [c for c in frame.columns if c != TIME_COLUMN]
        has_main = any(str(c).startswith(_OVERLAY_MAIN) for c in value_cols)
        has_comp = any(str(c).startswith(_OVERLAY_COMP) for c in value_cols)

        if has_main and has_comp:
            # Overlay figure carries two datasets. Split into two standalone,
            # annotation-ready CSVs (main + compared_data), each with clean base
            # SG headers -- no Main:/Comp: markers linger.
            emit("  overlay detected -> splitting into main + compared_data CSVs")
            for split_suffix, marker in ((SUFFIX_MAIN, _OVERLAY_MAIN),
                                         (SUFFIX_COMPARED, _OVERLAY_COMP)):
                cols = [c for c in value_cols if str(c).startswith(marker)]
                base = {TIME_COLUMN: frame[TIME_COLUMN]}
                for c in cols:
                    base[str(c)[len(marker):]] = frame[c]
                sub = pd.DataFrame(base)
                sub_meta = ExportMeta(meta.scenario, meta.group, split_suffix,
                                      matched=meta.matched)
                stem = build_export_stem(sub_meta) if meta.matched else \
                    f"{source.stem}__{split_suffix}"
                out_path = out_dir / (stem + ".csv")
                dataframe_to_csv(sub, out_path)
                emit(f"  wrote CSV: {out_path}")
                if self_check:
                    _assert_frames_equal(sub, csv_to_dataframe(out_path))
                result.outputs.append(out_path)
            if self_check:
                emit("  self-check: both CSVs re-import identically ✓")

            if do_percentage:
                # Additionally emit the plot_SG_calculations full-data table
                # (Time | main | Δ | %) for the Main∩Comp channels. The Δ/% headers
                # parse under the SG-annotations script (``%`` / U+0394 prefixes).
                pct_frame = build_comparison_full_frame(frame)
                if pct_frame is None:
                    emit("  percentage: no common Main/Comp channels -- skipped")
                else:
                    pct_meta = ExportMeta(meta.scenario, meta.group,
                                          SUFFIX_COMPARISON_FULL, matched=meta.matched)
                    pct_stem = build_export_stem(pct_meta) if meta.matched else \
                        f"{source.stem}__{SUFFIX_COMPARISON_FULL}"
                    pct_path = out_dir / (pct_stem + ".csv")
                    dataframe_to_csv(pct_frame, pct_path)
                    n_pct = sum(1 for c in pct_frame.columns if str(c).startswith("%"))
                    emit(f"  percentage: wrote CSV ({n_pct} channel(s)): {pct_path}")
                    if self_check:
                        _assert_frames_equal(pct_frame, csv_to_dataframe(pct_path))
                        emit("  self-check: percentage CSV re-imports identically ✓")
                    result.outputs.append(pct_path)
        else:
            # Single-dataset figure -> one CSV. Strip compared_data's display-only
            # ``*`` so the header is a clean SG_calculations column (``Δ``/``%`` stay,
            # the annotator understands them).
            if do_percentage:
                emit("  percentage: needs a Main/Comp overlay -- skipped "
                     "(single-dataset figure)")
            renames = {c: trace_name_to_header(c, meta.suffix) for c in value_cols}
            if any(k != v for k, v in renames.items()):
                frame = frame.rename(columns=renames)
                emit("  normalised compared-data '*' markers to base SG headers")
            out_path = out_dir / (build_export_stem(meta) + ".csv"
                                  if meta.matched else source.stem + ".csv")
            dataframe_to_csv(frame, out_path)
            emit(f"  wrote CSV: {out_path}")
            if self_check:
                _assert_frames_equal(frame, csv_to_dataframe(out_path))
                emit("  self-check: CSV re-imports identically ✓")
            result.outputs.append(out_path)

        result.ok = True
    except Exception as exc:  # noqa: BLE001 - surfaced to GUI/CLI per file
        result.error = str(exc)
        emit(f"  ERROR: {exc}")
    return result


def convert_csv_to_html(
    source: str | Path,
    out_dir: str | Path,
    *,
    scenario: str | None = None,
    group: str | None = None,
    suffix: str | None = None,
    progress: Callable[[str], None] | None = None,
    self_check: bool = True,
) -> ConversionResult:
    source = Path(source)
    result = ConversionResult(source=source)
    emit = _make_emitter(progress, result)
    try:
        emit(f"Reading CSV: {source.name}")
        frame = csv_to_dataframe(source)
        n_cols = len(frame.columns) - 1
        emit(f"  loaded {n_cols} channel(s), {len(frame)} time points")

        meta = parse_export_filename(source)
        eff_scenario = scenario if scenario else (meta.scenario if meta.matched else source.stem)
        eff_suffix = suffix if suffix else (meta.suffix if meta.matched else SUFFIX_MAIN)
        if eff_suffix not in SUFFIX_STYLES:
            raise ConversionError(f"Unknown suffix '{eff_suffix}'. "
                                  f"Expected one of {sorted(SUFFIX_STYLES)}.")
        if group:
            eff_group = group
        elif meta.matched:
            eff_group = meta.group
        else:
            eff_group = infer_group_from_columns(frame)
        emit(f"  scenario='{eff_scenario}', group='{eff_group}', suffix='{eff_suffix}'")

        meta_out = ExportMeta(scenario=eff_scenario, group=eff_group, suffix=eff_suffix)
        out_path = Path(out_dir) / (build_export_stem(meta_out) + ".html")
        dataframe_to_html(
            frame, out_path,
            scenario=title_scenario(eff_scenario), group=eff_group, suffix=eff_suffix,
        )
        emit(f"  wrote HTML: {out_path}")

        if self_check:
            reloaded = html_to_dataframe(out_path)
            expected_names = [header_to_trace_name(c, eff_suffix)
                              for c in frame.columns if c != TIME_COLUMN]
            _assert_frames_equal(frame, reloaded, expected_names=expected_names)
            emit("  self-check: HTML re-imports identically ✓")

        result.outputs.append(out_path)
        result.ok = True
    except Exception as exc:  # noqa: BLE001
        result.error = str(exc)
        emit(f"  ERROR: {exc}")
    return result


def _make_emitter(progress: Callable[[str], None] | None, result: ConversionResult):
    def emit(message: str) -> None:
        result.log(message)
        if progress is not None:
            progress(message)
    return emit


def _assert_frames_equal(
    expected: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    expected_names: list[str] | None = None,
    rtol: float = 1e-6,
    atol: float = 1e-6,
) -> None:
    """Verify a round-trip preserved Time, column names, and values.

    ``expected_names`` overrides the value-column names to compare against (used
    when the writer re-applies a display marker, e.g. compared_data's ``*``).
    """
    exp_values = [c for c in expected.columns if c != TIME_COLUMN]
    if expected_names is None:
        expected_names = [str(c) for c in exp_values]

    act_values = [c for c in actual.columns if c != TIME_COLUMN]
    if expected_names != [str(c) for c in act_values]:
        raise ConversionError(
            "Round-trip column mismatch.\n"
            f"  expected: {expected_names}\n"
            f"  actual:   {[str(c) for c in act_values]}"
        )

    if not np.allclose(expected[TIME_COLUMN].to_numpy(float),
                       actual[TIME_COLUMN].to_numpy(float),
                       rtol=rtol, atol=atol, equal_nan=True):
        raise ConversionError("Round-trip Time axis changed beyond tolerance.")

    for exp_col, act_col in zip(exp_values, act_values):
        a = expected[exp_col].to_numpy(float)
        b = actual[act_col].to_numpy(float)
        if not np.allclose(a, b, rtol=rtol, atol=atol, equal_nan=True):
            worst = float(np.max(np.abs(a - b))) if len(a) else float("nan")
            raise ConversionError(
                f"Round-trip values changed for '{exp_col}' (max abs diff {worst:g})."
            )


# --------------------------------------------------------------------------- #
# Command-line entry point (no Qt required)
# --------------------------------------------------------------------------- #

def _run_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Convert SG CSV <-> Plotly HTML.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--to-csv", metavar="HTML", help="convert an HTML figure to CSV")
    group.add_argument("--to-html", metavar="CSV", help="convert a CSV table to HTML")
    parser.add_argument("out_dir", nargs="?", default=".", help="output directory")
    parser.add_argument("--scenario")
    parser.add_argument("--group")
    parser.add_argument("--suffix", choices=sorted(SUFFIX_STYLES))
    parser.add_argument(
        "--percentage", action="store_true",
        help="for an overlay HTML -> CSV, also write a comparison_full CSV "
             "(Time | main | Δ | %%) like plot_SG_calculations",
    )
    args = parser.parse_args(argv)

    if args.to_csv:
        result = convert_html_to_csv(
            args.to_csv, args.out_dir,
            do_percentage=args.percentage, progress=print)
    else:
        result = convert_csv_to_html(
            args.to_html, args.out_dir,
            scenario=args.scenario, group=args.group, suffix=args.suffix,
            progress=print,
        )
    return 0 if result.ok else 1


# --------------------------------------------------------------------------- #
# PyQt6 Fusion GUI
# --------------------------------------------------------------------------- #

def _run_gui() -> int:  # pragma: no cover - exercised manually
    from PyQt6.QtCore import QThread, pyqtSignal
    from PyQt6.QtGui import QColor, QPalette
    from PyQt6.QtWidgets import (
        QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QGridLayout,
        QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow,
        QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton,
        QStyleFactory, QVBoxLayout, QWidget,
    )

    MODE_CSV_TO_HTML = "csv_to_html"
    MODE_HTML_TO_CSV = "html_to_csv"

    class Worker(QThread):
        progress = pyqtSignal(str)
        file_done = pyqtSignal(int, bool)   # index, ok
        finished_all = pyqtSignal(int, int, int)  # ok_count, total, overwrites

        def __init__(self, mode, files, out_dir, scenario, group, suffix,
                     do_percentage=False):
            super().__init__()
            self._mode = mode
            self._files = files
            # An empty out_dir means "write each output beside its own input".
            self._out_dir = out_dir or None
            self._scenario = scenario or None
            self._group = group or None
            self._suffix = suffix or None
            self._do_percentage = do_percentage

        def run(self):
            ok_count = 0
            overwrites = 0
            written: dict[str, str] = {}      # resolved output path -> first source
            for index, file_path in enumerate(self._files):
                self.progress.emit(f"[{index + 1}/{len(self._files)}] {Path(file_path).name}")
                out_dir = self._out_dir or str(Path(file_path).parent)
                if self._mode == MODE_HTML_TO_CSV:
                    result = convert_html_to_csv(
                        file_path, out_dir,
                        do_percentage=self._do_percentage,
                        progress=self.progress.emit)
                else:
                    result = convert_csv_to_html(
                        file_path, out_dir,
                        scenario=self._scenario, group=self._group, suffix=self._suffix,
                        progress=self.progress.emit)
                if result.ok:
                    for out in result.outputs:   # a split overlay yields two
                        key = str(Path(out).resolve())
                        if key in written:
                            overwrites += 1
                            self.progress.emit(
                                f"  WARNING: output '{Path(out).name}' also produced "
                                f"by '{Path(written[key]).name}' -- the earlier file was overwritten.")
                        else:
                            written[key] = str(file_path)
                self.file_done.emit(index, result.ok)
                if result.ok:
                    ok_count += 1
                self.progress.emit("")
            self.finished_all.emit(ok_count, len(self._files), overwrites)

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("SG CSV ↔ Plotly HTML Converter")
            self.resize(940, 680)
            self._files: list[str] = []
            self._out_dir: str = ""
            self._worker: Worker | None = None
            self._build_ui()
            self._on_mode_changed()

        def _build_ui(self):
            central = QWidget()
            root = QVBoxLayout(central)

            # --- Mode selector ---
            mode_box = QGroupBox("Conversion direction")
            mode_layout = QHBoxLayout(mode_box)
            self.rb_csv_to_html = QRadioButton("CSV  →  HTML")
            self.rb_html_to_csv = QRadioButton("HTML  →  CSV")
            self.rb_csv_to_html.setChecked(True)
            self._mode_group = QButtonGroup(self)
            self._mode_group.addButton(self.rb_csv_to_html)
            self._mode_group.addButton(self.rb_html_to_csv)
            self.rb_csv_to_html.toggled.connect(self._on_mode_changed)
            mode_layout.addWidget(self.rb_csv_to_html)
            mode_layout.addWidget(self.rb_html_to_csv)
            mode_layout.addStretch(1)
            root.addWidget(mode_box)

            # --- File selection ---
            files_box = QGroupBox("Input files (batch)")
            files_layout = QVBoxLayout(files_box)
            self.file_list = QListWidget()
            files_layout.addWidget(self.file_list)
            btn_row = QHBoxLayout()
            self.btn_add = QPushButton("Add files…")
            self.btn_clear = QPushButton("Clear")
            self.btn_add.clicked.connect(self._pick_files)
            self.btn_clear.clicked.connect(self._clear_files)
            btn_row.addWidget(self.btn_add)
            btn_row.addWidget(self.btn_clear)
            btn_row.addStretch(1)
            files_layout.addLayout(btn_row)
            root.addWidget(files_box)

            # --- Output + overrides ---
            opts_box = QGroupBox("Output && metadata")
            grid = QGridLayout(opts_box)
            self.out_edit = QLineEdit()
            self.out_edit.setPlaceholderText("Output folder (defaults to each input's folder)")
            self.btn_out = QPushButton("Choose…")
            self.btn_out.clicked.connect(self._pick_out_dir)
            grid.addWidget(QLabel("Output folder:"), 0, 0)
            grid.addWidget(self.out_edit, 0, 1)
            grid.addWidget(self.btn_out, 0, 2)

            self.scenario_edit = QLineEdit()
            self.scenario_edit.setPlaceholderText("(optional) override scenario")
            self.group_edit = QLineEdit()
            self.group_edit.setPlaceholderText("(optional) override label group")
            self.suffix_combo = QComboBox()
            self.suffix_combo.addItem("(from filename)", "")
            for s in KNOWN_SUFFIXES:
                self.suffix_combo.addItem(s, s)
            grid.addWidget(QLabel("Scenario:"), 1, 0)
            grid.addWidget(self.scenario_edit, 1, 1, 1, 2)
            grid.addWidget(QLabel("Label group:"), 2, 0)
            grid.addWidget(self.group_edit, 2, 1, 1, 2)
            grid.addWidget(QLabel("HTML suffix:"), 3, 0)
            grid.addWidget(self.suffix_combo, 3, 1, 1, 2)
            self.chk_percentage = QCheckBox("Do percentage calculations")
            self.chk_percentage.setToolTip(
                "HTML → CSV only: when a 'main_and_compared_data' overlay is "
                "imported, also write a comparison_full CSV "
                "(Time | main | Δ | %) in plot_SG_calculations format.")
            grid.addWidget(self.chk_percentage, 4, 1, 1, 2)
            self._override_box = opts_box
            root.addWidget(opts_box)

            # --- Progress ---
            self.progress_bar = QProgressBar()
            self.progress_bar.setTextVisible(True)
            root.addWidget(self.progress_bar)
            self.log = QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setPlaceholderText("Conversion log…")
            root.addWidget(self.log, 1)

            self.btn_convert = QPushButton("Convert")
            self.btn_convert.setMinimumHeight(36)
            self.btn_convert.clicked.connect(self._start)
            root.addWidget(self.btn_convert)

            self.setCentralWidget(central)

        def _on_mode_changed(self):
            csv_to_html = self.rb_csv_to_html.isChecked()
            # Scenario/group/suffix overrides only matter for CSV -> HTML.
            self.scenario_edit.setEnabled(csv_to_html)
            self.group_edit.setEnabled(csv_to_html)
            self.suffix_combo.setEnabled(csv_to_html)
            # Percentage calc reads an overlay's Main:/Comp: pair -> HTML -> CSV only.
            self.chk_percentage.setEnabled(not csv_to_html)

        def _pick_files(self):
            if self.rb_csv_to_html.isChecked():
                flt = "CSV files (*.csv);;All files (*)"
            else:
                flt = "Plotly HTML (*.html *.htm);;All files (*)"
            files, _ = QFileDialog.getOpenFileNames(self, "Select input files", "", flt)
            for f in files:
                if f not in self._files:
                    self._files.append(f)
                    self.file_list.addItem(f)

        def _clear_files(self):
            self._files.clear()
            self.file_list.clear()

        def _pick_out_dir(self):
            d = QFileDialog.getExistingDirectory(self, "Select output folder")
            if d:
                self.out_edit.setText(d)

        def _start(self):
            if not self._files:
                QMessageBox.warning(self, "No input", "Add at least one input file.")
                return
            mode = MODE_CSV_TO_HTML if self.rb_csv_to_html.isChecked() else MODE_HTML_TO_CSV
            # An empty output folder means "write each output beside its own
            # input"; the Worker resolves that per file.
            out_dir = self.out_edit.text().strip()
            files = list(self._files)
            self.progress_bar.setRange(0, len(files))
            self.progress_bar.setValue(0)
            self.log.clear()
            self._set_busy(True)
            self._worker = Worker(
                mode, files, out_dir,
                self.scenario_edit.text().strip(),
                self.group_edit.text().strip(),
                self.suffix_combo.currentData(),
                self.chk_percentage.isChecked(),
            )
            self._worker.progress.connect(self._append_log)
            self._worker.file_done.connect(self._on_file_done)
            self._worker.finished_all.connect(self._on_all_done)
            self._worker.start()

        def _append_log(self, message: str):
            self.log.appendPlainText(message)

        def _on_file_done(self, index: int, ok: bool):
            self.progress_bar.setValue(index + 1)

        def _on_all_done(self, ok_count: int, total: int, overwrites: int):
            self._set_busy(False)
            summary = f"\nDone: {ok_count}/{total} file(s) converted successfully."
            if overwrites:
                summary += (f" {overwrites} output(s) collided and overwrote an "
                            f"earlier result -- see the log.")
            self._append_log(summary)
            if ok_count == total and not overwrites:
                QMessageBox.information(self, "Conversion complete",
                                        f"All {total} file(s) converted successfully.")
            elif overwrites:
                QMessageBox.warning(
                    self, "Conversion finished with output collisions",
                    f"{ok_count}/{total} converted, but {overwrites} share an output "
                    f"name and overwrote earlier files. Pick distinct scenarios/groups "
                    f"or output folders. See the log for the colliding names.")
            else:
                QMessageBox.warning(self, "Conversion finished with errors",
                                    f"{ok_count}/{total} succeeded. See the log for details.")

        def _set_busy(self, busy: bool):
            self.btn_convert.setEnabled(not busy)
            self.btn_add.setEnabled(not busy)
            self.btn_clear.setEnabled(not busy)

    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(_engineering_palette(QPalette, QColor))
    window = MainWindow()
    window.show()
    return app.exec()


def _engineering_palette(QPalette, QColor):  # pragma: no cover - GUI styling
    """A restrained, instrument-panel light palette for the Fusion style."""
    palette = QPalette()
    base_bg = QColor("#f4f6f8")
    panel = QColor("#ffffff")
    text = QColor("#1d2733")
    accent = QColor("#0077B6")
    palette.setColor(QPalette.ColorRole.Window, base_bg)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, panel)
    palette.setColor(QPalette.ColorRole.AlternateBase, base_bg)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, base_bg)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, panel)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    return palette


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        return _run_cli(argv)
    return _run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
