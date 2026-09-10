"""Run outputs: manifest with input hashes, CSV artifacts, markdown report, APDL.

``run_manifest.json`` is the traceability anchor of the methodology note
(§11): resolved config echo + SHA-256 of every input file + tool/library
versions. APDL export follows the MARS ``generate_apdl_ic`` precedent
(comment header, ``%.6E`` formatting, plain command list).
"""

from __future__ import annotations

import json
import platform
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from scripts.equivalent_static_load import __version__
from scripts.equivalent_static_load.config import Channel, EslConfig, input_files
from scripts.equivalent_static_load.core import atomic_write_text, sha256_of_file
from scripts.equivalent_static_load.io_fields import field_frame, write_csv
from scripts.equivalent_static_load.reconstruct import von_mises

if TYPE_CHECKING:  # pragma: no cover
    from scripts.equivalent_static_load.instants import InstantSuggestion
    from scripts.equivalent_static_load.workflow import CaseResult, LoadedInputs


def build_manifest(cfg: EslConfig) -> dict:
    import pandas
    import scipy

    hashes = {}
    for label, path in input_files(cfg).items():
        try:
            hashes[label] = {"path": str(path), "sha256": sha256_of_file(path)}
        except OSError:
            hashes[label] = {"path": str(path), "sha256": None}
    return {
        "tool": "equivalent_static_load",
        "tool_version": __version__,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "libraries": {
            "numpy": np.__version__,
            "pandas": pandas.__version__,
            "scipy": scipy.__version__,
        },
        "inputs": hashes,
        "config_echo": cfg.raw,
    }


def write_run_outputs(
    out_dir: str | Path,
    cfg: EslConfig,
    inputs: "LoadedInputs",
    instants: list["InstantSuggestion"],
    cases: list["CaseResult"],
) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    atomic_write_text(out / "run_manifest.json", json.dumps(build_manifest(cfg), indent=2, sort_keys=True))

    mapping = inputs.mapping
    atomic_write_text(
        out / "mapping_report.json",
        json.dumps(
            {
                "method": mapping.method,
                "n_mapped": mapping.n_mapped,
                "n_id_matched": mapping.n_id_matched,
                "n_kdtree_matched": mapping.n_kdtree_matched,
                "n_unmatched": mapping.n_unmatched,
                "coord_rms_error": mapping.coord_rms_error,
                "coord_max_error": mapping.coord_max_error,
                "settings": {
                    "coord_tol": cfg.mapping.coord_tol,
                    "kdtree_max_dist": cfg.mapping.kdtree_max_dist,
                    "min_id_match_fraction": cfg.mapping.min_id_match_fraction,
                },
            },
            indent=2,
        ),
    )

    write_csv(
        out / "instants_used.csv",
        pd.DataFrame(
            {
                "time_s": [s.time for s in instants],
                "index": [s.index for s in instants],
                "reason": [s.reason for s in instants],
                "driver_node": [s.driver_node for s in instants],
                "vm_at_driver": [s.vm_at_driver for s in instants],
                "cluster_size": [s.cluster_size for s in instants],
            }
        ),
    )

    for case in cases:
        write_case_outputs(out / f"case_{case.case_id}", cfg, case)

    atomic_write_text(out / "esl_report.md", build_report_md(cfg, inputs, instants, cases))
    return out


def _loads_frame(cfg: EslConfig, case: "CaseResult") -> pd.DataFrame:
    rows = []
    for tier_key in sorted(case.tiers):
        tier = case.tiers[tier_key]
        for k, channel in enumerate(cfg.channels):
            load = float(tier.solution.loads[k])
            rows.append(
                {
                    "tier": tier_key,
                    "channel": channel.name,
                    "case_label": channel.case_label,
                    "point_x": channel.point[0] if channel.point else np.nan,
                    "point_y": channel.point[1] if channel.point else np.nan,
                    "point_z": channel.point[2] if channel.point else np.nan,
                    "dir_x": channel.direction[0] if channel.direction else np.nan,
                    "dir_y": channel.direction[1] if channel.direction else np.nan,
                    "dir_z": channel.direction[2] if channel.direction else np.nan,
                    "cs": channel.cs,
                    "magnitude": load,
                    "magnitude_rt_scaled": load * cfg.scaling.rt_factor,
                    "at_bound": bool(tier.solution.at_bound[k]),
                    "pattern_value": (
                        float(tier.pattern.values[k]) if tier.pattern is not None else np.nan
                    ),
                    "unconstrained_magnitude": float(tier.solution.unconstrained_loads[k]),
                    "notes": channel.notes,
                }
            )
    return pd.DataFrame(rows)


