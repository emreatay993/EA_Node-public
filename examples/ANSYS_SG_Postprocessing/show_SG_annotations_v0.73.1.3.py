# region Import necessary libraries
import re
import csv
import os
import System
from System.Windows.Forms import (Form, ComboBox, Button, Label,
                                  Application, MessageBox, MessageBoxButtons,
                                  MessageBoxIcon, DialogResult, OpenFileDialog,
                                  Keys, TextBox, CheckBox, FormStartPosition)
from System.Drawing import Font, FontStyle, Color, Size
from System.Drawing import Point as GUI_Point
# endregion

#--------------------------------------------------------------------------------------------

# region Class definition(s) for GUI
class DataSelectionForm(Form):
    def __init__(self, times, measurements):
        self.Text = "Data Selection"
        self.Width = 300
        self.Height = 380
        self.BackColor = Color.White

        # Define GUI fonts
        label_font = Font("Segoe UI", 10, FontStyle.Bold)
        combobox_font = Font("Segoe UI", 10, FontStyle.Regular)

        # Label for the time selection ComboBox
        self.timeLabel = Label()
        self.timeLabel.Text = "Select a time point"
        self.timeLabel.Location = GUI_Point(30, 20)
        self.timeLabel.Size = Size(240, 20)
        self.timeLabel.Font = label_font
        self.timeLabel.ForeColor = Color.LightSkyBlue
        self.timeLabel.Parent = self

        # Time selection ComboBox
        self.timeCombo = ComboBox()
        self.timeCombo.Parent = self
        self.timeCombo.Location = GUI_Point(30, 40)
        self.timeCombo.Size = Size(240, 30)
        self.timeCombo.Font = combobox_font
        self.timeCombo.ForeColor = Color.Black
        [self.timeCombo.Items.Add(time) for time in times]
        self.timeCombo.SelectedIndex = 0

        # Label for the measurement type selection ComboBox
        self.measurementLabel = Label()
        self.measurementLabel.Text = "Select a result set"
        self.measurementLabel.Location = GUI_Point(30, 80)
        self.measurementLabel.Size = Size(240, 20)
        self.measurementLabel.Font = label_font
        self.measurementLabel.ForeColor = Color.LightSkyBlue
        self.measurementLabel.Parent = self

        # Measurement type selection ComboBox
        self.measurementCombo = ComboBox()
        self.measurementCombo.Parent = self
        self.measurementCombo.Location = GUI_Point(30, 100)
        self.measurementCombo.Size = Size(240, 30)
        self.measurementCombo.Font = combobox_font
        self.measurementCombo.ForeColor = Color.Black
        [self.measurementCombo.Items.Add(m) for m in measurements]
        self.measurementCombo.SelectedIndex = 0

        # Checkbox for deleting existing labels
        self.deleteCheckbox = CheckBox()
        self.deleteCheckbox.Text = "Delete existing labels"
        self.deleteCheckbox.Location = GUI_Point(30, 140)
        self.deleteCheckbox.Size = Size(240, 20)
        self.deleteCheckbox.Font = combobox_font
        self.deleteCheckbox.Parent = self

        # Checkbox for setting the same color for all labels
        self.sameColorCheckbox = CheckBox()
        self.sameColorCheckbox.Text = "Set same color for all labels"
        self.sameColorCheckbox.Location = GUI_Point(30, 170)
        self.sameColorCheckbox.Size = Size(240, 20)
        self.sameColorCheckbox.Font = combobox_font
        self.sameColorCheckbox.Parent = self

        # Checkbox for labels always stay on screen
        self.alwaysOnScreenCheckbox = CheckBox()
        self.alwaysOnScreenCheckbox.Text = "Labels always stay on the screen"
        self.alwaysOnScreenCheckbox.Location = GUI_Point(30, 200)
        self.alwaysOnScreenCheckbox.Size = Size(240, 20)
        self.alwaysOnScreenCheckbox.Font = combobox_font
        self.alwaysOnScreenCheckbox.ForeColor = Color.Black
        self.alwaysOnScreenCheckbox.Parent = self

        # Checkbox for appending time value to the label note
        self.appendTimeCheckbox = CheckBox()
        self.appendTimeCheckbox.Text = "Append time value to label note"
        self.appendTimeCheckbox.Location = GUI_Point(30, 230)
        self.appendTimeCheckbox.Size = Size(240, 20)
        self.appendTimeCheckbox.Font = combobox_font
        self.appendTimeCheckbox.ForeColor = Color.Black
        self.appendTimeCheckbox.Parent = self

        # Checkbox for adding a custom note all label notes
        self.customLabelCheckbox = CheckBox()
        self.customLabelCheckbox.Text = "Add a custom note to each label"
        self.customLabelCheckbox.Location = GUI_Point(30, 260)
        self.customLabelCheckbox.Size = Size(240, 20)
        self.customLabelCheckbox.Font = combobox_font
        self.customLabelCheckbox.Parent = self

        # OK Button
        self.okButton = Button()
        self.okButton.Text = "OK"
        self.okButton.Font = label_font
        self.okButton.ForeColor = Color.Black
        self.okButton.BackColor = Color.LightSkyBlue
        self.okButton.Location = GUI_Point(100, 290)
        self.okButton.Size = Size(100, 30)
        self.okButton.Parent = self
        self.okButton.Click += self.button_clicked

        # Enable KeyPreview to catch key events before they reach other controls
        self.KeyPreview = True

        # Handle key down events on the form
        self.KeyDown += self.form_key_down

        # Handle form closing event
        self.FormClosing += self.on_form_closing

    def button_clicked(self, sender, args):
        # Actions to perform when OK button is clicked
        self.perform_actions()

    def form_key_down(self, sender, args):
        # Check if the Enter key was pressed
        if args.KeyCode == Keys.Enter:
            # Prevent further processing of the key event
            args.Handled = True
            # Perform the same actions as clicking the OK button
            self.perform_actions()

    def perform_actions(self):
        # Common actions to perform (previously in button_clicked)
        global time_value, measurement_type, measurement_suffix, labels_always_on_screen, append_time, list_of_requested_SG_label_result, custom_label, color_list
        time_value = float(self.timeCombo.SelectedItem)
        measurement_type = self.measurementCombo.SelectedItem
        measurement_suffix = measurement_suffixes.get(measurement_type, '')

        # Check if the deleteCheckbox is checked and delete existing labels if true
        if self.deleteCheckbox.Checked:
            list_of_obj_of_SG_label_calculation = [
                label_manager.Labels[i]
                for i in range(len(label_manager.Labels))
                if label_manager.Labels[i].Note.Contains("SG_")
            ]
            label_manager.DeleteLabels(list_of_obj_of_SG_label_calculation)

        labels_always_on_screen = self.alwaysOnScreenCheckbox.Checked
        append_time = self.appendTimeCheckbox.Checked

        # Check if the customLabelCheckbox is checked and prompt for the suffix if true
        custom_label = ''
        if self.customLabelCheckbox.Checked:
            custom_label = InputBox.show("Enter a custom note for all labels:")

        # Perform the main processing logic
        list_of_requested_SG_label_result = read_row_based_on_time_and_measurement(file_path_of_SG_calculations, time_value, measurement_type)
        list_of_requested_SG_label_result = [round(num, 2) for num in list_of_requested_SG_label_result]  # round off the results to two significant digits
        # Determine the color scheme of labels based on calculated SG data
        color_list = numbers_to_rainbow_colors(list_of_requested_SG_label_result)
        # Create SG labels on the screen
        self.create_labels(list_of_requested_SG_label_result, color_list)
        # Keep the GUI open and set focus back to the ComboBox
        self.timeCombo.Focus()

    def create_labels(self, results, colors):
        # Define whether labels will always stay on the screen
        global list_of_obj_of_SG_label_calculation

        # Refractoring collector list for a better readability of the code
        xyz_list = list_of_coordinates_of_all_filtered_names_of_CS_SG_channels
        # Initialize list of label objects
        list_of_obj_of_SG_label_calculation = []

        with Graphics.Suspend():
            with Transaction():
                for i in range(len(xyz_list)):
                    obj_of_SG_label_calculation = label_manager.CreateLabel(sol_selected_environment)
                    note_text = "SG_" + str(list_of_SG_reference_numbers[i]) + ": " + str(list_of_requested_SG_label_result[i]) + measurement_suffix

                    # Append the time value to the label note if the checkbox is checked
                    if append_time:
                        note_text += " @" + str(time_value) + "s"

                    # Append the string suffix to the label note if the checkbox is checked
                    if custom_label:
                        note_text += " " + '"'+ custom_label + '"'

                    obj_of_SG_label_calculation.Note = note_text
                    obj_of_SG_label_calculation.Scoping.XYZ = Point((xyz_list[i][0], xyz_list[i][1], xyz_list[i][2]), 'm')

                    # Check if labels should always stay on the screen
                    obj_of_SG_label_calculation.ShowAlways = labels_always_on_screen

                    # Set the color for the label
                    if form.sameColorCheckbox.Checked:
                        label_color = (255, 253, 208)  # Light beige paper-like color
                    else:
                        label_color = color_list[i]

                    obj_of_SG_label_calculation.Color = Ansys.ACT.Common.Graphics.Color(red=label_color[0],
                                                                                        green=label_color[1],
                                                                                        blue=label_color[2],
                                                                                        alpha=0)
                    list_of_obj_of_SG_label_calculation.append(obj_of_SG_label_calculation)

    def on_form_closing(self, sender, args):
        global form_closed
        form_closed = True

