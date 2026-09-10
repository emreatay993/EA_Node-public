from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCursor, QIcon, QKeySequence, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .analysis_tables import AnalysisTable


ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def asset_icon(filename: str) -> QIcon:
    return QIcon(str(ASSETS_DIR / filename))


class DataFrameTableModel(QAbstractTableModel):
    def __init__(self, frame: pd.DataFrame | None = None):
        super().__init__()
        self._frame = frame.copy() if frame is not None else pd.DataFrame()

    @property
    def frame(self) -> pd.DataFrame:
        return self._frame

    def set_frame(self, frame: pd.DataFrame) -> None:
        self.beginResetModel()
        self._frame = frame.copy()
        self.endResetModel()

    def rowCount(self, _parent: QModelIndex = QModelIndex()) -> int:
        return int(len(self._frame))

    def columnCount(self, _parent: QModelIndex = QModelIndex()) -> int:
        return int(len(self._frame.columns))

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        value = self._frame.iat[index.row(), index.column()]
        if role in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole}:
            return self._display_value(value)
        if role == Qt.ItemDataRole.TextAlignmentRole and self._is_numeric_value(value):
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._frame.columns):
                return str(self._frame.columns[section])
            return None
        return str(section + 1)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if column < 0 or column >= len(self._frame.columns):
            return
        column_name = self._frame.columns[column]
        ascending = order == Qt.SortOrder.AscendingOrder
        self.layoutAboutToBeChanged.emit()
        try:
            self._frame = self._frame.sort_values(column_name, ascending=ascending, kind="mergesort", na_position="last")
        except TypeError:
            helper = self._frame[column_name].map(lambda value: "" if pd.isna(value) else str(value))
            self._frame = self._frame.assign(_sort_helper=helper).sort_values(
                "_sort_helper",
                ascending=ascending,
                kind="mergesort",
                na_position="last",
            ).drop(columns=["_sort_helper"])
        self._frame = self._frame.reset_index(drop=True)
        self.layoutChanged.emit()

    @staticmethod
    def _display_value(value: object) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, float):
            return f"{value:.12g}"
        return str(value)

    @staticmethod
    def _is_numeric_value(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)


