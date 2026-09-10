from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ea_node_editor.custom_workflows import export_custom_workflow_file, import_custom_workflow_file
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.transforms import group_selection_into_subnode
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import (
    GRAPH_DATA_TYPE_ID,
    JSON_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
)
from ea_node_editor.workspace.manager import WorkspaceManager


class SerializerWorkflowMixin:
    def test_round_trip_preserves_scope_path_and_normalized_custom_workflows(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        parent = model.add_node(workspace.workspace_id, "core.logger", "Group", 40.0, 60.0)
        child = model.add_node(workspace.workspace_id, "core.constant", "Constant", 120.0, 160.0)
        child.parent_node_id = parent.node_id
        view = workspace.views[workspace.active_view_id]
        view.scope_path = [parent.node_id]
        model.project.metadata["custom_workflows"] = [
            {
                "workflow_id": "wf_valid",
                "name": "Valid Workflow",
                "description": "kept",
                "revision": 2,
                "ports": [
                    {
                        "key": "message",
                        "label": "Message",
                        "direction": "in",
                        "kind": "data",
                        "data_type": STRING_DATA_TYPE_ID,
                        "accepted_data_types": [JSON_DATA_TYPE_ID],
                        "data_access": "tree",
                    }
                ],
                "fragment": {
                    "kind": "ea-node-editor/graph-fragment",
                    "version": 2,
                    "nodes": [
                        {
                            "ref_id": "logger",
                            "type_id": "core.logger",
                            "title": "Logger",
                            "x": 0.0,
                            "y": 0.0,
                        }
                    ],
                    "edges": [],
                },
            },
            {
                "workflow_id": "wf_valid",
                "name": "Duplicate",
                "fragment": {"root_node_id": child.node_id},
            },
            {
                "workflow_id": "wf_missing_fragment",
                "name": "Invalid",
                "fragment": [],
            },
        ]

        serializer = JsonProjectSerializer(build_default_registry())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save(str(path), model.project)
            loaded = serializer.load(str(path))

        loaded_view = loaded.workspaces[workspace.workspace_id].views[workspace.active_view_id]
        self.assertEqual(loaded_view.scope_path, [parent.node_id])
        workflows = loaded.metadata.get("custom_workflows")
        self.assertEqual(len(workflows), 1)
        self.assertEqual(workflows[0]["workflow_id"], "wf_valid")
        self.assertEqual(workflows[0]["ports"][0]["kind"], "data")
        self.assertEqual(
            workflows[0]["ports"][0]["accepted_data_types"],
            [JSON_DATA_TYPE_ID],
        )
        self.assertEqual(workflows[0]["ports"][0]["data_access"], "tree")
        self.assertEqual(workflows[0]["fragment"]["version"], 2)

    def test_custom_workflow_eawf_round_trip_preserves_snapshot_fidelity(self) -> None:
        definition = {
            "workflow_id": "wf_roundtrip",
            "name": "Roundtrip Workflow",
            "description": "portable snapshot",
            "revision": 5,
            "ports": [
                {
                    "key": "payload",
                    "label": "Payload",
                    "direction": "in",
                    "kind": "data",
                    "data_type": GRAPH_DATA_TYPE_ID,
                    "accepted_data_types": [STRING_DATA_TYPE_ID],
                    "data_access": "item",
                },
                {
                    "key": "payload",
                    "label": "Payload",
                    "direction": "out",
                    "kind": "data",
                    "data_type": JSON_DATA_TYPE_ID,
                    "accepted_data_types": [],
                },
            ],
            "fragment": {
                "kind": "ea-node-editor/graph-fragment",
                "version": 1,
                "nodes": [
                    {
                        "ref_id": "note_a",
                        "type_id": "tests.passive_note",
                        "title": "Note A",
                        "x": 10.0,
                        "y": 20.0,
                        "settings_section_expanded": True,
                        "visual_style": {"fill": "#ffeaa7", "outline": {"width": 2}},
                    },
                    {
                        "ref_id": "note_b",
                        "type_id": "tests.passive_note",
                        "title": "Note B",
                        "x": 220.0,
                        "y": 80.0,
                        "visual_style": {"fill": "#dfe6e9"},
                    },
                ],
                "edges": [
                    {
                        "source_ref_id": "note_a",
                        "source_port_key": "flow_out",
                        "target_ref_id": "note_b",
                        "target_port_key": "flow_in",
                        "label": "Primary path",
                        "visual_style": {"stroke": "dashed", "arrow": {"kind": "none"}},
                    }
                ],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "workflow_export"
            saved_path = export_custom_workflow_file(definition, path)
            self.assertEqual(saved_path.suffix, ".cxwf")

            payload = json.loads(saved_path.read_text(encoding="utf-8"))
            self.assertEqual(payload.get("kind"), "ea-node-editor/custom-workflow")
            self.assertEqual(payload.get("version"), 2)

            imported = import_custom_workflow_file(saved_path)

        self.assertEqual(imported["workflow_id"], definition["workflow_id"])
        self.assertEqual(imported["ports"][0]["data_access"], "item")
        self.assertEqual(imported["fragment"]["version"], 2)
        self.assertNotIn("settings_section_expanded", imported["fragment"]["nodes"][0])

    def test_custom_workflow_import_removes_legacy_settings_section_state(self) -> None:
        legacy_document = {
            "kind": "ea-node-editor/custom-workflow",
            "version": 1,
            "workflow": {
                "workflow_id": "wf_legacy_settings",
                "name": "Legacy Settings",
                "description": "",
                "revision": 1,
                "ports": [],
                "fragment": {
                    "kind": "ea-node-editor/graph-fragment",
                    "version": 1,
                    "nodes": [
                        {
                            "ref_id": "logger",
                            "type_id": "core.logger",
                            "title": "Logger",
                            "x": 0.0,
                            "y": 0.0,
                            "advanced_section_expanded": True,
                        }
                    ],
                    "edges": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.cxwf"
            path.write_text(json.dumps(legacy_document), encoding="utf-8")
            imported = import_custom_workflow_file(path, registry=build_default_registry())
            exported_path = export_custom_workflow_file(imported, Path(temp_dir) / "migrated")
            exported = json.loads(exported_path.read_text(encoding="utf-8"))

        imported_node = imported["fragment"]["nodes"][0]
        self.assertNotIn("settings_section_expanded", imported_node)
        self.assertNotIn("advanced_section_expanded", imported_node)
        exported_node = exported["workflow"]["fragment"]["nodes"][0]
        self.assertNotIn("settings_section_expanded", exported_node)
        self.assertNotIn("advanced_section_expanded", exported_node)

    def test_round_trip_preserves_grouped_subnode_parenting_and_boundary_edges(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        source_a = model.add_node(workspace.workspace_id, "core.constant", "Source A", 20.0, 20.0)
        source_b = model.add_node(workspace.workspace_id, "core.constant", "Source B", 20.0, 220.0)
        script_a = model.add_node(workspace.workspace_id, "core.python_script", "Script A", 280.0, 20.0)
        script_b = model.add_node(workspace.workspace_id, "core.python_script", "Script B", 280.0, 220.0)
        sink_a = model.add_node(workspace.workspace_id, "core.logger", "Sink A", 640.0, 0.0)
        sink_b = model.add_node(workspace.workspace_id, "core.logger", "Sink B", 640.0, 140.0)
        sink_c = model.add_node(workspace.workspace_id, "core.logger", "Sink C", 640.0, 280.0)
        sink_d = model.add_node(workspace.workspace_id, "core.logger", "Sink D", 640.0, 420.0)

        model.add_edge(workspace.workspace_id, source_a.node_id, "value", script_a.node_id, "payload")
        model.add_edge(workspace.workspace_id, source_b.node_id, "value", script_b.node_id, "payload")
        model.add_edge(workspace.workspace_id, script_a.node_id, "result", sink_a.node_id, "message")
        model.add_edge(workspace.workspace_id, script_a.node_id, "result", sink_b.node_id, "message")
        model.add_edge(workspace.workspace_id, script_b.node_id, "result", sink_c.node_id, "message")
        model.add_edge(workspace.workspace_id, script_b.node_id, "result", sink_d.node_id, "message")

        grouped = group_selection_into_subnode(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            selected_node_ids=[script_a.node_id, script_b.node_id],
            scope_path=[],
            shell_x=280.0,
            shell_y=120.0,
        )
        self.assertIsNotNone(grouped)
        assert grouped is not None

        shell_id = grouped.shell_node_id
        edge_signature_before = {
            (
                edge.source_node_id,
                edge.source_port_key,
                edge.target_node_id,
                edge.target_port_key,
            )
            for edge in workspace.edges.values()
            if edge.source_node_id == shell_id or edge.target_node_id == shell_id
        }
        self.assertTrue(edge_signature_before)

        serializer = JsonProjectSerializer(registry)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save(str(path), model.project)
            loaded = serializer.load(str(path))

        loaded_ws = loaded.workspaces[workspace.workspace_id]
        self.assertIn(shell_id, loaded_ws.nodes)
        expected_children = [script_a.node_id, script_b.node_id, *grouped.created_pin_node_ids]
        for node_id in expected_children:
            self.assertIn(node_id, loaded_ws.nodes)
            self.assertEqual(loaded_ws.nodes[node_id].parent_node_id, shell_id)
        edge_signature_after = {
            (
                edge.source_node_id,
                edge.source_port_key,
                edge.target_node_id,
                edge.target_port_key,
            )
            for edge in loaded_ws.edges.values()
            if edge.source_node_id == shell_id or edge.target_node_id == shell_id
        }
        self.assertEqual(edge_signature_after, edge_signature_before)

    def test_save_output_is_deterministic_and_uses_workspace_order(self) -> None:
        model = GraphModel()
        manager = WorkspaceManager(model)
        first = manager.active_workspace_id()
        second = manager.create_workspace("Second")
        manager.move_workspace(1, 0)
        manager.set_active_workspace(second)

        workspace = model.project.workspaces[second]
        workspace.ensure_default_view()
        view = workspace.views[workspace.active_view_id]
        view.zoom = 1.42
        view.pan_x = -30.0
        view.pan_y = 45.0
        source = model.add_node(second, "core.constant", "Constant", 12.0, 20.0)
        target = model.add_node(second, "core.logger", "Logger", 80.0, 20.0)
        edge = model.add_edge(second, source.node_id, "as_text", target.node_id, "message")
        self.assertIsNotNone(edge.edge_id)

        serializer = JsonProjectSerializer(build_default_registry())
        doc = serializer.to_document(model.project)
        self.assertEqual(doc["workspace_order"], [second, first])
        self.assertEqual([ws["workspace_id"] for ws in doc["workspaces"]], [second, first])
        self.assertEqual(doc["active_workspace_id"], second)

        with tempfile.TemporaryDirectory() as temp_dir:
            path_a = Path(temp_dir) / "a.cxproj"
            path_b = Path(temp_dir) / "b.cxproj"
            serializer.save(str(path_a), model.project)
            serializer.save(str(path_b), model.project)
            self.assertEqual(path_a.read_text(encoding="utf-8"), path_b.read_text(encoding="utf-8"))
