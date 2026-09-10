from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from ea_node_editor.ui.theme import DEFAULT_THEME_ID, ShellThemeService


class ThemeBridge(QObject):
    changed = pyqtSignal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        theme_id: object = DEFAULT_THEME_ID,
        theme_service: ShellThemeService | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme_service = theme_service or ShellThemeService(theme_id=theme_id)

    def apply_theme(self, theme_id: Any) -> str:
        if self._theme_service.apply_theme(theme_id):
            self.changed.emit()
        return self._theme_service.theme_id

    @pyqtProperty(str, notify=changed)
    def theme_id(self) -> str:
        return self._theme_service.theme_id

    @pyqtProperty(str, notify=changed)
    def theme_label(self) -> str:
        return self._theme_service.label

    @pyqtProperty("QVariantMap", notify=changed)
    def palette(self) -> dict[str, str]:
        return self._theme_service.palette()

    @pyqtSlot(str, result=str)
    def token(self, name: str) -> str:
        return self._theme_service.token(name)
