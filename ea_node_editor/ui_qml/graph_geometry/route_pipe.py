from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF

from .anchors import flowchart_anchor_normal, flowchart_anchor_tangent
from .route_endpoints import _flow_pipe_route_sides, _rect_center_x

EDGE_FORWARD_LEAD_MIN = 56.0
EDGE_BACKWARD_VERTICAL_CLEARANCE = 56.0
EDGE_PIPE_STUB = 44.0
EDGE_PIPE_STUB_MIN = 32.0
EDGE_PIPE_STUB_MAX = 72.0
EDGE_PIPE_MIDDLE_MARGIN = 10.0


def edge_control_points(
    source: QPointF,
    target: QPointF,
    source_bounds: QRectF,
    target_bounds: QRectF,
    *,
    pair_lane: float,
    source_fan: float,
    target_fan: float,
    source_side: str = "",
    target_side: str = "",
) -> tuple[float, float, float, float]:
    normalized_source_side = str(source_side or "").strip().lower()
    normalized_target_side = str(target_side or "").strip().lower()
    if normalized_source_side and normalized_target_side:
        delta_extent = max(
            abs(float(target.x() - source.x())),
            abs(float(target.y() - source.y())),
        )
        lead = max(EDGE_FORWARD_LEAD_MIN * 0.55, min(EDGE_FORWARD_LEAD_MIN * 1.2, delta_extent * 0.42))
        lead += abs(pair_lane) * 0.2
        source_normal_x, source_normal_y = flowchart_anchor_normal(normalized_source_side)
        target_normal_x, target_normal_y = flowchart_anchor_normal(normalized_target_side)
        source_tangent_x, source_tangent_y = flowchart_anchor_tangent(normalized_source_side)
        target_tangent_x, target_tangent_y = flowchart_anchor_tangent(normalized_target_side)
        source_bias = source_fan + pair_lane * 0.35
        target_bias = target_fan - pair_lane * 0.35
        return (
            float(source.x() + source_normal_x * lead + source_tangent_x * source_bias),
            float(source.y() + source_normal_y * lead + source_tangent_y * source_bias),
            float(target.x() + target_normal_x * lead + target_tangent_x * target_bias),
            float(target.y() + target_normal_y * lead + target_tangent_y * target_bias),
        )

    dx = float(target.x() - source.x())
    lead = max(EDGE_FORWARD_LEAD_MIN, abs(dx) * 0.5)
    lead += abs(pair_lane) * 0.2
    c1x = float(source.x() + lead)
    c2x = float(target.x() - lead)
    c1y = float(source.y() + source_fan + pair_lane * 0.35)
    c2y = float(target.y() + target_fan - pair_lane * 0.35)
    return c1x, c1y, c2x, c2y


def _pipe_stub_length(source: QPointF, target: QPointF) -> float:
    dominant_gap = max(abs(float(target.x() - source.x())), abs(float(target.y() - source.y())))
    return min(
        EDGE_PIPE_STUB_MAX,
        max(EDGE_PIPE_STUB_MIN, max(EDGE_PIPE_STUB, dominant_gap * 0.2)),
    )


def _pipe_stub_point(point: QPointF, side: str, stub_length: float) -> tuple[float, float]:
    normal_x, normal_y = flowchart_anchor_normal(side)
    return (
        float(point.x() + normal_x * stub_length),
        float(point.y() + normal_y * stub_length),
    )


def _add_axis_value(values: set[float], value: float) -> None:
    if math.isfinite(value):
        values.add(float(value))


def _axis_gap_or_overlap_interval(
    a_low: float,
    a_high: float,
    b_low: float,
    b_high: float,
) -> tuple[float, float] | None:
    if a_high <= b_low:
        return float(a_high), float(b_low)
    if b_high <= a_low:
        return float(b_high), float(a_low)
    overlap_low = max(a_low, b_low)
    overlap_high = min(a_high, b_high)
    if overlap_low <= overlap_high:
        return float(overlap_low), float(overlap_high)
    return None


def _add_axis_interval_candidates(
    values: set[float],
    preferred: list[float],
    interval: tuple[float, float] | None,
    *,
    lane_bias: float,
) -> None:
    if interval is None:
        return
    low, high = interval
    center = (low + high) * 0.5
    biased = min(high, max(low, center + lane_bias * 0.35))
    _add_axis_value(values, center)
    preferred.append(center)
    if abs(biased - center) > 0.001:
        _add_axis_value(values, biased)
        preferred.insert(0, biased)


