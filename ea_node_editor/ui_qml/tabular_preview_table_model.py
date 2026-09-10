from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from PyQt6.QtCore import (
    QByteArray,
    QAbstractTableModel,
    QModelIndex,
    QObject,
    Qt,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtQml import qmlRegisterType

from ea_node_editor.addons.tabular_data.input_node import (
    TABULAR_TABLE_VIEW_STATE_MAX_COLUMN_WIDTH,
    TABULAR_TABLE_VIEW_STATE_MIN_COLUMN_WIDTH,
)

_QML_IMPORT_NAME = "EA.NodeEditor"
_QML_IMPORT_MAJOR_VERSION = 1
_QML_IMPORT_MINOR_VERSION = 0
_QML_TYPE_NAME = "TabularPreviewTableModel"
_QML_REGISTERED = False

_DISPLAY_ROLE = int(Qt.ItemDataRole.DisplayRole.value)
_EDIT_ROLE = int(Qt.ItemDataRole.EditRole.value)


def _object_value(value: Any) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()} if isinstance(value, Mapping) else {}


def _array_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _string_value(value: Any) -> str:
    return "" if value is None else str(value)


def _non_negative_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


def _preview_payload(payload: Any) -> dict[str, Any]:
    normalized = _object_value(payload)
    nested = normalized.get("preview")
    return _object_value(nested) if isinstance(nested, Mapping) else normalized


def _window_payload(preview: Mapping[str, Any]) -> dict[str, Any]:
    if str(preview.get("preview_kind", "") or "") == "array":
        return _object_value(preview.get("slice_2d"))
    return _object_value(preview.get("window"))


def _role(role: int | Qt.ItemDataRole) -> int:
    return int(role.value) if isinstance(role, Qt.ItemDataRole) else int(role)


def _width_for_text(values: Sequence[str]) -> int:
    longest = max((len(value) for value in values), default=0)
    width = longest * 8 + 32
    return max(TABULAR_TABLE_VIEW_STATE_MIN_COLUMN_WIDTH, min(TABULAR_TABLE_VIEW_STATE_MAX_COLUMN_WIDTH, width))


class TabularPreviewTableModel(QAbstractTableModel):
    preview_changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._preview: dict[str, Any] = {}
        self._preview_kind = ""
        self._rows: list[Any] = []
        self._columns: list[str] = []
        self._row_offset = 0
        self._column_offset = 0

    @pyqtProperty("QVariantMap", notify=preview_changed)
    def preview(self) -> dict[str, Any]:
        return copy.deepcopy(self._preview)

    @preview.setter
    def preview(self, value: Mapping[str, Any] | None) -> None:
        self.set_preview(value)

    @pyqtProperty(str, notify=preview_changed)
    def preview_kind(self) -> str:
        return self._preview_kind

    @pyqtProperty(int, notify=preview_changed)
    def row_count(self) -> int:
        return len(self._rows)

    @pyqtProperty(int, notify=preview_changed)
    def column_count(self) -> int:
        return len(self._columns)

    @pyqtProperty(int, notify=preview_changed)
    def row_offset(self) -> int:
        return self._row_offset

    @pyqtProperty(int, notify=preview_changed)
    def column_offset(self) -> int:
        return self._column_offset

    @pyqtSlot("QVariantMap")
    def setPreview(self, value: Mapping[str, Any] | None) -> None:  # noqa: N802 - QML API
        self.set_preview(value)

    def set_preview(self, value: Mapping[str, Any] | None) -> None:
        preview = _preview_payload(value)
        if preview == self._preview:
            return
        rows, columns, preview_kind, row_offset, column_offset = self._extract_window(preview)
        self.beginResetModel()
        self._preview = copy.deepcopy(preview)
        self._rows = rows
        self._columns = columns
        self._preview_kind = preview_kind
        self._row_offset = row_offset
        self._column_offset = column_offset
        self.endResetModel()
        self.preview_changed.emit()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._columns)

    def data(self, index: QModelIndex, role: int = _DISPLAY_ROLE) -> str | None:
        if not index.isValid() or _role(role) not in {_DISPLAY_ROLE, _EDIT_ROLE}:
            return None
        return self.cell_text(index.row(), index.column())

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = _DISPLAY_ROLE,
    ) -> str | None:  # noqa: N802
        if _role(role) not in {_DISPLAY_ROLE, _EDIT_ROLE}:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._columns):
                return self._columns[section]
            return None
        if orientation == Qt.Orientation.Vertical:
            return str(self._row_offset + int(section))
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802
        return {_DISPLAY_ROLE: QByteArray(b"display")}

    @pyqtSlot(int, int, result=str)
    def cell_text(self, row: int, column: int) -> str:
        if not (0 <= row < len(self._rows) and 0 <= column < len(self._columns)):
            return ""
        row_value = self._rows[row]
        if self._preview_kind == "array":
            values = _array_value(row_value)
            return _string_value(values[column]) if 0 <= column < len(values) else ""
        if not isinstance(row_value, Mapping):
            return ""
        return _string_value(row_value.get(self._columns[column]))

    @pyqtSlot(int, result=str)
    def column_label(self, column: int) -> str:
        return self._columns[column] if 0 <= column < len(self._columns) else ""

    @pyqtSlot(int, result=str)
    def row_label(self, row: int) -> str:
        return str(self._row_offset + int(row)) if 0 <= row < len(self._rows) else ""

    @pyqtSlot(int, result=str)
    def column_key(self, column: int) -> str:
        if not (0 <= column < len(self._columns)):
            return ""
        if self._preview_kind == "array":
            return f"array:{self._column_offset + int(column)}"
        return f"table:{self._columns[column]}"

    @pyqtSlot(int, result=int)
    def autofit_width(self, column: int) -> int:
        if not (0 <= column < len(self._columns)):
            return TABULAR_TABLE_VIEW_STATE_MIN_COLUMN_WIDTH
        values = [self._columns[column]]
        values.extend(self.cell_text(row, column) for row in range(len(self._rows)))
        return _width_for_text(values)

    @staticmethod
    def _extract_window(preview: Mapping[str, Any]) -> tuple[list[Any], list[str], str, int, int]:
        preview_kind = str(preview.get("preview_kind", "") or "")
        window = _window_payload(preview)
        row_offset = _non_negative_int(window.get("row_offset"), 0)
        column_offset = _non_negative_int(window.get("column_offset"), 0)
        if preview_kind == "array":
            rows = _array_value(window.get("values"))
            width = max((len(_array_value(row)) for row in rows), default=0)
            columns = [f"C{column_offset + index}" for index in range(width)]
            return rows, columns, preview_kind, row_offset, column_offset
        columns = [_string_value(column) for column in _array_value(window.get("columns"))]
        rows = _array_value(window.get("rows"))
        return rows, columns, preview_kind, row_offset, column_offset


def register_qml_types() -> None:
    global _QML_REGISTERED
    if _QML_REGISTERED:
        return
    qmlRegisterType(
        TabularPreviewTableModel,
        _QML_IMPORT_NAME,
        _QML_IMPORT_MAJOR_VERSION,
        _QML_IMPORT_MINOR_VERSION,
        _QML_TYPE_NAME,
    )
    _QML_REGISTERED = True


__all__ = ["TabularPreviewTableModel", "register_qml_types"]
