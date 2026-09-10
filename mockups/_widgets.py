"""Faithful, reusable field editors shared by all four wizard mockups.

These use the real COREX-styled Qt widgets so every design renders the same
node-creation content identically -- only the *layout/flow* differs per design.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mockups._theme import Port, WizField, tokens


def section_label(text: str) -> QLabel:
    """Uppercase muted section header -- reuses the app's settingsSectionTitle QSS."""
    lbl = QLabel(text.upper())
    lbl.setProperty("settingsSectionTitle", True)
    return lbl


def title_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("panelTitle")
    return lbl


def card(child: QWidget, *, margins=(14, 14, 14, 14)) -> QFrame:
    """Wrap a widget in the app's rounded settingsCard surface."""
    frame = QFrame()
    frame.setProperty("settingsCard", True)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(*margins)
    lay.setSpacing(10)
    lay.addWidget(child)
    return frame


def hint(text: str) -> QLabel:
    t = tokens()
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {t.muted_fg}; font-size: 11px;")
    return lbl


class CategoryPathEditor(QWidget):
    """Breadcrumb-style category editor (Custom › Python …)."""

    changed = pyqtSignal()

    def __init__(self, value=("Custom", "Python"), parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.edit = QLineEdit(" › ".join(value))
        self.edit.setPlaceholderText("Custom › MyGroup")
        self.edit.textChanged.connect(self.changed)
        add = QToolButton()
        add.setText("＋")
        add.setToolTip("Add sub-category")
        lay.addWidget(self.edit, 1)
        lay.addWidget(add)

    def value(self) -> tuple:
        return tuple(s.strip() for s in self.edit.text().split("›") if s.strip())


class PortListEditor(QWidget):
    """Editable list of ports: key, kind (exec/data), data_type, required."""

    changed = pyqtSignal()

    def __init__(self, ports=(), parent=None) -> None:
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(6)
        self._rows_box = QVBoxLayout()
        self._rows_box.setSpacing(6)
        self._root.addLayout(self._rows_box)
        add = QPushButton("＋  Add port")
        add.clicked.connect(lambda: (self._add_row(Port("new_port")), self.changed.emit()))
        self._root.addWidget(add, alignment=Qt.AlignmentFlag.AlignLeft)
        for p in ports:
            self._add_row(p)
        if not ports:
            self._add_row(Port("payload"))

    def _add_row(self, port: Port) -> None:
        row = QFrame()
        row.setProperty("settingsCard", True)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 6, 8, 6)
        rl.setSpacing(8)
        key = QLineEdit(port.key)
        key.setPlaceholderText("port_key")
        key.textChanged.connect(self.changed)
        kind = QComboBox()
        kind.addItems(["data", "exec"])
        kind.setCurrentText(port.kind)
        kind.setFixedWidth(78)
        kind.currentTextChanged.connect(self.changed)
        dtype = QLineEdit(port.data_type)
        dtype.setPlaceholderText("data_type")
        dtype.setFixedWidth(96)
        dtype.textChanged.connect(self.changed)
        req = QCheckBox("required")
        req.setChecked(port.required)
        req.toggled.connect(self.changed)
        rm = QToolButton()
        rm.setText("✕")
        rm.setToolTip("Remove port")

        def _remove() -> None:
            self._rows_box.removeWidget(row)
            row.deleteLater()
            self.changed.emit()

        rm.clicked.connect(_remove)
        rl.addWidget(key, 1)
        rl.addWidget(kind)
        rl.addWidget(dtype)
        rl.addWidget(req)
        rl.addWidget(rm)
        self._rows_box.addWidget(row)
        # remember widgets for value()
        row._fields = (key, kind, dtype, req)  # type: ignore[attr-defined]

    def value(self) -> list[Port]:
        out: list[Port] = []
        for i in range(self._rows_box.count()):
            w = self._rows_box.itemAt(i).widget()
            if w is None or not hasattr(w, "_fields"):
                continue
            key, kind, dtype, req = w._fields  # type: ignore[attr-defined]
            if key.text().strip():
                out.append(Port(key.text().strip(), kind.currentText(),
                                 dtype.text().strip() or "any", req.isChecked()))
        return out


