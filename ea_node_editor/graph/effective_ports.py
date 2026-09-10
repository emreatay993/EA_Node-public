from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, TypeVar

from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.graph.subnode_contract import (
    SUBNODE_PIN_PORT_KEY,
    is_subnode_pin_type as _is_subnode_pin_type,
    is_subnode_shell_type as _is_subnode_shell_type,
    resolve_subnode_pin_definition,
)
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
from ea_node_editor.nodes.instance_resolution import resolve_instance_ports
from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    DataTypeCompatibility,
    GRAPH_DATA_TYPE_ID,
)

_FLOW_EDGE_KINDS = frozenset({"flow"})
_CARDINAL_SIDES = ("top", "right", "bottom", "left")
_LAYOUT_INPUT_SIDES = frozenset({"top", "left"})


@dataclass(slots=True, frozen=True)
class EffectivePort:
    key: str
    label: str
    direction: str
    kind: str
    data_type: str
    data_access: str = "item"
    side: str = ""
    required: bool = False
    exposed: bool = True
    allow_multiple_connections: bool = False
    allow_empty_string: bool = False
    uses_property_default: bool = False
    accepted_data_types: tuple[str, ...] = ()
    display_tier: str = ""
    description: str = ""


PortLike = TypeVar("PortLike", EffectivePort, PortSpec)


def port_side(port: EffectivePort | PortSpec) -> str:
    side = str(getattr(port, "side", "") or "").strip().lower()
    if side in _CARDINAL_SIDES:
        return side
    return ""


def is_neutral_flow_port(port: EffectivePort | PortSpec) -> bool:
    return (
        str(port.direction) == "neutral"
        and str(port.kind) == "flow"
        and str(port.data_type) == "flow"
        and bool(port_side(port))
    )


def is_flow_edge_port_kind(kind: str) -> bool:
    return str(kind or "").strip().lower() in _FLOW_EDGE_KINDS


def is_flow_edge_port(port: EffectivePort | PortSpec) -> bool:
    return is_flow_edge_port_kind(str(getattr(port, "kind", "")))


def port_layout_direction(port: EffectivePort | PortSpec) -> str:
    if not is_neutral_flow_port(port):
        return str(port.direction)
    return "in" if port_side(port) in _LAYOUT_INPUT_SIDES else "out"


def port_supports_outgoing_edge(port: EffectivePort | PortSpec) -> bool:
    return str(port.direction) == "out" or is_neutral_flow_port(port)


def port_supports_incoming_edge(port: EffectivePort | PortSpec) -> bool:
    return str(port.direction) == "in" or is_neutral_flow_port(port)


def is_subnode_shell_type(type_id: str) -> bool:
    return _is_subnode_shell_type(type_id)


def is_subnode_pin_type(type_id: str) -> bool:
    return _is_subnode_pin_type(type_id)


def are_port_kinds_compatible(source_kind: str, target_kind: str) -> bool:
    source_kind = str(source_kind or "").strip().lower()
    target_kind = str(target_kind or "").strip().lower()
    if source_kind == "flow" or target_kind == "flow":
        return source_kind == target_kind
    return source_kind == "data" and target_kind == "data"


def port_accepted_data_types(port: EffectivePort | PortSpec) -> tuple[str, ...]:
    declared = (
        str(getattr(port, "data_type", "")),
        *tuple(getattr(port, "accepted_data_types", ()) or ()),
    )
    return tuple(dict.fromkeys(declared))


def port_compatibility(
    source_port: EffectivePort | PortSpec,
    target_port: EffectivePort | PortSpec,
    *,
    data_types: DataTypeCatalog,
) -> DataTypeCompatibility:
    source_type_id = str(source_port.data_type)
    target_type_id = str(target_port.data_type)
    if not are_port_kinds_compatible(source_port.kind, target_port.kind):
        return DataTypeCompatibility(
            status="incompatible",
            source_type_id=source_type_id,
            target_type_id=target_type_id,
            reason_code="port_kind_mismatch",
        )
    source_kind = str(source_port.kind or "").strip().lower()
    target_kind = str(target_port.kind or "").strip().lower()
    if source_kind == "flow" or target_kind == "flow":
        return DataTypeCompatibility(
            status="assignable",
            source_type_id="flow",
            target_type_id="flow",
            matched_type_id="flow",
            reason_code="flow_kind_match",
        )
    return data_types.compatibility(
        source_type_id,
        target_type_id,
        tuple(getattr(target_port, "accepted_data_types", ()) or ()),
    )


def ports_compatible(
    source_port: EffectivePort | PortSpec,
    target_port: EffectivePort | PortSpec,
    *,
    data_types: DataTypeCatalog,
) -> bool:
    return port_compatibility(
        source_port,
        target_port,
        data_types=data_types,
    ).is_compatible


def port_display_tier(port: EffectivePort | PortSpec) -> str:
    explicit = str(getattr(port, "display_tier", "") or "").strip().lower()
    if explicit in {"simple", "advanced"}:
        return explicit
    return ""


