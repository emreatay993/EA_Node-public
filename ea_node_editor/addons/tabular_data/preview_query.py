# Purpose: Normalize and evaluate Tabular preview sort, filter, search, and window requests.
# Map: feature_routes/tabular_data_addon_preview
# Tests: tests/test_tabular_preview_query.py
from __future__ import annotations

import importlib
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ea_node_editor.addons.tabular_data.source_backends import (
    json_safe_mapping as _json_safe_mapping,
)


_NUMERIC_TEXT_PATTERN = r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"


@dataclass(slots=True, frozen=True)
class QueryFilter:
    column: str | None
    op: str
    value: str


@dataclass(slots=True, frozen=True)
class NormalizedPreviewQuery:
    all_columns: tuple[str, ...]
    selected_columns: tuple[str, ...]
    predicates: tuple[QueryFilter, ...]
    sort_directives: tuple[tuple[str, bool], ...]
    row_offset: int
    row_limit: int
    column_offset: int
    column_limit: int

    @classmethod
    def from_mapping(
        cls,
        request: Mapping[str, Any] | None,
        all_columns: Sequence[str],
    ) -> NormalizedPreviewQuery:
        request_map = dict(request) if isinstance(request, Mapping) else {}
        row_offset = _query_int(request_map.get("row_offset"), default=0, minimum=0)
        row_limit = _query_int(request_map.get("row_limit"), default=50, minimum=1)
        column_offset = _query_int(request_map.get("column_offset"), default=0, minimum=0)
        column_limit = _query_int(request_map.get("column_limit"), default=50, minimum=1)
        requested_columns = tuple(
            str(name).strip()
            for name in _as_sequence(request_map.get("columns"))
            if str(name).strip()
        )
        available = tuple(all_columns)
        if requested_columns:
            selected_columns = tuple(name for name in requested_columns if name in available)[:column_limit]
        else:
            selected_columns = available[column_offset : column_offset + column_limit]
        return cls(
            all_columns=available,
            selected_columns=selected_columns,
            predicates=_collect_query_predicates(
                request_map.get("filters"),
                request_map.get("filter"),
                request_map.get("search"),
            ),
            sort_directives=_normalize_sort_directives(request_map.get("sort")),
            row_offset=row_offset,
            row_limit=row_limit,
            column_offset=column_offset,
            column_limit=column_limit,
        )


@dataclass(slots=True, frozen=True)
class PreviewQueryResult:
    rows: tuple[dict[str, Any], ...]
    total_rows: int
    backend: str
    truncated: bool = False
    scanned_rows: int = 0


def evaluate_python_query(
    query: NormalizedPreviewQuery,
    source_rows: Iterable[Mapping[str, Any]],
    *,
    scan_row_cap: int,
) -> PreviewQueryResult:
    matched: list[Mapping[str, Any]] = []
    scanned = 0
    truncated = False
    predicates = query.predicates
    selected_columns = query.selected_columns
    for source_row in source_rows:
        if scanned >= scan_row_cap:
            truncated = True
            break
        scanned += 1
        if _row_passes_predicates(source_row, predicates, selected_columns):
            matched.append(source_row)

    for column, descending in reversed(query.sort_directives):
        matched.sort(
            key=lambda row, _column=column: _query_sort_key(row.get(_column)),
            reverse=descending,
        )

    windowed = matched[query.row_offset : query.row_offset + query.row_limit]
    return PreviewQueryResult(
        rows=tuple(
            {column: source_row.get(column) for column in selected_columns}
            for source_row in windowed
        ),
        total_rows=len(matched),
        backend="python",
        truncated=truncated,
        scanned_rows=scanned,
    )


