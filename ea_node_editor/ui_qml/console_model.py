from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot


class ConsoleModel(QObject):
    output_changed = pyqtSignal()
    errors_changed = pyqtSignal()
    warnings_changed = pyqtSignal()
    counts_changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._output_lines: list[str] = []
        self._error_lines: list[str] = []
        self._warning_lines: list[str] = []

    @property
    def warning_count(self) -> int:
        return len(self._warning_lines)

    @property
    def error_count(self) -> int:
        return len(self._error_lines)

    @pyqtProperty(str, notify=output_changed)
    def output_text(self) -> str:
        return "\n".join(self._output_lines)

    @pyqtProperty(str, notify=errors_changed)
    def errors_text(self) -> str:
        return "\n".join(self._error_lines)

    @pyqtProperty(str, notify=warnings_changed)
    def warnings_text(self) -> str:
        return "\n".join(self._warning_lines)

    @pyqtProperty(int, notify=counts_changed)
    def warning_count_value(self) -> int:
        return self.warning_count

    @pyqtProperty(int, notify=counts_changed)
    def error_count_value(self) -> int:
        return self.error_count

    @pyqtSlot()
    def clear_all(self) -> None:
        self._output_lines.clear()
        self._error_lines.clear()
        self._warning_lines.clear()
        self.output_changed.emit()
        self.errors_changed.emit()
        self.warnings_changed.emit()
        self.counts_changed.emit()

    def append_log(self, level: str, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        normalized_level = str(level).lower()
        line = f"[{stamp}] [{normalized_level.upper()}] {message}"
        self._output_lines.append(line)
        self.output_changed.emit()

        if normalized_level == "warning":
            self._warning_lines.append(line)
            self.warnings_changed.emit()
            self.counts_changed.emit()
        elif normalized_level == "error":
            self._error_lines.append(line)
            self.errors_changed.emit()
            self.counts_changed.emit()
