from __future__ import annotations

import ast
import re
import unittest
from dataclasses import fields
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ea_node_editor.ui.shell.controllers.graph_action_controller import GraphActionController
from ea_node_editor.ui.shell.graph_action_contracts import (
    GRAPH_ACTION_IDS,
    GRAPH_ACTION_SPECS,
    LOW_LEVEL_QML_ACTION_EXCEPTIONS,
    GraphActionId,
    GraphActionSpec,
    graph_action_metadata,
    graph_action_spec,
    normalize_graph_action_payload,
)
from ea_node_editor.platform_paths import default_user_desktop_path
from ea_node_editor.ui.folder_explorer import FolderExplorerFilesystemService
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_action_bridge import GraphActionBridge


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_MENUS_QML = (
    REPO_ROOT
    / "ea_node_editor"
    / "ui_qml"
    / "components"
    / "graph_canvas"
    / "GraphCanvasContextMenus.qml"
)
NODE_DELEGATE_QML = (
    REPO_ROOT
    / "ea_node_editor"
    / "ui_qml"
    / "components"
    / "graph_canvas"
    / "GraphCanvasNodeDelegate.qml"
)
INPUT_LAYERS_QML = (
    REPO_ROOT
    / "ea_node_editor"
    / "ui_qml"
    / "components"
    / "graph_canvas"
    / "GraphCanvasInputLayers.qml"
)
ACTION_ROUTER_QML = (
    REPO_ROOT
    / "ea_node_editor"
    / "ui_qml"
    / "components"
    / "graph_canvas"
    / "GraphCanvasActionRouter.qml"
)
ACTION_PRESENTATION_JS = (
    REPO_ROOT
    / "ea_node_editor"
    / "ui_qml"
    / "components"
    / "graph"
    / "GraphActionPresentation.js"
)
GRAPH_ACTION_CONTROLLER = (
    REPO_ROOT
    / "ea_node_editor"
    / "ui"
    / "shell"
    / "controllers"
    / "graph_action_controller.py"
)
SELECTION_ENVELOPE_OVERLAY_QML = (
    REPO_ROOT
    / "ea_node_editor"
    / "ui_qml"
    / "components"
    / "graph"
    / "overlay"
    / "GraphSelectionEnvelopeOverlay.qml"
)
WINDOW_ACTIONS = REPO_ROOT / "ea_node_editor" / "ui" / "shell" / "window_actions.py"
WORKSPACE_GRAPH_ACTIONS = (
    REPO_ROOT
    / "ea_node_editor"
    / "ui"
    / "shell"
    / "window_state"
    / "workspace_graph_actions.py"
)

