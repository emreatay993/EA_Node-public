from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.persistence.session_store import SessionAutosaveStore
from ea_node_editor.telemetry.startup_profile import phase
from ea_node_editor.ui.graph_interactions import GraphInteractions
from ea_node_editor.ui.icon_registry import UiIconImageProvider, UiIconRegistryBridge
from ea_node_editor.ui.image_value_preview_provider import (
    set_active_image_value_preview_provider,
)
from ea_node_editor.ui.media_preview_provider import LocalMediaPreviewImageProvider
from ea_node_editor.ui.pdf_preview_provider import LocalPdfPreviewImageProvider
from ea_node_editor.ui.plot_preview_cache_provider import (
    PlotPreviewCacheImageProvider,
    ViewerPreviewCacheImageProvider,
)
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
from ea_node_editor.ui.shell.workspace_flow import ShellWorkspaceManagerAdapter
from ea_node_editor.ui_qml.console_model import ConsoleModel
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.script_editor_model import ScriptEditorModel
from ea_node_editor.ui_qml.syntax_bridge import QmlScriptSyntaxBridge
from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge
from ea_node_editor.ui_qml.workspace_tabs_model import WorkspaceTabsModel
from ea_node_editor.workspace.manager import WorkspaceManager

if TYPE_CHECKING:
    from ea_node_editor.nodes.registry import NodeRegistry
    from ea_node_editor.ui.shell.composition.state import ShellStateDependencies
    from ea_node_editor.ui.shell.window import ShellWindow


@dataclass(frozen=True, slots=True)
class ShellPrimitiveDependencies:
    registry: object
    serializer: JsonProjectSerializer
    _session_store: object
    session_store: object
    model: GraphModel
    workspace_manager: WorkspaceManager
    runtime_history: RuntimeGraphHistory
    scene: GraphSceneBridge
    view: ViewportBridge
    _graph_interactions: GraphInteractions
    graph_interactions: GraphInteractions
    console_panel: ConsoleModel
    script_editor: ScriptEditorModel
    script_highlighter: QmlScriptSyntaxBridge
    workspace_tabs: WorkspaceTabsModel
    ui_icons: UiIconRegistryBridge
    _ui_icon_image_provider: UiIconImageProvider
    _local_media_preview_provider: LocalMediaPreviewImageProvider
    _local_pdf_preview_provider: LocalPdfPreviewImageProvider
    _plot_preview_cache_provider: PlotPreviewCacheImageProvider
    _viewer_preview_cache_provider: ViewerPreviewCacheImageProvider

    def attach(self, host: "ShellWindow") -> None:
        host.registry = self.registry
        host.serializer = self.serializer
        host._session_store = self._session_store
        host.session_store = self.session_store
        host.model = self.model
        host.workspace_manager = self.workspace_manager
        host.runtime_history = self.runtime_history
        host.scene = self.scene
        host.view = self.view
        host._graph_interactions = self._graph_interactions
        host.graph_interactions = self.graph_interactions
        host.console_panel = self.console_panel
        host.script_editor = self.script_editor
        host.script_highlighter = self.script_highlighter
        host.workspace_tabs = self.workspace_tabs
        host.ui_icons = self.ui_icons
        host._ui_icon_image_provider = self._ui_icon_image_provider
        host._local_media_preview_provider = self._local_media_preview_provider
        host._local_pdf_preview_provider = self._local_pdf_preview_provider
        host._plot_preview_cache_provider = self._plot_preview_cache_provider
        host._viewer_preview_cache_provider = self._viewer_preview_cache_provider


def _recent_session_path():
    # Deliberately indirect through the window module: tests patch
    # ea_node_editor.ui.shell.window.recent_session_path.
    from ea_node_editor.ui.shell import window as shell_window_module

    return shell_window_module.recent_session_path()


def _autosave_project_path():
    # Deliberately indirect through the window module: tests patch
    # ea_node_editor.ui.shell.window.autosave_project_path.
    from ea_node_editor.ui.shell import window as shell_window_module

    return shell_window_module.autosave_project_path()


