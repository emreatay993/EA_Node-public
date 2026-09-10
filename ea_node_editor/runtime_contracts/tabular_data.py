from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ea_node_editor.common.payload_tools import (
    REF_METADATA_MAX_BYTES,
    copy_json_mapping,
    copy_json_safe,
    validate_payload_fields,
)
from ea_node_editor.runtime_contracts.data_types import (
    ARRAY_DATA_REF_TYPE_ID,
    ARRAY_SLICE_2D_REF_TYPE_ID,
    TABULAR_DATA_REF_TYPE_ID,
    TABULAR_WINDOW_REF_TYPE_ID,
)

RUNTIME_VALUE_MARKER_KEY = "__ea_runtime_value__"
TABULAR_DATA_REF_MARKER_VALUE = "tabular_data_ref"
ARRAY_DATA_REF_MARKER_VALUE = "array_data_ref"
TABULAR_WINDOW_REF_MARKER_VALUE = "tabular_window_ref"
ARRAY_SLICE_2D_REF_MARKER_VALUE = "array_slice_2d_ref"
RUNTIME_REF_SCHEMA_VERSION = 1


def _copy_json_safe(value: Any, *, field_name: str) -> Any:
    return copy_json_safe(value, field_name=field_name)


def _copy_json_mapping(value: Mapping[str, Any] | None, *, field_name: str) -> dict[str, Any]:
    is_metadata = field_name == "metadata"
    return copy_json_mapping(
        value,
        field_name=field_name,
        max_encoded_bytes=REF_METADATA_MAX_BYTES if is_metadata else None,
        reject_sensitive_metadata=is_metadata,
    )


def _validate_fixed_carrier(
    payload: Mapping[str, Any],
    *,
    expected_type_id: str,
) -> None:
    if "data_type_id" not in payload:
        raise ValueError("Runtime ref payload is missing data_type_id")
    if payload["data_type_id"] != expected_type_id:
        raise ValueError(
            f"Runtime ref data_type_id must be {expected_type_id!r}"
        )
    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != RUNTIME_REF_SCHEMA_VERSION
    ):
        raise ValueError(
            f"Runtime ref schema_version must be {RUNTIME_REF_SCHEMA_VERSION}"
        )


