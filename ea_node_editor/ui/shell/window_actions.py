from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence

from ea_node_editor.ui.icon_registry import qicon
from ea_node_editor.ui.shell.graph_action_contracts import GraphActionId, graph_action_spec
from ea_node_editor.ui.shell.tooltip_policy import TOOLTIP_CATEGORY_GENERAL

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


def format_recent_project_menu_label(index: int, project_path: str) -> str:
    path = Path(project_path)
    parent = str(path.parent)
    if not parent or parent == ".":
        return f"{index}. {path.name}"
    return f"{index}. {path.name} [{parent}]"


def _trigger_graph_action(window: ShellWindow, action_id: GraphActionId) -> bool:
    controller = getattr(window, "graph_action_controller", None)
    if controller is None:
        return False
    return bool(controller.trigger(action_id.value))


def _create_graph_action(window: ShellWindow, action_id: GraphActionId) -> QAction:
    spec = graph_action_spec(action_id)
    action = QAction(str(spec.label or action_id.value), window)
    if spec.shortcut is not None:
        action.setShortcut(QKeySequence(spec.shortcut))
    action.triggered.connect(
        lambda _checked=False, selected_action_id=action_id: _trigger_graph_action(window, selected_action_id)
    )
    return action


def _open_canvas_quick_insert(window: "ShellWindow") -> None:
    if not hasattr(window, "request_open_canvas_quick_insert"):
        return
    view = getattr(window, "view", None)
    scene_x = 0.0
    scene_y = 0.0
    overlay_x = 0.0
    overlay_y = 0.0
    if view is not None:
        scene_x = float(getattr(view, "center_x", 0.0) or 0.0)
        scene_y = float(getattr(view, "center_y", 0.0) or 0.0)
        rect_getter = getattr(view, "rect", None)
        rect = rect_getter() if callable(rect_getter) else None
        if rect is not None:
            overlay_x = float(getattr(rect, "width", lambda: 0.0)() or 0.0) * 0.5
            overlay_y = float(getattr(rect, "height", lambda: 0.0)() or 0.0) * 0.5
    if not isinstance(scene_x, float) or not math.isfinite(scene_x):
        scene_x = 0.0
    if not isinstance(scene_y, float) or not math.isfinite(scene_y):
        scene_y = 0.0
    if not isinstance(overlay_x, float) or not math.isfinite(overlay_x):
        overlay_x = 0.0
    if not isinstance(overlay_y, float) or not math.isfinite(overlay_y):
        overlay_y = 0.0
    window.request_open_canvas_quick_insert(scene_x, scene_y, overlay_x, overlay_y)


def _recent_project_tooltip_text(window: ShellWindow, project_path: str) -> str:
    tooltip_manager = getattr(window, "tooltip_manager", None)
    if tooltip_manager is None:
        return project_path
    should_show_tooltip = getattr(tooltip_manager, "should_show_info_tooltip", None)
    if not callable(should_show_tooltip):
        return project_path
    if should_show_tooltip(project_path):
        return project_path
    # QAction falls back to its text when the tooltip is set to an empty string.
    return " "


def refresh_recent_projects_menu(window: ShellWindow) -> None:
    menu = getattr(window, "menu_recent_projects", None)
    if menu is None:
        return
    menu.clear()
    recent_paths = list(window.recent_project_paths)
    if not recent_paths:
        empty_action = menu.addAction("No Recent Files")
        empty_action.setEnabled(False)
        return

    current_project_path = window.project_session_controller._normalize_project_path(window.project_path)
    for index, project_path in enumerate(recent_paths, start=1):
        action = menu.addAction(format_recent_project_menu_label(index, project_path))
        action.setToolTip(_recent_project_tooltip_text(window, project_path))
        action.setStatusTip(project_path)
        action.triggered.connect(
            lambda _checked=False, selected_path=project_path: window._open_project_path(selected_path)
        )
        if current_project_path and project_path == current_project_path:
            action.setEnabled(False)
    menu.addSeparator()
    menu.addAction(window.action_clear_recent_projects)


