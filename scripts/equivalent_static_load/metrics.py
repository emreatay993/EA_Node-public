"""Validity metrics: does the static field actually reproduce the dynamic one?

All comparisons run on the mapped evaluation set. Von Mises is used for
reporting and weighting only — the solve itself matches tensor components.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from scripts.equivalent_static_load.reconstruct import signed_von_mises, von_mises


@dataclass
class CaseMetrics:
    critical_node: int
    vm_dyn_at_critical: float
    vm_esl_at_critical: float
    peak_ratio_at_critical: float
    weighted_r2: float
    weighted_pearson_vm: float
    hotspots: pd.DataFrame
    under_test: pd.DataFrame
    residual: np.ndarray            # (n_eval, 6) target - achieved

    @property
    def n_under_test(self) -> int:
        return int(len(self.under_test))


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    total = float(weights.sum())
    return float(np.dot(values, weights) / total) if total > 0 else 0.0


def _weighted_pearson(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    mx, my = _weighted_mean(x, w), _weighted_mean(y, w)
    cov = _weighted_mean((x - mx) * (y - my), w)
    vx = _weighted_mean((x - mx) ** 2, w)
    vy = _weighted_mean((y - my) ** 2, w)
    if vx <= 0 or vy <= 0:
        return float("nan")
    return float(cov / np.sqrt(vx * vy))


def evaluate_case(
    target: np.ndarray,
    achieved: np.ndarray,
    weights: np.ndarray,
    node_ids: np.ndarray,
    coords: np.ndarray | None,
    top_n: int = 25,
    under_test_tol: float = 0.05,
    vm_floor_frac: float = 0.10,
) -> CaseMetrics:
    """Compare achieved static field vs dynamic target on the evaluation set."""
    vm_t = von_mises(target)
    vm_a = von_mises(achieved)
    svm_t = signed_von_mises(target)
    svm_a = signed_von_mises(achieved)

    crit = int(np.argmax(vm_t))
    vm_crit_t = float(vm_t[crit])
    vm_crit_a = float(vm_a[crit])
    peak_ratio = float(vm_crit_a / vm_crit_t) if vm_crit_t > 0 else float("nan")

    # Weighted R^2 on stacked tensor components (the quantity the solver minimizes).
    n_comp = target.shape[1]
    w_rows = np.repeat(weights, n_comp)
    resid = (target - achieved).reshape(-1)
    b = target.reshape(-1)
    ss_res = float(np.dot(w_rows * resid, resid))
    b_mean = _weighted_mean(b, w_rows)
    ss_tot = float(np.dot(w_rows * (b - b_mean), b - b_mean))
    weighted_r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    def frame(mask_or_index: np.ndarray) -> pd.DataFrame:
        data: dict[str, np.ndarray] = {"NodeID": node_ids[mask_or_index]}
        if coords is not None:
            data["X"] = coords[mask_or_index, 0]
            data["Y"] = coords[mask_or_index, 1]
            data["Z"] = coords[mask_or_index, 2]
        data["vm_dyn"] = vm_t[mask_or_index]
        data["vm_esl"] = vm_a[mask_or_index]
        with np.errstate(divide="ignore", invalid="ignore"):
            data["ratio"] = np.where(
                vm_t[mask_or_index] > 0, vm_a[mask_or_index] / vm_t[mask_or_index], np.nan
            )
        data["signed_vm_dyn"] = svm_t[mask_or_index]
        data["signed_vm_esl"] = svm_a[mask_or_index]
        return pd.DataFrame(data)

    order = np.argsort(vm_t)[::-1][: max(1, top_n)]
    hotspots = frame(order)

    floor = vm_floor_frac * vm_crit_t
    under_mask = (vm_t >= floor) & (vm_a < vm_t * (1.0 - under_test_tol))
    under_index = np.flatnonzero(under_mask)
    under = frame(under_index)
    if len(under):
        under["deficit_frac"] = 1.0 - under["ratio"]
        under = under.sort_values("deficit_frac", ascending=False).reset_index(drop=True)

    return CaseMetrics(
        critical_node=int(node_ids[crit]),
        vm_dyn_at_critical=vm_crit_t,
        vm_esl_at_critical=vm_crit_a,
        peak_ratio_at_critical=peak_ratio,
        weighted_r2=weighted_r2,
        weighted_pearson_vm=_weighted_pearson(vm_t, vm_a, weights),
        hotspots=hotspots,
        under_test=under,
        residual=target - achieved,
    )


def build_weights(vm_target: np.ndarray, mode: str, exponent: float) -> np.ndarray:
    """Per-node weights: 'uniform' or 'vm' (normalized VM to a power)."""
    if mode == "uniform":
        return np.ones_like(vm_target)
    if mode == "vm":
        peak = float(vm_target.max(initial=0.0))
        if peak <= 0:
            return np.ones_like(vm_target)
        return (vm_target / peak) ** float(exponent)
    raise ValueError(f"Unknown weighting mode {mode!r}")


def region_mask(
    vm_target: np.ndarray,
    node_ids: np.ndarray,
    coords: np.ndarray | None,
    mode: str,
    value: float,
    node_list: np.ndarray | None,
    bbox: tuple[float, float, float, float, float, float] | None,
) -> np.ndarray:
    """Evaluation-region mask over the mapped node set."""
    if mode == "all":
        return np.ones(len(node_ids), dtype=bool)
    if mode == "top_vm_percent":
        if not 0 < value <= 100:
            raise ValueError(f"top_vm_percent value must be in (0, 100], got {value}")
        n_keep = max(1, int(np.ceil(len(vm_target) * value / 100.0)))
        threshold = np.partition(vm_target, -n_keep)[-n_keep]
        return vm_target >= threshold
    if mode == "node_list_csv":
        if node_list is None:
            raise ValueError("node_list required for region mode 'node_list_csv'")
        wanted = set(int(n) for n in node_list)
        return np.fromiter((int(n) in wanted for n in node_ids), dtype=bool, count=len(node_ids))
    if mode == "bbox":
        if coords is None or bbox is None:
            raise ValueError("bbox region needs coordinates and a 6-element bbox")
        xmin, ymin, zmin, xmax, ymax, zmax = bbox
        return (
            (coords[:, 0] >= xmin) & (coords[:, 0] <= xmax)
            & (coords[:, 1] >= ymin) & (coords[:, 1] <= ymax)
            & (coords[:, 2] >= zmin) & (coords[:, 2] <= zmax)
        )
    raise ValueError(f"Unknown region mode {mode!r}")
