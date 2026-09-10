from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from skfcalc.batch import run_batch_dataframe, run_numba_dgbb_dataframe
from skfcalc.calibration import fit_calibration
from skfcalc.constants import available_series, get_series_constants
from skfcalc.drag import drag_torque_nmm, volume_factor
from skfcalc.io import case_from_dict, load_case, save_case
from skfcalc.life import _aiso_core, rated_viscosity_cst, reliability_factor_a1
from skfcalc.models import (
    BearingCase,
    BearingFamily,
    LubricationMode,
    SealDefinition,
    ThermalModel,
)
from skfcalc.report import generate_html_report
from skfcalc.seals import seal_torque_nmm
from skfcalc.solver import solve_case
from skfcalc.viscosity import viscosity_cst


def test_viscosity_returns_input_points() -> None:
    case = BearingCase()
    assert viscosity_cst(40.0, case.lubricant) == pytest.approx(case.lubricant.nu40_cst, rel=1e-12)
    assert viscosity_cst(100.0, case.lubricant) == pytest.approx(case.lubricant.nu100_cst, rel=1e-12)


def test_legacy_dgbb_one_node_reference() -> None:
    case = BearingCase()
    case.thermal.model = ThermalModel.ONE_NODE
    case.thermal.oil_bypass_fraction = 0.0
    case.thermal.relaxation = 0.85
    case.thermal.tolerance_c = 1e-5
    case.lubrication.drag_enabled = False
    result = solve_case(case)
    assert result.converged
    assert result.thermal.contact_temperature_c == pytest.approx(131.6474, rel=2e-5)
    assert result.friction.total_torque_nmm == pytest.approx(240.2413, rel=2e-5)
    assert result.friction.total_power_w == pytest.approx(301.8962, rel=2e-5)


@pytest.mark.parametrize("family", list(BearingFamily))
def test_every_family_solves(family: BearingFamily) -> None:
    case = BearingCase()
    case.bearing.family = family
    case.bearing.series = available_series(family)[0]
    if case.bearing.is_thrust:
        case.operating.radial_load_n = 500.0
        case.operating.axial_load_n = 5_000.0
    result = solve_case(case)
    assert result.converged
    assert math.isfinite(result.friction.total_torque_nmm)
    assert result.friction.total_torque_nmm >= 0
    assert math.isfinite(result.thermal.contact_temperature_c)
    assert result.life is not None
    assert result.life.basic_life_mrev > 0



def test_carb_full_complement_proxy_is_visibly_flagged() -> None:
    case = BearingCase()
    case.bearing.family = BearingFamily.CARB
    case.bearing.series = "Full-complement proxy (calibrate)"
    result = solve_case(case)
    assert any("Engineering proxy" in warning for warning in result.warnings)


def test_drag_and_volume_factor() -> None:
    case = BearingCase()
    c = get_series_constants(case.bearing.family, case.bearing.series)
    torque, warnings, details = drag_torque_nmm(
        case.bearing,
        c,
        case.lubrication,
        case.operating.speed_rpm,
        10.0,
    )
    assert torque > 0
    assert 0 < details["VM"] < 0.01
    assert any("digitized" in w for w in warnings)
    assert volume_factor(0.0, True) == 0.0


def test_oil_jet_is_twice_equivalent_oil_bath_model() -> None:
    case = BearingCase()
    c = get_series_constants(case.bearing.family, case.bearing.series)
    case.lubrication.mode = LubricationMode.OIL_BATH_LOW
    bath, _, _ = drag_torque_nmm(case.bearing, c, case.lubrication, 10_000.0, 8.0)
    case.lubrication.mode = LubricationMode.OIL_JET
    jet, _, _ = drag_torque_nmm(case.bearing, c, case.lubrication, 10_000.0, 8.0)
    assert jet == pytest.approx(2.0 * bath, rel=1e-12)


def test_dgbb_rs1_seal_table() -> None:
    case = BearingCase()
    case.seal = SealDefinition(seal_type="RS1", count=2)
    torque, warnings = seal_torque_nmm(case.bearing, case.seal)
    expected = 0.018 * case.bearing.d2_mm**2.25 + 20.0  # D=80 row
    assert torque == pytest.approx(expected)
    assert warnings == []


def test_reliability_and_aiso_reference() -> None:
    assert reliability_factor_a1(90.0) == 1.0
    assert reliability_factor_a1(99.0) == 0.25
    assert _aiso_core("roller", 2.0, 0.5) == pytest.approx(3.0813, rel=1e-4)
    assert rated_viscosity_cst(1000.0, 60.0) > 0


