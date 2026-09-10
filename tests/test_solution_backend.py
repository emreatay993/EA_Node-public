# Purpose: Direct durable backend port and result-contract tests.
# Map: subsystems/execution.md
from __future__ import annotations

import pytest

import ea_node_editor.execution.solution_backend as solution_backend_module
from ea_node_editor.execution.solution_backend import (
    DurableBackendOpenResult,
    DurableLookupResult,
    DurablePayloadResult,
    DurableStageResult,
)
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.runtime_contracts import (
    STRING_DATA_TYPE_ID,
)
from ea_node_editor.runtime_contracts.settled_results import (
    SettledPortResult,
)
from ea_node_editor.runtime_contracts.solution_records import (
    SolutionOutputDescriptor,
    SolutionPayloadLocator,
    SolutionRecord,
    SolutionResidency,
)

_A = "a" * 64
_B = "b" * 64
_C = "c" * 64
_REGISTRY = build_default_registry()


def _descriptor(*, status: str = "value") -> SolutionOutputDescriptor:
    return SolutionOutputDescriptor(
        port_key="result",
        status=status,
        data_type_id=STRING_DATA_TYPE_ID if status == "value" else "",
        concrete_data_type_ids=(STRING_DATA_TYPE_ID,) if status == "value" else (),
        data_access="item" if status == "value" else "",
        item_count=1 if status == "value" else 0,
        payload_kinds=("inline",) if status == "value" else (),
        payload_digest=_A if status == "value" else "",
        payload_schema_version=1 if status == "value" else 0,
    )


def _record(
    *,
    residency: SolutionResidency = SolutionResidency.SESSION,
    descriptors: tuple[SolutionOutputDescriptor, ...] | None = None,
    locator: SolutionPayloadLocator | None = None,
) -> SolutionRecord:
    output_descriptors = descriptors if descriptors is not None else (_descriptor(),)
    payload_locator = locator
    if payload_locator is None and any(
        item.status == "value" for item in output_descriptors
    ):
        payload_locator = SolutionPayloadLocator(
            kind=residency,
            reference_id="session-output"
            if residency is SolutionResidency.SESSION
            else _B,
            blob_digests=() if residency is SolutionResidency.SESSION else (_B,),
        )
    return SolutionRecord(
        record_id="record-1",
        project_id="project-1",
        workspace_id="workspace-1",
        node_id="node-1",
        solution_key=_A,
        node_interface_revision=1,
        node_interface_digest=_B,
        node_contract_digest=_C,
        dependency_solution_keys=(),
        input_provenance_digest=_A,
        execution_policy_digest=_B,
        implementation_digest=_C,
        execution_environment_digest=_A,
        settlement_status=(
            "completed"
            if not output_descriptors
            or any(item.status == "value" for item in output_descriptors)
            else "empty"
        ),
        result_digest=_B,
        reuse_eligible=True,
        output_descriptors=output_descriptors,
        payload_locator=payload_locator,
        residency=residency,
        runtime_generation=7 if residency is SolutionResidency.SESSION else None,
        created_at_epoch_ms=1,
        catalog=(
            _REGISTRY.data_types if residency is SolutionResidency.DURABLE else None
        ),
    )


def test_durable_port_results_enforce_type_specific_combinations() -> None:
    record = _record(residency=SolutionResidency.DURABLE)
    outputs = (("result", SettledPortResult(status="empty")),)

    assert DurableLookupResult(record, "durable_hit").record is record
    assert DurablePayloadResult(outputs, "durable_hit").outputs == outputs
    assert DurableStageResult(record, "durable_stage_published").record is record
    with pytest.raises(ValueError, match="requires a solution record"):
        DurableLookupResult(None, "durable_hit")
    with pytest.raises(ValueError, match="misses cannot carry"):
        DurableLookupResult(record, "durable_key_absent")
    with pytest.raises(ValueError, match="requires outputs"):
        DurablePayloadResult(None, "durable_hit")
    with pytest.raises(ValueError, match="misses cannot carry"):
        DurablePayloadResult(outputs, "durable_payload_missing")
    with pytest.raises(ValueError, match="requires a record"):
        DurableStageResult(None, "durable_stage_existing_identical")
    with pytest.raises(ValueError, match="failed durable stages"):
        DurableStageResult(record, "durable_stage_write_failed")
    with pytest.raises(ValueError, match="reason_code"):
        DurableLookupResult(None, "unknown")


