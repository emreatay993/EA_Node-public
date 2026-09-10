from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ea_node_editor.common.coercions import coerce_int as _coerce_int
from ea_node_editor.common.scene_protocol import ENGINEERING_VIEWER_BACKEND_ID
from ea_node_editor.execution.handle_registry import (
    HandleDisposalError,
    StaleHandleError,
)
from ea_node_editor.execution.viewer_messages import (
    CloseViewerSessionCommand,
    MaterializeViewerDataCommand,
    OpenViewerSessionCommand,
    QueryViewerSessionCommand,
    UpdateViewerSessionCommand,
    ViewerDataMaterializedEvent,
    ViewerSessionClosedEvent,
    ViewerSessionFailedEvent,
    ViewerSessionOpenedEvent,
    ViewerQueryResultEvent,
    ViewerSessionUpdatedEvent,
    normalize_viewer_invalidation_node_ids,
    normalize_viewer_node_invalidation_epochs,
    viewer_epoch_snapshot_digest,
)
from ea_node_editor.execution.viewer_backend import (
    ViewerBackendMaterializationRequest,
    ViewerBackendQueryRequest,
    ViewerBackendQueryResult,
)
from ea_node_editor.runtime_contracts.value_refs import (
    RuntimeArtifactRef,
    coerce_runtime_handle_ref,
)
from ea_node_editor.runtime_contracts.data_types import (
    COREX_VIEWER_SESSION_HANDLE_KIND,
    VIEWER_SESSION_DATA_TYPE_ID,
)
from ea_node_editor.runtime_contracts.value_refs import RuntimeHandleRef

if TYPE_CHECKING:
    from ea_node_editor.execution.protocol_codec import (
        WorkerEvent,
        WorkerCommand,
    )
    from ea_node_editor.execution.runtime_snapshot import (
        RuntimeSnapshot,
        RuntimeSnapshotContext,
    )
    from ea_node_editor.execution.worker_services import WorkerServices

_DEFAULT_OUTPUT_PROFILE = "memory"
_SESSION_ID_PREFIX = "viewer_session_"
_SESSION_INVALIDATION_REASON_RERUN = "workspace_rerun"
_MATERIALIZED_DATA_KEYS = frozenset({"dataset", "preview", "csv", "png", "vtu", "vtm"})
_MATERIALIZE_TRANSIENT_OPTION_KEYS = frozenset(
    {"temporary_root_parent", "force_recompute"}
)
_CLOSE_TRANSIENT_OPTION_KEYS = frozenset({"reason", "release_handles"})
_TRANSPORT_RERUN_REQUIRED_BLOCKER = {
    "code": "rerun_required",
    "reason": "Live viewer transport is unavailable and requires rerun.",
    "rerun_required": True,
}
_VALID_VIEWER_SESSION_PHASES = frozenset(
    {"open", "opening", "closing", "closed", "blocked", "invalidated", "error"}
)
_LOGGER = logging.getLogger(__name__)


def _copy_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): copy.deepcopy(item) for key, item in value.items()}


def _transport_is_live(transport: Mapping[str, Any]) -> bool:
    if not transport:
        return False
    return bool(str(transport.get("kind", "")).strip())


def _canonical_source_ref_key(key: Any) -> str:
    normalized_key = str(key).strip()
    return normalized_key


