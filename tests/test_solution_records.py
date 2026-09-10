from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from unittest import mock

import pytest

from ea_node_editor.execution.backends import ExecutionBackendSelection
from ea_node_editor.execution.prepared_execution import (
    AcceptedOutputPayload,
    InvalidationResult,
    PreparedAction,
    PreparedDispatchEnvelope,
    PreparedExecution,
    PreparedNodeDecision,
    RecomputeMode,
    SolutionStateChangedEvent,
    validate_accepted_output_payload,
)
from ea_node_editor.execution.protocol_codec import (
    dict_to_event,
    event_to_dict,
)
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.run_messages import (
    NodeSettledEvent,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.runtime_contracts import (
    COREX_VIEWER_SESSION_HANDLE_KIND,
    STRING_DATA_TYPE_ID,
    TABULAR_DATA_REF_TYPE_ID,
    VIEWER_SESSION_DATA_TYPE_ID,
    DataTree,
    RuntimeHandleRef,
    TabularDataRef,
)
from ea_node_editor.runtime_contracts.settled_results import (
    MAX_ROOT_ERRORS_PER_RESULT,
    RootExecutionError,
    SettledPortResult,
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
            reference_id="session-output" if residency is SolutionResidency.SESSION else _B,
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
            _REGISTRY.data_types
            if residency is SolutionResidency.DURABLE
            else None
        ),
    )


def _dispatch_envelope() -> tuple[PreparedDispatchEnvelope, object, object]:
    registry = _REGISTRY
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Constant",
        0,
        0,
        properties={"value": "ready"},
    )
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    snapshot.metadata["alias_probe"] = {"items": [1]}
    catalog_fingerprint, catalog_revisions = catalog_agreement(registry.data_types)
    plugin_fingerprint = registry.plugin_fingerprint()
    return (
        PreparedDispatchEnvelope(
            project_path="",
            project_id=snapshot.project_id,
            workspace_id=workspace.workspace_id,
            trigger={"alias_probe": {"items": [1]}},
            runtime_snapshot=snapshot,
            execution_backend=ExecutionBackendSelection(),
            target_node_ids=(node.node_id,),
            clicked_trigger_node_id="",
            trigger_capture_node_ids=(),
            trigger_publications={},
            trigger_captures={},
            recompute_mode=RecomputeMode.REUSE_VALID,
            developer_mode=False,
            catalog_fingerprint=catalog_fingerprint,
            catalog_revisions=catalog_revisions,
            plugin_bundles=registry.plugin_bundle_refs(),
            plugin_fingerprint=plugin_fingerprint,
            runtime_registry_fingerprint=runtime_registry_fingerprint(
                catalog_fingerprint,
                plugin_fingerprint,
            ),
            registry_contract_fingerprint=registry.contract_fingerprint(),
            addon_runtime_config=registry.addon_runtime_config(),
            catalog=registry.data_types,
        ),
        registry,
        snapshot,
    )


def test_solution_fact_semantic_rows_and_roundtrip() -> None:
    never = NodeSolutionFact(
        project_id="project",
        workspace_id="workspace",
        node_id="node",
        freshness=SolutionFreshness.NEVER,
        revision=0,
    )
    current = NodeSolutionFact(
        project_id="project",
        workspace_id="workspace",
        node_id="node",
        freshness=SolutionFreshness.CURRENT,
        revision=1,
        retained_record_id="record",
        retained_solution_key=_A,
        residency=SolutionResidency.SESSION,
        last_disposition=SolutionDisposition.RECOMPUTED,
    )
    expired = NodeSolutionFact(
        project_id="project",
        workspace_id="workspace",
        node_id="node",
        freshness=SolutionFreshness.EXPIRED,
        revision=2,
        retained_record_id="record",
        retained_solution_key=_A,
        residency=SolutionResidency.SESSION,
        expiration_reason_code="property_changed",
        expiration_root_node_ids=("node",),
        last_disposition=SolutionDisposition.RECOMPUTED,
    )

    for fact in (never, current, expired):
        assert NodeSolutionFact.from_payload(fact.to_payload()) == fact

    with pytest.raises(ValueError, match="form one triple"):
        NodeSolutionFact(
            project_id="project",
            workspace_id="workspace",
            node_id="node",
            freshness=SolutionFreshness.CURRENT,
            revision=1,
            retained_record_id="record",
            retained_solution_key=_A,
            last_disposition=SolutionDisposition.REUSED,
        )
    with pytest.raises(ValueError, match="reason and root"):
        NodeSolutionFact(
            project_id="project",
            workspace_id="workspace",
            node_id="node",
            freshness=SolutionFreshness.EXPIRED,
            revision=1,
        )