class InputBox(Form):
    def __init__(self, prompt):
        self.Text = "Input Box"
        self.Width = 300
        self.Height = 150
        self.StartPosition = FormStartPosition.CenterParent

        self.promptLabel = Label()
        self.promptLabel.Text = prompt
        self.promptLabel.Location = GUI_Point(10, 10)
        self.promptLabel.Size = Size(260, 20)
        self.promptLabel.Parent = self

        self.inputTextBox = TextBox()
        self.inputTextBox.Location = GUI_Point(10, 40)
        self.inputTextBox.Size = Size(260, 20)
        self.inputTextBox.Parent = self

        self.okButton = Button()
        self.okButton.Text = "OK"
        self.okButton.Location = GUI_Point(100, 70)
        self.okButton.Size = Size(100, 30)
        self.okButton.Parent = self
        self.okButton.Click += self.on_ok_click

        self.KeyPreview = True  # Enable KeyPreview to capture key events
        self.KeyDown += self.input_form_key_down  # Handle key down events on the form

    def on_ok_click(self, sender, args):
        self.DialogResult = DialogResult.OK
        self.Close()

    def input_form_key_down(self, sender, args):
        # Check if the Enter key was pressed
        if args.KeyCode == Keys.Enter:
            # Prevent further processing of the key event
            args.Handled = True
            # Perform the same actions as clicking the OK button
            self.on_ok_click(sender, args)

    @staticmethod
    def show(prompt):
        input_box = InputBox(prompt)
        if input_box.ShowDialog() == DialogResult.OK:
            return input_box.inputTextBox.Text
        return None
