# Purpose: DPF metadata, scoping, named-selection, and coordinate-system helpers for the MCF DPF section resultants tool.
# Map: subsystems/packaging_generated_assets
# Tests: tests/test_mcf_dpf_section_resultants_gui.py
# Landmarks: selected_element_mesh; nodal_displacement_batch_for_ids; result_set_options; force_summation_operator
"""DPF and result-file access helpers."""

from __future__ import annotations

import argparse
import csv
import errno
import json
import math
import os
import re
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.mcf_dpf_section_resultants.core import *
from scripts.mcf_dpf_section_resultants.core import _MODAL_RST_METADATA_CACHE

def parse_version_tuple(value: Any) -> Tuple[int, int, int]:
    parts = [int(part) for part in re.findall(r"\d+", str(value or ""))[:3]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def version_at_least(value: Any, minimum: Tuple[int, int, int]) -> bool:
    return parse_version_tuple(value) >= minimum


def detected_ansys_release_codes(env: Optional[Dict[str, str]] = None) -> List[int]:
    source = env if env is not None else os.environ
    codes: set[int] = set()
    for key in source:
        match = re.fullmatch(r"AWP_ROOT(\d{3})", str(key).upper())
        if match:
            codes.add(int(match.group(1)))
    return sorted(codes)


def ansys_release_label(release_code: int) -> str:
    year = 2000 + int(release_code) // 10
    release = int(release_code) % 10
    return f"Ansys {year} R{release}"


def is_2023r2_or_older_dpf_release(release_code: int) -> bool:
    return ANSYS_2022R2_RELEASE_CODE <= int(release_code) <= ANSYS_2023R2_RELEASE_CODE


def is_unc_path(path: str) -> bool:
    return str(path).startswith("\\\\")


def dpf_compatibility_error_message(dpf_version: Any, release_codes: Sequence[int]) -> Optional[str]:
    if not version_at_least(dpf_version, PYDPF_CORE_2023R2_MAX_VERSION):
        return None
    legacy_codes = [code for code in release_codes if is_2023r2_or_older_dpf_release(code)]
    newer_codes = [code for code in release_codes if code > ANSYS_2023R2_RELEASE_CODE]
    if legacy_codes and not newer_codes:
        labels = ", ".join(ansys_release_label(code) for code in legacy_codes)
        return (
            f"PyDPF-Core {dpf_version} is not compatible with {labels}. "
            "For Ansys 2022 R2 through 2023 R2, install PyDPF-Core below 0.16.0. "
            f"Run: {PYDPF_CORE_2023R2_INSTALL_COMMAND}"
        )
    return None


def preflight_dpf_open(dpf: Any, rst_path: str, log: LogFn = None) -> None:
    dpf_version = getattr(dpf, "__version__", "unknown")
    release_codes = detected_ansys_release_codes()
    if release_codes:
        labels = ", ".join(ansys_release_label(code) for code in release_codes)
        emit(log, f"Detected Ansys installation environment: {labels}.")
    else:
        emit(log, "No AWP_ROOT### Ansys installation environment variable was detected.")
    emit(log, f"PyDPF-Core client version: {dpf_version}.")

    message = dpf_compatibility_error_message(dpf_version, release_codes)
    if message:
        emit(log, f"DPF compatibility check failed: {message}")
        raise DpfCompatibilityError(message)

    if version_at_least(dpf_version, PYDPF_CORE_2023R2_MAX_VERSION):
        emit(
            log,
            "If this run uses Ansys 2023 R2, this PyDPF-Core client is too new; "
            f"use {PYDPF_CORE_2023R2_INSTALL_COMMAND}.",
        )
    if is_unc_path(rst_path):
        emit(
            log,
            "RST is on a UNC/network path. If DPF opening is slow or fails, "
            "copy the RST and adjacent solver files to a local SSD path and retry.",
        )

def modal_rst_signature(rst_path: str) -> ModalRstSignature:
    path = Path(rst_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Modal RST does not exist: {rst_path}")
    resolved = path.resolve()
    stat = resolved.stat()
    return ModalRstSignature(
        path=str(resolved),
        size_bytes=int(stat.st_size),
        mtime_ns=int(stat.st_mtime_ns),
    )


def modal_rst_cache_key(signature: ModalRstSignature) -> RstMetadataCacheKey:
    return (signature.path, signature.size_bytes, signature.mtime_ns)


def clear_modal_rst_metadata_cache() -> None:
    _MODAL_RST_METADATA_CACHE.clear()

def make_scoping(dpf: Any, ids: Sequence[int], location: Optional[str] = None) -> Any:
    ids_list = [int(value) for value in ids]
    try:
        if location is None:
            return dpf.Scoping(ids=ids_list)
        return dpf.Scoping(ids=ids_list, location=location)
    except TypeError:
        scoping = dpf.Scoping()
        try:
            scoping.ids = ids_list
        except Exception:
            scoping.Ids = ids_list
        if location is not None:
            try:
                scoping.location = location
            except Exception:
                pass
        return scoping


def object_ids(value: Any) -> List[int]:
    ids = getattr(value, "ids", None)
    if ids is None:
        ids = getattr(value, "Ids", None)
    if ids is None:
        ids = value
    return [int(item) for item in list(ids)]


def _read_mechanical_export_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def _unique_positive_ids(values: Iterable[int], label: str) -> List[int]:
    ids: List[int] = []
    seen: set[int] = set()
    for raw_value in values:
        value = int(raw_value)
        if value <= 0:
            raise ValueError(f"{label} contains invalid ID {value}; IDs must be positive.")
        if value not in seen:
            ids.append(value)
            seen.add(value)
    return ids


def parse_mechanical_named_selection_text(path: str) -> List[int]:
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"External named-selection file does not exist: {path}")
    ids: List[int] = []
    for line in _read_mechanical_export_text(source).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        first_column = re.split(r"[\s,;]+", stripped, maxsplit=1)[0].strip('"')
        if re.fullmatch(r"\+?\d+", first_column):
            ids.append(int(first_column))
    ids = _unique_positive_ids(ids, "Mechanical text export")
    if not ids:
        raise ValueError(
            f"Mechanical text export contains no generated node IDs: {source}"
        )
    return ids


def _expand_cmblock_entries(entries: Sequence[int], name: str) -> List[int]:
    expanded: List[int] = []
    previous: Optional[int] = None
    for entry in entries:
        if entry >= 0:
            expanded.append(entry)
            previous = entry
            continue
        endpoint = abs(entry)
        if previous is None or endpoint <= previous:
            raise ValueError(
                f"CDB component {name!r} has invalid compact range endpoint {entry}."
            )
        expanded.extend(range(previous + 1, endpoint + 1))
        previous = endpoint
    return _unique_positive_ids(expanded, f"CDB component {name!r}")


def parse_cdb_named_selection_components(path: str) -> List[Dict[str, Any]]:
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"External named-selection CDB does not exist: {path}")
    lines = _read_mechanical_export_text(source).splitlines()
    components: List[Dict[str, Any]] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not re.match(r"^CMBLOCK\s*,", line, flags=re.IGNORECASE):
            index += 1
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) < 4 or not fields[1]:
            raise ValueError(f"Malformed CMBLOCK header in {source}: {line}")
        name = fields[1]
        entity = fields[2].upper()
        try:
            entry_count = int(fields[3])
        except ValueError as exc:
            raise ValueError(f"Invalid CMBLOCK item count in {source}: {line}") from exc
        if entry_count < 0:
            raise ValueError(f"Invalid CMBLOCK item count in {source}: {line}")

        index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        if index >= len(lines) or not lines[index].lstrip().startswith("("):
            raise ValueError(f"CMBLOCK {name!r} is missing its format line in {source}.")
        index += 1

        entries: List[int] = []
        while len(entries) < entry_count and index < len(lines):
            data_line = lines[index].strip()
            if re.match(r"^[A-Z/]", data_line, flags=re.IGNORECASE):
                break
            entries.extend(int(value) for value in re.findall(r"[+-]?\d+", data_line))
            index += 1
        if len(entries) < entry_count:
            raise ValueError(
                f"CMBLOCK {name!r} expected {entry_count} entries, "
                f"but only {len(entries)} were found in {source}."
            )
        if len(entries) > entry_count:
            raise ValueError(
                f"CMBLOCK {name!r} contains more than its declared "
                f"{entry_count} entries in {source}."
            )

        if entity in {"NODE", "ELEM", "ELEMENT"}:
            normalized_entity = "NODE" if entity == "NODE" else "ELEMENT"
            ids = _expand_cmblock_entries(entries, name)
            components.append(
                {
                    "name": name,
                    "entity": normalized_entity,
                    "ids": ids,
                    "count": len(ids),
                }
            )
    return components