RETIRED_QML_COMMAND_BRIDGE_ACTION_SLOTS = {
    "request_edit_flow_edge_style",
    "request_edit_flow_edge_label",
    "request_reset_flow_edge_style",
    "request_copy_flow_edge_style",
    "request_paste_flow_edge_style",
    "request_remove_edge",
    "request_publish_custom_workflow_from_node",
    "request_open_comment_peek",
    "request_edit_passive_node_style",
    "request_reset_passive_node_style",
    "request_copy_passive_node_style",
    "request_paste_passive_node_style",
    "request_propagate_passive_node_style",
    "request_ungroup_node",
    "request_remove_node",
    "request_duplicate_node",
    "request_wrap_selected_nodes_in_group_backdrop",
}
P03_RETIRED_SHELL_GRAPH_ACTION_FACADE_SLOTS = {
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
P03_RETIRED_QML_GRAPH_ACTION_ALIASES = {
    "open_addon_manager",
    "enter_subnode",
    "add_to_workflows",
    "peek_comment",
    "exit_comment_peek",
    "edit_node_style",
    "reset_node_style",
    "copy_node_style",
    "paste_node_style",
    "show_help",
    "ungroup_subnode",
    "edit_flow_edge",
    "edit_edge_label",
    "wrap_into_frame",
    "enterScope",
    "rename",
    "delete",
    "duplicate",
}
P03_RETIRED_FOLDER_EXPLORER_COMMAND_ALIASES = {
    "list",
    "navigate",
    "refresh",
    "setSort",
    "setSearch",
    "open",
    "openInNewWindow",
    "newFolder",
    "rename",
    "delete",
    "cut",
    "copy",
    "paste",
    "copyPath",
    "properties",
    "sendToCorexPathPointer",
}

FOLDER_EXPLORER_ACTION_PAYLOAD_KEYS = {
    GraphActionId.FOLDER_EXPLORER_LIST: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_NAVIGATE: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_REFRESH: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_SET_SORT: ("node_id", "path", "sort_key"),
    GraphActionId.FOLDER_EXPLORER_SET_SEARCH: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_OPEN: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_OPEN_WITH: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_OPEN_IN_NEW_WINDOW: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_NEW_FOLDER: ("node_id", "path", "name"),
    GraphActionId.FOLDER_EXPLORER_RENAME: ("node_id", "path", "new_name"),
    GraphActionId.FOLDER_EXPLORER_DELETE: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_CUT: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_COPY: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_PASTE: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_COPY_PATH: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_PROPERTIES: ("node_id", "path"),
    GraphActionId.FOLDER_EXPLORER_SEND_TO_COREX_PATH_POINTER: ("node_id", "path"),
}


class _GraphActionSource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.backdrop_nodes_model: list[dict[str, object]] = []
        self.nodes_model = [
            {
                "node_id": "locked-node",
                "addon_id": "addon.from-node",
                "locked_state": {"focus_addon_id": "addon.from-lock"},
            }
        ]

    def _record(self, name: str, *args: object) -> bool:
        self.calls.append((name, args))
        return True

    def copy_selected_nodes_to_clipboard(self) -> bool:
        return self._record("copy_selected_nodes_to_clipboard")

    def align_selection_left(self) -> bool:
        return self._record("align_selection_left")

    def set_selection_same_type_width(self, node_ids: tuple[str, ...]) -> bool:
        return self._record("set_selection_same_type_width", node_ids)

    def set_selection_same_type_height(self, node_ids: tuple[str, ...]) -> bool:
        return self._record("set_selection_same_type_height", node_ids)

    def straighten_selection_connections(self) -> bool:
        return self._record("straighten_selection_connections")

    def request_delete_selected_graph_items(self, edge_ids: list[object]):  # noqa: ANN201
        return SimpleNamespace(
            payload=self._record("request_delete_selected_graph_items", edge_ids)
        )

    def open_subnode_scope(self, node_id: str) -> bool:
        return self._record("open_subnode_scope", node_id)

    def request_publish_custom_workflow_from_node(self, node_id: str) -> bool:
        return self._record("request_publish_custom_workflow_from_node", node_id)

    def publish_custom_workflow_from_node(self, node_id: str):  # noqa: ANN201
        return SimpleNamespace(
            payload=self._record("publish_custom_workflow_from_node", node_id)
        )

    def open_comment_peek(self, node_id: str) -> bool:
        return self._record("open_comment_peek", node_id)

    def close_comment_peek(self) -> bool:
        return self._record("close_comment_peek")

    def requestOpen(self, focus_addon_id: str) -> None:  # noqa: N802
        self.calls.append(("requestOpen", (focus_addon_id,)))

    def request_edit_flow_edge_style(self, edge_id: str) -> bool:
        return self._record("request_edit_flow_edge_style", edge_id)

    def request_remove_edge(self, edge_id: str) -> bool:
        return self._record("request_remove_edge", edge_id)

    def request_propagate_passive_node_style(self, node_id: str) -> bool:
        return self._record("request_propagate_passive_node_style", node_id)

    def run_selected_nodes(self, node_ids=None) -> bool:  # noqa: ANN001
        return self._record("run_selected_nodes", tuple(node_ids or ()))

    def preview_selected_run(self, node_ids=None) -> bool:  # noqa: ANN001
        return self._record("preview_selected_run", tuple(node_ids or ()))

    def open_selected_run_settings(self) -> bool:
        return self._record("open_selected_run_settings")

    def confirm_selected_run_preview(self) -> bool:
        return self._record("confirm_selected_run_preview")

    def clear_selected_run_preview(self) -> bool:
        return self._record("clear_selected_run_preview")


class _CommentPeekScene:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.active_comment_peek_node_id = ""

    def can_open_comment_peek(self, node_id: str) -> bool:
        self.calls.append(("can_open_comment_peek", (node_id,)))
        return node_id == "comment-1"

    def open_comment_peek(self, node_id: str) -> bool:
        self.calls.append(("open_comment_peek", (node_id,)))
        if node_id != "comment-1":
            return False
        self.active_comment_peek_node_id = node_id
        return True

    def close_comment_peek(self) -> bool:
        self.calls.append(("close_comment_peek", ()))
        if not self.active_comment_peek_node_id:
            return False
        self.active_comment_peek_node_id = ""
        return True


class GraphActionBridgeDelegationTests(unittest.TestCase):
    def test_graph_action_controller_delegates_representative_action_families(self) -> None:
        workspace = _GraphActionSource()
        host_presenter = _GraphActionSource()
        workflow = _GraphActionSource()
        scene = _GraphActionSource()
        addon_manager = _GraphActionSource()
        controller = GraphActionController(
            workspace_edit_controller=workspace,
            workflow_library_controller=workflow,
            search_scope_controller=SimpleNamespace(
                navigate_scope=lambda callback: callback()
            ),
            graph_canvas_host_presenter=host_presenter,
            scene_bridge=scene,
            addon_manager_bridge=addon_manager,
        )

        self.assertFalse(hasattr(controller, "shell_window"))
        self.assertFalse(hasattr(controller, "_shell_window"))
        self.assertTrue(controller.trigger(GraphActionId.COPY_SELECTION.value))
        self.assertTrue(controller.trigger(GraphActionId.ALIGN_SELECTION_LEFT.value))
        self.assertTrue(
            controller.trigger(
                GraphActionId.SET_SELECTION_SAME_TYPE_WIDTH.value,
                {"node_ids": ["node-1", "node-2"]},
            )
        )
        self.assertTrue(
            controller.trigger(
                GraphActionId.SET_SELECTION_SAME_TYPE_HEIGHT.value,
                {"node_ids": ["node-3", "node-4"]},
            )
        )
        self.assertTrue(controller.trigger(GraphActionId.STRAIGHTEN_SELECTION_CONNECTIONS.value))
        self.assertTrue(controller.trigger(GraphActionId.DELETE_SELECTION.value, {"edge_ids": ["edge-1"]}))
        self.assertTrue(controller.trigger(GraphActionId.OPEN_SUBNODE_SCOPE.value, {"node_id": "node-1"}))
        self.assertTrue(
            controller.trigger(GraphActionId.PUBLISH_CUSTOM_WORKFLOW_FROM_NODE.value, {"node_id": "node-2"})
        )
        self.assertTrue(controller.trigger(GraphActionId.OPEN_COMMENT_PEEK.value, {"node_id": "comment-1"}))
        self.assertTrue(controller.trigger(GraphActionId.CLOSE_COMMENT_PEEK.value))
        self.assertTrue(controller.trigger(GraphActionId.OPEN_ADDON_MANAGER_FOR_NODE.value, {"node_id": "locked-node"}))
        self.assertTrue(controller.trigger(GraphActionId.REMOVE_EDGE.value, {"edge_id": "edge-1"}))
        self.assertTrue(
            controller.trigger(GraphActionId.PROPAGATE_PASSIVE_NODE_STYLE.value, {"node_id": "node-3"})
        )

        self.assertEqual(
            workspace.calls,
            [
                ("copy_selected_nodes_to_clipboard", ()),
                ("align_selection_left", ()),
                ("set_selection_same_type_width", (("node-1", "node-2"),)),
                ("set_selection_same_type_height", (("node-3", "node-4"),)),
                ("straighten_selection_connections", ()),
                ("request_delete_selected_graph_items", (["edge-1"],)),
            ],
        )
        self.assertEqual(
            scene.calls,
            [("open_subnode_scope", ("node-1",)), ("open_comment_peek", ("comment-1",)), ("close_comment_peek", ())],
        )
        self.assertEqual(
            host_presenter.calls,
            [
                ("request_remove_edge", ("edge-1",)),
                ("request_propagate_passive_node_style", ("node-3",)),
            ],
        )
        self.assertEqual(
            workflow.calls,
            [("publish_custom_workflow_from_node", ("node-2",))],
        )
        self.assertEqual(addon_manager.calls, [("requestOpen", ("addon.from-lock",))])

    def test_graph_action_controller_routes_selected_run_actions(self) -> None:
        run_controller = _GraphActionSource()
        controller = GraphActionController(run_controller=run_controller)

        self.assertTrue(controller.trigger(GraphActionId.RUN_SELECTED.value, {"node_id": "node-1"}))
        self.assertTrue(controller.trigger(GraphActionId.PREVIEW_SELECTED_RUN.value, {"node_id": "node-3"}))
        self.assertTrue(controller.trigger(GraphActionId.OPEN_SELECTED_RUN_SETTINGS.value))
        self.assertTrue(controller.trigger(GraphActionId.CONFIRM_SELECTED_RUN_PREVIEW.value))
        self.assertTrue(controller.trigger(GraphActionId.CLEAR_SELECTED_RUN_PREVIEW.value))

        self.assertEqual(
            run_controller.calls,
            [
                ("run_selected_nodes", (("node-1",),)),
                ("preview_selected_run", (("node-3",),)),
                ("open_selected_run_settings", ()),
                ("confirm_selected_run_preview", ()),
                ("clear_selected_run_preview", ()),
            ],
        )

    def test_graph_action_controller_opens_node_path_via_platform_helpers(self) -> None:
        import ea_node_editor.ui.shell.controllers.graph_action_controller as controller_module

        class _PathPointerScene:
            backdrop_nodes_model = []
            nodes_model = [
                {
                    "node_id": "pp-1",
                    "type_id": "io.path_pointer",
                    "properties": {"path": "C:/tmp/file.txt", "mode": "file"},
                }
            ]

        class _HintPresenter:
            def __init__(self) -> None:
                self.hints: list[tuple[str, int]] = []

            def show_graph_hint(self, message: str, timeout_ms: int = 3600) -> None:
                self.hints.append((message, timeout_ms))

        presenter = _HintPresenter()
        controller = GraphActionController(
            scene_bridge=_PathPointerScene(),
            show_graph_hint=presenter.show_graph_hint,
        )

        default_calls: list[str] = []
        chooser_calls: list[str] = []
        with mock.patch.object(
            controller_module,
            "open_path_with_default_handler",
            lambda path: default_calls.append(path) or True,
        ), mock.patch.object(
            controller_module,
            "open_path_with_app_chooser",
            lambda path: chooser_calls.append(path) or True,
        ):
            self.assertTrue(controller.trigger(GraphActionId.OPEN_NODE_PATH.value, {"node_id": "pp-1"}))
            self.assertTrue(controller.trigger(GraphActionId.OPEN_NODE_PATH_WITH.value, {"node_id": "pp-1"}))

        self.assertEqual(default_calls, ["C:/tmp/file.txt"])
        self.assertEqual(chooser_calls, ["C:/tmp/file.txt"])
        self.assertEqual(presenter.hints, [])

    def test_graph_action_controller_open_node_path_hints_when_path_missing(self) -> None:
        import ea_node_editor.ui.shell.controllers.graph_action_controller as controller_module

        class _EmptyPathPointerScene:
            backdrop_nodes_model = []
            nodes_model = [
                {"node_id": "pp-1", "type_id": "io.path_pointer", "properties": {"path": ""}}
            ]

        class _HintPresenter:
            def __init__(self) -> None:
                self.hints: list[tuple[str, int]] = []

            def show_graph_hint(self, message: str, timeout_ms: int = 3600) -> None:
                self.hints.append((message, timeout_ms))

        presenter = _HintPresenter()
        controller = GraphActionController(
            scene_bridge=_EmptyPathPointerScene(),
            show_graph_hint=presenter.show_graph_hint,
        )

        opener_calls: list[str] = []
        with mock.patch.object(
            controller_module,
            "open_path_with_default_handler",
            lambda path: opener_calls.append(path) or True,
        ):
            self.assertFalse(controller.trigger(GraphActionId.OPEN_NODE_PATH.value, {"node_id": "pp-1"}))

        self.assertEqual(opener_calls, [])
        self.assertEqual(len(presenter.hints), 1)
        self.assertIn("No path", presenter.hints[0][0])

    def test_graph_action_bridge_exposes_contract_metadata_and_rejects_bad_payloads(self) -> None:
        host_presenter = _GraphActionSource()
        controller = GraphActionController(graph_canvas_host_presenter=host_presenter)
        bridge = GraphActionBridge(controller=controller)

        self.assertIn(GraphActionId.REMOVE_EDGE.value, bridge.actionIds)
        self.assertEqual(
            bridge.action_metadata(GraphActionId.EDIT_FLOW_EDGE_STYLE.value)["actionId"],
            GraphActionId.EDIT_FLOW_EDGE_STYLE.value,
        )
        self.assertEqual(bridge.action_metadata("edit_flow_edge"), {})
        self.assertEqual(
            bridge.action_metadata(GraphActionId.REMOVE_EDGE.value)["requiredPayloadKeys"],
            ["edge_id"],
        )
        self.assertTrue(bridge.trigger_graph_action("edit_flow_edge_style", {"edge_id": "edge-2"}))
        self.assertFalse(bridge.trigger_graph_action("edit_flow_edge_style", {"edge_id": ""}))
        self.assertFalse(bridge.trigger_graph_action("edit_flow_edge_style", {"edge_id": 123}))
        self.assertFalse(bridge.trigger_graph_action("not_a_graph_action", {}))
        self.assertEqual(
            host_presenter.calls,
            [("request_edit_flow_edge_style", ("edge-2",))],
        )

    def test_comment_peek_opens_via_graph_action_and_uses_command_bridge_helpers(self) -> None:
        scene = _CommentPeekScene()
        command_bridge = GraphCanvasCommandBridge(scene_bridge=scene)
        action_bridge = GraphActionBridge(
            controller=GraphActionController(scene_bridge=scene),
        )

        self.assertTrue(command_bridge.can_open_comment_peek("comment-1"))
        self.assertFalse(command_bridge.can_open_comment_peek("logger-1"))
        self.assertTrue(
            action_bridge.trigger_graph_action(
                GraphActionId.OPEN_COMMENT_PEEK.value,
                {"node_id": "comment-1"},
            )
        )
        self.assertEqual(command_bridge.active_comment_peek_node_id(), "comment-1")
        self.assertTrue(command_bridge.request_close_comment_peek())
        self.assertEqual(command_bridge.active_comment_peek_node_id(), "")
        self.assertEqual(
            scene.calls,
            [
                ("can_open_comment_peek", ("comment-1",)),
                ("can_open_comment_peek", ("logger-1",)),
                ("open_comment_peek", ("comment-1",)),
                ("close_comment_peek", ()),
            ],
        )


class _FolderExplorerConfirmationProbe:
    def __init__(self, accepted: bool) -> None:
        self.accepted = accepted
        self.calls: list[tuple[str, str, str]] = []

    def confirm_folder_explorer_operation(self, operation: str, path: str, target_path: str = "") -> bool:
        self.calls.append((operation, path, target_path))
        return self.accepted


class _FolderExplorerClipboardProbe:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:  # noqa: N802
        self.text = text


class _FolderExplorerOpenProbe:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.paths: list[str] = []

    def open_folder_explorer_path(self, path: str) -> bool:
        self.paths.append(path)
        return self.accepted


class _FolderExplorerSceneCommandProbe:
    def __init__(self, *, bulk_result: bool = True) -> None:
        self.added_nodes: list[tuple[str, float, float, str]] = []
        self.properties: list[tuple[str, str, object]] = []
        self.bulk_properties: list[tuple[str, dict[str, object]]] = []
        self.create_kwargs: list[dict[str, object]] = []
        self.bulk_result = bool(bulk_result)
        self._serial = 0

    def add_node_from_type(self, type_id: str, x: float = 0.0, y: float = 0.0) -> str:
        self._serial += 1
        node_id = f"node-{self._serial}"
        self.added_nodes.append((type_id, float(x), float(y), node_id))
        return node_id

    def set_node_property(self, node_id: str, key: str, value: object) -> None:
        self.properties.append((node_id, key, value))

    def set_node_properties(self, node_id: str, values: dict[str, object]) -> bool:
        self.bulk_properties.append((node_id, dict(values)))
        return self.bulk_result

    def create_node_from_type(self, **kwargs) -> str:  # noqa: ANN003
        self.create_kwargs.append(dict(kwargs))
        return self.add_node_from_type(
            str(kwargs["type_id"]),
            float(kwargs.get("x", 0.0)),
            float(kwargs.get("y", 0.0)),
        )


def _pyqt_graph_actions_from_contract() -> dict[str, GraphActionId]:
    return {
        "action_connect_selected": GraphActionId.CONNECT_SELECTED,
        "action_copy_selection": GraphActionId.COPY_SELECTION,
        "action_cut_selection": GraphActionId.CUT_SELECTION,
        "action_paste_selection": GraphActionId.PASTE_SELECTION,
        "action_duplicate_selection": GraphActionId.DUPLICATE_SELECTION,
        "action_wrap_selection_in_group_backdrop": GraphActionId.WRAP_SELECTION_IN_GROUP_BACKDROP,
        "action_group_selection": GraphActionId.GROUP_SELECTION,
        "action_ungroup_selection": GraphActionId.UNGROUP_SELECTION,
        "action_align_left": GraphActionId.ALIGN_SELECTION_LEFT,
        "action_align_right": GraphActionId.ALIGN_SELECTION_RIGHT,
        "action_align_top": GraphActionId.ALIGN_SELECTION_TOP,
        "action_align_bottom": GraphActionId.ALIGN_SELECTION_BOTTOM,
        "action_distribute_horizontally": GraphActionId.DISTRIBUTE_SELECTION_HORIZONTALLY,
        "action_distribute_vertically": GraphActionId.DISTRIBUTE_SELECTION_VERTICALLY,
        "action_straighten_connections": GraphActionId.STRAIGHTEN_SELECTION_CONNECTIONS,
        "action_scope_parent": GraphActionId.NAVIGATE_SCOPE_PARENT,
        "action_scope_root": GraphActionId.NAVIGATE_SCOPE_ROOT,
        "action_show_help": GraphActionId.SHOW_NODE_HELP,
    }


PYQT_GRAPH_ACTIONS: dict[str, GraphActionId] = _pyqt_graph_actions_from_contract()

PYQT_MENU_ACTION_EXCEPTIONS = {
    "action_undo",
    "action_redo",
    "action_snap_to_grid",
    "action_interact_with_locked_objects",
    "action_graph_search",
    "action_toggle_script_editor",
    "action_node_browser",
    "action_show_port_labels",
    "action_general_help_tooltips",
    "action_frame_all",
    "action_frame_selection",
    "action_center_selection",
}

STANDARD_KEY_SHORTCUTS = {
    "Copy": "Ctrl+C",
    "Cut": "Ctrl+X",
    "Paste": "Ctrl+V",
}


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _qml_context_action_ids() -> set[str]:
    return set(re.findall(r'"actionId"\s*:\s*"([^"]+)"', _source(ACTION_ROUTER_QML)))


def _qml_node_delegate_action_literals() -> set[str]:
    return set(re.findall(r'"actionId"\s*:\s*"([^"]+)"', _source(ACTION_ROUTER_QML)))


def _window_action_assignments() -> dict[str, ast.Call]:
    tree = ast.parse(_source(WINDOW_ACTIONS), filename=str(WINDOW_ACTIONS))
    assignments: dict[str, ast.Call] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if not _is_qaction_constructor(node.value):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Attribute):
                continue
            if isinstance(target.value, ast.Name) and target.value.id == "window":
                assignments[target.attr] = node.value
    return assignments


