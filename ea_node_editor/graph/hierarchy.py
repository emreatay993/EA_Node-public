from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.graph.workspace_state import WorkspaceData

ScopePath = tuple[str, ...]


def normalize_scope_path(workspace: WorkspaceData, scope_path: Sequence[object] | None) -> ScopePath:
    if not scope_path:
        return ()
    normalized: list[str] = []
    parent_id: str | None = None
    for value in scope_path:
        node_id = str(value).strip()
        if not node_id:
            break
        node = workspace.nodes.get(node_id)
        if node is None:
            break
        if node.parent_node_id != parent_id:
            break
        normalized.append(node_id)
        parent_id = node_id
    return tuple(normalized)


def scope_parent_id(scope_path: Sequence[object] | None) -> str | None:
    if not scope_path:
        return None
    normalized = [str(value).strip() for value in scope_path if str(value).strip()]
    if not normalized:
        return None
    return normalized[-1]


def parent_to_children_map(workspace: WorkspaceData) -> dict[str | None, list[str]]:
    mapping: dict[str | None, list[str]] = defaultdict(list)
    for node_id, node in workspace.nodes.items():
        mapping[node.parent_node_id].append(node_id)
    for node_ids in mapping.values():
        node_ids.sort()
    return dict(mapping)


def direct_child_node_ids(workspace: WorkspaceData, scope_path: Sequence[object] | None) -> list[str]:
    parent_id = scope_parent_id(scope_path)
    children = [
        node_id
        for node_id, node in workspace.nodes.items()
        if node.parent_node_id == parent_id
    ]
    children.sort()
    return children


def direct_child_nodes(workspace: WorkspaceData, scope_path: Sequence[object] | None) -> list[NodeInstance]:
    node_ids = direct_child_node_ids(workspace, scope_path)
    return [workspace.nodes[node_id] for node_id in node_ids]


def scope_node_ids(workspace: WorkspaceData, scope_path: Sequence[object] | None) -> list[str]:
    normalized_scope = normalize_scope_path(workspace, scope_path)
    return direct_child_node_ids(workspace, normalized_scope)


def scope_edges(workspace: WorkspaceData, scope_path: Sequence[object] | None) -> list[EdgeInstance]:
    visible_ids = set(scope_node_ids(workspace, scope_path))
    edges = [
        edge
        for edge in workspace.edges.values()
        if edge.source_node_id in visible_ids and edge.target_node_id in visible_ids
    ]
    edges.sort(key=lambda edge: edge.edge_id)
    return edges


def ancestor_chain(workspace: WorkspaceData, node_id: str) -> list[str]:
    normalized_node_id = str(node_id).strip()
    if not normalized_node_id:
        return []
    node = workspace.nodes.get(normalized_node_id)
    if node is None:
        return []
    chain: list[str] = []
    seen: set[str] = set()
    parent_id = node.parent_node_id
    while parent_id and parent_id not in seen:
        parent = workspace.nodes.get(parent_id)
        if parent is None:
            break
        chain.append(parent_id)
        seen.add(parent_id)
        parent_id = parent.parent_node_id
    chain.reverse()
    return chain


def node_scope_path(workspace: WorkspaceData, node_id: str) -> ScopePath:
    return tuple(ancestor_chain(workspace, node_id))


def subnode_scope_path(workspace: WorkspaceData, node_id: object) -> ScopePath:
    normalized_node_id = str(node_id).strip()
    if not normalized_node_id:
        return ()
    if normalized_node_id not in workspace.nodes:
        return ()
    parent_scope = node_scope_path(workspace, normalized_node_id)
    return (*parent_scope, normalized_node_id)


def breadcrumb_scope_path(
    workspace: WorkspaceData,
    scope_path: Sequence[object] | None,
    node_id: object,
) -> ScopePath:
    normalized_scope = normalize_scope_path(workspace, scope_path)
    target_id = str(node_id).strip()
    if not target_id:
        return ()
    try:
        target_index = normalized_scope.index(target_id)
    except ValueError:
        return normalized_scope
    return normalized_scope[: target_index + 1]


def is_node_in_scope(workspace: WorkspaceData, node_id: str, scope_path: Sequence[object] | None) -> bool:
    node = workspace.nodes.get(str(node_id).strip())
    if node is None:
        return False
    return node.parent_node_id == scope_parent_id(normalize_scope_path(workspace, scope_path))


def nodes_share_scope(workspace: WorkspaceData, node_ids: Iterable[object]) -> bool:
    parent_values: set[str | None] = set()
    seen_any = False
    for value in node_ids:
        node = workspace.nodes.get(str(value).strip())
        if node is None:
            continue
        parent_values.add(node.parent_node_id)
        seen_any = True
        if len(parent_values) > 1:
            return False
    return seen_any


