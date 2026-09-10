"""SKF rolling-bearing friction torque equations for all published families."""

from __future__ import annotations

import math

from .constants import KRS_BY_MODE, MU_EHL_BY_LUBRICANT, get_series_constants
from .drag import drag_torque_nmm
from .models import (
    BearingDefinition,
    CalibrationProfile,
    FrictionResult,
    InstallationResult,
    LubricantDefinition,
    LubricationDefinition,
    OperatingPoint,
    SealDefinition,
)
from .seals import seal_torque_nmm


def load_factors(
    bearing: BearingDefinition,
    speed_rpm: float,
    radial_load_n: float,
    axial_load_n: float,
) -> tuple[float, float]:
    """Return SKF bearing-specific Grr and Gsl load factors."""
    c = get_series_constants(bearing.family, bearing.series)
    dm = bearing.dm_mm
    n = max(speed_rpm, 0.0)
    fr = max(radial_load_n, 0.0)
    fa = max(axial_load_n, 0.0)
    a = c.coefficients

    if c.formula == "dgbb":
        r1, r2, s1, s2 = a
        if fa <= 0:
            return r1 * dm**1.96 * fr**0.54, s1 * dm**(-0.26) * fr ** (5.0 / 3.0)
        alpha_deg = 24.6 * (fa / bearing.C0_N) ** 0.24
        sin_alpha = max(math.sin(math.radians(alpha_deg)), 1e-12)
        grr = r1 * dm**1.96 * (fr + (r2 / sin_alpha) * fa) ** 0.54
        gsl = s1 * dm**(-0.145) * (
            fr**5 + (s2 * dm**1.5 / sin_alpha) * fa**4
        ) ** (1.0 / 3.0)
        return grr, gsl

    if c.formula == "angular":
        r1, r2, r3, s1, s2, s3 = a
        fg_r = r3 * dm**4 * n**2
        fg_s = s3 * dm**4 * n**2
        grr = r1 * dm**1.97 * (fr + fg_r + r2 * fa) ** 0.54
        gsl = s1 * dm**0.26 * ((fr + fg_s) ** (4.0 / 3.0) + s2 * fa ** (4.0 / 3.0))
        return grr, gsl

    if c.formula == "self_aligning_ball":
        r1, r2, r3, s1, s2, s3 = a
        fg_r = r3 * dm**3.5 * n**2
        fg_s = s3 * dm**3.5 * n**2
        grr = r1 * dm**2.0 * (fr + fg_r + r2 * fa) ** 0.54
        gsl = s1 * dm**(-0.12) * ((fr + fg_s) ** (4.0 / 3.0) + s2 * fa ** (4.0 / 3.0))
        return grr, gsl

    if c.formula == "cylindrical":
        r1, s1, s2 = a
        return r1 * dm**2.41 * fr**0.31, s1 * dm**0.9 * fa + s2 * dm * fr

    if c.formula == "tapered":
        r1, r2, s1, s2 = a
        y = bearing.Y
        return (
            r1 * dm**2.38 * (fr + r2 * y * fa) ** 0.31,
            s1 * dm**0.82 * (fr + s2 * y * fa),
        )

    if c.formula == "spherical":
        r1, r2, r3, r4, s1, s2, s3, s4 = a
        grr_e = r1 * dm**1.85 * (fr + r2 * fa) ** 0.54
        grr_l = r3 * dm**2.3 * (fr + r4 * fa) ** 0.31
        gsl_e = s1 * dm**0.25 * (fr**4 + s2 * fa**4) ** (1.0 / 3.0)
        gsl_l = s3 * dm**0.94 * (fr**3 + s4 * fa**3) ** (1.0 / 3.0)
        return min(grr_e, grr_l), min(gsl_e, gsl_l)

    if c.formula == "carb":
        r1, r2, s1, s2 = a
        threshold_r = ((r2**1.85 * dm**0.78) / r1**1.85) ** 2.35
        grr = r1 * dm**1.97 * fr**0.54 if fr < threshold_r else r2 * dm**2.37 * fr**0.31
        threshold_s = ((s2 * dm**1.24) / s1) ** 1.5
        gsl = s1 * dm**(-0.19) * fr ** (5.0 / 3.0) if fr < threshold_s else s2 * dm**1.05 * fr
        return grr, gsl

    if c.formula == "thrust_ball":
        r1, s1 = a
        return r1 * dm**1.83 * fa**0.54, s1 * dm**0.05 * fa ** (4.0 / 3.0)

    if c.formula == "cylindrical_thrust":
        r1, s1 = a
        return r1 * dm**2.38 * fa**0.31, s1 * dm**0.62 * fa

    if c.formula == "spherical_thrust":
        r1, r2, r3, r4, s1, s2, s3, s4, s5 = a
        grr_e = r1 * dm**1.96 * (fr + r2 * fa) ** 0.54
        grr_l = r3 * dm**2.39 * (fr + r4 * fa) ** 0.31
        grr = min(grr_e, grr_l)
        gsl_e = s1 * dm**(-0.35) * (fr ** (5.0 / 3.0) + s2 * fa ** (5.0 / 3.0))
        gsl_l = s3 * dm**0.89 * (fr + fa)
        gsr = min(gsl_e, gsl_l)
        gf = s4 * dm**0.76 * (fr + s5 * fa)
        # Viscosity-dependent flange term is completed in friction_torque; here
        # return the two components encoded through a negative sentinel is not
        # desirable, so calculate the base Gsr and attach Gf to a temporary
        # attribute is impossible. Re-evaluate in the caller for this family.
        return grr, gsr + gf

    raise NotImplementedError(c.formula)


