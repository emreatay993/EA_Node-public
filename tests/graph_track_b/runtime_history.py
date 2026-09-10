from __future__ import annotations

import unittest

from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.graph.registry_normalization import normalize_project_for_registry
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.ui.shell.runtime_history import (
    ACTION_EDIT_EDGE_LABEL,
    ACTION_GROUP_SELECTED_NODES,
)
from tests.graph_track_b.scene_and_model import ACTION_ADD_NODE, GraphModel, RuntimeGraphHistory, ViewState


class _CountingRuntimeGraphHistory(RuntimeGraphHistory):
    def __init__(self) -> None:
        super().__init__()
        self.capture_count = 0

    def capture_workspace(self, workspace):  # noqa: ANN001
        self.capture_count += 1
        return super().capture_workspace(workspace)


class _Plugin:
    def __init__(self, spec: NodeTypeSpec) -> None:
        self._spec = spec

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult()


def _normalization_registry() -> NodeRegistry:
    registry = NodeRegistry()
    spec = NodeTypeSpec(
        type_id="tests.normalize_history",
        display_name="Normalize History",
        category_path=("Tests",),
        icon="",
        ports=(PortSpec("value", "out", "data", 'COREX.DataTypes.Any'),),
        properties=(PropertySpec("count", "int", 7, "Count"),),
    )
    registry.register(lambda: _Plugin(spec))
    return registry


