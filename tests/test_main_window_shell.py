from __future__ import annotations

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QObject

from ea_node_editor.addons.catalog import TABULAR_DATA_ADDON_ID
from ea_node_editor.ui.shell.composition import AddonManagerBridge
from ea_node_editor.ui.shell.graph_action_contracts import GraphActionId
from ea_node_editor.ui.shell.presenters.addon_manager_presenter import AddOnManagerPresenter
from ea_node_editor.ui_qml.graph_action_bridge import GraphActionBridge
from ea_node_editor.ui_qml.content_fullscreen_bridge import ContentFullscreenBridge
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.shell_context_bootstrap import ShellContextBundle
from ea_node_editor.ui_qml.shell_inspector_bridge import ShellInspectorBridge
from ea_node_editor.ui_qml.shell_library_bridge import ShellLibraryBridge
from ea_node_editor.ui_qml.shell_workspace_bridge import ShellWorkspaceBridge
from ea_node_editor.ui_qml.viewer_host_service import ViewerHostService
from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge
from tests.main_window_shell.base import SharedMainWindowShellTestBase
from tests.main_window_shell.bridge_contracts import (
    _REPO_ROOT,
)

_SHELL_TEST_MODULES = (
    "tests.main_window_shell.shell_basics_and_search",
    "tests.main_window_shell.drop_connect_and_workflow_io",
    "tests.main_window_shell.edit_clipboard_history",
    "tests.main_window_shell.mutation_ui_effects",
    "tests.main_window_shell.passive_style_context_menus",
    "tests.main_window_shell.passive_property_editors",
    "tests.main_window_shell.view_library_inspector",
    "tests.main_window_shell.shell_runtime_contracts",
)

QML_GRAPH_ACTION_DISPATCH_SLOTS = {
    "request_navigate_scope_parent",
    "request_navigate_scope_root",
    "request_align_selection_left",
    "request_align_selection_right",
    "request_align_selection_top",
    "request_align_selection_bottom",
    "request_distribute_selection_horizontally",
    "request_distribute_selection_vertically",
    "request_straighten_selection_connections",
    "request_connect_selected_nodes",
    "request_duplicate_selected_nodes",
    "request_wrap_selected_nodes_in_group_backdrop",
    "request_group_selected_nodes",
    "request_ungroup_selected_nodes",
    "request_copy_selected_nodes",
    "request_cut_selected_nodes",
    "request_paste_selected_nodes",
    "request_delete_selected_graph_items",
}

pytestmark = pytest.mark.xdist_group("p03_main_window_shell")


def _load_shell_test_modules() -> None:
    for module_name in _SHELL_TEST_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name:
                raise
            continue
        exported_names = getattr(module, "__all__", None)
        if exported_names is None:
            exported_names = [name for name in module.__dict__ if not name.startswith("_")]
        globals().update({name: getattr(module, name) for name in exported_names})


_load_shell_test_modules()


def _assert_text_snippets(
    test_case: unittest.TestCase,
    *,
    label: str,
    text: str,
    absent_snippets: tuple[str, ...] = (),
    present_snippets: tuple[str, ...] = (),
) -> None:
    for snippet in absent_snippets:
        with test_case.subTest(path=label, snippet=snippet, expectation="absent"):
            test_case.assertNotIn(snippet, text)

    for snippet in present_snippets:
        with test_case.subTest(path=label, snippet=snippet, expectation="present"):
            test_case.assertIn(snippet, text)


