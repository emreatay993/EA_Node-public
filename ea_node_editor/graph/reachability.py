from __future__ import annotations

from collections.abc import Iterable

from ea_node_editor.graph.workspace_state import WorkspaceData, WorkspaceSnapshot


def downstream_node_ids(
    workspace: WorkspaceData | WorkspaceSnapshot,
    root_node_ids: Iterable[object],
    *,
    include_roots: bool = False,
) -> tuple[str, ...]:
    roots = tuple(
        normalized
        for normalized in (str(node_id or "").strip() for node_id in root_node_ids)
        if normalized
    )
    if not roots:
        return ()

    known_node_ids = set(workspace.nodes)
    children_by_source: dict[str, set[str]] = {}
    for edge in workspace.edges.values():
        source_node_id = str(edge.source_node_id or "").strip()
        target_node_id = str(edge.target_node_id or "").strip()
        if (
            not source_node_id
            or not target_node_id
            or source_node_id not in known_node_ids
            or target_node_id not in known_node_ids
        ):
            continue
        children_by_source.setdefault(source_node_id, set()).add(target_node_id)

    visited: set[str] = set(roots if include_roots else ())
    queue = [root for root in sorted(set(roots)) if root in known_node_ids]
    while queue:
        current_id = queue.pop(0)
        for child_id in sorted(children_by_source.get(current_id, ())):
            if child_id in visited:
                continue
            visited.add(child_id)
            queue.append(child_id)
    if not include_roots:
        visited.difference_update(roots)
    return tuple(sorted(visited))


__all__ = ["downstream_node_ids"]
