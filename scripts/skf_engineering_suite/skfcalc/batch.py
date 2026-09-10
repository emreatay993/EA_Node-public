"""Batch operating-map execution."""

from __future__ import annotations

import copy
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

from .io import case_from_dict
from .models import BearingCase
from .solver import solve_case


@dataclass(slots=True)
class BatchRunResult:
    dataframe: pd.DataFrame
    failed_cases: int


_OVERRIDE_MAP = {
    "speed_rpm": ("operating", "speed_rpm"),
    "radial_load_n": ("operating", "radial_load_n"),
    "axial_load_n": ("operating", "axial_load_n"),
    "equivalent_dynamic_load_n": ("operating", "equivalent_dynamic_load_n"),
    "inlet_temp_c": ("thermal", "inlet_temp_c"),
    "ambient_temp_c": ("thermal", "ambient_temp_c"),
    "shaft_boundary_temp_c": ("thermal", "shaft_boundary_temp_c"),
    "housing_boundary_temp_c": ("thermal", "housing_boundary_temp_c"),
    "oil_flow_l_min": ("thermal", "oil_flow_l_min"),
    "oil_level_h_mm": ("lubrication", "oil_level_h_mm"),
    "operating_clearance_um": ("installation", "operating_clearance_um"),
    "radial_preload_n": ("installation", "radial_preload_n"),
    "axial_preload_n": ("installation", "axial_preload_n"),
    "misalignment_mrad": ("installation", "misalignment_mrad"),
}


def _apply_row(base_case: BearingCase, row: dict) -> BearingCase:
    case = copy.deepcopy(base_case)
    for column, (section, field) in _OVERRIDE_MAP.items():
        value = row.get(column)
        if value is not None and not pd.isna(value) and value != "":
            setattr(getattr(case, section), field, float(value))
    case.case_name = str(row.get("case_id", row.get("case_name", case.case_name)))
    return case


def _solve_payload(payload: tuple[dict, dict]) -> dict:
    base_dict, row = payload
    try:
        case = _apply_row(case_from_dict(base_dict), row)
        result = solve_case(case)
        return {
            "case_id": row.get("case_id", case.case_name),
            **result.summary_dict(),
            "warnings": " | ".join(result.warnings),
            "error": "",
        }
    except Exception as exc:
        return {
            "case_id": row.get("case_id", ""),
            "converged": False,
            "warnings": "",
            "error": str(exc),
        }


def run_batch_dataframe(
    base_case: BearingCase,
    dataframe: pd.DataFrame,
    workers: int = 1,
    progress: Callable[[int, int], None] | None = None,
) -> BatchRunResult:
    if dataframe.empty:
        return BatchRunResult(pd.DataFrame(), 0)
    rows = dataframe.to_dict(orient="records")
    outputs: list[dict] = []
    failed = 0

    if workers > 1:
        payloads = [(base_case.to_dict(), row) for row in rows]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for index, future_result in enumerate(pool.map(_solve_payload, payloads), start=1):
                outputs.append(future_result)
                if future_result.get("error"):
                    failed += 1
                if progress:
                    progress(index, len(rows))
    else:
        for index, row in enumerate(rows, start=1):
            try:
                case = _apply_row(base_case, row)
                result = solve_case(case)
                outputs.append(
                    {
                        "case_id": row.get("case_id", case.case_name),
                        **result.summary_dict(),
                        "warnings": " | ".join(result.warnings),
                        "error": "",
                    }
                )
            except Exception as exc:  # batch should preserve remaining rows
                failed += 1
                outputs.append(
                    {
                        "case_id": row.get("case_id", index),
                        "converged": False,
                        "warnings": "",
                        "error": str(exc),
                    }
                )
            if progress:
                progress(index, len(rows))

    return BatchRunResult(pd.DataFrame(outputs), failed)


def run_batch_csv(
    base_case: BearingCase,
    input_path: str | Path,
    output_path: str | Path | None = None,
    workers: int = 1,
    progress: Callable[[int, int], None] | None = None,
) -> BatchRunResult:
    data = pd.read_csv(input_path)
    result = run_batch_dataframe(base_case, data, workers=workers, progress=progress)
    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        result.dataframe.to_csv(output_path, index=False)
    return result


def run_numba_dgbb_dataframe(base_case: BearingCase, dataframe: pd.DataFrame) -> BatchRunResult:
    """Run the high-throughput DGBB one-node Numba path.

    Rows may override the same operating/thermal columns as the regular batch
    solver. Rating-life and four-node outputs are intentionally not produced by
    this narrowed backend.
    """
    import numpy as np

    from .fast_dgbb import solve_numba_dgbb_map

    count = len(dataframe)
    if count == 0:
        return BatchRunResult(pd.DataFrame(), 0)

    def values(column: str, default: float) -> np.ndarray:
        if column not in dataframe:
            return np.full(count, default, dtype=float)
        series = pd.to_numeric(dataframe[column], errors="coerce").fillna(default)
        return series.to_numpy(dtype=float)

    result = solve_numba_dgbb_map(
        base_case,
        values("speed_rpm", base_case.operating.speed_rpm),
        values("radial_load_n", base_case.operating.radial_load_n),
        values("axial_load_n", base_case.operating.axial_load_n),
        values("inlet_temp_c", base_case.thermal.inlet_temp_c),
        values("ambient_temp_c", base_case.thermal.ambient_temp_c),
        values("oil_flow_l_min", base_case.thermal.oil_flow_l_min),
        values("housing_conductance_w_k", base_case.thermal.one_node_housing_conductance_w_k),
    )
    out = pd.DataFrame({key: np.asarray(value).ravel() for key, value in result.items()})
    if "case_id" in dataframe:
        out.insert(0, "case_id", dataframe["case_id"].astype(str).to_numpy())
    else:
        out.insert(0, "case_id", np.arange(count).astype(str))
    out["backend"] = "Numba DGBB one-node"
    out["warnings"] = "Fast backend omits four-node temperatures, installation correction and rating-life output."
    out["error"] = ""
    return BatchRunResult(out, int((~out["converged"].astype(bool)).sum()))


def run_numba_dgbb_csv(base_case: BearingCase, input_path: str | Path) -> BatchRunResult:
    return run_numba_dgbb_dataframe(base_case, pd.read_csv(input_path))
