# Purpose: Declare strict COREX DateTime, Tensor, Cell, Interval2D, and Animation contracts.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_core_media_types.py

from __future__ import annotations

from datetime import datetime
import math
import re

from ea_node_editor.nodes.core_data_types import GRAPH_DATA_TYPE_ID
from ea_node_editor.nodes.plugin_contracts import PluginContractManifest
from ea_node_editor.runtime_contracts import DataTypeSpec, RuntimeArtifactRef

COREX_CORE_MEDIA_OWNER_ID = "corex.core_media"
COREX_CORE_MEDIA_OWNER_VERSION = "1"

DATETIME_DATA_TYPE_ID = "COREX.DataTypes.DateTime"
TENSOR_DATA_TYPE_ID = "COREX.DataTypes.Tensor"
CELL_DATA_TYPE_ID = "COREX.DataTypes.Cell"
INTERVAL_2D_DATA_TYPE_ID = "COREX.DataTypes.Interval2D"
ANIMATION_DATA_TYPE_ID = "COREX.DataTypes.Animation"

_INT32_MAX = 2_147_483_647
_SYSTEM_SINGLE_MAX = 3.4028234663852886e38
_DATETIME_KEYS = frozenset(
    {
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "second",
        "millisecond",
        "kind",
    }
)
_DATETIME_KINDS = frozenset({"Unspecified", "Utc", "Local"})
_TENSOR_KEYS = frozenset({"data", "dimensions"})
_CELL_KEYS = frozenset({"Column", "Row"})
_INTERVAL_2D_KEYS = frozenset({"u", "v"})
_INTERVAL_KEYS = frozenset({"start", "end"})
_CELL_COLUMN_PATTERN = re.compile(r"[A-Z]+", re.ASCII)


def _has_exact_keys(value: object, keys: frozenset[str]) -> bool:
    return (
        type(value) is dict
        and len(value) == len(keys)
        and all(type(key) is str and key in keys for key in value)
    )


def _is_finite_float(value: object) -> bool:
    return type(value) is float and math.isfinite(value)


def is_datetime_payload(value: object) -> bool:
    if not _has_exact_keys(value, _DATETIME_KEYS):
        return False
    assert type(value) is dict
    integer_fields = (
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "second",
        "millisecond",
    )
    if (
        any(type(value[field]) is not int for field in integer_fields)
        or type(value["kind"]) is not str
        or value["kind"] not in _DATETIME_KINDS
        or not 0 <= value["millisecond"] <= 999
    ):
        return False
    try:
        datetime(
            value["year"],
            value["month"],
            value["day"],
            value["hour"],
            value["minute"],
            value["second"],
            value["millisecond"] * 1000,
        )
    except (OverflowError, TypeError, ValueError):
        return False
    return True


def is_tensor_payload(value: object) -> bool:
    if not _has_exact_keys(value, _TENSOR_KEYS):
        return False
    assert type(value) is dict
    data = value["data"]
    dimensions = value["dimensions"]
    if (
        type(data) is not list
        or type(dimensions) is not list
        or not dimensions
        or any(
            type(item) is not float
            or not math.isfinite(item)
            or abs(item) > _SYSTEM_SINGLE_MAX
            for item in data
        )
    ):
        return False

    item_count = 1
    for dimension in dimensions:
        if (
            type(dimension) is not int
            or not 1 <= dimension <= _INT32_MAX
            or item_count > _INT32_MAX // dimension
        ):
            return False
        item_count *= dimension
    return item_count == len(data)


def is_cell_payload(value: object) -> bool:
    if not _has_exact_keys(value, _CELL_KEYS):
        return False
    assert type(value) is dict
    column = value["Column"]
    row = value["Row"]
    return (
        type(column) is str
        and _CELL_COLUMN_PATTERN.fullmatch(column) is not None
        and type(row) is int
        and 1 <= row <= _INT32_MAX
    )


def _is_interval_payload(value: object) -> bool:
    return (
        _has_exact_keys(value, _INTERVAL_KEYS)
        and _is_finite_float(value["start"])
        and _is_finite_float(value["end"])
    )


def is_interval_2d_payload(value: object) -> bool:
    return (
        _has_exact_keys(value, _INTERVAL_2D_KEYS)
        and _is_interval_payload(value["u"])
        and _is_interval_payload(value["v"])
    )


def is_animation_artifact(value: object) -> bool:
    return (
        type(value) is RuntimeArtifactRef
        and value.data_type_id == ANIMATION_DATA_TYPE_ID
        and value.schema_version == 1
        and value.format == "gif"
    )


_GRAPH_PARENT = (GRAPH_DATA_TYPE_ID,)

COREX_CORE_MEDIA_DATA_TYPES = (
    DataTypeSpec(
        DATETIME_DATA_TYPE_ID,
        "Date Time",
        "scalar",
        is_datetime_payload,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"inline"}),
        persistence="inline",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        TENSOR_DATA_TYPE_ID,
        "Tensor",
        "container",
        is_tensor_payload,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"inline"}),
        persistence="inline",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        CELL_DATA_TYPE_ID,
        "Cell",
        "corex_data",
        is_cell_payload,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"inline"}),
        persistence="never",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        INTERVAL_2D_DATA_TYPE_ID,
        "Interval 2D",
        "interval",
        is_interval_2d_payload,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"inline"}),
        persistence="inline",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        ANIMATION_DATA_TYPE_ID,
        "Animation",
        "viewer",
        is_animation_artifact,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"artifact"}),
        persistence="saved_artifact",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_CORE_MEDIA_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_CORE_MEDIA_DATA_TYPES,
)

__all__ = [
    "ANIMATION_DATA_TYPE_ID",
    "CELL_DATA_TYPE_ID",
    "DATETIME_DATA_TYPE_ID",
    "INTERVAL_2D_DATA_TYPE_ID",
    "COREX_CORE_MEDIA_CONTRACT_MANIFEST",
    "COREX_CORE_MEDIA_DATA_TYPES",
    "COREX_CORE_MEDIA_OWNER_ID",
    "COREX_CORE_MEDIA_OWNER_VERSION",
    "TENSOR_DATA_TYPE_ID",
    "is_animation_artifact",
    "is_cell_payload",
    "is_datetime_payload",
    "is_interval_2d_payload",
    "is_tensor_payload",
]
