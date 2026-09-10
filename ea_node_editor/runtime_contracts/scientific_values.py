# Purpose: Own immutable scientific buffers and native Python boundary adapters.
# Map: subsystems/supporting_runtime_assets.md
# Tests: tests/test_scientific_values.py

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ea_node_editor.common.payload_tools import JSON_MAX_DEPTH
from ea_node_editor.runtime_contracts.data_tree import DataTree

ARRAY_VALUE_TYPE_ID = "COREX.DataTypes.ArrayValue"
TABLE_VALUE_TYPE_ID = "COREX.DataTypes.TableValue"
SERIES_VALUE_TYPE_ID = "COREX.DataTypes.SeriesValue"
SCIENTIFIC_VALUE_MAX_BYTES = 256 * 1024 * 1024
SCIENTIFIC_OPERATION_MAX_BYTES = 512 * 1024 * 1024
_DTYPE = re.compile(
    r"[<>=|]([biufcmMSU])([0-9]+)(?:\[([0-9]*)(Y|M|W|D|h|m|s|ms|us|ns|ps|fs|as)\])?\Z"
)
_NULLABLE = re.compile(r"(?:U?Int(?:8|16|32|64)|Float(?:32|64)|boolean)\Z")
_STRING_DTYPES = frozenset(
    {
        "object",
        "string:python:NA",
        "string:pyarrow:NA",
        "string:python:nan",
        "string:pyarrow:nan",
    }
)


def _numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise ImportError(
            "Scientific array values require NumPy in the execution Python environment."
        ) from exc
    return np


def _pandas():
    try:
        import pandas as pd
    except ImportError as exc:
        raise ImportError(
            "Scientific table values require pandas in the execution Python environment."
        ) from exc
    return pd


def array_layout(dtype: str, shape: tuple[int, ...]) -> int:
    if type(dtype) is not str or len(dtype) > 128 or _DTYPE.fullmatch(dtype) is None:
        raise ValueError(
            "Unsupported scientific dtype; object, structured and custom dtypes are not supported"
        )
    parsed = _numpy().dtype(dtype)
    if parsed.hasobject or parsed.fields is not None or parsed.subdtype is not None:
        raise ValueError("Unsupported scientific dtype")
    if (
        type(shape) is not tuple
        or len(shape) > 32
        or any(type(n) is not int or not 0 <= n <= 2**31 - 1 for n in shape)
    ):
        raise ValueError(
            "Scientific array shape requires at most 32 bounded non-negative integer dimensions"
        )
    count = math.prod(shape)
    if count * max(1, parsed.itemsize) > SCIENTIFIC_VALUE_MAX_BYTES:
        raise ValueError("Scientific value exceeds the 256 MiB decoded-content limit")
    return count * parsed.itemsize


def _label(value: Any) -> Any:
    # Labels are metadata, never payload-selected objects or constructors.
    if (
        value is None
        or type(value) in {str, bool, int}
        or type(value) is float
        and math.isfinite(value)
    ):
        return value
    if type(value).__module__.split(".")[0] == "numpy" and isinstance(
        value, _numpy().generic
    ):
        return _label(value.item())
    raise TypeError(
        "Scientific column/index names must be finite scalar text, numbers, booleans or None"
    )


