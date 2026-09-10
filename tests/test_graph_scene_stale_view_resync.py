"""Mutations that reference a node the model cannot resolve must resync the
scene instead of silently no-opping.

Regression coverage for the "phantom node" report: a stale payload row kept
rendering an inert node that ignored delete/drag/resize until app restart,
because every mutation gate returned False without flushing the stale view.
"""
from __future__ import annotations

import unittest

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui.graph_interactions import GraphInteractions
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


class StaleSceneViewResyncTests(unittest.TestCase):
    def _build_scene(self) -> tuple[GraphSceneBridge, GraphModel, str]:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        scene.bind_runtime_history(RuntimeGraphHistory())
        return scene, model, workspace_id

    def _payload_node_ids(self, scene: GraphSceneBridge) -> set[str]:
        return {str(payload.get("node_id", "")) for payload in scene.nodes_model}

    def _desync_node_from_model(self, scene: GraphSceneBridge, model: GraphModel, workspace_id: str) -> tuple[str, str]:
        """Create two nodes, then drop one from the model without a scene
        publication — the desynced state the phantom-node bug leaves behind."""
        stale_id = scene.add_node_from_type("core.constant", 80.0, 60.0)
        kept_id = scene.add_node_from_type("core.logger", 320.0, 60.0)
        workspace = model.project.workspaces[workspace_id]
        del workspace.nodes[stale_id]
        self.assertIn(stale_id, self._payload_node_ids(scene))
        return stale_id, kept_id

    def test_remove_node_on_model_missing_node_flushes_stale_payload(self) -> None:
        scene, model, workspace_id = self._build_scene()
        stale_id, kept_id = self._desync_node_from_model(scene, model, workspace_id)

        scene.remove_node(stale_id)

        refreshed = self._payload_node_ids(scene)
        self.assertNotIn(stale_id, refreshed)
        self.assertIn(kept_id, refreshed)

    def test_remove_node_on_out_of_scope_node_flushes_stale_payload(self) -> None:
        scene, model, workspace_id = self._build_scene()
        stale_id = scene.add_node_from_type("core.constant", 80.0, 60.0)
        kept_id = scene.add_node_from_type("core.logger", 320.0, 60.0)
        anchor_id = scene.add_node_from_type("core.python_script", 560.0, 60.0)
        workspace = model.project.workspaces[workspace_id]
        # Reparent without a scene publication: the root payload keeps showing
        # the node while the root-scope delete gate now rejects it.
        workspace.nodes[stale_id].parent_node_id = anchor_id
        self.assertIn(stale_id, self._payload_node_ids(scene))

        scene.remove_node(stale_id)

        refreshed = self._payload_node_ids(scene)
        self.assertNotIn(stale_id, refreshed)
        self.assertIn(kept_id, refreshed)
        self.assertIn(stale_id, workspace.nodes)  # out-of-scope node is kept

    def test_move_node_on_model_missing_node_flushes_stale_payload(self) -> None:
        scene, model, workspace_id = self._build_scene()
        stale_id, kept_id = self._desync_node_from_model(scene, model, workspace_id)

        scene.move_node(stale_id, 500.0, 400.0)

        refreshed = self._payload_node_ids(scene)
        self.assertNotIn(stale_id, refreshed)
        self.assertIn(kept_id, refreshed)

    def test_move_nodes_by_delta_with_stale_id_flushes_stale_payload(self) -> None:
        scene, model, workspace_id = self._build_scene()
        stale_id, kept_id = self._desync_node_from_model(scene, model, workspace_id)

        moved = scene.move_nodes_by_delta([stale_id, kept_id], 40.0, 0.0)

        self.assertTrue(moved)  # the resolvable node still moves
        refreshed = self._payload_node_ids(scene)
        self.assertNotIn(stale_id, refreshed)
        kept_payload = {p["node_id"]: p for p in scene.nodes_model}[kept_id]
        self.assertEqual(float(kept_payload["x"]), 360.0)

    def test_set_node_geometry_on_model_missing_node_flushes_stale_payload(self) -> None:
        scene, model, workspace_id = self._build_scene()
        stale_id, kept_id = self._desync_node_from_model(scene, model, workspace_id)

        scene.set_node_geometry(stale_id, 10.0, 10.0, 400.0, 300.0)

        refreshed = self._payload_node_ids(scene)
        self.assertNotIn(stale_id, refreshed)
        self.assertIn(kept_id, refreshed)

    def test_graph_action_remove_node_resyncs_when_node_missing(self) -> None:
        scene, model, workspace_id = self._build_scene()
        stale_id, kept_id = self._desync_node_from_model(scene, model, workspace_id)
        actions = GraphInteractions(scene, build_default_registry())

        result = actions.remove_node(stale_id)

        self.assertFalse(result.ok)
        refreshed = self._payload_node_ids(scene)
        self.assertNotIn(stale_id, refreshed)
        self.assertIn(kept_id, refreshed)

    def test_stale_resync_flushes_visible_scene_model(self) -> None:
        scene, model, workspace_id = self._build_scene()
        state_bridge = GraphCanvasStateBridge(scene_bridge=scene)
        state_bridge.force_visible_scene_models_exact()
        stale_id, kept_id = self._desync_node_from_model(scene, model, workspace_id)
        state_bridge.force_visible_scene_models_exact()
        visible_before = {
            str(payload.get("node_id", ""))
            for payload in state_bridge.visible_nodes_payloads
        }
        self.assertIn(stale_id, visible_before)

        scene.remove_node(stale_id)
        state_bridge.force_visible_scene_models_exact()

        visible_after = {
            str(payload.get("node_id", ""))
            for payload in state_bridge.visible_nodes_payloads
        }
        self.assertNotIn(stale_id, visible_after)
        self.assertIn(kept_id, visible_after)

    def test_remove_node_with_valid_node_still_removes(self) -> None:
        scene, model, workspace_id = self._build_scene()
        node_id = scene.add_node_from_type("core.logger", 100.0, 100.0)

        scene.remove_node(node_id)

        self.assertNotIn(node_id, model.project.workspaces[workspace_id].nodes)
        self.assertNotIn(node_id, self._payload_node_ids(scene))


if __name__ == "__main__":
    unittest.main()