class SpreadsheetTableView(QTableView):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._table: AnalysisTable | None = None
        self._model = DataFrameTableModel()
        self.setModel(self._model)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSortingEnabled(True)
        self.setShowGrid(True)
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.horizontalHeader().setSectionsMovable(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.verticalHeader().setDefaultSectionSize(24)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    @property
    def table(self) -> AnalysisTable | None:
        return self._table

    def set_table(self, table: AnalysisTable | None) -> None:
        self._table = table
        self._model.set_frame(table.frame if table is not None else pd.DataFrame())
        self.resizeColumnsToContents()

    def selected_values(self, column_name: str) -> list[str]:
        frame = self._model.frame
        if column_name not in frame.columns:
            return []
        column_index = frame.columns.get_loc(column_name)
        values: list[str] = []
        for row in sorted({index.row() for index in self.selectedIndexes()}):
            if row < 0 or row >= len(frame):
                continue
            value = frame.iat[row, column_index]
            if pd.isna(value):
                continue
            text = str(value)
            if text not in values:
                values.append(text)
        return values

    def keyPressEvent(self, event: Any) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection(include_headers=False)
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.selectAll()
            return
        super().keyPressEvent(event)

    def copy_selection(self, *, include_headers: bool = False) -> str:
        indexes = self.selectedIndexes()
        if not indexes:
            return ""
        rows = sorted({index.row() for index in indexes})
        columns = sorted({index.column() for index in indexes})
        selected = {(index.row(), index.column()) for index in indexes}
        lines: list[str] = []
        if include_headers:
            lines.append("\t".join(str(self._model.headerData(column, Qt.Orientation.Horizontal)) for column in columns))
        for row in rows:
            values = []
            for column in columns:
                value = self._model.data(self._model.index(row, column), Qt.ItemDataRole.DisplayRole) if (row, column) in selected else ""
                values.append(str(value or ""))
            lines.append("\t".join(values))
        text = "\n".join(lines)
        QApplication.clipboard().setText(text)
        return text

    def _show_context_menu(self, position: Any) -> None:
        menu = QMenu(self)
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(lambda: self.copy_selection(include_headers=False))
        copy_headers_action = QAction("Copy with Headers", self)
        copy_headers_action.triggered.connect(lambda: self.copy_selection(include_headers=True))
        select_all_action = QAction("Select All", self)
        select_all_action.triggered.connect(self.selectAll)
        menu.addAction(copy_action)
        menu.addAction(copy_headers_action)
        menu.addSeparator()
        menu.addAction(select_all_action)
        menu.exec(self.viewport().mapToGlobal(position))


def panel_frame() -> QFrame:
    frame = QFrame()
    frame.setObjectName("Panel")
    frame.setFrameShape(QFrame.Shape.NoFrame)
    return frame


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def muted_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("MutedLabel")
    label.setWordWrap(True)
    return label


def table_handle_button(filename: str, tooltip: str, accessible_name: str) -> QPushButton:
    button = QPushButton()
    button.setIcon(asset_icon(filename))
    button.setIconSize(QSize(13, 13))
    button.setFixedSize(28, 26)
    button.setProperty("tableHandle", "true")
    button.setToolTip(tooltip)
    button.setAccessibleName(accessible_name)
    return button


def pane_handle_button(filename: str, tooltip: str, accessible_name: str, theme: str = "panel") -> QPushButton:
    button = QPushButton()
    button.setIcon(asset_icon(filename))
    button.setIconSize(QSize(14, 14))
    button.setFixedSize(28, 26)
    button.setProperty("paneHandle", "true")
    button.setProperty("paneTheme", theme)
    button.setToolTip(tooltip)
    button.setAccessibleName(accessible_name)
    return button


def pane_header(title: str, collapse_button: QPushButton) -> QWidget:
    header = QWidget()
    header.setObjectName("PaneHeader")
    layout = QHBoxLayout(header)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(section_title(title))
    layout.addStretch(1)
    layout.addWidget(collapse_button)
    return header


class CollapsedPaneHandle(QFrame):
    restore_requested = pyqtSignal()

    def __init__(
        self,
        title: str,
        tooltip: str,
        accessible_name: str,
        *,
        theme: str = "panel",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._title = title
        self._theme = theme
        self._hovered = False
        self._pressed = False
        self.setObjectName("CollapsedPaneHandle")
        self.setFixedSize(30, max(132, len(title) * 10 + 54))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setAccessibleName(accessible_name)
        self.setMouseTracking(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

    def enterEvent(self, event: Any) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(event.position().toPoint()):
                self.restore_requested.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: Any) -> None:
        palette = self._colors()
        background = palette["pressed"] if self._pressed else palette["hover" if self._hovered else "background"]
        border = palette["border_hover"] if self._hovered or self._pressed else palette["border"]

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QColor(border))
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect, 10, 10)
        edge_rect = QRect(rect.left(), rect.top(), 9, rect.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRect(edge_rect)

        painter.setPen(QColor(palette["foreground"]))
        font = painter.font()
        font.setBold(True)
        chevron_pen = QPen(QColor(palette["foreground"]), 2)
        chevron_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        chevron_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(chevron_pen)
        center_x = self.width() // 2
        painter.drawLine(center_x - 3, 10, center_x + 3, 15)
        painter.drawLine(center_x + 3, 15, center_x - 3, 20)

        painter.save()
        painter.translate(self.width() / 2, self.height() / 2 + 12)
        painter.rotate(90)
        label_rect = QRect(-self.height() // 2, -8, self.height(), 18)
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self._title)
        painter.restore()

    def _colors(self) -> dict[str, str]:
        if self._theme == "sidebar":
            return {
                "background": "#223141",
                "hover": "#2b3c4f",
                "pressed": "#36506a",
                "border": "#405369",
                "border_hover": "#7fa6d4",
                "foreground": "#f4f7fb",
            }
        return {
            "background": "#ffffff",
            "hover": "#f7fbff",
            "pressed": "#e8f2ff",
            "border": "#b8c4d1",
            "border_hover": "#7fa6d4",
            "foreground": "#263545",
        }


class CollapsedPaneRail(QFrame):
    reveal_changed = pyqtSignal(bool)

    EDGE_REVEAL_WIDTH = 8
    HANDLE_WIDTH = 30
    TAB_TOP_MARGIN = 112

    def __init__(
        self,
        title: str,
        tooltip: str,
        accessible_name: str,
        *,
        theme: str,
        restore_callback: Callable[[], None],
        overlay_parent: QWidget | None = None,
        tab_top_margin: int | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._revealed = False
        self._tab_top_margin = self.TAB_TOP_MARGIN if tab_top_margin is None else int(tab_top_margin)
        self.setObjectName("CollapsedPaneRail")
        self.setProperty("railTheme", theme)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setFixedWidth(self.EDGE_REVEAL_WIDTH)
        self.handle = CollapsedPaneHandle(title, tooltip, accessible_name, theme=theme, parent=overlay_parent or self)
        self.handle.installEventFilter(self)
        self.handle.restore_requested.connect(restore_callback)
        self.handle.hide()

    def enterEvent(self, event: Any) -> None:
        self.set_revealed(True)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self._schedule_conceal()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._revealed:
            self.set_revealed(True)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def moveEvent(self, event: Any) -> None:
        self._position_handle()
        super().moveEvent(event)

    def resizeEvent(self, event: Any) -> None:
        self._position_handle()
        super().resizeEvent(event)

    def eventFilter(self, watched: Any, event: QEvent) -> bool:
        if watched is self.handle:
            if event.type() == QEvent.Type.Enter:
                self.set_revealed(True)
            elif event.type() == QEvent.Type.Leave:
                self._schedule_conceal()
        return super().eventFilter(watched, event)

    def set_revealed(self, revealed: bool) -> None:
        revealed = bool(revealed)
        if self._revealed == revealed:
            if revealed:
                self._position_handle()
            return
        self._revealed = revealed
        self.setFixedWidth(self.EDGE_REVEAL_WIDTH)
        if revealed:
            self._position_handle()
            self.handle.show()
            self.handle.raise_()
        else:
            self.handle.hide()
        self.reveal_changed.emit(revealed)

    def conceal(self) -> None:
        self.set_revealed(False)

    def _position_handle(self) -> None:
        parent = self.handle.parentWidget()
        if parent is None:
            return
        global_pos = self.mapToGlobal(QPoint(0, self._tab_top_margin))
        self.handle.move(parent.mapFromGlobal(global_pos))

    def _schedule_conceal(self) -> None:
        QTimer.singleShot(90, self._conceal_if_cursor_left)

    def _conceal_if_cursor_left(self) -> None:
        if self._cursor_inside(self) or self._cursor_inside(self.handle):
            return
        self.conceal()

    @staticmethod
    def _cursor_inside(widget: QWidget) -> bool:
        if widget.isHidden():
            return False
        local_pos = widget.mapFromGlobal(QCursor.pos())
        return widget.rect().contains(local_pos)


def collapsed_pane_rail(
    title: str,
    tooltip: str,
    accessible_name: str,
    *,
    theme: str,
    restore_callback: Callable[[], None],
    overlay_parent: QWidget | None = None,
    tab_top_margin: int | None = None,
) -> tuple[CollapsedPaneRail, CollapsedPaneHandle]:
    rail = CollapsedPaneRail(
        title,
        tooltip,
        accessible_name,
        theme=theme,
        restore_callback=restore_callback,
        overlay_parent=overlay_parent,
        tab_top_margin=tab_top_margin,
    )
    return rail, rail.handle


class CollapsedTableHandle(QPushButton):
    def __init__(self, title: str, tooltip: str, accessible_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._title = title
        self._hovered = False
        self._icon = asset_icon("chevron-up.svg")
        self.setObjectName("CollapsedTableHandle")
        self.setText("")
        self.setFixedHeight(30)
        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setAccessibleName(accessible_name)
        self.setMouseTracking(True)

    def enterEvent(self, event: Any) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: Any) -> None:
        background = "#e8f2ff" if self.isDown() else ("#f7fbff" if self._hovered else "#ffffff")
        border = "#7fa6d4" if self._hovered or self.isDown() else "#d3dce7"
        foreground = "#263545"

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QColor(border))
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect, 9, 9)

        font = painter.font()
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(self._title)
        cluster_width = 18 + 8 + text_width
        start_x = max(12, (self.width() - cluster_width) // 2)
        icon_rect = QRect(start_x, (self.height() - 14) // 2, 14, 14)
        self._icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)
        painter.setPen(QColor(foreground))
        text_rect = QRect(start_x + 26, 0, max(0, self.width() - start_x - 38), self.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._title)


class CollapsibleTableSection(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str,
        table_view: SpreadsheetTableView,
        *,
        controls: Sequence[QWidget] = (),
        framed: bool = True,
        table_min_height: int | None = None,
        table_max_height: int | None = None,
        table_stretch: bool = False,
    ):
        super().__init__()
        self.table_collapsed = False
        self.table_view = table_view
        self.table_panel = panel_frame() if framed else QWidget()
        self.table_panel.setObjectName("Panel" if framed else "PlainTablePanel")
        panel_layout = QVBoxLayout(self.table_panel)
        panel_layout.setContentsMargins(12, 10, 12, 12)
        panel_layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(section_title(title))
        header.addStretch(1)
        for control in controls:
            header.addWidget(control)
        self.collapse_button = table_handle_button("chevron-down.svg", f"Collapse {title}", f"Collapse {title}")
        self.collapse_button.clicked.connect(self.collapse_table)
        header.addWidget(self.collapse_button)
        panel_layout.addLayout(header)
        panel_layout.addWidget(muted_label(subtitle))
        if table_min_height is not None:
            self.table_view.setMinimumHeight(table_min_height)
        if table_max_height is not None:
            self.table_view.setMaximumHeight(table_max_height)
        panel_layout.addWidget(self.table_view, 1 if table_stretch else 0)

        self.collapsed_handle = CollapsedTableHandle(title, f"Show {title}", f"Show {title}")
        self.collapsed_handle.clicked.connect(self.expand_table)
        self.collapsed_handle.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.table_panel, 1 if table_stretch else 0)
        layout.addWidget(self.collapsed_handle)

    def collapse_table(self) -> None:
        if self.table_collapsed:
            return
        self.table_panel.hide()
        self.collapsed_handle.show()
        self.table_collapsed = True

    def expand_table(self) -> None:
        if not self.table_collapsed:
            return
        self.collapsed_handle.hide()
        self.table_panel.show()
        self.table_collapsed = False

    def toggle_table(self) -> None:
        if self.table_collapsed:
            self.expand_table()
        else:
            self.collapse_table()


