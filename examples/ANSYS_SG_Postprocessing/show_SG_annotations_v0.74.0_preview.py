# region Import necessary libraries
import csv
import os
import re

import System
from System.Drawing import Color, Font, FontStyle, Size
from System.Drawing import Point as GUI_Point
from System.Windows.Forms import (
    Button,
    CheckBox,
    ComboBox,
    DialogResult,
    Form,
    FormStartPosition,
    Keys,
    Label,
    MessageBox,
    MessageBoxButtons,
    MessageBoxIcon,
    OpenFileDialog,
    ScrollBars,
    TextBox,
)
# endregion

# --------------------------------------------------------------------------------------------

SCRIPT_VERSION = "v0.74.0_preview"
CHANNEL_PATTERN = re.compile(r"CS_SG_Ch_(\d+)_2[^0-9]*")
HEADER_PATTERN = re.compile(r"^SG(\d+)_(.+)$")

PREFERRED_CSV_FILE_NAMES = [
    "SG_FEA_microstrain_data.csv",
    "SG_FEA_strain_data.csv",
    "SG_calculations.csv",
    "SG_calculations_FEA.csv",
]

SAME_LABEL_COLOR = (255, 253, 208)
NEUTRAL_LABEL_COLOR = (204, 224, 244)

DELTA_SYMBOL = u"\u0394"
UTF8_DELTA_BYTES = "\xce\x94"

MEASUREMENT_SUFFIXES = {
    "epsilon_x": ", epsilon_x",
    "epsilon_y": ", epsilon_y",
    "gamma_xy": ", gamma_xy",
    "sigma_1": ", sigma_1",
    "sigma_2": ", sigma_2",
    "theta_p": ", theta_p",
    "Biaxiality_Ratio": ", BR",
    "von_Mises": ", VM",
}

MEASUREMENT_DISPLAY_NAMES = {
    "epsilon_x": "epsilon_x",
    "epsilon_y": "epsilon_y",
    "gamma_xy": "gamma_xy",
    "sigma_1": "sigma_1",
    "sigma_2": "sigma_2",
    "theta_p": "theta_p",
    "Biaxiality_Ratio": "biaxiality ratio",
    "von_Mises": "von Mises",
}


# --------------------------------------------------------------------------------------------
# region Small data containers

class SGChannel(object):
    def __init__(self, reference_number, name, xyz):
        self.reference_number = reference_number
        self.name = name
        self.xyz = xyz


class MeasurementGroup(object):
    def __init__(self, key, display_name, suffix):
        self.key = key
        self.display_name = display_name
        self.suffix = suffix
        self.indices_by_ref = {}

    def add_index(self, reference_number, index):
        self.indices_by_ref[reference_number] = index


class CsvData(object):
    def __init__(self, file_path, file_kind, header, rows, time_index, time_values, groups):
        self.file_path = file_path
        self.file_kind = file_kind
        self.header = header
        self.rows = rows
        self.time_index = time_index
        self.time_values = time_values
        self.groups = groups


class AnnotationState(object):
    def __init__(self, solution_environment, csv_data, sg_channels):
        self.solution_environment = solution_environment
        self.csv_data = csv_data
        self.sg_channels = sg_channels


class ApplyOptions(object):
    def __init__(self, replace_existing, same_color, always_on_screen, append_time, custom_note):
        self.replace_existing = replace_existing
        self.same_color = same_color
        self.always_on_screen = always_on_screen
        self.append_time = append_time
        self.custom_note = custom_note

# endregion


# --------------------------------------------------------------------------------------------
# region Generic helpers

def contains_text(value, needle):
    if value is None:
        return False
    try:
        return value.Contains(needle)
    except Exception:
        return needle in str(value)


def safe_to_string(value):
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return value.ToString()


def starts_with(value, prefix):
    try:
        return value.startswith(prefix)
    except Exception:
        return False


def compact_float(value):
    try:
        number = float(value)
    except Exception:
        return safe_to_string(value)
    if abs(number - int(number)) < 1.0e-12:
        return str(int(number))
    return ("%g" % number)


def format_number(value):
    try:
        return compact_float(round(float(value), 2))
    except Exception:
        return safe_to_string(value)


