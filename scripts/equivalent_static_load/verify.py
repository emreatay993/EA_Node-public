"""Verification: compare a combined-solve field against the case target.

This is the rig-side Open Item C1 check (methodology §8): the derived loads
were computed on linear unit fields; the verification solve carries the real
nonlinear contacts and pressurized state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.equivalent_static_load.config import EslConfig
from scripts.equivalent_static_load.core import InputError, LogFn, atomic_write_text, emit
from scripts.equivalent_static_load.io_fields import TensorField, load_tensor_csv, write_csv
from scripts.equivalent_static_load.metrics import CaseMetrics, build_weights, evaluate_case
from scripts.equivalent_static_load.reconstruct import von_mises


@dataclass
class VerifyResult:
    case_id: str
    metrics: CaseMetrics
    lambda_corr: float
    accepted: bool
    n_missing_nodes: int


def verify_case(
    cfg: EslConfig,
    case_dir: str | Path,
    solved: TensorField | str | Path,
    log: LogFn = None,
) -> VerifyResult:
    """Compare the solved field with the stored case target; write reports.

    ``lambda_corr = vm_dyn(crit) / vm_solved(crit)`` is the recommended scalar
    correction; the corrected load table is written as
    ``esl_loads_corrected.csv`` (iterate: re-verify after applying).
    """
    case_path = Path(case_dir)
    target_csv = case_path / "target_field.csv"
    if not target_csv.is_file():
        raise InputError(f"{target_csv} not found — run derive first")
    target = load_tensor_csv(target_csv)
    if isinstance(solved, (str, Path)):
        solved = load_tensor_csv(solved)

    index = {int(n): i for i, n in enumerate(solved.node_ids)}
    rows_target, rows_solved = [], []
    for i, n in enumerate(target.node_ids):
        j = index.get(int(n))
        if j is not None:
            rows_target.append(i)
            rows_solved.append(j)
    n_missing = len(target.node_ids) - len(rows_target)
    if not rows_target:
        raise InputError("Solved field shares no nodes with the case target")
    if n_missing:
        emit(log, f"WARNING: {n_missing} target nodes missing from the solved field")

    t = target.data[np.asarray(rows_target)]
    s = solved.data[np.asarray(rows_solved)]
    ids = target.node_ids[np.asarray(rows_target)]
    coords = target.coords[np.asarray(rows_target)] if target.coords is not None else None

    weights = build_weights(von_mises(t), cfg.solve.weighting, cfg.solve.vm_weight_exponent)
    metrics = evaluate_case(
        t, s, weights, ids, coords,
        top_n=cfg.outputs.top_n_hotspots,
        under_test_tol=cfg.acceptance.under_test_tol,
        vm_floor_frac=cfg.acceptance.vm_floor_frac,
    )
    lam_corr = (
        float(metrics.vm_dyn_at_critical / metrics.vm_esl_at_critical)
        if metrics.vm_esl_at_critical > 0
        else float("nan")
    )
    accepted = (
        metrics.peak_ratio_at_critical >= cfg.acceptance.min_peak_ratio
        and metrics.n_under_test == 0
    )
    emit(
        log,
        f"Verification: peak ratio {metrics.peak_ratio_at_critical:.3f}, "
        f"under-test {metrics.n_under_test}, lambda_corr {lam_corr:.4g}, "
        f"accepted={accepted}",
    )

    write_csv(
        case_path / "verification_metrics.csv",
        pd.DataFrame(
            [
                {
                    "peak_ratio_at_critical": metrics.peak_ratio_at_critical,
                    "critical_node": metrics.critical_node,
                    "vm_dyn_at_critical": metrics.vm_dyn_at_critical,
                    "vm_solved_at_critical": metrics.vm_esl_at_critical,
                    "weighted_r2": metrics.weighted_r2,
                    "weighted_pearson_vm": metrics.weighted_pearson_vm,
                    "n_under_test": metrics.n_under_test,
                    "n_missing_nodes": n_missing,
                    "lambda_corr": lam_corr,
                    "accepted": accepted,
                }
            ]
        ),
    )

    loads_csv = case_path / "esl_loads.csv"
    if loads_csv.is_file() and np.isfinite(lam_corr):
        loads = pd.read_csv(loads_csv)
        loads["magnitude"] = loads["magnitude"] * lam_corr
        loads["magnitude_rt_scaled"] = loads["magnitude_rt_scaled"] * lam_corr
        loads["correction_note"] = f"scaled by lambda_corr={lam_corr:.6g}; re-verify"
        write_csv(case_path / "esl_loads_corrected.csv", loads)

    atomic_write_text(
        case_path / "verification_report.md",
        "\n".join(
            [
                f"# Verification — case `{case_path.name}`",
                "",
                f"- Accepted: **{accepted}** "
                f"(min peak ratio {cfg.acceptance.min_peak_ratio}, zero under-test required)",
                f"- Peak ratio at critical node {metrics.critical_node}: "
                f"**{metrics.peak_ratio_at_critical:.3f}**",
                f"- Recommended correction lambda_corr = **{lam_corr:.4g}** "
                "(applied in `esl_loads_corrected.csv`; re-run the combined solve and re-verify)",
                f"- Weighted R²: {metrics.weighted_r2:.4f}; Pearson (VM): "
                f"{metrics.weighted_pearson_vm:.4f}; under-test nodes: {metrics.n_under_test}",
                f"- Nodes missing from solved field: {n_missing}",
                "",
                "This comparison is the rig-side Open Item C1 evidence "
                "(combined nonlinear solve vs superposed linear prediction).",
                "",
            ]
        ),
    )
    return VerifyResult(
        case_id=case_path.name, metrics=metrics, lambda_corr=lam_corr,
        accepted=accepted, n_missing_nodes=n_missing,
    )
