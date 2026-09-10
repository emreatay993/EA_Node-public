from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .plots import SignAgreementPlotData
from .table_views import CollapsedPaneRail, collapsed_pane_rail, pane_handle_button


STATUS_COLORS = {
    "Opposite": "#b64a4a",
    "Deadband": "#9aa7b5",
    "Same": "#3a8f5a",
}

STATUS_LABELS = {-1: "Opposite", 0: "Deadband", 1: "Same"}


class SignAgreementView(QWidget):
    sign_deadband_changed = pyqtSignal(float)
    summary_filter_changed = pyqtSignal()

    SUMMARY_EXPANDED_MIN_WIDTH = 420
    SUMMARY_DEFAULT_WIDTH = 520
    COLLAPSED_RAIL_WIDTH = CollapsedPaneRail.EDGE_REVEAL_WIDTH

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.figure: SignAgreementPlotData | None = None
        self.plot_data: SignAgreementPlotData | None = None
        self.refresh_count = 0
        self._needs_render = False
        self._time_values = np.array([], dtype=float)
        self._all_channels: list[str] = []
        self._channels: list[str] = []
        self._all_status_matrix = np.empty((0, 0), dtype=int)
        self._status_matrix = np.empty((0, 0), dtype=int)
        self._metrics_by_channel: dict[str, dict[str, Any]] = {}
        self.summary_panel_collapsed = False
        self._summary_expanded_width = self.SUMMARY_DEFAULT_WIDTH

        pg.setConfigOptions(antialias=False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(14)
        self.title_label = QLabel("Sign Agreement")
        self.title_label.setObjectName("SignAgreementTitle")
        header.addWidget(self.title_label, 1)
        for label, color in [
            ("Same", STATUS_COLORS["Same"]),
            ("Deadband", STATUS_COLORS["Deadband"]),
            ("Opposite", STATUS_COLORS["Opposite"]),
        ]:
            header.addWidget(self._legend_item(label, color))
        layout.addLayout(header)

        self.summary_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.summary_splitter.setChildrenCollapsible(False)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setObjectName("SignAgreementPlot")
        self.plot_widget.setBackground("w")
        self.plot_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        plot_item = self.plot_widget.getPlotItem()
        plot_item.hideButtons()
        plot_item.setMenuEnabled(False)
        plot_item.setMouseEnabled(x=True, y=False)
        plot_item.setLabel("bottom", "Time")
        plot_item.setLabel("left", "Channel")
        plot_item.showGrid(x=True, y=False, alpha=0.18)
        plot_item.invertY(True)
        self.image_item = pg.ImageItem(axisOrder="col-major")
        self.image_item.setLookupTable(
            np.array(
                [
                    [182, 74, 74, 255],
                    [154, 167, 181, 255],
                    [58, 143, 90, 255],
                ],
                dtype=np.ubyte,
            )
        )
        plot_item.addItem(self.image_item)
        self.plot_widget.scene().sigMouseMoved.connect(self._handle_mouse_moved)
        self.summary_splitter.addWidget(self.plot_widget)

        self.summary_shell = QWidget()
        self.summary_shell.setObjectName("CollapsibleColumnShell")
        self.summary_shell.setMinimumWidth(self.SUMMARY_EXPANDED_MIN_WIDTH)
        summary_shell_layout = QHBoxLayout(self.summary_shell)
        summary_shell_layout.setContentsMargins(0, 0, 0, 0)
        summary_shell_layout.setSpacing(0)

        self.summary_sidebar = QFrame()
        self.summary_sidebar.setObjectName("SignSummaryPanel")
        summary_layout = QVBoxLayout(self.summary_sidebar)
        summary_layout.setContentsMargins(12, 12, 12, 12)
        summary_layout.setSpacing(8)
        summary_header = QHBoxLayout()
        summary_header.setSpacing(8)
        title_filter_layout = QVBoxLayout()
        title_filter_layout.setContentsMargins(0, 0, 0, 0)
        title_filter_layout.setSpacing(5)
        summary_title = QLabel("Channel Summary")
        summary_title.setObjectName("SectionTitle")
        title_filter_layout.addWidget(summary_title)
        self.opposite_threshold_spin = self._threshold_spinbox(
            "OppositeThresholdSpin",
            "Show channels with opposite sign percentage above this threshold.",
        )
        title_filter_layout.addLayout(
            self._threshold_row("% opposite sign in each channel >", self.opposite_threshold_spin)
        )
        self.sign_deadband_spin = self._sign_deadband_spinbox()
        title_filter_layout.addLayout(self._threshold_row("Sign deadband +/-", self.sign_deadband_spin))
        summary_header.addLayout(title_filter_layout, 1)
        self.summary_collapse_button = pane_handle_button(
            "chevrons-right.svg",
            "Collapse Channel Summary",
            "Collapse Channel Summary",
        )
        self.summary_collapse_button.clicked.connect(self.collapse_summary_panel)
        summary_header.addWidget(self.summary_collapse_button)
        summary_layout.addLayout(summary_header)
        self.summary_table = QTableWidget()
        self.summary_table.setObjectName("SignSummaryTable")
        self.summary_table.setColumnCount(5)
        self.summary_table.setHorizontalHeaderLabels(["Channel", "Same", "Opposite", "Deadband", "Max Mismatch"])
        self.summary_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.summary_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.summary_table.setAlternatingRowColors(True)
        self.summary_table.verticalHeader().setVisible(False)
        horizontal_header = self.summary_table.horizontalHeader()
        horizontal_header.setSectionsMovable(True)
        horizontal_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate([132, 76, 92, 92, 112]):
            self.summary_table.setColumnWidth(column, width)
        summary_layout.addWidget(self.summary_table, 1)
        self.summary_restore_rail, self.summary_restore_handle = collapsed_pane_rail(
            "Channel Summary",
            "Show Channel Summary",
            "Show Channel Summary",
            theme="panel",
            restore_callback=self.expand_summary_panel,
            overlay_parent=self,
            tab_top_margin=0,
        )
        self.summary_restore_rail.hide()
        summary_shell_layout.addWidget(self.summary_sidebar)
        summary_shell_layout.addWidget(self.summary_restore_rail)
        self.summary_splitter.addWidget(self.summary_shell)
        self.summary_splitter.setStretchFactor(0, 1)
        self.summary_splitter.setStretchFactor(1, 0)
        self.summary_splitter.setSizes([900, self.SUMMARY_DEFAULT_WIDTH])
        layout.addWidget(self.summary_splitter, 1)

        self.hover_label = QLabel("No sign-agreement data loaded.")
        self.hover_label.setObjectName("SignHoverLabel")
        layout.addWidget(self.hover_label)

    def set_figure(self, plot_data: Any) -> None:
        if not isinstance(plot_data, SignAgreementPlotData):
            self.clear()
            return
        self.figure = plot_data
        self.plot_data = plot_data
        self._needs_render = True
        if self.isVisible():
            self.refresh_plot()

    def refresh_plot(self) -> None:
        self.refresh_count += 1
        if self.plot_data is not None:
            if self._needs_render:
                self._render_plot_data(self.plot_data)
                self._needs_render = False
            self.plot_widget.getPlotItem().enableAutoRange()

    def clear(self) -> None:
        self.figure = None
        self.plot_data = None
        self._needs_render = False
        self._time_values = np.array([], dtype=float)
        self._all_channels = []
        self._channels = []
        self._all_status_matrix = np.empty((0, 0), dtype=int)
        self._status_matrix = np.empty((0, 0), dtype=int)
        self._metrics_by_channel = {}
        self.image_item.clear()
        self.summary_table.setRowCount(0)
        self.title_label.setText("Sign Agreement")
        self.hover_label.setText("No sign-agreement data loaded.")

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.refresh_plot()

    def _render_plot_data(self, plot_data: SignAgreementPlotData) -> None:
        status_frame = plot_data.status_frame
        self._all_channels = [column for column in status_frame.columns if column != "Time"]
        self._time_values = status_frame["Time"].to_numpy(dtype=float) if "Time" in status_frame else np.array([], dtype=float)
        if not self._all_channels or not len(self._time_values):
            self.clear()
            return

        self._all_status_matrix = status_frame[self._all_channels].to_numpy(dtype=int)
        self._metrics_by_channel = {str(metric["Channel"]): metric for metric in plot_data.metrics}
        self.title_label.setText(
            f"Sign Agreement - {plot_data.reference_name} vs {plot_data.target_name} "
            f"(deadband +/- {plot_data.deadband:g})"
        )
        self.set_sign_deadband(plot_data.deadband)
        self._apply_channel_filter()

    def _apply_channel_filter(self, _value: float | None = None) -> None:
        if self.plot_data is None or not len(self._time_values):
            return
        opposite_threshold = float(self.opposite_threshold_spin.value())
        visible_channels = self.filtered_channels()
        index_by_channel = {channel: index for index, channel in enumerate(self._all_channels)}
        channel_indices = [index_by_channel[channel] for channel in visible_channels]
        self._channels = visible_channels
        self._status_matrix = (
            self._all_status_matrix[:, channel_indices]
            if channel_indices
            else np.empty((len(self._time_values), 0), dtype=int)
        )
        self._render_visible_channels(self._active_filter_text(opposite_threshold))
        self._fill_summary_table()

    @staticmethod
    def filtered_channels_for(
        channels: Sequence[str],
        metrics: Sequence[Mapping[str, Any]],
        opposite_threshold: float,
    ) -> list[str]:
        if opposite_threshold <= 0.0:
            return list(channels)
        metrics_by_channel = {str(metric.get("Channel", "")): metric for metric in metrics}
        return [
            channel
            for channel in channels
            if float(metrics_by_channel.get(channel, {}).get("Sign Mismatch (%)", 0.0)) > opposite_threshold
        ]

    def filtered_channels(self) -> list[str]:
        return self.filtered_channels_for(
            self._all_channels,
            list(self._metrics_by_channel.values()),
            float(self.opposite_threshold_spin.value()),
        )

    def _render_visible_channels(self, active_filter_text: str) -> None:
        left = float(self._time_values[0])
        right = float(self._time_values[-1])
        width = right - left
        if width <= 0:
            width = 1.0
        if not self._channels:
            self.image_item.clear()
            self.plot_widget.getPlotItem().getAxis("left").setTicks([[]])
            self.plot_widget.setXRange(left, right if right > left else left + width, padding=0.01)
            self.plot_widget.setYRange(-0.5, 0.5, padding=0)
            self.hover_label.setText(f"No channels match {active_filter_text}.")
            return

        image_matrix = np.clip(self._status_matrix + 1, 0, 2)
        self.image_item.setImage(image_matrix, autoLevels=False, levels=(0, 2))
        self.image_item.setRect(QRectF(left, -0.5, width, len(self._channels)))

        y_axis = self.plot_widget.getPlotItem().getAxis("left")
        y_axis.setTicks([[(index, channel) for index, channel in enumerate(self._channels)]])
        self.plot_widget.setXRange(left, right if right > left else left + width, padding=0.01)
        self.plot_widget.setYRange(-0.5, len(self._channels) - 0.5, padding=0)
        if not active_filter_text:
            self.hover_label.setText(f"{len(self._channels)} channels x {len(self._time_values)} time samples rendered.")
        else:
            self.hover_label.setText(
                f"{len(self._channels)} of {len(self._all_channels)} channels match {active_filter_text}."
            )

    def _active_filter_text(self, opposite_threshold: float) -> str:
        filters = []
        if opposite_threshold > 0.0:
            filters.append(f"opposite > {opposite_threshold:g}%")
        return " and ".join(filters)

    def _threshold_spinbox(self, object_name: str, tooltip: str) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setObjectName(object_name)
        spinbox.setRange(0.0, 100.0)
        spinbox.setDecimals(1)
        spinbox.setSingleStep(1.0)
        spinbox.setSuffix("%")
        spinbox.setKeyboardTracking(False)
        spinbox.setFixedWidth(116)
        spinbox.setToolTip(tooltip)
        spinbox.valueChanged.connect(self._apply_channel_filter)
        spinbox.valueChanged.connect(lambda _value: self.summary_filter_changed.emit())
        return spinbox

    def _sign_deadband_spinbox(self) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setObjectName("SignDeadbandSpin")
        spinbox.setKeyboardTracking(False)
        spinbox.setDecimals(6)
        spinbox.setRange(0, 999999999)
        spinbox.setSingleStep(0.001)
        spinbox.setToolTip("Treat values from -deadband to +deadband as neutral when calculating sign agreement.")
        spinbox.setFixedWidth(118)
        spinbox.valueChanged.connect(self.sign_deadband_changed)
        return spinbox

    def set_sign_deadband(self, value: float) -> None:
        if self.sign_deadband_spin.value() == value:
            return
        self.sign_deadband_spin.blockSignals(True)
        self.sign_deadband_spin.setValue(value)
        self.sign_deadband_spin.blockSignals(False)

    def _threshold_row(self, label_text: str, spinbox: QDoubleSpinBox) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        label = QLabel(label_text)
        label.setObjectName("MutedLabel")
        row.addWidget(label)
        row.addWidget(spinbox)
        row.addStretch(1)
        return row

    def _fill_summary_table(self) -> None:
        self.summary_table.setUpdatesEnabled(False)
        try:
            self.summary_table.setRowCount(len(self._channels))
            for row, channel in enumerate(self._channels):
                metric = self._metrics_by_channel.get(channel, {})
                values = [
                    channel,
                    f"{float(metric.get('Sign Agreement (%)', 0.0)):.1f}%",
                    f"{float(metric.get('Sign Mismatch (%)', 0.0)):.1f}%",
                    f"{float(metric.get('Sign Deadband (%)', 0.0)):.1f}%",
                    f"{float(metric.get('Longest Sign Mismatch (s)', 0.0)):g}s",
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column > 0:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if column == 1:
                        item.setBackground(QColor("#ecf7f0"))
                    elif column == 2:
                        item.setBackground(QColor("#faeeee"))
                    elif column == 3:
                        item.setBackground(QColor("#f1f4f8"))
                    self.summary_table.setItem(row, column, item)
        finally:
            self.summary_table.setUpdatesEnabled(True)

    def collapse_summary_panel(self) -> None:
        if self.summary_panel_collapsed:
            return
        current_width = self.summary_shell.width()
        if current_width > self.COLLAPSED_RAIL_WIDTH:
            self._summary_expanded_width = max(self.SUMMARY_EXPANDED_MIN_WIDTH, current_width)
        self.summary_sidebar.hide()
        self.summary_restore_rail.conceal()
        self.summary_restore_rail.show()
        self.summary_shell.setMinimumWidth(self.COLLAPSED_RAIL_WIDTH)
        self.summary_shell.setMaximumWidth(self.COLLAPSED_RAIL_WIDTH)
        self.summary_panel_collapsed = True
        splitter_width = max(self.summary_splitter.width(), self.COLLAPSED_RAIL_WIDTH + 800)
        self.summary_splitter.setSizes([splitter_width - self.COLLAPSED_RAIL_WIDTH, self.COLLAPSED_RAIL_WIDTH])

    def expand_summary_panel(self) -> None:
        if not self.summary_panel_collapsed:
            return
        self.summary_restore_rail.conceal()
        self.summary_restore_rail.hide()
        self.summary_sidebar.show()
        self.summary_shell.setMinimumWidth(self.SUMMARY_EXPANDED_MIN_WIDTH)
        self.summary_shell.setMaximumWidth(16777215)
        self.summary_panel_collapsed = False
        width = max(self._summary_expanded_width, self.SUMMARY_EXPANDED_MIN_WIDTH)
        splitter_width = max(self.summary_splitter.width(), width + 800)
        self.summary_splitter.setSizes([splitter_width - width, width])

    def toggle_summary_panel(self) -> None:
        if self.summary_panel_collapsed:
            self.expand_summary_panel()
        else:
            self.collapse_summary_panel()

    def _handle_mouse_moved(self, scene_pos: Any) -> None:
        if self.plot_data is None or not len(self._time_values) or not self._channels:
            return
        if not self.plot_widget.sceneBoundingRect().contains(scene_pos):
            return
        point = self.plot_widget.getPlotItem().vb.mapSceneToView(scene_pos)
        row = int(round(point.y()))
        if row < 0 or row >= len(self._channels):
            return
        column = self._nearest_time_index(float(point.x()))
        if column is None:
            return
        raw_status = int(self._status_matrix[column, row])
        self.hover_label.setText(
            f"Time {self._time_values[column]:g} | {self._channels[row]} | {STATUS_LABELS.get(raw_status, 'Unknown')}"
        )

    def _nearest_time_index(self, value: float) -> int | None:
        if not len(self._time_values):
            return None
        if value < self._time_values[0] or value > self._time_values[-1]:
            return None
        index = int(np.searchsorted(self._time_values, value, side="left"))
        if index >= len(self._time_values):
            return len(self._time_values) - 1
        if index > 0:
            previous_distance = abs(value - self._time_values[index - 1])
            current_distance = abs(value - self._time_values[index])
            if previous_distance <= current_distance:
                return index - 1
        return index

    def _legend_item(self, label: str, color: str) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        chip = QFrame()
        chip.setFixedSize(13, 13)
        chip.setStyleSheet(f"background: {color}; border: 1px solid rgba(30, 42, 54, 0.18); border-radius: 2px;")
        text = QLabel(label)
        text.setObjectName("MutedLabel")
        layout.addWidget(chip)
        layout.addWidget(text)
        return widget
