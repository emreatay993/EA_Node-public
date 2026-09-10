# Purpose: Apply graph-scene node, edge, property, scope, link, and comment mutations with history.
# Map: feature_routes/clipboard_undo_redo_mutation_history.md
# Tests: tests/graph_track_b/scene_model_graph_scene_suite.py, tests/mechanical_catalogue/test_controls.py, tests/mechanical_catalogue/test_visuals.py
# Landmarks: _create_node_from_type; request_rewire_edges; set_node_settings_group_expanded; set_node_property; insert_dynamic_port; link_parameter_setup; upsert_node_link; upsert_node_comment

from __future__ import annotations

import copy
import getpass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from PyQt6.QtCore import QPointF

from ea_node_editor.common.protected_values import (
    protect_secret,
    reprotect_secret,
    secret_public_state,
)
from ea_node_editor.common.optimization_links import (
    OPTIMIZATION_PARAMETER_SETUP_TYPE_ID,
    optimization_pool_role,
    parameter_setup_pool_link_facts,
)
from ea_node_editor.graph.ids import new_id
from ea_node_editor.graph.node_comments import normalize_node_comment_record
from ea_node_editor.graph.node_links import (
    node_link_targets_node,
    normalize_node_link_record,
    unwrap_corex_link_anchors,
)
from ea_node_editor.passive_style_normalization import (
    normalize_passive_node_style_payload,
)
from ea_node_editor.graph.effective_ports import (
    find_port,
    ports_compatible,
    preferred_connection_port,
    visible_ports,
)
from ea_node_editor.graph.hierarchy import is_node_in_scope, scope_parent_id
from ea_node_editor.graph.invariant_kernel import GraphInvariantKernel
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.builtins.subnode import (
    SUBNODE_PIN_LABEL_PROPERTY,
    SUBNODE_PIN_PORT_KEY,
    is_subnode_pin_type,
    is_subnode_shell_type,
)
from ea_node_editor.nodes.builtins.data_control import NUMBER_SLIDER_TYPE_ID, SELECT_TYPE_ID
from ea_node_editor.nodes.builtins.web_viewer import WEB_PAGE_VIEWER_TYPE_ID
from ea_node_editor.nodes.instance_resolution import resolve_instance_ports
from ea_node_editor.ui_qml.graph_scene_mutation.collision_avoidance_ops import (
    expand_collision_avoidance_updates,
)
from ea_node_editor.ui.shell.runtime_clipboard import (
    normalize_edge_label as _normalize_edge_label,
    normalize_visual_style_payload,
)
from ea_node_editor.ui.shell.runtime_history import (
    ACTION_ADD_EDGE,
    ACTION_ADD_NODE,
    ACTION_EDIT_EDGE_LABEL,
    ACTION_EDIT_EDGE_STYLE,
    ACTION_EDIT_PORT_MODIFIERS,
    ACTION_EDIT_NODE_PROPERTY,
    ACTION_EDIT_NODE_STYLE,
    ACTION_EDIT_NODE_COMMENT,
    ACTION_EDIT_NODE_LINK,
    ACTION_EDIT_PORT_LABEL,
    ACTION_INSERT_DYNAMIC_PORT,
    ACTION_REMOVE_DYNAMIC_PORT,
    ACTION_REMOVE_EDGE,
    ACTION_REMOVE_NODE,
    ACTION_RENAME_DYNAMIC_PORT,
    ACTION_RENAME_NODE,
    ACTION_SET_PRINCIPAL_INPUT,
    ACTION_TOGGLE_COLLAPSED,
    ACTION_TOGGLE_SETTINGS_GROUP,
    ACTION_TOGGLE_NODE_LOCKED,
    ACTION_TOGGLE_EDGE_ENABLED,
    ACTION_TOGGLE_EXPOSED_PORT,
)

if TYPE_CHECKING:
    from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation

_MISSING = object()
ACTION_TOGGLE_HIDE_OPTIONAL_PORTS = "toggle-hide-optional-ports"
_EDGE_DISPLAY_MODES = frozenset({"default", "faint", "hidden"})


def _normalize_edge_display_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _EDGE_DISPLAY_MODES else "default"


def _normalize_edge_visual_style(visual_style: Any) -> dict[str, Any]:
    normalized = normalize_visual_style_payload(visual_style)
    if "display_mode" in normalized:
        normalized["display_mode"] = _normalize_edge_display_mode(
            normalized["display_mode"]
        )
    return normalized


def _protected_value_is_set(value: Any) -> bool:
    return bool(secret_public_state(value).get("has_value", False))


def _comment_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_comment_author(model: Any) -> str:
    metadata = getattr(getattr(model, "project", None), "metadata", {})
    workflow_settings = (
        metadata.get("workflow_settings") if isinstance(metadata, dict) else None
    )
    general = (
        workflow_settings.get("general")
        if isinstance(workflow_settings, dict)
        else None
    )
    author = general.get("author") if isinstance(general, dict) else ""
    normalized = str(author or "").strip()
    if normalized:
        return normalized
    return str(getpass.getuser() or "").strip() or "You"


def _property_diff_keys(
    before_node: NodeInstance, after_node: NodeInstance
) -> set[str]:
    before_properties = dict(before_node.properties)
    after_properties = dict(after_node.properties)
    return {
        key
        for key in set(before_properties) | set(after_properties)
        if before_properties.get(key, _MISSING) != after_properties.get(key, _MISSING)
    }


def _node_change_is_payload_only(
    before_node: NodeInstance,
    after_node: NodeInstance,
    keys: set[str],
) -> bool:
    if not _property_diff_keys(before_node, after_node).issubset(keys):
        return False
    candidate = before_node.clone()
    if "title" in keys:
        candidate.title = after_node.title
    candidate.properties = copy.deepcopy(after_node.properties)
    return candidate == after_node


# Node types whose property commits need cross-field normalization against the
# node's full merged property state (not just the incoming keys).
_CONTEXTUAL_NORMALIZATION_TYPE_IDS = frozenset(
    {WEB_PAGE_VIEWER_TYPE_ID, NUMBER_SLIDER_TYPE_ID, SELECT_TYPE_ID}
)


def _contextual_property_updates(
    registry: Any, node: NodeInstance, updates: dict[str, Any]
) -> dict[str, Any]:
    if not updates:
        return {}
    if node.type_id not in _CONTEXTUAL_NORMALIZATION_TYPE_IDS:
        return {
            key: value
            for key, value in updates.items()
            if node.properties.get(key, _MISSING) != value
        }
    merged_properties = copy.deepcopy(node.properties)
    merged_properties.update(copy.deepcopy(updates))
    normalized_properties = registry.normalize_properties(
        node.type_id,
        merged_properties,
        include_defaults=False,
    )
    return {
        key: value
        for key, value in normalized_properties.items()
        if node.properties.get(key, _MISSING) != value
    }


def _can_publish_targeted_property_delta(
    *,
    before_node: NodeInstance,
    after_node: NodeInstance,
    spec: Any,
    keys: set[str],
    before_edge_ids: set[str],
    after_edge_ids: set[str],
) -> bool:
    if is_subnode_pin_type(after_node.type_id):
        return False
    if str(getattr(spec, "surface_family", "") or "").strip() == "group_backdrop":
        return False
    if before_edge_ids != after_edge_ids:
        return False
    return _node_change_is_payload_only(before_node, after_node, keys)


def _publish_property_change(
    self,
    node_id: str,
    *,
    before_node: NodeInstance,
    after_node: NodeInstance,
    spec: Any,
    keys: set[str],
    before_edge_ids: set[str],
) -> None:
    after_edge_ids = set(self._scene_context.current_workspace().edges)
    title_changed = str(getattr(before_node, "title", "")) != str(
        getattr(after_node, "title", "")
    )
    changed_fields = {
        ("node.title" if key == "title" and title_changed else f"properties.{key}")
        for key in keys
        if str(key or "").strip()
    }
    if _can_publish_targeted_property_delta(
        before_node=before_node,
        after_node=after_node,
        spec=spec,
        keys=keys,
        before_edge_ids=before_edge_ids,
        after_edge_ids=after_edge_ids,
    ) and self._scene_context.publish_node_property_delta(
        node_id,
        changed_fields=changed_fields,
    ):
        return
    self._scene_context.rebuild_models()


def _publish_title_change(self, node_id: str, geometry_changed: bool) -> None:
    if geometry_changed:
        if not self._scene_context.publish_node_geometry_delta(
            {node_id}, publication_path="node_title_geometry_delta"
        ):
            self._scene_context.rebuild_models()
        return
    self._scene_context.publish_node_title_payload_delta(
        node_id, changed_fields={"node.title"}
    )


def _publish_port_label_change(self, node_id: str) -> None:
    if self._scene_context.publish_node_payload_delta(
        node_id,
        publication_path="port_label_payload_delta",
        edge_delta_reason="port_label",
    ):
        return
    self._scene_context.rebuild_models()


def _sync_payload_cache_view_filters(self) -> None:
    workspace = self._scene_context.workspace_or_none()
    if workspace is None:
        return
    active_view = workspace.views.get(workspace.active_view_id)
    if active_view is None:
        active_view = next(iter(workspace.views.values()), None)
    if active_view is None:
        return
    self._scene_context._bridge._payload_cache.set_active_view_filters(
        active_view_id=active_view.view_id,
        hide_optional_ports=active_view.hide_optional_ports,
    )


def add_node_from_type(self, type_id: str, x: float = 0.0, y: float = 0.0) -> str:
    return self.create_node_from_type(
        type_id=type_id,
        x=float(x),
        y=float(y),
        parent_node_id=scope_parent_id(self._scene_context.scope_path),
        select_node=True,
    )


