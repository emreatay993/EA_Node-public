from __future__ import annotations

import copy
import io
import json
import queue
import threading
import time
import unittest
from dataclasses import dataclass, replace
from unittest.mock import patch

from ea_node_editor.execution.external_python_client import ExternalPythonExecutionClient
from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.trusted_client import TrustedInProcessExecutionClient
from ea_node_editor.execution.run_messages import (
    CancelRunPreflightCommand,
    CommitRunPreflightCommand,
    NodeSettledEvent,
    ProtocolErrorEvent,
    RunCompletedEvent,
    RunFailedEvent,
    RunPreflightAcceptedEvent,
    RunStateEvent,
    RunStoppedEvent,
    ShutdownCommand,
    StartRunCommand,
)
from ea_node_editor.execution.registry_agreement import (
    CatalogRevisionRecord,
    catalog_agreement,
    catalog_mismatch_message,
    normalize_catalog_revisions,
)
from ea_node_editor.execution.viewer_messages import (
    OpenViewerSessionCommand,
    QueryViewerSessionCommand,
    viewer_epoch_snapshot_digest,
)
from ea_node_editor.execution.protocol_codec import (
    command_to_dict,
    dict_to_command,
    dict_to_event,
    event_to_dict,
)
from ea_node_editor.execution.prepared_execution import (
    AcceptedOutputPayload,
    PreparedAction,
    PreparedNodeDecision,
)
from ea_node_editor.runtime_contracts.settled_results import (
    RootExecutionError,
    SettledPortResult,
)
from ea_node_editor.execution.runtime_dto import (
    RuntimeEdge,
    RuntimeNode,
    RuntimeWorkspace,
)
from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot
from ea_node_editor.execution.stdio_worker import main as stdio_worker_main
from ea_node_editor.execution.worker_protocol import decode_command_payload, emit
from ea_node_editor.execution.worker_runner import RunControl
from ea_node_editor.execution.worker_runtime import (
    DEFAULT_RUNTIME_PREPARATION_CACHE,
)
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.runtime_contracts import (
    ArrayDataRef,
    DataConversionSpec,
    DataTypeCatalog,
    DataTypeFamilySpec,
    DataTypeSpec,
    DataTree,
    Interval1D,
    PATH_DATA_TYPE_ID,
    RuntimeArtifactRef,
    TabularDataRef,
)
from ea_node_editor.runtime_contracts.data_types import MAX_PAYLOAD_SCHEMA_VERSION
from ea_node_editor.runtime_contracts.solution_records import SolutionResidency


@dataclass
class _UnsupportedDataclass:
    value: int


class _RecordingQueue:
    def __init__(self) -> None:
        self.items: list[object] = []

    def put(self, value: object) -> None:
        self.items.append(value)


class _RecordingStdin:
    def __init__(self) -> None:
        self.writes: list[str] = []
        self.flush_count = 0

    def write(self, value: str) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        self.flush_count += 1


class _RunningExternalProcess:
    def __init__(self) -> None:
        self.stdin = _RecordingStdin()

    @staticmethod
    def poll() -> None:
        return None


class _TrackingWorkerServices(WorkerServices):
    def __init__(self) -> None:
        super().__init__()
        self.bound_catalogs = []

    def bind_data_types(self, data_types) -> None:  # noqa: ANN001
        self.bound_catalogs.append(data_types)
        super().bind_data_types(data_types)


def _catalog():
    return build_default_registry().data_types


def _revision_catalog(implementation_version: str) -> DataTypeCatalog:
    catalog = DataTypeCatalog()
    catalog.register_many(
        families=(
            DataTypeFamilySpec("tests.catalog", "Catalog", "data.tests", "tests"),
        ),
        types=(
            DataTypeSpec(
                "tests.CatalogValue",
                "Catalog Value",
                "tests.catalog",
                lambda value: isinstance(value, str),
                implementation_version=implementation_version,
            ),
        ),
        owner_id="tests.catalog",
        owner_version=implementation_version,
    )
    catalog.freeze()
    return catalog


def _semantic_catalog(
    *,
    family_display_name: str = "Catalog",
    capabilities: frozenset[str] = frozenset(),
    source_label: str = "",
) -> DataTypeCatalog:
    catalog = DataTypeCatalog()
    catalog.register_many(
        families=(
            DataTypeFamilySpec(
                "tests.catalog",
                family_display_name,
                "data.tests",
                "tests",
            ),
        ),
        types=(
            DataTypeSpec(
                "tests.CatalogValue",
                "Catalog Value",
                "tests.catalog",
                lambda value: isinstance(value, str),
                capabilities=capabilities,
                implementation_version="1",
            ),
            DataTypeSpec(
                "tests.CatalogText",
                "Catalog Text",
                "tests.catalog",
                lambda value: isinstance(value, str),
                implementation_version="1",
            ),
        ),
        conversions=(
            DataConversionSpec(
                "tests.CatalogValue",
                "tests.CatalogText",
                str,
                implementation_version="1",
            ),
        ),
        owner_id="tests.catalog",
        owner_version="1",
        source_label=source_label,
    )
    catalog.freeze()
    return catalog


