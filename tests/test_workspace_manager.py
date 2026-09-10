from __future__ import annotations

import unittest

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.workspace.manager import WorkspaceManager


class WorkspaceManagerTests(unittest.TestCase):
    def test_manager_resolves_workspace_records_without_load_time_metadata_repair(self) -> None:
        model = GraphModel()
        manager = WorkspaceManager(model)
        first = manager.active_workspace_id()
        second = manager.create_workspace("Second")
        third = manager.create_workspace("Third")
        model.project.metadata = {"workspace_order": [third, "missing", first, third]}
        model.project.active_workspace_id = "missing"
        manager = WorkspaceManager(model)

        self.assertEqual(
            [workspace.workspace_id for workspace in manager.list_workspaces()],
            [first, second, third],
        )
        self.assertEqual(model.project.metadata["workspace_order"], [third, "missing", first, third])

        self.assertEqual(manager.active_workspace_id(), first)
        self.assertEqual(model.project.active_workspace_id, first)

    def test_create_workspace_appends_to_authoritative_order_and_activates_the_new_workspace(self) -> None:
        model = GraphModel()
        manager = WorkspaceManager(model)
        first = manager.active_workspace_id()

        second = manager.create_workspace("Second")

        self.assertEqual(model.project.metadata["workspace_order"], [first, second])
        self.assertEqual(manager.active_workspace_id(), second)

    def test_duplicate_workspace_inserts_clone_after_source_in_authoritative_order(self) -> None:
        model = GraphModel()
        manager = WorkspaceManager(model)
        first = manager.active_workspace_id()
        second = manager.create_workspace("Second")
        third = manager.create_workspace("Third")
        manager.move_workspace(2, 1)

        duplicated = manager.duplicate_workspace(third)

        self.assertEqual(
            model.project.metadata["workspace_order"],
            [first, third, duplicated, second],
        )
        self.assertEqual(manager.active_workspace_id(), duplicated)

    def test_duplicate_workspace_preserves_independent_live_graph_copy(self) -> None:
        model = GraphModel()
        manager = WorkspaceManager(model)
        source = model.active_workspace
        node = model.add_node(
            source.workspace_id,
            "core.logger",
            "Logger",
            10.0,
            20.0,
            properties={"message": "source"},
        )

        duplicated_id = manager.duplicate_workspace(source.workspace_id)
        duplicate = model.project.workspaces[duplicated_id]

        self.assertEqual(duplicate.nodes[node.node_id].properties, {"message": "source"})

        duplicate.nodes[node.node_id].properties["message"] = "duplicate"

        self.assertEqual(source.nodes[node.node_id].properties, {"message": "source"})

    def test_close_workspace_promotes_the_next_workspace_in_authoritative_order(self) -> None:
        model = GraphModel()
        manager = WorkspaceManager(model)
        first = manager.active_workspace_id()
        second = manager.create_workspace("Second")
        third = manager.create_workspace("Third")
        manager.move_workspace(2, 1)
        manager.set_active_workspace(third)

        manager.close_workspace(third)

        self.assertEqual(model.project.metadata["workspace_order"], [first, second])
        self.assertEqual(manager.active_workspace_id(), second)

    def test_move_workspace_updates_authoritative_order_for_tabs_and_persistence(self) -> None:
        model = GraphModel()
        manager = WorkspaceManager(model)
        first = manager.active_workspace_id()
        second = manager.create_workspace("Second")
        third = manager.create_workspace("Third")

        manager.move_workspace(2, 0)

        self.assertEqual(model.project.metadata["workspace_order"], [third, first, second])
        self.assertEqual(
            [workspace.workspace_id for workspace in manager.list_workspaces()],
            [third, first, second],
        )

    def test_workspace_manager_does_not_expose_view_lifecycle_helpers(self) -> None:
        manager_methods = set(dir(WorkspaceManager))

        self.assertFalse(
            {
                "create_view",
                "set_active_view",
                "close_view",
                "rename_view",
                "move_view",
            }
            & manager_methods
        )


if __name__ == "__main__":
    unittest.main()