def create_window_actions(window: ShellWindow) -> None:
    window.action_new_project = QAction("New Project", window)
    window.action_new_project.setShortcut(QKeySequence.StandardKey.New)
    window.action_new_project.triggered.connect(window._new_project)

    window.action_new_workspace = QAction("New Workspace", window)
    window.action_new_workspace.setShortcut(QKeySequence("Ctrl+Shift+N"))
    window.action_new_workspace.triggered.connect(
        window.workspace_navigation_controller.create_workspace
    )

    window.action_save_project = QAction("Save Project", window)
    window.action_save_project.setShortcut(QKeySequence.StandardKey.Save)
    window.action_save_project.triggered.connect(window._save_project)

    window.action_save_project_as = QAction("Save Project As...", window)
    window.action_save_project_as.setShortcut(QKeySequence.StandardKey.SaveAs)
    window.action_save_project_as.triggered.connect(window._save_project_as)

    window.action_project_files = QAction("Project Files...", window)
    window.action_project_files.triggered.connect(window._show_project_files)

    window.action_open_project = QAction("Open Project", window)
    window.action_open_project.setShortcut(QKeySequence.StandardKey.Open)
    window.action_open_project.triggered.connect(window._open_project)

    window.action_new_plugin = QAction("New Plugin...", window)
    window.action_new_plugin.triggered.connect(window.show_plugin_authoring_dialog)

    window.action_reload_plugins = QAction("Reload Plugins", window)
    window.action_reload_plugins.triggered.connect(window.reload_plugins)

    window.action_clear_recent_projects = QAction("Clear Recent Files", window)
    window.action_clear_recent_projects.triggered.connect(window._clear_recent_projects)

    window.action_workflow_settings = QAction("Workflow Settings", window)
    window.action_workflow_settings.setShortcut(QKeySequence("Ctrl+,"))
    window.action_workflow_settings.triggered.connect(window.show_workflow_settings_dialog)

    window.action_graphics_settings = QAction("Graphics Settings", window)
    window.action_graphics_settings.triggered.connect(window.show_graphics_settings_dialog)

    window.action_keyboard_mouse_reference = QAction("Keyboard and Mouse Reference", window)
    window.action_keyboard_mouse_reference.triggered.connect(window.show_keyboard_mouse_reference_dialog)

    window.action_third_party_notices = QAction("Third-Party Notices", window)
    window.action_third_party_notices.triggered.connect(window.show_third_party_notices_dialog)

    window.action_addon_manager = QAction("Add-On Manager", window)
    window.action_addon_manager.triggered.connect(window.request_open_addon_manager)

    window.action_toggle_script_editor = QAction("Script Editor", window)
    window.action_toggle_script_editor.setCheckable(True)
    window.action_toggle_script_editor.setShortcut(QKeySequence("Ctrl+Shift+E"))
    window.action_toggle_script_editor.triggered.connect(window.set_script_editor_panel_visible)

    window.action_run = QAction("Run", window)
    window.action_run.setIcon(qicon("run"))
    window.action_run.setShortcut(QKeySequence("F5"))
    window.action_run.triggered.connect(window.run_controller.run_workflow)

    window.action_stop = QAction("Stop", window)
    window.action_stop.setIcon(qicon("stop"))
    window.action_stop.setShortcut(QKeySequence("Shift+F5"))
    window.action_stop.triggered.connect(window._stop_workflow)

    window.action_pause = QAction("Pause", window)
    window.action_pause.setIcon(qicon("pause"))
    window.action_pause.setShortcut(QKeySequence("F6"))
    window.action_pause.triggered.connect(window._toggle_pause_resume)

    # Hidden developer-mode toggle. The shortcut only has an effect when the
    # COREX_DEV_MODE env capability was set at startup; otherwise it is inert.
    window.action_toggle_developer_mode = QAction("Toggle Developer Mode", window)
    window.action_toggle_developer_mode.setShortcut(QKeySequence("Ctrl+Alt+Shift+D"))
    window.action_toggle_developer_mode.triggered.connect(window._toggle_developer_mode)

    window.action_connect_selected = _create_graph_action(window, GraphActionId.CONNECT_SELECTED)

    window.action_duplicate_selection = _create_graph_action(window, GraphActionId.DUPLICATE_SELECTION)

    window.action_wrap_selection_in_group_backdrop = _create_graph_action(
        window,
        GraphActionId.WRAP_SELECTION_IN_GROUP_BACKDROP,
    )

    window.action_group_selection = _create_graph_action(window, GraphActionId.GROUP_SELECTION)

    window.action_ungroup_selection = _create_graph_action(window, GraphActionId.UNGROUP_SELECTION)

    window.action_align_left = _create_graph_action(window, GraphActionId.ALIGN_SELECTION_LEFT)

    window.action_align_right = _create_graph_action(window, GraphActionId.ALIGN_SELECTION_RIGHT)

    window.action_align_top = _create_graph_action(window, GraphActionId.ALIGN_SELECTION_TOP)

    window.action_align_bottom = _create_graph_action(window, GraphActionId.ALIGN_SELECTION_BOTTOM)

    window.action_distribute_horizontally = _create_graph_action(
        window,
        GraphActionId.DISTRIBUTE_SELECTION_HORIZONTALLY,
    )

    window.action_distribute_vertically = _create_graph_action(
        window,
        GraphActionId.DISTRIBUTE_SELECTION_VERTICALLY,
    )

    window.action_straighten_connections = _create_graph_action(
        window,
        GraphActionId.STRAIGHTEN_SELECTION_CONNECTIONS,
    )

    window.action_snap_to_grid = QAction("Snap to Grid", window)
    window.action_snap_to_grid.setCheckable(True)
    window.action_snap_to_grid.setChecked(False)
    window.action_snap_to_grid.toggled.connect(window.set_snap_to_grid_enabled)

    window.action_interact_with_locked_objects = QAction("Interact with Locked Objects", window)
    window.action_interact_with_locked_objects.setCheckable(True)
    window.action_interact_with_locked_objects.setChecked(False)
    window.action_interact_with_locked_objects.setShortcut(QKeySequence("Ctrl+L"))
    window.action_interact_with_locked_objects.toggled.connect(window.set_interact_with_locked_objects)

    window.action_show_port_labels = QAction("Port Labels", window)
    window.action_show_port_labels.setCheckable(True)
    window.action_show_port_labels.setChecked(True)
    window.action_show_port_labels.toggled.connect(window.set_graphics_show_port_labels)

    window.action_general_help_tooltips = QAction("General Help Tooltips", window)
    window.action_general_help_tooltips.setCheckable(True)
    window.action_general_help_tooltips.setChecked(True)
    window.action_general_help_tooltips.toggled.connect(
        lambda checked=False: window.set_graphics_tooltip_category_enabled(
            TOOLTIP_CATEGORY_GENERAL,
            bool(checked),
        )
    )
    window.action_general_help_tooltips.toggled.connect(lambda _checked=False: refresh_recent_projects_menu(window))

    window.action_undo = QAction("Undo", window)
    window.action_undo.setShortcut(QKeySequence("Ctrl+Z"))
    window.action_undo.triggered.connect(window.workspace_edit_controller.undo)

    window.action_redo = QAction("Redo", window)
    window.action_redo.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
    window.action_redo.triggered.connect(window.workspace_edit_controller.redo)

    window.action_copy_selection = _create_graph_action(window, GraphActionId.COPY_SELECTION)

    window.action_cut_selection = _create_graph_action(window, GraphActionId.CUT_SELECTION)

    window.action_paste_selection = _create_graph_action(window, GraphActionId.PASTE_SELECTION)

    window.action_frame_all = QAction("Frame All", window)
    window.action_frame_all.setShortcut(QKeySequence("A"))
    window.action_frame_all.triggered.connect(
        window.workspace_navigation_controller.frame_all
    )

    window.action_frame_selection = QAction("Frame Selection", window)
    window.action_frame_selection.setShortcut(QKeySequence("F"))
    window.action_frame_selection.triggered.connect(
        window.workspace_navigation_controller.frame_selection
    )

    window.action_center_selection = QAction("Center Selection", window)
    window.action_center_selection.setShortcut(QKeySequence("Shift+F"))
    window.action_center_selection.triggered.connect(
        window.workspace_navigation_controller.center_on_selection
    )

    window.action_scope_parent = _create_graph_action(window, GraphActionId.NAVIGATE_SCOPE_PARENT)

    window.action_scope_root = _create_graph_action(window, GraphActionId.NAVIGATE_SCOPE_ROOT)

    window.action_graph_search = QAction("Graph Search", window)
    window.action_graph_search.setShortcut(QKeySequence("Ctrl+K"))
    window.action_graph_search.triggered.connect(window.request_open_graph_search)

    window.action_node_browser = QAction("Node Browser", window)
    window.action_node_browser.setShortcut(QKeySequence("Ctrl+B"))
    window.action_node_browser.triggered.connect(lambda _checked=False: _open_canvas_quick_insert(window))

    window.action_show_help = _create_graph_action(window, GraphActionId.SHOW_NODE_HELP)

    window.action_new_view = QAction("New View", window)
    window.action_new_view.setShortcut(QKeySequence("Ctrl+Shift+V"))
    window.action_new_view.triggered.connect(
        window.workspace_navigation_controller.create_view
    )

    window.action_duplicate_workspace = QAction("Duplicate Workspace", window)
    window.action_duplicate_workspace.setShortcut(QKeySequence("Ctrl+Shift+D"))
    window.action_duplicate_workspace.triggered.connect(
        window.workspace_navigation_controller.duplicate_active_workspace
    )

    window.action_rename_workspace = QAction("Rename Workspace", window)
    window.action_rename_workspace.setShortcut(QKeySequence("F2"))
    window.action_rename_workspace.triggered.connect(
        window.workspace_navigation_controller.rename_active_workspace
    )

    window.action_close_workspace = QAction("Close Workspace", window)
    window.action_close_workspace.setShortcut(QKeySequence.StandardKey.Close)
    window.action_close_workspace.triggered.connect(
        window.workspace_navigation_controller.close_active_workspace
    )

    window.action_next_workspace = QAction("Next Workspace", window)
    window.action_next_workspace.setShortcuts([QKeySequence("Ctrl+Tab"), QKeySequence("Ctrl+PgDown")])
    window.action_next_workspace.triggered.connect(
        lambda: window.workspace_navigation_controller.switch_workspace_by_offset(1)
    )

    window.action_prev_workspace = QAction("Previous Workspace", window)
    window.action_prev_workspace.setShortcuts([QKeySequence("Ctrl+Shift+Tab"), QKeySequence("Ctrl+PgUp")])
    window.action_prev_workspace.triggered.connect(
        lambda: window.workspace_navigation_controller.switch_workspace_by_offset(-1)
    )

    window.action_import_node_package = QAction("Import Node Package...", window)
    window.action_import_node_package.triggered.connect(
        window.workspace_package_io_controller.import_node_package
    )

    window.action_export_node_package = QAction("Export Node Package...", window)
    window.action_export_node_package.triggered.connect(
        window.workspace_package_io_controller.export_node_package
    )

    window.action_import_custom_workflow = QAction("Import Custom Workflow...", window)
    window.action_import_custom_workflow.triggered.connect(
        window.workspace_package_io_controller.import_custom_workflow
    )

    window.action_export_custom_workflow = QAction("Export Custom Workflow...", window)
    window.action_export_custom_workflow.triggered.connect(
        window.workspace_package_io_controller.export_custom_workflow
    )

    window.action_export_canvas_views = QAction("Export Canvas Views...", window)
    window.action_export_canvas_views.triggered.connect(window._export_canvas_views)

    window.action_export_project_review_deck = QAction("Export Project Review Deck...", window)
    window.action_export_project_review_deck.triggered.connect(window._export_project_review_deck)

    for action in (
        window.action_new_project,
        window.action_new_workspace,
        window.action_save_project,
        window.action_save_project_as,
        window.action_project_files,
        window.action_open_project,
        window.action_new_plugin,
        window.action_reload_plugins,
        window.action_clear_recent_projects,
        window.action_workflow_settings,
        window.action_graphics_settings,
        window.action_keyboard_mouse_reference,
        window.action_third_party_notices,
        window.action_addon_manager,
        window.action_toggle_script_editor,
        window.action_run,
        window.action_stop,
        window.action_pause,
        window.action_toggle_developer_mode,
        window.action_undo,
        window.action_redo,
        window.action_copy_selection,
        window.action_cut_selection,
        window.action_paste_selection,
        window.action_connect_selected,
        window.action_duplicate_selection,
        window.action_wrap_selection_in_group_backdrop,
        window.action_group_selection,
        window.action_ungroup_selection,
        window.action_align_left,
        window.action_align_right,
        window.action_align_top,
        window.action_align_bottom,
        window.action_distribute_horizontally,
        window.action_distribute_vertically,
        window.action_straighten_connections,
        window.action_snap_to_grid,
        window.action_interact_with_locked_objects,
        window.action_show_port_labels,
        window.action_general_help_tooltips,
        window.action_frame_all,
        window.action_frame_selection,
        window.action_center_selection,
        window.action_scope_parent,
        window.action_scope_root,
        window.action_graph_search,
        window.action_node_browser,
        window.action_show_help,
        window.action_new_view,
        window.action_duplicate_workspace,
        window.action_rename_workspace,
        window.action_close_workspace,
        window.action_next_workspace,
        window.action_prev_workspace,
        window.action_import_custom_workflow,
        window.action_export_custom_workflow,
        window.action_import_node_package,
        window.action_export_node_package,
        window.action_export_canvas_views,
        window.action_export_project_review_deck,
    ):
        action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        window.addAction(action)


