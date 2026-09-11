# Purpose: Infer topology-derived output types independently of declared runtime port contracts.
# Map: subsystems/graph_domain.md
# Tests: tests/test_type_forwarding.py

from __future__ import annotations

from collections import ChainMap, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from ea_node_editor.graph.effective_ports import EffectivePort, effective_ports, port_compatibility
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.graph.subnode_contract import (
    SUBNODE_PIN_PORT_KEY,
    is_subnode_input_type,
    is_subnode_shell_type,
)
from ea_node_editor.nodes.node_specs import PortSpec
from ea_node_editor.runtime_contracts import DataTypeCatalog, DataTypeCompatibility, GRAPH_DATA_TYPE_ID

if TYPE_CHECKING:
    from ea_node_editor.nodes.registry import NodeRegistry

PortEndpoint = tuple[str, str]


@dataclass(frozen=True, slots=True)
class ResolvedSourceContract:
    """Possible source types, never an input's accepted alternatives or runtime schema."""

    type_ids: tuple[str, ...]
    has_unresolved_sources: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "type_ids", tuple(sorted(set(self.type_ids))))

    @property
    def identity(self) -> tuple[tuple[str, ...], bool]:
        return self.type_ids, self.has_unresolved_sources


_UNRESOLVED_SOURCE = ResolvedSourceContract((), has_unresolved_sources=True)
_COMPATIBILITY_ORDER = {
    "assignable": 0,
    "convertible": 1,
    "runtime_check": 2,
    "unresolved": 3,
    "incompatible": 4,
}


@dataclass(frozen=True, slots=True)
class PortTypeCompatibility:
    """All-members result with intact catalog evidence for recommendation ranking."""

    members: tuple[DataTypeCompatibility, ...]

    @property
    def worst_match(self) -> DataTypeCompatibility:
        return max(
            self.members,
            key=lambda member: (
                _COMPATIBILITY_ORDER[member.status],
                member.status == "assignable" and member.reason_code == "declared_parent",
            ),
        )

    @property
    def status(self) -> str:
        return self.worst_match.status

    @property
    def is_compatible(self) -> bool:
        return all(member.is_compatible for member in self.members)


def source_port_compatibility(
    source_port: EffectivePort | PortSpec,
    target_port: EffectivePort | PortSpec,
    *,
    data_types: DataTypeCatalog,
    source_contract: ResolvedSourceContract | None = None,
) -> PortTypeCompatibility:
    """Require every inferred source to satisfy the ordinary target declaration.

    The existing scalar compatibility function remains unchanged. Structural/flow
    checks still use it; data members retain the catalog's exact union-selection
    and direct-conversion semantics. No conversions happen here.
    """
    if source_port.kind != "data" or target_port.kind != "data":
        return PortTypeCompatibility((
            port_compatibility(source_port, target_port, data_types=data_types),
        ))
    contract = source_contract or ResolvedSourceContract((source_port.data_type,))
    members = tuple(
        data_types.compatibility(type_id, target_port.data_type, target_port.accepted_data_types)
        for type_id in contract.type_ids
    )
    if contract.has_unresolved_sources or not members:
        members += (DataTypeCompatibility(
            status="unresolved",
            source_type_id="",
            target_type_id=target_port.data_type,
            reason_code="unknown_source",
        ),)
    return PortTypeCompatibility(members)


