from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd
from PyQt6.QtCore import QRect, QSize, QStringListModel, Qt, QUrl, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCursor, QDesktopServices, QGuiApplication, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .analysis_tables import (
    AnalysisTable,
    AnalysisTableBundle,
    build_analysis_table_bundle,
    certification_ranking_frame,
    single_table_bundle,
    write_analysis_workbook,
)
from .logic import (
    DatasetSpec,
    MetricDiagnostics,
    PreparedComparison,
    SensorDataError,
    apply_sample_shift,
    build_overlay_transforms,
    calculate_calibration_diagnostics,
    calculate_data_quality,
    calculate_event_timing_diagnostics,
    calculate_frequency_diagnostics,
    calculate_lag_diagnostics,
    calculate_scale_offset,
    calculate_metric_diagnostics,
    calculate_residual_diagnostics,
    calculate_rolling_diagnostics,
    calculate_sign_agreement,
    calculate_statistical_metrics,
    detect_main_comp_overlay_pairs,
    display_name_from_path,
    filter_time_range,
    load_dataset,
    prepare_comparison,
    reference_target_frames,
    update_metric_tolerances,
)
from .metric_help import metric_fallback_tooltip, metric_help_html
from .dash_plot_host import LocalResamplerDashHost
from .plots import (
    DEFAULT_LEGEND_POSITION,
    DEFAULT_HOVER_ANNOTATION_STYLE,
    DEFAULT_METRIC_KEYS,
    METRIC_GROUPS,
    apply_overlay_channel_visibility,
    build_certification_ranking_figure,
    build_metrics_figure,
    build_calibration_figure,
    build_data_quality_figure,
    build_events_figure,
    build_frequency_figure,
    build_lag_figure,
    build_overlay_figure,
    build_residual_figure,
    build_rolling_metrics_figure,
    build_scale_offset_figure,
    build_sign_agreement_plot_data,
    is_resampled_figure,
    hover_annotation_style_label,
    next_legend_position,
    next_hover_annotation_style,
    write_offline_plot_html,
)
from .resources import help_pdf_path
from .sign_agreement_view import SignAgreementView
from .table_views import (
    CollapsedPaneRail,
    OverlayResultsView,
    PlotTablePanel,
    SelectableTablesView,
    StandaloneTablePanel,
    SpreadsheetTableView,
    collapsed_pane_rail,
    pane_handle_button,
    pane_header,
)


PlotViewFactory = Callable[[], QWidget]
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGGER = logging.getLogger(__name__)
OVERLAY_TABLE_IDS = (
    "overlay_reference",
    "overlay_candidate_original",
    "overlay_candidate_scaled",
    "overlay_candidate_offset",
    "overlay_candidate_scaled_offset",
)


def _asset_icon(filename: str) -> QIcon:
    return QIcon(str(ASSETS_DIR / filename))


def _title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("TitleLabel")
    return label


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("MutedLabel")
    label.setWordWrap(True)
    return label


def _primary_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("variant", "primary")
    return button


def _panel() -> QFrame:
    frame = QFrame()
    frame.setObjectName("Panel")
    frame.setFrameShape(QFrame.Shape.NoFrame)
    return frame


class WebPlotView(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.web_view = None
        self._dash_host: LocalResamplerDashHost | None = None
        self._figure: Any | None = None
        self._needs_render = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.placeholder = QLabel("Plot will render after datasets are prepared.")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setObjectName("MutedLabel")
        layout.addWidget(self.placeholder)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_figure(self, figure: Any) -> None:
        self._figure = figure
        self._needs_render = True
        if self.isVisible():
            self.refresh_plot()

    def apply_trace_visibility_mask(self, mask: Sequence[bool]) -> None:
        if self._figure is None:
            return
        mask_tuple = tuple(bool(value) for value in mask)
        for trace, visible in zip(self._figure.data, mask_tuple):
            trace.visible = visible
        if self._dash_host is not None:
            self._dash_host.set_trace_visibility(mask_tuple)
        if self.web_view is None or self._needs_render:
            return
        mask_json = json.dumps(list(mask_tuple))
        script = f"""
(() => {{
  const mask = {mask_json};
  const root = document.getElementById("resampled-plot");
  const graph = (root && root.querySelector(".js-plotly-plot, .plotly-graph-div"))
    || (root && root.classList && root.classList.contains("js-plotly-plot") ? root : null)
    || document.querySelector(".js-plotly-plot, .plotly-graph-div");
  if (!graph || !window.Plotly) {{
    return false;
  }}
  const indices = mask.map((_value, index) => index);
  window.Plotly.restyle(graph, {{visible: mask}}, indices);
  return true;
}})();
"""
        self.web_view.page().runJavaScript(script)

    def refresh_plot(self) -> None:
        if self._figure is None or not self._needs_render:
            return
        started = perf_counter()
        trace_count = len(getattr(self._figure, "data", ()))
        self._ensure_web_view()
        if is_resampled_figure(self._figure):
            if self._dash_host is None:
                self._dash_host = LocalResamplerDashHost()
            self.web_view.setUrl(QUrl(self._dash_host.set_figure(self._figure)))
            render_path = "dash-resampler"
        else:
            temp_html_path = write_offline_plot_html(self._figure)
            self.web_view.setUrl(QUrl.fromLocalFile(temp_html_path))
            render_path = "offline-html"
        self._needs_render = False
        LOGGER.info("Plot handoff via %s took %.3fs (%d traces)", render_path, perf_counter() - started, trace_count)

    def force_refresh_plot(self) -> None:
        if self._figure is None:
            return
        self._needs_render = True
        self.refresh_plot()

    def clear(self) -> None:
        self._figure = None
        self._needs_render = False
        if self.web_view is not None:
            self.web_view.setHtml("<html><body></body></html>")

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.refresh_plot()

    def closeEvent(self, event: Any) -> None:
        if self._dash_host is not None:
            self._dash_host.stop()
        super().closeEvent(event)

    def _ensure_web_view(self) -> None:
        if self.web_view is not None:
            return
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        self.placeholder.hide()
        self.web_view = QWebEngineView(self)
        self.layout().addWidget(self.web_view)


class CurrentWidgetStack(QStackedWidget):
    def sizeHint(self) -> Any:
        widget = self.currentWidget()
        return widget.sizeHint() if widget is not None else super().sizeHint()

    def minimumSizeHint(self) -> Any:
        widget = self.currentWidget()
        return widget.minimumSizeHint() if widget is not None else super().minimumSizeHint()


class DetachedPlotWindow(QMainWindow):
    def __init__(self, title: str, plot_widget: QWidget, restore_callback: Callable[[], None]):
        super().__init__()
        self._restore_callback = restore_callback
        self._closing_for_restore = False
        self.setWindowTitle(title)
        self.resize(1100, 740)
        self.setCentralWidget(plot_widget)

    def close_for_restore(self) -> None:
        self._closing_for_restore = True
        self.close()

    def closeEvent(self, event: Any) -> None:
        if not self._closing_for_restore:
            self._restore_callback()
        super().closeEvent(event)


@dataclass
class DetachedPlotState:
    tab_widget: QWidget
    detached_widget: QWidget
    placeholder: QWidget
    window: DetachedPlotWindow
    title: str
    tooltip: str


class DetachedTableWindow(QMainWindow):
    def __init__(self, title: str, table_view: SpreadsheetTableView, close_callback: Callable[[], None]):
        super().__init__()
        self._close_callback = close_callback
        self._closing_for_restore = False
        self.setWindowTitle(title)
        self.resize(1000, 620)
        self.setCentralWidget(table_view)

    def close_for_restore(self) -> None:
        self._closing_for_restore = True
        self.close()

    def closeEvent(self, event: Any) -> None:
        if not self._closing_for_restore:
            self._close_callback()
        super().closeEvent(event)


@dataclass
class DetachedTableState:
    table_id: str
    table_view: SpreadsheetTableView
    window: DetachedTableWindow


@dataclass(frozen=True)
class ResultsSnapshot:
    reference_index: int
    selected_columns: tuple[str, ...]
    start_time: float
    end_time: float
    sign_deadband: float
    absolute_tolerance: float
    relative_tolerance_pct: float
    noise_floor: float
    selected_metric_keys: tuple[str, ...]
    hide_transforms: bool
    filter_overlay_to_sign_summary: bool
    overlay_metric_filter: "OverlayMetricFilterState"


@dataclass(frozen=True)
class OverlayMetricThresholdRule:
    metric_key: str
    operator: str
    value: float


@dataclass(frozen=True)
class OverlayMetricFilterState:
    thresholds: tuple[OverlayMetricThresholdRule, ...] = ()
    rank_metric_keys: tuple[str, ...] = ()
    rank_count: int = 0
    rank_direction: str = ""

    def enabled(self) -> bool:
        return bool(self.thresholds or self.ranking_enabled())

    def ranking_enabled(self) -> bool:
        return bool(self.rank_metric_keys and self.rank_count > 0 and self.rank_direction in ("Best", "Worst"))


@dataclass(frozen=True)
class FilteredResultsData:
    reference_df: pd.DataFrame
    target_df: pd.DataFrame
    reference_name: str
    target_name: str


@dataclass(frozen=True)
class StableResultsArtifacts:
    residual: Any
    lag: Any
    events: Any
    quality: Any
    calibration: Any
    frequency: Any
    scale_offset_metrics: list[dict[str, float | str]]
    scaled_only: pd.DataFrame
    offset_only: pd.DataFrame
    scaled_offset: pd.DataFrame


@dataclass(frozen=True)
class SignResultsArtifacts:
    sign_agreement: Any
    rolling: Any


@dataclass(frozen=True)
class MetricsResultsArtifacts:
    metrics: list[dict[str, float | str]]
    table_bundle: AnalysisTableBundle


HIGHER_IS_BETTER_METRICS = {
    "Max Correlation",
    "Pearson Correlation",
    "Coefficient of Determination",
    "Within Tolerance Abs (%)",
    "Within Tolerance Rel (%)",
    "Sign Agreement (%)",
    "Polarity Score",
    "Max Lag Correlation",
    "Calibration R^2",
    "Spectral Energy Ratio",
    "Certification Score",
}
CLOSER_TO_ZERO_METRICS = {
    "Mean Bias",
    "Calibration Offset",
    "Best Lag (samples)",
    "Best Lag (s)",
    "Lag at Max Correlation (samples)",
    "Time Shift (s)",
    "Dominant Freq Delta",
}
OPERATORS = ("<=", "<", ">=", ">")
RANK_DIRECTIONS = ("Best", "Worst")


def _finite_metric_value(row: dict[str, Any], metric_key: str) -> float | None:
    try:
        value = float(row.get(metric_key))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _passes_threshold(value: float | None, operator: str, limit: float) -> bool:
    if value is None:
        return False
    if operator == "<=":
        return value <= limit
    if operator == "<":
        return value < limit
    if operator == ">=":
        return value >= limit
    if operator == ">":
        return value > limit
    return False


def _metric_badness(value: float | None, metric_key: str) -> float | None:
    if value is None:
        return None
    if metric_key in HIGHER_IS_BETTER_METRICS:
        return -value
    if metric_key == "Calibration Slope":
        return abs(value - 1.0)
    if metric_key in CLOSER_TO_ZERO_METRICS:
        return abs(value)
    return value


def _rank_filtered_channels(
    channels: Sequence[str],
    metric_rows: dict[str, dict[str, Any]],
    state: OverlayMetricFilterState,
) -> tuple[str, ...]:
    if not state.ranking_enabled():
        return tuple(channels)
    totals = dict.fromkeys(channels, 0)
    invalid_counts = dict.fromkeys(channels, 0)
    order = {channel: index for index, channel in enumerate(channels)}
    for metric_key in state.rank_metric_keys:
        scored: list[tuple[float, str]] = []
        invalid: list[str] = []
        for channel in channels:
            badness = _metric_badness(_finite_metric_value(metric_rows[channel], metric_key), metric_key)
            if badness is None:
                invalid.append(channel)
            else:
                scored.append((badness, channel))
        scored.sort(key=lambda item: (item[0], order[item[1]]))
        worst_rank = len(scored) + len(invalid)
        for rank, (_score, channel) in enumerate(scored):
            totals[channel] += rank
        for channel in invalid:
            totals[channel] += worst_rank
            invalid_counts[channel] += 1
    if state.rank_direction == "Worst":
        ranked = sorted(channels, key=lambda channel: (invalid_counts[channel] > 0, -totals[channel], order[channel]))
    else:
        ranked = sorted(channels, key=lambda channel: (invalid_counts[channel] > 0, totals[channel], order[channel]))
    return tuple(ranked[: state.rank_count])


def metric_filtered_overlay_channels(
    selected_columns: Sequence[str],
    metrics: Sequence[dict[str, Any]],
    state: OverlayMetricFilterState,
) -> tuple[str, ...] | None:
    if not state.enabled():
        return None
    metric_rows = {str(row.get("Channel")): row for row in metrics}
    channels = [channel for channel in selected_columns if channel in metric_rows]
    for rule in state.thresholds:
        channels = [
            channel
            for channel in channels
            if _passes_threshold(_finite_metric_value(metric_rows[channel], rule.metric_key), rule.operator, rule.value)
        ]
    return _rank_filtered_channels(channels, metric_rows, state)


class LoadPage(QWidget):
    inputs_changed = pyqtSignal()

    OVERLAY_MODE = "overlay"
    SEPARATE_MODE = "separate"

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        layout.addWidget(_title("Choose Input"))
        layout.addWidget(
            _muted(
                "Choose one input workflow. SG Plotly HTML overlays are split into Main and Comp traces automatically; "
                "separate datasets can be CSV or SG Plotly HTML files. "
                "The first column or trace x-axis must be Time, and all sensor channels must be numeric."
            )
        )

        self.overlay_mode_button = QPushButton("Single SG Plotly overlay HTML")
        self.separate_mode_button = QPushButton("Two separate datasets")
        self.mode_button_group = QButtonGroup(self)
        self.mode_button_group.setExclusive(True)
        for button in [self.overlay_mode_button, self.separate_mode_button]:
            button.setCheckable(True)
            button.setProperty("modeButton", "true")
            self.mode_button_group.addButton(button)
        self.overlay_mode_button.clicked.connect(lambda _checked=False: self.set_input_mode(self.OVERLAY_MODE))
        self.separate_mode_button.clicked.connect(lambda _checked=False: self.set_input_mode(self.SEPARATE_MODE))
        self.overlay_mode_button.setChecked(True)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(self.overlay_mode_button)
        mode_row.addWidget(self.separate_mode_button)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        self.overlay_path_edit = QLineEdit()
        self.overlay_path_edit.setReadOnly(True)
        self.overlay_path_edit.textChanged.connect(self._overlay_path_changed)
        self.overlay_browse_button = QPushButton("Browse...")
        self.overlay_clear_button = QPushButton("Clear")
        self.overlay_browse_button.clicked.connect(self._choose_overlay_file)
        self.overlay_clear_button.clicked.connect(self.clear_overlay_input)

        self.path1_edit = QLineEdit()
        self.path1_edit.setReadOnly(True)
        self.path2_edit = QLineEdit()
        self.path2_edit.setReadOnly(True)
        self.name1_edit = QLineEdit()
        self.name1_edit.setPlaceholderText("Dataset 1")
        self.name2_edit = QLineEdit()
        self.name2_edit.setPlaceholderText("Dataset 2")
        for edit in [self.path1_edit, self.path2_edit, self.name1_edit, self.name2_edit]:
            edit.textChanged.connect(self.inputs_changed.emit)

        self.browse1_button = QPushButton("Browse...")
        self.browse2_button = QPushButton("Browse...")
        self.browse1_button.clicked.connect(lambda: self._choose_file(self.path1_edit, self.name1_edit, "Dataset 1"))
        self.browse2_button.clicked.connect(lambda: self._choose_file(self.path2_edit, self.name2_edit, "Dataset 2"))

        self.overlay_panel = self._build_overlay_panel()
        self.separate_panel = self._build_separate_panel()
        self.input_stack = CurrentWidgetStack()
        self.input_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.input_stack.addWidget(self.overlay_panel)
        self.input_stack.addWidget(self.separate_panel)
        layout.addWidget(self.input_stack, 0, Qt.AlignmentFlag.AlignTop)

        summaries = QHBoxLayout()
        self.summary1 = self._summary_card("Reference: Main traces", "Select one SG Plotly HTML overlay file.")
        self.summary2 = self._summary_card("Candidate: Comp traces", "Waiting for overlay file.")
        summaries.addWidget(self.summary1)
        summaries.addWidget(self.summary2)
        layout.addLayout(summaries)
        layout.addStretch(1)
        self._sync_input_mode()

    def _build_overlay_panel(self) -> QFrame:
        panel = _panel()
        panel.setProperty("inputPanel", "overlay")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 16, 16, 16)
        panel_layout.setSpacing(10)
        panel_layout.addWidget(_section_title("Single SG Plotly overlay HTML"))
        panel_layout.addWidget(_muted("Use one exported Plotly HTML file containing matched Main: and Comp: traces."))

        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        input_row.addWidget(self.overlay_path_edit, 1)
        input_row.addWidget(self.overlay_browse_button)
        input_row.addWidget(self.overlay_clear_button)
        panel_layout.addLayout(input_row)
        return panel

    def _build_separate_panel(self) -> QFrame:
        panel = _panel()
        panel.setProperty("inputPanel", "separate")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        form_layout = QGridLayout(panel)
        form_layout.setContentsMargins(16, 16, 16, 16)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(10)
        form_layout.addWidget(_section_title("Two separate datasets"), 0, 0, 1, 3)
        form_layout.addWidget(_muted("Load a reference dataset and a candidate dataset from CSV or SG Plotly HTML files."), 1, 0, 1, 3)
        form_layout.addWidget(QLabel("Reference-side input"), 2, 0)
        form_layout.addWidget(self.path1_edit, 2, 1)
        form_layout.addWidget(self.browse1_button, 2, 2)
        form_layout.addWidget(QLabel("Display name"), 3, 0)
        form_layout.addWidget(self.name1_edit, 3, 1, 1, 2)
        form_layout.addWidget(QLabel("Candidate-side input"), 4, 0)
        form_layout.addWidget(self.path2_edit, 4, 1)
        form_layout.addWidget(self.browse2_button, 4, 2)
        form_layout.addWidget(QLabel("Display name"), 5, 0)
        form_layout.addWidget(self.name2_edit, 5, 1, 1, 2)
        form_layout.setColumnStretch(1, 1)
        return panel

    def _summary_card(self, title: str, detail: str) -> QLabel:
        label = QLabel(f"{title}\n{detail}")
        label.setObjectName("SummaryCard")
        label.setMinimumHeight(72)
        label.setWordWrap(True)
        label.setContentsMargins(12, 10, 12, 10)
        return label

    def _choose_file(self, path_edit: QLineEdit, name_edit: QLineEdit, fallback: str) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV or SG Plotly HTML File",
            "",
            "Sensor Data Files (*.csv *.html *.htm);;CSV Files (*.csv);;HTML Files (*.html *.htm)",
        )
        if file_path:
            path_edit.setText(file_path)
            if not name_edit.text().strip():
                name_edit.setText(Path(file_path).stem or fallback)

    def _choose_overlay_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SG Plotly HTML Overlay",
            "",
            "HTML Files (*.html *.htm)",
        )
        if file_path:
            self.overlay_path_edit.setText(file_path)

    def clear_overlay_input(self) -> None:
        self.overlay_path_edit.clear()

    def input_mode(self) -> str:
        if self.separate_mode_button.isChecked():
            return self.SEPARATE_MODE
        return self.OVERLAY_MODE

    def set_input_mode(self, mode: str) -> None:
        if mode not in {self.OVERLAY_MODE, self.SEPARATE_MODE}:
            raise ValueError(f"Unknown input mode: {mode}")
        self.overlay_mode_button.setChecked(mode == self.OVERLAY_MODE)
        self.separate_mode_button.setChecked(mode == self.SEPARATE_MODE)
        self._sync_input_mode()
        self.inputs_changed.emit()

    def overlay_input(self) -> str:
        return self.overlay_path_edit.text().strip()

    def _overlay_path_changed(self) -> None:
        self._sync_input_mode()
        self.inputs_changed.emit()

    def _sync_input_mode(self) -> None:
        if self.input_mode() == self.OVERLAY_MODE:
            active_panel = self.overlay_panel
        else:
            active_panel = self.separate_panel
        self.input_stack.setCurrentWidget(active_panel)
        self.input_stack.setMaximumHeight(active_panel.sizeHint().height())
        self.input_stack.updateGeometry()
        self.overlay_clear_button.setEnabled(bool(self.overlay_input()))

    def dataset_inputs(self) -> tuple[str, str, str, str]:
        return (
            self.path1_edit.text().strip(),
            self.name1_edit.text().strip(),
            self.path2_edit.text().strip(),
            self.name2_edit.text().strip(),
        )

    def set_summaries(self, dataset1: Any, dataset2: Any) -> None:
        self.summary1.setText(self._summary_text(dataset1))
        self.summary2.setText(self._summary_text(dataset2))

    def set_dataset_summary(self, dataset_number: int, dataset: Any) -> None:
        summary = self.summary1 if dataset_number == 1 else self.summary2
        summary.setText(self._summary_text(dataset))

    def set_summary_status(self, dataset_number: int, title: str, detail: str) -> None:
        summary = self.summary1 if dataset_number == 1 else self.summary2
        summary.setText(f"{title}\n{detail}")

    def set_overlay_summaries(self, dataset: Any, pairs: Any) -> None:
        ignored = len(pairs.ignored_columns)
        ignored_text = f" | {ignored} ignored" if ignored else ""
        self.summary1.setText(
            f"Reference: Main traces\n"
            f"{dataset.display_name} | {dataset.row_count:,} rows | {len(pairs.dataset1_columns)} matched pairs{ignored_text}\n"
            f"Time {dataset.time_min:g} to {dataset.time_max:g}"
        )
        self.summary2.setText(
            f"Candidate: Comp traces\n"
            f"{dataset.display_name} | {dataset.row_count:,} rows | {len(pairs.dataset2_columns)} matched pairs{ignored_text}\n"
            f"Time {dataset.time_min:g} to {dataset.time_max:g}"
        )

    def _summary_text(self, dataset: Any) -> str:
        return (
            f"{dataset.display_name}\n"
            f"{dataset.row_count:,} rows | {len(dataset.channels)} channels\n"
            f"Time {dataset.time_min:g} to {dataset.time_max:g}"
        )


class MatchPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        layout.addWidget(_title("Match Channels"))
        layout.addWidget(
            _muted(
                "Reorder or remove channels so each row pairs the same physical signal "
                "from both datasets."
            )
        )

        body = QHBoxLayout()
        left_panel, self.left_list, self.left_count = self._list_panel("Dataset 1 Channels")
        right_panel, self.right_list, self.right_count = self._list_panel("Dataset 2 Channels")
        controls = self._control_panel()
        body.addWidget(left_panel, 1)
        body.addWidget(controls)
        body.addWidget(right_panel, 1)
        layout.addLayout(body, 1)

    def _list_panel(self, title: str) -> tuple[QFrame, QListWidget, QLabel]:
        frame = _panel()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(_section_title(title))
        count_label = _muted("0 channels")
        layout.addWidget(count_label)
        list_widget = QListWidget()
        list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        list_widget.model().rowsInserted.connect(self.update_counts)
        list_widget.model().rowsRemoved.connect(self.update_counts)
        layout.addWidget(list_widget, 1)
        return frame, list_widget, count_label

    def _control_panel(self) -> QFrame:
        frame = _panel()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(8)
        layout.addWidget(_section_title("Edit Lists"))
        for title, list_widget in [("Dataset 1", self.left_list), ("Dataset 2", self.right_list)]:
            layout.addWidget(_muted(title))
            buttons = QHBoxLayout()
            buttons.setSpacing(6)
            for icon, tooltip, handler in [
                (QStyle.StandardPixmap.SP_ArrowUp, f"Move selected {title} channels up", lambda lw=list_widget: self._move_up(lw)),
                (QStyle.StandardPixmap.SP_ArrowDown, f"Move selected {title} channels down", lambda lw=list_widget: self._move_down(lw)),
                (QStyle.StandardPixmap.SP_DialogCloseButton, f"Remove selected {title} channels", lambda lw=list_widget: self._remove_selected(lw)),
            ]:
                button = self._icon_button(icon, tooltip)
                button.clicked.connect(handler)
                buttons.addWidget(button)
            layout.addLayout(buttons)
        layout.addStretch(1)
        return frame

    def _icon_button(self, standard_icon: QStyle.StandardPixmap, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setIcon(self.style().standardIcon(standard_icon))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(38, 34)
        button.setProperty("iconButton", "true")
        return button

    def set_columns(self, dataset1_columns: list[str], dataset2_columns: list[str]) -> None:
        self.left_list.clear()
        self.right_list.clear()
        self.left_list.addItems(dataset1_columns)
        self.right_list.addItems(dataset2_columns)
        self.update_counts()

    def columns(self) -> tuple[list[str], list[str]]:
        return (
            [self.left_list.item(index).text() for index in range(self.left_list.count())],
            [self.right_list.item(index).text() for index in range(self.right_list.count())],
        )

    def update_counts(self) -> None:
        self.left_count.setText(f"{self.left_list.count()} channels")
        self.right_count.setText(f"{self.right_list.count()} channels")

    def _move_up(self, list_widget: QListWidget) -> None:
        selected_indices = sorted(list_widget.row(item) for item in list_widget.selectedItems())
        if not selected_indices or min(selected_indices) == 0:
            return
        for index in selected_indices:
            item = list_widget.takeItem(index)
            list_widget.insertItem(index - 1, item)
        for index in selected_indices:
            list_widget.item(index - 1).setSelected(True)

    def _move_down(self, list_widget: QListWidget) -> None:
        selected_indices = sorted((list_widget.row(item) for item in list_widget.selectedItems()), reverse=True)
        if not selected_indices or max(selected_indices) == list_widget.count() - 1:
            return
        for index in selected_indices:
            item = list_widget.takeItem(index)
            list_widget.insertItem(index + 1, item)
        for index in selected_indices:
            list_widget.item(index + 1).setSelected(True)

    def _remove_selected(self, list_widget: QListWidget) -> None:
        for item in list_widget.selectedItems():
            list_widget.takeItem(list_widget.row(item))


class NamePage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        layout.addWidget(_title("Name Channels"))
        layout.addWidget(
            _muted(
                "Choose the final channel names used by every plot and metric. "
                "Names must be non-empty and unique."
            )
        )

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Dataset 1", "Dataset 2", "Final Name"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        controls = QHBoxLayout()
        self.use_left_button = QPushButton("Use Dataset 1 Names")
        self.use_right_button = QPushButton("Use Dataset 2 Names")
        self.use_left_button.clicked.connect(lambda: self._use_column(0))
        self.use_right_button.clicked.connect(lambda: self._use_column(1))
        controls.addWidget(self.use_left_button)
        controls.addWidget(self.use_right_button)
        controls.addStretch(1)
        layout.addLayout(controls)

    def set_pairs(
        self,
        dataset1_columns: list[str],
        dataset2_columns: list[str],
        final_names: Sequence[str] | None = None,
    ) -> None:
        self.table.setRowCount(len(dataset1_columns))
        for row, (left, right) in enumerate(zip(dataset1_columns, dataset2_columns)):
            left_item = QTableWidgetItem(left)
            left_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            right_item = QTableWidgetItem(right)
            right_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            final_name = final_names[row] if final_names is not None and row < len(final_names) else left
            final_item = QTableWidgetItem(final_name)
            self.table.setItem(row, 0, left_item)
            self.table.setItem(row, 1, right_item)
            self.table.setItem(row, 2, final_item)

    def final_names(self) -> list[str]:
        names: list[str] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            names.append(item.text() if item is not None else "")
        return names

    def _use_column(self, source_column: int) -> None:
        for row in range(self.table.rowCount()):
            source = self.table.item(row, source_column)
            self.table.setItem(row, 2, QTableWidgetItem(source.text() if source else ""))


class ConfigPage(QWidget):
    reference_changed = pyqtSignal()
    sync_requested = pyqtSignal()
    revert_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        layout.addWidget(_title("Configure Alignment"))
        layout.addWidget(
            _muted(
                "Select the reference dataset, confirm the analysis time window, and optionally "
                "shift one aligned dataset before reviewing results."
            )
        )

        form = _panel()
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(16, 16, 16, 16)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)

        self.reference_combo = QComboBox()
        self.reference_combo.currentIndexChanged.connect(self.reference_changed)
        self.start_spin = self._time_spinbox()
        self.end_spin = self._time_spinbox()
        self.sync_checkbox = QCheckBox("Enable manual time synchronization")
        self.sync_checkbox.stateChanged.connect(self._toggle_sync)
        self.sync_time1 = self._time_spinbox()
        self.sync_time2 = self._time_spinbox()
        self.shift_combo = QComboBox()
        self.apply_button = _primary_button("Apply Shift")
        self.revert_button = QPushButton("Revert Shift")
        self.apply_button.clicked.connect(self.sync_requested)
        self.revert_button.clicked.connect(self.revert_requested)

        form_layout.addWidget(QLabel("Reference dataset"), 0, 0)
        form_layout.addWidget(self.reference_combo, 0, 1)
        form_layout.addWidget(QLabel("Analysis start"), 1, 0)
        form_layout.addWidget(self.start_spin, 1, 1)
        form_layout.addWidget(QLabel("Analysis end"), 1, 2)
        form_layout.addWidget(self.end_spin, 1, 3)
        form_layout.addWidget(self.sync_checkbox, 2, 0, 1, 4)
        form_layout.addWidget(QLabel("Reference time 1"), 3, 0)
        form_layout.addWidget(self.sync_time1, 3, 1)
        form_layout.addWidget(QLabel("Reference time 2"), 3, 2)
        form_layout.addWidget(self.sync_time2, 3, 3)
        form_layout.addWidget(QLabel("Dataset to shift"), 4, 0)
        form_layout.addWidget(self.shift_combo, 4, 1)
        form_layout.addWidget(self.apply_button, 4, 2)
        form_layout.addWidget(self.revert_button, 4, 3)
        form_layout.setColumnStretch(1, 1)
        form_layout.setColumnStretch(3, 1)
        layout.addWidget(form)

        self.status_label = QLabel("Prepare the comparison to configure alignment.")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        self._toggle_sync()

    def _time_spinbox(self) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setDecimals(3)
        spinbox.setRange(0, 999999999)
        spinbox.setSingleStep(0.1)
        return spinbox

    def set_ready(self, prepared: PreparedComparison) -> None:
        self.reference_combo.blockSignals(True)
        self.shift_combo.blockSignals(True)
        self.reference_combo.clear()
        self.reference_combo.addItems([prepared.dataset1.display_name, prepared.dataset2.display_name])
        self.shift_combo.clear()
        self.shift_combo.addItems([prepared.dataset1.display_name, prepared.dataset2.display_name])
        self.reference_combo.setCurrentIndex(0)
        self.shift_combo.setCurrentIndex(1 if prepared.dataset2.display_name else 0)
        self.reference_combo.blockSignals(False)
        self.shift_combo.blockSignals(False)
        for spinbox in [self.start_spin, self.end_spin, self.sync_time1, self.sync_time2]:
            spinbox.blockSignals(True)
            spinbox.setRange(prepared.time_min, prepared.time_max)
            spinbox.blockSignals(False)
        self.start_spin.setValue(prepared.time_min)
        self.end_spin.setValue(prepared.time_max)
        self.sync_time1.setValue(prepared.time_min)
        self.sync_time2.setValue(prepared.time_min)
        self.status_label.setText(
            f"Aligned {len(prepared.channels)} channels from time {prepared.time_min:g} to {prepared.time_max:g}."
        )

    def analysis_range(self) -> tuple[float, float]:
        return self.start_spin.value(), self.end_spin.value()

    def reference_index(self) -> int:
        return self.reference_combo.currentIndex()

    def shift_seconds(self) -> float:
        return self.sync_time1.value() - self.sync_time2.value()

    def shift_target_index(self) -> int:
        return self.shift_combo.currentIndex()

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _toggle_sync(self) -> None:
        enabled = self.sync_checkbox.isChecked()
        for widget in [self.sync_time1, self.sync_time2, self.shift_combo, self.apply_button, self.revert_button]:
            widget.setEnabled(enabled or widget is self.revert_button)


class MetricHelpPopover(QFrame):
    pin_changed = pyqtSignal(bool)

    WIDTH = 430
    HEIGHT = 360
    OFFSET = 10

    def __init__(self, parent: QWidget | None = None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("MetricHelpPopover")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._html = ""
        self._pinned = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.browser = QTextBrowser()
        self.browser.setObjectName("MetricHelpText")
        self.browser.setOpenExternalLinks(False)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.browser)
        self.pin_button = QToolButton(self)
        self.pin_button.setObjectName("MetricHelpPinButton")
        self.pin_button.setIcon(_asset_icon("pin.svg"))
        self.pin_button.setIconSize(QSize(15, 15))
        self.pin_button.setFixedSize(28, 28)
        self.pin_button.setCheckable(True)
        self.pin_button.toggled.connect(self._set_pinned_from_button)
        self._sync_pin_button()

    def show_metric(self, metric_key: str, menu_rect: QRect, preferred_y: int) -> None:
        self._html = metric_help_html(metric_key)
        self.browser.setHtml(self._html)
        self._move_near(menu_rect, preferred_y)
        self.show()
        self.raise_()
        self.pin_button.raise_()

    def current_html(self) -> str:
        return self._html

    def is_pinned(self) -> bool:
        return self._pinned

    def set_pinned(self, pinned: bool) -> None:
        pinned = bool(pinned)
        if self.pin_button.isChecked() != pinned:
            self.pin_button.setChecked(pinned)
            return
        self._set_pinned_from_button(pinned)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.set_pinned(False)
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event: Any) -> None:
        if not self._pinned:
            self.hide()
        super().focusOutEvent(event)

    def resizeEvent(self, event: Any) -> None:
        self._position_pin_button()
        super().resizeEvent(event)

    def _move_near(self, menu_rect: QRect, preferred_y: int) -> None:
        screen = QGuiApplication.screenAt(menu_rect.center()) or QGuiApplication.primaryScreen()
        x = menu_rect.right() + self.OFFSET
        y = preferred_y
        if screen is None:
            self.move(x, y)
            return

        bounds = screen.availableGeometry()
        right_x = menu_rect.right() + self.OFFSET
        left_x = menu_rect.left() - self.width() - self.OFFSET
        if right_x + self.width() <= bounds.right():
            x = right_x
        elif left_x >= bounds.left():
            x = left_x
        else:
            right_space = bounds.right() - menu_rect.right()
            left_space = menu_rect.left() - bounds.left()
            x = bounds.right() - self.width() if right_space >= left_space else bounds.left()
        if y + self.height() > bounds.bottom():
            y = bounds.bottom() - self.height()

        max_x = max(bounds.left(), bounds.right() - self.width())
        max_y = max(bounds.top(), bounds.bottom() - self.height())
        x = max(bounds.left(), min(x, max_x))
        y = max(bounds.top(), min(y, max_y))
        self.move(x, y)
        self._position_pin_button()

    def _position_pin_button(self) -> None:
        self.pin_button.move(self.width() - self.pin_button.width() - 16, 10)
        self.pin_button.raise_()

    def _set_pinned_from_button(self, pinned: bool) -> None:
        pinned = bool(pinned)
        if self._pinned == pinned:
            self._sync_pin_button()
            return
        self._pinned = pinned
        self._sync_pin_button()
        self.pin_changed.emit(self._pinned)

    def _sync_pin_button(self) -> None:
        tooltip = "Unpin metric help" if self._pinned else "Keep metric help open"
        accessible_name = "Unpin Metric Help" if self._pinned else "Pin Metric Help"
        self.pin_button.setToolTip(tooltip)
        self.pin_button.setAccessibleName(accessible_name)
        self.pin_button.setProperty("pinned", self._pinned)
        self.pin_button.style().unpolish(self.pin_button)
        self.pin_button.style().polish(self.pin_button)


