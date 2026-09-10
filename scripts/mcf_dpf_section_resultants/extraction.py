# Purpose: DPF modal summation and result export orchestration for the MCF DPF section resultants tool.
# Map: subsystems/packaging_generated_assets
# Tests: tests/test_mcf_dpf_section_resultants_gui.py
# Landmarks: modal_force_moment_coefficients; static_force_moment_series; extract_static_section_resultants; extract_section_resultants
"""Section resultant extraction workflow."""

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
from scripts.mcf_dpf_section_resultants.dpf_io import *
from scripts.mcf_dpf_section_resultants.visualization import *

def modal_force_moment_coefficients(
    config: SectionConfig,
    axes: Matrix3,
    log: LogFn = None,
    max_modes: Optional[int] = None,
    capture_nodal_vectors: bool = False,
) -> Tuple[List[List[float]], Dict[str, Any]]:
    import ansys.dpf.core as dpf

    phase_start = perf_counter()
    static_mode = config.analysis_mode == "static"
    requested_coordinate_system_origin = vector3(
        config.coordinate_system_origin,
        "coordinate_system_origin",
    )
    emit(log, f"Loading RST: {config.modal_rst}")
    emit(log, f"PyDPF version: {getattr(dpf, '__version__', 'unknown')}")
    preflight_dpf_open(dpf, config.modal_rst, log=log)
    emit(log, "Opening DPF data sources and stream container.")
    data_sources = dpf.DataSources(config.modal_rst)
    streams_container = create_streams_container(dpf, data_sources)
    model = dpf.Model(data_sources)
    selection_source = (
        config.external_named_selection_path or "the RST named selections"
    )
    emit(
        log,
        f"Resolving named selection {config.element_named_selection!r} "
        f"from {selection_source} as elemental scoping.",
    )
    scoping_start = perf_counter()
    if config.external_named_selection_path:
        element_scoping, element_name, available_named = resolve_external_element_scoping(
            dpf,
            model,
            config.external_named_selection_path,
            config.element_named_selection,
        )
    else:
        element_scoping, element_name, available_named = resolve_element_named_selection_scoping(
            dpf,
            model,
            data_sources,
            streams_container,
            config.element_named_selection,
        )
    named_selection_seconds = perf_counter() - scoping_start
    emit(
        log,
        "Named selection resolved in "
        f"{format_seconds(named_selection_seconds)}: {element_name!r}, "
        f"{scoping_id_count(element_scoping)} elemental ID(s).",
    )
    emit(log, "Building the selected element mesh view from the open RST mesh.")
    mesh_start = perf_counter()
    reference_mesh = selected_element_mesh(model, element_scoping)
    mesh_seconds = perf_counter() - mesh_start
    emit(log, f"Selected element submesh ready in {format_seconds(mesh_seconds)}.")
    config, origin_unit_conversion = config_with_origin_in_mesh_units(
        config,
        reference_mesh,
        log=log,
    )
    mesh = reference_mesh
    deformation: Optional[Dict[str, Any]] = None
    reference_side_filter_info: Optional[Dict[str, Any]] = None
    if static_mode:
        number_sets = get_time_set_count(model.metadata.time_freq_support)
        if config.result_set_id is None:
            raise ValueError("Static Structural mode requires a result-set ID.")
        result_set_id = int(config.result_set_id)
        if result_set_id < 1 or result_set_id > number_sets:
            raise ValueError(
                f"Static result-set ID {result_set_id} is out of range; "
                f"the RST has cumulative set IDs 1-{number_sets}."
            )
        nodal_displacements, deformation = selected_set_nodal_displacements(
            dpf,
            data_sources,
            streams_container,
            reference_mesh,
            result_set_id,
            log=log,
        )
        mesh = mesh_with_nodal_displacements(
            reference_mesh,
            nodal_displacements,
            deformation,
            include_grid=False,
        )
        _, _, reference_side_filter_info = construction_surface_scoping(
            dpf,
            model,
            element_scoping,
            config,
            axes,
            mesh=reference_mesh,
            allow_empty_cut=True,
        )
    emit(
        log,
        "Building construction-surface scoping: "
        f"normal={config.section_normal_axis}, side={config.extraction_side}, "
        f"tolerance={config.side_filter_tolerance:.3g}.",
    )
    surface_start = perf_counter()
    scoping_mesh = mesh
    if static_mode and config.reference_frame_motion == "fixed":
        scoping_mesh = reference_mesh
    filtered_elem_scope, node_scope, side_filter_info = construction_surface_scoping(
        dpf,
        model,
        element_scoping,
        config,
        axes,
        mesh=scoping_mesh,
    )
    if static_mode and config.reference_frame_motion == "fixed":
        side_filter_info = side_filter_with_mesh_coordinates(
            side_filter_info,
            mesh,
            config.coordinate_system_origin,
            axis_from_coordinate_system(axes, config.section_normal_axis),
            scoping_geometry_state="reference",
        )
    elif static_mode:
        side_filter_info["scoping_geometry_state"] = "deformed"
        side_filter_info["coordinate_geometry_state"] = "deformed"
    if deformation is not None and reference_side_filter_info is not None:
        deformation["scope_change"] = deformation_scope_change_evidence(
            reference_side_filter_info,
            side_filter_info,
        )
    surface_seconds = perf_counter() - surface_start
    emit(
        log,
        "Construction-surface filter complete in "
        f"{format_seconds(surface_seconds)}: "
        f"{side_filter_info['cut_element_count']} cut element(s), "
        f"{side_filter_info['selected_node_count']} side node(s), "
        f"{side_filter_info['not_cut_element_count']} not-cut element(s), "
        f"{side_filter_info['element_failure_count']} element lookup failure(s).",
    )

    moment_reference_xyz = vector3(config.coordinate_system_origin, "coordinate_system_origin")
    if config.moment_reference_mode == "mechanical_probe_mesh_centroid":
        moment_reference_xyz = [
            float(value) for value in side_filter_info["moment_reference_centroid"]
        ]
    elif config.moment_reference_mode == "selected_side_node_centroid":
        moment_reference_xyz = [
            float(value) for value in side_filter_info["selected_node_centroid"]
        ]
    elif config.moment_reference_mode != "coordinate_system_origin":
        raise ValueError(f"Unsupported moment_reference_mode: {config.moment_reference_mode!r}.")
    emit(
        log,
        f"Moment reference mode {config.moment_reference_mode!r}: "
        f"{moment_reference_xyz}.",
    )

    number_sets = get_time_set_count(model.metadata.time_freq_support)
    if number_sets <= 0:
        raise ValueError(f"Modal RST has no time/frequency sets: {config.modal_rst}")
    if static_mode:
        if config.result_set_id is None:
            raise ValueError("Static Structural mode requires a result-set ID.")
        result_set_id = int(config.result_set_id)
        if result_set_id < 1 or result_set_id > number_sets:
            raise ValueError(
                f"Static result-set ID {result_set_id} is out of range; "
                f"the RST has cumulative set IDs 1-{number_sets}."
            )
        skip_first_modes = 0
        modes_available_after_skip = 1
        modes_to_evaluate = 1
        modal_batch_size = 1
        first_mode_set_id = result_set_id
        last_mode_set_id = result_set_id
        mode_batches = [[result_set_id]]
    else:
        skip_first_modes = max(0, int(config.skip_first_modes))
        if skip_first_modes >= number_sets:
            raise ValueError(
                f"Skip first modes ({skip_first_modes}) leaves no modal RST set to evaluate; "
                f"the modal RST reports {number_sets} modal/time set(s)."
            )
        modes_available_after_skip = number_sets - skip_first_modes
        modes_to_evaluate = modes_available_after_skip
        if max_modes is not None:
            modes_to_evaluate = min(modes_available_after_skip, int(max_modes))
        if modes_to_evaluate <= 0:
            raise ValueError("No MCF modal coordinates were available for DPF evaluation.")
        modal_batch_size = max(1, int(config.modal_summation_batch_size))
        first_mode_set_id = skip_first_modes + 1
        last_mode_set_id = skip_first_modes + modes_to_evaluate
        mode_batches = modal_summation_batches(
            modes_to_evaluate,
            modal_batch_size,
            start_mode_id=first_mode_set_id,
        )
    result_names = result_info_names(model.metadata.result_info)
    if static_mode:
        emit(log, f"Static result scope: cumulative DPF set ID {first_mode_set_id} of {number_sets}.")
    else:
        emit(
            log,
            f"Modal set scope: evaluating {modes_to_evaluate} of {number_sets} "
            f"RST modal/time set(s); MCF requested {max_modes if max_modes is not None else 'all'}; "
            f"skipped first {skip_first_modes}; DPF set IDs {first_mode_set_id}-{last_mode_set_id}; "
            f"batch size={modal_batch_size} mode(s), batches={len(mode_batches)}.",
        )

    summation_seconds = 0.0
    coefficient_seconds = 0.0
    coefficients: List[List[float]] = []
    result_units: Dict[str, Optional[str]] = {"force": None, "moment": None}
    vector_capture_warning = None
    visualization_nodal_force_coefficients: Dict[int, List[Vector]] = {}
    visualization_nodal_moment_coefficients: Dict[int, List[Vector]] = {}
    nodal_moment_capture_warning = None
    nodal_moment_output_available = False
    if capture_nodal_vectors:
        visualization_nodal_force_coefficients = {
            int(node_id): []
            for node_id in side_filter_info.get("selected_node_ids", [])
        }
    selected_node_ids = list(visualization_nodal_force_coefficients)
    if capture_nodal_vectors and static_mode:
        visualization_nodal_moment_coefficients = {
            node_id: [] for node_id in selected_node_ids
        }

    for batch_index, mode_ids in enumerate(mode_batches, start=1):
        batch_first = mode_ids[0]
        batch_last = mode_ids[-1]
        emit(
            log,
            "Running DPF force_summation batch "
            f"{batch_index}/{len(mode_batches)} for modal set IDs {batch_first}-{batch_last} "
            f"({len(mode_ids)} effective mode(s)): {len(filtered_elem_scope.ids)} cut element(s), "
            f"{len(node_scope.ids)} side node(s).",
        )
        batch_summation_start = perf_counter()
        op = dpf.operators.averaging.force_summation()
        connect_pin(op.inputs.data_sources, data_sources)
        connect_optional_pin(op.inputs, "streams_container", streams_container)
        connect_pin(op.inputs.time_scoping, make_scoping(dpf, mode_ids))
        connect_pin(op.inputs.nodal_scoping, node_scope)
        connect_pin(op.inputs.elemental_scoping, filtered_elem_scope)
        connect_pin(
            op.inputs.force_type,
            MECHANICAL_PROBE_FORCE_TYPE if static_mode else int(config.force_type),
        )

        try:
            force_fc = output_data(op.outputs.force_accumulation)
            moment_fc = output_data(op.outputs.moment_accumulation)
        except Exception as exc:
            message = build_force_summation_failure_message(
                config=config,
                result_names=result_names,
                raw_element_count=int(len(element_scoping.ids)),
                cut_element_count=int(len(filtered_elem_scope.ids)),
                side_node_count=int(len(node_scope.ids)),
                modes_to_evaluate=len(mode_ids),
                raw_error=exc,
            )
            if static_mode:
                message += (
                    "\n\nFailed Static Structural result set: "
                    f"cumulative DPF set ID {batch_first}."
                )
            else:
                message += (
                    "\n\nFailed modal summation batch: "
                    f"modal set IDs {batch_first}-{batch_last}; "
                    f"skipped first {skip_first_modes} mode(s). "
                    "Try lowering modal_summation_batch_size in the config or GUI."
                )
            emit(
                log,
                "DPF force_summation failed before coefficient extraction for "
                f"batch {batch_index}/{len(mode_batches)}. The RST may be missing "
                "OUTRES,NLOAD-style elemental-nodal force data, the selected force "
                "type may not be stored, or the modal batch is still too large.",
            )
            raise RuntimeError(message) from exc

        if capture_nodal_vectors and vector_capture_warning is None:
            try:
                forces_on_nodes_fc = output_data(op.outputs.forces_on_nodes)
                for mode_id in mode_ids:
                    rows = field_vector_rows_by_id(
                        field_by_time_id(forces_on_nodes_fc, mode_id)
                    )
                    for node_id in selected_node_ids:
                        visualization_nodal_force_coefficients[node_id].append(
                            rows.get(node_id, [0.0, 0.0, 0.0])
                        )
            except Exception as exc:
                vector_capture_warning = repr(exc)
                if static_mode:
                    raise RuntimeError(
                        "Static Structural extraction produced aggregate resultants, "
                        "but DPF force_summation did not provide the per-node forces "
                        "required for nodal export and visualization. Confirm that the "
                        "RST stores OUTRES,NLOAD-style elemental-nodal force data. "
                        f"Raw DPF error: {exc}"
                    ) from exc
                emit(
                    log,
                    "Warning: DPF force_summation did not provide per-node force "
                    f"vectors for visualization: {exc}",
                )

        if capture_nodal_vectors and static_mode:
            try:
                moments_on_nodes_fc = output_data(op.outputs.moments_on_nodes)
                try:
                    nodal_moment_field_count = len(moments_on_nodes_fc)
                except (AttributeError, TypeError):
                    nodal_moment_field_count = None
                if nodal_moment_field_count == 0:
                    for node_id in selected_node_ids:
                        visualization_nodal_moment_coefficients[node_id].extend(
                            [[0.0, 0.0, 0.0] for _mode_id in mode_ids]
                        )
                    emit(
                        log,
                        "DPF force_summation returned an empty moments_on_nodes "
                        "container; this result set has no explicit nodal couples.",
                    )
                else:
                    for mode_id in mode_ids:
                        rows = field_vector_rows_by_id(
                            field_by_time_id(moments_on_nodes_fc, mode_id)
                        )
                        for node_id in selected_node_ids:
                            visualization_nodal_moment_coefficients[node_id].append(
                                rows.get(node_id, [0.0, 0.0, 0.0])
                            )
                nodal_moment_output_available = True
            except Exception as exc:
                nodal_moment_capture_warning = repr(exc)
                for node_id in selected_node_ids:
                    visualization_nodal_moment_coefficients[node_id].extend(
                        [[0.0, 0.0, 0.0] for _mode_id in mode_ids]
                    )
                emit(
                    log,
                    "Warning: DPF force_summation could not read explicit per-node "
                    "moments. Continuing with zero nodal couples, marking moment "
                    f"parity incomplete, and retaining the raw error: {exc}",
                )

        batch_summation_seconds = perf_counter() - batch_summation_start
        summation_seconds += batch_summation_seconds
        emit(
            log,
            "DPF force_summation batch "
            f"{batch_index}/{len(mode_batches)} evaluated in "
            f"{format_seconds(batch_summation_seconds)}; "
            "reading force/moment fields.",
        )

        batch_coefficient_start = perf_counter()
        for mode_id in mode_ids:
            force_field = field_by_time_id(force_fc, mode_id)
            moment_field = field_by_time_id(moment_fc, mode_id)
            if result_units["force"] is None or result_units["moment"] is None:
                field_units = result_units_from_fields(force_field, moment_field)
                result_units = {
                    "force": result_units["force"] or field_units.get("force"),
                    "moment": result_units["moment"] or field_units.get("moment"),
                }
            force = field_vector(force_field)
            moment_about_origin = field_vector(moment_field)
            coefficients.append(force + moment_about_origin)
        coefficient_seconds += perf_counter() - batch_coefficient_start
        del force_fc, moment_fc, op

    result_units = complete_result_units(result_units, mesh_unit=getattr(mesh, "unit", None))
    emit(
        log,
        "Modal force/moment coefficient rows assembled in "
        f"{format_seconds(coefficient_seconds)}.",
    )
    section_geometry = projected_section_geometry_from_mesh(
        mesh,
        config,
        axes,
        side_filter_info,
    )

    visualization_vector_data = None
    if capture_nodal_vectors:
        visualization_vector_data = {
            "geometry_state": "deformed" if deformation is not None else "reference",
            "deformation": dict(deformation) if deformation is not None else None,
            "selected_node_coordinates": side_filter_info.get(
                "selected_node_coordinates",
                {},
            ),
            "selected_node_centroid": side_filter_info.get(
                "selected_node_centroid",
                moment_reference_xyz,
            ),
            "moment_reference_xyz": moment_reference_xyz,
            "section_geometry": section_geometry,
            "nodal_force_modal_coefficients": visualization_nodal_force_coefficients,
            "nodal_moment_modal_coefficients": visualization_nodal_moment_coefficients,
            "nodal_force_capture_warning": vector_capture_warning,
            "nodal_moment_capture_warning": nodal_moment_capture_warning,
            "nodal_moment_output_available": nodal_moment_output_available,
        }

    info = {
        "analysis_mode": config.analysis_mode,
        "result_set_id": int(config.result_set_id) if static_mode else None,
        "geometry_state": "deformed" if deformation is not None else "reference",
        "deformation": dict(deformation) if deformation is not None else None,
        "dpf_version": getattr(dpf, "__version__", None),
        "mesh_unit": getattr(mesh, "unit", None),
        "result_units": result_units,
        "force_type": MECHANICAL_PROBE_FORCE_TYPE if static_mode else int(config.force_type),
        "mode_count": modes_to_evaluate,
        "modal_sets_available": number_sets,
        "modes_available_after_skip": modes_available_after_skip,
        "skip_first_modes": skip_first_modes,
        "first_mode_set_id": first_mode_set_id,
        "last_mode_set_id": last_mode_set_id,
        "modes_evaluated": modes_to_evaluate,
        "element_named_selection": element_name,
        "available_named_selections": available_named,
        "raw_element_count": int(len(element_scoping.ids)),
        "element_count": int(len(filtered_elem_scope.ids)),
        "surface_node_count": int(len(node_scope.ids)),
        "nodal_force_node_count": len(visualization_nodal_force_coefficients),
        "nodal_moment_node_count": (
            len(visualization_nodal_moment_coefficients)
            if nodal_moment_output_available
            else 0
        ),
        "nodal_moment_output_available": nodal_moment_output_available,
        "nodal_moment_capture_warning": nodal_moment_capture_warning,
        "side_filter": compact_side_filter_info(side_filter_info),
        "section_geometry": section_geometry,
        "requested_reference_xyz": requested_coordinate_system_origin,
        "coordinate_system_origin": config.coordinate_system_origin,
        "coordinate_system_origin_unit_conversion": origin_unit_conversion,
        "result_signature": result_visualization_signature(
            config,
            mesh_unit=getattr(mesh, "unit", None),
        ),
        "moment_reference_mode": config.moment_reference_mode,
        "moment_reference_xyz": moment_reference_xyz,
        "modal_summation_batch_size": modal_batch_size,
        "modal_summation_batch_count": len(mode_batches),
        "coefficients_preview": coefficients[:3],
        "named_selection_resolution_seconds": named_selection_seconds,
        "selected_mesh_seconds": mesh_seconds,
        "surface_filter_seconds": surface_seconds,
        "force_summation_eval_seconds": summation_seconds,
        "coefficient_read_seconds": coefficient_seconds,
        "elapsed_seconds": perf_counter() - phase_start,
    }
    if visualization_vector_data is not None:
        info["_visualization_vector_data"] = visualization_vector_data
    try:
        streams_container.release_handles()
        emit(log, "Released DPF stream handles.")
    except Exception:
        pass
    return coefficients, info


