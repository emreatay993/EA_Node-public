# Purpose: Encode immutable scientific values using bounded versioned data-only payloads.
# Map: subsystems/supporting_runtime_assets.md
# Tests: tests/test_scientific_values.py

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any

from ea_node_editor.common.payload_tools import JSON_MAX_DEPTH, validate_payload_fields
from ea_node_editor.runtime_contracts.data_tree import DataTree
from ea_node_editor.runtime_contracts import scientific_values as values
from ea_node_editor.runtime_contracts.scientific_values import (
    ArrayValue,
    ColumnValue,
    TableValue,
    array_layout,
    column_layout,
    table_layout,
)

SCIENTIFIC_MARKER = "scientific_value"
_MARKER = "__ea_runtime_value__"


def _fields(payload: Any, fields: str) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError("Scientific payload must be a mapping")
    validate_payload_fields(
        payload, label="Scientific payload", required=frozenset(fields.split())
    )


def _encoded_size(text: Any, expected: int | None = None) -> int:
    if (
        type(text) is not str
        or len(text) % 4
        or len(text) > 4 * ((values.SCIENTIFIC_VALUE_MAX_BYTES + 2) // 3)
    ):
        raise ValueError(
            "Scientific base64 buffer length is invalid or exceeds the decoded-content limit"
        )
    size = len(text) // 4 * 3 - (
        2 if text.endswith("==") else 1 if text.endswith("=") else 0
    )
    if expected is not None and size != expected:
        raise ValueError("Scientific buffer length does not match its declared layout")
    return size


def _array_size(payload: Any) -> int:
    _fields(payload, "dtype shape buffer")
    if type(payload["shape"]) is not list:
        raise ValueError("Scientific array shape must be a list")
    size = array_layout(payload["dtype"], tuple(payload["shape"]))
    _encoded_size(payload["buffer"], size)
    return size


def _column_size(payload: Any) -> int:
    _fields(payload, "dtype data mask offsets timezone")
    size = _array_size(payload["data"]) + _encoded_size(payload["mask"])
    if type(payload["offsets"]) is not list or any(
        type(n) is not int for n in payload["offsets"]
    ):
        raise ValueError("Scientific string offsets must be integers")
    if type(payload["dtype"]) is not str or type(payload["timezone"]) is not str:
        raise ValueError("Scientific column dtype/timezone must be text")
    data = payload["data"]
    column_layout(
        payload["dtype"],
        data["dtype"],
        tuple(data["shape"]),
        _encoded_size(data["buffer"]),
        _encoded_size(payload["mask"]),
        tuple(payload["offsets"]),
        payload["timezone"],
    )
    return (
        size
        + 8 * len(payload["offsets"])
        + len(payload["dtype"].encode())
        + len(payload["timezone"].encode())
    )


def scientific_payload_size(payload: Mapping[str, Any]) -> int:
    if payload.get("kind") == "array":
        _fields(payload, f"{_MARKER} version kind array")
        size = _array_size(payload["array"])
    else:
        _fields(
            payload,
            f"{_MARKER} version kind columns column_names index range_index index_name columns_name",
        )
        if (
            payload["kind"] not in {"series", "frame"}
            or type(payload["columns"]) is not list
            or type(payload["column_names"]) is not list
        ):
            raise ValueError("Scientific table kind and columns are invalid")
        if len(payload["columns"]) != len(payload["column_names"]):
            raise ValueError("Scientific table columns and labels differ in length")
        size = sum(_column_size(column) for column in payload["columns"])
        size += _column_size(payload["index"]) if payload["index"] is not None else 24
        for label in (
            *payload["column_names"],
            payload["index_name"],
            payload["columns_name"],
        ):
            values._label(label)
            size += len(str(label).encode("utf-8"))
        index_range = payload["range_index"]
        if index_range is not None and (
            type(index_range) is not list
            or len(index_range) != 3
            or any(type(n) is not int for n in index_range)
        ):
            raise ValueError("Scientific RangeIndex must be three integers")

        def rows(column):
            return (
                len(column["offsets"]) - 1
                if column["offsets"]
                else column["data"]["shape"][0]
            )

        table_layout(
            payload["kind"],
            tuple(rows(c) for c in payload["columns"]),
            tuple(payload["column_names"]),
            rows(payload["index"]) if payload["index"] is not None else None,
            tuple(index_range) if index_range is not None else None,
            payload["index_name"],
            payload["columns_name"],
        )
    if (
        payload[_MARKER] != SCIENTIFIC_MARKER
        or type(payload["version"]) is not int
        or payload["version"] != 1
    ):
        raise ValueError("Unsupported scientific value schema version")
    if size > values.SCIENTIFIC_VALUE_MAX_BYTES:
        raise ValueError("Scientific value exceeds the 256 MiB decoded-content limit")
    return size