def code_editor(text: str) -> QPlainTextEdit:
    ed = QPlainTextEdit()
    ed.setPlainText(text)
    f = QFont("Consolas")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(10)
    ed.setFont(f)
    ed.setMinimumHeight(150)
    ed.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    return ed


def make_editor(field: WizField) -> QWidget:
    """Return the faithful editor widget for one wizard field."""
    if field.kind == "string":
        e = QLineEdit(str(field.default))
        if field.required:
            e.setPlaceholderText(f"{field.label} (required)")
        return e
    if field.kind == "category_path":
        return CategoryPathEditor(field.default or ("Custom",))
    if field.kind == "port_list":
        return PortListEditor(field.default or ())
    if field.kind == "python_source":
        return code_editor(str(field.default))
    if field.kind == "enum":
        c = QComboBox()
        c.addItems(list(field.options))
        if field.default in field.options:
            c.setCurrentText(str(field.default))
        return c
    if field.kind == "bool":
        return QCheckBox(field.label)
    e = QLineEdit(str(field.default))
    return e


def field_block(field: WizField) -> tuple[QWidget, QWidget]:
    """Return (label_row, editor) -- label carries the required asterisk + hint."""
    head = QWidget()
    hl = QVBoxLayout(head)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(2)
    name = field.label + ("  *" if field.required else "")
    lab = QLabel(name)
    lab.setStyleSheet("font-weight: 600;")
    hl.addWidget(lab)
    if field.help:
        hl.addWidget(hint(field.help))
    return head, make_editor(field)


class FlowSwitch(QWidget):
    """Segmented Python-Script <-> Generic toggle used by every design."""

    flowChanged = pyqtSignal(str)

    def __init__(self, current: str = "python", parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._btns: dict[str, QPushButton] = {}
        for flow_id, text in (("python", "Python Script"),
                              ("generic", "Generic Custom Node")):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setChecked(flow_id == current)
            b.clicked.connect(lambda _=False, f=flow_id: self._pick(f))
            self._style(b, b.isChecked())
            self._btns[flow_id] = b
            lay.addWidget(b)
        lay.addStretch(1)

    def _style(self, btn: QPushButton, on: bool) -> None:
        t = tokens()
        if on:
            btn.setStyleSheet(
                f"QPushButton{{background:{t.accent_strong};color:#ffffff;"
                f"border:1px solid {t.accent};border-radius:3px;padding:5px 12px;}}")
        else:
            btn.setStyleSheet("")

    def _pick(self, flow_id: str) -> None:
        for fid, b in self._btns.items():
            b.setChecked(fid == flow_id)
            self._style(b, fid == flow_id)
        self.flowChanged.emit(flow_id)


def build_form(fields) -> tuple[QWidget, dict]:
    """A simple vertical form of field blocks. Returns (container, editors)."""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(14)
    editors: dict = {}
    for f in fields:
        head, ed = field_block(f)
        lay.addWidget(head)
        lay.addWidget(ed)
        editors[f.key] = ed
    lay.addStretch(1)
    return box, editors


def review_widget(flow) -> QWidget:
    """A read-only summary of what will be created (final wizard step)."""
    t = tokens()
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lay.addWidget(section_label("Review"))
    rows = [
        ("Node", flow.title),
        ("Category", flow.subtitle),
        ("Inputs", ", ".join(p.key for p in flow.preview_inputs) or "—"),
        ("Outputs", ", ".join(p.key for p in flow.preview_outputs) or "—"),
        ("Type", "core.python_script (script-backed)"
            if flow.flow_id == "python" else "generated NodeTypeSpec"),
    ]
    for k, v in rows:
        r = QLabel(f"<span style='color:{t.muted_fg}'>{k}</span>"
                   f"&nbsp;&nbsp;<b>{v}</b>")
        r.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(r)
    note = hint("Creating will register the node and add it to the library. "
                "(Mockup: no files are written.)")
    lay.addWidget(note)
    lay.addStretch(1)
    return box