def mechanical_equivalent_static_resultants(
    force: Sequence[float],
    raw_dpf_moment_about_reference: Sequence[float],
    mechanical_equivalent_reference_row: Sequence[float],
    moment_reference_xyz: Sequence[float],
    axes: Matrix3,
    *,
    cross_product_moment_factor: float,
) -> Dict[str, List[float]]:
    """Build primary Mechanical-equivalent and raw DPF audit resultants."""

    if len(force) < 3 or len(raw_dpf_moment_about_reference) < 3:
        raise ValueError("Static resultant force and raw DPF moment must have 3 components.")
    if len(mechanical_equivalent_reference_row) < 6:
        raise ValueError(
            "Mechanical-equivalent reference resultant must have 6 components."
        )
    force_values = [float(value) for value in force[:3]]
    mechanical_reference = force_values + [
        float(value) for value in mechanical_equivalent_reference_row[3:6]
    ]
    mechanical_global_origin = force_values + shift_moment_reference(
        mechanical_reference[3:6],
        moment_reference_xyz,
        [0.0, 0.0, 0.0],
        force_values,
        cross_product_moment_factor=cross_product_moment_factor,
    )
    raw_dpf_reference = force_values + [
        float(value) for value in raw_dpf_moment_about_reference[:3]
    ]
    raw_dpf_global_origin = force_values + shift_moment_reference(
        raw_dpf_reference[3:6],
        moment_reference_xyz,
        [0.0, 0.0, 0.0],
        force_values,
        cross_product_moment_factor=cross_product_moment_factor,
    )
    return {
        "resultant_global_origin": mechanical_global_origin,
        "resultant_reference_global": mechanical_reference,
        "resultant_local": rotate_to_local(mechanical_reference, axes),
        "raw_dpf_resultant_global_origin": raw_dpf_global_origin,
        "raw_dpf_resultant_reference_global": raw_dpf_reference,
        "raw_dpf_resultant_local": rotate_to_local(raw_dpf_reference, axes),
    }