def create_node_from_type(self, **kwargs) -> str:
    history_before = self._capture_history_snapshot()
    node_id = _create_node_from_type(self, **kwargs)
    if node_id:
        self._record_history(ACTION_ADD_NODE, history_before)
    return node_id


def _create_node_from_type(
    self,
    *,
    type_id: str,
    x: float,
    y: float,
    parent_node_id: str | None,
    select_node: bool,
    property_overrides: dict[str, Any] | None = None,
    exposed_port_overrides: dict[str, bool] | None = None,
    initial_title: str | None = None,
    custom_width: float | None = None,
    custom_height: float | None = None,
    after_create: Callable[[NodeInstance, ValidatedGraphMutation], bool | None]
    | None = None,
) -> str:
    model, registry = self._scene_context.require_bound()
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return ""
    dirty_before = bool(workspace.dirty)
    mutation_revision_before = int(workspace.mutation_revision)
    spec = registry.get_spec(type_id)
    mutations = self._validated_mutations()
    properties = registry.default_properties(type_id)
    media_panel_defaults = None
    if spec.type_id == MEDIA_PANEL_TYPE_ID:
        media_panel_defaults = self._scene_context.graphics_media_panel_defaults
        for key in ("show_title", "show_frame"):
            if key in properties:
                properties[key] = registry.normalize_property_value(
                    type_id,
                    key,
                    media_panel_defaults.get(key),
                )
    if property_overrides:
        properties.update(
            {
                str(key): registry.normalize_property_value(type_id, key, value)
                for key, value in property_overrides.items()
            }
        )
    resolved_ports = resolve_instance_ports(spec, properties)
    exposed_ports = {port.key: port.exposed for port in resolved_ports}
    if media_panel_defaults is not None:
        exposed_ports["source"] = bool(media_panel_defaults["source_input_exposed"])
    if exposed_port_overrides:
        overrides = {
            str(key).strip(): bool(value)
            for key, value in exposed_port_overrides.items()
        }
        unknown_keys = sorted(set(overrides) - set(exposed_ports))
        if unknown_keys:
            raise KeyError(
                f"Unknown exposed port override for {type_id}: {', '.join(unknown_keys)}"
            )
        exposed_ports.update(overrides)
    node = mutations.add_node(
        type_id=type_id,
        title=properties.get("title", spec.display_name)
        if initial_title is None
        else str(initial_title).strip(),
        x=float(x),
        y=float(y),
        properties=properties,
        exposed_ports=exposed_ports,
        parent_node_id=parent_node_id,
        custom_width=custom_width,
        custom_height=custom_height,
        expanded_settings_group_ids=spec.default_expanded_settings_group_ids,
    )
    selected_before = list(self._scope_selection.selected_node_ids)

    def rollback_created_node() -> None:
        self._record_mutations().remove_node(node.node_id)
        workspace.dirty = dirty_before
        workspace.mutation_revision = mutation_revision_before
        if select_node:
            self._scope_selection.set_selected_node_ids(selected_before, workspace=workspace)

    try:
        if after_create is not None and after_create(node, mutations) is False:
            rollback_created_node()
            return ""
        self._scene_context.sync_surface_title(node, spec)
        selection_changed = False
        if select_node:
            selection_changed = self._scope_selection.set_selected_node_ids(
                [node.node_id],
                workspace=workspace,
                emit_signals=after_create is not None,
            )
        if after_create is None:
            if not self._scene_context.publish_node_addition_delta(node.node_id):
                self._scene_context.rebuild_models()
            if selection_changed:
                self._scene_context.emit_selection_changed(node.node_id)
        else:
            self._scene_context.rebuild_models()
    except Exception:
        rollback_created_node()
        # A publication can fail after exposing the new node. Rebuild from the
        # rolled-back graph before reporting the import failure.
        self._scene_context.rebuild_models()
        raise
    return node.node_id


def add_edge(
    self,
    source_node_id: str,
    source_port: str,
    target_node_id: str,
    target_port: str,
    append_requested: bool = False,
) -> str:
    model, _registry = self._scene_context.require_bound()
    history_before = self._capture_history_snapshot()
    workspace = model.project.workspaces[self._scene_context.workspace_id]
    if not is_node_in_scope(
        workspace, source_node_id, self._scene_context.scope_path
    ) or not is_node_in_scope(
        workspace,
        target_node_id,
        self._scene_context.scope_path,
    ):
        raise ValueError("Connections are only allowed for nodes in the active scope.")
    before_edge_ids = set(workspace.edges)
    edge = self._validated_mutations().add_edge(
        source_node_id=source_node_id,
        source_port_key=source_port,
        target_node_id=target_node_id,
        target_port_key=target_port,
        append_requested=bool(append_requested),
    )
    after_edge_ids = set(workspace.edges)
    added_edge_ids = after_edge_ids - before_edge_ids
    removed_edge_ids = before_edge_ids - after_edge_ids
    if not added_edge_ids and not removed_edge_ids:
        return edge.edge_id
    related_edge_ids = self._scene_context.related_edge_ids_for_edges([edge])
    self._scene_context.publish_edge_topology_delta(
        added_edge_ids=added_edge_ids,
        removed_edge_ids=removed_edge_ids,
        updated_edge_ids=related_edge_ids - added_edge_ids,
        dirty_node_ids={edge.source_node_id, edge.target_node_id},
    )
    self._record_history(ACTION_ADD_EDGE, history_before)
    return edge.edge_id


def _connection_port_candidates(
    *,
    node: NodeInstance,
    spec,
    workspace_nodes: dict[str, NodeInstance],
    direction: str,
    peer_node: NodeInstance,
) -> tuple:
    in_ports, out_ports = visible_ports(
        node=node,
        spec=spec,
        workspace_nodes=workspace_nodes,
    )
    ports = out_ports if direction == "out" else in_ports
    preferred_key = preferred_connection_port(
        node=node,
        spec=spec,
        workspace_nodes=workspace_nodes,
        direction=direction,
        peer_node=peer_node,
    )
    ordered_ports = []
    seen_keys: set[str] = set()
    if preferred_key:
        for port in ports:
            if port.key != preferred_key:
                continue
            ordered_ports.append(port)
            seen_keys.add(port.key)
            break
    for port in ports:
        if port.key in seen_keys:
            continue
        ordered_ports.append(port)
    return tuple(ordered_ports)


def _preferred_connection_pair(
    *,
    source_node: NodeInstance,
    source_spec,
    target_node: NodeInstance,
    target_spec,
    workspace_nodes: dict[str, NodeInstance],
    data_types,
) -> tuple[str, str] | None:
    source_ports = _connection_port_candidates(
        node=source_node,
        spec=source_spec,
        workspace_nodes=workspace_nodes,
        direction="out",
        peer_node=target_node,
    )
    target_ports = _connection_port_candidates(
        node=target_node,
        spec=target_spec,
        workspace_nodes=workspace_nodes,
        direction="in",
        peer_node=source_node,
    )
    for source_port in source_ports:
        for target_port in target_ports:
            if not ports_compatible(
                source_port,
                target_port,
                data_types=data_types,
            ):
                continue
            return source_port.key, target_port.key
    return None


def connect_nodes(self, node_a_id: str, node_b_id: str) -> str:
    model, registry = self._scene_context.require_bound()
    workspace = model.project.workspaces[self._scene_context.workspace_id]
    if not is_node_in_scope(
        workspace, node_a_id, self._scene_context.scope_path
    ) or not is_node_in_scope(
        workspace,
        node_b_id,
        self._scene_context.scope_path,
    ):
        raise ValueError("Selected nodes must be in the active scope.")
    node_a = workspace.nodes[node_a_id]
    node_b = workspace.nodes[node_b_id]
    spec_a = registry.get_spec(node_a.type_id)
    spec_b = registry.get_spec(node_b.type_id)

    a_to_b = _preferred_connection_pair(
        source_node=node_a,
        source_spec=spec_a,
        target_node=node_b,
        target_spec=spec_b,
        workspace_nodes=workspace.nodes,
        data_types=registry.data_types,
    )
    b_to_a = _preferred_connection_pair(
        source_node=node_b,
        source_spec=spec_b,
        target_node=node_a,
        target_spec=spec_a,
        workspace_nodes=workspace.nodes,
        data_types=registry.data_types,
    )

    can_a_to_b = a_to_b is not None
    can_b_to_a = b_to_a is not None
    prefer_a_to_b = float(node_a.x) < float(node_b.x) or (
        float(node_a.x) == float(node_b.x) and float(node_a.y) <= float(node_b.y)
    )
    if can_a_to_b and (not can_b_to_a or prefer_a_to_b):
        return self.add_edge(node_a_id, a_to_b[0], node_b_id, a_to_b[1])
    if can_b_to_a:
        return self.add_edge(node_b_id, b_to_a[0], node_a_id, b_to_a[1])
    raise ValueError("Selected nodes do not have compatible out/in ports.")


