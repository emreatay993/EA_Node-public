from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtQuick import QQuickItem

from ea_node_editor.nodes.category_paths import category_key
from ea_node_editor.ui.shell.presenters.state import build_default_shell_workspace_ui_state
from ea_node_editor.ui.shell.presenters.workspace_presenter import ShellWorkspacePresenter
from ea_node_editor.ui.shell.state import ShellRunState
from ea_node_editor.ui_qml.shell_inspector_bridge import ShellInspectorBridge
from ea_node_editor.ui_qml.shell_library_bridge import ShellLibraryBridge
from ea_node_editor.ui_qml.shell_workspace_bridge import ShellWorkspaceBridge
from ea_node_editor.ui_qml.viewer_host_service import ViewerHostService
from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PASSIVE_IMAGE_DIRECT_ENV = "EA_NODE_EDITOR_PASSIVE_IMAGE_NODES_DIRECT"
_PASSIVE_PDF_DIRECT_ENV = "EA_NODE_EDITOR_PASSIVE_PDF_NODES_DIRECT"
_GRAPH_CANVAS_HOST_DIRECT_ENV = "EA_NODE_EDITOR_GRAPH_CANVAS_HOST_DIRECT"

pytestmark = pytest.mark.xdist_group("p03_bridge_contracts")


def _named_child_items(root: QObject, object_name: str) -> list[QQuickItem]:
    matches: list[QQuickItem] = []

    def _visit(item: QObject) -> None:
        if not isinstance(item, QQuickItem):
            return
        if item.objectName() == object_name:
            matches.append(item)
        for child in item.childItems():
            _visit(child)

    _visit(root)
    return matches


class _ShellLibraryHostStub(QObject):
    node_library_changed = pyqtSignal()
    library_pane_reset_requested = pyqtSignal(name="libraryPaneResetRequested")
    graph_search_changed = pyqtSignal()
    connection_quick_insert_changed = pyqtSignal()
    graph_hint_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.grouped_node_library_items = [
            {
                "kind": "item",
                "type_id": "core.logger",
                "display_name": "Logger",
            }
        ]
        self.display_node_library_items = list(self.grouped_node_library_items)
        self.passive_node_library_display_mode = "text"
        self.graph_search_open = True
        self.graph_search_query = "graph search"
        self.graph_search_enabled_scopes = ["title", "type", "content", "port"]
        self.graph_search_results = [{"node_id": "node-1"}]
        self.graph_search_highlight_index = 2
        self.connection_quick_insert_open = True
        self.connection_quick_insert_overlay_x = 125.5
        self.connection_quick_insert_overlay_y = 240.25
        self.connection_quick_insert_source_summary = "Logger.message [str]"
        self.connection_quick_insert_is_canvas_mode = True
        self.connection_quick_insert_query = "quick insert"
        self.connection_quick_insert_results = [{"type_id": "core.constant"}]
        self.connection_quick_insert_highlight_index = 1
        self.graph_hint_visible = True
        self.graph_hint_message = "Hint message"
        self._return_values = {
            "request_rename_custom_workflow_from_library": True,
            "request_set_custom_workflow_scope": True,
            "request_delete_custom_workflow_from_library": True,
            "request_add_node_from_library_with_properties": True,
            "request_graph_search_accept": True,
            "request_graph_search_jump": True,
            "request_connection_quick_insert_accept": True,
            "request_connection_quick_insert_choose": True,
        }

    def _record(self, name: str, *args):
        self.calls.append((name, args))
        return self._return_values.get(name)

    def set_library_query(self, query: str) -> None:
        self._record("set_library_query", query)

    def request_add_node_from_library(self, type_id: str) -> None:
        self._record("request_add_node_from_library", type_id)

    def request_add_node_from_library_with_properties(self, type_id: str, properties: dict[str, object]) -> bool:
        return bool(self._record("request_add_node_from_library_with_properties", type_id, dict(properties)))

    def request_rename_custom_workflow_from_library(self, workflow_id: str, workflow_scope: str = "") -> bool:
        return bool(self._record("request_rename_custom_workflow_from_library", workflow_id, workflow_scope))

    def request_set_custom_workflow_scope(self, workflow_id: str, workflow_scope: str) -> bool:
        return bool(self._record("request_set_custom_workflow_scope", workflow_id, workflow_scope))

    def request_delete_custom_workflow_from_library(self, workflow_id: str, workflow_scope: str = "") -> bool:
        return bool(self._record("request_delete_custom_workflow_from_library", workflow_id, workflow_scope))

    def set_graph_search_query(self, query: str) -> None:
        self._record("set_graph_search_query", query)

    def set_graph_search_scope_enabled(self, scope_id: str, enabled: bool) -> None:
        self._record("set_graph_search_scope_enabled", scope_id, enabled)

    def request_graph_search_move(self, delta: int) -> None:
        self._record("request_graph_search_move", delta)

    def request_graph_search_accept(self) -> bool:
        return bool(self._record("request_graph_search_accept"))

    def request_close_graph_search(self) -> None:
        self._record("request_close_graph_search")

    def request_graph_search_highlight(self, index: int) -> None:
        self._record("request_graph_search_highlight", index)

    def request_graph_search_jump(self, index: int) -> bool:
        return bool(self._record("request_graph_search_jump", index))

    def set_connection_quick_insert_query(self, query: str) -> None:
        self._record("set_connection_quick_insert_query", query)

    def request_connection_quick_insert_move(self, delta: int) -> None:
        self._record("request_connection_quick_insert_move", delta)

    def request_connection_quick_insert_accept(self) -> bool:
        return bool(self._record("request_connection_quick_insert_accept"))

    def request_close_connection_quick_insert(self) -> None:
        self._record("request_close_connection_quick_insert")

    def request_connection_quick_insert_highlight(self, index: int) -> None:
        self._record("request_connection_quick_insert_highlight", index)

    def request_connection_quick_insert_choose(self, index: int) -> bool:
        return bool(self._record("request_connection_quick_insert_choose", index))


