from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ea_node_editor.graph.effective_ports import find_port, is_subnode_pin_type
from ea_node_editor.graph.hierarchy import normalize_scope_path, scope_parent_id
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.record_mutation_ops import GraphRecordMutation
from ea_node_editor.graph.records import EdgeInstance
from ea_node_editor.graph.subnode_contract import (
    SUBNODE_INPUT_TYPE_ID,
    SUBNODE_OUTPUT_TYPE_ID,
    SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY,
    SUBNODE_PIN_DATA_ACCESS_PROPERTY,
    SUBNODE_PIN_DATA_TYPE_PROPERTY,
    SUBNODE_PIN_KIND_PROPERTY,
    SUBNODE_PIN_LABEL_PROPERTY,
    SUBNODE_PIN_PORT_KEY,
    SUBNODE_TYPE_ID,
    default_subnode_pin_label,
    is_subnode_shell_type,
    normalize_subnode_pin_data_type,
    normalize_subnode_pin_accepted_data_types,
    normalize_subnode_pin_data_access,
    normalize_subnode_pin_kind,
)
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.runtime_contracts import GRAPH_DATA_TYPE_ID


_PIN_OFFSET_X = 220.0
_PIN_ROW_STEP = 70.0


@dataclass(slots=True, frozen=True)
class GroupSubnodeResult:
    shell_node_id: str
    moved_node_ids: tuple[str, ...]
    created_pin_node_ids: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class UngroupSubnodeResult:
    removed_shell_node_id: str
    moved_node_ids: tuple[str, ...]
    removed_pin_node_ids: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class _BoundaryEdge:
    edge: EdgeInstance
    pin_type_id: str
    label: str
    kind: str
    data_type: str
    accepted_data_types: tuple[str, ...]
    data_access: str


def group_selection_into_subnode(
    *,
    model: GraphModel,
    registry,
    workspace_id: str,
    selected_node_ids: Sequence[object],
    scope_path: Sequence[object] | None,
    shell_x: float,
    shell_y: float,
) -> GroupSubnodeResult | None:
    workspace = model.project.workspaces.get(str(workspace_id).strip())
    if workspace is None:
        return None
    return _group_selection_into_subnode_operation(
        model=model,
        registry=registry,
        workspace_id=workspace.workspace_id,
        selected_node_ids=selected_node_ids,
        scope_path=scope_path,
        shell_x=shell_x,
        shell_y=shell_y,
    )


