# Purpose: Match and rank canvas and connection Quick Insert candidates.
# Map: feature_routes/workspace_tabs_library_context_menus.md
# Tests: tests/test_quick_insert_projection.py

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ea_node_editor.graph.effective_ports import port_compatibility
from ea_node_editor.nodes.node_specs import PortSpec
from ea_node_editor.runtime_contracts import (
    CONNECTION_FALLBACK_CAPABILITY,
    DataTypeCatalog,
    DataTypeCompatibility,
)
from ea_node_editor.ui.shell.library_projection import (
    projected_port_declared_data_types,
)

_COMPATIBILITY_LABELS = {
    "exact": "Exact type",
    "assignable": "Compatible type",
    "convertible": "Converts automatically",
    "flow": "Flow",
    "generic": "Broad data match",
    "runtime_check": "Checked at runtime",
}
_COMPATIBILITY_TIERS = {kind: index for index, kind in enumerate(_COMPATIBILITY_LABELS)}


def _compatibility_kind(result: DataTypeCompatibility, data_types: DataTypeCatalog) -> str:
    if not result.is_compatible:
        return ""
    if result.reason_code == "flow_kind_match":
        return "flow"
    if result.status == "runtime_check":
        return "runtime_check"
    matched_type = data_types.get(result.matched_type_id)
    if matched_type is not None and CONNECTION_FALLBACK_CAPABILITY in matched_type.capabilities:
        return "generic"
    if result.status == "convertible":
        return "convertible"
    return "exact" if result.reason_code == "exact" else "assignable"


def _normalized_library_ports(item: dict[str, Any]) -> list[dict[str, Any]]:
    ports = item.get("ports", [])
    if not isinstance(ports, list):
        return []
    return [port for port in ports if isinstance(port, dict)]


def _library_item_matches_query(
    item: dict[str, Any], *, query: str, compatible_ports: list[dict[str, Any]]
) -> bool:
    normalized_query = str(query).strip().lower()
    if not normalized_query:
        return True
    haystack = " ".join(
        [
            str(item.get("type_id", "")),
            str(item.get("display_name", "")),
            str(item.get("category", "")),
            str(item.get("category_display", "")),
            str(item.get("description", "")),
            " ".join(str(port.get("key", "")) for port in compatible_ports),
            " ".join(str(port.get("label", "")) for port in compatible_ports),
        ]
    ).lower()
    return normalized_query in haystack


def _is_neutral_flow_library_port(port: dict[str, Any]) -> bool:
    direction = str(port.get("direction", "")).strip().lower()
    kind = str(port.get("kind", "")).strip().lower()
    data_type = str(port.get("data_type", "")).strip().lower()
    return direction == "neutral" and kind == "flow" and data_type == "flow"


def _library_port_spec(port: Mapping[str, Any]) -> PortSpec | None:
    declared_types = projected_port_declared_data_types(port)
    if not declared_types:
        return None
    return PortSpec(
        key=str(port.get("key", "")).strip(),
        direction=str(port.get("direction", "")).strip().lower(),
        kind=str(port.get("kind", "")).strip().lower(),
        data_type=declared_types[0],
        label=str(port.get("label", "")).strip(),
        exposed=bool(port.get("exposed", True)),
        accepted_data_types=declared_types[1:],
    )


def _compatible_library_ports(
    item: dict[str, Any],
    *,
    data_types: DataTypeCatalog,
    source_direction: str,
    source_kind: str,
    source_data_type: str,
    source_accepted_data_types: Iterable[str] = (),
) -> list[dict[str, Any]]:
    normalized_source_direction = str(source_direction).strip().lower()
    normalized_source_kind = str(source_kind).strip().lower()
    source_declared_types = projected_port_declared_data_types({
        "data_type": source_data_type,
        "accepted_data_types": tuple(source_accepted_data_types),
    })
    if not source_declared_types:
        return []
    normalized_source_data_type = source_declared_types[0]
    normalized_source_accepted_data_types = source_declared_types[1:]
    source_is_neutral_flow = (
        normalized_source_direction == "neutral"
        and normalized_source_kind == "flow"
        and normalized_source_data_type == "flow"
    )
    source_port = PortSpec(
        key="source",
        direction=normalized_source_direction,
        kind=normalized_source_kind,
        data_type=normalized_source_data_type,
        accepted_data_types=normalized_source_accepted_data_types,
    )
    compatible_ports: list[dict[str, Any]] = []
    best_tier = len(_COMPATIBILITY_TIERS)
    for port in _normalized_library_ports(item):
        candidate_port = _library_port_spec(port)
        if candidate_port is None or not candidate_port.exposed:
            continue
        if source_is_neutral_flow:
            if not _is_neutral_flow_library_port(port):
                continue
            source, target = source_port, candidate_port
        elif normalized_source_direction == "out":
            if candidate_port.direction != "in":
                continue
            source, target = source_port, candidate_port
        elif normalized_source_direction == "in":
            if candidate_port.direction != "out":
                continue
            source, target = candidate_port, source_port
        else:
            continue
        compatibility = port_compatibility(source, target, data_types=data_types)
        kind = _compatibility_kind(compatibility, data_types)
        if not kind:
            continue
        tier = _COMPATIBILITY_TIERS[kind]
        if tier > best_tier:
            continue
        if tier < best_tier:
            compatible_ports.clear()
            best_tier = tier
        compatible_ports.append({
            **port,
            "compatibility_kind": kind,
            "compatibility_label": _COMPATIBILITY_LABELS[kind],
            "matched_data_type": compatibility.matched_type_id,
        })
    return compatible_ports


