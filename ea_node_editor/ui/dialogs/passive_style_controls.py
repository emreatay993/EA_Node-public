from __future__ import annotations

import re
from collections.abc import Callable

from PyQt6.QtCore import QRegularExpression, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QRegularExpressionValidator
from PyQt6.QtWidgets import QColorDialog, QFrame, QHBoxLayout, QLineEdit, QWidget

FINAL_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")

class ColorSwatchFrame(QFrame):
    """A 32x32 clickable color swatch that can open a QColorDialog."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setProperty("dialogSwatch", True)
        self._editable = False

    @property
    def editable(self) -> bool:
        return self._editable

    @editable.setter
    def editable(self, value: bool) -> None:
        self._editable = bool(value)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if self._editable else Qt.CursorShape.ArrowCursor
        )

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if self._editable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            return
        super().mousePressEvent(event)


class ColorHexFieldControl(QWidget):
    valueChanged = pyqtSignal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        allow_empty: bool = False,
        color_dialog_title: str = "Pick Color",
    ) -> None:
        super().__init__(parent)
        self._allow_empty = bool(allow_empty)
        self._color_dialog_title = str(color_dialog_title)
        self._before_color_apply: Callable[[str], bool] | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.swatch = ColorSwatchFrame(self)
        self.swatch.clicked.connect(self._choose_color)
        layout.addWidget(self.swatch, stretch=0, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.line_edit = QLineEdit(self)
        self.line_edit.setValidator(hex_color_validator(self, allow_empty=self._allow_empty))
        self.line_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.line_edit, stretch=1)

        self.refresh_swatch()
        # Keep the swatch clickability aligned with the field editability.
        self.setReadOnly(self.line_edit.isReadOnly())

    def text(self) -> str:
        return self.line_edit.text()

    def setText(self, value: object) -> None:
        self.line_edit.setText(str(value or "").strip())

    def setReadOnly(self, value: bool) -> None:
        read_only = bool(value)
        self.line_edit.setReadOnly(read_only)
        self.swatch.editable = not read_only

    def setObjectNames(self, *, value_name: str, swatch_name: str) -> None:
        self.line_edit.setObjectName(value_name)
        self.swatch.setObjectName(swatch_name)

    def setBeforeColorApply(self, callback: Callable[[str], bool] | None) -> None:
        self._before_color_apply = callback

    def is_valid(self) -> bool:
        return is_valid_hex_color(self.text(), allow_empty=self._allow_empty)

    def mark_invalid(self) -> None:
        set_dialog_role(self.line_edit, "error")
        set_dialog_role(self.swatch, "error")

    def mark_valid(self) -> None:
        set_dialog_role(self.line_edit, None)
        self.refresh_swatch()

    def refresh_swatch(self) -> None:
        normalized = self.text().strip()
        if not normalized and self._allow_empty:
            role = "empty"
        elif not is_valid_hex_color(normalized, allow_empty=self._allow_empty):
            role = "error"
        else:
            role = None
        set_dialog_role(self.swatch, role)
        self.swatch.setStyleSheet(swatch_style(normalized, allow_empty=self._allow_empty))

    def _on_text_changed(self, text: str) -> None:
        normalized = str(text or "").strip()
        if text != normalized:
            self.line_edit.blockSignals(True)
            self.line_edit.setText(normalized)
            self.line_edit.blockSignals(False)
        self.refresh_swatch()
        self.valueChanged.emit(normalized)

    def _choose_color(self) -> None:
        current_text = self.text().strip()
        initial_color = QColor(current_text) if is_valid_hex_color(current_text) else QColor("#ffffff")
        color = QColorDialog.getColor(
            initial_color,
            self,
            self._color_dialog_title,
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        selected_hex = color_to_hex(color)
        if self._before_color_apply is not None and not self._before_color_apply(selected_hex):
            return
        self.setText(selected_hex)


def color_to_hex(color: QColor) -> str:
    if color.alpha() < 255:
        return f"#{color.alpha():02X}{color.red():02X}{color.green():02X}{color.blue():02X}"
    return color.name().upper()


def hex_color_validator(parent: QWidget | None = None, *, allow_empty: bool = False) -> QRegularExpressionValidator:
    pattern = r"(?:#[0-9A-Fa-f]{0,8})?" if allow_empty else r"#[0-9A-Fa-f]{0,8}"
    return QRegularExpressionValidator(QRegularExpression(pattern), parent)


def is_valid_hex_color(value: object, *, allow_empty: bool = False) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return allow_empty
    return bool(FINAL_HEX_COLOR.match(normalized))


def set_dialog_role(widget: QWidget, role: str | None) -> None:
    if widget.property("dialogRole") == role:
        return
    widget.setProperty("dialogRole", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def swatch_style(value: object, *, allow_empty: bool = False) -> str:
    normalized = str(value or "").strip()
    if not normalized and allow_empty:
        return "background-color: transparent;"
    if not is_valid_hex_color(normalized, allow_empty=allow_empty):
        return "background-color: transparent;"
    return f"background-color: {normalized};"


__all__ = [
    "ColorHexFieldControl",
    "ColorSwatchFrame",
    "FINAL_HEX_COLOR",
    "color_to_hex",
    "hex_color_validator",
    "is_valid_hex_color",
    "set_dialog_role",
    "swatch_style",
]