def evaluate_arrow_query(
    query: NormalizedPreviewQuery,
    parquet_path: Path,
    *,
    query_table_for: Callable[[Any, Path, Sequence[str]], tuple[Any, dict[str, Any]] | None],
    run_io: Callable[..., Any],
) -> PreviewQueryResult | None:
    """Evaluate one normalized query with the preloaded Arrow compute kernels."""

    try:
        pyarrow = importlib.import_module("pyarrow")
        pa_compute = importlib.import_module("pyarrow.compute")
        pq = importlib.import_module("pyarrow.parquet")
    except ModuleNotFoundError:
        return None

    def run_query() -> tuple[int, tuple[dict[str, Any], ...]]:
        needed: list[str] = list(query.selected_columns)
        for predicate in query.predicates:
            if predicate.column and predicate.column in query.all_columns and predicate.column not in needed:
                needed.append(predicate.column)
        for column, _descending in query.sort_directives:
            if column in query.all_columns and column not in needed:
                needed.append(column)
        cached = query_table_for(pq, parquet_path, needed)
        if cached is not None:
            table, text_views = cached
        else:
            table, text_views = pq.read_table(parquet_path, columns=needed), {}

        def full_text_view(column_name: str) -> Any:
            view = text_views.get(column_name)
            if view is None:
                view = _arrow_text_view(pyarrow, pa_compute, table.column(column_name))
                text_views[column_name] = view
            return view

        mask = None
        for predicate in query.predicates:
            predicate_mask = _arrow_predicate_mask(
                pyarrow,
                pa_compute,
                table,
                predicate,
                query.selected_columns,
                full_text_view,
            )
            mask = predicate_mask if mask is None else pa_compute.and_kleene(mask, predicate_mask)
        filtered = table
        if mask is not None:
            filtered = table.filter(pa_compute.fill_null(mask, False))
        total = int(filtered.num_rows)

        applicable_sorts = [
            (column, descending)
            for column, descending in query.sort_directives
            if column in filtered.column_names
        ]
        if applicable_sorts and total > 1:
            augmented = filtered
            sort_keys: list[tuple[str, str]] = []
            reserved_key_names = set(augmented.column_names)
            for index, (column, descending) in enumerate(applicable_sorts):
                field_type = filtered.schema.field(column).type
                key_names = (column,)
                if pyarrow.types.is_string(field_type) or pyarrow.types.is_large_string(field_type):
                    text_values = (
                        full_text_view(column)
                        if filtered is table
                        else _arrow_text_view(pyarrow, pa_compute, filtered.column(column))
                    )
                    key_names = tuple(
                        _unique_sort_key_name(base_name, reserved_key_names)
                        for base_name in (
                            f"__sort_kind_{index}",
                            f"__sort_numeric_{index}",
                            f"__sort_text_{index}",
                        )
                    )
                    for key_name, key_values in zip(
                        key_names,
                        _arrow_query_sort_columns(pyarrow, pa_compute, filtered.column(column), text_values),
                        strict=True,
                    ):
                        augmented = augmented.append_column(key_name, key_values)
                elif pyarrow.types.is_floating(field_type):
                    key_names = tuple(
                        _unique_sort_key_name(base_name, reserved_key_names)
                        for base_name in (
                            f"__sort_kind_{index}",
                            f"__sort_numeric_{index}",
                        )
                    )
                    for key_name, key_values in zip(
                        key_names,
                        _arrow_float_sort_columns(pyarrow, pa_compute, filtered.column(column)),
                        strict=True,
                    ):
                        augmented = augmented.append_column(key_name, key_values)
                else:
                    kind_name = _unique_sort_key_name(
                        f"__sort_kind_{index}",
                        reserved_key_names,
                    )
                    augmented = augmented.append_column(
                        kind_name,
                        _arrow_native_sort_kind(pyarrow, pa_compute, filtered.column(column)),
                    )
                    key_names = (kind_name, column)
                direction = "descending" if descending else "ascending"
                sort_keys.extend(
                    (key_name, direction)
                    for key_name in key_names
                )
            indices = pa_compute.sort_indices(
                augmented,
                sort_keys=sort_keys,
                null_placement="at_end",
            )
            page_indices = indices.slice(query.row_offset, query.row_limit if query.row_limit > 0 else None)
            page = filtered.select(list(query.selected_columns)).take(page_indices)
        else:
            page = filtered.select(list(query.selected_columns)).slice(
                query.row_offset,
                query.row_limit if query.row_limit > 0 else None,
            )
        rows = tuple(_json_safe_mapping(row) for row in page.to_pylist())
        return total, rows

    total_rows, rows = run_io(run_query)
    return PreviewQueryResult(rows=rows, total_rows=total_rows, backend="arrow")