class GraphTypeResolver:
    """One immutable declaration/topology snapshot, reusable across all consumers.

    Construct again after a graph or registry edit. Optional effective ports let
    an existing validation/projection pass share its resolved declarations. The
    resolver neither executes node source nor reads previously published values.
    """

    def __init__(
        self,
        *,
        registry: NodeRegistry,
        workspace_nodes: Mapping[str, NodeInstance],
        workspace_edges: Iterable[EdgeInstance],
        ports_by_node_id: Mapping[str, tuple[EffectivePort, ...]] | None = None,
    ) -> None:
        self._data_types = registry.data_types
        supplied_ports = ports_by_node_id or {}
        self._ports_by_node_id: dict[str, tuple[EffectivePort, ...]] = {}
        for node_id, node in workspace_nodes.items():
            if node_id in supplied_ports:
                ports = tuple(supplied_ports[node_id])
            elif registry.spec_or_none(node.type_id) is not None:
                ports = effective_ports(
                    node=node,
                    spec=registry.resolve_spec(node.type_id, node.properties),
                    workspace_nodes=workspace_nodes,
                )
            else:
                ports = ()
            self._ports_by_node_id[node_id] = ports
        self._ports = {
            (node_id, port.key): port
            for node_id, ports in self._ports_by_node_id.items()
            for port in ports
        }
        incoming: dict[PortEndpoint, set[PortEndpoint]] = {}
        for edge in workspace_edges:
            if edge.enabled:
                incoming.setdefault((edge.target_node_id, edge.target_port_key), set()).add(
                    (edge.source_node_id, edge.source_port_key)
                )

        self._incoming: Mapping[PortEndpoint, frozenset[PortEndpoint]] = {
            endpoint: frozenset(sources) for endpoint, sources in incoming.items()
        }
        self._input_by_output: dict[PortEndpoint, PortEndpoint | None] = {}
        for endpoint, port in self._ports.items():
            if port.direction != "out" or port.kind != "data":
                continue
            node = workspace_nodes[endpoint[0]]
            input_endpoint = None
            if port.type_from_input:
                input_endpoint = (node.node_id, port.type_from_input)
            elif port.data_type == GRAPH_DATA_TYPE_ID:
                if is_subnode_shell_type(node.type_id):
                    input_endpoint = (port.key, SUBNODE_PIN_PORT_KEY)
                elif is_subnode_input_type(node.type_id):
                    input_endpoint = (node.parent_node_id or "", node.node_id)
            self._input_by_output[endpoint] = input_endpoint
        dependencies, seeds = {}, {}
        for endpoint in self._input_by_output:
            dependencies[endpoint], seeds[endpoint] = self._dependency_and_seed(endpoint)
        self._source_contracts = self._resolve(dependencies, seeds)
        self._fully_resolved = True

    def with_input_connections(
        self, incoming_sources: Mapping[PortEndpoint, Iterable[PortEndpoint]],
    ) -> GraphTypeResolver:
        """Overlay changed enabled inputs without rebuilding the graph snapshot.

        Declaration and topology indexes are shared. Contracts are resolved on
        demand through the proposed topology, including feedback into the source
        being checked; baseline contracts cannot safely substitute for that walk.
        Each overlay belongs to one immutable connection proposal.
        """
        proposal = object.__new__(GraphTypeResolver)
        proposal._data_types = self._data_types
        proposal._ports_by_node_id = self._ports_by_node_id
        proposal._ports = self._ports
        proposal._input_by_output = self._input_by_output
        proposal._incoming = ChainMap(
            {endpoint: frozenset(sources) for endpoint, sources in incoming_sources.items()},
            self._incoming,
        )
        proposal._source_contracts = {}
        proposal._fully_resolved = False
        return proposal

    def _dependency_and_seed(
        self, endpoint: PortEndpoint,
    ) -> tuple[set[PortEndpoint], ResolvedSourceContract]:
        if endpoint not in self._input_by_output:
            return set(), _UNRESOLVED_SOURCE
        port = self._ports[endpoint]
        input_endpoint = self._input_by_output[endpoint]
        if input_endpoint is None:
            return set(), ResolvedSourceContract((port.data_type,))
        # Missing boundary metadata differs from a real, unconnected Any input.
        if input_endpoint not in self._ports:
            return set(), _UNRESOLVED_SOURCE
        sources = set(self._incoming.get(input_endpoint, ()))
        return sources, ResolvedSourceContract(() if sources else (port.data_type,))

    def _resolve_source(self, endpoint: PortEndpoint) -> None:
        """Resolve only this source's ancestor closure, once per proposal."""
        dependencies, seeds = {}, {}
        pending = [endpoint]
        while pending:
            current = pending.pop()
            if current in dependencies:
                continue
            if current in self._source_contracts:
                dependencies[current], seeds[current] = set(), self._source_contracts[current]
            else:
                dependencies[current], seeds[current] = self._dependency_and_seed(current)
                pending.extend(dependencies[current])
        for source, contract in self._resolve(dependencies, seeds).items():
            self._source_contracts.setdefault(source, contract)

    @staticmethod
    def _resolve(
        dependencies: dict[PortEndpoint, set[PortEndpoint]],
        seeds: dict[PortEndpoint, ResolvedSourceContract],
    ) -> dict[PortEndpoint, ResolvedSourceContract]:
        """Iterative propagation supports long chains and conservative cyclic inputs."""
        for sources in tuple(dependencies.values()):
            for source in sources:
                if source not in dependencies:
                    dependencies[source] = set()
                    seeds[source] = _UNRESOLVED_SOURCE
        consumers: dict[PortEndpoint, set[PortEndpoint]] = {key: set() for key in dependencies}
        remaining = {key: len(sources) for key, sources in dependencies.items()}
        for target, sources in dependencies.items():
            for source in sources:
                consumers[source].add(target)
        ready = deque(key for key, count in remaining.items() if count == 0)
        while ready:
            source = ready.popleft()
            for target in consumers[source]:
                remaining[target] -= 1
                if remaining[target] == 0:
                    ready.append(target)

        type_sets = {key: set(contract.type_ids) for key, contract in seeds.items()}
        unresolved = {key: contract.has_unresolved_sources for key, contract in seeds.items()}
        # Kahn's remainder includes cycles and their consumers. Any keeps them
        # conservative even when an external concrete source enters a cycle.
        for key, count in remaining.items():
            if count:
                type_sets[key].add(GRAPH_DATA_TYPE_ID)
        pending = deque(dependencies)
        queued = set(dependencies)
        while pending:
            source = pending.popleft()
            queued.remove(source)
            for target in consumers[source]:
                old_size = len(type_sets[target])
                was_unresolved = unresolved[target]
                type_sets[target].update(type_sets[source])
                unresolved[target] |= unresolved[source]
                if (len(type_sets[target]) != old_size or unresolved[target] != was_unresolved) and target not in queued:
                    pending.append(target)
                    queued.add(target)
        return {
            key: ResolvedSourceContract(tuple(type_sets[key]), unresolved[key])
            for key in dependencies
        }

    def ports_for_node(self, node_id: str) -> tuple[EffectivePort, ...]:
        return self._ports_by_node_id.get(node_id, ())

    @property
    def source_contracts(self) -> Mapping[PortEndpoint, ResolvedSourceContract]:
        """Immutable output facts for snapshot comparison and downstream refresh."""
        if not self._fully_resolved:
            for endpoint in self._input_by_output:
                if endpoint not in self._source_contracts:
                    self._resolve_source(endpoint)
            self._fully_resolved = True
        return MappingProxyType(self._source_contracts)

    def port(self, node_id: str, port_key: str) -> EffectivePort | None:
        return self._ports.get((node_id, port_key))

    def source_contract(self, node_id: str, port_key: str) -> ResolvedSourceContract:
        endpoint = (node_id, port_key)
        if endpoint in self._input_by_output and endpoint not in self._source_contracts:
            self._resolve_source(endpoint)
        if endpoint in self._source_contracts:
            return self._source_contracts[endpoint]
        port = self._ports.get(endpoint)
        return ResolvedSourceContract((port.data_type,)) if port is not None else _UNRESOLVED_SOURCE

    def compatibility(
        self, source_node_id: str, source_port_key: str, target_port: EffectivePort | PortSpec,
    ) -> PortTypeCompatibility:
        source = self.port(source_node_id, source_port_key)
        if source is None:
            return PortTypeCompatibility((DataTypeCompatibility(
                status="unresolved", source_type_id="", target_type_id=target_port.data_type,
                reason_code="unknown_source",
            ),))
        return source_port_compatibility(
            source, target_port, data_types=self._data_types,
            source_contract=self.source_contract(source_node_id, source_port_key),
        )


__all__ = ["GraphTypeResolver", "PortTypeCompatibility", "ResolvedSourceContract", "source_port_compatibility"]
