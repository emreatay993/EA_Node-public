from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ea_node_editor.ui.shell.composition.bridges import ShellContextBridgeDependencies
from ea_node_editor.ui.shell.composition.controllers import ShellControllerDependencies
from ea_node_editor.ui.shell.composition.graph_actions import ShellGraphActionDependencies
from ea_node_editor.ui.shell.composition.library_workspace import ShellLibraryWorkspaceDependencies
from ea_node_editor.ui.shell.composition.preferences import ShellPreferencesThemeStatusDependencies
from ea_node_editor.ui.shell.composition.presenters import ShellPresenterDependencies
from ea_node_editor.ui.shell.composition.primitives import ShellPrimitiveDependencies
from ea_node_editor.ui.shell.composition.qml_context import ShellQmlContextDependencies
from ea_node_editor.ui.shell.composition.registry_replacement import (
    ShellRegistryReplacementDependencies,
)
from ea_node_editor.ui.shell.composition.runtime_services import ShellRuntimeDependencies
from ea_node_editor.ui.shell.composition.state import ShellStateDependencies

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


@dataclass(frozen=True, slots=True)
class ShellServices:
    state: ShellStateDependencies
    primitives: ShellPrimitiveDependencies
    preferences_theme_status: ShellPreferencesThemeStatusDependencies
    library_workspace: ShellLibraryWorkspaceDependencies
    controllers: ShellControllerDependencies
    presenters: ShellPresenterDependencies
    runtime: ShellRuntimeDependencies
    registry_replacement: ShellRegistryReplacementDependencies
    context_bridges: ShellContextBridgeDependencies
    graph_actions: ShellGraphActionDependencies
    qml_context: ShellQmlContextDependencies

    def attach(self, host: "ShellWindow") -> None:
        host.shell_services = self
        self.state.attach(host)
        self.primitives.attach(host)
        self.preferences_theme_status.attach(host)
        self.library_workspace.attach(host)
        self.controllers.attach(host)
        self.presenters.attach(host)
        self.runtime.attach(host)
        self.registry_replacement.attach(host)
        self.context_bridges.attach(host)
        self.graph_actions.attach(host)


@dataclass(frozen=True, slots=True)
class ShellWindowComposition:
    services: ShellServices

    def attach(self, host: "ShellWindow") -> None:
        self.services.attach(host)


__all__ = [
    "ShellServices",
    "ShellWindowComposition",
]