class MainWindowShellContextBootstrapTests(SharedMainWindowShellTestBase):
    def test_addon_hot_apply_failure_keeps_active_shell_consumers_and_preferences(
        self,
    ) -> None:
        presenter = AddOnManagerPresenter()
        presenter.bind(shell_window=self.window)
        presenter._records = (
            SimpleNamespace(
                addon_id=TABULAR_DATA_ADDON_ID,
                availability=SimpleNamespace(is_available=True),
            ),
        )

        active_registry = self.window.registry
        active_graph_registry = self.window.graph_interactions._registry
        active_serializer = self.window.serializer
        active_session_serializer = self.window.session_store._serializer
        active_scene_registry = self.window.scene._registry
        active_document = self.window.app_preferences_controller.document()
        persisted_document = self.window.app_preferences_controller._store.load_document()
        with patch.object(
            self.window.registry_replacement_coordinator,
            "apply_addon_enabled_state",
            side_effect=RuntimeError("registry replacement failed"),
        ):
            self.assertFalse(
                presenter.set_addon_enabled(TABULAR_DATA_ADDON_ID, False)
            )

        self.assertIs(self.window.registry, active_registry)
        self.assertIs(self.window.graph_interactions._registry, active_graph_registry)
        self.assertIs(self.window.serializer, active_serializer)
        self.assertIs(
            self.window.session_store._serializer,
            active_session_serializer,
        )
        self.assertIs(self.window.scene._registry, active_scene_registry)
        self.assertEqual(
            self.window.app_preferences_controller.document(),
            active_document,
        )
        self.assertEqual(
            self.window.app_preferences_controller._store.load_document(),
            persisted_document,
        )

    def test_qml_context_removes_raw_canvas_globals_and_registers_split_canvas_bridges(self) -> None:
        self._reopen_shared_window()
        context = self.window.quick_widget.rootContext()
        services = self.window.shell_services

        expected_context_names = (
            "shellContext",
            "scriptEditorBridge",
            "scriptHighlighterBridge",
            "themeBridge",
            "graphThemeBridge",
            "uiIcons",
            "statusEngine",
            "statusJobs",
            "statusMetrics",
            "statusNotifications",
            "shellLibraryBridge",
            "shellWorkspaceBridge",
            "shellInspectorBridge",
            "addonManagerBridge",
            "graphActionBridge",
            "graphCanvasStateBridge",
            "graphCanvasCommandBridge",
            "graphCanvasViewBridge",
            "contentFullscreenBridge",
            "viewerSessionBridge",
            "viewerHostService",
        )
        for name in expected_context_names:
            with self.subTest(name=name):
                self.assertIsNotNone(context.contextProperty(name))

        for name in (
            "mainWindow",
            "sceneBridge",
            "viewBridge",
            "consoleBridge",
            "workspaceTabsBridge",
        ):
            with self.subTest(name=name, expectation="removed"):
                self.assertIsNone(context.contextProperty(name))

        shell_library_bridge = context.contextProperty("shellLibraryBridge")
        shell_context = context.contextProperty("shellContext")
        self.assertIsInstance(shell_context, ShellContextBundle)
        self.assertIs(shell_context, services.qml_context.qml_context_bundle)
        self.assertIsInstance(shell_library_bridge, ShellLibraryBridge)
        self.assertIsNone(shell_library_bridge.shell_window)
        self.assertIs(shell_library_bridge.library_source, self.window.shell_library_presenter)

        shell_workspace_bridge = context.contextProperty("shellWorkspaceBridge")
        self.assertIsInstance(shell_workspace_bridge, ShellWorkspaceBridge)
        self.assertIs(shell_workspace_bridge.shell_window, self.window)
        self.assertIs(shell_workspace_bridge.workspace_source, self.window.shell_workspace_presenter)
        self.assertIs(shell_workspace_bridge.scene_bridge, self.window.scene)
        self.assertIs(shell_workspace_bridge.view_bridge, self.window.view)
        self.assertIs(shell_workspace_bridge.console_bridge, self.window.console_panel)
        self.assertIs(shell_workspace_bridge.workspace_tabs_bridge, self.window.workspace_tabs)

        shell_inspector_bridge = context.contextProperty("shellInspectorBridge")
        self.assertIsInstance(shell_inspector_bridge, ShellInspectorBridge)
        self.assertIsNone(shell_inspector_bridge.shell_window)
        self.assertIs(shell_inspector_bridge.inspector_source, self.window.shell_inspector_presenter)
        self.assertIs(shell_inspector_bridge.scene_bridge, self.window.scene)

        addon_manager_bridge = context.contextProperty("addonManagerBridge")
        self.assertIsInstance(addon_manager_bridge, AddonManagerBridge)
        self.assertIs(addon_manager_bridge.parent(), self.window)
        self.assertFalse(addon_manager_bridge.open)
        self.assertEqual(addon_manager_bridge.focusAddonId, "")
        self.assertEqual(addon_manager_bridge.requestSerial, self.window.addon_manager_request_serial)

        graph_action_bridge = context.contextProperty("graphActionBridge")
        self.assertIsInstance(graph_action_bridge, GraphActionBridge)
        self.assertIs(graph_action_bridge.parent(), self.window)
        self.assertIs(graph_action_bridge.controller, self.window.graph_action_controller)
        self.assertNotIn("legacyRouteNames", graph_action_bridge.action_metadata("remove_edge"))
        self.assertEqual(graph_action_bridge.action_metadata("request_remove_edge"), {})

        graph_canvas_state_bridge = context.contextProperty("graphCanvasStateBridge")
        self.assertIsInstance(graph_canvas_state_bridge, GraphCanvasStateBridge)
        self.assertIs(graph_canvas_state_bridge.parent(), self.window)
        self.assertIs(graph_canvas_state_bridge._session_state, self.window.search_scope_state)
        self.assertIs(graph_canvas_state_bridge.graphics_source, self.window.shell_workspace_presenter)
        self.assertIs(graph_canvas_state_bridge.execution_source, self.window)
        self.assertIs(graph_canvas_state_bridge.scene_bridge, self.window.scene)
        self.assertIs(graph_canvas_state_bridge.view_bridge, self.window.view)

        graph_canvas_command_bridge = context.contextProperty("graphCanvasCommandBridge")
        self.assertIsInstance(graph_canvas_command_bridge, GraphCanvasCommandBridge)
        self.assertIs(graph_canvas_command_bridge.parent(), self.window)
        self.assertIs(graph_canvas_command_bridge._run_controller, self.window.run_controller)
        self.assertIs(
            graph_canvas_command_bridge.graphics_source,
            self.window.shell_workspace_presenter,
        )
        self.assertIs(graph_canvas_command_bridge.host_source, self.window.graph_canvas_host_presenter)
        self.assertIs(graph_canvas_command_bridge.scene_bridge, self.window.scene)
        self.assertIs(graph_canvas_command_bridge.view_bridge, self.window.view)
        self.assertIs(
            self.window.scene._graphics_preferences_source,
            self.window.shell_workspace_presenter,
        )

        graph_canvas_view_bridge = context.contextProperty("graphCanvasViewBridge")
        self.assertIs(graph_canvas_view_bridge, self.window.view)
        self.assertIs(graph_canvas_view_bridge.parent(), self.window)

        content_fullscreen_bridge = context.contextProperty("contentFullscreenBridge")
        self.assertIsInstance(content_fullscreen_bridge, ContentFullscreenBridge)
        self.assertIs(content_fullscreen_bridge.parent(), self.window)
        self.assertIs(content_fullscreen_bridge, services.runtime.content_fullscreen_bridge)
        self.assertFalse(content_fullscreen_bridge.open)

        viewer_session_bridge = context.contextProperty("viewerSessionBridge")
        self.assertIsInstance(viewer_session_bridge, ViewerSessionBridge)
        self.assertIs(viewer_session_bridge.parent(), self.window)
        self.assertEqual(
            viewer_session_bridge.active_workspace_id,
            self.window.workspace_manager.active_workspace_id(),
        )

        viewer_host_service = context.contextProperty("viewerHostService")
        self.assertIsInstance(viewer_host_service, ViewerHostService)
        self.assertIs(viewer_host_service.parent(), self.window)
        self.assertIs(viewer_host_service.overlay_manager, self.window.embedded_viewer_overlay_manager)

        context_bindings = dict(services.qml_context.qml_context_property_bindings)
        self.assertIs(context_bindings["shellContext"], shell_context)
        self.assertIs(context_bindings["shellLibraryBridge"], shell_library_bridge)
        self.assertIs(context_bindings["shellWorkspaceBridge"], shell_workspace_bridge)
        self.assertIs(context_bindings["shellInspectorBridge"], shell_inspector_bridge)
        self.assertIs(context_bindings["addonManagerBridge"], addon_manager_bridge)
        self.assertIs(context_bindings["graphActionBridge"], graph_action_bridge)
        self.assertIs(context_bindings["graphCanvasStateBridge"], graph_canvas_state_bridge)
        self.assertIs(context_bindings["graphCanvasCommandBridge"], graph_canvas_command_bridge)
        self.assertIs(context_bindings["graphCanvasViewBridge"], graph_canvas_view_bridge)
        self.assertIs(context_bindings["contentFullscreenBridge"], content_fullscreen_bridge)
        self.assertIs(context_bindings["viewerSessionBridge"], viewer_session_bridge)
        self.assertIs(context_bindings["viewerHostService"], viewer_host_service)

        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        if root_object is None:
            self.fail("Expected the shell root object to be available.")

        addon_loader = root_object.findChild(QObject, "addonManagerPaneLoader")
        addon_surface = root_object.findChild(QObject, "addonManagerPane")
        addon_surface_bridge = root_object.findChild(QObject, "shellAddOnManagerBridge")
        self.assertIsNotNone(addon_loader)
        self.assertIsNone(addon_surface)
        self.assertIsNone(addon_surface_bridge)

    def test_addon_manager_bridge_tracks_shell_open_request_contract(self) -> None:
        context = self.window.quick_widget.rootContext()
        bridge = context.contextProperty("addonManagerBridge")
        initial_serial = int(bridge.requestSerial)

        self.assertIsInstance(bridge, AddonManagerBridge)
        self.assertEqual(
            bridge.request,
            {
                "open": False,
                "focus_addon_id": "",
                "request_serial": initial_serial,
            },
        )

        self.window.request_open_addon_manager(TABULAR_DATA_ADDON_ID)
        self.app.processEvents()

        self.assertTrue(bridge.open)
        self.assertEqual(bridge.focusAddonId, TABULAR_DATA_ADDON_ID)
        self.assertEqual(bridge.requestSerial, initial_serial + 1)
        self.assertEqual(
            bridge.request,
            {
                "open": True,
                "focus_addon_id": TABULAR_DATA_ADDON_ID,
                "request_serial": initial_serial + 1,
            },
        )

        bridge.requestOpen(TABULAR_DATA_ADDON_ID)
        self.app.processEvents()

        self.assertTrue(bridge.open)
        self.assertEqual(bridge.focusAddonId, TABULAR_DATA_ADDON_ID)
        self.assertEqual(bridge.requestSerial, initial_serial + 2)

        bridge.requestClose()
        self.app.processEvents()

        self.assertFalse(bridge.open)
        self.assertEqual(bridge.focusAddonId, "")
        self.assertEqual(bridge.requestSerial, initial_serial + 2)
        self.assertEqual(
            bridge.request,
            {
                "open": False,
                "focus_addon_id": "",
                "request_serial": initial_serial + 2,
            },
        )

    def test_content_fullscreen_bridge_context_property_registers_shell_owned_contract(self) -> None:
        context = self.window.quick_widget.rootContext()
        runtime = self.window.shell_services.runtime
        bridge = context.contextProperty("contentFullscreenBridge")

        self.assertIsInstance(bridge, ContentFullscreenBridge)
        self.assertIs(bridge, runtime.content_fullscreen_bridge)
        self.assertIs(bridge.parent(), self.window)
        self.assertIs(bridge._scene_bridge, self.window.scene)
        self.assertIs(bridge._viewer_session_bridge, runtime.viewer_session_bridge)
        self.assertFalse(bridge.open)
        self.assertEqual(bridge.node_id, "")
        self.assertEqual(bridge.workspace_id, "")
        self.assertEqual(bridge.content_kind, "")
        self.assertEqual(bridge.media_payload, {})
        self.assertEqual(bridge.viewer_payload, {})

    def test_shell_window_keeps_services_bundle_in_sync_with_context_bundle(self) -> None:
        services = self.window.shell_services
        bridges = services.context_bridges.shell_context_bridges
        context_bindings = dict(services.qml_context.qml_context_property_bindings)

        self.assertIs(self.window.shell_library_bridge, bridges.shell_library_bridge)
        self.assertIs(self.window.shell_workspace_bridge, bridges.shell_workspace_bridge)
        self.assertIs(self.window.shell_inspector_bridge, bridges.shell_inspector_bridge)
        self.assertIs(self.window.graph_canvas_state_bridge, bridges.graph_canvas_state_bridge)
        self.assertIs(self.window.graph_canvas_command_bridge, bridges.graph_canvas_command_bridge)
        self.assertIs(
            self.window.graph_action_bridge,
            context_bindings["graphActionBridge"],
        )
        self.assertIs(
            services.runtime.viewer_session_bridge,
            context_bindings["viewerSessionBridge"],
        )
        self.assertIs(
            services.runtime.viewer_host_service,
            context_bindings["viewerHostService"],
        )
        self.assertNotIn("_shell_context_bridges", self.window.__dict__)
        self.assertNotIn("_shell_qml_context_property_bindings", self.window.__dict__)
        self.assertNotIn("_shell_qml_host_bindings", self.window.__dict__)
        self.assertNotIn("shell_context", self.window.__dict__)


class PresenterPackageBoundaryTests(unittest.TestCase):
    def test_presenter_family_split_uses_curated_package_surface(self) -> None:
        package_root = _REPO_ROOT / "ea_node_editor" / "ui" / "shell" / "presenters"
        self.assertTrue(package_root.is_dir())
        self.assertFalse((_REPO_ROOT / "ea_node_editor" / "ui" / "shell" / "presenters.py").exists())

        module = importlib.import_module("ea_node_editor.ui.shell.presenters")
        self.assertTrue(str(module.__file__ or "").replace("\\", "/").endswith("/ui/shell/presenters/__init__.py"))

        expected_exports = {
            "AddOnManagerPresenter",
            "GraphCanvasHostPresenter",
            "CanvasExportPresenter",
            "ShellInspectorPresenter",
            "ShellLibraryPresenter",
            "ShellWorkspacePresenter",
            "ShellWorkspaceUiState",
            "build_default_shell_workspace_ui_state",
            "normalize_graph_theme_settings",
        }
        self.assertTrue(expected_exports.issubset(set(getattr(module, "__all__", ()))))
        for name in expected_exports:
            with self.subTest(name=name):
                self.assertTrue(hasattr(module, name))
        self.assertIs(AddOnManagerPresenter, getattr(module, "AddOnManagerPresenter"))

        for relative_path in (
            "__init__.py",
            "addon_manager_presenter.py",
            "library_presenter.py",
            "workspace_presenter.py",
            "inspector_presenter.py",
            "canvas_export_presenter.py",
            "graph_canvas_host_presenter.py",
        ):
            with self.subTest(path=relative_path):
                self.assertTrue((package_root / relative_path).is_file())


