# Purpose: Core config, parsing, math, and unit helpers for the MCF DPF section resultants tool.
# Map: subsystems/packaging_generated_assets
# Tests: tests/test_mcf_dpf_section_resultants_gui.py
# Landmarks: SectionConfig; StaticAnimationSession; fit_geometry_following_frame; resolve_static_result_set_ids
"""Shared data, constants, and pure helpers for section resultant extraction."""

from __future__ import annotations

import argparse
import csv
import errno
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

SCRIPT_DESCRIPTION = """Standalone DPF section resultant extractor.

This tool extracts section forces and moments from either:

- a modal ``file.rst`` containing modal nodal force output, and
- a transient MSUP ``file.mcf`` containing modal coordinates, or
- one or more cumulative result sets in a Static Structural ``file.rst``.

It mirrors the Mechanical construction-surface probe convention verified for
this example project, while staying usable as a standalone Slurm post job.
Run without ``--cli`` to open the PyQt GUI, or run with ``--cli`` for batch use.
"""

Vector = List[float]
Matrix3 = List[Vector]
LogFn = Optional[Callable[[str], None]]


NORMAL_AXIS_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("Local Z axis", "z"),
    ("Local X axis", "x"),
    ("Local Y axis", "y"),
)
EXTRACTION_SIDE_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("Positive side (+normal)", "positive"),
    ("Negative side (-normal)", "negative"),
    ("Both sides", "both"),
)
MOMENT_REFERENCE_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("Coordinate system origin", "coordinate_system_origin"),
    ("Mechanical probe mesh centroid", "mechanical_probe_mesh_centroid"),
    ("Selected side node centroid", "selected_side_node_centroid"),
)
MECHANICAL_PROBE_FORCE_TYPE = 1
DPF_FORCE_TYPE_CHOICES: Tuple[Tuple[str, int], ...] = (
    ("Static forces (1, Mechanical probe default)", 1),
    ("Total forces: static + damping + inertia (0)", 0),
    ("Damping forces (2)", 2),
    ("Inertia forces (3)", 3),
)
VISUALIZATION_RESULT_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("Force Reaction", "force"),
    ("Moment Reaction", "moment"),
)
MOMENT_REFERENCE_TOOLTIP = (
    "Moment resultants are computed about this point. Mechanical Moment Reaction "
    "with Local Coord Summation uses the selected coordinate-system origin; "
    "centroid options change the lever arm."
)
COORDINATE_SYSTEM_TOOLTIP = (
    "Select a coordinate system to fill Origin [mm] and Local axis rows. The "
    "axes rotate local result components; they do not choose the moment "
    "reference unless Moment reference is Coordinate system origin."
)
ORIGIN_TOOLTIP = (
    "Origin of the selected coordinate system, entered in millimeters. The "
    "extraction converts this point to the RST mesh unit when needed. It "
    "locates the section plane and becomes the moment summation point only "
    "when Moment reference is Coordinate system origin."
)
NORMAL_AXIS_TOOLTIP = (
    "Local axis used as the section-plane normal. This drives the cut and side "
    "selection; it is separate from the moment reference point."
)
EXTRACTION_SIDE_TOOLTIP = (
    "Side of the cut whose nodes feed DPF force_summation. This changes the "
    "summed forces and the centroid-based moment-reference options."
)
ANALYSIS_MODE_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("MSUP Transient", "modal"),
    ("Static Structural", "static"),
)
STATIC_SET_SCOPE_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("Single", "single"),
    ("Range", "range"),
    ("All", "all"),
)
REFERENCE_FRAME_MOTION_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("Follow geometry (moving section)", "follow-geometry"),
    ("Fixed (Mechanical Construction Surface)", "fixed"),
)
SIDE_TOLERANCE_TOOLTIP = (
    "Geometric tolerance around the section plane, expressed in the RST mesh's "
    "length unit. It controls which elements intersect the plane and which nodes "
    "are included on the selected side. Nodes within +/- tolerance are treated "
    "as lying on the plane. Use a small, non-negative value."
)
DPF_FORCE_TYPE_TOOLTIP = (
    "Force family sent to DPF force_summation. This changes both summed force "
    "and the resulting moment."
)
RESULT_FRAME_TOOLTIP = (
    "Choose the component axes for plotted resultants. Both Global and Local "
    "moment traces use the selected Moment reference point; Global shows global "
    "XYZ components, and Local shows local coordinate-system components. New "
    "results default to Local when the moment reference is not the global origin."
)
VISUALIZATION_RESULT_TOOLTIP = (
    "Force Reaction shows force vectors. Moment Reaction shows the total moment "
    "computed about the selected Moment reference point."
)
VISUALIZATION_LARGE_ELEMENT_COUNT = 50000
VISUALIZATION_LARGE_NODE_COUNT = 200000
VISUALIZATION_PLANE_PADDING_FRACTION = 0.05
VISUALIZATION_NODAL_VECTOR_LENGTH_FRACTION = 0.08
VISUALIZATION_TOTAL_VECTOR_LENGTH_FRACTION = 0.28
VISUALIZATION_TOTAL_VECTOR_PLANE_EXIT_MARGIN = 1.12
VISUALIZATION_TOTAL_VECTOR_MIN_PLANE_LENGTH_FRACTION = 0.18
VISUALIZATION_TOTAL_VECTOR_NORMAL_PLANE_LENGTH_FRACTION = 0.52
VISUALIZATION_PLANE_DEGENERATE_EXTENT_FRACTION = 0.25
VISUALIZATION_PLANE_MIN_ABSOLUTE_EXTENT = 1.0e-6
VISUALIZATION_SCENE_MIN_EXTENT = 1.0e-6
VISUALIZATION_RULER_OFFSET_FRACTION = 0.08
VISUALIZATION_STATIC_RULER_VIEWPORT_Y = 0.14
VISUALIZATION_NODAL_GLYPH_SCALE_ARRAY = "DisplayLength"
VISUALIZATION_TOTAL_FORCE_COLOR = "#005cff"
VISUALIZATION_TOTAL_MOMENT_COLOR = "#c100ff"
VISUALIZATION_DOCK_DEFAULT_WIDTH = 900
VISUALIZATION_DOCK_MIN_WIDTH = 380
VISUALIZATION_DOCK_COLLAPSED_WIDTH = 48
VISUALIZATION_HISTORY_DEFAULT_HEIGHT = 420
VISUALIZATION_HISTORY_MIN_HEIGHT = 170
VISUALIZATION_HISTORY_COLLAPSED_HEIGHT = 34
VISUALIZATION_HISTORY_CANVAS_MIN_HEIGHT = 80
VISUALIZATION_HISTORY_SPLITTER_HANDLE_WIDTH = 10
VISUALIZATION_HISTORY_TOOLBAR_ICON_SIZE = 32
COORDINATE_SYSTEM_ID_SCAN_LIMIT = 250
GUI_ORIGIN_UNIT = "mm"
DEFAULT_MODAL_SUMMATION_BATCH_SIZE = 25
MANUAL_COORDINATE_SYSTEM_LABEL = "Manual / custom coordinates from fields"
ANSYS_2022R2_RELEASE_CODE = 222
ANSYS_2023R2_RELEASE_CODE = 232
PYDPF_CORE_2023R2_MAX_VERSION = (0, 16, 0)
PYDPF_CORE_2023R2_INSTALL_COMMAND = (
    '.\\venv\\Scripts\\python.exe -m pip install "ansys-dpf-core<0.16.0"'
)
MOMENT_DISPLAY_UNIT_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("Source", "source"),
    ("N mm", "N mm"),
    ("N m", "N m"),
    ("kN mm", "kN mm"),
    ("kN m", "kN m"),
    ("lbf in", "lbf in"),
    ("lbf ft", "lbf ft"),
)
_FORCE_UNIT_TO_N = {
    "n": 1.0,
    "newton": 1.0,
    "newtons": 1.0,
    "kn": 1.0e3,
    "mn": 1.0e6,
    "lbf": 4.4482216152605,
    "lb": 4.4482216152605,
    "kip": 4448.2216152605,
    "kips": 4448.2216152605,
}
_LENGTH_UNIT_TO_M = {
    "mm": 1.0e-3,
    "millimeter": 1.0e-3,
    "millimeters": 1.0e-3,
    "cm": 1.0e-2,
    "centimeter": 1.0e-2,
    "centimeters": 1.0e-2,
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "in": 0.0254,
    "inch": 0.0254,
    "inches": 0.0254,
    "ft": 0.3048,
    "foot": 0.3048,
    "feet": 0.3048,
}


