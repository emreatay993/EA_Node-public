# Load Reconstruction

"""
Estimates the loads applied on a system based on the measured strains from each SG channel.
The load estimation is based on two inputs, "SG_FEA_strain_data.csv" and "strain_sensitivity_matrix.csv". 
This button searches the measured SG results file from FEA ("SG_FEA_strain_data.csv") for measured strains created by the "SG Strain" command, 
inside the solution folder of the selected analysis environment. 
However, the "strain_sensitivity_matrix.csv" file is searched inside 
the project folder specified by the "Project Folder" button.

"""

# region Import necessary libraries
import os
import sys
from System.Drawing import Color, Font, FontStyle, Size, Point, SolidBrush, Pen
from System.Windows.Forms import *
from System.Diagnostics import Process, ProcessWindowStyle
from System.IO import StreamWriter, FileStream, FileMode, FileAccess, StreamReader
from System.Text import UTF8Encoding
from System import Environment
# endregion

# ----------------------------------------------------------------------------------------------------------------

# region Import the necessary classes and functions for the GUI
class FlatTextBox(TextBox):
    # Custom Textbox with no border for a flat design
    def __init__(self):
        super().__init__()
        self.BackColor = Color.White
        self.Font = Font("Segoe UI", 9)
        self.SetStyle(ControlStyles.UserPaint, True)

    def OnPaint(self, e):
        super().OnPaint(e)
        # Paint background color
        e.Graphics.FillRectangle(SolidBrush(self.BackColor), 0, 0, self.Width, self.Height)
        # Paint text
        e.Graphics.DrawString(self.Text, self.Font, SolidBrush(self.ForeColor), 2, 2)
        # Draw border if focused
        if self.Focused:
            e.Graphics.DrawRectangle(Pen(Color.FromArgb(204, 228, 247)), 0, 0, self.Width - 1, self.Height - 1)

class InputForm(Form):
    def __init__(self):
        self.InitializeComponent()
    
    def InitializeComponent(self):
        self.Text = 'Parameter Input'
        self.Size = Size(365, 290)
        self.FormBorderStyle = FormBorderStyle.FixedDialog
        self.BackColor = Color.White
        self.MaximizeBox = False
        self.MinimizeBox = False
        self.StartPosition = FormStartPosition.CenterScreen
    
        label_font = Font("Segoe UI", 9, FontStyle.Regular)
        self.flowPanel = FlowLayoutPanel()
        self.flowPanel.FlowDirection = FlowDirection.TopDown
        self.flowPanel.Location = Point(20, 20)
        self.flowPanel.Size = Size(350, 240)
        self.flowPanel.AutoScroll = True
    
        # Labels and TextFields for each parameter
        self.labels_text = ['Overall Signal Noise (microstrains):', 'Gage Factor Error (%):', 'Positioning Std. Uncertainty [mm]:']
        self.textFields = []
        default_values = ['20', '1', '0.5']  # Default values for the text fields
    
        for i, text in enumerate(self.labels_text):
            label = Label()
            label.Text = text
            label.Size = Size(300, 20)
            label.Font = label_font
            label.Margin = Padding(5, 5, 5, 0)
            self.flowPanel.Controls.Add(label)
    
            textField = TextBox()
            textField.Size = Size(300, 20)
            textField.Font = label_font
            textField.Margin = Padding(5, 0, 5, 5)
            textField.Text = default_values[i]  # Set the default value here
            self.flowPanel.Controls.Add(textField)
            self.textFields.append(textField)
    
        # OK Button
        self.okButton = Button()
        self.okButton.Text = 'OK'
        self.okButton.Size = Size(300, 40)
        self.okButton.Font = Font("Segoe UI", 10, FontStyle.Bold)
        self.okButton.FlatStyle = FlatStyle.Flat
        self.okButton.FlatAppearance.BorderSize = 0
        self.okButton.BackColor = Color.FromArgb(204, 228, 247)
        self.okButton.ForeColor = Color.White
        self.okButton.Click += self.OkButtonClick
        self.okButton.Margin = Padding(5, 10, 5, 5)
        self.flowPanel.Controls.Add(self.okButton)
    
        self.Controls.Add(self.flowPanel)

    def OkButtonClick(self, sender, args):
        try:
            # Parse the input values
            self.signal_noise_microstrains = float(self.textFields[0].Text)
            self.gage_factor_error_percent = float(self.textFields[1].Text)
            self.positioning_std_mm = float(self.textFields[2].Text)
            if self.signal_noise_microstrains < 0 or self.gage_factor_error_percent < 0 or self.positioning_std_mm < 0:
                raise ValueError
            self.DialogResult = DialogResult.OK
            self.Close()
        except ValueError:
            MessageBox.Show("Please enter valid non-negative numerical values.", "Input Error", MessageBoxButtons.OK, MessageBoxIcon.Error)

