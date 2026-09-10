from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ea_node_editor.addons.property_edit_adapters import (
    PropertyEditAdapterContext,
    PropertyEditRewrite,
)
from ea_node_editor.addons.tabular_data.extraction_nodes import (
    ARRAY_SLICE_COLUMN_COUNT_PROPERTY,
    ARRAY_SLICE_COLUMN_START_PROPERTY,
    ARRAY_SLICE_ROW_COUNT_PROPERTY,
    ARRAY_SLICE_ROW_START_PROPERTY,
    ARRAY_SLICE_SUMMARY_PROPERTY,
    TABLE_WINDOW_COLUMN_COUNT_PROPERTY,
    TABLE_WINDOW_COLUMN_START_PROPERTY,
    TABLE_WINDOW_COLUMNS_PROPERTY,
    TABLE_WINDOW_ROW_COUNT_PROPERTY,
    TABLE_WINDOW_ROW_START_PROPERTY,
    TABLE_WINDOW_SUMMARY_PROPERTY,
    TABULAR_ARRAY_SLICE_2D_NODE_TYPE_ID,
    TABULAR_TABLE_WINDOW_NODE_TYPE_ID,
)
from ea_node_editor.addons.tabular_data.input_node import (
    TABULAR_ARRAY_COLUMN_COUNT_PROPERTY,
    TABULAR_ARRAY_COLUMN_START_PROPERTY,
    TABULAR_ARRAY_ROW_COUNT_PROPERTY,
    TABULAR_ARRAY_ROW_START_PROPERTY,
    TABULAR_ARRAY_SELECTION_SUMMARY_PROPERTY,
    TABULAR_ARRAY_SLICE_2D_PROPERTY,
    TABULAR_DATA_INPUT_NODE_TYPE_ID,
    tabular_array_column_label_from_offset,
    tabular_array_slice_2d_from_value,
    tabular_array_slice_2d_summary,
    tabular_array_slice_2d_with_property_update,
)

_TABULAR_SELECTION_HELP_TEXT = (
    "Optional. Use this when the file contains multiple sheets, keys, or datasets."
)
_TABLE_WINDOW_PROPERTY_KEYS = frozenset(
    {
        TABLE_WINDOW_ROW_START_PROPERTY,
        TABLE_WINDOW_ROW_COUNT_PROPERTY,
        TABLE_WINDOW_COLUMN_START_PROPERTY,
        TABLE_WINDOW_COLUMN_COUNT_PROPERTY,
        TABLE_WINDOW_COLUMNS_PROPERTY,
    }
)
_ARRAY_SLICE_PROPERTY_KEYS = frozenset(
    {
        ARRAY_SLICE_ROW_START_PROPERTY,
        ARRAY_SLICE_ROW_COUNT_PROPERTY,
        ARRAY_SLICE_COLUMN_START_PROPERTY,
        ARRAY_SLICE_COLUMN_COUNT_PROPERTY,
    }
)


def _node_properties(node: Any) -> Mapping[str, Any]:
    properties = getattr(node, "properties", {})
    return properties if isinstance(properties, Mapping) else {}


def _dedupe_text_values(values: Iterable[Any]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value).strip()
        if not value:
            continue
        normalized = value.casefold()
        if normalized in seen:
            continue
        ordered.append(value)
        seen.add(normalized)
    return tuple(ordered)


def _non_negative_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return max(0, default)
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return max(0, default)
    return max(0, normalized)


def _positive_user_row(value: Any, *, default: int) -> int:
    return max(1, _non_negative_int(value, default=default))


def _column_offset_from_user_value(value: Any, *, default: int) -> int:
    text = str(value or "").strip()
    if not text:
        return max(0, int(default))
    try:
        return max(0, int(text) - 1)
    except ValueError:
        pass
    normalized = text.upper()
    if not normalized.isalpha():
        return max(0, int(default))
    offset = 0
    for character in normalized:
        offset = offset * 26 + (ord(character) - ord("A") + 1)
    return max(0, offset - 1)