def _flow_pipe_candidate_axes(
    source: QPointF,
    target: QPointF,
    source_stub: tuple[float, float],
    target_stub: tuple[float, float],
    source_bounds: QRectF | None,
    target_bounds: QRectF | None,
    *,
    lane_bias: float,
    clearance: float,
) -> tuple[list[float], list[float], list[float], list[float]]:
    x_values: set[float] = {
        float(source.x()),
        float(target.x()),
        float(source_stub[0]),
        float(target_stub[0]),
        (float(source_stub[0]) + float(target_stub[0])) * 0.5,
    }
    y_values: set[float] = {
        float(source.y()),
        float(target.y()),
        float(source_stub[1]),
        float(target_stub[1]),
        (float(source_stub[1]) + float(target_stub[1])) * 0.5,
    }
    preferred_xs: list[float] = []
    preferred_ys: list[float] = []

    if source_bounds is not None and target_bounds is not None:
        left_bound = min(float(source_bounds.left()), float(target_bounds.left()))
        right_bound = max(float(source_bounds.right()), float(target_bounds.right()))
        top_bound = min(float(source_bounds.top()), float(target_bounds.top()))
        bottom_bound = max(float(source_bounds.bottom()), float(target_bounds.bottom()))
        _add_axis_value(x_values, left_bound - clearance - max(0.0, lane_bias))
        _add_axis_value(x_values, right_bound + clearance + max(0.0, -lane_bias))
        _add_axis_value(y_values, top_bound - clearance - max(0.0, lane_bias))
        _add_axis_value(y_values, bottom_bound + clearance + max(0.0, -lane_bias))
        _add_axis_interval_candidates(
            x_values,
            preferred_xs,
            _axis_gap_or_overlap_interval(
                float(source_bounds.left()),
                float(source_bounds.right()),
                float(target_bounds.left()),
                float(target_bounds.right()),
            ),
            lane_bias=lane_bias,
        )
        _add_axis_interval_candidates(
            y_values,
            preferred_ys,
            _axis_gap_or_overlap_interval(
                float(source_bounds.top()),
                float(source_bounds.bottom()),
                float(target_bounds.top()),
                float(target_bounds.bottom()),
            ),
            lane_bias=lane_bias,
        )

    return sorted(x_values), sorted(y_values), preferred_xs, preferred_ys


def _point_inside_bounds(point: tuple[float, float], bounds: QRectF, *, epsilon: float = 0.001) -> bool:
    x, y = point
    return (
        float(bounds.left()) + epsilon < x < float(bounds.right()) - epsilon
        and float(bounds.top()) + epsilon < y < float(bounds.bottom()) - epsilon
    )


def _segment_clear(
    start: tuple[float, float],
    end: tuple[float, float],
    obstacles: list[QRectF],
    *,
    epsilon: float = 0.001,
) -> bool:
    x1, y1 = start
    x2, y2 = end
    if abs(x1 - x2) <= epsilon:
        x = float(x1)
        low = min(float(y1), float(y2))
        high = max(float(y1), float(y2))
        for bounds in obstacles:
            if not (float(bounds.left()) + epsilon < x < float(bounds.right()) - epsilon):
                continue
            overlap_low = max(low, float(bounds.top()) + epsilon)
            overlap_high = min(high, float(bounds.bottom()) - epsilon)
            if overlap_low < overlap_high:
                return False
        return True

    if abs(y1 - y2) <= epsilon:
        y = float(y1)
        low = min(float(x1), float(x2))
        high = max(float(x1), float(x2))
        for bounds in obstacles:
            if not (float(bounds.top()) + epsilon < y < float(bounds.bottom()) - epsilon):
                continue
            overlap_low = max(low, float(bounds.left()) + epsilon)
            overlap_high = min(high, float(bounds.right()) - epsilon)
            if overlap_low < overlap_high:
                return False
        return True

    return False


def _simplify_orthogonal_points(
    points: list[tuple[float, float]],
    *,
    epsilon: float = 0.001,
) -> list[tuple[float, float]]:
    deduped: list[tuple[float, float]] = []
    for point in points:
        if deduped and abs(deduped[-1][0] - point[0]) <= epsilon and abs(deduped[-1][1] - point[1]) <= epsilon:
            continue
        deduped.append((float(point[0]), float(point[1])))
    simplified: list[tuple[float, float]] = []
    for point in deduped:
        if len(simplified) < 2:
            simplified.append(point)
            continue
        prev = simplified[-1]
        prev_prev = simplified[-2]
        if (
            abs(prev_prev[0] - prev[0]) <= epsilon
            and abs(prev[0] - point[0]) <= epsilon
        ) or (
            abs(prev_prev[1] - prev[1]) <= epsilon
            and abs(prev[1] - point[1]) <= epsilon
        ):
            simplified[-1] = point
            continue
        simplified.append(point)
    return simplified


