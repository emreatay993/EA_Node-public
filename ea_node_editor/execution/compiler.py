from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Mapping

from ea_node_editor.execution.runtime_dto import RuntimeEdge, RuntimeNode, RuntimeWorkspace
from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.node_specs import NodeTypeSpec

if TYPE_CHECKING:
    from ea_node_editor.graph.invariant_kernel import (
        GraphInvariantKernel,
        RegistryValidationPassMemo,
    )
    from ea_node_editor.graph.records import NodeInstance

def compile_workspace_document(
    workspace_doc: Mapping[str, Any],
    registry: NodeRegistry | None = None,
) -> dict[str, Any]:
    return compile_runtime_workspace(workspace_doc, registry=registry).to_document()


def compile_runtime_workspace(
    workspace_doc: Mapping[str, Any],
    registry: NodeRegistry | None = None,
) -> RuntimeWorkspace:
    return compile_runtime_workspace_snapshot(RuntimeWorkspace.from_mapping(workspace_doc), registry=registry)


def compile_runtime_snapshot(
    runtime_snapshot: RuntimeSnapshot,
    *,
    workspace_id: str,
    registry: NodeRegistry | None = None,
) -> RuntimeWorkspace:
    return compile_runtime_workspace_snapshot(runtime_snapshot.workspace(workspace_id), registry=registry)


def compile_runtime_workspace_snapshot(
    workspace: RuntimeWorkspace,
    registry: NodeRegistry | None = None,
) -> RuntimeWorkspace:
    """Compile nested subnode authoring constructs into a flat execution graph."""
    nodes_by_id, node_order = _normalize_nodes(workspace.nodes)
    workspace_nodes = _materialize_nodes(nodes_by_id)
    validation_kernel, validation_memo = _registry_validation_context(
        registry=registry,
        workspace_nodes=workspace_nodes,
    )
    runtime_edges = _normalize_edges(
        workspace.edges,
        valid_node_ids=set(nodes_by_id),
        workspace_nodes=workspace_nodes,
        registry=registry,
        kernel=validation_kernel,
        memo=validation_memo,
    )

    input_pins_by_shell: dict[str, set[str]] = defaultdict(set)
    output_pin_parent: dict[str, str] = {}

    for node_id, node_doc in nodes_by_id.items():
        type_id = str(node_doc.get("type_id", ""))
        parent_id = _normalize_optional_id(node_doc.get("parent_node_id"))
        if _is_subnode_input_type(type_id) and parent_id and _is_subnode_shell_type(_node_type(nodes_by_id, parent_id)):
            input_pins_by_shell[parent_id].add(node_id)
        elif _is_subnode_output_type(type_id) and parent_id and _is_subnode_shell_type(_node_type(nodes_by_id, parent_id)):
            output_pin_parent[node_id] = parent_id

    compiled_edges = _compile_edges(
        nodes_by_id=nodes_by_id,
        edges=runtime_edges,
        input_pins_by_shell=input_pins_by_shell,
        output_pin_parent=output_pin_parent,
    )

    compiled_nodes: list[RuntimeNode] = []
    real_node_ids: set[str] = set()
    for node_id in node_order:
        node_doc = nodes_by_id[node_id]
        if _is_runtime_excluded(node_doc, registry):
            continue
        runtime_node = RuntimeNode.from_mapping(node_doc)
        if runtime_node is None:
            continue
        compiled_nodes.append(runtime_node)
        real_node_ids.add(node_id)

    flattened_edges = _normalize_edges(
        compiled_edges,
        valid_node_ids=real_node_ids,
        workspace_nodes=workspace_nodes,
        registry=registry,
        kernel=validation_kernel,
        memo=validation_memo,
    )

    return RuntimeWorkspace(
        document_fields=copy.deepcopy(workspace.document_fields),
        nodes=tuple(compiled_nodes),
        edges=tuple(flattened_edges),
    )


