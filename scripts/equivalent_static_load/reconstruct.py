"""Single-instant reconstruction from modal data.

The full response history is never materialized: the ESL target needs only
``sigma(t*) = sum_j q_j(t*) * sigma_j`` — one matvec per component. This is the
same superposition MARS solves over all time points, evaluated at one column.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from scripts.equivalent_static_load.constants import SOLVE_DTYPE
from scripts.equivalent_static_load.core import InputError
from scripts.equivalent_static_load.io_modal import ModalCoordinates, ModalField, SteadyField


@dataclass(frozen=True)
class SnappedInstant:
    """A requested time snapped onto the modal-coordinate time grid."""

    requested: float
    time: float
    index: int


def snap_to_grid(coords: ModalCoordinates, t: float) -> SnappedInstant:
    idx = int(np.argmin(np.abs(coords.times - t)))
    return SnappedInstant(requested=float(t), time=float(coords.times[idx]), index=idx)


def reconstruct_at_instant(
    field: ModalField,
    coords: ModalCoordinates,
    instant: SnappedInstant,
    steady: SteadyField | None = None,
    modes_used: int | None = None,
) -> np.ndarray:
    """Reconstruct the nodal field at one instant; returns (n_nodes, n_comp) float64.

    ``modes_used`` truncates the basis deliberately (sensitivity checks); the
    default uses every mode, matching the MARS run.
    """
    if field.num_modes != coords.num_modes:
        raise InputError(
            f"Field has {field.num_modes} modes, coordinates have {coords.num_modes}"
        )
    m = field.num_modes if modes_used is None else int(modes_used)
    if not 0 < m <= field.num_modes:
        raise InputError(f"modes_used={modes_used} outside 1..{field.num_modes}")
    q_t = coords.q[:m, instant.index].astype(SOLVE_DTYPE)
    result = np.einsum("ncm,m->nc", field.data[:, :, :m], q_t)
    if steady is not None:
        result = result + align_steady(steady, field.node_ids)
    return result


def align_steady(steady: SteadyField, node_ids: np.ndarray) -> np.ndarray:
    """Align a steady field onto ``node_ids`` order; missing nodes are an error."""
    index = {int(n): i for i, n in enumerate(steady.node_ids)}
    try:
        rows = np.fromiter((index[int(n)] for n in node_ids), dtype=np.int64, count=len(node_ids))
    except KeyError as exc:
        raise InputError(f"Steady field is missing node {exc.args[0]}") from exc
    return steady.data[rows, :]


def von_mises(tensor: np.ndarray) -> np.ndarray:
    """Von Mises from (n, 6) components in (sx, sy, sz, sxy, syz, sxz) order."""
    sx, sy, sz, sxy, syz, sxz = (tensor[:, i] for i in range(6))
    return np.sqrt(
        0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
        + 3.0 * (sxy**2 + syz**2 + sxz**2)
    )


def signed_von_mises(tensor: np.ndarray) -> np.ndarray:
    """VM signed by the trace — distinguishes tension/compression states in reports."""
    return von_mises(tensor) * np.sign(tensor[:, 0] + tensor[:, 1] + tensor[:, 2])


def interface_resultants(
    force_field: ModalField,
    coords: ModalCoordinates,
    instant: SnappedInstant,
    node_ids: np.ndarray,
    ref_point: tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Sum reconstructed element nodal forces/moments over an interface cut.

    Returns ``(F, M_ref)`` with the total moment transferred to ``ref_point``:
    ``M_ref = sum(m_i) + sum((r_i - ref) x f_i)``. ``ref_point`` must be the
    same reference the whole-engine team reduces interface loads to.
    """
    if force_field.coords is None:
        raise InputError("Modal force CSV needs X, Y, Z columns for moment transfer")
    at_t = reconstruct_at_instant(force_field, coords, instant)  # (n, 6): fx..mz
    index = {int(n): i for i, n in enumerate(force_field.node_ids)}
    missing = [int(n) for n in node_ids if int(n) not in index]
    if missing:
        raise InputError(
            f"Interface node set has {len(missing)} nodes absent from the modal "
            f"force CSV (first few: {missing[:5]})"
        )
    rows = np.fromiter((index[int(n)] for n in node_ids), dtype=np.int64, count=len(node_ids))
    forces = at_t[rows, 0:3]
    moments = at_t[rows, 3:6]
    r = force_field.coords[rows, :] - np.asarray(ref_point, dtype=SOLVE_DTYPE)
    total_force = forces.sum(axis=0)
    total_moment = moments.sum(axis=0) + np.cross(r, forces).sum(axis=0)
    return total_force, total_moment
