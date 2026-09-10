# Purpose: Compare open graph instances with a candidate node registry without mutation.
# Map: subsystems/graph_domain.md
# Tests: tests/test_registry_compatibility.py

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ea_node_editor.graph.effective_ports import EffectivePort, effective_ports
from ea_node_editor.graph.invariant_kernel import (
    GraphInvariantKernel,
    RegistryNodeResolution,
    RegistryValidationPassMemo,
)
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.graph.property_validation import is_saved_property_value_valid
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PropertySpec
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import DataTypeCatalog


@dataclass(slots=True, frozen=True)
class RegistryCompatibilityIssue:
    code: str
    message: str
    project_id: str
    workspace_id: str
    node_id: str = ""
    edge_id: str = ""
    member_key: str = ""


@dataclass(slots=True, frozen=True)
class RegistryCompatibilityReport:
    issues: tuple[RegistryCompatibilityIssue, ...] = ()

    @property
    def compatible(self) -> bool:
        return not self.issues


_PORT_FIELDS = (
    ("direction", "port_direction_changed", "direction"),
    ("kind", "port_kind_changed", "kind"),
    ("data_type", "port_data_type_changed", "data type"),
    (
        "accepted_data_types",
        "port_accepted_data_types_changed",
        "accepted data types",
    ),
    ("data_access", "port_access_changed", "data access"),
    ("required", "port_requiredness_changed", "requiredness"),
    (
        "allow_multiple_connections",
        "port_multiplicity_changed",
        "connection multiplicity",
    ),
    ("exposed", "port_exposure_changed", "exposure"),
    (
        "uses_property_default",
        "port_property_default_pairing_changed",
        "property-default pairing",
    ),
)

_PROPERTY_STORAGE_FIELDS = (
    (
        "persistence_data_type_id",
        "property_persistence_data_type_changed",
        "persistence data type",
    ),
    ("sensitive", "property_sensitivity_changed", "sensitivity"),
    (
        "sensitive_scope_key",
        "property_sensitive_scope_changed",
        "sensitive scope",
    ),
)


def check_registry_compatibility(
    *,
    current_registry: NodeRegistry,
    candidate_registry: NodeRegistry,
    projects: ProjectData | Iterable[ProjectData],
) -> RegistryCompatibilityReport:
    """Return every incompatibility without changing a project or registry."""
    if not isinstance(current_registry, NodeRegistry):
        raise TypeError("current_registry must be a NodeRegistry")
    if not isinstance(candidate_registry, NodeRegistry):
        raise TypeError("candidate_registry must be a NodeRegistry")
    project_items = (projects,) if isinstance(projects, ProjectData) else tuple(projects)
    if not all(isinstance(project, ProjectData) for project in project_items):
        raise TypeError("projects must contain ProjectData values")

    issues: list[RegistryCompatibilityIssue] = []
    for project in project_items:
        for workspace_id in sorted(project.workspaces):
            _check_workspace(
                project=project,
                workspace=project.workspaces[workspace_id],
                current_registry=current_registry,
                candidate_registry=candidate_registry,
                issues=issues,
            )
    return RegistryCompatibilityReport(tuple(issues))


