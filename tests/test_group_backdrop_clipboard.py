from __future__ import annotations

import unittest

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

GROUP_BACKDROP_TYPE_ID = "passive.annotation.group_backdrop"


class GroupBackdropClipboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()
        self.model = GraphModel()
        self.workspace_id = self.model.active_workspace.workspace_id
        self.scene = GraphSceneBridge()
        self.scene.set_workspace(self.model, self.registry, self.workspace_id)

    def _scene_payload(self, node_id: str) -> dict[str, object]:
        for payload in [*self.scene.nodes_model, *self.scene.backdrop_nodes_model]:
            if str(payload.get("node_id", "")) == str(node_id):
                return payload
        raise AssertionError(f"Node payload {node_id!r} was not found.")

    def _wrap_nodes_in_group_backdrop(self, node_ids: list[str], *, collapsed: bool = False) -> str:
        backdrop_id = self.scene.wrap_node_ids_in_group_backdrop(node_ids)
        self.assertTrue(backdrop_id)
        self.scene.set_node_collapsed(backdrop_id, collapsed)
        return backdrop_id

    def test_expanded_group_backdrop_copy_keeps_descendants_explicit_only(self) -> None:
        logger_id = self.scene.add_node_from_type("core.logger", 110.0, 110.0)
        backdrop_id = self._wrap_nodes_in_group_backdrop([logger_id], collapsed=False)
        self.assertEqual(self._scene_payload(logger_id)["owner_backdrop_id"], backdrop_id)

        self.scene.select_node(backdrop_id, False)
        fragment = self.scene.serialize_selected_subgraph_fragment()

        self.assertIsNotNone(fragment)
        assert fragment is not None
        self.assertEqual({node["ref_id"] for node in fragment["nodes"]}, {backdrop_id})
        self.assertEqual(fragment["edges"], [])

    def test_wrap_group_backdrop_publishes_membership_delta_without_rebuild(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 110.0, 110.0)
        target_id = self.scene.add_node_from_type("core.python_script", 320.0, 130.0)
        nodes_changed: list[str] = []
        rebuild_calls: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            backdrop_id = self.scene.wrap_node_ids_in_group_backdrop([source_id, target_id])
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertTrue(backdrop_id)
        self.assertEqual(rebuild_calls, [])
        self.assertEqual(nodes_changed, ["nodes"])
        self.assertEqual(self._scene_payload(source_id)["owner_backdrop_id"], backdrop_id)
        self.assertEqual(self._scene_payload(target_id)["owner_backdrop_id"], backdrop_id)
        self.assertEqual(set(self._scene_payload(backdrop_id)["member_node_ids"]), {source_id, target_id})
        node_delta = getattr(self.scene.state_bridge, "node_delta_payload", {})
        self.assertEqual(node_delta["reason"], "group_backdrop_addition_delta")
        self.assertEqual(node_delta["added_node_ids"], [backdrop_id])
        self.assertEqual(
            {payload["node_id"] for payload in node_delta["nodes"]},
            {source_id, target_id},
        )
        self.assertEqual(
            {payload["node_id"] for payload in node_delta["backdrop_nodes"]},
            {backdrop_id},
        )

    def test_add_node_inside_expanded_group_backdrop_publishes_membership_delta(self) -> None:
        logger_id = self.scene.add_node_from_type("core.logger", 110.0, 110.0)
        backdrop_id = self._wrap_nodes_in_group_backdrop([logger_id], collapsed=False)
        nodes_changed: list[str] = []
        rebuild_calls: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            added_id = self.scene.add_node_from_type("core.constant", 130.0, 125.0)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertTrue(added_id)
        self.assertEqual(rebuild_calls, [])
        self.assertEqual(nodes_changed, ["nodes"])
        self.assertEqual(self._scene_payload(added_id)["owner_backdrop_id"], backdrop_id)
        self.assertEqual(
            set(self._scene_payload(backdrop_id)["member_node_ids"]),
            {logger_id, added_id},
        )
        node_delta = getattr(self.scene.state_bridge, "node_delta_payload", {})
        self.assertEqual(node_delta["reason"], "node_addition_delta")
        self.assertEqual(node_delta["added_node_ids"], [added_id])
        self.assertEqual(
            {payload["node_id"] for payload in node_delta["nodes"]},
            {added_id},
        )
        self.assertEqual(
            {payload["node_id"] for payload in node_delta["backdrop_nodes"]},
            {backdrop_id},
        )

    def test_add_node_with_collapsed_group_backdrop_falls_back_to_rebuild(self) -> None:
        logger_id = self.scene.add_node_from_type("core.logger", 110.0, 110.0)
        self._wrap_nodes_in_group_backdrop([logger_id], collapsed=True)
        rebuild_calls: list[str] = []
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _record_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _record_rebuild_models
        try:
            added_id = self.scene.add_node_from_type("core.constant", 130.0, 125.0)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertTrue(added_id)
        self.assertEqual(rebuild_calls, ["rebuild"])

    def test_collapsed_group_backdrop_copy_includes_recursive_descendants_and_internal_edges(self) -> None:
        inner_source_id = self.scene.add_node_from_type("core.constant", 220.0, 160.0)
        inner_backdrop_id = self._wrap_nodes_in_group_backdrop([inner_source_id], collapsed=False)
        outer_target_id = self.scene.add_node_from_type("core.python_script", 220.0, 360.0)
        outside_script_id = self.scene.add_node_from_type("core.python_script", 760.0, 240.0)
        self.scene.add_edge(inner_source_id, "value", outer_target_id, "payload")
        self.scene.add_edge(inner_source_id, "value", outside_script_id, "payload")
        outer_backdrop_id = self._wrap_nodes_in_group_backdrop([inner_backdrop_id, outer_target_id], collapsed=True)

        self.scene.select_node(outer_backdrop_id, False)
        fragment = self.scene.serialize_selected_subgraph_fragment()

        self.assertIsNotNone(fragment)
        assert fragment is not None
        self.assertEqual(
            {node["ref_id"] for node in fragment["nodes"]},
            {outer_backdrop_id, inner_backdrop_id, inner_source_id, outer_target_id},
        )
        self.assertEqual(
            {
                (
                    edge["source_ref_id"],
                    edge["source_port_key"],
                    edge["target_ref_id"],
                    edge["target_port_key"],
                )
                for edge in fragment["edges"]
            },
            {(inner_source_id, "value", outer_target_id, "payload")},
        )

    def test_duplicate_selected_collapsed_group_backdrop_recomputes_membership_for_duplicates(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 280.0, 220.0)
        backdrop_id = self._wrap_nodes_in_group_backdrop([source_id], collapsed=True)
        workspace = self.model.project.workspaces[self.workspace_id]
        before_node_ids = set(workspace.nodes)

        self.scene.select_node(backdrop_id, False)
        duplicated = self.scene.duplicate_selected_subgraph()

        self.assertTrue(duplicated)
        new_node_ids = set(workspace.nodes) - before_node_ids
        self.assertEqual(len(new_node_ids), 2)

        duplicate_backdrop_id = next(
            node_id
            for node_id in new_node_ids
            if workspace.nodes[node_id].type_id == GROUP_BACKDROP_TYPE_ID
        )
        duplicate_source_id = next(
            node_id
            for node_id in new_node_ids
            if workspace.nodes[node_id].type_id == "core.constant"
        )
        self.assertAlmostEqual(workspace.nodes[duplicate_backdrop_id].x, workspace.nodes[backdrop_id].x + 40.0, places=6)
        self.assertAlmostEqual(workspace.nodes[duplicate_backdrop_id].y, workspace.nodes[backdrop_id].y + 40.0, places=6)
        self.assertAlmostEqual(workspace.nodes[duplicate_source_id].x, workspace.nodes[source_id].x + 40.0, places=6)
        self.assertAlmostEqual(workspace.nodes[duplicate_source_id].y, workspace.nodes[source_id].y + 40.0, places=6)

        self.scene.set_node_collapsed(duplicate_backdrop_id, False)
        duplicate_backdrop_payload = self._scene_payload(duplicate_backdrop_id)
        duplicate_source_payload = self._scene_payload(duplicate_source_id)
        self.assertEqual(duplicate_source_payload["owner_backdrop_id"], duplicate_backdrop_id)
        self.assertEqual(duplicate_backdrop_payload["member_node_ids"], [duplicate_source_id])

    def test_delete_selected_expanded_group_backdrop_keeps_descendants(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 110.0, 110.0)
        backdrop_id = self._wrap_nodes_in_group_backdrop([source_id], collapsed=False)
        workspace = self.model.project.workspaces[self.workspace_id]

        self.scene.select_node(backdrop_id, False)
        deleted = self.scene.delete_selected_graph_items([])

        self.assertTrue(deleted)
        self.assertNotIn(backdrop_id, workspace.nodes)
        self.assertIn(source_id, workspace.nodes)

    def test_delete_selected_collapsed_group_backdrop_removes_recursive_descendants(self) -> None:
        inner_source_id = self.scene.add_node_from_type("core.constant", 220.0, 160.0)
        inner_backdrop_id = self._wrap_nodes_in_group_backdrop([inner_source_id], collapsed=False)
        outer_target_id = self.scene.add_node_from_type("core.python_script", 220.0, 360.0)
        outside_script_id = self.scene.add_node_from_type("core.python_script", 760.0, 240.0)
        self.scene.add_edge(inner_source_id, "value", outer_target_id, "payload")
        self.scene.add_edge(inner_source_id, "value", outside_script_id, "payload")
        outer_backdrop_id = self._wrap_nodes_in_group_backdrop([inner_backdrop_id, outer_target_id], collapsed=True)
        workspace = self.model.project.workspaces[self.workspace_id]

        self.scene.select_node(outer_backdrop_id, False)
        deleted = self.scene.delete_selected_graph_items([])

        self.assertTrue(deleted)
        for removed_node_id in (outer_backdrop_id, inner_backdrop_id, inner_source_id, outer_target_id):
            self.assertNotIn(removed_node_id, workspace.nodes)
        self.assertIn(outside_script_id, workspace.nodes)
        self.assertEqual(list(workspace.edges), [])


if __name__ == "__main__":
    unittest.main()