def _group_selection_into_subnode_operation(
    *,
    model: GraphModel,
    registry,
    workspace_id: str,
    selected_node_ids: Sequence[object],
    scope_path: Sequence[object] | None,
    shell_x: float,
    shell_y: float,
) -> GroupSubnodeResult | None:
    workspace = model.project.workspaces[str(workspace_id).strip()]
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    records = GraphRecordMutation(model=model, workspace_id=workspace.workspace_id)
    normalized_scope = normalize_scope_path(workspace, scope_path)
    expected_parent_id = scope_parent_id(normalized_scope)
    roots = _normalize_selected_roots(
        workspace=workspace,
        selected_node_ids=selected_node_ids,
        expected_parent_id=expected_parent_id,
    )
    if len(roots) < 2:
        return None
    if not _roots_share_parent(workspace=workspace, node_ids=roots):
        return None

    selected_set = set(roots)
    incoming_edges, outgoing_edges = _boundary_edges(
        workspace=workspace,
        selected_node_ids=selected_set,
    )
    incoming_boundary = [
        _build_boundary_edge(
            edge=edge,
            pin_type_id=SUBNODE_INPUT_TYPE_ID,
            registry=registry,
            workspace=workspace,
            inner_node_id=edge.target_node_id,
            inner_port_key=edge.target_port_key,
        )
        for edge in incoming_edges
    ]
    outgoing_boundary = [
        _build_boundary_edge(
            edge=edge,
            pin_type_id=SUBNODE_OUTPUT_TYPE_ID,
            registry=registry,
            workspace=workspace,
            inner_node_id=edge.source_node_id,
            inner_port_key=edge.source_port_key,
        )
        for edge in outgoing_edges
    ]

    shell_defaults = registry.default_properties(SUBNODE_TYPE_ID)
    shell_spec = registry.get_spec(SUBNODE_TYPE_ID)
    shell = mutations.add_node(
        type_id=SUBNODE_TYPE_ID,
        title=shell_spec.display_name,
        x=float(shell_x),
        y=float(shell_y),
        properties=shell_defaults,
        exposed_ports={},
        parent_node_id=expected_parent_id,
    )

    for node_id in roots:
        records._set_node_parent_record(node_id, shell.node_id)

    created_pin_ids: list[str] = []

    for index, boundary in enumerate(incoming_boundary):
        pin_id = _create_boundary_pin(
            mutations=mutations,
            shell_node_id=shell.node_id,
            pin_type_id=boundary.pin_type_id,
            x=float(shell_x) - _PIN_OFFSET_X,
            y=float(shell_y) + (index * _PIN_ROW_STEP),
            label=boundary.label,
            kind=boundary.kind,
            data_type=boundary.data_type,
            accepted_data_types=boundary.accepted_data_types,
            data_access=boundary.data_access,
        )
        created_pin_ids.append(pin_id)
        records._remove_edge_record(boundary.edge.edge_id)
        records._add_edge_record(
            source_node_id=boundary.edge.source_node_id,
            source_port_key=boundary.edge.source_port_key,
            target_node_id=shell.node_id,
            target_port_key=pin_id,
            enabled=boundary.edge.enabled,
            input_order=boundary.edge.input_order,
        )
        records._add_edge_record(
            source_node_id=pin_id,
            source_port_key=SUBNODE_PIN_PORT_KEY,
            target_node_id=boundary.edge.target_node_id,
            target_port_key=boundary.edge.target_port_key,
            enabled=boundary.edge.enabled,
            input_order=boundary.edge.input_order,
        )

    for index, boundary in enumerate(outgoing_boundary):
        pin_id = _create_boundary_pin(
            mutations=mutations,
            shell_node_id=shell.node_id,
            pin_type_id=boundary.pin_type_id,
            x=float(shell_x) + _PIN_OFFSET_X,
            y=float(shell_y) + (index * _PIN_ROW_STEP),
            label=boundary.label,
            kind=boundary.kind,
            data_type=boundary.data_type,
            accepted_data_types=boundary.accepted_data_types,
            data_access=boundary.data_access,
        )
        created_pin_ids.append(pin_id)
        records._remove_edge_record(boundary.edge.edge_id)
        records._add_edge_record(
            source_node_id=boundary.edge.source_node_id,
            source_port_key=boundary.edge.source_port_key,
            target_node_id=pin_id,
            target_port_key=SUBNODE_PIN_PORT_KEY,
            enabled=boundary.edge.enabled,
            input_order=boundary.edge.input_order,
        )
        records._add_edge_record(
            source_node_id=shell.node_id,
            source_port_key=pin_id,
            target_node_id=boundary.edge.target_node_id,
            target_port_key=boundary.edge.target_port_key,
            enabled=boundary.edge.enabled,
            input_order=boundary.edge.input_order,
        )

    return GroupSubnodeResult(
        shell_node_id=shell.node_id,
        moved_node_ids=tuple(roots),
        created_pin_node_ids=tuple(created_pin_ids),
    )


def ungroup_subnode(
    *,
    model: GraphModel,
    workspace_id: str,
    shell_node_id: object,
) -> UngroupSubnodeResult | None:
    workspace = model.project.workspaces.get(str(workspace_id).strip())
    if workspace is None:
        return None
    return _ungroup_subnode_operation(
        model=model,
        workspace_id=workspace.workspace_id,
        shell_node_id=shell_node_id,
    )