def test_solution_record_descriptor_locator_and_generation_matrix() -> None:
    session = _record()
    durable = _record(residency=SolutionResidency.DURABLE)
    empty = _record(descriptors=(_descriptor(status="empty"),), locator=None)

    for record in (session, durable, empty):
        catalog = (
            _REGISTRY.data_types
            if record.residency is SolutionResidency.DURABLE
            else None
        )
        assert SolutionRecord.from_payload(
            record.to_payload(catalog=catalog),
            catalog=catalog,
        ) == record

    with pytest.raises(ValueError, match="payload locator"):
        replace(session, payload_locator=None)
    with pytest.raises(ValueError, match="runtime generation"):
        SolutionRecord(
            **{
                **session.to_payload(),
                "output_descriptors": session.output_descriptors,
                "payload_locator": session.payload_locator,
                "runtime_generation": None,
            }
        )

    handle_descriptor = replace(
        _descriptor(),
        data_type_id=VIEWER_SESSION_DATA_TYPE_ID,
        concrete_data_type_ids=(VIEWER_SESSION_DATA_TYPE_ID,),
        payload_kinds=("handle_ref",),
    )
    assert _record(descriptors=(handle_descriptor,)).residency is SolutionResidency.SESSION
    with pytest.raises(ValueError, match="session-only carriers"):
        _record(
            residency=SolutionResidency.DURABLE,
            descriptors=(handle_descriptor,),
        )
    session_only_inline_descriptor = replace(
        _descriptor(),
        data_type_id=TABULAR_DATA_REF_TYPE_ID,
    )
    with pytest.raises(ValueError, match="session-only carriers"):
        _record(
            residency=SolutionResidency.DURABLE,
            descriptors=(session_only_inline_descriptor,),
        )
    with pytest.raises(ValueError, match="completed or empty"):
        SolutionRecord(
            **{
                **session.to_payload(),
                "output_descriptors": session.output_descriptors,
                "payload_locator": session.payload_locator,
                "settlement_status": "failed",
            }
        )
    with pytest.raises(TypeError, match="integer"):
        SolutionRecord(
            **{
                **session.to_payload(),
                "output_descriptors": session.output_descriptors,
                "payload_locator": session.payload_locator,
                "created_at_epoch_ms": True,
            }
        )








def test_solution_record_routes_durable_output_validation_to_shared_gate() -> None:
    record = _record(residency=SolutionResidency.DURABLE)
    outputs = {
        "result": SettledPortResult(
            status="value",
            value=DataTree.from_item("cached"),
        )
    }
    validation = record.validate_durable_outputs(
        outputs,
        catalog=_REGISTRY.data_types,
        artifact_context=None,
    )
    assert not validation.eligible  # fixture descriptor digest intentionally differs
    with pytest.raises(ValueError, match="durable residency"):
        _record().validate_durable_outputs(
            outputs,
            catalog=_REGISTRY.data_types,
            artifact_context=None,
        )