def load_external_named_selection_options(path: str) -> List[Dict[str, Any]]:
    source = Path(path).expanduser()
    if source.suffix.lower() == ".cdb":
        options = parse_cdb_named_selection_components(str(source))
    else:
        if source.suffix.lower() in {".xls", ".xlsx"}:
            raise ValueError(
                "Excel named-selection exports are not supported; save/export as text."
            )
        ids = parse_mechanical_named_selection_text(str(source))
        options = [
            {
                "name": source.stem or "External selection",
                "entity": "NODE",
                "ids": ids,
                "count": len(ids),
            }
        ]
    usable = [option for option in options if option["ids"]]
    if not usable:
        raise ValueError(
            f"No non-empty NODE or ELEMENT named-selection components were found in {source}."
        )
    return usable


def discover_external_named_selection_options(path: str) -> List[Dict[str, Any]]:
    return [
        {
            "name": str(option["name"]),
            "entity": str(option["entity"]),
            "location": (
                "Nodal (converted to fully-contained elements)"
                if option["entity"] == "NODE"
                else "Elemental"
            ),
            "count": int(option["count"]),
        }
        for option in load_external_named_selection_options(path)
    ]


def connect_pin(pin: Any, value: Any) -> None:
    if hasattr(pin, "connect"):
        pin.connect(value)
        return
    if hasattr(pin, "Connect"):
        pin.Connect(value)
        return
    raise AttributeError(f"DPF pin cannot be connected: {pin!r}")


def output_data(output_pin: Any) -> Any:
    try:
        return output_pin()
    except TypeError:
        pass
    if hasattr(output_pin, "eval"):
        return output_pin.eval()
    if hasattr(output_pin, "GetData"):
        return output_pin.GetData()
    raise AttributeError(f"DPF output cannot be evaluated: {output_pin!r}")


def dpf_field_unit(field: Any) -> Optional[str]:
    for attr in ("unit", "Unit", "unit_string", "UnitString"):
        if not hasattr(field, attr):
            continue
        value = getattr(field, attr)
        try:
            value = value() if callable(value) else value
        except TypeError:
            continue
        text = str(value or "").strip()
        if text and text.lower() not in {"none", "unitless"}:
            return text
    return None


def result_units_from_fields(
    force_field: Any = None,
    moment_field: Any = None,
) -> Dict[str, Optional[str]]:
    return {
        "force": dpf_field_unit(force_field) if force_field is not None else None,
        "moment": dpf_field_unit(moment_field) if moment_field is not None else None,
    }


def label_with_unit(label: str, unit: Optional[str]) -> str:
    unit_text = str(unit or "").strip()
    return f"{label} [{unit_text}]" if unit_text else label


def csv_result_header(name: str, unit: Optional[str]) -> str:
    return label_with_unit(name, unit)


def connect_optional_pin(inputs: Any, name: str, value: Any) -> None:
    if value is None or not hasattr(inputs, name):
        return
    connect_pin(getattr(inputs, name), value)


def create_streams_container(dpf: Any, data_sources: Any) -> Any:
    provider = dpf.operators.metadata.streams_provider()
    connect_pin(provider.inputs.data_sources, data_sources)
    return output_data(provider.outputs.streams_container)


def mesh_provider_laziness(dpf: Any) -> Any:
    tree = dpf.DataTree()
    tree.add(
        num_named_selections=0,
        named_selection=1,
        mat=1,
        apdl_element_type=1,
        section=1,
    )
    return tree


class _ScopedIds:
    def __init__(self, ids: Sequence[int], location: str) -> None:
        self.ids = [int(value) for value in ids]
        self.location = str(location)


class _ScopedNodesView:
    def __init__(self, source: Any, node_ids: Sequence[int]) -> None:
        self._source = source
        self.scoping = _ScopedIds(node_ids, "Nodal")

    @property
    def n_nodes(self) -> int:
        return len(self.scoping.ids)

    def node_by_id(self, node_id: int) -> Any:
        return self._source.node_by_id(int(node_id))


class _ScopedElementsView:
    def __init__(self, source: Any, element_ids: Sequence[int]) -> None:
        self._source = source
        self.scoping = _ScopedIds(element_ids, "Elemental")

    @property
    def n_elements(self) -> int:
        return len(self.scoping.ids)

    def element_by_id(self, element_id: int) -> Any:
        return self._source.element_by_id(int(element_id))


class _SelectedMeshView:
    def __init__(
        self,
        source_mesh: Any,
        node_ids: Sequence[int],
        element_ids: Sequence[int],
        element_nodes: Dict[int, Sequence[int]],
        points: Sequence[Sequence[float]],
    ) -> None:
        self.unit = getattr(source_mesh, "unit", None)
        self._source_mesh = source_mesh
        self.nodes = _ScopedNodesView(source_mesh.nodes, node_ids)
        self.elements = _ScopedElementsView(source_mesh.elements, element_ids)
        self._element_nodes = {
            int(element_id): [int(node_id) for node_id in topology_node_ids]
            for element_id, topology_node_ids in element_nodes.items()
        }
        self._points = [
            [float(value) for value in coordinates[:3]]
            for coordinates in points
        ]
        self._cached_grid_payload: Optional[Dict[str, Any]] = None

    @property
    def _grid_payload(self) -> Dict[str, Any]:
        """Build the renderer-only VTK payload on first visualization access."""

        if self._cached_grid_payload is None:
            element_ids = [int(value) for value in self.elements.scoping.ids]
            node_ids = [int(value) for value in self.nodes.scoping.ids]
            point_index = {
                node_id: index
                for index, node_id in enumerate(node_ids)
            }
            cells: List[int] = []
            celltypes: List[int] = []
            for element_id in element_ids:
                element = self._source_mesh.elements.element_by_id(element_id)
                render_node_ids = self._element_nodes[element_id]
                vtk_type, render_node_ids = _linear_vtk_cell(element, render_node_ids)
                try:
                    render_indices = [point_index[node_id] for node_id in render_node_ids]
                except KeyError as exc:
                    raise RuntimeError(
                        f"Selected element {element_id} references node {exc.args[0]} outside "
                        "the selected mesh."
                    ) from exc
                cells.extend([len(render_indices), *render_indices])
                celltypes.append(int(vtk_type))
            self._cached_grid_payload = {
                "points": self._points,
                "cells": cells,
                "celltypes": celltypes,
                "element_ids": element_ids,
            }
        return self._cached_grid_payload


