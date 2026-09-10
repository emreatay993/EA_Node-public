# Purpose: Durable solution backend/factory ports and strict result DTOs.
# Map: subsystems/execution.md
# Tests: tests/test_solution_backend.py, tests/test_solution_repository.py
# Landmarks: DurableSolutionBackend; DurableSolutionBackendFactory; DurableBackendOpenResult
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ea_node_editor.runtime_contracts.data_types import DataTypeCatalog
from ea_node_editor.runtime_contracts.settled_results import (
    MAX_OUTPUTS_PER_NODE,
    SettledPortResult,
)
from ea_node_editor.runtime_contracts.solution_records import (
    SolutionRecord,
    SolutionResidency,
)

if TYPE_CHECKING:
    from ea_node_editor.execution.project_solution import (
        ProjectSolutionGcResult,
        ProjectSolutionSaveRecordExport,
        ProjectSolutionSaveResult,
        ProjectSolutionSaveSnapshot,
    )

MAX_DURABLE_DIAGNOSTIC_UTF8_BYTES = 512


_DURABLE_NAMESPACE_MAX_UTF8_BYTES = 4_096


_SENSITIVE_DIAGNOSTIC_PATTERN = re.compile(
    r"(?:api[_ -]?key|authorization|cookie|credential|password|private[_ -]?key|secret|token)",
    re.IGNORECASE,
)


_DURABLE_SESSION_ONLY_STATUSES = frozenset(
    {
        "durable_session_only_metadata_absent",
        "durable_session_only_factory_unavailable",
        "durable_session_only_metadata_invalid",
        "durable_session_only_schema_unsupported",
        "durable_session_only_pointer_invalid",
        "durable_session_only_manifest_missing",
        "durable_session_only_manifest_oversized",
        "durable_session_only_manifest_invalid",
        "durable_session_only_manifest_digest_mismatch",
        "durable_session_only_path_unsafe",
        "durable_session_only_reparse_rejected",
        "durable_session_only_io_error",
    }
)


_DURABLE_LOOKUP_REASONS = frozenset(
    {
        "durable_hit",
        "durable_not_bound",
        "durable_key_absent",
        "durable_node_manifest_missing",
        "durable_node_manifest_oversized",
        "durable_node_manifest_invalid",
        "durable_node_manifest_digest_mismatch",
        "durable_record_missing",
        "durable_record_oversized",
        "durable_record_invalid",
        "durable_record_digest_mismatch",
        "durable_record_binding_mismatch",
        "durable_path_unsafe",
        "durable_reparse_rejected",
        "durable_io_error",
    }
)


_DURABLE_PAYLOAD_REASONS = frozenset(
    {
        "durable_hit",
        "durable_not_bound",
        "durable_payload_missing",
        "durable_payload_oversized",
        "durable_payload_invalid",
        "durable_payload_digest_mismatch",
        "durable_payload_binding_mismatch",
        "durable_value_ineligible",
        "durable_artifact_invalid",
        "durable_path_unsafe",
        "durable_reparse_rejected",
        "durable_io_error",
    }
)


_DURABLE_STAGE_REASONS = frozenset(
    {
        "durable_stage_published",
        "durable_stage_existing_identical",
        "durable_stage_ineligible",
        "durable_stage_capacity_exceeded",
        "durable_stage_path_unsafe",
        "durable_stage_reparse_rejected",
        "durable_stage_write_failed",
        "durable_nondeterminism_conflict",
    }
)


_HEX_32_PATTERN = re.compile(r"[0-9a-f]{32}")


_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def sanitize_durable_diagnostic(value: object) -> str:
    text = value if type(value) is str else ""
    if re.search(r"(?:[A-Za-z]:[\\/]|\\\\|/[^ ]|://)", text) or (
        _SENSITIVE_DIAGNOSTIC_PATTERN.search(text)
    ):
        text = ""
    text = text.replace("\x00", " ").replace("\r", " ").replace("\n", " ")
    text = (
        " ".join(text.split())
        or "Durable solutions are unavailable; results will be recomputed."
    )
    encoded = text.encode("utf-8", errors="replace")[:MAX_DURABLE_DIAGNOSTIC_UTF8_BYTES]
    while encoded:
        try:
            return encoded.decode("utf-8")
        except UnicodeDecodeError:
            encoded = encoded[:-1]
    return "Durable solutions are unavailable."


@dataclass(frozen=True, slots=True)
class DurableLookupResult:
    record: SolutionRecord | None
    reason_code: str

    def __post_init__(self) -> None:
        if self.reason_code not in _DURABLE_LOOKUP_REASONS:
            raise ValueError("durable lookup reason_code is invalid")
        if self.reason_code == "durable_hit":
            if not isinstance(self.record, SolutionRecord):
                raise ValueError("durable_hit requires a solution record")
            if (
                self.record.residency is not SolutionResidency.DURABLE
                or not self.record.reuse_eligible
                or self.record.runtime_generation is not None
            ):
                raise ValueError("durable_hit requires a reusable durable record")
        elif self.record is not None:
            raise ValueError("durable lookup misses cannot carry a record")