def show_input_form():
    form = InputForm()
    result = form.ShowDialog()
    if result == DialogResult.OK:
        return form.signal_noise_microstrains, form.gage_factor_error_percent, form.positioning_std_mm
    else:
        return None
# endregion

# ----------------------------------------------------------------------------------------------------------------

# # region Run the form to get the test parameters (noise, uncertainty etc.)
def env_flag(name):
    value = Environment.GetEnvironmentVariable(name)
    if value is None:
        return False
    return str(value).strip().lower() in ["1", "true", "yes", "on"]

def env_float(name, default_value):
    value = Environment.GetEnvironmentVariable(name)
    if value is None or str(value).strip() == "":
        return float(default_value)
    return float(value)

def env_int(name, default_value):
    value = Environment.GetEnvironmentVariable(name)
    if value is None or str(value).strip() == "":
        return int(default_value)
    return int(value)

def env_string(name, default_value):
    value = Environment.GetEnvironmentVariable(name)
    if value is None:
        return default_value
    return str(value)

# Initialize parameters. These environment variables make the command usable in
# Mechanical batch tests without requiring a WinForms prompt.
signal_noise_microstrains = 20.0
gage_factor_error_percent = 1.0
positioning_std_mm = 0.5
monte_carlo_samples = env_int("SG_LOAD_RECON_MONTE_CARLO_SAMPLES", 1000)
monte_carlo_seed = env_int("SG_LOAD_RECON_SEED", 20260628)
thermal_file_path = env_string("SG_LOAD_RECON_THERMAL_FILE", "")
known_loads_file_path = env_string("SG_LOAD_RECON_KNOWN_LOADS_FILE", "")
skip_plot = env_flag("SG_LOAD_RECON_NO_PLOT") or env_flag("SG_LOAD_RECON_NO_GUI")
wait_for_cpython = env_flag("SG_LOAD_RECON_WAIT") or env_flag("SG_LOAD_RECON_NO_GUI")

if env_flag("SG_LOAD_RECON_NO_GUI"):
    signal_noise_microstrains = env_float("SG_LOAD_RECON_SIGNAL_NOISE_MICROSTRAINS", signal_noise_microstrains)
    gage_factor_error_percent = env_float("SG_LOAD_RECON_GAGE_FACTOR_ERROR_PERCENT", gage_factor_error_percent)
    positioning_std_mm = env_float("SG_LOAD_RECON_POSITION_STD_MM", positioning_std_mm)
else:
    parameters = show_input_form()
    if parameters:
        signal_noise_microstrains, gage_factor_error_percent, positioning_std_mm = parameters
    else:
        sys.exit()