def _check_workspace(
    *,
    project: ProjectData,
    workspace: WorkspaceData,
    current_registry: NodeRegistry,
    candidate_registry: NodeRegistry,
    issues: list[RegistryCompatibilityIssue],
) -> None:
    def add_issue(
        code: str,
        message: str,
        *,
        node_id: str = "",
        edge_id: str = "",
        member_key: str = "",
    ) -> None:
        issues.append(
            RegistryCompatibilityIssue(
                code=code,
                message=message,
                project_id=str(project.project_id),
                workspace_id=str(workspace.workspace_id),
                node_id=node_id,
                edge_id=edge_id,
                member_key=member_key,
            )
        )

    candidate_resolutions: dict[str, RegistryNodeResolution] = {}
    for node_id in sorted(workspace.nodes):
        node = workspace.nodes[node_id]
        if candidate_registry.spec_or_none(node.type_id) is None:
            add_issue(
                "node_type_missing",
                f"Node type {node.type_id!r} is missing from the candidate registry.",
                node_id=node_id,
            )
            continue
        if current_registry.spec_or_none(node.type_id) is None:
            add_issue(
                "current_node_type_missing",
                f"Node type {node.type_id!r} is missing from the current registry.",
                node_id=node_id,
            )
            continue
        try:
            current_spec = current_registry.resolve_spec(node.type_id, node.properties)
        except Exception:  # noqa: BLE001 - a resolver failure is an incompatibility
            add_issue(
                "current_node_resolution_failed",
                f"Node type {node.type_id!r} cannot resolve its current instance.",
                node_id=node_id,
            )
            continue
        try:
            candidate_spec = candidate_registry.resolve_spec(node.type_id, node.properties)
        except Exception:  # noqa: BLE001 - candidate code must not abort the check
            add_issue(
                "candidate_node_resolution_failed",
                f"Node type {node.type_id!r} cannot resolve against saved properties.",
                node_id=node_id,
            )
            continue

        _check_properties(
            node_id=node_id,
            saved_properties=node.properties,
            current_spec=current_spec,
            candidate_spec=candidate_spec,
            current_data_types=current_registry.data_types,
            candidate_data_types=candidate_registry.data_types,
            add_issue=add_issue,
        )
        try:
            current_ports = effective_ports(
                node=node,
                spec=current_spec,
                workspace_nodes=workspace.nodes,
            )
            candidate_ports = effective_ports(
                node=node,
                spec=candidate_spec,
                workspace_nodes=workspace.nodes,
            )
        except Exception:  # noqa: BLE001 - dynamic port failures are reported
            add_issue(
                "candidate_port_resolution_failed",
                f"Node type {node.type_id!r} cannot resolve effective ports.",
                node_id=node_id,
            )
            continue
        _check_ports(
            node_id=node_id,
            current_ports=current_ports,
            candidate_ports=candidate_ports,
            add_issue=add_issue,
        )
        candidate_resolutions[node_id] = RegistryNodeResolution(
            node=node,
            spec=candidate_spec,
        )

    kernel = GraphInvariantKernel(
        registry=candidate_registry,
        workspace_nodes=workspace.nodes,
        workspace_edges=workspace.edges.values(),
    )
    memo = RegistryValidationPassMemo(resolved_nodes=candidate_resolutions)
    seen_connections: set[tuple[str, str, str, str]] = set()
    occupied_single_target_ports: set[tuple[str, str]] = set()
    for edge_id, edge in workspace.edges.items():
        try:
            resolution = kernel.validate_registry_edge(
                source_node_id=edge.source_node_id,
                source_port_key=edge.source_port_key,
                target_node_id=edge.target_node_id,
                target_port_key=edge.target_port_key,
                resolved_nodes=candidate_resolutions,
                memo=memo,
                require_source_output=True,
                require_target_input=True,
                require_exposed_ports=True,
                require_compatible_ports=True,
            )
        except Exception:  # noqa: BLE001 - edge resolution failures are reported
            resolution = None
        if resolution is None:
            add_issue(
                "candidate_invalid_edge",
                "The candidate registry rejects this existing edge.",
                edge_id=edge_id,
            )
            continue
        if not kernel.accept_registry_edge(
            resolution,
            seen_connections=seen_connections,
            occupied_single_target_ports=occupied_single_target_ports,
        ):
            add_issue(
                "candidate_edge_cardinality",
                "The candidate registry rejects this edge by connection cardinality.",
                edge_id=edge_id,
            )


