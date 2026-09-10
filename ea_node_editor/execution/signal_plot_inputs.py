# Purpose: Normalize Signal Plot sources into aligned, ordered, read-only X/Y traces.
# Map: feature_routes/plotter_nodes
# Tests: tests/test_signal_plot_inputs.py
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Any

import numpy as np

from ea_node_editor.runtime_contracts import (
    ArrayDataRef,
    ArrayMaterializationOptions,
    ArraySlice2DRef,
    DataTree,
    TabularDataRef,
    TabularWindowRef,
    coerce_array_data_ref,
    coerce_array_slice_2d_ref,
    coerce_tabular_data_ref,
    coerce_tabular_window_ref,
)
from ea_node_editor.runtime_contracts.scientific_values import (
    ArrayValue,
    TableValue,
    snapshot_scientific_value,
)


@dataclass(frozen=True, slots=True)
class SignalTrace:
    x: np.ndarray
    y: np.ndarray
    label: str
    x_kind: str = "numeric"


@dataclass(frozen=True, slots=True)
class _Columns:
    names: tuple[Any, ...]
    kinds: tuple[str, ...]
    read: Callable[[Sequence[int]], dict[int, np.ndarray]]
    indexed: bool = False


def _dtype_kind(dtype: str) -> str:
    text = dtype.lower()
    if not text:
        return "unknown"
    if text.startswith(("timestamp[", "date32[", "date64[")) or text == "datetime_tz":
        return "datetime"
    if text in {"bool", "boolean"}:
        return "boolean"
    try:
        kind = np.dtype(dtype).kind
    except TypeError:
        try:
            kind = np.dtype(text).kind
        except TypeError:
            return "other"
    return {"i": "numeric", "u": "numeric", "f": "numeric", "M": "datetime", "b": "boolean"}.get(kind, "other")


def _selector(value: Any, names: Sequence[Any], field: str) -> int:
    if type(value) is int and 0 <= value < len(names):
        return value
    if type(value) is str:
        matches = [index for index, name in enumerate(names) if type(name) is str and name == value]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"{field} name {value!r} is duplicated; select a zero-based column position")
    raise ValueError(f"{field} {value!r} does not identify an available column; use an exact name or zero-based position")


def _readonly(array: Any) -> np.ndarray:
    result = np.asarray(array).view()
    result.flags.writeable = False
    return result


def _infer_file_column(array: np.ndarray) -> tuple[np.ndarray, str]:
    """Infer numeric values only for file sources that have no typed schema."""
    if array.dtype.kind != "O":
        kind = _dtype_kind(array.dtype.str)
        if kind != "other":
            return array, kind
    # Direct CSV sources expose numeric cells as strings. Date strings remain text.
    present = [value for value in array if value is not None and not (isinstance(value, str) and not value.strip())]
    if present and all(isinstance(value, (bool, np.bool_)) for value in present):
        return array, "boolean"
    if present and any(isinstance(value, (bool, np.bool_)) for value in present):
        return array, "other"
    try:
        numeric = np.asarray([
            np.nan if value is None or isinstance(value, str) and not value.strip() else value
            for value in array
        ], dtype=np.float64)
    except (ValueError, TypeError):
        return array, "other"
    return numeric, "numeric" if present else "other"


def _array_columns(array: np.ndarray) -> _Columns:
    if array.ndim not in {1, 2}:
        raise ValueError("Values arrays must be one- or two-dimensional")
    if not len(array) or array.ndim == 2 and not array.shape[1]:
        raise ValueError("Values must contain a non-empty signal")
    width = 1 if array.ndim == 1 else array.shape[1]
    kind = _dtype_kind(array.dtype.str)
    return _Columns(
        (None,) * width,
        (kind,) * width,
        lambda positions: {i: array if array.ndim == 1 else array[:, i] for i in positions},
        indexed=array.ndim == 1,
    )


