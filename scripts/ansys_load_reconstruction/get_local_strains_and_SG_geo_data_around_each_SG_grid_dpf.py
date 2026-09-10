"""Mechanical button: export local SG strain clouds with DPF.

This is the faster DPF replacement for
get_local_strains_and_SG_geo_data_around_each_SG_grid.py. It writes the same
StrainX_around_each_SG folder shape, but it does not create temporary named
selections or Normal Elastic Strain result contours in the Mechanical tree.
"""

import csv
import json
import os
import re
import time
import traceback

import clr

clr.AddReference("System.Drawing")
clr.AddReference("System.Windows.Forms")

from System.Drawing import Color, Font, FontStyle, Point, Size
from System.Windows.Forms import (
    AnchorStyles,
    Button,
    DialogResult,
    Form,
    FormBorderStyle,
    FormStartPosition,
    Keys,
    Label,
    MessageBox,
    MessageBoxButtons,
    MessageBoxIcon,
    TextBox,
)

import mech_dpf
import Ans.DataProcessing as dpf


OUTPUT_FOLDER_NAME = "StrainX_around_each_SG"
DIAGNOSTICS_FILE_NAME = "local_sg_strain_dpf_diagnostics.json"
DEFAULT_RADIUS_MM = "10"
DEFAULT_TIME_SEC = "0.777"
DEFAULT_PRELOAD_TIME_SEC = "0.000"


class StopScriptError(Exception):
    pass


