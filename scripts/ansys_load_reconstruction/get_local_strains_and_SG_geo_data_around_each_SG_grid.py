# region Import libraries
import os
import sys
import csv
import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("Microsoft.VisualBasic")
from Microsoft.VisualBasic import Interaction
from System.Windows.Forms import (Form, Label, TextBox, Button, DialogResult,
                                  MessageBox, MessageBoxButtons, MessageBoxIcon,
                                  FormStartPosition, FormBorderStyle,
                                  AnchorStyles, Keys)
from System.Drawing import Font, FontStyle, Color, Point, Size
import context_menu
# endregion

# region Definition of classes and global variables
class ModernInputBox(Form):
    def __init__(self, prompt, title="Input Required", default_value="", width=400):
        self.Text = title
        self.Width = width  # Use the specified width
        self.Height = 180  # Initial height
        self.StartPosition = FormStartPosition.CenterParent
        self.BackColor = Color.White  # Set background color to white
        self.FormBorderStyle = FormBorderStyle.Sizable  # Allow the form to be resizable
        self.MinimumSize = Size(300, 150)  # Set a minimum size to prevent the form from being too small

        # Label
        self.label = Label()
        self.label.Text = prompt
        self.label.Font = Font("Segoe UI", 10, FontStyle.Regular)
        self.label.Location = Point(20, 20)
        self.label.Size = Size(width - 40, 20)  # Adjust size to fit within the form based on width
        self.label.ForeColor = Color.FromArgb(50, 50, 50)  # Dark gray text
        self.label.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right  # Make label responsive to resizing
        self.label.Parent = self

        # TextBox
        self.textBox = TextBox()
        self.textBox.Location = Point(20, 50)
        self.textBox.Size = Size(width - 40, 30)  # Adjust size to fit within the form based on width
        self.textBox.Font = Font("Segoe UI", 10, FontStyle.Regular)
        self.textBox.ForeColor = Color.FromArgb(50, 50, 50)
        self.textBox.Text = default_value  # Default value
        self.textBox.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right  # Make text box responsive to resizing
        self.textBox.Parent = self

        # OK Button
        self.okButton = Button()
        self.okButton.Text = "OK"
        self.okButton.Font = Font("Segoe UI", 10, FontStyle.Regular)
        self.okButton.ForeColor = Color.White
        self.okButton.BackColor = Color.FromArgb(45, 156, 219)  # Blue button
        self.okButton.FlatStyle = System.Windows.Forms.FlatStyle.Flat
        self.okButton.Location = Point((width - 100) // 2, 100)  # Center the button within the form
        self.okButton.Size = Size(100, 30)
        self.okButton.Anchor = AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right  # Make button responsive to resizing
        self.okButton.Parent = self
        self.okButton.Click += self.on_ok_click

        self.KeyPreview = True  # Enable KeyPreview to capture key events
        self.KeyDown += self.form_key_down  # Handle key down events on the form

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
# endregion

# region Initialize the preference settings of Mechanical
def initialize_mechanical_preferences():
    ExtAPI.Application.ScriptByName("jscript").ExecuteCommand(
        'WB.PreferenceMgr.Preference("PID_Show_Node_Numbers") = 1;')
    ExtAPI.Application.ScriptByName("jscript").ExecuteCommand(
        'WB.PreferenceMgr.Preference("PID_Show_Node_Location") = 1;')
    ExtAPI.Application.ScriptByName("jscript").ExecuteCommand(
        'WB.PreferenceMgr.Preference("PID_Show_Tensor_Components") = 1;')
    ExtAPI.Application.ActiveUnitSystem = MechanicalUnitSystem.StandardNMM
# endregion

# region Create local strain results around each SG with their respective SG orientations

# Get named selections
def get_named_selections():
    list_of_NS_of_nodes_around_each_SG = DataModel.GetObjectsByName("NS_of_nodes_around_each_SG")
    list_of_StrainX_around_each_SG = DataModel.GetObjectsByName("StrainX_around_each_SG")
    return list_of_NS_of_nodes_around_each_SG, list_of_StrainX_around_each_SG

# Check if NS_of_nodes_around_each_SG exists
def check_NS_existence(list_of_NS_of_nodes_around_each_SG):
    try:
        return len(list_of_NS_of_nodes_around_each_SG) == 0
    except:
        return False

# If NS_of_nodes_around_each_SG exists, delete and regenerate objects
def handle_existing_NS(list_of_NS_of_nodes_around_each_SG, list_of_StrainX_around_each_SG):
    if not check_NS_existence(list_of_NS_of_nodes_around_each_SG):
        message = r"""Some output objects are already in the Mechanical Tree. The program will now attempt to delete and regenerate all of these objects."""
        caption = "Warning"
        MessageBox.Show(message, caption, MessageBoxButtons.OK, MessageBoxIcon.Warning)

        try:
            list_of_NS_of_nodes_around_each_SG[0].DeleteTreeGroupAndChildren()
        except Exception as e:
            MessageBox.Show(str(e), "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)

        try:
            list_of_StrainX_around_each_SG[0].DeleteTreeGroupAndChildren()
        except Exception as e:
            MessageBox.Show(str(e), "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)

# Check if NS_of_faces_of_SG_test_parts exists
def check_test_parts_existence():
    try:
        NS_faces_test_parts = DataModel.GetObjectsByName("NS_of_faces_of_SG_test_parts")[0]
        return NS_faces_test_parts, False
    except:
        return None, True

# Ensure test piece is correctly defined
def ensure_test_piece_defined(NS_faces_test_parts, NS_faces_test_parts_not_found):
    if NS_faces_test_parts_not_found:
        message = r"""Please define a named selection of bodies called "NS_of_faces_of_SG_test_parts" using "Test Part" button. """
        caption = "Warning"
        MessageBox.Show(message, caption, MessageBoxButtons.OK, MessageBoxIcon.Warning)

        NS_faces_test_parts = Model.AddNamedSelection()
        NS_faces_test_parts.Name = "NS_of_faces_of_SG_test_parts"
        NS_faces_test_parts.SendToSolver = False

    if not NS_faces_test_parts_not_found and len(NS_faces_test_parts.Location.Ids) == 0:
        message = r""""NS_of_faces_of_SG_test_parts" object is already in the tree but the bodies of test parts are not defined.
        Ensure that it is assigned and this button is re-run. """
        caption = "Warning"
        MessageBox.Show(message, caption, MessageBoxButtons.OK, MessageBoxIcon.Warning)

    return NS_faces_test_parts

# Get IDs and names of each coordinate system of each SG channel
def get_CS_SG_ids_and_names():
    list_of_ids_of_each_CS_SG_Ch_ = [
        Model.CoordinateSystems.Children[i].ObjectId
        for i in range(len(Model.CoordinateSystems.Children))
        if Model.CoordinateSystems.Children[i].Name.Contains("CS_SG_Ch_")
    ]

    list_of_names_of_each_CS_SG_Ch_ = [
        Model.CoordinateSystems.Children[i].Name
        for i in range(len(Model.CoordinateSystems.Children))
        if Model.CoordinateSystems.Children[i].Name.Contains("CS_SG_Ch_")
    ]
    return list_of_ids_of_each_CS_SG_Ch_, list_of_names_of_each_CS_SG_Ch_

# Prompt the user for radius of interest
def prompt_user_for_radius():
    prompt = "Please enter the radius [mm] of interest around each SG:"
    form = ModernInputBox(prompt, "Radius Input", "10")
    radius_str = form.get_input()
    if radius_str is not None:
        try:
            radius = float(radius_str)
            return radius
        except ValueError:
            MessageBox.Show("Invalid input. Please enter a numeric value.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            return prompt_user_for_radius()  # Retry input if invalid
    else:
        MessageBox.Show("Operation canceled. Please provide a valid radius.", "Information", MessageBoxButtons.OK, MessageBoxIcon.Information)
        return None

# Create a named selection of nodes around each SG channel
def create_NS_of_nodes_around_SG(NS_faces_test_parts, list_of_ids_of_each_CS_SG_Ch_, list_of_names_of_each_CS_SG_Ch_, radius):
    try:
        NS_nodes_SG_test_parts = DataModel.GetObjectsByName("NS_of_nodes_of_SG_test_parts")[0]
    except:
        # NS_nodes_SG_test_parts = NS_faces_test_parts.CreateNodalNamedSelection()
        NS_nodes_SG_test_parts = Model.AddNamedSelection()
        NS_nodes_SG_test_parts.ScopingMethod = GeometryDefineByType.Worksheet
        NS_nodes_SG_test_parts.GenerationCriteria.Add(None)
        NS_nodes_SG_test_parts.GenerationCriteria[0].EntityType = SelectionType.GeoFace
        NS_nodes_SG_test_parts.GenerationCriteria[0].Criterion = SelectionCriterionType.NamedSelection
        NS_nodes_SG_test_parts.GenerationCriteria[0].Operator = SelectionOperatorType.Equal
        NS_nodes_SG_test_parts.GenerationCriteria[0].Value = NS_faces_test_parts
        NS_nodes_SG_test_parts.GenerationCriteria.Add(None)
        NS_nodes_SG_test_parts.GenerationCriteria[1].Action = SelectionActionType.Convert
        NS_nodes_SG_test_parts.GenerationCriteria[1].EntityType = SelectionType.MeshNode
        NS_nodes_SG_test_parts.Generate()
        NS_nodes_SG_test_parts.Name = "NS_of_nodes_of_SG_test_parts"

    list_of_NS_test_part_strains = []

    for i in range(len(list_of_names_of_each_CS_SG_Ch_)):
        NS_test_part_strain = Model.AddNamedSelection()
        NS_test_part_strain.ScopingMethod = GeometryDefineByType.Worksheet

        NS_test_part_strain.GenerationCriteria.Add(None)
        NS_test_part_strain.GenerationCriteria[0].EntityType = SelectionType.MeshNode
        NS_test_part_strain.GenerationCriteria[0].Criterion = SelectionCriterionType.Distance
        NS_test_part_strain.GenerationCriteria[0].Operator = SelectionOperatorType.LessThanOrEqual
        NS_test_part_strain.GenerationCriteria[0].Value = Quantity(radius, 'mm')
        NS_test_part_strain.GenerationCriteria[0].CoordinateSystem = DataModel.GetObjectById(list_of_ids_of_each_CS_SG_Ch_[i])

        NS_test_part_strain.GenerationCriteria.Add(None)
        NS_test_part_strain.GenerationCriteria[1].Action = SelectionActionType.Filter
        NS_test_part_strain.GenerationCriteria[1].Criterion = SelectionCriterionType.NamedSelection
        NS_test_part_strain.GenerationCriteria[1].Operator = SelectionOperatorType.Equal
        NS_test_part_strain.GenerationCriteria[1].Value = NS_nodes_SG_test_parts

        NS_test_part_strain.Name = "NS_of_nodes_around_" + list_of_names_of_each_CS_SG_Ch_[i]
        NS_test_part_strain.Generate()

        list_of_NS_test_part_strains.append(NS_test_part_strain)

    return list_of_NS_test_part_strains

# Prompt the user for time to be displayed in results
def prompt_user_for_displayed_time():
    prompt = "Enter the time to be displayed/extracted [in seconds]:"
    form = ModernInputBox(prompt, "Time Input", "0.777")
    time_str = form.get_input()
    if time_str is not None:
        try:
            time_value = float(time_str)
            return time_value
        except ValueError:
            MessageBox.Show("Invalid input. Please enter a numeric value.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            return prompt_user_for_displayed_time()  # Retry input if invalid
    else:
        MessageBox.Show("Operation canceled. Please provide a valid time value.", "Information", MessageBoxButtons.OK, MessageBoxIcon.Information)
        return None

# Prompt the user for preload time
def prompt_user_for_preload_time(time_value):
    prompt = (
        "Enter the reference time (preload step etc.) to zero the strain gauges. If no SG zeroing will be applied, set the value below as zero (0)."
    )
    form = ModernInputBox(prompt, "Preload Time Input", "0.000", width=900)
    time_preload_str = form.get_input()
    if time_preload_str is not None:
        try:
            time_preload = float(time_preload_str)
            # Check if the preload time is valid
            if time_preload >= 0 and time_preload < time_value:
                return time_preload
            else:
                MessageBox.Show(
                    "Invalid input. Please enter a value greater than or equal to 0 and less than "+ time_value,
                    "Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                )
                return prompt_user_for_preload_time(time_value)  # Retry input if invalid
        except ValueError:
            MessageBox.Show("Invalid input. Please enter a numeric value.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            return prompt_user_for_preload_time(time_value)  # Retry input if invalid
    else:
        MessageBox.Show("Operation canceled. Please provide a valid time value.", "Information", MessageBoxButtons.OK, MessageBoxIcon.Information)
        return None

# Create contour plot of strains for nodes around each CS_SG_Ch_
def create_contour_plot_of_strains(list_of_names_of_each_CS_SG_Ch_, list_of_ids_of_each_CS_SG_Ch_, list_of_NS_test_part_strains, selected_time_point):
    for i in range(len(list_of_names_of_each_CS_SG_Ch_)):
        try:
            obj_of_contour_of_nodes_around_each_SG_Ch = sol_selected_environment.AddNormalElasticStrain()
            obj_of_contour_of_nodes_around_each_SG_Ch.ScopingMethod = GeometryDefineByType.Component
            obj_of_contour_of_nodes_around_each_SG_Ch.Location = list_of_NS_test_part_strains[i]
            obj_of_contour_of_nodes_around_each_SG_Ch.Name = "StrainX_around_" + list_of_names_of_each_CS_SG_Ch_[i][3:]
            obj_of_contour_of_nodes_around_each_SG_Ch.CoordinateSystem = DataModel.GetObjectById(list_of_ids_of_each_CS_SG_Ch_[i])
            obj_of_contour_of_nodes_around_each_SG_Ch.CalculateTimeHistory = True
            obj_of_contour_of_nodes_around_each_SG_Ch.DisplayTime = Quantity(selected_time_point, "sec")
        except:
            message = r"""Please define the solution environment of interest by running "Solution Object" button. """
            caption = "Error"
            MessageBox.Show(message, caption, MessageBoxButtons.OK, MessageBoxIcon.Error)
            sys.exit(1)

# Group existing objects in the tree
def group_existing_objects(list_of_obj_of_NS_of_nodes_around_each_SG, list_of_obj_of_StrainX_around):
    ExtAPI.DataModel.Tree.Activate(list_of_obj_of_NS_of_nodes_around_each_SG)
    context_menu.DoCreateGroupingFolderInTree(ExtAPI)
    DataModel.GetObjectsByName("New Folder")[0].Name = "NS_of_nodes_around_each_SG"

    ExtAPI.DataModel.Tree.Activate(list_of_obj_of_StrainX_around)
    context_menu.DoCreateGroupingFolderInTree(ExtAPI)
    DataModel.GetObjectsByName("New Folder")[0].Name = "StrainX_around_each_SG"

# Evaluate all results
def evaluate_all_results():
    sol_selected_environment.Activate()
    sol_selected_environment.EvaluateAllResults()

# Create CSV files from each of these local SG strain results
def create_CSV_files_from_strain_results(list_of_obj_of_StrainX_around, time_preload, time_value):

    # Initialize the subfolder
    solution_directory_path = sol_selected_environment.WorkingDir
    subfolder = os.path.join(solution_directory_path, "StrainX_around_each_SG")
    if not os.path.exists(subfolder):
        os.makedirs(subfolder)
        print("Folder '{}' created successfully.".format(subfolder))
    else:
        print("Folder '{}' already exists.".format(subfolder))

    if time_preload == 0:
        # Get the local strains around SGs for a selected time point
        for i in range(len(list_of_obj_of_StrainX_around)):
            file_name_of_StrainX_around_each_SG = list_of_obj_of_StrainX_around[i].Name + ".csv"
            file_path = os.path.join(subfolder, file_name_of_StrainX_around_each_SG)
            list_of_obj_of_StrainX_around[i].ExportToTextFile(file_path)

    elif time_preload > 0 and time_preload < time_value:
        # Get the local strains around SGs for a selected time point
        for i in range(len(list_of_obj_of_StrainX_around)):
            file_name_of_StrainX_around_each_SG = list_of_obj_of_StrainX_around[i].Name + ".csv"
            file_path = os.path.join(subfolder, file_name_of_StrainX_around_each_SG)
            list_of_obj_of_StrainX_around[i].ExportToTextFile(file_path)

        # Get the local strains around SGs for a selected time point for zeroing stage
        for obj_of_contour_of_nodes_around_each_SG_Ch in list_of_obj_of_StrainX_around:
            obj_of_contour_of_nodes_around_each_SG_Ch.DisplayTime = Quantity(time_preload, "sec")
        evaluate_all_results()

        for i in range(len(list_of_obj_of_StrainX_around)):
            file_name_of_StrainX_around_each_SG_preload = "Preload_" + list_of_obj_of_StrainX_around[i].Name + ".csv"
            file_path_preload = os.path.join(subfolder, file_name_of_StrainX_around_each_SG_preload)
            list_of_obj_of_StrainX_around[i].ExportToTextFile(file_path_preload)

        # Perform the zeroing calculation for each SG channel
        for i in range(len(list_of_obj_of_StrainX_around)):
            # Construct the file paths
            file_name_selected = list_of_obj_of_StrainX_around[i].Name + ".csv"
            file_name_preload = "Preload_" + list_of_obj_of_StrainX_around[i].Name + ".csv"
            file_path_selected = os.path.join(subfolder, file_name_selected)
            file_path_preload = os.path.join(subfolder, file_name_preload)

            # Create a "_zeroed" file to store the results temporarily
            file_name_zeroed = list_of_obj_of_StrainX_around[i].Name + "_zeroed.csv"
            file_path_zeroed = os.path.join(subfolder, file_name_zeroed)

            # Read the CSV files and perform the subtraction
            with open(file_path_selected, 'r') as selected_file, open(file_path_preload, 'r') as preload_file, open(file_path_zeroed, 'wb') as zeroed_file:
                reader_selected = csv.reader(selected_file, delimiter='\t')
                reader_preload = csv.reader(preload_file, delimiter='\t')
                writer = csv.writer(zeroed_file, delimiter='\t')

                # Read headers
                headers = next(reader_selected)
                next(reader_preload)  # Skip header in preload file

                # Write headers to the new zeroed file
                writer.writerow(headers)

                # Find the index of the "Normal Elastic Strain (mm/mm)" column
                strain_index = headers.index("Normal Elastic Strain (mm/mm)")

                # Subtract the values in the "Normal Elastic Strain (mm/mm)" column
                for row_selected, row_preload in zip(reader_selected, reader_preload):
                    # Subtract preload strain from selected strain
                    row_selected[strain_index] = str(float(row_selected[strain_index]) - float(row_preload[strain_index]))
                    # Write the modified row to the new CSV file
                    writer.writerow(row_selected)

            # Remove the original source file
            os.remove(file_path_selected)

            # Rename the "_zeroed" file to the original filename
            os.rename(file_path_zeroed, file_path_selected)

            print("Zeroed data successfully written to " + file_path_selected)
    else:
        print("Invalid time_preload value. It must be either zero or a positive number smaller than time_value.")

# Create CSV files containing the corner points of each SG grid body
def create_CSV_files_for_SG_grid_bodies_in_global_CS():
    list_of_all_bodies_in_tree = DataModel.GetObjectsByType(DataModelObjectCategory.Body)

    list_of_of_SG_grid_bodies = [
        (each_body.GetGeoBody().Name, each_body.GetGeoBody().Vertices)
        for each_body in list_of_all_bodies_in_tree
        if each_body.Name.Contains("SG_Grid_Body_")
    ]

    geo_data_SG =[]
    for each_SG_body in list_of_of_SG_grid_bodies:
        body_vertices = each_SG_body[1]
        for j, each_vertex in enumerate(body_vertices):
            geo_data_SG.append({
                'Body_Name': each_SG_body[0],
                'Vertex_No': j+1,
                'X [mm]': each_vertex.X * 1000,  # Convert to mm
                'Y [mm]': each_vertex.Y * 1000,  # Convert to mm
                'Z [mm]': each_vertex.Z * 1000   # Convert to mm
            })

    solution_directory_path = sol_selected_environment.WorkingDir
    subfolder = os.path.join(solution_directory_path, "StrainX_around_each_SG")
    file_path_CSV_SG_grid_data = os.path.join(subfolder, 'SG_grid_body_vertices.csv')

    with open(file_path_CSV_SG_grid_data, 'wb') as csvfile:
        fieldnames = ["Body_Name", "Vertex_No", "X [mm]", "Y [mm]", "Z [mm]"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(geo_data_SG)

    print("CSV file saved to {}".format(file_path_CSV_SG_grid_data))
    #os.startfile(file_path_CSV_SG_grid_data)

# Create CSV files containing the definition of coordinate system of the channel
def get_SG_coordinate_data(channel_name):
    SG_channel = DataModel.GetObjectsByName(channel_name)[0]
    coordinate_data = {
        'CS Name': channel_name,
        'Origin_X': SG_channel.Origin[0],
        'Origin_Y': SG_channel.Origin[1],
        'Origin_Z': SG_channel.Origin[2],
        'X_dir_i': SG_channel.XAxis[0],
        'X_dir_j': SG_channel.XAxis[1],
        'X_dir_k': SG_channel.XAxis[2],
        'Y_dir_i': SG_channel.YAxis[0],
        'Y_dir_j': SG_channel.YAxis[1],
        'Y_dir_k': SG_channel.YAxis[2],
        'Z_dir_i': SG_channel.ZAxis[0],
        'Z_dir_j': SG_channel.ZAxis[1],
        'Z_dir_k': SG_channel.ZAxis[2]
    }
    return coordinate_data

def save_data_to_csv(coordinate_data, file_path):
    expected_keys = [
        'CS Name', 'Origin_X', 'Origin_Y', 'Origin_Z',
        'X_dir_i', 'X_dir_j', 'X_dir_k',
        'Y_dir_i', 'Y_dir_j', 'Y_dir_k',
        'Z_dir_i', 'Z_dir_j', 'Z_dir_k'
    ]

    fieldnames = [key for key in expected_keys if key in coordinate_data]
    write_header = not os.path.exists(file_path)

    with open(file_path, mode='ab') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow({key: coordinate_data.get(key, '') for key in fieldnames})

def create_CSV_files_for_coordinate_system():
    solution_directory_path = sol_selected_environment.WorkingDir
    subfolder = os.path.join(solution_directory_path, "StrainX_around_each_SG")
    file_name = "SG_coordinate_matrix.csv"
    file_path = os.path.join(subfolder, file_name)

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError as e:
        print("Error: {} : {}".format(file_path, e.strerror))

    list_of_names_of_each_CS_SG_Ch_ = [
        Model.CoordinateSystems.Children[i].Name
        for i in range(len(Model.CoordinateSystems.Children))
        if Model.CoordinateSystems.Children[i].Name.Contains("CS_SG_Ch_")
    ]

    for channel_name in list_of_names_of_each_CS_SG_Ch_:
        coordinate_data = get_SG_coordinate_data(channel_name)
        save_data_to_csv(coordinate_data, file_path)

    print("Data saved to {}".format(file_path))
    #os.startfile(file_path)

def parse_coordinate_matrix(file_path):
    """Parses the SG_coordinate_matrix.csv file to extract local coordinate systems."""
    coordinate_systems = {}

    with open(file_path, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            cs_name = row['CS Name']
            origin = (float(row['Origin_X']), float(row['Origin_Y']), float(row['Origin_Z']))
            x_dir = (float(row['X_dir_i']), float(row['X_dir_j']), float(row['X_dir_k']))
            y_dir = (float(row['Y_dir_i']), float(row['Y_dir_j']), float(row['Y_dir_k']))
            z_dir = (float(row['Z_dir_i']), float(row['Z_dir_j']), float(row['Z_dir_k']))
            coordinate_systems[cs_name] = {'origin': origin, 'x_dir': x_dir, 'y_dir': y_dir, 'z_dir': z_dir}

    return coordinate_systems

def transform_to_local(global_coords, local_cs):
    """Transforms global coordinates to local coordinates using the local coordinate system."""
    origin = local_cs['origin']
    x_dir = local_cs['x_dir']
    y_dir = local_cs['y_dir']
    z_dir = local_cs['z_dir']

    # Convert global coordinates from meters to millimeters
    global_coords_mm = [coord * 1000 for coord in global_coords]

    # Translate global coordinates by subtracting the origin
    translated_coords = [
        global_coords_mm[0] - origin[0],
        global_coords_mm[1] - origin[1],
        global_coords_mm[2] - origin[2]
    ]

    # Project the translated coordinates onto the local axes
    x_local = sum(translated_coords[i] * x_dir[i] for i in range(3))
    y_local = sum(translated_coords[i] * y_dir[i] for i in range(3))
    z_local = sum(translated_coords[i] * z_dir[i] for i in range(3))

    return (x_local, y_local, z_local)

def create_CSV_files_for_SG_grid_bodies_in_local_CS():
    # File paths
    solution_directory_path = sol_selected_environment.WorkingDir
    subfolder = os.path.join(solution_directory_path, "StrainX_around_each_SG")
    cs_matrix_file = os.path.join(subfolder, 'SG_coordinate_matrix.csv')
    local_vertices_file = os.path.join(subfolder, 'SG_grid_body_vertices_in_local_CS.csv')

    # Parse coordinate systems
    coordinate_systems = parse_coordinate_matrix(cs_matrix_file)

    # Get bodies
    list_of_all_bodies_in_tree = DataModel.GetObjectsByType(DataModelObjectCategory.Body)
    list_of_SG_grid_bodies = [
        (each_body.GetGeoBody().Name, each_body.GetGeoBody().Vertices)
        for each_body in list_of_all_bodies_in_tree
        if each_body.Name.Contains("SG_Grid_Body_")
    ]

    geo_data_SG_local = []

    # Transform each vertex to the local coordinate system
    for each_SG_body in list_of_SG_grid_bodies:
        body_name = each_SG_body[0]
        body_vertices = each_SG_body[1]

        # Correctly extract the coordinate system name
        cs_name = body_name.replace("SG_Grid_Body_", "CS_SG_Ch_")

        local_cs = coordinate_systems.get(cs_name, None)

        if not local_cs:
            print("No coordinate system found for {}".format(cs_name))
            continue

        for j, each_vertex in enumerate(body_vertices):
            local_coords = transform_to_local((each_vertex.X, each_vertex.Y, each_vertex.Z), local_cs)
            geo_data_SG_local.append({
                'Body_Name': body_name,
                'Vertex_No': j+1,
                'X_local [mm]': local_coords[0],
                'Y_local [mm]': local_coords[1],
                'Z_local [mm]': local_coords[2]
            })

    # Save to CSV
    with open(local_vertices_file, 'wb') as csvfile:
        fieldnames = ["Body_Name", "Vertex_No", "X_local [mm]", "Y_local [mm]", "Z_local [mm]"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(geo_data_SG_local)

    print("Local coordinates saved to {}".format(local_vertices_file))

# region Main execution
initialize_mechanical_preferences()

list_of_NS_of_nodes_around_each_SG, list_of_StrainX_around_each_SG = get_named_selections()
handle_existing_NS(list_of_NS_of_nodes_around_each_SG, list_of_StrainX_around_each_SG)

NS_faces_test_parts, NS_faces_test_parts_not_found = check_test_parts_existence()
NS_faces_test_parts = ensure_test_piece_defined(NS_faces_test_parts, NS_faces_test_parts_not_found)

list_of_ids_of_each_CS_SG_Ch_, list_of_names_of_each_CS_SG_Ch_ = get_CS_SG_ids_and_names()

radius = prompt_user_for_radius()
time_value = prompt_user_for_displayed_time()
time_preload = prompt_user_for_preload_time(time_value)

list_of_NS_test_part_strains = create_NS_of_nodes_around_SG(NS_faces_test_parts, list_of_ids_of_each_CS_SG_Ch_, list_of_names_of_each_CS_SG_Ch_, radius)
create_contour_plot_of_strains(list_of_names_of_each_CS_SG_Ch_, list_of_ids_of_each_CS_SG_Ch_, list_of_NS_test_part_strains, time_value)

list_of_obj_of_NS_of_nodes_around_each_SG = [
    obj for obj in DataModel.Project.GetChildren(DataModelObjectCategory.NamedSelection, True) if obj.Name.Contains("NS_of_nodes_around_")
]
list_of_obj_of_StrainX_around = [
    obj for obj in DataModel.Project.GetChildren(DataModelObjectCategory.NormalElasticStrain, True) if obj.Name.Contains("StrainX_around_")
]

group_existing_objects(list_of_obj_of_NS_of_nodes_around_each_SG, list_of_obj_of_StrainX_around)
evaluate_all_results()

create_CSV_files_from_strain_results(list_of_obj_of_StrainX_around, time_preload, time_value)
create_CSV_files_for_SG_grid_bodies_in_global_CS()
create_CSV_files_for_coordinate_system()
create_CSV_files_for_SG_grid_bodies_in_local_CS()
# endregion
