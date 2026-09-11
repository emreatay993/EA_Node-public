# Purpose: Apply invariant-checked graph mutations through graph-owned record writers.
# Map: subsystems/graph_domain.md
# Tests: tests/test_registry_validation.py, tests/test_dataflow_graph_persistence.py, tests/mechanical_catalogue/test_controls.py
# Landmarks: ValidatedGraphMutation; add_node; rewire_edges; set_node_properties; dynamic-port mutation; edge pruning

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from ea_node_editor.graph.boundary_adapters import GraphBoundaryAdapters, fallback_graph_boundary_adapters
from ea_node_editor.graph.edge_rewire import PreparedEdgeRewire
from ea_node_editor.graph.effective_ports import (
    EffectivePort,
)
from ea_node_editor.graph.hierarchy import validate_parent_node_id
from ea_node_editor.graph.invariant_kernel import (
    GraphInvariantKernel,
    RegistryNodeResolution,
    RegistryValidationPassMemo,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.property_validation import is_saved_property_value_valid
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.graph.subnode_contract import (
    SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY,
    SUBNODE_PIN_DATA_ACCESS_PROPERTY,
    SUBNODE_PIN_DATA_TYPE_PROPERTY,
    SUBNODE_PIN_KIND_PROPERTY,
    is_subnode_pin_type,
)
from ea_node_editor.graph.workspace_state import ViewState, WorkspaceData
from ea_node_editor.nodes.instance_resolution import resolve_dynamic_port_groups, resolve_instance_ports
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.node_specs import DynamicPortGroupSpec, NodeTypeSpec, PortSpec

_MISSING = object()


@dataclass(slots=True)
class ValidatedGraphMutation:
    model: GraphModel
    workspace_id: str
    registry: NodeRegistry
    boundary_adapters: GraphBoundaryAdapters = field(default_factory=fallback_graph_boundary_adapters)

    @property
    def workspace(self) -> WorkspaceData:
        return self.model.project.workspaces[self.workspace_id]

    @property
    def kernel(self) -> GraphInvariantKernel:
        return GraphInvariantKernel(
            registry=self.registry,
            workspace_nodes=self.workspace.nodes,
            workspace_edges=self.workspace.edges.values(),
        )

    def _active_view_state(self) -> ViewState:
        return self.workspace.active_view_state()

    def add_node(
        self,
        *,
        type_id: str,
        title: str,
        x: float,
        y: float,
        properties: dict[str, object] | None = None,
        exposed_ports: dict[str, bool] | None = None,
        visual_style: dict[str, object] | None = None,
        parent_node_id: str | None = None,
        custom_width: float | None = None,
        custom_height: float | None = None,
        expanded_settings_group_ids: tuple[str, ...] = (),
    ) -> NodeInstance:
        spec = self.registry.get_spec(type_id)
        requested_expanded_group_ids = tuple(
            str(group_id) for group_id in expanded_settings_group_ids
        )
        normalized_expanded_group_ids = tuple(
            group.group_id
            for group in spec.settings_groups
            if group.group_id in requested_expanded_group_ids
        )
        if normalized_expanded_group_ids != requested_expanded_group_ids:
            raise ValueError(
                "Expanded settings groups must be unique declared IDs in declaration order"
            )
        normalized_title = str(title or "").strip()
        if not normalized_title and not any(prop.key == "title" for prop in spec.properties):
            normalized_title = spec.display_name
        normalized_properties = self.registry.normalize_properties(
            type_id,
            dict(properties or {}),
            include_defaults=True,
        )
        self._validate_resolved_port_data_types(
            resolve_instance_ports(spec, normalized_properties)
        )
        requested_exposed_ports = {
            str(key): bool(value)
            for key, value in dict(exposed_ports or {}).items()
            if str(key).strip()
        }
        node = self.model._add_node_record(
            self.workspace_id,
            type_id=type_id,
            title=normalized_title,
            x=float(x),
            y=float(y),
            properties=normalized_properties,
            exposed_ports=requested_exposed_ports,
            visual_style=(
                dict(visual_style or {})
                if str(spec.runtime_behavior or "").strip().lower() == "passive"
                else {}
            ),
            custom_width=custom_width,
            custom_height=custom_height,
            expanded_settings_group_ids=normalized_expanded_group_ids,
        )
        node.parent_node_id = self._validated_parent_node_id(node.node_id, parent_node_id)
        node.exposed_ports = self._normalized_exposed_ports(node.node_id)
        return node

    def set_node_parent(self, node_id: str, parent_node_id: str | None) -> bool:
        node = self.workspace.nodes[node_id]
        normalized_parent_id = self._validated_parent_node_id(node_id, parent_node_id)
        current_parent_id = str(node.parent_node_id or "").strip() or None
        if current_parent_id == normalized_parent_id:
            return False
        affected_node_ids = {node_id}
        if current_parent_id:
            affected_node_ids.add(current_parent_id)
        if normalized_parent_id:
            affected_node_ids.add(normalized_parent_id)
        node.parent_node_id = normalized_parent_id
        self.workspace.mark_dirty()
        self._prune_edges_for_nodes(affected_node_ids)
        return True

    def add_edge(
        self,
        *,
        source_node_id: str,
        source_port_key: str,
        target_node_id: str,
        target_port_key: str,
        append_requested: bool = False,
        label: str = "",
        visual_style: dict[str, object] | None = None,
    ) -> EdgeInstance:
        workspace = self.workspace
        if source_node_id not in workspace.nodes:
            raise KeyError(f"Unknown source node: {source_node_id}")
        if target_node_id not in workspace.nodes:
            raise KeyError(f"Unknown target node: {target_node_id}")
        target_edges = [
            edge
            for edge in workspace.edges.values()
            if edge.target_node_id == target_node_id and edge.target_port_key == target_port_key
        ]
        exact = next(
            (
                edge
                for edge in target_edges
                if edge.source_node_id == source_node_id and edge.source_port_key == source_port_key
            ),
            None,
        )
        if exact is not None:
            return exact
        candidate = EdgeInstance("__candidate__", source_node_id, source_port_key,
                                 target_node_id, target_port_key)
        candidate_edges = [edge for edge in workspace.edges.values()
                           if append_requested or edge not in target_edges] + [candidate]
        GraphInvariantKernel(self.registry, workspace.nodes, candidate_edges).add_edge_or_raise(
            source_node_id=source_node_id,
            source_port_key=source_port_key,
            target_node_id=target_node_id,
            target_port_key=target_port_key,
            append_requested=append_requested,
            capacity_excluded_edge_id=candidate.edge_id,
        )
        if not append_requested:
            for edge in target_edges:
                self.model._remove_edge_record(self.workspace_id, edge.edge_id)
        added = self.model._add_edge_record(
            self.workspace_id,
            source_node_id=source_node_id,
            source_port_key=source_port_key,
            target_node_id=target_node_id,
            target_port_key=target_port_key,
            input_order=None if append_requested else 0,
            label=label,
            visual_style=dict(visual_style or {}),
        )
        self._prune_edges_for_nodes({target_node_id})
        return added

    def rewire_edges(
        self,
        edge_ids: list[object] | tuple[object, ...],
        endpoint: str,
        node_id: str,
        port_key: str,
        *,
        copy_requested: bool = False,
        append_requested: bool = False,
        _validate_only: bool = False,
    ) -> tuple[str, ...]:
        prepared = self.prepare_rewire_edges(
            edge_ids, endpoint, copy_requested=copy_requested, append_requested=append_requested,
        )
        proposal = prepared.validate(node_id, port_key)
        if proposal is None:
            return ()
        requested_edges = prepared.requested_edges
        if _validate_only:
            return tuple(edge.edge_id for edge in requested_edges)
        if not proposal.candidates:
            for edge in requested_edges:
                self.model._remove_edge_record(self.workspace_id, edge.edge_id)
            self._prune_edges_for_nodes({edge.target_node_id for edge in requested_edges})
            return tuple(edge.edge_id for edge in requested_edges)
        candidate_edges = proposal.candidates
        for edge_id in proposal.replaced_edge_ids:
            self.model._remove_edge_record(self.workspace_id, edge_id)
        if copy_requested:
            source = requested_edges[0]
            candidate = candidate_edges[0]
            copied = self.model._add_edge_record(
                self.workspace_id,
                source_node_id=candidate.source_node_id,
                source_port_key=candidate.source_port_key,
                target_node_id=candidate.target_node_id,
                target_port_key=candidate.target_port_key,
                enabled=source.enabled,
                input_order=candidate.input_order,
                label=source.label,
                visual_style=source.visual_style,
            )
            self._prune_edges_for_nodes({copied.target_node_id})
            return (copied.edge_id,)

        affected = {edge.target_node_id for edge in requested_edges + candidate_edges}
        for edge, candidate in zip(requested_edges, candidate_edges):
            self.model._move_edge_endpoint_record(
                self.workspace_id,
                edge.edge_id,
                source_node_id=candidate.source_node_id,
                source_port_key=candidate.source_port_key,
                target_node_id=candidate.target_node_id,
                target_port_key=candidate.target_port_key,
                input_order=candidate.input_order,
            )
        self._prune_edges_for_nodes(affected)
        return tuple(edge.edge_id for edge in requested_edges)

    def prepare_rewire_edges(
        self,
        edge_ids: list[object] | tuple[object, ...],
        endpoint: str,
        *,
        copy_requested: bool = False,
        append_requested: bool = False,
    ) -> PreparedEdgeRewire:
        """Prepare one read-only candidate session; commits always prepare afresh."""
        return PreparedEdgeRewire(
            registry=self.registry, workspace_nodes=self.workspace.nodes,
            workspace_edges=self.workspace.edges.values(), edge_ids=edge_ids, endpoint=endpoint,
            copy_requested=copy_requested, append_requested=append_requested,
        )

    def can_rewire_edges(
        self,
        edge_ids: list[object] | tuple[object, ...],
        endpoint: str,
        node_id: str,
        port_key: str,
        *,
        copy_requested: bool = False,
        append_requested: bool = False,
    ) -> bool:
        try:
            return bool(
                self.rewire_edges(
                    edge_ids,
                    endpoint,
                    node_id,
                    port_key,
                    copy_requested=copy_requested,
                    append_requested=append_requested,
                    _validate_only=True,
                )
            )
        except (KeyError, ValueError):
            return False

    def move_edge_endpoint(
        self,
        edge_id: str,
        endpoint: str,
        node_id: str,
        port_key: str,
        append_requested: bool = False,
    ) -> bool:
        return bool(
            self.rewire_edges(
                [edge_id],
                endpoint,
                node_id,
                port_key,
                append_requested=append_requested,
            )
        )

    def ports_compatible(
        self,
        *,
        source_node_id: str,
        source_port_key: str,
        target_node_id: str,
        target_port_key: str,
    ) -> bool:
        try:
            _source_node, _source_spec, source_port = self._resolved_port(source_node_id, source_port_key)
            _target_node, _target_spec, target_port = self._resolved_port(target_node_id, target_port_key)
        except (KeyError, ValueError):
            return False
        return self.kernel.type_resolver().compatibility(
            source_node_id, source_port_key, target_port,
        ).is_compatible

    def set_edges_enabled(self, edge_ids: list[str], enabled: bool) -> bool:
        requested = [self.workspace.edges[key] for key in dict.fromkeys(edge_ids)
                     if key in self.workspace.edges and self.workspace.edges[key].enabled != bool(enabled)]
        if not requested:
            return False
        requested_ids = {edge.edge_id for edge in requested}
        candidates = [edge.clone() for edge in self.workspace.edges.values()]
        for edge in candidates:
            if edge.edge_id in requested_ids:
                edge.enabled = bool(enabled)
        if enabled:
            kernel = GraphInvariantKernel(self.registry, self.workspace.nodes, candidates)
            memo = RegistryValidationPassMemo()
            try:
                for edge in requested:
                    kernel.add_edge_or_raise(
                        source_node_id=edge.source_node_id, source_port_key=edge.source_port_key,
                        target_node_id=edge.target_node_id, target_port_key=edge.target_port_key,
                        memo=memo,
                    )
            except (KeyError, ValueError):
                return False
        for edge in requested:
            self.model._set_edge_enabled_record(self.workspace_id, edge.edge_id, bool(enabled))
        self._prune_edges_for_nodes({edge.target_node_id for edge in requested})
        return True

    def set_edge_enabled(self, edge_id: str, enabled: bool) -> bool:
        return self.set_edges_enabled([edge_id], enabled)

    def remove_edge(self, edge_id: str) -> tuple[str, ...]:
        edge = self.workspace.edges.get(edge_id)
        if edge is None:
            return ()
        self.model._remove_edge_record(self.workspace_id, edge_id)
        return (edge_id, *self._prune_edges_for_nodes({edge.target_node_id}))

    def set_port_modifiers(
        self,
        node_id: str,
        port_key: str,
        modifiers: tuple[str, ...] | list[str],
    ) -> bool:
        node, _spec, port = self._resolved_port(node_id, port_key)
        if str(port.kind) != "data":
            raise ValueError("DataTree modifiers are available only on data ports.")
        previous = tuple(node.port_modifiers.get(port_key, ()))
        self.model._set_port_modifiers_record(self.workspace_id, node_id, port_key, modifiers)
        return previous != tuple(node.port_modifiers.get(port_key, ()))

    def set_principal_input_port(self, node_id: str, port_key: str | None) -> bool:
        node = self.workspace.nodes[node_id]
        normalized = str(port_key).strip() if port_key else None
        if normalized is not None:
            _node, _spec, port = self._resolved_port(node_id, normalized)
            if (
                str(port.kind) != "data"
                or str(port.direction) != "in"
                or str(getattr(port, "data_access", "item")) == "tree"
            ):
                raise ValueError("Principal must be an Item/List data input.")
        if node.principal_input_port_id == normalized:
            return False
        self.model._set_principal_input_port_record(self.workspace_id, node_id, normalized)
        return True

    def set_port_label(self, node_id: str, port_key: str, label: str) -> bool:
        node, spec, _port = self._resolved_port(node_id, port_key)
        properties = self.registry.normalize_properties(
            node.type_id,
            copy.deepcopy(node.properties),
            include_defaults=True,
        )
        dynamic_port = next(
            (
                port
                for port in resolve_instance_ports(spec, properties)[len(spec.ports) :]
                if port.key == port_key
            ),
            None,
        )
        if dynamic_port is not None:
            group = next(
                group
                for group in spec.dynamic_port_groups
                if group.direction == dynamic_port.direction
            )
            if group.rename_mode != "label":
                raise ValueError(
                    f"Dynamic port group {group.group_id} does not allow label rename."
                )
        normalized = str(label or "").strip()
        if node.port_labels.get(port_key, "") == normalized:
            return False
        self.model._set_port_label_record(
            self.workspace_id,
            node_id,
            port_key,
            normalized,
        )
        return True

    def insert_dynamic_port(self, node_id: str, group_id: str, ordinal: int) -> str:
        node, spec, group, properties, ports = self._dynamic_port_context(node_id, group_id)
        insert_at = int(ordinal)
        if insert_at < 0 or insert_at > len(ports):
            raise IndexError("Dynamic port ordinal is out of range.")
        if group.maximum is not None and len(ports) >= group.maximum:
            raise ValueError(
                f"Dynamic port group {group.group_id} allows at most {group.maximum} ports."
            )
        try:
            port_key = group.key_factory(copy.deepcopy(properties))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"Dynamic port group {group.group_id} key factory failed."
            ) from exc
        port_key = self._validated_dynamic_port_key(port_key, group.group_id)
        existing_keys = {port.key for port in resolve_instance_ports(spec, properties)}
        if port_key in existing_keys:
            raise ValueError(f"Dynamic port key already exists: {port_key}")

        candidate_keys = [port.key for port in ports]
        candidate_keys.insert(insert_at, port_key)
        resolved_keys, property_value = self._preflight_dynamic_port_keys(
            node=node,
            spec=spec,
            group=group,
            properties=properties,
            candidate_keys=candidate_keys,
        )
        if resolved_keys[insert_at] != port_key:
            raise ValueError(
                f"Dynamic port group {group.group_id} did not preserve inserted key {port_key}."
            )
        if group.property_editor is not None and node.type_id == "core.python_script":
            self.set_node_property(node_id, group.property_key, property_value)
            return port_key
        self.model._set_node_property_record(
            self.workspace_id,
            node_id,
            group.property_key,
            property_value,
        )
        self._prune_edges_for_nodes({node_id})
        return port_key

    def remove_dynamic_port(
        self,
        node_id: str,
        group_id: str,
        port_key: str,
    ) -> tuple[str, tuple[str, ...]]:
        node, spec, group, properties, ports = self._dynamic_port_context(node_id, group_id)
        normalized_key = str(port_key or "").strip()
        current_keys = [port.key for port in ports]
        if normalized_key not in current_keys:
            raise KeyError(
                f"Dynamic port {normalized_key!r} not found in group {group.group_id}."
            )
        if len(current_keys) <= group.minimum:
            raise ValueError(
                f"Dynamic port group {group.group_id} must retain at least {group.minimum} ports."
            )
        candidate_keys = [key for key in current_keys if key != normalized_key]
        resolved_keys, property_value = self._preflight_dynamic_port_keys(
            node=node,
            spec=spec,
            group=group,
            properties=properties,
            candidate_keys=candidate_keys,
        )
        removed_edge_ids = self._incident_edge_ids(node_id, normalized_key)
        if group.property_editor is not None and node.type_id == "core.python_script":
            self.set_node_property(node_id, group.property_key, property_value)
            return normalized_key, removed_edge_ids
        for edge_id in removed_edge_ids:
            self.model._remove_edge_record(self.workspace_id, edge_id)
        self.model._set_node_property_record(
            self.workspace_id,
            node_id,
            group.property_key,
            property_value,
        )
        self._clear_dynamic_port_state(node, normalized_key)
        removed_edge_ids += tuple(self._prune_edges_for_nodes({node_id}))
        return normalized_key, removed_edge_ids

    def rename_dynamic_port(
        self,
        node_id: str,
        group_id: str,
        port_key: str,
        value: str,
    ) -> tuple[str, tuple[str, ...]] | None:
        node, spec, group, properties, ports = self._dynamic_port_context(node_id, group_id)
        normalized_key = str(port_key or "").strip()
        ports_by_key = {port.key: port for port in ports}
        port = ports_by_key.get(normalized_key)
        if port is None:
            raise KeyError(
                f"Dynamic port {normalized_key!r} not found in group {group.group_id}."
            )
        if group.rename_mode == "none":
            raise ValueError(f"Dynamic port group {group.group_id} does not allow rename.")
        requested_value = str(value).strip()
        if group.rename_mode == "label":
            base_label = port.label or port.key
            current_label = node.port_labels.get(normalized_key) or base_label
            if requested_value == current_label or (
                not requested_value and normalized_key not in node.port_labels
            ):
                return None
            self.model._set_port_label_record(
                self.workspace_id,
                node_id,
                normalized_key,
                "" if requested_value == base_label else requested_value,
            )
            return normalized_key, ()

        assert group.key_renamer is not None
        try:
            renamed_key = group.key_renamer(
                copy.deepcopy(properties),
                normalized_key,
                requested_value,
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"Dynamic port group {group.group_id} key rename failed."
            ) from exc
        renamed_key = self._validated_dynamic_port_key(renamed_key, group.group_id)
        if renamed_key == normalized_key:
            return None
        existing_keys = {item.key for item in resolve_instance_ports(spec, properties)}
        existing_keys.discard(normalized_key)
        if renamed_key in existing_keys:
            raise ValueError(f"Dynamic port key already exists: {renamed_key}")

        current_keys = [item.key for item in ports]
        rename_at = current_keys.index(normalized_key)
        candidate_keys = list(current_keys)
        candidate_keys[rename_at] = renamed_key
        resolved_keys, property_value = self._preflight_dynamic_port_keys(
            node=node,
            spec=spec,
            group=group,
            properties=properties,
            candidate_keys=candidate_keys,
        )
        if resolved_keys[rename_at] != renamed_key:
            raise ValueError(
                f"Dynamic port group {group.group_id} did not preserve renamed key {renamed_key}."
            )
        removed_edge_ids = self._incident_edge_ids(node_id, normalized_key)
        if group.property_editor is not None and node.type_id == "core.python_script":
            self.set_node_property(node_id, group.property_key, property_value)
            return renamed_key, removed_edge_ids
        for edge_id in removed_edge_ids:
            self.model._remove_edge_record(self.workspace_id, edge_id)
        self.model._set_node_property_record(
            self.workspace_id,
            node_id,
            group.property_key,
            property_value,
        )
        self._clear_dynamic_port_state(node, normalized_key)
        removed_edge_ids += tuple(self._prune_edges_for_nodes({node_id}))
        return renamed_key, removed_edge_ids

    def set_node_property(self, node_id: str, key: str, value: object) -> object:
        node = self.workspace.nodes[node_id]
        if node.type_id == "core.python_script" and str(key) == "script":
            self.apply_python_script(node_id, str(value))
            return str(value)
        self._reject_dynamic_port_property_writes(node, {str(key or "")})
        normalized = self.registry.normalize_property_value(
            node.type_id,
            key,
            value,
            properties=node.properties,
        )
        normalized_updates = self._contextual_property_updates(node, {key: normalized})
        normalized_updates = self._guard_exposed_media_source_updates(
            node,
            normalized_updates,
        )
        if not normalized_updates:
            return normalized
        affected_node_ids = self._preflight_port_semantic_updates(
            node,
            normalized_updates,
        )
        for update_key, update_value in normalized_updates.items():
            self.model._set_node_property_record(self.workspace_id, node_id, update_key, update_value)
        if affected_node_ids:
            self._prune_edges_for_nodes(affected_node_ids)
        return normalized

    def apply_python_script(
        self,
        node_id: str,
        source: str,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        node = self.workspace.nodes[node_id]
        if node.type_id != "core.python_script":
            raise ValueError("Python Script Apply requires a core.python_script node.")

        old_spec = self.registry.resolve_spec(node.type_id, node.properties)
        candidate_seed = {
            "script": str(source),
            "timeout_sec": node.properties.get("timeout_sec", 0.0),
        }
        candidate_spec = self.registry.resolve_spec(node.type_id, candidate_seed)
        candidate_values: dict[str, object] = {}
        reset_keys: list[str] = []
        for prop in candidate_spec.properties:
            if prop.key == "script":
                candidate_values[prop.key] = str(source)
                continue
            previous = node.properties.get(prop.key, _MISSING)
            if previous is not _MISSING and is_saved_property_value_valid(
                prop,
                previous,
            ):
                candidate_values[prop.key] = copy.deepcopy(previous)
                continue
            candidate_values[prop.key] = copy.deepcopy(prop.default)
            if previous is not _MISSING and previous != prop.default:
                reset_keys.append(prop.key)

        candidate_properties = self.registry.normalize_properties(
            node.type_id,
            candidate_values,
            include_defaults=True,
        )
        candidate_spec = self.registry.resolve_spec(
            node.type_id,
            candidate_properties,
        )
        candidate_ports = resolve_instance_ports(
            candidate_spec,
            candidate_properties,
            data_types=self.registry.data_types,
        )
        self._validate_resolved_port_data_types(candidate_ports)
        candidate_ports_by_key = {port.key: port for port in candidate_ports}
        old_ports_by_key = {
            port.key: port
            for port in resolve_instance_ports(
                old_spec,
                node.properties,
                data_types=self.registry.data_types,
            )
        }
        semantic_changed_keys = {
            key
            for key in old_ports_by_key.keys() & candidate_ports_by_key.keys()
            if (
                old_ports_by_key[key].direction,
                old_ports_by_key[key].kind,
                old_ports_by_key[key].data_type,
                old_ports_by_key[key].accepted_data_types,
                old_ports_by_key[key].data_access,
                old_ports_by_key[key].type_from_input,
            )
            != (
                candidate_ports_by_key[key].direction,
                candidate_ports_by_key[key].kind,
                candidate_ports_by_key[key].data_type,
                candidate_ports_by_key[key].accepted_data_types,
                candidate_ports_by_key[key].data_access,
                candidate_ports_by_key[key].type_from_input,
            )
        }
        structure_changed_keys = {
            key
            for key in semantic_changed_keys
            if old_ports_by_key[key].data_access
            != candidate_ports_by_key[key].data_access
        }

        candidate_node = node.clone()
        candidate_node.properties = copy.deepcopy(candidate_properties)
        valid_port_keys = set(candidate_ports_by_key)
        candidate_node.exposed_ports = {
            key: bool(
                port.required
                or (
                    port.exposed
                    if key in semantic_changed_keys
                    else node.exposed_ports.get(key, port.exposed)
                )
            )
            for key, port in candidate_ports_by_key.items()
        }
        candidate_node.port_labels = {
            key: str(value)
            for key, value in node.port_labels.items()
            if key in valid_port_keys
            and key not in semantic_changed_keys
            and str(value).strip()
        }
        candidate_node.port_modifiers = {
            key: tuple(value)
            for key, value in node.port_modifiers.items()
            if key in valid_port_keys
            and key not in semantic_changed_keys
            and candidate_ports_by_key[key].kind == "data"
        }
        principal_key = str(node.principal_input_port_id or "")
        principal = candidate_ports_by_key.get(principal_key)
        candidate_node.principal_input_port_id = (
            principal_key
            if principal is not None
            and principal_key not in semantic_changed_keys
            and principal.direction == "in"
            and principal.kind == "data"
            and principal.data_access != "tree"
            else None
        )
        valid_group_ids = {group.group_id for group in candidate_spec.settings_groups}
        candidate_node.expanded_settings_group_ids = tuple(
            group_id
            for group_id in node.expanded_settings_group_ids
            if group_id in valid_group_ids
        )

        candidate_nodes = dict(self.workspace.nodes)
        candidate_nodes[node_id] = candidate_node
        candidate_kernel = GraphInvariantKernel(
            registry=self.registry,
            workspace_nodes=candidate_nodes,
            workspace_edges=self.workspace.edges.values(),
        )
        removed_edge_ids = self._edge_ids_to_prune(
            {node_id},
            kernel=candidate_kernel,
            forced_port_keys={node_id: structure_changed_keys},
        )

        node.properties = candidate_node.properties
        node.exposed_ports = candidate_node.exposed_ports
        node.port_labels = candidate_node.port_labels
        node.port_modifiers = candidate_node.port_modifiers
        node.principal_input_port_id = candidate_node.principal_input_port_id
        node.expanded_settings_group_ids = candidate_node.expanded_settings_group_ids
        self.workspace.mark_dirty()
        for edge_id in removed_edge_ids:
            self.model._remove_edge_record(self.workspace_id, edge_id)
        return tuple(reset_keys), tuple(removed_edge_ids)

    def set_node_properties(self, node_id: str, values: dict[str, object]) -> dict[str, object]:
        node = self.workspace.nodes[node_id]
        requested_values = dict(values or {})
        requested_keys = {
            str(key or "") for key in requested_values if str(key or "")
        }
        if node.type_id == "core.python_script" and "script" in requested_keys:
            if requested_keys != {"script"}:
                raise ValueError(
                    "Python Script source cannot be mixed with other bulk property updates."
                )
            source = str(requested_values.get("script", ""))
            self.apply_python_script(node_id, source)
            return {"script": source}
        self._reject_dynamic_port_property_writes(
            node,
            {str(key or "") for key in requested_values},
        )
        normalized_updates: dict[str, object] = {}
        for raw_key, raw_value in requested_values.items():
            key = str(raw_key or "")
            if not key:
                continue
            try:
                normalized = self.registry.normalize_property_value(
                    node.type_id,
                    key,
                    raw_value,
                    properties=node.properties,
                )
            except KeyError:
                continue
            normalized_updates[key] = normalized
        normalized_updates = self._contextual_property_updates(node, normalized_updates)
        normalized_updates = self._guard_exposed_media_source_updates(
            node,
            normalized_updates,
        )
        if not normalized_updates:
            return {}
        affected_node_ids = self._preflight_port_semantic_updates(
            node,
            normalized_updates,
        )
        for key, normalized in normalized_updates.items():
            self.model._set_node_property_record(self.workspace_id, node_id, key, normalized)
        if affected_node_ids:
            self._prune_edges_for_nodes(affected_node_ids)
        return normalized_updates

    @staticmethod
    def _guard_exposed_media_source_updates(
        node: NodeInstance,
        updates: dict[str, object],
    ) -> dict[str, object]:
        if (
            node.type_id != MEDIA_PANEL_TYPE_ID
            or not bool(node.exposed_ports.get("source", True))
            or "source" not in updates
        ):
            return updates
        if updates["source"] != node.properties.get("source"):
            raise PermissionError(
                "Media Panel source cannot be changed while the Source input is exposed."
            )
        filtered = dict(updates)
        filtered.pop("source")
        return filtered

    def _contextual_property_updates(
        self,
        node: NodeInstance,
        updates: dict[str, object],
    ) -> dict[str, object]:
        if not updates:
            return {}
        merged_properties = copy.deepcopy(node.properties)
        merged_properties.update(copy.deepcopy(updates))
        normalized_properties = self.registry.normalize_properties(
            node.type_id,
            merged_properties,
            include_defaults=False,
        )
        dynamic_property_keys = {
            group.property_key
            for group in self.registry.get_spec(node.type_id).dynamic_port_groups
        }
        return {
            key: value
            for key, value in normalized_properties.items()
            if (
                key not in dynamic_property_keys
                and node.properties.get(key, _MISSING) != value
            )
        }

    def _dynamic_port_context(
        self,
        node_id: str,
        group_id: str,
    ) -> tuple[
        NodeInstance,
        NodeTypeSpec,
        DynamicPortGroupSpec,
        dict[str, object],
        tuple[PortSpec, ...],
    ]:
        node = self.workspace.nodes[node_id]
        spec = self.registry.resolve_spec(node.type_id, node.properties)
        normalized_group_id = str(group_id or "").strip()
        group = next(
            (
                candidate
                for candidate in spec.dynamic_port_groups
                if candidate.group_id == normalized_group_id
            ),
            None,
        )
        if group is None:
            raise KeyError(
                f"Dynamic port group {normalized_group_id!r} not found on node type {spec.type_id}."
            )
        properties = self.registry.normalize_properties(
            node.type_id,
            copy.deepcopy(node.properties),
            include_defaults=True,
        )
        group_ports = resolve_dynamic_port_groups(spec, properties)[
            spec.dynamic_port_groups.index(group)
        ]
        return node, spec, group, properties, group_ports

    def _preflight_dynamic_port_keys(
        self,
        *,
        node: NodeInstance,
        spec: NodeTypeSpec,
        group: DynamicPortGroupSpec,
        properties: dict[str, object],
        candidate_keys: list[str],
    ) -> tuple[tuple[str, ...], object]:
        candidate_properties = copy.deepcopy(properties)
        candidate_properties[group.property_key] = (
            group.property_editor(copy.deepcopy(properties), tuple(candidate_keys))
            if group.property_editor is not None else list(candidate_keys)
        )
        normalized = self.registry.normalize_properties(
            node.type_id,
            candidate_properties,
            include_defaults=False,
        )
        spec = self.registry.resolve_spec(node.type_id, normalized)
        resolved = resolve_instance_ports(spec, normalized)
        self._validate_resolved_port_data_types(resolved)
        resolved_keys = tuple(
            port.key
            for port in resolve_dynamic_port_groups(spec, normalized)[
                next(i for i, candidate in enumerate(spec.dynamic_port_groups)
                     if candidate.group_id == group.group_id)
            ]
        )
        if resolved_keys != tuple(candidate_keys):
            raise ValueError(
                f"Dynamic port group {group.group_id} rejected the requested port keys."
            )
        return resolved_keys, normalized[group.property_key]

    def _preflight_port_semantic_updates(
        self,
        node: NodeInstance,
        updates: dict[str, object],
    ) -> set[str]:
        if not any(
            self._property_change_affects_ports(node, key)
            for key in updates
        ):
            return set()
        properties = copy.deepcopy(node.properties)
        properties.update(copy.deepcopy(updates))
        spec = self.registry.get_spec(node.type_id)
        self._validate_resolved_port_data_types(
            resolve_instance_ports(spec, properties)
        )
        return self._affected_node_ids_for_port_semantics(node)

    def _validate_resolved_port_data_types(
        self,
        ports: tuple[PortSpec, ...],
    ) -> None:
        for port in ports:
            if str(port.kind) != "data":
                continue
            for type_id in (
                str(port.data_type),
                *tuple(port.accepted_data_types),
            ):
                self.registry.data_types.require(type_id)

    @staticmethod
    def _validated_dynamic_port_key(value: object, group_id: str) -> str:
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError(
                f"Dynamic port group {group_id} produced an invalid port key: {value!r}."
            )
        return value

    def _incident_edge_ids(self, node_id: str, port_key: str) -> tuple[str, ...]:
        return tuple(
            edge.edge_id
            for edge in self.workspace.edges.values()
            if (
                edge.source_node_id == node_id
                and edge.source_port_key == port_key
            )
            or (
                edge.target_node_id == node_id
                and edge.target_port_key == port_key
            )
        )

    def _clear_dynamic_port_state(self, node: NodeInstance, port_key: str) -> None:
        node.exposed_ports.pop(port_key, None)
        if port_key in node.port_labels:
            self.model._set_port_label_record(self.workspace_id, node.node_id, port_key, "")
        if port_key in node.port_modifiers:
            self.model._set_port_modifiers_record(self.workspace_id, node.node_id, port_key, ())
        if node.principal_input_port_id == port_key:
            self.model._set_principal_input_port_record(self.workspace_id, node.node_id, None)

    def _reject_dynamic_port_property_writes(
        self,
        node: NodeInstance,
        keys: set[str],
    ) -> None:
        spec = self.registry.get_spec(node.type_id)
        dynamic_keys = {
            group.property_key
            for group in spec.dynamic_port_groups
        }
        blocked = sorted(dynamic_keys.intersection(keys))
        if blocked:
            raise ValueError(
                "Dynamic port backing properties may be changed only through "
                f"dynamic port mutations: {', '.join(blocked)}"
            )

    def set_exposed_port(self, node_id: str, key: str, exposed: bool) -> bool:
        node, _spec, port = self._resolved_port(node_id, key)
        normalized_exposed = bool(exposed)
        if port.required and not normalized_exposed:
            return False
        if key in node.exposed_ports and bool(node.exposed_ports[key]) == normalized_exposed:
            return False
        self.model._set_exposed_port_record(self.workspace_id, node_id, key, normalized_exposed)
        if not normalized_exposed:
            self._prune_edges_for_nodes({node_id})
        return True

    def set_view_hide_optional_ports(self, hide_optional_ports: bool) -> bool:
        view_state = self._active_view_state()
        normalized = bool(hide_optional_ports)
        if bool(view_state.hide_optional_ports) == normalized:
            return False
        view_state.hide_optional_ports = normalized
        self.workspace.mark_dirty()
        return True

    def _resolved_port(self, node_id: str, port_key: str) -> tuple[NodeInstance, NodeTypeSpec, EffectivePort]:
        return self.kernel._resolved_port(node_id, port_key)

    def _normalized_exposed_ports(self, node_id: str) -> dict[str, bool]:
        node = self.workspace.nodes[node_id]
        resolution = RegistryNodeResolution(
            node=node,
            spec=self.registry.get_spec(node.type_id),
        )
        return self.kernel.normalized_exposed_ports(resolution)

    def _validated_parent_node_id(self, node_id: str, parent_node_id: str | None) -> str | None:
        return validate_parent_node_id(self.workspace, node_id, parent_node_id)

    def _property_change_affects_ports(self, node: NodeInstance, key: str) -> bool:
        spec = self.registry.get_spec(node.type_id)
        if spec.instance_spec_resolver is not None or spec.dynamic_port_groups:
            return True
        if not is_subnode_pin_type(node.type_id):
            return False
        return key in {
            SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY,
            SUBNODE_PIN_DATA_ACCESS_PROPERTY,
            SUBNODE_PIN_DATA_TYPE_PROPERTY,
            SUBNODE_PIN_KIND_PROPERTY,
        }

    @staticmethod
    def _affected_node_ids_for_port_semantics(node: NodeInstance) -> set[str]:
        affected = {node.node_id}
        parent_node_id = str(node.parent_node_id or "").strip()
        if parent_node_id:
            affected.add(parent_node_id)
        return affected

    def _prune_edges_for_nodes(self, affected_node_ids: set[str]) -> list[str]:
        if not affected_node_ids:
            return []
        removed_edge_ids = self._edge_ids_to_prune(affected_node_ids)
        for edge_id in removed_edge_ids:
            self.workspace.edges.pop(edge_id, None)
        if removed_edge_ids:
            self.workspace.mark_dirty()
        return removed_edge_ids

    def _edge_ids_to_prune(
        self,
        affected_node_ids: set[str],
        *,
        kernel: GraphInvariantKernel | None = None,
        forced_port_keys: dict[str, set[str]] | None = None,
    ) -> list[str]:
        return (kernel or self.kernel).prunable_edge_ids(
            affected_node_ids=affected_node_ids, forced_port_keys=forced_port_keys,
        )


__all__ = ["ValidatedGraphMutation"]
