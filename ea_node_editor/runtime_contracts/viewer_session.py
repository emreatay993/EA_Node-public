from __future__ import annotations

import hashlib


def default_viewer_session_id(workspace_id: str, node_id: str) -> str:
    digest = hashlib.sha1(f"{workspace_id}:{node_id}".encode("utf-8")).hexdigest()[:16]
    return f"viewer_session_{digest}"


__all__ = ["default_viewer_session_id"]
