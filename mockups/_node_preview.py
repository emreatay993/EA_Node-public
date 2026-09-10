"""A faithful COREX-style node card, custom-painted from real theme tokens.

Used by the live-preview designs so you can see exactly what the node being
created will look like on the canvas as you edit the wizard fields.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

from mockups._theme import PORT_EXEC, tokens


class NodePreviewCard(QWidget):
    """Repaints itself to mirror the COREX canvas node chrome."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._t = tokens()
        self._title = "Untitled Node"
        self._subtitle = "Custom"
        self._glyph = "{ }"
        self._inputs: list = []
        self._outputs: list = []
        self.setMinimumSize(300, 230)

    # -- live update API ---------------------------------------------------- #
    def set_node(self, *, title, subtitle, glyph, inputs, outputs) -> None:
        self._title = title or "Untitled Node"
        self._subtitle = subtitle or "Custom"
        self._glyph = glyph or "{ }"
        self._inputs = list(inputs)
        self._outputs = list(outputs)
        self.update()

    # -- painting ----------------------------------------------------------- #
    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt signature)
        t = self._t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(t.canvas_bg))
        self._draw_grid(p)

        rows = max(len(self._inputs), len(self._outputs))
        header_h = 46
        row_h = 26
        body_h = max(row_h, rows * row_h + 12)
        node_w = min(360, max(220, self.width() - 64))
        node_h = header_h + body_h
        x = (self.width() - node_w) / 2
        y = (self.height() - node_h) / 2
        node = QRectF(x, y, node_w, node_h)

        # body
        body = QPainterPath()
        body.addRoundedRect(node, 10, 10)
        p.fillPath(body, QColor(t.inspector_card_bg))
        p.setPen(QPen(QColor(t.accent), 1.6))
        p.drawPath(body)

        # header band (rounded top only)
        hdr = QPainterPath()
        hdr.addRoundedRect(QRectF(x, y, node_w, header_h), 10, 10)
        hdr.addRect(QRectF(x, y + header_h - 12, node_w, 12))
        p.fillPath(hdr.simplified(), QColor(t.panel_alt_bg))
        p.setPen(QPen(QColor(t.border), 1))
        p.drawLine(QPointF(x, y + header_h), QPointF(x + node_w, y + header_h))

        # icon chip
        chip = QRectF(x + 12, y + 9, 28, 28)
        chip_path = QPainterPath()
        chip_path.addRoundedRect(chip, 6, 6)
        p.fillPath(chip_path, QColor(t.accent_strong))
        p.setPen(QColor("#ffffff"))
        gf = QFont("Segoe UI", 10, QFont.Weight.Bold)
        p.setFont(gf)
        p.drawText(chip, Qt.AlignmentFlag.AlignCenter, self._glyph[:3])

        # title + subtitle
        p.setPen(QColor(t.panel_title_fg))
        p.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        p.drawText(QRectF(x + 48, y + 8, node_w - 56, 20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._elide(self._title, 26))
        p.setPen(QColor(t.muted_fg))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(x + 48, y + 26, node_w - 56, 16),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._elide(self._subtitle, 34))

        # port rows
        p.setFont(QFont("Segoe UI", 9))
        top = y + header_h + 10
        for i, port in enumerate(self._inputs):
            cy = top + i * row_h
            self._port_marker(p, QPointF(x, cy + 6), port, is_input=True)
            p.setPen(QColor(t.app_fg))
            p.drawText(QRectF(x + 14, cy - 4, node_w / 2, 20),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       self._port_label(port))
        for i, port in enumerate(self._outputs):
            cy = top + i * row_h
            self._port_marker(p, QPointF(x + node_w, cy + 6), port, is_input=False)
            p.setPen(QColor(t.app_fg))
            p.drawText(QRectF(x + node_w / 2 - 14, cy - 4, node_w / 2, 20),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       self._port_label(port))
        p.end()

    # -- helpers ------------------------------------------------------------ #
    def _draw_grid(self, p: QPainter) -> None:
        t = self._t
        p.setPen(QPen(QColor(t.canvas_minor_grid), 1))
        step = 22
        for gx in range(0, self.width(), step):
            p.drawLine(gx, 0, gx, self.height())
        for gy in range(0, self.height(), step):
            p.drawLine(0, gy, self.width(), gy)
        p.setPen(QPen(QColor(t.canvas_major_grid), 1))
        for gx in range(0, self.width(), step * 5):
            p.drawLine(gx, 0, gx, self.height())
        for gy in range(0, self.height(), step * 5):
            p.drawLine(0, gy, self.width(), gy)

    def _port_marker(self, p: QPainter, c: QPointF, port, *, is_input: bool) -> None:
        t = self._t
        is_exec = getattr(port, "kind", "data") == PORT_EXEC
        color = QColor(t.accent if is_exec else t.accent_strong)
        required = getattr(port, "required", False)
        p.setPen(QPen(QColor(t.border), 1))
        p.setBrush(QBrush(color if required else QColor(t.canvas_bg)))
        if is_exec:
            tri = QPolygonF([
                QPointF(c.x() - 5, c.y() - 5),
                QPointF(c.x() + 5, c.y()),
                QPointF(c.x() - 5, c.y() + 5),
            ])
            p.setPen(QPen(color, 1.4))
            p.setBrush(QBrush(color))
            p.drawPolygon(tri)
        else:
            p.setPen(QPen(color, 1.4))
            p.setBrush(QBrush(color if required else QColor(t.canvas_bg)))
            p.drawEllipse(c, 5, 5)

    @staticmethod
    def _port_label(port) -> str:
        dt = getattr(port, "data_type", "any")
        key = getattr(port, "key", str(port))
        return f"{key}" if dt in ("any", "exec") else f"{key} : {dt}"

    @staticmethod
    def _elide(text: str, n: int) -> str:
        return text if len(text) <= n else text[: n - 1] + "…"
