# Purpose: Attach the shell-owned registry replacement transaction coordinator.
# Map: subsystems/ui_shell.md
# Tests: tests/test_registry_replacement.py

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ea_node_editor.ui.shell.registry_replacement import (
    RegistryReplacementCoordinator,
)

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


@dataclass(frozen=True, slots=True)
class ShellRegistryReplacementDependencies:
    registry_replacement_coordinator: RegistryReplacementCoordinator

    def attach(self, host: "ShellWindow") -> None:
        host.registry_replacement_coordinator = self.registry_replacement_coordinator


def create_registry_replacement_dependencies(
    host: "ShellWindow",
) -> ShellRegistryReplacementDependencies:
    return ShellRegistryReplacementDependencies(
        registry_replacement_coordinator=RegistryReplacementCoordinator(host)
    )


__all__ = [
    "ShellRegistryReplacementDependencies",
    "create_registry_replacement_dependencies",
]