def test_durable_record_id_and_logical_id_limits_accept_n_reject_n_plus_one() -> None:
    record = _record()
    assert len(replace(record, record_id="r" * 128).record_id.encode("utf-8")) == 128
    with pytest.raises(ValueError, match="128 bytes"):
        replace(record, record_id="r" * 129)
    assert len(replace(record, project_id="p" * 4096).project_id.encode("utf-8")) == 4096
    with pytest.raises(ValueError, match="4096 bytes"):
        replace(record, project_id="p" * 4097)
    with pytest.raises(ValueError, match="control"):
        replace(record, record_id="record\x7funsafe")
    with pytest.raises(ValueError, match="matching result blob"):
        replace(
            _record(residency=SolutionResidency.DURABLE),
            payload_locator=SolutionPayloadLocator(
                kind=SolutionResidency.DURABLE,
                reference_id=_B,
                blob_digests=(_B, _C),
            ),
            catalog=_REGISTRY.data_types,
        )






def test_solution_record_and_accepted_output_port_statuses_match_exactly() -> None:
    record = _record()
    accepted = AcceptedOutputPayload(
        node_id=record.node_id,
        record_id=record.record_id,
        solution_key=record.solution_key,
        settlement_status=record.settlement_status,
        result_digest=record.result_digest,
        residency=record.residency,
        runtime_generation=record.runtime_generation,
        outputs={
            "result": SettledPortResult(
                status="value", value=DataTree.from_item("cached")
            )
        },
    )
    validate_accepted_output_payload(record, accepted)

    with pytest.raises(ValueError, match="port keys and statuses"):
        validate_accepted_output_payload(
            record,
            replace(
                accepted,
                outputs={
                    "other": SettledPortResult(
                        status="value",
                        value=DataTree.from_item("cached"),
                    )
                },
            ),
        )


def test_output_descriptors_bound_mixed_types_and_carriers() -> None:
    mixed = replace(
        _descriptor(),
        concrete_data_type_ids=(STRING_DATA_TYPE_ID, VIEWER_SESSION_DATA_TYPE_ID),
        payload_kinds=("handle_ref", "inline"),
    )
    assert SolutionOutputDescriptor.from_payload(mixed.to_payload()) == mixed
    with pytest.raises(ValueError, match="sorted"):
        replace(
            mixed,
            concrete_data_type_ids=(VIEWER_SESSION_DATA_TYPE_ID, STRING_DATA_TYPE_ID),
        )
    with pytest.raises(ValueError, match="maximum count 64"):
        replace(
            mixed,
            concrete_data_type_ids=tuple(
                f"COREX.Test.{index:02d}" for index in range(65)
            ),
        )
    with pytest.raises(TypeError, match="reuse_eligible"):
        SolutionRecord(
            **{
                **_record().to_payload(),
                "reuse_eligible": 1,
                "catalog": _REGISTRY.data_types,
            }
        )


def test_settled_results_are_strict_bounded_and_not_protocol_owned() -> None:
    result = SettledPortResult(status="value", value=DataTree.from_item("value"))
    assert SettledPortResult.from_payload(result.to_payload()) == result
    failed = SettledPortResult(
        status="failed",
        errors=(RootExecutionError(node_id="node", error="boom"),),
    )
    assert SettledPortResult.from_payload(failed.to_payload()) == failed

    with pytest.raises(ValueError, match="unexpected"):
        SettledPortResult.from_payload({**result.to_payload(), "extra": True})
    with pytest.raises(ValueError, match="root error count"):
        SettledPortResult(
            status="failed",
            errors=tuple(
                RootExecutionError(node_id=str(index), error="boom")
                for index in range(MAX_ROOT_ERRORS_PER_RESULT + 1)
            ),
        )

    import ea_node_editor.execution.protocol_codec as protocol

    assert not hasattr(protocol, "RootExecutionError")
    assert not hasattr(protocol, "SettledPortResult")

    transported = event_to_dict(
        NodeSettledEvent(
            run_id="run",
            workspace_id="workspace",
            node_id="node",
            status="completed",
            outputs={"result": result},
        )
    )
    transported["outputs"]["result"]["unexpected"] = True
    with pytest.raises(ValueError, match="unexpected"):
        dict_to_event(transported)


