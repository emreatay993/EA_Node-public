from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ea_node_editor.app_preferences import normalize_expand_collision_avoidance_settings
from ea_node_editor.graph.group_backdrop_geometry import (
    GroupBackdropCandidate,
    GroupBackdropMembership,
    build_group_backdrop_occupied_bounds,
    compute_group_backdrop_membership,
)
from ea_node_editor.graph.hierarchy import node_scope_path, scope_node_ids
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.graph.transform_layout_ops import (
    LayoutNodeBounds,
    build_expand_collision_avoidance_position_updates,
)
from ea_node_editor.ui_qml.graph_surface_metrics import resolved_node_surface_size

if TYPE_CHECKING:
    from ea_node_editor.nodes.node_specs import NodeTypeSpec

_LOCAL_RADIUS_BY_PRESET = {
    "small": 420.0,
    "medium": 760.0,
    "large": 1200.0,
}
_GAP_BY_PRESET = {
    "tight": 16.0,
    "normal": 32.0,
    "loose": 56.0,
}
_MISSING = object()


@dataclass(slots=True, frozen=True)
class _CollisionObject:
    object_id: str
    bounds: LayoutNodeBounds
    move_node_ids: tuple[str, ...]


def expand_collision_avoidance_updates(
    self,
    node_id: str,
    *,
    use_current_presentation_bounds: bool = False,
) -> dict[str, tuple[float, float]]:
    settings = normalize_expand_collision_avoidance_settings(
        self._scene_context.graphics_expand_collision_avoidance
    )
    if not bool(settings.get("enabled", True)):
        return {}
    if str(settings.get("strategy", "nearest")).strip().lower() != "nearest":
        return {}
    if str(settings.get("scope", "all_movable")).strip().lower() != "all_movable":
        return {}

    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return {}
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return {}
    node = workspace.nodes.get(node_id)
    if node is None:
        return {}
    spec = registry.spec_or_none(node.type_id)
    if spec is None:
        return {}

    workspace_nodes = dict(workspace.nodes)
    membership_by_id, group_backdrop_ids = _group_backdrop_membership_for_scope(
        self,
        workspace,
        node_id,
        workspace_nodes=workspace_nodes,
    )
    presentation_bounds = (
        _current_presentation_bounds(self, node_id)
        if use_current_presentation_bounds
        else None
    )
    fixed_bounds, fixed_node_ids = _expanded_fixed_bounds(
        self,
        workspace=workspace,
        workspace_nodes=workspace_nodes,
        node=node,
        spec=spec,
        membership_by_id=membership_by_id,
        group_backdrop_ids=group_backdrop_ids,
        presentation_bounds=presentation_bounds,
    )
    if fixed_bounds is None:
        return {}

    collision_objects = _collision_objects_for_scope(
        self,
        workspace=workspace,
        expanding_node_id=node_id,
        workspace_nodes=workspace_nodes,
        fixed_node_ids=fixed_node_ids,
        membership_by_id=membership_by_id,
        group_backdrop_ids=group_backdrop_ids,
    )
    if not collision_objects:
        return {}

    gap = _gap_for_settings(settings)
    reach_radius = _reach_radius_for_settings(settings)
    object_updates = build_expand_collision_avoidance_position_updates(
        fixed_bounds=fixed_bounds,
        movable_bounds=[item.bounds for item in collision_objects],
        gap=gap,
        reach_radius=reach_radius,
    )
    if not object_updates:
        return {}

    updates: dict[str, tuple[float, float]] = {}
    for collision_object in collision_objects:
        final_position = object_updates.get(collision_object.object_id)
        if final_position is None:
            continue
        dx = float(final_position[0]) - float(collision_object.bounds.x)
        dy = float(final_position[1]) - float(collision_object.bounds.y)
        if abs(dx) < 0.01 and abs(dy) < 0.01:
            continue
        for move_node_id in collision_object.move_node_ids:
            if move_node_id == node_id:
                continue
            moved_node = workspace.nodes.get(move_node_id)
            if moved_node is None:
                continue
            updates[move_node_id] = (float(moved_node.x) + dx, float(moved_node.y) + dy)
    return updates


