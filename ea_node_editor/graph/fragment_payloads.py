from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from ea_node_editor.graph.effective_ports import (
    effective_ports,
    find_port,
    ports_compatible,
    port_supports_incoming_edge,
    port_supports_outgoing_edge,
)
from ea_node_editor.graph.invariant_kernel import GraphInvariantKernel, RegistryEdgeResolution
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.graph.record_payloads import (
    edge_instance_from_mapping,
    edge_instance_to_mapping,
    node_instance_from_mapping,
    node_instance_to_mapping,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.node_specs import NodeTypeSpec

GRAPH_FRAGMENT_KIND = "ea-node-editor/graph-fragment"
GRAPH_FRAGMENT_VERSION = 2
_LEGACY_GRAPH_FRAGMENT_VERSION = 1
_RETIRED_NODE_TYPE_IDS = frozenset(
    {"core.start", "core.end", "core.branch", "core.on_failure", "hpc.on_status"}
)
_CONTROL_PORT_KEYS = frozenset(
    {
        "exec",
        "exec_in",
        "exec_out",
        "completed",
        "done",
        "failed",
        "failed_in",
        "on_completed",
        "on_failed",
        "on_failure",
        "on_other",
        "true_out",
        "false_out",
    }
)
_CONTROL_PIN_KINDS = frozenset({"exec", "completed", "failed"})


def build_graph_fragment_payload(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "kind": GRAPH_FRAGMENT_KIND,
        "version": GRAPH_FRAGMENT_VERSION,
        "nodes": nodes,
        "edges": edges,
    }


def normalize_graph_fragment_payload(
    payload: Any,
    *,
    registry: NodeRegistry | None = None,
    migration_report: list[str] | None = None,
    report_context: str = "graph fragment",
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("kind") != GRAPH_FRAGMENT_KIND:
        return None
    try:
        version = int(payload.get("version", -1))
    except (TypeError, ValueError):
        return None
    if version not in {_LEGACY_GRAPH_FRAGMENT_VERSION, GRAPH_FRAGMENT_VERSION}:
        return None

    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return None

    local_report: list[str] = []
    if version == _LEGACY_GRAPH_FRAGMENT_VERSION:
        if registry is not None:
            _reject_unresolved_legacy_fragment_nodes(
                raw_nodes,
                registry=registry,
                report_context=report_context,
            )
        raw_nodes, raw_edges = _migrate_legacy_fragment_entries(
            raw_nodes,
            raw_edges,
            report=local_report,
            report_context=report_context,
        )

    normalized_nodes: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()
    for raw_node in raw_nodes:
        normalized_node = _normalize_fragment_node_entry(raw_node)
        if normalized_node is None:
            return None
        ref_id = normalized_node["ref_id"]
        if ref_id in seen_node_ids:
            return None
        seen_node_ids.add(ref_id)
        normalized_nodes.append(normalized_node)
    if not normalized_nodes:
        _merge_sorted_report(migration_report, local_report)
        return None

    normalized_edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str, str]] = set()
    next_input_order: dict[tuple[str, str], int] = {}
    for raw_edge in raw_edges:
        target_key = (
            str(raw_edge.get("target_ref_id", "")).strip() if isinstance(raw_edge, Mapping) else "",
            str(raw_edge.get("target_port_key", "")).strip() if isinstance(raw_edge, Mapping) else "",
        )
        fallback_order = next_input_order.get(target_key, 0)
        normalized_edge = _normalize_fragment_edge_entry(raw_edge, fallback_order=fallback_order)
        if normalized_edge is None:
            return None
        next_input_order[target_key] = max(
            fallback_order,
            int(normalized_edge["input_order"]),
        ) + 1
        source_ref_id = normalized_edge["source_ref_id"]
        target_ref_id = normalized_edge["target_ref_id"]
        if source_ref_id not in seen_node_ids or target_ref_id not in seen_node_ids:
            return None
        edge_key = (
            source_ref_id,
            normalized_edge["source_port_key"],
            target_ref_id,
            normalized_edge["target_port_key"],
        )
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        normalized_edges.append(normalized_edge)

    _merge_sorted_report(migration_report, local_report)
    return build_graph_fragment_payload(nodes=normalized_nodes, edges=normalized_edges)