def torque_to_power_w(torque_nmm: float, speed_rpm: float) -> float:
    return torque_nmm * 1e-3 * (2.0 * math.pi * speed_rpm / 60.0)


def friction_torque(
    bearing: BearingDefinition,
    operating: OperatingPoint,
    lubricant: LubricantDefinition,
    lubrication: LubricationDefinition,
    seal: SealDefinition,
    installation_result: InstallationResult,
    viscosity_cst: float,
    calibration: CalibrationProfile,
) -> FrictionResult:
    """Calculate all SKF torque components at a specified viscosity."""
    c = get_series_constants(bearing.family, bearing.series)
    n = max(operating.speed_rpm, 0.0)
    dm = bearing.dm_mm
    d = bearing.d_mm
    D = bearing.D_mm
    fr = installation_result.effective_radial_load_n
    fa = installation_result.effective_axial_load_n
    warnings: list[str] = []
    if not c.source_status.startswith("Published SKF"):
        warnings.append(c.source_status)

    grr, gsl = load_factors(bearing, n, fr, fa)
    if c.formula == "spherical_thrust":
        # Complete the published viscosity-dependent flange sliding term.
        _, _, _, _, s1, s2, s3, s4, s5 = c.coefficients
        gsl_e = s1 * dm**(-0.35) * (fr ** (5.0 / 3.0) + s2 * fa ** (5.0 / 3.0))
        gsl_l = s3 * dm**0.89 * (fr + fa)
        gsr = min(gsl_e, gsl_l)
        gf = s4 * dm**0.76 * (fr + s5 * fa)
        gsl = gsr + gf / math.exp(min(1e-6 * (n * viscosity_cst) ** 1.4 * dm, 700.0))

    phi_ish = 1.0 / (1.0 + 1.84e-9 * (n * dm) ** 1.28 * viscosity_cst**0.64)
    krs = KRS_BY_MODE[lubrication.mode.value]
    if krs == 0.0 or n == 0.0:
        phi_rs = 1.0
    else:
        exponent = krs * viscosity_cst * n * (d + D) * math.sqrt(c.kz / (2.0 * (D - d)))
        phi_rs = math.exp(-min(exponent, 700.0))

    if n > 0:
        mrr = phi_ish * phi_rs * grr * (viscosity_cst * n) ** 0.6
        phi_bl = math.exp(-min(2.6e-8 * (n * viscosity_cst) ** 1.4 * dm, 700.0))
        mu_bl = 0.12
    else:
        mrr = 0.0
        phi_bl = 1.0
        mu_bl = 0.15

    if c.formula == "cylindrical":
        mu_ehl = 0.02
    elif c.formula == "tapered":
        mu_ehl = 0.002
    else:
        mu_ehl = MU_EHL_BY_LUBRICANT[lubricant.kind.value]
    mu_sl = phi_bl * mu_bl + (1.0 - phi_bl) * mu_ehl
    msl = gsl * mu_sl

    # Apply explicitly separated installation correction to rolling/sliding only.
    install_mult = installation_result.total_torque_multiplier
    mrr *= install_mult * calibration.rolling_scale
    msl *= install_mult * calibration.sliding_scale

    mseal, seal_warnings = seal_torque_nmm(bearing, seal)
    mseal *= calibration.seal_scale
    warnings.extend(seal_warnings)
    mdrag, drag_warnings, _ = drag_torque_nmm(
        bearing,
        c,
        lubrication,
        n,
        viscosity_cst,
    )
    mdrag *= calibration.drag_scale
    warnings.extend(drag_warnings)

    total = mrr + msl + mseal + mdrag
    p_rr = torque_to_power_w(mrr, n)
    p_sl = torque_to_power_w(msl, n)
    p_seal = torque_to_power_w(mseal, n)
    p_drag = torque_to_power_w(mdrag, n)
    return FrictionResult(
        viscosity_cst=viscosity_cst,
        Grr=grr,
        Gsl=gsl,
        phi_ish=phi_ish,
        phi_rs=phi_rs,
        phi_bl=phi_bl,
        mu_sl=mu_sl,
        rolling_torque_nmm=mrr,
        sliding_torque_nmm=msl,
        seal_torque_nmm=mseal,
        drag_torque_nmm=mdrag,
        total_torque_nmm=total,
        rolling_power_w=p_rr,
        sliding_power_w=p_sl,
        seal_power_w=p_seal,
        drag_power_w=p_drag,
        total_power_w=p_rr + p_sl + p_seal + p_drag,
        warnings=warnings,
    )