class RuntimeGraphHistoryTrackBTests(unittest.TestCase):
    def test_history_is_isolated_per_workspace_and_clears_redo_on_new_commit(self) -> None:
        model = GraphModel()
        history = RuntimeGraphHistory()
        workspace_a_id = model.active_workspace.workspace_id
        workspace_b_id = model.create_workspace(name="Secondary").workspace_id
        workspace_a = model.project.workspaces[workspace_a_id]
        workspace_b = model.project.workspaces[workspace_b_id]

        before_a = history.capture_workspace(workspace_a)
        model.add_node(workspace_a_id, "core.constant", "Constant A", 0.0, 0.0)
        history.record_action(workspace_a_id, ACTION_ADD_NODE, before_a, workspace_a)

        before_b = history.capture_workspace(workspace_b)
        model.add_node(workspace_b_id, "core.logger", "Logger B", 240.0, 100.0)
        history.record_action(workspace_b_id, ACTION_ADD_NODE, before_b, workspace_b)

        self.assertEqual(history.undo_depth(workspace_a_id), 1)
        self.assertEqual(history.undo_depth(workspace_b_id), 1)

        undone = history.undo_workspace(workspace_a_id, workspace_a)
        self.assertIsNotNone(undone)
        self.assertEqual(len(workspace_a.nodes), 0)
        self.assertEqual(len(workspace_b.nodes), 1)
        self.assertEqual(history.redo_depth(workspace_a_id), 1)
        self.assertEqual(history.redo_depth(workspace_b_id), 0)

        before_new = history.capture_workspace(workspace_a)
        model.add_node(workspace_a_id, "core.logger", "Logger A", 80.0, 30.0)
        history.record_action(workspace_a_id, ACTION_ADD_NODE, before_new, workspace_a)
        self.assertEqual(history.redo_depth(workspace_a_id), 0)
        self.assertEqual(history.undo_depth(workspace_a_id), 1)

    def test_grouped_action_commits_single_history_entry(self) -> None:
        model = GraphModel()
        history = RuntimeGraphHistory()
        workspace_id = model.active_workspace.workspace_id
        workspace = model.project.workspaces[workspace_id]

        with history.grouped_action(workspace_id, ACTION_ADD_NODE, workspace):
            model.add_node(workspace_id, "core.constant", "Constant", 0.0, 0.0)
            model.add_node(workspace_id, "core.logger", "Logger", 280.0, 40.0)

        self.assertEqual(history.undo_depth(workspace_id), 1)
        history.undo_workspace(workspace_id, workspace)
        self.assertEqual(len(workspace.nodes), 0)

    def test_capture_workspace_reuses_snapshot_for_unchanged_revision(self) -> None:
        model = GraphModel()
        history = RuntimeGraphHistory()
        workspace_id = model.active_workspace.workspace_id
        workspace = model.project.workspaces[workspace_id]

        first = history.capture_workspace(workspace)
        second = history.capture_workspace(workspace)
        self.assertIs(first, second)

        model.add_node(workspace_id, "core.constant", "Constant", 0.0, 0.0)
        after_mutation = history.capture_workspace(workspace)
        self.assertIsNot(after_mutation, first)
        self.assertIs(history.capture_workspace(workspace), after_mutation)

        history.clear_workspace(workspace_id)
        after_clear = history.capture_workspace(workspace)
        self.assertIsNot(after_clear, after_mutation)

        history.clear_all()
        after_clear_all = history.capture_workspace(workspace)
        self.assertIsNot(after_clear_all, after_clear)

    def test_registry_normalization_invalidates_same_count_capture_memo(self) -> None:
        model = GraphModel()
        history = RuntimeGraphHistory()
        workspace = model.active_workspace
        node = NodeInstance(
            node_id="node_normalize_history",
            type_id="tests.normalize_history",
            title="Normalize History",
            x=0.0,
            y=0.0,
            properties={"count": "15", "stale": "drop"},
            exposed_ports={"stale_port": True},
        )
        workspace.nodes[node.node_id] = node

        before = history.capture_workspace(workspace)
        normalize_project_for_registry(model.project, _normalization_registry())
        after = history.capture_workspace(workspace)

        self.assertIsNot(after, before)
        self.assertEqual(after.nodes[node.node_id].properties, {"count": 15})
        self.assertEqual(after.nodes[node.node_id].exposed_ports, {"value": True})

    def test_undo_redo_restore_invalidates_capture_memo(self) -> None:
        model = GraphModel()
        history = RuntimeGraphHistory()
        workspace_id = model.active_workspace.workspace_id
        workspace = model.project.workspaces[workspace_id]

        before = history.capture_workspace(workspace)
        model.add_node(workspace_id, "core.constant", "Constant", 0.0, 0.0)
        after = history.capture_workspace(workspace)
        self.assertIsNotNone(history.record_action_from_snapshots(workspace_id, ACTION_ADD_NODE, before, after))

        self.assertIsNotNone(history.undo_workspace(workspace_id, workspace))
        undone = history.capture_workspace(workspace)
        self.assertIsNot(undone, before)
        self.assertEqual(undone, before)

        self.assertIsNotNone(history.redo_workspace(workspace_id, workspace))
        redone = history.capture_workspace(workspace)
        self.assertIsNot(redone, after)
        self.assertEqual(redone, after)

    def test_record_action_from_snapshots_reuses_caller_captures(self) -> None:
        model = GraphModel()
        history = _CountingRuntimeGraphHistory()
        workspace_id = model.active_workspace.workspace_id
        workspace = model.project.workspaces[workspace_id]

        before = history.capture_workspace(workspace)
        model.add_node(workspace_id, "core.constant", "Constant", 0.0, 0.0)
        after = history.capture_workspace(workspace)
        entry = history.record_action_from_snapshots(workspace_id, ACTION_ADD_NODE, before, after)

        self.assertIsNotNone(entry)
        self.assertEqual(history.capture_count, 2)
        self.assertEqual(history.undo_depth(workspace_id), 1)
        self.assertIsNotNone(history.undo_workspace(workspace_id, workspace))
        self.assertEqual(len(workspace.nodes), 0)

    def test_grouped_action_accepts_pre_captured_before_snapshot(self) -> None:
        model = GraphModel()
        history = _CountingRuntimeGraphHistory()
        workspace_id = model.active_workspace.workspace_id
        workspace = model.project.workspaces[workspace_id]

        before = history.capture_workspace(workspace)
        with history.grouped_action(workspace_id, ACTION_ADD_NODE, workspace, before_snapshot=before) as result:
            model.add_node(workspace_id, "core.constant", "Constant", 0.0, 0.0)
            model.add_node(workspace_id, "core.logger", "Logger", 280.0, 40.0)

        self.assertIsNotNone(result.entry)
        self.assertEqual(history.capture_count, 2)
        self.assertEqual(history.undo_depth(workspace_id), 1)
        history.undo_workspace(workspace_id, workspace)
        self.assertEqual(len(workspace.nodes), 0)

    def test_history_restores_full_workspace_state(self) -> None:
        model = GraphModel()
        history = RuntimeGraphHistory()
        workspace = model.active_workspace
        workspace_id = workspace.workspace_id

        shell = model.add_node(workspace_id, "core.subnode", "Shell", 120.0, 80.0)
        child = model.add_node(workspace_id, "core.logger", "Logger", 260.0, 120.0)
        workspace.nodes[child.node_id].parent_node_id = shell.node_id
        before_view = model.create_view(workspace_id, name="Nested Review")
        before_view.zoom = 1.75
        before_view.pan_x = 145.0
        before_view.pan_y = 230.0
        before_view.scope_path = [shell.node_id]
        workspace.active_view_id = before_view.view_id
        workspace.name = "Before State"
        workspace.dirty = True

        before = history.capture_workspace(workspace)

        workspace.name = "After State"
        after_node = model.add_node(workspace_id, "core.logger", "Logger", 420.0, 180.0)
        workspace.nodes = {after_node.node_id: after_node}
        workspace.edges = {}
        workspace.views = {
            "view_after": ViewState(
                view_id="view_after",
                name="After View",
                zoom=0.8,
                pan_x=-40.0,
                pan_y=25.0,
                scope_path=[],
            )
        }
        workspace.active_view_id = "view_after"
        workspace.dirty = False

        history.record_action(workspace_id, ACTION_ADD_NODE, before, workspace)

        self.assertIsNotNone(history.undo_workspace(workspace_id, workspace))
        self.assertEqual(workspace.name, "Before State")
        self.assertEqual(set(workspace.nodes), {shell.node_id, child.node_id})
        self.assertEqual(workspace.nodes[child.node_id].parent_node_id, shell.node_id)
        self.assertEqual(workspace.active_view_id, before_view.view_id)
        self.assertEqual(len(workspace.views), 2)
        self.assertIn(before_view.view_id, workspace.views)
        self.assertAlmostEqual(workspace.views[before_view.view_id].zoom, 1.75, places=6)
        self.assertAlmostEqual(workspace.views[before_view.view_id].pan_x, 145.0, places=6)
        self.assertAlmostEqual(workspace.views[before_view.view_id].pan_y, 230.0, places=6)
        self.assertEqual(workspace.views[before_view.view_id].scope_path, [shell.node_id])
        self.assertTrue(workspace.dirty)

        self.assertIsNotNone(history.redo_workspace(workspace_id, workspace))
        self.assertEqual(workspace.name, "After State")
        self.assertEqual(set(workspace.nodes), {after_node.node_id})
        self.assertEqual(set(workspace.views), {"view_after"})
        self.assertEqual(workspace.active_view_id, "view_after")
        self.assertAlmostEqual(workspace.views["view_after"].zoom, 0.8, places=6)
        self.assertAlmostEqual(workspace.views["view_after"].pan_x, -40.0, places=6)
        self.assertAlmostEqual(workspace.views["view_after"].pan_y, 25.0, places=6)
        self.assertFalse(workspace.dirty)

    def test_persistent_node_elapsed_action_types_preserve_recorded_labels(self) -> None:
        model = GraphModel()
        history = RuntimeGraphHistory()
        workspace = model.active_workspace
        workspace_id = workspace.workspace_id

        before = history.capture_workspace(workspace)
        model.add_node(workspace_id, "core.constant", "Constant", 0.0, 0.0)
        self.assertTrue(history.record_action(workspace_id, ACTION_EDIT_EDGE_LABEL, before, workspace))

        undone = history.undo_workspace(workspace_id, workspace)
        self.assertIsNotNone(undone)
        assert undone is not None
        self.assertEqual(undone.action_type, ACTION_EDIT_EDGE_LABEL)

        redone = history.redo_workspace(workspace_id, workspace)
        self.assertIsNotNone(redone)
        assert redone is not None
        self.assertEqual(redone.action_type, ACTION_EDIT_EDGE_LABEL)

        history.clear_workspace(workspace_id)
        with history.grouped_action(workspace_id, ACTION_GROUP_SELECTED_NODES, workspace):
            model.add_node(workspace_id, "core.constant", "Grouped Constant", 40.0, 20.0)
            model.add_node(workspace_id, "core.logger", "Grouped Logger", 320.0, 60.0)

        grouped = history.undo_workspace(workspace_id, workspace)
        self.assertIsNotNone(grouped)
        assert grouped is not None
        self.assertEqual(grouped.action_type, ACTION_GROUP_SELECTED_NODES)


__all__ = ["RuntimeGraphHistoryTrackBTests"]