class MasterExportDialog(QDialog):
    CURRENT_SCOPE = "current"
    FULL_SCOPE = "full"

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Export Master Workbook")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(_section_title("Master Workbook Scope"))
        layout.addWidget(_muted("Choose which data scope should be recalculated and written to the workbook."))
        self.current_radio = QRadioButton("Current analysis view")
        self.current_radio.setToolTip("Use the current reference side, selected channels, selected time range, and sign deadband.")
        self.full_radio = QRadioButton("Full aligned data")
        self.full_radio.setToolTip("Use all prepared channels and the full aligned time range with the current reference side and sign deadband.")
        self.current_radio.setChecked(True)
        layout.addWidget(self.current_radio)
        layout.addWidget(self.full_radio)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_scope(self) -> str:
        return self.FULL_SCOPE if self.full_radio.isChecked() else self.CURRENT_SCOPE


class OverlayMetricFilterDialog(QDialog):
    def __init__(
        self,
        state: OverlayMetricFilterState,
        metric_keys: Sequence[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Overlay Metric Filter")
        self.metric_keys = list(metric_keys)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(_section_title("Threshold rules"))
        layout.addWidget(_muted("Channels must pass every threshold rule before optional ranking is applied."))

        self.threshold_table = QTableWidget(0, 3)
        self.threshold_table.setHorizontalHeaderLabels(["Metric", "Operator", "Value"])
        self.threshold_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.threshold_table.verticalHeader().hide()
        self.threshold_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.threshold_table)

        threshold_buttons = QHBoxLayout()
        add_rule = QPushButton("Add Rule")
        add_rule.clicked.connect(lambda _checked=False: self._add_threshold_row())
        remove_rule = QPushButton("Remove Selected")
        remove_rule.clicked.connect(self._remove_selected_threshold_rows)
        threshold_buttons.addWidget(add_rule)
        threshold_buttons.addWidget(remove_rule)
        threshold_buttons.addStretch(1)
        layout.addLayout(threshold_buttons)
        for rule in state.thresholds:
            self._add_threshold_row(rule)

        layout.addWidget(_section_title("Ranking"))
        self.rank_enabled_checkbox = QCheckBox("Apply ranking after thresholds")
        self.rank_enabled_checkbox.setChecked(state.ranking_enabled())
        self.rank_enabled_checkbox.toggled.connect(self._sync_rank_controls)
        layout.addWidget(self.rank_enabled_checkbox)

        rank_layout = QGridLayout()
        rank_layout.addWidget(QLabel("Metrics"), 0, 0, Qt.AlignmentFlag.AlignTop)
        self.rank_metrics_list = QListWidget()
        for metric_key in self.metric_keys:
            self.rank_metrics_list.addItem(metric_key)
            item = self.rank_metrics_list.item(self.rank_metrics_list.count() - 1)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if metric_key in state.rank_metric_keys else Qt.CheckState.Unchecked
            )
        rank_layout.addWidget(self.rank_metrics_list, 0, 1, 1, 3)

        self.rank_count_spin = QSpinBox()
        self.rank_count_spin.setRange(1, 999)
        self.rank_count_spin.setValue(max(1, state.rank_count or 5))
        self.best_radio = QRadioButton("Best")
        self.worst_radio = QRadioButton("Worst")
        if state.rank_direction == "Best":
            self.best_radio.setChecked(True)
        elif state.rank_direction == "Worst":
            self.worst_radio.setChecked(True)
        rank_layout.addWidget(QLabel("Keep"), 1, 0)
        rank_layout.addWidget(self.rank_count_spin, 1, 1)
        rank_layout.addWidget(self.best_radio, 1, 2)
        rank_layout.addWidget(self.worst_radio, 1, 3)
        layout.addLayout(rank_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._sync_rank_controls()

    def _add_threshold_row(self, rule: OverlayMetricThresholdRule | None = None) -> None:
        row = self.threshold_table.rowCount()
        self.threshold_table.insertRow(row)
        metric_combo = QComboBox()
        metric_combo.addItems(self.metric_keys)
        if rule is not None and rule.metric_key in self.metric_keys:
            metric_combo.setCurrentText(rule.metric_key)
        operator_combo = QComboBox()
        operator_combo.addItems(OPERATORS)
        if rule is not None and rule.operator in OPERATORS:
            operator_combo.setCurrentText(rule.operator)
        value_spin = QDoubleSpinBox()
        value_spin.setDecimals(6)
        value_spin.setRange(-1.0e12, 1.0e12)
        value_spin.setValue(0.0 if rule is None else rule.value)
        self.threshold_table.setCellWidget(row, 0, metric_combo)
        self.threshold_table.setCellWidget(row, 1, operator_combo)
        self.threshold_table.setCellWidget(row, 2, value_spin)

    def _remove_selected_threshold_rows(self) -> None:
        rows = sorted({index.row() for index in self.threshold_table.selectedIndexes()}, reverse=True)
        if not rows and self.threshold_table.currentRow() >= 0:
            rows = [self.threshold_table.currentRow()]
        for row in rows:
            self.threshold_table.removeRow(row)

    def _sync_rank_controls(self) -> None:
        enabled = self.rank_enabled_checkbox.isChecked()
        for widget in (self.rank_metrics_list, self.rank_count_spin, self.best_radio, self.worst_radio):
            widget.setEnabled(enabled)

    def selected_state(self) -> OverlayMetricFilterState:
        thresholds: list[OverlayMetricThresholdRule] = []
        for row in range(self.threshold_table.rowCount()):
            metric_combo = self.threshold_table.cellWidget(row, 0)
            operator_combo = self.threshold_table.cellWidget(row, 1)
            value_spin = self.threshold_table.cellWidget(row, 2)
            if not isinstance(metric_combo, QComboBox) or not isinstance(operator_combo, QComboBox):
                continue
            if not isinstance(value_spin, QDoubleSpinBox):
                continue
            thresholds.append(
                OverlayMetricThresholdRule(
                    metric_key=metric_combo.currentText(),
                    operator=operator_combo.currentText(),
                    value=value_spin.value(),
                )
            )
        rank_metric_keys: tuple[str, ...] = ()
        rank_count = 0
        rank_direction = ""
        if self.rank_enabled_checkbox.isChecked():
            rank_metric_keys = tuple(
                self.rank_metrics_list.item(index).text()
                for index in range(self.rank_metrics_list.count())
                if self.rank_metrics_list.item(index).checkState() == Qt.CheckState.Checked
            )
            rank_count = self.rank_count_spin.value()
            rank_direction = "Best" if self.best_radio.isChecked() else "Worst" if self.worst_radio.isChecked() else ""
        return OverlayMetricFilterState(
            thresholds=tuple(thresholds),
            rank_metric_keys=rank_metric_keys,
            rank_count=rank_count,
            rank_direction=rank_direction,
        )

    def accept(self) -> None:
        state = self.selected_state()
        if self.rank_enabled_checkbox.isChecked() and not state.rank_metric_keys:
            QMessageBox.warning(self, "Overlay Filter", "Select at least one ranking metric.")
            return
        if self.rank_enabled_checkbox.isChecked() and state.rank_direction not in RANK_DIRECTIONS:
            QMessageBox.warning(self, "Overlay Filter", "Choose Best or Worst ranking.")
            return
        super().accept()


class ResultsPage(QWidget):
    changed = pyqtSignal()
    certification_display_changed = pyqtSignal()
    update_requested = pyqtSignal()
    help_requested = pyqtSignal()
    export_current_requested = pyqtSignal()
    export_master_requested = pyqtSignal()
    CHANNELS_EXPANDED_MIN_WIDTH = 220
    CHANNELS_EXPANDED_MAX_WIDTH = 420
    CHANNELS_DEFAULT_WIDTH = 260
    COLLAPSED_RAIL_WIDTH = CollapsedPaneRail.EDGE_REVEAL_WIDTH
    COLLAPSED_HANDLE_WIDTH = CollapsedPaneRail.HANDLE_WIDTH

    def __init__(self, plot_view_factory: PlotViewFactory):
        super().__init__()
        self._plot_view_factory = plot_view_factory
        self.metric_actions: dict[str, QAction] = {}
        self.metric_action_menus: dict[str, QMenu] = {}
        self._detached_plots: dict[int, DetachedPlotState] = {}
        self._detached_tables: dict[str, DetachedTableState] = {}
        self._detach_icon = _asset_icon("external-link.svg")
        self._restore_icon = _asset_icon("minimize-2.svg")
        self.metric_help_popover = MetricHelpPopover(self)
        self.metric_help_popover.pin_changed.connect(self._handle_metric_help_pin_changed)
        self.metric_menu: QMenu | None = None
        self._last_metric_menu_rect = QRect()
        self._overlay_metric_filter_state = OverlayMetricFilterState()
        self._certification_max_labels = 12
        self.channels_panel_collapsed = False
        self._channels_expanded_width = self.CHANNELS_DEFAULT_WIDTH
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        toolbar = _panel()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        self.reference_combo = QComboBox()
        self.reference_combo.currentIndexChanged.connect(self.changed)
        self.start_spin = self._time_spinbox()
        self.end_spin = self._time_spinbox()
        self.start_spin.valueChanged.connect(self.changed)
        self.end_spin.valueChanged.connect(self.changed)
        self.sign_deadband_spin = self._deadband_spinbox()
        self.sign_deadband_spin.valueChanged.connect(self.changed)
        self.abs_tolerance_spin = self._absolute_tolerance_spinbox()
        self.abs_tolerance_spin.valueChanged.connect(self.changed)
        self.rel_tolerance_spin = self._relative_tolerance_spinbox()
        self.rel_tolerance_spin.valueChanged.connect(self.changed)
        self.noise_floor_spin = self._noise_floor_spinbox()
        self.noise_floor_spin.valueChanged.connect(self.changed)
        self.hide_transforms_checkbox = QCheckBox("Hide transformed traces")
        self.hide_transforms_checkbox.setToolTip("Hide scaled, offset-only, and scaled+offset traces in the overlay plot.")
        self.hide_transforms_checkbox.setChecked(True)
        self.hide_transforms_checkbox.stateChanged.connect(self.changed)
        self.filter_overlay_to_sign_summary_checkbox = QCheckBox("Filter overlay to Sign Summary")
        self.filter_overlay_to_sign_summary_checkbox.setToolTip(
            "Show only Overlay channels currently passing the Sign Agreement Channel Summary filter."
        )
        self.filter_overlay_to_sign_summary_checkbox.stateChanged.connect(self.changed)
        self.metric_button = QPushButton("Metrics")
        self.metric_button.setToolTip("Choose which scalar metrics appear in the Statistical Metrics plot.")
        self.metric_button.setMenu(self._build_metric_menu())
        self.overlay_filter_button = QPushButton("Overlay Filter...")
        self.overlay_filter_button.setToolTip("Filter overlay channels by statistical metric thresholds and ranking.")
        self.overlay_filter_button.clicked.connect(self._configure_overlay_metric_filter)
        self.update_button = _primary_button("Update Data & Plots")
        self.update_button.setToolTip("Refresh tables and plots using the current Analyze Results settings.")
        self.update_button.setAccessibleName("Update Data and Plots")
        self.update_button.setEnabled(False)
        self.update_button.clicked.connect(lambda _checked=False: self.update_requested.emit())
        self.export_button = QPushButton()
        self.export_button.setIcon(_asset_icon("file-spreadsheet.svg"))
        self.export_button.setIconSize(QSize(18, 18))
        self.export_button.setFixedSize(38, 34)
        self.export_button.setProperty("iconButton", "true")
        self.export_button.setToolTip("Export the current table or a master workbook with all generated analysis tables.")
        self.export_button.setAccessibleName("Export Excel")
        self.export_button.setMenu(self._build_export_menu())
        self.detach_button = QPushButton()
        self.detach_button.setIcon(self._detach_icon)
        self.detach_button.setIconSize(QSize(18, 18))
        self.detach_button.setFixedSize(38, 34)
        self.detach_button.setProperty("iconButton", "true")
        self.detach_button.setToolTip("Open the current plot in a separate window.")
        self.detach_button.setAccessibleName("Detach Plot")
        self.detach_button.clicked.connect(self.toggle_current_plot_detached)
        self.detach_table_button = QPushButton()
        self.detach_table_button.setIcon(self._detach_icon)
        self.detach_table_button.setIconSize(QSize(18, 18))
        self.detach_table_button.setFixedSize(38, 34)
        self.detach_table_button.setProperty("iconButton", "true")
        self.detach_table_button.setToolTip("Open the current table in a separate window.")
        self.detach_table_button.setAccessibleName("Detach Table")
        self.detach_table_button.clicked.connect(self.toggle_current_table_detached)
        self.help_button = QPushButton("Metrics Help")
        self.help_button.setToolTip("Open formulas and interpretation notes for statistical and engineering diagnostics.")
        self.help_button.clicked.connect(self.help_requested)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(_title("Analyze Results"))
        noise_floor_label = QLabel("Noise floor")
        noise_floor_label.setToolTip(
            "Samples where both channels are at or below this magnitude are treated as negligible "
            "and counted as within tolerance. Leave at 0 to disable."
        )
        title_row.addWidget(noise_floor_label)
        title_row.addWidget(self.noise_floor_spin)
        title_row.addStretch(1)
        title_row.addWidget(self.update_button)
        title_row.addWidget(self.export_button)
        title_row.addWidget(self.detach_button)
        title_row.addWidget(self.detach_table_button)
        title_row.addWidget(self.help_button)
        layout.addLayout(title_row)
        toolbar_layout.addWidget(QLabel("Reference"))
        toolbar_layout.addWidget(self.reference_combo)
        toolbar_layout.addWidget(QLabel("Start"))
        toolbar_layout.addWidget(self.start_spin)
        toolbar_layout.addWidget(QLabel("End"))
        toolbar_layout.addWidget(self.end_spin)
        sign_deadband_label = QLabel("Sign deadband")
        sign_deadband_label.setToolTip("Values with absolute magnitude at or below this threshold are treated as neutral.")
        toolbar_layout.addWidget(sign_deadband_label)
        toolbar_layout.addWidget(self.sign_deadband_spin)
        abs_tolerance_label = QLabel("Abs tol")
        abs_tolerance_label.setToolTip("Absolute engineering tolerance in the current channel units.")
        toolbar_layout.addWidget(abs_tolerance_label)
        toolbar_layout.addWidget(self.abs_tolerance_spin)
        rel_tolerance_label = QLabel("Rel tol %")
        rel_tolerance_label.setToolTip("Relative engineering tolerance as a percent of the reference value.")
        toolbar_layout.addWidget(rel_tolerance_label)
        toolbar_layout.addWidget(self.rel_tolerance_spin)
        toolbar_layout.addWidget(self.metric_button)
        toolbar_layout.addWidget(self.overlay_filter_button)
        toolbar_layout.addWidget(self.hide_transforms_checkbox)
        toolbar_layout.addWidget(self.filter_overlay_to_sign_summary_checkbox)
        toolbar_layout.addStretch(1)
        layout.addWidget(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.results_splitter = splitter
        self.channels_shell = QWidget()
        self.channels_shell.setObjectName("CollapsibleColumnShell")
        self.channels_shell.setMinimumWidth(self.CHANNELS_EXPANDED_MIN_WIDTH)
        self.channels_shell.setMaximumWidth(self.CHANNELS_EXPANDED_MAX_WIDTH)
        channels_shell_layout = QHBoxLayout(self.channels_shell)
        channels_shell_layout.setContentsMargins(0, 0, 0, 0)
        channels_shell_layout.setSpacing(0)
        self.channels_sidebar = _panel()
        sidebar_layout = QVBoxLayout(self.channels_sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(8)
        self.channels_collapse_button = pane_handle_button(
            "chevrons-left.svg",
            "Collapse Channels",
            "Collapse Channels",
        )
        self.channels_collapse_button.clicked.connect(self.collapse_channels_panel)
        sidebar_layout.addWidget(pane_header("Channels", self.channels_collapse_button))
        self.channel_count = _muted("No channels loaded")
        sidebar_layout.addWidget(self.channel_count)
        self.channel_search_edit = QLineEdit()
        self.channel_search_edit.setPlaceholderText("Search channels")
        self.channel_search_edit.setClearButtonEnabled(True)
        self.channel_completion_model = QStringListModel(self)
        self.channel_completer = QCompleter(self.channel_completion_model, self)
        self.channel_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.channel_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.channel_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.channel_search_edit.setCompleter(self.channel_completer)
        self.channel_search_edit.textChanged.connect(self._filter_channel_list)
        sidebar_layout.addWidget(self.channel_search_edit)
        self.channel_list = QListWidget()
        self.channel_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.channel_list.itemSelectionChanged.connect(self._handle_channel_selection_changed)
        sidebar_layout.addWidget(self.channel_list, 1)
        channel_buttons = QHBoxLayout()
        self.select_all_channels_button = QPushButton("Select All")
        self.clear_channels_button = QPushButton("Clear")
        self.select_all_channels_button.clicked.connect(self.select_all_channels)
        self.clear_channels_button.clicked.connect(self.clear_channels)
        channel_buttons.addWidget(self.select_all_channels_button)
        channel_buttons.addWidget(self.clear_channels_button)
        sidebar_layout.addLayout(channel_buttons)
        certification_channel_buttons = QHBoxLayout()
        self.select_reject_channels_button = QPushButton("Select Reject")
        self.select_warning_channels_button = QPushButton("Select Warning")
        self.select_reject_channels_button.setEnabled(False)
        self.select_warning_channels_button.setEnabled(False)
        self.select_reject_channels_button.clicked.connect(self.select_reject_channels)
        self.select_warning_channels_button.clicked.connect(self.select_warning_channels)
        certification_channel_buttons.addWidget(self.select_reject_channels_button)
        certification_channel_buttons.addWidget(self.select_warning_channels_button)
        sidebar_layout.addLayout(certification_channel_buttons)
        self.channels_restore_rail, self.channels_restore_handle = collapsed_pane_rail(
            "Channels",
            "Show Channels",
            "Show Channels",
            theme="panel",
            restore_callback=self.expand_channels_panel,
            overlay_parent=self,
            tab_top_margin=0,
        )
        self.channels_restore_rail.hide()
        channels_shell_layout.addWidget(self.channels_sidebar)
        channels_shell_layout.addWidget(self.channels_restore_rail)

        self.tabs = QTabWidget()
        self._table_bundle: AnalysisTableBundle | None = None
        self.metrics_panel = PlotTablePanel(
            self._new_plot_panel(),
            "Statistical Metrics Table",
            "All aggregate metrics for the current selected channels and time range.",
        )
        self.metrics_plot = self.metrics_panel.plot
        self.metrics_table = self.metrics_panel.table_view
        self.certification_panel = PlotTablePanel(
            self._new_plot_panel(),
            "Certification Ranking Table",
            "Channel screening and ranking metrics for substantiation evidence selection.",
            controls=self._build_certification_controls(),
        )
        self.certification_plot = self.certification_panel.plot
        self.certification_table = self.certification_panel.table_view
        selection_model = self.certification_table.selectionModel()
        if selection_model is not None:
            selection_model.selectionChanged.connect(lambda *_args: self.certification_display_changed.emit())
        self.scale_panel = PlotTablePanel(
            self._new_plot_panel(),
            "Scale and Offset Table",
            "Correction coefficients used to transform the candidate toward the reference.",
        )
        self.scale_plot = self.scale_panel.plot
        self.scale_table = self.scale_panel.table_view
        self.sign_plot = SignAgreementView()
        self._wire_sign_deadband_view(self.sign_plot)
        self.sign_plot.setMinimumHeight(420)
        self.residual_plot = self._new_plot_panel()
        self.rolling_plot = self._new_plot_panel()
        self.lag_plot = self._new_plot_panel()
        self.events_view = StandaloneTablePanel(
            "Events",
            "Zero crossing, extrema, and threshold timing differences.",
        )
        self.events_table = self.events_view.table_view
        self.quality_view = StandaloneTablePanel(
            "Data Quality",
            "Timestamp, missing-value, flatline, clipping, and spike diagnostics.",
        )
        self.quality_table = self.quality_view.table_view
        self.calibration_view = PlotTablePanel(
            self._new_plot_panel(),
            "Calibration Fit Metrics",
            "Per-channel fit: candidate ~= slope * reference + offset.",
        )
        self.calibration_plot = self.calibration_view.plot
        self.calibration_table = self.calibration_view.table_view
        self.frequency_plot = self._new_plot_panel()
        self.overlay_view = OverlayResultsView(self._new_plot_panel())
        self.overlay_plot = self.overlay_view.plot
        self.overlay_table = self.overlay_view.table_view
        self.data_tables_view = SelectableTablesView(
            "Data Tables",
            "Browse every generated table from the current analysis.",
        )
        self.tabs.addTab(self.metrics_panel, "Statistical Metrics")
        self.tabs.addTab(self.certification_panel, "Certification Ranking")
        self.tabs.addTab(self.scale_panel, "Scale and Offset")
        self.tabs.addTab(self.sign_plot, "Sign Agreement")
        self.tabs.addTab(self.residual_plot, "Residuals")
        self.tabs.addTab(self.rolling_plot, "Rolling Metrics")
        self.tabs.addTab(self.lag_plot, "Lag")
        self.tabs.addTab(self.events_view, "Events")
        self.tabs.addTab(self.quality_view, "Data Quality")
        self.tabs.addTab(self.calibration_view, "Calibration")
        self.tabs.addTab(self.frequency_plot, "Frequency")
        self.tabs.addTab(self.overlay_view, "Overlay Plot")
        self.tabs.addTab(self.data_tables_view, "Data Tables")
        self.tabs.setTabToolTip(0, "Aggregate fit, error, correlation, and polarity metrics by channel.")
        self.tabs.setTabToolTip(1, "Certification-oriented ranking, peak parity, and eligibility screening by channel.")
        self.tabs.setTabToolTip(2, "Linear scale and offset coefficients by channel.")
        self.tabs.setTabToolTip(3, "Per-time-point same-sign, opposite-sign, and deadband status.")
        self.tabs.setTabToolTip(4, "Target-minus-reference residual traces and residual summary metrics.")
        self.tabs.setTabToolTip(5, "Rolling RMSE, bias, Pearson R, and sign agreement over time.")
        self.tabs.setTabToolTip(6, "Cross-correlation versus lag with best-lag markers.")
        self.tabs.setTabToolTip(7, "Zero crossing, extrema, and threshold timing differences.")
        self.tabs.setTabToolTip(8, "Timestamp, missing-value, flatline, clipping, and spike checks.")
        self.tabs.setTabToolTip(9, "Candidate-versus-reference scatter with identity and fitted lines.")
        self.tabs.setTabToolTip(10, "FFT magnitude comparison for sufficiently uniform time axes.")
        self.tabs.setTabToolTip(11, "Overlay the reference, target, and optional transformed traces.")
        self.tabs.setTabToolTip(12, "Browse and copy all generated analysis tables.")
        self.tabs.currentChanged.connect(lambda _index: self._hide_metric_help())
        self.tabs.currentChanged.connect(self._refresh_current_plot)
        self.tabs.currentChanged.connect(lambda _index: self._sync_detach_buttons())
        self.overlay_view.table_selector.currentIndexChanged.connect(lambda _index: self._sync_table_detach_button())
        self.data_tables_view.combo.currentIndexChanged.connect(lambda _index: self._sync_table_detach_button())
        splitter.addWidget(self.channels_shell)
        splitter.addWidget(self.tabs)
        splitter.setSizes([self.CHANNELS_DEFAULT_WIDTH, 980])
        layout.addWidget(splitter, 1)

        self.status_label = QLabel("Prepare datasets to render analysis.")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self._sync_detach_button()
        self._sync_table_detach_button()

    def collapse_channels_panel(self) -> None:
        if self.channels_panel_collapsed:
            return
        current_width = self.channels_shell.width()
        if current_width > self.COLLAPSED_RAIL_WIDTH:
            self._channels_expanded_width = max(self.CHANNELS_EXPANDED_MIN_WIDTH, current_width)
        self.channels_sidebar.hide()
        self.channels_restore_rail.conceal()
        self.channels_restore_rail.show()
        self.channels_shell.setMinimumWidth(self.COLLAPSED_RAIL_WIDTH)
        self.channels_shell.setMaximumWidth(self.COLLAPSED_RAIL_WIDTH)
        self.channels_panel_collapsed = True
        splitter_width = max(self.results_splitter.width(), self.COLLAPSED_RAIL_WIDTH + 800)
        self.results_splitter.setSizes([self.COLLAPSED_RAIL_WIDTH, splitter_width - self.COLLAPSED_RAIL_WIDTH])

    def expand_channels_panel(self) -> None:
        if not self.channels_panel_collapsed:
            return
        self.channels_restore_rail.conceal()
        self.channels_restore_rail.hide()
        self.channels_sidebar.show()
        self.channels_shell.setMinimumWidth(self.CHANNELS_EXPANDED_MIN_WIDTH)
        self.channels_shell.setMaximumWidth(self.CHANNELS_EXPANDED_MAX_WIDTH)
        self.channels_panel_collapsed = False
        width = min(
            max(self._channels_expanded_width, self.CHANNELS_EXPANDED_MIN_WIDTH),
            self.CHANNELS_EXPANDED_MAX_WIDTH,
        )
        splitter_width = max(self.results_splitter.width(), width + 800)
        self.results_splitter.setSizes([width, splitter_width - width])

    def toggle_channels_panel(self) -> None:
        if self.channels_panel_collapsed:
            self.expand_channels_panel()
        else:
            self.collapse_channels_panel()

    def _build_export_menu(self) -> QMenu:
        menu = QMenu(self)
        current_action = QAction("Export Current Table...", self)
        current_action.triggered.connect(self.export_current_requested)
        master_action = QAction("Export Master Workbook...", self)
        master_action.triggered.connect(self.export_master_requested)
        menu.addAction(current_action)
        menu.addAction(master_action)
        return menu

    def _build_metric_menu(self) -> QMenu:
        menu = QMenu(self)
        self.metric_menu = menu
        menu.aboutToHide.connect(self._schedule_metric_help_hide)
        select_all = QAction("Select All", self)
        select_all.triggered.connect(lambda: self._set_all_metrics(True))
        select_all.hovered.connect(self._hide_metric_help)
        clear = QAction("Clear", self)
        clear.triggered.connect(lambda: self._set_all_metrics(False))
        clear.hovered.connect(self._hide_metric_help)
        reset = QAction("Reset Defaults", self)
        reset.triggered.connect(self._reset_default_metrics)
        reset.hovered.connect(self._hide_metric_help)
        menu.addAction(select_all)
        menu.addAction(clear)
        menu.addAction(reset)
        menu.addSeparator()
        for group_name, metric_keys in METRIC_GROUPS.items():
            group_menu = menu.addMenu(group_name)
            group_menu.aboutToHide.connect(self._schedule_metric_help_hide)
            for metric_key in metric_keys:
                action = QAction(metric_key, self)
                action.setCheckable(True)
                action.setChecked(metric_key in DEFAULT_METRIC_KEYS)
                action.setToolTip(metric_fallback_tooltip(metric_key))
                action.setStatusTip(metric_fallback_tooltip(metric_key))
                action.toggled.connect(lambda _checked=False: self.changed.emit())
                action.triggered.connect(self._hide_metric_help)
                action.hovered.connect(
                    lambda key=metric_key, owner_menu=group_menu, owner_action=action: self._show_metric_help(
                        key,
                        owner_menu,
                        owner_action,
                    )
                )
                self.metric_actions[metric_key] = action
                self.metric_action_menus[metric_key] = group_menu
                group_menu.addAction(action)
        return menu

    def _show_metric_help(
        self,
        metric_key: str,
        owner_menu: QMenu | None = None,
        owner_action: QAction | None = None,
    ) -> None:
        owner_menu = owner_menu or self.metric_action_menus.get(metric_key)
        owner_action = owner_action or self.metric_actions.get(metric_key)
        if owner_menu is not None and owner_action is not None:
            action_rect = owner_menu.actionGeometry(owner_action)
            preferred_y = owner_menu.mapToGlobal(action_rect.topLeft()).y()
        else:
            preferred_y = self.metric_button.mapToGlobal(self.metric_button.rect().topLeft()).y()
        menu_rect = self._visible_metric_menu_rect()
        self._last_metric_menu_rect = menu_rect if self._metric_menu_visible() else QRect()
        self.metric_help_popover.show_metric(metric_key, menu_rect, preferred_y)

    def _schedule_metric_help_hide(self) -> None:
        QTimer.singleShot(180, self._hide_metric_help_if_cursor_left)

    def _hide_metric_help_if_cursor_left(self) -> None:
        if self.metric_help_popover.is_pinned():
            return
        if self._metric_menu_visible():
            return
        if self._cursor_inside_metric_help_zone():
            self._schedule_metric_help_hide()
            return
        self.metric_help_popover.hide()

    def _hide_metric_help(self) -> None:
        if self.metric_help_popover.is_pinned():
            return
        self.metric_help_popover.hide()

    def _force_hide_metric_help(self) -> None:
        self.metric_help_popover.set_pinned(False)
        self.metric_help_popover.hide()

    def _metric_menu_visible(self) -> bool:
        menus = [self.metric_menu, *self.metric_action_menus.values()]
        return any(menu is not None and menu.isVisible() for menu in menus)

    def _cursor_inside_metric_help_zone(self) -> bool:
        if self.metric_help_popover.isHidden():
            return False
        cursor_pos = QCursor.pos()
        popover_rect = self.metric_help_popover.frameGeometry()
        if popover_rect.adjusted(-4, -4, 4, 4).contains(cursor_pos):
            return True
        menu_rect = self._last_metric_menu_rect
        if menu_rect.isNull() or not menu_rect.isValid():
            return False
        return menu_rect.united(popover_rect).adjusted(-12, -12, 12, 12).contains(cursor_pos)

    def _handle_metric_help_pin_changed(self, pinned: bool) -> None:
        if not pinned and not self._metric_menu_visible():
            self.metric_help_popover.hide()

    def _visible_metric_menu_rect(self) -> QRect:
        menu_rect: QRect | None = None
        seen_menu_ids: set[int] = set()
        menus = [self.metric_menu, *self.metric_action_menus.values()]
        for menu in menus:
            if menu is None or id(menu) in seen_menu_ids:
                continue
            seen_menu_ids.add(id(menu))
            if menu.isVisible():
                current = menu.frameGeometry()
                menu_rect = current if menu_rect is None else menu_rect.united(current)
        if menu_rect is not None:
            return menu_rect
        top_left = self.metric_button.mapToGlobal(self.metric_button.rect().topLeft())
        return QRect(top_left, self.metric_button.size())

    def hideEvent(self, event: Any) -> None:
        self._force_hide_metric_help()
        super().hideEvent(event)

    def _set_all_metrics(self, checked: bool) -> None:
        for action in self.metric_actions.values():
            action.blockSignals(True)
            action.setChecked(checked)
            action.blockSignals(False)
        self.changed.emit()

    def _reset_default_metrics(self) -> None:
        for metric_key, action in self.metric_actions.items():
            action.blockSignals(True)
            action.setChecked(metric_key in DEFAULT_METRIC_KEYS)
            action.blockSignals(False)
        self.changed.emit()

    def _build_certification_controls(self) -> tuple[QWidget, ...]:
        label = QLabel("Labels")
        label.setToolTip("Choose which channels receive permanent labels in the Certification Ranking plot.")
        self.certification_label_combo = QComboBox()
        self.certification_label_combo.addItem("Auto labels", "auto")
        self.certification_label_combo.addItem("No labels", "none")
        self.certification_label_combo.addItem("Rejected labels", "rejected")
        self.certification_label_combo.addItem("Selected labels", "selected")
        self.certification_label_combo.setFixedWidth(142)
        self.certification_label_combo.setToolTip(
            "Labels are off by default - hover any point to read its channel, grade, and scores. "
            "Pick a mode to pin permanent text labels."
        )
        # Default to hover-only so the ranking plots stay uncluttered; channel detail is
        # surfaced through the existing hover tooltips. Set before wiring the signal so this
        # initial selection does not trigger a redundant display refresh.
        self.certification_label_combo.setCurrentIndex(self.certification_label_combo.findData("none"))
        self.certification_label_combo.currentIndexChanged.connect(
            lambda _index=0: self.certification_display_changed.emit()
        )
        return (label, self.certification_label_combo)

    def _time_spinbox(self) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setDecimals(3)
        spinbox.setRange(0, 999999999)
        spinbox.setSingleStep(0.1)
        return spinbox

    def _deadband_spinbox(self) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setKeyboardTracking(False)
        spinbox.setDecimals(6)
        spinbox.setRange(0, 999999999)
        spinbox.setSingleStep(0.001)
        spinbox.setToolTip(
            "Treat values from -deadband to +deadband as neutral when calculating sign agreement."
        )
        spinbox.setFixedWidth(118)
        return spinbox

    def _absolute_tolerance_spinbox(self) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setKeyboardTracking(False)
        spinbox.setDecimals(6)
        spinbox.setRange(0, 999999999)
        spinbox.setSingleStep(0.001)
        spinbox.setToolTip("Absolute tolerance in channel units for Within Tolerance Abs (%). Leave at 0 to disable.")
        spinbox.setFixedWidth(108)
        return spinbox

    def _relative_tolerance_spinbox(self) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setKeyboardTracking(False)
        spinbox.setDecimals(3)
        spinbox.setRange(0, 100000)
        spinbox.setSingleStep(0.1)
        spinbox.setSuffix(" %")
        spinbox.setToolTip("Relative tolerance for Within Tolerance Rel (%). Leave at 0 to disable.")
        spinbox.setFixedWidth(108)
        return spinbox

    def _noise_floor_spinbox(self) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setKeyboardTracking(False)
        spinbox.setDecimals(6)
        spinbox.setRange(0, 999999999)
        spinbox.setSingleStep(0.001)
        spinbox.setToolTip(
            "Noise floor in channel units. Samples where both channels are at or below this "
            "magnitude count as within tolerance for both Within Tolerance metrics. Leave at 0 to disable."
        )
        spinbox.setFixedWidth(108)
        return spinbox

    def _new_plot_panel(self) -> QWidget:
        panel = self._plot_view_factory()
        panel.setMinimumHeight(420)
        return panel

    def toggle_current_plot_detached(self) -> None:
        index = self.tabs.currentIndex()
        if index < 0:
            return
        if index in self._detached_plots:
            self.restore_detached_plot(index)
        else:
            self.detach_current_plot()

    def detach_current_plot(self) -> None:
        index = self.tabs.currentIndex()
        if index < 0:
            return
        if index in self._detached_plots:
            self._detached_plots[index].window.raise_()
            self._detached_plots[index].window.activateWindow()
            return

        tab_widget = self.tabs.widget(index)
        if tab_widget is None:
            return
        detached_widget = self._detached_plot_widget(tab_widget)
        if detached_widget is None:
            detached_widget = tab_widget
        title = self.tabs.tabText(index)
        tooltip = self.tabs.tabToolTip(index)
        placeholder = self._detached_placeholder(index, title)
        self.tabs.removeTab(index)
        self.tabs.insertTab(index, placeholder, title)
        self.tabs.setTabToolTip(index, tooltip)
        self.tabs.setCurrentIndex(index)

        window = DetachedPlotWindow(
            f"{self.window().windowTitle()} - {title}",
            detached_widget,
            lambda tab_index=index: self.restore_detached_plot(tab_index, from_window_close=True),
        )
        self._detached_plots[index] = DetachedPlotState(
            tab_widget=tab_widget,
            detached_widget=detached_widget,
            placeholder=placeholder,
            window=window,
            title=title,
            tooltip=tooltip,
        )
        window.show()
        self._force_refresh_plot(detached_widget)
        QTimer.singleShot(0, lambda widget=detached_widget: self._force_refresh_plot(widget))
        self._sync_detach_buttons()

    def restore_detached_plot(self, index: int | None = None, *, from_window_close: bool = False) -> None:
        if index is None:
            index = self.tabs.currentIndex()
        state = self._detached_plots.pop(index, None)
        if state is None:
            return

        if state.window.centralWidget() is state.detached_widget:
            state.window.takeCentralWidget()
        placeholder_index = self.tabs.indexOf(state.placeholder)
        insert_index = placeholder_index if placeholder_index >= 0 else min(index, self.tabs.count())
        if placeholder_index >= 0:
            self.tabs.removeTab(placeholder_index)
        self.tabs.insertTab(insert_index, state.tab_widget, state.title)
        self.tabs.setTabToolTip(insert_index, state.tooltip)
        self.tabs.setCurrentIndex(insert_index)
        state.placeholder.deleteLater()

        if not from_window_close:
            state.window.close_for_restore()
        if state.detached_widget is not state.tab_widget:
            state.detached_widget.deleteLater()
        state.window.deleteLater()
        self._force_refresh_plot(state.tab_widget)
        self._sync_detach_buttons()

    def _detached_plot_widget(self, tab_widget: QWidget) -> QWidget | None:
        source_plot = getattr(tab_widget, "plot", tab_widget)
        figure = getattr(source_plot, "figure", None)
        if figure is None:
            figure = getattr(source_plot, "_figure", None)
        if figure is None:
            figure = getattr(source_plot, "plot_data", None)
        if figure is None:
            return None

        if isinstance(source_plot, SignAgreementView):
            detached_widget: QWidget = SignAgreementView()
            self._wire_sign_deadband_view(detached_widget)
        else:
            detached_widget = self._plot_view_factory()
        detached_widget.setMinimumSize(900, 620)
        setter = getattr(detached_widget, "set_figure", None)
        if not callable(setter):
            return None
        setter(figure)
        return detached_widget

    def _detached_placeholder(self, index: int, title: str) -> QWidget:
        panel = _panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        label = QLabel(f"{title} is open in a detached window.")
        label.setObjectName("MutedLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        restore_button = _primary_button("Restore Plot")
        restore_button.setToolTip("Move the detached plot back into this tab.")
        restore_button.clicked.connect(lambda _checked=False, tab_index=index: self.restore_detached_plot(tab_index))
        layout.addStretch(1)
        layout.addWidget(label)
        layout.addWidget(restore_button, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        return panel

    def toggle_current_table_detached(self) -> None:
        table = self.current_table()
        if table is None:
            return
        if table.table_id in self._detached_tables:
            self.close_detached_table(table.table_id)
        else:
            self.detach_current_table()

    def detach_current_table(self) -> None:
        table = self.current_table()
        if table is None:
            return
        state = self._detached_tables.get(table.table_id)
        if state is not None:
            state.window.raise_()
            state.window.activateWindow()
            return

        table_view = SpreadsheetTableView()
        table_view.set_table(table)
        window = DetachedTableWindow(
            f"{self.window().windowTitle()} - {table.title}",
            table_view,
            lambda table_id=table.table_id: self.close_detached_table(table_id, from_window_close=True),
        )
        self._detached_tables[table.table_id] = DetachedTableState(
            table_id=table.table_id,
            table_view=table_view,
            window=window,
        )
        window.show()
        self._sync_table_detach_button()

    def close_detached_table(self, table_id: str, *, from_window_close: bool = False) -> None:
        state = self._detached_tables.pop(table_id, None)
        if state is None:
            return
        if not from_window_close:
            state.window.close_for_restore()
        state.window.deleteLater()
        self._sync_table_detach_button()

    def _sync_detach_button(self) -> None:
        index = self.tabs.currentIndex()
        detached = index in self._detached_plots
        label = "Restore Plot" if detached else "Detach Plot"
        self.detach_button.setText("")
        self.detach_button.setIcon(self._restore_icon if detached else self._detach_icon)
        self.detach_button.setToolTip(
            "Move the detached plot back into this tab." if detached else "Open the current plot in a separate window."
        )
        self.detach_button.setAccessibleName(label)
        self.detach_button.setEnabled(index >= 0)

    def _sync_table_detach_button(self) -> None:
        table = self.current_table()
        detached = table is not None and table.table_id in self._detached_tables
        label = "Close Detached Table" if detached else "Detach Table"
        self.detach_table_button.setText("")
        self.detach_table_button.setIcon(self._restore_icon if detached else self._detach_icon)
        self.detach_table_button.setToolTip(
            "Close the detached table window." if detached else "Open the current table in a separate window."
        )
        self.detach_table_button.setAccessibleName(label)
        self.detach_table_button.setEnabled(table is not None)

    def _sync_detach_buttons(self) -> None:
        self._sync_detach_button()
        self._sync_table_detach_button()

    def _force_refresh_plot(self, widget: QWidget) -> None:
        force_refresher = getattr(widget, "force_refresh_plot", None)
        if callable(force_refresher):
            force_refresher()
            return
        refresher = getattr(widget, "refresh_plot", None)
        if callable(refresher):
            refresher()

    def _refresh_current_plot(self, index: int | None = None) -> None:
        if index is None:
            index = self.tabs.currentIndex()
        if index < 0:
            return
        state = self._detached_plots.get(index)
        widget = state.detached_widget if state is not None else self.tabs.widget(index)
        refresher = getattr(widget, "refresh_plot", None)
        if callable(refresher):
            refresher()

    def apply_overlay_trace_visibility(self, mask: Sequence[bool]) -> None:
        self._apply_trace_visibility(self.overlay_plot, mask)
        for state in self._detached_plots.values():
            if state.tab_widget is self.overlay_view:
                self._apply_trace_visibility(state.detached_widget, mask)

    @staticmethod
    def _apply_trace_visibility(widget: QWidget, mask: Sequence[bool]) -> None:
        applier = getattr(widget, "apply_trace_visibility_mask", None)
        if callable(applier):
            applier(mask)

    def set_ready(self, prepared: PreparedComparison, reference_index: int, start_time: float, end_time: float) -> None:
        self.reference_combo.blockSignals(True)
        self.start_spin.blockSignals(True)
        self.end_spin.blockSignals(True)
        self.channel_list.blockSignals(True)

        self.reference_combo.clear()
        self.reference_combo.addItems([prepared.dataset1.display_name, prepared.dataset2.display_name])
        self.reference_combo.setCurrentIndex(reference_index)
        for spinbox in [self.start_spin, self.end_spin]:
            spinbox.setRange(prepared.time_min, prepared.time_max)
        self.start_spin.setValue(start_time)
        self.end_spin.setValue(end_time)
        self.channel_list.clear()
        self.channel_list.addItems(prepared.channels)
        self.channel_completion_model.setStringList(list(prepared.channels))
        for index in range(self.channel_list.count()):
            self.channel_list.item(index).setSelected(True)
        self._filter_channel_list(self.channel_search_edit.text())

        self.channel_list.blockSignals(False)
        self.end_spin.blockSignals(False)
        self.start_spin.blockSignals(False)
        self.reference_combo.blockSignals(False)

    def selected_columns(self) -> list[str]:
        return [item.text() for item in self.channel_list.selectedItems()]

    def certification_label_mode(self) -> str:
        return str(self.certification_label_combo.currentData() or "none")

    def certification_max_labels(self) -> int:
        return self._certification_max_labels

    def certification_highlighted_channels(self) -> tuple[str, ...]:
        return tuple(self.certification_table.selected_values("Channel"))

    def analysis_range(self) -> tuple[float, float]:
        return self.start_spin.value(), self.end_spin.value()

    def reference_index(self) -> int:
        return self.reference_combo.currentIndex()

    def hide_transforms(self) -> bool:
        return self.hide_transforms_checkbox.isChecked()

    def filter_overlay_to_sign_summary(self) -> bool:
        return self.filter_overlay_to_sign_summary_checkbox.isChecked()

    def overlay_metric_filter_state(self) -> OverlayMetricFilterState:
        return self._overlay_metric_filter_state

    def set_overlay_metric_filter_state(self, state: OverlayMetricFilterState) -> None:
        if state == self._overlay_metric_filter_state:
            return
        self._overlay_metric_filter_state = state
        self._update_overlay_filter_button()
        self.changed.emit()

    def _configure_overlay_metric_filter(self) -> None:
        metric_keys = [metric_key for metric_keys in METRIC_GROUPS.values() for metric_key in metric_keys]
        dialog = OverlayMetricFilterDialog(self._overlay_metric_filter_state, metric_keys, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.set_overlay_metric_filter_state(dialog.selected_state())

    def _update_overlay_filter_button(self) -> None:
        self.overlay_filter_button.setText(
            "Overlay Filter: On" if self._overlay_metric_filter_state.enabled() else "Overlay Filter..."
        )

    def sign_deadband(self) -> float:
        return self.sign_deadband_spin.value()

    def _set_sign_deadband_from_summary(self, value: float) -> None:
        if self.sign_deadband_spin.value() == value:
            return
        self.sign_deadband_spin.setValue(value)

    def _wire_sign_deadband_view(self, view: SignAgreementView) -> None:
        view.sign_deadband_changed.connect(self._set_sign_deadband_from_summary)
        view.summary_filter_changed.connect(self._on_sign_summary_filter_changed)
        self.sign_deadband_spin.valueChanged.connect(view.set_sign_deadband)
        view.set_sign_deadband(self.sign_deadband_spin.value())

    def _on_sign_summary_filter_changed(self) -> None:
        if self.filter_overlay_to_sign_summary():
            self.changed.emit()

    def abs_tolerance(self) -> float:
        return self.abs_tolerance_spin.value()

    def rel_tolerance_percent(self) -> float:
        return self.rel_tolerance_spin.value()

    def noise_floor(self) -> float:
        return self.noise_floor_spin.value()

    def selected_metric_keys(self) -> list[str]:
        return [metric_key for metric_key, action in self.metric_actions.items() if action.isChecked()]

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def set_update_pending(self, pending: bool) -> None:
        self.update_button.setEnabled(pending)
        self.update_button.setProperty("pending", pending)
        self.update_button.style().unpolish(self.update_button)
        self.update_button.style().polish(self.update_button)

    def set_figures(
        self,
        metrics: Any,
        scale_offset: Any,
        sign_agreement: Any,
        residual: Any,
        rolling: Any,
        lag: Any,
        events: Any,
        quality: Any,
        calibration: Any,
        frequency: Any,
        overlay: Any,
        *,
        certification: Any | None = None,
        table_bundle: AnalysisTableBundle | None = None,
    ) -> None:
        for view, figure in [
            (self.metrics_panel, metrics),
            (self.certification_panel, certification),
            (self.scale_panel, scale_offset),
            (self.sign_plot, sign_agreement),
            (self.residual_plot, residual),
            (self.rolling_plot, rolling),
            (self.lag_plot, lag),
            (self.calibration_view, calibration),
            (self.frequency_plot, frequency),
            (self.overlay_view, overlay),
        ]:
            if figure is None:
                continue
            setter = getattr(view, "set_figure", None)
            if callable(setter):
                setter(figure)
        detached_figures = {
            0: metrics,
            1: certification,
            2: scale_offset,
            3: sign_agreement,
            4: residual,
            5: rolling,
            6: lag,
            9: calibration,
            10: frequency,
            11: overlay,
        }
        for tab_index, state in self._detached_plots.items():
            if state.detached_widget is state.tab_widget:
                continue
            figure = detached_figures.get(tab_index)
            setter = getattr(state.detached_widget, "set_figure", None)
            if figure is not None and callable(setter):
                setter(figure)
                self._force_refresh_plot(state.detached_widget)
        self.set_table_bundle(table_bundle)
        self._refresh_current_plot()

    def set_tab_figure(self, tab_index: int, figure: Any) -> None:
        state = self._detached_plots.get(tab_index)
        widget = state.detached_widget if state is not None else self.tabs.widget(tab_index)
        setter = getattr(widget, "set_figure", None)
        if callable(setter):
            setter(figure)
        if state is not None and state.detached_widget is not state.tab_widget:
            self._force_refresh_plot(state.detached_widget)
        elif self.tabs.currentIndex() == tab_index:
            self._refresh_current_plot(tab_index)

    def set_table_bundle(self, bundle: AnalysisTableBundle | None) -> None:
        self._table_bundle = bundle
        self.metrics_panel.set_table(bundle.table("metrics") if bundle else None)
        self.certification_panel.set_table(bundle.table("certification_ranking") if bundle else None)
        self.scale_panel.set_table(bundle.table("scale_offset") if bundle else None)
        self.calibration_view.set_table(bundle.table("calibration") if bundle else None)
        self.events_view.set_table(bundle.table("events") if bundle else None)
        self.quality_view.set_table(bundle.table("data_quality") if bundle else None)
        overlay_tables = [
            table
            for table_id in [
                "overlay_reference",
                "overlay_candidate_original",
                "overlay_candidate_scaled",
                "overlay_candidate_offset",
                "overlay_candidate_scaled_offset",
            ]
            if bundle is not None and (table := bundle.table(table_id)) is not None
        ]
        self.overlay_view.set_tables(overlay_tables)
        self.data_tables_view.set_tables(bundle.tables if bundle is not None else ())
        self._sync_channel_quick_buttons()
        self._refresh_detached_tables()
        self._sync_table_detach_button()

    def current_table(self) -> AnalysisTable | None:
        index = self.tabs.currentIndex()
        if index < 0:
            return None
        state = self._detached_plots.get(index)
        widget = state.tab_widget if state is not None else self.tabs.widget(index)
        getter = getattr(widget, "current_table", None)
        if callable(getter):
            return getter()
        return None

    def _refresh_detached_tables(self) -> None:
        for table_id, state in list(self._detached_tables.items()):
            table = self._table_bundle.table(table_id) if self._table_bundle is not None else None
            if table is None:
                self.close_detached_table(table_id)
            else:
                state.table_view.set_table(table)

    def table_bundle(self) -> AnalysisTableBundle | None:
        return self._table_bundle

    def select_all_channels(self) -> None:
        self._set_selected_channels([self.channel_list.item(index).text() for index in range(self.channel_list.count())])

    def clear_channels(self) -> None:
        self._set_selected_channels([])

    def select_reject_channels(self) -> None:
        self._set_selected_channels(self._certification_channels("reject"))

    def select_warning_channels(self) -> None:
        self._set_selected_channels(self._certification_channels("warning"))

    def _handle_channel_selection_changed(self) -> None:
        self._sync_channel_count()
        self.changed.emit()

    def _filter_channel_list(self, text: str) -> None:
        query = text.casefold().strip()
        for index in range(self.channel_list.count()):
            item = self.channel_list.item(index)
            item.setHidden(bool(query and query not in item.text().casefold()))
        self._sync_channel_count()

    def _sync_channel_count(self) -> None:
        total = self.channel_list.count()
        selected = len(self.channel_list.selectedItems())
        visible = sum(not self.channel_list.item(index).isHidden() for index in range(total))
        if self.channel_search_edit.text().strip():
            self.channel_count.setText(f"{selected}/{total} selected; {visible} matches")
        else:
            self.channel_count.setText(f"{selected}/{total} selected")

    def _set_selected_channels(self, channels: Sequence[str]) -> None:
        target = set(channels)
        changed = False
        self.channel_list.blockSignals(True)
        for index in range(self.channel_list.count()):
            item = self.channel_list.item(index)
            selected = item.text() in target
            if item.isSelected() != selected:
                item.setSelected(selected)
                changed = True
        self.channel_list.blockSignals(False)
        self._sync_channel_count()
        if changed:
            self.changed.emit()

    def _certification_frame(self) -> pd.DataFrame:
        table = self._table_bundle.table("certification_ranking") if self._table_bundle else None
        return table.frame if table is not None else pd.DataFrame()

    def _certification_channels(self, mode: str) -> list[str]:
        frame = self._certification_frame()
        if frame.empty or "Channel" not in frame.columns:
            return []
        channels: list[str] = []
        for _, row in frame.iterrows():
            grade = str(row.get("Evidence Grade", ""))
            if mode == "reject":
                selected = grade == "Reject"
            else:
                warnings = self._float_or_zero(row.get("Data Quality Warnings")) > 0
                selected = grade != "Reject" and (
                    grade in {"B", "C"} or warnings or str(row.get("Certification Eligible", "")) == "No"
                )
            if selected:
                channels.append(str(row["Channel"]))
        return channels

    @staticmethod
    def _float_or_zero(value: Any) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return 0.0
        return result if math.isfinite(result) else 0.0

    def _sync_channel_quick_buttons(self) -> None:
        frame = self._certification_frame()
        enabled = not frame.empty and "Channel" in frame.columns
        self.select_reject_channels_button.setEnabled(enabled)
        self.select_warning_channels_button.setEnabled(enabled)

    def closeEvent(self, event: Any) -> None:
        for index in list(self._detached_plots):
            self.restore_detached_plot(index)
        for table_id in list(self._detached_tables):
            self.close_detached_table(table_id)
        super().closeEvent(event)


class SensorComparisonWindow(QMainWindow):
    STEP_TITLES = [
        "Choose Input",
        "Match Channels",
        "Name Channels",
        "Configure Alignment",
        "Analyze Results",
    ]
    WORKFLOW_EXPANDED_WIDTH = 235
    COLLAPSED_RAIL_WIDTH = CollapsedPaneRail.EDGE_REVEAL_WIDTH
    COLLAPSED_HANDLE_WIDTH = CollapsedPaneRail.HANDLE_WIDTH
    FIGURE_TABS = {
        "metrics": 0,
        "certification": 1,
        "scale": 2,
        "sign": 3,
        "residual": 4,
        "rolling": 5,
        "lag": 6,
        "calibration": 9,
        "frequency": 10,
        "overlay": 11,
    }

    def __init__(self, plot_view_factory: PlotViewFactory | None = None):
        super().__init__()
        self.plot_view_factory = plot_view_factory or WebPlotView
        self.dataset1 = None
        self.dataset2 = None
        self.prepared: PreparedComparison | None = None
        self.current_dataset1: pd.DataFrame | None = None
        self.current_dataset2: pd.DataFrame | None = None
        self._building_results = False
        self._pending_results_render = False
        self._results_render_timer = QTimer(self)
        self._results_render_timer.setSingleShot(True)
        self._results_render_timer.setInterval(120)
        self._results_render_timer.timeout.connect(self.render_results)
        self._filtered_cache_key: tuple[Any, ...] | None = None
        self._filtered_cache: FilteredResultsData | None = None
        self._stable_cache_key: tuple[Any, ...] | None = None
        self._stable_cache: StableResultsArtifacts | None = None
        self._sign_cache_key: tuple[Any, ...] | None = None
        self._sign_cache: SignResultsArtifacts | None = None
        self._base_metrics_cache_key: tuple[Any, ...] | None = None
        self._base_metrics_cache: list[dict[str, float | str]] | None = None
        self._metrics_cache_key: tuple[Any, ...] | None = None
        self._metrics_cache: MetricsResultsArtifacts | None = None
        self._overlay_table_cache_key: tuple[Any, ...] | None = None
        self._overlay_table_cache: AnalysisTableBundle | None = None
        self._figure_cache: dict[str, tuple[tuple[Any, ...], Any]] = {}
        self._rendered_figures: dict[int, Any] = {}
        self._rendered_table_bundle: AnalysisTableBundle | None = None
        self._results_dirty = False
        self.legend_position = DEFAULT_LEGEND_POSITION
        self.hover_annotation_style = DEFAULT_HOVER_ANNOTATION_STYLE
        self._match_source_paths: tuple[Path, Path] | None = None
        self._overlay_pairs = None
        self._auto_final_name_by_pair: dict[tuple[str, str], str] | None = None
        self.workflow_panel_collapsed = False

        self.setWindowTitle("Sensor Data Comparison Tool")
        self.resize(1280, 820)
        self._build_ui()
        self._install_shortcuts()
        self._refresh_steps()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)

        self.workflow_shell = QWidget()
        self.workflow_shell.setObjectName("CollapsibleColumnShell")
        self.workflow_shell.setFixedWidth(self.WORKFLOW_EXPANDED_WIDTH)
        workflow_shell_layout = QHBoxLayout(self.workflow_shell)
        workflow_shell_layout.setContentsMargins(0, 0, 0, 0)
        workflow_shell_layout.setSpacing(0)

        self.workflow_sidebar = QFrame()
        self.workflow_sidebar.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(self.workflow_sidebar)
        sidebar_layout.setContentsMargins(14, 16, 14, 16)
        sidebar_layout.setSpacing(9)
        self.workflow_collapse_button = pane_handle_button(
            "chevrons-left-light.svg",
            "Collapse Workflow",
            "Collapse Workflow",
            theme="sidebar",
        )
        self.workflow_collapse_button.clicked.connect(self.collapse_workflow_panel)
        sidebar_layout.addWidget(pane_header("Workflow", self.workflow_collapse_button))
        self.step_cards: list[QFrame] = []
        self.step_labels: list[QLabel] = []
        for index, title in enumerate(self.STEP_TITLES, start=1):
            card = QFrame()
            card.setObjectName("StepCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            label = QLabel(f"{index}. {title}")
            label.setObjectName("StepLabel")
            card_layout.addWidget(label)
            self.step_cards.append(card)
            self.step_labels.append(label)
            sidebar_layout.addWidget(card)
        sidebar_layout.addStretch(1)
        self.workflow_restore_rail, self.workflow_restore_handle = collapsed_pane_rail(
            "Workflow",
            "Show Workflow",
            "Show Workflow",
            theme="sidebar",
            restore_callback=self.expand_workflow_panel,
            overlay_parent=central,
        )
        self.workflow_restore_rail.hide()
        workflow_shell_layout.addWidget(self.workflow_sidebar)
        workflow_shell_layout.addWidget(self.workflow_restore_rail)
        root.addWidget(self.workflow_shell)

        content_shell = QVBoxLayout()
        self.stack = QStackedWidget()
        self.load_page = LoadPage()
        self.match_page = MatchPage()
        self.name_page = NamePage()
        self.config_page = ConfigPage()
        self.results_page = ResultsPage(self.plot_view_factory)
        for page in [
            self.load_page,
            self.match_page,
            self.name_page,
            self.config_page,
            self.results_page,
        ]:
            self.stack.addWidget(page)
        content_shell.addWidget(self.stack, 1)

        footer = QHBoxLayout()
        self.back_button = QPushButton("Back")
        self.next_button = _primary_button("Next")
        self.back_button.clicked.connect(self.go_back)
        self.next_button.clicked.connect(self.go_next)
        footer.addStretch(1)
        footer.addWidget(self.back_button)
        footer.addWidget(self.next_button)
        content_shell.addLayout(footer)
        root.addLayout(content_shell, 1)
        self.setCentralWidget(central)

        self.config_page.sync_requested.connect(self.apply_sync)
        self.config_page.revert_requested.connect(self.revert_sync)
        self.config_page.reference_changed.connect(self._sync_reference_to_results)
        self.results_page.changed.connect(self._mark_results_dirty)
        self.results_page.certification_display_changed.connect(self._refresh_certification_display)
        self.results_page.update_requested.connect(self._update_results_from_button)
        self.results_page.help_requested.connect(self.open_help_document)
        self.results_page.export_current_requested.connect(self.export_current_table)
        self.results_page.export_master_requested.connect(self.export_master_workbook)
        self.load_page.inputs_changed.connect(self.preview_load_inputs)
        self.load_page.inputs_changed.connect(self._refresh_steps)

    def collapse_workflow_panel(self) -> None:
        if self.workflow_panel_collapsed:
            return
        self.workflow_sidebar.hide()
        self.workflow_restore_rail.conceal()
        self.workflow_restore_rail.show()
        self.workflow_shell.setFixedWidth(self.COLLAPSED_RAIL_WIDTH)
        self.workflow_panel_collapsed = True

    def expand_workflow_panel(self) -> None:
        if not self.workflow_panel_collapsed:
            return
        self.workflow_restore_rail.conceal()
        self.workflow_restore_rail.hide()
        self.workflow_sidebar.show()
        self.workflow_shell.setFixedWidth(self.WORKFLOW_EXPANDED_WIDTH)
        self.workflow_panel_collapsed = False

    def toggle_workflow_panel(self) -> None:
        if self.workflow_panel_collapsed:
            self.expand_workflow_panel()
        else:
            self.collapse_workflow_panel()

    def _install_shortcuts(self) -> None:
        self.legend_shortcut = QShortcut(QKeySequence("K"), self)
        self.legend_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.legend_shortcut.activated.connect(self.cycle_legend_position)
        self.hover_annotation_shortcut = QShortcut(QKeySequence("H"), self)
        self.hover_annotation_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.hover_annotation_shortcut.activated.connect(self.cycle_hover_annotation_style)

    def cycle_legend_position(self) -> None:
        self.legend_position = next_legend_position(self.legend_position)
        if self.stack.currentIndex() == 4:
            self._mark_results_dirty()

    def cycle_hover_annotation_style(self) -> None:
        self.hover_annotation_style = next_hover_annotation_style(self.hover_annotation_style)
        if self.stack.currentIndex() == 4:
            self._mark_results_dirty()

    def _schedule_results_render(self) -> None:
        if self._building_results:
            self._pending_results_render = True
            return
        self._results_render_timer.start()

    def _set_results_dirty(self, dirty: bool) -> None:
        self._results_dirty = dirty
        self.results_page.set_update_pending(dirty)

    def _mark_results_dirty(self) -> None:
        if self.prepared is None or self.current_dataset1 is None or self.current_dataset2 is None:
            return
        self._set_results_dirty(True)
        self.results_page.set_status("Results settings changed. Click Update Data & Plots to refresh.")

    def _update_results_from_button(self) -> None:
        if not self._results_dirty:
            return
        self.render_results()

    def go_back(self) -> None:
        if self.stack.currentIndex() > 0:
            self.stack.setCurrentIndex(self.stack.currentIndex() - 1)
            self._refresh_steps()

    def go_next(self) -> None:
        current = self.stack.currentIndex()
        try:
            if current == 0:
                self._complete_load_step()
            elif current == 1:
                self._complete_match_step()
            elif current == 2:
                self._complete_name_step()
            elif current == 3:
                self._complete_config_step()
            elif current == 4:
                return
        except SensorDataError as exc:
            QMessageBox.warning(self, "Check Inputs", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        if current < self.stack.count() - 1:
            self.stack.setCurrentIndex(current + 1)
        self._refresh_steps()

    def _complete_load_step(self) -> None:
        if self.load_page.input_mode() == LoadPage.OVERLAY_MODE:
            if not self.load_page.overlay_input():
                raise SensorDataError("Select one SG Plotly HTML overlay file.")
            self.preview_load_inputs()
            if self.dataset1 is None or self.dataset2 is None or self._overlay_pairs is None:
                raise SensorDataError(
                    "Load an SG Plotly HTML overlay containing matched Main:/Comp: channels, "
                    "or switch to separate dataset inputs."
                )
            self.match_page.set_columns(
                list(self._overlay_pairs.dataset1_columns),
                list(self._overlay_pairs.dataset2_columns),
            )
            self._auto_final_name_by_pair = dict(
                zip(
                    zip(self._overlay_pairs.dataset1_columns, self._overlay_pairs.dataset2_columns),
                    self._overlay_pairs.final_names,
                )
            )
            self._match_source_paths = (self.dataset1.path, self.dataset2.path)
            return

        path1, _, path2, _ = self.load_page.dataset_inputs()
        self.preview_load_inputs()
        if not path1 or not path2:
            raise SensorDataError("Select both dataset CSV or SG Plotly HTML files.")
        if self.dataset1 is None or self.dataset2 is None:
            raise SensorDataError("Load two valid dataset CSV or SG Plotly HTML files before continuing.")
        self.load_page.set_summaries(self.dataset1, self.dataset2)
        self.match_page.set_columns(self.dataset1.channels, self.dataset2.channels)
        self._auto_final_name_by_pair = None
        self._match_source_paths = (self.dataset1.path, self.dataset2.path)

    def preview_load_inputs(self) -> None:
        if self.load_page.input_mode() == LoadPage.OVERLAY_MODE:
            overlay_path = self.load_page.overlay_input()
            if overlay_path:
                self._preview_overlay_input(overlay_path)
            else:
                self.load_page.set_summary_status(
                    1,
                    "Reference: Main traces",
                    "Select one SG Plotly HTML overlay file.",
                )
                self.load_page.set_summary_status(2, "Candidate: Comp traces", "Waiting for overlay file.")
                self._clear_loaded_workflow_state()
            return

        self._overlay_pairs = None
        self._auto_final_name_by_pair = None
        path1, name1, path2, name2 = self.load_page.dataset_inputs()
        self.dataset1 = self._preview_dataset(path1, name1, "Dataset 1", 1, self.dataset1)
        self.dataset2 = self._preview_dataset(path2, name2, "Dataset 2", 2, self.dataset2)
        if self.dataset1 is None or self.dataset2 is None:
            self._clear_loaded_workflow_state()
            return

        loaded_paths = (self.dataset1.path, self.dataset2.path)
        if loaded_paths != self._match_source_paths:
            self.match_page.set_columns(self.dataset1.channels, self.dataset2.channels)
            self.name_page.set_pairs([], [])
            self.prepared = None
            self.current_dataset1 = None
            self.current_dataset2 = None
            self._clear_results_cache()
            self._match_source_paths = loaded_paths

    def _preview_overlay_input(self, path_text: str) -> None:
        path = Path(path_text)
        clean_display_name = display_name_from_path(path, "Overlay")
        try:
            overlay_dataset = load_dataset(path, clean_display_name)
            pairs = detect_main_comp_overlay_pairs(overlay_dataset)
        except SensorDataError as exc:
            self.load_page.set_summary_status(1, "Overlay HTML", f"Invalid: {exc}")
            self.load_page.set_summary_status(2, "Candidate: Comp traces", "Waiting for valid overlay file.")
            self._clear_loaded_workflow_state()
            return

        self.dataset1 = replace(overlay_dataset, display_name="Main")
        self.dataset2 = replace(overlay_dataset, display_name="Comp")
        self._overlay_pairs = pairs
        self._auto_final_name_by_pair = dict(
            zip(zip(pairs.dataset1_columns, pairs.dataset2_columns), pairs.final_names)
        )
        self.load_page.set_overlay_summaries(overlay_dataset, pairs)

        loaded_paths = (self.dataset1.path, self.dataset2.path)
        if loaded_paths != self._match_source_paths:
            self.match_page.set_columns(list(pairs.dataset1_columns), list(pairs.dataset2_columns))
            self.name_page.set_pairs([], [])
            self.prepared = None
            self.current_dataset1 = None
            self.current_dataset2 = None
            self._match_source_paths = loaded_paths

    def _preview_dataset(
        self,
        path_text: str,
        display_name: str,
        fallback_name: str,
        dataset_number: int,
        current_dataset: DatasetSpec | None,
    ) -> DatasetSpec | None:
        if not path_text:
            self.load_page.set_summary_status(dataset_number, fallback_name, "Not loaded")
            return None
        path = Path(path_text)
        clean_display_name = display_name.strip() or display_name_from_path(path, fallback_name)
        try:
            if current_dataset is not None and current_dataset.path == path:
                dataset = replace(current_dataset, display_name=clean_display_name)
            else:
                dataset = load_dataset(path, clean_display_name)
        except SensorDataError as exc:
            self.load_page.set_summary_status(dataset_number, fallback_name, f"Invalid: {exc}")
            return None
        self.load_page.set_dataset_summary(dataset_number, dataset)
        return dataset

    def _clear_loaded_workflow_state(self) -> None:
        self.dataset1 = None
        self.dataset2 = None
        self._match_source_paths = None
        self._overlay_pairs = None
        self._auto_final_name_by_pair = None
        self.match_page.set_columns([], [])
        self.name_page.set_pairs([], [])
        self.prepared = None
        self.current_dataset1 = None
        self.current_dataset2 = None
        self._clear_results_cache()

    def _complete_match_step(self) -> None:
        left_columns, right_columns = self.match_page.columns()
        if len(left_columns) != len(right_columns):
            raise SensorDataError("The matched channel lists must have the same length.")
        if not left_columns:
            raise SensorDataError("Keep at least one matched channel.")
        final_names = None
        if self._auto_final_name_by_pair:
            final_names = [
                self._auto_final_name_by_pair.get((left, right), left)
                for left, right in zip(left_columns, right_columns)
            ]
        self.name_page.set_pairs(left_columns, right_columns, final_names)

    def _complete_name_step(self) -> None:
        if self.dataset1 is None or self.dataset2 is None:
            raise SensorDataError("Load datasets before preparing channel names.")
        left_columns, right_columns = self.match_page.columns()
        self.prepared = prepare_comparison(
            self.dataset1,
            self.dataset2,
            left_columns,
            right_columns,
            self.name_page.final_names(),
        )
        self.current_dataset1 = self.prepared.dataset1_aligned.copy()
        self.current_dataset2 = self.prepared.dataset2_aligned.copy()
        self._clear_results_cache()
        self.config_page.set_ready(self.prepared)

    def _complete_config_step(self) -> None:
        if self.prepared is None:
            raise SensorDataError("Prepare datasets before analysis.")
        start_time, end_time = self.config_page.analysis_range()
        if start_time > end_time:
            raise SensorDataError("Analysis start time must not exceed end time.")
        self.results_page.set_ready(
            self.prepared,
            self.config_page.reference_index(),
            start_time,
            end_time,
        )
        self.render_results(verbose_progress=True)

    def _sync_reference_to_results(self) -> None:
        if self.prepared is None or self.stack.currentIndex() != 4:
            return
        self.results_page.reference_combo.setCurrentIndex(self.config_page.reference_index())

    def apply_sync(self) -> None:
        if self.prepared is None or self.current_dataset1 is None or self.current_dataset2 is None:
            QMessageBox.warning(self, "No Data", "Prepare datasets before applying synchronization.")
            return
        if not self.config_page.sync_checkbox.isChecked():
            QMessageBox.information(self, "Sync Disabled", "Enable manual time synchronization first.")
            return
        try:
            target_index = self.config_page.shift_target_index()
            shift_seconds = self.config_page.shift_seconds()
            if target_index == 0:
                self.current_dataset1, shift_samples = apply_sample_shift(self.current_dataset1, shift_seconds)
                shifted_name = self.prepared.dataset1.display_name
            else:
                self.current_dataset2, shift_samples = apply_sample_shift(self.current_dataset2, shift_seconds)
                shifted_name = self.prepared.dataset2.display_name
            self._clear_results_cache()
            self.config_page.set_status(
                f"{shifted_name} shifted by {shift_samples} samples ({shift_seconds:.3f} seconds)."
            )
            if self.stack.currentIndex() == 4:
                self.render_results()
        except SensorDataError as exc:
            QMessageBox.warning(self, "Synchronization", str(exc))

    def revert_sync(self) -> None:
        if self.prepared is None:
            QMessageBox.warning(self, "No Data", "Prepare datasets before reverting synchronization.")
            return
        self.current_dataset1 = self.prepared.dataset1_aligned.copy()
        self.current_dataset2 = self.prepared.dataset2_aligned.copy()
        self._clear_results_cache()
        self.config_page.set_status("Aligned datasets restored to the original prepared state.")
        if self.stack.currentIndex() == 4:
            self.render_results()

    def export_current_table(self) -> None:
        table = self.results_page.current_table()
        if table is None:
            QMessageBox.information(self, "No Table", "Select a result tab with a table before exporting.")
            return
        summary = self.results_page.table_bundle().summary if self.results_page.table_bundle() is not None else {}
        bundle = single_table_bundle(table, summary=summary, scope=f"Current table - {table.title}")
        self._export_bundle(bundle, "Export Current Table")

    def export_master_workbook(self) -> None:
        dialog = MasterExportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            if dialog.selected_scope() == MasterExportDialog.FULL_SCOPE:
                bundle = self._build_table_bundle_for_scope(full_aligned=True)
            else:
                bundle = self.results_page.table_bundle() or self._build_table_bundle_for_scope(full_aligned=False)
        except SensorDataError as exc:
            QMessageBox.warning(self, "Export Excel", str(exc))
            return
        self._export_bundle(bundle, "Export Master Workbook")

    def _export_bundle(self, bundle: AnalysisTableBundle, title: str) -> None:
        path_text, _ = QFileDialog.getSaveFileName(
            self,
            title,
            "sensor_comparison_analysis.xlsx",
            "Excel Workbook (*.xlsx)",
        )
        if not path_text:
            return
        try:
            output_path = write_analysis_workbook(path_text, bundle)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Export Excel", str(exc))
            return
        message = QMessageBox(self)
        message.setWindowTitle("Export Complete")
        message.setText(f"Excel workbook exported:\n{output_path}")
        open_button = message.addButton("Open Workbook", QMessageBox.ButtonRole.AcceptRole)
        message.addButton(QMessageBox.StandardButton.Ok)
        message.exec()
        if message.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_path)))

    def _build_table_bundle_for_scope(self, *, full_aligned: bool) -> AnalysisTableBundle:
        if self.prepared is None or self.current_dataset1 is None or self.current_dataset2 is None:
            raise SensorDataError("Prepare datasets before exporting analysis tables.")
        reference_df, target_df, reference_name, target_name = reference_target_frames(
            self.prepared,
            self.current_dataset1,
            self.current_dataset2,
            self.results_page.reference_index(),
        )
        if full_aligned:
            selected_columns = self.prepared.channels
            start_time = float(reference_df["Time"].min())
            end_time = float(reference_df["Time"].max())
            scope = "Full aligned data"
        else:
            selected_columns = self.results_page.selected_columns()
            start_time, end_time = self.results_page.analysis_range()
            scope = "Current analysis view"
        reference_filtered = filter_time_range(reference_df, start_time, end_time, selected_columns)
        target_filtered = filter_time_range(target_df, start_time, end_time, selected_columns)
        bundle = self._calculate_table_bundle(
            scope=scope,
            reference_filtered=reference_filtered,
            target_filtered=target_filtered,
            reference_name=reference_name,
            target_name=target_name,
            start_time=start_time,
            end_time=end_time,
            selected_columns=selected_columns,
            sign_deadband=self.results_page.sign_deadband(),
            absolute_tolerance=self.results_page.abs_tolerance(),
            relative_tolerance_pct=self.results_page.rel_tolerance_percent(),
            noise_floor=self.results_page.noise_floor(),
        )
        overlay_channels, overlay_filter_label = self._overlay_channels_for_export(selected_columns, bundle)
        return self._overlay_filtered_table_bundle(bundle, overlay_channels, overlay_filter_label)

    def _calculate_table_bundle(
        self,
        *,
        scope: str,
        reference_filtered: pd.DataFrame,
        target_filtered: pd.DataFrame,
        reference_name: str,
        target_name: str,
        start_time: float,
        end_time: float,
        selected_columns: Sequence[str],
        sign_deadband: float,
        absolute_tolerance: float,
        relative_tolerance_pct: float,
        noise_floor: float,
    ) -> AnalysisTableBundle:
        diagnostics = calculate_metric_diagnostics(
            reference_filtered,
            target_filtered,
            sign_deadband=sign_deadband,
        )
        metrics = calculate_statistical_metrics(
            reference_filtered,
            target_filtered,
            sign_deadband=sign_deadband,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance_pct=relative_tolerance_pct,
            noise_floor=noise_floor,
            diagnostics=diagnostics,
        )
        residuals = diagnostics.residual
        rolling = calculate_rolling_diagnostics(reference_filtered, target_filtered, sign_deadband=sign_deadband)
        lag = diagnostics.lag
        events = diagnostics.events
        quality = diagnostics.quality
        calibration = diagnostics.calibration
        frequency = diagnostics.frequency
        sign_agreement = diagnostics.sign
        scale_offset_metrics = calculate_scale_offset(target_filtered, reference_filtered)
        scaled_only, offset_only, scaled_offset = build_overlay_transforms(reference_filtered, target_filtered)
        return build_analysis_table_bundle(
            scope=scope,
            summary=self._analysis_summary(
                reference_name=reference_name,
                target_name=target_name,
                start_time=start_time,
                end_time=end_time,
                selected_columns=selected_columns,
                sign_deadband=sign_deadband,
                absolute_tolerance=absolute_tolerance,
                relative_tolerance_pct=relative_tolerance_pct,
                noise_floor=noise_floor,
            ),
            metrics=metrics,
            scale_offset_metrics=scale_offset_metrics,
            sign_metrics=sign_agreement.metrics,
            sign_status_frame=sign_agreement.status_frame,
            residual_metrics=residuals.metrics,
            residual_frame=residuals.residual_frame,
            rolling_frame=rolling.frame,
            lag_metrics=lag.metrics,
            lag_correlations=lag.correlations,
            event_metrics=events.metrics,
            quality_rows=quality.rows,
            calibration_metrics=calibration.metrics,
            frequency_metrics=frequency.metrics,
            frequency_spectrum=frequency.spectrum_frame,
            overlay_frames={
                "overlay_reference": reference_filtered,
                "overlay_candidate_original": target_filtered,
                "overlay_candidate_scaled": scaled_only,
                "overlay_candidate_offset": offset_only,
                "overlay_candidate_scaled_offset": scaled_offset,
            },
        )

    def _analysis_summary(
        self,
        *,
        reference_name: str,
        target_name: str,
        start_time: float,
        end_time: float,
        selected_columns: Sequence[str],
        sign_deadband: float,
        absolute_tolerance: float,
        relative_tolerance_pct: float,
        noise_floor: float,
    ) -> dict[str, object]:
        return {
            "Reference": reference_name,
            "Candidate": target_name,
            "Start Time": start_time,
            "End Time": end_time,
            "Channel Count": len(selected_columns),
            "Channels": ", ".join(selected_columns),
            "Sign Deadband": sign_deadband,
            "Abs tol": absolute_tolerance,
            "Rel tol %": relative_tolerance_pct,
            "Noise floor": noise_floor,
            "Dataset 1": self.prepared.dataset1.display_name if self.prepared is not None else "",
            "Dataset 2": self.prepared.dataset2.display_name if self.prepared is not None else "",
        }

    def _overlay_channels_from_filters(
        self,
        selected_columns: Sequence[str],
        sign_metrics: Sequence[dict[str, Any]],
        metrics: Sequence[dict[str, Any]],
        *,
        filter_to_sign_summary: bool,
        metric_filter: OverlayMetricFilterState,
    ) -> tuple[tuple[str, ...] | None, str]:
        channels = tuple(selected_columns)
        labels: list[str] = []
        if filter_to_sign_summary:
            sign_channels = set(
                SignAgreementView.filtered_channels_for(
                    selected_columns,
                    sign_metrics,
                    float(self.results_page.sign_plot.opposite_threshold_spin.value()),
                )
            )
            channels = tuple(channel for channel in channels if channel in sign_channels)
            labels.append("Sign Summary")
        metric_channels = metric_filtered_overlay_channels(channels, metrics, metric_filter)
        if metric_channels is not None:
            channels = metric_channels
            labels.append("Metric Filter")
        if not labels:
            return None, ""
        return channels, " + ".join(labels)

    def _overlay_channels_for_export(
        self,
        selected_columns: Sequence[str],
        bundle: AnalysisTableBundle,
    ) -> tuple[tuple[str, ...] | None, str]:
        if not self.results_page.filter_overlay_to_sign_summary() and not self.results_page.overlay_metric_filter_state().enabled():
            return None, ""
        current_bundle = self.results_page.table_bundle()
        metrics_table = (
            current_bundle.table("sign_agreement_summary")
            if current_bundle is not None
            else bundle.table("sign_agreement_summary")
        )
        sign_metrics = metrics_table.frame.to_dict("records") if metrics_table is not None else []
        metric_table = bundle.table("metrics")
        metric_rows = metric_table.frame.to_dict("records") if metric_table is not None else []
        return self._overlay_channels_from_filters(
            selected_columns,
            sign_metrics,
            metric_rows,
            filter_to_sign_summary=self.results_page.filter_overlay_to_sign_summary(),
            metric_filter=self.results_page.overlay_metric_filter_state(),
        )

    def _filter_overlay_frame(self, frame: pd.DataFrame, overlay_channels: tuple[str, ...]) -> pd.DataFrame:
        if not overlay_channels:
            return pd.DataFrame()
        columns = ["Time", *[channel for channel in overlay_channels if channel in frame.columns]]
        if len(columns) == 1:
            return pd.DataFrame()
        return frame.loc[:, columns].copy()

    def _overlay_filtered_table_bundle(
        self,
        bundle: AnalysisTableBundle,
        overlay_channels: tuple[str, ...] | None,
        overlay_filter_label: str = "Sign Summary",
    ) -> AnalysisTableBundle:
        if overlay_channels is None:
            return bundle
        cache_key = (id(bundle), overlay_channels, overlay_filter_label)
        if self._overlay_table_cache_key == cache_key and self._overlay_table_cache is not None:
            return self._overlay_table_cache
        summary = dict(bundle.summary)
        summary.update(
            {
                "Overlay Filter": overlay_filter_label,
                "Overlay Channel Count": len(overlay_channels),
                "Overlay Channels": ", ".join(overlay_channels),
            }
        )
        tables = tuple(
            AnalysisTable(table.table_id, table.title, self._filter_overlay_frame(table.frame, overlay_channels))
            if table.table_id in OVERLAY_TABLE_IDS
            else table
            for table in bundle.tables
        )
        filtered_bundle = AnalysisTableBundle(scope=bundle.scope, summary=summary, tables=tables)
        self._overlay_table_cache_key = cache_key
        self._overlay_table_cache = filtered_bundle
        return filtered_bundle

    def _set_analysis_progress(self, message: str) -> None:
        self.config_page.set_status(message)
        self.results_page.set_status(message)
        QApplication.processEvents()

    def _clear_results_cache(self) -> None:
        self._filtered_cache_key = None
        self._filtered_cache = None
        self._stable_cache_key = None
        self._stable_cache = None
        self._sign_cache_key = None
        self._sign_cache = None
        self._base_metrics_cache_key = None
        self._base_metrics_cache = None
        self._metrics_cache_key = None
        self._metrics_cache = None
        self._overlay_table_cache_key = None
        self._overlay_table_cache = None
        self._figure_cache.clear()
        self._rendered_figures.clear()
        self._rendered_table_bundle = None

    def _results_snapshot(self) -> ResultsSnapshot:
        start_time, end_time = self.results_page.analysis_range()
        return ResultsSnapshot(
            reference_index=self.results_page.reference_index(),
            selected_columns=tuple(self.results_page.selected_columns()),
            start_time=start_time,
            end_time=end_time,
            sign_deadband=self.results_page.sign_deadband(),
            absolute_tolerance=self.results_page.abs_tolerance(),
            relative_tolerance_pct=self.results_page.rel_tolerance_percent(),
            noise_floor=self.results_page.noise_floor(),
            selected_metric_keys=tuple(self.results_page.selected_metric_keys()),
            hide_transforms=self.results_page.hide_transforms(),
            filter_overlay_to_sign_summary=self.results_page.filter_overlay_to_sign_summary(),
            overlay_metric_filter=self.results_page.overlay_metric_filter_state(),
        )

    def _data_cache_key(self, snapshot: ResultsSnapshot) -> tuple[Any, ...]:
        return (
            id(self.prepared),
            id(self.current_dataset1),
            id(self.current_dataset2),
            snapshot.reference_index,
            snapshot.start_time,
            snapshot.end_time,
            snapshot.selected_columns,
        )

    def _filtered_results(self, snapshot: ResultsSnapshot, data_key: tuple[Any, ...]) -> FilteredResultsData:
        if self._filtered_cache_key == data_key and self._filtered_cache is not None:
            return self._filtered_cache
        if self.prepared is None or self.current_dataset1 is None or self.current_dataset2 is None:
            raise SensorDataError("Prepare datasets before analysis.")
        reference_df, target_df, reference_name, target_name = reference_target_frames(
            self.prepared,
            self.current_dataset1,
            self.current_dataset2,
            snapshot.reference_index,
        )
        data = FilteredResultsData(
            reference_df=filter_time_range(reference_df, snapshot.start_time, snapshot.end_time, snapshot.selected_columns),
            target_df=filter_time_range(target_df, snapshot.start_time, snapshot.end_time, snapshot.selected_columns),
            reference_name=reference_name,
            target_name=target_name,
        )
        self._filtered_cache_key = data_key
        self._filtered_cache = data
        return data

    def _stable_results(
        self,
        data: FilteredResultsData,
        data_key: tuple[Any, ...],
        progress: Callable[[str], None] | None = None,
    ) -> StableResultsArtifacts:
        if self._stable_cache_key == data_key and self._stable_cache is not None:
            return self._stable_cache
        if progress is not None:
            progress("Calculating scale and offset transforms...")
        scale_offset_metrics = calculate_scale_offset(data.target_df, data.reference_df)
        if progress is not None:
            progress("Building overlay transforms...")
        scaled_only, offset_only, scaled_offset = build_overlay_transforms(data.reference_df, data.target_df)
        if progress is not None:
            progress("Calculating residual diagnostics...")
        residual = calculate_residual_diagnostics(data.reference_df, data.target_df)
        if progress is not None:
            progress("Calculating lag diagnostics...")
        lag = calculate_lag_diagnostics(data.reference_df, data.target_df)
        if progress is not None:
            progress("Calculating event timing diagnostics...")
        events = calculate_event_timing_diagnostics(data.reference_df, data.target_df)
        quality = calculate_data_quality(data.reference_df, data.target_df, progress=progress)
        if progress is not None:
            progress("Calculating calibration diagnostics...")
        calibration = calculate_calibration_diagnostics(data.reference_df, data.target_df)
        if progress is not None:
            progress("Calculating frequency diagnostics...")
        frequency = calculate_frequency_diagnostics(data.reference_df, data.target_df)
        stable = StableResultsArtifacts(
            residual=residual,
            lag=lag,
            events=events,
            quality=quality,
            calibration=calibration,
            frequency=frequency,
            scale_offset_metrics=scale_offset_metrics,
            scaled_only=scaled_only,
            offset_only=offset_only,
            scaled_offset=scaled_offset,
        )
        self._stable_cache_key = data_key
        self._stable_cache = stable
        return stable

    def _sign_results(
        self,
        data: FilteredResultsData,
        data_key: tuple[Any, ...],
        sign_deadband: float,
        progress: Callable[[str], None] | None = None,
    ) -> tuple[tuple[Any, ...], SignResultsArtifacts]:
        sign_key = (*data_key, sign_deadband)
        if self._sign_cache_key == sign_key and self._sign_cache is not None:
            return sign_key, self._sign_cache
        if progress is not None:
            progress("Calculating sign agreement...")
        sign_agreement = calculate_sign_agreement(data.reference_df, data.target_df, deadband=sign_deadband)
        if progress is not None:
            progress("Calculating rolling diagnostics...")
        rolling = calculate_rolling_diagnostics(data.reference_df, data.target_df, sign_deadband=sign_deadband)
        sign = SignResultsArtifacts(
            sign_agreement=sign_agreement,
            rolling=rolling,
        )
        self._sign_cache_key = sign_key
        self._sign_cache = sign
        return sign_key, sign

    def _metric_diagnostics(self, stable: StableResultsArtifacts, sign: SignResultsArtifacts) -> MetricDiagnostics:
        return MetricDiagnostics(
            sign=sign.sign_agreement,
            residual=stable.residual,
            lag=stable.lag,
            events=stable.events,
            quality=stable.quality,
            calibration=stable.calibration,
            frequency=stable.frequency,
        )

    def _analysis_bundle(
        self,
        *,
        data: FilteredResultsData,
        stable: StableResultsArtifacts,
        sign: SignResultsArtifacts,
        snapshot: ResultsSnapshot,
        metrics: list[dict[str, float | str]],
    ) -> AnalysisTableBundle:
        return build_analysis_table_bundle(
            scope="Current analysis view",
            summary=self._analysis_summary(
                reference_name=data.reference_name,
                target_name=data.target_name,
                start_time=snapshot.start_time,
                end_time=snapshot.end_time,
                selected_columns=snapshot.selected_columns,
                sign_deadband=snapshot.sign_deadband,
                absolute_tolerance=snapshot.absolute_tolerance,
                relative_tolerance_pct=snapshot.relative_tolerance_pct,
                noise_floor=snapshot.noise_floor,
            ),
            metrics=metrics,
            scale_offset_metrics=stable.scale_offset_metrics,
            sign_metrics=sign.sign_agreement.metrics,
            sign_status_frame=sign.sign_agreement.status_frame,
            residual_metrics=stable.residual.metrics,
            residual_frame=stable.residual.residual_frame,
            rolling_frame=sign.rolling.frame,
            lag_metrics=stable.lag.metrics,
            lag_correlations=stable.lag.correlations,
            event_metrics=stable.events.metrics,
            quality_rows=stable.quality.rows,
            calibration_metrics=stable.calibration.metrics,
            frequency_metrics=stable.frequency.metrics,
            frequency_spectrum=stable.frequency.spectrum_frame,
            overlay_frames={
                "overlay_reference": data.reference_df,
                "overlay_candidate_original": data.target_df,
                "overlay_candidate_scaled": stable.scaled_only,
                "overlay_candidate_offset": stable.offset_only,
                "overlay_candidate_scaled_offset": stable.scaled_offset,
            },
        )

    def _metrics_table_bundle(
        self,
        previous_bundle: AnalysisTableBundle,
        *,
        data: FilteredResultsData,
        snapshot: ResultsSnapshot,
        metrics: list[dict[str, float | str]],
    ) -> AnalysisTableBundle:
        summary = self._analysis_summary(
            reference_name=data.reference_name,
            target_name=data.target_name,
            start_time=snapshot.start_time,
            end_time=snapshot.end_time,
            selected_columns=snapshot.selected_columns,
            sign_deadband=snapshot.sign_deadband,
            absolute_tolerance=snapshot.absolute_tolerance,
            relative_tolerance_pct=snapshot.relative_tolerance_pct,
            noise_floor=snapshot.noise_floor,
        )
        tables = tuple(
            AnalysisTable("metrics", "Statistical Metrics", pd.DataFrame([dict(metric) for metric in metrics]))
            if table.table_id == "metrics"
            else AnalysisTable("certification_ranking", "Certification Ranking", certification_ranking_frame(metrics))
            if table.table_id == "certification_ranking"
            else table
            for table in previous_bundle.tables
        )
        return AnalysisTableBundle(scope=previous_bundle.scope, summary=summary, tables=tables)

    def _metrics_results(
        self,
        *,
        data: FilteredResultsData,
        stable: StableResultsArtifacts,
        sign: SignResultsArtifacts,
        sign_key: tuple[Any, ...],
        snapshot: ResultsSnapshot,
        progress: Callable[[str], None] | None = None,
    ) -> tuple[tuple[Any, ...], MetricsResultsArtifacts]:
        metrics_key = (*sign_key, snapshot.absolute_tolerance, snapshot.relative_tolerance_pct, snapshot.noise_floor)
        if self._metrics_cache_key == metrics_key and self._metrics_cache is not None:
            return metrics_key, self._metrics_cache
        if self._base_metrics_cache_key == sign_key and self._base_metrics_cache is not None:
            if progress is not None:
                progress("Updating tolerance metrics...")
            metrics = update_metric_tolerances(
                self._base_metrics_cache,
                data.reference_df,
                data.target_df,
                absolute_tolerance=snapshot.absolute_tolerance,
                relative_tolerance_pct=snapshot.relative_tolerance_pct,
                noise_floor=snapshot.noise_floor,
            )
        else:
            if progress is not None:
                progress("Calculating statistical metrics...")
            metrics = calculate_statistical_metrics(
                data.reference_df,
                data.target_df,
                sign_deadband=snapshot.sign_deadband,
                absolute_tolerance=snapshot.absolute_tolerance,
                relative_tolerance_pct=snapshot.relative_tolerance_pct,
                noise_floor=snapshot.noise_floor,
                diagnostics=self._metric_diagnostics(stable, sign),
            )
            self._base_metrics_cache_key = sign_key
            self._base_metrics_cache = [dict(metric) for metric in metrics]
        if progress is not None:
            progress("Building analysis tables...")
        result = MetricsResultsArtifacts(
            metrics=metrics,
            table_bundle=(
                self._metrics_table_bundle(
                    self._metrics_cache.table_bundle,
                    data=data,
                    snapshot=snapshot,
                    metrics=metrics,
                )
                if self._metrics_cache is not None
                and self._metrics_cache_key is not None
                and self._metrics_cache_key[: len(sign_key)] == sign_key
                else self._analysis_bundle(
                    data=data,
                    stable=stable,
                    sign=sign,
                    snapshot=snapshot,
                    metrics=metrics,
                )
            ),
        )
        self._metrics_cache_key = metrics_key
        self._metrics_cache = result
        return metrics_key, result

    def _cached_figure(self, name: str, key: tuple[Any, ...], builder: Callable[[], Any]) -> Any:
        cached = self._figure_cache.get(name)
        if cached is not None and cached[0] == key:
            return cached[1]
        figure = builder()
        self._figure_cache[name] = (key, figure)
        return figure

    def _certification_display_key(self) -> tuple[Any, ...]:
        return (
            self.results_page.certification_label_mode(),
            self.results_page.certification_max_labels(),
            self.results_page.certification_highlighted_channels(),
        )

    def _build_certification_display_figure(self) -> Any | None:
        if self._metrics_cache is None or self._filtered_cache is None:
            return None
        display_key = self._certification_display_key()
        style_key = (self.legend_position, self.hover_annotation_style)
        name_key = (self._filtered_cache.reference_name, self._filtered_cache.target_name)
        return self._cached_figure(
            "certification",
            (*(self._metrics_cache_key or ()), *display_key, *style_key, *name_key),
            lambda: build_certification_ranking_figure(
                self._metrics_cache.metrics,
                self._filtered_cache.reference_name,
                self._filtered_cache.target_name,
                legend_position=self.legend_position,
                hover_annotation_style=self.hover_annotation_style,
                highlighted_channels=display_key[2],
                label_mode=display_key[0],
                max_labels=display_key[1],
            ),
        )

    def _refresh_certification_display(self) -> None:
        figure = self._build_certification_display_figure()
        if figure is None:
            return
        tab_index = self.FIGURE_TABS["certification"]
        self.results_page.set_tab_figure(tab_index, figure)
        self._rendered_figures[tab_index] = figure

    def _result_figures(
        self,
        *,
        data: FilteredResultsData,
        stable: StableResultsArtifacts,
        sign: SignResultsArtifacts,
        metrics_result: MetricsResultsArtifacts,
        data_key: tuple[Any, ...],
        sign_key: tuple[Any, ...],
        metrics_key: tuple[Any, ...],
        snapshot: ResultsSnapshot,
        overlay_channels: tuple[str, ...] | None,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        style_key = (self.legend_position, self.hover_annotation_style)
        name_key = (data.reference_name, data.target_name)
        tolerance_metric_keys = {"Within Tolerance Abs (%)", "Within Tolerance Rel (%)"}
        metrics_value_key = (
            metrics_key
            if tolerance_metric_keys.intersection(snapshot.selected_metric_keys)
            else sign_key
        )
        certification_display_key = self._certification_display_key()
        return {
            "metrics": self._cached_figure(
                "metrics",
                (*metrics_value_key, snapshot.selected_metric_keys, *style_key, *name_key),
                lambda: (
                    progress("Building metrics figure...") if progress is not None else None,
                    build_metrics_figure(
                        metrics_result.metrics,
                        data.reference_name,
                        data.target_name,
                        selected_metric_keys=list(snapshot.selected_metric_keys),
                        legend_position=self.legend_position,
                        hover_annotation_style=self.hover_annotation_style,
                    ),
                )[1],
            ),
            "certification": self._cached_figure(
                "certification",
                (*metrics_key, *certification_display_key, *style_key, *name_key),
                lambda: (
                    progress("Building certification ranking figure...") if progress is not None else None,
                    build_certification_ranking_figure(
                        metrics_result.metrics,
                        data.reference_name,
                        data.target_name,
                        legend_position=self.legend_position,
                        hover_annotation_style=self.hover_annotation_style,
                        highlighted_channels=certification_display_key[2],
                        label_mode=certification_display_key[0],
                        max_labels=certification_display_key[1],
                    ),
                )[1],
            ),
            "scale": self._cached_figure(
                "scale",
                (*data_key, *style_key, data.reference_name),
                lambda: (
                    progress("Building scale and offset figure...") if progress is not None else None,
                    build_scale_offset_figure(
                        stable.scale_offset_metrics,
                        data.reference_name,
                        legend_position=self.legend_position,
                        hover_annotation_style=self.hover_annotation_style,
                    ),
                )[1],
            ),
            "sign": self._cached_figure(
                "sign",
                (*sign_key, *name_key),
                lambda: (
                    progress("Building sign agreement figure...") if progress is not None else None,
                    build_sign_agreement_plot_data(
                        sign.sign_agreement.status_frame,
                        sign.sign_agreement.metrics,
                        data.reference_name,
                        data.target_name,
                        deadband=snapshot.sign_deadband,
                    ),
                )[1],
            ),
            "residual": self._cached_figure(
                "residual",
                (*data_key, snapshot.absolute_tolerance, snapshot.relative_tolerance_pct, *style_key, *name_key),
                lambda: (
                    progress("Building residual figure...") if progress is not None else None,
                    build_residual_figure(
                        stable.residual.residual_frame,
                        stable.residual.metrics,
                        data.reference_name,
                        data.target_name,
                        reference_frame=data.reference_df,
                        absolute_tolerance=snapshot.absolute_tolerance,
                        relative_tolerance_pct=snapshot.relative_tolerance_pct,
                        legend_position=self.legend_position,
                        hover_annotation_style=self.hover_annotation_style,
                    ),
                )[1],
            ),
            "rolling": self._cached_figure(
                "rolling",
                (*sign_key, *style_key),
                lambda: (
                    progress("Building rolling diagnostics figure...") if progress is not None else None,
                    build_rolling_metrics_figure(
                        sign.rolling.frame,
                        sign.rolling.window_size,
                        legend_position=self.legend_position,
                        hover_annotation_style=self.hover_annotation_style,
                    ),
                )[1],
            ),
            "lag": self._cached_figure(
                "lag",
                (*data_key, *style_key),
                lambda: (
                    progress("Building lag figure...") if progress is not None else None,
                    build_lag_figure(
                        stable.lag.correlations,
                        stable.lag.metrics,
                        legend_position=self.legend_position,
                        hover_annotation_style=self.hover_annotation_style,
                    ),
                )[1],
            ),
            "calibration": self._cached_figure(
                "calibration",
                (*data_key, *style_key, *name_key),
                lambda: (
                    progress("Building calibration figure...") if progress is not None else None,
                    build_calibration_figure(
                        data.reference_df,
                        data.target_df,
                        stable.calibration.metrics,
                        data.reference_name,
                        data.target_name,
                        legend_position=self.legend_position,
                        hover_annotation_style=self.hover_annotation_style,
                    ),
                )[1],
            ),
            "frequency": self._cached_figure(
                "frequency",
                (*data_key, *style_key),
                lambda: (
                    progress("Building frequency figure...") if progress is not None else None,
                    build_frequency_figure(
                        stable.frequency,
                        legend_position=self.legend_position,
                        hover_annotation_style=self.hover_annotation_style,
                    ),
                )[1],
            ),
            "overlay": self._cached_figure(
                "overlay",
                (*data_key, snapshot.hide_transforms, overlay_channels, *style_key, *name_key),
                lambda: (
                    progress("Building overlay figure...") if progress is not None else None,
                    build_overlay_figure(
                        data.reference_df,
                        data.target_df,
                        stable.scaled_only,
                        stable.offset_only,
                        stable.scaled_offset,
                        data.reference_name,
                        data.target_name,
                        hide_transforms=snapshot.hide_transforms,
                        channels=overlay_channels,
                        legend_position=self.legend_position,
                        hover_annotation_style=self.hover_annotation_style,
                    ),
                )[1],
            ),
        }

    def _apply_cached_results(
        self,
        figures: dict[str, Any],
        table_bundle: AnalysisTableBundle,
        *,
        overlay_channels: tuple[str, ...] | None,
    ) -> None:
        overlay_mask = apply_overlay_channel_visibility(figures["overlay"], overlay_channels)
        if self._rendered_table_bundle is not table_bundle:
            self.results_page.set_table_bundle(table_bundle)
            self._rendered_table_bundle = table_bundle
        for name, tab_index in self.FIGURE_TABS.items():
            figure = figures[name]
            if self._rendered_figures.get(tab_index) is figure:
                continue
            self.results_page.set_tab_figure(tab_index, figure)
            self._rendered_figures[tab_index] = figure
        self.results_page.apply_overlay_trace_visibility(overlay_mask)

    def render_results(self, *, verbose_progress: bool = False) -> bool:
        self._results_render_timer.stop()
        if self._building_results:
            self._pending_results_render = True
            return False
        if self.prepared is None or self.current_dataset1 is None or self.current_dataset2 is None:
            return False
        self._pending_results_render = False
        self._building_results = True
        rendered = False
        try:
            progress = self._set_analysis_progress if verbose_progress else None
            if verbose_progress:
                self._set_analysis_progress("Preparing analysis settings...")
            snapshot = self._results_snapshot()
            if verbose_progress:
                self._set_analysis_progress(
                    f"Filtering {len(snapshot.selected_columns)} channels from {snapshot.start_time:g} to {snapshot.end_time:g}..."
                )
            data_key = self._data_cache_key(snapshot)
            data = self._filtered_results(snapshot, data_key)
            stable = self._stable_results(data, data_key, progress)
            sign_key, sign = self._sign_results(data, data_key, snapshot.sign_deadband, progress)
            metrics_key, metrics_result = self._metrics_results(
                data=data,
                stable=stable,
                sign=sign,
                sign_key=sign_key,
                snapshot=snapshot,
                progress=progress,
            )
            overlay_channels, overlay_filter_label = self._overlay_channels_from_filters(
                snapshot.selected_columns,
                sign.sign_agreement.metrics,
                metrics_result.metrics,
                filter_to_sign_summary=snapshot.filter_overlay_to_sign_summary,
                metric_filter=snapshot.overlay_metric_filter,
            )
            table_bundle = self._overlay_filtered_table_bundle(
                metrics_result.table_bundle,
                overlay_channels,
                overlay_filter_label,
            )
            figures = self._result_figures(
                data=data,
                stable=stable,
                sign=sign,
                metrics_result=metrics_result,
                data_key=data_key,
                sign_key=sign_key,
                metrics_key=metrics_key,
                snapshot=snapshot,
                overlay_channels=overlay_channels,
                progress=progress,
            )
            if progress is not None:
                progress("Rendering result plots...")
            self._apply_cached_results(figures, table_bundle, overlay_channels=overlay_channels)
            rendered_status = (
                f"Rendered {len(snapshot.selected_columns)} channels from {snapshot.start_time:g} to {snapshot.end_time:g}; "
                f"{len(snapshot.selected_metric_keys)} aggregate metrics selected; sign deadband +/- {snapshot.sign_deadband:g}; "
                f"abs tol {snapshot.absolute_tolerance:g}; rel tol {snapshot.relative_tolerance_pct:g}%; "
                f"noise floor {snapshot.noise_floor:g}; "
                f"hover annotations: {hover_annotation_style_label(self.hover_annotation_style)} (H toggles)."
            )
            if verbose_progress:
                self._set_analysis_progress("Opening Analyze Results...")
            self.results_page.set_status(rendered_status)
            self._set_results_dirty(False)
            rendered = True
        except SensorDataError as exc:
            self.results_page.set_status(str(exc))
            if verbose_progress:
                self.config_page.set_status(str(exc))
                QApplication.processEvents()
        except Exception as exc:
            message = f"Plot update failed: {exc}"
            self.results_page.set_status(message)
            if verbose_progress:
                self.config_page.set_status(message)
                QApplication.processEvents()
        finally:
            self._building_results = False
            if self._pending_results_render:
                self._pending_results_render = False
                self._results_render_timer.start()
        return rendered

    def open_help_document(self) -> None:
        path = help_pdf_path()
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.warning(self, "Help Missing", f"Help document not found: {path}")

    def _refresh_steps(self) -> None:
        current = self.stack.currentIndex()
        for index, (card, label) in enumerate(zip(self.step_cards, self.step_labels)):
            state = "current" if index == current else "completed" if index < current else "upcoming"
            card.setProperty("state", state)
            label.setProperty("state", state)
            for widget in (card, label):
                widget.style().unpolish(widget)
                widget.style().polish(widget)
        self.back_button.setEnabled(current > 0)
        if current == self.stack.count() - 1:
            next_text = "Finish"
        elif current == 0 and self.load_page.input_mode() == LoadPage.OVERLAY_MODE:
            next_text = "Review Matched Channels"
        else:
            next_text = "Next"
        self.next_button.setText(next_text)
        self.next_button.setEnabled(current < self.stack.count() - 1)


def create_window_for_smoke(plot_view_factory: PlotViewFactory | None = None) -> SensorComparisonWindow:
    app = QApplication.instance()
    if app is None:
        QApplication([])
    return SensorComparisonWindow(plot_view_factory=plot_view_factory)