def show_error(message):
    MessageBox.Show(message, "SG Annotation Error", MessageBoxButtons.OK, MessageBoxIcon.Error)


def show_info(message):
    MessageBox.Show(message, "SG Annotation", MessageBoxButtons.OK, MessageBoxIcon.Information)

# endregion


# --------------------------------------------------------------------------------------------
# region CSV parsing and result grouping

def infer_file_kind(file_path):
    name = os.path.basename(file_path).lower()
    if "microstrain" in name:
        return "microstrain"
    if "strain" in name:
        return "strain"
    return "calculation"


def split_header_prefix(header_name):
    text = header_name.strip()
    if starts_with(text, "%"):
        return "percent", text[1:]
    if starts_with(text, "?"):
        return "delta", text[1:]
    if starts_with(text, UTF8_DELTA_BYTES):
        return "delta", text[len(UTF8_DELTA_BYTES):]
    if starts_with(text, DELTA_SYMBOL):
        return "delta", text[len(DELTA_SYMBOL):]
    lower_text = text.lower()
    if lower_text.startswith("delta"):
        return "delta", text[5:]
    return "base", text


def pretty_measurement_name(token, prefix, file_kind):
    if token.isdigit():
        if file_kind == "microstrain":
            return "Channel %s (microstrain)" % token
        if file_kind == "strain":
            return "Channel %s (strain)" % token
        return "Channel %s" % token

    display = MEASUREMENT_DISPLAY_NAMES.get(token, token.replace("_", " "))
    if prefix == "delta":
        return "Delta %s" % display
    if prefix == "percent":
        return "Percent %s" % display
    return display


_UNIT_SUFFIX_RE = re.compile(r"\s*(\[[^\]]*\])\s*$")


def measurement_suffix(token, prefix, file_kind):
    if token.isdigit():
        if file_kind == "microstrain":
            return ", microstrain"
        if file_kind == "strain":
            return ", strain"
        return ", channel %s" % token

    # Split off a trailing unit (CSV result columns carry units like
    # [MPa]/[ue]/[deg]) so the short code is found, then re-attach the unit:
    # "von_Mises [MPa]" -> ", VM [MPa]" / ", %VM [MPa]" / ", delta VM [MPa]".
    unit_match = _UNIT_SUFFIX_RE.search(token)
    unit = " %s" % unit_match.group(1) if unit_match else ""
    name = _UNIT_SUFFIX_RE.sub("", token).strip()
    short = MEASUREMENT_SUFFIXES.get(name, ", %s" % name.replace("_", " "))[2:]
    if prefix == "delta":
        return ", delta %s%s" % (short, unit)
    if prefix == "percent":
        return ", %%%s%s" % (short, unit)
    return ", %s%s" % (short, unit)


def parse_result_header(header_name, index, file_kind):
    prefix, body = split_header_prefix(header_name)
    match = HEADER_PATTERN.match(body)
    if not match:
        return None

    reference_number = int(match.group(1))
    token = match.group(2).strip()
    if not token:
        return None

    key = "%s|%s" % (prefix, token)
    display_name = pretty_measurement_name(token, prefix, file_kind)
    suffix = measurement_suffix(token, prefix, file_kind)
    return reference_number, key, display_name, suffix, index


def read_csv_file(file_path):
    file_kind = infer_file_kind(file_path)
    with open(file_path, "r") as file:
        reader = csv.reader(file)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError("The CSV file is empty.")

        if "Time" not in header:
            raise ValueError("The CSV file must contain a 'Time' column.")
        time_index = header.index("Time")

        groups = {}
        for index, header_name in enumerate(header):
            if index == time_index:
                continue
            parsed = parse_result_header(header_name, index, file_kind)
            if parsed is None:
                continue
            reference_number, key, display_name, suffix, column_index = parsed
            if key not in groups:
                groups[key] = MeasurementGroup(key, display_name, suffix)
            groups[key].add_index(reference_number, column_index)

        rows = []
        unique_times = {}
        for row in reader:
            if len(row) <= time_index:
                continue
            try:
                time_value = float(row[time_index])
            except Exception:
                continue
            rows.append(row)
            unique_times[time_value] = True

    if not rows:
        raise ValueError("The CSV file does not contain any numeric time rows.")
    if not groups:
        raise ValueError("The CSV file does not contain supported SG result columns.")

    time_values = sorted(unique_times.keys())
    return CsvData(file_path, file_kind, header, rows, time_index, time_values, groups)