def _connection_quick_insert_rank(
    query: str, *, display_name: str, type_id: str
) -> int:
    normalized_query = str(query).strip().lower()
    if not normalized_query:
        return 100
    name = str(display_name).strip().lower()
    node_type_id = str(type_id).strip().lower()
    if name == normalized_query:
        return 0
    if name.startswith(normalized_query):
        return 10
    if normalized_query in name:
        return 20
    if node_type_id.startswith(normalized_query):
        return 30
    if normalized_query in node_type_id:
        return 40
    return 100


def build_connection_quick_insert_items(
    *,
    combined_items: Iterable[dict[str, Any]],
    data_types: DataTypeCatalog,
    query: str,
    source_direction: str,
    source_kind: str,
    source_data_type: str,
    source_accepted_data_types: Iterable[str] = (),
    limit: int = 12,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    source_accepted_data_types = tuple(source_accepted_data_types)
    include_fallbacks = bool(str(query).strip())
    for item in combined_items:
        compatible_ports = _compatible_library_ports(
            item,
            data_types=data_types,
            source_direction=source_direction,
            source_kind=source_kind,
            source_data_type=source_data_type,
            source_accepted_data_types=source_accepted_data_types,
        )
        if not compatible_ports:
            continue
        compatibility_kind = compatible_ports[0]["compatibility_kind"]
        if not include_fallbacks and compatibility_kind in {"generic", "runtime_check"}:
            continue
        if not _library_item_matches_query(
            item, query=query, compatible_ports=compatible_ports
        ):
            continue
        payload = dict(item)
        payload["compatible_ports"] = compatible_ports
        payload["compatible_port_labels"] = [
            str(port.get("label", "")).strip() or str(port.get("key", "")).strip()
            for port in compatible_ports
        ]
        payload["compatible_port_count"] = len(compatible_ports)
        payload["compatibility_kind"] = compatibility_kind
        payload["compatibility_label"] = _COMPATIBILITY_LABELS[compatibility_kind]
        payload["compatible_port_summaries"] = [
            f"{label} — {port['compatibility_label']}"
            for label, port in zip(payload["compatible_port_labels"], compatible_ports, strict=True)
        ]
        normalized_source_direction = str(source_direction).strip().lower()
        if normalized_source_direction == "out":
            payload["compatible_direction"] = "in"
        elif normalized_source_direction == "in":
            payload["compatible_direction"] = "out"
        else:
            payload["compatible_direction"] = "neutral"
        ranked.append(payload)
    ranked.sort(
        key=lambda item: (
            _connection_quick_insert_rank(query, display_name=str(item.get("display_name", "")), type_id=str(item.get("type_id", ""))),
            _COMPATIBILITY_TIERS[item["compatibility_kind"]],
            max(0, item["compatible_port_count"] - 1),
            str(item.get("display_name", "")).casefold(),
            str(item.get("type_id", "")).casefold(),
        )
    )
    capped = max(1, int(limit))
    return ranked[:capped]


def build_canvas_quick_insert_items(
    *,
    combined_items: Iterable[dict[str, Any]],
    query: str,
    limit: int = 12,
) -> list[dict[str, Any]]:
    normalized_query = str(query).strip()
    if not normalized_query:
        return []
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for item in combined_items:
        if not _library_item_matches_query(
            item, query=normalized_query, compatible_ports=[]
        ):
            continue
        payload = dict(item)
        payload["compatible_ports"] = []
        payload["compatible_port_labels"] = []
        payload["compatible_port_count"] = 0
        payload["compatible_direction"] = ""
        ranked.append(
            (
                _connection_quick_insert_rank(
                    normalized_query,
                    display_name=str(item.get("display_name", "")),
                    type_id=str(item.get("type_id", "")),
                ),
                str(item.get("display_name", "")).lower(),
                payload,
            )
        )
    ranked.sort(
        key=lambda entry: (entry[0], entry[1], str(entry[2].get("type_id", "")).lower())
    )
    capped = max(1, int(limit))
    return [entry[2] for entry in ranked[:capped]]
