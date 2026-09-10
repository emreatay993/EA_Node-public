from __future__ import annotations

"""Viewer-surface payload contribution: the viewer surface contract block."""

from typing import TYPE_CHECKING, Any

from ea_node_editor.ui_qml.graph_surface_metrics import viewer_surface_contract_payload

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_scene_payload.factory import PayloadBuildContext


def contribute(payload: dict[str, Any], ctx: "PayloadBuildContext") -> None:
    payload["viewer_surface"] = viewer_surface_contract_payload(
        width=ctx.width,
        height=ctx.height,
        surface_metrics=ctx.surface_metrics,
    )
