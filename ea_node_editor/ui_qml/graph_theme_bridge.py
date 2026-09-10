from __future__ import annotations

import copy
from typing import Any

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from ea_node_editor.ui.graph_theme import DEFAULT_GRAPH_THEME_ID, GraphThemeService


class GraphThemeBridge(QObject):
    changed = pyqtSignal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        theme_id: object = DEFAULT_GRAPH_THEME_ID,
        graph_theme_service: GraphThemeService | None = None,
    ) -> None:
        super().__init__(parent)
        self._graph_theme_service = graph_theme_service or GraphThemeService(theme_id=theme_id)
        self._theme_cache: dict[str, object] | None = None
        self._node_palette_cache: dict[str, object] | None = None
        self._edge_palette_cache: dict[str, str] | None = None
        self._port_kind_palette_cache: dict[str, str] | None = None
        self._port_state_palette_cache: dict[str, str] | None = None

    def _clear_projection_cache(self) -> None:
        self._theme_cache = None
        self._node_palette_cache = None
        self._edge_palette_cache = None
        self._port_kind_palette_cache = None
        self._port_state_palette_cache = None

    def apply_theme(self, theme_id: Any) -> str:
        if self._graph_theme_service.apply_theme(theme_id):
            self._clear_projection_cache()
            self.changed.emit()
        return self._graph_theme_service.theme_id

    def apply_settings(self, *, shell_theme_id: Any, graph_theme_settings: Any) -> str:
        if self._graph_theme_service.apply_settings(
            shell_theme_id=shell_theme_id,
            graph_theme_settings=graph_theme_settings,
        ):
            self._clear_projection_cache()
            self.changed.emit()
        return self._graph_theme_service.theme_id

    @pyqtProperty(str, notify=changed)
    def theme_id(self) -> str:
        return self._graph_theme_service.theme_id

    @pyqtProperty(str, notify=changed)
    def theme_label(self) -> str:
        return self._graph_theme_service.label

    @pyqtProperty("QVariantMap", notify=changed)
    def theme(self) -> dict[str, object]:
        if self._theme_cache is None:
            self._theme_cache = self._graph_theme_service.theme.as_dict()
        return copy.deepcopy(self._theme_cache)

    @pyqtProperty("QVariantMap", notify=changed)
    def node_palette(self) -> dict[str, object]:
        if self._node_palette_cache is None:
            self._node_palette_cache = self._graph_theme_service.theme.node_tokens.as_dict()
        return dict(self._node_palette_cache)

    @pyqtProperty("QVariantMap", notify=changed)
    def edge_palette(self) -> dict[str, str]:
        if self._edge_palette_cache is None:
            self._edge_palette_cache = self._graph_theme_service.theme.edge_tokens.as_dict()
        return dict(self._edge_palette_cache)

    @pyqtProperty("QVariantMap", notify=changed)
    def port_kind_palette(self) -> dict[str, str]:
        if self._port_kind_palette_cache is None:
            self._port_kind_palette_cache = self._graph_theme_service.theme.port_kind_tokens.as_dict()
        return dict(self._port_kind_palette_cache)

    @pyqtProperty("QVariantMap", notify=changed)
    def port_state_palette(self) -> dict[str, str]:
        if self._port_state_palette_cache is None:
            self._port_state_palette_cache = self._graph_theme_service.theme.port_state_tokens.as_dict()
        return dict(self._port_state_palette_cache)

    @pyqtSlot(str, result=str)
    def resolve_data_type_color(self, _color_token: str) -> str:
        """Resolve a projected family token through the active graph theme."""
        return self._graph_theme_service.theme.port_kind_tokens.data