def request_rewire_edges(
    self,
    edge_ids: list[Any],
    endpoint: str,
    node_id: str,
    port_key: str,
    copy_requested: bool = False,
    append_requested: bool = False,
) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False

    requested_edge_ids: list[str] = []
    seen_edge_ids: set[str] = set()
    for value in edge_ids:
        edge_id = str(value or "").strip()
        if edge_id and edge_id not in seen_edge_ids:
            seen_edge_ids.add(edge_id)
            requested_edge_ids.append(edge_id)
    if not requested_edge_ids or any(
        edge_id not in workspace.edges for edge_id in requested_edge_ids
    ):
        return False
    requested_edges = [workspace.edges[edge_id] for edge_id in requested_edge_ids]
    if any(
        not is_node_in_scope(
            workspace, edge.source_node_id, self._scene_context.scope_path
        )
        or not is_node_in_scope(
            workspace, edge.target_node_id, self._scene_context.scope_path
        )
        for edge in requested_edges
    ):
        return False
    normalized_node_id = str(node_id or "").strip()
    normalized_port_key = str(port_key or "").strip()
    if bool(normalized_node_id) != bool(normalized_port_key):
        return False
    if normalized_node_id and not is_node_in_scope(
        workspace, normalized_node_id, self._scene_context.scope_path
    ):
        return False

    edges_before = {
        edge_id: edge.clone() for edge_id, edge in workspace.edges.items()
    }
    history_before = self._capture_history_snapshot()
    try:
        changed_edge_ids = self._validated_mutations().rewire_edges(
            requested_edge_ids,
            endpoint,
            normalized_node_id,
            normalized_port_key,
            copy_requested=bool(copy_requested),
            append_requested=bool(append_requested),
        )
    except (KeyError, ValueError):
        return False
    if not changed_edge_ids:
        return False

    before_edge_ids = set(edges_before)
    after_edge_ids = set(workspace.edges)
    added_edge_ids = after_edge_ids - before_edge_ids
    removed_edge_ids = before_edge_ids - after_edge_ids
    related_edges = [
        edges_before[edge_id]
        for edge_id in requested_edge_ids
        if edge_id in edges_before
    ] + [
        edges_before[edge_id]
        for edge_id in removed_edge_ids
        if edge_id in edges_before
    ] + [
        workspace.edges[edge_id]
        for edge_id in set(changed_edge_ids) | added_edge_ids
        if edge_id in workspace.edges
    ]
    updated_edge_ids = self._scene_context.related_edge_ids_for_edges(related_edges)
    updated_edge_ids.update(
        edge_id for edge_id in changed_edge_ids if edge_id in workspace.edges
    )
    dirty_node_ids: set[str] = set()
    for edge in related_edges:
        dirty_node_ids.update((edge.source_node_id, edge.target_node_id))
    self._scene_context.publish_edge_topology_delta(
        added_edge_ids=added_edge_ids,
        updated_edge_ids=updated_edge_ids,
        removed_edge_ids=removed_edge_ids,
        dirty_node_ids=dirty_node_ids,
        publication_path="edge_batch_rewire_delta",
    )
    self._record_history(
        ACTION_REMOVE_EDGE
        if not added_edge_ids
        and all(edge_id not in workspace.edges for edge_id in requested_edge_ids)
        else ACTION_ADD_EDGE,
        history_before,
    )
    return True


def move_edge_endpoint(
    self,
    edge_id: str,
    endpoint: str,
    node_id: str,
    port_key: str,
    append_requested: bool = False,
) -> bool:
    return request_rewire_edges(
        self,
        [edge_id],
        endpoint,
        node_id,
        port_key,
        append_requested=append_requested,
    )


def remove_edge(self, edge_id: str) -> None:
    model = self._scene_context.model
    if model is None:
        return
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None or edge_id not in workspace.edges:
        return
    edge = workspace.edges.get(edge_id)
    if edge is None:
        return
    if not is_node_in_scope(
        workspace, edge.source_node_id, self._scene_context.scope_path
    ):
        return
    if not is_node_in_scope(
        workspace, edge.target_node_id, self._scene_context.scope_path
    ):
        return
    history_before = self._capture_history_snapshot()
    self._record_mutations().remove_edge(edge_id)
    related_edge_ids = self._scene_context.related_edge_ids_for_edges([edge])
    self._scene_context.publish_edge_topology_delta(
        updated_edge_ids=related_edge_ids,
        removed_edge_ids={edge.edge_id},
        dirty_node_ids={edge.source_node_id, edge.target_node_id},
    )
    self._record_history(ACTION_REMOVE_EDGE, history_before)


def remove_node_with_policy(self, node_id: str, *, require_visible: bool) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    if node_id not in workspace.nodes:
        self._resync_scene_after_stale_mutation()
        return False
    if require_visible and not is_node_in_scope(
        workspace, node_id, self._scene_context.scope_path
    ):
        self._resync_scene_after_stale_mutation()
        return False
    history_before = self._capture_history_snapshot()
    incoming_link_source_ids = {
        source_node.node_id
        for source_node in workspace.nodes.values()
        if source_node.node_id != node_id
        and any(
            node_link_targets_node(
                record,
                source_workspace_id=self._scene_context.workspace_id,
                target_workspace_id=self._scene_context.workspace_id,
                target_node_id=node_id,
            )
            for record in source_node.links
        )
    }
    incident_edges = self._scene_context.incident_edges_for_node(node_id)
    incident_edge_ids = {edge.edge_id for edge in incident_edges}
    dirty_node_ids = (
        self._scene_context.endpoint_node_ids_for_edges(incident_edges)
        | incoming_link_source_ids
        | {node_id}
    )
    self._record_mutations().remove_node(node_id, incident_edge_ids=incident_edge_ids)
    self._scope_selection.set_selected_node_ids(
        [value for value in self._scene_context.selected_node_ids if value != node_id],
        workspace=workspace,
    )
    self._scene_context.publish_edge_topology_delta(
        updated_edge_ids=self._scene_context.related_edge_ids_for_edges(incident_edges),
        removed_edge_ids={edge.edge_id for edge in incident_edges},
        dirty_node_ids=dirty_node_ids,
        removed_node_ids={node_id},
    )
    self._record_history(ACTION_REMOVE_NODE, history_before)
    return True


def remove_node(self, node_id: str) -> None:
    self.remove_node_with_policy(node_id, require_visible=True)


def remove_workspace_node(self, node_id: str) -> bool:
    return self.remove_node_with_policy(node_id, require_visible=False)


def focus_node(self, node_id: str) -> QPointF | None:
    item = self._scope_selection.node_item(node_id)
    if item is None:
        return None
    selection_changed = self._scope_selection.set_selected_node_ids([node_id])
    if not selection_changed:
        self._scene_context.emit_node_selected(node_id)
    return item.sceneBoundingRect().center()


def set_node_collapsed(self, node_id: str, collapsed: bool) -> bool:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    node = workspace.nodes.get(node_id)
    if node is None:
        return False
    spec = registry.resolve_spec(node.type_id, node.properties)
    if not spec.collapsible:
        return False
    normalized_collapsed = bool(collapsed)
    if bool(node.collapsed) == normalized_collapsed:
        return False
    collision_updates = {}
    if bool(node.collapsed) and not normalized_collapsed:
        collision_updates = expand_collision_avoidance_updates(self, node_id)
    history_group = self._scene_context.grouped_history_action(
        ACTION_TOGGLE_COLLAPSED, workspace
    )
    mutations = self._record_mutations()
    with history_group:
        mutations.set_node_collapsed(node_id, normalized_collapsed)
        for moved_node_id, (final_x, final_y) in collision_updates.items():
            if moved_node_id not in workspace.nodes:
                continue
            mutations.set_node_position(moved_node_id, final_x, final_y)
    self._scene_context.publish_node_geometry_delta(
        {node_id},
        position_node_ids=set(collision_updates),
        publication_path="node_collapsed_geometry_delta",
    )
    return True


def set_node_settings_group_expanded(
    self,
    node_id: str,
    group_id: str,
    expanded: bool,
) -> bool:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    normalized_node_id = str(node_id or "").strip()
    normalized_group_id = str(group_id or "").strip()
    node = workspace.nodes.get(normalized_node_id)
    spec = registry.spec_or_none(node.type_id) if node is not None else None
    if node is None or spec is None or bool(node.locked):
        return False
    spec = registry.resolve_spec(node.type_id, node.properties)
    declared_group_ids = tuple(group.group_id for group in spec.settings_groups)
    if normalized_group_id not in declared_group_ids:
        return False

    current_ids = {
        value
        for value in node.expanded_settings_group_ids
        if value in declared_group_ids
    }
    normalized_expanded = bool(expanded)
    if normalized_expanded:
        current_ids.add(normalized_group_id)
    else:
        current_ids.discard(normalized_group_id)
    final_group_ids = tuple(
        value for value in declared_group_ids if value in current_ids
    )
    if final_group_ids == node.expanded_settings_group_ids:
        return True

    presentation_model = copy.deepcopy(model) if bool(node.collapsed) else model
    presentation_node = presentation_model.project.workspaces[
        workspace.workspace_id
    ].nodes[normalized_node_id]
    if presentation_model is not model:
        presentation_node.collapsed = False

    def presentation_payload(
        expanded_group_ids: tuple[str, ...],
    ) -> dict[str, Any] | None:
        if presentation_model is not model:
            presentation_node.expanded_settings_group_ids = expanded_group_ids
        try:
            nodes, backdrops, _minimap = (
                self._scene_context._payload_builder.build_node_payloads_for_ids(
                    model=presentation_model,
                    registry=registry,
                    workspace_id=workspace.workspace_id,
                    scope_path=self._scene_context.scope_path,
                    node_ids={normalized_node_id},
                    graph_theme_bridge=self._scene_context.graph_theme_bridge,
                    show_port_labels=self._scene_context.graphics_show_port_labels,
                    graph_label_pixel_size=self._scene_context.graphics_graph_label_pixel_size,
                    graph_node_icon_pixel_size=self._scene_context.graphics_node_title_icon_pixel_size,
                    lightweight_canvas=self._scene_context.graphics_lightweight_canvas,
                )
            )
        except Exception:  # noqa: BLE001
            return None
        return next(
            (
                item
                for item in (*nodes, *backdrops)
                if str(item.get("node_id", "")) == normalized_node_id
            ),
            None,
        )

    before_payload = presentation_payload(node.expanded_settings_group_ids)
    collision_updates: dict[str, tuple[float, float]] = {}
    mutations = self._record_mutations()
    history_group = self._scene_context.grouped_history_action(
        ACTION_TOGGLE_SETTINGS_GROUP,
        workspace,
    )
    with history_group:
        mutations.set_node_expanded_settings_group_ids(
            normalized_node_id,
            final_group_ids,
        )
        after_payload = presentation_payload(final_group_ids)
        if (
            node.custom_height is not None
            and before_payload is not None
            and after_payload is not None
        ):
            before_band_height = float(
                before_payload.get("settings_band", {}).get("height", 0.0)
            )
            after_band_height = float(
                after_payload.get("settings_band", {}).get("height", 0.0)
            )
            height_delta = after_band_height - before_band_height
            if abs(height_delta) >= 0.01:
                minimum_height = float(
                    after_payload.get("surface_metrics", {}).get("min_height", 0.0)
                )
                final_height = max(
                    minimum_height,
                    float(node.custom_height) + height_delta,
                )
                mutations.set_node_geometry(
                    normalized_node_id,
                    float(node.x),
                    float(node.y),
                    node.custom_width,
                    final_height,
                )
        if normalized_expanded and not bool(node.collapsed):
            collision_updates = expand_collision_avoidance_updates(
                self,
                normalized_node_id,
                use_current_presentation_bounds=True,
            )
        for moved_node_id, (final_x, final_y) in collision_updates.items():
            if moved_node_id in workspace.nodes:
                mutations.set_node_position(moved_node_id, final_x, final_y)
    self._scene_context.publish_node_geometry_delta(
        {normalized_node_id},
        position_node_ids=set(collision_updates),
        publication_path="node_settings_group_geometry_delta",
    )
    return True


