from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ea_node_editor.ui.canvas_view_export import (
    CanvasViewExportError,
    MAX_EXPORT_SCALE,
    final_export_pixel_size,
)
from ea_node_editor.ui.pptx_export import SLIDE_SIZE_PRESETS


@dataclass(frozen=True, slots=True)
class CanvasViewExportDialogValues:
    view_ids: list[str]
    output_folder: Path
    scale: int
    crop_to_content: bool
    create_pptx: bool
    slide_size: str


class CanvasViewExportDialog(QDialog):
    def __init__(
        self,
        *,
        view_items: list[dict[str, Any]],
        initial_view_ids: list[str] | None = None,
        output_folder: Path | str,
        canvas_logical_size: tuple[float, float],
        device_pixel_ratio: float,
        browse_folder_callback: Callable[[str], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Canvas Views")
        self.setModal(True)
        self.resize(520, 440)

        self._view_items = [
            {
                "view_id": str(item.get("view_id", "") or "").strip(),
                "label": str(item.get("label", "") or item.get("name", "") or item.get("view_id", "") or "").strip(),
            }
            for item in view_items
        ]
        self._view_items = [item for item in self._view_items if item["view_id"]]
        self._canvas_logical_size = canvas_logical_size
        self._device_pixel_ratio = float(device_pixel_ratio)
        self._browse_folder_callback = browse_folder_callback

        initial_lookup = {str(view_id or "").strip() for view_id in initial_view_ids or []}
        if not initial_lookup:
            initial_lookup = {item["view_id"] for item in self._view_items}

        self.view_list = QListWidget(self)
        self.view_list.setObjectName("canvasViewExportViewList")
        self.view_list.setMinimumHeight(150)
        for item in self._view_items:
            label = item["label"] or item["view_id"]
            row = QListWidgetItem(label)
            row.setData(Qt.ItemDataRole.UserRole, item["view_id"])
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(
                Qt.CheckState.Checked
                if item["view_id"] in initial_lookup
                else Qt.CheckState.Unchecked
            )
            self.view_list.addItem(row)
        self.view_list.itemChanged.connect(self._update_ok_state)

        self.output_folder_edit = QLineEdit(str(output_folder or ""), self)
        self.output_folder_edit.setObjectName("canvasViewExportOutputFolderEdit")
        self.output_folder_edit.textChanged.connect(self._update_ok_state)
        self.browse_button = QPushButton("Browse...", self)
        self.browse_button.clicked.connect(self._browse_output_folder)

        output_row = QHBoxLayout()
        output_row.setContentsMargins(0, 0, 0, 0)
        output_row.addWidget(self.output_folder_edit, 1)
        output_row.addWidget(self.browse_button)
        output_widget = QWidget(self)
        output_widget.setLayout(output_row)

        self.scale_spin = QSpinBox(self)
        self.scale_spin.setObjectName("canvasViewExportScaleSpin")
        self.scale_spin.setRange(1, MAX_EXPORT_SCALE)
        self.scale_spin.setValue(1)
        self.scale_spin.setSuffix("x")
        self.scale_spin.valueChanged.connect(self._update_ok_state)

        self.pixel_size_label = QLabel("", self)
        self.pixel_size_label.setObjectName("canvasViewExportPixelSizeLabel")

        self.crop_check = QCheckBox("Crop to visible content", self)
        self.crop_check.setObjectName("canvasViewExportCropCheck")
        self.crop_check.setChecked(True)
        self.crop_check.toggled.connect(self._update_ok_state)

        self.pptx_check = QCheckBox("Create PowerPoint deck", self)
        self.pptx_check.setObjectName("canvasViewExportPptxCheck")
        self.pptx_check.toggled.connect(self._update_slide_size_enabled)

        self.slide_size_combo = QComboBox(self)
        self.slide_size_combo.setObjectName("canvasViewExportSlideSizeCombo")
        for label in SLIDE_SIZE_PRESETS:
            self.slide_size_combo.addItem(label, label)
        self.slide_size_combo.setEnabled(False)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("Views", self.view_list)
        form.addRow("Output folder", output_widget)
        form.addRow("PNG scale", self.scale_spin)
        form.addRow("PNG size", self.pixel_size_label)
        form.addRow("", self.crop_check)
        form.addRow("", self.pptx_check)
        form.addRow("Slide size", self.slide_size_combo)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

        self._update_ok_state()

    def values(self) -> CanvasViewExportDialogValues:
        slide_size = str(self.slide_size_combo.currentData() or self.slide_size_combo.currentText())
        return CanvasViewExportDialogValues(
            view_ids=self.selected_view_ids(),
            output_folder=Path(self.output_folder_edit.text().strip()).expanduser(),
            scale=int(self.scale_spin.value()),
            crop_to_content=bool(self.crop_check.isChecked()),
            create_pptx=bool(self.pptx_check.isChecked()),
            slide_size=slide_size,
        )

    def selected_view_ids(self) -> list[str]:
        selected: list[str] = []
        for row_index in range(self.view_list.count()):
            item = self.view_list.item(row_index)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(str(item.data(Qt.ItemDataRole.UserRole) or "").strip())
        return [view_id for view_id in selected if view_id]

    def _browse_output_folder(self) -> None:
        if self._browse_folder_callback is None:
            return
        selected = self._browse_folder_callback(str(self.output_folder_edit.text() or ""))
        if str(selected or "").strip():
            self.output_folder_edit.setText(str(selected).strip())

    def _update_slide_size_enabled(self) -> None:
        self.slide_size_combo.setEnabled(bool(self.pptx_check.isChecked()))
        self._update_ok_state()

    def _update_ok_state(self) -> None:
        error = ""
        try:
            width, height = final_export_pixel_size(
                canvas_logical_width=self._canvas_logical_size[0],
                canvas_logical_height=self._canvas_logical_size[1],
                device_pixel_ratio=self._device_pixel_ratio,
                scale=int(self.scale_spin.value()),
            )
            if self.crop_check.isChecked():
                self.pixel_size_label.setText(f"Up to {width} x {height} px per view before crop")
            else:
                self.pixel_size_label.setText(f"{width} x {height} px per view")
        except (CanvasViewExportError, ValueError, TypeError) as exc:
            self.pixel_size_label.setText(str(exc))
            error = str(exc)

        output_text = self.output_folder_edit.text().strip()
        if not self.selected_view_ids():
            error = "Select at least one view."
        elif not output_text:
            error = "Choose an output folder."
        ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(not error)


__all__ = ["CanvasViewExportDialog", "CanvasViewExportDialogValues"]
