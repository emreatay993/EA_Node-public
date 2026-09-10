from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ea_node_editor.ui.shell.media_panel_action_service import MediaPanelActionService
from ea_node_editor.ui.support.solution_output_cache import current_output_value
from ea_node_editor.ui_qml.content_fullscreen_bridge import ContentFullscreenBridge
from ea_node_editor.ui_qml.jupyter_server_bridge import JupyterServerBridge
from ea_node_editor.ui_qml.native_folder_explorer_host_service import NativeFolderExplorerHostService
from ea_node_editor.ui_qml.plot_auto_preview_service import PlotAutoPreviewService
from ea_node_editor.ui_qml.plot_host_service import PlotHostService
from ea_node_editor.ui_qml.viewer_host_service import ViewerHostService
from ea_node_editor.ui_qml.viewer_control_bridge import ViewerControlBridge
from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge
from ea_node_editor.web_host.bridge import WebSurfaceArtifactService

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.composition.controllers import (
        ShellControllerDependencies,
    )
    from ea_node_editor.ui.shell.composition.library_workspace import (
        ShellLibraryWorkspaceDependencies,
    )
    from ea_node_editor.ui.shell.composition.presenters import (
        ShellPresenterDependencies,
    )
    from ea_node_editor.ui.shell.composition.preferences import (
        ShellPreferencesThemeStatusDependencies,
    )
    from ea_node_editor.ui.shell.composition.primitives import ShellPrimitiveDependencies
    from ea_node_editor.ui.shell.composition.state import ShellStateDependencies
    from ea_node_editor.ui.shell.window import ShellWindow


@dataclass(frozen=True, slots=True)
class ShellRuntimeDependencies:
    media_panel_action_service: MediaPanelActionService
    content_fullscreen_bridge: ContentFullscreenBridge
    viewer_session_bridge: ViewerSessionBridge
    viewer_control_bridge: ViewerControlBridge
    viewer_host_service: ViewerHostService
    plot_host_service: PlotHostService
    plot_auto_preview_service: PlotAutoPreviewService
    native_folder_explorer_host_service: NativeFolderExplorerHostService
    jupyter_server_bridge: JupyterServerBridge

    def attach(self, host: "ShellWindow") -> None:
        host.media_panel_action_service = self.media_panel_action_service
        host.content_fullscreen_bridge = self.content_fullscreen_bridge
        host.viewer_session_bridge = self.viewer_session_bridge
        host.viewer_control_bridge = self.viewer_control_bridge
        host.viewer_host_service = self.viewer_host_service
        host.plot_host_service = self.plot_host_service
        host.plot_auto_preview_service = self.plot_auto_preview_service
        host.native_folder_explorer_host_service = self.native_folder_explorer_host_service
        host.jupyter_server_bridge = self.jupyter_server_bridge


