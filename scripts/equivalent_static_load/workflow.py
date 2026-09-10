"""End-to-end orchestration: load -> map -> instants -> solve -> metrics -> outputs.

Both the CLI and the GUI worker thread call these functions, so behavior is
identical in batch and interactive use (house pattern: the GUI is a shell
around the same engine that the CLI drives).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from scripts.equivalent_static_load import report as report_mod
from scripts.equivalent_static_load.config import EslConfig
from scripts.equivalent_static_load.core import InputError, LogFn, emit
from scripts.equivalent_static_load.instants import (
    InstantSuggestion,
    quadrature_companion,
    suggest_from_mars_envelope,
    suggest_self_computed,
)
from scripts.equivalent_static_load.io_fields import (
    UnitFields,
    load_mars_envelope,
    load_node_list,
    load_tensor_csv,
    load_unit_fields,
)
from scripts.equivalent_static_load.io_loads import (
    PatternAtInstant,
    load_interface_history,
    load_pattern_csv,
    pattern_from_history,
)
from scripts.equivalent_static_load.io_modal import (
    ModalCoordinates,
    ModalField,
    SteadyField,
    check_mode_consistency,
    load_modal_coordinates,
    load_modal_field,
    load_steady_field,
)
from scripts.equivalent_static_load.mapping import MappingResult, map_nodes
from scripts.equivalent_static_load.metrics import (
    CaseMetrics,
    build_weights,
    evaluate_case,
    region_mask,
)
from scripts.equivalent_static_load.reconstruct import (
    SnappedInstant,
    align_steady,
    reconstruct_at_instant,
    snap_to_grid,
    von_mises,
)
from scripts.equivalent_static_load.solve import EslSolution, gang_matrix, solve_esl


@dataclass
class LoadedInputs:
    """Everything loaded and cross-checked, ready for per-instant derivation."""

    stress: ModalField
    coords: ModalCoordinates
    steady: SteadyField | None
    unit_fields: UnitFields
    mapping: MappingResult
    history: object | None = None  # pandas.DataFrame with Time + channel columns
    warnings: list[str] = field(default_factory=list)


@dataclass
class TierResult:
    tier: str                       # "1" | "2"
    solution: EslSolution
    metrics: CaseMetrics
    achieved: np.ndarray            # (n_eval, 6)
    pattern: PatternAtInstant | None = None


@dataclass
class CaseResult:
    instant: SnappedInstant
    case_id: str
    node_ids: np.ndarray            # evaluation node set
    coords: np.ndarray | None
    target: np.ndarray              # (n_eval, 6)
    weights: np.ndarray
    tiers: dict[str, TierResult]
    warnings: list[str] = field(default_factory=list)


@dataclass
class DeriveRunResult:
    out_dir: Path
    cases: list[CaseResult]
    instants: list[InstantSuggestion]
    mapping: MappingResult
    warnings: list[str]


def case_id_for(time: float) -> str:
    return "t" + f"{time:.6f}".replace(".", "p")


def load_inputs(cfg: EslConfig, log: LogFn = None) -> LoadedInputs:
    warnings: list[str] = []
    emit(log, f"Loading modal stress CSV: {cfg.msup.modal_stress_csv}")
    stress = load_modal_field(cfg.msup.modal_stress_csv, kind="stress")
    emit(log, f"  {stress.num_nodes} nodes x {stress.num_modes} modes")
    emit(log, f"Loading modal coordinates: {cfg.msup.modal_coordinates}")
    coords = load_modal_coordinates(cfg.msup.modal_coordinates)
    emit(log, f"  {coords.num_modes} modes x {coords.num_times} time points")
    check_mode_consistency(stress, coords, "modal stress CSV")

    steady = None
    if cfg.msup.steady_state_csv is not None:
        steady = load_steady_field(cfg.msup.steady_state_csv)
        emit(log, f"Steady field loaded ({len(steady.node_ids)} nodes)")

    emit(log, "Loading unit-load fields from the virtual rig model")
    unit_fields = load_unit_fields(cfg.unit_fields, cfg.channels)
    emit(
        log,
        f"  {unit_fields.data.shape[0]} nodes x {unit_fields.data.shape[2]} channels",
    )

    emit(log, "Mapping MSUP nodes onto rig-model nodes")
    mapping = map_nodes(
        stress.node_ids,
        stress.coords,
        unit_fields.node_ids,
        unit_fields.coords,
        coord_tol=cfg.mapping.coord_tol,
        kdtree_max_dist=cfg.mapping.kdtree_max_dist,
        min_id_match_fraction=cfg.mapping.min_id_match_fraction,
    )
    emit(
        log,
        f"  method={mapping.method}, mapped={mapping.n_mapped}, "
        f"unmatched={mapping.n_unmatched}, coord RMS={mapping.coord_rms_error:.4g}",
    )
    if mapping.n_unmatched:
        warnings.append(
            f"{mapping.n_unmatched} MSUP nodes have no rig-model counterpart "
            f"(method: {mapping.method})"
        )

    history = None
    if cfg.interface_loads_csv is not None:
        history = load_interface_history(cfg.interface_loads_csv)
        emit(log, f"Interface load history loaded ({len(history)} rows)")

    return LoadedInputs(
        stress=stress, coords=coords, steady=steady,
        unit_fields=unit_fields, mapping=mapping,
        history=history, warnings=warnings,
    )


def choose_instants(
    cfg: EslConfig,
    inputs: LoadedInputs,
    override_times: list[float] | None = None,
    log: LogFn = None,
) -> list[InstantSuggestion]:
    """Explicit times (config or override) or evidence-driven suggestions."""
    times = override_times if override_times is not None else (
        list(cfg.instants.explicit_times) if cfg.instants.mode == "explicit" else None
    )
    if times is not None:
        out = []
        for t in times:
            snapped = snap_to_grid(inputs.coords, float(t))
            out.append(
                InstantSuggestion(
                    time=snapped.time, index=snapped.index, reason="explicit",
                    driver_node=-1, vm_at_driver=float("nan"), cluster_size=1,
                )
            )
        return out

    env = cfg.instants.mars_envelope
    region_rows = _region_rows_on_msup(cfg, inputs)
    if env.max_vm_csv is not None and env.time_of_max_vm_csv is not None:
        emit(log, "Suggesting instants from MARS envelope outputs")
        envelope = load_mars_envelope(env.max_vm_csv, env.time_of_max_vm_csv)
        suggestions = suggest_from_mars_envelope(
            envelope, inputs.coords,
            hotspot_top_percent=cfg.instants.hotspot_top_percent,
            cluster_dt=cfg.instants.cluster_dt,
            n_suggestions=cfg.instants.n_suggestions,
        )
    else:
        emit(log, "Suggesting instants from self-computed region envelope")
        suggestions = suggest_self_computed(
            inputs.stress, inputs.coords, region_rows,
            n_suggestions=cfg.instants.n_suggestions,
        )

    if cfg.instants.quadrature and suggestions:
        companion = quadrature_companion(
            suggestions[0], inputs.stress, inputs.coords, region_rows
        )
        if companion is not None and all(companion.index != s.index for s in suggestions):
            suggestions.append(companion)
    for s in suggestions:
        emit(log, f"  t={s.time:.6g}s ({s.reason}, driver node {s.driver_node})")
    return suggestions


def _region_rows_on_msup(cfg: EslConfig, inputs: LoadedInputs) -> np.ndarray:
    """Rows into the MSUP arrays used for instant suggestion (cheap region proxy)."""
    rows = inputs.mapping.msup_index
    region = cfg.solve.region
    if region.mode == "node_list_csv" and region.node_list_csv is not None:
        wanted = set(int(n) for n in load_node_list(region.node_list_csv))
        keep = [i for i, n in zip(rows, inputs.stress.node_ids[rows]) if int(n) in wanted]
        if keep:
            return np.asarray(keep, dtype=np.int64)
    return rows


def _target_on_msup(
    cfg: EslConfig, inputs: LoadedInputs, instant: SnappedInstant
) -> np.ndarray:
    """Dynamic tensor target on the full MSUP node set at the instant."""
    if cfg.target.mode == "tensor_csv":
        tf = load_tensor_csv(cfg.target.tensor_csv)
        if not np.array_equal(tf.node_ids, inputs.stress.node_ids):
            index = {int(n): i for i, n in enumerate(tf.node_ids)}
            try:
                rows = np.fromiter(
                    (index[int(n)] for n in inputs.stress.node_ids),
                    dtype=np.int64, count=inputs.stress.num_nodes,
                )
            except KeyError as exc:
                raise InputError(
                    f"target.tensor_csv is missing node {exc.args[0]} present in "
                    "the modal stress CSV"
                ) from exc
            data = tf.data[rows]
        else:
            data = tf.data
        if cfg.target.subtract_steady_csv is not None:
            bias = load_steady_field(cfg.target.subtract_steady_csv)
            data = data - align_steady(bias, inputs.stress.node_ids)
        return data
    steady = inputs.steady if cfg.msup.include_steady_bias else None
    return reconstruct_at_instant(
        inputs.stress, inputs.coords, instant,
        steady=steady, modes_used=cfg.msup.modes_used,
    )


def _tier1_pattern(
    cfg: EslConfig,
    inputs: LoadedInputs,
    instant: SnappedInstant,
    pattern_csv: Path | None,
) -> PatternAtInstant | None:
    if pattern_csv is not None:
        return load_pattern_csv(pattern_csv, cfg.channels)
    if inputs.history is not None:
        return pattern_from_history(inputs.history, cfg.channels, instant.time)
    return None


def derive_case(
    cfg: EslConfig,
    inputs: LoadedInputs,
    instant: SnappedInstant,
    tier: str | None = None,
    pattern_csv: Path | None = None,
    log: LogFn = None,
) -> CaseResult:
    """Derive ESL load sets for one instant (tiers per config unless overridden)."""
    tier = tier or cfg.solve.tier
    warnings: list[str] = []
    emit(log, f"Case {case_id_for(instant.time)}: reconstructing target at t={instant.time:.6g}s")
    target_msup = _target_on_msup(cfg, inputs, instant)

    mapping = inputs.mapping
    target_eval = target_msup[mapping.msup_index]
    unit_eval = inputs.unit_fields.data[mapping.rig_index]
    node_ids = mapping.node_ids
    coords = inputs.stress.coords[mapping.msup_index] if inputs.stress.coords is not None else None

    vm_t = von_mises(target_eval)
    node_list = (
        load_node_list(cfg.solve.region.node_list_csv)
        if cfg.solve.region.node_list_csv is not None
        else None
    )
    mask = region_mask(
        vm_t, node_ids, coords,
        mode=cfg.solve.region.mode, value=cfg.solve.region.value,
        node_list=node_list, bbox=cfg.solve.region.bbox,
    )
    if not mask.any():
        raise InputError("Evaluation region is empty — check region settings")
    target_r = target_eval[mask]
    unit_r = unit_eval[mask]
    ids_r = node_ids[mask]
    coords_r = coords[mask] if coords is not None else None
    weights = build_weights(vm_t[mask], cfg.solve.weighting, cfg.solve.vm_weight_exponent)
    emit(log, f"  evaluation region: {int(mask.sum())} nodes ({cfg.solve.region.mode})")

    tiers: dict[str, TierResult] = {}

    if tier in ("1", "both"):
        pattern = _tier1_pattern(cfg, inputs, instant, pattern_csv)
        if pattern is None:
            warnings.append(
                "Tier 1 skipped: no pattern source (interface_loads_csv or --pattern-csv)"
            )
        else:
            if pattern.interpolated:
                warnings.append("Tier-1 pattern interpolated between load-history samples")
            sol = solve_esl(
                unit_r, target_r, weights, cfg.channels,
                gang_map=pattern.values.reshape(-1, 1),
                tikhonov_alpha=cfg.solve.tikhonov_alpha,
                cond_warn_threshold=cfg.solve.cond_warn_threshold,
            )
            achieved = np.einsum("nck,k->nc", unit_r, sol.loads)
            m = evaluate_case(
                target_r, achieved, weights, ids_r, coords_r,
                top_n=cfg.outputs.top_n_hotspots,
                under_test_tol=cfg.acceptance.under_test_tol,
                vm_floor_frac=cfg.acceptance.vm_floor_frac,
            )
            if m.weighted_pearson_vm < 0:
                warnings.append(
                    "Tier-1 static field anti-correlates with the target — "
                    "likely sign or channel-mapping error"
                )
            emit(log, f"  Tier 1: lambda={sol.lam:.4g}, peak ratio={m.peak_ratio_at_critical:.3f}")
            tiers["1"] = TierResult(tier="1", solution=sol, metrics=m, achieved=achieved, pattern=pattern)

    if tier in ("2", "both"):
        gang_map, _ = gang_matrix(cfg.channels)
        sol = solve_esl(
            unit_r, target_r, weights, cfg.channels,
            gang_map=gang_map,
            tikhonov_alpha=cfg.solve.tikhonov_alpha,
            cond_warn_threshold=cfg.solve.cond_warn_threshold,
        )
        achieved = np.einsum("nck,k->nc", unit_r, sol.loads)
        m = evaluate_case(
            target_r, achieved, weights, ids_r, coords_r,
            top_n=cfg.outputs.top_n_hotspots,
            under_test_tol=cfg.acceptance.under_test_tol,
            vm_floor_frac=cfg.acceptance.vm_floor_frac,
        )
        emit(log, f"  Tier 2: peak ratio={m.peak_ratio_at_critical:.3f}, R2={m.weighted_r2:.4f}")
        tiers["2"] = TierResult(tier="2", solution=sol, metrics=m, achieved=achieved)

    if not tiers:
        raise InputError("No tier could be derived — check tier setting and pattern inputs")
    for t in tiers.values():
        if t.solution.diagnostics.get("condition_warning"):
            warnings.append(
                f"Tier {t.tier}: condition number {t.solution.condition_number:.3g} "
                f"above threshold — correlated unit fields, review channel layout"
            )

    return CaseResult(
        instant=instant, case_id=case_id_for(instant.time),
        node_ids=ids_r, coords=coords_r, target=target_r, weights=weights,
        tiers=tiers, warnings=warnings,
    )


def derive_run(
    cfg: EslConfig,
    inputs: LoadedInputs | None = None,
    override_times: list[float] | None = None,
    tier: str | None = None,
    pattern_csv: Path | None = None,
    out_dir: Path | None = None,
    log: LogFn = None,
) -> DeriveRunResult:
    """Full derive: all instants, all requested tiers, all outputs written."""
    if inputs is None:
        inputs = load_inputs(cfg, log=log)
    instants = choose_instants(cfg, inputs, override_times=override_times, log=log)
    if not instants:
        raise InputError("No instants to derive — check instants settings")

    cases = [
        derive_case(cfg, inputs, snap_to_grid(inputs.coords, s.time),
                    tier=tier, pattern_csv=pattern_csv, log=log)
        for s in instants
    ]

    out = out_dir or cfg.outputs.directory
    emit(log, f"Writing outputs to {out}")
    report_mod.write_run_outputs(out, cfg, inputs, instants, cases)
    warnings = list(inputs.warnings)
    for case in cases:
        warnings.extend(f"[{case.case_id}] {w}" for w in case.warnings)
    return DeriveRunResult(
        out_dir=Path(out), cases=cases, instants=instants,
        mapping=inputs.mapping, warnings=warnings,
    )
