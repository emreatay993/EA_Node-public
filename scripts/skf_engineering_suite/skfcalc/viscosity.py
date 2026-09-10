"""Lubricant viscosity-temperature relations."""

from __future__ import annotations

import math

from .models import LubricantDefinition


def walther_coefficients(nu40_cst: float, nu100_cst: float) -> tuple[float, float]:
    """Return the two-point ASTM D341/Walther fit coefficients A and B."""
    if nu40_cst <= nu100_cst or nu100_cst <= 0:
        raise ValueError("Expected nu40 > nu100 > 0.")

    def y(nu: float) -> float:
        return math.log10(math.log10(nu + 0.7))

    x40 = math.log10(313.15)
    x100 = math.log10(373.15)
    b = (y(nu40_cst) - y(nu100_cst)) / (x100 - x40)
    a = y(nu40_cst) + b * x40
    return a, b


def viscosity_cst(temp_c: float, lubricant: LubricantDefinition) -> float:
    """Kinematic viscosity [cSt] at temperature [degC]."""
    t_k = temp_c + 273.15
    if t_k <= 0:
        raise ValueError("Temperature must be above absolute zero.")
    a, b = walther_coefficients(lubricant.nu40_cst, lubricant.nu100_cst)
    y = a - b * math.log10(t_k)
    return max(10.0 ** (10.0**y) - 0.7, 0.05)