def test_every_durable_port_reason_has_one_strict_result_shape() -> None:
    record = _record(residency=SolutionResidency.DURABLE)
    outputs = (("result", SettledPortResult(status="empty")),)
    for reason in solution_backend_module._DURABLE_LOOKUP_REASONS:  # noqa: SLF001
        result = DurableLookupResult(
            record if reason == "durable_hit" else None,
            reason,
        )
        assert (result.record is not None) is (reason == "durable_hit")
    for reason in solution_backend_module._DURABLE_PAYLOAD_REASONS:  # noqa: SLF001
        result = DurablePayloadResult(
            outputs if reason == "durable_hit" else None,
            reason,
        )
        assert (result.outputs is not None) is (reason == "durable_hit")
    for reason in solution_backend_module._DURABLE_STAGE_REASONS:  # noqa: SLF001
        succeeded = reason in {
            "durable_stage_published",
            "durable_stage_existing_identical",
        }
        result = DurableStageResult(record if succeeded else None, reason)
        assert (result.record is not None) is succeeded


def test_durable_backend_open_result_enforces_active_and_session_only_shapes() -> None:
    class Backend:
        def lookup_record(self, workspace_id, node_id, solution_key, catalog):  # noqa: ANN001, ANN201
            del workspace_id, node_id, solution_key, catalog
            return DurableLookupResult(None, "durable_key_absent")

        def load_payload(self, record, catalog):  # noqa: ANN001, ANN201
            del record, catalog
            return DurablePayloadResult(None, "durable_payload_missing")

        def stage_record(self, record, canonical_payload, catalog):  # noqa: ANN001, ANN201
            del record, canonical_payload, catalog
            return DurableStageResult(None, "durable_stage_write_failed")

        def close(self) -> None:
            return None

    backend = Backend()
    active = DurableBackendOpenResult(
        backend,
        "namespace",
        "durable_bound_active",
        active_generation_id="a" * 32,
        active_manifest_set_digest="b" * 64,
    )
    assert active.backend is backend
    fallback = DurableBackendOpenResult(
        None,
        "namespace",
        "durable_session_only_metadata_absent",
        "x" * 600,
    )
    assert len(fallback.diagnostic.encode("utf-8")) == 512
    with pytest.raises(ValueError, match="backend only"):
        DurableBackendOpenResult(None, "namespace", "durable_bound_active")
    with pytest.raises(ValueError, match="diagnostic"):
        DurableBackendOpenResult(
            None,
            "namespace",
            "durable_session_only_metadata_absent",
        )
    for status_code in solution_backend_module._DURABLE_SESSION_ONLY_STATUSES:  # noqa: SLF001
        result = DurableBackendOpenResult(
            None,
            "namespace",
            status_code,
            "Durable result data will be recomputed.",
        )
        assert result.status_code == status_code


def test_durable_payload_result_requires_sorted_unique_bounded_ports() -> None:
    empty = SettledPortResult(status="empty")
    with pytest.raises(ValueError, match="sorted"):
        DurablePayloadResult((("z", empty), ("a", empty)), "durable_hit")
    with pytest.raises(ValueError, match="unique"):
        DurablePayloadResult((("a", empty), ("a", empty)), "durable_hit")


def test_durable_diagnostics_drop_paths_and_sensitive_text() -> None:
    for diagnostic in (
        r"C:\private\solution.json",
        "token=never-echo-this",
        "/private/solution.json",
    ):
        result = DurableBackendOpenResult(
            None,
            "namespace",
            "durable_session_only_io_error",
            diagnostic,
        )
        assert "private" not in result.diagnostic.casefold()
        assert "never-echo-this" not in result.diagnostic