def column_layout(
    dtype: str,
    data_dtype: str,
    shape: tuple[int, ...],
    nbytes: int,
    mask_size: int,
    offsets: tuple[int, ...],
    timezone: str,
) -> int:
    """Validate metadata without decoding or allocating the column buffers."""
    if type(dtype) is not str or len(shape) != 1 or type(timezone) is not str:
        raise ValueError(
            "Scientific column requires a one-dimensional array and text dtype/timezone"
        )
    rows = len(offsets) - 1 if offsets else shape[0]
    if dtype in _STRING_DTYPES:
        if (
            data_dtype != "|u1"
            or not offsets
            or offsets[0] != 0
            or offsets[-1] != nbytes
        ):
            raise ValueError("Scientific UTF-8 column requires exact byte offsets")
        previous = 0
        for offset in offsets:
            if type(offset) is not int or not previous <= offset <= nbytes:
                raise ValueError("Scientific UTF-8 offsets must be ordered and bounded")
            previous = offset
        if mask_size != rows or timezone:
            raise ValueError(
                "Scientific string missing-value mask or timezone is invalid"
            )
    elif _NULLABLE.fullmatch(dtype):
        expected = "bool" if dtype == "boolean" else dtype.lower()
        if (
            _numpy().dtype(expected) != _numpy().dtype(data_dtype)
            or offsets
            or timezone
        ):
            raise ValueError("Nullable column dtype does not match its storage")
        if mask_size != rows:
            raise ValueError("Scientific nullable mask length is invalid")
    elif dtype == "datetime_tz":
        if (
            not timezone
            or len(timezone) > 256
            or _numpy().dtype(data_dtype).kind != "M"
            or mask_size
            or offsets
        ):
            raise ValueError("Timezone datetime column metadata is invalid")
        _pandas().DatetimeTZDtype(
            unit=_numpy().datetime_data(_numpy().dtype(data_dtype))[0], tz=timezone
        )
    elif dtype != data_dtype or mask_size or offsets or timezone:
        raise ValueError("Scientific primitive column metadata is invalid")
    return rows


def table_layout(
    kind: str,
    column_rows: tuple[int, ...],
    column_names: tuple[Any, ...],
    index_rows: int | None,
    range_index: tuple[int, int, int] | None,
    index_name: Any,
    columns_name: Any,
) -> int:
    if (
        kind not in {"series", "frame"}
        or len(column_rows) != len(column_names)
        or kind == "series"
        and len(column_rows) != 1
    ):
        raise ValueError(
            "Scientific table kind and column labels must match its columns"
        )
    for label in (*column_names, index_name, columns_name):
        _label(label)
    if (index_rows is None) == (range_index is None):
        raise ValueError("Scientific table requires exactly one index representation")
    if range_index is not None:
        if (
            type(range_index) is not tuple
            or len(range_index) != 3
            or any(type(n) is not int or abs(n) > 2**63 - 1 for n in range_index)
            or range_index[2] == 0
        ):
            raise ValueError(
                "Scientific RangeIndex requires bounded start, stop and nonzero step"
            )
        try:
            rows = len(range(*range_index))
        except OverflowError as exc:
            raise ValueError("Scientific RangeIndex exceeds the row limit") from exc
    else:
        rows = index_rows
    if rows > SCIENTIFIC_VALUE_MAX_BYTES or any(n != rows for n in column_rows):
        raise ValueError(
            "Scientific table columns and index must have matching bounded row counts"
        )
    return rows


@dataclass(frozen=True, slots=True)
class ArrayValue:
    """C-contiguous logical array whose bytes have no writable owner."""

    dtype: str
    shape: tuple[int, ...]
    buffer: bytes

    def __post_init__(self) -> None:
        size = array_layout(self.dtype, self.shape)
        if type(self.buffer) is not bytes or len(self.buffer) != size:
            raise ValueError(
                "Scientific array buffer length must match dtype and shape exactly"
            )

    @property
    def data_type_id(self) -> str:
        return ARRAY_VALUE_TYPE_ID

    @property
    def nbytes(self) -> int:
        return len(self.buffer)

    def to_numpy(self, *, copy: bool = False):
        result = _numpy().frombuffer(self.buffer, dtype=self.dtype).reshape(self.shape)
        return result.copy() if copy else result

    @classmethod
    def from_numpy(cls, value: Any) -> ArrayValue:
        np = _numpy()
        if type(value) is not np.ndarray:
            raise TypeError(
                "Scientific arrays require an exact numpy.ndarray; subclasses are unsupported"
            )
        array_layout(value.dtype.str, tuple(value.shape))
        return cls(value.dtype.str, tuple(value.shape), value.tobytes(order="C"))


