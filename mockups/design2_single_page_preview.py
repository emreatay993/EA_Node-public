"""Design 2 -- Single page + live preview.

All fields on one scrollable form (left) with a live COREX node card (right)
that updates as you type. No steps; everything visible at once.
"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mockups._node_preview import NodePreviewCard
from mockups._theme import (
    GENERIC_TEMPLATES,
    apply_corex_theme,
    apply_window_icon,
    generic_flow,
    python_script_flow,
)
from mockups._widgets import (
    CategoryPathEditor,
    FlowSwitch,
    PortListEditor,
    build_form,
    section_label,
    title_label,
)


class SinglePagePreview(QDialog):
    def __init__(self, flow_id: str = "python", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Node — Single Page + Live Preview")
        apply_window_icon(self)
        self.setModal(True)
        self.resize(940, 640)
        self._flow_id = flow_id
        self._template_idx = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.addWidget(title_label("Create Node"))
        head.addStretch(1)
        self._template_combo = QComboBox()
        self._template_combo.addItems([t["name"] for t in GENERIC_TEMPLATES])
        self._template_combo.currentIndexChanged.connect(self._on_template)
        self._template_combo.setVisible(flow_id == "generic")
        head.addWidget(self._template_combo)
        self._switch = FlowSwitch(flow_id)
        self._switch.flowChanged.connect(self._set_flow)
        head.addWidget(self._switch)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(16)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setMinimumWidth(460)
        body.addWidget(self._scroll, 3)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        rl.addWidget(section_label("Live preview"))
        self._preview = NodePreviewCard()
        rl.addWidget(self._preview, 1)
        self._meta = QLabel()
        self._meta.setWordWrap(True)
        rl.addWidget(self._meta)
        body.addWidget(right, 2)
        root.addLayout(body, 1)

        foot = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        create = QPushButton("✓  Create Node")
        create.clicked.connect(self._create)
        foot.addWidget(cancel)
        foot.addStretch(1)
        foot.addWidget(create)
        root.addLayout(foot)

        self._rebuild()

    def _flow(self):
        if self._flow_id == "python":
            return python_script_flow()
        return generic_flow(GENERIC_TEMPLATES[self._template_idx])

    def _set_flow(self, flow_id: str) -> None:
        self._flow_id = flow_id
        self._template_combo.setVisible(flow_id == "generic")
        self._rebuild()

    def _on_template(self, idx: int) -> None:
        self._template_idx = idx
        self._rebuild()

    def _rebuild(self) -> None:
        flow = self._flow()
        form, self._editors = build_form(flow.fields)
        self._scroll.setWidget(form)
        for ed in self._editors.values():
            self._bind(ed)
        self._refresh()

    def _bind(self, ed: QWidget) -> None:
        if isinstance(ed, QLineEdit):
            ed.textChanged.connect(self._refresh)
        elif isinstance(ed, (PortListEditor, CategoryPathEditor)):
            ed.changed.connect(self._refresh)
        elif isinstance(ed, QComboBox):
            ed.currentTextChanged.connect(self._refresh)

    def _refresh(self) -> None:
        flow = self._flow()
        name_key = "node_name" if self._flow_id == "python" else "display_name"
        title = flow.title
        if name_key in self._editors and isinstance(self._editors[name_key], QLineEdit):
            title = self._editors[name_key].text() or flow.title
        subtitle = flow.subtitle
        if "category_path" in self._editors and isinstance(
                self._editors["category_path"], CategoryPathEditor):
            subtitle = " › ".join(self._editors["category_path"].value()) or flow.subtitle
        ins = flow.preview_inputs
        outs = flow.preview_outputs
        if isinstance(self._editors.get("input_ports"), PortListEditor):
            ins = self._editors["input_ports"].value()
        if isinstance(self._editors.get("output_ports"), PortListEditor):
            outs = self._editors["output_ports"].value()
        self._preview.set_node(title=title, subtitle=subtitle,
                               glyph=flow.icon_glyph, inputs=ins, outputs=outs)
        kind = ("core.python_script (script-backed)" if self._flow_id == "python"
                else "generated NodeTypeSpec")
        self._meta.setText(
            f"<b>{title}</b><br><span>Type:</span> {kind}<br>"
            f"<span>{len(list(ins))}</span> inputs · "
            f"<span>{len(list(outs))}</span> outputs")

    def _create(self) -> None:
        flow = self._flow()
        QMessageBox.information(
            self, "Node created (mockup)",
            f"'{flow.title}' would be registered under {flow.subtitle}.\n"
            f"No files were written — this is a visual mockup.")
        self.accept()


def make(flow_id: str = "python", parent=None) -> QDialog:
    return SinglePagePreview(flow_id, parent)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_corex_theme(app)
    make("python").exec()
