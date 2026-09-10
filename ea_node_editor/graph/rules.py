from __future__ import annotations

from ea_node_editor.graph.effective_ports import (
    port_accepted_data_types as effective_port_accepted_data_types,
    port_layout_direction,
    port_side as _port_side,
)
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
from ea_node_editor.runtime_contracts import GRAPH_DATA_TYPE_ID


def find_port(spec: NodeTypeSpec, port_key: str) -> PortSpec | None:
    for port in spec.ports:
        if port.key == port_key:
            return port
    return None


def port_direction(spec: NodeTypeSpec, port_key: str) -> str:
    port = find_port(spec, port_key)
    if port is None:
        raise KeyError(f"Port {port_key} not found on node type {spec.type_id}")
    return port_layout_direction(port)


def port_kind(spec: NodeTypeSpec, port_key: str) -> str:
    port = find_port(spec, port_key)
    if port is None:
        raise KeyError(f"Port {port_key} not found on node type {spec.type_id}")
    return port.kind


def port_data_type(spec: NodeTypeSpec, port_key: str) -> str:
    port = find_port(spec, port_key)
    if port is None:
        return GRAPH_DATA_TYPE_ID
    return port.data_type


def port_accepted_data_types(spec: NodeTypeSpec, port_key: str) -> tuple[str, ...]:
    port = find_port(spec, port_key)
    if port is None:
        return (GRAPH_DATA_TYPE_ID,)
    return effective_port_accepted_data_types(port)


def is_port_exposed(node: NodeInstance, spec: NodeTypeSpec, port_key: str) -> bool:
    port = find_port(spec, port_key)
    if port is None:
        raise KeyError(f"Port {port_key} not found on node type {spec.type_id}")
    return bool(port.required or node.exposed_ports.get(port.key, port.exposed))


def default_port(node: NodeInstance, spec: NodeTypeSpec, direction: str) -> str | None:
    for port in spec.ports:
        if port_layout_direction(port) != direction:
            continue
        if bool(port.required or node.exposed_ports.get(port.key, port.exposed)):
            return port.key
    return None


def visible_ports(node: NodeInstance, spec: NodeTypeSpec) -> tuple[list[PortSpec], list[PortSpec]]:
    in_ports: list[PortSpec] = []
    out_ports: list[PortSpec] = []
    for port in spec.ports:
        if not bool(port.required or node.exposed_ports.get(port.key, port.exposed)):
            continue
        if port_layout_direction(port) == "in":
            in_ports.append(port)
        else:
            out_ports.append(port)
    return in_ports, out_ports


def port_side(spec: NodeTypeSpec, port_key: str) -> str:
    port = find_port(spec, port_key)
    if port is None:
        raise KeyError(f"Port {port_key} not found on node type {spec.type_id}")
    return _port_side(port)


__all__ = [
    "default_port",
    "find_port",
    "port_accepted_data_types",
    "is_port_exposed",
    "port_data_type",
    "port_direction",
    "port_kind",
    "port_side",
    "visible_ports",
]