def _compile_edges(
    *,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    edges: list[RuntimeEdge],
    input_pins_by_shell: Mapping[str, set[str]],
    output_pin_parent: Mapping[str, str],
) -> list[RuntimeEdge]:
    from ea_node_editor.graph.subnode_contract import SUBNODE_PIN_PORT_KEY

    compiled_edges = list(edges)
    seen_connections = {_edge_connection(edge) for edge in compiled_edges}
    while True:
        outgoing_by_source: dict[tuple[str, str], list[RuntimeEdge]] = defaultdict(list)
        for edge in compiled_edges:
            outgoing_by_source[(edge.source_node_id, edge.source_port_key)].append(edge)
        for outgoing in outgoing_by_source.values():
            outgoing.sort(key=lambda edge: edge.input_order)

        additions: list[RuntimeEdge] = []
        for edge in compiled_edges:
            target_type_id = _node_type(nodes_by_id, edge.target_node_id)
            if _is_subnode_shell_type(target_type_id):
                if edge.target_port_key not in input_pins_by_shell.get(edge.target_node_id, set()):
                    continue
                for next_edge in outgoing_by_source.get(
                    (edge.target_port_key, SUBNODE_PIN_PORT_KEY),
                    [],
                ):
                    additions.append(
                        _flattened_edge(
                            edge,
                            next_edge,
                            input_order=edge.input_order,
                        )
                    )
                continue

            if _is_subnode_output_type(target_type_id) and edge.target_port_key == SUBNODE_PIN_PORT_KEY:
                shell_node_id = output_pin_parent.get(edge.target_node_id, "")
                if not shell_node_id:
                    continue
                for next_edge in outgoing_by_source.get(
                    (shell_node_id, edge.target_node_id),
                    [],
                ):
                    additions.append(
                        _flattened_edge(
                            edge,
                            next_edge,
                            input_order=next_edge.input_order,
                        )
                    )

        new_edges: list[RuntimeEdge] = []
        for addition in additions:
            connection = _edge_connection(addition)
            if connection in seen_connections:
                continue
            seen_connections.add(connection)
            new_edges.append(addition)
        if not new_edges:
            return compiled_edges
        compiled_edges.extend(new_edges)


def _edge_connection(edge: RuntimeEdge) -> tuple[str, str, str, str]:
    return (
        edge.source_node_id,
        edge.source_port_key,
        edge.target_node_id,
        edge.target_port_key,
    )


def _flattened_edge(
    source_edge: RuntimeEdge,
    target_edge: RuntimeEdge,
    *,
    input_order: int,
) -> RuntimeEdge:
    edge_ids = tuple(edge_id for edge_id in (source_edge.edge_id, target_edge.edge_id) if edge_id)
    return RuntimeEdge(
        source_node_id=source_edge.source_node_id,
        source_port_key=source_edge.source_port_key,
        target_node_id=target_edge.target_node_id,
        target_port_key=target_edge.target_port_key,
        edge_id=">".join(edge_ids),
        enabled=source_edge.enabled and target_edge.enabled,
        input_order=input_order,
    )


def _ordered_edges(edges: list[RuntimeEdge]) -> list[RuntimeEdge]:
    return sorted(
        edges,
        key=lambda edge: (
            edge.target_node_id,
            edge.target_port_key,
            edge.input_order,
        ),
    )


def _normalize_nodes(raw_nodes: object) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not isinstance(raw_nodes, (list, tuple)):
        return {}, []

    nodes_by_id: dict[str, dict[str, Any]] = {}
    node_order: list[str] = []
    for raw_node in raw_nodes:
        if not isinstance(raw_node, RuntimeNode):
            continue
        node_id = _normalize_required_id(raw_node.node_id)
        type_id = _normalize_required_id(raw_node.type_id)
        if not node_id or not type_id or node_id in nodes_by_id:
            continue
        node_doc = raw_node.to_document()
        node_doc["node_id"] = node_id
        node_doc["type_id"] = type_id
        node_doc["parent_node_id"] = _normalize_optional_id(raw_node.parent_node_id)
        nodes_by_id[node_id] = node_doc
        node_order.append(node_id)
    return nodes_by_id, node_order


def _materialize_nodes(nodes_by_id: Mapping[str, Mapping[str, Any]]) -> dict[str, NodeInstance]:
    from ea_node_editor.graph.record_payloads import node_instance_from_mapping

    materialized: dict[str, NodeInstance] = {}
    for node_id, node_doc in nodes_by_id.items():
        node = node_instance_from_mapping(node_doc)
        if node is None:
            continue
        materialized[node_id] = node
    return materialized


