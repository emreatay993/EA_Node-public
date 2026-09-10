# Purpose: Dispatch normalized graph action IDs through explicit concrete owners.
# Map: feature_routes/graph_actions_and_context_menus
# Tests: tests/test_graph_action_contracts.py
from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Callable
from typing import TYPE_CHECKING

from ea_node_editor.platform_open import (
    open_path_with_app_chooser,
    open_path_with_default_handler,
)
from ea_node_editor.ui.shell.graph_action_contracts import (
    GRAPH_ACTION_SPECS,
    GraphActionId,
    normalize_graph_action_payload,
)

if TYPE_CHECKING:
    from ea_node_editor.help.help_bridge import HelpBridge
    from ea_node_editor.ui.shell.composition.bridges import AddonManagerBridge
    from ea_node_editor.ui.shell.controllers.run_controller import RunController
    from ea_node_editor.ui.shell.controllers.workflow_library_controller import (
        WorkflowLibraryController,
    )
    from ea_node_editor.ui.shell.controllers.workspace_edit_controller import (
        WorkspaceEditController,
    )
    from ea_node_editor.ui.shell.presenters.graph_canvas_host_presenter import (
        GraphCanvasHostPresenter,
    )
    from ea_node_editor.ui.shell.window_search_scope_state import (
        WindowSearchScopeController,
    )
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


_UNSET = object()