@dataclass(frozen=True, slots=True)
class ColumnValue:
    """A primitive, nullable, datetime or UTF-8 column with immutable buffers."""

    dtype: str
    data: ArrayValue
    mask: bytes = b""
    offsets: tuple[int, ...] = ()
    timezone: str = ""

    def __post_init__(self) -> None:
        if (
            type(self.dtype) is not str
            or type(self.data) is not ArrayValue
            or len(self.data.shape) != 1
        ):
            raise ValueError("Scientific column requires a one-dimensional ArrayValue")
        if (
            type(self.mask) is not bytes
            or type(self.offsets) is not tuple
            or type(self.timezone) is not str
        ):
            raise TypeError("Scientific column metadata must be immutable")
        column_layout(
            self.dtype,
            self.data.dtype,
            self.data.shape,
            self.data.nbytes,
            len(self.mask),
            self.offsets,
            self.timezone,
        )
        if self.dtype in _STRING_DTYPES:
            previous = 0
            for offset in self.offsets:
                self.data.buffer[previous:offset].decode("utf-8")
                previous = offset
            if any(n > 4 for n in self.mask):
                raise ValueError("Scientific string missing-value mask is invalid")
        elif _NULLABLE.fullmatch(self.dtype):
            if any(n > 1 for n in self.mask):
                raise ValueError("Scientific nullable mask is invalid")

    @property
    def row_count(self) -> int:
        return len(self.offsets) - 1 if self.offsets else self.data.shape[0]

    @property
    def nbytes(self) -> int:
        return (
            self.data.nbytes
            + len(self.mask)
            + 8 * len(self.offsets)
            + len(self.dtype.encode())
            + len(self.timezone.encode())
        )

    def to_numpy(self):
        """Read-only plot access; nullable numeric values use NaN for missing samples."""
        np = _numpy()
        if self.offsets:
            result = np.asarray(self._strings(), dtype=object)
        elif self.mask:
            result = self.data.to_numpy().astype(float)
            result[np.frombuffer(self.mask, dtype="u1").astype(bool)] = np.nan
        else:
            return self.data.to_numpy()
        result.flags.writeable = False
        return result

    def _strings(self) -> list[Any]:
        pd = _pandas()
        missing = (None, None, float("nan"), pd.NA, pd.NaT)
        return [
            missing[self.mask[i]]
            if self.mask[i]
            else self.data.buffer[start:end].decode("utf-8")
            for i, (start, end) in enumerate(zip(self.offsets, self.offsets[1:]))
        ]

    def to_pandas_array(self):
        pd = _pandas()
        if self.offsets:
            if self.dtype == "object":
                return _numpy().asarray(self._strings(), dtype=object)
            _, storage, missing = self.dtype.split(":")
            dtype = pd.StringDtype(
                storage=storage, na_value=pd.NA if missing == "NA" else float("nan")
            )
            return pd.array(self._strings(), dtype=dtype)
        values = self.data.to_numpy(copy=True)
        if _NULLABLE.fullmatch(self.dtype):
            mask = _numpy().frombuffer(self.mask, dtype="u1").astype(bool)
            constructor = (
                pd.arrays.BooleanArray
                if self.dtype == "boolean"
                else pd.arrays.FloatingArray
                if self.dtype.startswith("Float")
                else pd.arrays.IntegerArray
            )
            return constructor(values, mask)
        if self.timezone:
            return (
                pd.DatetimeIndex(values)
                .tz_localize("UTC")
                .tz_convert(self.timezone)
                .array
            )
        return values


