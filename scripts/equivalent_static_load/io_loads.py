"""Interface load histories and Tier-1 load patterns.

Canonical load-history CSV: a ``Time`` column plus one named column per load
channel (wide format). Heterogeneous whole-engine formats are converted into
this canonical CSV outside the tool — by design, to keep ingestion traceable.

A pattern can also come from:
- a two-column CSV (``channel, value``), e.g. reshaped from the
  ``mcf_dpf_section_resultants`` output row at the chosen instant (Route A);
- that tool's resultants CSV directly, via ``resultants_at_time``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.equivalent_static_load.config import Channel
from scripts.equivalent_static_load.constants import SOLVE_DTYPE
from scripts.equivalent_static_load.core import InputError


@dataclass(frozen=True)
class PatternAtInstant:
    """Channel-ordered Tier-1 pattern values at the chosen instant."""

    values: np.ndarray
    interpolated: bool
    source: str


def load_interface_history(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.is_file():
        raise InputError(f"Interface load-history CSV not found: {p}")
    df = pd.read_csv(p)
    time_col = next((c for c in df.columns if str(c).strip().lower() in ("time", "time_s")), None)
    if time_col is None:
        raise InputError(f"{p} needs a 'Time' (or 'time_s') column")
    df = df.rename(columns={time_col: "Time"})
    if not df["Time"].is_monotonic_increasing:
        df = df.sort_values("Time", kind="stable").reset_index(drop=True)
    return df


def pattern_from_history(
    history: pd.DataFrame,
    channels: tuple[Channel, ...],
    t: float,
    grid_tol: float = 1e-9,
) -> PatternAtInstant:
    """Extract L(t*) for channels with an ``interface_channel`` mapping.

    Values are linearly interpolated when ``t`` is off the history grid; the
    flag is surfaced in the report (the whole-engine grid rarely matches the
    MSUP output grid exactly).
    """
    missing = [c.name for c in channels if c.interface_channel is None]
    if missing:
        raise InputError(
            "Tier-1 pattern from load history needs 'interface_channel' on every "
            f"channel; missing on: {missing}"
        )
    times = history["Time"].to_numpy(dtype=SOLVE_DTYPE)
    if not times[0] - grid_tol <= t <= times[-1] + grid_tol:
        raise InputError(
            f"t={t} outside the load-history range [{times[0]}, {times[-1]}]"
        )
    values = np.empty(len(channels), dtype=SOLVE_DTYPE)
    for k, channel in enumerate(channels):
        if channel.interface_channel not in history.columns:
            raise InputError(
                f"Load-history column '{channel.interface_channel}' "
                f"(channel '{channel.name}') not found"
            )
        series = history[channel.interface_channel].to_numpy(dtype=SOLVE_DTYPE)
        values[k] = np.interp(t, times, series)
    nearest = float(times[np.argmin(np.abs(times - t))])
    return PatternAtInstant(
        values=values,
        interpolated=abs(nearest - t) > grid_tol,
        source="interface_history",
    )


def load_pattern_csv(path: str | Path, channels: tuple[Channel, ...]) -> PatternAtInstant:
    """Two-column pattern CSV: ``channel, value`` — one row per rig channel."""
    p = Path(path)
    if not p.is_file():
        raise InputError(f"Pattern CSV not found: {p}")
    df = pd.read_csv(p)
    cols = {str(c).strip().lower(): c for c in df.columns}
    if "channel" not in cols or "value" not in cols:
        raise InputError(f"{p} must have 'channel' and 'value' columns")
    lookup = dict(
        zip(df[cols["channel"]].astype(str).str.strip(), df[cols["value"]].astype(float))
    )
    missing = [c.name for c in channels if c.name not in lookup]
    if missing:
        raise InputError(f"Pattern CSV {p} has no value for channels: {missing}")
    values = np.asarray([lookup[c.name] for c in channels], dtype=SOLVE_DTYPE)
    return PatternAtInstant(values=values, interpolated=False, source=str(p))


def resultants_at_time(path: str | Path, t: float) -> pd.Series:
    """Row of a ``mcf_dpf_section_resultants`` output CSV at (nearest) time ``t``."""
    p = Path(path)
    if not p.is_file():
        raise InputError(f"Resultants CSV not found: {p}")
    df = pd.read_csv(p)
    if "time_s" not in df.columns:
        raise InputError(f"{p} is not a section-resultants CSV (no 'time_s' column)")
    idx = int((df["time_s"] - t).abs().idxmin())
    return df.loc[idx]
