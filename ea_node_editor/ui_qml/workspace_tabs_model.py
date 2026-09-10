from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot


class WorkspaceTabsModel(QObject):
    tabs_changed = pyqtSignal()
    current_index_changed = pyqtSignal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tabs: list[dict[str, Any]] = []
        self._current_index = -1

    @pyqtProperty("QVariantList", notify=tabs_changed)
    def tabs(self) -> list[dict[str, Any]]:
        return list(self._tabs)

    @pyqtProperty(int, notify=current_index_changed)
    def current_index(self) -> int:
        return self._current_index

    def set_tabs(self, tabs: list[dict[str, Any]], current_workspace_id: str) -> None:
        previous_index = self._current_index
        self._tabs = list(tabs)
        next_index = -1
        for index, tab in enumerate(self._tabs):
            if tab.get("workspace_id") == current_workspace_id:
                next_index = index
                break
        self._current_index = next_index
        self.tabs_changed.emit()
        if self._current_index != previous_index:
            self.current_index_changed.emit(self._current_index)

    def count(self) -> int:
        return len(self._tabs)

    def currentIndex(self) -> int:
        return self._current_index

    def setCurrentIndex(self, index: int) -> None:
        if index < 0 or index >= len(self._tabs):
            return
        if self._current_index == index:
            return
        self._current_index = index
        self.current_index_changed.emit(index)

    def tabData(self, index: int) -> str:
        if index < 0 or index >= len(self._tabs):
            return ""
        return str(self._tabs[index].get("workspace_id", ""))

    @pyqtSlot(int)
    def activate_index(self, index: int) -> None:
        self.setCurrentIndex(index)

    @pyqtSlot(str)
    def activate_workspace(self, workspace_id: str) -> None:
        target = str(workspace_id)
        for index, tab in enumerate(self._tabs):
            if tab.get("workspace_id") == target:
                self.setCurrentIndex(index)
                return
