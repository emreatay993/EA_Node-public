# Purpose: Bridge QML viewer-session state, commands, and authoritative runtime projections.
# Map: subsystems/viewer_surfaces.md
# Tests: tests/test_viewer_session_bridge.py
# Landmarks: _ViewerSessionProjection; _ViewerSessionPresentationService; ViewerSessionBridge; execution-event projection

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from ea_node_editor.common.coercions import coerce_float
from ea_node_editor.common.scene_protocol import (
    normalize_scene_styles,
    normalize_viewer_background,
    normalize_viewer_colormap,
    normalize_viewer_deform_scale,
    normalize_viewer_representation,
    normalize_viewer_result_component,
    normalize_viewer_scalar_range_bound,
    normalize_viewer_scalar_range_mode,
)
from ea_node_editor.execution.viewer_messages import (
    normalize_viewer_invalidation_node_ids,
    normalize_viewer_node_invalidation_epochs,
    viewer_epoch_snapshot_digest,
)
from ea_node_editor.execution.viewer_session_service import (
    build_run_required_viewer_session_model,
    coerce_viewer_session_model,
    projection_safe_viewer_transport,
)
from ea_node_editor.runtime_contracts import (
    COREX_VIEWER_SESSION_HANDLE_KIND,
    VIEWER_SESSION_DATA_TYPE_ID,
    DataTree,
    DataTypeCatalog,
    RuntimeHandleRef,
    deserialize_runtime_value,
)

if TYPE_CHECKING:
    from ea_node_editor.graph.project_state import ProjectData
    from ea_node_editor.nodes.registry import NodeRegistry
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

_LIVE_MODE_FULL = "full"
_LIVE_MODE_PROXY = "proxy"
_OPEN_SESSION_PHASES = frozenset({"open", "opening"})
_VIEWER_EVENT_TYPES = frozenset(
    {
        "viewer_session_opened",
        "viewer_session_updated",
        "viewer_data_materialized",
        "viewer_session_closed",
        "viewer_session_failed",
        "viewer_query_result",
    }
)
_NODE_SETTLED_EVENT_TYPE = "node_settled"
_RUNTIME_VIEWER_OUTPUT_KEY = "session"


@dataclass(slots=True)
class _ViewerPendingDisplay:
    phase: str | None = None
    last_error: str | None = None
    playback_state: str | None = None
    step_index: int | None = None
    invalidated_reason: str | None = None
    close_reason: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    materialization: bool = False


@dataclass(slots=True)
class _ViewerSessionProjection:
    workspace_id: str
    node_id: str
    session_id: str
    phase: str = "closed"
    request_id: str = ""
    last_command: str = ""
    last_error: str = ""
    playback_state: str = "paused"
    step_index: int = 0
    cache_state: str = "empty"
    invalidated_reason: str = ""
    close_reason: str = ""
    backend_id: str = ""
    transport_revision: int = 0
    live_open_status: str = ""
    live_open_blocker: dict[str, Any] = field(default_factory=dict)
    data_refs: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    pending_display: _ViewerPendingDisplay = field(
        default_factory=_ViewerPendingDisplay
    )
    camera_state_locally_captured: bool = False

    def payload(self, *, include_pending: bool = True) -> dict[str, Any]:
        pending = self.pending_display if include_pending else _ViewerPendingDisplay()
        summary = _copy_mapping(self.summary)
        summary.update(copy.deepcopy(pending.summary))
        options = _copy_mapping(self.options)
        options.update(copy.deepcopy(pending.options))
        playback_state = (
            pending.playback_state
            or _string(options.get("playback_state", self.playback_state))
            or "paused"
        )
        step_index = (
            pending.step_index
            if pending.step_index is not None
            else _coerce_step_index(options.get("step_index"), default=self.step_index)
        )
        live_mode = _normalize_live_mode(options.get("live_mode", _LIVE_MODE_PROXY))
        playback = {"state": playback_state, "step_index": step_index}
        options["playback_state"] = playback_state
        options["step_index"] = step_index
        options["playback"] = copy.deepcopy(playback)
        options["live_mode"] = live_mode
        if self.camera_state:
            summary.setdefault("camera_state", copy.deepcopy(self.camera_state))
            summary.setdefault("camera", copy.deepcopy(self.camera_state))

        return {
            "workspace_id": self.workspace_id,
            "node_id": self.node_id,
            "session_id": self.session_id,
            "phase": pending.phase if pending.phase is not None else self.phase,
            "request_id": self.request_id,
            "last_command": self.last_command,
            "last_error": pending.last_error
            if pending.last_error is not None
            else self.last_error,
            "playback_state": playback_state,
            "step_index": step_index,
            "playback": playback,
            "cache_state": self.cache_state,
            "invalidated_reason": (
                pending.invalidated_reason
                if pending.invalidated_reason is not None
                else self.invalidated_reason
            ),
            "close_reason": (
                pending.close_reason
                if pending.close_reason is not None
                else self.close_reason
            ),
            "backend_id": self.backend_id,
            "transport_revision": self.transport_revision,
            "live_mode": live_mode,
            "live_open_status": self.live_open_status,
            "live_open_blocker": copy.deepcopy(self.live_open_blocker),
            "data_refs": copy.deepcopy(self.data_refs),
            "transport": copy.deepcopy(self.transport),
            "camera_state": copy.deepcopy(self.camera_state),
            "summary": summary,
            "options": options,
        }


def _copy_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): copy.deepcopy(item) for key, item in value.items()}


def _string(value: Any) -> str:
    return str(value or "").strip()


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = _string(value).casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    return default


_VIEW_OPTION_COERCERS: dict[str, Any] = {
    "show_mesh_edges": _coerce_bool,
    "colormap": normalize_viewer_colormap,
    "result_component": normalize_viewer_result_component,
    "scalar_range_mode": normalize_viewer_scalar_range_mode,
    "scalar_range_min": normalize_viewer_scalar_range_bound,
    "scalar_range_max": normalize_viewer_scalar_range_bound,
    "show_scalar_bar": lambda value: _coerce_bool(value, default=True),
    "deform_scale": normalize_viewer_deform_scale,
    "hover_probe": _coerce_bool,
    "show_minmax_markers": _coerce_bool,
    "viewer_background": normalize_viewer_background,
    "representation": normalize_viewer_representation,
    "scene_styles": normalize_scene_styles,
    "parallel_projection": _coerce_bool,
    "clip_enabled": _coerce_bool,
    "clip_axis": lambda value: (
        _string(value).casefold()
        if _string(value).casefold() in {"x", "y", "z"}
        else "x"
    ),
    "clip_offset": coerce_float,
    "show_attribute_colors": _coerce_bool,
    "show_orientation_triad": lambda value: _coerce_bool(value, default=True),
    "show_view_cube": lambda value: _coerce_bool(value, default=True),
    "show_world_axes": _coerce_bool,
}


def _session_option_updates_for_node_property(key: Any, value: Any) -> dict[str, Any]:
    normalized_key = _string(key)
    coercer = _VIEW_OPTION_COERCERS.get(normalized_key)
    if coercer is None:
        return {}
    try:
        return {normalized_key: coercer(value)}
    except (TypeError, ValueError):
        return {}


def _normalize_live_mode(value: Any) -> str:
    normalized = _string(value).lower() or _LIVE_MODE_PROXY
    if normalized not in {_LIVE_MODE_PROXY, _LIVE_MODE_FULL}:
        return _LIVE_MODE_PROXY
    return normalized


