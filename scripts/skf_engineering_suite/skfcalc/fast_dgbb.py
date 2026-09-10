"""Numba-accelerated DGBB one-node operating-map solver.

This is the retained high-throughput path from the original prototype. It is
intentionally narrower than the full solver: deep-groove ball bearings,
one-node thermal balance, no installation correction and no rating-life output.
It does include SKF rolling/sliding friction, seal torque, and the published
oil-bath/oil-jet drag equations used by the full model.
"""

from __future__ import annotations

import math

import numpy as np

from .constants import KRS_BY_MODE, MU_EHL_BY_LUBRICANT, get_series_constants
from .drag import volume_factor
from .models import BearingCase, BearingFamily, LubricationMode, ShaftOrientation, ThermalModel
from .seals import seal_torque_nmm

try:
    from numba import njit, prange

    NUMBA_AVAILABLE = True
except ImportError:  # pragma: no cover
    NUMBA_AVAILABLE = False
    njit = None
    prange = range


if NUMBA_AVAILABLE:

    @njit(cache=True)
    def _walther(nu40: float, nu100: float, temp_c: float) -> float:
        x40 = math.log10(313.15)
        x100 = math.log10(373.15)
        y40 = math.log10(math.log10(nu40 + 0.7))
        y100 = math.log10(math.log10(nu100 + 0.7))
        b = (y40 - y100) / (x100 - x40)
        a = y40 + b * x40
        y = a - b * math.log10(temp_c + 273.15)
        nu = 10.0 ** (10.0**y) - 0.7
        return max(nu, 0.05)

    @njit(cache=True, parallel=True)
    def _kernel(
        speed: np.ndarray,
        fr: np.ndarray,
        fa: np.ndarray,
        tin: np.ndarray,
        tamb: np.ndarray,
        flow: np.ndarray,
        ghouse: np.ndarray,
        d: float,
        D: float,
        C0: float,
        r1: float,
        r2: float,
        s1: float,
        s2: float,
        nu40: float,
        nu100: float,
        density: float,
        cp: float,
        mu_ehl: float,
        krs: float,
        kz: float,
        row_multiplier: float,
        oil_bypass: float,
        heat_fraction: float,
        seal_torque: float,
        fixed_drag: float,
        drag_enabled: int,
        drag_mode_code: int,
        drag_vm: float,
        drag_h: float,
        vertical_fraction: float,
        rolling_scale: float,
        sliding_scale: float,
        seal_scale: float,
        drag_scale: float,
        heat_scale: float,
        relaxation: float,
        tolerance: float,
        max_iterations: int,
    ):
        count = speed.size
        out_temp = np.empty(count)
        out_nu = np.empty(count)
        out_rr = np.empty(count)
        out_sl = np.empty(count)
        out_seal = np.empty(count)
        out_drag = np.empty(count)
        out_total = np.empty(count)
        out_power = np.empty(count)
        out_iter = np.empty(count, dtype=np.int32)
        out_conv = np.empty(count, dtype=np.bool_)
        dm = 0.5 * (d + D)
        star_geom = math.sqrt(kz / (2.0 * (D - d)))

        h = min(max(drag_h, 0.0), 1.2 * dm)
        arg = (0.6 * dm - h) / (0.6 * dm)
        arg = min(max(arg, -1.0), 1.0)
        t = 2.0 * math.acos(arg)
        ft = math.sin(0.5 * t) if t <= math.pi else 1.0
        fA = 0.05 * kz * (D + d) / (D - d)
        Rs = 0.36 * dm**2 * (t - math.sin(t)) * fA
        kball = row_multiplier * kz * (d + D) / (D - d) * 1e-12

        for i in prange(count):
            n = speed[i]
            fri = max(fr[i], 0.0)
            fai = max(fa[i], 0.0)
            if fai <= 0:
                grr = r1 * dm**1.96 * fri**0.54
                gsl = s1 * dm**(-0.26) * fri ** (5.0 / 3.0)
            else:
                alpha_deg = 24.6 * (fai / C0) ** 0.24
                sin_alpha = max(math.sin(alpha_deg * math.pi / 180.0), 1e-12)
                grr = r1 * dm**1.96 * (fri + (r2 / sin_alpha) * fai) ** 0.54
                gsl = s1 * dm**(-0.145) * (fri**5 + (s2 * dm**1.5 / sin_alpha) * fai**4) ** (1.0 / 3.0)

            oil_g = flow[i] * 1e-3 / 60.0 * density * cp * (1.0 - oil_bypass)
            house_g = ghouse[i] * heat_scale
            total_g = oil_g + house_g
            temp = tin[i]
            converged = False
            used_iterations = max_iterations
            mrr = msl = mdrag = total = power = 0.0

            for iteration in range(1, max_iterations + 1):
                nu = _walther(nu40, nu100, temp)
                phi_ish = 1.0 / (1.0 + 1.84e-9 * (n * dm) ** 1.28 * nu**0.64)
                phi_rs = 1.0 if krs == 0.0 or n == 0.0 else math.exp(-min(krs * nu * n * (d + D) * star_geom, 700.0))
                if n > 0:
                    mrr = phi_ish * phi_rs * grr * (nu * n) ** 0.6 * rolling_scale
                    phi_bl = math.exp(-min(2.6e-8 * (n * nu) ** 1.4 * dm, 700.0))
                    mu_sl = phi_bl * 0.12 + (1.0 - phi_bl) * mu_ehl
                else:
                    mrr = 0.0
                    mu_sl = 0.15
                msl = gsl * mu_sl * sliding_scale

                mdrag_model = 0.0
                if drag_enabled == 1 and n > 0 and drag_mode_code > 0:
                    hydrodynamic = 0.4 * drag_vm * kball * dm**5 * n**2
                    reynolds = n * dm**2 * ft / nu
                    common = 0.0
                    if reynolds > 0 and Rs > 0:
                        common = 1.093e-7 * n**2 * dm**3 * reynolds ** (-1.379) * Rs
                    mdrag_model = hydrodynamic + common
                    if drag_mode_code == 2:  # oil jet
                        mdrag_model *= 2.0
                    mdrag_model *= vertical_fraction
                mdrag = (mdrag_model + fixed_drag) * drag_scale
                mseal = seal_torque * seal_scale
                total = mrr + msl + mseal + mdrag
                power = total * 1e-3 * (2.0 * math.pi * n / 60.0)
                if total_g <= 0:
                    target = temp
                else:
                    target = (heat_fraction * power + house_g * tamb[i] + oil_g * tin[i]) / total_g
                next_temp = temp + relaxation * (target - temp)
                if abs(next_temp - temp) <= tolerance:
                    temp = next_temp
                    converged = True
                    used_iterations = iteration
                    break
                temp = next_temp

            # Recalculate properties and torque at the returned temperature. This
            # mirrors the full solver and avoids a small one-iteration lag in the
            # reported torque/power values at loose convergence tolerances.
            nu = _walther(nu40, nu100, temp)
            phi_ish = 1.0 / (1.0 + 1.84e-9 * (n * dm) ** 1.28 * nu**0.64)
            phi_rs = 1.0 if krs == 0.0 or n == 0.0 else math.exp(-min(krs * nu * n * (d + D) * star_geom, 700.0))
            if n > 0:
                mrr = phi_ish * phi_rs * grr * (nu * n) ** 0.6 * rolling_scale
                phi_bl = math.exp(-min(2.6e-8 * (n * nu) ** 1.4 * dm, 700.0))
                mu_sl = phi_bl * 0.12 + (1.0 - phi_bl) * mu_ehl
            else:
                mrr = 0.0
                mu_sl = 0.15
            msl = gsl * mu_sl * sliding_scale

            mdrag_model = 0.0
            if drag_enabled == 1 and n > 0 and drag_mode_code > 0:
                hydrodynamic = 0.4 * drag_vm * kball * dm**5 * n**2
                reynolds = n * dm**2 * ft / nu
                common = 0.0
                if reynolds > 0 and Rs > 0:
                    common = 1.093e-7 * n**2 * dm**3 * reynolds ** (-1.379) * Rs
                mdrag_model = hydrodynamic + common
                if drag_mode_code == 2:
                    mdrag_model *= 2.0
                mdrag_model *= vertical_fraction
            mdrag = (mdrag_model + fixed_drag) * drag_scale
            mseal = seal_torque * seal_scale
            total = mrr + msl + mseal + mdrag
            power = total * 1e-3 * (2.0 * math.pi * n / 60.0)

            out_temp[i] = temp
            out_nu[i] = nu
            out_rr[i] = mrr
            out_sl[i] = msl
            out_seal[i] = seal_torque * seal_scale
            out_drag[i] = mdrag
            out_total[i] = total
            out_power[i] = power
            out_iter[i] = used_iterations
            out_conv[i] = converged
        return out_temp, out_nu, out_rr, out_sl, out_seal, out_drag, out_total, out_power, out_iter, out_conv