RstMetadataCacheKey = Tuple[str, int, int]
VisualizationMeshSnapshotCacheKey = Tuple[Any, ...]

STATIC_ANIMATION_MAX_BATCH_SETS = 16
STATIC_ANIMATION_MAX_BATCH_BYTES = 64 * 1024 * 1024
STATIC_ANIMATION_RAM_LIMIT_BYTES = 256 * 1024 * 1024
STATIC_ANIMATION_MAX_DECODED_FRAMES = 3


@dataclass(frozen=True)
class ModalRstSignature:
    path: str
    size_bytes: int
    mtime_ns: int


@dataclass
class ModalRstMetadata:
    signature: ModalRstSignature
    named_selection_names: List[str]
    modal_set_count: int
    result_names: List[str]
    mesh_unit: Optional[str]
    coordinate_system_options: List[Dict[str, Any]]
    caerep_coordinate_systems: Dict[int, Dict[str, Any]]
    ds_dat_apdl_names: Dict[int, str]
    scanned_coordinate_system_options: Optional[List[Dict[str, Any]]] = None
    result_sets: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class VisualizationMeshSnapshot:
    key: VisualizationMeshSnapshotCacheKey
    element_name: str
    available_named_selections: List[str]
    mesh_unit: Optional[str]
    element_ids: List[int]
    element_node_ids: Dict[int, List[int]]
    node_ids: List[int]
    node_coordinates: Dict[int, Vector]
    grid_payload: Dict[str, Any]
    nodal_displacements: Dict[int, Vector] = field(default_factory=dict)
    deformation: Optional[Dict[str, Any]] = None
    resolved_reference_frame: Optional[Dict[str, Any]] = None


@dataclass
class ResolvedReferenceFrame:
    result_set_id: int
    result_value: Optional[float]
    result_unit: Optional[str]
    motion: str
    attachment_source: str
    attachment_selection: str
    tracking_node_count: int
    tracking_node_ids_hash: str
    tracking_node_ids: List[int]
    initial_origin: Vector
    initial_axes: Dict[str, Vector]
    reference_centroid: Vector
    current_centroid: Vector
    resolved_origin: Vector
    resolved_axes: Dict[str, Vector]
    rotation_matrix: Matrix3
    translation: Vector
    singular_values: Vector
    rank: int
    raw_determinant: float
    final_determinant: float
    orthogonality_error: float
    tracking_span: float
    residual_rms: float
    residual_max: float
    normalized_residual: float
    worst_node_id: Optional[int]
    reflection_corrected: bool
    warnings: List[str] = field(default_factory=list)


@dataclass
class StaticSetResult:
    result_set_id: int
    result_value: float
    result_unit: Optional[str]
    reference_frame: Dict[str, Any]
    moment_reference_xyz: Vector
    resultant_global_origin: List[float]
    resultant_reference_global: List[float]
    resultant_local: List[float]
    raw_dpf_resultant_global_origin: List[float]
    raw_dpf_resultant_reference_global: List[float]
    raw_dpf_resultant_local: List[float]
    scope: Dict[str, Any]
    section_geometry: Dict[str, Any]
    deformation: Dict[str, Any]
    nodal_parity: Dict[str, Any]
    visualization_signature: Dict[str, Any]
    timings: Dict[str, float]
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class StaticAnimationSessionSignature:
    """Inputs that make a streamed static-animation session reusable."""

    rst: Tuple[str, int, int]
    external_selection: Tuple[str, int, int]
    result_set_ids: Tuple[int, ...]
    element_named_selection: str
    coordinate_system_origin: Tuple[float, float, float]
    coordinate_system_axes: Tuple[Tuple[float, float, float], ...]
    reference_frame_motion: str
    reference_frame_attachment_selection: str
    section_normal_axis: str
    extraction_side: str
    side_filter_tolerance: float
    moment_reference_mode: str


@dataclass(frozen=True)
class StaticAnimationTopology:
    """Reference topology shared by every frame in one animation session."""

    node_ids: Tuple[int, ...]
    displacement_node_ids: Tuple[int, ...]
    reference_points: Any
    displacement_reference_points: Any
    cells: Any
    celltypes: Any
    element_ids: Tuple[int, ...]
    element_node_ids: Dict[int, Tuple[int, ...]]
    connectivity_point_indices: Any
    element_offsets: Any
    mesh_displacement_indices: Any
    tracking_node_ids: Tuple[int, ...]
    tracking_displacement_indices: Any
    element_name: str
    available_named_selections: Tuple[str, ...]
    mesh_unit: Optional[str]
    mesh_config: Dict[str, Any]
    origin_unit_conversion: Optional[Dict[str, Any]]
    attachment: Dict[str, Any]


@dataclass
class StaticAnimationSetRecord:
    result_set_id: int
    result_value: float
    result_unit: Optional[str]
    store_index: int
    deformation: Dict[str, Any] = field(default_factory=dict)
    resolved_reference_frame: Optional[Dict[str, Any]] = None
    primary_result_global_origin: Optional[List[float]] = None
    primary_result_reference_global: Optional[List[float]] = None
    moment_reference_xyz: Optional[Vector] = None


@dataclass(frozen=True)
class StaticAnimationInterpolation:
    lower_index: int
    upper_index: int
    fraction: float
    progress: float
    axis_value: float
    exact: bool
    warning: Optional[str] = None