def _plain_columns(value: Sequence[Any]) -> _Columns:
    try:
        raw = np.asarray(value, dtype=object)
    except ValueError as exc:
        raise ValueError("Values matrices must be rectangular, with equally sized rows") from exc
    if raw.ndim not in {1, 2}:
        raise ValueError("Values matrices must be one- or two-dimensional")
    if raw.ndim == 1 and any(isinstance(item, (list, tuple, np.ndarray)) for item in raw):
        raise ValueError("Values matrices must be rectangular, with equally sized rows")
    if not len(raw) or raw.ndim == 2 and not raw.shape[1]:
        raise ValueError("Values must contain a non-empty signal")
    # Classify before NumPy can turn a Boolean column into ints, or numeric
    # columns into strings merely because a neighbouring column contains text.
    width = 1 if raw.ndim == 1 else raw.shape[1]
    arrays, kinds = {}, []
    for i in range(width):
        samples = list(raw if raw.ndim == 1 else raw[:, i])
        present = [item for item in samples if item is not None]
        if present and all(isinstance(item, (bool, np.bool_)) for item in present):
            kind = "boolean"
        elif all(isinstance(item, Real) and not isinstance(item, (bool, np.bool_)) for item in present):
            kind = "numeric"
        else:
            kind = "other"
        if raw.ndim == 1 and kind != "numeric":
            raise ValueError("Values sequences must contain real numeric samples or missing values, without Boolean samples")
        arrays[i] = np.asarray(samples, dtype=np.float64 if len(present) != len(samples) else None) if kind == "numeric" else np.asarray(samples, dtype=object)
        kinds.append(kind)
    return _Columns((None,) * width, tuple(kinds), lambda positions: {i: arrays[i] for i in positions}, indexed=raw.ndim == 1)


def _ref_option(ref: TabularDataRef | ArrayDataRef, key: str, default: Any) -> Any:
    options = ref.metadata.get("node_options")
    if isinstance(options, Mapping) and key in options:
        return options[key]
    return ref.metadata.get(key, default)


def _table_columns(ref: TabularDataRef | TabularWindowRef, service: Any) -> _Columns:
    base = ref.table_data if isinstance(ref, TabularWindowRef) else ref
    schema = service.column_schema(base)
    all_names = tuple(column.name for column in schema.columns)
    selected = () if isinstance(ref, TabularWindowRef) else _ref_option(base, "selected_columns", ())
    if isinstance(selected, str):
        raise ValueError("Selected source columns must be an ordered list of names")
    positions = tuple(_selector(name, all_names, "Selected source column") for name in selected) if selected else tuple(range(len(all_names)))
    names = tuple(all_names[i] for i in positions)
    offset, limit = 0, None
    if isinstance(ref, TabularWindowRef):
        if ref.columns:
            chosen = tuple(_selector(name, names, "Window column") for name in ref.columns)
            if ref.column_limit:
                chosen = chosen[:ref.column_limit]
        else:
            stop = ref.column_offset + ref.column_limit if ref.column_limit else None
            chosen = tuple(range(len(names)))[ref.column_offset:stop]
        positions = tuple(positions[i] for i in chosen)
        names = tuple(all_names[i] for i in positions)
        offset, limit = ref.row_offset, ref.row_limit or None
    kinds = tuple(_dtype_kind(schema.columns[i].dtype) for i in positions)

    def read(requested: Sequence[int]) -> dict[int, np.ndarray]:
        keys = {i: positions[i] if all_names.count(names[i]) > 1 else names[i] for i in requested}
        data = service.column_arrays(base, columns=tuple(keys.values()), row_offset=offset, row_limit=limit)
        result = {}
        for i in requested:
            values = data[keys[i]]
            if kinds[i] == "numeric" and values.dtype.kind not in "iuf":
                has_missing = any(value is None or isinstance(value, str) and not value.strip() for value in values)
                dtype = np.float64 if has_missing else np.dtype(schema.columns[positions[i]].dtype)
                values = np.asarray([
                    np.nan if value is None or isinstance(value, str) and not value.strip() else value
                    for value in values
                ], dtype=dtype)
            elif kinds[i] == "datetime" and values.dtype.kind != "M":
                # The source schema supplies datetime semantics; strings alone never do.
                values = np.asarray(values, dtype="datetime64[us]")
            result[i] = values
        return result

    return _Columns(names, kinds, read)


