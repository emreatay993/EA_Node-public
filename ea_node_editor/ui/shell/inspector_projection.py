# Purpose: Project selected-node header, links, properties, ports, and editor metadata.
# Map: subsystems/qml_shell_and_bridges.md
# Tests: tests/test_inspector_projection.py

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ea_node_editor.ui.shell.property_edit_adapters import (
    create_shell_property_edit_adapters,
)
from ea_node_editor.addons.property_edit_adapters import (
    AddOnPropertyEditAdapter,
    PropertyEditAdapterContext,
    build_property_items_with_adapters,
)
from ea_node_editor.graph.effective_ports import (
    effective_ports,
    ordered_ports_for_display,
)
from ea_node_editor.graph.file_issue_state import (
    EXTERNAL_LINK_MODE,
    MANAGED_COPY_MODE,
    build_file_issue_payload,
    preferred_repair_mode_for_value,
    repair_modes_for_node_property,
)
from ea_node_editor.nodes.category_paths import category_display
from ea_node_editor.nodes.node_specs import (
    property_inspector_editor,
    property_visible_in_inspector,
)
from ea_node_editor.runtime_contracts import (
    BOOLEAN_DATA_TYPE_ID,
    DOUBLE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
    INTEGER_DATA_TYPE_ID,
    JSON_DATA_TYPE_ID,
    PATH_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
)
from ea_node_editor.ui.media_panel_source import media_panel_source_input_exposed
from ea_node_editor.ui.support.node_presentation import (
    build_inline_property_items,
    build_property_input_override_state,
    build_user_facing_node_instance_number,
    qml_safe_spec_property_value,
)

_PATH_LIKE_PORT_KEYS = frozenset({"normalized_path", "written_path", "path"})
_FOLDER_PATH_PROPERTIES_BY_TYPE = frozenset(
    {
        ("io.folder_explorer", "current_path"),
    }
)


def _project_root(project_path: str | None) -> Path | None:
    text = str(project_path or "").strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    return candidate.parent if candidate.suffix else candidate


