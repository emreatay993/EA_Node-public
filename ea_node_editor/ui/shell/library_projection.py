# Purpose: Project registry and workflow nodes into Library rows, filters, and category views.
# Map: feature_routes/workspace_tabs_library_context_menus.md
# Tests: tests/test_library_projection.py

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from ea_node_editor.nodes.category_paths import (
    CategoryPath,
    category_display,
    category_key,
    category_path_ancestors,
    category_path_matches_prefix,
    normalize_category_path,
)
from ea_node_editor.custom_workflows import CUSTOM_WORKFLOW_LIBRARY_CATEGORY
from ea_node_editor.graph.effective_ports import ordered_ports_for_display
from ea_node_editor.nodes.instance_resolution import resolve_instance_ports
from ea_node_editor.runtime_contracts import DataTypeCatalog
from ea_node_editor.ui.support.node_presentation import (
    project_port_data_type_presentation,
)

_DEFAULT_LIBRARY_CATEGORY = "Other"
_CUSTOM_WORKFLOW_LIBRARY_CATEGORY_PATH = (CUSTOM_WORKFLOW_LIBRARY_CATEGORY,)
_GRAPH_SURFACE_METRIC_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "ui_qml"
    / "components"
    / "graph"
    / "GraphNodeSurfaceMetricContract.json"
)
_FALLBACK_FLOWCHART_LIBRARY_ASPECT_RATIOS = {
    "start": 152.0 / 78.0,
    "end": 152.0 / 78.0,
    "process": 156.0 / 84.0,
    "decision": 192.0 / 128.0,
    "document": 176.0 / 104.0,
    "connector": 1.0,
    "input_output": 182.0 / 94.0,
    "predefined_process": 182.0 / 94.0,
    "database": 180.0 / 128.0,
    "card": 132.0 / 200.0,
    "callout": 196.0 / 120.0,
    "multi_document": 176.0 / 128.0,
    "tick": 1.0,
    "timestamp": 220.0 / 72.0,
    "message": 160.0 / 112.0,
    "isometric_cube": 1.0,
    "cube": 220.0 / 132.0,
    "actor": 116.0 / 156.0,
    "star": 1.0,
    "x": 1.0,
}


def _positive_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    return numeric