def build_window_menu_bar(window: ShellWindow) -> None:
    menu_bar = window.menuBar()
    menu_bar.clear()

    file_menu = menu_bar.addMenu("&File")
    file_menu.addAction(window.action_new_project)
    file_menu.addAction(window.action_open_project)
    window.menu_recent_projects = file_menu.addMenu("Open Recent")
    window.menu_recent_projects.aboutToShow.connect(window._refresh_recent_projects_menu)
    refresh_recent_projects_menu(window)
    file_menu.addAction(window.action_save_project)
    file_menu.addAction(window.action_save_project_as)
    file_menu.addAction(window.action_project_files)
    file_menu.addSeparator()
    file_menu.addAction(window.action_new_plugin)
    file_menu.addAction(window.action_reload_plugins)
    file_menu.addSeparator()
    file_menu.addAction(window.action_import_custom_workflow)
    file_menu.addAction(window.action_export_custom_workflow)
    file_menu.addAction(window.action_export_canvas_views)
    file_menu.addAction(window.action_export_project_review_deck)
    file_menu.addSeparator()
    file_menu.addAction(window.action_import_node_package)
    file_menu.addAction(window.action_export_node_package)

    edit_menu = menu_bar.addMenu("&Edit")
    edit_menu.addAction(window.action_undo)
    edit_menu.addAction(window.action_redo)
    edit_menu.addSeparator()
    edit_menu.addAction(window.action_copy_selection)
    edit_menu.addAction(window.action_cut_selection)
    edit_menu.addAction(window.action_paste_selection)
    edit_menu.addSeparator()
    edit_menu.addAction(window.action_connect_selected)
    edit_menu.addAction(window.action_duplicate_selection)
    edit_menu.addAction(window.action_wrap_selection_in_group_backdrop)
    edit_menu.addAction(window.action_group_selection)
    edit_menu.addAction(window.action_ungroup_selection)
    layout_menu = edit_menu.addMenu("Layout")
    layout_menu.addAction(window.action_align_left)
    layout_menu.addAction(window.action_align_right)
    layout_menu.addAction(window.action_align_top)
    layout_menu.addAction(window.action_align_bottom)
    layout_menu.addSeparator()
    layout_menu.addAction(window.action_distribute_horizontally)
    layout_menu.addAction(window.action_distribute_vertically)
    layout_menu.addSeparator()
    layout_menu.addAction(window.action_straighten_connections)
    edit_menu.addAction(window.action_snap_to_grid)
    edit_menu.addSeparator()
    edit_menu.addAction(window.action_graph_search)
    edit_menu.addSeparator()
    edit_menu.addAction(window.action_interact_with_locked_objects)

    view_menu = menu_bar.addMenu("&View")
    view_menu.addAction(window.action_node_browser)
    view_menu.addSeparator()
    view_menu.addAction(window.action_toggle_script_editor)
    view_menu.addAction(window.action_show_port_labels)
    view_menu.addAction(window.action_general_help_tooltips)
    view_menu.addSeparator()
    view_menu.addAction(window.action_frame_all)
    view_menu.addAction(window.action_frame_selection)
    view_menu.addAction(window.action_center_selection)
    view_menu.addSeparator()
    view_menu.addAction(window.action_scope_parent)
    view_menu.addAction(window.action_scope_root)

    run_menu = menu_bar.addMenu("&Run")
    run_menu.addAction(window.action_run)
    run_menu.addAction(window.action_pause)
    run_menu.addAction(window.action_stop)

    workspace_menu = menu_bar.addMenu("&Workspace")
    workspace_menu.addAction(window.action_new_workspace)
    workspace_menu.addAction(window.action_new_view)
    workspace_menu.addAction(window.action_duplicate_workspace)
    workspace_menu.addAction(window.action_rename_workspace)
    workspace_menu.addAction(window.action_close_workspace)
    workspace_menu.addSeparator()
    workspace_menu.addAction(window.action_next_workspace)
    workspace_menu.addAction(window.action_prev_workspace)

    menu_bar.addAction(window.action_addon_manager)

    settings_menu = menu_bar.addMenu("&Settings")
    settings_menu.addAction(window.action_workflow_settings)
    settings_menu.addAction(window.action_graphics_settings)

    help_menu = menu_bar.addMenu("&Help")
    help_menu.addAction(window.action_keyboard_mouse_reference)
    help_menu.addAction(window.action_third_party_notices)
