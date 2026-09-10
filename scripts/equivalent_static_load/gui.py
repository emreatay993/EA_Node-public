"""PyQt6 GUI — step-rail wizard over the ESL engine.

House patterns: QThread workers with ``log_message/completed/failed`` signals
(mcf_dpf_section_resultants), Fusion + engineering palette + QSS styling
(Sensor_Data_Comparison_Tool), config Load/Save as JSON. The GUI always
materializes its settings as ``gui_config.json`` inside the output folder
before running, so every run is reproducible from a hashed config file.
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from PyQt6 import QtCore, QtGui, QtWidgets

from scripts.equivalent_static_load import __version__
from scripts.equivalent_static_load import tooltips as tt
from scripts.equivalent_static_load.config import load_config
from scripts.equivalent_static_load.style import application_stylesheet, engineering_palette

STEPS = [
    ("1  Inputs", "MSUP results, unit fields, load history"),
    ("2  Channels", "Rig actuator channels"),
    ("3  Region && Mapping", "Tolerances, weighting, acceptance"),
    ("4  Instants", "Critical time selection"),
    ("5  Derive", "Run the ESL solve"),
    ("6  Results", "Loads, metrics, hotspots"),
    ("7  Verify", "Combined-solve comparison (C1)"),
]

CHANNEL_COLUMNS = [
    "name", "case_label", "unit_load", "point_x", "point_y", "point_z",
    "dir_x", "dir_y", "dir_z", "lower_bound", "upper_bound",
    "interface_channel", "apdl_node", "gang", "gang_ratio", "notes",
]


class WorkerThread(QtCore.QThread):
    """Runs one engine callable off the UI thread (house pattern)."""

    log_message = QtCore.pyqtSignal(str)
    completed = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, fn: Callable[[Callable[[str], None]], Any], parent=None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:  # pragma: no cover - thread body
        try:
            result = self._fn(self.log_message.emit)
        except Exception:
            self.failed.emit(traceback.format_exc())
            return
        self.completed.emit(result)


class FileRow(QtWidgets.QWidget):
    """Line edit + Browse button (open file / save file / pick directory).

    In "open" mode the line edit turns red while its (non-empty) path does not
    exist on disk — missing files are visible immediately, not at run time.
    """

    def __init__(self, mode: str = "open", name_filter: str = "All files (*)", parent=None) -> None:
        super().__init__(parent)
        self._mode = mode
        self._filter = name_filter
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QtWidgets.QLineEdit()
        button = QtWidgets.QPushButton("Browse…")
        button.clicked.connect(self._browse)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)
        if mode == "open":
            self.edit.textChanged.connect(self._refresh_missing_hint)

    def _refresh_missing_hint(self) -> None:
        text = self.edit.text().strip()
        missing = bool(text) and not Path(text).is_file()
        if self.edit.property("missingPath") == missing:
            return
        self.edit.setProperty("missingPath", missing)
        style = self.edit.style()
        style.unpolish(self.edit)
        style.polish(self.edit)

    def is_missing(self) -> bool:
        return bool(self.edit.property("missingPath"))

    def _browse(self) -> None:
        start = self.edit.text() or str(Path.home())
        if self._mode == "dir":
            path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select folder", start)
        elif self._mode == "save":
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Select file", start, self._filter)
        else:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select file", start, self._filter)
        if path:
            self.edit.setText(path)

    def path(self) -> str:
        return self.edit.text().strip()

    def set_path(self, value: str) -> None:
        self.edit.setText(value or "")


def _panel(title: str) -> tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout]:
    frame = QtWidgets.QFrame()
    frame.setObjectName("Panel")
    layout = QtWidgets.QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)
    label = QtWidgets.QLabel(title)
    label.setObjectName("SectionTitle")
    layout.addWidget(label)
    return frame, layout


def _dspin(minimum: float, maximum: float, value: float, decimals: int = 4, step: float = 0.01) -> QtWidgets.QDoubleSpinBox:
    box = QtWidgets.QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setValue(value)
    return box


def _form_row(
    form: QtWidgets.QFormLayout,
    label_text: str,
    field: QtWidgets.QWidget | QtWidgets.QLayout,
    tooltip: str,
) -> None:
    """Add a form row with the SAME rich tooltip on the label and the field.

    Users hover labels as often as fields; unexplained labels are exactly the
    ambiguity this GUI must not have.
    """
    label = QtWidgets.QLabel(label_text)
    label.setToolTip(tooltip)
    if isinstance(field, QtWidgets.QWidget):
        field.setToolTip(tooltip)
        if isinstance(field, FileRow):
            field.edit.setToolTip(tooltip)
    form.addRow(label, field)


def _set_header_tips(table: QtWidgets.QTableWidget, tips_by_label: dict[str, str]) -> None:
    """Attach rich tooltips to table column headers."""
    for col in range(table.columnCount()):
        item = table.horizontalHeaderItem(col)
        if item is not None and item.text() in tips_by_label:
            item.setToolTip(tips_by_label[item.text()])


def _friendly_error(trace: str) -> str:
    """Human-facing message from a worker traceback.

    Strips the ``package.module.SomeError:`` prefix off the final line (users
    should see 'Modal stress CSV not found: …', not the exception path); the
    full traceback is always in the log.
    """
    last = trace.strip().splitlines()[-1] if trace.strip() else "unknown error"
    match = re.match(r"^[\w\.]+(?:Error|Exception|Warning):\s*(.+)$", last)
    message = match.group(1) if match else last
    if "not found" in message:
        message += (
            "\n\nCheck the red-highlighted file fields. For a runnable demo "
            "dataset use the Load Example button."
        )
    return message + "\n\n(Full traceback is in the log panel.)"


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Equivalent Static Load — blade-out secondary ESL v{__version__}")
        self.resize(1480, 940)
        self._worker: WorkerThread | None = None
        self._derive_result = None  # workflow.DeriveRunResult
        self._config_base: Path | None = None

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

        root.addLayout(self._build_header())

        body = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.rail = QtWidgets.QListWidget()
        self.rail.setObjectName("StepRail")
        self.rail.setFixedWidth(240)
        self.rail.setToolTip(tt.STEP_RAIL)
        for (title, _hint), step_tip in zip(STEPS, tt.STEP_TIPS):
            item = QtWidgets.QListWidgetItem(title.replace("&&", "&"))
            item.setToolTip(step_tip)
            self.rail.addItem(item)
        self.pages = QtWidgets.QStackedWidget()
        for builder in (
            self._build_inputs_page, self._build_channels_page, self._build_region_page,
            self._build_instants_page, self._build_derive_page, self._build_results_page,
            self._build_verify_page,
        ):
            page = QtWidgets.QWidget()
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            layout = QtWidgets.QVBoxLayout(page)
            layout.setContentsMargins(12, 8, 12, 8)
            layout.setSpacing(10)
            builder(layout)
            layout.addStretch(1)
            scroll.setWidget(page)
            self.pages.addWidget(scroll)
        self.rail.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.rail.setCurrentRow(0)
        body.addWidget(self.rail)
        body.addWidget(self.pages)
        body.setStretchFactor(1, 1)
        root.addWidget(body, 1)

        root.addLayout(self._build_nav_row())
        root.addWidget(self._build_log_panel())

    # ------------------------------------------------------------- header/nav
    def _build_header(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Equivalent Static Load Derivation")
        title.setObjectName("TitleLabel")
        row.addWidget(title)
        row.addStretch(1)
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setToolTip(tt.STATUS)
        row.addWidget(self.status_label)
        example_btn = QtWidgets.QPushButton("Load Example")
        example_btn.setToolTip(tt.LOAD_EXAMPLE)
        example_btn.clicked.connect(self._load_example_clicked)
        load_btn = QtWidgets.QPushButton("Load Config…")
        load_btn.setToolTip(tt.LOAD_CONFIG)
        load_btn.clicked.connect(self._load_config_clicked)
        save_btn = QtWidgets.QPushButton("Save Config…")
        save_btn.setToolTip(tt.SAVE_CONFIG)
        save_btn.clicked.connect(self._save_config_clicked)
        row.addWidget(example_btn)
        row.addWidget(load_btn)
        row.addWidget(save_btn)
        return row

    def _build_nav_row(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setToolTip(tt.PROGRESS)
        row.addWidget(self.progress, 1)
        back = QtWidgets.QPushButton("◀ Back")
        back.setToolTip(tt.BACK)
        back.clicked.connect(lambda: self.rail.setCurrentRow(max(0, self.rail.currentRow() - 1)))
        nxt = QtWidgets.QPushButton("Next ▶")
        nxt.setToolTip(tt.NEXT)
        nxt.clicked.connect(
            lambda: self.rail.setCurrentRow(min(len(STEPS) - 1, self.rail.currentRow() + 1))
        )
        row.addWidget(back)
        row.addWidget(nxt)
        return row

    def _build_log_panel(self) -> QtWidgets.QWidget:
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setObjectName("LogView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(20000)
        self.log_view.setFixedHeight(150)
        self.log_view.setToolTip(tt.LOG)
        return self.log_view

    def _log(self, message: str) -> None:
        self.log_view.appendPlainText(message)
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ------------------------------------------------------------------ pages
    def _build_inputs_page(self, layout: QtWidgets.QVBoxLayout) -> None:
        panel, box = _panel("Run identification")
        form = QtWidgets.QFormLayout()
        self.title_edit = QtWidgets.QLineEdit("Blade-out secondary ESL")
        _form_row(form, "Title", self.title_edit, tt.TITLE)
        units_row = QtWidgets.QHBoxLayout()
        self.unit_force = QtWidgets.QLineEdit("N")
        self.unit_moment = QtWidgets.QLineEdit("N.mm")
        self.unit_stress = QtWidgets.QLineEdit("MPa")
        self.unit_length = QtWidgets.QLineEdit("mm")
        for label, widget in (
            ("force", self.unit_force), ("moment", self.unit_moment),
            ("stress", self.unit_stress), ("length", self.unit_length),
        ):
            unit_label = QtWidgets.QLabel(label)
            unit_label.setToolTip(tt.UNITS)
            widget.setToolTip(tt.UNITS)
            units_row.addWidget(unit_label)
            units_row.addWidget(widget)
        _form_row(form, "Units (assumed consistent)", units_row, tt.UNITS)
        box.addLayout(form)
        layout.addWidget(panel)

        panel, box = _panel("MSUP transient (same modal basis as the MARS run)")
        form = QtWidgets.QFormLayout()
        self.modal_stress_row = FileRow("open", "CSV (*.csv)")
        self.mcf_row = FileRow("open", "Modal coordinates (*.mcf *.pch);;All files (*)")
        self.modal_forces_row = FileRow("open", "CSV (*.csv)")
        self.steady_row = FileRow("open", "CSV/TXT (*.csv *.txt);;All files (*)")
        self.include_bias_cb = QtWidgets.QCheckBox(
            "Include steady bias in the target (keep OFF when the rig applies pressure physically)"
        )
        self.include_bias_cb.setToolTip(tt.INCLUDE_BIAS)
        _form_row(form, "Modal stress CSV *", self.modal_stress_row, tt.MODAL_STRESS)
        _form_row(form, "Modal coordinates (.mcf/.pch) *", self.mcf_row, tt.MCF)
        _form_row(form, "Modal forces CSV (Route A)", self.modal_forces_row, tt.MODAL_FORCES)
        _form_row(form, "Steady field", self.steady_row, tt.STEADY)
        form.addRow("", self.include_bias_cb)
        box.addLayout(form)
        layout.addWidget(panel)

        panel, box = _panel("Virtual rig model — unit-load fields")
        form = QtWidgets.QFormLayout()
        self.unit_layout_combo = QtWidgets.QComboBox()
        self.unit_layout_combo.addItems(["wide", "rst"])
        self.unit_csv_row = FileRow("open", "CSV (*.csv)")
        self.unit_rst_row = FileRow("open", "Result file (*.rst)")
        _form_row(form, "Layout", self.unit_layout_combo, tt.UNIT_LAYOUT)
        _form_row(form, "Unit fields CSV (wide)", self.unit_csv_row, tt.UNIT_CSV)
        _form_row(form, "Unit fields .rst (needs DPF)", self.unit_rst_row, tt.UNIT_RST)
        box.addLayout(form)
        layout.addWidget(panel)

        panel, box = _panel("Optional inputs")
        form = QtWidgets.QFormLayout()
        self.history_row = FileRow("open", "CSV (*.csv)")
        self.mars_max_row = FileRow("open", "CSV (*.csv)")
        self.mars_time_row = FileRow("open", "CSV (*.csv)")
        _form_row(form, "Interface load history (Tier-1 pattern)", self.history_row, tt.HISTORY)
        _form_row(form, "MARS max_von_mises.csv", self.mars_max_row, tt.MARS_MAX)
        _form_row(form, "MARS time_of_max_von_mises.csv", self.mars_time_row, tt.MARS_TIME)
        box.addLayout(form)
        layout.addWidget(panel)

    def _build_channels_page(self, layout: QtWidgets.QVBoxLayout) -> None:
        panel, box = _panel("Rig load channels (one static unit solve per channel)")
        hint = QtWidgets.QLabel(
            "bounds: push-only actuator = 0 / capacity; leave blank for ±∞. "
            "direction must be a unit vector in the global CS. "
            "case_label selects the unit-field columns (wide CSV) or result set (.rst)."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        box.addWidget(hint)
        self.channel_table = QtWidgets.QTableWidget(0, len(CHANNEL_COLUMNS))
        self.channel_table.setHorizontalHeaderLabels(CHANNEL_COLUMNS)
        self.channel_table.horizontalHeader().setStretchLastSection(True)
        self.channel_table.setAlternatingRowColors(True)
        self.channel_table.setMinimumHeight(320)
        self.channel_table.setToolTip(tt.CHANNELS_TABLE)
        _set_header_tips(self.channel_table, tt.CHANNEL_COLUMN_TIPS)
        box.addWidget(self.channel_table)
        buttons = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("Add channel")
        add.setToolTip(tt.ADD_CHANNEL)
        remove = QtWidgets.QPushButton("Remove selected")
        remove.setToolTip(tt.REMOVE_CHANNEL)
        add.clicked.connect(lambda: self._add_channel_row())
        remove.clicked.connect(self._remove_channel_rows)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        box.addLayout(buttons)
        layout.addWidget(panel)

    def _add_channel_row(self, values: dict[str, Any] | None = None) -> None:
        row = self.channel_table.rowCount()
        self.channel_table.insertRow(row)
        defaults = {
            "name": f"P{row + 1}", "case_label": f"Case{row + 1}", "unit_load": "1000",
            "gang_ratio": "1.0",
        }
        if values:
            defaults.update({k: "" if v is None else str(v) for k, v in values.items()})
        for col, key in enumerate(CHANNEL_COLUMNS):
            self.channel_table.setItem(row, col, QtWidgets.QTableWidgetItem(defaults.get(key, "")))

    def _remove_channel_rows(self) -> None:
        for row in sorted({i.row() for i in self.channel_table.selectedIndexes()}, reverse=True):
            self.channel_table.removeRow(row)

    def _build_region_page(self, layout: QtWidgets.QVBoxLayout) -> None:
        panel, box = _panel("Mesh mapping (MSUP ↔ rig model)")
        form = QtWidgets.QFormLayout()
        self.coord_tol = _dspin(0.0, 1e6, 0.1)
        self.kdtree_dist = _dspin(0.0, 1e6, 1.0)
        self.min_id_frac = _dspin(0.0, 1.0, 0.9, decimals=2, step=0.05)
        _form_row(form, "Coordinate tolerance (ID join)", self.coord_tol, tt.COORD_TOL)
        _form_row(form, "KD-tree max distance (fallback)", self.kdtree_dist, tt.KDTREE_DIST)
        _form_row(form, "Min ID-match fraction", self.min_id_frac, tt.MIN_ID_FRAC)
        box.addLayout(form)
        check_row = QtWidgets.QHBoxLayout()
        self.check_button = QtWidgets.QPushButton("Run pre-flight check")
        self.check_button.setToolTip(tt.CHECK_BUTTON)
        self.check_button.clicked.connect(self._check_clicked)
        self.mapping_label = QtWidgets.QLabel("Mapping not checked yet")
        self.mapping_label.setObjectName("MutedLabel")
        self.mapping_label.setToolTip(tt.MAPPING_LABEL)
        check_row.addWidget(self.check_button)
        check_row.addWidget(self.mapping_label, 1)
        box.addLayout(check_row)
        layout.addWidget(panel)

        panel, box = _panel("Evaluation region & weighting")
        form = QtWidgets.QFormLayout()
        self.region_mode = QtWidgets.QComboBox()
        self.region_mode.addItems(["top_vm_percent", "node_list_csv", "bbox", "all"])
        self.region_value = _dspin(0.01, 100.0, 5.0, decimals=2, step=1.0)
        self.region_nodes_row = FileRow("open", "CSV (*.csv)")
        self.bbox_edit = QtWidgets.QLineEdit()
        self.bbox_edit.setPlaceholderText("xmin, ymin, zmin, xmax, ymax, zmax")
        self.weighting_combo = QtWidgets.QComboBox()
        self.weighting_combo.addItems(["vm", "uniform"])
        self.vm_exponent = _dspin(0.0, 10.0, 1.0, decimals=2, step=0.5)
        self.tikhonov = _dspin(0.0, 1e3, 0.0, decimals=6, step=0.001)
        _form_row(form, "Region mode", self.region_mode, tt.REGION_MODE)
        _form_row(form, "Top-VM percent", self.region_value, tt.REGION_VALUE)
        _form_row(form, "Region node list CSV", self.region_nodes_row, tt.REGION_NODES)
        _form_row(form, "Bounding box", self.bbox_edit, tt.BBOX)
        _form_row(form, "Weighting", self.weighting_combo, tt.WEIGHTING)
        _form_row(form, "VM weight exponent", self.vm_exponent, tt.VM_EXP)
        _form_row(form, "Tikhonov alpha (0 = off)", self.tikhonov, tt.TIKHONOV)
        box.addLayout(form)
        layout.addWidget(panel)

        panel, box = _panel("Acceptance & RT scaling")
        form = QtWidgets.QFormLayout()
        self.under_test_tol = _dspin(0.0, 1.0, 0.05, decimals=3, step=0.01)
        self.vm_floor = _dspin(0.0, 1.0, 0.10, decimals=3, step=0.01)
        self.min_peak_ratio = _dspin(0.0, 10.0, 1.0, decimals=3, step=0.01)
        self.rt_factor = _dspin(0.0, 100.0, 1.0, decimals=4, step=0.01)
        self.rt_note = QtWidgets.QLineEdit()
        self.rt_note.setPlaceholderText("what the factor scales + property-ratio basis (traceability rule)")
        _form_row(form, "Under-test tolerance", self.under_test_tol, tt.UNDER_TEST_TOL)
        _form_row(form, "VM floor fraction", self.vm_floor, tt.VM_FLOOR)
        _form_row(form, "Min peak ratio", self.min_peak_ratio, tt.MIN_PEAK_RATIO)
        _form_row(form, "RT→operating factor (reported table only)", self.rt_factor, tt.RT_FACTOR)
        _form_row(form, "Scaling basis note", self.rt_note, tt.RT_NOTE)
        box.addLayout(form)
        layout.addWidget(panel)

    def _build_instants_page(self, layout: QtWidgets.QVBoxLayout) -> None:
        panel, box = _panel("Critical instants — two rig blade-out cases = two instants of the same event")
        panel.setToolTip(tt.INSTANTS_PANEL_HINT)
        form = QtWidgets.QFormLayout()
        self.instants_mode = QtWidgets.QComboBox()
        self.instants_mode.addItems(["auto", "explicit"])
        self.explicit_times = QtWidgets.QLineEdit()
        self.explicit_times.setPlaceholderText("comma-separated times [s], e.g. 0.0123, 0.0456")
        self.n_suggestions = QtWidgets.QSpinBox()
        self.n_suggestions.setRange(1, 50)
        self.n_suggestions.setValue(4)
        self.quadrature_cb = QtWidgets.QCheckBox("Add quadrature companion t* + 1/(4·f₀)")
        self.quadrature_cb.setChecked(True)
        self.quadrature_cb.setToolTip(tt.QUADRATURE)
        self.hotspot_pct = _dspin(0.01, 100.0, 2.0, decimals=2, step=0.5)
        self.cluster_dt = _dspin(0.0, 10.0, 0.002, decimals=6, step=0.001)
        _form_row(form, "Mode", self.instants_mode, tt.INSTANTS_MODE)
        _form_row(form, "Explicit times", self.explicit_times, tt.EXPLICIT_TIMES)
        _form_row(form, "Suggestions", self.n_suggestions, tt.N_SUGGESTIONS)
        form.addRow("", self.quadrature_cb)
        _form_row(form, "Hotspot top percent (MARS envelope)", self.hotspot_pct, tt.HOTSPOT_PCT)
        _form_row(form, "Cluster window dt [s]", self.cluster_dt, tt.CLUSTER_DT)
        box.addLayout(form)
        self.suggest_button = QtWidgets.QPushButton("Suggest instants from evidence")
        self.suggest_button.setToolTip(tt.SUGGEST_BUTTON)
        self.suggest_button.clicked.connect(self._suggest_clicked)
        box.addWidget(self.suggest_button)
        self.instants_table = QtWidgets.QTableWidget(0, 6)
        self.instants_table.setHorizontalHeaderLabels(
            ["use", "time [s]", "reason", "driver node", "VM at driver", "cluster"]
        )
        self.instants_table.horizontalHeader().setStretchLastSection(True)
        self.instants_table.setMinimumHeight(240)
        self.instants_table.setToolTip(tt.INSTANTS_TABLE)
        _set_header_tips(self.instants_table, tt.INSTANTS_HEADER_TIPS)
        box.addWidget(self.instants_table)
        hint = QtWidgets.QLabel(
            "Checked rows become the derive instants (Case 1 = governing peak; pick a second "
            "instant whose driver node sits in a different region — §5 coverage policy)."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        hint.setToolTip(tt.INSTANTS_PANEL_HINT)
        box.addWidget(hint)
        layout.addWidget(panel)

    def _build_derive_page(self, layout: QtWidgets.QVBoxLayout) -> None:
        panel, box = _panel("Derive equivalent static loads")
        form = QtWidgets.QFormLayout()
        self.tier_combo = QtWidgets.QComboBox()
        self.tier_combo.addItems(["both", "1", "2"])
        self.pattern_row = FileRow("open", "CSV (*.csv)")
        self.outdir_row = FileRow("dir")
        _form_row(form, "Tier (1 = pattern-scaled/DLF, 2 = constrained LS)", self.tier_combo, tt.TIER)
        _form_row(form, "Tier-1 pattern CSV (optional, channel,value)", self.pattern_row, tt.PATTERN_CSV)
        _form_row(form, "Output folder", self.outdir_row, tt.OUTDIR)
        box.addLayout(form)
        self.derive_button = QtWidgets.QPushButton("Derive ESL load sets")
        self.derive_button.setObjectName("PrimaryButton")
        self.derive_button.setToolTip(tt.DERIVE_BUTTON)
        self.derive_button.clicked.connect(self._derive_clicked)
        box.addWidget(self.derive_button)
        note = QtWidgets.QLabel(
            "Runs: load → map → reconstruct target at each instant → bounded weighted LS → "
            "metrics → writes run_manifest.json (input SHA-256 traceability), per-case load "
            "tables, residual fields, and APDL verification snippets."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
        box.addWidget(note)
        layout.addWidget(panel)

    def _build_results_page(self, layout: QtWidgets.QVBoxLayout) -> None:
        panel, box = _panel("Results")
        row = QtWidgets.QHBoxLayout()
        self.case_combo = QtWidgets.QComboBox()
        self.case_combo.setToolTip(tt.CASE_COMBO)
        self.result_tier_combo = QtWidgets.QComboBox()
        self.result_tier_combo.setToolTip(tt.RESULT_TIER_COMBO)
        self.case_combo.currentIndexChanged.connect(self._refresh_results_view)
        self.result_tier_combo.currentIndexChanged.connect(self._refresh_results_view)
        open_btn = QtWidgets.QPushButton("Open output folder")
        open_btn.setToolTip(tt.OPEN_FOLDER)
        open_btn.clicked.connect(self._open_output_folder)
        case_label = QtWidgets.QLabel("Case")
        case_label.setToolTip(tt.CASE_COMBO)
        tier_label = QtWidgets.QLabel("Tier")
        tier_label.setToolTip(tt.RESULT_TIER_COMBO)
        row.addWidget(case_label)
        row.addWidget(self.case_combo)
        row.addWidget(tier_label)
        row.addWidget(self.result_tier_combo)
        row.addStretch(1)
        row.addWidget(open_btn)
        box.addLayout(row)
        self.metrics_label = QtWidgets.QLabel("Run a derivation to see results.")
        self.metrics_label.setObjectName("StatusLabel")
        self.metrics_label.setWordWrap(True)
        self.metrics_label.setToolTip(tt.METRICS_LABEL)
        box.addWidget(self.metrics_label)
        tabs = QtWidgets.QTabWidget()
        self.loads_table = QtWidgets.QTableWidget(0, 6)
        self.loads_table.setHorizontalHeaderLabels(
            ["channel", "magnitude", "RT-scaled", "at bound", "pattern value", "unconstrained"]
        )
        self.loads_table.horizontalHeader().setStretchLastSection(True)
        self.loads_table.setToolTip(tt.LOADS_TABLE)
        _set_header_tips(self.loads_table, tt.LOADS_HEADER_TIPS)
        self.hotspots_table = QtWidgets.QTableWidget(0, 6)
        self.hotspots_table.setHorizontalHeaderLabels(
            ["NodeID", "vm_dyn", "vm_esl", "ratio", "signed_vm_dyn", "signed_vm_esl"]
        )
        self.hotspots_table.horizontalHeader().setStretchLastSection(True)
        self.hotspots_table.setToolTip(tt.HOTSPOTS_TABLE)
        _set_header_tips(self.hotspots_table, tt.HOTSPOTS_HEADER_TIPS)
        tabs.addTab(self.loads_table, "Channel loads")
        tabs.addTab(self.hotspots_table, "Hotspots")
        tabs.setMinimumHeight(340)
        box.addWidget(tabs)
        layout.addWidget(panel)

    def _build_verify_page(self, layout: QtWidgets.QVBoxLayout) -> None:
        panel, box = _panel("Verification — combined nonlinear solve vs target (Open Item C1)")
        form = QtWidgets.QFormLayout()
        self.verify_case_combo = QtWidgets.QComboBox()
        self.solved_row = FileRow("open", "Solved field CSV (*.csv)")
        _form_row(form, "Case", self.verify_case_combo, tt.VERIFY_CASE)
        _form_row(form, "Solved field CSV (NodeID + sx..sxz)", self.solved_row, tt.SOLVED_ROW)
        box.addLayout(form)
        self.verify_button = QtWidgets.QPushButton("Verify against target")
        self.verify_button.setObjectName("PrimaryButton")
        self.verify_button.setToolTip(tt.VERIFY_BUTTON)
        self.verify_button.clicked.connect(self._verify_clicked)
        box.addWidget(self.verify_button)
        self.verify_label = QtWidgets.QLabel(
            "Apply the derived loads in the virtual rig model (verify_forces_tier*.inp), run ONE "
            "combined static solve with real contacts and pressure, export the nodal stress field "
            "as CSV, then verify here. λ_corr is written into esl_loads_corrected.csv."
        )
        self.verify_label.setObjectName("MutedLabel")
        self.verify_label.setWordWrap(True)
        box.addWidget(self.verify_label)
        self.verify_result_label = QtWidgets.QLabel("")
        self.verify_result_label.setWordWrap(True)
        box.addWidget(self.verify_result_label)
        layout.addWidget(panel)

    # ------------------------------------------------------------ config I/O
    def collect_raw_config(self) -> dict[str, Any]:
        def opt(path: str) -> str | None:
            return path if path else None

        channels = []
        for row in range(self.channel_table.rowCount()):
            def cell(col_key: str) -> str:
                item = self.channel_table.item(row, CHANNEL_COLUMNS.index(col_key))
                return item.text().strip() if item else ""

            def num(col_key: str) -> float | None:
                text = cell(col_key)
                return float(text) if text else None

            point = [num("point_x"), num("point_y"), num("point_z")]
            direction = [num("dir_x"), num("dir_y"), num("dir_z")]
            channel: dict[str, Any] = {
                "name": cell("name"),
                "case_label": cell("case_label"),
                "unit_load": num("unit_load") or 1.0,
                "point": point if all(v is not None for v in point) else None,
                "direction": direction if all(v is not None for v in direction) else None,
                "bounds": [num("lower_bound"), num("upper_bound")],
                "interface_channel": cell("interface_channel") or None,
                "apdl_node": int(num("apdl_node")) if num("apdl_node") is not None else None,
                "gang": cell("gang") or None,
                "gang_ratio": num("gang_ratio") or 1.0,
                "notes": cell("notes"),
            }
            channels.append(channel)

        bbox_text = self.bbox_edit.text().strip()
        bbox = [float(v) for v in bbox_text.split(",")] if bbox_text else None
        explicit = self.explicit_times.text().strip()
        raw: dict[str, Any] = {
            "schema_version": 1,
            "title": self.title_edit.text().strip(),
            "notes": f"Materialized by the ESL GUI v{__version__}.",
            "units": {
                "force": self.unit_force.text().strip() or "N",
                "moment": self.unit_moment.text().strip() or "N.mm",
                "stress": self.unit_stress.text().strip() or "MPa",
                "length": self.unit_length.text().strip() or "mm",
            },
            "msup": {
                "modal_stress_csv": self.modal_stress_row.path(),
                "modal_coordinates": self.mcf_row.path(),
                "modal_forces_csv": opt(self.modal_forces_row.path()),
                "steady_state_csv": opt(self.steady_row.path()),
                "include_steady_bias": self.include_bias_cb.isChecked(),
            },
            "target": {"mode": "reconstruct"},
            "interface_loads_csv": opt(self.history_row.path()),
            "rig": {
                "unit_fields": {
                    "layout": self.unit_layout_combo.currentText(),
                    "csv": opt(self.unit_csv_row.path()),
                    "rst": opt(self.unit_rst_row.path()),
                },
                "channels": channels,
            },
            "mapping": {
                "coord_tol": self.coord_tol.value(),
                "kdtree_max_dist": self.kdtree_dist.value(),
                "min_id_match_fraction": self.min_id_frac.value(),
            },
            "instants": {
                "mode": self.instants_mode.currentText(),
                "explicit_times": (
                    [float(t) for t in explicit.split(",")] if explicit else None
                ),
                "n_suggestions": self.n_suggestions.value(),
                "quadrature": self.quadrature_cb.isChecked(),
                "hotspot_top_percent": self.hotspot_pct.value(),
                "cluster_dt": self.cluster_dt.value(),
                "mars_envelope": {
                    "max_vm_csv": opt(self.mars_max_row.path()),
                    "time_of_max_vm_csv": opt(self.mars_time_row.path()),
                },
            },
            "solve": {
                "tier": self.tier_combo.currentText(),
                "weighting": self.weighting_combo.currentText(),
                "vm_weight_exponent": self.vm_exponent.value(),
                "region": {
                    "mode": self.region_mode.currentText(),
                    "value": self.region_value.value(),
                    "node_list_csv": opt(self.region_nodes_row.path()),
                    "bbox": bbox,
                },
                "tikhonov_alpha": self.tikhonov.value(),
            },
            "acceptance": {
                "under_test_tol": self.under_test_tol.value(),
                "vm_floor_frac": self.vm_floor.value(),
                "min_peak_ratio": self.min_peak_ratio.value(),
            },
            "scaling": {
                "rt_factor": self.rt_factor.value(),
                "basis_note": self.rt_note.text().strip(),
            },
            "outputs": {
                "directory": self.outdir_row.path() or "esl_out",
                "apdl_snippet": True,
                "top_n_hotspots": 25,
            },
        }
        return raw

    def apply_raw_config(self, raw: dict[str, Any], base: Path) -> None:
        def absolute(value: Any) -> str:
            if not value:
                return ""
            p = Path(str(value))
            return str(p if p.is_absolute() else (base / p).resolve())

        self._config_base = base
        self.title_edit.setText(str(raw.get("title", "")))
        units = raw.get("units", {})
        self.unit_force.setText(str(units.get("force", "N")))
        self.unit_moment.setText(str(units.get("moment", "N.mm")))
        self.unit_stress.setText(str(units.get("stress", "MPa")))
        self.unit_length.setText(str(units.get("length", "mm")))
        msup = raw.get("msup", {})
        self.modal_stress_row.set_path(absolute(msup.get("modal_stress_csv")))
        self.mcf_row.set_path(absolute(msup.get("modal_coordinates")))
        self.modal_forces_row.set_path(absolute(msup.get("modal_forces_csv")))
        self.steady_row.set_path(absolute(msup.get("steady_state_csv")))
        self.include_bias_cb.setChecked(bool(msup.get("include_steady_bias", False)))
        self.history_row.set_path(absolute(raw.get("interface_loads_csv")))
        rig = raw.get("rig", {})
        uf = rig.get("unit_fields", {})
        layout = str(uf.get("layout", "wide"))
        index = self.unit_layout_combo.findText(layout)
        self.unit_layout_combo.setCurrentIndex(max(0, index))
        self.unit_csv_row.set_path(absolute(uf.get("csv")))
        self.unit_rst_row.set_path(absolute(uf.get("rst")))
        self.channel_table.setRowCount(0)
        for channel in rig.get("channels", []):
            bounds = channel.get("bounds") or [None, None]
            point = channel.get("point") or [None, None, None]
            direction = channel.get("direction") or [None, None, None]
            self._add_channel_row(
                {
                    "name": channel.get("name"), "case_label": channel.get("case_label"),
                    "unit_load": channel.get("unit_load", 1000),
                    "point_x": point[0], "point_y": point[1], "point_z": point[2],
                    "dir_x": direction[0], "dir_y": direction[1], "dir_z": direction[2],
                    "lower_bound": bounds[0], "upper_bound": bounds[1],
                    "interface_channel": channel.get("interface_channel"),
                    "apdl_node": channel.get("apdl_node"),
                    "gang": channel.get("gang"), "gang_ratio": channel.get("gang_ratio", 1.0),
                    "notes": channel.get("notes", ""),
                }
            )
        mapping = raw.get("mapping", {})
        self.coord_tol.setValue(float(mapping.get("coord_tol", 0.1)))
        self.kdtree_dist.setValue(float(mapping.get("kdtree_max_dist", 1.0)))
        self.min_id_frac.setValue(float(mapping.get("min_id_match_fraction", 0.9)))
        instants = raw.get("instants", {})
        index = self.instants_mode.findText(str(instants.get("mode", "auto")))
        self.instants_mode.setCurrentIndex(max(0, index))
        explicit = instants.get("explicit_times")
        self.explicit_times.setText(
            ", ".join(str(t) for t in explicit) if explicit else ""
        )
        self.n_suggestions.setValue(int(instants.get("n_suggestions", 4)))
        self.quadrature_cb.setChecked(bool(instants.get("quadrature", True)))
        self.hotspot_pct.setValue(float(instants.get("hotspot_top_percent", 2.0)))
        self.cluster_dt.setValue(float(instants.get("cluster_dt", 0.002)))
        envelope = instants.get("mars_envelope", {}) or {}
        self.mars_max_row.set_path(absolute(envelope.get("max_vm_csv")))
        self.mars_time_row.set_path(absolute(envelope.get("time_of_max_vm_csv")))
        solve = raw.get("solve", {})
        index = self.tier_combo.findText(str(solve.get("tier", "both")))
        self.tier_combo.setCurrentIndex(max(0, index))
        index = self.weighting_combo.findText(str(solve.get("weighting", "vm")))
        self.weighting_combo.setCurrentIndex(max(0, index))
        self.vm_exponent.setValue(float(solve.get("vm_weight_exponent", 1.0)))
        self.tikhonov.setValue(float(solve.get("tikhonov_alpha", 0.0)))
        region = solve.get("region", {}) or {}
        index = self.region_mode.findText(str(region.get("mode", "top_vm_percent")))
        self.region_mode.setCurrentIndex(max(0, index))
        self.region_value.setValue(float(region.get("value", 5.0)))
        self.region_nodes_row.set_path(absolute(region.get("node_list_csv")))
        bbox = region.get("bbox")
        self.bbox_edit.setText(", ".join(str(v) for v in bbox) if bbox else "")
        acceptance = raw.get("acceptance", {})
        self.under_test_tol.setValue(float(acceptance.get("under_test_tol", 0.05)))
        self.vm_floor.setValue(float(acceptance.get("vm_floor_frac", 0.10)))
        self.min_peak_ratio.setValue(float(acceptance.get("min_peak_ratio", 1.0)))
        scaling = raw.get("scaling", {})
        self.rt_factor.setValue(float(scaling.get("rt_factor", 1.0)))
        self.rt_note.setText(str(scaling.get("basis_note", "")))
        outputs = raw.get("outputs", {})
        self.outdir_row.set_path(absolute(outputs.get("directory", "esl_out")))

    def _open_file_rows(self) -> list[tuple[str, FileRow]]:
        """Every open-mode file row, labelled — the missing-path checklist."""
        return [
            ("Modal stress CSV", self.modal_stress_row),
            ("Modal coordinates (.mcf/.pch)", self.mcf_row),
            ("Modal forces CSV", self.modal_forces_row),
            ("Steady field", self.steady_row),
            ("Unit fields CSV", self.unit_csv_row),
            ("Unit fields .rst", self.unit_rst_row),
            ("Interface load history", self.history_row),
            ("MARS max_von_mises.csv", self.mars_max_row),
            ("MARS time_of_max_von_mises.csv", self.mars_time_row),
            ("Region node list CSV", self.region_nodes_row),
            ("Tier-1 pattern CSV", self.pattern_row),
            ("Solved field CSV", self.solved_row),
        ]

    def _missing_inputs(self) -> list[str]:
        return [
            f"{label}:  {row.path()}"
            for label, row in self._open_file_rows()
            if row.path() and row.is_missing()
        ]

    def _example_config_path(self) -> Path:
        return Path(__file__).resolve().parent / "examples" / "mockup_inputs" / "mockup_config.json"

    def _warn_if_missing_inputs(self, source_name: str) -> None:
        missing = self._missing_inputs()
        if not missing:
            return
        for entry in missing:
            self._log(f"MISSING FILE — {entry}")
        hint = ""
        if source_name == "example_config.json":
            hint = (
                "<p><b>example_config.json is a schema template with placeholder "
                "paths</b> — it documents the format but points at files that do "
                "not exist.</p>"
            )
        QtWidgets.QMessageBox.warning(
            self,
            "Config references missing files",
            f"{hint}<p>{len(missing)} referenced input file(s) do not exist "
            "(their fields are highlighted red):</p><p>"
            + "<br>".join(missing)
            + "</p><p>Fix the paths, or use <b>Load Example</b> for the runnable "
            "demo dataset (examples\\mockup_inputs\\mockup_config.json).</p>",
        )

    def _load_config_from(self, path: Path) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.apply_raw_config(raw, path.parent)
        self._log(f"Config loaded: {path}")
        self.status_label.setText(f"Config: {path.name}")
        self._warn_if_missing_inputs(path.name)

    def _load_config_clicked(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load config", str(Path.home()), "JSON (*.json)"
        )
        if not path:
            return
        try:
            self._load_config_from(Path(path))
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Load config failed", str(exc))

    def _load_example_clicked(self) -> None:
        example = self._example_config_path()
        if not example.is_file():
            QtWidgets.QMessageBox.warning(
                self, "Example not found",
                f"Expected the mockup dataset at:\n{example}",
            )
            return
        try:
            self._load_config_from(example)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Load example failed", str(exc))

    def _save_config_clicked(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save config", str(Path.home() / "esl_config.json"), "JSON (*.json)"
        )
        if not path:
            return
        Path(path).write_text(json.dumps(self.collect_raw_config(), indent=2), encoding="utf-8")
        self._log(f"Config saved: {path}")

    def _materialize_config(self) -> Path:
        """Write the GUI state as gui_config.json inside the output folder."""
        raw = self.collect_raw_config()
        out_dir = Path(raw["outputs"]["directory"])
        if not out_dir.is_absolute():
            raise ValueError("Choose an absolute output folder on the Derive page")
        out_dir.mkdir(parents=True, exist_ok=True)
        config_path = out_dir / "gui_config.json"
        config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        return config_path

    # --------------------------------------------------------------- workers
    def _start_worker(self, fn, on_done, busy_text: str) -> None:
        if self._worker is not None and self._worker.isRunning():
            QtWidgets.QMessageBox.information(self, "Busy", "A task is already running.")
            return
        self.status_label.setText(busy_text)
        self.progress.setRange(0, 0)
        for button in (self.derive_button, self.suggest_button, self.check_button, self.verify_button):
            button.setEnabled(False)
        self._worker = WorkerThread(fn, parent=self)
        self._worker.log_message.connect(self._log)
        self._worker.completed.connect(lambda result: self._finish_worker(on_done, result))
        self._worker.failed.connect(self._fail_worker)
        self._worker.start()

    def _finish_worker(self, on_done, result) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        for button in (self.derive_button, self.suggest_button, self.check_button, self.verify_button):
            button.setEnabled(True)
        self.status_label.setText("Ready")
        on_done(result)

    def _fail_worker(self, trace: str) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        for button in (self.derive_button, self.suggest_button, self.check_button, self.verify_button):
            button.setEnabled(True)
        self.status_label.setText("Failed")
        self._log(trace)
        QtWidgets.QMessageBox.critical(self, "Task failed", _friendly_error(trace))

    def _check_clicked(self) -> None:
        try:
            config_path = self._materialize_config()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Config incomplete", str(exc))
            return

        def job(log):
            from scripts.equivalent_static_load.workflow import load_inputs

            cfg = load_config(config_path)
            return load_inputs(cfg, log=log)

        def done(inputs) -> None:
            mapping = inputs.mapping
            self.mapping_label.setText(
                f"Mapping: {mapping.method} — mapped {mapping.n_mapped}, "
                f"unmatched {mapping.n_unmatched}, coord RMS {mapping.coord_rms_error:.4g}, "
                f"max {mapping.coord_max_error:.4g}"
            )
            self._log("Pre-flight check OK")

        self._start_worker(job, done, "Checking inputs…")

    def _suggest_clicked(self) -> None:
        try:
            config_path = self._materialize_config()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Config incomplete", str(exc))
            return

        def job(log):
            from scripts.equivalent_static_load.workflow import choose_instants, load_inputs

            cfg = load_config(config_path)
            inputs = load_inputs(cfg, log=log)
            return choose_instants(cfg, inputs, log=log)

        def done(suggestions) -> None:
            self.instants_table.setRowCount(0)
            for s in suggestions:
                row = self.instants_table.rowCount()
                self.instants_table.insertRow(row)
                use_item = QtWidgets.QTableWidgetItem()
                use_item.setFlags(
                    QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled
                )
                use_item.setCheckState(QtCore.Qt.CheckState.Checked)
                self.instants_table.setItem(row, 0, use_item)
                for col, value in enumerate(
                    (f"{s.time:.6g}", s.reason, str(s.driver_node),
                     f"{s.vm_at_driver:.5g}", str(s.cluster_size)),
                    start=1,
                ):
                    item = QtWidgets.QTableWidgetItem(value)
                    item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
                    self.instants_table.setItem(row, col, item)
            self._log(f"{len(suggestions)} instants suggested")

        self._start_worker(job, done, "Suggesting instants…")

    def _checked_instants(self) -> list[float] | None:
        times: list[float] = []
        for row in range(self.instants_table.rowCount()):
            use = self.instants_table.item(row, 0)
            if use is not None and use.checkState() == QtCore.Qt.CheckState.Checked:
                times.append(float(self.instants_table.item(row, 1).text()))
        return times or None

    def _derive_clicked(self) -> None:
        try:
            config_path = self._materialize_config()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Config incomplete", str(exc))
            return
        override = self._checked_instants()
        pattern = self.pattern_row.path() or None

        def job(log):
            from scripts.equivalent_static_load.workflow import derive_run

            cfg = load_config(config_path)
            return derive_run(
                cfg,
                override_times=override,
                pattern_csv=Path(pattern) if pattern else None,
                log=log,
            )

        def done(result) -> None:
            self._derive_result = result
            self.case_combo.clear()
            self.verify_case_combo.clear()
            for case in result.cases:
                self.case_combo.addItem(case.case_id)
                self.verify_case_combo.addItem(case.case_id)
            for warning in result.warnings:
                self._log(f"WARNING: {warning}")
            self._log(f"Derive complete — outputs in {result.out_dir}")
            self.rail.setCurrentRow(5)
            self._refresh_results_view()

        self._start_worker(job, done, "Deriving ESL…")

    def _refresh_results_view(self) -> None:
        result = self._derive_result
        if result is None or self.case_combo.currentIndex() < 0:
            return
        case = result.cases[self.case_combo.currentIndex()]
        tiers = sorted(case.tiers)
        current_tier = self.result_tier_combo.currentText()
        self.result_tier_combo.blockSignals(True)
        self.result_tier_combo.clear()
        self.result_tier_combo.addItems(tiers)
        if current_tier in tiers:
            self.result_tier_combo.setCurrentText(current_tier)
        self.result_tier_combo.blockSignals(False)
        tier = case.tiers[self.result_tier_combo.currentText() or tiers[0]]
        sol, m = tier.solution, tier.metrics
        lam_text = f"λ (effective DLF) = {sol.lam:.4g} · " if sol.lam is not None else ""
        self.metrics_label.setText(
            f"Case {case.case_id} tier {tier.tier}: {lam_text}"
            f"peak ratio at node {m.critical_node} = {m.peak_ratio_at_critical:.3f} "
            f"(dyn {m.vm_dyn_at_critical:.5g} vs ESL {m.vm_esl_at_critical:.5g}) · "
            f"R² = {m.weighted_r2:.4f} · Pearson(VM) = {m.weighted_pearson_vm:.4f} · "
            f"under-test = {m.n_under_test} · cond = {sol.condition_number:.4g}"
            + (" ⚠️" if sol.diagnostics.get("condition_warning") else "")
        )
        self.loads_table.setRowCount(0)
        rt = self.rt_factor.value()
        for k in range(len(sol.loads)):
            row = self.loads_table.rowCount()
            self.loads_table.insertRow(row)
            name = (
                self.channel_table.item(k, 0).text()
                if k < self.channel_table.rowCount() and self.channel_table.item(k, 0)
                else f"ch{k + 1}"
            )
            pattern_value = (
                f"{tier.pattern.values[k]:.6g}" if tier.pattern is not None else ""
            )
            for col, value in enumerate(
                (
                    name, f"{sol.loads[k]:.6g}", f"{sol.loads[k] * rt:.6g}",
                    "yes" if sol.at_bound[k] else "", pattern_value,
                    f"{sol.unconstrained_loads[k]:.6g}",
                )
            ):
                item = QtWidgets.QTableWidgetItem(value)
                item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
                self.loads_table.setItem(row, col, item)
        self.hotspots_table.setRowCount(0)
        hotspots = m.hotspots.head(25)
        for _, hotspot in hotspots.iterrows():
            row = self.hotspots_table.rowCount()
            self.hotspots_table.insertRow(row)
            for col, key in enumerate(
                ("NodeID", "vm_dyn", "vm_esl", "ratio", "signed_vm_dyn", "signed_vm_esl")
            ):
                value = hotspot.get(key, "")
                text = f"{value:.5g}" if isinstance(value, float) else str(value)
                item = QtWidgets.QTableWidgetItem(text)
                item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
                self.hotspots_table.setItem(row, col, item)

    def _open_output_folder(self) -> None:
        if self._derive_result is None:
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self._derive_result.out_dir)))

    def _verify_clicked(self) -> None:
        if self._derive_result is None:
            QtWidgets.QMessageBox.information(self, "No derivation", "Run a derivation first.")
            return
        solved = self.solved_row.path()
        if not solved:
            QtWidgets.QMessageBox.information(self, "No solved field", "Pick the solved-field CSV.")
            return
        case_id = self.verify_case_combo.currentText()
        out_dir = self._derive_result.out_dir
        config_path = out_dir / "gui_config.json"

        def job(log):
            from scripts.equivalent_static_load.verify import verify_case

            cfg = load_config(config_path)
            return verify_case(cfg, out_dir / f"case_{case_id}", Path(solved), log=log)

        def done(result) -> None:
            verdict = "ACCEPTED ✓" if result.accepted else "NOT ACCEPTED — iterate with λ_corr"
            self.verify_result_label.setText(
                f"<b>{verdict}</b> — peak ratio {result.metrics.peak_ratio_at_critical:.3f}, "
                f"under-test {result.metrics.n_under_test}, λ_corr = {result.lambda_corr:.4g}. "
                f"Corrected table: esl_loads_corrected.csv (re-verify after applying)."
            )
            self._log(f"Verification {verdict}")

        self._start_worker(job, done, "Verifying…")


def run_gui(argv: list[str] | None = None) -> int:
    QtWidgets.QApplication.setAttribute(
        QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
    )
    app = QtWidgets.QApplication(argv or sys.argv)
    app.setApplicationName("Equivalent Static Load")
    app.setStyle("Fusion")
    app.setPalette(engineering_palette())
    app.setStyleSheet(application_stylesheet())
    window = MainWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    if __package__ in (None, ""):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(run_gui())