def _expanded_fixed_bounds(
    self,
    *,
    workspace: WorkspaceData,
    workspace_nodes: dict[str, NodeInstance],
    node: NodeInstance,
    spec: "NodeTypeSpec",
    membership_by_id: dict[str, GroupBackdropMembership],
    group_backdrop_ids: set[str],
    presentation_bounds: LayoutNodeBounds | None,
) -> tuple[LayoutNodeBounds | None, set[str]]:
    expanded_bounds = presentation_bounds or _node_layout_bounds(
        self,
        workspace,
        node,
        spec,
        workspace_nodes=workspace_nodes,
        expanded=True,
    )
    if expanded_bounds is None:
        return None, {node.node_id}
    if node.node_id not in group_backdrop_ids:
        return expanded_bounds, {node.node_id}

    membership = membership_by_id.get(node.node_id)
    if membership is None:
        return expanded_bounds, {node.node_id}
    direct_member_ids = [*membership.member_node_ids, *membership.member_backdrop_ids]
    member_candidates = _comment_candidates_for_node_ids(
        self,
        workspace=workspace,
        workspace_nodes=workspace_nodes,
        node_ids=direct_member_ids,
        expanded=False,
    )
    occupied = build_group_backdrop_occupied_bounds(
        _candidate_from_bounds(expanded_bounds, is_backdrop=True, workspace=workspace),
        member_candidates,
    )
    fixed_ids = {
        node.node_id,
        *membership.member_node_ids,
        *membership.member_backdrop_ids,
        *membership.contained_node_ids,
        *membership.contained_backdrop_ids,
    }
    return (
        LayoutNodeBounds(
            node_id=node.node_id,
            x=float(occupied.x),
            y=float(occupied.y),
            width=float(occupied.width),
            height=float(occupied.height),
        ),
        fixed_ids,
    )


def _collision_objects_for_scope(
    self,
    *,
    workspace: WorkspaceData,
    expanding_node_id: str,
    workspace_nodes: dict[str, NodeInstance],
    fixed_node_ids: set[str],
    membership_by_id: dict[str, GroupBackdropMembership],
    group_backdrop_ids: set[str],
) -> list[_CollisionObject]:
    registry = self._scene_context.registry
    if registry is None:
        return []
    scope_path = node_scope_path(workspace, expanding_node_id)
    objects: list[_CollisionObject] = []
    moved_node_ids: set[str] = set()
    for candidate_id in scope_node_ids(workspace, scope_path):
        if candidate_id in fixed_node_ids:
            continue
        membership = membership_by_id.get(candidate_id)
        if membership is not None and membership.owner_backdrop_id:
            continue
        node = workspace.nodes.get(candidate_id)
        if node is None:
            continue
        spec = registry.spec_or_none(node.type_id)
        if spec is None:
            continue
        if candidate_id in group_backdrop_ids:
            object_membership = membership_by_id.get(candidate_id)
            move_ids = _comment_move_ids(candidate_id, object_membership)
            if expanding_node_id in move_ids or fixed_node_ids.intersection(move_ids):
                continue
            bounds = _comment_occupied_bounds_for_node(
                self,
                workspace=workspace,
                workspace_nodes=workspace_nodes,
                node=node,
                membership=object_membership,
                expanded=False,
            )
        else:
            move_ids = (candidate_id,)
            bounds = _node_layout_bounds(
                self,
                workspace,
                node,
                spec,
                workspace_nodes=workspace_nodes,
                expanded=False,
            )
        if bounds is None or moved_node_ids.intersection(move_ids):
            continue
        moved_node_ids.update(move_ids)
        objects.append(_CollisionObject(object_id=candidate_id, bounds=bounds, move_node_ids=move_ids))
    return objects


def _comment_move_ids(
    backdrop_id: str,
    membership: GroupBackdropMembership | None,
) -> tuple[str, ...]:
    if membership is None:
        return (backdrop_id,)
    return (
        backdrop_id,
        *membership.contained_backdrop_ids,
        *membership.contained_node_ids,
    )


