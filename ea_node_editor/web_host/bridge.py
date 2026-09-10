from __future__ import annotations

import base64
import binascii
import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from ea_node_editor.common.artifact_refs import ManagedArtifactRef, parse_artifact_ref
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore, StagedArtifactEntry
from ea_node_editor.settings import (
    PROJECT_ARTIFACT_SESSION_STAGING_DIRNAME,
    PROJECT_ARTIFACT_STORE_METADATA_KEY,
    recent_session_path,
)

MAX_SCENE_STATE_PAYLOAD_BYTES = 50_000_000
WEB_SURFACE_BRIDGE_OBJECT_NAME = "webSurfaceBridge"
_JSON_SEPARATORS = (",", ":")
_WEB_SURFACE_STAGING_ROOT = "web/excalidraw"
_INVALID_ARTIFACT_TOKEN_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_SUPPORTED_IMAGE_MIME_TYPES = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_PREVIEW_MIME_TYPE = "image/png"


class _SceneStateValidationError(ValueError):
    pass


class WebSurfaceArtifactError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _DecodedDataUrl:
    mime_type: str
    data: bytes

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True, slots=True)
class _PendingArtifactWrite:
    artifact_id: str
    io_dir: str
    subdirectory: str
    filename: str
    payload: bytes
    slot: str
    mime_type: str
    sha256: str
    size: int
    name: str = ""

    def extra_metadata(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mime_type": self.mime_type,
            "sha256": self.sha256,
            "size": self.size,
        }
        if self.name:
            payload["name"] = self.name
        return payload


@dataclass(frozen=True, slots=True)
class _PreparedSceneState:
    scene_state: dict[str, Any]
    pending_writes: tuple[_PendingArtifactWrite, ...] = ()

    def commit(self, artifact_service: "WebSurfaceArtifactService | None") -> None:
        if not self.pending_writes:
            return
        if artifact_service is None:
            raise WebSurfaceArtifactError("Artifact storage is not connected.")
        artifact_service.stage_artifacts(self.pending_writes)


@dataclass(frozen=True, slots=True)
class WebSurfaceAssetWriteResult:
    artifact_ref: str
    mime_type: str
    size: int
    sha256: str
    path: Path


def _snapshot_staged_payload(
    store: ProjectArtifactStore,
    relative_path: str,
) -> bytes | None:
    root = store.active_staging_root()
    if root is None:
        raise WebSurfaceArtifactError("Artifact staging root is unavailable.")
    destination = store.staged_target_path(relative_path)
    try:
        relative_parts = destination.relative_to(root).parts
    except ValueError as exc:
        raise WebSurfaceArtifactError("Artifact target is outside the staging root.") from exc

    def _is_link_or_reparse(path_stat: Any) -> bool:
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return stat.S_ISLNK(path_stat.st_mode) or bool(
            reparse_flag
            and getattr(path_stat, "st_file_attributes", 0) & reparse_flag
        )

    root_stat = root.lstat()
    if _is_link_or_reparse(root_stat) or not stat.S_ISDIR(root_stat.st_mode):
        raise WebSurfaceArtifactError("Artifact staging root is not a safe directory.")

    current = root
    for part in relative_parts[:-1]:
        current /= part
        try:
            current_stat = current.lstat()
        except FileNotFoundError:
            break
        if _is_link_or_reparse(current_stat) or not stat.S_ISDIR(current_stat.st_mode):
            raise WebSurfaceArtifactError("Artifact target parent is not a safe directory.")

    try:
        destination_stat = destination.lstat()
    except FileNotFoundError:
        return None
    if _is_link_or_reparse(destination_stat) or not stat.S_ISREG(destination_stat.st_mode):
        raise WebSurfaceArtifactError("Artifact target is not a regular file.")
    return destination.read_bytes()


