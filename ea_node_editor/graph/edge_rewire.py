# Purpose: Prepare shared graph snapshots and validate atomic edge endpoint proposals.
# Map: subsystems/graph_domain.md
# Tests: tests/test_rewire_validation.py, tests/test_type_forwarding_integration.py

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from ea_node_editor.graph.invariant_kernel import GraphInvariantKernel, RegistryValidationPassMemo
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.nodes.registry import NodeRegistry


def _connection_key(edge: EdgeInstance) -> tuple[str, str, str, str]:
    return (edge.source_node_id, edge.source_port_key, edge.target_node_id, edge.target_port_key)


def _target_key(edge: EdgeInstance) -> tuple[str, str]:
    return edge.target_node_id, edge.target_port_key


@dataclass(frozen=True, slots=True)
class EdgeRewireProposal:
    candidates: tuple[EdgeInstance, ...] = ()
    replaced_edge_ids: frozenset[str] = frozenset()


class PreparedEdgeRewire:
    """One read-only rewire request, reusable for every candidate in a gesture.

    Prepare declarations and base edge indexes once. Each candidate only changes
    the incident input lists and resolves its source dependency closures. Both
    preview and final mutation use this gate; mutation always prepares anew.
    """

    def __init__(
        self, *, registry: NodeRegistry, workspace_nodes: Mapping[str, NodeInstance],
        workspace_edges: Iterable[EdgeInstance], edge_ids: Iterable[object], endpoint: str,
        copy_requested: bool = False, append_requested: bool = False,
    ) -> None:
        self.endpoint = str(endpoint or "").strip().lower()
        if self.endpoint not in {"source", "target"}:
            raise ValueError("Edge endpoint must be 'source' or 'target'.")
        self.copy_requested = bool(copy_requested)
        self.append_requested = bool(append_requested)
        # These records belong to the preparation, never to the live workspace.
        edges = {edge.edge_id: edge.clone() for edge in workspace_edges}
        normalized_ids = tuple(dict.fromkeys(
            normalized for value in edge_ids if (normalized := str(value or "").strip())
        ))
        requested = tuple(sorted(
            (edges[edge_id] for edge_id in normalized_ids),
            key=lambda edge: (int(edge.input_order), edge.edge_id),
        )) if normalized_ids and all(edge_id in edges for edge_id in normalized_ids) else ()
        endpoints = {
            (edge.source_node_id, edge.source_port_key) if self.endpoint == "source" else _target_key(edge)
            for edge in requested
        }
        self.original_endpoint = next(iter(endpoints)) if len(endpoints) == 1 else None
        self.requested_edges = requested if self.original_endpoint is not None else ()
        if self.copy_requested and len(self.requested_edges) != 1:
            self.requested_edges = ()
        self._requested_ids = frozenset(edge.edge_id for edge in self.requested_edges)
        self._edges_by_target: dict[tuple[str, str], list[EdgeInstance]] = defaultdict(list)
        self._outside_keys = set()
        retained_counts: Counter[tuple[str, str, str, str]] = Counter()
        for edge in edges.values():
            self._edges_by_target[_target_key(edge)].append(edge)
            key = _connection_key(edge)
            if edge.edge_id not in self._requested_ids:
                self._outside_keys.add(key)
            if self.copy_requested or edge.edge_id not in self._requested_ids:
                retained_counts[key] += 1
        self._retained_keys = retained_counts.keys()
        self._duplicate_targets = {key[2:] for key, count in retained_counts.items() if count > 1}
        self._kernel = GraphInvariantKernel(
            registry, {key: node.clone() for key, node in workspace_nodes.items()}, tuple(edges.values()),
        )
        self._memo = RegistryValidationPassMemo()
        self.resolver = self._kernel.type_resolver(memo=self._memo)

    def validate(self, node_id: str, port_key: str) -> EdgeRewireProposal | None:
        """Return a complete valid proposal, or None for a no-op/invalid request.

        Structural/type failures raise the same errors as an ordinary connection;
        the Boolean preview adapter below consumes those errors.
        """
        node_id, port_key = str(node_id or "").strip(), str(port_key or "").strip()
        if bool(node_id) != bool(port_key):
            raise ValueError("Edge endpoint request requires both node_id and port_key.")
        if not self.requested_edges or (self.copy_requested and not node_id):
            return None
        if not node_id:
            return EdgeRewireProposal()
        if not self.copy_requested and (node_id, port_key) == self.original_endpoint:
            return None

        candidates = []
        for index, edge in enumerate(self.requested_edges):
            candidate = edge.clone()
            if self.copy_requested:
                candidate.edge_id = f"__copy_{index}_{edge.edge_id}"
            if self.endpoint == "source":
                candidate.source_node_id, candidate.source_port_key = node_id, port_key
            else:
                candidate.target_node_id, candidate.target_port_key = node_id, port_key
            candidates.append(candidate)
        candidate_keys = tuple(_connection_key(edge) for edge in candidates)
        if len(set(candidate_keys)) != len(candidate_keys) or any(
            key in self._outside_keys for key in candidate_keys
        ):
            return None

        replaced = ()
        replacement_target = None
        if self.endpoint == "target" and not self.copy_requested and not self.append_requested:
            replacement_target = (node_id, port_key)
            replaced = tuple(edge for edge in self._edges_by_target.get(replacement_target, ())
                             if edge.edge_id not in self._requested_ids)
        if self._duplicate_targets - {replacement_target} or any(
            key in self._retained_keys and key[2:] != replacement_target for key in candidate_keys
        ):
            return None

        removed = () if self.copy_requested else self.requested_edges
        removed_ids = {edge.edge_id for edge in (*removed, *replaced)}
        by_target: dict[tuple[str, str], list[EdgeInstance]] = defaultdict(list)
        for candidate in candidates:
            by_target[_target_key(candidate)].append(candidate)
        changed_targets = by_target.keys() | {_target_key(edge) for edge in (*removed, *replaced)}
        incoming = {
            target: [edge for edge in self._edges_by_target.get(target, ()) if edge.edge_id not in removed_ids]
            for target in changed_targets
        }
        if self.endpoint == "target":
            next_order = (
                1 + max((edge.input_order for edge in incoming[(node_id, port_key)]), default=-1)
                if self.append_requested or self.copy_requested else 0
            )
            for offset, candidate in enumerate(candidates):
                candidate.input_order = next_order + offset
        elif self.copy_requested:
            candidate = candidates[0]
            candidate.input_order = 1 + max(
                (edge.input_order for edge in incoming[_target_key(candidate)]), default=-1,
            )
        for target, additions in by_target.items():
            incoming[target].extend(additions)
        resolver = self.resolver.with_input_connections({
            target: ((edge.source_node_id, edge.source_port_key) for edge in edges if edge.enabled)
            for target, edges in incoming.items()
        })
        # The kernel's remaining edge lookup is flow capacity at candidate inputs.
        # All other structure/declaration checks share the prepared immutable view.
        memo = replace(
            self._memo, type_resolver=resolver,
            workspace_edge_values=tuple(edge for target in by_target for edge in incoming[target]),
        )
        for candidate in candidates:
            self._kernel.add_edge_or_raise(
                source_node_id=candidate.source_node_id, source_port_key=candidate.source_port_key,
                target_node_id=candidate.target_node_id, target_port_key=candidate.target_port_key,
                append_requested=True, memo=memo, capacity_excluded_edge_id=candidate.edge_id,
            )
        return EdgeRewireProposal(tuple(candidates), frozenset(edge.edge_id for edge in replaced))

    def can_rewire(self, node_id: str, port_key: str) -> bool:
        try:
            return self.validate(node_id, port_key) is not None
        except (KeyError, ValueError):
            return False


__all__ = ["EdgeRewireProposal", "PreparedEdgeRewire"]