def _registry_validation_context(
    *,
    registry: NodeRegistry | None,
    workspace_nodes: Mapping[str, NodeInstance],
) -> tuple[GraphInvariantKernel | None, RegistryValidationPassMemo | None]:
    if registry is None:
        return None, None
    from ea_node_editor.graph.invariant_kernel import (
        GraphInvariantKernel,
        RegistryValidationPassMemo,
    )
    validation_nodes = {}
    for node_id, node in workspace_nodes.items():
        try:
            registry.resolve_spec(node.type_id, node.properties)
        except KeyError:
            continue
        except (TypeError, ValueError):
            if node.type_id != "core.python_script":
                raise
            continue
        validation_nodes[node_id] = node

    return (
        GraphInvariantKernel(
            registry=registry,
            workspace_nodes=validation_nodes,
        ),
        RegistryValidationPassMemo(),
    )


def _normalize_edges(
    raw_edges: object,
    *,
    valid_node_ids: set[str],
    workspace_nodes: Mapping[str, NodeInstance],
    registry: NodeRegistry | None,
    kernel: GraphInvariantKernel | None = None,
    memo: RegistryValidationPassMemo | None = None,
) -> list[RuntimeEdge]:
    from ea_node_editor.graph.invariant_kernel import (
        GraphInvariantKernel,
        RegistryValidationPassMemo,
    )

    if not isinstance(raw_edges, (list, tuple)):
        return []

    edges: list[RuntimeEdge] = []
    seen_connections: set[tuple[str, str, str, str]] = set()
    occupied_single_target_ports: set[tuple[str, str]] = set()
    if registry is not None and kernel is None:
        kernel = GraphInvariantKernel(
            registry=registry,
            workspace_nodes=dict(workspace_nodes),
        )
    if kernel is not None and memo is None:
        memo = RegistryValidationPassMemo()
    if kernel is not None:
        candidates = tuple(edge for edge in raw_edges if isinstance(edge, RuntimeEdge)
                           and edge.source_node_id in valid_node_ids
                           and edge.target_node_id in valid_node_ids)
        # Runtime DTO edge IDs are optional; use unique pass-local IDs for pruning.
        kernel.workspace_edges = tuple(replace(edge, edge_id=str(index))
                                       for index, edge in enumerate(candidates))
        memo.invalidate_edges()
        pruned_ids = set(kernel.prunable_edge_ids(memo=memo))
        raw_edges = tuple(edge for index, edge in enumerate(candidates) if str(index) not in pruned_ids)
        kernel.workspace_edges = raw_edges
        memo.invalidate_edges()
    resolved_nodes = kernel.resolve_registry_nodes(memo=memo) if kernel is not None else {}
    spec_cache: dict[str, NodeTypeSpec | None] = {}
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, RuntimeEdge):
            continue
        source_node_id = _normalize_required_id(raw_edge.source_node_id)
        source_port_key = _normalize_required_id(raw_edge.source_port_key)
        target_node_id = _normalize_required_id(raw_edge.target_node_id)
        target_port_key = _normalize_required_id(raw_edge.target_port_key)
        if (
            not source_node_id
            or not source_port_key
            or not target_node_id
            or not target_port_key
            or source_node_id not in valid_node_ids
            or target_node_id not in valid_node_ids
        ):
            continue
        connection = (
            source_node_id,
            source_port_key,
            target_node_id,
            target_port_key,
        )

        resolution = None
        if kernel is not None:
            if source_node_id not in resolved_nodes or target_node_id not in resolved_nodes:
                continue
            resolution = kernel.validate_registry_edge(
                source_node_id=source_node_id,
                source_port_key=source_port_key,
                target_node_id=target_node_id,
                target_port_key=target_port_key,
                resolved_nodes=resolved_nodes,
                memo=memo,
                require_source_output=True,
                require_target_input=True,
                require_exposed_ports=True,
                require_compatible_ports=True,
            )
            if resolution is None:
                continue
            if resolution.source_port.kind == "flow" or resolution.target_port.kind == "flow":
                continue
            if not kernel.accept_registry_edge(
                resolution,
                seen_connections=seen_connections,
                occupied_single_target_ports=occupied_single_target_ports,
            ):
                continue
        elif _edge_is_runtime_excluded(
            source_node_id=source_node_id,
            source_port_key=source_port_key,
            target_node_id=target_node_id,
            target_port_key=target_port_key,
            workspace_nodes=workspace_nodes,
            registry=registry,
            spec_cache=spec_cache,
        ):
            continue
        elif connection in seen_connections:
            continue
        else:
            seen_connections.add(connection)

        edges.append(
            RuntimeEdge(
                source_node_id=source_node_id,
                source_port_key=source_port_key,
                target_node_id=target_node_id,
                target_port_key=target_port_key,
                edge_id=raw_edge.edge_id,
                enabled=raw_edge.enabled,
                input_order=raw_edge.input_order,
                label=raw_edge.label,
                visual_style=copy.deepcopy(raw_edge.visual_style),
                extra_fields=copy.deepcopy(raw_edge.extra_fields),
            )
        )
    return _ordered_edges(edges)


