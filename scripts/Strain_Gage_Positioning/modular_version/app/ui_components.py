import os
os.environ.setdefault("QT_API", "pyqt6")

import numpy as np
from PyQt6.QtWidgets import (QGroupBox, QVBoxLayout, QGridLayout, QLabel,
                             QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
                             QWidget, QHBoxLayout, QCheckBox, QLineEdit)
from PyQt6.QtCore import Qt, pyqtSignal
from . import tooltips as tips
from .ansys_overlay import (
    DEFAULT_ANNOTATION_FONT_SIZE, DEFAULT_BANDS, MAX_BANDS, MIN_BANDS,
)

# pyvistaqt is a required dependency for the VisualizationPanel
try:
    from pyvistaqt import QtInteractor
except ImportError:
    # This is a fallback. The application will exit if this fails in main_window.py.
    QtInteractor = QWidget


class InputDataPanel(QGroupBox):
    """
    A small panel for loading input data and showing the selected file.
    """
    file_load_requested = pyqtSignal()
    rst_load_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Input Data Controls", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.btn_load = QPushButton("Load Strain Data (text)")
        self.btn_load_rst = QPushButton("Load from .rst (DPF)")
        self.lbl_file = QLabel("No file loaded")
        self.lbl_file.setWordWrap(True)
        layout.addWidget(self.btn_load)
        layout.addWidget(self.btn_load_rst)
        layout.addWidget(self.lbl_file)
        self.btn_load.clicked.connect(self.file_load_requested.emit)
        self.btn_load_rst.clicked.connect(self.rst_load_requested.emit)
        # Tooltips
        self.btn_load.setToolTip(tips.LOAD_STRAIN_DATA)
        self.btn_load_rst.setToolTip(tips.LOAD_RST_DPF)
        self.lbl_file.setToolTip(tips.FILE_LABEL)

    def set_file_label(self, text: str):
        self.lbl_file.setText(text)


