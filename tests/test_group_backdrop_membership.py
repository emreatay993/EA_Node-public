from __future__ import annotations

from collections.abc import Callable
import unittest

from ea_node_editor.graph.group_backdrop_geometry import (
    GROUP_BACKDROP_WRAP_BOTTOM_PADDING,
    GroupBackdropCandidate,
    build_group_backdrop_wrap_bounds,
    compute_group_backdrop_membership,
)
from ea_node_editor.graph.group_backdrop_mutation_ops import wrap_selection_in_group_backdrop
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.subnode_contract import SUBNODE_TYPE_ID
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

GROUP_BACKDROP_TYPE_ID = "passive.annotation.group_backdrop"
LOGGER_TYPE_ID = "core.logger"


class GroupBackdropGeometryTests(unittest.TestCase):
    def test_compute_membership_prefers_smallest_full_container_in_same_scope(self) -> None:
        membership = compute_group_backdrop_membership(
            [
                GroupBackdropCandidate("outer", (), True, 0.0, 0.0, 420.0, 320.0),
                GroupBackdropCandidate("inner", (), True, 60.0, 50.0, 200.0, 160.0),
                GroupBackdropCandidate("inner_node", (), False, 100.0, 100.0, 40.0, 40.0),
                GroupBackdropCandidate("outer_node", (), False, 300.0, 120.0, 40.0, 40.0),
                GroupBackdropCandidate("partial_node", (), False, 390.0, 100.0, 60.0, 60.0),
                GroupBackdropCandidate("other_scope_node", ("subnode",), False, 80.0, 80.0, 40.0, 40.0),
            ]
        )

        self.assertIsNone(membership["outer"].owner_backdrop_id)
        self.assertEqual(membership["outer"].backdrop_depth, 0)
        self.assertEqual(membership["outer"].member_node_ids, ("outer_node",))
        self.assertEqual(membership["outer"].member_backdrop_ids, ("inner",))
        self.assertEqual(membership["outer"].contained_node_ids, ("inner_node", "outer_node"))
        self.assertEqual(membership["outer"].contained_backdrop_ids, ("inner",))

        self.assertEqual(membership["inner"].owner_backdrop_id, "outer")
        self.assertEqual(membership["inner"].backdrop_depth, 1)
        self.assertEqual(membership["inner"].member_node_ids, ("inner_node",))
        self.assertEqual(membership["inner"].member_backdrop_ids, ())
        self.assertEqual(membership["inner"].contained_node_ids, ("inner_node",))
        self.assertEqual(membership["inner"].contained_backdrop_ids, ())

        self.assertEqual(membership["inner_node"].owner_backdrop_id, "inner")
        self.assertEqual(membership["inner_node"].backdrop_depth, 2)
        self.assertEqual(membership["outer_node"].owner_backdrop_id, "outer")
        self.assertEqual(membership["outer_node"].backdrop_depth, 1)
        self.assertIsNone(membership["partial_node"].owner_backdrop_id)
        self.assertEqual(membership["partial_node"].backdrop_depth, 0)
        self.assertIsNone(membership["other_scope_node"].owner_backdrop_id)
        self.assertEqual(membership["other_scope_node"].backdrop_depth, 0)

    def test_wrap_bounds_enforce_minimum_width_and_bottom_padding(self) -> None:
        bounds = build_group_backdrop_wrap_bounds(
            [
                GroupBackdropCandidate("node", (), False, 100.0, 200.0, 50.0, 30.0),
            ]
        )

        self.assertIsNotNone(bounds)
        assert bounds is not None
        self.assertEqual(bounds.x, 5.0)
        self.assertEqual(bounds.y, 104.0)
        self.assertEqual(bounds.width, 240.0)
        self.assertEqual(bounds.height, 182.0)
        self.assertEqual(bounds.y + bounds.height - 230.0, GROUP_BACKDROP_WRAP_BOTTOM_PADDING)

    def test_wrap_bounds_preserve_padding_when_selection_exceeds_minimum(self) -> None:
        bounds = build_group_backdrop_wrap_bounds(
            [
                GroupBackdropCandidate("first", (), False, 100.0, 100.0, 210.0, 132.0),
                GroupBackdropCandidate("second", (), False, 380.0, 250.0, 210.0, 132.0),
            ]
        )

        self.assertIsNotNone(bounds)
        assert bounds is not None
        self.assertEqual(bounds.x, 68.0)
        self.assertEqual(bounds.y, 4.0)
        self.assertEqual(bounds.width, 554.0)
        self.assertEqual(bounds.height, 434.0)
        self.assertEqual(bounds.y + bounds.height - 382.0, GROUP_BACKDROP_WRAP_BOTTOM_PADDING)


class GroupBackdropSceneIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()
        self.model = GraphModel()
        self.workspace_id = self.model.active_workspace.workspace_id
        self.scene = GraphSceneBridge()
        self.scene.set_workspace(self.model, self.registry, self.workspace_id)

    def test_wrap_selected_nodes_is_a_noop_without_selection(self) -> None:
        self.assertFalse(self.scene.wrap_selected_nodes_in_group_backdrop())

    def _scene_payload(self, node_id: str) -> dict[str, object]:
        for payload in [*self.scene.nodes_model, *self.scene.backdrop_nodes_model]:
            if str(payload["node_id"]) == str(node_id):
                return payload
        raise AssertionError(f"Node payload {node_id!r} was not found.")

    def _install_rebuild_recorder(self) -> tuple[list[str], Callable[[], None]]:
        rebuild_calls: list[str] = []
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _recording_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _recording_rebuild_models
        return rebuild_calls, original_rebuild_models

    def _workspace_group_backdrop_ids(self) -> list[str]:
        workspace = self.model.project.workspaces[self.workspace_id]
        return [
            node_id
            for node_id, node in workspace.nodes.items()
            if node.type_id == GROUP_BACKDROP_TYPE_ID
        ]

    def _add_workspace_node(
        self,
        type_id: str,
        x: float,
        y: float,
        *,
        parent_node_id: str | None = None,
    ) -> str:
        service = self.model.validated_mutations(self.workspace_id, self.registry)
        spec = self.registry.get_spec(type_id)
        node = service.add_node(
            type_id=type_id,
            title=spec.display_name,
            x=float(x),
            y=float(y),
            properties=self.registry.default_properties(type_id),
            exposed_ports={port.key: port.exposed for port in spec.ports},
            parent_node_id=parent_node_id,
        )
        return node.node_id

    def test_scene_membership_rebuilds_after_bridge_move_and_explicit_refresh(self) -> None:
        logger_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 180.0, 140.0)
        backdrop_id = self.scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, 100.0, 100.0)
        self.scene.set_node_geometry(backdrop_id, 100.0, 100.0, 400.0, 260.0)

        logger_payload = self._scene_payload(logger_id)
        backdrop_payload = self._scene_payload(backdrop_id)
        self.assertEqual(logger_payload["owner_backdrop_id"], backdrop_id)
        self.assertEqual(logger_payload["backdrop_depth"], 1)
        self.assertEqual(backdrop_payload["member_node_ids"], [logger_id])
        self.assertEqual(backdrop_payload["contained_node_ids"], [logger_id])

        self.scene.move_node(logger_id, 520.0, 520.0)
        logger_payload = self._scene_payload(logger_id)
        backdrop_payload = self._scene_payload(backdrop_id)
        self.assertEqual(logger_payload["owner_backdrop_id"], "")
        self.assertEqual(logger_payload["backdrop_depth"], 0)
        self.assertEqual(backdrop_payload["member_node_ids"], [])
        self.assertEqual(backdrop_payload["contained_node_ids"], [])

        self.model.set_node_position(self.workspace_id, logger_id, 180.0, 140.0)
        self.scene.refresh_workspace_from_model(self.workspace_id)
        logger_payload = self._scene_payload(logger_id)
        backdrop_payload = self._scene_payload(backdrop_id)
        self.assertEqual(logger_payload["owner_backdrop_id"], backdrop_id)
        self.assertEqual(logger_payload["backdrop_depth"], 1)
        self.assertEqual(backdrop_payload["member_node_ids"], [logger_id])
        self.assertEqual(backdrop_payload["contained_node_ids"], [logger_id])

    def test_move_inside_group_backdrop_publishes_delta_without_full_rebuild(self) -> None:
        logger_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 180.0, 140.0)
        backdrop_id = self.scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, 100.0, 100.0)
        self.scene.set_node_geometry(backdrop_id, 100.0, 100.0, 400.0, 260.0)
        self.assertEqual(self._scene_payload(logger_id)["owner_backdrop_id"], backdrop_id)

        rebuild_calls, original_rebuild_models = self._install_rebuild_recorder()
        try:
            self.scene.move_node(logger_id, 220.0, 150.0)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertEqual(rebuild_calls, [])
        logger_payload = self._scene_payload(logger_id)
        backdrop_payload = self._scene_payload(backdrop_id)
        self.assertEqual(logger_payload["owner_backdrop_id"], backdrop_id)
        self.assertEqual(logger_payload["backdrop_depth"], 1)
        self.assertEqual(backdrop_payload["member_node_ids"], [logger_id])
        self.assertEqual(backdrop_payload["contained_node_ids"], [logger_id])

        node_delta = getattr(self.scene.state_bridge, "node_delta_payload", {})
        self.assertEqual(node_delta["kind"], "node_delta")
        self.assertEqual(node_delta["reason"], "node_position_delta")
        self.assertTrue(node_delta["visibility_may_change"])
        self.assertEqual([payload["node_id"] for payload in node_delta["nodes"]], [logger_id])
        self.assertEqual([payload["node_id"] for payload in node_delta["backdrop_nodes"]], [backdrop_id])

    def test_move_out_of_group_backdrop_keeps_membership_rebuild(self) -> None:
        logger_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 180.0, 140.0)
        backdrop_id = self.scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, 100.0, 100.0)
        self.scene.set_node_geometry(backdrop_id, 100.0, 100.0, 400.0, 260.0)
        self.assertEqual(self._scene_payload(logger_id)["owner_backdrop_id"], backdrop_id)

        rebuild_calls, original_rebuild_models = self._install_rebuild_recorder()
        try:
            self.scene.move_node(logger_id, 520.0, 520.0)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertGreaterEqual(len(rebuild_calls), 1)
        logger_payload = self._scene_payload(logger_id)
        backdrop_payload = self._scene_payload(backdrop_id)
        self.assertEqual(logger_payload["owner_backdrop_id"], "")
        self.assertEqual(logger_payload["backdrop_depth"], 0)
        self.assertEqual(backdrop_payload["member_node_ids"], [])
        self.assertEqual(backdrop_payload["contained_node_ids"], [])

    def test_collapsed_group_backdrop_move_keeps_full_rebuild(self) -> None:
        logger_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 180.0, 150.0)
        backdrop_id = self.scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, 100.0, 100.0)
        self.scene.set_node_geometry(backdrop_id, 100.0, 100.0, 460.0, 300.0)
        self.scene.set_node_collapsed(backdrop_id, True)

        rebuild_calls, original_rebuild_models = self._install_rebuild_recorder()
        try:
            self.scene.move_node(logger_id, 220.0, 160.0)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertGreaterEqual(len(rebuild_calls), 1)

    def test_comment_peek_move_keeps_full_rebuild(self) -> None:
        logger_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 180.0, 150.0)
        backdrop_id = self.scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, 100.0, 100.0)
        self.scene.set_node_geometry(backdrop_id, 100.0, 100.0, 460.0, 300.0)
        self.scene.set_node_collapsed(backdrop_id, True)
        self.assertTrue(self.scene.open_comment_peek(backdrop_id))
        self.assertEqual(self.scene.active_comment_peek_node_id, backdrop_id)

        rebuild_calls, original_rebuild_models = self._install_rebuild_recorder()
        try:
            self.scene.move_node(logger_id, 220.0, 160.0)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertGreaterEqual(len(rebuild_calls), 1)

    def test_wrap_node_ids_in_group_backdrop_creates_padded_group_backdrop_and_keeps_membership_derived(self) -> None:
        first_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 100.0, 100.0)
        second_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 380.0, 250.0)
        expected_bounds = build_group_backdrop_wrap_bounds(
            [
                GroupBackdropCandidate(
                    first_id,
                    (),
                    False,
                    float(self._scene_payload(first_id)["x"]),
                    float(self._scene_payload(first_id)["y"]),
                    float(self._scene_payload(first_id)["width"]),
                    float(self._scene_payload(first_id)["height"]),
                ),
                GroupBackdropCandidate(
                    second_id,
                    (),
                    False,
                    float(self._scene_payload(second_id)["x"]),
                    float(self._scene_payload(second_id)["y"]),
                    float(self._scene_payload(second_id)["width"]),
                    float(self._scene_payload(second_id)["height"]),
                ),
            ]
        )

        backdrop_id = self.scene.wrap_node_ids_in_group_backdrop([first_id, second_id])

        self.assertTrue(backdrop_id)
        self.assertEqual(self.scene.selected_node_id_value, backdrop_id)
        self.assertIsNotNone(expected_bounds)
        assert expected_bounds is not None

        workspace = self.model.project.workspaces[self.workspace_id]
        backdrop = workspace.nodes[backdrop_id]
        self.assertEqual(backdrop.type_id, GROUP_BACKDROP_TYPE_ID)
        self.assertEqual(backdrop.title, "")
        self.assertEqual(backdrop.properties, {"title": ""})
        self.assertEqual(backdrop.x, expected_bounds.x)
        self.assertEqual(backdrop.y, expected_bounds.y)
        self.assertEqual(backdrop.custom_width, expected_bounds.width)
        self.assertEqual(backdrop.custom_height, expected_bounds.height)

        first_payload = self._scene_payload(first_id)
        second_payload = self._scene_payload(second_id)
        backdrop_payload = self._scene_payload(backdrop_id)
        self.assertEqual(first_payload["owner_backdrop_id"], backdrop_id)
        self.assertEqual(second_payload["owner_backdrop_id"], backdrop_id)
        self.assertEqual(first_payload["backdrop_depth"], 1)
        self.assertEqual(second_payload["backdrop_depth"], 1)
        self.assertEqual(backdrop_payload["owner_backdrop_id"], "")
        self.assertEqual(backdrop_payload["backdrop_depth"], 0)
        self.assertEqual(backdrop_payload["member_node_ids"], sorted([first_id, second_id]))
        self.assertEqual(backdrop_payload["member_backdrop_ids"], [])
        self.assertEqual(backdrop_payload["contained_node_ids"], sorted([first_id, second_id]))
        self.assertEqual(backdrop_payload["contained_backdrop_ids"], [])

        document = JsonProjectSerializer(self.registry).to_document(self.model.project)
        workspace_doc = next(item for item in document["workspaces"] if item["workspace_id"] == self.workspace_id)
        backdrop_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == backdrop_id)
        first_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == first_id)
        for node_doc in (backdrop_doc, first_doc):
            for key in (
                "owner_backdrop_id",
                "backdrop_depth",
                "member_node_ids",
                "member_backdrop_ids",
                "contained_node_ids",
                "contained_backdrop_ids",
            ):
                self.assertNotIn(key, node_doc)

    def test_collapsed_group_backdrop_payload_projects_expanded_occupied_bounds(self) -> None:
        logger_id = self.scene.add_node_from_type(LOGGER_TYPE_ID, 180.0, 150.0)
        backdrop_id = self.scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, 100.0, 100.0)
        self.scene.set_node_geometry(backdrop_id, 100.0, 100.0, 460.0, 300.0)
        self.assertEqual(self._scene_payload(logger_id)["owner_backdrop_id"], backdrop_id)

        self.scene.set_node_collapsed(backdrop_id, True)

        backdrop_payload = self._scene_payload(backdrop_id)
        occupied = backdrop_payload["expanded_occupied_bounds"]
        self.assertGreater(float(occupied["width"]), float(backdrop_payload["width"]))
        self.assertGreater(float(occupied["height"]), float(backdrop_payload["height"]))
        self.assertAlmostEqual(float(occupied["x"]), 100.0, places=6)
        self.assertAlmostEqual(float(occupied["y"]), 100.0, places=6)
        self.assertAlmostEqual(float(occupied["width"]), 460.0, places=6)
        self.assertAlmostEqual(float(occupied["height"]), 300.0, places=6)

    def test_wrap_selection_transaction_rejects_cross_scope_node_sets(self) -> None:
        root_logger_id = self._add_workspace_node(LOGGER_TYPE_ID, 40.0, 40.0)
        shell_id = self._add_workspace_node(SUBNODE_TYPE_ID, 220.0, 120.0)
        child_logger_id = self._add_workspace_node(LOGGER_TYPE_ID, 20.0, 20.0, parent_node_id=shell_id)

        result = wrap_selection_in_group_backdrop(
            model=self.model,
            registry=self.registry,
            workspace_id=self.workspace_id,
            selected_node_ids=[root_logger_id, child_logger_id],
            scope_path=(),
        )

        self.assertIsNone(result)
        self.assertEqual(self._workspace_group_backdrop_ids(), [])


if __name__ == "__main__":
    unittest.main()
