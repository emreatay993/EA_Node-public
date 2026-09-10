from __future__ import annotations

from typing import Any

from ea_node_editor.ui.graph_theme.registry import (
    DEFAULT_GRAPH_THEME_ID,
    GraphThemeDefinition,
    resolve_graph_theme,
)
from ea_node_editor.ui.graph_theme.runtime import resolve_active_graph_theme


class GraphThemeService:
    def __init__(self, *, theme_id: object = DEFAULT_GRAPH_THEME_ID) -> None:
        self._theme = resolve_graph_theme(theme_id)

    @property
    def theme(self) -> GraphThemeDefinition:
        return self._theme

    @property
    def theme_id(self) -> str:
        return self._theme.theme_id

    @property
    def label(self) -> str:
        return self._theme.label

    def apply_theme(self, theme_id: object, *, custom_themes: Any = None) -> bool:
        return self._apply_resolved_theme(resolve_graph_theme(theme_id, custom_themes=custom_themes))

    def apply_settings(self, *, shell_theme_id: object, graph_theme_settings: Any) -> bool:
        return self._apply_resolved_theme(
            resolve_active_graph_theme(
                shell_theme_id=shell_theme_id,
                graph_theme_settings=graph_theme_settings,
            )
        )

    def _apply_resolved_theme(self, resolved_theme: GraphThemeDefinition) -> bool:
        if resolved_theme == self._theme:
            return False
        self._theme = resolved_theme
        return True


__all__ = ["GraphThemeService"]
