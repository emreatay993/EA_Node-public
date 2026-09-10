# Get position error
# region Import necessary libraries
import clr
import re

clr.AddReference('mscorlib')  # Ensure the core .NET assembly is referenced
clr.AddReference('System.Windows.Forms')
from System.Windows.Forms import MessageBox, MessageBoxButtons, MessageBoxIcon
from System.IO import StreamWriter, FileStream, FileMode, FileAccess
from System.Text import UTF8Encoding
from System.Diagnostics import Process, ProcessWindowStyle
import os
# endregion

# region Check whether NS_of_faces_of_SG_test_parts is defined inside the memory.
if 'NS_of_faces_of_SG_test_parts' not in locals():
    MessageBox.Show("The named selection called 'NS_of_faces_of_SG_test_parts' is not either found in the tree or not called into the memory. Please define required surfaces by running Test Parts button.", 
                "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
    raise RuntimeError("Condition not met. Exiting the script.")
# endregion

# region Set the unit system as N.mm
ExtAPI.Application.ActiveUnitSystem = MechanicalUnitSystem.StandardNMM
# endregion

# region Define the reference coordinates
# Filter the list of name of reference channels (in this case Ch_2) from each CS_SG_Ch object
list_of_all_coordinate_systems = DataModel.Project.GetChildren(DataModelObjectCategory.CoordinateSystem,True)
list_of_names_of_CS_SG_channels = [list_of_all_coordinate_systems[i].Name 
                                   for i in range(len(list_of_all_coordinate_systems))
                                   if list_of_all_coordinate_systems[i].Name.Contains("CS_SG_Ch_")
                                   and list_of_all_coordinate_systems[i].ObjectState != ObjectState.Suppressed]

# Regular expression to match channel names where y = 2, possibly followed by an underscore and more characters
pattern = r'CS_SG_Ch_(\d+)_2[^0-9]*'

# Filtered list using regular expression
list_of_filtered_names_of_CS_SG_channels = [
    channel for channel in list_of_names_of_CS_SG_channels if re.search(pattern, channel)]

# Extract the number from the channel name for sorting
def extract_number(channel_name):
    match = re.search(r'CS_SG_Ch_(\d+)_2', channel_name)
    return int(match.group(1)) if match else 0

# Sort the list of filtered names of CS_SG_Channels so that they are in natural order
list_of_filtered_names_of_CS_SG_channels.sort(key=extract_number)

# Extract SG reference numbers as well
list_of_SG_reference_numbers = [
    int(re.search(pattern, channel).group(1))  # Capture the group 1 which is the reference number
    for channel in list_of_filtered_names_of_CS_SG_channels if re.search(pattern, channel)]
# endregion

# region Get the corresponding SG objects from the tree and their coordinates
list_of_coordinates_of_all_filtered_names_of_CS_SG_channels = []

for i in range(len(list_of_filtered_names_of_CS_SG_channels)):
    # Get the list of transformed coordinates of each reference SG channel as a list of strings
    list_of_coordinates_of_filtered_names_of_CS_SG_channels = []
    list_of_coordinates_of_filtered_names_of_CS_SG_channels = \
    DataModel.GetObjectsByName(list_of_filtered_names_of_CS_SG_channels[i])[0].TransformedConfiguration.rsplit()[1:-1]
    
    # Convert this list into a list of actual numbers
    list_of_coordinates_of_each_filtered_names_of_CS_SG_channels = \
    [float(item) for item in list_of_coordinates_of_filtered_names_of_CS_SG_channels]
    
    # Collect the list of x,y,z coordinates of each reference SG channel in a wrapper/collector list
    list_of_coordinates_of_all_filtered_names_of_CS_SG_channels.append(
        list_of_coordinates_of_each_filtered_names_of_CS_SG_channels)
# endregion

# region Export the result set to be used as input as a CSV file
solution_directory_path = sol_selected_environment.WorkingDir[:-1]

if len(Tree.ActiveObjects) > 1:
        MessageBox.Show("More than one item is selected from the tree. Please select only one result item which is a valid contour object", 
                        "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
elif len(Tree.ActiveObjects) < 1:
        MessageBox.Show("You need to select a result object to calculate the expected errors caused by potential offsets from the reference strain gauge positions.", 
                        "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
elif len(Tree.ActiveObjects) == 1:
        obj_of_selected_result = Tree.ActiveObjects[0]
        selected_result_object_type = obj_of_selected_result.DataModelObjectCategory

        if (selected_result_object_type == DataModelObjectCategory.DirectionalStress 
            or selected_result_object_type == DataModelObjectCategory.DirectionalDeformation
            or selected_result_object_type == DataModelObjectCategory.TotalDeformation
            or selected_result_object_type == DataModelObjectCategory.EquivalentStress
            or selected_result_object_type == DataModelObjectCategory.MaximumPrincipalStress
            or selected_result_object_type == DataModelObjectCategory.MinimumPrincipalStress
            or selected_result_object_type == DataModelObjectCategory.NormalStress
            or selected_result_object_type == DataModelObjectCategory.EquivalentElasticStrainRST
            or selected_result_object_type == DataModelObjectCategory.MaximumPrincipalElasticStrain
            or selected_result_object_type == DataModelObjectCategory.MinimumPrincipalElasticStrain
            or selected_result_object_type == DataModelObjectCategory.NormalElasticStrain
            or selected_result_object_type == DataModelObjectCategory.DirectionalThermalStrain
            or selected_result_object_type == DataModelObjectCategory.UserDefinedResult):
            
            input_file_path = os.path.join(solution_directory_path, "distance_error.txt") 
            obj_of_selected_result.ExportToTextFile(input_file_path)

            if selected_result_object_type == DataModelObjectCategory.DirectionalDeformation:
                 string_of_result_type_identifier_suffix = "DirectionalDeformation"
            if selected_result_object_type == DataModelObjectCategory.TotalDeformation:
                 string_of_result_type_identifier_suffix = "TotalDeformation"
            if selected_result_object_type == DataModelObjectCategory.EquivalentStress:
                 string_of_result_type_identifier_suffix = "EquivalentStress"
            if selected_result_object_type == DataModelObjectCategory.MaximumPrincipalStress:
                 string_of_result_type_identifier_suffix = "MaximumPrincipalStress"
            if selected_result_object_type == DataModelObjectCategory.MinimumPrincipalStress:
                 string_of_result_type_identifier_suffix = "MinimumPrincipalStress"
            if selected_result_object_type == DataModelObjectCategory.NormalStress:
                 string_of_result_type_identifier_suffix = "NormalStress"
            if selected_result_object_type == DataModelObjectCategory.EquivalentElasticStrainRST:
                 string_of_result_type_identifier_suffix = "EquivalentElasticStrainRST"
            if selected_result_object_type == DataModelObjectCategory.MaximumPrincipalElasticStrain:
                 string_of_result_type_identifier_suffix = "MaximumPrincipalElasticStrain"
            if selected_result_object_type == DataModelObjectCategory.MinimumPrincipalElasticStrain:
                 string_of_result_type_identifier_suffix = "MinimumPrincipalElasticStrain"
            if selected_result_object_type == DataModelObjectCategory.NormalElasticStrain:
                 string_of_result_type_identifier_suffix = "NormalElasticStrain"
            if selected_result_object_type == DataModelObjectCategory.DirectionalThermalStrain:
                 string_of_result_type_identifier_suffix = "DirectionalThermalStrain"
            if selected_result_object_type == DataModelObjectCategory.UserDefinedResult:
                 string_of_result_type_identifier_suffix = "UserDefinedResult"

            print("Input CSV file is written to the solution directory")
        
        else:
            MessageBox.Show("The selected object in the tree is not a valid result object. Ensure that it is not under-defined and is evaluated correctly.", 
                            "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            raise RuntimeError("Condition not met. Exiting the script.")
# endregion

# region Define the CPython code to be run for calculating the errors
solution_directory_path = solution_directory_path.Replace("\\", "\\\\")

cpython_script_name = "calculate_distance_error_for_reference_nodes.py"
cpython_script_path = sol_selected_environment.WorkingDir + cpython_script_name
cpython_code = """
import numpy as np
import pandas as pd
import sys
import math
import re

from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton

###############################################################################
# Dialog classes for user input
###############################################################################
class RadiusDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Specify Distance')
        layout = QVBoxLayout()

        self.label = QLabel('Enter the max distance [mm]:')
        self.setFixedWidth(600)
        layout.addWidget(self.label)

        self.radius_input = QLineEdit(self)
        layout.addWidget(self.radius_input)

        self.submit_button = QPushButton('Submit', self)
        self.submit_button.clicked.connect(self.submit)
        layout.addWidget(self.submit_button)

        self.setLayout(layout)

    def submit(self):
        self.radius = float(self.radius_input.text())
        self.accept()

def get_user_radius():
    app = QApplication(sys.argv)
    dialog = RadiusDialog()
    if dialog.exec_() == QDialog.Accepted:
        return dialog.radius
    return None

###############################################################################
# Main logic
###############################################################################
def main():
    # Read the dataset
    file_name = r'""" + solution_directory_path + """' + "\\\\distance_error.txt"
    data = pd.read_csv(file_name, delimiter='\\t')

    # Convert relevant columns to NumPy arrays for faster computation
    node_numbers = data['Node Number'].values
    x_vals = data['X Location (mm)'].values
    y_vals = data['Y Location (mm)'].values
    z_vals = data['Z Location (mm)'].values
    
    # The final result column is assumed to be the last column in the dataframe
    field_values = data.iloc[:, -1].values

    # Store node coordinates in a single NumPy array of shape (N,3)
    node_coords = np.column_stack((x_vals, y_vals, z_vals))

    # Define the reference coordinates (injected from IronPython)
    reference_coordinates = """ + str(list_of_coordinates_of_all_filtered_names_of_CS_SG_channels) + """

    # Get user-specified radius
    radius = get_user_radius()
    if radius is None:
        print("No radius specified. Exiting.")
        sys.exit()

    all_nodes_with_errors = []
    max_errors = []
    results = []

    # Loop over each reference coordinate
    for idx, ref_coord in enumerate(reference_coordinates):
        ref_coord_np = np.array(ref_coord, dtype=float)

        # Vectorized distance calculation from ref_coord to all node_coords
        dists = np.linalg.norm(node_coords - ref_coord_np, axis=1)

        # Find the closest node quickly with argmin
        closest_idx = np.argmin(dists)
        closest_node_number = node_numbers[closest_idx]
        closest_node_coord = node_coords[closest_idx]
        closest_value = field_values[closest_idx]

        # Identify nodes that lie within the user-specified radius
        within_radius_mask = (dists <= radius)
        sub_indices = np.where(within_radius_mask)[0]  # indices of rows within radius

        # Calculate errors only for those nodes
        sub_abs_errors = closest_value - field_values[sub_indices]
        # Avoid division by zero if closest_value=0 by checking:
        if abs(closest_value) < 1e-15:
            sub_rel_errors = np.zeros_like(sub_abs_errors)
        else:
            sub_rel_errors = (sub_abs_errors / closest_value) * 100

        # Prepare node-by-node dictionary data
        for i, row_idx in enumerate(sub_indices):
            all_nodes_with_errors.append({
                'Node Number': int(node_numbers[row_idx]),
                'X [mm]': round(node_coords[row_idx, 0], 3),
                'Y [mm]': round(node_coords[row_idx, 1], 3),
                'Z [mm]': round(node_coords[row_idx, 2], 3),
                'Absolute Error': round(sub_abs_errors[i], 4),
                'Relative Error': round(sub_rel_errors[i], 4)
            })

        # Compute maxima for this reference point
        max_abs_error = round(np.max(sub_abs_errors), 4)
        max_rel_error = round(np.max(sub_rel_errors), 4)

        # Store aggregated results
        results.append({
            'Reference Point': f"Reference Point {idx + 1}",
            'Closest Node': {
                'Node Number': int(closest_node_number),
                'X [mm]': round(closest_node_coord[0], 3),
                'Y [mm]': round(closest_node_coord[1], 3),
                'Z [mm]': round(closest_node_coord[2], 3),
                'Field Value': round(closest_value, 4)
            },
            'Nodes Within Radius': sub_indices.size
        })

        max_errors.append({
            'Reference Point': f"Reference Point {idx + 1}",
            'X [mm]': round(ref_coord[0], 3),
            'Y [mm]': round(ref_coord[1], 3),
            'Z [mm]': round(ref_coord[2], 3),
            'Max Absolute Error': max_abs_error,
            'Max Relative Error': max_rel_error
        })

    # Convert lists of dicts to DataFrames
    errors_df = pd.DataFrame(all_nodes_with_errors)
    max_errors_df = pd.DataFrame(max_errors)

    # Write the results to CSV
    errors_csv = r'""" + solution_directory_path + """\\\\SG_positioning_errors.csv'
    max_errors_csv = r'""" + solution_directory_path + """\\\\SG_max_positioning_errors.csv'

    errors_df.to_csv(errors_csv, index=False)
    max_errors_df.to_csv(max_errors_csv, index=False)

    # Print some results
    for result in results:
        print(f"{result['Reference Point']}:")
        print(f"  Closest Node: {result['Closest Node']}")
        print(f"  Number of Nodes Within Radius: {result['Nodes Within Radius']}")

if __name__ == '__main__':
    main()
"""

# Use StreamWriter with FileStream to write the file with UTF-8 encoding
with StreamWriter(FileStream(cpython_script_path, FileMode.Create, FileAccess.Write), UTF8Encoding(True)) as writer:
    writer.Write(cpython_code)

print("Python file created successfully with UTF-8 encoding.")
# endregion

# region Run the CPython script asynchronously
# Run the CPython script asynchronously
process = Process()
# Configure the process to hide the window and not use the shell execute feature
# process.StartInfo.CreateNoWindow = True

process.StartInfo.UseShellExecute = True
# Set the command to run the Python interpreter with your script as the argument
process.StartInfo.WindowStyle = ProcessWindowStyle.Minimized
process.StartInfo.FileName = "cmd.exe"  # Use cmd.exe to allow window manipulation
process.StartInfo.Arguments = '/c python "' + cpython_script_path + '"'
# Start the process
process.Start()

#◙ Wait for the calculations to complete
process.WaitForExit()
# endregion

# region Plot the result from the output CSV file if "CSV Plot" extension is already loaded inside Mechanical
list_of_obj_of_extensions = ExtAPI.ExtensionManager.Extensions
is_csv_plot_enabled = False
for i in range(len(list_of_obj_of_extensions)):
    if list_of_obj_of_extensions[i].Name == 'CSV Plot':
        is_csv_plot_enabled = True
        break
    
if is_csv_plot_enabled:
    output_file_path = os.path.join(solution_directory_path, "SG_positioning_errors.csv")

    contour_object_of_error_result = sol_selected_environment.Parent.CreateResultObject("csvPlot", "CSV Plot")
    contour_object_of_error_result.Caption = "Relative Error around Each SG Reference Position" + ": " + string_of_result_type_identifier_suffix
    contour_object_of_error_result.Properties[0].Properties[0].InternalValue = 'ID_NamedSelection'
    if NS_of_faces_of_SG_test_parts:
        contour_object_of_error_result.Properties[0].Properties[0].Properties[1].InternalValue = NS_of_faces_of_SG_test_parts.ObjectId.ToString()
    contour_object_of_error_result.Properties[1].InternalValue = output_file_path
    contour_object_of_error_result.Properties[3].InternalValue = 'Relative Error'
    contour_object_of_error_result.Properties[4].InternalValue = 'Node'
    contour_object_of_error_result.Properties[5].InternalValue = 'No'
    contour_object_of_error_result.Suppressed = 1
    contour_object_of_error_result.Suppressed = 0
# endregion