def find_default_csv(solution_directory_path):
    for file_name in PREFERRED_CSV_FILE_NAMES:
        candidate = os.path.join(solution_directory_path, file_name)
        if os.path.exists(candidate):
            return candidate
    return None


def choose_csv_file(solution_directory_path):
    default_file = find_default_csv(solution_directory_path)
    if default_file:
        return default_file

    message = (
        "No supported SG data CSV was found in the solution directory:\n\n"
        "%s\n\n"
        "Expected one of:\n%s\n\n"
        "Would you like to select a CSV file manually?"
    ) % (solution_directory_path, "\n".join(PREFERRED_CSV_FILE_NAMES))
    result = MessageBox.Show(message, "SG Data File Not Found", MessageBoxButtons.YesNo, MessageBoxIcon.Warning)
    if result != DialogResult.Yes:
        return None

    file_dialog = OpenFileDialog()
    file_dialog.Filter = "CSV files (*.csv)|*.csv"
    file_dialog.Title = "Select SG Data CSV"
    if file_dialog.ShowDialog() == DialogResult.OK:
        return file_dialog.FileName
    return None

# endregion


# --------------------------------------------------------------------------------------------
# region Mechanical model and label helpers

def extract_channel_number(channel_name):
    match = CHANNEL_PATTERN.search(channel_name)
    return int(match.group(1)) if match else 0


def discover_sg_channels():
    coordinate_systems = DataModel.Project.GetChildren(DataModelObjectCategory.CoordinateSystem, True)
    channel_names = []
    for coordinate_system in coordinate_systems:
        name = safe_to_string(coordinate_system.Name)
        if not CHANNEL_PATTERN.search(name):
            continue
        try:
            if coordinate_system.ObjectState == ObjectState.Suppressed:
                continue
        except Exception:
            pass
        channel_names.append(name)

    channel_names.sort(key=extract_channel_number)
    channels = []
    for name in channel_names:
        objects = DataModel.GetObjectsByName(name)
        if len(objects) == 0:
            continue
        transformed = safe_to_string(objects[0].TransformedConfiguration)
        coordinate_tokens = transformed.rsplit()[1:-1]
        if len(coordinate_tokens) < 3:
            continue
        xyz = [float(item) for item in coordinate_tokens[:3]]
        channels.append(SGChannel(extract_channel_number(name), name, xyz))
    return channels


def selected_row_for_time(csv_data, selected_time):
    for row in csv_data.rows:
        try:
            if abs(float(row[csv_data.time_index]) - float(selected_time)) < 1.0e-9:
                return row
        except Exception:
            pass
    return None


def format_missing_refs(missing_refs):
    preview = ", ".join([str(value) for value in missing_refs[:8]])
    if len(missing_refs) > 8:
        preview += ", ..."
    return preview


def values_for_selection(csv_data, sg_channels, selected_time, measurement_key):
    if measurement_key not in csv_data.groups:
        raise ValueError("The selected result set is not available.")

    group = csv_data.groups[measurement_key]
    row = selected_row_for_time(csv_data, selected_time)
    if row is None:
        raise ValueError("The selected time point was not found in the CSV data.")

    used_channels = []
    values = []
    missing_refs = []
    for channel in sg_channels:
        reference_number = channel.reference_number
        # Skip (rather than error on) any SG reference the CSV has no usable
        # result column/value for, so labelling continues for the rest.
        if reference_number not in group.indices_by_ref:
            missing_refs.append(reference_number)
            continue
        column_index = group.indices_by_ref[reference_number]
        if len(row) <= column_index:
            missing_refs.append(reference_number)
            continue
        try:
            value = float(row[column_index])
        except Exception:
            missing_refs.append(reference_number)
            continue
        used_channels.append(channel)
        values.append(value)

    if not used_channels:
        raise ValueError(
            "The CSV has no result columns for any of the %s SG reference(s) in this "
            "selection (missing: %s)." % (len(sg_channels), format_missing_refs(missing_refs)))

    return used_channels, values, group, missing_refs