def test_settled_tree_and_output_count_limits(monkeypatch) -> None:  # noqa: ANN001
    from ea_node_editor.runtime_contracts import settled_results

    monkeypatch.setattr(settled_results, "MAX_DATA_TREE_BRANCHES_PER_OUTPUT", 1)
    with pytest.raises(ValueError, match="branch count"):
        SettledPortResult(
            status="value",
            value=DataTree((((0,), (1,)), ((1,), (2,)))),
        )
    raw_tree = {
        "__ea_runtime_value__": "data_tree",
        "branches": [
            {"path": [0], "items": [1]},
            {"path": [1], "items": [2]},
        ],
    }
    with mock.patch.object(settled_results, "deserialize_runtime_value") as decode:
        with pytest.raises(ValueError, match="branch count"):
            SettledPortResult.from_payload(
                {"status": "value", "value": raw_tree, "errors": []}
            )
        decode.assert_not_called()

    monkeypatch.setattr(settled_results, "MAX_DATA_TREE_BRANCHES_PER_OUTPUT", 100)
    monkeypatch.setattr(settled_results, "MAX_DATA_TREE_ITEMS_PER_OUTPUT", 1)
    with pytest.raises(ValueError, match="item count"):
        SettledPortResult(status="value", value=DataTree.from_list((1, 2)))

    with pytest.raises(ValueError, match="maximum count 0"):
        settled_results.normalize_settled_output_mapping(
            {"result": SettledPortResult()}, max_outputs=0
        )

    from ea_node_editor.runtime_contracts import solution_records

    raw_record = _record().to_payload()
    monkeypatch.setattr(solution_records, "MAX_OUTPUTS_PER_NODE", 0)
    with mock.patch.object(SolutionOutputDescriptor, "from_payload") as materialize:
        with pytest.raises(ValueError, match="output_descriptors exceeds"):
            SolutionRecord.from_payload(raw_record)
        materialize.assert_not_called()


def test_prepared_decision_payload_and_frozen_output_semantics() -> None:
    accepted = AcceptedOutputPayload(
        node_id="node",
        record_id="record",
        solution_key=_A,
        settlement_status="completed",
        result_digest=_B,
        residency=SolutionResidency.SESSION,
        runtime_generation=2,
        outputs={
            "result": SettledPortResult(
                status="value", value=DataTree.from_item("cached")
            )
        },
    )
    decision = PreparedNodeDecision(
        node_id="node",
        action=PreparedAction.REUSE,
        reason_code="record_valid",
        solution_key=_A,
        dependency_solution_keys=(_B,),
        accepted_record_id="record",
        accepted_payload_digest=accepted.commitment_digest(),
    )
    assert PreparedNodeDecision.from_payload(decision.to_payload()) == decision
    with pytest.raises(TypeError):
        accepted.outputs["other"] = SettledPortResult()  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        decision.reason_code = "changed"  # type: ignore[misc]

    with pytest.raises(ValueError, match="require accepted_record_id"):
        PreparedNodeDecision(
            node_id="node",
            action=PreparedAction.REUSE,
            reason_code="record_valid",
            solution_key=_A,
            dependency_solution_keys=(),
        )


def test_outputless_completed_and_empty_accepted_payloads_roundtrip() -> None:
    for settlement_status in ("completed", "empty"):
        payload = AcceptedOutputPayload(
            node_id=f"node-{settlement_status}",
            record_id=f"record-{settlement_status}",
            solution_key=_A,
            settlement_status=settlement_status,
            result_digest=_B,
            residency=SolutionResidency.SESSION,
            runtime_generation=1,
            outputs={},
        )
        assert AcceptedOutputPayload.from_payload(payload.to_payload()) == payload