def test_case_json_roundtrip(tmp_path: Path) -> None:
    case = BearingCase()
    case.case_name = "Roundtrip"
    path = save_case(case, tmp_path / "case.json")
    loaded = load_case(path)
    assert loaded.to_dict() == case.to_dict()
    assert case_from_dict(case.to_dict()).bearing.family == case.bearing.family


def test_batch_full_solver() -> None:
    case = BearingCase()
    frame = pd.DataFrame(
        [
            {"case_id": "A", "speed_rpm": 6000, "radial_load_n": 3000, "axial_load_n": 500},
            {"case_id": "B", "speed_rpm": 12000, "radial_load_n": 5000, "axial_load_n": 1000},
        ]
    )
    result = run_batch_dataframe(case, frame)
    assert result.failed_cases == 0
    assert list(result.dataframe["case_id"]) == ["A", "B"]
    assert result.dataframe["converged"].all()


def test_numba_matches_full_one_node() -> None:
    pytest.importorskip("numba")
    case = BearingCase()
    case.thermal.model = ThermalModel.ONE_NODE
    case.thermal.oil_bypass_fraction = 0.0
    frame = pd.DataFrame(
        [{"case_id": "A", "speed_rpm": 12000, "radial_load_n": 5000, "axial_load_n": 1000}]
    )
    fast = run_numba_dgbb_dataframe(case, frame).dataframe.iloc[0]
    full = solve_case(case)
    assert fast["contact_temperature_c"] == pytest.approx(full.thermal.contact_temperature_c, rel=1e-5)
    assert fast["total_torque_nmm"] == pytest.approx(full.friction.total_torque_nmm, rel=1e-5)


def test_numba_matches_full_with_partial_heat_and_double_row_drag() -> None:
    pytest.importorskip("numba")
    case = BearingCase()
    case.bearing.series = "42"
    case.bearing.row_count = 2
    case.thermal.model = ThermalModel.ONE_NODE
    case.thermal.oil_bypass_fraction = 0.10
    case.thermal.heat_fraction_to_model = 0.55
    case.operating.speed_rpm = 9000
    case.operating.radial_load_n = 4200
    case.operating.axial_load_n = 700
    frame = pd.DataFrame(
        [{"case_id": "DR", "speed_rpm": 9000, "radial_load_n": 4200, "axial_load_n": 700}]
    )
    fast = run_numba_dgbb_dataframe(case, frame).dataframe.iloc[0]
    full = solve_case(case)
    assert fast["contact_temperature_c"] == pytest.approx(full.thermal.contact_temperature_c, rel=1e-5)
    assert fast["drag_torque_nmm"] == pytest.approx(full.friction.drag_torque_nmm, rel=1e-10)
    assert fast["total_torque_nmm"] == pytest.approx(full.friction.total_torque_nmm, rel=1e-5)


def test_numba_rejects_negative_operating_map_values() -> None:
    pytest.importorskip("numba")
    case = BearingCase()
    case.thermal.model = ThermalModel.ONE_NODE
    frame = pd.DataFrame(
        [{"case_id": "BAD", "speed_rpm": -1, "radial_load_n": 1000, "axial_load_n": 0}]
    )
    with pytest.raises(ValueError, match="cannot be negative"):
        run_numba_dgbb_dataframe(case, frame)


def test_calibration_recovers_synthetic_scale() -> None:
    base = BearingCase()
    truth = BearingCase()
    truth.calibration.rolling_scale = 1.35
    rows = []
    for speed in (4000.0, 8000.0, 12000.0):
        truth.operating.speed_rpm = speed
        result = solve_case(truth)
        rows.append(
            {
                "case_id": str(speed),
                "speed_rpm": speed,
                "radial_load_n": truth.operating.radial_load_n,
                "axial_load_n": truth.operating.axial_load_n,
                "measured_torque_nmm": result.friction.total_torque_nmm,
                "measured_temperature_c": result.thermal.contact_temperature_c,
            }
        )
    fit = fit_calibration(base, pd.DataFrame(rows), ["rolling_scale"])
    assert fit.success
    assert fit.profile.rolling_scale == pytest.approx(1.35, rel=2e-3)
    assert fit.rms_normalized_residual < 1e-3


def test_html_report(tmp_path: Path) -> None:
    case = BearingCase()
    result = solve_case(case)
    path = generate_html_report(case, result, tmp_path / "report.html")
    text = path.read_text(encoding="utf-8")
    assert "SKF Engineering Bearing Calculation Report" in text
    assert "data:image/png;base64" in text
