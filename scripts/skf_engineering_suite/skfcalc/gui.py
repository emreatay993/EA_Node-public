"""Professional PyQt6 desktop interface for the SKF Engineering Bearing Suite."""

from __future__ import annotations

import copy
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSize,
    QObject,
    QRunnable,
    QSettings,
    Qt,
    QThreadPool,
    pyqtSignal,
)
from PyQt6.QtGui import QAction, QColor, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .batch import BatchRunResult, run_batch_csv, run_numba_dgbb_csv
from .calibration import CalibrationFitResult, fit_calibration_csv
from .constants import CONTAMINATION_PRESETS, available_series
from .io import (
    create_batch_template,
    create_calibration_template,
    load_case,
    save_calibration,
    save_case,
    write_history_csv,
)
from .models import (
    BearingCase,
    BearingFamily,
    BearingQuality,
    LubricantKind,
    LubricationMode,
    ShaftOrientation,
    ThermalModel,
)
from .report import generate_html_report
from .seals import compatible_seal_types
from .solver import solve_case
from .help_text import CONTROL_HELP, FIELD_HELP, methodology_html, tooltip_html
from .theme import T, apply_app_theme, build_stylesheet, configure_matplotlib, generate_icons, style_axes


APP_NAME = "SKF Engineering Bearing Suite"
APP_VERSION = "1.0.0"


def small_caps(text: str) -> str:
    """Upper-case Latin letters only.

    Plain ``str.upper()`` would turn engineering symbols into the wrong
    character - the viscosity ratio κ becomes capital kappa Κ, and µ becomes M.
    """
    return "".join(char.upper() if char.isascii() else char for char in text)


class WorkerSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()


class FunctionWorker(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            value = self.fn()
        except Exception:
            self.signals.error.emit(traceback.format_exc())
        else:
            self.signals.result.emit(value)
        finally:
            self.signals.finished.emit()


class DataFrameModel(QAbstractTableModel):
    def __init__(self, dataframe: pd.DataFrame | None = None):
        super().__init__()
        self.frame = dataframe if dataframe is not None else pd.DataFrame()

    def set_dataframe(self, dataframe: pd.DataFrame) -> None:
        self.beginResetModel()
        self.frame = dataframe.copy()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.frame)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.frame.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        value = self.frame.iat[index.row(), index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            if pd.isna(value):
                return ""
            if isinstance(value, float):
                return f"{value:.6g}"
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole and isinstance(value, (int, float)):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole and "error" in self.frame.columns:
            error = self.frame.iloc[index.row()].get("error", "")
            if isinstance(error, str) and error:
                return QColor(T.danger_soft)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self.frame.columns[section])
        return str(section + 1)


class PlotCanvas(FigureCanvas):
    """Matplotlib canvas themed to match the surrounding card."""

    def __init__(self, polar: bool = False):
        configure_matplotlib()  # rcParams must land before the Figure is built
        self.figure = Figure(figsize=(6.4, 4.0), tight_layout=True)
        self.polar = polar
        self.axes = self.figure.add_subplot(111, projection="polar" if polar else None)
        super().__init__(self.figure)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        style_axes(self.figure, self.axes, self.polar)

    def reset(self) -> Any:
        self.figure.clear()
        self.axes = self.figure.add_subplot(111, projection="polar" if self.polar else None)
        style_axes(self.figure, self.axes, self.polar)
        return self.axes