def test_session_carriers_pass_session_and_fail_durable_payloads() -> None:
    handle = RuntimeHandleRef(
        data_type_id=VIEWER_SESSION_DATA_TYPE_ID,
        schema_version=1,
        handle_id="viewer",
        kind=COREX_VIEWER_SESSION_HANDLE_KIND,
        owner_scope="run:viewer",
        worker_generation=1,
    )
    session = AcceptedOutputPayload(
        node_id="node",
        record_id="record",
        solution_key=_A,
        settlement_status="completed",
        result_digest=_B,
        residency=SolutionResidency.SESSION,
        runtime_generation=1,
        outputs={
            "session": SettledPortResult(
                status="value",
                value=DataTree.from_item(handle),
            )
        },
        catalog=_REGISTRY.data_types,
    )
    assert session.decode_outputs(catalog=_REGISTRY.data_types)[
        "session"
    ].value == DataTree.from_item(handle)

    with pytest.raises(ValueError, match="session-only carriers"):
        AcceptedOutputPayload(
            node_id="node",
            record_id="record",
            solution_key=_A,
            settlement_status="completed",
            result_digest=_B,
            residency=SolutionResidency.DURABLE,
            runtime_generation=None,
            outputs={
                "session": SettledPortResult(
                    status="value",
                    value=DataTree.from_item(handle),
                )
            },
            catalog=_REGISTRY.data_types,
        )

    table = TabularDataRef(ref_id="table", resolver_id="session.cache")
    with pytest.raises(ValueError, match="session-only carriers"):
        AcceptedOutputPayload(
            node_id="node",
            record_id="record",
            solution_key=_A,
            settlement_status="completed",
            result_digest=_B,
            residency=SolutionResidency.DURABLE,
            runtime_generation=None,
            outputs={
                "table": SettledPortResult(
                    status="value",
                    value=DataTree.from_item(table),
                )
            },
            catalog=_REGISTRY.data_types,
        )

    with pytest.raises(ValueError, match="require a value result"):
        AcceptedOutputPayload(
            node_id="node",
            record_id="record",
            solution_key=_A,
            settlement_status="completed",
            result_digest=_B,
            residency=SolutionResidency.SESSION,
            runtime_generation=1,
            outputs={"result": SettledPortResult(status="empty")},
        )


def test_prepared_payloads_detach_original_and_decoded_mutable_aliases() -> None:
    envelope, registry, snapshot = _dispatch_envelope()
    envelope_payload = envelope.to_payload(catalog=registry.data_types)

    snapshot.metadata["alias_probe"]["items"].append(2)
    decoded_snapshot = envelope.decode_runtime_snapshot(catalog=registry.data_types)
    decoded_snapshot.metadata["alias_probe"]["items"].append(3)
    decoded_trigger = envelope.decode_trigger(catalog=registry.data_types)
    decoded_trigger["alias_probe"]["items"].append(3)

    assert isinstance(envelope.runtime_snapshot, bytes)
    assert isinstance(envelope.trigger, bytes)
    assert envelope.to_payload(catalog=registry.data_types) == envelope_payload

    nested = {"items": [1]}
    accepted = AcceptedOutputPayload(
        node_id="node",
        record_id="record",
        solution_key=_A,
        settlement_status="completed",
        result_digest=_B,
        residency=SolutionResidency.SESSION,
        runtime_generation=1,
        outputs={
            "result": SettledPortResult(
                status="value",
                value=DataTree.from_item(nested),
            )
        },
    )
    accepted_payload = accepted.to_payload()
    nested["items"].append(2)
    decoded_outputs = accepted.decode_outputs()
    decoded_item = decoded_outputs["result"].value[(0,)][0]
    decoded_item["items"].append(3)

    assert isinstance(accepted.outputs, bytes)
    assert accepted.to_payload() == accepted_payload
    with pytest.raises(ValueError, match="forbid runtime_generation"):
        AcceptedOutputPayload(
            node_id="node",
            record_id="record",
            solution_key=_A,
            settlement_status="completed",
            result_digest=_B,
            residency=SolutionResidency.DURABLE,
            runtime_generation=1,
            outputs={},
        )


