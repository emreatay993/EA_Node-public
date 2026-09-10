# Purpose: Tests for the strain-gauge thermal-output correction tool.
# Map: subsystems/supporting_runtime_assets
# Tests: tests/test_strain_gauge_thermal_correction.py
"""Round-trip, schema-compatibility, units, and edge-case tests.

The reuse target ``channel_matrix_from_csv`` lives in an IronPython Mechanical
script (it imports ``System.Drawing`` at module top) and therefore cannot be
imported under CPython. Its documented CSV contract is vendored here verbatim so
the schema test stays honest without importing the IronPython module.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.strain_gauge_thermal_correction import config, core

REPO_ROOT = Path(__file__).resolve().parents[1]
ALPHA_PART = 9.0
ALPHA_CURVE = 16.0
T_REF = 20.0
M_CU = 1.1  # copper-reference curve slope, ppm/degC


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _scenario(*, gf_slope_pct: float = 0.0, n: int = 200, peak: float = 170.0, seed: int = 1):
    """Build a synthetic single-gauge scenario from a KNOWN mechanical strain."""
    rng = np.random.default_rng(seed)
    time = np.linspace(0.0, 100.0, n)
    temperature = T_REF + (peak - T_REF) * np.sin(np.pi * time / time[-1])
    eps_mech_true = 250.0 * np.sin(2 * np.pi * time / 30.0) + 0.8 * time
    eps_apparent = M_CU * (temperature - T_REF) + (ALPHA_PART - ALPHA_CURVE) * (temperature - T_REF)
    dF = gf_slope_pct * (temperature - T_REF)
    measured = eps_mech_true * (1.0 + dF / 100.0) + eps_apparent
    return {
        "time": time,
        "temperature": temperature,
        "truth": eps_mech_true,
        "measured": measured,
        "rng": rng,
    }


def _exact_copper_fit():
    """Exact copper-reference CurveFit (no noise) so round-trips invert cleanly."""
    # eps(T) = M_CU*(T - T_REF) -> polyval coeffs [M_CU, -M_CU*T_REF]
    return core.load_curve_from_coeffs([M_CU, -M_CU * T_REF], t_min=-20.0, t_max=260.0)


def _frames(scn, channel="SG01"):
    strain = pd.DataFrame({"Time": scn["time"], channel: scn["measured"]})
    temp = pd.DataFrame({"Time": scn["time"], channel: scn["temperature"]})
    return strain, temp


def _vendored_channel_matrix_from_csv(path, channel_names, target_rows):
    """Verbatim contract from load_reconstruction_*.py::channel_matrix_from_csv.

    Cannot import the original (IronPython: imports System.Drawing at module top).
    """
    df = pd.read_csv(path)
    if all(channel in df.columns for channel in channel_names):
        values = df.loc[:, channel_names].astype(float).values
    elif df.shape[1] == len(channel_names) + 1:
        values = df.iloc[:, 1:].astype(float).values
    elif df.shape[1] == len(channel_names):
        values = df.iloc[:, :].astype(float).values
    else:
        raise ValueError(f"{path} has shape {df.shape}, expected channel-matching columns")
    if values.shape[0] == 1 and target_rows > 1:
        values = np.repeat(values, target_rows, axis=0)
    if values.shape != (target_rows, len(channel_names)):
        raise ValueError(f"{path} -> {values.shape}, expected {(target_rows, len(channel_names))}")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{path} contains non-finite values")
    return values


def _load_sensor_validate():
    logic_path = REPO_ROOT / "scripts/Sensor_Data_Comparison_Tool/sensor_compare_tool/logic.py"
    name = "sg_sensor_logic_for_test"
    spec = importlib.util.spec_from_file_location(name, logic_path)
    module = importlib.util.module_from_spec(spec)
    # Register before exec: logic.py uses `from __future__ import annotations`, so
    # its dataclasses resolve field types via sys.modules at class-creation time.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# Round-trip / correctness
# --------------------------------------------------------------------------- #
def test_roundtrip_recovers_ground_truth():
    scn = _scenario(gf_slope_pct=0.008)
    strain, temp = _frames(scn)
    fit = _exact_copper_fit()
    cfg = config.CorrectionConfig(
        t_ref_celsius=T_REF,
        mismatch_enabled=True,
        alpha_part_ppm=ALPHA_PART,
        alpha_curve_substrate_ppm=ALPHA_CURVE,
        gauge_factor_delta_pct=0.008,
    )
    corrected, apparent, diag = core.correct_dataset(strain, temp, fit, cfg)
    recovered = corrected["SG01"].to_numpy(float)
    assert np.max(np.abs(recovered - scn["truth"])) < 1e-5
    # the apparent strain we corrected out is large and matches the hand value
    assert diag["channels"][0]["max_apparent_strain_microstrain"] > 800.0


def test_mismatch_off_introduces_expected_error():
    scn = _scenario(gf_slope_pct=0.0)  # isolate the mismatch term (no gauge-factor effect)
    strain, temp = _frames(scn)
    fit = _exact_copper_fit()
    cfg = config.CorrectionConfig(
        t_ref_celsius=T_REF,
        mismatch_enabled=False,  # WRONG for a copper-reference curve on titanium
        gauge_factor_delta_pct=None,
    )
    corrected, _apparent, _diag = core.correct_dataset(strain, temp, fit, cfg)
    recovered = corrected["SG01"].to_numpy(float)
    expected_error = (ALPHA_PART - ALPHA_CURVE) * (scn["temperature"] - T_REF)
    assert np.allclose(recovered - scn["truth"], expected_error, atol=1e-6)
    assert np.max(np.abs(recovered - scn["truth"])) > 900.0  # ~1050 ue


def test_curve_fit_r_squared(tmp_path):
    rng = np.random.default_rng(7)
    t_curve = np.linspace(-20.0, 260.0, 24)
    eps = M_CU * (t_curve - T_REF) + rng.normal(0.0, 0.4, t_curve.size)
    path = tmp_path / "curve.csv"
    pd.DataFrame({"Temperature_C": t_curve, "ApparentStrain_ue": eps}).to_csv(path, index=False)
    fit = core.load_curve(path, degree=1)
    assert fit.r_squared > 0.999
    assert abs(fit.coeffs[0] - M_CU) < 0.05
    assert fit.source == "csv"


def test_excel_curve_loader(tmp_path):
    t_curve = np.linspace(-20.0, 260.0, 20)
    eps = M_CU * (t_curve - T_REF)
    path = tmp_path / "curve.xlsx"
    pd.DataFrame({"Temperature_C": t_curve, "ApparentStrain_ue": eps}).to_excel(path, index=False)
    fit = core.load_curve(path, degree=1)
    assert fit.source == "excel"
    assert fit.r_squared > 0.9999
    assert abs(fit.coeffs[0] - M_CU) < 1e-6


# --------------------------------------------------------------------------- #
# Schema compatibility with downstream tools
# --------------------------------------------------------------------------- #
def test_thermal_csv_schema_compat(tmp_path):
    scn = _scenario()
    strain, temp = _frames(scn)
    fit = _exact_copper_fit()
    cfg = config.CorrectionConfig()
    _corrected, apparent, _diag = core.correct_dataset(strain, temp, fit, cfg)

    full = tmp_path / "SG_thermal_apparent_strain_data.csv"
    core.write_thermal_apparent_csv(full, apparent)
    matrix = _vendored_channel_matrix_from_csv(full, ["SG01"], target_rows=len(scn["time"]))
    assert matrix.shape == (len(scn["time"]), 1)
    assert np.all(np.isfinite(matrix))

    one_row = tmp_path / "SG_thermal_single_row.csv"
    core.write_thermal_apparent_csv(one_row, apparent, single_row=True)
    broadcast = _vendored_channel_matrix_from_csv(one_row, ["SG01"], target_rows=len(scn["time"]))
    assert broadcast.shape == (len(scn["time"]), 1)


def test_corrected_csv_validates_in_sensor_tool(tmp_path):
    scn = _scenario()
    strain, temp = _frames(scn)
    fit = _exact_copper_fit()
    corrected, _apparent, _diag = core.correct_dataset(strain, temp, fit, config.CorrectionConfig())
    path = tmp_path / "corrected_strain.csv"
    core.write_corrected_strain_csv(path, corrected)

    sensor_logic = _load_sensor_validate()
    frame = pd.read_csv(path)
    sensor_logic.validate_dataset_frame(frame, "corrected")  # must not raise


# --------------------------------------------------------------------------- #
# Units / gauge factor
# --------------------------------------------------------------------------- #
def test_units_microstrain_vs_strain():
    scn = _scenario()
    strain, temp = _frames(scn)
    fit = _exact_copper_fit()
    ue, _a1, _d1 = core.correct_dataset(strain, temp, fit, config.CorrectionConfig(output_unit="microstrain"))
    st, _a2, _d2 = core.correct_dataset(strain, temp, fit, config.CorrectionConfig(output_unit="strain"))
    assert np.allclose(ue["SG01"].to_numpy(float), st["SG01"].to_numpy(float) * 1.0e6, atol=1e-6)


def test_gauge_factor_identity():
    T = np.linspace(20.0, 200.0, 50)
    cfg_none = config.CorrectionConfig(gauge_factor_delta_pct=None)
    assert np.allclose(core.gauge_factor_scale(T, cfg_none), 1.0)
    cfg_gf = config.CorrectionConfig(gauge_factor_delta_pct=0.01)  # %/degC slope
    expected = 1.0 / (1.0 + 0.01 * (T - cfg_gf.t_ref_celsius) / 100.0)
    assert np.allclose(core.gauge_factor_scale(T, cfg_gf), expected)


def test_alpha_part_table_interpolation():
    cfg = config.CorrectionConfig(alpha_part_ppm=[[0.0, 8.5], [200.0, 9.7]])
    alpha = core.eval_alpha_part(np.array([0.0, 100.0, 200.0]), cfg.alpha_part_ppm)
    assert np.allclose(alpha, [8.5, 9.1, 9.7])


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #
def test_missing_temp_channel():
    scn = _scenario()
    strain = pd.DataFrame({"Time": scn["time"], "SG01": scn["measured"], "SG02": scn["measured"]})
    temp = pd.DataFrame({"Time": scn["time"], "SG01": scn["temperature"]})  # no SG02
    fit = _exact_copper_fit()
    corrected, _apparent, diag = core.correct_dataset(strain, temp, fit, config.CorrectionConfig())
    # SG02 left uncorrected -> equals measured
    assert np.allclose(corrected["SG02"].to_numpy(float), scn["measured"])
    assert any("SG02" in w for w in diag["warnings"])


def test_nan_handling():
    scn = _scenario()
    measured = scn["measured"].copy()
    temperature = scn["temperature"].copy()
    measured[10] = np.nan
    temperature[20] = np.nan
    strain = pd.DataFrame({"Time": scn["time"], "SG01": measured})
    temp = pd.DataFrame({"Time": scn["time"], "SG01": temperature})
    fit = _exact_copper_fit()
    corrected, apparent, _diag = core.correct_dataset(strain, temp, fit, config.CorrectionConfig())
    # apparent strain (fed to load reconstruction) must stay finite everywhere
    assert np.all(np.isfinite(apparent["SG01"].to_numpy(float)))
    # corrected NaN only where the measured input was NaN
    assert np.isnan(corrected["SG01"].to_numpy(float)[10])


def test_extrapolation_warn_vs_error():
    scn = _scenario(peak=170.0)
    strain, temp = _frames(scn)
    narrow = core.load_curve_from_coeffs([M_CU, -M_CU * T_REF], t_min=30.0, t_max=160.0)

    corrected, _a, diag = core.correct_dataset(strain, temp, narrow, config.CorrectionConfig(extrapolation="warn"))
    assert diag["channels"][0]["n_extrapolated_samples"] > 0
    assert any("outside curve fit range" in w for w in diag["channels"][0]["warnings"])

    with pytest.raises(ValueError):
        core.correct_dataset(strain, temp, narrow, config.CorrectionConfig(extrapolation="error"))


def test_config_validation():
    with pytest.raises(ValueError):
        config.CorrectionConfig(mismatch_enabled=True, alpha_part_ppm=None).validate()
    with pytest.raises(ValueError):
        config.CorrectionConfig(extrapolation="bogus").validate()
    with pytest.raises(ValueError):
        config.CorrectionConfig(output_unit="furlongs").validate()
