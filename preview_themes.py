"""Standalone preview of all registered graph theme palettes."""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ea_node_editor.ui.graph_theme.registry import GRAPH_THEME_REGISTRY


class SwatchWidget(QWidget):
    """Paints a single colour swatch with an optional border."""

    def __init__(self, color: str, size: int = 22, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(size, size)

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#555555"), 1))
        p.setBrush(self._color)
        p.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 3, 3)
        p.end()


class NodePreviewWidget(QWidget):
    """Miniature node card preview showing header + body + ports."""

    def __init__(self, theme: object, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setFixedSize(180, 110)

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        n = self._theme.node_tokens
        e = self._theme.edge_tokens
        ca = self._theme.category_accent_tokens
        pk = self._theme.port_kind_tokens

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Card background
        p.setPen(QPen(QColor(n.card_border), 1.5))
        p.setBrush(QColor(n.card_bg))
        p.drawRoundedRect(2, 2, 176, 106, 6, 6)

        # Header
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(n.header_bg))
        p.drawRoundedRect(3, 3, 174, 28, 5, 5)
        p.setBrush(QColor(n.card_bg))
        p.drawRect(3, 20, 174, 11)

        # Header text
        p.setPen(QColor(n.header_fg))
        font = p.font()
        font.setPointSize(8)
        font.setBold(True)
        p.setFont(font)
        p.drawText(10, 20, "Node Title")

        # Scope badge
        p.setPen(QPen(QColor(n.scope_badge_border), 1))
        p.setBrush(QColor(n.scope_badge_bg))
        p.drawRoundedRect(120, 8, 50, 16, 3, 3)
        font.setPointSize(6)
        font.setBold(False)
        p.setFont(font)
        p.setPen(QColor(n.scope_badge_fg))
        p.drawText(127, 19, "scope")

        # Inline row
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(n.inline_row_bg))
        p.drawRect(3, 32, 174, 22)
        p.setPen(QPen(QColor(n.inline_row_border), 0.5))
        p.drawLine(3, 54, 177, 54)

        # Inline label + input
        font.setPointSize(7)
        p.setFont(font)
        p.setPen(QColor(n.inline_label_fg))
        p.drawText(28, 46, "input")
        p.setPen(QPen(QColor(n.inline_input_border), 1))
        p.setBrush(QColor(n.inline_input_bg))
        p.drawRoundedRect(70, 36, 80, 14, 2, 2)
        p.setPen(QColor(n.inline_input_fg))
        p.drawText(74, 47, "0.0")

        # Port dots (left side)
        port_colors = [pk.data, pk.exec, pk.completed, pk.failed]
        for i, color in enumerate(port_colors):
            y = 36 + i * 18
            if y > 95:
                break
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(8, y, 10, 10)

        # Port label
        p.setPen(QColor(n.port_label_fg))
        p.drawText(28, 68, "output")

        # Category accent bar (left edge)
        accents = [ca.default, ca.core, ca.input_output, ca.physics, ca.logic, ca.hpc]
        bar_h = 104 // len(accents)
        for i, accent in enumerate(accents):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(accent))
            p.drawRect(168, 3 + i * bar_h, 8, bar_h)

        # Edge preview lines at bottom
        edge_colors = [
            (e.preview_stroke, "preview"),
            (e.selected_stroke, "selected"),
            (e.warning_stroke, "warning"),
        ]
        y_base = 80
        for i, (color, _label) in enumerate(edge_colors):
            p.setPen(QPen(QColor(color), 2))
            p.drawLine(28, y_base + i * 10, 155, y_base + i * 10)

        # Interactive port ring
        p.setPen(QPen(QColor(n.port_interactive_border), 1.5))
        p.setBrush(QColor(n.port_interactive_fill))
        p.drawEllipse(8, 60, 10, 10)

        p.end()


def _build_theme_card(theme_id: str, theme: object) -> QWidget:
    card = QWidget()
    card.setFixedWidth(220)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)

    # Title
    title = QLabel(theme.label)
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    font = title.font()
    font.setPointSize(9)
    font.setBold(True)
    title.setFont(font)
    title.setStyleSheet(
        f"color: {theme.node_tokens.header_fg}; "
        f"background: {theme.node_tokens.card_bg}; "
        "border-radius: 4px; padding: 4px;"
    )
    layout.addWidget(title)

    # Node preview
    preview = NodePreviewWidget(theme)
    layout.addWidget(preview, alignment=Qt.AlignmentFlag.AlignCenter)

    # Category accent row
    accent_row = QHBoxLayout()
    accent_row.setSpacing(3)
    for field_name in ("default", "core", "input_output", "physics", "logic", "hpc"):
        color = getattr(theme.category_accent_tokens, field_name)
        accent_row.addWidget(SwatchWidget(color, 18))
    accent_container = QWidget()
    accent_container.setLayout(accent_row)
    layout.addWidget(accent_container, alignment=Qt.AlignmentFlag.AlignCenter)

    # Port kind row
    port_row = QHBoxLayout()
    port_row.setSpacing(3)
    for field_name in ("data", "exec", "completed", "failed"):
        color = getattr(theme.port_kind_tokens, field_name)
        port_row.addWidget(SwatchWidget(color, 18))
    port_container = QWidget()
    port_container.setLayout(port_row)
    layout.addWidget(port_container, alignment=Qt.AlignmentFlag.AlignCenter)

    layout.addStretch()

    bg = theme.node_tokens.card_bg
    border = theme.node_tokens.card_border
    card.setStyleSheet(
        f"SwatchWidget {{ background: transparent; }}"
        f"QWidget#themeCard {{ background: {bg}; border: 1px solid {border}; border-radius: 6px; }}"
    )
    card.setObjectName("themeCard")
    card.setStyleSheet(
        f"QWidget#themeCard {{ background: {bg}; border: 1px solid {border}; border-radius: 8px; }}"
    )
    return card


def main() -> None:
    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("Graph Theme Palette Preview")
    window.setMinimumSize(1400, 750)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)

    container = QWidget()
    grid = QGridLayout(container)
    grid.setSpacing(12)
    grid.setContentsMargins(16, 16, 16, 16)

    # Group by family: dark on top, light on bottom
    families = []
    seen = set()
    for theme_id in GRAPH_THEME_REGISTRY:
        base = theme_id.rsplit("_", 1)[0]
        if base not in seen:
            seen.add(base)
            families.append(base)

    col = 0
    for family_base in families:
        dark_id = f"{family_base}_dark"
        light_id = f"{family_base}_light"
        if dark_id in GRAPH_THEME_REGISTRY:
            grid.addWidget(_build_theme_card(dark_id, GRAPH_THEME_REGISTRY[dark_id]), 0, col)
        if light_id in GRAPH_THEME_REGISTRY:
            grid.addWidget(_build_theme_card(light_id, GRAPH_THEME_REGISTRY[light_id]), 1, col)
        col += 1

    scroll.setWidget(container)
    layout = QVBoxLayout(window)
    layout.addWidget(scroll)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