if signal_noise_microstrains < 0 or gage_factor_error_percent < 0 or positioning_std_mm < 0 or monte_carlo_samples < 0:
    MessageBox.Show("Noise, gage-factor uncertainty, positioning uncertainty, and Monte Carlo sample count must be non-negative.", "Input Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
    sys.exit()
# endregion

# ----------------------------------------------------------------------------------------------------------------

# region Get the existing CSV files from sensitivity_matrix_file_path and measured_SG_strain_FEA_file_path
solution_directory_path = sol_selected_environment.WorkingDir[:-1]
solution_directory_path = solution_directory_path.Replace("\\", "\\\\")
project_path = project_path.Replace("\\", "\\")

measured_SG_strain_FEA_file_name = 'SG_FEA_strain_data.csv'
measured_SG_strain_FEA_file_path = os.path.join(solution_directory_path, measured_SG_strain_FEA_file_name)

# Define the path the cpython script will be executed
cpython_script_name = "load_reconstruction_FEA_cpython_code_only.py"
cpython_script_path = sol_selected_environment.WorkingDir + cpython_script_name
# strain_sensitivity_matrix_file_path will be obtained during the execution of cpython code
# endregion

# Define the load reconstruction function and optional plotter of the estimated loads to be run.
environment_name = str(sol_selected_environment.Parent.Name)
cpython_code = """
import json
import math
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import numpy as np
import pandas as pd

PROJECT_PATH = r'""" + project_path + """'
SOLUTION_DIRECTORY_PATH = r'""" + solution_directory_path + """'
MEASURED_FILE_PATH = r'""" + measured_SG_strain_FEA_file_path + """'
ENVIRONMENT_NAME = """ + repr(environment_name) + """

SIGNAL_NOISE_MICROSTRAINS = float(""" + repr(signal_noise_microstrains) + """)
GAGE_FACTOR_ERROR_PERCENT = float(""" + repr(gage_factor_error_percent) + """)
POSITIONING_STD_MM = float(""" + repr(positioning_std_mm) + """)
MONTE_CARLO_SAMPLES = int(""" + repr(monte_carlo_samples) + """)
MONTE_CARLO_SEED = int(""" + repr(monte_carlo_seed) + """)
THERMAL_FILE_PATH = """ + repr(thermal_file_path) + """
KNOWN_LOADS_FILE_PATH = """ + repr(known_loads_file_path) + """
SKIP_PLOT = bool(""" + repr(skip_plot) + """)


def _unique_existing(paths):
    seen = set()
    out = []
    for path in paths:
        if not path:
            continue
        path = os.path.abspath(path)
        key = os.path.normcase(path)
        if key not in seen and os.path.exists(path):
            seen.add(key)
            out.append(path)
    return out


def find_exact_file(root_path, file_name, allow_recursive=True):
    candidates = []
    direct = os.path.join(root_path, file_name)
    if os.path.exists(direct):
        candidates.append(direct)
    if allow_recursive and os.path.isdir(root_path):
        for root, _dirs, files in os.walk(root_path):
            for file in files:
                if file == file_name:
                    candidates.append(os.path.join(root, file))
    candidates = _unique_existing(candidates)
    if len(candidates) != 1:
        raise RuntimeError("Expected exactly one {0} under {1}; found {2}: {3}".format(file_name, root_path, len(candidates), candidates))
    return candidates[0]


def find_optional_file(file_name, explicit_path=""):
    paths = []
    if explicit_path:
        paths.append(explicit_path)
    for root_path in [SOLUTION_DIRECTORY_PATH, PROJECT_PATH]:
        direct = os.path.join(root_path, file_name)
        if os.path.exists(direct):
            paths.append(direct)
    paths = _unique_existing(paths)
    return paths[0] if paths else ""


def read_json_file(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r") as stream:
        return json.load(stream)


def ensure_finite_matrix(name, matrix):
    if not np.all(np.isfinite(matrix)):
        raise ValueError("{0} contains non-finite values".format(name))


def channel_matrix_from_csv(path, channel_names, target_rows):
    df = pd.read_csv(path)
    if all(channel in df.columns for channel in channel_names):
        values = df.loc[:, channel_names].astype(float).values
    elif df.shape[1] == len(channel_names) + 1:
        values = df.iloc[:, 1:].astype(float).values
    elif df.shape[1] == len(channel_names):
        values = df.iloc[:, :].astype(float).values
    else:
        raise ValueError("{0} has shape {1}, expected columns matching measured strain channels".format(path, df.shape))
    if values.shape[0] == 1 and target_rows > 1:
        values = np.repeat(values, target_rows, axis=0)
    if values.shape != (target_rows, len(channel_names)):
        raise ValueError("{0} produces matrix shape {1}, expected {2}".format(path, values.shape, (target_rows, len(channel_names))))
    ensure_finite_matrix(path, values)
    return values


def _load_index_from_label(value, load_count):
    text = str(value)
    match = re.search(r"(\\d+)$", text)
    if match:
        idx = int(match.group(1)) - 1
        if 0 <= idx < load_count:
            return idx
    try:
        idx = int(float(text)) - 1
        if 0 <= idx < load_count:
            return idx
    except Exception:
        pass
    return None


def load_placement_sensitivity(path, channel_names, load_count, warnings_list):
    if POSITIONING_STD_MM <= 0:
        return None, None
    if not path or not os.path.exists(path):
        warnings_list.append("Positioning Std. Uncertainty [mm] is nonzero, but strain_sensitivity_placement_sensitivity.csv was not found; placement uncertainty was not propagated.")
        return None, None
    df = pd.read_csv(path)
    required = ["Channel", "Load Case", "d_epsilon_d_x_per_mm", "d_epsilon_d_y_per_mm"]
    if any(column not in df.columns for column in required):
        warnings_list.append("Placement sensitivity file is missing one of these columns: {0}; placement uncertainty was not propagated.".format(required))
        return None, None
    gx = np.zeros((len(channel_names), load_count), dtype=float)
    gy = np.zeros((len(channel_names), load_count), dtype=float)
    filled = np.zeros((len(channel_names), load_count), dtype=bool)
    channel_index = {str(channel): index for index, channel in enumerate(channel_names)}
    for _row_index, row in df.iterrows():
        channel = str(row["Channel"])
        if channel not in channel_index:
            continue
        load_index = _load_index_from_label(row["Load Case"], load_count)
        if load_index is None:
            continue
        try:
            x_value = float(row["d_epsilon_d_x_per_mm"])
            y_value = float(row["d_epsilon_d_y_per_mm"])
        except Exception:
            continue
        if math.isfinite(x_value) and math.isfinite(y_value):
            gx[channel_index[channel], load_index] = x_value
            gy[channel_index[channel], load_index] = y_value
            filled[channel_index[channel], load_index] = True
    if not filled.any():
        warnings_list.append("Placement sensitivity file did not contain numeric derivatives; placement uncertainty was not propagated.")
        return None, None
    if not filled.all():
        warnings_list.append("Placement sensitivity file is incomplete; missing derivatives were treated as zero.")
    return gx, gy


def solver_text_mentions_isothermal():
    for file_name in ["CAERep.xml", "ds.dat"]:
        path = os.path.join(SOLUTION_DIRECTORY_PATH, file_name)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", errors="ignore") as stream:
                text = stream.read()
        except TypeError:
            with open(path, "r") as stream:
                text = stream.read()
        if "Isothermal Heating" in text or "Isothermal" in text:
            return True
    folder = os.path.abspath(SOLUTION_DIRECTORY_PATH)
    for _level in range(6):
        if not os.path.isdir(folder):
            break
        for file_name in os.listdir(folder):
            if not file_name.lower().endswith(".wbpj"):
                continue
            path = os.path.join(folder, file_name)
            try:
                with open(path, "r", errors="ignore") as stream:
                    text = stream.read()
            except TypeError:
                with open(path, "r") as stream:
                    text = stream.read()
            if "Isothermal Heating" in text or "Isothermal" in text:
                return True
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return False


def metadata_confirms_finite_channel_average(metadata):
    channels = metadata.get("channels", [])
    if not channels:
        return False
    for channel in channels:
        body = channel.get("sg_grid_body", {})
        model_type = str(body.get("model_type", "")).lower()
        geometry_type = str(body.get("geometry_type", "")).lower()
        scoped = bool(channel.get("scope_matches_expected_sg_grid_body", False))
        if not scoped or ("shell" not in model_type and "sheet" not in geometry_type):
            return False
    return True


def json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return str(value)


def write_plot(csv_path):
    if SKIP_PLOT:
        return
    try:
        import plotly.graph_objects as go
        import plotly.express as px
        from plotly.offline import plot
    except Exception as exc:
        print("Plot output skipped because Plotly/PyQt dependencies are unavailable: {0}".format(exc))
        return
    data = pd.read_csv(csv_path)
    fig = go.Figure()
    colors = px.colors.qualitative.Light24
    load_columns = [column for column in data.columns if column != "Time [s]"]
    for index, column in enumerate(load_columns):
        fig.add_trace(go.Scatter(
            x=data["Time [s]"],
            y=data[column],
            mode="markers+lines",
            name=column,
            line=dict(color=colors[index % len(colors)], width=2),
            marker=dict(size=3),
        ))
    fig.update_layout(
        title_text="Load Reconstruction - FEA: {0}".format(ENVIRONMENT_NAME),
        title_x=0.5,
        legend_title_text="Component",
        template="plotly_white",
        xaxis_title="Time [s]",
        yaxis_title="Load Factor",
    )
    html_path = os.path.join(SOLUTION_DIRECTORY_PATH, "Load_Reconstruction_FEA_{0}.html".format(ENVIRONMENT_NAME))
    plot(fig, filename=html_path, auto_open=True)


def estimate_loads():
    warnings_list = []
    sensitivity_matrix_file_path = find_exact_file(PROJECT_PATH, "strain_sensitivity_matrix.csv")
    metadata_file_path = find_optional_file("strain_sensitivity_metadata.json")
    placement_sensitivity_file_path = find_optional_file("strain_sensitivity_placement_sensitivity.csv")
    thermal_file_path = find_optional_file("SG_thermal_apparent_strain_data.csv", THERMAL_FILE_PATH)
    known_loads_file_path = find_optional_file("known_loads.csv", KNOWN_LOADS_FILE_PATH)

    S_df = pd.read_csv(MEASURED_FILE_PATH)
    A_df = pd.read_csv(sensitivity_matrix_file_path, header=None)
    metadata = read_json_file(metadata_file_path)

    if S_df.shape[1] < 2:
        raise ValueError("SG_FEA_strain_data.csv must contain Time plus at least one strain channel.")
    channel_names = [str(column) for column in S_df.columns[1:]]
    S_matrix = S_df.iloc[:, 1:].astype(float).values
    A_matrix = A_df.astype(float).values
    ensure_finite_matrix("SG_FEA_strain_data.csv", S_matrix)
    ensure_finite_matrix("strain_sensitivity_matrix.csv", A_matrix)

    if A_matrix.shape[0] != S_matrix.shape[1]:
        raise ValueError("Channel mismatch: measured strain has {0} channels, sensitivity matrix has {1} rows.".format(S_matrix.shape[1], A_matrix.shape[0]))

    metadata_channel_order = metadata.get("channel_order", [])
    if metadata_channel_order and list(metadata_channel_order) != channel_names:
        warnings_list.append("Metadata channel_order does not match SG_FEA_strain_data.csv column order. The solve uses file order only.")
    if not metadata_file_path:
        warnings_list.append("strain_sensitivity_metadata.json was not found; shell-channel scoping and finite-channel-average evidence could not be checked.")
    elif not metadata_confirms_finite_channel_average(metadata):
        warnings_list.append("Metadata does not fully confirm every StrainX_SG result is scoped to the matching shell/sheet SG_Grid_Body channel.")

    if thermal_file_path:
        thermal_matrix = channel_matrix_from_csv(thermal_file_path, channel_names, S_matrix.shape[0])
        S_matrix = S_matrix - thermal_matrix
    elif solver_text_mentions_isothermal():
        warnings_list.append("Isothermal Heating appears to exist, but no SG_thermal_apparent_strain_data.csv was supplied; thermal/apparent strain can reconstruct as fake mechanical load.")

    solution, residuals, rank, singular_values = np.linalg.lstsq(A_matrix, S_matrix.T, rcond=None)
    L_hat_timeseries = solution.T
    predicted_strain = L_hat_timeseries @ A_matrix.T
    residual_matrix = S_matrix - predicted_strain
    condition_number = float(np.inf) if singular_values.size == 0 or singular_values[-1] == 0 else float(singular_values[0] / singular_values[-1])

    load_columns = ["Load {0}".format(index + 1) for index in range(A_matrix.shape[1])]
    estimated_loads_df = pd.DataFrame(L_hat_timeseries, columns=load_columns)
    estimated_loads_df.insert(0, "Time [s]", S_df.iloc[:, 0])

    estimated_loads_csv_file_name = "estimated_loads_with_errors_per_gauge_RMS.csv"
    estimated_loads_csv_file_path = os.path.join(SOLUTION_DIRECTORY_PATH, estimated_loads_csv_file_name)
    estimated_loads_df.to_csv(estimated_loads_csv_file_path, index=False)

    placement_gx, placement_gy = load_placement_sensitivity(placement_sensitivity_file_path, channel_names, A_matrix.shape[1], warnings_list)
    uncertainty_path = os.path.join(SOLUTION_DIRECTORY_PATH, "estimated_loads_uncertainty.csv")
    if MONTE_CARLO_SAMPLES > 0:
        rng = np.random.default_rng(MONTE_CARLO_SEED)
        noise_sigma = SIGNAL_NOISE_MICROSTRAINS * 1e-6
        gage_factor_sigma = GAGE_FACTOR_ERROR_PERCENT / 100.0
        samples = np.empty((MONTE_CARLO_SAMPLES, S_matrix.shape[0], A_matrix.shape[1]), dtype=float)
        for sample_index in range(MONTE_CARLO_SAMPLES):
            strain_sample = np.array(S_matrix, copy=True)
            if noise_sigma > 0:
                strain_sample += rng.normal(0.0, noise_sigma, size=strain_sample.shape)
            if gage_factor_sigma > 0:
                channel_scale = 1.0 + rng.normal(0.0, gage_factor_sigma, size=S_matrix.shape[1])
                strain_sample *= channel_scale.reshape((1, -1))
            if POSITIONING_STD_MM > 0 and placement_gx is not None and placement_gy is not None:
                dx = rng.normal(0.0, POSITIONING_STD_MM, size=S_matrix.shape[1])
                dy = rng.normal(0.0, POSITIONING_STD_MM, size=S_matrix.shape[1])
                dstrain_dx = L_hat_timeseries @ placement_gx.T
                dstrain_dy = L_hat_timeseries @ placement_gy.T
                strain_sample += dstrain_dx * dx.reshape((1, -1)) + dstrain_dy * dy.reshape((1, -1))
            samples[sample_index] = np.linalg.lstsq(A_matrix, strain_sample.T, rcond=None)[0].T
        uncertainty_df = pd.DataFrame({"Time [s]": S_df.iloc[:, 0]})
        for load_index, load_name in enumerate(load_columns):
            values = samples[:, :, load_index]
            uncertainty_df[load_name + " Mean"] = values.mean(axis=0)
            uncertainty_df[load_name + " Std"] = values.std(axis=0, ddof=1) if MONTE_CARLO_SAMPLES > 1 else 0.0
            uncertainty_df[load_name + " P2.5"] = np.percentile(values, 2.5, axis=0)
            uncertainty_df[load_name + " P97.5"] = np.percentile(values, 97.5, axis=0)
        uncertainty_df.to_csv(uncertainty_path, index=False)
    else:
        uncertainty_df = pd.DataFrame({"Time [s]": S_df.iloc[:, 0]})
        for load_name in load_columns:
            uncertainty_df[load_name + " Mean"] = estimated_loads_df[load_name]
            uncertainty_df[load_name + " Std"] = 0.0
            uncertainty_df[load_name + " P2.5"] = estimated_loads_df[load_name]
            uncertainty_df[load_name + " P97.5"] = estimated_loads_df[load_name]
        uncertainty_df.to_csv(uncertainty_path, index=False)

    validation_path = ""
    if known_loads_file_path:
        known_df = pd.read_csv(known_loads_file_path)
        if all(column in known_df.columns for column in load_columns) and len(known_df) == len(estimated_loads_df):
            validation_df = pd.DataFrame({"Time [s]": estimated_loads_df["Time [s]"]})
            for load_name in load_columns:
                validation_df[load_name + " Known"] = known_df[load_name].astype(float)
                validation_df[load_name + " Estimated"] = estimated_loads_df[load_name]
                validation_df[load_name + " Error"] = estimated_loads_df[load_name] - known_df[load_name].astype(float)
            validation_path = os.path.join(SOLUTION_DIRECTORY_PATH, "load_reconstruction_validation.csv")
            validation_df.to_csv(validation_path, index=False)
        else:
            warnings_list.append("known_loads.csv exists but its load columns or row count do not match the reconstruction output; validation CSV was not written.")

    diagnostics = {
        "algorithm": "direct_svd_least_squares_np_linalg_lstsq",
        "normal_equations_used": False,
        "inputs": {
            "measured_strain_file": MEASURED_FILE_PATH,
            "sensitivity_matrix_file": sensitivity_matrix_file_path,
            "metadata_file": metadata_file_path,
            "placement_sensitivity_file": placement_sensitivity_file_path,
            "thermal_apparent_strain_file": thermal_file_path,
            "known_loads_file": known_loads_file_path,
        },
        "parameters": {
            "signal_noise_microstrains": SIGNAL_NOISE_MICROSTRAINS,
            "gage_factor_error_percent_systematic_std": GAGE_FACTOR_ERROR_PERCENT,
            "positioning_std_uncertainty_mm": POSITIONING_STD_MM,
            "monte_carlo_samples": MONTE_CARLO_SAMPLES,
            "monte_carlo_seed": MONTE_CARLO_SEED,
        },
        "matrix": {
            "strain_shape": list(S_matrix.shape),
            "sensitivity_shape": list(A_matrix.shape),
            "rank": int(rank),
            "singular_values": singular_values.tolist(),
            "condition_number": condition_number,
        },
        "finite_channel_averaging": {
            "point_strain_used": False,
            "statement": "The sensitivity and measurement files are interpreted as average strain per SG channel. No second finite-grid averaging correction is applied.",
            "metadata_confirms_shell_channel_average": metadata_confirms_finite_channel_average(metadata),
        },
        "residuals": {
            "rms_per_time": np.sqrt(np.mean(residual_matrix ** 2, axis=1)).tolist(),
            "global_rms": float(np.sqrt(np.mean(residual_matrix ** 2))),
            "max_abs": float(np.max(np.abs(residual_matrix))),
        },
        "outputs": {
            "estimated_loads": estimated_loads_csv_file_path,
            "uncertainty": uncertainty_path,
            "validation": validation_path,
        },
        "warnings": warnings_list,
    }
    diagnostics_path = os.path.join(SOLUTION_DIRECTORY_PATH, "load_reconstruction_diagnostics.json")
    with open(diagnostics_path, "w") as stream:
        json.dump(diagnostics, stream, indent=2, default=json_default)

    if not np.all(np.isfinite(L_hat_timeseries)):
        raise ValueError("Load reconstruction produced non-finite load estimates.")
    for column in uncertainty_df.columns:
        if column.endswith(" Std") and (uncertainty_df[column] < 0).any():
            raise ValueError("Uncertainty output contains a negative standard deviation.")

    print(estimated_loads_df)
    print("CSV file saved at: " + estimated_loads_csv_file_path)
    print("Diagnostics saved at: " + diagnostics_path)
    print("Uncertainty saved at: " + uncertainty_path)
    for message in warnings_list:
        print("WARNING: " + message)
    write_plot(estimated_loads_csv_file_path)


if __name__ == "__main__":
    estimate_loads()
"""

# Use StreamWriter with FileStream to write the cpython file with UTF-8 encoding
with StreamWriter(FileStream(cpython_script_path, FileMode.Create, FileAccess.Write), UTF8Encoding(True)) as writer:
    writer.Write(cpython_code)

print("Python file created successfully with UTF-8 encoding.")
# endregion

# Run the CPython script asynchronously
process = Process()
# Configure the process to hide the window and not use the shell execute feature
#process.StartInfo.CreateNoWindow = True

process.StartInfo.UseShellExecute = True
# Set the command to run the Python interpreter with your script as the argument
process.StartInfo.WindowStyle = ProcessWindowStyle.Minimized
process.StartInfo.FileName = "cmd.exe"  # Use cmd.exe to allow window manipulation
if wait_for_cpython:
    process.StartInfo.Arguments = '/c python "' + cpython_script_path + '"'
else:
    process.StartInfo.Arguments = '/k python "' + cpython_script_path + '"'
# Start the process
process.Start()
if wait_for_cpython:
    process.WaitForExit()
# endregion
