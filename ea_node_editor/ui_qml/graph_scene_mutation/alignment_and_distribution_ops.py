from __future__ import annotations

from typing import Any

from ea_node_editor.graph.effective_ports import port_direction
from ea_node_editor.graph.hierarchy import is_node_in_scope
from ea_node_editor.graph.transforms import (
    PortAlignmentConstraint,
    build_alignment_position_updates,
    build_distribution_position_updates,
    build_straighten_connection_position_updates,
)
from ea_node_editor.ui.shell.runtime_history import ACTION_MOVE_NODE, ACTION_RESIZE_NODE
from ea_node_editor.ui_qml.graph_geometry.anchors import flowchart_port_side
from ea_node_editor.ui_qml.graph_geometry.route_endpoints import port_scene_pos
from ea_node_editor.ui_qml.graph_surface_metrics import (
    node_surface_metrics,
    resolved_node_surface_size,
)

SNAP_GRID_SIZE = 20.0
_HORIZONTAL_PORT_SIDES = frozenset({"left", "right"})
_VERTICAL_PORT_SIDES = frozenset({"top", "bottom"})


def _minimum_node_size(self, node) -> tuple[float, float]:  # noqa: ANN001
    registry = self._scene_context.registry
    model = self._scene_context.model
    if registry is None or model is None:
        return 0.0, 0.0
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return 0.0, 0.0
    spec_or_none = getattr(registry, "spec_or_none", None)
    spec = spec_or_none(node.type_id) if callable(spec_or_none) else None
    if spec is None:
        return 0.0, 0.0
    cache = self._scene_context._bridge._payload_cache
    payload = None
    if not cache.dirty and self._scene_context._payload_cache_sync.payload_cache_matches_active_view():
        if not cache.indexes_valid:
            cache.rebuild_indexes()
        status, location = cache.resolve_node_payload_slot(str(node.node_id))
        if status == "ok" and location is not None:
            collection_name, index = location
            collection = cache.nodes if collection_name == "nodes" else cache.backdrop_nodes
            payload = collection[index]
    if payload is None:
        payload = self._scene_context._payload_builder.build_node_connection_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=self._scene_context.workspace_id,
            scope_path=self._scene_context.scope_path,
            node_ids={str(node.node_id)},
            graph_theme_bridge=self._scene_context.graph_theme_bridge,
            show_port_labels=self._scene_context.graphics_show_port_labels,
            graph_label_pixel_size=self._scene_context.graphics_graph_label_pixel_size,
            graph_node_icon_pixel_size=self._scene_context.graphics_node_title_icon_pixel_size,
            lightweight_canvas=self._scene_context.graphics_lightweight_canvas,
        ).get(str(node.node_id))
    surface_metrics = payload.get("surface_metrics", {}) if isinstance(payload, dict) else {}
    try:
        return float(surface_metrics["min_width"]), float(surface_metrics["min_height"])
    except (KeyError, TypeError, ValueError):
        metrics = node_surface_metrics(
            node,
            spec,
            workspace.nodes,
            show_port_labels=self._scene_context.graphics_show_port_labels,
            graph_label_pixel_size=self._scene_context.graphics_graph_label_pixel_size,
            graph_node_icon_pixel_size=self._scene_context.graphics_node_title_icon_pixel_size,
        )
        return float(metrics.min_width), float(metrics.min_height)


def move_node(self, node_id: str, x: float, y: float) -> None:
    model = self._scene_context.model
    if model is None:
        return
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return
    if not is_node_in_scope(workspace, node_id, self._scene_context.scope_path):
        self._resync_scene_after_stale_mutation()
        return
    node = self._node(node_id)
    if node is None:
        self._resync_scene_after_stale_mutation()
        return
    final_x = float(x)
    final_y = float(y)
    if float(node.x) == final_x and float(node.y) == final_y:
        return
    history_before = self._capture_history_snapshot()
    self._record_mutations().set_node_position(node_id, final_x, final_y)
    self._scene_context.publish_node_position_delta([node_id])
    self._record_history(ACTION_MOVE_NODE, history_before)