def static_nodal_moment_rows(
    moments_fc: Any,
    set_id: int,
    target_moment_unit: Optional[str],
) -> Tuple[Dict[int, Vector], str]:
    """Read explicit nodal couples, accepting only a genuinely empty container."""

    try:
        empty_moments = len(moments_fc) == 0
    except (AttributeError, TypeError):
        empty_moments = False
    if empty_moments:
        return {}, "empty_zero"
    nodal_moment_field = field_by_time_id(moments_fc, set_id)
    rows = field_vector_rows_by_id(nodal_moment_field)
    source_couple_unit = dpf_field_unit(nodal_moment_field) or target_moment_unit
    couple_unit_factor = moment_unit_conversion_factor(
        source_couple_unit,
        target_moment_unit,
    )
    if couple_unit_factor is None:
        raise RuntimeError(
            "Static Structural explicit nodal couples use an unsupported moment-unit "
            f"conversion: {source_couple_unit!r} to {target_moment_unit!r}."
        )
    if couple_unit_factor != 1.0:
        rows = {
            node_id: scale_vector(values, couple_unit_factor)
            for node_id, values in rows.items()
        }
    return rows, "available"


def _add_signed_vector(
    total: Sequence[float],
    values: Sequence[float],
    sign: float,
) -> Vector:
    return [
        float(total[index]) + float(sign) * float(values[index])
        for index in range(3)
    ]


def _merge_signed_vector_rows(
    target: Dict[int, Vector],
    rows: Dict[int, Vector],
    sign: float,
) -> None:
    for node_id, values in rows.items():
        target[int(node_id)] = _add_signed_vector(
            target.get(int(node_id), [0.0, 0.0, 0.0]),
            values,
            sign,
        )


def static_force_summation_terms(
    side_info: Dict[str, Any],
    filtered_elem_scope: Any,
    node_scope: Any,
) -> List[Dict[str, Any]]:
    """Return signed DPF scopes, including duplicate coincident section sheets."""

    configured = side_info.get("force_summation_terms")
    if configured:
        terms = [
            {
                "role": str(term.get("role") or "construction_surface"),
                "sign": float(term.get("sign", 1.0)),
                "element_ids": sorted(
                    set(int(value) for value in term.get("element_ids", []))
                ),
                "node_ids": sorted(
                    set(int(value) for value in term.get("node_ids", []))
                ),
            }
            for term in configured
        ]
        terms = [term for term in terms if term["element_ids"] and term["node_ids"]]
        if terms:
            return terms
    return [
        {
            "role": "construction_surface",
            "sign": 1.0,
            "element_ids": [int(value) for value in object_ids(filtered_elem_scope)],
            "node_ids": [int(value) for value in object_ids(node_scope)],
        }
    ]


def _field_entity_vector_rows(field: Any, entity_id: int) -> List[Vector]:
    getter = getattr(field, "get_entity_data_by_id", None)
    if getter is None:
        getter = getattr(field, "GetEntityDataById", None)
    if getter is None:
        raise AttributeError("Elemental-nodal field does not expose entity data by ID.")
    data = getter(int(entity_id))
    values = data.tolist() if hasattr(data, "tolist") else list(data)
    rows: List[Vector] = []
    for row in values:
        if hasattr(row, "tolist"):
            row = row.tolist()
        rows.append([float(value) for value in row])
    return rows


def static_duplicate_interface_resultants(
    dpf: Any,
    data_sources: Any,
    streams_container: Any,
    mesh: Any,
    displacements: Dict[int, Vector],
    result_set_id: int,
    moment_reference_xyz: Sequence[float],
    terms: Sequence[Dict[str, Any]],
    force_type: int,
) -> Dict[str, Any]:
    """Reconstruct signed, duplicate-sheet solid resultants from ENF rows."""

    selected_force_type = int(force_type)
    if selected_force_type != MECHANICAL_PROBE_FORCE_TYPE:
        raise ValueError(
            "Signed duplicate-interface elemental-nodal reconstruction is proven "
            "only for Static forces (force_type=1); "
            f"received force_type={force_type!r}."
        )
    component_offset = 0
    operator = dpf.operators.result.element_nodal_forces()
    connect_pin(operator.inputs.data_sources, data_sources)
    connect_optional_pin(operator.inputs, "streams_container", streams_container)
    connect_pin(
        operator.inputs.time_scoping,
        make_scoping(dpf, [int(result_set_id)], dpf.locations.time_freq),
    )
    all_element_ids = sorted(
        {
            int(element_id)
            for term in terms
            for element_id in term["element_ids"]
        }
    )
    connect_pin(
        operator.inputs.mesh_scoping,
        make_scoping(dpf, all_element_ids, dpf.locations.elemental),
    )
    connect_optional_pin(operator.inputs, "bool_rotate_to_global", True)
    connect_optional_pin(operator.inputs, "requested_location", dpf.locations.elemental_nodal)
    fields_container = output_data(operator.outputs.fields_container)
    field = field_by_time_id(fields_container, int(result_set_id))
    component_count = int(getattr(field, "component_count", 0) or 0)
    if component_count < component_offset + 3:
        raise RuntimeError(
            "The element-nodal force field does not contain the requested force "
            f"components: force_type={selected_force_type}, component_count={component_count}."
        )

    reference = vector3(moment_reference_xyz, "moment_reference_xyz")
    deformed_positions = {
        node_id: add_vectors(node_xyz(mesh, node_id), displacements[node_id])
        for node_id in sorted(
            {
                int(value)
                for term in terms
                for value in term["node_ids"]
            }
        )
    }
    force: Vector = [0.0, 0.0, 0.0]
    moment: Vector = [0.0, 0.0, 0.0]
    nodal_force_rows: Dict[int, Vector] = {}
    term_resultants: List[Dict[str, Any]] = []
    for term in terms:
        sign = float(term["sign"])
        selected_node_ids = set(int(value) for value in term["node_ids"])
        term_force: Vector = [0.0, 0.0, 0.0]
        term_moment: Vector = [0.0, 0.0, 0.0]
        term_nodal_rows: Dict[int, Vector] = {}
        for element_id in term["element_ids"]:
            element = mesh.elements.element_by_id(int(element_id))
            element_node_ids = [int(value) for value in element.node_ids]
            element_rows = _field_entity_vector_rows(field, int(element_id))
            if len(element_rows) != len(element_node_ids):
                raise RuntimeError(
                    "Elemental-nodal force row count does not match element connectivity: "
                    f"element={element_id}, rows={len(element_rows)}, "
                    f"nodes={len(element_node_ids)}."
                )
            for node_id, raw_row in zip(element_node_ids, element_rows):
                if node_id not in selected_node_ids:
                    continue
                if len(raw_row) < component_offset + 3:
                    raise RuntimeError(
                        "Elemental-nodal force row does not contain the requested force "
                        f"components: element={element_id}, node={node_id}, "
                        f"row_components={len(raw_row)}, offset={component_offset}."
                    )
                values = [float(raw_row[component_offset + index]) for index in range(3)]
                term_force = add_vectors(term_force, values)
                term_nodal_rows[node_id] = add_vectors(
                    term_nodal_rows.get(node_id, [0.0, 0.0, 0.0]),
                    values,
                )
                position = deformed_positions[node_id]
                lever = [position[index] - reference[index] for index in range(3)]
                term_moment = add_vectors(term_moment, cross(lever, values))
        force = _add_signed_vector(force, term_force, sign)
        moment = _add_signed_vector(moment, term_moment, sign)
        _merge_signed_vector_rows(nodal_force_rows, term_nodal_rows, sign)
        term_resultants.append(
            {
                "role": str(term["role"]),
                "sign": sign,
                "element_count": len(term["element_ids"]),
                "node_count": len(term["node_ids"]),
                "force_global": term_force,
                "moment_about_reference_global": term_moment,
            }
        )
    return {
        "force": force,
        "moment_about_reference": moment,
        "nodal_force_rows": nodal_force_rows,
        "nodal_moment_rows": {},
        "nodal_moment_output_status": "solid_element_nodal_no_explicit_couples",
        "force_unit": dpf_field_unit(field),
        "moment_unit": infer_moment_unit(dpf_field_unit(field), getattr(mesh, "unit", None)),
        "term_resultants": term_resultants,
    }


def require_static_nodal_force_match(parity: Dict[str, Any], set_id: int) -> None:
    if parity.get("force_matches") is True:
        return
    raise RuntimeError(
        "Static Structural per-node force reconstruction does not match DPF "
        "force_accumulation, so an exact Mechanical-equivalent section resultant "
        f"cannot be published for set {set_id}. "
        f"Force error norm={parity.get('force_error_norm')!r}; "
        f"tolerance={parity.get('force_tolerance')!r}; "
        f"component matches={parity.get('force_component_matches')!r}."
    )