def validate_ready_state(state):
    if not state.sg_channels:
        raise ValueError("No active coordinate systems named like CS_SG_Ch_<n>_2 were found.")
    if not state.csv_data.time_values:
        raise ValueError("No numeric time points were found in the CSV file.")
    if not state.csv_data.groups:
        raise ValueError("No supported SG result columns were found in the CSV file.")


def existing_labels():
    # Return every label currently in the scene; "Replace existing" removes all
    # previous labels (not only ones created by this script).
    label_manager = Graphics.LabelManager
    return [label_manager.Labels[index] for index in range(len(label_manager.Labels))]


def make_label_note(reference_number, value, group, selected_time, options):
    note_text = "SG_%s: %s%s" % (reference_number, format_number(value), group.suffix)
    if options.append_time:
        note_text += " @%ss" % compact_float(selected_time)
    if options.custom_note:
        note_text += ' "%s"' % options.custom_note
    return note_text


def interpolate_segment(color1, color2, segment_fraction):
    return tuple(color1[i] + (color2[i] - color1[i]) * segment_fraction for i in range(3))


def rainbow_color(value, min_val, max_val):
    colors = [
        (153, 153, 102),
        (0, 0, 255),
        (0, 89, 255),
        (0, 178, 255),
        (0, 216, 255),
        (0, 255, 255),
        (0, 255, 216),
        (0, 255, 178),
        (0, 255, 89),
        (0, 255, 0),
        (89, 255, 0),
        (178, 255, 0),
        (216, 255, 0),
        (255, 255, 0),
        (255, 216, 0),
        (255, 178, 0),
        (255, 0, 0),
    ]
    if min_val == max_val:
        return NEUTRAL_LABEL_COLOR

    num_segments = len(colors) - 1
    scaled_value = float(value - min_val) / float(max_val - min_val) * num_segments
    first_color_index = int(scaled_value)
    second_color_index = min(first_color_index + 1, num_segments)
    segment_fraction = scaled_value - first_color_index
    return interpolate_segment(colors[first_color_index], colors[second_color_index], segment_fraction)


def colors_for_values(values, same_color):
    if same_color:
        return [SAME_LABEL_COLOR for value in values]
    if not values:
        return []
    min_val = min(values)
    max_val = max(values)
    return [(int(r), int(g), int(b)) for r, g, b in [rainbow_color(value, min_val, max_val) for value in values]]


def apply_labels(state, selected_time, measurement_key, options):
    used_channels, values, group, missing_refs = values_for_selection(
        state.csv_data, state.sg_channels, selected_time, measurement_key)
    color_list = colors_for_values(values, options.same_color)
    label_manager = Graphics.LabelManager
    deleted_count = 0
    created_labels = []

    with Graphics.Suspend():
        with Transaction():
            if options.replace_existing:
                labels_to_delete = existing_labels()
                deleted_count = len(labels_to_delete)
                if labels_to_delete:
                    label_manager.DeleteLabels(labels_to_delete)

            for index, channel in enumerate(used_channels):
                label = label_manager.CreateLabel(state.solution_environment)
                label.Note = make_label_note(channel.reference_number, values[index], group, selected_time, options)
                label.Scoping.XYZ = Point((channel.xyz[0], channel.xyz[1], channel.xyz[2]), "m")
                label.ShowAlways = options.always_on_screen
                color = color_list[index]
                label.Color = Ansys.ACT.Common.Graphics.Color(
                    red=color[0],
                    green=color[1],
                    blue=color[2],
                    alpha=0,
                )
                created_labels.append(label)

    return len(created_labels), deleted_count, min(values), max(values), missing_refs

# endregion


# --------------------------------------------------------------------------------------------
# region GUI