@dataclass(frozen=True, slots=True)
class TableValue:
    kind: str
    columns: tuple[ColumnValue, ...]
    column_names: tuple[Any, ...]
    index: ColumnValue | None
    range_index: tuple[int, int, int] | None
    index_name: Any = None
    columns_name: Any = None

    def __post_init__(self) -> None:
        if (
            self.kind not in {"series", "frame"}
            or type(self.columns) is not tuple
            or not all(type(c) is ColumnValue for c in self.columns)
        ):
            raise ValueError(
                "Scientific table requires immutable columns and a series/frame kind"
            )
        if type(self.column_names) is not tuple:
            raise ValueError("Scientific table requires immutable column labels")
        if self.index is not None and type(self.index) is not ColumnValue:
            raise TypeError("Scientific table index must be a ColumnValue")
        table_layout(
            self.kind,
            tuple(c.row_count for c in self.columns),
            self.column_names,
            self.index.row_count if self.index is not None else None,
            self.range_index,
            self.index_name,
            self.columns_name,
        )
        object.__setattr__(
            self, "column_names", tuple(_label(n) for n in self.column_names)
        )
        object.__setattr__(self, "index_name", _label(self.index_name))
        object.__setattr__(self, "columns_name", _label(self.columns_name))
        if self.nbytes > SCIENTIFIC_VALUE_MAX_BYTES:
            raise ValueError(
                "Scientific value exceeds the 256 MiB decoded-content limit"
            )

    @property
    def data_type_id(self) -> str:
        return SERIES_VALUE_TYPE_ID if self.kind == "series" else TABLE_VALUE_TYPE_ID

    @property
    def row_count(self) -> int:
        return (
            self.index.row_count
            if self.index is not None
            else len(range(*self.range_index))
        )

    @property
    def nbytes(self) -> int:
        labels = sum(
            len(str(n).encode("utf-8"))
            for n in (*self.column_names, self.index_name, self.columns_name)
        )
        return (
            sum(c.nbytes for c in self.columns)
            + (self.index.nbytes if self.index else 24)
            + labels
        )

    def column_values(self, position: int):
        return self.columns[position].to_numpy()

    def to_pandas(self):
        pd = _pandas()
        index = (
            pd.Index(self.index.to_pandas_array(), name=self.index_name)
            if self.index
            else pd.RangeIndex(*self.range_index, name=self.index_name)
        )
        if self.kind == "series":
            return pd.Series(
                self.columns[0].to_pandas_array(),
                index=index,
                name=self.column_names[0],
                dtype=object if self.columns[0].dtype == "object" else None,
            )
        result = pd.DataFrame(
            {
                i: pd.Series(
                    col.to_pandas_array(),
                    index=index,
                    dtype=object if col.dtype == "object" else None,
                )
                for i, col in enumerate(self.columns)
            },
            index=index,
        )
        result.columns = pd.Index(
            self.column_names, name=self.columns_name, tupleize_cols=False
        )
        return result


def _column(value: Any) -> ColumnValue:
    np, pd = _numpy(), _pandas()
    dtype = value.dtype
    _validate_pandas_dtype(dtype)
    if isinstance(dtype, pd.CategoricalDtype):
        raise TypeError(
            "Categorical scientific columns are unsupported; convert them to strings or numbers"
        )
    if isinstance(dtype, pd.DatetimeTZDtype):
        utc = value.to_numpy(dtype=f"datetime64[{dtype.unit}]")
        return ColumnValue(
            "datetime_tz", ArrayValue.from_numpy(utc), timezone=str(dtype.tz)
        )
    if isinstance(dtype, pd.StringDtype) or dtype == object:
        parts, offsets, mask = [], [0], bytearray()
        for item in value:
            if type(item) is str:
                encoded, missing = item.encode("utf-8"), 0
            elif item is None:
                encoded, missing = b"", 1
            elif item is pd.NA:
                encoded, missing = b"", 3
            elif item is pd.NaT:
                encoded, missing = b"", 4
            elif isinstance(item, (float, np.floating)) and math.isnan(item):
                encoded, missing = b"", 2
            else:
                raise TypeError(
                    "Object-dtype pandas columns support only strings and missing values"
                )
            parts.append(encoded)
            offsets.append(offsets[-1] + len(encoded))
            mask.append(missing)
            if offsets[-1] + len(offsets) * 8 + len(mask) > SCIENTIFIC_VALUE_MAX_BYTES:
                raise ValueError(
                    "Scientific value exceeds the 256 MiB decoded-content limit"
                )
        raw = b"".join(parts)
        logical = (
            "object"
            if dtype == object
            else f"string:{dtype.storage}:{'NA' if dtype.na_value is pd.NA else 'nan'}"
        )
        return ColumnValue(
            logical, ArrayValue("|u1", (len(raw),), raw), bytes(mask), tuple(offsets)
        )
    logical = str(dtype)
    if _NULLABLE.fullmatch(logical):
        storage = "bool" if logical == "boolean" else logical.lower()
        array = value.to_numpy(dtype=storage, na_value=0)
        return ColumnValue(
            logical,
            ArrayValue.from_numpy(array),
            np.asarray(value.isna(), dtype="u1").tobytes(),
        )
    if isinstance(dtype, pd.api.extensions.ExtensionDtype):
        raise TypeError(
            "Custom pandas extension dtypes are unsupported; convert to standard numeric, string or datetime columns"
        )
    array = ArrayValue.from_numpy(value.to_numpy())
    return ColumnValue(array.dtype, array)


