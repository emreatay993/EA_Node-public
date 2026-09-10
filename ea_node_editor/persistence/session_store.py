from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.persistence.serializer import ProjectDocumentSnapshot
from ea_node_editor.settings import (
    PROJECT_ARTIFACT_SESSION_STAGING_DIRNAME,
    autosave_project_path,
    recent_session_path,
)
from ea_node_editor.common.payload_tools import (
    coerce_timestamp as coerce_timestamp_value,
    document_fingerprint as document_fingerprint_value,
    write_json_atomic,
)


class _SerializerProtocol(Protocol):
    def load(self, path: str) -> ProjectData:
        ...

    def to_document(self, project: ProjectData) -> dict[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class RecentSessionAutosaveState:
    resume_fingerprint: str = ""

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "RecentSessionAutosaveState":
        if payload is None:
            return cls()
        if not isinstance(payload, Mapping):
            raise ValueError("Recent session autosave metadata must be a JSON object.")
        return cls(resume_fingerprint=str(payload.get("resume_fingerprint", "")).strip())

    def to_mapping(self) -> dict[str, Any]:
        if not self.resume_fingerprint:
            return {}
        return {"resume_fingerprint": self.resume_fingerprint}


@dataclass(frozen=True, slots=True)
class RecentSessionEnvelope:
    project_path: str = ""
    last_manual_save_ts: float = 0.0
    recent_project_paths: tuple[str, ...] = ()
    autosave: RecentSessionAutosaveState = field(default_factory=RecentSessionAutosaveState)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "RecentSessionEnvelope":
        if payload is None:
            return cls()
        if not isinstance(payload, Mapping):
            raise ValueError("Recent session payload must be a JSON object.")
        recent_paths_source = payload.get("recent_project_paths")
        if recent_paths_source is None:
            recent_paths_iterable = ()
        elif isinstance(recent_paths_source, list):
            recent_paths_iterable = recent_paths_source
        else:
            raise ValueError("recent_project_paths must be a JSON array.")
        recent_project_paths = tuple(
            text
            for item in recent_paths_iterable
            if (text := str(item).strip())
        )
        return cls(
            project_path=str(payload.get("project_path", "")).strip(),
            last_manual_save_ts=coerce_timestamp_value(payload.get("last_manual_save_ts", 0.0)),
            recent_project_paths=recent_project_paths,
            autosave=RecentSessionAutosaveState.from_mapping(payload.get("autosave")),
        )

    def to_mapping(self) -> dict[str, Any]:
        payload = {
            "project_path": self.project_path,
            "last_manual_save_ts": self.last_manual_save_ts,
            "recent_project_paths": list(self.recent_project_paths),
        }
        autosave_payload = self.autosave.to_mapping()
        if autosave_payload:
            payload["autosave"] = autosave_payload
        return payload


class SessionAutosaveStore:
    def __init__(
        self,
        *,
        serializer: _SerializerProtocol,
        session_path_provider: Callable[[], Path] = recent_session_path,
        autosave_path_provider: Callable[[], Path] = autosave_project_path,
        staging_workspace_root_provider: Callable[[], Path] | None = None,
    ) -> None:
        self._serializer = serializer
        self._session_path_provider = session_path_provider
        self._autosave_path_provider = autosave_path_provider
        self._staging_workspace_root_provider = staging_workspace_root_provider

    def replace_serializer(self, serializer: _SerializerProtocol) -> None:
        self._serializer = serializer

    def staging_workspace_root(self) -> Path:
        if self._staging_workspace_root_provider is not None:
            path = self._staging_workspace_root_provider()
        else:
            path = self._session_path_provider().parent / PROJECT_ARTIFACT_SESSION_STAGING_DIRNAME
        path.mkdir(parents=True, exist_ok=True)
        return path

    def load_session_envelope(self) -> RecentSessionEnvelope:
        session_path = self._session_path_provider()
        if not session_path.exists():
            return RecentSessionEnvelope()
        try:
            payload = json.loads(session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return RecentSessionEnvelope()
        return RecentSessionEnvelope.from_mapping(payload)

    def load_session_payload(self) -> dict[str, Any]:
        return self.load_session_envelope().to_mapping()

    def has_autosave_snapshot(self) -> bool:
        return self._autosave_path_provider().exists()

    def _coerce_snapshot(
        self,
        *,
        project_snapshot: ProjectDocumentSnapshot | Mapping[str, Any] | None = None,
        project_doc: Mapping[str, Any] | None = None,
    ) -> ProjectDocumentSnapshot:
        if isinstance(project_snapshot, ProjectDocumentSnapshot):
            return project_snapshot
        if isinstance(project_snapshot, Mapping):
            return ProjectDocumentSnapshot.from_mapping(project_snapshot)
        return ProjectDocumentSnapshot.from_mapping(project_doc)

    def _project_snapshot(self, project: ProjectData) -> ProjectDocumentSnapshot:
        return ProjectDocumentSnapshot.from_owned_document(self._serializer.to_document(project))

    def persist_session(
        self,
        *,
        project_path: str,
        last_manual_save_ts: float,
        recent_project_paths: list[str],
        autosave_resume_fingerprint: str = "",
    ) -> None:
        write_json_atomic(
            self._session_path_provider(),
            RecentSessionEnvelope(
                project_path=str(project_path).strip(),
                last_manual_save_ts=coerce_timestamp_value(last_manual_save_ts),
                recent_project_paths=tuple(
                    text
                    for path in recent_project_paths
                    if (text := str(path).strip())
                ),
                autosave=RecentSessionAutosaveState(
                    resume_fingerprint=str(autosave_resume_fingerprint).strip(),
                ),
            ).to_mapping(),
        )

    def discard_autosave_snapshot(self) -> None:
        autosave_path = self._autosave_path_provider()
        if not autosave_path.exists():
            return
        try:
            autosave_path.unlink()
        except OSError:
            return

    def autosave_if_changed(
        self,
        *,
        last_fingerprint: str,
        project_doc: Mapping[str, Any] | None = None,
        project_snapshot: ProjectDocumentSnapshot | Mapping[str, Any] | None = None,
    ) -> str:
        snapshot = self._coerce_snapshot(project_snapshot=project_snapshot, project_doc=project_doc)
        if snapshot.fingerprint == last_fingerprint:
            return last_fingerprint
        write_json_atomic(
            self._autosave_path_provider(),
            snapshot.document,
            encoded_payload=snapshot.encoded_payload,
        )
        return snapshot.fingerprint

    def load_recoverable_autosave(
        self,
        *,
        project_path: str,
        last_manual_save_ts: float,
        current_project_doc: Mapping[str, Any] | None = None,
        current_project_snapshot: ProjectDocumentSnapshot | Mapping[str, Any] | None = None,
    ) -> ProjectData | None:
        autosave_path = self._autosave_path_provider()
        if not autosave_path.exists():
            return None

        try:
            autosave_ts = autosave_path.stat().st_mtime
        except OSError:
            return None

        current_snapshot = self._coerce_snapshot(
            project_snapshot=current_project_snapshot,
            project_doc=current_project_doc,
        )
        manual_save_ts = last_manual_save_ts
        if project_path and Path(project_path).exists():
            try:
                manual_save_ts = max(manual_save_ts, Path(project_path).stat().st_mtime)
            except OSError:
                pass
        if autosave_ts <= manual_save_ts:
            return None

        try:
            recovered_project = self._serializer.load(str(autosave_path))
        except Exception:  # noqa: BLE001
            self.discard_autosave_snapshot()
            return None

        recovered_snapshot = self._project_snapshot(recovered_project)
        if current_snapshot.fingerprint == recovered_snapshot.fingerprint:
            self.discard_autosave_snapshot()
            return None

        return recovered_project

    def load_resume_autosave(self, *, expected_fingerprint: str) -> ProjectData | None:
        fingerprint = str(expected_fingerprint).strip()
        if not fingerprint:
            return None
        autosave_path = self._autosave_path_provider()
        if not autosave_path.exists():
            return None
        try:
            recovered_project = self._serializer.load(str(autosave_path))
        except Exception:  # noqa: BLE001
            self.discard_autosave_snapshot()
            return None
        recovered_snapshot = self._project_snapshot(recovered_project)
        if recovered_snapshot.fingerprint != fingerprint:
            return None
        return recovered_project

    @staticmethod
    def coerce_timestamp(value: Any) -> float:
        return coerce_timestamp_value(value)

    @staticmethod
    def document_fingerprint(project_doc: Mapping[str, Any] | ProjectDocumentSnapshot) -> str:
        if isinstance(project_doc, ProjectDocumentSnapshot):
            return project_doc.fingerprint
        return document_fingerprint_value(dict(project_doc))
