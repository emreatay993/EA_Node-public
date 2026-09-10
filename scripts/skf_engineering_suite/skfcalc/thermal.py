"""Steady bearing thermal models.

The one-node model is a simple energy balance. The four-node network is an
engineering extension that resolves inner ring, rolling elements, outer ring and
lubricant. Conductances and local contact thermal resistances are installation-
specific calibration inputs, not SKF catalogue constants.
"""

from __future__ import annotations

import numpy as np

from .models import (
    CalibrationProfile,
    FrictionResult,
    LubricantDefinition,
    ThermalDefinition,
    ThermalModel,
    ThermalResult,
)


def oil_mass_flow_kg_s(flow_l_min: float, density_kg_m3: float) -> float:
    return flow_l_min * 1e-3 / 60.0 * density_kg_m3


def solve_thermal_state(
    friction: FrictionResult,
    thermal: ThermalDefinition,
    lubricant: LubricantDefinition,
    calibration: CalibrationProfile,
) -> ThermalResult:
    if thermal.model == ThermalModel.ONE_NODE:
        return _one_node(friction, thermal, lubricant, calibration)
    return _four_node(friction, thermal, lubricant, calibration)


def _one_node(
    friction: FrictionResult,
    thermal: ThermalDefinition,
    lubricant: LubricantDefinition,
    calibration: CalibrationProfile,
) -> ThermalResult:
    mdot = oil_mass_flow_kg_s(thermal.oil_flow_l_min, lubricant.density_kg_m3)
    oil_g = mdot * lubricant.cp_j_kgk * (1.0 - thermal.oil_bypass_fraction)
    ghouse = thermal.one_node_housing_conductance_w_k * calibration.heat_transfer_scale
    total_g = ghouse + oil_g
    if total_g <= 0:
        raise ValueError("The one-node thermal model has zero heat-removal conductance.")
    q = thermal.heat_fraction_to_model * friction.total_power_w
    t = (
        q
        + ghouse * thermal.ambient_temp_c
        + oil_g * thermal.inlet_temp_c
    ) / total_g
    q_house = ghouse * (t - thermal.ambient_temp_c)
    q_oil = oil_g * (t - thermal.inlet_temp_c)
    return ThermalResult(
        contact_temperature_c=t,
        inner_ring_temperature_c=t,
        rolling_element_temperature_c=t,
        outer_ring_temperature_c=t,
        oil_outlet_temperature_c=t,
        inner_contact_temperature_c=t,
        outer_contact_temperature_c=t,
        heat_to_shaft_w=0.0,
        heat_to_housing_w=q_house,
        heat_to_oil_w=q_oil,
    )


def _four_node(
    friction: FrictionResult,
    thermal: ThermalDefinition,
    lubricant: LubricantDefinition,
    calibration: CalibrationProfile,
) -> ThermalResult:
    scale = calibration.heat_transfer_scale
    gis = thermal.G_inner_shaft_w_k * scale
    goh = thermal.G_outer_housing_w_k * scale
    gie = thermal.G_inner_element_w_k * scale
    goe = thermal.G_outer_element_w_k * scale
    gio = thermal.G_inner_oil_w_k * scale
    goo = thermal.G_outer_oil_w_k * scale
    geo = thermal.G_element_oil_w_k * scale
    mdot = oil_mass_flow_kg_s(thermal.oil_flow_l_min, lubricant.density_kg_m3)
    goil = mdot * lubricant.cp_j_kgk * (1.0 - thermal.oil_bypass_fraction)

    if gis + goh + gie + goe + gio + goo + geo + goil <= 0:
        raise ValueError("The four-node thermal network has no positive conductance.")

    # Normalize the user-entered contact heat fractions in case they do not sum
    # exactly to one. All rolling/sliding heat is assigned to the three solids.
    shares = np.array(
        [
            thermal.inner_race_heat_fraction,
            thermal.element_heat_fraction,
            thermal.outer_race_heat_fraction,
        ],
        dtype=float,
    )
    if float(shares.sum()) <= 0:
        shares[:] = (0.30, 0.35, 0.35)
    shares /= shares.sum()

    q_contact = thermal.heat_fraction_to_model * (
        friction.rolling_power_w + friction.sliding_power_w
    )
    q_seal = thermal.heat_fraction_to_model * friction.seal_power_w
    q_drag = thermal.heat_fraction_to_model * friction.drag_power_w

    q_i = q_contact * shares[0] + q_seal * (1.0 - thermal.seal_heat_to_outer_fraction)
    q_e = q_contact * shares[1] + q_drag * (1.0 - thermal.drag_heat_to_oil_fraction)
    q_o = q_contact * shares[2] + q_seal * thermal.seal_heat_to_outer_fraction
    q_l = q_drag * thermal.drag_heat_to_oil_fraction

    # Nodes: inner ring, rolling element, outer ring, oil.
    A = np.array(
        [
            [gis + gie + gio, -gie, 0.0, -gio],
            [-gie, gie + goe + geo, -goe, -geo],
            [0.0, -goe, goh + goe + goo, -goo],
            [-gio, -geo, -goo, gio + geo + goo + goil],
        ],
        dtype=float,
    )
    b = np.array(
        [
            q_i + gis * thermal.shaft_boundary_temp_c,
            q_e,
            q_o + goh * thermal.housing_boundary_temp_c,
            q_l + goil * thermal.inlet_temp_c,
        ],
        dtype=float,
    )
    try:
        ti, te, to, tl = np.linalg.solve(A, b)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Four-node thermal network is singular; add a boundary conductance.") from exc

    # Engineering local contact-temperature estimates. The user-specified Rth
    # represents the unresolved constriction/flash resistance of each contact.
    q_inner_contact = q_contact * shares[0]
    q_outer_contact = q_contact * shares[2]
    tic = 0.5 * (ti + te) + q_inner_contact * thermal.inner_contact_rth_k_w
    toc = 0.5 * (to + te) + q_outer_contact * thermal.outer_contact_rth_k_w
    contact = 0.5 * (tic + toc)

    q_shaft = gis * (ti - thermal.shaft_boundary_temp_c)
    q_housing = goh * (to - thermal.housing_boundary_temp_c)
    q_oil = goil * (tl - thermal.inlet_temp_c)
    return ThermalResult(
        contact_temperature_c=float(contact),
        inner_ring_temperature_c=float(ti),
        rolling_element_temperature_c=float(te),
        outer_ring_temperature_c=float(to),
        oil_outlet_temperature_c=float(tl),
        inner_contact_temperature_c=float(tic),
        outer_contact_temperature_c=float(toc),
        heat_to_shaft_w=float(q_shaft),
        heat_to_housing_w=float(q_housing),
        heat_to_oil_w=float(q_oil),
    )
