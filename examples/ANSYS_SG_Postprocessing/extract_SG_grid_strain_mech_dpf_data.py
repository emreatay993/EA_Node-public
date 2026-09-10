# region Import necessary libraries
import csv
import os
import re
import sys
import time

import clr
import mech_dpf
import Ans.DataProcessing as dpf
clr.AddReference("System.Drawing")
clr.AddReference("System.Windows.Forms")
from System.Drawing import Point, Size
from System.Windows.Forms import (
    Application,
    Button,
    ComboBox,
    ComboBoxStyle,
    Form,
    FormBorderStyle,
    FormStartPosition,
    Label,
    MessageBox,
    MessageBoxButtons,
    MessageBoxIcon,
    ProgressBar,
    ScrollBars,
    TextBox,
)
# endregion

# ----------------------------------------------------------------------------------------------------------------

VERIFY_MECHANICAL_AVERAGE_PARITY = False
MECHANICAL_AVERAGE_ABSOLUTE_TOLERANCE = 1.0e-12
MECHANICAL_AVERAGE_RELATIVE_TOLERANCE = 1.0e-10
DPF_SHELL_LAYER_TOP_BOTTOM = 2
DPF_ROTATE_TO_GLOBAL_FOR_SOLUTION_COORDINATE_SYSTEM = False
DPF_USE_STREAMS_CONTAINER = False
DPF_USE_CHANGE_SHELL_LAYERS = False
STRAIN_CSV_FILE_NAME = "SG_FEA_strain_data.csv"
MICROSTRAIN_CSV_FILE_NAME = "SG_FEA_microstrain_data.csv"

# region Define the required functions
class StopScriptError(Exception):
    pass


class ExtractionCancelledError(StopScriptError):
    pass


# Function to extract reference and channel numbers from a strain name
def extract_numbers(name):
    pattern = r"StrainX_SG(\d+)_(\d+)"
    match = re.search(pattern, str(name))
    if match:
        return tuple(map(int, match.groups()))
    else:
        return (0, 0)  # Default to (0, 0) if the pattern does not match


# Function to sort the strain names using the extract_numbers function
def sort_strain_names(names):
    sorted_names = sorted(names, key=extract_numbers)
    return sorted_names


def show_error(message):
    MessageBox.Show(message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)


def stop_with_error(message):
    show_error(message)
    raise StopScriptError(message)


def show_info(title, message):
    MessageBox.Show(message, title, MessageBoxButtons.OK, MessageBoxIcon.Information)


class DpfExtractionProgressDialog(object):
    def __init__(self, total_steps, setup_summary=None):
        self.total_steps = max(1, int(total_steps))
        self.completed_steps = 0
        self.cancel_requested = False
        self.closed_by_script = False
        self.allow_close = False
        self.finished = False
        self.current_object_text = "Preparing extraction..."
        self.last_pump_time = 0.0
        self.pump_interval_seconds = 0.10

        self.form = Form()
        self.form.Text = "Extracting SG Strains with Mechanical DPF"
        self.form.ClientSize = Size(760, 560)
        self.form.FormBorderStyle = FormBorderStyle.FixedDialog
        self.form.StartPosition = FormStartPosition.CenterScreen
        self.form.MaximizeBox = False
        self.form.MinimizeBox = False
        self.form.TopMost = True
        self.form.FormClosing += self._form_closing

        self.status_label = Label()
        self.status_label.AutoSize = False
        self.status_label.Location = Point(12, 12)
        self.status_label.Size = Size(736, 22)
        self.status_label.Text = self.current_object_text

        self.detail_label = Label()
        self.detail_label.AutoSize = False
        self.detail_label.Location = Point(12, 38)
        self.detail_label.Size = Size(736, 34)
        self.detail_label.Text = "Reading result data..."

        self.progress_bar = ProgressBar()
        self.progress_bar.Location = Point(12, 78)
        self.progress_bar.Size = Size(736, 20)
        self.progress_bar.Minimum = 0
        self.progress_bar.Maximum = self.total_steps
        self.progress_bar.Value = 0

        self.summary_label = Label()
        self.summary_label.AutoSize = False
        self.summary_label.Location = Point(12, 108)
        self.summary_label.Size = Size(736, 18)
        self.summary_label.Text = "Run setup"

        self.summary_text_box = TextBox()
        self.summary_text_box.Location = Point(12, 130)
        self.summary_text_box.Size = Size(736, 120)
        self.summary_text_box.Multiline = True
        self.summary_text_box.ReadOnly = True
        self.summary_text_box.WordWrap = False
        self.summary_text_box.ScrollBars = ScrollBars.Both
        self.summary_text_box.Text = str(setup_summary or "")

        self.log_label = Label()
        self.log_label.AutoSize = False
        self.log_label.Location = Point(12, 262)
        self.log_label.Size = Size(736, 18)
        self.log_label.Text = "Detailed progress log"

        self.log_text_box = TextBox()
        self.log_text_box.Location = Point(12, 284)
        self.log_text_box.Size = Size(736, 230)
        self.log_text_box.Multiline = True
        self.log_text_box.ReadOnly = True
        self.log_text_box.WordWrap = False
        self.log_text_box.ScrollBars = ScrollBars.Both

        self.cancel_button = Button()
        self.cancel_button.Location = Point(660, 524)
        self.cancel_button.Size = Size(88, 25)
        self.cancel_button.Text = "Cancel"
        self.cancel_button.Click += self._cancel_clicked

        self.form.Controls.Add(self.status_label)
        self.form.Controls.Add(self.detail_label)
        self.form.Controls.Add(self.progress_bar)
        self.form.Controls.Add(self.summary_label)
        self.form.Controls.Add(self.summary_text_box)
        self.form.Controls.Add(self.log_label)
        self.form.Controls.Add(self.log_text_box)
        self.form.Controls.Add(self.cancel_button)
        self.form.Show()
        self.log("Progress UI opened.")
        self._pump(True)

    def _pump(self, force=False):
        now = time.time()
        if not force and now - self.last_pump_time < self.pump_interval_seconds:
            return
        self.last_pump_time = now
        try:
            Application.DoEvents()
        except Exception:
            pass

    def _cancel_clicked(self, sender, args):
        if self.finished:
            self.close()
            return
        self.cancel_requested = True
        self.cancel_button.Enabled = False
        self.cancel_button.Text = "Cancelling..."
        self.detail_label.Text = "Cancelling after the current DPF operation returns..."
        self.log("Cancellation requested. Waiting for the current DPF step to return.")
        self._pump(True)

    def _form_closing(self, sender, args):
        if not self.closed_by_script and not self.allow_close:
            self.cancel_requested = True
            args.Cancel = True
            self._cancel_clicked(sender, args)

    def check_cancelled(self, force=False):
        self._pump(force)
        if self.cancel_requested:
            raise ExtractionCancelledError("DPF SG strain extraction cancelled by user.")

    def set_stage(self, detail_text):
        self.detail_label.Text = str(detail_text)
        self.log(detail_text)
        self.check_cancelled(True)

    def set_total_steps(self, total_steps):
        self.total_steps = max(1, int(total_steps))
        self.progress_bar.Maximum = self.total_steps
        self.progress_bar.Value = min(self.completed_steps, self.total_steps)
        self.log("Progress target set to {0} object/result-set reductions.".format(self.total_steps))

    def start_object(self, object_index, object_count, object_name):
        self.current_object_text = "SG object {0} of {1}: {2}".format(
            object_index, object_count, object_name
        )
        self.status_label.Text = self.current_object_text
        self.log(self.current_object_text)
        self.set_stage("Preparing DPF scoping...")

    def set_current_object(self, object_index, object_count, object_name):
        self.current_object_text = "SG object {0} of {1}: {2}".format(
            object_index, object_count, object_name
        )
        self.status_label.Text = self.current_object_text
        self.check_cancelled()

    def complete_time_set(self, set_id, set_index, set_count):
        self.completed_steps = min(self.total_steps, self.completed_steps + 1)
        self.progress_bar.Value = self.completed_steps
        detail_text = "Result set {0} of {1} (set id {2})".format(
            set_index, set_count, set_id
        )
        self.detail_label.Text = detail_text
        self.log(detail_text)
        self.check_cancelled()

    def complete_steps(self, step_count, detail_text):
        self.completed_steps = min(
            self.total_steps, self.completed_steps + int(step_count)
        )
        self.progress_bar.Value = self.completed_steps
        self.detail_label.Text = str(detail_text)
        self.log(detail_text)
        self.check_cancelled()

    def start_writing(self):
        self.cancel_button.Enabled = False
        self.cancel_button.Text = "Writing..."
        self.status_label.Text = "Writing SG strain CSV files..."
        self.detail_label.Text = "Writing both output files as one completed extraction."
        self.log("Writing SG strain CSV files. Cancellation is disabled during file writes.")
        self.check_cancelled(True)

    def finish(self, summary_text=None):
        self.completed_steps = self.total_steps
        self.progress_bar.Value = self.total_steps
        self.status_label.Text = "SG strain extraction complete."
        self.detail_label.Text = "CSV files were written successfully."
        if summary_text:
            self.summary_text_box.Text = str(summary_text)
            self.log(summary_text)
        self.cancel_button.Enabled = True
        self.cancel_button.Text = "Close"
        self.finished = True
        self.allow_close = True
        self._pump(True)

    def log(self, message):
        text = str(message)
        print(text)
        try:
            timestamped = "[{0}] {1}\r\n".format(time.strftime("%H:%M:%S"), text)
            self.log_text_box.AppendText(timestamped)
            self.log_text_box.SelectionStart = len(self.log_text_box.Text)
            self.log_text_box.ScrollToCaret()
        except Exception:
            pass
        self._pump()

    def wait_for_close(self):
        while self.form is not None:
            try:
                if not self.form.Visible:
                    break
                Application.DoEvents()
                time.sleep(0.05)
            except Exception:
                break

    def close(self):
        if self.form is None:
            return
        try:
            self.closed_by_script = True
            self.form.Close()
        except Exception:
            pass
        self.form = None


