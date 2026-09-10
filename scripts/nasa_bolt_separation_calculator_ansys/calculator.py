from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from math import inf, isfinite, pi, sqrt
from typing import Any, Literal


NASA_STANDARD_PAGE_URL = "https://standards.nasa.gov/standard/nasa/nasa-std-5020"
NASA_5020B_REVALIDATED_PDF_URL = (
    "https://standards.nasa.gov/system/files/tmp/"
    "2025%20-01-05%20NASA-STD-5020B%20Final%20-Revalidated.pdf"
)

PtlDerivationMode = Literal["direct", "axial", "fz", "force_magnitude", "axial_plus_bending"]
CombinedFailureTheory = Literal["nasa_ultimate", "von_mises_yield", "tresca_yield"]
SlipMode = Literal["joint_concentric", "per_fastener"]
ShearPlaneMode = Literal["body", "threads"]
Severity = Literal["error", "warning"]


@dataclass
class ValidationIssue:
    path: str
    severity: Severity
    message: str


@dataclass
class FactorRecommendation:
    classification: str
    recommended_fssep: float | None
    basis: str


@dataclass
class PreloadInputs:
    ppi_nom: float = 10000.0
    gamma: float = 0.25
    cmin: float = 1.0
    nf: int = 1
    separation_critical: bool = True
    relaxation_loss: float = 500.0
    creep_loss: float = 0.0
    thermal_loss: float = 0.0


@dataclass
class PreloadOverrideInputs:
    ppi_nom: float | None = None
    gamma: float | None = None
    cmin: float | None = None
    nf: int | None = None
    separation_critical: bool | None = None
    relaxation_loss: float | None = None
    creep_loss: float | None = None
    thermal_loss: float | None = None


@dataclass
class BoltGeometry:
    diameter: float = 8.0
    tensile_area: float = 36.6
    shear_area: float = 50.3
    minor_diameter_area: float = 36.6
    section_modulus: float = 50.0


@dataclass
class BoltGeometryOverrides:
    diameter: float | None = None
    tensile_area: float | None = None
    shear_area: float | None = None
    minor_diameter_area: float | None = None
    section_modulus: float | None = None


@dataclass
class MaterialAllowables:
    tensile_yield: float = 900.0
    tensile_ultimate: float = 1100.0
    shear_ultimate: float = 635.0
    bending_ultimate: float = 1100.0
    shear_yield: float = 0.0


@dataclass
class MaterialAllowableOverrides:
    tensile_yield: float | None = None
    tensile_ultimate: float | None = None
    shear_ultimate: float | None = None
    bending_ultimate: float | None = None
    shear_yield: float | None = None


@dataclass
class CombinedLoadInputs:
    enabled: bool = False
    theory: CombinedFailureTheory = "nasa_ultimate"
    factor_of_safety: float = 1.0
    shear_plane: ShearPlaneMode = "body"
    plastic_bending: bool = False
    geometry: BoltGeometry = field(default_factory=BoltGeometry)
    material: MaterialAllowables = field(default_factory=MaterialAllowables)


@dataclass
class SlipInputs:
    enabled: bool = False
    mode: SlipMode = "per_fastener"
    friction_coefficient: float = 0.10
    friction_substantiated: bool = False
    clean_uncoated_metal: bool = False
    factor_of_safety: float = 1.0
    joint_tensile_limit: float = 0.0
    joint_shear_limit: float = 0.0


@dataclass
class SealPressureInputs:
    enabled: bool = False
    pressure: float = 0.0
    effective_pressure_area: float = 0.0
    gasket_contact_area: float = 0.0
    min_contact_pressure: float = 0.0
    min_residual_clamp: float = 0.0


@dataclass
class ContactEvidenceLimits:
    enabled: bool = False
    max_gap_allowed: float = 0.0
    min_contact_pressure_required: float = 0.0
    max_separated_area_fraction: float = 1.0
    max_redistributed_ptl: float = 0.0


@dataclass
class ContactEvidenceRow:
    case_id: str = "LC1"
    set_id: str = "1"
    bolt_id: str = ""
    region: str = ""
    max_gap: float = 0.0
    min_contact_pressure: float = 0.0
    separated_area_fraction: float = 0.0
    redistributed_ptl: float = 0.0
    quality_flags: str = ""


@dataclass
class AdvancedCheckInputs:
    combined: CombinedLoadInputs = field(default_factory=CombinedLoadInputs)
    slip: SlipInputs = field(default_factory=SlipInputs)
    seal_pressure: SealPressureInputs = field(default_factory=SealPressureInputs)
    evidence_limits: ContactEvidenceLimits = field(default_factory=ContactEvidenceLimits)
    contact_evidence: list[ContactEvidenceRow] = field(default_factory=list)


@dataclass
class BoltLoadRow:
    case_id: str = "LC1"
    set_id: str = "1"
    bolt_id: str = "B1"
    fx: float = 0.0
    fy: float = 0.0
    fz: float = 0.0
    mx: float = 0.0
    my: float = 0.0
    mz: float = 0.0
    axial: float = 0.0
    shear_mag: float = 0.0
    units: str = "N,Nmm"
    source_type: str = "manual"
    source_name: str = ""
    quality_flags: str = ""


@dataclass
class BoltInput:
    bolt_id: str = "B1"
    direct_ptl: float | None = 5000.0
    ptl_mode: PtlDerivationMode = "direct"
    load_row: BoltLoadRow = field(default_factory=BoltLoadRow)
    moment_arm: float | None = None
    fitting_factor: float | None = None
    separation_factor: float | None = None
    preload_override: PreloadOverrideInputs = field(default_factory=PreloadOverrideInputs)
    geometry_override: BoltGeometryOverrides = field(default_factory=BoltGeometryOverrides)
    material_override: MaterialAllowableOverrides = field(default_factory=MaterialAllowableOverrides)
    notes: str = ""


@dataclass
class ProjectInput:
    project_name: str = "NASA-STD-5020B Bolt Separation Study"
    analyst: str = ""
    force_units: str = "N"
    moment_units: str = "N-mm"
    fitting_factor: float = 1.15
    separation_factor: float = 1.2
    joint_classification: str = "critical"
    program_yield_factor: float = 1.2
    program_ultimate_factor: float = 1.4
    test_envelope_factor: float = 1.0
    fssep_basis_notes: str = ""
    seal_or_gasket: bool = False
    pressure_containment: bool = False
    combined_loading_expected: bool = False
    advanced: AdvancedCheckInputs = field(default_factory=AdvancedCheckInputs)
    preload: PreloadInputs = field(default_factory=PreloadInputs)
    bolts: list[BoltInput] = field(default_factory=list)


@dataclass
class MarginResult:
    pp_min: float
    fitting_factor: float
    separation_factor: float
    ptl: float
    demand: float
    margin: float
    passed: bool


@dataclass
class BoltResult:
    bolt_id: str
    case_id: str
    set_id: str
    ptl_mode: PtlDerivationMode
    margin_result: MarginResult
    warnings: list[str] = field(default_factory=list)


