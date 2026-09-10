# Purpose: Project Signal Plot column choices from already accepted value metadata.
# Map: feature_routes/plotter_nodes.md
# Tests: tests/test_plot_property_edit_adapter.py
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from ea_node_editor.runtime_contracts import ArrayDataRef, ArraySlice2DRef, DataTree, TabularDataRef, TabularWindowRef
from ea_node_editor.runtime_contracts.scientific_values import ArrayValue, TableValue


def connected_signal_value(node_id: str, edges: Any, current_output_provider: Callable[[str, str], Any] | None) -> Any:
    if current_output_provider is None:
        return None
    for edge in edges.values() if isinstance(edges, Mapping) else edges or ():
        if edge.target_node_id == node_id and edge.target_port_key == "values" and getattr(edge, "enabled", True):
            return current_output_provider(edge.source_node_id, edge.source_port_key)
    return None


def _option(ref: Any, key: str, default: Any) -> Any:
    options = ref.metadata.get("node_options", {})
    return options[key] if isinstance(options, Mapping) and key in options else ref.metadata.get(key, default)


def _columns(value: Any) -> tuple[tuple[Any, str], ...]:
    if isinstance(value, TableValue):
        return tuple((name, column.dtype) for name, column in zip(value.column_names, value.columns))
    if isinstance(value, (TabularDataRef, TabularWindowRef)):
        base = value.table_data if isinstance(value, TabularWindowRef) else value
        schema = base.metadata.get("column_schema", ())
        columns = tuple((item["name"], item["dtype"]) for item in schema if isinstance(item, Mapping) and type(item.get("name")) is str and type(item.get("dtype")) is str)
        names = value.columns if isinstance(value, TabularWindowRef) else _option(base, "selected_columns", ())
        if names:
            lookup = {name: (name, dtype) for name, dtype in columns}
            columns = tuple(lookup[name] for name in names if name in lookup)
        if isinstance(value, TabularWindowRef):
            start = 0 if value.columns else value.column_offset
            columns = columns[start:start + value.column_limit if value.column_limit else None]
        return columns
    if isinstance(value, (ArrayValue, ArrayDataRef, ArraySlice2DRef)):
        base = value.array_data if isinstance(value, ArraySlice2DRef) else value
        if len(base.shape) not in {1, 2}:
            return ()
        width = base.shape[1] if len(base.shape) == 2 else 1
        if isinstance(value, ArraySlice2DRef):
            start, limit = value.column_offset, value.column_limit
        elif isinstance(base, ArrayDataRef):
            hints = _option(base, "array_slice_2d", {})
            start, limit = hints.get("column_offset", 0), hints.get("column_limit", 0)
        else:
            start, limit = 0, 0
        width = max(0, min(width - start, limit) if limit else width - start)
        return ((None, base.dtype),) * min(width, 1024)
    if isinstance(value, (tuple, list)) and value and isinstance(value[0], (tuple, list)):
        return ((None, ""),) * min(len(value[0]), 1024)
    return ()


def _kind(dtype: str) -> str:
    text = dtype.lower()
    if text.startswith(("timestamp[", "date32[", "date64[", "datetime")) or re.match(r"^[<>=|]?M\d", dtype):
        return "datetime"
    if not text or re.match(r"^(?:[<>=|]?[iuf]\d|u?int\d|float\d|double$|float$)", text):
        return "numeric"
    return "other"


def enrich_signal_property_items(items: Iterable[Mapping[str, Any]], source: Any) -> list[dict[str, Any]]:
    """Read metadata only: never materialize arrays, query a loader or execute a node."""
    sources = (source,)
    if isinstance(source, DataTree):
        containers = (ArrayValue, TableValue, TabularDataRef, TabularWindowRef, ArrayDataRef, ArraySlice2DRef, list, tuple)
        sources = (item for _path, branch in source.branches if branch and isinstance(branch[0], containers) for item in branch if isinstance(item, containers))
    x_options: dict[str | int, str] = {}
    y_options: dict[str | int, str] = {}
    for value in sources:
        columns = _columns(value)
        counts = Counter(name for name, _dtype in columns if type(name) is str)
        for index, (name, dtype) in enumerate(columns):
            code = name if type(name) is str and name and counts[name] == 1 else index
            label = name if type(code) is str else f"Column {index + 1}" + (f" ({name})" if name is not None else "")
            if type(code) is int:
                while label in counts:
                    label += " [position]"
            kind = _kind(dtype)
            if kind in {"numeric", "datetime"}:
                x_options.setdefault(code, label)
            if kind == "numeric":
                y_options.setdefault(code, label)
        if len(x_options) >= 1024:
            break
    result = [dict(item) for item in items]
    for item in result:
        key = item.get("key")
        if key == "x_mode":
            item.update(enum_values=["Automatic", "Sample index", "Column"], enum_codes=["auto", "index", "column"])
        elif key in {"x_column", "y_columns"}:
            options = x_options if key == "x_column" else y_options
            item.update(
                enum_values=list(options.values()), enum_codes=list(options),
                exact_selectors=True, searchable=True,
                inline_editor="enum" if key == "x_column" else "list",
                editor_mode="editable_combo" if key == "x_column" else "chip_list",
                placeholder_text="Exact column name or choose a position",
            )
            if key == "y_columns":
                item.update(list_item_type="str", list_item_enum_values=list(options.values()), list_item_enum_codes=list(options))
    return result