class _ShellInspectorHostStub(QObject):
    selected_node_changed = pyqtSignal()
    workspace_state_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.selected_node_title = "Inspector Node"
        self.selected_node_subtitle = "Inspector subtitle"
        self.selected_node_id = "node-selected"
        self.selected_node_workspace_id = "workspace-source"
        self.selected_node_summary = "Inspector Node\nType: passive.fixture"
        self.selected_node_header_items = [{"label": "Type", "value": "passive.fixture"}]
        self.has_selected_node = True
        self.selected_node_collapsible = True
        self.selected_node_collapsed = False
        self.selected_node_is_subnode_pin = False
        self.selected_node_is_subnode_shell = True
        self.selected_node_property_items = [
            {
                "key": "message",
                "label": "Message",
                "value": "hello",
                "editor_mode": "text",
            }
        ]
        self.selected_node_port_items = [
            {
                "key": "message",
                "label": "Message",
                "direction": "in",
                "exposed": True,
            }
        ]
        self.selected_node_link_items = [
            {
                "id": "link-1",
                "kind": "url",
                "title": "Docs",
                "target": "https://example.com/docs",
                "subtitle": "Reference",
                "type_label": "Web",
                "breadcrumb": "example.com",
                "icon": "world-www",
                "type_color": "#3BA9F5",
                "index": 0,
                "can_move_up": False,
                "can_move_down": False,
            }
        ]
        self.selected_node_comment_items = [
            {
                "id": "comment-1",
                "body": "Check this node.",
                "author": "Analyst",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "resolved": False,
                "unread": True,
                "pinned": False,
                "parent_id": "",
            }
        ]
        self.selected_node_link_node_options = [
            {
                "kind": "node",
                "target": "node-target",
                "target_node_id": "node-target",
                "target_workspace_id": "workspace-target",
                "workspace_name": "Target Workspace",
                "label": "PDF2",
                "subtitle": "Target Workspace - Media - ID 2",
            }
        ]
        self.selected_node_link_workspace_options = [
            {
                "kind": "workspace",
                "target": "workspace-target",
                "target_workspace_id": "workspace-target",
                "label": "Target Workspace",
                "subtitle": "Workspace",
            }
        ]
        self.pin_data_type_options = ["any", "text"]
        self._return_values = {
            "browse_selected_node_property_path": "C:/temp/selected.txt",
            "pick_selected_node_property_color": "#AA5500",
            "set_selected_port_label": True,
            "request_ungroup_selected_nodes": True,
            "request_add_selected_subnode_pin": "port-1",
            "request_remove_selected_port": True,
            "upsert_selected_node_link": "link-1",
            "remove_selected_node_link": True,
            "move_selected_node_link": True,
            "open_selected_node_link": True,
            "upsert_selected_node_comment": "comment-1",
            "remove_selected_node_comment": True,
            "set_selected_node_comment_resolved": True,
            "set_selected_node_comment_pinned": True,
            "resolve_all_selected_node_comments": True,
            "mark_selected_node_comments_read": True,
        }

    def set_content_active(self, active: bool) -> None:
        self._record("set_content_active", active)

    def _record(self, name: str, *args):
        self.calls.append((name, args))
        return self._return_values.get(name)

    def request_add_selected_subnode_pin(self, direction: str) -> str:
        return str(self._record("request_add_selected_subnode_pin", direction) or "")

    def set_selected_port_label(self, key: str, label: str) -> bool:
        return bool(self._record("set_selected_port_label", key, label))

    def request_remove_selected_port(self, key: str) -> bool:
        return bool(self._record("request_remove_selected_port", key))

    def set_selected_node_collapsed(self, collapsed: bool) -> None:
        self._record("set_selected_node_collapsed", collapsed)

    def request_ungroup_selected_nodes(self) -> bool:
        return bool(self._record("request_ungroup_selected_nodes"))

    def set_selected_node_property(self, key: str, value: object) -> None:
        self._record("set_selected_node_property", key, value)

    def browse_selected_node_property_path(self, key: str, current_path: str) -> str:
        return str(self._record("browse_selected_node_property_path", key, current_path) or "")

    def pick_selected_node_property_color(self, key: str, current_value: str) -> str:
        return str(self._record("pick_selected_node_property_color", key, current_value) or "")

    def set_selected_port_exposed(self, key: str, exposed: bool) -> None:
        self._record("set_selected_port_exposed", key, exposed)

    def upsert_selected_node_link(
        self,
        link_id: str,
        kind: str,
        title: str,
        target: str,
        subtitle: str = "",
        target_workspace_id: str = "",
        target_node_id: str = "",
    ) -> str:
        return str(
            self._record(
                "upsert_selected_node_link",
                link_id,
                kind,
                title,
                target,
                subtitle,
                target_workspace_id,
                target_node_id,
            )
            or ""
        )

    def remove_selected_node_link(self, link_id: str) -> bool:
        return bool(self._record("remove_selected_node_link", link_id))

    def move_selected_node_link(self, link_id: str, offset: int) -> bool:
        return bool(self._record("move_selected_node_link", link_id, offset))

    def open_selected_node_link(self, link_id: str) -> bool:
        return bool(self._record("open_selected_node_link", link_id))

    def upsert_selected_node_comment(
        self,
        comment_id: str,
        body: str,
        parent_id: str = "",
        resolved: bool = False,
        unread: bool = True,
        pinned: bool = False,
    ) -> str:
        return str(
            self._record(
                "upsert_selected_node_comment",
                comment_id,
                body,
                parent_id,
                resolved,
                unread,
                pinned,
            )
            or ""
        )

    def remove_selected_node_comment(self, comment_id: str) -> bool:
        return bool(self._record("remove_selected_node_comment", comment_id))

    def set_selected_node_comment_resolved(self, comment_id: str, resolved: bool) -> bool:
        return bool(self._record("set_selected_node_comment_resolved", comment_id, resolved))

    def set_selected_node_comment_pinned(self, comment_id: str, pinned: bool) -> bool:
        return bool(self._record("set_selected_node_comment_pinned", comment_id, pinned))

    def resolve_all_selected_node_comments(self) -> bool:
        return bool(self._record("resolve_all_selected_node_comments"))

    def mark_selected_node_comments_read(self) -> bool:
        return bool(self._record("mark_selected_node_comments_read"))


