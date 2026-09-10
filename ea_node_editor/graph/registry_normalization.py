from __future__ import annotations

from ea_node_editor.graph.hierarchy import sanitize_workspace_parent_links
from ea_node_editor.graph.effective_ports import effective_ports
from ea_node_editor.graph.invariant_kernel import GraphInvariantKernel, RegistryValidationPassMemo
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import DATA_TREE_MODIFIER_ORDER


def normalize_project_for_registry(project: ProjectData, registry: NodeRegistry) -> None:
    """Normalize live graph content against the current registry."""
    for workspace in project.workspaces.values():
        workspace_changed = False
        kernel = GraphInvariantKernel(
            registry=registry,
            workspace_nodes=workspace.nodes,
            workspace_edges=workspace.edges.values(),
        )
        memo = RegistryValidationPassMemo()
        resolved_nodes = kernel.resolve_registry_nodes(memo=memo)
        unknown_node_ids = set(workspace.nodes) - set(resolved_nodes)
        for resolution in resolved_nodes.values():
            node = resolution.node
            try:
                normalized_properties = registry.normalize_properties(
                    node.type_id,
                    node.properties,
                    include_defaults=False,
                )
            except ValueError as exc:
                if "unknown data-type ID" not in str(exc):
                    raise
                normalized_properties = node.properties
            if node.properties != normalized_properties:
                node.properties = normalized_properties
                workspace_changed = True
            requested_settings_group_ids = set(node.expanded_settings_group_ids)
            normalized_settings_group_ids = tuple(
                group.group_id for group in resolution.spec.settings_groups if group.group_id in requested_settings_group_ids
            )
            if node.expanded_settings_group_ids != normalized_settings_group_ids:
                node.expanded_settings_group_ids = normalized_settings_group_ids
                workspace_changed = True

        for node_id in sorted(unknown_node_ids):
            if workspace.nodes.pop(node_id, None) is not None:
                workspace_changed = True

        for edge_id, edge in list(workspace.edges.items()):
            if edge.source_node_id in unknown_node_ids or edge.target_node_id in unknown_node_ids:
                if workspace.edges.pop(edge_id, None) is not None:
                    memo.invalidate_edges()
                    workspace_changed = True

        parent_links_before = {
            node_id: node.parent_node_id
            for node_id, node in workspace.nodes.items()
        }
        sanitize_workspace_parent_links(workspace)
        for node_id, node in workspace.nodes.items():
            if parent_links_before.get(node_id) != node.parent_node_id:
                workspace_changed = True
                break

        for resolution in resolved_nodes.values():
            normalized_exposed_ports = kernel.normalized_exposed_ports(resolution, memo=memo)
            if resolution.node.exposed_ports != normalized_exposed_ports:
                resolution.node.exposed_ports = normalized_exposed_ports
                workspace_changed = True
            effective = effective_ports(
                node=resolution.node,
                spec=resolution.spec,
                workspace_nodes=workspace.nodes,
            )
            ports_by_key = {port.key: port for port in effective}
            valid_port_keys = set(ports_by_key)
            non_label_rename_directions = {
                group.direction
                for group in resolution.spec.dynamic_port_groups
                if group.rename_mode != "label"
            }
            non_label_dynamic_port_keys = {
                port.key
                for port in effective[len(resolution.spec.ports) :]
                if port.direction in non_label_rename_directions
            }
            normalized_port_labels = {
                key: str(value)
                for key, value in resolution.node.port_labels.items()
                if (
                    key in valid_port_keys
                    and key not in non_label_dynamic_port_keys
                    and str(value).strip()
                )
            }
            if resolution.node.port_labels != normalized_port_labels:
                resolution.node.port_labels = normalized_port_labels
                workspace_changed = True
            normalized_modifiers = {
                key: tuple(
                    modifier
                    for modifier in DATA_TREE_MODIFIER_ORDER
                    if modifier in (
                        {str(item).strip().lower() for item in value}
                        if isinstance(value, (list, tuple, set, frozenset))
                        else set()
                    )
                )
                for key, value in resolution.node.port_modifiers.items()
                if key in ports_by_key and str(ports_by_key[key].kind) == "data"
            }
            normalized_modifiers = {
                key: value for key, value in normalized_modifiers.items() if value
            }
            if resolution.node.port_modifiers != normalized_modifiers:
                resolution.node.port_modifiers = normalized_modifiers
                workspace_changed = True
            principal_port = ports_by_key.get(str(resolution.node.principal_input_port_id or ""))
            if principal_port is None or (
                str(principal_port.kind) != "data"
                or str(principal_port.direction) != "in"
                or str(principal_port.data_access) == "tree"
            ):
                if resolution.node.principal_input_port_id is not None:
                    resolution.node.principal_input_port_id = None
                    workspace_changed = True

        seen_connections: set[tuple[str, str, str, str]] = set()
        occupied_single_target_ports: set[tuple[str, str]] = set()
        for edge_id, edge in list(workspace.edges.items()):
            resolution = kernel.validate_registry_edge(
                source_node_id=edge.source_node_id,
                source_port_key=edge.source_port_key,
                target_node_id=edge.target_node_id,
                target_port_key=edge.target_port_key,
                resolved_nodes=resolved_nodes,
                memo=memo,
                require_source_output=True,
                require_target_input=True,
                require_exposed_ports=True,
                require_compatible_ports=True,
            )
            if resolution is None or not kernel.accept_registry_edge(
                resolution,
                seen_connections=seen_connections,
                occupied_single_target_ports=occupied_single_target_ports,
            ):
                if workspace.edges.pop(edge_id, None) is not None:
                    memo.invalidate_edges()
                    workspace_changed = True

        input_groups: dict[tuple[str, str], list] = {}
        for edge in workspace.edges.values():
            input_groups.setdefault((edge.target_node_id, edge.target_port_key), []).append(edge)
        for edges in input_groups.values():
            ordered = sorted(edges, key=lambda edge: (edge.input_order, edge.edge_id))
            for input_order, edge in enumerate(ordered):
                if edge.input_order != input_order:
                    edge.input_order = input_order
                    workspace_changed = True

        if workspace_changed:
            workspace.mark_dirty()


__all__ = ["normalize_project_for_registry"]