@lru_cache(maxsize=1)
def _flowchart_library_aspect_ratios() -> dict[str, float]:
    ratios = dict(_FALLBACK_FLOWCHART_LIBRARY_ASPECT_RATIOS)
    try:
        contract = json.loads(
            _GRAPH_SURFACE_METRIC_CONTRACT_PATH.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return ratios

    flowchart = contract.get("flowchart", {})
    variants = flowchart.get("variants", {}) if isinstance(flowchart, Mapping) else {}
    if not isinstance(variants, Mapping):
        return ratios

    for variant, metrics in variants.items():
        if not isinstance(metrics, Mapping):
            continue
        default_width = _positive_float(metrics.get("default_width"))
        min_height = _positive_float(metrics.get("min_height"))
        if default_width is None or min_height is None:
            continue
        ratios[str(variant)] = default_width / min_height
    return ratios


def _flowchart_library_aspect_ratio(surface_variant: str) -> float:
    return float(_flowchart_library_aspect_ratios().get(surface_variant, 1.7))


def projected_port_declared_data_types(port: Mapping[str, Any]) -> tuple[str, ...]:
    raw_primary = port.get("data_type")
    if not isinstance(raw_primary, str) or not raw_primary.strip():
        return ()
    primary = raw_primary.strip()
    raw_accepted = port.get("accepted_data_types", ())
    accepted = raw_accepted if isinstance(raw_accepted, (list, tuple)) else ()
    return tuple(
        dict.fromkeys(
            (
                primary,
                *(value.strip() for value in accepted if isinstance(value, str) and value.strip()),
            )
        )
    )


def _category_sort_key(path: Iterable[str]) -> tuple[tuple[str, ...], CategoryPath]:
    normalized_path = normalize_category_path(tuple(path))
    return tuple(segment.casefold() for segment in normalized_path), normalized_path


def _category_metadata(path: Iterable[str]) -> dict[str, Any]:
    normalized_path = normalize_category_path(tuple(path))
    display = category_display(normalized_path)
    key = category_key(normalized_path)
    return {
        "category_path": normalized_path,
        "category_key": key,
        "category_display": display,
        "root_category": normalized_path[0],
        "category": display,
    }


def _category_path_from_item(item: Mapping[str, Any]) -> CategoryPath:
    raw_path = item.get("category_path")
    if raw_path is not None and not isinstance(raw_path, str):
        try:
            return normalize_category_path(tuple(raw_path))
        except (TypeError, ValueError):
            pass

    fallback_category = str(
        item.get("category_display")
        or item.get("category")
        or (
            CUSTOM_WORKFLOW_LIBRARY_CATEGORY
            if str(item.get("library_source", "")).strip() == "custom_workflow"
            else _DEFAULT_LIBRARY_CATEGORY
        )
    ).strip()
    return normalize_category_path((fallback_category or _DEFAULT_LIBRARY_CATEGORY,))


def _project_library_item_payload(
    item: Mapping[str, Any],
    *,
    data_type_projection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(item)
    payload.update(_category_metadata(_category_path_from_item(payload)))
    ports = payload.get("ports", [])
    projected_ports: list[Any] = []
    for port in ports if isinstance(ports, list) else ():
        if not isinstance(port, Mapping):
            continue
        declared_types = projected_port_declared_data_types(port)
        if not declared_types:
            continue
        projected_port = dict(port)
        projected_port["data_type"] = declared_types[0]
        projected_port["accepted_data_types"] = list(declared_types[1:])
        if data_type_projection is not None or "catalog_generation" not in port:
            projected_port.update(
                project_port_data_type_presentation(
                    data_type=declared_types[0],
                    accepted_data_types=declared_types[1:],
                    data_access=port.get("data_access", "item"),
                    kind=port.get("kind", "data"),
                    projection=data_type_projection,
                )
            )
        projected_ports.append(projected_port)
    payload["ports"] = projected_ports
    library_visual = payload.get("library_visual")
    payload["library_visual"] = (
        dict(library_visual)
        if isinstance(library_visual, Mapping)
        else {"kind": "none"}
    )
    return payload


def _library_visual_from_spec(spec: Any) -> dict[str, Any]:
    runtime_behavior = str(getattr(spec, "runtime_behavior", "") or "").strip().lower()
    surface_family = str(getattr(spec, "surface_family", "") or "").strip().lower()
    surface_variant = str(getattr(spec, "surface_variant", "") or "").strip().lower()
    icon = str(getattr(spec, "icon", "") or "").strip()
    visual: dict[str, Any] = {
        "kind": "none",
        "runtime_behavior": runtime_behavior,
        "surface_family": surface_family,
        "surface_variant": surface_variant,
        "shape_id": "",
        "icon": icon,
    }
    if runtime_behavior != "passive":
        if icon:
            visual["kind"] = "catalog_icon"
        return visual
    if surface_family == "flowchart" and surface_variant:
        visual["kind"] = "flowchart_shape"
        visual["shape_id"] = surface_variant
        visual["icon"] = ""
        visual["aspect_ratio"] = _flowchart_library_aspect_ratio(surface_variant)
        return visual
    if icon:
        visual["kind"] = "catalog_icon"
    return visual


def _is_passive_library_item(item: Mapping[str, Any]) -> bool:
    return str(item.get("runtime_behavior", "") or "").strip().lower() == "passive"


def _category_filter_prefix(value: str) -> CategoryPath | None:
    normalized_value = str(value or "").strip()
    if not normalized_value:
        return None
    try:
        decoded = json.loads(normalized_value)
    except json.JSONDecodeError:
        return None
    if isinstance(decoded, list):
        try:
            return normalize_category_path(tuple(decoded))
        except (TypeError, ValueError):
            return None
    return None


def _item_matches_category_filter(item: Mapping[str, Any], category: str) -> bool:
    normalized_category = str(category or "").strip()
    if not normalized_category:
        return True

    item_path = _category_path_from_item(item)
    prefix = _category_filter_prefix(normalized_category)
    if prefix is not None:
        return category_path_matches_prefix(item_path, prefix)

    category_display_filter = normalized_category.casefold()
    return any(
        category_display(ancestor).casefold() == category_display_filter
        for ancestor in category_path_ancestors(item_path)
    )


def _ancestor_category_keys(path: Iterable[str], *, include_self: bool) -> list[str]:
    ancestors = list(category_path_ancestors(normalize_category_path(tuple(path))))
    if not include_self:
        ancestors = ancestors[:-1]
    return [category_key(ancestor) for ancestor in ancestors]


def _category_row(path: Iterable[str]) -> dict[str, Any]:
    normalized_path = normalize_category_path(tuple(path))
    payload = _category_metadata(normalized_path)
    payload.update(
        {
            "kind": "category",
            "label": normalized_path[-1],
            "depth": len(normalized_path) - 1,
            "ancestor_category_keys": _ancestor_category_keys(
                normalized_path, include_self=False
            ),
        }
    )
    return payload


def _node_row(item: Mapping[str, Any]) -> dict[str, Any]:
    payload = _project_library_item_payload(item)
    category_path = _category_path_from_item(payload)
    payload.update(
        {
            "kind": "node",
            "label": str(payload.get("display_name", "")).strip(),
            "depth": len(category_path),
            "ancestor_category_keys": _ancestor_category_keys(
                category_path, include_self=True
            ),
        }
    )
    return payload


def _registry_library_item_from_spec(spec: Any, ports: Iterable[Any]) -> dict[str, Any]:
    return {
        "type_id": spec.type_id,
        "display_name": spec.display_name,
        **_category_metadata(spec.category_path),
        "icon": spec.icon,
        "runtime_behavior": str(getattr(spec, "runtime_behavior", "") or ""),
        "surface_family": str(getattr(spec, "surface_family", "") or ""),
        "surface_variant": str(getattr(spec, "surface_variant", "") or ""),
        "library_visual": _library_visual_from_spec(spec),
        "description": spec.description,
        "keywords": list(getattr(spec, "keywords", ()) or ()),
        "library_source": "node_registry",
        "ports": [
            {
                "key": port.key,
                "label": str(getattr(port, "label", "") or port.key),
                "description": str(getattr(port, "description", "") or ""),
                "direction": port.direction,
                "kind": port.kind,
                "data_type": port.data_type,
                "data_access": str(getattr(port, "data_access", "item") or "item"),
                "accepted_data_types": list(
                    getattr(port, "accepted_data_types", ()) or ()
                ),
                "side": port.side,
                "exposed": bool(port.exposed),
            }
            for port in ordered_ports_for_display(ports)
        ],
    }


def build_registry_library_items(
    *,
    registry_specs: Iterable[Any],
    data_types: DataTypeCatalog,
    data_type_projection: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        _project_library_item_payload(
            _registry_library_item_from_spec(
                spec, resolve_instance_ports(spec, {}, data_types=data_types)
            ),
            data_type_projection=data_type_projection,
        )
        for spec in registry_specs
    ]


def build_combined_library_items(
    *,
    registry_items: Iterable[dict[str, Any]],
    custom_workflow_items: Iterable[dict[str, Any]],
    data_type_projection: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    items = [
        _project_library_item_payload(
            item,
            data_type_projection=data_type_projection,
        )
        for item in registry_items
    ]
    items.extend(
        _project_library_item_payload(
            item,
            data_type_projection=data_type_projection,
        )
        for item in custom_workflow_items
    )
    items.sort(
        key=lambda item: (
            _category_sort_key(_category_path_from_item(item)),
            str(item.get("display_name", "")).lower(),
            str(item.get("type_id", "")).lower(),
        )
    )
    return items


def library_item_matches_filters(
    item: dict[str, Any],
    *,
    query: str,
    category: str,
    data_type: str,
    direction: str,
) -> bool:
    if not _item_matches_category_filter(item, category):
        return False

    ports = item.get("ports", [])
    normalized_ports = ports if isinstance(ports, list) else []

    if data_type or direction:
        matches_port = False
        for port in normalized_ports:
            if not isinstance(port, dict):
                continue
            declared_types = projected_port_declared_data_types(port)
            if not declared_types:
                continue
            port_direction = str(port.get("direction", "")).strip().lower()
            if direction and port_direction != direction:
                continue
            if data_type and not any(
                declared_type.casefold() == data_type.casefold()
                for declared_type in declared_types
            ):
                continue
            matches_port = True
            break
        if not matches_port:
            return False

    if not query:
        return True
    text_haystack = " ".join(
        [
            str(item.get("type_id", "")),
            str(item.get("display_name", "")),
            str(item.get("category", "")),
            str(item.get("category_display", "")),
            str(item.get("description", "")),
            " ".join(
                str(port.get("key", ""))
                for port in normalized_ports
                if isinstance(port, dict)
            ),
        ]
    ).lower()
    return query in text_haystack


def build_filtered_library_items(
    *,
    combined_items: Iterable[dict[str, Any]],
    query: str,
    category: str,
    data_type: str,
    direction: str,
) -> list[dict[str, Any]]:
    normalized_query = str(query).strip().lower()
    normalized_category = str(category).strip()
    normalized_data_type = str(data_type).strip().lower()
    normalized_direction = str(direction).strip().lower()
    return [
        item
        for item in combined_items
        if library_item_matches_filters(
            item,
            query=normalized_query,
            category=normalized_category,
            data_type=normalized_data_type,
            direction=normalized_direction,
        )
    ]


def build_library_category_tree(
    filtered_items: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    tree: dict[str, Any] = {"path": (), "children": {}, "items": []}
    for item in filtered_items:
        payload = _project_library_item_payload(item)
        node = tree
        current_path: CategoryPath = ()
        for segment in _category_path_from_item(payload):
            current_path = (*current_path, segment)
            node = node["children"].setdefault(
                segment,
                {"path": current_path, "children": {}, "items": []},
            )
        node["items"].append(payload)
    return tree


def _library_item_sort_key(item: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("display_name", "")).casefold(),
        str(item.get("type_id", "")).casefold(),
    )


def _passive_icon_grid_row(
    *,
    category_path: CategoryPath,
    items: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    effective_path = category_path or (_DEFAULT_LIBRARY_CATEGORY,)
    payload = _category_metadata(effective_path)
    payload.update(
        {
            "kind": "passive_icon_grid",
            "label": "",
            "depth": len(effective_path),
            "ancestor_category_keys": _ancestor_category_keys(
                effective_path, include_self=True
            ),
            "items": [_node_row(item) for item in items],
        }
    )
    return payload


def _project_library_category_tree(
    tree: dict[str, Any],
    *,
    passive_icon_mode: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def _append_node(node: dict[str, Any]) -> None:
        path = node["path"]
        if path:
            rows.append(_category_row(path))
        for child_segment in sorted(
            node["children"],
            key=lambda segment: (str(segment).casefold(), str(segment)),
        ):
            _append_node(node["children"][child_segment])

        sorted_items = sorted(node["items"], key=_library_item_sort_key)
        if not passive_icon_mode:
            rows.extend(_node_row(item) for item in sorted_items)
            return

        passive_items = [
            item for item in sorted_items if _is_passive_library_item(item)
        ]
        rows.extend(
            _node_row(item)
            for item in sorted_items
            if not _is_passive_library_item(item)
        )
        if passive_items:
            rows.append(_passive_icon_grid_row(category_path=path, items=passive_items))

    _append_node(tree)
    return rows


def project_grouped_library_items(
    *,
    category_tree: dict[str, Any],
) -> list[dict[str, Any]]:
    return _project_library_category_tree(category_tree, passive_icon_mode=False)


def project_display_library_items(
    *,
    category_tree: dict[str, Any],
    passive_node_library_display_mode: str,
) -> list[dict[str, Any]]:
    return _project_library_category_tree(
        category_tree,
        passive_icon_mode=(
            str(passive_node_library_display_mode).strip().lower() == "icon"
        ),
    )


def build_library_category_options(
    *,
    combined_items: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    paths: set[CategoryPath] = set()

    def _add_path(path: Iterable[str]) -> None:
        normalized_path = normalize_category_path(tuple(path))
        for ancestor in category_path_ancestors(normalized_path):
            paths.add(ancestor)

    for item in combined_items:
        item_path = _category_path_from_item(item)
        _add_path(item_path)

    _add_path(_CUSTOM_WORKFLOW_LIBRARY_CATEGORY_PATH)
    return [{"label": "All Categories", "value": ""}] + [
        {
            "label": category_display(path),
            "value": category_key(path),
            "category_path": path,
            "category_key": category_key(path),
            "depth": len(path) - 1,
            "root_category": path[0],
        }
        for path in sorted(paths, key=_category_sort_key)
    ]


def build_library_direction_options() -> list[dict[str, str]]:
    return [
        {"label": "Any Port Direction", "value": ""},
        {"label": "Input", "value": "in"},
        {"label": "Output", "value": "out"},
    ]


def build_library_data_type_options(
    *,
    combined_items: Iterable[dict[str, Any]],
) -> list[dict[str, str]]:
    data_types: set[str] = set()
    for item in combined_items:
        ports = item.get("ports", [])
        if not isinstance(ports, list):
            continue
        for port in ports:
            if not isinstance(port, dict):
                continue
            data_types.update(projected_port_declared_data_types(port))
    return [{"label": "Any Data Type", "value": ""}] + [
        {"label": data_type, "value": data_type}
        for data_type in sorted(data_types, key=lambda value: (value.casefold(), value))
    ]


def rank_node_library_usage(
    *,
    combined_items: Iterable[dict[str, Any]],
    usage: Iterable[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    last_used: dict[str, int] = {}
    for index, type_id in enumerate(usage):
        normalized_type_id = str(type_id).strip()
        if not normalized_type_id:
            continue
        counts[normalized_type_id] = counts.get(normalized_type_id, 0) + 1
        last_used[normalized_type_id] = index
    available = {
        str(item.get("type_id", "")).strip(): item
        for item in combined_items
        if str(item.get("library_source", "")).strip() == "node_registry"
    }
    ranked_type_ids = sorted(
        (type_id for type_id in counts if type_id in available),
        key=lambda type_id: (
            -counts[type_id],
            -last_used[type_id],
            str(available[type_id].get("display_name", "")).casefold(),
            type_id,
        ),
    )
    return [
        dict(available[type_id]) for type_id in ranked_type_ids[: max(0, int(limit))]
    ]
