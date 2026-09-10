from __future__ import annotations

import copy
from dataclasses import dataclass, field
import uuid
from collections.abc import Mapping
from typing import Any

from ea_node_editor.graph.fragment_payloads import normalize_graph_fragment_payload

from ea_node_editor.nodes.category_paths import (
    category_display,
    category_key,
    normalize_category_path,
)
from ea_node_editor.nodes.registry import NodeRegistry


CUSTOM_WORKFLOW_LIBRARY_CATEGORY = "Custom Workflows"
CUSTOM_WORKFLOW_LIBRARY_CATEGORY_PATH = normalize_category_path((CUSTOM_WORKFLOW_LIBRARY_CATEGORY,))
_CUSTOM_WORKFLOW_TYPE_PREFIX = "custom_workflow:"


@dataclass(slots=True)
class CustomWorkflowDefinition:
    workflow_id: str
    name: str
    description: str = ""
    revision: int = 1
    ports: list[dict[str, Any]] = field(default_factory=list)
    fragment: dict[str, Any] = field(default_factory=dict)


def normalize_custom_workflow_metadata(
    value: Any,
    *,
    registry: NodeRegistry | None = None,
    migration_report: list[str] | None = None,
) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    raw_items = value if isinstance(value, list) else []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        workflow_id = str(raw_item.get("workflow_id", "")).strip()
        name = str(raw_item.get("name", "")).strip()
        if not workflow_id or not name or workflow_id in seen_ids:
            continue
        seen_ids.add(workflow_id)
        workflow_report: list[str] = []
        raw_fragment = raw_item.get("fragment", {})
        fragment = normalize_graph_fragment_payload(
            copy.deepcopy(raw_fragment),
            registry=registry,
            migration_report=workflow_report,
            report_context=f"custom workflow {workflow_id}",
        )
        if fragment is None:
            if workflow_report:
                workflow_report.append(f"Removed empty custom workflow {workflow_id}.")
                _merge_sorted_report(migration_report, workflow_report)
            continue
        ports = copy.deepcopy(raw_item.get("ports", []))
        if not isinstance(ports, list):
            ports = []
        if _fragment_version(raw_fragment) == 1:
            for raw_port in ports:
                if not isinstance(raw_port, Mapping):
                    continue
                kind = str(raw_port.get("kind", "")).strip().lower()
                if kind in {"exec", "completed", "failed"}:
                    key = str(raw_port.get("key", "")).strip() or kind
                    workflow_report.append(
                        f"Removed control port {key} from custom workflow {workflow_id}."
                    )
        definitions.append(
            {
                "workflow_id": workflow_id,
                "name": name,
                "description": str(raw_item.get("description", "")).strip(),
                "revision": _coerce_int(raw_item.get("revision", 1), default=1),
                "ports": _normalize_port_preview_list(ports),
                "fragment": fragment,
            }
        )
        _merge_sorted_report(migration_report, workflow_report)
    return definitions


def custom_workflow_type_id(workflow_id: object) -> str:
    normalized_workflow_id = str(workflow_id).strip()
    if not normalized_workflow_id:
        return ""
    return f"{_CUSTOM_WORKFLOW_TYPE_PREFIX}{normalized_workflow_id}"


def parse_custom_workflow_type_id(type_id: object) -> str | None:
    normalized_type_id = str(type_id).strip()
    if not normalized_type_id.startswith(_CUSTOM_WORKFLOW_TYPE_PREFIX):
        return None
    workflow_id = normalized_type_id[len(_CUSTOM_WORKFLOW_TYPE_PREFIX) :].strip()
    if not workflow_id:
        return None
    return workflow_id


def find_custom_workflow_definition(value: Any, workflow_id: object) -> dict[str, Any] | None:
    normalized_workflow_id = str(workflow_id).strip()
    if not normalized_workflow_id:
        return None
    definitions = normalize_custom_workflow_metadata(value)
    for definition in definitions:
        if definition["workflow_id"] == normalized_workflow_id:
            return copy.deepcopy(definition)
    return None


def custom_workflow_library_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    category_display_text = category_display(CUSTOM_WORKFLOW_LIBRARY_CATEGORY_PATH)
    category_key_text = category_key(CUSTOM_WORKFLOW_LIBRARY_CATEGORY_PATH)
    for definition in normalize_custom_workflow_metadata(value):
        workflow_id = definition["workflow_id"]
        items.append(
            {
                "type_id": custom_workflow_type_id(workflow_id),
                "display_name": definition["name"],
                "category_path": CUSTOM_WORKFLOW_LIBRARY_CATEGORY_PATH,
                "category_key": category_key_text,
                "category_display": category_display_text,
                "root_category": CUSTOM_WORKFLOW_LIBRARY_CATEGORY_PATH[0],
                "category": category_display_text,
                "icon": "account_tree",
                "description": definition["description"],
                "ports": copy.deepcopy(definition["ports"]),
                "workflow_id": workflow_id,
                "revision": int(definition.get("revision", 1)),
                "library_source": "custom_workflow",
            }
        )
    items.sort(key=lambda item: (str(item["display_name"]).lower(), str(item["workflow_id"]).lower()))
    return items


