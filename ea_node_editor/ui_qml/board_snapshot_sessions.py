# Purpose: Keep pending board preview status tied to its live editor and workspace.
# Map: feature_routes/excalidraw_web_host_real_editor
# Tests: tests/test_content_fullscreen_bridge.py, tests/test_passive_graph_surface_host.py
from __future__ import annotations

from uuid import uuid4

_active_sessions: dict[str, tuple[object, str]] = {}


def register_board_snapshot_session(workspace: object, node_id: str) -> str:
    session_id = uuid4().hex
    _active_sessions[session_id] = (workspace, node_id)
    return session_id


def retire_board_snapshot_session(session_id: str) -> None:
    _active_sessions.pop(session_id, None)


def board_snapshot_session_active(session_id: str, workspace: object, node_id: str) -> bool:
    owner = _active_sessions.get(session_id)
    return owner is not None and owner[0] is workspace and owner[1] == node_id
