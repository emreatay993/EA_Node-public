from __future__ import annotations

"""Jupyter-notebook payload contributions: property normalization + surface payload."""

from typing import TYPE_CHECKING, Any

from ea_node_editor.nodes.builtins.jupyter_notebook import normalize_jupyter_notebook_properties
from ea_node_editor.ui_qml.graph_scene_payload.fullscreen import build_jupyter_notebook_payload

if TYPE_CHECKING:
    from ea_node_editor.graph.boundary_adapters import GraphBoundaryAdapters
    from ea_node_editor.nodes.node_specs import NodeTypeSpec
    from ea_node_editor.ui_qml.graph_scene_payload.factory import PayloadBuildContext


def normalize_properties(
    properties: dict[str, Any],
    *,
    node: Any,
    spec: "NodeTypeSpec",
    boundary_adapters: "GraphBoundaryAdapters",
) -> dict[str, Any]:
    del node, spec, boundary_adapters
    return normalize_jupyter_notebook_properties(properties)


def contribute(payload: dict[str, Any], ctx: "PayloadBuildContext") -> None:
    payload["jupyter_notebook_payload"] = build_jupyter_notebook_payload(
        workspace_id=ctx.workspace.workspace_id,
        node=ctx.node,
        spec=ctx.spec,
    )
