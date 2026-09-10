"""Case, calibration and tabular-data input/output."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import (
    BearingCase,
    BearingDefinition,
    BearingFamily,
    BearingQuality,
    CalibrationProfile,
    InstallationDefinition,
    LifeDefinition,
    LubricantDefinition,
    LubricantKind,
    LubricationDefinition,
    LubricationMode,
    OperatingPoint,
    SealDefinition,
    ShaftOrientation,
    SolverSettings,
    ThermalDefinition,
    ThermalModel,
)


def save_case(case: BearingCase, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(case.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def load_case(path: str | Path) -> BearingCase:
    return case_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def case_from_dict(data: dict[str, Any]) -> BearingCase:
    b = dict(data.get("bearing", {}))
    if "family" in b:
        b["family"] = BearingFamily(b["family"])
    if "quality" in b:
        b["quality"] = BearingQuality(b["quality"])

    oil = dict(data.get("lubricant", {}))
    if "kind" in oil:
        oil["kind"] = LubricantKind(oil["kind"])

    lub = dict(data.get("lubrication", {}))
    if "mode" in lub:
        lub["mode"] = LubricationMode(lub["mode"])
    if "shaft_orientation" in lub:
        lub["shaft_orientation"] = ShaftOrientation(lub["shaft_orientation"])

    thermal = dict(data.get("thermal", {}))
    if "model" in thermal:
        thermal["model"] = ThermalModel(thermal["model"])

    case = BearingCase(
        case_name=data.get("case_name", "SKF bearing case"),
        bearing=BearingDefinition(**b),
        lubricant=LubricantDefinition(**oil),
        operating=OperatingPoint(**data.get("operating", {})),
        lubrication=LubricationDefinition(**lub),
        seal=SealDefinition(**data.get("seal", {})),
        installation=InstallationDefinition(**data.get("installation", {})),
        thermal=ThermalDefinition(**thermal),
        life=LifeDefinition(**data.get("life", {})),
        calibration=CalibrationProfile(**data.get("calibration", {})),
        settings=SolverSettings(**data.get("settings", {})),
    )
    case.validate()
    return case


def save_calibration(profile: CalibrationProfile, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile.__dict__ if hasattr(profile, "__dict__") else {
        "name": profile.name,
        "rolling_scale": profile.rolling_scale,
        "sliding_scale": profile.sliding_scale,
        "seal_scale": profile.seal_scale,
        "drag_scale": profile.drag_scale,
        "heat_transfer_scale": profile.heat_transfer_scale,
        "installation_scale": profile.installation_scale,
        "notes": profile.notes,
    }, indent=2), encoding="utf-8")
    return target


def load_calibration(path: str | Path) -> CalibrationProfile:
    profile = CalibrationProfile(**json.loads(Path(path).read_text(encoding="utf-8")))
    profile.validate()
    return profile


def write_history_csv(rows: list[dict[str, float]], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        target.write_text("", encoding="utf-8")
        return target
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return target


def create_batch_template(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "case_id": "OP-001",
            "speed_rpm": 6000,
            "radial_load_n": 3000,
            "axial_load_n": 500,
            "inlet_temp_c": 70,
            "ambient_temp_c": 40,
            "oil_flow_l_min": 0.15,
            "equivalent_dynamic_load_n": "",
        },
        {
            "case_id": "OP-002",
            "speed_rpm": 12000,
            "radial_load_n": 5000,
            "axial_load_n": 1000,
            "inlet_temp_c": 85,
            "ambient_temp_c": 60,
            "oil_flow_l_min": 0.12,
            "equivalent_dynamic_load_n": "",
        },
    ]
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return target


def create_calibration_template(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "case_id": "TEST-001",
            "speed_rpm": 6000,
            "radial_load_n": 3000,
            "axial_load_n": 500,
            "inlet_temp_c": 70,
            "ambient_temp_c": 40,
            "oil_flow_l_min": 0.15,
            "measured_torque_nmm": 180,
            "measured_temperature_c": 95,
        },
        {
            "case_id": "TEST-002",
            "speed_rpm": 12000,
            "radial_load_n": 5000,
            "axial_load_n": 1000,
            "inlet_temp_c": 85,
            "ambient_temp_c": 60,
            "oil_flow_l_min": 0.12,
            "measured_torque_nmm": 340,
            "measured_temperature_c": 125,
        },
    ]
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return target
