from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.settings import PROJECT_EXTENSION

from .migration import (
    JsonProjectMigration,
    ProjectSessionMetadata,
    ProjectUiSessionMetadata,
    ScriptEditorSessionState,
)
from .image_blobs import (
    ProjectImageStage,
    collect_project_image_garbage,
    hydrate_project_images,
    stage_project_images,
)
from .project_codec import JsonProjectCodec
from ea_node_editor.common.payload_tools import (
    document_fingerprint as document_fingerprint_value,
    encode_json_payload,
)

__all__ = [
    "JsonProjectSerializer",
    "ProjectDocumentSnapshot",
    "ProjectDocumentPublicationResult",
    "ProjectDocumentPublicationState",
    "StagedProjectDocument",
    "ProjectSessionMetadata",
    "ProjectUiSessionMetadata",
    "ScriptEditorSessionState",
]

ProjectDocumentCommitMode = Literal["replace_current", "create_new"]
ProjectDocumentPublicationState = Literal[
    "not_published",
    "published",
    "publication_uncertain",
]
_PUBLICATION_REASON_BY_STATE = {
    "not_published": "project_document_not_published",
    "published": "project_document_published",
    "publication_uncertain": "project_document_publication_uncertain",
}


@dataclass(frozen=True, slots=True)
class ProjectDocumentSnapshot:
    document: dict[str, Any]
    fingerprint: str
    encoded_payload: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "ProjectDocumentSnapshot":
        document = copy.deepcopy(dict(payload)) if isinstance(payload, Mapping) else {}
        encoded_payload = encode_json_payload(document)
        return cls(
            document=document,
            fingerprint=document_fingerprint_value(document, encoded_payload=encoded_payload),
            encoded_payload=encoded_payload,
        )

    @classmethod
    def from_owned_document(cls, document: dict[str, Any] | None) -> "ProjectDocumentSnapshot":
        owned_document = document if isinstance(document, dict) else {}
        encoded_payload = encode_json_payload(owned_document)
        return cls(
            document=owned_document,
            fingerprint=document_fingerprint_value(owned_document, encoded_payload=encoded_payload),
            encoded_payload=encoded_payload,
        )


@dataclass(frozen=True, slots=True)
class StagedProjectDocument:
    target_path: Path
    temporary_path: Path
    canonical_bytes: bytes
    canonical_sha256: str
    commit_mode: ProjectDocumentCommitMode
    prepared_document: dict[str, Any]
    image_stage: ProjectImageStage


@dataclass(frozen=True, slots=True)
class ProjectDocumentPublicationResult:
    state: ProjectDocumentPublicationState
    reason_code: str

    def __post_init__(self) -> None:
        expected = _PUBLICATION_REASON_BY_STATE.get(self.state)
        if expected is None or self.reason_code != expected:
            raise ValueError("project document publication state/reason is invalid")

    @property
    def committed(self) -> bool:
        return self.state != "not_published"


@dataclass(frozen=True, slots=True)
class _PublicationTargetFact:
    identity: tuple[int, int, int, int, int, int]
    raw_bytes: bytes


def _is_link_or_reparse(file_stat: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(file_stat.st_mode) or bool(
        getattr(file_stat, "st_file_attributes", 0) & reparse_flag
    )


def _publication_target_fact(path: Path) -> _PublicationTargetFact | None:
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        return None
    if _is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode):
        raise OSError("project publication target is unsafe")
    raw = path.read_bytes()
    after = os.lstat(path)
    before_identity = (
        int(before.st_dev),
        int(before.st_ino),
        int(before.st_mode),
        int(before.st_size),
        int(before.st_mtime_ns),
        int(getattr(before, "st_file_attributes", 0)),
    )
    after_identity = (
        int(after.st_dev),
        int(after.st_ino),
        int(after.st_mode),
        int(after.st_size),
        int(after.st_mtime_ns),
        int(getattr(after, "st_file_attributes", 0)),
    )
    if before_identity != after_identity or len(raw) != before.st_size:
        raise OSError("project publication target changed during inspection")
    return _PublicationTargetFact(before_identity, raw)


def _publication_result(
    state: ProjectDocumentPublicationState,
) -> ProjectDocumentPublicationResult:
    return ProjectDocumentPublicationResult(state, _PUBLICATION_REASON_BY_STATE[state])


