"""Loaders for modal-superposition inputs.

- Modal coordinates: ``.mcf`` (reuses the field-proven parser from the sibling
  tool ``scripts.mcf_dpf_section_resultants.core.parse_mcf``) or NASTRAN
  ``.pch`` (ported from MARS ``src/utils/file_utils.py``,
  ``parse_nastran_pch_modal_coordinates``, port date 2026-07).
- Modal nodal field CSVs in the MARS export convention:
  ``NodeID, X, Y, Z, <comp>_Mode1, ..., <comp>_ModeN`` where ``<comp>`` is
  ``sx..sxz`` for stress or ``enfox..enmoz`` for element nodal forces/moments.
  Loader semantics (duplicate NodeIDs keep-last, contains-prefix column
  matching, integer-like NodeID coercion) intentionally replicate MARS
  ``src/file_io/loaders.py`` so both tools accept identical files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.equivalent_static_load.constants import (
    FORCE_COMPONENTS,
    FORCE_PREFIXES,
    SOLVE_DTYPE,
    STRESS_COMPONENTS,
    STRESS_PREFIXES,
)
from scripts.equivalent_static_load.core import InputError


@dataclass(frozen=True)
class ModalCoordinates:
    """Modal coordinate histories, shape (num_modes, num_time_points)."""

    q: np.ndarray
    times: np.ndarray
    source: str

    @property
    def num_modes(self) -> int:
        return int(self.q.shape[0])

    @property
    def num_times(self) -> int:
        return int(self.q.shape[1])


@dataclass(frozen=True)
class ModalField:
    """Per-mode nodal field: ``data`` has shape (n_nodes, n_comp, n_modes)."""

    node_ids: np.ndarray
    coords: np.ndarray | None
    data: np.ndarray
    components: tuple[str, ...]
    source: str

    @property
    def num_nodes(self) -> int:
        return int(self.data.shape[0])

    @property
    def num_modes(self) -> int:
        return int(self.data.shape[2])


@dataclass(frozen=True)
class SteadyField:
    """Static bias field: ``data`` has shape (n_nodes, 6)."""

    node_ids: np.ndarray
    data: np.ndarray


def load_modal_coordinates(path: str | Path) -> ModalCoordinates:
    """Load modal coordinates from ``.mcf`` (house parser) or ``.pch`` (MARS port)."""
    p = Path(path)
    if not p.is_file():
        raise InputError(f"Modal coordinates file not found: {p}")
    if p.suffix.lower() == ".pch" or _looks_like_pch(p):
        q, times = _parse_pch(p)
        return ModalCoordinates(q=q, times=times, source="pch")
    try:
        from scripts.mcf_dpf_section_resultants.core import parse_mcf
    except ImportError as exc:  # pragma: no cover - repo layout guard
        raise InputError(
            "Cannot import scripts.mcf_dpf_section_resultants.core.parse_mcf; "
            "run from the EA_Node_Editor repo root so sibling tools resolve"
        ) from exc
    times_list, coord_rows = parse_mcf(str(p))
    times = np.asarray(times_list, dtype=SOLVE_DTYPE)
    # parse_mcf returns one row per time point; modal_coord is (modes, times).
    q = np.asarray(coord_rows, dtype=SOLVE_DTYPE).T
    if q.ndim != 2 or q.shape[1] != times.shape[0]:
        raise InputError(f"Inconsistent .mcf data in {p}: q{q.shape} vs times{times.shape}")
    return ModalCoordinates(q=q, times=times, source="mcf")


def _looks_like_pch(path: Path) -> bool:
    try:
        with open(path, "r", errors="ignore") as handle:
            head = handle.read(4096)
    except OSError:
        return False
    return "$DISPLACEMENTS" in head and "SOLUTION SET" in head


def _parse_pch(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """NASTRAN SOL112 punch parser.

    Ported from MARS ``src/utils/file_utils.py::parse_nastran_pch_modal_coordinates``
    (2026-07): '$DISPLACEMENTS (SOLUTION SET)' sections, '$POINT ID' per mode,
    data rows 'TIME M VALUE...', 'G' (grid) rows skipped.
    """
    mode_data: dict[int, list[tuple[float, float]]] = {}
    current_mode: int | None = None
    in_solution_set = False
    with open(path, "r", errors="ignore") as handle:
        for raw in handle:
            line = raw.rstrip()
            if "$DISPLACEMENTS (SOLUTION SET)" in line:
                in_solution_set = True
                continue
            if line.startswith("$DISPLACEMENTS") and "(SOLUTION SET)" not in line:
                in_solution_set = False
                continue
            if line.startswith("$VELOCITIES") or line.startswith("$ACCELERATIONS"):
                in_solution_set = "(SOLUTION SET)" in line
                continue
            if in_solution_set and "$POINT ID =" in line:
                match = re.search(r"\$POINT ID\s*=\s*(\d+)", line)
                if match:
                    current_mode = int(match.group(1))
                    mode_data.setdefault(current_mode, [])
                continue
            if not in_solution_set or current_mode is None:
                continue
            if line.startswith("$") or line.startswith("-CONT-") or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 3 and parts[1] == "M":
                try:
                    mode_data[current_mode].append((float(parts[0]), float(parts[2])))
                except ValueError:
                    continue
    if not mode_data:
        raise InputError(
            f"No modal coordinates in punch file {path} "
            "(expected SDISPLACEMENT output with '(SOLUTION SET)' marker)"
        )
    mode_ids = sorted(mode_data)
    times = np.asarray([t for t, _ in mode_data[mode_ids[0]]], dtype=SOLVE_DTYPE)
    n_times = times.shape[0]
    q = np.zeros((len(mode_ids), n_times), dtype=SOLVE_DTYPE)
    for row, mode_id in enumerate(mode_ids):
        series = mode_data[mode_id]
        if len(series) != n_times:
            raise InputError(
                f"Mode {mode_id} has {len(series)} time points, expected {n_times} "
                f"(inconsistent punch file {path})"
            )
        q[row, :] = [v for _, v in series]
    return q, times


def _extract_node_ids(df: pd.DataFrame, column: str = "NodeID") -> np.ndarray:
    """Integer-like NodeID coercion (MARS parity)."""
    if column not in df.columns:
        raise InputError(f"Missing required column '{column}'")
    numeric = pd.to_numeric(df[column], errors="coerce")
    if numeric.isna().any():
        bad = df[column][numeric.isna()].astype(str).head(5).tolist()
        raise InputError(f"Invalid NodeID values: {bad}")
    values = numeric.to_numpy(dtype=np.float64)
    rounded = np.rint(values)
    if not np.all(np.isclose(values, rounded, atol=1e-9, rtol=0.0)):
        bad = df[column][~np.isclose(values, rounded, atol=1e-9, rtol=0.0)].astype(str).head(5).tolist()
        raise InputError(f"Non-integer NodeID values: {bad}")
    return rounded.astype(np.int64)


def _columns_containing_prefix(columns, prefixes: tuple[str, ...]) -> dict[str, list[str]]:
    """Contains-match, case-insensitive, preserving file order (MARS parity)."""
    matches: dict[str, list[str]] = {prefix: [] for prefix in prefixes}
    for column in columns:
        lower = str(column).lower()
        for prefix in prefixes:
            if prefix in lower:
                matches[prefix].append(column)
    return matches


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, engine="pyarrow")
    except Exception:
        return pd.read_csv(path)


def load_modal_field(path: str | Path, kind: str = "stress") -> ModalField:
    """Load a MARS-convention modal field CSV.

    Args:
        path: CSV path.
        kind: ``"stress"`` (sx..sxz) or ``"force"`` (enfox..enmoz).
    """
    p = Path(path)
    if not p.is_file():
        raise InputError(f"Modal {kind} CSV not found: {p}")
    if kind == "stress":
        prefixes, components = STRESS_PREFIXES, STRESS_COMPONENTS
    elif kind == "force":
        prefixes, components = FORCE_PREFIXES, FORCE_COMPONENTS
    else:
        raise ValueError(f"kind must be 'stress' or 'force', got {kind!r}")

    df = _read_csv(p)
    df = df.drop_duplicates(subset=["NodeID"], keep="last") if "NodeID" in df.columns else df
    node_ids = _extract_node_ids(df)
    coords = None
    if {"X", "Y", "Z"}.issubset(df.columns):
        coords = df[["X", "Y", "Z"]].to_numpy(dtype=SOLVE_DTYPE)

    matches = _columns_containing_prefix(df.columns, prefixes)
    counts = {prefix: len(cols) for prefix, cols in matches.items()}
    n_modes = counts[prefixes[0]]
    if n_modes == 0:
        raise InputError(
            f"No '{prefixes[0]}*' columns found in {p} — not a modal {kind} CSV?"
        )
    if any(count != n_modes for count in counts.values()):
        raise InputError(f"Unequal per-component mode column counts in {p}: {counts}")

    stacks = [
        df.loc[:, matches[prefix]].to_numpy(dtype=SOLVE_DTYPE, copy=False)
        for prefix in prefixes
    ]
    data = np.stack(stacks, axis=1)  # (n_nodes, n_comp, n_modes)
    return ModalField(node_ids=node_ids, coords=coords, data=data, components=components, source=str(p))


def load_steady_field(path: str | Path) -> SteadyField:
    """Load a steady/bias stress field: NodeID + sx..sxz columns (comma or whitespace)."""
    p = Path(path)
    if not p.is_file():
        raise InputError(f"Steady-state field file not found: {p}")
    try:
        df = pd.read_csv(p)
        if df.shape[1] < 7:
            raise ValueError("too few columns for comma parse")
    except Exception:
        df = pd.read_csv(p, sep=r"\s+")
    lower_map = {str(c).lower(): c for c in df.columns}
    missing = [c for c in ("nodeid", *STRESS_COMPONENTS) if c not in lower_map]
    if missing:
        raise InputError(
            f"Steady field {p} must have columns NodeID, sx..sxz (missing: {missing})"
        )
    node_ids = _extract_node_ids(df.rename(columns={lower_map["nodeid"]: "NodeID"}))
    data = df[[lower_map[c] for c in STRESS_COMPONENTS]].to_numpy(dtype=SOLVE_DTYPE)
    return SteadyField(node_ids=node_ids, data=data)


def check_mode_consistency(field: ModalField, coords: ModalCoordinates, label: str) -> None:
    """Hard error on mode-count mismatch — different-basis inputs are invalid."""
    if field.num_modes != coords.num_modes:
        raise InputError(
            f"Mode-count mismatch: {label} has {field.num_modes} modes but the "
            f"modal coordinates file has {coords.num_modes}. These inputs must "
            "come from the same modal solution."
        )