@dataclass(frozen=True, slots=True)
class DurablePayloadResult:
    outputs: tuple[tuple[str, SettledPortResult], ...] | None
    reason_code: str

    def __post_init__(self) -> None:
        if self.reason_code not in _DURABLE_PAYLOAD_REASONS:
            raise ValueError("durable payload reason_code is invalid")
        if self.reason_code == "durable_hit":
            if not isinstance(self.outputs, tuple):
                raise ValueError("durable_hit requires outputs")
            if any(
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], SettledPortResult)
                for item in self.outputs
            ):
                raise TypeError("durable outputs must be port/result pairs")
            port_keys = tuple(item[0] for item in self.outputs)
            if (
                len(port_keys) > MAX_OUTPUTS_PER_NODE
                or any(not key.strip() or key != key.strip() for key in port_keys)
                or len(port_keys) != len(set(port_keys))
                or port_keys != tuple(sorted(port_keys))
                or any(
                    item[1].status not in {"value", "empty"} for item in self.outputs
                )
            ):
                raise ValueError("durable outputs must be bounded, sorted, and unique")
        elif self.outputs is not None:
            raise ValueError("durable payload misses cannot carry outputs")


@dataclass(frozen=True, slots=True)
class DurableStageResult:
    record: SolutionRecord | None
    reason_code: str

    def __post_init__(self) -> None:
        if self.reason_code not in _DURABLE_STAGE_REASONS:
            raise ValueError("durable stage reason_code is invalid")
        if self.reason_code in {
            "durable_stage_published",
            "durable_stage_existing_identical",
        }:
            if not isinstance(self.record, SolutionRecord):
                raise ValueError("successful durable stage requires a record")
            if (
                self.record.residency is not SolutionResidency.DURABLE
                or not self.record.reuse_eligible
                or self.record.runtime_generation is not None
            ):
                raise ValueError("successful durable stage requires a durable record")
        elif self.record is not None:
            raise ValueError("failed durable stages cannot carry a record")


@dataclass(frozen=True, slots=True)
class DurableBackendOpenResult:
    backend: DurableSolutionBackend | None
    solution_namespace_id: str
    status_code: str
    diagnostic: str = ""
    active_generation_id: str = ""
    active_manifest_set_digest: str = ""

    def __post_init__(self) -> None:
        namespace_id = str(self.solution_namespace_id).strip()
        if (
            not namespace_id
            or len(namespace_id.encode("utf-8")) > _DURABLE_NAMESPACE_MAX_UTF8_BYTES
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in namespace_id
            )
        ):
            raise ValueError("durable backend result requires a namespace")
        if self.status_code == "durable_bound_active":
            if (
                self.backend is None
                or not isinstance(self.backend, DurableSolutionBackend)
                or self.diagnostic
            ):
                raise ValueError("active durable binding requires a backend only")
            if (
                _HEX_32_PATTERN.fullmatch(self.active_generation_id) is None
                or _SHA256_PATTERN.fullmatch(self.active_manifest_set_digest) is None
            ):
                raise ValueError("active durable binding pointer is invalid")
        elif self.status_code in _DURABLE_SESSION_ONLY_STATUSES:
            if (
                self.backend is not None
                or not self.diagnostic
                or self.active_generation_id
                or self.active_manifest_set_digest
            ):
                raise ValueError("session-only durable binding requires one diagnostic")
            diagnostic = sanitize_durable_diagnostic(self.diagnostic)
            object.__setattr__(self, "diagnostic", diagnostic)
        else:
            raise ValueError("durable backend status_code is invalid")
        object.__setattr__(self, "solution_namespace_id", namespace_id)


@runtime_checkable
class DurableSolutionBackend(Protocol):
    def lookup_record(
        self,
        workspace_id: str,
        node_id: str,
        solution_key: str,
        catalog: DataTypeCatalog,
    ) -> DurableLookupResult: ...

    def load_payload(
        self,
        record: SolutionRecord,
        catalog: DataTypeCatalog,
    ) -> DurablePayloadResult: ...

    def stage_record(
        self,
        record: SolutionRecord,
        canonical_payload: bytes,
        catalog: DataTypeCatalog,
    ) -> DurableStageResult: ...

    def close(self) -> None: ...


@runtime_checkable
class DurableSolutionBackendFactory(Protocol):
    def open_backend(
        self,
        project_id: str,
        project_path: str,
        metadata_solution_store: object,
        catalog: DataTypeCatalog,
    ) -> DurableBackendOpenResult: ...

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
    ) -> ProjectSolutionSaveSnapshot: ...

    def stage_project_solution_save(
        self,
        snapshot: ProjectSolutionSaveSnapshot,
        destination_project_path: str,
        catalog: DataTypeCatalog,
        destination_artifact_context: object,
    ) -> ProjectSolutionSaveResult: ...

    def open_project_solution_save_candidate(
        self,
        project_id: str,
        destination_project_path: str,
        metadata_solution_store: object,
        expected_namespace_id: str,
        catalog: DataTypeCatalog,
        destination_artifact_context: object,
    ) -> DurableBackendOpenResult: ...

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
    ) -> ProjectSolutionGcResult: ...
