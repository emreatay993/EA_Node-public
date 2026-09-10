# Purpose: Normalize node property values and built-in property policy from explicit spec/catalog context.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_property_normalization.py, tests/test_registry_validation.py

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from ea_node_editor.runtime_contracts import DataTypeCatalog
import ea_node_editor.nodes.instance_resolution as instance_resolution
import ea_node_editor.nodes.property_coercion as property_coercion
import ea_node_editor.nodes.spec_validation as spec_validation

from .node_specs import NodeTypeSpec, PropertySpec


def normalize_property_value(
    spec: NodeTypeSpec,
    key: str,
    value: Any,
    *,
    properties: Mapping[str, object] | None,
    data_types: DataTypeCatalog,
) -> Any:
    resolved_spec = _resolve_spec(spec, properties, data_types=data_types)
    prop = _property_spec(resolved_spec, key)
    return _normalize_special_property_value(
        resolved_spec.type_id,
        key,
        property_coercion.coerce_property_value(
            prop,
            value,
            strict=False,
            data_types=data_types,
        ),
    )


def normalize_properties(
    spec: NodeTypeSpec,
    values: Mapping[str, Any] | None,
    *,
    include_defaults: bool,
    data_types: DataTypeCatalog,
) -> dict[str, Any]:
    type_id = spec.type_id
    provided = dict(values or {})
    resolution_properties = {
        prop.key: copy.deepcopy(prop.default) for prop in spec.properties
    }
    resolution_properties.update(provided)
    resolved_spec = _resolve_spec(
        spec,
        resolution_properties,
        data_types=data_types,
    )
    normalized: dict[str, Any] = {}
    for prop in resolved_spec.properties:
        if prop.key in provided:
            normalized[prop.key] = _normalize_special_property_value(
                type_id,
                prop.key,
                property_coercion.coerce_property_value(
                    prop,
                    provided[prop.key],
                    strict=False,
                    data_types=data_types,
                ),
            )
            continue
        if include_defaults:
            normalized[prop.key] = _normalize_special_property_value(
                type_id,
                prop.key,
                property_coercion.coerce_property_value(
                    prop,
                    prop.default,
                    strict=False,
                    data_types=data_types,
                ),
            )
    normalized = _normalize_special_properties(type_id, normalized)
    resolved_groups = instance_resolution.resolve_dynamic_port_groups(
        resolved_spec,
        normalized,
        data_types=data_types,
    )
    for group, ports in zip(
        resolved_spec.dynamic_port_groups,
        resolved_groups,
        strict=True,
    ):
        if group.property_editor is None and (include_defaults or group.property_key in provided):
            normalized[group.property_key] = [port.key for port in ports]
    return normalized


def _resolve_spec(
    spec: NodeTypeSpec,
    properties: Mapping[str, object] | None,
    *,
    data_types: DataTypeCatalog,
) -> NodeTypeSpec:
    if properties is None:
        return spec
    resolved = instance_resolution.resolve_instance_spec(spec, properties)
    if resolved is not spec:
        spec_validation.validate_node_spec(resolved, data_types=data_types)
    return resolved


def _property_spec(spec: NodeTypeSpec, key: str) -> PropertySpec:
    for prop in spec.properties:
        if prop.key == key:
            return prop
    raise KeyError(f"Unknown property {key} for node type {spec.type_id}")


def _normalize_special_property_value(type_id: str, key: str, value: Any) -> Any:
    if type_id == "model.viewer" and key == "scene_styles":
        from ea_node_editor.common.scene_protocol import normalize_scene_styles

        return normalize_scene_styles(value)
    if type_id == "data.number_slider":
        from ea_node_editor.nodes.builtins.data_control import (
            normalize_number_slider_property_value,
        )

        return normalize_number_slider_property_value(key, value)
    if type_id != "web.page_viewer" or key != "browser_state":
        return value
    from ea_node_editor.nodes.builtins.web_viewer import (
        normalize_web_page_viewer_browser_state,
    )

    return normalize_web_page_viewer_browser_state(
        value if isinstance(value, Mapping) else {}
    )


def _normalize_special_properties(
    type_id: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    if type_id == "model.viewer":
        scene_ids = set(values.get("scene_input_ids", ["scene_1"]))
        if "scene_styles" in values:
            values["scene_styles"] = {
                key: style for key, style in values["scene_styles"].items() if key in scene_ids
            }
        return values
    if type_id == "data.select":
        from ea_node_editor.nodes.builtins.data_control import (
            normalize_select_properties,
        )

        return normalize_select_properties(values)
    if type_id == "data.number_slider":
        from ea_node_editor.nodes.builtins.data_control import (
            normalize_number_slider_properties,
        )

        return normalize_number_slider_properties(values)
    if type_id != "web.page_viewer":
        return values
    from ea_node_editor.nodes.builtins.web_viewer import (
        normalize_web_page_viewer_properties,
    )

    return normalize_web_page_viewer_properties(values)


__all__ = ["normalize_properties", "normalize_property_value"]