def _ungroup_subnode_operation(
    *,
    model: GraphModel,
    workspace_id: str,
    shell_node_id: object,
) -> UngroupSubnodeResult | None:
    workspace = model.project.workspaces[str(workspace_id).strip()]
    records = GraphRecordMutation(model=model, workspace_id=workspace.workspace_id)
    normalized_shell_id = str(shell_node_id).strip()
    if not normalized_shell_id:
        return None
    shell = workspace.nodes.get(normalized_shell_id)
    if shell is None or not is_subnode_shell_type(shell.type_id):
        return None

    direct_children = [
        node
        for node in workspace.nodes.values()
        if node.parent_node_id == normalized_shell_id
    ]
    direct_children.sort(key=lambda node: (float(node.y), float(node.x), node.node_id))

    pin_nodes = [node for node in direct_children if is_subnode_pin_type(node.type_id)]
    moved_nodes = [node for node in direct_children if not is_subnode_pin_type(node.type_id)]

    rewired_edges: dict[tuple[str, str, str, str], tuple[bool, int]] = {}
    for pin_node in pin_nodes:
        if pin_node.type_id == SUBNODE_INPUT_TYPE_ID:
            outer_edges = [
                edge
                for edge in workspace.edges.values()
                if edge.target_node_id == normalized_shell_id
                and edge.target_port_key == pin_node.node_id
            ]
            inner_edges = [
                edge
                for edge in workspace.edges.values()
                if edge.source_node_id == pin_node.node_id
                and edge.source_port_key == SUBNODE_PIN_PORT_KEY
            ]
            outer_edges.sort(key=_edge_sort_key)
            inner_edges.sort(key=_edge_sort_key)
            for outer in outer_edges:
                for inner in inner_edges:
                    _remember_rewired_edge(
                        rewired_edges,
                        (
                            outer.source_node_id,
                            outer.source_port_key,
                            inner.target_node_id,
                            inner.target_port_key,
                        ),
                        enabled=outer.enabled and inner.enabled,
                        input_order=inner.input_order,
                    )
        else:
            inner_edges = [
                edge
                for edge in workspace.edges.values()
                if edge.target_node_id == pin_node.node_id
                and edge.target_port_key == SUBNODE_PIN_PORT_KEY
            ]
            outer_edges = [
                edge
                for edge in workspace.edges.values()
                if edge.source_node_id == normalized_shell_id
                and edge.source_port_key == pin_node.node_id
            ]
            inner_edges.sort(key=_edge_sort_key)
            outer_edges.sort(key=_edge_sort_key)
            for inner in inner_edges:
                for outer in outer_edges:
                    _remember_rewired_edge(
                        rewired_edges,
                        (
                            inner.source_node_id,
                            inner.source_port_key,
                            outer.target_node_id,
                            outer.target_port_key,
                        ),
                        enabled=inner.enabled and outer.enabled,
                        input_order=outer.input_order,
                    )

    for node in moved_nodes:
        records._set_node_parent_record(node.node_id, shell.parent_node_id)

    for pin_node in pin_nodes:
        records._remove_node_record(pin_node.node_id)
    records._remove_node_record(normalized_shell_id)

    for (
        source_node_id,
        source_port_key,
        target_node_id,
        target_port_key,
    ), (enabled, input_order) in sorted(rewired_edges.items()):
        if source_node_id not in workspace.nodes or target_node_id not in workspace.nodes:
            continue
        try:
            records._add_edge_record(
                source_node_id=source_node_id,
                source_port_key=source_port_key,
                target_node_id=target_node_id,
                target_port_key=target_port_key,
                enabled=enabled,
                input_order=input_order,
            )
        except (KeyError, ValueError):
            continue

    return UngroupSubnodeResult(
        removed_shell_node_id=normalized_shell_id,
        moved_node_ids=tuple(node.node_id for node in moved_nodes),
        removed_pin_node_ids=tuple(node.node_id for node in pin_nodes),
    )


