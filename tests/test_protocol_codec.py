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
    ObservationInvalidationRequestedEvent,
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


class ProtocolCodecTests(unittest.TestCase):
    def test_start_run_semantic_carrier_round_trips_through_json(self) -> None:
        catalog = _catalog()
        command = StartRunCommand(
            run_id="run_protocol",
            workspace_id="ws_protocol",
            runtime_snapshot=_typed_snapshot(),
        )

        payload = command_to_dict(command, catalog=catalog)
        restored = dict_to_command(
            json.loads(json.dumps(payload)),
            catalog=catalog,
        )

        self.assertEqual(payload["catalog_fingerprint"], catalog.fingerprint())
        self.assertTrue(payload["catalog_revisions"])
        self.assertNotIn("catalog", payload["runtime_snapshot"])
        self.assertNotIn("catalog_revisions", payload["runtime_snapshot"])
        self.assertIsInstance(restored, StartRunCommand)
        self.assertEqual(restored.catalog_fingerprint, catalog.fingerprint())
        artifact = (
            restored.runtime_snapshot.workspace("ws_protocol")
            .nodes[0]
            .properties["value"]
        )
        self.assertIsInstance(artifact, RuntimeArtifactRef)
        self.assertEqual(artifact.data_type_id, PATH_DATA_TYPE_ID)

    def test_matching_fingerprint_treats_valid_revisions_as_diagnostics_only(
        self,
    ) -> None:
        catalog = _semantic_catalog()
        fingerprint, records = catalog_agreement(catalog)
        diagnostic_records = list(records)
        diagnostic_records[0] = replace(
            diagnostic_records[0],
            semantic_digest="0" * 64,
        )

        self.assertEqual(
            catalog_mismatch_message(
                fingerprint,
                tuple(diagnostic_records),
                catalog,
            ),
            "",
        )
        with self.assertRaises(ValueError):
            catalog_mismatch_message(
                fingerprint,
                ({"kind": "type"},),
                catalog,
            )

    def test_malformed_non_start_command_remains_protocol_error_only(self) -> None:
        event_queue: queue.Queue = queue.Queue()

        command = decode_command_payload(
            {
                "type": "open_viewer_session",
                "request_id": "viewer_bad",
                "data_refs": [],
            },
            event_queue=event_queue,
        )

        self.assertIsNone(command)
        events = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())
        self.assertEqual([event["type"] for event in events], ["protocol_error"])
        self.assertEqual(events[0]["request_id"], "viewer_bad")

    def test_protocol_rejects_arbitrary_python_values(self) -> None:
        catalog = _catalog()
        for value in (_UnsupportedDataclass(1), object(), b"bytes", {"set"}):
            with self.subTest(value_type=type(value).__name__):
                command = StartRunCommand(
                    workspace_id="ws_protocol",
                    trigger={"unsafe": value},
                    runtime_snapshot=_typed_snapshot(),
                )
                with self.assertRaises(TypeError):
                    command_to_dict(command, catalog=catalog)

    def test_settlement_and_root_error_use_explicit_adapters(self) -> None:
        catalog = _catalog()
        value_event = NodeSettledEvent(
            run_id="run_protocol",
            workspace_id="ws_protocol",
            node_id="node_protocol",
            outputs={
                "artifact": SettledPortResult(
                    status="value",
                    value=DataTree.from_item(
                        RuntimeArtifactRef.staged(
                            "settled_artifact",
                            data_type_id=PATH_DATA_TYPE_ID,
                            schema_version=1,
                            format="txt",
                            size_bytes=0,
                            sha256="0" * 64,
                            provenance="corex.test.fixture",
                        )
                    ),
                )
            },
        )
        restored_value = dict_to_event(
            event_to_dict(value_event, catalog=catalog),
            catalog=catalog,
        )
        self.assertIsInstance(restored_value, NodeSettledEvent)
        self.assertIsInstance(
            restored_value.outputs["artifact"].value[(0,)][0],
            RuntimeArtifactRef,
        )

        failed_event = NodeSettledEvent(
            node_id="node_protocol",
            status="failed",
            errors=(
                RootExecutionError(
                    node_id="root_node",
                    error="failed",
                    traceback="trace",
                ),
            ),
        )
        restored_failed = dict_to_event(event_to_dict(failed_event))
        self.assertEqual(restored_failed.errors, failed_event.errors)

    def test_observation_invalidation_event_round_trips_with_bounded_identity(self) -> None:
        event = ObservationInvalidationRequestedEvent(
            run_id="run",
            workspace_id="workspace",
            node_id="script",
            root_node_id="open",
            reason_code="mechanical_model_mutated",
        )
        self.assertEqual(dict_to_event(event_to_dict(event)), event)
        with self.assertRaises(ValueError):
            dict_to_event(
                {
                    **event_to_dict(event),
                    "reason_code": "x" * 257,
                }
            )

    def test_query_options_and_strict_composite_fields_round_trip(self) -> None:
        command = QueryViewerSessionCommand(
            request_id="query_protocol",
            workspace_id="ws_protocol",
            node_id="node_protocol",
            session_id="session_protocol",
            query_type="distance",
            payload={"points": [[0, 0, 0], [1, 0, 0]]},
            options={"precision": 4},
        )
        payload = command_to_dict(command)
        restored = dict_to_command(payload)
        self.assertEqual(restored.options, {"precision": 4})

        payload["options"] = "malformed"
        with self.assertRaisesRegex(ValueError, "options must be a dictionary"):
            dict_to_command(payload)

    def test_process_client_fails_before_queue_put(self) -> None:
        client = object.__new__(ProcessExecutionClient)
        client._data_types = _catalog()  # noqa: SLF001
        client._command_queue = _RecordingQueue()  # noqa: SLF001
        client._callbacks = []  # noqa: SLF001
        client._state_lock = threading.Lock()  # noqa: SLF001
        client._active_workspace_id = ""  # noqa: SLF001
        command = StartRunCommand(
            workspace_id="ws_protocol",
            trigger={"unsafe": object()},
            runtime_snapshot=_typed_snapshot(),
        )

        success, _message = client._try_post_command(command)  # noqa: SLF001

        self.assertFalse(success)
        self.assertEqual(client._command_queue.items, [])  # noqa: SLF001

    def test_malformed_outbound_runtime_documents_fail_before_queue_put(
        self,
    ) -> None:
        base = _typed_snapshot()
        workspace = base.workspaces[0]
        node = workspace.nodes[0]
        malformed_snapshots = {
            "schema_version": replace(
                base,
                schema_version="bad",  # type: ignore[arg-type]
            ),
            "node_x": replace(
                base,
                workspaces=(
                    replace(
                        workspace,
                        nodes=(
                            replace(
                                node,
                                x="bad",  # type: ignore[arg-type]
                            ),
                        ),
                    ),
                ),
            ),
            "node_properties": replace(
                base,
                workspaces=(
                    replace(
                        workspace,
                        nodes=(
                            replace(
                                node,
                                properties="bad",  # type: ignore[arg-type]
                            ),
                        ),
                    ),
                ),
            ),
            "edge_input_order": replace(
                base,
                workspaces=(
                    replace(
                        workspace,
                        edges=(
                            RuntimeEdge(
                                source_node_id=node.node_id,
                                source_port_key="value",
                                target_node_id=node.node_id,
                                target_port_key="value",
                                input_order="bad",  # type: ignore[arg-type]
                            ),
                        ),
                    ),
                ),
            ),
            "nested_view_zoom": replace(
                base,
                workspaces=(
                    replace(
                        workspace,
                        document_fields={
                            "workspace_id": "ws_protocol",
                            "views": [
                                {
                                    "view_id": "view",
                                    "zoom": "bad",
                                }
                            ],
                        },
                    ),
                ),
            ),
        }
        client = object.__new__(ProcessExecutionClient)
        client._data_types = _catalog()  # noqa: SLF001
        client._command_queue = _RecordingQueue()  # noqa: SLF001
        client._callbacks = []  # noqa: SLF001
        client._state_lock = threading.Lock()  # noqa: SLF001
        client._active_workspace_id = ""  # noqa: SLF001

        for field_name, snapshot in malformed_snapshots.items():
            command = StartRunCommand(
                run_id=f"run_{field_name}",
                workspace_id="ws_protocol",
                runtime_snapshot=snapshot,
            )
            with self.subTest(field_name=field_name):
                with self.assertRaises((TypeError, ValueError)):
                    command_to_dict(command, catalog=client._data_types)  # noqa: SLF001
                success, _message = client._try_post_command(command)  # noqa: SLF001
                self.assertFalse(success)
                self.assertEqual(client._command_queue.items, [])  # noqa: SLF001

    def test_external_client_fails_before_stdin_write(self) -> None:
        client = object.__new__(ExternalPythonExecutionClient)
        process = _RunningExternalProcess()
        client._data_types = _catalog()  # noqa: SLF001
        client._process = process  # noqa: SLF001
        client._stdin_lock = threading.Lock()  # noqa: SLF001
        client._callbacks = []  # noqa: SLF001
        client._state_lock = threading.Lock()  # noqa: SLF001
        client._active_workspace_id = ""  # noqa: SLF001
        command = StartRunCommand(
            workspace_id="ws_protocol",
            trigger={"unsafe": object()},
            runtime_snapshot=_typed_snapshot(),
        )

        success, _message = client._try_post_command(command)  # noqa: SLF001

        self.assertFalse(success)
        self.assertEqual(process.stdin.writes, [])
        self.assertEqual(process.stdin.flush_count, 0)

    def test_trusted_client_fails_before_run_thread_start(self) -> None:
        client = TrustedInProcessExecutionClient()
        try:
            run_id = client.start_run(
                "",
                "ws_protocol",
                {
                    "runtime_snapshot": _typed_snapshot(),
                    "unsafe": object(),
                },
                data_types=_catalog(),
            )

            self.assertEqual(run_id, "")
            self.assertIsNone(client._run_thread)  # noqa: SLF001
        finally:
            client.shutdown()

    def test_worker_event_fails_before_queue_put(self) -> None:
        event_queue = _RecordingQueue()
        event = NodeSettledEvent(
            outputs={
                "artifact": SettledPortResult(
                    status="value",
                    value=DataTree.from_item(
                        RuntimeArtifactRef.staged(
                            "event_artifact",
                            data_type_id=PATH_DATA_TYPE_ID,
                            schema_version=1,
                            format="txt",
                            size_bytes=0,
                            sha256="0" * 64,
                            provenance="corex.test.fixture",
                        )
                    ),
                )
            }
        )

        with self.assertRaisesRegex(ValueError, "active data-type catalog"):
            emit(event_queue, event)
        self.assertEqual(event_queue.items, [])

    def test_runtime_snapshot_rejects_present_malformed_full_schema_fields(
        self,
    ) -> None:
        catalog = _catalog()
        payload = command_to_dict(
            StartRunCommand(
                run_id="run_schema",
                workspace_id="ws_protocol",
                runtime_snapshot=_typed_snapshot(),
            ),
            catalog=catalog,
        )
        workspace = payload["runtime_snapshot"]["workspaces"][0]
        workspace["document_fields"].update(
            {
                "name": "Workspace",
                "dirty": False,
                "active_view_id": "view",
                "views": [
                    {
                        "view_id": "view",
                        "name": "View",
                        "zoom": 1.0,
                        "pan_x": 0.0,
                        "pan_y": 0.0,
                        "scope_path": [],
                    }
                ],
            }
        )
        workspace["edges"] = [
            {
                "edge_id": "edge",
                "source_node_id": "node_protocol",
                "source_port_key": "value",
                "target_node_id": "node_protocol",
                "target_port_key": "value",
                "enabled": True,
                "input_order": 0,
                "label": "",
                "visual_style": {},
            }
        ]

        malformed_paths = (
            (("runtime_snapshot", "schema_version"), "bad"),
            (("runtime_snapshot", "metadata"), "bad"),
            (("runtime_snapshot", "workspace_order"), "bad"),
            (("runtime_snapshot", "workspace_order", 0), 42),
            (("runtime_snapshot", "workspaces", 0, "document_fields"), "bad"),
            (
                (
                    "runtime_snapshot",
                    "workspaces",
                    0,
                    "document_fields",
                    "dirty",
                ),
                "bad",
            ),
            (
                (
                    "runtime_snapshot",
                    "workspaces",
                    0,
                    "document_fields",
                    "views",
                ),
                "bad",
            ),
            (
                (
                    "runtime_snapshot",
                    "workspaces",
                    0,
                    "document_fields",
                    "views",
                    0,
                    "zoom",
                ),
                "bad",
            ),
            (
                (
                    "runtime_snapshot",
                    "workspaces",
                    0,
                    "document_fields",
                    "views",
                    0,
                    "scope_path",
                ),
                "bad",
            ),
            (
                ("runtime_snapshot", "workspaces", 0, "nodes", 0, "properties"),
                "bad",
            ),
            (
                ("runtime_snapshot", "workspaces", 0, "nodes", 0, "x"),
                "bad",
            ),
            (
                ("runtime_snapshot", "workspaces", 0, "nodes", 0, "collapsed"),
                1,
            ),
            (
                (
                    "runtime_snapshot",
                    "workspaces",
                    0,
                    "nodes",
                    0,
                    "exposed_ports",
                ),
                "bad",
            ),
            (
                (
                    "runtime_snapshot",
                    "workspaces",
                    0,
                    "nodes",
                    0,
                    "port_labels",
                ),
                "bad",
            ),
            (
                (
                    "runtime_snapshot",
                    "workspaces",
                    0,
                    "nodes",
                    0,
                    "port_modifiers",
                ),
                {"value": "bad"},
            ),
            (
                (
                    "runtime_snapshot",
                    "workspaces",
                    0,
                    "nodes",
                    0,
                    "visual_style",
                ),
                "bad",
            ),
            (
                (
                    "runtime_snapshot",
                    "workspaces",
                    0,
                    "nodes",
                    0,
                    "custom_width",
                ),
                "bad",
            ),
            (
                ("runtime_snapshot", "workspaces", 0, "edges", 0, "enabled"),
                "bad",
            ),
            (
                ("runtime_snapshot", "workspaces", 0, "edges", 0, "input_order"),
                "bad",
            ),
            (
                (
                    "runtime_snapshot",
                    "workspaces",
                    0,
                    "edges",
                    0,
                    "visual_style",
                ),
                "bad",
            ),
        )

        for path, malformed_value in malformed_paths:
            with self.subTest(path=path):
                malformed = copy.deepcopy(payload)
                target = malformed
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = malformed_value
                with self.assertRaises((TypeError, ValueError)):
                    dict_to_command(malformed, catalog=catalog)

    def test_protocol_rejects_present_malformed_dto_fields(self) -> None:
        catalog = _catalog()
        start_payload = command_to_dict(
            StartRunCommand(
                run_id="run_schema",
                workspace_id="ws_protocol",
                runtime_snapshot=_typed_snapshot(),
            ),
            catalog=catalog,
        )
        start_cases = {
            "trigger": "bad",
            "execution_backend": "bad",
            "target_node_ids": 42,
            "trigger_publications": [],
            "trigger_captures": [],
            "clicked_trigger_node_id": 42,
            "developer_mode": "bad",
        }
        for field_name, malformed_value in start_cases.items():
            with self.subTest(command_field=field_name):
                malformed = copy.deepcopy(start_payload)
                malformed[field_name] = malformed_value
                with self.assertRaises((TypeError, ValueError)):
                    dict_to_command(malformed, catalog=catalog)

        command_payload = command_to_dict(
            OpenViewerSessionCommand(
                request_id="viewer",
                workspace_id="ws_protocol",
                node_id="node_protocol",
            )
        )
        for field_name, malformed_value in {
            "request_id": 42,
            "transport_revision": "bad",
            "live_open_status": 42,
            "data_refs": [],
        }.items():
            with self.subTest(viewer_command_field=field_name):
                malformed = copy.deepcopy(command_payload)
                malformed[field_name] = malformed_value
                with self.assertRaises((TypeError, ValueError)):
                    dict_to_command(malformed)

        event_cases = (
            (
                {
                    "type": "node_started",
                    "started_at_epoch_ms": "bad",
                },
                "started_at_epoch_ms",
            ),
            (
                {
                    "type": "node_settled",
                    "elapsed_ms": "bad",
                    "outputs": {},
                    "errors": [],
                    "warnings": [],
                },
                "elapsed_ms",
            ),
            (
                {
                    "type": "node_settled",
                    "outputs": {},
                    "errors": [],
                    "warnings": 42,
                },
                "warnings",
            ),
            (
                {
                    "type": "node_settled",
                    "outputs": {},
                    "errors": 42,
                    "warnings": [],
                },
                "errors",
            ),
            (
                {
                    "type": "run_failed",
                    "fatal": "bad",
                },
                "fatal",
            ),
            (
                {
                    "type": "viewer_query_result",
                    "supported": "bad",
                    "value": {},
                },
                "supported",
            ),
        )
        for malformed, field_name in event_cases:
            with self.subTest(event_field=field_name):
                with self.assertRaises((TypeError, ValueError)):
                    dict_to_event(malformed)

        with self.assertRaises((TypeError, ValueError)):
            command_to_dict(
                OpenViewerSessionCommand(
                    transport_revision="bad",  # type: ignore[arg-type]
                )
            )
        with self.assertRaises((TypeError, ValueError)):
            event_to_dict(
                NodeSettledEvent(
                    elapsed_ms="bad",  # type: ignore[arg-type]
                )
            )
        with self.assertRaises((TypeError, ValueError)):
            event_to_dict(
                NodeSettledEvent(
                    warnings=42,  # type: ignore[arg-type]
                )
            )

    def test_protocol_missing_optional_fields_keep_defaults(self) -> None:
        catalog = _catalog()
        payload = command_to_dict(
            StartRunCommand(
                run_id="run_defaults",
                workspace_id="ws_protocol",
                runtime_snapshot=_typed_snapshot(),
            ),
            catalog=catalog,
        )
        for field_name in (
            "trigger",
            "execution_backend",
            "target_node_ids",
            "trigger_publications",
            "trigger_captures",
            "clicked_trigger_node_id",
            "developer_mode",
        ):
            payload.pop(field_name)
        restored = dict_to_command(payload, catalog=catalog)
        self.assertEqual(restored.trigger, {})
        self.assertEqual(restored.target_node_ids, ())
        self.assertEqual(restored.trigger_publications, {})
        self.assertEqual(restored.trigger_captures, {})
        self.assertFalse(restored.developer_mode)

        settled = dict_to_event({"type": "node_settled"})
        self.assertEqual(settled.elapsed_ms, 0.0)
        self.assertEqual(settled.outputs, {})
        self.assertEqual(settled.errors, ())
        self.assertEqual(settled.warnings, ())

    def test_runtime_node_optional_dimensions_preserve_none_and_require_numbers(
        self,
    ) -> None:
        required_fields = {
            "node_id": "node_dimensions",
            "type_id": "core.constant",
        }
        node = RuntimeNode.from_mapping(required_fields)
        self.assertIsNotNone(node)
        assert node is not None
        self.assertIsNone(node.custom_width)
        self.assertIsNone(node.custom_height)

        for field_name in ("custom_width", "custom_height"):
            for numeric_value in (0, 24, 24.5):
                with self.subTest(field_name=field_name, value=numeric_value):
                    numeric_node = RuntimeNode.from_mapping(
                        {
                            **required_fields,
                            field_name: numeric_value,
                        }
                    )
                    self.assertIsNotNone(numeric_node)
                    assert numeric_node is not None
                    self.assertEqual(
                        getattr(numeric_node, field_name),
                        float(numeric_value),
                    )
            for malformed_value in (True, "24", float("nan"), float("inf")):
                with self.subTest(field_name=field_name, value=malformed_value):
                    with self.assertRaises(ValueError):
                        RuntimeNode.from_mapping(
                            {
                                **required_fields,
                                field_name: malformed_value,
                            }
                        )