def _edge_is_runtime_excluded(
    *,
    source_node_id: str,
    source_port_key: str,
    target_node_id: str,
    target_port_key: str,
    workspace_nodes: Mapping[str, NodeInstance],
    registry: NodeRegistry | None,
    spec_cache: dict[str, NodeTypeSpec | None],
) -> bool:
    source_port = _resolve_port(
        node_id=source_node_id,
        port_key=source_port_key,
        workspace_nodes=workspace_nodes,
        registry=registry,
        spec_cache=spec_cache,
    )
    if source_port is not None and source_port.kind == "flow":
        return True
    target_port = _resolve_port(
        node_id=target_node_id,
        port_key=target_port_key,
        workspace_nodes=workspace_nodes,
        registry=registry,
        spec_cache=spec_cache,
    )
    return target_port is not None and target_port.kind == "flow"


def _resolve_port(
    *,
    node_id: str,
    port_key: str,
    workspace_nodes: Mapping[str, NodeInstance],
    registry: NodeRegistry | None,
    spec_cache: dict[str, NodeTypeSpec | None],
):
    from ea_node_editor.graph.effective_ports import find_port

    node = workspace_nodes.get(node_id)
    if node is None:
        return None
    spec = _node_spec(node.type_id, registry=registry, spec_cache=spec_cache)
    if spec is None:
        return None
    return find_port(node=node, spec=spec, workspace_nodes=workspace_nodes, port_key=port_key)


def _is_runtime_excluded(node_doc: Mapping[str, Any], registry: NodeRegistry | None) -> bool:
    return _node_runtime_behavior(node_doc, registry) in {"compile_only", "passive"}


def _node_runtime_behavior(node_doc: Mapping[str, Any], registry: NodeRegistry | None) -> str:
    type_id = str(node_doc.get("type_id", ""))
    spec = _node_spec(type_id, registry=registry, spec_cache={})
    if spec is not None:
        return str(spec.runtime_behavior)
    if _is_subnode_authoring_type(type_id):
        return "compile_only"
    return "active"


def _node_spec(
    type_id: str,
    *,
    registry: NodeRegistry | None,
    spec_cache: dict[str, NodeTypeSpec | None],
) -> NodeTypeSpec | None:
    if registry is None:
        return None
    if type_id not in spec_cache:
        try:
            spec_cache[type_id] = registry.get_spec(type_id)
        except KeyError:
            spec_cache[type_id] = None
    return spec_cache[type_id]


def _node_type(nodes_by_id: Mapping[str, Mapping[str, Any]], node_id: str) -> str:
    node_doc = nodes_by_id.get(node_id)
    if node_doc is None:
        return ""
    return str(node_doc.get("type_id", ""))


def _normalize_required_id(value: object) -> str:
    return str(value or "").strip()


def _normalize_optional_id(value: object) -> str | None:
    normalized = _normalize_required_id(value)
    if not normalized:
        return None
    return normalized


def _is_subnode_authoring_type(type_id: str) -> bool:
    from ea_node_editor.graph.subnode_contract import is_subnode_authoring_type

    return is_subnode_authoring_type(type_id)


def _is_subnode_input_type(type_id: str) -> bool:
    from ea_node_editor.graph.subnode_contract import is_subnode_input_type

    return is_subnode_input_type(type_id)


def _is_subnode_output_type(type_id: str) -> bool:
    from ea_node_editor.graph.subnode_contract import is_subnode_output_type

    return is_subnode_output_type(type_id)


def _is_subnode_shell_type(type_id: str) -> bool:
    from ea_node_editor.graph.subnode_contract import is_subnode_shell_type

    return is_subnode_shell_type(type_id)


__all__ = [
    "compile_runtime_snapshot",
    "compile_runtime_workspace",
    "compile_runtime_workspace_snapshot",
    "compile_workspace_document",
]