def resize_node(self, node_id: str, width: float, height: float) -> None:
    model = self._scene_context.model
    if model is None:
        return
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return
    node = self._node(node_id)
    if node is None:
        self._resync_scene_after_stale_mutation()
        return
    if not is_node_in_scope(workspace, node_id, self._scene_context.scope_path):
        self._resync_scene_after_stale_mutation()
        return
    min_width, min_height = _minimum_node_size(self, node)
    final_width = max(min_width, float(width))
    final_height = max(min_height, float(height))
    self.set_node_geometry(node_id, float(node.x), float(node.y), final_width, final_height)


def set_node_geometry(self, node_id: str, x: float, y: float, width: float, height: float) -> None:
    model = self._scene_context.model
    if model is None:
        return
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return
    node = self._node(node_id)
    if node is None:
        self._resync_scene_after_stale_mutation()
        return
    if not is_node_in_scope(workspace, node_id, self._scene_context.scope_path):
        self._resync_scene_after_stale_mutation()
        return
    final_x = float(x)
    final_y = float(y)
    min_width, min_height = _minimum_node_size(self, node)
    final_w = max(min_width, float(width))
    final_h = max(min_height, float(height))
    if (
        float(node.x) == final_x
        and float(node.y) == final_y
        and node.custom_width == final_w
        and node.custom_height == final_h
    ):
        return
    history_before = self._capture_history_snapshot()
    self._record_mutations().set_node_geometry(node_id, final_x, final_y, final_w, final_h)
    if not self._scene_context.publish_node_geometry_delta(
        {node_id},
        publication_path="node_resize_geometry_delta",
    ):
        self._scene_context.rebuild_models()
    self._record_history(ACTION_RESIZE_NODE, history_before)


def move_nodes_by_delta(self, node_ids: list[Any], dx: float, dy: float) -> bool:
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False

    unique_node_ids: list[str] = []
    seen_node_ids: set[str] = set()
    requested_node_count = 0
    for value in node_ids:
        node_id = str(value).strip()
        if not node_id or node_id in seen_node_ids:
            continue
        seen_node_ids.add(node_id)
        requested_node_count += 1
        if node_id not in workspace.nodes:
            continue
        if not is_node_in_scope(workspace, node_id, self._scene_context.scope_path):
            continue
        unique_node_ids.append(node_id)
    if len(unique_node_ids) < requested_node_count:
        self._resync_scene_after_stale_mutation()
    if not unique_node_ids:
        return False

    delta_x = float(dx)
    delta_y = float(dy)
    if abs(delta_x) < 0.01 and abs(delta_y) < 0.01:
        return False

    moved_any = False
    history_group = self._scene_context.grouped_history_action(
        ACTION_MOVE_NODE,
        workspace,
        commit_if=lambda: moved_any,
    )
    mutations = self._record_mutations()
    with history_group:
        for node_id in unique_node_ids:
            node = workspace.nodes.get(node_id)
            if node is None:
                continue
            final_x = float(node.x) + delta_x
            final_y = float(node.y) + delta_y
            if float(node.x) == final_x and float(node.y) == final_y:
                continue
            mutations.set_node_position(node_id, final_x, final_y)
            moved_any = True

    if not moved_any:
        return False
    self._scene_context.publish_node_position_delta(unique_node_ids)
    return True


def _effective_node_size(self, workspace, node, spec) -> tuple[float, float]:  # noqa: ANN001
    width, height = resolved_node_surface_size(
        node,
        spec,
        workspace.nodes,
        show_port_labels=self._scene_context.graphics_show_port_labels,
        graph_label_pixel_size=self._scene_context.graphics_graph_label_pixel_size,
        graph_node_icon_pixel_size=self._scene_context.graphics_node_title_icon_pixel_size,
    )
    return float(width), float(height)


