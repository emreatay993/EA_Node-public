from __future__ import annotations

from ea_node_editor.graph.effective_ports import (
    port_supports_incoming_edge,
    port_supports_outgoing_edge,
)
from ea_node_editor.graph.hierarchy import scope_node_ids
from ea_node_editor.graph.type_forwarding import GraphTypeResolver


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
    resolver = GraphTypeResolver(registry=registry, workspace_nodes=workspace.nodes, workspace_edges=workspace.edges.values())
    source = resolver.port(source_node_id, source_port)
    target = resolver.port(target_node_id, target_port)
    if source is None or target is None or not source.exposed or not target.exposed:
        return False
    return resolver.compatibility(source_node_id, source_port, target).is_compatible



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

    resolver = GraphTypeResolver(registry=registry, workspace_nodes=workspace.nodes, workspace_edges=workspace.edges.values())
    ports_by_node = {node_id: resolver.ports_for_node(node_id)
                     for node_id in sorted(scope_node_ids(workspace, self._scene_context.scope_path))}
    anchor_port = next(
        (
            port
            for port in ports_by_node.get(str(anchor_node_id), ())
            if str(getattr(port, "key", "")) == str(anchor_port_key)
        ),
        None,
    )
    if anchor_port is None or not anchor_port.exposed:
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
                compatible = port_supports_incoming_edge(port) and resolver.compatibility(anchor_node_id, anchor_port_key, port).is_compatible
            else:
                compatible = port_supports_outgoing_edge(port) and resolver.compatibility(node_id, port.key, anchor_port).is_compatible
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

    mutations = model.validated_mutations(self._scene_context.workspace_id, registry)
    prepared = mutations.prepare_rewire_edges(
        edge_ids, role, copy_requested=bool(copy_requested), append_requested=bool(append_requested),
    )
    if not prepared.requested_edges:
        return result
    original_endpoint = prepared.original_endpoint

    resolver = prepared.resolver
    ports_by_node = {node_id: resolver.ports_for_node(node_id)
                     for node_id in sorted(scope_node_ids(workspace, self._scene_context.scope_path))}
    anchor = resolver.port(*original_endpoint)
    if original_endpoint[0] not in ports_by_node or anchor is None or not anchor.exposed:
        return result

    compatible_endpoint_ids: list[dict[str, str]] = []
    for candidate_node_id, ports in ports_by_node.items():
        for candidate in ports:
            candidate_key = str(candidate.key)
            if not candidate.exposed or (candidate_node_id, candidate_key) == original_endpoint:
                continue
            if prepared.can_rewire(candidate_node_id, candidate_key):
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