def normalize_edge_label(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def normalize_visual_style_payload(value: Any) -> dict[str, Any]:
    normalized = _normalize_visual_style_value(value)
    if isinstance(normalized, dict):
        return normalized
    return {}


def _normalize_fragment_node_entry(raw_node: Any) -> dict[str, Any] | None:
    if not isinstance(raw_node, dict):
        return None
    if _fragment_node_uses_retired_control(raw_node):
        return None
    node = node_instance_from_mapping(raw_node, node_id_key="ref_id", strict_payload=True)
    if node is None:
        return None
    payload = node_instance_to_mapping(node, node_id_key="ref_id")
    payload["visual_style"] = normalize_visual_style_payload(raw_node.get("visual_style"))
    return payload


def _normalize_fragment_edge_entry(raw_edge: Any, *, fallback_order: int = 0) -> dict[str, Any] | None:
    if not isinstance(raw_edge, dict):
        return None
    if (
        str(raw_edge.get("source_port_key", "")).strip() in _CONTROL_PORT_KEYS
        or str(raw_edge.get("target_port_key", "")).strip() in _CONTROL_PORT_KEYS
    ):
        return None
    edge = edge_instance_from_mapping(
        raw_edge,
        edge_id_key=None,
        source_node_id_key="source_ref_id",
        target_node_id_key="target_ref_id",
        require_edge_id=False,
    )
    if edge is None:
        return None
    payload = edge_instance_to_mapping(
        edge,
        edge_id_key=None,
        source_node_id_key="source_ref_id",
        target_node_id_key="target_ref_id",
    )
    payload["label"] = normalize_edge_label(raw_edge.get("label"))
    payload["visual_style"] = normalize_visual_style_payload(raw_edge.get("visual_style"))
    if "input_order" not in raw_edge:
        payload["input_order"] = max(0, int(fallback_order))
    return payload


def _migrate_legacy_fragment_entries(
    raw_nodes: list[Any],
    raw_edges: list[Any],
    *,
    report: list[str],
    report_context: str,
) -> tuple[list[Any], list[Any]]:
    removed_ref_ids = {
        str(raw_node.get("ref_id", "")).strip()
        for raw_node in raw_nodes
        if isinstance(raw_node, Mapping) and _fragment_node_uses_retired_control(raw_node)
    }
    removed_ref_ids.discard("")
    migrated_nodes: list[Any] = []
    for raw_node in raw_nodes:
        if not isinstance(raw_node, Mapping):
            migrated_nodes.append(raw_node)
            continue
        type_id = str(raw_node.get("type_id", "")).strip()
        properties = raw_node.get("properties")
        if _fragment_node_uses_retired_control(raw_node):
            ref_id = str(raw_node.get("ref_id", "")).strip()
            report.append(
                f"Removed retired node {ref_id or type_id} ({type_id}) from {report_context}."
            )
            continue
        node = copy.deepcopy(dict(raw_node))
        node.pop("settings_section_expanded", None)
        node.pop("advanced_section_expanded", None)
        if type_id in {"core.subnode_input", "core.subnode_output"} and isinstance(properties, Mapping):
            node["properties"] = {**dict(properties), "data_access": "item"}
        node.pop("locked_ports", None)
        for metadata_key in ("exposed_ports", "port_labels"):
            metadata = node.get(metadata_key)
            if isinstance(metadata, Mapping):
                node[metadata_key] = {
                    str(key): copy.deepcopy(value)
                    for key, value in metadata.items()
                    if str(key) not in _CONTROL_PORT_KEYS and str(key) not in removed_ref_ids
                }
        node["port_modifiers"] = {}
        node["principal_input_port_id"] = None
        migrated_nodes.append(node)

    migrated_edges: list[Any] = []
    next_input_order: dict[tuple[str, str], int] = {}
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping):
            migrated_edges.append(raw_edge)
            continue
        source_ref_id = str(raw_edge.get("source_ref_id", "")).strip()
        target_ref_id = str(raw_edge.get("target_ref_id", "")).strip()
        source_port_key = str(raw_edge.get("source_port_key", "")).strip()
        target_port_key = str(raw_edge.get("target_port_key", "")).strip()
        if (
            source_ref_id in removed_ref_ids
            or target_ref_id in removed_ref_ids
            or source_port_key in _CONTROL_PORT_KEYS
            or target_port_key in _CONTROL_PORT_KEYS
        ):
            report.append(
                "Removed control wire "
                f"{source_ref_id}.{source_port_key}->{target_ref_id}.{target_port_key} "
                f"from {report_context}."
            )
            continue
        edge = copy.deepcopy(dict(raw_edge))
        input_key = (target_ref_id, target_port_key)
        edge["enabled"] = True
        edge["input_order"] = next_input_order.get(input_key, 0)
        next_input_order[input_key] = int(edge["input_order"]) + 1
        migrated_edges.append(edge)
    return migrated_nodes, migrated_edges


