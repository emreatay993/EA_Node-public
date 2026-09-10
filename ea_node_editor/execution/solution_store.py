# Purpose: Own session solution facts, records, preparations, and registered runs.
# Map: subsystems/execution.md
# Tests: tests/test_solution_store_session.py, tests/test_runtime_current_results.py
# Landmarks: SolutionStore; register_preparation; consume_preparation; handle_event

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from ea_node_editor.execution.prepared_execution import (
    AcceptedOutputPayload,
    InvalidationResult,
    PreparedAction,
    PreparedExecution,
    validate_accepted_output_payload,
    validate_current_output_payload,
)
from ea_node_editor.execution.project_solution import (
    MAX_PROJECT_SOLUTION_SUPPLEMENTAL_RECORDS,
    ProjectSolutionSaveRecordExport,
    _canonical_json_bytes,
    _project_solution_owner_ids,
)
from ea_node_editor.execution.solution_backend import (
    DurableBackendOpenResult,
    DurableLookupResult,
    DurablePayloadResult,
    DurableSolutionBackend,
    DurableStageResult,
)
from ea_node_editor.runtime_contracts import (
    ArrayDataRef,
    ArraySlice2DRef,
    TabularDataRef,
    TabularWindowRef,
)
from ea_node_editor.runtime_contracts.data_tree import DataTree
from ea_node_editor.runtime_contracts.data_types import DataTypeCatalog
from ea_node_editor.runtime_contracts.durable_values import (
    validate_durable_settled_outputs,
)
from ea_node_editor.runtime_contracts.settled_results import (
    SettledPortResult,
    settled_output_mapping_from_payload,
    settled_outputs_to_payload,
)
from ea_node_editor.runtime_contracts.solution_records import (
    NodeSolutionFact,
    SolutionDisposition,
    SolutionFreshness,
    SolutionOutputDescriptor,
    SolutionPayloadLocator,
    SolutionRecord,
    SolutionResidency,
)
from ea_node_editor.runtime_contracts.value_refs import (
    RuntimeArtifactRef,
    RuntimeHandleRef,
)


@dataclass(frozen=True, slots=True)
class SolutionStoreLimits:
    records_per_node: int = 2
    records_per_workspace: int = 4_096
    payload_bytes_per_workspace: int = 536_870_912
    records_per_runtime: int = 16_384
    payload_bytes_per_runtime: int = 2_147_483_648
    preparations_per_runtime: int = 64
    preparation_bytes_per_runtime: int = 268_435_456

def _durable_record_matches(
    record: SolutionRecord,
    *,
    project_id: str,
    workspace_id: str,
    node_id: str,
    solution_key: str,
) -> bool:
    return bool(
        isinstance(record, SolutionRecord)
        and record.project_id == project_id
        and record.workspace_id == workspace_id
        and record.node_id == node_id
        and record.solution_key == solution_key
        and record.residency is SolutionResidency.DURABLE
        and record.runtime_generation is None
        and record.reuse_eligible
    )




































@dataclass(frozen=True, slots=True)
class CapturedNodeSolution:
    node_id: str
    solution_key: str
    captured_revision: int
    dependency_solution_keys: tuple[str, ...]
    node_interface_revision: int
    node_interface_digest: str
    node_contract_digest: str
    input_provenance_digest: str
    execution_policy_digest: str
    implementation_digest: str
    execution_environment_digest: str
    output_specs: tuple[tuple[str, str, str], ...]
    solution_reuse_scope: str
    identity_reuse_eligible: bool

    def __post_init__(self) -> None:
        if self.solution_reuse_scope not in {"never", "session", "durable"}:
            raise ValueError("solution_reuse_scope is invalid")
        if not isinstance(self.identity_reuse_eligible, bool):
            raise TypeError("identity_reuse_eligible must be a boolean")


@dataclass(frozen=True, slots=True)
class SettlementAcceptance:
    record_id: str
    solution_key: str
    result_digest: str
    disposition: SolutionDisposition
    fact_revision: int


@dataclass(slots=True)
class _RecordEntry:
    record: SolutionRecord
    payload: bytes | None
    payload_size: int
    sequence: int
    maximum_reuse_scope: str
    resource_leases: tuple[Any, ...] = ()


@dataclass(slots=True)
class _PreparationEntry:
    prepared: PreparedExecution
    candidate_registry: Any
    plan: Any
    captured_nodes: dict[str, CapturedNodeSolution]
    generation_snapshot: Any
    encoded_size: int
    sequence: int
    pinned_record_ids: set[str]
    trigger_reservation_id: str = ""
    adopted_workspace_revision: int | None = None


@dataclass(slots=True)
class _RunEntry:
    run_id: str
    preparation: _PreparationEntry
    generation_snapshot: Any
    pinned_record_ids: set[str]
    pre_dispatch_facts: dict[tuple[str, str, str], NodeSolutionFact]
    trigger_reservation_id: str = ""
    run_started_observed: bool = False
    accepted_record_ids: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class _TriggerReservation:
    reservation_id: str
    project_id: str
    workspace_id: str
    trigger_node_id: str
    generation: int
    owner_id: str




