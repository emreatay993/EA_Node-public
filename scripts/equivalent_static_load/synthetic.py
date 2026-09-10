"""Synthetic dataset generator — offline demo + test fixtures.

Construction guarantees a known exact answer: every modal stress field is a
linear combination of the channel unit fields (``sigma_j = sum_k B[j,k] s_k``),
so the reconstructed target at any instant lies exactly in the channel span
with loads ``P_true(t) = B^T q(t)``. The interface load history is written as
``L(t) = P_true(t) / lambda_true`` so the Tier-1 solve must recover
``lambda_true`` exactly. ``truth.json`` records both for self-checks.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.equivalent_static_load.constants import (
    FORCE_COMPONENTS,
    STRESS_COMPONENTS,
)
from scripts.equivalent_static_load.core import atomic_write_text
from scripts.equivalent_static_load.reconstruct import von_mises


def make_synthetic(
    out_dir: str | Path,
    n_nodes: int = 500,
    n_modes: int = 8,
    n_channels: int = 4,
    n_times: int = 1000,
    dt: float = 1e-4,
    lambda_true: float = 1.8,
    seed: int = 0,
) -> dict:
    """Write a complete synthetic dataset + config.json + truth.json.

    Returns the truth dict (also written to ``truth.json``).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    node_ids = np.arange(1, n_nodes + 1, dtype=np.int64)
    coords = rng.uniform(0.0, 100.0, size=(n_nodes, 3))

    # Per-unit channel fields (stress per +1 N), O(1 MPa/N) scale.
    unit_fields = rng.normal(0.0, 1.0, size=(n_nodes, 6, n_channels))
    unit_load = 1000.0  # "as-solved" magnitude written to the CSV

    # Mode mixing: sigma_j = sum_k B[j, k] * s_k
    mixing = rng.normal(0.0, 1.0, size=(n_modes, n_channels))

    # Modal coordinates: decaying sinusoids, distinct frequencies.
    times = np.arange(n_times) * dt
    freqs = np.linspace(40.0, 180.0, n_modes)
    zeta = 0.02
    amps = rng.uniform(0.5, 1.5, size=n_modes)
    q = np.stack(
        [
            a * np.exp(-zeta * 2 * np.pi * f * times) * np.sin(2 * np.pi * f * times)
            for a, f in zip(amps, freqs)
        ],
        axis=0,
    )  # (m, T)

    # ---- write modal stress CSV (MARS convention) ----
    modal_stress = np.einsum("nck,mk->ncm", unit_fields, mixing)
    stress_cols: dict[str, np.ndarray] = {
        "NodeID": node_ids, "X": coords[:, 0], "Y": coords[:, 1], "Z": coords[:, 2],
    }
    for j in range(n_modes):
        for c, comp in enumerate(STRESS_COMPONENTS):
            stress_cols[f"{comp}_Mode{j + 1}"] = modal_stress[:, c, j]
    pd.DataFrame(stress_cols).to_csv(out / "modal_stress.csv", index=False)

    # ---- write .mcf (format accepted by mcf_dpf_section_resultants.parse_mcf) ----
    lines = ["Synthetic ESL modal coordinate file", f"Number of Modes: {n_modes}", "Time    Coordinates"]
    for i, t in enumerate(times):
        values = " ".join(f"{q[j, i]: .12E}" for j in range(n_modes))
        lines.append(f"{t: .12E} {values}")
    atomic_write_text(out / "run.mcf", "\n".join(lines) + "\n")

    # ---- write unit fields CSV (wide layout, as-solved at unit_load) ----
    unit_cols: dict[str, np.ndarray] = {
        "NodeID": node_ids, "X": coords[:, 0], "Y": coords[:, 1], "Z": coords[:, 2],
    }
    for k in range(n_channels):
        for c, comp in enumerate(STRESS_COMPONENTS):
            unit_cols[f"{comp}_Case{k + 1}"] = unit_fields[:, c, k] * unit_load
    pd.DataFrame(unit_cols).to_csv(out / "unit_fields.csv", index=False)

    # ---- truth: critical instant of the exact reconstruction ----
    p_true_t = mixing.T @ q  # (K, T): exact channel loads over time
    vm_max_trace = np.empty(n_times)
    for start in range(0, n_times, 500):
        stop = min(start + 500, n_times)
        # (n, tc, 6): components last so the flat VM call sees one node-instant per row.
        block = np.einsum("ncm,mt->ntc", modal_stress, q[:, start:stop])
        vm = von_mises(block.reshape(-1, 6)).reshape(n_nodes, stop - start)
        vm_max_trace[start:stop] = vm.max(axis=0)
    t_star_idx = int(np.argmax(vm_max_trace))
    t_star = float(times[t_star_idx])
    p_true = p_true_t[:, t_star_idx]

    # ---- interface load history: L(t) = P_true(t) / lambda_true ----
    channel_names = [f"P{k + 1}" for k in range(n_channels)]
    history = {"Time": times}
    for k, name in enumerate(channel_names):
        history[f"F_{name}"] = p_true_t[k, :] / lambda_true
    pd.DataFrame(history).to_csv(out / "interface_history.csv", index=False)

    # ---- modal element nodal forces for one interface (Route A demo) ----
    n_iface = min(30, n_nodes)
    iface_rows = np.arange(n_iface)
    modal_forces = rng.normal(0.0, 100.0, size=(n_iface, 6, n_modes))
    force_cols: dict[str, np.ndarray] = {
        "NodeID": node_ids[iface_rows],
        "X": coords[iface_rows, 0], "Y": coords[iface_rows, 1], "Z": coords[iface_rows, 2],
    }
    for j in range(n_modes):
        for c, comp in enumerate(FORCE_COMPONENTS):
            force_cols[f"{comp}_Mode{j + 1}"] = modal_forces[:, c, j]
    pd.DataFrame(force_cols).to_csv(out / "modal_forces.csv", index=False)
    pd.DataFrame({"NodeID": node_ids[iface_rows]}).to_csv(out / "interface_nodes.csv", index=False)

    ref_point = (50.0, 50.0, 50.0)
    forces_t = np.einsum("ncm,m->nc", modal_forces, q[:, t_star_idx])
    resultant_f = forces_t[:, 0:3].sum(axis=0)
    r = coords[iface_rows] - np.asarray(ref_point)
    resultant_m = forces_t[:, 3:6].sum(axis=0) + np.cross(r, forces_t[:, 0:3]).sum(axis=0)

    # ---- config ----
    config = {
        "schema_version": 1,
        "title": "Synthetic ESL demo",
        "notes": "Generated by synthetic.py — exact recovery expected (see truth.json).",
        "units": {"force": "N", "moment": "N.mm", "stress": "MPa", "length": "mm"},
        "msup": {
            "modal_stress_csv": "modal_stress.csv",
            "modal_coordinates": "run.mcf",
            "modal_forces_csv": "modal_forces.csv",
        },
        "target": {"mode": "reconstruct"},
        "interface_loads_csv": "interface_history.csv",
        "rig": {
            "unit_fields": {"layout": "wide", "csv": "unit_fields.csv"},
            "channels": [
                {
                    "name": channel_names[k],
                    "case_label": f"Case{k + 1}",
                    "unit_load": unit_load,
                    "point": [float(10 * k), 0.0, 0.0],
                    "direction": [0.0, 0.0, 1.0],
                    "bounds": [-1.0e12, 1.0e12],
                    "interface_channel": f"F_{channel_names[k]}",
                    "apdl_node": 900001 + k,
                }
                for k in range(n_channels)
            ],
        },
        "interfaces": [
            {"name": "iface1", "node_list_csv": "interface_nodes.csv", "ref_point": list(ref_point)}
        ],
        "instants": {"mode": "auto", "n_suggestions": 3, "quadrature": True},
        "solve": {
            "tier": "both",
            "weighting": "vm",
            "region": {"mode": "top_vm_percent", "value": 100.0},
        },
        "acceptance": {"under_test_tol": 0.05, "vm_floor_frac": 0.10, "min_peak_ratio": 0.999},
        "scaling": {"rt_factor": 1.0, "basis_note": "synthetic demo, no RT scaling"},
        "outputs": {"directory": "esl_out", "apdl_snippet": True, "top_n_hotspots": 10},
    }
    atomic_write_text(out / "config.json", json.dumps(config, indent=2))

    truth = {
        "t_star": t_star,
        "t_star_index": t_star_idx,
        "P_true_at_t_star": [float(v) for v in p_true],
        "lambda_true": lambda_true,
        "unit_load": unit_load,
        "channel_names": channel_names,
        "interface_resultant_force": [float(v) for v in resultant_f],
        "interface_resultant_moment_about_ref": [float(v) for v in resultant_m],
        "interface_ref_point": list(ref_point),
        "seed": seed,
    }
    atomic_write_text(out / "truth.json", json.dumps(truth, indent=2))
    return truth
