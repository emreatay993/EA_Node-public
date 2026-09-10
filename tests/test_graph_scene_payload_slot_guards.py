"""Slot-identity and duplicate-payload guards for the phantom/duplicate node bug.

The duplicated-viewer report pinned the corruption signature:
a stale ``node_payload_location_by_id`` entry lets a keyed payload-cache write
clobber ANOTHER node's slot, leaving one node's payload duplicated (stale copy
at the old position + fresh copy in the clobbered slot) and the clobbered
node's payload destroyed. Downstream the visible model rendered both copies.

These tests pin the defenses:
- keyed cache writes verify the slot still belongs to the node and fall back
  to a full rebuild on mismatch (``resolve_node_payload_slot``),
- the visible models refuse to render duplicate node_ids: rows are deduped,
  the event is counted, and a deferred scene resync restores ground truth.
"""
from __future__ import annotations

import unittest

from PyQt6.QtCore import QCoreApplication

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_canvas_visible_model import GraphCanvasVisibleModel
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


def _ensure_app() -> QCoreApplication:
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


class _PayloadGuardHarness(unittest.TestCase):
    def _build_scene(self) -> tuple[GraphSceneBridge, GraphModel, str]:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        scene.bind_runtime_history(RuntimeGraphHistory())
        return scene, model, workspace_id

    def _build_three_nodes(self, scene: GraphSceneBridge) -> tuple[str, str, str]:
        node_a = scene.add_node_from_type("core.constant", 80.0, 60.0)
        node_b = scene.add_node_from_type("core.logger", 320.0, 60.0)
        node_c = scene.add_node_from_type("core.python_script", 560.0, 60.0)
        return node_a, node_b, node_c

    def _corrupt_location_map(self, scene: GraphSceneBridge, node_a: str, node_b: str) -> None:
        """Swap two nodes' location-index entries while leaving the payload
        collections untouched — the stale-index precondition of the bug."""
        scene.nodes_model  # noqa: B018 - force the payload cache current
        cache = scene._payload_cache  # noqa: SLF001
        if not cache.indexes_valid:
            cache.rebuild_indexes()
        location_a = cache.node_payload_location_by_id[node_a]
        location_b = cache.node_payload_location_by_id[node_b]
        cache.node_payload_location_by_id[node_a] = location_b
        cache.node_payload_location_by_id[node_b] = location_a

    def _assert_cache_consistent(self, scene: GraphSceneBridge, model: GraphModel, workspace_id: str) -> None:
        workspace = model.project.workspaces[workspace_id]
        payloads = [p for p in scene.nodes_model if isinstance(p, dict)]
        payload_ids = [str(p.get("node_id", "")) for p in payloads]
        self.assertEqual(sorted(payload_ids), sorted(workspace.nodes.keys()))
        self.assertEqual(len(payload_ids), len(set(payload_ids)), "duplicate payload ids in cache")
        for payload in payloads:
            node = workspace.nodes[str(payload.get("node_id", ""))]
            self.assertEqual(float(payload.get("x", 0.0)), float(node.x))
            self.assertEqual(float(payload.get("y", 0.0)), float(node.y))


class PayloadCacheSlotIdentityGuardTests(_PayloadGuardHarness):
    def test_resolve_node_payload_slot_reports_mismatch(self) -> None:
        scene, model, workspace_id = self._build_scene()
        node_a, node_b, _ = self._build_three_nodes(scene)
        self._corrupt_location_map(scene, node_a, node_b)
        cache = scene._payload_cache  # noqa: SLF001

        status, location = cache.resolve_node_payload_slot(node_a)

        self.assertEqual(status, "mismatch")
        self.assertIsNone(location)
        self.assertGreaterEqual(cache.slot_identity_mismatch_count, 1)
        self.assertEqual(cache.resolve_node_payload_slot("node_missing")[0], "absent")

    def test_move_with_stale_location_map_rebuilds_instead_of_clobbering(self) -> None:
        scene, model, workspace_id = self._build_scene()
        node_a, node_b, node_c = self._build_three_nodes(scene)
        self._corrupt_location_map(scene, node_a, node_b)

        scene.move_node(node_a, 500.0, 400.0)

        workspace = model.project.workspaces[workspace_id]
        self.assertEqual(float(workspace.nodes[node_a].x), 500.0)
        self._assert_cache_consistent(scene, model, workspace_id)
        self.assertGreaterEqual(scene._payload_cache.slot_identity_mismatch_count, 1)  # noqa: SLF001

    def test_full_payload_delta_with_stale_location_map_rebuilds(self) -> None:
        scene, model, workspace_id = self._build_scene()
        node_a, node_b, _ = self._build_three_nodes(scene)
        self._corrupt_location_map(scene, node_a, node_b)

        result = scene._scene_context.publish_node_payload_delta(node_a)  # noqa: SLF001

        self.assertTrue(result)
        self._assert_cache_consistent(scene, model, workspace_id)
        self.assertGreaterEqual(scene._payload_cache.slot_identity_mismatch_count, 1)  # noqa: SLF001

    def test_title_delta_with_stale_location_map_rebuilds(self) -> None:
        scene, model, workspace_id = self._build_scene()
        node_a, node_b, _ = self._build_three_nodes(scene)
        self._corrupt_location_map(scene, node_a, node_b)

        result = scene._scene_context.publish_node_title_payload_delta(node_a)  # noqa: SLF001

        self.assertTrue(result)
        self._assert_cache_consistent(scene, model, workspace_id)
        self.assertGreaterEqual(scene._payload_cache.slot_identity_mismatch_count, 1)  # noqa: SLF001