def _check_properties(
    *,
    node_id: str,
    saved_properties: dict[str, object],
    current_spec: NodeTypeSpec,
    candidate_spec: NodeTypeSpec,
    current_data_types: DataTypeCatalog,
    candidate_data_types: DataTypeCatalog,
    add_issue,
) -> None:
    current_by_key = {prop.key: prop for prop in current_spec.properties}
    candidate_by_key = {prop.key: prop for prop in candidate_spec.properties}
    for current_prop in current_spec.properties:
        candidate_prop = candidate_by_key.get(current_prop.key)
        if candidate_prop is None:
            add_issue(
                "property_removed",
                f"Property {current_prop.key!r} was removed.",
                node_id=node_id,
                member_key=current_prop.key,
            )
            continue
        if current_prop.type != candidate_prop.type:
            add_issue(
                "property_type_changed",
                f"Property {current_prop.key!r} changed type.",
                node_id=node_id,
                member_key=current_prop.key,
            )
            continue
        for attribute, code, label in _PROPERTY_STORAGE_FIELDS:
            if getattr(current_prop, attribute) == getattr(candidate_prop, attribute):
                continue
            add_issue(
                code,
                f"Property {current_prop.key!r} changed {label}.",
                node_id=node_id,
                member_key=current_prop.key,
            )
        if (
            current_prop.persistence_data_type_id
            and current_prop.persistence_data_type_id
            == candidate_prop.persistence_data_type_id
            and _data_type_storage_contract(current_data_types, current_prop)
            != _data_type_storage_contract(candidate_data_types, candidate_prop)
        ):
            add_issue(
                "property_data_type_storage_changed",
                f"Property {current_prop.key!r} changed its data type storage contract.",
                node_id=node_id,
                member_key=current_prop.key,
            )
        effective_value = saved_properties.get(current_prop.key, candidate_prop.default)
        if not is_saved_property_value_valid(
            candidate_prop,
            effective_value,
            data_types=candidate_data_types,
        ):
            add_issue(
                "property_value_invalid",
                f"Effective value for property {current_prop.key!r} is invalid.",
                node_id=node_id,
                member_key=current_prop.key,
            )
    for candidate_prop in candidate_spec.properties:
        if candidate_prop.key in current_by_key or is_saved_property_value_valid(
            candidate_prop,
            candidate_prop.default,
            data_types=candidate_data_types,
        ):
            continue
        add_issue(
            "new_property_default_invalid",
            f"New property {candidate_prop.key!r} has an invalid default.",
            node_id=node_id,
            member_key=candidate_prop.key,
        )


def _data_type_storage_contract(
    data_types: DataTypeCatalog,
    prop: PropertySpec,
) -> tuple[object, ...]:
    spec = data_types.require(prop.persistence_data_type_id)
    return (
        spec.persistence,
        spec.sensitivity,
        spec.carriers,
        spec.payload_schema_version,
    )


def _check_ports(
    *,
    node_id: str,
    current_ports: tuple[EffectivePort, ...],
    candidate_ports: tuple[EffectivePort, ...],
    add_issue,
) -> None:
    current_by_key = {port.key: port for port in current_ports}
    candidate_by_key = {port.key: port for port in candidate_ports}
    for key, current_port in current_by_key.items():
        candidate_port = candidate_by_key.get(key)
        if candidate_port is None:
            add_issue(
                "port_removed",
                f"Effective port {key!r} was removed.",
                node_id=node_id,
                member_key=key,
            )
            continue
        for attribute, code, label in _PORT_FIELDS:
            if getattr(current_port, attribute) != getattr(candidate_port, attribute):
                add_issue(
                    code,
                    f"Effective port {key!r} changed {label}.",
                    node_id=node_id,
                    member_key=key,
                )
    for key, candidate_port in candidate_by_key.items():
        if key in current_by_key:
            continue
        if candidate_port.direction == "out" or (
            candidate_port.direction == "in" and not candidate_port.required
        ):
            continue
        add_issue(
            (
                "required_input_added"
                if candidate_port.direction == "in" and candidate_port.required
                else "incompatible_port_added"
            ),
            f"Effective port {key!r} is not an optional input or output.",
            node_id=node_id,
            member_key=key,
        )


__all__ = [
    "RegistryCompatibilityIssue",
    "RegistryCompatibilityReport",
    "check_registry_compatibility",
]