class GraphActionController:
    def __init__(
        self,
        *,
        workspace_edit_controller: WorkspaceEditController | None = None,
        workflow_library_controller: WorkflowLibraryController | None = None,
        search_scope_controller: WindowSearchScopeController | None = None,
        show_graph_hint: Callable[[str, int], None] | None = None,
        graph_canvas_host_presenter: GraphCanvasHostPresenter | None = None,
        scene_bridge: GraphSceneBridge | None = None,
        help_bridge: HelpBridge | None = None,
        addon_manager_bridge: AddonManagerBridge | None = None,
        run_controller: RunController | None = None,
    ) -> None:
        self._workspace_edit_controller = workspace_edit_controller
        self._workflow_library_controller = workflow_library_controller
        self._search_scope_controller = search_scope_controller
        self._show_graph_hint = show_graph_hint
        self._graph_canvas_host_presenter = graph_canvas_host_presenter
        self._scene_bridge = scene_bridge
        self._help_bridge = help_bridge
        self._addon_manager_bridge = addon_manager_bridge
        self._run_controller = run_controller

    @property
    def available_action_ids(self) -> tuple[str, ...]:
        return tuple(spec.action_id.value for spec in GRAPH_ACTION_SPECS)

    def trigger(
        self,
        action_id: str,
        payload: Mapping[str, object] | None = None,
    ) -> bool:
        try:
            canonical_action_id = GraphActionId(str(action_id or "").strip())
        except ValueError:
            return False
        if canonical_action_id is GraphActionId.SHOW_NODE_HELP and payload is None:
            if self._help_bridge is None:
                return False
            return _result_bool(self._help_bridge.show_help_for_selected_node())
        normalized_payload = normalize_graph_action_payload(
            canonical_action_id, payload
        )
        if normalized_payload is None:
            return False
        return self._trigger_normalized(canonical_action_id, normalized_payload)

    def _trigger_normalized(
        self,
        action_id: GraphActionId,
        payload: Mapping[str, object],
    ) -> bool:
        edit = self._workspace_edit_controller
        if action_id is GraphActionId.CONNECT_SELECTED:
            if edit is None:
                return False
            edit.connect_selected_nodes()
            return True
        if action_id is GraphActionId.COPY_SELECTION:
            return edit is not None and edit.copy_selected_nodes_to_clipboard()
        if action_id is GraphActionId.CUT_SELECTION:
            return edit is not None and edit.cut_selected_nodes_to_clipboard()
        if action_id is GraphActionId.PASTE_SELECTION:
            return edit is not None and edit.paste_nodes_from_clipboard()
        if action_id is GraphActionId.DUPLICATE_SELECTION:
            return edit is not None and edit.duplicate_selected_nodes()
        if action_id is GraphActionId.WRAP_SELECTION_IN_GROUP_BACKDROP:
            return edit is not None and edit.wrap_selected_nodes_in_group_backdrop()
        if action_id is GraphActionId.GROUP_SELECTION:
            return edit is not None and edit.group_selected_nodes()
        if action_id is GraphActionId.UNGROUP_SELECTION:
            return edit is not None and edit.ungroup_selected_nodes()
        if action_id is GraphActionId.ALIGN_SELECTION_LEFT:
            return edit is not None and edit.align_selection_left()
        if action_id is GraphActionId.ALIGN_SELECTION_RIGHT:
            return edit is not None and edit.align_selection_right()
        if action_id is GraphActionId.ALIGN_SELECTION_TOP:
            return edit is not None and edit.align_selection_top()
        if action_id is GraphActionId.ALIGN_SELECTION_BOTTOM:
            return edit is not None and edit.align_selection_bottom()
        if action_id is GraphActionId.DISTRIBUTE_SELECTION_HORIZONTALLY:
            return edit is not None and edit.distribute_selection_horizontally()
        if action_id is GraphActionId.DISTRIBUTE_SELECTION_VERTICALLY:
            return edit is not None and edit.distribute_selection_vertically()
        if action_id is GraphActionId.STRAIGHTEN_SELECTION_CONNECTIONS:
            return edit is not None and edit.straighten_selection_connections()
        if action_id is GraphActionId.SET_SELECTION_SAME_TYPE_WIDTH:
            node_ids = _selection_node_ids(payload)
            return (
                edit is not None
                and node_ids is not None
                and edit.set_selection_same_type_width(node_ids)
            )
        if action_id is GraphActionId.SET_SELECTION_SAME_TYPE_HEIGHT:
            node_ids = _selection_node_ids(payload)
            return (
                edit is not None
                and node_ids is not None
                and edit.set_selection_same_type_height(node_ids)
            )
        if action_id is GraphActionId.DELETE_SELECTION:
            edge_ids = _optional_list(payload, "edge_ids")
            if edit is None or edge_ids is None:
                return False
            return bool(edit.request_delete_selected_graph_items(edge_ids).payload)

        run = self._run_controller
        if action_id is GraphActionId.RUN_SELECTED:
            if run is None:
                return False
            return _result_bool(
                run.run_selected_nodes(_selected_run_node_ids(payload)),
                none_is_success=True,
            )
        if action_id is GraphActionId.PREVIEW_SELECTED_RUN:
            if run is None:
                return False
            return _result_bool(
                run.preview_selected_run(_selected_run_node_ids(payload)),
                none_is_success=True,
            )
        if action_id is GraphActionId.CONFIRM_SELECTED_RUN_PREVIEW:
            if run is None:
                return False
            return _result_bool(
                run.confirm_selected_run_preview(),
                none_is_success=True,
            )
        if action_id is GraphActionId.CLEAR_SELECTED_RUN_PREVIEW:
            if run is None:
                return False
            return _result_bool(
                run.clear_selected_run_preview(),
                none_is_success=True,
            )
        if action_id is GraphActionId.OPEN_SELECTED_RUN_SETTINGS:
            if run is None:
                return False
            return _result_bool(
                run.open_selected_run_settings(),
                none_is_success=True,
            )

        host_presenter = self._graph_canvas_host_presenter
        if action_id is GraphActionId.NAVIGATE_SCOPE_PARENT:
            return (
                host_presenter is not None
                and host_presenter.request_navigate_scope_parent()
            )
        if action_id is GraphActionId.NAVIGATE_SCOPE_ROOT:
            return (
                host_presenter is not None
                and host_presenter.request_navigate_scope_root()
            )

        if action_id is GraphActionId.OPEN_SUBNODE_SCOPE:
            node_id = _required_str(payload, "node_id")
            search_scope = self._search_scope_controller
            scene = self._scene_bridge
            if not node_id or search_scope is None or scene is None:
                return False
            return bool(
                search_scope.navigate_scope(lambda: scene.open_subnode_scope(node_id))
            )

        if action_id is GraphActionId.PUBLISH_CUSTOM_WORKFLOW_FROM_NODE:
            workflow = self._workflow_library_controller
            if workflow is None:
                return False
            return bool(
                workflow.publish_custom_workflow_from_node(
                    _required_str(payload, "node_id")
                ).payload
            )

        scene = self._scene_bridge
        if action_id is GraphActionId.OPEN_COMMENT_PEEK:
            return scene is not None and scene.open_comment_peek(
                _required_str(payload, "node_id")
            )
        if action_id is GraphActionId.CLOSE_COMMENT_PEEK:
            return scene is not None and scene.close_comment_peek()
        if action_id is GraphActionId.RENAME_NODE and bool(
            payload.get("inline_title_edit")
        ):
            return True

        if host_presenter is not None and action_id in {
            GraphActionId.EDIT_PASSIVE_NODE_STYLE,
            GraphActionId.RESET_PASSIVE_NODE_STYLE,
            GraphActionId.COPY_PASSIVE_NODE_STYLE,
            GraphActionId.PASTE_PASSIVE_NODE_STYLE,
            GraphActionId.PROPAGATE_PASSIVE_NODE_STYLE,
            GraphActionId.RENAME_NODE,
            GraphActionId.UNGROUP_NODE,
            GraphActionId.REMOVE_NODE,
        }:
            node_id = _required_str(payload, "node_id")
            if action_id is GraphActionId.EDIT_PASSIVE_NODE_STYLE:
                return host_presenter.request_edit_passive_node_style(node_id)
            if action_id is GraphActionId.RESET_PASSIVE_NODE_STYLE:
                return host_presenter.request_reset_passive_node_style(node_id)
            if action_id is GraphActionId.COPY_PASSIVE_NODE_STYLE:
                return host_presenter.request_copy_passive_node_style(node_id)
            if action_id is GraphActionId.PASTE_PASSIVE_NODE_STYLE:
                return host_presenter.request_paste_passive_node_style(node_id)
            if action_id is GraphActionId.PROPAGATE_PASSIVE_NODE_STYLE:
                return host_presenter.request_propagate_passive_node_style(node_id)
            if action_id is GraphActionId.RENAME_NODE:
                return host_presenter.request_rename_node(node_id)
            if action_id is GraphActionId.UNGROUP_NODE:
                return host_presenter.request_ungroup_node(node_id)
            if action_id is GraphActionId.REMOVE_NODE:
                return host_presenter.request_remove_node(node_id)

        if action_id is GraphActionId.DUPLICATE_NODE:
            if scene is None:
                return False
            scene.select_node(_required_str(payload, "node_id"), False)
            return scene.duplicate_selected_subgraph()
        if action_id is GraphActionId.OPEN_NODE_PATH:
            return self._trigger_open_node_path(payload, chooser=False)
        if action_id is GraphActionId.OPEN_NODE_PATH_WITH:
            return self._trigger_open_node_path(payload, chooser=True)
        if action_id is GraphActionId.SHOW_NODE_HELP:
            return (
                self._help_bridge is not None
                and self._help_bridge.show_help_for_node(
                    _required_str(payload, "node_id")
                )
            )

        if host_presenter is not None and action_id in {
            GraphActionId.EDIT_FLOW_EDGE_STYLE,
            GraphActionId.EDIT_FLOW_EDGE_LABEL,
            GraphActionId.RESET_FLOW_EDGE_STYLE,
            GraphActionId.COPY_FLOW_EDGE_STYLE,
            GraphActionId.PASTE_FLOW_EDGE_STYLE,
            GraphActionId.REMOVE_EDGE,
        }:
            edge_id = _required_str(payload, "edge_id")
            if action_id is GraphActionId.EDIT_FLOW_EDGE_STYLE:
                return host_presenter.request_edit_flow_edge_style(edge_id)
            if action_id is GraphActionId.EDIT_FLOW_EDGE_LABEL:
                return host_presenter.request_edit_flow_edge_label(edge_id)
            if action_id is GraphActionId.RESET_FLOW_EDGE_STYLE:
                return host_presenter.request_reset_flow_edge_style(edge_id)
            if action_id is GraphActionId.COPY_FLOW_EDGE_STYLE:
                return host_presenter.request_copy_flow_edge_style(edge_id)
            if action_id is GraphActionId.PASTE_FLOW_EDGE_STYLE:
                return host_presenter.request_paste_flow_edge_style(edge_id)
            if action_id is GraphActionId.REMOVE_EDGE:
                return host_presenter.request_remove_edge(edge_id)

        if action_id is GraphActionId.OPEN_ADDON_MANAGER_FOR_NODE:
            focus_addon_id = self._addon_focus_id(payload)
            if not focus_addon_id or self._addon_manager_bridge is None:
                return False
            self._addon_manager_bridge.requestOpen(focus_addon_id)
            return True
        return False

    def _trigger_open_node_path(
        self,
        payload: Mapping[str, object],
        *,
        chooser: bool,
    ) -> bool:
        path = ""
        properties = self._scene_node_payload(_required_str(payload, "node_id")).get(
            "properties"
        )
        if isinstance(properties, Mapping):
            path = str(properties.get("path") or "").strip()
        if not path:
            self._show_open_path_hint("No path is set on this node to open.")
            return False
        opener = (
            open_path_with_app_chooser if chooser else open_path_with_default_handler
        )
        if not opener(path):
            self._show_open_path_hint(f'Could not open "{path}".')
            return False
        return True

    def _show_open_path_hint(self, message: str) -> None:
        if callable(self._show_graph_hint):
            self._show_graph_hint(message, 3200)

    def _addon_focus_id(self, payload: Mapping[str, object]) -> str:
        explicit = _first_non_empty_str(payload, "focus_addon_id", "addon_id")
        if explicit:
            return explicit
        node_payload = self._scene_node_payload(_required_str(payload, "node_id"))
        locked_state = node_payload.get("locked_state")
        if isinstance(locked_state, Mapping):
            focus_addon_id = _first_non_empty_str(locked_state, "focus_addon_id")
            if focus_addon_id:
                return focus_addon_id
        return _first_non_empty_str(node_payload, "addon_id")

    def _scene_node_payload(self, node_id: str) -> Mapping[str, object]:
        scene = self._scene_bridge
        normalized_node_id = str(node_id or "").strip()
        if scene is None or not normalized_node_id:
            return {}
        for payloads in (scene.nodes_model, scene.backdrop_nodes_model):
            for payload in payloads:
                if (
                    isinstance(payload, Mapping)
                    and str(payload.get("node_id", "")).strip() == normalized_node_id
                ):
                    return payload
        return {}