def _query_int(value: Any, *, default: int, minimum: int) -> int:
    if isinstance(value, bool):
        return max(minimum, default)
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return max(minimum, default)
    return max(minimum, normalized)


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if value is None or isinstance(value, (str, bytes, Mapping)):
        return ()
    if isinstance(value, Sequence):
        return tuple(value)
    return ()


def _sort_descending(entry: Mapping[str, Any]) -> bool:
    if "descending" in entry:
        return bool(entry.get("descending"))
    direction = str(entry.get("direction", "")).strip().lower()
    return direction in {"desc", "descending"}


def _normalize_sort_directives(value: Any) -> tuple[tuple[str, bool], ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, Mapping):
        entries: tuple[Any, ...] = (value,)
    elif isinstance(value, str):
        text = value.strip()
        return ((text, False),) if text else ()
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        entries = tuple(value)
    else:
        return ()
    directives: list[tuple[str, bool]] = []
    for entry in entries:
        if isinstance(entry, Mapping):
            column = str(entry.get("column", "")).strip()
            if column:
                directives.append((column, _sort_descending(entry)))
        elif isinstance(entry, str) and entry.strip():
            directives.append((entry.strip(), False))
    return tuple(directives)


def _structured_filter(entry: Mapping[str, Any]) -> QueryFilter | None:
    column = str(entry.get("column", "")).strip()
    op = str(entry.get("op", "contains")).strip().lower() or "contains"
    raw_value = entry.get("value", entry.get("text", ""))
    value_text = "" if raw_value is None else str(raw_value)
    if not column and not value_text.strip():
        return None
    return QueryFilter(column or None, op, value_text)


