from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot, RuntimeSnapshotContext


@dataclass(slots=True, frozen=True)
class ViewerBackendMaterializationRequest:
    workspace_id: str
    node_id: str
    session_id: str
    owner_scope: str
    source_refs: Mapping[str, Any]
    session_summary: Mapping[str, Any]
    session_options: Mapping[str, Any]
    request_options: Mapping[str, Any]
    output_profile: str
    export_formats: tuple[str, ...] = ()
    project_path: str = ""
    runtime_snapshot: RuntimeSnapshot | None = None
    runtime_snapshot_context: RuntimeSnapshotContext | None = None


@dataclass(slots=True, frozen=True)
class ViewerBackendMaterializationResult:
    backend_id: str
    data_refs: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)
    transport_revision: int = 0
    live_open_status: str = ""
    live_open_blocker: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    playback_state: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ViewerBackendQueryRequest:
    workspace_id: str
    session_id: str
    query_type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    session_summary: Mapping[str, Any] = field(default_factory=dict)
    session_options: Mapping[str, Any] = field(default_factory=dict)
    transport: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ViewerBackendQueryResult:
    supported: bool
    value: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""


class ViewerBackend(Protocol):
    backend_id: str

    def materialize(
        self,
        request: ViewerBackendMaterializationRequest,
    ) -> ViewerBackendMaterializationResult:
        ...


class ViewerBackendRegistry:
    def __init__(self) -> None:
        self._backends: dict[str, ViewerBackend] = {}

    def register(self, backend: ViewerBackend) -> None:
        backend_id = str(getattr(backend, "backend_id", "")).strip()
        if not backend_id:
            raise ValueError("viewer backend_id is required")
        self._backends[backend_id] = backend

    def resolve(self, backend_id: str) -> ViewerBackend:
        normalized = str(backend_id).strip()
        if not normalized:
            raise LookupError("viewer backend_id is required")
        try:
            return self._backends[normalized]
        except KeyError as exc:
            raise LookupError(f"Unknown viewer backend: {normalized!r}.") from exc

    def reset(self) -> None:
        for backend in self._backends.values():
            reset = getattr(backend, "reset", None)
            if callable(reset):
                reset()


__all__ = [
    "ViewerBackend",
    "ViewerBackendMaterializationRequest",
    "ViewerBackendMaterializationResult",
    "ViewerBackendQueryRequest",
    "ViewerBackendQueryResult",
    "ViewerBackendRegistry",
]