@dataclass
class CombinedLoadResult:
    bolt_id: str
    theory: CombinedFailureTheory
    equation: str
    axial_stress: float
    bending_stress: float
    total_normal_stress: float
    shear_stress: float
    equivalent_stress: float
    equivalent_ptl: float
    utilization: float
    margin: float
    passed: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class SlipResult:
    mode: SlipMode
    bolt_id: str | None
    equation: str
    effective_mu: float
    numerator: float
    denominator: float
    margin: float
    passed: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class SealPressureResult:
    pressure_separating_load: float
    residual_clamp: float
    residual_contact_pressure: float
    contact_pressure_margin: float | None
    residual_clamp_margin: float | None
    passed: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class ContactEvidenceResult:
    case_id: str
    set_id: str
    bolt_id: str
    region: str
    passed: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class AdvancedCheckResult:
    combined_load: list[CombinedLoadResult] = field(default_factory=list)
    slip: list[SlipResult] = field(default_factory=list)
    seal_pressure: SealPressureResult | None = None
    contact_evidence: list[ContactEvidenceResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ProjectResult:
    pp_min: float
    bolt_results: list[BoltResult]
    controlling_bolt_id: str | None
    controlling_margin: float | None
    passed: bool
    warnings: list[str] = field(default_factory=list)
    advanced: AdvancedCheckResult = field(default_factory=AdvancedCheckResult)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _normalized_classification(project: ProjectInput) -> str:
    return project.joint_classification.strip().lower()


def recommended_fssep(project: ProjectInput) -> FactorRecommendation:
    """Return the NASA-STD-5020B Figure 1 FSsep recommendation for the selected classification."""
    classification = _normalized_classification(project)
    if classification == "catastrophic":
        return FactorRecommendation(
            classification=classification,
            recommended_fssep=project.program_ultimate_factor,
            basis="Catastrophic separation consequence: NASA-STD-5020B Figure 1 uses program-levied FSu.",
        )
    if classification == "critical":
        return FactorRecommendation(
            classification=classification,
            recommended_fssep=max(1.2, project.program_yield_factor),
            basis="Critical separation consequence: NASA-STD-5020B Figure 1 uses max(1.2, program-levied FSy).",
        )
    if classification == "non-separation-critical":
        return FactorRecommendation(
            classification=classification,
            recommended_fssep=max(1.0, project.test_envelope_factor),
            basis="Non-separation-critical case: NASA-STD-5020B Figure 1 uses max(1.0, program-levied test factor).",
        )
    if classification == "user-defined":
        return FactorRecommendation(
            classification=classification,
            recommended_fssep=None,
            basis="User-defined classification: document the FSsep basis notes.",
        )
    return FactorRecommendation(
        classification=classification or "blank",
        recommended_fssep=None,
        basis=f"Unsupported joint classification: {project.joint_classification}.",
    )


def validate_fssep_against_classification(project: ProjectInput) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    recommendation = recommended_fssep(project)
    if recommendation.classification not in {"catastrophic", "critical", "non-separation-critical", "user-defined"}:
        issues.append(
            ValidationIssue(
                "joint_classification",
                "warning",
                f"Unsupported joint classification '{project.joint_classification}'; document the FSsep basis.",
            )
        )
        return issues

    if recommendation.recommended_fssep is not None and project.separation_factor < recommendation.recommended_fssep:
        issues.append(
            ValidationIssue(
                "separation_factor",
                "warning",
                (
                    f"Entered FSsep {project.separation_factor:g} is below the recommended "
                    f"{recommendation.recommended_fssep:g} for {recommendation.classification} classification."
                ),
            )
        )

    if recommendation.classification == "user-defined" and not project.fssep_basis_notes.strip():
        issues.append(
            ValidationIssue(
                "fssep_basis_notes",
                "warning",
                "User-defined joint classification should include FSsep basis notes.",
            )
        )

    if recommendation.classification in {"catastrophic", "critical"} and not project.preload.separation_critical:
        issues.append(
            ValidationIssue(
                "preload.separation_critical",
                "warning",
                (
                    "Catastrophic or critical classification normally pairs with separation-critical "
                    "preload Eq. 4; Step 2 is currently using Eq. 5."
                ),
            )
        )

    return issues


def calculate_initial_min_preload(inputs: PreloadInputs) -> float:
    """Calculate minimum initial preload from NASA-STD-5020B Eq. 4 or Eq. 5."""
    if inputs.ppi_nom <= 0:
        raise ValueError("Nominal initial preload must be positive.")
    if inputs.gamma < 0:
        raise ValueError("Preload variation gamma cannot be negative.")
    if inputs.cmin <= 0:
        raise ValueError("cmin must be positive.")
    if inputs.nf <= 0:
        raise ValueError("nf must be positive.")

    if inputs.separation_critical:
        multiplier = 1.0 - inputs.gamma
    else:
        multiplier = 1.0 - inputs.gamma / sqrt(inputs.nf)
    return inputs.cmin * multiplier * inputs.ppi_nom


def calculate_min_preload(inputs: PreloadInputs) -> float:
    """Calculate final minimum preload from NASA-STD-5020B Eq. 2."""
    initial_min = calculate_initial_min_preload(inputs)
    return initial_min - inputs.relaxation_loss - inputs.creep_loss - inputs.thermal_loss


def _override_value(value: Any, default: Any) -> Any:
    return default if value is None else value


def _override_has_values(override: object) -> bool:
    fields = getattr(override, "__dataclass_fields__", {})
    return any(getattr(override, field_name) is not None for field_name in fields)


def resolved_bolt_preload(project: ProjectInput, bolt: BoltInput) -> PreloadInputs:
    override = bolt.preload_override
    default = project.preload
    return PreloadInputs(
        ppi_nom=_override_value(override.ppi_nom, default.ppi_nom),
        gamma=_override_value(override.gamma, default.gamma),
        cmin=_override_value(override.cmin, default.cmin),
        nf=_override_value(override.nf, default.nf),
        separation_critical=_override_value(override.separation_critical, default.separation_critical),
        relaxation_loss=_override_value(override.relaxation_loss, default.relaxation_loss),
        creep_loss=_override_value(override.creep_loss, default.creep_loss),
        thermal_loss=_override_value(override.thermal_loss, default.thermal_loss),
    )


def resolved_bolt_fitting_factor(project: ProjectInput, bolt: BoltInput) -> float:
    return _override_value(bolt.fitting_factor, project.fitting_factor)


def resolved_bolt_separation_factor(project: ProjectInput, bolt: BoltInput) -> float:
    return _override_value(bolt.separation_factor, project.separation_factor)


def resolved_bolt_geometry(project: ProjectInput, bolt: BoltInput) -> BoltGeometry:
    override = bolt.geometry_override
    default = project.advanced.combined.geometry
    return BoltGeometry(
        diameter=_override_value(override.diameter, default.diameter),
        tensile_area=_override_value(override.tensile_area, default.tensile_area),
        shear_area=_override_value(override.shear_area, default.shear_area),
        minor_diameter_area=_override_value(override.minor_diameter_area, default.minor_diameter_area),
        section_modulus=_override_value(override.section_modulus, default.section_modulus),
    )


def resolved_bolt_material(project: ProjectInput, bolt: BoltInput) -> MaterialAllowables:
    override = bolt.material_override
    default = project.advanced.combined.material
    return MaterialAllowables(
        tensile_yield=_override_value(override.tensile_yield, default.tensile_yield),
        tensile_ultimate=_override_value(override.tensile_ultimate, default.tensile_ultimate),
        shear_ultimate=_override_value(override.shear_ultimate, default.shear_ultimate),
        bending_ultimate=_override_value(override.bending_ultimate, default.bending_ultimate),
        shear_yield=_override_value(override.shear_yield, default.shear_yield),
    )


def bolt_has_row_overrides(bolt: BoltInput) -> bool:
    return (
        bolt.fitting_factor is not None
        or bolt.separation_factor is not None
        or _override_has_values(bolt.preload_override)
        or _override_has_values(bolt.geometry_override)
        or _override_has_values(bolt.material_override)
    )


def derive_ptl_from_load_row(
    row: BoltLoadRow,
    mode: PtlDerivationMode,
    moment_arm: float | None = None,
) -> float:
    """Derive the tensile limit load used by Eq. 19 from an imported Ansys-style row."""
    if mode == "direct":
        raise ValueError("Direct PtL mode uses BoltInput.direct_ptl, not an Ansys load row.")
    if mode == "axial":
        return abs(row.axial)
    if mode == "fz":
        return abs(row.fz)
    if mode == "force_magnitude":
        return sqrt(row.fx**2 + row.fy**2 + row.fz**2)
    if mode == "axial_plus_bending":
        if moment_arm is None or moment_arm <= 0:
            raise ValueError("A positive moment arm is required for axial_plus_bending mode.")
        bending = sqrt(row.mx**2 + row.my**2)
        return abs(row.axial) + bending / moment_arm
    raise ValueError(f"Unsupported PtL derivation mode: {mode}")


def calculate_separation_margin(pp_min: float, ff: float, fs_sep: float, ptl: float) -> MarginResult:
    """Calculate NASA-STD-5020B Eq. 19 separation margin."""
    if pp_min <= 0:
        raise ValueError("Final minimum preload Pp_min must be positive.")
    if ff <= 0:
        raise ValueError("Fitting factor FF must be positive.")
    if fs_sep <= 0:
        raise ValueError("Separation factor FSsep must be positive.")
    if ptl <= 0:
        raise ValueError("Limit tensile load PtL must be positive.")
    demand = ff * fs_sep * ptl
    margin = pp_min / demand - 1.0
    return MarginResult(
        pp_min=pp_min,
        fitting_factor=ff,
        separation_factor=fs_sep,
        ptl=ptl,
        demand=demand,
        margin=margin,
        passed=margin >= 0.0,
    )


def _positive_or_error(name: str, value: float) -> None:
    if value <= 0 or not isfinite(value):
        raise ValueError(f"{name} must be positive.")


def _shear_allowable_yield(material: MaterialAllowables, theory: CombinedFailureTheory) -> float:
    if material.shear_yield > 0:
        return material.shear_yield
    _positive_or_error("Tensile yield allowable", material.tensile_yield)
    if theory == "tresca_yield":
        return material.tensile_yield / 2.0
    return material.tensile_yield / sqrt(3.0)


def calculate_combined_load_result(
    bolt: BoltInput,
    ptl: float,
    inputs: CombinedLoadInputs,
    fitting_factor: float,
) -> CombinedLoadResult:
    geometry = inputs.geometry
    material = inputs.material
    load = bolt.load_row
    _positive_or_error("Tensile area", geometry.tensile_area)
    _positive_or_error("Shear area", geometry.shear_area)
    _positive_or_error("Combined-load factor of safety", inputs.factor_of_safety)

    shear_load = abs(load.shear_mag) if abs(load.shear_mag) > 0.0 else sqrt(load.fx**2 + load.fy**2)
    bending_moment = sqrt(load.mx**2 + load.my**2)
    axial_stress = abs(ptl) / geometry.tensile_area
    bending_stress = bending_moment / geometry.section_modulus if geometry.section_modulus > 0 else 0.0
    total_normal_stress = axial_stress + bending_stress
    shear_stress = shear_load / geometry.shear_area
    warnings: list[str] = []

    if inputs.theory == "nasa_ultimate":
        _positive_or_error("Tensile ultimate allowable", material.tensile_ultimate)
        _positive_or_error("Shear ultimate allowable", material.shear_ultimate)
        if inputs.shear_plane == "threads":
            _positive_or_error("Minor-diameter area", geometry.minor_diameter_area)
            shear_allowable_load = material.shear_ultimate * geometry.minor_diameter_area
            shear_exponent = 1.2
            equation = "NASA-STD-5020B Eq. 22" if not inputs.plastic_bending else "NASA-STD-5020B Eq. 23"
        else:
            _positive_or_error("Bolt diameter", geometry.diameter)
            shear_allowable_load = pi * geometry.diameter**2 * material.shear_ultimate / 4.0
            shear_exponent = 2.5
            equation = "NASA-STD-5020B Eq. 20" if not inputs.plastic_bending else "NASA-STD-5020B Eq. 21"

        ptu_allow = material.tensile_ultimate * geometry.tensile_area
        shear_term = (fitting_factor * inputs.factor_of_safety * shear_load / shear_allowable_load) ** shear_exponent
        tensile_ratio = fitting_factor * inputs.factor_of_safety * abs(ptl) / ptu_allow
        if inputs.plastic_bending:
            _positive_or_error("Bending ultimate allowable", material.bending_ultimate)
            bending_term = fitting_factor * inputs.factor_of_safety * bending_stress / material.bending_ultimate
            tensile_exponent = 1.5 if inputs.shear_plane == "body" else 2.0
            utilization = shear_term + tensile_ratio**tensile_exponent + bending_term
        else:
            bending_ratio = fitting_factor * inputs.factor_of_safety * bending_stress / material.tensile_ultimate
            tensile_exponent = 1.5 if inputs.shear_plane == "body" else 2.0
            utilization = shear_term + (tensile_ratio + bending_ratio) ** tensile_exponent
        equivalent_stress = total_normal_stress
        equivalent_ptl = total_normal_stress * geometry.tensile_area
    else:
        _positive_or_error("Tensile yield allowable", material.tensile_yield)
        design_normal = fitting_factor * inputs.factor_of_safety * total_normal_stress
        design_shear = fitting_factor * inputs.factor_of_safety * shear_stress
        if inputs.theory == "tresca_yield":
            radius = sqrt((design_normal / 2.0) ** 2 + design_shear**2)
            s1 = design_normal / 2.0 + radius
            s2 = design_normal / 2.0 - radius
            equivalent_stress = max(abs(s1 - s2), abs(s1), abs(s2))
            equation = "Tresca yield screen"
        else:
            equivalent_stress = sqrt(design_normal**2 + 3.0 * design_shear**2)
            equation = "von Mises yield screen"
        utilization = equivalent_stress / material.tensile_yield
        equivalent_ptl = equivalent_stress * geometry.tensile_area
        shear_allow = _shear_allowable_yield(material, inputs.theory)
        if design_shear > shear_allow:
            warnings.append("Factored shear stress exceeds derived/direct shear-yield allowable.")

    margin = 1.0 / utilization - 1.0 if utilization > 0.0 else inf
    return CombinedLoadResult(
        bolt_id=bolt.bolt_id,
        theory=inputs.theory,
        equation=equation,
        axial_stress=axial_stress,
        bending_stress=bending_stress,
        total_normal_stress=total_normal_stress,
        shear_stress=shear_stress,
        equivalent_stress=equivalent_stress,
        equivalent_ptl=equivalent_ptl,
        utilization=utilization,
        margin=margin,
        passed=utilization <= 1.0,
        warnings=warnings,
    )


def _effective_friction(inputs: SlipInputs) -> tuple[float, list[str]]:
    warnings: list[str] = []
    _positive_or_error("Friction coefficient", inputs.friction_coefficient)
    if inputs.friction_substantiated:
        return inputs.friction_coefficient, warnings
    cap = 0.20 if inputs.clean_uncoated_metal else 0.10
    if inputs.friction_coefficient > cap:
        warnings.append(
            f"Friction coefficient {inputs.friction_coefficient:g} exceeds NASA unsubstantiated cap {cap:g}; cap used."
        )
        return cap, warnings
    return inputs.friction_coefficient, warnings


def calculate_slip_results(
    project: ProjectInput,
    pp_min: float,
    bolt_results: list[BoltResult],
) -> list[SlipResult]:
    inputs = project.advanced.slip
    if not inputs.enabled:
        return []
    _positive_or_error("Slip factor of safety", inputs.factor_of_safety)
    mu, base_warnings = _effective_friction(inputs)
    results: list[SlipResult] = []
    if inputs.mode == "joint_concentric":
        _positive_or_error("Joint shear limit load", inputs.joint_shear_limit)
        if inputs.joint_tensile_limit < 0:
            raise ValueError("Joint tensile limit load cannot be negative.")
        equation = "NASA-STD-5020B Eq. 85" if inputs.joint_tensile_limit == 0 else "NASA-STD-5020B Eq. 84"
        numerator = mu * project.preload.nf * pp_min
        denominator = inputs.factor_of_safety * (inputs.joint_shear_limit + mu * inputs.joint_tensile_limit)
        margin = numerator / denominator - 1.0
        warnings = list(base_warnings)
        warnings.append("Joint Eq. 84/85 assumes concentric loading, same fastener type, equal preload, and equivalent sizes.")
        if any(bolt_has_row_overrides(bolt) for bolt in project.bolts):
            warnings.append("Joint Eq. 84/85 uses the project-default preload; row-specific bolt overrides are not aggregated.")
        results.append(
            SlipResult(
                mode=inputs.mode,
                bolt_id=None,
                equation=equation,
                effective_mu=mu,
                numerator=numerator,
                denominator=denominator,
                margin=margin,
                passed=margin >= 0.0,
                warnings=warnings,
            )
        )
        return results

    for bolt_result, bolt in zip(bolt_results, project.bolts):
        ptl = bolt_result.margin_result.ptl
        shear = abs(bolt.load_row.shear_mag) if abs(bolt.load_row.shear_mag) > 0.0 else sqrt(bolt.load_row.fx**2 + bolt.load_row.fy**2)
        pp_min_i = bolt_result.margin_result.pp_min
        fitting_factor = bolt_result.margin_result.fitting_factor
        denominator = fitting_factor * inputs.factor_of_safety * (shear + mu * ptl)
        if denominator <= 0.0:
            margin = inf
            numerator = mu * pp_min_i
        else:
            numerator = mu * pp_min_i
            margin = numerator / denominator - 1.0
        results.append(
            SlipResult(
                mode=inputs.mode,
                bolt_id=bolt.bolt_id,
                equation="NASA-STD-5020B Eq. 86",
                effective_mu=mu,
                numerator=numerator,
                denominator=denominator,
                margin=margin,
                passed=margin >= 0.0,
                warnings=list(base_warnings),
            )
        )
    return results


def calculate_seal_pressure_result(project: ProjectInput, pp_min: float) -> SealPressureResult | None:
    inputs = project.advanced.seal_pressure
    if not inputs.enabled:
        return None
    for name, value in (
        ("Pressure", inputs.pressure),
        ("Effective pressure area", inputs.effective_pressure_area),
        ("Gasket/contact area", inputs.gasket_contact_area),
    ):
        _positive_or_error(name, value)
    if inputs.min_contact_pressure < 0 or inputs.min_residual_clamp < 0:
        raise ValueError("Seal pressure acceptance limits cannot be negative.")
    pressure_load = inputs.pressure * inputs.effective_pressure_area
    residual_clamp = project.preload.nf * pp_min - pressure_load
    residual_contact_pressure = residual_clamp / inputs.gasket_contact_area
    contact_margin = (
        residual_contact_pressure / inputs.min_contact_pressure - 1.0
        if inputs.min_contact_pressure > 0.0
        else None
    )
    clamp_margin = (
        residual_clamp / inputs.min_residual_clamp - 1.0
        if inputs.min_residual_clamp > 0.0
        else None
    )
    passed = residual_clamp >= 0.0
    if contact_margin is not None:
        passed = passed and contact_margin >= 0.0
    if clamp_margin is not None:
        passed = passed and clamp_margin >= 0.0
    warnings = [
        "Seal/pressure result is a residual compression check; NASA says Eq. 19 does not accurately predict seal/gasket separation margin."
    ]
    if any(bolt_has_row_overrides(bolt) for bolt in project.bolts):
        warnings.append("Seal/pressure residual compression uses the project-default preload, not row-specific bolt overrides.")
    return SealPressureResult(
        pressure_separating_load=pressure_load,
        residual_clamp=residual_clamp,
        residual_contact_pressure=residual_contact_pressure,
        contact_pressure_margin=contact_margin,
        residual_clamp_margin=clamp_margin,
        passed=passed,
        warnings=warnings,
    )


def calculate_contact_evidence_results(project: ProjectInput) -> list[ContactEvidenceResult]:
    limits = project.advanced.evidence_limits
    if not limits.enabled:
        return []
    results: list[ContactEvidenceResult] = []
    for row in project.advanced.contact_evidence:
        warnings: list[str] = []
        if limits.max_gap_allowed > 0.0 and row.max_gap > limits.max_gap_allowed:
            warnings.append(f"Max gap {row.max_gap:g} exceeds allowed {limits.max_gap_allowed:g}.")
        if limits.min_contact_pressure_required > 0.0 and row.min_contact_pressure < limits.min_contact_pressure_required:
            warnings.append(
                f"Min contact pressure {row.min_contact_pressure:g} is below required {limits.min_contact_pressure_required:g}."
            )
        if row.separated_area_fraction > limits.max_separated_area_fraction:
            warnings.append(
                f"Separated area fraction {row.separated_area_fraction:g} exceeds allowed {limits.max_separated_area_fraction:g}."
            )
        if limits.max_redistributed_ptl > 0.0 and row.redistributed_ptl > limits.max_redistributed_ptl:
            warnings.append(f"Redistributed PtL {row.redistributed_ptl:g} exceeds allowed {limits.max_redistributed_ptl:g}.")
        failed = bool(warnings)
        if row.quality_flags:
            warnings.append(f"Evidence flags: {row.quality_flags}")
        results.append(
            ContactEvidenceResult(
                case_id=row.case_id,
                set_id=row.set_id,
                bolt_id=row.bolt_id,
                region=row.region,
                passed=not failed,
                warnings=warnings,
            )
        )
    return results


def calculate_advanced_checks(project: ProjectInput, pp_min: float, bolt_results: list[BoltResult]) -> AdvancedCheckResult:
    advanced = AdvancedCheckResult()
    if project.advanced.combined.enabled:
        for bolt_result, bolt in zip(bolt_results, project.bolts):
            combined_inputs = replace(
                project.advanced.combined,
                geometry=resolved_bolt_geometry(project, bolt),
                material=resolved_bolt_material(project, bolt),
            )
            advanced.combined_load.append(
                calculate_combined_load_result(
                    bolt=bolt,
                    ptl=bolt_result.margin_result.ptl,
                    inputs=combined_inputs,
                    fitting_factor=bolt_result.margin_result.fitting_factor,
                )
            )
    advanced.slip = calculate_slip_results(project, pp_min, bolt_results)
    advanced.seal_pressure = calculate_seal_pressure_result(project, pp_min)
    advanced.contact_evidence = calculate_contact_evidence_results(project)
    if project.advanced.combined.enabled:
        advanced.warnings.append("Combined-load results are engineering screens; verify assumptions against NASA-STD-5020B Section 4.4.4.")
    if project.advanced.evidence_limits.enabled:
        advanced.warnings.append("Nonlinear evidence checks depend on the analyst-supplied Ansys contact/gap CSV and acceptance limits.")
    return advanced


def _bolt_ptl(bolt: BoltInput) -> float:
    if bolt.ptl_mode == "direct":
        if bolt.direct_ptl is None:
            raise ValueError(f"{bolt.bolt_id}: direct PtL is missing.")
        return bolt.direct_ptl
    return derive_ptl_from_load_row(bolt.load_row, bolt.ptl_mode, bolt.moment_arm)


def _project_warnings(project: ProjectInput) -> list[str]:
    warnings: list[str] = []
    if project.seal_or_gasket:
        warnings.append("Seal or gasket joint: NASA-STD-5020B says Eq. 19 may not accurately predict separation.")
    if project.pressure_containment:
        warnings.append("Pressure/fluid containment is present; use seal-specific analysis or test evidence.")
    if project.combined_loading_expected:
        warnings.append("Combined loading is expected; Eq. 19 is axial-only and needs engineering review.")
    if project.fitting_factor < 1.15 and project.preload.separation_critical:
        warnings.append("Separation-critical fitting factor is below the common 1.15 default; document the basis.")
    if any(bolt_has_row_overrides(bolt) for bolt in project.bolts):
        warnings.append("Bolt table contains row-specific overrides; blank override cells inherit the project defaults.")
    return warnings


def _bolt_warnings(bolt: BoltInput) -> list[str]:
    row = bolt.load_row
    warnings: list[str] = []
    if bolt.ptl_mode in {"force_magnitude", "axial_plus_bending"}:
        warnings.append(f"PtL was derived with {bolt.ptl_mode}; confirm this is conservative for Eq. 19.")
    if abs(row.shear_mag) > 0.0 or abs(row.fx) > 0.0 or abs(row.fy) > 0.0:
        warnings.append("Imported row includes shear/in-plane force; Eq. 19 is axial-only.")
    if abs(row.mx) > 0.0 or abs(row.my) > 0.0 or abs(row.mz) > 0.0:
        warnings.append("Imported row includes moment; confirm any conversion to PtL separately.")
    if row.quality_flags:
        warnings.append(f"Ansys quality flags: {row.quality_flags}")
    return warnings


def calculate_project(project: ProjectInput) -> ProjectResult:
    issues = validate_project(project)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        joined = "; ".join(f"{issue.path}: {issue.message}" for issue in errors)
        raise ValueError(joined)

    pp_min = calculate_min_preload(project.preload)
    bolt_results: list[BoltResult] = []
    for bolt in project.bolts:
        bolt_preload = resolved_bolt_preload(project, bolt)
        bolt_pp_min = calculate_min_preload(bolt_preload)
        fitting_factor = resolved_bolt_fitting_factor(project, bolt)
        separation_factor = resolved_bolt_separation_factor(project, bolt)
        ptl = _bolt_ptl(bolt)
        margin_result = calculate_separation_margin(
            pp_min=bolt_pp_min,
            ff=fitting_factor,
            fs_sep=separation_factor,
            ptl=ptl,
        )
        bolt_results.append(
            BoltResult(
                bolt_id=bolt.bolt_id,
                case_id=bolt.load_row.case_id,
                set_id=bolt.load_row.set_id,
                ptl_mode=bolt.ptl_mode,
                margin_result=margin_result,
                warnings=_bolt_warnings(bolt),
            )
        )

    advanced = calculate_advanced_checks(project, pp_min, bolt_results)
    advanced_passed = (
        all(item.passed for item in advanced.combined_load)
        and all(item.passed for item in advanced.slip)
        and (advanced.seal_pressure is None or advanced.seal_pressure.passed)
        and all(item.passed for item in advanced.contact_evidence)
    )
    controlling = min(bolt_results, key=lambda item: item.margin_result.margin, default=None)
    return ProjectResult(
        pp_min=pp_min,
        bolt_results=bolt_results,
        controlling_bolt_id=controlling.bolt_id if controlling else None,
        controlling_margin=controlling.margin_result.margin if controlling else None,
        passed=all(result.margin_result.passed for result in bolt_results) and advanced_passed,
        warnings=_project_warnings(project) + advanced.warnings + [issue.message for issue in issues if issue.severity == "warning"],
        advanced=advanced,
    )


def validate_project(project: ProjectInput) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def check_positive(path: str, value: Any, label: str) -> None:
        if not _is_number(value) or value <= 0:
            issues.append(ValidationIssue(path, "error", f"{label} must be a positive number."))

    check_positive("fitting_factor", project.fitting_factor, "Fitting factor")
    check_positive("separation_factor", project.separation_factor, "Separation factor")
    check_positive("program_yield_factor", project.program_yield_factor, "Program yield factor")
    check_positive("program_ultimate_factor", project.program_ultimate_factor, "Program ultimate factor")
    check_positive("test_envelope_factor", project.test_envelope_factor, "Test envelope factor")
    check_positive("preload.ppi_nom", project.preload.ppi_nom, "Nominal initial preload")
    check_positive("preload.cmin", project.preload.cmin, "cmin")
    if not isinstance(project.preload.nf, int) or project.preload.nf <= 0:
        issues.append(ValidationIssue("preload.nf", "error", "Fastener count nf must be a positive integer."))
    if project.preload.gamma < 0:
        issues.append(ValidationIssue("preload.gamma", "error", "Gamma cannot be negative."))
    if project.preload.gamma >= 1.0 and project.preload.separation_critical:
        issues.append(ValidationIssue("preload.gamma", "error", "Gamma must be less than 1 for separation-critical Eq. 4."))
    for attr in ("relaxation_loss", "creep_loss", "thermal_loss"):
        value = getattr(project.preload, attr)
        if not _is_number(value) or value < 0:
            issues.append(ValidationIssue(f"preload.{attr}", "error", f"{attr} cannot be negative."))

    try:
        pp_min = calculate_min_preload(project.preload)
        if pp_min <= 0:
            issues.append(ValidationIssue("preload", "error", "Final minimum preload Pp_min is not positive."))
    except ValueError as exc:
        issues.append(ValidationIssue("preload", "error", str(exc)))

    issues.extend(validate_fssep_against_classification(project))
    if project.advanced.combined.enabled:
        check_positive("advanced.combined.factor_of_safety", project.advanced.combined.factor_of_safety, "Combined-load factor")
        check_positive("advanced.combined.geometry.tensile_area", project.advanced.combined.geometry.tensile_area, "Tensile area")
        check_positive("advanced.combined.geometry.shear_area", project.advanced.combined.geometry.shear_area, "Shear area")
        if project.advanced.combined.geometry.section_modulus <= 0 and project.advanced.combined.theory == "nasa_ultimate":
            issues.append(
                ValidationIssue(
                    "advanced.combined.geometry.section_modulus",
                    "warning",
                    "Section modulus is zero; bending stress term will be zero in the combined-load screen.",
                )
            )
        if project.advanced.combined.theory == "nasa_ultimate":
            check_positive("advanced.combined.material.tensile_ultimate", project.advanced.combined.material.tensile_ultimate, "Tensile ultimate")
            check_positive("advanced.combined.material.shear_ultimate", project.advanced.combined.material.shear_ultimate, "Shear ultimate")
            if project.advanced.combined.plastic_bending:
                check_positive("advanced.combined.material.bending_ultimate", project.advanced.combined.material.bending_ultimate, "Bending ultimate")
        else:
            check_positive("advanced.combined.material.tensile_yield", project.advanced.combined.material.tensile_yield, "Tensile yield")

    if project.advanced.slip.enabled:
        check_positive("advanced.slip.friction_coefficient", project.advanced.slip.friction_coefficient, "Friction coefficient")
        check_positive("advanced.slip.factor_of_safety", project.advanced.slip.factor_of_safety, "Slip factor")
        if project.advanced.slip.mode == "joint_concentric":
            check_positive("advanced.slip.joint_shear_limit", project.advanced.slip.joint_shear_limit, "Joint shear limit")
            if project.advanced.slip.joint_tensile_limit < 0:
                issues.append(ValidationIssue("advanced.slip.joint_tensile_limit", "error", "Joint tensile limit cannot be negative."))

    if project.advanced.seal_pressure.enabled:
        check_positive("advanced.seal_pressure.pressure", project.advanced.seal_pressure.pressure, "Pressure")
        check_positive(
            "advanced.seal_pressure.effective_pressure_area",
            project.advanced.seal_pressure.effective_pressure_area,
            "Effective pressure area",
        )
        check_positive(
            "advanced.seal_pressure.gasket_contact_area",
            project.advanced.seal_pressure.gasket_contact_area,
            "Gasket/contact area",
        )
        if project.advanced.seal_pressure.min_contact_pressure < 0 or project.advanced.seal_pressure.min_residual_clamp < 0:
            issues.append(ValidationIssue("advanced.seal_pressure", "error", "Seal acceptance limits cannot be negative."))

    if project.advanced.evidence_limits.enabled:
        if not 0.0 <= project.advanced.evidence_limits.max_separated_area_fraction <= 1.0:
            issues.append(
                ValidationIssue(
                    "advanced.evidence_limits.max_separated_area_fraction",
                    "error",
                    "Max separated area fraction must be between 0 and 1.",
                )
            )
        for index, row in enumerate(project.advanced.contact_evidence):
            if row.max_gap < 0 or row.min_contact_pressure < 0 or row.separated_area_fraction < 0 or row.redistributed_ptl < 0:
                issues.append(
                    ValidationIssue(
                        f"advanced.contact_evidence[{index}]",
                        "error",
                        "Nonlinear evidence numeric fields cannot be negative.",
                    )
                )
            if row.separated_area_fraction > 1.0:
                issues.append(
                    ValidationIssue(
                        f"advanced.contact_evidence[{index}].separated_area_fraction",
                        "error",
                        "Separated area fraction must be between 0 and 1.",
                    )
                )
        if not project.advanced.contact_evidence:
            issues.append(
                ValidationIssue(
                    "advanced.contact_evidence",
                    "warning",
                    "Nonlinear evidence checks are enabled but no evidence rows are imported.",
                )
            )

    if not project.bolts:
        issues.append(ValidationIssue("bolts", "error", "Add at least one bolt row."))

    seen: set[str] = set()
    for index, bolt in enumerate(project.bolts):
        prefix = f"bolts[{index}]"
        if not bolt.bolt_id.strip():
            issues.append(ValidationIssue(f"{prefix}.bolt_id", "error", "Bolt ID is required."))
        elif bolt.bolt_id in seen:
            issues.append(ValidationIssue(f"{prefix}.bolt_id", "error", f"Duplicate bolt ID: {bolt.bolt_id}."))
        seen.add(bolt.bolt_id)

        if bolt.ptl_mode == "direct":
            check_positive(f"{prefix}.direct_ptl", bolt.direct_ptl, "Direct PtL")
        elif bolt.ptl_mode == "axial_plus_bending":
            check_positive(f"{prefix}.moment_arm", bolt.moment_arm, "Moment arm")
        elif bolt.ptl_mode not in {"axial", "fz", "force_magnitude"}:
            issues.append(ValidationIssue(f"{prefix}.ptl_mode", "error", f"Unsupported PtL mode: {bolt.ptl_mode}."))

        try:
            ptl = _bolt_ptl(bolt)
            if ptl <= 0:
                issues.append(ValidationIssue(f"{prefix}.ptl", "error", "Derived PtL is not positive."))
        except ValueError as exc:
            issues.append(ValidationIssue(f"{prefix}.ptl", "error", str(exc)))

        if bolt.ptl_mode != "direct" and not bolt.load_row.source_type:
            issues.append(ValidationIssue(f"{prefix}.source_type", "warning", "Source type is blank for imported load row."))

        if bolt.fitting_factor is not None:
            check_positive(f"{prefix}.fitting_factor", bolt.fitting_factor, "Bolt fitting factor")
        if bolt.separation_factor is not None:
            check_positive(f"{prefix}.separation_factor", bolt.separation_factor, "Bolt separation factor")
            recommendation = recommended_fssep(project)
            if recommendation.recommended_fssep is not None and bolt.separation_factor < recommendation.recommended_fssep:
                issues.append(
                    ValidationIssue(
                        f"{prefix}.separation_factor",
                        "warning",
                        (
                            f"Row FSsep {bolt.separation_factor:g} is below the recommended "
                            f"{recommendation.recommended_fssep:g} for {recommendation.classification} classification."
                        ),
                    )
                )

        preload_override = bolt.preload_override
        if preload_override.ppi_nom is not None:
            check_positive(f"{prefix}.preload_ppi_nom", preload_override.ppi_nom, "Bolt nominal initial preload")
        if preload_override.cmin is not None:
            check_positive(f"{prefix}.preload_cmin", preload_override.cmin, "Bolt cmin")
        if preload_override.nf is not None and (
            not isinstance(preload_override.nf, int) or preload_override.nf <= 0
        ):
            issues.append(ValidationIssue(f"{prefix}.preload_nf", "error", "Bolt fastener count nf must be a positive integer."))
        if preload_override.gamma is not None and preload_override.gamma < 0:
            issues.append(ValidationIssue(f"{prefix}.preload_gamma", "error", "Bolt gamma cannot be negative."))
        resolved_preload = resolved_bolt_preload(project, bolt)
        if resolved_preload.gamma >= 1.0 and resolved_preload.separation_critical:
            issues.append(
                ValidationIssue(
                    f"{prefix}.preload_gamma",
                    "error",
                    "Resolved bolt gamma must be less than 1 for separation-critical Eq. 4.",
                )
            )
        for attr in ("relaxation_loss", "creep_loss", "thermal_loss"):
            value = getattr(preload_override, attr)
            if value is not None and (not _is_number(value) or value < 0):
                issues.append(ValidationIssue(f"{prefix}.preload_{attr}", "error", f"Bolt {attr} cannot be negative."))
        try:
            if calculate_min_preload(resolved_preload) <= 0:
                issues.append(
                    ValidationIssue(
                        f"{prefix}.preload_ppi_nom",
                        "error",
                        "Resolved bolt final minimum preload Pp_min is not positive.",
                    )
                )
        except ValueError as exc:
            issues.append(ValidationIssue(f"{prefix}.preload_ppi_nom", "error", str(exc)))

        if project.advanced.combined.enabled:
            geometry_override = bolt.geometry_override
            for attr, label in (
                ("diameter", "Bolt diameter"),
                ("tensile_area", "Bolt tensile area"),
                ("shear_area", "Bolt shear area"),
                ("minor_diameter_area", "Bolt minor-diameter area"),
                ("section_modulus", "Bolt section modulus"),
            ):
                value = getattr(geometry_override, attr)
                if value is not None and value < 0:
                    issues.append(ValidationIssue(f"{prefix}.geometry_{attr}", "error", f"{label} cannot be negative."))
            resolved_geometry = resolved_bolt_geometry(project, bolt)
            if resolved_geometry.tensile_area <= 0:
                issues.append(ValidationIssue(f"{prefix}.geometry_tensile_area", "error", "Resolved bolt tensile area must be positive."))
            if resolved_geometry.shear_area <= 0:
                issues.append(ValidationIssue(f"{prefix}.geometry_shear_area", "error", "Resolved bolt shear area must be positive."))
            if resolved_geometry.section_modulus <= 0 and project.advanced.combined.theory == "nasa_ultimate":
                issues.append(
                    ValidationIssue(
                        f"{prefix}.geometry_section_modulus",
                        "warning",
                        "Resolved bolt section modulus is zero; bending stress term will be zero.",
                    )
                )
            if project.advanced.combined.theory == "nasa_ultimate":
                if resolved_geometry.diameter <= 0 and project.advanced.combined.shear_plane == "body":
                    issues.append(ValidationIssue(f"{prefix}.geometry_diameter", "error", "Resolved bolt diameter must be positive."))
                if resolved_geometry.minor_diameter_area <= 0 and project.advanced.combined.shear_plane == "threads":
                    issues.append(
                        ValidationIssue(
                            f"{prefix}.geometry_minor_diameter_area",
                            "error",
                            "Resolved bolt minor-diameter area must be positive.",
                        )
                    )

            material_override = bolt.material_override
            for attr, label in (
                ("tensile_yield", "Bolt tensile yield"),
                ("tensile_ultimate", "Bolt tensile ultimate"),
                ("shear_ultimate", "Bolt shear ultimate"),
                ("bending_ultimate", "Bolt bending ultimate"),
                ("shear_yield", "Bolt shear yield"),
            ):
                value = getattr(material_override, attr)
                if value is not None and value < 0:
                    issues.append(ValidationIssue(f"{prefix}.material_{attr}", "error", f"{label} cannot be negative."))
            resolved_material = resolved_bolt_material(project, bolt)
            if project.advanced.combined.theory == "nasa_ultimate":
                if resolved_material.tensile_ultimate <= 0:
                    issues.append(ValidationIssue(f"{prefix}.material_tensile_ultimate", "error", "Resolved bolt tensile ultimate must be positive."))
                if resolved_material.shear_ultimate <= 0:
                    issues.append(ValidationIssue(f"{prefix}.material_shear_ultimate", "error", "Resolved bolt shear ultimate must be positive."))
                if project.advanced.combined.plastic_bending and resolved_material.bending_ultimate <= 0:
                    issues.append(ValidationIssue(f"{prefix}.material_bending_ultimate", "error", "Resolved bolt bending ultimate must be positive."))
            elif resolved_material.tensile_yield <= 0:
                issues.append(ValidationIssue(f"{prefix}.material_tensile_yield", "error", "Resolved bolt tensile yield must be positive."))

    return issues


def project_to_dict(project: ProjectInput) -> dict[str, Any]:
    return asdict(project)


def preload_from_dict(data: dict[str, Any]) -> PreloadInputs:
    return PreloadInputs(**{key: data[key] for key in PreloadInputs.__dataclass_fields__ if key in data})


def preload_override_from_dict(data: dict[str, Any] | None) -> PreloadOverrideInputs:
    data = data or {}
    return PreloadOverrideInputs(**{key: data[key] for key in PreloadOverrideInputs.__dataclass_fields__ if key in data})


def load_row_from_dict(data: dict[str, Any]) -> BoltLoadRow:
    return BoltLoadRow(**{key: data[key] for key in BoltLoadRow.__dataclass_fields__ if key in data})


def bolt_geometry_from_dict(data: dict[str, Any]) -> BoltGeometry:
    return BoltGeometry(**{key: data[key] for key in BoltGeometry.__dataclass_fields__ if key in data})


def bolt_geometry_overrides_from_dict(data: dict[str, Any] | None) -> BoltGeometryOverrides:
    data = data or {}
    return BoltGeometryOverrides(**{key: data[key] for key in BoltGeometryOverrides.__dataclass_fields__ if key in data})


def material_allowables_from_dict(data: dict[str, Any]) -> MaterialAllowables:
    return MaterialAllowables(**{key: data[key] for key in MaterialAllowables.__dataclass_fields__ if key in data})


def material_allowable_overrides_from_dict(data: dict[str, Any] | None) -> MaterialAllowableOverrides:
    data = data or {}
    return MaterialAllowableOverrides(**{key: data[key] for key in MaterialAllowableOverrides.__dataclass_fields__ if key in data})


def combined_load_inputs_from_dict(data: dict[str, Any]) -> CombinedLoadInputs:
    raw = dict(data)
    raw["geometry"] = bolt_geometry_from_dict(raw.get("geometry", {}))
    raw["material"] = material_allowables_from_dict(raw.get("material", {}))
    return CombinedLoadInputs(**{key: raw[key] for key in CombinedLoadInputs.__dataclass_fields__ if key in raw})


def slip_inputs_from_dict(data: dict[str, Any]) -> SlipInputs:
    return SlipInputs(**{key: data[key] for key in SlipInputs.__dataclass_fields__ if key in data})


def seal_pressure_inputs_from_dict(data: dict[str, Any]) -> SealPressureInputs:
    return SealPressureInputs(**{key: data[key] for key in SealPressureInputs.__dataclass_fields__ if key in data})


def contact_evidence_limits_from_dict(data: dict[str, Any]) -> ContactEvidenceLimits:
    return ContactEvidenceLimits(**{key: data[key] for key in ContactEvidenceLimits.__dataclass_fields__ if key in data})


def contact_evidence_row_from_dict(data: dict[str, Any]) -> ContactEvidenceRow:
    return ContactEvidenceRow(**{key: data[key] for key in ContactEvidenceRow.__dataclass_fields__ if key in data})


def advanced_check_inputs_from_dict(data: dict[str, Any]) -> AdvancedCheckInputs:
    raw = dict(data)
    raw["combined"] = combined_load_inputs_from_dict(raw.get("combined", {}))
    raw["slip"] = slip_inputs_from_dict(raw.get("slip", {}))
    raw["seal_pressure"] = seal_pressure_inputs_from_dict(raw.get("seal_pressure", {}))
    raw["evidence_limits"] = contact_evidence_limits_from_dict(raw.get("evidence_limits", {}))
    raw["contact_evidence"] = [contact_evidence_row_from_dict(item) for item in raw.get("contact_evidence", [])]
    return AdvancedCheckInputs(**{key: raw[key] for key in AdvancedCheckInputs.__dataclass_fields__ if key in raw})


def bolt_from_dict(data: dict[str, Any]) -> BoltInput:
    raw = dict(data)
    raw["load_row"] = load_row_from_dict(raw.get("load_row", {}))
    raw["preload_override"] = preload_override_from_dict(raw.get("preload_override"))
    raw["geometry_override"] = bolt_geometry_overrides_from_dict(raw.get("geometry_override"))
    raw["material_override"] = material_allowable_overrides_from_dict(raw.get("material_override"))
    return BoltInput(**{key: raw[key] for key in BoltInput.__dataclass_fields__ if key in raw})


def project_from_dict(data: dict[str, Any]) -> ProjectInput:
    raw = dict(data)
    raw["preload"] = preload_from_dict(raw.get("preload", {}))
    raw["advanced"] = advanced_check_inputs_from_dict(raw.get("advanced", {}))
    raw["bolts"] = [bolt_from_dict(item) for item in raw.get("bolts", [])]
    return ProjectInput(**{key: raw[key] for key in ProjectInput.__dataclass_fields__ if key in raw})


def example_project() -> ProjectInput:
    load = BoltLoadRow(
        case_id="LC1",
        set_id="1",
        bolt_id="B1",
        fy=250.0,
        fz=4200.0,
        mx=1000.0,
        mz=50.0,
        axial=4200.0,
        shear_mag=300.0,
        source_type="beam_probe",
        source_name="B1_BEAM_PROBE",
        quality_flags="check local axis",
    )
    return ProjectInput(
        project_name="Example NASA-STD-5020B separation check",
        analyst="",
        fitting_factor=1.15,
        separation_factor=1.2,
        joint_classification="critical",
        program_yield_factor=1.2,
        program_ultimate_factor=1.4,
        test_envelope_factor=1.0,
        fssep_basis_notes="Critical classification uses max(1.2, program yield factor).",
        combined_loading_expected=True,
        advanced=AdvancedCheckInputs(
            combined=CombinedLoadInputs(enabled=True),
            slip=SlipInputs(
                enabled=True,
                friction_coefficient=0.20,
                clean_uncoated_metal=True,
                factor_of_safety=1.0,
            ),
            evidence_limits=ContactEvidenceLimits(
                enabled=True,
                max_gap_allowed=0.05,
                min_contact_pressure_required=0.1,
                max_separated_area_fraction=0.1,
                max_redistributed_ptl=6000.0,
            ),
            contact_evidence=[
                ContactEvidenceRow(
                    case_id="LC1",
                    set_id="1",
                    bolt_id="B1",
                    region="under_head_contact",
                    max_gap=0.01,
                    min_contact_pressure=2.5,
                    separated_area_fraction=0.02,
                    redistributed_ptl=4300.0,
                    quality_flags="sample nonlinear contact row",
                )
            ],
        ),
        preload=PreloadInputs(
            ppi_nom=10000.0,
            gamma=0.25,
            cmin=1.0,
            nf=8,
            separation_critical=True,
            relaxation_loss=500.0,
            creep_loss=0.0,
            thermal_loss=250.0,
        ),
        bolts=[
            BoltInput(bolt_id="B1", direct_ptl=4000.0, ptl_mode="direct", load_row=load),
            BoltInput(
                bolt_id="B2",
                direct_ptl=None,
                ptl_mode="axial",
                load_row=load,
                preload_override=PreloadOverrideInputs(ppi_nom=9200.0, relaxation_loss=650.0),
                geometry_override=BoltGeometryOverrides(tensile_area=32.0, shear_area=45.0),
                material_override=MaterialAllowableOverrides(tensile_ultimate=1050.0),
                notes="Example row override: smaller fastener and lower installation preload.",
            ),
        ],
    )


def generate_text_report(project: ProjectInput, result: ProjectResult) -> str:
    recommendation = recommended_fssep(project)
    recommended_text = (
        f"{recommendation.recommended_fssep:g}" if recommendation.recommended_fssep is not None else "user-defined"
    )
    lines = [
        "NASA-STD-5020B Bolt Separation Margin Report",
        "=" * 50,
        f"Project: {project.project_name}",
        f"Analyst: {project.analyst or 'Not specified'}",
        f"Force units: {project.force_units}",
        f"Moment units: {project.moment_units}",
        "",
        "Method",
        "------",
        "Primary check: MSsep = Pp_min / (FF * FSsep * PtL) - 1",
        "Pass criterion: MSsep >= 0",
        "NASA-STD-5020B Eq. 19 is treated as axial-only in this utility.",
        f"NASA standard page: {NASA_STANDARD_PAGE_URL}",
        f"NASA-STD-5020B PDF: {NASA_5020B_REVALIDATED_PDF_URL}",
        "",
        "Default Inputs",
        "--------------",
        f"Default fitting factor FF: {project.fitting_factor:g}",
        f"Default separation factor FSsep: {project.separation_factor:g}",
        f"Joint classification: {project.joint_classification}",
        f"Recommended FSsep: {recommended_text}",
        f"FSsep recommendation basis: {recommendation.basis}",
        f"Program yield factor FSy: {project.program_yield_factor:g}",
        f"Program ultimate factor FSu: {project.program_ultimate_factor:g}",
        f"Program/test envelope factor: {project.test_envelope_factor:g}",
        f"FSsep basis notes: {project.fssep_basis_notes or 'Not specified'}",
        f"Default final minimum preload Pp_min: {result.pp_min:g} {project.force_units}",
        "Blank bolt-table override cells inherit these defaults.",
        "",
        "Warnings",
        "--------",
    ]
    if result.warnings:
        lines.extend(f"- {warning}" for warning in result.warnings)
    else:
        lines.append("- None")

    lines.extend(["", "Bolt Results", "------------"])
    for bolt_result in result.bolt_results:
        margin = bolt_result.margin_result
        lines.append(
            f"{bolt_result.bolt_id}: case={bolt_result.case_id}, set={bolt_result.set_id}, "
            f"mode={bolt_result.ptl_mode}, Pp_min={margin.pp_min:g}, FF={margin.fitting_factor:g}, "
            f"FSsep={margin.separation_factor:g}, PtL={margin.ptl:g}, demand={margin.demand:g}, "
            f"MSsep={margin.margin:.6g}, status={'PASS' if margin.passed else 'FAIL'}"
        )
        for warning in bolt_result.warnings:
            lines.append(f"  warning: {warning}")

    lines.extend(["", "Combined Load Strength Screen", "-----------------------------"])
    if result.advanced.combined_load:
        for item in result.advanced.combined_load:
            lines.append(
                f"{item.bolt_id}: {item.equation}, theory={item.theory}, "
                f"sigma={item.total_normal_stress:g}, tau={item.shear_stress:g}, "
                f"U={item.utilization:.6g}, MS={item.margin:.6g}, "
                f"equiv_PtL={item.equivalent_ptl:g}, status={'PASS' if item.passed else 'FAIL'}"
            )
            for warning in item.warnings:
                lines.append(f"  warning: {warning}")
    else:
        lines.append("Not enabled.")

    lines.extend(["", "Joint Slip", "----------"])
    if result.advanced.slip:
        for item in result.advanced.slip:
            target = item.bolt_id or "joint"
            lines.append(
                f"{target}: {item.equation}, mode={item.mode}, mu={item.effective_mu:g}, "
                f"numerator={item.numerator:g}, denominator={item.denominator:g}, "
                f"MSslip={item.margin:.6g}, status={'PASS' if item.passed else 'FAIL'}"
            )
            for warning in item.warnings:
                lines.append(f"  warning: {warning}")
    else:
        lines.append("Not enabled.")

    lines.extend(["", "Seal / Pressure Residual Compression", "------------------------------------"])
    if result.advanced.seal_pressure is not None:
        seal = result.advanced.seal_pressure
        lines.append(
            f"pressure_load={seal.pressure_separating_load:g}, residual_clamp={seal.residual_clamp:g}, "
            f"residual_contact_pressure={seal.residual_contact_pressure:g}, "
            f"contact_MS={seal.contact_pressure_margin if seal.contact_pressure_margin is not None else 'n/a'}, "
            f"clamp_MS={seal.residual_clamp_margin if seal.residual_clamp_margin is not None else 'n/a'}, "
            f"status={'PASS' if seal.passed else 'FAIL'}"
        )
        for warning in seal.warnings:
            lines.append(f"  warning: {warning}")
    else:
        lines.append("Not enabled.")

    lines.extend(["", "Nonlinear Ansys Evidence", "------------------------"])
    if result.advanced.contact_evidence:
        for item in result.advanced.contact_evidence:
            lines.append(
                f"{item.case_id}/{item.set_id}/{item.bolt_id or 'joint'} {item.region}: "
                f"status={'PASS' if item.passed else 'FAIL'}"
            )
            for warning in item.warnings:
                lines.append(f"  warning: {warning}")
    else:
        lines.append("Not enabled or no rows imported.")

    lines.extend(
        [
            "",
            f"Controlling bolt: {result.controlling_bolt_id or 'n/a'}",
            f"Controlling margin: {result.controlling_margin if result.controlling_margin is not None else 'n/a'}",
            f"Overall status: {'PASS' if result.passed else 'FAIL'}",
        ]
    )
    return "\n".join(lines)