def _comment_occupied_bounds_for_node(
    self,
    *,
    workspace: WorkspaceData,
    workspace_nodes: dict[str, NodeInstance],
    node: NodeInstance,
    membership: GroupBackdropMembership | None,
    expanded: bool,
) -> LayoutNodeBounds | None:
    registry = self._scene_context.registry
    if registry is None:
        return None
    spec = registry.spec_or_none(node.type_id)
    if spec is None:
        return None
    backdrop_bounds = _node_layout_bounds(
        self,
        workspace,
        node,
        spec,
        workspace_nodes=workspace_nodes,
        expanded=expanded,
    )
    if backdrop_bounds is None:
        return None
    direct_member_ids = [] if membership is None else [*membership.member_node_ids, *membership.member_backdrop_ids]
    member_candidates = _comment_candidates_for_node_ids(
        self,
        workspace=workspace,
        workspace_nodes=workspace_nodes,
        node_ids=direct_member_ids,
        expanded=False,
    )
    occupied = build_group_backdrop_occupied_bounds(
        _candidate_from_bounds(backdrop_bounds, is_backdrop=True, workspace=workspace),
        member_candidates,
    )
    return LayoutNodeBounds(
        node_id=node.node_id,
        x=float(occupied.x),
        y=float(occupied.y),
        width=float(occupied.width),
        height=float(occupied.height),
    )


def _group_backdrop_membership_for_scope(
    self,
    workspace: WorkspaceData,
    node_id: str,
    *,
    workspace_nodes: dict[str, NodeInstance],
) -> tuple[dict[str, GroupBackdropMembership], set[str]]:
    registry = self._scene_context.registry
    if registry is None:
        return {}, set()
    scope_path = node_scope_path(workspace, node_id)
    scoped_node_ids = scope_node_ids(workspace, scope_path)
    specs_by_node_id: dict[str, "NodeTypeSpec"] = {}
    group_backdrop_ids: set[str] = set()
    for candidate_id in scoped_node_ids:
        node = workspace.nodes.get(candidate_id)
        if node is None:
            continue
        spec = registry.spec_or_none(node.type_id)
        if spec is None:
            continue
        specs_by_node_id[candidate_id] = spec
        if _is_group_backdrop_spec(spec):
            group_backdrop_ids.add(candidate_id)
    if not group_backdrop_ids:
        return {}, set()

    candidates: list[GroupBackdropCandidate] = []
    for candidate_id in scoped_node_ids:
        node = workspace.nodes.get(candidate_id)
        if node is None:
            continue
        spec = specs_by_node_id.get(candidate_id)
        if spec is None:
            continue
        is_backdrop = _is_group_backdrop_spec(spec)
        bounds = _node_layout_bounds(
            self,
            workspace,
            node,
            spec,
            workspace_nodes=workspace_nodes,
            expanded=is_backdrop,
        )
        if bounds is None:
            continue
        candidates.append(_candidate_from_bounds(bounds, is_backdrop=is_backdrop, workspace=workspace))
    return compute_group_backdrop_membership(candidates), group_backdrop_ids


