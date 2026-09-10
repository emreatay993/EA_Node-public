from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ea_node_editor.telemetry.startup_profile import phase
from ea_node_editor.ui.shell.composition.bridges import (
    ShellContextBridgeDependencies,
    create_context_bridge_dependencies,
)
from ea_node_editor.ui.shell.composition.controllers import (
    ShellControllerDependencies,
    create_controller_dependencies,
)
from ea_node_editor.ui.shell.composition.graph_actions import (
    ShellGraphActionDependencies,
    create_graph_action_dependencies,
)
from ea_node_editor.ui.shell.composition.library_workspace import (
    ShellLibraryWorkspaceDependencies,
    create_library_workspace_dependencies,
)
from ea_node_editor.ui.shell.composition.preferences import (
    ShellPreferencesThemeStatusDependencies,
    create_preferences_theme_status_dependencies,
)
from ea_node_editor.ui.shell.composition.presenters import (
    ShellPresenterDependencies,
    create_presenter_dependencies,
)
from ea_node_editor.ui.shell.composition.primitives import (
    ShellPrimitiveDependencies,
    create_primitive_dependencies,
)
from ea_node_editor.ui.shell.composition.qml_context import (
    ShellQmlContextDependencies,
    create_qml_context_dependencies,
)
from ea_node_editor.ui.shell.composition.registry_replacement import (
    ShellRegistryReplacementDependencies,
    create_registry_replacement_dependencies,
)
from ea_node_editor.ui.shell.composition.runtime_services import (
    ShellRuntimeDependencies,
    create_viewer_service_dependencies,
)
from ea_node_editor.ui.shell.composition.services import (
    ShellServices,
    ShellWindowComposition,
)
from ea_node_editor.ui.shell.composition.state import (
    ShellStateDependencies,
    create_state_dependencies,
)

if TYPE_CHECKING:
    from ea_node_editor.nodes.registry import NodeRegistry
    from ea_node_editor.ui.shell.window import ShellWindow