def _window_graph_action_contract_assignments() -> dict[str, GraphActionId]:
    tree = ast.parse(_source(WINDOW_ACTIONS), filename=str(WINDOW_ACTIONS))
    assignments: dict[str, GraphActionId] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Name) or call.func.id != "_create_graph_action":
            continue
        if len(call.args) != 2:
            continue
        action_id = _graph_action_id_from_ast(call.args[1])
        if action_id is None:
            continue
        for target in node.targets:
            if not isinstance(target, ast.Attribute):
                continue
            if isinstance(target.value, ast.Name) and target.value.id == "window":
                assignments[target.attr] = action_id
    return assignments


def _graph_action_id_from_ast(node: ast.AST) -> GraphActionId | None:
    if not isinstance(node, ast.Attribute):
        return None
    if not isinstance(node.value, ast.Name) or node.value.id != "GraphActionId":
        return None
    return GraphActionId[node.attr]


def _window_action_shortcuts() -> dict[str, str]:
    tree = ast.parse(_source(WINDOW_ACTIONS), filename=str(WINDOW_ACTIONS))
    shortcuts: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute):
            continue
        if call.func.attr not in {"setShortcut", "setShortcuts"}:
            continue
        owner = call.func.value
        if not isinstance(owner, ast.Attribute):
            continue
        if not isinstance(owner.value, ast.Name) or owner.value.id != "window":
            continue
        shortcut = _shortcut_from_call(call)
        if shortcut is not None:
            shortcuts[owner.attr] = shortcut
    return shortcuts