class StaticAnimationSession:
    """Thread-safe raw displacement store with a three-frame decoded view cache."""

    def __init__(
        self,
        signature: StaticAnimationSessionSignature,
        topology: StaticAnimationTopology,
        selected_result_sets: Sequence[Dict[str, Any]],
        *,
        generation: int = 0,
        ram_limit_bytes: int = STATIC_ANIMATION_RAM_LIMIT_BYTES,
    ) -> None:
        import numpy as np

        self.signature = signature
        self.topology = topology
        self.generation = int(generation)
        self.records = [
            StaticAnimationSetRecord(
                result_set_id=int(item["id"]),
                result_value=float(item.get("value", index)),
                result_unit=(str(item.get("unit")) if item.get("unit") else None),
                store_index=index,
            )
            for index, item in enumerate(selected_result_sets)
        ]
        shape = (len(self.records), len(topology.displacement_node_ids), 3)
        self.store_bytes = int(np.prod(shape, dtype=np.int64)) * 8
        self.memmap_path: Optional[str] = None
        if self.store_bytes <= int(ram_limit_bytes):
            self._store = np.empty(shape, dtype=np.float64, order="C")
            self.storage_kind = "ram"
        else:
            handle = tempfile.NamedTemporaryFile(
                prefix="mcf_dpf_animation_",
                suffix=".float64",
                delete=False,
            )
            handle.close()
            self.memmap_path = handle.name
            self._store = np.memmap(
                self.memmap_path,
                dtype=np.float64,
                mode="w+",
                shape=shape,
                order="C",
            )
            self.storage_kind = "memmap"
        self._loaded = np.zeros(len(self.records), dtype=bool)
        self._decoded_frames: "OrderedDict[int, Any]" = OrderedDict()
        self._lock = RLock()
        self.cancelled = False
        self.complete = False
        self.closed = False
        self.warnings: List[str] = []

    @property
    def loaded_count(self) -> int:
        with self._lock:
            return int(self._loaded.sum())

    @property
    def decoded_frame_count(self) -> int:
        with self._lock:
            return len(self._decoded_frames)

    def is_loaded(self, index: int) -> bool:
        with self._lock:
            return bool(self._loaded[int(index)])

    def loaded_indices(self) -> List[int]:
        import numpy as np

        with self._lock:
            return [int(value) for value in np.flatnonzero(self._loaded)]

    def put_displacements(
        self,
        index: int,
        values: Any,
        *,
        deformation: Optional[Dict[str, Any]] = None,
        resolved_reference_frame: Optional[Dict[str, Any]] = None,
    ) -> None:
        import numpy as np

        frame_index = int(index)
        array = np.asarray(values, dtype=np.float64)
        expected = (len(self.topology.displacement_node_ids), 3)
        if array.shape != expected:
            raise ValueError(
                f"Animation displacement frame has shape {array.shape}; expected {expected}."
            )
        if not np.isfinite(array).all():
            raise ValueError("Animation displacement frame contains non-finite values.")
        with self._lock:
            if self.closed:
                raise RuntimeError("Animation session is closed.")
            self._store[frame_index, :, :] = array
            if hasattr(self._store, "flush"):
                self._store.flush()
            self._loaded[frame_index] = True
            record = self.records[frame_index]
            record.deformation = dict(deformation or {})
            record.resolved_reference_frame = (
                dict(resolved_reference_frame)
                if resolved_reference_frame is not None
                else None
            )
            self._decoded_frames.pop(frame_index, None)

    def put_displacement_mapping(
        self,
        index: int,
        displacements: Dict[int, Sequence[float]],
        **metadata: Any,
    ) -> None:
        import numpy as np

        missing = [
            node_id
            for node_id in self.topology.displacement_node_ids
            if node_id not in displacements
        ]
        if missing:
            raise ValueError(
                "Animation displacement mapping is missing "
                f"{len(missing)} node(s): {missing[:10]}."
            )
        values = np.asarray(
            [displacements[node_id][:3] for node_id in self.topology.displacement_node_ids],
            dtype=np.float64,
        )
        self.put_displacements(index, values, **metadata)

    def displacement_frame(self, index: int) -> Any:
        import numpy as np

        frame_index = int(index)
        with self._lock:
            if self.closed:
                raise RuntimeError("Animation session is closed.")
            if not self._loaded[frame_index]:
                raise KeyError(f"Animation frame {frame_index} is not loaded.")
            cached = self._decoded_frames.pop(frame_index, None)
            if cached is None:
                cached = np.array(self._store[frame_index], dtype=np.float64, copy=True)
                cached.setflags(write=False)
            self._decoded_frames[frame_index] = cached
            while len(self._decoded_frames) > STATIC_ANIMATION_MAX_DECODED_FRAMES:
                self._decoded_frames.popitem(last=False)
            return cached

    def mark_complete(self) -> None:
        with self._lock:
            self.complete = self.loaded_count == len(self.records)

    def close(self) -> None:
        with self._lock:
            if self.closed:
                return
            self.closed = True
            self._decoded_frames.clear()
            store = self._store
            self._store = None
            if hasattr(store, "flush"):
                try:
                    store.flush()
                except Exception:
                    pass
            mmap = getattr(store, "_mmap", None)
            if mmap is not None:
                try:
                    mmap.close()
                except Exception:
                    pass
            path = self.memmap_path
            self.memmap_path = None
        if path:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass

    def __enter__(self) -> "StaticAnimationSession":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


_MODAL_RST_METADATA_CACHE: Dict[RstMetadataCacheKey, ModalRstMetadata] = {}
_VISUALIZATION_MESH_SNAPSHOT_CACHE: Dict[
    VisualizationMeshSnapshotCacheKey,
    VisualizationMeshSnapshot,
] = {}


class DpfCompatibilityError(RuntimeError):
    """Raised before DPF starts when the local client/runtime pairing is invalid."""



@dataclass
class SectionConfig:
    analysis_mode: str = "modal"
    static_set_scope: str = "single"
    result_set_id: Optional[int] = None
    result_set_range_start: Optional[int] = None
    result_set_range_end: Optional[int] = None
    result_set_range_stride: int = 1
    modal_rst: str = ""
    mcf: str = ""
    out_csv: str = ""
    external_named_selection_path: str = ""
    element_named_selection: str = "DENEME"
    coordinate_system_origin: Vector = field(default_factory=lambda: [51.0, 0.0, 0.0])
    coordinate_system_axes: Dict[str, Vector] = field(
        default_factory=lambda: {
            "x": [0.0, 0.0, -1.0],
            "y": [0.0, 1.0, 0.0],
            "z": [1.0, 0.0, 0.0],
        }
    )
    reference_frame_motion: str = "follow-geometry"
    reference_frame_attachment_selection: str = ""
    reference_frame_fit_warning_ratio: float = 0.01
    section_normal_axis: str = "z"
    extraction_side: str = "positive"
    side_filter_tolerance: float = 1.0e-8
    moment_reference_mode: str = "coordinate_system_origin"
    force_type: int = MECHANICAL_PROBE_FORCE_TYPE
    modal_summation_batch_size: int = DEFAULT_MODAL_SUMMATION_BATCH_SIZE
    skip_first_modes: int = 0


def default_summary_path(out_csv: str) -> str:
    path = Path(out_csv)
    if path.suffix:
        return str(path.with_name(path.stem + "_summary.json"))
    return str(path.with_name(path.name + "_summary.json"))


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def emit(log: LogFn, message: str) -> None:
    if log:
        log(f"[{timestamp()}] {message}")


def format_seconds(seconds: float) -> str:
    return f"{float(seconds):.3f} s"


def format_bytes(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:.1f} GB"


def preview_items(items: Sequence[Any], limit: int = 6) -> str:
    values = [str(item) for item in list(items)[:limit]]
    if len(items) > limit:
        values.append("...")
    return ", ".join(values) if values else "none"


def force_type_label(force_type: Any) -> str:
    try:
        normalized = int(force_type)
    except Exception:
        normalized = force_type
    for label, value in DPF_FORCE_TYPE_CHOICES:
        if value == normalized:
            return label
    return f"Unknown force type ({force_type})"


class MissingElementNodalForceDataError(RuntimeError):
    """Raised when an RST cannot support exact section-resultant extraction."""


def has_element_nodal_force_result(result_names: Sequence[str]) -> bool:
    aliases = {
        "element_nodal_force",
        "element_nodal_forces",
        "elemental_nodal_force",
        "elemental_nodal_forces",
    }
    return any(
        re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_") in aliases
        for name in result_names
    )


def require_element_nodal_force_result(
    *,
    rst_path: str,
    result_names: Sequence[str],
) -> None:
    """Reject RSTs that definitively lack the force records used by FSUM/NFORCE."""

    if not result_names or has_element_nodal_force_result(result_names):
        return
    raise MissingElementNodalForceDataError(
        "Exact section force/moment extraction is unavailable for this RST because "
        "DPF metadata does not report elemental-nodal force data "
        "(element_nodal_forces).\n\n"
        "This data must be written during the solve; changing the PyDPF version cannot "
        "recreate it. In Ansys Mechanical, set Analysis Settings > Output Controls > "
        "Nodal Forces to Yes, then re-solve the analysis. The solver-command equivalent "
        "is OUTRES,NLOAD,ALL.\n\n"
        "Reaction-force output is not a valid replacement for an arbitrary internal "
        "section. The extractor will not substitute an approximate result for the exact "
        "FSUM/NFORCE-style resultant.\n\n"
        f"RST: {rst_path}\n"
        "Available result names reported by DPF metadata: "
        f"{preview_items(result_names, limit=12)}."
    )


def build_force_summation_failure_message(
    *,
    config: SectionConfig,
    result_names: Sequence[str],
    raw_element_count: int,
    cut_element_count: int,
    side_node_count: int,
    modes_to_evaluate: int,
    raw_error: BaseException,
) -> str:
    result_text = preview_items(result_names, limit=12)
    raw_error_text = str(raw_error).strip() or repr(raw_error)
    static_mode = config.analysis_mode == "static"
    analysis_label = "Static Structural RST" if static_mode else "modal RST"
    set_label = "result sets" if static_mode else "modal sets"
    force_type = MECHANICAL_PROBE_FORCE_TYPE if static_mode else config.force_type
    return (
        "DPF force_summation could not produce force/moment fields for this RST.\n\n"
        f"This usually means the {analysis_label} does not contain the elemental-nodal "
        "force data required for FSUM/NFORCE-style section resultants. In "
        "Mechanical/APDL, check that the solve writes nodal force output "
        "to the result file, typically with OUTRES,NLOAD.\n\n"
        "Other checks:\n"
        f"- Requested force type: {force_type_label(force_type)}.\n"
        "- If damping, inertia, or total forces were selected, confirm that this "
        "analysis/result file stores those force contributions.\n"
        f"- Named selection: {config.element_named_selection!r}; raw elements="
        f"{raw_element_count}, cut elements={cut_element_count}, side nodes="
        f"{side_node_count}, {set_label} requested={modes_to_evaluate}.\n"
        "- Confirm the named selection is elemental and intersects the section "
        "side being extracted.\n"
        f"- Available result names reported by DPF metadata: {result_text}.\n\n"
        f"Raw DPF error: {raw_error_text}"
    )

