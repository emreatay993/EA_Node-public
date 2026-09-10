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
    QWidget,
    QLineEdit,
)

from ea_node_editor.passive_style_normalization import (
    DEFAULT_PASSIVE_NODE_STYLE_GRADIENT_DIRECTION,
    PASSIVE_NODE_STYLE_GRADIENT_DIRECTIONS,
    PASSIVE_NODE_STYLE_FONT_WEIGHTS,
    normalize_passive_node_style_payload,
)
from ea_node_editor.ui.dialogs.passive_style_controls import (
    ColorHexFieldControl,
    set_dialog_role,
)
from ea_node_editor.ui.passive_style_presets import PassiveStylePresetCatalog


class PassiveNodeStyleDialog(QDialog):
    _PRESET_ID_ROLE = Qt.ItemDataRole.UserRole

    def __init__(
        self,
        initial_style: Any | None = None,
        parent=None,
        *,
        user_presets: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Passive Node Style")
        self.setModal(True)
        self.resize(460, 0)

        self._color_fields: dict[str, ColorHexFieldControl] = {}
        self._gradient_color_fields: dict[str, ColorHexFieldControl] = {}
        self._gradient_mode_combos: dict[str, QComboBox] = {}
        self._gradient_direction_combos: dict[str, QComboBox] = {}
        self._numeric_fields: dict[str, QLineEdit] = {}
        self._preset_catalog = PassiveStylePresetCatalog("node", user_presets)
        self._loading_style = False

        self._build_ui()
        self._load_style(initial_style)
        self._rebuild_preset_combo(selected_preset_id=self._preset_catalog.matching_preset_id(self.node_style()))

    def node_style(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, field in self._color_fields.items():
            value = field.text().strip()
            if value:
                payload[key] = value
        for key, field in self._numeric_fields.items():
            value = field.text().strip()
            if value:
                payload[key] = value
        self._append_gradient_payload(
            payload,
            mode_key="gradient",
            enabled_key="gradient_enabled",
            color_key="gradient_color",
            direction_key="gradient_direction",
        )
        weight = str(self.font_weight_combo.currentData() or "").strip()
        if weight:
            payload["font_weight"] = weight
        return normalize_passive_node_style_payload(payload)

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

        note = QLabel("Overrides apply only to passive nodes. Leave fields blank to inherit the graph theme.", self)
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
            ("fill_color", "Fill Color"),
            ("border_color", "Border Color"),
            ("text_color", "Text Color"),
        ):
            field = ColorHexFieldControl(self, allow_empty=True, color_dialog_title=f"Pick {label}")
            field.setObjectNames(value_name=f"{key}_value", swatch_name=f"{key}_swatch")
            field.valueChanged.connect(self._sync_validation_message)
            field.valueChanged.connect(self._sync_preset_selection_for_current_style)
            self._color_fields[key] = field
            form.addRow(label, field)

            if key == "fill_color":
                form.addRow(
                    "Body Gradient",
                    self._gradient_row(
                        mode_key="gradient",
                        color_key="gradient_color",
                        direction_key="gradient_direction",
                        color_label="Body Gradient Color",
                    ),
                )
        self._numeric_fields["border_width"] = self._numeric_field(
            object_name="border_width_value",
            placeholder="inherit",
            validator=QRegularExpressionValidator(QRegularExpression(r"(?:\d+(?:\.\d+)?)?"), self),
        )
        form.addRow("Border Width", self._numeric_fields["border_width"])

        self._numeric_fields["corner_radius"] = self._numeric_field(
            object_name="corner_radius_value",
            placeholder="inherit",
            validator=QRegularExpressionValidator(QRegularExpression(r"(?:\d+(?:\.\d+)?)?"), self),
        )
        form.addRow("Corner Radius", self._numeric_fields["corner_radius"])

        self._numeric_fields["font_size"] = self._numeric_field(
            object_name="font_size_value",
            placeholder="inherit",
            validator=QRegularExpressionValidator(QRegularExpression(r"(?:\d+)?"), self),
        )
        form.addRow("Font Size", self._numeric_fields["font_size"])

        self.font_weight_combo = QComboBox(self)
        self.font_weight_combo.setObjectName("font_weight_combo")
        self.font_weight_combo.addItem("Inherit", "")
        for value in PASSIVE_NODE_STYLE_FONT_WEIGHTS:
            self.font_weight_combo.addItem(value.title(), value)
        self.font_weight_combo.currentIndexChanged.connect(self._sync_preset_selection_for_current_style)
        form.addRow("Font Weight", self.font_weight_combo)

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

    def _numeric_field(
        self,
        *,
        object_name: str,
        placeholder: str,
        validator: QRegularExpressionValidator,
    ) -> QLineEdit:
        field = QLineEdit(self)
        field.setObjectName(object_name)
        field.setPlaceholderText(placeholder)
        field.setValidator(validator)
        field.textChanged.connect(self._sync_validation_message)
        field.textChanged.connect(self._sync_preset_selection_for_current_style)
        return field

    def _gradient_row(
        self,
        *,
        mode_key: str,
        color_key: str,
        direction_key: str,
        color_label: str,
    ) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        mode = QComboBox(row)
        mode.setObjectName(f"{mode_key}_mode_value")
        mode.addItem("Inherit", "inherit")
        mode.addItem("Custom", "custom")
        mode.addItem("Off", "off")
        mode.currentIndexChanged.connect(
            lambda _index, current_key=mode_key: self._on_gradient_mode_changed(current_key)
        )
        mode.currentIndexChanged.connect(self._sync_preset_selection_for_current_style)
        self._gradient_mode_combos[mode_key] = mode
        layout.addWidget(mode, stretch=0)

        color = ColorHexFieldControl(row, allow_empty=True, color_dialog_title=f"Pick {color_label}")
        color.setObjectNames(value_name=f"{color_key}_value", swatch_name=f"{color_key}_swatch")
        color.valueChanged.connect(self._sync_validation_message)
        color.valueChanged.connect(self._sync_preset_selection_for_current_style)
        self._gradient_color_fields[color_key] = color
        layout.addWidget(color, stretch=1)

        direction = QComboBox(row)
        direction.setObjectName(f"{direction_key}_value")
        for value in PASSIVE_NODE_STYLE_GRADIENT_DIRECTIONS:
            direction.addItem(value.title(), value)
        direction.currentIndexChanged.connect(self._sync_preset_selection_for_current_style)
        self._gradient_direction_combos[direction_key] = direction
        layout.addWidget(direction, stretch=0)
        return row

    def _append_gradient_payload(
        self,
        payload: dict[str, Any],
        *,
        mode_key: str,
        enabled_key: str,
        color_key: str,
        direction_key: str,
    ) -> None:
        mode = str(self._gradient_mode_combos[mode_key].currentData() or "inherit").strip()
        if mode == "off":
            payload[enabled_key] = False
            return
        if mode != "custom":
            return
        payload[enabled_key] = True
        color_value = self._gradient_color_fields[color_key].text().strip()
        if color_value:
            payload[color_key] = color_value
        payload[direction_key] = str(
            self._gradient_direction_combos[direction_key].currentData()
            or DEFAULT_PASSIVE_NODE_STYLE_GRADIENT_DIRECTION
        )

    def _load_gradient_style(
        self,
        normalized: dict[str, Any],
        *,
        mode_key: str,
        enabled_key: str,
        color_key: str,
        direction_key: str,
    ) -> None:
        mode_combo = self._gradient_mode_combos[mode_key]
        color_field = self._gradient_color_fields[color_key]
        direction_combo = self._gradient_direction_combos[direction_key]
        enabled = normalized.get(enabled_key)
        if enabled is True:
            mode = "custom"
        elif enabled is False:
            mode = "off"
        elif normalized.get(color_key):
            mode = "custom"
        else:
            mode = "inherit"
        mode_combo.setCurrentIndex(max(0, mode_combo.findData(mode)))
        color_field.setText(normalized.get(color_key, ""))
        direction = str(normalized.get(direction_key, DEFAULT_PASSIVE_NODE_STYLE_GRADIENT_DIRECTION)).strip().lower()
        direction_combo.setCurrentIndex(max(0, direction_combo.findData(direction)))
        self._sync_gradient_row_enabled(mode_key)

    def _on_gradient_mode_changed(self, mode_key: str) -> None:
        self._sync_gradient_row_enabled(mode_key)
        self._sync_validation_message()

    def _sync_gradient_row_enabled(self, mode_key: str) -> None:
        custom = str(self._gradient_mode_combos[mode_key].currentData() or "") == "custom"
        self._gradient_color_fields["gradient_color"].setEnabled(custom)
        self._gradient_direction_combos["gradient_direction"].setEnabled(custom)

    def _validate_gradient_fields(self) -> bool:
        invalid = False
        field = self._gradient_color_fields["gradient_color"]
        custom = str(self._gradient_mode_combos["gradient"].currentData() or "") == "custom"
        if custom and (not field.text().strip() or not field.is_valid()):
            field.mark_invalid()
            invalid = True
        else:
            field.mark_valid()
        return invalid

    def _has_invalid_gradient_fields(self) -> bool:
        field = self._gradient_color_fields["gradient_color"]
        custom = str(self._gradient_mode_combos["gradient"].currentData() or "") == "custom"
        return custom and (not field.text().strip() or not field.is_valid())

    def _load_style(self, initial_style: Any | None) -> None:
        self._loading_style = True
        normalized = normalize_passive_node_style_payload(initial_style)
        for key, field in self._color_fields.items():
            field.setText(normalized.get(key, ""))
        self._load_gradient_style(
            normalized,
            mode_key="gradient",
            enabled_key="gradient_enabled",
            color_key="gradient_color",
            direction_key="gradient_direction",
        )
        if "border_width" in normalized:
            self._numeric_fields["border_width"].setText(_format_number(normalized["border_width"]))
        if "corner_radius" in normalized:
            self._numeric_fields["corner_radius"].setText(_format_number(normalized["corner_radius"]))
        if "font_size" in normalized:
            self._numeric_fields["font_size"].setText(str(normalized["font_size"]))
        weight = str(normalized.get("font_weight", "")).strip()
        index = max(0, self.font_weight_combo.findData(weight))
        self.font_weight_combo.setCurrentIndex(index)
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

        invalid |= _validate_positive_number_field(self._numeric_fields["border_width"], allow_zero=False)
        invalid |= _validate_positive_number_field(self._numeric_fields["corner_radius"], allow_zero=True)
        invalid |= _validate_int_field(self._numeric_fields["font_size"], allow_zero=False)
        invalid |= self._validate_gradient_fields()

        self.validation_message.setVisible(invalid)
        if invalid:
            QMessageBox.warning(
                self,
                "Invalid Passive Node Style",
                "Passive node styles must use valid hex colors, custom gradients need a color, and numeric values must be positive.",
            )
            return False
        return True

    def _sync_validation_message(self) -> None:
        invalid_colors = any(field.text().strip() and not field.is_valid() for field in self._color_fields.values())
        invalid_gradients = self._has_invalid_gradient_fields()
        invalid_numeric = any(
            (
                key == "font_size" and not _is_valid_int(field.text(), allow_zero=False)
            )
            or (
                key != "font_size"
                and not _is_valid_decimal(field.text(), allow_zero=(key == "corner_radius"))
            )
            for key, field in self._numeric_fields.items()
            if field.text().strip()
        )
        self.validation_message.setVisible(invalid_colors or invalid_gradients or invalid_numeric)

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
        name, accepted = QInputDialog.getText(self, "Save Node Preset", "Preset name:")
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
            "Rename Node Preset",
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
            "Delete Node Preset",
            f"Delete preset '{preset['name']}' from this project?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        if self._preset_catalog.delete(str(preset.get("preset_id", ""))):
            self._rebuild_preset_combo()

    def _validated_style_payload(self) -> dict[str, Any] | None:
        if not self._validate():
            return None
        return self.node_style()

    def _sync_preset_selection_for_current_style(self) -> None:
        if self._loading_style:
            return
        matching_preset_id = self._preset_catalog.matching_preset_id(self.node_style())
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


def _is_valid_decimal(value: str, *, allow_zero: bool) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return True
    try:
        numeric = float(normalized)
    except ValueError:
        return False
    return numeric >= 0.0 if allow_zero else numeric > 0.0


def _is_valid_int(value: str, *, allow_zero: bool) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return True
    try:
        numeric = int(normalized)
    except ValueError:
        return False
    return numeric >= 0 if allow_zero else numeric > 0


def _validate_positive_number_field(field: QLineEdit, *, allow_zero: bool) -> bool:
    if _is_valid_decimal(field.text(), allow_zero=allow_zero):
        set_dialog_role(field, None)
        return False
    set_dialog_role(field, "error")
    return True


def _validate_int_field(field: QLineEdit, *, allow_zero: bool) -> bool:
    if _is_valid_int(field.text(), allow_zero=allow_zero):
        set_dialog_role(field, None)
        return False
    set_dialog_role(field, "error")
    return True


__all__ = ["PassiveNodeStyleDialog"]
