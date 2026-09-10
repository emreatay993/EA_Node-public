#!/usr/bin/env python
# Purpose: PyQt GUI entrypoint for the MCF DPF section resultants tool.
# Map: subsystems/packaging_generated_assets
# Tests: tests/test_mcf_dpf_section_resultants_gui.py
# Landmarks: StaticAnimationLoaderThread; SectionVisualizationWidget; MainWindow; run_gui
"""Qt GUI entry point for section resultant extraction."""

from __future__ import annotations

import argparse
import csv
import errno
import json
import math
import os
import re
import sys
import tempfile
import threading
import traceback
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.mcf_dpf_section_resultants.core import *
from scripts.mcf_dpf_section_resultants.dpf_io import *
from scripts.mcf_dpf_section_resultants.visualization import *
from scripts.mcf_dpf_section_resultants.extraction import *
from scripts.mcf_dpf_section_resultants.cli import *


ANIMATION_ICON_FILENAMES = {
    "previous": "player-track-prev.svg",
    "play": "player-play.svg",
    "pause": "player-pause.svg",
    "next": "player-track-next.svg",
    "stop": "player-stop.svg",
    "buffering": "loader-2.svg",
}
ANIMATION_ICON_NOTICE_FILENAMES = (
    "TABLER_SOURCES.txt",
    "TABLER_LICENSE.txt",
)


def animation_icon_asset_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "mcf_dpf_section_resultants" / "icons"
    return Path(__file__).resolve().parent / "assets" / "icons"


def animation_icon_asset_path(name: str) -> Path:
    return animation_icon_asset_root() / ANIMATION_ICON_FILENAMES[name]


def import_qt() -> Tuple[Any, Any, Any]:
    from PyQt6 import QtCore, QtGui, QtWidgets

    return QtCore, QtGui, QtWidgets


