# Purpose: Stable identity for a persisted board and its rendered snapshot.
# Map: feature_routes/excalidraw_web_host_real_editor
# Tests: tests/test_content_fullscreen_bridge.py, tests/test_passive_graph_surface_host.py
from __future__ import annotations

import hashlib
import json
import base64
import binascii
from collections.abc import Mapping


def board_scene_digest(scene: object) -> str:
    """Identify drawing content, independent of artifact promotion or editor UI."""
    if not isinstance(scene, Mapping):
        return ""
    value = dict(scene)
    raw_elements = value.get("elements", [])
    raw_files = value.get("files", {})
    app_state = value.get("appState", {})
    if not isinstance(raw_elements, list) or not isinstance(raw_files, Mapping) or not isinstance(app_state, Mapping):
        return ""
    if any(not isinstance(element, Mapping) for element in raw_elements):
        return ""
    elements = [
        {key: item for key, item in element.items() if key not in {"updated", "version", "versionNonce"}}
        for element in raw_elements
        if isinstance(element, Mapping) and not element.get("isDeleted")
    ]
    files = {}
    for element in elements:
        file_id = element.get("fileId")
        if file_id is not None and not isinstance(file_id, str):
            return ""
        entry = raw_files.get(file_id) if isinstance(raw_files, Mapping) else None
        if not isinstance(entry, Mapping):
            continue
        digest = entry.get("sha256")
        inline = entry.get("dataURL")
        if isinstance(inline, str) and "," in inline:
            try:
                digest = hashlib.sha256(base64.b64decode(inline.split(",", 1)[1], validate=True)).hexdigest()
            except (ValueError, binascii.Error):
                digest = inline
        files[str(file_id)] = {"content": digest or entry, "mime_type": entry.get("mimeType") or entry.get("mime_type")}
    value = {
        "elements": elements,
        "appState": {key: app_state[key] for key in ("viewBackgroundColor", "gridModeEnabled", "gridSize", "gridStep") if key in app_state},
        "files": files,
    }
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