def static_force_moment_series(
    config: SectionConfig,
    axes: Matrix3,
    selected_result_sets: Sequence[Dict[str, Any]],
    log: LogFn = None,
    *,
    capture_nodal_vectors: bool = False,
    capture_animation_frames: Optional[bool] = None,
    animation_session: Optional[StaticAnimationSession] = None,
    animation_frame_sink: Optional[
        Callable[[StaticAnimationSession, List[int]], None]
    ] = None,
) -> Dict[str, Any]:
    import ansys.dpf.core as dpf

    phase_start = perf_counter()
    emit(log, f"Loading Static Structural RST once for {len(selected_result_sets)} set(s).")
    preflight_dpf_open(dpf, config.modal_rst, log=log)
    data_sources = dpf.DataSources(config.modal_rst)
    streams_container = create_streams_container(dpf, data_sources)
    try:
        model = dpf.Model(data_sources)
        result_names = result_info_names(model.metadata.result_info)
        require_element_nodal_force_result(
            rst_path=config.modal_rst,
            result_names=result_names,
        )
        if config.external_named_selection_path:
            element_scoping, element_name, available_named = resolve_external_element_scoping(
                dpf,
                model,
                config.external_named_selection_path,
                config.element_named_selection,
            )
        else:
            element_scoping, element_name, available_named = resolve_element_named_selection_scoping(
                dpf,
                model,
                data_sources,
                streams_container,
                config.element_named_selection,
            )
        reference_mesh = selected_element_mesh(model, element_scoping)
        mesh_config, origin_unit_conversion = config_with_origin_in_mesh_units(
            config,
            reference_mesh,
            log=log,
        )
        mesh_unit = str(getattr(reference_mesh, "unit", "") or "").strip()
        if not mesh_unit:
            raise RuntimeError(
                "The RST mesh must report a length unit before moving reference points "
                "can be supplied to DPF force_summation."
            )
        initial_element_scope, initial_node_scope, initial_side_info = construction_surface_scoping(
            dpf,
            model,
            element_scoping,
            mesh_config,
            axes,
            mesh=reference_mesh,
        )
        section_node_ids = selected_mesh_node_ids(reference_mesh)
        attachment_evidence: Dict[str, Any]
        tracking_node_ids: List[int] = []
        tracking_reference_coordinates: Dict[int, Vector] = {}
        if mesh_config.reference_frame_motion == "follow-geometry":
            override_name = mesh_config.reference_frame_attachment_selection.strip()
            if override_name:
                tracking_node_ids, attachment_evidence = resolve_reference_frame_attachment_nodes(
                    dpf,
                    model,
                    name=override_name,
                    external_named_selection_path=mesh_config.external_named_selection_path,
                )
                full_mesh = getattr(model.metadata, "meshed_region", None)
                full_mesh = full_mesh() if callable(full_mesh) else full_mesh
                tracking_reference_coordinates = mesh_node_coordinates_for_ids(
                    full_mesh,
                    tracking_node_ids,
                )
            else:
                tracking_node_ids = unique_element_node_ids(
                    reference_mesh,
                    initial_side_info.get("cut_element_ids", []),
                )
                attachment_evidence = {
                    "source": "local_section_cut_neighborhood",
                    "selection": element_name,
                    "entity": "INITIAL_CUT_ELEMENTS",
                    "entity_count": len(initial_side_info.get("cut_element_ids", [])),
                    "node_count": len(tracking_node_ids),
                    "node_ids_hash": stable_id_hash(tracking_node_ids),
                }
                tracking_reference_coordinates = mesh_node_coordinates_for_ids(
                    reference_mesh,
                    tracking_node_ids,
                )
        else:
            attachment_evidence = {
                "source": "none",
                "selection": "",
                "entity": "NONE",
                "entity_count": 0,
                "node_count": 0,
                "node_ids_hash": stable_id_hash([]),
            }

        displacement_node_ids = sorted(set(section_node_ids).union(tracking_node_ids))
        animation_warnings: List[str] = []
        if capture_animation_frames is None:
            capture_animation_frames = (
                capture_nodal_vectors and len(selected_result_sets) >= 2
            )
        owns_animation_session = animation_session is None
        if capture_animation_frames and animation_session is None:
            try:
                animation_session = create_static_animation_session(
                    mesh_config,
                    selected_result_sets,
                    mesh=reference_mesh,
                    element_scoping=element_scoping,
                    element_name=element_name,
                    available_named=available_named,
                    displacement_node_ids=displacement_node_ids,
                    tracking_node_ids=tracking_node_ids,
                    tracking_reference_coordinates=tracking_reference_coordinates,
                    attachment=attachment_evidence,
                    origin_unit_conversion=origin_unit_conversion,
                    signature_config=config,
                )
            except Exception as exc:
                warning = (
                    "Animation frame capture could not be prepared; extraction will "
                    f"continue and Play can reread displacement later. Raw error: {exc!r}"
                )
                animation_warnings.append(warning)
                emit(log, f"Warning: {warning}")
                animation_session = None
        result_units: Dict[str, Optional[str]] = {"force": None, "moment": None}
        static_results: List[StaticSetResult] = []
        last_detail: Optional[Dict[str, Any]] = None
        total_summation_seconds = 0.0
        for set_index, selected_set in enumerate(selected_result_sets):
            set_start = perf_counter()
            set_id = int(selected_set["id"])
            set_value = float(selected_set["value"])
            set_unit = selected_set.get("unit")
            emit(
                log,
                f"Processing static set {set_index + 1}/{len(selected_result_sets)} "
                f"— cumulative ID {set_id}.",
            )
            displacement_start = perf_counter()
            all_displacements, deformation = nodal_displacements_for_ids(
                dpf,
                data_sources,
                streams_container,
                displacement_node_ids,
                set_id,
                mesh_unit,
                log=log,
            )
            displacement_seconds = perf_counter() - displacement_start
            section_displacements = {
                node_id: all_displacements[node_id] for node_id in section_node_ids
            }
            deformed_mesh = mesh_with_nodal_displacements(
                reference_mesh,
                section_displacements,
                deformation,
                include_grid=False,
            )

            frame_start = perf_counter()
            if mesh_config.reference_frame_motion == "follow-geometry":
                current_tracking_coordinates = {
                    node_id: add_vectors(
                        tracking_reference_coordinates[node_id],
                        all_displacements[node_id],
                    )
                    for node_id in tracking_node_ids
                }
                frame = fit_geometry_following_frame(
                    tracking_reference_coordinates,
                    current_tracking_coordinates,
                    mesh_config.coordinate_system_origin,
                    mesh_config.coordinate_system_axes,
                    result_set_id=set_id,
                    result_value=set_value,
                    result_unit=set_unit,
                    attachment_source=attachment_evidence["source"],
                    attachment_selection=attachment_evidence["selection"],
                    warning_ratio=mesh_config.reference_frame_fit_warning_ratio,
                )
            else:
                frame = fixed_reference_frame(
                    mesh_config.coordinate_system_origin,
                    mesh_config.coordinate_system_axes,
                    result_set_id=set_id,
                    result_value=set_value,
                    result_unit=set_unit,
                )
            frame_seconds = perf_counter() - frame_start
            for warning in frame.warnings:
                emit(log, f"Warning: set {set_id}: {warning}")

            set_config = config_from_mapping(asdict(mesh_config))
            set_config.result_set_id = set_id
            set_config.coordinate_system_origin = list(frame.resolved_origin)
            set_config.coordinate_system_axes = {
                key: list(value) for key, value in frame.resolved_axes.items()
            }
            resolved_axes = validate_axes(set_config.coordinate_system_axes)
            scope_start = perf_counter()
            follows_geometry = (
                mesh_config.reference_frame_motion == "follow-geometry"
            )
            scoping_mesh = deformed_mesh if follows_geometry else reference_mesh
            filtered_elem_scope, node_scope, side_info = construction_surface_scoping(
                dpf,
                model,
                element_scoping,
                set_config,
                resolved_axes,
                mesh=scoping_mesh,
            )
            if not follows_geometry:
                side_info = side_filter_with_mesh_coordinates(
                    side_info,
                    deformed_mesh,
                    set_config.coordinate_system_origin,
                    axis_from_coordinate_system(
                        resolved_axes,
                        set_config.section_normal_axis,
                    ),
                    scoping_geometry_state="reference",
                )
            else:
                side_info["scoping_geometry_state"] = "deformed"
                side_info["coordinate_geometry_state"] = "deformed"
            deformation["scope_change"] = deformation_scope_change_evidence(
                initial_side_info,
                side_info,
            )
            deformation["scoping_geometry_state"] = (
                "deformed" if follows_geometry else "reference"
            )
            scope_seconds = perf_counter() - scope_start

            if set_index == 0:
                if follows_geometry:
                    emit(
                        log,
                        "Section scope follows the transported frame on the deformed mesh; "
                        "this is a moving-section result and is not the fixed Mechanical "
                        "Construction Surface definition.",
                    )
                else:
                    emit(
                        log,
                        "Section scope uses the initial/reference mesh to match a fixed "
                        "Mechanical Construction Surface; displaced node coordinates are "
                        "retained for result evidence and large-deflection moment arms.",
                    )

            if animation_session is not None:
                try:
                    animation_session.put_displacement_mapping(
                        set_index,
                        all_displacements,
                        deformation=deformation,
                        resolved_reference_frame=asdict(frame),
                    )
                    if animation_frame_sink is not None:
                        animation_frame_sink(animation_session, [set_index])
                except Exception as exc:
                    warning = (
                        f"Animation frame capture failed at set {set_id}; extraction will "
                        "continue and Play can reread displacement later. "
                        f"Raw error: {exc!r}"
                    )
                    animation_warnings.append(warning)
                    emit(log, f"Warning: {warning}")
                    if owns_animation_session:
                        animation_session.close()
                    animation_session = None

            moment_reference_xyz = list(frame.resolved_origin)
            if set_config.moment_reference_mode == "mechanical_probe_mesh_centroid":
                moment_reference_xyz = [
                    float(value) for value in side_info["moment_reference_centroid"]
                ]
            elif set_config.moment_reference_mode == "selected_side_node_centroid":
                moment_reference_xyz = [
                    float(value) for value in side_info["selected_node_centroid"]
                ]
            elif set_config.moment_reference_mode != "coordinate_system_origin":
                raise ValueError(
                    f"Unsupported moment_reference_mode: {set_config.moment_reference_mode!r}."
                )

            summation_terms = static_force_summation_terms(
                side_info,
                filtered_elem_scope,
                node_scope,
            )
            if len(summation_terms) > 1:
                emit(
                    log,
                    "Construction surface contains coordinate-coincident, node-disconnected "
                    f"interface sheets; combining {len(summation_terms)} independently "
                    "oriented element-nodal force terms.",
                )
            summation_start = perf_counter()
            if len(summation_terms) > 1:
                if any(
                    str(reference_mesh.elements.element_by_id(element_id).shape).lower()
                    != "solid"
                    for term in summation_terms
                    for element_id in term["element_ids"]
                ):
                    raise RuntimeError(
                        "Coordinate-coincident duplicate construction-surface sheets are "
                        "currently supported only for solid elements. Shell or beam scopes "
                        "can carry explicit nodal couples and require a separate supported "
                        "couple-moment reconstruction."
                    )
                interface_result = static_duplicate_interface_resultants(
                    dpf,
                    data_sources,
                    streams_container,
                    reference_mesh,
                    all_displacements,
                    set_id,
                    moment_reference_xyz,
                    summation_terms,
                    MECHANICAL_PROBE_FORCE_TYPE,
                )
                force = interface_result["force"]
                raw_dpf_moment_about_reference = interface_result[
                    "moment_about_reference"
                ]
                nodal_force_rows = interface_result["nodal_force_rows"]
                nodal_moment_rows = interface_result["nodal_moment_rows"]
                nodal_moment_output_available = True
                nodal_moment_capture_warning = None
                nodal_moment_output_status = interface_result[
                    "nodal_moment_output_status"
                ]
                term_resultants = interface_result["term_resultants"]
                aggregate_result_source = (
                    "dpf_element_nodal_signed_duplicate_interface"
                )
                result_units = complete_result_units(
                    {
                        "force": result_units["force"] or interface_result["force_unit"],
                        "moment": result_units["moment"] or interface_result["moment_unit"],
                    },
                    mesh_unit=mesh_unit,
                )
            else:
                term = summation_terms[0]
                term_role = str(term["role"])
                term_element_ids = [int(value) for value in term["element_ids"]]
                term_node_ids = [int(value) for value in term["node_ids"]]
                op = dpf.operators.averaging.force_summation()
                connect_pin(op.inputs.data_sources, data_sources)
                connect_optional_pin(op.inputs, "streams_container", streams_container)
                connect_pin(
                    op.inputs.time_scoping,
                    make_scoping(dpf, [set_id], dpf.locations.time_freq),
                )
                connect_pin(
                    op.inputs.nodal_scoping,
                    make_scoping(dpf, term_node_ids, dpf.locations.nodal),
                )
                connect_pin(
                    op.inputs.elemental_scoping,
                    make_scoping(dpf, term_element_ids, dpf.locations.elemental),
                )
                connect_pin(op.inputs.force_type, MECHANICAL_PROBE_FORCE_TYPE)
                connect_pin(
                    op.inputs.spoint,
                    summation_point_field(dpf, moment_reference_xyz, mesh_unit),
                )
                try:
                    force_fc = output_data(op.outputs.force_accumulation)
                    moment_fc = output_data(op.outputs.moment_accumulation)
                    force_field = field_by_time_id(force_fc, set_id)
                    moment_field = field_by_time_id(moment_fc, set_id)
                except Exception as exc:
                    raise RuntimeError(
                        build_force_summation_failure_message(
                            config=set_config,
                            result_names=result_names,
                            raw_element_count=len(object_ids(element_scoping)),
                            cut_element_count=len(term_element_ids),
                            side_node_count=len(term_node_ids),
                            modes_to_evaluate=1,
                            raw_error=exc,
                        )
                        + f"\n\nFailed Static Structural cumulative set ID {set_id}."
                    ) from exc

                field_units = result_units_from_fields(force_field, moment_field)
                result_units = complete_result_units(
                    {
                        "force": result_units["force"] or field_units.get("force"),
                        "moment": result_units["moment"] or field_units.get("moment"),
                    },
                    mesh_unit=mesh_unit,
                )
                force = field_vector(force_field)
                raw_dpf_moment_about_reference = field_vector(moment_field)
                term_resultants = [
                    {
                        "role": term_role,
                        "sign": 1.0,
                        "element_count": len(term_element_ids),
                        "node_count": len(term_node_ids),
                        "force_global": [float(value) for value in force],
                        "moment_about_reference_global": [
                            float(value) for value in raw_dpf_moment_about_reference
                        ],
                    }
                ]
                aggregate_result_source = "dpf_force_summation"
                try:
                    nodal_force_rows = field_vector_rows_by_id(
                        field_by_time_id(output_data(op.outputs.forces_on_nodes), set_id)
                    )
                except Exception as exc:
                    raise RuntimeError(
                        "Static Structural extraction produced aggregate resultants, but "
                        "DPF did not provide per-node forces required for audit evidence. "
                        f"Set {set_id}; term {term_role!r}; raw DPF error: {exc}"
                    ) from exc
                try:
                    nodal_moment_rows, nodal_moment_output_status = static_nodal_moment_rows(
                        output_data(op.outputs.moments_on_nodes),
                        set_id,
                        result_units.get("moment"),
                    )
                    nodal_moment_output_available = True
                    nodal_moment_capture_warning = None
                except Exception as exc:
                    raise RuntimeError(
                        "Static Structural extraction cannot reconstruct a Mechanical-"
                        "equivalent construction-surface moment because DPF did not provide "
                        "readable per-node moment/couple data. An empty moments_on_nodes "
                        "container is valid and is treated as zero couples, but evaluation "
                        f"failed for set {set_id}, term {term_role!r}. Raw DPF error: {exc}"
                    ) from exc
                del force_fc, moment_fc, op

            summation_seconds = perf_counter() - summation_start
            total_summation_seconds += summation_seconds
            raw_dpf_reference_global = force + raw_dpf_moment_about_reference
            selected_node_ids = [
                int(value) for value in side_info.get("selected_node_ids", [])
            ]
            side_info["force_summation_term_resultants"] = term_resultants
            side_info["aggregate_result_source"] = aggregate_result_source
            detail_signature_config = config_from_mapping(asdict(mesh_config))
            detail_signature_config.result_set_id = set_id
            set_signature = result_visualization_signature(
                detail_signature_config,
                mesh_unit=mesh_unit,
            )
            frame_dict = asdict(frame)
            section_geometry = projected_section_geometry_from_mesh(
                deformed_mesh,
                set_config,
                resolved_axes,
                side_info,
            )
            detail = {
                "analysis_mode": "static",
                "result_set_ids": [set_id],
                "selected_result_sets": [dict(selected_set)],
                "signature": set_signature,
                "signatures": [set_signature],
                "times": [set_value],
                "modal_coordinates": [[1.0]],
                "modes_used": 1,
                "mesh_unit": mesh_unit,
                "result_units": result_units,
                "resolved_reference_frames": [frame_dict],
                "moment_reference_xyz": moment_reference_xyz,
                "moment_reference_xyz_by_set": [moment_reference_xyz],
                "selected_node_coordinates": side_info.get("selected_node_coordinates", {}),
                "selected_node_coordinates_by_set": [
                    side_info.get("selected_node_coordinates", {})
                ],
                "selected_node_centroid": side_info.get("selected_node_centroid"),
                "nodal_force_modal_coefficients": {
                    node_id: [nodal_force_rows.get(node_id, [0.0, 0.0, 0.0])]
                    for node_id in selected_node_ids
                },
                "nodal_moment_modal_coefficients": {
                    node_id: [nodal_moment_rows.get(node_id, [0.0, 0.0, 0.0])]
                    for node_id in selected_node_ids
                },
                "nodal_moment_output_available": nodal_moment_output_available,
                "nodal_moment_capture_warning": nodal_moment_capture_warning,
                "nodal_moment_output_status": nodal_moment_output_status,
                "section_geometry": section_geometry,
                "aggregate_result_source": aggregate_result_source,
            }
            reconstructed = nodal_reconstructed_resultant_rows(detail)
            nodal_row = (
                reconstructed["global_rows"][0]
                if reconstructed and reconstructed.get("global_rows")
                else None
            )
            if nodal_row is None or len(nodal_row) < 6:
                raise RuntimeError(
                    "Static Structural extraction could not reconstruct a complete "
                    "Mechanical-equivalent construction-surface resultant from the "
                    f"per-node DPF output for set {set_id}."
                )
            parity = nodal_resultant_parity(
                raw_dpf_reference_global,
                nodal_row,
                nodal_moments_complete=nodal_moment_output_available,
            )
            require_static_nodal_force_match(parity, set_id)
            resultants = mechanical_equivalent_static_resultants(
                force,
                raw_dpf_moment_about_reference,
                nodal_row,
                moment_reference_xyz,
                resolved_axes,
                cross_product_moment_factor=float(reconstructed["moment_unit_factor"]),
            )
            global_origin = resultants["resultant_global_origin"]
            reference_global = resultants["resultant_reference_global"]
            local = resultants["resultant_local"]
            raw_dpf_global_origin = resultants["raw_dpf_resultant_global_origin"]
            raw_dpf_reference_global = resultants[
                "raw_dpf_resultant_reference_global"
            ]
            raw_dpf_local = resultants["raw_dpf_resultant_local"]
            detail.update(
                {
                    "resultants_global_origin": [global_origin],
                    "resultants_global": [global_origin],
                    "resultants_reference_global": [reference_global],
                    "resultants_local": [local],
                    "raw_dpf_resultants_global_origin": [raw_dpf_global_origin],
                    "raw_dpf_resultants_reference_global": [raw_dpf_reference_global],
                    "raw_dpf_resultants_local": [raw_dpf_local],
                }
            )
            detail["nodal_parity"] = parity
            warnings = list(frame.warnings)
            if parity.get("moment_matches") is not True:
                if aggregate_result_source == (
                    "dpf_element_nodal_signed_duplicate_interface"
                ):
                    warnings.append(
                        "Signed elemental-nodal duplicate-interface moment differs from "
                        "the Mechanical-equivalent nodal construction-surface moment. "
                        "The Mechanical-equivalent moment is used for results; the signed "
                        "duplicate-interface value is retained for audit."
                    )
                else:
                    warnings.append(
                        "Raw DPF moment_accumulation differs from the Mechanical-equivalent "
                        "nodal construction-surface moment. The Mechanical-equivalent "
                        "moment is used for results; the raw DPF value is retained for audit."
                    )
                emit(log, f"Warning: set {set_id}: {warnings[-1]}")
            static_results.append(
                StaticSetResult(
                    result_set_id=set_id,
                    result_value=set_value,
                    result_unit=set_unit,
                    reference_frame=frame_dict,
                    moment_reference_xyz=moment_reference_xyz,
                    resultant_global_origin=global_origin,
                    resultant_reference_global=reference_global,
                    resultant_local=local,
                    raw_dpf_resultant_global_origin=raw_dpf_global_origin,
                    raw_dpf_resultant_reference_global=raw_dpf_reference_global,
                    raw_dpf_resultant_local=raw_dpf_local,
                    scope=compact_side_filter_info(side_info),
                    section_geometry=section_geometry,
                    deformation=dict(deformation),
                    nodal_parity=parity,
                    visualization_signature=set_signature,
                    timings={
                        "displacement_seconds": displacement_seconds,
                        "frame_fit_seconds": frame_seconds,
                        "surface_filter_seconds": scope_seconds,
                        "force_summation_seconds": summation_seconds,
                        "total_seconds": perf_counter() - set_start,
                    },
                    warnings=warnings,
                )
            )
            if animation_session is not None:
                animation_record = animation_session.records[set_index]
                animation_record.primary_result_global_origin = list(global_origin)
                animation_record.primary_result_reference_global = list(reference_global)
                animation_record.moment_reference_xyz = list(moment_reference_xyz)
            if capture_nodal_vectors and set_index == len(selected_result_sets) - 1:
                last_detail = detail
            del deformed_mesh

        result_units = complete_result_units(result_units, mesh_unit=mesh_unit)
        if last_detail is not None:
            last_detail["result_units"] = result_units
        result_dicts = [asdict(item) for item in static_results]
        last_result = static_results[-1]
        result = {
            "static_set_results": result_dicts,
            "times": [item.result_value for item in static_results],
            "result_set_ids": [item.result_set_id for item in static_results],
            "resultants_global_origin": [item.resultant_global_origin for item in static_results],
            "resultants_global": [item.resultant_global_origin for item in static_results],
            "resultants_reference_global": [
                item.resultant_reference_global for item in static_results
            ],
            "resultants_local": [item.resultant_local for item in static_results],
            "raw_dpf_resultants_global_origin": [
                item.raw_dpf_resultant_global_origin for item in static_results
            ],
            "raw_dpf_resultants_reference_global": [
                item.raw_dpf_resultant_reference_global for item in static_results
            ],
            "raw_dpf_resultants_local": [
                item.raw_dpf_resultant_local for item in static_results
            ],
            "resolved_reference_frames": [item.reference_frame for item in static_results],
            "moment_reference_xyz_by_set": [
                item.moment_reference_xyz for item in static_results
            ],
            "signatures": [item.visualization_signature for item in static_results],
            "result_units": result_units,
            "mesh_unit": mesh_unit,
            "element_named_selection": element_name,
            "available_named_selections": available_named,
            "raw_element_count": len(object_ids(element_scoping)),
            "result_set_id": last_result.result_set_id,
            "geometry_state": "deformed",
            "deformation": last_result.deformation,
            "element_count": int(last_result.scope.get("cut_element_count", 0)),
            "surface_node_count": int(last_result.scope.get("selected_node_count", 0)),
            "side_filter": last_result.scope,
            "section_geometry": last_result.section_geometry,
            "moment_reference_xyz": last_result.moment_reference_xyz,
            "resolved_reference_frame": last_result.reference_frame,
            "initial_cut_element_count": len(object_ids(initial_element_scope)),
            "initial_side_node_count": len(object_ids(initial_node_scope)),
            "coordinate_system_origin_unit_conversion": origin_unit_conversion,
            "attachment": attachment_evidence,
            "force_type": MECHANICAL_PROBE_FORCE_TYPE,
            "aggregate_result_sources": [
                item.scope.get("aggregate_result_source") for item in static_results
            ],
            "force_summation_eval_seconds": total_summation_seconds,
            "elapsed_seconds": perf_counter() - phase_start,
            "_visualization_detail": last_detail,
            "animation_warnings": animation_warnings,
        }
        if animation_session is not None:
            animation_session.mark_complete()
            if animation_session.complete:
                result["_animation_session"] = animation_session
            elif owns_animation_session:
                animation_session.close()
        return result
    finally:
        try:
            streams_container.release_handles()
            emit(log, "Released DPF stream handles.")
        except Exception:
            pass


