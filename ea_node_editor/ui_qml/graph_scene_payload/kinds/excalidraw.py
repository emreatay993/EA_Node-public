from __future__ import annotations

"""Excalidraw-board payload contribution: web-board preview ref projection."""

import copy
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ea_node_editor.nodes.builtins.excalidraw import EXCALIDRAW_PREVIEW_REF_PROPERTY
from ea_node_editor.ui_qml.graph_scene_payload.normalize import _normalized_preview_ref

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
    payload["properties"][EXCALIDRAW_PREVIEW_REF_PROPERTY] = _web_board_preview_ref_payload(
        ctx.node.properties.get(EXCALIDRAW_PREVIEW_REF_PROPERTY, "")
    )