def load_config(
    path: str,
    *,
    include_modal_rst: bool = True,
    current_modal_rst: str = "",
) -> SectionConfig:
    with open(path, "r", encoding="utf-8") as stream:
        raw = json.load(stream)
    cfg = config_from_mapping(raw)
    if not include_modal_rst:
        cfg.modal_rst = str(current_modal_rst or "")
    return cfg


def save_config(path: str, config: SectionConfig) -> None:
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(asdict(config), stream, indent=2, sort_keys=True)
        stream.write("\n")

def config_from_mapping(raw: Dict[str, Any]) -> SectionConfig:
    cfg = SectionConfig()
    for key, value in raw.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    cfg.modal_rst = str(cfg.modal_rst or "")
    cfg.mcf = str(cfg.mcf or "")
    cfg.out_csv = str(cfg.out_csv or "")
    cfg.external_named_selection_path = str(cfg.external_named_selection_path or "")
    cfg.analysis_mode = str(cfg.analysis_mode or "modal").strip().lower()
    if cfg.analysis_mode not in {"modal", "static"}:
        raise ValueError(f"Unsupported analysis_mode: {cfg.analysis_mode!r}.")
    cfg.result_set_id = (
        int(cfg.result_set_id) if cfg.result_set_id not in (None, "") else None
    )
    cfg.static_set_scope = str(cfg.static_set_scope or "single").strip().lower()
    if cfg.static_set_scope not in {"single", "range", "all"}:
        raise ValueError(f"Unsupported static_set_scope: {cfg.static_set_scope!r}.")
    cfg.result_set_range_start = (
        int(cfg.result_set_range_start)
        if cfg.result_set_range_start not in (None, "")
        else None
    )
    cfg.result_set_range_end = (
        int(cfg.result_set_range_end)
        if cfg.result_set_range_end not in (None, "")
        else None
    )
    cfg.result_set_range_stride = int(cfg.result_set_range_stride or 1)
    if cfg.result_set_range_stride < 1:
        raise ValueError("result_set_range_stride must be at least 1.")
    cfg.coordinate_system_origin = vector3(cfg.coordinate_system_origin, "coordinate_system_origin")
    axes = cfg.coordinate_system_axes or {}
    cfg.coordinate_system_axes = {
        "x": vector3(axes.get("x", [1.0, 0.0, 0.0]), "coordinate_system_axes.x"),
        "y": vector3(axes.get("y", [0.0, 1.0, 0.0]), "coordinate_system_axes.y"),
        "z": vector3(axes.get("z", [0.0, 0.0, 1.0]), "coordinate_system_axes.z"),
    }
    cfg.reference_frame_motion = str(
        cfg.reference_frame_motion or "follow-geometry"
    ).strip().lower().replace("_", "-")
    if cfg.reference_frame_motion not in {"fixed", "follow-geometry"}:
        raise ValueError(
            f"Unsupported reference_frame_motion: {cfg.reference_frame_motion!r}."
        )
    cfg.reference_frame_attachment_selection = str(
        cfg.reference_frame_attachment_selection or ""
    ).strip()
    cfg.reference_frame_fit_warning_ratio = float(
        cfg.reference_frame_fit_warning_ratio
    )
    if cfg.reference_frame_fit_warning_ratio < 0.0:
        raise ValueError("reference_frame_fit_warning_ratio must be non-negative.")
    cfg.section_normal_axis = str(cfg.section_normal_axis or "z").lower()
    cfg.extraction_side = str(cfg.extraction_side or "positive").lower()
    cfg.moment_reference_mode = str(
        cfg.moment_reference_mode or "coordinate_system_origin"
    )
    cfg.side_filter_tolerance = float(cfg.side_filter_tolerance)
    cfg.force_type = int(cfg.force_type)
    if cfg.analysis_mode == "static":
        cfg.force_type = MECHANICAL_PROBE_FORCE_TYPE
    cfg.modal_summation_batch_size = max(
        1,
        int(cfg.modal_summation_batch_size or DEFAULT_MODAL_SUMMATION_BATCH_SIZE),
    )
    cfg.skip_first_modes = max(0, int(cfg.skip_first_modes or 0))
    return cfg


def vector3(value: Any, name: str) -> Vector:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must be a 3-number list.")
    return [float(value[0]), float(value[1]), float(value[2])]


def normalize(values: Sequence[float], name: str) -> Vector:
    length = math.sqrt(sum(float(value) * float(value) for value in values))
    if length <= 0.0:
        raise ValueError(f"{name} is a zero-length axis.")
    return [float(value) / length for value in values]


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def cross(a: Sequence[float], b: Sequence[float]) -> Vector:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def moment_about_reference_point(
    moment_about_global_origin: Sequence[float],
    reference_xyz: Sequence[float],
    force: Sequence[float],
    *,
    cross_product_moment_factor: float = 1.0,
) -> Vector:
    return shift_moment_reference(
        moment_about_global_origin,
        [0.0, 0.0, 0.0],
        reference_xyz,
        force,
        cross_product_moment_factor=cross_product_moment_factor,
    )


def shift_moment_reference(
    moment_about_from_reference: Sequence[float],
    from_reference_xyz: Sequence[float],
    to_reference_xyz: Sequence[float],
    force: Sequence[float],
    *,
    cross_product_moment_factor: float = 1.0,
) -> Vector:
    reference_delta = [
        float(from_reference_xyz[index]) - float(to_reference_xyz[index])
        for index in range(3)
    ]
    delta_cross_force = scale_vector(
        cross(reference_delta, force),
        cross_product_moment_factor,
    )
    return [
        float(moment_about_from_reference[index]) + delta_cross_force[index]
        for index in range(3)
    ]


def resultant_about_reference(
    global_origin_row: Sequence[float],
    reference_xyz: Sequence[float],
    *,
    cross_product_moment_factor: float = 1.0,
) -> List[float]:
    force = [float(value) for value in global_origin_row[:3]]
    moment = moment_about_reference_point(
        global_origin_row[3:6],
        reference_xyz,
        force,
        cross_product_moment_factor=cross_product_moment_factor,
    )
    return force + moment


def add_vectors(a: Sequence[float], b: Sequence[float]) -> Vector:
    return [float(a[index]) + float(b[index]) for index in range(3)]


def scale_vector(values: Sequence[float], scale: float) -> Vector:
    return [float(value) * float(scale) for value in values[:3]]


def vector_magnitude(values: Sequence[float]) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in values[:3]))


def centroid(points: Sequence[Sequence[float]]) -> Vector:
    if not points:
        raise ValueError("Cannot calculate centroid of an empty point set.")
    return [
        sum(float(point[index]) for point in points) / float(len(points))
        for index in range(3)
    ]