def _window_graph_menu_actions() -> set[str]:
    tree = ast.parse(_source(WINDOW_ACTIONS), filename=str(WINDOW_ACTIONS))
    actions: set[str] = set()
    graph_menu_names = {"edit_menu", "layout_menu", "view_menu"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "addAction":
            continue
        if not isinstance(call.func.value, ast.Name) or call.func.value.id not in graph_menu_names:
            continue
        if not call.args:
            continue
        action = call.args[0]
        if not isinstance(action, ast.Attribute):
            continue
        if isinstance(action.value, ast.Name) and action.value.id == "window":
            actions.add(action.attr)
    return actions - PYQT_MENU_ACTION_EXCEPTIONS


def _is_qaction_constructor(call: ast.Call) -> bool:
    return isinstance(call.func, ast.Name) and call.func.id == "QAction"


def _shortcut_from_call(call: ast.Call) -> str | None:
    if not call.args:
        return None
    first = call.args[0]
    if call.func.attr == "setShortcuts":
        return None
    if isinstance(first, ast.Attribute):
        return _standard_key_shortcut(first)
    if not isinstance(first, ast.Call):
        return None
    if not isinstance(first.func, ast.Name) or first.func.id != "QKeySequence":
        return None
    if not first.args:
        return None
    value = first.args[0]
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Attribute):
        return _standard_key_shortcut(value)
    return None


def _standard_key_shortcut(value: ast.Attribute) -> str | None:
    if not isinstance(value.value, ast.Attribute):
        return None
    if not isinstance(value.value.value, ast.Name) or value.value.value.id != "QKeySequence":
        return None
    if value.value.attr != "StandardKey":
        return None
    return STANDARD_KEY_SHORTCUTS.get(value.attr)


def _qaction_label(call: ast.Call) -> str:
    assert call.args, "QAction constructor is missing text"
    text_arg = call.args[0]
    assert isinstance(text_arg, ast.Constant) and isinstance(text_arg.value, str)
    return text_arg.value


def test_graph_action_ids_are_unique() -> None:
    ids = [spec.action_id.value for spec in GRAPH_ACTION_SPECS]
    assert len(ids) == len(set(ids))


def test_graph_action_contracts_do_not_emit_compatibility_alias_metadata() -> None:
    spec_fields = {field.name for field in fields(GraphActionSpec)}
    assert "legacy_route_names" not in spec_fields
    assert "legacy_labels" not in spec_fields

    metadata = graph_action_metadata(graph_action_spec(GraphActionId.REMOVE_EDGE))
    assert "legacyRouteNames" not in metadata
    assert "legacyLabels" not in metadata


def test_qml_action_literals_are_canonical_contract_ids() -> None:
    qml_literals = _qml_context_action_ids() | _qml_node_delegate_action_literals()
    missing = qml_literals - GRAPH_ACTION_IDS - LOW_LEVEL_QML_ACTION_EXCEPTIONS
    assert missing == set()
    assert qml_literals & P03_RETIRED_QML_GRAPH_ACTION_ALIASES == set()
    assert qml_literals & P03_RETIRED_FOLDER_EXPLORER_COMMAND_ALIASES == set()


def test_low_level_qml_action_exceptions_are_current() -> None:
    qml_literals = _qml_context_action_ids() | _qml_node_delegate_action_literals()
    assert LOW_LEVEL_QML_ACTION_EXCEPTIONS <= qml_literals


def test_qml_graph_canvas_actions_route_through_graph_action_bridge() -> None:
    canvas_source = _source(REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "GraphCanvas.qml")
    context_source = _source(CONTEXT_MENUS_QML)
    delegate_source = _source(NODE_DELEGATE_QML)
    input_layers_source = _source(INPUT_LAYERS_QML)
    action_router_source = _source(ACTION_ROUTER_QML)
    selection_envelope_source = _source(SELECTION_ENVELOPE_OVERLAY_QML)

    assert "property var graphActionBridge: null" in canvas_source
    assert "readonly property var graphActionBridgeRef: root.graphActionBridge || null" in canvas_source
    assert "GraphCanvasComponents.GraphCanvasActionRouter {" in canvas_source
    assert "readonly property var canvasActionRouter: actionRouter" in canvas_source
    assert "canvasActionRouter: root.canvasActionRouter" in canvas_source
    assert "property var graphActionBridge: null" in action_router_source
    assert "bridge.trigger_graph_action(String(actionId || \"\"), payload || ({}))" in action_router_source
    assert "property var canvasActionRouter: null" in context_source
    assert "function handleNodeContextAction(actionId)" in action_router_source
    assert "function handleEdgeContextAction(actionId)" in action_router_source
    assert "function handleEdgeToolbarAction(actionId, edgeId)" in action_router_source
    assert "function setEdgePathMode(edgeId, pathMode)" in action_router_source
    assert "function setFlowEdgeVisualStyle(edgeId, updates)" in action_router_source
    assert "function clearFlowEdgeLabel(edgeId)" in action_router_source
    assert "function handleSelectionContextAction(actionId)" in action_router_source
    assert "GraphSelectionEnvelopeOverlay" in _source(
        REPO_ROOT
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "graph_canvas"
        / "GraphCanvasRootLayers.qml"
    )
    assert "router.handleSelectionContextAction(String(actionId || \"\"))" in selection_envelope_source
    assert "actionRouter.handleNodeDelegateAction(nodeCard, nodeId, normalized)" in delegate_source
    assert "payload.inline_title_edit = true" in delegate_source
    assert "canvasItem.graphActionBridgeRef" in delegate_source
    assert "property var graphActionBridge: null" in input_layers_source
    assert "root.canvasActionRouter.deleteSelection(edgeIds)" in input_layers_source
    assert "root.canvasActionRouter.navigateScopeParent()" in input_layers_source
    assert "root.canvasActionRouter.navigateScopeRoot()" in input_layers_source
    assert "root.canvasActionRouter.navigateSelectedPdfPage" in input_layers_source
    assert "function navigateSelectedPdfPage(delta)" in action_router_source
    assert "root.canvasActionRouter.closeCommentPeekIfActive()" in input_layers_source
    assert "readonly property var shellContextRef" in context_source

    for action_id in (
        "align_selection_left",
        "align_selection_right",
        "align_selection_top",
        "align_selection_bottom",
        "distribute_selection_horizontally",
        "distribute_selection_vertically",
        "straighten_selection_connections",
        "wrap_selection_in_group_backdrop",
    ):
        assert f'"{action_id}": {{ "actionId": "{action_id}", "payload": "none" }}' in action_router_source
        assert action_id in context_source
        assert action_id in selection_envelope_source
        assert "qml_selection_context_menu" in graph_action_spec(GraphActionId(action_id)).surfaces
    for action_id in (
        "set_selection_same_type_width",
        "set_selection_same_type_height",
    ):
        assert f'"{action_id}": {{ "actionId": "{action_id}", "payload": "selection" }}' in action_router_source
        assert action_id in context_source
        assert "qml_selection_context_menu" in graph_action_spec(GraphActionId(action_id)).surfaces
        assert "qml_selection_envelope_toolbar" not in graph_action_spec(GraphActionId(action_id)).surfaces
    for action_id in (
        "run_selected",
        "preview_selected_run",
        "open_selected_run_settings",
    ):
        assert action_id in action_router_source
        assert action_id in context_source
        assert "qml_selection_context_menu" in graph_action_spec(GraphActionId(action_id)).surfaces
    assert '"run_selected": { "actionId": "run_selected", "payload": "node" }' in action_router_source
    assert '"preview_selected_run": { "actionId": "preview_selected_run", "payload": "node" }' in action_router_source
    assert (
        '"open_selected_run_settings": { "actionId": "open_selected_run_settings", "payload": "none" }'
        in action_router_source
    )
    assert '"run_selected": { "actionId": "run_selected", "payload": "selection" }' in action_router_source
    assert "run_selected_upstream_chain" not in action_router_source
    assert 'if (payloadKind === "selection")' in action_router_source
    assert '"id": "run_selected"' in selection_envelope_source
    assert "readonly property var shellContextRef" in input_layers_source
    assert "typeof viewerSessionBridge" not in delegate_source
    assert "property var shellCommandBridge" not in input_layers_source

    retired_hits = {
        slot
        for slot in RETIRED_QML_COMMAND_BRIDGE_ACTION_SLOTS
        if f".{slot}" in context_source or f".{slot}" in delegate_source
    }
    assert retired_hits == set()


