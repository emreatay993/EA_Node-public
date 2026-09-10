from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ea_node_editor.graph.hierarchy import ScopePath

GROUP_BACKDROP_WRAP_PADDING = 32.0
# Keep a visible gap after active-node shadow overflow.
GROUP_BACKDROP_WRAP_BOTTOM_PADDING = 56.0
GROUP_BACKDROP_WRAP_TOP_PADDING = 96.0
GROUP_BACKDROP_WRAP_MIN_WIDTH = 240.0
GROUP_BACKDROP_WRAP_MIN_HEIGHT = 160.0


@dataclass(slots=True, frozen=True)
class GroupBackdropCandidate:
    node_id: str
    scope_path: ScopePath
    is_backdrop: bool
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(slots=True, frozen=True)
class GroupBackdropMembership:
    owner_backdrop_id: str | None = None
    backdrop_depth: int = 0
    member_node_ids: tuple[str, ...] = ()
    member_backdrop_ids: tuple[str, ...] = ()
    contained_node_ids: tuple[str, ...] = ()
    contained_backdrop_ids: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class GroupBackdropBounds:
    x: float
    y: float
    width: float
    height: float


@dataclass(slots=True, frozen=True)
class GroupBackdropWrapResult:
    backdrop_node_id: str
    wrapped_node_ids: tuple[str, ...]
    scope_path: ScopePath
    x: float
    y: float
    width: float
    height: float