def _array_ref_columns(ref: ArrayDataRef | ArraySlice2DRef, service: Any) -> _Columns:
    base = ref.array_data if isinstance(ref, ArraySlice2DRef) else ref
    service.ensure_array_ref(base)
    if len(base.shape) not in {1, 2}:
        raise ValueError("Values array references must be one- or two-dimensional")
    rows, width = base.shape[0], base.shape[1] if len(base.shape) == 2 else 1
    hints = {} if isinstance(ref, ArraySlice2DRef) else _ref_option(base, "array_slice_2d", {})
    if not isinstance(hints, Mapping):
        raise ValueError("Array slice metadata must be a mapping")
    row_start, col_start, row_stop, col_stop = 0, 0, rows, width
    requests = [hints]
    if isinstance(ref, ArraySlice2DRef):
        requests.append({key: getattr(ref, key) for key in ("row_offset", "column_offset", "row_limit", "column_limit")})
    for request in requests:
        bounds = {key: request.get(key, 0) for key in ("row_offset", "column_offset", "row_limit", "column_limit")}
        if any(type(value) is not int or value < 0 for value in bounds.values()):
            raise ValueError("Array slice bounds must be non-negative integers")
        row_start = max(row_start, bounds["row_offset"])
        col_start = max(col_start, bounds["column_offset"])
        if bounds["row_limit"]:
            row_stop = min(row_stop, bounds["row_offset"] + bounds["row_limit"])
        if bounds["column_limit"]:
            col_stop = min(col_stop, bounds["column_offset"] + bounds["column_limit"])
    if row_start >= row_stop or col_start >= col_stop:
        raise ValueError("Values array selection must contain a non-empty signal")

    def read(positions: Sequence[int]) -> dict[int, np.ndarray]:
        if positions and base.metadata.get("format_id") == "npz":
            # An archive decompresses the complete array; share that one allocation.
            slices = ((row_start, row_stop - row_start),)
            if len(base.shape) == 2:
                slices += ((col_start, col_stop - col_start),)
            values = service.to_numpy(base, ArrayMaterializationOptions(slices=slices))
            return {i: values[:, i] if values.ndim == 2 else values for i in positions}
        result = {}
        for i in positions:
            slices = ((row_start, row_stop - row_start),)
            if len(base.shape) == 2:
                slices += ((col_start + i, 1),)
            values = service.to_numpy(base, ArrayMaterializationOptions(slices=slices))
            result[i] = values[:, 0] if values.ndim == 2 else values
        return result

    return _Columns((None,) * (col_stop - col_start), (_dtype_kind(base.dtype),) * (col_stop - col_start), read, indexed=len(base.shape) == 1)


def _source_columns(value: Any, service: Any) -> _Columns:
    captured = snapshot_scientific_value(value)
    if isinstance(captured, ArrayValue):
        return _array_columns(captured.to_numpy(copy=False))
    if isinstance(captured, TableValue):
        return _Columns(
            captured.column_names,
            tuple(_dtype_kind(column.dtype) for column in captured.columns),
            lambda positions: {i: captured.column_values(i) for i in positions},
            indexed=captured.kind == "series",
        )
    for coerce, table in ((coerce_tabular_window_ref, True), (coerce_tabular_data_ref, True), (coerce_array_slice_2d_ref, False), (coerce_array_data_ref, False)):
        ref = coerce(value)
        if ref is not None:
            if service is None:
                from ea_node_editor.addons.tabular_data.loader_cache_service import shared_tabular_loader_cache_service
                service = shared_tabular_loader_cache_service()
            return _table_columns(ref, service) if table else _array_ref_columns(ref, service)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return _plain_columns(value)
    raise ValueError("Values must be a numeric sequence, scientific array/table, or tabular/array reference")


