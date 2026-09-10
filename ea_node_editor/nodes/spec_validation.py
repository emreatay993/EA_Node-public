# Purpose: Validate node specifications against an explicit semantic data-type catalog.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_spec_validation.py, tests/test_registry_validation.py, tests/mechanical_catalogue/test_controls.py
# Landmarks: _SpecValidator; validate_node_spec

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from numbers import Real

from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    DataTypeCatalogError,
    INTERVAL_1D_DATA_TYPE,
    TypedInlineValue,
    deserialize_runtime_value,
)

from . import property_coercion
from .instance_resolution import (
    resolve_instance_ports,
    resolve_instance_spec,
    validate_port,
)
from .node_specs import (
    DynamicPortGroupSpec,
    NodeTypeSpec,
    PortSpec,
    PropertyConditionSpec,
    PropertySpec,
    ReadinessRequirementSpec,
    SettingsGroupItemSpec,
    SettingsGroupSpec,
    property_inspector_editor,
)


class _SpecValidator:
    __slots__ = ("_data_types",)

    _TYPE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
    _SETTINGS_GROUP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")
    _SUPPORTED_PROPERTY_TYPES = {
        "str",
        "int",
        "float",
        "bool",
        "path",
        "enum",
        "json",
        INTERVAL_1D_DATA_TYPE,
    }
    _SUPPORTED_INLINE_EDITORS = {
        "",
        "text",
        "number",
        "toggle",
        "enum",
        "path",
        "textarea",
        "color",
        "slider",
        "interval_slider",
        "interval_fields",
        "list",
        "secret",
    }
    _SUPPORTED_INSPECTOR_EDITORS = {
        "",
        "text",
        "textarea",
        "path",
        "toggle",
        "enum",
        "color",
        "font_family",
        "secret",
    }
    _SUPPORTED_RUNTIME_BEHAVIORS = {"active", "passive", "compile_only"}
    _SUPPORTED_SOLUTION_REUSE_SCOPES = {"never", "session", "durable"}
    _SUPPORTED_SURFACE_FAMILIES = {
        "standard",
        "flowchart",
        "planning",
        "annotation",
        "group_backdrop",
        "media",
        "viewer",
        "web",
        "jupyter",
    }

    def __init__(self, data_types: DataTypeCatalog) -> None:
        self._data_types = data_types

    def validate(self, spec: NodeTypeSpec) -> None:
        if not isinstance(spec, NodeTypeSpec):
            raise TypeError("Plugin spec() must return NodeTypeSpec")

        if not spec.type_id or spec.type_id.strip() != spec.type_id:
            raise ValueError("Node type_id must be a non-empty trimmed string")
        if not self._TYPE_ID_PATTERN.fullmatch(spec.type_id):
            raise ValueError(f"Node type_id has unsupported characters: {spec.type_id}")
        if not spec.display_name.strip():
            raise ValueError(f"Node {spec.type_id} display_name must be non-empty")
        if not spec.category_path:
            raise ValueError(f"Node {spec.type_id} category_path must be non-empty")
        if spec.runtime_behavior not in self._SUPPORTED_RUNTIME_BEHAVIORS:
            raise ValueError(
                f"Node {spec.type_id} runtime_behavior has invalid value: {spec.runtime_behavior}"
            )
        if (
            not isinstance(spec.solution_reuse_scope, str)
            or spec.solution_reuse_scope not in self._SUPPORTED_SOLUTION_REUSE_SCOPES
        ):
            raise ValueError(
                f"Node {spec.type_id} solution_reuse_scope has invalid value: "
                f"{spec.solution_reuse_scope}"
            )
        if spec.runtime_behavior != "active" and spec.solution_reuse_scope != "never":
            raise ValueError(
                f"Node {spec.type_id} non-active nodes must use "
                "solution_reuse_scope='never'"
            )
        if (
            not isinstance(spec.surface_family, str)
            or not spec.surface_family
            or spec.surface_family.strip() != spec.surface_family
        ):
            raise ValueError(
                f"Node {spec.type_id} surface_family must be a non-empty trimmed string"
            )
        if spec.surface_family not in self._SUPPORTED_SURFACE_FAMILIES:
            raise ValueError(
                f"Node {spec.type_id} surface_family has invalid value: {spec.surface_family}"
            )
        if (
            not isinstance(spec.surface_variant, str)
            or spec.surface_variant.strip() != spec.surface_variant
        ):
            raise ValueError(
                f"Node {spec.type_id} surface_variant must be a trimmed string"
            )
        if not isinstance(spec.ports, tuple):
            raise TypeError(f"Node {spec.type_id} ports must be a tuple[PortSpec, ...]")
        if not isinstance(spec.properties, tuple):
            raise TypeError(
                f"Node {spec.type_id} properties must be a tuple[PropertySpec, ...]"
            )
        if not isinstance(spec.dynamic_port_groups, tuple):
            raise TypeError(
                f"Node {spec.type_id} dynamic_port_groups must be a tuple[DynamicPortGroupSpec, ...]"
            )
        if not isinstance(spec.settings_groups, tuple):
            raise TypeError(
                f"Node {spec.type_id} settings_groups must be a tuple[SettingsGroupSpec, ...]"
            )
        if not isinstance(spec.readiness_requirements, tuple):
            raise TypeError(
                f"Node {spec.type_id} readiness_requirements must be a tuple[ReadinessRequirementSpec, ...]"
            )
        if spec.instance_spec_resolver is not None and not callable(
            spec.instance_spec_resolver
        ):
            raise TypeError(
                f"Node {spec.type_id} instance_spec_resolver must be callable or None"
            )

        port_keys: set[str] = set()
        for port in spec.ports:
            validate_port(spec, port, data_types=self._data_types)
            if port.key in port_keys:
                raise ValueError(
                    f"Node {spec.type_id} has duplicate port key: {port.key}"
                )
            port_keys.add(port.key)

        property_keys: set[str] = set()
        properties_by_key: dict[str, PropertySpec] = {}
        for prop in spec.properties:
            self._validate_property(spec.type_id, prop)
            if prop.key in property_keys:
                raise ValueError(
                    f"Node {spec.type_id} has duplicate property key: {prop.key}"
                )
            property_keys.add(prop.key)
            properties_by_key[prop.key] = prop
        self._validate_sensitive_properties(spec, properties_by_key)
        for provenance_input in spec.solution_provenance_inputs:
            property_spec = properties_by_key.get(provenance_input.property_key)
            if property_spec is None:
                raise ValueError(
                    f"Node {spec.type_id} solution provenance references unknown "
                    f"property {provenance_input.property_key!r}"
                )
            if property_spec.type != "path":
                raise ValueError(
                    f"Node {spec.type_id} solution provenance property "
                    f"{provenance_input.property_key!r} must use path type"
                )
        if spec.solution_reuse_scope != "never" and any(
            property_spec.sensitive for property_spec in spec.properties
        ):
            raise ValueError(
                f"Node {spec.type_id} sensitive properties require "
                "solution_reuse_scope='never'"
            )
        resolved_ports = self._validate_dynamic_port_groups(spec, properties_by_key)
        self._validate_property_conditions(spec, properties_by_key)
        self._validate_property_default_ports(spec, properties_by_key)
        self._validate_readiness_requirements(spec, properties_by_key)
        self._validate_settings_groups(spec)
        if spec.instance_spec_resolver is not None:
            self.validate(resolve_instance_spec(spec, {}))

    @staticmethod
    def _validate_sensitive_properties(
        spec: NodeTypeSpec,
        properties_by_key: Mapping[str, PropertySpec],
    ) -> None:
        for prop in spec.properties:
            secret_editor = (
                str(prop.inline_editor) == "secret"
                or str(prop.inspector_editor) == "secret"
            )
            if not isinstance(prop.sensitive, bool):
                raise TypeError(
                    f"Node {spec.type_id} property {prop.key} sensitive must be bool"
                )
            if secret_editor and not prop.sensitive:
                raise ValueError(
                    f"Node {spec.type_id} property {prop.key} secret editor requires sensitive=True"
                )
            if not prop.sensitive:
                if prop.sensitive_scope_key:
                    raise ValueError(
                        f"Node {spec.type_id} property {prop.key} sensitive_scope_key requires sensitive=True"
                    )
                continue
            if prop.type != "json":
                raise ValueError(
                    f"Node {spec.type_id} sensitive property {prop.key} requires a json property"
                )
            if not secret_editor:
                raise ValueError(
                    f"Node {spec.type_id} sensitive property {prop.key} requires a secret editor"
                )
            if not prop.sensitive_scope_key:
                continue
            scope_property = properties_by_key.get(prop.sensitive_scope_key)
            if scope_property is None or scope_property.type != "enum":
                raise ValueError(
                    f"Node {spec.type_id} sensitive property {prop.key} scope key "
                    f"{prop.sensitive_scope_key} must reference an enum property"
                )

    def _validate_dynamic_port_groups(
        self,
        spec: NodeTypeSpec,
        properties_by_key: Mapping[str, PropertySpec],
    ) -> tuple[PortSpec, ...]:
        group_ids: set[str] = set()
        property_keys: dict[str, bool] = {}
        directions: set[str] = set()
        for group in spec.dynamic_port_groups:
            if not isinstance(group, DynamicPortGroupSpec):
                raise TypeError(
                    f"Node {spec.type_id} dynamic_port_groups must contain DynamicPortGroupSpec instances"
                )
            if (
                not isinstance(group.group_id, str)
                or not group.group_id
                or group.group_id.strip() != group.group_id
            ):
                raise ValueError(
                    f"Node {spec.type_id} has invalid dynamic port group id: {group.group_id!r}"
                )
            if group.group_id in group_ids:
                raise ValueError(
                    f"Node {spec.type_id} has duplicate dynamic port group id: {group.group_id}"
                )
            group_ids.add(group.group_id)
            if (
                not isinstance(group.property_key, str)
                or not group.property_key
                or group.property_key.strip() != group.property_key
            ):
                raise ValueError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} has invalid property key: "
                    f"{group.property_key!r}"
                )
            source_backed = group.property_editor is not None
            if source_backed and not callable(group.property_editor):
                raise TypeError("Dynamic port property_editor must be callable")
            if group.property_key in property_keys and not (
                source_backed and property_keys[group.property_key]
            ):
                raise ValueError(
                    f"Node {spec.type_id} dynamic port groups duplicate property key: {group.property_key}"
                )
            property_keys[group.property_key] = source_backed
            backing_property = properties_by_key.get(group.property_key)
            if (
                backing_property is None
                or backing_property.type != ("str" if source_backed else "json")
                or (not source_backed and backing_property.inspector_visible)
            ):
                raise ValueError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} requires "
                    f"{'string' if source_backed else 'hidden JSON'} property "
                    f"{group.property_key}"
                )
            if group.direction not in {"in", "out"}:
                raise ValueError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} has invalid direction: "
                    f"{group.direction}"
                )
            if group.direction in directions:
                raise ValueError(
                    f"Node {spec.type_id} has more than one dynamic port group for direction {group.direction}"
                )
            directions.add(group.direction)
            if (
                not isinstance(group.minimum, int)
                or isinstance(group.minimum, bool)
                or group.minimum < 0
            ):
                raise ValueError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} minimum must be a non-negative int"
                )
            if group.maximum is not None and (
                not isinstance(group.maximum, int)
                or isinstance(group.maximum, bool)
                or group.maximum < group.minimum
            ):
                raise ValueError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} maximum must be None or >= minimum"
                )
            if not callable(group.ports_resolver):
                raise TypeError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} ports_resolver must be callable"
                )
            if not callable(group.key_factory):
                raise TypeError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} key_factory must be callable"
                )
            if group.rename_mode not in {"none", "label", "key"}:
                raise ValueError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} has invalid rename_mode: "
                    f"{group.rename_mode}"
                )
            if group.rename_mode == "key":
                if not callable(group.key_renamer):
                    raise TypeError(
                        f"Node {spec.type_id} dynamic port group {group.group_id} key rename requires key_renamer"
                    )
            elif group.key_renamer is not None:
                raise ValueError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} key_renamer requires key rename mode"
                )

        resolved_ports = resolve_instance_ports(
            spec,
            {},
            data_types=self._data_types,
        )
        for port in resolved_ports[len(spec.ports) :]:
            validate_port(spec, port, data_types=self._data_types)
        return resolved_ports

    def _validate_readiness_requirements(
        self,
        spec: NodeTypeSpec,
        properties_by_key: Mapping[str, PropertySpec],
    ) -> None:
        if spec.readiness_requirements and spec.runtime_behavior != "active":
            raise ValueError(
                f"Node {spec.type_id} readiness_requirements are only supported on active nodes"
            )

        ports_by_key = {port.key: port for port in spec.ports}
        validated: list[ReadinessRequirementSpec] = []
        for index, requirement in enumerate(spec.readiness_requirements):
            field_name = f"Node {spec.type_id} readiness requirement {index}"
            if not isinstance(requirement, ReadinessRequirementSpec):
                raise TypeError(
                    f"Node {spec.type_id} readiness_requirements must contain ReadinessRequirementSpec instances"
                )
            self._validate_readiness_keys(
                field_name, "any_of_ports", requirement.any_of_ports
            )
            self._validate_readiness_keys(
                field_name,
                "any_of_properties",
                requirement.any_of_properties,
            )
            self._validate_readiness_keys(
                field_name,
                "when_ports_present",
                requirement.when_ports_present,
            )
            if not requirement.any_of_ports and not requirement.any_of_properties:
                raise ValueError(f"{field_name} must declare at least one target")
            if not isinstance(requirement.when_properties, tuple):
                raise TypeError(f"{field_name} when_properties must be a tuple")
            if set(requirement.any_of_ports) & set(requirement.when_ports_present):
                raise ValueError(
                    f"{field_name} cannot require and condition on the same port"
                )

            for key in requirement.any_of_ports + requirement.when_ports_present:
                port = ports_by_key.get(key)
                if port is None:
                    raise ValueError(f"{field_name} references unknown port: {key}")
                if port.direction != "in" or port.kind != "data":
                    raise ValueError(
                        f"{field_name} port {key} must be an active data input"
                    )
                if key in requirement.any_of_ports and port.required is True:
                    raise ValueError(
                        f"{field_name} port {key} duplicates its unconditional required input rule"
                    )
            for key in requirement.any_of_properties:
                if key not in properties_by_key:
                    raise ValueError(f"{field_name} references unknown property: {key}")
            if set(requirement.any_of_ports) & set(requirement.any_of_properties):
                raise ValueError(f"{field_name} target keys must be unambiguous")

            condition_keys: set[str] = set()
            for condition in requirement.when_properties:
                if not isinstance(condition, PropertyConditionSpec):
                    raise TypeError(
                        f"{field_name} when_properties must contain PropertyConditionSpec instances"
                    )
                key = condition.property_key
                if not isinstance(key, str) or not key or key.strip() != key:
                    raise ValueError(
                        f"{field_name} has an invalid condition property key: {key!r}"
                    )
                if key in condition_keys:
                    raise ValueError(
                        f"{field_name} has contradictory conditions for property: {key}"
                    )
                condition_keys.add(key)
                prop = properties_by_key.get(key)
                if prop is None:
                    raise ValueError(
                        f"{field_name} condition references unknown property: {key}"
                    )
                if not isinstance(condition.values, tuple):
                    raise TypeError(
                        f"{field_name} condition {key} values must be a tuple"
                    )
                seen_values: list[object] = []
                for value in condition.values:
                    self._validate_readiness_condition_value(field_name, prop, value)
                    if any(value == existing for existing in seen_values):
                        raise ValueError(
                            f"{field_name} condition {key} values must be unique"
                        )
                    seen_values.append(value)
            if set(requirement.any_of_properties) & condition_keys:
                raise ValueError(
                    f"{field_name} cannot require and condition on the same property"
                )
            if any(requirement == previous for previous in validated):
                raise ValueError(
                    f"Node {spec.type_id} has duplicate readiness requirements"
                )
            validated.append(requirement)

    def _validate_property_conditions(
        self,
        spec: NodeTypeSpec,
        properties_by_key: Mapping[str, PropertySpec],
    ) -> None:
        scalar_types = {"str", "path", "enum", "bool", "int", "float"}
        for prop in spec.properties:
            condition = prop.enabled_when
            if condition is None:
                continue
            field_name = f"Node {spec.type_id} property {prop.key} enabled_when"
            if not isinstance(condition, PropertyConditionSpec):
                raise TypeError(f"{field_name} must be a PropertyConditionSpec")
            key = condition.property_key
            if not isinstance(key, str) or not key or key.strip() != key:
                raise ValueError(f"{field_name} has an invalid property key: {key!r}")
            if key == prop.key:
                raise ValueError(f"{field_name} cannot reference itself")
            source = properties_by_key.get(key)
            if source is None:
                raise ValueError(f"{field_name} references unknown property: {key}")
            if source.type not in scalar_types:
                raise ValueError(f"{field_name} source {key} must be a scalar property")
            if not isinstance(condition.values, tuple):
                raise TypeError(f"{field_name} values must be a tuple")
            if not condition.values:
                raise ValueError(f"{field_name} values must not be empty")
            for value in condition.values:
                self._validate_enabled_condition_value(field_name, source, value)

    @staticmethod
    def _validate_enabled_condition_value(
        field_name: str,
        source: PropertySpec,
        value: object,
    ) -> None:
        if source.type in {"str", "path", "enum"}:
            valid = isinstance(value, str)
        elif source.type == "bool":
            valid = isinstance(value, bool)
        elif source.type == "int":
            valid = isinstance(value, int) and not isinstance(value, bool)
        else:
            valid = isinstance(value, float)
        if not valid:
            raise ValueError(
                f"{field_name} value is invalid for {source.type}: {value!r}"
            )
        if source.type == "enum" and value not in source.enum_values:
            raise ValueError(
                f"{field_name} value must be one of {source.enum_values}: {value!r}"
            )

    @staticmethod
    def _validate_readiness_keys(field_name: str, name: str, keys: object) -> None:
        if not isinstance(keys, tuple):
            raise TypeError(f"{field_name} {name} must be a tuple")
        seen: set[str] = set()
        for key in keys:
            if not isinstance(key, str) or not key or key.strip() != key:
                raise ValueError(
                    f"{field_name} {name} contains an invalid key: {key!r}"
                )
            if key in seen:
                raise ValueError(f"{field_name} {name} must not contain duplicates")
            seen.add(key)

    @staticmethod
    def _validate_readiness_condition_value(
        field_name: str,
        prop: PropertySpec,
        value: object,
    ) -> None:
        valid = False
        if prop.type in {"str", "path", "enum"}:
            valid = isinstance(value, str)
        elif prop.type == "bool":
            valid = isinstance(value, bool)
        elif prop.type == "int":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif prop.type == "float":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        else:
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                valid = False
            else:
                valid = True
        if not valid:
            raise ValueError(
                f"{field_name} condition {prop.key} value is invalid for {prop.type}: {value!r}"
            )
        if prop.type == "enum" and value not in prop.enum_values:
            raise ValueError(
                f"{field_name} condition {prop.key} value must be one of {prop.enum_values}: {value!r}"
            )

    def _validate_property_default_ports(
        self,
        spec: NodeTypeSpec,
        properties_by_key: Mapping[str, PropertySpec],
    ) -> None:
        for port in spec.ports:
            if not port.uses_property_default:
                continue
            if (
                spec.runtime_behavior != "active"
                or port.direction != "in"
                or port.kind != "data"
            ):
                raise ValueError(
                    f"Node {spec.type_id} port {port.key} property defaults require an active data input"
                )
            prop = properties_by_key.get(port.key)
            if prop is None:
                raise ValueError(
                    f"Node {spec.type_id} port {port.key} property default requires a same-key property"
                )
            self._validate_property_default_value(spec.type_id, port, prop)

    def _validate_property_default_value(
        self,
        type_id: str,
        port: PortSpec,
        prop: PropertySpec,
    ) -> None:
        from ea_node_editor.runtime_contracts import DataTree

        normalized_default = property_coercion.coerce_property_value(
            prop,
            prop.default,
            strict=True,
            data_types=self._data_types,
        )
        if (
            prop.type == INTERVAL_1D_DATA_TYPE
            or type(normalized_default) is TypedInlineValue
        ):
            value = normalized_default
        else:
            value = deserialize_runtime_value(normalized_default)
        if isinstance(value, DataTree):
            if port.data_access != "tree":
                raise ValueError(
                    f"Node {type_id} port {port.key} serialized DataTree default requires tree access"
                )
            tree = value
        elif port.data_access == "list":
            if isinstance(value, (str, bytes, bytearray)) or not isinstance(
                value, Sequence
            ):
                raise ValueError(
                    f"Node {type_id} port {port.key} list property default must be a non-string sequence"
                )
            tree = DataTree.from_list(value)
        else:
            tree = DataTree.from_item(value)

        accepted_types = (port.data_type, *port.accepted_data_types)
        incompatible = [
            item
            for _path, items in tree.branches
            for item in items
            if not any(
                self._property_default_item_matches_type(item, data_type)
                for data_type in accepted_types
            )
        ]
        if incompatible:
            raise ValueError(
                f"Node {type_id} port {port.key} property default is incompatible with {port.data_type}"
            )

    def _property_default_item_matches_type(
        self,
        value: object,
        data_type: str,
    ) -> bool:
        try:
            if type(value) is TypedInlineValue:
                self._data_types.validate_carrier(data_type, value)
            else:
                self._data_types.prepare_untyped_input(data_type, value)
        except DataTypeCatalogError:
            return False
        return True

    def _validate_settings_groups(self, spec: NodeTypeSpec) -> None:
        if not spec.settings_groups:
            if spec.default_expanded_settings_group_ids:
                raise ValueError(
                    f"Node {spec.type_id} default expanded settings groups require settings_groups"
                )
            return
        if spec.runtime_behavior != "active":
            raise ValueError(
                f"Node {spec.type_id} settings_groups are only supported on active nodes"
            )

        ports_by_key = {port.key: port for port in spec.ports}
        properties_by_key = {prop.key: prop for prop in spec.properties}
        group_ids: set[str] = set()
        grouped_port_keys: set[str] = set()
        grouped_property_keys: set[str] = set()
        for group in spec.settings_groups:
            if not isinstance(group, SettingsGroupSpec):
                raise TypeError(
                    f"Node {spec.type_id} settings_groups must contain SettingsGroupSpec instances"
                )
            if not isinstance(
                group.group_id, str
            ) or not self._SETTINGS_GROUP_ID_PATTERN.fullmatch(group.group_id):
                raise ValueError(
                    f"Node {spec.type_id} has invalid settings group id: {group.group_id!r}"
                )
            if group.group_id in group_ids:
                raise ValueError(
                    f"Node {spec.type_id} has duplicate settings group id: {group.group_id}"
                )
            group_ids.add(group.group_id)
            if (
                not isinstance(group.label, str)
                or not group.label
                or group.label.strip() != group.label
            ):
                raise ValueError(
                    f"Node {spec.type_id} settings group {group.group_id} label must be non-empty and trimmed"
                )
            if not isinstance(group.items, tuple) or not group.items:
                raise ValueError(
                    f"Node {spec.type_id} settings group {group.group_id} items must be a non-empty tuple"
                )

            for item in group.items:
                if not isinstance(item, SettingsGroupItemSpec):
                    raise TypeError(
                        f"Node {spec.type_id} settings group {group.group_id} items must be SettingsGroupItemSpec instances"
                    )
                if not isinstance(item.port_key, str) or not isinstance(
                    item.property_key, str
                ):
                    raise TypeError(
                        f"Node {spec.type_id} settings group {group.group_id} item keys must be strings"
                    )
                port_key = item.port_key
                property_key = item.property_key
                if port_key.strip() != port_key or property_key.strip() != property_key:
                    raise ValueError(
                        f"Node {spec.type_id} settings group {group.group_id} item keys must be trimmed"
                    )
                if not port_key and not property_key:
                    raise ValueError(
                        f"Node {spec.type_id} settings group {group.group_id} items require a port_key or property_key"
                    )
                if port_key:
                    port = ports_by_key.get(port_key)
                    if port is None:
                        raise ValueError(
                            f"Node {spec.type_id} settings group {group.group_id} references unknown port: {port_key}"
                        )
                    if port.direction != "in":
                        raise ValueError(
                            f"Node {spec.type_id} settings group {group.group_id} port {port_key} must be an input"
                        )
                    if port_key in grouped_port_keys:
                        raise ValueError(
                            f"Node {spec.type_id} settings groups duplicate port membership: {port_key}"
                        )
                    grouped_port_keys.add(port_key)
                if property_key:
                    prop = properties_by_key.get(property_key)
                    if prop is None:
                        raise ValueError(
                            f"Node {spec.type_id} settings group {group.group_id} references unknown property: {property_key}"
                        )
                    if not str(prop.inline_editor).strip():
                        raise ValueError(
                            f"Node {spec.type_id} settings group {group.group_id} property {property_key} requires an inline editor"
                        )
                    if property_key in grouped_property_keys:
                        raise ValueError(
                            f"Node {spec.type_id} settings groups duplicate property membership: {property_key}"
                        )
                    grouped_property_keys.add(property_key)
                if port_key and property_key:
                    if port_key != property_key:
                        raise ValueError(
                            f"Node {spec.type_id} settings group {group.group_id} pairs unrelated port/property keys: "
                            f"{port_key}/{property_key}"
                        )

        declared_defaults = tuple(
            group.group_id
            for group in spec.settings_groups
            if group.group_id in spec.default_expanded_settings_group_ids
        )
        if declared_defaults != spec.default_expanded_settings_group_ids:
            raise ValueError(
                f"Node {spec.type_id} default expanded settings groups must be unique declared IDs in declaration order"
            )

    def _validate_property(self, type_id: str, prop: PropertySpec) -> None:
        if not isinstance(prop, PropertySpec):
            raise TypeError(f"Node {type_id} properties must be PropertySpec instances")
        if not prop.key or prop.key.strip() != prop.key:
            raise ValueError(f"Node {type_id} has invalid property key: {prop.key!r}")
        if prop.type not in self._SUPPORTED_PROPERTY_TYPES:
            raise ValueError(
                f"Node {type_id} property {prop.key} has invalid type: {prop.type}"
            )
        if not isinstance(prop.label, str):
            raise TypeError(
                f"Node {type_id} property {prop.key} label must be a string"
            )
        if prop.label.strip() != prop.label:
            raise ValueError(
                f"Node {type_id} property {prop.key} label must be trimmed"
            )
        if not isinstance(prop.expose_port_toggle, bool):
            raise TypeError(
                f"Node {type_id} property {prop.key} expose_port_toggle must be bool"
            )
        inline_editor = str(prop.inline_editor).strip()
        if inline_editor != prop.inline_editor:
            raise ValueError(
                f"Node {type_id} property {prop.key} inline_editor must be trimmed"
            )
        if inline_editor not in self._SUPPORTED_INLINE_EDITORS:
            raise ValueError(
                f"Node {type_id} property {prop.key} inline_editor has invalid value: {inline_editor}"
            )
        if not isinstance(prop.searchable, bool):
            raise TypeError(
                f"Node {type_id} property {prop.key} searchable must be bool"
            )
        if prop.searchable and (prop.type != "enum" or inline_editor != "enum"):
            raise ValueError(
                f"Node {type_id} property {prop.key} searchable requires an enum property using the enum inline editor"
            )
        interval_direction = str(prop.interval_direction).strip()
        if interval_direction != prop.interval_direction:
            raise ValueError(
                f"Node {type_id} property {prop.key} interval_direction must be trimmed"
            )
        if interval_direction not in {"", "increasing", "decreasing"}:
            raise ValueError(
                f"Node {type_id} property {prop.key} interval_direction has invalid value: {interval_direction}"
            )
        if prop.type != INTERVAL_1D_DATA_TYPE and interval_direction:
            raise ValueError(
                f"Node {type_id} property {prop.key} interval_direction requires an interval_1d property"
            )
        if prop.type == INTERVAL_1D_DATA_TYPE and inline_editor not in {
            "",
            "interval_fields",
            "interval_slider",
        }:
            raise ValueError(
                f"Node {type_id} property {prop.key} interval_1d properties require the interval_slider inline editor"
            )
        if inline_editor == "slider":
            if prop.type not in {"int", "float"}:
                raise ValueError(
                    f"Node {type_id} property {prop.key} slider inline_editor requires an int or float property"
                )
            if prop.minimum is None or prop.maximum is None:
                raise ValueError(
                    f"Node {type_id} property {prop.key} slider inline_editor requires minimum and maximum"
                )
            if not float(prop.minimum) < float(prop.maximum):
                raise ValueError(
                    f"Node {type_id} property {prop.key} slider inline_editor requires minimum < maximum"
                )
            if float(prop.step) < 0.0:
                raise ValueError(
                    f"Node {type_id} property {prop.key} slider inline_editor step must be >= 0"
                )
        if inline_editor == "interval_slider":
            if prop.type != INTERVAL_1D_DATA_TYPE:
                raise ValueError(
                    f"Node {type_id} property {prop.key} interval_slider inline_editor requires an interval_1d property"
                )
            if not interval_direction:
                raise ValueError(
                    f"Node {type_id} property {prop.key} interval_slider inline_editor requires an interval direction"
                )
            numeric_metadata = {
                "minimum": prop.minimum,
                "maximum": prop.maximum,
                "step": prop.step,
            }
            for name, value in numeric_metadata.items():
                if isinstance(value, bool) or not isinstance(value, Real):
                    raise ValueError(
                        f"Node {type_id} property {prop.key} interval_slider {name} must be a finite number"
                    )
                if not math.isfinite(float(value)):
                    raise ValueError(
                        f"Node {type_id} property {prop.key} interval_slider {name} must be finite"
                    )
            minimum = float(prop.minimum)
            maximum = float(prop.maximum)
            step = float(prop.step)
            if minimum >= maximum:
                raise ValueError(
                    f"Node {type_id} property {prop.key} interval_slider requires minimum < maximum"
                )
            if step < 0.0:
                raise ValueError(
                    f"Node {type_id} property {prop.key} interval_slider step must be >= 0"
                )
        if inline_editor == "interval_fields" and prop.type != INTERVAL_1D_DATA_TYPE:
            raise ValueError(
                f"Node {type_id} property {prop.key} interval_fields requires an interval_1d property"
            )
        if (
            inline_editor != "interval_slider"
            and prop.type == INTERVAL_1D_DATA_TYPE
            and (
                prop.minimum is not None
                or prop.maximum is not None
                or prop.step != 0.0
                or interval_direction
            )
        ):
            raise ValueError(
                f"Node {type_id} property {prop.key} interval editor metadata requires interval_slider"
            )
        inspector_editor = str(prop.inspector_editor).strip()
        if inspector_editor != prop.inspector_editor:
            raise ValueError(
                f"Node {type_id} property {prop.key} inspector_editor must be trimmed"
            )
        if inspector_editor not in self._SUPPORTED_INSPECTOR_EDITORS:
            raise ValueError(
                f"Node {type_id} property {prop.key} inspector_editor has invalid value: {inspector_editor}"
            )
        file_filter = str(prop.file_filter).strip()
        if file_filter != prop.file_filter:
            raise ValueError(
                f"Node {type_id} property {prop.key} file_filter must be trimmed"
            )
        if (
            file_filter
            and prop.type != "path"
            and inline_editor != "path"
            and property_inspector_editor(prop) != "path"
        ):
            raise ValueError(
                f"Node {type_id} property {prop.key} file_filter requires a path property/editor"
            )
        if not isinstance(prop.inspector_visible, bool):
            raise TypeError(
                f"Node {type_id} property {prop.key} inspector_visible must be bool"
            )
        persistence_data_type_id = prop.persistence_data_type_id
        if persistence_data_type_id:
            try:
                persistence_spec = self._data_types.require(persistence_data_type_id)
            except DataTypeCatalogError as exc:
                raise ValueError(
                    f"Node {type_id} property {prop.key} declares {exc}"
                ) from exc
            if persistence_spec.persistence == "never":
                raise ValueError(
                    f"Node {type_id} property {prop.key} data type "
                    f"{persistence_data_type_id!r} does not permit persistence"
                )
        enum_values = tuple(prop.enum_values)
        enum_codes = tuple(prop.enum_codes)
        if prop.type == "enum":
            if not enum_values:
                raise ValueError(
                    f"Node {type_id} enum property {prop.key} must define enum_values"
                )
            if len(set(enum_values)) != len(enum_values):
                raise ValueError(
                    f"Node {type_id} enum property {prop.key} enum_values must be unique"
                )
        elif enum_values and not (inline_editor == "enum" and enum_codes):
            raise ValueError(
                f"Node {type_id} non-enum property {prop.key} cannot define enum_values"
            )
        if enum_codes:
            if inline_editor != "enum" or len(enum_codes) != len(enum_values):
                raise ValueError(
                    f"Node {type_id} property {prop.key} enum_codes must match enum_values"
                )
            if len(set(enum_codes)) != len(enum_codes):
                raise ValueError(
                    f"Node {type_id} property {prop.key} enum_codes must be unique"
                )
        if prop.nullable and prop.type != INTERVAL_1D_DATA_TYPE:
            raise ValueError(
                f"Node {type_id} property {prop.key} nullable is supported only for interval_1d"
            )
        if inline_editor == "list":
            if prop.type != "json" or prop.list_item_type not in {
                "str",
                "int",
                "float",
                "enum",
                "color",
            }:
                raise ValueError(
                    f"Node {type_id} property {prop.key} list editor requires a json property and list_item_type"
                )
            if not isinstance(prop.default, list):
                raise ValueError(
                    f"Node {type_id} property {prop.key} list editor default must be a list"
                )
            if prop.list_item_type == "enum":
                if (
                    not prop.list_item_enum_values
                    or len(prop.list_item_enum_values) != len(prop.list_item_enum_codes)
                    or len(set(prop.list_item_enum_codes))
                    != len(prop.list_item_enum_codes)
                ):
                    raise ValueError(
                        f"Node {type_id} property {prop.key} enum list metadata is invalid"
                    )
                if any(item not in prop.list_item_enum_codes for item in prop.default):
                    raise ValueError(
                        f"Node {type_id} property {prop.key} enum list default contains an invalid code"
                    )
            elif prop.list_item_enum_values or prop.list_item_enum_codes:
                raise ValueError(
                    f"Node {type_id} property {prop.key} non-enum list cannot define enum metadata"
                )
            bounded_list = (
                prop.list_item_minimum is not None or prop.list_item_maximum is not None
            )
            if bounded_list:
                if (
                    prop.list_item_type not in {"int", "float"}
                    or prop.list_item_minimum is None
                    or prop.list_item_maximum is None
                    or not math.isfinite(float(prop.list_item_minimum))
                    or not math.isfinite(float(prop.list_item_maximum))
                    or float(prop.list_item_minimum) >= float(prop.list_item_maximum)
                    or float(prop.list_item_step) < 0.0
                ):
                    raise ValueError(
                        f"Node {type_id} property {prop.key} bounded list metadata is invalid"
                    )
                if any(
                    isinstance(item, bool)
                    or not isinstance(item, Real)
                    or not float(prop.list_item_minimum)
                    <= float(item)
                    <= float(prop.list_item_maximum)
                    for item in prop.default
                ):
                    raise ValueError(
                        f"Node {type_id} property {prop.key} list default is outside its bounds"
                    )
            elif prop.list_item_step != 0.0:
                raise ValueError(
                    f"Node {type_id} property {prop.key} list_item_step requires bounds"
                )
        elif (
            prop.list_item_type
            or prop.list_item_enum_values
            or prop.list_item_enum_codes
            or prop.list_item_minimum is not None
            or prop.list_item_maximum is not None
            or prop.list_item_step != 0.0
        ):
            raise ValueError(
                f"Node {type_id} property {prop.key} list metadata requires the list inline editor"
            )
        normalized_default = property_coercion.coerce_property_value(
            prop,
            prop.default,
            strict=True,
            data_types=self._data_types,
        )
        if inline_editor == "interval_slider":
            if (
                not float(prop.minimum)
                <= normalized_default.start
                <= float(prop.maximum)
            ):
                raise ValueError(
                    f"Node {type_id} property {prop.key} interval start is outside the slider domain"
                )
            if not float(prop.minimum) <= normalized_default.end <= float(prop.maximum):
                raise ValueError(
                    f"Node {type_id} property {prop.key} interval end is outside the slider domain"
                )
            if (
                interval_direction == "increasing"
                and normalized_default.start > normalized_default.end
            ):
                raise ValueError(
                    f"Node {type_id} property {prop.key} default must be increasing"
                )
            if (
                interval_direction == "decreasing"
                and normalized_default.start < normalized_default.end
            ):
                raise ValueError(
                    f"Node {type_id} property {prop.key} default must be decreasing"
                )

def validate_node_spec(
    spec: NodeTypeSpec,
    *,
    data_types: DataTypeCatalog,
) -> None:
    _SpecValidator(data_types).validate(spec)


__all__ = ["validate_node_spec"]