def _typed_snapshot() -> RuntimeSnapshot:
    artifact = RuntimeArtifactRef.staged(
        "protocol_artifact",
        data_type_id=PATH_DATA_TYPE_ID,
        schema_version=1,
        format="txt",
        size_bytes=0,
        sha256="0" * 64,
        provenance="corex.test.fixture",
    )
    return RuntimeSnapshot(
        schema_version=1,
        active_workspace_id="ws_protocol",
        workspace_order=("ws_protocol",),
        workspaces=(
            RuntimeWorkspace(
                document_fields={"workspace_id": "ws_protocol"},
                nodes=(
                    RuntimeNode(
                        node_id="node_protocol",
                        type_id="core.constant",
                        title="Protocol",
                        x=0.0,
                        y=0.0,
                        properties={"value": artifact},
                    ),
                ),
            ),
        ),
    )


class RunMessageTests(unittest.TestCase):
    def test_prepared_start_roundtrip_and_legacy_prepared_field_rejection(self) -> None:
        catalog = _catalog()
        accepted = AcceptedOutputPayload(
            node_id="node_protocol",
            record_id="record_protocol",
            solution_key="a" * 64,
            settlement_status="completed",
            result_digest="b" * 64,
            residency=SolutionResidency.SESSION,
            runtime_generation=7,
            outputs={
                "value": SettledPortResult(
                    status="value",
                    value=DataTree.from_item("cached"),
                )
            },
            catalog=catalog,
        )
        decision = PreparedNodeDecision(
            node_id="node_protocol",
            action=PreparedAction.REUSE,
            reason_code="reusable_record_accepted",
            solution_key="a" * 64,
            dependency_solution_keys=(),
            accepted_record_id="record_protocol",
            accepted_payload_digest=accepted.commitment_digest(),
        )
        command = StartRunCommand(
            run_id="run_prepared",
            workspace_id="ws_protocol",
            runtime_snapshot=_typed_snapshot(),
            preparation_id="preparation_protocol",
            solution_namespace_id="namespace_protocol",
            execution_affecting_workspace_revision=3,
            dispatch_runtime_generation=7,
            runtime_snapshot_fingerprint="c" * 64,
            execution_plan_fingerprint="d" * 64,
            workflow_interface_revision=1,
            workflow_interface_digest="e" * 64,
            execution_environment_digest="f" * 64,
            trigger_publication_generations=(("trigger", 2),),
            node_decisions=(decision,),
            accepted_output_payloads=(accepted,),
            viewer_invalidation_node_ids=(),
            viewer_invalidation_reservation_id="viewer_inv_protocol",
            viewer_epoch_snapshot_digest=viewer_epoch_snapshot_digest(
                workspace_id="ws_protocol",
                node_ids=(),
                workspace_epoch=0,
                node_epochs=(),
            ),
        )
        payload = command_to_dict(command, catalog=catalog)
        restored = dict_to_command(json.loads(json.dumps(payload)), catalog=catalog)
        self.assertEqual(command_to_dict(restored, catalog=catalog), payload)
        self.assertEqual(restored.preparation_id, command.preparation_id)
        self.assertEqual(restored.viewer_invalidation_node_ids, ())
        self.assertEqual(
            restored.viewer_epoch_snapshot_digest,
            command.viewer_epoch_snapshot_digest,
        )
        self.assertEqual(restored.node_decisions, command.node_decisions)
        self.assertEqual(
            restored.accepted_output_payloads[0].to_payload(catalog=catalog),
            accepted.to_payload(catalog=catalog),
        )
        clients = (
            ProcessExecutionClient(),
            ExternalPythonExecutionClient(),
            TrustedInProcessExecutionClient(),
        )
        try:
            for client in clients:
                client._data_types = catalog  # noqa: SLF001
                transported = client._decode_command(  # noqa: SLF001
                    client._encode_command(command)  # noqa: SLF001
                )
                self.assertEqual(transported.preparation_id, command.preparation_id)
                self.assertEqual(transported.node_decisions, command.node_decisions)
                self.assertEqual(
                    transported.accepted_output_payloads[0].to_payload(catalog=catalog),
                    accepted.to_payload(catalog=catalog),
                )
        finally:
            for client in clients:
                client.shutdown()

        for mutate in (
            lambda value: value.pop("solution_namespace_id"),
            lambda value: value.__setitem__("dispatch_runtime_generation", 8),
            lambda value: value.__setitem__("preparation_id", ""),
            lambda value: value.__setitem__("viewer_epoch_snapshot_digest", "0" * 64),
        ):
            malformed = copy.deepcopy(payload)
            mutate(malformed)
            with self.assertRaises(ValueError):
                dict_to_command(malformed, catalog=catalog)

    def test_run_preflight_acknowledgments_round_trip_exact_identity(self) -> None:
        digest = "a" * 64
        for command in (
            CommitRunPreflightCommand(
                run_id="run_preflight",
                viewer_invalidation_reservation_id="viewer_inv_preflight",
                viewer_epoch_snapshot_digest=digest,
            ),
            CancelRunPreflightCommand(
                run_id="run_preflight",
                viewer_invalidation_reservation_id="viewer_inv_preflight",
                viewer_epoch_snapshot_digest=digest,
            ),
        ):
            self.assertEqual(dict_to_command(command_to_dict(command)), command)
        event = RunPreflightAcceptedEvent(
            run_id="run_preflight",
            workspace_id="ws_preflight",
            preparation_id="prepared_preflight",
            viewer_invalidation_reservation_id="viewer_inv_preflight",
            viewer_epoch_snapshot_digest=digest,
        )
        self.assertEqual(dict_to_event(event_to_dict(event)), event)

    def test_solution_settlement_identity_combinations_are_strict(self) -> None:
        reused = NodeSettledEvent(
            run_id="run",
            workspace_id="ws",
            node_id="node",
            status="empty",
            disposition="reused",
            decision_reason="reusable_record_accepted",
            solution_key="a" * 64,
            record_id="record",
            residency="session",
        )
        self.assertEqual(
            dict_to_event(event_to_dict(reused)),
            reused,
        )
        invalid = (
            replace(reused, status="failed"),
            replace(reused, record_id=""),
            replace(reused, disposition="recomputed"),
            replace(
                reused,
                disposition="skipped",
                status="completed",
                record_id="",
                residency="",
            ),
            replace(
                reused,
                disposition="blocked",
                status="empty",
                record_id="",
                residency="",
            ),
        )
        for event in invalid:
            with self.assertRaises(ValueError):
                event_to_dict(event)

    def test_legacy_start_requires_exact_prepared_field_default_types(self) -> None:
        catalog = _catalog()
        payload = command_to_dict(
            StartRunCommand(
                run_id="legacy",
                workspace_id="ws_protocol",
                runtime_snapshot=_typed_snapshot(),
            ),
            catalog=catalog,
        )
        self.assertIsInstance(
            dict_to_command(payload, catalog=catalog), StartRunCommand
        )
        text_fields = (
            "preparation_id",
            "solution_namespace_id",
            "runtime_snapshot_fingerprint",
            "execution_plan_fingerprint",
            "workflow_interface_digest",
            "execution_environment_digest",
        )
        sequence_fields = (
            "trigger_publication_generations",
            "node_decisions",
            "accepted_output_payloads",
        )
        integer_fields = (
            "execution_affecting_workspace_revision",
            "dispatch_runtime_generation",
            "workflow_interface_revision",
        )
        for field_name in text_fields:
            for invalid in (None, False, 0):
                malformed = copy.deepcopy(payload)
                malformed[field_name] = invalid
                with self.assertRaises((TypeError, ValueError)):
                    dict_to_command(malformed, catalog=catalog)
        for field_name in sequence_fields:
            for invalid in (None, False, 0):
                malformed = copy.deepcopy(payload)
                malformed[field_name] = invalid
                with self.assertRaises((TypeError, ValueError)):
                    dict_to_command(malformed, catalog=catalog)
        for field_name in integer_fields:
            for invalid in (None, False, "0"):
                malformed = copy.deepcopy(payload)
                malformed[field_name] = invalid
                with self.assertRaises((TypeError, ValueError)):
                    dict_to_command(malformed, catalog=catalog)

    def test_run_lifecycle_states_are_literal_validated_in_both_directions(
        self,
    ) -> None:
        for state in ("ready", "running", "paused", "error"):
            with self.subTest(run_state=state):
                restored = dict_to_event({"type": "run_state", "state": state})
                self.assertEqual(restored.state, state)
                self.assertEqual(
                    dict_to_event(event_to_dict(RunStateEvent(state=state))).state,
                    state,
                )

        for transition in ("", "start", "pause", "resume", "stop", "complete", "fail"):
            with self.subTest(run_transition=transition):
                restored = dict_to_event(
                    {
                        "type": "run_state",
                        "transition": transition,
                    }
                )
                self.assertEqual(restored.transition, transition)

        for field_name, malformed_value in (
            ("state", 42),
            ("state", []),
            ("state", "bogus"),
            ("transition", 42),
            ("transition", []),
            ("transition", "bogus"),
        ):
            with self.subTest(field_name=field_name, value=malformed_value):
                with self.assertRaises((TypeError, ValueError)):
                    dict_to_event(
                        {
                            "type": "run_state",
                            field_name: malformed_value,
                        }
                    )

        fixed_events = (
            ("run_completed", "ready", RunCompletedEvent),
            ("run_failed", "error", RunFailedEvent),
            ("run_stopped", "ready", RunStoppedEvent),
        )
        for event_type, expected_state, event_class in fixed_events:
            with self.subTest(event_type=event_type, state="missing"):
                self.assertEqual(
                    dict_to_event({"type": event_type}).state,
                    expected_state,
                )
            with self.subTest(event_type=event_type, state="expected"):
                self.assertEqual(
                    dict_to_event(
                        {
                            "type": event_type,
                            "state": expected_state,
                        }
                    ).state,
                    expected_state,
                )
                self.assertEqual(
                    dict_to_event(event_to_dict(event_class())).state,
                    expected_state,
                )
            for malformed_value in (42, [], "bad", "bogus"):
                with self.subTest(
                    event_type=event_type,
                    malformed_state=malformed_value,
                ):
                    with self.assertRaises((TypeError, ValueError)):
                        dict_to_event(
                            {
                                "type": event_type,
                                "state": malformed_value,
                            }
                        )

        malformed_outbound_events = (
            RunStateEvent(state=42),  # type: ignore[arg-type]
            RunStateEvent(state="bogus"),  # type: ignore[arg-type]
            RunStateEvent(transition=[]),  # type: ignore[arg-type]
            RunStateEvent(transition="bogus"),
            RunCompletedEvent(state=42),  # type: ignore[arg-type]
            RunCompletedEvent(state="bad"),  # type: ignore[arg-type]
            RunFailedEvent(state=[]),  # type: ignore[arg-type]
            RunFailedEvent(state="bad"),  # type: ignore[arg-type]
            RunStoppedEvent(state=42),  # type: ignore[arg-type]
            RunStoppedEvent(state="bad"),  # type: ignore[arg-type]
        )
        for event in malformed_outbound_events:
            with self.subTest(event=event):
                with self.assertRaises((TypeError, ValueError)):
                    event_to_dict(event)

    def test_active_stdio_rejects_duplicate_start_before_registry_rebind(self) -> None:
        registry = build_default_registry()
        catalog = registry.data_types
        DEFAULT_RUNTIME_PREPARATION_CACHE.clear()
        first = command_to_dict(
            StartRunCommand(
                run_id="run_a",
                workspace_id="ws_protocol",
                runtime_snapshot=_typed_snapshot(),
                registry_contract_fingerprint=registry.contract_fingerprint(),
                addon_runtime_config=registry.addon_runtime_config(),
            ),
            catalog=catalog,
        )
        second = copy.deepcopy(first)
        second["run_id"] = "run_b"
        second["runtime_snapshot"]["workspaces"][0]["nodes"][0]["type_id"] = "math.add"
        input_stream = io.StringIO(json.dumps(first) + "\n" + json.dumps(second) + "\n")
        output_stream = io.StringIO()
        services = _TrackingWorkerServices()

        def hold_active_run(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
            time.sleep(0.2)

        with (
            patch(
                "ea_node_editor.execution.stdio_worker.WorkerServices",
                return_value=services,
            ),
            patch(
                "ea_node_editor.execution.stdio_worker._run_workflow_thread",
                side_effect=hold_active_run,
            ),
        ):
            self.assertEqual(stdio_worker_main(input_stream, output_stream), 0)

        self.assertEqual(len(services.bound_catalogs), 1)
        events = [
            json.loads(line)
            for line in output_stream.getvalue().splitlines()
            if line.strip()
        ]
        self.assertTrue(
            any(
                event.get("type") == "protocol_error"
                and "active run" in str(event.get("error", ""))
                for event in events
            )
        )

    def test_active_run_control_rejects_raw_start_before_decode(self) -> None:
        command_queue: queue.Queue = queue.Queue()
        event_queue: queue.Queue = queue.Queue()
        command_queue.put(
            {
                "type": "start_run",
                "run_id": "run_b",
                "workspace_id": "ws_b",
                "runtime_snapshot": {"properties": "bad"},
            }
        )
        control = RunControl(
            command_queue,
            event_queue,
            run_id="run_a",
            workspace_id="ws_a",
            data_types=_catalog(),
        )

        with patch(
            "ea_node_editor.execution.worker_runner.decode_command_payload"
        ) as decode:
            control.poll_commands()

        decode.assert_not_called()
        event = event_queue.get_nowait()
        self.assertEqual(event["type"], "protocol_error")
        self.assertIn("active run", event["error"])