def _filter_predicates(value: Any) -> tuple[QueryFilter, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (QueryFilter(None, "contains", text),) if text else ()
    if isinstance(value, Mapping):
        if {"column", "op", "value"} & set(value):
            single = _structured_filter(value)
            return (single,) if single is not None else ()
        if "text" in value:
            text = str(value.get("text", "")).strip()
            return (QueryFilter(None, "contains", text),) if text else ()
        predicates: list[QueryFilter] = []
        for key, raw in value.items():
            cell = "" if raw is None else str(raw).strip()
            if cell:
                predicates.append(QueryFilter(str(key).strip() or None, "contains", cell))
        return tuple(predicates)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        predicates = []
        for item in value:
            if isinstance(item, Mapping):
                single = _structured_filter(item)
                if single is not None:
                    predicates.append(single)
            elif isinstance(item, str) and item.strip():
                predicates.append(QueryFilter(None, "contains", item.strip()))
        return tuple(predicates)
    return ()


def _collect_query_predicates(
    filters_value: Any,
    filter_value: Any,
    search_value: Any,
) -> tuple[QueryFilter, ...]:
    predicates: list[QueryFilter] = []
    for raw in (filters_value, filter_value):
        predicates.extend(_filter_predicates(raw))
    search_text = "" if search_value is None else str(search_value).strip()
    if search_text:
        predicates.append(QueryFilter(None, "contains", search_text))
    return tuple(predicates)


def _cell_text(cell: Any) -> str:
    return "" if cell is None else str(cell)


def _cell_has_value(cell: Any) -> bool:
    if cell is None or (isinstance(cell, float) and not math.isfinite(cell)):
        return False
    return bool(_cell_text(cell).strip())


def _compare_cell(text: str, op: str, target: str) -> bool:
    try:
        left: Any = float(text)
        right: Any = float(target)
    except (TypeError, ValueError):
        left, right = text.lower(), target.lower()
    if op == "gt":
        return left > right
    if op == "gte":
        return left >= right
    if op == "lt":
        return left < right
    return left <= right


def _cell_op(cell: Any, op: str, target: str) -> bool:
    if not _cell_has_value(cell):
        return False
    text = _cell_text(cell)
    if op in {"gt", "gte", "lt", "lte"}:
        return _compare_cell(text, op, target)
    lowered = text.lower()
    needle = target.lower()
    if op in {"equals", "eq"}:
        return lowered.strip() == needle.strip()
    if op == "startswith":
        return lowered.startswith(needle)
    if op == "endswith":
        return lowered.endswith(needle)
    return needle in lowered


def _predicate_matches(
    row: Mapping[str, Any],
    predicate: QueryFilter,
    selected_columns: Sequence[str],
) -> bool:
    if predicate.column:
        cells: tuple[Any, ...] = (row.get(predicate.column),)
    else:
        cells = tuple(row.get(column) for column in selected_columns)
    if predicate.op == "not_contains":
        needle = predicate.value.lower()
        return all(
            not _cell_has_value(cell) or needle not in _cell_text(cell).lower()
            for cell in cells
        )
    return any(_cell_op(cell, predicate.op, predicate.value) for cell in cells)


def _row_passes_predicates(
    row: Mapping[str, Any],
    predicates: Sequence[QueryFilter],
    selected_columns: Sequence[str],
) -> bool:
    return all(_predicate_matches(row, predicate, selected_columns) for predicate in predicates)


def _arrow_text_view(pyarrow: Any, pa_compute: Any, column: Any) -> Any:
    if not (pyarrow.types.is_string(column.type) or pyarrow.types.is_large_string(column.type)):
        column = pa_compute.cast(column, pyarrow.string())
    return pa_compute.utf8_lower(column)


def _arrow_numeric_text_values(pyarrow: Any, pa_compute: Any, text_view: Any) -> tuple[Any, Any]:
    trimmed = pa_compute.utf8_trim_whitespace(text_view)
    numeric_mask = pa_compute.fill_null(
        pa_compute.match_substring_regex(trimmed, _NUMERIC_TEXT_PATTERN),
        False,
    )
    numeric_text = pa_compute.if_else(
        numeric_mask,
        trimmed,
        pyarrow.scalar(None, type=pyarrow.string()),
    )
    return numeric_mask, pa_compute.cast(numeric_text, pyarrow.float64())


def _arrow_value_present_mask(
    pyarrow: Any,
    pa_compute: Any,
    column: Any,
    text_view: Any,
) -> Any:
    present = pa_compute.and_kleene(
        pa_compute.is_valid(column),
        pa_compute.invert(pa_compute.equal(pa_compute.utf8_trim_whitespace(text_view), "")),
    )
    if pyarrow.types.is_floating(column.type):
        present = pa_compute.and_kleene(present, pa_compute.is_finite(column))
    return present


def _arrow_query_sort_columns(
    pyarrow: Any,
    pa_compute: Any,
    column: Any,
    text_view: Any,
) -> tuple[Any, Any, Any]:
    trimmed = pa_compute.utf8_trim_whitespace(text_view)
    empty_mask = pa_compute.equal(trimmed, "")
    numeric_mask, numeric_values = _arrow_numeric_text_values(pyarrow, pa_compute, text_view)
    valid_mask = pa_compute.is_valid(column)
    text_mask = pa_compute.and_kleene(
        valid_mask,
        pa_compute.and_kleene(pa_compute.invert(empty_mask), pa_compute.invert(numeric_mask)),
    )
    kind = pa_compute.if_else(
        numeric_mask,
        pyarrow.scalar(0),
        pa_compute.if_else(text_mask, pyarrow.scalar(1), pyarrow.scalar(2)),
    )
    numeric_key = pa_compute.fill_null(numeric_values, 0.0)
    text_key = pa_compute.if_else(text_mask, trimmed, pyarrow.scalar("", type=pyarrow.string()))
    return pa_compute.fill_null(kind, 2), numeric_key, pa_compute.fill_null(text_key, "")


def _arrow_float_sort_columns(pyarrow: Any, pa_compute: Any, column: Any) -> tuple[Any, Any]:
    finite = pa_compute.fill_null(pa_compute.is_finite(column), False)
    kind = pa_compute.if_else(finite, pyarrow.scalar(0), pyarrow.scalar(2))
    numeric_key = pa_compute.if_else(finite, column, pyarrow.scalar(0.0, type=column.type))
    return kind, numeric_key


def _unique_sort_key_name(base_name: str, reserved_names: set[str]) -> str:
    candidate = base_name
    suffix = 1
    while candidate in reserved_names:
        candidate = f"{base_name}_{suffix}"
        suffix += 1
    reserved_names.add(candidate)
    return candidate


def _arrow_native_sort_kind(pyarrow: Any, pa_compute: Any, column: Any) -> Any:
    present = pa_compute.fill_null(pa_compute.is_valid(column), False)
    return pa_compute.if_else(present, pyarrow.scalar(0), pyarrow.scalar(2))


def _arrow_cell_op_mask(
    pyarrow: Any,
    pa_compute: Any,
    column: Any,
    op: str,
    value: str,
    text_view: Any,
) -> Any:
    needle = value.lower()
    present_mask = _arrow_value_present_mask(pyarrow, pa_compute, column, text_view)
    if op in {"gt", "gte", "lt", "lte"}:
        compare = {
            "gt": pa_compute.greater,
            "gte": pa_compute.greater_equal,
            "lt": pa_compute.less,
            "lte": pa_compute.less_equal,
        }[op]
        try:
            numeric_target: float | None = float(value)
        except (TypeError, ValueError):
            numeric_target = None
        is_numeric_column = (
            pyarrow.types.is_integer(column.type)
            or pyarrow.types.is_floating(column.type)
            or pyarrow.types.is_decimal(column.type)
        )
        if is_numeric_column and numeric_target is not None and math.isfinite(numeric_target):
            operation_mask = compare(column, numeric_target)
        elif numeric_target is not None and math.isfinite(numeric_target):
            numeric_mask, numeric_values = _arrow_numeric_text_values(pyarrow, pa_compute, text_view)
            operation_mask = pa_compute.if_else(
                numeric_mask,
                compare(numeric_values, numeric_target),
                compare(text_view, needle),
            )
        else:
            operation_mask = compare(text_view, needle)
    elif op in {"equals", "eq"}:
        operation_mask = pa_compute.equal(pa_compute.utf8_trim_whitespace(text_view), needle.strip())
    elif op == "startswith":
        operation_mask = pa_compute.starts_with(text_view, needle)
    elif op == "endswith":
        operation_mask = pa_compute.ends_with(text_view, needle)
    else:
        operation_mask = pa_compute.match_substring(text_view, needle)
    return pa_compute.and_kleene(
        pa_compute.fill_null(present_mask, False),
        pa_compute.fill_null(operation_mask, False),
    )


def _arrow_predicate_mask(
    pyarrow: Any,
    pa_compute: Any,
    table: Any,
    predicate: QueryFilter,
    selected_columns: Sequence[str],
    text_view_for: Callable[[str], Any],
) -> Any:
    columns = (predicate.column,) if predicate.column else tuple(selected_columns)
    columns = tuple(column for column in columns if column in table.column_names)
    if not columns:
        if predicate.op == "not_contains":
            return pa_compute.cast(pyarrow.array([True] * table.num_rows), pyarrow.bool_())
        return pa_compute.cast(pyarrow.array([False] * table.num_rows), pyarrow.bool_())
    if predicate.op == "not_contains":
        mask = None
        for column in columns:
            column_values = table.column(column)
            text_view = text_view_for(column)
            present = pa_compute.fill_null(
                _arrow_value_present_mask(pyarrow, pa_compute, column_values, text_view),
                False,
            )
            contains = pa_compute.fill_null(
                pa_compute.match_substring(text_view, predicate.value.lower()),
                False,
            )
            inverted = pa_compute.invert(pa_compute.and_(present, contains))
            mask = inverted if mask is None else pa_compute.and_(mask, inverted)
        return mask
    mask = None
    for column in columns:
        cell_mask = pa_compute.fill_null(
            _arrow_cell_op_mask(
                pyarrow,
                pa_compute,
                table.column(column),
                predicate.op,
                predicate.value,
                text_view_for(column),
            ),
            False,
        )
        mask = cell_mask if mask is None else pa_compute.or_(mask, cell_mask)
    return mask


def _query_sort_key(value: Any) -> tuple[int, float, str]:
    if value is None:
        return (2, 0.0, "")
    if isinstance(value, bool):
        return (0, float(value), "")
    if isinstance(value, (int, float)):
        numeric = float(value)
        return (0, numeric, "") if math.isfinite(numeric) else (2, 0.0, "")
    text = str(value).strip()
    if not text:
        return (2, 0.0, "")
    try:
        return (0, float(text), "")
    except ValueError:
        return (1, 0.0, text.lower())


__all__ = [
    "NormalizedPreviewQuery",
    "PreviewQueryResult",
    "QueryFilter",
    "evaluate_arrow_query",
    "evaluate_python_query",
]
