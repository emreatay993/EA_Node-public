# Purpose: Validate saved graph property values against immutable node property specs.
# Map: subsystems/graph_domain.md
# Tests: tests/test_registry_compatibility.py

from __future__ import annotations

import math
from numbers import Real

from ea_node_editor.common.payload_tools import copy_json_safe
from ea_node_editor.nodes.node_specs import PropertySpec
from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    ImageValue,
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    Interval1D,
    RuntimeArtifactRef,
    TypedInlineValue,
)

_SEMANTIC_PERSISTENCE_VALUES = (TypedInlineValue, ImageValue, RuntimeArtifactRef)


def is_saved_property_value_valid(
    prop: PropertySpec,
    value: object,
    *,
    data_types: DataTypeCatalog | None = None,
) -> bool:
    """Return whether a saved value remains valid under ``prop``."""
    if isinstance(value, _SEMANTIC_PERSISTENCE_VALUES):
        return _is_persistence_value_valid(prop, value, data_types)
    if value is None:
        return bool(prop.nullable)
    if prop.type in {"str", "path"}:
        valid = isinstance(value, str)
    elif prop.type == "bool":
        valid = isinstance(value, bool)
    elif prop.type == "int":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif prop.type == "float":
        valid = isinstance(value, Real) and not isinstance(value, bool)
    elif prop.type == "enum":
        valid = isinstance(value, str) and value in prop.enum_values
    elif prop.type == "interval_1d":
        if not isinstance(value, Interval1D):
            return False
        values = (value.start, value.end)
        valid = True
        if prop.interval_direction == "increasing" and value.start > value.end:
            valid = False
        if prop.interval_direction == "decreasing" and value.start < value.end:
            valid = False
    elif prop.inline_editor == "list":
        if not isinstance(value, list):
            return False
        if prop.list_item_type == "enum":
            valid = all(item in prop.list_item_enum_codes for item in value)
            return valid and _is_persistence_value_valid(prop, value, data_types)
        expected = {
            "str": str,
            "color": str,
            "int": int,
            "float": Real,
        }.get(prop.list_item_type)
        if expected is None or any(
            isinstance(item, bool) or not isinstance(item, expected)
            for item in value
        ):
            return False
        if prop.list_item_type in {"str", "color"}:
            return _is_persistence_value_valid(prop, value, data_types)
        values = tuple(value)
        valid = True
    elif prop.type == "json":
        try:
            copy_json_safe(value, field_name=f"property {prop.key!r}")
        except (TypeError, ValueError):
            return False
        valid = True
    else:
        return False
    if not valid:
        return False
    if prop.enum_codes and value not in prop.enum_codes:
        return False
    if prop.type not in {"int", "float", "interval_1d"} and not (
        prop.inline_editor == "list"
        and prop.list_item_type in {"int", "float"}
    ):
        return _is_persistence_value_valid(prop, value, data_types)
    numeric_values = values if "values" in locals() else (value,)
    try:
        valid = all(
            math.isfinite(float(item))
            and (prop.minimum is None or float(item) >= float(prop.minimum))
            and (prop.maximum is None or float(item) <= float(prop.maximum))
            and (
                prop.list_item_minimum is None
                or float(item) >= float(prop.list_item_minimum)
            )
            and (
                prop.list_item_maximum is None
                or float(item) <= float(prop.list_item_maximum)
            )
            for item in numeric_values
        )
    except (TypeError, ValueError, OverflowError):
        return False
    return valid and _is_persistence_value_valid(prop, value, data_types)


def _is_persistence_value_valid(
    prop: PropertySpec,
    value: object,
    data_types: DataTypeCatalog | None,
) -> bool:
    if not isinstance(value, (*_SEMANTIC_PERSISTENCE_VALUES, Interval1D)):
        try:
            copy_json_safe(value, field_name=f"property {prop.key!r}")
        except (TypeError, ValueError):
            return False
    if data_types is None:
        return True
    declared_type_id = prop.persistence_data_type_id
    if not declared_type_id:
        return not isinstance(value, (*_SEMANTIC_PERSISTENCE_VALUES, Interval1D))
    try:
        declared_spec = data_types.require(declared_type_id)
        if declared_spec.persistence == "saved_artifact":
            if isinstance(value, str) and value == "":
                return True
            if isinstance(value, RuntimeArtifactRef):
                if data_types.require(value.data_type_id).persistence != "saved_artifact":
                    return False
                data_types.validate_carrier(declared_type_id, value)
                return True
            if not isinstance(value, str):
                return False
            placeholder = RuntimeArtifactRef.from_artifact_ref(
                value,
                data_type_id=declared_type_id,
                schema_version=declared_spec.payload_schema_version,
                format="bin",
                size_bytes=0,
                sha256="0" * 64,
                provenance="registry-compatibility",
            )
            data_types.validate_carrier(declared_type_id, placeholder)
            return True
        if declared_spec.persistence != "inline" or isinstance(
            value,
            RuntimeArtifactRef,
        ):
            return False
        if isinstance(value, (TypedInlineValue, ImageValue, Interval1D)):
            actual_type_id = (
                value.data_type_id
                if not isinstance(value, Interval1D)
                else INTERVAL_1D_GRAPH_DATA_TYPE_ID
            )
            if data_types.require(actual_type_id).persistence != "inline":
                return False
        data_types.validate_carrier(declared_type_id, value)
        return True
    except Exception:  # noqa: BLE001 - catalog/plugin validators are compatibility input
        return False


__all__ = ["is_saved_property_value_valid"]
