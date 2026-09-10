from __future__ import annotations

import math

import pytest

from scripts.miso_curve_builder import (
    ConversionSettings,
    CurveValidationError,
    RawCurveRow,
    compute_miso_from_rows,
    convert_to_true_curve,
    infer_elastic_modulus,
)


def _settings(
    *,
    curve_type: str = "true",
    modulus_mode: str = "infer",
    manual_modulus_mpa: float | None = None,
) -> ConversionSettings:
    return ConversionSettings(
        curve_type=curve_type,
        modulus_mode=modulus_mode,
        manual_modulus_mpa=manual_modulus_mpa,
        proof_offset_mode="proof_0p2",
        proof_offset_plastic_strain=0.002,
    )


def _row(stress_mpa: float, strain_fraction: float) -> RawCurveRow:
    return RawCurveRow(stress_text=f"{stress_mpa}", strain_text=f"{strain_fraction * 100.0}")


def test_engineering_round_trip_preserves_expected_miso_rows() -> None:
    modulus_mpa = 200000.0
    hardening_mpa = 1000.0
    engineering_rows: list[RawCurveRow] = []
    expected_rows: list[tuple[float, float]] = []
    for plastic_strain in [0.0, 0.001, 0.002, 0.004, 0.008]:
        stress_true = 250.0 + hardening_mpa * plastic_strain
        total_true_strain = stress_true / modulus_mpa + plastic_strain
        engineering_strain = math.exp(total_true_strain) - 1.0
        engineering_stress = stress_true / (1.0 + engineering_strain)
        engineering_rows.append(_row(engineering_stress, engineering_strain))
        if plastic_strain >= 0.002:
            expected_rows.append((plastic_strain - 0.002, stress_true))

    result = compute_miso_from_rows(
        engineering_rows,
        _settings(curve_type="engineering", modulus_mode="manual", manual_modulus_mpa=modulus_mpa),
    )

    actual_rows = [(row.plastic_strain, row.stress_mpa) for row in result.miso_rows]
    assert len(actual_rows) == len(expected_rows)
    for actual, expected in zip(actual_rows, expected_rows):
        assert actual[0] == pytest.approx(expected[0], abs=1e-9)
        assert actual[1] == pytest.approx(expected[1], abs=1e-6)
    assert result.elastic_fit is None


def test_infer_elastic_modulus_skips_toe_region() -> None:
    modulus_mpa = 210000.0
    rows: list[RawCurveRow] = []
    for stress_mpa in [15.0, 35.0, 60.0, 90.0, 120.0, 150.0, 180.0, 250.0, 260.0, 275.0]:
        slack_strain = 0.00035 * max(0.0, 1.0 - stress_mpa / 90.0)
        plastic_strain = 0.0 if stress_mpa <= 180.0 else (stress_mpa - 180.0) / 25000.0
        total_true_strain = stress_mpa / modulus_mpa + slack_strain + plastic_strain
        rows.append(_row(stress_mpa, total_true_strain))

    fit = infer_elastic_modulus(convert_to_true_curve(rows, "true"))

    assert fit.modulus_mpa == pytest.approx(modulus_mpa, rel=5e-3)
    assert fit.point_count == 4
    assert fit.strain_min > 0.0004
    assert fit.intercept_ratio < 0.01


def test_compute_miso_from_rows_reports_stable_inference_diagnostics_for_noisy_curve() -> None:
    modulus_mpa = 205000.0
    strain_noise = [0.0, 1e-6, -1.5e-6, 2e-6, -2.5e-6, 1.5e-6, -1e-6]
    rows = [
        _row(stress_mpa, stress_mpa / modulus_mpa + perturbation)
        for stress_mpa, perturbation in zip([0.0, 40.0, 80.0, 120.0, 160.0, 200.0, 240.0], strain_noise)
    ]
    for plastic_strain in [0.0008, 0.0015, 0.0025]:
        stress_mpa = 250.0 + 1200.0 * plastic_strain
        rows.append(_row(stress_mpa, stress_mpa / modulus_mpa + plastic_strain))

    result = compute_miso_from_rows(rows, _settings())

    assert result.modulus_mpa == pytest.approx(modulus_mpa, rel=0.01)
    assert result.elastic_fit is not None
    assert result.elastic_fit.point_count >= 5
    assert result.elastic_fit.r_squared > 0.999
    assert result.elastic_fit.max_secant_deviation < 0.05


def test_infer_elastic_modulus_rejects_unstable_curve() -> None:
    rows = [
        _row(0.0, 0.0),
        _row(20.0, 0.0005),
        _row(55.0, 0.0010),
        _row(105.0, 0.0015),
        _row(170.0, 0.0020),
        _row(245.0, 0.0025),
    ]

    with pytest.raises(CurveValidationError, match="stable elastic window"):
        infer_elastic_modulus(convert_to_true_curve(rows, "true"))
