# Purpose: Resolve instance-specific node specs and dynamic ports with shared port validation.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_spec_validation.py, tests/test_registry_validation.py
# Landmarks: validate_port; resolve_dynamic_port_groups; resolve_instance_spec; resolve_instance_ports

from __future__ import annotations

import copy
from collections.abc import Mapping

from ea_node_editor.runtime_contracts import (
    DataTypeCatalog, DataTypeCatalogError, GRAPH_DATA_TYPE_ID,
)

from . import property_coercion
from .node_specs import NodeTypeSpec, PortSpec

_SUPPORTED_DIRECTIONS = {"in", "out", "neutral"}
_SUPPORTED_PORT_SIDES = {"", "top", "right", "bottom", "left"}
_SUPPORTED_KINDS = {"data", "flow"}
_SUPPORTED_DATA_ACCESS = {"item", "list", "tree"}


def validate_port(
    spec: NodeTypeSpec,
    port: PortSpec,
    *,
    data_types: DataTypeCatalog | None = None,
) -> None:
    type_id = spec.type_id
    if not isinstance(port, PortSpec):
        raise TypeError(f"Node {type_id} ports must be PortSpec instances")
    if not isinstance(port.key, str) or not port.key or port.key.strip() != port.key:
        raise ValueError(f"Node {type_id} has invalid port key: {port.key!r}")
    if port.direction not in _SUPPORTED_DIRECTIONS:
        raise ValueError(
            f"Node {type_id} port {port.key} has invalid direction: {port.direction}"
        )
    if port.kind not in _SUPPORTED_KINDS:
        raise ValueError(
            f"Node {type_id} port {port.key} has invalid kind: {port.kind}"
        )
    if port.data_access not in _SUPPORTED_DATA_ACCESS:
        raise ValueError(
            f"Node {type_id} port {port.key} has invalid data_access: {port.data_access}"
        )
    if (
        not isinstance(port.data_type, str)
        or not port.data_type
        or port.data_type.strip() != port.data_type
    ):
        raise ValueError(
            f"Node {type_id} port {port.key} has invalid data_type: {port.data_type!r}"
        )
    for accepted_type in port.accepted_data_types:
        if not accepted_type or accepted_type.strip() != accepted_type:
            raise ValueError(
                f"Node {type_id} port {port.key} has invalid accepted_data_type: {accepted_type!r}"
            )
    if port.kind == "data" and data_types is not None:
        try:
            data_types.require(port.data_type)
            for accepted_type in port.accepted_data_types:
                data_types.require(accepted_type)
        except DataTypeCatalogError as exc:
            raise ValueError(f"Node {type_id} port {port.key} declares {exc}") from exc
    elif port.kind != "data" and port.accepted_data_types:
        raise ValueError(
            f"Node {type_id} flow port {port.key} cannot declare accepted_data_types"
        )
    if not isinstance(port.side, str) or port.side.strip() != port.side:
        raise ValueError(
            f"Node {type_id} port {port.key} side must be a trimmed string"
        )
    if port.side not in _SUPPORTED_PORT_SIDES:
        raise ValueError(
            f"Node {type_id} port {port.key} has invalid side: {port.side}"
        )
    if port.required is not None and not isinstance(port.required, bool):
        raise TypeError(f"Node {type_id} port {port.key} required must be bool or None")
    active_data_input = (
        spec.runtime_behavior == "active"
        and port.direction == "in"
        and port.kind == "data"
    )
    if active_data_input and port.required is None:
        raise ValueError(
            f"Node {type_id} active data input {port.key} must explicitly declare required=True or False"
        )
    if port.required is True and not active_data_input:
        raise ValueError(
            f"Node {type_id} port {port.key} required=True is only valid on active data inputs"
        )
    if not isinstance(port.uses_property_default, bool):
        raise TypeError(
            f"Node {type_id} port {port.key} uses_property_default must be bool"
        )
    if not isinstance(port.exposed, bool):
        raise TypeError(f"Node {type_id} port {port.key} exposed must be bool")
    if not isinstance(port.allow_multiple_connections, bool):
        raise TypeError(
            f"Node {type_id} port {port.key} allow_multiple_connections must be bool"
        )
    if port.direction == "neutral":
        if spec.runtime_behavior != "passive":
            raise ValueError(
                f"Node {type_id} port {port.key} neutral direction is only supported on passive nodes"
            )
        if port.kind != "flow" or port.data_type != "flow":
            raise ValueError(
                f"Node {type_id} port {port.key} neutral direction requires flow kind and data_type"
            )
        if not port.side:
            raise ValueError(
                f"Node {type_id} port {port.key} neutral direction requires a cardinal side"
            )
        if port.key != port.side:
            raise ValueError(
                f"Node {type_id} port {port.key} neutral direction side must match the stored port key"
            )
        if not port.allow_multiple_connections:
            raise ValueError(
                f"Node {type_id} port {port.key} neutral passive flow ports must allow multiple connections"
            )
    elif port.side:
        raise ValueError(
            f"Node {type_id} port {port.key} side metadata is only supported on neutral passive flow ports"
        )


