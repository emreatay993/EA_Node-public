from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ea_node_editor.ui.graph_theme.registry import (
    DEFAULT_GRAPH_THEME_ID,
    GraphThemeDefinition,
    default_graph_theme_id_for_shell_theme,
    resolve_graph_theme,
    resolve_graph_theme_id,
)

_RUNTIME_GRAPH_THEME_DEFAULTS = {
    "follow_shell_theme": True,
    "selected_theme_id": DEFAULT_GRAPH_THEME_ID,
    "custom_themes": [],
}


def resolve_active_graph_theme_id(*, shell_theme_id: object, graph_theme_settings: Any) -> str:
    custom_themes = _resolve_custom_themes(graph_theme_settings)
    if _resolve_follow_shell_theme(graph_theme_settings):
        return default_graph_theme_id_for_shell_theme(shell_theme_id)
    return resolve_graph_theme_id(
        _resolve_selected_theme_id(graph_theme_settings),
        custom_themes=custom_themes,
    )


def resolve_active_graph_theme(*, shell_theme_id: object, graph_theme_settings: Any) -> GraphThemeDefinition:
    custom_themes = _resolve_custom_themes(graph_theme_settings)
    return resolve_graph_theme(
        resolve_active_graph_theme_id(
            shell_theme_id=shell_theme_id,
            graph_theme_settings=graph_theme_settings,
        ),
        custom_themes=custom_themes,
    )


def _resolve_follow_shell_theme(graph_theme_settings: Any) -> bool:
    value = _runtime_setting(graph_theme_settings, "follow_shell_theme")
    if isinstance(value, bool):
        return value
    return bool(_RUNTIME_GRAPH_THEME_DEFAULTS["follow_shell_theme"])


def _resolve_selected_theme_id(graph_theme_settings: Any) -> str:
    value = _runtime_setting(graph_theme_settings, "selected_theme_id")
    return str(value).strip()


def _resolve_custom_themes(graph_theme_settings: Any) -> Any:
    return _runtime_setting(graph_theme_settings, "custom_themes")


def _runtime_setting(graph_theme_settings: Any, key: str) -> Any:
    if not isinstance(graph_theme_settings, Mapping):
        return _RUNTIME_GRAPH_THEME_DEFAULTS[key]
    return graph_theme_settings.get(key, _RUNTIME_GRAPH_THEME_DEFAULTS[key])


__all__ = [
    "resolve_active_graph_theme",
    "resolve_active_graph_theme_id",
]