# endregion

#--------------------------------------------------------------------------------------------

# region Global function and variable definitions
form_closed = False
label_manager = Graphics.LabelManager

# Extract the number from the channel name for sorting
def extract_number(channel_name):
    match = re.search(r'CS_SG_Ch_(\d+)_2', channel_name)
    return int(match.group(1)) if match else 0
# Create a color scale for the labels to be generated
def interpolate_segment(color1, color2, segment_fraction):
    return tuple(color1[i] + (color2[i] - color1[i]) * segment_fraction for i in range(3))

def get_rainbow_color(value, min_val, max_val):
    # Define the color range for the gradient
    colors = [
             (255, 0, 0),
             (255, 178, 0),
             (255, 216, 0),
             (255, 255, 0),
             (216, 255, 0),
             (178, 255, 0),
             (89, 255, 0),
             (0, 255, 0),
             (0, 255, 89),
             (0, 255, 178),
             (0, 255, 216),
             (0, 255, 255),
             (0, 216, 255),
             (0, 178, 255),
             (0, 89, 255),
             (0, 0, 255),
             (0, 0, 255),
             (153, 153, 102)]
    # Reverse the color order so that colors go from violet-blue to red as they increase
    colors.reverse()

    # Handle the case where min_val and max_val are equal to avoid division by zero
    if min_val == max_val:
        return colors[0]  # Return the last color in the gradient

    # Determine how many segments there are
    num_segments = len(colors) - 1

    # Scale the value to the number of segments
    scaled_value = float(value - min_val) / float(max_val - min_val) * num_segments

    # Determine which two colors to interpolate between
    first_color_index = int(scaled_value)
    second_color_index = min(first_color_index + 1, num_segments)

    # Determine the fraction between the two colors
    segment_fraction = scaled_value - first_color_index

    # Interpolate between the two colors
    return interpolate_segment(colors[first_color_index], colors[second_color_index], segment_fraction)