def resolve_static_result_set_ids(
    config: SectionConfig,
    result_sets: Sequence[Dict[str, Any]],
) -> List[int]:
    available_ids = [int(item.get("id", 0)) for item in result_sets]
    available_set = set(available_ids)
    if not available_ids:
        raise ValueError("The Static Structural RST reports no cumulative result sets.")
    scope = str(config.static_set_scope or "single").lower()
    if scope == "single":
        if config.result_set_id is None:
            raise ValueError("Static set scope Single requires a result-set ID.")
        selected = [int(config.result_set_id)]
    elif scope == "range":
        if config.result_set_range_start is None or config.result_set_range_end is None:
            raise ValueError("Static set scope Range requires both Start set and End set.")
        start = int(config.result_set_range_start)
        end = int(config.result_set_range_end)
        stride = int(config.result_set_range_stride)
        if start > end:
            raise ValueError("Static result-set range start must not exceed its end.")
        if stride < 1:
            raise ValueError("Static result-set range stride must be at least 1.")
        selected = list(range(start, end + 1, stride))
    elif scope == "all":
        selected = list(available_ids)
    else:
        raise ValueError(f"Unsupported static_set_scope: {scope!r}.")
    unavailable = [set_id for set_id in selected if set_id not in available_set]
    if unavailable:
        if len(unavailable) == 1:
            raise ValueError(
                f"Static result-set ID {unavailable[0]} is unavailable; "
                f"choose from {available_ids}."
            )
        raise ValueError(
            f"Static result-set ID(s) {unavailable} are unavailable; "
            f"choose from {available_ids}."
        )
    return selected


def stable_id_hash(ids: Sequence[int]) -> str:
    payload = ",".join(str(int(value)) for value in sorted(set(ids)))
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def fit_geometry_following_frame(
    reference_coordinates: Any,
    current_coordinates: Any,
    initial_origin: Sequence[float],
    initial_axes: Dict[str, Sequence[float]],
    *,
    result_set_id: int,
    result_value: Optional[float] = None,
    result_unit: Optional[str] = None,
    attachment_source: str = "local_section_cut_neighborhood",
    attachment_selection: str = "",
    warning_ratio: float = 0.01,
    tracking_node_ids: Optional[Sequence[int]] = None,
) -> ResolvedReferenceFrame:
    import numpy as np

    array_input = isinstance(reference_coordinates, np.ndarray) or isinstance(
        current_coordinates, np.ndarray
    )
    if array_input:
        reference = np.asarray(reference_coordinates, dtype=float)
        current = np.asarray(current_coordinates, dtype=float)
        node_ids = (
            [int(value) for value in tracking_node_ids]
            if tracking_node_ids is not None
            else list(range(len(reference)))
        )
    else:
        node_ids = sorted(set(int(value) for value in reference_coordinates))
        missing = [node_id for node_id in node_ids if node_id not in current_coordinates]
        if missing:
            raise ValueError(
                f"Following-frame coordinates are missing {len(missing)} tracking node(s): "
                f"{missing[:10]}."
            )
        reference = np.asarray(
            [
                [float(value) for value in reference_coordinates[node_id][:3]]
                for node_id in node_ids
            ],
            dtype=float,
        )
        current = np.asarray(
            [
                [float(value) for value in current_coordinates[node_id][:3]]
                for node_id in node_ids
            ],
            dtype=float,
        )
    if len(node_ids) < 3:
        raise ValueError(
            "Follow geometry requires at least 3 usable tracking nodes; "
            f"received {len(node_ids)}."
        )
    if len(node_ids) != len(reference):
        raise ValueError(
            "Following-frame tracking node IDs must align one-to-one with XYZ rows; "
            f"received {len(node_ids)} IDs and {len(reference)} rows."
        )
    if reference.shape != current.shape or reference.shape[1:] != (3,):
        raise ValueError("Following-frame tracking coordinates must be finite XYZ rows.")
    if not np.isfinite(reference).all() or not np.isfinite(current).all():
        raise ValueError("Following-frame tracking coordinates contain non-finite values.")

    reference_centroid = reference.mean(axis=0)
    current_centroid = current.mean(axis=0)
    centered_reference = reference - reference_centroid
    centered_current = current - current_centroid
    covariance = centered_reference.T @ centered_current
    left, singular_values, right_t = np.linalg.svd(covariance)
    leading = float(singular_values[0]) if len(singular_values) else 0.0
    rank_tolerance = max(leading * 1.0e-8, np.finfo(float).eps)
    rank = int(np.count_nonzero(singular_values > rank_tolerance))
    if rank < 2:
        raise ValueError(
            "Follow geometry tracking nodes are degenerate or collinear; "
            f"centered-coordinate rank={rank}, singular_values={singular_values.tolist()}."
        )

    rotation = right_t.T @ left.T
    raw_determinant = float(np.linalg.det(rotation))
    reflection_corrected = raw_determinant < 0.0
    if reflection_corrected:
        right_t[-1, :] *= -1.0
        rotation = right_t.T @ left.T
    final_determinant = float(np.linalg.det(rotation))
    if final_determinant <= 0.0:
        raise ValueError(
            "Following-frame rigid fit did not produce a proper right-handed rotation."
        )
    translation = current_centroid - rotation @ reference_centroid
    fitted = (rotation @ reference.T).T + translation
    residual_magnitudes = np.linalg.norm(current - fitted, axis=1)
    residual_rms = float(np.sqrt(np.mean(residual_magnitudes**2)))
    worst_index = int(np.argmax(residual_magnitudes))
    residual_max = float(residual_magnitudes[worst_index])
    span = float(np.linalg.norm(np.ptp(reference, axis=0)))
    if not math.isfinite(span) or span <= np.finfo(float).eps:
        raise ValueError("Follow geometry tracking span is zero or non-finite.")
    normalized_residual = residual_rms / span

    origin = np.asarray([float(value) for value in initial_origin[:3]], dtype=float)
    normalized_axes = validate_axes(
        {key: initial_axes[key] for key in ("x", "y", "z")}
    )
    resolved_origin = rotation @ origin + translation
    resolved_axes = {
        key: [float(value) for value in rotation @ np.asarray(axis, dtype=float)]
        for key, axis in zip(("x", "y", "z"), normalized_axes)
    }
    orthogonality_error = float(
        np.linalg.norm(rotation.T @ rotation - np.eye(3), ord="fro")
    )
    warnings: List[str] = []
    if normalized_residual > float(warning_ratio):
        warnings.append(
            "Following-frame rigid-fit residual exceeds the warning limit: "
            f"RMS/span={normalized_residual:.6g}, limit={float(warning_ratio):.6g}."
        )
    return ResolvedReferenceFrame(
        result_set_id=int(result_set_id),
        result_value=float(result_value) if result_value is not None else None,
        result_unit=str(result_unit) if result_unit else None,
        motion="follow-geometry",
        attachment_source=str(attachment_source),
        attachment_selection=str(attachment_selection or ""),
        tracking_node_count=len(node_ids),
        tracking_node_ids_hash=stable_id_hash(node_ids),
        tracking_node_ids=node_ids,
        initial_origin=[float(value) for value in origin],
        initial_axes={
            key: [float(value) for value in axis]
            for key, axis in zip(("x", "y", "z"), normalized_axes)
        },
        reference_centroid=[float(value) for value in reference_centroid],
        current_centroid=[float(value) for value in current_centroid],
        resolved_origin=[float(value) for value in resolved_origin],
        resolved_axes=resolved_axes,
        rotation_matrix=[
            [float(value) for value in row]
            for row in rotation.tolist()
        ],
        translation=[float(value) for value in translation],
        singular_values=[float(value) for value in singular_values],
        rank=rank,
        raw_determinant=raw_determinant,
        final_determinant=final_determinant,
        orthogonality_error=orthogonality_error,
        tracking_span=span,
        residual_rms=residual_rms,
        residual_max=residual_max,
        normalized_residual=normalized_residual,
        worst_node_id=node_ids[worst_index],
        reflection_corrected=reflection_corrected,
        warnings=warnings,
    )


