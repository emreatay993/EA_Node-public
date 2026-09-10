"""Shell composition package: one domain per module, aggregated here.

The public surface re-exported below is the composition contract used by
``window.py``, ``app.py``, the splash, and tests. Domain modules own their
dependency dataclass plus its ``create_*`` factory function; ``factory.py``
sequences them and ``bootstrap.py`` attaches the result to the host.
"""

from __future__ import annotations

from ea_node_editor.ui.shell.composition.bootstrap import (
    ShellTimerDependencies,
    ShellWindowBootstrapCoordinator,
    bootstrap_shell_window,
    create_shell_window,
)
from ea_node_editor.ui.shell.composition.bridges import (
    AddonManagerBridge,
    ShellContextBridgeDependencies,
)
from ea_node_editor.ui.shell.composition.controllers import ShellControllerDependencies
from ea_node_editor.ui.shell.composition.factory import (
    ShellWindowDependencyFactory,
    build_shell_window_composition,
)
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
from ea_node_editor.ui.shell.composition.services import ShellServices, ShellWindowComposition
from ea_node_editor.ui.shell.composition.state import ShellStateDependencies

__all__ = [
    "AddonManagerBridge",
    "ShellContextBridgeDependencies",
    "ShellControllerDependencies",
    "ShellGraphActionDependencies",
    "ShellLibraryWorkspaceDependencies",
    "ShellPreferencesThemeStatusDependencies",
    "ShellPresenterDependencies",
    "ShellPrimitiveDependencies",
    "ShellQmlContextDependencies",
    "ShellRegistryReplacementDependencies",
    "ShellRuntimeDependencies",
    "ShellServices",
    "ShellStateDependencies",
    "ShellTimerDependencies",
    "ShellWindowBootstrapCoordinator",
    "ShellWindowComposition",
    "ShellWindowDependencyFactory",
    "bootstrap_shell_window",
    "build_shell_window_composition",
    "create_shell_window",
]