def create_viewer_service_dependencies(
    host: "ShellWindow",
    state: "ShellStateDependencies",
    primitives: "ShellPrimitiveDependencies",
    preferences: "ShellPreferencesThemeStatusDependencies",
    library_workspace: "ShellLibraryWorkspaceDependencies",
    controllers: "ShellControllerDependencies",
    presenters: "ShellPresenterDependencies",
) -> ShellRuntimeDependencies:
    viewer_host_service_ref: list[ViewerHostService | None] = [None]
    viewer_control_bridge_ref: list[ViewerControlBridge | None] = [None]

    def model_provider():  # noqa: ANN202
        return host.model

    def registry_provider():  # noqa: ANN202
        return host.registry

    def active_workspace_id_provider() -> str:
        return str(host.workspace_manager.active_workspace_id() or "")

    def workspace_provider(workspace_id: str):  # noqa: ANN202
        return model_provider().project.workspaces.get(str(workspace_id or ""))

    def active_workspace_provider():  # noqa: ANN202
        return workspace_provider(active_workspace_id_provider())

    def execution_client_provider():  # noqa: ANN202
        return host.execution_client

    def qml_engine_provider():  # noqa: ANN202
        qml_host = getattr(host, "qml_host", None)
        engine = getattr(qml_host, "engine", None) if qml_host is not None else None
        return engine() if callable(engine) else None

    def capture_overlay_camera_state(node_id: str, *, workspace_id: str = ""):  # noqa: ANN202
        viewer_host_service = viewer_host_service_ref[0]
        if viewer_host_service is None:
            return {}
        return viewer_host_service.capture_overlay_camera_state(
            node_id,
            workspace_id=workspace_id,
        )

    def cycle_viewer_camera_bookmark(node_id: str, direction: int) -> bool:
        viewer_control_bridge = viewer_control_bridge_ref[0]
        if viewer_control_bridge is None:
            return False
        return bool(
            viewer_control_bridge.cycle_viewer_camera_bookmark(node_id, direction)
        )

    viewer_session_bridge = ViewerSessionBridge(
        host,
        execution_client_provider=execution_client_provider,
        active_workspace_id_provider=active_workspace_id_provider,
        workspace_provider=workspace_provider,
        scene_bridge=primitives.scene,
        data_types=primitives.registry.data_types,
        capture_overlay_camera_state=capture_overlay_camera_state,
    )

    def project_provider():  # noqa: ANN202
        return model_provider().project

    def project_context_provider() -> tuple[str | None, dict[str, Any] | None]:
        model = model_provider()
        metadata = model.project.metadata
        return (
            str(state.project_session_state.project_path or "").strip() or None,
            dict(metadata) if isinstance(metadata, dict) else None,
        )

    project_session = controllers.project_session_controller
    primitives.scene.set_current_output_provider(
        lambda workspace_id, node_id, port_key: current_output_value(state.run_state, workspace_id, node_id, port_key)
    )
    host.node_execution_state_changed.connect(primitives.scene.refresh_current_output_properties)

    def update_notification_counters() -> None:
        host.update_notification_counters(
            primitives.console_panel.warning_count,
            primitives.console_panel.error_count,
        )

    media_panel_action_service = MediaPanelActionService(
        host,
        scene_mutation=primitives.scene,
        workspace_edit_controller=library_workspace.workspace_edit_controller,
        workspace_drop_connect_controller=(
            library_workspace.workspace_drop_connect_controller
        ),
        model_provider=model_provider,
        active_workspace_provider=active_workspace_provider,
        project_provider=project_provider,
        stage_node_artifact_bytes=project_session.stage_node_artifact_bytes,
        run_state_provider=lambda: state.run_state,
        project_path_provider=lambda: state.project_session_state.project_path,
        append_console_log=primitives.console_panel.append_log,
        show_graph_hint=host.show_graph_hint,
        update_notification_counters=update_notification_counters,
    )

    def create_web_surface_artifact_service(
        node_workspace_id: str,
        node_workspace_name: str,
        node_id: str,
        node_title: str,
        node_type: str,
    ) -> WebSurfaceArtifactService:
        return WebSurfaceArtifactService(
            artifact_store=project_session.project_artifact_store,
            persist_artifact_store=project_session.replace_project_artifact_store,
            temporary_root_parent=primitives.session_store.staging_workspace_root,
            node_workspace_id=node_workspace_id,
            node_workspace_name=node_workspace_name,
            node_id=node_id,
            node_title=node_title,
            node_type=node_type,
        )

    content_fullscreen_bridge = ContentFullscreenBridge(
        host,
        model_provider=model_provider,
        registry_provider=registry_provider,
        active_workspace_id_provider=active_workspace_id_provider,
        project_context_provider=project_context_provider,
        scene_bridge=primitives.scene,
        viewer_session_bridge=viewer_session_bridge,
        run_state=state.run_state,
        execution_state_changed_signal=host.node_execution_state_changed,
        script_editor=primitives.script_editor,
        save_file_dialog=presenters.shell_host_presenter.save_file_dialog,
        trim_video_clip_replace=(
            media_panel_action_service.request_trim_video_clip_replace
        ),
        trim_video_clip_copy=media_panel_action_service.request_trim_video_clip_copy,
        create_web_surface_artifact_service=create_web_surface_artifact_service,
    )
    viewer_host_service = ViewerHostService(
        host,
        qml_engine_provider=qml_engine_provider,
        save_file_dialog=presenters.shell_host_presenter.save_file_dialog,
        cycle_camera_bookmark=cycle_viewer_camera_bookmark,
        viewer_session_bridge=viewer_session_bridge,
        content_fullscreen_bridge=content_fullscreen_bridge,
        preview_cache_provider=primitives._viewer_preview_cache_provider,
    )
    viewer_host_service_ref[0] = viewer_host_service
    viewer_control_bridge = ViewerControlBridge(
        host,
        active_workspace_id_provider=active_workspace_id_provider,
        workspace_provider=workspace_provider,
        model_provider=model_provider,
        registry_provider=registry_provider,
        app_preferences_controller=preferences.app_preferences_controller,
        save_file_dialog=presenters.shell_host_presenter.save_file_dialog,
        viewer_host_service=viewer_host_service,
        scene_bridge=primitives.scene,
        viewer_session_bridge=viewer_session_bridge,
    )
    viewer_control_bridge_ref[0] = viewer_control_bridge
    plot_host_service = PlotHostService(
        host,
        active_workspace_id_provider=active_workspace_id_provider,
        scene_bridge=primitives.scene,
        content_fullscreen_bridge=content_fullscreen_bridge,
        preview_cache_provider=primitives._plot_preview_cache_provider,
    )
    plot_auto_preview_service = PlotAutoPreviewService(
        host,
        scene_bridge=primitives.scene,
    )
    # With async preview surfaces wired, large sources must never convert on
    # the UI thread: cold reads return a loading state and the worker pools
    # build the managed cache. Small files (<= the inline threshold) still
    # convert synchronously.
    try:
        from ea_node_editor.addons.tabular_data.loader_cache_service import (
            set_shared_tabular_ui_thread_conversion_allowed,
        )

        set_shared_tabular_ui_thread_conversion_allowed(False)
    except Exception:  # noqa: BLE001 - tabular addon is optional
        pass
    native_folder_explorer_host_service = NativeFolderExplorerHostService(
        host,
        shell_window=host,
        scene_bridge=primitives.scene,
        enabled=False,
    )
    jupyter_server_bridge = JupyterServerBridge(
        host,
        shell_window=host,
        create_blank_notebook_artifact=project_session.create_blank_notebook_artifact,
    )
    return ShellRuntimeDependencies(
        media_panel_action_service=media_panel_action_service,
        content_fullscreen_bridge=content_fullscreen_bridge,
        viewer_session_bridge=viewer_session_bridge,
        viewer_control_bridge=viewer_control_bridge,
        viewer_host_service=viewer_host_service,
        plot_host_service=plot_host_service,
        plot_auto_preview_service=plot_auto_preview_service,
        native_folder_explorer_host_service=native_folder_explorer_host_service,
        jupyter_server_bridge=jupyter_server_bridge,
    )


__all__ = [
    "ShellRuntimeDependencies",
    "create_viewer_service_dependencies",
]