class SolutionStore:
    def __init__(self, *, limits: SolutionStoreLimits | None = None) -> None:
        self._limits = limits or SolutionStoreLimits()
        self._lock = threading.RLock()
        self._sequence = 0
        self._namespaces: dict[str, str] = {}
        self._workspace_revisions: dict[tuple[str, str], int] = defaultdict(int)
        self._workspace_execution_orders: dict[tuple[str, str], tuple[str, ...]] = {}
        self._node_revisions: dict[tuple[str, str, str], int] = defaultdict(int)
        self._facts: dict[tuple[str, str, str], NodeSolutionFact] = {}
        self._records: dict[str, _RecordEntry] = {}
        self._record_ids_by_node: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        self._reuse_index: dict[str, str] = {}
        self._preparations: dict[str, _PreparationEntry] = {}
        self._preparation_tombstones: dict[str, str] = {}
        self._runs: dict[str, _RunEntry] = {}
        self._trigger_generations: dict[tuple[str, str, str], int] = defaultdict(int)
        self._trigger_reservations: dict[str, _TriggerReservation] = {}
        self._durable_backend: DurableSolutionBackend | None = None
        self._durable_project_id = ""
        self._durable_status_code = "durable_session_only_factory_unavailable"
        self._durable_diagnostic = ""
        self._last_durable_reason_code = "durable_not_bound"
        self._active_generation_id = ""
        self._active_manifest_set_digest = ""

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def reset_project_session(
        self, project_id: str, project_path: str = ""
    ) -> tuple[str, tuple[InvalidationResult, ...]]:
        normalized_project_id = str(project_id).strip()
        if not normalized_project_id:
            raise ValueError("project_id must be non-empty")
        with self._lock:
            removed_by_workspace: dict[tuple[str, str], set[str]] = defaultdict(set)
            for key in self._facts:
                removed_by_workspace[key[:2]].add(key[2])
            results: list[InvalidationResult] = []
            for workspace_key, removed_ids in sorted(removed_by_workspace.items()):
                revision = self._workspace_revisions[workspace_key] + 1
                order = self._workspace_execution_orders.get(workspace_key, ())
                ordered = tuple(node_id for node_id in order if node_id in removed_ids)
                ordered = (*ordered, *sorted(removed_ids.difference(ordered)))
                results.append(
                    InvalidationResult(
                        project_id=workspace_key[0],
                        workspace_id=workspace_key[1],
                        solution_revision=revision,
                        changed_root_node_ids=(),
                        expired_node_ids=(),
                        removed_node_ids=ordered,
                        reason_code="project_session_reset",
                    )
                )
            self._clear_locked()
            namespace_id = (
                normalized_project_id
                if str(project_path).strip()
                else f"session_{uuid.uuid4().hex}"
            )
            self._namespaces[normalized_project_id] = namespace_id
            return namespace_id, tuple(results)

    def ensure_project(self, project_id: str, project_path: str = "") -> str:
        normalized_project_id = str(project_id).strip()
        if not normalized_project_id:
            raise ValueError("project_id must be non-empty")
        with self._lock:
            namespace_id = self._namespaces.get(normalized_project_id)
            if namespace_id is None:
                namespace_id = (
                    normalized_project_id
                    if str(project_path).strip()
                    else f"session_{uuid.uuid4().hex}"
                )
                self._namespaces[normalized_project_id] = namespace_id
            return namespace_id

    def solution_namespace_id(self, project_id: str) -> str:
        with self._lock:
            return self._namespaces.get(str(project_id).strip(), "")

    def project_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._namespaces))

    @property
    def durable_status(self) -> tuple[str, str]:
        with self._lock:
            return self._durable_status_code, self._durable_diagnostic

    @property
    def last_durable_reason_code(self) -> str:
        with self._lock:
            return self._last_durable_reason_code

    def durable_binding_pointer(self, project_id: str) -> tuple[str, str]:
        with self._lock:
            if self._durable_project_id != str(project_id).strip():
                return "", ""
            return self._active_generation_id, self._active_manifest_set_digest

    def install_durable_backend(
        self,
        project_id: str,
        result: DurableBackendOpenResult,
    ) -> DurableSolutionBackend | None:
        if not isinstance(result, DurableBackendOpenResult):
            raise TypeError("result must be DurableBackendOpenResult")
        normalized_project_id = str(project_id).strip()
        if not normalized_project_id:
            raise ValueError("project_id must be non-empty")
        with self._lock:
            previous = self._durable_backend
            if previous is not result.backend:
                self._evict_durable_binding_state_locked()
            self._durable_backend = result.backend
            self._durable_project_id = (
                normalized_project_id if result.backend is not None else ""
            )
            self._durable_status_code = result.status_code
            self._durable_diagnostic = result.diagnostic
            self._last_durable_reason_code = (
                "durable_hit" if result.backend is not None else "durable_not_bound"
            )
            self._active_generation_id = result.active_generation_id
            self._active_manifest_set_digest = result.active_manifest_set_digest
            self._namespaces[normalized_project_id] = result.solution_namespace_id
            return previous if previous is not result.backend else None

    def detach_durable_backend(self) -> DurableSolutionBackend | None:
        with self._lock:
            backend = self._durable_backend
            self._evict_durable_binding_state_locked()
            self._durable_backend = None
            self._durable_project_id = ""
            self._durable_status_code = "durable_session_only_factory_unavailable"
            self._durable_diagnostic = ""
            self._last_durable_reason_code = "durable_not_bound"
            self._active_generation_id = ""
            self._active_manifest_set_digest = ""
            return backend

    def project_solution_save_inputs(
        self,
        project_id: str,
        retained_owner_ids: Iterable[tuple[str, str]],
        *,
        catalog: DataTypeCatalog,
    ) -> tuple[
        str,
        str,
        str,
        tuple[tuple[str, str], ...],
        tuple[ProjectSolutionSaveRecordExport, ...],
        tuple[str, ...],
        int,
    ]:
        normalized_project_id = str(project_id).strip()
        owners = _project_solution_owner_ids(retained_owner_ids)
        owner_set = set(owners)
        with self._lock:
            namespace_id = self._namespaces.get(normalized_project_id, "")
            if not namespace_id:
                raise ValueError("project solution session is not active")
            candidates: list[tuple[bool, int, str, _RecordEntry]] = []
            for entry in self._records.values():
                record = entry.record
                if (
                    record.project_id != normalized_project_id
                    or (record.workspace_id, record.node_id) not in owner_set
                    or entry.maximum_reuse_scope != "durable"
                    or not record.reuse_eligible
                ):
                    continue
                fact = self._facts.get(
                    self._fact_key(record.project_id, record.workspace_id, record.node_id)
                )
                is_current = bool(
                    fact is not None
                    and fact.freshness is SolutionFreshness.CURRENT
                    and fact.retained_record_id == record.record_id
                    and fact.retained_solution_key == record.solution_key
                )
                if record.residency is SolutionResidency.SESSION and not is_current:
                    continue
                candidates.append((is_current, entry.sequence, record.record_id, entry))
            candidates.sort(key=lambda item: (not item[0], -item[1], item[2]))
            candidates = candidates[:MAX_PROJECT_SOLUTION_SUPPLEMENTAL_RECORDS]
            exports: list[ProjectSolutionSaveRecordExport] = []
            artifact_ids: set[str] = set()
            estimated_copy_bytes = 0
            for is_current, _sequence, _record_id, entry in candidates:
                record = entry.record
                payload = entry.payload
                if payload is None:
                    payload = _canonical_json_bytes(
                        settled_outputs_to_payload(
                            {
                                descriptor.port_key: SettledPortResult(status="empty")
                                for descriptor in record.output_descriptors
                            },
                            catalog=catalog,
                        )
                    )
                try:
                    decoded = json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue

                def collect(value: object) -> None:
                    if isinstance(value, Mapping):
                        if (
                            value.get("__ea_runtime_value__") == "artifact_ref"
                            and value.get("scope") == "managed"
                            and isinstance(value.get("artifact_id"), str)
                            and value["artifact_id"].strip()
                        ):
                            artifact_ids.add(value["artifact_id"].strip())
                        for nested in value.values():
                            collect(nested)
                    elif isinstance(value, list):
                        for nested in value:
                            collect(nested)

                collect(decoded)
                exports.append(
                    ProjectSolutionSaveRecordExport(
                        record=record,
                        canonical_payload=payload,
                        maximum_reuse_scope="durable",
                        is_current=is_current,
                    )
                )
                estimated_copy_bytes += len(payload)
            return (
                namespace_id,
                self._active_generation_id,
                self._active_manifest_set_digest,
                owners,
                tuple(exports),
                tuple(sorted(artifact_ids)),
                estimated_copy_bytes,
            )

    def _evict_durable_binding_state_locked(self) -> None:
        durable_record_ids = {
            record_id
            for record_id, entry in self._records.items()
            if entry.record.residency is SolutionResidency.DURABLE
        }
        for preparation_id, entry in tuple(self._preparations.items()):
            if entry.pinned_record_ids.intersection(durable_record_ids):
                self._drop_preparation_locked(
                    preparation_id,
                    "durable_backend_replaced",
                )
        for run_id, run in tuple(self._runs.items()):
            if run.pinned_record_ids.intersection(durable_record_ids):
                self._runs.pop(run_id, None)
                self._release_trigger_locked(run.trigger_reservation_id)
        for key, fact in tuple(self._facts.items()):
            if (
                fact.residency is SolutionResidency.DURABLE
                or fact.retained_record_id in durable_record_ids
            ):
                self._facts.pop(key, None)
        for record_id in durable_record_ids:
            self._remove_record_locked(record_id)

    def _fact_allows_solution_locked(
        self,
        *,
        project_id: str,
        workspace_id: str,
        node_id: str,
        solution_key: str,
    ) -> bool:
        fact = self._facts.get(
            self._fact_key(project_id, workspace_id, node_id)
        )
        return fact is None or bool(
            fact.freshness is SolutionFreshness.CURRENT
            and fact.retained_solution_key == solution_key
        )

    def _install_lazy_durable_fact_locked(self, record: SolutionRecord) -> None:
        key = self._fact_key(
            record.project_id,
            record.workspace_id,
            record.node_id,
        )
        fact = self._facts.get(key)
        if fact is not None and (
            fact.freshness is not SolutionFreshness.CURRENT
            or fact.retained_solution_key != record.solution_key
            or fact.retained_record_id != record.record_id
            or fact.residency is not SolutionResidency.DURABLE
        ):
            raise ValueError("durable solution fact does not match the record")
        self._facts[key] = NodeSolutionFact(
            project_id=record.project_id,
            workspace_id=record.workspace_id,
            node_id=record.node_id,
            freshness=SolutionFreshness.CURRENT,
            revision=self._node_revisions[key],
            retained_record_id=record.record_id,
            retained_solution_key=record.solution_key,
            residency=SolutionResidency.DURABLE,
            last_disposition=SolutionDisposition.REUSED,
        )

    def workspace_revision(self, project_id: str, workspace_id: str) -> int:
        with self._lock:
            return self._workspace_revisions[(project_id, workspace_id)]

    def node_revision(self, project_id: str, workspace_id: str, node_id: str) -> int:
        with self._lock:
            return self._node_revisions[(project_id, workspace_id, node_id)]

    def _fact_key(
        self, project_id: str, workspace_id: str, node_id: str
    ) -> tuple[str, str, str]:
        return (str(project_id).strip(), str(workspace_id).strip(), str(node_id).strip())

    def _never_fact_locked(
        self,
        project_id: str,
        workspace_id: str,
        node_id: str,
    ) -> NodeSolutionFact:
        key = self._fact_key(project_id, workspace_id, node_id)
        fact = self._facts.get(key)
        if fact is None:
            fact = NodeSolutionFact(
                project_id=key[0],
                workspace_id=key[1],
                node_id=key[2],
                freshness=SolutionFreshness.NEVER,
                revision=self._node_revisions[key],
            )
            self._facts[key] = fact
        return fact

    def fact(
        self,
        project_id: str,
        workspace_id: str,
        node_id: str,
    ) -> NodeSolutionFact:
        with self._lock:
            return self._never_fact_locked(project_id, workspace_id, node_id)

    def facts(self, project_id: str, workspace_id: str) -> tuple[NodeSolutionFact, ...]:
        with self._lock:
            facts_by_node = {
                fact.node_id: fact
                for key, fact in self._facts.items()
                if key[:2] == (project_id, workspace_id)
            }
            order = self._workspace_execution_orders.get(
                (project_id, workspace_id),
                (),
            )
            ordered = [
                facts_by_node.pop(node_id)
                for node_id in order
                if node_id in facts_by_node
            ]
            ordered.extend(
                facts_by_node[node_id] for node_id in sorted(facts_by_node)
            )
            return tuple(ordered)

    def expired_node_ids(
        self,
        project_id: str,
        workspace_id: str,
        *,
        execution_order: Sequence[str] = (),
    ) -> tuple[str, ...]:
        with self._lock:
            expired = {
                fact.node_id
                for key, fact in self._facts.items()
                if key[:2] == (project_id, workspace_id)
                and fact.freshness is SolutionFreshness.EXPIRED
            }
            order = tuple(execution_order) or self._workspace_execution_orders.get(
                (project_id, workspace_id),
                (),
            )
            if order:
                ordered = tuple(
                    node_id for node_id in order if node_id in expired
                )
                return (*ordered, *sorted(expired.difference(ordered)))
            return tuple(sorted(expired))

    def record(self, record_id: str) -> SolutionRecord | None:
        with self._lock:
            entry = self._records.get(str(record_id).strip())
            return entry.record if entry is not None else None

    def select_record(
        self,
        *,
        solution_key: str,
        project_id: str,
        workspace_id: str,
        node_id: str,
        runtime_generation: int,
        catalog: DataTypeCatalog,
    ) -> SolutionRecord | None:
        with self._lock:
            if not self._fact_allows_solution_locked(
                project_id=project_id,
                workspace_id=workspace_id,
                node_id=node_id,
                solution_key=solution_key,
            ):
                return None
            fact = self._facts.get(
                self._fact_key(project_id, workspace_id, node_id)
            )
            record_id = self._reuse_index.get(solution_key)
            entry = self._records.get(record_id or "")
            if entry is not None:
                record = entry.record
                generation_valid = (
                    record.runtime_generation == runtime_generation
                    if record.residency is SolutionResidency.SESSION
                    else record.runtime_generation is None
                )
                if (
                    record.reuse_eligible
                    and record.project_id == project_id
                    and record.workspace_id == workspace_id
                    and record.node_id == node_id
                    and generation_valid
                    and (
                        fact is None
                        or fact.retained_record_id == record.record_id
                    )
                ):
                    return record
            if (
                fact is not None
                and fact.residency is not SolutionResidency.DURABLE
            ):
                return None
            backend = (
                self._durable_backend
                if self._durable_project_id == project_id
                else None
            )
        if backend is None:
            with self._lock:
                self._last_durable_reason_code = "durable_not_bound"
            return None
        try:
            result = backend.lookup_record(
                workspace_id,
                node_id,
                solution_key,
                catalog,
            )
        except Exception:  # noqa: BLE001 - port failures fail closed.
            result = DurableLookupResult(None, "durable_io_error")
        if not isinstance(result, DurableLookupResult):
            result = DurableLookupResult(None, "durable_io_error")
        if result.record is not None and not _durable_record_matches(
            result.record,
            project_id=project_id,
            workspace_id=workspace_id,
            node_id=node_id,
            solution_key=solution_key,
        ):
            result = DurableLookupResult(None, "durable_record_binding_mismatch")
        with self._lock:
            if backend is not self._durable_backend:
                self._last_durable_reason_code = "durable_not_bound"
                return None
            self._last_durable_reason_code = result.reason_code
        return result.record

    def current_outputs(
        self,
        *,
        solution_key: str,
        project_id: str,
        workspace_id: str,
        node_id: str,
        runtime_generation: int,
        catalog: DataTypeCatalog,
        port_keys: tuple[str, ...],
        artifact_context: Any = None,
    ) -> tuple[SolutionRecord, AcceptedOutputPayload] | None:
        """Read the exact CURRENT detached result, without changing reuse policy."""
        key = self._fact_key(project_id, workspace_id, node_id)
        with self._lock:
            fact = self._facts.get(key)
            if (
                fact is None
                or fact.freshness is not SolutionFreshness.CURRENT
                or fact.retained_solution_key != solution_key
            ):
                return None
            entry = self._records.get(fact.retained_record_id or "")
            record = entry.record if entry is not None else None
        if record is None:
            record = self.select_record(
                solution_key=solution_key,
                project_id=project_id,
                workspace_id=workspace_id,
                node_id=node_id,
                runtime_generation=runtime_generation,
                catalog=catalog,
            )
        if record is None or record.record_id != fact.retained_record_id:
            return None
        payload = self.accepted_outputs(
            record,
            catalog=catalog,
            runtime_generation=runtime_generation,
            artifact_context=artifact_context,
        )
        payload = payload.select_ports(port_keys, catalog=catalog)
        validate_current_output_payload(payload, catalog=catalog, port_keys=port_keys)
        with self._lock:
            if (
                self._facts.get(key) != fact
                or self._records.get(record.record_id) is None
            ):
                return None
        return record, payload

    def accepted_outputs(
        self,
        record_id: str | SolutionRecord,
        *,
        catalog: DataTypeCatalog,
        runtime_generation: int,
        artifact_context: Any = None,
    ) -> AcceptedOutputPayload:
        requested_record = record_id if isinstance(record_id, SolutionRecord) else None
        normalized_record_id = (
            requested_record.record_id
            if requested_record is not None
            else str(record_id).strip()
        )
        with self._lock:
            entry = self._records.get(normalized_record_id)
            if (
                entry is not None
                and requested_record is not None
                and entry.record != requested_record
            ):
                raise ValueError("solution record identity is ambiguous")
            if entry is None or not entry.record.reuse_eligible:
                if requested_record is None:
                    raise ValueError("solution record is unavailable for reuse")
                record = requested_record
                backend = (
                    self._durable_backend
                    if self._durable_project_id == requested_record.project_id
                    else None
                )
            else:
                record = entry.record
                backend = None
            if not self._fact_allows_solution_locked(
                project_id=record.project_id,
                workspace_id=record.workspace_id,
                node_id=record.node_id,
                solution_key=record.solution_key,
            ):
                raise ValueError("solution fact is not current")
            if record.residency is SolutionResidency.SESSION and (
                record.runtime_generation != runtime_generation
            ):
                raise ValueError("solution record runtime generation is stale")
            if record.residency is SolutionResidency.DURABLE and record.runtime_generation is not None:
                raise ValueError("durable solution records cannot carry a runtime generation")
            if entry is not None and record.payload_locator is None:
                payload_bytes = _canonical_json_bytes(
                    settled_outputs_to_payload(
                        {
                            descriptor.port_key: SettledPortResult(status="empty")
                            for descriptor in record.output_descriptors
                        },
                        catalog=catalog,
                    )
                )
            elif entry is not None and entry.payload is None:
                raise ValueError("solution record payload is unavailable")
            elif entry is not None:
                payload_bytes = entry.payload
            else:
                payload_bytes = b""
        if entry is None:
            if backend is None or not _durable_record_matches(
                record,
                project_id=record.project_id,
                workspace_id=record.workspace_id,
                node_id=record.node_id,
                solution_key=record.solution_key,
            ):
                raise ValueError("durable solution backend is unavailable")
            try:
                loaded = backend.load_payload(record, catalog)
            except Exception:  # noqa: BLE001 - persistence failures fail closed.
                loaded = DurablePayloadResult(None, "durable_io_error")
            if not isinstance(loaded, DurablePayloadResult):
                loaded = DurablePayloadResult(None, "durable_io_error")
            with self._lock:
                self._last_durable_reason_code = loaded.reason_code
            if loaded.reason_code != "durable_hit" or loaded.outputs is None:
                raise ValueError(loaded.reason_code)
            outputs = dict(loaded.outputs)
            validation = validate_durable_settled_outputs(
                outputs,
                record.output_descriptors,
                catalog,
                artifact_context,
            )
            if not validation.eligible or validation.canonical_payload is None:
                with self._lock:
                    self._last_durable_reason_code = validation.reason_code
                raise ValueError(validation.reason_code)
            payload_bytes = validation.canonical_payload
            if hashlib.sha256(payload_bytes).hexdigest() != record.result_digest:
                raise ValueError("solution record payload digest is invalid")
            payload = AcceptedOutputPayload(
                node_id=record.node_id,
                record_id=record.record_id,
                solution_key=record.solution_key,
                settlement_status=record.settlement_status,
                result_digest=record.result_digest,
                residency=record.residency,
                runtime_generation=record.runtime_generation,
                outputs=payload_bytes,
                catalog=catalog,
            )
            validate_accepted_output_payload(
                record,
                payload,
                catalog=catalog,
                artifact_context=artifact_context,
            )
            with self._lock:
                if (
                    backend is not self._durable_backend
                    or self._durable_project_id != record.project_id
                ):
                    raise ValueError("durable solution backend changed during load")
                existing_id = self._reuse_index.get(record.solution_key)
                existing = self._records.get(existing_id or "")
                if existing is not None and existing.record.result_digest != record.result_digest:
                    self._last_durable_reason_code = "durable_nondeterminism_conflict"
                    raise ValueError("durable_nondeterminism_conflict")
                same_id = self._records.get(record.record_id)
                if same_id is not None and same_id.record != record:
                    self._last_durable_reason_code = "durable_record_binding_mismatch"
                    raise ValueError("durable_record_binding_mismatch")
                if existing is None:
                    new_entry = _RecordEntry(
                        record=record,
                        payload=payload_bytes if record.payload_locator is not None else None,
                        payload_size=len(payload_bytes) if record.payload_locator is not None else 0,
                        sequence=self._next_sequence(),
                        maximum_reuse_scope="durable",
                    )
                    self._records[record.record_id] = new_entry
                    key = self._fact_key(record.project_id, record.workspace_id, record.node_id)
                    self._record_ids_by_node[key].append(record.record_id)
                    self._reuse_index[record.solution_key] = record.record_id
                self._install_lazy_durable_fact_locked(record)
                self._last_durable_reason_code = "durable_hit"
            return payload
        if hashlib.sha256(payload_bytes).hexdigest() != record.result_digest:
            raise ValueError("solution record payload digest is invalid")
        payload = AcceptedOutputPayload(
            node_id=record.node_id,
            record_id=record.record_id,
            solution_key=record.solution_key,
            settlement_status=record.settlement_status,
            result_digest=record.result_digest,
            residency=record.residency,
            runtime_generation=record.runtime_generation,
            outputs=payload_bytes,
            catalog=catalog,
        )
        validate_accepted_output_payload(
            record,
            payload,
            catalog=catalog,
            artifact_context=artifact_context,
        )
        if record.residency is SolutionResidency.DURABLE:
            with self._lock:
                current_entry = self._records.get(record.record_id)
                if current_entry is None or current_entry.record != record:
                    raise ValueError("durable solution record changed during validation")
                self._install_lazy_durable_fact_locked(record)
        return payload

    def invalidate(
        self,
        *,
        project_id: str,
        workspace_id: str,
        plan: Any,
        changed_root_node_ids: Sequence[str],
        reason_code: str,
    ) -> tuple[InvalidationResult, tuple[Any, ...]]:
        normalized_reason = str(reason_code).strip()
        if not normalized_reason:
            raise ValueError("reason_code must be non-empty")
        closure = plan.affected_downstream_closure(changed_root_node_ids)
        contributing_roots = {
            root_node_id
            for roots_for_node in closure.values()
            for root_node_id in roots_for_node
        }
        roots = tuple(
            node_id for node_id in plan.execution_order if node_id in contributing_roots
        )
        if not roots:
            roots = tuple(dict.fromkeys(changed_root_node_ids))
        with self._lock:
            if project_id not in self._namespaces:
                raise ValueError("unknown project solution session")
            workspace_key = (project_id, workspace_id)
            active_node_ids = {
                node_id
                for node_id in plan.execution_order
                if plan.node_specs[node_id].runtime_behavior == "active"
            }
            removed_node_ids = tuple(
                node_id
                for node_id in self._workspace_execution_orders.get(workspace_key, ())
                if node_id not in active_node_ids
            )
            removed_node_ids = (*removed_node_ids, *(
                node_id
                for key in tuple(self._facts)
                if key[:2] == workspace_key
                and (node_id := key[2]) not in active_node_ids
                and node_id not in removed_node_ids
            ))
            released_leases: list[Any] = []
            for node_id in removed_node_ids:
                released_leases.extend(
                    self._remove_node_locked(project_id, workspace_id, node_id)
                )
            self._workspace_execution_orders[workspace_key] = tuple(
                node_id for node_id in plan.execution_order if node_id in active_node_ids
            )
            self._workspace_revisions[workspace_key] += 1
            for node_id, contributing_roots in closure.items():
                key = self._fact_key(project_id, workspace_id, node_id)
                self._node_revisions[key] += 1
                previous = self._never_fact_locked(project_id, workspace_id, node_id)
                self._facts[key] = NodeSolutionFact(
                    project_id=project_id,
                    workspace_id=workspace_id,
                    node_id=node_id,
                    freshness=SolutionFreshness.EXPIRED,
                    revision=self._node_revisions[key],
                    retained_record_id=previous.retained_record_id,
                    retained_solution_key=previous.retained_solution_key,
                    residency=previous.residency,
                    expiration_reason_code=normalized_reason,
                    expiration_root_node_ids=contributing_roots,
                    last_disposition=previous.last_disposition,
                )
            return (
                InvalidationResult(
                    project_id=project_id,
                    workspace_id=workspace_id,
                    solution_revision=self._workspace_revisions[workspace_key],
                    changed_root_node_ids=roots,
                    expired_node_ids=tuple(closure),
                    removed_node_ids=removed_node_ids,
                    reason_code=normalized_reason,
                ),
                tuple(released_leases),
            )

    def invalidate_current_observations(
        self,
        *,
        run_id: str,
        workspace_id: str,
        requesting_node_id: str,
        root_node_id: str,
        reason_code: str,
        generation_snapshot: Any,
    ) -> tuple[InvalidationResult | None, tuple[Any, ...]]:
        values = {
            "run_id": str(run_id).strip(),
            "workspace_id": str(workspace_id).strip(),
            "requesting_node_id": str(requesting_node_id).strip(),
            "root_node_id": str(root_node_id).strip(),
            "reason_code": str(reason_code).strip(),
        }
        if any(not value or len(value) > 256 for value in values.values()):
            return None, ()
        with self._lock:
            run = self._runs.get(values["run_id"])
            if run is None or run.generation_snapshot != generation_snapshot:
                return None, ()
            envelope = run.preparation.prepared.dispatch_envelope
            if envelope.workspace_id != values["workspace_id"]:
                return None, ()
            plan = run.preparation.plan
            if (
                values["requesting_node_id"] not in plan.scheduled_node_ids
                or values["root_node_id"] not in plan.scheduled_node_ids
            ):
                return None, ()
            closure = plan.affected_downstream_closure((values["root_node_id"],))
            if values["requesting_node_id"] not in closure:
                return None, ()
            if values["requesting_node_id"] in run.accepted_record_ids:
                return None, ()
            affected = []
            for node_id in plan.execution_order:
                record_id = run.accepted_record_ids.get(node_id)
                if node_id not in closure or record_id is None:
                    continue
                fact = self._facts.get(
                    self._fact_key(envelope.project_id, values["workspace_id"], node_id)
                )
                if (
                    fact is not None
                    and fact.freshness is SolutionFreshness.CURRENT
                    and fact.retained_record_id == record_id
                ):
                    affected.append(node_id)
            if not affected:
                return None, ()
            released: list[Any] = []
            project_id = envelope.project_id
            for node_id in affected:
                key = self._fact_key(project_id, values["workspace_id"], node_id)
                previous = self._never_fact_locked(*key)
                self._node_revisions[key] += 1
                record_id = run.accepted_record_ids.pop(node_id)
                entry = self._records.get(record_id)
                if entry is not None:
                    released.extend(entry.resource_leases)
                    entry.resource_leases = ()
                self._facts[key] = NodeSolutionFact(
                    project_id=project_id,
                    workspace_id=values["workspace_id"],
                    node_id=node_id,
                    freshness=SolutionFreshness.EXPIRED,
                    revision=self._node_revisions[key],
                    retained_record_id=previous.retained_record_id,
                    retained_solution_key=previous.retained_solution_key,
                    residency=previous.residency,
                    expiration_reason_code=values["reason_code"],
                    expiration_root_node_ids=closure[node_id],
                    last_disposition=previous.last_disposition,
                )
            workspace_key = (project_id, values["workspace_id"])
            self._workspace_revisions[workspace_key] += 1
            run.preparation.adopted_workspace_revision = self._workspace_revisions[
                workspace_key
            ]
            return (
                InvalidationResult(
                    project_id=project_id,
                    workspace_id=values["workspace_id"],
                    solution_revision=self._workspace_revisions[workspace_key],
                    changed_root_node_ids=(values["root_node_id"],),
                    expired_node_ids=tuple(affected),
                    removed_node_ids=(),
                    reason_code=values["reason_code"],
                ),
                tuple(released),
            )

    def trigger_generation(
        self,
        project_id: str,
        workspace_id: str,
        trigger_node_id: str,
    ) -> int:
        with self._lock:
            return self._trigger_generations[(project_id, workspace_id, trigger_node_id)]

    def reserve_trigger_generation(
        self,
        *,
        project_id: str,
        workspace_id: str,
        trigger_node_id: str,
        preparation_id: str,
    ) -> tuple[str, int]:
        key = (project_id, workspace_id, trigger_node_id)
        with self._lock:
            if any(
                (item.project_id, item.workspace_id, item.trigger_node_id) == key
                for item in self._trigger_reservations.values()
            ):
                raise ValueError("trigger publication generation is already reserved")
            reservation_id = f"trigger_{uuid.uuid4().hex}"
            generation = self._trigger_generations[key] + 1
            self._trigger_reservations[reservation_id] = _TriggerReservation(
                reservation_id=reservation_id,
                project_id=project_id,
                workspace_id=workspace_id,
                trigger_node_id=trigger_node_id,
                generation=generation,
                owner_id=preparation_id,
            )
            return reservation_id, generation

    def release_trigger_reservation(self, reservation_id: str) -> None:
        with self._lock:
            self._release_trigger_locked(str(reservation_id).strip())

    def register_preparation(
        self,
        prepared: PreparedExecution,
        *,
        candidate_registry: Any,
        plan: Any,
        captured_nodes: Sequence[CapturedNodeSolution],
        generation_snapshot: Any,
        encoded_size: int,
        trigger_reservation_id: str = "",
    ) -> None:
        if encoded_size < 0:
            raise ValueError("encoded_size must be non-negative")
        with self._lock:
            if prepared.preparation_id in self._preparations:
                raise ValueError("preparation_id is already registered")
            if encoded_size > self._limits.preparation_bytes_per_runtime:
                self._release_trigger_locked(trigger_reservation_id)
                raise ValueError("preparation exceeds session store capacity")
            while self._preparations and (
                len(self._preparations) >= self._limits.preparations_per_runtime
                or self._preparation_bytes_locked() + encoded_size
                > self._limits.preparation_bytes_per_runtime
            ):
                oldest = min(
                    self._preparations.values(),
                    key=lambda item: (item.sequence, item.prepared.preparation_id),
                )
                self._drop_preparation_locked(
                    oldest.prepared.preparation_id,
                    "preparation_evicted",
                )
            pinned_record_ids = {
                decision.accepted_record_id
                for decision in prepared.node_decisions
                if decision.action.uses_accepted_output
                and decision.accepted_record_id is not None
            }
            self._preparations[prepared.preparation_id] = _PreparationEntry(
                prepared=prepared,
                candidate_registry=candidate_registry,
                plan=plan,
                captured_nodes={item.node_id: item for item in captured_nodes},
                generation_snapshot=generation_snapshot,
                encoded_size=encoded_size,
                sequence=self._next_sequence(),
                pinned_record_ids=pinned_record_ids,
                trigger_reservation_id=trigger_reservation_id,
            )
            if not plan.target_nodes:
                self._workspace_execution_orders[
                    (
                        prepared.dispatch_envelope.project_id,
                        prepared.dispatch_envelope.workspace_id,
                    )
                ] = tuple(plan.execution_order)

    def preparation(self, preparation_id: str) -> _PreparationEntry:
        with self._lock:
            entry = self._preparations.get(str(preparation_id).strip())
            if entry is not None:
                return entry
            reason = self._preparation_tombstones.get(
                str(preparation_id).strip(),
                "preparation_unknown",
            )
            raise ValueError(reason)

    def consume_preparation(
        self,
        preparation_id: str,
        *,
        run_id: str,
        generation_snapshot: Any,
    ) -> _RunEntry:
        with self._lock:
            entry = self._preparations.pop(str(preparation_id).strip(), None)
            if entry is None:
                reason = self._preparation_tombstones.get(
                    str(preparation_id).strip(),
                    "preparation_unknown",
                )
                raise ValueError(reason)
            self._preparation_tombstones[entry.prepared.preparation_id] = (
                "preparation_consumed"
            )
            self._trim_tombstones_locked()
            if entry.trigger_reservation_id:
                reservation = self._trigger_reservations.get(
                    entry.trigger_reservation_id
                )
                if reservation is not None:
                    reservation.owner_id = run_id
            run = _RunEntry(
                run_id=run_id,
                preparation=entry,
                generation_snapshot=generation_snapshot,
                pinned_record_ids=set(entry.pinned_record_ids),
                pre_dispatch_facts={},
                trigger_reservation_id=entry.trigger_reservation_id,
            )
            self._runs[run_id] = run
            envelope = entry.prepared.dispatch_envelope
            for decision in entry.prepared.node_decisions:
                if decision.action is not PreparedAction.EXECUTE:
                    continue
                key = self._fact_key(
                    envelope.project_id,
                    envelope.workspace_id,
                    decision.node_id,
                )
                fact = self._facts.get(key)
                if fact is None or fact.freshness is not SolutionFreshness.CURRENT:
                    continue
                run.pre_dispatch_facts[key] = fact
                self._facts[key] = NodeSolutionFact(
                    project_id=key[0],
                    workspace_id=key[1],
                    node_id=key[2],
                    freshness=SolutionFreshness.EXPIRED,
                    revision=fact.revision,
                    retained_record_id=fact.retained_record_id,
                    retained_solution_key=fact.retained_solution_key,
                    residency=fact.residency,
                    expiration_reason_code="recompute_started",
                    expiration_root_node_ids=(decision.node_id,),
                    last_disposition=fact.last_disposition,
                )
            return run

    def discard_preparation(self, preparation_id: str, reason: str) -> None:
        with self._lock:
            self._drop_preparation_locked(preparation_id, reason)

    def release_run(self, run_id: str, reason: str = "") -> None:
        with self._lock:
            run = self._runs.pop(str(run_id).strip(), None)
            if run is not None:
                if (
                    str(reason).strip() == "start_failed"
                    and not run.run_started_observed
                ):
                    self._restore_failed_start_locked(run)
                self._release_trigger_locked(run.trigger_reservation_id)

    def handle_event(
        self,
        event: Mapping[str, Any],
        generation_snapshot: Any,
        *,
        catalog: DataTypeCatalog,
        resources_reusable: bool = False,
        resource_leases: Sequence[Any] = (),
        artifact_context: Any = None,
    ) -> tuple[
        tuple[dict[str, Any], ...],
        tuple[Any, ...],
        SettlementAcceptance | None,
    ]:
        run_id = str(event.get("run_id", "")).strip()
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.generation_snapshot != generation_snapshot:
                return (), tuple(resource_leases), None
            event_type = str(event.get("type", ""))
            diagnostics: list[dict[str, Any]] = []
            released_leases: list[Any] = []
            acceptance: SettlementAcceptance | None = None
            if event_type == "run_started":
                run.run_started_observed = True
            elif event_type == "node_settled":
                diagnostic, released, acceptance = self._capture_settlement_locked(
                    run,
                    event,
                    catalog=catalog,
                    resources_reusable=resources_reusable,
                    resource_leases=tuple(resource_leases),
                    artifact_context=artifact_context,
                )
                released_leases.extend(released)
                if acceptance is not None:
                    run.accepted_record_ids[
                        str(event.get("node_id", "")).strip()
                    ] = acceptance.record_id
                if diagnostic is not None:
                    diagnostics.append(diagnostic)
            elif resource_leases:
                released_leases.extend(resource_leases)
            elif event_type == "trigger_published":
                self._commit_trigger_locked(run, event)
            if event_type in {"run_completed", "run_failed", "run_stopped"}:
                self._runs.pop(run_id, None)
                self._release_trigger_locked(run.trigger_reservation_id)
            return tuple(diagnostics), tuple(released_leases), acceptance

    def _capture_settlement_locked(
        self,
        run: _RunEntry,
        event: Mapping[str, Any],
        *,
        catalog: DataTypeCatalog,
        resources_reusable: bool,
        resource_leases: tuple[Any, ...],
        artifact_context: Any,
    ) -> tuple[
        dict[str, Any] | None,
        tuple[Any, ...],
        SettlementAcceptance | None,
    ]:
        node_id = str(event.get("node_id", "")).strip()
        capture = run.preparation.captured_nodes.get(node_id)
        if capture is None:
            return None, resource_leases, None
        envelope = run.preparation.prepared.dispatch_envelope
        node_key = self._fact_key(
            envelope.project_id,
            envelope.workspace_id,
            node_id,
        )
        if self._node_revisions[node_key] != capture.captured_revision:
            return None, resource_leases, None
        decision = next(
            (
                item
                for item in run.preparation.prepared.node_decisions
                if item.node_id == node_id
            ),
            None,
        )
        if (
            decision is None
            or str(event.get("solution_key", "")).strip() != decision.solution_key
            or str(event.get("decision_reason", "")).strip()
            != decision.reason_code
        ):
            return None, resource_leases, None
        status = str(event.get("status", "")).strip()
        disposition = str(event.get("disposition", "")).strip()
        if decision.action in {PreparedAction.PRUNE, PreparedAction.READ_CURRENT}:
            return None, resource_leases, None
        if decision.action is PreparedAction.REUSE:
            if disposition != SolutionDisposition.REUSED.value:
                return None, resource_leases, None
            return self._capture_reused_settlement_locked(
                run,
                capture,
                decision,
                event,
                catalog=catalog,
                resources_reusable=resources_reusable,
                resource_leases=resource_leases,
            )
        expected_disposition = {
            "blocked": SolutionDisposition.BLOCKED.value,
            "empty": (
                SolutionDisposition.SKIPPED.value
                if disposition == SolutionDisposition.SKIPPED.value
                else SolutionDisposition.RECOMPUTED.value
            ),
            "completed": SolutionDisposition.RECOMPUTED.value,
            "failed": SolutionDisposition.RECOMPUTED.value,
        }.get(status)
        if disposition != expected_disposition:
            return None, resource_leases, None
        if status not in {"completed", "empty"}:
            return None, resource_leases, None
        try:
            outputs, payload_bytes = self._validated_outputs(
                event.get("outputs", {}),
                catalog=catalog,
            )
            if any(result.status == "failed" for result in outputs.values()):
                return None, resource_leases, None
            descriptors, carriers_reusable = self._output_descriptors(
                capture,
                outputs,
                catalog=catalog,
                runtime_generation=run.generation_snapshot.runtime_generation,
                resources_reusable=resources_reusable,
            )
        except (TypeError, ValueError):
            return None, resource_leases, None
        if not descriptors:
            locator = None
            stored_payload = None
            payload_size = 0
        else:
            reference_id = f"payload_{uuid.uuid4().hex}"
            locator = SolutionPayloadLocator(
                kind=SolutionResidency.SESSION,
                reference_id=reference_id,
            )
            stored_payload = payload_bytes
            payload_size = len(payload_bytes)
        result_digest = hashlib.sha256(payload_bytes).hexdigest()
        established_id = self._reuse_index.get(capture.solution_key)
        established = self._records.get(established_id or "")
        if established is not None:
            if established.record.result_digest != result_digest:
                key = self._fact_key(
                    established.record.project_id,
                    established.record.workspace_id,
                    node_id,
                )
                previous = self._never_fact_locked(*key)
                if self._node_revisions[key] == capture.captured_revision:
                    self._facts[key] = NodeSolutionFact(
                        project_id=key[0],
                        workspace_id=key[1],
                        node_id=key[2],
                        freshness=SolutionFreshness.EXPIRED,
                        revision=self._node_revisions[key],
                        retained_record_id=previous.retained_record_id,
                        retained_solution_key=previous.retained_solution_key,
                        residency=previous.residency,
                        expiration_reason_code="nondeterministic_solution_result",
                        expiration_root_node_ids=(node_id,),
                        last_disposition=previous.last_disposition,
                    )
                diagnostic = {
                    "type": "solution_nondeterminism",
                    "run_id": run.run_id,
                    "workspace_id": key[1],
                    "node_id": node_id,
                    "reason": "same_solution_key_different_result",
                }
                return diagnostic, resource_leases, None
            became_current = self._settle_fact_locked(
                established.record,
                capture,
                disposition=SolutionDisposition.RECOMPUTED,
            )
            return (
                None,
                resource_leases,
                self._acceptance(
                    established.record,
                    SolutionDisposition.RECOMPUTED,
                )
                if became_current
                else None,
            )
        session_reuse_eligible = (
            capture.identity_reuse_eligible
            and capture.solution_reuse_scope != "never"
            and carriers_reusable
            and resources_reusable
        )
        record = SolutionRecord(
            record_id=f"record_{uuid.uuid4().hex}",
            project_id=envelope.project_id,
            workspace_id=envelope.workspace_id,
            node_id=node_id,
            solution_key=capture.solution_key,
            node_interface_revision=capture.node_interface_revision,
            node_interface_digest=capture.node_interface_digest,
            node_contract_digest=capture.node_contract_digest,
            dependency_solution_keys=capture.dependency_solution_keys,
            input_provenance_digest=capture.input_provenance_digest,
            execution_policy_digest=capture.execution_policy_digest,
            implementation_digest=capture.implementation_digest,
            execution_environment_digest=capture.execution_environment_digest,
            settlement_status=status,
            result_digest=result_digest,
            reuse_eligible=session_reuse_eligible,
            output_descriptors=descriptors,
            payload_locator=locator,
            residency=SolutionResidency.SESSION,
            runtime_generation=run.generation_snapshot.runtime_generation,
            created_at_epoch_ms=int(time.time() * 1000),
            catalog=catalog,
        )
        if capture.solution_reuse_scope == "durable" and session_reuse_eligible:
            validation = validate_durable_settled_outputs(
                outputs,
                descriptors,
                catalog,
                artifact_context,
            )
            backend = (
                self._durable_backend
                if self._durable_project_id == envelope.project_id
                else None
            )
            if validation.eligible and validation.canonical_payload is not None and backend is not None:
                try:
                    staged = backend.stage_record(
                        record,
                        validation.canonical_payload,
                        catalog,
                    )
                except Exception:  # noqa: BLE001 - durable publication fails closed.
                    staged = DurableStageResult(None, "durable_stage_write_failed")
                if not isinstance(staged, DurableStageResult):
                    staged = DurableStageResult(None, "durable_stage_write_failed")
                if staged.record is not None and (
                    not _durable_record_matches(
                        staged.record,
                        project_id=record.project_id,
                        workspace_id=record.workspace_id,
                        node_id=record.node_id,
                        solution_key=record.solution_key,
                    )
                    or staged.record.result_digest != record.result_digest
                    or staged.record.settlement_status != record.settlement_status
                    or staged.record.output_descriptors != record.output_descriptors
                ):
                    staged = DurableStageResult(None, "durable_stage_write_failed")
                self._last_durable_reason_code = staged.reason_code
                if staged.reason_code == "durable_nondeterminism_conflict":
                    key = self._fact_key(
                        envelope.project_id,
                        envelope.workspace_id,
                        node_id,
                    )
                    previous = self._never_fact_locked(*key)
                    self._facts[key] = NodeSolutionFact(
                        project_id=key[0],
                        workspace_id=key[1],
                        node_id=key[2],
                        freshness=SolutionFreshness.EXPIRED,
                        revision=self._node_revisions[key],
                        retained_record_id=previous.retained_record_id,
                        retained_solution_key=previous.retained_solution_key,
                        residency=previous.residency,
                        expiration_reason_code="nondeterministic_solution_result",
                        expiration_root_node_ids=(node_id,),
                        last_disposition=previous.last_disposition,
                    )
                    return (
                        {
                            "type": "solution_nondeterminism",
                            "run_id": run.run_id,
                            "workspace_id": key[1],
                            "node_id": node_id,
                            "reason": "same_solution_key_different_result",
                        },
                        resource_leases,
                        None,
                    )
                if staged.record is not None:
                    record = staged.record
                    locator = record.payload_locator
                    stored_payload = (
                        validation.canonical_payload
                        if locator is not None
                        else None
                    )
                    payload_size = len(stored_payload or b"")
            elif not validation.eligible:
                self._last_durable_reason_code = validation.reason_code
            elif backend is None:
                self._last_durable_reason_code = "durable_not_bound"
        retained_resource_leases = (
            resource_leases if record.reuse_eligible else ()
        )
        released_leases = list(
            () if record.reuse_eligible else resource_leases
        )
        entry = _RecordEntry(
            record=record,
            payload=stored_payload,
            payload_size=payload_size,
            sequence=self._next_sequence(),
            maximum_reuse_scope=capture.solution_reuse_scope,
            resource_leases=retained_resource_leases,
        )
        self._records[record.record_id] = entry
        node_key = self._fact_key(record.project_id, record.workspace_id, node_id)
        self._record_ids_by_node[node_key].append(record.record_id)
        if record.reuse_eligible:
            self._reuse_index[record.solution_key] = record.record_id
        previous_fact = self._never_fact_locked(*node_key)
        became_current = self._settle_fact_locked(
            record,
            capture,
            disposition=SolutionDisposition.RECOMPUTED,
        )
        fits, evicted_leases = self._enforce_record_limits_locked(record.record_id)
        released_leases.extend(evicted_leases)
        if not fits:
            self._facts[node_key] = previous_fact
            released_leases.extend(self._remove_record_locked(record.record_id))
            if self._node_revisions[node_key] == capture.captured_revision:
                self._facts[node_key] = NodeSolutionFact(
                    project_id=node_key[0],
                    workspace_id=node_key[1],
                    node_id=node_key[2],
                    freshness=SolutionFreshness.EXPIRED,
                    revision=self._node_revisions[node_key],
                    retained_record_id=previous_fact.retained_record_id,
                    retained_solution_key=previous_fact.retained_solution_key,
                    residency=previous_fact.residency,
                    expiration_reason_code="session_store_capacity_exceeded",
                    expiration_root_node_ids=(node_id,),
                    last_disposition=previous_fact.last_disposition,
                )
        elif not became_current:
            run.pinned_record_ids.add(record.record_id)
        return (
            None,
            tuple(released_leases),
            self._acceptance(record, SolutionDisposition.RECOMPUTED)
            if fits and became_current
            else None,
        )

    def _capture_reused_settlement_locked(
        self,
        run: _RunEntry,
        capture: CapturedNodeSolution,
        decision: Any,
        event: Mapping[str, Any],
        *,
        catalog: DataTypeCatalog,
        resources_reusable: bool,
        resource_leases: tuple[Any, ...],
    ) -> tuple[
        dict[str, Any] | None,
        tuple[Any, ...],
        SettlementAcceptance | None,
    ]:
        accepted = next(
            (
                item
                for item in run.preparation.prepared.accepted_output_payloads
                if item.node_id == decision.node_id
            ),
            None,
        )
        record = self._records.get(str(decision.accepted_record_id or ""))
        if (
            accepted is None
            or record is None
            or record.record.record_id not in run.pinned_record_ids
            or str(event.get("record_id", "")).strip() != record.record.record_id
            or str(event.get("residency", "")).strip()
            != record.record.residency.value
            or str(event.get("status", "")).strip()
            != record.record.settlement_status
            or not resources_reusable
        ):
            return None, resource_leases, None
        try:
            validate_accepted_output_payload(
                record.record,
                accepted,
                catalog=catalog,
            )
            outputs, payload_bytes = self._validated_outputs(
                event.get("outputs", {}),
                catalog=catalog,
            )
        except (TypeError, ValueError):
            return None, resource_leases, None
        if (
            hashlib.sha256(payload_bytes).hexdigest() != accepted.result_digest
            or outputs != accepted.decode_outputs(catalog=catalog)
            or record.record.solution_key != capture.solution_key
            or (
                record.record.residency is SolutionResidency.SESSION
                and record.record.runtime_generation
                != run.generation_snapshot.runtime_generation
            )
            or (
                record.record.residency is SolutionResidency.DURABLE
                and record.record.runtime_generation is not None
            )
        ):
            return None, resource_leases, None
        became_current = self._settle_fact_locked(
            record.record,
            capture,
            disposition=SolutionDisposition.REUSED,
        )
        return (
            None,
            resource_leases,
            self._acceptance(record.record, SolutionDisposition.REUSED)
            if became_current
            else None,
        )

    def _validated_outputs(
        self,
        raw_outputs: Any,
        *,
        catalog: DataTypeCatalog,
    ) -> tuple[dict[str, SettledPortResult], bytes]:
        if isinstance(raw_outputs, Mapping) and all(
            isinstance(value, SettledPortResult) for value in raw_outputs.values()
        ):
            payload = settled_outputs_to_payload(raw_outputs, catalog=catalog)
        else:
            if not isinstance(raw_outputs, Mapping):
                raise TypeError("settled outputs must be a mapping")
            payload = dict(raw_outputs)
        outputs = settled_output_mapping_from_payload(payload, catalog=catalog)
        normalized_payload = settled_outputs_to_payload(outputs, catalog=catalog)
        return outputs, _canonical_json_bytes(normalized_payload)

    def _output_descriptors(
        self,
        capture: CapturedNodeSolution,
        outputs: Mapping[str, SettledPortResult],
        *,
        catalog: DataTypeCatalog,
        runtime_generation: int,
        resources_reusable: bool,
    ) -> tuple[tuple[SolutionOutputDescriptor, ...], bool]:
        specs = {port_key: (data_type_id, data_access) for port_key, data_type_id, data_access in capture.output_specs}
        descriptors: list[SolutionOutputDescriptor] = []
        reusable = True
        payload = settled_outputs_to_payload(outputs, catalog=catalog)
        for port_key, result in outputs.items():
            if port_key not in specs or result.status not in {"value", "empty"}:
                raise ValueError("settled output does not match captured output ports")
            data_type_id, data_access = specs[port_key]
            if result.status == "empty":
                descriptors.append(
                    SolutionOutputDescriptor(
                        port_key=port_key,
                        status="empty",
                        data_type_id="",
                        concrete_data_type_ids=(),
                        data_access="",
                        item_count=0,
                        payload_kinds=(),
                        payload_digest="",
                        payload_schema_version=0,
                    )
                )
                continue
            assert isinstance(result.value, DataTree)
            concrete_types: set[str] = set()
            payload_kinds: set[str] = set()
            for _path, items in result.value.branches:
                for item in items:
                    concrete_types.add(
                        str(getattr(item, "data_type_id", "") or data_type_id)
                    )
                    if isinstance(item, RuntimeHandleRef):
                        payload_kinds.add("handle_ref")
                        if (
                            item.worker_generation != runtime_generation
                            or not resources_reusable
                        ):
                            reusable = False
                    elif isinstance(item, RuntimeArtifactRef):
                        payload_kinds.add("artifact_ref")
                        if not resources_reusable:
                            reusable = False
                    elif isinstance(
                        item,
                        (
                            ArrayDataRef,
                            ArraySlice2DRef,
                            TabularDataRef,
                            TabularWindowRef,
                        ),
                    ):
                        payload_kinds.add("inline")
                        if not resources_reusable:
                            reusable = False
                    else:
                        payload_kinds.add("inline")
            if not concrete_types:
                concrete_types.add(data_type_id)
                payload_kinds.add("inline")
            if any(
                not catalog.compatibility(
                    concrete_type_id,
                    data_type_id,
                ).is_compatible
                for concrete_type_id in concrete_types
            ):
                reusable = False
            descriptor_digest = hashlib.sha256(
                _canonical_json_bytes({port_key: payload[port_key]})
            ).hexdigest()
            descriptors.append(
                SolutionOutputDescriptor(
                    port_key=port_key,
                    status="value",
                    data_type_id=data_type_id,
                    concrete_data_type_ids=tuple(sorted(concrete_types)),
                    data_access=data_access,
                    item_count=result.value.item_count,
                    payload_kinds=tuple(sorted(payload_kinds)),
                    payload_digest=descriptor_digest,
                    payload_schema_version=1,
                )
            )
        return tuple(descriptors), reusable

    def _settle_fact_locked(
        self,
        record: SolutionRecord,
        capture: CapturedNodeSolution,
        *,
        disposition: SolutionDisposition,
    ) -> bool:
        key = self._fact_key(record.project_id, record.workspace_id, record.node_id)
        if self._node_revisions[key] != capture.captured_revision:
            return False
        self._facts[key] = NodeSolutionFact(
            project_id=record.project_id,
            workspace_id=record.workspace_id,
            node_id=record.node_id,
            freshness=SolutionFreshness.CURRENT,
            revision=self._node_revisions[key],
            retained_record_id=record.record_id,
            retained_solution_key=record.solution_key,
            residency=record.residency,
            last_disposition=disposition,
        )
        return True

    def _acceptance(
        self,
        record: SolutionRecord,
        disposition: SolutionDisposition,
    ) -> SettlementAcceptance:
        fact = self._facts.get(
            self._fact_key(record.project_id, record.workspace_id, record.node_id)
        )
        if (
            fact is None
            or fact.freshness is not SolutionFreshness.CURRENT
            or fact.retained_record_id != record.record_id
            or fact.retained_solution_key != record.solution_key
        ):
            raise RuntimeError("accepted solution record is not current")
        return SettlementAcceptance(
            record_id=record.record_id,
            solution_key=record.solution_key,
            result_digest=record.result_digest,
            disposition=disposition,
            fact_revision=fact.revision,
        )

    def _restore_failed_start_locked(self, run: _RunEntry) -> None:
        for key, previous in run.pre_dispatch_facts.items():
            current = self._facts.get(key)
            if (
                current is not None
                and current.freshness is SolutionFreshness.EXPIRED
                and current.revision == previous.revision
                and current.expiration_reason_code == "recompute_started"
            ):
                self._facts[key] = previous

    def reset_runtime_generation(self, reason: str) -> tuple[InvalidationResult, ...]:
        with self._lock:
            expired_by_workspace: dict[tuple[str, str], list[str]] = defaultdict(list)
            for key, fact in tuple(self._facts.items()):
                self._node_revisions[key] += 1
                if fact.freshness is SolutionFreshness.NEVER:
                    self._facts[key] = replace(
                        fact,
                        revision=self._node_revisions[key],
                    )
                else:
                    expired_by_workspace[key[:2]].append(key[2])
                    self._facts[key] = NodeSolutionFact(
                        project_id=key[0],
                        workspace_id=key[1],
                        node_id=key[2],
                        freshness=SolutionFreshness.EXPIRED,
                        revision=self._node_revisions[key],
                        expiration_reason_code=str(reason).strip(),
                        expiration_root_node_ids=(key[2],),
                    )
            results: list[InvalidationResult] = []
            for workspace_key, expired_node_ids in sorted(expired_by_workspace.items()):
                self._workspace_revisions[workspace_key] += 1
                order = self._workspace_execution_orders.get(workspace_key, ())
                ordered = tuple(
                    node_id for node_id in order if node_id in expired_node_ids
                )
                ordered = (*ordered, *sorted(set(expired_node_ids).difference(ordered)))
                results.append(
                    InvalidationResult(
                        project_id=workspace_key[0],
                        workspace_id=workspace_key[1],
                        solution_revision=self._workspace_revisions[workspace_key],
                        changed_root_node_ids=ordered,
                        expired_node_ids=ordered,
                        removed_node_ids=(),
                        reason_code=str(reason).strip(),
                    )
                )
            self._records.clear()
            self._record_ids_by_node.clear()
            self._reuse_index.clear()
            for preparation_id in tuple(self._preparations):
                self._drop_preparation_locked(preparation_id, "preparation_evicted")
            self._runs.clear()
            self._trigger_generations.clear()
            self._trigger_reservations.clear()
            return tuple(results)

    def adopt_expected_generation(
        self, preparation_id: str, reason: str
    ) -> tuple[InvalidationResult, ...]:
        """Retire old session state while preserving the preparation that caused it."""

        with self._lock:
            for other_id in tuple(self._preparations):
                if other_id != preparation_id:
                    self._drop_preparation_locked(other_id, "preparation_evicted")
            retained_trigger_id = ""
            retained = self._preparations.get(preparation_id)
            if retained is not None:
                retained_trigger_id = retained.trigger_reservation_id
            for run in tuple(self._runs.values()):
                self._release_trigger_locked(run.trigger_reservation_id)
            self._runs.clear()
            expired_by_workspace: dict[tuple[str, str], list[str]] = defaultdict(list)
            for key, fact in tuple(self._facts.items()):
                if fact.freshness is SolutionFreshness.NEVER:
                    continue
                self._node_revisions[key] += 1
                expired_by_workspace[key[:2]].append(key[2])
                self._facts[key] = NodeSolutionFact(
                    project_id=key[0],
                    workspace_id=key[1],
                    node_id=key[2],
                    freshness=SolutionFreshness.EXPIRED,
                    revision=self._node_revisions[key],
                    expiration_reason_code=str(reason).strip(),
                    expiration_root_node_ids=(key[2],),
                )
            self._records.clear()
            self._record_ids_by_node.clear()
            self._reuse_index.clear()
            self._trigger_generations.clear()
            self._trigger_reservations = {
                reservation_id: reservation
                for reservation_id, reservation in self._trigger_reservations.items()
                if reservation_id == retained_trigger_id
            }
            results: list[InvalidationResult] = []
            for workspace_key, expired_node_ids in sorted(expired_by_workspace.items()):
                self._workspace_revisions[workspace_key] += 1
                order = self._workspace_execution_orders.get(workspace_key, ())
                ordered = tuple(
                    node_id for node_id in order if node_id in expired_node_ids
                )
                ordered = (*ordered, *sorted(set(expired_node_ids).difference(ordered)))
                results.append(
                    InvalidationResult(
                        project_id=workspace_key[0],
                        workspace_id=workspace_key[1],
                        solution_revision=self._workspace_revisions[workspace_key],
                        changed_root_node_ids=ordered,
                        expired_node_ids=ordered,
                        removed_node_ids=(),
                        reason_code=str(reason).strip(),
                    )
                )
            if retained is not None:
                envelope = retained.prepared.dispatch_envelope
                workspace_key = (envelope.project_id, envelope.workspace_id)
                retained.captured_nodes = {
                    node_id: replace(
                        capture,
                        captured_revision=self._node_revisions[
                            self._fact_key(
                                envelope.project_id,
                                envelope.workspace_id,
                                node_id,
                            )
                        ],
                    )
                    for node_id, capture in retained.captured_nodes.items()
                }
                retained.adopted_workspace_revision = self._workspace_revisions[
                    workspace_key
                ]
            return tuple(results)

    def adopt_preparation_generation(
        self,
        preparation_id: str,
        generation_snapshot: Any,
    ) -> None:
        """Bind a cold execute-only preparation to its now-live route generation."""

        with self._lock:
            entry = self._preparations.get(str(preparation_id).strip())
            if entry is None:
                raise ValueError("preparation_unknown")
            if entry.generation_snapshot.available:
                return
            if (
                entry.generation_snapshot.environment_digest
                != generation_snapshot.environment_digest
            ):
                raise ValueError("prepared_execution_environment_changed")
            decisions = {item.node_id: item for item in entry.prepared.node_decisions}
            unavailable_reasons = {
                "execution_generation_unavailable",
                "execution_environment_unavailable",
            }
            reusable_keys: dict[str, bool] = {}
            for node_id in entry.plan.execution_order:
                capture = entry.captured_nodes.get(node_id)
                if capture is None:
                    continue
                eligible = decisions[
                    node_id
                ].reason_code in unavailable_reasons and all(
                    reusable_keys.get(key, False)
                    for key in capture.dependency_solution_keys
                )
                entry.captured_nodes[node_id] = replace(
                    capture, identity_reuse_eligible=eligible
                )
                reusable_keys[capture.solution_key] = eligible
            entry.generation_snapshot = generation_snapshot

    def shutdown(self) -> None:
        with self._lock:
            self._clear_locked()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "records": len(self._records),
                "payload_bytes": sum(item.payload_size for item in self._records.values()),
                "preparations": len(self._preparations),
                "preparation_bytes": self._preparation_bytes_locked(),
                "runs": len(self._runs),
                "trigger_reservations": len(self._trigger_reservations),
            }

    def _commit_trigger_locked(
        self,
        run: _RunEntry,
        event: Mapping[str, Any],
    ) -> None:
        reservation = self._trigger_reservations.get(run.trigger_reservation_id)
        if reservation is None:
            return
        if str(event.get("trigger_node_id", "")).strip() != reservation.trigger_node_id:
            return
        key = (
            reservation.project_id,
            reservation.workspace_id,
            reservation.trigger_node_id,
        )
        if reservation.generation == self._trigger_generations[key] + 1:
            self._trigger_generations[key] = reservation.generation
        self._trigger_reservations.pop(reservation.reservation_id, None)
        run.trigger_reservation_id = ""

    def _preparation_bytes_locked(self) -> int:
        return sum(item.encoded_size for item in self._preparations.values())

    def _drop_preparation_locked(self, preparation_id: str, reason: str) -> None:
        entry = self._preparations.pop(str(preparation_id).strip(), None)
        if entry is None:
            return
        self._release_trigger_locked(entry.trigger_reservation_id)
        self._preparation_tombstones[entry.prepared.preparation_id] = reason
        self._trim_tombstones_locked()

    def _trim_tombstones_locked(self) -> None:
        while len(self._preparation_tombstones) > 256:
            self._preparation_tombstones.pop(next(iter(self._preparation_tombstones)))

    def _release_trigger_locked(self, reservation_id: str) -> None:
        if reservation_id:
            self._trigger_reservations.pop(reservation_id, None)

    def _is_record_pinned_locked(self, record_id: str) -> bool:
        if any(fact.retained_record_id == record_id and fact.freshness is SolutionFreshness.CURRENT for fact in self._facts.values()):
            return True
        return any(
            record_id in entry.pinned_record_ids
            for entry in (*self._preparations.values(), *self._runs.values())
        )

    def _workspace_totals_locked(self, project_id: str, workspace_id: str) -> tuple[int, int]:
        entries = [
            item
            for item in self._records.values()
            if (item.record.project_id, item.record.workspace_id)
            == (project_id, workspace_id)
        ]
        return len(entries), sum(item.payload_size for item in entries)

    def _over_record_limits_locked(self, candidate_id: str) -> bool:
        candidate = self._records[candidate_id]
        workspace_count, workspace_bytes = self._workspace_totals_locked(
            candidate.record.project_id,
            candidate.record.workspace_id,
        )
        node_count = len(
            self._record_ids_by_node[
                self._fact_key(
                    candidate.record.project_id,
                    candidate.record.workspace_id,
                    candidate.record.node_id,
                )
            ]
        )
        return bool(
            node_count > self._limits.records_per_node
            or workspace_count > self._limits.records_per_workspace
            or workspace_bytes > self._limits.payload_bytes_per_workspace
            or len(self._records) > self._limits.records_per_runtime
            or sum(item.payload_size for item in self._records.values())
            > self._limits.payload_bytes_per_runtime
        )

    def _enforce_record_limits_locked(
        self,
        candidate_id: str,
    ) -> tuple[bool, tuple[Any, ...]]:
        released_leases: list[Any] = []
        while self._over_record_limits_locked(candidate_id):
            candidates = [
                entry
                for record_id, entry in self._records.items()
                if record_id != candidate_id
                and not self._is_record_pinned_locked(record_id)
            ]
            if not candidates:
                return False, tuple(released_leases)
            oldest = min(candidates, key=lambda item: (item.sequence, item.record.record_id))
            released_leases.extend(
                self._remove_record_locked(oldest.record.record_id)
            )
        return True, tuple(released_leases)

    def _remove_record_locked(self, record_id: str) -> tuple[Any, ...]:
        entry = self._records.pop(record_id, None)
        if entry is None:
            return ()
        record = entry.record
        if self._reuse_index.get(record.solution_key) == record_id:
            self._reuse_index.pop(record.solution_key, None)
        key = self._fact_key(record.project_id, record.workspace_id, record.node_id)
        record_ids = self._record_ids_by_node.get(key, [])
        self._record_ids_by_node[key] = [item for item in record_ids if item != record_id]
        if not self._record_ids_by_node[key]:
            self._record_ids_by_node.pop(key, None)
        fact = self._facts.get(key)
        if fact is not None and fact.retained_record_id == record_id:
            if fact.freshness is SolutionFreshness.CURRENT:
                raise RuntimeError("current solution records are pinned")
            self._facts[key] = NodeSolutionFact(
                project_id=key[0],
                workspace_id=key[1],
                node_id=key[2],
                freshness=SolutionFreshness.EXPIRED,
                revision=fact.revision,
                expiration_reason_code=fact.expiration_reason_code,
                expiration_root_node_ids=fact.expiration_root_node_ids,
                last_disposition=fact.last_disposition,
            )
        return entry.resource_leases

    def _remove_node_locked(
        self,
        project_id: str,
        workspace_id: str,
        node_id: str,
    ) -> tuple[Any, ...]:
        key = self._fact_key(project_id, workspace_id, node_id)
        record_ids = tuple(self._record_ids_by_node.get(key, ()))
        self._facts.pop(key, None)
        self._node_revisions[key] += 1
        for owner in (*self._preparations.values(), *self._runs.values()):
            owner.pinned_record_ids.difference_update(record_ids)
        released: list[Any] = []
        for record_id in record_ids:
            released.extend(self._remove_record_locked(record_id))
        return tuple(released)

    def take_all_resource_leases(self) -> tuple[Any, ...]:
        with self._lock:
            leases = tuple(
                lease
                for entry in self._records.values()
                for lease in entry.resource_leases
            )
            for entry in self._records.values():
                entry.resource_leases = ()
            return leases

    def _clear_locked(self) -> None:
        self._namespaces.clear()
        self._workspace_revisions.clear()
        self._workspace_execution_orders.clear()
        self._node_revisions.clear()
        self._facts.clear()
        self._records.clear()
        self._record_ids_by_node.clear()
        self._reuse_index.clear()
        self._preparations.clear()
        self._preparation_tombstones.clear()
        self._runs.clear()
        self._trigger_generations.clear()
        self._trigger_reservations.clear()
        self._active_generation_id = ""
        self._active_manifest_set_digest = ""


__all__ = [
    "CapturedNodeSolution",
    "SettlementAcceptance",
    "SolutionStore",
    "SolutionStoreLimits",
]