class ControlPanel(QGroupBox):
    """
    A widget containing all user controls for the analysis. This class is part of the
    "View" in the MVC pattern. It emits signals when user actions occur.
    """
    # Signal emitted when the user clicks the "Update" / "Run" button.
    analysis_requested = pyqtSignal(bool)  # bool indicates if it's a continued K-Means run


    # Signal emitted when the display unit (strain/microstrain) changes.
    display_mode_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__("Positioning Controls", parent)
        self.setFixedWidth(280)
        self._setup_widgets()
        self._setup_layout()
        self._apply_tooltips()
        self._connect_signals()
        self._update_strategy_controls()

    def _setup_widgets(self):
        """Creates all the control widgets."""

        self.combo_measurement = QComboBox()
        self.combo_measurement.addItems(["Rosette", "Uniaxial"])

        self.combo_strategy = QComboBox()
        self.combo_strategy.addItems([
            "Max Quality (Greedy Search)",
            "Max Coverage (K-Means)",
            "Quality-Filtered K-Means",
            "Greedy Gradient Search",
            "Region of Interest (ROI) Search"
        ])

        self.combo_quality = QComboBox()
        self.combo_quality.addItems([
            "Signal-Noise Ratio: |ε|/(σ+1e-12)",
            "Default: |ε|/(1+σ)",
            "Squared: |ε|/(1+σ²)",
            "Exponential: |ε|·exp(–1000σ)"
        ])

        self.combo_agg = QComboBox()
        self.combo_agg.addItems(["Max", "Average"])

        self.spin_candidate_count = QSpinBox()
        self.spin_candidate_count.setRange(1, 1000)
        self.spin_candidate_count.setValue(10)

        self.dspin_uniformity_radius = QDoubleSpinBox()
        self.dspin_uniformity_radius.setRange(0.1, 1000)
        self.dspin_uniformity_radius.setValue(10.0)
        self.dspin_uniformity_radius.setSingleStep(0.5)

        # --- Strategy-specific controls ---
        self.lbl_min_distance = QLabel("Min Distance [mm]:")
        self.dspin_min_distance = QDoubleSpinBox()
        self.dspin_min_distance.setRange(0, 10000)
        self.dspin_min_distance.setValue(10.0)

        self.lbl_quality_percentile = QLabel("Quality Filter [%ile]:")
        self.dspin_quality_percentile = QDoubleSpinBox()
        self.dspin_quality_percentile.setRange(0.0, 100.0)
        self.dspin_quality_percentile.setValue(75.0)

        # Gradient mode (only used for Greedy Gradient strategy)
        self.lbl_gradient_mode = QLabel("Gradient Mode:")
        self.combo_gradient_mode = QComboBox()
        self.combo_gradient_mode.addItems(["Max Local Std", "Min Local Std"])
        self.combo_gradient_mode.setCurrentText("Max Local Std")

        # --- ROI Group Box ---
        self.roiGroup = QGroupBox("Region of Interest (Sphere)")
        roi_layout = QGridLayout(self.roiGroup)
        self.dspin_roi_x = QDoubleSpinBox();
        self.dspin_roi_x.setRange(-1e6, 1e6)
        self.dspin_roi_y = QDoubleSpinBox();
        self.dspin_roi_y.setRange(-1e6, 1e6)
        self.dspin_roi_z = QDoubleSpinBox();
        self.dspin_roi_z.setRange(-1e6, 1e6)
        self.dspin_roi_radius = QDoubleSpinBox();
        self.dspin_roi_radius.setRange(0, 1e6);
        self.dspin_roi_radius.setValue(50.0)

        roi_layout.addWidget(QLabel("Center X:"), 0, 0);
        roi_layout.addWidget(self.dspin_roi_x, 0, 1)
        roi_layout.addWidget(QLabel("Center Y:"), 1, 0);
        roi_layout.addWidget(self.dspin_roi_y, 1, 1)
        roi_layout.addWidget(QLabel("Center Z:"), 2, 0);
        roi_layout.addWidget(self.dspin_roi_z, 2, 1)
        roi_layout.addWidget(QLabel("Radius:"), 3, 0);
        roi_layout.addWidget(self.dspin_roi_radius, 3, 1)

        # Strain Threshold Filter
        self.thresholdGroup = QGroupBox("Strain Threshold Filter")
        threshold_layout = QGridLayout(self.thresholdGroup)
        self.chk_threshold_enable = QCheckBox("Enable microstrain threshold filter")
        self.dspin_threshold_value = QDoubleSpinBox();
        self.dspin_threshold_value.setRange(0.0, 1e9)
        self.dspin_threshold_value.setValue(10.0)
        self.dspin_threshold_value.setDecimals(3)
        self.combo_threshold_agg = QComboBox();
        self.combo_threshold_agg.addItems(["Average", "Max"])
        self.combo_threshold_agg.setCurrentText("Max")

        threshold_layout.addWidget(self.chk_threshold_enable, 0, 0, 1, 2)
        threshold_layout.addWidget(QLabel("Threshold (με):"), 1, 0)
        threshold_layout.addWidget(self.dspin_threshold_value, 1, 1)
        threshold_layout.addWidget(QLabel("Across load cases:"), 2, 0)
        threshold_layout.addWidget(self.combo_threshold_agg, 2, 1)

        # Initially hide value/agg controls until enabled
        self.dspin_threshold_value.setVisible(False)
        self.combo_threshold_agg.setVisible(False)
        # We also need to hide their labels; to do this simply store refs
        self._lbl_threshold_value = threshold_layout.itemAtPosition(1, 0).widget()
        self._lbl_threshold_agg = threshold_layout.itemAtPosition(2, 0).widget()
        self._lbl_threshold_value.setVisible(False)
        self._lbl_threshold_agg.setVisible(False)

        self.btn_update = QPushButton("Run Analysis")

    def _setup_layout(self):
        """Lays out all the control widgets."""
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        widgets_map = [
            ("Measurement Mode:", self.combo_measurement),
            ("Selection Strategy:", self.combo_strategy),
            ("Quality Metrics Mode:", self.combo_quality),
            ("Aggregation (Multi-Load Case):", self.combo_agg),
            ("Candidate Points Requested:", self.spin_candidate_count),
            ("Uniformity Search Radius [mm]:", self.dspin_uniformity_radius),
            (self.lbl_min_distance, self.dspin_min_distance),
            (self.lbl_gradient_mode, self.combo_gradient_mode),
            (self.lbl_quality_percentile, self.dspin_quality_percentile),
            (None, self.thresholdGroup),
            (None, self.roiGroup)
        ]

        for label, widget in widgets_map:
            if label:
                if isinstance(label, str):
                    main_layout.addWidget(QLabel(label))
                else:  # It's already a widget
                    main_layout.addWidget(label)
            main_layout.addWidget(widget)

        main_layout.addStretch(1)
        main_layout.addWidget(self.btn_update)

    def _apply_tooltips(self):
        """Applies all tooltips to the widgets in this panel."""
        self.btn_update.setToolTip(tips.RUN_ANALYSIS)

        # Core Settings
        self.combo_measurement.setToolTip(tips.MEASUREMENT_MODE)
        self.spin_candidate_count.setToolTip(tips.CANDIDATE_COUNT)
        self.dspin_uniformity_radius.setToolTip(tips.UNIFORMITY_RADIUS)

        # Quality Metrics
        self.combo_quality.setToolTip(tips.QUALITY_MODE)

        # Aggregation Method (with dynamic item tooltips)
        self.combo_agg.setToolTip(tips.AGGREGATION_METHOD)
        agg_map = {
            "Max": tips.AGGREGATION_MAX,
            "Average": tips.AGGREGATION_AVERAGE,
        }
        for i, (text, tooltip) in enumerate(agg_map.items()):
            self.combo_agg.setItemData(i, tooltip, Qt.ItemDataRole.ToolTipRole)

        # Selection Strategy (with dynamic item tooltips)
        self.combo_strategy.setToolTip(tips.SELECTION_STRATEGY)
        strategy_map = {
            "Max Quality (Greedy Search)": tips.STRATEGY_QUALITY_GREEDY,
            "Max Coverage (K-Means)": tips.STRATEGY_KMEANS,
            "Quality-Filtered K-Means": tips.STRATEGY_FILTERED_KMEANS,
            "Greedy Gradient Search": tips.STRATEGY_GRADIENT_GREEDY,
            "Region of Interest (ROI) Search": tips.STRATEGY_ROI,
        }
        for i, (text, tooltip) in enumerate(strategy_map.items()):
            self.combo_strategy.setItemData(i, tooltip, Qt.ItemDataRole.ToolTipRole)

        # Strategy-Specific Parameters
        self.dspin_min_distance.setToolTip(tips.MIN_DISTANCE)
        self.dspin_quality_percentile.setToolTip(tips.QUALITY_PERCENTILE)
        self.roiGroup.setToolTip(tips.ROI_GROUP)
        self.thresholdGroup.setToolTip(tips.STRAIN_THRESHOLD_GROUP)
        self.dspin_threshold_value.setToolTip(tips.STRAIN_THRESHOLD_VALUE)
        self.combo_threshold_agg.setToolTip(tips.STRAIN_THRESHOLD_AGG)
        self.combo_gradient_mode.setToolTip(tips.GRADIENT_MODE)

    def _connect_signals(self):
        """Connects widget signals to this panel's internal logic or output signals."""
        self.btn_update.clicked.connect(self._on_update_clicked)
        self.combo_strategy.currentTextChanged.connect(self._update_strategy_controls)
        self.chk_threshold_enable.toggled.connect(self._on_threshold_toggle)

    def _on_update_clicked(self):
        """Determines if the analysis is a continuation of K-Means."""
        is_continuation = "Continue" in self.btn_update.text()
        self.analysis_requested.emit(is_continuation)

    def _update_strategy_controls(self):
        """Shows or hides GUI controls based on the selected strategy."""
        strategy = self.combo_strategy.currentText()
        is_greedy = "Greedy" in strategy or "ROI" in strategy
        is_roi = "ROI" in strategy
        is_filtered_kmeans = "Filtered" in strategy
        is_gradient = "Gradient" in strategy

        self.lbl_min_distance.setVisible(is_greedy)
        self.dspin_min_distance.setVisible(is_greedy)
        self.lbl_gradient_mode.setVisible(is_gradient)
        self.combo_gradient_mode.setVisible(is_gradient)
        self.lbl_quality_percentile.setVisible(is_filtered_kmeans)
        self.dspin_quality_percentile.setVisible(is_filtered_kmeans)
        self.roiGroup.setVisible(is_roi)

        # Reset button text if strategy changes away from K-Means preview
        if "K-Means" not in strategy and "Continue" in self.btn_update.text():
            self.set_button_state_ready()

    def _on_threshold_toggle(self, checked: bool):
        """Show or hide the threshold numeric and agg controls when enabled."""
        self.dspin_threshold_value.setVisible(checked)
        self.combo_threshold_agg.setVisible(checked)
        if hasattr(self, "_lbl_threshold_value") and self._lbl_threshold_value is not None:
            self._lbl_threshold_value.setVisible(checked)
        if hasattr(self, "_lbl_threshold_agg") and self._lbl_threshold_agg is not None:
            self._lbl_threshold_agg.setVisible(checked)

    def get_parameters(self):
        """Gathers all settings from the UI widgets into a dictionary."""
        return {
            "measurement_mode": self.combo_measurement.currentText(),
            "quality_mode": self.combo_quality.currentText(),
            "agg_method": self.combo_agg.currentText(),
            "uniformity_radius": self.dspin_uniformity_radius.value(),
            "strategy": self.combo_strategy.currentText(),
            "candidate_count": self.spin_candidate_count.value(),
            "min_distance": self.dspin_min_distance.value(),
            "quality_percentile": self.dspin_quality_percentile.value(),
            "strain_threshold_enabled": self.chk_threshold_enable.isChecked(),
            "strain_threshold_value_microstrain": self.dspin_threshold_value.value(),
            "strain_threshold_agg": self.combo_threshold_agg.currentText(),
            "gradient_mode": self.combo_gradient_mode.currentText(),
            "roi_center": np.array([
                self.dspin_roi_x.value(),
                self.dspin_roi_y.value(),
                self.dspin_roi_z.value()
            ]),
            "roi_radius": self.dspin_roi_radius.value()
        }

    def set_file_label(self, text):
        """Public method to allow MainWindow to update the file label."""
        self.lbl_file.setText(text)

    def set_button_state_running(self):
        """Sets the update button to a 'running' state."""
        self.btn_update.setText("Running...")
        self.btn_update.setEnabled(False)

    def set_button_state_ready(self):
        """Sets the update button to a normal, ready state."""
        self.btn_update.setText("Run Analysis")
        self.btn_update.setEnabled(True)

    def set_button_state_kmeans_continue(self):
        """Sets the update button to the 'continue' state for K-Means."""
        self.btn_update.setText("Continue with K-Means")
        self.btn_update.setEnabled(True)