def test_complete_prepared_execution_roundtrip_and_cross_binding_rejection(
    monkeypatch,
) -> None:  # noqa: ANN001
    envelope, registry, snapshot = _dispatch_envelope()
    accepted = AcceptedOutputPayload(
        node_id="reuse-node",
        record_id="record",
        solution_key=_A,
        settlement_status="completed",
        result_digest=_C,
        residency=SolutionResidency.SESSION,
        runtime_generation=1,
        outputs={
            "result": SettledPortResult(
                status="value", value=DataTree.from_item("cached")
            )
        },
    )
    reuse = PreparedNodeDecision(
        node_id="reuse-node",
        action=PreparedAction.REUSE,
        reason_code="record_valid",
        solution_key=_A,
        dependency_solution_keys=(),
        accepted_record_id="record",
        accepted_payload_digest=accepted.commitment_digest(),
    )
    execute = PreparedNodeDecision(
        node_id="execute-node",
        action=PreparedAction.EXECUTE,
        reason_code="record_missing",
        solution_key=_B,
        dependency_solution_keys=(_A,),
    )
    prepared = PreparedExecution(
        preparation_id="preparation",
        dispatch_envelope=envelope,
        solution_namespace_id="namespace",
        execution_affecting_workspace_revision=3,
        runtime_snapshot_fingerprint=_A,
        execution_plan_fingerprint=_B,
        registry_contract_fingerprint=envelope.registry_contract_fingerprint,
        workflow_interface_revision=1,
        workflow_interface_digest=_C,
        execution_environment_digest=_A,
        trigger_publication_generations=(),
        node_decisions=(reuse, execute),
        accepted_output_payloads=(accepted,),
        recompute_node_ids=("execute-node",),
        reused_node_ids=("reuse-node",),
    )
    payload = prepared.to_payload(catalog=registry.data_types)
    assert (
        PreparedExecution.from_payload(payload, catalog=registry.data_types).to_payload(
            catalog=registry.data_types
        )
        == payload
    )
    snapshot.metadata["alias_probe"]["items"].append(4)
    prepared.dispatch_envelope.decode_runtime_snapshot(
        catalog=registry.data_types
    ).metadata["alias_probe"]["items"].append(5)
    assert prepared.runtime_snapshot_fingerprint == _A
    assert prepared.to_payload(catalog=registry.data_types) == payload

    raw_cross_key = {
        **payload,
        "node_decisions": [
            dict(payload["node_decisions"][0]),
            {
                **dict(payload["node_decisions"][1]),
                "solution_key": _A,
            },
        ],
    }
    with mock.patch.object(PreparedNodeDecision, "from_payload") as materialize:
        with pytest.raises(ValueError, match="cross-node solution keys"):
            PreparedExecution.from_payload(
                raw_cross_key,
                catalog=registry.data_types,
            )
        materialize.assert_not_called()

    raw_duplicate_record = {
        **payload,
        "accepted_output_payloads": [
            dict(payload["accepted_output_payloads"][0]),
            {
                **dict(payload["accepted_output_payloads"][0]),
                "node_id": "other-node",
                "solution_key": _B,
            },
        ],
    }
    with mock.patch.object(AcceptedOutputPayload, "from_payload") as materialize:
        with pytest.raises(ValueError, match="duplicate record IDs"):
            PreparedExecution.from_payload(
                raw_duplicate_record,
                catalog=registry.data_types,
            )
        materialize.assert_not_called()

    with pytest.raises(ValueError, match="matching reuse decisions"):
        replace(
            prepared,
            node_decisions=(execute,),
            accepted_output_payloads=(accepted,),
            recompute_node_ids=("execute-node",),
            reused_node_ids=(),
        )
    with pytest.raises(ValueError, match="cross-node solution keys"):
        replace(
            prepared,
            node_decisions=(reuse, replace(execute, solution_key=_A)),
        )

    reuse_two = replace(
        reuse,
        node_id="reuse-node-two",
        solution_key=_B,
    )
    accepted_two = replace(
        accepted,
        node_id="reuse-node-two",
        solution_key=_B,
    )
    with pytest.raises(ValueError, match="duplicate record IDs"):
        PreparedExecution(
            preparation_id="duplicate-record",
            dispatch_envelope=envelope,
            solution_namespace_id="namespace",
            execution_affecting_workspace_revision=3,
            runtime_snapshot_fingerprint=_A,
            execution_plan_fingerprint=_B,
            registry_contract_fingerprint=envelope.registry_contract_fingerprint,
            workflow_interface_revision=1,
            workflow_interface_digest=_C,
            execution_environment_digest=_A,
            trigger_publication_generations=(),
            node_decisions=(reuse, reuse_two),
            accepted_output_payloads=(accepted, accepted_two),
            recompute_node_ids=(),
            reused_node_ids=("reuse-node", "reuse-node-two"),
        )

    for unordered in ({_A}, frozenset({_A})):
        with pytest.raises(TypeError, match="must be a list"):
            PreparedNodeDecision(
                node_id="set-sequence",
                action=PreparedAction.EXECUTE,
                reason_code="record_missing",
                solution_key=_C,
                dependency_solution_keys=unordered,  # type: ignore[arg-type]
            )

    from ea_node_editor.execution import prepared_execution as prepared_contracts

    monkeypatch.setattr(prepared_contracts, "MAX_PREPARED_NODES", 1)
    with mock.patch.object(PreparedNodeDecision, "from_payload") as materialize:
        with pytest.raises(ValueError, match="node_decisions exceeds"):
            PreparedExecution.from_payload(payload, catalog=registry.data_types)
        materialize.assert_not_called()
    monkeypatch.setattr(prepared_contracts, "MAX_PREPARED_NODES", 100_000)
    monkeypatch.setattr(
        prepared_contracts, "MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION", 0
    )
    with pytest.raises(ValueError, match="accepted_output_payloads exceeds"):
        PreparedExecution.from_payload(payload, catalog=registry.data_types)
    monkeypatch.setattr(
        prepared_contracts, "MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION", 100_000
    )
    monkeypatch.setattr(
        prepared_contracts, "MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION", 0
    )
    with pytest.raises(ValueError, match="port results exceed"):
        PreparedExecution.from_payload(payload, catalog=registry.data_types)
    monkeypatch.setattr(
        prepared_contracts, "MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION", 1_000_000
    )
    monkeypatch.setattr(prepared_contracts, "MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES", 1)
    with pytest.raises(ValueError, match="maximum encoded size"):
        PreparedExecution.from_payload(payload, catalog=registry.data_types)


def test_invalidation_result_roundtrip_and_unknown_field_rejection() -> None:
    result = InvalidationResult(
        project_id="project",
        workspace_id="workspace",
        solution_revision=4,
        changed_root_node_ids=("root",),
        expired_node_ids=("root", "downstream"),
        removed_node_ids=("deleted",),
        reason_code="property_changed",
    )
    assert InvalidationResult.from_payload(result.to_payload()) == result
    with pytest.raises(ValueError, match="unexpected"):
        InvalidationResult.from_payload({**result.to_payload(), "extra": 1})
    event = SolutionStateChangedEvent.from_invalidation(result)
    assert SolutionStateChangedEvent.from_payload(event.to_payload()) == event
    with pytest.raises(ValueError, match="unexpected"):
        SolutionStateChangedEvent.from_payload({**event.to_payload(), "extra": 1})
    with pytest.raises(ValueError, match="solution_state_changed"):
        SolutionStateChangedEvent.from_payload(
            {**event.to_payload(), "type": "node_settled"}
        )