def numbers_to_rainbow_colors(numbers):
    min_val = min(numbers)
    max_val = max(numbers)

    # Generate a color for each number
    colors = [get_rainbow_color(num, min_val, max_val) for num in numbers]

    # Convert to RGB format as integers from 0 to 255
    rgb_colors = [(int(r), int(g), int(b)) for r, g, b in colors]

    return rgb_colors

# Function to classify headers based on measurement types
def classify_headers_by_measurement(file_path):
    with open(file_path, 'r') as file:
        reader = csv.reader(file)
        headers = next(reader)  # Read the header row
        measurements = {}  # Dictionary to store measurement types and indices

        # Updated regex to include optional delta and percent symbols
        pattern_measurement = re.compile(r'([?%]?SG\d+_(\w+))')

        for index, header in enumerate(headers):
            match = pattern_measurement.search(header)
            if match:
                measurement = match.group(2)  # Extracts the measurement type without the SG identifier
                if match.group(1).startswith(('Δ', '%')):
                    measurement = match.group(1)[0] + measurement
                if measurement not in measurements:
                    measurements[measurement] = []
                measurements[measurement].append(index)
            elif "Time" in header:
                if "Time" not in measurements:
                    measurements["Time"] = []
                measurements["Time"].append(index)

    return measurements

# Function to read a specific row based on "Time" and optionally filter by measurement type
def read_row_based_on_time_and_measurement(file_path, time_value, measurement_type=None):
    measurements = classify_headers_by_measurement(file_path)  # Get measurement groups
    with open(file_path, 'r') as file:
        reader = csv.reader(file)
        header = next(reader)
        time_index = header.index('Time')

        for row in reader:
            if float(row[time_index]) == float(time_value):
                if measurement_type:
                    # Filter for specific measurement type
                    indices = measurements.get(measurement_type, [])
                    return [float(row[i]) for i in indices]
                else:
                    # Return all values converted to float
                    return [float(value) for value in row]

# Function to classify headers and find unique time values
def prepare_data(file_path):
    times = set()  # Initialize a set to collect unique time points
    measurements = classify_headers_by_measurement(file_path)  # Get measurement types dynamically

    with open(file_path, 'r') as file:
        reader = csv.reader(file)
        header = next(reader)  # Skip the header
        for row in reader:
            time_value = row[0]  # Assuming the time value is in the first column
            if time_value:  # Ensure it's not an empty string
                try:
                    # Try to convert the time value to float to check if it's numeric
                    float(time_value)
                    times.add(time_value)
                except ValueError:
                    # Skip non-numeric values
                    continue

    # Convert times to floats for natural numerical sorting
    list_of_time_points = sorted(float(time) for time in times)

    # Create the list of measurement types which exist inside the data
    list_of_measurement_types = sorted(set(measurement for measurement in measurements.keys() if measurement != 'Time'))

    return list_of_time_points, list_of_measurement_types
# endregion

measurement_suffixes = {
    'epsilon_x': ', εx',
    'epsilon_y': ' , εy',
    'gamma_xy': ' , γxy',
    'sigma_1': ' , σ1',
    'sigma_2': ' , σ2',
    'theta_p': ' , θp',
    'Biaxiality_Ratio': ' , BR',
    'von_Mises': ' , VM',
    'Δepsilon_x': ' , Δεx',
    'Δepsilon_y': ' , Δεy',
    'Δgamma_xy': ' , Δγxy',
    'Δsigma_1': ' , Δσ1',
    'Δsigma_2': ' , Δσ2',
    'Δtheta_p': ' , Δθp',
    'ΔBiaxiality_Ratio': ' , ΔBR',
    'Δvon_Mises': ' , ΔVM',
    '%epsilon_x': ' , %εx',
    '%epsilon_y': ' , %εy',
    '%gamma_xy': ' , %γxy',
    '%sigma_1': ' , %σ1',
    '%sigma_2': ' , %σ2',
    '%theta_p': ' , %θp',
    '%Biaxiality_Ratio': ' , %BR',
    '%von_Mises': ' , %VM'
}
#--------------------------------------------------------------------------------------------