def _polyline_score(
    points: list[tuple[float, float]],
    preferred_xs: list[float],
    preferred_ys: list[float],
) -> tuple[int, float, float]:
    bends = max(0, len(points) - 2)
    length = 0.0
    lane_penalty = 0.0
    for index in range(1, len(points)):
        start = points[index - 1]
        end = points[index]
        length += abs(end[0] - start[0]) + abs(end[1] - start[1])
        if abs(end[0] - start[0]) <= 0.001 and preferred_xs:
            lane_penalty += min(abs(start[0] - preferred_x) for preferred_x in preferred_xs)
        elif abs(end[1] - start[1]) <= 0.001 and preferred_ys:
            lane_penalty += min(abs(start[1] - preferred_y) for preferred_y in preferred_ys)
    return bends, length, lane_penalty


def _orthogonal_flow_pipe_points(
    source: QPointF,
    target: QPointF,
    source_bounds: QRectF | None,
    target_bounds: QRectF | None,
    *,
    pair_lane: float,
    source_fan: float,
    target_fan: float,
    source_side: str = "",
    target_side: str = "",
) -> list[dict[str, float]]:
    route_source_side, route_target_side = _flow_pipe_route_sides(source_side, target_side)
    lane_bias = pair_lane + source_fan - target_fan
    stub_length = _pipe_stub_length(source, target)
    source_stub = _pipe_stub_point(source, route_source_side, stub_length)
    target_stub = _pipe_stub_point(target, route_target_side, stub_length)
    clearance = EDGE_BACKWARD_VERTICAL_CLEARANCE * 0.6 + abs(lane_bias) * 0.8
    x_candidates, y_candidates, preferred_xs, preferred_ys = _flow_pipe_candidate_axes(
        source,
        target,
        source_stub,
        target_stub,
        source_bounds,
        target_bounds,
        lane_bias=lane_bias,
        clearance=clearance,
    )
    obstacles = [bounds for bounds in (source_bounds, target_bounds) if bounds is not None]
    start = (float(source.x()), float(source.y()))
    end = (float(target.x()), float(target.y()))
    route_candidates: list[list[tuple[float, float]]] = [
        [source_stub, target_stub],
        [source_stub, (source_stub[0], target_stub[1]), target_stub],
        [source_stub, (target_stub[0], source_stub[1]), target_stub],
    ]
    for candidate_x in x_candidates:
        route_candidates.append(
            [source_stub, (candidate_x, source_stub[1]), (candidate_x, target_stub[1]), target_stub]
        )
    for candidate_y in y_candidates:
        route_candidates.append(
            [source_stub, (source_stub[0], candidate_y), (target_stub[0], candidate_y), target_stub]
        )
    for candidate_x in x_candidates:
        for candidate_y in y_candidates:
            route_candidates.append(
                [
                    source_stub,
                    (candidate_x, source_stub[1]),
                    (candidate_x, candidate_y),
                    (target_stub[0], candidate_y),
                    target_stub,
                ]
            )
            route_candidates.append(
                [
                    source_stub,
                    (source_stub[0], candidate_y),
                    (candidate_x, candidate_y),
                    (candidate_x, target_stub[1]),
                    target_stub,
                ]
            )

    best_points: list[tuple[float, float]] | None = None
    best_score: tuple[int, float, float] | None = None
    for candidate in route_candidates:
        routed_points = _simplify_orthogonal_points(candidate)
        interior_points = routed_points[1:-1]
        if any(_point_inside_bounds(point, bounds) for bounds in obstacles for point in interior_points):
            continue
        if not all(
            _segment_clear(routed_points[index - 1], routed_points[index], obstacles)
            for index in range(1, len(routed_points))
        ):
            continue
        points = _simplify_orthogonal_points([start, *routed_points, end])
        score = _polyline_score(points, preferred_xs, preferred_ys)
        if best_score is None or score < best_score:
            best_points = points
            best_score = score

    if best_points is None:
        return edge_pipe_points(
            source,
            target,
            source_bounds if source_bounds is not None else QRectF(),
            target_bounds if target_bounds is not None else QRectF(),
            pair_lane=pair_lane,
            source_fan=source_fan,
            target_fan=target_fan,
            source_side=route_source_side,
            target_side=route_target_side,
        )

    return [{"x": float(point[0]), "y": float(point[1])} for point in best_points]