def run_gui(initial_config: Optional[SectionConfig] = None) -> int:
    QtCore, QtGui, QtWidgets = import_qt()
    signal = QtCore.pyqtSignal

    class ExtractionThread(QtCore.QThread):
        log_message = signal(str)
        completed = signal(dict)
        failed = signal(str, str)

        def __init__(self, config: SectionConfig) -> None:
            super().__init__()
            self._config = config

        def run(self) -> None:
            try:
                summary = extract_section_resultants(
                    self._config,
                    self.log_message.emit,
                    capture_visualization_vectors=True,
                )
            except Exception as exc:
                self.failed.emit(str(exc), traceback.format_exc())
                return
            self.completed.emit(summary)

    class VisualizationThread(QtCore.QThread):
        log_message = signal(str)
        completed = signal(dict)
        failed = signal(str)

        def __init__(self, config: SectionConfig) -> None:
            super().__init__()
            self._config = config

        def run(self) -> None:
            try:
                payload = build_section_visualization_payload(
                    self._config,
                    self.log_message.emit,
                )
            except Exception:
                self.failed.emit(traceback.format_exc())
                return
            self.completed.emit(payload)

    class StaticAnimationLoaderThread(QtCore.QThread):
        """Load animation displacements without ever running DPF on the GUI thread."""

        log_message = signal(str)
        batch_loaded = signal(int, object, object)
        completed = signal(int, object)
        failed = signal(int, str)

        def __init__(
            self,
            config: SectionConfig,
            selected_result_sets: Sequence[Dict[str, Any]],
            *,
            generation: int,
            signature: StaticAnimationSessionSignature,
            priority_index: int,
            direction: int,
        ) -> None:
            super().__init__()
            self._config = config
            self._selected_result_sets = [dict(item) for item in selected_result_sets]
            self._generation = int(generation)
            self._signature = signature
            self._priority_index = int(priority_index)
            self._direction = 1 if int(direction) >= 0 else -1
            self._cancel_event = threading.Event()

        def cancel(self) -> None:
            self._cancel_event.set()

        def run(self) -> None:
            try:
                session = load_static_animation_session(
                    self._config,
                    self._selected_result_sets,
                    generation=self._generation,
                    expected_signature=self._signature,
                    priority_index=self._priority_index,
                    direction=self._direction,
                    cancel_requested=self._cancel_event.is_set,
                    on_batch=lambda loaded_session, indices: self.batch_loaded.emit(
                        self._generation,
                        loaded_session,
                        list(indices),
                    ),
                    log=self.log_message.emit,
                )
            except Exception:
                self.failed.emit(self._generation, traceback.format_exc())
                return
            self.completed.emit(self._generation, session)

    class FileRow(QtWidgets.QWidget):
        path_changed = signal(str)

        def __init__(self, mode: str, file_filter: str, parent: Optional[Any] = None) -> None:
            super().__init__(parent)
            self.mode = mode
            self.file_filter = file_filter
            self.edit = QtWidgets.QLineEdit()
            self.edit.setMinimumWidth(420)
            self.button = QtWidgets.QPushButton("Browse")
            self.button.clicked.connect(self.browse)
            layout = QtWidgets.QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.edit, 1)
            layout.addWidget(self.button)

        def text(self) -> str:
            return self.edit.text().strip()

        def set_text(self, value: str) -> None:
            text = value or ""
            if self.edit.text() == text:
                return
            self.edit.setText(text)
            self.path_changed.emit(text)

        def browse(self) -> None:
            if self.mode == "save":
                path, _ = QtWidgets.QFileDialog.getSaveFileName(
                    self, "Select output CSV", self.text(), self.file_filter
                )
            else:
                path, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self, "Select file", self.text(), self.file_filter
                )
            if path:
                self.set_text(path)

    class ChevronComboBox(QtWidgets.QComboBox):
        def __init__(self, parent: Optional[Any] = None) -> None:
            super().__init__(parent)
            self.setMouseTracking(True)

        def setEditable(self, editable: bool) -> None:  # noqa: N802
            super().setEditable(editable)
            self._sync_line_edit_margins()

        def showEvent(self, event: Any) -> None:  # noqa: N802
            super().showEvent(event)
            self._sync_line_edit_margins()

        def _sync_line_edit_margins(self) -> None:
            line_edit = self.lineEdit() if self.isEditable() else None
            if line_edit is not None:
                line_edit.setTextMargins(0, 0, 30, 0)

        def paintEvent(self, event: Any) -> None:  # noqa: N802
            super().paintEvent(event)
            painter = QtGui.QPainter(self)
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.Antialiasing,
                True,
            )
            enabled = self.isEnabled()
            color = QtGui.QColor("#52616b" if enabled else "#9aa8ad")
            if self.underMouse() and enabled:
                color = QtGui.QColor("#236b5f")
            pen = QtGui.QPen(color, 1.8)
            pen.setCapStyle(
                QtCore.Qt.PenCapStyle.RoundCap
            )
            pen.setJoinStyle(
                QtCore.Qt.PenJoinStyle.RoundJoin
            )
            painter.setPen(pen)
            rect = self.rect()
            center = QtCore.QPointF(rect.right() - 15.0, rect.center().y() + 0.5)
            size = 4.8
            painter.drawLine(
                QtCore.QPointF(center.x() - size, center.y() - 2.0),
                QtCore.QPointF(center.x(), center.y() + 2.6),
            )
            painter.drawLine(
                QtCore.QPointF(center.x(), center.y() + 2.6),
                QtCore.QPointF(center.x() + size, center.y() - 2.0),
            )

    class ThemedCheckBox(QtWidgets.QCheckBox):
        _BOX_SIZE = 18
        _TEXT_SPACING = 8

        def __init__(self, text: str = "", parent: Optional[Any] = None) -> None:
            super().__init__(text, parent)
            self.setMouseTracking(True)
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )

        def sizeHint(self) -> Any:  # noqa: N802
            metrics = self.fontMetrics()
            if hasattr(metrics, "horizontalAdvance"):
                text_width = metrics.horizontalAdvance(self.text())
            else:
                text_width = metrics.width(self.text())
            return QtCore.QSize(
                self._BOX_SIZE + self._TEXT_SPACING + text_width + 4,
                max(24, metrics.height() + 4),
            )

        def paintEvent(self, event: Any) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.Antialiasing,
                True,
            )
            enabled = self.isEnabled()
            checked = self.isChecked()
            hovered = self.underMouse() and enabled
            pressed = self.isDown() and enabled
            rect = self.rect()
            box_top = (rect.height() - self._BOX_SIZE) * 0.5
            box_rect = QtCore.QRectF(1.0, box_top, self._BOX_SIZE, self._BOX_SIZE)

            if checked:
                fill = QtGui.QColor("#236b5f")
                border = QtGui.QColor("#236b5f")
                tick = QtGui.QColor("#ffffff")
                if hovered:
                    fill = QtGui.QColor("#2d7f72")
                    border = QtGui.QColor("#2d7f72")
                if pressed:
                    fill = QtGui.QColor("#1e5f55")
                    border = QtGui.QColor("#1e5f55")
                if not enabled:
                    fill = QtGui.QColor("#d6e4e1")
                    border = QtGui.QColor("#9fb9b3")
                    tick = QtGui.QColor("#52616b")
            else:
                fill = QtGui.QColor("#ffffff")
                border = QtGui.QColor("#9fb1b8")
                tick = QtGui.QColor("#ffffff")
                if hovered:
                    border = QtGui.QColor("#236b5f")
                if pressed:
                    fill = QtGui.QColor("#edf5f3")
                if not enabled:
                    fill = QtGui.QColor("#f0f4f5")
                    border = QtGui.QColor("#c9d2d7")

            painter.setPen(QtGui.QPen(border, 1.2))
            painter.setBrush(fill)
            painter.drawRoundedRect(box_rect, 4.0, 4.0)

            if checked:
                pen = QtGui.QPen(tick, 2.0)
                pen.setCapStyle(
                    QtCore.Qt.PenCapStyle.RoundCap
                )
                pen.setJoinStyle(
                    QtCore.Qt.PenJoinStyle.RoundJoin
                )
                painter.setPen(pen)
                check_path = QtGui.QPainterPath()
                check_path.moveTo(box_rect.left() + 4.5, box_rect.center().y() + 0.3)
                check_path.lineTo(box_rect.left() + 7.8, box_rect.bottom() - 5.0)
                check_path.lineTo(box_rect.right() - 4.2, box_rect.top() + 5.0)
                painter.drawPath(check_path)

            text_rect = QtCore.QRectF(
                box_rect.right() + self._TEXT_SPACING,
                0.0,
                max(0.0, rect.width() - box_rect.right() - self._TEXT_SPACING),
                float(rect.height()),
            )
            painter.setPen(QtGui.QColor("#17212b" if enabled else "#52616b"))
            painter.drawText(
                text_rect,
                (
                    QtCore.Qt.AlignmentFlag.AlignVCenter
                    | QtCore.Qt.AlignmentFlag.AlignLeft
                ),
                self.text(),
            )

    class CollapseHandle(QtWidgets.QFrame):
        clicked = signal()

        _ICON_SCALE = 0.58
        _ROUNDING = 8.0

        def __init__(
            self,
            label: str = "",
            direction: str = "right",
            *,
            vertical: bool = False,
            parent: Optional[Any] = None,
        ) -> None:
            super().__init__(parent)
            self._label = label
            self._direction = direction
            self._vertical = bool(vertical)
            self._hovered = False
            self._pressed = False
            self.setCursor(
                QtCore.Qt.CursorShape.PointingHandCursor
            )
            self.setMouseTracking(True)
            self.setFocusPolicy(
                QtCore.Qt.FocusPolicy.StrongFocus
            )
            if self._vertical:
                self.setFixedWidth(34)
                self.setMinimumHeight(132)
            else:
                self.setFixedSize(28, 26)

        def set_direction(self, direction: str) -> None:
            if self._direction == direction:
                return
            self._direction = direction
            self.update()

        def sizeHint(self) -> Any:  # noqa: N802
            return QtCore.QSize(34, 150) if self._vertical else QtCore.QSize(28, 26)

        def enterEvent(self, event: Any) -> None:  # noqa: N802
            self._hovered = True
            self.update()
            super().enterEvent(event)

        def leaveEvent(self, event: Any) -> None:  # noqa: N802
            self._hovered = False
            self._pressed = False
            self.update()
            super().leaveEvent(event)

        def mousePressEvent(self, event: Any) -> None:  # noqa: N802
            if event.button() == (
                QtCore.Qt.MouseButton.LeftButton
            ):
                self._pressed = True
                self.update()
                event.accept()
                return
            super().mousePressEvent(event)

        def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
            left_button = (
                QtCore.Qt.MouseButton.LeftButton
            )
            if event.button() == left_button and self._pressed:
                self._pressed = False
                self.update()
                if self.rect().contains(event.pos()):
                    self.clicked.emit()
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def keyPressEvent(self, event: Any) -> None:  # noqa: N802
            key = event.key()
            if key in (
                QtCore.Qt.Key.Key_Return,
                QtCore.Qt.Key.Key_Enter,
                QtCore.Qt.Key.Key_Space,
            ):
                self.clicked.emit()
                event.accept()
                return
            super().keyPressEvent(event)

        def paintEvent(self, event: Any) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.Antialiasing,
                True,
            )
            rect = QtCore.QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
            if self._pressed:
                background = QtGui.QColor("#dcece8")
                border = QtGui.QColor("#9fb9b3")
            elif self._hovered or self.hasFocus():
                background = QtGui.QColor("#edf5f3")
                border = QtGui.QColor("#acc2bd")
            else:
                background = QtGui.QColor("#ffffff")
                border = QtGui.QColor("#c9d2d7")
            painter.setBrush(background)
            painter.setPen(QtGui.QPen(border, 1.0))
            painter.drawRoundedRect(rect, self._ROUNDING, self._ROUNDING)

            accent = QtGui.QColor("#236b5f")
            muted = QtGui.QColor("#8fa1a7")
            if self._vertical:
                self._draw_vertical_label(painter, rect, accent)
                center = QtCore.QPointF(rect.center().x(), rect.top() + 19.0)
                self._draw_chevron(painter, center, self._direction, accent)
                self._draw_grip(painter, rect, muted)
                return

            self._draw_chevron(painter, rect.center(), self._direction, accent)

        def _draw_vertical_label(
            self,
            painter: Any,
            rect: Any,
            color: Any,
        ) -> None:
            if not self._label:
                return
            painter.save()
            painter.setPen(color)
            font = painter.font()
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.translate(rect.center())
            painter.rotate(-90)
            label_rect = QtCore.QRectF(
                -rect.height() * 0.5 + 36.0,
                -rect.width() * 0.5,
                rect.height() - 72.0,
                rect.width(),
            )
            painter.drawText(
                label_rect,
                (
                    QtCore.Qt.AlignmentFlag.AlignCenter
                ),
                self._label,
            )
            painter.restore()

        def _draw_chevron(
            self,
            painter: Any,
            center: Any,
            direction: str,
            color: Any,
        ) -> None:
            pen = QtGui.QPen(color, 2.0)
            pen.setCapStyle(
                QtCore.Qt.PenCapStyle.RoundCap
            )
            pen.setJoinStyle(
                QtCore.Qt.PenJoinStyle.RoundJoin
            )
            painter.setPen(pen)
            painter.setBrush(
                QtCore.Qt.BrushStyle.NoBrush
            )
            step = 6.0 * self._ICON_SCALE
            span = 10.5 * self._ICON_SCALE
            direction = str(direction or "right").lower()
            if direction == "left":
                points = (
                    QtCore.QPointF(center.x() + step, center.y() - span),
                    QtCore.QPointF(center.x() - step, center.y()),
                    QtCore.QPointF(center.x() + step, center.y() + span),
                )
            elif direction == "up":
                points = (
                    QtCore.QPointF(center.x() - span, center.y() + step),
                    QtCore.QPointF(center.x(), center.y() - step),
                    QtCore.QPointF(center.x() + span, center.y() + step),
                )
            elif direction == "down":
                points = (
                    QtCore.QPointF(center.x() - span, center.y() - step),
                    QtCore.QPointF(center.x(), center.y() + step),
                    QtCore.QPointF(center.x() + span, center.y() - step),
                )
            else:
                points = (
                    QtCore.QPointF(center.x() - step, center.y() - span),
                    QtCore.QPointF(center.x() + step, center.y()),
                    QtCore.QPointF(center.x() - step, center.y() + span),
                )
            path = QtGui.QPainterPath()
            path.moveTo(points[0])
            path.lineTo(points[1])
            path.lineTo(points[2])
            painter.drawPath(path)

        def _draw_grip(self, painter: Any, rect: Any, color: Any) -> None:
            pen = QtGui.QPen(color, 1.2)
            pen.setCapStyle(
                QtCore.Qt.PenCapStyle.RoundCap
            )
            painter.setPen(pen)
            for offset in (-4.0, 0.0, 4.0):
                y = rect.bottom() - 18.0 + offset
                painter.drawLine(
                    QtCore.QPointF(rect.center().x() - 4.5, y),
                    QtCore.QPointF(rect.center().x() + 4.5, y),
                )

    class CollapsibleGroup(QtWidgets.QFrame):
        collapsed_changed = signal(bool)

        _UNBOUNDED_HEIGHT = 16777215

        def __init__(
            self,
            title: str,
            parent: Optional[Any] = None,
        ) -> None:
            super().__init__(parent)
            self._title = str(title)
            self._expanded = True
            self.setObjectName("collapsibleGroup")
            self.setAttribute(
                QtCore.Qt.WidgetAttribute.WA_StyledBackground,
                True,
            )

            root = QtWidgets.QVBoxLayout(self)
            self._root_layout = root
            root.setContentsMargins(8, 7, 8, 8)
            root.setSpacing(5)

            header = QtWidgets.QWidget(self)
            self.header_widget = header
            header.setObjectName("collapsibleGroupHeader")
            header_layout = QtWidgets.QHBoxLayout(header)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(6)

            self.toggle_button = CollapseHandle("", "down", parent=header)
            self.toggle_button.setAccessibleName(f"Collapse {self._title}")
            self.toggle_button.setToolTip(f"Collapse {self._title}")
            self.toggle_button.clicked.connect(self.toggle_expanded)
            header_layout.addWidget(self.toggle_button)

            self.title_label = QtWidgets.QLabel(self._title, header)
            self.title_label.setObjectName("collapsibleGroupTitle")
            header_layout.addWidget(self.title_label)
            header_layout.addStretch(1)
            root.addWidget(header)

            self.body_widget = QtWidgets.QWidget(self)
            self.body_widget.setObjectName("collapsibleGroupBody")
            root.addWidget(self.body_widget)

        def is_expanded(self) -> bool:
            return self._expanded

        def toggle_expanded(self) -> None:
            self.set_expanded(not self._expanded)

        def set_expanded(self, expanded: bool) -> None:
            expanded = bool(expanded)
            if expanded == self._expanded:
                return
            self._expanded = expanded
            self.body_widget.setVisible(expanded)
            policy = self.sizePolicy()
            if expanded:
                self.setMinimumHeight(0)
                self.setMaximumHeight(self._UNBOUNDED_HEIGHT)
                policy.setVerticalPolicy(QtWidgets.QSizePolicy.Policy.Preferred)
            else:
                self._root_layout.invalidate()
                self._root_layout.activate()
                margins = self._root_layout.contentsMargins()
                compact_height = (
                    self.header_widget.sizeHint().height()
                    + margins.top()
                    + margins.bottom()
                )
                self.setMinimumHeight(compact_height)
                self.setMaximumHeight(compact_height)
                policy.setVerticalPolicy(QtWidgets.QSizePolicy.Policy.Fixed)
            self.setSizePolicy(policy)
            direction = "down" if expanded else "right"
            action = "Collapse" if expanded else "Expand"
            self.toggle_button.set_direction(direction)
            self.toggle_button.setAccessibleName(f"{action} {self._title}")
            self.toggle_button.setToolTip(f"{action} {self._title}")
            self.updateGeometry()
            parent_layout = self.parentWidget().layout() if self.parentWidget() else None
            if parent_layout is not None:
                parent_layout.invalidate()
                parent_layout.activate()
            self.collapsed_changed.emit(not expanded)

    def _themed_control_icon(kind: str, color: str = "#e8f1ef") -> Any:
        pixmap = QtGui.QPixmap(16, 16)
        pixmap.fill(
            QtCore.Qt.GlobalColor.transparent
        )
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(
            QtGui.QPainter.RenderHint.Antialiasing,
            True,
        )
        pen = QtGui.QPen(QtGui.QColor(color), 1.6)
        pen.setCapStyle(
            QtCore.Qt.PenCapStyle.RoundCap
        )
        pen.setJoinStyle(
            QtCore.Qt.PenJoinStyle.RoundJoin
        )
        painter.setPen(pen)
        painter.setBrush(
            QtCore.Qt.BrushStyle.NoBrush
        )
        if kind == "close":
            painter.drawLine(QtCore.QPointF(5.0, 5.0), QtCore.QPointF(11.0, 11.0))
            painter.drawLine(QtCore.QPointF(11.0, 5.0), QtCore.QPointF(5.0, 11.0))
        elif kind == "dock":
            painter.drawRoundedRect(QtCore.QRectF(3.5, 3.5, 9.0, 9.0), 1.2, 1.2)
            painter.drawLine(QtCore.QPointF(9.5, 3.5), QtCore.QPointF(9.5, 12.5))
        else:
            painter.drawRoundedRect(QtCore.QRectF(4.0, 5.0, 8.0, 7.0), 1.2, 1.2)
            painter.drawLine(QtCore.QPointF(8.0, 4.0), QtCore.QPointF(12.0, 4.0))
            painter.drawLine(QtCore.QPointF(12.0, 4.0), QtCore.QPointF(12.0, 8.0))
        painter.end()
        return QtGui.QIcon(pixmap)

    def _animation_control_icon(name: str, size: int = 20) -> Any:
        from PyQt6.QtSvg import QSvgRenderer

        asset_path = animation_icon_asset_path(name)
        if not asset_path.is_file():
            raise FileNotFoundError(f"Animation icon asset was not found: {asset_path}")
        renderer = QSvgRenderer(str(asset_path))
        if not renderer.isValid():
            raise ValueError(f"Animation icon asset is not valid SVG: {asset_path}")

        def tinted_pixmap(color: str) -> Any:
            image = QtGui.QImage(
                size,
                size,
                QtGui.QImage.Format.Format_ARGB32_Premultiplied,
            )
            image.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(image)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            renderer.render(painter, QtCore.QRectF(0.0, 0.0, float(size), float(size)))
            painter.setCompositionMode(
                QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
            )
            painter.fillRect(image.rect(), QtGui.QColor(color))
            painter.end()
            return QtGui.QPixmap.fromImage(image)

        icon = QtGui.QIcon()
        icon.addPixmap(
            tinted_pixmap("#ffffff"),
            QtGui.QIcon.Mode.Normal,
            QtGui.QIcon.State.Off,
        )
        icon.addPixmap(
            tinted_pixmap("#edf1f2"),
            QtGui.QIcon.Mode.Disabled,
            QtGui.QIcon.State.Off,
        )
        return icon

    class DockTitleBar(QtWidgets.QWidget):
        def __init__(self, dock: Any, parent: Optional[Any] = None) -> None:
            super().__init__(parent or dock)
            self._dock = dock
            self.setObjectName("themedDockTitleBar")
            self.setFixedHeight(30)
            self.setAutoFillBackground(True)
            self.setAttribute(
                QtCore.Qt.WidgetAttribute.WA_StyledBackground,
                True,
            )

            layout = QtWidgets.QHBoxLayout(self)
            layout.setContentsMargins(8, 3, 4, 3)
            layout.setSpacing(4)

            self._title_label = QtWidgets.QLabel(str(dock.windowTitle() or ""), self)
            self._title_label.setObjectName("themedDockTitleLabel")
            layout.addWidget(self._title_label, 1)

            self._float_button = QtWidgets.QToolButton(self)
            self._float_button.setObjectName("dockTitleButton")
            self._float_button.setFixedSize(24, 22)
            self._float_button.setAutoRaise(True)
            self._float_button.clicked.connect(self._toggle_floating)
            layout.addWidget(self._float_button)

            self._close_button = QtWidgets.QToolButton(self)
            self._close_button.setObjectName("dockTitleButton")
            self._close_button.setFixedSize(24, 22)
            self._close_button.setAutoRaise(True)
            self._close_button.setIcon(_themed_control_icon("close", "#236b5f"))
            self._close_button.setToolTip("Close")
            self._close_button.clicked.connect(dock.close)
            layout.addWidget(self._close_button)

            dock.topLevelChanged.connect(self._sync_floating_state)
            if hasattr(dock, "windowTitleChanged"):
                dock.windowTitleChanged.connect(self._title_label.setText)
            self._sync_floating_state(bool(dock.isFloating()))

        def _toggle_floating(self) -> None:
            self._dock.setFloating(not bool(self._dock.isFloating()))

        def _sync_floating_state(self, floating: bool) -> None:
            if floating:
                self._float_button.setIcon(_themed_control_icon("dock", "#236b5f"))
                self._float_button.setToolTip("Dock")
            else:
                self._float_button.setIcon(_themed_control_icon("float", "#236b5f"))
                self._float_button.setToolTip("Undock")

        def mousePressEvent(self, event: Any) -> None:  # noqa: N802
            event.ignore()

        def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
            event.ignore()

        def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
            event.ignore()

        def mouseDoubleClickEvent(self, event: Any) -> None:  # noqa: N802
            event.ignore()

    class SectionVisualizationWidget(QtWidgets.QWidget):
        nodal_force_export_requested = signal()
        nodal_force_excel_export_requested = signal()

        def __init__(self, parent: Optional[Any] = None) -> None:
            super().__init__(parent)
            self._interactor: Optional[Any] = None
            self._last_payload: Optional[Dict[str, Any]] = None
            self._show_moment_reference_label = False
            self._show_ruler = True
            self._ruler_static_bottom = False
            self._static_ruler_actor: Optional[Any] = None
            self._static_ruler_camera: Optional[Any] = None
            self._static_ruler_observer_id: Optional[Any] = None
            self._static_ruler_payload: Optional[Dict[str, Any]] = None
            self._static_ruler_render_queued = False
            self._nodal_force_export_enabled = False
            self._has_rendered_payload = False
            self._animation_scene: Optional[Dict[str, Any]] = None
            self._error_label = QtWidgets.QLabel("")
            self._error_label.setWordWrap(True)
            action_class = QtGui.QAction
            self._moment_reference_label_action = action_class(
                "Show moment reference label",
                self,
            )
            self._moment_reference_label_action.setCheckable(True)
            self._moment_reference_label_action.setChecked(False)
            self._moment_reference_label_action.toggled.connect(
                self._set_show_moment_reference_label
            )
            self._show_ruler_action = action_class("Show ruler", self)
            self._show_ruler_action.setCheckable(True)
            self._show_ruler_action.setChecked(True)
            self._show_ruler_action.toggled.connect(self._set_show_ruler)
            self._ruler_static_bottom_action = action_class(
                "Place ruler at bottom of viewport",
                self,
            )
            self._ruler_static_bottom_action.setCheckable(True)
            self._ruler_static_bottom_action.setChecked(False)
            self._ruler_static_bottom_action.toggled.connect(
                self._set_ruler_static_bottom
            )
            self._nodal_force_export_action = action_class(
                "Export nodal forces CSV for current time...",
                self,
            )
            self._nodal_force_export_action.setEnabled(False)
            self._nodal_force_export_action.triggered.connect(
                self.nodal_force_export_requested.emit
            )
            self._nodal_force_excel_export_action = action_class(
                "Export nodal forces (global + selected local frame) Excel for current time...",
                self,
            )
            self._nodal_force_excel_export_action.setToolTip(
                "Exports DPF nodal forces in global components and their projection onto "
                "the selected local axes. The workbook records the exact local-axis matrix."
            )
            self._nodal_force_excel_export_action.setEnabled(False)
            self._nodal_force_excel_export_action.triggered.connect(
                self.nodal_force_excel_export_requested.emit
            )
            self._install_context_menu(self)
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            try:
                self._interactor = self._create_interactor()
            except Exception as exc:
                self._error_label.setText(
                    "PyVistaQt visualization is unavailable: " + str(exc)
                )
                layout.addWidget(self._error_label, 1)
            else:
                self._install_context_menu(self._interactor)
                layout.addWidget(self._interactor, 1)

        def _create_interactor(self) -> Any:
            from pyvistaqt import QtInteractor

            platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
            off_screen = platform in {"minimal", "offscreen"}
            return QtInteractor(parent=self, auto_update=False, off_screen=off_screen)

        def _custom_context_menu_policy(self) -> Any:
            return (
                QtCore.Qt.ContextMenuPolicy.CustomContextMenu
            )

        def _install_context_menu(self, widget: Any) -> None:
            if not hasattr(widget, "setContextMenuPolicy"):
                return
            widget.setContextMenuPolicy(self._custom_context_menu_policy())
            widget.customContextMenuRequested.connect(self._show_context_menu)

        def _show_context_menu(self, position: Any) -> None:
            source = self.sender()
            if source is not None and hasattr(source, "mapToGlobal"):
                global_position = source.mapToGlobal(position)
            else:
                global_position = self.mapToGlobal(position)
            menu = QtWidgets.QMenu(self)
            menu.addAction(self._moment_reference_label_action)
            menu.addSeparator()
            menu.addAction(self._show_ruler_action)
            menu.addAction(self._ruler_static_bottom_action)
            menu.addSeparator()
            menu.addAction(self._nodal_force_export_action)
            menu.addAction(self._nodal_force_excel_export_action)
            menu.exec(global_position)

        def set_nodal_force_export_enabled(self, enabled: bool) -> None:
            self._nodal_force_export_enabled = bool(enabled)
            self._nodal_force_export_action.setEnabled(self._nodal_force_export_enabled)
            self._nodal_force_excel_export_action.setEnabled(
                self._nodal_force_export_enabled
            )

        def _set_show_moment_reference_label(self, enabled: bool) -> None:
            self._show_moment_reference_label = bool(enabled)
            if self._last_payload is not None:
                self.render_payload(self._last_payload)

        def _set_show_ruler(self, enabled: bool) -> None:
            self._show_ruler = bool(enabled)
            if not self._show_ruler:
                self._clear_static_ruler_observer()
            if self._last_payload is not None:
                self.render_payload(self._last_payload)

        def _set_ruler_static_bottom(self, enabled: bool) -> None:
            self._ruler_static_bottom = bool(enabled)
            if not self._ruler_static_bottom:
                self._clear_static_ruler_observer()
            if self._last_payload is not None:
                self.render_payload(self._last_payload)

        def _clear_static_ruler_observer(self) -> None:
            camera = self._static_ruler_camera
            observer_id = self._static_ruler_observer_id
            if camera is not None:
                try:
                    remove_camera_observer(camera, observer_id)
                except Exception:
                    pass
            self._static_ruler_actor = None
            self._static_ruler_camera = None
            self._static_ruler_observer_id = None
            self._static_ruler_payload = None
            self._static_ruler_render_queued = False

        def _update_static_ruler_range(self) -> None:
            actor = self._static_ruler_actor
            payload = self._static_ruler_payload
            plotter = self._interactor
            if actor is None or payload is None or plotter is None:
                return
            update_static_ruler_actor_range(actor, plotter, payload)

        def _render_static_ruler_if_queued(self) -> None:
            if not self._static_ruler_render_queued:
                return
            self._static_ruler_render_queued = False
            plotter = self._interactor
            render = getattr(plotter, "render", None)
            if callable(render):
                render()

        def _on_static_ruler_camera_modified(self, _caller: Any = None, _event: Any = None) -> None:
            self._update_static_ruler_range()
            if self._static_ruler_render_queued:
                return
            self._static_ruler_render_queued = True
            QtCore.QTimer.singleShot(0, self._render_static_ruler_if_queued)

        def _install_static_ruler_observer(self, payload: Dict[str, Any]) -> None:
            plotter = self._interactor
            if plotter is None:
                return
            actor = add_visualization_static_bottom_ruler(plotter, payload)
            if actor is None:
                return
            camera = getattr(plotter, "camera", None)
            add_observer = getattr(camera, "AddObserver", None)
            self._static_ruler_actor = actor
            self._static_ruler_camera = camera
            self._static_ruler_payload = payload
            self._update_static_ruler_range()
            if callable(add_observer):
                self._static_ruler_observer_id = add_observer(
                    "ModifiedEvent",
                    self._on_static_ruler_camera_modified,
                )

        @staticmethod
        def _animation_topology_key(payload: Dict[str, Any]) -> Tuple[Any, ...]:
            mesh = payload.get("mesh") or {}
            topology_identity = payload.get("_animation_topology_identity")
            if topology_identity is not None:
                return (topology_identity,)
            celltypes = mesh.get("celltypes")
            element_ids = mesh.get("element_ids")
            cells = mesh.get("cells")
            points = mesh.get("points")
            return (
                payload.get("_animation_topology_identity"),
                tuple(int(value) for value in element_ids) if element_ids is not None else (),
                tuple(int(value) for value in celltypes) if celltypes is not None else (),
                len(cells) if cells is not None else 0,
                len(points) if points is not None else 0,
            )

        @staticmethod
        def _set_actor_visible(actor: Any, visible: bool) -> None:
            if actor is None:
                return
            setter = getattr(actor, "SetVisibility", None)
            if callable(setter):
                setter(bool(visible))
                return
            try:
                actor.visibility = bool(visible)
            except Exception:
                pass

        @staticmethod
        def _set_actor_dataset(actor: Any, dataset: Any) -> None:
            if actor is None:
                return
            mapper = getattr(actor, "mapper", None)
            if mapper is None:
                getter = getattr(actor, "GetMapper", None)
                mapper = getter() if callable(getter) else None
            if mapper is None:
                return
            setter = getattr(mapper, "SetInputData", None)
            if callable(setter):
                setter(dataset)
            else:
                try:
                    mapper.dataset = dataset
                except Exception:
                    return
            modified = getattr(mapper, "Modified", None)
            if callable(modified):
                modified()

        @staticmethod
        def _animation_arrow_mesh(
            pyvista: Any,
            origin: Sequence[float],
            vector: Sequence[float],
        ) -> Any:
            import numpy as np

            direction = np.asarray(vector, dtype=float)
            if float(np.linalg.norm(direction)) <= 1.0e-15:
                direction = np.asarray([1.0e-15, 0.0, 0.0], dtype=float)
            return pyvista.Arrow(
                start=np.asarray(origin, dtype=float),
                direction=direction,
                scale="auto",
            )

        def _animation_nodal_glyphs(
            self,
            pyvista: Any,
            payload: Dict[str, Any],
        ) -> Any:
            import numpy as np

            animation = payload.get("animation") or {}
            overlay = payload.get("result_overlay") or {}
            if not animation.get("exact", False):
                return pyvista.PolyData()
            items = nodal_vector_glyph_items(overlay.get("nodal_vectors") or [])
            if not items:
                return pyvista.PolyData()
            points = pyvista.PolyData(
                np.asarray([item["origin"] for item in items], dtype=float)
            )
            points["vectors"] = np.asarray(
                [item["display_vector"] for item in items], dtype=float
            )
            points[VISUALIZATION_NODAL_GLYPH_SCALE_ARRAY] = np.asarray(
                [item["display_length"] for item in items], dtype=float
            )
            points["Magnitude"] = np.asarray(
                [float(item.get("magnitude") or 0.0) for item in items], dtype=float
            )
            return points.glyph(
                orient="vectors",
                scale=VISUALIZATION_NODAL_GLYPH_SCALE_ARRAY,
                factor=1.0,
            )

        def _initialize_animation_scene(
            self,
            payload: Dict[str, Any],
            *,
            playing: bool,
        ) -> None:
            import numpy as np
            import pyvista

            plotter = self._interactor
            self._clear_static_ruler_observer()
            camera_state = (
                capture_plotter_camera_state(plotter)
                if self._has_rendered_payload
                else None
            )
            clear = getattr(plotter, "clear", None)
            if callable(clear):
                clear()

            mesh_payload = payload.get("mesh") or {}
            animation_points = payload.get("_animation_points_numpy")
            mesh_points = mesh_payload.get("points")
            grid = pyvista.UnstructuredGrid(
                mesh_payload.get("cells") if mesh_payload.get("cells") is not None else [],
                (
                    mesh_payload.get("celltypes")
                    if mesh_payload.get("celltypes") is not None
                    else []
                ),
                (
                    animation_points
                    if animation_points is not None
                    else mesh_points
                    if mesh_points is not None
                    else []
                ),
            )
            large = visualization_payload_exceeds_large_scene_limit(payload)
            base_actor = plotter.add_mesh(
                grid,
                color="#9aa8ad",
                opacity=0.28,
                show_edges=not (playing and large),
                edge_color="#5e6970",
                label="Selected named selection elements",
            )
            cut_indices = [
                int(index)
                for index in payload.get("cut_cell_indices", [])
                if 0 <= int(index) < int(grid.n_cells)
            ]
            cut_grid = (
                grid.extract_cells(cut_indices)
                if cut_indices
                else grid.extract_cells([0])
            )
            cut_actor = plotter.add_mesh(
                cut_grid,
                color="#f08a24",
                opacity=0.78,
                show_edges=True,
                edge_color="#7a3d0a",
                label="Cut elements",
            )
            self._set_actor_visible(cut_actor, bool(cut_indices))

            corners = (payload.get("plane") or {}).get("corners") or []
            plane_poly = pyvista.PolyData(corners)
            if len(corners) == 4:
                plane_poly.faces = [4, 0, 1, 2, 3]
            plane_actor = plotter.add_mesh(
                plane_poly,
                color="#18a8b8",
                opacity=0.32,
                show_edges=True,
                edge_color="#0a5c66",
                label="Construction plane",
            )
            outline_points = corners + [corners[0]] if len(corners) == 4 else []
            outline = pyvista.PolyData(outline_points)
            if outline_points:
                outline.lines = [5, 0, 1, 2, 3, 4]
            outline_actor = plotter.add_mesh(outline, color="#0a5c66", line_width=3)

            force_points = [
                item["xyz"]
                for item in payload.get("force_summation_nodes", [])
                if isinstance(item, dict) and "xyz" in item
            ]
            force_cloud = pyvista.PolyData(
                np.asarray(force_points, dtype=float).reshape((-1, 3))
                if force_points
                else np.asarray([[0.0, 0.0, 0.0]], dtype=float)
            )
            force_actor = plotter.add_points(
                force_cloud,
                color="#d61f3c",
                point_size=11,
                render_points_as_spheres=True,
                label="Force summation nodes",
            )
            self._set_actor_visible(force_actor, bool(force_points))

            reference_xyz = payload.get("moment_reference_xyz") or [0.0, 0.0, 0.0]
            reference = pyvista.PolyData([reference_xyz])
            reference_actor = plotter.add_points(
                reference,
                color="#5b3fd6",
                point_size=14,
                render_points_as_spheres=True,
                label="Moment reference",
            )
            self._set_actor_visible(reference_actor, bool(payload.get("moment_reference_xyz")))

            frame_origin = payload.get("coordinate_system_origin") or [0.0, 0.0, 0.0]
            frame_origin_poly = pyvista.PolyData([frame_origin])
            frame_origin_actor = plotter.add_points(
                frame_origin_poly,
                color="#111827",
                point_size=10,
                render_points_as_spheres=True,
                label="Reference frame origin",
            )
            frame_axes = payload.get("coordinate_system_axes") or {}
            frame_length = max(visualization_scene_extent(payload) * 0.08, 1.0e-12)
            axis_actors: Dict[str, Any] = {}
            for axis_name, color in (
                ("x", "#d62828"),
                ("y", "#2a9d47"),
                ("z", "#2563eb"),
            ):
                vector = scale_vector(frame_axes.get(axis_name) or [0.0, 0.0, 0.0], frame_length)
                axis_actors[axis_name] = plotter.add_mesh(
                    self._animation_arrow_mesh(pyvista, frame_origin, vector),
                    color=color,
                    label=f"Moving frame {axis_name.upper()}",
                )

            overlay = payload.get("result_overlay") or {}
            total = overlay.get("total_vector") or {}
            total_origin = total.get("origin") or frame_origin
            total_vector = total.get("display_vector") or [0.0, 0.0, 0.0]
            total_actor = plotter.add_mesh(
                self._animation_arrow_mesh(pyvista, total_origin, total_vector),
                color=str(total.get("color") or "#d61f3c"),
                label=str(overlay.get("label") or "Result vector"),
            )
            self._set_actor_visible(total_actor, vector_magnitude(total_vector) > 0.0)
            total_origin_poly = pyvista.PolyData([total_origin])
            total_origin_actor = plotter.add_points(
                total_origin_poly,
                color=str(total.get("color") or "#d61f3c"),
                point_size=13,
                render_points_as_spheres=True,
            )
            self._set_actor_visible(total_origin_actor, vector_magnitude(total_vector) > 0.0)

            nodal_glyphs = self._animation_nodal_glyphs(pyvista, payload)
            nodal_display = (
                nodal_glyphs
                if int(nodal_glyphs.n_points) > 0
                else pyvista.PolyData([[0.0, 0.0, 0.0]])
            )
            nodal_actor = plotter.add_mesh(
                nodal_display,
                color="#f4c542",
                label="Nodal force vectors (exact sets only)",
            )
            self._set_actor_visible(nodal_actor, int(nodal_glyphs.n_points) > 0)

            counts = payload.get("counts") or {}
            text = (
                f"{counts.get('raw_element_count', 0)} selected elements | "
                f"{counts.get('cut_element_count', 0)} cut elements | "
                f"{counts.get('force_summation_node_count', 0)} force nodes"
            )
            if overlay.get("text"):
                text += f"\n{overlay['text']}"
            text_actor = plotter.add_text(
                text,
                position="upper_left",
                font_size=9,
                color="#17212b",
            )
            if self._show_ruler and not self._ruler_static_bottom:
                add_visualization_bottom_ruler(plotter, payload)
            add_axes = getattr(plotter, "add_axes", None)
            if callable(add_axes):
                add_axes()
            restore_or_reset_plotter_camera(plotter, camera_state)
            if self._show_ruler and self._ruler_static_bottom:
                self._install_static_ruler_observer(payload)

            self._animation_scene = {
                "key": self._animation_topology_key(payload),
                "grid": grid,
                "base_actor": base_actor,
                "cut_actor": cut_actor,
                "plane_poly": plane_poly,
                "plane_actor": plane_actor,
                "outline": outline,
                "outline_actor": outline_actor,
                "force_cloud": force_cloud,
                "force_actor": force_actor,
                "reference": reference,
                "reference_actor": reference_actor,
                "frame_origin_poly": frame_origin_poly,
                "frame_origin_actor": frame_origin_actor,
                "axis_actors": axis_actors,
                "frame_length": frame_length,
                "total_actor": total_actor,
                "total_origin_poly": total_origin_poly,
                "total_origin_actor": total_origin_actor,
                "nodal_actor": nodal_actor,
                "text_actor": text_actor,
                "large": large,
                "playing": bool(playing),
            }
            render = getattr(plotter, "render", None)
            if callable(render):
                render()
            self._has_rendered_payload = True

        def _update_animation_scene(
            self,
            payload: Dict[str, Any],
            *,
            playing: bool,
        ) -> None:
            import numpy as np
            import pyvista

            scene = self._animation_scene or {}
            points = payload.get("_animation_points_numpy")
            if points is None:
                points = (payload.get("mesh") or {}).get("points")
            if points is None:
                points = []
            grid = scene["grid"]
            grid.points = np.asarray(points, dtype=float)
            modified = getattr(grid, "Modified", None)
            if callable(modified):
                modified()

            cut_indices = [
                int(index)
                for index in payload.get("cut_cell_indices", [])
                if 0 <= int(index) < int(grid.n_cells)
            ]
            cut_grid = grid.extract_cells(cut_indices) if cut_indices else pyvista.UnstructuredGrid()
            self._set_actor_dataset(scene["cut_actor"], cut_grid)
            self._set_actor_visible(scene["cut_actor"], bool(cut_indices))

            corners = (payload.get("plane") or {}).get("corners") or []
            if len(corners) == 4:
                scene["plane_poly"].points = np.asarray(corners, dtype=float)
                scene["outline"].points = np.asarray(corners + [corners[0]], dtype=float)

            force_points = [
                item["xyz"]
                for item in payload.get("force_summation_nodes", [])
                if isinstance(item, dict) and "xyz" in item
            ]
            scene["force_cloud"].points = (
                np.asarray(force_points, dtype=float).reshape((-1, 3))
                if force_points
                else np.empty((0, 3), dtype=float)
            )
            self._set_actor_visible(scene["force_actor"], bool(force_points))

            reference_xyz = payload.get("moment_reference_xyz")
            if reference_xyz:
                scene["reference"].points = np.asarray([reference_xyz], dtype=float)
            self._set_actor_visible(scene["reference_actor"], bool(reference_xyz))

            frame_origin = payload.get("coordinate_system_origin") or [0.0, 0.0, 0.0]
            scene["frame_origin_poly"].points = np.asarray([frame_origin], dtype=float)
            frame_axes = payload.get("coordinate_system_axes") or {}
            for axis_name, actor in scene["axis_actors"].items():
                vector = scale_vector(
                    frame_axes.get(axis_name) or [0.0, 0.0, 0.0],
                    scene["frame_length"],
                )
                self._set_actor_dataset(
                    actor,
                    self._animation_arrow_mesh(pyvista, frame_origin, vector),
                )

            overlay = payload.get("result_overlay") or {}
            total = overlay.get("total_vector") or {}
            total_origin = total.get("origin") or frame_origin
            total_vector = total.get("display_vector") or [0.0, 0.0, 0.0]
            total_visible = vector_magnitude(total_vector) > 0.0
            self._set_actor_dataset(
                scene["total_actor"],
                self._animation_arrow_mesh(pyvista, total_origin, total_vector),
            )
            scene["total_origin_poly"].points = np.asarray([total_origin], dtype=float)
            self._set_actor_visible(scene["total_actor"], total_visible)
            self._set_actor_visible(scene["total_origin_actor"], total_visible)

            nodal_glyphs = self._animation_nodal_glyphs(pyvista, payload)
            self._set_actor_dataset(scene["nodal_actor"], nodal_glyphs)
            self._set_actor_visible(scene["nodal_actor"], int(nodal_glyphs.n_points) > 0)

            counts = payload.get("counts") or {}
            text = (
                f"{counts.get('raw_element_count', 0)} selected elements | "
                f"{counts.get('cut_element_count', 0)} cut elements | "
                f"{counts.get('force_summation_node_count', 0)} force nodes"
            )
            if overlay.get("text"):
                text += f"\n{overlay['text']}"
            text_setter = getattr(scene.get("text_actor"), "SetInput", None)
            if callable(text_setter):
                text_setter(text)

            self.set_animation_playing(playing, render_scene=False)
            if self._static_ruler_actor is not None:
                self._static_ruler_payload = payload
                self._update_static_ruler_range()
            render = getattr(self._interactor, "render", None)
            if callable(render):
                render()

        def render_animation_payload(
            self,
            payload: Dict[str, Any],
            *,
            playing: bool = False,
        ) -> bool:
            """Render one stored animation frame while retaining the scene actors."""

            if self._interactor is None:
                return False
            try:
                if (
                    self._animation_scene is None
                    or self._animation_scene.get("key")
                    != self._animation_topology_key(payload)
                ):
                    self._initialize_animation_scene(payload, playing=playing)
                else:
                    self._update_animation_scene(payload, playing=playing)
            except Exception as exc:
                self._error_label.setText(f"Animation render failed: {exc}")
                if self._error_label.parent() is None:
                    self.layout().addWidget(self._error_label)
                return False
            self._error_label.setText("")
            self._last_payload = payload
            return True

        def set_animation_playing(
            self,
            playing: bool,
            *,
            render_scene: bool = True,
        ) -> None:
            scene = self._animation_scene
            if not scene or not scene.get("large"):
                return
            changed = bool(scene.get("playing")) != bool(playing)
            scene["playing"] = bool(playing)
            actor = scene.get("base_actor")
            prop_getter = getattr(actor, "GetProperty", None)
            prop = prop_getter() if callable(prop_getter) else None
            edge_setter = getattr(prop, "SetEdgeVisibility", None)
            if callable(edge_setter):
                edge_setter(not bool(playing))
            if changed:
                modified = getattr(actor, "Modified", None)
                if callable(modified):
                    modified()
                if render_scene:
                    render = getattr(self._interactor, "render", None)
                    if callable(render):
                        render()

        def render_payload(self, payload: Dict[str, Any]) -> bool:
            if self._interactor is None:
                return False
            self._animation_scene = None
            self._last_payload = payload
            try:
                self._render_payload(payload)
            except Exception as exc:
                self._error_label.setText(f"Visualization render failed: {exc}")
                if self._error_label.parent() is None:
                    self.layout().addWidget(self._error_label)
                return False
            self._error_label.setText("")
            return True

        def _render_payload(self, payload: Dict[str, Any]) -> None:
            import numpy as np
            import pyvista

            self._clear_static_ruler_observer()
            plotter = self._interactor
            camera_state = (
                capture_plotter_camera_state(plotter)
                if self._has_rendered_payload
                else None
            )
            clear = getattr(plotter, "clear", None)
            if callable(clear):
                clear()

            mesh_payload = payload.get("mesh") or {}
            animation_points = payload.get("_animation_points_numpy")
            mesh_points = mesh_payload.get("points")
            points = (
                animation_points
                if animation_points is not None
                else mesh_points
                if mesh_points is not None
                else []
            )
            cells = mesh_payload.get("cells")
            if cells is None:
                cells = []
            celltypes = mesh_payload.get("celltypes")
            if celltypes is None:
                celltypes = []
            grid = None
            if len(points) > 0 and len(cells) > 0 and len(celltypes) > 0:
                grid = pyvista.UnstructuredGrid(cells, celltypes, points)
                plotter.add_mesh(
                    grid,
                    color="#9aa8ad",
                    opacity=0.28,
                    show_edges=True,
                    edge_color="#5e6970",
                    label="Selected named selection elements",
                )
                cut_indices = [
                    int(index)
                    for index in payload.get("cut_cell_indices", [])
                    if 0 <= int(index) < int(grid.n_cells)
                ]
                if cut_indices:
                    plotter.add_mesh(
                        grid.extract_cells(cut_indices),
                        color="#f08a24",
                        opacity=0.78,
                        show_edges=True,
                        edge_color="#7a3d0a",
                        label="Cut elements",
                    )

            plane = payload.get("plane") or {}
            corners = plane.get("corners") or []
            if len(corners) == 4:
                plane_poly = pyvista.PolyData(corners)
                plane_poly.faces = [4, 0, 1, 2, 3]
                plotter.add_mesh(
                    plane_poly,
                    color="#18a8b8",
                    opacity=0.32,
                    show_edges=True,
                    edge_color="#0a5c66",
                    label="Construction plane",
                )
                outline = pyvista.PolyData(corners + [corners[0]])
                outline.lines = [5, 0, 1, 2, 3, 4]
                plotter.add_mesh(outline, color="#0a5c66", line_width=3)

            force_nodes = [
                item["xyz"]
                for item in payload.get("force_summation_nodes", [])
                if isinstance(item, dict) and "xyz" in item
            ]
            if force_nodes:
                cloud = pyvista.PolyData(force_nodes)
                plotter.add_points(
                    cloud,
                    color="#d61f3c",
                    point_size=11,
                    render_points_as_spheres=True,
                    label="Force summation nodes",
                )

            overlay = payload.get("result_overlay") or {}
            overlay_unit = overlay.get("unit")
            nodal_vectors = overlay.get("nodal_vectors") or []
            nodal_glyph_items = nodal_vector_glyph_items(nodal_vectors)
            nodal_origins = [
                item["origin"]
                for item in nodal_glyph_items
            ]
            nodal_display_vectors = [
                item["display_vector"]
                for item in nodal_glyph_items
            ]
            nodal_display_lengths = [
                item["display_length"]
                for item in nodal_glyph_items
            ]
            nodal_magnitudes = [
                float(item.get("magnitude") or 0.0)
                for item in nodal_glyph_items
            ]
            if nodal_origins and nodal_display_vectors:
                nodal_origin_array = np.asarray(nodal_origins, dtype=float)
                nodal_vector_array = np.asarray(nodal_display_vectors, dtype=float)
                nodal_display_length_array = np.asarray(nodal_display_lengths, dtype=float)
                nodal_magnitude_array = np.asarray(nodal_magnitudes, dtype=float)
                try:
                    arrow_points = pyvista.PolyData(nodal_origin_array)
                    arrow_points["vectors"] = nodal_vector_array
                    arrow_points[VISUALIZATION_NODAL_GLYPH_SCALE_ARRAY] = (
                        nodal_display_length_array
                    )
                    arrow_points["Magnitude"] = nodal_magnitude_array
                    glyphs = arrow_points.glyph(
                        orient="vectors",
                        scale=VISUALIZATION_NODAL_GLYPH_SCALE_ARRAY,
                        factor=1.0,
                    )
                    plotter.add_mesh(
                        glyphs,
                        scalars="Magnitude",
                        cmap="turbo",
                        label="Nodal force vectors",
                        scalar_bar_args=nodal_force_scalar_bar_args(overlay_unit),
                    )
                except Exception:
                    plotter.add_arrows(
                        nodal_origin_array,
                        nodal_vector_array,
                        mag=1.0,
                        color="#f4c542",
                        label="Nodal force vectors",
                    )

            total_vector = overlay.get("total_vector") or {}
            total_origin = total_vector.get("origin")
            total_display_vector = total_vector.get("display_vector")
            if total_origin and total_display_vector and vector_magnitude(total_display_vector) > 0.0:
                total_color = str(total_vector.get("color") or "#d61f3c")
                total_origin_array = np.asarray(total_origin, dtype=float)
                total_display_vector_array = np.asarray(total_display_vector, dtype=float)
                try:
                    total_arrow = pyvista.Arrow(
                        start=total_origin_array,
                        direction=total_display_vector_array,
                        scale="auto",
                    )
                    plotter.add_mesh(
                        total_arrow,
                        color=total_color,
                        label=str(overlay.get("label") or "Result vector"),
                    )
                except Exception:
                    plotter.add_arrows(
                        np.asarray([total_origin_array], dtype=float),
                        np.asarray([total_display_vector_array], dtype=float),
                        mag=1.0,
                        color=total_color,
                        label=str(overlay.get("label") or "Result vector"),
                    )
                plotter.add_points(
                    pyvista.PolyData([total_origin_array]),
                    color=total_color,
                    point_size=13,
                    render_points_as_spheres=True,
                )

            reference_xyz = payload.get("moment_reference_xyz")
            if reference_xyz:
                reference = pyvista.PolyData([reference_xyz])
                plotter.add_points(
                    reference,
                    color="#5b3fd6",
                    point_size=14,
                    render_points_as_spheres=True,
                    label="Moment reference",
                )
                if self._show_moment_reference_label:
                    label = str(payload.get("moment_reference_label") or "Moment reference")
                    add_point_labels = getattr(plotter, "add_point_labels", None)
                    if callable(add_point_labels):
                        add_point_labels(
                            [reference_xyz],
                            [label],
                            font_size=10,
                            point_size=0,
                            always_visible=True,
                        )

            frame_origin = payload.get("coordinate_system_origin")
            frame_axes = payload.get("coordinate_system_axes") or {}
            if frame_origin and all(frame_axes.get(key) for key in ("x", "y", "z")):
                frame_length = max(visualization_scene_extent(payload) * 0.08, 1.0e-12)
                plotter.add_points(
                    pyvista.PolyData([frame_origin]),
                    color="#111827",
                    point_size=10,
                    render_points_as_spheres=True,
                    label="Reference frame origin",
                )
                for axis_name, color in (
                    ("x", "#d62828"),
                    ("y", "#2a9d47"),
                    ("z", "#2563eb"),
                ):
                    axis_vector = scale_vector(frame_axes[axis_name], frame_length)
                    plotter.add_arrows(
                        np.asarray([frame_origin], dtype=float),
                        np.asarray([axis_vector], dtype=float),
                        mag=1.0,
                        color=color,
                        label=f"Moving frame {axis_name.upper()}",
                    )

            counts = payload.get("counts") or {}
            text = (
                f"{counts.get('raw_element_count', 0)} selected elements | "
                f"{counts.get('cut_element_count', 0)} cut elements | "
                f"{counts.get('force_summation_node_count', 0)} force nodes"
            )
            if overlay.get("text"):
                text = f"{text}\n{overlay['text']}"
            add_text = getattr(plotter, "add_text", None)
            if callable(add_text):
                add_text(text, position="upper_left", font_size=9, color="#17212b")
            if self._show_ruler and not self._ruler_static_bottom:
                add_visualization_bottom_ruler(plotter, payload)
            add_axes = getattr(plotter, "add_axes", None)
            if callable(add_axes):
                add_axes()
            restore_or_reset_plotter_camera(plotter, camera_state)
            if self._show_ruler and self._ruler_static_bottom:
                self._install_static_ruler_observer(payload)
            render = getattr(plotter, "render", None)
            if callable(render):
                render()
            self._has_rendered_payload = True

        def closeEvent(self, event: Any) -> None:  # noqa: N802
            self._clear_static_ruler_observer()
            self._animation_scene = None
            super().closeEvent(event)

    class ResultHistoryPlotWidget(QtWidgets.QWidget):
        time_selected = signal(int, str)
        frame_changed = signal()
        moment_unit_changed = signal()
        collapsed_changed = signal(bool)
        dock_requested = signal()

        _COMPONENT_ORDER = ("x", "y", "z", "total")
        _COLORS = {
            "x": "#d61f3c",
            "y": "#21a366",
            "z": "#2768d8",
            "total": "#17212b",
        }

        def __init__(self, parent: Optional[Any] = None) -> None:
            super().__init__(parent)
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
            self._plot_payload: Optional[Dict[str, Any]] = None
            self._selected_time_index = 0
            self._expanded = True
            self._matplotlib_ready = False
            self._mplcursors: Optional[Any] = None
            self._plots: Dict[str, Dict[str, Any]] = {}
            self._line_meta: Dict[Any, Dict[str, Any]] = {}
            self._point_meta: Dict[Any, Dict[str, Any]] = {}
            self._legend_to_line: Dict[Any, Any] = {}
            self._trace_visibility: Dict[Tuple[str, str, str], bool] = {}
            self._cursors: List[Any] = []
            self._selected_time_markers: Dict[str, Any] = {}
            self._detached = False
            self._mode_buttons: Dict[str, Any] = {}
            self._show_time_point_markers = True
            self._frame_payload_signature: Any = None
            self._frame_user_selected = False

            root = QtWidgets.QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(2)

            header = QtWidgets.QVBoxLayout()
            header.setSpacing(2)
            title_row = QtWidgets.QHBoxLayout()
            title_row.setSpacing(6)
            control_row = QtWidgets.QHBoxLayout()
            control_row.setSpacing(8)
            self._toggle_button = CollapseHandle("", "down")
            self._toggle_button.setToolTip("Collapse or expand result history")
            self._toggle_button.clicked.connect(self.toggle_expanded)
            self._title_label = QtWidgets.QLabel("Result History")
            self._status_label = QtWidgets.QLabel("")
            self._status_label.setWordWrap(False)
            self._status_label.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            self._status_label.setToolTip("")
            self._mode_widget = QtWidgets.QWidget(self)
            self._mode_widget.setObjectName("resultHistoryModeSelector")
            self._mode_widget.setMinimumWidth(224)
            self._mode_widget.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            mode_layout = QtWidgets.QHBoxLayout(self._mode_widget)
            mode_layout.setContentsMargins(0, 0, 0, 0)
            mode_layout.setSpacing(0)
            self._mode_group = QtWidgets.QButtonGroup(self)
            self._mode_group.setExclusive(True)
            for mode_key, title in (
                ("force", "Force"),
                ("moment", "Moment"),
                ("overlay", "Overlay"),
            ):
                button = QtWidgets.QToolButton(self._mode_widget)
                button.setObjectName("resultHistoryModeButton")
                button.setText(title)
                button.setCheckable(True)
                button.setAutoRaise(False)
                button.setFixedHeight(24)
                button.setMinimumWidth(72 if mode_key != "moment" else 80)
                button.clicked.connect(
                    lambda _checked=False, key=mode_key: self._set_history_page(key)
                )
                self._mode_group.addButton(button)
                mode_layout.addWidget(button)
                self._mode_buttons[mode_key] = button
            self._mode_buttons["force"].setChecked(True)
            self._mode_widget.setStyleSheet(
                """
                QWidget#resultHistoryModeSelector {
                    background: #eaf1f4;
                    border: 1px solid #b9c5ca;
                    border-radius: 5px;
                }
                QToolButton#resultHistoryModeButton {
                    background: transparent;
                    border: 0;
                    border-right: 1px solid #b9c5ca;
                    border-radius: 0;
                    color: #52616b;
                    padding: 2px 10px;
                    font-weight: 500;
                }
                QToolButton#resultHistoryModeButton:hover {
                    background: #dce9ea;
                    color: #26343d;
                }
                QToolButton#resultHistoryModeButton:checked {
                    background: #ffffff;
                    color: #1f2a33;
                    font-weight: 600;
                }
                QToolButton#resultHistoryModeButton:disabled {
                    color: #8b9ca3;
                    background: #f4f7f8;
                }
                """
            )
            self._frame_combo = ChevronComboBox()
            self._frame_combo.addItem("Global", "global")
            self._frame_combo.addItem("Local", "local")
            self._frame_combo.setToolTip(RESULT_FRAME_TOOLTIP)
            self._frame_combo.setItemData(
                0,
                "Show global XYZ components of resultants computed about the "
                "selected Moment reference point.",
                QtCore.Qt.ItemDataRole.ToolTipRole,
            )
            self._frame_combo.setItemData(
                1,
                "Show local coordinate-system components of resultants computed "
                "about the selected Moment reference point.",
                QtCore.Qt.ItemDataRole.ToolTipRole,
            )
            self._frame_combo.currentIndexChanged.connect(self._on_frame_changed)
            self._moment_unit_combo = ChevronComboBox()
            self._moment_unit_combo.setMinimumWidth(104)
            self._moment_unit_combo.setToolTip(
                "Moment unit used by the result-history plots."
            )
            for label, value in MOMENT_DISPLAY_UNIT_CHOICES:
                self._moment_unit_combo.addItem(label, value)
            self._moment_unit_combo.currentIndexChanged.connect(
                lambda _index: self.moment_unit_changed.emit()
            )
            self._time_point_markers_checkbox = ThemedCheckBox("Time circles", self)
            self._time_point_markers_checkbox.setChecked(True)
            self._time_point_markers_checkbox.setToolTip(
                "Show or hide circular markers at each time point on the result-history lines."
            )
            self._time_point_markers_checkbox.toggled.connect(
                self.set_time_point_markers_visible
            )
            self._dock_button = QtWidgets.QToolButton()
            self._dock_button.setObjectName("resultHistoryDockButton")
            self._dock_button.setFixedSize(28, 24)
            self._dock_button.setAutoRaise(True)
            self._dock_button.clicked.connect(self.dock_requested.emit)
            title_row.addWidget(self._toggle_button)
            title_row.addWidget(self._title_label)
            title_row.addStretch(1)
            frame_label = QtWidgets.QLabel("Coordinate System:")
            frame_label.setToolTip(RESULT_FRAME_TOOLTIP)
            title_row.addWidget(frame_label)
            title_row.addWidget(self._frame_combo)
            title_row.addSpacing(4)
            title_row.addWidget(QtWidgets.QLabel("Moment unit:"))
            title_row.addWidget(self._moment_unit_combo)
            title_row.addWidget(self._dock_button)
            control_row.addSpacing(34)
            control_row.addWidget(self._mode_widget)
            control_row.addWidget(self._time_point_markers_checkbox)
            control_row.addWidget(self._status_label, 1)
            header.addLayout(title_row)
            header.addLayout(control_row)
            root.addLayout(header)
            self.set_detached(False)

            self._body_widget = QtWidgets.QWidget(self)
            self._body_widget.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
            body_layout = QtWidgets.QVBoxLayout(self._body_widget)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(2)

            try:
                from matplotlib.backends.backend_qtagg import (
                    FigureCanvasQTAgg as FigureCanvas,
                )
                from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
                from matplotlib.figure import Figure
            except Exception as exc:
                self._status_label.setText(
                    "Matplotlib result history is unavailable: " + str(exc)
                )
                self._status_label.setToolTip(self._status_label.text())
                self._frame_combo.setEnabled(False)
                self._mode_widget.setEnabled(False)
            else:
                self._matplotlib_ready = True
                try:
                    import mplcursors
                except Exception:
                    self._mplcursors = None
                else:
                    self._mplcursors = mplcursors
                self._plot_stack = QtWidgets.QStackedWidget()
                self._plot_stack.setObjectName("resultHistoryPlotStack")
                self._plot_stack.setSizePolicy(
                    QtWidgets.QSizePolicy.Policy.Expanding,
                    QtWidgets.QSizePolicy.Policy.Expanding,
                )
                self._plot_stack.setStyleSheet(
                    """
                    QStackedWidget#resultHistoryPlotStack {
                        border: 1px solid #d4dee2;
                        border-radius: 5px;
                        background: #ffffff;
                    }
                    """
                )
                for key, title in (
                    ("force", "Force"),
                    ("moment", "Moment"),
                    ("overlay", "Overlay"),
                ):
                    figure = Figure(figsize=(5.0, 2.4), dpi=100)
                    canvas = FigureCanvas(figure)
                    canvas.setMinimumHeight(VISUALIZATION_HISTORY_CANVAS_MIN_HEIGHT)
                    canvas.setSizePolicy(
                        QtWidgets.QSizePolicy.Policy.Expanding,
                        QtWidgets.QSizePolicy.Policy.Expanding,
                    )
                    canvas.mpl_connect("pick_event", self._on_pick_event)
                    canvas.mpl_connect("button_press_event", self._on_button_press)
                    toolbar = NavigationToolbar2QT(canvas, self)
                    self._theme_matplotlib_toolbar(toolbar)
                    page = QtWidgets.QWidget()
                    page.setSizePolicy(
                        QtWidgets.QSizePolicy.Policy.Expanding,
                        QtWidgets.QSizePolicy.Policy.Expanding,
                    )
                    page_layout = QtWidgets.QVBoxLayout(page)
                    page_layout.setContentsMargins(0, 0, 0, 0)
                    page_layout.addWidget(toolbar)
                    page_layout.addWidget(canvas, 1)
                    self._plot_stack.addWidget(page)
                    self._plots[key] = {
                        "figure": figure,
                        "canvas": canvas,
                        "toolbar": toolbar,
                    }
                body_layout.addWidget(self._plot_stack, 1)
            root.addWidget(self._body_widget, 1)
            self.clear_history("Run extraction and update visualization to show result history.")

        def _transparent_qt_color(self) -> Any:
            return (
                QtCore.Qt.GlobalColor.transparent
            )

        def _image_format_argb32(self) -> Any:
            return (
                QtGui.QImage.Format.Format_ARGB32_Premultiplied
            )

        def _tinted_toolbar_icon(
            self,
            icon: Any,
            color: str = "#26343d",
            size: Optional[Any] = None,
        ) -> Any:
            if icon.isNull():
                return icon
            if size is None:
                size = QtCore.QSize(
                    VISUALIZATION_HISTORY_TOOLBAR_ICON_SIZE,
                    VISUALIZATION_HISTORY_TOOLBAR_ICON_SIZE,
                )
            pixmap = icon.pixmap(size)
            if pixmap.isNull():
                return icon
            image = QtGui.QImage(pixmap.size(), self._image_format_argb32())
            image.fill(self._transparent_qt_color())
            painter = QtGui.QPainter(image)
            painter.drawPixmap(0, 0, pixmap)
            painter.setCompositionMode(
                QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
            )
            painter.fillRect(image.rect(), QtGui.QColor(color))
            painter.end()
            return QtGui.QIcon(QtGui.QPixmap.fromImage(image))

        def _theme_matplotlib_toolbar(self, toolbar: Any) -> None:
            toolbar.setObjectName("resultHistoryMatplotlibToolbar")
            icon_size = QtCore.QSize(
                VISUALIZATION_HISTORY_TOOLBAR_ICON_SIZE,
                VISUALIZATION_HISTORY_TOOLBAR_ICON_SIZE,
            )
            toolbar.setIconSize(icon_size)
            toolbar.setMovable(False)
            toolbar.setFloatable(False)
            toolbar.setStyleSheet(
                """
                QToolBar#resultHistoryMatplotlibToolbar {
                    background: #ffffff;
                    border: 1px solid #d4dee2;
                    border-radius: 5px;
                    spacing: 2px;
                    padding: 3px;
                    color: #26343d;
                }
                QToolBar#resultHistoryMatplotlibToolbar QToolButton {
                    background: transparent;
                    border: 1px solid transparent;
                    border-radius: 4px;
                    color: #26343d;
                    padding: 3px;
                    margin: 1px;
                }
                QToolBar#resultHistoryMatplotlibToolbar QToolButton:hover {
                    background: #edf5f3;
                    border-color: #acc2bd;
                }
                QToolBar#resultHistoryMatplotlibToolbar QToolButton:checked,
                QToolBar#resultHistoryMatplotlibToolbar QToolButton:pressed {
                    background: #dcece8;
                    border-color: #2d7f72;
                }
                QToolBar#resultHistoryMatplotlibToolbar QToolButton:disabled {
                    color: #8b9ca3;
                }
                QToolBar#resultHistoryMatplotlibToolbar QLabel {
                    color: #26343d;
                }
                """
            )
            for action in toolbar.actions():
                icon = action.icon()
                if icon is not None and not icon.isNull():
                    action.setIcon(self._tinted_toolbar_icon(icon, size=icon_size))

        def _set_history_page(self, mode_key: str) -> None:
            plot_keys = list(self._plots)
            try:
                page_index = plot_keys.index(mode_key)
            except ValueError:
                return
            if hasattr(self, "_plot_stack"):
                self._plot_stack.setCurrentIndex(page_index)
            button = self._mode_buttons.get(mode_key)
            if button is not None:
                button.setChecked(True)

        def current_frame(self) -> str:
            return str(self._frame_combo.currentData() or "global")

        def _set_frame(self, frame: str) -> None:
            target = "local" if str(frame).strip().lower() == "local" else "global"
            for index in range(self._frame_combo.count()):
                if str(self._frame_combo.itemData(index) or "") == target:
                    blocked = self._frame_combo.blockSignals(True)
                    try:
                        self._frame_combo.setCurrentIndex(index)
                    finally:
                        self._frame_combo.blockSignals(blocked)
                    return

        def _on_frame_changed(self, _index: int) -> None:
            self._frame_user_selected = True
            self.frame_changed.emit()

        def frame_for_payload(self, payload_signature: Any, default_frame: str) -> str:
            if payload_signature != self._frame_payload_signature:
                self._frame_payload_signature = payload_signature
                self._frame_user_selected = False
            if not self._frame_user_selected:
                self._set_frame(default_frame)
            return self.current_frame()

        def current_moment_unit(self) -> Optional[str]:
            value = self._moment_unit_combo.currentData()
            if value is None:
                return None
            return str(value)

        def is_collapsed(self) -> bool:
            return not self._expanded

        def is_detached(self) -> bool:
            return self._detached

        def set_detached(self, detached: bool) -> None:
            self._detached = bool(detached)
            if self._detached:
                self._dock_button.setIcon(_themed_control_icon("dock", "#236b5f"))
                self._dock_button.setToolTip("Dock result history inside visualization")
            else:
                self._dock_button.setIcon(_themed_control_icon("float", "#236b5f"))
                self._dock_button.setToolTip("Undock result history")

        def _source_moment_unit(self) -> Optional[str]:
            if self._plot_payload is None:
                return None
            source_units = self._plot_payload.get("source_result_units") or {}
            unit = source_units.get("moment")
            if not unit:
                result_units = self._plot_payload.get("result_units") or {}
                unit = result_units.get("moment")
            if not unit:
                moment = self._plot_payload.get("moment") or {}
                unit = moment.get("unit")
            unit_text = str(unit or "").strip()
            return unit_text or None

        def _refresh_moment_unit_combo(self) -> None:
            source_unit = self._source_moment_unit()
            source_label = f"Source ({source_unit})" if source_unit else "Source"
            blocked = self._moment_unit_combo.blockSignals(True)
            try:
                if self._moment_unit_combo.count():
                    self._moment_unit_combo.setItemText(0, source_label)
            finally:
                self._moment_unit_combo.blockSignals(blocked)
            self._moment_unit_combo.setEnabled(
                self._matplotlib_ready
                and self._plot_payload is not None
                and bool(source_unit)
            )

        def toggle_expanded(self) -> None:
            self.set_expanded(not self._expanded)

        def set_expanded(self, expanded: bool) -> None:
            expanded = bool(expanded)
            if expanded == self._expanded:
                return
            self._expanded = expanded
            self._body_widget.setVisible(expanded)
            self._toggle_button.set_direction("down" if expanded else "right")
            self.collapsed_changed.emit(not expanded)

        def clear_history(self, message: str) -> None:
            self._plot_payload = None
            self._frame_payload_signature = None
            self._frame_user_selected = False
            self._line_meta.clear()
            self._point_meta.clear()
            self._legend_to_line.clear()
            self._selected_time_markers.clear()
            self._clear_cursors()
            self._status_label.setText(message)
            self._status_label.setToolTip(message)
            self._frame_combo.setEnabled(False)
            self._mode_widget.setEnabled(False)
            self._refresh_moment_unit_combo()
            self._time_point_markers_checkbox.setEnabled(False)
            if hasattr(self, "_plot_stack"):
                self._plot_stack.setEnabled(False)
            for plot in self._plots.values():
                figure = plot["figure"]
                figure.clear()
                plot["canvas"].draw_idle()

        def set_history_payload(
            self,
            payload: Optional[Dict[str, Any]],
            selected_time_index: int,
        ) -> None:
            if not payload:
                self.clear_history(
                    "Run extraction and update visualization to show result history."
                )
                return
            self._plot_payload = payload
            self._selected_time_index = self._clamped_time_index(selected_time_index)
            static_history = payload.get("analysis_mode") == "static"
            self._time_point_markers_checkbox.setText(
                "Set circles" if static_history else "Time circles"
            )
            self._time_point_markers_checkbox.setToolTip(
                "Show or hide circular markers at each solved cumulative result set."
                if static_history
                else "Show or hide circular markers at each time point on the result-history lines."
            )
            self._frame_combo.setEnabled(True)
            self._mode_widget.setEnabled(self._matplotlib_ready)
            self._refresh_moment_unit_combo()
            self._time_point_markers_checkbox.setEnabled(self._matplotlib_ready)
            if hasattr(self, "_plot_stack"):
                self._plot_stack.setEnabled(self._matplotlib_ready)
            self._update_history_status_text()
            self._draw_all_plots()

        def set_selected_time_index(self, selected_time_index: int) -> None:
            if self._plot_payload is None:
                return
            selected = self._clamped_time_index(selected_time_index)
            if selected == self._selected_time_index:
                return
            self._selected_time_index = selected
            x_values = self._history_x_values()
            if not x_values:
                return
            x_value = float(x_values[selected])
            canvases: Dict[int, Any] = {}
            for plot_key, marker in self._selected_time_markers.items():
                marker.set_xdata([x_value, x_value])
                canvas = (self._plots.get(plot_key) or {}).get("canvas")
                if canvas is not None:
                    canvases[id(canvas)] = canvas
            for canvas in canvases.values():
                canvas.draw_idle()

        def set_time_point_markers_visible(self, visible: bool) -> None:
            visible = bool(visible)
            if visible == self._show_time_point_markers:
                return
            self._show_time_point_markers = visible
            self._update_history_status_text()
            self._draw_all_plots()

        def _update_history_status_text(self) -> None:
            if self._plot_payload is None:
                return
            static_history = self._plot_payload.get("analysis_mode") == "static"
            target_name = "set" if static_history else "time"
            marker_name = "set circles" if static_history else "time circles"
            if self._show_time_point_markers:
                target_text = (
                    f"Double-click a point to show that {target_name} in the 3D view."
                )
                hover_text = f" Hover over {marker_name} for values."
            else:
                target_text = (
                    f"Double-click near a line vertex to show that {target_name} "
                    "in the 3D view."
                )
                hover_text = " Hover over plot lines for values."
            if self._mplcursors is None:
                hover_text = " Hover annotations unavailable; install mplcursors."
            status_text = (
                f"Result history ready: {len(self._plot_payload.get('times') or [])} "
                f"{'cumulative result set(s)' if static_history else 'time point(s)'}. "
                f"{target_text}{hover_text}"
            )
            self._status_label.setText(status_text)
            self._status_label.setToolTip(status_text)

        def _clamped_time_index(self, selected_time_index: int) -> int:
            if not self._plot_payload:
                return 0
            x_values = self._history_x_values()
            if not x_values:
                return 0
            return max(0, min(int(selected_time_index), len(x_values) - 1))

        def _history_x_values(self) -> List[float]:
            if not self._plot_payload:
                return []
            x_axis = self._plot_payload.get("x_axis") or {}
            values = x_axis.get("values")
            if values is None:
                values = self._plot_payload.get("times") or []
            return [float(value) for value in values]

        def _history_x_label(self) -> str:
            if not self._plot_payload:
                return "Time [s]"
            return str((self._plot_payload.get("x_axis") or {}).get("label") or "Time [s]")

        def _history_point_label(self, index: int) -> str:
            if not self._plot_payload:
                return f"row {index + 1}"
            labels = (self._plot_payload.get("x_axis") or {}).get("point_labels") or []
            if 0 <= int(index) < len(labels):
                return str(labels[int(index)])
            x_values = self._history_x_values()
            if 0 <= int(index) < len(x_values):
                return f"x={x_values[int(index)]:.6g}"
            return f"row {index + 1}"

        def _draw_all_plots(self) -> None:
            if not self._matplotlib_ready or not self._plot_payload:
                return
            self._line_meta.clear()
            self._point_meta.clear()
            self._legend_to_line.clear()
            self._selected_time_markers.clear()
            self._clear_cursors()
            self._draw_single_mode_plot("force")
            self._draw_single_mode_plot("moment")
            self._draw_overlay_plot()

        def _clear_cursors(self) -> None:
            for cursor in self._cursors:
                remove = getattr(cursor, "remove", None)
                if callable(remove):
                    remove()
            self._cursors = []

        def _draw_single_mode_plot(self, mode: str) -> None:
            plot = self._plots[mode]
            figure = plot["figure"]
            canvas = plot["canvas"]
            figure.clear()
            axis = figure.add_subplot(111)
            lines = self._add_component_lines(
                axis,
                tab_key=mode,
                result_mode=mode,
                linestyle="-",
            )
            label = "Force Reaction" if mode == "force" else "Moment Reaction"
            axis.set_title(f"{label} ({self.current_frame()})")
            axis.set_xlabel(self._history_x_label())
            axis.set_ylabel(label_with_unit(label, self._plot_unit(mode)))
            axis.grid(True, color="#d3dde2", linewidth=0.7)
            marker = self._add_selected_time_marker(axis)
            if marker is not None:
                self._selected_time_markers[mode] = marker
            self._install_legend(axis, lines)
            self._install_cursor(self._cursor_artists_for_lines(lines))
            figure.tight_layout()
            canvas.draw_idle()

        def _draw_overlay_plot(self) -> None:
            plot = self._plots["overlay"]
            figure = plot["figure"]
            canvas = plot["canvas"]
            figure.clear()
            force_axis = figure.add_subplot(111)
            moment_axis = force_axis.twinx()
            force_lines = self._add_component_lines(
                force_axis,
                tab_key="overlay",
                result_mode="force",
                linestyle="-",
            )
            moment_lines = self._add_component_lines(
                moment_axis,
                tab_key="overlay",
                result_mode="moment",
                linestyle="--",
            )
            force_axis.set_title(f"Force and Moment ({self.current_frame()})")
            force_axis.set_xlabel(self._history_x_label())
            force_axis.set_ylabel(
                label_with_unit("Force Reaction", self._plot_unit("force"))
            )
            moment_axis.set_ylabel(
                label_with_unit("Moment Reaction", self._plot_unit("moment"))
            )
            force_axis.grid(True, color="#d3dde2", linewidth=0.7)
            marker = self._add_selected_time_marker(force_axis)
            if marker is not None:
                self._selected_time_markers["overlay"] = marker
            lines = force_lines + moment_lines
            self._install_legend(force_axis, lines)
            self._install_cursor(self._cursor_artists_for_lines(lines))
            figure.tight_layout()
            canvas.draw_idle()

        def _plot_unit(self, mode: str) -> Optional[str]:
            if self._plot_payload is None:
                return None
            result = self._plot_payload.get(str(mode)) or {}
            unit = result.get("unit")
            if unit:
                return str(unit)
            return (self._plot_payload.get("result_units") or {}).get(str(mode))

        def _add_component_lines(
            self,
            axis: Any,
            *,
            tab_key: str,
            result_mode: str,
            linestyle: str,
        ) -> List[Any]:
            if self._plot_payload is None:
                return []
            times = self._history_x_values()
            result = self._plot_payload.get(result_mode) or {}
            components = result.get("components") or {}
            labels = result.get("labels") or {}
            lines = []
            time_values = [float(time_value) for time_value in times]
            for component in self._COMPONENT_ORDER:
                values = [float(value) for value in components.get(component, [])]
                if len(values) != len(time_values):
                    continue
                visibility_key = (tab_key, result_mode, component)
                visible = self._trace_visibility.get(visibility_key, True)
                line_label = str(labels.get(component) or component)
                line = axis.plot(
                    time_values,
                    values,
                    label=line_label,
                    color=self._COLORS[component],
                    linestyle=linestyle,
                    linewidth=1.6,
                    visible=visible,
                )[0]
                point_artist = axis.scatter(
                    time_values,
                    values,
                    s=18,
                    color=self._COLORS[component],
                    edgecolors="#ffffff",
                    linewidths=0.55,
                    visible=visible and self._show_time_point_markers,
                    zorder=line.get_zorder() + 1.0,
                    label="_nolegend_",
                )
                self._line_meta[line] = {
                    "tab": tab_key,
                    "mode": result_mode,
                    "component": component,
                    "label": line_label,
                    "times": time_values,
                    "values": values,
                    "point_artist": point_artist,
                    "visibility_key": visibility_key,
                }
                self._point_meta[point_artist] = self._line_meta[line]
                lines.append(line)
            return lines

        def _add_selected_time_marker(self, axis: Any) -> Optional[Any]:
            if self._plot_payload is None:
                return None
            x_values = self._history_x_values()
            if not x_values:
                return None
            x_value = float(x_values[self._clamped_time_index(self._selected_time_index)])
            return axis.axvline(
                x_value,
                color="#17212b",
                linestyle=":",
                linewidth=1.2,
                alpha=0.75,
            )

        def _install_legend(self, axis: Any, lines: Sequence[Any]) -> None:
            if not lines:
                return
            legend = axis.legend(lines, [line.get_label() for line in lines], fontsize=8)
            handles = getattr(legend, "legend_handles", None)
            if handles is None:
                handles = getattr(legend, "legendHandles", [])
            for legend_line, line in zip(handles, lines):
                legend_line.set_picker(6)
                legend_line.set_alpha(1.0 if line.get_visible() else 0.25)
                self._legend_to_line[legend_line] = line

        def _cursor_artists_for_lines(self, lines: Sequence[Any]) -> List[Any]:
            cursor_artists = []
            for line in lines:
                if not line.get_visible():
                    continue
                if not self._show_time_point_markers:
                    cursor_artists.append(line)
                    continue
                point_artist = (self._line_meta.get(line) or {}).get("point_artist")
                if point_artist is not None:
                    cursor_artists.append(point_artist)
            return cursor_artists

        def _install_cursor(self, artists: Sequence[Any]) -> None:
            if self._mplcursors is None or not artists:
                return
            cursor = self._mplcursors.cursor(list(artists), hover=True)
            cursor.connect("add", self._annotate_cursor_selection)
            self._cursors.append(cursor)

        def _annotate_cursor_selection(self, selection: Any) -> None:
            artist = selection.artist
            meta = self._point_meta.get(artist) or self._line_meta.get(artist)
            if self._plot_payload is None or not meta:
                return
            times = self._history_x_values()
            values = meta.get("values") or []
            if not times or not values:
                return
            try:
                raw_index = selection.index
                if isinstance(raw_index, (list, tuple)):
                    raw_index = raw_index[0]
                index = int(raw_index)
            except (TypeError, ValueError):
                try:
                    index = int(round(float(selection.index)))
                except (TypeError, ValueError):
                    index = 0
            index = max(0, min(index, min(len(times), len(values)) - 1))
            mode = str(meta["mode"])
            total = (
                (self._plot_payload.get(mode) or {})
                .get("components", {})
                .get("total", [])
            )
            total_value = float(total[index]) if index < len(total) else 0.0
            total_label = "Ftotal" if mode == "force" else "Mtotal"
            unit = self._plot_unit(mode)
            unit_suffix = f" {unit}" if unit else ""
            time_value = float(times[index])
            value = float(values[index])
            try:
                selection.annotation.xy = (time_value, value)
                selection.annotation.xycoords = "data"
            except AttributeError:
                pass
            selection.annotation.set_text(
                f"{meta['label']}\n"
                f"row {index + 1}, {self._history_point_label(index)}\n"
                f"value={value:.6g}{unit_suffix}\n"
                f"{total_label}={total_value:.6g}{unit_suffix}"
            )

        def _on_pick_event(self, event: Any) -> None:
            line = self._legend_to_line.get(event.artist)
            if line is None:
                return
            meta = self._line_meta.get(line)
            if not meta:
                return
            visible = not line.get_visible()
            line.set_visible(visible)
            point_artist = meta.get("point_artist")
            if point_artist is not None:
                point_artist.set_visible(visible and self._show_time_point_markers)
            self._trace_visibility[meta["visibility_key"]] = visible
            event.artist.set_alpha(1.0 if visible else 0.25)
            canvas = line.figure.canvas
            canvas.draw_idle()

        def _on_button_press(self, event: Any) -> None:
            if not getattr(event, "dblclick", False) or self._plot_payload is None:
                return
            tab_key = self._tab_key_for_canvas(event.canvas)
            if tab_key is None:
                return
            candidates = self._history_point_candidates(tab_key)
            nearest = nearest_history_point(candidates, event.x, event.y)
            if nearest is None:
                return
            self.time_selected.emit(
                int(nearest["time_index"]),
                str(nearest.get("mode") or "force"),
            )

        def _tab_key_for_canvas(self, canvas: Any) -> Optional[str]:
            for key, plot in self._plots.items():
                if plot.get("canvas") is canvas:
                    return key
            return None

        def _history_point_candidates(self, tab_key: str) -> List[Dict[str, Any]]:
            candidates: List[Dict[str, Any]] = []
            for line, meta in self._line_meta.items():
                if meta.get("tab") != tab_key or not line.get_visible():
                    continue
                x_values = line.get_xdata()
                y_values = line.get_ydata()
                for index, (x_value, y_value) in enumerate(zip(x_values, y_values)):
                    try:
                        x_pixel, y_pixel = line.axes.transData.transform(
                            (float(x_value), float(y_value))
                        )
                    except (TypeError, ValueError):
                        continue
                    candidates.append(
                        {
                            "time_index": index,
                            "mode": meta.get("mode"),
                            "component": meta.get("component"),
                            "x_pixel": x_pixel,
                            "y_pixel": y_pixel,
                        }
                    )
            return candidates

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self, cfg: SectionConfig) -> None:
            super().__init__()
            self.setWindowTitle("DPF Section Resultants")
            self.resize(2040, 1080)
            self.worker: Optional[ExtractionThread] = None
            self.visualization_worker: Optional[VisualizationThread] = None
            self.animation_worker: Optional[StaticAnimationLoaderThread] = None
            self._visualization_generation = 0
            self._visualization_input_revision = 0
            self._queued_visualization_result_set_id: Optional[int] = None
            self._last_visualization_payload: Optional[Dict[str, Any]] = None
            self._last_visualization_result_data: Optional[Dict[str, Any]] = None
            self._visualization_stale = True
            self._animation_generation = 0
            self._animation_session: Optional[StaticAnimationSession] = None
            self._animation_signature: Optional[
                StaticAnimationSessionSignature
            ] = None
            self._animation_progress = 0.0
            self._animation_direction = 1
            self._animation_playing = False
            self._animation_play_requested = False
            self._animation_render_busy = False
            self._animation_slider_dragging = False
            self._animation_preview_time_options = False
            self._closing_after_animation = False
            self._main_panel_collapsed = False
            self._main_panel_expanded_width = 0
            self._visualization_collapsed = False
            self._visualization_expanded_width = VISUALIZATION_DOCK_DEFAULT_WIDTH
            self._result_history_expanded_height = VISUALIZATION_HISTORY_DEFAULT_HEIGHT
            self._run_log_expanded_height = 180
            self._result_history_detached = False
            self._result_history_reembedding = False
            self._result_history_plot_visible = True
            self._result_history_floating_geometry: Optional[Any] = None

            self.modal_row = FileRow("open", "Ansys result files (*.rst);;All files (*)")
            self.mcf_row = FileRow("open", "MSUP modal coordinate files (*.mcf);;All files (*)")
            self.out_row = FileRow("save", "CSV files (*.csv);;All files (*)")
            self.external_selection_row = FileRow(
                "open",
                "Mechanical named selections (*.txt *.csv *.cdb);;All files (*)",
            )
            self.external_selection_row.setToolTip(
                "Optional Mechanical named-selection export. Text exports are "
                "generated node IDs; CDB exports expose NODE/ELEMENT components."
            )
            self.analysis_mode_combo = ChevronComboBox()
            self.analysis_mode_combo.setObjectName("analysisModeCombo")
            self.result_set_combo = ChevronComboBox()
            self.result_set_combo.setObjectName("resultSetCombo")
            self.result_set_combo.setMinimumWidth(220)
            self.result_set_combo.setToolTip(
                "Cumulative DPF result-set ID used by Static Structural extraction."
            )
            self.static_set_scope_combo = ChevronComboBox()
            self.static_set_scope_combo.setObjectName("staticSetScopeCombo")
            self.static_set_scope_combo.setToolTip(
                "Single extracts one solved set. Range uses an inclusive set-ID "
                "range and stride. All uses every cumulative Static Structural "
                "result set. Range and All enable deformation preview."
            )
            self.result_set_range_start_spin = QtWidgets.QSpinBox()
            self.result_set_range_end_spin = QtWidgets.QSpinBox()
            self.result_set_range_stride_spin = QtWidgets.QSpinBox()
            self.result_set_range_start_spin.setToolTip(
                "First Static Structural result-set ID included in the range."
            )
            self.result_set_range_end_spin.setToolTip(
                "Last Static Structural result-set ID included in the range."
            )
            self.result_set_range_stride_spin.setToolTip(
                "Use every Nth result set between Start and End. A larger stride "
                "reduces extraction and animation frames."
            )
            for spin in (
                self.result_set_range_start_spin,
                self.result_set_range_end_spin,
            ):
                spin.setRange(1, 1)
            self.result_set_range_stride_spin.setRange(1, 100000)
            self.result_set_range_stride_spin.setValue(1)
            self.all_result_sets_label = QtWidgets.QLabel("All result sets")
            self.all_result_sets_label.setObjectName("allResultSetsLabel")
            self._pending_result_set_id: Optional[int] = None
            self._pending_result_set_range_start: Optional[int] = None
            self._pending_result_set_range_end: Optional[int] = None
            self._loaded_result_sets: List[Dict[str, Any]] = []
            self._applying_config = False
            self._loaded_element_named_selections: List[str] = []
            self._loaded_coordinate_system_options: List[Dict[str, Any]] = []
            self.element_combo = ChevronComboBox()
            self.element_combo.setEditable(True)
            self.element_combo.setMinimumWidth(420)
            self.element_combo.setMaxVisibleItems(20)
            self.element_combo.setToolTip(
                "Choose a usable RST named selection, or load an external Mechanical "
                "text/CDB export above. Text NODE IDs and CDB NODE components are "
                "converted to fully-contained elements; CDB ELEMENT components are "
                "used directly."
            )
            if self.element_combo.lineEdit():
                self.element_combo.lineEdit().setToolTip(self.element_combo.toolTip())
                if hasattr(self.element_combo.lineEdit(), "setPlaceholderText"):
                    self.element_combo.lineEdit().setPlaceholderText(
                        "Load an RST or external named-selection export"
                    )
            self.coordinate_system_combo = ChevronComboBox()
            self.coordinate_system_combo.setEditable(True)
            self.coordinate_system_combo.setMinimumWidth(420)
            self.coordinate_system_combo.setMaxVisibleItems(20)
            self.coordinate_system_combo.setToolTip(
                COORDINATE_SYSTEM_TOOLTIP
            )
            if self.coordinate_system_combo.lineEdit():
                self.coordinate_system_combo.lineEdit().setToolTip(
                    self.coordinate_system_combo.toolTip()
                )
                if hasattr(self.coordinate_system_combo.lineEdit(), "setPlaceholderText"):
                    self.coordinate_system_combo.lineEdit().setPlaceholderText(
                        "Load an RST, then search by CS ID, name, or APDL name"
                    )
            self.origin_edits = [QtWidgets.QLineEdit() for _ in range(3)]
            for edit, placeholder in zip(
                self.origin_edits,
                ("X [mm]", "Y [mm]", "Z [mm]"),
            ):
                edit.setToolTip(ORIGIN_TOOLTIP)
                if hasattr(edit, "setPlaceholderText"):
                    edit.setPlaceholderText(placeholder)
            self.axis_edits = {
                "x": [QtWidgets.QLineEdit() for _ in range(3)],
                "y": [QtWidgets.QLineEdit() for _ in range(3)],
                "z": [QtWidgets.QLineEdit() for _ in range(3)],
            }
            self.normal_combo = ChevronComboBox()
            self.side_combo = ChevronComboBox()
            self.moment_combo = ChevronComboBox()
            self.reference_frame_motion_combo = ChevronComboBox()
            self.reference_frame_motion_combo.setObjectName("referenceFrameMotionCombo")
            self.reference_frame_motion_combo.setToolTip(
                "Follow Geometry transports the section plane and moment-reference "
                "origin and orientation with the deformed attachment nodes at every "
                "selected solved set, and is the default moving-section option. "
                "Fixed keeps the initial plane and cut membership in global space "
                "to match an Ansys Mechanical Construction Surface."
            )
            self.reference_frame_attachment_combo = ChevronComboBox()
            self.reference_frame_attachment_combo.setObjectName(
                "referenceFrameAttachmentCombo"
            )
            self.reference_frame_attachment_combo.setEditable(True)
            self.reference_frame_attachment_combo.setMinimumWidth(320)
            self.reference_frame_attachment_combo.setToolTip(
                "Optional NODE/ELEMENT named-selection override used to transport "
                "the initial frame. Leave empty to use all nodes of the initial "
                "section-cut elements."
            )
            self.reference_frame_fit_warning_spin = QtWidgets.QDoubleSpinBox()
            self.reference_frame_fit_warning_spin.setRange(0.0, 100.0)
            self.reference_frame_fit_warning_spin.setDecimals(3)
            self.reference_frame_fit_warning_spin.setSuffix(" %")
            self.reference_frame_fit_warning_spin.setValue(1.0)
            self.reference_frame_fit_warning_spin.setToolTip(
                "Warn and continue when the rigid-fit RMS residual divided by the "
                "tracking span exceeds this percentage."
            )
            self.reference_frame_tracking_status_label = QtWidgets.QLabel(
                "Attachment: local section-cut neighborhood"
            )
            self.reference_frame_tracking_status_label.setObjectName(
                "referenceFrameTrackingStatusLabel"
            )
            self.reference_frame_tracking_status_label.setToolTip(
                "Shows which nodes transport the frame. The default uses nodes from "
                "the initial section-cut elements; Advanced frame attachment can "
                "override them with a named selection."
            )
            self.tolerance_edit = QtWidgets.QLineEdit()
            self.force_type_combo = ChevronComboBox()
            self.modal_batch_spin = QtWidgets.QSpinBox()
            self.modal_batch_spin.setRange(1, 100000)
            self.modal_batch_spin.setSuffix(" modes")
            self.modal_batch_spin.setToolTip(
                "Maximum modal sets requested from DPF force_summation at once. "
                "Lower this if large modal RST files hit memory allocation errors."
            )
            self.skip_first_modes_spin = QtWidgets.QSpinBox()
            self.skip_first_modes_spin.setRange(0, 100000)
            self.skip_first_modes_spin.setSuffix(" modes")
            self.skip_first_modes_spin.setToolTip(
                "Skip the first N MCF modal coordinate columns and matching RST "
                "modal set IDs before modal summation."
            )
            self.scan_coordinate_system_button = QtWidgets.QPushButton(
                "Scan DPF Coordinate Systems"
            )
            self.scan_coordinate_system_button.setToolTip(
                "Runs the slower DPF coordinate-system ID scan. Normal RST loading "
                "uses metadata only."
            )
            self.run_button = QtWidgets.QPushButton("Run Extraction")
            self.load_button = QtWidgets.QPushButton("Load Config")
            self.save_button = QtWidgets.QPushButton("Save Config")
            self.load_modal_rst_from_config_checkbox = ThemedCheckBox(
                "Load RST path"
            )
            self.load_modal_rst_from_config_checkbox.setObjectName(
                "loadModalRstFromConfigCheckbox"
            )
            self.load_modal_rst_from_config_checkbox.setChecked(True)
            self.load_modal_rst_from_config_checkbox.setToolTip(
                "Turn off to keep the current RST field when loading a config."
            )
            self.open_folder_button = QtWidgets.QPushButton("Open Output Folder")
            self.rst_unit_label = QtWidgets.QLabel(
                rst_mesh_unit_indicator_text(None, state="not_loaded")
            )
            self.rst_unit_label.setObjectName("rstMeshUnitLabel")
            self.rst_unit_label.setToolTip(rst_mesh_unit_indicator_tooltip(None))
            self.status_label = QtWidgets.QLabel("Ready")
            self.log = QtWidgets.QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setMinimumHeight(150)
            self.log.setMaximumBlockCount(20000)
            self.log.setLineWrapMode(
                QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap
            )
            self.log.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn
            )
            self.log.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            self.clear_log_button = QtWidgets.QPushButton("Clear Log")
            self.visualization_update_button = QtWidgets.QPushButton("Update Visualization")
            self.visualization_update_button.setObjectName("visualizationUpdateButton")
            self.visualization_update_button.setProperty("visualizationStale", "true")
            self.visualization_result_combo = ChevronComboBox()
            self.visualization_time_combo = ChevronComboBox()
            self.visualization_time_combo.setMinimumWidth(150)
            self.visualization_status_label = QtWidgets.QLabel(
                "Visualization needs update"
            )
            self.visualization_status_label.setWordWrap(False)
            self.visualization_status_label.setMinimumWidth(220)
            self.visualization_status_label.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            self.visualization_status_label.setAlignment(
                (
                    QtCore.Qt.AlignmentFlag.AlignVCenter
                    | QtCore.Qt.AlignmentFlag.AlignLeft
                )
            )
            self._animation_control_icons = {
                name: _animation_control_icon(name)
                for name in ANIMATION_ICON_FILENAMES
            }
            self.animation_previous_button = QtWidgets.QPushButton()
            self.animation_previous_button.setObjectName("animationPreviousButton")
            self.animation_previous_button.setIcon(
                self._animation_control_icons["previous"]
            )
            self.animation_previous_button.setAccessibleName(
                "Previous solved frame"
            )
            self.animation_previous_button.setToolTip(
                "Show the previous exact solved result set and pause playback."
            )
            self.animation_play_button = QtWidgets.QPushButton()
            self.animation_play_button.setObjectName("animationPlayButton")
            self.animation_play_button.setToolTip(
                "Play or pause the selected Static Structural Range or All sequence. "
                "Displacement frames load in the background."
            )
            self.animation_next_button = QtWidgets.QPushButton()
            self.animation_next_button.setObjectName("animationNextButton")
            self.animation_next_button.setIcon(
                self._animation_control_icons["next"]
            )
            self.animation_next_button.setAccessibleName("Next solved frame")
            self.animation_next_button.setToolTip(
                "Show the next exact solved result set and pause playback."
            )
            self.animation_stop_button = QtWidgets.QPushButton()
            self.animation_stop_button.setObjectName("animationStopButton")
            self.animation_stop_button.setIcon(
                self._animation_control_icons["stop"]
            )
            self.animation_stop_button.setAccessibleName("Stop animation")
            self.animation_stop_button.setToolTip(
                "Stop playback and return the preview to the first exact solved frame."
            )
            for animation_button in (
                self.animation_previous_button,
                self.animation_play_button,
                self.animation_next_button,
                self.animation_stop_button,
            ):
                animation_button.setProperty("animationControl", True)
                animation_button.setFixedSize(34, 32)
                animation_button.setIconSize(QtCore.QSize(20, 20))
            self._set_animation_play_control_state("play")
            self.animation_timeline_slider = QtWidgets.QSlider(
                QtCore.Qt.Orientation.Horizontal
            )
            self.animation_timeline_slider.setObjectName("animationTimelineSlider")
            self.animation_timeline_slider.setRange(0, 1000)
            self.animation_timeline_slider.setValue(0)
            self.animation_timeline_slider.setTracking(True)
            self.animation_timeline_slider.setToolTip(
                "Scrubbing pauses playback and snaps to an exact solved result set."
            )
            self.animation_frame_label = QtWidgets.QLabel(
                "Load RST metadata to preview solved deformation"
            )
            self.animation_frame_label.setObjectName("animationFrameLabel")
            self.animation_frame_label.setMinimumWidth(230)
            self.animation_frame_label.setWordWrap(False)
            self.animation_mode_combo = ChevronComboBox()
            self.animation_mode_combo.setObjectName("animationModeCombo")
            self.animation_mode_combo.addItem("Smooth", "smooth")
            self.animation_mode_combo.addItem("Exact", "exact")
            self.animation_mode_combo.setToolTip(
                "Smooth visually interpolates between solved frames. Exact displays "
                "only solved result sets. Extraction evidence always uses solved mesh data."
            )
            self.animation_cycle_combo = ChevronComboBox()
            self.animation_cycle_combo.setObjectName("animationCycleCombo")
            self.animation_cycle_combo.addItem("Once", "once")
            self.animation_cycle_combo.addItem("Loop", "loop")
            self.animation_cycle_combo.addItem("Ping-pong", "ping-pong")
            self.animation_cycle_combo.setCurrentIndex(1)
            self.animation_cycle_combo.setToolTip(
                "Once stops at the end, Loop repeats from the beginning, and Ping-pong "
                "reverses direction at each end."
            )
            self.animation_speed_combo = ChevronComboBox()
            self.animation_speed_combo.setObjectName("animationSpeedCombo")
            for speed in (0.25, 0.5, 1.0, 2.0, 4.0):
                self.animation_speed_combo.addItem(f"{speed:g}x", speed)
            self.animation_speed_combo.setCurrentIndex(2)
            self.animation_speed_combo.setToolTip(
                "Preview playback rate only; solved times and extraction results are unchanged."
            )
            self.animation_deformation_spin = QtWidgets.QDoubleSpinBox()
            self.animation_deformation_spin.setObjectName(
                "animationDeformationScaleSpin"
            )
            self.animation_deformation_spin.setRange(0.0, 10000.0)
            self.animation_deformation_spin.setDecimals(2)
            self.animation_deformation_spin.setValue(1.0)
            self.animation_deformation_spin.setSuffix("x")
            self.animation_deformation_spin.setToolTip(
                "Visualization only. Extraction evidence always uses the actual 1x deformation."
            )
            self.animation_deformation_label = QtWidgets.QLabel(
                "Deformation (visual only)"
            )
            self.animation_deformation_label.setObjectName(
                "animationDeformationLabel"
            )
            self.animation_timer = QtCore.QTimer(self)
            self.animation_timer.setInterval(33)
            try:
                self.animation_timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
            except Exception:
                pass
            self.animation_elapsed_timer = QtCore.QElapsedTimer()
            self.main_panel_collapse_button = CollapseHandle("", "left")
            self.main_panel_collapse_button.setObjectName("mainPanelCollapseHandle")
            self.main_panel_collapse_button.setAccessibleName("Hide input panel")
            self.main_panel_collapse_button.setToolTip(
                "Hide the input panel to maximize the 3D view. Use the vertical Inputs "
                "tab at the left edge to restore it."
            )
            self.main_panel_expand_button = CollapseHandle(
                "Inputs",
                "right",
                vertical=True,
            )
            self.main_panel_expand_button.setObjectName("mainPanelExpandHandle")
            self.main_panel_expand_button.setToolTip("Restore the input panel")
            self.visualization_collapse_button = CollapseHandle("", "right")
            self.visualization_collapse_button.setObjectName("visualizationCollapseHandle")
            self.visualization_collapse_button.setToolTip(
                "Collapse visualization to the right side"
            )
            self.visualization_expand_button = CollapseHandle(
                "Visualization",
                "left",
                vertical=True,
            )
            self.visualization_expand_button.setObjectName("visualizationExpandHandle")
            self.visualization_expand_button.setToolTip("Expand visualization")

            self._populate_combo(self.normal_combo, NORMAL_AXIS_CHOICES)
            self._populate_combo(self.analysis_mode_combo, ANALYSIS_MODE_CHOICES)
            self._populate_combo(self.static_set_scope_combo, STATIC_SET_SCOPE_CHOICES)
            self._populate_combo(
                self.reference_frame_motion_combo,
                REFERENCE_FRAME_MOTION_CHOICES,
            )
            self.reference_frame_motion_combo.setItemData(
                0,
                "Moving-section mode: transports the origin, orientation, plane, and "
                "cut membership with the attached deformed geometry. Use this when the "
                "section must remain attached to a moving or rotating part; do not expect "
                "it to match a fixed Mechanical Construction Surface.",
                QtCore.Qt.ItemDataRole.ToolTipRole,
            )
            self.reference_frame_motion_combo.setItemData(
                1,
                "Mechanical-parity mode: keeps the section plane and cut membership on "
                "the initial/reference mesh while showing displaced nodes and retaining "
                "large-deflection result evidence.",
                QtCore.Qt.ItemDataRole.ToolTipRole,
            )
            self._populate_combo(self.side_combo, EXTRACTION_SIDE_CHOICES)
            self._populate_combo(self.moment_combo, MOMENT_REFERENCE_CHOICES)
            self._populate_combo(self.force_type_combo, DPF_FORCE_TYPE_CHOICES)
            self._populate_combo(self.visualization_result_combo, VISUALIZATION_RESULT_CHOICES)
            self.normal_combo.setToolTip(NORMAL_AXIS_TOOLTIP)
            self.side_combo.setToolTip(EXTRACTION_SIDE_TOOLTIP)
            self.moment_combo.setToolTip(MOMENT_REFERENCE_TOOLTIP)
            self.tolerance_edit.setToolTip(SIDE_TOLERANCE_TOOLTIP)
            self.force_type_combo.setToolTip(DPF_FORCE_TYPE_TOOLTIP)
            self.visualization_result_combo.setToolTip(VISUALIZATION_RESULT_TOOLTIP)
            tooltip_role = (
                QtCore.Qt.ItemDataRole.ToolTipRole
            )
            self.moment_combo.setItemData(
                0,
                "Compute moments about the selected coordinate-system origin. "
                "This matches Mechanical Moment Reaction when Summation is "
                "OrientationSystem; it is not just a component rotation.",
                tooltip_role,
            )
            self.moment_combo.setItemData(
                1,
                "Compute moments about the Mechanical-style mesh centroid of the "
                "construction-surface probe nodes.",
                tooltip_role,
            )
            self.moment_combo.setItemData(
                2,
                "Compute moments about the centroid of the nodes kept by the "
                "selected extraction side.",
                tooltip_role,
            )
            self.visualization_result_combo.setItemData(
                0,
                "Show force result vectors at the selected time point.",
                tooltip_role,
            )
            self.visualization_result_combo.setItemData(
                1,
                "Show the total moment vector computed about the selected Moment "
                "reference point.",
                tooltip_role,
            )
            self._configure_searchable_combo(self.element_combo)
            self._configure_searchable_combo(self.coordinate_system_combo)
            self._set_visualization_result_controls_enabled(False)

            self._build_layout()
            self._build_visualization_dock()
            self._build_menu_bar()
            self._apply_style()
            self.modal_row.path_changed.connect(self.on_modal_rst_path_changed)
            self.external_selection_row.path_changed.connect(
                self.on_external_selection_path_changed
            )
            self.external_selection_row.edit.editingFinished.connect(
                lambda: self.refresh_named_selection_options(show_errors=True)
            )
            self.mcf_row.edit.textChanged.connect(
                lambda _text: self.refresh_result_overlay_render()
            )
            self.modal_row.edit.editingFinished.connect(
                lambda: self.refresh_modal_rst_metadata(show_errors=True)
            )
            self.set_config(cfg)
            self.analysis_mode_combo.currentIndexChanged.connect(
                lambda _index: self.on_analysis_mode_changed()
            )
            self.static_set_scope_combo.currentIndexChanged.connect(
                lambda _index: self.on_static_set_scope_changed()
            )
            self.result_set_combo.currentIndexChanged.connect(self.on_result_set_changed)
            for spin in (
                self.result_set_range_start_spin,
                self.result_set_range_end_spin,
                self.result_set_range_stride_spin,
            ):
                spin.valueChanged.connect(lambda _value: self.mark_visualization_stale())
            self.reference_frame_motion_combo.currentIndexChanged.connect(
                lambda _index: self.on_reference_frame_motion_changed()
            )
            self.reference_frame_attachment_combo.currentTextChanged.connect(
                lambda _text: self.on_reference_frame_attachment_changed()
            )
            self.reference_frame_fit_warning_spin.valueChanged.connect(
                lambda _value: self.mark_visualization_stale()
            )
            self.coordinate_system_combo.activated.connect(self.apply_coordinate_system_index)
            self.scan_coordinate_system_button.clicked.connect(
                self.scan_dpf_coordinate_systems
            )
            self.run_button.clicked.connect(self.run_extraction)
            self.force_type_combo.currentIndexChanged.connect(
                lambda _index: self.refresh_result_overlay_render()
            )
            self.load_button.clicked.connect(self.load_config)
            self.save_button.clicked.connect(self.save_config)
            self.open_folder_button.clicked.connect(self.open_output_folder)
            self.clear_log_button.clicked.connect(self.log.clear)
            self.visualization_update_button.clicked.connect(self.update_visualization)
            self.visualization_result_combo.currentIndexChanged.connect(
                lambda _index: self.refresh_result_overlay_render()
            )
            self.visualization_time_combo.currentIndexChanged.connect(
                self.on_visualization_time_changed
            )
            self.animation_previous_button.clicked.connect(
                lambda _checked=False: self.step_static_animation(-1)
            )
            self.animation_play_button.clicked.connect(
                lambda _checked=False: self.toggle_static_animation_playback()
            )
            self.animation_next_button.clicked.connect(
                lambda _checked=False: self.step_static_animation(1)
            )
            self.animation_stop_button.clicked.connect(
                lambda _checked=False: self.stop_static_animation()
            )
            self.animation_timeline_slider.sliderPressed.connect(
                self.on_animation_slider_pressed
            )
            self.animation_timeline_slider.sliderMoved.connect(
                self.on_animation_slider_moved
            )
            self.animation_timeline_slider.sliderReleased.connect(
                self.on_animation_slider_released
            )
            self.animation_mode_combo.currentIndexChanged.connect(
                lambda _index: self.on_animation_display_option_changed()
            )
            self.animation_deformation_spin.valueChanged.connect(
                lambda _value: self.on_animation_display_option_changed()
            )
            self.animation_timer.timeout.connect(self.advance_static_animation)
            self.main_panel_collapse_button.clicked.connect(
                lambda: self.set_main_panel_collapsed(True)
            )
            self.main_panel_expand_button.clicked.connect(
                lambda: self.set_main_panel_collapsed(False)
            )
            self.visualization_collapse_button.clicked.connect(
                lambda: self.set_visualization_collapsed(True)
            )
            self.visualization_expand_button.clicked.connect(
                lambda: self.set_visualization_collapsed(False)
            )
            self.result_history_widget.frame_changed.connect(
                self.refresh_result_history_plot
            )
            self.result_history_widget.moment_unit_changed.connect(
                self.refresh_result_history_plot
            )
            self.result_history_widget.time_selected.connect(
                self.go_to_result_history_time
            )
            self.result_history_widget.collapsed_changed.connect(
                self.on_result_history_collapsed_changed
            )
            self.diagnostics_log_group.collapsed_changed.connect(
                self.on_run_log_collapsed_changed
            )
            self.result_history_widget.dock_requested.connect(
                self.toggle_result_history_dock
            )
            self.visualization_widget.nodal_force_export_requested.connect(
                self.export_current_nodal_forces
            )
            self.visualization_widget.nodal_force_excel_export_requested.connect(
                self.export_current_nodal_forces_excel
            )
            self._connect_visualization_stale_signals()
            self._refresh_animation_availability()

        def _build_layout(self) -> None:
            expanded = QtWidgets.QWidget()
            expanded.setObjectName("mainPanelExpandedContent")
            root = QtWidgets.QVBoxLayout(expanded)
            root.setContentsMargins(18, 16, 18, 16)
            root.setSpacing(12)

            self.input_files_group = CollapsibleGroup("Files")
            self.input_files_group.header_widget.layout().addWidget(
                self.main_panel_collapse_button
            )
            files_form = self._new_form_layout(self.input_files_group.body_widget)
            self._files_form = files_form
            files_form.addRow("Analysis mode", self.analysis_mode_combo)
            files_form.addRow("Result RST", self.modal_row)
            files_form.addRow("RST units", self.rst_unit_label)
            files_form.addRow("Static set scope", self.static_set_scope_combo)
            files_form.addRow("Static result set", self.result_set_combo)
            files_form.addRow("Start set", self.result_set_range_start_spin)
            files_form.addRow("End set", self.result_set_range_end_spin)
            files_form.addRow("Stride", self.result_set_range_stride_spin)
            files_form.addRow("Selected sets", self.all_result_sets_label)
            files_form.addRow("Transient MCF", self.mcf_row)
            files_form.addRow("Output CSV", self.out_row)
            files_form.addRow("External selection (optional)", self.external_selection_row)
            files_form.addRow("Named selection / CDB component", self.element_combo)

            self.section_parameters_group = CollapsibleGroup("Reference Frame")
            self.section_parameters_group.set_expanded(False)
            reference_frame_form = self._new_form_layout(
                self.section_parameters_group.body_widget
            )
            self._reference_frame_form = reference_frame_form
            reference_frame_form.addRow(
                "Reference frame motion",
                self.reference_frame_motion_combo,
            )
            reference_frame_form.addRow(
                "Frame attachment",
                self.reference_frame_tracking_status_label,
            )
            coordinate_system_label = QtWidgets.QLabel("Coordinate system")
            coordinate_system_label.setToolTip(COORDINATE_SYSTEM_TOOLTIP)
            reference_frame_form.addRow(
                coordinate_system_label,
                self._coordinate_system_widget(),
            )
            origin_label = QtWidgets.QLabel("Origin [mm]")
            origin_label.setToolTip(ORIGIN_TOOLTIP)
            self.origin_vector_editor = self._vector3_editor(
                self.origin_edits,
                ORIGIN_TOOLTIP,
            )
            reference_frame_form.addRow(
                origin_label,
                self.origin_vector_editor,
            )

            self.orientation_group = CollapsibleGroup("Orientation")
            self.orientation_group.set_expanded(False)
            orientation_layout = QtWidgets.QVBoxLayout(
                self.orientation_group.body_widget
            )
            orientation_layout.setContentsMargins(2, 2, 2, 2)
            self.orientation_matrix = self._orientation_matrix_widget()
            orientation_layout.addWidget(self.orientation_matrix)

            self.section_cut_group = CollapsibleGroup("Section Cut")
            self.section_cut_group.set_expanded(False)
            section_cut_form = self._new_form_layout(
                self.section_cut_group.body_widget
            )
            self._section_cut_form = section_cut_form
            normal_label = QtWidgets.QLabel("Normal axis")
            normal_label.setToolTip(NORMAL_AXIS_TOOLTIP)
            section_cut_form.addRow(normal_label, self.normal_combo)
            side_label = QtWidgets.QLabel("Extraction side")
            side_label.setToolTip(EXTRACTION_SIDE_TOOLTIP)
            section_cut_form.addRow(side_label, self.side_combo)
            moment_reference_label = QtWidgets.QLabel("Moment reference")
            moment_reference_label.setToolTip(MOMENT_REFERENCE_TOOLTIP)
            section_cut_form.addRow(moment_reference_label, self.moment_combo)
            tolerance_label = QtWidgets.QLabel("Side tolerance")
            tolerance_label.setToolTip(SIDE_TOLERANCE_TOOLTIP)
            section_cut_form.addRow(tolerance_label, self.tolerance_edit)

            self.reference_frame_advanced_group = CollapsibleGroup(
                "Advanced Frame Attachment",
            )
            self.reference_frame_advanced_group.set_expanded(False)
            advanced_frame_form = self._new_form_layout(
                self.reference_frame_advanced_group.body_widget
            )
            advanced_frame_form.addRow(
                "Selection override",
                self.reference_frame_attachment_combo,
            )
            advanced_frame_form.addRow(
                "Fit warning limit",
                self.reference_frame_fit_warning_spin,
            )

            self.modal_options_group = CollapsibleGroup("Modal Options")
            self.modal_options_group.set_expanded(False)
            modal_options_form = self._new_form_layout(
                self.modal_options_group.body_widget
            )
            self._modal_options_form = modal_options_form
            force_type_label = QtWidgets.QLabel("DPF force type")
            force_type_label.setToolTip(DPF_FORCE_TYPE_TOOLTIP)
            modal_options_form.addRow(force_type_label, self.force_type_combo)
            modal_options_form.addRow("Skip first modes", self.skip_first_modes_spin)
            modal_options_form.addRow("DPF modal batch size", self.modal_batch_spin)

            self.input_inspector_content = QtWidgets.QWidget()
            self.input_inspector_content.setObjectName("inputInspectorContent")
            inspector_layout = QtWidgets.QVBoxLayout(self.input_inspector_content)
            inspector_layout.setContentsMargins(0, 0, 0, 0)
            inspector_layout.setSpacing(10)
            inspector_layout.setSizeConstraint(
                QtWidgets.QLayout.SizeConstraint.SetMinAndMaxSize
            )
            inspector_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
            inspector_layout.addWidget(self.input_files_group)
            inspector_layout.addWidget(self.section_parameters_group)
            inspector_layout.addWidget(self.orientation_group)
            inspector_layout.addWidget(self.section_cut_group)
            inspector_layout.addWidget(self.reference_frame_advanced_group)
            inspector_layout.addWidget(self.modal_options_group)

            self.input_inspector_scroll_area = QtWidgets.QScrollArea()
            self.input_inspector_scroll_area.setObjectName("inputInspectorScrollArea")
            self.input_inspector_scroll_area.setWidgetResizable(True)
            self.input_inspector_scroll_area.setFrameShape(
                QtWidgets.QFrame.Shape.NoFrame
            )
            self.input_inspector_scroll_area.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self.input_inspector_scroll_area.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            self.input_inspector_scroll_area.setWidget(self.input_inspector_content)

            controls = QtWidgets.QHBoxLayout()
            controls.setSpacing(8)
            controls.addWidget(self.load_button)
            controls.addWidget(self.load_modal_rst_from_config_checkbox)
            controls.addWidget(self.save_button)
            controls.addStretch(1)
            controls.addWidget(self.open_folder_button)
            controls.addWidget(self.run_button)

            self.input_action_footer = QtWidgets.QWidget()
            self.input_action_footer.setObjectName("inputActionFooter")
            footer_layout = QtWidgets.QVBoxLayout(self.input_action_footer)
            footer_layout.setContentsMargins(0, 8, 0, 0)
            footer_layout.setSpacing(6)
            footer_layout.addLayout(controls)
            self.status_label.setWordWrap(True)
            footer_layout.addWidget(self.status_label)

            self.diagnostics_log_group = CollapsibleGroup("Run Log")
            self.diagnostics_log_group.set_expanded(False)
            log_layout = QtWidgets.QVBoxLayout(
                self.diagnostics_log_group.body_widget
            )
            log_layout.setContentsMargins(2, 2, 2, 2)
            log_controls = QtWidgets.QHBoxLayout()
            log_controls.addStretch(1)
            log_controls.addWidget(self.clear_log_button)
            log_layout.addLayout(log_controls)
            log_layout.addWidget(self.log)

            upper_widget = QtWidgets.QWidget()
            upper_layout = QtWidgets.QVBoxLayout(upper_widget)
            upper_layout.setContentsMargins(0, 0, 0, 0)
            upper_layout.setSpacing(0)
            upper_layout.addWidget(self.input_inspector_scroll_area, 1)
            upper_layout.addWidget(self.input_action_footer, 0)
            self.input_panel_upper_widget = upper_widget

            self.run_log_splitter = QtWidgets.QSplitter(
                QtCore.Qt.Orientation.Vertical
            )
            self.run_log_splitter.setObjectName("runLogVerticalSplitter")
            self.run_log_splitter.setChildrenCollapsible(False)
            self.run_log_splitter.setHandleWidth(8)
            self.run_log_splitter.addWidget(upper_widget)
            self.run_log_splitter.addWidget(self.diagnostics_log_group)
            self.run_log_splitter.setStretchFactor(0, 0)
            self.run_log_splitter.setStretchFactor(1, 1)
            self.run_log_splitter.setSizes([620, 180])

            root.addWidget(self.run_log_splitter, 1)
            collapsed = QtWidgets.QWidget()
            collapsed.setObjectName("mainPanelCollapsedContent")
            collapsed.setFixedWidth(VISUALIZATION_DOCK_COLLAPSED_WIDTH)
            collapsed_layout = QtWidgets.QVBoxLayout(collapsed)
            collapsed_layout.setContentsMargins(6, 12, 6, 8)
            collapsed_layout.addWidget(
                self.main_panel_expand_button,
                0,
                (
                    QtCore.Qt.AlignmentFlag.AlignHCenter
                ),
            )
            collapsed_layout.addStretch(1)

            self.main_panel_expanded_widget = expanded
            self.main_panel_collapsed_widget = collapsed
            self.main_panel_stack = QtWidgets.QStackedWidget()
            self.main_panel_stack.setObjectName("mainPanelStack")
            self.main_panel_stack.addWidget(self.main_panel_expanded_widget)
            self.main_panel_stack.addWidget(self.main_panel_collapsed_widget)
            self.setCentralWidget(self.main_panel_stack)

        def _build_visualization_dock(self) -> None:
            content = QtWidgets.QWidget()
            content.setObjectName("visualizationDockContent")
            content.setMinimumWidth(VISUALIZATION_DOCK_MIN_WIDTH)
            layout = QtWidgets.QVBoxLayout(content)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)
            header_controls = QtWidgets.QHBoxLayout()
            header_controls.setSpacing(10)
            header_controls.addWidget(self.visualization_update_button)
            header_controls.addSpacing(4)
            result_label = QtWidgets.QLabel("Result")
            result_label.setToolTip(VISUALIZATION_RESULT_TOOLTIP)
            header_controls.addWidget(result_label)
            header_controls.addWidget(self.visualization_result_combo)
            header_controls.addWidget(QtWidgets.QLabel("Time"))
            header_controls.addWidget(self.visualization_time_combo)
            header_controls.addWidget(self.visualization_status_label, 1)
            header_controls.addSpacing(4)
            header_controls.addWidget(self.visualization_collapse_button)
            layout.addLayout(header_controls)

            self.animation_group = CollapsibleGroup("Animation")
            self.animation_group.setObjectName("staticAnimationGroup")
            self.animation_group.setToolTip(
                "Preview solved Static Structural Range/All deformation before or after extraction."
            )
            animation_layout = QtWidgets.QVBoxLayout(
                self.animation_group.body_widget
            )
            animation_layout.setContentsMargins(2, 2, 2, 2)
            animation_layout.setSpacing(4)
            playback_row = QtWidgets.QHBoxLayout()
            playback_row.setSpacing(5)
            playback_row.addWidget(self.animation_previous_button)
            playback_row.addWidget(self.animation_play_button)
            playback_row.addWidget(self.animation_next_button)
            playback_row.addWidget(self.animation_stop_button)
            playback_row.addWidget(self.animation_timeline_slider, 1)
            playback_row.addWidget(self.animation_frame_label)
            animation_layout.addLayout(playback_row)
            options_row = QtWidgets.QHBoxLayout()
            options_row.setSpacing(6)
            options_row.addWidget(QtWidgets.QLabel("Playback"))
            options_row.addWidget(self.animation_mode_combo)
            options_row.addWidget(QtWidgets.QLabel("Cycle"))
            options_row.addWidget(self.animation_cycle_combo)
            options_row.addWidget(QtWidgets.QLabel("Speed"))
            options_row.addWidget(self.animation_speed_combo)
            options_row.addStretch(1)
            options_row.addWidget(self.animation_deformation_label)
            options_row.addWidget(self.animation_deformation_spin)
            animation_layout.addLayout(options_row)
            layout.addWidget(self.animation_group)

            self.visualization_widget = SectionVisualizationWidget(content)
            self.visualization_widget.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
            self.result_history_embedded_container = QtWidgets.QWidget(content)
            self.result_history_embedded_container.setObjectName(
                "resultHistoryEmbeddedContainer"
            )
            self.result_history_embedded_layout = QtWidgets.QVBoxLayout(
                self.result_history_embedded_container
            )
            self.result_history_embedded_layout.setContentsMargins(0, 0, 0, 0)
            self.result_history_embedded_layout.setSpacing(0)
            self.result_history_widget = ResultHistoryPlotWidget(
                self.result_history_embedded_container
            )
            self.result_history_embedded_layout.addWidget(self.result_history_widget)
            self.visualization_splitter = QtWidgets.QSplitter(
                self._vertical_orientation()
            )
            self.visualization_splitter.setObjectName("visualizationVerticalSplitter")
            self.visualization_splitter.setHandleWidth(
                VISUALIZATION_HISTORY_SPLITTER_HANDLE_WIDTH
            )
            self.visualization_splitter.setOpaqueResize(True)
            self.visualization_splitter.setChildrenCollapsible(False)
            self.visualization_splitter.addWidget(self.visualization_widget)
            self.visualization_splitter.addWidget(self.result_history_embedded_container)
            self.visualization_splitter.setStretchFactor(0, 3)
            self.visualization_splitter.setStretchFactor(1, 1)
            splitter_handle = self.visualization_splitter.handle(1)
            if splitter_handle is not None:
                splitter_handle.setToolTip(
                    "Drag to resize the 3D view and result history plot"
                )
            self.visualization_splitter.setSizes(
                [500, VISUALIZATION_HISTORY_DEFAULT_HEIGHT]
            )
            self.visualization_splitter.splitterMoved.connect(
                lambda _pos, _index: self.remember_result_history_splitter_size()
            )
            layout.addWidget(self.visualization_splitter, 1)
            self.visualization_expanded_widget = content

            collapsed = QtWidgets.QWidget()
            collapsed.setObjectName("visualizationDockCollapsedContent")
            collapsed.setFixedWidth(VISUALIZATION_DOCK_COLLAPSED_WIDTH)
            collapsed_layout = QtWidgets.QVBoxLayout(collapsed)
            collapsed_layout.setContentsMargins(6, 12, 6, 8)
            collapsed_layout.addWidget(
                self.visualization_expand_button,
                0,
                (
                    QtCore.Qt.AlignmentFlag.AlignHCenter
                ),
            )
            collapsed_layout.addStretch(1)
            self.visualization_collapsed_widget = collapsed

            self.visualization_stack = QtWidgets.QStackedWidget()
            self.visualization_stack.addWidget(self.visualization_expanded_widget)
            self.visualization_stack.addWidget(self.visualization_collapsed_widget)

            self.visualization_dock = QtWidgets.QDockWidget(
                "Section Visualization",
                self,
            )
            self.visualization_dock.setObjectName("sectionVisualizationDock")
            self.visualization_dock_title_bar = DockTitleBar(
                self.visualization_dock,
                self.visualization_dock,
            )
            self.visualization_dock.setTitleBarWidget(
                self.visualization_dock_title_bar
            )
            self.visualization_dock.setWidget(self.visualization_stack)
            self.visualization_dock.setFeatures(self._dock_features())
            self.addDockWidget(self._right_dock_area(), self.visualization_dock)
            self._apply_visualization_dock_width(VISUALIZATION_DOCK_DEFAULT_WIDTH)

            self.result_history_dock = QtWidgets.QDockWidget("Result History", self)
            self.result_history_dock.setObjectName("resultHistoryDock")
            self.result_history_dock_container = QtWidgets.QWidget(
                self.result_history_dock
            )
            self.result_history_dock_container.setObjectName("resultHistoryDockContent")
            self.result_history_dock_layout = QtWidgets.QVBoxLayout(
                self.result_history_dock_container
            )
            self.result_history_dock_layout.setContentsMargins(8, 8, 8, 8)
            self.result_history_dock_layout.setSpacing(0)
            self.result_history_dock_title_bar = DockTitleBar(
                self.result_history_dock,
                self.result_history_dock,
            )
            self.result_history_dock.setTitleBarWidget(
                self.result_history_dock_title_bar
            )
            self.result_history_dock.setWidget(self.result_history_dock_container)
            self.result_history_dock.setFeatures(self._dock_features())
            self.result_history_dock.visibilityChanged.connect(
                self.on_result_history_dock_visibility_changed
            )
            self.addDockWidget(self._bottom_dock_area(), self.result_history_dock)
            self.result_history_dock.hide()

        def _build_menu_bar(self) -> None:
            action_class = QtGui.QAction
            menu_bar = self.menuBar()

            file_menu = menu_bar.addMenu("File")
            self.load_config_action = action_class("Load Config", self)
            self.load_config_action.triggered.connect(
                lambda _checked=False: self.load_config()
            )
            file_menu.addAction(self.load_config_action)
            self.save_config_action = action_class("Save Config", self)
            self.save_config_action.triggered.connect(
                lambda _checked=False: self.save_config()
            )
            file_menu.addAction(self.save_config_action)

            view_menu = menu_bar.addMenu("View")
            self.view_3d_panel_action = action_class("3D Panel", self)
            self.view_3d_panel_action.setCheckable(True)
            self.view_3d_panel_action.toggled.connect(self.set_3d_panel_visible)
            view_menu.addAction(self.view_3d_panel_action)

            self.view_plot_action = action_class("Plot", self)
            self.view_plot_action.setCheckable(True)
            self.view_plot_action.toggled.connect(self.set_result_history_plot_visible)
            view_menu.addAction(self.view_plot_action)

            self.visualization_dock.visibilityChanged.connect(
                lambda _visible: self._sync_view_actions()
            )
            self._sync_view_actions()

        def _set_action_checked(self, action: Any, checked: bool) -> None:
            if action.isChecked() == bool(checked):
                return
            was_blocked = action.blockSignals(True)
            try:
                action.setChecked(bool(checked))
            finally:
                action.blockSignals(was_blocked)

        def _widget_visible_for_menu(self, widget: Any) -> bool:
            if self.isVisible():
                return bool(widget.isVisible())
            return not bool(widget.isHidden())

        def _sync_view_actions(self) -> None:
            if hasattr(self, "view_3d_panel_action"):
                self._set_action_checked(
                    self.view_3d_panel_action,
                    self._widget_visible_for_menu(self.visualization_dock),
                )
            if hasattr(self, "view_plot_action"):
                plot_visible = self._result_history_plot_visible
                if self._result_history_detached:
                    plot_visible = plot_visible and self._widget_visible_for_menu(
                        self.result_history_dock
                    )
                else:
                    plot_visible = (
                        plot_visible
                        and self._widget_visible_for_menu(
                            self.result_history_embedded_container
                        )
                    )
                self._set_action_checked(self.view_plot_action, plot_visible)

        def set_3d_panel_visible(self, visible: bool) -> None:
            if visible:
                self.visualization_dock.show()
                if self._visualization_collapsed:
                    self.set_visualization_collapsed(False)
            else:
                self.visualization_dock.hide()
            self._sync_view_actions()

        def set_result_history_plot_visible(self, visible: bool) -> None:
            self._result_history_plot_visible = bool(visible)
            if visible:
                self.result_history_widget.show()
                if self._result_history_detached:
                    self.result_history_dock.show()
                    self.result_history_dock.raise_()
                    self.result_history_dock.activateWindow()
                else:
                    self.visualization_dock.show()
                    self.result_history_embedded_container.show()
                    if self.result_history_widget.is_collapsed():
                        self.result_history_widget.set_expanded(True)
                    else:
                        self.on_result_history_collapsed_changed(False)
            else:
                self.remember_result_history_splitter_size()
                if self._result_history_detached:
                    if self.result_history_dock.isVisible():
                        self._result_history_floating_geometry = (
                            self.result_history_dock.geometry()
                        )
                    self._result_history_reembedding = True
                    try:
                        self.result_history_dock.hide()
                    finally:
                        self._result_history_reembedding = False
                else:
                    self.result_history_embedded_container.hide()
            self._sync_view_actions()

        def _right_dock_area(self) -> Any:
            return (
                QtCore.Qt.DockWidgetArea.RightDockWidgetArea
            )

        def _bottom_dock_area(self) -> Any:
            return (
                QtCore.Qt.DockWidgetArea.BottomDockWidgetArea
            )

        def _dock_features(self) -> Any:
            features = QtWidgets.QDockWidget.DockWidgetFeature
            return (
                features.DockWidgetMovable
                | features.DockWidgetFloatable
                | features.DockWidgetClosable
            )

        def _horizontal_orientation(self) -> Any:
            return (
                QtCore.Qt.Orientation.Horizontal
            )

        def _vertical_orientation(self) -> Any:
            return (
                QtCore.Qt.Orientation.Vertical
            )

        def _apply_visualization_dock_width(self, width: int) -> None:
            self.resizeDocks(
                [self.visualization_dock],
                [int(width)],
                self._horizontal_orientation(),
            )

        def set_main_panel_collapsed(self, collapsed: bool) -> None:
            collapsed = bool(collapsed)
            if collapsed == self._main_panel_collapsed:
                return
            if collapsed:
                self._main_panel_expanded_width = max(
                    self.main_panel_stack.width(),
                    VISUALIZATION_DOCK_MIN_WIDTH,
                )
                self._main_panel_collapsed = True
                self.main_panel_stack.setCurrentWidget(self.main_panel_collapsed_widget)
                self.main_panel_stack.setMinimumWidth(VISUALIZATION_DOCK_COLLAPSED_WIDTH)
                self.main_panel_stack.setMaximumWidth(VISUALIZATION_DOCK_COLLAPSED_WIDTH)
                self.main_panel_stack.updateGeometry()
                return

            self._main_panel_collapsed = False
            self.main_panel_stack.setMaximumWidth(16777215)
            self.main_panel_stack.setMinimumWidth(0)
            self.main_panel_stack.setCurrentWidget(self.main_panel_expanded_widget)
            self.main_panel_stack.updateGeometry()

        def toggle_result_history_dock(self) -> None:
            if self._result_history_detached:
                self.embed_result_history_plot()
            else:
                self.detach_result_history_plot()

        def _screen_available_geometry_for_point(self, point: Any) -> Any:
            screen = None
            screen_at = getattr(QtGui.QGuiApplication, "screenAt", None)
            if callable(screen_at):
                try:
                    screen = screen_at(point)
                except TypeError:
                    screen = None
            if screen is None:
                app = QtWidgets.QApplication.instance()
                primary_screen = getattr(app, "primaryScreen", None) if app else None
                if callable(primary_screen):
                    screen = primary_screen()
                if screen is None:
                    screen = QtGui.QGuiApplication.primaryScreen()
            if screen is not None:
                return screen.availableGeometry()
            return QtCore.QRect(0, 0, max(self.width(), 1200), max(self.height(), 800))

        def _clamp_rect_to_screen(self, rect: Any, available: Any) -> Any:
            margin = 24
            clamped = QtCore.QRect(rect)
            max_width = max(available.width() - margin * 2, 320)
            max_height = max(available.height() - margin * 2, 260)
            if clamped.width() > max_width:
                clamped.setWidth(max_width)
            if clamped.height() > max_height:
                clamped.setHeight(max_height)
            if clamped.right() > available.right() - margin:
                clamped.moveRight(available.right() - margin)
            if clamped.bottom() > available.bottom() - margin:
                clamped.moveBottom(available.bottom() - margin)
            if clamped.left() < available.left() + margin:
                clamped.moveLeft(available.left() + margin)
            if clamped.top() < available.top() + margin:
                clamped.moveTop(available.top() + margin)
            return clamped

        def _result_history_floating_rect(self, width: int, height: int) -> Any:
            saved = self._result_history_floating_geometry
            cursor_pos = QtGui.QCursor.pos()
            if saved is not None and saved.isValid():
                available = self._screen_available_geometry_for_point(saved.center())
                return self._clamp_rect_to_screen(saved, available)
            available = self._screen_available_geometry_for_point(cursor_pos)
            anchor = cursor_pos
            if not available.contains(anchor):
                anchor = self.mapToGlobal(self.rect().center())
                available = self._screen_available_geometry_for_point(anchor)
            rect = QtCore.QRect(
                QtCore.QPoint(anchor.x() + 24, anchor.y() + 24),
                QtCore.QSize(int(width), int(height)),
            )
            return self._clamp_rect_to_screen(rect, available)

        def detach_result_history_plot(self) -> None:
            if self._result_history_detached:
                return
            self.remember_result_history_splitter_size()
            self._result_history_plot_visible = True
            self._result_history_reembedding = True
            try:
                dock_width = max(
                    self.visualization_dock.width(),
                    VISUALIZATION_DOCK_DEFAULT_WIDTH,
                )
                dock_height = max(self._result_history_expanded_height + 120, 420)
                floating_rect = self._result_history_floating_rect(
                    dock_width,
                    dock_height,
                )
                self.result_history_embedded_layout.removeWidget(
                    self.result_history_widget
                )
                self.result_history_widget.setParent(self.result_history_dock_container)
                self.result_history_dock_layout.addWidget(self.result_history_widget)
                self.result_history_widget.show()
                self.result_history_embedded_container.hide()
                self._result_history_detached = True
                self.result_history_widget.set_detached(True)
                self.result_history_dock.setFloating(True)
                self.result_history_dock.setGeometry(floating_rect)
                self.result_history_dock.show()
                self.result_history_dock.raise_()
                self.result_history_dock.activateWindow()
            finally:
                self._result_history_reembedding = False
            self._sync_view_actions()

        def embed_result_history_plot(self) -> None:
            if not self._result_history_detached:
                return
            if self.result_history_dock.isVisible():
                self._result_history_floating_geometry = self.result_history_dock.geometry()
                self._result_history_expanded_height = max(
                    self.result_history_dock.height() - 120,
                    VISUALIZATION_HISTORY_MIN_HEIGHT,
                )
            self._result_history_reembedding = True
            try:
                self.result_history_dock_layout.removeWidget(self.result_history_widget)
                self.result_history_widget.setParent(self.result_history_embedded_container)
                self.result_history_embedded_layout.addWidget(self.result_history_widget)
                self.result_history_widget.show()
                self.result_history_embedded_container.setVisible(
                    self._result_history_plot_visible
                )
                self.result_history_dock.hide()
                self._result_history_detached = False
                self.result_history_widget.set_detached(False)
                if self._result_history_plot_visible:
                    total_height = max(sum(self.visualization_splitter.sizes()), 400)
                    history_height = min(
                        max(
                            self._result_history_expanded_height,
                            VISUALIZATION_HISTORY_MIN_HEIGHT,
                        ),
                        max(total_height - 100, VISUALIZATION_HISTORY_MIN_HEIGHT),
                    )
                    self.visualization_splitter.setSizes(
                        [max(total_height - history_height, 100), history_height]
                    )
            finally:
                self._result_history_reembedding = False
            self._sync_view_actions()

        def on_result_history_dock_visibility_changed(self, visible: bool) -> None:
            if visible:
                self._result_history_plot_visible = True
                self._sync_view_actions()
                return
            if (
                not self._result_history_detached
                or self._result_history_reembedding
            ):
                self._sync_view_actions()
                return
            self.embed_result_history_plot()
            self._sync_view_actions()

        def remember_result_history_splitter_size(self) -> None:
            if self._result_history_detached:
                return
            if self.result_history_widget.is_collapsed():
                return
            sizes = self.visualization_splitter.sizes()
            if len(sizes) >= 2 and sizes[1] >= VISUALIZATION_HISTORY_MIN_HEIGHT:
                self._result_history_expanded_height = int(sizes[1])

        def on_result_history_collapsed_changed(self, collapsed: bool) -> None:
            if self._result_history_detached:
                return
            if not self._result_history_plot_visible:
                return
            sizes = self.visualization_splitter.sizes()
            total_height = max(sum(sizes), 400) if sizes else 400
            if collapsed:
                if len(sizes) >= 2 and sizes[1] >= VISUALIZATION_HISTORY_MIN_HEIGHT:
                    self._result_history_expanded_height = int(sizes[1])
                self.visualization_splitter.setSizes(
                    [
                        max(total_height - VISUALIZATION_HISTORY_COLLAPSED_HEIGHT, 100),
                        VISUALIZATION_HISTORY_COLLAPSED_HEIGHT,
                    ]
                )
                return
            history_height = max(
                self._result_history_expanded_height,
                VISUALIZATION_HISTORY_MIN_HEIGHT,
            )
            history_height = min(
                history_height,
                max(total_height - 100, VISUALIZATION_HISTORY_MIN_HEIGHT),
            )
            self.visualization_splitter.setSizes(
                [max(total_height - history_height, 100), history_height]
            )

        def on_run_log_collapsed_changed(self, collapsed: bool) -> None:
            sizes = self.run_log_splitter.sizes()
            if len(sizes) < 2:
                return
            total_height = max(sum(sizes), 240)
            if collapsed:
                compact_height = max(
                    self.diagnostics_log_group.maximumHeight(),
                    self.diagnostics_log_group.sizeHint().height(),
                )
                if sizes[1] > compact_height:
                    self._run_log_expanded_height = int(sizes[1])
                self.run_log_splitter.setSizes(
                    [max(total_height - compact_height, 100), compact_height]
                )
                return
            log_height = max(
                self._run_log_expanded_height,
                self.diagnostics_log_group.minimumSizeHint().height(),
                140,
            )
            log_height = min(log_height, max(total_height - 100, 140))
            self.run_log_splitter.setSizes(
                [max(total_height - log_height, 100), log_height]
            )

        def set_visualization_collapsed(self, collapsed: bool) -> None:
            collapsed = bool(collapsed)
            if collapsed == self._visualization_collapsed:
                return
            if collapsed:
                self._visualization_expanded_width = max(
                    self.visualization_dock.width(),
                    VISUALIZATION_DOCK_MIN_WIDTH,
                )
                self._visualization_collapsed = True
                self.visualization_stack.setCurrentWidget(self.visualization_collapsed_widget)
                self.visualization_dock.setWindowTitle("Visualization")
                self.visualization_dock.setMinimumWidth(VISUALIZATION_DOCK_COLLAPSED_WIDTH)
                self.visualization_dock.setMaximumWidth(VISUALIZATION_DOCK_COLLAPSED_WIDTH)
                self._apply_visualization_dock_width(VISUALIZATION_DOCK_COLLAPSED_WIDTH)
                return

            self._visualization_collapsed = False
            self.visualization_dock.setMaximumWidth(16777215)
            self.visualization_dock.setMinimumWidth(VISUALIZATION_DOCK_MIN_WIDTH)
            self.visualization_stack.setCurrentWidget(self.visualization_expanded_widget)
            self.visualization_dock.setWindowTitle("Section Visualization")
            self._apply_visualization_dock_width(
                max(self._visualization_expanded_width, VISUALIZATION_DOCK_DEFAULT_WIDTH)
            )

        def apply_visualization_default_width(self) -> None:
            if not self._visualization_collapsed:
                self._apply_visualization_dock_width(VISUALIZATION_DOCK_DEFAULT_WIDTH)

        def _set_visualization_result_controls_enabled(self, enabled: bool) -> None:
            has_times = self.visualization_time_combo.count() > 0
            self.visualization_result_combo.setEnabled(bool(enabled))
            animation_times = (
                self._animation_is_visible()
                and len(self._animation_selected_result_sets()) >= 2
            )
            self.visualization_time_combo.setEnabled(
                has_times and (bool(enabled) or animation_times)
            )

        def _current_visualization_result_mode(self) -> str:
            value = self.visualization_result_combo.currentData()
            return str(value or "force")

        def _current_visualization_time_index(self) -> int:
            value = self.visualization_time_combo.currentData()
            if value is None:
                return 0
            return int(value)

        def _animation_selected_result_sets(self) -> List[Dict[str, Any]]:
            if self.analysis_mode_combo.currentData() != "static":
                return []
            scope = str(self.static_set_scope_combo.currentData() or "single")
            if scope not in {"range", "all"}:
                return []
            options = [dict(item) for item in self._loaded_result_sets]
            if scope == "all":
                return options
            start = int(self.result_set_range_start_spin.value())
            end = int(self.result_set_range_end_spin.value())
            stride = max(int(self.result_set_range_stride_spin.value()), 1)
            selected_ids = set(range(start, end + 1, stride)) if start <= end else set()
            return [item for item in options if int(item.get("id", 0)) in selected_ids]

        def _animation_is_visible(self) -> bool:
            return (
                self.analysis_mode_combo.currentData() == "static"
                and str(self.static_set_scope_combo.currentData() or "single")
                in {"range", "all"}
            )

        def _visualization_is_reference_preview_only(self) -> bool:
            return bool(
                (self._last_visualization_payload or {}).get("preview_only_reason")
            )

        def _sync_animation_time_combo(
            self,
            selected_sets: Sequence[Dict[str, Any]],
        ) -> None:
            result_data = self._last_visualization_result_data or {}
            result_ids = [
                int(value) for value in (result_data.get("result_set_ids") or [])
            ]
            selected_ids = [int(item.get("id", 0)) for item in selected_sets]
            if (
                result_data.get("analysis_mode") == "static"
                and result_ids == selected_ids
            ):
                self._animation_preview_time_options = False
                return
            previous_index = self.visualization_time_combo.currentIndex()
            blocked = self.visualization_time_combo.blockSignals(True)
            try:
                self.visualization_time_combo.clear()
                for index, item in enumerate(selected_sets):
                    self.visualization_time_combo.addItem(
                        str(item.get("label") or f"Set {item.get('id')}"),
                        index,
                    )
                if selected_sets:
                    self.visualization_time_combo.setCurrentIndex(
                        max(0, min(previous_index, len(selected_sets) - 1))
                    )
                self._animation_preview_time_options = bool(selected_sets)
            finally:
                self.visualization_time_combo.blockSignals(blocked)

        def _refresh_animation_availability(self) -> None:
            if not hasattr(self, "animation_group"):
                return
            visible = self._animation_is_visible()
            selected_sets = self._animation_selected_result_sets() if visible else []
            preview_only = self._visualization_is_reference_preview_only()
            available = len(selected_sets) >= 2 and not preview_only
            self.animation_group.setVisible(visible)
            self.animation_group.body_widget.setEnabled(available)
            self.animation_group.setToolTip(
                (
                    "Follow Geometry is limited to the initial/reference state until "
                    "the section plane cuts the selection or an explicit attachment is selected."
                )
                if preview_only
                else (
                    "Preview solved Static Structural Range/All deformation."
                    if available
                    else "Load metadata and select at least two cumulative result sets."
                )
            )
            if visible:
                self._sync_animation_time_combo(selected_sets)
            elif self._animation_preview_time_options and not self._last_visualization_result_data:
                blocked = self.visualization_time_combo.blockSignals(True)
                self.visualization_time_combo.clear()
                self.visualization_time_combo.blockSignals(blocked)
                self._animation_preview_time_options = False
            self._set_visualization_result_controls_enabled(
                bool(self._last_visualization_result_data)
            )
            if preview_only:
                self.animation_frame_label.setText(
                    "Initial/reference state only — Follow Geometry tracking unavailable"
                )
            elif not available:
                self.animation_frame_label.setText(
                    "Select at least two solved cumulative sets"
                )

        def _animation_record_options(self) -> List[Dict[str, Any]]:
            session = self._animation_session
            if session is not None and not session.closed:
                return [
                    {
                        "id": record.result_set_id,
                        "value": record.result_value,
                        "unit": record.result_unit,
                        "label": f"Set {record.result_set_id}",
                    }
                    for record in session.records
                ]
            return self._animation_selected_result_sets()

        def _animation_progress_for_index(self, index: int) -> float:
            options = self._animation_record_options()
            if len(options) < 2:
                return 0.0
            bounded = max(0, min(int(index), len(options) - 1))
            axis, _warning = static_animation_time_axis(options)
            span = float(axis[-1] - axis[0])
            if span <= 0.0:
                return float(bounded) / float(len(options) - 1)
            return (float(axis[bounded]) - float(axis[0])) / span

        def _animation_nearest_index(self, progress: Optional[float] = None) -> int:
            options = self._animation_record_options()
            if not options:
                return 0
            interpolation = static_animation_interpolation(
                options,
                self._animation_progress if progress is None else float(progress),
                mode="exact",
            )
            return int(interpolation.lower_index)

        def _animation_required_indices(
            self,
            progress: Optional[float] = None,
            *,
            mode: Optional[str] = None,
        ) -> Tuple[int, ...]:
            options = self._animation_record_options()
            if not options:
                return tuple()
            selected_mode = str(
                mode or self.animation_mode_combo.currentData() or "smooth"
            )
            interpolation = static_animation_interpolation(
                options,
                self._animation_progress if progress is None else float(progress),
                mode=selected_mode,
            )
            return tuple(
                dict.fromkeys(
                    (int(interpolation.lower_index), int(interpolation.upper_index))
                )
            )

        def _animation_initial_pair_ready(self) -> bool:
            session = self._animation_session
            if session is None or session.closed or session.loaded_count < 2:
                return False
            current = self._animation_nearest_index()
            neighbor = current + (1 if self._animation_direction >= 0 else -1)
            if neighbor < 0 or neighbor >= len(session.records):
                neighbor = current - (1 if self._animation_direction >= 0 else -1)
            return (
                0 <= current < len(session.records)
                and 0 <= neighbor < len(session.records)
                and session.is_loaded(current)
                and session.is_loaded(neighbor)
            )

        def _set_animation_progress_controls(self, progress: float) -> None:
            value = int(round(min(max(float(progress), 0.0), 1.0) * 1000.0))
            blocked = self.animation_timeline_slider.blockSignals(True)
            self.animation_timeline_slider.setValue(value)
            self.animation_timeline_slider.blockSignals(blocked)
            index = self._animation_nearest_index(progress)
            if self.visualization_time_combo.count() > index:
                blocked = self.visualization_time_combo.blockSignals(True)
                self.visualization_time_combo.setCurrentIndex(index)
                self.visualization_time_combo.blockSignals(blocked)
            self.result_history_widget.set_selected_time_index(index)

        def _set_animation_play_control_state(self, state: str) -> None:
            icon_name, accessible_name = {
                "play": ("play", "Play animation"),
                "pause": ("pause", "Pause animation"),
                "buffering": ("buffering", "Buffering animation frames"),
            }[state]
            self.animation_play_button.setText("")
            self.animation_play_button.setIcon(
                self._animation_control_icons[icon_name]
            )
            self.animation_play_button.setAccessibleName(accessible_name)
            self.animation_play_button.setProperty("animationState", state)

        def _animation_frame_text(self, payload: Dict[str, Any]) -> str:
            animation = payload.get("animation") or {}
            lower = animation.get("lower_result_set_id")
            upper = animation.get("upper_result_set_id")
            fraction = float(animation.get("fraction") or 0.0)
            if animation.get("exact", False) or lower == upper:
                text = f"Set {lower} (solved)"
            else:
                text = (
                    f"Sets {lower} -> {upper} | {fraction:.0%} | "
                    "visual interpolation"
                )
            scale = float(animation.get("deformation_scale") or 0.0)
            if abs(scale - 1.0) > 1.0e-12:
                text += f" | {scale:g}x visual-only deformation"
            return text

        def _render_static_animation_progress(
            self,
            *,
            mode_override: Optional[str] = None,
        ) -> bool:
            session = self._animation_session
            if session is None or session.closed or self._animation_render_busy:
                return False
            mode = str(mode_override or self.animation_mode_combo.currentData() or "smooth")
            required = self._animation_required_indices(mode=mode)
            if not required or not all(session.is_loaded(index) for index in required):
                self._animation_playing = False
                self.animation_timer.stop()
                self._set_animation_play_control_state("buffering")
                self.animation_frame_label.setText("Buffering solved displacement frames...")
                if (
                    self._animation_play_requested
                    and not (
                        self.animation_worker is not None
                        and self.animation_worker.isRunning()
                    )
                ):
                    self._start_animation_loader()
                return False
            self._animation_render_busy = True
            try:
                payload = build_static_animation_render_frame(
                    session,
                    self._animation_progress,
                    mode=mode,
                    deformation_scale=float(self.animation_deformation_spin.value()),
                    result_data=self._last_visualization_result_data,
                    result_mode=self._current_visualization_result_mode(),
                )
                rendered = self.visualization_widget.render_animation_payload(
                    payload,
                    playing=self._animation_playing,
                )
            except Exception:
                self.pause_static_animation()
                traceback_text = traceback.format_exc()
                self.animation_frame_label.setText("Animation paused at the last valid frame")
                self.visualization_status_label.setText(
                    "Animation frame failed; last valid deformed frame retained."
                )
                self.append_log(traceback_text)
                return False
            finally:
                self._animation_render_busy = False
            if not rendered:
                self.pause_static_animation()
                self.animation_frame_label.setText("Animation renderer unavailable")
                return False
            self._last_visualization_payload = payload
            self._visualization_stale = False
            self._set_visualization_update_button_stale(False)
            self._set_animation_progress_controls(self._animation_progress)
            self.animation_frame_label.setText(self._animation_frame_text(payload))
            self.visualization_status_label.setText(
                "Animation preview uses solved RST deformation; interpolated frames "
                "and non-1x scale are visualization-only."
            )
            self._refresh_nodal_force_export_action()
            return True

        def _start_animation_loader(self) -> None:
            if self.animation_worker is not None and self.animation_worker.isRunning():
                return
            try:
                config = self.collect_config()
                selected_sets = self._animation_selected_result_sets()
                if len(selected_sets) < 2:
                    raise ValueError("Select at least two cumulative static result sets.")
                signature = static_animation_session_signature(config, selected_sets)
            except Exception as exc:
                self._animation_play_requested = False
                self._set_animation_play_control_state("play")
                self.animation_frame_label.setText(str(exc))
                return
            self._animation_generation += 1
            generation = self._animation_generation
            self._animation_signature = signature
            priority_index = self._animation_nearest_index()
            worker = StaticAnimationLoaderThread(
                config,
                selected_sets,
                generation=generation,
                signature=signature,
                priority_index=priority_index,
                direction=self._animation_direction,
            )
            self.animation_worker = worker
            worker.log_message.connect(self.append_log)
            worker.batch_loaded.connect(self._on_animation_batch_loaded)
            worker.completed.connect(self._on_animation_loader_completed)
            worker.failed.connect(self._on_animation_loader_failed)
            self.animation_frame_label.setText("Buffering solved displacement frames...")
            self._set_animation_play_control_state("buffering")
            worker.start()

        def _adopt_animation_session(self, session: StaticAnimationSession) -> None:
            previous = self._animation_session
            if previous is session:
                return
            self._animation_session = session
            self._animation_signature = session.signature
            if previous is not None and previous is not session and not previous.closed:
                previous.close()

        def _on_animation_batch_loaded(
            self,
            generation: int,
            session: StaticAnimationSession,
            _indices: Sequence[int],
        ) -> None:
            if int(generation) != self._animation_generation:
                return
            self._adopt_animation_session(session)
            if self._animation_play_requested and self._animation_initial_pair_ready():
                self._begin_static_animation_playback()

        def _on_animation_loader_completed(
            self,
            generation: int,
            session: StaticAnimationSession,
        ) -> None:
            if int(generation) != self._animation_generation:
                if not session.closed:
                    session.close()
                if self.animation_worker is self.sender():
                    self.animation_worker = None
                return
            self.animation_worker = None
            self._adopt_animation_session(session)
            if self._animation_play_requested:
                if self._animation_initial_pair_ready():
                    self._begin_static_animation_playback()
                else:
                    self._animation_play_requested = False
                    self._set_animation_play_control_state("play")
                    self.animation_frame_label.setText(
                        "Animation load stopped before two endpoint frames were ready"
                    )
            elif session.loaded_count:
                self._set_animation_play_control_state("play")

        def _on_animation_loader_failed(
            self,
            generation: int,
            traceback_text: str,
        ) -> None:
            if int(generation) != self._animation_generation:
                self.animation_worker = None
                return
            self.animation_worker = None
            self.pause_static_animation()
            self.animation_frame_label.setText("Animation loading failed")
            self.visualization_status_label.setText(
                "Animation loading failed; last valid deformed frame retained."
            )
            self.append_log(traceback_text)

        def _begin_static_animation_playback(self) -> None:
            if not self._animation_initial_pair_ready():
                return
            self._animation_play_requested = True
            self._animation_playing = True
            self._set_animation_play_control_state("pause")
            self.animation_elapsed_timer.restart()
            if self._render_static_animation_progress():
                self.animation_timer.start()

        def toggle_static_animation_playback(self) -> None:
            if self._animation_playing or self._animation_play_requested:
                self.pause_static_animation()
                return
            if self._visualization_is_reference_preview_only():
                self._refresh_animation_availability()
                return
            if len(self._animation_selected_result_sets()) < 2:
                self._refresh_animation_availability()
                return
            self._animation_play_requested = True
            if self._animation_initial_pair_ready():
                self._begin_static_animation_playback()
                return
            self._start_animation_loader()

        def pause_static_animation(self) -> None:
            self._animation_playing = False
            self._animation_play_requested = False
            self.animation_timer.stop()
            self._set_animation_play_control_state("play")
            if hasattr(self, "visualization_widget"):
                self.visualization_widget.set_animation_playing(False)

        def stop_static_animation(self) -> None:
            self.pause_static_animation()
            if self.animation_worker is not None and self.animation_worker.isRunning():
                self.animation_worker.cancel()
            self._animation_direction = 1
            self._animation_progress = 0.0
            self._set_animation_progress_controls(0.0)
            session = self._animation_session
            if session is not None and not session.closed and session.is_loaded(0):
                self._render_static_animation_progress(mode_override="exact")
            else:
                options = self._animation_record_options()
                if options:
                    self.animation_frame_label.setText(
                        f"Set {options[0].get('id')} selected; press Play to stream preview"
                    )

        def advance_static_animation(self) -> None:
            if not self._animation_playing or self._animation_render_busy:
                return
            elapsed_seconds = max(float(self.animation_elapsed_timer.restart()), 0.0) / 1000.0
            speed = float(self.animation_speed_combo.currentData() or 1.0)
            progress = self._animation_progress + (
                float(self._animation_direction) * elapsed_seconds * speed / 4.0
            )
            cycle = str(self.animation_cycle_combo.currentData() or "loop")
            if cycle == "once":
                if progress <= 0.0 or progress >= 1.0:
                    self._animation_progress = min(max(progress, 0.0), 1.0)
                    self._render_static_animation_progress()
                    self.pause_static_animation()
                    return
            elif cycle == "ping-pong":
                while progress < 0.0 or progress > 1.0:
                    if progress > 1.0:
                        progress = 2.0 - progress
                        self._animation_direction = -1
                    elif progress < 0.0:
                        progress = -progress
                        self._animation_direction = 1
            else:
                progress %= 1.0
            self._animation_progress = min(max(progress, 0.0), 1.0)
            if not self._render_static_animation_progress():
                self.animation_timer.stop()

        def _set_animation_exact_index(self, index: int, *, render: bool = True) -> None:
            options = self._animation_record_options()
            if not options:
                return
            bounded = max(0, min(int(index), len(options) - 1))
            self._animation_progress = self._animation_progress_for_index(bounded)
            self._set_animation_progress_controls(self._animation_progress)
            if render:
                session = self._animation_session
                if session is not None and not session.closed and session.is_loaded(bounded):
                    self._render_static_animation_progress(mode_override="exact")
                else:
                    self.animation_frame_label.setText(
                        f"Set {options[bounded].get('id')} selected; press Play to stream preview"
                    )

        def step_static_animation(self, direction: int) -> None:
            self.pause_static_animation()
            options = self._animation_record_options()
            if not options:
                return
            current = self._animation_nearest_index()
            self._set_animation_exact_index(current + int(direction))

        def on_animation_slider_pressed(self) -> None:
            self._animation_slider_dragging = True
            self.pause_static_animation()

        def on_animation_slider_moved(self, value: int) -> None:
            self.pause_static_animation()
            progress = min(max(float(value) / 1000.0, 0.0), 1.0)
            index = self._animation_nearest_index(progress)
            self._set_animation_exact_index(index)

        def on_animation_slider_released(self) -> None:
            self._animation_slider_dragging = False
            progress = min(
                max(float(self.animation_timeline_slider.value()) / 1000.0, 0.0),
                1.0,
            )
            self._set_animation_exact_index(self._animation_nearest_index(progress))

        def on_animation_display_option_changed(self) -> None:
            if self._animation_session is not None:
                self._render_static_animation_progress(
                    mode_override=None if self._animation_playing else "exact"
                )

        def _invalidate_animation_session(self) -> None:
            self.pause_static_animation()
            self._animation_generation += 1
            worker_running = (
                self.animation_worker is not None and self.animation_worker.isRunning()
            )
            if worker_running:
                self.animation_worker.cancel()
            session = self._animation_session
            self._animation_session = None
            self._animation_signature = None
            if session is not None and not session.closed and not worker_running:
                session.close()

        def _current_nodal_force_export_payload(self) -> Optional[Dict[str, Any]]:
            if self._last_visualization_payload is None or self._visualization_stale:
                return None
            animation = self._last_visualization_payload.get("animation") or {}
            if animation and not animation.get("exact", False):
                return None
            if not self._last_visualization_result_data:
                return None
            if not result_signature_matches_visualization(
                self._last_visualization_result_data,
                self._last_visualization_payload,
                self._current_visualization_time_index(),
            ):
                return None
            return build_nodal_force_time_export_payload(
                self._last_visualization_result_data,
                self._current_visualization_time_index(),
            )

        def _refresh_nodal_force_export_action(self) -> None:
            self.visualization_widget.set_nodal_force_export_enabled(
                self._current_nodal_force_export_payload() is not None
            )

        def _default_nodal_force_export_path(self) -> str:
            base_text = self.out_row.text()
            if base_text:
                base = Path(base_text)
            else:
                base = Path.cwd() / "nodal_forces.csv"
            time_index = self._current_visualization_time_index() + 1
            return str(base.with_name(f"{base.stem}_nodal_forces_t{time_index}.csv"))

        def _default_nodal_force_excel_export_path(self) -> str:
            csv_path = Path(self._default_nodal_force_export_path())
            return str(csv_path.with_suffix(".xlsx"))

        def _set_visualization_result_times(
            self,
            result_data: Optional[Dict[str, Any]],
        ) -> None:
            previous_time = self.visualization_time_combo.currentData()
            self.visualization_time_combo.blockSignals(True)
            self.visualization_time_combo.clear()
            selected_index = 0
            if result_data:
                static_mode = result_data.get("analysis_mode") == "static"
                selected_sets = result_data.get("selected_result_sets") or []
                for index, time_value in enumerate(result_data.get("times", [])):
                    if static_mode and index < len(selected_sets):
                        label = str(
                            selected_sets[index].get("label")
                            or f"Set {selected_sets[index].get('id')}"
                        )
                    else:
                        label = f"{index + 1}: {float(time_value):.6g} s"
                    self.visualization_time_combo.addItem(
                        label,
                        index,
                    )
                    if previous_time is not None and int(previous_time) == index:
                        selected_index = index
                if static_mode and self.visualization_time_combo.count():
                    selected_index = self.visualization_time_combo.count() - 1
                if self.visualization_time_combo.count():
                    self.visualization_time_combo.setCurrentIndex(
                        min(selected_index, self.visualization_time_combo.count() - 1)
                    )
            self.visualization_time_combo.blockSignals(False)
            self._set_visualization_result_controls_enabled(bool(result_data))
            self._refresh_nodal_force_export_action()
            if not result_data:
                self.result_history_widget.clear_history(
                    "Run extraction to populate result history."
                )

        def _payload_with_current_result_overlay(
            self,
            payload: Dict[str, Any],
        ) -> Dict[str, Any]:
            if self._visualization_stale or payload.get("preview_only_reason"):
                preview_payload = dict(payload)
                preview_payload.pop("result_overlay", None)
                return preview_payload
            return visualization_payload_with_result_overlay(
                payload,
                self._last_visualization_result_data,
                self._current_visualization_result_mode(),
                self._current_visualization_time_index(),
            )

        def _current_result_history_payload(self) -> Optional[Dict[str, Any]]:
            if self._last_visualization_payload is None or self._visualization_stale:
                return None
            frame = self.result_history_widget.frame_for_payload(
                result_history_series_signature(
                    self._last_visualization_result_data
                ),
                result_history_default_frame(self._last_visualization_payload),
            )
            return build_result_history_plot_payload(
                self._last_visualization_payload,
                self._last_visualization_result_data,
                frame,
                selected_time_index=self._current_visualization_time_index(),
                moment_display_unit=self.result_history_widget.current_moment_unit(),
            )

        def _result_history_unavailable_message(self) -> str:
            if not self._last_visualization_result_data:
                return "Run extraction to populate result history."
            if self._last_visualization_payload is None:
                return "Update visualization to show result history."
            if self._visualization_is_reference_preview_only():
                return (
                    "Result history is hidden while Follow Geometry shows only the "
                    "initial/reference state."
                )
            if self._visualization_stale:
                return "Visualization needs update; result history hidden until updated."
            if not result_history_signature_matches_visualization(
                self._last_visualization_result_data,
                self._last_visualization_payload,
                self._current_visualization_time_index(),
            ):
                return "Run extraction again to update result history."
            return "Result history is unavailable for this run."

        def refresh_result_history_plot(self) -> None:
            payload = self._current_result_history_payload()
            if payload is None:
                self.result_history_widget.clear_history(
                    self._result_history_unavailable_message()
                )
                return
            self.result_history_widget.set_history_payload(
                payload,
                self._current_visualization_time_index(),
            )

        def go_to_result_history_time(self, time_index: int, result_mode: str) -> None:
            self.pause_static_animation()
            mode = "moment" if str(result_mode).lower().startswith("moment") else "force"
            result_was_blocked = self.visualization_result_combo.blockSignals(True)
            time_was_blocked = self.visualization_time_combo.blockSignals(True)
            try:
                self._set_combo_value(self.visualization_result_combo, mode)
                if self.visualization_time_combo.count():
                    index = max(
                        0,
                        min(int(time_index), self.visualization_time_combo.count() - 1),
                    )
                    self.visualization_time_combo.setCurrentIndex(index)
            finally:
                self.visualization_result_combo.blockSignals(result_was_blocked)
                self.visualization_time_combo.blockSignals(time_was_blocked)
            self.on_visualization_time_changed(time_index)

        def _static_result_set_id_for_time(self, time_index: int) -> Optional[int]:
            result_data = self._last_visualization_result_data or {}
            if result_data.get("analysis_mode") != "static":
                return None
            result_set_ids = result_data.get("result_set_ids") or []
            if 0 <= int(time_index) < len(result_set_ids):
                return int(result_set_ids[int(time_index)])
            return None

        def on_visualization_time_changed(self, time_index: int) -> None:
            if (
                self._animation_session is not None
                and self._animation_is_visible()
                and len(self._animation_record_options()) >= 2
            ):
                self.pause_static_animation()
                self._set_animation_exact_index(int(time_index))
                return
            set_id = self._static_result_set_id_for_time(int(time_index))
            if set_id is None:
                self.refresh_result_overlay_render()
                return
            if result_signature_matches_visualization(
                self._last_visualization_result_data,
                self._last_visualization_payload,
                int(time_index),
            ):
                self.refresh_result_overlay_render()
                return
            self.update_visualization(result_set_id=set_id)

        def _result_overlay_status_suffix(
            self,
            payload: Dict[str, Any],
            render_payload: Dict[str, Any],
        ) -> str:
            if payload.get("preview_only_reason"):
                return "; result vectors/history hidden in reference-only preview"
            overlay = render_payload.get("result_overlay")
            if overlay:
                return (
                    f"; {overlay.get('label')} vectors shown at "
                    f"t={float(overlay.get('time') or 0.0):.6g} s"
                )
            if not self._last_visualization_result_data:
                return ""
            if self._visualization_stale:
                return "; update visualization to show result vectors/history"
            if not result_signature_matches_visualization(
                self._last_visualization_result_data,
                payload,
                self._current_visualization_time_index(),
            ):
                return "; run extraction again to update result vectors/history"
            return "; result vectors/history unavailable"

        def _render_current_visualization_payload(self) -> bool:
            if self._last_visualization_payload is None:
                return False
            render_payload = self._payload_with_current_result_overlay(
                self._last_visualization_payload
            )
            rendered = self.visualization_widget.render_payload(render_payload)
            if rendered:
                counts = self._last_visualization_payload.get("counts") or {}
                self.visualization_status_label.setText(
                    "Visualization updated: "
                    f"{counts.get('raw_element_count', 0)} selected element(s), "
                    f"{counts.get('cut_element_count', 0)} cut element(s), "
                    f"{counts.get('force_summation_node_count', 0)} force node(s)"
                    f"{self._result_overlay_status_suffix(self._last_visualization_payload, render_payload)}."
                )
            return rendered

        def refresh_result_overlay_render(self) -> None:
            if (
                self._animation_session is not None
                and self._last_visualization_payload is not None
                and self._last_visualization_payload.get("animation")
            ):
                self._render_static_animation_progress(
                    mode_override=None if self._animation_playing else "exact"
                )
                self.refresh_result_history_plot()
                return
            if self._last_visualization_payload is None:
                self._refresh_nodal_force_export_action()
                self.refresh_result_history_plot()
                return
            if self._visualization_stale:
                self.visualization_status_label.setText(
                    "Visualization needs update; result vectors/history hidden until updated."
                )
                self._refresh_nodal_force_export_action()
                self.refresh_result_history_plot()
                return
            self._render_current_visualization_payload()
            self._refresh_nodal_force_export_action()
            self.refresh_result_history_plot()

        def _new_form_layout(self, parent: Any) -> Any:
            form = QtWidgets.QFormLayout(parent)
            form.setContentsMargins(2, 2, 2, 2)
            form.setHorizontalSpacing(12)
            form.setVerticalSpacing(6)
            form.setFieldGrowthPolicy(
                QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )
            form.setRowWrapPolicy(
                QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows
            )
            return form

        def _vector3_editor(
            self,
            edits: Sequence[Any],
            help_text: str,
        ) -> Any:
            widget = QtWidgets.QWidget()
            widget.setObjectName("vector3Editor")
            layout = QtWidgets.QGridLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setHorizontalSpacing(6)
            layout.setVerticalSpacing(2)
            for column, (component, edit) in enumerate(
                zip(("X", "Y", "Z"), edits)
            ):
                header = QtWidgets.QLabel(component)
                header.setObjectName("vectorComponentHeader")
                header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                header.setToolTip(help_text)
                edit.setMinimumWidth(64)
                edit.setMaximumWidth(160)
                edit.setSizePolicy(
                    QtWidgets.QSizePolicy.Policy.Expanding,
                    QtWidgets.QSizePolicy.Policy.Fixed,
                )
                edit.setToolTip(help_text)
                layout.addWidget(header, 0, column)
                layout.addWidget(edit, 1, column)
                layout.setColumnStretch(column, 1)
            return widget

        def _orientation_matrix_widget(self) -> Any:
            widget = QtWidgets.QWidget()
            widget.setObjectName("orientationMatrix")
            layout = QtWidgets.QGridLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setHorizontalSpacing(6)
            layout.setVerticalSpacing(5)
            for column, title in enumerate(("Global X", "Global Y", "Global Z"), 1):
                header = QtWidgets.QLabel(title)
                header.setObjectName("vectorComponentHeader")
                header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(header, 0, column)
                layout.setColumnStretch(column, 1)
            help_by_axis = {
                "x": "Global X/Y/Z components of the local coordinate system X direction.",
                "y": "Global X/Y/Z components of the local coordinate system Y direction.",
                "z": "Global X/Y/Z components of the local +Z normal; positive side uses this direction.",
            }
            for row, axis_name in enumerate(("x", "y", "z"), 1):
                help_text = help_by_axis[axis_name]
                row_label = QtWidgets.QLabel(f"Local {axis_name.upper()}")
                row_label.setObjectName("vectorRowLabel")
                row_label.setToolTip(help_text)
                layout.addWidget(row_label, row, 0)
                for column, edit in enumerate(self.axis_edits[axis_name], 1):
                    edit.setMinimumWidth(64)
                    edit.setMaximumWidth(160)
                    edit.setSizePolicy(
                        QtWidgets.QSizePolicy.Policy.Expanding,
                        QtWidgets.QSizePolicy.Policy.Fixed,
                    )
                    edit.setToolTip(help_text)
                    layout.addWidget(edit, row, column)
            return widget

        def _coordinate_system_widget(self) -> Any:
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.coordinate_system_combo, 1)
            layout.addWidget(self.scan_coordinate_system_button)
            return widget

        def _apply_style(self) -> None:
            stylesheet = """
                QMainWindow { background: #f5f7f8; }
                QMenuBar {
                    background: #f5f7f8;
                    color: #26343d;
                    spacing: 2px;
                    padding: 2px 6px;
                }
                QMenuBar::item {
                    background: transparent;
                    border-radius: 4px;
                    padding: 4px 8px;
                }
                QMenuBar::item:selected,
                QMenuBar::item:pressed {
                    background: #edf5f3;
                    color: #17212b;
                }
                QMenu {
                    background: #ffffff;
                    border: 1px solid #c9d2d7;
                    color: #17212b;
                    padding: 4px;
                }
                QMenu::item {
                    padding: 6px 28px 6px 24px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background: #2d7f72;
                    color: #ffffff;
                }
                QMenu::indicator {
                    width: 14px;
                    height: 14px;
                }
                QDockWidget {
                    background: #f5f7f8;
                    color: #26343d;
                    border: 1px solid #c9d2d7;
                }
                QDockWidget::title {
                    background: #e7eef1;
                    color: #26343d;
                    border-bottom: 1px solid #c9d2d7;
                    padding: 5px 8px;
                    text-align: left;
                    font-weight: 600;
                }
                QWidget#visualizationDockContent,
                QWidget#visualizationDockCollapsedContent,
                QWidget#resultHistoryEmbeddedContainer,
                QWidget#resultHistoryDockContent {
                    background: #f5f7f8;
                    color: #26343d;
                }
                QWidget#themedDockTitleBar {
                    background: #e7eef1;
                    border: 0;
                    border-bottom: 1px solid #c9d2d7;
                }
                QLabel#themedDockTitleLabel {
                    color: #26343d;
                    font-weight: 600;
                    padding-left: 2px;
                }
                QToolButton#dockTitleButton {
                    background: transparent;
                    border: 0;
                    border-radius: 4px;
                    padding: 2px;
                }
                QToolButton#dockTitleButton:hover {
                    background: #d6e9e4;
                }
                QToolButton#dockTitleButton:pressed {
                    background: #c5ded8;
                }
                QToolButton#resultHistoryDockButton {
                    background: transparent;
                    border: 1px solid transparent;
                    border-radius: 5px;
                    padding: 2px;
                }
                QToolButton#resultHistoryDockButton:hover {
                    background: #edf5f3;
                    border-color: #acc2bd;
                }
                QToolButton#resultHistoryDockButton:pressed {
                    background: #dcece8;
                    border-color: #9fb9b3;
                }
                QFrame#collapsibleGroup {
                    background: #f5f7f8;
                    border: 1px solid #c9d2d7;
                    border-radius: 6px;
                }
                QWidget#collapsibleGroupHeader,
                QWidget#collapsibleGroupBody {
                    background: transparent;
                    border: 0;
                }
                QLabel#collapsibleGroupTitle {
                    color: #1f2a33;
                    font-weight: 600;
                }
                QGroupBox {
                    border: 1px solid #c9d2d7;
                    border-radius: 6px;
                    margin-top: 10px;
                    padding: 10px 10px 8px 10px;
                    font-weight: 600;
                    color: #1f2a33;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 4px;
                }
                QLineEdit, QPlainTextEdit, QComboBox,
                QSpinBox, QDoubleSpinBox {
                    background: #ffffff;
                    border: 1px solid #b9c5ca;
                    border-radius: 4px;
                    padding: 5px;
                    color: #17212b;
                }
                QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled,
                QSpinBox:disabled, QDoubleSpinBox:disabled {
                    background: #eef2f3;
                    border-color: #c9d2d7;
                    color: #52616b;
                }
                QComboBox {
                    padding-right: 34px;
                }
                QComboBox:hover {
                    border-color: #8aa7a0;
                }
                QComboBox::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    border-left: 1px solid #b9c5ca;
                    width: 30px;
                }
                QComboBox::down-arrow {
                    image: none;
                    width: 0;
                    height: 0;
                }
                QComboBox QAbstractItemView {
                    background: #ffffff;
                    border: 1px solid #b9c5ca;
                    color: #17212b;
                    selection-background-color: #2d7f72;
                    selection-color: #ffffff;
                }
                QPushButton {
                    background: #236b5f;
                    color: #ffffff;
                    border: 0;
                    border-radius: 5px;
                    padding: 7px 12px;
                    font-weight: 600;
                }
                QPushButton:hover { background: #2d7f72; }
                QPushButton:disabled { background: #9aa8ad; }
                QPushButton[animationControl="true"] {
                    min-width: 34px;
                    max-width: 34px;
                    min-height: 32px;
                    max-height: 32px;
                    padding: 0;
                }
                QPushButton#visualizationUpdateButton[visualizationStale="true"] {
                    background: #d9a521;
                    color: #17212b;
                }
                QPushButton#visualizationUpdateButton[visualizationStale="true"]:hover {
                    background: #e4b333;
                }
                QPushButton#visualizationUpdateButton:disabled {
                    background: #9aa8ad;
                    color: #ffffff;
                }
                QCheckBox#loadModalRstFromConfigCheckbox {
                    color: #26343d;
                    spacing: 8px;
                    font-weight: 500;
                }
                QCheckBox#loadModalRstFromConfigCheckbox:disabled {
                    color: #52616b;
                }
                QLabel { color: #26343d; }
                QScrollArea#inputInspectorScrollArea {
                    border: 0;
                    background: transparent;
                }
                QWidget#inputInspectorContent {
                    background: transparent;
                }
                QWidget#inputActionFooter {
                    background: #f5f7f8;
                    border-top: 1px solid #d1dadd;
                }
                QLabel#vectorComponentHeader {
                    color: #52616b;
                    font-size: 10px;
                    font-weight: 600;
                }
                QLabel#vectorRowLabel {
                    color: #35434b;
                    font-weight: 500;
                }
                QSplitter#visualizationVerticalSplitter::handle:vertical {
                    background: #e3ebee;
                    border-top: 1px solid #c5d1d6;
                    border-bottom: 1px solid #c5d1d6;
                    margin: 2px 0;
                }
                QSplitter#visualizationVerticalSplitter::handle:vertical:hover {
                    background: #d6e9e4;
                    border-top-color: #9bbab2;
                    border-bottom-color: #9bbab2;
                }
                QSplitter#runLogVerticalSplitter::handle:vertical {
                    background: #e3ebee;
                    border-top: 1px solid #c5d1d6;
                    border-bottom: 1px solid #c5d1d6;
                    margin: 2px 0;
                }
                QSplitter#runLogVerticalSplitter::handle:vertical:hover {
                    background: #d6e9e4;
                    border-top-color: #9bbab2;
                    border-bottom-color: #9bbab2;
                }
                """
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.setStyleSheet(stylesheet)
            else:
                self.setStyleSheet(stylesheet)

        def _populate_combo(self, combo: Any, choices: Sequence[Tuple[str, Any]]) -> None:
            combo.clear()
            combo.setEditable(False)
            combo.setMaxVisibleItems(max(8, len(choices)))
            for label, value in choices:
                combo.addItem(label, value)

        def _configure_searchable_combo(self, combo: Any) -> None:
            no_insert = (
                QtWidgets.QComboBox.InsertPolicy.NoInsert
            )
            combo.setInsertPolicy(no_insert)
            completer = combo.completer()
            if completer is None:
                completer = QtWidgets.QCompleter(combo.model(), combo)
                combo.setCompleter(completer)
            completer.setCaseSensitivity(
                QtCore.Qt.CaseSensitivity.CaseInsensitive
            )
            if hasattr(completer, "setFilterMode"):
                completer.setFilterMode(
                    QtCore.Qt.MatchFlag.MatchContains
                )
            completer.setCompletionMode(
                QtWidgets.QCompleter.CompletionMode.PopupCompletion
            )

        def _connect_visualization_stale_signals(self) -> None:
            self.modal_row.edit.textChanged.connect(
                lambda _text: self.mark_visualization_stale()
            )
            self.external_selection_row.edit.textChanged.connect(
                lambda _text: self.mark_visualization_stale()
            )
            self.element_combo.currentTextChanged.connect(
                lambda _text: self.mark_visualization_stale()
            )
            self.normal_combo.currentIndexChanged.connect(
                lambda _index: self.mark_visualization_stale()
            )
            self.side_combo.currentIndexChanged.connect(
                lambda _index: self.mark_visualization_stale()
            )
            self.moment_combo.currentIndexChanged.connect(
                lambda _index: self.mark_visualization_stale()
            )
            self.tolerance_edit.textChanged.connect(
                lambda _text: self.mark_visualization_stale()
            )
            self.skip_first_modes_spin.valueChanged.connect(
                lambda _value: self.mark_visualization_stale()
            )
            for edit in self.origin_edits:
                edit.textChanged.connect(lambda _text: self.mark_visualization_stale())
            for edits in self.axis_edits.values():
                for edit in edits:
                    edit.textChanged.connect(
                        lambda _text: self.mark_visualization_stale()
                    )

        def _set_visualization_update_button_stale(self, stale: bool) -> None:
            button = self.visualization_update_button
            button.setProperty("visualizationStale", "true" if stale else "false")
            style = button.style()
            style.unpolish(button)
            style.polish(button)
            button.update()

        def mark_visualization_stale(self) -> None:
            self._visualization_input_revision += 1
            self._invalidate_animation_session()
            self._refresh_animation_availability()
            worker_running = (
                self.visualization_worker is not None
                and self.visualization_worker.isRunning()
            )
            self._visualization_stale = True
            self._refresh_nodal_force_export_action()
            if self._last_visualization_result_data:
                self.visualization_status_label.setText(
                    "Visualization needs update; result vectors/history hidden until updated."
                )
            else:
                self.visualization_status_label.setText("Visualization needs update")
            self.refresh_result_history_plot()
            self.visualization_update_button.setEnabled(not worker_running)
            self._set_visualization_update_button_stale(True)

        def set_config(self, cfg: SectionConfig) -> None:
            if hasattr(self, "animation_timer"):
                self._invalidate_animation_session()
            self._set_combo_value(self.analysis_mode_combo, cfg.analysis_mode)
            self._set_combo_value(self.static_set_scope_combo, cfg.static_set_scope)
            self._pending_result_set_id = cfg.result_set_id
            self._pending_result_set_range_start = cfg.result_set_range_start
            self._pending_result_set_range_end = cfg.result_set_range_end
            self._applying_config = True
            try:
                self.modal_row.set_text(cfg.modal_rst)
            finally:
                self._applying_config = False
            self.mcf_row.set_text(cfg.mcf)
            self.out_row.set_text(cfg.out_csv)
            self.external_selection_row.set_text(cfg.external_named_selection_path)
            self.element_combo.setEditText(cfg.element_named_selection)
            for edit, value in zip(self.origin_edits, cfg.coordinate_system_origin):
                edit.setText(f"{float(value):.12g}")
            for axis_name, edits in self.axis_edits.items():
                for edit, value in zip(edits, cfg.coordinate_system_axes[axis_name]):
                    edit.setText(f"{float(value):.12g}")
            self._set_combo_value(self.normal_combo, cfg.section_normal_axis)
            self._set_combo_value(self.side_combo, cfg.extraction_side)
            self._set_combo_value(self.moment_combo, cfg.moment_reference_mode)
            self._set_combo_value(
                self.reference_frame_motion_combo,
                cfg.reference_frame_motion,
            )
            self.reference_frame_attachment_combo.setEditText(
                cfg.reference_frame_attachment_selection
            )
            self.reference_frame_fit_warning_spin.setValue(
                float(cfg.reference_frame_fit_warning_ratio) * 100.0
            )
            self.tolerance_edit.setText(f"{float(cfg.side_filter_tolerance):.12g}")
            self._set_combo_value(self.force_type_combo, int(cfg.force_type))
            self.skip_first_modes_spin.setValue(int(cfg.skip_first_modes))
            self.modal_batch_spin.setValue(int(cfg.modal_summation_batch_size))
            self.coordinate_system_combo.setCurrentIndex(0)
            self._select_result_set(self._pending_result_set_id)
            self.on_analysis_mode_changed(mark_stale=False)
            self.on_static_set_scope_changed(mark_stale=False)
            self.on_reference_frame_motion_changed(mark_stale=False)
            self._refresh_animation_availability()

        def _message_box_yes_no(self) -> Tuple[Any, Any]:
            buttons = QtWidgets.QMessageBox.StandardButton
            return buttons.Yes, buttons.No

        def _critical_message_icon(self) -> Any:
            return (
                QtWidgets.QMessageBox.Icon.Critical
            )

        def _ok_message_button(self) -> Any:
            return (
                QtWidgets.QMessageBox.StandardButton.Ok
            )

        def _show_themed_error_dialog(
            self,
            title: str,
            text: str,
            detailed_text: str = "",
        ) -> None:
            dialog = QtWidgets.QMessageBox(self)
            dialog.setIcon(self._critical_message_icon())
            dialog.setWindowTitle(title)
            dialog.setText(text)
            if detailed_text:
                dialog.setDetailedText(detailed_text)
            dialog.setStandardButtons(self._ok_message_button())
            dialog.setStyleSheet(
                """
                QMessageBox {
                    background: #f5f7f8;
                    color: #26343d;
                }
                QMessageBox QLabel {
                    color: #26343d;
                    font-size: 13px;
                }
                QMessageBox QTextEdit {
                    background: #ffffff;
                    color: #17212b;
                    border: 1px solid #b9c5ca;
                    border-radius: 4px;
                    padding: 6px;
                }
                QMessageBox QPushButton {
                    background: #236b5f;
                    color: #ffffff;
                    border: 0;
                    border-radius: 5px;
                    padding: 7px 14px;
                    min-width: 72px;
                    font-weight: 600;
                }
                QMessageBox QPushButton:hover { background: #2d7f72; }
                """
            )
            dialog.exec()

        def update_visualization(
            self,
            _checked: bool = False,
            *,
            result_set_id: Optional[int] = None,
        ) -> None:
            if self.visualization_worker is not None and self.visualization_worker.isRunning():
                if result_set_id is not None:
                    self._queued_visualization_result_set_id = int(result_set_id)
                return
            try:
                cfg = self.collect_config()
            except Exception as exc:
                self.append_log(f"[{timestamp()}] Visualization settings validation failed: {exc}")
                self._show_themed_error_dialog(
                    "Invalid visualization settings",
                    str(exc),
                )
                return
            if cfg.analysis_mode == "static":
                selected_set_id = result_set_id
                if selected_set_id is None:
                    selected_set_id = self._static_result_set_id_for_time(
                        self._current_visualization_time_index()
                    )
                if selected_set_id is not None:
                    cfg.result_set_id = int(selected_set_id)

            self.append_log(f"[{timestamp()}] ---- Visualization update started ----")
            self.visualization_status_label.setText("Updating visualization...")
            self._set_visualization_update_button_stale(False)
            self.visualization_update_button.setEnabled(False)
            self.visualization_dock.show()
            self._visualization_generation += 1
            generation = self._visualization_generation
            input_revision = self._visualization_input_revision
            self._queued_visualization_result_set_id = None
            self.visualization_worker = VisualizationThread(cfg)
            self.visualization_worker.log_message.connect(self.append_log)
            self.visualization_worker.completed.connect(
                lambda payload,
                token=generation,
                revision=input_revision: self._on_visualization_thread_completed(
                    token, revision, payload
                )
            )
            self.visualization_worker.failed.connect(
                lambda traceback_text,
                token=generation,
                revision=input_revision: self._on_visualization_thread_failed(
                    token, revision, traceback_text
                )
            )
            self.visualization_worker.start()

        def _on_visualization_thread_completed(
            self,
            generation: int,
            input_revision: int,
            payload: Dict[str, Any],
        ) -> None:
            if int(generation) != self._visualization_generation:
                return
            self.visualization_worker = None
            if int(input_revision) != self._visualization_input_revision:
                self._visualization_stale = True
                self.visualization_update_button.setEnabled(True)
                self._set_visualization_update_button_stale(True)
                self._refresh_nodal_force_export_action()
                self.visualization_status_label.setText(
                    "Visualization inputs changed while loading; update again to render them."
                )
                self.refresh_result_history_plot()
                self.append_log(
                    f"[{timestamp()}] Discarded an outdated visualization payload "
                    "after inputs changed."
                )
                return
            self.on_visualization_completed(payload)
            queued_set_id = self._queued_visualization_result_set_id
            self._queued_visualization_result_set_id = None
            if queued_set_id is not None:
                QtCore.QTimer.singleShot(
                    0,
                    lambda set_id=queued_set_id: self.update_visualization(
                        result_set_id=set_id
                    ),
                )

        def _on_visualization_thread_failed(
            self,
            generation: int,
            input_revision: int,
            traceback_text: str,
        ) -> None:
            if int(generation) != self._visualization_generation:
                return
            self.visualization_worker = None
            if int(input_revision) != self._visualization_input_revision:
                self._visualization_stale = True
                self.visualization_update_button.setEnabled(True)
                self._set_visualization_update_button_stale(True)
                self._refresh_nodal_force_export_action()
                self.visualization_status_label.setText(
                    "Visualization inputs changed while loading; update again to render them."
                )
                self.refresh_result_history_plot()
                self.append_log(
                    f"[{timestamp()}] Ignored a visualization failure from outdated inputs."
                )
                return
            self.on_visualization_failed(traceback_text)

        def on_visualization_completed(self, payload: Dict[str, Any]) -> None:
            self.visualization_update_button.setEnabled(True)
            self._last_visualization_payload = payload
            self._refresh_animation_availability()
            if visualization_payload_exceeds_large_scene_limit(payload):
                yes, no = self._message_box_yes_no()
                result = QtWidgets.QMessageBox.question(
                    self,
                    "Render large visualization?",
                    visualization_large_scene_message(payload) + "\n\nRender anyway?",
                    yes | no,
                    no,
                )
                if result != yes:
                    self._visualization_stale = True
                    self._set_visualization_update_button_stale(True)
                    self._refresh_nodal_force_export_action()
                    geometry_text = format_section_geometry(payload.get("section_geometry"))
                    geometry_suffix = f"; {geometry_text}" if geometry_text else ""
                    self.visualization_status_label.setText(
                        f"Visualization ready{geometry_suffix}; render skipped for large scene."
                    )
                    self.append_log(
                        f"[{timestamp()}] Visualization render skipped for large scene"
                        f"{geometry_suffix}."
                    )
                    self.refresh_result_history_plot()
                    return

            counts = payload.get("counts") or {}
            self._visualization_stale = False
            render_payload = self._payload_with_current_result_overlay(payload)
            rendered = self.visualization_widget.render_payload(render_payload)
            if not rendered:
                self._visualization_stale = True
                self._set_visualization_update_button_stale(True)
                self._refresh_nodal_force_export_action()
                self.visualization_status_label.setText(
                    "Visualization payload ready, but the renderer is unavailable."
                )
                self.append_log(
                    f"[{timestamp()}] Visualization payload ready but not rendered."
                )
                self.refresh_result_history_plot()
                return
            warning_parts = []
            mesh_warning = (payload.get("mesh") or {}).get("warning")
            if mesh_warning:
                warning_parts.append("base mesh grid unavailable")
            missing_cut = payload.get("missing_cut_element_ids") or []
            if missing_cut:
                warning_parts.append(f"{len(missing_cut)} cut element(s) not mapped to cells")
            warning_parts.extend(str(item) for item in payload.get("warnings", []) if item)
            suffix = f" ({'; '.join(warning_parts)})" if warning_parts else ""
            geometry_text = format_section_geometry(payload.get("section_geometry"))
            geometry_suffix = f", {geometry_text}" if geometry_text else ""
            self._set_visualization_update_button_stale(False)
            self._refresh_nodal_force_export_action()
            status_text = (
                "Visualization updated: "
                f"{counts.get('raw_element_count', 0)} selected element(s), "
                f"{counts.get('cut_element_count', 0)} cut element(s), "
                f"{counts.get('force_summation_node_count', 0)} force node(s)"
                f"{geometry_suffix}"
                f"{suffix}{self._result_overlay_status_suffix(payload, render_payload)}"
                "."
            )
            self.visualization_status_label.setText(status_text)
            self.visualization_status_label.setToolTip(status_text)
            self.append_log(
                f"[{timestamp()}] Visualization rendered: "
                f"raw_elements={counts.get('raw_element_count')}, "
                f"cut_elements={counts.get('cut_element_count')}, "
                f"force_nodes={counts.get('force_summation_node_count')}"
                f"{'; ' + geometry_text if geometry_text else ''}."
            )
            self.refresh_result_history_plot()

        def on_visualization_failed(self, traceback_text: str) -> None:
            self.visualization_update_button.setEnabled(True)
            self._visualization_stale = True
            self._set_visualization_update_button_stale(True)
            self._refresh_nodal_force_export_action()
            self.visualization_status_label.setText("Visualization failed")
            self.refresh_result_history_plot()
            self.append_log(traceback_text)
            self._show_themed_error_dialog(
                "Visualization failed",
                "Visualization failed. The traceback was written to the run log.",
                traceback_text[-4000:],
            )

        def _set_combo_value(self, combo: Any, value: Any) -> None:
            for index in range(combo.count()):
                item_value = combo.itemData(index)
                if item_value == value or str(item_value) == str(value):
                    combo.setCurrentIndex(index)
                    return

        def _select_result_set(self, result_set_id: Optional[int]) -> None:
            if not self.result_set_combo.count():
                return
            if result_set_id is None:
                self.result_set_combo.setCurrentIndex(self.result_set_combo.count() - 1)
                return
            for index in range(self.result_set_combo.count()):
                if int(self.result_set_combo.itemData(index)) == int(result_set_id):
                    self.result_set_combo.setCurrentIndex(index)
                    return
            self.result_set_combo.setCurrentIndex(-1)

        def _refresh_result_set_options(self, options: Sequence[Dict[str, Any]]) -> None:
            current = self.result_set_combo.currentData()
            requested = self._pending_result_set_id if self._pending_result_set_id is not None else current
            self._loaded_result_sets = [dict(option) for option in options]
            self.result_set_combo.clear()
            for option in self._loaded_result_sets:
                self.result_set_combo.addItem(option["label"], int(option["id"]))
            self._select_result_set(int(requested) if requested is not None else None)
            maximum = max(
                [int(option["id"]) for option in self._loaded_result_sets] or [1]
            )
            for spin in (
                self.result_set_range_start_spin,
                self.result_set_range_end_spin,
            ):
                spin.setRange(1, maximum)
            start = self._pending_result_set_range_start or 1
            end = self._pending_result_set_range_end or maximum
            self.result_set_range_start_spin.setValue(min(maximum, max(1, int(start))))
            self.result_set_range_end_spin.setValue(min(maximum, max(1, int(end))))
            self.all_result_sets_label.setText(
                f"All {len(self._loaded_result_sets)} cumulative set(s)"
                if self._loaded_result_sets
                else "Load RST metadata"
            )
            self._refresh_animation_availability()

        def on_analysis_mode_changed(self, *, mark_stale: bool = True) -> None:
            static_mode = self.analysis_mode_combo.currentData() == "static"
            self._files_form.setRowVisible(self.static_set_scope_combo, static_mode)
            self._files_form.setRowVisible(self.mcf_row, not static_mode)
            self._reference_frame_form.setRowVisible(
                self.reference_frame_motion_combo,
                static_mode,
            )
            self._reference_frame_form.setRowVisible(
                self.reference_frame_tracking_status_label,
                static_mode,
            )
            self.modal_options_group.setVisible(not static_mode)
            self.result_set_combo.setEnabled(static_mode)
            self.mcf_row.setEnabled(not static_mode)
            self.force_type_combo.setEnabled(not static_mode)
            self.skip_first_modes_spin.setEnabled(not static_mode)
            self.modal_batch_spin.setEnabled(not static_mode)
            self.on_static_set_scope_changed(mark_stale=False)
            self.on_reference_frame_motion_changed(mark_stale=False)
            self._refresh_animation_availability()
            if mark_stale:
                self.mark_visualization_stale()

        def on_static_set_scope_changed(self, *, mark_stale: bool = True) -> None:
            static_mode = self.analysis_mode_combo.currentData() == "static"
            scope = str(self.static_set_scope_combo.currentData() or "single")
            single = static_mode and scope == "single"
            ranged = static_mode and scope == "range"
            all_sets = static_mode and scope == "all"
            self._files_form.setRowVisible(self.result_set_combo, single)
            self._files_form.setRowVisible(self.result_set_range_start_spin, ranged)
            self._files_form.setRowVisible(self.result_set_range_end_spin, ranged)
            self._files_form.setRowVisible(self.result_set_range_stride_spin, ranged)
            self._files_form.setRowVisible(self.all_result_sets_label, all_sets)
            self.result_set_combo.setEnabled(single)
            self._refresh_animation_availability()
            if mark_stale:
                self.mark_visualization_stale()

        def on_reference_frame_motion_changed(self, *, mark_stale: bool = True) -> None:
            static_mode = self.analysis_mode_combo.currentData() == "static"
            follows = (
                self.reference_frame_motion_combo.currentData() == "follow-geometry"
            )
            self.reference_frame_advanced_group.setVisible(static_mode and follows)
            self.on_reference_frame_attachment_changed(mark_stale=False)
            if mark_stale:
                self.mark_visualization_stale()

        def on_reference_frame_attachment_changed(
            self,
            *,
            mark_stale: bool = True,
        ) -> None:
            follows = (
                self.reference_frame_motion_combo.currentData() == "follow-geometry"
            )
            attachment_data = self.reference_frame_attachment_combo.currentData()
            override = (
                str(attachment_data).strip()
                if attachment_data is not None
                else self.reference_frame_attachment_combo.currentText().strip()
            )
            if not follows:
                text = "Fixed Mechanical Construction Surface scope"
            elif override:
                text = f"Attachment override: {override}"
            else:
                text = "Attachment: local section-cut neighborhood"
            self.reference_frame_tracking_status_label.setText(text)
            if mark_stale:
                self.mark_visualization_stale()

        def on_result_set_changed(self, _index: int) -> None:
            value = self.result_set_combo.currentData()
            self._pending_result_set_id = int(value) if value is not None else None
            self.mark_visualization_stale()

        def on_modal_rst_path_changed(self, _path: str) -> None:
            if not self._applying_config:
                self._pending_result_set_id = None
                self.result_set_combo.setCurrentIndex(-1)
            if self.modal_row.text():
                self.append_log(
                    f"[{timestamp()}] RST path changed; refreshing metadata."
                )
            self.refresh_modal_rst_metadata(show_errors=False)

        def on_external_selection_path_changed(self, path: str) -> None:
            if path:
                self.append_log(
                    f"[{timestamp()}] External selection path changed; "
                    "refreshing available selections."
                )
            self.refresh_named_selection_options(show_errors=False)
            self.mark_visualization_stale()

        def _set_rst_unit_indicator(
            self,
            mesh_unit: Optional[str],
            result_units: Optional[Dict[str, Optional[str]]] = None,
            *,
            state: str = "loaded",
        ) -> None:
            self.rst_unit_label.setText(
                rst_mesh_unit_indicator_text(mesh_unit, state=state)
            )
            self.rst_unit_label.setToolTip(
                rst_mesh_unit_indicator_tooltip(mesh_unit, result_units)
            )

        def refresh_modal_rst_metadata(self, show_errors: bool = False) -> None:
            modal_rst = self.modal_row.text()
            if modal_rst:
                self.append_log(f"[{timestamp()}] Load RST metadata refresh started.")
                refresh_start = perf_counter()
                try:
                    metadata = load_modal_rst_metadata(modal_rst, log=self.append_log)
                except Exception as exc:
                    self._refresh_result_set_options([])
                    self._set_rst_unit_indicator(None, state="read_failed")
                    self.append_log(f"[{timestamp()}] RST unit read failed: {exc}")
                else:
                    self._refresh_result_set_options(metadata.result_sets)
                    self._set_rst_unit_indicator(metadata.mesh_unit)
            else:
                refresh_start = None
                self._refresh_result_set_options([])
                self._set_rst_unit_indicator(None, state="not_loaded")
            self.refresh_named_selection_options(show_errors=show_errors)
            self.refresh_coordinate_system_options(show_errors=show_errors)
            if refresh_start is not None:
                self.append_log(
                    f"[{timestamp()}] Load RST metadata refresh finished in "
                    f"{format_seconds(perf_counter() - refresh_start)}."
                )

        def refresh_named_selection_options(self, show_errors: bool = False) -> None:
            modal_rst = self.modal_row.text()
            external_path = self.external_selection_row.text()
            current_name = self.element_combo.currentText().strip()
            self._loaded_element_named_selections = []
            self.element_combo.clear()
            if current_name:
                self.element_combo.setEditText(current_name)
            if not external_path and not modal_rst:
                self.status_label.setText("Load an RST to list element/body named selections")
                return

            source_label = (
                f"external export {external_path}"
                if external_path
                else "the RST"
            )
            self.append_log(
                f"[{timestamp()}] Filtering element/body named selections from "
                f"{source_label}."
            )
            QtWidgets.QApplication.setOverrideCursor(
                QtCore.Qt.CursorShape.WaitCursor
            )
            discovery_start = perf_counter()
            try:
                if external_path:
                    options = discover_external_named_selection_options(external_path)
                else:
                    options = discover_element_named_selection_options(
                        modal_rst,
                        log=self.append_log,
                    )
            except Exception as exc:
                self.status_label.setText(
                    "Could not read named selections from the external export"
                    if external_path
                    else "Could not read named selections from the RST"
                )
                self.append_log(f"[{timestamp()}] Named-selection discovery failed: {exc}")
                if show_errors:
                    self._show_themed_error_dialog(
                        "Named selection discovery failed",
                        str(exc),
                    )
                return
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()

            self.element_combo.clear()
            for option in options:
                self.element_combo.addItem(option["name"], option["name"])
            self._configure_searchable_combo(self.element_combo)
            self._loaded_element_named_selections = [option["name"] for option in options]
            attachment_current = self.reference_frame_attachment_combo.currentText().strip()
            if external_path:
                attachment_names = [str(option["name"]) for option in options]
            else:
                try:
                    attachment_names = list(
                        load_modal_rst_metadata(modal_rst).named_selection_names
                    )
                except Exception:
                    attachment_names = list(self._loaded_element_named_selections)
            self.reference_frame_attachment_combo.clear()
            self.reference_frame_attachment_combo.addItem(
                "Same as section selection (local cut neighborhood)",
                "",
            )
            for attachment_name in sorted(set(attachment_names), key=str.lower):
                self.reference_frame_attachment_combo.addItem(
                    attachment_name,
                    attachment_name,
                )
            if attachment_current:
                self.reference_frame_attachment_combo.setEditText(attachment_current)
            else:
                self.reference_frame_attachment_combo.setCurrentIndex(0)
            self._configure_searchable_combo(self.reference_frame_attachment_combo)

            default_name = SectionConfig().element_named_selection
            loaded_lower = {name.lower(): name for name in self._loaded_element_named_selections}
            if current_name and current_name.lower() in loaded_lower:
                self.element_combo.setEditText(loaded_lower[current_name.lower()])
            elif self._loaded_element_named_selections and (
                external_path or not current_name or current_name == default_name
            ):
                self.element_combo.setEditText(self._loaded_element_named_selections[0])
            elif current_name:
                self.element_combo.setEditText(current_name)

            if self._loaded_element_named_selections:
                source_kind = "external" if external_path else "RST"
                self.status_label.setText(
                    "Loaded "
                    f"{len(self._loaded_element_named_selections)} named selection "
                    f"name(s) from the {source_kind} selection source"
                )
                self.append_log(
                    f"[{timestamp()}] Named-selection dropdown updated in "
                    f"{format_seconds(perf_counter() - discovery_start)}; "
                    f"{len(self._loaded_element_named_selections)} item(s), "
                    f"selected={self.element_combo.currentText()!r}."
                )
            else:
                self.status_label.setText(
                    "No non-empty NODE/ELEMENT selections were found in the external export"
                    if external_path
                    else "No non-empty element/body named selections were found in the RST"
                )
                self.append_log(
                    f"[{timestamp()}] Named-selection filtering finished in "
                    f"{format_seconds(perf_counter() - discovery_start)}; no usable names found."
                )

        def refresh_coordinate_system_options(
            self,
            show_errors: bool = False,
            *,
            include_dpf_scan: bool = False,
        ) -> None:
            modal_rst = self.modal_row.text()
            current_text = self.coordinate_system_combo.currentText().strip()
            current_origin, current_axes = self.current_coordinate_system_fields()

            self._loaded_coordinate_system_options = []
            self.coordinate_system_combo.clear()
            self.coordinate_system_combo.addItem(MANUAL_COORDINATE_SYSTEM_LABEL, None)
            if not modal_rst:
                self._configure_searchable_combo(self.coordinate_system_combo)
                return

            mode_label = "DPF coordinate-system scan" if include_dpf_scan else "metadata coordinate-system read"
            self.append_log(f"[{timestamp()}] Starting {mode_label}.")
            QtWidgets.QApplication.setOverrideCursor(
                QtCore.Qt.CursorShape.WaitCursor
            )
            discovery_start = perf_counter()
            try:
                options = discover_coordinate_system_options(
                    modal_rst,
                    include_dpf_scan=include_dpf_scan,
                    log=self.append_log,
                )
            except Exception as exc:
                self.status_label.setText("Could not read coordinate systems from modal RST")
                self.append_log(f"[{timestamp()}] Coordinate-system discovery failed: {exc}")
                if show_errors:
                    self._show_themed_error_dialog(
                        "Coordinate system discovery failed",
                        str(exc),
                    )
                return
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()

            for option in options:
                self.coordinate_system_combo.addItem(option["label"], option)
            self._configure_searchable_combo(self.coordinate_system_combo)
            self._loaded_coordinate_system_options = options

            selected_index = 0
            if current_origin is not None and current_axes is not None:
                for index, option in enumerate(options, start=1):
                    if self.coordinate_system_matches(option, current_origin, current_axes):
                        selected_index = index
                        break
            if selected_index == 0 and current_text:
                for index in range(self.coordinate_system_combo.count()):
                    label = self.coordinate_system_combo.itemText(index)
                    option = self.coordinate_system_combo.itemData(index)
                    if (
                        current_text.lower() == label.lower()
                        or (
                            isinstance(option, dict)
                            and current_text.lower()
                            in {
                                str(option.get("id", "")).lower(),
                                str(option.get("name", "")).lower(),
                                str(option.get("apdl_name", "")).lower(),
                            }
                        )
                    ):
                        selected_index = index
                        break
            self.coordinate_system_combo.setCurrentIndex(selected_index)
            if options:
                source = "DPF scan" if include_dpf_scan else "metadata"
                self.status_label.setText(
                    f"Loaded {len(options)} coordinate system(s) from modal RST {source}"
                )
                self.append_log(
                    f"[{timestamp()}] Coordinate-system dropdown updated in "
                    f"{format_seconds(perf_counter() - discovery_start)}; "
                    f"{len(options)} option(s), source={source}, "
                    f"selected={self.coordinate_system_combo.currentText()!r}."
                )
            else:
                self.append_log(
                    f"[{timestamp()}] Coordinate-system read finished in "
                    f"{format_seconds(perf_counter() - discovery_start)}; no options found."
                )

        def scan_dpf_coordinate_systems(self) -> None:
            self.append_log(
                f"[{timestamp()}] Manual DPF coordinate-system scan requested."
            )
            self.refresh_coordinate_system_options(
                show_errors=True,
                include_dpf_scan=True,
            )

        def current_coordinate_system_fields(
            self,
        ) -> Tuple[Optional[Vector], Optional[Dict[str, Vector]]]:
            try:
                origin = self.read_vector(self.origin_edits, "Origin [mm]")
                axes = {
                    axis_name: self.read_vector(edits, f"Local {axis_name.upper()} axis")
                    for axis_name, edits in self.axis_edits.items()
                }
            except Exception:
                return None, None
            return origin, axes

        def coordinate_system_matches(
            self,
            option: Dict[str, Any],
            origin: Vector,
            axes: Dict[str, Vector],
        ) -> bool:
            option_origin = (
                coordinate_system_origin_for_gui_units(option)
                if len(option.get("origin") or []) >= 3
                else []
            )
            option_axes = option.get("axes") or {}
            if len(option_origin) < 3:
                return False
            origin_scale = max(1.0, max(abs(float(value)) for value in origin + option_origin[:3]))
            if any(
                abs(float(origin[index]) - float(option_origin[index])) > 1.0e-6 * origin_scale
                for index in range(3)
            ):
                return False
            for axis_name in ("x", "y", "z"):
                axis = axes.get(axis_name) or []
                option_axis = option_axes.get(axis_name) or []
                if len(axis) < 3 or len(option_axis) < 3:
                    return False
                if any(
                    abs(float(axis[index]) - float(option_axis[index])) > 1.0e-6
                    for index in range(3)
                ):
                    return False
            return True

        def apply_coordinate_system_index(self, index: int) -> None:
            option = self.coordinate_system_combo.itemData(index)
            if not isinstance(option, dict):
                return
            origin = (
                coordinate_system_origin_for_gui_units(option)
                if len(option.get("origin") or []) >= 3
                else []
            )
            axes = option.get("axes") or {}
            if len(origin) >= 3:
                for edit, value in zip(self.origin_edits, origin[:3]):
                    edit.setText(f"{float(value):.12g}")
            for axis_name, edits in self.axis_edits.items():
                axis = axes.get(axis_name) or []
                if len(axis) >= 3:
                    for edit, value in zip(edits, axis[:3]):
                        edit.setText(f"{float(value):.12g}")
            label = self.coordinate_system_combo.itemText(index)
            self.status_label.setText(f"Applied coordinate system: {label}")
            self.append_log(f"[{timestamp()}] Applied coordinate system: {label}")

        def read_vector(self, edits: Sequence[Any], label: str) -> Vector:
            try:
                return [float(edit.text().strip()) for edit in edits]
            except ValueError as exc:
                raise ValueError(f"{label} contains a non-numeric value.") from exc

        def selected_element_named_selection(self) -> str:
            name = self.element_combo.currentText().strip()
            if self._loaded_element_named_selections:
                loaded_lower = {item.lower() for item in self._loaded_element_named_selections}
                if name.lower() not in loaded_lower:
                    source = (
                        "external export"
                        if self.external_selection_row.text()
                        else "RST"
                    )
                    raise ValueError(
                        f"Choose an element/body named selection from the {source} dropdown. "
                        f"{name!r} is not one of the filtered usable named selections."
                    )
            return name

        def collect_config(self) -> SectionConfig:
            axes = {
                axis_name: self.read_vector(edits, f"Local {axis_name.upper()} axis")
                for axis_name, edits in self.axis_edits.items()
            }
            analysis_mode = str(self.analysis_mode_combo.currentData() or "modal")
            static_set_scope = str(
                self.static_set_scope_combo.currentData() or "single"
            )
            result_set_id = self.result_set_combo.currentData()
            if (
                analysis_mode == "static"
                and static_set_scope == "single"
                and result_set_id is None
            ):
                raise ValueError(
                    "Load RST metadata and choose one cumulative static result-set ID."
                )
            range_start = int(self.result_set_range_start_spin.value())
            range_end = int(self.result_set_range_end_spin.value())
            if (
                analysis_mode == "static"
                and static_set_scope == "range"
                and range_start > range_end
            ):
                raise ValueError("Static result-set Start set must not exceed End set.")
            return config_from_mapping(
                {
                    "analysis_mode": analysis_mode,
                    "static_set_scope": static_set_scope,
                    "result_set_id": (
                        int(result_set_id) if result_set_id is not None else None
                    ),
                    "result_set_range_start": range_start,
                    "result_set_range_end": range_end,
                    "result_set_range_stride": int(
                        self.result_set_range_stride_spin.value()
                    ),
                    "modal_rst": self.modal_row.text(),
                    "mcf": self.mcf_row.text(),
                    "out_csv": self.out_row.text(),
                    "external_named_selection_path": self.external_selection_row.text(),
                    "element_named_selection": self.selected_element_named_selection(),
                    "coordinate_system_origin": self.read_vector(self.origin_edits, "Origin [mm]"),
                    "coordinate_system_axes": axes,
                    "reference_frame_motion": str(
                        self.reference_frame_motion_combo.currentData()
                        or "follow-geometry"
                    ),
                    "reference_frame_attachment_selection": (
                        str(self.reference_frame_attachment_combo.currentData()).strip()
                        if self.reference_frame_attachment_combo.currentData() is not None
                        else self.reference_frame_attachment_combo.currentText().strip()
                    ),
                    "reference_frame_fit_warning_ratio": (
                        float(self.reference_frame_fit_warning_spin.value()) / 100.0
                    ),
                    "section_normal_axis": str(self.normal_combo.currentData()),
                    "extraction_side": str(self.side_combo.currentData()),
                    "moment_reference_mode": str(self.moment_combo.currentData()),
                    "side_filter_tolerance": float(self.tolerance_edit.text().strip()),
                    "force_type": (
                        MECHANICAL_PROBE_FORCE_TYPE
                        if analysis_mode == "static"
                        else int(self.force_type_combo.currentData())
                    ),
                    "skip_first_modes": int(self.skip_first_modes_spin.value()),
                    "modal_summation_batch_size": int(self.modal_batch_spin.value()),
                }
            )

        def append_log(self, message: str) -> None:
            self.log.appendPlainText(message)
            scrollbar = self.log.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            QtWidgets.QApplication.processEvents()

        def export_current_nodal_forces(self) -> None:
            payload = self._current_nodal_force_export_payload()
            if payload is None:
                self._show_themed_error_dialog(
                    "Nodal force export unavailable",
                    "Run extraction and update the 3D visualization before exporting nodal forces.",
                )
                self._refresh_nodal_force_export_action()
                return
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Export nodal forces",
                self._default_nodal_force_export_path(),
                "CSV files (*.csv);;All files (*)",
            )
            if not path:
                return
            try:
                write_nodal_force_time_csv(path, payload)
            except Exception as exc:
                self._show_themed_error_dialog("Nodal force export failed", str(exc))
                return
            self.append_log(
                f"[{timestamp()}] Nodal force CSV written: {path} "
                f"({len(payload.get('rows') or [])} node(s), "
                f"t={float(payload.get('time', 0.0)):.6g} s)."
            )

        def export_current_nodal_forces_excel(self) -> None:
            payload = build_nodal_force_time_excel_payload(
                self._last_visualization_result_data,
                self._current_visualization_time_index(),
            )
            if (
                payload is None
                or self._last_visualization_payload is None
                or self._visualization_stale
                or not result_signature_matches_visualization(
                    self._last_visualization_result_data,
                    self._last_visualization_payload,
                    self._current_visualization_time_index(),
                )
            ):
                self._show_themed_error_dialog(
                    "Nodal force Excel export unavailable",
                    "Run extraction and update the 3D visualization before exporting nodal forces.",
                )
                self._refresh_nodal_force_export_action()
                return
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Export nodal forces and local moments Excel",
                self._default_nodal_force_excel_export_path(),
                "Excel workbooks (*.xlsx);;All files (*)",
            )
            if not path:
                return
            try:
                write_nodal_force_time_excel(path, payload)
            except Exception as exc:
                self._show_themed_error_dialog("Nodal force Excel export failed", str(exc))
                return
            self.append_log(
                f"[{timestamp()}] Nodal force/local moment Excel written: {path} "
                f"({len(payload.get('rows') or [])} node(s), "
                f"t={float(payload.get('time', 0.0)):.6g} s)."
            )

        def run_extraction(self) -> None:
            try:
                cfg = self.collect_config()
            except Exception as exc:
                self.append_log(f"[{timestamp()}] Settings validation failed: {exc}")
                self._show_themed_error_dialog("Invalid settings", str(exc))
                return
            self._invalidate_animation_session()
            self.append_log(f"[{timestamp()}] ---- Extraction started ----")
            details = (
                f"set_scope={cfg.static_set_scope}, result_set_id={cfg.result_set_id}, "
                f"range={cfg.result_set_range_start}:{cfg.result_set_range_end}:"
                f"{cfg.result_set_range_stride}, frame_motion={cfg.reference_frame_motion}, "
                f"force_type={MECHANICAL_PROBE_FORCE_TYPE}"
                if cfg.analysis_mode == "static"
                else f"force_type={cfg.force_type}, skip_first_modes={cfg.skip_first_modes}, modal_batch_size={cfg.modal_summation_batch_size}"
            )
            self.append_log(
                f"[{timestamp()}] Queued {cfg.analysis_mode} extraction for "
                f"named_selection={cfg.element_named_selection!r}, side={cfg.extraction_side}, "
                f"normal={cfg.section_normal_axis}, {details}."
            )
            self.status_label.setText("Running")
            self.run_button.setEnabled(False)
            self.worker = ExtractionThread(cfg)
            self.worker.log_message.connect(self.append_log)
            self.worker.completed.connect(self.on_completed)
            self.worker.failed.connect(self.on_failed)
            self.worker.start()

        def on_completed(self, summary: Dict[str, Any]) -> None:
            self.run_button.setEnabled(True)
            self._last_visualization_result_data = summary.get("_visualization_result_data")
            self._set_visualization_result_times(self._last_visualization_result_data)
            animation_session = summary.get("_animation_session")
            if isinstance(animation_session, StaticAnimationSession):
                try:
                    current_config = self.collect_config()
                    selected_sets = self._animation_selected_result_sets()
                    expected_signature = static_animation_session_signature(
                        current_config,
                        selected_sets,
                    )
                except Exception:
                    expected_signature = None
                if (
                    expected_signature is not None
                    and animation_session.signature == expected_signature
                    and len(animation_session.records) >= 2
                ):
                    self._adopt_animation_session(animation_session)
                    self._animation_signature = expected_signature
                elif not animation_session.closed:
                    animation_session.close()
            self._refresh_animation_availability()
            if self._animation_session is not None:
                self._set_animation_exact_index(
                    self._current_visualization_time_index(),
                    render=True,
                )
            local = summary.get("max_abs_resultant_local", {})
            timings = summary.get("timings", {})
            dpf_info = summary.get("dpf_force_summation", {})
            self._set_rst_unit_indicator(
                dpf_info.get("mesh_unit"),
                summary.get("result_units") or {},
            )
            self.status_label.setText(
                "Done: "
                f"Fx {local.get('fx', 0.0):.6g}, "
                f"My {local.get('my', 0.0):.6g}"
            )
            self.append_log(
                f"[{timestamp()}] Extraction timing: metadata="
                f"{format_seconds(timings.get('metadata_load_seconds') or 0.0)}, "
                f"MCF parse={format_seconds(timings.get('mcf_parse_seconds') or 0.0)}, "
                f"DPF phase={format_seconds(timings.get('dpf_force_summation_seconds') or 0.0)}, "
                f"multiply={format_seconds(timings.get('modal_multiplication_seconds') or 0.0)}, "
                f"total={format_seconds(timings.get('total_seconds') or 0.0)}."
            )
            self.append_log(
                f"[{timestamp()}] Extraction scope: raw_elements="
                f"{dpf_info.get('raw_element_count')}, cut_elements="
                f"{dpf_info.get('element_count')}, side_nodes="
                f"{dpf_info.get('surface_node_count')}, modes="
                f"{summary.get('modes_evaluated')}, modal_batches="
                f"{summary.get('modal_summation_batch_count')}."
            )
            section_geometry_text = format_section_geometry(
                dpf_info.get("section_geometry")
            )
            if section_geometry_text:
                self.append_log(
                    f"[{timestamp()}] Section geometry: {section_geometry_text}."
                )
            self.append_log(f"[{timestamp()}] CSV: {summary.get('out_csv')}")
            self.append_log(f"[{timestamp()}] Summary: {summary.get('summary_json')}")
            if self._last_visualization_result_data:
                if self._visualization_stale:
                    self.visualization_status_label.setText(
                        "Extraction vectors and history ready; update visualization to show them."
                    )
                    self.refresh_result_history_plot()
                elif self._last_visualization_payload is not None:
                    self.refresh_result_overlay_render()
            else:
                self.visualization_status_label.setText(
                    "Extraction finished; result vectors/history are unavailable for this run."
                )
                self.refresh_result_history_plot()

        def on_failed(self, error_text: str, traceback_text: str) -> None:
            self.run_button.setEnabled(True)
            self.status_label.setText("Failed")
            self.append_log(traceback_text)
            self._show_themed_error_dialog(
                "Extraction failed",
                error_text or "Extraction failed. See Details and the run log.",
                traceback_text[-4000:],
            )

        def load_config(self) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Load config", "", "JSON files (*.json);;All files (*)"
            )
            if not path:
                return
            try:
                include_modal_rst = self.load_modal_rst_from_config_checkbox.isChecked()
                cfg = load_config(
                    path,
                    include_modal_rst=include_modal_rst,
                    current_modal_rst=self.modal_row.text(),
                )
                self.set_config(cfg)
                if not include_modal_rst:
                    self.append_log(
                        f"[{timestamp()}] Loaded config without changing Modal RST path."
                    )
            except Exception as exc:
                self._show_themed_error_dialog("Load failed", str(exc))

        def save_config(self) -> None:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save config", "", "JSON files (*.json);;All files (*)"
            )
            if not path:
                return
            try:
                save_config(path, self.collect_config())
            except Exception as exc:
                self._show_themed_error_dialog("Save failed", str(exc))

        def open_output_folder(self) -> None:
            out_csv = self.out_row.text()
            if not out_csv:
                return
            folder = str(Path(out_csv).expanduser().resolve().parent)
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))

        def closeEvent(self, event: Any) -> None:  # noqa: N802
            self.pause_static_animation()
            worker = self.animation_worker
            if worker is not None and worker.isRunning():
                worker.cancel()
                if not worker.wait(5000):
                    event.ignore()
                    self.visualization_status_label.setText(
                        "Stopping animation loader after its current DPF batch..."
                    )
                    if not self._closing_after_animation:
                        self._closing_after_animation = True
                        worker.finished.connect(self.close)
                    return
            session = self._animation_session
            self._animation_session = None
            if session is not None and not session.closed:
                session.close()
            self.visualization_widget.close()
            super().closeEvent(event)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = MainWindow(initial_config or SectionConfig())
    app._mcf_dpf_section_resultants_window = window
    window.showMaximized()
    QtCore.QTimer.singleShot(0, window.apply_visualization_default_width)
    return app.exec()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.cli or args.write_default_config:
        return run_cli(args)
    initial_config = load_config(args.config) if args.config else SectionConfig()
    if (
        args.modal_rst
        or args.mcf
        or args.out_csv
        or args.element_named_selection
        or args.origin
        or args.analysis_mode
        or args.result_set_id is not None
        or args.static_set_scope
        or args.result_set_start is not None
        or args.result_set_end is not None
        or args.result_set_stride is not None
        or args.reference_frame_motion
        or args.reference_frame_attachment is not None
        or args.frame_fit_warning_ratio is not None
    ):
        initial_config = config_from_args(args)
    return run_gui(initial_config)


if __name__ == "__main__":
    raise SystemExit(main())