def _traces(columns: _Columns, *, x_mode: str, x_column: Any, y_columns: Sequence[Any], logarithmic_y: bool) -> tuple[SignalTrace, ...]:
    names, kinds = columns.names, list(columns.kinds)
    y_positions = tuple(_selector(value, names, "Y column") for value in y_columns)
    if len(set(y_positions)) != len(y_positions):
        raise ValueError("Y columns must select distinct columns")
    x_position = _selector(x_column, names, "X column") if x_mode == "column" else None
    cache: dict[int, np.ndarray] = {}
    # With an untyped file, automatic mapping must inspect candidate columns.
    unknown = [i for i, kind in enumerate(kinds) if kind == "unknown" and (not y_positions or i in y_positions or x_mode == "auto" or i == x_position)]
    if unknown:
        for i, values in columns.read(unknown).items():
            cache[i], kinds[i] = _infer_file_column(values)
    numeric = [i for i, kind in enumerate(kinds) if kind == "numeric"]
    if x_mode == "auto" and not columns.indexed:
        usable = [i for i, kind in enumerate(kinds) if kind in {"numeric", "datetime"}]
        if len(usable) > 1:
            x_position = usable[0]
    if x_position is not None and kinds[x_position] not in {"numeric", "datetime"}:
        raise ValueError("X column must contain real numeric or typed datetime values")
    if not y_positions:
        y_positions = tuple(i for i in numeric if i != x_position)
    if not y_positions:
        raise ValueError("Values source has no numeric Y columns")
    if any(kinds[i] != "numeric" for i in y_positions):
        raise ValueError("Y columns must contain real numeric values; text, Boolean, complex and datetime columns are unsupported")
    needed = tuple(dict.fromkeys((*y_positions, *((x_position,) if x_position is not None else ()))))
    missing = tuple(i for i in needed if i not in cache)
    if missing:
        cache.update(columns.read(missing))
    result = []
    for i in y_positions:
        y = cache[i]
        if y.ndim != 1 or not len(y):
            raise ValueError("Values must contain a non-empty one-dimensional signal")
        if logarithmic_y and not np.any(np.isfinite(y) & (y > 0)):
            raise ValueError(f"Values column {i} has no positive finite samples for logarithmic Y")
        x = cache[x_position] if x_position is not None else np.arange(len(y))
        if x.ndim != 1 or len(x) != len(y):
            raise ValueError("Signal X and Y columns must have matching row counts")
        label = str(names[i]) if names[i] is not None else ("" if columns.indexed else f"Column {i + 1}")
        result.append(SignalTrace(_readonly(x), _readonly(y), label, kinds[x_position] if x_position is not None else "numeric"))
    return tuple(result)


def normalize_signal_inputs(
    values: Any,
    *,
    x_mode: str = "auto",
    x_column: str | int = "",
    y_columns: Sequence[str | int] = (),
    logarithmic_y: bool = False,
    service: Any = None,
) -> tuple[SignalTrace, ...]:
    """Preserve source rows/gaps; each numeric tree branch is one indexed trace."""
    if x_mode not in {"auto", "index", "column"}:
        raise ValueError("X mode must be auto, index or column")
    if isinstance(y_columns, (str, bytes)) or not isinstance(y_columns, Sequence):
        raise ValueError("Y columns must be an ordered list of exact names or zero-based positions")
    sources = []
    if isinstance(values, DataTree):
        for _path, items in values.branches:
            if not items or all(item is None or isinstance(item, Real) and not isinstance(item, (bool, np.bool_)) for item in items):
                sources.append(items)
            else:
                sources.extend(items)
    else:
        sources.append(values)
    result = []
    for value in sources:
        result.extend(_traces(_source_columns(value, service), x_mode=x_mode, x_column=x_column, y_columns=y_columns, logarithmic_y=logarithmic_y))
    if not result:
        raise ValueError("Values must contain at least one non-empty signal")
    return tuple(result)