def _pipe_control_handles(pipe_points: list[dict[str, float]]) -> tuple[tuple[float, float], tuple[float, float]]:
    if not pipe_points:
        return (0.0, 0.0), (0.0, 0.0)
    first = pipe_points[min(1, len(pipe_points) - 1)]
    last = pipe_points[max(0, len(pipe_points) - 2)]
    return (float(first["x"]), float(first["y"])), (float(last["x"]), float(last["y"]))


def _should_use_flow_pipe_route(
    source: QPointF,
    target: QPointF,
    source_bounds: QRectF,
    target_bounds: QRectF,
    source_side: str = "",
    target_side: str = "",
) -> bool:
    normalized_source_side, normalized_target_side = _flow_pipe_route_sides(source_side, target_side)
    dx = float(target.x() - source.x())
    dy = float(target.y() - source.y())
    horizontal_gap = float(target_bounds.left() - source_bounds.right())
    center_dx = abs(_rect_center_x(target_bounds) - _rect_center_x(source_bounds))
    max_width = max(float(source_bounds.width()), float(target_bounds.width()))
    min_width = min(float(source_bounds.width()), float(target_bounds.width()))
    overlap = float(source_bounds.left()) <= float(target_bounds.right()) and float(target_bounds.left()) <= float(source_bounds.right())
    stacked_vertical = dy >= 42.0 and center_dx <= max_width * 0.78
    near_vertical = abs(dx) <= max(96.0, min_width * 0.42) and dy >= 24.0
    cramped_forward = horizontal_gap <= max(56.0, min_width * 0.22)
    if normalized_source_side in {"top", "bottom"} and normalized_target_side in {"top", "bottom"}:
        if abs(dx) <= max(96.0, min_width * 0.42):
            return abs(dy) >= 24.0
    return dx < 104.0 or overlap or stacked_vertical or (near_vertical and cramped_forward)


def _transpose_point(point: QPointF) -> QPointF:
    return QPointF(float(point.y()), float(point.x()))


def _transpose_rect(bounds: QRectF) -> QRectF:
    return QRectF(float(bounds.y()), float(bounds.x()), float(bounds.height()), float(bounds.width()))


def _transpose_pipe_points(points: list[dict[str, float]]) -> list[dict[str, float]]:
    return [{"x": float(point["y"]), "y": float(point["x"])} for point in points]


def _horizontal_edge_pipe_points(
    source: QPointF,
    target: QPointF,
    source_bounds: QRectF,
    target_bounds: QRectF,
    *,
    pair_lane: float,
    source_fan: float,
    target_fan: float,
) -> list[dict[str, float]]:
    dx = float(target.x() - source.x())
    stub = min(EDGE_PIPE_STUB_MAX, max(EDGE_PIPE_STUB_MIN, max(EDGE_PIPE_STUB, abs(dx) * 0.2)))
    source_stub_x = float(max(source_bounds.right(), source.x()) + stub)
    target_stub_x = float(min(target_bounds.left(), target.x()) - stub)

    if source_stub_x <= target_stub_x:
        mid_x = (source_stub_x + target_stub_x) * 0.5
        source_stub_x = mid_x + EDGE_PIPE_STUB * 0.5
        target_stub_x = mid_x - EDGE_PIPE_STUB * 0.5

    vertical_clearance = EDGE_BACKWARD_VERTICAL_CLEARANCE * 0.6 + abs(pair_lane) * 0.8
    lane_bias = pair_lane + source_fan - target_fan
    top_bound = float(min(source_bounds.top(), target_bounds.top()))
    bottom_bound = float(max(source_bounds.bottom(), target_bounds.bottom()))
    top_route_y = float(top_bound - vertical_clearance - max(0.0, lane_bias))
    bottom_route_y = float(bottom_bound + vertical_clearance + max(0.0, -lane_bias))
    source_y = float(source.y())
    target_y = float(target.y())

    def route_len(route_y: float) -> float:
        return (
            abs(source_stub_x - float(source.x()))
            + abs(route_y - source_y)
            + abs(source_stub_x - target_stub_x)
            + abs(target_y - route_y)
            + abs(float(target.x()) - target_stub_x)
        )

    route_candidates: list[tuple[float, int]] = [
        (top_route_y, 1),
        (bottom_route_y, 1),
    ]

    middle_low: float | None = None
    middle_high: float | None = None
    source_bottom = float(source_bounds.bottom())
    source_top = float(source_bounds.top())
    target_bottom = float(target_bounds.bottom())
    target_top = float(target_bounds.top())
    if source_bottom + EDGE_PIPE_MIDDLE_MARGIN <= target_top - EDGE_PIPE_MIDDLE_MARGIN:
        middle_low = source_bottom + EDGE_PIPE_MIDDLE_MARGIN
        middle_high = target_top - EDGE_PIPE_MIDDLE_MARGIN
    elif target_bottom + EDGE_PIPE_MIDDLE_MARGIN <= source_top - EDGE_PIPE_MIDDLE_MARGIN:
        middle_low = target_bottom + EDGE_PIPE_MIDDLE_MARGIN
        middle_high = source_top - EDGE_PIPE_MIDDLE_MARGIN

    if middle_low is not None and middle_high is not None and middle_low <= middle_high:
        preferred_middle = (source_y + target_y) * 0.5 + lane_bias * 0.35
        middle_route_y = min(middle_high, max(middle_low, preferred_middle))
        route_candidates.append((middle_route_y, 0))

    route_y = min(route_candidates, key=lambda item: (route_len(item[0]), item[1]))[0]

    return [
        {"x": float(source.x()), "y": source_y},
        {"x": source_stub_x, "y": source_y},
        {"x": source_stub_x, "y": route_y},
        {"x": target_stub_x, "y": route_y},
        {"x": target_stub_x, "y": target_y},
        {"x": float(target.x()), "y": target_y},
    ]


