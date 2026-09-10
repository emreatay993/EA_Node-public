from __future__ import annotations

import unittest

from PyQt6.QtCore import QObject, QRectF, QMetaObject, Qt, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QFontMetricsF
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.workspace_state import ViewState
from ea_node_editor.ui.shell.runtime_history import (
    ACTION_ADD_NODE,
    ACTION_EDIT_PROPERTY,
    ACTION_RENAME_NODE,
    RuntimeGraphHistory,
)
from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge
from tests.graph_track_b.qml_support import (
    _GRAPH_CANVAS_QML_PATH,
    _NODE_CARD_QML_PATH,
    _GraphCanvasPreferenceBridge,
)
from tests.graph_track_b.scene_model_graph_model_suite import GraphModelTrackBTests
from tests.graph_track_b.scene_model_graph_scene_suite import GraphSceneBridgeTrackBTests
from tests.graph_track_b.theme_support import (
    GRAPH_STITCH_DARK_EDGE_TOKENS_V1,
    GRAPH_STITCH_LIGHT_EDGE_TOKENS_V1,
    GraphThemeBridge,
    STITCH_DARK_V1,
    STITCH_LIGHT_V1,
    ThemeBridge,
    _alpha_color_name,
    _color_name,
    resolve_graph_theme,
)

__all__ = [
    "ACTION_ADD_NODE",
    "ACTION_EDIT_PROPERTY",
    "ACTION_RENAME_NODE",
    "GraphModel",
    "GraphModelTrackBTests",
    "GraphSceneBridgeTrackBTests",
    "GraphThemeBridge",
    "QApplication",
    "QFont",
    "QFontMetricsF",
    "QMetaObject",
    "QObject",
    "QQmlComponent",
    "QQmlEngine",
    "QRectF",
    "Qt",
    "QUrl",
    "RuntimeGraphHistory",
    "STITCH_DARK_V1",
    "STITCH_LIGHT_V1",
    "ThemeBridge",
    "ViewState",
    "ViewportBridge",
    "_GRAPH_CANVAS_QML_PATH",
    "_NODE_CARD_QML_PATH",
    "_GraphCanvasPreferenceBridge",
    "_alpha_color_name",
    "_color_name",
    "pyqtProperty",
    "pyqtSignal",
    "pyqtSlot",
    "GRAPH_STITCH_DARK_EDGE_TOKENS_V1",
    "GRAPH_STITCH_LIGHT_EDGE_TOKENS_V1",
    "resolve_graph_theme",
]


if __name__ == "__main__":
    unittest.main()