class ModernInputBox(Form):
    def __init__(self, prompt, title, default_value, width=500):
        self.Text = title
        self.Width = width
        self.Height = 180
        self.StartPosition = FormStartPosition.CenterParent
        self.BackColor = Color.White
        self.FormBorderStyle = FormBorderStyle.Sizable
        self.MinimumSize = Size(360, 150)

        self.label = Label()
        self.label.Text = prompt
        self.label.Font = Font("Segoe UI", 10, FontStyle.Regular)
        self.label.Location = Point(20, 20)
        self.label.Size = Size(width - 40, 24)
        self.label.ForeColor = Color.FromArgb(50, 50, 50)
        self.label.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
        self.label.Parent = self

        self.textBox = TextBox()
        self.textBox.Location = Point(20, 54)
        self.textBox.Size = Size(width - 40, 28)
        self.textBox.Font = Font("Segoe UI", 10, FontStyle.Regular)
        self.textBox.ForeColor = Color.FromArgb(50, 50, 50)
        self.textBox.Text = default_value
        self.textBox.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
        self.textBox.Parent = self

        self.okButton = Button()
        self.okButton.Text = "OK"
        self.okButton.Font = Font("Segoe UI", 10, FontStyle.Regular)
        self.okButton.ForeColor = Color.White
        self.okButton.BackColor = Color.FromArgb(45, 156, 219)
        self.okButton.Location = Point((width - 100) // 2, 104)
        self.okButton.Size = Size(100, 30)
        self.okButton.Anchor = AnchorStyles.Bottom
        self.okButton.Parent = self
        self.okButton.Click += self.on_ok_click

        self.KeyPreview = True
        self.KeyDown += self.form_key_down

    def on_ok_click(self, sender, args):
        self.DialogResult = DialogResult.OK
        self.Close()

    def form_key_down(self, sender, args):
        if args.KeyCode == Keys.Enter:
            args.Handled = True
            self.on_ok_click(sender, args)

    def get_input(self):
        if self.ShowDialog() == DialogResult.OK:
            return self.textBox.Text
        return None


def show_error(message):
    MessageBox.Show(str(message), "Extract Local SG Strains - DPF", MessageBoxButtons.OK, MessageBoxIcon.Error)


def show_info(message):
    MessageBox.Show(str(message), "Extract Local SG Strains - DPF", MessageBoxButtons.OK, MessageBoxIcon.Information)


def stop_with_error(message):
    show_error(message)
    raise StopScriptError(message)


def safe_get(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def to_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return list(value)
    except Exception:
        return [value]


def connect_pin(pin, value):
    if hasattr(pin, "Connect"):
        pin.Connect(value)
        return
    if hasattr(pin, "connect"):
        pin.connect(value)
        return
    raise Exception("DPF input pin does not expose Connect/connect.")


def connect_optional_pin(inputs, name, value):
    pin = safe_get(inputs, name, None)
    if pin is not None:
        connect_pin(pin, value)


def output_data(output):
    if hasattr(output, "GetData"):
        return output.GetData()
    if callable(output):
        return output()
    return output


def scoping_ids(scoping):
    ids = safe_get(scoping, "Ids", None)
    if ids is None:
        ids = safe_get(scoping, "ids", None)
    return [int(item) for item in to_list(ids)]


def scoping_from_ids(ids, location):
    scoping = dpf.Scoping()
    scoping.Ids = [int(item) for item in sorted(set(ids))]
    try:
        scoping.Location = location
    except Exception:
        try:
            scoping.location = location
        except Exception:
            pass
    return scoping


def dpf_nodal_location():
    try:
        return dpf.locations.nodal
    except Exception:
        return "Nodal"


def dpf_elemental_nodal_location():
    try:
        return dpf.locations.elemental_nodal
    except Exception:
        return "ElementalNodal"


def channel_numbers(name):
    numbers = re.findall(r"\d+", str(name))
    if len(numbers) < 2:
        return (0, 0)
    return (int(numbers[-2]), int(numbers[-1]))


def channel_key(name):
    first, second = channel_numbers(name)
    return "{0}_{1}".format(first, second)


def sort_by_channel_name(objects):
    return sorted(objects, key=lambda obj: channel_numbers(safe_get(obj, "Name", obj)))


def selected_solution_environment():
    selected = globals().get("sol_selected_environment", None)
    if selected is not None and safe_get(selected, "WorkingDir", None):
        return selected

    target_working_dir = os.environ.get("SG_LOCAL_DPF_WORKING_DIR", "").strip()
    target_analysis = os.environ.get("SG_LOCAL_DPF_ANALYSIS_NAME", "").strip().lower()
    solutions = []
    try:
        analyses = to_list(Model.Analyses)
    except Exception:
        analyses = []

    for analysis in analyses:
        solution = safe_get(analysis, "Solution", None)
        if solution is None:
            continue
        solutions.append(solution)
        working_dir = str(safe_get(solution, "WorkingDir", "") or "")
        analysis_name = str(safe_get(analysis, "Name", "") or "")
        if target_working_dir and os.path.normcase(os.path.normpath(working_dir)) == os.path.normcase(os.path.normpath(target_working_dir)):
            return solution
        if target_analysis and target_analysis in analysis_name.lower():
            return solution

    if len(solutions) == 1:
        return solutions[0]

    stop_with_error(
        "Please select the solution environment first. For batch use, set "
        "SG_LOCAL_DPF_WORKING_DIR or SG_LOCAL_DPF_ANALYSIS_NAME."
    )


def prompt_float(prompt, title, default_value, env_name):
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return float(env_value)

    form = ModernInputBox(prompt, title, default_value, width=760)
    text = form.get_input()
    if text is None:
        raise StopScriptError("User cancelled.")
    try:
        return float(text)
    except Exception:
        MessageBox.Show("Invalid input. Please enter a numeric value.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        return prompt_float(prompt, title, default_value, env_name)


def require_test_part_faces():
    matches = DataModel.GetObjectsByName("NS_of_faces_of_SG_test_parts")
    if len(matches) == 0:
        stop_with_error('Missing "NS_of_faces_of_SG_test_parts". Run the Test Part button first.')
    named_selection = matches[0]
    location = safe_get(named_selection, "Location", None)
    ids = scoping_ids(location)
    if len(ids) == 0:
        stop_with_error('"NS_of_faces_of_SG_test_parts" exists but has no scoped faces.')
    return named_selection


def coordinate_systems_by_channel():
    systems = []
    for child in to_list(Model.CoordinateSystems.Children):
        name = str(safe_get(child, "Name", ""))
        if "CS_SG_Ch_" in name:
            systems.append(child)
    systems = sort_by_channel_name(systems)
    if len(systems) == 0:
        stop_with_error('No coordinate systems named "CS_SG_Ch_*" were found.')
    return systems


def coordinate_system_record(cs_obj):
    name = str(cs_obj.Name)
    return {
        "name": name,
        "key": channel_key(name),
        "origin": [float(cs_obj.Origin[0]), float(cs_obj.Origin[1]), float(cs_obj.Origin[2])],
        "x": [float(cs_obj.XAxis[0]), float(cs_obj.XAxis[1]), float(cs_obj.XAxis[2])],
        "y": [float(cs_obj.YAxis[0]), float(cs_obj.YAxis[1]), float(cs_obj.YAxis[2])],
        "z": [float(cs_obj.ZAxis[0]), float(cs_obj.ZAxis[1]), float(cs_obj.ZAxis[2])],
    }


def restore_selection(selection_manager, previous_selection):
    try:
        if previous_selection is None:
            selection_manager.ClearSelection()
        else:
            selection_manager.NewSelection(previous_selection)
    except Exception:
        try:
            selection_manager.ClearSelection()
        except Exception:
            pass


def select_mechanical_location(selection_manager, location):
    try:
        selection_manager.NewSelection(location)
        return
    except Exception as first_error:
        try:
            selection_manager.ClearSelection()
            selection_manager.AddSelection(location)
            return
        except Exception as second_error:
            raise Exception("NewSelection failed: {0}; AddSelection failed: {1}".format(first_error, second_error))


def nodes_from_named_selection(named_selection):
    selection_manager = ExtAPI.SelectionManager
    previous_selection = safe_get(selection_manager, "CurrentSelection", None)
    try:
        location = safe_get(named_selection, "Location", None)
        select_mechanical_location(selection_manager, location or named_selection)
        node_scoping = mech_dpf.GetNodesScoping()
    finally:
        restore_selection(selection_manager, previous_selection)

    node_ids = sorted(set(scoping_ids(node_scoping)))
    if len(node_ids) == 0:
        stop_with_error("DPF returned no test-part nodes from NS_of_faces_of_SG_test_parts.")
    return node_ids


def result_file_path(solution):
    checked = []
    for owner in (solution, safe_get(solution, "Parent", None)):
        if owner is None:
            continue
        for attr in ("ResultFileName", "ResultFilePath"):
            value = str(safe_get(owner, attr, "") or "")
            if value:
                checked.append(value)
                if os.path.isfile(value):
                    return value
        for attr in ("WorkingDir", "SolverFilesDirectory"):
            folder = str(safe_get(owner, attr, "") or "")
            if not folder:
                continue
            for name in ("file.rst", "file.rth"):
                path = os.path.join(folder, name)
                checked.append(path)
                if os.path.isfile(path):
                    return path
            try:
                for name in os.listdir(folder):
                    if name.lower().endswith((".rst", ".rth")):
                        path = os.path.join(folder, name)
                        checked.append(path)
                        if os.path.isfile(path):
                            return path
            except Exception:
                pass
    stop_with_error("Could not find the selected solution result file. Checked: {0}".format("; ".join(checked)))


def mesh_from_data_sources(data_sources):
    try:
        model = dpf.Model(data_sources)
        mesh = safe_get(model, "Mesh", None)
        if mesh is not None:
            return mesh
        metadata = safe_get(model, "metadata", None) or safe_get(model, "Metadata", None)
        mesh = safe_get(metadata, "meshed_region", None) or safe_get(metadata, "MeshedRegion", None)
        if mesh is not None:
            return mesh
    except Exception:
        pass

    provider = dpf.operators.mesh.mesh_provider()
    connect_pin(provider.inputs.data_sources, data_sources)
    return output_data(provider.outputs.mesh)


def dpf_node_xyz(mesh, node_id):
    node_id = int(node_id)
    if hasattr(mesh, "NodeById"):
        node = mesh.NodeById(node_id)
        return [float(node.X), float(node.Y), float(node.Z)]
    nodes = safe_get(mesh, "nodes", None)
    if nodes is not None and hasattr(nodes, "node_by_id"):
        node = nodes.node_by_id(node_id)
        return [float(value) for value in node.coordinates]
    raise Exception("Could not read coordinates for node {0} from the DPF mesh.".format(node_id))


def field_vectors_by_id(field):
    ids = scoping_ids(safe_get(field, "Scoping", None) or safe_get(field, "scoping", None))
    data = safe_get(field, "Data", None)
    if data is None:
        data = safe_get(field, "data", None)
    values = to_list(data)
    component_count = int(
        safe_get(field, "ComponentCount", None)
        or safe_get(field, "component_count", None)
        or safe_get(field, "components_count", None)
        or 1
    )
    result = {}
    if (
        component_count > 1
        and len(values) == len(ids) * component_count
        and (len(values) == 0 or not hasattr(values[0], "__iter__"))
    ):
        for index, node_id in enumerate(ids):
            start = index * component_count
            result[int(node_id)] = [float(item) for item in values[start : start + component_count]]
        return result

    for index, node_id in enumerate(ids):
        value = values[index]
        if hasattr(value, "tolist"):
            value = value.tolist()
        result[int(node_id)] = [float(item) for item in to_list(value)]
    return result


def first_field(fields_container):
    if hasattr(fields_container, "__getitem__"):
        try:
            return fields_container[0]
        except Exception:
            pass
    if hasattr(fields_container, "GetFieldByTimeId"):
        return fields_container.GetFieldByTimeId(1)
    raise Exception("DPF fields container did not expose a first field.")


def elastic_strain_fields_container(data_sources, node_ids, time_value, requested_location):
    op = dpf.operators.result.elastic_strain()
    connect_pin(op.inputs.data_sources, data_sources)
    if node_ids is not None:
        connect_pin(op.inputs.mesh_scoping, scoping_from_ids(node_ids, dpf_nodal_location()))
    connect_pin(op.inputs.time_scoping, [float(time_value)])
    connect_pin(op.inputs.requested_location, requested_location)
    connect_optional_pin(op.inputs, "bool_rotate_to_global", True)
    return output_data(op.outputs.fields_container)


def elastic_strain_field(data_sources, node_ids, time_value, requested_location):
    return first_field(elastic_strain_fields_container(data_sources, node_ids, time_value, requested_location))


def extended_midnode_vectors(data_sources, mesh, missing_node_ids, time_value):
    if len(missing_node_ids) == 0:
        return {}

    fields_container = elastic_strain_fields_container(
        data_sources,
        None,
        time_value,
        dpf_nodal_location(),
    )
    extend_op = dpf.operators.averaging.extend_to_mid_nodes_fc()
    connect_pin(extend_op.inputs.fields_container, fields_container)
    connect_optional_pin(extend_op.inputs, "mesh", mesh)
    vectors = field_vectors_by_id(first_field(output_data(extend_op.outputs.fields_container)))
    return dict((node_id, vectors[node_id]) for node_id in missing_node_ids if node_id in vectors)


def local_x_normal_strain(vector, x_axis):
    if len(vector) < 6:
        raise Exception("DPF elastic strain vector has {0} components; expected 6.".format(len(vector)))
    ex, ey, ez, gxy, gyz, gxz = [float(value) for value in vector[:6]]
    x0, x1, x2 = x_axis
    return (
        ex * x0 * x0
        + ey * x1 * x1
        + ez * x2 * x2
        + gxy * x0 * x1
        + gyz * x1 * x2
        + gxz * x0 * x2
    )


def distance_squared(left, right):
    return sum((float(left[index]) - float(right[index])) ** 2 for index in range(3))


def channel_node_ids(test_part_node_ids, coordinates_by_node, systems, radius_mm):
    radius_squared = float(radius_mm) * float(radius_mm)
    result = {}
    for system in systems:
        origin = system["origin"]
        ids = []
        for node_id in test_part_node_ids:
            xyz = coordinates_by_node[node_id]
            if distance_squared(xyz, origin) <= radius_squared + 1.0e-9:
                ids.append(int(node_id))
        result[system["key"]] = sorted(ids)
    return result


def format_float(value):
    return "%.8g" % float(value)


def write_channel_csv(path, rows):
    with open(path, "wb") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow([
            "Node Number",
            "X Location (mm)",
            "Y Location (mm)",
            "Z Location (mm)",
            "Normal Elastic Strain (mm/mm)",
        ])
        for row in rows:
            writer.writerow([
                int(row["node_id"]),
                format_float(row["x"]),
                format_float(row["y"]),
                format_float(row["z"]),
                format_float(row["strain"]),
            ])


def write_coordinate_system_csv(path, systems):
    with open(path, "wb") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "CS Name",
            "Origin_X",
            "Origin_Y",
            "Origin_Z",
            "X_dir_i",
            "X_dir_j",
            "X_dir_k",
            "Y_dir_i",
            "Y_dir_j",
            "Y_dir_k",
            "Z_dir_i",
            "Z_dir_j",
            "Z_dir_k",
        ])
        for system in systems:
            writer.writerow(
                [system["name"]]
                + [format_float(value) for value in system["origin"]]
                + [format_float(value) for value in system["x"]]
                + [format_float(value) for value in system["y"]]
                + [format_float(value) for value in system["z"]]
            )


def transform_to_local(global_coords_mm, system):
    translated = [float(global_coords_mm[i]) - float(system["origin"][i]) for i in range(3)]
    return [
        sum(translated[i] * system["x"][i] for i in range(3)),
        sum(translated[i] * system["y"][i] for i in range(3)),
        sum(translated[i] * system["z"][i] for i in range(3)),
    ]


def sg_grid_bodies():
    bodies = []
    for body in DataModel.GetObjectsByType(DataModelObjectCategory.Body):
        name = str(safe_get(body, "Name", ""))
        if "SG_Grid_Body_" in name:
            bodies.append(body)
    return sorted(bodies, key=lambda body: channel_numbers(safe_get(body, "Name", "")))


def write_sg_grid_vertices(output_folder, systems_by_key):
    global_path = os.path.join(output_folder, "SG_grid_body_vertices.csv")
    local_path = os.path.join(output_folder, "SG_grid_body_vertices_in_local_CS.csv")

    global_rows = []
    local_rows = []
    for body in sg_grid_bodies():
        geo_body = body.GetGeoBody()
        body_name = str(geo_body.Name)
        key = channel_key(body_name)
        system = systems_by_key.get(key, None)
        for index, vertex in enumerate(to_list(geo_body.Vertices), 1):
            xyz_mm = [float(vertex.X) * 1000.0, float(vertex.Y) * 1000.0, float(vertex.Z) * 1000.0]
            global_rows.append([body_name, index] + [format_float(value) for value in xyz_mm])
            if system is not None:
                local_rows.append([body_name, index] + [format_float(value) for value in transform_to_local(xyz_mm, system)])

    with open(global_path, "wb") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Body_Name", "Vertex_No", "X [mm]", "Y [mm]", "Z [mm]"])
        writer.writerows(global_rows)

    with open(local_path, "wb") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Body_Name", "Vertex_No", "X_local [mm]", "Y_local [mm]", "Z_local [mm]"])
        writer.writerows(local_rows)


def prepare_output_folder(solution):
    output_folder = os.path.join(str(solution.WorkingDir), OUTPUT_FOLDER_NAME)
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    for name in os.listdir(output_folder):
        if (
            name.startswith("StrainX_around_")
            or name.startswith("Preload_StrainX_around_")
            or name in (
                "SG_coordinate_matrix.csv",
                "SG_grid_body_vertices.csv",
                "SG_grid_body_vertices_in_local_CS.csv",
                DIAGNOSTICS_FILE_NAME,
            )
        ):
            try:
                os.remove(os.path.join(output_folder, name))
            except Exception:
                pass
    return output_folder


def extract_rows_at_time(data_sources, mesh, systems, systems_by_key, channel_nodes, coordinates_by_node, time_value, diagnostics):
    all_node_ids = sorted(set(node_id for ids in channel_nodes.values() for node_id in ids))
    if len(all_node_ids) == 0:
        stop_with_error("No channel nodes were found inside the requested radius.")

    direct_field = elastic_strain_field(data_sources, all_node_ids, time_value, dpf_nodal_location())
    direct_vectors = field_vectors_by_id(direct_field)
    missing_direct_nodes = sorted(set(node_id for node_id in all_node_ids if node_id not in direct_vectors))
    extended_vectors = extended_midnode_vectors(data_sources, mesh, missing_direct_nodes, time_value)

    rows_by_key = {}
    extended_midnode_count = 0
    for system in systems:
        key = system["key"]
        node_ids = channel_nodes.get(key, [])
        extended_missing = [node_id for node_id in node_ids if node_id not in direct_vectors and node_id in extended_vectors]
        extended_midnode_count += len(extended_missing)

        rows = []
        for node_id in node_ids:
            vector = direct_vectors.get(node_id, None)
            if vector is None:
                vector = extended_vectors.get(node_id, None)
            if vector is None:
                stop_with_error(
                    "DPF extend_to_mid_nodes_fc did not return strain data for node {0} in channel {1}.".format(
                        node_id,
                        system["name"],
                    )
                )
            xyz = coordinates_by_node[node_id]
            rows.append({
                "node_id": int(node_id),
                "x": xyz[0],
                "y": xyz[1],
                "z": xyz[2],
                "strain": local_x_normal_strain(vector, system["x"]),
            })
        rows_by_key[key] = rows

    diagnostics["direct_nodal_value_count"] = len(direct_vectors)
    diagnostics["missing_direct_node_count"] = len(missing_direct_nodes)
    diagnostics["extended_midnode_count"] = extended_midnode_count
    diagnostics["midnode_method"] = "unscoped_nodal_extend_to_mid_nodes_fc"
    return rows_by_key


def subtract_preload_rows(selected_rows, preload_rows):
    zeroed = {}
    for key, rows in selected_rows.items():
        preload_by_node = dict((row["node_id"], row["strain"]) for row in preload_rows.get(key, []))
        zeroed_rows = []
        for row in rows:
            new_row = dict(row)
            new_row["strain"] = float(row["strain"]) - float(preload_by_node.get(row["node_id"], 0.0))
            zeroed_rows.append(new_row)
        zeroed[key] = zeroed_rows
    return zeroed


def run():
    start = time.time()
    mech_dpf.setExtAPI(ExtAPI)

    solution = selected_solution_environment()
    radius_mm = prompt_float("Please enter the radius [mm] of interest around each SG:", "Radius Input", DEFAULT_RADIUS_MM, "SG_LOCAL_DPF_RADIUS_MM")
    time_value = prompt_float("Enter the time to be displayed/extracted [in seconds]:", "Time Input", DEFAULT_TIME_SEC, "SG_LOCAL_DPF_TIME_SEC")
    preload_time = prompt_float(
        "Enter the reference time to zero the strain gauges. Use 0 for no zeroing.",
        "Preload Time Input",
        DEFAULT_PRELOAD_TIME_SEC,
        "SG_LOCAL_DPF_PRELOAD_TIME_SEC",
    )
    if preload_time < 0 or preload_time >= time_value:
        stop_with_error("Preload time must be 0 or a positive value smaller than the selected time.")

    test_part_faces = require_test_part_faces()
    systems = [coordinate_system_record(cs) for cs in coordinate_systems_by_channel()]
    systems_by_key = dict((system["key"], system) for system in systems)

    output_folder = prepare_output_folder(solution)
    write_coordinate_system_csv(os.path.join(output_folder, "SG_coordinate_matrix.csv"), systems)
    write_sg_grid_vertices(output_folder, systems_by_key)

    rst_path = result_file_path(solution)
    data_sources = dpf.DataSources(rst_path)
    mesh = mesh_from_data_sources(data_sources)

    test_part_node_ids = nodes_from_named_selection(test_part_faces)
    coordinates_by_node = dict((node_id, dpf_node_xyz(mesh, node_id)) for node_id in test_part_node_ids)
    channel_nodes = channel_node_ids(test_part_node_ids, coordinates_by_node, systems, radius_mm)

    diagnostics = {
        "script": os.path.basename(__file__) if "__file__" in globals() else "Mechanical button",
        "working_dir": str(solution.WorkingDir),
        "output_folder": output_folder,
        "rst_path": rst_path,
        "radius_mm": radius_mm,
        "time_sec": time_value,
        "preload_time_sec": preload_time,
        "test_part_node_count": len(test_part_node_ids),
        "channel_count": len(systems),
        "channel_node_counts": dict((system["name"], len(channel_nodes.get(system["key"], []))) for system in systems),
    }

    selected_rows = extract_rows_at_time(data_sources, mesh, systems, systems_by_key, channel_nodes, coordinates_by_node, time_value, diagnostics)
    if preload_time > 0:
        preload_diag = {}
        preload_rows = extract_rows_at_time(data_sources, mesh, systems, systems_by_key, channel_nodes, coordinates_by_node, preload_time, preload_diag)
        diagnostics["preload_extraction"] = preload_diag
        final_rows = subtract_preload_rows(selected_rows, preload_rows)
    else:
        final_rows = selected_rows

    for system in systems:
        file_name = "StrainX_around_{0}.csv".format(system["name"][3:])
        write_channel_csv(os.path.join(output_folder, file_name), final_rows[system["key"]])

    diagnostics["elapsed_seconds"] = time.time() - start
    diagnostics["output_file_count"] = len(systems) + 3
    diagnostics_path = os.path.join(output_folder, DIAGNOSTICS_FILE_NAME)
    with open(diagnostics_path, "w") as stream:
        json.dump(diagnostics, stream, indent=2, sort_keys=True)

    show_info(
        "Wrote {0} local SG strain files to:\n{1}\n\nExtended midside nodes: {2}\nElapsed: {3:.2f} s".format(
            len(systems),
            output_folder,
            diagnostics.get("extended_midnode_count", 0),
            diagnostics["elapsed_seconds"],
        )
    )


try:
    run()
except StopScriptError:
    pass
except Exception as exc:
    try:
        show_error("{0}\n\n{1}".format(exc, traceback.format_exc()))
    except Exception:
        raise
