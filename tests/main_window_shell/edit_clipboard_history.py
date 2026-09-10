from __future__ import annotations

import copy
import hashlib
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from PyQt6.QtCore import QMimeData, QUrl
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QSignalSpy

from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.ui.shell.clipboard_paste_nodes import capture_canvas_mime_data, classify_canvas_import
from ea_node_editor.ui.shell.controllers.canvas_import_controller import CanvasImportController
from ea_node_editor.ui.shell.controllers.workspace_edit_controller import (
    WorkspaceEditController,
)
from ea_node_editor.ui.shell.runtime_clipboard import (
    GRAPH_FRAGMENT_MIME_TYPE,
    serialize_graph_fragment_payload,
)
from tests.main_window_shell.base import *  # noqa: F401,F403

GROUP_BACKDROP_TYPE_ID = "passive.annotation.group_backdrop"


def _selected_node_ids(window: ShellWindow) -> set[str]:
    return set(window.scene.selected_node_lookup)


def _scene_payload(window: ShellWindow, node_id: str) -> dict[str, object]:
    for payload in [*window.scene.nodes_model, *window.scene.backdrop_nodes_model]:
        if str(payload.get("node_id", "")) == str(node_id):
            return payload
    raise AssertionError(f"Node payload {node_id!r} was not found.")


def _new_workspace_nodes(window: ShellWindow, before_node_ids: set[str]) -> list[NodeInstance]:
    workspace_id = window.workspace_manager.active_workspace_id()
    workspace = window.model.project.workspaces[workspace_id]
    return [
        node
        for node_id, node in workspace.nodes.items()
        if node_id not in before_node_ids
    ]


def _seed_persistent_node_elapsed_state(
    window: ShellWindow,
    *,
    workspace_id: str,
    foreign_workspace_id: str,
    running_node_id: str,
    cached_node_id: str,
) -> tuple[dict[str, float], dict[str, float]]:
    state = window.run_state
    state.node_execution_workspace_id = ""
    state.running_node_ids.clear()
    state.completed_node_ids.clear()
    state.running_node_started_at_epoch_ms_by_node_id.clear()
    state.cached_node_elapsed_ms_by_workspace_id.clear()
    state.cached_node_elapsed_ms_by_workspace_id[foreign_workspace_id] = {"node_foreign": 91.0}
    window.run_projection_controller.mark_node_execution_running(
        workspace_id,
        running_node_id,
        started_at_epoch_ms=125.0,
    )
    window.run_projection_controller.mark_node_execution_settled(
        workspace_id,
        cached_node_id,
        status="completed",
        elapsed_ms=48.5,
    )
    return (
        {running_node_id: 125.0},
        {cached_node_id: 48.5},
    )


