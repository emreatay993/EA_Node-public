"""Design 3 -- Sidebar-section dialog.

Subclasses the *real* COREX SectionedSettingsDialog
(ea_node_editor/ui/dialogs/sectioned_settings_dialog.py): 190px left section
list + QStackedWidget, Cancel/Create. This is the most native option and the
least new code if it were actually implemented.
"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ea_node_editor.ui.dialogs.sectioned_settings_dialog import SectionedSettingsDialog

from mockups._theme import (
    GENERIC_TEMPLATES,
    apply_corex_theme,
    apply_window_icon,
    generic_flow,
    python_script_flow,
    steps_for,
)
from mockups._widgets import FlowSwitch, build_form, hint, review_widget, section_label


def _sections_for(flow_id: str):
    base = [(n.lower(), n) for n, _ in steps_for(
        python_script_flow() if flow_id == "python" else generic_flow())]
    if flow_id == "generic":
        base = [("type", "Type")] + base
    return base + [("review", "Review")]


class SidebarSectionWizard(SectionedSettingsDialog):
    def __init__(self, flow_id: str = "python", parent=None) -> None:
        self._flow_id = flow_id
        self._template_idx = 0
        super().__init__(
            window_title="Create Node — Sidebar Sections",
            header_text="Create a new node — pick a section on the left.",
            sections=_sections_for(flow_id),
            section_list_object_name="createNodeSectionList",
            header_object_name="panelTitle",
            size=(820, 560),
            parent=parent,
        )
        apply_window_icon(self)
        self.ok_button.setText("✓  Create Node")
        # Inject the flow switch directly under the header label.
        self._switch = FlowSwitch(flow_id)
        self._switch.flowChanged.connect(self._reload)
        self.layout().insertWidget(1, self._switch)

    # -- flow ---------------------------------------------------------------- #
    def _flow(self):
        if self._flow_id == "python":
            return python_script_flow()
        return generic_flow(GENERIC_TEMPLATES[self._template_idx])

    def _build_pages(self) -> None:
        flow = self._flow()
        if self._flow_id == "generic":
            self.add_section_page(self._scrolled(self._type_page()))
        for _name, fields in steps_for(flow):
            form, _ = build_form(fields)
            self.add_section_page(self._scrolled(form))
        self.add_section_page(self._scrolled(review_widget(flow)))

    @staticmethod
    def _scrolled(inner: QWidget) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setWidget(inner)
        lay.addWidget(sa)
        return wrap

    def _type_page(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(8)
        lay.addWidget(section_label("Node type"))
        lay.addWidget(hint("Choose a built-in to seed ports & category. "
                           "The remaining sections stay fully editable."))
        combo = QComboBox()
        combo.addItems([f"{t['name']}  —  {' › '.join(t['category'])}"
                        for t in GENERIC_TEMPLATES])
        combo.setCurrentIndex(self._template_idx)
        combo.currentIndexChanged.connect(self._on_template)
        lay.addWidget(combo)
        lay.addStretch(1)
        return box

    def _on_template(self, idx: int) -> None:
        self._template_idx = idx
        self._reload(self._flow_id)

    def _reload(self, flow_id: str) -> None:
        """Rebuild the section list + pages in place for the new flow."""
        self._flow_id = flow_id
        self.section_list.clear()
        while self.page_stack.count():
            w = self.page_stack.widget(0)
            self.page_stack.removeWidget(w)
            w.deleteLater()
        self._sections = list(_sections_for(flow_id))
        for _key, label in self._sections:
            self.section_list.addItem(label)
        self._build_pages()
        if self.section_list.count():
            self.section_list.setCurrentRow(0)

    def accept(self) -> None:  # noqa: D102
        flow = self._flow()
        QMessageBox.information(
            self, "Node created (mockup)",
            f"'{flow.title}' would be registered under {flow.subtitle}.\n"
            f"No files were written — this is a visual mockup.")
        super().accept()


def make(flow_id: str = "python", parent=None):
    return SidebarSectionWizard(flow_id, parent)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_corex_theme(app)
    make("python").exec()
