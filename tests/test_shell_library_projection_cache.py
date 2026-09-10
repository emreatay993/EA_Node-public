from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import QObject, pyqtSignal

from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.ui.shell.presenters import inspector_presenter as inspector_module
from ea_node_editor.ui.shell.presenters import library_presenter as library_module
from ea_node_editor.ui.shell.presenters.inspector_presenter import ShellInspectorPresenter
from ea_node_editor.ui.shell.presenters.library_presenter import ShellLibraryPresenter
from ea_node_editor.ui.shell.state import ShellLibraryFilterState


class _WorkflowLibraryControllerStub:
    def __init__(self) -> None:
        self.calls = 0
        self.items: list[dict[str, object]] = []

    def custom_workflow_library_items(self) -> list[dict[str, object]]:
        self.calls += 1
        return list(self.items)


class _LibraryHostStub(QObject):
    node_library_changed = pyqtSignal()
    library_pane_reset_requested = pyqtSignal()
    graph_search_changed = pyqtSignal()
    connection_quick_insert_changed = pyqtSignal()
    graph_hint_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.registry = build_builtin_registry()
        self.workflow_library_controller = _WorkflowLibraryControllerStub()
        self.library_filter_state = ShellLibraryFilterState()
        self.workspace_ui_state = SimpleNamespace(passive_node_library_display_mode="text")


class _InspectorHostStub(QObject):
    selected_node_changed = pyqtSignal()
    workspace_state_changed = pyqtSignal()
    node_execution_state_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.registry = build_builtin_registry()
        self.workspace = WorkspaceData(workspace_id="workspace-1", name="Workspace 1")
        self.model = SimpleNamespace(
            project=SimpleNamespace(workspaces={self.workspace.workspace_id: self.workspace})
        )
        self._SUBNODE_PIN_TYPE_IDS = {"core.subnode_input", "core.subnode_output"}


