# Purpose: Build and fingerprint the executable dependency topology for one run.
# Map: subsystems/execution.md
# Tests: tests/test_execution_plan.py, tests/test_runtime_current_results.py

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace
import hashlib
import json
from typing import Any

from ea_node_editor.common.optimization_links import (
    OPTIMIZATION_PARAMETER_POOL_TYPE_ID,
    OPTIMIZATION_PARAMETER_SETUP_TYPE_ID,
    OPTIMIZATION_RESPONSE_POOL_TYPE_ID,
    optimization_pool_role,
    parameter_setup_pool_link_facts,
)
from ea_node_editor.execution.runtime_dto import RuntimeEdge, RuntimeWorkspace
from ea_node_editor.execution.solution_identity import canonical_digest

_TRIGGER_TYPE_ID = "core.trigger"
_FINGERPRINT_SCHEMA_VERSION = 1
WORKFLOW_INTERFACE_REVISION = 2


class _ExecutionCycleError(ValueError):
    pass


class ExecutionPlan:
    def __init__(
        self,
        workspace: RuntimeWorkspace,
        registry: Any,
        *,
        target_node_ids: tuple[str, ...] = (),
        clicked_trigger_node_id: str = "",
        trigger_capture_node_ids: tuple[str, ...] = (),
    ) -> None:
        try:
            self._initialize(
                workspace,
                registry,
                target_node_ids=target_node_ids,
                clicked_trigger_node_id=clicked_trigger_node_id,
                trigger_capture_node_ids=trigger_capture_node_ids,
            )
        except _ExecutionCycleError as exc:
            raise ValueError(str(exc)) from None

    @classmethod
    def for_invalidation(
        cls,
        workspace: RuntimeWorkspace,
        registry: Any,
    ) -> "ExecutionPlan":
        plan = cls.__new__(cls)
        try:
            plan._initialize(workspace, registry)
        except _ExecutionCycleError:
            plan.execution_order = plan._compiled_declaration_order()
            plan._finalize()
        return plan

    def _initialize(
        self,
        workspace: RuntimeWorkspace,
        registry: Any,
        *,
        target_node_ids: tuple[str, ...] = (),
        clicked_trigger_node_id: str = "",
        trigger_capture_node_ids: tuple[str, ...] = (),
    ) -> None:
        self.workspace = workspace
        self.nodes = workspace.nodes_by_id
        self.clicked_trigger_node_id = str(clicked_trigger_node_id or "").strip()
        self.trigger_capture_node_ids = frozenset(
            str(node_id or "").strip()
            for node_id in trigger_capture_node_ids
            if str(node_id or "").strip()
        )
        self.target_nodes = tuple(
            node_id
            for node_id in dict.fromkeys(
                str(node_id or "").strip() for node_id in target_node_ids
            )
            if node_id
        )
        self._resolved_target_nodes = tuple(
            node_id for node_id in self.target_nodes if node_id in self.nodes
        )
        self._has_explicit_target_filter = bool(self.target_nodes)
        from ea_node_editor.nodes.python_script_declaration import (
            PythonScriptDeclarationError,
        )

        self.node_preflight_errors: dict[str, PythonScriptDeclarationError] = {}
        self.node_specs = {}
        for node_id, node in self.nodes.items():
            try:
                self.node_specs[node_id] = registry.resolve_spec(
                    node.type_id, node.properties
                )
            except (TypeError, ValueError) as exc:
                if node.type_id != "core.python_script":
                    raise
                self.node_preflight_errors[node_id] = (
                    exc
                    if isinstance(exc, PythonScriptDeclarationError)
                    else PythonScriptDeclarationError(str(exc))
                )
                self.node_specs[node_id] = replace(
                    registry.get_spec(node.type_id),
                    instance_spec_resolver=None,
                )
        self.node_instances = self._materialize_nodes()
        self.node_ports = self._resolve_effective_ports()
        self.ports_by_key = {
            node_id: {port.key: port for port in ports}
            for node_id, ports in self.node_ports.items()
        }
        self.data_incoming: dict[str, list[RuntimeEdge]] = defaultdict(list)
        self.data_outgoing: dict[str, list[RuntimeEdge]] = defaultdict(list)
        for edge in sorted(
            (edge for edge in workspace.edges if edge.enabled),
            key=lambda item: (
                item.target_node_id,
                item.target_port_key,
                item.input_order,
            ),
        ):
            self.data_incoming[edge.target_node_id].append(edge)
            self.data_outgoing[edge.source_node_id].append(edge)
        self._hidden_ordering_pairs = self._decode_hidden_ordering_pairs()
        self.scheduled_node_ids = self._build_scheduled_nodes()
        self.execution_order = self._topological_order()
        self._finalize()

    def _finalize(self) -> None:
        self.workflow_interface_revision = WORKFLOW_INTERFACE_REVISION
        self.workflow_interface_digest = self._workflow_interface_digest()
        self.fingerprint = self._topology_fingerprint()

    def _compiled_declaration_order(self) -> tuple[str, ...]:
        return tuple(
            node.node_id
            for node in self.workspace.nodes
            if node.node_id in self.scheduled_node_ids
        )

    def _materialize_nodes(self) -> dict[str, Any]:
        from ea_node_editor.graph.record_payloads import node_instance_from_mapping

        result: dict[str, Any] = {}
        for node_id, node in self.nodes.items():
            materialized = node_instance_from_mapping(node.to_document())
            if materialized is None:
                raise ValueError(f"Unable to materialize runtime node: {node_id}")
            result[node_id] = materialized
        return result

    def _resolve_effective_ports(self) -> dict[str, tuple[Any, ...]]:
        from ea_node_editor.graph.effective_ports import effective_ports

        return {
            node_id: effective_ports(
                node=node,
                spec=self.node_specs[node_id],
                workspace_nodes=self.node_instances,
            )
            for node_id, node in self.node_instances.items()
        }

    def _decode_hidden_ordering_pairs(self) -> tuple[tuple[str, str], ...]:
        expected_pool_types = (
            OPTIMIZATION_PARAMETER_POOL_TYPE_ID,
            OPTIMIZATION_RESPONSE_POOL_TYPE_ID,
        )
        candidates: list[tuple[str, str]] = []
        target_counts: dict[str, int] = defaultdict(int)
        workspace_id = self.workspace.workspace_id
        for setup_node in self.workspace.nodes:
            if setup_node.type_id != OPTIMIZATION_PARAMETER_SETUP_TYPE_ID:
                continue
            raw_links = setup_node.extra_fields.get("links", ())
            if not isinstance(raw_links, Sequence) or isinstance(
                raw_links, (str, bytes)
            ):
                continue
            link_mappings = tuple(
                link for link in raw_links if isinstance(link, Mapping)
            )
            for expected_pool_type in expected_pool_types:
                link_facts = parameter_setup_pool_link_facts(
                    optimization_pool_role(expected_pool_type)
                )
                if link_facts is None:
                    continue
                link_id, link_title = link_facts
                matching = tuple(
                    link for link in link_mappings if link.get("id") == link_id
                )
                if len(matching) != 1:
                    continue
                link = matching[0]
                target_node_id = link.get("target_node_id")
                target_node = (
                    self.nodes.get(target_node_id)
                    if isinstance(target_node_id, str)
                    else None
                )
                if (
                    target_node is None
                    or target_node.type_id != expected_pool_type
                    or link.get("kind") != "node"
                    or link.get("title") != link_title
                    or link.get("target") != target_node_id
                    or link.get("subtitle") != ""
                    or link.get("target_workspace_id") != workspace_id
                ):
                    continue
                pair = (setup_node.node_id, target_node_id)
                candidates.append(pair)
                target_counts[target_node_id] += 1
        conflicting_target_id = next(
            (
                target_node_id
                for target_node_id, count in target_counts.items()
                if count > 1
            ),
            "",
        )
        if conflicting_target_id:
            raise ValueError(
                "Conflicting Parameter Setup links target pool node "
                f"{conflicting_target_id!r}."
            )
        return tuple(candidates)

    def includes_node(self, node_id: str) -> bool:
        return node_id in self.scheduled_node_ids

    @property
    def hidden_ordering_pairs(self) -> tuple[tuple[str, str], ...]:
        return self._hidden_ordering_pairs

    def is_trigger(self, node_id: str) -> bool:
        node = self.nodes.get(node_id)
        return node is not None and node.type_id == _TRIGGER_TYPE_ID

    def _build_scheduled_nodes(self) -> set[str]:
        return self.required_node_ids()

    def required_node_ids(
        self, result_boundaries: frozenset[str] = frozenset()
    ) -> set[str]:
        """Resolve execution demand while retaining the full plan for attestation."""
        if not self._has_explicit_target_filter:
            return set(self.nodes)
        targets = set(self._resolved_target_nodes)
        explicit_targets = set(targets)
        if self.clicked_trigger_node_id in self.nodes:
            targets.add(self.clicked_trigger_node_id)
        pending = list(targets)
        while pending:
            current = pending.pop()
            if current in result_boundaries:
                continue
            if self.is_trigger(current):
                if (
                    current == self.clicked_trigger_node_id
                    and current in self.trigger_capture_node_ids
                ):
                    continue
                if (
                    current != self.clicked_trigger_node_id
                    and current not in explicit_targets
                ):
                    continue
            for edge in self.data_incoming.get(current, ()):
                source_node_id = edge.source_node_id
                if source_node_id not in self.nodes or source_node_id in targets:
                    continue
                targets.add(source_node_id)
                pending.append(source_node_id)
            for source_node_id, target_node_id in self._hidden_ordering_pairs:
                if target_node_id != current or source_node_id in targets:
                    continue
                targets.add(source_node_id)
                pending.append(source_node_id)
        if self.clicked_trigger_node_id in targets:
            pending = [self.clicked_trigger_node_id]
            while pending:
                current = pending.pop()
                for edge in self.data_outgoing.get(current, ()):
                    downstream = edge.target_node_id
                    if self.is_trigger(downstream) or downstream in targets:
                        continue
                    targets.add(downstream)
                    pending.append(downstream)
        return targets

    def dependency_edges(self) -> tuple[RuntimeEdge, ...]:
        return tuple(
            edge
            for node_id in self.scheduled_node_ids
            for edge in self.data_incoming.get(node_id, ())
            if edge.source_node_id in self.scheduled_node_ids
            and not self.is_trigger(node_id)
        )

    def current_result_ports(
        self, boundaries: frozenset[str]
    ) -> dict[str, tuple[str, ...]]:
        """Return only ports actually consumed past the current-result boundaries."""
        consumers = self.required_node_ids(boundaries).difference(boundaries)
        if any(
            source in boundaries and target in consumers
            for source, target in self.hidden_ordering_pairs
        ):
            raise ValueError("an ordering dependency cannot consume a current result")
        ports = {node_id: set() for node_id in boundaries}
        for source in boundaries:
            ports[source].update(
                edge.source_port_key
                for edge in self.data_outgoing.get(source, ())
                if edge.target_node_id in consumers
            )
        if any(not values for values in ports.values()):
            raise ValueError("a current-result boundary needs a data-port consumer")
        return {node_id: tuple(sorted(values)) for node_id, values in ports.items()}

    def _topological_order(self) -> tuple[str, ...]:
        validated_order = self._topological_subset(self.scheduled_node_ids)
        if self.clicked_trigger_node_id not in self.scheduled_node_ids:
            return validated_order
        upstream = self._clicked_upstream_nodes()
        downstream = self.scheduled_node_ids.difference(
            upstream, {self.clicked_trigger_node_id}
        )
        return (
            *self._topological_subset(upstream),
            self.clicked_trigger_node_id,
            *self._topological_subset(downstream),
        )

    def _clicked_upstream_nodes(self) -> set[str]:
        upstream: set[str] = set()
        pending = [self.clicked_trigger_node_id]
        while pending:
            current = pending.pop()
            for edge in self.data_incoming.get(current, ()):
                source = edge.source_node_id
                if source == self.clicked_trigger_node_id or source in upstream:
                    continue
                if source not in self.scheduled_node_ids:
                    continue
                upstream.add(source)
                if not self.is_trigger(source):
                    pending.append(source)
            for source, target in self._hidden_ordering_pairs:
                if target != current:
                    continue
                if source == self.clicked_trigger_node_id or source in upstream:
                    continue
                if source not in self.scheduled_node_ids:
                    continue
                upstream.add(source)
                if not self.is_trigger(source):
                    pending.append(source)
        return upstream

    def _topological_subset(self, node_ids: set[str]) -> tuple[str, ...]:
        incoming_count = {node_id: 0 for node_id in node_ids}
        outgoing: dict[str, list[str]] = defaultdict(list)
        for edge in self.dependency_edges():
            if (
                edge.source_node_id not in node_ids
                or edge.target_node_id not in node_ids
            ):
                continue
            incoming_count[edge.target_node_id] += 1
            outgoing[edge.source_node_id].append(edge.target_node_id)
        for source_node_id, target_node_id in self._hidden_ordering_pairs:
            if source_node_id not in node_ids or target_node_id not in node_ids:
                continue
            incoming_count[target_node_id] += 1
            outgoing[source_node_id].append(target_node_id)
        declaration_order = {
            node.node_id: ordinal for ordinal, node in enumerate(self.workspace.nodes)
        }
        ready = sorted(
            (node_id for node_id, count in incoming_count.items() if count == 0),
            key=lambda node_id: declaration_order.get(node_id, 0),
        )
        ordered: list[str] = []
        while ready:
            node_id = ready.pop(0)
            ordered.append(node_id)
            for downstream in outgoing.get(node_id, ()):
                incoming_count[downstream] -= 1
                if incoming_count[downstream] == 0:
                    ready.append(downstream)
            ready.sort(key=lambda item: declaration_order.get(item, 0))
        if len(ordered) != len(node_ids):
            cyclic = sorted(
                node_id for node_id, count in incoming_count.items() if count > 0
            )
            raise _ExecutionCycleError(
                f"Cycle detected among nodes: {', '.join(cyclic)}"
            )
        return tuple(ordered)

    def input_ports(self, node_id: str) -> tuple[Any, ...]:
        return tuple(
            port for port in self.node_ports.get(node_id, ()) if port.direction == "in"
        )

    def output_ports(self, node_id: str) -> tuple[Any, ...]:
        return tuple(
            port for port in self.node_ports.get(node_id, ()) if port.direction == "out"
        )

    def incoming_edges_for(
        self, node_id: str, port_key: str = ""
    ) -> tuple[RuntimeEdge, ...]:
        return tuple(
            edge
            for edge in self.data_incoming.get(node_id, ())
            if not port_key or edge.target_port_key == port_key
        )

    def affected_downstream_closure(
        self,
        root_node_ids: Sequence[str],
    ) -> dict[str, tuple[str, ...]]:
        """Return affected executable nodes and their contributing roots in plan order."""

        if isinstance(root_node_ids, (str, bytes)) or not isinstance(
            root_node_ids, Sequence
        ):
            raise TypeError("root_node_ids must be a sequence of node IDs")
        normalized_roots: list[str] = []
        for raw_node_id in root_node_ids:
            if not isinstance(raw_node_id, str) or not raw_node_id.strip():
                raise ValueError("root_node_ids must contain non-empty strings")
            node_id = raw_node_id.strip()
            if node_id not in self.nodes:
                raise ValueError(f"Unknown invalidation root node: {node_id}")
            if self.node_specs[node_id].runtime_behavior != "active":
                raise ValueError(f"Invalidation root is not executable: {node_id}")
            if node_id not in normalized_roots:
                normalized_roots.append(node_id)

        declaration_order = tuple(
            node_id
            for node_id in self.execution_order
            if self.node_specs[node_id].runtime_behavior == "active"
        )
        order_index = {
            node_id: ordinal for ordinal, node_id in enumerate(declaration_order)
        }
        roots = tuple(sorted(normalized_roots, key=order_index.__getitem__))
        contributing: dict[str, set[str]] = defaultdict(set)
        for root_node_id in roots:
            pending = [root_node_id]
            visited: set[str] = set()
            while pending:
                node_id = pending.pop()
                if node_id in visited:
                    continue
                visited.add(node_id)
                contributing[node_id].add(root_node_id)
                if self.is_trigger(node_id):
                    continue
                downstream = {
                    edge.target_node_id
                    for edge in self.data_outgoing.get(node_id, ())
                    if edge.target_node_id in order_index
                }
                downstream.update(
                    target_node_id
                    for source_node_id, target_node_id in self._hidden_ordering_pairs
                    if source_node_id == node_id and target_node_id in order_index
                )
                pending.extend(
                    sorted(
                        downstream.difference(visited),
                        key=order_index.__getitem__,
                        reverse=True,
                    )
                )
        return {
            node_id: tuple(root for root in roots if root in contributing[node_id])
            for node_id in declaration_order
            if node_id in contributing
        }

    def node_solution_interface_digest(self, node_id: str) -> str:
        """Identify this producer's interface, independently of its consumers."""
        return canonical_digest(
            {
                "revision": WORKFLOW_INTERFACE_REVISION,
                "node": self._workflow_node_interface(node_id),
            }
        )

    def _workflow_interface_digest(self) -> str:
        return canonical_digest(
            {
                "revision": WORKFLOW_INTERFACE_REVISION,
                "nodes": [self._workflow_node_interface(node_id) for node_id in self.execution_order],
            }
        )

    def _workflow_node_interface(self, node_id: str) -> dict[str, object]:
        spec = self.node_specs[node_id]
        node = self.nodes[node_id]
        property_defaults = {
            property_spec.key: property_spec.default
            for property_spec in spec.properties
        }
        return {
            "node_id": node_id,
            "type_id": node.type_id,
            "ports": [
                {
                    "key": port.key,
                    "direction": port.direction,
                    "kind": port.kind,
                    "data_type": port.data_type,
                    "accepted_data_types": port.accepted_data_types,
                    "data_access": port.data_access,
                    "required": port.required,
                    "uses_property_default": port.uses_property_default,
                    "property_default": (
                        property_defaults.get(port.key)
                        if port.uses_property_default
                        else None
                    ),
                    "exposed": port.exposed,
                    "allow_multiple_connections": port.allow_multiple_connections,
                    "modifiers": tuple(node.port_modifiers.get(port.key, ())),
                }
                for port in self.node_ports.get(node_id, ())
            ],
            "principal_input_port_id": node.principal_input_port_id,
            "readiness_requirements": [
                {
                    "any_of_ports": requirement.any_of_ports,
                    "any_of_properties": requirement.any_of_properties,
                    "when_ports_present": requirement.when_ports_present,
                    "when_properties": [
                        {
                            "property_key": condition.property_key,
                            "values": condition.values,
                        }
                        for condition in requirement.when_properties
                    ],
                }
                for requirement in spec.readiness_requirements
            ],
        }

    def _topology_fingerprint(self) -> str:
        payload = {
            "schema_version": _FINGERPRINT_SCHEMA_VERSION,
            "workspace_id": self.workspace.workspace_id,
            "targets": list(self.target_nodes),
            "clicked_trigger_node_id": self.clicked_trigger_node_id,
            "trigger_capture_node_ids": sorted(self.trigger_capture_node_ids),
            "scheduled_node_ids": list(self.execution_order),
            "nodes": [
                {
                    "node_id": node_id,
                    "type_id": self.nodes[node_id].type_id,
                    "ports": [
                        {
                            "key": port.key,
                            "direction": port.direction,
                            "kind": port.kind,
                            "data_type": port.data_type,
                            "data_access": port.data_access,
                            "required": port.required,
                            "allow_multiple_connections": port.allow_multiple_connections,
                            "uses_property_default": port.uses_property_default,
                            "accepted_data_types": list(port.accepted_data_types),
                        }
                        for port in self.node_ports.get(node_id, ())
                    ],
                }
                for node_id in self.execution_order
            ],
            "enabled_edges": [
                {
                    "source_node_id": edge.source_node_id,
                    "source_port_key": edge.source_port_key,
                    "target_node_id": edge.target_node_id,
                    "target_port_key": edge.target_port_key,
                    "input_order": edge.input_order,
                }
                for edge in sorted(
                    (
                        edge
                        for edge in self.workspace.edges
                        if edge.enabled
                        and edge.source_node_id in self.scheduled_node_ids
                        and edge.target_node_id in self.scheduled_node_ids
                    ),
                    key=lambda edge: (
                        edge.target_node_id,
                        edge.target_port_key,
                        edge.input_order,
                        edge.source_node_id,
                        edge.source_port_key,
                    ),
                )
            ],
            "hidden_ordering_pairs": [
                list(pair)
                for pair in self._hidden_ordering_pairs
                if pair[0] in self.scheduled_node_ids
                and pair[1] in self.scheduled_node_ids
            ],
        }
        encoded = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


__all__ = ["ExecutionPlan", "WORKFLOW_INTERFACE_REVISION"]
