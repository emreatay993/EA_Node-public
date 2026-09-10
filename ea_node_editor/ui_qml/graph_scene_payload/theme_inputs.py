from __future__ import annotations

"""Graph theme, typography, and pixel-size payload inputs."""


from typing import TYPE_CHECKING


from ea_node_editor.ui.graph_theme import (
    DEFAULT_GRAPH_THEME_ID,
    GraphThemeDefinition,
    resolve_graph_theme,
)

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge



class _GraphSceneThemeResolver:
    @staticmethod
    def active_graph_theme(graph_theme_bridge: GraphThemeBridge | None) -> GraphThemeDefinition:
        if graph_theme_bridge is None:
            return resolve_graph_theme(DEFAULT_GRAPH_THEME_ID)
        return resolve_graph_theme(graph_theme_bridge.theme)

