"""Coupled viscosity, friction, thermal and rating-life solver."""

from __future__ import annotations

import math

from .friction import friction_torque
from .installation import installation_correction, rolling_element_load_distribution
from .life import calculate_life
from .models import BearingCase, CaseResult, ThermalModel
from .thermal import solve_thermal_state
from .viscosity import viscosity_cst


def solve_case(case: BearingCase) -> CaseResult:
    case.validate()
    install = installation_correction(
        case.bearing,
        case.operating,
        case.installation,
        case.calibration.installation_scale,
    )
    load_distribution = rolling_element_load_distribution(
        case.bearing,
        install.effective_radial_load_n,
        case.installation,
    )

    temp = case.thermal.inlet_temp_c
    if case.thermal.model == ThermalModel.FOUR_NODE:
        temp = max(
            case.thermal.inlet_temp_c,
            0.5 * (case.thermal.shaft_boundary_temp_c + case.thermal.housing_boundary_temp_c),
        )
    history: list[dict[str, float]] = []
    converged = False
    thermal_result = None
    friction_result = None

    for iteration in range(1, case.thermal.max_iterations + 1):
        nu = viscosity_cst(temp, case.lubricant)
        friction_result = friction_torque(
            case.bearing,
            case.operating,
            case.lubricant,
            case.lubrication,
            case.seal,
            install,
            nu,
            case.calibration,
        )
        thermal_result = solve_thermal_state(
            friction_result,
            case.thermal,
            case.lubricant,
            case.calibration,
        )
        target = thermal_result.contact_temperature_c
        next_temp = temp + case.thermal.relaxation * (target - temp)
        history.append(
            {
                "iteration": float(iteration),
                "temperature_c": temp,
                "target_temperature_c": target,
                "viscosity_cst": nu,
                "rolling_torque_nmm": friction_result.rolling_torque_nmm,
                "sliding_torque_nmm": friction_result.sliding_torque_nmm,
                "seal_torque_nmm": friction_result.seal_torque_nmm,
                "drag_torque_nmm": friction_result.drag_torque_nmm,
                "total_torque_nmm": friction_result.total_torque_nmm,
                "power_loss_w": friction_result.total_power_w,
                "delta_temperature_c": next_temp - temp,
            }
        )
        if not math.isfinite(next_temp):
            raise FloatingPointError("Thermal iteration produced a non-finite temperature.")
        if next_temp > case.settings.max_temperature_c:
            raise RuntimeError(
                f"Temperature guard exceeded ({next_temp:.1f} degC > {case.settings.max_temperature_c:.1f} degC). "
                "Check heat-transfer inputs and lubrication flow."
            )
        if abs(next_temp - temp) <= case.thermal.tolerance_c:
            temp = next_temp
            converged = True
            break
        temp = next_temp

    # Recalculate all outputs at the final temperature so reported viscosity and
    # torque correspond exactly to the returned thermal state.
    nu = viscosity_cst(temp, case.lubricant)
    friction_result = friction_torque(
        case.bearing,
        case.operating,
        case.lubricant,
        case.lubrication,
        case.seal,
        install,
        nu,
        case.calibration,
    )
    thermal_result = solve_thermal_state(
        friction_result,
        case.thermal,
        case.lubricant,
        case.calibration,
    )
    life_result = (
        calculate_life(
            case.bearing,
            case.operating,
            case.lubricant,
            case.life,
            friction_result.viscosity_cst,
        )
        if case.life.enabled
        else None
    )

    warnings: list[str] = []
    warnings.extend(install.warnings)
    warnings.extend(friction_result.warnings)
    if life_result:
        warnings.extend(life_result.warnings)
    if case.thermal.model == ThermalModel.FOUR_NODE:
        warnings.append(
            "Four-node ring/element/oil temperatures and local contact rises use user-calibrated thermal conductances/resistances."
        )
    if not load_distribution.converged:
        warnings.append("Generic rolling-element load-distribution solve did not fully converge.")
    if not converged:
        warnings.append("Coupled thermal iteration reached the maximum iteration count.")

    # De-duplicate while preserving order.
    unique_warnings = list(dict.fromkeys(warnings))
    return CaseResult(
        converged=converged,
        iterations=len(history),
        friction=friction_result,
        thermal=thermal_result,
        life=life_result,
        installation=install,
        load_distribution=load_distribution,
        history=history,
        warnings=unique_warnings,
    )
