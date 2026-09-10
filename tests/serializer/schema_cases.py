from __future__ import annotations

from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.settings import SCHEMA_VERSION
from tests.serializer.base_cases import (
    _current_schema_inconsistent_payload,
    _current_schema_minimal_payload,
    _missing_plugin_round_trip_payload,
)


class SerializerSchemaMixin:
    def test_current_schema_preserves_ordered_data_fan_in(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_conflict",
            "name": "conflict",
            "active_workspace_id": "ws_a",
            "workspace_order": ["ws_a"],
            "workspaces": [
                {
                    "workspace_id": "ws_a",
                    "name": "Workspace",
                    "active_view_id": "view_a",
                    "views": [
                        {
                            "view_id": "view_a",
                            "name": "V1",
                            "zoom": 1.0,
                            "pan_x": 0.0,
                            "pan_y": 0.0,
                        }
                    ],
                    "nodes": [
                        {
                            "node_id": "source_a",
                            "type_id": "core.constant",
                            "title": "Source A",
                            "x": 0.0,
                            "y": 0.0,
                            "collapsed": False,
                            "properties": {},
                            "exposed_ports": {"as_text": True},
                            "parent_node_id": None,
                        },
                        {
                            "node_id": "source_b",
                            "type_id": "core.constant",
                            "title": "Source B",
                            "x": 0.0,
                            "y": 120.0,
                            "collapsed": False,
                            "properties": {},
                            "exposed_ports": {"as_text": True},
                            "parent_node_id": None,
                        },
                        {
                            "node_id": "sink",
                            "type_id": "core.logger",
                            "title": "Sink",
                            "x": 320.0,
                            "y": 60.0,
                            "collapsed": False,
                            "properties": {},
                            "exposed_ports": {"message": True},
                            "parent_node_id": None,
                        },
                    ],
                    "edges": [
                        {
                            "edge_id": "edge_a",
                            "source_node_id": "source_a",
                            "source_port_key": "as_text",
                            "target_node_id": "sink",
                            "target_port_key": "message",
                            "enabled": True,
                            "input_order": 0,
                        },
                        {
                            "edge_id": "edge_z",
                            "source_node_id": "source_b",
                            "source_port_key": "as_text",
                            "target_node_id": "sink",
                            "target_port_key": "message",
                            "enabled": False,
                            "input_order": 1,
                        },
                    ],
                }
            ],
            "metadata": {},
        }

        project = serializer.from_document(payload)
        workspace = project.workspaces["ws_a"]
        self.assertEqual(list(workspace.edges), ["edge_a", "edge_z"])
        self.assertEqual([edge.input_order for edge in workspace.edges.values()], [0, 1])
        self.assertEqual([edge.enabled for edge in workspace.edges.values()], [True, False])

    def test_current_schema_fixture_adds_defaults_and_normalizes_workspace_and_view(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = _current_schema_minimal_payload()
        project = serializer.from_document(payload)

        self.assertEqual(project.schema_version, SCHEMA_VERSION)
        self.assertEqual(project.active_workspace_id, "ws_a")
        self.assertEqual(project.metadata.get("workspace_order"), ["ws_a", "ws_b"])
        self.assertEqual(project.metadata.get("custom_workflows"), [])
        self.assertEqual(project.workspaces["ws_b"].active_view_id, "view_b1")
        self.assertEqual(project.workspaces["ws_a"].views["view_a1"].scope_path, [])
        self.assertEqual(project.workspaces["ws_b"].views["view_b1"].scope_path, [])

    def test_legacy_schema_fixture_rejects_unresolved_addons(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = _current_schema_inconsistent_payload()
        with self.assertRaisesRegex(ValueError, "unresolved add-ons"):
            serializer.from_document(payload)

    def test_from_document_migrates_v4_schema_payload(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = _current_schema_minimal_payload()
        payload["schema_version"] = SCHEMA_VERSION - 1

        project = serializer.from_document(payload)
        self.assertEqual(project.schema_version, SCHEMA_VERSION)
        self.assertEqual(project.migration_source_schema_version, SCHEMA_VERSION - 1)
        self.assertTrue(all(workspace.dirty for workspace in project.workspaces.values()))

    def test_current_schema_rejects_unresolved_plugin_nodes(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = _missing_plugin_round_trip_payload()
        with self.assertRaisesRegex(ValueError, "unresolved node type"):
            serializer.from_document(payload)