def _mixed_cardinal_pipe_points(
    source: QPointF,
    target: QPointF,
    *,
    pair_lane: float,
    source_side: str,
    target_side: str,
) -> list[dict[str, float]]:
    source_normal_x, source_normal_y = flowchart_anchor_normal(source_side)
    target_normal_x, target_normal_y = flowchart_anchor_normal(target_side)
    stub = EDGE_PIPE_STUB
    source_stub = {
        "x": float(source.x() + source_normal_x * stub),
        "y": float(source.y() + source_normal_y * stub),
    }
    target_stub = {
        "x": float(target.x() + target_normal_x * stub),
        "y": float(target.y() + target_normal_y * stub),
    }
    if source_side in {"left", "right"}:
        middle_x = (source_stub["x"] + target_stub["x"]) * 0.5 + pair_lane * 0.25
        return [
            {"x": float(source.x()), "y": float(source.y())},
            source_stub,
            {"x": middle_x, "y": source_stub["y"]},
            {"x": middle_x, "y": target_stub["y"]},
            target_stub,
            {"x": float(target.x()), "y": float(target.y())},
        ]
    middle_y = (source_stub["y"] + target_stub["y"]) * 0.5 + pair_lane * 0.25
    return [
        {"x": float(source.x()), "y": float(source.y())},
        source_stub,
        {"x": source_stub["x"], "y": middle_y},
        {"x": target_stub["x"], "y": middle_y},
        target_stub,
        {"x": float(target.x()), "y": float(target.y())},
    ]


def edge_pipe_points(
    source: QPointF,
    target: QPointF,
    source_bounds: QRectF,
    target_bounds: QRectF,
    *,
    pair_lane: float,
    source_fan: float,
    target_fan: float,
    source_side: str = "",
    target_side: str = "",
) -> list[dict[str, float]]:
    normalized_source_side = str(source_side or "").strip().lower()
    normalized_target_side = str(target_side or "").strip().lower()
    if normalized_source_side in {"top", "bottom"} and normalized_target_side in {"top", "bottom"}:
        return _transpose_pipe_points(
            _horizontal_edge_pipe_points(
                _transpose_point(source),
                _transpose_point(target),
                _transpose_rect(source_bounds),
                _transpose_rect(target_bounds),
                pair_lane=pair_lane,
                source_fan=source_fan,
                target_fan=target_fan,
            )
        )
    if normalized_source_side and normalized_target_side and (
        normalized_source_side in {"top", "bottom"} or normalized_target_side in {"top", "bottom"}
    ):
        return _mixed_cardinal_pipe_points(
            source,
            target,
            pair_lane=pair_lane,
            source_side=normalized_source_side,
            target_side=normalized_target_side,
        )
    return _horizontal_edge_pipe_points(
        source,
        target,
        source_bounds,
        target_bounds,
        pair_lane=pair_lane,
        source_fan=source_fan,
        target_fan=target_fan,
    )