class MainWindowShellEditClipboardHistoryTests(SharedMainWindowShellTestBase):
    def test_qml_request_remove_edge_mutates_model(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        source_id = self.window.scene.add_node_from_type("core.constant", x=40.0, y=40.0)
        target_id = self.window.scene.add_node_from_type("core.logger", x=280.0, y=40.0)
        edge_id = self.window.scene.add_edge(source_id, "as_text", target_id, "message")
        self.app.processEvents()

        removed = self.window.request_remove_edge(edge_id)
        self.assertTrue(removed)
        self.assertNotIn(edge_id, self.window.model.project.workspaces[workspace_id].edges)

    def test_qml_request_remove_node_removes_incident_edges(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        source_id = self.window.scene.add_node_from_type("core.constant", x=40.0, y=40.0)
        target_id = self.window.scene.add_node_from_type("core.logger", x=280.0, y=40.0)
        edge_id = self.window.scene.add_edge(source_id, "as_text", target_id, "message")
        self.app.processEvents()

        removed = self.window.request_remove_node(source_id)
        self.assertTrue(removed)
        workspace = self.window.model.project.workspaces[workspace_id]
        self.assertNotIn(source_id, workspace.nodes)
        self.assertNotIn(edge_id, workspace.edges)

    def test_qml_request_rename_node_updates_title(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.constant", x=40.0, y=40.0)
        self.app.processEvents()

        with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("Renamed Node", True)):
            renamed = self.window.request_rename_node(node_id)
        self.assertTrue(renamed)
        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertEqual(node.title, "Renamed Node")

    def test_qml_request_rename_node_renames_managed_video_artifact_folder(self) -> None:
        project_path = self._env.temp_path / "managed-video.cxproj"
        self.window.project_path = str(project_path)
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type(MEDIA_PANEL_TYPE_ID, x=40.0, y=40.0)
        workspace = self.window.model.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        store = ProjectArtifactStore(project_path=project_path, metadata=None)
        root = store.ensure_staging_root()
        before = store.node_artifact_paths(
            artifact_id="video",
            workspace_id=workspace_id,
            node_id=node_id,
            node_title=node.title,
            node_type="Media Panel",
            io_dir="in",
            subdirectory="media",
            filename="clip.mp4",
        )
        old_file = root.joinpath(*PurePosixPath(before.managed_relative_path).parts)
        old_file.parent.mkdir(parents=True, exist_ok=True)
        old_file.write_bytes(b"video payload")
        store = ProjectArtifactStore(
            project_path=project_path,
            metadata={
                "artifacts": {
                    "video": {
                        "relative_path": before.managed_relative_path,
                        **before.metadata,
                    }
                }
            },
        )
        self.window.project_session_controller.replace_project_artifact_store(store)
        node.properties["source"] = store.managed_ref("video")
        release_events: list[tuple[str, str]] = []
        meta_events: list[object] = []
        self.window.graph_canvas_command_bridge.managedArtifactRenameReleaseRequested.connect(
            lambda released_node_id: release_events.append(("release", released_node_id))
        )
        self.window.graph_canvas_command_bridge.managedArtifactRenameReleaseFinished.connect(
            lambda released_node_id: release_events.append(("finish", released_node_id))
        )
        self.window.project_meta_changed.connect(lambda: meta_events.append(object()))
        self.app.processEvents()

        with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("Renamed Video", True)):
            renamed = self.window.request_rename_node(node_id)

        after_store = self.window.project_session_controller.project_artifact_store()
        after = after_store.node_artifact_paths(
            artifact_id="video",
            workspace_id=workspace_id,
            node_id=node_id,
            node_title="Renamed Video",
            node_type="Media Panel",
            io_dir="in",
            subdirectory="media",
            filename="clip.mp4",
        )
        new_file = root.joinpath(*PurePosixPath(after.managed_relative_path).parts)
        self.assertTrue(renamed)
        self.assertEqual(workspace.nodes[node_id].title, "Renamed Video")
        self.assertEqual(release_events, [("release", node_id), ("finish", node_id)])
        self.assertTrue(meta_events)
        self.assertFalse(old_file.exists())
        self.assertEqual(new_file.read_bytes(), b"video payload")
        self.assertEqual(after_store.metadata["artifacts"]["video"]["relative_path"], after.managed_relative_path)
        self.assertEqual(after_store.metadata["artifacts"]["video"]["node_folder"], after.node_folder)

    def test_qml_request_rename_node_updates_title_for_scoped_and_collapsed_nodes(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        scoped_node_id = self.window.scene.add_node_from_type("core.subnode", x=40.0, y=40.0)
        collapsed_node_id = self.window.scene.add_node_from_type("core.logger", x=280.0, y=40.0)
        self.window.scene.set_node_collapsed(collapsed_node_id, True)
        self.app.processEvents()

        with patch(
            "PyQt6.QtWidgets.QInputDialog.getText",
            side_effect=[("Scoped Shell", True), ("Collapsed Logger", True)],
        ):
            scoped_renamed = self.window.request_rename_node(scoped_node_id)
            collapsed_renamed = self.window.request_rename_node(collapsed_node_id)

        self.assertTrue(scoped_renamed)
        self.assertTrue(collapsed_renamed)
        workspace = self.window.model.project.workspaces[workspace_id]
        self.assertEqual(workspace.nodes[scoped_node_id].title, "Scoped Shell")
        self.assertEqual(workspace.nodes[collapsed_node_id].title, "Collapsed Logger")

    def test_qml_request_rename_selected_port_updates_subnode_pin_label(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        shell_id = self.window.scene.add_node_from_type("core.subnode", x=120.0, y=80.0)
        self.window.scene.focus_node(shell_id)
        self.app.processEvents()

        port_node_id = self.window.request_add_selected_subnode_pin("out")
        self.assertTrue(port_node_id)

        with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("Renamed Port", True)):
            renamed = self.window.request_rename_selected_port(port_node_id)

        self.assertTrue(renamed)
        workspace = self.window.model.project.workspaces[workspace_id]
        self.assertEqual(workspace.nodes[port_node_id].properties["label"], "Renamed Port")
        port_items = {item["key"]: item for item in self.window.selected_node_port_items}
        self.assertIn(port_node_id, port_items)
        self.assertEqual(port_items[port_node_id]["label"], "Renamed Port")

    def test_qml_request_delete_selected_graph_items_removes_nodes_and_edges(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        source_id = self.window.scene.add_node_from_type("core.constant", x=40.0, y=40.0)
        target_id = self.window.scene.add_node_from_type("core.python_script", x=320.0, y=40.0)
        removable_node_id = self.window.scene.add_node_from_type("core.logger", x=520.0, y=40.0)
        edge_id = self.window.scene.add_edge(source_id, "value", target_id, "payload")
        self.window.scene.select_node(removable_node_id, False)
        self.app.processEvents()

        deleted = self.window.request_delete_selected_graph_items([edge_id])
        self.assertTrue(deleted)
        workspace = self.window.model.project.workspaces[workspace_id]
        self.assertNotIn(edge_id, workspace.edges)
        self.assertNotIn(removable_node_id, workspace.nodes)

    def test_qml_request_duplicate_selected_nodes_duplicates_internal_edges_and_selects_result(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        source_id = self.window.scene.add_node_from_type("core.constant", x=40.0, y=40.0)
        target_id = self.window.scene.add_node_from_type("core.logger", x=280.0, y=40.0)
        external_id = self.window.scene.add_node_from_type("core.python_script", x=520.0, y=90.0)
        self.window.scene.add_edge(source_id, "as_text", target_id, "message")
        self.window.scene.add_edge(source_id, "value", external_id, "payload")
        workspace = self.window.model.project.workspaces[workspace_id]
        before_nodes = len(workspace.nodes)
        before_edges = len(workspace.edges)

        workspace_b_id = self.window.workspace_manager.create_workspace("Secondary")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(workspace_b_id)
        self.window.scene.add_node_from_type("core.logger", x=80.0, y=80.0)
        self.window.workspace_navigation_controller.switch_workspace(workspace_id)
        self.app.processEvents()

        self.window.scene.select_node(source_id, False)
        self.window.scene.select_node(target_id, True)

        duplicated = self.window.request_duplicate_selected_nodes()
        self.assertTrue(duplicated)
        self.app.processEvents()

        workspace = self.window.model.project.workspaces[workspace_id]
        self.assertEqual(len(workspace.nodes), before_nodes + 2)
        self.assertEqual(len(workspace.edges), before_edges + 1)
        secondary_workspace = self.window.model.project.workspaces[workspace_b_id]
        self.assertEqual(len(secondary_workspace.nodes), 1)
        self.assertEqual(len(secondary_workspace.edges), 0)

        selected_duplicate_ids = _selected_node_ids(self.window)
        self.assertEqual(len(selected_duplicate_ids), 2)
        self.assertNotIn(source_id, selected_duplicate_ids)
        self.assertNotIn(target_id, selected_duplicate_ids)

        source_node = workspace.nodes[source_id]
        target_node = workspace.nodes[target_id]
        duplicate_source_id = ""
        duplicate_target_id = ""
        for node_id in selected_duplicate_ids:
            node = workspace.nodes[node_id]
            if (
                node.type_id == source_node.type_id
                and node.title == source_node.title
                and abs(node.x - (source_node.x + 40.0)) < 1e-6
                and abs(node.y - (source_node.y + 40.0)) < 1e-6
            ):
                duplicate_source_id = node_id
            if (
                node.type_id == target_node.type_id
                and node.title == target_node.title
                and abs(node.x - (target_node.x + 40.0)) < 1e-6
                and abs(node.y - (target_node.y + 40.0)) < 1e-6
            ):
                duplicate_target_id = node_id
        self.assertTrue(duplicate_source_id)
        self.assertTrue(duplicate_target_id)

        duplicated_internal_edges = [
            edge
            for edge in workspace.edges.values()
            if edge.source_node_id == duplicate_source_id
            and edge.source_port_key == "as_text"
            and edge.target_node_id == duplicate_target_id
            and edge.target_port_key == "message"
        ]
        self.assertEqual(len(duplicated_internal_edges), 1)
        duplicated_external_edges = [
            edge
            for edge in workspace.edges.values()
            if edge.source_node_id == duplicate_source_id and edge.source_port_key == "value"
        ]
        self.assertEqual(duplicated_external_edges, [])

    def test_qml_request_duplicate_selected_nodes_is_safe_noop_without_selection(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        self.window.scene.add_node_from_type("core.constant", x=20.0, y=20.0)
        self.window.scene.clear_selection()
        workspace = self.window.model.project.workspaces[workspace_id]
        before_state = self._workspace_state()
        before_undo_depth = self.window.runtime_history.undo_depth(workspace_id)

        duplicated = self.window.request_duplicate_selected_nodes()
        self.assertFalse(duplicated)
        self.app.processEvents()

        self.assertEqual(self._workspace_state(), before_state)
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), before_undo_depth)
        self.assertEqual(len(workspace.nodes), 1)

    def test_qml_request_group_and_ungroup_selected_nodes_are_single_undoable_actions(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        source_id = self.window.scene.add_node_from_type("core.constant", x=20.0, y=40.0)
        grouped_script_id = self.window.scene.add_node_from_type("core.python_script", x=320.0, y=60.0)
        grouped_constant_id = self.window.scene.add_node_from_type("core.constant", x=220.0, y=190.0)
        target_id = self.window.scene.add_node_from_type("core.logger", x=640.0, y=90.0)
        external_script_id = self.window.scene.add_node_from_type("core.python_script", x=700.0, y=230.0)
        self.window.scene.add_edge(source_id, "value", grouped_script_id, "payload")
        self.window.scene.add_edge(grouped_constant_id, "as_text", grouped_script_id, "payload", True)
        self.window.scene.add_edge(grouped_script_id, "result", target_id, "message")
        self.window.scene.add_edge(grouped_constant_id, "value", external_script_id, "payload")
        self.app.processEvents()
        workspace = self.window.model.project.workspaces[workspace_id]
        initial_edge_signature = {
            (edge.source_node_id, edge.source_port_key, edge.target_node_id, edge.target_port_key)
            for edge in workspace.edges.values()
        }

        self.window.scene.select_node(grouped_script_id, False)
        self.window.scene.select_node(grouped_constant_id, True)
        initial_state = self._workspace_state()
        self.window.runtime_history.clear_workspace(workspace_id)

        grouped = self.window.request_group_selected_nodes()
        self.assertTrue(grouped)
        grouped_state = self._workspace_state()
        self.assertNotEqual(grouped_state, initial_state)
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), 1)

        self.window.action_undo.trigger()
        self.app.processEvents()
        self.assertEqual(self._workspace_state(), initial_state)

        self.window.action_redo.trigger()
        self.app.processEvents()
        self.assertEqual(self._workspace_state(), grouped_state)

        workspace = self.window.model.project.workspaces[workspace_id]
        shell_ids = [
            node_id
            for node_id, node in workspace.nodes.items()
            if node.type_id == "core.subnode" and node.parent_node_id is None
        ]
        self.assertEqual(len(shell_ids), 1)
        shell_id = shell_ids[0]

        self.window.scene.select_node(shell_id, False)
        self.window.runtime_history.clear_workspace(workspace_id)
        ungrouped = self.window.request_ungroup_selected_nodes()
        self.assertTrue(ungrouped)
        ungrouped_edge_signature = {
            (edge.source_node_id, edge.source_port_key, edge.target_node_id, edge.target_port_key)
            for edge in workspace.edges.values()
        }
        self.assertEqual(ungrouped_edge_signature, initial_edge_signature)
        self.assertEqual(workspace.nodes[grouped_script_id].parent_node_id, None)
        self.assertEqual(workspace.nodes[grouped_constant_id].parent_node_id, None)
        remaining_subnode_types = {
            node.type_id for node in workspace.nodes.values() if node.type_id.startswith("core.subnode")
        }
        self.assertEqual(remaining_subnode_types, set())
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), 1)

        self.window.action_undo.trigger()
        self.app.processEvents()
        self.assertEqual(self._workspace_state(), grouped_state)

    def test_qml_request_copy_and_paste_selected_nodes_preserves_internal_edges_and_recenters_fragment(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        source_id = self.window.scene.add_node_from_type("core.constant", x=60.0, y=50.0)
        target_id = self.window.scene.add_node_from_type("core.logger", x=360.0, y=190.0)
        external_id = self.window.scene.add_node_from_type("core.python_script", x=680.0, y=90.0)
        self.window.scene.add_edge(source_id, "as_text", target_id, "message")
        self.window.scene.add_edge(source_id, "value", external_id, "payload")
        workspace = self.window.model.project.workspaces[workspace_id]
        before_nodes = len(workspace.nodes)
        before_edges = len(workspace.edges)

        source_node = workspace.nodes[source_id]
        target_node = workspace.nodes[target_id]
        relative_dx = float(target_node.x) - float(source_node.x)
        relative_dy = float(target_node.y) - float(source_node.y)

        self.window.scene.select_node(source_id, False)
        self.window.scene.select_node(target_id, True)
        self.window.view.set_zoom(0.75)
        self.window.view.centerOn(980.0, -210.0)
        self.app.processEvents()

        original_selection_bounds = self.window.scene.selection_bounds()
        self.assertIsNotNone(original_selection_bounds)
        original_center = original_selection_bounds.center()

        copied = self.window.request_copy_selected_nodes()
        self.assertTrue(copied)
        pasted = self.window.request_paste_selected_nodes()
        self.assertTrue(pasted)
        self.app.processEvents()

        workspace = self.window.model.project.workspaces[workspace_id]
        self.assertEqual(len(workspace.nodes), before_nodes + 2)
        self.assertEqual(len(workspace.edges), before_edges + 1)

        pasted_node_ids = _selected_node_ids(self.window)
        self.assertEqual(len(pasted_node_ids), 2)
        self.assertNotIn(source_id, pasted_node_ids)
        self.assertNotIn(target_id, pasted_node_ids)

        pasted_source = None
        pasted_target = None
        for node_id in pasted_node_ids:
            node = workspace.nodes[node_id]
            if node.type_id == "core.constant":
                pasted_source = node
            elif node.type_id == "core.logger":
                pasted_target = node
        self.assertIsNotNone(pasted_source)
        self.assertIsNotNone(pasted_target)
        self.assertAlmostEqual(float(pasted_target.x) - float(pasted_source.x), relative_dx, places=6)
        self.assertAlmostEqual(float(pasted_target.y) - float(pasted_source.y), relative_dy, places=6)

        internal_edges = [
            edge
            for edge in workspace.edges.values()
            if edge.source_node_id == pasted_source.node_id
            and edge.source_port_key == "as_text"
            and edge.target_node_id == pasted_target.node_id
            and edge.target_port_key == "message"
        ]
        self.assertEqual(len(internal_edges), 1)
        external_edges = [
            edge
            for edge in workspace.edges.values()
            if edge.source_node_id == pasted_source.node_id and edge.source_port_key == "value"
        ]
        self.assertEqual(external_edges, [])

        selection_bounds = self.window.scene.selection_bounds()
        self.assertIsNotNone(selection_bounds)
        self.assertAlmostEqual(selection_bounds.center().x(), original_center.x() + 40.0, places=5)
        self.assertAlmostEqual(selection_bounds.center().y(), original_center.y() + 40.0, places=5)

    def test_qml_request_copy_and_paste_selected_nodes_retargets_active_subnode_scope(
        self,
    ) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        source_id = self.window.scene.add_node_from_type("core.constant", x=80.0, y=70.0)
        shell_id = self.window.scene.add_node_from_type("core.subnode", x=320.0, y=120.0)
        workspace = self.window.model.project.workspaces[workspace_id]

        self.window.scene.select_node(source_id, False)
        self.assertTrue(self.window.request_copy_selected_nodes())
        self.assertTrue(self.window.request_open_subnode_scope(shell_id))
        self.app.processEvents()
        self.assertEqual(list(self.window.scene.active_scope_path), [shell_id])

        before_subnode_node_ids = set(workspace.nodes)
        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()

        inward_node_ids = set(workspace.nodes) - before_subnode_node_ids
        self.assertEqual(len(inward_node_ids), 1)
        inward_node_id = next(iter(inward_node_ids))
        inward_node = workspace.nodes[inward_node_id]
        self.assertEqual(inward_node.type_id, "core.constant")
        self.assertEqual(inward_node.parent_node_id, shell_id)
        self.assertEqual(_selected_node_ids(self.window), {inward_node_id})
        self.assertEqual(_scene_payload(self.window, inward_node_id)["node_id"], inward_node_id)

        self.assertTrue(self.window.request_copy_selected_nodes())
        self.assertTrue(self.window.request_navigate_scope_parent())
        self.app.processEvents()
        self.assertEqual(list(self.window.scene.active_scope_path), [])

        before_root_node_ids = set(workspace.nodes)
        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()

        outward_node_ids = set(workspace.nodes) - before_root_node_ids
        self.assertEqual(len(outward_node_ids), 1)
        outward_node_id = next(iter(outward_node_ids))
        outward_node = workspace.nodes[outward_node_id]
        self.assertEqual(outward_node.type_id, "core.constant")
        self.assertIsNone(outward_node.parent_node_id)
        self.assertEqual(_selected_node_ids(self.window), {outward_node_id})
        self.assertEqual(_scene_payload(self.window, outward_node_id)["node_id"], outward_node_id)

    def test_qml_request_paste_selected_nodes_into_other_workspace_selects_pasted_nodes(self) -> None:
        source_workspace_id = self.window.workspace_manager.active_workspace_id()
        source_a_id = self.window.scene.add_node_from_type("core.constant", x=100.0, y=120.0)
        source_b_id = self.window.scene.add_node_from_type("core.logger", x=340.0, y=140.0)
        self.window.scene.add_edge(source_a_id, "as_text", source_b_id, "message")
        source_workspace = self.window.model.project.workspaces[source_workspace_id]
        before_source_nodes = len(source_workspace.nodes)
        before_source_edges = len(source_workspace.edges)
        self.window.scene.select_node(source_a_id, False)
        self.window.scene.select_node(source_b_id, True)
        self.assertTrue(self.window.request_copy_selected_nodes())

        target_workspace_id = self.window.workspace_manager.create_workspace("Clipboard Target")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(target_workspace_id)
        self.window.view.centerOn(-430.0, 280.0)
        target_workspace = self.window.model.project.workspaces[target_workspace_id]
        before_target_nodes = len(target_workspace.nodes)
        before_target_edges = len(target_workspace.edges)

        pasted = self.window.request_paste_selected_nodes()
        self.assertTrue(pasted)
        self.app.processEvents()

        target_workspace = self.window.model.project.workspaces[target_workspace_id]
        self.assertEqual(len(target_workspace.nodes), before_target_nodes + 2)
        self.assertEqual(len(target_workspace.edges), before_target_edges + 1)
        selected_pasted_ids = _selected_node_ids(self.window)
        self.assertEqual(len(selected_pasted_ids), 2)
        self.assertEqual(self.window.workspace_manager.active_workspace_id(), target_workspace_id)

        source_workspace = self.window.model.project.workspaces[source_workspace_id]
        self.assertEqual(len(source_workspace.nodes), before_source_nodes)
        self.assertEqual(len(source_workspace.edges), before_source_edges)

    def test_qml_request_paste_selected_nodes_offsets_repeated_paste_from_same_clipboard(self) -> None:
        source_id = self.window.scene.add_node_from_type("core.constant", x=50.0, y=60.0)
        target_id = self.window.scene.add_node_from_type("core.logger", x=240.0, y=110.0)
        self.window.scene.add_edge(source_id, "as_text", target_id, "message")
        self.window.scene.select_node(source_id, False)
        self.window.scene.select_node(target_id, True)
        self.window.view.centerOn(300.0, -120.0)
        self.app.processEvents()

        original_bounds = self.window.scene.selection_bounds()
        self.assertIsNotNone(original_bounds)
        original_center = original_bounds.center()

        self.assertTrue(self.window.request_copy_selected_nodes())

        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()
        first_bounds = self.window.scene.selection_bounds()
        self.assertIsNotNone(first_bounds)

        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()
        second_bounds = self.window.scene.selection_bounds()
        self.assertIsNotNone(second_bounds)

        self.assertAlmostEqual(first_bounds.center().x(), original_center.x() + 40.0, places=5)
        self.assertAlmostEqual(first_bounds.center().y(), original_center.y() + 40.0, places=5)
        self.assertAlmostEqual(second_bounds.center().x(), original_center.x() + 80.0, places=5)
        self.assertAlmostEqual(second_bounds.center().y(), original_center.y() + 80.0, places=5)

    def test_qml_request_paste_selected_nodes_prefers_graph_fragment_mime_over_url_fallback(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        source_id = self.window.scene.add_node_from_type("core.constant", x=25.0, y=35.0)
        self.window.scene.select_node(source_id, False)
        fragment_payload = self.window.scene.serialize_selected_subgraph_fragment()
        serialized = serialize_graph_fragment_payload(fragment_payload)
        self.assertIsNotNone(serialized)

        mime_data = QMimeData()
        mime_data.setData(GRAPH_FRAGMENT_MIME_TYPE, str(serialized).encode("utf-8"))
        mime_data.setText("https://example.test/clipboard-image.png")
        self.app.clipboard().setMimeData(mime_data)
        before_node_ids = set(self.window.model.project.workspaces[workspace_id].nodes)

        pasted = self.window.request_paste_selected_nodes()
        self.assertTrue(pasted)
        self.app.processEvents()

        new_nodes = _new_workspace_nodes(self.window, before_node_ids)
        self.assertEqual(len(new_nodes), 1)
        self.assertEqual(new_nodes[0].type_id, "core.constant")

    def test_qml_request_paste_selected_nodes_creates_nodes_for_multiple_local_files(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        temp_dir = Path(self._env.temp_path)
        image_path = temp_dir / "clipboard-local-image.png"
        pdf_path = temp_dir / "clipboard-local-document.pdf"
        html_path = temp_dir / "clipboard-local-page.html"
        image = QImage(12, 8, QImage.Format.Format_ARGB32)
        image.fill(QColor("#2C85BF"))
        self.assertTrue(image.save(str(image_path)))
        pdf_path.write_bytes(b"%PDF-1.4\n% clipboard fixture\n")
        html_path.write_text("<html><body>Clipboard page</body></html>", encoding="utf-8")

        mime_data = QMimeData()
        mime_data.setUrls(
            [
                QUrl.fromLocalFile(str(image_path)),
                QUrl.fromLocalFile(str(pdf_path)),
                QUrl.fromLocalFile(str(html_path)),
            ]
        )
        self.app.clipboard().setMimeData(mime_data)
        before_node_ids = set(self.window.model.project.workspaces[workspace_id].nodes)

        pasted = self.window.request_paste_selected_nodes()
        self.assertTrue(pasted)
        self.app.processEvents()

        new_nodes = _new_workspace_nodes(self.window, before_node_ids)
        self.assertEqual(len(new_nodes), 3)
        media_by_suffix = {
            Path(str(node.properties["source"])).suffix.lower(): node
            for node in new_nodes
            if node.type_id == MEDIA_PANEL_TYPE_ID
        }
        by_type = {node.type_id: node for node in new_nodes if node.type_id != MEDIA_PANEL_TYPE_ID}
        self.assertEqual(
            Path(media_by_suffix[".png"].properties["source"]).resolve(),
            image_path.resolve(),
        )
        self.assertEqual(
            Path(media_by_suffix[".pdf"].properties["source"]).resolve(),
            pdf_path.resolve(),
        )
        self.assertTrue(
            all(not node.exposed_ports["source"] for node in media_by_suffix.values())
        )
        self.assertEqual(
            Path(by_type["web.page_viewer"].properties["start_location"]).resolve(),
            html_path.resolve(),
        )

    def test_clipboard_classifier_maps_mail_files_to_mail_panel_nodes(self) -> None:
        temp_dir = Path(self._env.temp_path)
        mail_path = temp_dir / "clipboard-local-message.eml"
        mail_path.write_text("Subject: Clipboard\n\nHello", encoding="utf-8")

        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(str(mail_path))])

        sources = classify_canvas_import(capture_canvas_mime_data(mime_data))
        items = [source.choice(source.detected_choice).item for source in sources]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].type_id, "passive.media.mail_panel")
        self.assertEqual(
            Path(items[0].properties["source_path"]).resolve(),
            mail_path.resolve(),
        )

    def test_qml_request_paste_selected_nodes_creates_web_or_media_nodes_for_plain_urls(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]

        self.app.clipboard().setText("https://example.test/specs/guide.pdf")
        before_node_ids = set(workspace.nodes)
        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()
        pdf_node = _new_workspace_nodes(self.window, before_node_ids)[0]
        self.assertEqual(pdf_node.type_id, MEDIA_PANEL_TYPE_ID)
        self.assertEqual(pdf_node.properties["source"], "https://example.test/specs/guide.pdf")
        self.assertFalse(pdf_node.exposed_ports["source"])

        self.app.clipboard().setText("https://example.test/docs/")
        before_node_ids = set(workspace.nodes)
        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()
        web_node = _new_workspace_nodes(self.window, before_node_ids)[0]
        self.assertEqual(web_node.type_id, "web.page_viewer")
        self.assertEqual(web_node.properties["start_location"], "https://example.test/docs/")

        reddit_url = "https://www.reddit.com/r/gamedev/comments/1fxd33a/unity_vs_godot_pros_and_cons_of_each_which_is/"
        rich_link = QMimeData()
        rich_link.setText("Unity vs Godot - pros and cons of each. Which is?")
        rich_link.setHtml(f'<a href="{reddit_url}">Unity vs Godot - pros and cons of each. Which is?</a>')
        self.app.clipboard().setMimeData(rich_link)
        before_node_ids = set(workspace.nodes)
        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()
        rich_web_node = _new_workspace_nodes(self.window, before_node_ids)[0]
        self.assertEqual(rich_web_node.type_id, "web.page_viewer")
        self.assertEqual(rich_web_node.properties["start_location"], reddit_url)

    def test_qml_request_paste_selected_nodes_stages_screenshot_as_internal_png(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        image = QImage(10, 10, QImage.Format.Format_ARGB32)
        image.fill(QColor("#D24B3A"))
        mime_data = QMimeData()
        mime_data.setImageData(image)
        self.app.clipboard().setMimeData(mime_data)
        before_node_ids = set(self.window.model.project.workspaces[workspace_id].nodes)
        metadata_spy = QSignalSpy(self.window.project_meta_changed)

        pasted = self.window.request_paste_selected_nodes()
        self.assertTrue(pasted)
        self.app.processEvents()

        image_node = _new_workspace_nodes(self.window, before_node_ids)[0]
        self.assertEqual(image_node.type_id, MEDIA_PANEL_TYPE_ID)
        self.assertFalse(image_node.exposed_ports["source"])
        source_ref = str(image_node.properties["source"])
        self.assertTrue(source_ref.startswith("temp://"))
        store = self.window.project_session_controller.project_artifact_store()
        staged_entry = store.staged_entry(source_ref)
        staged_path = store.resolve_staged_path(source_ref)
        self.assertIsNotNone(staged_entry)
        self.assertIsNotNone(staged_path)
        assert staged_entry is not None and staged_path is not None
        staged_bytes = staged_path.read_bytes()
        self.assertEqual(staged_path.suffix.lower(), ".png")
        self.assertTrue(staged_bytes.startswith(b"\x89PNG"))
        self.assertEqual(staged_entry.extra["artifact_kind"], "clipboard_image_source")
        self.assertEqual(staged_entry.extra["mime_type"], "image/png")
        self.assertEqual(staged_entry.extra["size"], len(staged_bytes))
        self.assertEqual(
            staged_entry.extra["sha256"],
            hashlib.sha256(staged_bytes).hexdigest(),
        )
        self.assertEqual(staged_entry.extra["node_id"], image_node.node_id)
        self.assertEqual(len(metadata_spy), 1)

    def test_qml_request_paste_selected_nodes_stages_raw_pdf_and_video_bytes(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]

        pdf_mime = QMimeData()
        pdf_mime.setData("application/pdf", b"%PDF-1.4\nclipboard pdf bytes\n")
        self.app.clipboard().setMimeData(pdf_mime)
        before_node_ids = set(workspace.nodes)
        metadata_spy = QSignalSpy(self.window.project_meta_changed)
        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()
        pdf_node = _new_workspace_nodes(self.window, before_node_ids)[0]
        self.assertEqual(pdf_node.type_id, MEDIA_PANEL_TYPE_ID)
        self.assertFalse(pdf_node.exposed_ports["source"])
        pdf_ref = str(pdf_node.properties["source"])
        self.assertTrue(pdf_ref.startswith("temp://"))
        store = self.window.project_session_controller.project_artifact_store()
        pdf_entry = store.staged_entry(pdf_ref)
        pdf_path = store.resolve_staged_path(pdf_ref)
        self.assertIsNotNone(pdf_entry)
        self.assertIsNotNone(pdf_path)
        assert pdf_entry is not None and pdf_path is not None
        pdf_bytes = pdf_path.read_bytes()
        self.assertEqual(pdf_path.suffix.lower(), ".pdf")
        self.assertEqual(pdf_bytes, b"%PDF-1.4\nclipboard pdf bytes\n")
        self.assertEqual(pdf_entry.extra["artifact_kind"], "clipboard_pdf_source")
        self.assertEqual(pdf_entry.extra["mime_type"], "application/pdf")
        self.assertEqual(pdf_entry.extra["size"], len(pdf_bytes))
        self.assertEqual(
            pdf_entry.extra["sha256"],
            hashlib.sha256(pdf_bytes).hexdigest(),
        )
        self.assertEqual(pdf_entry.extra["node_id"], pdf_node.node_id)
        self.assertEqual(len(metadata_spy), 1)

        video_mime = QMimeData()
        video_mime.setData("video/mp4", b"\x00\x00\x00\x18ftypmp42")
        self.app.clipboard().setMimeData(video_mime)
        before_node_ids = set(workspace.nodes)
        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()
        video_node = _new_workspace_nodes(self.window, before_node_ids)[0]
        self.assertEqual(video_node.type_id, MEDIA_PANEL_TYPE_ID)
        self.assertFalse(video_node.exposed_ports["source"])
        video_ref = str(video_node.properties["source"])
        self.assertTrue(video_ref.startswith("temp://"))
        store = self.window.project_session_controller.project_artifact_store()
        video_entry = store.staged_entry(video_ref)
        video_path = store.resolve_staged_path(video_ref)
        self.assertIsNotNone(video_entry)
        self.assertIsNotNone(video_path)
        assert video_entry is not None and video_path is not None
        video_bytes = video_path.read_bytes()
        self.assertEqual(video_path.suffix.lower(), ".mp4")
        self.assertEqual(video_bytes, b"\x00\x00\x00\x18ftypmp42")
        self.assertEqual(video_entry.extra["artifact_kind"], "clipboard_video_source")
        self.assertEqual(video_entry.extra["mime_type"], "video/mp4")
        self.assertEqual(video_entry.extra["size"], len(video_bytes))
        self.assertEqual(
            video_entry.extra["sha256"],
            hashlib.sha256(video_bytes).hexdigest(),
        )
        self.assertEqual(video_entry.extra["node_id"], video_node.node_id)
        self.assertEqual(len(metadata_spy), 2)

    def test_raw_media_clipboard_staging_failure_rolls_back_created_node_and_history(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        image = QImage(10, 10, QImage.Format.Format_ARGB32)
        image.fill(QColor("#D24B3A"))
        mime_data = QMimeData()
        mime_data.setImageData(image)
        self.app.clipboard().setMimeData(mime_data)

        for pre_dirty, expected_revision in ((False, 211), (True, 307)):
            with self.subTest(pre_dirty=pre_dirty):
                workspace.dirty = pre_dirty
                workspace.mutation_revision = expected_revision
                self.window.runtime_history.clear_workspace(workspace_id)
                before_node_ids = set(workspace.nodes)
                before_edges = dict(workspace.edges)
                before_selection = _selected_node_ids(self.window)
                before_metadata = copy.deepcopy(self.window.model.project.metadata)

                with patch.object(
                    self.window.project_session_controller,
                    "stage_node_artifact_bytes",
                    return_value="",
                ), patch.object(CanvasImportController, "_report_failures") as reporter:
                    pasted = self.window.request_paste_selected_nodes()
                self.app.processEvents()

                self.assertFalse(pasted)
                reporter.assert_called_once()
                self.assertEqual(set(workspace.nodes), before_node_ids)
                self.assertEqual(workspace.edges, before_edges)
                self.assertEqual(_selected_node_ids(self.window), before_selection)
                self.assertEqual(self.window.model.project.metadata, before_metadata)
                self.assertEqual(workspace.dirty, pre_dirty)
                self.assertEqual(workspace.mutation_revision, expected_revision)
                self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), 0)
                self.assertEqual(self.window.runtime_history.redo_depth(workspace_id), 0)

    def test_qml_request_paste_selected_nodes_creates_text_annotations_for_html_and_plain_text(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]

        html_mime = QMimeData()
        html_mime.setHtml("<h1>Clipboard Title</h1><p>Hello <strong>world</strong>.</p><script>bad()</script>")
        self.app.clipboard().setMimeData(html_mime)
        before_node_ids = set(workspace.nodes)
        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()
        html_node = _new_workspace_nodes(self.window, before_node_ids)[0]
        self.assertEqual(html_node.type_id, "passive.annotation.text")
        self.assertEqual(html_node.properties["format"], "markdown")
        self.assertIn("Clipboard Title", html_node.properties["text"])
        self.assertIn("Hello world.", html_node.properties["text"])
        self.assertNotIn("bad()", html_node.properties["text"])

        self.app.clipboard().setText("Plain clipboard note")
        before_node_ids = set(workspace.nodes)
        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()
        text_node = _new_workspace_nodes(self.window, before_node_ids)[0]
        self.assertEqual(text_node.type_id, "passive.annotation.text")
        self.assertEqual(text_node.properties["format"], "plain")
        self.assertEqual(text_node.properties["text"], "Plain clipboard note")

    def test_qml_request_paste_selected_nodes_creates_tabular_input_for_tsv_table_choice(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        mime_data = QMimeData()
        mime_data.setText("Name\tValue\nAlpha\t10\nBeta\t20\n")
        self.app.clipboard().setMimeData(mime_data)
        before_node_ids = set(workspace.nodes)

        with patch.object(
            CanvasImportController,
            "_choose",
        ) as chooser:
            self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()

        chooser.assert_not_called()
        table_node = _new_workspace_nodes(self.window, before_node_ids)[0]
        self.assertEqual(table_node.type_id, "tabular.input")
        source_ref = str(table_node.properties["path"])
        self.assertTrue(source_ref.startswith("temp://"))
        staged_path = self.window.project_session_controller.project_artifact_store().resolve_staged_path(source_ref)
        self.assertIsNotNone(staged_path)
        assert staged_path is not None
        self.assertEqual(staged_path.suffix.lower(), ".tsv")
        self.assertEqual(staged_path.read_text(encoding="utf-8"), "Name\tValue\nAlpha\t10\nBeta\t20\n")

    def test_qml_request_paste_selected_nodes_creates_markdown_annotation_for_table_choice(self) -> None:
        self.window.app_preferences_controller.set_graphics_canvas_import_mode("ask")
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        mime_data = QMimeData()
        mime_data.setHtml(
            "<table><tr><th>Name</th><th>Value</th></tr>"
            "<tr><td>Alpha</td><td>10</td></tr><tr><td>Beta</td><td>20</td></tr></table>"
        )
        self.app.clipboard().setMimeData(mime_data)
        before_node_ids = set(workspace.nodes)

        with patch.object(
            CanvasImportController,
            "_choose",
            return_value=("markdown_table",),
        ) as chooser:
            self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()

        chooser.assert_called_once()
        table_node = _new_workspace_nodes(self.window, before_node_ids)[0]
        self.assertEqual(table_node.type_id, "passive.annotation.text")
        self.assertEqual(table_node.properties["format"], "markdown")
        self.assertEqual(
            table_node.properties["text"],
            "| Name | Value |\n| --- | --- |\n| Alpha | 10 |\n| Beta | 20 |",
        )

    def test_qml_request_paste_selected_nodes_cancels_table_choice_without_creating_node(self) -> None:
        self.window.app_preferences_controller.set_graphics_canvas_import_mode("ask")
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        mime_data = QMimeData()
        mime_data.setText("Name\tValue\nAlpha\t10\n")
        self.app.clipboard().setMimeData(mime_data)
        before_node_ids = set(workspace.nodes)

        with patch.object(
            CanvasImportController,
            "_choose",
            return_value=None,
        ) as chooser:
            self.assertFalse(self.window.request_paste_selected_nodes())
        self.app.processEvents()

        chooser.assert_called_once()
        self.assertEqual(set(workspace.nodes), before_node_ids)

    def test_group_backdrop_copy_and_paste_for_expanded_group_backdrop_keeps_descendants_explicit_only(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        logger_id = self.window.scene.add_node_from_type("core.logger", x=110.0, y=110.0)
        backdrop_id = self.window.scene.wrap_node_ids_in_group_backdrop([logger_id])
        self.assertTrue(backdrop_id)
        self.window.scene.set_node_collapsed(backdrop_id, False)
        self.app.processEvents()

        workspace = self.window.model.project.workspaces[workspace_id]
        before_nodes = len(workspace.nodes)
        before_backdrops = len(
            [node for node in workspace.nodes.values() if node.type_id == GROUP_BACKDROP_TYPE_ID]
        )

        self.window.scene.select_node(backdrop_id, False)
        self.assertTrue(self.window.request_copy_selected_nodes())
        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()

        workspace = self.window.model.project.workspaces[workspace_id]
        self.assertEqual(len(workspace.nodes), before_nodes + 1)
        self.assertEqual(
            len([node for node in workspace.nodes.values() if node.type_id == GROUP_BACKDROP_TYPE_ID]),
            before_backdrops + 1,
        )
        self.assertEqual(len([node for node in workspace.nodes.values() if node.type_id == "core.logger"]), 1)

        selected_pasted_ids = _selected_node_ids(self.window)
        self.assertEqual(len(selected_pasted_ids), 1)
        pasted_backdrop_id = next(iter(selected_pasted_ids))
        self.assertNotEqual(pasted_backdrop_id, backdrop_id)
        self.assertEqual(workspace.nodes[pasted_backdrop_id].type_id, GROUP_BACKDROP_TYPE_ID)
        self.assertEqual(_scene_payload(self.window, pasted_backdrop_id)["member_node_ids"], [])

    def test_group_backdrop_copy_and_paste_for_collapsed_group_backdrop_includes_descendants_and_internal_edges(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        start_id = self.window.scene.add_node_from_type("core.constant", x=220.0, y=160.0)
        end_id = self.window.scene.add_node_from_type("core.logger", x=220.0, y=360.0)
        outside_script_id = self.window.scene.add_node_from_type("core.python_script", x=760.0, y=240.0)
        self.window.scene.add_edge(start_id, "as_text", end_id, "message")
        self.window.scene.add_edge(start_id, "value", outside_script_id, "payload")
        backdrop_id = self.window.scene.wrap_node_ids_in_group_backdrop([start_id, end_id])
        self.assertTrue(backdrop_id)
        self.window.scene.set_node_collapsed(backdrop_id, True)
        self.app.processEvents()

        workspace = self.window.model.project.workspaces[workspace_id]
        before_nodes = len(workspace.nodes)
        before_edges = len(workspace.edges)

        self.window.scene.select_node(backdrop_id, False)
        self.assertTrue(self.window.request_copy_selected_nodes())
        self.assertTrue(self.window.request_paste_selected_nodes())
        self.app.processEvents()

        workspace = self.window.model.project.workspaces[workspace_id]
        self.assertEqual(len(workspace.nodes), before_nodes + 3)
        self.assertEqual(len(workspace.edges), before_edges + 1)

        selected_pasted_ids = _selected_node_ids(self.window)
        self.assertEqual(len(selected_pasted_ids), 3)
        pasted_backdrop_id = next(
            node_id for node_id in selected_pasted_ids if workspace.nodes[node_id].type_id == GROUP_BACKDROP_TYPE_ID
        )
        pasted_start_id = next(
            node_id for node_id in selected_pasted_ids if workspace.nodes[node_id].type_id == "core.constant"
        )
        pasted_end_id = next(
            node_id for node_id in selected_pasted_ids if workspace.nodes[node_id].type_id == "core.logger"
        )
        self.assertAlmostEqual(workspace.nodes[pasted_backdrop_id].x, workspace.nodes[backdrop_id].x + 40.0, places=6)
        self.assertAlmostEqual(workspace.nodes[pasted_end_id].x, workspace.nodes[end_id].x + 40.0, places=6)
        self.window.scene.set_node_collapsed(pasted_backdrop_id, False)
        self.app.processEvents()
        self.assertEqual(_scene_payload(self.window, pasted_end_id)["owner_backdrop_id"], pasted_backdrop_id)

        duplicated_internal_edges = [
            edge
            for edge in workspace.edges.values()
            if edge.source_node_id == pasted_start_id
            and edge.source_port_key == "as_text"
            and edge.target_node_id == pasted_end_id
            and edge.target_port_key == "message"
        ]
        self.assertEqual(len(duplicated_internal_edges), 1)
        duplicated_boundary_edges = [
            edge
            for edge in workspace.edges.values()
            if edge.source_node_id == pasted_start_id and edge.source_port_key == "value"
        ]
        self.assertEqual(duplicated_boundary_edges, [])

    def test_group_backdrop_delete_respects_expanded_and_collapsed_semantics(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        expanded_logger_id = self.window.scene.add_node_from_type("core.logger", x=110.0, y=110.0)
        expanded_backdrop_id = self.window.scene.wrap_node_ids_in_group_backdrop([expanded_logger_id])
        self.assertTrue(expanded_backdrop_id)
        self.window.scene.set_node_collapsed(expanded_backdrop_id, False)

        collapsed_start_id = self.window.scene.add_node_from_type("core.constant", x=220.0, y=160.0)
        collapsed_end_id = self.window.scene.add_node_from_type("core.logger", x=220.0, y=360.0)
        self.window.scene.add_edge(collapsed_start_id, "as_text", collapsed_end_id, "message")
        collapsed_backdrop_id = self.window.scene.wrap_node_ids_in_group_backdrop([collapsed_start_id, collapsed_end_id])
        self.assertTrue(collapsed_backdrop_id)
        self.window.scene.set_node_collapsed(collapsed_backdrop_id, True)
        self.app.processEvents()

        workspace = self.window.model.project.workspaces[workspace_id]

        self.window.scene.select_node(expanded_backdrop_id, False)
        self.assertTrue(self.window.request_delete_selected_graph_items([]))
        self.app.processEvents()
        self.assertNotIn(expanded_backdrop_id, workspace.nodes)
        self.assertIn(expanded_logger_id, workspace.nodes)

        self.window.scene.select_node(collapsed_backdrop_id, False)
        self.assertTrue(self.window.request_delete_selected_graph_items([]))
        self.app.processEvents()
        for removed_node_id in (collapsed_backdrop_id, collapsed_start_id, collapsed_end_id):
            self.assertNotIn(removed_node_id, workspace.nodes)

    def test_qml_request_cut_selected_nodes_is_single_undoable_semantic_action(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        source_id = self.window.scene.add_node_from_type("core.constant", x=80.0, y=70.0)
        target_id = self.window.scene.add_node_from_type("core.logger", x=300.0, y=80.0)
        self.window.scene.add_edge(source_id, "as_text", target_id, "message")
        self.window.scene.select_node(source_id, False)
        self.window.scene.select_node(target_id, True)
        before_state = self._workspace_state()
        before_depth = self.window.runtime_history.undo_depth(workspace_id)
        self.app.processEvents()

        cut = self.window.request_cut_selected_nodes()
        self.assertTrue(cut)
        self.app.processEvents()
        after_cut_state = self._workspace_state()
        self.assertNotEqual(after_cut_state, before_state)
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), before_depth + 1)

        self.window.action_undo.trigger()
        self.app.processEvents()
        self.assertEqual(self._workspace_state(), before_state)

        self.window.action_redo.trigger()
        self.app.processEvents()
        self.assertEqual(self._workspace_state(), after_cut_state)

    def test_qml_request_paste_selected_nodes_ignores_empty_and_unsupported_clipboard_payloads(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        self.window.scene.add_node_from_type("core.constant", x=25.0, y=35.0)
        before_state = self._workspace_state()
        before_depth = self.window.runtime_history.undo_depth(workspace_id)
        clipboard = self.app.clipboard()

        clipboard.clear()
        empty_paste = self.window.request_paste_selected_nodes()
        self.assertFalse(empty_paste)
        self.assertEqual(self._workspace_state(), before_state)
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), before_depth)

        unsupported_mime = QMimeData()
        unsupported_mime.setData("application/octet-stream", b"unsupported bytes")
        clipboard.setMimeData(unsupported_mime)
        unsupported_paste = self.window.request_paste_selected_nodes()
        self.assertFalse(unsupported_paste)
        self.assertEqual(self._workspace_state(), before_state)
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), before_depth)

    def test_undo_redo_roundtrips_supported_graph_mutations(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()

        def assert_roundtrip(mutate, label: str) -> None:  # noqa: ANN001
            before_state = self._workspace_state()
            before_depth = self.window.runtime_history.undo_depth(workspace_id)
            mutate()
            self.app.processEvents()
            after_state = self._workspace_state()
            self.assertNotEqual(before_state, after_state, label)
            self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), before_depth + 1, label)

            self.window.action_undo.trigger()
            self.app.processEvents()
            self.assertEqual(self._workspace_state(), before_state, f"{label}: undo")

            self.window.action_redo.trigger()
            self.app.processEvents()
            self.assertEqual(self._workspace_state(), after_state, f"{label}: redo")

        source_id = self.window.scene.add_node_from_type("core.constant", x=40.0, y=40.0)
        target_id = self.window.scene.add_node_from_type("core.logger", x=280.0, y=40.0)
        logger_id = self.window.scene.add_node_from_type("core.logger", x=520.0, y=120.0)
        self.app.processEvents()

        assert_roundtrip(
            lambda: self.window.scene.add_node_from_type("core.python_script", x=620.0, y=80.0),
            "add node",
        )

        edge_holder: dict[str, str] = {}

        def add_edge() -> None:
            edge_holder["edge_id"] = self.window.scene.add_edge(source_id, "as_text", target_id, "message")

        assert_roundtrip(add_edge, "add edge")
        primary_edge_id = edge_holder["edge_id"]

        assert_roundtrip(lambda: self.window.request_remove_edge(primary_edge_id), "remove edge")

        def rename_node() -> None:
            current_title = self.window.model.project.workspaces[workspace_id].nodes[source_id].title
            with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=(f"{current_title} (renamed)", True)):
                self.window.request_rename_node(source_id)

        assert_roundtrip(rename_node, "rename node")

        def toggle_collapse() -> None:
            self.window.scene.focus_node(source_id)
            self.window.set_selected_node_collapsed(not self.window.selected_node_collapsed)

        assert_roundtrip(toggle_collapse, "collapse toggle")

        self.window.scene.add_edge(source_id, "as_text", target_id, "message")
        self.app.processEvents()

        def toggle_exposed_port() -> None:
            workspace = self.window.model.project.workspaces[workspace_id]
            source_node = workspace.nodes[source_id]
            current = bool(source_node.exposed_ports.get("as_text", True))
            self.window.scene.focus_node(source_id)
            self.window.set_selected_port_exposed("as_text", not current)

        assert_roundtrip(toggle_exposed_port, "exposed-port toggle")

        def edit_property() -> None:
            self.window.scene.focus_node(logger_id)
            self.window.set_selected_node_property("message", "updated through undo/redo roundtrip")

        assert_roundtrip(edit_property, "property edit")

        delete_node_id = self.window.scene.add_node_from_type("core.python_script", x=680.0, y=150.0)
        delete_edge_id = self.window.scene.add_edge(source_id, "value", delete_node_id, "payload")
        self.window.scene.select_node(delete_node_id, False)
        self.app.processEvents()
        assert_roundtrip(
            lambda: self.window.request_delete_selected_graph_items([delete_edge_id]),
            "delete-selected",
        )

        def move_node() -> None:
            workspace = self.window.model.project.workspaces[workspace_id]
            source_node = workspace.nodes[source_id]
            self.window.scene.move_node(source_id, source_node.x + 130.0, source_node.y + 75.0)

        assert_roundtrip(move_node, "node move")

        def move_group_nodes() -> None:
            self.window.scene.select_node(source_id, False)
            self.window.scene.select_node(logger_id, True)
            self.window.scene.move_nodes_by_delta([source_id, logger_id], 90.0, 35.0)

        assert_roundtrip(move_group_nodes, "group node move")

        def duplicate_selection() -> None:
            self.window.scene.select_node(source_id, False)
            self.window.scene.select_node(target_id, True)
            self.window.request_duplicate_selected_nodes()

        assert_roundtrip(duplicate_selection, "duplicate-selection")

        assert_roundtrip(lambda: self.window.request_remove_node(target_id), "remove node")

    def test_persistent_node_elapsed_invalidation_clears_execution_affecting_history_commit_undo_redo(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        foreign_workspace_id = self.window.workspace_manager.create_workspace("Elapsed Cache Control")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(workspace_id)
        self.window.run_controller.set_auto_run_enabled(False)
        runner_id = self.window.scene.add_node_from_type("core.constant", x=20.0, y=20.0)
        logger_id = self.window.scene.add_node_from_type("core.logger", x=260.0, y=40.0)
        self.app.processEvents()
        self.window.runtime_history.clear_workspace(workspace_id)
        bridge = self.window.graph_canvas_state_bridge

        _seed_persistent_node_elapsed_state(
            self.window,
            workspace_id=workspace_id,
            foreign_workspace_id=foreign_workspace_id,
            running_node_id=runner_id,
            cached_node_id=logger_id,
        )
        self.app.processEvents()
        first_revision = bridge.node_execution_revision

        self.window.scene.set_node_property(logger_id, "message", "Updated execution payload")
        self.app.processEvents()

        self.assertEqual(bridge.running_node_started_at_ms_lookup, {runner_id: 125.0})
        self.assertEqual(bridge.node_elapsed_ms_lookup, {})
        self.assertGreater(bridge.node_execution_revision, first_revision)
        self.assertNotIn(workspace_id, self.window.run_state.cached_node_elapsed_ms_by_workspace_id)
        self.assertEqual(
            self.window.run_state.cached_node_elapsed_ms_by_workspace_id[foreign_workspace_id],
            {"node_foreign": 91.0},
        )

        _seed_persistent_node_elapsed_state(
            self.window,
            workspace_id=workspace_id,
            foreign_workspace_id=foreign_workspace_id,
            running_node_id=runner_id,
            cached_node_id=logger_id,
        )
        self.app.processEvents()
        second_revision = bridge.node_execution_revision

        self.window.action_undo.trigger()
        self.app.processEvents()

        self.assertEqual(bridge.running_node_started_at_ms_lookup, {runner_id: 125.0})
        self.assertEqual(bridge.node_elapsed_ms_lookup, {})
        self.assertGreater(bridge.node_execution_revision, second_revision)
        self.assertNotIn(workspace_id, self.window.run_state.cached_node_elapsed_ms_by_workspace_id)
        self.assertEqual(
            self.window.run_state.cached_node_elapsed_ms_by_workspace_id[foreign_workspace_id],
            {"node_foreign": 91.0},
        )

        _seed_persistent_node_elapsed_state(
            self.window,
            workspace_id=workspace_id,
            foreign_workspace_id=foreign_workspace_id,
            running_node_id=runner_id,
            cached_node_id=logger_id,
        )
        self.app.processEvents()
        third_revision = bridge.node_execution_revision

        self.window.action_redo.trigger()
        self.app.processEvents()

        self.assertEqual(bridge.running_node_started_at_ms_lookup, {runner_id: 125.0})
        self.assertEqual(bridge.node_elapsed_ms_lookup, {})
        self.assertGreater(bridge.node_execution_revision, third_revision)
        self.assertNotIn(workspace_id, self.window.run_state.cached_node_elapsed_ms_by_workspace_id)
        self.assertEqual(
            self.window.run_state.cached_node_elapsed_ms_by_workspace_id[foreign_workspace_id],
            {"node_foreign": 91.0},
        )

    def test_persistent_node_elapsed_invalidation_preserves_comment_only_history_commit_undo_redo(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        foreign_workspace_id = self.window.workspace_manager.create_workspace("Elapsed Cache Control")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(workspace_id)
        self.window.run_controller.set_auto_run_enabled(False)
        runner_id = self.window.scene.add_node_from_type("core.constant", x=40.0, y=20.0)
        comment_id = self.window.scene.add_node_from_type(
            "passive.annotation.sticky_note",
            x=220.0,
            y=60.0,
        )
        self.app.processEvents()
        self.window.runtime_history.clear_workspace(workspace_id)
        bridge = self.window.graph_canvas_state_bridge
        expected_running_lookup, expected_elapsed_lookup = _seed_persistent_node_elapsed_state(
            self.window,
            workspace_id=workspace_id,
            foreign_workspace_id=foreign_workspace_id,
            running_node_id=runner_id,
            cached_node_id=comment_id,
        )
        self.app.processEvents()
        first_revision = bridge.node_execution_revision

        self.window.scene.set_node_property(comment_id, "body", "Context only note")
        self.app.processEvents()

        self.assertEqual(bridge.running_node_started_at_ms_lookup, expected_running_lookup)
        self.assertEqual(bridge.node_elapsed_ms_lookup, expected_elapsed_lookup)
        self.assertEqual(bridge.node_execution_revision, first_revision)
        self.assertEqual(
            self.window.run_state.cached_node_elapsed_ms_by_workspace_id[foreign_workspace_id],
            {"node_foreign": 91.0},
        )

        self.window.action_undo.trigger()
        self.app.processEvents()

        self.assertEqual(bridge.running_node_started_at_ms_lookup, expected_running_lookup)
        self.assertEqual(bridge.node_elapsed_ms_lookup, expected_elapsed_lookup)
        self.assertEqual(bridge.node_execution_revision, first_revision)
        self.assertEqual(
            self.window.run_state.cached_node_elapsed_ms_by_workspace_id[foreign_workspace_id],
            {"node_foreign": 91.0},
        )

        self.window.action_redo.trigger()
        self.app.processEvents()

        self.assertEqual(bridge.running_node_started_at_ms_lookup, expected_running_lookup)
        self.assertEqual(bridge.node_elapsed_ms_lookup, expected_elapsed_lookup)
        self.assertEqual(bridge.node_execution_revision, first_revision)
        self.assertEqual(
            self.window.run_state.cached_node_elapsed_ms_by_workspace_id[foreign_workspace_id],
            {"node_foreign": 91.0},
        )

    def test_undo_redo_isolated_per_workspace_and_redo_clears_after_new_mutation(self) -> None:
        workspace_a_id = self.window.workspace_manager.active_workspace_id()
        node_a_id = self.window.scene.add_node_from_type("core.constant", x=20.0, y=20.0)
        self.app.processEvents()

        workspace_b_id = self.window.workspace_manager.create_workspace("Secondary")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(workspace_b_id)
        self.app.processEvents()

        self.assertEqual(self.window.runtime_history.undo_depth(workspace_b_id), 0)
        node_b_id = self.window.scene.add_node_from_type("core.logger", x=40.0, y=40.0)
        self.app.processEvents()
        self.assertIn(node_b_id, self.window.model.project.workspaces[workspace_b_id].nodes)

        self.window.action_undo.trigger()
        self.app.processEvents()
        self.assertNotIn(node_b_id, self.window.model.project.workspaces[workspace_b_id].nodes)
        self.assertIn(node_a_id, self.window.model.project.workspaces[workspace_a_id].nodes)

        self.window.action_redo.trigger()
        self.app.processEvents()
        self.assertIn(node_b_id, self.window.model.project.workspaces[workspace_b_id].nodes)

        self.window.action_undo.trigger()
        self.app.processEvents()
        self.assertEqual(self.window.runtime_history.redo_depth(workspace_b_id), 1)

        replacement_node_id = self.window.scene.add_node_from_type("core.logger", x=120.0, y=50.0)
        self.app.processEvents()
        self.assertIn(replacement_node_id, self.window.model.project.workspaces[workspace_b_id].nodes)
        self.assertEqual(self.window.runtime_history.redo_depth(workspace_b_id), 0)

        before_failed_redo = self._workspace_state()
        self.window.action_redo.trigger()
        self.app.processEvents()
        self.assertEqual(self._workspace_state(), before_failed_redo)

        self.window.workspace_navigation_controller.switch_workspace(workspace_a_id)
        self.app.processEvents()
        self.window.action_undo.trigger()
        self.app.processEvents()
        self.assertNotIn(node_a_id, self.window.model.project.workspaces[workspace_a_id].nodes)
        self.assertIn(replacement_node_id, self.window.model.project.workspaces[workspace_b_id].nodes)

    def test_new_and_duplicated_workspaces_start_with_empty_history(self) -> None:
        workspace_a_id = self.window.workspace_manager.active_workspace_id()
        self.window.scene.add_node_from_type("core.constant", x=10.0, y=10.0)
        self.app.processEvents()
        self.assertGreater(self.window.runtime_history.undo_depth(workspace_a_id), 0)

        workspace_b_id = self.window.workspace_manager.create_workspace("New Workspace")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_b_id), 0)
        self.assertEqual(self.window.runtime_history.redo_depth(workspace_b_id), 0)

        self.window.workspace_navigation_controller.switch_workspace(workspace_a_id)
        self.app.processEvents()
        duplicated_id = self.window.workspace_manager.duplicate_workspace(workspace_a_id)
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.assertEqual(self.window.runtime_history.undo_depth(duplicated_id), 0)
        self.assertEqual(self.window.runtime_history.redo_depth(duplicated_id), 0)

    def test_new_project_clears_runtime_history_stacks(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        self.window.scene.add_node_from_type("core.constant", x=0.0, y=0.0)
        self.app.processEvents()
        self.assertGreater(self.window.runtime_history.undo_depth(workspace_id), 0)

        with patch.object(
            self.window.project_session_controller._document_service,
            "_confirm_project_replacement",
            return_value=True,
        ):
            self.window.action_new_project.trigger()
        self.app.processEvents()

        new_workspace_id = self.window.workspace_manager.active_workspace_id()
        self.assertEqual(self.window.runtime_history.undo_depth(new_workspace_id), 0)
        self.assertEqual(self.window.runtime_history.redo_depth(new_workspace_id), 0)