class ShellWindowStateFacadeBoundaryTests(unittest.TestCase):
    def test_window_state_split_uses_explicit_mixins_without_helper_facade(self) -> None:
        package_root = _REPO_ROOT / "ea_node_editor" / "ui" / "shell" / "window_state"
        helper_path = _REPO_ROOT / "ea_node_editor" / "ui" / "shell" / "window_state_helpers.py"
        window_source = (_REPO_ROOT / "ea_node_editor" / "ui" / "shell" / "window.py").read_text(
            encoding="utf-8"
        )

        self.assertTrue(package_root.is_dir())
        for relative_path in (
            "__init__.py",
            "context_properties.py",
            "library_and_overlay_state.py",
            "workspace_graph_actions.py",
            "project_session_actions.py",
            "run_and_style_state.py",
        ):
            with self.subTest(path=relative_path):
                self.assertTrue((package_root / relative_path).is_file())
        self.assertFalse(helper_path.exists())
        self.assertNotIn("locals().update", window_source)
        self.assertNotIn("SHELL_WINDOW_FACADE_BINDINGS", window_source)

        module_expectations = {
            "context_properties": ("ShellWindowContextPropertiesMixin", "project_path"),
            "library_and_overlay_state": ("ShellWindowLibraryOverlayStateMixin", "request_open_graph_search"),
            "project_session_actions": ("ShellWindowProjectSessionActionsMixin", "_save_project"),
            "run_and_style_state": ("ShellWindowRunAndStyleStateMixin", "request_run_workflow"),
            "workspace_graph_actions": ("ShellWindowWorkspaceGraphActionsMixin", "request_create_workspace"),
        }
        for module_name, (mixin_name, representative_name) in module_expectations.items():
            with self.subTest(module=module_name):
                module = importlib.import_module(f"ea_node_editor.ui.shell.window_state.{module_name}")
                self.assertTrue(hasattr(module, mixin_name))
                self.assertFalse(hasattr(module, "WINDOW_STATE_FACADE_BINDINGS"))
                self.assertIn(mixin_name, getattr(module, "__all__", ()))
                # Mixin members are defined in the class body, not rebound from
                # module-level functions through an assignment block.
                self.assertIn(representative_name, vars(getattr(module, mixin_name)))
                self.assertFalse(hasattr(module, representative_name))

        from ea_node_editor.ui.shell.window import ShellWindow

        for slot_name in sorted(QML_GRAPH_ACTION_DISPATCH_SLOTS):
            with self.subTest(slot=slot_name):
                self.assertEqual(
                    getattr(ShellWindow, slot_name).__module__,
                    "ea_node_editor.ui.shell.window_state.workspace_graph_actions",
                )

    def test_shell_window_leaves_dependency_creation_in_composition_root(self) -> None:
        shell_window_source = (_REPO_ROOT / "ea_node_editor" / "ui" / "shell" / "window.py").read_text(
            encoding="utf-8"
        )
        composition_package_root = _REPO_ROOT / "ea_node_editor" / "ui" / "shell" / "composition"
        composition_source = "\n".join(
            module_path.read_text(encoding="utf-8")
            for module_path in sorted(composition_package_root.glob("*.py"))
        )

        self.assertNotIn("ProcessExecutionClient", shell_window_source)
        self.assertNotIn("CorexRuntime", shell_window_source)
        self.assertNotIn("SessionAutosaveStore", shell_window_source)
        self.assertNotIn("def _create_execution_client", shell_window_source)
        self.assertNotIn("def _create_session_store", shell_window_source)
        self.assertIn("CorexRuntime", composition_source)
        self.assertIn("SessionAutosaveStore", composition_source)


class MainWindowBridgeContractPacketBoundaryTests(unittest.TestCase):
    def test_bridge_contracts_entrypoint_stays_thin_and_routes_suites_through_packet_modules(self) -> None:
        module = importlib.import_module("tests.main_window_shell.bridge_contracts")
        package_root = _REPO_ROOT / "tests" / "main_window_shell"
        entry_path = package_root / "bridge_contracts.py"

        self.assertTrue(entry_path.is_file())
        for relative_path in (
            "bridge_support.py",
            "bridge_contracts_library_and_inspector.py",
            "bridge_contracts_workspace_and_console.py",
        ):
            with self.subTest(path=relative_path):
                self.assertTrue((package_root / relative_path).is_file())

        self.assertEqual(
            module.ShellLibraryBridgeTests.__module__,
            "tests.main_window_shell.bridge_contracts_library_and_inspector",
        )
        self.assertEqual(
            module.ShellInspectorBridgeTests.__module__,
            "tests.main_window_shell.bridge_contracts_library_and_inspector",
        )
        self.assertEqual(
            module.ShellWorkspaceBridgeTests.__module__,
            "tests.main_window_shell.bridge_contracts_workspace_and_console",
        )
        self.assertEqual(
            module.SharedUiSupportBoundaryTests.__module__,
            "tests.main_window_shell.bridge_contracts_workspace_and_console",
        )
        self.assertEqual(
            module._named_child_items.__module__,
            "tests.main_window_shell.bridge_support",
        )


class MainWindowGraphCanvasSplitBridgeTests(SharedMainWindowShellTestBase):
    def test_qml_context_registers_action_state_command_and_view_canvas_bridges(self) -> None:
        context = self.window.quick_widget.rootContext()
        graph_action_bridge = context.contextProperty("graphActionBridge")
        graph_canvas_state_bridge = context.contextProperty("graphCanvasStateBridge")
        graph_canvas_command_bridge = context.contextProperty("graphCanvasCommandBridge")
        graph_canvas_view_bridge = context.contextProperty("graphCanvasViewBridge")

        self.assertIsInstance(graph_action_bridge, GraphActionBridge)
        self.assertIs(graph_action_bridge.parent(), self.window)
        self.assertIs(graph_action_bridge.controller, self.window.graph_action_controller)
        self.assertIsInstance(graph_canvas_state_bridge, GraphCanvasStateBridge)
        self.assertIs(graph_canvas_state_bridge.parent(), self.window)
        self.assertIs(graph_canvas_state_bridge._session_state, self.window.search_scope_state)
        self.assertIs(graph_canvas_state_bridge.graphics_source, self.window.shell_workspace_presenter)
        self.assertIs(graph_canvas_state_bridge.execution_source, self.window)
        self.assertIs(graph_canvas_state_bridge.scene_bridge, self.window.scene)
        self.assertIs(graph_canvas_state_bridge.view_bridge, self.window.view)

        self.assertIsInstance(graph_canvas_command_bridge, GraphCanvasCommandBridge)
        self.assertIs(graph_canvas_command_bridge.parent(), self.window)
        self.assertIs(graph_canvas_command_bridge._run_controller, self.window.run_controller)
        self.assertIs(
            graph_canvas_command_bridge.graphics_source,
            self.window.shell_workspace_presenter,
        )
        self.assertIs(graph_canvas_command_bridge.host_source, self.window.graph_canvas_host_presenter)
        self.assertIs(graph_canvas_command_bridge.scene_bridge, self.window.scene)
        self.assertIs(graph_canvas_command_bridge.view_bridge, self.window.view)
        self.assertIs(
            self.window.scene._graphics_preferences_source,
            self.window.shell_workspace_presenter,
        )
        self.assertIs(graph_canvas_view_bridge, self.window.view)
        self.assertIs(graph_canvas_view_bridge.parent(), self.window)

    def test_shell_window_keeps_graph_canvas_state_command_bridges_in_services_bundle(self) -> None:
        bridges = self.window.shell_services.context_bridges.shell_context_bridges

        self.assertIs(self.window.graph_action_bridge.controller, self.window.graph_action_controller)
        self.assertIs(self.window.graph_canvas_state_bridge, bridges.graph_canvas_state_bridge)
        self.assertIs(self.window.graph_canvas_command_bridge, bridges.graph_canvas_command_bridge)


