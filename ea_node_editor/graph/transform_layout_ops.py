from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Mapping, Sequence

from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.node_specs import NodeTypeSpec

_DEFAULT_LAYOUT_GRID_SIZE = 20.0


@dataclass(slots=True, frozen=True)
class LayoutNodeBounds:
    node_id: str
    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + (self.width * 0.5)

    @property
    def center_y(self) -> float:
        return self.y + (self.height * 0.5)

    def translated(self, dx: float, dy: float) -> "LayoutNodeBounds":
        return LayoutNodeBounds(
            node_id=self.node_id,
            x=self.x + float(dx),
            y=self.y + float(dy),
            width=self.width,
            height=self.height,
        )

    def inflated(self, amount: float) -> "LayoutNodeBounds":
        normalized = max(0.0, float(amount))
        return LayoutNodeBounds(
            node_id=self.node_id,
            x=self.x - normalized,
            y=self.y - normalized,
            width=self.width + (normalized * 2.0),
            height=self.height + (normalized * 2.0),
        )


@dataclass(slots=True, frozen=True)
class PortAlignmentConstraint:
    source_node_id: str
    target_node_id: str
    axis: str
    source_anchor: float
    target_anchor: float


def collect_layout_node_bounds(
    *,
    workspace: WorkspaceData,
    node_ids: Sequence[str],
    spec_lookup: Callable[[str], NodeTypeSpec],
    size_resolver: Callable[[NodeInstance, NodeTypeSpec, Mapping[str, NodeInstance]], tuple[float, float]],
) -> list[LayoutNodeBounds]:
    layout_nodes: list[LayoutNodeBounds] = []
    for node_id in node_ids:
        node = workspace.nodes.get(node_id)
        if node is None:
            continue
        spec = spec_lookup(node.type_id)
        width, height = size_resolver(node, spec, workspace.nodes)
        layout_nodes.append(
            LayoutNodeBounds(
                node_id=node_id,
                x=float(node.x),
                y=float(node.y),
                width=float(width),
                height=float(height),
            )
        )
    return layout_nodes


def snap_coordinate(value: float, grid_size: float, *, default_step: float = _DEFAULT_LAYOUT_GRID_SIZE) -> float:
    step = float(grid_size)
    if not math.isfinite(step) or step <= 0.0:
        step = float(default_step)
    target = float(value)
    if not math.isfinite(target):
        return 0.0
    return round(target / step) * step


def build_alignment_position_updates(
    *,
    layout_nodes: Sequence[LayoutNodeBounds],
    alignment: str,
) -> dict[str, tuple[float, float]]:
    normalized_alignment = str(alignment).strip().lower()
    if normalized_alignment not in {"left", "right", "top", "bottom"}:
        return {}
    if len(layout_nodes) < 2:
        return {}

    updates: dict[str, tuple[float, float]] = {}
    if normalized_alignment == "left":
        target_left = min(node.left for node in layout_nodes)
        for node in layout_nodes:
            updates[node.node_id] = (target_left, node.y)
    elif normalized_alignment == "right":
        target_right = max(node.right for node in layout_nodes)
        for node in layout_nodes:
            updates[node.node_id] = (target_right - node.width, node.y)
    elif normalized_alignment == "top":
        target_top = min(node.top for node in layout_nodes)
        for node in layout_nodes:
            updates[node.node_id] = (node.x, target_top)
    else:
        target_bottom = max(node.bottom for node in layout_nodes)
        for node in layout_nodes:
            updates[node.node_id] = (node.x, target_bottom - node.height)
    return updates


def build_distribution_position_updates(
    *,
    layout_nodes: Sequence[LayoutNodeBounds],
    orientation: str,
) -> dict[str, tuple[float, float]]:
    normalized_orientation = str(orientation).strip().lower()
    if normalized_orientation not in {"horizontal", "vertical"}:
        return {}
    if len(layout_nodes) < 3:
        return {}

    updates: dict[str, tuple[float, float]] = {}
    if normalized_orientation == "horizontal":
        ordered = sorted(layout_nodes, key=lambda node: (node.left, node.top, node.node_id))
        total_span = ordered[-1].right - ordered[0].left
        total_size = sum(node.width for node in ordered)
        gap = (total_span - total_size) / float(len(ordered) - 1)
        cursor = ordered[0].right + gap
        for node in ordered[1:-1]:
            updates[node.node_id] = (cursor, node.y)
            cursor += node.width + gap
    else:
        ordered = sorted(layout_nodes, key=lambda node: (node.top, node.left, node.node_id))
        total_span = ordered[-1].bottom - ordered[0].top
        total_size = sum(node.height for node in ordered)
        gap = (total_span - total_size) / float(len(ordered) - 1)
        cursor = ordered[0].bottom + gap
        for node in ordered[1:-1]:
            updates[node.node_id] = (node.x, cursor)
            cursor += node.height + gap
    return updates


