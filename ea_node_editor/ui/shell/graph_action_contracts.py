from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class GraphActionId(str, Enum):
    CONNECT_SELECTED = "connect_selected"
    COPY_SELECTION = "copy_selection"
    CUT_SELECTION = "cut_selection"
    PASTE_SELECTION = "paste_selection"
    DUPLICATE_SELECTION = "duplicate_selection"
    DELETE_SELECTION = "delete_selection"
    WRAP_SELECTION_IN_GROUP_BACKDROP = "wrap_selection_in_group_backdrop"
    GROUP_SELECTION = "group_selection"
    UNGROUP_SELECTION = "ungroup_selection"
    ALIGN_SELECTION_LEFT = "align_selection_left"
    ALIGN_SELECTION_RIGHT = "align_selection_right"
    ALIGN_SELECTION_TOP = "align_selection_top"
    ALIGN_SELECTION_BOTTOM = "align_selection_bottom"
    DISTRIBUTE_SELECTION_HORIZONTALLY = "distribute_selection_horizontally"
    DISTRIBUTE_SELECTION_VERTICALLY = "distribute_selection_vertically"
    SET_SELECTION_SAME_TYPE_WIDTH = "set_selection_same_type_width"
    SET_SELECTION_SAME_TYPE_HEIGHT = "set_selection_same_type_height"
    STRAIGHTEN_SELECTION_CONNECTIONS = "straighten_selection_connections"
    RUN_SELECTED = "run_selected"
    PREVIEW_SELECTED_RUN = "preview_selected_run"
    CONFIRM_SELECTED_RUN_PREVIEW = "confirm_selected_run_preview"
    CLEAR_SELECTED_RUN_PREVIEW = "clear_selected_run_preview"
    OPEN_SELECTED_RUN_SETTINGS = "open_selected_run_settings"
    NAVIGATE_SCOPE_PARENT = "navigate_scope_parent"
    NAVIGATE_SCOPE_ROOT = "navigate_scope_root"
    OPEN_ADDON_MANAGER_FOR_NODE = "open_addon_manager_for_node"
    OPEN_SUBNODE_SCOPE = "open_subnode_scope"
    PUBLISH_CUSTOM_WORKFLOW_FROM_NODE = "publish_custom_workflow_from_node"
    OPEN_COMMENT_PEEK = "open_comment_peek"
    CLOSE_COMMENT_PEEK = "close_comment_peek"
    EDIT_PASSIVE_NODE_STYLE = "edit_passive_node_style"
    RESET_PASSIVE_NODE_STYLE = "reset_passive_node_style"
    COPY_PASSIVE_NODE_STYLE = "copy_passive_node_style"
    PASTE_PASSIVE_NODE_STYLE = "paste_passive_node_style"
    PROPAGATE_PASSIVE_NODE_STYLE = "propagate_passive_node_style"
    RENAME_NODE = "rename_node"
    SHOW_NODE_HELP = "show_node_help"
    UNGROUP_NODE = "ungroup_node"
    REMOVE_NODE = "remove_node"
    DUPLICATE_NODE = "duplicate_node"
    OPEN_NODE_PATH = "open_node_path"
    OPEN_NODE_PATH_WITH = "open_node_path_with"
    EDIT_FLOW_EDGE_STYLE = "edit_flow_edge_style"
    EDIT_FLOW_EDGE_LABEL = "edit_flow_edge_label"
    RESET_FLOW_EDGE_STYLE = "reset_flow_edge_style"
    COPY_FLOW_EDGE_STYLE = "copy_flow_edge_style"
    PASTE_FLOW_EDGE_STYLE = "paste_flow_edge_style"
    REMOVE_EDGE = "remove_edge"
    FOLDER_EXPLORER_LIST = "folder_explorer_list"
    FOLDER_EXPLORER_NAVIGATE = "folder_explorer_navigate"
    FOLDER_EXPLORER_REFRESH = "folder_explorer_refresh"
    FOLDER_EXPLORER_SET_SORT = "folder_explorer_set_sort"
    FOLDER_EXPLORER_SET_SEARCH = "folder_explorer_set_search"
    FOLDER_EXPLORER_OPEN = "folder_explorer_open"
    FOLDER_EXPLORER_OPEN_WITH = "folder_explorer_open_with"
    FOLDER_EXPLORER_OPEN_IN_NEW_WINDOW = "folder_explorer_open_in_new_window"
    FOLDER_EXPLORER_NEW_FOLDER = "folder_explorer_new_folder"
    FOLDER_EXPLORER_RENAME = "folder_explorer_rename"
    FOLDER_EXPLORER_DELETE = "folder_explorer_delete"
    FOLDER_EXPLORER_CUT = "folder_explorer_cut"
    FOLDER_EXPLORER_COPY = "folder_explorer_copy"
    FOLDER_EXPLORER_PASTE = "folder_explorer_paste"
    FOLDER_EXPLORER_COPY_PATH = "folder_explorer_copy_path"
    FOLDER_EXPLORER_PROPERTIES = "folder_explorer_properties"
    FOLDER_EXPLORER_SEND_TO_COREX_PATH_POINTER = "folder_explorer_send_to_corex_path_pointer"


