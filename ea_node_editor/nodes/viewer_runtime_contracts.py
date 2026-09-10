# Purpose: Dependency-light viewer command ports used by executable viewer nodes.
# Map: feature_routes/viewer_session_overlay_fullscreen.md
# Tests: tests/test_engineering_viewer_node.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from ea_node_editor.runtime_contracts import default_viewer_session_id

@dataclass(frozen=True)
class OpenViewerSessionCommand:
    type: Literal["open_viewer_session"] = "open_viewer_session"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    backend_id: str = ""
    data_refs: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)
    transport_revision: int = 0
    live_open_status: str = ""
    live_open_blocker: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    playback_state: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


@dataclass(frozen=True)
class UpdateViewerSessionCommand:
    type: Literal["update_viewer_session"] = "update_viewer_session"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    backend_id: str = ""
    data_refs: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)
    transport_revision: int = 0
    live_open_status: str = ""
    live_open_blocker: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    playback_state: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


@dataclass(frozen=True)
class MaterializeViewerDataCommand:
    type: Literal["materialize_viewer_data"] = "materialize_viewer_data"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    backend_id: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


class ViewerSessionServicePort(Protocol):
    def open_session(self, command: OpenViewerSessionCommand) -> object: ...

    def update_session(self, command: UpdateViewerSessionCommand) -> object: ...

    def materialize_data(self, command: MaterializeViewerDataCommand) -> object: ...


def viewer_session_failed(event: object) -> bool:
    return str(getattr(event, "type", "")).strip() == "viewer_session_failed"


def viewer_session_error(event: object) -> str:
    return str(getattr(event, "error", "")).strip() or "viewer session command failed"


__all__ = [
    "MaterializeViewerDataCommand",
    "OpenViewerSessionCommand",
    "UpdateViewerSessionCommand",
    "ViewerSessionServicePort",
    "default_viewer_session_id",
    "viewer_session_error",
    "viewer_session_failed",
]