class MainWindowPyQtGraphActionRouteTests(SharedMainWindowShellTestBase):
    def test_pyqt_duplicate_clipboard_group_backdrop_subnode_group_align_scope_actions_dispatch_to_controller(self) -> None:
        actions = (
            (self.window.action_connect_selected, GraphActionId.CONNECT_SELECTED),
            (self.window.action_duplicate_selection, GraphActionId.DUPLICATE_SELECTION),
            (self.window.action_wrap_selection_in_group_backdrop, GraphActionId.WRAP_SELECTION_IN_GROUP_BACKDROP),
            (self.window.action_group_selection, GraphActionId.GROUP_SELECTION),
            (self.window.action_ungroup_selection, GraphActionId.UNGROUP_SELECTION),
            (self.window.action_align_left, GraphActionId.ALIGN_SELECTION_LEFT),
            (self.window.action_align_right, GraphActionId.ALIGN_SELECTION_RIGHT),
            (self.window.action_align_top, GraphActionId.ALIGN_SELECTION_TOP),
            (self.window.action_align_bottom, GraphActionId.ALIGN_SELECTION_BOTTOM),
            (self.window.action_distribute_horizontally, GraphActionId.DISTRIBUTE_SELECTION_HORIZONTALLY),
            (self.window.action_distribute_vertically, GraphActionId.DISTRIBUTE_SELECTION_VERTICALLY),
            (self.window.action_straighten_connections, GraphActionId.STRAIGHTEN_SELECTION_CONNECTIONS),
            (self.window.action_copy_selection, GraphActionId.COPY_SELECTION),
            (self.window.action_cut_selection, GraphActionId.CUT_SELECTION),
            (self.window.action_paste_selection, GraphActionId.PASTE_SELECTION),
            (self.window.action_scope_parent, GraphActionId.NAVIGATE_SCOPE_PARENT),
            (self.window.action_scope_root, GraphActionId.NAVIGATE_SCOPE_ROOT),
            (self.window.action_show_help, GraphActionId.SHOW_NODE_HELP),
        )
        calls: list[tuple[str, object | None]] = []

        def record(action_id: str, payload: object | None = None) -> bool:
            calls.append((action_id, payload))
            return True

        with patch.object(self.window.graph_action_controller, "trigger", side_effect=record):
            for action, _action_id in actions:
                action.trigger()

        self.assertEqual(calls, [(action_id.value, None) for _action, action_id in actions])

    def test_public_graph_action_slots_are_owned_by_workspace_graph_actions_mixin(self) -> None:
        for slot_name in sorted(QML_GRAPH_ACTION_DISPATCH_SLOTS):
            with self.subTest(slot_name=slot_name):
                self.assertEqual(
                    getattr(type(self.window), slot_name).__module__,
                    "ea_node_editor.ui.shell.window_state.workspace_graph_actions",
                )

    def test_duplicate_clipboard_group_backdrop_subnode_group_align_scope_request_slots_delegate_to_controller(self) -> None:
        requests = (
            (self.window.request_connect_selected_nodes, GraphActionId.CONNECT_SELECTED, None, None),
            (self.window.request_duplicate_selected_nodes, GraphActionId.DUPLICATE_SELECTION, None, True),
            (
                self.window.request_wrap_selected_nodes_in_group_backdrop,
                GraphActionId.WRAP_SELECTION_IN_GROUP_BACKDROP,
                None,
                True,
            ),
            (self.window.request_group_selected_nodes, GraphActionId.GROUP_SELECTION, None, True),
            (self.window.request_ungroup_selected_nodes, GraphActionId.UNGROUP_SELECTION, None, True),
            (self.window.request_align_selection_left, GraphActionId.ALIGN_SELECTION_LEFT, None, True),
            (self.window.request_align_selection_right, GraphActionId.ALIGN_SELECTION_RIGHT, None, True),
            (self.window.request_align_selection_top, GraphActionId.ALIGN_SELECTION_TOP, None, True),
            (self.window.request_align_selection_bottom, GraphActionId.ALIGN_SELECTION_BOTTOM, None, True),
            (
                self.window.request_distribute_selection_horizontally,
                GraphActionId.DISTRIBUTE_SELECTION_HORIZONTALLY,
                None,
                True,
            ),
            (
                self.window.request_distribute_selection_vertically,
                GraphActionId.DISTRIBUTE_SELECTION_VERTICALLY,
                None,
                True,
            ),
            (
                self.window.request_straighten_selection_connections,
                GraphActionId.STRAIGHTEN_SELECTION_CONNECTIONS,
                None,
                True,
            ),
            (self.window.request_copy_selected_nodes, GraphActionId.COPY_SELECTION, None, True),
            (self.window.request_cut_selected_nodes, GraphActionId.CUT_SELECTION, None, True),
            (self.window.request_paste_selected_nodes, GraphActionId.PASTE_SELECTION, None, True),
            (self.window.request_navigate_scope_parent, GraphActionId.NAVIGATE_SCOPE_PARENT, None, True),
            (self.window.request_navigate_scope_root, GraphActionId.NAVIGATE_SCOPE_ROOT, None, True),
            (
                lambda: self.window.request_delete_selected_graph_items(["edge-1"]),
                GraphActionId.DELETE_SELECTION,
                {"edge_ids": ["edge-1"]},
                True,
            ),
        )
        calls: list[tuple[str, object | None]] = []

        def record(action_id: str, payload: object | None = None) -> bool:
            calls.append((action_id, payload))
            return True

        with patch.object(self.window.graph_action_controller, "trigger", side_effect=record):
            results = [request() for request, _action_id, _payload, _expected in requests]

        self.assertEqual(results, [expected for _request, _action_id, _payload, expected in requests])
        self.assertEqual(
            calls,
            [(action_id.value, payload) for _request, action_id, payload, _expected in requests],
        )


class MainWindowGraphTypographyBridgeTests(SharedMainWindowShellTestBase):
    def test_graph_typography_bridge_shell_window_and_canvas_state_bridge_follow_graphics_updates(self) -> None:
        context = self.window.quick_widget.rootContext()
        graph_canvas_state_bridge = context.contextProperty("graphCanvasStateBridge")
        seen = {
            "window_graphics_preferences_changed": 0,
            "bridge_graphics_preferences_changed": 0,
        }
        self.window.graphics_preferences_changed.connect(
            lambda: seen.__setitem__(
                "window_graphics_preferences_changed",
                seen["window_graphics_preferences_changed"] + 1,
            )
        )
        graph_canvas_state_bridge.graphics_preferences_changed.connect(
            lambda: seen.__setitem__(
                "bridge_graphics_preferences_changed",
                seen["bridge_graphics_preferences_changed"] + 1,
            )
        )

        self.assertGreaterEqual(
            self.window.metaObject().indexOfProperty("graphics_graph_label_pixel_size"),
            0,
        )
        self.assertEqual(self.window.workspace_ui_state.graph_label_pixel_size, 10)
        self.assertEqual(self.window.shell_workspace_presenter.graphics_graph_label_pixel_size, 10)
        self.assertEqual(self.window.graphics_graph_label_pixel_size, 10)
        self.assertEqual(graph_canvas_state_bridge.graphics_graph_label_pixel_size, 10)

        resolved = self.window.app_preferences_controller.update_graphics_settings(
            {"typography": {"graph_label_pixel_size": 16}},
            host=self.window,
        )
        self.app.processEvents()

        self.assertEqual(resolved["typography"]["graph_label_pixel_size"], 16)
        self.assertEqual(
            self.window.app_preferences_controller.graphics_settings()["typography"]["graph_label_pixel_size"],
            16,
        )
        self.assertEqual(self.window.workspace_ui_state.graph_label_pixel_size, 16)
        self.assertEqual(self.window.shell_workspace_presenter.graphics_graph_label_pixel_size, 16)
        self.assertEqual(self.window.graphics_graph_label_pixel_size, 16)
        self.assertEqual(graph_canvas_state_bridge.graphics_graph_label_pixel_size, 16)
        self.assertEqual(
            seen,
            {
                "window_graphics_preferences_changed": 1,
                "bridge_graphics_preferences_changed": 1,
            },
        )

    def test_graph_node_icon_size_bridge_shell_window_and_canvas_state_bridge_project_effective_size(self) -> None:
        context = self.window.quick_widget.rootContext()
        graph_canvas_state_bridge = context.contextProperty("graphCanvasStateBridge")
        seen = {
            "window_graphics_preferences_changed": 0,
            "bridge_graphics_preferences_changed": 0,
        }
        self.window.graphics_preferences_changed.connect(
            lambda: seen.__setitem__(
                "window_graphics_preferences_changed",
                seen["window_graphics_preferences_changed"] + 1,
            )
        )
        graph_canvas_state_bridge.graphics_preferences_changed.connect(
            lambda: seen.__setitem__(
                "bridge_graphics_preferences_changed",
                seen["bridge_graphics_preferences_changed"] + 1,
            )
        )

        self.assertGreaterEqual(
            self.window.metaObject().indexOfProperty("graphics_graph_node_icon_pixel_size_override"),
            0,
        )
        self.assertGreaterEqual(
            self.window.metaObject().indexOfProperty("graphics_node_title_icon_pixel_size"),
            0,
        )
        self.assertIsNone(self.window.workspace_ui_state.graph_node_icon_pixel_size_override)
        self.assertEqual(self.window.workspace_ui_state.node_title_icon_pixel_size, 10)
        self.assertIsNone(self.window.graphics_graph_node_icon_pixel_size_override)
        self.assertEqual(self.window.graphics_node_title_icon_pixel_size, 10)
        self.assertIsNone(graph_canvas_state_bridge.graphics_graph_node_icon_pixel_size_override)
        self.assertEqual(graph_canvas_state_bridge.graphics_node_title_icon_pixel_size, 10)

        resolved = self.window.app_preferences_controller.update_graphics_settings(
            {
                "typography": {
                    "graph_label_pixel_size": 16,
                    "graph_node_icon_pixel_size_override": 12,
                }
            },
            host=self.window,
        )
        self.app.processEvents()

        self.assertEqual(resolved["typography"]["graph_label_pixel_size"], 16)
        self.assertEqual(resolved["typography"]["graph_node_icon_pixel_size_override"], 12)
        self.assertEqual(self.window.workspace_ui_state.graph_label_pixel_size, 16)
        self.assertEqual(self.window.workspace_ui_state.graph_node_icon_pixel_size_override, 12)
        self.assertEqual(self.window.workspace_ui_state.node_title_icon_pixel_size, 12)
        self.assertEqual(self.window.shell_workspace_presenter.graphics_node_title_icon_pixel_size, 12)
        self.assertEqual(self.window.graphics_node_title_icon_pixel_size, 12)
        self.assertEqual(graph_canvas_state_bridge.graphics_node_title_icon_pixel_size, 12)
        self.assertEqual(
            seen,
            {
                "window_graphics_preferences_changed": 1,
                "bridge_graphics_preferences_changed": 1,
            },
        )

        resolved = self.window.app_preferences_controller.update_graphics_settings(
            {
                "typography": {
                    "graph_node_icon_pixel_size_override": None,
                }
            },
            host=self.window,
        )
        self.app.processEvents()

        self.assertIsNone(resolved["typography"]["graph_node_icon_pixel_size_override"])
        self.assertEqual(self.window.graphics_graph_label_pixel_size, 16)
        self.assertEqual(self.window.graphics_node_title_icon_pixel_size, 16)
        self.assertIsNone(graph_canvas_state_bridge.graphics_graph_node_icon_pixel_size_override)
        self.assertEqual(graph_canvas_state_bridge.graphics_node_title_icon_pixel_size, 16)
        self.assertEqual(
            seen,
            {
                "window_graphics_preferences_changed": 2,
                "bridge_graphics_preferences_changed": 2,
            },
        )