def validate_type_forwarding(type_id: str, ports: tuple[PortSpec, ...]) -> None:
    """Validate relationships against the complete static or resolved interface."""
    by_key = {port.key: port for port in ports}
    for port in ports:
        if not port.type_from_input:
            continue
        prefix = f"Node {type_id} port {port.key} type_from_input"
        if port.direction != "out" or port.kind != "data" or port.data_type != GRAPH_DATA_TYPE_ID:
            raise ValueError(f"{prefix} requires an Any data output")
        source = by_key.get(port.type_from_input)
        if source is None:
            raise ValueError(f"{prefix} references missing input {port.type_from_input!r}")
        if source.direction != "in" or source.kind != "data" or source.data_type != GRAPH_DATA_TYPE_ID:
            raise ValueError(f"{prefix} must reference an Any data input")
        if source.data_access != port.data_access:
            raise ValueError(f"{prefix} requires matching input and output data_access")


def resolve_dynamic_port_groups(
    spec: NodeTypeSpec,
    properties: Mapping[str, object],
    *,
    data_types: DataTypeCatalog | None = None,
) -> tuple[tuple[PortSpec, ...], ...]:
    if not spec.dynamic_port_groups:
        return ()
    resolved_properties = {
        prop.key: property_coercion.coerce_property_value(
            prop,
            properties[prop.key] if prop.key in properties else prop.default,
            strict=prop.key not in properties,
            data_types=data_types,
        )
        for prop in spec.properties
    }
    static_ports = {port.key: port for port in spec.ports}
    seen_keys = set(static_ports)
    resolved_groups: list[tuple[PortSpec, ...]] = []
    for group in spec.dynamic_port_groups:
        try:
            ports = group.ports_resolver(dict(resolved_properties))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"Node {spec.type_id} dynamic port group {group.group_id} resolver failed"
            ) from exc
        if not isinstance(ports, tuple):
            raise ValueError(
                f"Node {spec.type_id} dynamic port group {group.group_id} resolver must return tuple[PortSpec, ...]"
            )
        if len(ports) < group.minimum:
            raise ValueError(
                f"Node {spec.type_id} dynamic port group {group.group_id} requires at least {group.minimum} ports"
            )
        if group.maximum is not None and len(ports) > group.maximum:
            raise ValueError(
                f"Node {spec.type_id} dynamic port group {group.group_id} allows at most {group.maximum} ports"
            )
        member_keys: set[str] = set()
        for port in ports:
            if not isinstance(port, PortSpec):
                raise ValueError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} must resolve PortSpec instances"
                )
            validate_port(spec, port, data_types=data_types)
            if port.direction != group.direction:
                raise ValueError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} port {port.key} direction must be {group.direction}"
                )
            if port.kind != "data":
                raise ValueError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} port {port.key} must be a data port"
                )
            if port.uses_property_default:
                raise ValueError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} port {port.key} cannot use a property default"
                )
            if not port.key or port.key.strip() != port.key:
                raise ValueError(
                    f"Node {spec.type_id} dynamic port group {group.group_id} has invalid port key: {port.key!r}"
                )
            if port.key in member_keys:
                raise ValueError(f"Node {spec.type_id} has duplicate port key: {port.key}")
            member_keys.add(port.key)
            if group.property_editor is not None:
                if static_ports.get(port.key) != port:
                    raise ValueError(
                        f"Node {spec.type_id} source-backed group {group.group_id} "
                        f"must reference an existing resolved port: {port.key}"
                    )
            elif port.key in seen_keys:
                raise ValueError(
                    f"Node {spec.type_id} has duplicate port key: {port.key}"
                )
            seen_keys.add(port.key)
        resolved_groups.append(ports)
        if group.property_editor is None:
            resolved_properties[group.property_key] = [port.key for port in ports]
    validate_type_forwarding(
        spec.type_id,
        spec.ports + tuple(
            port
            for group, ports in zip(spec.dynamic_port_groups, resolved_groups, strict=True)
            if group.property_editor is None
            for port in ports
        ),
    )
    return tuple(resolved_groups)


def resolve_instance_ports(
    spec: NodeTypeSpec,
    properties: Mapping[str, object],
    *,
    data_types: DataTypeCatalog | None = None,
) -> tuple[PortSpec, ...]:
    spec = resolve_instance_spec(spec, properties)
    dynamic_ports = tuple(
        port
        for group, group_ports in zip(
            spec.dynamic_port_groups,
            resolve_dynamic_port_groups(spec, properties, data_types=data_types),
            strict=True,
        )
        if group.property_editor is None
        for port in group_ports
    )
    ports = spec.ports + dynamic_ports
    validate_type_forwarding(spec.type_id, ports)
    return ports


def resolve_instance_spec(
    spec: NodeTypeSpec,
    properties: Mapping[str, object],
) -> NodeTypeSpec:
    resolver = spec.instance_spec_resolver
    if resolver is None:
        return spec
    resolved_properties = {
        prop.key: copy.deepcopy(prop.default) for prop in spec.properties
    }
    resolved_properties.update(dict(properties))
    resolved = resolver(spec, resolved_properties)
    if not isinstance(resolved, NodeTypeSpec):
        raise TypeError(
            f"Node {spec.type_id} instance_spec_resolver must return NodeTypeSpec"
        )
    if resolved.type_id != spec.type_id:
        raise ValueError(
            f"Node {spec.type_id} instance_spec_resolver changed the node type ID"
        )
    if resolved.instance_spec_resolver is not None:
        raise ValueError(
            f"Node {spec.type_id} resolved instance spec must clear instance_spec_resolver"
        )
    return resolved


__all__ = [
    "resolve_dynamic_port_groups",
    "resolve_instance_ports",
    "resolve_instance_spec",
    "validate_port",
    "validate_type_forwarding",
]
