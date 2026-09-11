from __future__ import annotations

from dataclasses import dataclass, field

from ea_node_editor.graph.effective_ports import (
    EffectivePort,
    effective_ports,
    find_port,
    is_flow_edge_port,
    port_supports_incoming_edge,
    port_supports_outgoing_edge,
    target_port_has_capacity,
)
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.graph.type_forwarding import GraphTypeResolver
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.node_specs import NodeTypeSpec

@dataclass(slots=True, frozen=True)
class RegistryNodeResolution:
    node: NodeInstance
    spec: NodeTypeSpec


@dataclass(slots=True)
class RegistryValidationPassMemo:
    resolved_nodes: dict[str, RegistryNodeResolution] | None = None
    workspace_node_view: dict[str, NodeInstance] | None = None
    effective_ports_by_node_id: dict[str, tuple[EffectivePort, ...]] = field(default_factory=dict)
    port_by_node_and_key: dict[tuple[str, str], EffectivePort | None] = field(default_factory=dict)
    workspace_edge_values: tuple[EdgeInstance, ...] | None = None
    type_resolver: GraphTypeResolver | None = None

    def invalidate_edges(self) -> None:
        self.workspace_edge_values = None
        self.type_resolver = None


@dataclass(slots=True)
class GraphInvariantKernel:
    registry: NodeRegistry
    workspace_nodes: dict[str, NodeInstance]
    workspace_edges: object | None = None

    def type_resolver(self, *, memo: RegistryValidationPassMemo | None = None) -> GraphTypeResolver:
        memo = memo or RegistryValidationPassMemo()
        if memo.type_resolver is None:
            resolved = self.resolve_registry_nodes(memo=memo)
            nodes = self._workspace_node_view(resolved, memo=memo)
            ports = {
                node_id: self._effective_ports_for(resolution, workspace_nodes=nodes, memo=memo)
                for node_id, resolution in resolved.items()
            }
            memo.type_resolver = GraphTypeResolver(
                registry=self.registry, workspace_nodes=nodes,
                workspace_edges=self._workspace_edge_values(memo=memo), ports_by_node_id=ports,
            )
        return memo.type_resolver

    def _workspace_edge_values(
        self,
        *,
        memo: RegistryValidationPassMemo | None = None,
    ) -> tuple[EdgeInstance, ...]:
        if memo is None:
            if self.workspace_edges is None:
                return ()
            return tuple(self.workspace_edges)
        if memo.workspace_edge_values is None:
            memo.workspace_edge_values = () if self.workspace_edges is None else tuple(self.workspace_edges)
        return memo.workspace_edge_values

    @staticmethod
    def _workspace_node_view(
        resolved_nodes: dict[str, RegistryNodeResolution],
        *,
        memo: RegistryValidationPassMemo | None = None,
    ) -> dict[str, NodeInstance]:
        if memo is None:
            return {node_id: resolution.node for node_id, resolution in resolved_nodes.items()}
        if memo.workspace_node_view is None:
            memo.workspace_node_view = {
                node_id: resolution.node
                for node_id, resolution in resolved_nodes.items()
            }
        return memo.workspace_node_view

    def _effective_ports_for(
        self,
        resolution: RegistryNodeResolution,
        *,
        workspace_nodes: dict[str, NodeInstance],
        memo: RegistryValidationPassMemo | None = None,
    ) -> tuple[EffectivePort, ...]:
        node_id = str(resolution.node.node_id)
        if memo is not None and node_id in memo.effective_ports_by_node_id:
            return memo.effective_ports_by_node_id[node_id]
        ports = effective_ports(
            node=resolution.node,
            spec=resolution.spec,
            workspace_nodes=workspace_nodes,
        )
        if memo is not None:
            memo.effective_ports_by_node_id[node_id] = ports
        return ports

    def _find_port(
        self,
        resolution: RegistryNodeResolution,
        port_key: str,
        *,
        workspace_nodes: dict[str, NodeInstance],
        memo: RegistryValidationPassMemo | None = None,
    ) -> EffectivePort | None:
        node_id = str(resolution.node.node_id)
        normalized_port_key = str(port_key)
        cache_key = (node_id, normalized_port_key)
        if memo is not None and cache_key in memo.port_by_node_and_key:
            return memo.port_by_node_and_key[cache_key]
        for port in self._effective_ports_for(resolution, workspace_nodes=workspace_nodes, memo=memo):
            if port.key == normalized_port_key:
                if memo is not None:
                    memo.port_by_node_and_key[cache_key] = port
                return port
        if memo is not None:
            memo.port_by_node_and_key[cache_key] = None
        return None

    def resolve_registry_nodes(
        self,
        *,
        memo: RegistryValidationPassMemo | None = None,
    ) -> dict[str, RegistryNodeResolution]:
        if memo is not None and memo.resolved_nodes is not None:
            return memo.resolved_nodes
        resolved: dict[str, RegistryNodeResolution] = {}
        for node_id, node in self.workspace_nodes.items():
            if self.registry.spec_or_none(node.type_id) is None:
                continue
            spec = self.registry.resolve_spec(node.type_id, node.properties)
            resolved[node_id] = RegistryNodeResolution(node=node, spec=spec)
        if memo is not None:
            memo.resolved_nodes = resolved
        return resolved

    def normalized_exposed_ports(
        self,
        resolution: RegistryNodeResolution,
        *,
        memo: RegistryValidationPassMemo | None = None,
    ) -> dict[str, bool]:
        return {
            port.key: bool(port.required or resolution.node.exposed_ports.get(port.key, port.exposed))
            for port in self._effective_ports_for(
                resolution,
                workspace_nodes=self.workspace_nodes,
                memo=memo,
            )
        }

    def validate_registry_edge(
        self,
        *,
        source_node_id: str,
        source_port_key: str,
        target_node_id: str,
        target_port_key: str,
        resolved_nodes: dict[str, RegistryNodeResolution] | None = None,
        memo: RegistryValidationPassMemo | None = None,
        require_source_output: bool,
        require_target_input: bool = True,
        require_exposed_ports: bool = False,
        require_compatible_ports: bool = False,
    ) -> RegistryEdgeResolution | None:
        if resolved_nodes is None:
            resolved_nodes = self.resolve_registry_nodes(memo=memo)
        source_resolution = resolved_nodes.get(source_node_id)
        target_resolution = resolved_nodes.get(target_node_id)
        if source_resolution is None or target_resolution is None:
            return None
        workspace_nodes = self._workspace_node_view(resolved_nodes, memo=memo)
        source_port = self._find_port(
            source_resolution,
            source_port_key,
            workspace_nodes=workspace_nodes,
            memo=memo,
        )
        if source_port is None:
            return None
        target_port = self._find_port(
            target_resolution,
            target_port_key,
            workspace_nodes=workspace_nodes,
            memo=memo,
        )
        if target_port is None:
            return None
        if require_source_output and not port_supports_outgoing_edge(source_port):
            return None
        if require_target_input and not port_supports_incoming_edge(target_port):
            return None
        if require_exposed_ports and (not source_port.exposed or not target_port.exposed):
            return None
        if require_compatible_ports:
            compatibility = self.type_resolver(memo=memo).compatibility(
                source_node_id, source_port_key, target_port,
            )
            if not compatibility.is_compatible:
                return None
        return RegistryEdgeResolution(
            source_node_id=source_node_id,
            source_port_key=source_port_key,
            target_node_id=target_node_id,
            target_port_key=target_port_key,
            source_port=source_port,
            target_port=target_port,
        )

    def add_edge_or_raise(
        self,
        *,
        source_node_id: str,
        source_port_key: str,
        target_node_id: str,
        target_port_key: str,
        append_requested: bool = False,
        memo: RegistryValidationPassMemo | None = None,
        capacity_excluded_edge_id: str = "",
    ) -> RegistryEdgeResolution:
        if source_node_id not in self.workspace_nodes:
            raise KeyError(f"Unknown source node: {source_node_id}")
        if target_node_id not in self.workspace_nodes:
            raise KeyError(f"Unknown target node: {target_node_id}")
        memo = memo or RegistryValidationPassMemo()
        resolved = self.resolve_registry_nodes(memo=memo)
        source_resolution = resolved.get(source_node_id)
        target_resolution = resolved.get(target_node_id)
        if source_resolution is None or target_resolution is None:
            raise KeyError("Unknown node type in connection")
        source_port = self._find_port(source_resolution, source_port_key, workspace_nodes=self.workspace_nodes, memo=memo)
        target_port = self._find_port(target_resolution, target_port_key, workspace_nodes=self.workspace_nodes, memo=memo)
        if source_port is None or target_port is None:
            raise KeyError("Port not found in connection")
        target_node, target_spec = target_resolution.node, target_resolution.spec
        if source_node_id == target_node_id and is_flow_edge_port(source_port) and is_flow_edge_port(target_port):
            raise ValueError("Flow edges cannot connect ports on the same node.")
        if not port_supports_outgoing_edge(source_port):
            raise ValueError(f"Source port must support outgoing edges: {source_node_id}.{source_port_key}")
        if not port_supports_incoming_edge(target_port):
            raise ValueError(f"Target port must support incoming edges: {target_node_id}.{target_port_key}")
        compatibility = self.type_resolver(memo=memo).compatibility(
            source_node_id, source_port_key, target_port,
        )
        if compatibility.worst_match.reason_code == "port_kind_mismatch":
            raise ValueError(
                "Incompatible ports: "
                f"{source_node_id}.{source_port_key} -> {target_node_id}.{target_port_key}"
            )
        if not compatibility.is_compatible:
            raise ValueError(
                "Incompatible data types: "
                f"{source_node_id}.{source_port_key} ({source_port.data_type}) -> "
                f"{target_node_id}.{target_port_key} ({target_port.data_type}); "
                f"{compatibility.status}:{compatibility.worst_match.reason_code}"
            )
        if not source_port.exposed:
            raise ValueError(f"Source port is hidden: {source_node_id}.{source_port_key}")
        if not target_port.exposed:
            raise ValueError(f"Target port is hidden: {target_node_id}.{target_port_key}")
        if append_requested and str(target_port.kind) == "flow":
            if not target_port_has_capacity(
                edges=tuple(edge for edge in self._workspace_edge_values(memo=memo)
                            if edge.edge_id != capacity_excluded_edge_id),
                node=target_node,
                spec=target_spec,
                workspace_nodes=self.workspace_nodes,
                port_key=target_port_key,
            ):
                raise ValueError(f"Target input port already has a connection: {target_node_id}.{target_port_key}")
        return RegistryEdgeResolution(
            source_node_id=source_node_id,
            source_port_key=source_port_key,
            target_node_id=target_node_id,
            target_port_key=target_port_key,
            source_port=source_port,
            target_port=target_port,
        )

    def _resolved_port(self, node_id: str, port_key: str) -> tuple[NodeInstance, NodeTypeSpec, EffectivePort]:
        node = self.workspace_nodes[node_id]
        spec = self.registry.resolve_spec(node.type_id, node.properties)
        port = find_port(
            node=node,
            spec=spec,
            workspace_nodes=self.workspace_nodes,
            port_key=port_key,
        )
        if port is None:
            raise KeyError(f"Port {port_key} not found on node type {spec.type_id}")
        return node, spec, port

    def prunable_edge_ids(
        self, *, affected_node_ids: set[str] | None = None,
        forced_port_keys: dict[str, set[str]] | None = None,
        memo: RegistryValidationPassMemo | None = None,
    ) -> list[str]:
        """Validate a proposed topology, removing invalid wires in snapshot batches.

        Structural failures are removed before inference, so a removed dynamic
        port cannot poison an otherwise valid forwarding chain. Each semantic
        pass shares one resolver; subsequent passes see the pruned topology.
        """
        memo = memo or RegistryValidationPassMemo()
        forced_port_keys = forced_port_keys or {}
        original_edges = self.workspace_edges
        active = list(self._workspace_edge_values(memo=memo))
        affected = None if affected_node_ids is None else self.downstream_nodes(affected_node_ids)
        removed: list[str] = []
        try:
            semantic_pass = False
            while True:
                seen: set[tuple[str, str, str, str]] = set()
                occupied: set[tuple[str, str]] = set()
                rejected: list[str] = []
                for edge in active:
                    touches = affected is None or edge.source_node_id in affected or edge.target_node_id in affected
                    forced = (edge.source_port_key in forced_port_keys.get(edge.source_node_id, set())
                              or edge.target_port_key in forced_port_keys.get(edge.target_node_id, set()))
                    resolution = None if forced else self.validate_registry_edge(
                        source_node_id=edge.source_node_id, source_port_key=edge.source_port_key,
                        target_node_id=edge.target_node_id, target_port_key=edge.target_port_key,
                        memo=memo, require_source_output=True, require_exposed_ports=True,
                        require_compatible_ports=semantic_pass,
                    )
                    valid = resolution is not None and self.accept_registry_edge(
                        resolution, seen_connections=seen, occupied_single_target_ports=occupied,
                    )
                    if touches and not valid:
                        rejected.append(edge.edge_id)
                if rejected:
                    removed.extend(rejected)
                    rejected_set = set(rejected)
                    active = [edge for edge in active if edge.edge_id not in rejected_set]
                    self.workspace_edges = active
                    memo.invalidate_edges()
                elif semantic_pass:
                    break
                semantic_pass = True
            return removed
        finally:
            self.workspace_edges = original_edges
            memo.invalidate_edges()

    def downstream_nodes(self, roots: set[str]) -> set[str]:
        """Include boundary counterparts when following potentially affected contracts."""
        outgoing: dict[str, set[str]] = {}
        for edge in self._workspace_edge_values():
            outgoing.setdefault(edge.source_node_id, set()).add(edge.target_node_id)
        from ea_node_editor.graph.subnode_contract import is_subnode_pin_type
        for node in self.workspace_nodes.values():
            if node.parent_node_id and is_subnode_pin_type(node.type_id):
                outgoing.setdefault(node.node_id, set()).add(node.parent_node_id)
                outgoing.setdefault(node.parent_node_id, set()).add(node.node_id)
        result = set(roots)
        pending = list(roots)
        while pending:
            for node_id in outgoing.get(pending.pop(), ()):
                if node_id not in result:
                    result.add(node_id)
                    pending.append(node_id)
        return result

    @staticmethod
    def accept_registry_edge(
        edge: RegistryEdgeResolution,
        *,
        seen_connections: set[tuple[str, str, str, str]],
        occupied_single_target_ports: set[tuple[str, str]],
    ) -> bool:
        if edge.connection_key in seen_connections:
            return False
        if (
            str(edge.target_port.kind) == "flow"
            and not edge.target_port.allow_multiple_connections
            and edge.target_input_key in occupied_single_target_ports
        ):
            return False
        seen_connections.add(edge.connection_key)
        if str(edge.target_port.kind) == "flow" and not edge.target_port.allow_multiple_connections:
            occupied_single_target_ports.add(edge.target_input_key)
        return True


@dataclass(slots=True, frozen=True)
class RegistryEdgeResolution:
    source_node_id: str
    source_port_key: str
    target_node_id: str
    target_port_key: str
    source_port: EffectivePort
    target_port: EffectivePort

    @property
    def connection_key(self) -> tuple[str, str, str, str]:
        return (
            self.source_node_id,
            self.source_port_key,
            self.target_node_id,
            self.target_port_key,
        )

    @property
    def target_input_key(self) -> tuple[str, str]:
        return (
            self.target_node_id,
            self.target_port_key,
        )


__all__ = [
    "GraphInvariantKernel",
    "RegistryEdgeResolution",
    "RegistryNodeResolution",
    "RegistryValidationPassMemo",
]
