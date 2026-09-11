from __future__ import annotations

"""Excalidraw-board payload contribution: web-board preview ref projection."""

import copy
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ea_node_editor.common.board_snapshot import board_scene_digest
from ea_node_editor.nodes.builtins.excalidraw import EXCALIDRAW_PREVIEW_REF_PROPERTY, EXCALIDRAW_STATE_PROPERTY
from ea_node_editor.ui_qml.graph_scene_payload.normalize import _normalized_preview_ref
from ea_node_editor.ui_qml.board_snapshot_sessions import board_snapshot_session_active

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_scene_payload.factory import PayloadBuildContext


def _web_board_preview_ref_payload(value: object) -> object:
    normalized = _normalized_preview_ref(value)
    if not isinstance(normalized, Mapping):
        return normalized
    payload = copy.deepcopy(dict(normalized))
    if str(payload.get("uri", "") or "").strip():
        return payload
    for key in ("artifact_ref", "preview_ref", "ref", "artifact_id", "path"):
        ref = str(payload.get(key, "") or "").strip()
        if ref:
            payload["uri"] = ref
            break
    return payload


def contribute(payload: dict[str, Any], ctx: "PayloadBuildContext") -> None:
    preview = _web_board_preview_ref_payload(
        ctx.node.properties.get(EXCALIDRAW_PREVIEW_REF_PROPERTY, "")
    )
    if isinstance(preview, Mapping):
        preview = dict(preview)
        if preview.get("status") == "updating" and not board_snapshot_session_active(
            str(preview.get("session_id") or ""), ctx.workspace, ctx.node.node_id,
        ):
            preview.update(status="error", error="Preview update was interrupted. Open the editor to retry.")
        preview["current"] = bool(
            preview.get("status") == "ready"
            and preview.get("scene_sha256")
            and preview["scene_sha256"] == board_scene_digest(ctx.node.properties.get(EXCALIDRAW_STATE_PROPERTY))
        )
    payload["properties"][EXCALIDRAW_PREVIEW_REF_PROPERTY] = preview