class ShellLibraryProjectionCacheTests(unittest.TestCase):
    def test_display_projection_reuses_tree_without_eager_grouped_rows(self) -> None:
        presenter = ShellLibraryPresenter(_LibraryHostStub())

        with (
            patch.object(
                library_module,
                "build_library_category_tree",
                wraps=library_module.build_library_category_tree,
            ) as build_category_tree,
            patch.object(
                library_module,
                "project_grouped_library_items",
                wraps=library_module.project_grouped_library_items,
            ) as project_grouped_items,
        ):
            self.assertTrue(presenter.display_node_library_items)
            self.assertEqual(build_category_tree.call_count, 1)
            self.assertEqual(project_grouped_items.call_count, 0)

            self.assertTrue(presenter.grouped_node_library_items)
            self.assertEqual(build_category_tree.call_count, 1)
            self.assertEqual(project_grouped_items.call_count, 1)

    def test_reuses_projection_results_across_property_reads_and_filter_changes(self) -> None:
        host = _LibraryHostStub()
        presenter = ShellLibraryPresenter(host)

        with (
            patch.object(
                library_module,
                "build_registry_library_items",
                wraps=library_module.build_registry_library_items,
            ) as build_registry_items,
            patch.object(
                library_module,
                "build_combined_library_items",
                wraps=library_module.build_combined_library_items,
            ) as build_combined_items,
            patch.object(
                library_module,
                "build_filtered_library_items",
                wraps=library_module.build_filtered_library_items,
            ) as build_filtered_items,
            patch.object(
                library_module,
                "build_library_category_tree",
                wraps=library_module.build_library_category_tree,
            ) as build_category_tree,
            patch.object(
                library_module,
                "project_grouped_library_items",
                wraps=library_module.project_grouped_library_items,
            ) as project_grouped_items,
            patch.object(
                library_module,
                "project_display_library_items",
                wraps=library_module.project_display_library_items,
            ) as project_display_items,
            patch.object(
                library_module,
                "build_library_category_options",
                wraps=library_module.build_library_category_options,
            ) as build_category_options,
            patch.object(
                library_module,
                "build_library_data_type_options",
                wraps=library_module.build_library_data_type_options,
            ) as build_data_type_options,
        ):
            for _ in range(3):
                self.assertTrue(presenter.filtered_node_library_items)
                self.assertTrue(presenter.grouped_node_library_items)
                self.assertTrue(presenter.display_node_library_items)
                self.assertTrue(presenter.library_category_options)
                self.assertTrue(presenter.library_data_type_options)

            self.assertEqual(build_registry_items.call_count, 1)
            self.assertEqual(build_combined_items.call_count, 1)
            self.assertEqual(build_filtered_items.call_count, 1)
            self.assertEqual(build_category_tree.call_count, 1)
            self.assertEqual(project_grouped_items.call_count, 1)
            self.assertEqual(project_display_items.call_count, 1)
            self.assertEqual(build_category_options.call_count, 1)
            self.assertEqual(build_data_type_options.call_count, 1)
            self.assertEqual(host.workflow_library_controller.calls, 1)

            presenter.set_library_query("logger")
            self.assertTrue(presenter.filtered_node_library_items)
            self.assertTrue(presenter.grouped_node_library_items)
            self.assertTrue(presenter.display_node_library_items)
            self.assertTrue(presenter.library_category_options)
            self.assertTrue(presenter.library_data_type_options)

            self.assertEqual(build_registry_items.call_count, 1)
            self.assertEqual(build_combined_items.call_count, 1)
            self.assertEqual(build_filtered_items.call_count, 2)
            self.assertEqual(build_category_tree.call_count, 2)
            self.assertEqual(project_grouped_items.call_count, 2)
            self.assertEqual(project_display_items.call_count, 2)
            self.assertEqual(build_category_options.call_count, 1)
            self.assertEqual(build_data_type_options.call_count, 1)
            self.assertEqual(host.workflow_library_controller.calls, 1)

    def test_invalidates_workflow_and_registry_projections_on_existing_change_signal(self) -> None:
        host = _LibraryHostStub()
        presenter = ShellLibraryPresenter(host)

        with patch.object(
            library_module,
            "build_registry_library_items",
            wraps=library_module.build_registry_library_items,
        ) as build_registry_items:
            initial_count = len(presenter.filtered_node_library_items)
            host.workflow_library_controller.items = [
                {
                    "type_id": "custom_workflow:workflow-1",
                    "display_name": "Workflow 1",
                    "category": "Custom Workflows",
                    "ports": [],
                    "workflow_id": "workflow-1",
                    "revision": 2,
                    "library_source": "custom_workflow",
                }
            ]
            host.node_library_changed.emit()

            refreshed_items = presenter.filtered_node_library_items
            self.assertEqual(len(refreshed_items), initial_count + 1)
            self.assertEqual(host.workflow_library_controller.calls, 2)
            self.assertEqual(build_registry_items.call_count, 1)

            host.registry = build_builtin_registry()
            host.node_library_changed.emit()
            self.assertEqual(len(presenter.filtered_node_library_items), initial_count + 1)
            self.assertEqual(build_registry_items.call_count, 2)


class ShellInspectorProjectionCacheTests(unittest.TestCase):
    def test_pin_options_follow_registry_identity_and_workspace_revision(self) -> None:
        host = _InspectorHostStub()
        presenter = ShellInspectorPresenter(host)

        with patch.object(
            inspector_module,
            "build_pin_data_type_options",
            wraps=inspector_module.build_pin_data_type_options,
        ) as build_pin_options:
            initial = presenter.pin_data_type_options
            self.assertEqual(presenter.pin_data_type_options, initial)
            self.assertEqual(build_pin_options.call_count, 1)

            host.workspace.bump_mutation_revision()
            self.assertEqual(presenter.pin_data_type_options, initial)
            self.assertEqual(build_pin_options.call_count, 2)

            host.registry = build_builtin_registry()
            self.assertEqual(presenter.pin_data_type_options, initial)
            self.assertEqual(build_pin_options.call_count, 3)


if __name__ == "__main__":
    unittest.main()