def nodal_resultant_parity(
    raw_dpf_reference_global: Sequence[float],
    mechanical_equivalent_reference_global: Optional[Sequence[float]],
    *,
    nodal_moments_complete: bool = True,
) -> Dict[str, Any]:
    raw_dpf = [float(value) for value in raw_dpf_reference_global[:6]]
    if (
        mechanical_equivalent_reference_global is None
        or len(mechanical_equivalent_reference_global) < 6
    ):
        return {
            "available": False,
            "primary_result_source": "mechanical_equivalent_nodal_reconstruction",
            "raw_dpf_resultant_reference_global": raw_dpf,
            "reason": "Per-node force/moment reconstruction was unavailable.",
        }
    mechanical_equivalent = [
        float(value) for value in mechanical_equivalent_reference_global[:6]
    ]
    delta = [mechanical_equivalent[index] - raw_dpf[index] for index in range(6)]

    def comparison(
        indices: Sequence[int],
    ) -> Tuple[bool, float, float, List[bool], List[float], List[float]]:
        error_norm = math.sqrt(sum(delta[index] ** 2 for index in indices))
        reference_norm = max(
            math.sqrt(sum(raw_dpf[index] ** 2 for index in indices)),
            math.sqrt(sum(mechanical_equivalent[index] ** 2 for index in indices)),
        )
        tolerance = 1.0e-9 + 1.0e-6 * reference_norm
        component_errors = [abs(delta[index]) for index in indices]
        component_tolerances = [
            1.0e-9
            + 1.0e-6
            * max(abs(raw_dpf[index]), abs(mechanical_equivalent[index]))
            for index in indices
        ]
        component_matches = [
            error <= component_tolerance
            for error, component_tolerance in zip(
                component_errors,
                component_tolerances,
            )
        ]
        return (
            error_norm <= tolerance and all(component_matches),
            error_norm,
            tolerance,
            component_matches,
            component_errors,
            component_tolerances,
        )

    (
        force_matches,
        force_error_norm,
        force_tolerance,
        force_component_matches,
        force_component_errors,
        force_component_tolerances,
    ) = comparison((0, 1, 2))
    (
        raw_moment_matches,
        moment_error_norm,
        moment_tolerance,
        moment_component_matches,
        moment_component_errors,
        moment_component_tolerances,
    ) = comparison((3, 4, 5))
    moment_matches: Optional[bool] = (
        raw_moment_matches if nodal_moments_complete else None
    )

    return {
        "available": True,
        "relative_tolerance": 1.0e-6,
        "absolute_tolerance": 1.0e-9,
        "force_matches": force_matches,
        "moment_matches": moment_matches,
        "moment_comparison_complete": bool(nodal_moments_complete),
        "force_error_norm": force_error_norm,
        "force_tolerance": force_tolerance,
        "force_component_matches": force_component_matches,
        "force_component_errors": force_component_errors,
        "force_component_tolerances": force_component_tolerances,
        "moment_error_norm": moment_error_norm,
        "moment_tolerance": moment_tolerance,
        "moment_component_matches": (
            moment_component_matches if nodal_moments_complete else None
        ),
        "moment_component_errors": moment_component_errors,
        "moment_component_tolerances": moment_component_tolerances,
        "primary_result_source": "mechanical_equivalent_nodal_reconstruction",
        "raw_dpf_resultant_reference_global": raw_dpf,
        "mechanical_equivalent_resultant_reference_global": mechanical_equivalent,
        "delta_mechanical_equivalent_minus_raw_dpf": delta,
    }