class PlotTablePanel(QWidget):
    DEFAULT_TABLE_HEIGHT = 210

    def __init__(self, plot_widget: QWidget, title: str, subtitle: str, *, controls: Sequence[QWidget] = ()):
        super().__init__()
        self.plot = plot_widget
        self.table_view = SpreadsheetTableView()
        self._expanded_table_height = self.DEFAULT_TABLE_HEIGHT
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.plot.setMinimumHeight(240)
        self.splitter.addWidget(self.plot)
        self.table_section = CollapsibleTableSection(
            title,
            subtitle,
            self.table_view,
            controls=controls,
            table_min_height=150,
        )
        self.splitter.addWidget(self.table_section)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([640, self.DEFAULT_TABLE_HEIGHT])
        layout.addWidget(self.splitter, 1)

    @property
    def table_collapsed(self) -> bool:
        return self.table_section.table_collapsed

    def collapse_table(self) -> None:
        sizes = self.splitter.sizes()
        if len(sizes) > 1 and sizes[1] > 34:
            self._expanded_table_height = sizes[1]
        self.table_section.collapse_table()
        total = max(sum(self.splitter.sizes()), 640)
        self.splitter.setSizes([max(1, total - 34), 34])

    def expand_table(self) -> None:
        self.table_section.expand_table()
        total = max(sum(self.splitter.sizes()), self._expanded_table_height + 320)
        table_height = max(150, self._expanded_table_height)
        self.splitter.setSizes([max(1, total - table_height), table_height])

    def toggle_table(self) -> None:
        if self.table_collapsed:
            self.expand_table()
        else:
            self.collapse_table()

    def set_figure(self, figure: Any) -> None:
        setter = getattr(self.plot, "set_figure", None)
        if callable(setter):
            setter(figure)

    def refresh_plot(self) -> None:
        refresher = getattr(self.plot, "refresh_plot", None)
        if callable(refresher):
            refresher()

    def force_refresh_plot(self) -> None:
        force_refresher = getattr(self.plot, "force_refresh_plot", None)
        if callable(force_refresher):
            force_refresher()
            return
        self.refresh_plot()

    def set_table(self, table: AnalysisTable | None) -> None:
        self.table_view.set_table(table)

    def current_table(self) -> AnalysisTable | None:
        return self.table_view.table