class JsonProjectSerializer:
    def __init__(self, registry: NodeRegistry) -> None:
        self._registry = registry
        self._migration = JsonProjectMigration(self._registry)
        self._codec = JsonProjectCodec(self._registry)

    def load(self, path: str) -> ProjectData:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        payload = hydrate_project_images(payload, project_path=path, catalog=self._registry.data_types)
        return self.from_document(payload)

    def save(self, path: str, project: ProjectData) -> None:
        self.save_document(path, self.to_persistent_document(project))

    def save_document(self, path: str, document: Mapping[str, Any]) -> None:
        target = Path(path)
        if target.suffix.lower() != PROJECT_EXTENSION:
            target = target.with_suffix(PROJECT_EXTENSION)
        target.parent.mkdir(parents=True, exist_ok=True)
        staged = self.stage_document(
            target,
            document,
            "replace_current" if target.exists() else "create_new",
        )
        try:
            publication = self.commit_staged_document(staged)
            if not publication.committed:
                raise OSError("project document was not published")
            self.verify_committed_document(staged)
        finally:
            self.discard_staged_document(staged)
        try:
            collect_project_image_garbage(
                project_path=target,
                candidate_digests=staged.image_stage.cleanup_candidates,
                protected_digests=staged.image_stage.retained_digests,
            )
        except Exception:  # noqa: BLE001 - pruning is post-commit and best effort.
            pass

    def stage_document(
        self,
        path: str | Path,
        document: Mapping[str, Any],
        commit_mode: ProjectDocumentCommitMode,
    ) -> StagedProjectDocument:
        if commit_mode not in {"replace_current", "create_new"}:
            raise ValueError("project document commit mode is invalid")
        self._codec.validate_persistent_document(document)
        target = Path(path)
        if target.suffix.lower() != PROJECT_EXTENSION:
            target = target.with_suffix(PROJECT_EXTENSION)
        if not target.parent.is_dir():
            raise ValueError("project destination parent must already exist")
        previous_document: Mapping[str, Any] | None = None
        if target.is_file():
            try:
                loaded = json.loads(target.read_text(encoding="utf-8"))
                previous_document = loaded if isinstance(loaded, Mapping) else None
            except (OSError, TypeError, ValueError):
                previous_document = None
        image_stage = stage_project_images(
            document,
            project_path=target,
            catalog=self._registry.data_types,
            previous_document=previous_document,
        )
        canonical_bytes = encode_json_payload(image_stage.document).replace(
            "\n", os.linesep
        ).encode("utf-8")
        canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
        fd, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        temporary_path = Path(temporary)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(canonical_bytes)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return StagedProjectDocument(
            target_path=target,
            temporary_path=temporary_path,
            canonical_bytes=canonical_bytes,
            canonical_sha256=canonical_sha256,
            commit_mode=commit_mode,
            prepared_document=image_stage.document,
            image_stage=image_stage,
        )

    @staticmethod
    def commit_staged_document(
        stage: StagedProjectDocument,
    ) -> ProjectDocumentPublicationResult:
        if not isinstance(stage, StagedProjectDocument):
            raise TypeError("stage must be StagedProjectDocument")
        try:
            temporary = stage.temporary_path.read_bytes()
            if (
                temporary != stage.canonical_bytes
                or hashlib.sha256(temporary).hexdigest() != stage.canonical_sha256
            ):
                return _publication_result("not_published")
            before = _publication_target_fact(stage.target_path)
            if stage.commit_mode == "replace_current" and before is None:
                return _publication_result("not_published")
            if stage.commit_mode == "create_new" and before is not None:
                return _publication_result("not_published")
        except (OSError, TypeError, ValueError):
            return _publication_result("not_published")

        try:
            if stage.commit_mode == "replace_current":
                os.replace(stage.temporary_path, stage.target_path)
            else:
                os.link(stage.temporary_path, stage.target_path)
        except Exception:  # noqa: BLE001 - classify the atomic attempt.
            try:
                after = _publication_target_fact(stage.target_path)
            except Exception:  # noqa: BLE001 - unreadable means publication uncertain.
                return _publication_result("publication_uncertain")
            if after is not None and after.raw_bytes == stage.canonical_bytes:
                return _publication_result("published")
            if stage.commit_mode == "create_new" and after is None:
                return _publication_result("not_published")
            if stage.commit_mode == "replace_current" and after == before:
                return _publication_result("not_published")
            if after is not None and (
                before is None
                or after.identity != before.identity
                or after.raw_bytes != before.raw_bytes
            ):
                return _publication_result("published")
            return _publication_result("publication_uncertain")
        return _publication_result("published")

    @staticmethod
    def verify_committed_document(stage: StagedProjectDocument) -> None:
        if not isinstance(stage, StagedProjectDocument):
            raise TypeError("stage must be StagedProjectDocument")
        fact = _publication_target_fact(stage.target_path)
        if (
            fact is None
            or fact.raw_bytes != stage.canonical_bytes
            or hashlib.sha256(fact.raw_bytes).hexdigest()
            != stage.canonical_sha256
        ):
            raise OSError("committed project document verification failed")

    @staticmethod
    def discard_staged_document(stage: StagedProjectDocument) -> None:
        if not isinstance(stage, StagedProjectDocument):
            raise TypeError("stage must be StagedProjectDocument")
        stage.temporary_path.unlink(missing_ok=True)

    def to_document(self, project: ProjectData) -> dict[str, Any]:
        return self._codec.to_document(project)

    def document_snapshot(self, project: ProjectData) -> ProjectDocumentSnapshot:
        return self.snapshot_from_owned_document(self.to_document(project))

    @staticmethod
    def snapshot_from_mapping(payload: Mapping[str, Any] | None) -> ProjectDocumentSnapshot:
        return ProjectDocumentSnapshot.from_mapping(payload)

    @staticmethod
    def snapshot_from_owned_document(document: dict[str, Any] | None) -> ProjectDocumentSnapshot:
        return ProjectDocumentSnapshot.from_owned_document(document)

    def to_persistent_document(self, project: ProjectData) -> dict[str, Any]:
        return self._codec.to_persistent_document(project)

    def from_document(self, payload: dict[str, Any]) -> ProjectData:
        migrated = self.migrate(payload)
        project = self.from_migrated_document(migrated)
        project.migration_report = self._migration.last_report
        project.migration_source_schema_version = self._migration.source_schema_version
        if project.migration_report:
            for workspace in project.workspaces.values():
                workspace.dirty = True
        return project

    def from_migrated_document(self, payload: dict[str, Any]) -> ProjectData:
        return self._codec.from_document(payload)

    @property
    def last_load_phase_timings_ms(self) -> dict[str, float]:
        return dict(self._codec.last_load_phase_timings_ms)

    def migrate(self, raw_doc: dict[str, Any]) -> dict[str, Any]:
        return self._migration.migrate(raw_doc)
