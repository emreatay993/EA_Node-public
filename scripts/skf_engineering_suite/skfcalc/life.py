"""Basic and modified bearing rating life calculations.

The life-modification equations implement ISO 281:2007 forms used by the SKF
standard life diagram. SKF Explorer mode applies a configurable effective
fatigue-limit-axis scale because SKF publishes the Explorer improvement as a
more favourable diagram scale rather than one universal algebraic factor.
"""

from __future__ import annotations

import bisect
import math

import numpy as np

from .constants import RELIABILITY_A1
from .models import (
    BearingDefinition,
    BearingQuality,
    LifeDefinition,
    LifeResult,
    LubricantDefinition,
    OperatingPoint,
)


def reliability_factor_a1(reliability_percent: float) -> float:
    keys = sorted(RELIABILITY_A1)
    r = float(np.clip(reliability_percent, keys[0], keys[-1]))
    if r in RELIABILITY_A1:
        return RELIABILITY_A1[r]
    idx = bisect.bisect_left(keys, r)
    lo, hi = keys[idx - 1], keys[idx]
    return RELIABILITY_A1[lo] + (RELIABILITY_A1[hi] - RELIABILITY_A1[lo]) * (r - lo) / (hi - lo)


def rated_viscosity_cst(speed_rpm: float, dm_mm: float) -> float:
    """SKF rated viscosity nu1 [cSt]."""
    if speed_rpm <= 0 or dm_mm <= 0:
        return math.inf
    if speed_rpm < 1_000:
        return 45_000.0 * speed_rpm ** (-0.83) * dm_mm ** (-0.5)
    return 4_500.0 * speed_rpm ** (-0.5) * dm_mm ** (-0.5)


def _aiso_core(kind: str, kappa: float, x: float) -> float:
    k = float(np.clip(kappa, 0.1, 4.0))
    x = float(np.clip(x, 0.0, 5.0))
    if kind == "ball":
        if k < 0.4:
            A, B = 2.2649, 0.054381
        elif k < 1.0:
            A, B = 1.9987, 0.19087
        else:
            A, B = 1.9987, 0.071739
        base = max(2.5671 - A / k**B, 0.0)
        bracket = 1.0 - base**0.83 * x ** (1.0 / 3.0)
        exponent = -9.3
    else:
        if k < 0.4:
            A, B = 1.3993, 0.054381
        elif k < 1.0:
            A, B = 1.2348, 0.19087
        else:
            A, B = 1.2348, 0.071739
        bracket = 1.0 - (1.5859 - A / k**B) * x**0.4
        exponent = -9.185
    if bracket <= 0:
        return 50.0
    return min(0.1 * bracket**exponent, 50.0)


def life_modification_factor(
    bearing: BearingDefinition,
    kappa: float,
    contamination_factor_ec: float,
    equivalent_dynamic_load_n: float,
    lubricant: LubricantDefinition,
    life: LifeDefinition,
) -> tuple[float, list[str]]:
    warnings: list[str] = []
    if equivalent_dynamic_load_n <= 0:
        return 50.0, ["Equivalent dynamic load is zero; life modification factor was capped at 50."]

    denominator_multiplier = 1.0
    if bearing.is_thrust:
        denominator_multiplier = 3.0 if bearing.is_ball else 2.5
    x = contamination_factor_ec * bearing.Cu_N / (denominator_multiplier * equivalent_dynamic_load_n)

    kind = "ball" if bearing.is_ball else "roller"
    askf_normal = _aiso_core(kind, kappa, x)
    askf = askf_normal

    # ISO treatment for proven EP additives when kappa < 1 and eC >= 0.2.
    if lubricant.proven_ep_additives and kappa < 1.0 and contamination_factor_ec >= 0.2:
        ep_value = _aiso_core(kind, 1.0, x)
        askf = max(askf_normal, min(ep_value, 3.0))
        warnings.append("Proven-EP-additive rule was applied for kappa < 1.")

    if bearing.quality == BearingQuality.SKF_EXPLORER:
        scale = life.explorer_axis_scale
        if scale <= 0:
            scale = 1.20 if bearing.is_ball else 1.44
            warnings.append(
                "Default SKF Explorer diagram-axis approximation was used; replace with a product-specific calibrated scale where available."
            )
        askf = _aiso_core(kind, max(kappa, 1.0) if lubricant.proven_ep_additives and kappa < 1 and contamination_factor_ec >= 0.2 else kappa, x * scale)
        if lubricant.proven_ep_additives and kappa < 1.0 and contamination_factor_ec >= 0.2:
            askf = max(askf_normal, min(askf, 3.0))

    return min(askf, 50.0), warnings


def equivalent_dynamic_load(
    bearing: BearingDefinition,
    operating: OperatingPoint,
) -> tuple[float, str]:
    if operating.equivalent_dynamic_load_n > 0:
        return operating.equivalent_dynamic_load_n, "User-entered equivalent dynamic load P"
    if bearing.is_thrust:
        return max(operating.axial_load_n, 1e-12), "Axial load Fa used as P (engineering default)"
    if bearing.family.value.startswith("Tapered"):
        return max(operating.radial_load_n + bearing.Y * operating.axial_load_n, 1e-12), "Fr + Y Fa engineering default"
    return max(math.hypot(operating.radial_load_n, operating.axial_load_n), 1e-12), "sqrt(Fr^2+Fa^2) engineering default"


def calculate_life(
    bearing: BearingDefinition,
    operating: OperatingPoint,
    lubricant: LubricantDefinition,
    life: LifeDefinition,
    operating_viscosity_cst: float,
) -> LifeResult:
    P, source = equivalent_dynamic_load(bearing, operating)
    p = 3.0 if bearing.is_ball else 10.0 / 3.0
    L10 = (bearing.C_N / P) ** p
    if operating.speed_rpm > 0:
        L10h = 1e6 * L10 / (60.0 * operating.speed_rpm)
    else:
        L10h = math.inf
    a1 = reliability_factor_a1(life.reliability_percent)
    nu1 = rated_viscosity_cst(operating.speed_rpm, bearing.dm_mm)
    kappa = operating_viscosity_cst / nu1 if math.isfinite(nu1) else 0.0
    askf, warnings = life_modification_factor(
        bearing,
        kappa,
        life.contamination_factor_ec,
        P,
        lubricant,
        life,
    )
    warnings.insert(0, f"Equivalent load source: {source}.")
    Lnm = a1 * askf * L10
    Lnmh = 1e6 * Lnm / (60.0 * operating.speed_rpm) if operating.speed_rpm > 0 else math.inf
    return LifeResult(
        equivalent_dynamic_load_n=P,
        load_exponent=p,
        basic_life_mrev=L10,
        basic_life_hours=L10h,
        reliability_factor_a1=a1,
        rated_viscosity_cst=nu1,
        viscosity_ratio_kappa=kappa,
        contamination_factor_ec=life.contamination_factor_ec,
        askf=askf,
        modified_life_mrev=Lnm,
        modified_life_hours=Lnmh,
        warnings=warnings,
    )
