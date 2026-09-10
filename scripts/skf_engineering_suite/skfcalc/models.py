"""Typed data models for the SKF Engineering Bearing Suite.

All public model inputs use engineering units:
- length: mm
- force: N
- speed: r/min
- torque: N mm
- temperature: degC
- kinematic viscosity: mm^2/s (cSt)
- thermal conductance: W/K
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class BearingFamily(str, Enum):
    DEEP_GROOVE_BALL = "Deep-groove ball"
    ANGULAR_CONTACT_BALL = "Angular-contact / four-point ball"
    SELF_ALIGNING_BALL = "Self-aligning ball"
    CYLINDRICAL_ROLLER = "Cylindrical roller"
    TAPERED_ROLLER = "Tapered roller"
    SPHERICAL_ROLLER = "Spherical roller"
    CARB = "CARB toroidal roller"
    THRUST_BALL = "Thrust ball"
    CYLINDRICAL_ROLLER_THRUST = "Cylindrical roller thrust"
    SPHERICAL_ROLLER_THRUST = "Spherical roller thrust"


class LubricationMode(str, Enum):
    GREASE = "Grease"
    OIL_AIR = "Oil-air"
    OIL_JET = "Oil jet"
    OIL_BATH_LOW = "Oil bath, low level"
    OIL_BATH_NORMAL = "Oil bath, normal level"
    OIL_BATH_HIGH = "Oil bath, high level"


class LubricantKind(str, Enum):
    MINERAL = "Mineral oil"
    SYNTHETIC = "Synthetic oil"
    TRANSMISSION = "Transmission lubricant"


class ShaftOrientation(str, Enum):
    HORIZONTAL = "Horizontal"
    VERTICAL = "Vertical"


class ThermalModel(str, Enum):
    ONE_NODE = "One-node balance"
    FOUR_NODE = "Four-node inner/element/outer/oil network"


class BearingQuality(str, Enum):
    STANDARD = "Standard"
    SKF_EXPLORER = "SKF Explorer (chart approximation)"


@dataclass(slots=True)
class BearingDefinition:
    family: BearingFamily = BearingFamily.DEEP_GROOVE_BALL
    series: str = "62"
    designation: str = "6208"
    d_mm: float = 40.0
    D_mm: float = 80.0
    B_mm: float = 18.0
    C_N: float = 32_500.0
    C0_N: float = 19_000.0
    Cu_N: float = 780.0
    Y: float = 1.5
    d1_mm: float = 47.0
    d2_mm: float = 72.0
    E_mm: float = 70.0
    rolling_element_diameter_mm: float = 10.0
    rolling_element_count: int = 10
    row_count: int = 1
    quality: BearingQuality = BearingQuality.STANDARD

    def validate(self) -> None:
        if self.d_mm <= 0 or self.D_mm <= self.d_mm:
            raise ValueError("Bearing geometry requires D > d > 0.")
        if self.B_mm <= 0:
            raise ValueError("Bearing width B must be positive.")
        if self.C_N <= 0 or self.C0_N <= 0:
            raise ValueError("Dynamic and static load ratings must be positive.")
        if self.Cu_N < 0:
            raise ValueError("Fatigue load limit Cu cannot be negative.")
        if self.Y <= 0:
            raise ValueError("Tapered-bearing factor Y must be positive.")
        if self.rolling_element_count < 1 or self.row_count < 1:
            raise ValueError("Rolling-element and row counts must be positive integers.")

    @property
    def dm_mm(self) -> float:
        return 0.5 * (self.d_mm + self.D_mm)

    @property
    def is_ball(self) -> bool:
        return self.family in {
            BearingFamily.DEEP_GROOVE_BALL,
            BearingFamily.ANGULAR_CONTACT_BALL,
            BearingFamily.SELF_ALIGNING_BALL,
            BearingFamily.THRUST_BALL,
        }

    @property
    def is_self_aligning(self) -> bool:
        return self.family in {
            BearingFamily.SELF_ALIGNING_BALL,
            BearingFamily.SPHERICAL_ROLLER,
            BearingFamily.CARB,
            BearingFamily.SPHERICAL_ROLLER_THRUST,
        }

    @property
    def is_thrust(self) -> bool:
        return self.family in {
            BearingFamily.THRUST_BALL,
            BearingFamily.CYLINDRICAL_ROLLER_THRUST,
            BearingFamily.SPHERICAL_ROLLER_THRUST,
        }


@dataclass(slots=True)
class LubricantDefinition:
    name: str = "ISO VG 46 example"
    nu40_cst: float = 46.0
    nu100_cst: float = 7.1
    density_kg_m3: float = 850.0
    cp_j_kgk: float = 2_000.0
    kind: LubricantKind = LubricantKind.MINERAL
    proven_ep_additives: bool = False

    def validate(self) -> None:
        if self.nu40_cst <= self.nu100_cst or self.nu100_cst <= 0:
            raise ValueError("Expected nu40 > nu100 > 0 for the lubricant.")
        if self.density_kg_m3 <= 0 or self.cp_j_kgk <= 0:
            raise ValueError("Lubricant density and heat capacity must be positive.")


@dataclass(slots=True)
class OperatingPoint:
    speed_rpm: float = 12_000.0
    radial_load_n: float = 5_000.0
    axial_load_n: float = 1_000.0
    equivalent_dynamic_load_n: float = 0.0

    def validate(self) -> None:
        if min(self.speed_rpm, self.radial_load_n, self.axial_load_n) < 0:
            raise ValueError("Speed and loads cannot be negative.")
        if self.equivalent_dynamic_load_n < 0:
            raise ValueError("Equivalent dynamic load cannot be negative.")


@dataclass(slots=True)
class LubricationDefinition:
    mode: LubricationMode = LubricationMode.OIL_JET
    oil_level_h_mm: float = 8.0
    shaft_orientation: ShaftOrientation = ShaftOrientation.HORIZONTAL
    vertical_submerged_width_fraction: float = 1.0
    drag_enabled: bool = True
    fixed_drag_torque_nmm: float = 0.0
    volume_factor_override: float = 0.0

    def validate(self) -> None:
        if self.oil_level_h_mm < 0:
            raise ValueError("Oil immersion level H cannot be negative.")
        if not 0 < self.vertical_submerged_width_fraction <= 1:
            raise ValueError("Vertical submerged-width fraction must be in (0, 1].")
        if self.fixed_drag_torque_nmm < 0 or self.volume_factor_override < 0:
            raise ValueError("Drag torque and volume factor cannot be negative.")


@dataclass(slots=True)
class SealDefinition:
    seal_type: str = "None"
    count: int = 0
    manual_diameter_mm: float = 0.0
    manual_Ks1: float = 0.0
    manual_Ks2: float = 0.0
    manual_beta: float = 0.0

    def validate(self) -> None:
        if self.count not in (0, 1, 2):
            raise ValueError("Seal count must be 0, 1 or 2.")
        if min(
            self.manual_diameter_mm,
            self.manual_Ks1,
            self.manual_Ks2,
            self.manual_beta,
        ) < 0:
            raise ValueError("Manual seal values cannot be negative.")


@dataclass(slots=True)
class InstallationDefinition:
    enabled: bool = False
    operating_clearance_um: float = 12.0
    reference_clearance_um: float = 12.0
    radial_preload_n: float = 0.0
    axial_preload_n: float = 0.0
    clearance_stiffness_n_per_um: float = 0.0
    misalignment_mrad: float = 0.0
    permissible_misalignment_mrad: float = 1.0
    clearance_torque_coefficient: float = 0.25
    misalignment_torque_coefficient: float = 0.20
    contact_stiffness_n_per_mm_p: float = 100_000.0
    load_deflection_exponent: float = 1.5

    def validate(self) -> None:
        if self.reference_clearance_um <= 0:
            raise ValueError("Reference clearance must be positive.")
        if min(
            self.radial_preload_n,
            self.axial_preload_n,
            self.clearance_stiffness_n_per_um,
            self.misalignment_mrad,
            self.clearance_torque_coefficient,
            self.misalignment_torque_coefficient,
            self.contact_stiffness_n_per_mm_p,
            self.load_deflection_exponent,
        ) < 0:
            raise ValueError("Installation-extension values cannot be negative.")
        if self.permissible_misalignment_mrad <= 0:
            raise ValueError("Permissible misalignment must be positive.")


@dataclass(slots=True)
class ThermalDefinition:
    model: ThermalModel = ThermalModel.FOUR_NODE
    inlet_temp_c: float = 85.0
    ambient_temp_c: float = 60.0
    shaft_boundary_temp_c: float = 80.0
    housing_boundary_temp_c: float = 65.0
    oil_flow_l_min: float = 0.12
    one_node_housing_conductance_w_k: float = 2.0
    heat_fraction_to_model: float = 1.0

    # Four-node network conductances.
    G_inner_shaft_w_k: float = 2.5
    G_outer_housing_w_k: float = 4.0
    G_inner_element_w_k: float = 8.0
    G_outer_element_w_k: float = 10.0
    G_inner_oil_w_k: float = 1.5
    G_outer_oil_w_k: float = 2.0
    G_element_oil_w_k: float = 2.5

    oil_bypass_fraction: float = 0.15
    element_heat_fraction: float = 0.35
    inner_race_heat_fraction: float = 0.30
    outer_race_heat_fraction: float = 0.35
    seal_heat_to_outer_fraction: float = 0.80
    drag_heat_to_oil_fraction: float = 0.90
    inner_contact_rth_k_w: float = 0.010
    outer_contact_rth_k_w: float = 0.010

    relaxation: float = 0.65
    tolerance_c: float = 1e-4
    max_iterations: int = 100

    def validate(self) -> None:
        if self.oil_flow_l_min < 0:
            raise ValueError("Oil flow cannot be negative.")
        if self.one_node_housing_conductance_w_k < 0:
            raise ValueError("One-node conductance cannot be negative.")
        conductances = (
            self.G_inner_shaft_w_k,
            self.G_outer_housing_w_k,
            self.G_inner_element_w_k,
            self.G_outer_element_w_k,
            self.G_inner_oil_w_k,
            self.G_outer_oil_w_k,
            self.G_element_oil_w_k,
        )
        if min(conductances) < 0:
            raise ValueError("Thermal conductances cannot be negative.")
        if not 0 < self.heat_fraction_to_model <= 1:
            raise ValueError("Heat fraction to model must be in (0, 1].")
        for name, value in (
            ("oil_bypass_fraction", self.oil_bypass_fraction),
            ("element_heat_fraction", self.element_heat_fraction),
            ("inner_race_heat_fraction", self.inner_race_heat_fraction),
            ("outer_race_heat_fraction", self.outer_race_heat_fraction),
            ("seal_heat_to_outer_fraction", self.seal_heat_to_outer_fraction),
            ("drag_heat_to_oil_fraction", self.drag_heat_to_oil_fraction),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1.")
        if self.inner_contact_rth_k_w < 0 or self.outer_contact_rth_k_w < 0:
            raise ValueError("Local contact thermal resistance cannot be negative.")
        if not 0 < self.relaxation <= 1 or self.tolerance_c <= 0 or self.max_iterations < 1:
            raise ValueError("Invalid thermal convergence controls.")


@dataclass(slots=True)
class LifeDefinition:
    enabled: bool = True
    reliability_percent: float = 90.0
    contamination_factor_ec: float = 0.55
    contamination_preset: str = "Normal cleanliness"
    explorer_axis_scale: float = 0.0

    def validate(self) -> None:
        if not 90 <= self.reliability_percent < 100:
            raise ValueError("Reliability must be between 90 and 100 percent.")
        if not 0 <= self.contamination_factor_ec <= 1:
            raise ValueError("Contamination factor eC must be in [0, 1].")
        if self.explorer_axis_scale < 0:
            raise ValueError("Explorer axis scale cannot be negative.")


@dataclass(slots=True)
class CalibrationProfile:
    name: str = "Uncalibrated"
    rolling_scale: float = 1.0
    sliding_scale: float = 1.0
    seal_scale: float = 1.0
    drag_scale: float = 1.0
    heat_transfer_scale: float = 1.0
    installation_scale: float = 1.0
    notes: str = ""

    def validate(self) -> None:
        values = (
            self.rolling_scale,
            self.sliding_scale,
            self.seal_scale,
            self.drag_scale,
            self.heat_transfer_scale,
            self.installation_scale,
        )
        if min(values) <= 0:
            raise ValueError("Calibration scale factors must be positive.")


@dataclass(slots=True)
class SolverSettings:
    enforce_validity_warnings: bool = False
    max_temperature_c: float = 500.0


@dataclass(slots=True)
class BearingCase:
    case_name: str = "SKF engineering example"
    bearing: BearingDefinition = field(default_factory=BearingDefinition)
    lubricant: LubricantDefinition = field(default_factory=LubricantDefinition)
    operating: OperatingPoint = field(default_factory=OperatingPoint)
    lubrication: LubricationDefinition = field(default_factory=LubricationDefinition)
    seal: SealDefinition = field(default_factory=SealDefinition)
    installation: InstallationDefinition = field(default_factory=InstallationDefinition)
    thermal: ThermalDefinition = field(default_factory=ThermalDefinition)
    life: LifeDefinition = field(default_factory=LifeDefinition)
    calibration: CalibrationProfile = field(default_factory=CalibrationProfile)
    settings: SolverSettings = field(default_factory=SolverSettings)

    def validate(self) -> None:
        self.bearing.validate()
        self.lubricant.validate()
        self.operating.validate()
        self.lubrication.validate()
        self.seal.validate()
        self.installation.validate()
        self.thermal.validate()
        self.life.validate()
        self.calibration.validate()
        if self.settings.max_temperature_c <= -273.15:
            raise ValueError("Maximum temperature guard is invalid.")

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))


def _enum_values(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _enum_values(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_enum_values(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_enum_values(v) for v in value)
    return value


@dataclass(slots=True)
class InstallationResult:
    effective_radial_load_n: float
    effective_axial_load_n: float
    clearance_multiplier: float
    misalignment_multiplier: float
    total_torque_multiplier: float
    induced_preload_n: float
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FrictionResult:
    viscosity_cst: float
    Grr: float
    Gsl: float
    phi_ish: float
    phi_rs: float
    phi_bl: float
    mu_sl: float
    rolling_torque_nmm: float
    sliding_torque_nmm: float
    seal_torque_nmm: float
    drag_torque_nmm: float
    total_torque_nmm: float
    rolling_power_w: float
    sliding_power_w: float
    seal_power_w: float
    drag_power_w: float
    total_power_w: float
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ThermalResult:
    contact_temperature_c: float
    inner_ring_temperature_c: float
    rolling_element_temperature_c: float
    outer_ring_temperature_c: float
    oil_outlet_temperature_c: float
    inner_contact_temperature_c: float
    outer_contact_temperature_c: float
    heat_to_shaft_w: float
    heat_to_housing_w: float
    heat_to_oil_w: float


@dataclass(slots=True)
class LifeResult:
    equivalent_dynamic_load_n: float
    load_exponent: float
    basic_life_mrev: float
    basic_life_hours: float
    reliability_factor_a1: float
    rated_viscosity_cst: float
    viscosity_ratio_kappa: float
    contamination_factor_ec: float
    askf: float
    modified_life_mrev: float
    modified_life_hours: float
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LoadDistributionResult:
    angles_deg: list[float] = field(default_factory=list)
    element_loads_n: list[float] = field(default_factory=list)
    radial_displacement_mm: float = 0.0
    maximum_element_load_n: float = 0.0
    loaded_element_count: int = 0
    converged: bool = True


@dataclass(slots=True)
class CaseResult:
    converged: bool
    iterations: int
    friction: FrictionResult
    thermal: ThermalResult
    life: LifeResult | None
    installation: InstallationResult
    load_distribution: LoadDistributionResult
    history: list[dict[str, float]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "converged": self.converged,
            "iterations": self.iterations,
            "contact_temperature_c": self.thermal.contact_temperature_c,
            "inner_ring_temperature_c": self.thermal.inner_ring_temperature_c,
            "rolling_element_temperature_c": self.thermal.rolling_element_temperature_c,
            "outer_ring_temperature_c": self.thermal.outer_ring_temperature_c,
            "oil_outlet_temperature_c": self.thermal.oil_outlet_temperature_c,
            "viscosity_cst": self.friction.viscosity_cst,
            "rolling_torque_nmm": self.friction.rolling_torque_nmm,
            "sliding_torque_nmm": self.friction.sliding_torque_nmm,
            "seal_torque_nmm": self.friction.seal_torque_nmm,
            "drag_torque_nmm": self.friction.drag_torque_nmm,
            "total_torque_nmm": self.friction.total_torque_nmm,
            "total_power_w": self.friction.total_power_w,
            "maximum_element_load_n": self.load_distribution.maximum_element_load_n,
        }
        if self.life:
            data.update(
                {
                    "basic_life_hours": self.life.basic_life_hours,
                    "modified_life_hours": self.life.modified_life_hours,
                    "viscosity_ratio_kappa": self.life.viscosity_ratio_kappa,
                    "aSKF": self.life.askf,
                }
            )
        return data
