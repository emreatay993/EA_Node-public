import os
import sys
from datetime import datetime
os.environ.setdefault("QT_API", "pyqt6")

import pandas as pd
import numpy as np
import pyvista as pv
from pathlib import Path

from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import (QMainWindow, QHBoxLayout, QWidget, QFileDialog,
                             QMessageBox, QDockWidget, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QHeaderView, QAbstractItemView, QApplication)
from PyQt6.QtCore import Qt, QCoreApplication
from pyvistaqt import MainWindow as PyVistaMainWindow

from .ui_components import ControlPanel, VisualizationPanel, InputDataPanel
from .ui_tools import ContourHoverUI, DistanceMeasureUI, GagePlacementUI, PLACEMENT_COLUMNS
from .ansys_overlay import (
    DEFAULT_BANDS, AnsysAnnotations, AnsysLegend, AnsysLegendInteractor,
    AnsysResultHeader, ansys_rainbow_colormap, format_ansys_number,
    lookup_table_band_colors, lookup_table_range_colors,
)
from .analysis_engine import AnalysisEngine
from .dpf_dialog import DpfImportDialog
from . import dpf_loader
from . import tooltips as tips


def _format_rst_set_summary(set_ids):
    ids = list(set_ids)
    if not ids:
        return "no sets"
    if len(ids) == 1:
        return f"set {ids[0]}"
    if len(ids) <= 6:
        return "sets " + ",".join(str(s) for s in ids)
    if ids == list(range(ids[0], ids[-1] + 1)):
        return f"sets {ids[0]}-{ids[-1]} ({len(ids)} sets)"
    shown = ",".join(str(s) for s in ids[:3])
    return f"sets {shown},...{ids[-1]} ({len(ids)} sets)"


def _format_rst_contour_entry(set_id, times):
    label = "Set {0}".format(int(set_id))
    index = int(set_id) - 1
    if 0 <= index < len(times):
        label += " — time/frequency {0:g}".format(float(times[index]))
    return label


def _parse_contour_set_ids(text, available_ids):
    available_ids = [int(set_id) for set_id in available_ids]
    if not available_ids:
        raise ValueError("No result sets are available for contouring.")
    value = str(text or "").strip().lower()
    if value in ("", "all", "*"):
        return available_ids

    def _set_id(token):
        token = token.strip()
        return available_ids[-1] if token == "last" else int(token)

    requested = []
    try:
        for part in value.replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part and not part.startswith("-"):
                start_text, stop_text = part.split("-", 1)
                start, stop = _set_id(start_text), _set_id(stop_text)
                step = 1 if stop >= start else -1
                requested.extend(range(start, stop + step, step))
            else:
                requested.append(_set_id(part))
    except (TypeError, ValueError):
        raise ValueError(
            "Contour sets must use values such as all, last, 2, 1,3,5, or 2-6."
        )

    requested = list(dict.fromkeys(requested))
    unavailable = [set_id for set_id in requested if set_id not in available_ids]
    if not requested or unavailable:
        raise ValueError(
            "Contour set(s) {0} were not loaded. Available sets: {1}.".format(
                ", ".join(str(set_id) for set_id in unavailable or requested),
                ", ".join(str(set_id) for set_id in available_ids),
            )
        )
    return requested


def _rst_surface_result_indices(result_node_ids, surface):
    """Map each RST surface point to its solver-node result row."""
    if "DPFNodeId" not in surface.point_data:
        raise ValueError("The extracted RST surface does not contain DPFNodeId data.")

    result_node_ids = np.asarray(result_node_ids, dtype=np.int64).reshape(-1)
    surface_node_ids = np.asarray(surface.point_data["DPFNodeId"], dtype=np.int64).reshape(-1)
    if surface_node_ids.size != int(surface.n_points):
        raise ValueError("RST surface node IDs do not match the surface point count.")
    if np.unique(result_node_ids).size != result_node_ids.size:
        raise ValueError("RST result node IDs must be unique.")
    if np.unique(surface_node_ids).size != surface_node_ids.size:
        raise ValueError("RST surface node IDs must be unique.")

    result_indices = dpf_loader._indices_for_ids(result_node_ids, surface_node_ids)
    if result_indices.size != surface_node_ids.size:
        missing = np.setdiff1d(surface_node_ids, result_node_ids)
        example = ", ".join(str(int(node_id)) for node_id in missing[:5])
        raise ValueError(
            "{0} RST surface node(s) have no strain result{1}.".format(
                missing.size,
                " (for example: {0})".format(example) if example else "",
            )
        )
    return result_indices