def _write_result_csv_stream(
    stream: Any,
    times: Sequence[float],
    global_rows: Sequence[Sequence[float]],
    local_rows: Sequence[Sequence[float]],
    result_units: Optional[Dict[str, Optional[str]]] = None,
    result_set_ids: Optional[Sequence[int]] = None,
) -> None:
    units = result_units or {}
    force_unit = units.get("force")
    moment_unit = units.get("moment")
    writer = csv.writer(stream)
    header = ["time_s"]
    if result_set_ids is not None:
        header.append("result_set_id")
    writer.writerow(
        header
        + [
            csv_result_header("fx_global", force_unit),
            csv_result_header("fy_global", force_unit),
            csv_result_header("fz_global", force_unit),
            csv_result_header("mx_global_about_global_origin", moment_unit),
            csv_result_header("my_global_about_global_origin", moment_unit),
            csv_result_header("mz_global_about_global_origin", moment_unit),
            csv_result_header("fx_local", force_unit),
            csv_result_header("fy_local", force_unit),
            csv_result_header("fz_local", force_unit),
            csv_result_header("mx_local_about_moment_reference", moment_unit),
            csv_result_header("my_local_about_moment_reference", moment_unit),
            csv_result_header("mz_local_about_moment_reference", moment_unit),
        ]
    )
    for row_index, time_value in enumerate(times):
        identity = [f"{time_value:.16g}"]
        if result_set_ids is not None:
            identity.append(str(int(result_set_ids[row_index])))
        writer.writerow(
            identity
            + [f"{value:.16g}" for value in global_rows[row_index]]
            + [f"{value:.16g}" for value in local_rows[row_index]]
        )


def write_result_csv(
    path: str,
    times: Sequence[float],
    global_rows: Sequence[Sequence[float]],
    local_rows: Sequence[Sequence[float]],
    result_units: Optional[Dict[str, Optional[str]]] = None,
    result_set_ids: Optional[Sequence[int]] = None,
) -> None:
    target = Path(path)
    ensure_output_csv_can_be_replaced(str(target))
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            newline="",
            encoding="utf-8",
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            _write_result_csv_stream(
                stream,
                times,
                global_rows,
                local_rows,
                result_units,
                result_set_ids,
            )

        ensure_output_csv_can_be_replaced(str(target))
        os.replace(temp_path, target)
        temp_path = None
    except PermissionError as exc:
        raise PermissionError(output_csv_unavailable_message(str(target))) from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass


def write_summary(path: str, payload: Dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def validate_paths(config: SectionConfig) -> None:
    if not config.modal_rst:
        raise ValueError("RST path is empty.")
    if config.analysis_mode == "modal" and not config.mcf:
        raise ValueError("Transient MCF path is empty.")
    if (
        config.analysis_mode == "static"
        and config.static_set_scope == "single"
        and config.result_set_id is None
    ):
        raise ValueError("Static set scope Single requires a result-set ID.")
    if config.analysis_mode == "static" and config.static_set_scope == "range":
        if config.result_set_range_start is None or config.result_set_range_end is None:
            raise ValueError("Static set scope Range requires Start set and End set.")
    if not config.out_csv:
        raise ValueError("Output CSV path is empty.")
    paths = [("RST", config.modal_rst)]
    if config.analysis_mode == "modal":
        paths.append(("Transient MCF", config.mcf))
    if config.external_named_selection_path:
        paths.append(("External named selection", config.external_named_selection_path))
    for label, path in paths:
        if not Path(path).is_file():
            raise FileNotFoundError(f"{label} does not exist: {path}")


def _extract_static_section_resultants(
    config: SectionConfig,
    axes: Matrix3,
    modal_metadata: ModalRstMetadata,
    *,
    metadata_elapsed: float,
    total_start: float,
    summary_path: str,
    log: LogFn,
    capture_visualization_vectors: bool,
) -> Dict[str, Any]:
    selected_ids = resolve_static_result_set_ids(config, modal_metadata.result_sets)
    options_by_id = {
        int(item["id"]): dict(item) for item in modal_metadata.result_sets
    }
    selected_result_sets = [options_by_id[set_id] for set_id in selected_ids]
    emit(
        log,
        "Selected static result sets: "
        + ", ".join(str(set_id) for set_id in selected_ids)
        + f" ({config.static_set_scope}).",
    )
    series = static_force_moment_series(
        config,
        axes,
        selected_result_sets,
        log,
        capture_nodal_vectors=capture_visualization_vectors,
    )
    visualization_detail = series.pop("_visualization_detail", None)
    animation_session = series.pop("_animation_session", None)
    result_units = series["result_units"]
    times = series["times"]
    global_rows = series["resultants_global_origin"]
    reference_rows = series["resultants_reference_global"]
    local_rows = series["resultants_local"]
    emit(log, f"Writing CSV: {config.out_csv}")
    write_result_csv(
        config.out_csv,
        times,
        global_rows,
        local_rows,
        result_units,
        selected_ids,
    )
    csv_size = Path(config.out_csv).stat().st_size
    total_elapsed = perf_counter() - total_start
    last_set = selected_result_sets[-1]
    last_result = series["static_set_results"][-1]
    nodal_parity = last_result.get("nodal_parity")
    summary = {
        "ok": True,
        "analysis_mode": "static",
        "static_set_scope": config.static_set_scope,
        "selected_result_set": (
            selected_result_sets[0] if len(selected_result_sets) == 1 else None
        ),
        "selected_result_sets": selected_result_sets,
        "result_set_ids": selected_ids,
        "geometry_state": "deformed",
        "deformation": last_result.get("deformation"),
        "resolved_reference_frame": last_result.get("reference_frame"),
        "resolved_reference_frames": series["resolved_reference_frames"],
        "nodal_parity": nodal_parity,
        "nodal_parity_by_set": [
            item.get("nodal_parity") for item in series["static_set_results"]
        ],
        "metadata_only_load": True,
        "method": (
            "standalone PyDPF sequential static construction-surface extraction: "
            "DPF force_summation for ordinary cuts or signed elemental-nodal "
            "aggregation for duplicate interface sheets, with Mechanical-equivalent "
            "deformed-node r x F and supported explicit nodal couples about each "
            "resolved reference point"
        ),
        "config": asdict(config),
        "modal_rst": config.modal_rst,
        "mcf": "",
        "out_csv": config.out_csv,
        "out_csv_mb": csv_size / 1000000.0,
        "summary_json": summary_path,
        "time_point_count": len(times),
        "modes_used": 0,
        "modal_sets_available": modal_metadata.modal_set_count,
        "modes_evaluated": 0,
        "modes_in_modal_rst": 0,
        "modes_in_mcf": 0,
        "skip_first_modes": 0,
        "skipped_mcf_modes": 0,
        "mcf_modes_after_skip": 0,
        "modal_sets_after_skip": 0,
        "modal_summation_batch_size": None,
        "modal_summation_batch_count": None,
        "ignored_mcf_modes": 0,
        "selected_named_selection_count": series.get("raw_element_count"),
        "timings": {
            "metadata_load_seconds": metadata_elapsed,
            "mcf_parse_seconds": 0.0,
            "dpf_force_summation_seconds": series.get("elapsed_seconds"),
            "modal_multiplication_seconds": 0.0,
            "total_seconds": total_elapsed,
            "per_set": [
                item.get("timings") for item in series["static_set_results"]
            ],
        },
        "result_units": result_units,
        "dpf_force_summation": series,
        "static_set_results": series["static_set_results"],
        "max_abs_resultant_global": max_abs_by_component(global_rows),
        "max_abs_resultant_global_origin": max_abs_by_component(global_rows),
        "max_abs_resultant_local": max_abs_by_component(local_rows),
        "max_abs_resultant_reference_global": max_abs_by_component(reference_rows),
    }
    emit(log, f"Writing summary: {summary_path}")
    write_summary(summary_path, summary)
    if capture_visualization_vectors:
        visualization_result_data: Dict[str, Any] = {
            "analysis_mode": "static",
            "static_set_scope": config.static_set_scope,
            "selected_result_set": (
                selected_result_sets[0] if len(selected_result_sets) == 1 else last_set
            ),
            "selected_result_sets": selected_result_sets,
            "result_set_ids": selected_ids,
            "times": times,
            "mesh_unit": series.get("mesh_unit"),
            "result_units": result_units,
            "resultants_global_origin": global_rows,
            "resultants_global": global_rows,
            "resultants_reference_global": reference_rows,
            "resultants_local": local_rows,
            "raw_dpf_resultants_global_origin": series.get(
                "raw_dpf_resultants_global_origin", []
            ),
            "raw_dpf_resultants_reference_global": series.get(
                "raw_dpf_resultants_reference_global", []
            ),
            "raw_dpf_resultants_local": series.get("raw_dpf_resultants_local", []),
            "resolved_reference_frames": series["resolved_reference_frames"],
            "moment_reference_xyz_by_set": series["moment_reference_xyz_by_set"],
            "signatures": series["signatures"],
            "signature": series["signatures"][-1],
            "static_set_results": series["static_set_results"],
            "nodal_parity": nodal_parity,
            "detail_time_index": len(selected_ids) - 1,
            "detail_result_set_id": selected_ids[-1],
        }
        if visualization_detail:
            for key in (
                "selected_node_coordinates",
                "selected_node_centroid",
                "nodal_force_modal_coefficients",
                "nodal_moment_modal_coefficients",
                "nodal_moment_output_available",
                "nodal_moment_capture_warning",
                "nodal_moment_output_status",
                "section_geometry",
            ):
                visualization_result_data[key] = visualization_detail.get(key)
        summary["_visualization_result_data"] = visualization_result_data
    if animation_session is not None:
        summary["_animation_session"] = animation_session
    emit(log, f"Extraction finished in {format_seconds(total_elapsed)}.")
    return summary


def extract_section_resultants(
    config: SectionConfig,
    log: LogFn = None,
    *,
    capture_visualization_vectors: bool = False,
) -> Dict[str, Any]:
    total_start = perf_counter()
    config = config_from_mapping(asdict(config))
    validate_paths(config)
    ensure_output_csv_can_be_replaced(config.out_csv)
    axes = validate_axes(config.coordinate_system_axes)
    summary_path = default_summary_path(config.out_csv)
    emit(log, "Starting standalone DPF section resultant extraction.")
    emit(log, f"Analysis mode: {config.analysis_mode}.")
    emit(log, f"RST path: {config.modal_rst}")
    if config.analysis_mode == "modal":
        emit(log, f"Transient MCF path: {config.mcf}")
    emit(log, f"Output CSV path: {config.out_csv}")
    emit(
        log,
        "Extraction settings: "
        f"named_selection={config.element_named_selection!r}, "
        f"external_selection={config.external_named_selection_path or 'none'}, "
        f"normal={config.section_normal_axis}, side={config.extraction_side}, "
        f"moment_reference={config.moment_reference_mode}, "
        f"frame_motion={config.reference_frame_motion}, "
        f"static_set_scope={config.static_set_scope}, "
        f"force_type={MECHANICAL_PROBE_FORCE_TYPE if config.analysis_mode == 'static' else config.force_type}, "
        f"modal_batch_size={config.modal_summation_batch_size}, "
        f"skip_first_modes={config.skip_first_modes}.",
    )
    metadata_start = perf_counter()
    modal_metadata = load_modal_rst_metadata(config.modal_rst, log=log)
    metadata_elapsed = perf_counter() - metadata_start
    emit(
        log,
        "Metadata stage complete in "
        f"{format_seconds(metadata_elapsed)}: "
        f"{len(modal_metadata.named_selection_names)} named selection(s), "
        f"{modal_metadata.modal_set_count} modal/time set(s), "
        f"{len(modal_metadata.result_names)} result name(s).",
    )

    if config.analysis_mode == "static":
        return _extract_static_section_resultants(
            config,
            axes,
            modal_metadata,
            metadata_elapsed=metadata_elapsed,
            total_start=total_start,
            summary_path=summary_path,
            log=log,
            capture_visualization_vectors=capture_visualization_vectors,
        )

    modal_sets_available = int(modal_metadata.modal_set_count or 0)
    selected_result_set: Optional[Dict[str, Any]] = None
    if config.analysis_mode == "static":
        selected_result_set = next(
            (
                item
                for item in modal_metadata.result_sets
                if int(item.get("id", 0)) == int(config.result_set_id or 0)
            ),
            None,
        )
        if selected_result_set is None:
            available_ids = [int(item.get("id", 0)) for item in modal_metadata.result_sets]
            raise ValueError(
                f"Static result-set ID {config.result_set_id} is unavailable; "
                f"select one of {available_ids or 'the cumulative IDs reported by the RST'}."
            )
        times = [float(selected_result_set["value"])]
        modal_coordinates = [[1.0]]
        mcf_elapsed = 0.0
        modes_in_mcf = 0
        skip_first_modes = 0
        mcf_modes_after_skip = 1
        modal_sets_after_skip = modal_sets_available
        requested_coefficient_modes = 1
        emit(
            log,
            "Selected static result set: "
            f"{selected_result_set['label']}.",
        )
    else:
        emit(log, f"Parsing transient MCF: {config.mcf}")
        mcf_start = perf_counter()
        times, modal_coordinates = parse_mcf(config.mcf)
        mcf_elapsed = perf_counter() - mcf_start
        modes_in_mcf = len(modal_coordinates[0]) if modal_coordinates else 0
        emit(
            log,
            "MCF parse complete in "
            f"{format_seconds(mcf_elapsed)}: {len(times)} time point(s), "
            f"{modes_in_mcf} modal coordinate(s) per point.",
        )
        skip_first_modes = int(config.skip_first_modes)
        if skip_first_modes >= modes_in_mcf:
            raise ValueError(
                f"Skip first modes ({skip_first_modes}) leaves no MCF modal coordinate "
                f"column to evaluate; the MCF has {modes_in_mcf} modal coordinate(s)."
            )
        if modal_sets_available > 0 and skip_first_modes >= modal_sets_available:
            raise ValueError(
                f"Skip first modes ({skip_first_modes}) leaves no modal RST set to evaluate; "
                f"the modal RST reports {modal_sets_available} modal/time set(s)."
            )
        if skip_first_modes:
            emit(
                log,
                f"Skipping first {skip_first_modes} mode(s): MCF modal coordinate "
                f"column(s) 1-{skip_first_modes} and RST modal set ID(s) 1-{skip_first_modes}.",
            )
        mcf_modes_after_skip = modes_in_mcf - skip_first_modes
        modal_sets_after_skip = (
            max(0, modal_sets_available - skip_first_modes)
            if modal_sets_available > 0
            else 0
        )
        requested_coefficient_modes = mcf_modes_after_skip
        if modal_sets_available > 0 and mcf_modes_after_skip > modal_sets_after_skip:
            requested_coefficient_modes = modal_sets_after_skip
            emit(
                log,
                "Warning: MCF has "
                f"{mcf_modes_after_skip} modal coordinate(s) per point after skipping "
                f"{skip_first_modes}, but the modal RST reports {modal_sets_after_skip} "
                "remaining modal/time set(s). Extra MCF "
                "modal coordinate column(s) will be ignored.",
            )
    coefficient_kwargs: Dict[str, Any] = {"max_modes": requested_coefficient_modes}
    if capture_visualization_vectors or config.analysis_mode == "static":
        coefficient_kwargs["capture_nodal_vectors"] = True
    coefficients, coefficient_info = modal_force_moment_coefficients(
        config,
        axes,
        log,
        **coefficient_kwargs,
    )
    visualization_vector_data = coefficient_info.pop("_visualization_vector_data", None)
    moment_reference_xyz = vector3(
        coefficient_info.get("moment_reference_xyz")
        or coefficient_info.get("coordinate_system_origin")
        or config.coordinate_system_origin,
        "moment_reference_xyz",
    )
    coefficient_info["moment_reference_xyz"] = moment_reference_xyz
    n_modes = min(len(coefficients), mcf_modes_after_skip)
    if n_modes <= 0:
        raise ValueError("No common modal coordinates/coefficient modes were available.")
    if n_modes < len(coefficients) or n_modes < mcf_modes_after_skip:
        emit(
            log,
            f"Warning: using {n_modes} common modes; modal RST has {len(coefficients)}, "
            f"MCF has {mcf_modes_after_skip} after skipping {skip_first_modes}.",
        )

    if config.analysis_mode == "static":
        emit(log, "Using the selected static result-set resultant without modal scaling.")
    else:
        emit(
            log,
            f"Multiplying {len(modal_coordinates)} MCF row(s) by {n_modes} modal "
            "force/moment coefficient row(s).",
        )
    multiplication_start = perf_counter()
    resultants_global_origin: List[List[float]] = []
    resultants_global: List[List[float]] = []
    resultants_reference_global: List[List[float]] = []
    resultants_local: List[List[float]] = []
    for row in modal_coordinates:
        effective_row = row[skip_first_modes : skip_first_modes + n_modes]
        global_origin_row = []
        for component_index in range(6):
            value = 0.0
            for mode_index in range(n_modes):
                value += (
                    effective_row[mode_index]
                    * coefficients[mode_index][component_index]
                )
            global_origin_row.append(value)
        resultants_global_origin.append(global_origin_row)
        reference_global_row = resultant_about_reference(
            global_origin_row,
            moment_reference_xyz,
        )
        resultants_global.append(global_origin_row)
        resultants_reference_global.append(reference_global_row)
        resultants_local.append(rotate_to_local(reference_global_row, axes))
    multiplication_elapsed = perf_counter() - multiplication_start
    emit(
        log,
        (
            "Static resultant transform complete in "
            if config.analysis_mode == "static"
            else "Modal-coordinate multiplication complete in "
        )
        + format_seconds(multiplication_elapsed)
        + ".",
    )

    emit(log, f"Writing CSV: {config.out_csv}")
    result_units = coefficient_info.get("result_units") or {}
    visualization_result_data = None
    if visualization_vector_data is not None:
        visualization_result_data = {
            "analysis_mode": config.analysis_mode,
            "selected_result_set": selected_result_set,
            "signature": coefficient_info.get("result_signature")
            or result_visualization_signature(config),
            "times": [float(value) for value in times],
            "modal_coordinates": [
                [
                    float(value)
                    for value in row[skip_first_modes : skip_first_modes + n_modes]
                ]
                for row in modal_coordinates
            ],
            "modes_used": n_modes,
            "mesh_unit": coefficient_info.get("mesh_unit"),
            "result_units": result_units,
            "resultants_global_origin": resultants_global_origin,
            "resultants_global": resultants_global,
            "resultants_reference_global": resultants_reference_global,
            "resultants_local": resultants_local,
            **visualization_vector_data,
        }
    nodal_parity = None
    if config.analysis_mode == "static":
        reconstructed = nodal_reconstructed_resultant_rows(visualization_result_data)
        nodal_row = (
            reconstructed["global_rows"][0]
            if reconstructed and reconstructed.get("global_rows")
            else None
        )
        nodal_parity = nodal_resultant_parity(
            resultants_reference_global[0],
            nodal_row,
            nodal_moments_complete=bool(
                visualization_result_data
                and visualization_result_data.get("nodal_moment_output_available")
            ),
        )
        coefficient_info["nodal_parity"] = nodal_parity
        if visualization_result_data is not None:
            visualization_result_data["nodal_parity"] = nodal_parity
        if nodal_parity.get("available") and (
            nodal_parity.get("force_matches") is not True
            or nodal_parity.get("moment_matches") is not True
        ):
            emit(
                log,
                "Warning: the Mechanical-equivalent nodal construction-surface "
                "resultant differs from raw DPF force_summation. Comparison evidence "
                "was saved in the summary. "
                "Delta="
                f"{nodal_parity['delta_mechanical_equivalent_minus_raw_dpf']}.",
            )
    write_result_csv(
        config.out_csv,
        times,
        resultants_global,
        resultants_local,
        result_units,
    )
    csv_size = Path(config.out_csv).stat().st_size
    emit(log, f"CSV written: {config.out_csv} ({format_bytes(csv_size)}).")
    total_elapsed = perf_counter() - total_start
    summary = {
        "ok": True,
        "analysis_mode": config.analysis_mode,
        "selected_result_set": selected_result_set,
        "geometry_state": coefficient_info.get("geometry_state", "reference"),
        "deformation": coefficient_info.get("deformation"),
        "nodal_parity": nodal_parity,
        "metadata_only_load": True,
        "method": (
            "standalone PyDPF one-set static force_summation with selected-set deformed-mesh construction-surface cut scoping"
            if config.analysis_mode == "static"
            else "standalone PyDPF force_summation + MSUP MCF modal-coordinate multiplication with construction-surface cut scoping"
        ),
        "config": asdict(config),
        "modal_rst": config.modal_rst,
        "mcf": config.mcf if config.analysis_mode == "modal" else "",
        "out_csv": config.out_csv,
        "out_csv_mb": csv_size / 1000000.0,
        "summary_json": summary_path,
        "time_point_count": len(times),
        "modes_used": n_modes,
        "modal_sets_available": coefficient_info.get(
            "modal_sets_available",
            modal_metadata.modal_set_count,
        ),
        "modes_evaluated": coefficient_info.get("modes_evaluated", len(coefficients)),
        "modes_in_modal_rst": coefficient_info.get("modal_sets_available", len(coefficients)),
        "modes_in_mcf": modes_in_mcf,
        "skip_first_modes": skip_first_modes,
        "skipped_mcf_modes": skip_first_modes,
        "mcf_modes_after_skip": mcf_modes_after_skip,
        "modal_sets_after_skip": modal_sets_after_skip,
        "modal_summation_batch_size": coefficient_info.get(
            "modal_summation_batch_size",
            config.modal_summation_batch_size,
        ),
        "modal_summation_batch_count": coefficient_info.get("modal_summation_batch_count"),
        "ignored_mcf_modes": max(0, mcf_modes_after_skip - n_modes),
        "selected_named_selection_count": coefficient_info.get("raw_element_count"),
        "timings": {
            "metadata_load_seconds": metadata_elapsed,
            "mcf_parse_seconds": mcf_elapsed,
            "dpf_force_summation_seconds": coefficient_info.get("elapsed_seconds"),
            "modal_multiplication_seconds": multiplication_elapsed,
            "total_seconds": total_elapsed,
        },
        "result_units": result_units,
        "dpf_force_summation": coefficient_info,
        "max_abs_resultant_global": max_abs_by_component(resultants_global),
        "max_abs_resultant_global_origin": max_abs_by_component(
            resultants_global_origin
        ),
        "max_abs_resultant_local": max_abs_by_component(resultants_local),
        "max_abs_resultant_reference_global": max_abs_by_component(
            resultants_reference_global
        ),
    }
    emit(log, f"Writing summary: {summary_path}")
    write_summary(summary_path, summary)
    emit(log, f"Summary written: {summary_path}.")
    if capture_visualization_vectors and visualization_result_data is not None:
        summary["_visualization_result_data"] = visualization_result_data
    emit(log, f"Extraction finished in {format_seconds(total_elapsed)}.")
    return summary