def effective_ports(
    *,
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
) -> tuple[EffectivePort, ...]:
    if is_subnode_shell_type(node.type_id):
        return _subnode_shell_ports(node=node, workspace_nodes=workspace_nodes)
    if is_subnode_pin_type(node.type_id):
        return (_subnode_pin_port(node=node),)
    resolved_ports = resolve_instance_ports(spec, node.properties)
    non_label_rename_directions = {
        group.direction
        for group in spec.dynamic_port_groups
        if group.rename_mode != "label"
    }
    non_label_dynamic_port_keys = {
        port.key
        for port in resolved_ports[len(spec.ports) :]
        if port.direction in non_label_rename_directions
    }
    return tuple(
        EffectivePort(
            key=port.key,
            label=(
                ""
                if port.key in non_label_dynamic_port_keys
                else node.port_labels.get(port.key, "")
            )
            or port.label
            or port.key,
            direction=port.direction,
            kind=port.kind,
            data_type=port.data_type,
            data_access=str(getattr(port, "data_access", "item") or "item"),
            side=port.side,
            required=bool(port.required),
            exposed=bool(port.required or node.exposed_ports.get(port.key, port.exposed)),
            allow_multiple_connections=(
                bool(port.allow_multiple_connections)
                if str(port.kind) == "flow"
                else False
            ),
            allow_empty_string=bool(port.allow_empty_string),
            uses_property_default=bool(port.uses_property_default),
            accepted_data_types=port.accepted_data_types,
            display_tier=port_display_tier(port),
            description=str(getattr(port, "description", "") or ""),
        )
        for port in resolved_ports
    )


def ordered_ports_for_display(ports: Iterable[PortLike]) -> tuple[PortLike, ...]:
    indexed_ports = list(enumerate(ports))
    indexed_ports.sort(key=lambda item: (_display_port_priority(item[1]), item[0]))
    return tuple(port for _, port in indexed_ports)


def _display_port_priority(port: EffectivePort | PortSpec) -> int:
    return 0


def find_port(
    *,
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
    port_key: str,
) -> EffectivePort | None:
    for port in effective_ports(node=node, spec=spec, workspace_nodes=workspace_nodes):
        if port.key == port_key:
            return port
    return None


def port_direction(
    *,
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
    port_key: str,
) -> str:
    port = find_port(node=node, spec=spec, workspace_nodes=workspace_nodes, port_key=port_key)
    if port is None:
        raise KeyError(f"Port {port_key} not found on node type {spec.type_id}")
    return port_layout_direction(port)


def port_kind(
    *,
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
    port_key: str,
) -> str:
    port = find_port(node=node, spec=spec, workspace_nodes=workspace_nodes, port_key=port_key)
    if port is None:
        raise KeyError(f"Port {port_key} not found on node type {spec.type_id}")
    return port.kind


def port_data_type(
    *,
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
    port_key: str,
) -> str:
    port = find_port(node=node, spec=spec, workspace_nodes=workspace_nodes, port_key=port_key)
    if port is None:
        return GRAPH_DATA_TYPE_ID
    return port.data_type


def port_data_access(
    *,
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
    port_key: str,
) -> str:
    port = find_port(node=node, spec=spec, workspace_nodes=workspace_nodes, port_key=port_key)
    if port is None:
        return "item"
    return str(port.data_access)


def is_port_exposed(
    *,
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
    port_key: str,
) -> bool:
    port = find_port(node=node, spec=spec, workspace_nodes=workspace_nodes, port_key=port_key)
    if port is None:
        raise KeyError(f"Port {port_key} not found on node type {spec.type_id}")
    return bool(port.exposed)


def port_allows_multiple_connections(
    *,
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
    port_key: str,
) -> bool:
    port = find_port(node=node, spec=spec, workspace_nodes=workspace_nodes, port_key=port_key)
    if port is None:
        raise KeyError(f"Port {port_key} not found on node type {spec.type_id}")
    return bool(port.allow_multiple_connections)


def target_port_has_capacity(
    *,
    edges: Iterable[EdgeInstance],
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
    port_key: str,
) -> bool:
    port = find_port(node=node, spec=spec, workspace_nodes=workspace_nodes, port_key=port_key)
    if port is None:
        raise KeyError(f"Port {port_key} not found on node type {spec.type_id}")
    if not port_supports_incoming_edge(port):
        raise ValueError(f"Port {port_key} does not accept incoming edges on node type {spec.type_id}")
    if str(port.kind) == "data" or port.allow_multiple_connections:
        return True
    for edge in edges:
        if edge.target_node_id == node.node_id and edge.target_port_key == port_key:
            return False
    return True


def default_port(
    *,
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
    direction: str,
) -> str | None:
    for port in effective_ports(node=node, spec=spec, workspace_nodes=workspace_nodes):
        if port_layout_direction(port) != direction:
            continue
        if port.exposed:
            return port.key
    return None