def compute_group_backdrop_membership(
    candidates: Sequence[GroupBackdropCandidate],
) -> dict[str, GroupBackdropMembership]:
    candidate_by_id = {candidate.node_id: candidate for candidate in candidates}
    backdrop_candidates = [candidate for candidate in candidates if candidate.is_backdrop]
    direct_owner_by_id: dict[str, str | None] = {}

    for candidate in candidates:
        containing_backdrops = [
            backdrop
            for backdrop in backdrop_candidates
            if _can_directly_own(backdrop, candidate)
        ]
        containing_backdrops.sort(
            key=lambda backdrop: (
                float(backdrop.area),
                float(backdrop.width),
                float(backdrop.height),
                float(backdrop.x),
                float(backdrop.y),
                backdrop.node_id,
            )
        )
        direct_owner_by_id[candidate.node_id] = containing_backdrops[0].node_id if containing_backdrops else None

    direct_node_members: dict[str, list[str]] = {backdrop.node_id: [] for backdrop in backdrop_candidates}
    direct_backdrop_members: dict[str, list[str]] = {backdrop.node_id: [] for backdrop in backdrop_candidates}
    for candidate in candidates:
        owner_id = direct_owner_by_id.get(candidate.node_id)
        if not owner_id:
            continue
        if candidate.is_backdrop:
            direct_backdrop_members.setdefault(owner_id, []).append(candidate.node_id)
        else:
            direct_node_members.setdefault(owner_id, []).append(candidate.node_id)

    for member_ids in direct_node_members.values():
        member_ids.sort()
    for member_ids in direct_backdrop_members.values():
        member_ids.sort()

    depth_cache: dict[str, int] = {}

    def depth_for(node_id: str) -> int:
        cached = depth_cache.get(node_id)
        if cached is not None:
            return cached
        owner_id = direct_owner_by_id.get(node_id)
        if not owner_id:
            depth_cache[node_id] = 0
            return 0
        depth = depth_for(owner_id) + 1
        depth_cache[node_id] = depth
        return depth

    contained_cache: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}

    def contained_for(backdrop_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        cached = contained_cache.get(backdrop_id)
        if cached is not None:
            return cached

        contained_node_ids = list(direct_node_members.get(backdrop_id, ()))
        contained_backdrop_ids = list(direct_backdrop_members.get(backdrop_id, ()))
        for child_backdrop_id in direct_backdrop_members.get(backdrop_id, ()):
            child_nodes, child_backdrops = contained_for(child_backdrop_id)
            contained_node_ids.extend(child_nodes)
            contained_backdrop_ids.extend(child_backdrops)

        result = (tuple(sorted(contained_node_ids)), tuple(sorted(contained_backdrop_ids)))
        contained_cache[backdrop_id] = result
        return result

    membership_by_id: dict[str, GroupBackdropMembership] = {}
    for candidate in candidates:
        member_node_ids: tuple[str, ...] = ()
        member_backdrop_ids: tuple[str, ...] = ()
        contained_node_ids: tuple[str, ...] = ()
        contained_backdrop_ids: tuple[str, ...] = ()
        if candidate.is_backdrop:
            member_node_ids = tuple(direct_node_members.get(candidate.node_id, ()))
            member_backdrop_ids = tuple(direct_backdrop_members.get(candidate.node_id, ()))
            contained_node_ids, contained_backdrop_ids = contained_for(candidate.node_id)
        membership_by_id[candidate.node_id] = GroupBackdropMembership(
            owner_backdrop_id=direct_owner_by_id.get(candidate.node_id),
            backdrop_depth=depth_for(candidate.node_id),
            member_node_ids=member_node_ids,
            member_backdrop_ids=member_backdrop_ids,
            contained_node_ids=contained_node_ids,
            contained_backdrop_ids=contained_backdrop_ids,
        )
    return membership_by_id


def build_group_backdrop_wrap_bounds(
    candidates: Sequence[GroupBackdropCandidate],
    *,
    padding: float = GROUP_BACKDROP_WRAP_PADDING,
    top_padding: float = GROUP_BACKDROP_WRAP_TOP_PADDING,
    min_width: float = GROUP_BACKDROP_WRAP_MIN_WIDTH,
    min_height: float = GROUP_BACKDROP_WRAP_MIN_HEIGHT,
) -> GroupBackdropBounds | None:
    if not candidates:
        return None

    left = min(candidate.x for candidate in candidates)
    top = min(candidate.y for candidate in candidates)
    right = max(candidate.right for candidate in candidates)
    bottom = max(candidate.bottom for candidate in candidates)

    padded_x = float(left) - float(padding)
    padded_y = float(top) - float(top_padding)
    padded_width = (float(right) - float(left)) + (float(padding) * 2.0)
    padded_height = (float(bottom) - float(top)) + float(top_padding) + GROUP_BACKDROP_WRAP_BOTTOM_PADDING

    final_width = max(float(min_width), padded_width)
    final_height = max(float(min_height), padded_height)
    final_x = padded_x - ((final_width - padded_width) * 0.5)
    final_y = padded_y - ((final_height - padded_height) * 0.5)
    return GroupBackdropBounds(
        x=final_x,
        y=final_y,
        width=final_width,
        height=final_height,
    )


def build_group_backdrop_occupied_bounds(
    backdrop: GroupBackdropCandidate,
    direct_members: Sequence[GroupBackdropCandidate],
) -> GroupBackdropBounds:
    candidates = [backdrop, *list(direct_members)]
    left = min(candidate.x for candidate in candidates)
    top = min(candidate.y for candidate in candidates)
    right = max(candidate.right for candidate in candidates)
    bottom = max(candidate.bottom for candidate in candidates)
    return GroupBackdropBounds(
        x=float(left),
        y=float(top),
        width=float(right) - float(left),
        height=float(bottom) - float(top),
    )


def _can_directly_own(owner: GroupBackdropCandidate, candidate: GroupBackdropCandidate) -> bool:
    if not owner.is_backdrop or owner.node_id == candidate.node_id:
        return False
    if owner.scope_path != candidate.scope_path:
        return False
    return _strictly_contains(owner, candidate)


def _strictly_contains(owner: GroupBackdropCandidate, candidate: GroupBackdropCandidate) -> bool:
    if owner.width <= 0.0 or owner.height <= 0.0:
        return False
    if candidate.width <= 0.0 or candidate.height <= 0.0:
        return False
    if owner.x > candidate.x or owner.y > candidate.y:
        return False
    if owner.right < candidate.right or owner.bottom < candidate.bottom:
        return False
    return (
        owner.x < candidate.x
        or owner.y < candidate.y
        or owner.right > candidate.right
        or owner.bottom > candidate.bottom
    )


__all__ = [
    "GROUP_BACKDROP_WRAP_MIN_HEIGHT",
    "GROUP_BACKDROP_WRAP_MIN_WIDTH",
    "GROUP_BACKDROP_WRAP_BOTTOM_PADDING",
    "GROUP_BACKDROP_WRAP_PADDING",
    "GROUP_BACKDROP_WRAP_TOP_PADDING",
    "GroupBackdropBounds",
    "GroupBackdropCandidate",
    "GroupBackdropMembership",
    "GroupBackdropWrapResult",
    "build_group_backdrop_occupied_bounds",
    "build_group_backdrop_wrap_bounds",
    "compute_group_backdrop_membership",
]
