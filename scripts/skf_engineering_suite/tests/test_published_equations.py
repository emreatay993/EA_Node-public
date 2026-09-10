from __future__ import annotations

import math

import pytest

from skfcalc.constants import REGISTRY, get_series_constants
from skfcalc.friction import friction_torque, load_factors
from skfcalc.installation import installation_correction
from skfcalc.models import BearingCase, BearingFamily, LubricationMode


def _case(family: BearingFamily, series: str) -> BearingCase:
    case = BearingCase()
    case.bearing.family = family
    case.bearing.series = series
    case.operating.speed_rpm = 7_500.0
    case.operating.radial_load_n = 4_200.0
    case.operating.axial_load_n = 1_100.0
    case.lubrication.drag_enabled = False
    return case


def test_registry_row_counts_match_transcribed_table_scope() -> None:
    assert {family: len(rows) for family, rows in REGISTRY.items()} == {
        BearingFamily.DEEP_GROOVE_BALL: 15,
        BearingFamily.ANGULAR_CONTACT_BALL: 9,
        BearingFamily.SELF_ALIGNING_BALL: 7,
        BearingFamily.CYLINDRICAL_ROLLER: 9,
        BearingFamily.TAPERED_ROLLER: 20,
        BearingFamily.SPHERICAL_ROLLER: 13,
        BearingFamily.CARB: 13,
        BearingFamily.THRUST_BALL: 1,
        BearingFamily.CYLINDRICAL_ROLLER_THRUST: 1,
        BearingFamily.SPHERICAL_ROLLER_THRUST: 5,
    }


def test_dgbb_load_factor_no_axial_reference() -> None:
    case = _case(BearingFamily.DEEP_GROOVE_BALL, "62")
    case.operating.axial_load_n = 0.0
    dm, fr = case.bearing.dm_mm, case.operating.radial_load_n
    r1, _, s1, _ = get_series_constants(case.bearing.family, case.bearing.series).coefficients
    expected = (r1 * dm**1.96 * fr**0.54, s1 * dm**-0.26 * fr ** (5 / 3))
    assert load_factors(case.bearing, case.operating.speed_rpm, fr, 0.0) == pytest.approx(expected)


def test_dgbb_load_factor_with_axial_reference() -> None:
    case = _case(BearingFamily.DEEP_GROOVE_BALL, "63")
    dm, fr, fa = case.bearing.dm_mm, case.operating.radial_load_n, case.operating.axial_load_n
    r1, r2, s1, s2 = get_series_constants(case.bearing.family, case.bearing.series).coefficients
    alpha = math.radians(24.6 * (fa / case.bearing.C0_N) ** 0.24)
    expected = (
        r1 * dm**1.96 * (fr + r2 / math.sin(alpha) * fa) ** 0.54,
        s1 * dm**-0.145 * (fr**5 + s2 * dm**1.5 / math.sin(alpha) * fa**4) ** (1 / 3),
    )
    assert load_factors(case.bearing, case.operating.speed_rpm, fr, fa) == pytest.approx(expected)


def test_angular_contact_load_factor_reference() -> None:
    case = _case(BearingFamily.ANGULAR_CONTACT_BALL, "72 B(E)")
    dm, n = case.bearing.dm_mm, case.operating.speed_rpm
    fr, fa = case.operating.radial_load_n, case.operating.axial_load_n
    r1, r2, r3, s1, s2, s3 = get_series_constants(case.bearing.family, case.bearing.series).coefficients
    expected = (
        r1 * dm**1.97 * (fr + r3 * dm**4 * n**2 + r2 * fa) ** 0.54,
        s1 * dm**0.26 * ((fr + s3 * dm**4 * n**2) ** (4 / 3) + s2 * fa ** (4 / 3)),
    )
    assert load_factors(case.bearing, n, fr, fa) == pytest.approx(expected)


def test_self_aligning_ball_load_factor_reference() -> None:
    case = _case(BearingFamily.SELF_ALIGNING_BALL, "22")
    dm, n = case.bearing.dm_mm, case.operating.speed_rpm
    fr, fa = case.operating.radial_load_n, case.operating.axial_load_n
    r1, r2, r3, s1, s2, s3 = get_series_constants(case.bearing.family, case.bearing.series).coefficients
    expected = (
        r1 * dm**2 * (fr + r3 * dm**3.5 * n**2 + r2 * fa) ** 0.54,
        s1 * dm**-0.12 * ((fr + s3 * dm**3.5 * n**2) ** (4 / 3) + s2 * fa ** (4 / 3)),
    )
    assert load_factors(case.bearing, n, fr, fa) == pytest.approx(expected)


def test_cylindrical_roller_load_factor_reference() -> None:
    case = _case(BearingFamily.CYLINDRICAL_ROLLER, "Caged N/NU/NJ/NUP 22")
    dm, fr, fa = case.bearing.dm_mm, case.operating.radial_load_n, case.operating.axial_load_n
    r1, s1, s2 = get_series_constants(case.bearing.family, case.bearing.series).coefficients
    expected = (r1 * dm**2.41 * fr**0.31, s1 * dm**0.9 * fa + s2 * dm * fr)
    assert load_factors(case.bearing, case.operating.speed_rpm, fr, fa) == pytest.approx(expected)


