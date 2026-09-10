import unittest
from unittest.mock import patch

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.record_mutation_ops import GraphRecordMutation
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


class GraphSceneDeleteIncidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()
        self.model = GraphModel()
        self.workspace_id = self.model.active_workspace.workspace_id
        self.workspace = self.model.project.workspaces[self.workspace_id]
        self.scene = GraphSceneBridge()
        self.scene.set_workspace(self.model, self.registry, self.workspace_id)

    def test_multi_delete_passes_precomputed_incident_edge_ids_per_node(self) -> None:
        node_a = self.scene.add_node_from_type("core.python_script", 0.0, 0.0)
        node_b = self.scene.add_node_from_type("core.python_script", 300.0, 0.0)
        external_source = self.scene.add_node_from_type("core.python_script", -300.0, 0.0)
        external_target = self.scene.add_node_from_type("core.python_script", 600.0, 0.0)

        edge_ab = self.model._add_edge_record(
            self.workspace_id,
            source_node_id=node_a,
            source_port_key="result",
            target_node_id=node_b,
            target_port_key="payload",
        ).edge_id
        edge_a_external = self.model._add_edge_record(
            self.workspace_id,
            source_node_id=node_a,
            source_port_key="result",
            target_node_id=external_target,
            target_port_key="payload",
        ).edge_id
        edge_external_b = self.model._add_edge_record(
            self.workspace_id,
            source_node_id=external_source,
            source_port_key="result",
            target_node_id=node_b,
            target_port_key="payload",
        ).edge_id
        non_incident_edge = self.model._add_edge_record(
            self.workspace_id,
            source_node_id=external_source,
            source_port_key="result",
            target_node_id=external_target,
            target_port_key="payload",
        ).edge_id
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.scene.select_node(node_a, False)
        self.scene.select_node(node_b, True)

        original_remove_node = GraphRecordMutation.remove_node
        remove_calls: dict[str, set[str] | None] = {}

        def _spy_remove_node(
            mutation: GraphRecordMutation,
            node_id: str,
            *,
            incident_edge_ids: set[str] | None = None,
        ) -> None:
            remove_calls[node_id] = None if incident_edge_ids is None else set(incident_edge_ids)
            original_remove_node(mutation, node_id, incident_edge_ids=incident_edge_ids)

        with patch.object(GraphRecordMutation, "remove_node", new=_spy_remove_node):
            deleted = self.scene.delete_selected_graph_items([])

        self.assertTrue(deleted)
        self.assertEqual(remove_calls[node_a], {edge_ab, edge_a_external})
        self.assertEqual(remove_calls[node_b], {edge_ab, edge_external_b})
        self.assertNotIn(non_incident_edge, remove_calls[node_a] or set())
        self.assertNotIn(non_incident_edge, remove_calls[node_b] or set())
        self.assertNotIn(node_a, self.workspace.nodes)
        self.assertNotIn(node_b, self.workspace.nodes)
        self.assertIn(external_source, self.workspace.nodes)
        self.assertIn(external_target, self.workspace.nodes)


if __name__ == "__main__":
    unittest.main()
