"""Optional installation and rolling-element load-distribution extensions.

SKF's published friction model assumes normal operating clearance and aligned
rings. The functions in this module are deliberately separated from the SKF
formula layer: they are engineering extensions whose coefficients should be
calibrated for a real bearing/installation or replaced by an ISO/TS 16281 load
distribution solution.
"""

from __future__ import annotations

import math

import numpy as np

from .models import (
    BearingDefinition,
    InstallationDefinition,
    InstallationResult,
    LoadDistributionResult,
    OperatingPoint,
)


def installation_correction(
    bearing: BearingDefinition,
    operating: OperatingPoint,
    installation: InstallationDefinition,
    calibration_scale: float = 1.0,
) -> InstallationResult:
    """Return effective loads and empirical torque multipliers.

    The extension is inactive unless ``installation.enabled`` is true. A
    negative operating clearance is interpreted as preload. Additional radial
    preload induced by clearance is estimated only when a user-supplied
    clearance stiffness is non-zero.
    """
    if not installation.enabled:
        return InstallationResult(
            effective_radial_load_n=operating.radial_load_n,
            effective_axial_load_n=operating.axial_load_n,
            clearance_multiplier=1.0,
            misalignment_multiplier=1.0,
            total_torque_multiplier=1.0,
            induced_preload_n=0.0,
        )

    warnings: list[str] = [
        "Clearance/preload and misalignment corrections are engineering extensions, not SKF table equations."
    ]
    negative_clearance_um = max(-installation.operating_clearance_um, 0.0)
    induced_preload = negative_clearance_um * installation.clearance_stiffness_n_per_um
    radial_preload = installation.radial_preload_n + induced_preload
    effective_fr = math.hypot(operating.radial_load_n, radial_preload)
    effective_fa = operating.axial_load_n + installation.axial_preload_n

    clearance_ratio = (
        installation.operating_clearance_um / installation.reference_clearance_um
    )
    # No penalty for clearance at or above the reference value. A smooth square
    # relation avoids a discontinuity at the reference clearance.
    tightness = max(1.0 - clearance_ratio, 0.0)
    clearance_multiplier = 1.0 + (
        installation.clearance_torque_coefficient
        * calibration_scale
        * tightness**2
    )

    ratio = installation.misalignment_mrad / installation.permissible_misalignment_mrad
    if bearing.is_self_aligning and ratio <= 1.0:
        misalignment_multiplier = 1.0
    else:
        # For self-aligning bearings only excess beyond the permissible value is
        # penalized. For rigid bearings the full ratio is used.
        effective_ratio = max(ratio - 1.0, 0.0) if bearing.is_self_aligning else ratio
        misalignment_multiplier = 1.0 + (
            installation.misalignment_torque_coefficient
            * calibration_scale
            * effective_ratio**2
        )

    if negative_clearance_um > 0 and installation.clearance_stiffness_n_per_um == 0:
        warnings.append(
            "Negative clearance was entered but clearance stiffness is zero; no induced preload was added to load."
        )
    if ratio > 1.0:
        warnings.append("Entered misalignment exceeds the stated permissible value.")

    return InstallationResult(
        effective_radial_load_n=effective_fr,
        effective_axial_load_n=effective_fa,
        clearance_multiplier=clearance_multiplier,
        misalignment_multiplier=misalignment_multiplier,
        total_torque_multiplier=clearance_multiplier * misalignment_multiplier,
        induced_preload_n=induced_preload,
        warnings=warnings,
    )


def rolling_element_load_distribution(
    bearing: BearingDefinition,
    radial_load_n: float,
    installation: InstallationDefinition,
) -> LoadDistributionResult:
    """Solve a generic radial rolling-element load distribution.

    This Hertz-like visualization solves ring radial displacement so that the
    sum of element force components balances the applied radial load. It is not
    used in SKF Grr/Gsl unless the user separately calibrates the installation
    correction.
    """
    z = max(int(bearing.rolling_element_count), 1)
    angles = np.linspace(0.0, 2.0 * math.pi, z, endpoint=False)
    if radial_load_n <= 0:
        return LoadDistributionResult(
            angles_deg=np.degrees(angles).tolist(),
            element_loads_n=[0.0] * z,
            radial_displacement_mm=0.0,
            maximum_element_load_n=0.0,
            loaded_element_count=0,
            converged=True,
        )

    p = max(installation.load_deflection_exponent, 1e-6)
    stiffness = max(installation.contact_stiffness_n_per_mm_p, 1e-12)
    clearance_mm = installation.operating_clearance_um * 1e-3
    preload_deflection_mm = 0.0
    if installation.radial_preload_n > 0:
        preload_deflection_mm = (installation.radial_preload_n / (z * stiffness)) ** (1.0 / p)

    # A simple tilt-induced radial approach around the circumference. The scale
    # uses half the bearing width and small-angle kinematics.
    tilt_approach_mm = 0.5 * bearing.B_mm * installation.misalignment_mrad * 1e-3

    def loads_for(displacement_mm: float) -> np.ndarray:
        approach = (
            displacement_mm * np.cos(angles)
            - 0.5 * clearance_mm
            + preload_deflection_mm
            + tilt_approach_mm * np.cos(angles)
        )
        return stiffness * np.maximum(approach, 0.0) ** p

    def residual(displacement_mm: float) -> float:
        loads = loads_for(displacement_mm)
        return float(np.sum(loads * np.cos(angles)) - radial_load_n)

    lo = 0.0
    hi = max((radial_load_n / stiffness) ** (1.0 / p) * 4.0, abs(clearance_mm) + 1e-4)
    for _ in range(80):
        if residual(hi) >= 0:
            break
        hi *= 2.0
    else:
        loads = loads_for(hi)
        return LoadDistributionResult(
            angles_deg=np.degrees(angles).tolist(),
            element_loads_n=loads.tolist(),
            radial_displacement_mm=hi,
            maximum_element_load_n=float(loads.max(initial=0.0)),
            loaded_element_count=int(np.count_nonzero(loads)),
            converged=False,
        )

    converged = False
    mid = hi
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        res = residual(mid)
        if abs(res) <= max(1e-7 * radial_load_n, 1e-6):
            converged = True
            break
        if res > 0:
            hi = mid
        else:
            lo = mid

    loads = loads_for(mid)
    return LoadDistributionResult(
        angles_deg=np.degrees(angles).tolist(),
        element_loads_n=loads.tolist(),
        radial_displacement_mm=mid,
        maximum_element_load_n=float(np.max(loads)),
        loaded_element_count=int(np.count_nonzero(loads > 0)),
        converged=converged,
    )