def _coerce_step_index(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_playback_payload(
    value: Any,
    *,
    fallback_state: str = "paused",
    fallback_step_index: int = 0,
) -> dict[str, Any]:
    payload = _copy_mapping(value)
    state = (
        _string(payload.get("state") or payload.get("playback_state")) or fallback_state
    )
    step_index = _coerce_step_index(
        payload.get("step_index"),
        default=fallback_step_index,
    )
    return {
        "state": state,
        "step_index": step_index,
    }


class _ViewerSessionPresentationService:
    def __init__(
        self,
        *,
        capture_overlay_camera_state: Callable[..., Any] | None,
    ) -> None:
        self._capture_overlay_camera_state = capture_overlay_camera_state

    def projected_payload(self, state: _ViewerSessionProjection) -> dict[str, Any]:
        return state.payload()

    def capture_live_overlay_camera_state(
        self,
        state: _ViewerSessionProjection,
    ) -> dict[str, Any]:
        capture = self._capture_overlay_camera_state
        if not callable(capture):
            return copy.deepcopy(state.camera_state)
        try:
            captured = _copy_mapping(
                capture(
                    state.node_id,
                    workspace_id=state.workspace_id,
                )
            )
        except Exception:  # noqa: BLE001
            return copy.deepcopy(state.camera_state)
        if captured:
            return captured
        return copy.deepcopy(state.camera_state)

class ViewerSessionBridge(QObject):
    sessions_changed = pyqtSignal()
    active_workspace_changed = pyqtSignal()
    last_error_changed = pyqtSignal()
    viewer_query_completed = pyqtSignal(str, "QVariantMap", name="viewerQueryCompleted")

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        execution_client_provider: Callable[[], Any],
        active_workspace_id_provider: Callable[[], str],
        workspace_provider: Callable[[str], Any],
        scene_bridge: "GraphSceneBridge | None" = None,
        data_types: DataTypeCatalog,
        capture_overlay_camera_state: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self._execution_client_provider = execution_client_provider
        self._active_workspace_id_provider = active_workspace_id_provider
        self._workspace_provider = workspace_provider
        self._scene_bridge = scene_bridge
        self._data_types = data_types
        self._sessions: dict[tuple[str, str], _ViewerSessionProjection] = {}
        self._presentation_service = _ViewerSessionPresentationService(
            capture_overlay_camera_state=capture_overlay_camera_state,
        )
        self._pending_reset_seed: (
            dict[tuple[str, str], _ViewerSessionProjection] | None
        ) = None
        self._explicit_inline_node_by_workspace: dict[str, str] = {}
        self._viewer_presentation_holds: set[tuple[str, str]] = set()
        self._workspace_invalidation_epochs: dict[str, int] = {}
        self._node_invalidation_epochs: dict[tuple[str, str], int] = {}
        self._pending_query_requests: dict[
            str, tuple[str, str, str, int, int]
        ] = {}
        self._last_error = ""
        self._live_mode_sync_in_progress = False

        if scene_bridge is not None:
            scene_bridge.workspace_changed.connect(self._on_workspace_changed)
            scene_bridge.selection_changed.connect(self._on_selection_changed)
            scene_bridge.nodes_changed.connect(self._on_nodes_changed)

    def assert_registry_replaceable(self) -> None:
        if any(
            self._display_phase(state) in {*_OPEN_SESSION_PHASES, "closing"}
            for state in self._sessions.values()
        ):
            raise RuntimeError(
                "Cannot replace the registry while a viewer session is active"
            )

    def replace_data_types(self, data_types: DataTypeCatalog) -> None:
        if not isinstance(data_types, DataTypeCatalog):
            raise TypeError("data_types must be a DataTypeCatalog")
        self._data_types = data_types

    @pyqtProperty(str, notify=active_workspace_changed)
    def active_workspace_id(self) -> str:
        return self._current_workspace_id()

    @pyqtProperty("QVariantList", notify=sessions_changed)
    def sessions_model(self) -> list[dict[str, Any]]:
        workspace_id = self._current_workspace_id()
        sessions = [
            self._projected_payload(state)
            for state in self._sessions.values()
            if state.workspace_id == workspace_id
        ]
        sessions.sort(
            key=lambda item: (str(item.get("phase", "")), str(item.get("node_id", "")))
        )
        return sessions

    @pyqtProperty(int, notify=sessions_changed)
    def session_count(self) -> int:
        workspace_id = self._current_workspace_id()
        return sum(
            1 for state in self._sessions.values() if state.workspace_id == workspace_id
        )

    @pyqtProperty(str, notify=last_error_changed)
    def last_error(self) -> str:
        return self._last_error

    @pyqtSlot(str, result="QVariantMap")
    @pyqtSlot(str, "QVariantMap", result="QVariantMap")
    def session_state(self, node_id: str, payload: Any = None) -> dict[str, Any]:
        workspace_id = self._workspace_id_from_payload(payload)
        normalized_node_id = _string(node_id)
        if not workspace_id or not normalized_node_id:
            return {}
        state = self._sessions.get((workspace_id, normalized_node_id))
        return self._projected_payload(state) if state is not None else {}

    def query_session(
        self,
        *,
        workspace_id: str,
        node_id: str,
        session_id: str,
        query_type: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_workspace_id = _string(workspace_id)
        normalized_node_id = _string(node_id)
        normalized_session_id = _string(session_id)
        normalized_query_type = _string(query_type)
        state = self._sessions.get((normalized_workspace_id, normalized_node_id))
        if (
            state is None
            or not normalized_session_id
            or state.session_id != normalized_session_id
            or not normalized_query_type
        ):
            return {
                "pending": False,
                "supported": False,
                "value": {},
                "explanation": "The active viewer session is not ready for this query.",
            }
        request_id = self._send_execution_command(
            "query_viewer_session",
            workspace_id=state.workspace_id,
            node_id=state.node_id,
            session_id=state.session_id,
            backend_id=state.backend_id,
            query_type=normalized_query_type,
            payload=dict(payload or {}),
            options=self._effective_options(state),
        )
        if not request_id:
            return {
                "pending": False,
                "supported": False,
                "value": {},
                "explanation": self._last_error
                or "The viewer query could not be dispatched.",
            }
        workspace_epoch, node_epoch = self._viewer_epochs(
            state.workspace_id, state.node_id
        )
        self._pending_query_requests[request_id] = (
            state.workspace_id,
            state.node_id,
            state.session_id,
            workspace_epoch,
            node_epoch,
        )
        return {
            "pending": True,
            "request_id": request_id,
            "query_type": normalized_query_type,
            "supported": False,
            "value": {},
            "explanation": "Engineering query queued.",
        }

    @pyqtSlot(str, str, "QVariant", result=bool)
    @pyqtSlot(str, str, "QVariant", "QVariantMap", result=bool)
    def sync_node_property_option(
        self,
        node_id: str,
        key: str,
        value: Any,
        payload: Any = None,
    ) -> bool:
        option_updates = _session_option_updates_for_node_property(key, value)
        if not option_updates:
            return False
        state = self._active_session(node_id, payload)
        if state is None:
            return False
        effective_options = self._effective_options(state)
        if all(
            effective_options.get(option_key) == option_value
            for option_key, option_value in option_updates.items()
        ):
            return False
        return self._update_session_command(
            node_id,
            payload,
            command_name="sync_node_property_option",
            option_updates=option_updates,
        )

    @pyqtSlot(str, result=str)
    @pyqtSlot(str, "QVariantMap", result=str)
    def open(self, node_id: str, payload: Any = None) -> str:
        workspace_id = self._workspace_id_from_payload(payload)
        normalized_node_id = _string(node_id)
        if not workspace_id or not normalized_node_id:
            return ""

        existing_state = self._sessions.get((workspace_id, normalized_node_id))
        payload_map = _copy_mapping(payload)
        data_refs = _copy_mapping(payload_map.get("data_refs"))
        transport = _copy_mapping(payload_map.get("transport"))
        if existing_state is not None:
            if not data_refs:
                data_refs = copy.deepcopy(existing_state.data_refs)
            if not transport:
                transport = copy.deepcopy(existing_state.transport)
        if existing_state is None and not data_refs and not transport:
            return ""

        state = existing_state or self._ensure_session_state(
            workspace_id, normalized_node_id
        )
        summary = _copy_mapping(payload_map.get("summary"))
        if not summary and existing_state is not None:
            summary = _copy_mapping(existing_state.summary)
        summary.pop("close_reason", None)
        summary.pop("invalidated_reason", None)
        option_updates = _copy_mapping(payload_map.get("options"))
        if existing_state is not None:
            option_updates.pop("reason", None)
            option_updates.pop("release_handles", None)
        backend_id = self._resolve_backend_id(state, payload_map)
        camera_state = _copy_mapping(payload_map.get("camera_state"))
        if not camera_state and existing_state is not None:
            camera_state = copy.deepcopy(existing_state.camera_state)
        playback = _normalize_playback_payload(
            payload_map.get("playback_state") or option_updates,
            fallback_state=state.playback_state,
            fallback_step_index=state.step_index,
        )
        transport_revision = _coerce_step_index(
            payload_map.get("transport_revision"),
            default=state.transport_revision,
        )
        live_open_status = (
            _string(payload_map.get("live_open_status")) or state.live_open_status
        )
        live_open_blocker = _copy_mapping(payload_map.get("live_open_blocker"))
        if not live_open_blocker:
            live_open_blocker = copy.deepcopy(state.live_open_blocker)

        state.last_command = "open"
        self._clear_pending_projection(state)
        self._merge_pending_projection(
            state,
            phase="opening",
            last_error="",
            invalidated_reason="",
            close_reason="",
        )

        request_options = self._request_options(state, option_updates)
        request_options.pop("reason", None)
        request_options.pop("release_handles", None)
        request_options["playback_state"] = playback["state"]
        request_options["step_index"] = playback["step_index"]
        request_options["live_mode"] = self._desired_live_mode_map(workspace_id).get(
            (workspace_id, normalized_node_id),
            _LIVE_MODE_PROXY,
        )
        self._merge_pending_projection(
            state,
            summary=summary,
            options=request_options,
        )
        request_id = self._send_execution_command(
            "open_viewer_session",
            workspace_id=workspace_id,
            node_id=normalized_node_id,
            session_id=state.session_id,
            backend_id=backend_id,
            data_refs=data_refs,
            transport=transport,
            transport_revision=transport_revision,
            live_open_status=live_open_status,
            live_open_blocker=live_open_blocker,
            summary=summary,
            camera_state=camera_state,
            playback_state=playback,
            options=request_options,
        )
        if not request_id:
            self._merge_pending_projection(
                state,
                phase="error",
                last_error=self._last_error,
            )
            self.sessions_changed.emit()
            return ""

        state.request_id = request_id
        state.backend_id = backend_id or state.backend_id
        state.camera_state = camera_state or state.camera_state
        self.sessions_changed.emit()
        return state.session_id

    @pyqtSlot(str, result=bool)
    @pyqtSlot(str, "QVariantMap", result=bool)
    def close(self, node_id: str, payload: Any = None) -> bool:
        state = self._active_session(node_id, payload)
        if state is None:
            return False

        payload_map = _copy_mapping(payload)
        option_updates = _copy_mapping(payload_map.get("options"))
        if "reason" not in option_updates:
            option_updates["reason"] = "user_close"
        request_id = self._send_execution_command(
            "close_viewer_session",
            workspace_id=state.workspace_id,
            node_id=state.node_id,
            session_id=state.session_id,
            options=option_updates,
        )
        if not request_id:
            state.last_command = "close"
            self._merge_pending_projection(
                state,
                phase="error",
                last_error=self._last_error,
            )
            self.sessions_changed.emit()
            return False

        state.request_id = request_id
        state.last_command = "close"
        self._clear_pending_projection(state)
        self._merge_pending_projection(
            state,
            phase="closing",
            last_error="",
            close_reason=_string(option_updates.get("reason")),
        )
        self._clear_explicit_inline_if_matches(state.workspace_id, state.node_id)
        self.sessions_changed.emit()
        self._sync_live_modes(state.workspace_id)
        return True

    @pyqtSlot(str, result=bool)
    @pyqtSlot(str, "QVariantMap", result=bool)
    def play(self, node_id: str, payload: Any = None) -> bool:
        return self._update_session_command(
            node_id,
            payload,
            command_name="play",
            option_updates={"playback_state": "playing"},
        )

    @pyqtSlot(str, result=bool)
    @pyqtSlot(str, "QVariantMap", result=bool)
    def pause(self, node_id: str, payload: Any = None) -> bool:
        return self._update_session_command(
            node_id,
            payload,
            command_name="pause",
            option_updates={"playback_state": "paused"},
        )

    @pyqtSlot(str, result=bool)
    @pyqtSlot(str, "QVariantMap", result=bool)
    def step(self, node_id: str, payload: Any = None) -> bool:
        state = self._active_session(node_id, payload)
        if state is None:
            return False
        step_index = self._effective_step_index(state) + 1
        return self._update_session_command(
            node_id,
            payload,
            command_name="step",
            option_updates={
                "playback_state": "paused",
                "step_index": step_index,
            },
        )

    @pyqtSlot(str, result=bool)
    @pyqtSlot(str, "QVariantMap", result=bool)
    def step_back(self, node_id: str, payload: Any = None) -> bool:
        state = self._active_session(node_id, payload)
        if state is None:
            return False
        step_index = max(0, self._effective_step_index(state) - 1)
        return self._update_session_command(
            node_id,
            payload,
            command_name="step_back",
            option_updates={
                "playback_state": "paused",
                "step_index": step_index,
            },
        )

    @pyqtSlot(str, int, result=bool)
    @pyqtSlot(str, int, "QVariantMap", result=bool)
    def set_step_index(
        self, node_id: str, step_index: int, payload: Any = None
    ) -> bool:
        state = self._active_session(node_id, payload)
        if state is None:
            return False
        return self._update_session_command(
            node_id,
            payload,
            command_name="set_step_index",
            option_updates={
                "playback_state": "paused",
                "step_index": max(0, _coerce_step_index(step_index)),
            },
        )

    @pyqtSlot(result=bool)
    @pyqtSlot("QVariantMap", result=bool)
    def clear_viewer_focus(self, payload: Any = None) -> bool:
        workspace_id = self._workspace_id_from_payload(payload)
        if not workspace_id:
            return False
        changed = self._explicit_inline_node_by_workspace.pop(workspace_id, None) is not None
        self._sync_live_modes(workspace_id)
        if changed:
            self.sessions_changed.emit()
        return True

    @pyqtSlot(str, bool, result=bool)
    @pyqtSlot(str, bool, "QVariantMap", result=bool)
    def set_embedded_interaction_active(
        self, node_id: str, active: bool, payload: Any = None
    ) -> bool:
        workspace_id = self._workspace_id_from_payload(payload)
        normalized_node_id = _string(node_id)
        if not workspace_id or not normalized_node_id:
            return False
        state = self._active_session(normalized_node_id, {"workspace_id": workspace_id})
        if state is None:
            return False
        current_node_id = self._explicit_inline_node_by_workspace.get(workspace_id)
        if bool(active):
            changed = current_node_id != normalized_node_id
            self._explicit_inline_node_by_workspace[workspace_id] = normalized_node_id
        else:
            changed = current_node_id == normalized_node_id
            if changed:
                self._explicit_inline_node_by_workspace.pop(workspace_id, None)
        self._sync_live_modes(workspace_id)
        if changed:
            self.sessions_changed.emit()
        return True

    @pyqtSlot(str, result=bool)
    @pyqtSlot(str, "QVariantMap", result=bool)
    def add_viewer_presentation_hold(self, node_id: str, payload: Any = None) -> bool:
        """Keep a session live while a detached/external presentation shows it."""
        workspace_id = self._workspace_id_from_payload(payload)
        normalized_node_id = _string(node_id)
        if not workspace_id or not normalized_node_id:
            return False
        key = (workspace_id, normalized_node_id)
        changed = key not in self._viewer_presentation_holds
        self._viewer_presentation_holds.add(key)
        self._sync_live_modes(workspace_id)
        if changed:
            self.sessions_changed.emit()
        return True

    @pyqtSlot(str, result=bool)
    @pyqtSlot(str, "QVariantMap", result=bool)
    def remove_viewer_presentation_hold(
        self, node_id: str, payload: Any = None
    ) -> bool:
        workspace_id = self._workspace_id_from_payload(payload)
        normalized_node_id = _string(node_id)
        if not workspace_id or not normalized_node_id:
            return False
        key = (workspace_id, normalized_node_id)
        changed = key in self._viewer_presentation_holds
        self._viewer_presentation_holds.discard(key)
        self._sync_live_modes(workspace_id)
        if changed:
            self.sessions_changed.emit()
        return True

    def project_loaded(
        self,
        project: "ProjectData | None",
        registry: "NodeRegistry | None",
        *,
        reseed_on_next_reset: bool = False,
    ) -> None:
        old_workspace_ids = {workspace_id for workspace_id, _node_id in self._sessions}
        incoming_workspaces = getattr(project, "workspaces", {})
        incoming_workspace_ids = (
            {str(workspace_id) for workspace_id in incoming_workspaces}
            if isinstance(incoming_workspaces, dict)
            else set()
        )
        for workspace_id in sorted(old_workspace_ids | incoming_workspace_ids):
            self._advance_invalidation_epochs(workspace_id, None)
        next_sessions = self._build_project_projection(project, registry)
        self._sessions = next_sessions
        self._explicit_inline_node_by_workspace.clear()
        self._viewer_presentation_holds.clear()
        self._pending_reset_seed = (
            copy.deepcopy(next_sessions) if reseed_on_next_reset else None
        )
        self.sessions_changed.emit()

    def adopt_committed_invalidation(
        self,
        *,
        workspace_id: str,
        node_ids: Iterable[str] | None,
        workspace_epoch: int,
        node_epochs: Iterable[tuple[str, int]],
        snapshot_digest: str,
        reason: str,
        run_id: str = "",
    ) -> bool:
        normalized_workspace_id = _string(workspace_id)
        normalized_reason = _string(reason)
        normalized_node_ids = normalize_viewer_invalidation_node_ids(node_ids)
        normalized_node_epochs = normalize_viewer_node_invalidation_epochs(
            tuple(node_epochs)
        )
        if not normalized_workspace_id or not normalized_reason:
            return False
        if snapshot_digest != viewer_epoch_snapshot_digest(
            workspace_id=normalized_workspace_id,
            node_ids=normalized_node_ids,
            workspace_epoch=workspace_epoch,
            node_epochs=normalized_node_epochs,
        ):
            return False
        current_workspace_epoch = self._workspace_invalidation_epochs.get(
            normalized_workspace_id, 0
        )
        if workspace_epoch < current_workspace_epoch:
            return False
        if normalized_node_ids is None:
            if normalized_node_epochs or workspace_epoch <= current_workspace_epoch:
                return False
        elif normalized_node_ids == ():
            return bool(
                not normalized_node_epochs
                and workspace_epoch == current_workspace_epoch
            )
        elif tuple(node_id for node_id, _epoch in normalized_node_epochs) != normalized_node_ids:
            return False

        workspace_advanced = workspace_epoch > current_workspace_epoch
        if not workspace_advanced and normalized_node_ids not in {None, ()}:
            for node_id, epoch in normalized_node_epochs:
                if epoch != self._node_invalidation_epochs.get(
                    (normalized_workspace_id, node_id), 0
                ) + 1:
                    return False
        if workspace_advanced:
            self._workspace_invalidation_epochs[normalized_workspace_id] = (
                workspace_epoch
            )
            for key in tuple(self._node_invalidation_epochs):
                if key[0] == normalized_workspace_id:
                    self._node_invalidation_epochs.pop(key, None)
        for node_id, epoch in normalized_node_epochs:
            key = (normalized_workspace_id, node_id)
            if epoch < self._node_invalidation_epochs.get(key, 0):
                return False
            self._node_invalidation_epochs[key] = epoch
        cleanup_node_ids = None if workspace_advanced else normalized_node_ids
        for request_id, pending in tuple(self._pending_query_requests.items()):
            pending_workspace_id, pending_node_id, *_rest = pending
            if pending_workspace_id == normalized_workspace_id and (
                cleanup_node_ids is None or pending_node_id in cleanup_node_ids
            ):
                self._pending_query_requests.pop(request_id, None)
        changed = False
        for state in self._sessions.values():
            if state.workspace_id != normalized_workspace_id or (
                cleanup_node_ids is not None
                and state.node_id not in cleanup_node_ids
            ):
                continue
            self._project_run_required_state(
                state, reason=normalized_reason, run_id=run_id
            )
            self._viewer_presentation_holds.discard(
                (state.workspace_id, state.node_id)
            )
            changed = True
        explicit_node_id = self._explicit_inline_node_by_workspace.get(
            normalized_workspace_id, ""
        )
        if cleanup_node_ids is None or explicit_node_id in cleanup_node_ids:
            self._explicit_inline_node_by_workspace.pop(
                normalized_workspace_id, None
            )
        if changed:
            self.sessions_changed.emit()
        return True

    def project_all_run_required(self, *, reason: str) -> None:
        normalized_reason = _string(reason)
        if not normalized_reason or not self._sessions:
            return
        for workspace_id in sorted(
            {state.workspace_id for state in self._sessions.values()}
        ):
            self._advance_invalidation_epochs(workspace_id, None)
        for state in self._sessions.values():
            self._project_run_required_state(state, reason=normalized_reason)
            self._viewer_presentation_holds.discard((state.workspace_id, state.node_id))
        self._explicit_inline_node_by_workspace.clear()
        self.sessions_changed.emit()

    def reset_all_sessions(self, *, reason: str = "") -> None:
        if reason:
            self._set_last_error("")
        pending_seed = (
            copy.deepcopy(self._pending_reset_seed)
            if self._pending_reset_seed is not None
            else None
        )
        workspace_ids = {
            *self._workspace_invalidation_epochs,
            *(workspace_id for workspace_id, _node_id in self._sessions),
        }
        for workspace_id in sorted(workspace_ids):
            self._advance_invalidation_epochs(workspace_id, None)
        self._pending_reset_seed = None
        self._sessions.clear()
        self._explicit_inline_node_by_workspace.clear()
        self._viewer_presentation_holds.clear()
        if pending_seed is not None and _string(reason) == "project_close":
            self._sessions = pending_seed
        self.sessions_changed.emit()

    def _viewer_epochs(self, workspace_id: str, node_id: str) -> tuple[int, int]:
        return (
            self._workspace_invalidation_epochs.get(workspace_id, 0),
            self._node_invalidation_epochs.get((workspace_id, node_id), 0),
        )

    def _advance_invalidation_epochs(
        self,
        workspace_id: str,
        node_ids: tuple[str, ...] | None,
    ) -> None:
        if node_ids == ():
            return
        if node_ids is None:
            self._workspace_invalidation_epochs[workspace_id] = (
                self._workspace_invalidation_epochs.get(workspace_id, 0) + 1
            )
            for key in tuple(self._node_invalidation_epochs):
                if key[0] == workspace_id:
                    self._node_invalidation_epochs.pop(key, None)
        else:
            for node_id in node_ids:
                key = (workspace_id, node_id)
                self._node_invalidation_epochs[key] = (
                    self._node_invalidation_epochs.get(key, 0) + 1
                )
        for request_id, pending in tuple(self._pending_query_requests.items()):
            pending_workspace_id, pending_node_id, *_rest = pending
            if pending_workspace_id == workspace_id and (
                node_ids is None or pending_node_id in node_ids
            ):
                self._pending_query_requests.pop(request_id, None)
        execution_client = self._execution_client()
        invalidate = getattr(execution_client, "invalidate_viewer_requests", None)
        if callable(invalidate):
            invalidate(workspace_id, node_ids)

    def _event_epoch_is_current(self, event: Mapping[str, Any]) -> bool:
        workspace_id = _string(event.get("workspace_id"))
        node_id = _string(event.get("node_id"))
        if not workspace_id or not node_id:
            return False
        workspace_epoch, node_epoch = self._viewer_epochs(workspace_id, node_id)
        return (
            _coerce_step_index(event.get("workspace_invalidation_epoch"))
            == workspace_epoch
            and _coerce_step_index(event.get("node_invalidation_epoch"))
            == node_epoch
        )

    def _build_project_projection(
        self,
        project: "ProjectData | None",
        registry: "NodeRegistry | None",
    ) -> dict[tuple[str, str], _ViewerSessionProjection]:
        if project is None:
            return {}
        next_sessions: dict[tuple[str, str], _ViewerSessionProjection] = {}
        previous_sessions = copy.deepcopy(self._sessions)
        workspaces = getattr(project, "workspaces", {})
        if not isinstance(workspaces, dict):
            return {}
        for workspace_id, workspace in workspaces.items():
            nodes = getattr(workspace, "nodes", {})
            if not isinstance(nodes, dict):
                continue
            for node_id, node in nodes.items():
                if not self._is_viewer_node(node, registry):
                    continue
                session_key = (str(workspace_id), str(node_id))
                baseline = previous_sessions.get(session_key)
                state = baseline or _ViewerSessionProjection(
                    workspace_id=str(workspace_id),
                    node_id=str(node_id),
                    session_id=self._build_session_id(str(workspace_id), str(node_id)),
                )
                state.workspace_id = str(workspace_id)
                state.node_id = str(node_id)
                state.session_id = self._build_session_id(
                    state.workspace_id, state.node_id
                )
                state.request_id = ""
                state.last_error = ""
                state.invalidated_reason = ""
                state.close_reason = ""
                self._clear_pending_projection(state)
                self._project_run_required_state(
                    state,
                    reason="project_reload",
                    run_id="",
                )
                next_sessions[session_key] = state
        return next_sessions

    @staticmethod
    def _is_viewer_node(node: Any, registry: "NodeRegistry | None") -> bool:
        if registry is None:
            return False
        spec_or_none = getattr(registry, "spec_or_none", None)
        if not callable(spec_or_none):
            return False
        spec = spec_or_none(_string(getattr(node, "type_id", "")))
        if spec is None:
            return False
        return _string(getattr(spec, "surface_family", "")) == "viewer"

    def _project_run_required_state(
        self,
        state: _ViewerSessionProjection,
        *,
        reason: str,
        run_id: str = "",
    ) -> None:
        self._clear_pending_projection(state)
        projection_model = build_run_required_viewer_session_model(
            state.payload(),
            reason=reason,
            run_id=run_id,
            last_command="run_required",
        )
        if not projection_model:
            return
        self._apply_session_model(state, projection_model)

    def _active_session(
        self, node_id: str, payload: Any = None
    ) -> _ViewerSessionProjection | None:
        workspace_id = self._workspace_id_from_payload(payload)
        normalized_node_id = _string(node_id)
        if not workspace_id or not normalized_node_id:
            return None
        state = self._sessions.get((workspace_id, normalized_node_id))
        if state is None or self._display_phase(state) in {
            "closed",
            "blocked",
            "error",
        }:
            return None
        return state

    def _update_session_command(
        self,
        node_id: str,
        payload: Any,
        *,
        command_name: str,
        option_updates: dict[str, Any],
    ) -> bool:
        state = self._active_session(node_id, payload)
        if state is None:
            return False
        if self._display_phase(state) == "closing":
            return False

        payload_map = _copy_mapping(payload)
        summary = _copy_mapping(payload_map.get("summary"))
        merged_option_updates = dict(option_updates)
        merged_option_updates.update(_copy_mapping(payload_map.get("options")))
        backend_id = self._resolve_backend_id(state, payload_map)
        camera_state = _copy_mapping(payload_map.get("camera_state")) or copy.deepcopy(
            state.camera_state
        )
        playback = _normalize_playback_payload(
            payload_map.get("playback_state") or merged_option_updates,
            fallback_state=state.playback_state,
            fallback_step_index=state.step_index,
        )
        request_options = self._request_options(state, merged_option_updates)
        request_id = self._send_execution_command(
            "update_viewer_session",
            workspace_id=state.workspace_id,
            node_id=state.node_id,
            session_id=state.session_id,
            backend_id=backend_id,
            camera_state=camera_state,
            playback_state=playback,
            summary=summary,
            options=request_options,
        )
        if not request_id:
            state.last_command = command_name
            self._merge_pending_projection(
                state,
                phase="error",
                last_error=self._last_error,
            )
            self.sessions_changed.emit()
            return False

        state.request_id = request_id
        state.last_command = command_name
        state.backend_id = backend_id or state.backend_id
        state.camera_state = camera_state
        self._merge_pending_projection(
            state,
            last_error="",
            summary=summary,
            options=request_options,
        )
        self.sessions_changed.emit()
        self._sync_live_modes(state.workspace_id)
        return True

    def _resolve_backend_id(
        self, state: _ViewerSessionProjection, payload_map: Mapping[str, Any]
    ) -> str:
        payload_backend_id = _string(payload_map.get("backend_id"))
        if payload_backend_id:
            return payload_backend_id
        options = _copy_mapping(payload_map.get("options"))
        summary = _copy_mapping(payload_map.get("summary"))
        return (
            _string(options.get("backend_id"))
            or _string(summary.get("backend_id"))
            or state.backend_id
        )

    @staticmethod
    def _clear_pending_projection(state: _ViewerSessionProjection) -> None:
        state.pending_display = _ViewerPendingDisplay()

    @staticmethod
    def _merge_pending_projection(
        state: _ViewerSessionProjection,
        *,
        phase: str | None = None,
        last_error: str | None = None,
        invalidated_reason: str | None = None,
        close_reason: str | None = None,
        summary: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        pending_materialization: bool | None = None,
    ) -> None:
        pending = state.pending_display
        if phase is not None:
            pending.phase = phase
        if last_error is not None:
            pending.last_error = last_error
        if invalidated_reason is not None:
            pending.invalidated_reason = invalidated_reason
        if close_reason is not None:
            pending.close_reason = close_reason
        if summary:
            pending.summary.update(copy.deepcopy(summary))
        if options:
            pending.options.update(copy.deepcopy(options))
            if "playback_state" in options:
                pending.playback_state = (
                    _string(options.get("playback_state")) or "paused"
                )
            if "step_index" in options:
                pending.step_index = _coerce_step_index(options.get("step_index"))
        if pending_materialization is not None:
            pending.materialization = pending_materialization

    @staticmethod
    def _display_phase(state: _ViewerSessionProjection) -> str:
        pending_phase = state.pending_display.phase
        return pending_phase if pending_phase is not None else state.phase

    @staticmethod
    def _effective_options(state: _ViewerSessionProjection) -> dict[str, Any]:
        options = copy.deepcopy(state.options)
        options.update(copy.deepcopy(state.pending_display.options))
        return options

    def _effective_step_index(self, state: _ViewerSessionProjection) -> int:
        return _coerce_step_index(
            self._effective_options(state).get("step_index"),
            default=state.step_index,
        )

    def _request_options(
        self, state: _ViewerSessionProjection, option_updates: dict[str, Any]
    ) -> dict[str, Any]:
        options = self._effective_options(state)
        options.update(copy.deepcopy(option_updates))
        options["playback_state"] = (
            _string(options.get("playback_state", state.playback_state)) or "paused"
        )
        options["step_index"] = _coerce_step_index(
            options.get("step_index"),
            default=self._effective_step_index(state),
        )
        options["live_mode"] = _normalize_live_mode(
            options.get("live_mode", _LIVE_MODE_PROXY)
        )
        return options

    def _materialize_options(
        self,
        state: _ViewerSessionProjection,
        option_updates: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_updates = copy.deepcopy(option_updates or {})
        requested_live_mode = _normalize_live_mode(
            normalized_updates.get(
                "live_mode",
                self._effective_options(state).get("live_mode", _LIVE_MODE_FULL),
            )
        )
        options = self._request_options(state, normalized_updates)
        if (
            requested_live_mode == _LIVE_MODE_FULL
            and "output_profile" not in normalized_updates
        ):
            output_profile = "memory"
            options.pop("export_formats", None)
        else:
            output_profile = _string(options.get("output_profile")) or "memory"
        options["output_profile"] = output_profile
        options["live_mode"] = requested_live_mode
        return options

    def _send_execution_command(self, method_name: str, **kwargs: Any) -> str:
        execution_client = self._execution_client()
        method = getattr(execution_client, method_name, None)
        if not callable(method):
            self._set_last_error(f"Execution client does not support {method_name}.")
            return ""
        try:
            request_id = method(**kwargs)
        except TypeError as exc:
            self._set_last_error(str(exc))
            return ""
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return ""
        self._set_last_error("")
        return _string(request_id)

    def _execution_client(self) -> Any:
        try:
            return self._execution_client_provider()
        except Exception:  # noqa: BLE001
            return None

    def _send_materialize_command(
        self,
        state: _ViewerSessionProjection,
        *,
        option_updates: dict[str, Any] | None = None,
    ) -> bool:
        request_options = self._materialize_options(state, option_updates)
        request_id = self._send_execution_command(
            "materialize_viewer_data",
            workspace_id=state.workspace_id,
            node_id=state.node_id,
            session_id=state.session_id,
            backend_id=state.backend_id,
            options=request_options,
        )
        if not request_id:
            state.last_command = "materialize"
            self._merge_pending_projection(
                state,
                phase="error",
                last_error=self._last_error,
            )
            return False
        state.request_id = request_id
        state.last_command = "materialize"
        self._merge_pending_projection(
            state,
            phase="open",
            last_error="",
            options=request_options,
            pending_materialization=True,
        )
        return True

    def _capture_live_overlay_camera_state(
        self,
        state: _ViewerSessionProjection,
    ) -> dict[str, Any]:
        return self._presentation_service.capture_live_overlay_camera_state(state)

    @staticmethod
    def _apply_session_model(
        state: _ViewerSessionProjection,
        session_model: Mapping[str, Any],
    ) -> None:
        playback = _copy_mapping(session_model.get("playback"))
        if not playback:
            playback = _normalize_playback_payload(
                session_model.get("playback_state"),
                fallback_state=state.playback_state,
                fallback_step_index=state.step_index,
            )
        state.workspace_id = (
            _string(session_model.get("workspace_id")) or state.workspace_id
        )
        state.node_id = _string(session_model.get("node_id")) or state.node_id
        state.session_id = _string(session_model.get("session_id")) or state.session_id
        state.phase = _string(session_model.get("phase")) or "closed"
        state.request_id = _string(session_model.get("request_id"))
        state.last_command = _string(session_model.get("last_command"))
        state.last_error = _string(session_model.get("last_error"))
        state.playback_state = (
            _string(playback.get("state", state.playback_state)) or state.playback_state
        )
        state.step_index = _coerce_step_index(
            playback.get("step_index"), default=state.step_index
        )
        state.cache_state = _string(session_model.get("cache_state")) or "empty"
        state.invalidated_reason = _string(session_model.get("invalidated_reason"))
        state.close_reason = _string(session_model.get("close_reason"))
        state.backend_id = _string(session_model.get("backend_id")) or state.backend_id
        state.transport_revision = _coerce_step_index(
            session_model.get("transport_revision"),
            default=state.transport_revision,
        )
        state.live_open_status = _string(session_model.get("live_open_status"))
        state.live_open_blocker = _copy_mapping(session_model.get("live_open_blocker"))
        state.data_refs = _copy_mapping(session_model.get("data_refs"))
        state.transport = _copy_mapping(session_model.get("transport"))
        state.camera_state = _copy_mapping(session_model.get("camera_state"))
        state.summary = _copy_mapping(session_model.get("summary"))
        state.options = _copy_mapping(session_model.get("options"))

    def _ensure_session_state(
        self, workspace_id: str, node_id: str
    ) -> _ViewerSessionProjection:
        session_key = (workspace_id, node_id)
        state = self._sessions.get(session_key)
        if state is not None:
            return state
        state = _ViewerSessionProjection(
            workspace_id=workspace_id,
            node_id=node_id,
            session_id=self._build_session_id(workspace_id, node_id),
        )
        self._sessions[session_key] = state
        return state

    @staticmethod
    def _build_session_id(workspace_id: str, node_id: str) -> str:
        digest = hashlib.sha1(f"{workspace_id}:{node_id}".encode("utf-8")).hexdigest()[
            :16
        ]
        return f"viewer_session_{digest}"

    def _workspace_id_from_payload(self, payload: Any) -> str:
        payload_map = _copy_mapping(payload)
        workspace_id = _string(payload_map.get("workspace_id"))
        if workspace_id:
            return workspace_id
        return self._current_workspace_id()

    def _current_workspace_id(self) -> str:
        if self._scene_bridge is not None:
            workspace_id = _string(getattr(self._scene_bridge, "workspace_id", ""))
            if workspace_id:
                return workspace_id
        try:
            return _string(self._active_workspace_id_provider())
        except Exception:  # noqa: BLE001
            return ""

    def handle_viewer_execution_event(self, event: dict[str, Any]) -> None:
        event_type = _string(event.get("type"))
        if event_type == _NODE_SETTLED_EVENT_TYPE:
            if self._seed_runtime_projection_from_node_settled(event):
                return
        if event_type not in _VIEWER_EVENT_TYPES:
            return

        workspace_id = _string(event.get("workspace_id"))
        node_id = _string(event.get("node_id"))
        if not workspace_id or not node_id or not self._event_epoch_is_current(event):
            return
        event_request_id = _string(event.get("request_id"))

        if event_type == "viewer_query_result":
            pending_query = self._pending_query_requests.pop(event_request_id, None)
            if pending_query is None or pending_query[:3] != (
                workspace_id,
                node_id,
                _string(event.get("session_id")),
            ):
                return
            result = {
                "pending": False,
                "request_id": _string(event.get("request_id")),
                "query_type": _string(event.get("query_type")),
                "supported": bool(event.get("supported", False)),
                "value": _copy_mapping(event.get("value")),
                "explanation": _string(event.get("explanation")),
            }
            self.viewer_query_completed.emit(node_id, result)
            return

        if (
            event_type == "viewer_session_failed"
            and _string(event.get("command")) == "query_viewer_session"
        ):
            pending_query = self._pending_query_requests.pop(event_request_id, None)
            if pending_query is not None and pending_query[:3] == (
                workspace_id,
                node_id,
                _string(event.get("session_id")),
            ):
                self.viewer_query_completed.emit(
                    node_id,
                    {
                        "pending": False,
                        "request_id": _string(event.get("request_id")),
                        "query_type": "",
                        "supported": False,
                        "value": {},
                        "explanation": _string(event.get("error"))
                        or "Engineering query failed.",
                    },
                )
            return

        state = self._sessions.get((workspace_id, node_id))
        if state is None:
            return
        event_session_id = _string(event.get("session_id"))
        if event_request_id and event_request_id != state.request_id:
            return
        if event_session_id and event_session_id != state.session_id:
            return
        event_live_mode = _string(event.get("live_mode")) or _string(
            _copy_mapping(event.get("options")).get("live_mode")
        )
        pending_live_mode = _string(state.pending_display.options.get("live_mode"))
        if (
            event_type == "viewer_session_updated"
            and state.last_command == "set_live_mode"
            and event_request_id
            and state.request_id
            and event_request_id != state.request_id
            and event_live_mode
            and pending_live_mode
            and _normalize_live_mode(event_live_mode)
            != _normalize_live_mode(pending_live_mode)
        ):
            return

        if event_type == "viewer_session_failed":
            failure_payload = state.payload(include_pending=False)
            failure_payload.update(
                {
                    "type": event_type,
                    "request_id": _string(event.get("request_id")) or state.request_id,
                    "session_id": _string(event.get("session_id")) or state.session_id,
                    "phase": "error",
                    "last_command": _string(event.get("command")),
                    "last_error": _string(event.get("error")),
                }
            )
            self._apply_authoritative_projection(state, failure_payload)
            self._clear_pending_projection(state)
            self._set_last_error(_string(event.get("error")))
            self.sessions_changed.emit()
            return

        self._set_last_error("")
        authoritative_model = self._apply_authoritative_projection(state, event)
        self._clear_pending_projection(state)
        authoritative_live_mode = _normalize_live_mode(
            authoritative_model.get("live_mode")
            or _copy_mapping(event.get("options")).get(
                "live_mode", state.options.get("live_mode")
            )
        )
        if authoritative_live_mode == _LIVE_MODE_FULL:
            # Hold the locally captured proxy camera until live mode is
            # authoritatively restored so the first refocus uses it.
            state.camera_state_locally_captured = False
        if event_type == "viewer_session_closed":
            state.camera_state_locally_captured = False
            self._clear_explicit_inline_if_matches(workspace_id, node_id)
        self.sessions_changed.emit()
        self._sync_live_modes(workspace_id)

    def _seed_runtime_projection_from_node_settled(
        self,
        event: Mapping[str, Any],
    ) -> bool:
        if _string(event.get("status")) != "completed":
            return False
        outputs = _copy_mapping(event.get("outputs"))
        settled_output = _copy_mapping(outputs.get(_RUNTIME_VIEWER_OUTPUT_KEY))
        if _string(settled_output.get("status")) != "value":
            return False
        try:
            output_tree = deserialize_runtime_value(
                settled_output.get("value"),
                catalog=self._data_types,
            )
        except (TypeError, ValueError):
            return False
        if not isinstance(output_tree, DataTree) or output_tree.item_count != 1:
            return False
        runtime_ref = next(
            item for _path, items in output_tree.branches for item in items
        )
        if (
            not isinstance(runtime_ref, RuntimeHandleRef)
            or runtime_ref.data_type_id != VIEWER_SESSION_DATA_TYPE_ID
            or runtime_ref.kind != COREX_VIEWER_SESSION_HANDLE_KIND
        ):
            return False

        workspace_id = _string(runtime_ref.metadata.get("workspace_id"))
        node_id = _string(runtime_ref.metadata.get("node_id"))
        session_id = _string(runtime_ref.metadata.get("session_id"))
        backend_id = _string(runtime_ref.metadata.get("backend_id"))
        if (
            not workspace_id
            or not node_id
            or not session_id
            or not backend_id
            or workspace_id != _string(event.get("workspace_id"))
            or node_id != _string(event.get("node_id"))
        ):
            return False

        request_id = self._send_execution_command(
            "open_viewer_session",
            workspace_id=workspace_id,
            node_id=node_id,
            session_id=session_id,
            backend_id=backend_id,
        )
        if not request_id:
            return False
        state = self._ensure_session_state(workspace_id, node_id)
        state.session_id = session_id
        state.backend_id = backend_id
        state.request_id = request_id
        state.last_command = "run_projection"
        self._clear_pending_projection(state)
        self._merge_pending_projection(
            state,
            phase="opening",
            last_error="",
            invalidated_reason="",
            close_reason="",
        )
        self.sessions_changed.emit()
        return True

    def _apply_authoritative_projection(
        self,
        state: _ViewerSessionProjection,
        event: Mapping[str, Any],
    ) -> dict[str, Any]:
        event_payload = _copy_mapping(event)
        event_type = _string(event_payload.get("type"))
        if "phase" not in event_payload:
            event_payload["phase"] = (
                "closed" if event_type == "viewer_session_closed" else "open"
            )
        summary = _copy_mapping(event_payload.get("summary"))
        options = _copy_mapping(event_payload.get("options"))
        playback_payload = _copy_mapping(event_payload.get("playback"))
        if not playback_payload:
            playback_payload = _copy_mapping(event_payload.get("playback_state"))
        if not playback_payload and "step_index" not in event_payload:
            effective_options = self._effective_options(state)
            event_payload["playback"] = {
                "state": _string(
                    options.get(
                        "playback_state",
                        state.pending_display.playback_state or state.playback_state,
                    )
                )
                or "paused",
                "step_index": _coerce_step_index(
                    options.get("step_index", effective_options.get("step_index")),
                    default=state.step_index,
                ),
            }
        if not _copy_mapping(event_payload.get("camera_state")) and state.camera_state:
            event_payload["camera_state"] = copy.deepcopy(state.camera_state)
        if "cache_state" not in event_payload:
            event_payload["cache_state"] = summary.get("cache_state", "")
        if "close_reason" not in event_payload:
            event_payload["close_reason"] = summary.get("close_reason", "")
        if "invalidated_reason" not in event_payload:
            event_payload["invalidated_reason"] = summary.get("invalidated_reason", "")
        if "live_mode" not in event_payload:
            event_payload["live_mode"] = options.get("live_mode", "")
        if event_type == "viewer_session_closed":
            event_payload["data_refs"] = {}
            event_payload["transport"] = projection_safe_viewer_transport(
                _copy_mapping(event_payload.get("transport")) or state.transport
            )
        authoritative_model = coerce_viewer_session_model(event_payload)
        if not authoritative_model:
            return {}
        preserve_locally_captured_camera = (
            state.camera_state_locally_captured
            and bool(state.camera_state)
            and _normalize_live_mode(authoritative_model.get("live_mode"))
            in {_LIVE_MODE_PROXY, _LIVE_MODE_FULL}
        )
        if preserve_locally_captured_camera:
            authoritative_model["camera_state"] = copy.deepcopy(state.camera_state)
            authoritative_summary = _copy_mapping(authoritative_model.get("summary"))
            authoritative_summary["camera"] = copy.deepcopy(state.camera_state)
            authoritative_summary["camera_state"] = copy.deepcopy(state.camera_state)
            authoritative_model["summary"] = authoritative_summary
        self._apply_session_model(state, authoritative_model)
        return authoritative_model

    def _on_workspace_changed(self, _workspace_id: str) -> None:
        previous_workspaces = tuple(self._explicit_inline_node_by_workspace)
        self._explicit_inline_node_by_workspace.clear()
        for workspace_id in previous_workspaces:
            self._sync_live_modes(workspace_id)
        self.active_workspace_changed.emit()
        self.sessions_changed.emit()
        self._sync_live_modes(self._current_workspace_id())

    def _on_selection_changed(self) -> None:
        workspace_id = self._current_workspace_id()
        explicit_node_id = self._explicit_inline_node_by_workspace.get(workspace_id, "")
        if explicit_node_id:
            selected_lookup = _copy_mapping(
                getattr(self._scene_bridge, "selected_node_lookup", {})
            )
            if not bool(selected_lookup.get(explicit_node_id, False)):
                self._explicit_inline_node_by_workspace.pop(workspace_id, None)
        self._sync_live_modes(workspace_id)

    def _on_nodes_changed(self) -> None:
        workspace_id = self._current_workspace_id()
        if not workspace_id:
            return
        workspace_node_ids = self._workspace_node_ids(workspace_id)
        if workspace_node_ids is None:
            return
        removed_keys = [
            key
            for key, state in self._sessions.items()
            if state.workspace_id == workspace_id
            and state.node_id not in workspace_node_ids
        ]
        if removed_keys:
            for key in removed_keys:
                self._viewer_presentation_holds.discard(key)
                self._sessions.pop(key, None)
            self.sessions_changed.emit()
        explicit_node_id = self._explicit_inline_node_by_workspace.get(workspace_id, "")
        if explicit_node_id and explicit_node_id not in workspace_node_ids:
            self._explicit_inline_node_by_workspace.pop(workspace_id, None)
        self._sync_live_modes(workspace_id)

    def _workspace_node_ids(self, workspace_id: str) -> set[str] | None:
        try:
            workspace = self._workspace_provider(workspace_id)
        except Exception:  # noqa: BLE001
            return None
        if workspace is None:
            return None
        nodes = getattr(workspace, "nodes", None)
        if not isinstance(nodes, dict):
            return None
        return {str(node_id) for node_id in nodes}

    def _workspace_open_states(
        self, workspace_id: str
    ) -> list[_ViewerSessionProjection]:
        states = [
            state
            for state in self._sessions.values()
            if state.workspace_id == workspace_id
            and self._display_phase(state) in _OPEN_SESSION_PHASES
        ]
        states.sort(key=lambda state: state.node_id)
        return states

    def _clear_explicit_inline_if_matches(
        self, workspace_id: str, node_id: str
    ) -> bool:
        normalized_workspace_id = _string(workspace_id)
        normalized_node_id = _string(node_id)
        if not normalized_workspace_id or not normalized_node_id:
            return False
        if (
            self._explicit_inline_node_by_workspace.get(normalized_workspace_id)
            != normalized_node_id
        ):
            return False
        self._explicit_inline_node_by_workspace.pop(normalized_workspace_id, None)
        return True

    def _projected_payload(self, state: _ViewerSessionProjection) -> dict[str, Any]:
        return self._presentation_service.projected_payload(state)

    def _desired_live_mode_map(self, workspace_id: str) -> dict[tuple[str, str], str]:
        desired_modes: dict[tuple[str, str], str] = {}
        if not workspace_id:
            return desired_modes
        states = self._workspace_open_states(workspace_id)
        if not states:
            return desired_modes

        explicit_node_id = self._explicit_inline_node_by_workspace.get(workspace_id, "")
        for state in states:
            key = (state.workspace_id, state.node_id)
            desired_modes[key] = (
                _LIVE_MODE_FULL
                if state.node_id == explicit_node_id
                or key in self._viewer_presentation_holds
                else _LIVE_MODE_PROXY
            )
        return desired_modes

    def _sync_live_modes(self, workspace_id: str) -> None:
        normalized_workspace_id = _string(workspace_id)
        if not normalized_workspace_id or self._live_mode_sync_in_progress:
            return
        desired_modes = self._desired_live_mode_map(normalized_workspace_id)
        if not desired_modes:
            return

        self._live_mode_sync_in_progress = True
        changed = False
        try:
            for state in self._workspace_open_states(normalized_workspace_id):
                if self._display_phase(state) != "open":
                    continue
                desired_mode = desired_modes.get(
                    (state.workspace_id, state.node_id), _LIVE_MODE_PROXY
                )
                changed = self._apply_desired_live_mode(state, desired_mode) or changed
        finally:
            self._live_mode_sync_in_progress = False

        if changed:
            self.sessions_changed.emit()

    def _apply_desired_live_mode(
        self, state: _ViewerSessionProjection, desired_mode: str
    ) -> bool:
        normalized_desired_mode = _normalize_live_mode(desired_mode)
        current_live_mode = _normalize_live_mode(
            self._effective_options(state).get("live_mode")
        )

        if normalized_desired_mode == _LIVE_MODE_PROXY:
            if current_live_mode != _LIVE_MODE_PROXY:
                captured_camera_state = self._capture_live_overlay_camera_state(state)
                request_options = self._request_options(
                    state, {"live_mode": _LIVE_MODE_PROXY}
                )
                request_id = self._send_execution_command(
                    "update_viewer_session",
                    workspace_id=state.workspace_id,
                    node_id=state.node_id,
                    session_id=state.session_id,
                    backend_id=state.backend_id,
                    camera_state=captured_camera_state,
                    playback_state={
                        "state": state.playback_state,
                        "step_index": int(state.step_index),
                    },
                    options=request_options,
                )
                if not request_id:
                    state.last_command = "set_live_mode"
                    self._merge_pending_projection(
                        state,
                        phase="error",
                        last_error=self._last_error,
                    )
                    return True
                state.request_id = request_id
                state.last_command = "set_live_mode"
                state.camera_state = captured_camera_state
                state.camera_state_locally_captured = bool(captured_camera_state)
                self._merge_pending_projection(
                    state,
                    phase="open",
                    last_error="",
                    options={"live_mode": _LIVE_MODE_PROXY},
                )
                return True
            return False

        if _string(state.live_open_status).lower() != "ready":
            return False
        if state.cache_state == "live_ready":
            if current_live_mode == _LIVE_MODE_FULL:
                return False
            request_options = self._request_options(
                state, {"live_mode": _LIVE_MODE_FULL}
            )
            request_id = self._send_execution_command(
                "update_viewer_session",
                workspace_id=state.workspace_id,
                node_id=state.node_id,
                session_id=state.session_id,
                backend_id=state.backend_id,
                camera_state=state.camera_state,
                playback_state={
                    "state": state.playback_state,
                    "step_index": int(state.step_index),
                },
                options=request_options,
            )
            if not request_id:
                state.last_command = "set_live_mode"
                self._merge_pending_projection(
                    state,
                    phase="error",
                    last_error=self._last_error,
                )
                return True
            state.request_id = request_id
            state.last_command = "set_live_mode"
            self._merge_pending_projection(
                state,
                phase="open",
                last_error="",
                options={"live_mode": _LIVE_MODE_FULL},
            )
            return True

        if state.pending_display.materialization:
            return False
        materialize_requested = self._send_materialize_command(
            state,
            option_updates={"live_mode": _LIVE_MODE_FULL},
        )
        return materialize_requested or self._display_phase(state) == "error"

    def _set_last_error(self, value: str) -> None:
        normalized = _string(value)
        if normalized == self._last_error:
            return
        self._last_error = normalized
        self.last_error_changed.emit()


__all__ = ["ViewerSessionBridge"]
