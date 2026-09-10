"""Bounded, weighted least-squares ESL solve.

One code path serves both routes:
- Route B (pattern-scaled / stress-matched DLF): ``gang_map`` is the pattern
  column ``L(t*)[:, None]`` — a single reduced variable, lambda.
- Route C (free channels): ``gang_map`` encodes ganged-channel ratios (or the
  identity), reduced variables are solved per group.

Matching is on tensor components. The full tall matrix goes to
``scipy.optimize.lsq_linear`` — normal equations are never formed (they square
the condition number; same choice as scripts/ansys_load_reconstruction, which
records ``normal_equations_used: False``). The unconstrained ``lstsq`` solution
is always computed as a diagnostic, mirroring that tool's record format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from scripts.equivalent_static_load.config import Channel
from scripts.equivalent_static_load.constants import AT_BOUND_RTOL, SOLVE_DTYPE
from scripts.equivalent_static_load.core import SolveError


@dataclass
class EslSolution:
    """Solved channel loads plus the evidence needed to defend them."""

    loads: np.ndarray                 # (n_channels,)
    reduced: np.ndarray               # (n_reduced,) solved variables
    lam: float | None                 # Route-B lambda (effective DLF), else None
    condition_number: float
    tikhonov_alpha: float
    residual_norm: float
    target_norm: float
    at_bound: np.ndarray              # (n_channels,) bool
    unconstrained_loads: np.ndarray   # diagnostic plain-lstsq solution
    method: str
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def relative_residual(self) -> float:
        return float(self.residual_norm / self.target_norm) if self.target_norm else 0.0


def gang_matrix(channels: tuple[Channel, ...]) -> tuple[np.ndarray, list[str]]:
    """Build the (n_channels, n_reduced) gang map from channel gang/ratio fields."""
    n = len(channels)
    groups: dict[str, list[int]] = {}
    singles: list[int] = []
    for k, channel in enumerate(channels):
        if channel.gang:
            groups.setdefault(channel.gang, []).append(k)
        else:
            singles.append(k)
    names: list[str] = []
    columns: list[np.ndarray] = []
    for k in singles:
        col = np.zeros(n, dtype=SOLVE_DTYPE)
        col[k] = 1.0
        columns.append(col)
        names.append(channels[k].name)
    for gang_name, members in groups.items():
        col = np.zeros(n, dtype=SOLVE_DTYPE)
        for k in members:
            ratio = channels[k].gang_ratio
            if ratio == 0.0:
                raise SolveError(f"Channel '{channels[k].name}' has gang_ratio 0")
            col[k] = ratio
        columns.append(col)
        names.append(f"gang:{gang_name}")
    return np.stack(columns, axis=1), names


def reduced_bounds(
    channels: tuple[Channel, ...], gang_map: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Translate per-channel load bounds through the gang map.

    For each reduced variable, intersect the intervals implied by every channel
    it drives. An empty intersection (e.g. a push-only channel whose pattern
    entry is negative) is reported, never silently clamped.
    """
    n_reduced = gang_map.shape[1]
    lb = np.full(n_reduced, -np.inf, dtype=SOLVE_DTYPE)
    ub = np.full(n_reduced, np.inf, dtype=SOLVE_DTYPE)
    for j in range(n_reduced):
        for k, channel in enumerate(channels):
            g = float(gang_map[k, j])
            lo, hi = channel.bounds
            if g == 0.0:
                if not (lo <= 0.0 <= hi):
                    raise SolveError(
                        f"Channel '{channel.name}' has zero coupling to reduced "
                        f"variable {j} but its bounds [{lo}, {hi}] exclude 0 — "
                        "infeasible regardless of the solved value"
                    )
                continue
            cand_lo, cand_hi = (lo / g, hi / g) if g > 0 else (hi / g, lo / g)
            lb[j] = max(lb[j], cand_lo)
            ub[j] = min(ub[j], cand_hi)
        # >= : channel bounds enforce lo < hi, so a degenerate interval only
        # arises from conflicting couplings (e.g. push-only channel with a
        # negative pattern entry collapsing lambda to [0, -0.0]).
        if lb[j] >= ub[j]:
            drivers = [channels[k].name for k in np.flatnonzero(gang_map[:, j])]
            raise SolveError(
                f"Bound conflict for reduced variable {j} (channels {drivers}): "
                f"intersection [{lb[j]}, {ub[j]}] is empty or pinned to a point. "
                "Typical cause: a push-only channel whose pattern entry is "
                "negative — review channel directions/bounds instead of clamping"
            )
    return lb, ub