def check_scientific_budget(value: Any) -> None:
    """Preflight the entire operation before decoding any scientific buffer."""
    total = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal total
        if depth > JSON_MAX_DEPTH:
            raise ValueError(
                f"runtime value exceeds maximum JSON depth {JSON_MAX_DEPTH}"
            )
        if type(item) in {ArrayValue, TableValue}:
            size = item.nbytes
        elif (
            isinstance(item, Mapping)
            and not isinstance(item, DataTree)
            and item.get(_MARKER) == SCIENTIFIC_MARKER
        ):
            size = scientific_payload_size(item)
        else:
            if isinstance(item, DataTree):
                children = (child for _, branch in item.branches for child in branch)
            elif isinstance(item, Mapping):
                children = item.values()
            elif isinstance(item, (list, tuple)):
                children = item
            else:
                return
            for child in children:
                visit(child, depth + 1)
            return
        if size > values.SCIENTIFIC_VALUE_MAX_BYTES:
            raise ValueError(
                "Scientific value exceeds the 256 MiB decoded-content limit"
            )
        total += size
        if total > values.SCIENTIFIC_OPERATION_MAX_BYTES:
            raise ValueError(
                "Scientific values exceed the 512 MiB cumulative decoded-content limit"
            )

    visit(value, 0)


def _array_payload(value: ArrayValue) -> dict[str, Any]:
    return {
        "dtype": value.dtype,
        "shape": list(value.shape),
        "buffer": base64.b64encode(value.buffer).decode("ascii"),
    }


def _column_payload(value: ColumnValue) -> dict[str, Any]:
    return {
        "dtype": value.dtype,
        "data": _array_payload(value.data),
        "mask": base64.b64encode(value.mask).decode("ascii"),
        "offsets": list(value.offsets),
        "timezone": value.timezone,
    }


def scientific_to_payload(value: ArrayValue | TableValue) -> dict[str, Any]:
    header = {_MARKER: SCIENTIFIC_MARKER, "version": 1}
    if type(value) is ArrayValue:
        return {**header, "kind": "array", "array": _array_payload(value)}
    return {
        **header,
        "kind": value.kind,
        "columns": [_column_payload(column) for column in value.columns],
        "column_names": list(value.column_names),
        "index": _column_payload(value.index) if value.index is not None else None,
        "range_index": list(value.range_index)
        if value.range_index is not None
        else None,
        "index_name": value.index_name,
        "columns_name": value.columns_name,
    }


def _decode(text: str) -> bytes:
    try:
        return base64.b64decode(text, validate=True)
    except ValueError as exc:
        raise ValueError("Scientific buffer is not valid base64") from exc


def _array_from_payload(payload: Mapping[str, Any]) -> ArrayValue:
    return ArrayValue(
        payload["dtype"], tuple(payload["shape"]), _decode(payload["buffer"])
    )


def _column_from_payload(payload: Mapping[str, Any]) -> ColumnValue:
    return ColumnValue(
        payload["dtype"],
        _array_from_payload(payload["data"]),
        _decode(payload["mask"]),
        tuple(payload["offsets"]),
        payload["timezone"],
    )


def scientific_from_payload(payload: Mapping[str, Any]) -> ArrayValue | TableValue:
    scientific_payload_size(payload)
    if payload["kind"] == "array":
        return _array_from_payload(payload["array"])
    return TableValue(
        payload["kind"],
        tuple(_column_from_payload(column) for column in payload["columns"]),
        tuple(payload["column_names"]),
        _column_from_payload(payload["index"])
        if payload["index"] is not None
        else None,
        tuple(payload["range_index"]) if payload["range_index"] is not None else None,
        payload["index_name"],
        payload["columns_name"],
    )