def _reject_unresolved_legacy_fragment_nodes(
    raw_nodes: list[Any],
    *,
    registry: NodeRegistry,
    report_context: str,
) -> None:
    unresolved = sorted(
        {
            type_id
            for raw_node in raw_nodes
            if isinstance(raw_node, Mapping)
            and not _fragment_node_uses_retired_control(raw_node)
            and (type_id := str(raw_node.get("type_id", "")).strip())
            and registry.spec_or_none(type_id) is None
        }
    )
    if unresolved:
        raise ValueError(
            f"Legacy {report_context} contains unresolved add-ons: " + ", ".join(unresolved)
        )


def _merge_sorted_report(target: list[str] | None, entries: list[str]) -> None:
    if target is None or not entries:
        return
    target[:] = sorted(set((*target, *entries)))


def _fragment_node_uses_retired_control(raw_node: Mapping[str, Any]) -> bool:
    type_id = str(raw_node.get("type_id", "")).strip()
    properties = raw_node.get("properties")
    pin_kind = (
        str(properties.get("kind", "")).strip().lower()
        if isinstance(properties, Mapping)
        else ""
    )
    return type_id in _RETIRED_NODE_TYPE_IDS or (
        type_id in {"core.subnode_input", "core.subnode_output"}
        and pin_kind in _CONTROL_PIN_KINDS
    )


def _fragment_internal_parent_topology_is_valid(nodes_payload: list[dict[str, Any]]) -> bool:
    ref_ids = {str(node_payload.get("ref_id", "")).strip() for node_payload in nodes_payload}
    parent_by_ref_id: dict[str, str] = {}
    for node_payload in nodes_payload:
        ref_id = str(node_payload.get("ref_id", "")).strip()
        parent_id = str(node_payload.get("parent_node_id") or "").strip()
        if not ref_id or not parent_id or parent_id not in ref_ids:
            continue
        if parent_id == ref_id:
            return False
        parent_by_ref_id[ref_id] = parent_id

    for ref_id in ref_ids:
        seen = {ref_id}
        parent_id = parent_by_ref_id.get(ref_id)
        while parent_id:
            if parent_id in seen:
                return False
            seen.add(parent_id)
            parent_id = parent_by_ref_id.get(parent_id)
    return True


