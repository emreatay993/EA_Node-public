from __future__ import annotations

import unittest

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.settings import SCHEMA_VERSION


def _workspace_doc(workspace_id: str, name: str) -> dict[str, object]:
    view_id = f"{workspace_id}_view_1"
    return {
        "workspace_id": workspace_id,
        "name": name,
        "active_view_id": view_id,
        "views": [
            {
                "view_id": view_id,
                "name": "V1",
                "zoom": 1.0,
                "pan_x": 0.0,
                "pan_y": 0.0,
            }
        ],
        "nodes": [],
        "edges": [],
    }


class SerializerSchemaMigrationTests(unittest.TestCase):
    def test_migrate_prefers_explicit_workspace_order_and_normalizes_metadata_copy(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_explicit_order",
            "name": "Explicit Order",
            "active_workspace_id": "missing_workspace",
            "workspace_order": ["ws_a", "ws_b"],
            "workspaces": [
                _workspace_doc("ws_b", "Workspace B"),
                _workspace_doc("ws_a", "Workspace A"),
            ],
            "metadata": {
                "workspace_order": ["ws_b", "ws_a"],
                "ui": {
                    "passive_style_presets": {
                        "node_presets": [
                            {
                                "preset_id": "NodePreset",
                                "name": " Warm ",
                                "style": {
                                    "fill_color": "#102030",
                                    "border_width": "2.5",
                                    "ignored": True,
                                    "accent_color": "#203040",
                                    "header_color": "#304050",
                                    "header_gradient_enabled": True,
                                    "header_gradient_color": "#405060",
                                    "header_gradient_direction": "east",
                                },
                            }
                        ]
                    }
                },
            },
        }

        migrated = serializer.migrate(payload)

        self.assertEqual(migrated["workspace_order"], ["ws_a", "ws_b"])
        self.assertEqual(migrated["metadata"]["workspace_order"], ["ws_a", "ws_b"])
        self.assertEqual([workspace["workspace_id"] for workspace in migrated["workspaces"]], ["ws_a", "ws_b"])
        self.assertEqual(migrated["active_workspace_id"], "ws_a")
        self.assertEqual(
            migrated["metadata"]["ui"]["passive_style_presets"]["node_presets"][0]["name"],
            "Warm",
        )
        self.assertEqual(
            migrated["metadata"]["ui"]["passive_style_presets"]["node_presets"][0]["style"],
            {"fill_color": "#102030", "border_width": 2.5, "ignored": True},
        )

    def test_current_schema_load_removes_active_styles_and_retired_passive_style_keys(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        workspace = _workspace_doc("ws_style_cleanup", "Style Cleanup")
        workspace["nodes"] = [
            {
                "node_id": "node_passive",
                "type_id": "passive.flowchart.process",
                "title": "Passive",
                "x": 10.0,
                "y": 20.0,
                "collapsed": False,
                "properties": {
                    "accent_color": "#ABCDEF",
                    "custom_property": {"header_color": "preserve"},
                },
                "exposed_ports": {},
                "visual_style": {
                    "fill_color": "#112233",
                    "border_width": "2.5",
                    "gradient_enabled": True,
                    "gradient_color": "#223344",
                    "gradient_direction": "west",
                    "accent_color": "#334455",
                    "header_color": "#445566",
                    "header_gradient_enabled": True,
                    "header_gradient_color": "#556677",
                    "header_gradient_direction": "east",
                    "plugin_style": {"accent_color": "nested-preserved"},
                },
                "parent_node_id": None,
            },
            {
                "node_id": "node_active",
                "type_id": "core.constant",
                "title": "Constant",
                "x": 240.0,
                "y": 20.0,
                "collapsed": False,
                "properties": {},
                "exposed_ports": {},
                "visual_style": {"fill_color": "#AABBCC"},
                "parent_node_id": None,
            },
        ]
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_style_cleanup",
            "name": "Style Cleanup",
            "active_workspace_id": "ws_style_cleanup",
            "workspace_order": ["ws_style_cleanup"],
            "workspaces": [workspace],
            "metadata": {
                "ui": {
                    "passive_style_presets": {
                        "node_presets": [
                            {
                                "preset_id": "node_preset_deadbeef",
                                "name": "Legacy",
                                "style": {
                                    "fill_color": "#667788",
                                    "accent_color": "#778899",
                                    "header_color": "#8899AA",
                                    "header_gradient_enabled": False,
                                    "header_gradient_color": "#99AABB",
                                    "header_gradient_direction": "south",
                                    "plugin_style": {"header_color": "nested-preserved"},
                                },
                            }
                        ],
                        "edge_presets": [],
                    }
                }
            },
        }

        migrated = serializer.migrate(payload)
        migrated_nodes = {
            node["node_id"]: node for node in migrated["workspaces"][0]["nodes"]
        }
        migrated_node = migrated_nodes["node_passive"]
        self.assertNotIn("visual_style", migrated_nodes["node_active"])
        self.assertEqual(
            migrated_node["properties"],
            {
                "accent_color": "#ABCDEF",
                "custom_property": {"header_color": "preserve"},
            },
        )

        loaded = serializer.from_document(payload)
        saved = serializer.to_document(loaded)
        saved_nodes = {node["node_id"]: node for node in saved["workspaces"][0]["nodes"]}
        saved_node = saved_nodes["node_passive"]
        self.assertNotIn("visual_style", saved_nodes["node_active"])

        self.assertEqual(
            saved_node["visual_style"],
            {
                "fill_color": "#112233",
                "border_width": "2.5",
                "gradient_enabled": True,
                "gradient_color": "#223344",
                "gradient_direction": "west",
                "plugin_style": {"accent_color": "nested-preserved"},
            },
        )
        self.assertEqual(
            saved["metadata"]["ui"]["passive_style_presets"]["node_presets"][0]["style"],
            {
                "fill_color": "#667788",
                "plugin_style": {"header_color": "nested-preserved"},
            },
        )

    def test_migrate_current_schema_document_uses_workspace_payload_order_when_order_is_missing(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_payload_order",
            "name": "Payload Order",
            "active_workspace_id": "",
            "workspaces": [
                _workspace_doc("ws_b", "Workspace B"),
                _workspace_doc("ws_a", "Workspace A"),
            ],
            "metadata": {},
        }

        migrated = serializer.migrate(payload)

        self.assertEqual(migrated["workspace_order"], ["ws_b", "ws_a"])
        self.assertEqual(migrated["metadata"]["workspace_order"], ["ws_b", "ws_a"])
        self.assertEqual([workspace["workspace_id"] for workspace in migrated["workspaces"]], ["ws_b", "ws_a"])
        self.assertEqual(migrated["active_workspace_id"], "ws_b")

    def test_migrate_normalizes_session_metadata_substructures_and_preserves_extra_ui_keys(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_session_metadata",
            "name": "Session Metadata",
            "workspace_order": ["ws"],
            "active_workspace_id": "ws",
            "workspaces": [_workspace_doc("ws", "Workspace")],
            "metadata": {
                "ui": {
                    "script_editor": {
                        "visible": True,
                    },
                    "panel_state": {
                        "library": "collapsed",
                    },
                },
                "workflow_settings": {
                    "solver_config": {
                        "thread_count": 16,
                    }
                },
            },
        }

        migrated = serializer.migrate(payload)

        self.assertEqual(
            migrated["metadata"]["ui"]["script_editor"],
            {
                "visible": True,
                "floating": False,
                "width": 0.0,
            },
        )
        self.assertEqual(migrated["metadata"]["ui"]["panel_state"], {"library": "collapsed"})
        self.assertEqual(migrated["metadata"]["workflow_settings"]["solver_config"]["thread_count"], 16)
        self.assertIn("memory_limit_gb", migrated["metadata"]["workflow_settings"]["solver_config"])

    def test_migrate_drops_legacy_plot_session_layout_current_schema_only(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_plot_session",
            "name": "Plot Session",
            "workspace_order": ["ws"],
            "active_workspace_id": "ws",
            "workspaces": [_workspace_doc("ws", "Workspace")],
            "plot_session_layout": {
                "version": 1,
                "workspaces": {
                    "ws": {
                        "window": {"open": True, "geometry": {"width": "1200"}},
                        "panels": [
                            {
                                "panel_id": "panel-line",
                                "node_id": "node-line",
                                "plot_type": "line",
                                "geometry": {"x": "10", "y": "20", "width": "640", "height": "420"},
                                "transport": {"pipe": "transient"},
                            }
                        ],
                        "brush_selections": [
                            {
                                "selection_id": "brush-a",
                                "panel_id": "panel-line",
                                "range": {"x_min": "1.5", "x_max": "2.5"},
                            }
                        ],
                        "pinned_overlays": [
                            {
                                "overlay_id": "pin-a",
                                "panel_id": "panel-line",
                                "snapshot": {"artifact_ref": "managed://plot-a"},
                                "live": {"render_revision": 2, "widget": "transient"},
                            }
                        ],
                    },
                    "missing": {
                        "panels": [{"panel_id": "panel-missing", "node_id": "node-missing"}],
                    },
                },
            },
            "metadata": {},
        }

        migrated = serializer.migrate(payload)
        project = serializer.from_document(payload)
        round_tripped = serializer.to_persistent_document(project)

        self.assertNotIn("plot_session_layout", migrated)
        self.assertNotIn("plot_session_layout", round_tripped)
        self.assertFalse(hasattr(project, "plot_session_layout"))

    def test_migrate_and_load_known_node_without_title_uses_registry_display_name(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_missing_title",
            "name": "Missing Title",
            "workspace_order": ["ws"],
            "active_workspace_id": "ws",
            "workspaces": [
                {
                    "workspace_id": "ws",
                    "name": "Workspace",
                    "active_view_id": "view",
                    "views": [
                        {
                            "view_id": "view",
                            "name": "V1",
                            "zoom": 1.0,
                            "pan_x": 0.0,
                            "pan_y": 0.0,
                            "scope_path": [],
                        }
                    ],
                    "nodes": [
                        {
                            "node_id": "node1",
                            "type_id": "core.constant",
                        }
                    ],
                    "edges": [],
                }
            ],
            "metadata": {},
        }

        migrated = serializer.migrate(payload)
        project = serializer.from_document(payload)

        self.assertEqual(migrated["workspaces"][0]["nodes"][0]["title"], "Constant")
        self.assertEqual(project.workspaces["ws"].nodes["node1"].title, "Constant")

    def test_migrate_current_schema_renames_legacy_engineering_viewer_nodes(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_legacy_model_viewer",
            "name": "Legacy Model Viewer",
            "workspace_order": ["ws"],
            "active_workspace_id": "ws",
            "workspaces": [
                {
                    "workspace_id": "ws",
                    "name": "Workspace",
                    "active_view_id": "view",
                    "views": [
                        {
                            "view_id": "view",
                            "name": "V1",
                            "zoom": 1.0,
                            "pan_x": 0.0,
                            "pan_y": 0.0,
                            "scope_path": [],
                        }
                    ],
                    "nodes": [
                        {"node_id": "untitled", "type_id": "engineering.viewer"},
                        {
                            "node_id": "default_title",
                            "type_id": "engineering.viewer",
                            "title": "Engineering Viewer",
                        },
                        {
                            "node_id": "custom_title",
                            "type_id": "engineering.viewer",
                            "title": "Review Model",
                        },
                    ],
                    "edges": [],
                }
            ],
            "metadata": {},
        }

        migrated = serializer.migrate(payload)
        migrated_nodes = {
            node["node_id"]: node for node in migrated["workspaces"][0]["nodes"]
        }
        project = serializer.from_document(payload)
        round_tripped = serializer.to_persistent_document(project)
        round_tripped_nodes = {
            node["node_id"]: node
            for node in round_tripped["workspaces"][0]["nodes"]
        }

        self.assertEqual(migrated["schema_version"], SCHEMA_VERSION)
        self.assertEqual(
            {
                node_id: node["type_id"]
                for node_id, node in migrated_nodes.items()
            },
            {
                "untitled": "model.viewer",
                "default_title": "model.viewer",
                "custom_title": "model.viewer",
            },
        )
        self.assertEqual(migrated_nodes["untitled"]["title"], "Model Viewer")
        self.assertEqual(migrated_nodes["default_title"]["title"], "Model Viewer")
        self.assertEqual(migrated_nodes["custom_title"]["title"], "Review Model")
        project_nodes = project.workspaces["ws"].nodes
        self.assertEqual(project_nodes["untitled"].title, "Model Viewer")
        self.assertEqual(project_nodes["default_title"].title, "Model Viewer")
        self.assertEqual(project_nodes["custom_title"].title, "Review Model")
        self.assertEqual(round_tripped["schema_version"], SCHEMA_VERSION)
        self.assertEqual(
            {node["type_id"] for node in round_tripped_nodes.values()},
            {"model.viewer"},
        )
        self.assertEqual(round_tripped_nodes["custom_title"]["title"], "Review Model")

    def test_migrate_current_schema_removes_settings_section_state(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        model = GraphModel()
        workspace = model.active_workspace
        first = model.add_node(workspace.workspace_id, "core.constant", "Constant", 0.0, 0.0)
        second = model.add_node(workspace.workspace_id, "core.logger", "Logger", 240.0, 0.0)
        payload = serializer.to_document(model.project)
        node_docs = {node["node_id"]: node for node in payload["workspaces"][0]["nodes"]}
        node_docs[first.node_id]["settings_section_expanded"] = False
        node_docs[first.node_id]["expanded_settings_group_ids"] = ["options"]
        node_docs[second.node_id]["advanced_section_expanded"] = "yes"
        node_docs[second.node_id]["settings_section_expanded"] = True

        migrated = serializer.migrate(payload)
        migrated_nodes = {node["node_id"]: node for node in migrated["workspaces"][0]["nodes"]}

        self.assertNotIn("settings_section_expanded", migrated_nodes[first.node_id])
        self.assertEqual(migrated_nodes[first.node_id]["expanded_settings_group_ids"], ["options"])
        self.assertNotIn("settings_section_expanded", migrated_nodes[second.node_id])
        self.assertNotIn("advanced_section_expanded", migrated_nodes[second.node_id])

    def test_migrate_accepts_v4_and_marks_loaded_workspaces_dirty(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION - 1,
            "project_id": "proj_legacy",
            "name": "Legacy",
            "active_workspace_id": "",
            "workspaces": [_workspace_doc("ws_a", "Workspace A")],
            "metadata": {},
        }

        project = serializer.from_document(payload)
        self.assertEqual(project.schema_version, SCHEMA_VERSION)
        self.assertEqual(project.migration_source_schema_version, SCHEMA_VERSION - 1)
        self.assertTrue(project.workspaces["ws_a"].dirty)

    def test_from_document_rejects_nonempty_legacy_workspace_recovery_metadata(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_legacy_runtime_envelope",
            "name": "Legacy Runtime Envelope",
            "active_workspace_id": "ws_a",
            "workspace_order": ["ws_a"],
            "workspaces": [_workspace_doc("ws_a", "Workspace A")],
            "metadata": {
                "_runtime_unresolved_workspaces": {
                    "ws_a": {
                        "nodes": [
                            {
                                "node_id": "node_missing",
                                "type_id": "plugin.missing",
                            }
                        ]
                    }
                }
            },
        }

        with self.assertRaisesRegex(ValueError, "unresolved add-ons"):
            serializer.from_document(payload)

    def test_from_document_rejects_nonempty_legacy_project_recovery_metadata(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_legacy_workspace_envelope",
            "name": "Legacy Workspace Envelope",
            "active_workspace_id": "ws_a",
            "workspace_order": ["ws_a"],
            "workspaces": [_workspace_doc("ws_a", "Workspace A")],
            "metadata": {
                "_persistence_envelope": {
                    "document_flavor": "runtime",
                    "workspaces": {
                        "ws_a": {
                            "nodes": [
                                {
                                    "node_id": "node_missing",
                                    "type_id": "plugin.missing",
                                }
                            ],
                            "edges": [],
                            "node_overrides": {},
                        }
                    },
                }
            },
        }

        with self.assertRaisesRegex(ValueError, "unresolved add-ons"):
            serializer.from_document(payload)

    def test_from_document_drops_empty_legacy_recovery_metadata(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_empty_legacy_recovery",
            "name": "Empty Legacy Recovery",
            "active_workspace_id": "ws_a",
            "workspace_order": ["ws_a"],
            "workspaces": [_workspace_doc("ws_a", "Workspace A")],
            "metadata": {
                "_persistence_envelope": {
                    "document_flavor": "runtime",
                    "workspaces": {},
                },
                "_runtime_unresolved_workspaces": {},
            },
        }

        project = serializer.from_document(payload)

        self.assertNotIn("_persistence_envelope", project.metadata)
        self.assertNotIn("_runtime_unresolved_workspaces", project.metadata)

    def test_migrate_preserves_multiple_connections_for_allow_multiple_target_ports(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_flowchart_multi",
            "name": "Flowchart Multi",
            "active_workspace_id": "ws_a",
            "workspace_order": ["ws_a"],
            "workspaces": [
                {
                    "workspace_id": "ws_a",
                    "name": "Workspace A",
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
                            "node_id": "node_start_a",
                            "type_id": "passive.flowchart.start",
                            "title": "Start A",
                            "x": 0.0,
                            "y": 0.0,
                            "collapsed": False,
                            "properties": {},
                            "exposed_ports": {"flow_out": True},
                            "parent_node_id": None,
                        },
                        {
                            "node_id": "node_start_b",
                            "type_id": "passive.flowchart.start",
                            "title": "Start B",
                            "x": 0.0,
                            "y": 120.0,
                            "collapsed": False,
                            "properties": {},
                            "exposed_ports": {"flow_out": True},
                            "parent_node_id": None,
                        },
                        {
                            "node_id": "node_end",
                            "type_id": "passive.flowchart.end",
                            "title": "End",
                            "x": 320.0,
                            "y": 60.0,
                            "collapsed": False,
                            "properties": {},
                            "exposed_ports": {"flow_in": True},
                            "parent_node_id": None,
                        },
                    ],
                    "edges": [
                        {
                            "edge_id": "edge_a",
                            "source_node_id": "node_start_a",
                            "source_port_key": "right",
                            "target_node_id": "node_end",
                            "target_port_key": "left",
                        },
                        {
                            "edge_id": "edge_b",
                            "source_node_id": "node_start_b",
                            "source_port_key": "right",
                            "target_node_id": "node_end",
                            "target_port_key": "left",
                        },
                    ],
                }
            ],
            "metadata": {},
        }

        project = serializer.from_document(payload)
        workspace = project.workspaces["ws_a"]

        self.assertEqual(set(workspace.edges), {"edge_a", "edge_b"})
        self.assertEqual(
            {
                (
                    edge.source_node_id,
                    edge.source_port_key,
                    edge.target_node_id,
                    edge.target_port_key,
                )
                for edge in workspace.edges.values()
            },
            {
                ("node_start_a", "right", "node_end", "left"),
                ("node_start_b", "right", "node_end", "left"),
            },
        )

    def test_current_schema_document_rejects_unresolved_nodes(self) -> None:
        serializer = JsonProjectSerializer(build_default_registry())
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": "proj_missing_plugin",
            "name": "Missing Plugin",
            "active_workspace_id": "ws_a",
            "workspaces": [
                {
                    "workspace_id": "ws_a",
                    "name": "Workspace A",
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
                            "node_id": "node_unknown",
                            "type_id": "plugin.missing_node",
                            "title": "Missing",
                            "x": 180.0,
                            "y": 0.0,
                            "collapsed": True,
                            "properties": {"threshold": 0.5},
                            "exposed_ports": {"plugin_in": True},
                            "visual_style": {"fill": "#334455"},
                            "parent_node_id": None,
                            "plugin_payload": {"mode": "offline"},
                        },
                    ],
                    "edges": [],
                }
            ],
            "metadata": {},
        }

        migrated = serializer.migrate(payload)
        self.assertEqual(
            migrated["workspaces"][0]["nodes"][0]["visual_style"],
            {"fill": "#334455"},
        )
        with self.assertRaisesRegex(ValueError, "unresolved node type"):
            serializer.from_document(payload)


if __name__ == "__main__":
    unittest.main()