def set_node_locked(self, node_id: str, locked: bool) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    node = workspace.nodes.get(str(node_id or "").strip())
    if node is None or not str(node.type_id).startswith("passive."):
        return False
    normalized_locked = bool(locked)
    if bool(node.locked) == normalized_locked:
        return True
    history_before = self._capture_history_snapshot()
    self._record_mutations().set_node_locked(node.node_id, normalized_locked)
    self._scope_selection.set_selected_node_ids(
        self._scene_context.selected_node_ids, workspace=workspace
    )
    self._scene_context.publish_node_payload_delta(
        node.node_id,
        publication_path="node_locked_payload_delta",
        changed_fields={"node.locked"},
    )
    self._record_history(ACTION_TOGGLE_NODE_LOCKED, history_before)
    return True


def set_node_property(self, node_id: str, key: str, value: Any) -> None:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return
    node = workspace.nodes.get(node_id)
    if node is None:
        return
    spec = registry.resolve_spec(node.type_id, node.properties)
    property_spec = next(
        (
            property_spec
            for property_spec in spec.properties
            if property_spec.key == key
        ),
        None,
    )
    if key == "title" and (
        property_spec is None or self._scene_context.surface_title_sync_enabled(spec)
    ):
        normalized_title = self._normalized_title_update(node, value)
        if normalized_title is None:
            return
        history_before = self._capture_history_snapshot()
        geometry_changed = self._apply_title_update(
            node_id, node, spec, normalized_title
        )
        _publish_title_change(self, node_id, geometry_changed)
        self.notify_selected_node_context_updated(node_id)
        self._record_history(ACTION_RENAME_NODE, history_before)
        return
    if property_spec is None or bool(getattr(property_spec, "sensitive", False)):
        return
    if node.type_id == "core.python_script" and key == "script":
        history_before = self._capture_history_snapshot()
        self._validated_mutations().apply_python_script(node_id, str(value))
        self._scene_context.rebuild_models()
        self.notify_selected_node_context_updated(node_id)
        self._record_history(ACTION_EDIT_NODE_PROPERTY, history_before)
        return
    normalized = registry.normalize_property_value(
        node.type_id,
        key,
        value,
        properties=node.properties,
    )
    normalized_updates = _contextual_property_updates(registry, node, {key: normalized})
    normalized_updates = _sensitive_scope_updates(
        node=node,
        spec=spec,
        updates=normalized_updates,
    )
    if not normalized_updates:
        return
    history_before = self._capture_history_snapshot()
    before_node = node.clone()
    before_edge_ids = set(workspace.edges)
    try:
        self._validated_mutations().set_node_properties(node_id, normalized_updates)
    except PermissionError:
        return
    _publish_property_change(
        self,
        node_id,
        before_node=before_node,
        after_node=node,
        spec=spec,
        keys=set(normalized_updates),
        before_edge_ids=before_edge_ids,
    )
    self.notify_selected_node_context_updated(node_id)
    self._record_history(ACTION_EDIT_NODE_PROPERTY, history_before)


def set_node_properties(self, node_id: str, values: dict[str, Any]) -> bool:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    node = workspace.nodes.get(node_id)
    if node is None:
        return False
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
        if source == str(node.properties.get("script", "")):
            return False
        history_before = self._capture_history_snapshot()
        self._validated_mutations().apply_python_script(node_id, source)
        self._scene_context.rebuild_models()
        self.notify_selected_node_context_updated(node_id)
        self._record_history(ACTION_EDIT_NODE_PROPERTY, history_before)
        return True
    spec = registry.resolve_spec(node.type_id, node.properties)
    normalized_updates: dict[str, Any] = {}
    normalized_title = None
    for raw_key, raw_value in requested_values.items():
        key = str(raw_key or "")
        if not key:
            continue
        property_spec = next(
            (
                property_spec
                for property_spec in spec.properties
                if property_spec.key == key
            ),
            None,
        )
        if key == "title" and (
            property_spec is None or self._scene_context.surface_title_sync_enabled(spec)
        ):
            normalized_title = self._normalized_title_update(node, raw_value)
            continue
        if property_spec is None or bool(
            getattr(property_spec, "sensitive", False)
        ):
            continue
        try:
            normalized = registry.normalize_property_value(
                node.type_id,
                key,
                raw_value,
                properties=node.properties,
            )
        except KeyError:
            continue
        current_value = node.properties.get(key, _MISSING)
        if current_value is not _MISSING and current_value == normalized:
            continue
        normalized_updates[key] = normalized
    normalized_updates = _contextual_property_updates(
        registry, node, normalized_updates
    )
    normalized_updates = _sensitive_scope_updates(
        node=node,
        spec=spec,
        updates=normalized_updates,
    )
    if not normalized_updates and normalized_title is None:
        return False

    history_before = self._capture_history_snapshot()
    if normalized_title is not None and not normalized_updates:
        geometry_changed = self._apply_title_update(
            node_id, node, spec, normalized_title
        )
        _publish_title_change(self, node_id, geometry_changed)
        self.notify_selected_node_context_updated(node_id)
        self._record_history(ACTION_RENAME_NODE, history_before)
        return True
    before_node = node.clone()
    before_edge_ids = set(workspace.edges)
    try:
        self._validated_mutations().set_node_properties(node_id, normalized_updates)
    except PermissionError:
        return False
    if normalized_title is not None:
        self._apply_title_update(node_id, node, spec, normalized_title)
    changed_keys = set(normalized_updates)
    if normalized_title is not None:
        changed_keys.add("title")
    _publish_property_change(
        self,
        node_id,
        before_node=before_node,
        after_node=node,
        spec=spec,
        keys=changed_keys,
        before_edge_ids=before_edge_ids,
    )
    self.notify_selected_node_context_updated(node_id)
    self._record_history(ACTION_EDIT_NODE_PROPERTY, history_before)
    return True


def _sensitive_scope_updates(
    *,
    node: NodeInstance,
    spec: Any,
    updates: dict[str, Any],
) -> dict[str, Any]:
    expanded = dict(updates)
    for property_spec in spec.properties:
        scope_key = str(
            getattr(property_spec, "sensitive_scope_key", "") or ""
        ).strip()
        if (
            not bool(getattr(property_spec, "sensitive", False))
            or scope_key not in expanded
        ):
            continue
        scope_spec = next(
            (candidate for candidate in spec.properties if candidate.key == scope_key),
            None,
        )
        current_scope = (
            node.properties.get(scope_key, scope_spec.default)
            if scope_spec is not None
            else None
        )
        if current_scope == expanded[scope_key]:
            continue
        protected_value = node.properties.get(property_spec.key, property_spec.default)
        if not _protected_value_is_set(protected_value):
            continue
        expanded[property_spec.key] = reprotect_secret(
            protected_value,
            str(expanded[scope_key]),
        )
    return expanded


def set_node_secret(
    self,
    node_id: str,
    key: str,
    plaintext: str,
) -> bool:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    node = workspace.nodes.get(str(node_id or "").strip())
    if node is None:
        return False
    spec = registry.get_spec(node.type_id)
    property_spec = next(
        (
            property_spec
            for property_spec in spec.properties
            if property_spec.key == str(key or "").strip()
        ),
        None,
    )
    if property_spec is None or not bool(getattr(property_spec, "sensitive", False)):
        return False
    normalized_plaintext = str(plaintext)
    if not normalized_plaintext:
        return False
    scope_key = str(
        getattr(property_spec, "sensitive_scope_key", "") or ""
    ).strip()
    scope = ""
    if scope_key:
        scope_spec = next(
            (candidate for candidate in spec.properties if candidate.key == scope_key),
            None,
        )
        if scope_spec is not None:
            scope = str(node.properties.get(scope_key, scope_spec.default))
    protected_value = protect_secret(normalized_plaintext, scope)
    normalized = registry.normalize_property_value(
        node.type_id,
        property_spec.key,
        protected_value,
    )
    history_before = self._capture_history_snapshot()
    before_node = node.clone()
    before_edge_ids = set(workspace.edges)
    self._validated_mutations().set_node_property(
        node.node_id,
        property_spec.key,
        normalized,
    )
    _publish_property_change(
        self,
        node.node_id,
        before_node=before_node,
        after_node=node,
        spec=spec,
        keys={property_spec.key},
        before_edge_ids=before_edge_ids,
    )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_EDIT_NODE_PROPERTY, history_before)
    return True