def _normalize_visual_style_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            normalized_key = str(key).strip()
            if not normalized_key:
                continue
            normalized[normalized_key] = _normalize_visual_style_value(child)
        return normalized
    if isinstance(value, list):
        return [_normalize_visual_style_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_visual_style_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return copy.deepcopy(value)
    return str(value)


def fragment_node_from_payload(node_payload: Mapping[str, Any]) -> NodeInstance:
    node = node_instance_from_mapping(node_payload, node_id_key="ref_id", strict_payload=True)
    if node is None:
        raise ValueError("Invalid graph fragment node payload.")
    return node


def graph_fragment_payload_is_valid(
    *,
    fragment_payload: Mapping[str, Any],
    registry: NodeRegistry,
) -> bool:
    try:
        normalized_payload = normalize_graph_fragment_payload(
            fragment_payload,
            registry=registry,
        )
    except ValueError:
        return False
    if normalized_payload is None:
        return False
    raw_nodes = normalized_payload["nodes"]
    raw_edges = normalized_payload["edges"]
    if not _fragment_internal_parent_topology_is_valid(raw_nodes):
        return False

    node_specs: dict[str, NodeTypeSpec] = {}
    fragment_nodes: dict[str, NodeInstance] = {}
    for node_payload in raw_nodes:
        ref_id = node_payload["ref_id"]
        type_id = node_payload["type_id"]
        try:
            node_specs[ref_id] = registry.get_spec(type_id)
        except KeyError:
            return False
        fragment_nodes[ref_id] = fragment_node_from_payload(node_payload)

    for ref_id, fragment_node in fragment_nodes.items():
        try:
            resolved_ports = effective_ports(
                node=fragment_node,
                spec=node_specs[ref_id],
                workspace_nodes=fragment_nodes,
            )
            for port in resolved_ports:
                if str(port.kind) != "data":
                    continue
                registry.data_types.require(str(port.data_type))
                for accepted_type_id in port.accepted_data_types:
                    registry.data_types.require(str(accepted_type_id))
        except (KeyError, ValueError):
            return False

    seen_connections: set[tuple[str, str, str, str]] = set()
    occupied_single_target_ports: set[tuple[str, str]] = set()
    for edge_payload in raw_edges:
        source_ref_id = edge_payload["source_ref_id"]
        target_ref_id = edge_payload["target_ref_id"]
        source_node = fragment_nodes.get(source_ref_id)
        target_node = fragment_nodes.get(target_ref_id)
        source_spec = node_specs.get(source_ref_id)
        target_spec = node_specs.get(target_ref_id)
        if source_node is None or target_node is None or source_spec is None or target_spec is None:
            return False
        source_port = find_port(
            node=source_node,
            spec=source_spec,
            workspace_nodes=fragment_nodes,
            port_key=edge_payload["source_port_key"],
        )
        target_port = find_port(
            node=target_node,
            spec=target_spec,
            workspace_nodes=fragment_nodes,
            port_key=edge_payload["target_port_key"],
        )
        if source_port is None or target_port is None:
            return False
        if (
            not port_supports_outgoing_edge(source_port)
            or not port_supports_incoming_edge(target_port)
            or not ports_compatible(
                source_port,
                target_port,
                data_types=registry.data_types,
            )
        ):
            return False
        if not GraphInvariantKernel.accept_registry_edge(
            RegistryEdgeResolution(
                source_node_id=source_ref_id,
                source_port_key=edge_payload["source_port_key"],
                target_node_id=target_ref_id,
                target_port_key=edge_payload["target_port_key"],
                source_port=source_port,
                target_port=target_port,
            ),
            seen_connections=seen_connections,
            occupied_single_target_ports=occupied_single_target_ports,
        ):
            return False
    return True


__all__ = [
    "GRAPH_FRAGMENT_KIND",
    "GRAPH_FRAGMENT_VERSION",
    "build_graph_fragment_payload",
    "fragment_node_from_payload",
    "graph_fragment_payload_is_valid",
    "normalize_edge_label",
    "normalize_graph_fragment_payload",
    "normalize_visual_style_payload",
]