class ShellWorkspaceBridgeQmlBoundaryTests(unittest.TestCase):
    def test_workspace_run_toolbar_and_console_qml_routes_owned_concerns_through_shell_workspace_bridge(self) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/shell/ShellRunToolbar.qml": (
                (
                    "property var mainWindowRef",
                    "mainWindowRef.project_file_name",
                    "mainWindowRef.active_scope_breadcrumb_items",
                    "mainWindowRef.request_run_workflow",
                    "mainWindowRef.request_toggle_run_pause",
                    "mainWindowRef.request_stop_workflow",
                    "mainWindowRef.request_open_scope_breadcrumb",
                    "mainWindowRef.set_script_editor_panel_visible",
                    'objectName: "shellRunToolbarRunButton"',
                    'objectName: "shellRunToolbarPauseButton"',
                ),
                (
                    "property var viewBridgeRef",
                    "property var scriptEditorBridgeRef",
                    "property var workspaceBridgeRef:",
                    "property var themeBridgeRef:",
                    'objectName: "shellRunToolbarProjectFileName"',
                    'objectName: "shellRunToolbarScopeBreadcrumb"',
                    'objectName: "shellRunToolbarRunPauseResumeButton"',
                    'objectName: "shellRunToolbarStopButton"',
                    "root.workspaceBridgeRef.project_file_name",
                    "root.workspaceBridgeRef.active_scope_breadcrumb_items",
                    "root.workspaceBridgeRef.active_workspace_run_control_mode",
                    "enabled: root.workspaceBridgeRef.active_workspace_can_run",
                    "|| root.workspaceBridgeRef.active_workspace_can_pause",
                    "enabled: root.workspaceBridgeRef.active_workspace_can_stop",
                    'if (runControlMode === "run")',
                    "root.workspaceBridgeRef.request_run_workflow",
                    "root.workspaceBridgeRef.request_toggle_run_pause",
                    "root.workspaceBridgeRef.request_stop_workflow",
                    "root.workspaceBridgeRef.request_open_scope_breadcrumb",
                    "root.workspaceBridgeRef.set_script_editor_panel_visible",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/WorkspaceCenterPane.qml": (
                (
                    "mainWindowRef.graphics_tab_strip_density",
                    "mainWindowRef.active_scope_breadcrumb_items",
                    "mainWindowRef.active_view_items",
                    "mainWindowRef.active_workspace_id",
                    "mainWindowRef.request_open_scope_breadcrumb",
                    "mainWindowRef.request_switch_view",
                    "mainWindowRef.request_move_view_tab",
                    "mainWindowRef.request_rename_view",
                    "mainWindowRef.request_close_view",
                    "mainWindowRef.request_create_view",
                    "mainWindowRef.request_move_workspace_tab",
                    "mainWindowRef.request_rename_workspace_by_id",
                    "mainWindowRef.request_close_workspace_by_id",
                    "mainWindowRef.request_create_workspace",
                    "property var workspaceTabsBridgeRef",
                    "property var consoleBridgeRef",
                    "workspaceTabsBridgeRef.tabs",
                    "workspaceTabsBridgeRef.activate_workspace",
                    "consoleBridgeRef.error_count_value",
                    "consoleBridgeRef.warning_count_value",
                    "consoleBridgeRef.clear_all",
                    "consoleBridgeRef.output_text",
                    "consoleBridgeRef.errors_text",
                    "consoleBridgeRef.warnings_text",
                    "property var mainWindowRef",
                    "property var sceneBridgeRef",
                    "property var viewBridgeRef",
                    "property var graphCanvasBridgeRef",
                    "canvasBridge: root.graphCanvasBridgeRef",
                ),
                (
                    "property var graphActionBridgeRef",
                    "property var graphCanvasStateBridgeRef",
                    "property var graphCanvasCommandBridgeRef",
                    "property var overlayHostItem",
                    "property var workspaceBridgeRef",
                    "property var themeBridgeRef",
                    "property var uiIconsRef:",
                    "root.workspaceBridgeRef.graphics_tab_strip_density",
                    "root.workspaceBridgeRef.active_view_items",
                    "root.workspaceBridgeRef.active_workspace_id",
                    "root.workspaceBridgeRef.request_switch_view",
                    "root.workspaceBridgeRef.request_move_view_tab",
                    "root.workspaceBridgeRef.request_rename_view",
                    "root.workspaceBridgeRef.request_close_view",
                    "root.workspaceBridgeRef.request_create_view",
                    "root.workspaceBridgeRef.request_move_workspace_tab",
                    "root.workspaceBridgeRef.request_rename_workspace_by_id",
                    "root.workspaceBridgeRef.request_close_workspace_by_id",
                    "root.workspaceBridgeRef.request_create_workspace",
                    "root.workspaceBridgeRef.workspace_tabs",
                    "root.workspaceBridgeRef.activate_workspace",
                    "root.workspaceBridgeRef.error_count_value",
                    "root.workspaceBridgeRef.warning_count_value",
                    "root.workspaceBridgeRef.clear_all",
                    "root.workspaceBridgeRef.output_text",
                    "root.workspaceBridgeRef.errors_text",
                    "root.workspaceBridgeRef.warnings_text",
                    'objectName: "workspaceConsoleSeverityTabs"',
                    '"workspaceConsoleOutputTab"',
                    '"workspaceConsoleErrorsTab"',
                    '"workspaceConsoleWarningsTab"',
                    '"workspaceConsoleErrorsBadge"',
                    '"workspaceConsoleWarningsBadge"',
                    'objectName: "workspaceConsoleClearButton"',
                    'objectName: "workspaceConsoleResizeHandle"',
                    'objectName: "workspaceConsoleOutputScrollView"',
                    'objectName: "workspaceConsoleOutputTextArea"',
                    "ScrollBar.vertical.policy: ScrollBar.AsNeeded",
                    "cursorShape: Qt.SplitVCursor",
                    "function scrollToBottom()",
                    "badgeValue: consolePane.consoleChannelCount(channelIndex)",
                    "graphActionBridge: root.graphActionBridgeRef",
                    "canvasStateBridge: root.graphCanvasStateBridgeRef",
                    "canvasCommandBridge: root.graphCanvasCommandBridgeRef",
                ),
            ),
            "ea_node_editor/ui_qml/components/shell/ScriptEditorOverlay.qml": (
                (
                    "property var mainWindowRef",
                    "mainWindowRef.set_script_editor_panel_visible(false)",
                ),
                (
                    "property var scriptEditorBridgeRef",
                    "property var scriptHighlighterBridgeRef",
                    "property var workspaceBridgeRef:",
                    "property var themeBridgeRef:",
                    "root.workspaceBridgeRef.set_script_editor_panel_visible(false)",
                ),
            ),
        }

        for relative_path, (absent_snippets, present_snippets) in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            _assert_text_snippets(
                self,
                label=relative_path,
                text=qml_text,
                absent_snippets=absent_snippets,
                present_snippets=present_snippets,
            )

    def test_main_shell_keeps_only_the_remaining_live_shell_plumbing_assignments(self) -> None:
        relative_path = "ea_node_editor/ui_qml/MainShell.qml"
        qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")

        absent_snippets = (
            "typeof graphCanvasBridge",
            "typeof mainWindow",
            "typeof sceneBridge",
            "typeof viewBridge",
            "workspaceTabsBridgeRef: workspaceTabsBridge",
            "consoleBridgeRef: consoleBridge",
            "mainWindowRef: mainWindow",
            "sceneBridgeRef: root.sceneBridgeRef",
            "viewBridgeRef: root.viewBridgeRef",
            "viewBridgeRef: viewBridge",
            "readonly property var canvasShellBridgeRef",
            "readonly property var canvasSceneBridgeRef",
            "readonly property var canvasBridgeRef: graphCanvasBridge",
            "canvasBridgeRef: root.canvasBridgeRef",
            "ShellTitleBar {",
        )
        present_snippets = (
            "readonly property var shellContextRef: shellContext",
            "readonly property var shellLibraryBridgeRef: root.shellContextRef.shellLibraryBridge",
            "readonly property var shellWorkspaceBridgeRef: root.shellContextRef.shellWorkspaceBridge",
            "readonly property var themeBridgeRef: root.shellContextRef.themeBridge",
            "readonly property var graphThemeBridgeRef: root.shellContextRef.graphThemeBridge",
            "readonly property var contentFullscreenBridgeRef: root.shellContextRef.contentFullscreenBridge",
            "readonly property var viewerHostServiceRef: root.shellContextRef.viewerHostService",
            "readonly property var graphActionBridgeRef: root.shellContextRef.graphActionBridge",
            "readonly property var canvasStateBridgeRef: root.shellContextRef.graphCanvasStateBridge",
            "readonly property var canvasCommandBridgeRef: root.shellContextRef.graphCanvasCommandBridge",
            "readonly property var canvasViewBridgeRef: root.shellContextRef.graphCanvasViewBridge",
            "WorkspaceCenterPane {",
            "graphActionBridgeRef: root.graphActionBridgeRef",
            "graphCanvasStateBridgeRef: root.canvasStateBridgeRef",
            "graphCanvasCommandBridgeRef: root.canvasCommandBridgeRef",
            "workspaceBridgeRef: root.shellWorkspaceBridgeRef",
            "themeBridgeRef: root.themeBridgeRef",
            "overlayHostItem: root",
            "viewBridgeRef: root.canvasViewBridgeRef",
            "ShellStatusStrip {",
            "canvasStateBridgeRef: root.canvasStateBridgeRef",
            "canvasCommandBridgeRef: root.canvasCommandBridgeRef",
            "scriptEditorBridgeRef: root.scriptEditorBridgeRef",
            "scriptHighlighterBridgeRef: root.scriptHighlighterBridgeRef",
        )

        _assert_text_snippets(
            self,
            label=relative_path,
            text=qml_text,
            absent_snippets=absent_snippets,
            present_snippets=present_snippets,
        )

    def test_migrated_shell_components_do_not_reach_shell_context_directly(self) -> None:
        shell_component_root = _REPO_ROOT / "ea_node_editor/ui_qml/components/shell"
        for qml_path in shell_component_root.glob("*.qml"):
            qml_text = qml_path.read_text(encoding="utf-8")
            _assert_text_snippets(
                self,
                label=qml_path.relative_to(_REPO_ROOT).as_posix(),
                text=qml_text,
                absent_snippets=("shellContext",),
            )