def _validate_pandas_dtype(dtype: Any) -> None:
    pd = _pandas()
    allowed = {
        pd.StringDtype,
        pd.DatetimeTZDtype,
        pd.BooleanDtype,
        pd.Int8Dtype,
        pd.Int16Dtype,
        pd.Int32Dtype,
        pd.Int64Dtype,
        pd.UInt8Dtype,
        pd.UInt16Dtype,
        pd.UInt32Dtype,
        pd.UInt64Dtype,
        pd.Float32Dtype,
        pd.Float64Dtype,
    }
    if (
        isinstance(dtype, pd.api.extensions.ExtensionDtype)
        and type(dtype) not in allowed
    ):
        raise TypeError(
            "Categorical and custom pandas extension dtypes are unsupported; convert to standard numeric, string or datetime columns"
        )


def _native_column_size(value: Any) -> int:
    """Preflight content bounds before creating any owned scientific buffers."""
    pd, np = _pandas(), _numpy()
    dtype = value.dtype
    _validate_pandas_dtype(dtype)
    if isinstance(dtype, pd.StringDtype) or dtype == object:
        logical = (
            "object"
            if dtype == object
            else f"string:{dtype.storage}:{'NA' if dtype.na_value is pd.NA else 'nan'}"
        )
        size = 8 * (len(value) + 1) + len(value) + len(logical.encode())
        for item in value:
            if type(item) is str:
                size += len(item.encode("utf-8"))
            elif not (
                item is None
                or item is pd.NA
                or item is pd.NaT
                or isinstance(item, (float, np.floating))
                and math.isnan(item)
            ):
                raise TypeError(
                    "Object-dtype pandas columns support only strings and missing values"
                )
            if size > SCIENTIFIC_VALUE_MAX_BYTES:
                raise ValueError(
                    "Scientific value exceeds the 256 MiB decoded-content limit"
                )
        return size
    if isinstance(dtype, pd.DatetimeTZDtype):
        return len(value) * 8 + len("datetime_tz") + len(str(dtype.tz).encode())
    if _NULLABLE.fullmatch(str(dtype)):
        return len(value) * (dtype.numpy_dtype.itemsize + 1) + len(str(dtype).encode())
    array_layout(dtype.str, (len(value),))
    return len(value) * dtype.itemsize + len(dtype.str.encode())


def _native_scientific_size(value: Any) -> int | None:
    modules = {base.__module__.split(".")[0] for base in type(value).__mro__}
    if "numpy" in modules:
        np = _numpy()
        if isinstance(value, np.ndarray):
            if type(value) is not np.ndarray:
                raise TypeError(
                    "Scientific arrays require an exact numpy.ndarray; subclasses are unsupported"
                )
            return array_layout(value.dtype.str, tuple(value.shape))
    if "pandas" not in modules:
        return None
    pd = _pandas()
    if type(value) not in {pd.Series, pd.DataFrame}:
        raise TypeError(
            "Scientific pandas values require an exact Series or DataFrame; subclasses are unsupported"
        )
    if isinstance(value.index, pd.MultiIndex) or isinstance(
        getattr(value, "columns", None), pd.MultiIndex
    ):
        raise TypeError(
            "MultiIndex is unsupported; flatten the index/columns before returning the value"
        )
    is_series = type(value) is pd.Series
    labels = (value.name,) if is_series else tuple(value.columns)
    labels += (value.index.name, None if is_series else value.columns.name)
    size = sum(len(str(_label(label)).encode()) for label in labels)
    size += (
        24 if type(value.index) is pd.RangeIndex else _native_column_size(value.index)
    )
    columns = (
        (value,) if is_series else (value.iloc[:, i] for i in range(value.shape[1]))
    )
    for column in columns:
        size += _native_column_size(column)
        if size > SCIENTIFIC_VALUE_MAX_BYTES:
            raise ValueError(
                "Scientific value exceeds the 256 MiB decoded-content limit"
            )
    return size


