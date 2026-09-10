"""Design 4 -- Canvas-inline create.

No modal dialog. Double-click the canvas and an inline create-card expands
right where you clicked; on Create it morphs into a placed node. Esc cancels.
Most integrated, least disruptive to flow.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mockups._theme import (
    GENERIC_TEMPLATES,
    Port,
    apply_corex_theme,
    apply_window_icon,
    generic_flow,
    python_script_flow,
    tokens,
)
from mockups._widgets import CategoryPathEditor, PortListEditor, hint, section_label


@dataclass
class PlacedNode:
    x: float
    y: float
    title: str
    subtitle: str
    glyph: str
    inputs: list
    outputs: list


class InlineCreateCard(QFrame):
    """Compact in-canvas creation card anchored at the click point."""

    def __init__(self, flow_id: str, on_create, on_cancel, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("settingsCard", True)
        self.setFixedWidth(360)
        self._flow_id = flow_id
        self._template_idx = 0
        self._on_create = on_create
        self._on_cancel = on_cancel
        self._advanced = False
        self._build()

    def _flow(self):
        if self._flow_id == "python":
            return python_script_flow()
        return generic_flow(GENERIC_TEMPLATES[self._template_idx])

    def _build(self) -> None:
        for c in list(self.children()):
            if isinstance(c, QWidget):
                c.deleteLater()
        if self.layout():
            QWidget().setLayout(self.layout())
        flow = self._flow()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        top = QHBoxLayout()
        glyph = QLabel(flow.icon_glyph)
        glyph.setStyleSheet("font-weight:700;font-size:14px;")
        top.addWidget(glyph)
        top.addWidget(section_label("Create node"))
        top.addStretch(1)
        for fid, txt in (("python", "Py"), ("generic", "Generic")):
            b = QPushButton(txt)
            b.setCheckable(True)
            b.setChecked(fid == self._flow_id)
            b.setFixedWidth(64)
            b.clicked.connect(lambda _=False, f=fid: self._set_flow(f))
            top.addWidget(b)
        lay.addLayout(top)

        if self._flow_id == "generic":
            combo = QComboBox()
            combo.addItems([t["name"] for t in GENERIC_TEMPLATES])
            combo.setCurrentIndex(self._template_idx)
            combo.currentIndexChanged.connect(self._set_template)
            lay.addWidget(combo)

        self._name = QLineEdit()
        self._name.setPlaceholderText("Node name (required)")
        self._name.setText("" if self._flow_id == "python" else flow.title)
        lay.addWidget(self._name)
        self._cat = CategoryPathEditor(
            tuple(flow.subtitle.split(" › ")) if flow.subtitle else ("Custom",))
        lay.addWidget(self._cat)

        adv_btn = QToolButton()
        adv_btn.setText(("▾  Hide ports & source" if self._advanced
                         else "▸  Ports & source"))
        adv_btn.clicked.connect(self._toggle_adv)
        adv_btn.setStyleSheet("QToolButton{border:none;background:transparent;}")
        lay.addWidget(adv_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        if self._advanced:
            lay.addWidget(hint("Inputs"))
            self._ins = PortListEditor(flow.preview_inputs)
            lay.addWidget(self._ins)
            lay.addWidget(hint("Outputs"))
            self._outs = PortListEditor(flow.preview_outputs)
            lay.addWidget(self._outs)
        else:
            self._ins = None
            self._outs = None
            lay.addWidget(hint(
                "Inputs: " + (", ".join(p.key for p in flow.preview_inputs) or "—")
                + "   ·   Outputs: "
                + (", ".join(p.key for p in flow.preview_outputs) or "—")))

        foot = QHBoxLayout()
        esc = QPushButton("Esc")
        esc.setFixedWidth(56)
        esc.clicked.connect(self._on_cancel)
        create = QPushButton("✓  Create")
        create.clicked.connect(self._emit)
        foot.addWidget(esc)
        foot.addStretch(1)
        foot.addWidget(create)
        lay.addLayout(foot)
        self.adjustSize()

    def _set_flow(self, fid: str) -> None:
        self._flow_id = fid
        self._build()

    def _set_template(self, idx: int) -> None:
        self._template_idx = idx
        self._build()

    def _toggle_adv(self) -> None:
        self._advanced = not self._advanced
        self._build()

    def _emit(self) -> None:
        flow = self._flow()
        ins = self._ins.value() if self._ins else list(flow.preview_inputs)
        outs = self._outs.value() if self._outs else list(flow.preview_outputs)
        self._on_create(
            self._name.text().strip() or flow.title,
            " › ".join(self._cat.value()) or flow.subtitle,
            flow.icon_glyph, ins, outs)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self._on_cancel()
        else:
            super().keyPressEvent(e)


class CanvasInlineCreate(QWidget):
    """A mock COREX graph canvas that hosts the inline create-card."""

    def __init__(self, flow_id: str = "python", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Node — Canvas Inline")
        apply_window_icon(self)
        self.resize(1040, 680)
        self._t = tokens()
        self._flow_id = flow_id
        self._placed: list[PlacedNode] = []
        self._card: InlineCreateCard | None = None
        self.setMouseTracking(True)

    # -- interaction -------------------------------------------------------- #
    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        self._open_card(e.position().x(), e.position().y())

    def _open_card(self, x: float, y: float) -> None:
        if self._card is not None:
            self._card.deleteLater()
        card = InlineCreateCard(self._flow_id, self._create, self._close_card, self)
        cx = int(min(max(8, x), self.width() - card.width() - 8))
        cy = int(min(max(8, y), self.height() - 360))
        card.move(cx, cy)
        card.show()
        card.setFocus()
        self._card = card
        self._card_origin = (cx, cy)

    def _close_card(self) -> None:
        if self._card is not None:
            self._card.deleteLater()
            self._card = None
        self.update()

    def _create(self, title, subtitle, glyph, inputs, outputs) -> None:
        ox, oy = getattr(self, "_card_origin", (80, 80))
        self._placed.append(PlacedNode(ox, oy, title, subtitle, glyph,
                                       list(inputs), list(outputs)))
        self._close_card()

    # -- painting ----------------------------------------------------------- #
    def paintEvent(self, _e) -> None:  # noqa: N802
        t = self._t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(t.canvas_bg))
        p.setPen(QPen(QColor(t.canvas_minor_grid), 1))
        for gx in range(0, self.width(), 24):
            p.drawLine(gx, 0, gx, self.height())
        for gy in range(0, self.height(), 24):
            p.drawLine(0, gy, self.width(), gy)
        p.setPen(QPen(QColor(t.canvas_major_grid), 1))
        for gx in range(0, self.width(), 120):
            p.drawLine(gx, 0, gx, self.height())
        for gy in range(0, self.height(), 120):
            p.drawLine(0, gy, self.width(), gy)

        if not self._placed and self._card is None:
            p.setPen(QColor(t.muted_fg))
            p.setFont(QFont("Segoe UI", 13))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Double-click anywhere to create a node")

        for n in self._placed:
            self._draw_node(p, n)
        p.end()

    def _draw_node(self, p: QPainter, n: PlacedNode) -> None:
        t = self._t
        rows = max(len(n.inputs), len(n.outputs), 1)
        w, hh = 230, 44 + rows * 24 + 10
        rect = QRectF(n.x, n.y, w, hh)
        path = QPainterPath()
        path.addRoundedRect(rect, 9, 9)
        p.fillPath(path, QColor(t.inspector_card_bg))
        p.setPen(QPen(QColor(t.accent), 1.4))
        p.drawPath(path)
        p.fillRect(QRectF(n.x, n.y, w, 40), QColor(t.panel_alt_bg))
        p.setPen(QPen(QColor(t.border), 1))
        p.drawLine(QPointF(n.x, n.y + 40), QPointF(n.x + w, n.y + 40))
        chip = QRectF(n.x + 10, n.y + 8, 24, 24)
        cp = QPainterPath()
        cp.addRoundedRect(chip, 5, 5)
        p.fillPath(cp, QColor(t.accent_strong))
        p.setPen(QColor("#fff"))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(chip, Qt.AlignmentFlag.AlignCenter, n.glyph[:3])
        p.setPen(QColor(t.panel_title_fg))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        p.drawText(QRectF(n.x + 42, n.y + 6, w - 48, 16),
                   Qt.AlignmentFlag.AlignVCenter, n.title[:24])
        p.setPen(QColor(t.muted_fg))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(n.x + 42, n.y + 22, w - 48, 14),
                   Qt.AlignmentFlag.AlignVCenter, n.subtitle[:32])
        p.setFont(QFont("Segoe UI", 8))
        for i, port in enumerate(n.inputs):
            cy = n.y + 54 + i * 24
            p.setBrush(QColor(t.accent_strong))
            p.setPen(QPen(QColor(t.accent_strong), 1))
            p.drawEllipse(QPointF(n.x, cy), 4, 4)
            p.setPen(QColor(t.app_fg))
            p.drawText(QPointF(n.x + 10, cy + 4), port.key)
        for i, port in enumerate(n.outputs):
            cy = n.y + 54 + i * 24
            p.setBrush(QColor(t.accent))
            p.setPen(QPen(QColor(t.accent), 1))
            p.drawEllipse(QPointF(n.x + w, cy), 4, 4)
            p.setPen(QColor(t.app_fg))
            p.drawText(QRectF(n.x + w / 2, cy - 6, w / 2 - 10, 14),
                       Qt.AlignmentFlag.AlignRight, port.key)


def make(flow_id: str = "python", parent=None) -> QWidget:
    return CanvasInlineCreate(flow_id, parent)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_corex_theme(app)
    w = make("python")
    w.show()
    sys.exit(app.exec())
