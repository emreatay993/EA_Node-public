from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRegularExpression, Qt
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QLineEdit,
)

from ea_node_editor.passive_style_normalization import (
    FLOW_EDGE_ARROW_HEADS,
    FLOW_EDGE_PATH_MODES,
    FLOW_EDGE_STYLE_PATTERNS,
    normalize_flow_edge_style_payload,
)
from ea_node_editor.ui.dialogs.passive_style_controls import (
    ColorHexFieldControl,
    set_dialog_role,
)
from ea_node_editor.ui.passive_style_presets import PassiveStylePresetCatalog


class FlowEdgeStyleDialog(QDialog):
    _PRESET_ID_ROLE = Qt.ItemDataRole.UserRole

    def __init__(
        self,
        initial_style: Any | None = None,
        parent=None,
        *,
        user_presets: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Flow Edge Style")
        self.setModal(True)
        self.resize(430, 0)

        self._color_fields: dict[str, ColorHexFieldControl] = {}
        self._preset_catalog = PassiveStylePresetCatalog("edge", user_presets)
        self._loading_style = False
        self._build_ui()
        self._load_style(initial_style)
        self._rebuild_preset_combo(selected_preset_id=self._preset_catalog.matching_preset_id(self.edge_style()))

    def edge_style(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, field in self._color_fields.items():
            value = field.text().strip()
            if value:
                payload[key] = value
        stroke_width = self.stroke_width_field.text().strip()
        if stroke_width:
            payload["stroke_width"] = stroke_width
        stroke_pattern = str(self.stroke_pattern_combo.currentData() or "").strip()
        if stroke_pattern:
            payload["stroke_pattern"] = stroke_pattern
        arrow_head = str(self.arrow_head_combo.currentData() or "").strip()
        if arrow_head:
            payload["arrow_head"] = arrow_head
        path_mode = str(self.path_mode_combo.currentData() or "").strip()
        if path_mode:
            payload["path_mode"] = path_mode
        return normalize_flow_edge_style_payload(payload)

    def user_presets(self) -> list[dict[str, Any]]:
        return self._preset_catalog.user_presets()

    def accept(self) -> None:
        if not self._validate():
            return
        super().accept()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        note = QLabel("Overrides apply only to flow edges. Leave fields blank to inherit the graph theme.", self)
        note.setWordWrap(True)
        note.setProperty("dialogRole", "muted")
        root.addWidget(note)

        self.validation_message = QLabel("Fix invalid style values before applying.", self)
        self.validation_message.setWordWrap(True)
        self.validation_message.setProperty("dialogRole", "error")
        self.validation_message.hide()
        root.addWidget(self.validation_message)

        preset_layout = QVBoxLayout()
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(6)

        preset_label = QLabel("Style Presets", self)
        preset_label.setStyleSheet("font-weight: 600;")
        preset_layout.addWidget(preset_label)

        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(8)

        self.preset_combo = QComboBox(self)
        self.preset_combo.setObjectName("preset_combo")
        self.preset_combo.currentIndexChanged.connect(self._sync_preset_controls)
        preset_row.addWidget(self.preset_combo, stretch=1)

        self.apply_preset_button = QPushButton("Apply Preset", self)
        self.apply_preset_button.setObjectName("apply_preset_button")
        self.apply_preset_button.clicked.connect(self._apply_selected_preset)
        preset_row.addWidget(self.apply_preset_button)

        preset_layout.addLayout(preset_row)

        preset_actions = QHBoxLayout()
        preset_actions.setContentsMargins(0, 0, 0, 0)
        preset_actions.setSpacing(8)

        self.save_preset_button = QPushButton("Save As New", self)
        self.save_preset_button.setObjectName("save_preset_button")
        self.save_preset_button.clicked.connect(self._save_current_style_as_preset)
        preset_actions.addWidget(self.save_preset_button)

        self.overwrite_preset_button = QPushButton("Overwrite", self)
        self.overwrite_preset_button.setObjectName("overwrite_preset_button")
        self.overwrite_preset_button.clicked.connect(self._overwrite_selected_preset)
        preset_actions.addWidget(self.overwrite_preset_button)

        self.rename_preset_button = QPushButton("Rename", self)
        self.rename_preset_button.setObjectName("rename_preset_button")
        self.rename_preset_button.clicked.connect(self._rename_selected_preset)
        preset_actions.addWidget(self.rename_preset_button)

        self.delete_preset_button = QPushButton("Delete", self)
        self.delete_preset_button.setObjectName("delete_preset_button")
        self.delete_preset_button.setProperty("dialogRole", "danger")
        self.delete_preset_button.clicked.connect(self._delete_selected_preset)
        preset_actions.addWidget(self.delete_preset_button)

        preset_layout.addLayout(preset_actions)

        self.preset_status_label = QLabel(self)
        self.preset_status_label.setObjectName("preset_status_label")
        self.preset_status_label.setProperty("dialogRole", "muted")
        self.preset_status_label.setWordWrap(True)
        preset_layout.addWidget(self.preset_status_label)

        root.addLayout(preset_layout)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)
        root.addLayout(form)

        for key, label in (
            ("stroke_color", "Stroke Color"),
            ("label_text_color", "Label Text Color"),
            ("label_background_color", "Label Background Color"),
        ):
            field = ColorHexFieldControl(self, allow_empty=True, color_dialog_title=f"Pick {label}")
            field.setObjectNames(value_name=f"{key}_value", swatch_name=f"{key}_swatch")
            field.valueChanged.connect(self._sync_validation_message)
            field.valueChanged.connect(self._sync_preset_selection_for_current_style)
            self._color_fields[key] = field
            form.addRow(label, field)

        self.stroke_width_field = QLineEdit(self)
        self.stroke_width_field.setObjectName("stroke_width_value")
        self.stroke_width_field.setPlaceholderText("inherit")
        self.stroke_width_field.setValidator(QRegularExpressionValidator(QRegularExpression(r"(?:\d+(?:\.\d+)?)?"), self))
        self.stroke_width_field.textChanged.connect(self._sync_validation_message)
        self.stroke_width_field.textChanged.connect(self._sync_preset_selection_for_current_style)
        form.addRow("Stroke Width", self.stroke_width_field)

        self.stroke_pattern_combo = QComboBox(self)
        self.stroke_pattern_combo.setObjectName("stroke_pattern_combo")
        self.stroke_pattern_combo.addItem("Inherit", "")
        for value in FLOW_EDGE_STYLE_PATTERNS:
            self.stroke_pattern_combo.addItem(value.title(), value)
        self.stroke_pattern_combo.currentIndexChanged.connect(self._sync_preset_selection_for_current_style)
        form.addRow("Stroke Pattern", self.stroke_pattern_combo)

        self.arrow_head_combo = QComboBox(self)
        self.arrow_head_combo.setObjectName("arrow_head_combo")
        self.arrow_head_combo.addItem("Inherit", "")
        for value in FLOW_EDGE_ARROW_HEADS:
            self.arrow_head_combo.addItem(value.title(), value)
        self.arrow_head_combo.currentIndexChanged.connect(self._sync_preset_selection_for_current_style)
        form.addRow("Arrow Head", self.arrow_head_combo)

        self.path_mode_combo = QComboBox(self)
        self.path_mode_combo.setObjectName("path_mode_combo")
        self.path_mode_combo.addItem("Auto", "")
        for value in FLOW_EDGE_PATH_MODES:
            if value == "auto":
                continue
            self.path_mode_combo.addItem(value.title(), value)
        self.path_mode_combo.currentIndexChanged.connect(self._sync_preset_selection_for_current_style)
        form.addRow("Path Mode", self.path_mode_combo)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)

        self.apply_button = QPushButton("Apply", self)
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.clicked.connect(self.accept)
        buttons.addWidget(self.apply_button)

        root.addLayout(buttons)

    def _load_style(self, initial_style: Any | None) -> None:
        self._loading_style = True
        normalized = normalize_flow_edge_style_payload(initial_style)
        for key, field in self._color_fields.items():
            field.setText(normalized.get(key, ""))
        if "stroke_width" in normalized:
            self.stroke_width_field.setText(_format_number(normalized["stroke_width"]))
        self.stroke_pattern_combo.setCurrentIndex(max(0, self.stroke_pattern_combo.findData(normalized.get("stroke_pattern", ""))))
        self.arrow_head_combo.setCurrentIndex(max(0, self.arrow_head_combo.findData(normalized.get("arrow_head", ""))))
        self.path_mode_combo.setCurrentIndex(max(0, self.path_mode_combo.findData(normalized.get("path_mode", ""))))
        self._loading_style = False
        self._sync_validation_message()
        self._sync_preset_selection_for_current_style()

    def _validate(self) -> bool:
        invalid = False
        for field in self._color_fields.values():
            value = field.text().strip()
            if value and field.is_valid():
                field.mark_valid()
            elif not value:
                field.mark_valid()
            else:
                field.mark_invalid()
                invalid = True

        if _is_valid_decimal(self.stroke_width_field.text()):
            set_dialog_role(self.stroke_width_field, None)
        else:
            set_dialog_role(self.stroke_width_field, "error")
            invalid = True

        self.validation_message.setVisible(invalid)
        if invalid:
            QMessageBox.warning(
                self,
                "Invalid Flow Edge Style",
                "Flow edge styles must use valid hex colors and positive numeric values.",
            )
            return False
        return True

    def _sync_validation_message(self) -> None:
        invalid_colors = any(field.text().strip() and not field.is_valid() for field in self._color_fields.values())
        invalid_width = not _is_valid_decimal(self.stroke_width_field.text())
        self.validation_message.setVisible(invalid_colors or invalid_width)

    def _selected_preset_id(self) -> str:
        return str(self.preset_combo.currentData(self._PRESET_ID_ROLE) or "").strip()

    def _rebuild_preset_combo(self, *, selected_preset_id: str = "") -> None:
        target_id = str(selected_preset_id or self._selected_preset_id()).strip()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("Current Style")
        self.preset_combo.setItemData(0, "", self._PRESET_ID_ROLE)
        for entry in self._preset_catalog.entries():
            label_prefix = "Starter" if entry.get("read_only") else "Project"
            self.preset_combo.addItem(f"{label_prefix}: {entry['name']}")
            index = self.preset_combo.count() - 1
            self.preset_combo.setItemData(index, entry["preset_id"], self._PRESET_ID_ROLE)
        if target_id:
            index = self.preset_combo.findData(target_id, self._PRESET_ID_ROLE)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)
        if self.preset_combo.currentIndex() < 0 and self.preset_combo.count():
            self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)
        self._sync_preset_controls()

    def _sync_preset_controls(self) -> None:
        preset = self._preset_catalog.get(self._selected_preset_id())
        has_preset = preset is not None
        read_only = bool(preset and preset.get("read_only"))
        self.apply_preset_button.setEnabled(has_preset)
        self.overwrite_preset_button.setEnabled(has_preset and not read_only)
        self.rename_preset_button.setEnabled(has_preset and not read_only)
        self.delete_preset_button.setEnabled(has_preset and not read_only)
        if not preset:
            self.preset_status_label.setText("Current style does not exactly match a saved preset.")
        elif read_only:
            self.preset_status_label.setText("Starter presets are read-only and are not saved into the project.")
        else:
            self.preset_status_label.setText("Project presets are saved with the current project only.")

    def _apply_selected_preset(self) -> None:
        preset = self._preset_catalog.get(self._selected_preset_id())
        if preset is None:
            return
        self._load_style(preset.get("style"))

    def _save_current_style_as_preset(self) -> None:
        style = self._validated_style_payload()
        if style is None:
            return
        name, accepted = QInputDialog.getText(self, "Save Edge Preset", "Preset name:")
        if not accepted:
            return
        entry = self._preset_catalog.save_new(name, style)
        if entry is None:
            return
        self._rebuild_preset_combo(selected_preset_id=entry["preset_id"])

    def _overwrite_selected_preset(self) -> None:
        preset_id = self._selected_preset_id()
        if not self._preset_catalog.is_user_preset(preset_id):
            return
        style = self._validated_style_payload()
        if style is None:
            return
        if self._preset_catalog.overwrite(preset_id, style):
            self._rebuild_preset_combo(selected_preset_id=preset_id)

    def _rename_selected_preset(self) -> None:
        preset = self._preset_catalog.get(self._selected_preset_id())
        if preset is None or preset.get("read_only"):
            return
        name, accepted = QInputDialog.getText(
            self,
            "Rename Edge Preset",
            "Preset name:",
            text=str(preset.get("name", "")),
        )
        if not accepted:
            return
        if self._preset_catalog.rename(str(preset.get("preset_id", "")), name):
            self._rebuild_preset_combo(selected_preset_id=str(preset.get("preset_id", "")))

    def _delete_selected_preset(self) -> None:
        preset = self._preset_catalog.get(self._selected_preset_id())
        if preset is None or preset.get("read_only"):
            return
        choice = QMessageBox.question(
            self,
            "Delete Edge Preset",
            f"Delete preset '{preset['name']}' from this project?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        if self._preset_catalog.delete(str(preset.get("preset_id", ""))):
            self._rebuild_preset_combo()

    def _validated_style_payload(self) -> dict[str, Any] | None:
        if not self._validate():
            return None
        return self.edge_style()

    def _sync_preset_selection_for_current_style(self) -> None:
        if self._loading_style:
            return
        matching_preset_id = self._preset_catalog.matching_preset_id(self.edge_style())
        current_preset_id = self._selected_preset_id()
        if matching_preset_id == current_preset_id:
            self._sync_preset_controls()
            return
        self.preset_combo.blockSignals(True)
        index = self.preset_combo.findData(matching_preset_id, self._PRESET_ID_ROLE)
        self.preset_combo.setCurrentIndex(max(0, index))
        self.preset_combo.blockSignals(False)
        self._sync_preset_controls()


def _format_number(value: object) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else str(numeric)


def _is_valid_decimal(value: str) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return True
    try:
        numeric = float(normalized)
    except ValueError:
        return False
    return numeric > 0.0


__all__ = ["FlowEdgeStyleDialog"]