class VisualizationPanel(QWidget):
    """
    A widget containing the PyVista plot and its associated graphical controls.
    This is part of the "View" in the MVC pattern. It emits a signal when
    graphical settings are changed, allowing the Controller to refresh the view.
    """
    visualization_settings_changed = pyqtSignal()
    contour_selection_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_widgets()
        self._setup_layout()
        self._apply_tooltips()
        self._connect_signals()

    def _setup_widgets(self):
        """Creates all the control widgets for the visualization."""
        group_box_style = self.parent().styleSheet() if self.parent() else ""

        # --- Graphical and Legend Controls ---
        self.graphical_group = QGroupBox("Graphical Controls")
        self.graphical_group.setStyleSheet(group_box_style)
        graphical_layout = QHBoxLayout(self.graphical_group)
        self.dspin_cloud_point_size = QDoubleSpinBox()
        self.dspin_cloud_point_size.setRange(1.0, 100.0)
        self.dspin_cloud_point_size.setValue(10.0)
        self.dspin_candidate_point_size = QDoubleSpinBox()
        self.dspin_candidate_point_size.setRange(1.0, 50.0)
        self.dspin_candidate_point_size.setValue(20.0)
        self.spin_label_font_size = QSpinBox()
        self.spin_label_font_size.setRange(6, 24)
        self.spin_label_font_size.setValue(DEFAULT_ANNOTATION_FONT_SIZE)
        graphical_layout.addWidget(QLabel("Cloud Size:"))
        graphical_layout.addWidget(self.dspin_cloud_point_size)
        graphical_layout.addWidget(QLabel("Candidate Size:"))
        graphical_layout.addWidget(self.dspin_candidate_point_size)
        graphical_layout.addWidget(QLabel("Annotation Size:"))
        graphical_layout.addWidget(self.spin_label_font_size)
        graphical_layout.addStretch(1)

        self.contour_group = QGroupBox("Contour Controls")
        self.contour_group.setStyleSheet(group_box_style)
        contour_layout = QHBoxLayout(self.contour_group)
        self.edit_contour_sets = QLineEdit("all")
        self.edit_contour_sets.setEnabled(False)
        self.combo_contour_aggregation = QComboBox()
        self.combo_contour_aggregation.addItems(["Max", "Average"])
        self.combo_contour_aggregation.setEnabled(False)
        self.lbl_contour_sets = QLabel("No result sets loaded")
        contour_layout.addWidget(QLabel("Sets/time points:"))
        contour_layout.addWidget(self.edit_contour_sets)
        contour_layout.addWidget(QLabel("Aggregation:"))
        contour_layout.addWidget(self.combo_contour_aggregation)
        contour_layout.addWidget(self.lbl_contour_sets)
        contour_layout.addStretch(1)

        self.legend_group = QGroupBox("Legend Controls")
        self.legend_group.setStyleSheet(group_box_style)
        legend_layout = QHBoxLayout(self.legend_group)
        self.dspin_above_limit = QDoubleSpinBox()
        self.dspin_above_limit.setRange(-1e9, 1e9)
        self.dspin_above_limit.setValue(1.0)
        self.dspin_above_limit.setDecimals(4)
        self.dspin_below_limit = QDoubleSpinBox()
        self.dspin_below_limit.setRange(-1e9, 1e9)
        self.dspin_below_limit.setValue(0.0)
        self.dspin_below_limit.setDecimals(4)
        self.combo_above_color = QComboBox()
        self.combo_above_color.addItems(["Purple", "White"])
        self.combo_below_color = QComboBox()
        self.combo_below_color.addItems(["Gray", "White"])
        self.spin_legend_bands = QSpinBox()
        self.spin_legend_bands.setRange(MIN_BANDS, MAX_BANDS)
        self.spin_legend_bands.setValue(DEFAULT_BANDS)
        legend_layout.addWidget(QLabel("Upper Limit:"))
        legend_layout.addWidget(self.dspin_above_limit)
        legend_layout.addWidget(QLabel("Lower Limit:"))
        legend_layout.addWidget(self.dspin_below_limit)
        legend_layout.addWidget(QLabel("Above Color:"))
        legend_layout.addWidget(self.combo_above_color)
        legend_layout.addWidget(QLabel("Below Color:"))
        legend_layout.addWidget(self.combo_below_color)
        legend_layout.addWidget(QLabel("Bands:"))
        legend_layout.addWidget(self.spin_legend_bands)
        legend_layout.addStretch(1)

        self.surface_group = QGroupBox("Surface Placement")
        self.surface_group.setStyleSheet(group_box_style)
        surface_layout = QHBoxLayout(self.surface_group)
        self.chk_show_surface_edges = QCheckBox("Mesh edges")
        self.chk_show_surface_edges.setChecked(True)
        self.dspin_surface_mesh_opacity = QDoubleSpinBox()
        self.dspin_surface_mesh_opacity.setRange(0.0, 1.0)
        self.dspin_surface_mesh_opacity.setDecimals(2)
        self.dspin_surface_mesh_opacity.setSingleStep(0.05)
        self.dspin_surface_mesh_opacity.setValue(1.0)
        self.chk_show_surface_normals = QCheckBox("Normals")
        self.chk_show_surface_normals.setChecked(True)
        self.chk_show_gage_axes = QCheckBox("Gage axes")
        self.chk_show_gage_axes.setChecked(True)
        self.chk_override_gage_direction = QCheckBox("Override direction")
        self.btn_clear_gage_overrides = QPushButton("Clear overrides")
        self.btn_export_gage_placements = QPushButton("Export placements")
        surface_layout.addWidget(self.chk_show_surface_edges)
        surface_layout.addWidget(QLabel("Surface Opacity:"))
        surface_layout.addWidget(self.dspin_surface_mesh_opacity)
        for widget in [
            self.chk_show_surface_normals,
            self.chk_show_gage_axes,
            self.chk_override_gage_direction,
            self.btn_clear_gage_overrides,
            self.btn_export_gage_placements,
        ]:
            surface_layout.addWidget(widget)
        surface_layout.addStretch(1)
        self.set_surface_placement_enabled(False)

        # PyVista Interactor
        self.vtk_widget = QtInteractor(self)
        # Orientation triad bottom-right, matching Mechanical and keeping the
        # left edge free for the header block and legend column.
        try:
            self.vtk_widget.add_axes(viewport=(0.86, 0.0, 1.0, 0.16))
        except Exception:
            self.vtk_widget.show_axes()


    def _setup_layout(self):
        """Lays out all the widgets in this panel."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(self.graphical_group)
        layout.addWidget(self.contour_group)
        layout.addWidget(self.legend_group)
        layout.addWidget(self.surface_group)
        layout.addWidget(self.vtk_widget.interactor)

    def _apply_tooltips(self):
        """Applies all tooltips to the visualization control widgets."""
        self.dspin_cloud_point_size.setToolTip(tips.CLOUD_POINT_SIZE)
        self.dspin_candidate_point_size.setToolTip(tips.CANDIDATE_POINT_SIZE)
        self.spin_label_font_size.setToolTip(tips.LABEL_FONT_SIZE)
        self.contour_group.setToolTip(tips.CONTOUR_SELECTION)
        self.edit_contour_sets.setToolTip(tips.CONTOUR_SELECTION)
        self.combo_contour_aggregation.setToolTip(tips.CONTOUR_SELECTION)
        self.legend_group.setToolTip(tips.LEGEND_CONTROLS)
        self.spin_legend_bands.setToolTip(tips.LEGEND_BAND_COUNT)
        self.chk_show_surface_edges.setToolTip(tips.SHOW_SURFACE_EDGES)
        self.dspin_surface_mesh_opacity.setToolTip(tips.SURFACE_OPACITY)
        self.chk_show_surface_normals.setToolTip(tips.SHOW_SURFACE_NORMALS)
        self.chk_show_gage_axes.setToolTip(tips.SHOW_GAGE_AXES)
        self.chk_override_gage_direction.setToolTip(tips.OVERRIDE_GAGE_DIRECTION)
        self.btn_clear_gage_overrides.setToolTip(tips.CLEAR_GAGE_OVERRIDES)
        self.btn_export_gage_placements.setToolTip(tips.EXPORT_GAGE_PLACEMENTS)

    def _connect_signals(self):
        """Connects widget signals to this panel's output signal."""
        for widget in [self.dspin_cloud_point_size, self.dspin_candidate_point_size,
                       self.spin_label_font_size, self.dspin_above_limit, self.dspin_below_limit,
                       self.spin_legend_bands,
                       self.dspin_surface_mesh_opacity, self.combo_above_color, self.combo_below_color,
                       self.chk_show_surface_edges, self.chk_show_surface_normals,
                       self.chk_show_gage_axes]:
            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.valueChanged.connect(self.visualization_settings_changed.emit)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self.visualization_settings_changed.emit)
            else:
                widget.currentIndexChanged.connect(self.visualization_settings_changed.emit)
        self.edit_contour_sets.editingFinished.connect(
            self.contour_selection_changed.emit
        )
        self.combo_contour_aggregation.currentIndexChanged.connect(
            self.contour_selection_changed.emit
        )

    def get_settings(self):
        """Gathers all visualization settings into a dictionary."""
        return {
            'cloud_point_size': self.dspin_cloud_point_size.value(),
            'candidate_point_size': self.dspin_candidate_point_size.value(),
            'label_font_size': self.spin_label_font_size.value(),
            'n_bands': self.spin_legend_bands.value(),
            'clim_min': self.dspin_below_limit.value(),
            'clim_max': self.dspin_above_limit.value(),
            'below_color': self.combo_below_color.currentText().lower(),
            'above_color': self.combo_above_color.currentText().lower(),
            'show_surface_edges': self.chk_show_surface_edges.isChecked(),
            'surface_mesh_opacity': self.dspin_surface_mesh_opacity.value(),
            'show_surface_normals': self.chk_show_surface_normals.isChecked(),
            'show_gage_axes': self.chk_show_gage_axes.isChecked(),
        }

    def set_surface_placement_enabled(self, enabled):
        for widget in [
            self.chk_show_surface_edges,
            self.dspin_surface_mesh_opacity,
            self.chk_show_surface_normals,
            self.chk_show_gage_axes,
            self.chk_override_gage_direction,
            self.btn_clear_gage_overrides,
            self.btn_export_gage_placements,
        ]:
            widget.setEnabled(bool(enabled))

    def configure_contour_sets(self, entries, default_aggregation="Max", reset=False):
        """Configure loaded ``(set_id, label)`` entries for contour selection."""
        entries = list(entries or [])
        self._contour_entries = entries
        enabled = bool(entries)
        self.edit_contour_sets.setEnabled(enabled)
        self.combo_contour_aggregation.setEnabled(enabled)
        if reset:
            self.edit_contour_sets.blockSignals(True)
            self.combo_contour_aggregation.blockSignals(True)
            self.edit_contour_sets.setText("all")
            self.combo_contour_aggregation.setCurrentText(str(default_aggregation))
            self.edit_contour_sets.blockSignals(False)
            self.combo_contour_aggregation.blockSignals(False)
        summary = "Loaded: " + ", ".join(str(set_id) for set_id, _ in entries) if entries else "No result sets loaded"
        details = "\n".join(label for _, label in entries)
        self.lbl_contour_sets.setText(summary)
        self.lbl_contour_sets.setToolTip(details)

    def get_contour_selection(self):
        return (
            self.edit_contour_sets.text().strip(),
            self.combo_contour_aggregation.currentText(),
            list(getattr(self, "_contour_entries", [])),
        )

    def set_legend_band_count(self, count):
        """Set the contour band count; the valueChanged signal redraws the view."""
        self.spin_legend_bands.setValue(int(count))

    def set_legend_limits(self, min_val, max_val):
        """Sets the values for the legend limit spinboxes."""
        # Block signals to prevent an unnecessary refresh cycle
        self.dspin_below_limit.blockSignals(True)
        self.dspin_above_limit.blockSignals(True)

        self.dspin_below_limit.setValue(min_val)
        self.dspin_above_limit.setValue(max_val)

        self.dspin_below_limit.blockSignals(False)
        self.dspin_above_limit.blockSignals(False)
