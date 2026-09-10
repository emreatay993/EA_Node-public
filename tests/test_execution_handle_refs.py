from __future__ import annotations

import unittest

from ea_node_editor.execution.run_messages import (
    NodeSettledEvent,
    StartRunCommand,
)
from ea_node_editor.execution.protocol_codec import (
    command_to_dict,
    dict_to_command,
    dict_to_event,
    event_to_dict,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot
from ea_node_editor.runtime_contracts.value_codec import (
    deserialize_runtime_value,
    serialize_runtime_value,
)
from ea_node_editor.runtime_contracts.value_refs import RuntimeHandleRef
from ea_node_editor.common.scene_protocol import COREX_SCENE_HANDLE_KIND
from ea_node_editor.runtime_contracts import DataTree, ENGINEERING_SCENE_DATA_TYPE_ID
from tests.typed_handle_support import core_data_type_catalog

_DATA_TYPES = core_data_type_catalog()


class ExecutionHandleRefProtocolTests(unittest.TestCase):
    def test_node_settled_event_round_trips_runtime_handle_ref_payloads(self) -> None:
        runtime_ref = RuntimeHandleRef(
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            schema_version=1,
            handle_id="mesh_001",
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="run:run_handle",
            worker_generation=7,
            metadata={"label": "primary"},
        )
        event = NodeSettledEvent(
            run_id="run_handle",
            workspace_id="ws_main",
            node_id="node_export",
            outputs={
                "mesh_handle": SettledPortResult(
                    status="value",
                    value=DataTree.from_item(runtime_ref),
                ),
            },
        )

        payload = event_to_dict(event, catalog=_DATA_TYPES)

        self.assertEqual(
            payload["outputs"]["mesh_handle"]["value"]["branches"][0]["items"][0],
            {
                "__ea_runtime_value__": "handle_ref",
                "data_type_id": ENGINEERING_SCENE_DATA_TYPE_ID,
                "schema_version": 1,
                "handle_id": "mesh_001",
                "kind": COREX_SCENE_HANDLE_KIND,
                "owner_scope": "run:run_handle",
                "worker_generation": 7,
                "metadata": {"label": "primary"},
            },
        )

        restored = dict_to_event(payload, catalog=_DATA_TYPES)
        self.assertEqual(
            restored.outputs["mesh_handle"].value,
            DataTree.from_item(runtime_ref),
        )

    def test_start_run_command_round_trips_runtime_snapshot_handle_payloads(
        self,
    ) -> None:
        snapshot = RuntimeSnapshot(
            schema_version=1,
            project_id="project_demo",
            metadata={
                "viewer_state": {
                    "field_handle": RuntimeHandleRef(
                        data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
                        schema_version=1,
                        handle_id="field_123",
                        kind=COREX_SCENE_HANDLE_KIND,
                        owner_scope="workspace:ws_main",
                        worker_generation=11,
                    )
                }
            },
        )
        command = StartRunCommand(
            run_id="run_demo",
            workspace_id="ws_main",
            trigger={"kind": "manual"},
            runtime_snapshot=snapshot,
        )

        payload = command_to_dict(command, catalog=_DATA_TYPES)

        self.assertEqual(
            payload["runtime_snapshot"]["metadata"]["viewer_state"]["field_handle"],
            {
                "__ea_runtime_value__": "handle_ref",
                "data_type_id": ENGINEERING_SCENE_DATA_TYPE_ID,
                "schema_version": 1,
                "handle_id": "field_123",
                "kind": COREX_SCENE_HANDLE_KIND,
                "owner_scope": "workspace:ws_main",
                "worker_generation": 11,
            },
        )

        restored = dict_to_command(payload, catalog=_DATA_TYPES)
        self.assertIsNotNone(restored.runtime_snapshot)
        if restored.runtime_snapshot is None:
            self.fail("runtime snapshot was not restored")
        restored_ref = restored.runtime_snapshot.metadata["viewer_state"][
            "field_handle"
        ]
        self.assertIsInstance(restored_ref, RuntimeHandleRef)
        if not isinstance(restored_ref, RuntimeHandleRef):
            self.fail("runtime handle ref did not round-trip through RuntimeSnapshot")
        self.assertEqual(restored_ref.handle_id, "field_123")
        self.assertEqual(restored_ref.kind, COREX_SCENE_HANDLE_KIND)
        self.assertEqual(restored_ref.owner_scope, "workspace:ws_main")
        self.assertEqual(restored_ref.worker_generation, 11)

    def test_deserialize_runtime_value_rejects_unknown_runtime_marker(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported runtime value marker"):
            deserialize_runtime_value(
                {
                    "__ea_runtime_value__": "unknown_ref",
                    "value": "bad",
                }
            )

    def test_deserialize_runtime_value_rejects_incomplete_handle_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing: owner_scope"):
            deserialize_runtime_value(
                {
                    "__ea_runtime_value__": "handle_ref",
                    "data_type_id": ENGINEERING_SCENE_DATA_TYPE_ID,
                    "schema_version": 1,
                    "handle_id": "field_123",
                    "kind": COREX_SCENE_HANDLE_KIND,
                    "worker_generation": 3,
                },
                catalog=_DATA_TYPES,
            )

    def test_serialize_runtime_value_rejects_malformed_runtime_marker(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "Runtime value marker must be a non-empty string"
        ):
            serialize_runtime_value(
                {
                    "__ea_runtime_value__": "",
                    "value": "bad",
                }
            )


if __name__ == "__main__":
    unittest.main()
