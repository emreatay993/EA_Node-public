# Purpose: Deterministically generate synthetic example CSVs for the thermal-correction tool.
# Map: subsystems/supporting_runtime_assets
# Tests: tests/test_strain_gauge_thermal_correction.py
"""Generate the example dataset used by the README/CLI demo.

The scenario mirrors the resolved BAB350 / titanium case:
  * constantan gauge, STC "(16)" => copper-reference curve (alpha_curve = 16),
  * bonded to titanium (alpha_part = 9) => the mismatch term is real,
  * a small gauge-factor-vs-temperature drift.

Data is built from a KNOWN mechanical strain so the tool's recovery is checkable::

    eps_measured = eps_mech_true * (1 + dF(T)/100) + eps_apparent(T)
    eps_apparent = m_cu*(T - T_ref) + (alpha_part - alpha_curve)*(T - T_ref)

Run::

    python scripts/strain_gauge_thermal_correction/examples/generate_examples.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

CHANNELS = ["SG01", "SG02", "SG03", "SG04"]
T_REF = 20.0
ALPHA_PART = 9.0      # titanium, ppm/degC
ALPHA_CURVE = 16.0    # copper STC reference, ppm/degC
M_CU = 1.1            # near-flat copper-reference curve slope, ppm/degC
GF_SLOPE_PCT = 0.008  # gauge-factor drift, %/degC


def _temperature(time: np.ndarray, peak: float) -> np.ndarray:
    # Smooth run-up/run-down bump peaking mid-test.
    return T_REF + (peak - T_REF) * np.sin(np.pi * time / time[-1])


def build_frames():
    rng = np.random.default_rng(20260630)
    n = 240
    time = np.linspace(0.0, 120.0, n)
    peaks = {"SG01": 150.0, "SG02": 170.0, "SG03": 160.0, "SG04": 140.0}
    phases = {"SG01": 0.0, "SG02": 0.7, "SG03": 1.5, "SG04": 2.3}
    amps = {"SG01": 300.0, "SG02": 220.0, "SG03": 380.0, "SG04": 160.0}

    temp = {"Time": time}
    measured = {"Time": time}
    truth = {"Time": time}
    for ch in CHANNELS:
        T = _temperature(time, peaks[ch])
        eps_mech_true = amps[ch] * np.sin(2 * np.pi * time / 40.0 + phases[ch]) + 100.0 * time / 120.0
        eps_app = M_CU * (T - T_REF) + (ALPHA_PART - ALPHA_CURVE) * (T - T_REF)
        dF = GF_SLOPE_PCT * (T - T_REF)
        eps_measured = eps_mech_true * (1.0 + dF / 100.0) + eps_app
        temp[ch] = T
        measured[ch] = eps_measured
        truth[ch] = eps_mech_true

    # Copper-reference curve points (near-flat); tiny noise -> R^2 ~ 0.999.
    t_curve = np.arange(-20.0, 261.0, 20.0)
    eps_curve = M_CU * (t_curve - T_REF) + rng.normal(0.0, 0.4, size=t_curve.size)
    curve = pd.DataFrame({"Temperature_C": t_curve, "ApparentStrain_ue": eps_curve})

    return (
        pd.DataFrame(temp),
        pd.DataFrame(measured),
        pd.DataFrame(truth),
        curve,
    )


def main() -> int:
    here = Path(__file__).resolve().parent
    temp, measured, truth, curve = build_frames()
    measured.to_csv(here / "synthetic_strain.csv", index=False)
    temp.to_csv(here / "synthetic_temperature.csv", index=False)
    truth.to_csv(here / "synthetic_ground_truth_mechanical.csv", index=False)
    curve.to_csv(here / "copper_reference_curve.csv", index=False)
    print(f"wrote example CSVs to {here}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
