# File: app/dpf_loader.py
"""
Headless DPF (PyDPF / ansys-dpf-core) loader for the Strain Gage Positioning tool.

Reads Ansys ``.rst`` result files directly and produces the SAME data contract
that :func:`computation.load_data` yields from a text file::

    (nodes, coords, strain_tensors)

    nodes          : np.ndarray[int]      node IDs (row-aligned with coords)
    coords         : np.ndarray (N, 3)    node coordinates in MILLIMETRES
    strain_tensors : dict[int, np.ndarray (N, 3)]
                     one entry per requested result set ("load case"); each row is
                     [exx, eyy, gamma_xy] in MICROSTRAIN (engineering shear).

That lets the analysis engine consume ``.rst`` input with no other changes.

There are deliberately NO Qt imports here: this is the model layer and must stay
unit-testable headless. The Qt selection dialog lives in ``dpf_dialog.py``.

Conventions (verified against the repo's embedded extractor
``get_local_strains_and_SG_geo_data_around_each_SG_grid_dpf.py``):
  * DPF ``elastic_strain`` returns 6 components ordered [XX, YY, ZZ, XY, YZ, XZ].
  * The XY component is the ENGINEERING shear strain (gamma_xy); this matches the
    transform used by :func:`computation.compute_normal_strains`.
  * Strains in the ``.rst`` are dimensionless; multiplied by 1e6 -> microstrain.
  * The nodal strain field need NOT cover every mesh node, and its node ordering
    need NOT match the mesh coordinate field, so coordinates are joined on node ID.
"""
from __future__ import annotations

import numpy as np

# Map a DPF mesh length unit to a millimetre scale factor.
_LENGTH_TO_MM = {
    "m": 1000.0, "meter": 1000.0, "metre": 1000.0,
    "mm": 1.0, "millimeter": 1.0, "millimetre": 1.0,
    "cm": 10.0, "centimeter": 10.0, "centimetre": 10.0,
    "um": 1.0e-3, "micrometer": 1.0e-3, "micrometre": 1.0e-3,
    "in": 25.4, "inch": 25.4,
    "ft": 304.8, "foot": 304.8,
}

_MICROSTRAIN = 1.0e6
# DPF tensor component indices we keep: XX, YY, XY (engineering shear).
_KEEP_COMPONENTS = [0, 1, 3]


def dpf_available() -> bool:
    """Return True if ansys-dpf-core can be imported (does not start a server)."""
    try:
        import ansys.dpf.core  # noqa: F401
        return True
    except Exception:
        return False


def _require_dpf():
    try:
        import ansys.dpf.core as dpf
        return dpf
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "ansys-dpf-core is not available, so .rst files cannot be read "
            "directly. Install ansys-dpf-core (with an Ansys/DPF server) or use "
            "the text-file loader instead.\n\nDetails: {0}".format(exc)
        )


def _stress_evaluation_shell_element_ids(dpf, data_sources):
    """Return SHELL181 element IDs whose KEYOPT(1) is evaluation-only (2)."""
    def _property(name):
        return dpf.operators.metadata.mesh_property_provider(
            data_sources=data_sources,
            property_name=name,
        ).outputs.property_as_property_field()

    element_types = _property("apdl_element_type")
    keyopt_1 = _property("keyopt_1")
    keyopts_by_id = {
        int(element_id): int(value)
        for element_id, value in zip(keyopt_1.scoping.ids, np.asarray(keyopt_1.data).reshape(-1))
    }
    return np.asarray([
        int(element_id)
        for element_id, element_type in zip(
            element_types.scoping.ids, np.asarray(element_types.data).reshape(-1)
        )
        if int(element_type) == 181 and keyopts_by_id.get(int(element_id)) == 2
    ], dtype=np.int64)


def _length_scale_to_mm(unit) -> float:
    if not unit:
        return 1.0
    return _LENGTH_TO_MM.get(str(unit).strip().lower(), 1.0)


