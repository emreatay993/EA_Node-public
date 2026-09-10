# Purpose: Strain-gauge thermal-output correction core — curve fit, apparent strain, gauge factor, per-channel correction, CSV/JSON I/O.
# Map: subsystems/supporting_runtime_assets
# Tests: tests/test_strain_gauge_thermal_correction.py
"""Core, GUI-free correction functions.

All internal math is in **microstrain**. CSV units are converted at the boundary
using :func:`config.unit_factor_to_microstrain`.

Correction model::

    eps_mech(t)   = (eps_measured(t) - eps_apparent(T(t))) * F_ref / F(T(t))
    eps_apparent  = curve_fit(T) + (alpha_part - alpha_curve) * (T - T_ref)
    F(T)          = F_ref * (1 + dF(T) / 100)         ->  scale = 1 / (1 + dF(T)/100)
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

try:  # package import (tests, CLI as module)
    from .config import (
        MICROSTRAIN,
        CorrectionConfig,
        unit_factor_to_microstrain,
    )
except ImportError:  # pragma: no cover - direct-script execution fallback
    from config import (  # type: ignore
        MICROSTRAIN,
        CorrectionConfig,
        unit_factor_to_microstrain,
    )

TIME_COLUMN = "Time"
_T_REF_TOL = 5.0  # degC; warn if first temperature sample is far from t_ref


# --------------------------------------------------------------------------- #
# Curve fitting
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CurveFit:
    """A fitted thermal-output curve, eps_apparent [microstrain] as f(T [degC])."""

    coeffs: np.ndarray  # numpy.polyval order (highest power first), microstrain
    degree: int
    r_squared: float
    rmse: float  # microstrain
    t_min: float
    t_max: float
    source: str  # "excel" | "csv" | "coeffs"
    n_points: int = 0


def _polyfit_with_r2(t: np.ndarray, eps: np.ndarray, degree: int):
    """Fit a polynomial, returning ``(coeffs, r_squared, rmse)``.

    Mirrors the (slope, intercept, r_squared, rmse) reporting style of
    ``scripts/miso_curve_builder.py::linear_regression_fit``.
    """
    t = np.asarray(t, dtype=float)
    eps = np.asarray(eps, dtype=float)
    degree = int(degree)
    if t.size <= degree:
        raise ValueError(
            f"need at least degree+1={degree + 1} points to fit a degree-{degree} polynomial; got {t.size}"
        )
    coeffs = np.polyfit(t, eps, degree)
    pred = np.polyval(coeffs, t)
    resid = eps - pred
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((eps - eps.mean()) ** 2))
    r_squared = 1.0 if ss_tot <= 1e-18 else max(0.0, 1.0 - ss_res / ss_tot)
    rmse = math.sqrt(ss_res / t.size)
    return coeffs, r_squared, rmse


def _extract_curve_columns(frame: pd.DataFrame, t_col, strain_col):
    if t_col is not None and strain_col is not None:
        return (
            pd.to_numeric(frame[t_col], errors="coerce").to_numpy(float),
            pd.to_numeric(frame[strain_col], errors="coerce").to_numpy(float),
        )

    def _find(keywords):
        for col in frame.columns:
            name = str(col).strip().lower()
            if any(k in name for k in keywords):
                return col
        return None

    tcol = t_col or _find(("temperature", "temp", "sicaklik", "sıcaklık", "deg", "°c", "(c)"))
    scol = strain_col or _find(
        ("apparent", "thermal output", "thermal", "output", "microstrain", "µε", "ue", "strain")
    )
    numeric_cols = list(frame.select_dtypes(include=[np.number]).columns)
    if tcol is None or scol is None:
        if len(numeric_cols) < 2:
            raise ValueError(
                "curve file must expose at least two numeric columns (temperature, apparent strain)"
            )
        tcol = tcol or numeric_cols[0]
        scol = scol or next((c for c in numeric_cols if c != tcol), numeric_cols[-1])
    t_values = pd.to_numeric(frame[tcol], errors="coerce").to_numpy(float)
    eps_values = pd.to_numeric(frame[scol], errors="coerce").to_numpy(float)
    mask = np.isfinite(t_values) & np.isfinite(eps_values)
    return t_values[mask], eps_values[mask]


def load_curve(
    source,
    *,
    degree: int = 1,
    t_col=None,
    strain_col=None,
    sheet=0,
    curve_unit: str = MICROSTRAIN,
) -> CurveFit:
    """Load a manufacturer thermal-output curve from Excel or CSV and fit it.

    The curve columns are (temperature [degC], apparent strain [``curve_unit``]).
    Columns are detected by name, falling back to the first two numeric columns.
    """
    path = Path(source)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls", ".xlsm"):
        frame = pd.read_excel(path, sheet_name=sheet)
        source_kind = "excel"
    elif suffix in (".csv", ".txt"):
        frame = pd.read_csv(path)
        source_kind = "csv"
    elif suffix == ".tsv":
        frame = pd.read_csv(path, sep="\t")
        source_kind = "csv"
    else:
        raise ValueError(f"unsupported curve file type {suffix!r}; use .xlsx/.xls/.csv/.tsv")
    t_values, eps_values = _extract_curve_columns(frame, t_col, strain_col)
    eps_ue = eps_values * unit_factor_to_microstrain(curve_unit)
    coeffs, r2, rmse = _polyfit_with_r2(t_values, eps_ue, degree)
    return CurveFit(
        coeffs=coeffs,
        degree=int(degree),
        r_squared=r2,
        rmse=rmse,
        t_min=float(np.min(t_values)),
        t_max=float(np.max(t_values)),
        source=source_kind,
        n_points=int(t_values.size),
    )


def load_curve_from_coeffs(
    coeffs,
    *,
    t_min: float = -math.inf,
    t_max: float = math.inf,
    curve_unit: str = MICROSTRAIN,
    r_squared: float = float("nan"),
    rmse: float = float("nan"),
) -> CurveFit:
    """Build a :class:`CurveFit` from known polynomial coefficients.

    ``coeffs`` are in numpy.polyval order (highest power first), expressed in
    ``curve_unit`` strain as a function of temperature in degC.
    """
    arr = np.asarray(coeffs, dtype=float) * unit_factor_to_microstrain(curve_unit)
    return CurveFit(
        coeffs=arr,
        degree=int(arr.size - 1),
        r_squared=float(r_squared),
        rmse=float(rmse),
        t_min=float(t_min),
        t_max=float(t_max),
        source="coeffs",
        n_points=0,
    )


# --------------------------------------------------------------------------- #
# Apparent strain + gauge factor
# --------------------------------------------------------------------------- #
def eval_alpha_part(temperature_c, spec) -> np.ndarray:
    """Evaluate the part thermal-expansion coefficient alpha(T) in ppm/degC.

    ``spec`` is a scalar, an (N, 2) table of ``[T, alpha]`` rows, or a callable.
    """
    T = np.asarray(temperature_c, dtype=float)
    if spec is None:
        raise ValueError("alpha_part spec is None")
    if callable(spec):
        return np.asarray(spec(T), dtype=float) * np.ones_like(T)
    if np.isscalar(spec) or isinstance(spec, (int, float)):
        return np.full_like(T, float(spec))
    table = np.asarray(spec, dtype=float)
    if table.ndim != 2 or table.shape[1] != 2:
        raise ValueError("alpha_part table must be (N, 2) with columns [T, alpha]")
    order = np.argsort(table[:, 0])
    return np.interp(T, table[order, 0], table[order, 1])


def _eval_delta_pct(temperature_c, cfg: CorrectionConfig):
    spec = cfg.gauge_factor_delta_pct
    if spec is None:
        return None
    T = np.asarray(temperature_c, dtype=float)
    if callable(spec):
        return np.asarray(spec(T), dtype=float) * np.ones_like(T)
    if np.isscalar(spec) or isinstance(spec, (int, float)):
        if cfg.gauge_factor_delta_is_slope:
            return float(spec) * (T - cfg.t_ref_celsius)
        return np.full_like(T, float(spec))
    table = np.asarray(spec, dtype=float)
    if table.ndim != 2 or table.shape[1] != 2:
        raise ValueError("gauge_factor_delta_pct table must be (N, 2) with columns [T, delta_percent]")
    order = np.argsort(table[:, 0])
    return np.interp(T, table[order, 0], table[order, 1])


def apparent_strain(temperature_c, fit: CurveFit, cfg: CorrectionConfig) -> np.ndarray:
    """Apparent (thermal-output) strain in microstrain at temperature(s) T."""
    T = np.asarray(temperature_c, dtype=float)
    t_poly = np.clip(T, fit.t_min, fit.t_max) if cfg.extrapolation == "clamp" else T
    base = np.polyval(fit.coeffs, t_poly)
    base = np.asarray(base, dtype=float) * np.ones_like(T)
    if cfg.mismatch_enabled:
        alpha_part = eval_alpha_part(T, cfg.alpha_part_ppm)
        base = base + (alpha_part - float(cfg.alpha_curve_substrate_ppm)) * (T - cfg.t_ref_celsius)
    return base


def gauge_factor_scale(temperature_c, cfg: CorrectionConfig) -> np.ndarray:
    """Gauge-factor correction scale F_ref/F(T) = 1/(1 + dF(T)/100). Ones if no data."""
    T = np.asarray(temperature_c, dtype=float)
    dpct = _eval_delta_pct(T, cfg)
    if dpct is None:
        return np.ones_like(T)
    return 1.0 / (1.0 + np.asarray(dpct, dtype=float) / 100.0)


def gauge_factor(temperature_c, cfg: CorrectionConfig):
    """Actual gauge factor F(T) for reporting; ``None`` if F_ref not provided."""
    if cfg.gauge_factor_ref is None:
        return None
    T = np.asarray(temperature_c, dtype=float)
    dpct = _eval_delta_pct(T, cfg)
    if dpct is None:
        return np.full_like(T, float(cfg.gauge_factor_ref))
    return float(cfg.gauge_factor_ref) * (1.0 + np.asarray(dpct, dtype=float) / 100.0)


# --------------------------------------------------------------------------- #
# Per-channel + dataset correction
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChannelCorrection:
    name: str
    eps_mech: np.ndarray  # microstrain
    eps_apparent: np.ndarray  # microstrain
    gf_scale: np.ndarray
    max_apparent_abs: float  # microstrain
    n_extrapolated: int
    warnings: list = field(default_factory=list)


def correct_channel(
    time,
    eps_measured_microstrain,
    temperature_c,
    fit: CurveFit,
    cfg: CorrectionConfig,
    *,
    name: str = "",
) -> ChannelCorrection:
    """Correct one channel. Inputs/outputs are in microstrain; T in degC."""
    time = np.asarray(time, dtype=float)
    eps_meas = np.asarray(eps_measured_microstrain, dtype=float)
    T = np.asarray(temperature_c, dtype=float)
    warnings: list[str] = []

    finite_T = T[np.isfinite(T)]
    n_extrap = int(np.count_nonzero((finite_T < fit.t_min) | (finite_T > fit.t_max)))
    if n_extrap:
        if cfg.extrapolation == "error":
            raise ValueError(
                f"channel {name!r}: {n_extrap} temperature samples outside curve range "
                f"[{fit.t_min:.1f}, {fit.t_max:.1f}] degC"
            )
        if cfg.extrapolation in ("warn", "clamp"):
            verb = "clamped" if cfg.extrapolation == "clamp" else "extrapolated"
            warnings.append(
                f"{n_extrap} temperature samples outside curve fit range "
                f"[{fit.t_min:.1f}, {fit.t_max:.1f}] degC; apparent strain {verb}."
            )

    eps_app = apparent_strain(T, fit, cfg)
    scale = gauge_factor_scale(T, cfg)
    eps_mech = (eps_meas - eps_app) * scale

    if finite_T.size and abs(float(finite_T[0]) - cfg.t_ref_celsius) > _T_REF_TOL:
        warnings.append(
            f"first temperature sample {float(finite_T[0]):.1f} degC differs from t_ref "
            f"{cfg.t_ref_celsius:.1f} degC; confirm the test is zeroed at the curve reference."
        )

    max_app = float(np.nanmax(np.abs(eps_app))) if eps_app.size else 0.0
    return ChannelCorrection(
        name=name,
        eps_mech=eps_mech,
        eps_apparent=eps_app,
        gf_scale=scale,
        max_apparent_abs=max_app,
        n_extrapolated=n_extrap,
        warnings=warnings,
    )


def _same_grid(a: np.ndarray, b: np.ndarray) -> bool:
    return a.size == b.size and bool(np.allclose(a, b, equal_nan=False))


def correct_dataset(
    strain_frame: pd.DataFrame,
    temp_frame,
    fit: CurveFit,
    cfg: CorrectionConfig,
    *,
    time_column: str = TIME_COLUMN,
):
    """Correct every channel in ``strain_frame`` using same-named temperature columns.

    Returns ``(corrected_frame, apparent_frame, diagnostics)`` where the strain
    frames carry a ``Time`` column plus per-channel data in ``cfg.output_unit``,
    and ``diagnostics`` is a JSON-ready dict.
    """
    cfg.validate()
    strain_frame = strain_frame.copy()
    if strain_frame.columns[0] != time_column:
        strain_frame = strain_frame.rename(columns={strain_frame.columns[0]: time_column})
    time = strain_frame[time_column].to_numpy(float)
    channels = [c for c in strain_frame.columns if c != time_column]

    temp_lookup: dict[str, np.ndarray] = {}
    temp_time = time
    if temp_frame is not None:
        temp_frame = temp_frame.copy()
        if temp_frame.columns[0] != time_column:
            temp_frame = temp_frame.rename(columns={temp_frame.columns[0]: time_column})
        temp_time = temp_frame[time_column].to_numpy(float)
        temp_lookup = {
            c: temp_frame[c].to_numpy(float) for c in temp_frame.columns if c != time_column
        }

    m_factor = unit_factor_to_microstrain(cfg.measured_unit)
    o_factor = unit_factor_to_microstrain(cfg.output_unit)

    corrected: dict[str, np.ndarray] = {time_column: time}
    apparent: dict[str, np.ndarray] = {time_column: time}
    per_channel: list[dict[str, Any]] = []
    global_warnings: list[str] = []

    for ch in channels:
        eps_meas_ue = strain_frame[ch].to_numpy(float) * m_factor
        if ch in temp_lookup:
            T_raw = temp_lookup[ch]
            T = T_raw if _same_grid(time, temp_time) else np.interp(time, temp_time, T_raw)
            cc = correct_channel(time, eps_meas_ue, T, fit, cfg, name=str(ch))
            eps_mech_ue = cc.eps_mech
            eps_app_ue = np.where(np.isfinite(cc.eps_apparent), cc.eps_apparent, 0.0)
            ch_warnings = list(cc.warnings)
            temp_source = "matched" if _same_grid(time, temp_time) else "interpolated-onto-strain-time"
            max_app = cc.max_apparent_abs
            n_extrap = cc.n_extrapolated
        else:
            # No same-named temperature channel: leave uncorrected (pass-through).
            eps_mech_ue = eps_meas_ue.copy()
            eps_app_ue = np.zeros_like(time)
            ch_warnings = ["no temperature column with the same name; channel left uncorrected."]
            temp_source = "missing"
            max_app = 0.0
            n_extrap = 0
            global_warnings.append(f"channel {ch!r}: {ch_warnings[0]}")

        corrected[str(ch)] = eps_mech_ue / o_factor
        apparent[str(ch)] = eps_app_ue / o_factor
        per_channel.append(
            {
                "channel": str(ch),
                "temperature_source": temp_source,
                "max_apparent_strain_microstrain": max_app,
                "n_extrapolated_samples": int(n_extrap),
                "n_samples": int(time.size),
                "warnings": ch_warnings,
            }
        )

    corrected_frame = pd.DataFrame(corrected)
    apparent_frame = pd.DataFrame(apparent)
    diagnostics = build_diagnostics(fit, cfg, per_channel, global_warnings)
    return corrected_frame, apparent_frame, diagnostics


# --------------------------------------------------------------------------- #
# Diagnostics + CSV/JSON I/O
# --------------------------------------------------------------------------- #
def _describe_alpha(spec) -> Any:
    if spec is None:
        return None
    if np.isscalar(spec) or isinstance(spec, (int, float)):
        return float(spec)
    if callable(spec):
        return "callable(T)"
    return {"table": np.asarray(spec, dtype=float).tolist()}


def build_diagnostics(
    fit: CurveFit,
    cfg: CorrectionConfig,
    per_channel: list,
    global_warnings: Sequence[str] | None = None,
) -> dict:
    return {
        "tool": "strain_gauge_thermal_correction",
        "model": {
            "equation": (
                "eps_mech = (eps_measured - eps_apparent) * F_ref/F(T); "
                "eps_apparent = curve_fit(T) + (alpha_part - alpha_curve)*(T - T_ref)"
            ),
            "t_ref_celsius": cfg.t_ref_celsius,
            "mismatch_enabled": bool(cfg.mismatch_enabled),
            "alpha_part_ppm_per_C": _describe_alpha(cfg.alpha_part_ppm),
            "alpha_curve_substrate_ppm_per_C": float(cfg.alpha_curve_substrate_ppm),
            "gauge_factor_correction_applied": cfg.gauge_factor_delta_pct is not None,
        },
        "curve_fit": {
            "source": fit.source,
            "degree": fit.degree,
            "coeffs_microstrain_vs_T_highest_power_first": [float(c) for c in np.atleast_1d(fit.coeffs)],
            "r_squared": fit.r_squared,
            "rmse_microstrain": fit.rmse,
            "t_min_celsius": fit.t_min,
            "t_max_celsius": fit.t_max,
            "n_points": fit.n_points,
        },
        "units": {
            "measured": cfg.measured_unit,
            "curve": cfg.curve_unit,
            "output": cfg.output_unit,
            "internal": MICROSTRAIN,
        },
        "channels": list(per_channel),
        "warnings": list(global_warnings or []),
        "trust_checklist": [
            "Confirm with the gauge maker which substrate the thermal-output curve was measured on "
            "(copper/STC reference vs your titanium part); it decides whether the mismatch term applies.",
            "Confirm the exact reference alpha (alpha_curve) and the curve's reference temperature "
            "(the apparent-strain zero).",
            "Use alpha_part(T) for the actual titanium alloy, not a single constant, over a wide span.",
            "Ensure measured strain and SG_FEA_strain_data.csv share strain units (set output_unit to match).",
            "Zero the test data at the same reference temperature used by the curve.",
            "Compare against FE ELASTIC strain projected onto the gauge axis, not total strain.",
        ],
    }


def read_timeseries_csv(path, *, time_column: str = TIME_COLUMN) -> pd.DataFrame:
    """Read a ``Time + channels`` CSV, coercing values to numeric."""
    frame = pd.read_csv(path)
    if frame.shape[1] < 2:
        raise ValueError(f"{path}: expected a time column plus at least one channel column")
    if str(frame.columns[0]) != time_column:
        frame = frame.rename(columns={frame.columns[0]: time_column})
    for col in frame.columns:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def write_corrected_strain_csv(path, frame: pd.DataFrame, *, time_column: str = TIME_COLUMN) -> Path:
    """Write a corrected-strain time series (Sensor-Comparison-Tool schema)."""
    out = frame.copy()
    if out.columns[0] != time_column:
        out = out.rename(columns={out.columns[0]: time_column})
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(target, index=False)
    return target


def write_thermal_apparent_csv(
    path,
    apparent_frame: pd.DataFrame,
    *,
    time_column: str = TIME_COLUMN,
    single_row: bool = False,
) -> Path:
    """Write ``SG_thermal_apparent_strain_data.csv`` for the load-reconstruction tool.

    Headers are the channel names; the load-reconstruction reader selects channels
    by name (so the leading ``Time`` column is ignored there but kept for clarity).
    ``single_row=True`` emits one broadcastable row (mean apparent strain per
    channel), matching that tool's single-row broadcast branch.
    """
    frame = apparent_frame.copy()
    channels = [c for c in frame.columns if c != time_column]
    if single_row:
        frame = pd.DataFrame({c: [float(np.nanmean(frame[c].to_numpy(float)))] for c in channels})
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    return target


def write_diagnostics_json(path, diagnostics: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as stream:
        json.dump(diagnostics, stream, indent=2)
    return target
