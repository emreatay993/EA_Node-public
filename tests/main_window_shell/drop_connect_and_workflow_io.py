from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtTest import QTest

from ea_node_editor.custom_workflows import import_custom_workflow_file
from ea_node_editor.nodes.category_paths import category_key
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from tests.main_window_shell.base import *  # noqa: F401,F403
from tests.main_window_shell.base import _action_shortcuts
from tests.main_window_shell.bridge_support import _named_child_items


def _qml_variant_map(raw_value) -> dict[str, object]:  # noqa: ANN001
    if hasattr(raw_value, "toVariant"):
        raw_value = raw_value.toVariant()
    if not isinstance(raw_value, dict):
        return {}
    return {str(key): value for key, value in raw_value.items()}


def _single_inserted_node_id(workspace, before_node_ids: set[str]) -> str:  # noqa: ANN001
    (node_id,) = set(workspace.nodes).difference(before_node_ids)
    return node_id


class MainWindowShellDropConnectAndWorkflowIOTests(SharedMainWindowShellTestBase):
    _DEEP_CATEGORY_PATH = ("Engineering Analysis", "Simulation", "Results")
    _DEEP_CATEGORY_TYPE_ID = "tests.deep_category_result"

    def _register_deep_category_fixture(self) -> None:
        if self.window.registry.spec_or_none(self._DEEP_CATEGORY_TYPE_ID) is None:
            self.window.registry.register_descriptor(
                NodeTypeSpec(
                    type_id=self._DEEP_CATEGORY_TYPE_ID,
                    display_name="Deep Category Result",
                    category_path=self._DEEP_CATEGORY_PATH,
                    icon="",
                    ports=(),
                    properties=(),
                    description="Retained fixture for nested library-category behavior.",
                    keywords=("nested", "category"),
                ),
                lambda: SimpleNamespace(),
            )
        self.window.shell_library_presenter._invalidate_registry_items()
        self.window.node_library_changed.emit()
        self.app.processEvents()

    def test_file_menu_new_project_resets_to_blank_project(self) -> None:
        self.window.scene.add_node_from_type("core.constant", x=40.0, y=40.0)
        self.window.workspace_manager.create_workspace("Second")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.project_path = str(Path(self._temp_dir.name) / "existing_project.cxproj")
        self.app.processEvents()

        file_menu = None
        for action in self.window.menuBar().actions():
            if action.text() == "&File":
                file_menu = action.menu()
                break
        self.assertIsNotNone(file_menu)
        file_entries = [action.text() for action in file_menu.actions() if not action.isSeparator()]
        self.assertIn("New Project", file_entries)
        self.assertIn("Ctrl+N", _action_shortcuts(self.window.action_new_project))

        with patch.object(
            self.window.project_session_controller._document_service,
            "_confirm_project_replacement",
            return_value=True,
        ):
            self.window.action_new_project.trigger()
        self.app.processEvents()

        self.assertEqual(self.window.project_path, "")
        self.assertEqual(self.window.project_display_name, "COREX Node Editor - untitled.cxproj")
        self.assertEqual(len(self.window.model.project.workspaces), 1)
        active_workspace_id = self.window.workspace_manager.active_workspace_id()
        active_workspace = self.window.model.project.workspaces[active_workspace_id]
        self.assertEqual(active_workspace.nodes, {})
        self.assertEqual(active_workspace.edges, {})
        self.assertFalse(active_workspace.dirty)

    def test_recent_files_menu_tracks_saved_projects_and_restores_from_session(self) -> None:
        alpha_path = Path(self._temp_dir.name) / "projects" / "alpha_project.cxproj"
        alpha_path.parent.mkdir(parents=True, exist_ok=True)

        self.window.project_path = str(alpha_path)
        self.window._save_project()
        self.app.processEvents()

        self.assertEqual(self.window.recent_project_paths, [str(alpha_path)])
        recent_actions = [action for action in self.window.menu_recent_projects.actions() if not action.isSeparator()]
        self.assertEqual(recent_actions[0].text(), f"1. alpha_project.cxproj [{alpha_path.parent}]")
        self.assertFalse(recent_actions[0].isEnabled())
        self.assertEqual(recent_actions[-1].text(), "Clear Recent Files")

        session_payload = json.loads(self._session_path.read_text(encoding="utf-8"))
        self.assertEqual(session_payload["recent_project_paths"], [str(alpha_path)])

        self._reopen_shared_window()
        restored = self.window
        self.assertEqual(restored.recent_project_paths, [str(alpha_path)])
        restored_actions = [action for action in restored.menu_recent_projects.actions() if not action.isSeparator()]
        self.assertEqual(restored_actions[0].text(), f"1. alpha_project.cxproj [{alpha_path.parent}]")
        self.assertEqual(restored.project_path, "")
        self.assertTrue(restored_actions[0].isEnabled())

    def test_recent_files_menu_action_opens_selected_project(self) -> None:
        alpha_path = Path(self._temp_dir.name) / "alpha_project.cxproj"
        beta_path = Path(self._temp_dir.name) / "beta_project.cxproj"

        alpha_node_id = self.window.scene.add_node_from_type("core.constant", x=40.0, y=40.0)
        self.window.project_path = str(alpha_path)
        self.window._save_project()
        self.app.processEvents()

        with patch.object(
            self.window.project_session_controller._document_service,
            "_confirm_project_replacement",
            return_value=True,
        ):
            self.window._new_project()
        beta_node_id = self.window.scene.add_node_from_type("core.logger", x=160.0, y=40.0)
        self.window.project_path = str(beta_path)
        self.window._save_project()
        self.app.processEvents()

        recent_actions = [action for action in self.window.menu_recent_projects.actions() if not action.isSeparator()]
        self.assertEqual(self.window.recent_project_paths, [str(beta_path), str(alpha_path)])
        self.assertFalse(recent_actions[0].isEnabled())
        recent_actions[1].trigger()
        self.app.processEvents()

        self.assertEqual(self.window.project_path, str(alpha_path))
        self.assertEqual(self.window.recent_project_paths, [str(alpha_path), str(beta_path)])
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        self.assertIn(alpha_node_id, workspace.nodes)
        self.assertNotIn(beta_node_id, workspace.nodes)

    def test_qml_connect_selected_supports_additive_selection(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        source_id = self.window.scene.add_node_from_type("core.python_script", x=40.0, y=40.0)
        target_id = self.window.scene.add_node_from_type("core.logger", x=280.0, y=40.0)
        self.window.scene.select_node(source_id)
        self.window.scene.select_node(target_id, True)
        self.app.processEvents()

        self.window.request_connect_selected_nodes()
        self.app.processEvents()

        edges = self.window.model.project.workspaces[workspace_id].edges
        self.assertEqual(len(edges), 1)

    def test_qml_connect_ports_orients_bidirectional_drag_request(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        source_id = self.window.scene.add_node_from_type("core.python_script", x=40.0, y=40.0)
        target_id = self.window.scene.add_node_from_type("core.logger", x=280.0, y=40.0)
        self.app.processEvents()

        created = self.window.request_connect_ports(source_id, "result", target_id, "message")
        self.assertTrue(created)
        edge_id = next(iter(self.window.model.project.workspaces[workspace_id].edges))
        removed = self.window.request_remove_edge(edge_id)
        self.assertTrue(removed)
        self.app.processEvents()

        created_reversed = self.window.request_connect_ports(target_id, "message", source_id, "result")
        self.assertTrue(created_reversed)
        edges = self.window.model.project.workspaces[workspace_id].edges
        self.assertEqual(len(edges), 1)
        edge = next(iter(edges.values()))
        self.assertEqual(edge.source_node_id, source_id)
        self.assertEqual(edge.target_node_id, target_id)
        self.assertEqual(edge.source_port_key, "result")
        self.assertEqual(edge.target_port_key, "message")

    def test_qml_connect_ports_rejects_same_direction(self) -> None:
        source_id = self.window.scene.add_node_from_type("core.python_script", x=40.0, y=40.0)
        target_id = self.window.scene.add_node_from_type("core.python_script", x=280.0, y=40.0)
        self.app.processEvents()

        created = self.window.request_connect_ports(source_id, "result", target_id, "result")
        self.assertFalse(created)

    def test_qml_connect_ports_accepts_same_node_data_edge_for_runtime_cycle_detection(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.python_script", x=40.0, y=40.0)
        self.app.processEvents()

        created = self.window.request_connect_ports(node_id, "result", node_id, "payload")
        self.assertTrue(created)
        edges = self.window.model.project.workspaces[workspace_id].edges
        self.assertEqual(len(edges), 1)

    def test_qml_connect_ports_rejects_passive_flow_to_data_kind_mismatch(self) -> None:
        source_id = self.window.scene.add_node_from_type(
            "passive.flowchart.process", x=40.0, y=40.0
        )
        target_id = self.window.scene.add_node_from_type("core.if", x=280.0, y=40.0)
        self.app.processEvents()

        created = self.window.request_connect_ports(source_id, "right", target_id, "condition")
        self.assertFalse(created)

    def test_qml_nested_category_library_payload_filters_and_quick_insert_use_path_values(self) -> None:
        self._register_deep_category_fixture()
        self.window.set_library_query("")
        self.window.set_library_direction("")
        self.window.set_library_data_type("")
        self.app.processEvents()

        options_by_label = {
            option["label"]: option for option in self.window.library_category_options
        }
        root_path = self._DEEP_CATEGORY_PATH[:1]
        leaf_label = " > ".join(self._DEEP_CATEGORY_PATH)
        leaf_key = category_key(self._DEEP_CATEGORY_PATH)
        self.assertEqual(options_by_label[root_path[0]]["value"], category_key(root_path))
        self.assertEqual(options_by_label[leaf_label]["value"], leaf_key)

        self.window.set_library_category(options_by_label[root_path[0]]["value"])
        self.app.processEvents()
        self.assertIn(
            leaf_label,
            {item["category"] for item in self.window.filtered_node_library_items},
        )

        self.window.set_library_category(leaf_key)
        self.app.processEvents()
        leaf_items = self.window.filtered_node_library_items
        self.assertTrue(leaf_items)
        self.assertTrue(all(item["category"] == leaf_label for item in leaf_items))

        self.window.request_open_canvas_quick_insert(320.0, 160.0, 420.0, 220.0)
        self.window.set_connection_quick_insert_query(leaf_label)
        self.app.processEvents()
        results = self.window.connection_quick_insert_results
        self.assertTrue(results)
        self.assertTrue(all(item["category"] == leaf_label for item in results))
        self.assertTrue(all(item["category_key"] == leaf_key for item in results))

    def test_nested_category_qml_descendants_require_each_ancestor_expanded(self) -> None:
        self._register_deep_category_fixture()
        library_pane = self._library_pane_item()
        root_key = category_key(self._DEEP_CATEGORY_PATH[:1])
        middle_key = category_key(self._DEEP_CATEGORY_PATH[:2])
        leaf_key = category_key(self._DEEP_CATEGORY_PATH)

        def collapsed_map() -> dict[str, bool]:
            return {
                key: bool(value)
                for key, value in _qml_variant_map(
                    library_pane.property("collapsedCategories")
                ).items()
            }

        def library_rows():  # noqa: ANN202
            self.app.processEvents()
            return _named_child_items(library_pane, "nodeLibraryRow")

        def category_row(category_key_value: str):  # noqa: ANN202
            return next(
                row
                for row in library_rows()
                if bool(row.property("isCategory"))
                and str(row.property("rowCategoryKey") or "") == category_key_value
            )

        def node_row():  # noqa: ANN202
            return next(
                row
                for row in library_rows()
                if str(row.property("rowTypeId") or "") == self._DEEP_CATEGORY_TYPE_ID
            )

        collapsed = collapsed_map()
        self.assertTrue(collapsed.get(root_key, False))
        self.assertTrue(collapsed.get(middle_key, False))
        self.assertTrue(collapsed.get(leaf_key, False))
        self.assertEqual(int(category_row(root_key).property("rowDepth")), 0)
        self.assertEqual(int(category_row(middle_key).property("rowDepth")), 1)
        self.assertEqual(int(category_row(leaf_key).property("rowDepth")), 2)
        self.assertEqual(int(node_row().property("rowDepth")), 3)
        self.assertFalse(bool(category_row(root_key).property("hiddenByAncestors")))
        self.assertTrue(bool(category_row(middle_key).property("hiddenByAncestors")))
        self.assertTrue(bool(category_row(leaf_key).property("hiddenByAncestors")))
        self.assertTrue(bool(node_row().property("hiddenByAncestors")))

        for key, revealed in (
            (root_key, middle_key),
            (middle_key, leaf_key),
            (leaf_key, self._DEEP_CATEGORY_TYPE_ID),
        ):
            next_collapsed = collapsed_map()
            next_collapsed[key] = False
            library_pane.setProperty("collapsedCategories", next_collapsed)
            self.app.processEvents()
            revealed_row = (
                node_row()
                if revealed == self._DEEP_CATEGORY_TYPE_ID
                else category_row(revealed)
            )
            self.assertFalse(bool(revealed_row.property("hiddenByAncestors")))

        self.assertTrue(bool(node_row().property("visible")))
        self.assertEqual(float(node_row().property("height")), 28.0)

    def test_qml_request_drop_node_from_library_places_node_at_exact_scene_position(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        before_node_ids = set(workspace.nodes)
        selected_before = set(self.window.scene.selected_node_lookup)
        placed = self.window.request_drop_node_from_library(
            "core.constant",
            123.5,
            456.25,
            "",
            "",
            "",
            "",
        )
        self.assertTrue(placed)
        self.app.processEvents()

        node_id = _single_inserted_node_id(workspace, before_node_ids)
        self.assertEqual(set(self.window.scene.selected_node_lookup), selected_before)
        self.assertNotIn(node_id, selected_before)
        node = workspace.nodes[node_id]
        self.assertAlmostEqual(node.x, 123.5, places=4)
        self.assertAlmostEqual(node.y, 456.25, places=4)
        self.assertEqual(len(workspace.edges), 0)

    def test_qml_request_drop_node_from_library_port_target_autoconnects_single_candidate(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        target_id = self.window.scene.add_node_from_type("core.logger", x=360.0, y=40.0)
        self.app.processEvents()
        before_node_ids = set(workspace.nodes)
        selected_before = set(self.window.scene.selected_node_lookup)

        created = self.window.request_drop_node_from_library(
            "core.python_script",
            120.0,
            60.0,
            "port",
            target_id,
            "message",
            "",
        )
        self.assertTrue(created)
        self.app.processEvents()

        self.assertEqual(len(workspace.edges), 1)
        new_node_id = _single_inserted_node_id(workspace, before_node_ids)
        self.assertEqual(set(self.window.scene.selected_node_lookup), selected_before)
        self.assertNotIn(new_node_id, selected_before)
        edge = next(iter(workspace.edges.values()))
        self.assertEqual(edge.source_node_id, new_node_id)
        self.assertEqual(edge.source_port_key, "result")
        self.assertEqual(edge.target_node_id, target_id)
        self.assertEqual(edge.target_port_key, "message")

    def test_qml_request_drop_node_from_library_port_target_ambiguous_uses_prompt_selection(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        target_id = self.window.scene.add_node_from_type("core.python_script", x=360.0, y=40.0)
        self.app.processEvents()

        with patch(
            "PyQt6.QtWidgets.QInputDialog.getItem",
            return_value=("Constant.as_text -> Python Script.Payload", True),
        ):
            created = self.window.request_drop_node_from_library(
                "core.constant",
                160.0,
                90.0,
                "port",
                target_id,
                "payload",
                "",
            )
        self.assertTrue(created)
        self.app.processEvents()

        workspace = self.window.model.project.workspaces[workspace_id]
        self.assertEqual(len(workspace.edges), 1)
        edge = next(iter(workspace.edges.values()))
        self.assertEqual(edge.target_node_id, target_id)
        self.assertEqual(edge.target_port_key, "payload")
        self.assertEqual(edge.source_port_key, "as_text")

    def test_qml_request_drop_node_from_library_edge_target_inserts_inline(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        source_id = self.window.scene.add_node_from_type("core.constant", x=20.0, y=20.0)
        target_id = self.window.scene.add_node_from_type("core.logger", x=380.0, y=20.0)
        edge_id = self.window.scene.add_edge(source_id, "as_text", target_id, "message")
        self.app.processEvents()
        before_node_ids = set(workspace.nodes)
        selected_before = set(self.window.scene.selected_node_lookup)

        created = self.window.request_drop_node_from_library(
            "core.python_script",
            210.0,
            90.0,
            "edge",
            "",
            "",
            edge_id,
        )
        self.assertTrue(created)
        self.app.processEvents()

        self.assertNotIn(edge_id, workspace.edges)
        self.assertEqual(len(workspace.edges), 2)
        new_node_id = _single_inserted_node_id(workspace, before_node_ids)
        self.assertEqual(set(self.window.scene.selected_node_lookup), selected_before)
        self.assertNotIn(new_node_id, selected_before)

        edge_tuples = {
            (edge.source_node_id, edge.source_port_key, edge.target_node_id, edge.target_port_key)
            for edge in workspace.edges.values()
        }
        self.assertIn((source_id, "as_text", new_node_id, "payload"), edge_tuples)
        self.assertIn((new_node_id, "result", target_id, "message"), edge_tuples)

    def test_qml_request_drop_node_from_library_falls_back_to_node_only_when_no_valid_connection(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        target_id = self.window.scene.add_node_from_type("core.logger", x=320.0, y=20.0)
        self.app.processEvents()
        before_node_ids = set(workspace.nodes)
        selected_before = set(self.window.scene.selected_node_lookup)

        created = self.window.request_drop_node_from_library(
            "core.logger",
            120.0,
            140.0,
            "port",
            target_id,
            "message",
            "",
        )
        self.assertTrue(created)
        self.app.processEvents()

        self.assertEqual(len(workspace.edges), 0)
        new_node_id = _single_inserted_node_id(workspace, before_node_ids)
        self.assertEqual(set(self.window.scene.selected_node_lookup), selected_before)
        self.assertNotIn(new_node_id, selected_before)
        self.assertIn(new_node_id, workspace.nodes)

    def test_qml_connection_quick_insert_filters_results_and_accepts_choice(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        target_id = self.window.scene.add_node_from_type("core.if", x=320.0, y=40.0)
        self.app.processEvents()
        before_node_ids = set(workspace.nodes)
        selected_before = set(self.window.scene.selected_node_lookup)

        opened = self.window.request_open_connection_quick_insert(
            target_id,
            "condition",
            220.0,
            80.0,
            340.0,
            180.0,
        )
        self.assertTrue(opened)
        self.assertTrue(self.window.connection_quick_insert_open)
        self.assertGreater(len(self.window.connection_quick_insert_results), 0)

        self.window.set_connection_quick_insert_query("constant")
        self.app.processEvents()

        results = self.window.connection_quick_insert_results
        self.assertTrue(results)
        self.assertTrue(all("constant" in str(item["display_name"]).lower() for item in results))

        chosen_index = next(
            index
            for index, item in enumerate(results)
            if item.get("type_id") == "core.constant"
        )
        created = self.window.request_connection_quick_insert_choose(chosen_index)
        self.assertTrue(created)
        self.app.processEvents()

        self.assertFalse(self.window.connection_quick_insert_open)
        self.assertEqual(len(workspace.edges), 1)
        edge = next(iter(workspace.edges.values()))
        new_node_id = _single_inserted_node_id(workspace, before_node_ids)
        self.assertEqual(set(self.window.scene.selected_node_lookup), selected_before)
        self.assertNotIn(new_node_id, selected_before)
        self.assertEqual(edge.source_node_id, new_node_id)
        self.assertEqual(edge.source_port_key, "value")
        self.assertEqual(edge.target_node_id, target_id)
        self.assertEqual(edge.target_port_key, "condition")

    def test_qml_connection_quick_insert_allows_connected_input_replacement(self) -> None:
        source_id = self.window.scene.add_node_from_type("core.constant", x=40.0, y=40.0)
        target_id = self.window.scene.add_node_from_type("core.if", x=320.0, y=40.0)
        self.window.scene.add_edge(source_id, "value", target_id, "condition")
        self.app.processEvents()

        opened = self.window.request_open_connection_quick_insert(
            target_id,
            "condition",
            220.0,
            40.0,
            240.0,
            140.0,
        )
        self.assertTrue(opened)
        self.assertTrue(self.window.connection_quick_insert_open)
        self.assertTrue(self.window.connection_quick_insert_results)

    def test_qml_connection_quick_insert_path_filters_plot_series_but_keeps_exports(self) -> None:
        path_node_id = self.window.scene.add_node_from_type("io.file_write", x=40.0, y=40.0)
        path_target_id = self.window.scene.add_node_from_type("io.file_read", x=40.0, y=240.0)
        self.app.processEvents()

        opened = self.window.request_open_connection_quick_insert(
            path_node_id,
            "written_path",
            220.0,
            80.0,
            340.0,
            180.0,
        )
        self.assertTrue(opened)
        self.window.set_connection_quick_insert_query("bar plot")
        self.app.processEvents()

        output_results = self.window.connection_quick_insert_results
        self.assertNotIn(
            "plot.bar",
            {str(item.get("type_id", "")) for item in output_results},
        )
        self.window.request_close_connection_quick_insert()

        opened = self.window.request_open_connection_quick_insert(
            path_target_id,
            "path",
            220.0,
            80.0,
            340.0,
            180.0,
        )
        self.assertTrue(opened)
        self.window.set_connection_quick_insert_query("bar plot")
        self.app.processEvents()

        bar_plot = next(
            item
            for item in self.window.connection_quick_insert_results
            if item.get("type_id") == "plot.bar"
        )
        self.assertEqual(
            [str(port.get("key", "")) for port in bar_plot["compatible_ports"]],
            ["static_export", "data_export"],
        )

    def test_qml_connection_quick_insert_geometry_group_uses_typed_rows_and_reconnects(self) -> None:
        workspace = self.window.model.active_workspace
        source_id = self.window.scene.add_node_from_type("geometry.construct_group", x=40.0, y=40.0)
        self.app.processEvents()
        self.assertTrue(self.window.request_open_connection_quick_insert(source_id, "group", 300.0, 60.0, 400.0, 180.0))
        rows = self.window.connection_quick_insert_results
        self.assertIn("model.viewer", {row["type_id"] for row in rows})
        self.assertTrue(all(row["compatibility_kind"] not in {"generic", "runtime_check"} for row in rows))
        self.window.set_connection_quick_insert_query("panel")
        panel = next(row for row in self.window.connection_quick_insert_results if row["type_id"] == "data.panel")
        self.assertEqual(panel["compatibility_label"], "Broad data match")
        self.window.set_connection_quick_insert_query("")
        index = next(index for index, row in enumerate(self.window.connection_quick_insert_results) if row["type_id"] == "model.viewer")
        self.assertTrue(self.window.request_connection_quick_insert_choose(index))
        edge = next(iter(workspace.edges.values()))
        self.assertEqual((edge.source_node_id, edge.source_port_key, edge.target_port_key), (source_id, "group", "scene_1"))
        self.assertTrue(
            self.window.request_open_connection_quick_insert(
                edge.target_node_id,
                edge.target_port_key,
                200.0,
                100.0,
                300.0,
                150.0,
            )
        )
        reverse_rows = {row["type_id"]: row for row in self.window.connection_quick_insert_results}
        self.assertEqual(reverse_rows["geometry.construct_group"]["compatibility_kind"], "exact")
        self.assertNotIn("core.constant", reverse_rows)

    def test_qml_connection_quick_insert_default_dynamic_output_connects_selected_key(self) -> None:
        workspace = self.window.model.active_workspace
        target_id = self.window.scene.add_node_from_type("core.if", x=320.0, y=40.0)
        self.assertTrue(self.window.request_open_connection_quick_insert(target_id, "condition", 120.0, 60.0, 300.0, 180.0))
        self.window.set_connection_quick_insert_query("python script")
        rows = self.window.connection_quick_insert_results
        index = next(index for index, row in enumerate(rows) if row["type_id"] == "core.python_script")
        self.assertEqual([port["key"] for port in rows[index]["compatible_ports"]], ["result"])
        self.assertTrue(self.window.request_connection_quick_insert_choose(index))
        edge = next(iter(workspace.edges.values()))
        self.assertEqual(workspace.nodes[edge.source_node_id].type_id, "core.python_script")
        self.assertEqual((edge.source_port_key, edge.target_node_id, edge.target_port_key), ("result", target_id, "condition"))

    def test_qml_connection_quick_insert_empty_wire_release_stays_open_and_searchable(self) -> None:
        workspace = self.window.model.active_workspace
        self.assertFalse(self.window.request_open_connection_quick_insert("missing", "result", 0.0, 0.0, 0.0, 0.0))
        source_id = self.window.scene.add_node_from_type("core.python_script", x=40.0, y=40.0)
        self.app.processEvents()
        QTest.qWait(30)
        canvas = self._graph_canvas_item()
        end_x = max(400.0, float(canvas.property("width")) - 80.0)
        end_y = max(300.0, float(canvas.property("height")) - 80.0)
        canvas.beginPortWireDrag(source_id, "result", "out", 200.0, 80.0, 200.0, 80.0, 0)
        canvas.finishPortWireDrag(source_id, "result", "out", 200.0, 80.0, end_x, end_y, True, 0)
        self.app.processEvents()
        QTest.qWait(30)
        self.assertTrue(self.window.connection_quick_insert_open)
        self.assertEqual(self.window.connection_quick_insert_results, [])
        message = self._find_qml_item("connectionQuickInsertEmptyMessage")
        field = self._find_qml_item("connectionQuickInsertField")
        self.assertIsNotNone(message)
        self.assertIsNotNone(field)
        self.assertEqual(message.property("text"), "No direct type matches. Type to search broader compatible nodes.")
        self.assertTrue(field.property("activeFocus"))
        field.setProperty("text", "no_such_compatible_node")
        self.app.processEvents()
        self.assertEqual(message.property("text"), "No matching compatible nodes.")
        field.setProperty("text", "logger")
        self.app.processEvents()
        self.assertEqual(self.window.connection_quick_insert_results[0]["compatibility_label"], "Checked at runtime")
        summary = self._find_qml_item("connectionQuickInsertPortSummary")
        self.assertIsNotNone(summary)
        self.assertEqual(summary.property("text"), "message — Checked at runtime")
        QTest.keyClick(self._qml_input_widget(), Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertFalse(self.window.connection_quick_insert_open)
        edge = next(iter(workspace.edges.values()))
        self.assertEqual((edge.source_node_id, edge.source_port_key, edge.target_port_key), (source_id, "result", "message"))
        self.assertTrue(self.window.request_open_connection_quick_insert(source_id, "result", 300.0, 60.0, 400.0, 180.0))
        self.app.processEvents()
        QTest.qWait(20)
        QTest.keyClick(self._qml_input_widget(), Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(self.window.connection_quick_insert_open)

    def test_qml_published_workflow_quick_insert_maps_displayed_pin_keys_in_both_directions(self) -> None:
        workspace = self.window.model.active_workspace
        for pin_type, origin_type, origin_port, direction in (
            ("core.subnode_input", "core.constant", "as_text", "out"),
            ("core.subnode_output", "core.logger", "message", "in"),
        ):
            with self.subTest(direction=direction):
                title = f"Published {direction} Workflow"
                source_shell_id = self.window.scene.add_node_from_type("core.subnode", x=220.0, y=120.0)
                self.window.scene.set_node_title(source_shell_id, title)
                self.assertTrue(self.window.request_open_subnode_scope(source_shell_id))
                broad_pin_id = self.window.scene.add_node_from_type(pin_type, x=80.0, y=40.0)
                self.window.scene.set_node_property(broad_pin_id, "label", "Broad")
                typed_pin_id = self.window.scene.add_node_from_type(pin_type, x=80.0, y=140.0)
                self.window.scene.set_node_property(typed_pin_id, "label", "Typed")
                self.window.scene.set_node_property(typed_pin_id, "data_type", "COREX.DataTypes.String")
                self.assertTrue(self.window.request_navigate_scope_parent())
                self.window.scene.focus_node(source_shell_id)
                self.assertTrue(self.window.request_publish_custom_workflow_from_selected())
                self.app.processEvents()

                library_item = next(
                    item for item in self.window.filtered_node_library_items
                    if item.get("workflow_id") == f"wf_shell_{source_shell_id}"
                )
                self.assertEqual({port["key"] for port in library_item["ports"]}, {broad_pin_id, typed_pin_id})
                self.assertTrue(all("node_ref_id" not in port and "port_key" not in port for port in library_item["ports"]))
                origin_id = self.window.scene.add_node_from_type(origin_type, x=40.0, y=40.0)
                self.assertTrue(self.window.request_open_connection_quick_insert(origin_id, origin_port, 600.0, 200.0, 400.0, 180.0))
                self.window.set_connection_quick_insert_query(title)
                rows = self.window.connection_quick_insert_results
                index = next(index for index, row in enumerate(rows) if row["type_id"] == library_item["type_id"])
                self.assertEqual([port["key"] for port in rows[index]["compatible_ports"]], [typed_pin_id])
                before_nodes = set(workspace.nodes)
                before_edges = set(workspace.edges)
                self.assertTrue(self.window.request_connection_quick_insert_choose(index))
                self.app.processEvents()

                inserted_ids = set(workspace.nodes) - before_nodes
                inserted_shell_id = next(node_id for node_id in inserted_ids if workspace.nodes[node_id].type_id == "core.subnode")
                inserted_typed_pin_id = next(
                    node_id for node_id in inserted_ids
                    if workspace.nodes[node_id].parent_node_id == inserted_shell_id
                    and workspace.nodes[node_id].properties.get("label") == "Typed"
                )
                new_edges = set(workspace.edges) - before_edges
                self.assertEqual(len(new_edges), 1)
                edge = workspace.edges[new_edges.pop()]
                expected = (
                    (origin_id, origin_port, inserted_shell_id, inserted_typed_pin_id)
                    if direction == "out"
                    else (inserted_shell_id, inserted_typed_pin_id, origin_id, origin_port)
                )
                self.assertEqual((edge.source_node_id, edge.source_port_key, edge.target_node_id, edge.target_port_key), expected)
                self.assertNotIn(source_shell_id, (edge.source_node_id, edge.target_node_id))
                self.assertNotIn(typed_pin_id, (edge.source_port_key, edge.target_port_key))

    def test_qml_ordinary_published_workflow_port_and_edge_drops_keep_chooser_selection(self) -> None:
        workspace = self.window.model.active_workspace
        for mode in ("port", "edge"):
            with self.subTest(mode=mode):
                source_shell_id = self.window.scene.add_node_from_type("core.subnode", x=220.0, y=120.0)
                self.window.scene.set_node_title(source_shell_id, f"Ordinary {mode} Workflow")
                self.assertTrue(self.window.request_open_subnode_scope(source_shell_id))
                for pin_type, label, y in (
                    ("core.subnode_input", "Input A", 40.0),
                    ("core.subnode_input", "Input B", 140.0),
                    ("core.subnode_output", "Output", 240.0),
                ):
                    pin_id = self.window.scene.add_node_from_type(pin_type, x=80.0, y=y)
                    self.window.scene.set_node_property(pin_id, "label", label)
                    self.window.scene.set_node_property(pin_id, "data_type", "COREX.DataTypes.String")
                self.assertTrue(self.window.request_navigate_scope_parent())
                self.window.scene.focus_node(source_shell_id)
                self.assertTrue(self.window.request_publish_custom_workflow_from_selected())
                self.app.processEvents()
                library_item = next(
                    item for item in self.window.filtered_node_library_items
                    if item.get("workflow_id") == f"wf_shell_{source_shell_id}"
                )
                self.assertTrue(all("node_ref_id" not in port and "port_key" not in port for port in library_item["ports"]))
                source_id = self.window.scene.add_node_from_type("core.constant", x=20.0, y=20.0)
                target_id = self.window.scene.add_node_from_type("core.logger", x=900.0, y=20.0)
                original_edge_id = self.window.scene.add_edge(source_id, "as_text", target_id, "message") if mode == "edge" else ""
                before_nodes = set(workspace.nodes)
                before_edges = set(workspace.edges)

                def choose_input_b(_parent, _title, _label, options, *_args):
                    self.assertEqual(len(options), 2)
                    return next(option for option in options if ".Input B" in option), True

                with patch("PyQt6.QtWidgets.QInputDialog.getItem", side_effect=choose_input_b) as chooser:
                    self.assertTrue(self.window.request_drop_node_from_library(
                        library_item["type_id"], 600.0, 200.0, mode,
                        source_id if mode == "port" else "",
                        "as_text" if mode == "port" else "", original_edge_id,
                    ))
                self.app.processEvents()
                chooser.assert_called_once()
                inserted_ids = set(workspace.nodes) - before_nodes
                inserted_shell_id = next(node_id for node_id in inserted_ids if workspace.nodes[node_id].type_id == "core.subnode")
                inserted_pin_ids = {
                    workspace.nodes[node_id].properties.get("label"): node_id
                    for node_id in inserted_ids
                    if workspace.nodes[node_id].parent_node_id == inserted_shell_id
                }
                new_edge_pairs = {
                    (edge.source_node_id, edge.source_port_key, edge.target_node_id, edge.target_port_key)
                    for edge_id, edge in workspace.edges.items() if edge_id not in before_edges
                }
                expected = {(source_id, "as_text", inserted_shell_id, inserted_pin_ids["Input B"])}
                if mode == "edge":
                    expected.add((inserted_shell_id, inserted_pin_ids["Output"], target_id, "message"))
                    self.assertNotIn(original_edge_id, workspace.edges)
                self.assertEqual(new_edge_pairs, expected)

    def test_qml_custom_workflow_publish_appears_in_library_and_places_independent_snapshots(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        source_shell_id, _source_pin_id = self._create_publishable_subnode(
            shell_title="Reusable Scope",
            output_label="Data A",
        )

        published = self.window.request_publish_custom_workflow_from_selected()
        self.assertTrue(published)
        self.app.processEvents()

        self.window.set_library_query("")
        self.window.set_library_category("Custom Workflows")
        self.window.set_library_direction("")
        self.window.set_library_data_type("")
        self.app.processEvents()

        custom_items = [
            item
            for item in self.window.filtered_node_library_items
            if item.get("category") == "Custom Workflows"
        ]
        self.assertEqual(len(custom_items), 1)
        custom_item = custom_items[0]
        self.assertTrue(str(custom_item["type_id"]).startswith("custom_workflow:"))
        self.assertEqual(custom_item["ports"][0]["kind"], "data")

        def _inserted_root_shell(inserted_ids: set[str]) -> str:
            for node_id in sorted(inserted_ids):
                node = workspace.nodes[node_id]
                if node.type_id != "core.subnode":
                    continue
                if node.parent_node_id in inserted_ids:
                    continue
                return node_id
            return ""

        baseline_node_ids = set(workspace.nodes)
        placed_once = self.window.request_drop_node_from_library(
            custom_item["type_id"],
            560.0,
            180.0,
            "",
            "",
            "",
            "",
        )
        self.assertTrue(placed_once)
        self.app.processEvents()
        after_first_ids = set(workspace.nodes)
        first_inserted_ids = after_first_ids.difference(baseline_node_ids)
        self.assertTrue(first_inserted_ids)
        first_shell_id = _inserted_root_shell(first_inserted_ids)
        self.assertTrue(first_shell_id)

        placed_twice = self.window.request_drop_node_from_library(
            custom_item["type_id"],
            820.0,
            240.0,
            "",
            "",
            "",
            "",
        )
        self.assertTrue(placed_twice)
        self.app.processEvents()
        after_second_ids = set(workspace.nodes)
        second_inserted_ids = after_second_ids.difference(after_first_ids)
        self.assertTrue(second_inserted_ids)
        self.assertTrue(first_inserted_ids.isdisjoint(second_inserted_ids))
        second_shell_id = _inserted_root_shell(second_inserted_ids)
        self.assertTrue(second_shell_id)

        def _output_pin_label(shell_id: str) -> str:
            output_pins = [
                node
                for node in workspace.nodes.values()
                if node.parent_node_id == shell_id and node.type_id == "core.subnode_output"
            ]
            self.assertEqual(len(output_pins), 1)
            return str(output_pins[0].properties.get("label", ""))

        self.assertEqual(_output_pin_label(first_shell_id), "Data A")
        self.assertEqual(_output_pin_label(second_shell_id), "Data A")
        self.assertNotEqual(first_shell_id, source_shell_id)
        self.assertNotEqual(second_shell_id, source_shell_id)

    def test_qml_delete_custom_workflow_removes_item_from_library_and_metadata(self) -> None:
        source_shell_id, _source_pin_id = self._create_publishable_subnode(
            shell_title="Delete Target",
            output_label="Exec Out",
        )
        self.window.scene.focus_node(source_shell_id)
        self.assertTrue(self.window.request_publish_custom_workflow_from_selected())
        self.app.processEvents()

        custom_item = next(
            item
            for item in self.window.filtered_node_library_items
            if item.get("category") == "Custom Workflows"
        )
        workflow_id = str(custom_item.get("workflow_id", ""))
        self.assertTrue(workflow_id)

        deleted = self.window.request_delete_custom_workflow_from_library(workflow_id, "local")
        self.assertTrue(deleted)
        self.app.processEvents()

        self.assertEqual(self.window.model.project.metadata.get("custom_workflows", []), [])
        self.assertFalse(
            [
                item
                for item in self.window.filtered_node_library_items
                if item.get("category") == "Custom Workflows"
            ]
        )

    def test_qml_rename_custom_workflow_updates_library_and_metadata(self) -> None:
        source_shell_id, _source_pin_id = self._create_publishable_subnode(
            shell_title="Rename Target",
            output_label="Exec Out",
        )
        self.window.scene.focus_node(source_shell_id)
        self.assertTrue(self.window.request_publish_custom_workflow_from_selected())
        self.app.processEvents()

        custom_item = next(
            item
            for item in self.window.filtered_node_library_items
            if item.get("category") == "Custom Workflows" and item.get("display_name") == "Rename Target"
        )
        workflow_id = str(custom_item.get("workflow_id", ""))
        self.assertTrue(workflow_id)

        with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("Renamed Workflow", True)):
            renamed = self.window.request_rename_custom_workflow_from_library(workflow_id, "local")
        self.assertTrue(renamed)
        self.app.processEvents()

        definitions = self.window.model.project.metadata.get("custom_workflows", [])
        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0]["name"], "Renamed Workflow")
        self.assertEqual(definitions[0]["revision"], 1)

        updated_item = next(
            item
            for item in self.window.filtered_node_library_items
            if item.get("category") == "Custom Workflows" and item.get("workflow_id") == workflow_id
        )
        self.assertEqual(updated_item.get("display_name"), "Renamed Workflow")

    def test_qml_set_custom_workflow_scope_moves_local_item_to_global(self) -> None:
        source_shell_id, _source_pin_id = self._create_publishable_subnode(
            shell_title="Scope Switch",
            output_label="Exec Out",
        )
        self.window.scene.focus_node(source_shell_id)
        self.assertTrue(self.window.request_publish_custom_workflow_from_selected())
        self.app.processEvents()

        custom_item = next(
            item
            for item in self.window.filtered_node_library_items
            if item.get("category") == "Custom Workflows" and item.get("display_name") == "Scope Switch"
        )
        workflow_id = str(custom_item.get("workflow_id", ""))
        self.assertTrue(workflow_id)
        self.assertEqual(custom_item.get("workflow_scope"), "local")

        switched = self.window.request_set_custom_workflow_scope(workflow_id, "global")
        self.assertTrue(switched)
        self.app.processEvents()
        self.assertEqual(self.window.model.project.metadata.get("custom_workflows", []), [])

        updated_item = next(
            item
            for item in self.window.filtered_node_library_items
            if item.get("category") == "Custom Workflows" and item.get("workflow_id") == workflow_id
        )
        self.assertEqual(updated_item.get("workflow_scope"), "global")

    def test_qml_custom_workflow_export_import_round_trip_preserves_snapshot_fidelity(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        source_shell_id, _source_pin_id = self._create_publishable_subnode(
            shell_title="Exportable Scope",
            output_label="Exec Export",
        )
        self.window.scene.focus_node(source_shell_id)
        self.assertTrue(self.window.request_publish_custom_workflow_from_selected())
        self.app.processEvents()

        definitions = self.window.model.project.metadata.get("custom_workflows", [])
        self.assertEqual(len(definitions), 1)
        original_definition = copy.deepcopy(definitions[0])

        with tempfile.TemporaryDirectory() as temp_dir:
            export_target = Path(temp_dir) / "exported_custom_workflow"
            self.window.workspace_package_io_controller.prompt_custom_workflow_export_definition = (  # type: ignore[method-assign]
                lambda definitions: definitions[0]
            )
            with (
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(export_target), "Custom Workflow (*.cxwf)"),
                ),
                patch("PyQt6.QtWidgets.QMessageBox.information"),
                patch("PyQt6.QtWidgets.QMessageBox.warning"),
            ):
                self.window.workspace_package_io_controller.export_custom_workflow()
            self.app.processEvents()

            export_path = export_target.with_suffix(".cxwf")
            self.assertTrue(export_path.exists())
            self.assertEqual(import_custom_workflow_file(export_path), original_definition)

            self.window.model.project.metadata["custom_workflows"] = []
            self.window.project_meta_changed.emit()
            self.window.node_library_changed.emit()
            self.app.processEvents()
            self.assertFalse(
                [
                    item
                    for item in self.window.filtered_node_library_items
                    if item.get("category") == "Custom Workflows"
                ]
            )

            with (
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getOpenFileName",
                    return_value=(str(export_path), "Custom Workflow (*.cxwf)"),
                ),
                patch("PyQt6.QtWidgets.QMessageBox.information"),
                patch("PyQt6.QtWidgets.QMessageBox.warning"),
            ):
                self.window.workspace_package_io_controller.import_custom_workflow()
            self.app.processEvents()

        imported_definitions = self.window.model.project.metadata.get("custom_workflows", [])
        self.assertEqual(imported_definitions, [original_definition])

        custom_item = next(
            item
            for item in self.window.filtered_node_library_items
            if item.get("category") == "Custom Workflows"
        )
        existing_ids = set(workspace.nodes)
        self.assertTrue(
            self.window.request_drop_node_from_library(
                custom_item["type_id"],
                780.0,
                260.0,
                "",
                "",
                "",
                "",
            )
        )
        self.app.processEvents()

        inserted_ids = set(workspace.nodes).difference(existing_ids)
        inserted_shell_id = next(
            node_id
            for node_id in sorted(inserted_ids)
            if workspace.nodes[node_id].type_id == "core.subnode"
            and workspace.nodes[node_id].parent_node_id not in inserted_ids
        )
        inserted_output = next(
            node
            for node in workspace.nodes.values()
            if node.parent_node_id == inserted_shell_id and node.type_id == "core.subnode_output"
        )
        self.assertEqual(str(inserted_output.properties.get("label", "")), "Exec Export")

    def test_qml_install_project_emits_library_refresh_for_restored_custom_workflows(self) -> None:
        source_shell_id, _source_pin_id = self._create_publishable_subnode(
            shell_title="Restored Custom Workflow",
            output_label="Data A",
        )
        self.window.scene.focus_node(source_shell_id)
        self.assertTrue(self.window.request_publish_custom_workflow_from_selected())
        self.app.processEvents()

        restored_project = self.window.serializer.from_document(
            self.window.serializer.to_document(self.window.model.project)
        )
        library_changed = {"count": 0}

        def _mark_library_changed() -> None:
            library_changed["count"] += 1

        self.window.node_library_changed.connect(_mark_library_changed)
        self.window.project_session_controller._install_project(restored_project, project_path="restored.cxproj")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(
            self.window.workspace_manager.active_workspace_id()
        )
        self.app.processEvents()

        self.assertGreaterEqual(library_changed["count"], 1)

        custom_category_rows = [
            row
            for row in self.window.grouped_node_library_items
            if row.get("kind") == "category" and row.get("category") == "Custom Workflows"
        ]
        self.assertTrue(custom_category_rows)

    def test_nested_category_qml_library_categories_start_collapsed_on_project_install(self) -> None:
        library_pane = self._library_pane_item()
        self.app.processEvents()

        def _collapsed_map() -> dict[str, bool]:
            return {
                key: bool(value)
                for key, value in _qml_variant_map(library_pane.property("collapsedCategories")).items()
            }

        for category_key_value in {
            row["category_key"] for row in self.window.grouped_node_library_items if row.get("kind") == "category"
        }:
            self.assertTrue(_collapsed_map().get(category_key_value, False))

        library_pane.setProperty(
            "collapsedCategories",
            {
                category_key(("Flow Control",)): False,
                category_key(("Custom Workflows",)): False,
            },
        )
        self.app.processEvents()

        source_shell_id, _source_pin_id = self._create_publishable_subnode(
            shell_title="Collapsed Restore Workflow",
            output_label="Data A",
        )
        self.window.scene.focus_node(source_shell_id)
        self.assertTrue(self.window.request_publish_custom_workflow_from_selected())
        self.app.processEvents()

        restored_project = self.window.serializer.from_document(
            self.window.serializer.to_document(self.window.model.project)
        )
        self.window.project_session_controller._install_project(restored_project, project_path="collapsed-reset.cxproj")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(
            self.window.workspace_manager.active_workspace_id()
        )
        self.app.processEvents()

        collapsed_categories = _collapsed_map()
        restored_category_keys = {
            row["category_key"] for row in self.window.grouped_node_library_items if row.get("kind") == "category"
        }
        self.assertIn(category_key(("Custom Workflows",)), restored_category_keys)
        for category_key_value in restored_category_keys:
            self.assertTrue(bool(collapsed_categories.get(category_key_value, False)))

    def test_qml_custom_workflow_update_changes_future_placements_only(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        source_shell_id, source_pin_id = self._create_publishable_subnode(
            shell_title="Updatable Scope",
            output_label="Data A",
        )

        self.assertTrue(self.window.request_publish_custom_workflow_from_selected())
        self.app.processEvents()
        custom_item = next(
            item
            for item in self.window.filtered_node_library_items
            if item.get("category") == "Custom Workflows"
        )

        target_a = self.window.scene.add_node_from_type("core.logger", x=940.0, y=40.0)
        baseline_node_ids = set(workspace.nodes)
        placed_first = self.window.request_drop_node_from_library(
            custom_item["type_id"],
            520.0,
            120.0,
            "port",
            target_a,
            "message",
            "",
        )
        self.assertTrue(placed_first)
        self.app.processEvents()
        after_first_ids = set(workspace.nodes)
        first_inserted_ids = after_first_ids.difference(baseline_node_ids)
        first_shell_id = next(
            node_id
            for node_id in sorted(first_inserted_ids)
            if workspace.nodes[node_id].type_id == "core.subnode" and workspace.nodes[node_id].parent_node_id not in first_inserted_ids
        )

        self.assertTrue(self.window.request_open_subnode_scope(source_shell_id))
        self.window.scene.set_node_property(source_pin_id, "label", "Data B")
        self.assertTrue(self.window.request_navigate_scope_parent())
        self.window.scene.focus_node(source_shell_id)
        self.app.processEvents()

        self.assertTrue(self.window.request_publish_custom_workflow_from_selected())
        self.app.processEvents()

        metadata_definitions = self.window.model.project.metadata.get("custom_workflows", [])
        self.assertEqual(len(metadata_definitions), 1)
        self.assertEqual(metadata_definitions[0]["revision"], 2)

        target_b = self.window.scene.add_node_from_type("core.logger", x=980.0, y=220.0)
        placed_second = self.window.request_drop_node_from_library(
            custom_item["type_id"],
            760.0,
            260.0,
            "port",
            target_b,
            "message",
            "",
        )
        self.assertTrue(placed_second)
        self.app.processEvents()
        after_second_ids = set(workspace.nodes)
        second_inserted_ids = after_second_ids.difference(after_first_ids)
        second_shell_id = next(
            node_id
            for node_id in sorted(second_inserted_ids)
            if workspace.nodes[node_id].type_id == "core.subnode" and workspace.nodes[node_id].parent_node_id not in second_inserted_ids
        )

        def _output_pin_label(shell_id: str) -> str:
            output_pin = next(
                node
                for node in workspace.nodes.values()
                if node.parent_node_id == shell_id and node.type_id == "core.subnode_output"
            )
            return str(output_pin.properties.get("label", ""))

        self.assertEqual(_output_pin_label(first_shell_id), "Data A")
        self.assertEqual(_output_pin_label(second_shell_id), "Data B")

        first_auto_edge_exists = any(
            edge.source_node_id == first_shell_id
            and edge.target_node_id == target_a
            and edge.target_port_key == "message"
            for edge in workspace.edges.values()
        )
        second_auto_edge_exists = any(
            edge.source_node_id == second_shell_id
            and edge.target_node_id == target_b
            and edge.target_port_key == "message"
            for edge in workspace.edges.values()
        )
        self.assertTrue(first_auto_edge_exists)
        self.assertTrue(second_auto_edge_exists)

    def test_qml_custom_workflow_publish_from_scope_and_reinsert_in_same_scope_preserves_parent_on_reload(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        source_shell_id, _source_pin_id = self._create_publishable_subnode(
            shell_title="Subnode1",
            output_label="Data A",
        )

        self.assertTrue(self.window.request_open_subnode_scope(source_shell_id))
        self.app.processEvents()
        self.assertEqual(self.window.scene.active_scope_path, [source_shell_id])
        self.assertTrue(self.window.request_publish_custom_workflow_from_scope())
        self.app.processEvents()

        custom_item = next(
            item
            for item in self.window.filtered_node_library_items
            if item.get("category") == "Custom Workflows" and item.get("display_name") == "Subnode1"
        )
        existing_ids = set(workspace.nodes)
        self.assertTrue(
            self.window.request_drop_node_from_library(
                custom_item["type_id"],
                620.0,
                300.0,
                "",
                "",
                "",
                "",
            )
        )
        self.app.processEvents()

        inserted_ids = set(workspace.nodes).difference(existing_ids)
        inserted_shell_id = next(
            node_id
            for node_id in sorted(inserted_ids)
            if workspace.nodes[node_id].type_id == "core.subnode" and node_id != source_shell_id
        )
        self.assertEqual(workspace.nodes[inserted_shell_id].parent_node_id, source_shell_id)
        self.assertNotEqual(workspace.nodes[inserted_shell_id].parent_node_id, inserted_shell_id)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scope_reinsert_custom_workflow.cxproj"
            self.window.serializer.save(str(path), self.window.model.project)
            loaded = self.window.serializer.load(str(path))

        loaded_workspace = loaded.workspaces[workspace_id]
        self.assertIn(inserted_shell_id, loaded_workspace.nodes)
        self.assertEqual(loaded_workspace.nodes[inserted_shell_id].parent_node_id, source_shell_id)

    def test_qml_nested_custom_workflow_drop_opens_without_crash_and_survives_save_load(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        outer_id, _inner_id = self._create_nested_outer_inner_subnodes()

        self.window.scene.focus_node(outer_id)
        self.assertTrue(self.window.request_publish_custom_workflow_from_selected())
        self.app.processEvents()

        custom_item = next(
            item
            for item in self.window.filtered_node_library_items
            if item.get("category") == "Custom Workflows" and item.get("display_name") == "Outer"
        )
        existing_ids = set(workspace.nodes)
        self.assertTrue(
            self.window.request_drop_node_from_library(
                custom_item["type_id"],
                880.0,
                360.0,
                "",
                "",
                "",
                "",
            )
        )
        self.app.processEvents()

        inserted_ids = set(workspace.nodes).difference(existing_ids)
        dropped_outer_id = next(
            node_id
            for node_id in sorted(inserted_ids)
            if workspace.nodes[node_id].type_id == "core.subnode"
            and workspace.nodes[node_id].parent_node_id not in inserted_ids
        )
        self.assertTrue(self.window.request_open_subnode_scope(dropped_outer_id))
        self.app.processEvents()
        self.assertEqual(self.window.scene.active_scope_path, [dropped_outer_id])

        dropped_inner_id = next(
            node_id
            for node_id in inserted_ids
            if workspace.nodes[node_id].type_id == "core.subnode"
            and workspace.nodes[node_id].parent_node_id == dropped_outer_id
        )
        self.assertTrue(self.window.request_open_subnode_scope(dropped_inner_id))
        self.app.processEvents()
        self.assertEqual(self.window.scene.active_scope_path, [dropped_outer_id, dropped_inner_id])

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested_custom_workflow.cxproj"
            self.window.serializer.save(str(path), self.window.model.project)
            loaded = self.window.serializer.load(str(path))

        loaded_workspace = loaded.workspaces[workspace_id]
        self.assertIn(dropped_outer_id, loaded_workspace.nodes)
        self.assertIn(dropped_inner_id, loaded_workspace.nodes)
        self.assertEqual(loaded_workspace.nodes[dropped_inner_id].parent_node_id, dropped_outer_id)

        loaded_outer_children = {
            node.node_id
            for node in loaded_workspace.nodes.values()
            if node.parent_node_id == dropped_outer_id
        }
        self.assertIn(dropped_inner_id, loaded_outer_children)

        loaded_edge_tuples = {
            (edge.source_node_id, edge.source_port_key, edge.target_node_id, edge.target_port_key)
            for edge in loaded_workspace.edges.values()
        }
        bridging_edges = [
            edge
            for edge in loaded_edge_tuples
            if edge[0] == dropped_inner_id or edge[2] == dropped_inner_id
        ]
        self.assertTrue(bridging_edges)