def parse_set_ids(text, n_sets):
    """Parse a user set-id string into a sorted, unique list of 1-based set ids.

    Supports ``"all"``, ``"last"``, comma lists (``"1,3,5"``) and ranges
    (``"1-4"``, ``"2-last"``). Returns ``[n_sets]`` (the last set) when nothing
    valid is parsed.
    """
    n_sets = int(n_sets)
    if n_sets < 1:
        return []
    last = n_sets
    s = str(text or "").strip().lower()
    if s in ("", "all", "*"):
        return list(range(1, n_sets + 1))

    def _tok(t):
        t = t.strip()
        return last if t == "last" else int(float(t))

    ids = []
    for part in s.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part and not part.startswith("-"):
                a, b = part.split("-", 1)
                start, stop = _tok(a), _tok(b)
                step = 1 if stop >= start else -1
                ids.extend(range(start, stop + step, step))
            else:
                ids.append(_tok(part))
        except Exception:
            continue

    seen, out = set(), []
    for v in ids:
        if 1 <= v <= n_sets and v not in seen:
            seen.add(v)
            out.append(v)
    return out or [last]


def inspect_rst(rst_path):
    """Open a ``.rst`` and return lightweight metadata for the import dialog.

    Returns a dict with keys: ``named_selections`` (list[str]), ``n_sets`` (int),
    ``times`` (list[float]), ``unit`` (str), ``n_nodes`` (int), and
    ``stress_evaluation_shell_count`` (int).
    """
    dpf = _require_dpf()
    model = dpf.Model(str(rst_path))
    meta = model.metadata
    mesh = meta.meshed_region
    try:
        names = [str(n) for n in meta.available_named_selections]
    except Exception:
        names = []
    tfs = meta.time_freq_support
    try:
        n_sets = int(tfs.n_sets)
    except Exception:
        n_sets = 1
    try:
        times = np.asarray(tfs.time_frequencies.data).astype(float).tolist()
    except Exception:
        times = []
    try:
        n_nodes = int(len(mesh.nodes.scoping.ids))
    except Exception:
        n_nodes = 0
    try:
        evaluation_shell_count = int(len(_stress_evaluation_shell_element_ids(
            dpf, dpf.DataSources(str(rst_path))
        )))
    except Exception:
        evaluation_shell_count = 0
    return {
        "named_selections": names,
        "n_sets": n_sets,
        "times": times,
        "unit": str(getattr(mesh, "unit", "") or ""),
        "n_nodes": n_nodes,
        "stress_evaluation_shell_count": evaluation_shell_count,
    }


def _scoping_for_named_selection(dpf, data_sources, model, name, location):
    """Return a mesh scoping for ``name`` at ``location``.

    Prefers the ``scoping.on_named_selection`` operator with a forced location
    so face/node/element components can be resolved consistently. Falls back to
    the model metadata accessor for older runtimes.
    """
    try:
        op = dpf.operators.scoping.on_named_selection(
            requested_location=str(location),
            named_selection_name=str(name),
            data_sources=data_sources,
        )
        return op.outputs.mesh_scoping()
    except Exception:
        pass
    try:
        return model.metadata.named_selection(str(name))
    except Exception as exc:
        raise ValueError(
            "Named selection '{0}' could not be resolved.\nDetails: {1}".format(name, exc)
        )


def _nodal_scoping_for_named_selection(dpf, data_sources, model, name):
    """Return a Nodal mesh scoping for ``name``."""
    return _scoping_for_named_selection(dpf, data_sources, model, name, "Nodal")


def _elemental_scoping_for_named_selection(dpf, data_sources, model, name):
    """Return an Elemental mesh scoping for ``name``."""
    return _scoping_for_named_selection(dpf, data_sources, model, name, "Elemental")


def _indices_for_ids(all_ids, selected_ids):
    all_ids = np.asarray(all_ids, dtype=np.int64)
    selected_ids = np.asarray(selected_ids, dtype=np.int64)
    if all_ids.size == 0 or selected_ids.size == 0:
        return np.asarray([], dtype=int)
    order = np.argsort(all_ids)
    sorted_ids = all_ids[order]
    pos = np.searchsorted(sorted_ids, selected_ids)
    valid = pos < len(sorted_ids)
    pos_valid = pos[valid]
    selected_valid = selected_ids[valid]
    matches = sorted_ids[pos_valid] == selected_valid
    return order[pos_valid[matches]].astype(int)


