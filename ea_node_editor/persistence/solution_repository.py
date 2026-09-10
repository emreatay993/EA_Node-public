# Purpose: Persist immutable solution records and result blobs in project sidecars.
# Map: subsystems/persistence.md
# Tests: tests/test_solution_repository.py
# Landmarks: SolutionRepositoryFactory; SolutionRepository; build_candidate_generation

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Any
import unicodedata
from uuid import uuid4

from ea_node_editor.execution.solution_backend import (
    DurableBackendOpenResult,
    DurableLookupResult,
    DurablePayloadResult,
    DurableStageResult,
)
from ea_node_editor.execution.project_solution import (
    MAX_PROJECT_SOLUTION_ORPHAN_CANDIDATES,
    MAX_PROJECT_SOLUTION_ORPHAN_SCAN_ENTRIES,
    ProjectSolutionGcResult,
    ProjectSolutionSaveRecordExport,
    ProjectSolutionSaveResult,
    ProjectSolutionSaveSnapshot,
)
from ea_node_editor.persistence.artifact_store import (
    ProjectArtifactLayout,
    ensure_owned_artifact_directory,
    validate_owned_artifact_path,
)
from ea_node_editor.runtime_contracts.data_types import DataTypeCatalog
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.runtime_contracts.solution_records import (
    MAX_DURABLE_LOGICAL_ID_UTF8_BYTES,
    SolutionPayloadLocator,
    SolutionRecord,
    SolutionResidency,
)
from ea_node_editor.runtime_contracts.durable_values import (
    durable_settled_outputs_from_payload,
    validate_durable_settled_outputs,
)
from ea_node_editor.runtime_contracts.value_refs import RuntimeArtifactRef

SCHEMA_VERSION = 1
MAX_DURABLE_JSON_DEPTH = 32
MAX_DURABLE_DIAGNOSTIC_UTF8_BYTES = 512
MAX_DURABLE_MANIFEST_SET_BYTES = 67_108_864
MAX_DURABLE_NODE_MANIFEST_BYTES = 1_048_576
MAX_DURABLE_RECORD_JSON_BYTES = 8_388_608
MAX_DURABLE_RESULT_BLOB_BYTES = 67_108_864
MAX_DURABLE_NODE_MANIFESTS_PER_GENERATION = 100_000
MAX_DURABLE_RECORDS_PER_NODE = 256
MAX_DURABLE_RECORDS_PER_GENERATION = 1_000_000
MAX_DURABLE_NODE_MANIFEST_BYTES_PER_GENERATION = 268_435_456
MAX_DURABLE_REFERENCED_BYTES_PER_GENERATION = 4_294_967_296

_HEX_32 = re.compile(r"[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_WORKSPACE_KEY_PREFIX = b"corex-solution-workspace-key-v1\0"
_NODE_KEY_PREFIX = b"corex-solution-node-key-v1\0"
_SOLUTION_ROOT = PurePosixPath("solutions", "v1")
_MANIFEST_FIELDS = frozenset(
    {"schema_version", "generation_id", "solution_namespace_id", "node_manifests"}
)
_MANIFEST_ENTRY_FIELDS = frozenset(
    {"workspace_key", "node_key", "relative_path", "node_manifest_digest"}
)
_NODE_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "solution_namespace_id",
        "workspace_id",
        "node_id",
        "workspace_key",
        "node_key",
        "records",
    }
)
_NODE_RECORD_FIELDS = frozenset({"solution_key", "record_digest"})
_RESULT_BLOB_FIELDS = frozenset(
    {"schema_version", "record_id", "solution_key", "result_digest", "settlement_status", "outputs"}
)
_METADATA_FIELDS = frozenset(
    {"schema_version", "solution_namespace_id", "active_generation_id", "active_manifest_set_digest"}
)
_GENERATION_REASONS = frozenset(
    {
        "durable_generation_built",
        "durable_generation_valid",
        "durable_generation_capacity_exceeded",
        "durable_generation_invalid",
        "durable_generation_digest_mismatch",
        "durable_generation_write_failed",
    }
)
_PRUNABLE_PATH_PATTERNS = (
    re.compile(r"generations/[0-9a-f]{32}/manifest-set\.json"),
    re.compile(
        r"generations/[0-9a-f]{32}/nodes/[0-9a-f]{64}/[0-9a-f]{64}\.json"
    ),
    re.compile(r"records/sha256/[0-9a-f]{2}/[0-9a-f]{64}\.json"),
    re.compile(r"blobs/sha256/[0-9a-f]{2}/[0-9a-f]{64}"),
)


class _RepositoryError(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class DurableGenerationResult:
    generation_id: str
    manifest_set_digest: str
    reason_code: str
    solution_namespace_id: str = ""

    def __post_init__(self) -> None:
        if self.reason_code not in _GENERATION_REASONS:
            raise ValueError("durable generation reason_code is invalid")
        succeeded = self.reason_code in {
            "durable_generation_built",
            "durable_generation_valid",
        }
        if succeeded:
            if (
                _HEX_32.fullmatch(self.generation_id or "") is None
                or _SHA256.fullmatch(self.manifest_set_digest or "") is None
            ):
                raise ValueError("successful durable generations require IDs")
            _logical_id(self.solution_namespace_id, "solution_namespace_id")
        elif self.generation_id or self.manifest_set_digest or self.solution_namespace_id:
            raise ValueError("failed durable generations cannot carry IDs")

    @property
    def metadata_solution_store(self) -> dict[str, Any]:
        if self.reason_code not in {"durable_generation_built", "durable_generation_valid"}:
            return {}
        return {
            "schema_version": SCHEMA_VERSION,
            "solution_namespace_id": self.solution_namespace_id,
            "active_generation_id": self.generation_id,
            "active_manifest_set_digest": self.manifest_set_digest,
        }


@dataclass(frozen=True, slots=True)
class _GenerationInspection:
    paths: frozenset[Path]
    manifest_set_digest: str


def workspace_path_key(workspace_id: str) -> str:
    return hashlib.sha256(
        _WORKSPACE_KEY_PREFIX + _logical_id(workspace_id, "workspace_id").encode("utf-8")
    ).hexdigest()


def node_path_key(node_id: str) -> str:
    return hashlib.sha256(
        _NODE_KEY_PREFIX + _logical_id(node_id, "node_id").encode("utf-8")
    ).hexdigest()


def _logical_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    normalized = value.strip()
    if len(normalized.encode("utf-8")) > MAX_DURABLE_LOGICAL_ID_UTF8_BYTES:
        raise ValueError(f"{field_name} exceeds the durable logical ID limit")
    if any(unicodedata.category(char) == "Cc" for char in normalized):
        raise ValueError(f"{field_name} contains control characters")
    return normalized


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _strict_json_bytes(raw: bytes, *, maximum: int) -> Mapping[str, Any]:
    if type(raw) is not bytes or len(raw) > maximum:
        raise ValueError("durable JSON exceeds its byte limit")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError("durable JSON contains duplicate keys")
            result[key] = value
        return result

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("durable JSON contains a non-finite number")
            ),
        )
        if not isinstance(payload, Mapping):
            raise ValueError("durable JSON root must be an object")
        _validate_json_depth(payload, 0)
        if _canonical_json_bytes(payload) != raw:
            raise ValueError("durable JSON bytes are not canonical")
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        OverflowError,
        RecursionError,
        TypeError,
    ) as exc:
        raise ValueError("durable JSON is invalid") from exc
    return payload


