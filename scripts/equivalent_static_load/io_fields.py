"""Loaders/writers for static stress fields and node lists.

Unit-load fields follow the same CSV conventions as the modal exports so the
existing extraction scripts can be reused unchanged:
- wide layout: ``NodeID, X, Y, Z, sx_<case_label>, ..., sxz_<case_label>``
- per-case layout: one CSV per channel with plain ``sx..sxz`` columns.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.equivalent_static_load.config import Channel, UnitFieldsConfig
from scripts.equivalent_static_load.constants import SOLVE_DTYPE, STRESS_COMPONENTS
from scripts.equivalent_static_load.core import InputError, atomic_write_text
from scripts.equivalent_static_load.io_modal import _extract_node_ids, _read_csv


@dataclass(frozen=True)
class TensorField:
    """A single-instant nodal tensor field, ``data`` shape (n_nodes, 6)."""

    node_ids: np.ndarray
    coords: np.ndarray | None
    data: np.ndarray


@dataclass(frozen=True)
class UnitFields:
    """Per-channel unit stress fields, ``data`` shape (n_nodes, 6, n_channels).

    Fields are normalized to +1 force unit (as-solved values divided by each
    channel's ``unit_load``).
    """

    node_ids: np.ndarray
    coords: np.ndarray | None
    data: np.ndarray
    channel_names: tuple[str, ...]


def _coords_if_present(df: pd.DataFrame) -> np.ndarray | None:
    if {"X", "Y", "Z"}.issubset(df.columns):
        return df[["X", "Y", "Z"]].to_numpy(dtype=SOLVE_DTYPE)
    return None


def _find_column(df: pd.DataFrame, name: str, source: Path) -> str:
    lower_map = {str(c).lower(): c for c in df.columns}
    key = name.lower()
    if key not in lower_map:
        raise InputError(f"Column '{name}' not found in {source}")
    return lower_map[key]


def load_unit_fields_wide(path: str | Path, channels: tuple[Channel, ...]) -> UnitFields:
    p = Path(path)
    if not p.is_file():
        raise InputError(f"Unit-fields CSV not found: {p}")
    df = _read_csv(p)
    df = df.drop_duplicates(subset=["NodeID"], keep="last") if "NodeID" in df.columns else df
    node_ids = _extract_node_ids(df)
    coords = _coords_if_present(df)
    n = len(node_ids)
    data = np.empty((n, 6, len(channels)), dtype=SOLVE_DTYPE)
    for k, channel in enumerate(channels):
        for c, comp in enumerate(STRESS_COMPONENTS):
            col = _find_column(df, f"{comp}_{channel.case_label}", p)
            data[:, c, k] = df[col].to_numpy(dtype=SOLVE_DTYPE)
        data[:, :, k] /= float(channel.unit_load)
    return UnitFields(
        node_ids=node_ids,
        coords=coords,
        data=data,
        channel_names=tuple(c.name for c in channels),
    )


def load_unit_fields_per_case(
    files: dict[str, Path], channels: tuple[Channel, ...]
) -> UnitFields:
    base: TensorField | None = None
    fields: list[np.ndarray] = []
    for channel in channels:
        if channel.case_label not in files:
            raise InputError(
                f"rig.unit_fields.per_case_files has no entry for case_label "
                f"'{channel.case_label}' (channel '{channel.name}')"
            )
        tf = load_tensor_csv(files[channel.case_label])
        if base is None:
            base = tf
        elif not np.array_equal(tf.node_ids, base.node_ids):
            raise InputError(
                f"Unit-field file for '{channel.name}' has a different node set "
                "than the first file — export all cases from the same model"
            )
        fields.append(tf.data / float(channel.unit_load))
    assert base is not None
    return UnitFields(
        node_ids=base.node_ids,
        coords=base.coords,
        data=np.stack(fields, axis=2),
        channel_names=tuple(c.name for c in channels),
    )


def load_unit_fields(cfg: UnitFieldsConfig, channels: tuple[Channel, ...]) -> UnitFields:
    if cfg.layout == "wide":
        return load_unit_fields_wide(cfg.csv, channels)
    if cfg.layout == "per_case":
        return load_unit_fields_per_case(cfg.per_case_files or {}, channels)
    if cfg.layout == "rst":
        from scripts.equivalent_static_load.io_dpf import read_unit_fields_from_rst

        return read_unit_fields_from_rst(cfg.rst, channels)
    raise InputError(f"Unknown unit-fields layout {cfg.layout!r}")


def load_tensor_csv(path: str | Path) -> TensorField:
    """Single-instant tensor field: NodeID [, X, Y, Z], sx..sxz."""
    p = Path(path)
    if not p.is_file():
        raise InputError(f"Tensor field CSV not found: {p}")
    df = _read_csv(p)
    df = df.drop_duplicates(subset=["NodeID"], keep="last") if "NodeID" in df.columns else df
    node_ids = _extract_node_ids(df)
    cols = [_find_column(df, comp, p) for comp in STRESS_COMPONENTS]
    return TensorField(
        node_ids=node_ids,
        coords=_coords_if_present(df),
        data=df[cols].to_numpy(dtype=SOLVE_DTYPE),
    )


def load_node_list(path: str | Path) -> np.ndarray:
    """Node list CSV: a NodeID column, or the first column if unnamed."""
    p = Path(path)
    if not p.is_file():
        raise InputError(f"Node list CSV not found: {p}")
    df = pd.read_csv(p)
    if "NodeID" not in df.columns:
        df = df.rename(columns={df.columns[0]: "NodeID"})
    return _extract_node_ids(df)


def load_mars_envelope(max_vm_csv: str | Path, time_of_max_csv: str | Path) -> pd.DataFrame:
    """Join MARS ``max_von_mises`` and ``time_of_max_von_mises`` outputs on NodeID.

    Returns columns: NodeID, X, Y, Z (if present), vm, time_of_max.
    """
    df_max = _read_csv(Path(max_vm_csv))
    df_time = _read_csv(Path(time_of_max_csv))
    for df, name in ((df_max, max_vm_csv), (df_time, time_of_max_csv)):
        if "NodeID" not in df.columns:
            raise InputError(f"'NodeID' column missing in {name}")
    value_col = df_max.columns[-1]
    time_col = df_time.columns[-1]
    keep = ["NodeID"] + [c for c in ("X", "Y", "Z") if c in df_max.columns]
    merged = df_max[keep + [value_col]].merge(
        df_time[["NodeID", time_col]], on="NodeID", how="inner"
    )
    return merged.rename(columns={value_col: "vm", time_col: "time_of_max"})


def field_frame(
    node_ids: np.ndarray,
    coords: np.ndarray | None,
    columns: dict[str, np.ndarray],
) -> pd.DataFrame:
    """Assemble the house output frame: NodeID, X, Y, Z, then data columns."""
    out: dict[str, np.ndarray] = {"NodeID": node_ids}
    if coords is not None:
        out["X"], out["Y"], out["Z"] = coords[:, 0], coords[:, 1], coords[:, 2]
    out.update(columns)
    return pd.DataFrame(out)


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    atomic_write_text(path, frame.to_csv(index=False, lineterminator="\n"))
