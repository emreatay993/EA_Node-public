from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

try:
    from .calculator import (
        BoltGeometryOverrides,
        BoltInput,
        BoltLoadRow,
        ContactEvidenceRow,
        MaterialAllowableOverrides,
        PreloadOverrideInputs,
        ProjectInput,
        bolt_from_dict,
        project_from_dict,
        project_to_dict,
    )
except ImportError:  # pragma: no cover - direct script execution fallback.
    from calculator import (  # type: ignore
        BoltGeometryOverrides,
        BoltInput,
        BoltLoadRow,
        ContactEvidenceRow,
        MaterialAllowableOverrides,
        PreloadOverrideInputs,
        ProjectInput,
        bolt_from_dict,
        project_from_dict,
        project_to_dict,
    )


ANSYS_LOAD_COLUMNS = [
    "case_id",
    "set_id",
    "bolt_id",
    "fx",
    "fy",
    "fz",
    "mx",
    "my",
    "mz",
    "axial",
    "shear_mag",
    "units",
    "source_type",
    "source_name",
    "quality_flags",
]

BOLT_TABLE_COLUMNS = [
    "bolt_id",
    "ptl_mode",
    "direct_ptl",
    "case_id",
    "set_id",
    "fx",
    "fy",
    "fz",
    "mx",
    "my",
    "mz",
    "axial",
    "shear_mag",
    "moment_arm",
    "units",
    "source_type",
    "source_name",
    "quality_flags",
    "fitting_factor",
    "separation_factor",
    "preload_ppi_nom",
    "preload_gamma",
    "preload_cmin",
    "preload_nf",
    "preload_separation_critical",
    "preload_relaxation_loss",
    "preload_creep_loss",
    "preload_thermal_loss",
    "geometry_diameter",
    "geometry_tensile_area",
    "geometry_shear_area",
    "geometry_minor_diameter_area",
    "geometry_section_modulus",
    "material_tensile_yield",
    "material_tensile_ultimate",
    "material_shear_ultimate",
    "material_bending_ultimate",
    "material_shear_yield",
    "notes",
]

NONLINEAR_EVIDENCE_COLUMNS = [
    "case_id",
    "set_id",
    "bolt_id",
    "region",
    "max_gap",
    "min_contact_pressure",
    "separated_area_fraction",
    "redistributed_ptl",
    "quality_flags",
]


def _float_cell(row: dict[str, str], key: str, default: float = 0.0) -> float:
    raw = (row.get(key) or "").strip()
    if raw == "":
        return default
    return float(raw)


def _optional_float_cell(row: dict[str, str], key: str) -> float | None:
    raw = (row.get(key) or "").strip()
    if raw == "":
        return None
    return float(raw)


def _optional_int_cell(row: dict[str, str], key: str) -> int | None:
    raw = (row.get(key) or "").strip()
    if raw == "":
        return None
    return int(raw)


def _optional_bool_cell(row: dict[str, str], key: str) -> bool | None:
    raw = (row.get(key) or "").strip().lower()
    if raw == "":
        return None
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{key} must be true/false or blank")


def load_project_json(path: str | Path) -> ProjectInput:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return project_from_dict(data)


def save_project_json(project: ProjectInput, path: str | Path) -> None:
    Path(path).write_text(json.dumps(project_to_dict(project), indent=2), encoding="utf-8")


def import_ansys_loads_csv(path: str | Path) -> list[BoltLoadRow]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row.")
        missing = [column for column in ANSYS_LOAD_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise ValueError(f"Missing Ansys load columns: {', '.join(missing)}")
        rows: list[BoltLoadRow] = []
        for index, raw in enumerate(reader, start=2):
            try:
                rows.append(
                    BoltLoadRow(
                        case_id=(raw.get("case_id") or "").strip(),
                        set_id=(raw.get("set_id") or "").strip(),
                        bolt_id=(raw.get("bolt_id") or "").strip(),
                        fx=_float_cell(raw, "fx"),
                        fy=_float_cell(raw, "fy"),
                        fz=_float_cell(raw, "fz"),
                        mx=_float_cell(raw, "mx"),
                        my=_float_cell(raw, "my"),
                        mz=_float_cell(raw, "mz"),
                        axial=_float_cell(raw, "axial"),
                        shear_mag=_float_cell(raw, "shear_mag"),
                        units=(raw.get("units") or "").strip(),
                        source_type=(raw.get("source_type") or "").strip(),
                        source_name=(raw.get("source_name") or "").strip(),
                        quality_flags=(raw.get("quality_flags") or "").strip(),
                    )
                )
            except ValueError as exc:
                raise ValueError(f"Invalid numeric value on CSV row {index}: {exc}") from exc
    return rows


def export_ansys_loads_csv(rows: Iterable[BoltLoadRow], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ANSYS_LOAD_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: getattr(row, column) for column in ANSYS_LOAD_COLUMNS})


