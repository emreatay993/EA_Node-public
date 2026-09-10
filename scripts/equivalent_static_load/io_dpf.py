"""Optional ansys-dpf-core readers for rig-model result files.

DPF is imported inside functions only — the engine, tests, and CLI work
without an Ansys installation. Result-set convention for unit fields: one
static result set per channel; a numeric ``case_label`` selects that set id,
otherwise sets are taken in channel order (1..K).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from scripts.equivalent_static_load.config import Channel
from scripts.equivalent_static_load.constants import SOLVE_DTYPE
from scripts.equivalent_static_load.core import InputError
from scripts.equivalent_static_load.io_fields import TensorField, UnitFields


def _import_dpf():
    try:
        from ansys.dpf import core as dpf  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment guard
        raise InputError(
            "ansys-dpf-core is not available in this environment; use the CSV "
            "unit-field layouts instead"
        ) from exc
    return dpf


def _nodal_stress(dpf, model, set_id: int) -> tuple[np.ndarray, np.ndarray]:
    op = dpf.operators.result.stress()
    op.inputs.data_sources.connect(model.metadata.data_sources)
    op.inputs.time_scoping.connect([int(set_id)])
    op.inputs.requested_location.connect(dpf.locations.nodal)
    fields = op.outputs.fields_container()
    if len(fields) == 0:
        raise InputError(f"No stress field for result set {set_id}")
    field = fields[0]
    ids = np.asarray(field.scoping.ids, dtype=np.int64)
    data = np.asarray(field.data, dtype=SOLVE_DTYPE)
    if data.ndim != 2 or data.shape[1] != 6:
        raise InputError(f"Unexpected stress data shape {data.shape} for set {set_id}")
    return ids, data


def _node_coords(model, node_ids: np.ndarray) -> np.ndarray | None:
    try:
        mesh = model.metadata.meshed_region
        coords_field = mesh.nodes.coordinates_field
        all_ids = np.asarray(coords_field.scoping.ids, dtype=np.int64)
        all_xyz = np.asarray(coords_field.data, dtype=SOLVE_DTYPE)
    except Exception:
        return None
    index = {int(n): i for i, n in enumerate(all_ids)}
    try:
        rows = np.fromiter((index[int(n)] for n in node_ids), dtype=np.int64, count=len(node_ids))
    except KeyError:
        return None
    return all_xyz[rows]


def read_unit_fields_from_rst(rst_path: str | Path, channels: tuple[Channel, ...]) -> UnitFields:
    """Nodal-averaged stress per channel result set, normalized by unit_load."""
    dpf = _import_dpf()
    p = Path(rst_path)
    if not p.is_file():
        raise InputError(f"Rig-model result file not found: {p}")
    model = dpf.Model(str(p))

    base_ids: np.ndarray | None = None
    stacks: list[np.ndarray] = []
    for k, channel in enumerate(channels):
        set_id = int(channel.case_label) if channel.case_label.isdigit() else k + 1
        ids, data = _nodal_stress(dpf, model, set_id)
        if base_ids is None:
            base_ids = ids
        elif not np.array_equal(ids, base_ids):
            raise InputError(
                f"Result set {set_id} (channel '{channel.name}') has a different "
                "node scoping than the first set"
            )
        stacks.append(data / float(channel.unit_load))
    assert base_ids is not None
    return UnitFields(
        node_ids=base_ids,
        coords=_node_coords(model, base_ids),
        data=np.stack(stacks, axis=2),
        channel_names=tuple(c.name for c in channels),
    )


def read_solved_field_from_rst(rst_path: str | Path, set_id: int | None = None) -> TensorField:
    """Nodal-averaged stress of a verification solve (last set by default)."""
    dpf = _import_dpf()
    p = Path(rst_path)
    if not p.is_file():
        raise InputError(f"Solved result file not found: {p}")
    model = dpf.Model(str(p))
    if set_id is None:
        set_id = int(model.metadata.time_freq_support.n_sets)
    ids, data = _nodal_stress(dpf, model, set_id)
    return TensorField(node_ids=ids, coords=_node_coords(model, ids), data=data)