def subtree_node_ids(workspace: WorkspaceData, root_node_ids: Iterable[object]) -> list[str]:
    normalized_roots: list[str] = []
    seen_roots: set[str] = set()
    for value in root_node_ids:
        node_id = str(value).strip()
        if not node_id or node_id in seen_roots or node_id not in workspace.nodes:
            continue
        normalized_roots.append(node_id)
        seen_roots.add(node_id)

    children_by_parent = parent_to_children_map(workspace)
    subtree_ids: list[str] = []
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        subtree_ids.append(node_id)
        for child_id in children_by_parent.get(node_id, []):
            visit(child_id)

    for root_id in normalized_roots:
        visit(root_id)
    return subtree_ids


def descendant_node_ids(workspace: WorkspaceData, root_node_id: object) -> list[str]:
    root_id = str(root_node_id).strip()
    if not root_id:
        return []
    subtree = subtree_node_ids(workspace, [root_id])
    return [node_id for node_id in subtree if node_id != root_id]


def normalize_parent_node_id(parent_node_id: object | None) -> str | None:
    return str(parent_node_id or "").strip() or None


def parent_link_would_cycle(
    workspace: WorkspaceData,
    node_id: object,
    parent_node_id: object | None,
    *,
    candidate_parent_by_node: Mapping[str, str | None] | None = None,
) -> bool:
    normalized_node_id = str(node_id).strip()
    normalized_parent_id = normalize_parent_node_id(parent_node_id)
    if not normalized_node_id or normalized_parent_id is None:
        return False
    seen = {normalized_node_id}
    current_parent_id: str | None = normalized_parent_id
    while current_parent_id:
        if current_parent_id in seen:
            return True
        seen.add(current_parent_id)
        if candidate_parent_by_node is not None and current_parent_id in candidate_parent_by_node:
            current_parent_id = normalize_parent_node_id(candidate_parent_by_node[current_parent_id])
            continue
        parent = workspace.nodes.get(current_parent_id)
        current_parent_id = normalize_parent_node_id(parent.parent_node_id) if parent is not None else None
    return False


def validate_parent_node_id(
    workspace: WorkspaceData,
    node_id: object,
    parent_node_id: object | None,
    *,
    candidate_parent_by_node: Mapping[str, str | None] | None = None,
) -> str | None:
    normalized_node_id = str(node_id).strip()
    if not normalized_node_id or normalized_node_id not in workspace.nodes:
        raise KeyError(f"Unknown node: {normalized_node_id}")
    normalized_parent_id = normalize_parent_node_id(parent_node_id)
    if normalized_parent_id is None:
        return None
    if normalized_parent_id == normalized_node_id:
        raise ValueError("Node cannot parent itself.")
    if normalized_parent_id not in workspace.nodes:
        raise KeyError(f"Unknown parent node: {normalized_parent_id}")
    if parent_link_would_cycle(
        workspace,
        normalized_node_id,
        normalized_parent_id,
        candidate_parent_by_node=candidate_parent_by_node,
    ):
        raise ValueError("Parent link would create a cycle.")
    return normalized_parent_id


def subtree_edges(workspace: WorkspaceData, root_node_ids: Iterable[object]) -> list[EdgeInstance]:
    subtree_set = set(subtree_node_ids(workspace, root_node_ids))
    edges = [
        edge
        for edge in workspace.edges.values()
        if edge.source_node_id in subtree_set and edge.target_node_id in subtree_set
    ]
    edges.sort(key=lambda edge: edge.edge_id)
    return edges


def root_node_ids_for_fragment(workspace: WorkspaceData, node_ids: Iterable[object]) -> list[str]:
    subtree_set = set(str(value).strip() for value in node_ids if str(value).strip())
    roots: list[str] = []
    for node_id in subtree_set:
        node = workspace.nodes.get(node_id)
        if node is None:
            continue
        if node.parent_node_id in subtree_set:
            continue
        roots.append(node_id)
    roots.sort()
    return roots


def scope_breadcrumb_payload(workspace: WorkspaceData, scope_path: Sequence[object] | None) -> list[dict[str, str]]:
    normalized_scope = normalize_scope_path(workspace, scope_path)
    payload = [{"node_id": "", "label": workspace.name}]
    for node_id in normalized_scope:
        node = workspace.nodes.get(node_id)
        payload.append(
            {
                "node_id": node_id,
                "label": node.title if node is not None else node_id,
            }
        )
    return payload


def sanitize_workspace_parent_links(workspace: WorkspaceData) -> None:
    for node in workspace.nodes.values():
        try:
            node.parent_node_id = validate_parent_node_id(workspace, node.node_id, node.parent_node_id)
        except (KeyError, ValueError):
            node.parent_node_id = None


__all__ = [
    "ScopePath",
    "ancestor_chain",
    "breadcrumb_scope_path",
    "descendant_node_ids",
    "direct_child_node_ids",
    "direct_child_nodes",
    "is_node_in_scope",
    "node_scope_path",
    "nodes_share_scope",
    "normalize_parent_node_id",
    "normalize_scope_path",
    "parent_link_would_cycle",
    "parent_to_children_map",
    "root_node_ids_for_fragment",
    "sanitize_workspace_parent_links",
    "scope_breadcrumb_payload",
    "scope_edges",
    "scope_node_ids",
    "scope_parent_id",
    "subnode_scope_path",
    "subtree_edges",
    "subtree_node_ids",
    "validate_parent_node_id",
]