def upsert_custom_workflow_definition(
    value: Any,
    *,
    name: object,
    ports: list[dict[str, Any]] | None,
    fragment: dict[str, Any] | None,
    description: object = "",
    workflow_id: object | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    definitions = normalize_custom_workflow_metadata(value)
    normalized_name = _coerce_workflow_name(name)
    normalized_description = str(description).strip()
    normalized_ports = _normalize_port_preview_list(
        list(ports or []), reject_invalid_data_types=True
    )
    normalized_fragment = normalize_graph_fragment_payload(
        copy.deepcopy(fragment if isinstance(fragment, Mapping) else {})
    )
    if normalized_fragment is None:
        raise ValueError("Custom workflow fragment is invalid or empty.")
    normalized_workflow_id = str(workflow_id).strip() if workflow_id is not None else ""

    target_index = -1
    if normalized_workflow_id:
        for index, definition in enumerate(definitions):
            if definition["workflow_id"] == normalized_workflow_id:
                target_index = index
                break

    if target_index < 0:
        if not normalized_workflow_id:
            normalized_workflow_id = _next_custom_workflow_id(definitions)
        created = {
            "workflow_id": normalized_workflow_id,
            "name": normalized_name,
            "description": normalized_description,
            "revision": 1,
            "ports": normalized_ports,
            "fragment": normalized_fragment,
        }
        definitions.append(created)
        return definitions, copy.deepcopy(created)

    existing = definitions[target_index]
    updated = {
        "workflow_id": normalized_workflow_id or existing["workflow_id"],
        "name": normalized_name,
        "description": normalized_description,
        "revision": _coerce_int(existing.get("revision", 1), default=1) + 1,
        "ports": normalized_ports,
        "fragment": normalized_fragment,
    }
    definitions[target_index] = updated
    return definitions, copy.deepcopy(updated)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fragment_version(value: Any) -> int:
    if not isinstance(value, Mapping):
        return -1
    return _coerce_int(value.get("version"), default=-1)


def _merge_sorted_report(target: list[str] | None, entries: list[str]) -> None:
    if target is None or not entries:
        return
    target[:] = sorted(set((*target, *entries)))


def _normalize_port_preview_list(
    items: list[Any], *, reject_invalid_data_types: bool = False
) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        label = str(item.get("label", "")).strip() or key
        direction = str(item.get("direction", "")).strip()
        kind = str(item.get("kind", "")).strip()
        raw_data_type = item.get("data_type")
        if not isinstance(raw_data_type, str) or not raw_data_type.strip():
            if kind == "data" and reject_invalid_data_types:
                raise ValueError(
                    f"Custom workflow data port {key!r} requires a non-empty data_type string."
                )
            continue
        data_type = raw_data_type.strip()
        raw_accepted_data_types = item.get("accepted_data_types", ())
        accepted_data_types: list[str] = []
        seen_data_types = {data_type}
        if isinstance(raw_accepted_data_types, (list, tuple)):
            for raw_data_type in raw_accepted_data_types:
                if not isinstance(raw_data_type, str):
                    continue
                accepted_data_type = raw_data_type.strip()
                if (
                    not accepted_data_type
                    or accepted_data_type in seen_data_types
                ):
                    continue
                accepted_data_types.append(accepted_data_type)
                seen_data_types.add(accepted_data_type)
        data_access = str(item.get("data_access", "item")).strip().lower()
        if (
            not key
            or direction not in {"in", "out"}
            or kind not in {"data", "flow"}
            or data_access not in {"item", "list", "tree"}
        ):
            continue
        normalized = {
            "key": key,
            "label": label,
            "direction": direction,
            "kind": kind,
            "data_type": data_type,
            "accepted_data_types": accepted_data_types,
            "data_access": data_access,
        }
        node_ref_id = str(item.get("node_ref_id", "")).strip()
        port_key = str(item.get("port_key", "")).strip()
        if node_ref_id and port_key:
            normalized["node_ref_id"] = node_ref_id
            normalized["port_key"] = port_key
        preview.append(normalized)
    return preview


def _coerce_workflow_name(value: object) -> str:
    normalized_name = str(value).strip()
    if not normalized_name:
        return "Custom Workflow"
    return normalized_name


def _next_custom_workflow_id(definitions: list[dict[str, Any]]) -> str:
    used_ids = {str(definition.get("workflow_id", "")).strip() for definition in definitions}
    used_ids.discard("")
    for _ in range(24):
        candidate = f"wf_{uuid.uuid4().hex[:10]}"
        if candidate not in used_ids:
            return candidate
    fallback_index = 1
    while True:
        candidate = f"wf_{fallback_index:04d}"
        if candidate not in used_ids:
            return candidate
        fallback_index += 1