class StandaloneTablePanel(QWidget):
    def __init__(self, title: str, subtitle: str):
        super().__init__()
        self.table_view = SpreadsheetTableView()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.table_section = CollapsibleTableSection(
            title,
            subtitle,
            self.table_view,
            framed=False,
            table_stretch=True,
        )
        layout.addWidget(self.table_section, 1)

    @property
    def table_collapsed(self) -> bool:
        return self.table_section.table_collapsed

    def collapse_table(self) -> None:
        self.table_section.collapse_table()

    def expand_table(self) -> None:
        self.table_section.expand_table()

    def toggle_table(self) -> None:
        if self.table_collapsed:
            self.expand_table()
        else:
            self.collapse_table()

    def set_table(self, table: AnalysisTable | None) -> None:
        self.table_view.set_table(table)

    def refresh_plot(self) -> None:
        return

    def force_refresh_plot(self) -> None:
        return

    def current_table(self) -> AnalysisTable | None:
        return self.table_view.table


class SelectableTablesView(QWidget):
    def __init__(self, title: str, subtitle: str):
        super().__init__()
        self._tables: tuple[AnalysisTable, ...] = ()
        self.combo = QComboBox()
        self.table_view = SpreadsheetTableView()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.table_section = CollapsibleTableSection(
            title,
            subtitle,
            self.table_view,
            controls=(QLabel("Table"), self.combo),
            framed=False,
            table_stretch=True,
        )
        layout.addWidget(self.table_section, 1)
        self.combo.currentIndexChanged.connect(self._sync_table)

    @property
    def table_collapsed(self) -> bool:
        return self.table_section.table_collapsed

    def collapse_table(self) -> None:
        self.table_section.collapse_table()

    def expand_table(self) -> None:
        self.table_section.expand_table()

    def toggle_table(self) -> None:
        self.table_section.toggle_table()

    def set_tables(self, tables: Sequence[AnalysisTable]) -> None:
        self._tables = tuple(tables)
        self.combo.blockSignals(True)
        self.combo.clear()
        for table in self._tables:
            self.combo.addItem(table.title, table.table_id)
        self.combo.blockSignals(False)
        self.combo.setCurrentIndex(0 if self._tables else -1)
        self._sync_table()

    def refresh_plot(self) -> None:
        return

    def force_refresh_plot(self) -> None:
        return

    def current_table(self) -> AnalysisTable | None:
        index = self.combo.currentIndex()
        if index < 0 or index >= len(self._tables):
            return None
        return self._tables[index]

    def _sync_table(self) -> None:
        self.table_view.set_table(self.current_table())