def clear_node_secret(self, node_id: str, key: str) -> bool:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    node = workspace.nodes.get(str(node_id or "").strip())
    if node is None:
        return False
    spec = registry.get_spec(node.type_id)
    property_spec = next(
        (
            property_spec
            for property_spec in spec.properties
            if property_spec.key == str(key or "").strip()
        ),
        None,
    )
    if property_spec is None or not bool(getattr(property_spec, "sensitive", False)):
        return False
    current_value = node.properties.get(property_spec.key, property_spec.default)
    if not _protected_value_is_set(current_value):
        return False
    normalized = registry.normalize_property_value(
        node.type_id,
        property_spec.key,
        copy.deepcopy(property_spec.default),
    )
    history_before = self._capture_history_snapshot()
    before_node = node.clone()
    before_edge_ids = set(workspace.edges)
    self._validated_mutations().set_node_property(
        node.node_id,
        property_spec.key,
        normalized,
    )
    _publish_property_change(
        self,
        node.node_id,
        before_node=before_node,
        after_node=node,
        spec=spec,
        keys={property_spec.key},
        before_edge_ids=before_edge_ids,
    )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_EDIT_NODE_PROPERTY, history_before)
    return True


def normalize_node_visual_style(visual_style: Any) -> dict[str, Any]:
    return normalize_visual_style_payload(visual_style)


def set_node_visual_style(self, node_id: str, visual_style: Any) -> None:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None:
        return
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return
    node = workspace.nodes.get(node_id)
    if node is None:
        return
    spec = registry.spec_or_none(node.type_id) if registry is not None else None
    if (
        spec is not None
        and str(spec.runtime_behavior or "").strip().lower() != "passive"
    ):
        return
    normalized = normalize_visual_style_payload(visual_style)
    if node.visual_style == normalized:
        return
    history_before = self._capture_history_snapshot()
    self._record_mutations().set_node_visual_style(node_id, normalized)
    self._scene_context.rebuild_models()
    self._record_history(ACTION_EDIT_NODE_STYLE, history_before)


def clear_node_visual_style(self, node_id: str) -> None:
    self.set_node_visual_style(node_id, {})


def _node_has_passive_runtime(registry: Any, node: NodeInstance) -> bool:
    spec = registry.spec_or_none(node.type_id)
    return (
        spec is not None
        and str(spec.runtime_behavior or "").strip().lower() == "passive"
    )


def _connected_node_ids(workspace: Any, source_node_id: str) -> list[str]:
    adjacency: dict[str, set[str]] = {}
    for edge in workspace.edges.values():
        source_id = str(edge.source_node_id or "").strip()
        target_id = str(edge.target_node_id or "").strip()
        if not source_id or not target_id:
            continue
        adjacency.setdefault(source_id, set()).add(target_id)
        adjacency.setdefault(target_id, set()).add(source_id)

    ordered: list[str] = []
    visited = {source_node_id}
    stack = [source_node_id]
    while stack:
        current_id = stack.pop()
        ordered.append(current_id)
        for neighbor_id in sorted(adjacency.get(current_id, ())):
            if neighbor_id in visited or neighbor_id not in workspace.nodes:
                continue
            visited.add(neighbor_id)
            stack.append(neighbor_id)
    return ordered


def propagate_passive_node_style(self, node_id: str) -> bool:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    source_id = str(node_id or "").strip()
    if not source_id:
        return False
    source_node = workspace.nodes.get(source_id)
    if source_node is None or not _node_has_passive_runtime(registry, source_node):
        return False

    style = normalize_passive_node_style_payload(source_node.visual_style)
    target_node_ids = [
        candidate_id
        for candidate_id in _connected_node_ids(workspace, source_id)
        if candidate_id != source_id
        and _node_has_passive_runtime(registry, workspace.nodes[candidate_id])
        and workspace.nodes[candidate_id].visual_style != style
    ]
    if not target_node_ids:
        return False

    mutations = self._record_mutations()
    history_group = self._scene_context.grouped_history_action(
        ACTION_EDIT_NODE_STYLE, workspace
    )
    with history_group:
        for target_id in target_node_ids:
            mutations.set_node_visual_style(target_id, style)
    self._scene_context.rebuild_models()
    return True


def set_node_title(self, node_id: str, title: str) -> None:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return
    node = self._node(node_id)
    if node is None:
        return
    spec = registry.get_spec(node.type_id)
    normalized = self._normalized_title_update(node, title)
    if normalized is None:
        return
    history_before = self._capture_history_snapshot()
    geometry_changed = self._apply_title_update(node_id, node, spec, normalized)
    _publish_title_change(self, node_id, geometry_changed)
    self.notify_selected_node_context_updated(node_id)
    self._record_history(ACTION_RENAME_NODE, history_before)


def normalize_edge_label(label: Any) -> str:
    return _normalize_edge_label(label)


def set_edge_label(self, edge_id: str, label: Any) -> None:
    model = self._scene_context.model
    if model is None:
        return
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return
    edge = workspace.edges.get(edge_id)
    if edge is None:
        return
    normalized = _normalize_edge_label(label)
    if edge.label == normalized:
        return
    history_before = self._capture_history_snapshot()
    self._record_mutations().set_edge_label(edge_id, normalized)
    self._scene_context.publish_edge_topology_delta(
        updated_edge_ids={edge.edge_id},
        dirty_node_ids=self._scene_context.endpoint_node_ids_for_edges([edge]),
    )
    self._record_history(ACTION_EDIT_EDGE_LABEL, history_before)


def clear_edge_label(self, edge_id: str) -> None:
    self.set_edge_label(edge_id, "")


def normalize_edge_visual_style(visual_style: Any) -> dict[str, Any]:
    return _normalize_edge_visual_style(visual_style)


def set_edge_visual_style(self, edge_id: str, visual_style: Any) -> None:
    model = self._scene_context.model
    if model is None:
        return
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return
    edge = workspace.edges.get(edge_id)
    if edge is None:
        return
    normalized = _normalize_edge_visual_style(visual_style)
    if edge.visual_style == normalized:
        return
    history_before = self._capture_history_snapshot()
    self._record_mutations().set_edge_visual_style(edge_id, normalized)
    self._scene_context.publish_edge_topology_delta(
        updated_edge_ids={edge.edge_id},
        dirty_node_ids=self._scene_context.endpoint_node_ids_for_edges([edge]),
    )
    self._record_history(ACTION_EDIT_EDGE_STYLE, history_before)


def clear_edge_visual_style(self, edge_id: str) -> None:
    self.set_edge_visual_style(edge_id, {})


def set_edges_display_mode(self, edge_ids: list[Any], mode: Any) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False

    requested_edge_ids: list[str] = []
    seen_edge_ids: set[str] = set()
    for value in edge_ids:
        edge_id = str(value or "").strip()
        if edge_id and edge_id not in seen_edge_ids:
            seen_edge_ids.add(edge_id)
            requested_edge_ids.append(edge_id)
    if not requested_edge_ids or any(
        edge_id not in workspace.edges for edge_id in requested_edge_ids
    ):
        return False

    display_mode = _normalize_edge_display_mode(mode)
    style_updates: dict[str, dict[str, Any]] = {}
    for edge_id in requested_edge_ids:
        edge = workspace.edges[edge_id]
        if (
            _normalize_edge_display_mode(edge.visual_style.get("display_mode"))
            == display_mode
        ):
            continue
        visual_style = dict(edge.visual_style)
        if display_mode == "default":
            visual_style.pop("display_mode", None)
        else:
            visual_style["display_mode"] = display_mode
        style_updates[edge_id] = visual_style
    if not style_updates:
        return False

    history_before = self._capture_history_snapshot()
    mutations = self._record_mutations()
    dirty_node_ids: set[str] = set()
    for edge_id, visual_style in style_updates.items():
        mutations.set_edge_visual_style(edge_id, visual_style)
        edge = workspace.edges[edge_id]
        dirty_node_ids.update((edge.source_node_id, edge.target_node_id))
    self._scene_context.publish_edge_topology_delta(
        updated_edge_ids=set(style_updates),
        dirty_node_ids=dirty_node_ids,
        publication_path="edge_display_mode_delta",
    )
    self._record_history(ACTION_EDIT_EDGE_STYLE, history_before)
    return True


