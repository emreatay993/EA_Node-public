# Purpose: Project-solution save, candidate, adoption, GC contracts and token calculation.
# Map: subsystems/execution.md
# Tests: tests/test_project_solution.py, tests/test_solution_repository.py
# Landmarks: ProjectSolutionSaveSnapshot; project_solution_snapshot_token; ProjectSolutionSaveResult
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ea_node_editor.execution.solution_backend import (
    _HEX_32_PATTERN,
    _SHA256_PATTERN,
    sanitize_durable_diagnostic,
)
from ea_node_editor.runtime_contracts.solution_records import (
    SolutionRecord,
    SolutionResidency,
)

_PROJECT_SOLUTION_SAVE_REASONS = frozenset(
    {
        "project_solution_save_staged",
        "project_solution_save_snapshot_stale",
        "project_solution_save_source_invalid",
        "project_solution_save_destination_invalid",
        "project_solution_save_artifact_invalid",
        "project_solution_save_capacity_exceeded",
        "project_solution_save_generation_invalid",
        "project_solution_save_io_error",
    }
)


_PROJECT_SOLUTION_ADOPTION_REASONS = frozenset(
    {
        "project_solution_adopted",
        "project_solution_adoption_snapshot_stale",
        "project_solution_adoption_namespace_mismatch",
        "project_solution_adoption_candidate_invalid",
        "project_solution_adoption_io_error",
    }
)


_PROJECT_SOLUTION_CANDIDATE_REASONS = frozenset(
    {
        "project_solution_candidate_prepared",
        "project_solution_candidate_snapshot_stale",
        "project_solution_candidate_invalid",
        "project_solution_candidate_io_error",
    }
)


_PROJECT_SOLUTION_GC_REASONS = frozenset(
    {
        "project_solution_gc_completed",
        "project_solution_gc_partial",
        "project_solution_gc_skipped_invalid",
        "project_solution_gc_io_error",
    }
)


MAX_PROJECT_SOLUTION_RETAINED_OWNERS = 100_000


MAX_PROJECT_SOLUTION_SUPPLEMENTAL_RECORDS = 16_384


MAX_PROJECT_SOLUTION_ORPHAN_SCAN_ENTRIES = 100_000


MAX_PROJECT_SOLUTION_ORPHAN_CANDIDATES = 10_000


MAX_PROJECT_SOLUTION_RECORD_PAYLOAD_BYTES = 67_108_864


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ProjectSolutionSaveRecordExport:
    record: SolutionRecord
    canonical_payload: bytes
    maximum_reuse_scope: str
    is_current: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.record, SolutionRecord)
            or not self.record.reuse_eligible
        ):
            raise ValueError("project solution export requires a reusable record")
        if type(self.canonical_payload) is not bytes:
            raise TypeError("project solution export payload must be bytes")
        if (
            len(self.canonical_payload) > MAX_PROJECT_SOLUTION_RECORD_PAYLOAD_BYTES
            or hashlib.sha256(self.canonical_payload).hexdigest()
            != self.record.result_digest
        ):
            raise ValueError("project solution export payload is invalid")
        if self.maximum_reuse_scope != "durable":
            raise ValueError("project solution export maximum scope must be durable")
        if type(self.is_current) is not bool:
            raise TypeError("project solution export current flag must be boolean")
        if self.record.residency is SolutionResidency.SESSION and not self.is_current:
            raise ValueError("session project solution export must be current")


def _project_solution_logical_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be normalized")
    if len(value.encode("utf-8")) > 4_096 or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        raise ValueError(f"{field_name} is invalid")
    return value


def _project_solution_source_path(value: object) -> str:
    if value == "":
        return ""
    if not isinstance(value, str) or not value:
        raise ValueError("source project path is invalid")
    normalized = os.path.normcase(os.path.abspath(value))
    if value != normalized:
        raise ValueError("source project path must be normalized absolute")
    return value