class NodeBrowserQmlBoundaryTests(unittest.TestCase):
    def test_node_browser_owns_keyboard_click_drag_and_anchored_insert_paths(self) -> None:
        relative_path = "ea_node_editor/ui_qml/components/shell/NodeBrowserOverlay.qml"
        qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")

        _assert_text_snippets(
            self,
            label=relative_path,
            text=qml_text,
            present_snippets=(
                "function openBrowser(initialQuery, sceneX, sceneY, mode)",
                "Common.DialogSurface {",
                "Common.DialogTextField {",
                "Common.DialogButton {",
                "closeButtonVisible: true",
                "onCloseRequested: root.closeBrowser()",
                "readonly property var rootCategoryOptions: root._rootCategoryOptions()",
                "readonly property var groupedRows: root._groupedRows()",
                "function _handleNavigationKey(event)",
                "model: root.groupedRows",
                'objectName: "nodeBrowserCategoryHeader"',
                'objectName: "nodeBrowserNodeTile"',
                'property int itemIndex: Number(modelData)',
                "onDoubleClicked:",
                "root.graphCanvasRef.performLibraryDrop",
                "root.canvasCommandBridgeRef.request_drop_node_from_library",
                'text: "Open Example"',
                "enabled: false",
            ),
            absent_snippets=("ToolButton {",),
        )

    def test_canvas_quick_insert_owns_ctrl_b_canvas_mode(self) -> None:
        window_actions_path = _REPO_ROOT / "ea_node_editor/ui/shell/window_actions.py"
        window_actions_text = window_actions_path.read_text(encoding="utf-8")
        self.assertIn(
            "window.action_node_browser.triggered.connect("
            "lambda _checked=False: _open_canvas_quick_insert(window))",
            window_actions_text,
        )

        main_shell_path = _REPO_ROOT / "ea_node_editor/ui_qml/MainShell.qml"
        main_shell_text = main_shell_path.read_text(encoding="utf-8")
        self.assertIn("ConnectionQuickInsertOverlay {", main_shell_text)
        self.assertNotIn("CanvasInsertRadialMenu {", main_shell_text)

        quick_insert_path = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/shell/ConnectionQuickInsertOverlay.qml"
        )
        quick_insert_text = quick_insert_path.read_text(encoding="utf-8")
        self.assertIn(
            "visible: root.shellLibraryBridgeRef.connection_quick_insert_open",
            quick_insert_text,
        )
        self.assertNotIn(
            "&& !root.shellLibraryBridgeRef.connection_quick_insert_is_canvas_mode",
            quick_insert_text,
        )


