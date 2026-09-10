# region Import libraries
import csv
import context_menu
import clr

clr.AddReference('mscorlib')  # Ensure the core .NET assembly is referenced
from System.IO import StreamWriter, FileStream, FileMode, FileAccess
from System.Text import UTF8Encoding
from System.Diagnostics import Process, ProcessWindowStyle
import os

# endregion

# region Define the plot function to be run
solution_directory_path = sol_selected_environment.WorkingDir[:-1]
solution_directory_path = solution_directory_path.Replace("\\", "\\\\")
file_name_of_SG_calculations = 'SG_calculations.csv'
file_path_of_SG_calculations = os.path.join(solution_directory_path, file_name_of_SG_calculations)

cpython_script_name = "plot_SG_calculations_cpython_code_only.py"
cpython_script_path = sol_selected_environment.WorkingDir + cpython_script_name
cpython_code = """
# region Import necessary modules
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)
try:
    import sys
    import time as time_module
    import socket
    import threading
    import pandas as pd
    import numpy as np
    from scipy.interpolate import interp1d
    import plotly.graph_objects as go
    from plotly.offline import plot
    import plotly.express as px
    import plotly.figure_factory as ff
    from plotly_resampler import FigureResampler
    import os
    import re
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
    from PyQt5 import QtCore
    from PyQt5.QtWidgets import (QApplication, QMainWindow, QLineEdit, QDialog, QHBoxLayout,
                                 QVBoxLayout, QWidget, QMessageBox, QComboBox, QCheckBox, QFileDialog,
                                 QLabel, QSizePolicy, QPushButton, QTableWidget, QTableWidgetItem,
                                 QHeaderView, QProgressBar, QTabWidget)
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    import concurrent.futures
    from concurrent.futures import ThreadPoolExecutor

    import dash
    from dash import Dash, Input, Output, callback_context, dcc, html, no_update, State
    import dash_bootstrap_components as dbc
    # from dash_extensions.enrich import DashProxy, Serverside, ServersideOutputTransform
except ImportError as e:

    app_messagebox = QApplication(sys.argv)
    QMessageBox.critical(None, "Import Error", f"Failed to import a required module: {str(e)}")
    sys.exit(1)
# endregion

# region Define global variables
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
SCRIPT_VERSION = "0.79.1.3"
ROSETTE_ANGLE_COLUMNS = ["Angle_A_deg", "Angle_B_deg", "Angle_C_deg"]
ROSETTE_SETUP_USED_FILENAME = "SG_rosette_setup_used.csv"
my_discrete_color_scheme = px.colors.qualitative.Light24
global selected_group

global my_fig_main
my_fig_main = FigureResampler()
global current_figure_main
current_figure_main = None

global my_fig_comparison
my_fig_comparison = FigureResampler()
global current_figure_comparison
current_figure_comparison = None

global my_fig_comparison_percent
my_fig_comparison_percent = FigureResampler()
global current_figure_comparison_percent
current_figure_comparison_percent = None

global my_fig_compared_data
my_fig_compared_data = FigureResampler()
global current_figure_compared_data
current_figure_compared_data = None

global my_fig_main_and_compared_data
my_fig_main_and_compared_data = FigureResampler()
global current_figure_main_and_compared_data
current_figure_main_and_compared_data = None

selected_group = None
selected_ref_number = None
output_data = None
output_SG_data_w_raw = None
trace_columns = None
use_existing_sg_calculations = False

global comparison_data
comparison_data = None
global comparison_trace_columns
comparison_trace_columns = None
global compare_data
compare_data = None
global compare_data_full
compare_data_full = None
global compare_data_percent_full
compare_data_percent_full = None
global selected_group_comparison
selected_group_comparison = None
global selected_ref_number_comparison
selected_ref_number_comparison = None

global common_columns
common_columns = None


# endregion

# region Define global functions and classes
class MaterialPropertiesDialog(QDialog):
    def __init__(self, parent=None):
        super(MaterialPropertiesDialog, self).__init__(parent)
        self.is_temperature_dependent_properties_checked = False
        self.material_data_df = pd.DataFrame()
        self.temperature_measurement_data_df = pd.DataFrame()
        self.channel_specific_data = pd.DataFrame(columns=["Channel", "Time", "E", "v"])
        self.interpolated_material_data = pd.DataFrame()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Enter Material Properties')
        self.setGeometry(100, 100, 100, 100)
        self.fullWidth = 500
        self.fullHeight = 400
        self.reducedWidth = 400
        self.reducedHeight = 200

        self.setStyleSheet(
            "QWidget { font-size: 11px; } QPushButton { background-color: #0077B6; color: white; border-radius: 5px; padding: 6px; } QLineEdit { border: 1px solid #ccc; border-radius: 5px; padding: 5px; background-color: #ffffff; } QLabel { color: #333; }")

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Adjusting the layout for labels and line edits
        formLayout = QVBoxLayout()

        self.labelE = QLabel("Young's Modulus [GPa]:")
        self.lineEditE = QLineEdit(self)
        formLayout.addWidget(self.labelE)
        formLayout.addWidget(self.lineEditE)

        self.labelV = QLabel("Poisson's Ratio:")
        self.lineEditV = QLineEdit(self)
        formLayout.addWidget(self.labelV)
        formLayout.addWidget(self.lineEditV)

        layout.addLayout(formLayout)

        # Checkbox for time-dependent input
        self.checkbox = QCheckBox("Time and Temperature-Dependent Input:")
        self.checkbox.stateChanged.connect(self.toggle_time_dependent_input)
        layout.addWidget(self.checkbox)

        # Tab widgets to contain the tables
        self.tabs = QTabWidget()
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tabs.addTab(self.tab1, "Material Properties")
        self.tabs.addTab(self.tab2, "Temperature Measurement")
        self.tabs.setVisible(False)

        # Layout for the first tab
        self.tab1_layout = QVBoxLayout()
        self.tab1.setLayout(self.tab1_layout)

        # File selection and data table visibility for the first tab
        fileLayout1 = QHBoxLayout()
        self.fileLabel1 = QLabel("Select a directory for 'T vs. E, v' data:")
        self.fileLabel1.setVisible(False)
        self.selectFileButton1 = QPushButton("Select File")
        self.selectFileButton1.clicked.connect(lambda: self.select_file(1))
        self.selectFileButton1.setVisible(False)
        fileLayout1.addWidget(self.fileLabel1)
        fileLayout1.addWidget(self.selectFileButton1)
        self.tab1_layout.addLayout(fileLayout1)

        self.filePathLineEdit1 = QLineEdit(self)
        self.filePathLineEdit1.setReadOnly(True)
        self.filePathLineEdit1.setVisible(False)
        self.tab1_layout.addWidget(self.filePathLineEdit1)

        # Table to display the data for the first tab
        self.dataTable1 = QTableWidget(self)
        self.dataTable1.setColumnCount(3)
        self.dataTable1.setHorizontalHeaderLabels(["Temperature [°C]", "Young's Modulus [GPa]", "Poisson's Ratio"])
        self.dataTable1.setVisible(False)
        self.dataTable1.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tab1_layout.addWidget(self.dataTable1)

        # Layout for the second tab
        self.tab2_layout = QVBoxLayout()
        self.tab2.setLayout(self.tab2_layout)

        # File selection and data table visibility for the second tab
        fileLayout2 = QHBoxLayout()
        self.fileLabel2 = QLabel("Select a directory for 'Time vs. Temp' data at each measurement point:")
        self.fileLabel2.setVisible(False)
        self.selectFileButton2 = QPushButton("Select File")
        self.selectFileButton2.clicked.connect(lambda: self.select_file(2))
        self.selectFileButton2.setVisible(False)
        fileLayout2.addWidget(self.fileLabel2)
        fileLayout2.addWidget(self.selectFileButton2)
        self.tab2_layout.addLayout(fileLayout2)

        self.filePathLineEdit2 = QLineEdit(self)
        self.filePathLineEdit2.setReadOnly(True)
        self.filePathLineEdit2.setVisible(False)
        self.tab2_layout.addWidget(self.filePathLineEdit2)

        # Table to display the data for the second tab
        self.dataTable2 = QTableWidget(self)
        self.dataTable2.setVisible(False)
        self.dataTable2.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.dataTable2.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.tab2_layout.addWidget(self.dataTable2)

        layout.addWidget(self.tabs)

        # OK and Cancel buttons
        buttonLayout = QHBoxLayout()
        self.okButton = QPushButton('OK')
        self.okButton.clicked.connect(self.acceptInputs)
        cancelButton = QPushButton('Cancel')
        cancelButton.clicked.connect(self.reject)
        buttonLayout.addWidget(self.okButton)
        buttonLayout.addWidget(cancelButton)
        layout.addLayout(buttonLayout)

        self.resize(self.reducedWidth, self.reducedHeight + 100)

    def toggle_time_dependent_input(self, state):
        self.is_temperature_dependent_properties_checked = state == Qt.Checked
        if self.is_temperature_dependent_properties_checked:
            self.resize(self.fullWidth, self.fullHeight)
            self.lineEditE.clear()
            self.lineEditV.clear()
            self.lineEditE.setStyleSheet("background-color: #e0e0e0;")  # Light grey background
            self.lineEditV.setStyleSheet("background-color: #e0e0e0;")  # Light grey background
            self.tabs.setVisible(self.is_temperature_dependent_properties_checked)
        else:
            self.resize(self.reducedWidth, self.reducedHeight)
            self.lineEditE.setStyleSheet("background-color: #ffffff;")  # White background
            self.lineEditV.setStyleSheet("background-color: #ffffff;")  # White background
            self.tabs.setVisible(self.is_temperature_dependent_properties_checked)
        self.lineEditE.setDisabled(self.is_temperature_dependent_properties_checked)
        self.lineEditV.setDisabled(self.is_temperature_dependent_properties_checked)
        self.fileLabel1.setVisible(self.is_temperature_dependent_properties_checked)
        self.selectFileButton1.setVisible(self.is_temperature_dependent_properties_checked)
        self.filePathLineEdit1.setVisible(self.is_temperature_dependent_properties_checked)
        self.dataTable1.setVisible(self.is_temperature_dependent_properties_checked)
        self.fileLabel2.setVisible(self.is_temperature_dependent_properties_checked)
        self.selectFileButton2.setVisible(self.is_temperature_dependent_properties_checked)
        self.filePathLineEdit2.setVisible(self.is_temperature_dependent_properties_checked)
        self.dataTable2.setVisible(self.is_temperature_dependent_properties_checked)

    def select_file(self, tab_index):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "CSV Files (*.csv);;All Files (*)")
        if file_path:
            if tab_index == 1:
                self.filePathLineEdit1.setText(file_path)
                self.load_data(file_path, self.dataTable1, tab_index)
            elif tab_index == 2:
                self.filePathLineEdit2.setText(file_path)
                self.load_data(file_path, self.dataTable2, tab_index)

    def load_data(self, file_path, table, tab_index):
        try:
            data = pd.read_csv(file_path, encoding='ISO-8859-1')
            self.populate_table_and_dataframes(data, table, tab_index)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load the file: {str(e)}")

    def populate_table_and_dataframes(self, data, table, tab_index):
        if tab_index == 1:
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["Temperature [°C]", "Young's Modulus [GPa]", "Poisson's Ratio"])

            # Create a DataFrame for the temperature-dependent material data
            self.material_data_df = pd.DataFrame(
                columns=["Temperature [°C]", "Young's Modulus [GPa]", "Poisson's Ratio"])
        elif tab_index == 2:
            table.setColumnCount(len(data.columns))
            table.setHorizontalHeaderLabels(data.columns)

            # Create a DataFrame for the temperature measurement data
            self.temperature_measurement_data_df = pd.DataFrame(columns=data.columns)

        table.setRowCount(len(data))
        for i, (index, row) in enumerate(data.iterrows()):
            for j in range(len(row)):
                table.setItem(i, j, QTableWidgetItem(str(row.iloc[j])))

        if tab_index == 1:
            self.material_data_df = data
        elif tab_index == 2:
            self.temperature_measurement_data_df = data

        # After populating the data, perform a check to find channels with missing data
        self.check_channel_data_consistency()

        # Check if any temperature measurement is outside the bounds of material data
        min_temp_material = self.material_data_df["Temperature [°C]"].min()
        max_temp_material = self.material_data_df["Temperature [°C]"].max()

        # Get columns of temperature data from time vs temperature measurements data
        temperature_columns = [col for col in self.temperature_measurement_data_df.columns if
                               "Temperature" in col or "[°C]" in col]

        out_of_bounds_temps = self.temperature_measurement_data_df[temperature_columns].apply(
            lambda row: any(
                row.iloc[i] < min_temp_material or row.iloc[i] > max_temp_material for i in range(len(row))), axis=1
        )

        if out_of_bounds_temps.any():
            QMessageBox.warning(self, "Warning",
                                "Some temperature measurements are outside the bounds of material data. "
                                "Material properties for these points will be extrapolated accordingly.")
            return

        table.setVisible(True)

    def natural_sort_key(self, s):
        # Split the SG channel string into parts where digit sequences are treated numerically.
        return [int(num) if num.isdigit() else num for num in re.split(r'(\d+)', s)]

    def check_channel_data_consistency(self):
        # Extract channel identifiers from strain and temperature measurement data
        strain_channels = set([col for col in initial_SG_raw_data.columns if re.match(r'SG\d+_', col)])
        temp_channels = set([col.split('_T')[0] for col in self.temperature_measurement_data_df.columns if
                             ("Temperature" in col or "[°C]" in col) and 'Time' not in col])

        # Channels with strain but no temperature
        missing_temp_channels = strain_channels - temp_channels

        # Channels with temperature but no strain
        missing_strain_channels = temp_channels - strain_channels

        if missing_temp_channels or missing_strain_channels:
            missing_info = []
            if missing_temp_channels:
                # Use the natural_sort_key helper method to sort missing_temp_channels
                sorted_missing_temp_channels = sorted(missing_temp_channels, key=self.natural_sort_key)
                missing_info.append(
                    f"Channels with strain data but missing temperature data: {', '.join(sorted_missing_temp_channels)}")
            if missing_strain_channels:
                # Use the natural_sort_key helper method to sort missing_strain_channels
                sorted_missing_strain_channels = sorted(missing_strain_channels, key=self.natural_sort_key)
                missing_info.append(
                    f"Channels with temperature data but missing strain data: {', '.join(sorted_missing_strain_channels)}")

            QMessageBox.warning(self, "Data Consistency Warning", "".join(missing_info))

    def interpolate_material_properties(self):
        # Prepare a DataFrame to hold the interpolated values for all channels
        # TODO - Resample shorter, lower sampling rate measurement so both strain and temperature has data points at all time points
        # TODO - Change df to be used in initializing depending on which one is longer and has a higher sampling rate
        # TODO - I mean, change either to temperature_measurement_data_df['Time'] or data['Time']

        interpolated_df = pd.DataFrame(index=self.temperature_measurement_data_df.index)

        # Iterate over each channel in the temperature measurement data
        for column in self.temperature_measurement_data_df.columns:
            if "Temperature" in column or "[°C]" in column:
                # Extract channel identifier (e.g., "SG1_1" from "SG_1_1_Temperature [°C]")
                channel_identifier = "_".join(column.split("_")[:-1])

                # Get temperature data for this channel
                temperatures = self.temperature_measurement_data_df[column]

                # Perform interpolation for E and v based on temperature
                E_interp_func = interp1d(
                    self.material_data_df["Temperature [°C]"],
                    self.material_data_df["Young's Modulus [GPa]"] * 1e9,  # Convert to Pa
                    fill_value="extrapolate"
                )
                v_interp_func = interp1d(
                    self.material_data_df["Temperature [°C]"],
                    self.material_data_df["Poisson's Ratio"],
                    fill_value="extrapolate"
                )

                # Apply interpolation to get E and v values for each time step
                E_values = E_interp_func(temperatures)
                v_values = v_interp_func(temperatures)

                # Store the interpolated values in the DataFrame
                interpolated_df[f"{channel_identifier}_E"] = E_values
                interpolated_df[f"{channel_identifier}_v"] = v_values

        # Print the interpolated DataFrame
        print(interpolated_df.head())

        # Store it back into a class attribute to be used later in principal stress calculations
        self.interpolated_material_data = interpolated_df

    def acceptInputs(self):
        if self.is_temperature_dependent_properties_checked == False:
            try:
                E = float(self.lineEditE.text())
                E = E * 1e9  # Convert the [GPa] to SI units [Pa]
                v = float(self.lineEditV.text())
                # Optionally add validation rules here
                if E <= 0 or v <= 0 or v >= 0.5:
                    raise ValueError("Please enter valid values: E > 0 and 0 < v < 0.5")
                self.user_input = {'E': E, 'v': v}
                self.accept()  # Close the dialog and return success
            except ValueError as ve:
                QMessageBox.critical(self, "Input Error", str(ve))

        if self.is_temperature_dependent_properties_checked == True:
            # Perform channel-specific interpolation for E and v
            self.interpolate_material_properties()

            if not self.interpolated_material_data.empty:
                QMessageBox.information(self, "Success", "Material data has been interpolated successfully")
                self.accept()

            # QMessageBox.critical(None, "Error",
            #                      "Temperature and time-dependent SG calculation algorithm is not yet implemented.")


def natural_sort_key(value):
    return [int(num) if num.isdigit() else num for num in re.split(r'(\d+)', str(value))]


def detect_rosette_channels(strain_gauge_data):
    rosette_channels = {}
    for column in strain_gauge_data.columns:
        match = re.search(r'SG(\d+)_', str(column))
        if match:
            sg_number = int(match.group(1))
            rosette_channels.setdefault(sg_number, []).append(column)

    return {
        sg_number: sorted(columns, key=natural_sort_key)
        for sg_number, columns in sorted(rosette_channels.items())
    }


def build_default_rosette_setup(rosette_channels, base_angle=0.0, offsets=None):
    if offsets is None:
        offsets = [0.0, 45.0, 90.0]

    rows = []
    for sg_number in sorted(rosette_channels):
        rows.append({
            "SG": sg_number,
            "Angle_A_deg": base_angle + offsets[0],
            "Angle_B_deg": base_angle + offsets[1],
            "Angle_C_deg": base_angle + offsets[2],
        })
    return pd.DataFrame(rows, columns=["SG"] + ROSETTE_ANGLE_COLUMNS)


def normalize_rosette_setup_dataframe(raw_df, expected_sg_numbers=None):
    if "SG" not in raw_df.columns:
        raise ValueError("The rosette setup CSV must contain an 'SG' column.")

    angle_columns = [column for column in ROSETTE_ANGLE_COLUMNS if column in raw_df.columns]
    if len(angle_columns) == 3:
        source_columns = angle_columns
    else:
        loose_columns = [column for column in raw_df.columns if column != "SG"]
        if len(loose_columns) < 3:
            raise ValueError(
                "The rosette setup CSV must contain explicit Angle_A_deg, Angle_B_deg, "
                "Angle_C_deg columns or at least three angle columns after SG."
            )
        source_columns = loose_columns[:3]

    normalized = raw_df[["SG"] + source_columns].copy()
    normalized.columns = ["SG"] + ROSETTE_ANGLE_COLUMNS

    try:
        normalized["SG"] = pd.to_numeric(normalized["SG"], errors="raise").astype(int)
        for column in ROSETTE_ANGLE_COLUMNS:
            normalized[column] = pd.to_numeric(normalized[column], errors="raise")
    except Exception as exc:
        raise ValueError(f"SG and rosette angle values must be numeric: {exc}")

    duplicate_sgs = sorted(normalized.loc[normalized["SG"].duplicated(), "SG"].unique())
    if duplicate_sgs:
        raise ValueError(f"Duplicate rosette setup rows found for SG: {duplicate_sgs}")

    if expected_sg_numbers is not None:
        expected = set(expected_sg_numbers)
        actual = set(normalized["SG"].tolist())
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing or extra:
            messages = []
            if missing:
                messages.append(f"missing SG rows: {missing}")
            if extra:
                messages.append(f"rows not present in raw data: {extra}")
            raise ValueError("Imported rosette setup does not match the raw data (" + "; ".join(messages) + ").")

        normalized = normalized.set_index("SG").loc[sorted(expected)].reset_index()

    return normalized[["SG"] + ROSETTE_ANGLE_COLUMNS]


class RosetteSetupDialog(QDialog):
    def __init__(self, rosette_channels, initial_directory="", parent=None):
        super(RosetteSetupDialog, self).__init__(parent)
        self.rosette_channels = rosette_channels
        self.initial_directory = initial_directory
        self.rosette_angles_df = build_default_rosette_setup(rosette_channels)
        self.initUI()
        self.populate_table(self.rosette_angles_df)

    def initUI(self):
        self.setWindowTitle("Rosette Setup")
        self.setGeometry(100, 100, 900, 520)
        self.setStyleSheet(
            "QWidget { font-size: 11px; } QPushButton { background-color: #0077B6; color: white; border-radius: 5px; padding: 6px; } "
            "QLineEdit { border: 1px solid #ccc; border-radius: 5px; padding: 5px; background-color: #ffffff; } QLabel { color: #333; }"
        )

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.summaryLabel = QLabel(
            f"Detected {len(self.rosette_channels)} rosettes from the raw SG data. "
            "Review angles, import an optional setup CSV, or export the final setup for traceability."
        )
        layout.addWidget(self.summaryLabel)

        bulkLayout = QHBoxLayout()
        bulkLayout.addWidget(QLabel("Rosette Type:"))
        self.typeComboBox = QComboBox()
        self.typeComboBox.addItems(["Rectangular 0/45/90", "Delta 0/60/120", "Custom"])
        bulkLayout.addWidget(self.typeComboBox)

        bulkLayout.addWidget(QLabel("Base Angle [deg]:"))
        self.baseAngleLineEdit = QLineEdit("0")
        self.baseAngleLineEdit.setFixedWidth(80)
        bulkLayout.addWidget(self.baseAngleLineEdit)

        self.applyAllButton = QPushButton("Apply to All")
        self.applyAllButton.clicked.connect(self.apply_bulk_angles)
        bulkLayout.addWidget(self.applyAllButton)
        bulkLayout.addStretch()
        layout.addLayout(bulkLayout)

        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["SG", "Raw Channels", "Angle_A_deg", "Angle_B_deg", "Angle_C_deg"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        fileLayout = QHBoxLayout()
        self.importButton = QPushButton("Import CSV...")
        self.importButton.clicked.connect(self.import_csv)
        self.exportButton = QPushButton("Export CSV...")
        self.exportButton.clicked.connect(self.export_csv)
        fileLayout.addWidget(self.importButton)
        fileLayout.addWidget(self.exportButton)
        fileLayout.addStretch()
        layout.addLayout(fileLayout)

        buttonLayout = QHBoxLayout()
        self.okButton = QPushButton("Use This Setup")
        self.okButton.clicked.connect(self.accept_setup)
        self.cancelButton = QPushButton("Cancel")
        self.cancelButton.clicked.connect(self.reject)
        buttonLayout.addStretch()
        buttonLayout.addWidget(self.okButton)
        buttonLayout.addWidget(self.cancelButton)
        layout.addLayout(buttonLayout)

    def _make_readonly_item(self, value):
        item = QTableWidgetItem(str(value))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def populate_table(self, setup_df):
        self.table.setRowCount(len(setup_df))
        for row_index, row in setup_df.reset_index(drop=True).iterrows():
            sg_number = int(row["SG"])
            channel_text = ", ".join(self.rosette_channels.get(sg_number, []))
            self.table.setItem(row_index, 0, self._make_readonly_item(sg_number))
            self.table.setItem(row_index, 1, self._make_readonly_item(channel_text))
            for angle_index, column in enumerate(ROSETTE_ANGLE_COLUMNS, start=2):
                self.table.setItem(row_index, angle_index, QTableWidgetItem(str(row[column])))

    def _offsets_for_selected_type(self):
        selected_type = self.typeComboBox.currentText()
        if selected_type.startswith("Rectangular"):
            return [0.0, 45.0, 90.0]
        if selected_type.startswith("Delta"):
            return [0.0, 60.0, 120.0]
        return None

    def apply_bulk_angles(self):
        offsets = self._offsets_for_selected_type()
        if offsets is None:
            QMessageBox.information(self, "Custom Setup", "Edit custom rosette angles directly in the table.")
            return

        try:
            base_angle = float(self.baseAngleLineEdit.text())
        except ValueError:
            QMessageBox.critical(self, "Invalid Base Angle", "Base angle must be numeric.")
            return

        for row in range(self.table.rowCount()):
            for index, offset in enumerate(offsets, start=2):
                self.table.setItem(row, index, QTableWidgetItem(str(base_angle + offset)))

    def dataframe_from_table(self):
        rows = []
        for row in range(self.table.rowCount()):
            sg_item = self.table.item(row, 0)
            try:
                sg_number = int(float(sg_item.text()))
                angles = []
                for column in range(2, 5):
                    item = self.table.item(row, column)
                    if item is None or not item.text().strip():
                        raise ValueError("blank angle")
                    angles.append(float(item.text()))
            except Exception as exc:
                raise ValueError(f"Invalid rosette setup on row {row + 1}: {exc}")

            rows.append({
                "SG": sg_number,
                "Angle_A_deg": angles[0],
                "Angle_B_deg": angles[1],
                "Angle_C_deg": angles[2],
            })

        return normalize_rosette_setup_dataframe(pd.DataFrame(rows), sorted(self.rosette_channels))

    def import_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Rosette Setup CSV",
            self.initial_directory,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return

        try:
            imported_df = pd.read_csv(file_path)
            normalized_df = normalize_rosette_setup_dataframe(imported_df, sorted(self.rosette_channels))
            self.rosette_angles_df = normalized_df
            self.populate_table(normalized_df)
            QMessageBox.information(self, "Rosette Setup Imported", f"Imported rosette setup from {file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Invalid Rosette Setup CSV", str(exc))

    def export_csv(self):
        try:
            setup_df = self.dataframe_from_table()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid Rosette Setup", str(exc))
            return

        default_path = os.path.join(self.initial_directory or os.getcwd(), "SG_rosette_setup.csv")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Rosette Setup CSV",
            default_path,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return

        try:
            setup_df.to_csv(file_path, index=False, encoding="utf-8-sig")
            QMessageBox.information(self, "Rosette Setup Exported", f"Rosette setup saved to {file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Failed to export rosette setup: {exc}")

    def accept_setup(self):
        try:
            self.rosette_angles_df = self.dataframe_from_table()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid Rosette Setup", str(exc))
            return
        self.accept()


class PlotlyViewer(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.qdash = QDash()
        self.load(QtCore.QUrl("http://127.0.0.1:8050"))

    def update_plot(self, fig):
        self.qdash.update_graph(fig)


class PlotWindow(QMainWindow):
    def __init__(self, folder_name, file_name):
        super().__init__()
        self.setWindowTitle('SG Calculations v' + SCRIPT_VERSION + ' : """ + sol_selected_environment.Parent.Name + """')
        self.setGeometry(100, 100, 1000, 550)
        self.folder_name = folder_name
        self.file_name = file_name
        self.initProgressBar()
        self.initUI()

    plot_started = pyqtSignal()
    plot_progress = pyqtSignal(int)
    plot_finished = pyqtSignal()

    def initUI(self):
        file_path = os.path.join(self.folder_name, self.file_name)
        global output_data
        try:
            if use_existing_sg_calculations:
                output_data = pd.read_csv(file_path)
                # Drop columns starting with star symbol (*)
                output_data = output_data.loc[:, ~output_data.columns.str.startswith('*')]
            else:
                output_data = output_SG_data_w_raw

            if 'Time' not in output_data.columns:
                if 'time' in globals() and len(time) == len(output_data):
                    time_df = pd.DataFrame(time).reset_index(drop=True)
                    output_data = pd.concat([time_df, output_data.reset_index(drop=True)], axis=1)
                else:
                    output_data = output_data.reset_index(drop=True)
                    output_data.insert(0, 'Time', output_data.index)
            output_data = output_data.sort_values(by='Time')

        except Exception as e:
            QMessageBox.critical(self, "File Error", f"Failed to read the file: {str(e)}")
            sys.exit(1)

        # Ensure 'Time' is the first column
        cols = ['Time'] + [col for col in output_data if col != 'Time']
        output_data = output_data[cols]

        # Filter Data label setup
        self.label = QLabel("Filter Data:")
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Channel label setup
        self.label_channel = QLabel("Rosette Channel:")
        self.label_channel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label_channel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Combobox setups
        self.comboBox = QComboBox()
        self.comboBox.addItem("All")
        self.comboBox.addItem("Raw Strain Data")
        # Add data groups to the combobox
        self.add_combobox_items()

        self.refNumberComboBox = QComboBox()
        self.refNumberComboBox.addItem("-")  # Similar to "All" functionality
        self.add_ref_number_items()

        self.comboBox.currentIndexChanged.connect(self.update_plot)
        self.refNumberComboBox.currentIndexChanged.connect(self.update_plot)
        self.viewer = PlotlyViewer()
        self.savePlotButton = QPushButton("Save Plot on the Screen as HTML")
        self.savePlotButton.clicked.connect(self.save_current_plot)

        self.offsetZeroButton = QPushButton("Offset-Zero SG's")
        self.offsetZeroButton.clicked.connect(self.offset_zero_sgs)  # Connect to the new function
        if use_existing_sg_calculations:
            self.offsetZeroButton.setEnabled(False)
            self.offsetZeroButton.setToolTip("Offset-zero recalculation needs the raw SG data and rosette setup from a new calculation.")

        self.offsetStartTimeButton = QPushButton("Offset-Zero Start Time")  # New button
        self.offsetStartTimeButton.clicked.connect(self.offset_start_time)  # Connect to the new function

        self.writeCSVButton = QPushButton("Write Full Data to CSV (Main Data)")
        self.writeCSVButton.setToolTip(
            "Click to save the full output data as a CSV file in the specified location. If any offset operation is applied, the CSV file is written with those effects included.")
        self.writeCSVButton.clicked.connect(self.write_full_data_to_csv)

        self.update_plot(0)  # Initialize plot

        # Modify the layout setup to add the label and combobox horizontally
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(self.label)
        filter_layout.addWidget(self.comboBox)
        filter_layout.addWidget(self.label_channel)
        filter_layout.addWidget(self.refNumberComboBox)
        filter_layout.addWidget(self.savePlotButton)
        filter_layout.addWidget(self.offsetZeroButton)
        filter_layout.addWidget(self.offsetStartTimeButton)
        filter_layout.addWidget(self.writeCSVButton)
        filter_layout.addStretch()  # Add stretch to push everything to the left

        # Create the main layout
        layout = QVBoxLayout()

        # Add the filter layout to the main layout using addLayout
        layout.addLayout(filter_layout)

        # Add the rest of your widgets to the layout
        layout.addWidget(self.viewer)
        layout.addWidget(self.progressBar)

        # Set the layout to the central widget
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def initProgressBar(self):
        self.progressBar = QProgressBar(self)
        self.progressBar.setGeometry(30, 40, 300, 25)
        self.progressBar.setMaximum(100)
        self.progressBar.setVisible(False)

        self.plot_started.connect(self.on_plot_started)
        self.plot_progress.connect(self.on_plot_progress)
        self.plot_finished.connect(self.on_plot_finished)

    def on_plot_started(self):
        self.progressBar.setVisible(True)
        self.progressBar.setValue(0)

    def on_plot_progress(self, value):
        self.progressBar.setValue(value)

    def on_plot_finished(self):
        self.progressBar.setValue(100)
        QTimer.singleShot(500, self.hide_progress_bar)

    def hide_progress_bar(self):
        self.progressBar.setVisible(False)

    def add_combobox_items(self):
        suffixes = set()
        global output_data
        for col in output_data.columns:
            if '_' in col and not col.split('_')[1].isdigit():
                suffix = col.split('_', 1)[1]
                suffixes.add(suffix)

        for suffix in sorted(suffixes):
            self.comboBox.addItem(suffix)

    def add_ref_number_items(self):
        global output_data
        ref_numbers = set(
            col.split('_')[1] for col in output_data.columns if '_' in col and col.split('_')[1].isdigit())
        for ref_number in sorted(ref_numbers, key=int):
            self.refNumberComboBox.addItem(ref_number)

    def update_plot(self, index):
        fig: FigureResampler = FigureResampler()
        global selected_group
        global selected_ref_number
        global output_data
        global trace_columns
        selected_group = self.comboBox.currentText()
        selected_ref_number = self.refNumberComboBox.currentText()

        # Determine columns based on the selected suffix
        if selected_group == "All":
            trace_columns = [col for col in output_data.columns if col != 'Time']
            self.refNumberComboBox.setEnabled(False)
            self.refNumberComboBox.setCurrentIndex(0)
        elif selected_group == "Raw Strain Data":
            trace_columns = [col for col in output_data.columns if re.match(r'SG\d+_\d+$', col)]
            self.refNumberComboBox.setEnabled(True)
        else:
            trace_columns = [col for col in output_data.columns if col.endswith(selected_group)]
            self.refNumberComboBox.setEnabled(False)
            self.refNumberComboBox.setCurrentIndex(0)

        # Further filter columns based on the selected reference number
        if selected_ref_number != "-":
            trace_columns = [col for col in trace_columns if col.split('_')[1] == selected_ref_number]

        # Debug output
        print(f"Filtered columns: {trace_columns}")

        self.viewer.update_plot(fig)

    def get_active_tab(self):
        global active_tab_value
        return active_tab_value

    def save_current_plot(self):
        # Retrieve the parent name from the environment for the filename
        parent_name = '''""" + sol_selected_environment.Parent.Name + """'''
        active_tab = self.get_active_tab()

        if active_tab == 'tab-main':
            filename = f"SG_Calculations__{parent_name}__{selected_group}__main.html"
            plot(current_figure_main, filename=os.path.join(self.folder_name, filename),
                 output_type='file', auto_open=False)
        elif active_tab == 'tab-compared-data':
            filename = f"SG_Calculations__{parent_name}__{selected_group}__compared_data.html"
            plot(current_figure_compared_data, filename=os.path.join(self.folder_name, filename),
                 output_type='file', auto_open=False)
        elif active_tab == 'tab-main-and-compared-data':
            filename = f"SG_Calculations__{parent_name}__{selected_group}__main_and_compared_data.html"
            plot(current_figure_main_and_compared_data, filename=os.path.join(self.folder_name, filename),
                 output_type='file', auto_open=False)
        elif active_tab == 'tab-comparison':
            filename = f"SG_Calculations__{parent_name}__{selected_group}__comparison.html"
            plot(current_figure_comparison, filename=os.path.join(self.folder_name, filename),
                 output_type='file', auto_open=False)
        elif active_tab == 'tab-comparison-percent':
            filename = f"SG_Calculations__{parent_name}__{selected_group}__comparison_percent.html"
            plot(current_figure_comparison_percent, filename=os.path.join(self.folder_name, filename),
                 output_type='file', auto_open=False)
        else:
            QMessageBox.warning(self, "Save Plot", "No active plot found to save.")
            return

        QMessageBox.information(self, "Plot Saved",
                                f"The plot has been saved to: {filename} in the solution directory.")

    def offset_zero_sgs(self):
        # Get the unique time points as strings for the combo box
        time_points = [str(tp) for tp in output_data['Time'].unique()]

        dialog = OffsetZeroDialog(self, time_points)
        if dialog.exec_() == QDialog.Accepted:
            selected_time = dialog.get_selected_time()
            self.apply_offset_zero(selected_time)

    def apply_offset_zero(self, selected_time):
        global output_data, initial_SG_raw_data

        # Define a small epsilon value
        epsilon = 1e-10

        # Make a copy of the raw SG data
        raw_data_copy = initial_SG_raw_data.copy()

        # Get the strain columns (assume columns with 'SG' in their name)
        strain_columns = [col for col in raw_data_copy.columns if 'SG' in col]

        # Extract strain data 
        strain_data = raw_data_copy[strain_columns]

        # Add epsilon to any zero values in the strain columns before the offset calculations
        strain_data = strain_data.apply(lambda x: x + (x == 0) * epsilon)

        # Find the index of the selected time
        selected_time_index = output_data[output_data['Time'] == selected_time].index
        if selected_time_index.empty:
            QMessageBox.critical(self, "Error", "Selected time point not found in the data.")
            return
        selected_time_index = selected_time_index[0]

        # Extract the strain values at the selected time point
        offset_values = strain_data.iloc[selected_time_index]

        # Subtract the strains at the selected time point from all strain values
        strain_data = strain_data - offset_values

        # Set all strain values before the selected time point to zero
        strain_data[:selected_time_index] = 0

        # Add epsilon to any zero values again after the offset calculations
        strain_data = strain_data.apply(lambda x: x + (x == 0) * epsilon)

        # Recalculate the SG variables
        output_SG_data_w_raw = calculate_all_SG_variables(strain_data, rosette_angles_df)
        output_SG_data_w_raw.insert(0, 'Time', output_data['Time'])
        # output_SG_data_w_raw.set_index('Time', inplace=True)

        output_data = output_SG_data_w_raw

        # Update the plot
        self.update_plot(0)

    def offset_start_time(self):
        # Get the unique time points as strings for the combo box
        time_points = [str(tp) for tp in output_data['Time'].unique()]

        dialog = OffsetZeroDialog(self, time_points)
        if dialog.exec_() == QDialog.Accepted:
            selected_time = dialog.get_selected_time()
            self.apply_offset_start_time(selected_time)

    def apply_offset_start_time(self, selected_time):
        global output_data

        # Find the index of the selected time
        selected_time_index = output_data[output_data['Time'] == selected_time].index
        if selected_time_index.empty:
            QMessageBox.critical(self, "Error", "Selected time point not found in the data.")
            return
        selected_time_index = selected_time_index[0]

        # Drop data before the selected time point
        output_data = output_data.loc[selected_time_index:].reset_index(drop=True)

        # Offset the time so that the selected time point becomes the new zero
        output_data['Time'] = output_data['Time'] - selected_time

        # Update the plot
        self.update_plot(0)

    def write_full_data_to_csv(self):
        global output_data
        global compare_data_full
        global compare_data_percent_full
        file_path = os.path.join(self.folder_name, self.file_name)

        combined_data = output_data

        try:
            if compare_data_full is not None:
                combined_data = pd.concat([combined_data, compare_data_full], axis=1)

            if compare_data_percent_full is not None:
                combined_data = pd.concat([combined_data, compare_data_percent_full], axis=1)

            combined_data.to_csv(file_path, index=False, encoding='utf-8-sig')
            QMessageBox.information(self, "CSV Saved", f"The full data has been saved as {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to write the CSV file: {str(e)}")


# region Add styles for frontend GUI
tab_style = {'width': '40%', 'height': '3vh', 'line-height': '3vh', 'padding': '0', 'margin': '0', 'font-size': '10px'}
selected_tab_style = {'width': '40%', 'height': '3vh', 'line-height': '3vh', 'padding': '0', 'margin': '0',
                      'font-size': '10px'}


# endregion


class QDash(QtCore.QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._app = my_dash_app
        self.app.layout = html.Div([
            dcc.Tabs(id="tabs-example", value='tab-main', children=[
                dcc.Tab(label='Main Data', value='tab-main', style=tab_style, selected_style=selected_tab_style),
                dcc.Tab(label='Compared Data', value='tab-compared-data', style=tab_style,
                        selected_style=selected_tab_style),
                dcc.Tab(label='Main & Compared Data', value='tab-main-and-compared-data', style=tab_style,
                        selected_style=selected_tab_style),
                dcc.Tab(label='Comparison(Δ)', value='tab-comparison', style=tab_style,
                        selected_style=selected_tab_style),
                dcc.Tab(label='Comparison(%)', value='tab-comparison-percent', style=tab_style,
                        selected_style=selected_tab_style),
            ], style={'width': '60%', 'height': '3vh', 'line-height': '3vh', 'padding': '0', 'margin': '0'}),
            html.Div(id='tabs-content-example', style={'padding': '0'}),
            html.Div(id='comparison-data-loaded', style={'display': 'none'}),
            html.Div(id='dummy-output', style={'display': 'none'})
        ])

    @property
    def app(self):
        return self._app

    def update_graph(self, fig):
        pass


class OffsetZeroDialog(QDialog):
    def __init__(self, parent=None, time_points=None):
        super(OffsetZeroDialog, self).__init__(parent)
        self.setWindowTitle('Select Time Point for Offset-Zero')
        self.setGeometry(100, 100, 300, 100)

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.label = QLabel("Select Time Point:")
        layout.addWidget(self.label)

        self.comboBox = QComboBox()
        self.comboBox.addItems(time_points)
        self.comboBox.setEditable(True)
        layout.addWidget(self.comboBox)

        buttonLayout = QHBoxLayout()
        self.okButton = QPushButton('OK')
        self.okButton.clicked.connect(self.accept)
        cancelButton = QPushButton('Cancel')
        cancelButton.clicked.connect(self.reject)
        buttonLayout.addWidget(self.okButton)
        buttonLayout.addWidget(cancelButton)
        layout.addLayout(buttonLayout)

    def get_selected_time(self):
        return float(self.comboBox.currentText())


# endregion

# region Initialization of main dash app
my_dash_app = Dash(__name__)


# endregion

# region Definition of callback functions required for main dash app

# Update the callback to render the content of each tab
@my_dash_app.callback(
    Output('tabs-content-example', 'children'),
    [Input('tabs-example', 'value')],
    [State('comparison-data-loaded', 'children')],
    prevent_initial_call=False,
)
def render_content(tab, comparison_data_loaded):
    button_style = {
        'width': '12%', 'margin': '0.5vh',
        'font-size': '10px', 'background-color': '#87CEFA',
        'border': 'none', 'border-radius': '8px',
        'cursor': 'pointer', 'transition': 'background-color 0.3s ease'}

    button_success_style = {
        **button_style,
        'background-color': 'green',  # Change to green on success
    }

    if tab == 'tab-main':
        graph = dcc.Graph(
            id="graph-id",
            config={
                'displaylogo': False  # Disable the plotly logo
            },
            style={'width': '100%', 'height': 'calc(100vh - 12vh)', 'overflow': 'auto'}
        )
        if current_figure_main:
            graph.figure = current_figure_main  # Set the current figure if it exists
        return html.Div([
            html.Button("Click to Plot", id="plot-button", n_clicks=0, style=button_style),
            graph
        ])

    elif tab == 'tab-compared-data':
        graph_compared_data = dcc.Graph(
            id="graph-compared-data-id",
            config={
                'displaylogo': False  # Disable the plotly logo
            },
            style={'width': '100%', 'height': 'calc(100vh - 12vh)', 'overflow': 'auto'}
        )
        if current_figure_compared_data:
            graph_compared_data.figure = current_figure_compared_data  # Set the current figure if it exists
        return html.Div([
            html.Button("Click to Plot", id="plot-compared-data-button", n_clicks=0, style=button_style),
            html.Button("Load Comparison CSV", id="load-comparison-csv-button", n_clicks=0, style=button_style),
            graph_compared_data
        ])

    elif tab == 'tab-main-and-compared-data':
        graph_main_and_compared_data = dcc.Graph(
            id="graph-main-and-compared-data-id",
            config={
                'displaylogo': False  # Disable the plotly logo
            },
            style={'width': '100%', 'height': 'calc(100vh - 12vh)', 'overflow': 'auto'}
        )
        if current_figure_main_and_compared_data:
            graph_main_and_compared_data.figure = current_figure_main_and_compared_data  # Set the current figure if it exists
        return html.Div([
            html.Button("Click to Plot", id="plot-main-and-compared-data-button", n_clicks=0, style=button_style),
            graph_main_and_compared_data
        ])

    elif tab == 'tab-comparison':
        graph_comparison = dcc.Graph(
            id="graph-comparison-id",
            config={
                'displaylogo': False  # Disable the plotly logo
            },
            style={'width': '100%', 'height': 'calc(100vh - 12vh)', 'overflow': 'auto'}
        )
        if current_figure_comparison:
            graph_comparison.figure = current_figure_comparison  # Set the current figure if it exists
        return html.Div([
            html.Button("Click to Plot", id="plot-comparison-button", n_clicks=0, style=button_style),
            graph_comparison
        ])

    elif tab == 'tab-comparison-percent':
        graph_comparison_percent = dcc.Graph(
            id="graph-comparison-percent-id",
            config={
                'displaylogo': False  # Disable the plotly logo
            },
            style={'width': '100%', 'height': 'calc(100vh - 12vh)', 'overflow': 'auto'}
        )
        if current_figure_comparison_percent:
            graph_comparison_percent.figure = current_figure_comparison_percent  # Set the current figure if it exists
        return html.Div([
            html.Button("Click to Plot", id="plot-comparison-percent-button", n_clicks=0, style=button_style),
            graph_comparison_percent
        ])


# Update the callback to plot the graph
@my_dash_app.callback(
    Output("graph-id", "figure"),
    Input("plot-button", "n_clicks"),
    prevent_initial_call=False,
)
def plot_graph(n_clicks):
    ctx = callback_context
    global current_figure_main  # Declare the global variable
    if len(ctx.triggered) and "plot-button" in ctx.triggered[0]["prop_id"]:
        global my_fig_main
        global output_data
        global trace_columns

        mainWindow.plot_started.emit()  # Emit the plot started signal

        if len(my_fig_main.data):
            my_fig_main.replace(go.Figure())

        time_data_in_x_axis = output_data['Time']
        total_no_of_traces_to_add = len(trace_columns)

        for idx, col in enumerate(trace_columns):
            color_idx = idx % len(my_discrete_color_scheme)
            my_fig_main.add_trace(go.Scattergl(
                x=time_data_in_x_axis,
                y=output_data[col],
                name=col,
                line=dict(color=my_discrete_color_scheme[color_idx]),
                hovertemplate='%{meta}<br>Time = %{x:.2f} s<br>Data = %{y:.1f}<extra></extra>',
                hoverlabel=dict(font_size=14, bgcolor='rgba(255, 255, 255, 0.5)'),
                meta=col
            ))
            progress = int((idx + 1) / total_no_of_traces_to_add * 100)
            mainWindow.plot_progress.emit(progress)  # Emit the plot progress signal

            my_fig_main.update_layout(
                title_text='SG Calculations : """ + sol_selected_environment.Parent.Name + """ ' + "( " + selected_group + " )",
                title_x=0.45,
                title_y=0.95,
                legend_title_text='Result',
                template="plotly_white",
                plot_bgcolor='rgba(0,0,0,0.005)',
                xaxis_title='Time [s]',
                yaxis_title='Data',
                font=dict(family="Arial, sans-serif", size=12, color="#0077B6"),
                xaxis=dict(showline=True, showgrid=True, showticklabels=True, linewidth=2,
                           tickfont=dict(family='Arial, sans-serif', size=12), tickmode='auto', nticks=30),
                yaxis=dict(showgrid=True, zeroline=False, showline=False, showticklabels=True,
                           linecolor='rgb(204, 204, 204)', tickmode='auto', nticks=30),
                hovermode='closest',
                margin=dict(t=40, b=0)  # Adjust the top margin to bring the graph closer to the title
            )

        current_figure_main = my_fig_main  # Update the global variable with the new figure
        mainWindow.plot_finished.emit()  # Emit the plot finished signal
        return my_fig_main
    else:
        return no_update


@my_dash_app.callback(
    Output('comparison-data-loaded', 'children'),
    Input('load-comparison-csv-button', 'n_clicks'),
    prevent_initial_call=True,
)
def load_comparison_csv(n_clicks):
    if n_clicks:
        global comparison_data
        global compare_data
        global compare_data_full
        global compare_data_percent_full
        global comparison_trace_columns
        global common_columns
        global output_data

        file_path, _ = QFileDialog.getOpenFileName(None, 'Open comparison CSV file', '', 'CSV Files (*.csv)')
        if file_path:
            comparison_data = pd.read_csv(file_path)

            # Drop columns starting with "%" or "Δ"
            comparison_data = comparison_data.loc[:, ~comparison_data.columns.str.startswith(('%', 'Δ'))]

            comparison_trace_columns_all = [col for col in comparison_data.columns if col != 'Time']
            if selected_group == "All":
                comparison_trace_columns = comparison_trace_columns_all
            elif selected_group == "Raw Strain Data":
                comparison_trace_columns = [col for col in comparison_data.columns if re.match(r'SG\d+_\d+$', col)]
            else:
                comparison_trace_columns = [col for col in comparison_data.columns if col.endswith(selected_group)]

            if selected_ref_number != "-":
                comparison_trace_columns = [col for col in comparison_trace_columns if
                                            col.split('_')[1] == selected_ref_number]

            if 'Time' in output_data.columns and 'Time' in comparison_data.columns:
                comparison_time = comparison_data['Time']
                main_time = output_data['Time']

                common_columns = [col for col in comparison_trace_columns_all if
                                  col in comparison_data.columns and col in output_data.columns]
                print(f"Common columns: {common_columns}")

                if len(main_time) > len(comparison_time):
                    interp_func = interp1d(comparison_time, comparison_data[common_columns], axis=0,
                                           fill_value="extrapolate")
                    interpolated_comparison_data = pd.DataFrame(interp_func(main_time), columns=common_columns)
                    interpolated_comparison_data.insert(0, 'Time', main_time)

                    compare_data = output_data[common_columns].values - interpolated_comparison_data[
                        common_columns].values
                    compare_data = pd.DataFrame(compare_data, columns=common_columns)

                    compare_data_full = output_data[common_columns].values - interpolated_comparison_data[
                        common_columns].values
                    compare_data_full = pd.DataFrame(compare_data_full,
                                                     columns=['Δ' + col for col in comparison_trace_columns_all])
                    compare_data_full.insert(0, 'Time', main_time)

                    compare_data_percent_full = ((output_data[common_columns].values / interpolated_comparison_data[
                        common_columns].values) - 1) * 100
                    compare_data_percent_full = pd.DataFrame(compare_data_percent_full, columns=['%' + col for col in
                                                                                                 comparison_trace_columns_all])
                    compare_data_percent_full.insert(0, 'Time', main_time)

                    compare_data.insert(0, 'Time', main_time)
                else:
                    interp_func = interp1d(main_time, output_data[common_columns], axis=0, fill_value="extrapolate")
                    interpolated_main_data = pd.DataFrame(interp_func(comparison_time), columns=common_columns)
                    interpolated_main_data.insert(0, 'Time', comparison_time)

                    compare_data = interpolated_main_data[common_columns].values - comparison_data[
                        common_columns].values
                    compare_data = pd.DataFrame(compare_data, columns=common_columns)

                    compare_data_full = interpolated_main_data[common_columns].values - comparison_data[
                        common_columns].values
                    compare_data_full = pd.DataFrame(compare_data_full,
                                                     columns=['Δ' + col for col in comparison_trace_columns_all])
                    compare_data_full.insert(0, 'Time', comparison_time)

                    compare_data_percent_full = ((interpolated_main_data[common_columns].values / comparison_data[
                        common_columns].values) - 1) * 100
                    compare_data_percent_full = pd.DataFrame(compare_data_percent_full,
                                                             columns=['%' + col for col in
                                                                      comparison_trace_columns_all])
                    compare_data_percent_full.insert(0, 'Time', comparison_time)

                    compare_data.insert(0, 'Time', comparison_time)

                return 'loaded'
            else:
                raise KeyError("'Time' column is missing in one of the DataFrames")
    return no_update


@my_dash_app.callback(
    Output("graph-compared-data-id", "figure"),
    Input("plot-compared-data-button", "n_clicks"),
    prevent_initial_call=False,
)
def plot_compared_data_graph(n_clicks):
    ctx = callback_context
    global current_figure_compared_data
    global my_fig_compared_data
    global output_data
    global compare_data
    global compared_data_trace_columns
    global output_data

    if selected_group == "All":
        compared_data_trace_columns = [col for col in comparison_data.columns if col != 'Time']
    elif selected_group == "Raw Strain Data":
        compared_data_trace_columns = [col for col in comparison_data.columns if re.match(r'SG\d+_\d+$', col)]
    else:
        compared_data_trace_columns = [col for col in comparison_data.columns if col.endswith(selected_group)]

    if selected_ref_number != "-":
        compared_data_trace_columns = [col for col in compared_data_trace_columns if
                                       col.split('_')[1] == selected_ref_number]

    comparison_time = comparison_data['Time']
    main_time = output_data['Time']

    # Determine which dataset has a lower sample rate
    if len(main_time) > len(comparison_time):
        interp_func = interp1d(comparison_time, comparison_data[compared_data_trace_columns], axis=0,
                               fill_value="extrapolate")
        interpolated_comparison_data = pd.DataFrame(interp_func(main_time), columns=compared_data_trace_columns)
        interpolated_comparison_data.insert(0, 'Time', main_time)
        compared_data = interpolated_comparison_data
    else:
        interp_func = interp1d(main_time, output_data[compared_data_trace_columns], axis=0, fill_value="extrapolate")
        interpolated_main_data = pd.DataFrame(interp_func(comparison_time), columns=compared_data_trace_columns)
        interpolated_main_data.insert(0, 'Time', comparison_time)

        compared_data = comparison_data

    if len(ctx.triggered) and "plot-compared-data-button" in ctx.triggered[0]["prop_id"]:
        if compared_data is not None and compared_data_trace_columns is not None:
            my_fig_compared_data.replace(go.Figure())  # Reset the figure

            time_data_in_x_axis = compared_data['Time']
            total_no_of_traces_to_add = len(compared_data_trace_columns)

            mainWindow.plot_started.emit()

            for idx, col in enumerate(compared_data_trace_columns):
                color_idx = idx % len(my_discrete_color_scheme)
                my_fig_compared_data.add_trace(go.Scattergl(
                    x=time_data_in_x_axis,
                    y=compared_data[col],
                    name="*" + col,
                    line=dict(color=my_discrete_color_scheme[color_idx]),
                    hovertemplate='%{meta}<br>Time = %{x:.2f} s<br>Data = %{y:.1f}<extra></extra>',
                    hoverlabel=dict(font_size=14, bgcolor='rgba(255, 255, 255, 0.5)'),
                    meta="*" + col
                ))
                progress = int((idx + 1) / total_no_of_traces_to_add * 100)
                mainWindow.plot_progress.emit(progress)  # Emit the plot progress signal

                my_fig_compared_data.update_layout(
                    title_text='Compared Data : """ + sol_selected_environment.Parent.Name + """ ' + " (" + selected_group + ")",
                    title_x=0.45,
                    title_y=0.95,
                    legend_title_text='Result',
                    template="plotly_white",
                    plot_bgcolor='rgba(0,0,0,0.005)',
                    xaxis_title='Time [s]',
                    yaxis_title='Data',
                    font=dict(family="Arial, sans-serif", size=12, color="#0077B6"),
                    xaxis=dict(showline=True, showgrid=True, showticklabels=True, linewidth=2,
                               tickfont=dict(family='Arial, sans-serif', size=12), tickmode='auto', nticks=30),
                    yaxis=dict(showgrid=True, zeroline=False, showline=False, showticklabels=True,
                               linecolor='rgb(204, 204, 204)', tickmode='auto', nticks=30),
                    hovermode='closest',
                    margin=dict(t=40, b=0)  # Adjust the top margin to bring the graph closer to the title
                )
            current_figure_compared_data = my_fig_compared_data
            mainWindow.plot_finished.emit()
            return my_fig_compared_data
    return no_update


@my_dash_app.callback(
    Output("graph-main-and-compared-data-id", "figure"),
    Input("plot-main-and-compared-data-button", "n_clicks"),
    prevent_initial_call=False,
)
def plot_main_and_compared_data_graph(n_clicks):
    ctx = callback_context
    global current_figure_main_and_compared_data
    global my_fig_main_and_compared_data
    global output_data
    global compare_data
    # global compared_data_trace_columns
    global output_data

    if selected_group == "All":
        main_and_compared_data_trace_columns = [col for col in comparison_data.columns if col != 'Time']
    elif selected_group == "Raw Strain Data":
        main_and_compared_data_trace_columns = [col for col in comparison_data.columns if re.match(r'SG\d+_\d+$', col)]
    else:
        main_and_compared_data_trace_columns = [col for col in comparison_data.columns if col.endswith(selected_group)]

    if selected_ref_number != "-":
        main_and_compared_data_trace_columns = [col for col in main_and_compared_data_trace_columns if
                                                col.split('_')[1] == selected_ref_number]

    comparison_time = comparison_data['Time']
    main_time = output_data['Time']

    common_columns = [col for col in main_and_compared_data_trace_columns if
                      col in comparison_data.columns and col in output_data.columns]

    # Determine which dataset has a lower sample rate
    if len(main_time) > len(comparison_time):
        interp_func = interp1d(comparison_time, comparison_data[common_columns], axis=0, fill_value="extrapolate")
        interpolated_comparison_data = pd.DataFrame(interp_func(main_time), columns=common_columns)
        interpolated_comparison_data.insert(0, 'Time', main_time)

        compared_data = interpolated_comparison_data
        main_data = output_data
    else:
        interp_func = interp1d(main_time, output_data[common_columns], axis=0, fill_value="extrapolate")
        interpolated_main_data = pd.DataFrame(interp_func(comparison_time), columns=common_columns)
        interpolated_main_data.insert(0, 'Time', comparison_time)

        compared_data = comparison_data
        main_data = interpolated_main_data

    if len(ctx.triggered) and "plot-main-and-compared-data-button" in ctx.triggered[0]["prop_id"]:
        if compared_data is not None and main_and_compared_data_trace_columns is not None:
            my_fig_main_and_compared_data.replace(go.Figure())  # Reset the figure

            time_data_in_x_axis = compared_data['Time']
            total_no_of_traces_to_add = len(main_and_compared_data_trace_columns)

            mainWindow.plot_started.emit()

            for idx, col in enumerate(main_and_compared_data_trace_columns):
                color_idx = idx % len(my_discrete_color_scheme)
                my_fig_main_and_compared_data.add_trace(go.Scattergl(
                    x=time_data_in_x_axis,
                    y=main_data[col],
                    name="Main: " + col,
                    line=dict(color=my_discrete_color_scheme[color_idx]),
                    hovertemplate='%{meta}<br>Time = %{x:.2f} s<br>Data = %{y:.1f}<extra></extra>',
                    hoverlabel=dict(font_size=14, bgcolor='rgba(255, 255, 255, 0.5)'),
                    meta="Main: " + col,
                ))

                my_fig_main_and_compared_data.add_trace(go.Scattergl(
                    x=time_data_in_x_axis,
                    y=compared_data[col],
                    name="Comp: " + col,
                    line=dict(color=my_discrete_color_scheme[color_idx], dash='dash'),
                    hovertemplate='%{meta}<br>Time = %{x:.2f} s<br>Data = %{y:.1f}<extra></extra>',
                    hoverlabel=dict(font_size=14, bgcolor='rgba(255, 255, 255, 0.5)'),
                    meta="Comp: " + col,
                ))

                progress = int((idx + 1) / total_no_of_traces_to_add * 100)
                mainWindow.plot_progress.emit(progress)  # Emit the plot progress signal

                my_fig_main_and_compared_data.update_layout(
                    title_text='Overlay Plot : """ + sol_selected_environment.Parent.Name + """ ' + " (" + selected_group + ")",
                    title_x=0.45,
                    title_y=0.95,
                    legend_title_text='Result',
                    template="plotly_white",
                    plot_bgcolor='rgba(0,0,0,0.005)',
                    xaxis_title='Time [s]',
                    yaxis_title='Data',
                    font=dict(family="Arial, sans-serif", size=12, color="#0077B6"),
                    xaxis=dict(showline=True, showgrid=True, showticklabels=True, linewidth=2,
                               tickfont=dict(family='Arial, sans-serif', size=12), tickmode='auto', nticks=30),
                    yaxis=dict(showgrid=True, zeroline=False, showline=False, showticklabels=True,
                               linecolor='rgb(204, 204, 204)', tickmode='auto', nticks=30),
                    hovermode='closest',
                    margin=dict(t=40, b=0)  # Adjust the top margin to bring the graph closer to the title
                )
            current_figure_main_and_compared_data = my_fig_main_and_compared_data
            mainWindow.plot_finished.emit()
            return my_fig_main_and_compared_data
    return no_update


@my_dash_app.callback(
    Output("graph-comparison-id", "figure"),
    Input("plot-comparison-button", "n_clicks"),
    prevent_initial_call=False,
)
def plot_comparison_graph(n_clicks):
    ctx = callback_context
    global current_figure_comparison
    global my_fig_comparison
    global output_data
    global compare_data
    global comparison_trace_columns
    global output_data

    if selected_group == "All":
        comparison_trace_columns = [col for col in comparison_data.columns if col != 'Time']
    elif selected_group == "Raw Strain Data":
        comparison_trace_columns = [col for col in comparison_data.columns if re.match(r'SG\d+_\d+$', col)]
    else:
        comparison_trace_columns = [col for col in comparison_data.columns if col.endswith(selected_group)]

    if selected_ref_number != "-":
        comparison_trace_columns = [col for col in comparison_trace_columns if col.split('_')[1] == selected_ref_number]

    comparison_time = comparison_data['Time']
    main_time = output_data['Time']

    # Determine which dataset has a lower sample rate
    if len(main_time) > len(comparison_time):
        interp_func = interp1d(comparison_time, comparison_data[comparison_trace_columns], axis=0,
                               fill_value="extrapolate")
        interpolated_comparison_data = pd.DataFrame(interp_func(main_time), columns=comparison_trace_columns)
        interpolated_comparison_data.insert(0, 'Time', main_time)

        # Calculate the difference
        compare_data = output_data[comparison_trace_columns].values - interpolated_comparison_data[
            comparison_trace_columns].values
        compare_data = pd.DataFrame(compare_data, columns=comparison_trace_columns)
        compare_data.insert(0, 'Time', main_time)
    else:
        interp_func = interp1d(main_time, output_data[comparison_trace_columns], axis=0, fill_value="extrapolate")
        interpolated_main_data = pd.DataFrame(interp_func(comparison_time), columns=comparison_trace_columns)
        interpolated_main_data.insert(0, 'Time', comparison_time)

        # Calculate the difference
        compare_data = interpolated_main_data[comparison_trace_columns].values - comparison_data[
            comparison_trace_columns].values
        compare_data = pd.DataFrame(compare_data, columns=comparison_trace_columns)
        compare_data.insert(0, 'Time', comparison_time)

    if len(ctx.triggered) and "plot-comparison-button" in ctx.triggered[0]["prop_id"]:
        if compare_data is not None and comparison_trace_columns is not None:
            my_fig_comparison.replace(go.Figure())  # Reset the figure

            time_data_in_x_axis = compare_data['Time']
            total_no_of_traces_to_add = len(comparison_trace_columns)

            mainWindow.plot_started.emit()

            for idx, col in enumerate(comparison_trace_columns):
                color_idx = idx % len(my_discrete_color_scheme)
                my_fig_comparison.add_trace(go.Scattergl(
                    x=time_data_in_x_axis,
                    y=compare_data[col],
                    name="Δ" + col,
                    line=dict(color=my_discrete_color_scheme[color_idx]),
                    hovertemplate='%{meta}<br>Time = %{x:.2f} s<br>Data = %{y:.1f}<extra></extra>',
                    hoverlabel=dict(font_size=14, bgcolor='rgba(255, 255, 255, 0.5)'),
                    meta=col
                ))
                progress = int((idx + 1) / total_no_of_traces_to_add * 100)
                mainWindow.plot_progress.emit(progress)  # Emit the plot progress signal

                my_fig_comparison.update_layout(
                    title_text='Comparison : """ + sol_selected_environment.Parent.Name + """ ' + " (" + selected_group + ")",
                    title_x=0.45,
                    title_y=0.95,
                    legend_title_text='Result',
                    template="plotly_white",
                    plot_bgcolor='rgba(0,0,0,0.005)',
                    xaxis_title='Time [s]',
                    yaxis_title='Data',
                    font=dict(family="Arial, sans-serif", size=12, color="#0077B6"),
                    xaxis=dict(showline=True, showgrid=True, showticklabels=True, linewidth=2,
                               tickfont=dict(family='Arial, sans-serif', size=12), tickmode='auto', nticks=30),
                    yaxis=dict(showgrid=True, zeroline=False, showline=False, showticklabels=True,
                               linecolor='rgb(204, 204, 204)', tickmode='auto', nticks=30),
                    hovermode='closest',
                    margin=dict(t=40, b=0)  # Adjust the top margin to bring the graph closer to the title
                )
            current_figure_comparison = my_fig_comparison
            mainWindow.plot_finished.emit()
            return my_fig_comparison
    return no_update


@my_dash_app.callback(
    Output("graph-comparison-percent-id", "figure"),
    Input("plot-comparison-percent-button", "n_clicks"),
    prevent_initial_call=False,
)
def plot_comparison_percent_graph(n_clicks):
    ctx = callback_context
    global current_figure_comparison_percent
    global my_fig_comparison_percent
    global comparison_trace_columns_percent
    global output_data

    if selected_group == "All":
        comparison_trace_columns_percent = [col for col in comparison_data.columns if col != 'Time']
    elif selected_group == "Raw Strain Data":
        comparison_trace_columns_percent = [col for col in comparison_data.columns if re.match(r'SG\d+_\d+$', col)]
    else:
        comparison_trace_columns_percent = [col for col in comparison_data.columns if col.endswith(selected_group)]

    if selected_ref_number != "-":
        comparison_trace_columns_percent = [col for col in comparison_trace_columns_percent if
                                            col.split('_')[1] == selected_ref_number]

    comparison_time = comparison_data['Time']
    main_time = output_data['Time']

    # Determine which dataset has a lower sample rate
    if len(main_time) > len(comparison_time):
        interp_func = interp1d(comparison_time, comparison_data[comparison_trace_columns_percent], axis=0,
                               fill_value="extrapolate")
        interpolated_comparison_data = pd.DataFrame(interp_func(main_time), columns=comparison_trace_columns_percent)
        interpolated_comparison_data.insert(0, 'Time', main_time)

        # Calculate the difference
        compare_data_percent = ((output_data[comparison_trace_columns_percent].values / interpolated_comparison_data[
            comparison_trace_columns_percent].values) - 1) * 100
        compare_data_percent = pd.DataFrame(compare_data_percent, columns=comparison_trace_columns_percent)
        compare_data_percent.insert(0, 'Time', main_time)
    else:
        interp_func = interp1d(main_time, output_data[comparison_trace_columns_percent], axis=0,
                               fill_value="extrapolate")
        interpolated_main_data = pd.DataFrame(interp_func(comparison_time), columns=comparison_trace_columns_percent)
        interpolated_main_data.insert(0, 'Time', comparison_time)

        # Calculate the difference
        compare_data_percent = ((interpolated_main_data[comparison_trace_columns_percent].values / comparison_data[
            comparison_trace_columns_percent].values) - 1) * 100
        compare_data_percent = pd.DataFrame(compare_data_percent, columns=comparison_trace_columns_percent)
        compare_data_percent.insert(0, 'Time', comparison_time)

    if len(ctx.triggered) and "plot-comparison-percent-button" in ctx.triggered[0]["prop_id"]:
        if compare_data_percent is not None and comparison_trace_columns_percent is not None:
            my_fig_comparison_percent.replace(go.Figure())  # Reset the figure

            time_data_in_x_axis = compare_data_percent['Time']
            total_no_of_traces_to_add = len(comparison_trace_columns_percent)

            mainWindow.plot_started.emit()

            for idx, col in enumerate(comparison_trace_columns_percent):
                color_idx = idx % len(my_discrete_color_scheme)
                my_fig_comparison_percent.add_trace(go.Scattergl(
                    x=time_data_in_x_axis,
                    y=compare_data_percent[col],
                    name="%" + col,
                    line=dict(color=my_discrete_color_scheme[color_idx]),
                    hovertemplate='%{meta}<br>Time = %{x:.2f} s<br>Data = %{y:.1f}%<extra></extra>',
                    hoverlabel=dict(font_size=14, bgcolor='rgba(255, 255, 255, 0.5)'),
                    meta="%" + col
                ))
                progress = int((idx + 1) / total_no_of_traces_to_add * 100)
                mainWindow.plot_progress.emit(progress)  # Emit the plot progress signal

                my_fig_comparison_percent.update_layout(
                    title_text='Comparison : """ + sol_selected_environment.Parent.Name + """ ' + " (" + selected_group + ")",
                    title_x=0.45,
                    title_y=0.95,
                    legend_title_text='Result',
                    template="plotly_white",
                    plot_bgcolor='rgba(0,0,0,0.005)',
                    xaxis_title='Time [s]',
                    yaxis_title='Data',
                    font=dict(family="Arial, sans-serif", size=12, color="#0077B6"),
                    xaxis=dict(showline=True, showgrid=True, showticklabels=True, linewidth=2,
                               tickfont=dict(family='Arial, sans-serif', size=12), tickmode='auto', nticks=30),
                    yaxis=dict(showgrid=True, zeroline=False, showline=False, showticklabels=True,
                               linecolor='rgb(204, 204, 204)', tickmode='auto', nticks=30),
                    hovermode='closest',
                    margin=dict(t=40, b=0)  # Adjust the top margin to bring the graph closer to the title
                )
            current_figure_comparison_percent = my_fig_comparison_percent
            mainWindow.plot_finished.emit()
            return my_fig_comparison_percent
    return no_update


# Callback to update the active tab
@my_dash_app.callback(
    Output('dummy-output', 'children'),  # Dummy output to trigger the callback
    [Input('tabs-example', 'value')]
)
def update_active_tab(tab):
    global active_tab_value
    active_tab_value = tab
    return no_update


# endregion

# region Select existing results or prepare raw SG data and rosette setup
# Initialize the QApplication instance
app_dialog = QApplication(sys.argv)

saved_results_path = os.path.join(r'""" + solution_directory_path + """', r'""" + file_name_of_SG_calculations + """')
if os.path.exists(saved_results_path):
    reply = QMessageBox.question(
        None,
        'File Found',
        "An SG_calculations.csv is found inside the solution directory. Would you like to plot the saved results instead of running a new calculation?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )
    if reply == QMessageBox.Yes:
        use_existing_sg_calculations = True

file_path_SG_raw_data = None
data = pd.DataFrame()
time = pd.Series(dtype=float)
initial_SG_raw_data = pd.DataFrame()
rosette_angles_df = pd.DataFrame(columns=["SG"] + ROSETTE_ANGLE_COLUMNS)

if not use_existing_sg_calculations:
    # File selection for raw strain data
    file_path_SG_raw_data, _ = QFileDialog().getOpenFileName(
        None,
        'Open raw data file for SG rosettes',
        r'""" + solution_directory_path + """',
        'CSV Files (*.csv);;All Files (*)'
    )

    if not file_path_SG_raw_data:
        QMessageBox.information(None, "Raw SG Data Required", "No raw SG data file was selected. The calculation was canceled.")
        sys.exit("Raw SG data selection was canceled.")

    print("Selected SG data:", file_path_SG_raw_data)

    try:
        data = pd.read_csv(file_path_SG_raw_data)
    except Exception as exc:
        QMessageBox.critical(None, "Raw SG Data Error", f"Failed to read raw SG data: {exc}")
        sys.exit("Raw SG data could not be read.")

    if "Time" not in data.columns:
        QMessageBox.critical(None, "Raw SG Data Error", "The raw SG data must contain a 'Time' column.")
        sys.exit("Raw SG data is missing a Time column.")

    time = data["Time"]
    initial_SG_raw_data = data.drop(columns=["Time"]).filter(regex=r'SG\d+_')
    initial_SG_raw_data.reset_index(drop=True, inplace=True)
    time.reset_index(drop=True, inplace=True)

    rosette_channels = detect_rosette_channels(initial_SG_raw_data)
    if not rosette_channels:
        QMessageBox.critical(None, "No Rosettes Detected", "No SG<number>_ channels were detected in the raw SG data.")
        sys.exit("No SG rosette channels were detected.")

    invalid_rosettes = {sg: channels for sg, channels in rosette_channels.items() if len(channels) != 3}
    if invalid_rosettes:
        details = []
        for sg, channels in invalid_rosettes.items():
            details.append(f"SG{sg}: {len(channels)} channels ({', '.join(channels)})")
        QMessageBox.critical(
            None,
            "Invalid Rosette Channel Count",
            "Each rosette must have exactly three raw channels before calculation.\n\n" + "\n".join(details)
        )
        sys.exit("Invalid rosette channel count.")

    rosette_setup_dialog = RosetteSetupDialog(rosette_channels, os.path.dirname(file_path_SG_raw_data))
    if rosette_setup_dialog.exec_() == QDialog.Accepted:
        rosette_angles_df = rosette_setup_dialog.rosette_angles_df
    else:
        QMessageBox.information(None, "Rosette Setup Canceled", "Rosette setup was canceled. The calculation was not run.")
        sys.exit("Rosette setup was canceled.")

    rosette_setup_used_path = os.path.join(r'""" + solution_directory_path + """', ROSETTE_SETUP_USED_FILENAME)
    try:
        rosette_angles_df.to_csv(rosette_setup_used_path, index=False, encoding="utf-8-sig")
        print("Rosette setup used for calculation:", rosette_setup_used_path)
    except Exception as exc:
        QMessageBox.warning(None, "Rosette Setup Trace Warning", f"Calculation will continue, but the rosette setup trace CSV could not be written: {exc}")

    print("Selected raw data from directory:   ", file_path_SG_raw_data)
    print("Rosette setup used:")
    print(rosette_angles_df)
# endregion

# region Define material properties
if not use_existing_sg_calculations:
    material_input_dialog = MaterialPropertiesDialog()
    if material_input_dialog.exec_() == QDialog.Accepted:
        if material_input_dialog.is_temperature_dependent_properties_checked == False:
            E = material_input_dialog.user_input.get('E')
            v = material_input_dialog.user_input.get('v')

            # Convert to numpy column arrays to get individual E and v at each index (therefore, at each time step) later
            E = (np.full(time.shape, E))
            v = (np.full(time.shape, v))

        if material_input_dialog.is_temperature_dependent_properties_checked == True:
            pass

    else:
        sys.exit("Material properties input was canceled or failed.")


# endregion

# region Functions for main calculation loop
def process_sg_number(sg_number, strain_gauge_data, rosette_angles_df):
    sg_cols = sorted([col for col in strain_gauge_data.columns if f'SG{sg_number}_' in col], key=natural_sort_key)
    new_columns = []
    if len(sg_cols) == 3:
        rosette_row = rosette_angles_df[rosette_angles_df['SG'] == sg_number]
        if not rosette_row.empty:
            current_angles = rosette_row.iloc[0][ROSETTE_ANGLE_COLUMNS].values.astype(dtype=np.float64)
            strains = strain_gauge_data[sg_cols].values.astype(dtype=np.float64)
            theta_A, theta_B, theta_C = np.radians(current_angles)

            # Matrix T and its inverse T_inv
            T = np.array([
                [np.cos(theta_A) ** 2, np.sin(theta_A) ** 2, np.sin(theta_A) * np.cos(theta_A)],
                [np.cos(theta_B) ** 2, np.sin(theta_B) ** 2, np.sin(theta_B) * np.cos(theta_B)],
                [np.cos(theta_C) ** 2, np.sin(theta_C) ** 2, np.sin(theta_C) * np.cos(theta_C)]
            ])
            T_inv = np.linalg.inv(T)

            # Vectorized global strains transformation
            global_strains = strains @ T_inv.T

            # Vectorized principal strains calculation
            # epsilon_x = global_strains[:, 0]
            # epsilon_y = global_strains[:, 1]
            C = (global_strains[:, 0] + global_strains[:, 1]) / 2
            R = np.sqrt(((global_strains[:, 0] - global_strains[:, 1]) / 2) ** 2 + (global_strains[:, 2] / 2) ** 2)
            principal_strains = np.stack((C + R, C - R), axis=-1)

            # Vectorized principal stresses calculation
            if material_input_dialog.is_temperature_dependent_properties_checked == False:
                # Compute a constant S matrix for all time points
                S = np.array([
                    [1, v[0]],
                    [v[0], 1]
                ]) * E[0] / (1 - v[0] ** 2)
                principal_stresses = (principal_strains / 1e6) @ S.T / 1e6  # Convert to MPa

            if material_input_dialog.is_temperature_dependent_properties_checked == True:

                strain_time = data['Time'].values  # Time points of strain data
                temp_time = material_input_dialog.temperature_measurement_data_df['Time'].values  # Time points of temperature data

                # Construct column names for E and v
                first_sg_col = sg_cols[0]
                channel_identifier = "_".join(first_sg_col.split('_')[:2])  # e.g., 'SG1_1'

                if f"{channel_identifier}_E" not in material_input_dialog.interpolated_material_data.columns or \
                   f"{channel_identifier}_v" not in material_input_dialog.interpolated_material_data.columns:
                    print(f"Skipping SG{sg_number} due to missing temperature data.")
                    return []

                # Retrieve the corresponding E and v for the current channel
                E_channel_original = material_input_dialog.interpolated_material_data[f"{channel_identifier}_E"].values
                v_channel_original = material_input_dialog.interpolated_material_data[f"{channel_identifier}_v"].values

                # Interpolation functions
                E_interp_func = interp1d(temp_time, E_channel_original, fill_value="extrapolate")
                v_interp_func = interp1d(temp_time, v_channel_original, fill_value="extrapolate")

                # Apply interpolation to get E and v values at strain time points
                E_channel = E_interp_func(strain_time) / 1e6 # Convert from Pa to MPa
                v_channel = v_interp_func(strain_time)


                # Compute the principal stresses at each time step
                S11 = (1 * E_channel) / (1 - v_channel ** 2)
                S12 = (v_channel * E_channel) / (1 - v_channel ** 2)

                # Calculate principal stresses
                principal_stresses_1 = (S11 * principal_strains[:, 0] + S12 * principal_strains[:, 1]) / 1e6
                principal_stresses_2 = (S12 * principal_strains[:, 0] + S11 * principal_strains[:, 1]) / 1e6

                # Stack them together to form the principal stresses matrix
                principal_stresses = np.stack((principal_stresses_1, principal_stresses_2), axis=-1)

            theta_p_rad = 0.5 * np.arctan2(global_strains[:, 2], global_strains[:, 0] - global_strains[:, 1])
            theta_p = np.degrees(theta_p_rad)
            theta_p[theta_p < 0] += 180

            # Vectorized biaxiality ratio calculation
            sigma_1 = np.maximum(np.abs(principal_stresses[:, 0]), np.abs(principal_stresses[:, 1]))
            sigma_2 = np.minimum(np.abs(principal_stresses[:, 0]), np.abs(principal_stresses[:, 1]))
            biaxiality_ratios = sigma_2 / sigma_1

            # Vectorized von Mises stress calculation
            # S1 = principal_stresses[:, 0]
            # S2 = principal_stresses[:, 1]
            von_mises_stresses = np.sqrt(((principal_stresses[:, 0] - principal_stresses[:,
                                                                      1]) ** 2 + principal_stresses[:,
                                                                                 0] ** 2 + principal_stresses[:,
                                                                                           1] ** 2) / 2)

            # Collect results into new columns
            for i, strain_type in enumerate(['epsilon_x [µe]', 'epsilon_y [µe]', 'gamma_xy [µe]']):
                new_columns.append(pd.DataFrame({f'SG{sg_number}_{strain_type}': global_strains[:, i]}))
            new_columns.append(pd.DataFrame({
                f'SG{sg_number}_sigma_1 [MPa]': principal_stresses[:, 0],
                f'SG{sg_number}_sigma_2 [MPa]': principal_stresses[:, 1],
                f'SG{sg_number}_theta_p [°]': theta_p,
                f'SG{sg_number}_Biaxiality_Ratio': biaxiality_ratios,
                f'SG{sg_number}_von_Mises [MPa]': von_mises_stresses
            }))
        else:
            print(f'Angles for Rosette {sg_number} not found in rosette setup.')
    else:
        print(f'SG Cols: {sg_cols}')
        print(f'Unexpected number of columns for Rosette {sg_number}.')
    return new_columns


def calculate_all_SG_variables(strain_gauge_data, rosette_angles_df):
    # Start the timer
    start_time = time_module.time()

    matching_columns = [col for col in strain_gauge_data.columns if re.search(r'SG(\d+)_', col)]
    sg_numbers = sorted(set(int(re.search(r'SG(\d+)_', col).group(1)) for col in matching_columns))

    new_columns_list = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = executor.map(lambda sg_number: process_sg_number(sg_number, strain_gauge_data, rosette_angles_df), sg_numbers)
        for result in results:
            new_columns_list.extend(result)

    # Ensure the new columns are correctly concatenated
    if new_columns_list:
        strain_gauge_data = pd.concat([strain_gauge_data] + new_columns_list, axis=1)
    else:
        pass
        # QMessageBox.information(None, "Info", "No new columns generated during SG variable calculation.")

    # End the timer
    end_time = time_module.time()

    # Calculate elapsed time in seconds (two significant digits)
    elapsed_time = end_time - start_time
    elapsed_time_formatted = f"{elapsed_time:.2f}"

    # Show the completion message with the elapsed time
    QMessageBox.information(None, "Info", f"Calculation is completed in {elapsed_time_formatted} seconds.")

    return strain_gauge_data


# endregion

# region Calculate the SG results
if not use_existing_sg_calculations:
    output_SG_data_w_raw = calculate_all_SG_variables(initial_SG_raw_data, rosette_angles_df)
    output_SG_data_w_raw.insert(0, 'Time', time)
    output_SG_data_w_raw.set_index('Time', inplace=True)
    output_SG_data_w_raw
# endregion

# region Show the results
try:
    def find_available_port(port_list):
        for port in port_list:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('localhost', port)) != 0:
                    return port
        return None


    if __name__ == '__main__':
        app_plot = QApplication(sys.argv)

        # The plotly-resampler callback to update the graph after a relayout event (= zoom/pan)
        my_fig_main.register_update_graph_callback(app=my_dash_app, graph_id="graph-id")
        my_fig_compared_data.register_update_graph_callback(app=my_dash_app, graph_id="graph-compared-data-id")
        my_fig_main_and_compared_data.register_update_graph_callback(app=my_dash_app,
                                                                     graph_id="graph-main-and-compared-data-id")

        mainWindow = PlotWindow('""" + solution_directory_path + """', '""" + file_name_of_SG_calculations + """')
        mainWindow.show()
        available_port = find_available_port([8050, 8051, 8052, 8053])
        if available_port:
            threading.Thread(target=my_dash_app.run_server,
                             kwargs={'debug': False, 'use_reloader': False, 'port': available_port},
                             daemon=True).start()
            print('Available Port: ' + str(available_port))
        sys.exit(app_plot.exec_())
        # os.remove(cpython_script_path)
except Exception as e:
    print(f"An error occurred: {e}")
    input("Press Enter to close...")
# endregion
"""

# Use StreamWriter with FileStream to write the file with UTF-8 encoding
with StreamWriter(FileStream(cpython_script_path, FileMode.Create, FileAccess.Write), UTF8Encoding(True)) as writer:
    writer.Write(cpython_code)

print("Python file created successfully with UTF-8 encoding.")
# endregion

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
# endregion