def write_case_outputs(case_dir: Path, cfg: EslConfig, case: "CaseResult") -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    write_csv(case_dir / "esl_loads.csv", _loads_frame(cfg, case))

    comp_cols = ("sx", "sy", "sz", "sxy", "syz", "sxz")
    target_cols = {c: case.target[:, i] for i, c in enumerate(comp_cols)}
    target_cols["svm"] = von_mises(case.target)
    write_csv(case_dir / "target_field.csv", field_frame(case.node_ids, case.coords, target_cols))

    best = case.tiers.get("2") or case.tiers.get("1")
    esl_cols = {c: best.achieved[:, i] for i, c in enumerate(comp_cols)}
    esl_cols["svm"] = von_mises(best.achieved)
    write_csv(case_dir / "esl_field.csv", field_frame(case.node_ids, case.coords, esl_cols))

    residual = case.target - best.achieved
    res_cols = {f"d{c}": residual[:, i] for i, c in enumerate(comp_cols)}
    res_cols["dvm"] = von_mises(case.target) - von_mises(best.achieved)
    with np.errstate(divide="ignore", invalid="ignore"):
        res_cols["vm_ratio"] = np.where(
            von_mises(case.target) > 0,
            von_mises(best.achieved) / von_mises(case.target),
            np.nan,
        )
    write_csv(case_dir / "residual_field.csv", field_frame(case.node_ids, case.coords, res_cols))

    write_csv(case_dir / "hotspots.csv", best.metrics.hotspots)
    write_csv(case_dir / "under_test_nodes.csv", best.metrics.under_test)

    if cfg.outputs.apdl_snippet:
        for tier_key, tier in case.tiers.items():
            snippet = generate_apdl_forces(
                cfg.channels, tier.solution.loads, case.case_id, cfg.units, tier_key
            )
            atomic_write_text(case_dir / f"verify_forces_tier{tier_key}.inp", snippet)


def generate_apdl_forces(
    channels: tuple[Channel, ...],
    loads: np.ndarray,
    case_id: str,
    units: dict[str, str],
    tier: str,
) -> str:
    """APDL F-commands for the verification solve (MARS APDL-export precedent).

    Forces are given in the global CS as ``load * direction`` at each channel's
    pilot node. Channels without ``apdl_node`` are emitted as comments.
    """
    force_unit = units.get("force", "N")
    lines = [
        f"! ESL verification loads — case {case_id}, tier {tier}",
        f"! Units: force in {force_unit}; global coordinate system",
        "! Apply to the virtual rig model and run ONE combined static solve",
        "! (real contacts, pressure on) — methodology note section 8.",
        "/SOLU",
    ]
    for k, channel in enumerate(channels):
        load = float(loads[k])
        if channel.direction is None:
            lines.append(f"! {channel.name}: no direction vector — apply {load:.6E} manually")
            continue
        fx, fy, fz = (load * d for d in channel.direction)
        if channel.apdl_node is None:
            lines.append(
                f"! {channel.name}: no apdl_node — apply FX={fx:.6E} FY={fy:.6E} FZ={fz:.6E}"
            )
            continue
        node = int(channel.apdl_node)
        for comp, value in (("FX", fx), ("FY", fy), ("FZ", fz)):
            if value != 0.0:
                lines.append(f"F,{node},{comp},{value:.6E}")
    lines.append("! End of ESL verification loads")
    return "\n".join(lines) + "\n"