def make_progress_dialog(total_steps, setup_summary=None):
    try:
        return DpfExtractionProgressDialog(total_steps, setup_summary)
    except Exception as exc:
        stop_with_error(
            "Progress dialog could not be shown; extraction was not started. Details: {0}".format(
                exc
            )
        )


def log_message(progress, message):
    if progress is not None and hasattr(progress, "log"):
        progress.log(message)
    else:
        print(str(message))


def safe_get(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def to_list(value):
    if value is None:
        return []
    try:
        return list(value)
    except Exception:
        return [value]


def to_float(value):
    try:
        return float(value)
    except Exception:
        pass

    quantity_value = safe_get(value, "Value", None)
    if quantity_value is not None:
        try:
            return float(quantity_value)
        except Exception:
            pass

    return float(str(value))


def connect_pin(pin, value):
    if hasattr(pin, "Connect"):
        pin.Connect(value)
    else:
        pin.connect(value)


def connect_optional_pin(inputs, name, value):
    if value is None or not hasattr(inputs, name):
        return
    connect_pin(getattr(inputs, name), value)


def output_data(output):
    if hasattr(output, "GetData"):
        return output.GetData()
    if hasattr(output, "get_data"):
        return output.get_data()
    if callable(output):
        return output()
    return output


def create_streams_container(data_sources, progress=None):
    if not DPF_USE_STREAMS_CONTAINER:
        log_message(progress, "DPF streams container is disabled; using data sources directly.")
        return None
    try:
        provider = dpf.operators.metadata.streams_provider()
        connect_pin(provider.inputs.data_sources, data_sources)
        streams_container = output_data(provider.outputs.streams_container)
        log_message(progress, "DPF streams container created for cached result-file reads.")
        return streams_container
    except Exception as exc:
        log_message(
            progress,
            "DPF streams container could not be created; using data sources directly. Details: {0}".format(exc),
        )
        return None


def release_streams_container(streams_container, progress=None):
    if streams_container is None:
        log_message(progress, "No DPF stream handles to release.")
        return
    release_handles = safe_get(streams_container, "release_handles", None)
    if callable(release_handles):
        try:
            release_handles()
            log_message(progress, "DPF stream handles released.")
        except Exception as exc:
            log_message(progress, "DPF stream handles could not be released. Details: {0}".format(exc))


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


def scoping_ids(scoping):
    ids = safe_get(scoping, "Ids", None)
    if ids is None:
        ids = safe_get(scoping, "ids", None)
    return [int(item) for item in to_list(ids)]


def scoping_from_ids(ids, location=None):
    scoping = dpf.Scoping()
    scoping.Ids = [int(item) for item in sorted(set(ids))]
    if location is not None:
        try:
            scoping.Location = location
        except Exception:
            try:
                scoping.location = location
            except Exception:
                pass
    return scoping


def field_by_time_id(fields_container, time_id):
    if hasattr(fields_container, "GetFieldByTimeId"):
        return fields_container.GetFieldByTimeId(time_id)
    if hasattr(fields_container, "get_field_by_time_id"):
        return fields_container.get_field_by_time_id(time_id)
    try:
        return fields_container[time_id - 1]
    except Exception:
        raise Exception("Fields container does not expose field access by time id.")


def field_value_groups(field):
    data = safe_get(field, "Data", None)
    if data is None:
        data = safe_get(field, "data", None)
    if data is None:
        return []

    if hasattr(data, "tolist"):
        values = data.tolist()
    else:
        values = to_list(data)

    groups = []
    for value in values:
        if hasattr(value, "tolist"):
            value = value.tolist()
        if isinstance(value, (list, tuple)):
            groups.append([float(item) for item in value])
        else:
            groups.append([float(value)])

    return groups


def field_values(field):
    flattened_values = []
    for group in field_value_groups(field):
        flattened_values.extend(group)
    return flattened_values


def flattened_groups(groups):
    flattened_values = []
    for group in groups:
        flattened_values.extend(group)
    return flattened_values


def field_entity_group_layout(field):
    field_scoping = safe_get(field, "Scoping", None)
    if field_scoping is None:
        field_scoping = safe_get(field, "scoping", None)
    field_ids = scoping_ids(field_scoping)
    value_groups = field_value_groups(field)

    if len(field_ids) == 0 or len(value_groups) == 0:
        return None

    if len(value_groups) % len(field_ids) != 0:
        return None

    groups_per_entity = int(len(value_groups) / len(field_ids))
    return {
        "ids": field_ids,
        "groups": value_groups,
        "groups_per_entity": groups_per_entity,
        "index_by_id": dict(
            (int(entity_id), index) for index, entity_id in enumerate(field_ids)
        ),
    }


def group_slices_for_ids(layout, keep_ids):
    groups_per_entity = layout["groups_per_entity"]
    index_by_id = layout["index_by_id"]
    group_slices = []
    for entity_id in keep_ids:
        entity_id = int(entity_id)
        if entity_id not in index_by_id:
            return None
        start = index_by_id[entity_id] * groups_per_entity
        end = start + groups_per_entity
        group_slices.append((start, end))
    return group_slices


def value_groups_from_slices(value_groups, group_slices):
    selected_groups = []
    for start, end in group_slices:
        selected_groups.extend(value_groups[start:end])
    return selected_groups


def field_value_groups_for_ids(field, keep_ids):
    layout = field_entity_group_layout(field)
    if layout is None:
        return None

    group_slices = group_slices_for_ids(layout, keep_ids)
    if group_slices is None:
        return None

    return value_groups_from_slices(layout["groups"], group_slices)


def mean_field_value(field, object_name, set_id):
    values = field_values(field)
    if len(values) == 0:
        stop_with_error(
            "DPF returned no nodal strain values for {0} at result set {1}.".format(
                object_name, set_id
            )
        )
    return sum(values) / float(len(values))


def weighted_average_field(field, weights, object_name, set_id):
    value_groups = field_value_groups(field)
    values = []
    for group in value_groups:
        values.extend(group)
    weight_values = field_values(weights)

    if len(values) == 0:
        stop_with_error(
            "DPF returned no strain values for {0} at result set {1}.".format(
                object_name, set_id
            )
        )

    if len(weight_values) == 0:
        stop_with_error(
            "DPF returned no integration weights for {0} at result set {1}.".format(
                object_name, set_id
            )
        )

    if len(value_groups) == len(weight_values):
        weighted_sum = 0.0
        weight_sum = 0.0
        for group, weight in zip(value_groups, weight_values):
            for value in group:
                weighted_sum += value * weight
                weight_sum += weight
    elif len(values) == len(weight_values):
        weighted_sum = 0.0
        weight_sum = 0.0
        for value, weight in zip(values, weight_values):
            weighted_sum += value * weight
            weight_sum += weight
    else:
        stop_with_error(
            "DPF strain value count ({0}) does not match integration weight count ({1}) "
            "for {2} at result set {3}.".format(
                len(values), len(weight_values), object_name, set_id
            )
        )

    if abs(weight_sum) <= 1.0e-300:
        stop_with_error(
            "DPF returned zero integration weight for {0} at result set {1}.".format(
                object_name, set_id
            )
        )

    return weighted_sum / weight_sum


def weighted_average_group_values(value_groups, weight_values, object_name, set_id):
    values = flattened_groups(value_groups)
    if len(values) == 0:
        stop_with_error(
            "DPF returned no strain values for {0} at result set {1}.".format(
                object_name, set_id
            )
        )

    if len(weight_values) == 0:
        stop_with_error(
            "DPF returned no integration weights for {0} at result set {1}.".format(
                object_name, set_id
            )
        )

    if len(values) != len(weight_values):
        stop_with_error(
            "DPF strain value count ({0}) does not match integration weight count ({1}) "
            "for {2} at result set {3}.".format(
                len(values), len(weight_values), object_name, set_id
            )
        )

    weighted_sum = 0.0
    weight_sum = 0.0
    for value, weight in zip(values, weight_values):
        weighted_sum += value * weight
        weight_sum += weight

    if weight_sum == 0.0:
        stop_with_error(
            "DPF integration weights sum to zero for {0} at result set {1}.".format(
                object_name, set_id
            )
        )

    return weighted_sum / weight_sum


def enum_text(value):
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def detail_key(value):
    return (
        enum_text(value)
        .split(".")[-1]
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace("/", "")
        .replace(":", "")
        .lower()
    )


def detail_property_value(result_obj, labels):
    target_keys = [detail_key(label) for label in labels]
    for collection_name in ("VisibleProperties", "Properties"):
        properties = safe_get(result_obj, collection_name, None)
        for prop in to_list(properties):
            prop_keys = []
            for name_attr in (
                "APIName",
                "Name",
                "Caption",
                "DisplayName",
                "PropertyName",
                "InternalName",
            ):
                prop_name = safe_get(prop, name_attr, None)
                if prop_name is not None:
                    prop_keys.append(detail_key(prop_name))

            if not any(prop_key in target_keys for prop_key in prop_keys):
                continue

            for value_attr in ("DisplayValue", "StringValue", "Value", "InternalValue"):
                value = safe_get(prop, value_attr, None)
                if value is not None and not callable(value):
                    return value

    return None


def result_detail_value(result_obj, direct_attrs, labels):
    for attr in direct_attrs:
        value = safe_get(result_obj, attr, None)
        if value is not None:
            return value
    return detail_property_value(result_obj, list(direct_attrs) + list(labels))


def require_detail_key(result_obj, object_name, label, direct_attrs, labels, accepted_keys, expected_text):
    value = result_detail_value(result_obj, direct_attrs, labels)
    if value is None:
        stop_with_error(
            "Could not read {0} for {1}. This DPF extractor requires {0} = {2}.".format(
                label, object_name, expected_text
            )
        )

    value_key = detail_key(value)
    if value_key not in accepted_keys:
        stop_with_error(
            "Unsupported {0} for {1}: {2}. This DPF extractor requires {0} = {3}.".format(
                label, object_name, enum_text(value), expected_text
            )
        )

    return value


def optional_detail_key(result_obj, object_name, label, direct_attrs, labels, accepted_keys, expected_text):
    value = result_detail_value(result_obj, direct_attrs, labels)
    if value is None:
        return None

    value_key = detail_key(value)
    if value_key not in accepted_keys:
        stop_with_error(
            "Unsupported {0} for {1}: {2}. This DPF extractor requires {0} = {3}.".format(
                label, object_name, enum_text(value), expected_text
            )
        )

    return value


def bool_detail_matches(value, expected):
    if value is True or value is False:
        return value == expected

    value_key = detail_key(value)
    if expected:
        return value_key in ("true", "yes", "1")
    return value_key in ("false", "no", "0")


def require_bool_detail(result_obj, object_name, label, direct_attrs, labels, expected):
    value = result_detail_value(result_obj, direct_attrs, labels)
    expected_text = "Yes" if expected else "No"
    if value is None:
        stop_with_error(
            "Could not read {0} for {1}. This DPF extractor requires {0} = {2}.".format(
                label, object_name, expected_text
            )
        )

    if not bool_detail_matches(value, expected):
        stop_with_error(
            "Unsupported {0} for {1}: {2}. This DPF extractor requires {0} = {3}.".format(
                label, object_name, enum_text(value), expected_text
            )
        )

    return value


def ensure_supported_strain_object(result_obj):
    object_name = str(safe_get(result_obj, "Name", "<unnamed>"))

    require_detail_key(
        result_obj,
        object_name,
        "Scoping Method",
        ("ScopingMethod",),
        ("Scoping Method",),
        ("geometry", "geometryselection"),
        "Geometry Selection",
    )

    require_detail_key(
        result_obj,
        object_name,
        "Orientation",
        ("NormalOrientation",),
        ("Orientation", "Normal Orientation"),
        ("xaxis", "0"),
        "X Axis",
    )

    optional_detail_key(
        result_obj,
        object_name,
        "Type",
        (),
        ("Type",),
        ("normalelasticstrain",),
        "Normal Elastic Strain",
    )

    require_detail_key(
        result_obj,
        object_name,
        "Layer",
        (),
        ("Layer",),
        ("entiresection", "all"),
        "Entire Section",
    )

    require_detail_key(
        result_obj,
        object_name,
        "Position",
        ("Position",),
        ("Position",),
        ("topandbottom", "topbottom", "2"),
        "Top/Bottom",
    )

    require_detail_key(
        result_obj,
        object_name,
        "By",
        ("By",),
        ("By",),
        ("time", "1"),
        "Time",
    )

    require_bool_detail(
        result_obj,
        object_name,
        "Separate Data by Entity",
        ("SeparateDataByEntity", "SeparateDataByEntities"),
        ("Separate Data by Entity",),
        False,
    )

    require_bool_detail(
        result_obj,
        object_name,
        "Calculate Time History",
        ("CalculateTimeHistory",),
        ("Calculate Time History",),
        True,
    )

    require_detail_key(
        result_obj,
        object_name,
        "Display Option",
        ("DisplayOption",),
        ("Display Option",),
        ("averaged", "1"),
        "Averaged",
    )

    require_bool_detail(
        result_obj,
        object_name,
        "Average Across Bodies",
        ("AverageAcrossBodies",),
        ("Average Across Bodies",),
        False,
    )

    coordinate_system = result_detail_value(
        result_obj, ("CoordinateSystem",), ("Coordinate System",)
    )
    if coordinate_system is not None:
        cs_name = str(safe_get(coordinate_system, "Name", ""))
        if not cs_name:
            cs_name = enum_text(coordinate_system)
        cs_key = detail_key(cs_name)
        if cs_key not in ("", "solutioncoordinatesystem"):
            stop_with_error(
                "Unsupported coordinate system for {0}: {1}. "
                "This DPF extractor requires Coordinate System = Solution Coordinate System.".format(
                    object_name, cs_name
                )
            )


def selected_geometry_kind_counts(selection):
    counts = {}
    ids = safe_get(selection, "Ids", None)
    for geo_id in to_list(ids):
        try:
            entity = ExtAPI.DataModel.GeoData.GeoEntityById(int(geo_id))
            type_text = enum_text(safe_get(entity, "Type", None)).lower()
        except Exception:
            type_text = ""

        if "body" in type_text:
            kind = "body"
        elif "face" in type_text or "surface" in type_text:
            kind = "face"
        elif "edge" in type_text:
            kind = "edge"
        elif "vertex" in type_text:
            kind = "vertex"
        elif type_text:
            kind = type_text
        else:
            kind = "unknown"

        counts[kind] = counts.get(kind, 0) + 1

    return counts


def selected_geometry_kinds(selection):
    counts = selected_geometry_kind_counts(selection)
    return [kind for kind in counts.keys() if counts[kind] > 0 and kind != "unknown"]


def require_single_body_scope(selected_scope, object_name):
    if selected_scope["kind"] != "body":
        stop_with_error(
            "Unsupported SG result scope for {0}: {1}. "
            "This DPF extractor mirrors the tabular SG setup and requires Geometry = 1 Body.".format(
                object_name, selected_scope["kind"]
            )
        )

    geometry_counts = selected_scope.get("geometry_counts", {})
    body_count = int(geometry_counts.get("body", 0))
    selected_count = sum(int(count) for count in geometry_counts.values())
    if body_count != 1 or selected_count != 1:
        stop_with_error(
            "Unsupported Geometry scope for {0}: {1}. "
            "This DPF extractor requires exactly 1 selected body and Average Across Bodies = No.".format(
                object_name,
                ", ".join(
                    "{0} {1}".format(count, kind)
                    for kind, count in sorted(geometry_counts.items())
                )
                or "unreadable geometry selection",
            )
        )


def scoping_target_for_result(result_obj):
    location = safe_get(result_obj, "Location", None)
    if location is not None:
        return location

    named_selections = safe_get(result_obj, "NamedSelections", None)
    named_selection_list = to_list(named_selections)
    if len(named_selection_list) > 0:
        return named_selection_list[0]

    return None


def named_selection_for_result(result_obj):
    named_selections = safe_get(result_obj, "NamedSelections", None)
    named_selection_list = to_list(named_selections)
    for named_selection in named_selection_list:
        name = safe_get(named_selection, "Name", None)
        if name:
            return named_selection

    location = safe_get(result_obj, "Location", None)
    category_text = enum_text(safe_get(location, "DataModelObjectCategory", None))
    if safe_get(location, "Name", None) and "namedselection" in (
        category_text.replace("_", "").replace(" ", "").lower()
    ):
        return location

    return None


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
    except Exception as new_selection_error:
        try:
            selection_manager.ClearSelection()
            selection_manager.AddSelection(location)
            return
        except Exception as add_selection_error:
            raise Exception(
                "NewSelection failed: {0}; AddSelection failed: {1}".format(
                    new_selection_error, add_selection_error
                )
            )


def dominant_scope_kind(geometry_kinds, node_scoping, element_scoping):
    unsupported_geometry = []
    for geometry_kind in geometry_kinds:
        if geometry_kind not in ("face", "body"):
            unsupported_geometry.append(geometry_kind)
    if unsupported_geometry:
        stop_with_error(
            "Unsupported SG result geometry scope type: {0}. "
            "Use face, body, or direct nodal scoping for StrainX_SG results.".format(
                ", ".join(unsupported_geometry)
            )
        )

    if "face" in geometry_kinds and "body" in geometry_kinds:
        stop_with_error(
            "Mixed face and body scoping is not supported by the DPF SG strain extractor. "
            "Use one face-based or one body-based scope per StrainX_SG result."
        )

    if "face" in geometry_kinds:
        return "face"
    if "body" in geometry_kinds:
        return "body"

    if len(scoping_ids(element_scoping)) == 0 and len(scoping_ids(node_scoping)) > 0:
        return "node"

    stop_with_error(
        "Could not determine whether the SG result scope is a face or a body. "
        "The DPF extractor refuses to use an unweighted nodal average for geometry scopes."
    )


def selected_scope_for_result(result_obj, data_sources):
    target = scoping_target_for_result(result_obj)
    if target is None:
        stop_with_error(
            "No Location or Named Selection is defined for {0}; cannot build a DPF mesh scoping.".format(
                safe_get(result_obj, "Name", "<unnamed>")
            )
        )

    named_selection = named_selection_for_result(result_obj)
    if named_selection is not None:
        stop_with_error(
            "Unsupported scoping method for {0}: Named Selection. "
            "This DPF extractor mirrors the tabular SG setup and requires Scoping Method = Geometry Selection.".format(
                safe_get(result_obj, "Name", "<unnamed>")
            )
        )

    selection_manager = ExtAPI.SelectionManager
    previous_selection = safe_get(selection_manager, "CurrentSelection", None)

    try:
        select_mechanical_location(selection_manager, target)
        current_selection = safe_get(selection_manager, "CurrentSelection", None)
        geometry_counts = selected_geometry_kind_counts(current_selection)
        geometry_kinds = selected_geometry_kinds(current_selection)
        node_scoping = mech_dpf.GetNodesScoping()
        element_scoping = mech_dpf.GetElementScoping()
    finally:
        restore_selection(selection_manager, previous_selection)

    scoping_source = "mechanical_selection"
    scope_kind = dominant_scope_kind(geometry_kinds, node_scoping, element_scoping)
    return {
        "kind": scope_kind,
        "node_scoping": node_scoping,
        "element_scoping": element_scoping,
        "geometry_kinds": geometry_kinds,
        "geometry_counts": geometry_counts,
        "source": scoping_source,
    }


def selected_scope_or_error(result_obj, data_sources):
    object_name = str(safe_get(result_obj, "Name", "<unnamed>"))

    try:
        selected_scope = selected_scope_for_result(result_obj, data_sources)
    except StopScriptError:
        raise
    except Exception as exc:
        stop_with_error(
            "Could not build DPF scoping from the Mechanical tree scope for {0}. "
            "Details: {1}".format(object_name, exc)
        )

    if len(scoping_ids(selected_scope["node_scoping"])) == 0:
        stop_with_error(
            "DPF returned an empty nodal scoping for {0}.".format(object_name)
        )

    require_single_body_scope(selected_scope, object_name)

    if selected_scope["kind"] in ("face", "body") and len(scoping_ids(selected_scope["element_scoping"])) == 0:
        stop_with_error(
            "DPF returned an empty elemental scoping for geometry-scoped result {0}.".format(
                object_name
            )
        )

    return selected_scope


def evaluate_mechanical_result(result_obj, object_name, set_id):
    evaluate_methods = [
        safe_get(result_obj, "EvaluateAllResults", None),
        safe_get(safe_get(result_obj, "Parent", None), "EvaluateAllResults", None),
        safe_get(sol_selected_environment, "EvaluateAllResults", None),
    ]

    last_error = None
    for evaluate_method in evaluate_methods:
        if callable(evaluate_method):
            try:
                evaluate_method()
                return
            except Exception as exc:
                last_error = exc

    stop_with_error(
        "Could not evaluate Mechanical result {0} at result set {1}. Details: {2}".format(
            object_name, set_id, last_error
        )
    )


def mechanical_average_column(result_obj, set_ids, object_name):
    original_set_number = safe_get(result_obj, "SetNumber", None)
    column = []

    try:
        for set_id in set_ids:
            try:
                result_obj.SetNumber = int(set_id)
            except Exception as exc:
                stop_with_error(
                    "Could not set Mechanical result set {0} for {1}. Details: {2}".format(
                        set_id, object_name, exc
                    )
                )

            evaluate_mechanical_result(result_obj, object_name, set_id)
            average_value = safe_get(result_obj, "Average", None)
            if average_value is None:
                stop_with_error(
                    "Mechanical result {0} did not expose an Average value at result set {1}.".format(
                        object_name, set_id
                    )
                )

            try:
                column.append(to_float(average_value))
            except Exception as exc:
                stop_with_error(
                    "Could not convert Mechanical Average for {0} at result set {1} to a number. "
                    "Details: {2}".format(object_name, set_id, exc)
                )
    finally:
        if original_set_number is not None:
            try:
                result_obj.SetNumber = original_set_number
            except Exception as exc:
                print(
                    "Warning: could not restore SetNumber for {0} after parity check. "
                    "Details: {1}".format(object_name, exc)
                )

    return column


def values_close(left, right):
    tolerance = MECHANICAL_AVERAGE_ABSOLUTE_TOLERANCE + (
        MECHANICAL_AVERAGE_RELATIVE_TOLERANCE * max(abs(left), abs(right))
    )
    return abs(left - right) <= tolerance


def max_difference(column, reference_column, set_ids):
    worst = None
    for index, value in enumerate(column):
        reference_value = reference_column[index]
        difference = abs(value - reference_value)
        tolerance = MECHANICAL_AVERAGE_ABSOLUTE_TOLERANCE + (
            MECHANICAL_AVERAGE_RELATIVE_TOLERANCE * max(abs(value), abs(reference_value))
        )
        if worst is None or difference > worst["difference"]:
            worst = {
                "set_id": set_ids[index],
                "value": value,
                "reference_value": reference_value,
                "difference": difference,
                "tolerance": tolerance,
            }
    return worst


def choose_parity_checked_column(result_obj, object_name, candidates, set_ids):
    if not VERIFY_MECHANICAL_AVERAGE_PARITY:
        return candidates[0][1]

    reference_column = mechanical_average_column(result_obj, set_ids, object_name)
    if len(reference_column) != len(set_ids):
        stop_with_error(
            "Mechanical Average parity data count ({0}) does not match result set count ({1}) for {2}.".format(
                len(reference_column), len(set_ids), object_name
            )
        )

    mismatch_summaries = []
    for candidate_name, candidate_column in candidates:
        if len(candidate_column) != len(reference_column):
            mismatch_summaries.append(
                "{0}: value count {1}, expected {2}".format(
                    candidate_name, len(candidate_column), len(reference_column)
                )
            )
            continue

        if all(
            values_close(candidate_column[index], reference_column[index])
            for index in range(len(reference_column))
        ):
            if candidate_name != candidates[0][0]:
                print(
                    "Using {0} for {1}; it matches Mechanical Average better than the primary DPF candidate.".format(
                        candidate_name, object_name
                    )
                )
            return candidate_column

        worst = max_difference(candidate_column, reference_column, set_ids)
        mismatch_summaries.append(
            "{0}: set {1}, DPF={2:.17g}, Mechanical Average={3:.17g}, diff={4:.3e}, tol={5:.3e}".format(
                candidate_name,
                worst["set_id"],
                worst["value"],
                worst["reference_value"],
                worst["difference"],
                worst["tolerance"],
            )
        )

    stop_with_error(
        "No DPF reduction matched the Mechanical Average/old Tabular Data summary for {0}. "
        "CSV files were not written. Mismatches: {1}".format(
            object_name, "; ".join(mismatch_summaries)
        )
    )


def mesh_from_data_sources(data_sources, streams_container=None):
    if streams_container is not None:
        try:
            provider = dpf.operators.mesh.mesh_provider()
            connect_pin(provider.inputs.data_sources, data_sources)
            connect_optional_pin(provider.inputs, "streams_container", streams_container)
            return output_data(provider.outputs.mesh)
        except Exception:
            pass

    try:
        model = dpf.Model(data_sources)
        mesh = safe_get(model, "Mesh", None)
        if mesh is not None:
            return mesh

        metadata = safe_get(model, "metadata", None)
        if metadata is None:
            metadata = safe_get(model, "Metadata", None)
        mesh = safe_get(metadata, "meshed_region", None)
        if mesh is not None:
            return mesh
    except Exception:
        pass

    provider = dpf.operators.mesh.mesh_provider()
    connect_pin(provider.inputs.data_sources, data_sources)
    connect_optional_pin(provider.inputs, "streams_container", streams_container)
    return output_data(provider.outputs.mesh)


def skin_mesh_from_node_scoping(model_mesh, node_scoping):
    skin_op = dpf.operators.mesh.skin()
    connect_pin(skin_op.inputs.mesh, model_mesh)
    connect_pin(skin_op.inputs.mesh_scoping, node_scoping)
    return output_data(skin_op.outputs.mesh)


def element_nodal_weights(mesh, element_scoping=None):
    weights_op = dpf.operators.geo.element_nodal_contribution()
    connect_pin(weights_op.inputs.mesh, mesh)
    if element_scoping is not None:
        connect_pin(weights_op.inputs.scoping, element_scoping)
    connect_pin(weights_op.inputs.volume_fraction, True)
    return output_data(weights_op.outputs.field)


def elastic_strain_x_elemental_nodal(
    data_sources, time_scoping, element_scoping, streams_container=None
):
    strain_op = dpf.operators.result.elastic_strain_X()
    connect_pin(strain_op.inputs.data_sources, data_sources)
    connect_optional_pin(strain_op.inputs, "streams_container", streams_container)
    connect_pin(strain_op.inputs.time_scoping, time_scoping)
    connect_pin(strain_op.inputs.mesh_scoping, element_scoping)
    connect_pin(
        strain_op.inputs.bool_rotate_to_global,
        DPF_ROTATE_TO_GLOBAL_FOR_SOLUTION_COORDINATE_SYSTEM,
    )
    connect_pin(strain_op.inputs.requested_location, dpf_elemental_nodal_location())
    return output_data(strain_op.outputs.fields_container)


def top_bottom_shell_layer_field(field):
    if not DPF_USE_CHANGE_SHELL_LAYERS:
        return field

    shell_layer_op = dpf.operators.utility.change_shell_layers()
    connect_pin(shell_layer_op.inputs.fields_container, field)
    connect_pin(shell_layer_op.inputs.e_shell_layer, DPF_SHELL_LAYER_TOP_BOTTOM)

    for output_name in ("field", "fields_container"):
        output = safe_get(shell_layer_op.outputs, output_name, None)
        if output is None:
            continue
        try:
            candidate = output_data(output)
            if len(field_values(candidate)) > 0:
                return candidate
        except Exception:
            pass

    return field


def skin_strain_fields_container(strain_fields_container, skin_mesh, model_mesh):
    mapper = dpf.operators.mapping.solid_to_skin_fc()
    connect_pin(mapper.inputs.fields_container, strain_fields_container)
    connect_pin(mapper.inputs.mesh, skin_mesh)
    connect_pin(mapper.inputs.solid_mesh, model_mesh)
    return output_data(mapper.outputs.fields_container)


def time_freq_support_from_data_sources(data_sources):
    time_freq_support = None

    try:
        model = dpf.Model(data_sources)
        time_freq_support = safe_get(model, "TimeFreqSupport", None)
        if time_freq_support is None:
            metadata = safe_get(model, "metadata", None)
            if metadata is None:
                metadata = safe_get(model, "Metadata", None)
            time_freq_support = safe_get(metadata, "time_freq_support", None)
            if time_freq_support is None:
                time_freq_support = safe_get(metadata, "TimeFreqSupport", None)
    except Exception:
        time_freq_support = None

    if time_freq_support is None:
        provider = dpf.operators.metadata.time_freq_provider()
        connect_pin(provider.inputs.data_sources, data_sources)
        time_freq_support = output_data(provider.outputs.time_freq_support)

    return time_freq_support


def scalar_values_from_candidate(candidate):
    values = field_values(candidate)
    if len(values) > 0:
        return values

    data = safe_get(candidate, "Data", None)
    if data is None:
        data = safe_get(candidate, "data", None)
    if data is None:
        data = candidate

    values = []
    for value in to_list(data):
        if hasattr(value, "tolist"):
            value = value.tolist()
        if isinstance(value, (list, tuple)):
            values.extend([to_float(item) for item in value])
        else:
            values.append(to_float(value))
    return values


def time_values_from_time_freq_support(time_freq_support):
    candidate_names = (
        "TimeFreqs",
        "time_freqs",
        "TimeFrequencies",
        "time_frequencies",
    )

    for name in candidate_names:
        candidate = safe_get(time_freq_support, name, None)
        if candidate is not None:
            values = scalar_values_from_candidate(candidate)
            if len(values) > 0:
                return values

    method_names = (
        "GetTimeFreqs",
        "get_time_freqs",
        "GetTimeFrequencies",
        "get_time_frequencies",
    )
    for name in method_names:
        method = safe_get(time_freq_support, name, None)
        if callable(method):
            values = scalar_values_from_candidate(method())
            if len(values) > 0:
                return values

    return []


def get_time_data(solution, data_sources, expected_number_sets):
    time_values = []

    try:
        get_results_data = safe_get(solution, "GetResultsData", None)
        if callable(get_results_data):
            results_data = get_results_data()
            if results_data is not None:
                time_values = [
                    to_float(value) for value in to_list(results_data.ListTimeFreq)
                ]
    except Exception:
        time_values = []

    if len(time_values) == 0:
        try:
            time_freq_support = time_freq_support_from_data_sources(data_sources)
            time_values = time_values_from_time_freq_support(time_freq_support)
        except Exception as exc:
            stop_with_error(
                "Could not read DPF result time/frequency values from the selected analysis. "
                "Solve or relink the result file before running the DPF extractor. Details: {0}".format(
                    exc
                )
            )

    if len(time_values) == 0:
        stop_with_error(
            "Could not read result time/frequency values from the selected analysis result metadata."
        )

    if len(time_values) != expected_number_sets:
        stop_with_error(
            "Mismatch between Mechanical result time values ({0}) and DPF result sets ({1}).".format(
                len(time_values), expected_number_sets
            )
        )

    return time_values


def get_number_of_result_sets(data_sources):
    time_freq_support = time_freq_support_from_data_sources(data_sources)
    number_sets = safe_get(time_freq_support, "NumberSets", None)
    if number_sets is None:
        number_sets = safe_get(time_freq_support, "number_sets", None)
    if number_sets is None:
        stop_with_error("DPF could not read the number of result sets.")

    number_sets = int(number_sets)
    if number_sets <= 0:
        stop_with_error("DPF found no result sets in the selected analysis result file.")

    return number_sets


def make_time_scoping(set_ids):
    time_scoping = dpf.Scoping()
    time_scoping.Ids = set_ids
    return time_scoping


def extract_nodal_fallback_column(
    data_sources,
    time_scoping,
    node_scoping,
    set_ids,
    object_name,
    progress=None,
    streams_container=None,
):
    if progress is not None:
        progress.set_stage("Running DPF nodal strain operator...")
    operator_start = time.time()
    strain_op = dpf.operators.result.elastic_strain_X()
    connect_pin(strain_op.inputs.data_sources, data_sources)
    connect_optional_pin(strain_op.inputs, "streams_container", streams_container)
    connect_pin(strain_op.inputs.time_scoping, time_scoping)
    connect_pin(strain_op.inputs.mesh_scoping, node_scoping)
    connect_pin(
        strain_op.inputs.bool_rotate_to_global,
        DPF_ROTATE_TO_GLOBAL_FOR_SOLUTION_COORDINATE_SYSTEM,
    )
    connect_pin(strain_op.inputs.requested_location, dpf_nodal_location())

    fields_container = output_data(strain_op.outputs.fields_container)
    log_message(
        progress,
        "DPF nodal strain operator for {0} completed in {1:.2f} seconds.".format(
            object_name, time.time() - operator_start
        ),
    )

    column = []
    set_count = len(set_ids)
    for set_index, set_id in enumerate(set_ids, 1):
        if progress is not None:
            progress.check_cancelled()
        field = top_bottom_shell_layer_field(field_by_time_id(fields_container, set_id))
        column.append(mean_field_value(field, object_name, set_id))
        if progress is not None:
            progress.complete_time_set(set_id, set_index, set_count)
    return column


def extract_weighted_column(fields_container, weights, set_ids, object_name, progress=None):
    column = []
    set_count = len(set_ids)
    for set_index, set_id in enumerate(set_ids, 1):
        if progress is not None:
            progress.check_cancelled()
        field = top_bottom_shell_layer_field(field_by_time_id(fields_container, set_id))
        column.append(weighted_average_field(field, weights, object_name, set_id))
        if progress is not None:
            progress.complete_time_set(set_id, set_index, set_count)
    return column


def collect_body_strain_descriptors(
    result_objects, object_names, data_sources, progress=None
):
    descriptors = []
    object_count = len(object_names)
    for object_index, (result_obj, object_name) in enumerate(
        zip(result_objects, object_names), 1
    ):
        ensure_supported_strain_object(result_obj)
        if progress is not None:
            progress.start_object(object_index, object_count, object_name)

        selected_scope = selected_scope_or_error(result_obj, data_sources)
        scope_kind = selected_scope["kind"]
        log_message(
            progress,
            "Validated {0}: scope={1}, nodes={2}, elements={3}, geometry={4}.".format(
                object_name,
                scope_kind,
                len(scoping_ids(selected_scope["node_scoping"])),
                len(scoping_ids(selected_scope["element_scoping"])),
                selected_scope.get("geometry_counts", {}),
            ),
        )
        if scope_kind != "body":
            log_message(
                progress,
                "Body-batch DPF extraction skipped because {0} has scope kind {1}.".format(
                    object_name, scope_kind
                ),
            )
            return None

        element_ids = scoping_ids(selected_scope["element_scoping"])
        if len(element_ids) == 0:
            stop_with_error(
                "DPF returned an empty elemental scoping for body-scoped result {0}.".format(
                    object_name
                )
            )

        descriptors.append(
            {
                "index": object_index,
                "object": result_obj,
                "name": object_name,
                "sg_name": sg_header_from_name(object_name),
                "element_ids": element_ids,
                "node_ids": scoping_ids(selected_scope["node_scoping"]),
            }
        )

    return descriptors


def extract_body_batch_strain_columns(
    result_objects,
    object_names,
    data_sources,
    model_mesh,
    time_scoping,
    set_ids,
    progress=None,
    streams_container=None,
):
    descriptors = collect_body_strain_descriptors(
        result_objects, object_names, data_sources, progress
    )
    if descriptors is None:
        return None

    union_element_ids = []
    for descriptor in descriptors:
        union_element_ids.extend(descriptor["element_ids"])
    union_element_scoping = scoping_from_ids(
        union_element_ids, dpf_elemental_nodal_location()
    )

    if progress is not None:
        progress.set_stage(
            "Running one DPF strain operator for {0} SG body scopes...".format(
                len(descriptors)
            )
        )
    dpf_operator_start = time.time()
    union_fields_container = elastic_strain_x_elemental_nodal(
        data_sources, time_scoping, union_element_scoping, streams_container
    )
    log_message(
        progress,
        "Body-batch DPF strain operator completed in {0:.2f} seconds.".format(
            time.time() - dpf_operator_start
        ),
    )

    if progress is not None:
        progress.set_stage("Preparing union integration weights...")
    reduction_start = time.time()
    union_weights = element_nodal_weights(model_mesh, union_element_scoping)
    union_weight_layout = field_entity_group_layout(union_weights)
    if union_weight_layout is None:
        stop_with_error("Could not read DPF union integration weights.")

    columns_by_name = {}
    weight_values_by_name = {}
    for descriptor in descriptors:
        weight_slices = group_slices_for_ids(
            union_weight_layout, descriptor["element_ids"]
        )
        if weight_slices is None:
            stop_with_error(
                "Could not split DPF union integration weights for {0}.".format(
                    descriptor["name"]
                )
            )
        columns_by_name[descriptor["name"]] = []
        weight_values_by_name[descriptor["name"]] = flattened_groups(
            value_groups_from_slices(union_weight_layout["groups"], weight_slices)
        )

    set_count = len(set_ids)
    object_count = len(descriptors)
    first_set_id = set_ids[0] if set_count else None
    first_field = None
    first_field_layout = None
    if first_set_id is not None:
        first_field = top_bottom_shell_layer_field(
            field_by_time_id(union_fields_container, first_set_id)
        )
        first_field_layout = field_entity_group_layout(first_field)
        if first_field_layout is None:
            stop_with_error(
                "Could not read DPF union strain values at result set {0}.".format(
                    first_set_id
                )
            )
        for descriptor in descriptors:
            strain_slices = group_slices_for_ids(
                first_field_layout, descriptor["element_ids"]
            )
            if strain_slices is None:
                stop_with_error(
                    "Could not split DPF union strain values for {0} at result set {1}.".format(
                        descriptor["name"], first_set_id
                    )
                )
            descriptor["strain_slices"] = strain_slices

    for set_index, set_id in enumerate(set_ids, 1):
        if progress is not None:
            progress.check_cancelled()
        if set_id == first_set_id:
            field_layout = first_field_layout
        else:
            field = top_bottom_shell_layer_field(
                field_by_time_id(union_fields_container, set_id)
            )
            field_layout = field_entity_group_layout(field)
            if field_layout is None:
                stop_with_error(
                    "Could not read DPF union strain values at result set {0}.".format(
                        set_id
                    )
                )

        use_cached_slices = (
            field_layout["ids"] == first_field_layout["ids"]
            and field_layout["groups_per_entity"]
            == first_field_layout["groups_per_entity"]
        )
        for descriptor in descriptors:
            if use_cached_slices:
                value_groups = value_groups_from_slices(
                    field_layout["groups"], descriptor["strain_slices"]
                )
            else:
                strain_slices = group_slices_for_ids(
                    field_layout, descriptor["element_ids"]
                )
                if strain_slices is None:
                    stop_with_error(
                        "Could not split DPF union strain values for {0} at result set {1}.".format(
                            descriptor["name"], set_id
                        )
                    )
                value_groups = value_groups_from_slices(
                    field_layout["groups"], strain_slices
                )
            columns_by_name[descriptor["name"]].append(
                weighted_average_group_values(
                    value_groups,
                    weight_values_by_name[descriptor["name"]],
                    descriptor["name"],
                    set_id,
                )
            )
        if progress is not None:
            progress.complete_steps(
                object_count,
                "Result set {0} of {1} (set id {2}); reduced {3} SG bodies.".format(
                    set_index, set_count, set_id, object_count
                ),
            )

    log_message(
        progress,
        "Body-batch DPF split/reduce completed in {0:.2f} seconds.".format(
            time.time() - reduction_start
        ),
    )

    headers = [descriptor["sg_name"] for descriptor in descriptors]
    columns = [columns_by_name[descriptor["name"]] for descriptor in descriptors]
    return headers, columns


def extract_strain_column(
    result_obj,
    object_name,
    data_sources,
    model_mesh,
    time_scoping,
    set_ids,
    progress=None,
    streams_container=None,
):
    ensure_supported_strain_object(result_obj)
    if progress is not None:
        progress.set_stage("Preparing Mechanical geometry scoping...")
    selected_scope = selected_scope_or_error(result_obj, data_sources)
    scope_kind = selected_scope["kind"]
    node_scoping = selected_scope["node_scoping"]
    element_scoping = selected_scope["element_scoping"]
    log_message(
        progress,
        "Validated {0}: scope={1}, nodes={2}, elements={3}, geometry={4}.".format(
            object_name,
            scope_kind,
            len(scoping_ids(node_scoping)),
            len(scoping_ids(element_scoping)),
            selected_scope.get("geometry_counts", {}),
        ),
    )

    try:
        if scope_kind == "face":
            if progress is not None:
                progress.set_stage("Running DPF elemental-nodal strain operator...")
            operator_start = time.time()
            strain_fields_container = elastic_strain_x_elemental_nodal(
                data_sources, time_scoping, element_scoping, streams_container
            )
            log_message(
                progress,
                "DPF elemental-nodal strain operator for {0} completed in {1:.2f} seconds.".format(
                    object_name, time.time() - operator_start
                ),
            )
            if progress is not None:
                progress.set_stage("Mapping face strain data to the scoped skin mesh...")
            skin_mesh = skin_mesh_from_node_scoping(model_mesh, node_scoping)
            skin_fields_container = skin_strain_fields_container(
                strain_fields_container, skin_mesh, model_mesh
            )
            if progress is not None:
                progress.set_stage("Preparing integration weights...")
            weights = element_nodal_weights(skin_mesh)
            candidates = [
                (
                    "DPF face integration-weighted mean",
                    extract_weighted_column(
                        skin_fields_container, weights, set_ids, object_name, progress
                    ),
                ),
            ]
        elif scope_kind == "body":
            if progress is not None:
                progress.set_stage("Running DPF elemental-nodal strain operator...")
            operator_start = time.time()
            strain_fields_container = elastic_strain_x_elemental_nodal(
                data_sources, time_scoping, element_scoping, streams_container
            )
            log_message(
                progress,
                "DPF elemental-nodal strain operator for {0} completed in {1:.2f} seconds.".format(
                    object_name, time.time() - operator_start
                ),
            )
            if progress is not None:
                progress.set_stage("Preparing integration weights...")
            weights = element_nodal_weights(model_mesh, element_scoping)
            candidates = [
                (
                    "DPF body integration-weighted mean",
                    extract_weighted_column(
                        strain_fields_container, weights, set_ids, object_name, progress
                    ),
                ),
            ]
        elif scope_kind == "node":
            candidates = [
                (
                    "DPF nodal arithmetic mean",
                    extract_nodal_fallback_column(
                        data_sources,
                        time_scoping,
                        node_scoping,
                        set_ids,
                        object_name,
                        progress,
                        streams_container,
                    ),
                )
            ]
            log_message(
                progress,
                "Using DPF nodal arithmetic mean for node-scoped result {0}.".format(
                    object_name
                ),
            )
        else:
            stop_with_error(
                "Unsupported SG result scope type for {0}: {1}.".format(
                    object_name, scope_kind
                )
            )

        if VERIFY_MECHANICAL_AVERAGE_PARITY and scope_kind in ("face", "body"):
            candidates.append(
                (
                    "DPF nodal arithmetic mean",
                    extract_nodal_fallback_column(
                        data_sources,
                        time_scoping,
                        node_scoping,
                        set_ids,
                        object_name,
                        progress,
                        streams_container,
                    ),
                )
            )

        column = choose_parity_checked_column(result_obj, object_name, candidates, set_ids)
    except StopScriptError:
        raise
    except Exception as exc:
        stop_with_error(
            "DPF {0} strain extraction failed for {1}. Details: {2}".format(
                scope_kind, object_name, exc
            )
        )

    if len(column) != len(set_ids):
        stop_with_error(
            "Mismatch between extracted strain values ({0}) and result sets ({1}) for {2}.".format(
                len(column), len(set_ids), object_name
            )
        )

    return column


def open_csv_for_write(file_path):
    if sys.version_info[0] >= 3:
        return open(file_path, "w", newline="")
    return open(file_path, "wb")


def mechanical_tabular_number_text(value):
    text = "%.8g" % float(value)
    if "e" not in text and "E" not in text and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def write_csv(file_path, headers, time_data, column_data):
    transposed_data = list(map(list, zip(*column_data)))
    if len(transposed_data) != len(time_data):
        stop_with_error(
            "Mismatch between CSV time rows ({0}) and strain rows ({1}).".format(
                len(time_data), len(transposed_data)
            )
        )

    with open_csv_for_write(file_path) as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        for index, row in enumerate(transposed_data):
            writer.writerow(
                [time_data[index]]
                + [mechanical_tabular_number_text(value) for value in row]
            )


def sg_header_from_name(name):
    match = re.search(r"(SG\d+_\d+)", str(name))
    if match:
        return match.group(1)
    return "Unknown"


def solution_working_directory(solution):
    return str(safe_get(solution, "WorkingDir", ""))


def csv_output_paths_for_directory(solution_directory_path):
    return {
        "strain": os.path.join(solution_directory_path, STRAIN_CSV_FILE_NAME),
        "microstrain": os.path.join(solution_directory_path, MICROSTRAIN_CSV_FILE_NAME),
    }


def active_sg_strain_objects(solution):
    all_elastic_strains = solution.GetChildren(
        DataModelObjectCategory.NormalElasticStrain, True
    )
    sg_objects = []
    for obj in all_elastic_strains:
        obj_name = str(safe_get(obj, "Name", ""))
        if "StrainX_SG" in obj_name and safe_get(obj, "ObjectState", None) != ObjectState.Suppressed:
            sg_objects.append(obj)
    return sg_objects


def sorted_sg_strain_objects(sg_objects):
    paired_list = [
        (
            safe_get(obj, "ObjectId", None),
            str(safe_get(obj, "Name", "")),
            obj,
        )
        for obj in sg_objects
    ]
    sorted_pairs = sorted(paired_list, key=lambda x: extract_numbers(x[1]))
    if len(sorted_pairs) == 0:
        return [], [], []
    sorted_IDs, sorted_names, sorted_objects = zip(*sorted_pairs)
    return list(sorted_IDs), list(sorted_names), list(sorted_objects)


def solution_choice_key(solution):
    object_id = safe_get(solution, "ObjectId", None)
    if object_id is not None:
        return "object_id:{0}".format(object_id)
    return "solution:{0}|{1}".format(
        safe_get(solution, "Name", ""),
        solution_working_directory(solution),
    )


def choice_matches_solution(choice, solution):
    if solution is None:
        return False
    return choice.get("key") == solution_choice_key(solution)


def make_solution_choice(analysis, solution, source, preselected):
    analysis_name = str(safe_get(analysis, "Name", "")) or "<unnamed analysis>"
    solution_name = str(safe_get(solution, "Name", "")) or "Solution"
    working_dir = solution_working_directory(solution)
    sg_objects = []
    sg_error = None
    try:
        sg_objects = active_sg_strain_objects(solution)
    except Exception as exc:
        sg_error = str(exc)

    return {
        "analysis": analysis,
        "analysis_name": analysis_name,
        "solution": solution,
        "solution_name": solution_name,
        "working_dir": working_dir,
        "output_paths": csv_output_paths_for_directory(working_dir),
        "sg_objects": sg_objects,
        "sg_error": sg_error,
        "source": source,
        "preselected": preselected,
        "key": solution_choice_key(solution),
    }


def available_solution_choices():
    choices = []
    seen = set()
    existing_solution = globals().get("sol_selected_environment", None)

    model_candidates = (
        safe_get(safe_get(DataModel, "Project", None), "Model", None),
        safe_get(safe_get(safe_get(ExtAPI, "DataModel", None), "Project", None), "Model", None),
        globals().get("Model", None),
    )
    for model in model_candidates:
        analyses = to_list(safe_get(model, "Analyses", None))
        for analysis in analyses:
            solution = safe_get(analysis, "Solution", None)
            if solution is None:
                continue
            key = solution_choice_key(solution)
            if key in seen:
                continue
            seen.add(key)
            preselected = existing_solution is not None and solution_choice_key(existing_solution) == key
            choices.append(
                make_solution_choice(
                    analysis,
                    solution,
                    "Project analysis",
                    preselected,
                )
            )

    if existing_solution is not None and not any(
        choice_matches_solution(choice, existing_solution) for choice in choices
    ):
        choices.insert(
            0,
            make_solution_choice(
                safe_get(existing_solution, "Parent", None),
                existing_solution,
                "Existing sol_selected_environment",
                True,
            ),
        )

    if len(choices) == 0:
        stop_with_error("No analysis environment was found for SG strain extraction.")

    if not any(choice.get("preselected", False) for choice in choices):
        choices[0]["preselected"] = True
        choices[0]["source"] = "Default first analysis"

    return choices


def dpf_options_summary_lines():
    return [
        "VERIFY_MECHANICAL_AVERAGE_PARITY = {0}".format(VERIFY_MECHANICAL_AVERAGE_PARITY),
        "DPF_ROTATE_TO_GLOBAL_FOR_SOLUTION_COORDINATE_SYSTEM = {0}".format(
            DPF_ROTATE_TO_GLOBAL_FOR_SOLUTION_COORDINATE_SYSTEM
        ),
        "DPF_USE_STREAMS_CONTAINER = {0}".format(DPF_USE_STREAMS_CONTAINER),
        "DPF_USE_CHANGE_SHELL_LAYERS = {0}".format(DPF_USE_CHANGE_SHELL_LAYERS),
        "DPF_SHELL_LAYER_TOP_BOTTOM = {0}".format(DPF_SHELL_LAYER_TOP_BOTTOM),
    ]


def preflight_summary_text(choice):
    sg_names = [str(safe_get(obj, "Name", "")) for obj in choice.get("sg_objects", [])]
    shown_names = sg_names[:20]
    if len(sg_names) > len(shown_names):
        shown_names.append("... {0} more".format(len(sg_names) - len(shown_names)))

    lines = [
        "Selected Mechanical environment",
        "Analysis: {0}".format(choice.get("analysis_name", "<unknown>")),
        "Solution: {0}".format(choice.get("solution_name", "Solution")),
        "Selection source: {0}".format(choice.get("source", "")),
        "Working directory: {0}".format(choice.get("working_dir", "")),
        "",
        "Detected active StrainX_SG objects: {0}".format(len(sg_names)),
    ]
    if choice.get("sg_error"):
        lines.append("Could not inspect SG objects: {0}".format(choice.get("sg_error")))
    elif len(shown_names) > 0:
        lines.extend(["  {0}".format(name) for name in shown_names])
    else:
        lines.append("  None found in this environment.")

    output_paths = choice.get("output_paths", {})
    lines.extend(
        [
            "",
            "Output files",
            "Strain CSV: {0}".format(output_paths.get("strain", "")),
            "Microstrain CSV: {0}".format(output_paths.get("microstrain", "")),
            "",
            "DPF options",
        ]
    )
    lines.extend(dpf_options_summary_lines())
    return "\r\n".join(lines)


def solution_choice_display(choice):
    prefix = "* " if choice.get("preselected", False) else ""
    return "{0}{1} - {2} [{3}; {4} active SG]".format(
        prefix,
        choice.get("analysis_name", "<unknown>"),
        choice.get("solution_name", "Solution"),
        choice.get("source", ""),
        len(choice.get("sg_objects", [])),
    )


class DpfExtractionPreflightDialog(object):
    def __init__(self, choices):
        self.choices = choices
        self.selected_choice = None

        self.form = Form()
        self.form.Text = "Start SG DPF Strain Extraction"
        self.form.ClientSize = Size(760, 520)
        self.form.FormBorderStyle = FormBorderStyle.FixedDialog
        self.form.StartPosition = FormStartPosition.CenterScreen
        self.form.MaximizeBox = False
        self.form.MinimizeBox = False
        self.form.TopMost = True

        title_label = Label()
        title_label.AutoSize = False
        title_label.Location = Point(12, 12)
        title_label.Size = Size(736, 18)
        title_label.Text = "Choose the Mechanical analysis/environment to extract from."

        self.choice_combo = ComboBox()
        self.choice_combo.Location = Point(12, 36)
        self.choice_combo.Size = Size(736, 24)
        self.choice_combo.DropDownStyle = ComboBoxStyle.DropDownList
        self.choice_combo.SelectedIndexChanged += self._selection_changed
        for choice in choices:
            self.choice_combo.Items.Add(solution_choice_display(choice))

        summary_label = Label()
        summary_label.AutoSize = False
        summary_label.Location = Point(12, 74)
        summary_label.Size = Size(736, 18)
        summary_label.Text = "Run details"

        self.summary_text_box = TextBox()
        self.summary_text_box.Location = Point(12, 96)
        self.summary_text_box.Size = Size(736, 360)
        self.summary_text_box.Multiline = True
        self.summary_text_box.ReadOnly = True
        self.summary_text_box.WordWrap = False
        self.summary_text_box.ScrollBars = ScrollBars.Both

        self.start_button = Button()
        self.start_button.Location = Point(568, 480)
        self.start_button.Size = Size(88, 25)
        self.start_button.Text = "Start"
        self.start_button.Click += self._start_clicked

        self.cancel_button = Button()
        self.cancel_button.Location = Point(660, 480)
        self.cancel_button.Size = Size(88, 25)
        self.cancel_button.Text = "Cancel"
        self.cancel_button.Click += self._cancel_clicked

        self.form.Controls.Add(title_label)
        self.form.Controls.Add(self.choice_combo)
        self.form.Controls.Add(summary_label)
        self.form.Controls.Add(self.summary_text_box)
        self.form.Controls.Add(self.start_button)
        self.form.Controls.Add(self.cancel_button)

        selected_index = 0
        for index, choice in enumerate(choices):
            if choice.get("preselected", False):
                selected_index = index
                break
        self.choice_combo.SelectedIndex = selected_index
        self._update_summary()

    def _selected_choice(self):
        index = int(self.choice_combo.SelectedIndex)
        if index < 0 or index >= len(self.choices):
            return None
        return self.choices[index]

    def _update_summary(self):
        choice = self._selected_choice()
        if choice is not None:
            self.summary_text_box.Text = preflight_summary_text(choice)

    def _selection_changed(self, sender, args):
        self._update_summary()

    def _start_clicked(self, sender, args):
        choice = self._selected_choice()
        if choice is None:
            show_error("Choose a Mechanical analysis/environment before starting.")
            return
        if choice.get("sg_error"):
            show_error(
                "Could not inspect active StrainX_SG objects for this environment.\n\n{0}".format(
                    choice.get("sg_error")
                )
            )
            return
        if len(choice.get("sg_objects", [])) == 0:
            show_error(
                "The selected environment has no active StrainX_SG result objects.\n\n"
                "Choose another analysis or unsuppress/add the SG strain result objects before starting."
            )
            return
        self.selected_choice = choice
        self.form.Close()

    def _cancel_clicked(self, sender, args):
        self.selected_choice = None
        self.form.Close()

    def show(self):
        self.form.ShowDialog()
        return self.selected_choice


def show_preflight_dialog(choices):
    try:
        return DpfExtractionPreflightDialog(choices).show()
    except Exception as exc:
        stop_with_error(
            "Preflight dialog could not be shown; extraction was not started. Details: {0}".format(
                exc
            )
        )
# endregion

# ----------------------------------------------------------------------------------------------------------------

# region Choose the analysis solution environment and extract with Mechanical-hosted DPF
selected_solution_choice = show_preflight_dialog(available_solution_choices())
if selected_solution_choice is None:
    print("DPF SG strain extraction cancelled before start.")
else:
    sol_selected_environment = selected_solution_choice["solution"]
    solution_directory_path = selected_solution_choice["working_dir"]
    output_paths = selected_solution_choice["output_paths"]
    list_of_SG_grid_strain_objects = selected_solution_choice["sg_objects"]

    if len(list_of_SG_grid_strain_objects) == 0:
        stop_with_error(
            "There are no active SG strain contours to be extracted within the selected analysis environment."
        )

    (
        list_of_IDs_of_SG_grid_strains,
        list_of_names_of_SG_grid_strains,
        list_of_SG_grid_strain_objects,
    ) = sorted_sg_strain_objects(list_of_SG_grid_strain_objects)

    setup_summary = preflight_summary_text(selected_solution_choice)
    progress_dialog = make_progress_dialog(1, setup_summary)
    streams_container = None
    success = False
    start_time = time.time()

    try:
        log_message(
            progress_dialog,
            "Selected environment: {0} - {1}".format(
                selected_solution_choice.get("analysis_name", "<unknown>"),
                selected_solution_choice.get("solution_name", "Solution"),
            ),
        )
        log_message(progress_dialog, "Solution working directory: {0}".format(solution_directory_path))
        log_message(progress_dialog, "Active SG objects: {0}".format(len(list_of_names_of_SG_grid_strains)))
        log_message(progress_dialog, "Output strain CSV: {0}".format(output_paths["strain"]))
        log_message(progress_dialog, "Output microstrain CSV: {0}".format(output_paths["microstrain"]))

        progress_dialog.set_stage("Binding Mechanical ExtAPI to mech_dpf...")
        mech_dpf.setExtAPI(ExtAPI)

        progress_dialog.set_stage("Activating selected Mechanical solution environment...")
        try:
            sol_selected_environment.Activate()
            log_message(progress_dialog, "Selected solution environment activated.")
        except Exception as exc:
            log_message(progress_dialog, "Selected solution environment could not be activated; continuing. Details: {0}".format(exc))

        progress_dialog.set_stage("Reading DPF data sources from the selected Mechanical environment...")
        data_sources = mech_dpf.GetDataSources()
        log_message(progress_dialog, "DPF data sources resolved.")

        progress_dialog.set_stage("Reading DPF result-set metadata...")
        number_of_result_sets = get_number_of_result_sets(data_sources)
        set_ids = list(range(1, number_of_result_sets + 1))
        progress_dialog.set_total_steps(
            len(list_of_names_of_SG_grid_strains) * len(set_ids)
        )
        log_message(progress_dialog, "DPF result sets detected: {0}".format(number_of_result_sets))

        progress_dialog.set_stage("Preparing DPF streams container...")
        streams_container = create_streams_container(data_sources, progress_dialog)

        progress_dialog.set_stage("Loading DPF model mesh...")
        mesh_start = time.time()
        model_mesh = mesh_from_data_sources(data_sources, streams_container)
        log_message(
            progress_dialog,
            "DPF model mesh loaded in {0:.2f} seconds.".format(time.time() - mesh_start),
        )

        progress_dialog.set_stage("Preparing result-set time scoping...")
        time_scoping = make_time_scoping(set_ids)

        progress_dialog.set_stage("Reading result time/frequency values...")
        time_data = get_time_data(sol_selected_environment, data_sources, number_of_result_sets)
        log_message(
            progress_dialog,
            "Time/frequency values read: {0} rows; first={1}; last={2}.".format(
                len(time_data),
                time_data[0] if len(time_data) > 0 else "<none>",
                time_data[-1] if len(time_data) > 0 else "<none>",
            ),
        )

        list_of_strain_data = []
        headers_strain = []
        headers_microstrain = []

        body_batch_result = extract_body_batch_strain_columns(
            list_of_SG_grid_strain_objects,
            list_of_names_of_SG_grid_strains,
            data_sources,
            model_mesh,
            time_scoping,
            set_ids,
            progress_dialog,
            streams_container,
        )

        if body_batch_result is not None:
            headers_strain, list_of_strain_data = body_batch_result
            headers_microstrain = list(headers_strain)
        else:
            object_count = len(list_of_names_of_SG_grid_strains)
            for m in range(object_count):
                result_obj = list_of_SG_grid_strain_objects[m]
                object_name = list_of_names_of_SG_grid_strains[m]
                sg_name = sg_header_from_name(object_name)
                object_start_time = time.time()

                progress_dialog.start_object(m + 1, object_count, object_name)

                headers_strain.append(sg_name)
                headers_microstrain.append(sg_name)

                list_of_strain_data.append(
                    extract_strain_column(
                        result_obj,
                        object_name,
                        data_sources,
                        model_mesh,
                        time_scoping,
                        set_ids,
                        progress_dialog,
                        streams_container,
                    )
                )

                log_message(
                    progress_dialog,
                    "Extracted {0} in {1:.2f} seconds.".format(
                        object_name, time.time() - object_start_time
                    ),
                )

        if len(list_of_strain_data) != len(list_of_names_of_SG_grid_strains):
            stop_with_error(
                "Mismatch between SG result objects ({0}) and extracted strain columns ({1}).".format(
                    len(list_of_names_of_SG_grid_strains), len(list_of_strain_data)
                )
            )

        progress_dialog.check_cancelled(True)

        headers_strain.insert(0, "Time")
        headers_microstrain.insert(0, "Time")

        file_path = output_paths["strain"]
        SG_FEA_microstrain_file_path = output_paths["microstrain"]

        progress_dialog.start_writing()

        log_message(progress_dialog, "Writing strain CSV with {0} data columns and {1} rows.".format(len(list_of_strain_data), len(time_data)))
        write_csv(file_path, headers_strain, time_data, list_of_strain_data)
        log_message(progress_dialog, "CSV file for each SG channel (strain in mm/mm) created at: " + file_path)

        SG_FEA_microstrain_data = [
            [value * 1e6 for value in column] for column in list_of_strain_data
        ]

        log_message(progress_dialog, "Writing microstrain CSV with {0} data columns and {1} rows.".format(len(SG_FEA_microstrain_data), len(time_data)))
        write_csv(
            SG_FEA_microstrain_file_path,
            headers_microstrain,
            time_data,
            SG_FEA_microstrain_data,
        )
        log_message(progress_dialog, "CSV file for each SG channel (microstrain) created at: " + SG_FEA_microstrain_file_path)

        elapsed_seconds = time.time() - start_time
        final_summary = "\r\n".join(
            [
                setup_summary,
                "",
                "Completed extraction",
                "Result sets / rows: {0}".format(number_of_result_sets),
                "SG strain columns: {0}".format(len(list_of_strain_data)),
                "Elapsed time: {0:.2f} seconds".format(elapsed_seconds),
                "Strain CSV: {0}".format(file_path),
                "Microstrain CSV: {0}".format(SG_FEA_microstrain_file_path),
            ]
        )
        progress_dialog.finish(final_summary)
        log_message(progress_dialog, "Mechanical DPF SG strain extraction completed in {0:.2f} seconds.".format(elapsed_seconds))
        success = True
    except ExtractionCancelledError as exc:
        print(str(exc) + " No CSV files were written.")
        show_info("Extraction Cancelled", str(exc) + "\n\nNo CSV files were written.")
    finally:
        release_streams_container(streams_container, progress_dialog)
        if success:
            progress_dialog.wait_for_close()
        else:
            progress_dialog.close()
# endregion