def test_qml_graph_action_bridge_payloads_use_contract_keys() -> None:
    context_source = _source(CONTEXT_MENUS_QML)
    delegate_source = _source(NODE_DELEGATE_QML)
    action_router_source = _source(ACTION_ROUTER_QML)

    assert 'return edgeId.length ? { "edge_id": edgeId } : null;' in action_router_source
    assert 'return normalized.length ? { "edge_id": normalized } : null;' in action_router_source
    assert 'var payload = { "node_id": nodeId };' in action_router_source
    assert '{ "node_id": String(nodeId || "") }' in delegate_source
    assert "inline_title_edit" in action_router_source
    assert "inline_title_edit" in delegate_source


def test_active_wire_actions_use_batch_rewire_display_mode_and_endpoint_navigation() -> None:
    canvas_source = _source(REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "GraphCanvas.qml")
    context_source = _source(CONTEXT_MENUS_QML)
    input_layers_source = _source(INPUT_LAYERS_QML)
    action_router_source = _source(ACTION_ROUTER_QML)
    presentation_source = _source(ACTION_PRESENTATION_JS)
    options_source = _source(
        REPO_ROOT
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "graph_canvas"
        / "GraphCanvasOptionsMenu.qml"
    )
    interaction_source = _source(
        REPO_ROOT
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "graph_canvas"
        / "GraphCanvasInteractionState.qml"
    )

    for function_name in (
        "setEdgesDisplayMode(edgeIds, mode)",
        "edgeEndpointScenePoint(edgeId, endpoint)",
        "jumpToEdgeEndpoint(edgeId, endpoint)",
    ):
        assert f"function {function_name}" in canvas_source
    for function_name in (
        "setEdgesDisplayMode(edgeIds, mode)",
        "jumpToEdgeEndpoint(edgeId, endpoint)",
        "jumpToSelectedEdgeEndpoint(endpoint)",
    ):
        assert f"function {function_name}" in action_router_source

    assert '"edge_display_mode_menu"' in context_source
    assert 'objectName: "graphCanvasEdgeDisplayModeContextPopup"' in context_source
    assert 'var prefix = "edge_display_mode:";' in context_source
    for mode in ("default", "faint", "hidden"):
        assert f'"{mode}"' in presentation_source
    assert "GraphActionPresentation.edgeDisplayMenuActions(" in context_source
    assert '"jump_edge_start"' in context_source
    assert '"jump_edge_end"' in context_source
    assert 'activeSubmenu === "selectedWireDisplayMode"' in options_source
    assert "selectedWireDisplayModeSubmenuLoader" in options_source
    assert "Selected Wires Display Mode" in options_source

    assert "root.shellBridge.request_rewire_edges(" in interaction_source
    assert "finalState.moving_edge_ids" in interaction_source
    assert "finalState.copy_requested" in interaction_source
    assert "finalState.append_requested" in interaction_source
    assert "compatible_rewire_endpoint_snapshot" in interaction_source
    assert "request_move_edge_endpoint" not in interaction_source
    assert "jumpToSelectedEdgeEndpoint(endpoint)" in input_layers_source
    assert "property bool wireSelectionModeHeld: false" in input_layers_source
    assert "Keys.onPressed" in input_layers_source
    assert "Keys.onReleased" in input_layers_source
    assert 'marqueeMode = root.wireSelectionModeHeld ? "edge_selection" : "selection";' in input_layers_source
    assert "function updateEdgeSelection()" in input_layers_source
    assert "canvasItem.edgeIdsIntersectingScreenRect" in input_layers_source
    assert "canvasItem.setEdgeSelection" in input_layers_source


def test_pyqt_graph_action_declarations_use_contract_ids() -> None:
    assignments = _window_graph_action_contract_assignments()
    missing_actions = set(PYQT_GRAPH_ACTIONS) - set(assignments)
    assert missing_actions == set()
    assert assignments == PYQT_GRAPH_ACTIONS


def test_pyqt_graph_action_factory_uses_contract_labels_shortcuts_and_controller() -> None:
    source = _source(WINDOW_ACTIONS)
    assert "graph_action_spec(action_id)" in source
    assert "QAction(str(spec.label or action_id.value), window)" in source
    assert "action.setShortcut(QKeySequence(spec.shortcut))" in source
    assert "controller.trigger(action_id.value)" in source


def test_pyqt_graph_menu_actions_are_mapped_to_contract() -> None:
    missing = _window_graph_menu_actions() - set(PYQT_GRAPH_ACTIONS)
    assert missing == set()


def test_qml_graph_action_slots_are_mixin_methods_dispatching_to_controller() -> None:
    # The QML-facing graph-action slots are defined once, in the
    # workspace_graph_actions mixin class body, and dispatch through
    # graph_action_controller.trigger(GraphActionId...). No module-level
    # facade functions, assignment-block rebinding, or facade binding maps.
    source = _source(WORKSPACE_GRAPH_ACTIONS)
    window_source = _source(REPO_ROOT / "ea_node_editor" / "ui" / "shell" / "window.py")
    missing_definitions = {
        slot_name
        for slot_name in P03_RETIRED_SHELL_GRAPH_ACTION_FACADE_SLOTS
        if f"def {slot_name}" not in source
    }
    assert missing_definitions == set()
    window_definitions = {
        slot_name
        for slot_name in P03_RETIRED_SHELL_GRAPH_ACTION_FACADE_SLOTS
        if f"def {slot_name}" in window_source
    }
    assert window_definitions == set()
    assert "graph_action_controller.trigger(GraphActionId" in source
    assert re.search(r"^(?:request_\w+|_\w+) = \w+$", source, re.M) is None
    assert "WINDOW_STATE_FACADE_BINDINGS" not in source


