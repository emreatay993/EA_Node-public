from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import unquote, urlparse

from ea_node_editor.common.artifact_refs import ManagedArtifactRef, StagedArtifactRef, parse_artifact_ref
from .artifact_store import ProjectArtifactStore


def _coerce_path_string(value: str | Path | None) -> str:
    if isinstance(value, Path):
        return str(value).strip()
    if value is None:
        return ""
    return str(value).strip()


def _path_from_file_url(value: str) -> Path | None:
    parsed = urlparse(value)
    if parsed.scheme.lower() != "file":
        return None
    if parsed.netloc and parsed.netloc not in {"", "localhost"}:
        raw_path = f"//{parsed.netloc}{unquote(parsed.path)}"
    else:
        raw_path = unquote(parsed.path or parsed.netloc)
    if not raw_path:
        return None
    if raw_path.startswith("/") and len(raw_path) >= 3 and raw_path[2] == ":":
        raw_path = raw_path[1:]
    if PureWindowsPath(raw_path).is_absolute():
        return Path(PureWindowsPath(raw_path))
    return Path(raw_path)


def _absolute_external_path(value: str) -> Path | None:
    path = Path(value)
    if path.is_absolute():
        return path
    windows_path = PureWindowsPath(value)
    if windows_path.is_absolute():
        return Path(windows_path)
    return None


@dataclass(frozen=True, slots=True)
class ArtifactResolution:
    source_value: str
    kind: str
    absolute_path: Path | None
    artifact_id: str | None = None

    @property
    def resolved(self) -> bool:
        return self.absolute_path is not None


class ProjectArtifactResolver:
    def __init__(
        self,
        *,
        project_path: str | Path | None,
        project_metadata: dict[str, Any] | None = None,
        artifact_store: ProjectArtifactStore | None = None,
    ) -> None:
        self._store = artifact_store or ProjectArtifactStore.from_project_metadata(
            project_path=project_path,
            project_metadata=project_metadata,
        )

    @property
    def store(self) -> ProjectArtifactStore:
        return self._store

    def resolve(self, value: str | Path | None) -> ArtifactResolution:
        text = _coerce_path_string(value)
        if not text:
            return ArtifactResolution(source_value="", kind="blank", absolute_path=None)

        parsed_ref = parse_artifact_ref(text)
        if isinstance(parsed_ref, ManagedArtifactRef):
            path = self._store.resolve_managed_path(parsed_ref.artifact_id)
            return ArtifactResolution(
                source_value=text,
                kind="managed" if path is not None else "managed_missing",
                absolute_path=path,
                artifact_id=parsed_ref.artifact_id,
            )
        if isinstance(parsed_ref, StagedArtifactRef):
            path = self._store.resolve_staged_path(parsed_ref.artifact_id)
            return ArtifactResolution(
                source_value=text,
                kind="staged" if path is not None else "staged_missing",
                absolute_path=path,
                artifact_id=parsed_ref.artifact_id,
            )

        file_url_path = _path_from_file_url(text)
        if file_url_path is not None:
            return ArtifactResolution(
                source_value=text,
                kind="external_file_url",
                absolute_path=file_url_path,
            )

        external_path = _absolute_external_path(text)
        if external_path is not None:
            return ArtifactResolution(
                source_value=text,
                kind="external_path",
                absolute_path=external_path,
            )

        return ArtifactResolution(source_value=text, kind="unresolved", absolute_path=None)

    def resolve_to_path(self, value: str | Path | None) -> Path | None:
        return self.resolve(value).absolute_path