def build_straighten_connection_position_updates(
    *,
    workspace: WorkspaceData,
    constraints: Sequence[PortAlignmentConstraint],
    tolerance: float = 0.01,
) -> dict[str, tuple[float, float]]:
    updates: dict[str, list[float]] = {}
    for axis in ("x", "y"):
        axis_offsets = _straighten_axis_offsets(
            workspace=workspace,
            constraints=constraints,
            axis=axis,
            tolerance=tolerance,
        )
        for node_id, delta in axis_offsets.items():
            node = workspace.nodes.get(node_id)
            if node is None:
                continue
            current = updates.setdefault(node_id, [float(node.x), float(node.y)])
            if axis == "x":
                current[0] = float(node.x) + delta
            else:
                current[1] = float(node.y) + delta
    return {node_id: (position[0], position[1]) for node_id, position in updates.items()}


def _straighten_axis_offsets(
    *,
    workspace: WorkspaceData,
    constraints: Sequence[PortAlignmentConstraint],
    axis: str,
    tolerance: float,
) -> dict[str, float]:
    adjacency: dict[str, list[tuple[str, float]]] = {}
    for constraint in constraints:
        if str(constraint.axis).strip().lower() != axis:
            continue
        source_id = str(constraint.source_node_id).strip()
        target_id = str(constraint.target_node_id).strip()
        if not source_id or not target_id or source_id == target_id:
            continue
        if source_id not in workspace.nodes or target_id not in workspace.nodes:
            continue
        required_delta = float(constraint.source_anchor) - float(constraint.target_anchor)
        if not math.isfinite(required_delta):
            continue
        adjacency.setdefault(source_id, []).append((target_id, required_delta))
        adjacency.setdefault(target_id, []).append((source_id, -required_delta))

    offsets: dict[str, float] = {}
    visited: set[str] = set()
    for root_id in sorted(adjacency):
        if root_id in visited:
            continue
        relative, conflicted = _solve_straighten_axis_component(
            adjacency,
            root_id,
            tolerance=tolerance,
        )
        visited.update(relative)
        if conflicted:
            continue
        shift = -_median(tuple(relative.values()))
        for node_id, value in relative.items():
            delta = value + shift
            if abs(delta) > tolerance:
                offsets[node_id] = delta
    return offsets


def _solve_straighten_axis_component(
    adjacency: Mapping[str, Sequence[tuple[str, float]]],
    root_id: str,
    *,
    tolerance: float,
) -> tuple[dict[str, float], bool]:
    assigned = {root_id: 0.0}
    stack = [root_id]
    conflicted = False
    while stack:
        node_id = stack.pop()
        base = assigned[node_id]
        for neighbor_id, delta in adjacency.get(node_id, ()):
            target = base + delta
            existing = assigned.get(neighbor_id)
            if existing is None:
                assigned[neighbor_id] = target
                stack.append(neighbor_id)
            elif abs(existing - target) > tolerance:
                conflicted = True
    return assigned, conflicted


def _median(values: Sequence[float]) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) * 0.5


def normalize_layout_position_updates(
    *,
    workspace: WorkspaceData,
    updates: Mapping[str, tuple[float, float]],
    snap_to_grid: bool,
    grid_size: float,
    default_grid_size: float = _DEFAULT_LAYOUT_GRID_SIZE,
) -> dict[str, tuple[float, float]]:
    final_positions: dict[str, tuple[float, float]] = {}
    for node_id, (x_value, y_value) in updates.items():
        node = workspace.nodes.get(node_id)
        if node is None:
            continue
        final_x = float(x_value)
        final_y = float(y_value)
        if snap_to_grid:
            final_x = snap_coordinate(final_x, grid_size, default_step=default_grid_size)
            final_y = snap_coordinate(final_y, grid_size, default_step=default_grid_size)
        if float(node.x) == final_x and float(node.y) == final_y:
            continue
        final_positions[node_id] = (final_x, final_y)
    return final_positions