_LINEAR_VTK_CELL_BY_DPF_TYPE: Dict[str, Tuple[int, Optional[int]]] = {
    "tet10": (10, 4),
    "hex20": (12, 8),
    "wedge15": (13, 6),
    "pyramid13": (14, 5),
    "tri6": (5, 3),
    "trishell6": (5, 3),
    "quad8": (9, 4),
    "quadshell8": (9, 4),
    "line3": (3, 2),
    "point1": (1, 1),
    "tet4": (10, 4),
    "hex8": (12, 8),
    "wedge6": (13, 6),
    "pyramid5": (14, 5),
    "tri3": (5, 3),
    "trishell3": (5, 3),
    "quad4": (9, 4),
    "quadshell4": (9, 4),
    "line2": (3, 2),
    "surface3": (5, 3),
    "surface4": (9, 4),
    "surface6": (5, 3),
    "surface8": (9, 4),
    "polygon": (7, None),
}


def _linear_vtk_cell(element: Any, node_ids: Sequence[int]) -> Tuple[int, List[int]]:
    element_type = getattr(element, "type", None)
    type_name = getattr(element_type, "name", element_type)
    normalized_type = str(type_name or "").split(".")[-1].lower()
    specification = _LINEAR_VTK_CELL_BY_DPF_TYPE.get(normalized_type)
    if specification is not None:
        vtk_type, corner_count = specification
        return vtk_type, list(node_ids[:corner_count]) if corner_count else list(node_ids)

    shape = str(getattr(element, "shape", "") or "").lower()
    node_count = len(node_ids)
    if shape == "point" or node_count == 1:
        return 1, list(node_ids[:1])
    if shape == "beam" or node_count == 2:
        return 3, list(node_ids[:2])
    if shape == "shell":
        corner_count = 3 if node_count in (3, 6) else min(4, node_count)
        return (5 if corner_count == 3 else 9), list(node_ids[:corner_count])
    if shape == "solid":
        solid_layout = {4: (10, 4), 5: (14, 5), 6: (13, 6), 8: (12, 8)}
        if node_count in solid_layout:
            vtk_type, corner_count = solid_layout[node_count]
            return vtk_type, list(node_ids[:corner_count])
    element_id = getattr(element, "id", "unknown")
    raise ValueError(
        "Cannot build a safe linear VTK cell for selected element "
        f"{element_id}: DPF element type={type_name!r}, shape={shape!r}, "
        f"node_count={node_count}. This element type is not supported by the "
        "local selected-mesh renderer."
    )


def selected_element_mesh_view(source_mesh: Any, element_scoping: Any) -> Any:
    """Build a selected-mesh view without DPF mesh-copy or VTK operators."""

    element_ids = [int(value) for value in object_ids(element_scoping)]
    if not element_ids:
        raise ValueError("Selected element scoping contains no element IDs.")
    element_nodes: Dict[int, List[int]] = {}
    for element_id in element_ids:
        node_ids = [
            int(value)
            for value in source_mesh.elements.element_by_id(element_id).node_ids
        ]
        if not node_ids:
            raise ValueError(f"Selected element {element_id} contains no nodes.")
        element_nodes[element_id] = node_ids

    node_ids: List[int] = []
    seen_node_ids: set[int] = set()
    for element_id in element_ids:
        for node_id in element_nodes[element_id]:
            if node_id not in seen_node_ids:
                seen_node_ids.add(node_id)
                node_ids.append(node_id)
    points: List[List[float]] = []
    for node_id in node_ids:
        try:
            coordinates = source_mesh.nodes.node_by_id(node_id).coordinates
        except Exception as exc:
            raise RuntimeError(
                "Selected elements reference node ID "
                f"{node_id} that cannot be read from the source mesh."
            ) from exc
        if len(coordinates) < 3:
            raise RuntimeError(
                "Selected mesh node "
                f"{node_id} does not provide three reference coordinates."
            )
        points.append([float(value) for value in coordinates[:3]])

    return _SelectedMeshView(
        source_mesh,
        node_ids,
        element_ids,
        element_nodes,
        points,
    )


def selected_element_mesh(model: Any, element_scoping: Any) -> Any:
    source_mesh = getattr(model.metadata, "meshed_region", None)
    source_mesh = source_mesh() if callable(source_mesh) else source_mesh
    if source_mesh is None:
        raise ValueError("DPF did not expose the RST mesh for selected-element scoping.")
    return selected_element_mesh_view(source_mesh, element_scoping)


def selected_mesh_node_ids(mesh: Any) -> List[int]:
    nodes = getattr(mesh, "nodes", None)
    scoping = getattr(nodes, "scoping", None)
    if scoping is None:
        raise ValueError("Selected DPF mesh does not expose nodal scoping IDs.")
    node_ids = object_ids(scoping)
    if not node_ids:
        raise ValueError("Selected DPF mesh contains no nodes to deform.")
    return node_ids


def nodal_displacements_for_ids(
    dpf: Any,
    data_sources: Any,
    streams_container: Any,
    node_ids: Sequence[int],
    result_set_id: int,
    mesh_unit: str,
    log: LogFn = None,
) -> Tuple[Dict[int, Vector], Dict[str, Any]]:
    node_ids = sorted(set(int(value) for value in node_ids))
    if not node_ids:
        raise ValueError("No node IDs were supplied for selected-set displacement.")
    set_id = int(result_set_id)
    emit(
        log,
        f"Reading global nodal displacement for cumulative DPF set ID {set_id} "
        f"on {len(node_ids)} selected-mesh node(s).",
    )
    try:
        operator = dpf.operators.result.displacement()
    except Exception as exc:
        raise RuntimeError(
            "DPF could not create the displacement operator required for deformed "
            f"geometry at result set {set_id}: {exc}"
        ) from exc
    connect_pin(operator.inputs.data_sources, data_sources)
    connect_optional_pin(operator.inputs, "streams_container", streams_container)
    connect_pin(
        operator.inputs.time_scoping,
        make_scoping(dpf, [set_id], dpf.locations.time_freq),
    )
    connect_pin(
        operator.inputs.mesh_scoping,
        make_scoping(dpf, node_ids, dpf.locations.nodal),
    )
    connect_optional_pin(operator.inputs, "bool_rotate_to_global", True)
    try:
        fields_container = output_data(operator.outputs.fields_container)
        field = field_by_time_id(fields_container, set_id)
        raw_rows = field_vector_rows_by_id(field)
    except Exception as exc:
        raise RuntimeError(
            "DPF could not read the displacement field required for deformed "
            f"geometry at cumulative result set {set_id}: {exc}"
        ) from exc

    missing_node_ids = [node_id for node_id in node_ids if node_id not in raw_rows]
    if missing_node_ids:
        raise RuntimeError(
            "The selected-set displacement field is missing "
            f"{len(missing_node_ids)} selected-mesh node(s); first missing IDs: "
            f"{missing_node_ids[:10]}. Refusing to fall back to reference geometry."
        )

    displacement_unit = dpf_field_unit(field)
    mesh_unit = str(mesh_unit or "").strip() or None
    if displacement_unit is None or mesh_unit is None:
        raise RuntimeError(
            "DPF must report both displacement and mesh length units before "
            "deformed coordinates can be used safely. "
            f"displacement_unit={displacement_unit!r}, mesh_unit={mesh_unit!r}."
        )
    conversion_factor = length_unit_conversion_factor(displacement_unit, mesh_unit)
    if conversion_factor is None and displacement_unit.strip().lower() == mesh_unit.lower():
        conversion_factor = 1.0
    if conversion_factor is None:
        raise RuntimeError(
            "Cannot convert the selected-set displacement unit to the RST mesh unit: "
            f"{displacement_unit!r} -> {mesh_unit!r}. Refusing to use mixed-unit geometry."
        )

    displacements = {
        node_id: scale_vector(raw_rows[node_id], conversion_factor)
        for node_id in node_ids
    }
    max_node_id = max(displacements, key=lambda node_id: vector_magnitude(displacements[node_id]))
    max_displacement = vector_magnitude(displacements[max_node_id])
    evidence = {
        "geometry_state": "deformed",
        "coordinate_equation": "X_deformed = X_reference + U_global(result_set)",
        "coordinate_basis": "global_cartesian",
        "result_set_id": set_id,
        "displacement_unit": displacement_unit,
        "mesh_unit": mesh_unit,
        "displacement_to_mesh_unit_factor": float(conversion_factor),
        "node_count": len(node_ids),
        "missing_node_count": 0,
        "max_displacement": float(max_displacement),
        "max_displacement_node_id": int(max_node_id),
        "max_displacement_vector": [
            float(value) for value in displacements[max_node_id]
        ],
    }
    emit(
        log,
        "Selected-set deformed geometry ready: "
        f"max |U|={max_displacement:.6g} {mesh_unit} at node {max_node_id}.",
    )
    return displacements, evidence