def _normalize_required_string(field_name: str, value: object) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_optional_string(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_optional_non_negative_int(field_name: str, value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be an integer") from exc
    if normalized < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return normalized


def _normalize_positive_int(field_name: str, value: object) -> int:
    normalized = _normalize_optional_non_negative_int(field_name, value)
    if normalized is None or normalized <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return normalized


def _normalize_optional_positive_int(field_name: str, value: object) -> int | None:
    normalized = _normalize_optional_non_negative_int(field_name, value)
    if normalized is not None and normalized <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return normalized


def _normalize_non_negative_int(field_name: str, value: object) -> int:
    normalized = _normalize_optional_non_negative_int(field_name, value)
    if normalized is None:
        raise ValueError(f"{field_name} must be an integer")
    return normalized


def _normalize_column_names(value: Sequence[object] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = tuple(value.replace(";", ",").split(","))
    normalized: list[str] = []
    for item in value:
        name = str(item).strip()
        if not name:
            raise ValueError("column names must be non-empty strings")
        normalized.append(name)
    return tuple(normalized)


def _normalize_shape(value: Sequence[object] | None) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise TypeError("shape must be a sequence of integers")
    shape: list[int] = []
    for index, dimension in enumerate(value):
        normalized = _normalize_optional_non_negative_int(f"shape[{index}]", dimension)
        if normalized is None:
            raise ValueError(f"shape[{index}] must be an integer")
        shape.append(normalized)
    return tuple(shape)


@dataclass(slots=True, frozen=True)
class TabularDataRef:
    ref_id: str
    resolver_id: str
    backend_id: str = ""
    source_uri: str = ""
    object_id: str = ""
    row_count: int | None = None
    column_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_id", _normalize_required_string("ref_id", self.ref_id))
        object.__setattr__(self, "resolver_id", _normalize_required_string("resolver_id", self.resolver_id))
        object.__setattr__(self, "backend_id", _normalize_optional_string(self.backend_id))
        object.__setattr__(self, "source_uri", _normalize_optional_string(self.source_uri))
        object.__setattr__(self, "object_id", _normalize_optional_string(self.object_id))
        object.__setattr__(
            self,
            "row_count",
            _normalize_optional_non_negative_int("row_count", self.row_count),
        )
        object.__setattr__(
            self,
            "column_count",
            _normalize_optional_non_negative_int("column_count", self.column_count),
        )
        object.__setattr__(
            self,
            "metadata",
            _copy_json_mapping(self.metadata, field_name="metadata"),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> TabularDataRef | None:
        if str(payload.get(RUNTIME_VALUE_MARKER_KEY, "")).strip() != TABULAR_DATA_REF_MARKER_VALUE:
            return None
        validate_payload_fields(
            payload,
            label="Runtime ref payload",
            required=frozenset(
                {
                    RUNTIME_VALUE_MARKER_KEY,
                    "data_type_id",
                    "schema_version",
                    "ref_id",
                    "resolver_id",
                }
            ),
            optional=frozenset(
                {
                    "backend_id",
                    "source_uri",
                    "object_id",
                    "row_count",
                    "column_count",
                    "metadata",
                }
            ),
        )
        _validate_fixed_carrier(payload, expected_type_id=TABULAR_DATA_REF_TYPE_ID)
        return cls(
            ref_id=payload.get("ref_id", ""),
            resolver_id=payload.get("resolver_id", ""),
            backend_id=payload.get("backend_id", ""),
            source_uri=payload.get("source_uri", ""),
            object_id=payload.get("object_id", ""),
            row_count=payload.get("row_count"),
            column_count=payload.get("column_count"),
            metadata=payload.get("metadata"),
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            RUNTIME_VALUE_MARKER_KEY: TABULAR_DATA_REF_MARKER_VALUE,
            "data_type_id": TABULAR_DATA_REF_TYPE_ID,
            "schema_version": RUNTIME_REF_SCHEMA_VERSION,
            "ref_id": self.ref_id,
            "resolver_id": self.resolver_id,
        }
        if self.backend_id:
            payload["backend_id"] = self.backend_id
        if self.source_uri:
            payload["source_uri"] = self.source_uri
        if self.object_id:
            payload["object_id"] = self.object_id
        if self.row_count is not None:
            payload["row_count"] = self.row_count
        if self.column_count is not None:
            payload["column_count"] = self.column_count
        if self.metadata:
            payload["metadata"] = _copy_json_mapping(self.metadata, field_name="metadata")
        return payload


@dataclass(slots=True, frozen=True)
class ArrayDataRef:
    ref_id: str
    resolver_id: str
    backend_id: str = ""
    source_uri: str = ""
    object_id: str = ""
    shape: tuple[int, ...] = ()
    dtype: str = ""
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_id", _normalize_required_string("ref_id", self.ref_id))
        object.__setattr__(self, "resolver_id", _normalize_required_string("resolver_id", self.resolver_id))
        object.__setattr__(self, "backend_id", _normalize_optional_string(self.backend_id))
        object.__setattr__(self, "source_uri", _normalize_optional_string(self.source_uri))
        object.__setattr__(self, "object_id", _normalize_optional_string(self.object_id))
        object.__setattr__(self, "shape", _normalize_shape(self.shape))
        object.__setattr__(self, "dtype", _normalize_optional_string(self.dtype))
        object.__setattr__(
            self,
            "metadata",
            _copy_json_mapping(self.metadata, field_name="metadata"),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ArrayDataRef | None:
        if str(payload.get(RUNTIME_VALUE_MARKER_KEY, "")).strip() != ARRAY_DATA_REF_MARKER_VALUE:
            return None
        validate_payload_fields(
            payload,
            label="Runtime ref payload",
            required=frozenset(
                {
                    RUNTIME_VALUE_MARKER_KEY,
                    "data_type_id",
                    "schema_version",
                    "ref_id",
                    "resolver_id",
                }
            ),
            optional=frozenset(
                {
                    "backend_id",
                    "source_uri",
                    "object_id",
                    "shape",
                    "dtype",
                    "metadata",
                }
            ),
        )
        _validate_fixed_carrier(payload, expected_type_id=ARRAY_DATA_REF_TYPE_ID)
        return cls(
            ref_id=payload.get("ref_id", ""),
            resolver_id=payload.get("resolver_id", ""),
            backend_id=payload.get("backend_id", ""),
            source_uri=payload.get("source_uri", ""),
            object_id=payload.get("object_id", ""),
            shape=payload.get("shape") if isinstance(payload.get("shape"), Sequence) else None,
            dtype=payload.get("dtype", ""),
            metadata=payload.get("metadata"),
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            RUNTIME_VALUE_MARKER_KEY: ARRAY_DATA_REF_MARKER_VALUE,
            "data_type_id": ARRAY_DATA_REF_TYPE_ID,
            "schema_version": RUNTIME_REF_SCHEMA_VERSION,
            "ref_id": self.ref_id,
            "resolver_id": self.resolver_id,
        }
        if self.backend_id:
            payload["backend_id"] = self.backend_id
        if self.source_uri:
            payload["source_uri"] = self.source_uri
        if self.object_id:
            payload["object_id"] = self.object_id
        if self.shape:
            payload["shape"] = list(self.shape)
        if self.dtype:
            payload["dtype"] = self.dtype
        if self.metadata:
            payload["metadata"] = _copy_json_mapping(self.metadata, field_name="metadata")
        return payload


def coerce_tabular_data_ref(value: object) -> TabularDataRef | None:
    if isinstance(value, TabularDataRef):
        return value
    if isinstance(value, Mapping):
        return TabularDataRef.from_payload(value)
    return None


def coerce_array_data_ref(value: object) -> ArrayDataRef | None:
    if isinstance(value, ArrayDataRef):
        return value
    if isinstance(value, Mapping):
        return ArrayDataRef.from_payload(value)
    return None


@dataclass(slots=True, frozen=True)
class TabularWindowRef:
    ref_id: str
    table_data: TabularDataRef
    row_offset: int = 0
    row_limit: int = 1000
    column_offset: int = 0
    column_limit: int = 0
    columns: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        table_data = coerce_tabular_data_ref(self.table_data)
        if table_data is None:
            raise TypeError("table_data must be a TabularDataRef")
        object.__setattr__(self, "ref_id", _normalize_required_string("ref_id", self.ref_id))
        object.__setattr__(self, "table_data", table_data)
        object.__setattr__(self, "row_offset", _normalize_non_negative_int("row_offset", self.row_offset))
        object.__setattr__(self, "row_limit", _normalize_non_negative_int("row_limit", self.row_limit))
        object.__setattr__(
            self,
            "column_offset",
            _normalize_non_negative_int("column_offset", self.column_offset),
        )
        object.__setattr__(
            self,
            "column_limit",
            _normalize_non_negative_int("column_limit", self.column_limit),
        )
        object.__setattr__(self, "columns", _normalize_column_names(self.columns))
        object.__setattr__(
            self,
            "metadata",
            _copy_json_mapping(self.metadata, field_name="metadata"),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> TabularWindowRef | None:
        if str(payload.get(RUNTIME_VALUE_MARKER_KEY, "")).strip() != TABULAR_WINDOW_REF_MARKER_VALUE:
            return None
        validate_payload_fields(
            payload,
            label="Runtime ref payload",
            required=frozenset(
                {
                    RUNTIME_VALUE_MARKER_KEY,
                    "data_type_id",
                    "schema_version",
                    "ref_id",
                    "table_data",
                }
            ),
            optional=frozenset(
                {
                    "row_offset",
                    "row_limit",
                    "column_offset",
                    "column_limit",
                    "columns",
                    "metadata",
                }
            ),
        )
        _validate_fixed_carrier(payload, expected_type_id=TABULAR_WINDOW_REF_TYPE_ID)
        table_data = coerce_tabular_data_ref(payload.get("table_data"))
        if table_data is None:
            raise ValueError("Tabular window ref payload is missing table_data")
        return cls(
            ref_id=payload.get("ref_id", ""),
            table_data=table_data,
            row_offset=payload.get("row_offset", 0),
            row_limit=payload.get("row_limit", 1000),
            column_offset=payload.get("column_offset", 0),
            column_limit=payload.get("column_limit", 0),
            columns=payload.get("columns") if isinstance(payload.get("columns"), Sequence) else None,
            metadata=payload.get("metadata"),
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            RUNTIME_VALUE_MARKER_KEY: TABULAR_WINDOW_REF_MARKER_VALUE,
            "data_type_id": TABULAR_WINDOW_REF_TYPE_ID,
            "schema_version": RUNTIME_REF_SCHEMA_VERSION,
            "ref_id": self.ref_id,
            "table_data": self.table_data.to_payload(),
            "row_offset": self.row_offset,
            "row_limit": self.row_limit,
            "column_offset": self.column_offset,
            "column_limit": self.column_limit,
        }
        if self.columns:
            payload["columns"] = list(self.columns)
        if self.metadata:
            payload["metadata"] = _copy_json_mapping(self.metadata, field_name="metadata")
        return payload


@dataclass(slots=True, frozen=True)
class ArraySlice2DRef:
    ref_id: str
    array_data: ArrayDataRef
    row_offset: int = 0
    row_limit: int = 1000
    column_offset: int = 0
    column_limit: int = 100
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        array_data = coerce_array_data_ref(self.array_data)
        if array_data is None:
            raise TypeError("array_data must be an ArrayDataRef")
        object.__setattr__(self, "ref_id", _normalize_required_string("ref_id", self.ref_id))
        object.__setattr__(self, "array_data", array_data)
        object.__setattr__(self, "row_offset", _normalize_non_negative_int("row_offset", self.row_offset))
        object.__setattr__(self, "row_limit", _normalize_non_negative_int("row_limit", self.row_limit))
        object.__setattr__(
            self,
            "column_offset",
            _normalize_non_negative_int("column_offset", self.column_offset),
        )
        object.__setattr__(
            self,
            "column_limit",
            _normalize_non_negative_int("column_limit", self.column_limit),
        )
        object.__setattr__(
            self,
            "metadata",
            _copy_json_mapping(self.metadata, field_name="metadata"),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ArraySlice2DRef | None:
        if str(payload.get(RUNTIME_VALUE_MARKER_KEY, "")).strip() != ARRAY_SLICE_2D_REF_MARKER_VALUE:
            return None
        validate_payload_fields(
            payload,
            label="Runtime ref payload",
            required=frozenset(
                {
                    RUNTIME_VALUE_MARKER_KEY,
                    "data_type_id",
                    "schema_version",
                    "ref_id",
                    "array_data",
                }
            ),
            optional=frozenset(
                {
                    "row_offset",
                    "row_limit",
                    "column_offset",
                    "column_limit",
                    "metadata",
                }
            ),
        )
        _validate_fixed_carrier(payload, expected_type_id=ARRAY_SLICE_2D_REF_TYPE_ID)
        array_data = coerce_array_data_ref(payload.get("array_data"))
        if array_data is None:
            raise ValueError("Array slice 2D ref payload is missing array_data")
        return cls(
            ref_id=payload.get("ref_id", ""),
            array_data=array_data,
            row_offset=payload.get("row_offset", 0),
            row_limit=payload.get("row_limit", 1000),
            column_offset=payload.get("column_offset", 0),
            column_limit=payload.get("column_limit", 100),
            metadata=payload.get("metadata"),
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            RUNTIME_VALUE_MARKER_KEY: ARRAY_SLICE_2D_REF_MARKER_VALUE,
            "data_type_id": ARRAY_SLICE_2D_REF_TYPE_ID,
            "schema_version": RUNTIME_REF_SCHEMA_VERSION,
            "ref_id": self.ref_id,
            "array_data": self.array_data.to_payload(),
            "row_offset": self.row_offset,
            "row_limit": self.row_limit,
            "column_offset": self.column_offset,
            "column_limit": self.column_limit,
        }
        if self.metadata:
            payload["metadata"] = _copy_json_mapping(self.metadata, field_name="metadata")
        return payload


def coerce_tabular_window_ref(value: object) -> TabularWindowRef | None:
    if isinstance(value, TabularWindowRef):
        return value
    if isinstance(value, Mapping):
        return TabularWindowRef.from_payload(value)
    return None


def coerce_array_slice_2d_ref(value: object) -> ArraySlice2DRef | None:
    if isinstance(value, ArraySlice2DRef):
        return value
    if isinstance(value, Mapping):
        return ArraySlice2DRef.from_payload(value)
    return None


@dataclass(slots=True, frozen=True)
class TabularColumn:
    name: str
    dtype: str = ""
    nullable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_required_string("name", self.name))
        object.__setattr__(self, "dtype", _normalize_optional_string(self.dtype))
        object.__setattr__(self, "nullable", bool(self.nullable))
        object.__setattr__(
            self,
            "metadata",
            _copy_json_mapping(self.metadata, field_name="metadata"),
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "nullable": self.nullable}
        if self.dtype:
            payload["dtype"] = self.dtype
        if self.metadata:
            payload["metadata"] = _copy_json_mapping(self.metadata, field_name="metadata")
        return payload


@dataclass(slots=True, frozen=True)
class TabularSchema:
    columns: tuple[TabularColumn, ...]
    row_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        columns = tuple(
            column if isinstance(column, TabularColumn) else TabularColumn(**column)
            for column in self.columns
        )
        object.__setattr__(self, "columns", columns)
        object.__setattr__(
            self,
            "row_count",
            _normalize_optional_non_negative_int("row_count", self.row_count),
        )
        object.__setattr__(
            self,
            "metadata",
            _copy_json_mapping(self.metadata, field_name="metadata"),
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"columns": [column.to_payload() for column in self.columns]}
        if self.row_count is not None:
            payload["row_count"] = self.row_count
        if self.metadata:
            payload["metadata"] = _copy_json_mapping(self.metadata, field_name="metadata")
        return payload


@dataclass(slots=True, frozen=True)
class TabularWindowRequest:
    row_limit: int
    column_limit: int
    row_offset: int = 0
    column_offset: int = 0
    columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_limit", _normalize_non_negative_int("row_limit", self.row_limit))
        object.__setattr__(self, "column_limit", _normalize_non_negative_int("column_limit", self.column_limit))
        object.__setattr__(self, "row_offset", _normalize_non_negative_int("row_offset", self.row_offset))
        object.__setattr__(
            self,
            "column_offset",
            _normalize_non_negative_int("column_offset", self.column_offset),
        )
        object.__setattr__(self, "columns", _normalize_column_names(self.columns))


@dataclass(slots=True, frozen=True)
class TabularArrowBatchOptions:
    row_limit: int
    batch_size: int
    row_offset: int = 0
    columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_limit", _normalize_positive_int("row_limit", self.row_limit))
        object.__setattr__(self, "batch_size", _normalize_positive_int("batch_size", self.batch_size))
        object.__setattr__(self, "row_offset", _normalize_non_negative_int("row_offset", self.row_offset))
        object.__setattr__(self, "columns", _normalize_column_names(self.columns))


@dataclass(slots=True, frozen=True)
class TabularMaterializationOptions:
    row_limit: int | None = None
    column_limit: int | None = None
    columns: tuple[str, ...] = ()
    allow_full_materialization: bool = False
    memory_limit_bytes: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "row_limit",
            _normalize_optional_positive_int("row_limit", self.row_limit),
        )
        object.__setattr__(
            self,
            "column_limit",
            _normalize_optional_positive_int("column_limit", self.column_limit),
        )
        object.__setattr__(self, "columns", _normalize_column_names(self.columns))
        object.__setattr__(self, "allow_full_materialization", bool(self.allow_full_materialization))
        object.__setattr__(
            self,
            "memory_limit_bytes",
            _normalize_optional_positive_int("memory_limit_bytes", self.memory_limit_bytes),
        )
        if (
            not self.allow_full_materialization
            and self.row_limit is None
            and self.column_limit is None
            and not self.columns
        ):
            raise ValueError(
                "Tabular materialization requires bounded row/column limits "
                "or allow_full_materialization=True."
            )


@dataclass(slots=True, frozen=True)
class TabularDataWindow:
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    row_offset: int
    column_offset: int = 0
    total_rows: int | None = None
    total_columns: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "columns", _normalize_column_names(self.columns))
        object.__setattr__(
            self,
            "rows",
            tuple(_copy_json_mapping(row, field_name="rows") for row in self.rows),
        )
        object.__setattr__(self, "row_offset", _normalize_non_negative_int("row_offset", self.row_offset))
        object.__setattr__(
            self,
            "column_offset",
            _normalize_non_negative_int("column_offset", self.column_offset),
        )
        object.__setattr__(
            self,
            "total_rows",
            _normalize_optional_non_negative_int("total_rows", self.total_rows),
        )
        object.__setattr__(
            self,
            "total_columns",
            _normalize_optional_non_negative_int("total_columns", self.total_columns),
        )
        object.__setattr__(
            self,
            "metadata",
            _copy_json_mapping(self.metadata, field_name="metadata"),
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "columns": list(self.columns),
            "rows": [dict(row) for row in self.rows],
            "row_offset": self.row_offset,
            "column_offset": self.column_offset,
        }
        if self.total_rows is not None:
            payload["total_rows"] = self.total_rows
        if self.total_columns is not None:
            payload["total_columns"] = self.total_columns
        if self.metadata:
            payload["metadata"] = _copy_json_mapping(self.metadata, field_name="metadata")
        return payload


@dataclass(slots=True, frozen=True)
class ArraySlice2DRequest:
    row_limit: int
    column_limit: int
    row_offset: int = 0
    column_offset: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_limit", _normalize_non_negative_int("row_limit", self.row_limit))
        object.__setattr__(self, "column_limit", _normalize_non_negative_int("column_limit", self.column_limit))
        object.__setattr__(self, "row_offset", _normalize_non_negative_int("row_offset", self.row_offset))
        object.__setattr__(
            self,
            "column_offset",
            _normalize_non_negative_int("column_offset", self.column_offset),
        )


@dataclass(slots=True, frozen=True)
class ArrayMaterializationOptions:
    max_elements: int | None = None
    slices: tuple[tuple[int, int], ...] = ()
    allow_full_materialization: bool = False
    memory_limit_bytes: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_elements",
            _normalize_optional_positive_int("max_elements", self.max_elements),
        )
        normalized_slices: list[tuple[int, int]] = []
        for index, slice_pair in enumerate(self.slices):
            if len(slice_pair) != 2:
                raise ValueError("array materialization slices must be (offset, limit) pairs")
            offset = _normalize_non_negative_int(f"slices[{index}][0]", slice_pair[0])
            limit = _normalize_positive_int(f"slices[{index}][1]", slice_pair[1])
            normalized_slices.append((offset, limit))
        object.__setattr__(self, "slices", tuple(normalized_slices))
        object.__setattr__(self, "allow_full_materialization", bool(self.allow_full_materialization))
        object.__setattr__(
            self,
            "memory_limit_bytes",
            _normalize_optional_positive_int("memory_limit_bytes", self.memory_limit_bytes),
        )
        if not self.allow_full_materialization and self.max_elements is None and not self.slices:
            raise ValueError(
                "Array materialization requires max_elements, bounded slices, "
                "or allow_full_materialization=True."
            )


@dataclass(slots=True, frozen=True)
class ArraySlice2D:
    values: tuple[tuple[Any, ...], ...]
    row_offset: int
    column_offset: int
    shape: tuple[int, ...] = ()
    dtype: str = ""
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "values",
            tuple(
                tuple(_copy_json_safe(value, field_name="values") for value in row)
                for row in self.values
            ),
        )
        object.__setattr__(self, "row_offset", _normalize_non_negative_int("row_offset", self.row_offset))
        object.__setattr__(
            self,
            "column_offset",
            _normalize_non_negative_int("column_offset", self.column_offset),
        )
        object.__setattr__(self, "shape", _normalize_shape(self.shape))
        object.__setattr__(self, "dtype", _normalize_optional_string(self.dtype))
        object.__setattr__(
            self,
            "metadata",
            _copy_json_mapping(self.metadata, field_name="metadata"),
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "values": [list(row) for row in self.values],
            "row_offset": self.row_offset,
            "column_offset": self.column_offset,
        }
        if self.shape:
            payload["shape"] = list(self.shape)
        if self.dtype:
            payload["dtype"] = self.dtype
        if self.metadata:
            payload["metadata"] = _copy_json_mapping(self.metadata, field_name="metadata")
        return payload


@runtime_checkable
class TabularDataResolver(Protocol):
    def schema(self, ref: TabularDataRef) -> TabularSchema: ...

    def metadata(self, ref: TabularDataRef) -> Mapping[str, Any]: ...

    def window(self, ref: TabularDataRef, request: TabularWindowRequest) -> TabularDataWindow: ...

    def rows(self, ref: TabularDataRef, request: TabularWindowRequest) -> Sequence[Mapping[str, Any]]: ...

    def arrow_batches(self, ref: TabularDataRef, options: TabularArrowBatchOptions) -> Iterable[Any]: ...

    def to_pandas(self, ref: TabularDataRef, options: TabularMaterializationOptions) -> Any: ...

    def to_polars(self, ref: TabularDataRef, options: TabularMaterializationOptions) -> Any: ...

    def to_numpy(self, ref: TabularDataRef, options: TabularMaterializationOptions) -> Any: ...


@runtime_checkable
class ArrayDataResolver(Protocol):
    def metadata(self, ref: ArrayDataRef) -> Mapping[str, Any]: ...

    def slice_2d(self, ref: ArrayDataRef, request: ArraySlice2DRequest) -> ArraySlice2D: ...

    def to_numpy(self, ref: ArrayDataRef, options: ArrayMaterializationOptions) -> Any: ...


__all__ = [
    "ARRAY_DATA_REF_MARKER_VALUE",
    "ARRAY_SLICE_2D_REF_MARKER_VALUE",
    "RUNTIME_VALUE_MARKER_KEY",
    "TABULAR_DATA_REF_MARKER_VALUE",
    "TABULAR_WINDOW_REF_MARKER_VALUE",
    "ArrayDataRef",
    "ArrayDataResolver",
    "ArrayMaterializationOptions",
    "ArraySlice2D",
    "ArraySlice2DRef",
    "ArraySlice2DRequest",
    "TabularArrowBatchOptions",
    "TabularColumn",
    "TabularDataRef",
    "TabularDataResolver",
    "TabularDataWindow",
    "TabularMaterializationOptions",
    "TabularSchema",
    "TabularWindowRef",
    "TabularWindowRequest",
    "coerce_array_data_ref",
    "coerce_array_slice_2d_ref",
    "coerce_tabular_data_ref",
    "coerce_tabular_window_ref",
]
