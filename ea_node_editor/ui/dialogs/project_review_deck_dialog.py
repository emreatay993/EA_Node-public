from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ea_node_editor.ui.pptx_export import SLIDE_SIZE_PRESETS
from ea_node_editor.ui.project_review_deck import ProjectReviewDeckPlan


@dataclass(frozen=True, slots=True)
class ProjectReviewDeckDialogValues:
    slide_ids: list[str]
    output_path: Path
    slide_size: str
    template_path: Path | None
    crop_canvas_snapshots: bool


class ProjectReviewDeckDialog(QDialog):
    def __init__(
        self,
        *,
        plan: ProjectReviewDeckPlan,
        output_path: Path | str,
        browse_output_callback: Callable[[str], str] | None = None,
        browse_template_callback: Callable[[str], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Project Review Deck")
        self.setModal(True)
        self.resize(760, 620)
        self._plan = plan
        self._browse_output_callback = browse_output_callback
        self._browse_template_callback = browse_template_callback

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.summary_label = QLabel(
            f"{plan.project_name} - {plan.slide_count} proposed slides",
            self,
        )
        self.summary_label.setObjectName("projectReviewDeckSummaryLabel")
        layout.addWidget(self.summary_label)

        self.tree = QTreeWidget(self)
        self.tree.setObjectName("projectReviewDeckTree")
        self.tree.setHeaderLabels(["Slide", "Type"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.itemChanged.connect(self._sync_section_check_state)
        layout.addWidget(self.tree, 1)
        self._populate_tree()

        move_row = QHBoxLayout()
        move_row.setContentsMargins(0, 0, 0, 0)
        self.move_up_button = QPushButton("Move Up", self)
        self.move_up_button.setObjectName("projectReviewDeckMoveUpButton")
        self.move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self.move_down_button = QPushButton("Move Down", self)
        self.move_down_button.setObjectName("projectReviewDeckMoveDownButton")
        self.move_down_button.clicked.connect(lambda: self._move_selected(1))
        move_row.addStretch(1)
        move_row.addWidget(self.move_up_button)
        move_row.addWidget(self.move_down_button)
        layout.addLayout(move_row)

        self.output_path_edit = QLineEdit(str(output_path or ""), self)
        self.output_path_edit.setObjectName("projectReviewDeckOutputPathEdit")
        self.output_path_edit.textChanged.connect(self._update_ok_state)
        self.output_browse_button = QPushButton("Browse...", self)
        self.output_browse_button.clicked.connect(self._browse_output_path)
        output_row = self._path_row(self.output_path_edit, self.output_browse_button)

        self.template_path_edit = QLineEdit("", self)
        self.template_path_edit.setObjectName("projectReviewDeckTemplatePathEdit")
        self.template_browse_button = QPushButton("Browse...", self)
        self.template_browse_button.clicked.connect(self._browse_template_path)
        self.template_clear_button = QPushButton("Clear", self)
        self.template_clear_button.clicked.connect(lambda: self.template_path_edit.clear())
        template_row = self._path_row(
            self.template_path_edit,
            self.template_browse_button,
            self.template_clear_button,
        )

        self.slide_size_combo = QComboBox(self)
        self.slide_size_combo.setObjectName("projectReviewDeckSlideSizeCombo")
        for label in SLIDE_SIZE_PRESETS:
            self.slide_size_combo.addItem(label, label)

        self.crop_check = QCheckBox("Crop canvas snapshots to content", self)
        self.crop_check.setObjectName("projectReviewDeckCropCanvasSnapshotsCheck")
        self.crop_check.setChecked(True)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("Output deck", output_row)
        form.addRow("Corporate template", template_row)
        form.addRow("Slide size", self.slide_size_combo)
        form.addRow("", self.crop_check)
        layout.addLayout(form)

        self.warning_label = QLabel("\n".join(plan.warnings), self)
        self.warning_label.setObjectName("projectReviewDeckWarningLabel")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(bool(plan.warnings))
        layout.addWidget(self.warning_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update_ok_state()

    def values(self) -> ProjectReviewDeckDialogValues:
        template_text = self.template_path_edit.text().strip()
        return ProjectReviewDeckDialogValues(
            slide_ids=self.selected_slide_ids(),
            output_path=Path(self.output_path_edit.text().strip()).expanduser(),
            slide_size=str(self.slide_size_combo.currentData() or self.slide_size_combo.currentText()),
            template_path=Path(template_text).expanduser() if template_text else None,
            crop_canvas_snapshots=bool(self.crop_check.isChecked()),
        )

    def selected_slide_ids(self) -> list[str]:
        selected: list[str] = []
        for section_index in range(self.tree.topLevelItemCount()):
            section = self.tree.topLevelItem(section_index)
            for child_index in range(section.childCount()):
                item = section.child(child_index)
                if item.checkState(0) == Qt.CheckState.Checked:
                    slide_id = str(item.data(0, Qt.ItemDataRole.UserRole) or "").strip()
                    if slide_id:
                        selected.append(slide_id)
        return selected

    @staticmethod
    def _path_row(*widgets: QWidget) -> QWidget:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        for index, widget in enumerate(widgets):
            row.addWidget(widget, 1 if index == 0 else 0)
        container = QWidget()
        container.setLayout(row)
        return container

    def _populate_tree(self) -> None:
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            for section in self._plan.sections:
                section_item = QTreeWidgetItem([section.title, "Section"])
                section_item.setFlags(section_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                section_item.setCheckState(0, Qt.CheckState.Checked if section.checked else Qt.CheckState.Unchecked)
                for slide in section.slides:
                    child = QTreeWidgetItem([slide.title, slide.kind])
                    child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.CheckState.Checked if slide.checked else Qt.CheckState.Unchecked)
                    child.setData(0, Qt.ItemDataRole.UserRole, slide.slide_id)
                    section_item.addChild(child)
                self.tree.addTopLevelItem(section_item)
                section_item.setExpanded(True)
        finally:
            self.tree.blockSignals(False)
        self.tree.resizeColumnToContents(0)

    def _sync_section_check_state(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        if item.parent() is not None:
            self._update_ok_state()
            return
        self.tree.blockSignals(True)
        try:
            state = item.checkState(0)
            for child_index in range(item.childCount()):
                item.child(child_index).setCheckState(0, state)
        finally:
            self.tree.blockSignals(False)
        self._update_ok_state()

    def _move_selected(self, direction: int) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        normalized_direction = -1 if int(direction) < 0 else 1
        parent = item.parent()
        if parent is None:
            self._move_section(item, normalized_direction)
            return
        self._move_slide(item, parent, normalized_direction)
        self._update_ok_state()

    def _move_section(self, item: QTreeWidgetItem, direction: int) -> None:
        index = self.tree.indexOfTopLevelItem(item)
        target = index + direction
        if index < 0 or target < 0 or target >= self.tree.topLevelItemCount():
            return
        moved = self.tree.takeTopLevelItem(index)
        self.tree.insertTopLevelItem(target, moved)
        moved.setExpanded(True)
        self.tree.setCurrentItem(moved)

    def _move_slide(
        self,
        item: QTreeWidgetItem,
        parent: QTreeWidgetItem,
        direction: int,
    ) -> None:
        index = parent.indexOfChild(item)
        target = index + int(direction)
        if 0 <= target < parent.childCount():
            moved = parent.takeChild(index)
            parent.insertChild(target, moved)
            self.tree.setCurrentItem(moved)
            return
        parent_index = self.tree.indexOfTopLevelItem(parent)
        destination_index = parent_index + direction
        if destination_index < 0 or destination_index >= self.tree.topLevelItemCount():
            return
        destination = self.tree.topLevelItem(destination_index)
        insert_index = destination.childCount() if direction < 0 else 0
        moved = parent.takeChild(index)
        destination.insertChild(insert_index, moved)
        destination.setExpanded(True)
        self.tree.setCurrentItem(moved)

    def _browse_output_path(self) -> None:
        if self._browse_output_callback is None:
            return
        selected = self._browse_output_callback(str(self.output_path_edit.text() or ""))
        if str(selected or "").strip():
            self.output_path_edit.setText(str(selected).strip())

    def _browse_template_path(self) -> None:
        if self._browse_template_callback is None:
            return
        selected = self._browse_template_callback(str(self.template_path_edit.text() or ""))
        if str(selected or "").strip():
            self.template_path_edit.setText(str(selected).strip())

    def _update_ok_state(self) -> None:
        ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(bool(self.output_path_edit.text().strip()) and bool(self.selected_slide_ids()))


__all__ = ["ProjectReviewDeckDialog", "ProjectReviewDeckDialogValues"]
