# Purpose: Standalone strain-gauge thermal-output (apparent-strain) correction tool for FE validation.
# Map: subsystems/supporting_runtime_assets
# Tests: tests/test_strain_gauge_thermal_correction.py
"""Strain-gauge thermal correction.

Removes the temperature-induced *thermal output* (apparent strain) from measured
strain-gauge channels so the recovered **mechanical** strain can be validated
against an FE model's elastic strain.

Correction model::

    eps_mech(t)   = (eps_measured(t) - eps_apparent(T(t))) * F_ref / F(T(t))
    eps_apparent  = curve_fit(T) + (alpha_part - alpha_curve) * (T - T_ref)
    F(T)          = F_ref * (1 + dF(T) / 100)

See ``methodology_docs/`` for the full theory walkthrough.
"""

from __future__ import annotations

from .config import (
    MICROSTRAIN,
    STRAIN,
    CorrectionConfig,
    unit_factor_to_microstrain,
)
from .core import (
    ChannelCorrection,
    CurveFit,
    apparent_strain,
    build_diagnostics,
    correct_channel,
    correct_dataset,
    eval_alpha_part,
    gauge_factor,
    gauge_factor_scale,
    load_curve,
    load_curve_from_coeffs,
    read_timeseries_csv,
    write_corrected_strain_csv,
    write_diagnostics_json,
    write_thermal_apparent_csv,
)

__all__ = [
    "MICROSTRAIN",
    "STRAIN",
    "CorrectionConfig",
    "unit_factor_to_microstrain",
    "ChannelCorrection",
    "CurveFit",
    "apparent_strain",
    "build_diagnostics",
    "correct_channel",
    "correct_dataset",
    "eval_alpha_part",
    "gauge_factor",
    "gauge_factor_scale",
    "load_curve",
    "load_curve_from_coeffs",
    "read_timeseries_csv",
    "write_corrected_strain_csv",
    "write_diagnostics_json",
    "write_thermal_apparent_csv",
]