def _validate_json_depth(value: Any, depth: int) -> None:
    if depth > MAX_DURABLE_JSON_DEPTH:
        raise ValueError("durable JSON exceeds the depth limit")
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("durable JSON object keys must be strings")
            _validate_json_depth(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _validate_json_depth(item, depth + 1)
    elif value is not None and type(value) not in {str, bool, int, float}:
        raise ValueError("durable JSON contains an unsupported value")


def _exact_fields(payload: Mapping[str, Any], fields: frozenset[str]) -> None:
    if set(payload) != fields:
        raise ValueError("durable JSON fields are invalid")


def _identity(file_stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(file_stat.st_dev),
        int(file_stat.st_ino),
        int(file_stat.st_size),
        int(file_stat.st_mtime_ns),
        int(getattr(file_stat, "st_file_attributes", 0)),
    )


def _is_link_or_reparse(file_stat: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(file_stat.st_mode) or bool(
        getattr(file_stat, "st_file_attributes", 0) & reparse_flag
    )


def _contains_reparse_component(root: Path, relative_path: str) -> bool:
    target = Path(os.path.abspath(os.path.join(root, *PurePosixPath(relative_path).parts)))
    current = Path(target.anchor)
    for part in target.parts[1:]:
        current /= part
        try:
            current_stat = os.lstat(current)
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(current_stat.st_mode) or bool(
            getattr(current_stat, "st_file_attributes", 0) & 0x400
        ):
            return True
    return False


def _read_file(
    root: Path,
    relative_path: str,
    *,
    maximum: int,
    missing_reason: str,
    oversized_reason: str,
) -> bytes:
    try:
        path = validate_owned_artifact_path(root, relative_path)
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError
        if before.st_size > maximum:
            raise _RepositoryError(oversized_reason)
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if _identity(opened) != _identity(before):
                raise OSError
            raw = stream.read(maximum + 1)
            after_open = os.fstat(stream.fileno())
        after = os.lstat(path)
        validate_owned_artifact_path(root, relative_path)
        if len(raw) > maximum:
            raise _RepositoryError(oversized_reason)
        if _identity(before) != _identity(after_open) or _identity(before) != _identity(after):
            raise OSError
        return raw
    except FileNotFoundError:
        raise _RepositoryError(missing_reason) from None
    except _RepositoryError:
        raise
    except ValueError:
        reason = (
            "durable_reparse_rejected"
            if _contains_reparse_component(root, relative_path)
            else "durable_path_unsafe"
        )
        raise _RepositoryError(reason) from None
    except OSError:
        raise _RepositoryError("durable_io_error") from None


def _ensure_relative_parent(root: Path, relative_path: PurePosixPath) -> Path:
    current = root
    for part in relative_path.parent.parts:
        current = ensure_owned_artifact_directory(current / part)
    return current


def _publish_immutable(root: Path, relative_path: str, raw: bytes) -> bool:
    relative = PurePosixPath(relative_path)
    parent = _ensure_relative_parent(root, relative)
    target_relative = relative.as_posix()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        existing = _read_file(
            root,
            target_relative,
            maximum=max(len(raw), 1),
            missing_reason="missing",
            oversized_reason="oversized",
        )
    except _RepositoryError as exc:
        if exc.reason_code == "oversized":
            raise _RepositoryError("durable_nondeterminism_conflict") from None
        if exc.reason_code != "missing":
            raise
    else:
        if existing != raw or hashlib.sha256(existing).hexdigest() != digest:
            raise _RepositoryError("durable_nondeterminism_conflict")
        return False

    fd, temporary = tempfile.mkstemp(prefix=f".{relative.name}.", suffix=".tmp", dir=parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        validate_owned_artifact_path(parent, temporary_path.name)
        try:
            os.link(temporary_path, parent / relative.name)
        except FileExistsError:
            winner = _read_file(
                root,
                target_relative,
                maximum=max(len(raw), 1),
                missing_reason="durable_stage_write_failed",
                oversized_reason="durable_stage_write_failed",
            )
            if winner != raw or hashlib.sha256(winner).hexdigest() != digest:
                raise _RepositoryError("durable_nondeterminism_conflict")
            return False
        validate_owned_artifact_path(root, target_relative)
        installed = _read_file(
            root,
            target_relative,
            maximum=max(len(raw), 1),
            missing_reason="durable_stage_write_failed",
            oversized_reason="durable_stage_write_failed",
        )
        if installed != raw:
            raise _RepositoryError("durable_stage_write_failed")
        return True
    except _RepositoryError:
        raise
    except ValueError:
        reason = (
            "durable_reparse_rejected"
            if _contains_reparse_component(root, target_relative)
            else "durable_path_unsafe"
        )
        raise _RepositoryError(reason) from None
    except OSError:
        raise _RepositoryError("durable_stage_write_failed") from None
    finally:
        temporary_path.unlink(missing_ok=True)


def _result_blob_payload(record: SolutionRecord, outputs_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": record.record_id,
        "solution_key": record.solution_key,
        "result_digest": record.result_digest,
        "settlement_status": record.settlement_status,
        "outputs": dict(outputs_payload),
    }


class _TrustedStagedArtifactContext:
    """Accept structurally valid managed refs already verified by the execution gate."""

    @staticmethod
    def inspect_durable_artifact(value: object) -> str:
        if type(value) is not RuntimeArtifactRef or value.scope != "managed":
            raise ValueError("durable artifact is not managed")
        return "managed"


_TRUSTED_STAGED_ARTIFACT_CONTEXT = _TrustedStagedArtifactContext()


def _projected_supplemental_bytes(
    exports: tuple[ProjectSolutionSaveRecordExport, ...],
    *,
    solution_namespace_id: str,
    catalog: DataTypeCatalog,
) -> int:
    total = 0
    manifest_entries: list[dict[str, str]] = []
    for exported in exports:
        outputs_payload = _strict_json_bytes(
            exported.canonical_payload,
            maximum=MAX_DURABLE_RESULT_BLOB_BYTES,
        )
        record = exported.record
        if any(item.status == "value" for item in record.output_descriptors):
            blob_without_locator = _canonical_json_bytes(
                _result_blob_payload(record, outputs_payload)
            )
            blob_digest = hashlib.sha256(blob_without_locator).hexdigest()
            durable_record = replace(
                record,
                residency=SolutionResidency.DURABLE,
                runtime_generation=None,
                payload_locator=SolutionPayloadLocator(
                    kind=SolutionResidency.DURABLE,
                    reference_id=blob_digest,
                    blob_digests=(blob_digest,),
                ),
                reuse_eligible=True,
                catalog=catalog,
            )
            blob_raw = _canonical_json_bytes(
                _result_blob_payload(durable_record, outputs_payload)
            )
            total += len(blob_raw)
        else:
            durable_record = replace(
                record,
                residency=SolutionResidency.DURABLE,
                runtime_generation=None,
                payload_locator=None,
                reuse_eligible=True,
                catalog=catalog,
            )
        record_raw = _canonical_json_bytes(
            durable_record.to_payload(catalog=catalog)
        )
        record_digest = hashlib.sha256(record_raw).hexdigest()
        total += len(record_raw)
        workspace_key = workspace_path_key(record.workspace_id)
        node_key = node_path_key(record.node_id)
        node_raw = _canonical_json_bytes(
            {
                "schema_version": SCHEMA_VERSION,
                "solution_namespace_id": solution_namespace_id,
                "workspace_id": record.workspace_id,
                "node_id": record.node_id,
                "workspace_key": workspace_key,
                "node_key": node_key,
                "records": [
                    {
                        "solution_key": record.solution_key,
                        "record_digest": record_digest,
                    }
                ],
            }
        )
        total += len(node_raw)
        manifest_entries.append(
            {
                "workspace_key": workspace_key,
                "node_key": node_key,
                "relative_path": f"nodes/{workspace_key}/{node_key}.json",
                "node_manifest_digest": hashlib.sha256(node_raw).hexdigest(),
            }
        )
    manifest_raw = _canonical_json_bytes(
        {
            "schema_version": SCHEMA_VERSION,
            "generation_id": "0" * 32,
            "solution_namespace_id": solution_namespace_id,
            "node_manifests": sorted(
                manifest_entries,
                key=lambda item: (item["workspace_key"], item["node_key"]),
            ),
        }
    )
    return total + len(manifest_raw)


class SolutionRepositoryFactory:
    def open_backend(
        self,
        project_id: str,
        project_path: str,
        metadata_solution_store: object,
        catalog: DataTypeCatalog,
    ) -> DurableBackendOpenResult:
        normalized_project_id = _logical_id(project_id, "project_id")
        fallback_namespace = normalized_project_id
        if not str(project_path).strip():
            return DurableBackendOpenResult(
                None,
                fallback_namespace,
                "durable_session_only_metadata_absent",
                "Unsaved projects use session-only solution reuse.",
            )
        if metadata_solution_store is None:
            return DurableBackendOpenResult(
                None,
                fallback_namespace,
                "durable_session_only_metadata_absent",
                "No durable solution pointer is committed; results will be recomputed.",
            )
        try:
            metadata = self._metadata(metadata_solution_store)
        except _RepositoryError as exc:
            return DurableBackendOpenResult(
                None,
                fallback_namespace,
                exc.reason_code,
                "The durable solution pointer is invalid; results will be recomputed.",
            )
        namespace_id = metadata["solution_namespace_id"]
        try:
            repository = SolutionRepository(
                project_id=normalized_project_id,
                project_path=project_path,
                solution_namespace_id=namespace_id,
                active_generation_id=metadata["active_generation_id"],
                active_manifest_set_digest=metadata["active_manifest_set_digest"],
                catalog=catalog,
            )
        except _RepositoryError as exc:
            status_code = {
                "durable_path_unsafe": "durable_session_only_path_unsafe",
                "durable_reparse_rejected": "durable_session_only_reparse_rejected",
                "durable_io_error": "durable_session_only_io_error",
            }.get(exc.reason_code, exc.reason_code)
            return DurableBackendOpenResult(
                None,
                namespace_id,
                status_code,
                "Durable solution data is unavailable; results will be recomputed.",
            )
        except (OverflowError, RecursionError, TypeError, ValueError):
            return DurableBackendOpenResult(
                None,
                namespace_id,
                "durable_session_only_manifest_invalid",
                "Durable solution data is unavailable; results will be recomputed.",
            )
        return DurableBackendOpenResult(
            repository,
            namespace_id,
            "durable_bound_active",
            active_generation_id=metadata["active_generation_id"],
            active_manifest_set_digest=metadata["active_manifest_set_digest"],
        )

    @staticmethod
    def _metadata(value: object) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != _METADATA_FIELDS:
            raise _RepositoryError("durable_session_only_metadata_invalid")
        schema = value.get("schema_version")
        if type(schema) is not int:
            raise _RepositoryError("durable_session_only_metadata_invalid")
        if schema != SCHEMA_VERSION:
            raise _RepositoryError("durable_session_only_schema_unsupported")
        try:
            namespace_id = _logical_id(value.get("solution_namespace_id"), "solution_namespace_id")
        except ValueError:
            raise _RepositoryError("durable_session_only_metadata_invalid") from None
        generation_id = value.get("active_generation_id")
        digest = value.get("active_manifest_set_digest")
        if not isinstance(generation_id, str) or _HEX_32.fullmatch(generation_id) is None:
            raise _RepositoryError("durable_session_only_pointer_invalid")
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise _RepositoryError("durable_session_only_pointer_invalid")
        return {
            "schema_version": SCHEMA_VERSION,
            "solution_namespace_id": namespace_id,
            "active_generation_id": generation_id,
            "active_manifest_set_digest": digest,
        }

    def export_project_solution_save(
        self,
        project_id: str,
        source_project_path: str,
        solution_namespace_id: str,
        source_generation_id: str,
        source_manifest_set_digest: str,
        retained_owner_ids: tuple[tuple[str, str], ...],
        supplemental_records: tuple[ProjectSolutionSaveRecordExport, ...],
        binding_revision: int,
        registry_contract_fingerprint: str,
        source_artifact_context_digest: str,
        catalog: DataTypeCatalog,
        source_artifact_context: object,
    ) -> ProjectSolutionSaveSnapshot:
        required_artifact_ids: set[str] = set()
        estimated_copy_bytes = _projected_supplemental_bytes(
            supplemental_records,
            solution_namespace_id=solution_namespace_id,
            catalog=catalog,
        )
        for exported in supplemental_records:
            required_artifact_ids.update(
                _managed_artifact_ids_from_payload(exported.canonical_payload)
            )
        if source_generation_id and source_manifest_set_digest and source_project_path:
            try:
                repository = SolutionRepository(
                    project_id=project_id,
                    project_path=source_project_path,
                    solution_namespace_id=solution_namespace_id,
                    active_generation_id=source_generation_id,
                    active_manifest_set_digest=source_manifest_set_digest,
                    catalog=catalog,
                )
                active_exports = repository.generation_record_exports(
                    artifact_context=source_artifact_context,
                )
                estimated_copy_bytes += repository.generation_storage_bytes()
            except Exception:  # noqa: BLE001 - corrupt cache is omitted from save.
                active_exports = ()
            else:
                for exported in active_exports:
                    required_artifact_ids.update(
                        _managed_artifact_ids_from_payload(exported.canonical_payload)
                    )
                repository.close()
        return ProjectSolutionSaveSnapshot.create(
            project_id=_logical_id(project_id, "project_id"),
            source_project_path=source_project_path,
            solution_namespace_id=_logical_id(
                solution_namespace_id,
                "solution_namespace_id",
            ),
            binding_revision=binding_revision,
            registry_contract_fingerprint=registry_contract_fingerprint,
            source_artifact_context_digest=source_artifact_context_digest,
            source_generation_id=source_generation_id,
            source_manifest_set_digest=source_manifest_set_digest,
            retained_owner_ids=retained_owner_ids,
            supplemental_records=supplemental_records,
            required_managed_artifact_ids=tuple(sorted(required_artifact_ids)),
            estimated_copy_bytes=estimated_copy_bytes,
        )

    def stage_project_solution_save(
        self,
        snapshot: ProjectSolutionSaveSnapshot,
        destination_project_path: str,
        catalog: DataTypeCatalog,
        destination_artifact_context: object,
    ) -> ProjectSolutionSaveResult:
        if not isinstance(snapshot, ProjectSolutionSaveSnapshot):
            raise TypeError("snapshot must be ProjectSolutionSaveSnapshot")

        def failed(reason_code: str, diagnostic: str) -> ProjectSolutionSaveResult:
            return ProjectSolutionSaveResult(
                snapshot_token=snapshot.snapshot_token,
                solution_namespace_id=snapshot.solution_namespace_id,
                reason_code=reason_code,
                diagnostic=diagnostic,
            )

        try:
            destination = Path(destination_project_path)
            if not destination.is_absolute() or not destination.parent.is_dir():
                return failed(
                    "project_solution_save_destination_invalid",
                    "The destination project path is invalid.",
                )
            active_exports: tuple[ProjectSolutionSaveRecordExport, ...] = ()
            previous_generation_id = ""
            previous_manifest_set_digest = ""
            source_generation_valid = not snapshot.source_generation_id
            if snapshot.source_generation_id:
                try:
                    source_repository = SolutionRepository(
                        project_id=snapshot.project_id,
                        project_path=snapshot.source_project_path,
                        solution_namespace_id=snapshot.solution_namespace_id,
                        active_generation_id=snapshot.source_generation_id,
                        active_manifest_set_digest=snapshot.source_manifest_set_digest,
                        catalog=catalog,
                    )
                    active_exports = source_repository.generation_record_exports(
                        artifact_context=None,
                    )
                    source_repository.close()
                    source_generation_valid = True
                    previous_generation_id = snapshot.source_generation_id
                    previous_manifest_set_digest = snapshot.source_manifest_set_digest
                except Exception:  # noqa: BLE001 - the active cache is discarded whole.
                    active_exports = ()
                    source_generation_valid = False

            retained = set(snapshot.retained_owner_ids)
            by_key: dict[
                tuple[str, str, str], ProjectSolutionSaveRecordExport
            ] = {}
            conflicts: set[tuple[str, str, str]] = set()
            omitted = 0
            ordered_exports = sorted(
                (*active_exports, *snapshot.supplemental_records),
                key=lambda item: (
                    not item.is_current,
                    -item.record.created_at_epoch_ms,
                    item.record.record_id,
                ),
            )
            for exported in ordered_exports:
                record = exported.record
                key = (record.workspace_id, record.node_id, record.solution_key)
                if (record.workspace_id, record.node_id) not in retained:
                    omitted += 1
                    continue
                if key in conflicts:
                    omitted += 1
                    continue
                existing = by_key.get(key)
                if existing is None:
                    by_key[key] = exported
                    continue
                if existing.record.result_digest != record.result_digest:
                    by_key.pop(key, None)
                    conflicts.add(key)
                    omitted += 2

            selected: list[ProjectSolutionSaveRecordExport] = []
            per_owner: dict[tuple[str, str], int] = {}
            referenced_bytes = 0
            for exported in sorted(
                by_key.values(),
                key=lambda item: (
                    not item.is_current,
                    -item.record.created_at_epoch_ms,
                    item.record.record_id,
                ),
            ):
                owner = (exported.record.workspace_id, exported.record.node_id)
                if (
                    per_owner.get(owner, 0) >= MAX_DURABLE_RECORDS_PER_NODE
                    or len(selected) >= MAX_DURABLE_RECORDS_PER_GENERATION
                    or referenced_bytes + len(exported.canonical_payload)
                    > MAX_DURABLE_REFERENCED_BYTES_PER_GENERATION
                ):
                    omitted += 1
                    continue
                selected.append(exported)
                per_owner[owner] = per_owner.get(owner, 0) + 1
                referenced_bytes += len(exported.canonical_payload)

            repository = SolutionRepository.create_empty(
                project_id=snapshot.project_id,
                project_path=destination,
                solution_namespace_id=snapshot.solution_namespace_id,
                catalog=catalog,
            )
            staged_records: list[SolutionRecord] = []
            for exported in selected:
                try:
                    payload = _strict_json_bytes(
                        exported.canonical_payload,
                        maximum=MAX_DURABLE_RESULT_BLOB_BYTES,
                    )
                    outputs = durable_settled_outputs_from_payload(payload)
                    validation = validate_durable_settled_outputs(
                        outputs,
                        exported.record.output_descriptors,
                        catalog,
                        destination_artifact_context,
                    )
                except Exception:  # noqa: BLE001 - one invalid record is omitted.
                    validation = None
                if (
                    validation is None
                    or not validation.eligible
                    or validation.canonical_payload is None
                    or validation.canonical_payload != exported.canonical_payload
                ):
                    omitted += 1
                    continue
                staged = repository.stage_record(
                    exported.record,
                    exported.canonical_payload,
                    catalog,
                )
                if staged.record is None:
                    omitted += 1
                    continue
                staged_records.append(staged.record)
            generation = repository.build_candidate_generation(staged_records)
            if generation.reason_code == "durable_generation_capacity_exceeded":
                repository.close()
                return failed(
                    "project_solution_save_capacity_exceeded",
                    "The project solution snapshot exceeds the destination capacity.",
                )
            if generation.reason_code != "durable_generation_built":
                repository.close()
                return failed(
                    "project_solution_save_generation_invalid",
                    "The project solution generation could not be validated.",
                )
            staged_new_bytes = repository.published_bytes
            if staged_new_bytes > snapshot.estimated_copy_bytes:
                repository.close()
                return failed(
                    "project_solution_save_capacity_exceeded",
                    "The project solution generation exceeded its byte estimate.",
                )
            orphan_candidates, scan_complete = repository.enumerate_orphan_candidates()
            if not source_generation_valid:
                orphan_candidates = ()
            protected = tuple(
                sorted(
                    {
                        *(
                            ((previous_generation_id, previous_manifest_set_digest),)
                            if previous_generation_id
                            else ()
                        ),
                        (generation.generation_id, generation.manifest_set_digest),
                    }
                )
            )
            repository.close()
            return ProjectSolutionSaveResult(
                snapshot_token=snapshot.snapshot_token,
                solution_namespace_id=snapshot.solution_namespace_id,
                candidate_generation_id=generation.generation_id,
                candidate_manifest_set_digest=generation.manifest_set_digest,
                previous_generation_id=previous_generation_id,
                previous_manifest_set_digest=previous_manifest_set_digest,
                initially_protected_generations=protected,
                orphan_candidate_relative_paths=orphan_candidates,
                orphan_scan_complete=scan_complete and source_generation_valid,
                omitted_record_count=omitted,
                estimated_copy_bytes=snapshot.estimated_copy_bytes,
                staged_new_bytes=staged_new_bytes,
                reason_code="project_solution_save_staged",
            )
        except (OSError, OverflowError, RecursionError, TypeError, ValueError):
            return failed(
                "project_solution_save_io_error",
                "The project solution snapshot could not be staged.",
            )

    def open_project_solution_save_candidate(
        self,
        project_id: str,
        destination_project_path: str,
        metadata_solution_store: object,
        expected_namespace_id: str,
        catalog: DataTypeCatalog,
        destination_artifact_context: object,
    ) -> DurableBackendOpenResult:
        opened = self.open_backend(
            project_id,
            destination_project_path,
            metadata_solution_store,
            catalog,
        )
        if opened.backend is None:
            return opened
        if opened.solution_namespace_id != expected_namespace_id:
            opened.backend.close()
            return DurableBackendOpenResult(
                None,
                expected_namespace_id,
                "durable_session_only_metadata_invalid",
                "The project solution namespace does not match.",
            )
        try:
            opened.backend.generation_record_exports(
                artifact_context=destination_artifact_context,
            )
        except Exception:  # noqa: BLE001 - candidate validation fails closed.
            opened.backend.close()
            return DurableBackendOpenResult(
                None,
                expected_namespace_id,
                "durable_session_only_manifest_invalid",
                "The project solution generation could not be validated.",
            )
        return opened

    def collect_project_solution_garbage(
        self,
        project_id: str,
        project_path: str,
        active_generation_id: str,
        active_manifest_set_digest: str,
        extra_protected_generations: tuple[tuple[str, str], ...],
        candidate_relative_paths: tuple[str, ...],
        orphan_scan_complete: bool,
        limit: int,
        catalog: DataTypeCatalog,
    ) -> ProjectSolutionGcResult:
        candidates = set(candidate_relative_paths)
        bounded_limit = min(max(int(limit), 0), MAX_PROJECT_SOLUTION_ORPHAN_CANDIDATES)
        scan_complete = bool(orphan_scan_complete)
        try:
            metadata = {
                "schema_version": SCHEMA_VERSION,
                "solution_namespace_id": "placeholder",
                "active_generation_id": active_generation_id,
                "active_manifest_set_digest": active_manifest_set_digest,
            }
            solution_root = (
                ProjectArtifactLayout.from_project_path(project_path).sidecar_root
                / _SOLUTION_ROOT
            )
            manifest = _strict_json_bytes(
                _read_file(
                    solution_root,
                    f"generations/{active_generation_id}/manifest-set.json",
                    maximum=MAX_DURABLE_MANIFEST_SET_BYTES,
                    missing_reason="durable_generation_invalid",
                    oversized_reason="durable_generation_capacity_exceeded",
                ),
                maximum=MAX_DURABLE_MANIFEST_SET_BYTES,
            )
            metadata["solution_namespace_id"] = manifest["solution_namespace_id"]
            repository = SolutionRepository(
                project_id=project_id,
                project_path=project_path,
                solution_namespace_id=metadata["solution_namespace_id"],
                active_generation_id=active_generation_id,
                active_manifest_set_digest=active_manifest_set_digest,
                catalog=catalog,
            )
            if not scan_complete:
                rescanned, scan_complete = repository.enumerate_orphan_candidates()
                candidates.update(rescanned)
                if len(candidates) > MAX_PROJECT_SOLUTION_ORPHAN_CANDIDATES:
                    candidates = set(
                        sorted(candidates)[:MAX_PROJECT_SOLUTION_ORPHAN_CANDIDATES]
                    )
                    scan_complete = False
            ordered_candidates = tuple(sorted(candidates))
            selected = ordered_candidates[:bounded_limit]
            active_protected = repository.reachable_generation_pairs(
                ((active_generation_id, active_manifest_set_digest),)
            )
            extra_protected = repository.reachable_generation_pairs(
                extra_protected_generations
            ) if extra_protected_generations else frozenset()
            protected = frozenset(
                (*active_protected, *extra_protected)
            )
            removed = repository.prune_unreachable_paths(
                selected,
                reachable_paths=protected,
            )
            resolved = set(removed)
            active_relative_paths = {
                path.relative_to(repository._root).as_posix()  # noqa: SLF001
                for path in active_protected
            }
            for relative in selected:
                candidate_path = repository._root / PurePosixPath(relative)  # noqa: SLF001
                if not candidate_path.exists():
                    resolved.add(relative)
            repository.close()
        except Exception:  # noqa: BLE001 - garbage collection never changes save success.
            ordered_candidates = tuple(sorted(candidates))
            return ProjectSolutionGcResult(
                candidate_relative_paths=ordered_candidates,
                removed_relative_paths=(),
                has_more=bool(ordered_candidates) or not scan_complete,
                reason_code="project_solution_gc_io_error",
            )
        report_candidates = tuple(
            relative
            for relative in ordered_candidates
            if relative not in active_relative_paths
        )
        report_removed = tuple(
            sorted(set(resolved).intersection(report_candidates))
        )
        has_more = bool(set(report_candidates).difference(report_removed)) or not scan_complete
        return ProjectSolutionGcResult(
            candidate_relative_paths=report_candidates,
            removed_relative_paths=report_removed,
            has_more=has_more,
            reason_code=(
                "project_solution_gc_partial"
                if has_more
                else "project_solution_gc_completed"
            ),
        )


def _managed_artifact_ids_from_payload(raw: bytes) -> tuple[str, ...]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ()
    result: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            if (
                value.get("__ea_runtime_value__") == "artifact_ref"
                and value.get("scope") == "managed"
                and isinstance(value.get("artifact_id"), str)
                and value["artifact_id"].strip()
            ):
                result.add(value["artifact_id"].strip())
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)
    return tuple(sorted(result))


class SolutionRepository:
    def __init__(
        self,
        *,
        project_id: str,
        project_path: str | Path,
        solution_namespace_id: str,
        active_generation_id: str,
        active_manifest_set_digest: str,
        catalog: DataTypeCatalog,
    ) -> None:
        self.project_id = _logical_id(project_id, "project_id")
        self.solution_namespace_id = _logical_id(
            solution_namespace_id,
            "solution_namespace_id",
        )
        self._catalog = catalog
        self._layout = ProjectArtifactLayout.from_project_path(project_path)
        self._root = self._layout.sidecar_root / _SOLUTION_ROOT
        self._closed = False
        self._published_bytes = 0
        if _HEX_32.fullmatch(active_generation_id or "") is None:
            raise _RepositoryError("durable_session_only_pointer_invalid")
        if _SHA256.fullmatch(active_manifest_set_digest or "") is None:
            raise _RepositoryError("durable_session_only_pointer_invalid")
        self._active_generation_id = active_generation_id
        self._active_manifest_set_digest = active_manifest_set_digest
        self._staged_records: dict[tuple[str, str, str], SolutionRecord] = {}
        self._record_digests: dict[str, str] = {}
        raw = _read_file(
            self._root,
            f"generations/{active_generation_id}/manifest-set.json",
            maximum=MAX_DURABLE_MANIFEST_SET_BYTES,
            missing_reason="durable_session_only_manifest_missing",
            oversized_reason="durable_session_only_manifest_oversized",
        )
        if hashlib.sha256(raw).hexdigest() != active_manifest_set_digest:
            raise _RepositoryError("durable_session_only_manifest_digest_mismatch")
        try:
            manifest = self._manifest_set(raw)
        except ValueError:
            raise _RepositoryError("durable_session_only_manifest_invalid") from None
        if (
            manifest["generation_id"] != active_generation_id
            or manifest["solution_namespace_id"] != self.solution_namespace_id
        ):
            raise _RepositoryError("durable_session_only_manifest_invalid")
        self._manifest = manifest
        self._manifest_entries = {
            (entry["workspace_key"], entry["node_key"]): entry
            for entry in manifest["node_manifests"]
        }

    @classmethod
    def create_empty(
        cls,
        *,
        project_id: str,
        project_path: str | Path,
        solution_namespace_id: str,
        catalog: DataTypeCatalog,
    ) -> SolutionRepository:
        self = object.__new__(cls)
        self.project_id = _logical_id(project_id, "project_id")
        self.solution_namespace_id = _logical_id(solution_namespace_id, "solution_namespace_id")
        self._catalog = catalog
        self._layout = ProjectArtifactLayout.from_project_path(project_path)
        self._root = self._layout.sidecar_root / _SOLUTION_ROOT
        self._closed = False
        self._published_bytes = 0
        self._active_generation_id = ""
        self._active_manifest_set_digest = ""
        self._staged_records = {}
        self._record_digests = {}
        self._manifest = {
            "schema_version": SCHEMA_VERSION,
            "generation_id": "",
            "solution_namespace_id": self.solution_namespace_id,
            "node_manifests": [],
        }
        self._manifest_entries = {}
        return self

    def close(self) -> None:
        self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise _RepositoryError("durable_not_bound")

    @property
    def published_bytes(self) -> int:
        return self._published_bytes

    @staticmethod
    def _manifest_set(raw: bytes) -> dict[str, Any]:
        payload = dict(_strict_json_bytes(raw, maximum=MAX_DURABLE_MANIFEST_SET_BYTES))
        _exact_fields(payload, _MANIFEST_FIELDS)
        if type(payload["schema_version"]) is not int or payload["schema_version"] != SCHEMA_VERSION:
            raise ValueError
        if not isinstance(payload["generation_id"], str) or _HEX_32.fullmatch(payload["generation_id"]) is None:
            raise ValueError
        _logical_id(payload["solution_namespace_id"], "solution_namespace_id")
        entries = payload["node_manifests"]
        if type(entries) is not list or len(entries) > MAX_DURABLE_NODE_MANIFESTS_PER_GENERATION:
            raise ValueError
        normalized: list[dict[str, str]] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ValueError
            _exact_fields(entry, _MANIFEST_ENTRY_FIELDS)
            workspace_key = entry["workspace_key"]
            node_key = entry["node_key"]
            digest = entry["node_manifest_digest"]
            if any(not isinstance(item, str) or _SHA256.fullmatch(item) is None for item in (workspace_key, node_key, digest)):
                raise ValueError
            relative = f"nodes/{workspace_key}/{node_key}.json"
            if entry["relative_path"] != relative:
                raise ValueError
            normalized.append(dict(entry))
        if normalized != sorted(normalized, key=lambda item: (item["workspace_key"], item["node_key"])):
            raise ValueError
        if len({(item["workspace_key"], item["node_key"]) for item in normalized}) != len(normalized):
            raise ValueError
        payload["node_manifests"] = normalized
        return payload

    def _node_manifest(self, raw: bytes, workspace_id: str, node_id: str) -> dict[str, Any]:
        payload = dict(_strict_json_bytes(raw, maximum=MAX_DURABLE_NODE_MANIFEST_BYTES))
        _exact_fields(payload, _NODE_MANIFEST_FIELDS)
        if type(payload["schema_version"]) is not int or payload["schema_version"] != SCHEMA_VERSION:
            raise ValueError
        if payload["solution_namespace_id"] != self.solution_namespace_id:
            raise ValueError
        if payload["workspace_id"] != workspace_id or payload["node_id"] != node_id:
            raise ValueError
        if payload["workspace_key"] != workspace_path_key(workspace_id) or payload["node_key"] != node_path_key(node_id):
            raise ValueError
        records = payload["records"]
        if type(records) is not list or len(records) > MAX_DURABLE_RECORDS_PER_NODE:
            raise ValueError
        normalized: list[dict[str, str]] = []
        for item in records:
            if not isinstance(item, Mapping):
                raise ValueError
            _exact_fields(item, _NODE_RECORD_FIELDS)
            if any(not isinstance(item[key], str) or _SHA256.fullmatch(item[key]) is None for key in _NODE_RECORD_FIELDS):
                raise ValueError
            normalized.append(dict(item))
        if normalized != sorted(normalized, key=lambda item: item["solution_key"]):
            raise ValueError
        if len({item["solution_key"] for item in normalized}) != len(normalized):
            raise ValueError
        payload["records"] = normalized
        return payload

    def lookup_record(
        self,
        workspace_id: str,
        node_id: str,
        solution_key: str,
        catalog: DataTypeCatalog,
    ) -> DurableLookupResult:
        try:
            self._require_open()
            workspace_id = _logical_id(workspace_id, "workspace_id")
            node_id = _logical_id(node_id, "node_id")
            if not isinstance(solution_key, str) or _SHA256.fullmatch(solution_key) is None:
                raise _RepositoryError("durable_record_binding_mismatch")
            staged = self._staged_records.get((workspace_id, node_id, solution_key))
            if staged is not None:
                return DurableLookupResult(staged, "durable_hit")
            entry = self._manifest_entries.get((workspace_path_key(workspace_id), node_path_key(node_id)))
            if entry is None:
                return DurableLookupResult(None, "durable_key_absent")
            raw_manifest = _read_file(
                self._root / "generations" / self._active_generation_id,
                entry["relative_path"],
                maximum=MAX_DURABLE_NODE_MANIFEST_BYTES,
                missing_reason="durable_node_manifest_missing",
                oversized_reason="durable_node_manifest_oversized",
            )
            if hashlib.sha256(raw_manifest).hexdigest() != entry["node_manifest_digest"]:
                return DurableLookupResult(None, "durable_node_manifest_digest_mismatch")
            try:
                node_manifest = self._node_manifest(raw_manifest, workspace_id, node_id)
            except (OverflowError, RecursionError, ValueError):
                return DurableLookupResult(None, "durable_node_manifest_invalid")
            record_ref = next((item for item in node_manifest["records"] if item["solution_key"] == solution_key), None)
            if record_ref is None:
                return DurableLookupResult(None, "durable_key_absent")
            record_digest = record_ref["record_digest"]
            raw_record = _read_file(
                self._root,
                f"records/sha256/{record_digest[:2]}/{record_digest}.json",
                maximum=MAX_DURABLE_RECORD_JSON_BYTES,
                missing_reason="durable_record_missing",
                oversized_reason="durable_record_oversized",
            )
            if hashlib.sha256(raw_record).hexdigest() != record_digest:
                return DurableLookupResult(None, "durable_record_digest_mismatch")
            try:
                payload = _strict_json_bytes(raw_record, maximum=MAX_DURABLE_RECORD_JSON_BYTES)
                record = SolutionRecord.from_payload(payload, catalog=catalog)
                if _canonical_json_bytes(record.to_payload(catalog=catalog)) != raw_record:
                    raise ValueError
            except (OverflowError, RecursionError, TypeError, ValueError):
                return DurableLookupResult(None, "durable_record_invalid")
            if (
                record.project_id != self.project_id
                or record.workspace_id != workspace_id
                or record.node_id != node_id
                or record.solution_key != solution_key
                or record.residency is not SolutionResidency.DURABLE
                or not record.reuse_eligible
            ):
                return DurableLookupResult(None, "durable_record_binding_mismatch")
            self._record_digests[record.record_id] = record_digest
            return DurableLookupResult(record, "durable_hit")
        except _RepositoryError as exc:
            reason = exc.reason_code
            if reason == "durable_path_unsafe":
                reason = "durable_path_unsafe"
            return DurableLookupResult(None, reason)
        except (AttributeError, OverflowError, RecursionError, TypeError, ValueError):
            return DurableLookupResult(None, "durable_record_binding_mismatch")

    def load_payload(
        self,
        record: SolutionRecord,
        catalog: DataTypeCatalog,
    ) -> DurablePayloadResult:
        try:
            self._require_open()
            if record.residency is not SolutionResidency.DURABLE:
                return DurablePayloadResult(None, "durable_payload_binding_mismatch")
            if record.payload_locator is None:
                return DurablePayloadResult(
                    tuple(
                        (descriptor.port_key, SettledPortResult(status="empty"))
                        for descriptor in record.output_descriptors
                    ),
                    "durable_hit",
                )
            digest = record.payload_locator.reference_id
            raw = _read_file(
                self._root,
                f"blobs/sha256/{digest[:2]}/{digest}",
                maximum=MAX_DURABLE_RESULT_BLOB_BYTES,
                missing_reason="durable_payload_missing",
                oversized_reason="durable_payload_oversized",
            )
            if hashlib.sha256(raw).hexdigest() != digest:
                return DurablePayloadResult(None, "durable_payload_digest_mismatch")
            try:
                payload = dict(_strict_json_bytes(raw, maximum=MAX_DURABLE_RESULT_BLOB_BYTES))
                _exact_fields(payload, _RESULT_BLOB_FIELDS)
                if type(payload["schema_version"]) is not int or payload["schema_version"] != SCHEMA_VERSION:
                    raise ValueError
                if (
                    payload["record_id"] != record.record_id
                    or payload["solution_key"] != record.solution_key
                    or payload["result_digest"] != record.result_digest
                    or payload["settlement_status"] != record.settlement_status
                ):
                    return DurablePayloadResult(None, "durable_payload_binding_mismatch")
                outputs = durable_settled_outputs_from_payload(payload["outputs"])
                canonical_outputs = _canonical_json_bytes(payload["outputs"])
            except (KeyError, OverflowError, RecursionError, TypeError, ValueError):
                return DurablePayloadResult(None, "durable_payload_invalid")
            if hashlib.sha256(canonical_outputs).hexdigest() != record.result_digest:
                return DurablePayloadResult(None, "durable_payload_binding_mismatch")
            return DurablePayloadResult(tuple(sorted(outputs.items())), "durable_hit")
        except _RepositoryError as exc:
            return DurablePayloadResult(None, exc.reason_code)
        except (AttributeError, OverflowError, RecursionError, TypeError, ValueError):
            return DurablePayloadResult(None, "durable_payload_binding_mismatch")

    def stage_record(
        self,
        record: SolutionRecord,
        canonical_payload: bytes,
        catalog: DataTypeCatalog,
    ) -> DurableStageResult:
        try:
            self._require_open()
            if (
                not isinstance(record, SolutionRecord)
                or record.project_id != self.project_id
                or not record.reuse_eligible
            ):
                return DurableStageResult(None, "durable_stage_ineligible")
            if type(canonical_payload) is not bytes or len(canonical_payload) > MAX_DURABLE_RESULT_BLOB_BYTES:
                return DurableStageResult(None, "durable_stage_capacity_exceeded")
            try:
                outputs_payload = _strict_json_bytes(
                    canonical_payload,
                    maximum=MAX_DURABLE_RESULT_BLOB_BYTES,
                )
                outputs = durable_settled_outputs_from_payload(outputs_payload)
                canonical_payload = _canonical_json_bytes(outputs_payload)
            except (OverflowError, RecursionError, TypeError, ValueError):
                return DurableStageResult(None, "durable_stage_ineligible")
            durable_validation = validate_durable_settled_outputs(
                outputs,
                record.output_descriptors,
                catalog,
                _TRUSTED_STAGED_ARTIFACT_CONTEXT,
            )
            if not durable_validation.eligible:
                return DurableStageResult(None, "durable_stage_ineligible")
            if hashlib.sha256(canonical_payload).hexdigest() != record.result_digest:
                return DurableStageResult(None, "durable_stage_ineligible")
            existing = self.lookup_record(
                record.workspace_id,
                record.node_id,
                record.solution_key,
                catalog,
            )
            if existing.reason_code == "durable_hit" and existing.record is not None:
                if existing.record.result_digest == record.result_digest:
                    return DurableStageResult(existing.record, "durable_stage_existing_identical")
                return DurableStageResult(None, "durable_nondeterminism_conflict")
            if existing.reason_code not in {"durable_key_absent"}:
                return DurableStageResult(None, "durable_stage_write_failed")
            has_value = any(item.status == "value" for item in record.output_descriptors)
            if has_value:
                blob_without_locator = _canonical_json_bytes(_result_blob_payload(record, outputs_payload))
                blob_digest = hashlib.sha256(blob_without_locator).hexdigest()
                durable_record = replace(
                    record,
                    residency=SolutionResidency.DURABLE,
                    runtime_generation=None,
                    payload_locator=SolutionPayloadLocator(
                        kind=SolutionResidency.DURABLE,
                        reference_id=blob_digest,
                        blob_digests=(blob_digest,),
                    ),
                    reuse_eligible=True,
                    catalog=catalog,
                )
                blob_raw = _canonical_json_bytes(_result_blob_payload(durable_record, outputs_payload))
                if hashlib.sha256(blob_raw).hexdigest() != blob_digest:
                    return DurableStageResult(None, "durable_stage_ineligible")
                if len(blob_raw) > MAX_DURABLE_RESULT_BLOB_BYTES:
                    return DurableStageResult(None, "durable_stage_capacity_exceeded")
                if _publish_immutable(
                    self._root,
                    f"blobs/sha256/{blob_digest[:2]}/{blob_digest}",
                    blob_raw,
                ):
                    self._published_bytes += len(blob_raw)
            else:
                durable_record = replace(
                    record,
                    residency=SolutionResidency.DURABLE,
                    runtime_generation=None,
                    payload_locator=None,
                    reuse_eligible=True,
                    catalog=catalog,
                )
            record_raw = _canonical_json_bytes(durable_record.to_payload(catalog=catalog))
            if len(record_raw) > MAX_DURABLE_RECORD_JSON_BYTES:
                return DurableStageResult(None, "durable_stage_capacity_exceeded")
            record_digest = hashlib.sha256(record_raw).hexdigest()
            published = _publish_immutable(
                self._root,
                f"records/sha256/{record_digest[:2]}/{record_digest}.json",
                record_raw,
            )
            if published:
                self._published_bytes += len(record_raw)
            self._record_digests[durable_record.record_id] = record_digest
            self._staged_records[
                (durable_record.workspace_id, durable_record.node_id, durable_record.solution_key)
            ] = durable_record
            return DurableStageResult(
                durable_record,
                "durable_stage_published" if published else "durable_stage_existing_identical",
            )
        except _RepositoryError as exc:
            if exc.reason_code == "durable_nondeterminism_conflict":
                return DurableStageResult(None, exc.reason_code)
            if exc.reason_code == "durable_path_unsafe":
                return DurableStageResult(None, "durable_stage_path_unsafe")
            if exc.reason_code == "durable_reparse_rejected":
                return DurableStageResult(None, "durable_stage_reparse_rejected")
            return DurableStageResult(None, "durable_stage_write_failed")
        except (OSError, OverflowError, RecursionError, TypeError, ValueError):
            return DurableStageResult(None, "durable_stage_ineligible")

    def build_candidate_generation(
        self,
        records: Sequence[SolutionRecord] | None = None,
        *,
        generation_id: str | None = None,
    ) -> DurableGenerationResult:
        try:
            self._require_open()
            selected = tuple(records) if records is not None else tuple(self._staged_records.values())
            if len(selected) > MAX_DURABLE_RECORDS_PER_GENERATION:
                return DurableGenerationResult("", "", "durable_generation_capacity_exceeded")
            generation = generation_id or uuid4().hex
            if _HEX_32.fullmatch(generation) is None:
                return DurableGenerationResult("", "", "durable_generation_invalid")
            grouped: dict[tuple[str, str], list[SolutionRecord]] = {}
            record_ids: set[str] = set()
            for record in selected:
                if (
                    not isinstance(record, SolutionRecord)
                    or record.residency is not SolutionResidency.DURABLE
                    or record.project_id != self.project_id
                ):
                    return DurableGenerationResult("", "", "durable_generation_invalid")
                if record.record_id in record_ids:
                    return DurableGenerationResult("", "", "durable_generation_invalid")
                record_ids.add(record.record_id)
                grouped.setdefault((record.workspace_id, record.node_id), []).append(record)
            if len(grouped) > MAX_DURABLE_NODE_MANIFESTS_PER_GENERATION:
                return DurableGenerationResult("", "", "durable_generation_capacity_exceeded")
            entries: list[dict[str, str]] = []
            node_publications: list[tuple[str, bytes]] = []
            path_bindings: set[tuple[str, str]] = set()
            manifest_bytes_total = 0
            referenced_bytes = 0
            for (workspace_id, node_id), node_records in sorted(grouped.items()):
                if len(node_records) > MAX_DURABLE_RECORDS_PER_NODE:
                    return DurableGenerationResult("", "", "durable_generation_capacity_exceeded")
                if len({record.solution_key for record in node_records}) != len(node_records):
                    return DurableGenerationResult("", "", "durable_generation_invalid")
                record_refs: list[dict[str, str]] = []
                for record in sorted(node_records, key=lambda item: item.solution_key):
                    digest = self._record_digests.get(record.record_id)
                    if digest is None:
                        return DurableGenerationResult("", "", "durable_generation_invalid")
                    record_refs.append({"solution_key": record.solution_key, "record_digest": digest})
                    raw_record = _read_file(
                        self._root,
                        f"records/sha256/{digest[:2]}/{digest}.json",
                        maximum=MAX_DURABLE_RECORD_JSON_BYTES,
                        missing_reason="durable_generation_invalid",
                        oversized_reason="durable_generation_capacity_exceeded",
                    )
                    if hashlib.sha256(raw_record).hexdigest() != digest:
                        return DurableGenerationResult("", "", "durable_generation_digest_mismatch")
                    try:
                        persisted = SolutionRecord.from_payload(
                            _strict_json_bytes(
                                raw_record,
                                maximum=MAX_DURABLE_RECORD_JSON_BYTES,
                            ),
                            catalog=self._catalog,
                        )
                    except (TypeError, ValueError):
                        return DurableGenerationResult("", "", "durable_generation_invalid")
                    if persisted != record:
                        return DurableGenerationResult("", "", "durable_generation_invalid")
                    referenced_bytes += len(raw_record)
                    if record.payload_locator is not None:
                        blob_digest = record.payload_locator.reference_id
                        blob_raw = _read_file(
                                self._root,
                                f"blobs/sha256/{blob_digest[:2]}/{blob_digest}",
                                maximum=MAX_DURABLE_RESULT_BLOB_BYTES,
                                missing_reason="durable_generation_invalid",
                                oversized_reason="durable_generation_capacity_exceeded",
                            )
                        if hashlib.sha256(blob_raw).hexdigest() != blob_digest:
                            return DurableGenerationResult("", "", "durable_generation_digest_mismatch")
                        loaded = self.load_payload(record, self._catalog)
                        if loaded.reason_code != "durable_hit":
                            return DurableGenerationResult("", "", "durable_generation_invalid")
                        referenced_bytes += len(blob_raw)
                workspace_key = workspace_path_key(workspace_id)
                node_key = node_path_key(node_id)
                if (workspace_key, node_key) in path_bindings:
                    return DurableGenerationResult("", "", "durable_generation_invalid")
                path_bindings.add((workspace_key, node_key))
                node_payload = {
                    "schema_version": SCHEMA_VERSION,
                    "solution_namespace_id": self.solution_namespace_id,
                    "workspace_id": workspace_id,
                    "node_id": node_id,
                    "workspace_key": workspace_key,
                    "node_key": node_key,
                    "records": record_refs,
                }
                node_raw = _canonical_json_bytes(node_payload)
                manifest_bytes_total += len(node_raw)
                if len(node_raw) > MAX_DURABLE_NODE_MANIFEST_BYTES:
                    return DurableGenerationResult("", "", "durable_generation_capacity_exceeded")
                node_digest = hashlib.sha256(node_raw).hexdigest()
                relative = f"nodes/{workspace_key}/{node_key}.json"
                node_publications.append((relative, node_raw))
                entries.append(
                    {
                        "workspace_key": workspace_key,
                        "node_key": node_key,
                        "relative_path": relative,
                        "node_manifest_digest": node_digest,
                    }
                )
            if (
                manifest_bytes_total > MAX_DURABLE_NODE_MANIFEST_BYTES_PER_GENERATION
                or referenced_bytes > MAX_DURABLE_REFERENCED_BYTES_PER_GENERATION
            ):
                return DurableGenerationResult("", "", "durable_generation_capacity_exceeded")
            entries.sort(key=lambda item: (item["workspace_key"], item["node_key"]))
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "generation_id": generation,
                "solution_namespace_id": self.solution_namespace_id,
                "node_manifests": entries,
            }
            raw = _canonical_json_bytes(manifest)
            if len(raw) > MAX_DURABLE_MANIFEST_SET_BYTES:
                return DurableGenerationResult("", "", "durable_generation_capacity_exceeded")
            digest = hashlib.sha256(raw).hexdigest()
            for relative, node_raw in sorted(node_publications):
                if _publish_immutable(
                    self._root / "generations" / generation,
                    relative,
                    node_raw,
                ):
                    self._published_bytes += len(node_raw)
            if _publish_immutable(
                self._root,
                f"generations/{generation}/manifest-set.json",
                raw,
            ):
                self._published_bytes += len(raw)
            inspection = self._inspect_generation(
                generation,
                expected_manifest_set_digest=digest,
            )
            if inspection.manifest_set_digest != digest:
                return DurableGenerationResult(
                    "",
                    "",
                    "durable_generation_digest_mismatch",
                )
            return DurableGenerationResult(
                generation,
                digest,
                "durable_generation_built",
                self.solution_namespace_id,
            )
        except _RepositoryError as exc:
            reason = (
                exc.reason_code
                if exc.reason_code
                in {
                    "durable_generation_capacity_exceeded",
                    "durable_generation_digest_mismatch",
                    "durable_generation_invalid",
                }
                else "durable_generation_write_failed"
            )
            return DurableGenerationResult("", "", reason)
        except (AttributeError, OverflowError, RecursionError, TypeError, ValueError):
            return DurableGenerationResult("", "", "durable_generation_invalid")

    def _inspect_generation(
        self,
        generation_id: str,
        *,
        expected_manifest_set_digest: str | None = None,
    ) -> _GenerationInspection:
        try:
            self._require_open()
            if _HEX_32.fullmatch(generation_id or "") is None:
                raise _RepositoryError("durable_generation_invalid")
            if (
                expected_manifest_set_digest is not None
                and _SHA256.fullmatch(expected_manifest_set_digest) is None
            ):
                raise _RepositoryError("durable_generation_invalid")
            manifest_relative = f"generations/{generation_id}/manifest-set.json"
            manifest_raw = _read_file(
                self._root,
                manifest_relative,
                maximum=MAX_DURABLE_MANIFEST_SET_BYTES,
                missing_reason="durable_generation_invalid",
                oversized_reason="durable_generation_capacity_exceeded",
            )
            manifest_digest = hashlib.sha256(manifest_raw).hexdigest()
            if (
                expected_manifest_set_digest is not None
                and manifest_digest != expected_manifest_set_digest
            ):
                raise _RepositoryError("durable_generation_digest_mismatch")
            manifest = self._manifest_set(manifest_raw)
            if (
                manifest["generation_id"] != generation_id
                or manifest["solution_namespace_id"] != self.solution_namespace_id
            ):
                raise _RepositoryError("durable_generation_invalid")

            paths: set[Path] = {self._root / manifest_relative}
            record_count = 0
            node_manifest_bytes = 0
            referenced_bytes = 0
            for entry in manifest["node_manifests"]:
                node_relative = (
                    f"generations/{generation_id}/{entry['relative_path']}"
                )
                node_raw = _read_file(
                    self._root,
                    node_relative,
                    maximum=MAX_DURABLE_NODE_MANIFEST_BYTES,
                    missing_reason="durable_generation_invalid",
                    oversized_reason="durable_generation_capacity_exceeded",
                )
                if hashlib.sha256(node_raw).hexdigest() != entry["node_manifest_digest"]:
                    raise _RepositoryError("durable_generation_digest_mismatch")
                node_manifest_bytes += len(node_raw)
                if (
                    node_manifest_bytes
                    > MAX_DURABLE_NODE_MANIFEST_BYTES_PER_GENERATION
                ):
                    raise _RepositoryError(
                        "durable_generation_capacity_exceeded"
                    )
                generic_node = _strict_json_bytes(
                    node_raw,
                    maximum=MAX_DURABLE_NODE_MANIFEST_BYTES,
                )
                node_manifest = self._node_manifest(
                    node_raw,
                    generic_node.get("workspace_id", ""),
                    generic_node.get("node_id", ""),
                )
                record_count += len(node_manifest["records"])
                if record_count > MAX_DURABLE_RECORDS_PER_GENERATION:
                    raise _RepositoryError(
                        "durable_generation_capacity_exceeded"
                    )
                paths.add(self._root / node_relative)
                for record_ref in node_manifest["records"]:
                    record_digest = record_ref["record_digest"]
                    record_relative = (
                        f"records/sha256/{record_digest[:2]}/{record_digest}.json"
                    )
                    record_raw = _read_file(
                        self._root,
                        record_relative,
                        maximum=MAX_DURABLE_RECORD_JSON_BYTES,
                        missing_reason="durable_generation_invalid",
                        oversized_reason="durable_generation_capacity_exceeded",
                    )
                    if hashlib.sha256(record_raw).hexdigest() != record_digest:
                        raise _RepositoryError(
                            "durable_generation_digest_mismatch"
                        )
                    referenced_bytes += len(record_raw)
                    if referenced_bytes > MAX_DURABLE_REFERENCED_BYTES_PER_GENERATION:
                        raise _RepositoryError(
                            "durable_generation_capacity_exceeded"
                        )
                    record = SolutionRecord.from_payload(
                        _strict_json_bytes(
                            record_raw,
                            maximum=MAX_DURABLE_RECORD_JSON_BYTES,
                        ),
                        catalog=self._catalog,
                    )
                    if (
                        _canonical_json_bytes(
                            record.to_payload(catalog=self._catalog)
                        )
                        != record_raw
                        or record.project_id != self.project_id
                        or record.workspace_id != node_manifest["workspace_id"]
                        or record.node_id != node_manifest["node_id"]
                        or record.solution_key != record_ref["solution_key"]
                        or record.residency is not SolutionResidency.DURABLE
                        or not record.reuse_eligible
                    ):
                        raise _RepositoryError("durable_generation_invalid")
                    paths.add(self._root / record_relative)
                    if record.payload_locator is None:
                        continue
                    blob_digest = record.payload_locator.reference_id
                    blob_relative = f"blobs/sha256/{blob_digest[:2]}/{blob_digest}"
                    blob_raw = _read_file(
                        self._root,
                        blob_relative,
                        maximum=MAX_DURABLE_RESULT_BLOB_BYTES,
                        missing_reason="durable_generation_invalid",
                        oversized_reason="durable_generation_capacity_exceeded",
                    )
                    if hashlib.sha256(blob_raw).hexdigest() != blob_digest:
                        raise _RepositoryError(
                            "durable_generation_digest_mismatch"
                        )
                    referenced_bytes += len(blob_raw)
                    if referenced_bytes > MAX_DURABLE_REFERENCED_BYTES_PER_GENERATION:
                        raise _RepositoryError(
                            "durable_generation_capacity_exceeded"
                        )
                    loaded = self.load_payload(record, self._catalog)
                    if loaded.reason_code != "durable_hit":
                        reason = (
                            "durable_generation_capacity_exceeded"
                            if loaded.reason_code == "durable_payload_oversized"
                            else "durable_generation_invalid"
                        )
                        raise _RepositoryError(reason)
                    paths.add(self._root / blob_relative)
            return _GenerationInspection(
                paths=frozenset(paths),
                manifest_set_digest=manifest_digest,
            )
        except _RepositoryError:
            raise
        except (
            AttributeError,
            OverflowError,
            RecursionError,
            TypeError,
            ValueError,
        ) as exc:
            raise _RepositoryError("durable_generation_invalid") from exc

    def validate_generation(
        self,
        generation_id: str,
        manifest_set_digest: str,
    ) -> DurableGenerationResult:
        try:
            inspection = self._inspect_generation(
                generation_id,
                expected_manifest_set_digest=manifest_set_digest,
            )
        except _RepositoryError as exc:
            reason = (
                exc.reason_code
                if exc.reason_code
                in {
                    "durable_generation_capacity_exceeded",
                    "durable_generation_digest_mismatch",
                    "durable_generation_invalid",
                }
                else "durable_generation_invalid"
            )
            return DurableGenerationResult("", "", reason)
        return DurableGenerationResult(
            generation_id,
            inspection.manifest_set_digest,
            "durable_generation_valid",
            self.solution_namespace_id,
        )

    def generation_record_exports(
        self,
        *,
        artifact_context: object | None,
    ) -> tuple[ProjectSolutionSaveRecordExport, ...]:
        self._require_open()
        exports: list[ProjectSolutionSaveRecordExport] = []
        validation_context = (
            artifact_context
            if artifact_context is not None
            else _TRUSTED_STAGED_ARTIFACT_CONTEXT
        )
        for entry in self._manifest["node_manifests"]:
            node_raw = _read_file(
                self._root / "generations" / self._active_generation_id,
                entry["relative_path"],
                maximum=MAX_DURABLE_NODE_MANIFEST_BYTES,
                missing_reason="durable_generation_invalid",
                oversized_reason="durable_generation_capacity_exceeded",
            )
            if hashlib.sha256(node_raw).hexdigest() != entry["node_manifest_digest"]:
                raise _RepositoryError("durable_generation_digest_mismatch")
            node_manifest = self._node_manifest(
                node_raw,
                workspace_id=_strict_json_bytes(
                    node_raw,
                    maximum=MAX_DURABLE_NODE_MANIFEST_BYTES,
                )["workspace_id"],
                node_id=_strict_json_bytes(
                    node_raw,
                    maximum=MAX_DURABLE_NODE_MANIFEST_BYTES,
                )["node_id"],
            )
            for record_ref in node_manifest["records"]:
                lookup = self.lookup_record(
                    node_manifest["workspace_id"],
                    node_manifest["node_id"],
                    record_ref["solution_key"],
                    self._catalog,
                )
                if lookup.record is None:
                    raise _RepositoryError("durable_generation_invalid")
                loaded = self.load_payload(lookup.record, self._catalog)
                if loaded.outputs is None:
                    raise _RepositoryError("durable_generation_invalid")
                validation = validate_durable_settled_outputs(
                    dict(loaded.outputs),
                    lookup.record.output_descriptors,
                    self._catalog,
                    validation_context,
                )
                if not validation.eligible or validation.canonical_payload is None:
                    raise _RepositoryError("durable_generation_invalid")
                exports.append(
                    ProjectSolutionSaveRecordExport(
                        record=lookup.record,
                        canonical_payload=validation.canonical_payload,
                        maximum_reuse_scope="durable",
                        is_current=False,
                    )
                )
        return tuple(exports)

    def reachable_generation_pairs(
        self,
        generation_pairs: Iterable[tuple[str, str]],
    ) -> frozenset[Path]:
        if isinstance(generation_pairs, (str, bytes)):
            raise TypeError("generation pairs must be an iterable")
        reachable: set[Path] = set()
        for generation_id, manifest_set_digest in tuple(generation_pairs):
            inspection = self._inspect_generation(
                generation_id,
                expected_manifest_set_digest=manifest_set_digest,
            )
            reachable.update(inspection.paths)
        return frozenset(reachable)

    def generation_storage_bytes(self) -> int:
        self._require_open()
        if not self._active_generation_id or not self._active_manifest_set_digest:
            return 0
        inspection = self._inspect_generation(
            self._active_generation_id,
            expected_manifest_set_digest=self._active_manifest_set_digest,
        )
        total = 0
        for path in inspection.paths:
            path_stat = os.lstat(path)
            if _is_link_or_reparse(path_stat) or not stat.S_ISREG(path_stat.st_mode):
                raise _RepositoryError("durable_path_unsafe")
            total += int(path_stat.st_size)
        return total

    def enumerate_orphan_candidates(
        self,
    ) -> tuple[tuple[str, ...], bool]:
        self._require_open()
        try:
            root_stat = os.lstat(self._root)
        except FileNotFoundError:
            return (), True
        if _is_link_or_reparse(root_stat) or not stat.S_ISDIR(root_stat.st_mode):
            raise _RepositoryError("durable_path_unsafe")
        stack = [self._root]
        candidates: list[str] = []
        scanned = 0
        scan_complete = True
        while stack:
            directory = stack.pop()
            with os.scandir(directory) as entries:
                ordered = sorted(entries, key=lambda item: item.name)
            for entry in ordered:
                scanned += 1
                if scanned > MAX_PROJECT_SOLUTION_ORPHAN_SCAN_ENTRIES:
                    scan_complete = False
                    stack.clear()
                    break
                entry_stat = entry.stat(follow_symlinks=False)
                if _is_link_or_reparse(entry_stat):
                    raise _RepositoryError("durable_reparse_rejected")
                path = Path(entry.path)
                if stat.S_ISDIR(entry_stat.st_mode):
                    stack.append(path)
                    continue
                if not stat.S_ISREG(entry_stat.st_mode):
                    raise _RepositoryError("durable_path_unsafe")
                relative = path.relative_to(self._root).as_posix()
                if any(pattern.fullmatch(relative) for pattern in _PRUNABLE_PATH_PATTERNS):
                    candidates.append(relative)
        ordered_candidates = tuple(sorted(set(candidates)))
        if len(ordered_candidates) > MAX_PROJECT_SOLUTION_ORPHAN_CANDIDATES:
            ordered_candidates = ordered_candidates[:MAX_PROJECT_SOLUTION_ORPHAN_CANDIDATES]
            scan_complete = False
        return ordered_candidates, scan_complete

    def enumerate_reachable_paths(
        self,
        generation_ids: Iterable[str],
    ) -> frozenset[Path]:
        if isinstance(generation_ids, (str, bytes)):
            raise TypeError("generation_ids must be an iterable of IDs")
        reachable: set[Path] = set()
        try:
            for generation_id in tuple(generation_ids):
                expected_digest = (
                    self._active_manifest_set_digest
                    if generation_id == self._active_generation_id
                    else None
                )
                inspection = self._inspect_generation(
                    generation_id,
                    expected_manifest_set_digest=expected_digest,
                )
                reachable.update(inspection.paths)
        except _RepositoryError as exc:
            raise ValueError("durable generation reachability is invalid") from exc
        return frozenset(reachable)

    def prune_unreachable_paths(
        self,
        candidate_relative_paths: Iterable[str],
        *,
        reachable_paths: Iterable[Path],
    ) -> tuple[str, ...]:
        self._require_open()
        if isinstance(candidate_relative_paths, (str, bytes)):
            raise TypeError("candidate_relative_paths must be an iterable")
        if isinstance(reachable_paths, (str, bytes)):
            raise TypeError("reachable_paths must be an iterable")
        protected = {Path(path) for path in reachable_paths}
        if self._active_generation_id:
            protected.update(
                self.enumerate_reachable_paths((self._active_generation_id,))
            )
        protected_keys = {
            os.path.normcase(os.path.abspath(os.fspath(path)))
            for path in protected
        }
        candidates: list[tuple[str, Path, tuple[int, int, int, int, int]]] = []
        for relative in sorted(set(candidate_relative_paths)):
            if (
                not isinstance(relative, str)
                or not any(pattern.fullmatch(relative) for pattern in _PRUNABLE_PATH_PATTERNS)
            ):
                raise ValueError("prune candidate path is invalid")
            try:
                target = validate_owned_artifact_path(self._root, relative)
            except FileNotFoundError:
                continue
            except ValueError as exc:
                raise ValueError("prune candidate path is unsafe") from exc
            if os.path.normcase(os.path.abspath(os.fspath(target))) in protected_keys:
                continue
            target_stat = os.lstat(target)
            if not stat.S_ISREG(target_stat.st_mode):
                raise ValueError("prune candidate is not a regular file")
            candidates.append((relative, target, _identity(target_stat)))

        for _relative, target, expected_identity in candidates:
            validate_owned_artifact_path(
                self._root,
                target.relative_to(self._root).as_posix(),
            )
            if _identity(os.lstat(target)) != expected_identity:
                raise ValueError("prune candidate changed during validation")

        removed: list[str] = []
        for relative, target, expected_identity in candidates:
            try:
                validate_owned_artifact_path(self._root, relative)
                if _identity(os.lstat(target)) != expected_identity:
                    raise ValueError("prune candidate changed before deletion")
                target.unlink()
                if target.exists():
                    continue
            except FileNotFoundError:
                continue
            except OSError:
                continue
            removed.append(relative)
        return tuple(removed)


__all__ = [
    "DurableGenerationResult",
    "MAX_DURABLE_DIAGNOSTIC_UTF8_BYTES",
    "MAX_DURABLE_JSON_DEPTH",
    "MAX_DURABLE_MANIFEST_SET_BYTES",
    "MAX_DURABLE_NODE_MANIFESTS_PER_GENERATION",
    "MAX_DURABLE_NODE_MANIFEST_BYTES",
    "MAX_DURABLE_NODE_MANIFEST_BYTES_PER_GENERATION",
    "MAX_DURABLE_RECORDS_PER_GENERATION",
    "MAX_DURABLE_RECORDS_PER_NODE",
    "MAX_DURABLE_RECORD_JSON_BYTES",
    "MAX_DURABLE_REFERENCED_BYTES_PER_GENERATION",
    "MAX_DURABLE_RESULT_BLOB_BYTES",
    "SCHEMA_VERSION",
    "SolutionRepository",
    "SolutionRepositoryFactory",
    "node_path_key",
    "workspace_path_key",
]
