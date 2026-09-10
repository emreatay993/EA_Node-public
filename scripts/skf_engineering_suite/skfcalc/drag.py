"""SKF oil-bath and oil-jet drag-loss model."""

from __future__ import annotations

import math

import numpy as np

from .constants import SeriesConstants
from .models import (
    BearingDefinition,
    LubricationDefinition,
    LubricationMode,
    ShaftOrientation,
)

# Digitized engineering representation of SKF's VM diagram. The published
# equation uses VM from a graph; values are therefore visibly tagged as a graph
# digitization rather than exact tabular data.
_VM_X = np.array([0.0, 0.025, 0.05, 0.075, 0.10, 0.125, 0.15, 0.175, 0.20, 0.30, 0.50, 0.80, 1.00, 1.20, 1.40])
_VM_BALL = np.array([0.0, 2e-6, 1.2e-5, 3.0e-5, 6.5e-5, 1.0e-4, 1.45e-4, 1.95e-4, 2.45e-4, 3.8e-4, 5.5e-4, 8.0e-4, 1.0e-3, 1.25e-3, 1.25e-3])
_VM_ROLLER = np.array([0.0, 5e-6, 3.0e-5, 6.0e-5, 1.0e-4, 1.5e-4, 2.1e-4, 2.6e-4, 3.0e-4, 4.8e-4, 6.8e-4, 1.0e-3, 1.25e-3, 1.5e-3, 1.5e-3])


def volume_factor(h_over_dm: float, is_ball: bool) -> float:
    x = float(np.clip(h_over_dm, _VM_X[0], _VM_X[-1]))
    return float(np.interp(x, _VM_X, _VM_BALL if is_ball else _VM_ROLLER))


def drag_torque_nmm(
    bearing: BearingDefinition,
    constants: SeriesConstants,
    lubrication: LubricationDefinition,
    speed_rpm: float,
    viscosity_cst: float,
) -> tuple[float, list[str], dict[str, float]]:
    """Return SKF drag torque, warnings and intermediate values.

    The SKF relation is applicable to a large oil reservoir, horizontal shaft,
    rotating inner ring and constant speed. Vertical-shaft and oil-jet
    multipliers follow the published guidance.
    """
    warnings: list[str] = []
    details: dict[str, float] = {}
    fixed = max(lubrication.fixed_drag_torque_nmm, 0.0)
    if not lubrication.drag_enabled or speed_rpm <= 0:
        return fixed, warnings, details
    if lubrication.mode in {LubricationMode.GREASE, LubricationMode.OIL_AIR}:
        return fixed, warnings, details

    dm = bearing.dm_mm
    d = bearing.d_mm
    D = bearing.D_mm
    n = speed_rpm
    h = min(max(lubrication.oil_level_h_mm, 0.0), 1.2 * dm)
    if lubrication.mode == LubricationMode.OIL_JET and h <= 0:
        if bearing.rolling_element_diameter_mm > 0:
            h = 0.5 * bearing.rolling_element_diameter_mm
        else:
            h = 0.10 * dm
        warnings.append("Oil-jet equivalent immersion H was estimated because H was zero.")

    x = h / dm if dm > 0 else 0.0
    vm = lubrication.volume_factor_override or volume_factor(x, bearing.is_ball)
    if lubrication.volume_factor_override == 0:
        warnings.append("VM was interpolated from a digitized SKF graph.")

    arg = (0.6 * dm - h) / (0.6 * dm)
    arg = float(np.clip(arg, -1.0, 1.0))
    t = 2.0 * math.acos(arg)
    ft = math.sin(0.5 * t) if t <= math.pi else 1.0
    fA = 0.05 * constants.kz * (D + d) / (D - d)
    Rs = 0.36 * dm**2 * (t - math.sin(t)) * fA

    common = 0.0
    reynolds_term = n * dm**2 * ft / max(viscosity_cst, 1e-12)
    if reynolds_term > 0 and Rs > 0:
        common = 1.093e-7 * n**2 * dm**3 * reynolds_term ** (-1.379) * Rs

    if bearing.is_ball:
        i_rw = max(bearing.row_count, constants.row_count, 1)
        kball = i_rw * constants.kz * (d + D) / (D - d) * 1e-12
        hydrodynamic = 0.4 * vm * kball * dm**5 * n**2
    else:
        if constants.kl is None:
            raise ValueError("Roller-bearing drag model requires KL.")
        kroll = constants.kl * constants.kz * (d + D) / (D - d) * 1e-12
        lD = 5.0 * constants.kl * bearing.B_mm / dm
        Cw = max(2.789e-10 * lD**3 - 2.786e-4 * lD**2 + 0.0195 * lD + 0.6439, 0.0)
        hydrodynamic = 4.0 * vm * kroll * Cw * bearing.B_mm * dm**4 * n**2
        details.update({"lD": lD, "Cw": Cw, "Kroll": kroll})

    model_torque = hydrodynamic + common
    if lubrication.mode == LubricationMode.OIL_JET:
        model_torque *= 2.0
    if lubrication.shaft_orientation == ShaftOrientation.VERTICAL:
        model_torque *= lubrication.vertical_submerged_width_fraction
        warnings.append("Vertical-shaft correction uses the entered submerged-width fraction.")

    if (h <= 0.5 * D and viscosity_cst > 500) or (h > 0.5 * D and viscosity_cst > 250):
        warnings.append("Viscosity is outside the published SKF drag-model limit for the entered oil level.")

    details.update(
        {
            "H_mm": h,
            "H_over_dm": x,
            "VM": vm,
            "t_rad": t,
            "ft": ft,
            "fA": fA,
            "Rs_mm2": Rs,
            "hydrodynamic_torque_nmm": hydrodynamic,
            "rotating_volume_torque_nmm": common,
        }
    )
    return model_torque + fixed, warnings, details