def set_edges_enabled(self, edge_ids: list[Any], enabled: bool) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False

    normalized_enabled = bool(enabled)
    requested_edge_ids: list[str] = []
    seen: set[str] = set()
    for value in edge_ids:
        edge_id = str(value or "").strip()
        if not edge_id or edge_id in seen:
            continue
        seen.add(edge_id)
        edge = workspace.edges.get(edge_id)
        if edge is not None and bool(edge.enabled) != normalized_enabled:
            requested_edge_ids.append(edge_id)
    if not requested_edge_ids:
        return False

    mutations = self._validated_mutations()
    if normalized_enabled:
        requested_edge_id_set = set(requested_edge_ids)
        temporary_edges = []
        for edge in workspace.edges.values():
            candidate = edge.clone()
            if candidate.edge_id in requested_edge_id_set:
                candidate.enabled = True
            temporary_edges.append(candidate)
        kernel = GraphInvariantKernel(
            registry=mutations.registry,
            workspace_nodes=workspace.nodes,
            workspace_edges=temporary_edges,
        )
        try:
            for edge_id in requested_edge_ids:
                edge = workspace.edges[edge_id]
                kernel.add_edge_or_raise(
                    source_node_id=edge.source_node_id,
                    source_port_key=edge.source_port_key,
                    target_node_id=edge.target_node_id,
                    target_port_key=edge.target_port_key,
                )
        except (KeyError, ValueError):
            return False

    history_before = self._capture_history_snapshot()
    record_mutations = self._record_mutations()
    changed_edge_ids: set[str] = set()
    dirty_node_ids: set[str] = set()
    for edge_id in requested_edge_ids:
        edge = workspace.edges.get(edge_id)
        if edge is None:
            continue
        record_mutations.set_edge_enabled(edge_id, normalized_enabled)
        changed_edge_ids.add(edge_id)
        dirty_node_ids.update((edge.source_node_id, edge.target_node_id))
    if not changed_edge_ids:
        return False

    self._scene_context.publish_edge_topology_delta(
        updated_edge_ids=changed_edge_ids,
        dirty_node_ids=dirty_node_ids,
    )
    self._record_history(ACTION_TOGGLE_EDGE_ENABLED, history_before)
    return True


def set_edge_enabled(self, edge_id: str, enabled: bool) -> bool:
    return self.set_edges_enabled([edge_id], enabled)


def set_port_modifiers(self, node_id: str, port_key: str, modifiers: list[Any]) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None or node_id not in workspace.nodes:
        return False
    normalized_modifiers = [str(value or "").strip().lower() for value in modifiers]
    history_before = self._capture_history_snapshot()
    try:
        changed = self._validated_mutations().set_port_modifiers(
            str(node_id),
            str(port_key),
            normalized_modifiers,
        )
    except (KeyError, ValueError):
        return False
    if not changed:
        return False
    self._scene_context.publish_node_payload_update(
        str(node_id),
        publication_path="port_modifier_payload",
    )
    self.notify_selected_node_context_updated(str(node_id))
    self._record_history(ACTION_EDIT_PORT_MODIFIERS, history_before)
    return True


def set_principal_input_port(self, node_id: str, port_key: str) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None or node_id not in workspace.nodes:
        return False
    normalized_port_key = str(port_key or "").strip() or None
    history_before = self._capture_history_snapshot()
    try:
        changed = self._validated_mutations().set_principal_input_port(
            str(node_id),
            normalized_port_key,
        )
    except (KeyError, ValueError):
        return False
    if not changed:
        return False
    self._scene_context.publish_node_payload_update(
        str(node_id),
        publication_path="principal_input_payload",
    )
    self.notify_selected_node_context_updated(str(node_id))
    self._record_history(ACTION_SET_PRINCIPAL_INPUT, history_before)
    return True


def insert_dynamic_port(
    self,
    node_id: str,
    group_id: str,
    ordinal: int,
) -> str:
    model = self._scene_context.model
    if model is None:
        return ""
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    node = (
        workspace.nodes.get(str(node_id or "").strip())
        if workspace is not None
        else None
    )
    if node is None:
        return ""
    incident_before = self._scene_context.incident_edges_for_node(node.node_id)
    history_before = self._capture_history_snapshot()
    port_key = self._validated_mutations().insert_dynamic_port(
        node.node_id,
        str(group_id),
        int(ordinal),
    )
    self._scene_context.publish_node_payload_update(
        node.node_id,
        publication_path="dynamic_port_insert",
    )
    incident_after = self._scene_context.incident_edges_for_node(node.node_id)
    updated_edges = self._scene_context.related_edge_ids_for_edges(
        [*incident_before, *incident_after]
    )
    if updated_edges:
        self._scene_context.publish_edge_topology_delta(
            updated_edge_ids=updated_edges,
            dirty_node_ids=self._scene_context.endpoint_node_ids_for_edges(
                incident_after
            )
            | {node.node_id},
        )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_INSERT_DYNAMIC_PORT, history_before)
    return port_key


def remove_dynamic_port(
    self,
    node_id: str,
    group_id: str,
    port_key: str,
) -> tuple[str, tuple[str, ...]] | None:
    model = self._scene_context.model
    if model is None:
        return None
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    node = (
        workspace.nodes.get(str(node_id or "").strip())
        if workspace is not None
        else None
    )
    if node is None:
        return None
    incident_before = self._scene_context.incident_edges_for_node(node.node_id)
    history_before = self._capture_history_snapshot()
    removed_port_key, removed_edge_ids = (
        self._validated_mutations().remove_dynamic_port(
            node.node_id,
            str(group_id),
            str(port_key),
        )
    )
    removed_edge_id_set = set(removed_edge_ids)
    self._scene_context.publish_node_payload_update(
        node.node_id,
        publication_path="dynamic_port_remove",
    )
    incident_after = self._scene_context.incident_edges_for_node(node.node_id)
    updated_edges = (
        self._scene_context.related_edge_ids_for_edges(
            [*incident_before, *incident_after]
        )
        - removed_edge_id_set
    )
    self._scene_context.publish_edge_topology_delta(
        updated_edge_ids=updated_edges,
        removed_edge_ids=removed_edge_id_set,
        dirty_node_ids=self._scene_context.endpoint_node_ids_for_edges(incident_before)
        | {node.node_id},
    )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_REMOVE_DYNAMIC_PORT, history_before)
    return removed_port_key, tuple(removed_edge_ids)


def rename_dynamic_port(
    self,
    node_id: str,
    group_id: str,
    port_key: str,
    value: str,
) -> tuple[str, tuple[str, ...]] | None:
    model = self._scene_context.model
    if model is None:
        return None
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    node = (
        workspace.nodes.get(str(node_id or "").strip())
        if workspace is not None
        else None
    )
    if node is None:
        return None
    incident_before = self._scene_context.incident_edges_for_node(node.node_id)
    history_before = self._capture_history_snapshot()
    result = self._validated_mutations().rename_dynamic_port(
        node.node_id,
        str(group_id),
        str(port_key),
        str(value),
    )
    if result is None:
        return None
    resulting_port_key, removed_edge_ids = result
    removed_edge_id_set = set(removed_edge_ids)
    self._scene_context.publish_node_payload_update(
        node.node_id,
        publication_path="dynamic_port_rename",
    )
    incident_after = self._scene_context.incident_edges_for_node(node.node_id)
    updated_edges = (
        self._scene_context.related_edge_ids_for_edges(
            [*incident_before, *incident_after]
        )
        - removed_edge_id_set
    )
    self._scene_context.publish_edge_topology_delta(
        updated_edge_ids=updated_edges,
        removed_edge_ids=removed_edge_id_set,
        dirty_node_ids=self._scene_context.endpoint_node_ids_for_edges(
            incident_before
        )
        | {node.node_id},
    )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_RENAME_DYNAMIC_PORT, history_before)
    return resulting_port_key, tuple(removed_edge_ids)


def set_exposed_port(self, node_id: str, key: str, exposed: bool) -> None:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return
    node = workspace.nodes.get(node_id)
    if node is None:
        return
    spec = registry.get_spec(node.type_id)
    port = find_port(
        node=node,
        spec=spec,
        workspace_nodes=workspace.nodes,
        port_key=key,
    )
    if port is None:
        return
    normalized_exposed = bool(exposed)
    current_exposed = bool(port.exposed)
    if current_exposed == normalized_exposed:
        return
    history_before = self._capture_history_snapshot()
    changed = self._validated_mutations().set_exposed_port(
        node_id, key, normalized_exposed
    )
    if not changed:
        return
    self._scene_context.rebuild_models()
    self._record_history(ACTION_TOGGLE_EXPOSED_PORT, history_before)


def set_hide_optional_ports(self, hide_optional_ports: bool) -> bool:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    history_before = self._capture_history_snapshot()
    changed = self._validated_mutations().set_view_hide_optional_ports(
        bool(hide_optional_ports)
    )
    if not changed:
        return False
    self._scene_context.rebuild_models()
    _sync_payload_cache_view_filters(self)
    self._record_history(ACTION_TOGGLE_HIDE_OPTIONAL_PORTS, history_before)
    return True


def set_node_port_label(self, node_id: str, port_key: str, label: str) -> None:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return
    node = workspace.nodes.get(node_id)
    if node is None:
        return
    normalized_label = str(label or "").strip()

    if is_subnode_shell_type(node.type_id):
        pin_node = workspace.nodes.get(str(port_key or "").strip())
        if pin_node is None or str(pin_node.parent_node_id or "").strip() != str(
            node.node_id
        ):
            return
        current_label = str(
            pin_node.properties.get(SUBNODE_PIN_LABEL_PROPERTY, "")
        ).strip()
        if not normalized_label or normalized_label == current_label:
            return
        history_before = self._capture_history_snapshot()
        self._validated_mutations().set_node_property(
            pin_node.node_id, SUBNODE_PIN_LABEL_PROPERTY, normalized_label
        )
        _publish_port_label_change(self, node.node_id)
        self.notify_selected_node_context_updated(node.node_id)
        self._record_history(ACTION_EDIT_PORT_LABEL, history_before)
        return

    if (
        is_subnode_pin_type(node.type_id)
        and str(port_key or "").strip() == SUBNODE_PIN_PORT_KEY
    ):
        current_label = str(node.properties.get(SUBNODE_PIN_LABEL_PROPERTY, "")).strip()
        if not normalized_label or normalized_label == current_label:
            return
        history_before = self._capture_history_snapshot()
        self._validated_mutations().set_node_property(
            node.node_id, SUBNODE_PIN_LABEL_PROPERTY, normalized_label
        )
        _publish_port_label_change(self, node.node_id)
        self.notify_selected_node_context_updated(node.node_id)
        self._record_history(ACTION_EDIT_PORT_LABEL, history_before)
        return

    current_label = node.port_labels.get(port_key, "")
    if normalized_label == current_label:
        return
    history_before = self._capture_history_snapshot()
    self._validated_mutations().set_port_label(node_id, port_key, normalized_label)
    _publish_port_label_change(self, node_id)
    self.notify_selected_node_context_updated(node_id)
    self._record_history(ACTION_EDIT_PORT_LABEL, history_before)