def set_selected_same_type_size(self, node_ids: list[Any], dimension: str) -> bool:
    axis = str(dimension or "").strip().lower()
    if axis not in {"width", "height"}:
        return False
    model = self._scene_context.model
    if model is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False

    ordered_node_ids: list[str] = []
    seen_node_ids: set[str] = set()
    for value in node_ids:
        node_id = str(value or "").strip()
        if not node_id or node_id in seen_node_ids or node_id not in workspace.nodes:
            continue
        if not is_node_in_scope(workspace, node_id, self._scene_context.scope_path):
            continue
        seen_node_ids.add(node_id)
        ordered_node_ids.append(node_id)
    if len(ordered_node_ids) < 2:
        return False

    spec_or_none = getattr(self._scene_context.registry, "spec_or_none", None)
    if not callable(spec_or_none):
        return False
    buckets: dict[str, list[str]] = {}
    effective_sizes: dict[str, tuple[float, float]] = {}
    for node_id in ordered_node_ids:
        node = workspace.nodes.get(node_id)
        if node is None:
            continue
        type_id = str(node.type_id or "").strip()
        if not type_id:
            continue
        spec = spec_or_none(type_id)
        if spec is None or str(spec.runtime_behavior or "").strip().lower() != "passive":
            continue
        size = _effective_node_size(self, workspace, node, spec)
        effective_sizes[node_id] = size
        buckets.setdefault(type_id, []).append(node_id)

    geometry_updates: dict[str, tuple[float, float, float | None, float | None]] = {}
    for bucket_node_ids in buckets.values():
        if len(bucket_node_ids) < 2:
            continue
        reference_size = effective_sizes.get(bucket_node_ids[0])
        if reference_size is None:
            continue
        target_size = reference_size[0] if axis == "width" else reference_size[1]
        for node_id in bucket_node_ids[1:]:
            node = workspace.nodes.get(node_id)
            current_size = effective_sizes.get(node_id)
            if node is None or current_size is None:
                continue
            min_width, min_height = _minimum_node_size(self, node)
            if axis == "width":
                final_width = max(min_width, target_size)
                if abs(current_size[0] - final_width) < 0.01:
                    continue
                geometry_updates[node_id] = (float(node.x), float(node.y), final_width, node.custom_height)
            else:
                final_height = max(min_height, target_size)
                if abs(current_size[1] - final_height) < 0.01:
                    continue
                geometry_updates[node_id] = (float(node.x), float(node.y), node.custom_width, final_height)

    if not geometry_updates:
        return False

    history_group = self._scene_context.grouped_history_action(ACTION_RESIZE_NODE, workspace)
    mutations = self._record_mutations()
    with history_group:
        for node_id, (final_x, final_y, final_width, final_height) in geometry_updates.items():
            mutations.set_node_geometry(node_id, final_x, final_y, final_width, final_height)
    if not self._scene_context.publish_node_geometry_delta(
        set(geometry_updates),
        publication_path="selection_same_type_size_geometry_delta",
    ):
        self._scene_context.rebuild_models()
    return True


def align_selected_nodes(
    self,
    alignment: str,
    *,
    snap_to_grid: bool = False,
    grid_size: float = SNAP_GRID_SIZE,
) -> bool:
    workspace, selected = self._selected_layout_metrics()
    if workspace is None:
        return False
    updates = build_alignment_position_updates(layout_nodes=selected, alignment=alignment)
    return self._apply_layout_updates(
        workspace,
        updates,
        snap_to_grid=snap_to_grid,
        grid_size=grid_size,
    )


def distribute_selected_nodes(
    self,
    orientation: str,
    *,
    snap_to_grid: bool = False,
    grid_size: float = SNAP_GRID_SIZE,
) -> bool:
    workspace, selected = self._selected_layout_metrics()
    if workspace is None:
        return False
    updates = build_distribution_position_updates(layout_nodes=selected, orientation=orientation)
    return self._apply_layout_updates(
        workspace,
        updates,
        snap_to_grid=snap_to_grid,
        grid_size=grid_size,
    )