def test_graph_action_controller_calls_scope_owners_directly() -> None:
    source = _source(GRAPH_ACTION_CONTROLLER)
    tree = ast.parse(source, filename=str(GRAPH_ACTION_CONTROLLER))
    controller = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GraphActionController"
    )

    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        for node in ast.walk(controller)
    )
    assert "search_scope.navigate_scope(" in source
    assert "scene.open_subnode_scope(node_id)" in source
    assert "search_scope is None or scene is None" in source
    assert "callable(navigate)" not in source
    assert "callable(open_scope)" not in source


def test_required_payload_keys_are_declared_for_payload_actions() -> None:
    payload_action_ids = {
        GraphActionId.OPEN_ADDON_MANAGER_FOR_NODE,
        GraphActionId.OPEN_SUBNODE_SCOPE,
        GraphActionId.PUBLISH_CUSTOM_WORKFLOW_FROM_NODE,
        GraphActionId.OPEN_COMMENT_PEEK,
        GraphActionId.EDIT_PASSIVE_NODE_STYLE,
        GraphActionId.RESET_PASSIVE_NODE_STYLE,
        GraphActionId.COPY_PASSIVE_NODE_STYLE,
        GraphActionId.PASTE_PASSIVE_NODE_STYLE,
        GraphActionId.PROPAGATE_PASSIVE_NODE_STYLE,
        GraphActionId.RENAME_NODE,
        GraphActionId.UNGROUP_NODE,
        GraphActionId.REMOVE_NODE,
        GraphActionId.DUPLICATE_NODE,
        GraphActionId.EDIT_FLOW_EDGE_STYLE,
        GraphActionId.EDIT_FLOW_EDGE_LABEL,
        GraphActionId.RESET_FLOW_EDGE_STYLE,
        GraphActionId.COPY_FLOW_EDGE_STYLE,
        GraphActionId.PASTE_FLOW_EDGE_STYLE,
        GraphActionId.REMOVE_EDGE,
    }
    missing = {
        action_id.value
        for action_id in payload_action_ids
        if not graph_action_spec(action_id).required_payload_keys
    }
    assert missing == set()


def test_graph_action_dispatch_ids_are_canonical_only() -> None:
    assert GraphActionId("remove_edge") is GraphActionId.REMOVE_EDGE
    assert normalize_graph_action_payload("request_remove_edge", {"edge_id": "edge-1"}) is None
    assert normalize_graph_action_payload("edit_flow_edge", {"edge_id": "edge-1"}) is None
    assert normalize_graph_action_payload("show_help", {"node_id": "node-1"}) is None
    assert normalize_graph_action_payload("not_a_graph_action", {}) is None


def test_graph_action_payload_normalization_rejects_invalid_required_payloads() -> None:
    assert normalize_graph_action_payload(GraphActionId.REMOVE_EDGE, {"edge_id": " edge-1 "}) == {
        "edge_id": "edge-1"
    }
    assert normalize_graph_action_payload("remove_edge", {"edge_id": ""}) is None
    assert normalize_graph_action_payload("remove_edge", {"node_id": "node-1"}) is None
    assert normalize_graph_action_payload("remove_edge", {"edge_id": 123}) is None
    assert normalize_graph_action_payload("copy_selection", None) == {}


def test_folder_explorer_action_contract_declares_stable_commands_and_payload_keys() -> None:
    for action_id, payload_keys in FOLDER_EXPLORER_ACTION_PAYLOAD_KEYS.items():
        spec = graph_action_spec(action_id)
        assert spec.required_payload_keys == payload_keys
        assert any(surface.startswith("qml_folder_explorer") for surface in spec.surfaces)

    assert graph_action_spec(GraphActionId.FOLDER_EXPLORER_DELETE).destructive is True
    assert graph_action_spec(GraphActionId.FOLDER_EXPLORER_SEND_TO_COREX_PATH_POINTER).destructive is False
    assert normalize_graph_action_payload(
        "folderExplorerSendToCorexPathPointer",
        {"node_id": "folder-node", "path": "C:/tmp"},
    ) is None
    assert normalize_graph_action_payload(
        "folder_explorer_new_folder",
        {"node_id": " folder-node ", "path": " C:/tmp ", "name": " Created "},
    ) == {"node_id": "folder-node", "path": "C:/tmp", "name": "Created"}
    assert normalize_graph_action_payload(
        "folder_explorer_set_sort",
        {"node_id": "folder-node", "path": "C:/tmp"},
    ) is None


def test_qml_folder_explorer_actions_route_through_canvas_command_bridge() -> None:
    action_router_source = _source(ACTION_ROUTER_QML)
    surface_bridge_source = _source(
        REPO_ROOT
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "graph_canvas"
        / "GraphCanvasNodeSurfaceBridge.qml"
    )

    assert "readonly property var folderExplorerActionDescriptors" in action_router_source
    assert (
        '"folder_explorer_open_with": { "actionId": "folder_explorer_open_with" }'
        in action_router_source
    )
    assert (
        '"folder_explorer_send_to_corex_path_pointer": '
        '{ "actionId": "folder_explorer_send_to_corex_path_pointer" }'
    ) in (
        action_router_source
    )
    assert "function requestFolderExplorerAction(actionId, payload)" in action_router_source
    assert "bridge.request_folder_explorer_action(String(actionId || \"\"), payload || ({}))" in action_router_source
    assert "function requestFolderExplorerAction(nodeId, command, payload)" in surface_bridge_source
    assert "function createFolderExplorerPathPointer(nodeId, path, sceneX, sceneY)" in surface_bridge_source
    assert '"type_id": "io.path_pointer"' in surface_bridge_source


def test_folder_explorer_bridge_lists_and_updates_current_path_through_scene_mutation() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        child = root / "Child"
        child.mkdir()
        (child / "note.txt").write_text("hello", encoding="utf-8")
        scene = _FolderExplorerSceneCommandProbe()
        bridge = GraphCanvasCommandBridge(
            scene_bridge=scene,
            folder_explorer_service=FolderExplorerFilesystemService(),
            folder_explorer_confirmation_source=_FolderExplorerConfirmationProbe(True),
        )

        result = bridge.request_folder_explorer_action(
            "folder_explorer_navigate",
            {"node_id": "folder-node", "path": str(child), "sort_key": "name"},
        )

        assert result["success"] is True
        assert result["path"] == str(child.resolve())
        assert result["listing"]["directory_path"] == str(child.resolve())
        assert [entry["name"] for entry in result["listing"]["entries"]] == ["note.txt"]
        assert scene.properties == [("folder-node", "current_path", str(child.resolve()))]


def test_folder_explorer_bridge_defaults_empty_list_path_to_desktop() -> None:
    scene = _FolderExplorerSceneCommandProbe()
    bridge = GraphCanvasCommandBridge(
        scene_bridge=scene,
        folder_explorer_service=FolderExplorerFilesystemService(),
    )
    default_path = default_user_desktop_path()

    result = bridge.request_folder_explorer_action(
        "folder_explorer_list",
        {"node_id": "folder-node"},
    )

    assert result["success"] is True
    assert result["path"] == default_path
    assert result["listing"]["directory_path"] == default_path
    assert scene.properties == [("folder-node", "current_path", default_path)]


def test_folder_explorer_bridge_declined_delete_does_not_call_service_mutation() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        target = root / "delete-me.txt"
        target.write_text("keep", encoding="utf-8")
        confirmation = _FolderExplorerConfirmationProbe(False)
        bridge = GraphCanvasCommandBridge(
            folder_explorer_service=FolderExplorerFilesystemService(),
            folder_explorer_confirmation_source=confirmation,
        )

        result = bridge.request_folder_explorer_action(
            "folder_explorer_delete",
            {"node_id": "folder-node", "path": str(target), "current_path": str(root)},
        )

        assert result["success"] is False
        assert result["cancelled"] is True
        assert result["error"]["code"] == "cancelled"
        assert target.exists()
        assert confirmation.calls == [("delete", str(target), "")]