def _parameter_setup_pool_context(self, pool_node_id: object) -> tuple[Any, ...] | None:
    model = self._scene_context.model
    if model is None:
        return None
    workspace_id = str(self._scene_context.workspace_id or "").strip()
    workspace = model.project.workspaces.get(workspace_id)
    normalized_pool_node_id = str(pool_node_id or "").strip()
    pool_node = workspace.nodes.get(normalized_pool_node_id) if workspace else None
    pool_role = optimization_pool_role(pool_node.type_id if pool_node else "")
    link_facts = parameter_setup_pool_link_facts(pool_role)
    if workspace is None or pool_node is None or link_facts is None:
        return None
    link_id, link_title = link_facts
    return workspace, pool_node, pool_role, link_id, link_title


def _canonical_parameter_setup_pool_link(
    setup_node: NodeInstance,
    *,
    workspace_id: str,
    pool_node: NodeInstance,
    link_id: str,
    link_title: str,
) -> Any | None:
    if setup_node.type_id != OPTIMIZATION_PARAMETER_SETUP_TYPE_ID:
        return None
    matching_records = [
        item for item in setup_node.links if item.link_id == link_id
    ]
    if len(matching_records) != 1:
        return None
    record = matching_records[0]
    if (
        record.kind != "node"
        or record.title != link_title
        or record.target != pool_node.node_id
        or record.subtitle != ""
        or record.target_workspace_id != workspace_id
        or record.target_node_id != pool_node.node_id
    ):
        return None
    return record


def parameter_setup_link_options(
    self,
    pool_node_id: object,
) -> list[dict[str, Any]]:
    context = _parameter_setup_pool_context(self, pool_node_id)
    if context is None:
        return []
    workspace, pool_node, _pool_role, link_id, link_title = context
    workspace_id = str(self._scene_context.workspace_id or "").strip()
    valid_setup_ids = [
        node.node_id
        for node in workspace.nodes.values()
        if _canonical_parameter_setup_pool_link(
            node,
            workspace_id=workspace_id,
            pool_node=pool_node,
            link_id=link_id,
            link_title=link_title,
        )
        is not None
    ]
    linked_setup_id = valid_setup_ids[0] if len(valid_setup_ids) == 1 else ""
    return [
        {
            "setup_node_id": node.node_id,
            "title": str(node.title or "").strip() or "Parameter Setup",
            "linked": node.node_id == linked_setup_id,
        }
        for node in workspace.nodes.values()
        if node.type_id == OPTIMIZATION_PARAMETER_SETUP_TYPE_ID
        and node.node_id != pool_node.node_id
    ]


def parameter_setup_link_status(
    self,
    pool_node_id: object,
) -> dict[str, Any]:
    context = _parameter_setup_pool_context(self, pool_node_id)
    if context is None:
        return {
            "eligible": False,
            "linked": False,
            "conflict": False,
            "pool_role": "",
            "setup_node_id": "",
            "setup_title": "",
        }
    workspace, pool_node, pool_role, link_id, link_title = context
    workspace_id = str(self._scene_context.workspace_id or "").strip()
    valid_setups = [
        node
        for node in workspace.nodes.values()
        if _canonical_parameter_setup_pool_link(
            node,
            workspace_id=workspace_id,
            pool_node=pool_node,
            link_id=link_id,
            link_title=link_title,
        )
        is not None
    ]
    linked_setup = valid_setups[0] if len(valid_setups) == 1 else None
    return {
        "eligible": True,
        "linked": linked_setup is not None,
        "conflict": len(valid_setups) > 1,
        "pool_role": pool_role,
        "setup_node_id": linked_setup.node_id if linked_setup else "",
        "setup_title": (
            str(linked_setup.title or "").strip() or "Parameter Setup"
            if linked_setup
            else ""
        ),
    }


def link_parameter_setup(
    self,
    pool_node_id: object,
    setup_node_id: object,
) -> bool:
    context = _parameter_setup_pool_context(self, pool_node_id)
    if context is None:
        return False
    workspace, pool_node, _pool_role, link_id, link_title = context
    normalized_setup_node_id = str(setup_node_id or "").strip()
    setup_node = workspace.nodes.get(normalized_setup_node_id)
    if (
        setup_node is None
        or setup_node.node_id == pool_node.node_id
        or setup_node.type_id != OPTIMIZATION_PARAMETER_SETUP_TYPE_ID
    ):
        return False

    workspace_id = str(self._scene_context.workspace_id or "").strip()
    canonical_record = normalize_node_link_record(
        link_id=link_id,
        kind="node",
        title=link_title,
        target=pool_node.node_id,
        subtitle="",
        target_workspace_id=workspace_id,
        target_node_id=pool_node.node_id,
        source_workspace_id=workspace_id,
    )
    if canonical_record is None:
        return False

    mutations = self._record_mutations()
    affected_setup_ids: set[str] = set()
    changed = False
    chosen_role_indices = [
        index
        for index, record in enumerate(setup_node.links)
        if record.link_id == link_id
    ]
    chosen_role_index = chosen_role_indices[0] if chosen_role_indices else None
    chosen_is_canonical = (
        len(chosen_role_indices) == 1
        and setup_node.links[chosen_role_indices[0]] == canonical_record
    )
    with self._scene_context.grouped_history_action(
        ACTION_EDIT_NODE_LINK,
        workspace,
        commit_if=lambda: changed,
    ):
        for candidate in workspace.nodes.values():
            if (
                candidate.type_id != OPTIMIZATION_PARAMETER_SETUP_TYPE_ID
                or candidate.node_id == setup_node.node_id
            ):
                continue
            if not any(
                record.link_id == link_id
                and (
                    str(record.target or "").strip() == pool_node.node_id
                    or str(record.target_node_id or "").strip()
                    == pool_node.node_id
                )
                for record in candidate.links
            ):
                continue
            if mutations.remove_node_link(candidate.node_id, link_id):
                affected_setup_ids.add(candidate.node_id)
                changed = True

        if not chosen_is_canonical:
            if chosen_role_indices:
                if not mutations.remove_node_link(setup_node.node_id, link_id):
                    return False
                changed = True
            stored = mutations.upsert_node_link(
                setup_node.node_id,
                link_id=canonical_record.link_id,
                kind=canonical_record.kind,
                title=canonical_record.title,
                target=canonical_record.target,
                subtitle=canonical_record.subtitle,
                target_workspace_id=canonical_record.target_workspace_id,
                target_node_id=canonical_record.target_node_id,
            )
            if stored is None:
                return False
            affected_setup_ids.add(setup_node.node_id)
            changed = True
            if chosen_role_index is not None:
                current_index = len(setup_node.links) - 1
                target_index = min(chosen_role_index, current_index)
                if target_index != current_index:
                    if not mutations.move_node_link(
                        setup_node.node_id,
                        link_id,
                        target_index - current_index,
                    ):
                        return False

    if _canonical_parameter_setup_pool_link(
        setup_node,
        workspace_id=workspace_id,
        pool_node=pool_node,
        link_id=link_id,
        link_title=link_title,
    ) is None:
        return False
    if any(
        candidate.node_id != setup_node.node_id
        and candidate.type_id == OPTIMIZATION_PARAMETER_SETUP_TYPE_ID
        and any(
            record.link_id == link_id
            and (
                str(record.target or "").strip() == pool_node.node_id
                or str(record.target_node_id or "").strip() == pool_node.node_id
            )
            for record in candidate.links
        )
        for candidate in workspace.nodes.values()
    ):
        return False

    for affected_setup_id in affected_setup_ids:
        self._scene_context.publish_node_payload_update(
            affected_setup_id,
            publication_path="parameter_setup_pool_link_payload",
        )
        self.notify_selected_node_context_updated(affected_setup_id)
    self._scope_selection.set_selected_node_ids(
        [pool_node.node_id, setup_node.node_id],
        workspace=workspace,
    )
    return True


def unlink_parameter_setup(self, pool_node_id: object) -> bool:
    context = _parameter_setup_pool_context(self, pool_node_id)
    if context is None:
        return False
    workspace, pool_node, _pool_role, link_id, link_title = context
    workspace_id = str(self._scene_context.workspace_id or "").strip()
    linked_setups = [
        node
        for node in workspace.nodes.values()
        if _canonical_parameter_setup_pool_link(
            node,
            workspace_id=workspace_id,
            pool_node=pool_node,
            link_id=link_id,
            link_title=link_title,
        )
        is not None
    ]
    if not linked_setups:
        return False

    mutations = self._record_mutations()
    changed = False
    with self._scene_context.grouped_history_action(
        ACTION_EDIT_NODE_LINK,
        workspace,
        commit_if=lambda: changed,
    ):
        for setup_node in linked_setups:
            changed = mutations.remove_node_link(setup_node.node_id, link_id) or changed

    for setup_node in linked_setups:
        self._scene_context.publish_node_payload_update(
            setup_node.node_id,
            publication_path="parameter_setup_pool_link_payload",
        )
        self.notify_selected_node_context_updated(setup_node.node_id)
    return changed


