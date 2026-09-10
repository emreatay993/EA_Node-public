from __future__ import annotations

from ea_node_editor.graph.effective_ports import (
    EffectivePort,
    effective_ports,
    find_port,
    port_supports_incoming_edge,
    port_supports_outgoing_edge,
    ports_compatible,
)
from ea_node_editor.graph.hierarchy import scope_node_ids


def are_ports_compatible(
    self,
    source_node_id: str,
    source_port: str,
    target_node_id: str,
    target_port: str,
) -> bool:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if registry is None or model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    source_node = self._scene_context.node(source_node_id)
    target_node = self._scene_context.node(target_node_id)
    if source_node is None or target_node is None:
        return False
    source_spec = registry.get_spec(source_node.type_id)
    target_spec = registry.get_spec(target_node.type_id)
    source_port_doc = find_port(
        node=source_node,
        spec=source_spec,
        workspace_nodes=workspace.nodes,
        port_key=source_port,
    )
    target_port_doc = find_port(
        node=target_node,
        spec=target_spec,
        workspace_nodes=workspace.nodes,
        port_key=target_port,
    )
    if source_port_doc is None or target_port_doc is None:
        return False
    return ports_compatible(
        source_port_doc,
        target_port_doc,
        data_types=registry.data_types,
    )


def compatible_endpoint_snapshot(
    self,
    anchor_node_id: str,
    anchor_port_key: str,
    candidate_role: str,
) -> dict[str, object]:
    """Return current compatible endpoints for one drag gesture."""
    model = self._scene_context.model
    registry = self._scene_context.registry
    result: dict[str, object] = {
        "catalog_generation": (
            registry.data_types.fingerprint() if registry is not None else ""
        ),
        "candidate_role": str(candidate_role or "").strip().lower(),
        "compatible_endpoint_ids": [],
    }
    if model is None or registry is None:
        return result
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    role = str(candidate_role or "").strip().lower()
    if workspace is None or role not in {"source", "target"}:
        return result

    ports_by_node: dict[str, tuple[EffectivePort, ...]] = {}
    for node_id in sorted(scope_node_ids(workspace, self._scene_context.scope_path)):
        node = workspace.nodes.get(node_id)
        spec = registry.spec_or_none(node.type_id) if node is not None else None
        if node is None or spec is None:
            continue
        ports_by_node[node_id] = tuple(
            effective_ports(
                node=node,
                spec=spec,
                workspace_nodes=workspace.nodes,
            )
        )
    anchor_port = next(
        (
            port
            for port in ports_by_node.get(str(anchor_node_id), ())
            if str(getattr(port, "key", "")) == str(anchor_port_key)
        ),
        None,
    )
    if anchor_port is None:
        return result
    if role == "target" and not port_supports_outgoing_edge(anchor_port):
        return result
    if role == "source" and not port_supports_incoming_edge(anchor_port):
        return result

    compatible_endpoint_ids: list[dict[str, str]] = []
    for node_id, ports in ports_by_node.items():
        for port in ports:
            port_key = str(getattr(port, "key", ""))
            if node_id == str(anchor_node_id) and port_key == str(anchor_port_key):
                continue
            if not bool(getattr(port, "exposed", False)):
                continue
            if role == "target":
                compatible = port_supports_incoming_edge(port) and ports_compatible(
                    anchor_port,
                    port,
                    data_types=registry.data_types,
                )
            else:
                compatible = port_supports_outgoing_edge(port) and ports_compatible(
                    port,
                    anchor_port,
                    data_types=registry.data_types,
                )
            if compatible:
                compatible_endpoint_ids.append(
                    {"node_id": node_id, "port_key": port_key}
                )
    result["compatible_endpoint_ids"] = compatible_endpoint_ids
    return result


def compatible_rewire_endpoint_snapshot(
    self,
    edge_ids: list[object],
    endpoint: str,
    copy_requested: bool = False,
    append_requested: bool = False,
) -> dict[str, object]:
    """Return the endpoints compatible with every edge in a rewire bundle."""
    model = self._scene_context.model
    registry = self._scene_context.registry
    role = str(endpoint or "").strip().lower()
    result: dict[str, object] = {
        "catalog_generation": (
            registry.data_types.fingerprint() if registry is not None else ""
        ),
        "candidate_role": role,
        "compatible_endpoint_ids": [],
    }
    if model is None or registry is None or role not in {"source", "target"}:
        return result
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return result

    normalized_edge_ids: list[str] = []
    seen_edge_ids: set[str] = set()
    for value in edge_ids:
        edge_id = str(value or "").strip()
        if edge_id and edge_id not in seen_edge_ids:
            seen_edge_ids.add(edge_id)
            normalized_edge_ids.append(edge_id)
    if not normalized_edge_ids or any(
        edge_id not in workspace.edges for edge_id in normalized_edge_ids
    ):
        return result
    edges = [workspace.edges[edge_id] for edge_id in normalized_edge_ids]
    endpoint_pairs = {
        (edge.source_node_id, edge.source_port_key)
        if role == "source"
        else (edge.target_node_id, edge.target_port_key)
        for edge in edges
    }
    if len(endpoint_pairs) != 1:
        return result
    original_endpoint = next(iter(endpoint_pairs))

    ports_by_node: dict[str, tuple[EffectivePort, ...]] = {}
    for node_id in sorted(scope_node_ids(workspace, self._scene_context.scope_path)):
        node = workspace.nodes.get(node_id)
        spec = registry.spec_or_none(node.type_id) if node is not None else None
        if node is None or spec is None:
            continue
        ports_by_node[node_id] = tuple(
            effective_ports(node=node, spec=spec, workspace_nodes=workspace.nodes)
        )

    mutations = model.validated_mutations(
        self._scene_context.workspace_id,
        registry,
    )
    compatible_endpoint_ids: list[dict[str, str]] = []
    for candidate_node_id, ports in ports_by_node.items():
        for candidate in ports:
            candidate_key = str(candidate.key)
            if (candidate_node_id, candidate_key) == original_endpoint:
                continue
            if mutations.can_rewire_edges(
                normalized_edge_ids,
                role,
                candidate_node_id,
                candidate_key,
                copy_requested=bool(copy_requested),
                append_requested=bool(append_requested),
            ):
                compatible_endpoint_ids.append(
                    {"node_id": candidate_node_id, "port_key": candidate_key}
                )
    result["compatible_endpoint_ids"] = compatible_endpoint_ids
    return result


__all__ = [
    "are_ports_compatible",
    "compatible_endpoint_snapshot",
    "compatible_rewire_endpoint_snapshot",
]
