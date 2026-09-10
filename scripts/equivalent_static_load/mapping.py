"""Node correspondence between the MSUP casing mesh and the rig-model casing mesh.

Strategy: NodeID join validated by coordinates; if the ID overlap is poor
(renumbered meshes), fall back to nearest-neighbor coordinate matching with a
KD-tree. Every run reports match method, coordinate errors, and unmatched
counts — poor mapping quality invalidates any derived load.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from scripts.equivalent_static_load.core import InputError


@dataclass
class MappingResult:
    """Aligned index arrays into the MSUP arrays and the rig unit-field arrays."""

    node_ids: np.ndarray
    msup_index: np.ndarray
    rig_index: np.ndarray
    method: str                    # "id_join" | "kdtree_fallback"
    n_id_matched: int
    n_kdtree_matched: int
    n_unmatched: int
    coord_rms_error: float
    coord_max_error: float

    @property
    def n_mapped(self) -> int:
        return int(self.node_ids.shape[0])


def map_nodes(
    msup_ids: np.ndarray,
    msup_xyz: np.ndarray | None,
    rig_ids: np.ndarray,
    rig_xyz: np.ndarray | None,
    coord_tol: float = 0.1,
    kdtree_max_dist: float = 1.0,
    min_id_match_fraction: float = 0.9,
) -> MappingResult:
    """Map MSUP nodes onto rig-model nodes.

    ID join is accepted when at least ``min_id_match_fraction`` of MSUP nodes
    match by ID (and coordinates agree within ``coord_tol`` where available);
    otherwise a KD-tree nearest-neighbor match within ``kdtree_max_dist`` runs.
    """
    msup_pos = {int(n): i for i, n in enumerate(msup_ids)}
    rig_pos = {int(n): i for i, n in enumerate(rig_ids)}
    common = [n for n in msup_pos if n in rig_pos]
    id_fraction = len(common) / max(len(msup_pos), 1)

    if id_fraction >= min_id_match_fraction:
        msup_index = np.asarray([msup_pos[n] for n in common], dtype=np.int64)
        rig_index = np.asarray([rig_pos[n] for n in common], dtype=np.int64)
        rms = maxe = 0.0
        if msup_xyz is not None and rig_xyz is not None:
            delta = np.linalg.norm(msup_xyz[msup_index] - rig_xyz[rig_index], axis=1)
            rms = float(np.sqrt(np.mean(delta**2)))
            maxe = float(delta.max(initial=0.0))
            keep = delta <= coord_tol
            if not keep.all():
                msup_index, rig_index = msup_index[keep], rig_index[keep]
                common = [n for n, k in zip(common, keep) if k]
        return MappingResult(
            node_ids=np.asarray(common, dtype=np.int64),
            msup_index=msup_index,
            rig_index=rig_index,
            method="id_join",
            n_id_matched=len(common),
            n_kdtree_matched=0,
            n_unmatched=len(msup_pos) - len(common),
            coord_rms_error=rms,
            coord_max_error=maxe,
        )

    if msup_xyz is None or rig_xyz is None:
        raise InputError(
            f"Only {id_fraction:.0%} of nodes match by ID (need "
            f"{min_id_match_fraction:.0%}) and coordinates are unavailable for a "
            "nearest-neighbor fallback — export X, Y, Z columns in both models"
        )

    from scipy.spatial import cKDTree

    tree = cKDTree(rig_xyz)
    dist, nearest = tree.query(msup_xyz, k=1)
    keep = dist <= kdtree_max_dist
    if not keep.any():
        raise InputError(
            f"KD-tree fallback found no rig node within {kdtree_max_dist} of any "
            "MSUP node — wrong model pair or wrong length units?"
        )
    msup_index = np.flatnonzero(keep).astype(np.int64)
    rig_index = nearest[keep].astype(np.int64)
    matched_dist = dist[keep]
    return MappingResult(
        node_ids=msup_ids[msup_index].astype(np.int64),
        msup_index=msup_index,
        rig_index=rig_index,
        method="kdtree_fallback",
        n_id_matched=len(common),
        n_kdtree_matched=int(keep.sum()),
        n_unmatched=int((~keep).sum()),
        coord_rms_error=float(np.sqrt(np.mean(matched_dist**2))),
        coord_max_error=float(matched_dist.max()),
    )