def _cell_indices_touching_points(grid, point_indices, require_all=True):
    selected = {int(i) for i in point_indices}
    if not selected:
        return np.asarray([], dtype=int)
    cells = []
    for cell_index in range(int(grid.n_cells)):
        try:
            point_ids = list(grid.get_cell(cell_index).point_ids)
        except Exception:
            continue
        if not point_ids:
            continue
        if require_all:
            keep = all(int(pid) in selected for pid in point_ids)
        else:
            keep = any(int(pid) in selected for pid in point_ids)
        if keep:
            cells.append(cell_index)
    return np.asarray(cells, dtype=int)


def _extract_surface(dataset):
    try:
        surface = dataset.extract_surface(algorithm="dataset_surface")
    except TypeError:
        surface = dataset.extract_surface()
    return surface.compute_normals(
        point_normals=True,
        cell_normals=True,
        consistent_normals=True,
        auto_orient_normals=False,
        inplace=False,
    )


def load_rst_surface_mesh(
    rst_path,
    named_selection=None,
    ignore_stress_evaluation_shells=False,
    result_node_ids=None,
):
    """Extract a PyVista surface mesh for a named selection in millimetres.

    Returns a dict containing ``surface`` (``pyvista.PolyData``), selected node
    and element ids, mesh unit, and the resolved named selection label. The
    surface includes ``Normals`` in point data for local gage-frame placement.
    When evaluation-only shells are ignored, their cells and any remaining
    cells without complete result-node coverage are removed.
    """
    dpf = _require_dpf()

    rst_path = str(rst_path)
    data_sources = dpf.DataSources(rst_path)
    model = dpf.Model(rst_path)
    mesh = model.metadata.meshed_region
    scale = _length_scale_to_mm(getattr(mesh, "unit", None))

    grid = mesh.grid.copy()
    if scale != 1.0:
        grid.points = np.asarray(grid.points, dtype=float) * scale

    node_ids = np.asarray(mesh.nodes.scoping.ids, dtype=np.int64)
    element_ids = np.asarray(mesh.elements.scoping.ids, dtype=np.int64)
    if len(node_ids) == int(grid.n_points):
        grid.point_data["DPFNodeId"] = node_ids
    if len(element_ids) == int(grid.n_cells):
        grid.cell_data["DPFElementId"] = element_ids

    selected_node_ids = np.asarray([], dtype=np.int64)
    selected_element_ids = np.asarray([], dtype=np.int64)
    cell_indices = None
    selected = grid

    if named_selection:
        try:
            node_scoping = _nodal_scoping_for_named_selection(
                dpf, data_sources, model, named_selection
            )
            selected_node_ids = np.asarray(node_scoping.ids, dtype=np.int64)
        except Exception:
            selected_node_ids = np.asarray([], dtype=np.int64)

        try:
            element_scoping = _elemental_scoping_for_named_selection(
                dpf, data_sources, model, named_selection
            )
            selected_element_ids = np.asarray(element_scoping.ids, dtype=np.int64)
        except Exception:
            selected_element_ids = np.asarray([], dtype=np.int64)

        cell_indices = _indices_for_ids(element_ids, selected_element_ids)
        if cell_indices.size == 0 and selected_node_ids.size:
            point_indices = _indices_for_ids(node_ids, selected_node_ids)
            cell_indices = _cell_indices_touching_points(
                grid, point_indices, require_all=True
            )
            if cell_indices.size == 0:
                cell_indices = _cell_indices_touching_points(
                    grid, point_indices, require_all=False
                )

        if cell_indices.size == 0:
            raise ValueError(
                "Named selection '{0}' did not resolve to mesh cells.".format(
                    named_selection
                )
            )

    ignored_element_ids = np.asarray([], dtype=np.int64)
    if ignore_stress_evaluation_shells:
        ignored_element_ids = _stress_evaluation_shell_element_ids(dpf, data_sources)
        ignored_cell_indices = _indices_for_ids(element_ids, ignored_element_ids)
        if ignored_cell_indices.size:
            allowed_cell_indices = np.setdiff1d(
                np.arange(int(grid.n_cells)), ignored_cell_indices
            )
            cell_indices = (
                allowed_cell_indices
                if cell_indices is None
                else np.intersect1d(cell_indices, allowed_cell_indices)
            )

    if cell_indices is not None:
        if cell_indices.size == 0:
            raise ValueError(
                "No mesh cells remain after excluding stress/strain-evaluation-only shells."
            )
        selected = grid.extract_cells(cell_indices)

    surface = _extract_surface(selected)
    if ignore_stress_evaluation_shells and result_node_ids is not None:
        if "DPFNodeId" not in surface.point_data:
            raise ValueError("The extracted RST surface does not contain DPFNodeId data.")
        surface_node_ids = np.asarray(surface.point_data["DPFNodeId"], dtype=np.int64)
        result_point_indices = np.flatnonzero(
            np.isin(surface_node_ids, np.asarray(result_node_ids, dtype=np.int64))
        )
        complete_cells = _cell_indices_touching_points(
            surface, result_point_indices, require_all=True
        )
        if complete_cells.size == 0:
            raise ValueError(
                "No contour cells remain after excluding stress/strain-evaluation-only shells."
            )
        if complete_cells.size != int(surface.n_cells):
            surface = _extract_surface(surface.extract_cells(complete_cells))
    if int(surface.n_points) == 0 or int(surface.n_cells) == 0:
        raise ValueError(
            "Named selection '{0}' produced an empty surface mesh.".format(
                named_selection or "(whole model)"
            )
        )
    if "Normals" not in surface.point_data:
        surface = surface.compute_normals(point_normals=True, inplace=False)

    return {
        "surface": surface,
        "named_selection": named_selection,
        "unit": "mm",
        "source_unit": str(getattr(mesh, "unit", "") or ""),
        "node_ids": selected_node_ids.astype(int),
        "element_ids": selected_element_ids.astype(int),
        "n_points": int(surface.n_points),
        "n_cells": int(surface.n_cells),
        "ignored_stress_evaluation_shell_element_ids": ignored_element_ids.astype(int),
    }