def solve_esl(
    unit_fields: np.ndarray,
    target: np.ndarray,
    weights: np.ndarray,
    channels: tuple[Channel, ...],
    gang_map: np.ndarray | None = None,
    tikhonov_alpha: float = 0.0,
    cond_warn_threshold: float = 1e8,
) -> EslSolution:
    """Solve ``min_P || W^1/2 (sum_k P_k s_k - target) ||`` with bounds/gangs.

    Args:
        unit_fields: (n_eval, 6, n_channels) per +1 force unit, float64.
        target: (n_eval, 6) dynamic tensor field at the instant.
        weights: (n_eval,) non-negative per-node weights.
        channels: channel definitions (bounds are taken from here).
        gang_map: (n_channels, n_reduced); Route B passes ``pattern[:, None]``.
        tikhonov_alpha: relative regularization strength, 0 disables (default —
            regularization biases loads low, an under-test risk).
    """
    n_eval, n_comp, n_channels = unit_fields.shape
    if target.shape != (n_eval, n_comp):
        raise SolveError(f"target shape {target.shape} != {(n_eval, n_comp)}")
    if weights.shape != (n_eval,):
        raise SolveError(f"weights shape {weights.shape} != {(n_eval,)}")
    if np.any(weights < 0):
        raise SolveError("weights must be non-negative")
    if gang_map is None:
        gang_map, _ = gang_matrix(channels)
    if gang_map.shape[0] != n_channels:
        raise SolveError(f"gang_map rows {gang_map.shape[0]} != channels {n_channels}")

    a = unit_fields.reshape(n_eval * n_comp, n_channels).astype(SOLVE_DTYPE)
    b = target.reshape(n_eval * n_comp).astype(SOLVE_DTYPE)
    sqrt_w = np.repeat(np.sqrt(weights.astype(SOLVE_DTYPE)), n_comp)
    keep = sqrt_w > 0.0
    m = (a[keep] * sqrt_w[keep, None]) @ gang_map
    b_w = b[keep] * sqrt_w[keep]
    if m.shape[0] < m.shape[1]:
        raise SolveError(
            f"Under-determined solve: {m.shape[0]} weighted rows for "
            f"{m.shape[1]} unknowns — widen the evaluation region"
        )

    singular_values = np.linalg.svd(m, compute_uv=False)
    smin = float(singular_values[-1])
    cond = float("inf") if smin == 0.0 else float(singular_values[0] / smin)

    r_unconstrained = np.linalg.lstsq(m, b_w, rcond=None)[0]

    m_solve, b_solve = m, b_w
    if tikhonov_alpha > 0.0:
        # Relative regularization: alpha is dimensionless w.r.t. column scale.
        scale = np.linalg.norm(m, axis=0)
        scale[scale == 0.0] = 1.0
        m_solve = np.vstack([m, np.sqrt(tikhonov_alpha) * np.diag(scale)])
        b_solve = np.concatenate([b_w, np.zeros(m.shape[1], dtype=SOLVE_DTYPE)])

    lb, ub = reduced_bounds(channels, gang_map)
    from scipy.optimize import lsq_linear

    method = "bvls"
    try:
        result = lsq_linear(m_solve, b_solve, bounds=(lb, ub), method="bvls")
    except Exception:
        method = "trf"
        result = lsq_linear(m_solve, b_solve, bounds=(lb, ub), method="trf")
    if not result.success and result.status <= 0:
        raise SolveError(f"lsq_linear failed (status {result.status}): {result.message}")

    reduced = np.asarray(result.x, dtype=SOLVE_DTYPE)
    loads = gang_map @ reduced
    residual_norm = float(np.linalg.norm(m @ reduced - b_w))
    target_norm = float(np.linalg.norm(b_w))

    at_bound = np.zeros(n_channels, dtype=bool)
    for k, channel in enumerate(channels):
        lo, hi = channel.bounds
        scale_ref = max(1.0, abs(loads[k]))
        if np.isfinite(lo) and abs(loads[k] - lo) <= AT_BOUND_RTOL * scale_ref:
            at_bound[k] = True
        if np.isfinite(hi) and abs(loads[k] - hi) <= AT_BOUND_RTOL * scale_ref:
            at_bound[k] = True

    lam = float(reduced[0]) if gang_map.shape[1] == 1 else None
    diagnostics = {
        "algorithm": "bounded_weighted_lstsq_scipy_lsq_linear",
        "normal_equations_used": False,
        "lsq_method": method,
        "matrix": {
            "weighted_rows": int(m.shape[0]),
            "reduced_unknowns": int(m.shape[1]),
            "condition_number": cond,
            "singular_values": [float(s) for s in singular_values],
        },
        "tikhonov_alpha": float(tikhonov_alpha),
        "condition_warning": bool(cond > cond_warn_threshold),
        "reduced_bounds": {"lower": lb.tolist(), "upper": ub.tolist()},
        "lsq_status": int(result.status),
    }
    return EslSolution(
        loads=loads,
        reduced=reduced,
        lam=lam,
        condition_number=cond,
        tikhonov_alpha=float(tikhonov_alpha),
        residual_norm=residual_norm,
        target_norm=target_norm,
        at_bound=at_bound,
        unconstrained_loads=gang_map @ r_unconstrained,
        method=method,
        diagnostics=diagnostics,
    )


def closed_form_lambda(
    unit_fields: np.ndarray,
    target: np.ndarray,
    weights: np.ndarray,
    pattern: np.ndarray,
) -> float:
    """Unconstrained Route-B lambda: <a, b>_W / <a, a>_W with a = A @ pattern.

    Used as a cross-check on the solver (tests) and as the reported
    "effective dynamic amplification factor" when bounds are inactive.
    """
    n_eval, n_comp, _ = unit_fields.shape
    a = (unit_fields.reshape(n_eval * n_comp, -1) @ pattern).astype(SOLVE_DTYPE)
    b = target.reshape(n_eval * n_comp).astype(SOLVE_DTYPE)
    w = np.repeat(weights.astype(SOLVE_DTYPE), n_comp)
    denom = float(np.dot(a * w, a))
    if denom == 0.0:
        raise SolveError("Pattern produces a zero static field on the evaluation region")
    return float(np.dot(a * w, b) / denom)
