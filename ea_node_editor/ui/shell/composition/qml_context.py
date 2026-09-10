from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ea_node_editor.ui_qml.shell_context_bootstrap import (
    ShellContextBundle,
    ShellContextPropertyBindings,
    ShellQmlHostBindings,
)
from ea_node_editor.ui.tooltips import TooltipCopyBridge
from ea_node_editor.web_host.webengine import is_webengine_available

if TYPE_CHECKING:
    from ea_node_editor.help.help_bridge import HelpBridge
    from ea_node_editor.ui.shell.composition.bridges import (
        AddonManagerBridge,
        ShellContextBridgeDependencies,
    )
    from ea_node_editor.ui.shell.composition.graph_actions import ShellGraphActionDependencies
    from ea_node_editor.ui.shell.composition.preferences import (
        ShellPreferencesThemeStatusDependencies,
    )
    from ea_node_editor.ui.shell.composition.primitives import ShellPrimitiveDependencies
    from ea_node_editor.ui.shell.composition.runtime_services import ShellRuntimeDependencies
    from ea_node_editor.ui.shell.context_bridges import ShellContextBridges
    from ea_node_editor.ui.shell.window import ShellWindow
    from ea_node_editor.ui_qml.graph_action_bridge import GraphActionBridge


@dataclass(frozen=True, slots=True)
class ShellQmlContextDependencies:
    qml_context_bundle: ShellContextBundle
    qml_context_property_bindings: ShellContextPropertyBindings
    qml_host_bindings: ShellQmlHostBindings


def _build_shell_context_bundle(
    host: "ShellWindow",
    bridges: "ShellContextBridges",
    addon_manager_bridge: "AddonManagerBridge",
    graph_action_bridge: "GraphActionBridge",
    primitives: "ShellPrimitiveDependencies",
    preferences_theme_status: "ShellPreferencesThemeStatusDependencies",
    runtime: "ShellRuntimeDependencies",
    help_bridge: "HelpBridge",
) -> ShellContextBundle:
    return ShellContextBundle(
        parent=host,
        shell_library_bridge=bridges.shell_library_bridge,
        shell_workspace_bridge=bridges.shell_workspace_bridge,
        shell_inspector_bridge=bridges.shell_inspector_bridge,
        addon_manager_bridge=addon_manager_bridge,
        graph_action_bridge=graph_action_bridge,
        graph_canvas_state_bridge=bridges.graph_canvas_state_bridge,
        graph_canvas_command_bridge=bridges.graph_canvas_command_bridge,
        graph_canvas_view_bridge=primitives.view,
        content_fullscreen_bridge=runtime.content_fullscreen_bridge,
        jupyter_server_bridge=runtime.jupyter_server_bridge,
        viewer_session_bridge=runtime.viewer_session_bridge,
        viewer_control_bridge=runtime.viewer_control_bridge,
        viewer_host_service=runtime.viewer_host_service,
        plot_host_service=runtime.plot_host_service,
        script_editor_bridge=primitives.script_editor,
        script_highlighter_bridge=primitives.script_highlighter,
        theme_bridge=preferences_theme_status.theme_bridge,
        graph_theme_bridge=preferences_theme_status.graph_theme_bridge,
        ui_icons=primitives.ui_icons,
        status_engine=preferences_theme_status.status_engine,
        status_jobs=preferences_theme_status.status_jobs,
        status_metrics=preferences_theme_status.status_metrics,
        status_notifications=preferences_theme_status.status_notifications,
        help_bridge=help_bridge,
        tooltip_copy_bridge=TooltipCopyBridge(host),
    )


def _build_shell_context_property_bindings(
    context_bundle: ShellContextBundle,
) -> ShellContextPropertyBindings:
    return (
        ("shellContext", context_bundle),
        ("shellLibraryBridge", context_bundle.shellLibraryBridge),
        ("shellWorkspaceBridge", context_bundle.shellWorkspaceBridge),
        ("shellInspectorBridge", context_bundle.shellInspectorBridge),
        ("addonManagerBridge", context_bundle.addonManagerBridge),
        ("graphActionBridge", context_bundle.graphActionBridge),
        ("graphCanvasStateBridge", context_bundle.graphCanvasStateBridge),
        ("graphCanvasCommandBridge", context_bundle.graphCanvasCommandBridge),
        ("graphCanvasViewBridge", context_bundle.graphCanvasViewBridge),
        ("contentFullscreenBridge", context_bundle.contentFullscreenBridge),
        ("jupyterServerBridge", context_bundle.jupyterServerBridge),
        ("graphWebBoardForceFallback", not is_webengine_available()),
        ("viewerSessionBridge", context_bundle.viewerSessionBridge),
        ("viewerControlBridge", context_bundle.viewerControlBridge),
        ("viewerHostService", context_bundle.viewerHostService),
        ("plotHostService", context_bundle.plotHostService),
        ("scriptEditorBridge", context_bundle.scriptEditorBridge),
        ("scriptHighlighterBridge", context_bundle.scriptHighlighterBridge),
        ("themeBridge", context_bundle.themeBridge),
        ("graphThemeBridge", context_bundle.graphThemeBridge),
        ("uiIcons", context_bundle.uiIcons),
        ("statusEngine", context_bundle.statusEngine),
        ("statusJobs", context_bundle.statusJobs),
        ("statusMetrics", context_bundle.statusMetrics),
        ("statusNotifications", context_bundle.statusNotifications),
        ("helpBridge", context_bundle.helpBridge),
        ("tooltipCopyBridge", context_bundle.tooltipCopyBridge),
    )


def create_qml_context_dependencies(
    host: "ShellWindow",
    primitives: "ShellPrimitiveDependencies",
    preferences_theme_status: "ShellPreferencesThemeStatusDependencies",
    runtime: "ShellRuntimeDependencies",
    context_bridges: "ShellContextBridgeDependencies",
    graph_actions: "ShellGraphActionDependencies",
) -> ShellQmlContextDependencies:
    qml_context_bundle = _build_shell_context_bundle(
        host,
        context_bridges.shell_context_bridges,
        context_bridges.addon_manager_bridge,
        graph_actions.graph_action_bridge,
        primitives,
        preferences_theme_status,
        runtime,
        context_bridges.help_bridge,
    )
    return ShellQmlContextDependencies(
        qml_context_bundle=qml_context_bundle,
        qml_context_property_bindings=_build_shell_context_property_bindings(qml_context_bundle),
        qml_host_bindings=ShellQmlHostBindings(
            ui_icon_image_provider=primitives._ui_icon_image_provider,
            local_media_preview_provider=primitives._local_media_preview_provider,
            local_pdf_preview_provider=primitives._local_pdf_preview_provider,
            plot_preview_cache_provider=primitives._plot_preview_cache_provider,
            viewer_preview_cache_provider=primitives._viewer_preview_cache_provider,
            record_render_frame=host._record_render_frame,
        ),
    )


__all__ = [
    "ShellQmlContextDependencies",
    "create_qml_context_dependencies",
]
