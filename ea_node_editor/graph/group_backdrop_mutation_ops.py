from __future__ import annotations

from collections.abc import Sequence

from ea_node_editor.graph.boundary_adapters import GraphBoundaryAdapters, fallback_graph_boundary_adapters
from ea_node_editor.graph.group_backdrop_geometry import (
    GROUP_BACKDROP_WRAP_MIN_HEIGHT,
    GROUP_BACKDROP_WRAP_MIN_WIDTH,
    GROUP_BACKDROP_WRAP_PADDING,
    GroupBackdropCandidate,
    GroupBackdropWrapResult,
    build_group_backdrop_wrap_bounds,
)
from ea_node_editor.graph.hierarchy import normalize_scope_path, node_scope_path, scope_parent_id
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.nodes.builtins.passive_annotation import PASSIVE_ANNOTATION_GROUP_BACKDROP_TYPE_ID
from ea_node_editor.nodes.registry import NodeRegistry


def wrap_selection_in_group_backdrop(
    *,
    model: GraphModel,
    registry: NodeRegistry,
    workspace_id: str,
    selected_node_ids: Sequence[object],
    scope_path: Sequence[object] | None,
    boundary_adapters: GraphBoundaryAdapters | None = None,
) -> GroupBackdropWrapResult | None:
    workspace = model.project.workspaces.get(str(workspace_id).strip())
    if workspace is None:
        return None
    adapters = boundary_adapters or fallback_graph_boundary_adapters()
    normalized_scope = normalize_scope_path(workspace, scope_path)
    selected_candidates: list[GroupBackdropCandidate] = []
    wrapped_node_ids: list[str] = []
    seen_node_ids: set[str] = set()

    for value in selected_node_ids:
        node_id = str(value).strip()
        if not node_id or node_id in seen_node_ids:
            continue
        node = workspace.nodes.get(node_id)
        if node is None:
            return None
        if node_scope_path(workspace, node_id) != normalized_scope:
            return None
        spec = registry.get_spec(node.type_id)
        width, height = adapters.node_size(node, spec, workspace.nodes)
        selected_candidates.append(
            GroupBackdropCandidate(
                node_id=node_id,
                scope_path=normalized_scope,
                is_backdrop=(str(spec.surface_family or "").strip() == "group_backdrop"),
                x=float(node.x),
                y=float(node.y),
                width=float(width),
                height=float(height),
            )
        )
        wrapped_node_ids.append(node_id)
        seen_node_ids.add(node_id)

    if not selected_candidates:
        return None

    bounds = build_group_backdrop_wrap_bounds(
        selected_candidates,
        padding=GROUP_BACKDROP_WRAP_PADDING,
        min_width=GROUP_BACKDROP_WRAP_MIN_WIDTH,
        min_height=GROUP_BACKDROP_WRAP_MIN_HEIGHT,
    )
    if bounds is None:
        return None

    validated = ValidatedGraphMutation(
        model=model,
        workspace_id=workspace.workspace_id,
        registry=registry,
        boundary_adapters=adapters,
    )
    backdrop_spec = registry.get_spec(PASSIVE_ANNOTATION_GROUP_BACKDROP_TYPE_ID)
    backdrop_properties = registry.default_properties(PASSIVE_ANNOTATION_GROUP_BACKDROP_TYPE_ID)
    backdrop = validated.add_node(
        type_id=PASSIVE_ANNOTATION_GROUP_BACKDROP_TYPE_ID,
        title=backdrop_properties.get("title", backdrop_spec.display_name),
        x=float(bounds.x),
        y=float(bounds.y),
        properties=backdrop_properties,
        exposed_ports={port.key: port.exposed for port in backdrop_spec.ports},
        parent_node_id=scope_parent_id(normalized_scope),
    )
    model._set_node_geometry_record(
        workspace.workspace_id,
        backdrop.node_id,
        float(bounds.x),
        float(bounds.y),
        float(bounds.width),
        float(bounds.height),
    )
    return GroupBackdropWrapResult(
        backdrop_node_id=backdrop.node_id,
        wrapped_node_ids=tuple(wrapped_node_ids),
        scope_path=normalized_scope,
        x=float(bounds.x),
        y=float(bounds.y),
        width=float(bounds.width),
        height=float(bounds.height),
    )


__all__ = ["wrap_selection_in_group_backdrop"]
