from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "bladeout_compensation_ratio_calculator.py"
)


def load_tool_module():
    spec = importlib.util.spec_from_file_location(
        "bladeout_compensation_ratio_calculator", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_calculates_reference_modulus_strength_and_utilization_ratios() -> None:
    tool = load_tool_module()

    results = tool.calculate_ratios(100.0, 90.0, 900.0, 600.0)

    assert results["stiffness_retention"] == pytest.approx(0.9)
    assert results["strain_equivalence_multiplier"] == pytest.approx(1.0 / 0.9)
    assert results["strength_retention"] == pytest.approx(2.0 / 3.0)
    assert results["strength_ratio"] == pytest.approx(1.5)
    assert results["utilization_screening_factor"] == pytest.approx(1.35)


def test_validation_mode_excludes_strength_and_explains_the_claim() -> None:
    tool = load_tool_module()

    results = tool.calculate_ratios(100.0, 90.0)

    assert set(results) == {
        "stiffness_retention",
        "strain_equivalence_multiplier",
        "modulus_change_percent",
    }
    guidance = tool.guidance_for_mode(tool.VALIDATION_MODE)
    assert "Do not apply a material strength ratio" in guidance
    assert "incremental room-temperature test response" in guidance


def test_accepts_decimal_comma_and_rejects_invalid_properties() -> None:
    tool = load_tool_module()

    assert math.isclose(tool.parse_number("100,5", "E"), 100.5)
    assert math.isclose(tool.parse_number(" 1 000.25 ", "E"), 1000.25)
    with pytest.raises(ValueError, match="greater than zero"):
        tool.parse_number("0", "E")
    with pytest.raises(ValueError, match="finite"):
        tool.parse_number("nan", "E")
    with pytest.raises(ValueError, match="both room and hot"):
        tool.calculate_ratios(100.0, 90.0, 900.0)


def test_summary_labels_validation_and_utilization_outputs() -> None:
    tool = load_tool_module()
    validation_results = tool.calculate_ratios(100.0, 90.0)
    validation_summary = tool.build_summary(
        mode=tool.VALIDATION_MODE,
        material="Ti6242",
        assessment_point="HPC1",
        room_temperature=25.0,
        hot_temperature=350.0,
        e_room=100.0,
        e_hot=90.0,
        results=validation_results,
    )
    assert "Strength ratio applied: NO" in validation_summary

    utilization_results = tool.calculate_ratios(100.0, 90.0, 900.0, 600.0)
    utilization_summary = tool.build_summary(
        mode=tool.UTILIZATION_MODE,
        material="Ti6242",
        assessment_point="HPC1",
        room_temperature=25.0,
        hot_temperature=350.0,
        e_room=100.0,
        e_hot=90.0,
        results=utilization_results,
        strength_basis="Yield strength",
        strength_room=900.0,
        strength_hot=600.0,
    )
    assert "Utilization screening factor" in utilization_summary
    assert "1.3500" in utilization_summary