class GraphCanvasQmlBoundaryTests(unittest.TestCase):
    def test_graph_canvas_routes_owned_concerns_through_split_bridge_refs(self) -> None:
        relative_path = "ea_node_editor/ui_qml/components/GraphCanvas.qml"
        qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")

        absent_snippets = (
            "property var canvasBridge: null",
            "readonly property var canvasBridgeRef",
            "property var mainWindowBridge",
            "property var viewBridge: root.canvasStateBridgeRef",
            "readonly property var _canvasViewStateBridgeRef: root.canvasStateBridgeRef",
            "readonly property var _canvasViewCommandBridgeRef: root.canvasCommandBridgeRef",
            "mainWindowBridge.graphics_minimap_expanded",
            "mainWindowBridge.graphics_show_grid",
            "mainWindowBridge.graphics_show_minimap",
            "mainWindowBridge.graphics_node_shadow",
            "mainWindowBridge.graphics_shadow_strength",
            "mainWindowBridge.graphics_shadow_softness",
            "mainWindowBridge.graphics_shadow_offset",
            "mainWindowBridge.snap_to_grid_enabled",
            "mainWindowBridge.snap_grid_size",
            "mainWindowBridge.request_open_subnode_scope",
            "mainWindowBridge.browse_node_property_path",
            "mainWindowBridge.request_drop_node_from_library",
            "mainWindowBridge.request_connect_ports",
            "mainWindowBridge.request_open_connection_quick_insert",
            "sceneBridge.nodes_model",
            "sceneBridge.selected_node_lookup",
            "sceneBridge.select_node",
            "sceneBridge.set_node_property",
            "sceneBridge.are_port_kinds_compatible",
            "sceneBridge.are_data_types_compatible",
            "sceneBridge.move_nodes_by_delta",
            "sceneBridge.move_node",
            "sceneBridge.resize_node",
            "viewBridge.adjust_zoom",
            "viewBridge.pan_by",
            "viewBridge.set_viewport_size",
            "viewBridge.zoom_value",
            "viewBridge.center_x",
            "viewBridge.center_y",
            "property var hoveredPort: null",
            "property var pendingConnectionPort: null",
            "property var wireDragState: null",
            "property bool edgeContextVisible: false",
            "property bool interactionActive: false",
            "readonly property var _canvasCommandBridgeRef",
            "readonly property var _canvasShellBridgeRef",
            "readonly property var _canvasSceneBridgeRef",
            "readonly property var _canvasViewBridgeRef",
            "typeof graphCanvasViewBridge",
            "readonly property var _canvasShellCompatRef",
            "readonly property var _canvasSceneCompatRef",
            "readonly property var _canvasViewCompatRef",
            "readonly property var _canvasCompatBridgeRef",
            "readonly property var _legacyCanvasViewBridgeRef",
            "readonly property var _canvasSceneStateBridgeRef",
            "readonly property var _canvasShellCommandBridgeRef",
            "readonly property var _canvasSceneCommandBridgeRef",
            "readonly property var _canvasViewCommandBridgeRef",
            "shellCommandBridge: root._canvasShellCommandBridgeRef",
            "graphCanvasFacade",
            "canvasFacadeRef",
            "_facadeService",
            "graphCanvasFacadeAdapter",
            "_canvasStateBridgeRef",
            "_canvasViewStateBridgeRef",
        )
        present_snippets = (
            "property var canvasStateBridge: null",
            "property var graphActionBridge: null",
            "property var canvasCommandBridge: null",
            "property var canvasViewBridge: null",
            "readonly property var _canvasViewportBridge: root.canvasViewBridge",
            "readonly property var graphActionBridgeRef",
            "readonly property var canvasStateBridgeRef: root.canvasStateBridge || null",
            "readonly property var canvasCommandBridgeRef: root.canvasCommandBridge || null",
            "readonly property var canvasViewBridgeRef: root._canvasViewportBridge",
            "readonly property var graphActionBridgeRef: root.graphActionBridge || null",
            "readonly property var sceneBridge: root.canvasStateBridgeRef",
            "readonly property var viewBridge: root.canvasViewBridgeRef",
            "readonly property bool showGrid: preferenceFactsObject.showGrid",
            "readonly property var sceneStateBridge: root.canvasStateBridgeRef",
            "readonly property var sceneCommandBridge: root.canvasCommandBridgeRef",
            "GraphCanvasComponents.GraphCanvasInteractionState {",
            "GraphCanvasComponents.GraphCanvasSceneState {",
            "GraphCanvasComponents.GraphCanvasNodeSurfaceBridge {",
            "GraphCanvasComponents.GraphCanvasViewportController {",
            "GraphCanvasComponents.GraphCanvasSceneLifecycle {",
            "GraphCanvasComponents.GraphCanvasRootLayers {",
            "GraphCanvasComponents.GraphCanvasInputLayers {",
            "GraphCanvasComponents.GraphCanvasContextMenus {",
            "graphActionBridge: root.graphActionBridgeRef",
            "readonly property var canvasViewportController: viewportController",
            "readonly property var canvasSceneLifecycle: sceneLifecycle",
            "property alias hoveredPort: interactionState.hoveredPort",
            "property alias pendingConnectionPort: interactionState.pendingConnectionPort",
            "property alias interactionActive: interactionState.interactionActive",
            'GraphCanvasRootApi.invoke(interactionState, "updateLibraryDropPreview"',
            'GraphCanvasRootApi.invoke(interactionState, "beginPortWireDrag"',
            'GraphCanvasRootApi.invoke(viewportController, "applyWheelZoom"',
            'GraphCanvasRootApi.invoke(sceneLifecycle, "requestEdgeRedraw"',
            "sceneStateBridge: root.sceneStateBridge",
            "sceneCommandBridge: root.sceneCommandBridge",
            "shellBridge: root.canvasCommandBridgeRef",
            "canvasCommandBridge: root.canvasCommandBridgeRef",
            "viewStateBridge: root.viewBridge",
            "viewCommandBridge: root.viewBridge",
        )

        _assert_text_snippets(
            self,
            label=relative_path,
            text=qml_text,
            absent_snippets=absent_snippets,
            present_snippets=present_snippets,
        )

    def test_node_execution_canvas_properties_bind_only_to_state_bridge_execution_contract(self) -> None:
        relative_path = "ea_node_editor/ui_qml/components/GraphCanvas.qml"
        qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")

        present_snippets = (
            "readonly property var runningNodeLookup: executionFactsObject.runningNodeLookup",
            "readonly property var completedNodeLookup: executionFactsObject.completedNodeLookup",
            "readonly property int nodeExecutionRevision: executionFactsObject.nodeExecutionRevision",
        )

        _assert_text_snippets(
            self,
            label=relative_path,
            text=qml_text,
            present_snippets=present_snippets,
        )

    def test_graph_canvas_interaction_state_helper_owns_extracted_canvas_state(self) -> None:
        relative_path = "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInteractionState.qml"
        helper_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")

        present_snippets = (
            "property var pendingConnectionPort: null",
            "property var wireDragState: null",
            "property bool edgeContextVisible: false",
            "property bool interactionActive: false",
            "property var interactionIdleTimer: null",
            "function updateLibraryDropPreview(screenX, screenY, payload) {",
            "function finishPortWireDrag(nodeId, portKey, direction, _sceneX, _sceneY, screenX, screenY, dragActive, modifiers) {",
            "function _openNodeContext(nodeId, x, y) {",
            "function resetSceneBridgeState() {",
        )

        _assert_text_snippets(
            self,
            label=relative_path,
            text=helper_text,
            present_snippets=present_snippets,
        )

    def test_graph_canvas_helper_components_hold_scene_surface_and_delegate_logic(self) -> None:
        expectations = {
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasSceneState.qml": (
                "property var selectedEdgeIds: []",
                "function sceneNodePayload(nodeId) {",
                "function syncEdgePayload() {",
                'bridge && typeof bridge.selected_node_lookup !== "undefined"',
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasNodeSurfaceBridge.qml": (
                "GraphCanvasSurfaceInteractionHost {",
                "function requestOpenSubnodeScope(nodeId) {",
                "function commitNodeSurfaceProperties(nodeId, properties) {",
                "function browseNodePropertyPath(nodeId, key, currentPath) {",
                "function pickNodePropertyColor(nodeId, key, currentValue) {",
                "bridge.pick_node_property_color",
                "return hostInteraction.sceneSelectionBridge();",
                "hostInteraction.resetSurfaceInteractionState();",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasViewportController.qml": (
                "function applyWheelZoom(eventObj) {",
                "function requestViewStateRedraw() {",
                "function updateViewportSize() {",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasSceneLifecycle.qml": (
                "function handleSceneMutation() {",
                "function resetCanvasSceneState() {",
                "target: root.sceneStateBridge",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasNodeDelegate.qml": (
                "GraphComponents.GraphNodeHost {",
                "property bool backdropInputOverlay: false",
                "canvasItem.requestEdgeRedraw",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasWorldLayer.qml": (
                "property bool backdropInputOverlay: false",
                "delegate: GraphCanvasNodeDelegate {",
                "scale: viewBridge ? viewBridge.zoom_value : 1.0",
            ),
        }

        for relative_path, present_snippets in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            _assert_text_snippets(
                self,
                label=relative_path,
                text=qml_text,
                present_snippets=present_snippets,
            )

    def test_graph_canvas_root_exposes_color_picker_helper_through_node_surface_bridge(self) -> None:
        relative_path = "ea_node_editor/ui_qml/components/GraphCanvas.qml"
        qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")

        _assert_text_snippets(
            self,
            label=relative_path,
            text=qml_text,
            present_snippets=(
                "function pickNodePropertyColor(nodeId, key, currentValue) {",
                'GraphCanvasRootApi.invoke(nodeSurfaceBridge, "pickNodePropertyColor", [nodeId, key, currentValue], "")',
            ),
        )

    def test_overlay_host_item_plumbing_remains_live_for_canvas_overlay_paths(self) -> None:
        expectations = {
            "ea_node_editor/ui_qml/MainShell.qml": (
                "WorkspaceCenterPane {",
                "overlayHostItem: root",
            ),
            "ea_node_editor/ui_qml/components/shell/WorkspaceCenterPane.qml": (
                "property var overlayHostItem",
                "overlayHostItem: root.overlayHostItem",
            ),
            "ea_node_editor/ui_qml/components/GraphCanvas.qml": (
                "property var overlayHostItem: null",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInputLayers.qml": (
                "var overlayHost = root.canvasItem.overlayHostItem || root.canvasItem;",
            ),
            "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInteractionState.qml": (
                "root.canvasItem.overlayHostItem ? root.canvasItem.overlayHostItem : root.canvasItem",
            ),
        }

        for relative_path, present_snippets in expectations.items():
            qml_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            _assert_text_snippets(
                self,
                label=relative_path,
                text=qml_text,
                present_snippets=present_snippets,
            )


