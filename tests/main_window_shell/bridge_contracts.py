from __future__ import annotations

import pytest
from PyQt6.QtCore import QObject

from ea_node_editor.telemetry.frame_rate import FrameRateSampler
from ea_node_editor.ui.shell.runtime_clipboard import (
    build_graph_fragment_payload,
    serialize_graph_fragment_payload,
)
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.shell_inspector_bridge import ShellInspectorBridge
from ea_node_editor.ui_qml.shell_library_bridge import ShellLibraryBridge
from ea_node_editor.ui_qml.shell_workspace_bridge import ShellWorkspaceBridge
from tests.main_window_shell.bridge_contracts_library_and_inspector import (
    ShellInspectorBridgeTests,
    ShellLibraryBridgeTests,
)
from tests.main_window_shell.bridge_contracts_workspace_and_console import (
    SharedUiSupportBoundaryTests,
    ShellWorkspaceBridgeTests,
)
from tests.main_window_shell.bridge_support import (
    _GRAPH_CANVAS_HOST_DIRECT_ENV,
    _PASSIVE_IMAGE_DIRECT_ENV,
    _PASSIVE_PDF_DIRECT_ENV,
    _REPO_ROOT,
    _named_child_items,
)

pytestmark = pytest.mark.xdist_group("p03_bridge_contracts")

__all__ = [
    "FrameRateSampler",
    "GraphCanvasCommandBridge",
    "GraphCanvasStateBridge",
    "QObject",
    "SharedUiSupportBoundaryTests",
    "ShellInspectorBridge",
    "ShellInspectorBridgeTests",
    "ShellLibraryBridge",
    "ShellLibraryBridgeTests",
    "ShellWorkspaceBridge",
    "ShellWorkspaceBridgeTests",
    "_GRAPH_CANVAS_HOST_DIRECT_ENV",
    "_PASSIVE_IMAGE_DIRECT_ENV",
    "_PASSIVE_PDF_DIRECT_ENV",
    "_REPO_ROOT",
    "_named_child_items",
    "build_graph_fragment_payload",
    "serialize_graph_fragment_payload",
]