def test_folder_explorer_bridge_confirmed_mutation_returns_refreshed_listing() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        confirmation = _FolderExplorerConfirmationProbe(True)
        bridge = GraphCanvasCommandBridge(
            folder_explorer_service=FolderExplorerFilesystemService(),
            folder_explorer_confirmation_source=confirmation,
        )

        result = bridge.request_folder_explorer_action(
            "folder_explorer_new_folder",
            {"node_id": "folder-node", "path": str(root), "name": "Created"},
        )

        assert result["success"] is True
        assert (root / "Created").is_dir()
        assert result["entry"]["kind"] == "folder"
        assert [entry["name"] for entry in result["listing"]["entries"]] == ["Created"]
        assert confirmation.calls == [("new_folder", str(root), str(root / "Created"))]


def test_folder_explorer_bridge_confirmed_rename_cut_and_paste_mutate_only_temp_paths() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        source = root / "source.txt"
        source.write_text("move me", encoding="utf-8")
        sibling = root / "sibling.txt"
        sibling.write_text("keep me", encoding="utf-8")
        destination = root / "Destination"
        destination.mkdir()
        renamed = root / "renamed.txt"
        confirmation = _FolderExplorerConfirmationProbe(True)
        bridge = GraphCanvasCommandBridge(
            folder_explorer_service=FolderExplorerFilesystemService(),
            folder_explorer_confirmation_source=confirmation,
        )

        rename_result = bridge.request_folder_explorer_action(
            "folder_explorer_rename",
            {"node_id": "folder-node", "path": str(source), "new_name": "renamed.txt", "current_path": str(root)},
        )
        cut_result = bridge.request_folder_explorer_action(
            "folder_explorer_cut",
            {"node_id": "folder-node", "path": str(renamed)},
        )
        paste_result = bridge.request_folder_explorer_action(
            "folder_explorer_paste",
            {"node_id": "folder-node", "path": str(destination)},
        )

        assert rename_result["success"] is True
        assert cut_result["success"] is True
        assert paste_result["success"] is True
        assert not source.exists()
        assert not renamed.exists()
        assert (destination / "renamed.txt").read_text(encoding="utf-8") == "move me"
        assert sibling.read_text(encoding="utf-8") == "keep me"
        assert paste_result["listing"]["directory_path"] == str(destination.resolve(strict=False))
        assert [entry["name"] for entry in paste_result["listing"]["entries"]] == ["renamed.txt"]
        assert confirmation.calls == [
            ("rename", str(source), str(renamed)),
            ("cut", str(renamed), ""),
            ("paste", str(destination), ""),
        ]


def test_folder_explorer_bridge_copy_path_and_open_use_shell_seams() -> None:
    with TemporaryDirectory() as temporary_directory:
        target = Path(temporary_directory) / "open-me.txt"
        target.write_text("hello", encoding="utf-8")
        clipboard = _FolderExplorerClipboardProbe()
        opener = _FolderExplorerOpenProbe()
        bridge = GraphCanvasCommandBridge(
            folder_explorer_service=FolderExplorerFilesystemService(),
            folder_explorer_clipboard_source=clipboard,
            folder_explorer_open_source=opener,
        )

        copy_result = bridge.request_folder_explorer_action(
            "folder_explorer_copy_path",
            {"node_id": "folder-node", "path": str(target)},
        )
        open_result = bridge.request_folder_explorer_action(
            "folder_explorer_open",
            {"node_id": "folder-node", "path": str(target)},
        )

        assert copy_result["success"] is True
        assert clipboard.text == str(target.resolve())
        assert open_result["success"] is True
        assert opener.paths == [str(target.resolve())]


def test_folder_explorer_bridge_open_with_uses_app_chooser_seam(monkeypatch) -> None:
    import ea_node_editor.ui_qml.graph_canvas_command.folder_explorer_ops as command_bridge_module

    with TemporaryDirectory() as temporary_directory:
        target = Path(temporary_directory) / "open-with-me.txt"
        target.write_text("hello", encoding="utf-8")
        bridge = GraphCanvasCommandBridge(folder_explorer_service=FolderExplorerFilesystemService())

        chooser_calls: list[str] = []

        def _chooser(path: str) -> bool:
            chooser_calls.append(path)
            return True

        monkeypatch.setattr(command_bridge_module, "open_path_with_app_chooser", _chooser)
        ok_result = bridge.request_folder_explorer_action(
            "folder_explorer_open_with",
            {"node_id": "folder-node", "path": str(target)},
        )

        assert ok_result["success"] is True
        assert chooser_calls == [str(target.resolve())]

        # An existing path whose chooser launch fails surfaces an open_failed error.
        monkeypatch.setattr(command_bridge_module, "open_path_with_app_chooser", lambda path: False)
        failed_result = bridge.request_folder_explorer_action(
            "folder_explorer_open_with",
            {"node_id": "folder-node", "path": str(target)},
        )

        assert failed_result["success"] is False
        assert failed_result["error"]["code"] == "open_failed"


def test_open_node_path_actions_route_through_node_delegate_descriptors() -> None:
    action_router_source = _source(ACTION_ROUTER_QML)

    assert '"open_node_path": { "actionId": "open_node_path", "payload": "node" }' in action_router_source
    assert (
        '"open_node_path_with": { "actionId": "open_node_path_with", "payload": "node" }'
        in action_router_source
    )
    for action_id in (GraphActionId.OPEN_NODE_PATH, GraphActionId.OPEN_NODE_PATH_WITH):
        spec = graph_action_spec(action_id)
        assert spec.surfaces == ("qml_node_delegate",)
        assert spec.required_payload_keys == ("node_id",)
        assert spec.destructive is False


def test_path_pointer_node_host_exposes_open_toolbar_popover() -> None:
    node_host_source = _source(
        REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph" / "GraphNodeHost.qml"
    )
    presentation_source = _source(ACTION_PRESENTATION_JS)

    assert 'type_id || "") === "io.path_pointer"' in node_host_source
    assert "GraphActionPresentation.nodeContextActions(" in node_host_source
    assert '"open_node_path_menu"' in presentation_source
    assert '"open_node_path"' in presentation_source
    assert '"open_node_path_with"' in presentation_source
    assert "popoverActions" in presentation_source


def test_folder_explorer_surface_wires_row_context_menu() -> None:
    surface_source = _source(
        REPO_ROOT
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "graph"
        / "passive"
        / "GraphNativeExplorerSurface.qml"
    )

    # The right-click menu and its non-destructive items are wired into the row.
    assert 'objectName: "graphFolderExplorerRowContextMenu"' in surface_source
    for object_name in (
        "graphFolderExplorerRowOpenItem",
        "graphFolderExplorerRowOpenWithItem",
        "graphFolderExplorerRowCopyPathItem",
        "graphFolderExplorerRowOpenNewWindowItem",
        "graphFolderExplorerRowSendToCorexItem",
        "graphFolderExplorerRowPropertiesItem",
    ):
        assert f'objectName: "{object_name}"' in surface_source

    # Open with... dispatches the new chooser action and is hidden for folders/parents.
    assert "function openPathWith(path)" in surface_source
    assert '"folder_explorer_open_with"' in surface_source
    assert "!root._menuIsFolder && !root._menuIsParent" in surface_source

    # Right-click opens the menu without disturbing left-drag / double-click.
    assert "else if (mouse.button === Qt.RightButton)" in surface_source
    assert "root._openRowContextMenu(rowMouseArea, mouse, rowRoot)" in surface_source

    # Reused (non-destructive) backend actions are dispatched from the menu.
    for command in (
        "folder_explorer_copy_path",
        "folder_explorer_properties",
        "folder_explorer_open_in_new_window",
        "folder_explorer_send_to_corex_path_pointer",
    ):
        assert command in surface_source