def upsert_node_link(
    self,
    node_id: str,
    link_id: str,
    kind: str,
    title: str,
    target: str,
    subtitle: str = "",
    target_workspace_id: str = "",
    target_node_id: str = "",
) -> str:
    model = self._scene_context.model
    if model is None:
        return ""
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return ""
    node = workspace.nodes.get(str(node_id or "").strip())
    if node is None:
        return ""
    normalized_link_id = str(link_id or "").strip() or new_id("link")
    record = normalize_node_link_record(
        link_id=normalized_link_id,
        kind=kind,
        title=title,
        target=target,
        subtitle=subtitle,
        target_workspace_id=target_workspace_id,
        target_node_id=target_node_id,
        source_workspace_id=self._scene_context.workspace_id,
    )
    if record is None:
        return ""
    existing = next(
        (item for item in node.links if item.link_id == record.link_id), None
    )
    if existing == record:
        return record.link_id
    history_before = self._capture_history_snapshot()
    stored = self._record_mutations().upsert_node_link(
        node.node_id,
        link_id=record.link_id,
        kind=record.kind,
        title=record.title,
        target=record.target,
        subtitle=record.subtitle,
        target_workspace_id=record.target_workspace_id,
        target_node_id=record.target_node_id,
    )
    if stored is None:
        return ""
    self._scene_context.publish_node_payload_update(
        node.node_id, publication_path="node_link_payload"
    )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_EDIT_NODE_LINK, history_before)
    return stored.link_id


def _unwrap_deleted_node_link_markdown(self, node_id: str, link_id: str) -> None:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return
    node = workspace.nodes.get(node_id)
    if node is None:
        return
    updates: dict[str, Any] = {}
    for key, value in list(node.properties.items()):
        if not isinstance(value, str):
            continue
        unwrapped = unwrap_corex_link_anchors(value, link_id)
        if unwrapped != value:
            updates[str(key)] = unwrapped
    if updates:
        self._validated_mutations().set_node_properties(node_id, updates)


def remove_node_link(self, node_id: str, link_id: str) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    node = workspace.nodes.get(str(node_id or "").strip())
    if node is None:
        return False
    normalized_link_id = str(link_id or "").strip()
    if not normalized_link_id or not any(
        item.link_id == normalized_link_id for item in node.links
    ):
        return False
    history_before = self._capture_history_snapshot()
    removed = self._record_mutations().remove_node_link(
        node.node_id, normalized_link_id
    )
    if not removed:
        return False
    _unwrap_deleted_node_link_markdown(self, node.node_id, normalized_link_id)
    self._scene_context.publish_node_payload_update(
        node.node_id, publication_path="node_link_payload"
    )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_EDIT_NODE_LINK, history_before)
    return True


def move_node_link(self, node_id: str, link_id: str, offset: int) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    node = workspace.nodes.get(str(node_id or "").strip())
    if node is None:
        return False
    normalized_link_id = str(link_id or "").strip()
    if not normalized_link_id:
        return False
    history_before = self._capture_history_snapshot()
    moved = self._record_mutations().move_node_link(
        node.node_id, normalized_link_id, int(offset)
    )
    if not moved:
        return False
    self._scene_context.publish_node_payload_update(
        node.node_id, publication_path="node_link_payload"
    )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_EDIT_NODE_LINK, history_before)
    return True


def upsert_node_comment(
    self,
    node_id: str,
    comment_id: str,
    body: str,
    author: str = "",
    parent_id: str = "",
    resolved: bool = False,
    unread: bool = True,
    pinned: bool = False,
) -> str:
    model = self._scene_context.model
    if model is None:
        return ""
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return ""
    node = workspace.nodes.get(str(node_id or "").strip())
    if node is None:
        return ""
    normalized_comment_id = str(comment_id or "").strip() or new_id("comment")
    existing = next(
        (item for item in node.comments if item.comment_id == normalized_comment_id),
        None,
    )
    stamp = _comment_timestamp()
    record = normalize_node_comment_record(
        comment_id=normalized_comment_id,
        body=body,
        author=author
        or (existing.author if existing else _default_comment_author(model)),
        created_at=existing.created_at if existing else stamp,
        updated_at=stamp,
        resolved=existing.resolved if existing else resolved,
        unread=existing.unread if existing else unread,
        pinned=existing.pinned if existing else pinned,
        parent_id=existing.parent_id if existing else parent_id,
    )
    if record is None:
        return ""
    if existing == record:
        return record.comment_id
    history_before = self._capture_history_snapshot()
    stored = self._record_mutations().upsert_node_comment(
        node.node_id,
        comment_id=record.comment_id,
        body=record.body,
        author=record.author,
        created_at=record.created_at,
        updated_at=record.updated_at,
        resolved=record.resolved,
        unread=record.unread,
        pinned=record.pinned,
        parent_id=record.parent_id,
    )
    if stored is None:
        return ""
    self._scene_context.publish_node_payload_update(
        node.node_id, publication_path="node_comment_payload"
    )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_EDIT_NODE_COMMENT, history_before)
    return stored.comment_id


def remove_node_comment(self, node_id: str, comment_id: str) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    node = workspace.nodes.get(str(node_id or "").strip())
    if node is None:
        return False
    normalized_comment_id = str(comment_id or "").strip()
    if not normalized_comment_id or not any(
        item.comment_id == normalized_comment_id for item in node.comments
    ):
        return False
    history_before = self._capture_history_snapshot()
    removed = self._record_mutations().remove_node_comment(
        node.node_id, normalized_comment_id
    )
    if not removed:
        return False
    self._scene_context.publish_node_payload_update(
        node.node_id, publication_path="node_comment_payload"
    )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_EDIT_NODE_COMMENT, history_before)
    return True


def set_node_comment_resolved(
    self, node_id: str, comment_id: str, resolved: bool
) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    node = workspace.nodes.get(str(node_id or "").strip())
    if node is None:
        return False
    normalized_comment_id = str(comment_id or "").strip()
    if not normalized_comment_id:
        return False
    history_before = self._capture_history_snapshot()
    changed = self._record_mutations().set_node_comment_resolved(
        node.node_id,
        normalized_comment_id,
        bool(resolved),
        _comment_timestamp(),
    )
    if not changed:
        return False
    self._scene_context.publish_node_payload_update(
        node.node_id, publication_path="node_comment_payload"
    )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_EDIT_NODE_COMMENT, history_before)
    return True


def set_node_comment_pinned(self, node_id: str, comment_id: str, pinned: bool) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    node = workspace.nodes.get(str(node_id or "").strip())
    if node is None:
        return False
    normalized_comment_id = str(comment_id or "").strip()
    if not normalized_comment_id:
        return False
    history_before = self._capture_history_snapshot()
    changed = self._record_mutations().set_node_comment_pinned(
        node.node_id, normalized_comment_id, bool(pinned)
    )
    if not changed:
        return False
    self._scene_context.publish_node_payload_update(
        node.node_id, publication_path="node_comment_payload"
    )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_EDIT_NODE_COMMENT, history_before)
    return True


def resolve_all_node_comments(self, node_id: str) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    node = workspace.nodes.get(str(node_id or "").strip())
    if node is None:
        return False
    history_before = self._capture_history_snapshot()
    changed = self._record_mutations().resolve_all_node_comments(
        node.node_id, _comment_timestamp()
    )
    if not changed:
        return False
    self._scene_context.publish_node_payload_update(
        node.node_id, publication_path="node_comment_payload"
    )
    self.notify_selected_node_context_updated(node.node_id)
    self._record_history(ACTION_EDIT_NODE_COMMENT, history_before)
    return True


def mark_node_comments_read(self, node_id: str) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    node = workspace.nodes.get(str(node_id or "").strip())
    if node is None:
        return False
    history_before = self._capture_history_snapshot()
    changed = self._record_mutations().mark_node_comments_read(node.node_id)
    if changed:
        self._scene_context.publish_node_payload_update(
            node.node_id, publication_path="node_comment_payload"
        )
        self.notify_selected_node_context_updated(node.node_id)
        self._record_history(ACTION_EDIT_NODE_COMMENT, history_before)
    return changed


__all__ = [
    "add_edge",
    "add_node_from_type",
    "clear_edge_label",
    "clear_edge_visual_style",
    "clear_node_visual_style",
    "connect_nodes",
    "create_node_from_type",
    "focus_node",
    "normalize_edge_label",
    "normalize_edge_visual_style",
    "normalize_node_visual_style",
    "propagate_passive_node_style",
    "remove_edge",
    "remove_node",
    "remove_node_with_policy",
    "remove_workspace_node",
    "move_node_link",
    "mark_node_comments_read",
    "move_edge_endpoint",
    "request_rewire_edges",
    "set_edge_label",
    "set_edge_enabled",
    "set_edges_display_mode",
    "set_edges_enabled",
    "set_edge_visual_style",
    "set_exposed_port",
    "set_hide_optional_ports",
    "set_node_collapsed",
    "set_node_settings_group_expanded",
    "set_node_locked",
    "set_node_port_label",
    "set_port_modifiers",
    "set_principal_input_port",
    "set_node_properties",
    "set_node_property",
    "set_node_title",
    "set_node_visual_style",
    "upsert_node_link",
    "upsert_node_comment",
    "remove_node_link",
    "remove_node_comment",
    "resolve_all_node_comments",
    "set_node_comment_pinned",
    "set_node_comment_resolved",
]
