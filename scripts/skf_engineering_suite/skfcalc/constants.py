"""SKF friction-model constants transcribed from the published SKF tables.

The registry intentionally stores a formula identifier separately from the
coefficients. This keeps calculations auditable and makes the selected table
row visible in saved cases and reports.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import BearingFamily


@dataclass(frozen=True, slots=True)
class SeriesConstants:
    formula: str
    coefficients: tuple[float, ...]
    kz: float
    kl: float | None = None
    row_count: int = 1
    description: str = ""
    source_status: str = "Published SKF table row"


# Deep-groove ball: R1, R2, S1, S2
DGBB: dict[str, SeriesConstants] = {
    "2": SeriesConstants("dgbb", (4.4e-7, 1.7, 2.00e-3, 100.0), 3.1),
    "3": SeriesConstants("dgbb", (4.4e-7, 1.7, 2.00e-3, 100.0), 3.1),
    "42": SeriesConstants("dgbb", (5.4e-7, 0.96, 3.00e-3, 40.0), 3.1, row_count=2),
    "43": SeriesConstants("dgbb", (5.4e-7, 0.96, 3.00e-3, 40.0), 3.1, row_count=2),
    "60": SeriesConstants("dgbb", (4.1e-7, 1.7, 3.73e-3, 14.6), 3.1),
    "630": SeriesConstants("dgbb", (4.1e-7, 1.7, 3.73e-3, 14.6), 3.1),
    "62": SeriesConstants("dgbb", (3.9e-7, 1.7, 3.23e-3, 36.5), 3.1),
    "622": SeriesConstants("dgbb", (3.9e-7, 1.7, 3.23e-3, 36.5), 3.1),
    "63": SeriesConstants("dgbb", (3.7e-7, 1.7, 2.84e-3, 92.8), 3.1),
    "623": SeriesConstants("dgbb", (3.7e-7, 1.7, 2.84e-3, 92.8), 3.1),
    "64": SeriesConstants("dgbb", (3.6e-7, 1.7, 2.43e-3, 198.0), 3.1),
    "160": SeriesConstants("dgbb", (4.3e-7, 1.7, 4.63e-3, 4.25), 3.1),
    "161": SeriesConstants("dgbb", (4.3e-7, 1.7, 4.63e-3, 4.25), 3.1),
    "617/618/628/637/638": SeriesConstants("dgbb", (4.7e-7, 1.7, 6.50e-3, 0.78), 3.1),
    "619/639": SeriesConstants("dgbb", (4.3e-7, 1.7, 4.75e-3, 3.6), 3.1),
}

# Angular contact / four-point: R1,R2,R3,S1,S2,S3
ANGULAR: dict[str, SeriesConstants] = {
    "72 B(E)": SeriesConstants("angular", (4.33e-7, 2.02, 2.44e-12, 1.82e-2, 0.71, 2.44e-12), 4.4),
    "73 B(E)": SeriesConstants("angular", (4.54e-7, 2.02, 1.84e-12, 1.64e-2, 0.71, 1.84e-12), 4.4),
    "72 AC": SeriesConstants("angular", (3.58e-7, 3.64, 3.55e-12, 1.14e-2, 1.55, 3.55e-12), 4.4),
    "73 AC": SeriesConstants("angular", (3.48e-7, 3.64, 1.66e-12, 9.85e-3, 1.55, 1.66e-12), 4.4),
    "Other single-row": SeriesConstants("angular", (5.03e-7, 1.97, 1.90e-12, 1.30e-2, 0.68, 1.91e-12), 4.4),
    "32 A": SeriesConstants("angular", (5.18e-7, 1.63, 4.18e-12, 1.08e-2, 1.47, 4.18e-12), 3.1, row_count=2),
    "33 A": SeriesConstants("angular", (5.31e-7, 1.63, 8.83e-13, 5.48e-3, 1.47, 8.83e-13), 3.1, row_count=2),
    "Other double-row": SeriesConstants("angular", (6.34e-7, 1.41, 7.83e-13, 7.56e-3, 1.21, 7.83e-13), 3.1, row_count=2),
    "Four-point contact": SeriesConstants("angular", (4.78e-7, 2.42, 1.40e-12, 1.20e-2, 0.90, 1.40e-12), 3.1),
}

# Self-aligning ball: R1,R2,R3,S1,S2,S3
SELF_ALIGNING_BALL: dict[str, SeriesConstants] = {
    "12": SeriesConstants("self_aligning_ball", (3.25e-7, 6.51, 2.43e-12, 4.36e-3, 9.33, 2.43e-12), 4.8, row_count=2),
    "13": SeriesConstants("self_aligning_ball", (3.11e-7, 5.76, 3.52e-12, 5.76e-3, 8.03, 3.52e-12), 4.8, row_count=2),
    "22": SeriesConstants("self_aligning_ball", (3.13e-7, 5.54, 3.12e-12, 5.84e-3, 6.60, 3.12e-12), 4.8, row_count=2),
    "23": SeriesConstants("self_aligning_ball", (3.11e-7, 3.87, 5.41e-12, 1.00e-2, 4.35, 5.41e-12), 4.8, row_count=2),
    "112": SeriesConstants("self_aligning_ball", (3.25e-7, 6.16, 2.48e-12, 4.33e-3, 8.44, 2.48e-12), 4.8, row_count=2),
    "130": SeriesConstants("self_aligning_ball", (2.39e-7, 5.81, 1.10e-12, 7.25e-3, 7.98, 1.10e-12), 4.8, row_count=2),
    "139": SeriesConstants("self_aligning_ball", (2.44e-7, 7.96, 5.63e-13, 4.51e-3, 12.11, 5.63e-13), 4.8, row_count=2),
}

# Cylindrical roller: R1,S1,S2
CYLINDRICAL: dict[str, SeriesConstants] = {
    "Caged N/NU/NJ/NUP 2/3": SeriesConstants("cylindrical", (1.09e-6, 0.16, 0.0015), 5.1, 0.65),
    "Caged N/NU/NJ/NUP 4": SeriesConstants("cylindrical", (1.00e-6, 0.16, 0.0015), 5.1, 0.65),
    "Caged N/NU/NJ/NUP 10": SeriesConstants("cylindrical", (1.12e-6, 0.17, 0.0015), 5.1, 0.65),
    "Caged N/NU/NJ/NUP 12/20": SeriesConstants("cylindrical", (1.23e-6, 0.16, 0.0015), 5.1, 0.65),
    "Caged N/NU/NJ/NUP 22": SeriesConstants("cylindrical", (1.40e-6, 0.16, 0.0015), 5.1, 0.65),
    "Caged N/NU/NJ/NUP 23": SeriesConstants("cylindrical", (1.48e-6, 0.16, 0.0015), 5.1, 0.65),
    "High-capacity caged 22": SeriesConstants("cylindrical", (1.54e-6, 0.16, 0.0015), 5.1, 0.65),
    "High-capacity caged 23": SeriesConstants("cylindrical", (1.63e-6, 0.16, 0.0015), 5.1, 0.65),
    "Full complement": SeriesConstants("cylindrical", (2.13e-6, 0.16, 0.0015), 6.2, 0.70),
}

# Tapered roller: R1,R2,S1,S2
TAPERED: dict[str, SeriesConstants] = {
    "302": SeriesConstants("tapered", (1.76e-6, 10.9, 0.017, 2.0), 6.0, 0.70),
    "303": SeriesConstants("tapered", (1.69e-6, 10.9, 0.017, 2.0), 6.0, 0.70),
    "313(X)": SeriesConstants("tapered", (1.84e-6, 10.9, 0.048, 2.0), 6.0, 0.70),
    "320 X": SeriesConstants("tapered", (2.38e-6, 10.9, 0.014, 2.0), 6.0, 0.70),
    "322": SeriesConstants("tapered", (2.27e-6, 10.9, 0.018, 2.0), 6.0, 0.70),
    "322 B": SeriesConstants("tapered", (2.38e-6, 10.9, 0.026, 2.0), 6.0, 0.70),
    "323": SeriesConstants("tapered", (2.38e-6, 10.9, 0.019, 2.0), 6.0, 0.70),
    "323 B": SeriesConstants("tapered", (2.79e-6, 10.9, 0.030, 2.0), 6.0, 0.70),
    "329": SeriesConstants("tapered", (2.31e-6, 10.9, 0.009, 2.0), 6.0, 0.70),
    "330": SeriesConstants("tapered", (2.71e-6, 11.3, 0.010, 2.0), 6.0, 0.70),
    "331": SeriesConstants("tapered", (2.71e-6, 10.9, 0.015, 2.0), 6.0, 0.70),
    "332": SeriesConstants("tapered", (2.71e-6, 10.9, 0.018, 2.0), 6.0, 0.70),
    "LL": SeriesConstants("tapered", (1.72e-6, 10.9, 0.0057, 2.0), 6.0, 0.70),
    "L": SeriesConstants("tapered", (2.19e-6, 10.9, 0.0093, 2.0), 6.0, 0.70),
    "LM": SeriesConstants("tapered", (2.25e-6, 10.9, 0.011, 2.0), 6.0, 0.70),
    "M": SeriesConstants("tapered", (2.48e-6, 10.9, 0.015, 2.0), 6.0, 0.70),
    "HM": SeriesConstants("tapered", (2.60e-6, 10.9, 0.020, 2.0), 6.0, 0.70),
    "H": SeriesConstants("tapered", (2.60e-6, 10.9, 0.025, 2.0), 6.0, 0.70),
    "HH": SeriesConstants("tapered", (2.51e-6, 10.9, 0.027, 2.0), 6.0, 0.70),
    "Other": SeriesConstants("tapered", (2.31e-6, 10.9, 0.019, 2.0), 6.0, 0.70),
}

# Spherical roller: R1,R2,R3,R4,S1,S2,S3,S4
SPHERICAL: dict[str, SeriesConstants] = {
    "213 E / 222 E": SeriesConstants("spherical", (1.6e-6, 5.84, 2.81e-6, 5.8, 3.62e-3, 508.0, 8.8e-3, 117.0), 5.5, 0.80, row_count=2),
    "222": SeriesConstants("spherical", (2.0e-6, 5.54, 2.92e-6, 5.5, 5.10e-3, 414.0, 9.7e-3, 100.0), 5.5, 0.80, row_count=2),
    "223": SeriesConstants("spherical", (1.7e-6, 4.1, 3.13e-6, 4.05, 6.92e-3, 124.0, 1.7e-2, 41.0), 5.5, 0.80, row_count=2),
    "223 E": SeriesConstants("spherical", (1.6e-6, 4.1, 3.14e-6, 4.05, 6.23e-3, 124.0, 1.7e-2, 41.0), 5.5, 0.80, row_count=2),
    "230": SeriesConstants("spherical", (2.4e-6, 6.44, 3.76e-6, 6.4, 4.13e-3, 755.0, 1.1e-2, 160.0), 5.5, 0.80, row_count=2),
    "231": SeriesConstants("spherical", (2.4e-6, 4.7, 4.04e-6, 4.72, 6.70e-3, 231.0, 1.7e-2, 65.0), 5.5, 0.80, row_count=2),
    "232": SeriesConstants("spherical", (2.3e-6, 4.1, 4.00e-6, 4.05, 8.66e-3, 126.0, 2.1e-2, 41.0), 5.5, 0.80, row_count=2),
    "238": SeriesConstants("spherical", (3.1e-6, 12.1, 3.82e-6, 12.0, 1.74e-3, 9495.0, 5.9e-3, 1057.0), 5.5, 0.80, row_count=2),
    "239": SeriesConstants("spherical", (2.7e-6, 8.53, 3.87e-6, 8.47, 2.77e-3, 2330.0, 8.5e-3, 371.0), 5.5, 0.80, row_count=2),
    "240": SeriesConstants("spherical", (2.9e-6, 4.87, 4.78e-6, 4.84, 6.95e-3, 240.0, 2.1e-2, 68.0), 5.5, 0.80, row_count=2),
    "241": SeriesConstants("spherical", (2.6e-6, 3.8, 4.79e-6, 3.7, 1.00e-2, 86.7, 2.9e-2, 31.0), 5.5, 0.80, row_count=2),
    "248": SeriesConstants("spherical", (3.8e-6, 9.4, 5.09e-6, 9.3, 2.80e-3, 3415.0, 1.2e-2, 486.0), 5.5, 0.80, row_count=2),
    "249": SeriesConstants("spherical", (3.0e-6, 6.67, 5.09e-6, 6.62, 3.90e-3, 887.0, 1.7e-2, 180.0), 5.5, 0.80, row_count=2),
}

# CARB: R1,R2,S1,S2
CARB: dict[str, SeriesConstants] = {
    "C22": SeriesConstants("carb", (1.17e-6, 2.08e-6, 1.32e-3, 0.8e-2), 5.3, 0.80),
    "C23": SeriesConstants("carb", (1.20e-6, 2.28e-6, 1.24e-3, 0.9e-2), 5.3, 0.80),
    "C30": SeriesConstants("carb", (1.40e-6, 2.59e-6, 1.58e-3, 1.0e-2), 5.3, 0.80),
    "C31": SeriesConstants("carb", (1.37e-6, 2.77e-6, 1.30e-3, 1.1e-2), 5.3, 0.80),
    "C32": SeriesConstants("carb", (1.33e-6, 2.63e-6, 1.31e-3, 1.1e-2), 5.3, 0.80),
    "C39": SeriesConstants("carb", (1.45e-6, 2.55e-6, 1.84e-3, 1.0e-2), 5.3, 0.80),
    "C40": SeriesConstants("carb", (1.53e-6, 3.15e-6, 1.50e-3, 1.3e-2), 5.3, 0.80),
    "C41": SeriesConstants("carb", (1.49e-6, 3.11e-6, 1.32e-3, 1.3e-2), 5.3, 0.80),
    "C49": SeriesConstants("carb", (1.49e-6, 3.24e-6, 1.39e-3, 1.5e-2), 5.3, 0.80),
    "C59": SeriesConstants("carb", (1.77e-6, 3.81e-6, 1.80e-3, 1.8e-2), 5.3, 0.80),
    "C60": SeriesConstants("carb", (1.83e-6, 5.22e-6, 1.17e-3, 2.8e-2), 5.3, 0.80),
    "C69": SeriesConstants("carb", (1.85e-6, 4.53e-6, 1.61e-3, 2.3e-2), 5.3, 0.80),
    "Full-complement proxy (calibrate)": SeriesConstants(
        "carb",
        (1.49e-6, 3.24e-6, 1.39e-3, 1.5e-2),
        6.0,
        0.75,
        source_status=(
            "Engineering proxy: SKF publishes full-complement CARB Kz/KL values but no corresponding "
            "Grr/Gsl table row in the referenced friction document; C49 G constants are used pending calibration."
        ),
    ),
}

THRUST_BALL: dict[str, SeriesConstants] = {
    "All thrust-ball series": SeriesConstants("thrust_ball", (1.03e-6, 1.6e-2), 3.8)
}

CYLINDRICAL_THRUST: dict[str, SeriesConstants] = {
    "All cylindrical-roller thrust": SeriesConstants("cylindrical_thrust", (2.25e-6, 0.154), 4.4, 0.43)
}

# Spherical roller thrust: R1,R2,R3,R4,S1,S2,S3,S4,S5
SPHERICAL_THRUST: dict[str, SeriesConstants] = {
    "292": SeriesConstants("spherical_thrust", (1.32e-6, 1.57, 1.97e-6, 3.21, 4.53e-3, 0.26, 0.02, 0.10, 0.60), 5.6, 0.58),
    "292 E": SeriesConstants("spherical_thrust", (1.32e-6, 1.65, 2.09e-6, 2.92, 5.98e-3, 0.23, 0.03, 0.17, 0.56), 5.6, 0.58),
    "293": SeriesConstants("spherical_thrust", (1.39e-6, 1.66, 1.96e-6, 3.23, 5.52e-3, 0.25, 0.02, 0.10, 0.60), 5.6, 0.58),
    "293 E": SeriesConstants("spherical_thrust", (1.16e-6, 1.64, 2.00e-6, 3.04, 4.26e-3, 0.23, 0.025, 0.15, 0.58), 5.6, 0.58),
    "294 E": SeriesConstants("spherical_thrust", (1.25e-6, 1.67, 2.15e-6, 2.86, 6.42e-3, 0.21, 0.04, 0.20, 0.54), 5.6, 0.58),
}

REGISTRY: dict[BearingFamily, dict[str, SeriesConstants]] = {
    BearingFamily.DEEP_GROOVE_BALL: DGBB,
    BearingFamily.ANGULAR_CONTACT_BALL: ANGULAR,
    BearingFamily.SELF_ALIGNING_BALL: SELF_ALIGNING_BALL,
    BearingFamily.CYLINDRICAL_ROLLER: CYLINDRICAL,
    BearingFamily.TAPERED_ROLLER: TAPERED,
    BearingFamily.SPHERICAL_ROLLER: SPHERICAL,
    BearingFamily.CARB: CARB,
    BearingFamily.THRUST_BALL: THRUST_BALL,
    BearingFamily.CYLINDRICAL_ROLLER_THRUST: CYLINDRICAL_THRUST,
    BearingFamily.SPHERICAL_ROLLER_THRUST: SPHERICAL_THRUST,
}

KRS_BY_MODE = {
    "Grease": 6e-8,
    "Oil-air": 6e-8,
    "Oil jet": 3e-8,
    "Oil bath, low level": 3e-8,
    "Oil bath, normal level": 0.0,
    "Oil bath, high level": 0.0,
}

MU_EHL_BY_LUBRICANT = {
    "Mineral oil": 0.05,
    "Synthetic oil": 0.04,
    "Transmission lubricant": 0.10,
}

# ISO 281 / SKF reliability factor values. Linear interpolation is used between
# tabulated reliability levels in life.py.
RELIABILITY_A1 = {
    90.00: 1.000,
    95.00: 0.640,
    96.00: 0.550,
    97.00: 0.470,
    98.00: 0.370,
    99.00: 0.250,
    99.20: 0.220,
    99.40: 0.190,
    99.60: 0.160,
    99.80: 0.120,
    99.90: 0.093,
    99.92: 0.087,
    99.94: 0.080,
    99.95: 0.077,
}

CONTAMINATION_PRESETS = {
    "Extreme cleanliness": (1.0, 1.0),
    "High cleanliness": (0.70, 0.85),
    "Normal cleanliness": (0.55, 0.70),
    "Slight contamination": (0.40, 0.50),
    "Typical contamination": (0.20, 0.30),
    "Severe contamination": (0.05, 0.05),
    "Very severe contamination": (0.0, 0.0),
}


def available_series(family: BearingFamily) -> list[str]:
    return list(REGISTRY[family].keys())


def get_series_constants(family: BearingFamily, series: str) -> SeriesConstants:
    table = REGISTRY[family]
    if series in table:
        return table[series]
    # Permit a complete designation beginning with a table series, favouring
    # the longest key to avoid matching "2" before "23".
    normalized = series.upper().replace(" ", "")
    matches = [key for key in table if normalized.startswith(key.upper().replace(" ", "").split("/")[0])]
    if matches:
        return table[max(matches, key=len)]
    raise KeyError(f"No SKF friction constants for {family.value}, series {series!r}.")