def test_tapered_roller_load_factor_reference() -> None:
    case = _case(BearingFamily.TAPERED_ROLLER, "322")
    dm, fr, fa, y = case.bearing.dm_mm, case.operating.radial_load_n, case.operating.axial_load_n, case.bearing.Y
    r1, r2, s1, s2 = get_series_constants(case.bearing.family, case.bearing.series).coefficients
    expected = (
        r1 * dm**2.38 * (fr + r2 * y * fa) ** 0.31,
        s1 * dm**0.82 * (fr + s2 * y * fa),
    )
    assert load_factors(case.bearing, case.operating.speed_rpm, fr, fa) == pytest.approx(expected)


def test_spherical_roller_load_factor_reference() -> None:
    case = _case(BearingFamily.SPHERICAL_ROLLER, "223 E")
    dm, fr, fa = case.bearing.dm_mm, case.operating.radial_load_n, case.operating.axial_load_n
    r1, r2, r3, r4, s1, s2, s3, s4 = get_series_constants(case.bearing.family, case.bearing.series).coefficients
    expected = (
        min(r1 * dm**1.85 * (fr + r2 * fa) ** 0.54, r3 * dm**2.3 * (fr + r4 * fa) ** 0.31),
        min(s1 * dm**0.25 * (fr**4 + s2 * fa**4) ** (1 / 3), s3 * dm**0.94 * (fr**3 + s4 * fa**3) ** (1 / 3)),
    )
    assert load_factors(case.bearing, case.operating.speed_rpm, fr, fa) == pytest.approx(expected)


def test_carb_branch_equations_reference() -> None:
    case = _case(BearingFamily.CARB, "C22")
    dm = case.bearing.dm_mm
    r1, r2, s1, s2 = get_series_constants(case.bearing.family, case.bearing.series).coefficients
    for fr in (50.0, 50_000.0):
        threshold_r = ((r2**1.85 * dm**0.78) / r1**1.85) ** 2.35
        threshold_s = ((s2 * dm**1.24) / s1) ** 1.5
        expected = (
            r1 * dm**1.97 * fr**0.54 if fr < threshold_r else r2 * dm**2.37 * fr**0.31,
            s1 * dm**-0.19 * fr ** (5 / 3) if fr < threshold_s else s2 * dm**1.05 * fr,
        )
        assert load_factors(case.bearing, case.operating.speed_rpm, fr, 0.0) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("family", "series", "expected"),
    [
        (BearingFamily.THRUST_BALL, "All thrust-ball series", "ball"),
        (BearingFamily.CYLINDRICAL_ROLLER_THRUST, "All cylindrical-roller thrust", "cyl"),
    ],
)
def test_simple_thrust_load_factors(family: BearingFamily, series: str, expected: str) -> None:
    case = _case(family, series)
    dm, fa = case.bearing.dm_mm, case.operating.axial_load_n
    coefficients = get_series_constants(family, series).coefficients
    if expected == "ball":
        r1, s1 = coefficients
        reference = (r1 * dm**1.83 * fa**0.54, s1 * dm**0.05 * fa ** (4 / 3))
    else:
        r1, s1 = coefficients
        reference = (r1 * dm**2.38 * fa**0.31, s1 * dm**0.62 * fa)
    assert load_factors(case.bearing, case.operating.speed_rpm, case.operating.radial_load_n, fa) == pytest.approx(reference)


def test_spherical_thrust_flange_term_reference() -> None:
    case = _case(BearingFamily.SPHERICAL_ROLLER_THRUST, "293 E")
    case.lubrication.mode = LubricationMode.OIL_AIR
    viscosity = 12.5
    install = installation_correction(case.bearing, case.operating, case.installation)
    result = friction_torque(
        case.bearing,
        case.operating,
        case.lubricant,
        case.lubrication,
        case.seal,
        install,
        viscosity,
        case.calibration,
    )
    dm, n = case.bearing.dm_mm, case.operating.speed_rpm
    fr, fa = case.operating.radial_load_n, case.operating.axial_load_n
    _, _, _, _, s1, s2, s3, s4, s5 = get_series_constants(case.bearing.family, case.bearing.series).coefficients
    gsr = min(
        s1 * dm**-0.35 * (fr ** (5 / 3) + s2 * fa ** (5 / 3)),
        s3 * dm**0.89 * (fr + fa),
    )
    gf = s4 * dm**0.76 * (fr + s5 * fa)
    expected_gsl = gsr + gf / math.exp(1e-6 * (n * viscosity) ** 1.4 * dm)
    assert result.Gsl == pytest.approx(expected_gsl)


def test_published_replenishment_constants_change_phi_rs() -> None:
    case = _case(BearingFamily.DEEP_GROOVE_BALL, "62")
    install = installation_correction(case.bearing, case.operating, case.installation)
    values = {}
    for mode in (LubricationMode.GREASE, LubricationMode.OIL_JET, LubricationMode.OIL_BATH_NORMAL):
        case.lubrication.mode = mode
        values[mode] = friction_torque(
            case.bearing,
            case.operating,
            case.lubricant,
            case.lubrication,
            case.seal,
            install,
            10.0,
            case.calibration,
        ).phi_rs
    assert values[LubricationMode.GREASE] < values[LubricationMode.OIL_JET] < values[LubricationMode.OIL_BATH_NORMAL]
    assert values[LubricationMode.OIL_BATH_NORMAL] == 1.0