def test_folder_explorer_bridge_creates_path_pointer_and_new_explorer_nodes() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        target_file = root / "selected.txt"
        target_file.write_text("hello", encoding="utf-8")
        scene = _FolderExplorerSceneCommandProbe()
        bridge = GraphCanvasCommandBridge(
            scene_bridge=scene,
            folder_explorer_service=FolderExplorerFilesystemService(),
        )

        path_pointer_result = bridge.request_folder_explorer_action(
            "folder_explorer_send_to_corex_path_pointer",
            {"node_id": "folder-node", "path": str(target_file), "scene_x": 120, "scene_y": 240},
        )
        explorer_result = bridge.request_folder_explorer_action(
            "folder_explorer_open_in_new_window",
            {"node_id": "folder-node", "path": str(root), "scene_x": 360, "scene_y": 480},
        )

        assert path_pointer_result["success"] is True
        assert path_pointer_result["created_type_id"] == "io.path_pointer"
        assert explorer_result["success"] is True
        assert explorer_result["created_type_id"] == "io.folder_explorer"
        assert scene.added_nodes == [
            ("io.path_pointer", 120.0, 240.0, "node-1"),
            ("io.folder_explorer", 360.0, 480.0, "node-2"),
        ]
        assert scene.bulk_properties == [
            ("node-1", {"path": str(target_file.resolve()), "mode": "file"}),
            ("node-2", {"current_path": str(root.resolve())}),
        ]


def test_graph_canvas_command_bridge_creates_path_pointer_from_os_drop_url() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        target_file = root / "dropped.txt"
        target_file.write_text("hello", encoding="utf-8")
        scene = _FolderExplorerSceneCommandProbe()
        bridge = GraphCanvasCommandBridge(scene_bridge=scene)

        result = bridge.request_create_path_pointer_node(
            target_file.resolve().as_uri(),
            False,
            48,
            96,
        )

        assert result["success"] is True
        assert result["created_type_id"] == "io.path_pointer"
        assert result["mode"] == "file"
        assert scene.added_nodes == [("io.path_pointer", 48.0, 96.0, "node-1")]
        assert scene.bulk_properties == [("node-1", {"path": str(target_file.resolve()), "mode": "file"})]


def test_graph_canvas_command_bridge_updates_existing_path_pointer_from_drop() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        target_file = root / "message.eml"
        target_file.write_text("Subject: Hello\n\nBody", encoding="utf-8")
        target_folder = root / "results"
        target_folder.mkdir()
        scene = _FolderExplorerSceneCommandProbe()
        bridge = GraphCanvasCommandBridge(scene_bridge=scene)

        assert bridge.request_update_path_pointer_node("pointer-1", target_file.resolve().as_uri(), False)
        assert bridge.request_update_path_pointer_node("pointer-1", str(target_folder), False)

        assert scene.bulk_properties == [
            ("pointer-1", {"path": str(target_file.resolve()), "mode": "file"}),
            ("pointer-1", {"path": str(target_folder.resolve()), "mode": "folder"}),
        ]
        assert scene.added_nodes == []
        assert scene.properties == []


def test_graph_canvas_command_bridge_rejects_invalid_path_pointer_updates_without_single_property_fallback() -> None:
    unavailable_bridge = GraphCanvasCommandBridge()
    rejected_scene = _FolderExplorerSceneCommandProbe(bulk_result=False)
    rejected_bridge = GraphCanvasCommandBridge(scene_bridge=rejected_scene)

    assert not unavailable_bridge.request_update_path_pointer_node("pointer-1", "C:/results/input.rst", False)
    assert not rejected_bridge.request_update_path_pointer_node("", "C:/results/input.rst", False)
    assert not rejected_bridge.request_update_path_pointer_node("pointer-1", "", False)
    assert not rejected_bridge.request_update_path_pointer_node("pointer-1", "C:/results/input.rst", True)

    assert rejected_scene.bulk_properties == [
        ("pointer-1", {"path": str(Path("C:/results/input.rst").resolve()), "mode": "folder"})
    ]
    assert rejected_scene.properties == []


def test_graph_canvas_command_bridge_routes_all_drop_formats_to_import_controller() -> None:
    calls = []
    controller = SimpleNamespace(
        drop=lambda *args: calls.append(args) or True,
        drop_local_path=lambda *args: calls.append(args) or True,
    )
    bridge = GraphCanvasCommandBridge(canvas_import_controller=controller)
    urls = ["file:///C:/a.png", "https://example.test/page?x=1#part"]
    assert bridge.request_canvas_import_drop(urls, "literal text", "<b>HTML</b>", 64, 128)
    assert calls == [(urls, "literal text", "<b>HTML</b>", 64, 128)]
    assert bridge.request_canvas_import_local_path("C:/folder", True, 8, 16)
    assert calls[-1] == ("C:/folder", True, 8, 16)
    assert not GraphCanvasCommandBridge().request_canvas_import_drop(urls, "", "", 0, 0)


def test_graph_canvas_qml_delegates_classification_and_preserves_targeted_path_replacement() -> None:
    canvas_source = _source(REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "GraphCanvas.qml")
    assert "function _mailFileDropPayload" not in canvas_source
    assert "function _fileDropPayload" not in canvas_source
    assert "request_create_file_drop_node" not in canvas_source
    assert "bridge.request_canvas_import_drop(urls, text, html," in canvas_source
    assert "return root.performPathPointerNodeDrop(targetHost.nodeId, path, isFolder)" in canvas_source


def test_mail_panel_surface_declares_source_open_and_safe_webengine_actions() -> None:
    surface_source = _source(
        REPO_ROOT
        / "ea_node_editor"
        / "ui_qml"
        / "components"
        / "graph"
        / "passive"
        / "GraphMailPanelSurface.qml"
    )

    for action_id in (
        "editSource",
        "editSourceManagedCopy",
        "editSourceExternalLink",
        "internalizeSource",
        "openSource",
        "openSourceWith",
        "fullscreen",
        "toggle_content_only",
        "toggle_title",
        "toggle_frame",
    ):
        assert f'"{action_id}"' in surface_source
    assert "host.describeMailPreview(sourcePath)" in surface_source
    assert "host.openLocalFileSource(sourcePath, Boolean(chooser))" in surface_source
    assert "readonly property bool blocksHostInteraction: false" in surface_source
    assert "host.surfaceFullscreenAction(fullscreenAvailable && readyPreview, false)" in surface_source
    assert 'if (normalized === "fullscreen")' in surface_source
    assert '"    enabled: false"' in surface_source
    assert "settings.javascriptEnabled: false" in surface_source
    assert "settings.pluginsEnabled: false" in surface_source
    assert "settings.localContentCanAccessRemoteUrls: true" in surface_source


def test_folder_explorer_bridge_rejects_retired_qml_command_aliases_for_drag_and_new_window() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        target_folder = root / "Selected Folder"
        target_folder.mkdir()
        scene = _FolderExplorerSceneCommandProbe()
        bridge = GraphCanvasCommandBridge(
            scene_bridge=scene,
            folder_explorer_service=FolderExplorerFilesystemService(),
        )

        drag_result = bridge.request_folder_explorer_action(
            "sendToCorexPathPointer",
            {"node_id": "folder-node", "path": str(target_folder), "scene_x": 10, "scene_y": 20},
        )
        new_window_result = bridge.request_folder_explorer_action(
            "openInNewWindow",
            {"node_id": "folder-node", "path": str(root), "scene_x": 30, "scene_y": 40},
        )

        assert drag_result["success"] is False
        assert drag_result["error"]["code"] == "unknown_action"
        assert new_window_result["success"] is False
        assert new_window_result["error"]["code"] == "unknown_action"
        assert scene.added_nodes == []
        assert scene.bulk_properties == []
