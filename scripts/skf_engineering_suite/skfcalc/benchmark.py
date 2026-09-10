"""Performance benchmark for the full solver and the Numba DGBB fast path."""

from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .batch import run_batch_dataframe
from .fast_dgbb import NUMBA_AVAILABLE, solve_numba_dgbb_map
from .models import BearingCase, ThermalModel


def _median(fn, repeats: int = 3) -> float:
    values = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        values.append(time.perf_counter() - start)
    return statistics.median(values)


def run_benchmark(output: Path, sizes: tuple[int, ...] = (100, 1_000, 10_000, 100_000)) -> pd.DataFrame:
    rng = np.random.default_rng(20260819)
    case = BearingCase()
    case.thermal.model = ThermalModel.ONE_NODE
    case.thermal.oil_bypass_fraction = 0.0
    case.installation.enabled = False
    rows: list[dict] = []

    for count in sizes:
        speed = rng.uniform(2_000, 20_000, count)
        fr = rng.uniform(1_000, 15_000, count)
        fa = rng.uniform(0, 3_000, count)
        tin = rng.uniform(60, 100, count)
        tamb = rng.uniform(30, 80, count)
        flow = rng.uniform(0.08, 0.30, count)
        g = rng.uniform(1, 8, count)
        frame = pd.DataFrame({
            "case_id": np.arange(count),
            "speed_rpm": speed,
            "radial_load_n": fr,
            "axial_load_n": fa,
            "inlet_temp_c": tin,
            "ambient_temp_c": tamb,
            "oil_flow_l_min": flow,
        })

        full_count = min(count, 2_000)
        full_frame = frame.iloc[:full_count]
        elapsed = _median(lambda: run_batch_dataframe(case, full_frame, workers=1), repeats=2)
        extrapolated = elapsed * count / full_count
        rows.append({
            "cases": count,
            "backend": "Full Python solver (extrapolated above 2,000)",
            "seconds": extrapolated,
            "cases_per_second": count / extrapolated,
        })

        if NUMBA_AVAILABLE:
            solve_numba_dgbb_map(case, speed[:16], fr[:16], fa[:16], tin[:16], tamb[:16], flow[:16], g[:16])
            elapsed = _median(lambda: solve_numba_dgbb_map(case, speed, fr, fa, tin, tamb, flow, g))
            rows.append({
                "cases": count,
                "backend": "Numba DGBB one-node (warm)",
                "seconds": elapsed,
                "cases_per_second": count / elapsed,
            })

    result = pd.DataFrame(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("benchmark.csv"))
    args = parser.parse_args()
    print(run_benchmark(args.output).to_string(index=False))


if __name__ == "__main__":
    main()
