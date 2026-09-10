from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class SectionedSettingsDialog(QDialog):
    def __init__(
        self,
        *,
        window_title: str,
        header_text: str,
        sections: Sequence[tuple[str, str]],
        section_list_object_name: str | None = None,
        header_object_name: str | None = None,
        size: tuple[int, int] = (760, 520),
        scroll_pages: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._sections = list(sections)
        self.setWindowTitle(window_title)
        self.setModal(True)
        self.resize(*size)

        self.section_list = QListWidget(self)
        self.section_list.setFixedWidth(190)
        if section_list_object_name:
            self.section_list.setObjectName(section_list_object_name)
        for _key, label in self._sections:
            self.section_list.addItem(QListWidgetItem(label))

        self.page_stack = QStackedWidget(self)
        self._build_pages()
        if self.page_stack.count() != len(self._sections):
            raise RuntimeError(
                f"{self.__class__.__name__} built {self.page_stack.count()} pages for {len(self._sections)} sections."
            )
        self.page_scroll_area: QScrollArea | None = None
        page_container: QWidget = self.page_stack
        if scroll_pages:
            self.page_scroll_area = QScrollArea(self)
            self.page_scroll_area.setObjectName("sectionedSettingsPageScrollArea")
            self.page_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
            self.page_scroll_area.setWidgetResizable(True)
            self.page_scroll_area.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            self.page_scroll_area.setWidget(self.page_stack)
            page_container = self.page_scroll_area

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)
        body_layout.addWidget(self.section_list, stretch=0)
        body_layout.addWidget(page_container, stretch=1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.cancel_button = QPushButton("Cancel", self)
        self.ok_button = QPushButton("OK", self)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.ok_button)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        self.header_label = QLabel(header_text, self)
        if header_object_name:
            self.header_label.setObjectName(header_object_name)
        root.addWidget(self.header_label)
        root.addLayout(body_layout, stretch=1)
        root.addLayout(actions)

        self.section_list.currentRowChanged.connect(self.page_stack.setCurrentIndex)
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button.clicked.connect(self.accept)
        if self.section_list.count() and self.page_stack.count():
            self.section_list.setCurrentRow(0)

    def add_section_page(self, page: QWidget) -> None:
        self.page_stack.addWidget(page)

    def _build_pages(self) -> None:
        raise NotImplementedError