class OverlayResultsView(QWidget):
    DEFAULT_TABLE_HEIGHT = 210

    def __init__(self, plot_widget: QWidget):
        super().__init__()
        self.plot = plot_widget
        self.table_selector = QComboBox()
        self.table_view = SpreadsheetTableView()
        self._tables: tuple[AnalysisTable, ...] = ()
        self._expanded_table_height = self.DEFAULT_TABLE_HEIGHT

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.plot.setMinimumHeight(260)
        self.splitter.addWidget(self.plot)

        self.table_section = CollapsibleTableSection(
            "Overlay Data",
            "Time-series values matching the overlay traces.",
            self.table_view,
            controls=(QLabel("Source"), self.table_selector),
            table_min_height=150,
        )
        self.splitter.addWidget(self.table_section)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([660, self.DEFAULT_TABLE_HEIGHT])
        layout.addWidget(self.splitter, 1)
        self.table_selector.currentIndexChanged.connect(self._sync_table)

    @property
    def table_collapsed(self) -> bool:
        return self.table_section.table_collapsed

    def collapse_table(self) -> None:
        sizes = self.splitter.sizes()
        if len(sizes) > 1 and sizes[1] > 34:
            self._expanded_table_height = sizes[1]
        self.table_section.collapse_table()
        total = max(sum(self.splitter.sizes()), 660)
        self.splitter.setSizes([max(1, total - 34), 34])

    def expand_table(self) -> None:
        self.table_section.expand_table()
        total = max(sum(self.splitter.sizes()), self._expanded_table_height + 340)
        table_height = max(150, self._expanded_table_height)
        self.splitter.setSizes([max(1, total - table_height), table_height])

    def toggle_table(self) -> None:
        self.table_section.toggle_table()

    def set_figure(self, figure: Any) -> None:
        setter = getattr(self.plot, "set_figure", None)
        if callable(setter):
            setter(figure)

    def refresh_plot(self) -> None:
        refresher = getattr(self.plot, "refresh_plot", None)
        if callable(refresher):
            refresher()

    def force_refresh_plot(self) -> None:
        force_refresher = getattr(self.plot, "force_refresh_plot", None)
        if callable(force_refresher):
            force_refresher()
            return
        self.refresh_plot()

    def set_tables(self, tables: Sequence[AnalysisTable]) -> None:
        self._tables = tuple(tables)
        self.table_selector.blockSignals(True)
        self.table_selector.clear()
        for table in self._tables:
            self.table_selector.addItem(table.title, table.table_id)
        self.table_selector.blockSignals(False)
        self.table_selector.setCurrentIndex(0 if self._tables else -1)
        self._sync_table()

    def current_table(self) -> AnalysisTable | None:
        index = self.table_selector.currentIndex()
        if index < 0 or index >= len(self._tables):
            return None
        return self._tables[index]

    def _sync_table(self) -> None:
        self.table_view.set_table(self.current_table())