def build_viewer_session_model(
    *,
    workspace_id: str,
    node_id: str,
    session_id: str,
    phase: str,
    request_id: str = "",
    last_command: str = "",
    last_error: str = "",
    playback_state: Mapping[str, Any] | None = None,
    cache_state: str = "empty",
    invalidated_reason: str = "",
    close_reason: str = "",
    backend_id: str = "",
    transport_revision: int = 0,
    live_mode: str = "proxy",
    live_open_status: str = "",
    live_open_blocker: Mapping[str, Any] | None = None,
    data_refs: Mapping[str, Any] | None = None,
    transport: Mapping[str, Any] | None = None,
    camera_state: Mapping[str, Any] | None = None,
    summary: Mapping[str, Any] | None = None,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_phase = str(phase).strip().lower() or "closed"
    if normalized_phase not in _VALID_VIEWER_SESSION_PHASES:
        normalized_phase = "closed"
    normalized_playback = _copy_mapping(playback_state)
    normalized_playback = {
        "state": str(normalized_playback.get("state", "paused")).strip() or "paused",
        "step_index": _coerce_int(normalized_playback.get("step_index"), default=0),
    }
    normalized_live_mode = str(live_mode).strip().lower() or "proxy"
    if normalized_live_mode not in {"proxy", "full"}:
        normalized_live_mode = "proxy"

    normalized_summary = _copy_mapping(summary)
    normalized_options = _copy_mapping(options)
    normalized_live_open_blocker = _copy_mapping(live_open_blocker)
    normalized_data_refs = _copy_mapping(data_refs)
    normalized_transport = _copy_mapping(transport)
    normalized_camera_state = _copy_mapping(camera_state)
    normalized_cache_state = str(cache_state).strip() or "empty"
    normalized_backend_id = str(backend_id).strip()
    normalized_transport_revision = _coerce_int(transport_revision)
    normalized_live_open_status = str(live_open_status).strip()
    normalized_invalidated_reason = str(invalidated_reason).strip()
    normalized_close_reason = str(close_reason).strip()

    if normalized_camera_state:
        normalized_summary.setdefault("camera_state", copy.deepcopy(normalized_camera_state))
        normalized_summary.setdefault("camera", copy.deepcopy(normalized_camera_state))

    normalized_options["playback_state"] = normalized_playback["state"]
    normalized_options["step_index"] = normalized_playback["step_index"]
    normalized_options["playback"] = copy.deepcopy(normalized_playback)
    normalized_options["live_mode"] = normalized_live_mode
    return {
        "workspace_id": str(workspace_id).strip(),
        "node_id": str(node_id).strip(),
        "session_id": str(session_id).strip(),
        "phase": normalized_phase,
        "request_id": str(request_id).strip(),
        "last_command": str(last_command).strip(),
        "last_error": str(last_error).strip(),
        "playback_state": normalized_playback["state"],
        "step_index": normalized_playback["step_index"],
        "playback": copy.deepcopy(normalized_playback),
        "cache_state": normalized_cache_state,
        "invalidated_reason": normalized_invalidated_reason,
        "close_reason": normalized_close_reason,
        "backend_id": normalized_backend_id,
        "transport_revision": normalized_transport_revision,
        "live_mode": normalized_live_mode,
        "live_open_status": normalized_live_open_status,
        "live_open_blocker": copy.deepcopy(normalized_live_open_blocker),
        "data_refs": copy.deepcopy(normalized_data_refs),
        "transport": copy.deepcopy(normalized_transport),
        "camera_state": copy.deepcopy(normalized_camera_state),
        "summary": normalized_summary,
        "options": normalized_options,
    }


def projection_safe_viewer_transport(value: Any) -> dict[str, Any]:
    transport = _copy_mapping(value)
    projection: dict[str, Any] = {}
    kind = str(transport.get("kind", "")).strip()
    if kind:
        projection["kind"] = kind
    backend_id = str(transport.get("backend_id", "")).strip()
    if backend_id:
        projection["backend_id"] = backend_id
    return projection


def coerce_viewer_session_model(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    payload_map = _copy_mapping(payload)
    if not payload_map:
        return {}

    summary = _copy_mapping(payload_map.get("summary"))
    options = _copy_mapping(payload_map.get("options"))
    playback = _copy_mapping(payload_map.get("playback"))
    if not playback:
        playback_state_payload = payload_map.get("playback_state")
        playback = _copy_mapping(playback_state_payload)
        if not playback:
            playback = {
                "state": str(playback_state_payload or "paused").strip()
                or "paused",
                "step_index": _coerce_int(
                    payload_map.get("step_index", 0),
                    default=0,
                ),
            }
    camera_state = _copy_mapping(payload_map.get("camera_state"))
    phase = str(payload_map.get("phase", "") or "").strip()
    if not phase:
        phase = "closed"

    return build_viewer_session_model(
        workspace_id=str(payload_map.get("workspace_id", "") or "").strip(),
        node_id=str(payload_map.get("node_id", "") or "").strip(),
        session_id=str(payload_map.get("session_id", "") or "").strip(),
        phase=phase,
        request_id=str(payload_map.get("request_id", "") or "").strip(),
        last_command=str(payload_map.get("last_command", "") or "").strip(),
        last_error=str(payload_map.get("last_error", "") or "").strip(),
        playback_state=playback,
        cache_state=str(payload_map.get("cache_state", "") or "").strip(),
        invalidated_reason=str(payload_map.get("invalidated_reason", "") or "").strip(),
        close_reason=str(payload_map.get("close_reason", "") or "").strip(),
        backend_id=str(payload_map.get("backend_id", "") or "").strip(),
        transport_revision=payload_map.get("transport_revision", 0),
        live_mode=payload_map.get("live_mode", ""),
        live_open_status=str(payload_map.get("live_open_status", "") or "").strip(),
        live_open_blocker=_copy_mapping(payload_map.get("live_open_blocker")),
        data_refs=_copy_mapping(payload_map.get("data_refs")),
        transport=_copy_mapping(payload_map.get("transport")),
        camera_state=camera_state,
        summary=summary,
        options=options,
    )


def _viewer_session_has_proxy_projection(model: Mapping[str, Any]) -> bool:
    return any(
        (
            bool(_copy_mapping(model.get("summary"))),
            bool(_copy_mapping(model.get("options"))),
            bool(_copy_mapping(model.get("camera_state"))),
            _coerce_int(model.get("transport_revision"), default=0) > 0,
            bool(str(model.get("backend_id", "")).strip()),
        )
    )


def build_run_required_viewer_session_model(
    payload: Mapping[str, Any] | None,
    *,
    reason: str,
    run_id: str = "",
    last_command: str = "run_required",
) -> dict[str, Any]:
    base_model = coerce_viewer_session_model(payload)
    if not base_model:
        return {}

    blocker = copy.deepcopy(_TRANSPORT_RERUN_REQUIRED_BLOCKER)
    summary = _copy_mapping(base_model.get("summary"))
    options = _copy_mapping(base_model.get("options"))
    cache_state = "proxy_ready" if _viewer_session_has_proxy_projection(base_model) else "empty"

    summary["cache_state"] = cache_state
    summary["live_open_status"] = "blocked"
    summary["live_open_blocker"] = copy.deepcopy(blocker)
    summary["rerun_required"] = True
    backend_id = str(base_model.get("backend_id", "")).strip()
    if backend_id:
        summary["backend_id"] = backend_id
    transport_revision = _coerce_int(base_model.get("transport_revision"), default=0)
    if transport_revision > 0:
        summary["transport_revision"] = transport_revision
    if str(reason).strip():
        summary["live_transport_release_reason"] = str(reason).strip()
    if str(run_id).strip():
        summary["run_id"] = str(run_id).strip()

    options["cache_state"] = cache_state
    options["live_mode"] = "proxy"
    options["live_open_status"] = "blocked"
    options["live_open_blocker"] = copy.deepcopy(blocker)
    options["rerun_required"] = True
    options["playback_state"] = str(base_model.get("playback_state", "paused")).strip() or "paused"
    options["step_index"] = _coerce_int(base_model.get("step_index"), default=0)
    if backend_id:
        options["backend_id"] = backend_id
    if transport_revision > 0:
        options["transport_revision"] = transport_revision

    return build_viewer_session_model(
        workspace_id=str(base_model.get("workspace_id", "")).strip(),
        node_id=str(base_model.get("node_id", "")).strip(),
        session_id=str(base_model.get("session_id", "")).strip(),
        phase="blocked",
        request_id="",
        last_command=str(last_command).strip() or "run_required",
        last_error="",
        playback_state=_copy_mapping(base_model.get("playback")) or {
            "state": str(base_model.get("playback_state", "paused")).strip() or "paused",
            "step_index": _coerce_int(base_model.get("step_index"), default=0),
        },
        cache_state=cache_state,
        invalidated_reason=str(base_model.get("invalidated_reason", "")).strip(),
        close_reason=str(base_model.get("close_reason", "")).strip(),
        backend_id=backend_id,
        transport_revision=transport_revision,
        live_mode="proxy",
        live_open_status="blocked",
        live_open_blocker=blocker,
        data_refs={},
        transport=projection_safe_viewer_transport(base_model.get("transport")),
        camera_state=_copy_mapping(base_model.get("camera_state")),
        summary=summary,
        options=options,
    )


@dataclass(slots=True)
class _ViewerWorkspaceContext:
    project_path: str = ""
    runtime_snapshot: RuntimeSnapshot | None = None
    runtime_snapshot_context: RuntimeSnapshotContext | None = None


@dataclass(slots=True)
class _ViewerSessionRecord:
    workspace_id: str
    node_id: str
    session_id: str
    owner_scope: str
    backend_id: str = ""
    source_refs: dict[str, Any] = field(default_factory=dict)
    materialized_refs: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)
    transport_revision: int = 0
    live_open_status: str = ""
    live_open_blocker: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    playback_state: dict[str, Any] = field(
        default_factory=lambda: {
            "state": "paused",
            "step_index": 0,
        }
    )
    summary: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    session_state: str = "open"
    invalidated_reason: str = ""
    rerun_required: bool = False
    stale_ref_keys: set[str] = field(default_factory=set)

    def has_live_dataset(self) -> bool:
        return coerce_runtime_handle_ref(self.materialized_refs.get("dataset")) is not None

    def cache_state(self) -> str:
        if self.invalidated_reason:
            return "invalidated"
        if self.session_state == "closed":
            return "closed"
        if _transport_is_live(self.transport):
            return "live_ready"
        if self.source_refs or self.materialized_refs or self.transport or self.rerun_required:
            return "proxy_ready"
        return "empty"

    def public_data_refs(self) -> dict[str, Any]:
        return copy.deepcopy(self.materialized_refs)

    def public_summary(self) -> dict[str, Any]:
        summary = copy.deepcopy(self.summary)
        summary["cache_state"] = self.cache_state()
        summary["has_source_data"] = bool(self.source_refs)
        summary["has_materialized_data"] = bool(self.materialized_refs)
        summary["backend_id"] = self.backend_id
        summary["transport_revision"] = self.transport_revision
        summary["live_open_status"] = self.live_open_status
        if self.invalidated_reason:
            summary["invalidated_reason"] = self.invalidated_reason
        if self.rerun_required:
            summary["rerun_required"] = True
        if self.live_open_blocker:
            summary["live_open_blocker"] = copy.deepcopy(self.live_open_blocker)
        if self.camera_state:
            summary["camera"] = copy.deepcopy(self.camera_state)
            summary["camera_state"] = copy.deepcopy(self.camera_state)
        if self.stale_ref_keys:
            summary["stale_ref_keys"] = sorted(self.stale_ref_keys)
        artifact_formats = sorted(
            key
            for key, value in self.materialized_refs.items()
            if isinstance(value, RuntimeArtifactRef)
        )
        if artifact_formats:
            summary["artifact_formats"] = artifact_formats
        if self.has_live_dataset():
            summary["live_dataset_key"] = "dataset"
        return summary

    def public_options(self) -> dict[str, Any]:
        options = copy.deepcopy(self.options)
        requested_live_mode = str(options.get("live_mode", "")).strip() or "proxy"
        live_ready = self.live_open_status == "ready" and not self.invalidated_reason
        options["live_mode"] = requested_live_mode if live_ready else "proxy"
        options["session_state"] = self.session_state
        options["cache_state"] = self.cache_state()
        options["backend_id"] = self.backend_id
        options["transport_revision"] = self.transport_revision
        options["live_open_status"] = self.live_open_status
        options["rerun_required"] = self.rerun_required
        if self.live_open_blocker:
            options["live_open_blocker"] = copy.deepcopy(self.live_open_blocker)
        playback_state = copy.deepcopy(self.playback_state)
        options["playback_state"] = str(playback_state.get("state", "paused")).strip() or "paused"
        options["step_index"] = _coerce_int(playback_state.get("step_index"), default=0)
        options["playback"] = playback_state
        return options

    def public_phase(self) -> str:
        if self.session_state == "closed":
            return "closed"
        if self.invalidated_reason:
            if self.rerun_required or self.live_open_status == "blocked":
                return "blocked"
            return "invalidated"
        if self.rerun_required and self.live_open_status == "blocked":
            return "blocked"
        return "open"

    def public_projection(
        self,
        *,
        summary: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_summary = _copy_mapping(summary) if summary is not None else self.public_summary()
        resolved_options = _copy_mapping(options) if options is not None else self.public_options()
        return build_viewer_session_model(
            workspace_id=self.workspace_id,
            node_id=self.node_id,
            session_id=self.session_id,
            phase=self.public_phase(),
            playback_state=self.playback_state,
            cache_state=self.cache_state(),
            invalidated_reason=self.invalidated_reason,
            close_reason=str(
                resolved_summary.get("close_reason") or self.summary.get("close_reason", "")
            ).strip(),
            backend_id=self.backend_id,
            transport_revision=self.transport_revision,
            live_mode=str(resolved_options.get("live_mode", self.options.get("live_mode", "proxy"))),
            live_open_status=self.live_open_status,
            live_open_blocker=self.live_open_blocker,
            data_refs=self.public_data_refs(),
            transport=self.transport,
            camera_state=self.camera_state,
            summary=resolved_summary,
            options=resolved_options,
        )


class ViewerSessionService:
    def __init__(self, worker_services: WorkerServices) -> None:
        self._worker_services = worker_services
        self._backend_registry = worker_services.viewer_backend_registry
        self._sessions: dict[tuple[str, str], _ViewerSessionRecord] = {}
        self._workspace_contexts: dict[str, _ViewerWorkspaceContext] = {}
        self._workspace_invalidation_epochs: dict[str, int] = {}
        self._node_invalidation_epochs: dict[tuple[str, str], int] = {}

    def session_handle(
        self,
        workspace_id: str,
        session_id: str,
    ) -> RuntimeHandleRef:
        normalized_workspace_id = str(workspace_id).strip()
        normalized_session_id = str(session_id).strip()
        record = self._sessions.get(
            (normalized_workspace_id, normalized_session_id)
        )
        if record is None:
            raise LookupError(
                f"Unknown viewer session: {normalized_session_id!r}."
            )
        return self._worker_services.register_handle(
            record.public_projection(),
            data_type_id=VIEWER_SESSION_DATA_TYPE_ID,
            kind=COREX_VIEWER_SESSION_HANDLE_KIND,
            owner_scope=record.owner_scope,
            metadata={
                "workspace_id": record.workspace_id,
                "node_id": record.node_id,
                "session_id": record.session_id,
                "backend_id": record.backend_id,
            },
        )

    def _public_event_contract(
        self,
        record: _ViewerSessionRecord,
        *,
        summary: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        public_summary = _copy_mapping(summary) if summary is not None else record.public_summary()
        public_options = _copy_mapping(options) if options is not None else record.public_options()
        return public_summary, public_options

    def install_workspace_context(
        self,
        *,
        workspace_id: str,
        project_path: str = "",
        runtime_snapshot: RuntimeSnapshot | None = None,
        runtime_snapshot_context: RuntimeSnapshotContext | None = None,
    ) -> None:
        normalized_workspace_id = self._normalize_required_string(
            "workspace_id", workspace_id
        )
        self._workspace_contexts[normalized_workspace_id] = _ViewerWorkspaceContext(
            project_path=str(project_path).strip(),
            runtime_snapshot=runtime_snapshot,
            runtime_snapshot_context=runtime_snapshot_context,
        )

    def validate_invalidation_snapshot(
        self,
        *,
        workspace_id: str,
        node_ids: Iterable[str] | None,
        workspace_epoch: int,
        node_epochs: Iterable[tuple[str, int]],
        snapshot_digest: str,
        buffered_viewer_commands: bool = False,
    ) -> tuple[tuple[str, ...] | None, tuple[tuple[str, int], ...]]:
        normalized_workspace_id = self._normalize_required_string(
            "workspace_id", workspace_id
        )
        normalized_node_ids = normalize_viewer_invalidation_node_ids(node_ids)
        normalized_node_epochs = normalize_viewer_node_invalidation_epochs(
            tuple(node_epochs)
        )
        expected_digest = viewer_epoch_snapshot_digest(
            workspace_id=normalized_workspace_id,
            node_ids=normalized_node_ids,
            workspace_epoch=workspace_epoch,
            node_epochs=normalized_node_epochs,
        )
        if snapshot_digest != expected_digest:
            raise ValueError("viewer invalidation snapshot digest mismatch")
        current_workspace_epoch = self._workspace_invalidation_epochs.get(
            normalized_workspace_id, 0
        )
        if workspace_epoch < current_workspace_epoch:
            raise ValueError("viewer workspace invalidation epoch is stale")
        if normalized_node_ids is None:
            if normalized_node_epochs or workspace_epoch <= current_workspace_epoch:
                raise ValueError("global viewer invalidation epoch must advance")
        elif normalized_node_ids == ():
            if normalized_node_epochs:
                raise ValueError("empty viewer invalidation forbids node epochs")
            if workspace_epoch > current_workspace_epoch:
                if buffered_viewer_commands or not self._fresh_for_epoch_baseline(
                    normalized_workspace_id
                ):
                    raise ValueError(
                        "empty viewer baseline adoption requires a fresh service"
                    )
            elif workspace_epoch != current_workspace_epoch:
                raise ValueError("empty viewer invalidation epoch is stale")
        else:
            if tuple(node_id for node_id, _epoch in normalized_node_epochs) != normalized_node_ids:
                raise ValueError("viewer node epochs do not match the filter")
            if workspace_epoch > current_workspace_epoch:
                if buffered_viewer_commands or not self._fresh_for_epoch_baseline(
                    normalized_workspace_id
                ):
                    raise ValueError(
                        "scoped viewer baseline adoption requires a fresh service"
                    )
            else:
                for node_id, epoch in normalized_node_epochs:
                    if epoch != self._node_invalidation_epochs.get(
                        (normalized_workspace_id, node_id), 0
                    ) + 1:
                        raise ValueError("viewer node invalidation epoch must advance once")
        return normalized_node_ids, normalized_node_epochs

    def _fresh_for_epoch_baseline(self, workspace_id: str) -> bool:
        return bool(
            workspace_id not in self._workspace_invalidation_epochs
            and workspace_id not in self._workspace_contexts
            and not any(key[0] == workspace_id for key in self._node_invalidation_epochs)
            and not any(key[0] == workspace_id for key in self._sessions)
            and self._worker_services.handle_registry.active_handle_count == 0
            and self._worker_services.handle_registry.active_lease_count == 0
        )

    def adopt_invalidation_snapshot(
        self,
        *,
        workspace_id: str,
        node_ids: Iterable[str] | None,
        workspace_epoch: int,
        node_epochs: Iterable[tuple[str, int]],
        snapshot_digest: str,
        reason: str,
        buffered_viewer_commands: bool = False,
    ) -> int:
        normalized_node_ids, normalized_node_epochs = (
            self.validate_invalidation_snapshot(
                workspace_id=workspace_id,
                node_ids=node_ids,
                workspace_epoch=workspace_epoch,
                node_epochs=node_epochs,
                snapshot_digest=snapshot_digest,
                buffered_viewer_commands=buffered_viewer_commands,
            )
        )
        normalized_workspace_id = self._normalize_required_string(
            "workspace_id", workspace_id
        )
        current_workspace_epoch = self._workspace_invalidation_epochs.get(
            normalized_workspace_id, 0
        )
        if normalized_node_ids == ():
            if workspace_epoch > current_workspace_epoch:
                self._workspace_invalidation_epochs[normalized_workspace_id] = (
                    workspace_epoch
                )
            return 0
        normalized_reason = self._normalize_required_string("reason", reason)
        workspace_advanced = workspace_epoch > current_workspace_epoch
        if workspace_advanced:
            self._workspace_invalidation_epochs[normalized_workspace_id] = (
                workspace_epoch
            )
            if normalized_node_ids is None:
                for key in tuple(self._node_invalidation_epochs):
                    if key[0] == normalized_workspace_id:
                        self._node_invalidation_epochs.pop(key, None)
        for node_id, epoch in normalized_node_epochs:
            self._node_invalidation_epochs[(normalized_workspace_id, node_id)] = epoch
        return self._invalidate_records(
            normalized_workspace_id,
            reason=normalized_reason,
            node_ids=normalized_node_ids,
        )

    def invalidate_workspace(
        self,
        workspace_id: str,
        *,
        reason: str,
        node_ids: Iterable[str] | None = None,
    ) -> int:
        normalized_workspace_id = self._normalize_required_string("workspace_id", workspace_id)
        normalized_reason = self._normalize_required_string("reason", reason)
        normalized_node_ids = self._normalize_node_ids(node_ids)
        if normalized_node_ids == ():
            return 0
        if normalized_node_ids is None:
            self._workspace_invalidation_epochs[normalized_workspace_id] = (
                self._workspace_invalidation_epochs.get(normalized_workspace_id, 0)
                + 1
            )
            for key in tuple(self._node_invalidation_epochs):
                if key[0] == normalized_workspace_id:
                    self._node_invalidation_epochs.pop(key, None)
        else:
            for node_id in normalized_node_ids:
                key = (normalized_workspace_id, node_id)
                self._node_invalidation_epochs[key] = (
                    self._node_invalidation_epochs.get(key, 0) + 1
                )
        return self._invalidate_records(
            normalized_workspace_id,
            reason=normalized_reason,
            node_ids=normalized_node_ids,
        )

    def reset(
        self,
        *,
        warn: Callable[[str], None] | None = None,
    ) -> None:
        workspace_ids = {
            *self._workspace_contexts,
            *(workspace_id for workspace_id, _session_id in self._sessions),
            *self._workspace_invalidation_epochs,
        }
        for workspace_id in workspace_ids:
            self._workspace_invalidation_epochs[workspace_id] = (
                self._workspace_invalidation_epochs.get(workspace_id, 0) + 1
            )
        self._node_invalidation_epochs.clear()
        for record in self._sessions.values():
            self._release_live_transport(
                record,
                reason="worker_reset",
                mark_rerun_required=False,
                warn=warn,
            )
        try:
            self._backend_registry.reset()
        except Exception:  # noqa: BLE001
            self._report_cleanup_warning(
                "Viewer backend automatic reset failed.",
                warn=warn,
            )
        released_owner_scopes = {record.owner_scope for record in self._sessions.values()}
        for owner_scope in released_owner_scopes:
            self._release_owner_scope(owner_scope, warn=warn)
        self._sessions.clear()
        self._workspace_contexts.clear()

    def handle_command(self, command: WorkerCommand) -> WorkerEvent:
        if isinstance(command, OpenViewerSessionCommand):
            return self.open_session(command)
        if isinstance(command, UpdateViewerSessionCommand):
            return self.update_session(command)
        if isinstance(command, CloseViewerSessionCommand):
            return self.close_session(command)
        if isinstance(command, QueryViewerSessionCommand):
            return self.query_session_command(command)
        if isinstance(command, MaterializeViewerDataCommand):
            return self.materialize_data(command)
        raise TypeError(f"Unsupported viewer session command: {type(command)!r}")

    @staticmethod
    def _normalize_node_ids(
        node_ids: Iterable[str] | None,
    ) -> tuple[str, ...] | None:
        if node_ids is None:
            return None
        if isinstance(node_ids, (str, bytes)):
            raise TypeError("node_ids must be an iterable of node IDs or None")
        normalized: list[str] = []
        for value in node_ids:
            node_id = str(value or "").strip()
            if node_id and node_id not in normalized:
                normalized.append(node_id)
        return tuple(normalized)

    def _command_for_current_epoch(
        self,
        command: WorkerCommand,
    ) -> WorkerCommand | ViewerSessionFailedEvent:
        workspace_id, node_id = self._normalize_workspace_and_node(command)
        if not workspace_id or not node_id:
            return command
        workspace_epoch = self._workspace_invalidation_epochs.get(workspace_id, 0)
        node_key = (workspace_id, node_id)
        node_epoch = self._node_invalidation_epochs.get(node_key, 0)
        request_id = str(getattr(command, "request_id", "")).strip()
        if not request_id:
            return replace(
                command,
                workspace_invalidation_epoch=workspace_epoch,
                node_invalidation_epoch=node_epoch,
            )
        command_workspace_epoch = int(
            getattr(command, "workspace_invalidation_epoch", 0)
        )
        command_node_epoch = int(getattr(command, "node_invalidation_epoch", 0))
        if command_workspace_epoch < workspace_epoch or (
            command_workspace_epoch == workspace_epoch
            and command_node_epoch < node_epoch
        ):
            return self._failure(
                command, "viewer command was invalidated by a newer epoch"
            )
        if command_workspace_epoch > workspace_epoch:
            self._invalidate_records(
                workspace_id,
                reason="workspace_epoch_advanced",
                node_ids=None,
            )
            self._workspace_invalidation_epochs[workspace_id] = command_workspace_epoch
            for key in tuple(self._node_invalidation_epochs):
                if key[0] == workspace_id:
                    self._node_invalidation_epochs.pop(key, None)
            self._node_invalidation_epochs[node_key] = command_node_epoch
        elif command_node_epoch > node_epoch:
            self._invalidate_records(
                workspace_id,
                reason="node_epoch_advanced",
                node_ids=(node_id,),
            )
            self._node_invalidation_epochs[node_key] = command_node_epoch
        return command

    def _invalidate_records(
        self,
        workspace_id: str,
        *,
        reason: str,
        node_ids: tuple[str, ...] | None,
    ) -> int:
        invalidated_count = 0
        for session_workspace_id, session_id in tuple(self._sessions):
            if session_workspace_id != workspace_id:
                continue
            record = self._sessions[(session_workspace_id, session_id)]
            if node_ids is not None and record.node_id not in node_ids:
                continue
            self._release_live_transport(
                record,
                reason=reason,
                mark_rerun_required=True,
            )
            self._release_owner_scope(record.owner_scope)
            record.source_refs = self._without_handle_refs(record.source_refs)
            record.materialized_refs = self._without_handle_refs(record.materialized_refs)
            record.session_state = "invalidated"
            record.invalidated_reason = reason
            record.rerun_required = True
            record.stale_ref_keys.clear()
            self._refresh_public_contract(record)
            invalidated_count += 1
        return invalidated_count

    def query_session(
        self,
        *,
        workspace_id: str,
        session_id: str,
        query_type: str,
        payload: Mapping[str, Any] | None = None,
    ) -> ViewerBackendQueryResult:
        record = self._sessions.get((str(workspace_id).strip(), str(session_id).strip()))
        if record is None:
            return ViewerBackendQueryResult(
                supported=False,
                explanation="The viewer session is not open.",
            )
        try:
            backend = self._backend_registry.resolve(record.backend_id)
        except LookupError as exc:
            return ViewerBackendQueryResult(supported=False, explanation=str(exc))
        query = getattr(backend, "query", None)
        if not callable(query):
            return ViewerBackendQueryResult(
                supported=False,
                explanation=f"Viewer backend '{record.backend_id}' does not support engineering queries.",
            )
        return query(
            ViewerBackendQueryRequest(
                workspace_id=record.workspace_id,
                session_id=record.session_id,
                query_type=str(query_type).strip(),
                payload=_copy_mapping(payload),
                session_summary=record.public_summary(),
                session_options=record.public_options(),
                transport=copy.deepcopy(record.transport),
            )
        )

    def query_session_command(
        self,
        command: QueryViewerSessionCommand,
    ) -> ViewerQueryResultEvent | ViewerSessionFailedEvent:
        current_command = self._command_for_current_epoch(command)
        if isinstance(current_command, ViewerSessionFailedEvent):
            return current_command
        command = current_command
        record = self._require_record(command)
        if isinstance(record, ViewerSessionFailedEvent):
            return record
        requested_backend_id = str(command.backend_id).strip()
        if requested_backend_id and requested_backend_id != record.backend_id:
            return self._failure(
                command,
                f"Viewer session backend is {record.backend_id!r}, not {requested_backend_id!r}.",
            )
        query_type = str(command.query_type).strip()
        if not query_type:
            return self._failure(command, "viewer query_type is required.")
        result = self.query_session(
            workspace_id=record.workspace_id,
            session_id=record.session_id,
            query_type=query_type,
            payload=command.payload,
        )
        return ViewerQueryResultEvent(
            request_id=command.request_id,
            workspace_id=record.workspace_id,
            node_id=record.node_id,
            session_id=record.session_id,
            backend_id=record.backend_id,
            query_type=query_type,
            supported=bool(result.supported),
            value=copy.deepcopy(result.value),
            explanation=str(result.explanation),
            workspace_invalidation_epoch=command.workspace_invalidation_epoch,
            node_invalidation_epoch=command.node_invalidation_epoch,
        )

    def open_session(self, command: OpenViewerSessionCommand) -> ViewerSessionOpenedEvent | ViewerSessionFailedEvent:
        current_command = self._command_for_current_epoch(command)
        if isinstance(current_command, ViewerSessionFailedEvent):
            return current_command
        command = current_command
        workspace_id, node_id = self._normalize_workspace_and_node(command)
        if not workspace_id or not node_id:
            return self._failure(command, "workspace_id and node_id are required.")

        session_id = str(command.session_id).strip() or self._next_session_id()
        session_key = (workspace_id, session_id)
        record = self._sessions.get(session_key)
        if record is None:
            record = _ViewerSessionRecord(
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=session_id,
                owner_scope=self._session_owner_scope(),
            )
            self._sessions[session_key] = record
        elif record.node_id != node_id:
            return self._failure(
                command,
                f"session_id {session_id!r} is already bound to node_id {record.node_id!r}.",
                session_id=session_id,
            )

        self._sanitize_record(record)
        self._apply_session_payload(
            record,
            backend_id=command.backend_id,
            data_refs=command.data_refs,
            transport=command.transport,
            transport_revision=command.transport_revision,
            live_open_status=command.live_open_status,
            live_open_blocker=command.live_open_blocker,
            camera_state=command.camera_state,
            playback_state=command.playback_state,
            summary=command.summary,
            options=command.options,
            replace_scene_sources=(
                (command.backend_id or record.backend_id)
                == ENGINEERING_VIEWER_BACKEND_ID
                and isinstance(command.data_refs.get("scene_order"), (list, tuple))
                and bool(command.data_refs["scene_order"])
            ),
        )
        if command.data_refs or command.transport:
            record.invalidated_reason = ""
        record.session_state = "open"
        self._refresh_public_contract(record)
        public_summary, public_options = self._public_event_contract(record)
        return ViewerSessionOpenedEvent(
            request_id=command.request_id,
            workspace_id=workspace_id,
            node_id=node_id,
            session_id=session_id,
            backend_id=record.backend_id,
            data_refs=record.public_data_refs(),
            transport=copy.deepcopy(record.transport),
            transport_revision=record.transport_revision,
            live_open_status=record.live_open_status,
            live_open_blocker=copy.deepcopy(record.live_open_blocker),
            camera_state=copy.deepcopy(record.camera_state),
            playback_state=copy.deepcopy(record.playback_state),
            summary=public_summary,
            options=public_options,
            workspace_invalidation_epoch=command.workspace_invalidation_epoch,
            node_invalidation_epoch=command.node_invalidation_epoch,
        )

    def update_session(self, command: UpdateViewerSessionCommand) -> ViewerSessionUpdatedEvent | ViewerSessionFailedEvent:
        current_command = self._command_for_current_epoch(command)
        if isinstance(current_command, ViewerSessionFailedEvent):
            return current_command
        command = current_command
        record = self._require_record(command)
        if isinstance(record, ViewerSessionFailedEvent):
            return record

        self._sanitize_record(record)
        self._apply_session_payload(
            record,
            backend_id=command.backend_id,
            data_refs=command.data_refs,
            transport=command.transport,
            transport_revision=command.transport_revision,
            live_open_status=command.live_open_status,
            live_open_blocker=command.live_open_blocker,
            camera_state=command.camera_state,
            playback_state=command.playback_state,
            summary=command.summary,
            options=command.options,
        )
        if command.data_refs or command.transport:
            record.invalidated_reason = ""
        record.session_state = "open"
        self._refresh_public_contract(record)
        public_summary, public_options = self._public_event_contract(record)
        return ViewerSessionUpdatedEvent(
            request_id=command.request_id,
            workspace_id=record.workspace_id,
            node_id=record.node_id,
            session_id=record.session_id,
            backend_id=record.backend_id,
            data_refs=record.public_data_refs(),
            transport=copy.deepcopy(record.transport),
            transport_revision=record.transport_revision,
            live_open_status=record.live_open_status,
            live_open_blocker=copy.deepcopy(record.live_open_blocker),
            camera_state=copy.deepcopy(record.camera_state),
            playback_state=copy.deepcopy(record.playback_state),
            summary=public_summary,
            options=public_options,
            workspace_invalidation_epoch=command.workspace_invalidation_epoch,
            node_invalidation_epoch=command.node_invalidation_epoch,
        )

    def close_session(self, command: CloseViewerSessionCommand) -> ViewerSessionClosedEvent | ViewerSessionFailedEvent:
        current_command = self._command_for_current_epoch(command)
        if isinstance(current_command, ViewerSessionFailedEvent):
            return current_command
        command = current_command
        record = self._require_record(command)
        if isinstance(record, ViewerSessionFailedEvent):
            return record

        self._sanitize_record(record)
        release_handles = bool(command.options.get("release_handles", False))
        cleanup_errors: list[str] = []
        was_closed = record.session_state == "closed"
        if not was_closed:
            self._release_live_transport(
                record,
                reason="session_closed",
                mark_rerun_required=True,
                cleanup_errors=cleanup_errors,
            )
            cleanup_errors.extend(
                self._release_stored_handles_explicit(record)
            )

        reason = str(command.options.get("reason", "")).strip()
        if reason:
            record.summary["close_reason"] = reason
        if not was_closed:
            if cleanup_errors:
                record.summary["cleanup_error"] = cleanup_errors[0]
                record.summary["cleanup_error_count"] = len(cleanup_errors)
            else:
                record.summary.pop("cleanup_error", None)
                record.summary.pop("cleanup_error_count", None)
        record.session_state = "closed"
        self._refresh_public_contract(record)
        if cleanup_errors:
            return self._failure(command, "Viewer session cleanup failed.")

        event_options = record.public_options()
        if reason:
            event_options["reason"] = reason
        if "release_handles" in command.options:
            event_options["release_handles"] = release_handles
        public_summary, public_options = self._public_event_contract(
            record,
            options=event_options,
        )
        return ViewerSessionClosedEvent(
            request_id=command.request_id,
            workspace_id=record.workspace_id,
            node_id=record.node_id,
            session_id=record.session_id,
            backend_id=record.backend_id,
            transport=copy.deepcopy(record.transport),
            transport_revision=record.transport_revision,
            live_open_status=record.live_open_status,
            live_open_blocker=copy.deepcopy(record.live_open_blocker),
            camera_state=copy.deepcopy(record.camera_state),
            playback_state=copy.deepcopy(record.playback_state),
            summary=public_summary,
            options=public_options,
            workspace_invalidation_epoch=command.workspace_invalidation_epoch,
            node_invalidation_epoch=command.node_invalidation_epoch,
        )

    def materialize_data(
        self,
        command: MaterializeViewerDataCommand,
    ) -> ViewerDataMaterializedEvent | ViewerSessionFailedEvent:
        current_command = self._command_for_current_epoch(command)
        if isinstance(current_command, ViewerSessionFailedEvent):
            return current_command
        command = current_command
        record = self._require_record(command)
        if isinstance(record, ViewerSessionFailedEvent):
            return record

        self._sanitize_record(record)
        request_options = copy.deepcopy(command.options)
        persistent_options = {
            str(key): copy.deepcopy(value)
            for key, value in request_options.items()
            if str(key) not in _MATERIALIZE_TRANSIENT_OPTION_KEYS
        }
        if persistent_options:
            record.options.update(persistent_options)

        output_profile = self._resolve_output_profile(record, request_options)
        export_formats = self._normalize_export_formats(request_options.get("export_formats", record.options.get("export_formats")))
        if not bool(request_options.get("force_recompute", False)):
            cached_event = self._cached_materialization_event(
                record,
                command=command,
                output_profile=output_profile,
                export_formats=export_formats,
            )
            if cached_event is not None:
                record.session_state = "open"
                return cached_event

        if record.invalidated_reason and not record.source_refs:
            return self._failure(
                command,
                f"Viewer session {record.session_id!r} is invalidated: {record.invalidated_reason}.",
            )

        context = self._workspace_contexts.get(record.workspace_id)
        backend_id = str(command.backend_id).strip() or record.backend_id
        if not backend_id:
            return self._failure(command, "viewer backend_id is required for materialization.")
        try:
            result_payload = self._materialize_backend_result(
                record,
                backend_id=backend_id,
                request_options=request_options,
                output_profile=output_profile,
                export_formats=export_formats,
                context=context,
            )
        except Exception as exc:  # noqa: BLE001
            return self._failure(command, str(exc))

        self._merge_record_refs(
            record,
            source_refs={},
            materialized_refs=result_payload["data_refs"],
        )
        result_backend_id = str(result_payload["backend_id"]).strip() or backend_id
        result_transport = _copy_mapping(result_payload["transport"])
        result_transport_revision = _coerce_int(result_payload["transport_revision"])
        result_camera_state = _copy_mapping(result_payload["camera_state"])
        result_playback_state = _copy_mapping(result_payload["playback_state"])
        result_live_open_status = str(result_payload["live_open_status"]).strip()
        result_live_open_blocker = _copy_mapping(result_payload["live_open_blocker"])
        record.backend_id = result_backend_id
        self._set_transport_state(
            record,
            transport=result_transport,
            transport_revision=result_transport_revision,
        )
        if result_camera_state:
            record.camera_state = result_camera_state
        if result_playback_state:
            record.playback_state = self._normalize_playback_state(
                result_playback_state,
                fallback=record.playback_state,
            )
        record.summary.update(copy.deepcopy(result_payload["summary"]))
        record.summary["materialized_output_profile"] = output_profile
        record.invalidated_reason = ""
        record.rerun_required = bool(result_live_open_blocker.get("rerun_required", False))
        if not record.rerun_required and result_transport and not _transport_is_live(result_transport):
            record.rerun_required = True
        record.session_state = "open"
        self._refresh_public_contract(
            record,
            live_open_status=result_live_open_status,
            live_open_blocker=result_live_open_blocker,
        )
        public_summary, public_options = self._public_event_contract(record)
        return ViewerDataMaterializedEvent(
            request_id=command.request_id,
            workspace_id=record.workspace_id,
            node_id=record.node_id,
            session_id=record.session_id,
            backend_id=record.backend_id,
            data_refs=record.public_data_refs(),
            transport=copy.deepcopy(record.transport),
            transport_revision=record.transport_revision,
            live_open_status=record.live_open_status,
            live_open_blocker=copy.deepcopy(record.live_open_blocker),
            camera_state=copy.deepcopy(record.camera_state),
            playback_state=copy.deepcopy(record.playback_state),
            summary=public_summary,
            options=public_options,
            workspace_invalidation_epoch=command.workspace_invalidation_epoch,
            node_invalidation_epoch=command.node_invalidation_epoch,
        )

    def _materialize_backend_result(
        self,
        record: _ViewerSessionRecord,
        *,
        backend_id: str,
        request_options: Mapping[str, Any],
        output_profile: str,
        export_formats: tuple[str, ...],
        context: _ViewerWorkspaceContext | None,
    ) -> dict[str, Any]:
        backend = self._backend_registry.resolve(backend_id)
        result = backend.materialize(
            ViewerBackendMaterializationRequest(
                workspace_id=record.workspace_id,
                node_id=record.node_id,
                session_id=record.session_id,
                owner_scope=record.owner_scope,
                source_refs=record.source_refs,
                session_summary={
                    **copy.deepcopy(record.summary),
                    **(
                        {"transport_revision": record.transport_revision}
                        if backend_id == ENGINEERING_VIEWER_BACKEND_ID
                        else {}
                    ),
                    "camera_state": copy.deepcopy(record.camera_state),
                },
                session_options=record.options,
                request_options=request_options,
                output_profile=output_profile,
                export_formats=export_formats,
                project_path=context.project_path if context is not None else "",
                runtime_snapshot=context.runtime_snapshot if context is not None else None,
                runtime_snapshot_context=context.runtime_snapshot_context if context is not None else None,
            )
        )
        return {
            "backend_id": str(result.backend_id).strip() or backend_id,
            "data_refs": copy.deepcopy(result.data_refs),
            "transport": _copy_mapping(result.transport),
            "transport_revision": _coerce_int(result.transport_revision),
            "camera_state": _copy_mapping(result.camera_state),
            "playback_state": _copy_mapping(result.playback_state),
            "live_open_status": str(result.live_open_status).strip(),
            "live_open_blocker": _copy_mapping(result.live_open_blocker),
            "summary": _copy_mapping(result.summary),
        }

    @staticmethod
    def _next_session_id() -> str:
        return f"{_SESSION_ID_PREFIX}{uuid4().hex[:12]}"

    @staticmethod
    def _normalize_required_string(field_name: str, value: Any) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError(f"{field_name} is required.")
        return normalized

    @staticmethod
    def _normalize_workspace_and_node(command: Any) -> tuple[str, str]:
        workspace_id = str(getattr(command, "workspace_id", "")).strip()
        node_id = str(getattr(command, "node_id", "")).strip()
        return workspace_id, node_id

    @staticmethod
    def _session_owner_scope() -> str:
        return f"cache:viewer_session:{uuid4().hex}"

    @staticmethod
    def _is_materialized_ref(key: str, value: Any) -> bool:
        return isinstance(value, RuntimeArtifactRef) or str(key) in _MATERIALIZED_DATA_KEYS

    @staticmethod
    def _resolve_output_profile(record: _ViewerSessionRecord, request_options: Mapping[str, Any]) -> str:
        profile = str(request_options.get("output_profile", record.options.get("output_profile", _DEFAULT_OUTPUT_PROFILE))).strip()
        return profile or _DEFAULT_OUTPUT_PROFILE

    @staticmethod
    def _normalize_export_formats(value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            normalized = value.strip()
            return (normalized,) if normalized else ()
        if not isinstance(value, Iterable) or isinstance(value, Mapping):
            return ()
        formats: list[str] = []
        for item in value:
            token = str(item).strip()
            if token and token not in formats:
                formats.append(token)
        return tuple(formats)

    def _require_record(self, command: Any) -> _ViewerSessionRecord | ViewerSessionFailedEvent:
        workspace_id, node_id = self._normalize_workspace_and_node(command)
        session_id = str(getattr(command, "session_id", "")).strip()
        if not workspace_id or not node_id or not session_id:
            return self._failure(command, "workspace_id, node_id, and session_id are required.")
        record = self._sessions.get((workspace_id, session_id))
        if record is None:
            return self._failure(command, f"Unknown viewer session: {session_id!r}.")
        if record.node_id != node_id:
            return self._failure(
                command,
                f"Viewer session {session_id!r} belongs to node_id {record.node_id!r}, not {node_id!r}.",
            )
        return record

    def _failure(self, command: Any, error: str, *, session_id: str = "") -> ViewerSessionFailedEvent:
        return ViewerSessionFailedEvent(
            request_id=str(getattr(command, "request_id", "")).strip(),
            workspace_id=str(getattr(command, "workspace_id", "")).strip(),
            node_id=str(getattr(command, "node_id", "")).strip(),
            session_id=session_id or str(getattr(command, "session_id", "")).strip(),
            command=str(getattr(command, "type", "")).strip(),
            error=str(error).strip() or "viewer session command failed",
            workspace_invalidation_epoch=int(
                getattr(command, "workspace_invalidation_epoch", 0)
            ),
            node_invalidation_epoch=int(
                getattr(command, "node_invalidation_epoch", 0)
            ),
        )

    def _sanitize_record(self, record: _ViewerSessionRecord) -> None:
        record.source_refs, stale_source = self._sanitize_ref_map(record.source_refs)
        record.materialized_refs, stale_materialized = self._sanitize_ref_map(record.materialized_refs)
        record.stale_ref_keys = stale_source | stale_materialized
        if record.transport and stale_materialized and not record.materialized_refs:
            self._release_live_transport(
                record,
                reason="stale_materialized_refs",
                mark_rerun_required=bool(record.source_refs),
            )
        elif record.transport and not self._is_transport_live(record.transport):
            self._release_live_transport(
                record,
                reason="transport_missing",
                mark_rerun_required=True,
            )
        self._refresh_transport_refs(record)
        self._refresh_public_contract(record)

    def _sanitize_ref_map(self, ref_map: Mapping[str, Any]) -> tuple[dict[str, Any], set[str]]:
        sanitized: dict[str, Any] = {}
        stale_keys: set[str] = set()
        for key, value in ref_map.items():
            runtime_ref = coerce_runtime_handle_ref(value)
            if runtime_ref is None:
                sanitized[str(key)] = copy.deepcopy(value)
                continue
            try:
                self._worker_services.resolve_handle(
                    runtime_ref,
                    expected_data_type=runtime_ref.data_type_id,
                    expected_kind=runtime_ref.kind,
                )
            except (StaleHandleError, TypeError):
                stale_keys.add(str(key))
                continue
            sanitized[str(key)] = runtime_ref
        return sanitized, stale_keys

    def _apply_session_payload(
        self,
        record: _ViewerSessionRecord,
        *,
        backend_id: str,
        data_refs: Mapping[str, Any],
        transport: Mapping[str, Any],
        transport_revision: int,
        live_open_status: str,
        live_open_blocker: Mapping[str, Any],
        camera_state: Mapping[str, Any],
        playback_state: Mapping[str, Any],
        summary: Mapping[str, Any],
        options: Mapping[str, Any],
        replace_scene_sources: bool = False,
    ) -> None:
        source_refs: dict[str, Any] = {}
        materialized_refs: dict[str, Any] = {}
        canonical_data_refs: dict[str, Any] = {}
        aliased_data_refs: list[tuple[str, Any]] = []
        for key, value in data_refs.items():
            raw_key = str(key).strip()
            normalized_key = _canonical_source_ref_key(raw_key)
            if raw_key == normalized_key:
                canonical_data_refs[normalized_key] = value
            else:
                aliased_data_refs.append((normalized_key, value))
        for normalized_key, value in aliased_data_refs:
            canonical_data_refs.setdefault(normalized_key, value)

        for normalized_key, value in canonical_data_refs.items():
            previous_value = record.source_refs.get(
                normalized_key,
                record.materialized_refs.get(normalized_key),
            )
            runtime_ref = coerce_runtime_handle_ref(value)
            previous_ref = coerce_runtime_handle_ref(previous_value)
            if (
                replace_scene_sources
                and runtime_ref is not None
                and runtime_ref.owner_scope == record.owner_scope
                and (
                    previous_ref is None
                    or previous_ref.handle_id != runtime_ref.handle_id
                )
            ):
                value = self._worker_services.lease_handle(
                    value, owner_scope=record.owner_scope
                )
            persisted_value = self._persist_ref_value(
                value,
                owner_scope=record.owner_scope,
                previous_value=previous_value,
            )
            if persisted_value is None:
                record.stale_ref_keys.add(normalized_key)
                continue
            if self._is_materialized_ref(normalized_key, persisted_value):
                materialized_refs[normalized_key] = persisted_value
            else:
                source_refs[normalized_key] = persisted_value
            record.stale_ref_keys.discard(normalized_key)

        removed_scene_keys = {
            key
            for key in record.source_refs
            if replace_scene_sources
            and key.startswith(("scene:", "native_source:"))
            and key not in source_refs
        }
        scene_sources_changed = replace_scene_sources and (
            bool(removed_scene_keys)
            or any(
                record.source_refs.get(key) != value
                for key, value in source_refs.items()
            )
        )
        self._merge_record_refs(
            record,
            source_refs=source_refs,
            materialized_refs=materialized_refs,
        )
        for key in removed_scene_keys:
            self._release_session_handle(
                record.source_refs.pop(key), owner_scope=record.owner_scope
            )
            record.stale_ref_keys.discard(key)
        if scene_sources_changed and record.transport:
            self._release_live_transport(
                record, reason="scene_sources_changed", mark_rerun_required=False
            )
        normalized_backend_id = str(backend_id).strip()
        if normalized_backend_id:
            record.backend_id = normalized_backend_id

        if isinstance(summary, Mapping):
            record.summary.update(
                {str(key): copy.deepcopy(value) for key, value in summary.items()}
            )
        if isinstance(options, Mapping):
            record.options.update(
                {
                    str(key): copy.deepcopy(value)
                    for key, value in options.items()
                    if str(key) not in _CLOSE_TRANSIENT_OPTION_KEYS
                }
            )
        if camera_state:
            record.camera_state = _copy_mapping(camera_state)
        else:
            record.camera_state = _copy_mapping(record.summary.get("camera_state") or record.summary.get("camera"))
        if playback_state:
            record.playback_state = self._normalize_playback_state(
                playback_state,
                fallback=record.playback_state,
            )
        else:
            record.playback_state = self._normalize_playback_state(
                record.options,
                fallback=record.playback_state,
            )
        normalized_transport = _copy_mapping(transport)
        if normalized_transport or _coerce_int(transport_revision) > 0:
            self._set_transport_state(
                record,
                transport=normalized_transport,
                transport_revision=transport_revision,
            )
            if normalized_transport:
                record.rerun_required = bool(_copy_mapping(live_open_blocker).get("rerun_required", False))
                if not _transport_is_live(normalized_transport):
                    record.rerun_required = True
        elif data_refs:
            record.rerun_required = False
        self._refresh_public_contract(
            record,
            live_open_status=live_open_status,
            live_open_blocker=live_open_blocker if live_open_status or live_open_blocker else None,
        )

    @staticmethod
    def _normalize_playback_state(
        value: Mapping[str, Any] | Any,
        *,
        fallback: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = _copy_mapping(fallback)
        payload = _copy_mapping(value)
        state = str(payload.get("state", base.get("state", payload.get("playback_state", "paused")))).strip() or "paused"
        step_index = _coerce_int(
            payload.get("step_index", base.get("step_index", 0)),
            default=_coerce_int(base.get("step_index"), default=0),
        )
        return {
            "state": state,
            "step_index": step_index,
        }

    def _set_transport_state(
        self,
        record: _ViewerSessionRecord,
        *,
        transport: Mapping[str, Any],
        transport_revision: int,
    ) -> None:
        normalized_transport = _copy_mapping(transport)
        if normalized_transport != record.transport:
            if normalized_transport:
                explicit_revision = _coerce_int(transport_revision)
                record.transport_revision = explicit_revision if explicit_revision > 0 else record.transport_revision + 1
            elif record.transport:
                record.transport_revision += 1
            record.transport = normalized_transport
            return
        explicit_revision = _coerce_int(transport_revision)
        if explicit_revision > record.transport_revision:
            record.transport_revision = explicit_revision

    def _default_live_open_state(self, record: _ViewerSessionRecord) -> tuple[str, dict[str, Any]]:
        if record.invalidated_reason:
            blocker = {
                "code": "session_invalidated",
                "reason": record.invalidated_reason,
            }
            if record.invalidated_reason == _SESSION_INVALIDATION_REASON_RERUN:
                blocker["rerun_required"] = True
            return "blocked", blocker
        if record.session_state == "closed":
            return "blocked", {
                "code": "session_closed",
                "reason": str(record.summary.get("close_reason", "session_closed")).strip() or "session_closed",
            }
        if self._is_transport_live(record.transport):
            return "ready", {}
        if record.rerun_required:
            return "blocked", copy.deepcopy(_TRANSPORT_RERUN_REQUIRED_BLOCKER)
        if record.source_refs or record.materialized_refs:
            return "blocked", copy.deepcopy(_TRANSPORT_RERUN_REQUIRED_BLOCKER)
        return "blocked", {
            "code": "no_source_data",
            "reason": "Viewer session does not have source data.",
        }

    def _refresh_public_contract(
        self,
        record: _ViewerSessionRecord,
        *,
        live_open_status: str = "",
        live_open_blocker: Mapping[str, Any] | None = None,
    ) -> None:
        default_status, default_blocker = self._default_live_open_state(record)
        normalized_status = str(live_open_status).strip() or default_status
        normalized_blocker = _copy_mapping(live_open_blocker if live_open_blocker is not None else default_blocker)
        if normalized_status == "ready" and default_status != "ready":
            normalized_status = default_status
            normalized_blocker = copy.deepcopy(default_blocker)
        elif normalized_status == "ready":
            normalized_blocker = {}
        elif not normalized_blocker:
            normalized_blocker = copy.deepcopy(default_blocker)
        record.live_open_status = normalized_status
        record.live_open_blocker = normalized_blocker

    def _refresh_transport_refs(self, record: _ViewerSessionRecord) -> None:
        return

    def _persist_ref_value(
        self,
        value: Any,
        *,
        owner_scope: str,
        previous_value: Any = None,
    ) -> Any | None:
        runtime_ref = coerce_runtime_handle_ref(value)
        if runtime_ref is None:
            return copy.deepcopy(value)
        try:
            self._worker_services.resolve_handle(
                runtime_ref,
                expected_data_type=runtime_ref.data_type_id,
                expected_kind=runtime_ref.kind,
            )
        except (StaleHandleError, TypeError):
            return None
        previous_ref = coerce_runtime_handle_ref(previous_value)
        if (
            previous_ref is not None
            and previous_ref.handle_id == runtime_ref.handle_id
            and previous_ref.owner_scope == owner_scope
        ):
            return previous_ref
        if runtime_ref.owner_scope == owner_scope:
            return runtime_ref
        return self._worker_services.lease_handle(
            runtime_ref,
            owner_scope=owner_scope,
        )

    def _merge_record_refs(
        self,
        record: _ViewerSessionRecord,
        *,
        source_refs: Mapping[str, Any],
        materialized_refs: Mapping[str, Any],
    ) -> None:
        for key, value in source_refs.items():
            if key in record.materialized_refs:
                self._release_session_handle(record.materialized_refs.pop(key), owner_scope=record.owner_scope)
            previous = record.source_refs.get(key)
            if previous != value:
                self._release_session_handle(previous, owner_scope=record.owner_scope)
            record.source_refs[str(key)] = value

        for key, value in materialized_refs.items():
            if key in record.source_refs:
                self._release_session_handle(record.source_refs.pop(key), owner_scope=record.owner_scope)
            previous = record.materialized_refs.get(key)
            if previous != value:
                self._release_session_handle(previous, owner_scope=record.owner_scope)
            record.materialized_refs[str(key)] = value

    def _release_live_transport(
        self,
        record: _ViewerSessionRecord,
        *,
        reason: str,
        mark_rerun_required: bool,
        cleanup_errors: list[str] | None = None,
        warn: Callable[[str], None] | None = None,
    ) -> None:
        had_transport = bool(record.transport)
        backend_id = str(record.backend_id).strip()
        try:
            backend = self._backend_registry.resolve(backend_id) if backend_id else None
        except LookupError:
            backend = None
        if backend is not None and hasattr(backend, "release_session_transport"):
            try:
                backend.release_session_transport(
                    workspace_id=record.workspace_id,
                    session_id=record.session_id,
                )
            except Exception:  # noqa: BLE001
                message = "Viewer session transport cleanup failed."
                if cleanup_errors is not None:
                    cleanup_errors.append(message)
                else:
                    self._report_cleanup_warning(message, warn=warn)

        self._set_transport_state(
            record,
            transport={},
            transport_revision=record.transport_revision + 1 if had_transport else record.transport_revision,
        )
        if str(reason).strip():
            record.summary["live_transport_release_reason"] = str(reason).strip()
        if mark_rerun_required and (had_transport or record.source_refs or record.materialized_refs):
            record.rerun_required = True

    @staticmethod
    def _is_transport_live(transport: Mapping[str, Any]) -> bool:
        return _transport_is_live(transport)

    def _release_stored_handles_explicit(
        self,
        record: _ViewerSessionRecord,
    ) -> list[str]:
        cleanup_errors: list[str] = []
        for ref_map in (record.source_refs, record.materialized_refs):
            for value in tuple(ref_map.values()):
                runtime_ref = coerce_runtime_handle_ref(value)
                if (
                    runtime_ref is None
                    or runtime_ref.owner_scope != record.owner_scope
                ):
                    continue
                try:
                    self._worker_services.release_handle(runtime_ref)
                except HandleDisposalError as exc:
                    cleanup_errors.append(str(exc))
                except (StaleHandleError, TypeError):
                    continue
                except Exception:  # noqa: BLE001
                    cleanup_errors.append("Runtime handle cleanup failed.")

        automatic_warnings: list[str] = []
        self._release_owner_scope(
            record.owner_scope,
            warn=automatic_warnings.append,
        )
        cleanup_errors.extend(automatic_warnings)
        record.source_refs = self._without_handle_refs(record.source_refs)
        record.materialized_refs = self._without_handle_refs(
            record.materialized_refs
        )
        self._refresh_transport_refs(record)
        return cleanup_errors

    def _release_session_handle(self, value: Any, *, owner_scope: str) -> None:
        runtime_ref = coerce_runtime_handle_ref(value)
        if runtime_ref is None or runtime_ref.owner_scope != owner_scope:
            return
        try:
            self._worker_services.release_handle(runtime_ref)
        except (StaleHandleError, TypeError):
            return

    @staticmethod
    def _without_handle_refs(ref_map: Mapping[str, Any]) -> dict[str, Any]:
        return {
            str(key): value
            for key, value in ref_map.items()
            if coerce_runtime_handle_ref(value) is None
        }

    @staticmethod
    def _report_cleanup_warning(
        message: str,
        *,
        warn: Callable[[str], None] | None = None,
    ) -> None:
        try:
            if warn is None:
                _LOGGER.warning(message)
            else:
                warn(message)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Viewer session cleanup warning sink failed.")

    def _release_owner_scope(
        self,
        owner_scope: str,
        *,
        warn: Callable[[str], None] | None = None,
    ) -> None:
        if not str(owner_scope).strip():
            return
        self._worker_services.handle_registry.release_owner_scope(
            owner_scope,
            warn=warn,
        )

    def _cached_materialization_event(
        self,
        record: _ViewerSessionRecord,
        *,
        command: MaterializeViewerDataCommand,
        output_profile: str,
        export_formats: tuple[str, ...],
    ) -> ViewerDataMaterializedEvent | None:
        if record.rerun_required or not self._is_transport_live(record.transport):
            return None

        cached_refs: dict[str, Any] = {}
        if output_profile in {"memory", "both"}:
            dataset_ref = record.materialized_refs.get("dataset")
            if dataset_ref is not None:
                cached_refs["dataset"] = dataset_ref
            elif output_profile == "memory":
                return None

        requested_artifact_keys = export_formats or tuple(
            key
            for key, value in record.materialized_refs.items()
            if isinstance(value, RuntimeArtifactRef)
        )
        if output_profile in {"stored", "both"}:
            missing_artifacts = [
                key for key in requested_artifact_keys
                if not isinstance(record.materialized_refs.get(key), RuntimeArtifactRef)
            ]
            if missing_artifacts:
                return None
            cached_refs.update(
                {
                    key: record.materialized_refs[key]
                    for key in requested_artifact_keys
                    if key in record.materialized_refs
                }
            )

        if not cached_refs:
            return None

        summary = record.public_summary()
        summary["materialized_output_profile"] = output_profile
        self._refresh_public_contract(record)
        public_summary, public_options = self._public_event_contract(record, summary=summary)
        return ViewerDataMaterializedEvent(
            request_id=command.request_id,
            workspace_id=record.workspace_id,
            node_id=record.node_id,
            session_id=record.session_id,
            backend_id=record.backend_id,
            data_refs=copy.deepcopy(cached_refs),
            transport=copy.deepcopy(record.transport),
            transport_revision=record.transport_revision,
            live_open_status=record.live_open_status,
            live_open_blocker=copy.deepcopy(record.live_open_blocker),
            camera_state=copy.deepcopy(record.camera_state),
            playback_state=copy.deepcopy(record.playback_state),
            summary=public_summary,
            options=public_options,
            workspace_invalidation_epoch=command.workspace_invalidation_epoch,
            node_invalidation_epoch=command.node_invalidation_epoch,
        )


__all__ = [
    "build_run_required_viewer_session_model",
    "build_viewer_session_model",
    "coerce_viewer_session_model",
    "projection_safe_viewer_transport",
    "ViewerSessionService",
]