class VisibleModelDuplicateGuardTests(_PayloadGuardHarness):
    def test_sync_payloads_dedupes_duplicate_node_ids(self) -> None:
        _ensure_app()
        model = GraphCanvasVisibleModel()
        detected: list[list[str]] = []
        model.duplicate_node_ids_detected.connect(detected.append)

        first = {"node_id": "n1", "x": 10.0}
        stale_duplicate = {"node_id": "n1", "x": 999.0}
        model.sync_payloads([first, {"node_id": "n2", "x": 20.0}, stale_duplicate])

        self.assertEqual(len(model), 2)
        self.assertEqual([p["node_id"] for p in model.payloads()], ["n1", "n2"])
        self.assertEqual(model.payloads()[0]["x"], 10.0)  # keeps first occurrence
        self.assertEqual(detected, [["n1"]])
        self.assertEqual(model.duplicate_payload_sync_count, 1)
        self.assertEqual(model.last_duplicate_node_ids, ("n1",))

        model.sync_payloads([{"node_id": "n1", "x": 11.0}, {"node_id": "n2", "x": 20.0}])
        self.assertEqual(detected, [["n1"]])  # clean sync does not re-report

    def test_screenshot_shape_corruption_self_heals(self) -> None:
        """Pin the exact 2026-07-03 corruption shape end to end: node A's
        payload duplicated (stale + fresh copy) with node B's payload
        destroyed must never render two copies of A, and the deferred resync
        must restore all nodes from the graph model."""
        app = _ensure_app()
        scene, model, workspace_id = self._build_scene()
        node_a, node_b, node_c = self._build_three_nodes(scene)
        state_bridge = GraphCanvasStateBridge(scene_bridge=scene)
        state_bridge.force_visible_scene_models_exact()

        cache = scene._payload_cache  # noqa: SLF001
        if not cache.indexes_valid:
            cache.rebuild_indexes()
        slot_a = cache.node_payload_location_by_id[node_a]
        slot_b = cache.node_payload_location_by_id[node_b]
        self.assertEqual(slot_a[0], "nodes")
        self.assertEqual(slot_b[0], "nodes")
        # Simulate the clobber: A's fresh payload lands in B's slot while A's
        # own slot keeps a stale copy at another position. B's payload is gone.
        stale_copy = dict(cache.nodes[slot_a[1]])
        stale_copy["x"] = 1220.0
        stale_copy["y"] = 0.0
        cache.nodes[slot_b[1]] = dict(cache.nodes[slot_a[1]])
        cache.nodes[slot_a[1]] = stale_copy
        setattr(scene.state_bridge, "node_delta_payload", {})
        scene.nodes_changed.emit()
        state_bridge.force_visible_scene_models_exact()

        rows = [r for r in state_bridge._visible_nodes_model.payloads() if isinstance(r, dict)]  # noqa: SLF001
        row_ids = [str(r.get("node_id", "")) for r in rows]
        self.assertEqual(len(row_ids), len(set(row_ids)), "visible model rendered duplicate node ids")
        diagnostics = state_bridge.visible_scene_model_diagnostics
        self.assertGreaterEqual(int(diagnostics["duplicate_payload_detection_count"]), 1)
        self.assertIn(node_a, list(diagnostics["duplicate_payload_last_node_ids"]))

        app.processEvents()  # run the deferred resync
        state_bridge.force_visible_scene_models_exact()

        self._assert_cache_consistent(scene, model, workspace_id)
        rows = [r for r in state_bridge._visible_nodes_model.payloads() if isinstance(r, dict)]  # noqa: SLF001
        row_ids = sorted(str(r.get("node_id", "")) for r in rows)
        self.assertEqual(row_ids, sorted([node_a, node_b, node_c]))
        workspace = model.project.workspaces[workspace_id]
        for row in rows:
            node = workspace.nodes[str(row.get("node_id", ""))]
            self.assertEqual(float(row.get("x", 0.0)), float(node.x))
            self.assertEqual(float(row.get("y", 0.0)), float(node.y))
        diagnostics = state_bridge.visible_scene_model_diagnostics
        self.assertGreaterEqual(int(diagnostics["duplicate_payload_resync_count"]), 1)


if __name__ == "__main__":
    unittest.main()
