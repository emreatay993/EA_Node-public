from __future__ import annotations

"""Graph-canvas command bridge package.

The QML-facing ``GraphCanvasCommandBridge`` is composed from per-domain
plain-Python mixin modules; this composition root owns ONLY construction and
source resolution. New canvas commands are added as one ``@pyqtSlot`` in the
matching ``*_ops`` module (plus its protocol entry in the same file or
``protocols.py``) — not here.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal
from PyQt6.QtWidgets import QWidget

from ea_node_editor.ui.folder_explorer import FolderExplorerFilesystemService
from ea_node_editor.ui_qml.graph_canvas_command.annotation_style_ops import AnnotationStyleOps
from ea_node_editor.ui_qml.graph_canvas_command.canvas_host_ops import CanvasHostOps
from ea_node_editor.ui_qml.graph_canvas_command.folder_explorer_ops import (
    FolderExplorerOps,
    _FolderExplorerClipboardSource,
    _FolderExplorerConfirmationSource,
    _FolderExplorerOpenSource,
)
from ea_node_editor.ui_qml.graph_canvas_command.graphics_settings_ops import GraphicsSettingsOps
from ea_node_editor.ui_qml.graph_canvas_command.media_image_ops import MediaImageOps
from ea_node_editor.ui_qml.graph_canvas_command.media_video_ops import MediaVideoOps
from ea_node_editor.ui_qml.graph_canvas_command.node_creation_ops import NodeCreationOps
from ea_node_editor.ui_qml.graph_canvas_command.protocols import (
    _GraphCanvasGraphicsCommandSource,
    _GraphCanvasHostSource,
    _GraphCanvasSceneCommandSource,
    _GraphCanvasScenePolicySource,
)
from ea_node_editor.ui_qml.graph_canvas_command.scene_mutation_ops import SceneMutationOps
from ea_node_editor.ui_qml.graph_canvas_command.viewport_ops import ViewportOps

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.controllers.canvas_import_controller import CanvasImportController
    from ea_node_editor.ui.shell.controllers.app_preferences_controller import (
        AppPreferencesController,
    )
    from ea_node_editor.ui.shell.controllers.run_controller import RunController
    from ea_node_editor.ui.shell.controllers.workspace_drop_connect_controller import (
        WorkspaceDropConnectController,
    )
    from ea_node_editor.ui.shell.controllers.workspace_edit_controller import (
        WorkspaceEditController,
    )
    from ea_node_editor.ui.shell.media_panel_action_service import (
        MediaPanelActionService,
    )
    from ea_node_editor.ui.shell.presenters.graph_canvas_host_presenter import (
        GraphCanvasHostPresenter,
    )
    from ea_node_editor.ui.shell.presenters.inspector_presenter import (
        ShellInspectorPresenter,
    )
    from ea_node_editor.ui.shell.presenters.library_presenter import (
        ShellLibraryPresenter,
    )
    from ea_node_editor.ui.shell.window_search_scope_state import (
        WindowSearchScopeController,
    )
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
    from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge


def _resolve_scene_command_source(scene_bridge: object | None) -> _GraphCanvasSceneCommandSource | None:
    if scene_bridge is None:
        return None
    return cast(
        _GraphCanvasSceneCommandSource,
        getattr(scene_bridge, "command_bridge", scene_bridge),
    )


def _resolve_scene_policy_source(scene_bridge: object | None) -> _GraphCanvasScenePolicySource | None:
    if scene_bridge is None:
        return None
    return cast(
        _GraphCanvasScenePolicySource,
        getattr(scene_bridge, "policy_bridge", scene_bridge),
    )


class GraphCanvasCommandBridge(
    GraphicsSettingsOps,
    ViewportOps,
    SceneMutationOps,
    MediaImageOps,
    MediaVideoOps,
    NodeCreationOps,
    AnnotationStyleOps,
    CanvasHostOps,
    FolderExplorerOps,
    QObject,
):
    managedArtifactRenameReleaseRequested = pyqtSignal(str)
    managedArtifactRenameReleaseFinished = pyqtSignal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        search_scope_controller: "WindowSearchScopeController | None" = None,
        app_preferences_source: "AppPreferencesController | None" = None,
        graphics_preferences_changed_signal: object | None = None,
        run_controller: "RunController | None" = None,
        show_graph_hint: Callable[[str, int], None] | None = None,
        inspector_source: "ShellInspectorPresenter | None" = None,
        library_source: "ShellLibraryPresenter | None" = None,
        workspace_edit_controller: "WorkspaceEditController | None" = None,
        canvas_import_controller: "CanvasImportController | None" = None,
        workspace_drop_connect_controller: "WorkspaceDropConnectController | None" = None,
        model_provider: Callable[[], object] | None = None,
        active_workspace_id_provider: Callable[[], str] | None = None,
        workspace_navigation_controller: object | None = None,
        media_action_source: "MediaPanelActionService | None" = None,
        graphics_source: _GraphCanvasGraphicsCommandSource | None = None,
        host_source: "GraphCanvasHostPresenter | _GraphCanvasHostSource | None" = None,
        scene_bridge: "GraphSceneBridge | None" = None,
        view_bridge: "ViewportBridge | None" = None,
        folder_explorer_service: FolderExplorerFilesystemService | None = None,
        folder_explorer_confirmation_source: _FolderExplorerConfirmationSource | None = None,
        folder_explorer_clipboard_source: _FolderExplorerClipboardSource | None = None,
        folder_explorer_open_source: _FolderExplorerOpenSource | None = None,
    ) -> None:
        super().__init__(parent)
        self._scene_bridge = scene_bridge
        self._view_bridge = view_bridge
        self._search_scope_controller = search_scope_controller
        self._app_preferences_source = app_preferences_source
        self._graphics_preferences_changed_signal = graphics_preferences_changed_signal
        self._run_controller = run_controller
        self._show_graph_hint_callback = show_graph_hint
        self._inspector_source = inspector_source
        self._library_source = library_source
        self._workspace_edit_controller = workspace_edit_controller
        self._canvas_import_controller = canvas_import_controller
        self._workspace_drop_connect_controller = workspace_drop_connect_controller
        self._model_provider = model_provider
        self._active_workspace_id_provider = active_workspace_id_provider
        self._workspace_navigation_controller = workspace_navigation_controller
        self._dialog_parent = parent if isinstance(parent, QWidget) else None
        self._media_action_source = media_action_source
        self._graphics_source = graphics_source
        self._host_source = host_source
        self._scene_command_source = _resolve_scene_command_source(scene_bridge)
        self._scene_policy_source = _resolve_scene_policy_source(scene_bridge)
        self._folder_explorer_service = folder_explorer_service or FolderExplorerFilesystemService()
        self._folder_explorer_confirmation_source = folder_explorer_confirmation_source
        self._folder_explorer_clipboard_source = folder_explorer_clipboard_source
        self._folder_explorer_open_source = folder_explorer_open_source
        self._text_annotation_style_clipboard = ""

    @property
    def media_action_source(self) -> "MediaPanelActionService | None":
        return self._media_action_source

    @property
    def graphics_source(self) -> _GraphCanvasGraphicsCommandSource | None:
        return self._graphics_source

    @property
    def host_source(self) -> _GraphCanvasHostSource | None:
        return self._host_source

    @property
    def scene_bridge(self) -> "GraphSceneBridge | None":
        return self._scene_bridge

    @property
    def scene_command_source(self) -> _GraphCanvasSceneCommandSource | None:
        return self._scene_command_source

    @property
    def scene_policy_source(self) -> _GraphCanvasScenePolicySource | None:
        return self._scene_policy_source

    @property
    def view_bridge(self) -> "ViewportBridge | None":
        return self._view_bridge

    @pyqtProperty(QObject, constant=True)
    def viewport_bridge(self) -> "ViewportBridge | None":
        return self._view_bridge


__all__ = [
    "GraphCanvasCommandBridge",
]
