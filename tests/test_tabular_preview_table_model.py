from __future__ import annotations

import copy

from PyQt6.QtCore import QModelIndex, Qt

from ea_node_editor.addons.tabular_data.input_node import (
    TABULAR_TABLE_VIEW_STATE_MAX_COLUMN_WIDTH,
    TABULAR_TABLE_VIEW_STATE_MIN_COLUMN_WIDTH,
)
from ea_node_editor.ui_qml.tabular_preview_table_model import TabularPreviewTableModel


def _table_preview() -> dict:
    return {
        "state": "ready",
        "preview_kind": "table",
        "window": {
            "columns": ["station", "temp", "count"],
            "rows": [
                {"station": "S0", "temp": "20.0", "count": 0},
                {"station": "S1", "temp": "20.1", "count": 1},
            ],
            "row_offset": 10,
            "column_offset": 0,
        },
    }


def _array_preview() -> dict:
    return {
        "state": "ready",
        "preview_kind": "array",
        "array": {"shape": [100, 10], "dtype": "float64"},
        "slice_2d": {
            "values": [[1, 2], [4, 5, 6]],
            "row_offset": 20,
            "column_offset": 4,
        },
    }


def test_tabular_preview_table_model_maps_table_payload() -> None:
    model = TabularPreviewTableModel()
    model.set_preview(_table_preview())

    assert model.rowCount() == 2
    assert model.columnCount() == 3
    assert model.headerData(0, Qt.Orientation.Horizontal) == "station"
    assert model.headerData(1, Qt.Orientation.Vertical) == "11"
    assert model.data(model.index(1, 1), Qt.ItemDataRole.DisplayRole) == "20.1"
    assert model.cell_text(0, 2) == "0"
    assert model.column_key(0) == "table:station"


def test_tabular_preview_table_model_maps_array_payload() -> None:
    model = TabularPreviewTableModel()
    model.set_preview(_array_preview())

    assert model.rowCount() == 2
    assert model.columnCount() == 3
    assert model.headerData(0, Qt.Orientation.Horizontal) == "C4"
    assert model.headerData(1, Qt.Orientation.Vertical) == "21"
    assert model.data(model.index(1, 2), Qt.ItemDataRole.DisplayRole) == "6"
    assert model.column_key(2) == "array:6"


def test_tabular_preview_table_model_reset_clears_rows_and_columns() -> None:
    model = TabularPreviewTableModel()
    model.set_preview(_table_preview())
    model.set_preview({})

    assert model.rowCount() == 0
    assert model.columnCount() == 0
    assert model.data(QModelIndex(), Qt.ItemDataRole.DisplayRole) is None


def test_tabular_preview_table_model_ignores_unchanged_preview_payload() -> None:
    model = TabularPreviewTableModel()
    model_reset_count = 0
    preview_changed_count = 0

    def _record_model_reset() -> None:
        nonlocal model_reset_count
        model_reset_count += 1

    def _record_preview_changed() -> None:
        nonlocal preview_changed_count
        preview_changed_count += 1

    model.modelReset.connect(_record_model_reset)
    model.preview_changed.connect(_record_preview_changed)

    preview = _table_preview()
    model.set_preview({"preview": preview})
    model.set_preview({"preview": copy.deepcopy(preview)})

    assert model_reset_count == 1
    assert preview_changed_count == 1
    assert model.rowCount() == 2


def test_tabular_preview_table_model_is_read_only() -> None:
    model = TabularPreviewTableModel()
    model.set_preview(_table_preview())

    flags = model.flags(model.index(0, 0))
    assert flags & Qt.ItemFlag.ItemIsEnabled
    assert flags & Qt.ItemFlag.ItemIsSelectable
    assert not flags & Qt.ItemFlag.ItemIsEditable


def test_tabular_preview_table_model_autofit_width_clamps_to_supported_range() -> None:
    model = TabularPreviewTableModel()
    preview = _table_preview()
    preview["window"]["rows"][0]["station"] = "x" * 200
    model.set_preview(preview)

    assert model.autofit_width(0) == TABULAR_TABLE_VIEW_STATE_MAX_COLUMN_WIDTH
    assert model.autofit_width(2) >= TABULAR_TABLE_VIEW_STATE_MIN_COLUMN_WIDTH