def _result_bool(result: object, *, none_is_success: bool = False) -> bool:
    if result is None:
        return none_is_success
    payload = getattr(result, "payload", _UNSET)
    if payload is not _UNSET:
        return bool(payload)
    return bool(result)


def _required_str(payload: Mapping[str, object], key: str) -> str:
    return str(payload[key]).strip()


def _first_non_empty_str(payload: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _optional_list(
    payload: Mapping[str, object],
    key: str,
) -> list[object] | None:
    value = payload.get(key, [])
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return None


def _selected_run_node_ids(
    payload: Mapping[str, object],
) -> tuple[str, ...] | None:
    node_ids = _optional_list(payload, "node_ids")
    if node_ids is not None:
        normalized = tuple(
            str(value or "").strip() for value in node_ids if str(value or "").strip()
        )
        if normalized:
            return normalized
    node_id = payload.get("node_id")
    if isinstance(node_id, str) and node_id.strip():
        return (node_id.strip(),)
    return None


def _selection_node_ids(
    payload: Mapping[str, object],
) -> tuple[str, ...] | None:
    node_ids = _optional_list(payload, "node_ids")
    if node_ids is None:
        return None
    normalized = tuple(
        str(value or "").strip() for value in node_ids if str(value or "").strip()
    )
    return normalized or None


__all__ = ["GraphActionController"]