def bolt_inputs_from_load_rows(rows: Iterable[BoltLoadRow], ptl_mode: str = "axial") -> list[BoltInput]:
    bolts: list[BoltInput] = []
    for row in rows:
        bolts.append(BoltInput(bolt_id=row.bolt_id, direct_ptl=None, ptl_mode=ptl_mode, load_row=row))
    return bolts


def import_bolt_table_csv(path: str | Path) -> list[BoltInput]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row.")
        missing = [column for column in BOLT_TABLE_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise ValueError(f"Missing bolt table columns: {', '.join(missing)}")
        bolts: list[BoltInput] = []
        for index, raw in enumerate(reader, start=2):
            try:
                load = BoltLoadRow(
                    case_id=(raw.get("case_id") or "").strip(),
                    set_id=(raw.get("set_id") or "").strip(),
                    bolt_id=(raw.get("bolt_id") or "").strip(),
                    fx=_float_cell(raw, "fx"),
                    fy=_float_cell(raw, "fy"),
                    fz=_float_cell(raw, "fz"),
                    mx=_float_cell(raw, "mx"),
                    my=_float_cell(raw, "my"),
                    mz=_float_cell(raw, "mz"),
                    axial=_float_cell(raw, "axial"),
                    shear_mag=_float_cell(raw, "shear_mag"),
                    units=(raw.get("units") or "").strip(),
                    source_type=(raw.get("source_type") or "").strip(),
                    source_name=(raw.get("source_name") or "").strip(),
                    quality_flags=(raw.get("quality_flags") or "").strip(),
                )
                bolts.append(
                    BoltInput(
                        bolt_id=(raw.get("bolt_id") or "").strip(),
                        ptl_mode=(raw.get("ptl_mode") or "direct").strip(),  # type: ignore[arg-type]
                        direct_ptl=_optional_float_cell(raw, "direct_ptl"),
                        load_row=load,
                        moment_arm=_optional_float_cell(raw, "moment_arm"),
                        fitting_factor=_optional_float_cell(raw, "fitting_factor"),
                        separation_factor=_optional_float_cell(raw, "separation_factor"),
                        preload_override=PreloadOverrideInputs(
                            ppi_nom=_optional_float_cell(raw, "preload_ppi_nom"),
                            gamma=_optional_float_cell(raw, "preload_gamma"),
                            cmin=_optional_float_cell(raw, "preload_cmin"),
                            nf=_optional_int_cell(raw, "preload_nf"),
                            separation_critical=_optional_bool_cell(raw, "preload_separation_critical"),
                            relaxation_loss=_optional_float_cell(raw, "preload_relaxation_loss"),
                            creep_loss=_optional_float_cell(raw, "preload_creep_loss"),
                            thermal_loss=_optional_float_cell(raw, "preload_thermal_loss"),
                        ),
                        geometry_override=BoltGeometryOverrides(
                            diameter=_optional_float_cell(raw, "geometry_diameter"),
                            tensile_area=_optional_float_cell(raw, "geometry_tensile_area"),
                            shear_area=_optional_float_cell(raw, "geometry_shear_area"),
                            minor_diameter_area=_optional_float_cell(raw, "geometry_minor_diameter_area"),
                            section_modulus=_optional_float_cell(raw, "geometry_section_modulus"),
                        ),
                        material_override=MaterialAllowableOverrides(
                            tensile_yield=_optional_float_cell(raw, "material_tensile_yield"),
                            tensile_ultimate=_optional_float_cell(raw, "material_tensile_ultimate"),
                            shear_ultimate=_optional_float_cell(raw, "material_shear_ultimate"),
                            bending_ultimate=_optional_float_cell(raw, "material_bending_ultimate"),
                            shear_yield=_optional_float_cell(raw, "material_shear_yield"),
                        ),
                        notes=(raw.get("notes") or "").strip(),
                    )
                )
            except ValueError as exc:
                raise ValueError(f"Invalid numeric value on CSV row {index}: {exc}") from exc
    return bolts


def export_bolt_table_csv(bolts: Iterable[BoltInput], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BOLT_TABLE_COLUMNS)
        writer.writeheader()
        for bolt in bolts:
            load = bolt.load_row
            writer.writerow(
                {
                    "bolt_id": bolt.bolt_id,
                    "ptl_mode": bolt.ptl_mode,
                    "direct_ptl": "" if bolt.direct_ptl is None else bolt.direct_ptl,
                    "case_id": load.case_id,
                    "set_id": load.set_id,
                    "fx": load.fx,
                    "fy": load.fy,
                    "fz": load.fz,
                    "mx": load.mx,
                    "my": load.my,
                    "mz": load.mz,
                    "axial": load.axial,
                    "shear_mag": load.shear_mag,
                    "moment_arm": "" if bolt.moment_arm is None else bolt.moment_arm,
                    "units": load.units,
                    "source_type": load.source_type,
                    "source_name": load.source_name,
                    "quality_flags": load.quality_flags,
                    "fitting_factor": "" if bolt.fitting_factor is None else bolt.fitting_factor,
                    "separation_factor": "" if bolt.separation_factor is None else bolt.separation_factor,
                    "preload_ppi_nom": "" if bolt.preload_override.ppi_nom is None else bolt.preload_override.ppi_nom,
                    "preload_gamma": "" if bolt.preload_override.gamma is None else bolt.preload_override.gamma,
                    "preload_cmin": "" if bolt.preload_override.cmin is None else bolt.preload_override.cmin,
                    "preload_nf": "" if bolt.preload_override.nf is None else bolt.preload_override.nf,
                    "preload_separation_critical": (
                        "" if bolt.preload_override.separation_critical is None else bolt.preload_override.separation_critical
                    ),
                    "preload_relaxation_loss": (
                        "" if bolt.preload_override.relaxation_loss is None else bolt.preload_override.relaxation_loss
                    ),
                    "preload_creep_loss": "" if bolt.preload_override.creep_loss is None else bolt.preload_override.creep_loss,
                    "preload_thermal_loss": "" if bolt.preload_override.thermal_loss is None else bolt.preload_override.thermal_loss,
                    "geometry_diameter": "" if bolt.geometry_override.diameter is None else bolt.geometry_override.diameter,
                    "geometry_tensile_area": (
                        "" if bolt.geometry_override.tensile_area is None else bolt.geometry_override.tensile_area
                    ),
                    "geometry_shear_area": "" if bolt.geometry_override.shear_area is None else bolt.geometry_override.shear_area,
                    "geometry_minor_diameter_area": (
                        "" if bolt.geometry_override.minor_diameter_area is None else bolt.geometry_override.minor_diameter_area
                    ),
                    "geometry_section_modulus": (
                        "" if bolt.geometry_override.section_modulus is None else bolt.geometry_override.section_modulus
                    ),
                    "material_tensile_yield": (
                        "" if bolt.material_override.tensile_yield is None else bolt.material_override.tensile_yield
                    ),
                    "material_tensile_ultimate": (
                        "" if bolt.material_override.tensile_ultimate is None else bolt.material_override.tensile_ultimate
                    ),
                    "material_shear_ultimate": (
                        "" if bolt.material_override.shear_ultimate is None else bolt.material_override.shear_ultimate
                    ),
                    "material_bending_ultimate": (
                        "" if bolt.material_override.bending_ultimate is None else bolt.material_override.bending_ultimate
                    ),
                    "material_shear_yield": (
                        "" if bolt.material_override.shear_yield is None else bolt.material_override.shear_yield
                    ),
                    "notes": bolt.notes,
                }
            )


def import_nonlinear_evidence_csv(path: str | Path) -> list[ContactEvidenceRow]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row.")
        missing = [column for column in NONLINEAR_EVIDENCE_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise ValueError(f"Missing nonlinear evidence columns: {', '.join(missing)}")
        rows: list[ContactEvidenceRow] = []
        for index, raw in enumerate(reader, start=2):
            try:
                rows.append(
                    ContactEvidenceRow(
                        case_id=(raw.get("case_id") or "").strip(),
                        set_id=(raw.get("set_id") or "").strip(),
                        bolt_id=(raw.get("bolt_id") or "").strip(),
                        region=(raw.get("region") or "").strip(),
                        max_gap=_float_cell(raw, "max_gap"),
                        min_contact_pressure=_float_cell(raw, "min_contact_pressure"),
                        separated_area_fraction=_float_cell(raw, "separated_area_fraction"),
                        redistributed_ptl=_float_cell(raw, "redistributed_ptl"),
                        quality_flags=(raw.get("quality_flags") or "").strip(),
                    )
                )
            except ValueError as exc:
                raise ValueError(f"Invalid numeric value on CSV row {index}: {exc}") from exc
    return rows


def export_nonlinear_evidence_csv(rows: Iterable[ContactEvidenceRow], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=NONLINEAR_EVIDENCE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: getattr(row, column) for column in NONLINEAR_EVIDENCE_COLUMNS})


def load_bolt_json(path: str | Path) -> list[BoltInput]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [bolt_from_dict(item) for item in data]
