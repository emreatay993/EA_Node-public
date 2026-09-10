"""Candidate critical-instant suggestion.

Policy (methodology note §5): the rig's blade-out cases are N instants of the
same transient — the governing peak plus instants at which *other regions*
reach their critical state. Suggestions come from evidence:

- MARS-envelope mode: cluster the per-node times-of-max of the top-VM hotspot
  population (from ``max_von_mises.csv`` + ``time_of_max_von_mises.csv``).
- Self-computed mode: reconstruct the region VM(t) envelope trace and pick its
  prominent peaks (no MARS files needed).
- Optional quadrature companion ``t* + 1/(4 f0)`` for the 90-degree-shifted
  stress pattern of a narrowband response.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from scripts.equivalent_static_load.constants import SOLVE_DTYPE
from scripts.equivalent_static_load.io_modal import ModalCoordinates, ModalField
from scripts.equivalent_static_load.reconstruct import snap_to_grid, von_mises


@dataclass(frozen=True)
class InstantSuggestion:
    time: float
    index: int
    reason: str
    driver_node: int
    vm_at_driver: float
    cluster_size: int


def suggest_from_mars_envelope(
    envelope,  # pd.DataFrame with NodeID, vm, time_of_max (io_fields.load_mars_envelope)
    coords: ModalCoordinates,
    hotspot_top_percent: float = 2.0,
    cluster_dt: float = 0.002,
    n_suggestions: int = 4,
) -> list[InstantSuggestion]:
    """Cluster hotspot times-of-max; one candidate per cluster.

    The global-max node's time is always the first suggestion; remaining
    clusters rank by their VM-weighted importance — these are the "does another
    region become critical at another time?" candidates.
    """
    df = envelope.sort_values("vm", ascending=False).reset_index(drop=True)
    n_keep = max(1, int(np.ceil(len(df) * hotspot_top_percent / 100.0)))
    hot = df.iloc[:n_keep]

    order = np.argsort(hot["time_of_max"].to_numpy())
    times = hot["time_of_max"].to_numpy()[order]
    vms = hot["vm"].to_numpy()[order]
    nodes = hot["NodeID"].to_numpy()[order]

    clusters: list[dict] = []
    for t, vm, node in zip(times, vms, nodes):
        if clusters and (t - clusters[-1]["t_max"]) <= cluster_dt:
            c = clusters[-1]
            c["t_max"] = t
            c["sum_vm"] += vm
            c["sum_vm_t"] += vm * t
            c["size"] += 1
            if vm > c["peak_vm"]:
                c["peak_vm"], c["peak_node"] = vm, node
        else:
            clusters.append(
                {
                    "t_max": t, "sum_vm": vm, "sum_vm_t": vm * t,
                    "size": 1, "peak_vm": vm, "peak_node": node,
                }
            )

    global_node = int(df.iloc[0]["NodeID"])
    global_time = float(df.iloc[0]["time_of_max"])
    suggestions: list[InstantSuggestion] = []
    seen_indices: set[int] = set()

    snapped = snap_to_grid(coords, global_time)
    suggestions.append(
        InstantSuggestion(
            time=snapped.time, index=snapped.index, reason="global_vm_max",
            driver_node=global_node, vm_at_driver=float(df.iloc[0]["vm"]), cluster_size=1,
        )
    )
    seen_indices.add(snapped.index)

    for c in sorted(clusters, key=lambda c: c["sum_vm"], reverse=True):
        if len(suggestions) >= n_suggestions:
            break
        representative_t = c["sum_vm_t"] / c["sum_vm"]
        snapped = snap_to_grid(coords, float(representative_t))
        if snapped.index in seen_indices:
            continue
        seen_indices.add(snapped.index)
        suggestions.append(
            InstantSuggestion(
                time=snapped.time, index=snapped.index, reason="hotspot_cluster",
                driver_node=int(c["peak_node"]), vm_at_driver=float(c["peak_vm"]),
                cluster_size=int(c["size"]),
            )
        )
    return suggestions


def suggest_self_computed(
    stress: ModalField,
    coords: ModalCoordinates,
    region_rows: np.ndarray,
    n_suggestions: int = 4,
    time_chunk: int = 2000,
) -> list[InstantSuggestion]:
    """Peaks of the region-max VM(t) trace, reconstructed in time chunks."""
    from scipy.signal import find_peaks

    sub = stress.data[region_rows]                    # (r, 6, m)
    node_ids = stress.node_ids[region_rows]
    n_times = coords.num_times
    trace = np.empty(n_times, dtype=SOLVE_DTYPE)
    argnode = np.empty(n_times, dtype=np.int64)
    for start in range(0, n_times, time_chunk):
        stop = min(start + time_chunk, n_times)
        q_block = coords.q[:, start:stop]             # (m, tc)
        # (r, tc, 6): components must be the last axis before the flat VM call.
        block = np.einsum("rcm,mt->rtc", sub, q_block)
        vm = von_mises(block.reshape(-1, 6)).reshape(len(region_rows), stop - start)
        trace[start:stop] = vm.max(axis=0)
        argnode[start:stop] = np.argmax(vm, axis=0)

    prominence = 0.10 * float(trace.max(initial=0.0))
    peaks, _ = find_peaks(trace, prominence=max(prominence, 1e-30))
    if len(peaks) == 0:
        peaks = np.array([int(np.argmax(trace))])
    ranked = peaks[np.argsort(trace[peaks])[::-1]][:n_suggestions]
    return [
        InstantSuggestion(
            time=float(coords.times[i]), index=int(i),
            reason="global_vm_max" if rank == 0 else "envelope_peak",
            driver_node=int(node_ids[argnode[i]]),
            vm_at_driver=float(trace[i]), cluster_size=1,
        )
        for rank, i in enumerate(ranked)
    ]


def quadrature_companion(
    base: InstantSuggestion,
    stress: ModalField,
    coords: ModalCoordinates,
    region_rows: np.ndarray,
    window: int = 256,
) -> InstantSuggestion | None:
    """Suggest ``t* + 1/(4 f0)`` where f0 is the dominant response frequency.

    f0 is estimated from the FFT of the modal coordinate with the largest
    stress-weighted contribution at t*, windowed around t*. Returns None when
    the frequency cannot be resolved or the shifted time falls off the grid.
    """
    mode_norms = np.linalg.norm(
        stress.data[region_rows].reshape(-1, stress.num_modes), axis=0
    )
    contributions = np.abs(coords.q[:, base.index]) * mode_norms
    j_star = int(np.argmax(contributions))

    half = window // 2
    lo = max(0, base.index - half)
    hi = min(coords.num_times, base.index + half)
    segment = coords.q[j_star, lo:hi]
    if len(segment) < 16:
        return None
    dt = float(np.median(np.diff(coords.times)))
    segment = (segment - segment.mean()) * np.hanning(len(segment))
    spectrum = np.abs(np.fft.rfft(segment))
    freqs = np.fft.rfftfreq(len(segment), d=dt)
    if len(spectrum) < 2:
        return None
    k = 1 + int(np.argmax(spectrum[1:]))
    f0 = float(freqs[k])
    if f0 <= 0.0:
        return None
    t_quad = base.time + 1.0 / (4.0 * f0)
    if not coords.times[0] <= t_quad <= coords.times[-1]:
        return None
    snapped = snap_to_grid(coords, t_quad)
    if snapped.index == base.index:
        return None
    return InstantSuggestion(
        time=snapped.time, index=snapped.index,
        reason=f"quadrature_of_t{base.time:.6g}_f0_{f0:.4g}Hz",
        driver_node=base.driver_node, vm_at_driver=float("nan"), cluster_size=1,
    )