class _ShellWorkspaceHostStub(QObject):
    project_meta_changed = pyqtSignal()
    workspace_state_changed = pyqtSignal()
    graphics_preferences_changed = pyqtSignal()
    run_controls_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.project_display_name = "COREX Node Editor - packet.cxproj"
        self.project_file_name = "packet.cxproj"
        self.graphics_tab_strip_density = "relaxed"
        self.shell_panel_collapsed = {
            "node_library": True,
            "property_pane": False,
            "output_panel": True,
        }
        self.active_workspace_id = "ws-2"
        self.active_workspace_can_run = True
        self.active_workspace_can_pause = False
        self.active_workspace_can_stop = False
        self.auto_run_enabled = False
        self.active_scope_breadcrumb_items = [
            {"label": "Root", "node_id": ""},
            {"label": "Scope", "node_id": "scope-node"},
        ]
        self.active_view_items = [
            {"view_id": "view-1", "label": "Main", "active": True},
            {"view_id": "view-2", "label": "Inspect", "active": False},
        ]
        self._return_values = {
            "request_open_scope_breadcrumb": True,
            "request_move_view_tab": True,
            "request_rename_view": True,
            "request_close_view": True,
            "request_move_workspace_tab": True,
            "request_rename_workspace_by_id": True,
            "request_close_workspace_by_id": True,
        }

    def _record(self, name: str, *args):
        self.calls.append((name, args))
        return self._return_values.get(name)

    def request_run_workflow(self) -> None:
        self._record("request_run_workflow")

    def request_toggle_run_pause(self) -> None:
        self._record("request_toggle_run_pause")

    def request_stop_workflow(self) -> None:
        self._record("request_stop_workflow")

    def request_toggle_auto_run(self) -> None:
        self._record("request_toggle_auto_run")

    def show_workflow_settings_dialog(self, checked: bool = False) -> None:
        self._record("show_workflow_settings_dialog", checked)

    def set_script_editor_panel_visible(self, checked: bool | None = None) -> None:
        self._record("set_script_editor_panel_visible", checked)

    def set_shell_panel_collapsed(self, panel_id: str, collapsed: bool) -> None:
        self._record("set_shell_panel_collapsed", panel_id, collapsed)

    def request_open_scope_breadcrumb(self, node_id: str) -> bool:
        return bool(self._record("request_open_scope_breadcrumb", node_id))

    def request_switch_view(self, view_id: str) -> None:
        self._record("request_switch_view", view_id)

    def request_move_view_tab(self, from_index: int, to_index: int) -> bool:
        return bool(self._record("request_move_view_tab", from_index, to_index))

    def request_rename_view(self, view_id: str) -> bool:
        return bool(self._record("request_rename_view", view_id))

    def request_close_view(self, view_id: str) -> bool:
        return bool(self._record("request_close_view", view_id))

    def request_create_view(self) -> None:
        self._record("request_create_view")

    def request_move_workspace_tab(self, from_index: int, to_index: int) -> bool:
        return bool(self._record("request_move_workspace_tab", from_index, to_index))

    def request_rename_workspace_by_id(self, workspace_id: str) -> bool:
        return bool(self._record("request_rename_workspace_by_id", workspace_id))

    def request_close_workspace_by_id(self, workspace_id: str) -> bool:
        return bool(self._record("request_close_workspace_by_id", workspace_id))

    def request_create_workspace(self) -> None:
        self._record("request_create_workspace")