class ShellWindowDependencyFactory:
    def __init__(
        self,
        host: "ShellWindow",
        registry: "NodeRegistry | None" = None,
        *,
        preferences_document: Any = None,
    ) -> None:
        self._host = host
        self._registry = registry
        self._preferences_document = preferences_document

    def build_composition(self) -> ShellWindowComposition:
        with phase("factory.state"):
            state = self.create_state_dependencies()
        with phase("factory.primitives"):
            primitives = self.create_primitive_dependencies(state)
        with phase("factory.preferences_theme_status"):
            preferences_theme_status = (
                self.create_preferences_theme_status_dependencies(state, primitives)
            )
        with phase("factory.library_workspace"):
            library_workspace = self.create_library_workspace_dependencies()
        with phase("factory.controllers"):
            controllers = self.create_controller_dependencies(state, primitives)
        with phase("factory.presenters"):
            presenters = self.create_presenter_dependencies(state)
        with phase("factory.viewer_services"):
            runtime = self.create_viewer_service_dependencies(
                state,
                primitives,
                preferences_theme_status,
                library_workspace,
                controllers,
                presenters,
            )
        with phase("factory.registry_replacement"):
            registry_replacement = self.create_registry_replacement_dependencies()
        with phase("factory.context_bridges"):
            context_bridges = self.create_context_bridge_dependencies(
                state,
                primitives,
                preferences_theme_status,
                library_workspace,
                controllers,
                presenters,
                runtime,
            )
        with phase("factory.graph_actions"):
            graph_actions = self.create_graph_action_dependencies(
                primitives,
                library_workspace,
                controllers,
                presenters,
                context_bridges,
            )
        with phase("factory.qml_context"):
            qml_context = self.create_qml_context_dependencies(
                primitives,
                preferences_theme_status,
                runtime,
                context_bridges,
                graph_actions,
            )
        with phase("factory.services"):
            services = self.create_services_bundle(
                state=state,
                primitives=primitives,
                preferences_theme_status=preferences_theme_status,
                library_workspace=library_workspace,
                controllers=controllers,
                presenters=presenters,
                runtime=runtime,
                registry_replacement=registry_replacement,
                context_bridges=context_bridges,
                graph_actions=graph_actions,
                qml_context=qml_context,
            )
        return ShellWindowComposition(
            services=services,
        )

    def create_services_bundle(
        self,
        *,
        state: ShellStateDependencies,
        primitives: ShellPrimitiveDependencies,
        preferences_theme_status: ShellPreferencesThemeStatusDependencies,
        library_workspace: ShellLibraryWorkspaceDependencies,
        controllers: ShellControllerDependencies,
        presenters: ShellPresenterDependencies,
        runtime: ShellRuntimeDependencies,
        registry_replacement: ShellRegistryReplacementDependencies,
        context_bridges: ShellContextBridgeDependencies,
        graph_actions: ShellGraphActionDependencies,
        qml_context: ShellQmlContextDependencies,
    ) -> ShellServices:
        return ShellServices(
            state=state,
            primitives=primitives,
            preferences_theme_status=preferences_theme_status,
            library_workspace=library_workspace,
            controllers=controllers,
            presenters=presenters,
            runtime=runtime,
            registry_replacement=registry_replacement,
            context_bridges=context_bridges,
            graph_actions=graph_actions,
            qml_context=qml_context,
        )

    def create_state_dependencies(self) -> ShellStateDependencies:
        return create_state_dependencies()

    def create_primitive_dependencies(
        self, state: ShellStateDependencies
    ) -> ShellPrimitiveDependencies:
        return create_primitive_dependencies(
            self._host,
            state,
            registry=self._registry,
            preferences_document=self._preferences_document,
        )

    def create_preferences_theme_status_dependencies(
        self,
        state: ShellStateDependencies,
        primitives: ShellPrimitiveDependencies,
    ) -> ShellPreferencesThemeStatusDependencies:
        return create_preferences_theme_status_dependencies(
            self._host,
            state,
            primitives,
            preferences_document=self._preferences_document,
        )

    def create_controller_dependencies(
        self,
        state: ShellStateDependencies,
        primitives: ShellPrimitiveDependencies,
    ) -> ShellControllerDependencies:
        return create_controller_dependencies(
            self._host,
            state,
            registry=primitives.registry,
        )

    def create_library_workspace_dependencies(
        self,
    ) -> ShellLibraryWorkspaceDependencies:
        return create_library_workspace_dependencies(self._host)

    def create_presenter_dependencies(
        self, state: ShellStateDependencies
    ) -> ShellPresenterDependencies:
        return create_presenter_dependencies(self._host, state)

    def create_registry_replacement_dependencies(
        self,
    ) -> ShellRegistryReplacementDependencies:
        return create_registry_replacement_dependencies(self._host)

    def create_viewer_service_dependencies(
        self,
        state: ShellStateDependencies,
        primitives: ShellPrimitiveDependencies,
        preferences: ShellPreferencesThemeStatusDependencies,
        library_workspace: ShellLibraryWorkspaceDependencies,
        controllers: ShellControllerDependencies,
        presenters: ShellPresenterDependencies,
    ) -> ShellRuntimeDependencies:
        return create_viewer_service_dependencies(
            self._host,
            state,
            primitives,
            preferences,
            library_workspace,
            controllers,
            presenters,
        )

    def create_context_bridge_dependencies(
        self,
        state: ShellStateDependencies,
        primitives: ShellPrimitiveDependencies,
        preferences_theme_status: ShellPreferencesThemeStatusDependencies,
        library_workspace: ShellLibraryWorkspaceDependencies,
        controllers: ShellControllerDependencies,
        presenters: ShellPresenterDependencies,
        runtime: ShellRuntimeDependencies,
    ) -> ShellContextBridgeDependencies:
        return create_context_bridge_dependencies(
            self._host,
            state,
            primitives,
            preferences_theme_status,
            library_workspace,
            controllers,
            presenters,
            runtime,
        )

    def create_graph_action_dependencies(
        self,
        primitives: ShellPrimitiveDependencies,
        library_workspace: ShellLibraryWorkspaceDependencies,
        controllers: ShellControllerDependencies,
        presenters: ShellPresenterDependencies,
        context_bridges: ShellContextBridgeDependencies,
    ) -> ShellGraphActionDependencies:
        return create_graph_action_dependencies(
            self._host,
            primitives,
            library_workspace,
            controllers,
            presenters,
            context_bridges,
        )

    def create_qml_context_dependencies(
        self,
        primitives: ShellPrimitiveDependencies,
        preferences_theme_status: ShellPreferencesThemeStatusDependencies,
        runtime: ShellRuntimeDependencies,
        context_bridges: ShellContextBridgeDependencies,
        graph_actions: ShellGraphActionDependencies,
    ) -> ShellQmlContextDependencies:
        return create_qml_context_dependencies(
            self._host,
            primitives,
            preferences_theme_status,
            runtime,
            context_bridges,
            graph_actions,
        )


def build_shell_window_composition(
    host: "ShellWindow",
    registry: "NodeRegistry | None" = None,
    *,
    preferences_document: Any = None,
) -> ShellWindowComposition:
    return ShellWindowDependencyFactory(
        host,
        registry=registry,
        preferences_document=preferences_document,
    ).build_composition()


__all__ = [
    "ShellWindowDependencyFactory",
    "build_shell_window_composition",
]