def solve_numba_dgbb_map(
    case: BearingCase,
    speed_rpm: np.ndarray,
    radial_load_n: np.ndarray,
    axial_load_n: np.ndarray,
    inlet_temp_c: np.ndarray,
    ambient_temp_c: np.ndarray,
    oil_flow_l_min: np.ndarray,
    housing_conductance_w_k: np.ndarray,
) -> dict[str, np.ndarray]:
    if not NUMBA_AVAILABLE:
        raise RuntimeError("Numba is not installed.")
    if case.bearing.family != BearingFamily.DEEP_GROOVE_BALL:
        raise ValueError("Fast Numba path supports deep-groove ball bearings only.")
    if case.thermal.model != ThermalModel.ONE_NODE:
        raise ValueError("Fast Numba path supports the one-node thermal model only.")
    if case.installation.enabled:
        raise ValueError("Disable installation correction for the fast Numba path.")
    case.validate()
    c = get_series_constants(case.bearing.family, case.bearing.series)
    arrays = np.broadcast_arrays(
        np.asarray(speed_rpm, dtype=np.float64),
        np.asarray(radial_load_n, dtype=np.float64),
        np.asarray(axial_load_n, dtype=np.float64),
        np.asarray(inlet_temp_c, dtype=np.float64),
        np.asarray(ambient_temp_c, dtype=np.float64),
        np.asarray(oil_flow_l_min, dtype=np.float64),
        np.asarray(housing_conductance_w_k, dtype=np.float64),
    )
    flat = [np.ascontiguousarray(a.ravel()) for a in arrays]
    if np.any(flat[0] < 0) or np.any(flat[1] < 0) or np.any(flat[2] < 0):
        raise ValueError("Fast-path speed and loads cannot be negative.")
    if np.any(flat[5] < 0) or np.any(flat[6] < 0):
        raise ValueError("Fast-path oil flow and housing conductance cannot be negative.")
    seal_value, _ = seal_torque_nmm(case.bearing, case.seal)
    h = case.lubrication.oil_level_h_mm
    if case.lubrication.mode == LubricationMode.OIL_JET and h <= 0:
        h = 0.5 * case.bearing.rolling_element_diameter_mm if case.bearing.rolling_element_diameter_mm > 0 else 0.1 * case.bearing.dm_mm
    vm = case.lubrication.volume_factor_override or volume_factor(h / case.bearing.dm_mm, True)
    if case.lubrication.mode == LubricationMode.OIL_JET:
        drag_code = 2
    elif case.lubrication.mode in {LubricationMode.OIL_BATH_LOW, LubricationMode.OIL_BATH_NORMAL, LubricationMode.OIL_BATH_HIGH}:
        drag_code = 1
    else:
        drag_code = 0
    vertical_fraction = case.lubrication.vertical_submerged_width_fraction if case.lubrication.shaft_orientation == ShaftOrientation.VERTICAL else 1.0
    r1, r2, s1, s2 = c.coefficients
    result = _kernel(
        *flat,
        case.bearing.d_mm,
        case.bearing.D_mm,
        case.bearing.C0_N,
        r1,
        r2,
        s1,
        s2,
        case.lubricant.nu40_cst,
        case.lubricant.nu100_cst,
        case.lubricant.density_kg_m3,
        case.lubricant.cp_j_kgk,
        MU_EHL_BY_LUBRICANT[case.lubricant.kind.value],
        KRS_BY_MODE[case.lubrication.mode.value],
        c.kz,
        float(max(case.bearing.row_count, c.row_count, 1)),
        case.thermal.oil_bypass_fraction,
        case.thermal.heat_fraction_to_model,
        seal_value,
        case.lubrication.fixed_drag_torque_nmm,
        int(case.lubrication.drag_enabled),
        drag_code,
        vm,
        h,
        vertical_fraction,
        case.calibration.rolling_scale,
        case.calibration.sliding_scale,
        case.calibration.seal_scale,
        case.calibration.drag_scale,
        case.calibration.heat_transfer_scale,
        case.thermal.relaxation,
        case.thermal.tolerance_c,
        case.thermal.max_iterations,
    )
    names = [
        "contact_temperature_c",
        "viscosity_cst",
        "rolling_torque_nmm",
        "sliding_torque_nmm",
        "seal_torque_nmm",
        "drag_torque_nmm",
        "total_torque_nmm",
        "total_power_w",
        "iterations",
        "converged",
    ]
    shape = arrays[0].shape
    return {name: value.reshape(shape) for name, value in zip(names, result)}