def _create_shell_session_store(serializer: Any) -> SessionAutosaveStore:
    return SessionAutosaveStore(
        serializer=serializer,
        session_path_provider=_recent_session_path,
        autosave_path_provider=_autosave_project_path,
    )


def create_primitive_dependencies(
    host: "ShellWindow",
    state: "ShellStateDependencies",
    *,
    registry: "NodeRegistry | None" = None,
    preferences_document: Any = None,
) -> ShellPrimitiveDependencies:
    with phase("prim.build_default_registry"):
        if registry is None:
            registry = build_default_registry(preferences_document=preferences_document)
    with phase("prim.JsonProjectSerializer"):
        serializer = JsonProjectSerializer(registry)
    with phase("prim.session_store"):
        session_store = _create_shell_session_store(serializer)
    with phase("prim.GraphModel"):
        model = GraphModel(ProjectData(project_id="proj_local", name="untitled"))
    with phase("prim.WorkspaceManager"):
        workspace_manager = ShellWorkspaceManagerAdapter(WorkspaceManager(model), model)
    with phase("prim.RuntimeGraphHistory"):
        runtime_history = RuntimeGraphHistory()
    with phase("prim.GraphSceneBridge"):
        scene = GraphSceneBridge(host)
        scene.bind_runtime_history(runtime_history)
    with phase("prim.ViewportBridge"):
        view = ViewportBridge(host)
    with phase("prim.GraphInteractions"):
        graph_interactions = GraphInteractions(
            scene=scene,
            registry=registry,
            history=runtime_history,
        )
    with phase("prim.ConsoleModel"):
        console_panel = ConsoleModel(host)
    with phase("prim.ScriptEditorModel"):
        script_editor = ScriptEditorModel(host)
    with phase("prim.QmlScriptSyntaxBridge"):
        script_highlighter = QmlScriptSyntaxBridge(host)
    with phase("prim.WorkspaceTabsModel"):
        workspace_tabs = WorkspaceTabsModel(host)
    with phase("prim.UiIconRegistryBridge"):
        ui_icons = UiIconRegistryBridge(host)
    with phase("prim.UiIconImageProvider"):
        ui_icon_image_provider = UiIconImageProvider()
    with phase("prim.LocalMediaPreviewImageProvider"):
        local_media_preview_provider = LocalMediaPreviewImageProvider()
    with phase("prim.LocalPdfPreviewImageProvider"):
        local_pdf_preview_provider = LocalPdfPreviewImageProvider()
    with phase("prim.PlotPreviewCacheImageProvider"):
        plot_preview_cache_provider = PlotPreviewCacheImageProvider()
    with phase("prim.ViewerPreviewCacheImageProvider"):
        viewer_preview_cache_provider = ViewerPreviewCacheImageProvider()
        set_active_image_value_preview_provider(viewer_preview_cache_provider)
    return ShellPrimitiveDependencies(
        registry=registry,
        serializer=serializer,
        _session_store=session_store,
        session_store=session_store,
        model=model,
        workspace_manager=workspace_manager,
        runtime_history=runtime_history,
        scene=scene,
        view=view,
        _graph_interactions=graph_interactions,
        graph_interactions=graph_interactions,
        console_panel=console_panel,
        script_editor=script_editor,
        script_highlighter=script_highlighter,
        workspace_tabs=workspace_tabs,
        ui_icons=ui_icons,
        _ui_icon_image_provider=ui_icon_image_provider,
        _local_media_preview_provider=local_media_preview_provider,
        _local_pdf_preview_provider=local_pdf_preview_provider,
        _plot_preview_cache_provider=plot_preview_cache_provider,
        _viewer_preview_cache_provider=viewer_preview_cache_provider,
    )


__all__ = [
    "ShellPrimitiveDependencies",
    "create_primitive_dependencies",
]