def nodal_displacement_batch_for_ids(
    dpf: Any,
    data_sources: Any,
    streams_container: Any,
    node_ids: Sequence[int],
    result_set_ids: Sequence[int],
    mesh_unit: str,
    log: LogFn = None,
) -> Dict[int, Tuple[Dict[int, Vector], Dict[str, Any]]]:
    """Read a bounded group of static displacement fields with one DPF operator."""

    scoped_node_ids = sorted(set(int(value) for value in node_ids))
    set_ids = [int(value) for value in result_set_ids]
    if not scoped_node_ids:
        raise ValueError("No node IDs were supplied for animation displacement.")
    if not set_ids:
        return {}
    estimated_bytes = len(scoped_node_ids) * 3 * 8 * len(set_ids)
    if len(set_ids) > STATIC_ANIMATION_MAX_BATCH_SETS:
        raise ValueError(
            "Animation displacement batch exceeds "
            f"{STATIC_ANIMATION_MAX_BATCH_SETS} result sets."
        )
    if len(set_ids) > 1 and estimated_bytes > STATIC_ANIMATION_MAX_BATCH_BYTES:
        raise ValueError(
            "Animation displacement batch exceeds the 64 MiB raw-vector limit: "
            f"{format_bytes(estimated_bytes)}."
        )
    emit(
        log,
        "Reading global nodal displacement for cumulative DPF set IDs "
        f"{set_ids} on {len(scoped_node_ids)} animation node(s).",
    )
    try:
        operator = dpf.operators.result.displacement()
    except Exception as exc:
        raise RuntimeError(
            "DPF could not create the displacement operator required for animation "
            f"sets {set_ids}: {exc}"
        ) from exc
    connect_pin(operator.inputs.data_sources, data_sources)
    connect_optional_pin(operator.inputs, "streams_container", streams_container)
    connect_pin(
        operator.inputs.time_scoping,
        make_scoping(dpf, set_ids, dpf.locations.time_freq),
    )
    connect_pin(
        operator.inputs.mesh_scoping,
        make_scoping(dpf, scoped_node_ids, dpf.locations.nodal),
    )
    connect_optional_pin(operator.inputs, "bool_rotate_to_global", True)
    try:
        fields_container = output_data(operator.outputs.fields_container)
    except Exception as exc:
        raise RuntimeError(
            "DPF could not read displacement fields required for animation "
            f"sets {set_ids}: {exc}"
        ) from exc

    mesh_length_unit = str(mesh_unit or "").strip() or None
    results: Dict[int, Tuple[Dict[int, Vector], Dict[str, Any]]] = {}
    for set_id in set_ids:
        try:
            field = field_by_time_id(fields_container, set_id)
            raw_rows = field_vector_rows_by_id(field)
        except Exception as exc:
            raise RuntimeError(
                "DPF could not read the displacement field required for animation "
                f"at cumulative result set {set_id}: {exc}"
            ) from exc
        missing_node_ids = [
            node_id for node_id in scoped_node_ids if node_id not in raw_rows
        ]
        if missing_node_ids:
            raise RuntimeError(
                "The animation displacement field is missing "
                f"{len(missing_node_ids)} node(s) at set {set_id}; first missing IDs: "
                f"{missing_node_ids[:10]}."
            )
        displacement_unit = dpf_field_unit(field)
        if displacement_unit is None or mesh_length_unit is None:
            raise RuntimeError(
                "DPF must report displacement and mesh units for animation; "
                f"set={set_id}, displacement_unit={displacement_unit!r}, "
                f"mesh_unit={mesh_length_unit!r}."
            )
        conversion_factor = length_unit_conversion_factor(
            displacement_unit, mesh_length_unit
        )
        if (
            conversion_factor is None
            and displacement_unit.strip().lower() == mesh_length_unit.lower()
        ):
            conversion_factor = 1.0
        if conversion_factor is None:
            raise RuntimeError(
                "Cannot convert animation displacement to the RST mesh unit: "
                f"{displacement_unit!r} -> {mesh_length_unit!r}."
            )
        displacements = {
            node_id: scale_vector(raw_rows[node_id], conversion_factor)
            for node_id in scoped_node_ids
        }
        max_node_id = max(
            displacements,
            key=lambda node_id: vector_magnitude(displacements[node_id]),
        )
        max_displacement = vector_magnitude(displacements[max_node_id])
        results[set_id] = (
            displacements,
            {
                "geometry_state": "deformed",
                "coordinate_equation": "X_deformed = X_reference + U_global(result_set)",
                "coordinate_basis": "global_cartesian",
                "result_set_id": set_id,
                "displacement_unit": displacement_unit,
                "mesh_unit": mesh_length_unit,
                "displacement_to_mesh_unit_factor": float(conversion_factor),
                "node_count": len(scoped_node_ids),
                "missing_node_count": 0,
                "max_displacement": float(max_displacement),
                "max_displacement_node_id": int(max_node_id),
                "max_displacement_vector": [
                    float(value) for value in displacements[max_node_id]
                ],
            },
        )
    return results


def selected_set_nodal_displacements(
    dpf: Any,
    data_sources: Any,
    streams_container: Any,
    mesh: Any,
    result_set_id: int,
    log: LogFn = None,
) -> Tuple[Dict[int, Vector], Dict[str, Any]]:
    return nodal_displacements_for_ids(
        dpf,
        data_sources,
        streams_container,
        selected_mesh_node_ids(mesh),
        result_set_id,
        str(getattr(mesh, "unit", "") or ""),
        log=log,
    )


def summation_point_field(
    dpf: Any,
    coordinates: Sequence[float],
    mesh_unit: str,
) -> Any:
    unit = str(mesh_unit or "").strip()
    if not unit:
        raise ValueError("A mesh length unit is required for the DPF summation point.")
    field = dpf.Field(
        nentities=1,
        nature=dpf.natures.vector,
        location=dpf.locations.overall,
    )
    field.scoping.ids = [0]
    field.data = [[float(value) for value in coordinates[:3]]]
    field.unit = unit
    return field