def snapshot_scientific_value(value: Any) -> Any:
    """Capture a native object once; all retained data is owned immutable storage."""
    if type(value) in {ArrayValue, TableValue}:
        return value
    size = _native_scientific_size(value)
    if size is None:
        return value
    if size > SCIENTIFIC_VALUE_MAX_BYTES:
        raise ValueError("Scientific value exceeds the 256 MiB decoded-content limit")
    module = type(value).__module__.split(".")[0]
    # The MRO check catches locally declared ndarray/DataFrame subclasses too.
    modules = {base.__module__.split(".")[0] for base in type(value).__mro__}
    if module == "numpy" or "numpy" in modules:
        return ArrayValue.from_numpy(value)
    if module != "pandas" and "pandas" not in modules:
        return value
    pd = _pandas()
    if type(value) not in {pd.Series, pd.DataFrame}:
        raise TypeError(
            "Scientific pandas values require an exact Series or DataFrame; subclasses are unsupported"
        )
    if isinstance(value.index, pd.MultiIndex) or isinstance(
        getattr(value, "columns", None), pd.MultiIndex
    ):
        raise TypeError(
            "MultiIndex is unsupported; flatten the index/columns before returning the value"
        )
    is_series = type(value) is pd.Series
    columns = (
        (value,) if is_series else (value.iloc[:, i] for i in range(value.shape[1]))
    )
    index = value.index
    range_index = (
        (index.start, index.stop, index.step) if type(index) is pd.RangeIndex else None
    )
    captured = []
    size = 0
    for column in columns:
        owned = _column(column)
        size += owned.nbytes
        if size > SCIENTIFIC_VALUE_MAX_BYTES:
            raise ValueError(
                "Scientific value exceeds the 256 MiB decoded-content limit"
            )
        captured.append(owned)
    return TableValue(
        "series" if is_series else "frame",
        tuple(captured),
        (_label(value.name),) if is_series else tuple(_label(n) for n in value.columns),
        None if range_index is not None else _column(index),
        range_index,
        _label(index.name),
        None if is_series else _label(value.columns.name),
    )


def _map_scientific(
    value: Any, *, native: bool, depth: int = 0, budget: list[int] | None = None
) -> Any:
    if depth > JSON_MAX_DEPTH:
        raise ValueError(f"runtime value exceeds maximum JSON depth {JSON_MAX_DEPTH}")
    if budget is None:
        budget = [0]
    size = (
        value.nbytes
        if type(value) in {ArrayValue, TableValue}
        else None
        if native
        else _native_scientific_size(value)
    )
    if size is not None:
        budget[0] += size
        if (
            size > SCIENTIFIC_VALUE_MAX_BYTES
            or budget[0] > SCIENTIFIC_OPERATION_MAX_BYTES
        ):
            raise ValueError(
                "Scientific values exceed the per-value or cumulative decoded-content limit"
            )
    if native:
        if type(value) is ArrayValue:
            return value.to_numpy(copy=True)
        if type(value) is TableValue:
            return value.to_pandas()
    else:
        captured = snapshot_scientific_value(value)
        if captured is not value or type(value) in {ArrayValue, TableValue}:
            return captured
    # Native conversion must not invoke custom container methods before the
    # existing consumer validates them. Transport already owns the plain shapes.
    if native and type(value) not in {DataTree, dict, list, tuple}:
        return value
    if isinstance(value, DataTree):
        branches = tuple(
            (
                path,
                tuple(
                    _map_scientific(n, native=native, depth=depth + 1, budget=budget)
                    for n in items
                ),
            )
            for path, items in value.branches
        )
        return (
            value
            if all(
                before is after
                for (_, original), (_, updated) in zip(value.branches, branches)
                for before, after in zip(original, updated)
            )
            else DataTree(branches)
        )
    if isinstance(value, Mapping):
        mapped = {
            key: _map_scientific(n, native=native, depth=depth + 1, budget=budget)
            for key, n in value.items()
        }
        return (
            value if all(mapped[key] is item for key, item in value.items()) else mapped
        )
    if isinstance(value, (list, tuple)):
        items = [
            _map_scientific(n, native=native, depth=depth + 1, budget=budget)
            for n in value
        ]
        if all(before is after for before, after in zip(value, items)):
            return value
        return tuple(items) if isinstance(value, tuple) else list(items)
    return value


def snapshot_scientific_values(value: Any) -> Any:
    return _map_scientific(value, native=False)


def materialize_script_values(value: Any) -> Any:
    return _map_scientific(value, native=True)