def visible_ports(
    *,
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
) -> tuple[list[EffectivePort], list[EffectivePort]]:
    in_ports: list[EffectivePort] = []
    out_ports: list[EffectivePort] = []
    for port in ordered_ports_for_display(
        effective_ports(node=node, spec=spec, workspace_nodes=workspace_nodes)
    ):
        if not port.exposed:
            continue
        if port_layout_direction(port) == "in":
            in_ports.append(port)
        else:
            out_ports.append(port)
    return in_ports, out_ports


def preferred_connection_port(
    *,
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance],
    direction: str,
    peer_node: NodeInstance,
) -> str | None:
    neutral_ports = [
        port
        for port in effective_ports(node=node, spec=spec, workspace_nodes=workspace_nodes)
        if port.exposed and is_neutral_flow_port(port)
    ]
    if not neutral_ports:
        return default_port(
            node=node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            direction=direction,
        )

    for side in _ordered_cardinal_sides_toward(node=node, peer_node=peer_node):
        for port in neutral_ports:
            if port.side == side:
                return port.key
    return neutral_ports[0].key


def _ordered_cardinal_sides_toward(*, node: NodeInstance, peer_node: NodeInstance) -> tuple[str, ...]:
    dx = float(peer_node.x) - float(node.x)
    dy = float(peer_node.y) - float(node.y)

    if abs(dx) >= abs(dy):
        primary = "right" if dx >= 0.0 else "left"
        secondary = "bottom" if dy >= 0.0 else "top"
    else:
        primary = "bottom" if dy >= 0.0 else "top"
        secondary = "right" if dx >= 0.0 else "left"

    ordered = [
        primary,
        secondary,
        _opposite_side(secondary),
        _opposite_side(primary),
    ]
    seen: set[str] = set()
    result: list[str] = []
    for side in ordered:
        if side in seen:
            continue
        seen.add(side)
        result.append(side)
    return tuple(result)


def _opposite_side(side: str) -> str:
    if side == "top":
        return "bottom"
    if side == "right":
        return "left"
    if side == "bottom":
        return "top"
    return "right"


def _subnode_shell_ports(
    *,
    node: NodeInstance,
    workspace_nodes: Mapping[str, NodeInstance],
) -> tuple[EffectivePort, ...]:
    child_pins: list[NodeInstance] = []
    for candidate in workspace_nodes.values():
        if candidate.parent_node_id != node.node_id:
            continue
        if not is_subnode_pin_type(candidate.type_id):
            continue
        child_pins.append(candidate)
    child_pins.sort(key=lambda candidate: (float(candidate.y), float(candidate.x), candidate.node_id))

    ports: list[EffectivePort] = []
    for pin_node in child_pins:
        pin_definition = resolve_subnode_pin_definition(
            pin_node.type_id,
            pin_node.properties,
        )
        shell_direction = pin_definition.shell_port_direction
        shell_key = pin_node.node_id
        ports.append(
            EffectivePort(
                key=shell_key,
                label=pin_definition.label,
                direction=shell_direction,
                kind=pin_definition.kind,
                data_type=pin_definition.data_type,
                data_access=pin_definition.data_access,
                required=shell_direction == "in",
                exposed=bool(node.exposed_ports.get(shell_key, True)),
                allow_multiple_connections=False,
                accepted_data_types=pin_definition.accepted_data_types,
                display_tier=port_display_tier(pin_definition),
            )
        )
    return tuple(ports)


def _subnode_pin_port(*, node: NodeInstance) -> EffectivePort:
    pin_definition = resolve_subnode_pin_definition(
        node.type_id,
        node.properties,
    )
    return EffectivePort(
        key=SUBNODE_PIN_PORT_KEY,
        label=pin_definition.label,
        direction=pin_definition.pin_port_direction,
        kind=pin_definition.kind,
        data_type=pin_definition.data_type,
        data_access=pin_definition.data_access,
        required=pin_definition.pin_port_direction == "in",
        exposed=bool(node.exposed_ports.get(SUBNODE_PIN_PORT_KEY, True)),
        allow_multiple_connections=False,
        accepted_data_types=pin_definition.accepted_data_types,
        display_tier=port_display_tier(pin_definition),
    )


__all__ = [
    "EffectivePort",
    "are_port_kinds_compatible",
    "default_port",
    "effective_ports",
    "find_port",
    "is_flow_edge_port",
    "is_flow_edge_port_kind",
    "is_port_exposed",
    "is_neutral_flow_port",
    "port_allows_multiple_connections",
    "port_layout_direction",
    "port_side",
    "is_subnode_pin_type",
    "is_subnode_shell_type",
    "port_data_type",
    "port_data_access",
    "port_direction",
    "port_display_tier",
    "port_kind",
    "port_compatibility",
    "port_supports_incoming_edge",
    "port_supports_outgoing_edge",
    "preferred_connection_port",
    "ordered_ports_for_display",
    "port_accepted_data_types",
    "ports_compatible",
    "target_port_has_capacity",
    "visible_ports",
]