class MetricCard(QFrame):
    """KPI tile: small-caps title above a large value with its unit inline."""

    def __init__(self, title: str, unit: str = ""):
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 16)
        layout.setSpacing(6)
        title_label = QLabel(small_caps(title))
        title_label.setObjectName("metricTitle")
        title_label.setToolTip(title)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("metricValue")
        self.unit_label = QLabel(unit)
        self.unit_label.setObjectName("metricUnit")
        self.unit_label.setVisible(False)
        self.value_label.setProperty("empty", True)
        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.setSpacing(7)
        value_row.addWidget(self.value_label)
        value_row.addWidget(self.unit_label, 0, Qt.AlignmentFlag.AlignBottom)
        value_row.addStretch()
        layout.addWidget(title_label)
        layout.addLayout(value_row)

    def set_value(self, value: float | str, decimals: int = 2) -> None:
        if isinstance(value, str):
            text = value
        elif value == float("inf"):
            text = "∞"
        else:
            text = f"{value:,.{decimals}f}"
        self.value_label.setText(text)
        # A bold 21 pt em dash reads as a redaction bar, so the empty state is
        # styled down through a dynamic property.
        self.value_label.setProperty("empty", text == "—")
        self.unit_label.setVisible(text != "—")
        self.value_label.style().unpolish(self.value_label)
        self.value_label.style().polish(self.value_label)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.case = BearingCase()
        self.result = None
        self.current_case_path: Path | None = None
        self.batch_result: BatchRunResult | None = None
        self.calibration_result: CalibrationFitResult | None = None
        self.thread_pool = QThreadPool.globalInstance()
        self.settings = QSettings("EngineeringTools", "SKFEngineeringBearingSuite")

        self.setWindowTitle(APP_NAME)
        self.resize(1460, 900)
        self.setMinimumSize(1120, 720)
        self._build_actions()
        self._build_toolbar()
        self._build_central()
        self._build_status_bar()
        self._apply_field_help()
        self._apply_stylesheet()
        self._write_case_to_ui(self.case)
        self._restore_settings()

    # ------------------------------------------------------------------ UI shell
    def _build_actions(self) -> None:
        self.new_action = QAction("New", self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self._new_case)
        self.open_action = QAction("Open", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self._open_case)
        self.save_action = QAction("Save", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._save_case)
        self.save_as_action = QAction("Save As", self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(lambda: self._save_case(save_as=True))
        self.run_action = QAction("Run calculation", self)
        self.run_action.setShortcut(QKeySequence("F5"))
        self.run_action.setToolTip("Solve the coupled friction / thermal / life model  (F5)")
        self.run_action.triggered.connect(self._run_calculation)
        self.report_action = QAction("Export report", self)
        self.report_action.setToolTip("Write a standalone HTML report for the current result")
        self.report_action.triggered.connect(self._export_report)
        self.report_action.setEnabled(False)
        self.about_action = QAction("Methodology / About", self)
        self.about_action.triggered.connect(self._show_about)
        for action, hint in (
            (self.new_action, "Start a new case  (Ctrl+N)"),
            (self.open_action, "Open a saved case  (Ctrl+O)"),
            (self.save_action, "Save the current case  (Ctrl+S)"),
        ):
            action.setToolTip(hint)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addActions([self.new_action, self.open_action, self.save_action, self.save_as_action])
        file_menu.addSeparator()
        file_menu.addAction(self.report_action)
        run_menu = self.menuBar().addMenu("Calculate")
        run_menu.addAction(self.run_action)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.about_action)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.addAction(self.new_action)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        toolbar.addAction(self.run_action)
        toolbar.addAction(self.report_action)
        # Give the primary action filled-accent emphasis. Styling the existing
        # tool button rather than swapping in a QPushButton keeps enable/disable
        # and the F5 shortcut driven by the single QAction.
        run_button = toolbar.widgetForAction(self.run_action)
        if run_button is not None:
            run_button.setObjectName("runButton")
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        method = QLabel("SKF friction + ISO 281 life")
        method.setObjectName("toolbarBadge")
        method.setToolTip(
            "Published SKF friction and ISO 281 rating-life equations.\n"
            "Engineering extensions beyond the published tables are flagged in place."
        )
        toolbar.addWidget(method)
        trailing = QWidget()
        trailing.setFixedWidth(6)
        toolbar.addWidget(trailing)
        self.addToolBar(toolbar)

    def _build_central(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(252)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 22, 16, 18)
        side_layout.setSpacing(0)
        brand = QLabel("BEARING\nENGINEERING")
        brand.setObjectName("brand")
        subbrand = QLabel("CALCULATION WORKSPACE")
        subbrand.setObjectName("subbrand")
        side_layout.addWidget(brand)
        side_layout.addSpacing(5)
        side_layout.addWidget(subbrand)
        side_layout.addSpacing(18)
        divider = QFrame()
        divider.setObjectName("railDivider")
        divider.setFixedHeight(1)
        side_layout.addWidget(divider)
        side_layout.addSpacing(14)

        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setSpacing(2)
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.navigation.setFrameShape(QFrame.Shape.NoFrame)
        # Section headers are non-selectable rows. The page each row targets is
        # carried in UserRole rather than being the row number, so adding or
        # moving a header cannot desynchronise the rail from the page stack.
        rail_entries: list[tuple[str, int | None]] = [
            ("SETUP", None),
            ("01   Bearing", 0),
            ("02   Operating & Oil", 1),
            ("03   Lubrication & Seals", 2),
            ("04   Installation", 3),
            ("05   Thermal Network", 4),
            ("06   Rating Life", 5),
            ("ANALYSIS", None),
            ("07   Results", 6),
            ("08   Batch Map", 7),
            ("09   Calibration", 8),
        ]
        for text, page_index in rail_entries:
            item = QListWidgetItem(text)
            if page_index is None:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setSizeHint(QSize(0, 34))
            else:
                item.setData(Qt.ItemDataRole.UserRole, page_index)
                item.setSizeHint(QSize(0, 40))
            self.navigation.addItem(item)
        side_layout.addWidget(self.navigation, 1)
        version = QLabel(f"v{APP_VERSION}  ·  Engineering prototype")
        version.setObjectName("versionLabel")
        side_layout.addSpacing(10)
        side_layout.addWidget(version)

        self.stack = QStackedWidget()
        self.stack.setObjectName("pageStack")
        self.stack.addWidget(self._bearing_page())
        self.stack.addWidget(self._operating_page())
        self.stack.addWidget(self._lubrication_page())
        self.stack.addWidget(self._installation_page())
        self.stack.addWidget(self._thermal_page())
        self.stack.addWidget(self._life_page())
        self.stack.addWidget(self._results_page())
        self.stack.addWidget(self._batch_page())
        self.stack.addWidget(self._calibration_page())
        self.navigation.currentRowChanged.connect(self._navigation_changed)
        self._go_to_page(0)

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        bar.setSizeGripEnabled(False)
        self.setStatusBar(bar)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusText")
        self.status_model = QLabel("No result")
        self.status_model.setObjectName("statusChip")
        bar.addWidget(self.status_label, 1)
        bar.addPermanentWidget(self.status_model)
        self._set_status_chip("No result", "idle")

    def _set_status_chip(self, text: str, state: str = "idle") -> None:
        """Update the result chip and re-polish so the QSS state rule applies."""
        self.status_model.setText(text)
        self.status_model.setProperty("state", state)
        self.status_model.style().unpolish(self.status_model)
        self.status_model.style().polish(self.status_model)

    # ------------------------------------------------------------------ help
    def _apply_field_help(self) -> None:
        """Attach the rich-text field help to inputs and their form labels.

        Keys in ``FIELD_HELP`` are widget attribute names, so the catalogue
        stays decoupled from label wording and layout order.
        """
        for name, entry in FIELD_HELP.items():
            widget = getattr(self, name, None)
            if widget is None:
                continue
            widget.setToolTip(tooltip_html(entry))
            widget.setWhatsThis(tooltip_html(entry))

        for name, entry in CONTROL_HELP.items():
            target = getattr(self, name, None)
            if target is None:
                continue
            html = tooltip_html(entry)
            if isinstance(target, dict):
                for widget in target.values():
                    widget.setToolTip(html)
            else:
                target.setToolTip(html)

        # QFormLayout.addRow(str, widget) makes the label a buddy of the field,
        # so the same help can be reached by hovering the label as well.
        for label in self.findChildren(QLabel):
            buddy = label.buddy()
            if buddy is not None and buddy.toolTip() and not label.toolTip():
                label.setToolTip(buddy.toolTip())

    # ------------------------------------------------------------- navigation
    def _navigation_changed(self, row: int) -> None:
        item = self.navigation.item(row)
        if item is None:
            return
        page_index = item.data(Qt.ItemDataRole.UserRole)
        if page_index is not None:
            self.stack.setCurrentIndex(int(page_index))

    def _go_to_page(self, page_index: int) -> None:
        """Select the rail row that owns ``page_index``."""
        for row in range(self.navigation.count()):
            item = self.navigation.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == page_index:
                self.navigation.setCurrentRow(row)
                return

    # ------------------------------------------------------------------ helpers
    def _page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("pageRoot")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(34, 28, 34, 22)
        outer.setSpacing(16)
        header = QLabel(title)
        header.setObjectName("pageTitle")
        detail = QLabel(subtitle)
        detail.setObjectName("pageSubtitle")
        detail.setWordWrap(True)
        detail.setMaximumWidth(940)
        head = QVBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(5)
        head.addWidget(header)
        head.addWidget(detail)
        outer.addLayout(head)
        return page, outer

    def _scroll_container(self, outer: QVBoxLayout) -> tuple[QWidget, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("scrollContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 2, 10, 10)
        layout.setSpacing(16)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        return content, layout

    def _group(self, title: str, columns: int = 1) -> tuple[QGroupBox, QGridLayout]:
        group = QGroupBox(small_caps(title))
        group.setObjectName("engineeringGroup")
        grid = QGridLayout(group)
        # The card header lives in the group box's QSS padding-top, so the
        # layout only needs side and bottom breathing room.
        grid.setContentsMargins(21, 2, 21, 20)
        grid.setHorizontalSpacing(30)
        grid.setVerticalSpacing(12)
        return group, grid

    def _form(self) -> QFormLayout:
        form = QFormLayout()
        # Left-aligned labels give every row a common left edge and remove the
        # dead gutter that right alignment opened up inside the wide cards.
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        return form

    def _double(
        self,
        minimum: float = 0.0,
        maximum: float = 1e9,
        decimals: int = 3,
        suffix: str = "",
        step: float = 1.0,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(decimals)
        widget.setSingleStep(step)
        widget.setSuffix(f" {suffix}" if suffix else "")
        widget.setKeyboardTracking(False)
        return widget

    def _spin(self, minimum: int, maximum: int, suffix: str = "") -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setSuffix(f" {suffix}" if suffix else "")
        widget.setKeyboardTracking(False)
        return widget

    def _combo(self, values: list[Any]) -> QComboBox:
        combo = QComboBox()
        for value in values:
            if hasattr(value, "value"):
                combo.addItem(value.value, value)
            else:
                combo.addItem(str(value), value)
        return combo

    def _note(self, text: str, warning: bool = False) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("warningNote" if warning else "methodNote")
        return label

    # ------------------------------------------------------------------ pages
    def _bearing_page(self) -> QWidget:
        page, outer = self._page(
            "Bearing definition",
            "Select the SKF friction-table family and series, then enter product geometry and rating data from the applicable catalogue record.",
        )
        _, layout = self._scroll_container(outer)

        group, grid = self._group("Case and table selection")
        left = self._form()
        self.case_name = QLineEdit()
        self.case_name.setPlaceholderText("e.g. HPT rear bearing — cruise")
        self.designation = QLineEdit()
        self.designation.setPlaceholderText("SKF catalogue designation, e.g. 6208")
        self.family = self._combo(list(BearingFamily))
        self.series = QComboBox()
        self.quality = self._combo(list(BearingQuality))
        left.addRow("Case name", self.case_name)
        left.addRow("Designation", self.designation)
        left.addRow("Bearing family", self.family)
        left.addRow("SKF table series", self.series)
        left.addRow("Performance class", self.quality)
        grid.addLayout(left, 0, 0)
        grid.addWidget(self._note("The selected family and series determine Grr/Gsl constants, Kz, KL and ball/roller friction coefficients."), 0, 1, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(group)

        group, grid = self._group("Geometry and product ratings")
        f1, f2 = self._form(), self._form()
        self.d = self._double(0.1, 5000, 3, "mm")
        self.D = self._double(0.1, 5000, 3, "mm")
        self.B = self._double(0.1, 3000, 3, "mm")
        self.d1 = self._double(0, 5000, 3, "mm")
        self.d2 = self._double(0, 5000, 3, "mm")
        self.E = self._double(0, 5000, 3, "mm")
        self.element_d = self._double(0, 1000, 3, "mm")
        self.element_count = self._spin(1, 500)
        self.row_count = self._spin(1, 10)
        f1.addRow("Bore d", self.d)
        f1.addRow("Outside diameter D", self.D)
        f1.addRow("Width B", self.B)
        f1.addRow("Seal diameter d1", self.d1)
        f1.addRow("Seal diameter d2", self.d2)
        f1.addRow("Raceway diameter E", self.E)
        f1.addRow("Rolling-element diameter", self.element_d)
        f1.addRow("Rolling-element count", self.element_count)
        f1.addRow("Row count", self.row_count)
        self.C = self._double(0.1, 1e10, 1, "N", 100)
        self.C0 = self._double(0.1, 1e10, 1, "N", 100)
        self.Cu = self._double(0, 1e10, 1, "N", 10)
        self.Y = self._double(0.001, 100, 4, "", 0.1)
        f2.addRow("Dynamic rating C", self.C)
        f2.addRow("Static rating C0", self.C0)
        f2.addRow("Fatigue load limit Cu", self.Cu)
        f2.addRow("Tapered factor Y", self.Y)
        grid.addLayout(f1, 0, 0)
        grid.addLayout(f2, 0, 1)
        layout.addWidget(group)
        layout.addWidget(self._note("d1, d2 and E are needed only by applicable contact-seal table rows. Y is required for tapered roller bearings."))
        layout.addStretch()

        self.family.currentIndexChanged.connect(self._family_changed)
        return page

    def _operating_page(self) -> QWidget:
        page, outer = self._page(
            "Operating point and lubricant",
            "Loads and speed drive the friction model. Viscosity is iterated from the solved contact temperature using a two-point Walther relation.",
        )
        _, layout = self._scroll_container(outer)
        group, grid = self._group("Operating condition")
        f1 = self._form()
        self.speed = self._double(0, 1e7, 1, "r/min", 100)
        self.Fr = self._double(0, 1e10, 1, "N", 100)
        self.Fa = self._double(0, 1e10, 1, "N", 100)
        self.P = self._double(0, 1e10, 1, "N", 100)
        f1.addRow("Speed n", self.speed)
        f1.addRow("Radial load Fr", self.Fr)
        f1.addRow("Axial load Fa", self.Fa)
        f1.addRow("Equivalent dynamic load P", self.P)
        grid.addLayout(f1, 0, 0)
        grid.addWidget(self._note("Set P to zero to use the program's clearly reported engineering default. For release work, enter P calculated with the bearing-specific X/Y factors."), 0, 1, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(group)

        group, grid = self._group("Lubricant properties")
        f1, f2 = self._form(), self._form()
        self.oil_name = QLineEdit()
        self.oil_name.setPlaceholderText("e.g. MIL-PRF-23699 turbine oil")
        self.nu40 = self._double(0.01, 100000, 3, "cSt", 1)
        self.nu100 = self._double(0.01, 100000, 3, "cSt", 0.1)
        self.oil_kind = self._combo(list(LubricantKind))
        self.density = self._double(1, 3000, 2, "kg/m³", 10)
        self.cp = self._double(1, 10000, 1, "J/(kg·K)", 10)
        self.ep_additives = QCheckBox("Proven EP additive performance")
        f1.addRow("Lubricant name", self.oil_name)
        f1.addRow("Kinematic viscosity ν40", self.nu40)
        f1.addRow("Kinematic viscosity ν100", self.nu100)
        f1.addRow("Lubricant category", self.oil_kind)
        f2.addRow("Density", self.density)
        f2.addRow("Specific heat", self.cp)
        f2.addRow("Additive status", self.ep_additives)
        grid.addLayout(f1, 0, 0)
        grid.addLayout(f2, 0, 1)
        layout.addWidget(group)
        layout.addStretch()
        return page

    def _lubrication_page(self) -> QWidget:
        page, outer = self._page(
            "Lubrication, drag and seals",
            "Replenishment controls the SKF starvation factor. Oil-bath and oil-jet modes also evaluate churning/drag torque; compatible contact seals use SKF table coefficients.",
        )
        _, layout = self._scroll_container(outer)
        group, grid = self._group("Lubrication and drag")
        f1, f2 = self._form(), self._form()
        self.lub_mode = self._combo(list(LubricationMode))
        self.oil_level = self._double(0, 5000, 3, "mm")
        self.orientation = self._combo(list(ShaftOrientation))
        self.vertical_fraction = self._double(0.001, 1.0, 3)
        self.drag_enabled = QCheckBox("Evaluate SKF oil drag")
        self.fixed_drag = self._double(0, 1e9, 4, "N·mm")
        self.vm_override = self._double(0, 1.0, 8)
        f1.addRow("Lubrication mode", self.lub_mode)
        f1.addRow("Immersion/equivalent H", self.oil_level)
        f1.addRow("Shaft orientation", self.orientation)
        f1.addRow("Vertical submerged fraction", self.vertical_fraction)
        f2.addRow("Drag model", self.drag_enabled)
        f2.addRow("Added fixed drag torque", self.fixed_drag)
        f2.addRow("Manual VM override (0=graph)", self.vm_override)
        grid.addLayout(f1, 0, 0)
        grid.addLayout(f2, 0, 1)
        layout.addWidget(group)
        layout.addWidget(self._note("The SKF VM factor is published graphically. With override = 0, the program uses a documented digitization; oil-jet drag uses the published ×2 treatment."))

        group, grid = self._group("Contact seals")
        f1, f2 = self._form(), self._form()
        self.seal_type = QComboBox()
        self.seal_count = self._spin(0, 2)
        self.seal_diameter = self._double(0, 5000, 3, "mm")
        self.Ks1 = self._double(0, 1000, 8)
        self.Ks2 = self._double(0, 1e8, 5, "N·mm")
        self.beta = self._double(0, 10, 5)
        f1.addRow("Seal type", self.seal_type)
        f1.addRow("Seal count", self.seal_count)
        f1.addRow("Manual diameter", self.seal_diameter)
        f2.addRow("Manual Ks1", self.Ks1)
        f2.addRow("Manual Ks2", self.Ks2)
        f2.addRow("Manual β", self.beta)
        grid.addLayout(f1, 0, 0)
        grid.addLayout(f2, 0, 1)
        layout.addWidget(group)
        layout.addStretch()
        return page

    def _installation_page(self) -> QWidget:
        page, outer = self._page(
            "Clearance, preload and misalignment",
            "SKF's table model assumes normal operating clearance and aligned rings. This page contains optional, separately flagged engineering extensions and a generic rolling-element load-zone solver.",
        )
        _, layout = self._scroll_container(outer)
        self.install_enabled = QCheckBox("Enable installation correction in friction calculation")
        self.install_enabled.setObjectName("primaryCheck")
        layout.addWidget(self.install_enabled)
        layout.addWidget(self._note("These correction multipliers are not published SKF friction equations. Calibrate coefficients against detailed internal-load analysis, SKF Bearing Select reference points, or tests.", True))

        group, grid = self._group("Clearance and preload")
        f1, f2 = self._form(), self._form()
        self.clearance = self._double(-10000, 10000, 3, "µm", 1)
        self.reference_clearance = self._double(0.001, 10000, 3, "µm", 1)
        self.radial_preload = self._double(0, 1e9, 1, "N", 100)
        self.axial_preload = self._double(0, 1e9, 1, "N", 100)
        self.clearance_stiffness = self._double(0, 1e9, 3, "N/µm", 1)
        self.clearance_coeff = self._double(0, 100, 4)
        f1.addRow("Operating clearance", self.clearance)
        f1.addRow("Reference clearance", self.reference_clearance)
        f1.addRow("Radial preload", self.radial_preload)
        f1.addRow("Axial preload", self.axial_preload)
        f2.addRow("Clearance stiffness", self.clearance_stiffness)
        f2.addRow("Torque coefficient", self.clearance_coeff)
        grid.addLayout(f1, 0, 0)
        grid.addLayout(f2, 0, 1)
        layout.addWidget(group)

        group, grid = self._group("Misalignment and load distribution")
        f1, f2 = self._form(), self._form()
        self.misalignment = self._double(0, 1000, 5, "mrad", 0.1)
        self.permissible_misalignment = self._double(0.0001, 1000, 5, "mrad", 0.1)
        self.misalignment_coeff = self._double(0, 100, 4)
        self.contact_stiffness = self._double(0.001, 1e12, 2, "N/mmᵖ", 1000)
        self.deflection_exponent = self._double(0.01, 10, 5)
        f1.addRow("Ring misalignment", self.misalignment)
        f1.addRow("Permissible misalignment", self.permissible_misalignment)
        f1.addRow("Torque coefficient", self.misalignment_coeff)
        f2.addRow("Contact stiffness", self.contact_stiffness)
        f2.addRow("Load-deflection exponent p", self.deflection_exponent)
        grid.addLayout(f1, 0, 0)
        grid.addLayout(f2, 0, 1)
        layout.addWidget(group)
        layout.addStretch()
        return page

    def _thermal_page(self) -> QWidget:
        page, outer = self._page(
            "Thermal network and oil flow",
            "Choose a fast one-node balance or resolve inner ring, rolling elements, outer ring and lubricant. Four-node conductances and local contact resistances are calibration inputs.",
        )
        _, layout = self._scroll_container(outer)
        group, grid = self._group("Boundary conditions and solver")
        f1, f2 = self._form(), self._form()
        self.thermal_model = self._combo(list(ThermalModel))
        self.inlet_temp = self._double(-200, 1000, 3, "°C")
        self.ambient_temp = self._double(-200, 1000, 3, "°C")
        self.shaft_temp = self._double(-200, 1000, 3, "°C")
        self.housing_temp = self._double(-200, 1000, 3, "°C")
        self.oil_flow = self._double(0, 10000, 5, "L/min", 0.01)
        self.one_g = self._double(0, 1e8, 5, "W/K", 0.1)
        self.heat_fraction = self._double(0.001, 1.0, 4)
        self.relaxation = self._double(0.001, 1.0, 4)
        self.tolerance = self._double(1e-9, 100, 7, "°C")
        self.max_iterations = self._spin(1, 10000)
        f1.addRow("Thermal model", self.thermal_model)
        f1.addRow("Oil inlet temperature", self.inlet_temp)
        f1.addRow("Ambient temperature", self.ambient_temp)
        f1.addRow("Shaft boundary", self.shaft_temp)
        f1.addRow("Housing boundary", self.housing_temp)
        f1.addRow("Oil flow", self.oil_flow)
        f2.addRow("One-node housing G", self.one_g)
        f2.addRow("Heat fraction modelled", self.heat_fraction)
        f2.addRow("Relaxation", self.relaxation)
        f2.addRow("Temperature tolerance", self.tolerance)
        f2.addRow("Maximum iterations", self.max_iterations)
        grid.addLayout(f1, 0, 0)
        grid.addLayout(f2, 0, 1)
        layout.addWidget(group)

        group, grid = self._group("Four-node conductances")
        f1, f2 = self._form(), self._form()
        self.Gis = self._double(0, 1e8, 5, "W/K")
        self.Goh = self._double(0, 1e8, 5, "W/K")
        self.Gie = self._double(0, 1e8, 5, "W/K")
        self.Goe = self._double(0, 1e8, 5, "W/K")
        self.Gio = self._double(0, 1e8, 5, "W/K")
        self.Goo = self._double(0, 1e8, 5, "W/K")
        self.Geo = self._double(0, 1e8, 5, "W/K")
        f1.addRow("Inner ring → shaft", self.Gis)
        f1.addRow("Outer ring → housing", self.Goh)
        f1.addRow("Inner ring ↔ elements", self.Gie)
        f1.addRow("Outer ring ↔ elements", self.Goe)
        f2.addRow("Inner ring ↔ oil", self.Gio)
        f2.addRow("Outer ring ↔ oil", self.Goo)
        f2.addRow("Elements ↔ oil", self.Geo)
        grid.addLayout(f1, 0, 0)
        grid.addLayout(f2, 0, 1)
        layout.addWidget(group)

        group, grid = self._group("Flow partition and local contact rise")
        f1, f2 = self._form(), self._form()
        self.bypass = self._double(0, 1, 4)
        self.q_element = self._double(0, 1, 4)
        self.q_inner = self._double(0, 1, 4)
        self.q_outer = self._double(0, 1, 4)
        self.seal_outer = self._double(0, 1, 4)
        self.drag_oil = self._double(0, 1, 4)
        self.rth_inner = self._double(0, 1000, 7, "K/W")
        self.rth_outer = self._double(0, 1000, 7, "K/W")
        f1.addRow("Oil bypass fraction", self.bypass)
        f1.addRow("Element heat share", self.q_element)
        f1.addRow("Inner-race heat share", self.q_inner)
        f1.addRow("Outer-race heat share", self.q_outer)
        f2.addRow("Seal heat to outer", self.seal_outer)
        f2.addRow("Drag heat to oil", self.drag_oil)
        f2.addRow("Inner contact Rth", self.rth_inner)
        f2.addRow("Outer contact Rth", self.rth_outer)
        grid.addLayout(f1, 0, 0)
        grid.addLayout(f2, 0, 1)
        layout.addWidget(group)
        layout.addStretch()
        return page

    def _life_page(self) -> QWidget:
        page, outer = self._page(
            "SKF / ISO rating life",
            "Calculate L10 and modified life from reliability, viscosity ratio, contamination and fatigue load limit. The exact equivalent dynamic load should normally be entered on the Operating page.",
        )
        _, layout = self._scroll_container(outer)
        self.life_enabled = QCheckBox("Calculate rating life")
        self.life_enabled.setObjectName("primaryCheck")
        layout.addWidget(self.life_enabled)
        group, grid = self._group("Life modification inputs")
        f1, f2 = self._form(), self._form()
        self.reliability = self._double(90, 99.95, 3, "%", 0.1)
        self.contamination_preset = QComboBox()
        for name in CONTAMINATION_PRESETS:
            self.contamination_preset.addItem(name)
        self.ec = self._double(0, 1, 5)
        self.explorer_scale = self._double(0, 10, 5)
        f1.addRow("Reliability", self.reliability)
        f1.addRow("Cleanliness preset", self.contamination_preset)
        f1.addRow("Contamination factor eC", self.ec)
        f2.addRow("Explorer axis scale (0=default)", self.explorer_scale)
        grid.addLayout(f1, 0, 0)
        grid.addLayout(f2, 0, 1)
        layout.addWidget(group)
        layout.addWidget(self._note("Explorer mode uses a configurable diagram-axis approximation because the improvement depends on bearing performance class and published SKF diagrams. It is not represented as one universal catalogue multiplier."))
        layout.addStretch()
        self.contamination_preset.currentTextChanged.connect(self._contamination_preset_changed)
        return page

    def _results_page(self) -> QWidget:
        page, outer = self._page(
            "Calculation results",
            "Run the coupled solution with F5. Charts, factor values, assumptions and warnings update from the current case.",
        )
        cards = QGridLayout()
        self.metric_temp = MetricCard("Contact temperature", "°C")
        self.metric_visc = MetricCard("Operating viscosity", "cSt")
        self.metric_torque = MetricCard("Total friction torque", "N·mm")
        self.metric_power = MetricCard("Power loss", "W")
        self.metric_life = MetricCard("Modified life", "h")
        self.metric_kappa = MetricCard("Viscosity ratio κ", "—")
        for index, card in enumerate([
            self.metric_temp,
            self.metric_visc,
            self.metric_torque,
            self.metric_power,
            self.metric_life,
            self.metric_kappa,
        ]):
            cards.addWidget(card, index // 3, index % 3)
        outer.addLayout(cards)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.result_tabs = QTabWidget()
        self.convergence_plot = PlotCanvas()
        self.torque_plot = PlotCanvas()
        self.temperature_plot = PlotCanvas()
        self.load_plot = PlotCanvas(polar=True)
        self.result_tabs.addTab(self.convergence_plot, "Convergence")
        self.result_tabs.addTab(self.torque_plot, "Torque")
        self.result_tabs.addTab(self.temperature_plot, "Temperatures")
        self.result_tabs.addTab(self.load_plot, "Element load zone")
        splitter.addWidget(self.result_tabs)

        lower = QTabWidget()
        self.results_table = QTableWidget(0, 2)
        self.results_table.setHorizontalHeaderLabels(["Quantity", "Value"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.warning_text = QTextEdit()
        self.warning_text.setReadOnly(True)
        lower.addTab(self.results_table, "Detailed values")
        lower.addTab(self.warning_text, "Warnings / assumptions")
        splitter.addWidget(lower)
        splitter.setSizes([450, 260])
        outer.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        export_report = QPushButton("Export HTML report")
        export_history = QPushButton("Export convergence CSV")
        export_report.clicked.connect(self._export_report)
        export_history.clicked.connect(self._export_history)
        buttons.addStretch()
        buttons.addWidget(export_history)
        buttons.addWidget(export_report)
        outer.addLayout(buttons)
        return page

    def _batch_page(self) -> QWidget:
        page, outer = self._page(
            "Batch operating map",
            "Each CSV row overrides the current base case. Use this for speed/load maps, duty cycles, sensitivity studies and design-of-experiments tables.",
        )
        controls, grid = self._group("Batch input")
        self.batch_path = QLineEdit()
        self.batch_path.setPlaceholderText("Select a CSV of operating points…")
        self.batch_path.setClearButtonEnabled(True)
        browse = QPushButton("Browse…")
        template = QPushButton("Create template")
        self.batch_workers = self._spin(1, max(os.cpu_count() or 1, 1))
        self.batch_backend = QComboBox()
        self.batch_backend.addItems(["Full engineering solver", "Numba fast DGBB one-node"])
        run = QPushButton("Run batch")
        run.setObjectName("primaryButton")
        save = QPushButton("Save results…")
        browse.clicked.connect(self._browse_batch)
        template.clicked.connect(self._create_batch_template)
        run.clicked.connect(self._run_batch)
        save.clicked.connect(self._save_batch_result)
        input_label = QLabel("Input CSV")
        input_label.setBuddy(self.batch_path)
        grid.addWidget(input_label, 0, 0)
        grid.addWidget(self.batch_path, 0, 1, 1, 3)
        grid.addWidget(browse, 0, 4)
        grid.addWidget(template, 0, 5)
        backend_label = QLabel("Backend")
        backend_label.setBuddy(self.batch_backend)
        workers_label = QLabel("Processes")
        workers_label.setBuddy(self.batch_workers)
        grid.addWidget(backend_label, 1, 0)
        grid.addWidget(self.batch_backend, 1, 1)
        grid.addWidget(workers_label, 1, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.batch_workers, 1, 3)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 6, 0, 0)
        actions.setSpacing(10)
        actions.addStretch()
        actions.addWidget(save)
        actions.addWidget(run)
        grid.addLayout(actions, 2, 0, 1, 6)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        outer.addWidget(controls)
        self.batch_model = DataFrameModel()
        self.batch_table = QTableView()
        self.batch_table.setModel(self.batch_model)
        self.batch_table.setAlternatingRowColors(True)
        self.batch_table.setSortingEnabled(False)
        self.batch_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        outer.addWidget(self.batch_table, 1)
        return page

    def _calibration_page(self) -> QWidget:
        page, outer = self._page(
            "Calibration and validation",
            "Import measured torque/temperature points or manually exported SKF Bearing Select reference points. Fit selected scale parameters, inspect residuals, and save the profile with the case.",
        )
        controls, grid = self._group("Reference data and parameters")
        self.cal_path = QLineEdit()
        self.cal_path.setPlaceholderText("Select a CSV of measured reference points…")
        self.cal_path.setClearButtonEnabled(True)
        browse = QPushButton("Browse…")
        template = QPushButton("Create template")
        browse.clicked.connect(self._browse_calibration)
        template.clicked.connect(self._create_calibration_template)
        cal_label = QLabel("Calibration CSV")
        cal_label.setBuddy(self.cal_path)
        grid.addWidget(cal_label, 0, 0)
        grid.addWidget(self.cal_path, 0, 1, 1, 3)
        grid.addWidget(browse, 0, 4)
        grid.addWidget(template, 0, 5)
        self.cal_checks: dict[str, QCheckBox] = {}
        names = [
            ("rolling_scale", "Rolling"),
            ("sliding_scale", "Sliding"),
            ("seal_scale", "Seal"),
            ("drag_scale", "Drag"),
            ("heat_transfer_scale", "Heat transfer"),
            ("installation_scale", "Installation"),
        ]
        fitted_label = QLabel("Fitted scale parameters")
        grid.addWidget(fitted_label, 1, 0, Qt.AlignmentFlag.AlignTop)
        checks = QHBoxLayout()
        checks.setContentsMargins(0, 0, 0, 0)
        checks.setSpacing(18)
        for key, label in names:
            check = QCheckBox(label)
            check.setChecked(key in {"rolling_scale", "sliding_scale", "drag_scale", "heat_transfer_scale"})
            self.cal_checks[key] = check
            checks.addWidget(check)
        checks.addStretch()
        grid.addLayout(checks, 1, 1, 1, 5)
        fit = QPushButton("Fit selected parameters")
        fit.setObjectName("primaryButton")
        save = QPushButton("Save profile…")
        fit.clicked.connect(self._run_calibration)
        save.clicked.connect(self._save_calibration_profile)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 6, 0, 0)
        actions.setSpacing(10)
        actions.addStretch()
        actions.addWidget(save)
        actions.addWidget(fit)
        grid.addLayout(actions, 2, 0, 1, 6)
        grid.setColumnStretch(1, 1)
        outer.addWidget(controls)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.calibration_summary = QTextEdit()
        self.calibration_summary.setReadOnly(True)
        self.calibration_summary.setMaximumHeight(190)
        self.calibration_model = DataFrameModel()
        self.calibration_table = QTableView()
        self.calibration_table.setModel(self.calibration_model)
        self.calibration_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        splitter.addWidget(self.calibration_summary)
        splitter.addWidget(self.calibration_table)
        splitter.setSizes([180, 450])
        outer.addWidget(splitter, 1)
        return page

    # ------------------------------------------------------------------ binding
    def _family_changed(self) -> None:
        family = self.family.currentData()
        if not isinstance(family, BearingFamily):
            return
        current_series = self.series.currentText()
        self.series.blockSignals(True)
        self.series.clear()
        self.series.addItems(available_series(family))
        index = self.series.findText(current_series)
        self.series.setCurrentIndex(index if index >= 0 else 0)
        self.series.blockSignals(False)

        current_seal = self.seal_type.currentText() if hasattr(self, "seal_type") else "None"
        if hasattr(self, "seal_type"):
            self.seal_type.clear()
            self.seal_type.addItems(compatible_seal_types(family))
            idx = self.seal_type.findText(current_seal)
            self.seal_type.setCurrentIndex(idx if idx >= 0 else 0)

    def _contamination_preset_changed(self, name: str) -> None:
        if name not in CONTAMINATION_PRESETS or not hasattr(self, "D"):
            return
        small, large = CONTAMINATION_PRESETS[name]
        dm = 0.5 * (self.d.value() + self.D.value())
        self.ec.setValue(small if dm < 100 else large)

    def _read_case_from_ui(self) -> BearingCase:
        case = copy.deepcopy(self.case)
        case.case_name = self.case_name.text().strip() or "Untitled bearing case"
        b = case.bearing
        b.family = self.family.currentData()
        b.series = self.series.currentText()
        b.designation = self.designation.text().strip()
        b.quality = self.quality.currentData()
        b.d_mm, b.D_mm, b.B_mm = self.d.value(), self.D.value(), self.B.value()
        b.d1_mm, b.d2_mm, b.E_mm = self.d1.value(), self.d2.value(), self.E.value()
        b.rolling_element_diameter_mm = self.element_d.value()
        b.rolling_element_count = self.element_count.value()
        b.row_count = self.row_count.value()
        b.C_N, b.C0_N, b.Cu_N, b.Y = self.C.value(), self.C0.value(), self.Cu.value(), self.Y.value()

        op = case.operating
        op.speed_rpm, op.radial_load_n, op.axial_load_n = self.speed.value(), self.Fr.value(), self.Fa.value()
        op.equivalent_dynamic_load_n = self.P.value()
        oil = case.lubricant
        oil.name = self.oil_name.text().strip()
        oil.nu40_cst, oil.nu100_cst = self.nu40.value(), self.nu100.value()
        oil.kind = self.oil_kind.currentData()
        oil.density_kg_m3, oil.cp_j_kgk = self.density.value(), self.cp.value()
        oil.proven_ep_additives = self.ep_additives.isChecked()

        lub = case.lubrication
        lub.mode = self.lub_mode.currentData()
        lub.oil_level_h_mm = self.oil_level.value()
        lub.shaft_orientation = self.orientation.currentData()
        lub.vertical_submerged_width_fraction = self.vertical_fraction.value()
        lub.drag_enabled = self.drag_enabled.isChecked()
        lub.fixed_drag_torque_nmm = self.fixed_drag.value()
        lub.volume_factor_override = self.vm_override.value()
        seal = case.seal
        seal.seal_type, seal.count = self.seal_type.currentText(), self.seal_count.value()
        seal.manual_diameter_mm = self.seal_diameter.value()
        seal.manual_Ks1, seal.manual_Ks2, seal.manual_beta = self.Ks1.value(), self.Ks2.value(), self.beta.value()

        ins = case.installation
        ins.enabled = self.install_enabled.isChecked()
        ins.operating_clearance_um = self.clearance.value()
        ins.reference_clearance_um = self.reference_clearance.value()
        ins.radial_preload_n, ins.axial_preload_n = self.radial_preload.value(), self.axial_preload.value()
        ins.clearance_stiffness_n_per_um = self.clearance_stiffness.value()
        ins.clearance_torque_coefficient = self.clearance_coeff.value()
        ins.misalignment_mrad = self.misalignment.value()
        ins.permissible_misalignment_mrad = self.permissible_misalignment.value()
        ins.misalignment_torque_coefficient = self.misalignment_coeff.value()
        ins.contact_stiffness_n_per_mm_p = self.contact_stiffness.value()
        ins.load_deflection_exponent = self.deflection_exponent.value()

        th = case.thermal
        th.model = self.thermal_model.currentData()
        th.inlet_temp_c, th.ambient_temp_c = self.inlet_temp.value(), self.ambient_temp.value()
        th.shaft_boundary_temp_c, th.housing_boundary_temp_c = self.shaft_temp.value(), self.housing_temp.value()
        th.oil_flow_l_min = self.oil_flow.value()
        th.one_node_housing_conductance_w_k = self.one_g.value()
        th.heat_fraction_to_model = self.heat_fraction.value()
        th.relaxation, th.tolerance_c, th.max_iterations = self.relaxation.value(), self.tolerance.value(), self.max_iterations.value()
        th.G_inner_shaft_w_k, th.G_outer_housing_w_k = self.Gis.value(), self.Goh.value()
        th.G_inner_element_w_k, th.G_outer_element_w_k = self.Gie.value(), self.Goe.value()
        th.G_inner_oil_w_k, th.G_outer_oil_w_k, th.G_element_oil_w_k = self.Gio.value(), self.Goo.value(), self.Geo.value()
        th.oil_bypass_fraction = self.bypass.value()
        th.element_heat_fraction, th.inner_race_heat_fraction, th.outer_race_heat_fraction = self.q_element.value(), self.q_inner.value(), self.q_outer.value()
        th.seal_heat_to_outer_fraction, th.drag_heat_to_oil_fraction = self.seal_outer.value(), self.drag_oil.value()
        th.inner_contact_rth_k_w, th.outer_contact_rth_k_w = self.rth_inner.value(), self.rth_outer.value()

        life = case.life
        life.enabled = self.life_enabled.isChecked()
        life.reliability_percent = self.reliability.value()
        life.contamination_preset = self.contamination_preset.currentText()
        life.contamination_factor_ec = self.ec.value()
        life.explorer_axis_scale = self.explorer_scale.value()
        case.validate()
        return case

    def _set_combo_data(self, combo: QComboBox, value: Any) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value or combo.itemText(i) == getattr(value, "value", value):
                combo.setCurrentIndex(i)
                return

    def _write_case_to_ui(self, case: BearingCase) -> None:
        self.case_name.setText(case.case_name)
        self.designation.setText(case.bearing.designation)
        self._set_combo_data(self.family, case.bearing.family)
        self._family_changed()
        idx = self.series.findText(case.bearing.series)
        self.series.setCurrentIndex(idx if idx >= 0 else 0)
        self._set_combo_data(self.quality, case.bearing.quality)
        for widget, value in [
            (self.d, case.bearing.d_mm), (self.D, case.bearing.D_mm), (self.B, case.bearing.B_mm),
            (self.d1, case.bearing.d1_mm), (self.d2, case.bearing.d2_mm), (self.E, case.bearing.E_mm),
            (self.element_d, case.bearing.rolling_element_diameter_mm), (self.C, case.bearing.C_N),
            (self.C0, case.bearing.C0_N), (self.Cu, case.bearing.Cu_N), (self.Y, case.bearing.Y),
            (self.speed, case.operating.speed_rpm), (self.Fr, case.operating.radial_load_n),
            (self.Fa, case.operating.axial_load_n), (self.P, case.operating.equivalent_dynamic_load_n),
            (self.nu40, case.lubricant.nu40_cst), (self.nu100, case.lubricant.nu100_cst),
            (self.density, case.lubricant.density_kg_m3), (self.cp, case.lubricant.cp_j_kgk),
            (self.oil_level, case.lubrication.oil_level_h_mm), (self.vertical_fraction, case.lubrication.vertical_submerged_width_fraction),
            (self.fixed_drag, case.lubrication.fixed_drag_torque_nmm), (self.vm_override, case.lubrication.volume_factor_override),
            (self.seal_diameter, case.seal.manual_diameter_mm), (self.Ks1, case.seal.manual_Ks1),
            (self.Ks2, case.seal.manual_Ks2), (self.beta, case.seal.manual_beta),
            (self.clearance, case.installation.operating_clearance_um), (self.reference_clearance, case.installation.reference_clearance_um),
            (self.radial_preload, case.installation.radial_preload_n), (self.axial_preload, case.installation.axial_preload_n),
            (self.clearance_stiffness, case.installation.clearance_stiffness_n_per_um), (self.clearance_coeff, case.installation.clearance_torque_coefficient),
            (self.misalignment, case.installation.misalignment_mrad), (self.permissible_misalignment, case.installation.permissible_misalignment_mrad),
            (self.misalignment_coeff, case.installation.misalignment_torque_coefficient), (self.contact_stiffness, case.installation.contact_stiffness_n_per_mm_p),
            (self.deflection_exponent, case.installation.load_deflection_exponent), (self.inlet_temp, case.thermal.inlet_temp_c),
            (self.ambient_temp, case.thermal.ambient_temp_c), (self.shaft_temp, case.thermal.shaft_boundary_temp_c),
            (self.housing_temp, case.thermal.housing_boundary_temp_c), (self.oil_flow, case.thermal.oil_flow_l_min),
            (self.one_g, case.thermal.one_node_housing_conductance_w_k), (self.heat_fraction, case.thermal.heat_fraction_to_model),
            (self.relaxation, case.thermal.relaxation), (self.tolerance, case.thermal.tolerance_c),
            (self.Gis, case.thermal.G_inner_shaft_w_k), (self.Goh, case.thermal.G_outer_housing_w_k),
            (self.Gie, case.thermal.G_inner_element_w_k), (self.Goe, case.thermal.G_outer_element_w_k),
            (self.Gio, case.thermal.G_inner_oil_w_k), (self.Goo, case.thermal.G_outer_oil_w_k),
            (self.Geo, case.thermal.G_element_oil_w_k), (self.bypass, case.thermal.oil_bypass_fraction),
            (self.q_element, case.thermal.element_heat_fraction), (self.q_inner, case.thermal.inner_race_heat_fraction),
            (self.q_outer, case.thermal.outer_race_heat_fraction), (self.seal_outer, case.thermal.seal_heat_to_outer_fraction),
            (self.drag_oil, case.thermal.drag_heat_to_oil_fraction), (self.rth_inner, case.thermal.inner_contact_rth_k_w),
            (self.rth_outer, case.thermal.outer_contact_rth_k_w), (self.reliability, case.life.reliability_percent),
            (self.ec, case.life.contamination_factor_ec), (self.explorer_scale, case.life.explorer_axis_scale),
        ]:
            widget.setValue(value)
        self.element_count.setValue(case.bearing.rolling_element_count)
        self.row_count.setValue(case.bearing.row_count)
        self.max_iterations.setValue(case.thermal.max_iterations)
        self.oil_name.setText(case.lubricant.name)
        self._set_combo_data(self.oil_kind, case.lubricant.kind)
        self.ep_additives.setChecked(case.lubricant.proven_ep_additives)
        self._set_combo_data(self.lub_mode, case.lubrication.mode)
        self._set_combo_data(self.orientation, case.lubrication.shaft_orientation)
        self.drag_enabled.setChecked(case.lubrication.drag_enabled)
        seal_index = self.seal_type.findText(case.seal.seal_type)
        self.seal_type.setCurrentIndex(seal_index if seal_index >= 0 else 0)
        self.seal_count.setValue(case.seal.count)
        self.install_enabled.setChecked(case.installation.enabled)
        self._set_combo_data(self.thermal_model, case.thermal.model)
        self.life_enabled.setChecked(case.life.enabled)
        preset_index = self.contamination_preset.findText(case.life.contamination_preset)
        self.contamination_preset.setCurrentIndex(preset_index if preset_index >= 0 else 0)

    # ------------------------------------------------------------------ actions
    def _new_case(self) -> None:
        self.case = BearingCase()
        self.current_case_path = None
        self.result = None
        self._write_case_to_ui(self.case)
        self._clear_results()
        self.status_label.setText("New case")

    def _open_case(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open bearing case", "", "Bearing case (*.json);;All files (*)")
        if not path:
            return
        try:
            case = load_case(path)
        except Exception as exc:
            self._show_error("Could not open case", str(exc))
            return
        self.case, self.current_case_path = case, Path(path)
        self._write_case_to_ui(case)
        self.result = None
        self._clear_results()
        self.status_label.setText(f"Opened {Path(path).name}")

    def _save_case(self, save_as: bool = False) -> None:
        try:
            self.case = self._read_case_from_ui()
        except Exception as exc:
            self._show_error("Input validation failed", str(exc))
            return
        path = self.current_case_path
        if save_as or path is None:
            selected, _ = QFileDialog.getSaveFileName(self, "Save bearing case", f"{self.case.case_name}.json", "Bearing case (*.json)")
            if not selected:
                return
            path = Path(selected)
        save_case(self.case, path)
        self.current_case_path = path
        self.status_label.setText(f"Saved {path.name}")

    def _run_calculation(self) -> None:
        try:
            self.case = self._read_case_from_ui()
        except Exception as exc:
            self._show_error("Input validation failed", str(exc))
            return
        self.run_action.setEnabled(False)
        self.status_label.setText("Solving coupled bearing model…")
        self._set_status_chip("RUNNING", "running")
        case = copy.deepcopy(self.case)
        worker = FunctionWorker(lambda: solve_case(case))
        worker.signals.result.connect(self._calculation_finished)
        worker.signals.error.connect(lambda text: self._worker_error("Calculation failed", text))
        worker.signals.finished.connect(lambda: self.run_action.setEnabled(True))
        self.thread_pool.start(worker)

    def _calculation_finished(self, result: Any) -> None:
        self.result = result
        self._update_results(result)
        self.report_action.setEnabled(True)
        self.status_label.setText(f"Solved in {result.iterations} iterations")
        if result.converged:
            self._set_status_chip("CONVERGED", "ok")
        else:
            self._set_status_chip("NOT CONVERGED", "warn")
        self._go_to_page(6)

    def _clear_results(self) -> None:
        for card in [self.metric_temp, self.metric_visc, self.metric_torque, self.metric_power, self.metric_life, self.metric_kappa]:
            card.set_value("—")
        self.results_table.setRowCount(0)
        self.warning_text.clear()
        self.report_action.setEnabled(False)
        for canvas in [self.convergence_plot, self.torque_plot, self.temperature_plot, self.load_plot]:
            canvas.reset()
            canvas.draw_idle()
        self._set_status_chip("No result", "idle")

    def _update_results(self, result: Any) -> None:
        self.metric_temp.set_value(result.thermal.contact_temperature_c)
        self.metric_visc.set_value(result.friction.viscosity_cst, 3)
        self.metric_torque.set_value(result.friction.total_torque_nmm)
        self.metric_power.set_value(result.friction.total_power_w)
        if result.life:
            self.metric_life.set_value(result.life.modified_life_hours, 1)
            self.metric_kappa.set_value(result.life.viscosity_ratio_kappa, 3)
        else:
            self.metric_life.set_value("Disabled")
            self.metric_kappa.set_value("—")

        details = {
            "Converged": result.converged,
            "Iterations": result.iterations,
            "Grr": result.friction.Grr,
            "Gsl": result.friction.Gsl,
            "φish": result.friction.phi_ish,
            "φrs": result.friction.phi_rs,
            "φbl": result.friction.phi_bl,
            "μsl": result.friction.mu_sl,
            "Rolling torque [N·mm]": result.friction.rolling_torque_nmm,
            "Sliding torque [N·mm]": result.friction.sliding_torque_nmm,
            "Seal torque [N·mm]": result.friction.seal_torque_nmm,
            "Drag torque [N·mm]": result.friction.drag_torque_nmm,
            "Total power [W]": result.friction.total_power_w,
            "Inner contact [°C]": result.thermal.inner_contact_temperature_c,
            "Outer contact [°C]": result.thermal.outer_contact_temperature_c,
            "Heat to shaft [W]": result.thermal.heat_to_shaft_w,
            "Heat to housing [W]": result.thermal.heat_to_housing_w,
            "Heat to oil [W]": result.thermal.heat_to_oil_w,
            "Effective radial load [N]": result.installation.effective_radial_load_n,
            "Effective axial load [N]": result.installation.effective_axial_load_n,
            "Installation torque multiplier": result.installation.total_torque_multiplier,
            "Maximum element load [N]": result.load_distribution.maximum_element_load_n,
            "Loaded elements": result.load_distribution.loaded_element_count,
        }
        if result.life:
            details.update({
                "Equivalent dynamic load P [N]": result.life.equivalent_dynamic_load_n,
                "Basic L10 [Mrev]": result.life.basic_life_mrev,
                "Basic L10h [h]": result.life.basic_life_hours,
                "Reliability factor a1": result.life.reliability_factor_a1,
                "Rated viscosity ν1 [cSt]": result.life.rated_viscosity_cst,
                "Viscosity ratio κ": result.life.viscosity_ratio_kappa,
                "aSKF": result.life.askf,
                "Modified life [Mrev]": result.life.modified_life_mrev,
                "Modified life [h]": result.life.modified_life_hours,
            })
        self.results_table.setRowCount(len(details))
        for row, (name, value) in enumerate(details.items()):
            self.results_table.setItem(row, 0, QTableWidgetItem(str(name)))
            if isinstance(value, float):
                text = "∞" if value == float("inf") else f"{value:,.6g}"
            else:
                text = str(value)
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.results_table.setItem(row, 1, item)
        self.warning_text.setPlainText("\n\n".join(f"• {item}" for item in result.warnings) or "No warnings.")

        ax = self.convergence_plot.reset()
        ax.plot([h["iteration"] for h in result.history], [h["temperature_c"] for h in result.history], marker="o", label="Iterated")
        ax.plot([h["iteration"] for h in result.history], [h["target_temperature_c"] for h in result.history], marker="x", label="Thermal target")
        ax.set_xlabel("Iteration")
        ax.set_ylabel("Temperature [°C]")
        ax.grid(True, alpha=0.25)
        ax.legend()
        self.convergence_plot.draw_idle()

        ax = self.torque_plot.reset()
        labels = ["Rolling", "Sliding", "Seal", "Drag"]
        values = [result.friction.rolling_torque_nmm, result.friction.sliding_torque_nmm, result.friction.seal_torque_nmm, result.friction.drag_torque_nmm]
        ax.bar(labels, values)
        ax.set_ylabel("Torque [N·mm]")
        ax.grid(True, axis="y", alpha=0.25)
        self.torque_plot.draw_idle()

        ax = self.temperature_plot.reset()
        labels = ["Inner", "Elements", "Outer", "Oil", "Contact"]
        values = [result.thermal.inner_ring_temperature_c, result.thermal.rolling_element_temperature_c, result.thermal.outer_ring_temperature_c, result.thermal.oil_outlet_temperature_c, result.thermal.contact_temperature_c]
        ax.bar(labels, values)
        ax.set_ylabel("Temperature [°C]")
        ax.grid(True, axis="y", alpha=0.25)
        self.temperature_plot.draw_idle()

        ax = self.load_plot.reset()
        import numpy as np
        angles = np.radians(result.load_distribution.angles_deg)
        loads = np.asarray(result.load_distribution.element_loads_n)
        if loads.size:
            width = 2 * np.pi / max(loads.size, 1) * 0.82
            ax.bar(angles, loads, width=width)
        ax.set_theta_zero_location("E")
        ax.set_title("Generic radial load distribution", pad=18)
        self.load_plot.draw_idle()

    def _export_report(self) -> None:
        if self.result is None:
            self._show_error("No result", "Run a calculation before exporting a report.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export HTML report", f"{self.case.case_name}_report.html", "HTML report (*.html)")
        if path:
            generate_html_report(self.case, self.result, path)
            self.status_label.setText(f"Report written to {Path(path).name}")

    def _export_history(self) -> None:
        if self.result is None:
            self._show_error("No result", "Run a calculation before exporting convergence history.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export convergence history", "convergence.csv", "CSV (*.csv)")
        if path:
            write_history_csv(self.result.history, path)
            self.status_label.setText(f"History written to {Path(path).name}")

    # ------------------------------------------------------------------ batch
    def _browse_batch(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select batch CSV", "", "CSV (*.csv)")
        if path:
            self.batch_path.setText(path)

    def _create_batch_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Create batch template", "batch_template.csv", "CSV (*.csv)")
        if path:
            create_batch_template(path)
            self.batch_path.setText(path)

    def _run_batch(self) -> None:
        path = self.batch_path.text().strip()
        if not path:
            self._show_error("No batch file", "Select or create a batch CSV.")
            return
        try:
            self.case = self._read_case_from_ui()
        except Exception as exc:
            self._show_error("Input validation failed", str(exc))
            return
        workers = self.batch_workers.value()
        backend = self.batch_backend.currentText()
        self.status_label.setText("Running batch operating map…")
        if backend.startswith("Numba"):
            worker = FunctionWorker(lambda: run_numba_dgbb_csv(copy.deepcopy(self.case), path))
        else:
            worker = FunctionWorker(lambda: run_batch_csv(copy.deepcopy(self.case), path, workers=workers))
        worker.signals.result.connect(self._batch_finished)
        worker.signals.error.connect(lambda text: self._worker_error("Batch failed", text))
        self.thread_pool.start(worker)

    def _batch_finished(self, result: Any) -> None:
        self.batch_result = result
        self.batch_model.set_dataframe(result.dataframe)
        self.batch_table.resizeColumnsToContents()
        self.status_label.setText(f"Batch complete: {len(result.dataframe)} cases, {result.failed_cases} failed")

    def _save_batch_result(self) -> None:
        if self.batch_result is None:
            self._show_error("No batch result", "Run a batch before saving results.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save batch results", "batch_results.csv", "CSV (*.csv)")
        if path:
            self.batch_result.dataframe.to_csv(path, index=False)
            self.status_label.setText(f"Batch results written to {Path(path).name}")

    # ------------------------------------------------------------------ calibration
    def _browse_calibration(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select calibration CSV", "", "CSV (*.csv)")
        if path:
            self.cal_path.setText(path)

    def _create_calibration_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Create calibration template", "calibration_template.csv", "CSV (*.csv)")
        if path:
            create_calibration_template(path)
            self.cal_path.setText(path)

    def _run_calibration(self) -> None:
        path = self.cal_path.text().strip()
        if not path:
            self._show_error("No calibration file", "Select or create a calibration CSV.")
            return
        selected = [key for key, check in self.cal_checks.items() if check.isChecked()]
        if not selected:
            self._show_error("No parameters", "Select at least one parameter to fit.")
            return
        try:
            self.case = self._read_case_from_ui()
        except Exception as exc:
            self._show_error("Input validation failed", str(exc))
            return
        self.status_label.setText("Fitting calibration profile…")
        worker = FunctionWorker(lambda: fit_calibration_csv(copy.deepcopy(self.case), path, selected))
        worker.signals.result.connect(self._calibration_finished)
        worker.signals.error.connect(lambda text: self._worker_error("Calibration failed", text))
        self.thread_pool.start(worker)

    def _calibration_finished(self, result: Any) -> None:
        self.calibration_result = result
        self.case.calibration = copy.deepcopy(result.profile)
        self.calibration_model.set_dataframe(result.predictions)
        p = result.profile
        self.calibration_summary.setPlainText(
            f"Status: {'success' if result.success else 'not converged'}\n"
            f"Message: {result.message}\n"
            f"Cost: {result.cost:.6g} | evaluations: {result.evaluations} | normalized RMS: {result.rms_normalized_residual:.6g}\n\n"
            f"rolling_scale = {p.rolling_scale:.6g}\n"
            f"sliding_scale = {p.sliding_scale:.6g}\n"
            f"seal_scale = {p.seal_scale:.6g}\n"
            f"drag_scale = {p.drag_scale:.6g}\n"
            f"heat_transfer_scale = {p.heat_transfer_scale:.6g}\n"
            f"installation_scale = {p.installation_scale:.6g}"
        )
        self.status_label.setText("Calibration profile applied to current case")

    def _save_calibration_profile(self) -> None:
        profile = self.case.calibration
        path, _ = QFileDialog.getSaveFileName(self, "Save calibration profile", "calibration_profile.json", "Calibration profile (*.json)")
        if path:
            save_calibration(profile, path)
            self.status_label.setText(f"Calibration profile written to {Path(path).name}")

    # ------------------------------------------------------------------ dialogs/settings
    def _worker_error(self, title: str, details: str) -> None:
        self._set_status_chip("FAILED", "warn")
        self.status_label.setText(title)
        short = details.strip().splitlines()[-1] if details.strip() else "Unknown error"
        self._show_error(title, short, details)

    def _show_error(self, title: str, text: str, details: str = "") -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(title)
        box.setText(text)
        if details:
            box.setDetailedText(details)
        box.exec()

    def _show_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Methodology, equations and sources")
        dialog.resize(860, 680)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(14)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(methodology_html(APP_VERSION))
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _restore_settings(self) -> None:
        geometry = self.settings.value("windowGeometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.settings.setValue("windowGeometry", self.saveGeometry())
        super().closeEvent(event)

    def _apply_stylesheet(self) -> None:
        """Style the window itself.

        ``main()`` already styles the whole QApplication; this keeps a window
        constructed directly (tests, screenshot drivers, embedding) looking
        right on its own.
        """
        try:
            icons = generate_icons()
        except OSError:
            icons = {}
        self.setStyleSheet(build_stylesheet(icons))



def main() -> None:
    # The offscreen platform can be set externally for automated tests/screenshots.
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("EngineeringTools")
    # Pins the light colour scheme, palette, font and style sheet. Without
    # this the Windows dark-mode palette bleeds through every widget the
    # style sheet does not explicitly name.
    apply_app_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