def resolve_element_named_selection_scoping(
    dpf: Any,
    model: Any,
    data_sources: Any,
    streams_container: Any,
    name: str,
) -> Tuple[Any, str, List[str]]:
    available = [
        str(item)
        for item in list(getattr(model.metadata, "available_named_selections", []) or [])
    ]
    matched_name = name
    for candidate in available:
        if candidate.lower() == name.lower():
            matched_name = candidate
            break

    metadata_error: Optional[Exception] = None
    metadata_location = ""
    try:
        scoping, matched_name, available = get_named_scoping(model, matched_name)
        metadata_location = str(getattr(scoping, "location", "") or "")
        if is_element_named_selection_location(metadata_location):
            return scoping, str(matched_name), available
    except Exception as exc:
        metadata_error = exc

    try:
        op = dpf.operators.scoping.on_named_selection()
        connect_pin(op.inputs.requested_location, dpf.locations.elemental)
        connect_pin(op.inputs.named_selection_name, str(matched_name).upper())
        connect_optional_pin(op.inputs, "int_inclusive", 0)
        connect_optional_pin(op.inputs, "streams_container", streams_container)
        connect_pin(op.inputs.data_sources, data_sources)
        scoping = output_data(op.outputs.mesh_scoping)
    except Exception as exc:
        available_text = ", ".join(available)
        if metadata_error is not None:
            metadata_detail = f"Metadata lookup failed: {metadata_error}."
        else:
            metadata_detail = (
                "Metadata resolved location: "
                f"{metadata_location or 'unknown'}."
            )
        raise ValueError(
            f"Named selection {name!r} did not resolve to elemental scoping. "
            f"{metadata_detail} Elemental named-selection resolution failed: {exc}. "
            f"Available named selections: {available_text}"
        ) from exc

    location = str(getattr(scoping, "location", "") or "")
    if not is_element_named_selection_location(location):
        available_text = ", ".join(available)
        raise ValueError(
            f"Named selection {name!r} did not resolve to elemental scoping. "
            f"Resolved location: {location or 'unknown'}. "
            f"Available named selections: {available_text}"
        )
    return scoping, str(matched_name), available


def resolve_external_element_scoping(
    dpf: Any,
    model: Any,
    path: str,
    name: str,
) -> Tuple[Any, str, List[str]]:
    options = load_external_named_selection_options(path)
    available = [str(option["name"]) for option in options]
    matched = next(
        (
            option
            for option in options
            if str(option["name"]).lower() == str(name).lower()
        ),
        None,
    )
    if matched is None:
        raise ValueError(
            f"External named selection {name!r} was not found in {path}. "
            f"Available selections: {', '.join(available)}"
        )

    mesh = getattr(model.metadata, "meshed_region", None)
    mesh = mesh() if callable(mesh) else mesh
    if mesh is None:
        raise ValueError("DPF did not expose the RST mesh for external selection scoping.")
    entity = str(matched["entity"])
    container = mesh.nodes if entity == "NODE" else mesh.elements
    available_ids = set(object_ids(container.scoping))
    requested_ids = [int(value) for value in matched["ids"]]
    missing_ids = [value for value in requested_ids if value not in available_ids]
    if missing_ids:
        raise ValueError(
            f"External {entity} component {matched['name']!r} contains "
            f"{len(missing_ids)} ID(s) absent from the RST mesh: "
            f"{preview_items(missing_ids)}"
        )

    if entity == "ELEMENT":
        scoping = make_scoping(dpf, requested_ids, dpf.locations.elemental)
    else:
        transpose = dpf.operators.scoping.transpose()
        connect_pin(
            transpose.inputs.mesh_scoping,
            make_scoping(dpf, requested_ids, dpf.locations.nodal),
        )
        connect_pin(transpose.inputs.meshed_region, mesh)
        connect_optional_pin(transpose.inputs, "inclusive", 0)
        connect_optional_pin(transpose.inputs, "extend_midside_nodes", False)
        connect_optional_pin(
            transpose.inputs,
            "requested_location",
            dpf.locations.elemental,
        )
        scoping = transpose.eval()
        if not object_ids(scoping):
            raise ValueError(
                f"External NODE component {matched['name']!r} contains no complete "
                "RST elements. Export all generated nodes for the element/body selection."
            )
    return scoping, str(matched["name"]), available


def _mesh_entity_node_ids(mesh: Any, element_ids: Sequence[int]) -> List[int]:
    node_ids: set[int] = set()
    for element_id in element_ids:
        element = mesh.elements.element_by_id(int(element_id))
        node_ids.update(int(value) for value in list(element.node_ids))
    return sorted(node_ids)


def mesh_node_coordinates_for_ids(
    mesh: Any,
    node_ids: Sequence[int],
) -> Dict[int, Vector]:
    coordinates: Dict[int, Vector] = {}
    for node_id in sorted(set(int(value) for value in node_ids)):
        node = mesh.nodes.node_by_id(node_id)
        xyz = list(node.coordinates)
        if len(xyz) < 3:
            raise ValueError(f"RST node {node_id} does not expose three coordinates.")
        coordinates[node_id] = [float(value) for value in xyz[:3]]
    return coordinates


def resolve_reference_frame_attachment_nodes(
    dpf: Any,
    model: Any,
    *,
    name: str,
    external_named_selection_path: str = "",
) -> Tuple[List[int], Dict[str, Any]]:
    selection_name = str(name or "").strip()
    if not selection_name:
        raise ValueError("Reference-frame attachment selection name is empty.")
    mesh = getattr(model.metadata, "meshed_region", None)
    mesh = mesh() if callable(mesh) else mesh
    if mesh is None:
        raise ValueError("DPF did not expose the RST mesh for frame attachment.")

    if external_named_selection_path:
        options = load_external_named_selection_options(external_named_selection_path)
        matched = next(
            (
                option
                for option in options
                if str(option["name"]).lower() == selection_name.lower()
            ),
            None,
        )
        if matched is None:
            raise ValueError(
                f"Frame attachment selection {selection_name!r} was not found in "
                f"{external_named_selection_path}."
            )
        entity = str(matched["entity"]).upper()
        entity_ids = [int(value) for value in matched["ids"]]
        available_container = mesh.nodes if entity == "NODE" else mesh.elements
        available_ids = set(object_ids(available_container.scoping))
        missing = [value for value in entity_ids if value not in available_ids]
        if missing:
            raise ValueError(
                f"Frame attachment {entity} selection {selection_name!r} contains "
                f"ID(s) absent from the RST mesh: {missing[:10]}."
            )
        node_ids = (
            sorted(set(entity_ids))
            if entity == "NODE"
            else _mesh_entity_node_ids(mesh, entity_ids)
        )
        source = "external_named_selection"
    else:
        scoping, resolved_name, available = get_named_scoping(model, selection_name)
        selection_name = resolved_name
        location = str(getattr(scoping, "location", "") or "").lower()
        entity_ids = object_ids(scoping)
        if "nod" in location:
            entity = "NODE"
            node_ids = sorted(set(entity_ids))
        elif "elem" in location:
            entity = "ELEMENT"
            node_ids = _mesh_entity_node_ids(mesh, entity_ids)
        else:
            raise ValueError(
                f"Frame attachment selection {selection_name!r} must be nodal or "
                f"elemental; resolved location={location or 'unknown'}. "
                f"Available named selections: {', '.join(available)}"
            )
        source = "rst_named_selection"
    if not node_ids:
        raise ValueError(
            f"Frame attachment selection {selection_name!r} resolves to zero nodes."
        )
    return node_ids, {
        "source": source,
        "selection": selection_name,
        "entity": entity,
        "entity_count": len(entity_ids),
        "node_count": len(node_ids),
        "node_ids_hash": stable_id_hash(node_ids),
    }