def _reindex_rows(values, src_ids, target_ids, columns):
    """Reorder ``values[:, columns]`` from ``src_ids`` order onto ``target_ids``.

    Rows whose id is absent in ``src_ids`` are left as zeros. Vectorised join.
    """
    out = np.zeros((len(target_ids), len(columns)), dtype=float)
    order = np.argsort(src_ids)
    sorted_ids = src_ids[order]
    pos = np.searchsorted(sorted_ids, target_ids)
    pos = np.clip(pos, 0, len(sorted_ids) - 1)
    match = sorted_ids[pos] == target_ids
    rows = order[pos]
    out[match] = values[rows[match]][:, columns]
    return out


def load_rst_strain(
    rst_path,
    set_ids,
    named_selection=None,
    rotate_to_global=True,
    ignore_stress_evaluation_shells=False,
):
    """Extract nodal elastic strain from a ``.rst`` into the SG-tool data contract.

    Args:
        rst_path: path to the ``.rst`` file.
        set_ids: iterable of 1-based result set ids (one "load case" per id).
        named_selection: optional NS name to scope to (None/"" => whole model).
        rotate_to_global: rotate strains to the global coordinate system.
        ignore_stress_evaluation_shells: exclude SHELL181 elements whose
            KEYOPT(1)=2 before nodal strain evaluation.

    Returns:
        ``(nodes, coords_mm, strain_tensors)`` matching :func:`computation.load_data`.
    """
    dpf = _require_dpf()
    from ansys.dpf.core import time_freq_scoping_factory as tfsf

    rst_path = str(rst_path)
    set_ids = [int(s) for s in set_ids]
    if not set_ids:
        raise ValueError("No result sets selected.")

    data_sources = dpf.DataSources(rst_path)
    model = dpf.Model(rst_path)
    mesh = model.metadata.meshed_region
    scale = _length_scale_to_mm(getattr(mesh, "unit", None))

    mesh_scoping = None
    named_node_ids = None
    if named_selection:
        mesh_scoping = _nodal_scoping_for_named_selection(
            dpf, data_sources, model, named_selection
        )
        named_node_ids = np.asarray(mesh_scoping.ids, dtype=np.int64)

    ignored_element_ids = np.asarray([], dtype=np.int64)
    if ignore_stress_evaluation_shells:
        ignored_element_ids = _stress_evaluation_shell_element_ids(dpf, data_sources)
        if ignored_element_ids.size:
            allowed_element_ids = np.setdiff1d(
                np.asarray(mesh.elements.scoping.ids, dtype=np.int64),
                ignored_element_ids,
            )
            if allowed_element_ids.size == 0:
                raise ValueError(
                    "No elements remain after excluding stress/strain-evaluation-only shells."
                )
            mesh_scoping = dpf.mesh_scoping_factory.elemental_scoping(
                allowed_element_ids.tolist()
            )

    # Whole-mesh coordinate field, used to join coordinates onto strain nodes.
    coords_field = mesh.nodes.coordinates_field
    coord_ids = np.asarray(coords_field.scoping.ids, dtype=np.int64)
    coord_data = np.asarray(coords_field.data, dtype=float)

    ref_ids = None
    strain_tensors = {}

    for case_idx, set_id in enumerate(set_ids):
        op = dpf.operators.result.elastic_strain()
        op.inputs.data_sources.connect(data_sources)
        op.inputs.requested_location.connect("Nodal")
        try:
            op.inputs.bool_rotate_to_global.connect(bool(rotate_to_global))
        except Exception:
            pass
        op.inputs.time_scoping.connect(tfsf.scoping_by_set(int(set_id)))
        if mesh_scoping is not None:
            op.inputs.mesh_scoping.connect(mesh_scoping)

        fields_container = op.outputs.fields_container()
        if "elshape" in fields_container.labels:
            fields_container = dpf.operators.utility.merge_fields_by_label(
                fields_container=fields_container,
                label="elshape",
            ).outputs.fields_container()
        fields = [field for field in fields_container if len(field.scoping.ids)]
        if len(fields) != 1:
            raise ValueError(
                "Elastic strain returned {0} unresolved fields with labels {1}.".format(
                    len(fields), list(fields_container.labels)
                )
            )
        field = fields[0]
        ids = np.asarray(field.scoping.ids, dtype=np.int64)
        data = np.asarray(field.data, dtype=float)
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        if ignored_element_ids.size and named_node_ids is not None:
            keep = np.isin(ids, named_node_ids)
            ids = ids[keep]
            data = data[keep]
        if data.shape[1] < 4:
            raise ValueError(
                "Elastic strain field has {0} components; expected 6 "
                "[XX, YY, ZZ, XY, YZ, XZ].".format(data.shape[1])
            )

        if ref_ids is None:
            ref_ids = ids
            strain_tensors[case_idx] = data[:, _KEEP_COMPONENTS] * _MICROSTRAIN
        else:
            # Align later sets onto the first set's node ordering.
            strain_tensors[case_idx] = (
                _reindex_rows(data, ids, ref_ids, _KEEP_COMPONENTS) * _MICROSTRAIN
            )

    if ref_ids is None or len(ref_ids) == 0:
        raise ValueError("No strain data was returned for the requested sets.")

    # Join coordinates onto the strain node ids (orders/sizes differ in general).
    coords_all = _reindex_rows(
        coord_data, coord_ids, ref_ids, [0, 1, 2]
    )
    # Drop any strain node that has no coordinate match (degenerate; rare).
    order = np.argsort(coord_ids)
    pos = np.clip(np.searchsorted(coord_ids[order], ref_ids), 0, len(coord_ids) - 1)
    have_coord = coord_ids[order][pos] == ref_ids
    if not np.all(have_coord):
        ref_ids = ref_ids[have_coord]
        coords_all = coords_all[have_coord]
        for k in list(strain_tensors.keys()):
            strain_tensors[k] = strain_tensors[k][have_coord]

    nodes = ref_ids.astype(int)
    coords_mm = coords_all * scale
    return nodes, coords_mm, strain_tensors