class WebSurfaceArtifactService:
    """Artifact-store adapter for web-surface image and preview payloads."""

    def __init__(
        self,
        *,
        project_path: str | Path | Callable[[], str | Path | None] | None = None,
        project_metadata: Mapping[str, Any] | Callable[[], Mapping[str, Any] | None] | None = None,
        artifact_store: ProjectArtifactStore | Callable[[], ProjectArtifactStore | None] | None = None,
        persist_project_metadata: Callable[[dict[str, Any]], None] | None = None,
        persist_artifact_store_metadata: Callable[[dict[str, Any]], None] | None = None,
        persist_artifact_store: Callable[[ProjectArtifactStore], None] | None = None,
        temporary_root_parent: str | Path | Callable[[], str | Path | None] | None = None,
        node_workspace_id: str = "",
        node_workspace_name: str = "",
        node_id: str = "",
        node_title: str = "",
        node_type: str = "",
    ) -> None:
        self._project_path_source = project_path
        self._project_metadata_source = project_metadata
        self._artifact_store_source = artifact_store
        self._persist_project_metadata = persist_project_metadata
        self._persist_artifact_store_metadata = persist_artifact_store_metadata
        self._persist_artifact_store = persist_artifact_store
        self._temporary_root_parent_source = temporary_root_parent
        self._node_workspace_id = _coerce_optional_str(node_workspace_id)
        self._node_workspace_name = _coerce_optional_str(node_workspace_name)
        self._node_id = _coerce_optional_str(node_id)
        self._node_title = _coerce_optional_str(node_title)
        self._node_type = _coerce_optional_str(node_type)
        self._store: ProjectArtifactStore | None = artifact_store if isinstance(artifact_store, ProjectArtifactStore) else None

    @property
    def store(self) -> ProjectArtifactStore:
        if self._store is not None:
            return self._store

        callback_store = self._callback_value(self._artifact_store_source)
        if isinstance(callback_store, ProjectArtifactStore):
            self._store = callback_store
            return self._store

        self._store = ProjectArtifactStore.from_project_metadata(
            project_path=self._callback_value(self._project_path_source),
            project_metadata=self._project_metadata(),
        )
        return self._store

    def prepare_scene_state(
        self,
        scene_state: dict[str, Any],
        *,
        max_payload_bytes: int,
        artifact_scope: str = "",
    ) -> _PreparedSceneState:
        files = scene_state.get("files")
        if not isinstance(files, Mapping):
            return _PreparedSceneState(copy.deepcopy(scene_state))

        next_state = copy.deepcopy(scene_state)
        next_files = dict(next_state.get("files") or {})
        pending_writes: list[_PendingArtifactWrite] = []
        for file_id, raw_file_entry in sorted(files.items(), key=lambda item: str(item[0])):
            if not isinstance(raw_file_entry, Mapping) or "dataURL" not in raw_file_entry:
                continue
            file_entry = dict(raw_file_entry)
            decoded = _decode_data_url(
                file_entry.get("dataURL"),
                supported_mime_types=_SUPPORTED_IMAGE_MIME_TYPES,
                max_payload_bytes=max_payload_bytes,
            )
            artifact_id = _web_artifact_id(
                "asset",
                _scoped_web_artifact_key(file_id, artifact_scope=artifact_scope),
                decoded.sha256,
            )
            suffix = _SUPPORTED_IMAGE_MIME_TYPES[decoded.mime_type]
            file_name = _coerce_optional_str(file_entry.get("name"))
            pending_writes.append(
                _PendingArtifactWrite(
                    artifact_id=artifact_id,
                    io_dir="in",
                    subdirectory="web/excalidraw/assets",
                    filename=f"{artifact_id}{suffix}",
                    payload=decoded.data,
                    slot=_web_artifact_slot("asset", file_id, artifact_scope=artifact_scope),
                    mime_type=decoded.mime_type,
                    sha256=decoded.sha256,
                    size=decoded.size,
                    name=file_name,
                )
            )
            next_files[str(file_id)] = _persistent_excalidraw_file_entry(
                artifact_ref=self.store.staged_ref(artifact_id),
                source_entry=file_entry,
                decoded=decoded,
                name=file_name,
            )

        if not pending_writes:
            return _PreparedSceneState(next_state)
        next_state["files"] = next_files
        return _PreparedSceneState(next_state, tuple(pending_writes))

    def stage_preview(
        self,
        *,
        payload: bytes,
        mime_type: str,
        width: int,
        height: int,
        name: str = "",
        artifact_scope: str = "",
    ) -> WebSurfaceAssetWriteResult:
        if mime_type != _PREVIEW_MIME_TYPE:
            raise WebSurfaceArtifactError("Preview export must be an image/png data URL.")
        digest = hashlib.sha256(payload).hexdigest()
        artifact_id = _web_artifact_id(
            "preview",
            _scoped_web_artifact_key(f"{width}x{height}", artifact_scope=artifact_scope),
            digest,
        )
        return self.stage_artifact(
            _PendingArtifactWrite(
                artifact_id=artifact_id,
                io_dir="out",
                subdirectory="web/excalidraw/previews",
                filename=f"{artifact_id}.png",
                payload=payload,
                slot=_web_artifact_slot("preview", artifact_scope=artifact_scope),
                mime_type=mime_type,
                sha256=digest,
                size=len(payload),
                name=name,
            )
        )

    def stage_artifacts(
        self,
        pending_writes: tuple[_PendingArtifactWrite, ...] | list[_PendingArtifactWrite],
    ) -> tuple[WebSurfaceAssetWriteResult, ...]:
        if not pending_writes:
            return ()
        store = self.store
        try:
            store.ensure_staging_root(
                temporary_root_parent=self._temporary_root_parent(),
            )
            prepared_writes: list[
                tuple[_PendingArtifactWrite, str, Path, dict[str, Any]]
            ] = []
            for pending_write in pending_writes:
                artifact_paths = store.node_artifact_paths(
                    artifact_id=pending_write.artifact_id,
                    workspace_id=self._node_workspace_id,
                    workspace_name=self._node_workspace_name,
                    node_id=self._node_id or "web_surface",
                    node_title=self._node_title or "Web Surface",
                    node_type=self._node_type or "Web Surface",
                    io_dir=pending_write.io_dir,
                    subdirectory=pending_write.subdirectory,
                    filename=pending_write.filename,
                )
                relative_path = artifact_paths.staged_relative_path
                destination = store.staged_target_path(relative_path)
                prepared_writes.append(
                    (
                        pending_write,
                        relative_path,
                        destination,
                        {**pending_write.extra_metadata(), **artifact_paths.metadata},
                    )
                )

            pending_ids = {pending_write.artifact_id for pending_write in pending_writes}
            pending_slots = {pending_write.slot for pending_write in pending_writes if pending_write.slot}
            affected_entries = [
                copy.deepcopy(entry)
                for entry in store.state.staged.values()
                if entry.artifact_id in pending_ids
                or (entry.slot is not None and entry.slot in pending_slots)
            ]
            if any(
                entry.absolute_path_hint or not entry.relative_path
                for entry in affected_entries
            ):
                raise WebSurfaceArtifactError(
                    "Existing artifact cannot be safely replaced."
                )

            snapshot_paths = dict.fromkeys(
                [
                    *(entry.relative_path for entry in affected_entries if entry.relative_path),
                    *(relative_path for _, relative_path, _, _ in prepared_writes),
                ]
            )
            path_snapshots = {
                relative_path: _snapshot_staged_payload(store, relative_path)
                for relative_path in snapshot_paths
            }
        except WebSurfaceArtifactError:
            raise
        except (OSError, ValueError) as exc:
            raise WebSurfaceArtifactError("Artifact payload could not be written.") from exc

        results: list[WebSurfaceAssetWriteResult] = []
        try:
            for pending_write, relative_path, destination, _extra in prepared_writes:
                _snapshot_staged_payload(store, relative_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(pending_write.payload)

            for pending_write, relative_path, destination, extra in prepared_writes:
                store.register_staged_entry(
                    pending_write.artifact_id,
                    relative_path=relative_path,
                    slot=pending_write.slot,
                    extra=extra,
                )
                results.append(
                    WebSurfaceAssetWriteResult(
                        artifact_ref=store.staged_ref(pending_write.artifact_id),
                        mime_type=pending_write.mime_type,
                        size=pending_write.size,
                        sha256=pending_write.sha256,
                        path=destination,
                    )
                )
            self._persist_store_metadata(store)
        except Exception as exc:  # noqa: BLE001 - cleanup must not mask the original failure
            self._rollback_staged_artifacts(
                store,
                pending_ids=pending_ids,
                affected_entries=affected_entries,
                path_snapshots=path_snapshots,
            )
            if isinstance(exc, WebSurfaceArtifactError):
                raise
            if not isinstance(exc, (OSError, ValueError)):
                raise
            raise WebSurfaceArtifactError("Artifact payload could not be written.") from exc
        return tuple(results)

    def stage_artifact(self, pending_write: _PendingArtifactWrite) -> WebSurfaceAssetWriteResult:
        return self.stage_artifacts((pending_write,))[0]

    def _rollback_staged_artifacts(
        self,
        store: ProjectArtifactStore,
        *,
        pending_ids: set[str],
        affected_entries: list[StagedArtifactEntry],
        path_snapshots: dict[str, bytes | None],
    ) -> None:
        affected_ids = {entry.artifact_id for entry in affected_entries}
        try:
            store.discard_staged_entries(pending_ids | affected_ids)
        except Exception:  # noqa: BLE001 - preserve the original staging failure
            pass
        for relative_path, payload in path_snapshots.items():
            try:
                _snapshot_staged_payload(store, relative_path)
                destination = store.staged_target_path(relative_path)
                if payload is None:
                    destination.unlink(missing_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(payload)
            except Exception:  # noqa: BLE001 - continue cleaning remaining batch paths
                continue
        for entry in affected_entries:
            try:
                store.register_staged_entry(
                    entry.artifact_id,
                    relative_path=entry.relative_path,
                    slot=entry.slot,
                    extra=copy.deepcopy(entry.extra),
                )
            except Exception:  # noqa: BLE001 - continue restoring remaining descriptors
                continue
        try:
            self._persist_store_metadata(store)
        except Exception:  # noqa: BLE001 - preserve the original staging failure
            pass

    def asset_data_url(self, artifact_ref: str) -> dict[str, Any]:
        parsed = parse_artifact_ref(artifact_ref)
        if parsed is None:
            raise WebSurfaceArtifactError("Asset request must use an artifact ref.")

        store = self.store
        entry = None
        path = None
        if isinstance(parsed, ManagedArtifactRef):
            entry = store.managed_entry(parsed.artifact_id)
            path = store.resolve_managed_path(parsed.artifact_id)
        else:
            entry = store.staged_entry(parsed.artifact_id)
            path = store.resolve_staged_path(parsed.artifact_id)

        if entry is None or path is None:
            raise WebSurfaceArtifactError("Artifact ref could not be resolved.")
        if not path.is_file():
            raise WebSurfaceArtifactError("Artifact payload is missing.")

        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise WebSurfaceArtifactError("Artifact payload could not be read.") from exc
        mime_type = _metadata_mime_type(getattr(entry, "extra", {}), path)
        if mime_type not in _SUPPORTED_IMAGE_MIME_TYPES:
            raise WebSurfaceArtifactError(f"Unsupported image MIME type: {mime_type or 'unknown'}.")

        digest = hashlib.sha256(payload).hexdigest()
        return {
            "artifact_ref": artifact_ref,
            "mime_type": mime_type,
            "size": len(payload),
            "sha256": digest,
            "data_url": _encode_data_url(mime_type, payload),
        }

    def _persist_store_metadata(self, store: ProjectArtifactStore) -> None:
        if self._persist_artifact_store is not None:
            self._persist_artifact_store(store)

        metadata = copy.deepcopy(store.metadata)
        if self._persist_artifact_store_metadata is not None:
            self._persist_artifact_store_metadata(metadata)

        if self._persist_project_metadata is not None:
            project_metadata = self._project_metadata()
            project_metadata[PROJECT_ARTIFACT_STORE_METADATA_KEY] = metadata
            self._persist_project_metadata(project_metadata)

    def _project_metadata(self) -> dict[str, Any]:
        metadata = self._callback_value(self._project_metadata_source)
        return copy.deepcopy(dict(metadata)) if isinstance(metadata, Mapping) else {}

    def _temporary_root_parent(self) -> Path:
        source_value = self._callback_value(self._temporary_root_parent_source)
        if source_value:
            return Path(source_value)
        return recent_session_path().parent / PROJECT_ARTIFACT_SESSION_STAGING_DIRNAME

    @staticmethod
    def _callback_value(source: Any) -> Any:
        return source() if callable(source) else source


class WebSurfaceBridge(QObject):
    state_changed = pyqtSignal(name="stateChanged")
    error_changed = pyqtSignal(name="errorChanged")

    def __init__(
        self,
        initial_state: dict[str, Any] | None = None,
        parent: QObject | None = None,
        *,
        artifact_service: WebSurfaceArtifactService | None = None,
        project_path: str | Path | Callable[[], str | Path | None] | None = None,
        project_metadata: Mapping[str, Any] | Callable[[], Mapping[str, Any] | None] | None = None,
        artifact_store: ProjectArtifactStore | Callable[[], ProjectArtifactStore | None] | None = None,
        persist_project_metadata: Callable[[dict[str, Any]], None] | None = None,
        persist_artifact_store_metadata: Callable[[dict[str, Any]], None] | None = None,
        persist_artifact_store: Callable[[ProjectArtifactStore], None] | None = None,
        temporary_root_parent: str | Path | Callable[[], str | Path | None] | None = None,
        max_payload_bytes: int = MAX_SCENE_STATE_PAYLOAD_BYTES,
        artifact_scope: str = "",
        node_workspace_id: str = "",
        node_workspace_name: str = "",
        node_id: str = "",
        node_title: str = "",
        node_type: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName(WEB_SURFACE_BRIDGE_OBJECT_NAME)
        self._max_payload_bytes = _normalize_payload_limit(max_payload_bytes)
        self._artifact_scope = _coerce_optional_str(artifact_scope)
        self._artifact_service = artifact_service or _artifact_service_from_constructor_args(
            project_path=project_path,
            project_metadata=project_metadata,
            artifact_store=artifact_store,
            persist_project_metadata=persist_project_metadata,
            persist_artifact_store_metadata=persist_artifact_store_metadata,
            persist_artifact_store=persist_artifact_store,
            temporary_root_parent=temporary_root_parent,
            node_workspace_id=node_workspace_id,
            node_workspace_name=node_workspace_name,
            node_id=node_id,
            node_title=node_title,
            node_type=node_type,
        )
        self._scene_state = _normalize_scene_state(
            {} if initial_state is None else initial_state,
            max_payload_bytes=self._max_payload_bytes,
            artifact_service=self._artifact_service,
            artifact_scope=self._artifact_scope,
        )
        self._last_error = ""

    @pyqtProperty("QVariantMap", notify=state_changed)
    def scene_state(self) -> dict[str, Any]:
        return self.load_state()

    @pyqtProperty(str, notify=error_changed)
    def last_error(self) -> str:
        return self._last_error

    @pyqtProperty(bool, notify=error_changed)
    def has_error(self) -> bool:
        return bool(self._last_error)

    @pyqtProperty(int, constant=True)
    def max_payload_bytes(self) -> int:
        return self._max_payload_bytes

    @pyqtSlot(result="QVariantMap")
    def load_state(self) -> dict[str, Any]:
        return copy.deepcopy(self._scene_state)

    @pyqtSlot("QVariant", result=bool)
    def save_state(self, payload: Any) -> bool:
        try:
            scene_state = _normalize_scene_state(
                payload,
                max_payload_bytes=self._max_payload_bytes,
                artifact_service=self._artifact_service,
                artifact_scope=self._artifact_scope,
            )
        except (_SceneStateValidationError, WebSurfaceArtifactError) as exc:
            self._set_error(str(exc))
            return False

        changed = scene_state != self._scene_state
        self._scene_state = scene_state
        self._clear_error()
        if changed:
            self.state_changed.emit()
        return True

    @pyqtSlot(result="QVariantMap")
    @pyqtSlot(str, result="QVariantMap")
    @pyqtSlot("QVariant", result="QVariantMap")
    def asset_request(self, payload: Any = "") -> dict[str, Any]:
        normalized_asset_id, artifact_ref = _asset_request_ref(payload, self._scene_state)
        if self._artifact_service is None:
            return {
                "ok": False,
                "asset_id": normalized_asset_id,
                "artifact_ref": artifact_ref,
                "mime_type": "",
                "data_url": "",
                "dataURL": "",
                "error": "Asset lookup is not connected.",
            }
        try:
            asset = self._artifact_service.asset_data_url(artifact_ref)
        except WebSurfaceArtifactError as exc:
            return {
                "ok": False,
                "asset_id": normalized_asset_id,
                "artifact_ref": artifact_ref,
                "mime_type": "",
                "data_url": "",
                "dataURL": "",
                "error": str(exc),
            }
        data_url = str(asset["data_url"])
        return {
            "ok": True,
            "asset_id": normalized_asset_id,
            "artifact_ref": artifact_ref,
            "mime_type": asset["mime_type"],
            "data_url": data_url,
            "dataURL": data_url,
            "size": asset["size"],
            "sha256": asset["sha256"],
            "error": "",
        }

    @pyqtSlot(result="QVariantMap")
    @pyqtSlot("QVariant", result="QVariantMap")
    def export_preview(self, payload: Any = None) -> dict[str, Any]:
        if self._artifact_service is None:
            return {
                "ok": False,
                "preview_ref": "",
                "artifact_ref": "",
                "mime_type": "",
                "width": 0,
                "height": 0,
                "size": 0,
                "sha256": "",
                "error": "Preview export is not connected.",
            }
        try:
            preview_payload = _preview_export_payload(payload, max_payload_bytes=self._max_payload_bytes)
            result = self._artifact_service.stage_preview(
                **preview_payload,
                artifact_scope=self._artifact_scope,
            )
        except WebSurfaceArtifactError as exc:
            return {
                "ok": False,
                "preview_ref": "",
                "artifact_ref": "",
                "mime_type": "",
                "width": 0,
                "height": 0,
                "size": 0,
                "sha256": "",
                "error": str(exc),
            }
        return {
            "ok": True,
            "preview_ref": result.artifact_ref,
            "artifact_ref": result.artifact_ref,
            "mime_type": result.mime_type,
            "width": preview_payload["width"],
            "height": preview_payload["height"],
            "size": result.size,
            "sha256": result.sha256,
            "error": "",
        }

    def _set_error(self, message: str) -> None:
        normalized = str(message or "Scene state could not be saved.")
        if normalized == self._last_error:
            return
        self._last_error = normalized
        self.error_changed.emit()

    def _clear_error(self) -> None:
        if not self._last_error:
            return
        self._last_error = ""
        self.error_changed.emit()


def _normalize_payload_limit(value: int) -> int:
    limit = int(value)
    if limit < 1:
        raise ValueError("max_payload_bytes must be at least 1")
    return limit


def _normalize_scene_state(
    payload: Any,
    *,
    max_payload_bytes: int,
    artifact_service: WebSurfaceArtifactService | None = None,
    artifact_scope: str = "",
) -> dict[str, Any]:
    decoded = _decode_scene_state_payload(payload, max_payload_bytes=max_payload_bytes)
    if not isinstance(decoded, dict):
        raise _SceneStateValidationError("Scene state must be a JSON object.")
    _validate_json_value(decoded, path="$")
    prepared = _prepare_artifact_backed_scene_state(
        decoded,
        artifact_service=artifact_service,
        max_payload_bytes=max_payload_bytes,
        artifact_scope=artifact_scope,
    )
    encoded = _encode_scene_state(prepared.scene_state)
    _enforce_payload_size(encoded, max_payload_bytes=max_payload_bytes)
    prepared.commit(artifact_service)
    return json.loads(encoded)


def _decode_scene_state_payload(payload: Any, *, max_payload_bytes: int) -> Any:
    if isinstance(payload, str):
        _enforce_payload_size(payload, max_payload_bytes=max_payload_bytes)
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise _SceneStateValidationError(
                "Scene state must be valid JSON object data."
            ) from exc
    return payload


def _validate_json_value(value: Any, *, path: str) -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise _SceneStateValidationError(f"Scene state contains a non-finite number at {path}.")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise _SceneStateValidationError(
                    f"Scene state object keys must be strings at {path}."
                )
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise _SceneStateValidationError(f"Scene state contains non-JSON data at {path}.")


def _encode_scene_state(scene_state: dict[str, Any]) -> str:
    try:
        return json.dumps(
            scene_state,
            allow_nan=False,
            ensure_ascii=False,
            separators=_JSON_SEPARATORS,
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise _SceneStateValidationError("Scene state must be JSON-compatible.") from exc


def _enforce_payload_size(payload: str, *, max_payload_bytes: int) -> None:
    if len(payload.encode("utf-8")) <= max_payload_bytes:
        return
    raise _SceneStateValidationError(
        f"Scene state payload exceeds {max_payload_bytes} bytes."
    )


def _artifact_service_from_constructor_args(
    *,
    project_path: str | Path | Callable[[], str | Path | None] | None,
    project_metadata: Mapping[str, Any] | Callable[[], Mapping[str, Any] | None] | None,
    artifact_store: ProjectArtifactStore | Callable[[], ProjectArtifactStore | None] | None,
    persist_project_metadata: Callable[[dict[str, Any]], None] | None,
    persist_artifact_store_metadata: Callable[[dict[str, Any]], None] | None,
    persist_artifact_store: Callable[[ProjectArtifactStore], None] | None,
    temporary_root_parent: str | Path | Callable[[], str | Path | None] | None,
    node_workspace_id: str = "",
    node_workspace_name: str = "",
    node_id: str = "",
    node_title: str = "",
    node_type: str = "",
) -> WebSurfaceArtifactService | None:
    if not any(
        (
            project_path is not None,
            project_metadata is not None,
            artifact_store is not None,
            persist_project_metadata is not None,
            persist_artifact_store_metadata is not None,
            persist_artifact_store is not None,
            temporary_root_parent is not None,
            node_workspace_id,
            node_workspace_name,
            node_id,
            node_title,
            node_type,
        )
    ):
        return None
    return WebSurfaceArtifactService(
        project_path=project_path,
        project_metadata=project_metadata,
        artifact_store=artifact_store,
        persist_project_metadata=persist_project_metadata,
        persist_artifact_store_metadata=persist_artifact_store_metadata,
        persist_artifact_store=persist_artifact_store,
        temporary_root_parent=temporary_root_parent,
        node_workspace_id=node_workspace_id,
        node_workspace_name=node_workspace_name,
        node_id=node_id,
        node_title=node_title,
        node_type=node_type,
    )


def _prepare_artifact_backed_scene_state(
    scene_state: dict[str, Any],
    *,
    artifact_service: WebSurfaceArtifactService | None,
    max_payload_bytes: int,
    artifact_scope: str = "",
) -> _PreparedSceneState:
    if not _scene_state_has_inline_file_data(scene_state):
        return _PreparedSceneState(copy.deepcopy(scene_state))
    if artifact_service is None:
        raise WebSurfaceArtifactError("Artifact storage is not connected.")
    return artifact_service.prepare_scene_state(
        scene_state,
        max_payload_bytes=max_payload_bytes,
        artifact_scope=artifact_scope,
    )


def _scene_state_has_inline_file_data(scene_state: dict[str, Any]) -> bool:
    files = scene_state.get("files")
    if not isinstance(files, Mapping):
        return False
    return any(isinstance(value, Mapping) and "dataURL" in value for value in files.values())


def _persistent_excalidraw_file_entry(
    *,
    artifact_ref: str,
    source_entry: Mapping[str, Any],
    decoded: _DecodedDataUrl,
    name: str,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "artifact_ref": artifact_ref,
        "mimeType": decoded.mime_type,
        "created": copy.deepcopy(source_entry.get("created", 0)),
        "lastRetrieved": copy.deepcopy(source_entry.get("lastRetrieved", 0)),
        "size": decoded.size,
        "sha256": decoded.sha256,
    }
    if name:
        entry["name"] = name
    return entry


def _asset_request_ref(payload: Any, scene_state: dict[str, Any]) -> tuple[str, str]:
    if isinstance(payload, Mapping):
        asset_id = _coerce_optional_str(
            payload.get("asset_id")
            or payload.get("assetId")
            or payload.get("file_id")
            or payload.get("fileId")
            or payload.get("id")
        )
        artifact_ref = _coerce_optional_str(
            payload.get("artifact_ref")
            or payload.get("artifactRef")
            or payload.get("preview_ref")
            or payload.get("previewRef")
            or payload.get("ref")
        )
    else:
        text = _coerce_optional_str(payload)
        artifact_ref = text if parse_artifact_ref(text) is not None else ""
        asset_id = "" if artifact_ref else text

    if not artifact_ref and asset_id:
        artifact_ref = _artifact_ref_for_asset_id(scene_state, asset_id)
    return asset_id, artifact_ref


def _artifact_ref_for_asset_id(scene_state: dict[str, Any], asset_id: str) -> str:
    files = scene_state.get("files")
    if not isinstance(files, Mapping):
        return ""
    entry = files.get(asset_id)
    if not isinstance(entry, Mapping):
        return ""
    return _coerce_optional_str(entry.get("artifact_ref") or entry.get("artifactRef"))


def _preview_export_payload(payload: Any, *, max_payload_bytes: int) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        data_url = payload.get("dataURL") or payload.get("data_url") or payload.get("previewDataURL")
        width = _coerce_non_negative_int(payload.get("width"))
        height = _coerce_non_negative_int(payload.get("height"))
        name = _coerce_optional_str(payload.get("name"))
    else:
        data_url = payload
        width = 0
        height = 0
        name = ""

    decoded = _decode_data_url(
        data_url,
        supported_mime_types={_PREVIEW_MIME_TYPE: ".png"},
        max_payload_bytes=max_payload_bytes,
    )
    return {
        "payload": decoded.data,
        "mime_type": decoded.mime_type,
        "width": width,
        "height": height,
        "name": name,
    }


def _decode_data_url(
    value: Any,
    *,
    supported_mime_types: Mapping[str, str],
    max_payload_bytes: int,
) -> _DecodedDataUrl:
    text = _coerce_optional_str(value)
    if not text.startswith("data:") or "," not in text:
        raise WebSurfaceArtifactError("Image payload must be a base64 data URL.")
    _enforce_artifact_payload_size(text, max_payload_bytes=max_payload_bytes)

    metadata, encoded_payload = text[5:].split(",", 1)
    metadata_parts = [part.strip() for part in metadata.split(";") if part.strip()]
    mime_type = metadata_parts[0].lower() if metadata_parts else ""
    flags = {part.lower() for part in metadata_parts[1:]}
    if mime_type not in supported_mime_types:
        raise WebSurfaceArtifactError(f"Unsupported image MIME type: {mime_type or 'unknown'}.")
    if "base64" not in flags:
        raise WebSurfaceArtifactError("Image data URL must be base64 encoded.")
    try:
        payload = base64.b64decode(encoded_payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise WebSurfaceArtifactError("Image data URL contains invalid base64 data.") from exc
    if not payload:
        raise WebSurfaceArtifactError("Image data URL payload is empty.")
    return _DecodedDataUrl(mime_type=mime_type, data=payload)


def _encode_data_url(mime_type: str, payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _enforce_artifact_payload_size(payload: str, *, max_payload_bytes: int) -> None:
    if len(payload.encode("utf-8")) <= max_payload_bytes:
        return
    raise WebSurfaceArtifactError(f"Image payload exceeds {max_payload_bytes} bytes.")


def _web_artifact_id(kind: str, key: Any, sha256: str) -> str:
    safe_kind = _sanitize_artifact_token(kind, fallback="artifact")
    safe_key = _sanitize_artifact_token(key, fallback="payload")
    return f"web-surface.{safe_kind}.{safe_key}.{sha256[:16]}"


def _scoped_web_artifact_key(key: Any, *, artifact_scope: str) -> str:
    scope_token = _web_artifact_scope_token(artifact_scope)
    safe_key = _sanitize_artifact_token(key, fallback="payload")
    if not scope_token:
        return safe_key
    return f"{scope_token}.{safe_key}"


def _web_artifact_slot(kind: str, key: Any = "", *, artifact_scope: str = "") -> str:
    parts = ["web_surface", _sanitize_artifact_token(kind, fallback="artifact")]
    if key != "":
        parts.append(_sanitize_artifact_token(key, fallback="payload"))
    scope_token = _web_artifact_scope_token(artifact_scope)
    if scope_token:
        parts.append(scope_token)
    return ".".join(parts)


def _web_artifact_scope_token(value: Any) -> str:
    text = _coerce_optional_str(value)
    if not text:
        return ""
    token = _sanitize_artifact_token(text, fallback="")
    if token:
        return token
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _web_artifact_relative_path(category: str, artifact_id: str, suffix: str) -> str:
    normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    return PurePosixPath(
        _WEB_SURFACE_STAGING_ROOT,
        _sanitize_artifact_token(category, fallback="assets"),
        f"{artifact_id}{normalized_suffix}",
    ).as_posix()


def _sanitize_artifact_token(value: Any, *, fallback: str) -> str:
    text = _INVALID_ARTIFACT_TOKEN_CHARS.sub("_", str(value).strip())
    text = text.strip("._-")
    if not text or not re.match(r"^[A-Za-z0-9]", text):
        return fallback
    return text


def _coerce_optional_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_non_negative_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(number, 0)


def _metadata_mime_type(metadata: Any, path: Path) -> str:
    if isinstance(metadata, Mapping):
        mime_type = _coerce_optional_str(metadata.get("mime_type") or metadata.get("mimeType")).lower()
        if mime_type:
            return mime_type
    suffix = path.suffix.lower()
    for mime_type, expected_suffix in _SUPPORTED_IMAGE_MIME_TYPES.items():
        if suffix == expected_suffix:
            return mime_type
    return ""


__all__ = [
    "MAX_SCENE_STATE_PAYLOAD_BYTES",
    "WEB_SURFACE_BRIDGE_OBJECT_NAME",
    "WebSurfaceArtifactError",
    "WebSurfaceArtifactService",
    "WebSurfaceBridge",
]