def straighten_selected_connections(self) -> bool:
    model = self._scene_context.model
    registry = self._scene_context.registry
    if model is None or registry is None:
        return False
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return False
    selected_node_ids = set(self._selected_node_ids_in_workspace(workspace))
    if len(selected_node_ids) < 2:
        return False

    constraints = _straighten_connection_constraints(self, workspace, selected_node_ids)
    if not constraints:
        return False
    updates = build_straighten_connection_position_updates(
        workspace=workspace,
        constraints=constraints,
    )
    return self._apply_layout_updates(
        workspace,
        updates,
        snap_to_grid=False,
        grid_size=SNAP_GRID_SIZE,
    )


def _straighten_connection_constraints(
    self,
    workspace,
    selected_node_ids: set[str],
) -> list[PortAlignmentConstraint]:  # noqa: ANN001
    registry = self._scene_context.registry
    if registry is None:
        return []
    graph_label_pixel_size = self._scene_context.graphics_graph_label_pixel_size
    graph_node_icon_pixel_size = self._scene_context.graphics_node_title_icon_pixel_size
    constraints: list[PortAlignmentConstraint] = []
    for edge in workspace.edges.values():
        if edge.source_node_id not in selected_node_ids or edge.target_node_id not in selected_node_ids:
            continue
        source_node = workspace.nodes.get(edge.source_node_id)
        target_node = workspace.nodes.get(edge.target_node_id)
        if source_node is None or target_node is None:
            continue
        source_spec = registry.spec_or_none(source_node.type_id)
        target_spec = registry.spec_or_none(target_node.type_id)
        if source_spec is None or target_spec is None:
            continue
        source_side = _straighten_port_side(
            node=source_node,
            spec=source_spec,
            workspace_nodes=workspace.nodes,
            port_key=edge.source_port_key,
        )
        target_side = _straighten_port_side(
            node=target_node,
            spec=target_spec,
            workspace_nodes=workspace.nodes,
            port_key=edge.target_port_key,
        )
        axis = _straighten_axis(source_side, target_side)
        if axis is None:
            continue
        source_anchor = port_scene_pos(
            source_node,
            source_spec,
            edge.source_port_key,
            workspace.nodes,
            show_port_labels=self._scene_context.graphics_show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
        target_anchor = port_scene_pos(
            target_node,
            target_spec,
            edge.target_port_key,
            workspace.nodes,
            show_port_labels=self._scene_context.graphics_show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
        constraints.append(
            PortAlignmentConstraint(
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
                axis=axis,
                source_anchor=float(source_anchor.x() if axis == "x" else source_anchor.y()),
                target_anchor=float(target_anchor.x() if axis == "x" else target_anchor.y()),
            )
        )
    return constraints


def _straighten_port_side(*, node, spec, workspace_nodes, port_key: str) -> str:  # noqa: ANN001
    side = flowchart_port_side(node, spec, port_key, workspace_nodes)
    if side:
        return side
    try:
        direction = port_direction(
            node=node,
            spec=spec,
            workspace_nodes=workspace_nodes,
            port_key=port_key,
        )
    except KeyError:
        return ""
    if direction == "in":
        return "left"
    if direction == "out":
        return "right"
    return ""


def _straighten_axis(source_side: str, target_side: str) -> str | None:
    if source_side in _HORIZONTAL_PORT_SIDES and target_side in _HORIZONTAL_PORT_SIDES:
        return "y"
    if source_side in _VERTICAL_PORT_SIDES and target_side in _VERTICAL_PORT_SIDES:
        return "x"
    return None


__all__ = [
    "SNAP_GRID_SIZE",
    "align_selected_nodes",
    "distribute_selected_nodes",
    "move_node",
    "move_nodes_by_delta",
    "resize_node",
    "set_selected_same_type_size",
    "set_node_geometry",
    "straighten_selected_connections",
]