@dataclass(frozen=True)
class GraphActionSpec:
    action_id: GraphActionId
    label: str | None
    shortcut: str | None
    surfaces: tuple[str, ...]
    destructive: bool = False
    required_payload_keys: tuple[str, ...] = ()


GRAPH_ACTION_SPECS: tuple[GraphActionSpec, ...] = (
    GraphActionSpec(
        GraphActionId.CONNECT_SELECTED,
        "Connect Selected",
        "Ctrl+Shift+L",
        ("pyqt_edit_menu", "pyqt_shortcut"),
    ),
    GraphActionSpec(
        GraphActionId.COPY_SELECTION,
        "Copy Selection",
        "Ctrl+C",
        ("pyqt_edit_menu", "pyqt_shortcut"),
    ),
    GraphActionSpec(
        GraphActionId.CUT_SELECTION,
        "Cut Selection",
        "Ctrl+X",
        ("pyqt_edit_menu", "pyqt_shortcut"),
        destructive=True,
    ),
    GraphActionSpec(
        GraphActionId.PASTE_SELECTION,
        "Paste Selection",
        "Ctrl+V",
        ("pyqt_edit_menu", "pyqt_shortcut"),
    ),
    GraphActionSpec(
        GraphActionId.DUPLICATE_SELECTION,
        "Duplicate Selection",
        "Ctrl+D",
        ("pyqt_edit_menu", "pyqt_shortcut"),
    ),
    GraphActionSpec(
        GraphActionId.DELETE_SELECTION,
        "Delete Selection",
        "Delete",
        ("qml_key_handler",),
        destructive=True,
    ),
    GraphActionSpec(
        GraphActionId.WRAP_SELECTION_IN_GROUP_BACKDROP,
        "Wrap Selection in Group",
        "C",
        (
            "pyqt_edit_menu",
            "pyqt_shortcut",
            "qml_selection_context_menu",
            "qml_selection_envelope_toolbar",
        ),
    ),
    GraphActionSpec(
        GraphActionId.GROUP_SELECTION,
        "Group Selection",
        "Ctrl+Alt+G",
        ("pyqt_edit_menu", "pyqt_shortcut"),
    ),
    GraphActionSpec(
        GraphActionId.UNGROUP_SELECTION,
        "Ungroup Selection",
        "Ctrl+Shift+G",
        ("pyqt_edit_menu", "pyqt_shortcut"),
        destructive=True,
    ),
    GraphActionSpec(
        GraphActionId.ALIGN_SELECTION_LEFT,
        "Align Left",
        None,
        ("pyqt_layout_menu", "qml_selection_context_menu", "qml_selection_envelope_toolbar"),
    ),
    GraphActionSpec(
        GraphActionId.ALIGN_SELECTION_RIGHT,
        "Align Right",
        None,
        ("pyqt_layout_menu", "qml_selection_context_menu", "qml_selection_envelope_toolbar"),
    ),
    GraphActionSpec(
        GraphActionId.ALIGN_SELECTION_TOP,
        "Align Top",
        None,
        ("pyqt_layout_menu", "qml_selection_context_menu", "qml_selection_envelope_toolbar"),
    ),
    GraphActionSpec(
        GraphActionId.ALIGN_SELECTION_BOTTOM,
        "Align Bottom",
        None,
        ("pyqt_layout_menu", "qml_selection_context_menu", "qml_selection_envelope_toolbar"),
    ),
    GraphActionSpec(
        GraphActionId.DISTRIBUTE_SELECTION_HORIZONTALLY,
        "Distribute Horizontally",
        None,
        ("pyqt_layout_menu", "qml_selection_context_menu", "qml_selection_envelope_toolbar"),
    ),
    GraphActionSpec(
        GraphActionId.DISTRIBUTE_SELECTION_VERTICALLY,
        "Distribute Vertically",
        None,
        ("pyqt_layout_menu", "qml_selection_context_menu", "qml_selection_envelope_toolbar"),
    ),
    GraphActionSpec(
        GraphActionId.SET_SELECTION_SAME_TYPE_WIDTH,
        "Set Same Width",
        None,
        ("qml_selection_context_menu",),
    ),
    GraphActionSpec(
        GraphActionId.SET_SELECTION_SAME_TYPE_HEIGHT,
        "Set Same Height",
        None,
        ("qml_selection_context_menu",),
    ),
    GraphActionSpec(
        GraphActionId.STRAIGHTEN_SELECTION_CONNECTIONS,
        "Straighten Connections",
        None,
        ("pyqt_layout_menu", "qml_selection_context_menu", "qml_selection_envelope_toolbar"),
    ),
    GraphActionSpec(
        GraphActionId.RUN_SELECTED,
        "Run Selected",
        None,
        (
            "qml_node_delegate_toolbar",
            "qml_node_context_menu",
            "qml_selection_context_menu",
            "qml_selection_envelope_toolbar",
        ),
    ),
    GraphActionSpec(
        GraphActionId.PREVIEW_SELECTED_RUN,
        "Preview Run",
        None,
        (
            "qml_node_context_menu",
            "qml_selection_context_menu",
            "qml_selection_envelope_toolbar",
        ),
    ),
    GraphActionSpec(
        GraphActionId.CONFIRM_SELECTED_RUN_PREVIEW,
        "Run",
        None,
        ("qml_selected_run_preview",),
    ),
    GraphActionSpec(
        GraphActionId.CLEAR_SELECTED_RUN_PREVIEW,
        "Cancel",
        None,
        ("qml_selected_run_preview",),
    ),
    GraphActionSpec(
        GraphActionId.OPEN_SELECTED_RUN_SETTINGS,
        "Run Settings...",
        None,
        ("qml_node_context_menu", "qml_selection_context_menu"),
    ),
    GraphActionSpec(
        GraphActionId.NAVIGATE_SCOPE_PARENT,
        "Scope Parent",
        "Alt+Left",
        ("pyqt_view_menu", "pyqt_shortcut", "qml_key_handler"),
    ),
    GraphActionSpec(
        GraphActionId.NAVIGATE_SCOPE_ROOT,
        "Scope Root",
        "Alt+Home",
        ("pyqt_view_menu", "pyqt_shortcut", "qml_key_handler"),
    ),
    GraphActionSpec(
        GraphActionId.OPEN_ADDON_MANAGER_FOR_NODE,
        "Open Add-On Manager",
        None,
        ("qml_node_context_menu",),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.OPEN_SUBNODE_SCOPE,
        "Enter Subnode",
        None,
        ("qml_node_context_menu", "qml_node_delegate"),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.PUBLISH_CUSTOM_WORKFLOW_FROM_NODE,
        "Add to Workflows",
        None,
        ("qml_node_context_menu",),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.OPEN_COMMENT_PEEK,
        "Peek Inside",
        None,
        ("qml_node_context_menu",),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.CLOSE_COMMENT_PEEK,
        "Exit Peek",
        None,
        ("qml_node_context_menu",),
    ),
    GraphActionSpec(
        GraphActionId.EDIT_PASSIVE_NODE_STYLE,
        "Edit Style...",
        None,
        ("qml_node_context_menu",),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.RESET_PASSIVE_NODE_STYLE,
        "Reset Style",
        None,
        ("qml_node_context_menu",),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.COPY_PASSIVE_NODE_STYLE,
        "Copy Style",
        None,
        ("qml_node_context_menu",),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.PASTE_PASSIVE_NODE_STYLE,
        "Paste Style",
        None,
        ("qml_node_context_menu",),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.PROPAGATE_PASSIVE_NODE_STYLE,
        "Propagate Style",
        None,
        ("qml_node_context_menu",),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.RENAME_NODE,
        "Rename Node",
        None,
        ("qml_node_context_menu", "qml_node_delegate"),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.SHOW_NODE_HELP,
        "Help",
        "F1",
        ("pyqt_shortcut", "qml_node_context_menu"),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.UNGROUP_NODE,
        "Ungroup Subnode",
        None,
        ("qml_node_context_menu",),
        destructive=True,
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.REMOVE_NODE,
        "Remove Node",
        None,
        ("qml_node_context_menu", "qml_node_delegate"),
        destructive=True,
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.DUPLICATE_NODE,
        "Duplicate Node",
        None,
        ("qml_node_delegate",),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.OPEN_NODE_PATH,
        "Open",
        None,
        ("qml_node_delegate",),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.OPEN_NODE_PATH_WITH,
        "Open with...",
        None,
        ("qml_node_delegate",),
        required_payload_keys=("node_id",),
    ),
    GraphActionSpec(
        GraphActionId.EDIT_FLOW_EDGE_STYLE,
        "Edit Flow Edge...",
        None,
        ("qml_edge_context_menu",),
        required_payload_keys=("edge_id",),
    ),
    GraphActionSpec(
        GraphActionId.EDIT_FLOW_EDGE_LABEL,
        "Edit Label...",
        None,
        ("qml_edge_context_menu",),
        required_payload_keys=("edge_id",),
    ),
    GraphActionSpec(
        GraphActionId.RESET_FLOW_EDGE_STYLE,
        "Reset Style",
        None,
        ("qml_edge_context_menu",),
        required_payload_keys=("edge_id",),
    ),
    GraphActionSpec(
        GraphActionId.COPY_FLOW_EDGE_STYLE,
        "Copy Style",
        None,
        ("qml_edge_context_menu",),
        required_payload_keys=("edge_id",),
    ),
    GraphActionSpec(
        GraphActionId.PASTE_FLOW_EDGE_STYLE,
        "Paste Style",
        None,
        ("qml_edge_context_menu",),
        required_payload_keys=("edge_id",),
    ),
    GraphActionSpec(
        GraphActionId.REMOVE_EDGE,
        "Remove Connection",
        None,
        ("qml_edge_context_menu",),
        destructive=True,
        required_payload_keys=("edge_id",),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_LIST,
        None,
        None,
        ("qml_folder_explorer_surface",),
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_NAVIGATE,
        None,
        None,
        ("qml_folder_explorer_surface",),
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_REFRESH,
        None,
        None,
        ("qml_folder_explorer_surface",),
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_SET_SORT,
        None,
        None,
        ("qml_folder_explorer_surface",),
        required_payload_keys=("node_id", "path", "sort_key"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_SET_SEARCH,
        None,
        None,
        ("qml_folder_explorer_surface",),
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_OPEN,
        "Open",
        None,
        ("qml_folder_explorer_context_menu",),
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_OPEN_WITH,
        "Open with...",
        None,
        ("qml_folder_explorer_context_menu",),
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_OPEN_IN_NEW_WINDOW,
        "Open in New Classic Explorer",
        None,
        ("qml_folder_explorer_context_menu",),
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_NEW_FOLDER,
        "New Folder",
        None,
        ("qml_folder_explorer_context_menu",),
        destructive=True,
        required_payload_keys=("node_id", "path", "name"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_RENAME,
        "Rename",
        None,
        ("qml_folder_explorer_context_menu",),
        destructive=True,
        required_payload_keys=("node_id", "path", "new_name"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_DELETE,
        "Delete",
        None,
        ("qml_folder_explorer_context_menu",),
        destructive=True,
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_CUT,
        "Cut",
        "Ctrl+X",
        ("qml_folder_explorer_context_menu",),
        destructive=True,
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_COPY,
        "Copy",
        "Ctrl+C",
        ("qml_folder_explorer_context_menu",),
        destructive=True,
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_PASTE,
        "Paste",
        "Ctrl+V",
        ("qml_folder_explorer_context_menu",),
        destructive=True,
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_COPY_PATH,
        "Copy Path",
        None,
        ("qml_folder_explorer_context_menu",),
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_PROPERTIES,
        "Properties",
        None,
        ("qml_folder_explorer_context_menu",),
        required_payload_keys=("node_id", "path"),
    ),
    GraphActionSpec(
        GraphActionId.FOLDER_EXPLORER_SEND_TO_COREX_PATH_POINTER,
        "Send to COREX as Path Pointer",
        None,
        ("qml_folder_explorer_context_menu", "qml_folder_explorer_drag"),
        required_payload_keys=("node_id", "path"),
    ),
)

GRAPH_ACTION_SPECS_BY_ID: dict[GraphActionId, GraphActionSpec] = {
    spec.action_id: spec for spec in GRAPH_ACTION_SPECS
}
GRAPH_ACTION_IDS: frozenset[str] = frozenset(spec.action_id.value for spec in GRAPH_ACTION_SPECS)

# P01 keeps the inventory exhaustive for current high-level QML action literals.
LOW_LEVEL_QML_ACTION_EXCEPTIONS: frozenset[str] = frozenset()


def graph_action_spec(action_id: GraphActionId | str) -> GraphActionSpec:
    return GRAPH_ACTION_SPECS_BY_ID[GraphActionId(action_id)]


def normalize_graph_action_payload(
    action_id: GraphActionId | str,
    payload: Mapping[str, object] | None = None,
) -> dict[str, object] | None:
    try:
        spec = graph_action_spec(action_id)
    except (TypeError, ValueError):
        return None
    if payload is None:
        normalized: dict[str, object] = {}
    elif isinstance(payload, Mapping):
        normalized = dict(payload)
    else:
        return None

    for key in spec.required_payload_keys:
        value = normalized.get(key)
        if not isinstance(value, str):
            return None
        normalized_value = value.strip()
        if not normalized_value:
            return None
        normalized[key] = normalized_value
    return normalized


def graph_action_metadata(spec: GraphActionSpec) -> dict[str, object]:
    return {
        "actionId": spec.action_id.value,
        "label": spec.label or "",
        "shortcut": spec.shortcut or "",
        "surfaces": list(spec.surfaces),
        "destructive": bool(spec.destructive),
        "requiredPayloadKeys": list(spec.required_payload_keys),
    }


__all__ = [
    "GRAPH_ACTION_IDS",
    "GRAPH_ACTION_SPECS",
    "GRAPH_ACTION_SPECS_BY_ID",
    "LOW_LEVEL_QML_ACTION_EXCEPTIONS",
    "GraphActionId",
    "GraphActionSpec",
    "graph_action_metadata",
    "graph_action_spec",
    "normalize_graph_action_payload",
]