def _workspace_view_stub(view_id: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(view_id=view_id, name=name)


def _workspace_stub(
    name: str,
    *,
    active_view_id: str,
    views: list[SimpleNamespace],
) -> SimpleNamespace:
    workspace = SimpleNamespace(
        name=name,
        active_view_id=active_view_id,
        views={view.view_id: view for view in views},
    )
    workspace.ensure_default_view = lambda: None
    return workspace


class _PresenterRunControllerStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def run_workflow(self) -> None:
        self.calls.append(("run_workflow", ()))

    def toggle_pause_resume(self) -> None:
        self.calls.append(("toggle_pause_resume", ()))

    def stop_workflow(self) -> None:
        self.calls.append(("stop_workflow", ()))

    def toggle_auto_run(self) -> None:
        self.calls.append(("toggle_auto_run", ()))

    def auto_run_enabled_for_workspace(self, _workspace_id: str = "") -> bool:
        return False


class _ActiveWorkspaceManagerStub:
    def __init__(self, workspace_id: str) -> None:
        self._workspace_id = str(workspace_id)

    def active_workspace_id(self) -> str:
        return self._workspace_id


class _ShellWorkspacePresenterHostStub(QObject):
    project_meta_changed = pyqtSignal()
    workspace_state_changed = pyqtSignal()
    graphics_preferences_changed = pyqtSignal()
    run_controls_changed = pyqtSignal()

    def __init__(
        self,
        *,
        active_workspace_id: str = "ws-2",
        active_run_id: str = "",
        active_run_workspace_id: str = "",
        engine_state: str = "ready",
    ) -> None:
        super().__init__()
        self.project_path = "C:/projects/presenter_packet.cxproj"
        self.workspace_ui_state = build_default_shell_workspace_ui_state()
        self.workspace_manager = _ActiveWorkspaceManagerStub(active_workspace_id)
        self.model = SimpleNamespace(
            project=SimpleNamespace(
                workspaces={
                    "ws-1": _workspace_stub(
                        "Workspace 1",
                        active_view_id="view-1",
                        views=[
                            _workspace_view_stub("view-1", "Main"),
                            _workspace_view_stub("view-2", "Inspect"),
                        ],
                    ),
                    "ws-2": _workspace_stub(
                        "Workspace 2",
                        active_view_id="view-3",
                        views=[
                            _workspace_view_stub("view-3", "Presenter"),
                        ],
                    ),
                }
            )
        )
        self.scene = SimpleNamespace(
            scope_breadcrumb_model=[
                {"label": "Root", "node_id": ""},
                {"label": "Scope", "node_id": "scope-node"},
            ],
            active_scope_path=(),
            navigate_scope_to=lambda node_id: bool(node_id),
            sync_scope_with_active_view=lambda: None,
        )
        self.run_state = ShellRunState(
            active_run_id=active_run_id,
            active_run_workspace_id=active_run_workspace_id,
            engine_state_value=engine_state,
        )
        self.run_controller = _PresenterRunControllerStub()
        self.project_session_controller = SimpleNamespace(
            save_project_as=lambda: None,
            show_workflow_settings_dialog=lambda checked=False: None,
            set_script_editor_panel_visible=lambda checked=None: None,
        )
        self.search_scope_controller = SimpleNamespace(
            navigate_scope=lambda callback: callback(),
            remember_scope_camera=lambda: None,
            restore_scope_camera=lambda: None,
            set_snap_to_grid_enabled=lambda enabled, persist=False: None,
        )
        self.search_scope_state = SimpleNamespace(
            graphics_minimap_expanded=False,
            snap_to_grid_enabled=False,
        )
        self.workspace_navigation_controller = SimpleNamespace(
            switch_view=lambda target_id: None,
            move_view=lambda from_index, to_index: True,
            rename_view=lambda view_id: True,
            close_view=lambda view_id: True,
            create_view=lambda: None,
            move_workspace=lambda from_index, to_index: True,
            rename_workspace_by_id=lambda workspace_id: True,
            close_workspace_by_id=lambda workspace_id: True,
            create_workspace=lambda: None,
        )
        self.shell_host_presenter = SimpleNamespace(apply_theme=lambda theme_id: str(theme_id or "system"))
        self.shell_inspector_presenter = SimpleNamespace(
            set_property_pane_variant=lambda variant: None,
        )
        self.graph_theme_bridge = SimpleNamespace(theme_id="system", apply_settings=lambda **kwargs: None)
class _WorkspaceTabsBridgeStub(QObject):
    tabs_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.tabs = [
            {"workspace_id": "ws-1", "label": "Workspace 1"},
            {"workspace_id": "ws-2", "label": "Workspace 2"},
        ]

    def activate_workspace(self, workspace_id: str) -> None:
        self.calls.append(("activate_workspace", (workspace_id,)))


class _ConsoleBridgeStub(QObject):
    output_changed = pyqtSignal()
    errors_changed = pyqtSignal()
    warnings_changed = pyqtSignal()
    counts_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.output_text = "stdout line"
        self.errors_text = "error line"
        self.warnings_text = "warning line"
        self.error_count_value = 3
        self.warning_count_value = 2

    def clear_all(self) -> None:
        self.calls.append(("clear_all", ()))


class _ScopeSceneBridgeStub(QObject):
    scope_changed = pyqtSignal()


class ShellLibraryBridgeTests(unittest.TestCase):
    def test_node_browser_request_carries_query_anchor_and_closes_quick_insert(self) -> None:
        host = _ShellLibraryHostStub()
        bridge = ShellLibraryBridge(shell_window=host, library_source=host)
        requests: list[tuple[str, float, float]] = []
        bridge.node_browser_requested.connect(
            lambda query, scene_x, scene_y: requests.append((query, scene_x, scene_y))
        )

        bridge.request_open_node_browser("multiply", 125.0, 240.0)

        self.assertEqual(host.calls, [("request_close_connection_quick_insert", ())])
        self.assertEqual(requests, [("multiply", 125.0, 240.0)])

    def test_bridge_nested_category_library_payload_preserves_row_and_quick_insert_metadata(self) -> None:
        host = _ShellLibraryHostStub()
        root_key = category_key(("Engineering Analysis",))
        compute_key = category_key(("Engineering Analysis", "Compute"))
        host.grouped_node_library_items = [
            {
                "kind": "category",
                "category": "Engineering Analysis",
                "category_display": "Engineering Analysis",
                "category_path": ("Engineering Analysis",),
                "category_key": root_key,
                "root_category": "Engineering Analysis",
                "label": "Engineering Analysis",
                "depth": 0,
                "ancestor_category_keys": [],
            },
            {
                "kind": "category",
                "category": "Engineering Analysis > Compute",
                "category_display": "Engineering Analysis > Compute",
                "category_path": ("Engineering Analysis", "Compute"),
                "category_key": compute_key,
                "root_category": "Engineering Analysis",
                "label": "Compute",
                "depth": 1,
                "ancestor_category_keys": [root_key],
            },
            {
                "kind": "node",
                "type_id": "fixture.compute",
                "display_name": "Compute Node",
                "category": "Engineering Analysis > Compute",
                "category_display": "Engineering Analysis > Compute",
                "category_path": ("Engineering Analysis", "Compute"),
                "category_key": compute_key,
                "root_category": "Engineering Analysis",
                "depth": 2,
                "ancestor_category_keys": [root_key, compute_key],
            },
        ]
        host.connection_quick_insert_results = [
            {
                "type_id": "fixture.compute",
                "display_name": "Compute Node",
                "category": "Engineering Analysis > Compute",
                "category_display": "Engineering Analysis > Compute",
                "category_path": ("Engineering Analysis", "Compute"),
                "category_key": compute_key,
                "root_category": "Engineering Analysis",
            }
        ]
        host.passive_node_library_display_mode = "icon"
        host.display_node_library_items = [
            host.grouped_node_library_items[0],
            {
                "kind": "passive_icon_grid",
                "category": "Engineering Analysis > Compute",
                "category_display": "Engineering Analysis > Compute",
                "category_path": ("Engineering Analysis", "Compute"),
                "category_key": compute_key,
                "root_category": "Engineering Analysis",
                "depth": 2,
                "ancestor_category_keys": [root_key, compute_key],
                "items": [
                    {
                        "kind": "node",
                        "type_id": "fixture.compute",
                        "display_name": "Compute Node",
                        "library_visual": {"kind": "flowchart_shape", "shape_id": "process"},
                    }
                ],
            },
        ]
        bridge = ShellLibraryBridge(shell_window=host, library_source=host)

        self.assertEqual(bridge.grouped_node_library_items, host.grouped_node_library_items)
        self.assertEqual(bridge.display_node_library_items, host.display_node_library_items)
        self.assertEqual(bridge.passive_node_library_display_mode, "icon")
        self.assertEqual(
            bridge.grouped_node_library_items[1]["ancestor_category_keys"],
            [root_key],
        )
        self.assertEqual(
            bridge.connection_quick_insert_results[0]["category"],
            "Engineering Analysis > Compute",
        )
        self.assertEqual(
            bridge.connection_quick_insert_results[0]["category_key"],
            compute_key,
        )

    def test_bridge_forwards_shell_library_search_state_and_actions(self) -> None:
        host = _ShellLibraryHostStub()
        bridge = ShellLibraryBridge(shell_window=host, library_source=host)

        self.assertIsNone(bridge.shell_window)
        self.assertIs(bridge.library_source, host)
        self.assertEqual(bridge.grouped_node_library_items, host.grouped_node_library_items)
        self.assertEqual(bridge.display_node_library_items, host.display_node_library_items)
        self.assertEqual(bridge.passive_node_library_display_mode, "text")
        self.assertTrue(bridge.graph_search_open)
        self.assertEqual(bridge.graph_search_query, "graph search")
        self.assertEqual(bridge.graph_search_enabled_scopes, host.graph_search_enabled_scopes)
        self.assertEqual(bridge.graph_search_results, host.graph_search_results)
        self.assertEqual(bridge.graph_search_highlight_index, 2)
        self.assertTrue(bridge.connection_quick_insert_open)
        self.assertEqual(bridge.connection_quick_insert_overlay_x, 125.5)
        self.assertEqual(bridge.connection_quick_insert_overlay_y, 240.25)
        self.assertEqual(bridge.connection_quick_insert_source_summary, "Logger.message [str]")
        self.assertTrue(bridge.connection_quick_insert_is_canvas_mode)
        self.assertEqual(bridge.connection_quick_insert_query, "quick insert")
        self.assertEqual(bridge.connection_quick_insert_results, host.connection_quick_insert_results)
        self.assertEqual(bridge.connection_quick_insert_highlight_index, 1)
        self.assertTrue(bridge.graph_hint_visible)
        self.assertEqual(bridge.graph_hint_message, "Hint message")

        bridge.set_library_query("logger")
        bridge.request_add_node_from_library("core.logger")
        self.assertTrue(bridge.request_rename_custom_workflow_from_library("wf-rename", "global"))
        self.assertTrue(bridge.request_set_custom_workflow_scope("wf-scope", "local"))
        self.assertTrue(bridge.request_delete_custom_workflow_from_library("wf-delete", "global"))
        bridge.set_graph_search_query("duplicate")
        bridge.set_graph_search_scope_enabled("content", False)
        bridge.request_graph_search_move(-1)
        self.assertTrue(bridge.request_graph_search_accept())
        bridge.request_close_graph_search()
        bridge.request_graph_search_highlight(3)
        self.assertTrue(bridge.request_graph_search_jump(4))
        bridge.set_connection_quick_insert_query("constant")
        bridge.request_connection_quick_insert_move(1)
        self.assertTrue(bridge.request_connection_quick_insert_accept())
        bridge.request_close_connection_quick_insert()
        bridge.request_connection_quick_insert_highlight(5)
        self.assertTrue(bridge.request_connection_quick_insert_choose(6))

        self.assertEqual(
            host.calls,
            [
                ("set_library_query", ("logger",)),
                ("request_add_node_from_library", ("core.logger",)),
                ("request_rename_custom_workflow_from_library", ("wf-rename", "global")),
                ("request_set_custom_workflow_scope", ("wf-scope", "local")),
                ("request_delete_custom_workflow_from_library", ("wf-delete", "global")),
                ("set_graph_search_query", ("duplicate",)),
                ("set_graph_search_scope_enabled", ("content", False)),
                ("request_graph_search_move", (-1,)),
                ("request_graph_search_accept", ()),
                ("request_close_graph_search", ()),
                ("request_graph_search_highlight", (3,)),
                ("request_graph_search_jump", (4,)),
                ("set_connection_quick_insert_query", ("constant",)),
                ("request_connection_quick_insert_move", (1,)),
                ("request_connection_quick_insert_accept", ()),
                ("request_close_connection_quick_insert", ()),
                ("request_connection_quick_insert_highlight", (5,)),
                ("request_connection_quick_insert_choose", (6,)),
            ],
        )

    def test_bridge_uses_explicit_library_source_contract_when_injected(self) -> None:
        host = _ShellLibraryHostStub()
        presenter = _ShellLibraryHostStub()
        presenter.grouped_node_library_items = [
            {"kind": "item", "type_id": "core.constant", "display_name": "Constant"}
        ]
        presenter.display_node_library_items = [
            {"kind": "item", "type_id": "core.constant", "display_name": "Constant"}
        ]
        presenter.passive_node_library_display_mode = "text_icon"
        presenter.graph_search_query = "presenter search"
        presenter.connection_quick_insert_query = "presenter quick insert"
        host.shell_library_presenter = presenter

        bridge = ShellLibraryBridge(shell_window=host, library_source=presenter)

        self.assertIs(bridge.library_source, presenter)
        self.assertEqual(bridge.grouped_node_library_items, presenter.grouped_node_library_items)
        self.assertEqual(bridge.display_node_library_items, presenter.display_node_library_items)
        self.assertEqual(bridge.passive_node_library_display_mode, "text_icon")
        self.assertEqual(bridge.graph_search_query, "presenter search")
        self.assertEqual(bridge.connection_quick_insert_query, "presenter quick insert")

        bridge.set_library_query("from presenter")
        self.assertEqual(presenter.calls, [("set_library_query", ("from presenter",))])
        self.assertEqual(host.calls, [])

    def test_bridge_requires_explicit_library_source_and_does_not_discover_host_presenter(self) -> None:
        host = _ShellLibraryHostStub()
        presenter = _ShellLibraryHostStub()
        presenter.graph_search_query = "presenter search"
        host.shell_library_presenter = presenter

        with self.assertRaisesRegex(TypeError, "explicit library source contract"):
            ShellLibraryBridge(shell_window=host)

        self.assertEqual(presenter.calls, [])
        self.assertEqual(host.calls, [])

    def test_bridge_re_emits_shell_signals(self) -> None:
        host = _ShellLibraryHostStub()
        bridge = ShellLibraryBridge(shell_window=host, library_source=host)
        seen = {
            "node_library_changed": 0,
            "library_pane_reset_requested": 0,
            "graph_search_changed": 0,
            "connection_quick_insert_changed": 0,
            "graph_hint_changed": 0,
        }

        bridge.node_library_changed.connect(
            lambda: seen.__setitem__("node_library_changed", seen["node_library_changed"] + 1)
        )
        bridge.library_pane_reset_requested.connect(
            lambda: seen.__setitem__("library_pane_reset_requested", seen["library_pane_reset_requested"] + 1)
        )
        bridge.graph_search_changed.connect(
            lambda: seen.__setitem__("graph_search_changed", seen["graph_search_changed"] + 1)
        )
        bridge.connection_quick_insert_changed.connect(
            lambda: seen.__setitem__(
                "connection_quick_insert_changed",
                seen["connection_quick_insert_changed"] + 1,
            )
        )
        bridge.graph_hint_changed.connect(
            lambda: seen.__setitem__("graph_hint_changed", seen["graph_hint_changed"] + 1)
        )

        host.node_library_changed.emit()
        host.library_pane_reset_requested.emit()
        host.graph_search_changed.emit()
        host.connection_quick_insert_changed.emit()
        host.graph_hint_changed.emit()

        self.assertEqual(
            seen,
            {
                "node_library_changed": 1,
                "library_pane_reset_requested": 1,
                "graph_search_changed": 1,
                "connection_quick_insert_changed": 1,
                "graph_hint_changed": 1,
            },
        )


def test_bridge_nested_category_library_payload_preserves_row_and_quick_insert_metadata() -> None:
    case = ShellLibraryBridgeTests(
        "test_bridge_nested_category_library_payload_preserves_row_and_quick_insert_metadata"
    )
    case.test_bridge_nested_category_library_payload_preserves_row_and_quick_insert_metadata()


class ShellInspectorBridgeTests(unittest.TestCase):
    def test_bridge_forwards_inspector_content_demand(self) -> None:
        host = _ShellInspectorHostStub()
        bridge = ShellInspectorBridge(inspector_source=host)
        bridge.set_content_active(False)
        bridge.set_content_active(True)
        self.assertEqual(host.calls, [("set_content_active", (False,)), ("set_content_active", (True,))])

    def test_bridge_forwards_shell_inspector_state_and_actions(self) -> None:
        host = _ShellInspectorHostStub()
        bridge = ShellInspectorBridge(shell_window=host, inspector_source=host)

        self.assertIsNone(bridge.shell_window)
        self.assertIs(bridge.inspector_source, host)
        self.assertEqual(bridge.selected_node_title, "Inspector Node")
        self.assertEqual(bridge.selected_node_subtitle, "Inspector subtitle")
        self.assertEqual(bridge.selected_node_id, "node-selected")
        self.assertEqual(bridge.selected_node_workspace_id, "workspace-source")
        self.assertEqual(bridge.selected_node_summary, "Inspector Node\nType: passive.fixture")
        self.assertEqual(bridge.selected_node_header_items, host.selected_node_header_items)
        self.assertTrue(bridge.has_selected_node)
        self.assertTrue(bridge.selected_node_collapsible)
        self.assertFalse(bridge.selected_node_collapsed)
        self.assertFalse(bridge.selected_node_is_subnode_pin)
        self.assertTrue(bridge.selected_node_is_subnode_shell)
        self.assertEqual(bridge.selected_node_property_items, host.selected_node_property_items)
        self.assertEqual(bridge.selected_node_port_items, host.selected_node_port_items)
        self.assertEqual(bridge.selected_node_link_items, host.selected_node_link_items)
        self.assertEqual(bridge.selected_node_comment_items, host.selected_node_comment_items)
        self.assertEqual(bridge.selected_node_link_node_options, host.selected_node_link_node_options)
        self.assertEqual(bridge.selected_node_link_workspace_options, host.selected_node_link_workspace_options)
        self.assertEqual(bridge.pin_data_type_options, host.pin_data_type_options)

        self.assertEqual(bridge.request_add_selected_subnode_pin("out"), "port-1")
        self.assertTrue(bridge.set_selected_port_label("payload", "Renamed Input"))
        self.assertTrue(bridge.request_remove_selected_port("payload"))
        bridge.set_selected_node_collapsed(True)
        self.assertTrue(bridge.request_ungroup_selected_nodes())
        bridge.set_selected_node_property("message", "updated from bridge")
        self.assertEqual(
            bridge.browse_selected_node_property_path("source_path", "C:/temp"),
            "C:/temp/selected.txt",
        )
        self.assertEqual(
            bridge.pick_selected_node_property_color("accent_color", "#336699"),
            "#AA5500",
        )
        bridge.set_selected_port_exposed("payload", False)
        self.assertEqual(
            bridge.upsert_selected_node_link(
                "",
                "url",
                "Docs",
                "https://example.com/docs",
                "Reference",
            ),
            "link-1",
        )
        self.assertEqual(
            bridge.upsert_selected_node_link(
                "",
                "node",
                "PDF2",
                "node-target",
                "Target Workspace - Media - ID 2",
                "workspace-target",
                "node-target",
            ),
            "link-1",
        )
        self.assertTrue(bridge.remove_selected_node_link("link-1"))
        self.assertTrue(bridge.move_selected_node_link("link-1", 1))
        self.assertTrue(bridge.open_selected_node_link("link-1"))
        self.assertEqual(
            bridge.upsert_selected_node_comment(
                "",
                "Check this node.",
                "",
                False,
                True,
                False,
            ),
            "comment-1",
        )
        self.assertTrue(bridge.remove_selected_node_comment("comment-1"))
        self.assertTrue(bridge.set_selected_node_comment_resolved("comment-1", True))
        self.assertTrue(bridge.set_selected_node_comment_pinned("comment-1", True))
        self.assertTrue(bridge.resolve_all_selected_node_comments())
        self.assertTrue(bridge.mark_selected_node_comments_read())

        self.assertEqual(
            host.calls,
            [
                ("request_add_selected_subnode_pin", ("out",)),
                ("set_selected_port_label", ("payload", "Renamed Input")),
                ("request_remove_selected_port", ("payload",)),
                ("set_selected_node_collapsed", (True,)),
                ("request_ungroup_selected_nodes", ()),
                ("set_selected_node_property", ("message", "updated from bridge")),
                ("browse_selected_node_property_path", ("source_path", "C:/temp")),
                ("pick_selected_node_property_color", ("accent_color", "#336699")),
                ("set_selected_port_exposed", ("payload", False)),
                (
                    "upsert_selected_node_link",
                    ("", "url", "Docs", "https://example.com/docs", "Reference", "", ""),
                ),
                (
                    "upsert_selected_node_link",
                    (
                        "",
                        "node",
                        "PDF2",
                        "node-target",
                        "Target Workspace - Media - ID 2",
                        "workspace-target",
                        "node-target",
                    ),
                ),
                ("remove_selected_node_link", ("link-1",)),
                ("move_selected_node_link", ("link-1", 1)),
                ("open_selected_node_link", ("link-1",)),
                ("upsert_selected_node_comment", ("", "Check this node.", "", False, True, False)),
                ("remove_selected_node_comment", ("comment-1",)),
                ("set_selected_node_comment_resolved", ("comment-1", True)),
                ("set_selected_node_comment_pinned", ("comment-1", True)),
                ("resolve_all_selected_node_comments", ()),
                ("mark_selected_node_comments_read", ()),
            ],
        )

    def test_bridge_uses_explicit_inspector_source_contract_when_injected(self) -> None:
        host = _ShellInspectorHostStub()
        presenter = _ShellInspectorHostStub()
        presenter.selected_node_title = "Presenter Node"
        presenter.selected_node_property_items = [
            {"key": "message", "label": "Message", "value": "from presenter", "editor_mode": "text"}
        ]
        host.shell_inspector_presenter = presenter

        bridge = ShellInspectorBridge(shell_window=host, inspector_source=presenter)

        self.assertIs(bridge.inspector_source, presenter)
        self.assertEqual(bridge.selected_node_title, "Presenter Node")
        self.assertEqual(bridge.selected_node_property_items, presenter.selected_node_property_items)

        bridge.set_selected_node_property("message", "updated")
        self.assertEqual(presenter.calls, [("set_selected_node_property", ("message", "updated"))])
        self.assertEqual(host.calls, [])

    def test_bridge_requires_explicit_inspector_source_and_does_not_discover_host_presenter(self) -> None:
        host = _ShellInspectorHostStub()
        presenter = _ShellInspectorHostStub()
        presenter.selected_node_title = "Presenter Node"
        host.shell_inspector_presenter = presenter

        with self.assertRaisesRegex(TypeError, "explicit inspector source contract"):
            ShellInspectorBridge(shell_window=host)

        self.assertEqual(presenter.calls, [])
        self.assertEqual(host.calls, [])

    def test_bridge_re_emits_shell_state_signals(self) -> None:
        host = _ShellInspectorHostStub()
        bridge = ShellInspectorBridge(shell_window=host, inspector_source=host)
        seen = {
            "selected_node_changed": 0,
            "workspace_state_changed": 0,
            "inspector_state_changed": 0,
        }

        bridge.selected_node_changed.connect(
            lambda: seen.__setitem__("selected_node_changed", seen["selected_node_changed"] + 1)
        )
        bridge.workspace_state_changed.connect(
            lambda: seen.__setitem__("workspace_state_changed", seen["workspace_state_changed"] + 1)
        )
        bridge.inspector_state_changed.connect(
            lambda: seen.__setitem__("inspector_state_changed", seen["inspector_state_changed"] + 1)
        )

        host.selected_node_changed.emit()
        host.workspace_state_changed.emit()

        self.assertEqual(
            seen,
            {
                "selected_node_changed": 1,
                "workspace_state_changed": 1,
                "inspector_state_changed": 2,
            },
        )


class SharedUiSupportBoundaryTests(unittest.TestCase):
    def test_packet_owned_shared_helpers_route_through_neutral_ui_support_module(self) -> None:
        expectations = {
            "ea_node_editor/ui_qml/graph_scene_payload/factory.py": (
                (
                    "from ea_node_editor.ui.shell.window_library_inspector import build_inline_property_items",
                ),
                (
                    "from ea_node_editor.ui.support.node_presentation import (",
                    "build_inline_property_items",
                ),
            ),
            "ea_node_editor/ui/shell/controllers/workspace_view_nav_ops.py": (
                (
                    "from ea_node_editor.ui.shell.window_library_inspector import build_user_facing_node_instance_number",
                ),
                (
                    "from ea_node_editor.ui.support.node_presentation import build_user_facing_node_instance_number",
                ),
            ),
            "ea_node_editor/ui/shell/inspector_projection.py": (
                (),
                (
                    "from ea_node_editor.ui.support.node_presentation import (",
                    "build_inline_property_items",
                    "build_user_facing_node_instance_number",
                ),
            ),
        }

        for relative_path, (absent_snippets, present_snippets) in expectations.items():
            module_text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for snippet in absent_snippets:
                with self.subTest(path=relative_path, snippet=snippet, expectation="absent"):
                    self.assertNotIn(snippet, module_text)
            for snippet in present_snippets:
                with self.subTest(path=relative_path, snippet=snippet, expectation="present"):
                    self.assertIn(snippet, module_text)


class ShellWorkspaceBridgeTests(unittest.TestCase):
    def test_bridge_forwards_workspace_run_title_and_console_concerns(self) -> None:
        host = _ShellWorkspaceHostStub()
        tabs_bridge = _WorkspaceTabsBridgeStub()
        console_bridge = _ConsoleBridgeStub()
        scene_bridge = _ScopeSceneBridgeStub()
        bridge = ShellWorkspaceBridge(
            shell_window=host,
            workspace_source=host,
            scene_bridge=scene_bridge,
            console_bridge=console_bridge,
            workspace_tabs_bridge=tabs_bridge,
        )

        self.assertIs(bridge.shell_window, host)
        self.assertIs(bridge.workspace_source, host)
        self.assertIs(bridge.scene_bridge, scene_bridge)
        self.assertIs(bridge.console_bridge, console_bridge)
        self.assertIs(bridge.workspace_tabs_bridge, tabs_bridge)
        self.assertEqual(bridge.project_display_name, "COREX Node Editor - packet.cxproj")
        self.assertEqual(bridge.project_file_name, "packet.cxproj")
        self.assertEqual(bridge.graphics_tab_strip_density, "relaxed")
        self.assertEqual(
            bridge.shell_panel_collapsed,
            {
                "node_library": True,
                "property_pane": False,
                "output_panel": True,
            },
        )
        self.assertEqual(bridge.active_workspace_id, "ws-2")
        self.assertEqual(
            bridge.active_scope_breadcrumb_items,
            host.active_scope_breadcrumb_items,
        )
        self.assertEqual(bridge.active_view_items, host.active_view_items)
        self.assertTrue(bridge.active_workspace_can_run)
        self.assertFalse(bridge.active_workspace_can_pause)
        self.assertFalse(bridge.active_workspace_can_stop)
        self.assertFalse(bridge.auto_run_enabled)
        self.assertEqual(bridge.workspace_tabs, tabs_bridge.tabs)
        self.assertEqual(bridge.output_text, "stdout line")
        self.assertEqual(bridge.errors_text, "error line")
        self.assertEqual(bridge.warnings_text, "warning line")
        self.assertEqual(bridge.error_count_value, 3)
        self.assertEqual(bridge.warning_count_value, 2)

        bridge.request_run_workflow()
        bridge.request_toggle_run_pause()
        bridge.request_stop_workflow()
        bridge.request_toggle_auto_run()
        bridge.show_workflow_settings_dialog()
        bridge.show_workflow_settings_dialog(True)
        bridge.set_script_editor_panel_visible()
        bridge.set_script_editor_panel_visible(False)
        bridge.set_shell_panel_collapsed("property_pane", True)
        self.assertTrue(bridge.request_open_scope_breadcrumb("scope-node"))
        bridge.request_switch_view("view-2")
        self.assertTrue(bridge.request_move_view_tab(0, 1))
        self.assertTrue(bridge.request_rename_view("view-2"))
        self.assertTrue(bridge.request_close_view("view-1"))
        bridge.request_create_view()
        bridge.activate_workspace("ws-1")
        self.assertTrue(bridge.request_move_workspace_tab(1, 0))
        self.assertTrue(bridge.request_rename_workspace_by_id("ws-1"))
        self.assertTrue(bridge.request_close_workspace_by_id("ws-1"))
        bridge.request_create_workspace()
        bridge.clear_all()

        self.assertEqual(
            host.calls,
            [
                ("request_run_workflow", ()),
                ("request_toggle_run_pause", ()),
                ("request_stop_workflow", ()),
                ("request_toggle_auto_run", ()),
                ("show_workflow_settings_dialog", (False,)),
                ("show_workflow_settings_dialog", (True,)),
                ("set_script_editor_panel_visible", (None,)),
                ("set_script_editor_panel_visible", (False,)),
                ("set_shell_panel_collapsed", ("property_pane", True)),
                ("request_open_scope_breadcrumb", ("scope-node",)),
                ("request_switch_view", ("view-2",)),
                ("request_move_view_tab", (0, 1)),
                ("request_rename_view", ("view-2",)),
                ("request_close_view", ("view-1",)),
                ("request_create_view", ()),
                ("request_move_workspace_tab", (1, 0)),
                ("request_rename_workspace_by_id", ("ws-1",)),
                ("request_close_workspace_by_id", ("ws-1",)),
                ("request_create_workspace", ()),
            ],
        )
        self.assertEqual(
            tabs_bridge.calls,
            [("activate_workspace", ("ws-1",))],
        )
        self.assertEqual(console_bridge.calls, [("clear_all", ())])

    def test_bridge_uses_explicit_workspace_source_contract_when_injected(self) -> None:
        host = _ShellWorkspaceHostStub()
        presenter_host = _ShellWorkspacePresenterHostStub(
            active_workspace_id="ws-2",
            active_run_id="run-1",
            active_run_workspace_id="ws-2",
            engine_state="paused",
        )
        presenter = ShellWorkspacePresenter(presenter_host)
        host.shell_workspace_presenter = presenter
        tabs_bridge = _WorkspaceTabsBridgeStub()
        console_bridge = _ConsoleBridgeStub()
        scene_bridge = _ScopeSceneBridgeStub()

        bridge = ShellWorkspaceBridge(
            shell_window=host,
            workspace_source=presenter,
            scene_bridge=scene_bridge,
            console_bridge=console_bridge,
            workspace_tabs_bridge=tabs_bridge,
        )

        self.assertIs(bridge.workspace_source, presenter)
        self.assertEqual(presenter.project_display_name, "COREX Node Editor - presenter_packet.cxproj")
        self.assertEqual(presenter.project_file_name, "presenter_packet.cxproj")
        self.assertFalse(presenter.active_workspace_can_run)
        self.assertTrue(presenter.active_workspace_can_pause)
        self.assertTrue(presenter.active_workspace_can_stop)
        self.assertEqual(bridge.project_display_name, presenter.project_display_name)
        self.assertEqual(bridge.project_file_name, presenter.project_file_name)
        self.assertEqual(bridge.active_view_items, presenter.active_view_items)
        self.assertFalse(bridge.active_workspace_can_run)
        self.assertTrue(bridge.active_workspace_can_pause)
        self.assertTrue(bridge.active_workspace_can_stop)
        self.assertFalse(bridge.auto_run_enabled)

        seen = {"presenter": 0, "bridge": 0}
        presenter.run_controls_changed.connect(
            lambda: seen.__setitem__("presenter", seen["presenter"] + 1)
        )
        bridge.run_controls_changed.connect(
            lambda: seen.__setitem__("bridge", seen["bridge"] + 1)
        )
        presenter_host.run_state.active_run_workspace_id = "ws-1"
        presenter_host.run_controls_changed.emit()

        self.assertEqual(seen, {"presenter": 1, "bridge": 1})
        self.assertTrue(bridge.active_workspace_can_run)
        self.assertFalse(bridge.active_workspace_can_pause)
        self.assertFalse(bridge.active_workspace_can_stop)

        bridge.request_run_workflow()
        bridge.request_toggle_auto_run()
        self.assertEqual(
            presenter_host.run_controller.calls,
            [("run_workflow", ()), ("toggle_auto_run", ())],
        )
        self.assertEqual(host.calls, [])

    def test_bridge_requires_explicit_workspace_source_and_does_not_discover_host_presenter(self) -> None:
        host = _ShellWorkspaceHostStub()
        presenter_host = _ShellWorkspacePresenterHostStub(
            active_workspace_id="ws-1",
            active_run_id="run-1",
            active_run_workspace_id="ws-2",
            engine_state="running",
        )
        presenter = ShellWorkspacePresenter(presenter_host)
        host.shell_workspace_presenter = presenter
        tabs_bridge = _WorkspaceTabsBridgeStub()
        console_bridge = _ConsoleBridgeStub()
        scene_bridge = _ScopeSceneBridgeStub()

        with self.assertRaisesRegex(TypeError, "explicit workspace source contract"):
            ShellWorkspaceBridge(
                shell_window=host,
                scene_bridge=scene_bridge,
                console_bridge=console_bridge,
                workspace_tabs_bridge=tabs_bridge,
            )

        self.assertEqual(presenter_host.run_controller.calls, [])
        self.assertEqual(host.calls, [])

    def test_bridge_re_emits_workspace_and_console_signals(self) -> None:
        host = _ShellWorkspaceHostStub()
        tabs_bridge = _WorkspaceTabsBridgeStub()
        console_bridge = _ConsoleBridgeStub()
        scene_bridge = _ScopeSceneBridgeStub()
        bridge = ShellWorkspaceBridge(
            shell_window=host,
            workspace_source=host,
            scene_bridge=scene_bridge,
            console_bridge=console_bridge,
            workspace_tabs_bridge=tabs_bridge,
        )
        seen = {
            "project_meta_changed": 0,
            "workspace_state_changed": 0,
            "graphics_preferences_changed": 0,
            "run_controls_changed": 0,
            "workspace_tabs_changed": 0,
            "console_output_changed": 0,
            "console_errors_changed": 0,
            "console_warnings_changed": 0,
            "console_counts_changed": 0,
        }

        bridge.project_meta_changed.connect(
            lambda: seen.__setitem__("project_meta_changed", seen["project_meta_changed"] + 1)
        )
        bridge.workspace_state_changed.connect(
            lambda: seen.__setitem__("workspace_state_changed", seen["workspace_state_changed"] + 1)
        )
        bridge.graphics_preferences_changed.connect(
            lambda: seen.__setitem__(
                "graphics_preferences_changed",
                seen["graphics_preferences_changed"] + 1,
            )
        )
        bridge.run_controls_changed.connect(
            lambda: seen.__setitem__("run_controls_changed", seen["run_controls_changed"] + 1)
        )
        bridge.workspace_tabs_changed.connect(
            lambda: seen.__setitem__("workspace_tabs_changed", seen["workspace_tabs_changed"] + 1)
        )
        bridge.console_output_changed.connect(
            lambda: seen.__setitem__("console_output_changed", seen["console_output_changed"] + 1)
        )
        bridge.console_errors_changed.connect(
            lambda: seen.__setitem__("console_errors_changed", seen["console_errors_changed"] + 1)
        )
        bridge.console_warnings_changed.connect(
            lambda: seen.__setitem__("console_warnings_changed", seen["console_warnings_changed"] + 1)
        )
        bridge.console_counts_changed.connect(
            lambda: seen.__setitem__("console_counts_changed", seen["console_counts_changed"] + 1)
        )

        host.project_meta_changed.emit()
        host.workspace_state_changed.emit()
        host.graphics_preferences_changed.emit()
        host.run_controls_changed.emit()
        scene_bridge.scope_changed.emit()
        tabs_bridge.tabs_changed.emit()
        console_bridge.output_changed.emit()
        console_bridge.errors_changed.emit()
        console_bridge.warnings_changed.emit()
        console_bridge.counts_changed.emit()

        self.assertEqual(
            seen,
            {
                "project_meta_changed": 1,
                "workspace_state_changed": 2,
                "graphics_preferences_changed": 1,
                "run_controls_changed": 1,
                "workspace_tabs_changed": 1,
                "console_output_changed": 1,
                "console_errors_changed": 1,
                "console_warnings_changed": 1,
                "console_counts_changed": 1,
            },
        )


ShellLibraryBridgeTests.__test__ = False
ShellInspectorBridgeTests.__test__ = False
SharedUiSupportBoundaryTests.__test__ = False
ShellWorkspaceBridgeTests.__test__ = False


__all__ = [
    "ShellLibraryBridgeTests",
    "ShellInspectorBridgeTests",
    "SharedUiSupportBoundaryTests",
    "ShellWorkspaceBridgeTests",
]