class AnnotationForm(Form):
    def __init__(self, state):
        self.state = state
        self.measurement_key_by_display = {}

        self.Text = "SG Annotation Labels %s" % SCRIPT_VERSION
        self.Width = 560
        self.Height = 535
        self.StartPosition = FormStartPosition.CenterScreen
        self.BackColor = Color.White

        label_font = Font("Segoe UI", 9, FontStyle.Regular)
        heading_font = Font("Segoe UI", 10, FontStyle.Bold)
        button_font = Font("Segoe UI", 9, FontStyle.Bold)
        status_font = Font("Segoe UI", 9, FontStyle.Regular)

        self.titleLabel = Label()
        self.titleLabel.Text = "Create SG result labels"
        self.titleLabel.Location = GUI_Point(20, 15)
        self.titleLabel.Size = Size(500, 24)
        self.titleLabel.Font = Font("Segoe UI", 12, FontStyle.Bold)
        self.titleLabel.ForeColor = Color.FromArgb(30, 80, 120)
        self.titleLabel.Parent = self

        self.fileLabel = Label()
        self.fileLabel.Text = "Data file"
        self.fileLabel.Location = GUI_Point(20, 45)
        self.fileLabel.Size = Size(510, 18)
        self.fileLabel.Font = label_font
        self.fileLabel.ForeColor = Color.Black
        self.fileLabel.Parent = self

        self.filePathTextBox = TextBox()
        self.filePathTextBox.Text = self.state.csv_data.file_path
        self.filePathTextBox.Location = GUI_Point(20, 65)
        self.filePathTextBox.Size = Size(510, 46)
        self.filePathTextBox.Font = label_font
        self.filePathTextBox.Multiline = True
        self.filePathTextBox.ReadOnly = True
        self.filePathTextBox.WordWrap = False
        self.filePathTextBox.ScrollBars = ScrollBars.Horizontal
        self.filePathTextBox.Parent = self

        self.summaryLabel = Label()
        self.summaryLabel.Text = self.build_file_summary()
        self.summaryLabel.Location = GUI_Point(20, 120)
        self.summaryLabel.Size = Size(510, 24)
        self.summaryLabel.Font = label_font
        self.summaryLabel.ForeColor = Color.DimGray
        self.summaryLabel.Parent = self

        self.timeLabel = Label()
        self.timeLabel.Text = "Time point"
        self.timeLabel.Location = GUI_Point(20, 160)
        self.timeLabel.Size = Size(230, 20)
        self.timeLabel.Font = heading_font
        self.timeLabel.ForeColor = Color.FromArgb(30, 80, 120)
        self.timeLabel.Parent = self

        self.timeCombo = ComboBox()
        self.timeCombo.Parent = self
        self.timeCombo.Location = GUI_Point(20, 183)
        self.timeCombo.Size = Size(230, 30)
        self.timeCombo.Font = label_font
        for time_value in self.state.csv_data.time_values:
            self.timeCombo.Items.Add(compact_float(time_value))
        if self.timeCombo.Items.Count > 0:
            self.timeCombo.SelectedIndex = 0
        self.timeCombo.SelectedIndexChanged += self.selection_changed

        self.measurementLabel = Label()
        self.measurementLabel.Text = "Result set"
        self.measurementLabel.Location = GUI_Point(285, 160)
        self.measurementLabel.Size = Size(230, 20)
        self.measurementLabel.Font = heading_font
        self.measurementLabel.ForeColor = Color.FromArgb(30, 80, 120)
        self.measurementLabel.Parent = self

        self.measurementCombo = ComboBox()
        self.measurementCombo.Parent = self
        self.measurementCombo.Location = GUI_Point(285, 183)
        self.measurementCombo.Size = Size(230, 30)
        self.measurementCombo.Font = label_font
        self.populate_measurements()
        self.measurementCombo.SelectedIndexChanged += self.selection_changed

        self.replaceCheckbox = CheckBox()
        self.replaceCheckbox.Text = "Replace all existing labels"
        self.replaceCheckbox.Location = GUI_Point(20, 235)
        self.replaceCheckbox.Size = Size(330, 24)
        self.replaceCheckbox.Font = label_font
        self.replaceCheckbox.Checked = True
        self.replaceCheckbox.Parent = self

        self.sameColorCheckbox = CheckBox()
        self.sameColorCheckbox.Text = "Use one readable color for all labels"
        self.sameColorCheckbox.Location = GUI_Point(20, 263)
        self.sameColorCheckbox.Size = Size(330, 24)
        self.sameColorCheckbox.Font = label_font
        self.sameColorCheckbox.Parent = self
        self.sameColorCheckbox.CheckedChanged += self.selection_changed

        self.alwaysOnScreenCheckbox = CheckBox()
        self.alwaysOnScreenCheckbox.Text = "Keep labels on screen"
        self.alwaysOnScreenCheckbox.Location = GUI_Point(20, 291)
        self.alwaysOnScreenCheckbox.Size = Size(330, 24)
        self.alwaysOnScreenCheckbox.Font = label_font
        self.alwaysOnScreenCheckbox.Parent = self

        self.appendTimeCheckbox = CheckBox()
        self.appendTimeCheckbox.Text = "Append selected time to label note"
        self.appendTimeCheckbox.Location = GUI_Point(20, 319)
        self.appendTimeCheckbox.Size = Size(330, 24)
        self.appendTimeCheckbox.Font = label_font
        self.appendTimeCheckbox.Parent = self

        self.customLabelCheckbox = CheckBox()
        self.customLabelCheckbox.Text = "Append custom note"
        self.customLabelCheckbox.Location = GUI_Point(20, 347)
        self.customLabelCheckbox.Size = Size(160, 24)
        self.customLabelCheckbox.Font = label_font
        self.customLabelCheckbox.Parent = self
        self.customLabelCheckbox.CheckedChanged += self.custom_label_changed

        self.customLabelTextBox = TextBox()
        self.customLabelTextBox.Location = GUI_Point(185, 347)
        self.customLabelTextBox.Size = Size(330, 24)
        self.customLabelTextBox.Font = label_font
        self.customLabelTextBox.Enabled = False
        self.customLabelTextBox.Parent = self

        self.previewLabel = Label()
        self.previewLabel.Text = ""
        self.previewLabel.Location = GUI_Point(20, 385)
        self.previewLabel.Size = Size(510, 24)
        self.previewLabel.Font = label_font
        self.previewLabel.ForeColor = Color.DimGray
        self.previewLabel.Parent = self

        self.statusLabel = Label()
        self.statusLabel.Text = "Ready."
        self.statusLabel.Location = GUI_Point(20, 413)
        self.statusLabel.Size = Size(510, 42)
        self.statusLabel.Font = status_font
        self.statusLabel.ForeColor = Color.FromArgb(30, 80, 120)
        self.statusLabel.Parent = self

        self.applyButton = Button()
        self.applyButton.Text = "Apply Labels"
        self.applyButton.Font = button_font
        self.applyButton.ForeColor = Color.Black
        self.applyButton.BackColor = Color.LightSkyBlue
        self.applyButton.Location = GUI_Point(285, 460)
        self.applyButton.Size = Size(115, 32)
        self.applyButton.Parent = self
        self.applyButton.Click += self.apply_clicked

        self.closeButton = Button()
        self.closeButton.Text = "Close"
        self.closeButton.Font = button_font
        self.closeButton.ForeColor = Color.Black
        self.closeButton.Location = GUI_Point(415, 460)
        self.closeButton.Size = Size(100, 32)
        self.closeButton.Parent = self
        self.closeButton.Click += self.close_clicked

        self.KeyPreview = True
        self.KeyDown += self.form_key_down
        self.update_preview()

    def build_file_summary(self):
        return "%s SG channels | %s time points | %s result sets" % (
            len(self.state.sg_channels),
            len(self.state.csv_data.time_values),
            len(self.state.csv_data.groups),
        )

    def populate_measurements(self):
        keys = sorted(self.state.csv_data.groups.keys(), key=lambda key: self.state.csv_data.groups[key].display_name)
        for key in keys:
            display = self.state.csv_data.groups[key].display_name
            final_display = display
            suffix = 2
            while final_display in self.measurement_key_by_display:
                final_display = "%s (%s)" % (display, suffix)
                suffix += 1
            self.measurement_key_by_display[final_display] = key
            self.measurementCombo.Items.Add(final_display)
        if self.measurementCombo.Items.Count > 0:
            self.measurementCombo.SelectedIndex = 0

    def selected_time(self):
        return float(self.timeCombo.SelectedItem)

    def selected_measurement_key(self):
        return self.measurement_key_by_display[safe_to_string(self.measurementCombo.SelectedItem)]

    def current_options(self):
        custom_note = ""
        if self.customLabelCheckbox.Checked:
            custom_note = safe_to_string(self.customLabelTextBox.Text).strip()
        return ApplyOptions(
            self.replaceCheckbox.Checked,
            self.sameColorCheckbox.Checked,
            self.alwaysOnScreenCheckbox.Checked,
            self.appendTimeCheckbox.Checked,
            custom_note,
        )

    def selection_changed(self, sender, args):
        self.update_preview()

    def custom_label_changed(self, sender, args):
        self.customLabelTextBox.Enabled = self.customLabelCheckbox.Checked
        if self.customLabelCheckbox.Checked:
            self.customLabelTextBox.Focus()
        self.update_preview()

    def update_preview(self):
        try:
            if self.timeCombo.SelectedItem is None or self.measurementCombo.SelectedItem is None:
                self.previewLabel.Text = "Select a time point and result set."
                return
            used_channels, values, group, missing_refs = values_for_selection(
                self.state.csv_data,
                self.state.sg_channels,
                self.selected_time(),
                self.selected_measurement_key(),
            )
            range_text = "Range %s to %s" % (format_number(min(values)), format_number(max(values)))
            if min(values) == max(values):
                range_text += " | one neutral color will be used"
            elif self.sameColorCheckbox.Checked:
                range_text += " | one readable color selected"
            preview_text = "%s labels will be created. %s." % (len(values), range_text)
            if missing_refs:
                preview_text += (" %s SG reference(s) missing from the CSV will be skipped: %s."
                                 % (len(missing_refs), format_missing_refs(missing_refs)))
            self.previewLabel.Text = preview_text
        except Exception as exc:
            self.previewLabel.Text = safe_to_string(exc)

    def apply_clicked(self, sender, args):
        try:
            created_count, deleted_count, min_value, max_value, missing_refs = apply_labels(
                self.state,
                self.selected_time(),
                self.selected_measurement_key(),
                self.current_options(),
            )
            status = "Created %s labels" % created_count
            if deleted_count:
                status += " after deleting %s existing labels" % deleted_count
            if min_value == max_value and not self.sameColorCheckbox.Checked:
                status += ". Values are equal, so neutral label color was used"
            status += "."
            if missing_refs:
                status += (" Skipped %s SG reference(s) missing from the CSV: %s."
                           % (len(missing_refs), format_missing_refs(missing_refs)))
            self.statusLabel.ForeColor = Color.FromArgb(30, 100, 50)
            self.statusLabel.Text = status
            self.update_preview()
        except Exception as exc:
            self.statusLabel.ForeColor = Color.Firebrick
            self.statusLabel.Text = safe_to_string(exc)

    def close_clicked(self, sender, args):
        self.Close()

    def form_key_down(self, sender, args):
        if args.KeyCode == Keys.Enter:
            args.Handled = True
            self.apply_clicked(sender, args)
        elif args.KeyCode == Keys.Escape:
            args.Handled = True
            self.Close()

# endregion


# --------------------------------------------------------------------------------------------
# region Main workflow

def build_state():
    solution_environment = sol_selected_environment
    solution_directory_path = safe_to_string(solution_environment.WorkingDir)
    csv_file_path = choose_csv_file(solution_directory_path)
    if not csv_file_path:
        return None

    csv_data = read_csv_file(csv_file_path)
    sg_channels = discover_sg_channels()
    state = AnnotationState(solution_environment, csv_data, sg_channels)
    validate_ready_state(state)
    return state


def run_annotation_tool():
    state = build_state()
    if state is None:
        show_info("No SG labels were created.")
        return

    form = AnnotationForm(state)
    form.ShowDialog()


original_unit_system = None
try:
    original_unit_system = ExtAPI.Application.ActiveUnitSystem
    ExtAPI.Application.ActiveUnitSystem = MechanicalUnitSystem.StandardMKS
    run_annotation_tool()
except Exception as exc:
    show_error(safe_to_string(exc))
finally:
    try:
        if original_unit_system is not None:
            ExtAPI.Application.ActiveUnitSystem = original_unit_system
        else:
            ExtAPI.Application.ActiveUnitSystem = MechanicalUnitSystem.StandardNMM
    except Exception:
        pass

# endregion