def _columns_from_value(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items: Iterable[Any] = value.replace(";", ",").split(",")
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        raw_items = value
    else:
        raw_items = ()
    columns: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        columns.append(text)
    return columns


def _base_item(
    *,
    key: str,
    label: str,
    value: Any,
    type_: str = "str",
    editor_mode: str = "text",
    group: str = "Selection",
    dirty: bool = False,
    enum_values: Iterable[str] = (),
    help_text: str = "",
    placeholder_text: str = "",
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "key": key,
        "label": label,
        "type": type_,
        "value": value,
        "enum_values": list(enum_values),
        "inline_editor": "",
        "editor_mode": editor_mode,
        "group": group,
        "dirty": bool(dirty),
    }
    if help_text:
        item["help_text"] = help_text
    if placeholder_text:
        item["placeholder_text"] = placeholder_text
    return item


def _bounds_from_node(node: Any, *, row_limit_default: int, column_limit_default: int) -> dict[str, int]:
    properties = _node_properties(node)
    return {
        "row_offset": _non_negative_int(properties.get("row_offset"), default=0),
        "row_limit": _non_negative_int(properties.get("row_limit"), default=row_limit_default),
        "column_offset": _non_negative_int(properties.get("column_offset"), default=0),
        "column_limit": _non_negative_int(properties.get("column_limit"), default=column_limit_default),
    }


def _rows_summary(row_offset: int, row_limit: int) -> str:
    start = row_offset + 1
    if row_limit == 0:
        return f"Rows {start} onward"
    return f"Rows {start}-{row_offset + row_limit}"


def _columns_summary(column_offset: int, column_limit: int, columns: list[str] | None = None) -> str:
    if columns:
        preview = ", ".join(columns[:4])
        suffix = "" if len(columns) <= 4 else f" +{len(columns) - 4} more"
        return f"Columns {preview}{suffix}"
    start = tabular_array_column_label_from_offset(column_offset)
    if column_limit == 0:
        return f"Columns {start} onward"
    end = tabular_array_column_label_from_offset(column_offset + column_limit - 1)
    return f"Columns {start}-{end}"


def _table_window_property_items(node: Any) -> list[dict[str, Any]]:
    bounds = _bounds_from_node(node, row_limit_default=1000, column_limit_default=0)
    columns = _columns_from_value(_node_properties(node).get("columns", ""))
    summary = f"{_rows_summary(bounds['row_offset'], bounds['row_limit'])}, {_columns_summary(bounds['column_offset'], bounds['column_limit'], columns)}"
    return [
        _base_item(
            key=TABLE_WINDOW_COLUMNS_PROPERTY,
            label="Selected Columns",
            type_="list",
            value=columns,
            editor_mode="chip_list",
            dirty=bool(columns),
            placeholder_text="Search columns",
            help_text="Leave empty to select columns by position.",
        ),
        _base_item(
            key=TABLE_WINDOW_ROW_START_PROPERTY,
            label="Start Row",
            type_="int",
            value=bounds["row_offset"] + 1,
            dirty=bounds["row_offset"] != 0,
            help_text="Rows are numbered from 1.",
        ),
        _base_item(
            key=TABLE_WINDOW_ROW_COUNT_PROPERTY,
            label="Number of Rows",
            type_="int",
            value=bounds["row_limit"],
            dirty=bounds["row_limit"] != 1000,
            help_text="Enter 0 for all remaining rows.",
        ),
        _base_item(
            key=TABLE_WINDOW_COLUMN_START_PROPERTY,
            label="Start Column",
            value=tabular_array_column_label_from_offset(bounds["column_offset"]),
            dirty=bounds["column_offset"] != 0,
            help_text="Use spreadsheet letters such as A or AA, or enter a column number.",
        ),
        _base_item(
            key=TABLE_WINDOW_COLUMN_COUNT_PROPERTY,
            label="Number of Columns",
            type_="int",
            value=bounds["column_limit"],
            dirty=bounds["column_limit"] != 0,
            help_text="Enter 0 for all remaining columns.",
        ),
        _base_item(
            key=TABLE_WINDOW_SUMMARY_PROPERTY,
            label="Preview",
            value=summary,
            editor_mode="summary",
            dirty=False,
        ),
    ]


def _array_slice_property_items(node: Any) -> list[dict[str, Any]]:
    bounds = _bounds_from_node(node, row_limit_default=1000, column_limit_default=100)
    summary = f"{_rows_summary(bounds['row_offset'], bounds['row_limit'])}, {_columns_summary(bounds['column_offset'], bounds['column_limit'])}"
    return [
        _base_item(
            key=ARRAY_SLICE_ROW_START_PROPERTY,
            label="Start Row",
            type_="int",
            value=bounds["row_offset"] + 1,
            dirty=bounds["row_offset"] != 0,
            help_text="Rows are numbered from 1.",
        ),
        _base_item(
            key=ARRAY_SLICE_ROW_COUNT_PROPERTY,
            label="Number of Rows",
            type_="int",
            value=bounds["row_limit"],
            dirty=bounds["row_limit"] != 1000,
            help_text="Enter 0 for all remaining rows.",
        ),
        _base_item(
            key=ARRAY_SLICE_COLUMN_START_PROPERTY,
            label="Start Column",
            value=tabular_array_column_label_from_offset(bounds["column_offset"]),
            dirty=bounds["column_offset"] != 0,
            help_text="Use spreadsheet letters such as A or AA, or enter a column number.",
        ),
        _base_item(
            key=ARRAY_SLICE_COLUMN_COUNT_PROPERTY,
            label="Number of Columns",
            type_="int",
            value=bounds["column_limit"],
            dirty=bounds["column_limit"] != 100,
            help_text="Enter 0 for all remaining columns.",
        ),
        _base_item(
            key=ARRAY_SLICE_SUMMARY_PROPERTY,
            label="Preview",
            value=summary,
            editor_mode="summary",
            dirty=False,
        ),
    ]


def _rewrite_table_window_property(node: Any, key: str, value: Any) -> PropertyEditRewrite | None:
    if key not in _TABLE_WINDOW_PROPERTY_KEYS:
        return None
    properties = _node_properties(node)
    if key == TABLE_WINDOW_COLUMNS_PROPERTY:
        return PropertyEditRewrite("columns", ", ".join(_columns_from_value(value)))
    if key == TABLE_WINDOW_ROW_START_PROPERTY:
        return PropertyEditRewrite(
            "row_offset",
            _positive_user_row(value, default=_non_negative_int(properties.get("row_offset"), default=0) + 1) - 1,
        )
    if key == TABLE_WINDOW_ROW_COUNT_PROPERTY:
        return PropertyEditRewrite("row_limit", _non_negative_int(value, default=1000))
    if key == TABLE_WINDOW_COLUMN_START_PROPERTY:
        return PropertyEditRewrite(
            "column_offset",
            _column_offset_from_user_value(
                value,
                default=_non_negative_int(properties.get("column_offset"), default=0),
            ),
        )
    if key == TABLE_WINDOW_COLUMN_COUNT_PROPERTY:
        return PropertyEditRewrite("column_limit", _non_negative_int(value, default=0))
    return None


def _rewrite_array_slice_property(node: Any, key: str, value: Any) -> PropertyEditRewrite | None:
    if key not in _ARRAY_SLICE_PROPERTY_KEYS:
        return None
    properties = _node_properties(node)
    if key == ARRAY_SLICE_ROW_START_PROPERTY:
        return PropertyEditRewrite(
            "row_offset",
            _positive_user_row(value, default=_non_negative_int(properties.get("row_offset"), default=0) + 1) - 1,
        )
    if key == ARRAY_SLICE_ROW_COUNT_PROPERTY:
        return PropertyEditRewrite("row_limit", _non_negative_int(value, default=1000))
    if key == ARRAY_SLICE_COLUMN_START_PROPERTY:
        return PropertyEditRewrite(
            "column_offset",
            _column_offset_from_user_value(
                value,
                default=_non_negative_int(properties.get("column_offset"), default=0),
            ),
        )
    if key == ARRAY_SLICE_COLUMN_COUNT_PROPERTY:
        return PropertyEditRewrite("column_limit", _non_negative_int(value, default=100))
    return None


def _selection_property_items(node: Any) -> list[dict[str, Any]]:
    selection = tabular_array_slice_2d_from_value(
        _node_properties(node).get(TABULAR_ARRAY_SLICE_2D_PROPERTY, {})
    )
    return [
        {
            "key": TABULAR_ARRAY_ROW_START_PROPERTY,
            "label": "Start Row",
            "type": "int",
            "value": selection["row_offset"] + 1,
            "enum_values": [],
            "inline_editor": "",
            "editor_mode": "text",
            "group": "Selection",
            "dirty": selection["row_offset"] != 0,
            "help_text": "Rows are numbered from 1.",
        },
        {
            "key": TABULAR_ARRAY_ROW_COUNT_PROPERTY,
            "label": "Number of Rows",
            "type": "int",
            "value": selection["row_limit"],
            "enum_values": [],
            "inline_editor": "",
            "editor_mode": "text",
            "group": "Selection",
            "dirty": selection["row_limit"] != 50,
        },
        {
            "key": TABULAR_ARRAY_COLUMN_START_PROPERTY,
            "label": "Start Column",
            "type": "str",
            "value": tabular_array_column_label_from_offset(selection["column_offset"]),
            "enum_values": [],
            "inline_editor": "",
            "editor_mode": "text",
            "group": "Selection",
            "dirty": selection["column_offset"] != 0,
            "help_text": "Use spreadsheet letters such as A or AA, or enter a column number.",
        },
        {
            "key": TABULAR_ARRAY_COLUMN_COUNT_PROPERTY,
            "label": "Number of Columns",
            "type": "int",
            "value": selection["column_limit"],
            "enum_values": [],
            "inline_editor": "",
            "editor_mode": "text",
            "group": "Selection",
            "dirty": selection["column_limit"] != 50,
        },
        {
            "key": TABULAR_ARRAY_SELECTION_SUMMARY_PROPERTY,
            "label": "Preview",
            "type": "str",
            "value": tabular_array_slice_2d_summary(selection),
            "enum_values": [],
            "inline_editor": "",
            "editor_mode": "summary",
            "group": "Selection",
            "dirty": False,
        },
    ]


class TabularDataPropertyEditAdapter:
    def _node_type_id(self, context: PropertyEditAdapterContext) -> str:
        return str(getattr(context.node, "type_id", "")).strip()

    def _is_tabular_input(self, context: PropertyEditAdapterContext) -> bool:
        return self._node_type_id(context) == TABULAR_DATA_INPUT_NODE_TYPE_ID

    def rewrite_property_edit(
        self,
        context: PropertyEditAdapterContext,
        *,
        key: str,
        value: Any,
    ) -> PropertyEditRewrite | None:
        node_type_id = self._node_type_id(context)
        if node_type_id == TABULAR_TABLE_WINDOW_NODE_TYPE_ID:
            return _rewrite_table_window_property(context.node, str(key or "").strip(), value)
        if node_type_id == TABULAR_ARRAY_SLICE_2D_NODE_TYPE_ID:
            return _rewrite_array_slice_property(context.node, str(key or "").strip(), value)
        if node_type_id != TABULAR_DATA_INPUT_NODE_TYPE_ID:
            return None
        updated_slice = tabular_array_slice_2d_with_property_update(
            _node_properties(context.node).get(TABULAR_ARRAY_SLICE_2D_PROPERTY, {}),
            str(key or "").strip(),
            value,
        )
        if updated_slice is None:
            return None
        return PropertyEditRewrite(TABULAR_ARRAY_SLICE_2D_PROPERTY, updated_slice)

    def build_property_items(
        self,
        context: PropertyEditAdapterContext,
        items: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        node_type_id = self._node_type_id(context)
        if node_type_id == TABULAR_TABLE_WINDOW_NODE_TYPE_ID:
            return [dict(item) for item in items] + _table_window_property_items(context.node)
        if node_type_id == TABULAR_ARRAY_SLICE_2D_NODE_TYPE_ID:
            return [dict(item) for item in items] + _array_slice_property_items(context.node)
        if node_type_id != TABULAR_DATA_INPUT_NODE_TYPE_ID:
            return [dict(item) for item in items]

        result: list[dict[str, Any]] = []
        inserted_slice_items = False
        for item in items:
            next_item = dict(item)
            result.append(next_item)
            if str(next_item.get("key", "")).strip() != "selected_object":
                continue
            next_item["help_text"] = _TABULAR_SELECTION_HELP_TEXT
            next_item.update(self._selected_object_override(context))
            result.extend(_selection_property_items(context.node))
            inserted_slice_items = True
        if not inserted_slice_items:
            result.extend(_selection_property_items(context.node))
        return result

    def _selected_object_override(self, context: PropertyEditAdapterContext) -> dict[str, Any]:
        from ea_node_editor.ui.tabular_preview_provider import describe_tabular_selector

        selector_properties = dict(_node_properties(context.node))
        source_path = context.source_path_for_property("path")
        if source_path:
            selector_properties["path"] = source_path

        def project_context() -> tuple[str | None, dict[str, Any] | None]:
            metadata = dict(context.project_metadata) if isinstance(context.project_metadata, Mapping) else None
            return context.project_path, metadata

        try:
            payload = describe_tabular_selector(selector_properties, project_context_provider=project_context)
        except Exception:
            payload = {}
        selector = payload.get("selector") if isinstance(payload, Mapping) else {}
        raw_objects_value = selector.get("objects") if isinstance(selector, Mapping) else []
        raw_objects = (
            raw_objects_value
            if isinstance(raw_objects_value, Iterable) and not isinstance(raw_objects_value, (str, bytes, Mapping))
            else []
        )
        options = _dedupe_text_values(
            str(item.get("object_id") or item.get("display_name") or "")
            for item in raw_objects
            if isinstance(item, Mapping)
        )
        state = str(payload.get("state", "") if isinstance(payload, Mapping) else "")
        error = payload.get("error") if isinstance(payload, Mapping) else {}
        error_code = str(error.get("code", "") if isinstance(error, Mapping) else "")
        placeholder = ""
        if not source_path:
            placeholder = "Choose a tabular data file first"
        elif not options:
            placeholder = (
                "No sheets, keys, or datasets found"
                if state == "ready"
                else "Enter sheet, key, or dataset manually"
            )
        elif error_code == "selector_required":
            placeholder = "Select a sheet, key, or dataset"
        return {
            "editor_mode": "editable_combo",
            "enum_values": list(options),
            "placeholder_text": placeholder,
        }


def create_tabular_property_edit_adapters() -> tuple[TabularDataPropertyEditAdapter, ...]:
    return (TabularDataPropertyEditAdapter(),)


__all__ = [
    "TabularDataPropertyEditAdapter",
    "create_tabular_property_edit_adapters",
]