class MainWindowNodeExecutionCanvasTests(SharedMainWindowShellTestBase):
    def test_node_execution_canvas_properties_follow_graph_canvas_state_bridge(self) -> None:
        graph_canvas = self._graph_canvas_item()
        bridge = self.window.graph_canvas_state_bridge
        workspace_id = self.window.scene.workspace_id

        self.assertTrue(workspace_id)
        self.assertEqual(graph_canvas.property("runningNodeLookup"), bridge.running_node_lookup)
        self.assertEqual(graph_canvas.property("completedNodeLookup"), bridge.completed_node_lookup)
        self.assertEqual(
            int(graph_canvas.property("nodeExecutionRevision")),
            bridge.node_execution_revision,
        )

        self.window.run_projection_controller.mark_node_execution_running(workspace_id, "node_exec")
        self.app.processEvents()

        self.assertEqual(graph_canvas.property("runningNodeLookup"), {"node_exec": True})
        self.assertEqual(graph_canvas.property("runningNodeLookup"), bridge.running_node_lookup)
        self.assertEqual(graph_canvas.property("completedNodeLookup"), {})
        self.assertEqual(graph_canvas.property("completedNodeLookup"), bridge.completed_node_lookup)
        self.assertEqual(
            int(graph_canvas.property("nodeExecutionRevision")),
            bridge.node_execution_revision,
        )

        self.window.run_projection_controller.mark_node_execution_settled(workspace_id, "node_exec")
        self.app.processEvents()

        self.assertEqual(graph_canvas.property("runningNodeLookup"), {})
        self.assertEqual(graph_canvas.property("runningNodeLookup"), bridge.running_node_lookup)
        self.assertEqual(graph_canvas.property("completedNodeLookup"), {"node_exec": True})
        self.assertEqual(graph_canvas.property("completedNodeLookup"), bridge.completed_node_lookup)
        self.assertEqual(
            int(graph_canvas.property("nodeExecutionRevision")),
            bridge.node_execution_revision,
        )

        self.window.run_projection_controller.clear_node_execution_visualization_state()
        self.app.processEvents()

        self.assertEqual(graph_canvas.property("runningNodeLookup"), {})
        self.assertEqual(graph_canvas.property("runningNodeLookup"), bridge.running_node_lookup)
        self.assertEqual(graph_canvas.property("completedNodeLookup"), {})
        self.assertEqual(graph_canvas.property("completedNodeLookup"), bridge.completed_node_lookup)
        self.assertEqual(
            int(graph_canvas.property("nodeExecutionRevision")),
            bridge.node_execution_revision,
        )

    def test_persistent_node_elapsed_canvas_properties_follow_graph_canvas_state_bridge(self) -> None:
        graph_canvas = self._graph_canvas_item()
        bridge = self.window.graph_canvas_state_bridge
        workspace_id = self.window.scene.workspace_id

        self.assertTrue(workspace_id)
        self.window.run_state.cached_node_elapsed_ms_by_workspace_id["ws_other"] = {
            "node_foreign": 12.0,
        }

        self.window.run_projection_controller.mark_node_execution_running(
            workspace_id,
            "node_live",
            started_at_epoch_ms=125.0,
        )
        self.window.run_projection_controller.mark_node_execution_settled(
            workspace_id,
            "node_cached",
            elapsed_ms=48.5,
        )
        self.app.processEvents()

        self.assertEqual(
            bridge.running_node_started_at_ms_lookup,
            {"node_live": 125.0},
        )
        self.assertEqual(
            bridge.node_elapsed_ms_lookup,
            {"node_cached": 48.5},
        )
        self.assertEqual(
            graph_canvas.property("runningNodeStartedAtMsLookup"),
            {"node_live": 125.0},
        )
        self.assertEqual(
            graph_canvas.property("runningNodeStartedAtMsLookup"),
            bridge.running_node_started_at_ms_lookup,
        )
        self.assertEqual(
            graph_canvas.property("nodeElapsedMsLookup"),
            {"node_cached": 48.5},
        )
        self.assertEqual(
            graph_canvas.property("nodeElapsedMsLookup"),
            bridge.node_elapsed_ms_lookup,
        )
        self.assertEqual(
            int(graph_canvas.property("nodeExecutionRevision")),
            bridge.node_execution_revision,
        )

    def test_persistent_node_elapsed_invalidation_clears_canvas_timing_lookups_after_history_commit(self) -> None:
        graph_canvas = self._graph_canvas_item()
        bridge = self.window.graph_canvas_state_bridge
        workspace_id = self.window.scene.workspace_id

        self.assertTrue(workspace_id)
        runner_id = self.window.scene.add_node_from_type("core.constant", x=20.0, y=20.0)
        logger_id = self.window.scene.add_node_from_type("core.logger", x=260.0, y=40.0)
        self.window.runtime_history.clear_workspace(workspace_id)
        self.window.run_state.node_execution_workspace_id = ""
        self.window.run_state.running_node_ids.clear()
        self.window.run_state.completed_node_ids.clear()
        self.window.run_state.running_node_started_at_epoch_ms_by_node_id.clear()
        self.window.run_state.cached_node_elapsed_ms_by_workspace_id.clear()
        self.window.run_state.cached_node_elapsed_ms_by_workspace_id["ws_other"] = {
            "node_foreign": 12.0,
        }
        self.window.run_projection_controller.mark_node_execution_running(
            workspace_id,
            runner_id,
            started_at_epoch_ms=125.0,
        )
        self.window.run_projection_controller.mark_node_execution_settled(
            workspace_id,
            logger_id,
            elapsed_ms=48.5,
        )
        self.app.processEvents()

        first_revision = bridge.node_execution_revision
        self.assertEqual(
            graph_canvas.property("runningNodeStartedAtMsLookup"),
            {runner_id: 125.0},
        )
        self.assertEqual(
            graph_canvas.property("nodeElapsedMsLookup"),
            {logger_id: 48.5},
        )

        self.window.scene.set_node_property(logger_id, "message", "Invalidate cached elapsed")
        self.app.processEvents()

        self.assertGreater(bridge.node_execution_revision, first_revision)
        self.assertEqual(bridge.running_node_started_at_ms_lookup, {runner_id: 125.0})
        self.assertEqual(bridge.node_elapsed_ms_lookup, {})
        self.assertEqual(graph_canvas.property("runningNodeStartedAtMsLookup"), {runner_id: 125.0})
        self.assertEqual(graph_canvas.property("nodeElapsedMsLookup"), {})
        self.assertNotIn("ws_other", self.window.run_state.cached_node_elapsed_ms_by_workspace_id)


class MainWindowShellHostFacadeDelegationTests(SharedMainWindowShellTestBase):
    def test_host_slot_delegates_app_dialog_to_shell_host_presenter(self) -> None:
        self.assertIsNotNone(self.window.shell_host_presenter)

        with patch.object(
            self.window.shell_host_presenter,
            "show_graphics_settings_dialog",
        ) as show_graphics_mock:
            self.window.show_graphics_settings_dialog()

        show_graphics_mock.assert_called_once_with(False)

    def test_shell_window_addon_facade_and_run_projection_owner_are_direct(self) -> None:
        self.assertFalse(hasattr(self.window, "mark_node_execution_running"))
        self.assertFalse(
            hasattr(self.window, "clear_node_execution_visualization_state")
        )
        self.assertFalse(hasattr(self.window, "_handle_execution_event"))
        self.assertFalse(hasattr(self.window, "_run_workflow"))
        self.assertIs(
            self.window.run_event_controller,
            self.window.shell_services.controllers.run_event_controller,
        )
        with (
            patch.object(self.window.addon_manager_controller, "request_open") as open_addon_mock,
            patch.object(self.window.addon_manager_controller, "request_close") as close_addon_mock,
            patch.object(
                self.window.run_projection_controller,
                "mark_node_execution_running",
            ) as mark_running_mock,
            patch.object(
                self.window.run_projection_controller,
                "clear_node_execution_visualization_state",
            ) as clear_execution_mock,
        ):
            self.window.request_open_addon_manager(TABULAR_DATA_ADDON_ID)
            self.window.request_close_addon_manager()
            self.window.run_projection_controller.mark_node_execution_running(
                "workspace-1", "node-1", started_at_epoch_ms=12.5
            )
            self.window.run_projection_controller.clear_node_execution_visualization_state()

        open_addon_mock.assert_called_once_with(TABULAR_DATA_ADDON_ID)
        close_addon_mock.assert_called_once_with()
        mark_running_mock.assert_called_once_with(
            "workspace-1",
            "node-1",
            started_at_epoch_ms=12.5,
        )
        clear_execution_mock.assert_called_once_with()


def load_tests(loader: unittest.TestLoader, _tests, _pattern):  # noqa: ANN001
    suite = unittest.TestSuite()
    explicit_case_names = (
        "FrameRateSamplerTests",
        "ShellLibraryBridgeTests",
        "ShellInspectorBridgeTests",
        "ShellWorkspaceBridgeTests",
        "MainWindowBridgeContractPacketBoundaryTests",
        "ShellWindowStateFacadeBoundaryTests",
        "ShellLibraryBridgeQmlBoundaryTests",
        "ShellInspectorBridgeQmlBoundaryTests",
        "ShellWorkspaceBridgeQmlBoundaryTests",
        "GraphCanvasQmlBoundaryTests",
        "MutationUiEffectsTests",
    )
    for case_name in explicit_case_names:
        candidate = globals().get(case_name)
        if isinstance(candidate, type):
            suite.addTests(loader.loadTestsFromTestCase(candidate))

    shell_classes: list[type[SharedMainWindowShellTestBase]] = []
    for candidate in globals().values():
        if not isinstance(candidate, type):
            continue
        if not issubclass(candidate, SharedMainWindowShellTestBase):
            continue
        if candidate is SharedMainWindowShellTestBase:
            continue
        shell_classes.append(candidate)

    for case_type in sorted(shell_classes, key=lambda item: (item.__module__, item.__name__)):
        suite.addTests(loader.loadTestsFromTestCase(case_type))
    return suite


if __name__ == "__main__":
    unittest.main()