def _metrics_block(case: "CaseResult") -> list[str]:
    lines = []
    for tier_key in sorted(case.tiers):
        tier = case.tiers[tier_key]
        sol, m = tier.solution, tier.metrics
        lam_txt = f", lambda (effective DLF) = **{sol.lam:.4g}**" if sol.lam is not None else ""
        lines += [
            f"### Tier {tier_key}{' (pattern-scaled)' if tier_key == '1' else ' (constrained least squares)'}",
            "",
            f"- Peak ratio at critical node {m.critical_node}: **{m.peak_ratio_at_critical:.3f}** "
            f"(dyn {m.vm_dyn_at_critical:.4g} vs ESL {m.vm_esl_at_critical:.4g}){lam_txt}",
            f"- Weighted R² (tensor components): {m.weighted_r2:.4f}; "
            f"weighted Pearson (VM): {m.weighted_pearson_vm:.4f}",
            f"- Under-test nodes: **{m.n_under_test}**",
            f"- Condition number: {sol.condition_number:.4g}"
            + (" ⚠️" if sol.diagnostics.get("condition_warning") else ""),
            f"- Residual / target norm: {sol.relative_residual:.4f}; "
            f"solver: {sol.method}; Tikhonov alpha: {sol.tikhonov_alpha}",
            f"- Channels at a bound: {int(sol.at_bound.sum())}",
            "",
        ]
    return lines


def build_report_md(
    cfg: EslConfig,
    inputs: "LoadedInputs",
    instants: list["InstantSuggestion"],
    cases: list["CaseResult"],
) -> str:
    mapping = inputs.mapping
    total_under = {
        tier: sum(c.tiers[tier].metrics.n_under_test for c in cases if tier in c.tiers)
        for tier in ("1", "2")
    }
    lines = [
        f"# ESL derivation report — {cfg.title or 'untitled run'}",
        "",
        f"> Generated {datetime.now().isoformat(timespec='seconds')} — "
        f"equivalent_static_load v{__version__}. Traceability: `run_manifest.json`.",
        "",
        "## Inputs",
        "",
        f"- Modal stress: `{cfg.msup.modal_stress_csv}` "
        f"({inputs.stress.num_nodes} nodes × {inputs.stress.num_modes} modes)",
        f"- Modal coordinates: `{cfg.msup.modal_coordinates}` "
        f"({inputs.coords.num_times} time points, source: {inputs.coords.source})",
        f"- Unit fields: {cfg.unit_fields.layout} — {len(cfg.channels)} channels",
        f"- Steady bias included in target: **{cfg.msup.include_steady_bias}** "
        "(rig applies pressure physically — see methodology §7)",
        f"- Units (assumed, not validated): {cfg.units}",
        "",
        "## Mapping quality",
        "",
        f"- Method: **{mapping.method}** — mapped {mapping.n_mapped}, "
        f"ID-matched {mapping.n_id_matched}, KD-tree {mapping.n_kdtree_matched}, "
        f"unmatched {mapping.n_unmatched}",
        f"- Coordinate error: RMS {mapping.coord_rms_error:.4g}, max {mapping.coord_max_error:.4g}",
        "",
        "## Instants",
        "",
        "| time [s] | reason | driver node | cluster |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {s.time:.6g} | {s.reason} | {s.driver_node} | {s.cluster_size} |" for s in instants
    ]
    lines += ["", "## Cases", ""]
    for case in cases:
        lines += [f"## Case `{case.case_id}` (t = {case.instant.time:.6g} s)", ""]
        lines += _metrics_block(case)
        if case.warnings:
            lines += ["**Warnings:**", ""] + [f"- ⚠️ {w}" for w in case.warnings] + [""]
        top = (case.tiers.get("2") or case.tiers.get("1")).metrics.hotspots.head(10)
        lines += ["Top hotspots (best tier):", "", top.to_markdown(index=False), ""]
    lines += [
        "## Case-set coverage",
        "",
        f"- Residual under-test nodes across all cases: tier 1 = {total_under['1']}, "
        f"tier 2 = {total_under['2']} (union coverage argument: methodology §5/§9)",
        "",
        "## Scaling",
        "",
        f"- RT factor applied to reported load tables: **{cfg.scaling.rt_factor}** "
        f"({cfg.scaling.basis_note or 'no basis note provided'})",
        "",
        "## Next step",
        "",
        "- Run ONE combined static solve of the virtual rig model with "
        "`verify_forces_tier*.inp`, then `verify` against the target "
        "(methodology §8 — this is the Open Item C1 evidence).",
        "",
    ]
    return "\n".join(lines)