def field_by_time_id(fields_container: Any, time_id: int) -> Any:
    if hasattr(fields_container, "get_field_by_time_id"):
        return fields_container.get_field_by_time_id(time_id)
    if hasattr(fields_container, "GetFieldByTimeId"):
        return fields_container.GetFieldByTimeId(time_id)
    raise AttributeError("FieldsContainer does not expose get_field_by_time_id.")


def field_values(field: Any) -> List[float]:
    data = field.data if hasattr(field, "data") else field.Data
    if hasattr(data, "tolist"):
        values = data.tolist()
    else:
        values = list(data)
    if values and hasattr(values[0], "tolist"):
        values = values[0].tolist()
    if values and isinstance(values[0], (list, tuple)):
        values = values[0]
    return [float(value) for value in values]


def field_vector(field: Any) -> Vector:
    values = field_values(field)
    if len(values) < 3:
        raise ValueError(f"Expected a 3-component field, got {values!r}.")
    return [float(values[0]), float(values[1]), float(values[2])]


def field_vector_rows_by_id(field: Any) -> Dict[int, Vector]:
    scoping = getattr(field, "scoping", None)
    if scoping is None:
        scoping = getattr(field, "Scoping", None)
    if scoping is None:
        raise AttributeError("Field does not expose scoping.")
    ids = object_ids(scoping)

    data = field.data if hasattr(field, "data") else field.Data
    values = data.tolist() if hasattr(data, "tolist") else list(data)
    if values and hasattr(values[0], "tolist"):
        values = [value.tolist() for value in values]

    rows: List[Any]
    if not values:
        rows = []
    elif isinstance(values[0], (list, tuple)):
        rows = list(values)
    else:
        flat = [float(value) for value in values]
        if len(ids) == 1 and len(flat) >= 3:
            rows = [flat[:3]]
        elif len(flat) == len(ids) * 3:
            rows = [flat[index : index + 3] for index in range(0, len(flat), 3)]
        else:
            raise ValueError(
                "Field data row count does not match scoping IDs: "
                f"{len(flat)} value(s), {len(ids)} ID(s)."
            )

    if len(rows) != len(ids):
        raise ValueError(
            "Field data row count does not match scoping IDs: "
            f"{len(rows)} row(s), {len(ids)} ID(s)."
        )

    result: Dict[int, Vector] = {}
    for node_id, row in zip(ids, rows):
        if hasattr(row, "tolist"):
            row = row.tolist()
        if len(row) < 3:
            raise ValueError(f"Expected a 3-component vector row, got {row!r}.")
        result[int(node_id)] = [float(row[0]), float(row[1]), float(row[2])]
    return result


def get_time_set_count(time_freq_support: Any) -> int:
    for attr in ("n_sets", "number_sets", "NumberSets"):
        if hasattr(time_freq_support, attr):
            value = getattr(time_freq_support, attr)
            return int(value() if callable(value) else value)
    raise AttributeError("Could not determine the number of modal sets.")


def result_set_options(time_freq_support: Any) -> List[Dict[str, Any]]:
    set_count = get_time_set_count(time_freq_support)
    time_field = getattr(time_freq_support, "time_frequencies", None)
    if time_field is None:
        raise ValueError("RST time/frequency support does not expose result-set values.")
    if callable(time_field):
        time_field = time_field()
    values = field_values(time_field)
    if len(values) != set_count:
        raise ValueError(
            "RST result-set metadata is misaligned: "
            f"n_sets={set_count}, time/frequency values={len(values)}."
        )
    unit = dpf_field_unit(time_field)
    unit_suffix = f" {unit}" if unit else ""
    return [
        {
            "id": set_id,
            "value": float(value),
            "unit": unit,
            "label": f"Set {set_id} — {float(value):.12g}{unit_suffix}",
        }
        for set_id, value in enumerate(values, start=1)
    ]


def modal_summation_batches(
    mode_count: int,
    batch_size: int,
    *,
    start_mode_id: int = 1,
) -> List[List[int]]:
    mode_total = int(mode_count)
    if mode_total <= 0:
        return []
    size = max(1, int(batch_size))
    start_id = max(1, int(start_mode_id))
    end_id = start_id + mode_total - 1
    return [
        list(range(start, min(end_id, start + size - 1) + 1))
        for start in range(start_id, end_id + 1, size)
    ]


def get_named_scoping(model: Any, name: str) -> Tuple[Any, str, List[str]]:
    available = list(getattr(model.metadata, "available_named_selections", []) or [])
    for candidate in available:
        if str(candidate).lower() == name.lower():
            return model.metadata.named_selection(candidate), str(candidate), [str(item) for item in available]
    try:
        scoping = model.metadata.named_selection(name)
        return scoping, name, [str(item) for item in available]
    except Exception as exc:
        available_text = ", ".join(str(item) for item in available)
        raise ValueError(
            f"Named selection {name!r} was not found in the modal RST. "
            f"Available named selections: {available_text}"
        ) from exc


def is_element_named_selection_location(location: Any) -> bool:
    location_text = str(location or "").lower()
    return "element" in location_text


def scoping_id_count(scoping: Any) -> int:
    ids = getattr(scoping, "ids", None)
    if ids is None:
        ids = getattr(scoping, "Ids", [])
    try:
        return int(len(ids))
    except TypeError:
        return int(len(list(ids)))


def discover_element_named_selection_options(
    rst_path: str,
    log: LogFn = None,
) -> List[Dict[str, Any]]:
    import ansys.dpf.core as dpf

    metadata = load_modal_rst_metadata(rst_path, log=log)
    data_sources = dpf.DataSources(metadata.signature.path)
    model = dpf.Model(data_sources)
    streams_container = create_streams_container(dpf, data_sources)
    options: List[Dict[str, Any]] = []
    skipped: List[str] = []
    emit(
        log,
        "Filtering named-selection dropdown to non-empty elemental/body "
        "scopes usable for section force postprocessing.",
    )
    try:
        for name in sorted(metadata.named_selection_names, key=str.lower):
            try:
                scoping, resolved_name, _available = resolve_element_named_selection_scoping(
                    dpf,
                    model,
                    data_sources,
                    streams_container,
                    name,
                )
                count = scoping_id_count(scoping)
            except Exception:
                skipped.append(name)
                continue
            if count <= 0:
                skipped.append(name)
                continue
            options.append(
                {
                    "name": resolved_name,
                    "location": str(getattr(scoping, "location", "") or "Elemental"),
                    "count": count,
                    "metadata_only": False,
                }
            )
    finally:
        try:
            streams_container.release_handles()
        except Exception:
            pass
    emit(
        log,
        "Named-selection filter kept "
        f"{len(options)} of {len(metadata.named_selection_names)} "
        f"({preview_items([option['name'] for option in options])}).",
    )
    if skipped:
        emit(
            log,
            "Hidden empty or non-elemental named selections: "
            f"{preview_items(skipped)}.",
        )
    return options

def parse_float_csv(text: Optional[str]) -> List[float]:
    if not text:
        return []
    return [
        float(part)
        for part in re.split(r"[,\s]+", text.strip())
        if part
    ]


