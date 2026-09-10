# Strain Sensitivity Matrix

'''
Generates the strain sensitivity matrix [A]. 
To get the values of the matrix a unit load study should be specified, where each unit load case should be specified in a different analysis environment and also should contain "Unit_Load_Study_LC_" in their name in the Mechanical tree. 
The program gets each analysis environment from top to bottom, assuming that they go from the first unit load case (LC1) to the last unit load case (LC{end}). 
The columns of the matrix specifies are those load cases. 
Within each analysis environment, the results from each normal strain result objects with "StrainX_SG" in their names and that are NOT suppressed, are extracted. 
Each extracted value is the average value of that strain gauge result. 
The columns of sensitivity matrix correspond to the response of each strain gauge for each unit load case. 
Therefore the rows in each column correspond to sensitivity of each strain gage to that unit load case.
'''

# ----------------------------------------------------------------------------------------------------------

# region Import necessary libraries
import csv
import os
import json
import context_menu
import clr
clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')
clr.AddReference("System")
from System.Drawing import *
from System.Windows.Forms import *
from System.Diagnostics import Process, ProcessWindowStyle
# endregion

# ----------------------------------------------------------------------------------------------------------

# region Import the necessary classes and function for the GUI
class FlatTextBox(TextBox):
    # Custom Textbox with no border for a flat design
    def __init__(self):
        self.BackColor = Color.White
        self.Font = Font("Segoe UI", 9)
        self.SetStyle(ControlStyles.UserPaint, True)

    def OnPaint(self, e):
        # Paint background color
        e.Graphics.FillRectangle(SolidBrush(self.BackColor), 0, 0, self.Width, self.Height)
        # Paint text
        e.Graphics.DrawString(self.Text, self.Font, SolidBrush(self.ForeColor), 2, 2)
        # Draw border
        if self.Focused:
            e.Graphics.DrawRectangle(Pen(Color.FromArgb(204, 228, 247)), 0, 0, self.Width - 1, self.Height - 1)