# region Filter the list of name of reference channels (in this case Ch_2) from each CS_SG_Ch object
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
# Sort the list of filtered names of CS_SG_Channels so that they are in natural order
list_of_filtered_names_of_CS_SG_channels.sort(key=extract_number)
# Extract SG reference numbers as well
list_of_SG_reference_numbers = [
    int(re.search(pattern, channel).group(1))  # Capture the group 1 which is the reference number
    for channel in list_of_filtered_names_of_CS_SG_channels if re.search(pattern, channel)]
# endregion

#--------------------------------------------------------------------------------------------

# region Get the corresponding objects from the tree and their coordinates
ExtAPI.Application.ActiveUnitSystem = MechanicalUnitSystem.StandardMKS  # Set the unit system as 'm,kg,N'
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

#--------------------------------------------------------------------------------------------

# region Configure the graphics settings
label_manager.LabelObscureStyle = MechanicalEnums.Graphics.ObscuredLabelStyle.eHiddenStyle
# endregion

#--------------------------------------------------------------------------------------------

# region Try to read the SG calculation results from solution folder path, if there is any file
solution_directory_path = sol_selected_environment.WorkingDir[:-1]
solution_directory_path = solution_directory_path.Replace("\\", "\\\\")
file_name_of_SG_calculations = 'SG_calculations.csv'
file_path_of_SG_calculations = os.path.join(solution_directory_path,file_name_of_SG_calculations)

if os.path.exists(file_path_of_SG_calculations):
    times, measurements = prepare_data(file_path_of_SG_calculations)
    form = DataSelectionForm(times, measurements)
    Application.Run(form)

    while True:
        Application.DoEvents()  # Process all Windows messages currently in the message queue
        # if 'time_value' in globals() and 'measurement_type' in globals():
        #     list_of_requested_SG_label_result = read_row_based_on_time_and_measurement(file_path_of_SG_calculations, time_value, measurement_type)
        #     list_of_requested_SG_label_result = [round(num, 2) for num in list_of_requested_SG_label_result]  # round off the results to two significant digits
        #     # Determine the color scheme of labels based on calculated SG data
        #     color_list = numbers_to_rainbow_colors(list_of_requested_SG_label_result)
        #     break  # Exit the loop once the values are set
        if form_closed:
            break  # Exit the loop if the form is closed

else:
    message = '"SG_calculations_FEA.csv" file is not found in the solution directory. Would you like to manually specify this file?'
    title = 'File Not Found'
    result = MessageBox.Show(message, title, MessageBoxButtons.YesNo, MessageBoxIcon.Warning)
    if result == DialogResult.Yes:
        file_dialog = OpenFileDialog()
        file_dialog.Filter = "CSV files (*.csv)|*.csv"
        file_dialog.Title = "Select a CSV file of SG Calculations"
        if file_dialog.ShowDialog() == DialogResult.OK:
            file_path_of_SG_calculations = file_dialog.FileName
            print("File selected:", file_path_of_SG_calculations)
            times, measurements = prepare_data(file_path_of_SG_calculations)
            form = DataSelectionForm(times, measurements)
            Application.Run(form)
        else:
            print("No files are selected. Only labels will be generated")
            list_of_requested_SG_label_result = [""] * len(list_of_coordinates_of_all_filtered_names_of_CS_SG_channels)
            # Determine the color scheme of labels based on SG numbers
            color_list = numbers_to_rainbow_colors(list_of_SG_reference_numbers)
            form.create_labels(list_of_requested_SG_label_result, color_list)
# endregion

ExtAPI.Application.ActiveUnitSystem = MechanicalUnitSystem.StandardNMM  # Revert the unit system back to 'mm,kg,N'
