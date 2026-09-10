from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QWidget


class ViewerWidgetNoBind(RuntimeError):
    """Signal that the host should leave the overlay container unbound."""


@dataclass(slots=True, frozen=True)
class ViewerWidgetBindRequest:
    workspace_id: str
    node_id: str
    session_id: str
    backend_id: str
    transport_revision: int
    live_mode: str
    cache_state: str
    live_open_status: str
    live_open_blocker: Mapping[str, Any] = field(default_factory=dict)
    data_refs: Mapping[str, Any] = field(default_factory=dict)
    transport: Mapping[str, Any] = field(default_factory=dict)
    camera_state: Mapping[str, Any] = field(default_factory=dict)
    playback_state: Mapping[str, Any] = field(default_factory=dict)
    summary: Mapping[str, Any] = field(default_factory=dict)
    options: Mapping[str, Any] = field(default_factory=dict)
    session_model: Mapping[str, Any] = field(default_factory=dict)
    container: QWidget | None = None
    current_widget: QWidget | None = None


@dataclass(slots=True, frozen=True)
class ViewerWidgetReleaseRequest:
    workspace_id: str
    node_id: str
    session_id: str
    backend_id: str
    transport_revision: int
    data_refs: Mapping[str, Any] = field(default_factory=dict)
    transport: Mapping[str, Any] = field(default_factory=dict)
    summary: Mapping[str, Any] = field(default_factory=dict)
    options: Mapping[str, Any] = field(default_factory=dict)
    session_model: Mapping[str, Any] = field(default_factory=dict)
    container: QWidget | None = None
    widget: QWidget | None = None
    reason: str = ""


class ViewerWidgetBinder(Protocol):
    def bind_widget(self, request: ViewerWidgetBindRequest) -> QWidget | None:
        ...

    def release_widget(self, request: ViewerWidgetReleaseRequest) -> None:
        ...


class ViewerWidgetPreviewCapture(Protocol):
    def capture_preview_image(self, widget: QWidget | None) -> QImage | None:
        ...


class ViewerWidgetBinderRegistry:
    def __init__(self) -> None:
        self._binders: dict[str, ViewerWidgetBinder] = {}

    def register(self, backend_id: str, binder: ViewerWidgetBinder) -> None:
        normalized_backend_id = str(backend_id).strip()
        if not normalized_backend_id:
            raise ValueError("viewer widget binder backend_id is required")
        self._binders[normalized_backend_id] = binder

    def lookup(self, backend_id: str) -> ViewerWidgetBinder | None:
        normalized_backend_id = str(backend_id).strip()
        if not normalized_backend_id:
            return None
        return self._binders.get(normalized_backend_id)

    def resolve(self, backend_id: str) -> ViewerWidgetBinder:
        normalized_backend_id = str(backend_id).strip()
        if not normalized_backend_id:
            raise LookupError("viewer widget binder backend_id is required")
        binder = self.lookup(normalized_backend_id)
        if binder is None:
            raise LookupError(f"Unknown viewer widget binder backend: {normalized_backend_id!r}.")
        return binder


__all__ = [
    "ViewerWidgetBindRequest",
    "ViewerWidgetBinder",
    "ViewerWidgetBinderRegistry",
    "ViewerWidgetNoBind",
    "ViewerWidgetPreviewCapture",
    "ViewerWidgetReleaseRequest",
]
