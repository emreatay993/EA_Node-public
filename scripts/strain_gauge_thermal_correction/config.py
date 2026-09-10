# Purpose: Configuration + unit handling for strain-gauge thermal-output correction.
# Map: subsystems/supporting_runtime_assets
# Tests: tests/test_strain_gauge_thermal_correction.py
"""Configuration objects and unit helpers.

The internal strain representation is **microstrain** (1e-6 strain). This is the
natural unit for the physics here: thermal-expansion coefficients are expressed in
``ppm/degC`` (== ``microstrain/degC``), so the substrate-mismatch term
``(alpha_part - alpha_curve) * (T - T_ref)`` lands directly in microstrain.

Input/output CSV units are configurable (``microstrain`` or dimensionless
``strain``) and converted at the CSV boundary only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence, Union

MICROSTRAIN = "microstrain"
STRAIN = "strain"

# Multiply a value expressed in <unit> by this factor to get microstrain.
_UNIT_TO_MICROSTRAIN: dict[str, float] = {MICROSTRAIN: 1.0, STRAIN: 1.0e6}

# alpha_part may be a scalar (ppm/degC), an (N,2) table of (T, alpha) rows, or a
# callable T -> alpha. Likewise for the gauge-factor delta-percent spec.
AlphaSpec = Union[float, int, Sequence[Sequence[float]], Callable[..., object], None]
DeltaPctSpec = Union[float, int, Sequence[Sequence[float]], Callable[..., object], None]

_VALID_EXTRAPOLATION = ("warn", "error", "clamp", "ignore")


def unit_factor_to_microstrain(unit: str) -> float:
    """Return the factor that converts ``unit`` to microstrain."""
    key = str(unit).strip().lower()
    if key not in _UNIT_TO_MICROSTRAIN:
        raise ValueError(
            f"Unknown strain unit {unit!r}; expected one of {sorted(_UNIT_TO_MICROSTRAIN)}"
        )
    return _UNIT_TO_MICROSTRAIN[key]


@dataclass(frozen=True)
class CorrectionConfig:
    """Parameters that drive a thermal-output correction run.

    Defaults reflect the resolved BAB350 / titanium case: the manufacturer curve
    is the STC-reference (copper, ``alpha_curve ~ 16``) curve, so the substrate
    mismatch term is ON and ``alpha_part ~ 9`` (titanium).
    """

    t_ref_celsius: float = 20.0
    degree: int = 1

    # Substrate alpha-mismatch term: eps += (alpha_part - alpha_curve) * (T - T_ref).
    mismatch_enabled: bool = True
    alpha_part_ppm: AlphaSpec = 9.0  # ppm/degC; scalar | (T, alpha) table | callable
    alpha_curve_substrate_ppm: float = 16.0  # STC reference the curve was measured on

    # Gauge-factor-vs-temperature term: scale by F_ref / F(T) = 1 / (1 + dF(T)/100).
    # F_ref is optional and only used for reporting F(T); the scale needs only dF(T).
    gauge_factor_ref: Union[float, None] = None
    gauge_factor_delta_pct: DeltaPctSpec = None  # percent deviation of F at T vs F_ref
    gauge_factor_delta_is_slope: bool = True  # scalar interpreted as %/degC slope from T_ref

    # Units of input/output CSVs (internal math is always microstrain).
    measured_unit: str = MICROSTRAIN
    curve_unit: str = MICROSTRAIN
    output_unit: str = MICROSTRAIN

    extrapolation: str = "warn"  # warn | error | clamp | ignore

    def validate(self) -> None:
        if int(self.degree) < 1:
            raise ValueError("degree must be >= 1")
        unit_factor_to_microstrain(self.measured_unit)
        unit_factor_to_microstrain(self.curve_unit)
        unit_factor_to_microstrain(self.output_unit)
        if self.extrapolation not in _VALID_EXTRAPOLATION:
            raise ValueError(
                f"extrapolation must be one of {_VALID_EXTRAPOLATION}, got {self.extrapolation!r}"
            )
        if self.mismatch_enabled and self.alpha_part_ppm is None:
            raise ValueError("mismatch_enabled=True requires alpha_part_ppm to be set")
        if self.gauge_factor_ref is not None and float(self.gauge_factor_ref) <= 0.0:
            raise ValueError("gauge_factor_ref must be positive when provided")
