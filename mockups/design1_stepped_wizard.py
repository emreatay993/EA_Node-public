"""Design 1 -- Stepped wizard.

Classic guided flow: a left step rail (Identity > Ports > ... > Review) with
Back / Next / Create. Familiar and hand-holding. For the generic flow the first
step is a node-type/template picker.
"""
from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mockups._theme import (
    GENERIC_TEMPLATES,
    apply_corex_theme,
    apply_window_icon,
    generic_flow,
    python_script_flow,
    steps_for,
    tokens,
)
from mockups._widgets import (
    FlowSwitch,
    build_form,
    hint,
    review_widget,
    section_label,
    title_label,
)


class StepRail(QWidget):
    """Vertical numbered step list with an accent-highlighted current step."""

    def __init__(self, on_jump, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(190)
        self._on_jump = on_jump
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 4, 8, 4)
        self._lay.setSpacing(4)
        self._buttons: list[QPushButton] = []

    def set_steps(self, names: list[str]) -> None:
        while self._lay.count():
            it = self._lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._buttons.clear()
        for i, name in enumerate(names):
            b = QPushButton(f"  {i + 1}.  {name}")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, idx=i: self._on_jump(idx))
            self._buttons.append(b)
            self._lay.addWidget(b)
        self._lay.addStretch(1)

    def set_current(self, idx: int) -> None:
        t = tokens()
        for i, b in enumerate(self._buttons):
            done = i < idx
            cur = i == idx
            b.setChecked(cur)
            if cur:
                b.setStyleSheet(
                    f"QPushButton{{text-align:left;background:{t.accent_strong};"
                    f"color:#fff;border:1px solid {t.accent};border-radius:4px;"
                    f"padding:7px 8px;font-weight:600;}}")
            elif done:
                b.setStyleSheet(
                    f"QPushButton{{text-align:left;background:transparent;"
                    f"color:{t.accent};border:1px solid {t.border};"
                    f"border-radius:4px;padding:7px 8px;}}")
            else:
                b.setStyleSheet(
                    f"QPushButton{{text-align:left;background:transparent;"
                    f"color:{t.muted_fg};border:1px solid {t.border};"
                    f"border-radius:4px;padding:7px 8px;}}")


def _template_picker(on_pick) -> QWidget:
    """Selectable cards of real built-in node templates (generic flow step 1)."""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lay.addWidget(section_label("Pick a node type"))
    lay.addWidget(hint("Start from an existing built-in. Its ports and category "
                        "seed the next steps -- everything stays editable."))
    cards: list[QFrame] = []

    def select(i: int) -> None:
        for j, c in enumerate(cards):
            c.setProperty("performanceModeSelected", j == i)
            c.style().unpolish(c)
            c.style().polish(c)
        on_pick(i)

    for i, tpl in enumerate(GENERIC_TEMPLATES):
        c = QFrame()
        c.setProperty("performanceModeOption", True)
        c.setProperty("performanceModeSelected", i == 0)
        c.setCursor(Qt.CursorShape.PointingHandCursor)
        cl = QHBoxLayout(c)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(12)
        g = QLabel(tpl["glyph"])
        g.setFixedWidth(34)
        g.setStyleSheet("font-weight:700;font-size:14px;")
        txt = QWidget()
        tv = QVBoxLayout(txt)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(2)
        nm = QLabel(f"{tpl['name']}")
        nm.setStyleSheet("font-weight:600;")
        tv.addWidget(nm)
        tv.addWidget(hint(f"{' › '.join(tpl['category'])} — {tpl['desc']}"))
        cl.addWidget(g)
        cl.addWidget(txt, 1)
        c.mousePressEvent = lambda _e, idx=i: select(idx)  # type: ignore[assignment]
        cards.append(c)
        lay.addWidget(c)
    lay.addStretch(1)
    return box


class SteppedWizard(QDialog):
    def __init__(self, flow_id: str = "python", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Node — Stepped Wizard")
        apply_window_icon(self)
        self.setModal(True)
        self.resize(880, 600)
        self._flow_id = flow_id
        self._template_idx = 0
        self._index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.addWidget(title_label("Create Node"))
        head.addStretch(1)
        self._switch = FlowSwitch(flow_id)
        self._switch.flowChanged.connect(self._set_flow)
        head.addWidget(self._switch)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(14)
        self._rail = StepRail(self._jump)
        body.addWidget(self._rail, 0)
        self._stack = QStackedWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self._stack)
        body.addWidget(scroll, 1)
        root.addLayout(body, 1)

        foot = QHBoxLayout()
        self._cancel = QPushButton("Cancel")
        self._cancel.clicked.connect(self.reject)
        self._back = QPushButton("‹ Back")
        self._back.clicked.connect(lambda: self._jump(self._index - 1))
        self._next = QPushButton("Next ›")
        self._next.clicked.connect(self._advance)
        foot.addWidget(self._cancel)
        foot.addStretch(1)
        foot.addWidget(self._back)
        foot.addWidget(self._next)
        root.addLayout(foot)

        self._rebuild()

    # -- flow / step management -------------------------------------------- #
    def _flow(self):
        if self._flow_id == "python":
            return python_script_flow()
        return generic_flow(GENERIC_TEMPLATES[self._template_idx])

    def _set_flow(self, flow_id: str) -> None:
        self._flow_id = flow_id
        self._index = 0
        self._rebuild()

    def _rebuild(self) -> None:
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()
        flow = self._flow()
        self._step_names = []
        if self._flow_id == "generic":
            self._step_names.append("Template")
            self._stack.addWidget(self._wrap(
                _template_picker(self._on_template)))
        for name, fields in steps_for(flow):
            self._step_names.append(name)
            form, _ = build_form(fields)
            self._stack.addWidget(self._wrap(form))
        self._step_names.append("Review")
        self._stack.addWidget(self._wrap(review_widget(flow)))
        self._rail.set_steps(self._step_names)
        self._index = min(self._index, len(self._step_names) - 1)
        self._sync()

    @staticmethod
    def _wrap(inner: QWidget) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 4, 8, 4)
        lay.addWidget(inner)
        return page

    def _on_template(self, idx: int) -> None:
        self._template_idx = idx
        # refresh later steps to reflect the chosen template's defaults
        keep = self._index
        self._rebuild()
        self._jump(keep)

    def _jump(self, idx: int) -> None:
        self._index = max(0, min(idx, len(self._step_names) - 1))
        self._sync()

    def _advance(self) -> None:
        if self._index >= len(self._step_names) - 1:
            self._create()
            return
        self._jump(self._index + 1)

    def _sync(self) -> None:
        self._stack.setCurrentIndex(self._index)
        self._rail.set_current(self._index)
        self._back.setEnabled(self._index > 0)
        last = self._index == len(self._step_names) - 1
        self._next.setText("✓  Create Node" if last else "Next ›")

    def _create(self) -> None:
        f = self._flow()
        QMessageBox.information(
            self, "Node created (mockup)",
            f"'{f.title}' would be registered under {f.subtitle}.\n"
            f"No files were written — this is a visual mockup.")
        self.accept()


def make(flow_id: str = "python", parent=None) -> QDialog:
    return SteppedWizard(flow_id, parent)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_corex_theme(app)
    make("python").exec()