def _resolve_candidate_path(value: Any, *, project_path: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        project_root = _project_root(project_path)
        if project_root is not None:
            candidate = project_root / candidate
    return str(candidate.resolve(strict=False))


def _property_text(node: Any, key: str) -> str:
    properties = getattr(node, "properties", {})
    if not isinstance(properties, Mapping):
        return ""
    return str(properties.get(key, "") or "").strip()


def _workspace_edge_values(
    workspace_edges: Mapping[str, Any] | Iterable[Any] | None,
) -> tuple[Any, ...]:
    if workspace_edges is None:
        return ()
    if isinstance(workspace_edges, Mapping):
        return tuple(workspace_edges.values())
    return tuple(workspace_edges)


def _incoming_edge_for_port(
    *,
    node: Any,
    port_key: str,
    workspace_edges: Mapping[str, Any] | Iterable[Any] | None,
) -> Any | None:
    node_id = str(getattr(node, "node_id", "")).strip()
    normalized_port_key = str(port_key or "").strip()
    if not node_id or not normalized_port_key:
        return None
    for edge in _workspace_edge_values(workspace_edges):
        if (
            str(getattr(edge, "target_node_id", "")).strip() == node_id
            and str(getattr(edge, "target_port_key", "")).strip() == normalized_port_key
        ):
            return edge
    return None


def _resolve_static_path_from_output_source(
    node: Any | None,
    *,
    source_port_key: str,
    project_path: str | None,
) -> str:
    if node is None:
        return ""
    if str(source_port_key or "").strip() in _PATH_LIKE_PORT_KEYS:
        return _resolve_candidate_path(
            _property_text(node, "path"), project_path=project_path
        )
    return ""


def _source_path_for_node_property(
    *,
    node: Any,
    property_key: str,
    workspace_nodes: Mapping[str, Any],
    workspace_edges: Mapping[str, Any] | Iterable[Any] | None,
    project_path: str | None,
) -> str:
    normalized_property_key = str(property_key or "").strip()
    if not normalized_property_key:
        return ""
    raw_node_path = _property_text(node, normalized_property_key)
    if raw_node_path:
        if "://" in raw_node_path or Path(raw_node_path).expanduser().is_absolute():
            return raw_node_path
        return _resolve_candidate_path(raw_node_path, project_path=project_path)
    path_edge = _incoming_edge_for_port(
        node=node,
        port_key=normalized_property_key,
        workspace_edges=workspace_edges,
    )
    if path_edge is None:
        return ""
    source_node = workspace_nodes.get(
        str(getattr(path_edge, "source_node_id", "")).strip()
    )
    return _resolve_static_path_from_output_source(
        source_node,
        source_port_key=str(getattr(path_edge, "source_port_key", "")).strip(),
        project_path=project_path,
    )


def _path_property_dialog_mode(*, node: Any, prop: Any) -> str:
    node_type_id = str(getattr(node, "type_id", "")).strip()
    property_key = str(getattr(prop, "key", "")).strip()
    if (node_type_id, property_key) == ("web.page_viewer", "start_location"):
        return "file"

    if str(getattr(prop, "type", "")).strip() != "path":
        return ""

    if (node_type_id, property_key) in _FOLDER_PATH_PROPERTIES_BY_TYPE:
        return "folder"

    if node_type_id == "io.path_pointer" and property_key == "path":
        properties = getattr(node, "properties", None)
        if hasattr(properties, "get"):
            mode = str(properties.get("mode", "file")).strip().lower()
            if mode == "folder":
                return "folder"

    return "file"


def _path_property_source_modes(*, node: Any, prop: Any) -> tuple[str, ...]:
    node_type_id = str(getattr(node, "type_id", "")).strip()
    property_key = str(getattr(prop, "key", "")).strip()
    if (node_type_id, property_key) == ("web.page_viewer", "start_location"):
        return (MANAGED_COPY_MODE, EXTERNAL_LINK_MODE)

    if str(getattr(prop, "type", "")).strip() != "path":
        return ()
    return repair_modes_for_node_property(
        node_type_id,
        property_key,
    )


def build_pin_data_type_options(
    *,
    registry_specs: Iterable[Any],
    workspaces: Iterable[Any],
    subnode_pin_type_ids: set[str],
    subnode_pin_data_type_property: str,
) -> list[str]:
    suggested = {
        GRAPH_DATA_TYPE_ID,
        STRING_DATA_TYPE_ID,
        INTEGER_DATA_TYPE_ID,
        DOUBLE_DATA_TYPE_ID,
        BOOLEAN_DATA_TYPE_ID,
        JSON_DATA_TYPE_ID,
        PATH_DATA_TYPE_ID,
    }
    suggested.update(
        type_id
        for spec in registry_specs
        for port in spec.ports
        for type_id in (
            str(port.data_type).strip(),
            *(
                str(value).strip()
                for value in (getattr(port, "accepted_data_types", ()) or ())
            ),
        )
        if type_id
    )
    for workspace in workspaces:
        for node in workspace.nodes.values():
            if node.type_id not in subnode_pin_type_ids:
                continue
            value = str(node.properties.get(subnode_pin_data_type_property, "")).strip()
            if value:
                suggested.add(value)
    ordered = [GRAPH_DATA_TYPE_ID]
    suggested.discard(GRAPH_DATA_TYPE_ID)
    ordered.extend(sorted(suggested, key=lambda value: (value.casefold(), value)))
    return ordered


def build_selected_node_header_data(
    *,
    node: Any,
    spec: Any,
    workflow_nodes: Mapping[str, Any],
) -> dict[str, Any]:
    title = (
        str(getattr(node, "title", "")).strip()
        or str(getattr(spec, "display_name", "")).strip()
    )
    display_name = str(getattr(spec, "display_name", "")).strip()
    description = str(getattr(spec, "description", "")).strip()
    subtitle = display_name if title != display_name and display_name else description

    instance_number = build_user_facing_node_instance_number(
        node=node,
        workflow_nodes=workflow_nodes,
    )

    metadata_items: list[dict[str, str]] = []
    category = str(getattr(spec, "category", "")).strip()
    category_path = getattr(spec, "category_path", None)
    if category_path is not None:
        try:
            category = category_display(category_path)
        except (TypeError, ValueError):
            pass
    if category:
        metadata_items.append({"label": "Category", "value": category})
    metadata_items.append({"label": "ID", "value": str(instance_number)})

    return {
        "title": title,
        "subtitle": subtitle,
        "metadata_items": metadata_items,
    }


_LINK_KIND_META = {
    "url": ("Web", "world-www", "#3BA9F5"),
    "file": ("File", "file-text", "#8B7CF6"),
    "folder": ("Folder", "folder", "#F2B84B"),
    "workspace": ("Workspace", "layout-dashboard", "#64C88A"),
    "node": ("Node", "hierarchy-2", "#60CDFF"),
}


def _link_target_breadcrumb(
    *,
    kind: str,
    target: str,
    workspace_nodes: Mapping[str, Any],
    workspaces: Mapping[str, Any],
    target_workspace_id: str = "",
    target_node_id: str = "",
) -> str:
    if kind == "url":
        parsed = urlparse(target)
        return parsed.netloc or target
    if kind in {"file", "folder"}:
        try:
            return Path(target).name or target
        except (OSError, ValueError):
            return target
    if kind == "node":
        normalized_node_id = str(target_node_id or target).strip()
        normalized_workspace_id = str(target_workspace_id or "").strip()
        target_workspace = (
            workspaces.get(normalized_workspace_id) if normalized_workspace_id else None
        )
        target_nodes = (
            getattr(target_workspace, "nodes", None)
            if target_workspace is not None
            else None
        )
        target_node = (
            target_nodes.get(normalized_node_id)
            if isinstance(target_nodes, Mapping)
            else workspace_nodes.get(normalized_node_id)
        )
        if target_node is None:
            return "Missing node"
        parts: list[str] = []
        workspace_name = str(getattr(target_workspace, "name", "") or "").strip()
        if workspace_name:
            parts.append(workspace_name)
        title = str(
            getattr(target_node, "title", "")
            or getattr(target_node, "type_id", "")
            or normalized_node_id
        )
        parts.append(title)
        return " - ".join(parts)
    if kind == "workspace":
        target_workspace = workspaces.get(target)
        if target_workspace is None:
            return "Missing workspace"
        return str(getattr(target_workspace, "name", "") or target)
    return target


def build_selected_node_link_items(
    *,
    node: Any,
    workspace_nodes: Mapping[str, Any] | None = None,
    workspaces: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    resolved_nodes = dict(workspace_nodes or {})
    resolved_workspaces = dict(workspaces or {})
    links = list(getattr(node, "links", []) or [])
    items: list[dict[str, Any]] = []
    for index, link in enumerate(links):
        kind = str(getattr(link, "kind", "") or "url").strip().lower() or "url"
        type_label, icon, type_color = _LINK_KIND_META.get(kind, _LINK_KIND_META["url"])
        target = str(getattr(link, "target", "") or "").strip()
        target_node_id = str(getattr(link, "target_node_id", "") or "").strip()
        target_workspace_id = str(
            getattr(link, "target_workspace_id", "") or ""
        ).strip()
        title = str(getattr(link, "title", "") or "").strip() or target or type_label
        subtitle = str(getattr(link, "subtitle", "") or "").strip()
        breadcrumb = subtitle or _link_target_breadcrumb(
            kind=kind,
            target=target,
            workspace_nodes=resolved_nodes,
            workspaces=resolved_workspaces,
            target_workspace_id=target_workspace_id,
            target_node_id=target_node_id,
        )
        items.append(
            {
                "id": str(getattr(link, "link_id", "") or "").strip(),
                "kind": kind,
                "title": title,
                "target": target,
                "target_node_id": target_node_id,
                "target_workspace_id": target_workspace_id,
                "subtitle": subtitle,
                "type_label": type_label,
                "breadcrumb": breadcrumb,
                "icon": icon,
                "type_color": type_color,
                "index": index,
                "can_move_up": index > 0,
                "can_move_down": index < len(links) - 1,
            }
        )
    return items


def build_selected_node_property_items(
    *,
    node: Any,
    spec: Any,
    subnode_pin_type_ids: set[str],
    workspace_id: str = "",
    workspace_nodes: Mapping[str, Any] | None = None,
    workspace_edges: Mapping[str, Any] | Iterable[Any] | None = None,
    port_connection_counts: Mapping[tuple[str, str], int] | None = None,
    file_issues_by_key: Mapping[str, Any] | None = None,
    project_path: str | None = None,
    project_metadata: Mapping[str, Any] | None = None,
    property_edit_adapters: Iterable[AddOnPropertyEditAdapter] | None = None,
    current_output_provider: Any = None,
) -> list[dict[str, Any]]:
    if node.type_id in subnode_pin_type_ids:
        ordered_keys = ("label", "kind", "data_type")
        ordered_properties = [
            prop
            for key in ordered_keys
            for prop in spec.properties
            if prop.key == key and property_visible_in_inspector(prop)
        ]
    else:
        ordered_properties = [
            prop for prop in spec.properties if property_visible_in_inspector(prop)
        ]
    issue_lookup = dict(file_issues_by_key or {})
    resolved_workspace_nodes = dict(workspace_nodes or {}) or {
        str(getattr(node, "node_id", "")).strip(): node
    }
    adapters = (
        tuple(property_edit_adapters)
        if property_edit_adapters is not None
        else create_shell_property_edit_adapters()
    )
    adapter_context = PropertyEditAdapterContext(
        node=node,
        spec=spec,
        workspace_id=str(workspace_id or ""),
        workspace_nodes=resolved_workspace_nodes,
        workspace_edges=workspace_edges,
        project_path=project_path,
        project_metadata=project_metadata,
        current_output_provider=current_output_provider,
        source_path_resolver=lambda source_node, property_key: (
            _source_path_for_node_property(
                node=source_node,
                property_key=property_key,
                workspace_nodes=resolved_workspace_nodes,
                workspace_edges=workspace_edges,
                project_path=project_path,
            )
        ),
    )
    resolved_input_ports = {
        port.key: port
        for port in effective_ports(
            node=node, spec=spec, workspace_nodes=resolved_workspace_nodes
        )
        if str(port.direction).strip().lower() == "in" and bool(port.exposed)
    }
    presentation_by_key = {
        str(item["key"]): item
        for item in build_inline_property_items(
            node=node,
            spec=spec,
            workspace_nodes=resolved_workspace_nodes,
            port_connection_counts=port_connection_counts,
        )
    }
    items: list[dict[str, Any]] = []
    sensitive_scope_keys = {
        str(getattr(candidate, "sensitive_scope_key", "") or "")
        for candidate in spec.properties
        if bool(getattr(candidate, "sensitive", False))
        and str(getattr(candidate, "sensitive_scope_key", "") or "")
    }
    media_source_input_exposed = media_panel_source_input_exposed(node)
    for prop in ordered_properties:
        current_value = node.properties.get(prop.key, prop.default)
        safe_current_value = qml_safe_spec_property_value(prop, current_value)
        presentation = presentation_by_key.get(str(prop.key))
        item = {
            "key": prop.key,
            "label": prop.label,
            "type": prop.type,
            "value": safe_current_value,
            "display_value": safe_current_value,
            "enum_values": list(prop.enum_values),
            "inline_editor": prop.inline_editor,
            "editor_mode": (
                "interval_slider"
                if str(prop.inline_editor) == "interval_slider"
                else property_inspector_editor(prop)
            ),
            "group": getattr(prop, "group", "") or "Properties",
            "dirty": current_value != prop.default,
            "sensitive": bool(getattr(prop, "sensitive", False)),
            "sensitive_scope_key": str(getattr(prop, "sensitive_scope_key", "") or ""),
            "reprotects_sensitive_properties": prop.key in sensitive_scope_keys,
        }
        help_text = str(getattr(prop, "description", "") or "")
        if help_text:
            item["help_text"] = help_text
        path_dialog_mode = _path_property_dialog_mode(node=node, prop=prop)
        if path_dialog_mode:
            item["path_dialog_mode"] = path_dialog_mode
        path_source_modes = _path_property_source_modes(node=node, prop=prop)
        if path_source_modes:
            item["path_source_modes"] = list(path_source_modes)
            item["path_supports_managed_copy"] = MANAGED_COPY_MODE in path_source_modes
            item["path_supports_external_link"] = (
                EXTERNAL_LINK_MODE in path_source_modes
            )
            item["path_current_source_mode"] = preferred_repair_mode_for_value(
                str(current_value or ""),
                project_path=project_path,
                project_metadata=project_metadata,
                fallback_mode=EXTERNAL_LINK_MODE,
                allowed_modes=path_source_modes,
            )
        if presentation is not None:
            item.update(presentation)
        else:
            item.update(
                build_property_input_override_state(
                    node=node,
                    property_key=prop.key,
                    resolved_input_ports=resolved_input_ports,
                    port_connection_counts=port_connection_counts,
                )
            )
        if media_source_input_exposed and prop.key == "source":
            item["editor_enabled"] = False
            item["editor_disabled_reason"] = (
                "Hide the Source input to edit Browse source."
            )
        item.update(
            build_file_issue_payload(
                None
                if media_source_input_exposed and prop.key == "source"
                else issue_lookup.get(prop.key)
            )
        )
        items.append(item)
    return build_property_items_with_adapters(adapters, adapter_context, items)


def build_selected_node_port_items(
    *,
    node: Any,
    spec: Any,
    workspace_nodes: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "key": port.key,
            "label": port.label,
            "direction": port.direction,
            "kind": port.kind,
            "data_type": port.data_type,
            "accepted_data_types": list(port.accepted_data_types),
            "side": port.side,
            "required": bool(port.required),
            "exposed": bool(port.exposed),
        }
        for port in ordered_ports_for_display(
            effective_ports(node=node, spec=spec, workspace_nodes=workspace_nodes)
        )
    ]
