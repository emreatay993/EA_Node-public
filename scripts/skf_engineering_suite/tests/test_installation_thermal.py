from __future__ import annotations

import pytest

from skfcalc.installation import installation_correction, rolling_element_load_distribution
from skfcalc.models import BearingCase, ThermalModel
from skfcalc.solver import solve_case


def test_installation_extension_can_be_disabled() -> None:
    case = BearingCase()
    result = installation_correction(case.bearing, case.operating, case.installation)
    assert result.total_torque_multiplier == 1.0
    assert result.effective_radial_load_n == case.operating.radial_load_n


def test_negative_clearance_induces_preload_when_stiffness_given() -> None:
    case = BearingCase()
    case.installation.enabled = True
    case.installation.operating_clearance_um = -5.0
    case.installation.clearance_stiffness_n_per_um = 100.0
    result = installation_correction(case.bearing, case.operating, case.installation)
    assert result.induced_preload_n == 500.0
    assert result.effective_radial_load_n > case.operating.radial_load_n
    assert result.total_torque_multiplier > 1.0


def test_load_distribution_balances_and_is_nonnegative() -> None:
    case = BearingCase()
    result = rolling_element_load_distribution(case.bearing, 5000.0, case.installation)
    assert result.converged
    assert result.maximum_element_load_n > 0
    assert all(load >= 0 for load in result.element_loads_n)
    assert 1 <= result.loaded_element_count <= case.bearing.rolling_element_count


def test_four_node_energy_rejection_matches_generated_heat() -> None:
    case = BearingCase()
    result = solve_case(case)
    rejected = result.thermal.heat_to_shaft_w + result.thermal.heat_to_housing_w + result.thermal.heat_to_oil_w
    assert rejected == pytest.approx(case.thermal.heat_fraction_to_model * result.friction.total_power_w, rel=1e-9, abs=1e-8)


def test_one_node_and_four_node_are_selectable() -> None:
    case = BearingCase()
    four = solve_case(case)
    case.thermal.model = ThermalModel.ONE_NODE
    one = solve_case(case)
    assert four.thermal.inner_ring_temperature_c != four.thermal.outer_ring_temperature_c
    assert one.thermal.inner_ring_temperature_c == one.thermal.outer_ring_temperature_c
