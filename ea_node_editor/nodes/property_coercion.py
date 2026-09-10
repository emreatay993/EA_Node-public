# Purpose: Coerce one node property value without registry or subsystem state.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_property_coercion.py, tests/test_spec_validation.py

from __future__ import annotations

import copy
import json
from typing import Any

from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    INTERVAL_1D_DATA_TYPE,
    ImageValue,
    RuntimeArtifactRef,
    TypedInlineValue,
    coerce_interval_1d,
    deserialize_runtime_value,
)

from .node_specs import PropertySpec


def coerce_property_value(
    prop: PropertySpec,
    value: Any,
    *,
    strict: bool,
    data_types: DataTypeCatalog | None = None,
) -> Any:
    default = copy.deepcopy(prop.default)
    if value is None:
        if prop.nullable:
            return None
        if strict:
            raise ValueError(f"Property {prop.key} default cannot be None")
        return coerce_property_value(
            prop,
            default,
            strict=True,
            data_types=data_types,
        )

    try:
        if prop.persistence_data_type_id and isinstance(
            value,
            (TypedInlineValue, ImageValue, RuntimeArtifactRef),
        ):
            if data_types is None:
                raise ValueError(
                    "persistence-aware property requires a data-type catalog"
                )
            data_types.validate_carrier(prop.persistence_data_type_id, value)
            actual_spec = data_types.require(value.data_type_id)
            expected_persistence = (
                "inline"
                if isinstance(value, (TypedInlineValue, ImageValue))
                else "saved_artifact"
            )
            if actual_spec.persistence != expected_persistence:
                raise ValueError(
                    f"data type {value.data_type_id!r} does not permit "
                    f"{expected_persistence} persistence"
                )
            if isinstance(value, RuntimeArtifactRef):
                if value.scope == "managed":
                    return value.ref
                return value
            return copy.deepcopy(value)
        if prop.type in {"str", "path"}:
            return str(value)
        if prop.type == "int":
            if isinstance(value, bool):
                raise ValueError("bool is not a valid int default")
            return int(value)
        if prop.type == "float":
            if isinstance(value, bool):
                raise ValueError("bool is not a valid float default")
            return float(value)
        if prop.type == "bool":
            if not isinstance(value, bool):
                raise ValueError("bool property requires bool value")
            return value
        if prop.type == "enum":
            normalized = str(value)
            if normalized not in set(prop.enum_values):
                raise ValueError(
                    f"enum property value must be one of {tuple(prop.enum_values)}"
                )
            return normalized
        if prop.type == INTERVAL_1D_DATA_TYPE:
            try:
                return coerce_interval_1d(value)
            except TypeError:
                return coerce_interval_1d(deserialize_runtime_value(value))
        json.dumps(value)
        return copy.deepcopy(value)
    except Exception as exc:  # noqa: BLE001
        if strict:
            raise ValueError(
                f"Invalid default for property {prop.key} ({prop.type}): {value!r}"
            ) from exc
        return coerce_property_value(
            prop,
            default,
            strict=True,
            data_types=data_types,
        )


__all__ = ["coerce_property_value"]