def _project_solution_owner_ids(
    values: Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError("retained owner IDs must be an iterable")
    normalized: list[tuple[str, str]] = []
    for item in values:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("retained owner IDs must be workspace/node pairs")
        workspace_id, node_id = item
        _project_solution_logical_id(workspace_id, "workspace_id")
        _project_solution_logical_id(node_id, "node_id")
        normalized.append((workspace_id, node_id))
    result = tuple(sorted(set(normalized)))
    if len(result) > MAX_PROJECT_SOLUTION_RETAINED_OWNERS:
        raise ValueError("retained owner ID capacity exceeded")
    return result


def _project_solution_relative_paths(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError("project solution paths must be an iterable")
    normalized: list[str] = []
    for value in values:
        if (
            not isinstance(value, str)
            or not value
            or "\\" in value
            or value.startswith("/")
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ValueError("project solution path is invalid")
        normalized.append(value)
        if len(normalized) > MAX_PROJECT_SOLUTION_ORPHAN_CANDIDATES:
            raise ValueError("project solution path capacity exceeded")
    return tuple(sorted(set(normalized)))


@dataclass(frozen=True, slots=True)
class ProjectSolutionSaveSnapshot:
    project_id: str
    source_project_path: str
    solution_namespace_id: str
    binding_revision: int
    registry_contract_fingerprint: str
    source_artifact_context_digest: str
    snapshot_token: str
    source_generation_id: str
    source_manifest_set_digest: str
    retained_owner_ids: tuple[tuple[str, str], ...]
    supplemental_records: tuple[ProjectSolutionSaveRecordExport, ...]
    required_managed_artifact_ids: tuple[str, ...]
    estimated_copy_bytes: int

    @classmethod
    def create(cls, **values: Any) -> "ProjectSolutionSaveSnapshot":
        payload = dict(values)
        payload["snapshot_token"] = "0" * 64
        provisional = cls(**payload, _skip_token_check=True)
        payload["snapshot_token"] = project_solution_snapshot_token(provisional)
        return cls(**payload)

    def __init__(
        self,
        project_id: str,
        source_project_path: str,
        solution_namespace_id: str,
        binding_revision: int,
        registry_contract_fingerprint: str,
        source_artifact_context_digest: str,
        snapshot_token: str,
        source_generation_id: str,
        source_manifest_set_digest: str,
        retained_owner_ids: tuple[tuple[str, str], ...],
        supplemental_records: tuple[ProjectSolutionSaveRecordExport, ...],
        required_managed_artifact_ids: tuple[str, ...],
        estimated_copy_bytes: int,
        *,
        _skip_token_check: bool = False,
    ) -> None:
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "source_project_path", source_project_path)
        object.__setattr__(self, "solution_namespace_id", solution_namespace_id)
        object.__setattr__(self, "binding_revision", binding_revision)
        object.__setattr__(
            self, "registry_contract_fingerprint", registry_contract_fingerprint
        )
        object.__setattr__(
            self, "source_artifact_context_digest", source_artifact_context_digest
        )
        object.__setattr__(self, "snapshot_token", snapshot_token)
        object.__setattr__(self, "source_generation_id", source_generation_id)
        object.__setattr__(
            self, "source_manifest_set_digest", source_manifest_set_digest
        )
        object.__setattr__(self, "retained_owner_ids", retained_owner_ids)
        object.__setattr__(self, "supplemental_records", supplemental_records)
        object.__setattr__(
            self, "required_managed_artifact_ids", required_managed_artifact_ids
        )
        object.__setattr__(self, "estimated_copy_bytes", estimated_copy_bytes)
        self._validate(skip_token_check=_skip_token_check)

    def _validate(self, *, skip_token_check: bool) -> None:
        _project_solution_logical_id(self.project_id, "project_id")
        _project_solution_logical_id(
            self.solution_namespace_id,
            "solution_namespace_id",
        )
        _project_solution_source_path(self.source_project_path)
        if type(self.binding_revision) is not int or self.binding_revision < 0:
            raise ValueError("project solution binding revision is invalid")
        if (
            _SHA256_PATTERN.fullmatch(self.registry_contract_fingerprint or "") is None
            or _SHA256_PATTERN.fullmatch(self.source_artifact_context_digest or "")
            is None
        ):
            raise ValueError("project solution snapshot fingerprints are invalid")
        if _SHA256_PATTERN.fullmatch(self.snapshot_token or "") is None:
            raise ValueError("project solution snapshot token is invalid")
        if bool(self.source_generation_id) != bool(self.source_manifest_set_digest):
            raise ValueError("project solution source pointer must be complete")
        if self.source_generation_id and (
            _HEX_32_PATTERN.fullmatch(self.source_generation_id) is None
            or _SHA256_PATTERN.fullmatch(self.source_manifest_set_digest) is None
        ):
            raise ValueError("project solution source pointer is invalid")
        owners = _project_solution_owner_ids(self.retained_owner_ids)
        if owners != self.retained_owner_ids:
            raise ValueError("retained owner IDs must be sorted and unique")
        if (
            not isinstance(self.supplemental_records, tuple)
            or len(self.supplemental_records)
            > MAX_PROJECT_SOLUTION_SUPPLEMENTAL_RECORDS
            or any(
                not isinstance(item, ProjectSolutionSaveRecordExport)
                for item in self.supplemental_records
            )
        ):
            raise ValueError("project solution supplemental records are invalid")
        if any(
            item.record.project_id != self.project_id
            or (item.record.workspace_id, item.record.node_id) not in set(owners)
            for item in self.supplemental_records
        ):
            raise ValueError("project solution supplemental record binding is invalid")
        record_ids = tuple(item.record.record_id for item in self.supplemental_records)
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("project solution supplemental record IDs must be unique")
        artifact_ids = tuple(sorted(set(self.required_managed_artifact_ids)))
        if (
            artifact_ids != self.required_managed_artifact_ids
            or len(artifact_ids) > MAX_PROJECT_SOLUTION_RETAINED_OWNERS
            or any(
                _project_solution_logical_id(item, "artifact_id") != item
                for item in artifact_ids
            )
        ):
            raise ValueError("project solution artifact IDs must be sorted and unique")
        if type(self.estimated_copy_bytes) is not int or self.estimated_copy_bytes < 0:
            raise ValueError("project solution copy estimate is invalid")
        if (
            not skip_token_check
            and project_solution_snapshot_token(self) != self.snapshot_token
        ):
            raise ValueError("project solution snapshot token does not match payload")


def project_solution_snapshot_token(snapshot: ProjectSolutionSaveSnapshot) -> str:
    payload = {
        "schema_version": 1,
        "tag": "corex-project-solution-save-snapshot-v1",
        "project_id": snapshot.project_id,
        "source_project_path": snapshot.source_project_path,
        "solution_namespace_id": snapshot.solution_namespace_id,
        "binding_revision": snapshot.binding_revision,
        "registry_contract_fingerprint": snapshot.registry_contract_fingerprint,
        "source_artifact_context_digest": snapshot.source_artifact_context_digest,
        "source_generation_id": snapshot.source_generation_id,
        "source_manifest_set_digest": snapshot.source_manifest_set_digest,
        "retained_owner_ids": [list(item) for item in snapshot.retained_owner_ids],
        "supplemental_records": [
            {
                "record": exported.record.to_payload(),
                "canonical_payload_size": len(exported.canonical_payload),
                "canonical_payload_sha256": hashlib.sha256(
                    exported.canonical_payload
                ).hexdigest(),
                "maximum_reuse_scope": exported.maximum_reuse_scope,
                "is_current": exported.is_current,
            }
            for exported in snapshot.supplemental_records
        ],
        "required_managed_artifact_ids": list(snapshot.required_managed_artifact_ids),
        "estimated_copy_bytes": snapshot.estimated_copy_bytes,
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class ProjectSolutionSaveResult:
    snapshot_token: str
    solution_namespace_id: str
    candidate_generation_id: str = ""
    candidate_manifest_set_digest: str = ""
    previous_generation_id: str = ""
    previous_manifest_set_digest: str = ""
    initially_protected_generations: tuple[tuple[str, str], ...] = ()
    orphan_candidate_relative_paths: tuple[str, ...] = ()
    orphan_scan_complete: bool = True
    omitted_record_count: int = 0
    estimated_copy_bytes: int = 0
    staged_new_bytes: int = 0
    reason_code: str = "project_solution_save_staged"
    diagnostic: str = ""

    def __post_init__(self) -> None:
        if _SHA256_PATTERN.fullmatch(self.snapshot_token or "") is None:
            raise ValueError("project solution result token is invalid")
        _project_solution_logical_id(
            self.solution_namespace_id,
            "solution_namespace_id",
        )
        if self.reason_code not in _PROJECT_SOLUTION_SAVE_REASONS:
            raise ValueError("project solution save reason is invalid")
        success = self.reason_code == "project_solution_save_staged"
        pointer_fields = (
            self.candidate_generation_id,
            self.candidate_manifest_set_digest,
        )
        previous_fields = (
            self.previous_generation_id,
            self.previous_manifest_set_digest,
        )
        if success:
            if (
                _HEX_32_PATTERN.fullmatch(pointer_fields[0] or "") is None
                or _SHA256_PATTERN.fullmatch(pointer_fields[1] or "") is None
                or bool(previous_fields[0]) != bool(previous_fields[1])
                or (
                    previous_fields[0]
                    and (
                        _HEX_32_PATTERN.fullmatch(previous_fields[0]) is None
                        or _SHA256_PATTERN.fullmatch(previous_fields[1]) is None
                    )
                )
                or self.diagnostic
            ):
                raise ValueError("successful project solution result is invalid")
        elif (
            any(pointer_fields)
            or any(previous_fields)
            or self.initially_protected_generations
            or self.orphan_candidate_relative_paths
            or self.omitted_record_count
            or self.estimated_copy_bytes
            or self.staged_new_bytes
            or not self.diagnostic
        ):
            raise ValueError("failed project solution result has invalid payload")
        protected = tuple(sorted(set(self.initially_protected_generations)))
        if protected != self.initially_protected_generations or any(
            _HEX_32_PATTERN.fullmatch(generation_id or "") is None
            or _SHA256_PATTERN.fullmatch(digest or "") is None
            for generation_id, digest in protected
        ):
            raise ValueError("project solution protected generations are invalid")
        if (
            success
            and (
                self.candidate_generation_id,
                self.candidate_manifest_set_digest,
            )
            not in protected
        ):
            raise ValueError("candidate generation must be protected initially")
        paths = _project_solution_relative_paths(self.orphan_candidate_relative_paths)
        if (
            paths != self.orphan_candidate_relative_paths
            or len(paths) > MAX_PROJECT_SOLUTION_ORPHAN_CANDIDATES
        ):
            raise ValueError("project solution orphan candidates are invalid")
        if type(self.orphan_scan_complete) is not bool:
            raise TypeError("project solution orphan scan flag must be boolean")
        if (
            type(self.omitted_record_count) is not int
            or self.omitted_record_count < 0
            or type(self.estimated_copy_bytes) is not int
            or self.estimated_copy_bytes < 0
            or type(self.staged_new_bytes) is not int
            or self.staged_new_bytes < 0
            or self.staged_new_bytes > self.estimated_copy_bytes
        ):
            raise ValueError("project solution result counters are invalid")
        object.__setattr__(
            self,
            "diagnostic",
            sanitize_durable_diagnostic(self.diagnostic) if self.diagnostic else "",
        )

    @property
    def metadata_solution_store(self) -> dict[str, Any]:
        if self.reason_code != "project_solution_save_staged":
            return {}
        return {
            "schema_version": 1,
            "solution_namespace_id": self.solution_namespace_id,
            "active_generation_id": self.candidate_generation_id,
            "active_manifest_set_digest": self.candidate_manifest_set_digest,
        }


@dataclass(frozen=True, slots=True)
class ProjectSolutionAdoptionResult:
    adopted: bool
    reason_code: str
    diagnostic: str = ""

    def __post_init__(self) -> None:
        if (
            type(self.adopted) is not bool
            or self.reason_code not in _PROJECT_SOLUTION_ADOPTION_REASONS
        ):
            raise ValueError("project solution adoption result is invalid")
        if self.adopted != (self.reason_code == "project_solution_adopted"):
            raise ValueError("project solution adoption status is inconsistent")
        if self.adopted and self.diagnostic:
            raise ValueError("successful project solution adoption has no diagnostic")
        if not self.adopted and not self.diagnostic:
            raise ValueError("failed project solution adoption requires a diagnostic")
        object.__setattr__(
            self,
            "diagnostic",
            sanitize_durable_diagnostic(self.diagnostic) if self.diagnostic else "",
        )


@dataclass(frozen=True, slots=True)
class ProjectSolutionCandidateResult:
    prepared: bool
    reason_code: str
    diagnostic: str = ""

    def __post_init__(self) -> None:
        if (
            type(self.prepared) is not bool
            or self.reason_code not in _PROJECT_SOLUTION_CANDIDATE_REASONS
            or self.prepared
            != (self.reason_code == "project_solution_candidate_prepared")
        ):
            raise ValueError("project solution candidate result is invalid")
        if self.prepared and self.diagnostic:
            raise ValueError("prepared project solution candidate has no diagnostic")
        if not self.prepared and not self.diagnostic:
            raise ValueError("failed project solution candidate requires diagnostic")
        object.__setattr__(
            self,
            "diagnostic",
            sanitize_durable_diagnostic(self.diagnostic) if self.diagnostic else "",
        )


@dataclass(frozen=True, slots=True)
class ProjectSolutionGcResult:
    candidate_relative_paths: tuple[str, ...]
    removed_relative_paths: tuple[str, ...]
    has_more: bool
    reason_code: str

    def __post_init__(self) -> None:
        if (
            self.reason_code not in _PROJECT_SOLUTION_GC_REASONS
            or type(self.has_more) is not bool
        ):
            raise ValueError("project solution GC result is invalid")
        candidates = _project_solution_relative_paths(self.candidate_relative_paths)
        removed = _project_solution_relative_paths(self.removed_relative_paths)
        if (
            candidates != self.candidate_relative_paths
            or removed != self.removed_relative_paths
        ):
            raise ValueError("project solution GC paths must be sorted and unique")
        if not set(removed).issubset(candidates):
            raise ValueError("project solution GC removed paths must be candidates")
        if self.reason_code == "project_solution_gc_completed" and self.has_more:
            raise ValueError("completed project solution GC cannot have more")
        if self.reason_code == "project_solution_gc_partial" and not self.has_more:
            raise ValueError("partial project solution GC must have more")
        if self.reason_code == "project_solution_gc_skipped_invalid" and removed:
            raise ValueError("skipped project solution GC cannot remove paths")
