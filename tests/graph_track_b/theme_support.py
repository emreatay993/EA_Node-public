from __future__ import annotations

from PyQt6.QtGui import QColor

from ea_node_editor.ui.graph_theme import (
    GRAPH_STITCH_DARK_EDGE_TOKENS_V1,
    GRAPH_STITCH_LIGHT_EDGE_TOKENS_V1,
    resolve_graph_theme,
)
from ea_node_editor.ui.theme import STITCH_DARK_V1, STITCH_LIGHT_V1
from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
from ea_node_editor.ui_qml.theme_bridge import ThemeBridge


def _color_name(value: object, *, include_alpha: bool = False) -> str:
    name_format = QColor.NameFormat.HexArgb if include_alpha else QColor.NameFormat.HexRgb
    return QColor(value).name(name_format)


def _alpha_color_name(value: str, alpha: float) -> str:
    color = QColor(value)
    color.setAlphaF(alpha)
    return _color_name(color, include_alpha=True)


__all__ = [
    'GRAPH_STITCH_DARK_EDGE_TOKENS_V1',
    'GRAPH_STITCH_LIGHT_EDGE_TOKENS_V1',
    'GraphThemeBridge',
    'STITCH_DARK_V1',
    'STITCH_LIGHT_V1',
    'ThemeBridge',
    '_alpha_color_name',
    '_color_name',
    'resolve_graph_theme',
]
