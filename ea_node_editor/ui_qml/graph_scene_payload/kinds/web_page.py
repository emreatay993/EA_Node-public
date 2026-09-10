from __future__ import annotations

"""Web-page-viewer payload contributions: property normalization + fullscreen payload."""

from typing import TYPE_CHECKING, Any

from ea_node_editor.nodes.builtins.web_viewer import normalize_web_page_viewer_properties
from ea_node_editor.ui_qml.graph_scene_payload.fullscreen import (
    build_content_fullscreen_web_page_payload,
)

if TYPE_CHECKING:
    from ea_node_editor.graph.boundary_adapters import GraphBoundaryAdapters
    from ea_node_editor.nodes.node_specs import NodeTypeSpec
    from ea_node_editor.ui_qml.graph_scene_payload.factory import PayloadBuildContext


def _project_context_from_graph_theme_bridge(
    graph_theme_bridge: object | None,
) -> tuple[str | None, dict[str, Any] | None]:
    parent = getattr(graph_theme_bridge, "parent", None)
    host = parent() if callable(parent) else None
    project_path = str(getattr(host, "project_path", "") or "").strip() if host is not None else ""
    project = getattr(getattr(host, "model", None), "project", None) if host is not None else None
    metadata = getattr(project, "metadata", None)
    return project_path or None, dict(metadata) if isinstance(metadata, dict) else None


def normalize_properties(
    properties: dict[str, Any],
    *,
    node: Any,
    spec: "NodeTypeSpec",
    boundary_adapters: "GraphBoundaryAdapters",
) -> dict[str, Any]:
    del node, spec, boundary_adapters
    return normalize_web_page_viewer_properties(properties)


def contribute(payload: dict[str, Any], ctx: "PayloadBuildContext") -> None:
    project_path, project_metadata = _project_context_from_graph_theme_bridge(ctx.graph_theme_bridge)
    payload["web_page_payload"] = build_content_fullscreen_web_page_payload(
        workspace_id=ctx.workspace.workspace_id,
        node=ctx.node,
        spec=ctx.spec,
        project_path=project_path,
        project_metadata=project_metadata,
    )
