from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot


class StatusItemModel(QObject):
    changed = pyqtSignal()
    action_requested = pyqtSignal(str, name="actionRequested")

    def __init__(self, icon: str, text: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._icon = icon
        self._text = text

    def set_icon(self, value: str) -> None:
        if self._icon == value:
            return
        self._icon = value
        self.changed.emit()

    def set_text(self, value: str) -> None:
        if self._text == value:
            return
        self._text = value
        self.changed.emit()

    def icon(self) -> str:
        return self._icon

    def text(self) -> str:
        return self._text

    @pyqtSlot(str)
    def requestAction(self, action: str = "auto") -> None:  # noqa: N802
        self.action_requested.emit(str(action or "auto").strip() or "auto")

    @pyqtProperty(str, notify=changed)
    def icon_value(self) -> str:
        return self._icon

    @pyqtProperty(str, notify=changed)
    def text_value(self) -> str:
        return self._text