class MainWindow(QMainWindow):
    """
    The main application window. This class is the "Controller" in the MVC design pattern.
    Its primary roles are:
    1. Assembling the UI from various components (ControlPanel, VisualizationPanel).
    2. Connecting signals from the UI (View) to trigger actions in the logic (Model).
    3. Receiving signals from the logic (Model) and updating the UI (View) with the results.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Strain Gage Positioning Tool v0.4")
        self.resize(1400, 900)

        # --- Application State ---
        self.project_dir = os.getcwd()
        self.input_file = None
        self.display_in_strain = False
        self.engine_thread = None
        self.last_results = {}  # Cache for visualization refreshes
        # Pre-extracted dataset (nodes, coords, strain_tensors) from a .rst via DPF.
        # When set, it takes precedence over self.input_file as the analysis source.
        self.preloaded_dataset = None
        self.rst_surface_mesh = None
        self.rst_named_selection = None
        self.contour_case_entries = []

        # --- UI Setup ---
        self._setup_ui()
        self._apply_tooltips()
        self._connect_signals()

    def _setup_ui(self):
        """Creates and arranges all UI components."""
        main_widget = QWidget()
        main_widget.setObjectName("AppCentralWidget")
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # Instantiate our custom UI components
        self.input_panel = InputDataPanel()
        self.control_panel = ControlPanel()
        self.visualization_panel = VisualizationPanel(self.control_panel)

        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.addWidget(self.input_panel)
        left_column.addWidget(self.control_panel)
        left_container = QWidget()
        left_container.setLayout(left_column)

        main_layout.addWidget(left_container)
        main_layout.addWidget(self.visualization_panel)

        # Attach the distance measurement UI tool to the plotter
        self.distance_tool = DistanceMeasureUI(self.visualization_panel.vtk_widget, units="mm")
        self.contour_hover_tool = ContourHoverUI(self.visualization_panel.vtk_widget)
        self.gage_placement_tool = GagePlacementUI(
            self.visualization_panel.vtk_widget,
            on_changed=self.export_gage_placements,
        )

        # Ansys-Mechanical-style viewport furniture: the top-left information
        # block, the vertical banded legend beneath it, and the draggable
        # callouts on the candidate points.
        plotter = self.visualization_panel.vtk_widget
        self.result_header = AnsysResultHeader(plotter)
        self.result_legend = AnsysLegend(plotter)
        self.result_annotations = AnsysAnnotations(plotter)
        self.legend_interactor = AnsysLegendInteractor(
            plotter,
            self.result_legend,
            on_get_limits=self.get_legend_limits,
            on_set_limits=self.apply_legend_limits,
            on_set_bands=self.apply_legend_band_count,
            on_reset_range=self.reset_legend_range,
        )

        # Create other UI elements like menus and docks
        self._create_menu_bar()
        self._create_candidate_table_dock()

    def _create_menu_bar(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        self.action_set_proj = QAction("Set Project Directory", self)
        self.action_set_proj.triggered.connect(self.set_project_directory)
        file_menu.addAction(self.action_set_proj)

        view_menu = menubar.addMenu("Display")
        self.action_show_table = QAction("Table of Candidate Points", self, checkable=True)
        view_menu.addAction(self.action_show_table)

        self.action_display_strain = QAction("Results in Strain (mm/mm)", self, checkable=True)
        view_menu.addAction(self.action_display_strain)

    def _create_candidate_table_dock(self):
        self.candidate_table_dock = QDockWidget("Candidate Points", self)
        self.candidate_table = QTableWidget()
        self.candidate_table.setAlternatingRowColors(True)
        header = self.candidate_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.candidate_table.horizontalHeader().setStyleSheet(
            "QHeaderView::section { background-color: lightgray; font-weight: bold; }")
        self.candidate_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.candidate_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.candidate_table_dock.setWidget(self.candidate_table)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.candidate_table_dock)
        self.candidate_table_dock.hide()

        # Camera fly-to on row click
        self.candidate_table.cellClicked.connect(self.on_candidate_table_cell_clicked)

    def _apply_tooltips(self):
        """Applies all tooltips to the main window's widgets."""
        # Tooltips for controls are now handled within their respective panel classes.
        self.action_set_proj.setToolTip(tips.SET_PROJECT_DIR)
        self.action_show_table.setToolTip(tips.SHOW_TABLE)
        self.action_display_strain.setToolTip(tips.DISPLAY_STRAIN)

    def _connect_signals(self):
        """Connect the Model, View, and Controller components."""
        # --- Control Panel (View) -> MainWindow (Controller) ---
        self.control_panel.analysis_requested.connect(self.run_analysis)
        self.input_panel.file_load_requested.connect(self.load_strain_data)
        self.input_panel.rst_load_requested.connect(self.load_rst_data)
        self.visualization_panel.chk_override_gage_direction.toggled.connect(
            self.toggle_gage_direction_override
        )
        self.visualization_panel.btn_clear_gage_overrides.clicked.connect(
            self.clear_gage_overrides
        )
        self.visualization_panel.btn_export_gage_placements.clicked.connect(
            self.export_gage_placements
        )

        # --- Menu Actions (View) -> MainWindow (Controller) ---
        self.action_show_table.toggled.connect(self.toggle_candidate_table)
        self.action_display_strain.toggled.connect(self.toggle_display_mode)

        # --- Visualization Panel (View) -> MainWindow (Controller) ---
        self.visualization_panel.visualization_settings_changed.connect(self.refresh_visualization)
        self.visualization_panel.contour_selection_changed.connect(
            self.on_contour_selection_changed
        )

    def set_project_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Project Directory", self.project_dir)
        if directory:
            self.project_dir = directory

    def load_strain_data(self):
        fnames, _ = QFileDialog.getOpenFileNames(self, "Select Strain Data File(s)", self.project_dir,
                                                 "Text Files (*.txt *.dat)")
        if fnames:
            # Store as list for multi-file support, or single path otherwise
            self.input_file = fnames if len(fnames) > 1 else fnames[0]
            # Label: show first file name (+ count if multiple)
            if isinstance(self.input_file, list):
                first = Path(self.input_file[0]).name
                count = len(self.input_file)
                label = f"{first} (+{count-1} more)" if count > 1 else first
            else:
                label = Path(self.input_file).name
            self.input_panel.set_file_label(label)
            self.preloaded_dataset = None  # Text file supersedes any prior .rst import
            self.rst_surface_mesh = None
            self.rst_named_selection = None
            self.contour_case_entries = []
            self.visualization_panel.configure_contour_sets([], reset=True)
            self.visualization_panel.set_surface_placement_enabled(False)
            self.gage_placement_tool.set_context(None, None)
            self.last_results = {}  # Invalidate cache
            self.clear_visualization(preserve_camera=False)

    def load_rst_data(self):
        """Import strain directly from an Ansys .rst result file via DPF.

        Opens the file, lets the user pick a named selection / result sets /
        rotation, then extracts the dataset once and caches it. Re-running the
        analysis (different strategy, units, etc.) reuses the cached extraction
        rather than re-reading the .rst.
        """
        if not dpf_loader.dpf_available():
            QMessageBox.critical(
                self, "DPF Not Available",
                "ansys-dpf-core could not be imported, so .rst files cannot be "
                "read directly.\n\nInstall ansys-dpf-core (with an Ansys/DPF "
                "server) or use the text-file loader instead.")
            return

        rst_path, _ = QFileDialog.getOpenFileName(
            self, "Select Ansys Result File", self.project_dir,
            "Ansys Result Files (*.rst *.rth);;All Files (*)")
        if not rst_path:
            return

        # Inspect the file (cheap) to populate the import dialog.
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            meta = dpf_loader.inspect_rst(rst_path)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Could Not Open Result File",
                                 f"Failed to read '{Path(rst_path).name}':\n\n{e}")
            return
        QApplication.restoreOverrideCursor()

        dialog = DpfImportDialog(rst_path, meta, self)
        if dialog.exec() != DpfImportDialog.DialogCode.Accepted:
            return
        named_selection, set_text, rotate, ignore_evaluation_shells = dialog.get_selection()
        set_ids = dpf_loader.parse_set_ids(set_text, meta.get("n_sets", 1))

        # Extract the dataset (potentially slow on large models).
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            nodes, coords, strain_tensors = dpf_loader.load_rst_strain(
                rst_path, set_ids, named_selection=named_selection,
                rotate_to_global=rotate,
                ignore_stress_evaluation_shells=ignore_evaluation_shells)
            surface_mesh = dpf_loader.load_rst_surface_mesh(
                rst_path,
                named_selection=named_selection,
                ignore_stress_evaluation_shells=ignore_evaluation_shells,
                result_node_ids=nodes if ignore_evaluation_shells else None,
            )
            surface_mesh["result_indices"] = _rst_surface_result_indices(
                nodes, surface_mesh["surface"]
            )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Extraction Failed",
                                 f"Could not extract strain/surface data from '{Path(rst_path).name}':\n\n{e}")
            return
        QApplication.restoreOverrideCursor()

        self.preloaded_dataset = (nodes, coords, strain_tensors)
        self.rst_surface_mesh = surface_mesh
        self.rst_named_selection = named_selection
        times = list(meta.get("times", []) or [])
        self.contour_case_entries = [
            (set_id, _format_rst_contour_entry(set_id, times)) for set_id in set_ids
        ]
        self.input_file = None  # .rst dataset supersedes any text file
        ns_label = named_selection if named_selection else "whole model"
        shell_label = " - evaluation shells ignored" if ignore_evaluation_shells else ""
        self.input_panel.set_file_label(
            f"{Path(rst_path).name} - {ns_label}{shell_label} - "
            f"{_format_rst_set_summary(set_ids)} - {len(nodes):,} nodes")
        self.visualization_panel.set_surface_placement_enabled(True)
        self.last_results = {}  # Invalidate cache
        self.visualization_panel.configure_contour_sets(
            self.contour_case_entries,
            default_aggregation=self.control_panel.get_parameters()["agg_method"],
            reset=True,
        )
        self.display_rst_surface_preview(preserve_camera=False)

    def toggle_display_mode(self, checked):
        self.display_in_strain = checked
        if self.input_file or self.preloaded_dataset is not None:
            # Rerun analysis with the new display unit setting
            self.run_analysis(is_continued_kmeans=False)

    def run_analysis(self, is_continued_kmeans=False):
        """Slot to create and start the analysis engine."""
        if not self.input_file and self.preloaded_dataset is None:
            QMessageBox.warning(self, "Input Error",
                                "Please load a strain data file or import a .rst first.")
            return

        params = self.control_panel.get_parameters()
        self.control_panel.set_button_state_running()

        self.engine_thread = AnalysisEngine(
            self.input_file, params, self.display_in_strain, is_continued_kmeans,
            preloaded_data=self.preloaded_dataset)
        self.engine_thread.analysis_complete.connect(self.on_analysis_complete)
        self.engine_thread.analysis_failed.connect(self.on_analysis_failed)
        self.engine_thread.kmeans_preview_ready.connect(self.on_kmeans_preview_ready)

        QCoreApplication.processEvents()  # Allow UI to update before long computation
        self.engine_thread.run()

    def on_analysis_complete(self, coords, scalars, case_scalars, candidates_df):
        """Slot to receive results from the engine and update the view."""
        self.control_panel.set_button_state_ready()

        if candidates_df.empty and self.control_panel.get_parameters()["strategy"] == "Region of Interest (ROI) Search":
            QMessageBox.warning(self, "ROI Empty", "No data points found within the specified Region of Interest.")

        output_path = os.path.join(self.project_dir, "strain_candidate_points.csv")
        candidates_df.to_csv(output_path, index=False, float_format="%.6e")

        # Decide whether to preserve camera based on whether we have a prior scene
        preserve_camera = bool(self.last_results)
        self.last_results = {
            'coords': coords,
            'scalars': scalars,
            'case_scalars': dict(case_scalars),
            'candidates_df': candidates_df,
        }
        if len(self.contour_case_entries) != len(case_scalars):
            self.contour_case_entries = [
                (index + 1, "Load case {0}".format(index + 1))
                for index in range(len(case_scalars))
            ]
            self.visualization_panel.configure_contour_sets(
                self.contour_case_entries,
                default_aggregation=self.control_panel.get_parameters()["agg_method"],
                reset=True,
            )
        self.gage_placement_tool.set_context(
            self.rst_surface_mesh, candidates_df, self.rst_named_selection
        )

        contour_scalars, contour_label = self._selected_contour_data()
        self._set_contour_legend_limits(contour_scalars)

        # Draw directly, resetting camera on the first render to fit the data bounds
        self.display_strain_with_candidates(
            coords,
            contour_scalars,
            candidates_df,
            preserve_camera=preserve_camera,
            contour_label=contour_label,
        )

        self.update_candidate_table(output_path)

    def on_kmeans_preview_ready(self, coords, cluster_labels):
        """Slot to handle the K-Means preview step."""
        self.control_panel.set_button_state_kmeans_continue()
        self.display_kmeans_preview(coords, cluster_labels)

    def on_analysis_failed(self, error_message):
        """Slot to handle errors reported by the engine."""
        QMessageBox.critical(self, "Analysis Failed", error_message)
        self.control_panel.set_button_state_ready()

    def clear_visualization(self, preserve_camera=False):
        plotter = self.visualization_panel.vtk_widget
        camera = plotter.camera.copy() if preserve_camera else None
        self.contour_hover_tool.clear_context()
        self.result_header.clear()
        self.result_legend.clear()
        self.result_annotations.clear()
        plotter.clear()
        if camera:
            plotter.camera = camera
        else:
            plotter.reset_camera()

    def refresh_visualization(self):
        """Redraws the main plot using cached data and current graphical settings."""
        if not self.last_results:
            if self.rst_surface_mesh:
                self.display_rst_surface_preview(preserve_camera=True)
            return

        contour_scalars, contour_label = self._selected_contour_data()
        self.display_strain_with_candidates(
            self.last_results['coords'],
            contour_scalars,
            self.last_results['candidates_df'],
            preserve_camera=True,
            contour_label=contour_label,
        )

    def _selected_contour_data(self):
        set_text, aggregation, entries = self.visualization_panel.get_contour_selection()
        available_ids = [set_id for set_id, _label in entries]
        selected_ids = _parse_contour_set_ids(set_text, available_ids)
        case_scalars = self.last_results.get('case_scalars', {})
        arrays_by_set = {
            set_id: np.asarray(case_scalars[index], dtype=float)
            for index, (set_id, _label) in enumerate(entries)
        }
        selected_arrays = [arrays_by_set[set_id] for set_id in selected_ids]
        if len(selected_arrays) == 1:
            scalars = selected_arrays[0]
            label = dict(entries)[selected_ids[0]]
        else:
            stack = np.column_stack(selected_arrays)
            scalars = (
                np.max(stack, axis=1)
                if aggregation == "Max"
                else np.mean(stack, axis=1)
            )
            label = "{0} of sets {1}".format(
                aggregation,
                ",".join(str(set_id) for set_id in selected_ids),
            )
        return scalars, label

    def _set_contour_legend_limits(self, scalars):
        if len(scalars) > 0:
            self.visualization_panel.set_legend_limits(
                float(np.min(scalars)), float(np.max(scalars))
            )

    def get_legend_limits(self):
        """Current legend limits, for the legend value editor and context menu."""
        panel = self.visualization_panel
        return (panel.dspin_below_limit.value(), panel.dspin_above_limit.value())

    def apply_legend_limits(self, min_val, max_val):
        """Write new legend limits and redraw.

        ``set_legend_limits`` deliberately blocks the spin-box signals so the
        draw path can push the data range back into the UI without recursing,
        which means the redraw has to be requested explicitly here.
        """
        self.visualization_panel.set_legend_limits(float(min_val), float(max_val))
        self.refresh_visualization()

    def apply_legend_band_count(self, count):
        # setValue emits valueChanged -> visualization_settings_changed -> redraw.
        self.visualization_panel.set_legend_band_count(int(count))

    def reset_legend_range(self):
        """Rescale the legend to the contoured data range."""
        if not self.last_results:
            return
        contour_scalars, _label = self._selected_contour_data()
        self._set_contour_legend_limits(contour_scalars)
        self.refresh_visualization()

    def _result_header_info(self, contour_label):
        """Assemble the Mechanical-style top-left block for the current result."""
        params = self.control_panel.get_parameters()
        mode = str(params["measurement_mode"])
        # Rosette mode contours von Mises equivalent strain; Uniaxial contours
        # the largest normal strain over the swept gage angles (AnalysisEngine).
        quantity = (
            "Equivalent (von Mises) Elastic Strain"
            if mode == "Rosette"
            else "Maximum Normal Elastic Strain"
        )
        metric = str(params["quality_mode"]).split(":")[0].strip()
        unit = "mm/mm" if self.display_in_strain else "microstrain"
        lines = [
            quantity,
            "Type: {0} - {1}".format(mode, metric),
            "Unit: {0}".format(unit),
        ]
        if contour_label:
            lines.append(str(contour_label))
        lines.append(datetime.now().strftime("%Y-%m-%d %H:%M"))
        scoping = self.rst_named_selection or "Whole Model"
        return "A: {0}".format(scoping), lines

    def update_result_overlay(self, contour_actor, scalars, viz_settings, contour_label):
        """Rebuild the header block and banded legend for the current frame.

        The band colours are read back off the mapper's lookup table rather than
        recomputed from the colormap name, so the legend always shows exactly the
        colours the surface was rendered with.
        """
        title, lines = self._result_header_info(contour_label)
        self.result_header.set_info(title, lines)

        try:
            lookup_table = contour_actor.mapper.lookup_table
        except Exception:
            lookup_table = None
        if lookup_table is None:
            self.result_legend.clear()
            return

        n_bands = int(viz_settings.get('n_bands', DEFAULT_BANDS))
        clim = (float(viz_settings['clim_min']), float(viz_settings['clim_max']))
        values = np.asarray(scalars, dtype=float).reshape(-1)
        finite = values[np.isfinite(values)]
        below_color, above_color = lookup_table_range_colors(lookup_table)
        self.result_legend.set_context(
            lookup_table_band_colors(lookup_table, n_bands),
            clim,
            n_bands,
            top_y=self.result_header.bottom_y(),
            below_color=below_color,
            above_color=above_color,
            clipped_below=bool(finite.size and finite.min() < clim[0]),
            clipped_above=bool(finite.size and finite.max() > clim[1]),
        )

    def on_contour_selection_changed(self):
        if not self.last_results:
            return
        try:
            contour_scalars, contour_label = self._selected_contour_data()
        except ValueError as exc:
            QMessageBox.warning(self, "Contour Selection", str(exc))
            self.visualization_panel.edit_contour_sets.setText("all")
            contour_scalars, contour_label = self._selected_contour_data()
        self._set_contour_legend_limits(contour_scalars)
        self.display_strain_with_candidates(
            self.last_results['coords'],
            contour_scalars,
            self.last_results['candidates_df'],
            preserve_camera=True,
            contour_label=contour_label,
        )

    def display_rst_surface_preview(self, preserve_camera=False):
        self.clear_visualization(preserve_camera=preserve_camera)
        plotter = self.visualization_panel.vtk_widget
        if self.rst_surface_mesh and self.rst_surface_mesh.get("surface") is not None:
            self._add_rst_surface_mesh(plotter)
        plotter.render()

    def _add_rst_surface_mesh(self, plotter):
        settings = self.visualization_panel.get_settings()
        plotter.add_mesh(
            self.rst_surface_mesh["surface"],
            color="lightgray",
            opacity=settings.get("surface_mesh_opacity", 1.0),
            show_edges=settings.get("show_surface_edges", True),
            edge_color="dimgray",
            pickable=True,
        )

    def display_strain_with_candidates(
        self, coords, scalars, candidates_df, preserve_camera=False,
        contour_label=None,
    ):
        self.clear_visualization(preserve_camera=preserve_camera)
        plotter = self.visualization_panel.vtk_widget
        viz_settings = self.visualization_panel.get_settings()
        n_bands = int(viz_settings.get('n_bands', DEFAULT_BANDS))
        scalar_title = "Strain (mm/mm)" if self.display_in_strain else "Microstrain"
        if contour_label:
            scalar_title += " — " + str(contour_label)

        if self.rst_surface_mesh and self.rst_surface_mesh.get("surface") is not None:
            surface = self.rst_surface_mesh["surface"]
            result_indices = np.asarray(
                self.rst_surface_mesh.get("result_indices", []), dtype=int
            )
            scalar_values = np.asarray(scalars, dtype=float).reshape(-1)
            if (
                result_indices.size != int(surface.n_points)
                or np.any(result_indices < 0)
                or np.any(result_indices >= scalar_values.size)
            ):
                raise ValueError("The cached RST surface-to-result mapping is invalid.")

            surface.point_data["Scalars"] = scalar_values[result_indices]
            surface.set_active_scalars("Scalars")
            contour_actor = plotter.add_mesh(
                surface,
                scalars="Scalars",
                cmap=ansys_rainbow_colormap(),
                n_colors=n_bands,
                clim=(viz_settings['clim_min'], viz_settings['clim_max']),
                below_color=viz_settings['below_color'],
                above_color=viz_settings['above_color'],
                opacity=viz_settings['surface_mesh_opacity'],
                show_edges=viz_settings['show_surface_edges'],
                edge_color="dimgray",
                interpolate_before_map=True,
                pickable=True,
                show_scalar_bar=False,
            )
            self.contour_hover_tool.set_context(
                contour_actor, surface, "Scalars", scalar_title
            )
        else:
            cloud = pv.PolyData(coords)
            cloud["Scalars"] = np.asarray(scalars, dtype=float)
            contour_actor = plotter.add_mesh(
                cloud, scalars="Scalars",
                cmap=ansys_rainbow_colormap(),
                n_colors=n_bands,
                point_size=viz_settings['cloud_point_size'],
                render_points_as_spheres=True,
                clim=(viz_settings['clim_min'], viz_settings['clim_max']),
                below_color=viz_settings['below_color'],
                above_color=viz_settings['above_color'],
                show_scalar_bar=False,
            )

        if not candidates_df.empty:
            candidate_points = pv.PolyData(candidates_df[['X', 'Y', 'Z']].values)
            plotter.add_mesh(candidate_points, color="magenta",
                             point_size=viz_settings['candidate_point_size'],
                             render_points_as_spheres=True)

            strategy = self.control_panel.get_parameters()["strategy"]
            if "Gradient" in strategy:
                values = candidates_df['Local_Std'].values
                labels = [
                    "P{0}  Std {1}".format(i + 1, format_ansys_number(v, 3))
                    for i, v in enumerate(values)
                ]
            else:
                values = candidates_df['Quality'].values
                max_val = values.max() if len(values) > 0 and values.max() > 0 else 1.0
                labels = [
                    "P{0}  Q {1:.0f}%".format(i + 1, v / max_val * 100)
                    for i, v in enumerate(values)
                ]

            self.result_annotations.set_points(
                candidates_df[['X', 'Y', 'Z']].values,
                labels,
                font_size=viz_settings['label_font_size'],
            )

        self.gage_placement_tool.set_visibility(
            show_normals=viz_settings.get('show_surface_normals', True),
            show_axes=viz_settings.get('show_gage_axes', True),
        )
        self.update_result_overlay(
            contour_actor, scalars, viz_settings, contour_label
        )

        if not preserve_camera: plotter.reset_camera()
        plotter.render()

    def display_kmeans_preview(self, coords, cluster_labels):
        self.clear_visualization(preserve_camera=False)
        plotter = self.visualization_panel.vtk_widget
        viz_settings = self.visualization_panel.get_settings()

        cloud = pv.PolyData(coords)
        cloud["Cluster"] = cluster_labels
        plotter.add_mesh(cloud, scalars="Cluster", cmap="plasma",
                         point_size=viz_settings['cloud_point_size'],
                         render_points_as_spheres=True,
                         scalar_bar_args={'title': "Cluster ID"})
        plotter.add_text("K-Means Preview. Press 'Continue' to select points.",
                         position='upper_left', font_size=14)
        plotter.reset_camera()
        plotter.render()

    def update_candidate_table(self, csv_filepath):
        if not os.path.exists(csv_filepath): return
        try:
            df = pd.read_csv(csv_filepath)
        except Exception as e:
            print(f"Error reading candidate CSV for table: {e}")
            return

        self.candidate_table.clear()
        self.candidate_table.setRowCount(len(df))
        self.candidate_table.setColumnCount(len(df.columns))
        self.candidate_table.setHorizontalHeaderLabels(df.columns.tolist())

        for row_idx, row_data in df.iterrows():
            for col_idx, col_name in enumerate(df.columns):
                cell_value = row_data[col_name]
                if pd.isna(cell_value):
                    item_text = "N/A"
                elif isinstance(cell_value, (int, np.integer)):
                    item_text = f"{cell_value}"
                elif isinstance(cell_value, (float, np.floating)):
                    item_text = f"{cell_value:.4g}"
                else:
                    item_text = str(cell_value)
                item = QTableWidgetItem(item_text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.candidate_table.setItem(row_idx, col_idx, item)

        # Auto-size columns and adjust dock width so all columns are visible
        header = self.candidate_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.candidate_table.resizeColumnsToContents()
        total_width = int(header.length() + self.candidate_table.verticalHeader().width() + self.candidate_table.frameWidth() * 2 + 32)
        self.candidate_table_dock.setMinimumWidth(total_width)
        self.candidate_table_dock.resize(total_width, self.candidate_table_dock.height())

    def on_candidate_table_cell_clicked(self, row, column):
        """
        Fly the camera to the XYZ position of the clicked candidate row.

        Behavior:
        - Reads the table's column headers to locate the 'X', 'Y', 'Z' columns (robust to column order).
        - Parses the numeric values from the clicked row (ignores empty / N/A cells).
        - Uses PyVista's fly_to for a smooth camera transition; falls back to setting the
          camera focal point if fly_to is unavailable in the installed version.
        """
        try:
            # Determine indices of coordinate columns by header name, so this logic
            # remains valid even if the table column order changes in the future.
            headers = [self.candidate_table.horizontalHeaderItem(i).text() for i in range(self.candidate_table.columnCount())]
            x_idx = headers.index('X') if 'X' in headers else None
            y_idx = headers.index('Y') if 'Y' in headers else None
            z_idx = headers.index('Z') if 'Z' in headers else None
            if x_idx is None or y_idx is None or z_idx is None:
                return

            # Helper to get and safely convert a cell's text to float.
            def get_val(col_idx):
                item = self.candidate_table.item(row, col_idx)
                return float(item.text()) if item and item.text() not in (None, '', 'N/A') else None

            x = get_val(x_idx); y = get_val(y_idx); z = get_val(z_idx)
            if x is None or y is None or z is None:
                return
            self.gage_placement_tool.set_active_index(row)
            self.gage_placement_tool.draw()

            plotter = self.visualization_panel.vtk_widget
            try:
                # Preferred smooth navigation when available (PyVista >= certain versions).
                plotter.fly_to((float(x), float(y), float(z)))
            except Exception:
                # Fallback for environments without fly_to: directly move camera focal point.
                cam = plotter.camera
                cam.focal_point = (float(x), float(y), float(z))
                plotter.render()
        except Exception:
            pass

    def toggle_gage_direction_override(self, checked):
        if checked:
            self.distance_tool.disable()
        self.gage_placement_tool.set_override_enabled(checked)

    def clear_gage_overrides(self):
        self.gage_placement_tool.clear_overrides()
        if self.last_results:
            self.refresh_visualization()

    def export_gage_placements(self):
        records = self.gage_placement_tool.placement_records()
        if not records:
            return
        output_path = os.path.join(self.project_dir, "strain_gage_surface_placements.csv")
        pd.DataFrame(records, columns=PLACEMENT_COLUMNS).to_csv(
            output_path, index=False, float_format="%.8g"
        )

    def toggle_candidate_table(self, checked):
        if checked:
            self.candidate_table_dock.show()
            output_path = os.path.join(self.project_dir, "strain_candidate_points.csv")
            self.update_candidate_table(output_path)
        else:
            self.candidate_table_dock.hide()

    def closeEvent(self, event):
        """Ensure the application and any VTK elements close cleanly."""
        self.contour_hover_tool.close()
        self.legend_interactor.close()
        self.result_annotations.close()
        self.visualization_panel.vtk_widget.close()
        event.accept()