def fixed_reference_frame(
    origin: Sequence[float],
    axes: Dict[str, Sequence[float]],
    *,
    result_set_id: int,
    result_value: Optional[float] = None,
    result_unit: Optional[str] = None,
) -> ResolvedReferenceFrame:
    normalized_axes = validate_axes({key: axes[key] for key in ("x", "y", "z")})
    axes_mapping = {
        key: [float(value) for value in axis]
        for key, axis in zip(("x", "y", "z"), normalized_axes)
    }
    origin_values = [float(value) for value in origin[:3]]
    return ResolvedReferenceFrame(
        result_set_id=int(result_set_id),
        result_value=float(result_value) if result_value is not None else None,
        result_unit=str(result_unit) if result_unit else None,
        motion="fixed",
        attachment_source="none",
        attachment_selection="",
        tracking_node_count=0,
        tracking_node_ids_hash=stable_id_hash([]),
        tracking_node_ids=[],
        initial_origin=origin_values,
        initial_axes=axes_mapping,
        reference_centroid=[0.0, 0.0, 0.0],
        current_centroid=[0.0, 0.0, 0.0],
        resolved_origin=list(origin_values),
        resolved_axes={key: list(value) for key, value in axes_mapping.items()},
        rotation_matrix=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        translation=[0.0, 0.0, 0.0],
        singular_values=[0.0, 0.0, 0.0],
        rank=3,
        raw_determinant=1.0,
        final_determinant=1.0,
        orthogonality_error=0.0,
        tracking_span=0.0,
        residual_rms=0.0,
        residual_max=0.0,
        normalized_residual=0.0,
        worst_node_id=None,
        reflection_corrected=False,
        warnings=[],
    )


def rebase_reference_frame(
    frame: Any,
    initial_origin: Sequence[float],
    initial_axes: Dict[str, Sequence[float]],
    *,
    warning_ratio: float,
) -> ResolvedReferenceFrame:
    """Apply cached rigid-motion evidence to a currently edited local frame."""

    import numpy as np

    data = asdict(frame) if isinstance(frame, ResolvedReferenceFrame) else dict(frame)
    motion = str(data.get("motion") or "").strip().lower()
    if motion == "fixed":
        return fixed_reference_frame(
            initial_origin,
            initial_axes,
            result_set_id=int(data["result_set_id"]),
            result_value=data.get("result_value"),
            result_unit=data.get("result_unit"),
        )
    if motion != "follow-geometry":
        raise ValueError(f"Unsupported resolved reference-frame motion: {motion!r}.")

    origin = np.asarray([float(value) for value in initial_origin[:3]], dtype=float)
    normalized_axes = validate_axes(
        {key: initial_axes[key] for key in ("x", "y", "z")}
    )
    rotation = np.asarray(data.get("rotation_matrix"), dtype=float)
    translation = np.asarray(data.get("translation"), dtype=float)
    if origin.shape != (3,) or rotation.shape != (3, 3) or translation.shape != (3,):
        raise ValueError("Resolved reference-frame transform must contain finite 3D data.")
    if not (
        np.isfinite(origin).all()
        and np.isfinite(rotation).all()
        and np.isfinite(translation).all()
    ):
        raise ValueError("Resolved reference-frame transform contains non-finite values.")

    threshold = float(warning_ratio)
    if threshold < 0.0:
        raise ValueError("reference_frame_fit_warning_ratio must be non-negative.")
    normalized_residual = float(data.get("normalized_residual") or 0.0)
    warnings: List[str] = []
    if normalized_residual > threshold:
        warnings.append(
            "Following-frame rigid-fit residual exceeds the warning limit: "
            f"RMS/span={normalized_residual:.6g}, limit={threshold:.6g}."
        )

    rebased = dict(data)
    rebased.update(
        initial_origin=[float(value) for value in origin],
        initial_axes={
            key: [float(value) for value in axis]
            for key, axis in zip(("x", "y", "z"), normalized_axes)
        },
        resolved_origin=[float(value) for value in rotation @ origin + translation],
        resolved_axes={
            key: [float(value) for value in rotation @ np.asarray(axis, dtype=float)]
            for key, axis in zip(("x", "y", "z"), normalized_axes)
        },
        warnings=warnings,
    )
    return ResolvedReferenceFrame(**rebased)


def validate_axes(raw_axes: Dict[str, Sequence[float]]) -> Matrix3:
    axes = [
        normalize(raw_axes["x"], "coordinate_system_axes.x"),
        normalize(raw_axes["y"], "coordinate_system_axes.y"),
        normalize(raw_axes["z"], "coordinate_system_axes.z"),
    ]
    determinant = (
        axes[0][0] * (axes[1][1] * axes[2][2] - axes[1][2] * axes[2][1])
        - axes[0][1] * (axes[1][0] * axes[2][2] - axes[1][2] * axes[2][0])
        + axes[0][2] * (axes[1][0] * axes[2][1] - axes[1][1] * axes[2][0])
    )
    if abs(determinant - 1.0) > 1.0e-5:
        raise ValueError(
            "Coordinate-system axes must form an orthonormal, right-handed frame; "
            f"determinant={determinant:.8g}."
        )
    return axes


def normalized_result_path(path: str) -> str:
    if not path:
        return ""
    return str(Path(path).expanduser().resolve())


def optional_file_signature(path: str) -> Tuple[str, int, int]:
    resolved = normalized_result_path(path)
    if not resolved:
        return ("", 0, 0)
    try:
        stat = Path(resolved).stat()
    except OSError:
        return (resolved, 0, 0)
    return (resolved, int(stat.st_size), int(stat.st_mtime_ns))


def static_animation_session_signature(
    config: SectionConfig,
    selected_result_sets: Sequence[Dict[str, Any]],
) -> StaticAnimationSessionSignature:
    """Return the exact geometry/session identity without GUI playback settings."""

    axes = validate_axes(config.coordinate_system_axes)
    return StaticAnimationSessionSignature(
        rst=optional_file_signature(config.modal_rst),
        external_selection=optional_file_signature(config.external_named_selection_path),
        result_set_ids=tuple(int(item["id"]) for item in selected_result_sets),
        element_named_selection=str(config.element_named_selection or "").strip().lower(),
        coordinate_system_origin=tuple(
            float(value)
            for value in vector3(config.coordinate_system_origin, "coordinate_system_origin")
        ),
        coordinate_system_axes=tuple(
            tuple(float(value) for value in axis) for axis in axes
        ),
        reference_frame_motion=str(
            config.reference_frame_motion or "follow-geometry"
        )
        .strip()
        .lower(),
        reference_frame_attachment_selection=str(
            config.reference_frame_attachment_selection or ""
        )
        .strip()
        .lower(),
        section_normal_axis=str(config.section_normal_axis or "z").strip().lower(),
        extraction_side=str(config.extraction_side or "positive").strip().lower(),
        side_filter_tolerance=float(config.side_filter_tolerance),
        moment_reference_mode=str(config.moment_reference_mode or "coordinate_system_origin")
        .strip()
        .lower(),
    )


def static_animation_time_axis(
    selected_result_sets: Sequence[Dict[str, Any]],
) -> Tuple[List[float], Optional[str]]:
    """Use physical result values only when they form a finite increasing axis."""

    values = [float(item.get("value", index)) for index, item in enumerate(selected_result_sets)]
    valid = all(math.isfinite(value) for value in values) and all(
        values[index] > values[index - 1] for index in range(1, len(values))
    )
    if valid:
        return values, None
    return (
        [float(index) for index in range(len(values))],
        "Result values are duplicate, non-finite, or non-monotonic; "
        "animation timing uses ordered set positions.",
    )


def static_animation_interpolation(
    selected_result_sets: Sequence[Dict[str, Any]],
    progress: float,
    *,
    mode: str = "smooth",
) -> StaticAnimationInterpolation:
    """Map normalized timeline progress to exact or physical-time endpoints."""

    import bisect

    if not selected_result_sets:
        raise ValueError("Static animation requires at least one result set.")
    bounded_progress = min(max(float(progress), 0.0), 1.0)
    axis, warning = static_animation_time_axis(selected_result_sets)
    if len(axis) == 1:
        return StaticAnimationInterpolation(
            0, 0, 0.0, bounded_progress, axis[0], True, warning
        )
    target = axis[0] + bounded_progress * (axis[-1] - axis[0])
    if str(mode).strip().lower() == "exact":
        nearest = min(range(len(axis)), key=lambda index: abs(axis[index] - target))
        return StaticAnimationInterpolation(
            nearest, nearest, 0.0, bounded_progress, axis[nearest], True, warning
        )
    upper = min(max(bisect.bisect_right(axis, target), 1), len(axis) - 1)
    lower = upper - 1
    span = axis[upper] - axis[lower]
    fraction = 0.0 if span <= 0.0 else (target - axis[lower]) / span
    if bounded_progress >= 1.0:
        lower = upper = len(axis) - 1
        fraction = 0.0
    elif bounded_progress <= 0.0:
        lower = upper = 0
        fraction = 0.0
    exact = lower == upper or fraction <= 1.0e-12 or fraction >= 1.0 - 1.0e-12
    if fraction <= 1.0e-12 and lower != upper:
        upper = lower
        fraction = 0.0
    elif fraction >= 1.0 - 1.0e-12 and lower != upper:
        lower = upper
        fraction = 0.0
    return StaticAnimationInterpolation(
        lower,
        upper,
        float(fraction),
        bounded_progress,
        float(target),
        exact,
        warning,
    )