def _current_presentation_bounds(self, node_id: str) -> LayoutNodeBounds | None:
    context = self._scene_context
    model = context.model
    registry = context.registry
    workspace = context.workspace_or_none()
    if model is None or registry is None or workspace is None:
        return None
    try:
        nodes, backdrops, _minimap = context._payload_builder.build_node_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=context.scope_path,
            node_ids={node_id},
            graph_theme_bridge=context.graph_theme_bridge,
            show_port_labels=context.graphics_show_port_labels,
            graph_label_pixel_size=context.graphics_graph_label_pixel_size,
            graph_node_icon_pixel_size=context.graphics_node_title_icon_pixel_size,
            lightweight_canvas=context.graphics_lightweight_canvas,
        )
    except Exception:  # noqa: BLE001
        return None
    payload = next(
        (item for item in (*nodes, *backdrops) if str(item.get("node_id", "")) == node_id),
        None,
    )
    if payload is None:
        return None
    try:
        return LayoutNodeBounds(
            node_id=node_id,
            x=float(payload["x"]),
            y=float(payload["y"]),
            width=max(1.0, float(payload["width"])),
            height=max(1.0, float(payload["height"])),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _comment_candidates_for_node_ids(
    self,
    *,
    workspace: WorkspaceData,
    workspace_nodes: dict[str, NodeInstance],
    node_ids: list[str],
    expanded: bool,
) -> list[GroupBackdropCandidate]:
    registry = self._scene_context.registry
    if registry is None:
        return []
    candidates: list[GroupBackdropCandidate] = []
    for node_id in node_ids:
        node = workspace.nodes.get(node_id)
        if node is None:
            continue
        spec = registry.spec_or_none(node.type_id)
        if spec is None:
            continue
        bounds = _node_layout_bounds(
            self,
            workspace,
            node,
            spec,
            workspace_nodes=workspace_nodes,
            expanded=expanded,
        )
        if bounds is None:
            continue
        candidates.append(
            _candidate_from_bounds(
                bounds,
                is_backdrop=_is_group_backdrop_spec(spec),
                workspace=workspace,
            )
        )
    return candidates


def _node_layout_bounds(
    self,
    workspace: WorkspaceData,
    node: NodeInstance,
    spec: "NodeTypeSpec",
    *,
    workspace_nodes: dict[str, NodeInstance] | None = None,
    expanded: bool,
) -> LayoutNodeBounds | None:
    if not expanded:
        cached_bounds = _cached_node_layout_bounds(self, node.node_id)
        if cached_bounds is not None:
            return cached_bounds

    probe = node.clone()
    if expanded:
        probe.collapsed = False
    scoped_nodes = workspace_nodes
    if scoped_nodes is None:
        scoped_nodes = dict(workspace.nodes)
        original_node = _MISSING
    else:
        original_node = scoped_nodes.get(node.node_id, _MISSING)
    scoped_nodes[node.node_id] = probe
    try:
        width, height = resolved_node_surface_size(
            probe,
            spec,
            scoped_nodes,
            show_port_labels=self._scene_context.graphics_show_port_labels,
            graph_label_pixel_size=self._scene_context.graphics_graph_label_pixel_size,
            graph_node_icon_pixel_size=self._scene_context.graphics_node_title_icon_pixel_size,
        )
    except Exception:  # noqa: BLE001
        return None
    finally:
        if original_node is _MISSING:
            scoped_nodes.pop(node.node_id, None)
        else:
            scoped_nodes[node.node_id] = original_node
    return LayoutNodeBounds(
        node_id=node.node_id,
        x=float(node.x),
        y=float(node.y),
        width=max(1.0, float(width)),
        height=max(1.0, float(height)),
    )


def _cached_node_layout_bounds(self, node_id: str) -> LayoutNodeBounds | None:
    cache = self._scene_context._bridge._payload_cache
    if cache.dirty or not self._scene_context._payload_cache_sync.payload_cache_matches_active_view():
        return None
    if not cache.indexes_valid:
        cache.rebuild_indexes()
    status, location = cache.resolve_node_payload_slot(str(node_id or "").strip())
    if status != "ok" or location is None:
        return None
    collection_name, index = location
    collection = cache.nodes if collection_name == "nodes" else cache.backdrop_nodes
    payload = collection[index]
    try:
        x = float(payload.get("x", 0.0))
        y = float(payload.get("y", 0.0))
        width = max(1.0, float(payload.get("width", 0.0)))
        height = max(1.0, float(payload.get("height", 0.0)))
    except (TypeError, ValueError):
        return None
    return LayoutNodeBounds(
        node_id=str(node_id),
        x=x,
        y=y,
        width=width,
        height=height,
    )


def _candidate_from_bounds(
    bounds: LayoutNodeBounds,
    *,
    is_backdrop: bool,
    workspace: WorkspaceData,
) -> GroupBackdropCandidate:
    return GroupBackdropCandidate(
        node_id=bounds.node_id,
        scope_path=node_scope_path(workspace, bounds.node_id),
        is_backdrop=is_backdrop,
        x=float(bounds.x),
        y=float(bounds.y),
        width=float(bounds.width),
        height=float(bounds.height),
    )


def _is_group_backdrop_spec(spec: "NodeTypeSpec") -> bool:
    return str(spec.surface_family or "").strip() == "group_backdrop"


def _gap_for_settings(settings: dict[str, Any]) -> float:
    preset = str(settings.get("gap_preset", "normal")).strip().lower()
    return _GAP_BY_PRESET.get(preset, _GAP_BY_PRESET["normal"])


def _reach_radius_for_settings(settings: dict[str, Any]) -> float | None:
    radius_mode = str(settings.get("radius_mode", "local")).strip().lower()
    if radius_mode == "unbounded":
        return None
    preset = str(settings.get("local_radius_preset", "medium")).strip().lower()
    return _LOCAL_RADIUS_BY_PRESET.get(preset, _LOCAL_RADIUS_BY_PRESET["medium"])


__all__ = ["expand_collision_avoidance_updates"]
