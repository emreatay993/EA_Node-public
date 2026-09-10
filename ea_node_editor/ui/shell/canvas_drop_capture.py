# Purpose: Snapshot native drop MIME before QML routes the target without consuming events.
# Map: feature_routes/clipboard_undo_redo_mutation_history.md
# Tests: tests/test_canvas_import_controller.py
from PyQt6.QtCore import QEvent, QObject


class CanvasDropCapture(QObject):
    def __init__(self, surface: QObject, controller) -> None:
        super().__init__(surface)
        self._controller = controller
        surface.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Drop:
            self._controller.capture_native_drop(event.mimeData())
        return False