def _normalize_selected_roots(
    *,
    workspace,
    selected_node_ids: Sequence[object],
    expected_parent_id: str | None,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in selected_node_ids:
        node_id = str(value).strip()
        if not node_id or node_id in seen:
            continue
        node = workspace.nodes.get(node_id)
        if node is None:
            continue
        if node.parent_node_id != expected_parent_id:
            continue
        seen.add(node_id)
        normalized.append(node_id)
    return normalized


def _roots_share_parent(*, workspace, node_ids: Sequence[str]) -> bool:
    parent_values = {
        workspace.nodes[node_id].parent_node_id
        for node_id in node_ids
        if node_id in workspace.nodes
    }
    return len(parent_values) == 1


def _boundary_edges(
    *,
    workspace,
    selected_node_ids: set[str],
) -> tuple[list[EdgeInstance], list[EdgeInstance]]:
    incoming: list[EdgeInstance] = []
    outgoing: list[EdgeInstance] = []
    for edge in workspace.edges.values():
        source_in = edge.source_node_id in selected_node_ids
        target_in = edge.target_node_id in selected_node_ids
        if source_in and not target_in:
            outgoing.append(edge)
        elif target_in and not source_in:
            incoming.append(edge)
    incoming.sort(
        key=lambda edge: _incoming_boundary_sort_key(workspace, edge),
    )
    outgoing.sort(
        key=lambda edge: _outgoing_boundary_sort_key(workspace, edge),
    )
    return incoming, outgoing


def _incoming_boundary_sort_key(
    workspace,
    edge: EdgeInstance,
) -> tuple[float, float, float, float, str, str, str]:
    source_y, source_x = _node_sort_position(workspace, edge.source_node_id)
    target_y, target_x = _node_sort_position(workspace, edge.target_node_id)
    return (
        source_y,
        source_x,
        target_y,
        target_x,
        edge.source_port_key,
        edge.target_port_key,
        edge.edge_id,
    )


def _outgoing_boundary_sort_key(
    workspace,
    edge: EdgeInstance,
) -> tuple[float, float, float, float, str, str, str]:
    source_y, source_x = _node_sort_position(workspace, edge.source_node_id)
    target_y, target_x = _node_sort_position(workspace, edge.target_node_id)
    return (
        target_y,
        target_x,
        source_y,
        source_x,
        edge.target_port_key,
        edge.source_port_key,
        edge.edge_id,
    )


def _node_sort_position(workspace, node_id: str) -> tuple[float, float]:
    node = workspace.nodes.get(node_id)
    if node is None:
        return (0.0, 0.0)
    return (float(node.y), float(node.x))


def _build_boundary_edge(
    *,
    edge: EdgeInstance,
    pin_type_id: str,
    registry,
    workspace,
    inner_node_id: str,
    inner_port_key: str,
) -> _BoundaryEdge:
    label, kind, data_type, accepted_data_types, data_access = _pin_signature_for_inner_port(
        registry=registry,
        workspace=workspace,
        node_id=inner_node_id,
        port_key=inner_port_key,
    )
    return _BoundaryEdge(
        edge=edge,
        pin_type_id=pin_type_id,
        label=label,
        kind=kind,
        data_type=data_type,
        accepted_data_types=accepted_data_types,
        data_access=data_access,
    )


def _pin_signature_for_inner_port(
    *,
    registry,
    workspace,
    node_id: str,
    port_key: str,
) -> tuple[str, str, str, tuple[str, ...], str]:
    default_label = str(port_key).strip() or "Port"
    default_signature = (default_label, "data", GRAPH_DATA_TYPE_ID, (), "item")
    node = workspace.nodes.get(node_id)
    if node is None:
        return default_signature
    try:
        spec = registry.get_spec(node.type_id)
    except KeyError:
        return default_signature

    port = find_port(
        node=node,
        spec=spec,
        workspace_nodes=workspace.nodes,
        port_key=port_key,
    )
    if port is None:
        return default_signature

    label = str(port.label).strip() or default_label
    kind = normalize_subnode_pin_kind(port.kind)
    data_type = normalize_subnode_pin_data_type(kind, port.data_type)
    accepted_data_types = normalize_subnode_pin_accepted_data_types(
        kind,
        data_type,
        port.accepted_data_types,
    )
    data_access = normalize_subnode_pin_data_access(port.data_access)
    return label, kind, data_type, accepted_data_types, data_access


def _create_boundary_pin(
    *,
    mutations: ValidatedGraphMutation,
    shell_node_id: str,
    pin_type_id: str,
    x: float,
    y: float,
    label: str,
    kind: str,
    data_type: str,
    accepted_data_types: tuple[str, ...],
    data_access: str,
) -> str:
    registry = mutations.registry
    pin_spec = registry.get_spec(pin_type_id)
    pin_defaults = registry.default_properties(pin_type_id)
    pin = mutations.add_node(
        type_id=pin_type_id,
        title=pin_spec.display_name,
        x=float(x),
        y=float(y),
        properties=pin_defaults,
        exposed_ports={},
        parent_node_id=shell_node_id,
    )
    normalized_kind = normalize_subnode_pin_kind(kind)
    normalized_data_type = normalize_subnode_pin_data_type(normalized_kind, data_type)
    normalized_accepted_data_types = normalize_subnode_pin_accepted_data_types(
        normalized_kind,
        normalized_data_type,
        accepted_data_types,
    )
    normalized_data_access = normalize_subnode_pin_data_access(data_access)
    mutations.set_node_properties(
        pin.node_id,
        {
            SUBNODE_PIN_LABEL_PROPERTY: str(label).strip() or default_subnode_pin_label(pin_type_id),
            SUBNODE_PIN_KIND_PROPERTY: normalized_kind,
            SUBNODE_PIN_DATA_TYPE_PROPERTY: normalized_data_type,
            SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY: list(
                normalized_accepted_data_types
            ),
            SUBNODE_PIN_DATA_ACCESS_PROPERTY: normalized_data_access,
        },
    )
    mutations.set_exposed_port(shell_node_id, pin.node_id, True)
    return pin.node_id


def _remember_rewired_edge(
    rewired_edges: dict[tuple[str, str, str, str], tuple[bool, int]],
    endpoint: tuple[str, str, str, str],
    *,
    enabled: bool,
    input_order: int,
) -> None:
    previous = rewired_edges.get(endpoint)
    if previous is None:
        rewired_edges[endpoint] = (bool(enabled), max(0, int(input_order)))
        return
    rewired_edges[endpoint] = (
        previous[0] or bool(enabled),
        min(previous[1], max(0, int(input_order))),
    )


def _edge_sort_key(edge: EdgeInstance) -> tuple[str, str, str, str, str]:
    return (
        edge.source_node_id,
        edge.source_port_key,
        edge.target_node_id,
        edge.target_port_key,
        edge.edge_id,
    )


__all__ = [
    "GroupSubnodeResult",
    "UngroupSubnodeResult",
    "group_selection_into_subnode",
    "ungroup_subnode",
]
