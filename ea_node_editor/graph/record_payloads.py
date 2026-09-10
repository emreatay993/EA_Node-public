from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from ea_node_editor.graph.node_comments import node_comments_from_payload, node_comments_to_payload
from ea_node_editor.graph.node_links import node_links_from_payload, node_links_to_payload
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.runtime_contracts import (
    DATA_TREE_MODIFIER_ORDER,
    DataTypeCatalog,
    deserialize_runtime_value,
    serialize_runtime_value,
)


def _coerce_str(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else default
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _try_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_nonnegative_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _as_mapping(value: Any, *, strict: bool = False) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None if strict else {}
    return {str(key): item for key, item in value.items()}


def _normalize_port_modifiers(value: Any, *, strict: bool = False) -> dict[str, tuple[str, ...]] | None:
    if not isinstance(value, Mapping):
        return None if strict else {}
    normalized: dict[str, tuple[str, ...]] = {}
    for raw_port_key, raw_modifiers in value.items():
        port_key = str(raw_port_key).strip()
        if not port_key or not isinstance(raw_modifiers, (list, tuple)):
            if strict:
                return None
            continue
        requested = {str(modifier).strip().lower() for modifier in raw_modifiers}
        if strict and requested.difference(DATA_TREE_MODIFIER_ORDER):
            return None
        modifiers = tuple(modifier for modifier in DATA_TREE_MODIFIER_ORDER if modifier in requested)
        if modifiers:
            normalized[port_key] = modifiers
    return normalized


def _normalize_string_tuple(value: Any, *, strict: bool = False) -> tuple[str, ...] | None:
    if not isinstance(value, (list, tuple)):
        return None if strict else ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            if strict:
                return None
            continue
        token = item.strip()
        if token not in seen:
            normalized.append(token)
            seen.add(token)
    return tuple(normalized)


def node_instance_from_mapping(
    payload: Mapping[str, Any],
    *,
    node_id_key: str = "node_id",
    strict_payload: bool = False,
    source_workspace_id: str = "",
    data_types: DataTypeCatalog | None = None,
) -> NodeInstance | None:
    node_id = _coerce_str(payload.get(node_id_key))
    type_id = _coerce_str(payload.get("type_id"))
    if not node_id or not type_id:
        return None
    x = _try_float(payload.get("x", 0.0))
    y = _try_float(payload.get("y", 0.0))
    if strict_payload and (x is None or y is None):
        return None
    custom_width = None
    if payload.get("custom_width") is not None:
        custom_width = _try_float(payload.get("custom_width"))
        if strict_payload and custom_width is None:
            return None
    custom_height = None
    if payload.get("custom_height") is not None:
        custom_height = _try_float(payload.get("custom_height"))
        if strict_payload and custom_height is None:
            return None
    raw_properties = _as_mapping(payload.get("properties", {}), strict=strict_payload)
    raw_exposed_ports = _as_mapping(payload.get("exposed_ports", {}), strict=strict_payload)
    raw_port_labels = _as_mapping(payload.get("port_labels", {}), strict=strict_payload)
    raw_port_modifiers = _normalize_port_modifiers(payload.get("port_modifiers", {}), strict=strict_payload)
    expanded_settings_group_ids = _normalize_string_tuple(
        payload.get("expanded_settings_group_ids", ()),
        strict=strict_payload,
    )
    if (
        raw_properties is None
        or raw_exposed_ports is None
        or raw_port_labels is None
        or raw_port_modifiers is None
        or expanded_settings_group_ids is None
    ):
        return None
    normalized_properties = deserialize_runtime_value(
        raw_properties,
        catalog=data_types,
    )
    if not isinstance(normalized_properties, Mapping):
        return None
    normalized_exposed_ports: dict[str, bool] = {}
    for key, value in raw_exposed_ports.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            if strict_payload:
                return None
            continue
        normalized_exposed_ports[normalized_key] = bool(value)
    parent_node_id = _coerce_str(payload.get("parent_node_id")) or None
    return NodeInstance(
        node_id=node_id,
        type_id=type_id,
        title=_coerce_str(payload.get("title"), type_id),
        x=0.0 if x is None else x,
        y=0.0 if y is None else y,
        collapsed=bool(payload.get("collapsed", False)),
        expanded_settings_group_ids=expanded_settings_group_ids,
        locked=bool(payload.get("locked", False)),
        properties={str(key): value for key, value in normalized_properties.items()},
        exposed_ports=normalized_exposed_ports,
        port_labels={str(k): str(v) for k, v in raw_port_labels.items() if str(v).strip()},
        port_modifiers=raw_port_modifiers,
        principal_input_port_id=_coerce_str(payload.get("principal_input_port_id")) or None,
        visual_style=_as_mapping(payload.get("visual_style")) or {},
        links=node_links_from_payload(payload.get("links", []), source_workspace_id=source_workspace_id),
        comments=node_comments_from_payload(payload.get("comments", [])),
        parent_node_id=parent_node_id,
        custom_width=custom_width,
        custom_height=custom_height,
    )


def node_instance_to_mapping(
    node: NodeInstance,
    *,
    node_id_key: str = "node_id",
    source_workspace_id: str = "",
    data_types: DataTypeCatalog | None = None,
    properties_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        node_id_key: node.node_id,
        "type_id": node.type_id,
        "title": node.title,
        "x": node.x,
        "y": node.y,
        "collapsed": node.collapsed,
        "expanded_settings_group_ids": list(node.expanded_settings_group_ids),
        "locked": node.locked,
        "properties": serialize_runtime_value(
            node.properties if properties_override is None else properties_override,
            catalog=data_types,
        ),
        "exposed_ports": copy.deepcopy(node.exposed_ports),
        "port_labels": copy.deepcopy(node.port_labels),
        "port_modifiers": {
            port_key: list(modifiers)
            for port_key, modifiers in node.port_modifiers.items()
            if modifiers
        },
        "principal_input_port_id": node.principal_input_port_id,
        "visual_style": copy.deepcopy(node.visual_style),
        "links": node_links_to_payload(list(node.links), source_workspace_id=source_workspace_id),
        "comments": node_comments_to_payload(list(node.comments)),
        "parent_node_id": node.parent_node_id,
        "custom_width": node.custom_width,
        "custom_height": node.custom_height,
    }


def edge_instance_from_mapping(
    payload: Mapping[str, Any],
    *,
    edge_id_key: str | None = "edge_id",
    source_node_id_key: str = "source_node_id",
    target_node_id_key: str = "target_node_id",
    require_edge_id: bool = True,
) -> EdgeInstance | None:
    edge_id = _coerce_str(payload.get(edge_id_key)) if edge_id_key is not None else ""
    source_node_id = _coerce_str(payload.get(source_node_id_key))
    source_port_key = _coerce_str(payload.get("source_port_key"))
    target_node_id = _coerce_str(payload.get(target_node_id_key))
    target_port_key = _coerce_str(payload.get("target_port_key"))
    if (
        (require_edge_id and not edge_id)
        or not source_node_id
        or not source_port_key
        or not target_node_id
        or not target_port_key
    ):
        return None
    return EdgeInstance(
        edge_id=edge_id,
        source_node_id=source_node_id,
        source_port_key=source_port_key,
        target_node_id=target_node_id,
        target_port_key=target_port_key,
        enabled=_coerce_bool(payload.get("enabled", True), True),
        input_order=_coerce_nonnegative_int(payload.get("input_order", 0)),
        label=_coerce_str(payload.get("label")),
        visual_style=_as_mapping(payload.get("visual_style")) or {},
    )


def edge_instance_to_mapping(
    edge: EdgeInstance,
    *,
    edge_id_key: str | None = "edge_id",
    source_node_id_key: str = "source_node_id",
    target_node_id_key: str = "target_node_id",
) -> dict[str, Any]:
    payload = {
        source_node_id_key: edge.source_node_id,
        "source_port_key": edge.source_port_key,
        target_node_id_key: edge.target_node_id,
        "target_port_key": edge.target_port_key,
        "enabled": edge.enabled,
        "input_order": edge.input_order,
        "label": edge.label,
        "visual_style": copy.deepcopy(edge.visual_style),
    }
    if edge_id_key is not None:
        payload = {edge_id_key: edge.edge_id, **payload}
    return payload


__all__ = [
    "edge_instance_from_mapping",
    "edge_instance_to_mapping",
    "node_instance_from_mapping",
    "node_instance_to_mapping",
]