class Form(Form):
    def __init__(self):
        self.InitializeComponent()
    
    def InitializeComponent(self):
        self.Text = 'Load Step Input'
        self.Size = Size(325, 285)
        self.FormBorderStyle = FormBorderStyle.FixedDialog
        self.BackColor = Color.White
        self.MaximizeBox = False
        self.MinimizeBox = False
        self.StartPosition = FormStartPosition.CenterScreen
    
        # Fonts
        label_font = Font("Segoe UI", 9, FontStyle.Regular)
        
        maxWidth = 250
        
        # FlowLayoutPanel setup
        self.flowPanel = FlowLayoutPanel()
        self.flowPanel.FlowDirection = FlowDirection.TopDown
        self.flowPanel.Location = Point(20, 20)
        self.flowPanel.Size = Size(450, 260)
        self.flowPanel.AutoScroll = True
    
        # Label for unit load step
        self.label1 = Label()
        self.label1.Text = 'Select the unit load step:'
        self.label1.Size = Size(250, 20)
        self.label1.Font = label_font
        self.label1.Margin = Padding(5, 5, 5, 5)
        self.flowPanel.Controls.Add(self.label1)
    
        # Combobox for unit load step endtime
        self.comboBox1 = ComboBox()
        self.comboBox1.Size = Size(250, 20)
        self.comboBox1.Font = label_font
        self.comboBox1.SelectedIndexChanged += self.comboBox1_SelectedIndexChanged
        self.comboBox1.Margin = Padding(5, 5, 5, 5)
        self.flowPanel.Controls.Add(self.comboBox1)
        
        # Label for unit load step endtime
        self.label2 = Label()
        self.label2.Text = 'Step End Time [Seconds]:'
        self.label2.Size = Size(250, 20)
        self.label2.Font = label_font
        self.label2.Margin = Padding(5, 5, 5, 5)
        self.flowPanel.Controls.Add(self.label2)
        
    
        # Read-only FlatTextBox for displaying selected value or additional info
        self.readOnlyTextBox1 = FlatTextBox()
        self.readOnlyTextBox1.Size = Size(250, 20)
        self.readOnlyTextBox1.ReadOnly = True
        self.readOnlyTextBox1.BackColor = Color.LightGray
        self.readOnlyTextBox1.Margin = Padding(5, 5, 5, 5)
        self.flowPanel.Controls.Add(self.readOnlyTextBox1)
    
        # OK button setup
        self.okButton = Button()
        self.okButton.Text = 'OK'
        self.okButton.Size = Size(250, 40)
        self.okButton.Font = Font("Segoe UI", 10, FontStyle.Bold)
        self.okButton.FlatStyle = FlatStyle.Flat
        self.okButton.FlatAppearance.BorderSize = 0
        self.okButton.BackColor = Color.FromArgb(204, 228, 247)
        self.okButton.ForeColor = Color.White
        self.okButton.Click += self.OkButtonClick
        self.okButton.Margin = Padding(5, 5, 5, 5)
        self.flowPanel.Controls.Add(self.okButton)
    
        # Add controls to the form
        self.Controls.Add(self.flowPanel)
    
        # Get number_of_analysis_steps_of_unit_load_study
        global number_of_analysis_steps_of_unit_load_study
    
        # Populate combobox items
        for timestep in range(1, number_of_analysis_steps_of_unit_load_study + 1):
            self.comboBox1.Items.Add(str(timestep))
    
        # Optionally set the first item as selected in each combobox
        if number_of_analysis_steps_of_unit_load_study > 0:
            self.comboBox1.SelectedIndex = 0
            
    def comboBox1_SelectedIndexChanged(self, sender, args):
        selectedIndex = self.comboBox1.SelectedIndex  # Get the index of the selected item
        if selectedIndex >= 0 and selectedIndex < len(list_of_endtime_of_time_steps):
            # Ensure the selected index is valid and within the range of the list_of_endtime_of_time_steps
            selectedEndTime = list_of_endtime_of_time_steps[selectedIndex]  # Retrieve the corresponding end time
            self.readOnlyTextBox1.Text = str(selectedEndTime)  # Display the end time in the ReadOnlyTextBox
    
    def OkButtonClick(self, sender, args):
        try:
            # Attempt to parse the text as float
            # Assign the value to a 'result' attribute
            selectedIndex = self.comboBox1.SelectedIndex
            if selectedIndex >= 0 and selectedIndex < len(list_of_endtime_of_time_steps):
                # Retrieve the corresponding end time based on the selected index
                self.endtime_of_unit_load = float(list_of_endtime_of_time_steps[selectedIndex])
                # Assuming you have a way to determine the initial load end time, otherwise set a default or use user input
                self.endtime_of_initial_load = float(list_of_endtime_of_time_steps[selectedIndex-1])
                self.DialogResult = DialogResult.OK
                self.Close()
            else:
                # Handle the case where no valid selection is made
                MessageBox.Show("Please select a valid timestep.", "Selection Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        except ValueError:
            # Handle the case where the conversion to float fails
            MessageBox.Show("Invalid value for end time. Please ensure a valid timestep is selected.", "Value Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
# endregion

# ----------------------------------------------------------------------------------------------------------

# region Filter all analysis environments that contains "Unit_Load_Study_LC_" in their names
list_of_obj_of_all_analysis_environments = DataModel.Project.GetChildren(DataModelObjectCategory.Analysis,True)
list_of_obj_of_analysis_environments_of_unit_load_studies = [
    list_of_obj_of_all_analysis_environments[i]
    for i in range(len(list_of_obj_of_all_analysis_environments))
    if list_of_obj_of_all_analysis_environments[i].Name.Contains("Unit_Load_Study_LC")]

# Throw an error if analysis environments named Unit_Load_Study_LC are not defined in the tree.
if len(list_of_obj_of_analysis_environments_of_unit_load_studies) == 0:
    message_no_analysis_found = "Analysis environments that starts with the name 'Unit_Load_Study_LC' are not defined in the tree. Please define these environments along with their SG result objects at each SG channel and try again."
    msg = Ansys.Mechanical.Application.Message(message_no_analysis_found, MessageSeverityType.Error)
    ExtAPI.Application.Messages.Add(msg)
# endregion

# ----------------------------------------------------------------------------------------------------------

# region Get the endtime of each load step in the analysis settings of unit load studies
DataModel.GetObjectById(list_of_obj_of_analysis_environments_of_unit_load_studies[0].ObjectId).AnalysisSettings.Activate()
Pane = ExtAPI.UserInterface.GetPane(MechanicalPanelEnum.TabularData)
Con = Pane.ControlUnknown

# Helper function to check if a string can be converted to float
def is_float(element):
    try:
        float(element)
        return True
    except ValueError:
        return False

def safe_str(value):
    try:
        if value is None:
            return None
        return str(value)
    except Exception:
        return None

def safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None

def safe_getattr(obj, name):
    try:
        return getattr(obj, name)
    except Exception:
        return None

def channel_name_from_result(result_obj):
    result_name = safe_str(safe_getattr(result_obj, "Name")) or ""
    if result_name.startswith("StrainX_"):
        return result_name[len("StrainX_"):]
    return result_name

def sg_grid_body_name_from_channel(channel_name):
    suffix = channel_name
    if suffix.startswith("SG_"):
        suffix = suffix[len("SG_"):]
    elif suffix.startswith("SG"):
        suffix = suffix[len("SG"):]
    return "SG_Grid_Body_" + suffix

def find_first_object_by_name(object_name):
    try:
        objects = DataModel.GetObjectsByName(object_name)
        if objects is not None and len(objects) > 0:
            return objects[0]
    except Exception:
        pass
    try:
        objects = ExtAPI.DataModel.GetObjectsByName(object_name)
        if objects is not None and len(objects) > 0:
            return objects[0]
    except Exception:
        pass
    return None

def body_bounds_and_dimensions(body_obj):
    bounds = None
    dimensions = None
    diagonal = None
    try:
        geo_body = body_obj.GetGeoBody()
        vertices = list(geo_body.Vertices)
        xs = [safe_float(v.X) for v in vertices if safe_float(v.X) is not None]
        ys = [safe_float(v.Y) for v in vertices if safe_float(v.Y) is not None]
        zs = [safe_float(v.Z) for v in vertices if safe_float(v.Z) is not None]
        if xs and ys and zs:
            bounds = {
                "x": [min(xs), max(xs)],
                "y": [min(ys), max(ys)],
                "z": [min(zs), max(zs)],
            }
            dimensions = {
                "x": max(xs) - min(xs),
                "y": max(ys) - min(ys),
                "z": max(zs) - min(zs),
            }
            diagonal = (dimensions["x"] ** 2 + dimensions["y"] ** 2 + dimensions["z"] ** 2) ** 0.5
    except Exception:
        pass
    return bounds, dimensions, diagonal

def sg_body_evidence(body_obj):
    if body_obj is None:
        return {
            "found": False,
            "name": None,
            "geometry_type": None,
            "model_type": None,
            "bounds": None,
            "dimensions": None,
            "bounding_box_diagonal": None,
            "shell_or_sheet_evidence": False,
        }
    bounds, dimensions, diagonal = body_bounds_and_dimensions(body_obj)
    geometry_type = safe_str(safe_getattr(body_obj, "GeometryType"))
    model_type = safe_str(safe_getattr(body_obj, "ModelType"))
    name = safe_str(safe_getattr(body_obj, "Name"))
    text = ((geometry_type or "") + " " + (model_type or "")).lower()
    return {
        "found": True,
        "name": name,
        "geometry_type": geometry_type,
        "model_type": model_type,
        "bounds": bounds,
        "dimensions": dimensions,
        "bounding_box_diagonal": diagonal,
        "shell_or_sheet_evidence": ("sheet" in text or "shell" in text),
    }

def result_scope_mentions_body(result_obj, expected_body_name):
    location = safe_getattr(result_obj, "Location")
    location_text = safe_str(location) or ""
    if expected_body_name in location_text:
        return True, location_text
    try:
        names = []
        for child in location.Children:
            names.append(safe_str(safe_getattr(child, "Name")) or "")
        location_text = ";".join(names)
        if expected_body_name in location_text:
            return True, location_text
    except Exception:
        pass
    return False, location_text

def run_cpython_metadata_postprocess(matrix_path, metadata_path):
    postprocess_path = os.path.join(project_path, "strain_sensitivity_metadata_postprocess.py")
    code = r'''
import json
import math
import sys
import numpy as np
import pandas as pd

matrix_path = sys.argv[1]
metadata_path = sys.argv[2]
matrix = pd.read_csv(matrix_path, header=None).astype(float).values
singular_values = np.linalg.svd(matrix, full_matrices=False, compute_uv=False)
condition_number = float("inf") if singular_values.size == 0 or singular_values[-1] == 0 else float(singular_values[0] / singular_values[-1])
with open(metadata_path, "r") as stream:
    metadata = json.load(stream)
metadata.setdefault("matrix", {})
metadata["matrix"].update({
    "rows": int(matrix.shape[0]),
    "columns": int(matrix.shape[1]),
    "rank": int(np.linalg.matrix_rank(matrix)),
    "singular_values": [float(value) for value in singular_values],
    "condition_number": condition_number,
})
with open(metadata_path, "w") as stream:
    json.dump(metadata, stream, indent=2)
'''
    try:
        with open(postprocess_path, "w") as stream:
            stream.write(code)
        process = Process()
        process.StartInfo.UseShellExecute = True
        process.StartInfo.WindowStyle = ProcessWindowStyle.Hidden
        process.StartInfo.FileName = "cmd.exe"
        process.StartInfo.Arguments = '/c python "' + postprocess_path + '" "' + matrix_path + '" "' + metadata_path + '"'
        process.Start()
        process.WaitForExit()
        if process.ExitCode != 0:
            with open(metadata_path, "r") as metadata_file:
                metadata = json.load(metadata_file)
            metadata.setdefault("warnings", []).append("CPython metadata postprocess failed; rank, singular_values, and condition_number may be missing.")
            with open(metadata_path, "w") as metadata_file:
                json.dump(metadata, metadata_file, indent=2)
        try:
            os.remove(postprocess_path)
        except Exception:
            pass
    except Exception:
        pass

def run_cpython_placement_sensitivity_postprocess(metadata_path, placement_path):
    try:
        with open(metadata_path, "r") as metadata_file:
            metadata = json.load(metadata_file)
        metadata.setdefault("placement_sensitivity", {})
        metadata["placement_sensitivity"].update({
            "file": placement_path,
            "numeric_rows_filled": 0,
            "method": "not_computed_by_generator",
            "required_calculator": "calculate_placement_sensitivity_from_local_strains.py",
            "note": "Run the calculator after exporting StrainX_around_each_SG local fields. The old global-X/Y plane fit is intentionally not used because rotated SG channels need local-footprint shifts.",
        })
        with open(metadata_path, "w") as metadata_file:
            json.dump(metadata, metadata_file, indent=2)
    except Exception:
        pass

list_of_endtime_of_time_steps = []
flat_list = []
for C in range(1, Con.ColumnsCount + 1):
    for R in range(1, Con.RowsCount + 1):
        Text = Con.cell(R, C).Text
        if Text is not None:
            flat_list.append(Text)

numeric_list = [float(item) for item in flat_list if is_float(item)]

num_elements_per_column = len(numeric_list) // 3
columns = [numeric_list[i * num_elements_per_column: (i + 1) * num_elements_per_column] for i in range(3)]

list_of_endtime_of_time_steps.append(columns[2])
list_of_endtime_of_time_steps = list_of_endtime_of_time_steps[0]
# endregion

# ----------------------------------------------------------------------------------------------------------

# region Run the GUI to get the requested timesteps as inputs.
# Get the first unit load study and its number of steps
number_of_analysis_steps_of_unit_load_study = list_of_obj_of_analysis_environments_of_unit_load_studies[0].AnalysisSettings.NumberOfSteps
#Initialize time step variables
endtime_of_unit_load = None
endtime_of_initial_load = None

form = Form()
Application.EnableVisualStyles()
Application.Run(form)

# After the form is closed, if OK was clicked, access the values
if form.DialogResult == DialogResult.OK:
    endtime_of_unit_load = form.endtime_of_unit_load
    endtime_of_initial_load = form.endtime_of_initial_load
# endregion

# ----------------------------------------------------------------------------------------------------------

# region Get results from environments
''' 
From environments with "Unit_Load_Study_LC_" in their names,
- Get the objects with SG_ in their names if:
    - Their result type is normal elastic strain contours and
    - They are NOT suppressed
    - They have "StrainX_SG" in their names
'''
list_of_list_of_obj_of_SG_results_of_unit_load_studies = [
    [list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children[k]
     for k in range(len(list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children))
     if list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children[k].Name.Contains("StrainX_SG")
     and list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children[k].DataModelObjectCategory == DataModelObjectCategory.NormalElasticStrain
     and list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children[k].Suppressed == False]
     for i in range(len(list_of_obj_of_analysis_environments_of_unit_load_studies))]
# Flatten the list
list_of_obj_of_SG_results_of_unit_load_studies = []
for sublist in list_of_list_of_obj_of_SG_results_of_unit_load_studies:
    for item in sublist:
        list_of_obj_of_SG_results_of_unit_load_studies.append(item)
# endregion 

# ----------------------------------------------------------------------------------------------------------

# region Set the endtime of SG results to be extracted
for i in range(len(list_of_obj_of_SG_results_of_unit_load_studies)):
    list_of_obj_of_SG_results_of_unit_load_studies[i].DisplayTime = Quantity(endtime_of_initial_load, "sec")
# endregion

# ----------------------------------------------------------------------------------------------------------

# region Evaluate all SG results
[list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.EvaluateAllResults() 
for i in range(len(list_of_obj_of_analysis_environments_of_unit_load_studies))]
# endregion

# ----------------------------------------------------------------------------------------------------------

# region Get the values of each SG due to their initial values (Bolt preload, shrink/rabbet fits etc.) 
list_of_SG_initial_strains_of_unit_load_studies = [
    [list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children[k].Average.Value
     for k in range(len(list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children))
     if list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children[k].Name.Contains("StrainX_SG")
     and list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children[k].DataModelObjectCategory == DataModelObjectCategory.NormalElasticStrain
     and list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children[k].Suppressed == False]
     for i in range(len(list_of_obj_of_analysis_environments_of_unit_load_studies))]
# endregion 

# ----------------------------------------------------------------------------------------------------------

# region Set the endtime of SG results to be extracted
for i in range(len(list_of_obj_of_SG_results_of_unit_load_studies)):
    list_of_obj_of_SG_results_of_unit_load_studies[i].DisplayTime = Quantity(endtime_of_unit_load, "sec")
# endregion

# ----------------------------------------------------------------------------------------------------------

# region Evaluate all SG results
[list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.EvaluateAllResults() 
for i in range(len(list_of_obj_of_analysis_environments_of_unit_load_studies))]
# endregion

# ----------------------------------------------------------------------------------------------------------

# region Get the values of each SG due to the application of unit loads only 
list_of_SG_results_of_unit_load_studies = [
    [list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children[k].Average.Value
     for k in range(len(list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children))
     if list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children[k].Name.Contains("StrainX_SG")
     and list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children[k].DataModelObjectCategory == DataModelObjectCategory.NormalElasticStrain
     and list_of_obj_of_analysis_environments_of_unit_load_studies[i].Solution.Children[k].Suppressed == False]
     for i in range(len(list_of_obj_of_analysis_environments_of_unit_load_studies))]
# endregion 

# ----------------------------------------------------------------------------------------------------------

# region Check if all inner lists have the same length
list_lengths = [len(inner) for inner in list_of_SG_results_of_unit_load_studies]
if min(list_lengths) != max(list_lengths):
    raise ValueError("The number of extracted values are different for each unit load application. Please check whether all the analyses have the same number of SGs with name StrainX_SG and they are all evaluated and their results are correct.")

list_lengths = [len(inner) for inner in list_of_SG_initial_strains_of_unit_load_studies]
if min(list_lengths) != max(list_lengths):
    raise ValueError("The number of extracted values are different for the initial load results of each unit load application. Please check whether all the analyses have the same number of SGs with name StrainX_SG and they are all evaluated and their results are correct.")

channel_order_by_unit_load_study = [
    [channel_name_from_result(result_obj) for result_obj in sg_result_list]
    for sg_result_list in list_of_list_of_obj_of_SG_results_of_unit_load_studies]

channel_order = channel_order_by_unit_load_study[0]
for i in range(1, len(channel_order_by_unit_load_study)):
    if channel_order_by_unit_load_study[i] != channel_order:
        raise ValueError("The StrainX_SG result object order differs between unit load studies. The sensitivity matrix would not have a trustworthy channel order.")
# endregion

# ----------------------------------------------------------------------------------------------------------

# Subtracting the effect of initial strains from unit load results
list_of_SG_results_of_unit_load_studies_only = [
    [result - initial for result, initial in zip(results_list, initial_list)]
    for results_list, initial_list in 
    zip(list_of_SG_results_of_unit_load_studies, list_of_SG_initial_strains_of_unit_load_studies)]

csv_file_name = 'strain_sensitivity_matrix.csv'

csv_file_path = os.path.join(project_path, csv_file_name)

# Write to CSV file into the specified project path
with open(csv_file_path, 'wb') as csvfile:
    writer = csv.writer(csvfile)
    
    # Use zip(*list_of_SG_results_of_unit_load_studies) to transpose the list of lists
    for row in zip(*list_of_SG_results_of_unit_load_studies_only):
        writer.writerow(row)
# endregion

# ----------------------------------------------------------------------------------------------------------

# region Write metadata and placement-sensitivity sidecar files
metadata_file_name = "strain_sensitivity_metadata.json"
metadata_file_path = os.path.join(project_path, metadata_file_name)
placement_sensitivity_file_name = "strain_sensitivity_placement_sensitivity.csv"
placement_sensitivity_file_path = os.path.join(project_path, placement_sensitivity_file_name)

metadata_warnings = []
channels_metadata = []
for index, result_obj in enumerate(list_of_list_of_obj_of_SG_results_of_unit_load_studies[0]):
    channel_name = channel_order[index]
    expected_body_name = sg_grid_body_name_from_channel(channel_name)
    body_obj = find_first_object_by_name(expected_body_name)
    body_evidence = sg_body_evidence(body_obj)
    scope_matches, scope_text = result_scope_mentions_body(result_obj, expected_body_name)
    if not body_evidence.get("shell_or_sheet_evidence", False):
        metadata_warnings.append("Expected SG body {0} was not confirmed as shell/sheet from the Mechanical object model.".format(expected_body_name))
    if not scope_matches:
        metadata_warnings.append("Result {0} was not confirmed as scoped to {1} from the Mechanical object model.".format(safe_str(safe_getattr(result_obj, "Name")), expected_body_name))
    channels_metadata.append({
        "index": index,
        "channel": channel_name,
        "result_object_name": safe_str(safe_getattr(result_obj, "Name")),
        "expected_sg_grid_body_name": expected_body_name,
        "scope_matches_expected_sg_grid_body": scope_matches,
        "scope_evidence": scope_text,
        "sg_grid_body": body_evidence,
        "average_value_source": "NormalElasticStrain.Average.Value",
    })

unit_load_systems_metadata = []
for analysis_index, analysis_obj in enumerate(list_of_obj_of_analysis_environments_of_unit_load_studies):
    result_names = [safe_str(safe_getattr(result_obj, "Name")) for result_obj in list_of_list_of_obj_of_SG_results_of_unit_load_studies[analysis_index]]
    unit_load_systems_metadata.append({
        "index": analysis_index,
        "analysis_name": safe_str(safe_getattr(analysis_obj, "Name")),
        "analysis_object_id": safe_str(safe_getattr(analysis_obj, "ObjectId")),
        "working_dir": safe_str(safe_getattr(analysis_obj, "WorkingDir")),
        "initial_load_time_sec": endtime_of_initial_load,
        "unit_load_time_sec": endtime_of_unit_load,
        "result_object_names": result_names,
    })

metadata = {
    "description": "Sensitivity matrix sidecar generated by get_strain_sensitivity_matrix_from_unit_load_cases_in_mechanical_v0.py.",
    "theory_note": "Rows are already finite SG-channel averages because StrainX_SG* NormalElasticStrain.Average.Value is evaluated on SG_Grid_Body_* shell/sheet channel bodies. Do not apply a second finite-grid averaging correction.",
    "channel_order": channel_order,
    "unit_load_systems": unit_load_systems_metadata,
    "step_times": {
        "initial_load_time_sec": endtime_of_initial_load,
        "unit_load_time_sec": endtime_of_unit_load,
        "available_step_end_times_sec": list_of_endtime_of_time_steps,
    },
    "channels": channels_metadata,
    "matrix": {
        "rows": len(channel_order),
        "columns": len(list_of_obj_of_analysis_environments_of_unit_load_studies),
        "rank": None,
        "singular_values": None,
        "condition_number": None,
    },
    "warnings": metadata_warnings,
}

with open(metadata_file_path, "w") as metadata_file:
    json.dump(metadata, metadata_file, indent=2)

run_cpython_metadata_postprocess(csv_file_path, metadata_file_path)

with open(placement_sensitivity_file_path, "wb") as placement_file:
    fieldnames = [
        "Channel",
        "Load Case",
        "d_epsilon_d_x_per_mm",
        "d_epsilon_d_y_per_mm",
        "gradient_norm_per_mm",
        "Method",
        "Warning",
    ]
    writer = csv.DictWriter(placement_file, fieldnames=fieldnames)
    writer.writeheader()
    for channel_name in channel_order:
        for analysis_obj in list_of_obj_of_analysis_environments_of_unit_load_studies:
            writer.writerow({
                "Channel": channel_name,
                "Load Case": safe_str(safe_getattr(analysis_obj, "Name")),
                "d_epsilon_d_x_per_mm": "",
                "d_epsilon_d_y_per_mm": "",
                "gradient_norm_per_mm": "",
                "Method": "not_computed",
                "Warning": "Placement sensitivity requires local StrainX_around_each_SG field exports. Run calculate_placement_sensitivity_from_local_strains.py before using positioning uncertainty.",
            })

run_cpython_placement_sensitivity_postprocess(metadata_file_path, placement_sensitivity_file_path)
# endregion

# ----------------------------------------------------------------------------------------------------------

# region Show the generated strain sensitivity matrix [A]
message_success = r"""
The script for generating the strain sensitivity matrix [A] is run successfully.
Please verify the contents of the generated CSV file in the specified project path by the "Project Folder" button.
"""
msg = Ansys.Mechanical.Application.Message(message_success, MessageSeverityType.Info)
ExtAPI.Application.Messages.Add(msg)

#Open the CSV file with the default application
# try:
#     # Open the CSV file with the default application
#     if os.name == 'nt':  # For Windows
#         os.startfile(csv_file_path)