def safe_int(value: Any) -> Optional[int]:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def child_text(element: ET.Element, tag: str) -> Optional[str]:
    for child in list(element):
        if child.tag == tag:
            return (child.text or "").strip()
    return None


def first_child_text_containing(element: ET.Element, needle: str) -> Optional[str]:
    needle_lower = needle.lower()
    for child in element.iter():
        if needle_lower in child.tag.lower():
            text = (child.text or "").strip()
            if text:
                return text
    return None


def parse_caerep_coordinate_systems(rst_path: str) -> Dict[int, Dict[str, Any]]:
    caerep_path = Path(rst_path).expanduser().with_name("CAERep.xml")
    if not caerep_path.is_file():
        return {}
    try:
        root = ET.parse(str(caerep_path)).getroot()
    except Exception:
        return {}

    systems: Dict[int, Dict[str, Any]] = {}
    for element in root.iter("CoordinateSystemRep"):
        solver_id = safe_int(child_text(element, "SolverCoordNumber"))
        if solver_id is None:
            continue
        caption = child_text(element, "Caption") or ""
        cs_type = child_text(element, "Type") or ""
        apdl_name = child_text(element, "SolverCoordName") or first_child_text_containing(
            element, "apdl"
        )
        is_global = (child_text(element, "IsGlobal") or "").lower() == "true"

        origin: Optional[Vector] = None
        origin_unit: Optional[str] = None
        point = next(element.iter("DSGePoint3d"), None)
        if point is not None:
            coords_node = next(point.iter("Coordinates"), None)
            origin_values = parse_float_csv(coords_node.text if coords_node is not None else None)
            if len(origin_values) >= 3:
                origin = origin_values[:3]
                origin_unit = coords_node.attrib.get("Unt") if coords_node is not None else None

        axes: Optional[Dict[str, Vector]] = None
        matrix = next(element.iter("Matrix3X3"), None)
        if matrix is not None:
            rows = [
                parse_float_csv(child_text(matrix, "Row0")),
                parse_float_csv(child_text(matrix, "Row1")),
                parse_float_csv(child_text(matrix, "Row2")),
            ]
            if all(len(row) >= 3 for row in rows):
                axes = {
                    "x": rows[0][:3],
                    "y": rows[1][:3],
                    "z": rows[2][:3],
                }

        candidate = {
            "id": solver_id,
            "name": caption,
            "apdl_name": apdl_name,
            "type": cs_type,
            "origin": origin,
            "origin_unit": origin_unit,
            "axes": axes,
            "object_id": element.attrib.get("ObjId", ""),
            "source": "CAERep.xml",
            "_score": int(is_global) * 4 + int(bool(caption and caption != "Undefined")) * 2 + int(bool(apdl_name)),
        }
        existing = systems.get(solver_id)
        if existing is None or candidate["_score"] > existing.get("_score", 0):
            systems[solver_id] = candidate

    for value in systems.values():
        value.pop("_score", None)
    return systems


def parse_ds_dat_coordinate_name_map(rst_path: str) -> Dict[int, str]:
    ds_dat = Path(rst_path).expanduser().with_name("ds.dat")
    if not ds_dat.is_file():
        return {}
    result: Dict[int, str] = {}
    pattern = re.compile(
        r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\d+)\b.*Coordinate\s+System\s+ID",
        re.IGNORECASE,
    )
    try:
        with open(ds_dat, "r", encoding="utf-8", errors="ignore") as stream:
            for line in stream:
                match = pattern.search(line)
                if match:
                    result[int(match.group(2))] = match.group(1)
    except Exception:
        return result
    return result


def candidate_coordinate_system_ids(
    rst_path: str,
    caerep: Dict[int, Dict[str, Any]],
    *,
    exhaustive: bool = False,
) -> List[int]:
    ids = set(range(1, COORDINATE_SYSTEM_ID_SCAN_LIMIT + 1)) if exhaustive else set()
    ids.update(int(key) for key in caerep)
    ds_dat = Path(rst_path).expanduser().with_name("ds.dat")
    if ds_dat.is_file():
        pattern = re.compile(r"^\s*(?:c?local|cs|cskp)\s*,\s*(\d+)", re.IGNORECASE)
        try:
            with open(ds_dat, "r", encoding="utf-8", errors="ignore") as stream:
                for line in stream:
                    match = pattern.search(line)
                    if match:
                        ids.add(int(match.group(1)))
        except Exception:
            pass
    ids.discard(0)
    return sorted(ids)


def dpf_coordinate_system_type(dpf_module: Any, data_sources: Any, cs_id: int) -> str:
    try:
        provider = dpf_module.operators.metadata.coordinate_system_data_provider(
            data_sources=data_sources,
            solver_coordinate_system_ids=[int(cs_id)],
        )
        data = provider.outputs.coordinate_system_data1.get_data()
        return str(data.get_property("type") or "")
    except Exception:
        return ""


def dpf_coordinate_system_transform(dpf_module: Any, data_sources: Any, cs_id: int) -> Tuple[Vector, Dict[str, Vector]]:
    op = dpf_module.operators.result.coordinate_system(
        data_sources=data_sources,
        cs_id=int(cs_id),
    )
    values = field_values(op.outputs.field.get_data())
    if len(values) < 12:
        raise ValueError(f"Coordinate system {cs_id} returned {len(values)} values, expected 12.")
    rotation = [values[0:3], values[3:6], values[6:9]]
    axes = {
        "x": [rotation[0][0], rotation[1][0], rotation[2][0]],
        "y": [rotation[0][1], rotation[1][1], rotation[2][1]],
        "z": [rotation[0][2], rotation[1][2], rotation[2][2]],
    }
    return values[9:12], axes


def coordinate_system_origin_for_gui_units(option: Dict[str, Any]) -> Vector:
    origin = vector3(
        option.get("origin") or [0.0, 0.0, 0.0],
        "coordinate_system_origin",
    )
    factor = length_unit_conversion_factor(option.get("origin_unit"), GUI_ORIGIN_UNIT)
    if factor is None:
        return origin
    return scale_vector(origin, factor)


def coordinate_system_label(option: Dict[str, Any]) -> str:
    parts = [f"ID {option['id']}"]
    apdl_name = option.get("apdl_name")
    if apdl_name:
        parts.append(f"APDL {apdl_name}")
    elif option.get("name"):
        parts.append(str(option["name"]))
    if option.get("type"):
        parts.append(str(option["type"]))
    if len(option.get("origin") or []) >= 3:
        origin = coordinate_system_origin_for_gui_units(option)
        parts.append(
            "origin[{0}]=({1:.6g}, {2:.6g}, {3:.6g})".format(
                GUI_ORIGIN_UNIT,
                float(origin[0]), float(origin[1]), float(origin[2])
            )
        )
    return " - ".join(parts)