def build_expand_collision_avoidance_position_updates(
    *,
    fixed_bounds: LayoutNodeBounds,
    movable_bounds: Sequence[LayoutNodeBounds],
    gap: float,
    reach_radius: float | None = None,
) -> dict[str, tuple[float, float]]:
    normalized_gap = max(0.0, float(gap))
    reach_bounds = fixed_bounds.inflated(float(reach_radius)) if reach_radius is not None else None
    remaining = {
        bounds.node_id: bounds
        for bounds in movable_bounds
        if bounds.node_id and bounds.width > 0.0 and bounds.height > 0.0
    }
    resolved_bounds = [fixed_bounds]
    updates: dict[str, tuple[float, float]] = {}

    while remaining:
        colliding = [
            (
                _bounds_distance(bounds, fixed_bounds),
                bounds.node_id,
                bounds,
            )
            for bounds in remaining.values()
            if (reach_bounds is None or _rects_intersect(bounds, reach_bounds))
            and _first_intersecting_bounds(bounds, resolved_bounds, normalized_gap) is not None
        ]
        if not colliding:
            break
        _distance, node_id, bounds = min(colliding, key=lambda item: (item[0], item[1]))
        final_bounds = _separate_from_bounds(bounds, resolved_bounds, normalized_gap)
        if final_bounds.x != bounds.x or final_bounds.y != bounds.y:
            updates[node_id] = (final_bounds.x, final_bounds.y)
        resolved_bounds.append(final_bounds)
        remaining.pop(node_id, None)
    return updates


def _separate_from_bounds(
    bounds: LayoutNodeBounds,
    blockers: Sequence[LayoutNodeBounds],
    gap: float,
) -> LayoutNodeBounds:
    resolved = bounds
    for _attempt in range(max(1, len(blockers) * 4)):
        blocker = _first_intersecting_bounds(resolved, blockers, gap)
        if blocker is None:
            return resolved
        dx, dy = _nearest_separation_delta(resolved, blocker, gap)
        if dx == 0.0 and dy == 0.0:
            return resolved
        resolved = resolved.translated(dx, dy)
    return resolved


def _first_intersecting_bounds(
    bounds: LayoutNodeBounds,
    blockers: Sequence[LayoutNodeBounds],
    gap: float,
) -> LayoutNodeBounds | None:
    candidates = [
        blocker
        for blocker in blockers
        if blocker.node_id != bounds.node_id and _rects_intersect(bounds, blocker.inflated(gap))
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda blocker: (
            _bounds_distance(bounds, blocker),
            blocker.node_id,
        ),
    )


def _nearest_separation_delta(
    bounds: LayoutNodeBounds,
    blocker: LayoutNodeBounds,
    gap: float,
) -> tuple[float, float]:
    moves = [
        ("left", blocker.left - gap - bounds.right, 0.0),
        ("right", blocker.right + gap - bounds.left, 0.0),
        ("up", 0.0, blocker.top - gap - bounds.bottom),
        ("down", 0.0, blocker.bottom + gap - bounds.top),
    ]
    preferred = _preferred_separation_sides(bounds, blocker)
    side, dx, dy = min(
        moves,
        key=lambda item: (
            abs(item[1]) + abs(item[2]),
            0 if item[0] in preferred else 1,
            item[0],
        ),
    )
    del side
    return float(dx), float(dy)


def _preferred_separation_sides(bounds: LayoutNodeBounds, blocker: LayoutNodeBounds) -> set[str]:
    dx = bounds.center_x - blocker.center_x
    dy = bounds.center_y - blocker.center_y
    preferred = {"right" if dx >= 0.0 else "left"}
    preferred.add("down" if dy >= 0.0 else "up")
    return preferred


def _rects_intersect(first: LayoutNodeBounds, second: LayoutNodeBounds) -> bool:
    return (
        first.left < second.right
        and first.right > second.left
        and first.top < second.bottom
        and first.bottom > second.top
    )


def _bounds_distance(first: LayoutNodeBounds, second: LayoutNodeBounds) -> float:
    dx = first.center_x - second.center_x
    dy = first.center_y - second.center_y
    return (dx * dx) + (dy * dy)


__all__ = [
    "LayoutNodeBounds",
    "PortAlignmentConstraint",
    "build_alignment_position_updates",
    "build_distribution_position_updates",
    "build_expand_collision_avoidance_position_updates",
    "build_straighten_connection_position_updates",
    "collect_layout_node_bounds",
    "normalize_layout_position_updates",
    "snap_coordinate",
]
