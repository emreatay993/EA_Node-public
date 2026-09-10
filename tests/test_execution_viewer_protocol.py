from __future__ import annotations

import unittest
from dataclasses import replace

from ea_node_editor.execution.viewer_messages import (
    CloseViewerSessionCommand,
    MaterializeViewerDataCommand,
    OpenViewerSessionCommand,
    QueryViewerSessionCommand,
    ViewerDataMaterializedEvent,
    ViewerQueryResultEvent,
    ViewerSessionClosedEvent,
    ViewerSessionFailedEvent,
    ViewerSessionOpenedEvent,
    ViewerSessionUpdatedEvent,
    UpdateViewerSessionCommand,
)
from ea_node_editor.execution.run_messages import (
    ProtocolErrorEvent,
)
from ea_node_editor.execution.protocol_codec import (
    command_to_dict,
    dict_to_command,
    dict_to_event,
    event_to_dict,
)
from ea_node_editor.runtime_contracts.value_refs import (
    RuntimeArtifactRef,
    RuntimeHandleRef,
)
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.common.scene_protocol import (
    COREX_SCENE_HANDLE_KIND,
    ENGINEERING_VIEWER_BACKEND_ID,
)
from ea_node_editor.runtime_contracts import ENGINEERING_SCENE_DATA_TYPE_ID, PATH_DATA_TYPE_ID


class _FakeViewerObject:
    pass


class ViewerExecutionProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = build_default_registry().data_types

    def test_viewer_command_family_round_trips_runtime_refs_and_options(self) -> None:
        shared_handle = RuntimeHandleRef(
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            schema_version=1,
            handle_id="viewer_dataset_001",
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="workspace:ws_main",
            worker_generation=5,
            metadata={"array_names": ["U"]},
        )
        preview_artifact = RuntimeArtifactRef.managed(
            "viewer_preview_png",
            data_type_id=PATH_DATA_TYPE_ID,
            schema_version=1,
            format="png",
            size_bytes=0,
            sha256="0" * 64,
            provenance="corex.test.fixture",
        )

        commands = [
            OpenViewerSessionCommand(
                request_id="viewer_req_open",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_existing",
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                data_refs={
                    "dataset": shared_handle,
                    "preview": preview_artifact,
                },
                transport={
                    "kind": "scene_transport",
                    "version": 1,
                    "data_refs": {"dataset": shared_handle},
                },
                transport_revision=3,
                live_open_status="ready",
                camera_state={"position": [1.0, 2.0, 3.0]},
                playback_state={"state": "paused", "step_index": 1},
                summary={"result_name": "displacement", "set_ids": [1, 2]},
                options={"live_mode": "proxy"},
            ),
            UpdateViewerSessionCommand(
                request_id="viewer_req_update",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_existing",
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                data_refs={"dataset": shared_handle},
                transport={
                    "kind": "scene_transport",
                    "version": 1,
                    "data_refs": {"dataset": shared_handle},
                },
                transport_revision=4,
                live_open_status="blocked",
                live_open_blocker={"code": "rerun_required"},
                camera_state={"position": [1.0, 2.0, 3.0]},
                playback_state={"state": "playing", "step_index": 2},
                summary={"camera": {"position": [1.0, 2.0, 3.0]}},
                options={"selection": {"set_ids": [2]}},
            ),
            CloseViewerSessionCommand(
                request_id="viewer_req_close",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_existing",
                options={"reason": "node_hidden"},
            ),
            MaterializeViewerDataCommand(
                request_id="viewer_req_materialize",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_existing",
                options={"output_profile": "both", "export_formats": ["png", "vtm"]},
            ),
            QueryViewerSessionCommand(
                request_id="viewer_req_query",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_existing",
                backend_id="corex_scene",
                query_type="distance",
                payload={"point_a": [0, 0, 0], "point_b": [3, 4, 0]},
                options={"precision": 3},
            ),
        ]
        commands = [
            replace(
                command,
                workspace_invalidation_epoch=3,
                node_invalidation_epoch=5,
            )
            for command in commands
        ]

        for command in commands:
            with self.subTest(command_type=command.type):
                payload = command_to_dict(command, catalog=self.catalog)
                self.assertEqual(payload["type"], command.type)
                self.assertEqual(payload["request_id"], command.request_id)
                self.assertEqual(payload["workspace_id"], "ws_main")
                self.assertEqual(payload["node_id"], "node_viewer")
                self.assertEqual(payload["session_id"], "session_existing")
                self.assertEqual(payload["workspace_invalidation_epoch"], 3)
                self.assertEqual(payload["node_invalidation_epoch"], 5)

                if "data_refs" in payload:
                    self.assertEqual(
                        payload["data_refs"].get("dataset"),
                        {
                            "__ea_runtime_value__": "handle_ref",
                            "data_type_id": ENGINEERING_SCENE_DATA_TYPE_ID,
                            "schema_version": 1,
                            "handle_id": "viewer_dataset_001",
                            "kind": COREX_SCENE_HANDLE_KIND,
                            "owner_scope": "workspace:ws_main",
                            "worker_generation": 5,
                            "metadata": {"array_names": ["U"]},
                        },
                    )
                    self.assertEqual(payload["backend_id"], ENGINEERING_VIEWER_BACKEND_ID)
                    self.assertIn("transport", payload)
                    self.assertIn("transport_revision", payload)
                    self.assertIn("live_open_status", payload)
                    self.assertIn("camera_state", payload)
                    self.assertIn("playback_state", payload)

                restored = dict_to_command(payload, catalog=self.catalog)
                self.assertIsInstance(restored, type(command))
                self.assertEqual(restored.request_id, command.request_id)
                self.assertEqual(restored.workspace_id, command.workspace_id)
                self.assertEqual(restored.node_id, command.node_id)
                self.assertEqual(restored.session_id, command.session_id)
                self.assertEqual(restored.workspace_invalidation_epoch, 3)
                self.assertEqual(restored.node_invalidation_epoch, 5)

                if isinstance(
                    restored, (OpenViewerSessionCommand, UpdateViewerSessionCommand)
                ):
                    self.assertIsInstance(
                        restored.data_refs["dataset"], RuntimeHandleRef
                    )
                    self.assertEqual(restored.backend_id, ENGINEERING_VIEWER_BACKEND_ID)
                    self.assertEqual(
                        restored.transport_revision, command.transport_revision
                    )
                    self.assertEqual(
                        restored.live_open_status, command.live_open_status
                    )
                    self.assertEqual(restored.camera_state, command.camera_state)
                    self.assertEqual(restored.playback_state, command.playback_state)
                if isinstance(restored, OpenViewerSessionCommand):
                    self.assertIsInstance(
                        restored.data_refs["preview"], RuntimeArtifactRef
                    )
                if isinstance(restored, QueryViewerSessionCommand):
                    self.assertEqual(restored.backend_id, "corex_scene")
                    self.assertEqual(restored.query_type, "distance")
                    self.assertEqual(restored.payload["point_b"], [3, 4, 0])
                    self.assertEqual(restored.options, {"precision": 3})

    def test_viewer_event_family_round_trips_runtime_refs_and_summaries(self) -> None:
        dataset_ref = RuntimeHandleRef(
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            schema_version=1,
            handle_id="viewer_dataset_live",
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="viewer:session_live",
            worker_generation=7,
            metadata={"dataset_type": "UnstructuredGrid"},
        )
        staged_png = RuntimeArtifactRef.staged(
            "viewer_png_export",
            data_type_id=PATH_DATA_TYPE_ID,
            schema_version=1,
            format="png",
            size_bytes=0,
            sha256="0" * 64,
            provenance="corex.test.fixture",
        )

        events = [
            ViewerSessionOpenedEvent(
                request_id="viewer_req_open",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_live",
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                data_refs={"dataset": dataset_ref},
                transport={
                    "kind": "scene_transport",
                    "version": 1,
                    "data_refs": {"dataset": dataset_ref},
                },
                transport_revision=1,
                live_open_status="ready",
                camera_state={"position": [0.0, 0.0, 1.0]},
                playback_state={"state": "paused", "step_index": 0},
                summary={"dataset_type": "UnstructuredGrid", "array_names": ["U"]},
                options={"live_mode": "proxy"},
            ),
            ViewerSessionUpdatedEvent(
                request_id="viewer_req_update",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_live",
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                data_refs={"dataset": dataset_ref},
                transport={
                    "kind": "scene_transport",
                    "version": 1,
                    "data_refs": {"dataset": dataset_ref},
                },
                transport_revision=2,
                live_open_status="ready",
                camera_state={"zoom": 1.25},
                playback_state={"state": "playing", "step_index": 1},
                summary={"camera": {"zoom": 1.25}},
                options={"selection": {"set_ids": [1]}},
            ),
            ViewerSessionClosedEvent(
                request_id="viewer_req_close",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_live",
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                transport_revision=2,
                live_open_status="blocked",
                live_open_blocker={"code": "session_closed"},
                playback_state={"state": "paused", "step_index": 1},
                summary={"reason": "node_removed"},
                options={"release_handles": True},
            ),
            ViewerDataMaterializedEvent(
                request_id="viewer_req_materialize",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_live",
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                data_refs={
                    "dataset": dataset_ref,
                    "png": staged_png,
                },
                transport={
                    "kind": "scene_transport",
                    "version": 1,
                    "data_refs": {"dataset": dataset_ref, "png": staged_png},
                },
                transport_revision=3,
                live_open_status="ready",
                camera_state={"zoom": 1.25},
                playback_state={"state": "playing", "step_index": 2},
                summary={"output_profile": "both", "field_count": 2},
                options={"export_formats": ["png"]},
            ),
            ViewerQueryResultEvent(
                request_id="viewer_req_query",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_live",
                backend_id="corex_scene",
                query_type="distance",
                supported=True,
                value={"distance": 5.0, "length_unit": "mm"},
            ),
            ViewerSessionFailedEvent(
                request_id="viewer_req_fail",
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id="session_live",
                command="materialize_viewer_data",
                error="viewer session expired",
            ),
        ]
        events = [
            replace(
                event,
                workspace_invalidation_epoch=3,
                node_invalidation_epoch=5,
            )
            for event in events
        ]

        for event in events:
            with self.subTest(event_type=event.type):
                payload = event_to_dict(event, catalog=self.catalog)
                self.assertEqual(payload["type"], event.type)
                restored = dict_to_event(payload, catalog=self.catalog)
                self.assertIsInstance(restored, type(event))
                self.assertEqual(restored.request_id, event.request_id)
                self.assertEqual(restored.workspace_id, event.workspace_id)
                self.assertEqual(restored.node_id, event.node_id)
                self.assertEqual(restored.session_id, event.session_id)
                self.assertEqual(payload["workspace_invalidation_epoch"], 3)
                self.assertEqual(payload["node_invalidation_epoch"], 5)
                self.assertEqual(restored.workspace_invalidation_epoch, 3)
                self.assertEqual(restored.node_invalidation_epoch, 5)

                if isinstance(
                    restored,
                    (
                        ViewerSessionOpenedEvent,
                        ViewerSessionUpdatedEvent,
                        ViewerDataMaterializedEvent,
                    ),
                ):
                    self.assertIsInstance(
                        restored.data_refs["dataset"], RuntimeHandleRef
                    )
                    self.assertEqual(restored.backend_id, ENGINEERING_VIEWER_BACKEND_ID)
                    self.assertEqual(
                        restored.transport_revision, event.transport_revision
                    )
                    self.assertEqual(restored.live_open_status, event.live_open_status)
                    self.assertEqual(restored.camera_state, event.camera_state)
                    self.assertEqual(restored.playback_state, event.playback_state)
                if isinstance(restored, ViewerDataMaterializedEvent):
                    self.assertIsInstance(restored.data_refs["png"], RuntimeArtifactRef)
                if isinstance(restored, ViewerSessionClosedEvent):
                    self.assertEqual(restored.backend_id, ENGINEERING_VIEWER_BACKEND_ID)
                    self.assertEqual(restored.live_open_status, "blocked")
                    self.assertEqual(
                        restored.live_open_blocker, {"code": "session_closed"}
                    )
                if isinstance(restored, ViewerQueryResultEvent):
                    self.assertTrue(restored.supported)
                    self.assertEqual(restored.query_type, "distance")
                    self.assertEqual(restored.value["distance"], 5.0)

    def test_protocol_error_event_round_trips_request_correlation(self) -> None:
        event = ProtocolErrorEvent(
            workspace_id="ws_main",
            request_id="viewer_req_fail",
            command="update_viewer_session",
            error="Unknown command type.",
        )

        payload = event_to_dict(event)
        self.assertEqual(payload["request_id"], "viewer_req_fail")
        self.assertEqual(payload["command"], "update_viewer_session")

        restored = dict_to_event(payload)
        self.assertIsInstance(restored, ProtocolErrorEvent)
        self.assertEqual(restored.workspace_id, event.workspace_id)
        self.assertEqual(restored.request_id, event.request_id)
        self.assertEqual(restored.command, event.command)
        self.assertEqual(restored.error, event.error)

    def test_viewer_command_payloads_reject_non_json_safe_objects(self) -> None:
        command = OpenViewerSessionCommand(
            request_id="viewer_req_bad",
            workspace_id="ws_main",
            node_id="node_viewer",
            data_refs={"raw_viewer_object": _FakeViewerObject()},
        )

        with self.assertRaisesRegex(TypeError, "JSON-safe"):
            command_to_dict(command)


if __name__ == "__main__":
    unittest.main()
