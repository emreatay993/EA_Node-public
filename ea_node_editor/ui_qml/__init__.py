from __future__ import annotations


def register_qml_types() -> None:
    from ea_node_editor.ui_qml.shell_addon_manager_bridge import register_qml_types as register_addon_manager_qml_types
    from ea_node_editor.ui_qml.tabular_preview_table_model import register_qml_types as register_tabular_model_qml_types

    register_addon_manager_qml_types()
    register_tabular_model_qml_types()

from ea_node_editor.ui_qml.console_model import ConsoleModel
from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.script_editor_model import ScriptEditorModel
from ea_node_editor.ui_qml.status_model import StatusItemModel
from ea_node_editor.ui_qml.tabular_preview_table_model import TabularPreviewTableModel
from ea_node_editor.ui_qml.theme_bridge import ThemeBridge
from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge
from ea_node_editor.ui_qml.workspace_tabs_model import WorkspaceTabsModel

register_qml_types()

__all__ = [
    "ConsoleModel",
    "GraphThemeBridge",
    "GraphSceneBridge",
    "ViewportBridge",
    "ScriptEditorModel",
    "StatusItemModel",
    "TabularPreviewTableModel",
    "ThemeBridge",
    "WorkspaceTabsModel",
    "register_qml_types",
]
