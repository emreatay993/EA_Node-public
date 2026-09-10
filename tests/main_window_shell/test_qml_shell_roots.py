from __future__ import annotations

from tests.main_window_shell.bridge_qml_boundaries import (
    GraphCanvasQmlBoundaryTests,
    ShellAddOnManagerQmlBoundaryTests,
    ShellInspectorBridgeQmlBoundaryTests,
    ShellLibraryBridgeQmlBoundaryTests,
    ShellStatusStripQmlBoundaryTests,
    ShellWorkspaceBridgeQmlBoundaryTests,
    TooltipManagerTierCatalogQmlBoundaryTests,
)
from tests.main_window_shell.shell_runtime_contracts import (
    MainWindowShellContentFullscreenStaticContractsTests,
)

__all__ = [
    "GraphCanvasQmlBoundaryTests",
    "MainWindowShellContentFullscreenStaticContractsTests",
    "ShellAddOnManagerQmlBoundaryTests",
    "ShellInspectorBridgeQmlBoundaryTests",
    "ShellLibraryBridgeQmlBoundaryTests",
    "ShellStatusStripQmlBoundaryTests",
    "ShellWorkspaceBridgeQmlBoundaryTests",
    "TooltipManagerTierCatalogQmlBoundaryTests",
]
