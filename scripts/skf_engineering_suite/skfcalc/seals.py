"""SKF contact-seal friction torque tables."""

from __future__ import annotations

from dataclasses import dataclass

from .models import BearingDefinition, BearingFamily, SealDefinition


@dataclass(frozen=True, slots=True)
class SealRow:
    Ks1: float
    Ks2: float
    beta: float
    diameter_field: str
    description: str


def _diameter(bearing: BearingDefinition, field: str, manual: float) -> float:
    if manual > 0:
        return manual
    value = {
        "d1": bearing.d1_mm,
        "d2": bearing.d2_mm,
        "E": bearing.E_mm,
    }.get(field, 0.0)
    if value <= 0:
        raise ValueError(f"Seal table requires positive bearing dimension {field} or a manual seal diameter.")
    return value


def _lookup_row(bearing: BearingDefinition, seal_type: str) -> SealRow:
    D = bearing.D_mm
    family = bearing.family
    code = seal_type.upper().strip()

    if code == "MANUAL":
        raise RuntimeError("Manual rows are handled separately.")

    if family == BearingFamily.DEEP_GROOVE_BALL and code == "RSL":
        if D <= 25:
            return SealRow(0.0, 0.0, 0.0, "d2", "DGBB RSL, D <= 25 mm")
        if D <= 52:
            return SealRow(0.0018, 0.0, 2.25, "d2", "DGBB RSL, 25 < D <= 52 mm")
    if family == BearingFamily.DEEP_GROOVE_BALL and code == "RSH" and D <= 52:
        return SealRow(0.028, 2.0, 2.25, "d2", "DGBB RSH, D <= 52 mm")
    if family == BearingFamily.DEEP_GROOVE_BALL and code == "RS1":
        if D <= 62:
            return SealRow(0.023, 2.0, 2.25, "d2", "DGBB RS1, D <= 62 mm")
        if D <= 80:
            return SealRow(0.018, 20.0, 2.25, "d2", "DGBB RS1, 62 < D <= 80 mm")
        if D <= 100:
            return SealRow(0.018, 15.0, 2.25, "d2", "DGBB RS1, 80 < D <= 100 mm")
        return SealRow(0.018, 0.0, 2.25, "d2", "DGBB RS1, D > 100 mm")
    if family == BearingFamily.ANGULAR_CONTACT_BALL and code == "RS1" and 30 <= D <= 120:
        return SealRow(0.014, 10.0, 2.0, "d1", "Angular-contact RS1")
    if family == BearingFamily.SELF_ALIGNING_BALL and code == "RS1" and 30 <= D <= 125:
        return SealRow(0.014, 10.0, 2.0, "d2", "Self-aligning ball RS1")
    if family == BearingFamily.CYLINDRICAL_ROLLER and code == "LS" and 42 <= D <= 360:
        return SealRow(0.032, 50.0, 2.0, "E", "Cylindrical roller LS")
    if family in {BearingFamily.SPHERICAL_ROLLER, BearingFamily.CARB} and code in {"CS", "CS2", "CS5"}:
        limit = 300 if family == BearingFamily.SPHERICAL_ROLLER else 340
        valid_range = 42 <= D <= limit if family == BearingFamily.CARB else 62 <= D <= limit
        if valid_range:
            return SealRow(0.057, 50.0, 2.0, "d2", f"{family.value} {code}")

    raise ValueError(
        f"No published SKF seal-table row for {family.value}, seal {seal_type}, D={D:g} mm. "
        "Use Manual only with verified product data."
    )


def seal_torque_nmm(
    bearing: BearingDefinition,
    seal: SealDefinition,
) -> tuple[float, list[str]]:
    """Return seal torque [N mm] and notes/warnings."""
    if seal.count == 0 or seal.seal_type.lower() in {"none", "open"}:
        return 0.0, []

    warnings: list[str] = []
    if seal.seal_type.upper() == "MANUAL":
        if seal.manual_diameter_mm <= 0:
            raise ValueError("Manual seal model requires a positive seal diameter.")
        row = SealRow(
            seal.manual_Ks1,
            seal.manual_Ks2,
            seal.manual_beta,
            "manual",
            "Manual seal coefficients",
        )
        ds = seal.manual_diameter_mm
        warnings.append("Manual seal coefficients were used; verify them against product data.")
    else:
        row = _lookup_row(bearing, seal.seal_type)
        ds = _diameter(bearing, row.diameter_field, seal.manual_diameter_mm)

    two_seal_reference = row.Ks1 * ds**row.beta + row.Ks2
    # SKF normally uses half the two-seal result for one seal. RSL deep-groove
    # bearings with D > 25 mm are the published exception.
    if seal.count == 1:
        if (
            bearing.family == BearingFamily.DEEP_GROOVE_BALL
            and seal.seal_type.upper() == "RSL"
            and bearing.D_mm > 25
        ):
            multiplier = 1.0
        else:
            multiplier = 0.5
    else:
        multiplier = 1.0
    return multiplier * two_seal_reference, warnings


def compatible_seal_types(family: BearingFamily) -> list[str]:
    common = ["None", "Manual"]
    return {
        BearingFamily.DEEP_GROOVE_BALL: ["None", "RSL", "RSH", "RS1", "Manual"],
        BearingFamily.ANGULAR_CONTACT_BALL: ["None", "RS1", "Manual"],
        BearingFamily.SELF_ALIGNING_BALL: ["None", "RS1", "Manual"],
        BearingFamily.CYLINDRICAL_ROLLER: ["None", "LS", "Manual"],
        BearingFamily.SPHERICAL_ROLLER: ["None", "CS", "CS2", "CS5", "Manual"],
        BearingFamily.CARB: ["None", "CS", "CS2", "CS5", "Manual"],
    }.get(family, common)