def metadata_coordinate_system_options(
    caerep: Dict[int, Dict[str, Any]],
    ds_dat_apdl_names: Dict[int, str],
    *,
    mesh_unit: Optional[str] = None,
) -> List[Dict[str, Any]]:
    options: List[Dict[str, Any]] = []
    global_meta = caerep.get(0, {})
    global_option = {
        "id": 0,
        "name": global_meta.get("name") or "Global Coordinate System",
        "apdl_name": global_meta.get("apdl_name") or ds_dat_apdl_names.get(0),
        "type": global_meta.get("type") or "Cartesian",
        "origin": [0.0, 0.0, 0.0],
        "origin_unit": global_meta.get("origin_unit") or GUI_ORIGIN_UNIT,
        "axes": {
            "x": [1.0, 0.0, 0.0],
            "y": [0.0, 1.0, 0.0],
            "z": [0.0, 0.0, 1.0],
        },
        "source": "global",
    }
    global_option["label"] = coordinate_system_label(global_option)
    options.append(global_option)

    for cs_id, meta in sorted(caerep.items()):
        if int(cs_id) == 0:
            continue
        origin = meta.get("origin")
        axes = meta.get("axes")
        if not origin or not axes:
            continue
        option = {
            "id": int(cs_id),
            "name": meta.get("name") or "",
            "apdl_name": meta.get("apdl_name") or ds_dat_apdl_names.get(int(cs_id)),
            "type": meta.get("type") or "",
            "origin": origin,
            "origin_unit": meta.get("origin_unit") or mesh_unit,
            "axes": axes,
            "object_id": meta.get("object_id", ""),
            "source": meta.get("source") or "CAERep.xml",
        }
        option["label"] = coordinate_system_label(option)
        options.append(option)
    return sorted(options, key=lambda item: int(item["id"]))


def result_info_names(result_info: Any) -> List[str]:
    available = getattr(result_info, "available_results", None)
    if available is None:
        return []
    names: List[str] = []
    for result in list(available or []):
        for attr in ("name", "operator_name", "result_name"):
            value = getattr(result, attr, None)
            if value:
                names.append(str(value() if callable(value) else value))
                break
        else:
            names.append(str(result))
    return names


def _read_modal_rst_metadata_uncached(
    signature: ModalRstSignature,
    log: LogFn = None,
) -> ModalRstMetadata:
    import ansys.dpf.core as dpf

    preflight_dpf_open(dpf, signature.path, log=log)
    data_sources = dpf.DataSources(signature.path)
    model = dpf.Model(data_sources)
    metadata = model.metadata
    sets = result_set_options(metadata.time_freq_support)
    try:
        mesh_unit = str(getattr(metadata.meshed_region, "unit", "") or "") or None
    except Exception:
        mesh_unit = None
    caerep = parse_caerep_coordinate_systems(signature.path)
    ds_dat_apdl_names = parse_ds_dat_coordinate_name_map(signature.path)
    return ModalRstMetadata(
        signature=signature,
        named_selection_names=[
            str(item)
            for item in list(getattr(metadata, "available_named_selections", []) or [])
        ],
        modal_set_count=get_time_set_count(metadata.time_freq_support),
        result_names=result_info_names(metadata.result_info),
        mesh_unit=mesh_unit,
        coordinate_system_options=metadata_coordinate_system_options(
            caerep,
            ds_dat_apdl_names,
            mesh_unit=mesh_unit,
        ),
        caerep_coordinate_systems=caerep,
        ds_dat_apdl_names=ds_dat_apdl_names,
        result_sets=sets,
    )


def load_modal_rst_metadata(
    rst_path: str,
    *,
    include_dpf_coordinate_scan: bool = False,
    log: LogFn = None,
) -> ModalRstMetadata:
    signature = modal_rst_signature(rst_path)
    key = modal_rst_cache_key(signature)
    emit(
        log,
        "RST metadata request: "
        f"{signature.path} ({format_bytes(signature.size_bytes)}).",
    )
    metadata = _MODAL_RST_METADATA_CACHE.get(key)
    if metadata is None:
        emit(
            log,
            "Metadata cache miss; opening DPF model for result info, "
            "time/frequency support, and named-selection names.",
        )
        metadata_start = perf_counter()
        metadata = _read_modal_rst_metadata_uncached(signature, log=log)
        _MODAL_RST_METADATA_CACHE[key] = metadata
        emit(
            log,
            "Metadata read complete in "
            f"{format_seconds(perf_counter() - metadata_start)}: "
            f"{len(metadata.named_selection_names)} named selection(s), "
            f"{metadata.modal_set_count} modal/time set(s), "
            f"{len(metadata.result_names)} result name(s), "
            f"{len(metadata.coordinate_system_options)} coordinate option(s).",
        )
    else:
        emit(
            log,
            "Metadata cache hit: "
            f"{len(metadata.named_selection_names)} named selection(s), "
            f"{metadata.modal_set_count} modal/time set(s), "
            f"{len(metadata.result_names)} result name(s).",
        )
    if include_dpf_coordinate_scan and metadata.scanned_coordinate_system_options is None:
        emit(
            log,
            "DPF coordinate-system scan requested; probing solver coordinate IDs "
            f"up to {COORDINATE_SYSTEM_ID_SCAN_LIMIT}.",
        )
        scan_start = perf_counter()
        metadata.scanned_coordinate_system_options = scan_dpf_coordinate_system_options(
            signature.path,
            metadata.caerep_coordinate_systems,
            metadata.ds_dat_apdl_names,
            metadata.coordinate_system_options,
            mesh_unit=metadata.mesh_unit,
        )
        emit(
            log,
            "DPF coordinate-system scan complete in "
            f"{format_seconds(perf_counter() - scan_start)}: "
            f"{len(metadata.scanned_coordinate_system_options)} option(s).",
        )
    elif include_dpf_coordinate_scan:
        emit(
            log,
            "DPF coordinate-system scan cache hit: "
            f"{len(metadata.scanned_coordinate_system_options or [])} option(s).",
        )
    return metadata


def scan_dpf_coordinate_system_options(
    rst_path: str,
    caerep: Dict[int, Dict[str, Any]],
    ds_dat_apdl_names: Dict[int, str],
    base_options: Sequence[Dict[str, Any]],
    *,
    mesh_unit: Optional[str] = None,
) -> List[Dict[str, Any]]:
    import ansys.dpf.core as dpf

    data_sources = dpf.DataSources(rst_path)
    options = [dict(option) for option in base_options]
    seen = {int(option["id"]) for option in options if "id" in option}
    for cs_id in candidate_coordinate_system_ids(rst_path, caerep, exhaustive=True):
        if cs_id in seen:
            continue
        try:
            origin, axes = dpf_coordinate_system_transform(dpf, data_sources, cs_id)
        except Exception:
            continue
        meta = caerep.get(cs_id, {})
        cs_type = dpf_coordinate_system_type(dpf, data_sources, cs_id) or meta.get("type") or ""
        option = {
            "id": cs_id,
            "name": meta.get("name") or "",
            "apdl_name": meta.get("apdl_name") or ds_dat_apdl_names.get(cs_id),
            "type": cs_type,
            "origin": origin,
            "origin_unit": mesh_unit,
            "axes": axes,
            "object_id": meta.get("object_id", ""),
            "source": "modal RST",
        }
        option["label"] = coordinate_system_label(option)
        options.append(option)
        seen.add(cs_id)
    return sorted(options, key=lambda item: int(item["id"]))

def discover_coordinate_system_options(
    rst_path: str,
    *,
    include_dpf_scan: bool = False,
    log: LogFn = None,
) -> List[Dict[str, Any]]:
    metadata = load_modal_rst_metadata(
        rst_path,
        include_dpf_coordinate_scan=include_dpf_scan,
        log=log,
    )
    if include_dpf_scan and metadata.scanned_coordinate_system_options is not None:
        options = [dict(option) for option in metadata.scanned_coordinate_system_options]
        emit(
            log,
            "Coordinate-system list ready from DPF scan: "
            f"{len(options)} option(s).",
        )
        return options
    options = [dict(option) for option in metadata.coordinate_system_options]
    emit(
        log,
        "Coordinate-system list ready from metadata sidecars/defaults: "
        f"{len(options)} option(s).",
    )
    return options