def static_animation_load_order(
    set_count: int,
    *,
    priority_index: int = 0,
    direction: int = 1,
) -> List[int]:
    """Prioritize the current endpoint, then the requested playback direction."""

    count = max(int(set_count), 0)
    if count == 0:
        return []
    current = min(max(int(priority_index), 0), count - 1)
    step = -1 if int(direction) < 0 else 1
    primary = list(range(current, count, step)) if step > 0 else list(range(current, -1, step))
    secondary = (
        list(range(current - 1, -1, -1))
        if step > 0
        else list(range(current + 1, count))
    )
    return primary + secondary


def static_animation_batch_size(node_count: int) -> int:
    bytes_per_set = max(int(node_count), 1) * 3 * 8
    by_bytes = max(STATIC_ANIMATION_MAX_BATCH_BYTES // bytes_per_set, 1)
    return int(min(STATIC_ANIMATION_MAX_BATCH_SETS, by_bytes))


def result_visualization_signature(
    config: SectionConfig,
    *,
    mesh_unit: Optional[str] = None,
) -> Dict[str, Any]:
    cfg = config_from_mapping(asdict(config))
    signature = {
        "analysis_mode": cfg.analysis_mode,
        "static_set_scope": cfg.static_set_scope,
        "result_set_id": cfg.result_set_id,
        "result_set_range_start": cfg.result_set_range_start,
        "result_set_range_end": cfg.result_set_range_end,
        "result_set_range_stride": cfg.result_set_range_stride,
        "modal_rst": normalized_result_path(cfg.modal_rst),
        "mcf": normalized_result_path(cfg.mcf),
        "external_named_selection": list(
            optional_file_signature(cfg.external_named_selection_path)
        ),
        "element_named_selection": str(cfg.element_named_selection).strip().lower(),
        "coordinate_system_origin": [float(value) for value in cfg.coordinate_system_origin],
        "coordinate_system_axes": {
            key: [float(value) for value in cfg.coordinate_system_axes[key]]
            for key in ("x", "y", "z")
        },
        "reference_frame_motion": cfg.reference_frame_motion,
        "reference_frame_attachment_selection": (
            cfg.reference_frame_attachment_selection.strip().lower()
        ),
        "reference_frame_fit_warning_ratio": cfg.reference_frame_fit_warning_ratio,
        "section_normal_axis": str(cfg.section_normal_axis).lower(),
        "extraction_side": str(cfg.extraction_side).lower(),
        "side_filter_tolerance": float(cfg.side_filter_tolerance),
        "moment_reference_mode": str(cfg.moment_reference_mode),
        "force_type": int(cfg.force_type),
        "skip_first_modes": int(cfg.skip_first_modes),
    }
    if mesh_unit is not None:
        signature["mesh_unit"] = str(mesh_unit or "")
    return signature


def axis_from_coordinate_system(axes: Matrix3, axis_name: str) -> Vector:
    axis_index = {"x": 0, "y": 1, "z": 2}.get((axis_name or "").lower())
    if axis_index is None:
        raise ValueError(f"Unsupported section_normal_axis: {axis_name!r}.")
    return axes[axis_index]


def plane_span_axes(axes: Matrix3, normal_axis_name: str) -> Tuple[Vector, Vector]:
    normal_index = {"x": 0, "y": 1, "z": 2}.get((normal_axis_name or "").lower())
    if normal_index is None:
        raise ValueError(f"Unsupported section_normal_axis: {normal_axis_name!r}.")
    span_indices = [index for index in range(3) if index != normal_index]
    return axes[span_indices[0]], axes[span_indices[1]]


def plane_span_axis_names(normal_axis_name: str) -> Tuple[str, str]:
    normal_index = {"x": 0, "y": 1, "z": 2}.get((normal_axis_name or "").lower())
    if normal_index is None:
        raise ValueError(f"Unsupported section_normal_axis: {normal_axis_name!r}.")
    names = ("x", "y", "z")
    span_indices = [index for index in range(3) if index != normal_index]
    return names[span_indices[0]], names[span_indices[1]]


def moment_reference_choice_label(mode: str) -> str:
    for label, value in MOMENT_REFERENCE_CHOICES:
        if str(value) == str(mode):
            return label
    return str(mode or "Moment reference")


def parse_float_tokens(text: str) -> List[float]:
    pattern = re.compile(
        r"[-+]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[EeDd][-+]?\d+)?"
    )
    return [float(match.group(0).replace("D", "E").replace("d", "e")) for match in pattern.finditer(text)]

def _is_mcf_coordinate_header(stripped: str) -> bool:
    return bool(re.search(r"\bTime\b.*\bCoordinates\b", stripped, re.IGNORECASE))

def _unwrap_mcf_lines(lines: Sequence[str]) -> List[str]:
    """Return logical MCF lines by joining indentation-wrapped data records."""
    header_end: Optional[int] = None
    for index, line in enumerate(lines):
        if re.match(r"^\s*Number\s+of\s+Modes\b", line, re.IGNORECASE):
            header_end = index
            break

    if header_end is None:
        header_lines: List[str] = []
        data_lines = list(lines)
    else:
        header_lines = [line.rstrip("\r\n") for line in lines[: header_end + 1]]
        data_lines = list(lines[header_end + 1 :])

    base_indent: Optional[int] = None
    for line in data_lines:
        stripped = line.strip()
        if not stripped or _is_mcf_coordinate_header(stripped):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if base_indent is None or indent < base_indent:
            base_indent = indent
    if base_indent is None:
        base_indent = 0

    unwrapped_data: List[str] = []
    current_line = ""
    for line in data_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _is_mcf_coordinate_header(stripped):
            if current_line:
                unwrapped_data.append(current_line)
                current_line = ""
            unwrapped_data.append(stripped)
            continue

        indent = len(line) - len(line.lstrip(" "))
        if indent == base_indent:
            if current_line:
                unwrapped_data.append(current_line)
            current_line = stripped
        else:
            current_line = f"{current_line} {stripped}".strip()

    if current_line:
        unwrapped_data.append(current_line)

    return header_lines + unwrapped_data

def parse_mcf(path: str) -> Tuple[List[float], List[List[float]]]:
    times: List[float] = []
    coordinates: List[List[float]] = []
    expected_modes: Optional[int] = None
    in_coordinate_table = False
    current_time: Optional[float] = None
    current_coordinates: List[float] = []

    def flush_current(line_number: int) -> None:
        nonlocal current_time, current_coordinates
        if current_time is None:
            return
        if expected_modes is not None and len(current_coordinates) != expected_modes:
            raise ValueError(
                f"MCF record ending near line {line_number} has "
                f"{len(current_coordinates)} modal coordinates; expected {expected_modes}. "
                "If MCFOPT wrapping is enabled, continuation lines must be present."
            )
        times.append(float(current_time))
        coordinates.append([float(value) for value in current_coordinates])
        current_time = None
        current_coordinates = []

    with open(path, "r", encoding="utf-8", errors="ignore") as stream:
        logical_lines = _unwrap_mcf_lines(stream.readlines())

    for line_number, line in enumerate(logical_lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue

        mode_match = re.search(r"Number\s+of\s+Modes\s*:\s*(\d+)", stripped, re.IGNORECASE)
        if mode_match:
            expected_modes = int(mode_match.group(1))
            continue

        if re.search(r"\bTime\b.*\bCoordinates\b", stripped, re.IGNORECASE):
            in_coordinate_table = True
            continue

        if not in_coordinate_table:
            continue

        if not re.match(r"^[+-]?(?:\d|\.)", stripped):
            continue

        values = parse_float_tokens(stripped)
        if not values:
            continue

        if current_time is None:
            current_time = values[0]
            current_coordinates = values[1:]
        elif expected_modes is not None and len(current_coordinates) < expected_modes:
            current_coordinates.extend(values)
        else:
            flush_current(line_number - 1)
            current_time = values[0]
            current_coordinates = values[1:]

        if expected_modes is not None and len(current_coordinates) > expected_modes:
            raise ValueError(
                f"MCF record near line {line_number} contains "
                f"{len(current_coordinates)} modal coordinates; expected {expected_modes}. "
                "The modal-coordinate wrapping could not be parsed unambiguously."
            )

        if expected_modes is not None and len(current_coordinates) == expected_modes:
            flush_current(line_number)

    flush_current(line_number if "line_number" in locals() else 0)

    if not coordinates:
        raise ValueError(f"No modal-coordinate rows were found in {path}.")
    if expected_modes is None:
        row_lengths = {len(row) for row in coordinates}
        if len(row_lengths) != 1:
            raise ValueError(
                f"MCF modal-coordinate rows have inconsistent lengths: {sorted(row_lengths)}. "
                "The file may use wrapped MCFOPT output but does not include a readable "
                "'Number of Modes' header."
            )
    return times, coordinates

def rst_mesh_unit_indicator_text(
    mesh_unit: Optional[str],
    *,
    state: str = "loaded",
) -> str:
    if state == "not_loaded":
        return "RST mesh unit: not loaded"
    if state == "read_failed":
        return "RST mesh unit: read failed"
    unit_text = str(mesh_unit or "").strip()
    return f"RST mesh unit: {unit_text}" if unit_text else "RST mesh unit: unavailable"

def rst_mesh_unit_indicator_tooltip(
    mesh_unit: Optional[str],
    result_units: Optional[Dict[str, Optional[str]]] = None,
) -> str:
    unit_text = str(mesh_unit or "").strip()
    units = result_units or {}
    lines = [
        "RST mesh unit reported by DPF model.metadata.meshed_region.unit.",
        (
            f"Current RST mesh unit: {unit_text}."
            if unit_text
            else "Current RST mesh unit is unavailable."
        ),
    ]
    if units:
        lines.append(
            "Extracted source units: "
            f"force={units.get('force') or 'unavailable'}, "
            f"moment={units.get('moment') or 'unavailable'}."
        )
    lines.extend(
        [
            "If DPF does not report a moment field unit, this tool infers "
            "source moment unit as force unit plus RST mesh unit.",
            "The plot moment-unit dropdown can convert display units without "
            "changing extracted source values.",
        ]
    )
    return "\n".join(lines)

def length_unit_factor_to_m(unit: Optional[str]) -> Optional[float]:
    text = str(unit or "").strip().lower()
    if not text:
        return None
    return _LENGTH_UNIT_TO_M.get(text)

def length_unit_conversion_factor(
    source_unit: Optional[str],
    target_unit: Optional[str],
) -> Optional[float]:
    source_factor = length_unit_factor_to_m(source_unit)
    target_factor = length_unit_factor_to_m(target_unit)
    if source_factor is None or target_factor is None or target_factor == 0.0:
        return None
    return source_factor / target_factor

def moment_unit_factor_to_n_m(unit: Optional[str]) -> Optional[float]:
    text = str(unit or "").strip().lower()
    if not text or text == "source":
        return None
    normalized = re.sub(r"[\s*._/\-]+", " ", text).strip()
    tokens = normalized.split()
    if len(tokens) >= 2:
        force_token, length_token = tokens[0], tokens[1]
        if force_token in _FORCE_UNIT_TO_N and length_token in _LENGTH_UNIT_TO_M:
            return _FORCE_UNIT_TO_N[force_token] * _LENGTH_UNIT_TO_M[length_token]
    compact = re.sub(r"[\s*._/\-]+", "", text)
    for force_token in sorted(_FORCE_UNIT_TO_N, key=len, reverse=True):
        if not compact.startswith(force_token):
            continue
        length_token = compact[len(force_token) :]
        if length_token in _LENGTH_UNIT_TO_M:
            return _FORCE_UNIT_TO_N[force_token] * _LENGTH_UNIT_TO_M[length_token]
    return None

def moment_unit_conversion_factor(
    source_unit: Optional[str],
    target_unit: Optional[str],
) -> Optional[float]:
    target_text = str(target_unit or "").strip()
    if not target_text or target_text.lower() == "source":
        return 1.0
    source_factor = moment_unit_factor_to_n_m(source_unit)
    target_factor = moment_unit_factor_to_n_m(target_text)
    if source_factor is None or target_factor is None or target_factor == 0.0:
        return None
    return source_factor / target_factor

def convert_result_components(
    components: Dict[str, Sequence[float]],
    factor: float,
) -> Dict[str, List[float]]:
    return {
        key: [float(value) * factor for value in values]
        for key, values in components.items()
    }

def rotate_to_local(global_row: Sequence[float], axes: Matrix3) -> List[float]:
    force = global_row[:3]
    moment = global_row[3:]
    return [
        dot(force, axes[0]),
        dot(force, axes[1]),
        dot(force, axes[2]),
        dot(moment, axes[0]),
        dot(moment, axes[1]),
        dot(moment, axes[2]),
    ]

def max_abs_by_component(rows: Sequence[Sequence[float]]) -> Dict[str, float]:
    labels = ["fx", "fy", "fz", "mx", "my", "mz"]
    result: Dict[str, float] = {}
    for index, label in enumerate(labels):
        result[label] = max((abs(row[index]) for row in rows), default=0.0)
    return result

def infer_moment_unit(
    force_unit: Optional[str],
    length_unit: Optional[str],
) -> Optional[str]:
    force_text = str(force_unit or "").strip()
    length_text = str(length_unit or "").strip()
    if not force_text or not length_text:
        return None
    return f"{force_text} {length_text}"

def complete_result_units(
    result_units: Optional[Dict[str, Optional[str]]],
    *,
    mesh_unit: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    units = dict(result_units or {})
    force_unit = units.get("force")
    moment_unit = units.get("moment")
    if not moment_unit:
        moment_unit = infer_moment_unit(force_unit, mesh_unit)
    return {
        "force": force_unit,
        "moment": moment_unit,
    }

def output_csv_unavailable_message(path: str) -> str:
    return (
        "Output CSV cannot be overwritten because it appears to be open or locked: "
        f"{path}. Close the CSV in Excel or any other program and run extraction again. "
        "The existing file was not overwritten."
    )

def _assert_windows_output_file_replaceable(path: Path) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    generic_read = 0x80000000
    generic_write = 0x40000000
    open_existing = 3
    file_attribute_normal = 0x80
    invalid_handle = ctypes.c_void_p(-1).value

    handle = create_file(
        str(path),
        generic_read | generic_write,
        0,
        None,
        open_existing,
        file_attribute_normal,
        None,
    )
    if handle == invalid_handle:
        error_code = ctypes.get_last_error()
        if error_code in {5, 32, 33}:
            raise PermissionError(output_csv_unavailable_message(str(path)))
        raise OSError(error_code, f"Unable to check output CSV replace access: {path}")
    close_handle(handle)

def _assert_existing_output_file_replaceable(path: Path) -> None:
    if os.name == "nt":
        _assert_windows_output_file_replaceable(path)
        return

    try:
        with open(path, "r+b") as stream:
            try:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            except ImportError:
                pass
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    raise PermissionError(output_csv_unavailable_message(str(path))) from exc
                raise
    except PermissionError as exc:
        raise PermissionError(output_csv_unavailable_message(str(path))) from exc

def ensure_output_csv_can_be_replaced(path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_dir():
            raise IsADirectoryError(f"Output CSV path is a directory: {target}")
        _assert_existing_output_file_replaceable(target)

    probe_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(target.parent),
            prefix=f".{target.name}.write-test-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            probe_path = Path(stream.name)
            stream.write("")
    except PermissionError as exc:
        raise PermissionError(f"Output CSV folder is not writable: {target.parent}") from exc
    finally:
        if probe_path is not None:
            try:
                probe_path.unlink()
            except OSError:
                pass
