from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock

from ea_node_editor.graph.boundary_adapters import build_graph_boundary_adapters
from ea_node_editor.graph.fragment_payloads import build_graph_fragment_payload, graph_fragment_payload_is_valid
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.transform_fragment_ops import insert_graph_fragment
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.graph.workspace_view_ops import WorkspaceViewMutation
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.node_specs import SettingsGroupItemSpec, SettingsGroupSpec
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from ea_node_editor.ui_qml.graph_surface_metrics import resolved_node_surface_size


class GraphModelTrackBTests(unittest.TestCase):
    def _geometry_payload_builder(self) -> GraphScenePayloadBuilder:
        return GraphScenePayloadBuilder(
            boundary_adapters=build_graph_boundary_adapters(
                node_size_resolver=resolved_node_surface_size,
            )
        )

    def _node_payloads_by_title(self, model: GraphModel, registry) -> dict[str, dict]:
        workspace = model.active_workspace
        nodes_payload, _minimap_payload, _edges_payload = self._geometry_payload_builder().rebuild_models(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )
        return {str(payload["title"]): payload for payload in nodes_payload}

    def test_add_move_connect_remove_node_operations(self) -> None:
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        source = model.add_node(workspace_id, "core.constant", "Source", 0.0, 0.0)
        target = model.add_node(workspace_id, "core.python_script", "Target", 300.0, 80.0)

        model.set_node_position(workspace_id, source.node_id, 25.0, 45.0)
        moved = model.project.workspaces[workspace_id].nodes[source.node_id]
        self.assertEqual((moved.x, moved.y), (25.0, 45.0))

        edge = model.add_edge(workspace_id, source.node_id, "value", target.node_id, "payload")
        duplicate = model.add_edge(workspace_id, source.node_id, "value", target.node_id, "payload")
        self.assertEqual(edge.edge_id, duplicate.edge_id)
        self.assertEqual(len(model.project.workspaces[workspace_id].edges), 1)

        model.remove_node(workspace_id, source.node_id)
        workspace = model.project.workspaces[workspace_id]
        self.assertNotIn(source.node_id, workspace.nodes)
        self.assertEqual(workspace.edges, {})

    def test_validated_mutation_boundary_prunes_subnode_edges_when_pin_kind_changes(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        mutations = model.validated_mutations(workspace.workspace_id, registry)
        self.assertIsInstance(mutations, ValidatedGraphMutation)

        def _add_node(
            type_id: str,
            title: str,
            x: float,
            y: float,
            *,
            parent_node_id: str | None = None,
        ):
            spec = registry.get_spec(type_id)
            return mutations.add_node(
                type_id=type_id,
                title=title,
                x=x,
                y=y,
                properties=registry.default_properties(type_id),
                exposed_ports={port.key: port.exposed for port in spec.ports},
                parent_node_id=parent_node_id,
            )

        source = _add_node("core.constant", "Source", 0.0, 0.0)
        shell = _add_node("core.subnode", "Shell", 240.0, 40.0)
        pin_in = _add_node("core.subnode_input", "Input", 40.0, 80.0, parent_node_id=shell.node_id)
        inner = _add_node("core.logger", "Inner", 320.0, 140.0, parent_node_id=shell.node_id)

        mutations.set_exposed_port(shell.node_id, pin_in.node_id, True)

        shell_edge = mutations.add_edge(
            source_node_id=source.node_id,
            source_port_key="value",
            target_node_id=shell.node_id,
            target_port_key=pin_in.node_id,
        )
        inner_edge = mutations.add_edge(
            source_node_id=pin_in.node_id,
            source_port_key="pin",
            target_node_id=inner.node_id,
            target_port_key="message",
        )

        self.assertIn(shell_edge.edge_id, workspace.edges)
        self.assertIn(inner_edge.edge_id, workspace.edges)

        mutations.set_node_property(pin_in.node_id, "kind", "flow")

        self.assertNotIn(shell_edge.edge_id, workspace.edges)
        self.assertNotIn(inner_edge.edge_id, workspace.edges)
        self.assertEqual(workspace.nodes[pin_in.node_id].properties["kind"], "flow")

    def test_validated_mutation_rejects_descendant_parent_assignment(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        mutations = model.validated_mutations(workspace.workspace_id, registry)
        root = mutations.add_node(type_id="core.logger", title="Root", x=0.0, y=0.0)
        child = mutations.add_node(
            type_id="core.logger",
            title="Child",
            x=140.0,
            y=0.0,
            parent_node_id=root.node_id,
        )
        grandchild = mutations.add_node(
            type_id="core.logger",
            title="Grandchild",
            x=280.0,
            y=0.0,
            parent_node_id=child.node_id,
        )

        with self.assertRaises(ValueError):
            mutations.set_node_parent(root.node_id, grandchild.node_id)

        self.assertIsNone(workspace.nodes[root.node_id].parent_node_id)
        self.assertEqual(workspace.nodes[child.node_id].parent_node_id, root.node_id)
        self.assertEqual(workspace.nodes[grandchild.node_id].parent_node_id, child.node_id)

    def test_raw_parent_writer_rejects_self_missing_and_cycle_parent_links(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        root = model.add_node(workspace.workspace_id, "core.logger", "Root", 0.0, 0.0)
        child = model.add_node(workspace.workspace_id, "core.logger", "Child", 140.0, 0.0)
        grandchild = model.add_node(workspace.workspace_id, "core.logger", "Grandchild", 280.0, 0.0)
        model._set_node_parent_record(workspace.workspace_id, child.node_id, root.node_id)
        model._set_node_parent_record(workspace.workspace_id, grandchild.node_id, child.node_id)

        with self.assertRaises(ValueError):
            model._set_node_parent_record(workspace.workspace_id, root.node_id, root.node_id)
        with self.assertRaises(KeyError):
            model._set_node_parent_record(workspace.workspace_id, root.node_id, "missing-parent")
        with self.assertRaises(ValueError):
            model._set_node_parent_record(workspace.workspace_id, root.node_id, grandchild.node_id)

        self.assertIsNone(workspace.nodes[root.node_id].parent_node_id)
        self.assertEqual(workspace.nodes[child.node_id].parent_node_id, root.node_id)
        self.assertEqual(workspace.nodes[grandchild.node_id].parent_node_id, child.node_id)

    def test_graph_fragment_payload_validation_rejects_internal_parent_self_and_cycles(self) -> None:
        registry = build_default_registry()

        def _node_payload(ref_id: str, parent_node_id: str | None = None) -> dict[str, object]:
            return {
                "ref_id": ref_id,
                "type_id": "core.logger",
                "title": ref_id,
                "x": 0.0,
                "y": 0.0,
                "collapsed": False,
                "properties": {},
                "exposed_ports": {},
                "visual_style": {},
                "parent_node_id": parent_node_id,
                "custom_width": None,
                "custom_height": None,
            }

        self_parent_payload = build_graph_fragment_payload(nodes=[_node_payload("self", "self")], edges=[])
        cyclic_payload = build_graph_fragment_payload(
            nodes=[_node_payload("cycle-a", "cycle-b"), _node_payload("cycle-b", "cycle-a")],
            edges=[],
        )
        valid_nested_payload = build_graph_fragment_payload(
            nodes=[_node_payload("parent"), _node_payload("child", "parent")],
            edges=[],
        )

        self.assertFalse(graph_fragment_payload_is_valid(fragment_payload=self_parent_payload, registry=registry))
        self.assertFalse(graph_fragment_payload_is_valid(fragment_payload=cyclic_payload, registry=registry))
        self.assertTrue(graph_fragment_payload_is_valid(fragment_payload=valid_nested_payload, registry=registry))

    def test_fragment_insertion_drops_invalid_parent_links_without_corrupting_valid_topology(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace

        def _node_payload(
            ref_id: str,
            parent_node_id: str | None = None,
        ) -> dict[str, object]:
            return {
                "ref_id": ref_id,
                "type_id": "core.logger",
                "title": ref_id,
                "x": 0.0,
                "y": 0.0,
                "collapsed": False,
                "properties": {},
                "exposed_ports": {},
                "visual_style": {},
                "parent_node_id": parent_node_id,
                "custom_width": None,
                "custom_height": None,
            }

        fragment_payload = build_graph_fragment_payload(
            nodes=[
                _node_payload("valid-parent"),
                _node_payload("valid-child", "valid-parent"),
                _node_payload("self-parent", "self-parent"),
                _node_payload("cycle-a", "cycle-b"),
                _node_payload("cycle-b", "cycle-a"),
            ],
            edges=[],
        )

        inserted_node_ids = insert_graph_fragment(
            model=model,
            workspace_id=workspace.workspace_id,
            fragment_payload=fragment_payload,
            delta_x=0.0,
            delta_y=0.0,
        )

        self.assertEqual(len(inserted_node_ids), 5)
        inserted_by_title = {workspace.nodes[node_id].title: workspace.nodes[node_id] for node_id in inserted_node_ids}
        self.assertIsNone(inserted_by_title["valid-parent"].parent_node_id)
        self.assertEqual(
            inserted_by_title["valid-child"].parent_node_id,
            inserted_by_title["valid-parent"].node_id,
        )
        self.assertIsNone(inserted_by_title["self-parent"].parent_node_id)
        self.assertIsNone(inserted_by_title["cycle-a"].parent_node_id)
        self.assertIsNone(inserted_by_title["cycle-b"].parent_node_id)

    def test_fragment_insertion_preserves_data_tree_port_state(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node_payload = {
            "ref_id": "configured-node",
            "type_id": "core.logger",
            "title": "Configured Node",
            "x": 0.0,
            "y": 0.0,
            "collapsed": False,
            "expanded_settings_group_ids": ["options"],
            "properties": {},
            "exposed_ports": {},
            "port_modifiers": {"message": ["reverse", "clean"]},
            "principal_input_port_id": "message",
            "visual_style": {},
            "parent_node_id": None,
            "custom_width": None,
            "custom_height": None,
        }

        inserted_node_ids = insert_graph_fragment(
            model=model,
            workspace_id=workspace.workspace_id,
            fragment_payload=build_graph_fragment_payload(nodes=[node_payload], edges=[]),
            delta_x=0.0,
            delta_y=0.0,
        )

        self.assertEqual(len(inserted_node_ids), 1)
        inserted = workspace.nodes[inserted_node_ids[0]]
        self.assertEqual(inserted.port_modifiers, {"message": ("reverse", "clean")})
        self.assertEqual(inserted.principal_input_port_id, "message")
        self.assertEqual(inserted.expanded_settings_group_ids, ("options",))

    def test_fragment_insertion_normalizes_settings_groups_for_registry(self) -> None:
        registry = build_default_registry()
        spec = replace(
            registry.get_spec("core.logger"),
            type_id="tests.fragment_settings_groups",
            settings_groups=(
                SettingsGroupSpec(
                    group_id="general",
                    label="General",
                    items=(SettingsGroupItemSpec(property_key="message"),),
                ),
                SettingsGroupSpec(
                    group_id="plot",
                    label="Plot",
                    items=(SettingsGroupItemSpec(property_key="level"),),
                ),
            ),
        )
        registry.register_descriptor(spec, lambda: Mock())
        model = GraphModel()
        workspace = model.active_workspace
        payload = {
            "ref_id": "configured-node",
            "type_id": spec.type_id,
            "title": "Configured Node",
            "x": 0.0,
            "y": 0.0,
            "expanded_settings_group_ids": ["missing", "plot", "general", "plot"],
        }

        inserted_node_ids = insert_graph_fragment(
            model=model,
            workspace_id=workspace.workspace_id,
            fragment_payload=build_graph_fragment_payload(nodes=[payload], edges=[]),
            delta_x=0.0,
            delta_y=0.0,
            registry=registry,
        )

        inserted = workspace.nodes[inserted_node_ids[0]]
        self.assertEqual(inserted.expanded_settings_group_ids, ("general", "plot"))

    def test_workspace_view_mutation_manages_view_state_without_registry(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        service = model.workspace_view_mutations(workspace.workspace_id)
        self.assertIsInstance(service, WorkspaceViewMutation)
        start_revision = workspace.mutation_revision

        changed = service.save_active_view_state(
            zoom=1.25,
            pan_x=125.0,
            pan_y=220.0,
        )

        self.assertTrue(changed)
        self.assertGreater(workspace.mutation_revision, start_revision)
        active_view = service.active_view_state()
        self.assertAlmostEqual(active_view.zoom, 1.25, places=6)
        self.assertAlmostEqual(active_view.pan_x, 125.0, places=6)
        self.assertAlmostEqual(active_view.pan_y, 220.0, places=6)

        saved_revision = workspace.mutation_revision
        unchanged = service.save_active_view_state(
            zoom=1.25,
            pan_x=125.0,
            pan_y=220.0,
        )
        self.assertFalse(unchanged)
        self.assertEqual(workspace.mutation_revision, saved_revision)

        created_view = service.create_view(
            name="Review",
            source_view_id=active_view.view_id,
        )
        self.assertGreater(workspace.mutation_revision, saved_revision)
        self.assertEqual(workspace.active_view_id, created_view.view_id)
        self.assertEqual(created_view.name, "Review")
        self.assertAlmostEqual(created_view.zoom, 1.25, places=6)
        self.assertAlmostEqual(created_view.pan_x, 125.0, places=6)
        self.assertAlmostEqual(created_view.pan_y, 220.0, places=6)

        created_revision = workspace.mutation_revision
        service.set_active_view(active_view.view_id)
        self.assertGreater(workspace.mutation_revision, created_revision)
        self.assertEqual(workspace.active_view_id, active_view.view_id)

        selected_revision = workspace.mutation_revision
        service.set_active_view(active_view.view_id)
        self.assertEqual(workspace.mutation_revision, selected_revision)

        service.rename_view(active_view.view_id, "Main")
        self.assertGreater(workspace.mutation_revision, selected_revision)
        renamed_revision = workspace.mutation_revision
        service.rename_view(active_view.view_id, "Main")
        self.assertEqual(workspace.mutation_revision, renamed_revision)

        service.move_view(0, 1)
        self.assertGreater(workspace.mutation_revision, renamed_revision)
        moved_revision = workspace.mutation_revision

        service.close_view(created_view.view_id)
        self.assertGreater(workspace.mutation_revision, moved_revision)

    def test_project_document_epoch_tracks_project_and_workspace_document_changes(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        initial_epoch = model.project.document_epoch()

        self.assertFalse(model.project.replace_metadata(dict(model.project.metadata)))
        self.assertEqual(model.project.document_epoch(), initial_epoch)

        model.project.replace_metadata({"custom": "value"})
        metadata_epoch = model.project.document_epoch()
        self.assertNotEqual(metadata_epoch, initial_epoch)

        model.add_node(workspace.workspace_id, "core.constant", "Constant", 1.0, 2.0)
        graph_epoch = model.project.document_epoch()
        self.assertNotEqual(graph_epoch, metadata_epoch)

        model.workspace_view_mutations(workspace.workspace_id).save_active_view_state(
            zoom=1.5,
            pan_x=20.0,
            pan_y=-10.0,
        )
        view_epoch = model.project.document_epoch()
        self.assertNotEqual(view_epoch, graph_epoch)

        workspace.dirty = False
        dirty_epoch = model.project.document_epoch()
        self.assertNotEqual(dirty_epoch, view_epoch)

        second_workspace = model.create_workspace("Second")
        create_workspace_epoch = model.project.document_epoch()
        self.assertNotEqual(create_workspace_epoch, dirty_epoch)

        model.set_active_workspace(workspace.workspace_id)
        active_workspace_epoch = model.project.document_epoch()
        self.assertNotEqual(active_workspace_epoch, create_workspace_epoch)

        model.set_active_workspace(workspace.workspace_id)
        self.assertEqual(model.project.document_epoch(), active_workspace_epoch)
        self.assertIn(second_workspace.workspace_id, model.project.workspaces)

    def test_workspace_data_repairs_missing_active_view_for_view_mutations(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        service = model.workspace_view_mutations(workspace.workspace_id)

        first_view_id = workspace.active_view_id
        second_view = service.create_view(name="Secondary", source_view_id=first_view_id)
        self.assertEqual(workspace.active_view_id, second_view.view_id)

        create_revision = workspace.mutation_revision
        workspace.active_view_id = "missing_view"
        repaired_view = service.active_view_state()
        self.assertGreater(workspace.mutation_revision, create_revision)
        self.assertEqual(repaired_view.view_id, first_view_id)
        self.assertEqual(workspace.active_view_id, first_view_id)

        repair_revision = workspace.mutation_revision
        workspace.views = {}
        workspace.active_view_id = "missing_view"
        default_view = service.active_view_state()
        self.assertGreater(workspace.mutation_revision, repair_revision)
        self.assertEqual(workspace.active_view_id, default_view.view_id)
        self.assertEqual(list(workspace.views), [default_view.view_id])

    def test_hide_optional_ports_keeps_connected_optional_ports_and_hides_unused_ports(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        constant = model.add_node(workspace.workspace_id, "core.constant", "Constant", 40.0, 60.0)
        logger = model.add_node(workspace.workspace_id, "core.logger", "Logger", 260.0, 60.0)
        model.add_edge(workspace.workspace_id, constant.node_id, "as_text", logger.node_id, "message")
        workspace.views[workspace.active_view_id].hide_optional_ports = True

        payloads = self._node_payloads_by_title(model, registry)

        constant_ports = [str(port["key"]) for port in payloads["Constant"]["ports"]]
        logger_port_by_key = {
            str(port["key"]): port for port in payloads["Logger"]["ports"]
        }
        logger_ports = list(logger_port_by_key)
        self.assertEqual(constant_ports, ["as_text"])
        self.assertEqual(logger_ports, ["message"])
        self.assertTrue(logger_port_by_key["message"]["connected"])

    def test_hide_optional_ports_shrinks_height_metrics_and_zero_port_rows(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        model.add_node(workspace.workspace_id, "core.constant", "Constant", 40.0, 60.0)

        visible_payload = self._node_payloads_by_title(model, registry)["Constant"]
        workspace.views[workspace.active_view_id].hide_optional_ports = True
        hidden_payload = self._node_payloads_by_title(model, registry)["Constant"]

        port_height = float(visible_payload["surface_metrics"]["port_height"])
        expected_delta = port_height * 2.0
        self.assertEqual(hidden_payload["ports"], [])
        self.assertAlmostEqual(
            float(hidden_payload["height"]),
            max(
                float(hidden_payload["surface_metrics"]["min_height"]),
                float(visible_payload["height"]) - expected_delta,
            ),
        )
        self.assertAlmostEqual(
            float(visible_payload["surface_metrics"]["default_height"])
            - float(hidden_payload["surface_metrics"]["default_height"]),
            expected_delta,
        )
        self.assertLess(
            float(hidden_payload["surface_metrics"]["min_height"]),
            float(visible_payload["surface_metrics"]["min_height"]),
        )

    def test_hide_optional_ports_shrinks_custom_height_by_removed_rows(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(workspace.workspace_id, "core.constant", "Constant", 40.0, 60.0)
        node.custom_height = 260.0

        visible_payload = self._node_payloads_by_title(model, registry)["Constant"]
        workspace.views[workspace.active_view_id].hide_optional_ports = True
        hidden_payload = self._node_payloads_by_title(model, registry)["Constant"]

        expected_delta = float(visible_payload["surface_metrics"]["port_height"]) * 2.0
        self.assertAlmostEqual(float(visible_payload["height"]), 260.0)
        self.assertAlmostEqual(float(hidden_payload["height"]), 260.0 - expected_delta)

__all__ = ['GraphModelTrackBTests']
