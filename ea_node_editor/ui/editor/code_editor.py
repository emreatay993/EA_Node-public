from __future__ import annotations

import re

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QTextCharFormat, QTextFormat, QSyntaxHighlighter
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget


class PythonSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document) -> None:  # noqa: ANN001
        super().__init__(document)
        self._rules: list[tuple[re.Pattern[str], QTextCharFormat]] = []
        self._build_rules()

    def _build_rules(self) -> None:
        keyword_fmt = QTextCharFormat()
        keyword_fmt.setForeground(QColor("#68a5ff"))
        keyword_fmt.setFontWeight(QFont.Weight.Bold)
        keywords = (
            "and",
            "as",
            "assert",
            "break",
            "class",
            "continue",
            "def",
            "elif",
            "else",
            "except",
            "False",
            "finally",
            "for",
            "from",
            "if",
            "import",
            "in",
            "is",
            "lambda",
            "None",
            "not",
            "or",
            "pass",
            "raise",
            "return",
            "True",
            "try",
            "while",
            "with",
            "yield",
        )
        for keyword in keywords:
            self._rules.append((re.compile(rf"\b{keyword}\b"), keyword_fmt))

        string_fmt = QTextCharFormat()
        string_fmt.setForeground(QColor("#d39d7e"))
        self._rules.append((re.compile(r"'[^']*'"), string_fmt))
        self._rules.append((re.compile(r'"[^"]*"'), string_fmt))

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#7da56b"))
        self._rules.append((re.compile(r"#[^\n]*"), comment_fmt))

        fn_fmt = QTextCharFormat()
        fn_fmt.setForeground(QColor("#d8d49a"))
        self._rules.append((re.compile(r"\b[A-Za-z_]\w*(?=\()"), fn_fmt))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class PythonCodeEditor(QPlainTextEdit):
    caret_diagnostics_changed = pyqtSignal(int, int, int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setFont(QFont("Consolas", 10))
        self._line_number_area = _LineNumberArea(self)
        self._highlighter = PythonSyntaxHighlighter(self.document())
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.cursorPositionChanged.connect(self._emit_caret_diagnostics)
        self.selectionChanged.connect(self._emit_caret_diagnostics)
        self._update_line_number_area_width(0)
        self._highlight_current_line()
        self._emit_caret_diagnostics()

    def _highlight_current_line(self) -> None:
        extra_selection = QTextEdit.ExtraSelection()
        extra_selection.format.setBackground(QColor("#2a3040"))
        extra_selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        extra_selection.cursor = self.textCursor()
        extra_selection.cursor.clearSelection()
        self.setExtraSelections([extra_selection])

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def line_number_area_paint_event(self, event) -> None:  # noqa: ANN001
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor("#171c28"))
        painter.setPen(QColor("#7d8698"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.drawText(
                    0,
                    top,
                    self._line_number_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )
            block = block.next()
            block_number += 1
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        contents = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(contents.left(), contents.top(), self.line_number_area_width(), contents.height())
        )

    def _update_line_number_area_width(self, _new_block_count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy: int) -> None:  # noqa: ANN001
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def _emit_caret_diagnostics(self) -> None:
        cursor = self.textCursor()
        line = cursor.blockNumber() + 1
        column = cursor.columnNumber() + 1
        position = cursor.position()
        selection = abs(cursor.anchor() - cursor.position())
        self.caret_diagnostics_changed.emit(line, column, position, selection)


class _LineNumberArea(QWidget):
    def __init__(self, editor: PythonCodeEditor) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: ANN001
        self._editor.line_number_area_paint_event(event)
