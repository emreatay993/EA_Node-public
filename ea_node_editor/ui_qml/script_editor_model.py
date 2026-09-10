from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot


class ScriptEditorModel(QObject):
    visibility_changed = pyqtSignal()
    node_changed = pyqtSignal()
    content_changed = pyqtSignal()
    cursor_changed = pyqtSignal()
    dirty_changed = pyqtSignal()
    focus_changed = pyqtSignal()
    width_changed = pyqtSignal()
    script_apply_requested = pyqtSignal(str, str, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._visible = False
        self._floating = False
        self._panel_width = 0.0
        self._current_node_id = ""
        self._current_node_label = ""
        self._base_script = ""
        self._script_text = ""
        self._dirty = False
        self._cursor_label = "Ln 1, Col 1 | Sel 0 | Pos 0"
        self._has_focus = False

    @pyqtProperty(bool, notify=visibility_changed)
    def visible(self) -> bool:
        return self._visible

    @pyqtProperty(bool, notify=visibility_changed)
    def floating(self) -> bool:
        return self._floating

    @pyqtProperty(float, notify=width_changed)
    def panel_width(self) -> float:
        return self._panel_width

    @pyqtProperty(str, notify=node_changed)
    def current_node_id(self) -> str:
        return self._current_node_id

    @pyqtProperty(str, notify=node_changed)
    def current_node_label(self) -> str:
        return self._current_node_label

    @pyqtProperty(str, notify=content_changed)
    def script_text(self) -> str:
        return self._script_text

    @pyqtProperty(bool, notify=dirty_changed)
    def dirty(self) -> bool:
        return self._dirty

    @pyqtProperty(str, notify=cursor_changed)
    def cursor_label(self) -> str:
        return self._cursor_label

    @pyqtProperty(bool, notify=focus_changed)
    def has_focus(self) -> bool:
        return self._has_focus

    def set_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if self._visible == visible:
            return
        self._visible = visible
        if not visible:
            self._has_focus = False
            self.focus_changed.emit()
        self.visibility_changed.emit()

    def set_floating(self, floating: bool) -> None:
        floating = bool(floating)
        if self._floating == floating:
            return
        self._floating = floating
        self.visibility_changed.emit()

    @pyqtSlot(float)
    def set_width(self, width: Any) -> None:
        try:
            value = float(width)
        except (TypeError, ValueError):
            value = 0.0
        # NaN or non-positive means "unset"; the QML panel falls back to its
        # responsive default width in that case.
        if value != value or value < 0.0:
            value = 0.0
        if self._panel_width == value:
            return
        self._panel_width = value
        self.width_changed.emit()

    def set_node(self, node: Any | None) -> None:
        if node is None or getattr(node, "type_id", "") != "core.python_script":
            self._current_node_id = ""
            self._current_node_label = ""
            self._base_script = ""
            self._set_script_text_internal("")
            self._set_dirty(False)
            self._set_focus(False)
            self.node_changed.emit()
            return

        script = str(getattr(node, "properties", {}).get("script", ""))
        node_id = str(getattr(node, "node_id", ""))
        if (
            self._dirty
            and self._current_node_id == node_id
        ):
            # History/source refresh changes the Revert baseline, never the draft.
            self._base_script = script
            self._set_dirty(self._script_text != script)
            return
        self._current_node_id = node_id
        self._current_node_label = str(getattr(node, "title", "")).strip() or "Python Script"
        self._base_script = script
        self._set_script_text_internal(script)
        self._set_dirty(False)
        self.node_changed.emit()

    @pyqtSlot(str)
    def set_script_text(self, text: str) -> None:
        self._set_script_text_internal(str(text))
        self._set_dirty(bool(self._current_node_id and self._script_text != self._base_script))

    @pyqtSlot(result=bool)
    def apply(self) -> bool:
        if not self._current_node_id:
            return False
        if not self._dirty:
            return True
        node_id = self._current_node_id
        script = self._script_text
        self.script_apply_requested.emit(node_id, "script", script)
        self.focus_editor()
        return (
            self._current_node_id == node_id
            and self._base_script == script
            and not self._dirty
        )

    @pyqtSlot()
    def revert(self) -> None:
        if not self._current_node_id:
            return
        self._set_script_text_internal(self._base_script)
        self._set_dirty(False)
        self.focus_editor()

    def focus_editor(self) -> bool:
        active = self._visible and bool(self._current_node_id)
        self._set_focus(active)
        return self._has_focus

    @pyqtSlot(int, int, int, int)
    def set_cursor_metrics(self, line: int, column: int, position: int, selection: int) -> None:
        label = f"Ln {line}, Col {column} | Sel {selection} | Pos {position}"
        if self._cursor_label == label:
            return
        self._cursor_label = label
        self.cursor_changed.emit()

    def _set_focus(self, focused: bool) -> None:
        focused = bool(focused)
        if self._has_focus == focused:
            return
        self._has_focus = focused
        self.focus_changed.emit()

    def _set_dirty(self, dirty: bool) -> None:
        dirty = bool(dirty)
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit()

    def _set_script_text_internal(self, value: str) -> None:
        if self._script_text == value:
            return
        self._script_text = value
        self.content_changed.emit()
