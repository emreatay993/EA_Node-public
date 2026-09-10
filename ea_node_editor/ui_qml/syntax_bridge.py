from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtQuick import QQuickTextDocument

from ea_node_editor.ui.editor.code_editor import PythonSyntaxHighlighter


class QmlScriptSyntaxBridge(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._highlighters: dict[int, tuple[object, PythonSyntaxHighlighter]] = {}

    @pyqtSlot(QQuickTextDocument)
    def attach_document(self, text_document: QQuickTextDocument) -> None:
        if text_document is None:
            return
        document = text_document.textDocument()
        if document is None:
            return
        key = id(document)
        if key in self._highlighters and self._highlighters[key][0] is document:
            return
        highlighter = PythonSyntaxHighlighter(document)
        self._highlighters[key] = (document, highlighter)
        highlighter.rehighlight()
