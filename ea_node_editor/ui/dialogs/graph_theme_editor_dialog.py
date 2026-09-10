from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ea_node_editor.ui.dialogs.passive_style_controls import (
    ColorHexFieldControl,
    is_valid_hex_color,
    set_dialog_role,
    swatch_style,
)
from ea_node_editor.ui.graph_theme import (
    DEFAULT_GRAPH_THEME_ID,
    GRAPH_NODE_GRADIENT_DIRECTIONS,
    create_blank_custom_graph_theme,
    duplicate_graph_theme_as_custom,
    resolve_graph_theme,
    resolve_graph_theme_id,
    serialize_custom_graph_themes,
)
from ea_node_editor.ui.dialogs.graph_theme_editor_support import (
    CollapsibleSection,
    build_theme_tree_items,
    custom_theme_index,
    h_separator,
    is_active_explicit_custom_theme,
    resolve_preview_metadata,
    resolve_theme_action_state,
    resolve_theme_ids_after_delete,
    token_label,
    update_custom_theme_token,
    validate_custom_theme_tokens,
)
from ea_node_editor.ui.shell.controllers.app_preferences_controller import normalize_graph_theme_settings
from ea_node_editor.ui.shell.tooltip_policy import TOOLTIP_CATEGORY_GENERAL
from ea_node_editor.ui.tooltips import tooltip_text

# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------


class GraphThemeEditorDialog(QDialog):
    _THEME_ID_ROLE = Qt.ItemDataRole.UserRole
    _TOKEN_SECTIONS = (
        ("node_tokens", "Passive Node Defaults"),
        ("edge_tokens", "Edge Tokens"),
        ("port_kind_tokens", "Port Kind Tokens"),
        ("port_state_tokens", "Port State Tokens"),
    )
    _NODE_GRADIENT_ROWS = {
        "card_gradient_enabled": (
            "Body Gradient",
            "card_gradient_enabled",
            "card_gradient_color",
            "card_gradient_direction",
        ),
    }
    _NODE_GRADIENT_BUILD_SKIP_TOKENS = {
        "card_gradient_color",
        "card_gradient_direction",
    }

    def __init__(
        self,
        initial_settings: Any | None = None,
        parent=None,
        *,
        live_apply_callback: Callable[[dict[str, Any]], None] | None = None,
        tooltips_enabled: bool | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Graph Theme Manager")
        self.setModal(True)
        self.resize(1040, 720)

        normalized = normalize_graph_theme_settings(initial_settings)
        self._follow_shell_theme = bool(normalized["follow_shell_theme"])
        self._custom_graph_themes = serialize_custom_graph_themes(normalized["custom_themes"])
        self._explicit_theme_id = resolve_graph_theme_id(
            normalized["selected_theme_id"],
            custom_themes=self._custom_graph_themes,
        )
        self._preview_theme_id = self._explicit_theme_id
        self._live_apply_callback = live_apply_callback
        self._tooltips_enabled = self._resolve_tooltips_enabled(
            explicit_value=tooltips_enabled,
            parent=parent,
        )
        self._use_selected_requested = False
        self._theme_items: dict[str, QTreeWidgetItem] = {}
        self._token_value_fields: dict[str, dict[str, QLineEdit]] = {}
        self._token_swatch_frames: dict[str, dict[str, QFrame]] = {}
        self._gradient_enabled_fields: dict[str, QCheckBox] = {}
        self._gradient_direction_fields: dict[str, QComboBox] = {}
        self._suppress_token_sync = False
        self._collapsed_sections: dict[str, bool] = {}
        self._collapsible_sections: dict[str, CollapsibleSection] = {}

        self._build_ui()
        self._rebuild_theme_tree(selected_theme_id=self._preview_theme_id)

    @property
    def use_selected_requested(self) -> bool:
        return self._use_selected_requested

    @property
    def theme_name_field(self) -> QLabel:
        """Backward-compatible accessor (tests)."""
        return self._top_bar_name

    @property
    def theme_id_field(self) -> QLabel:
        """Backward-compatible accessor (tests)."""
        return self._top_bar_id

    @property
    def theme_mode_field(self) -> QLabel:
        """Backward-compatible accessor (tests)."""
        return self._top_bar_status

    def reject(self) -> None:
        self._accept_without_using_selected()

    def graph_theme_settings(self) -> dict[str, Any]:
        custom_themes = serialize_custom_graph_themes(self._custom_graph_themes)
        selected_theme_id = resolve_graph_theme_id(self._explicit_theme_id, custom_themes=custom_themes)
        return normalize_graph_theme_settings(
            {
                "follow_shell_theme": self._follow_shell_theme,
                "selected_theme_id": selected_theme_id,
                "custom_themes": copy.deepcopy(custom_themes),
            }
        )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        # --- Top bar ---
        top_bar = self._build_top_bar()
        root.addWidget(top_bar)

        sep1 = h_separator()
        root.addWidget(sep1)

        # --- Splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._build_library_panel())
        splitter.addWidget(self._build_preview_panel())
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        sep2 = h_separator()
        root.addWidget(sep2)

        # --- Bottom bar ---
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 8, 0, 0)

        self.close_button = QPushButton("Close", self)
        self.close_button.clicked.connect(self._accept_without_using_selected)
        bottom_bar.addWidget(self.close_button)

        bottom_bar.addStretch(1)

        self.use_selected_button = QPushButton("Use Selected", self)
        self.use_selected_button.setObjectName("primaryButton")
        self.use_selected_button.setToolTip(
            tooltip_text("settings.graph_theme.use_selected") if self._tooltips_enabled else ""
        )
        self.use_selected_button.clicked.connect(self._use_selected_theme)
        bottom_bar.addWidget(self.use_selected_button)
        root.addLayout(bottom_bar)

    def _build_top_bar(self) -> QWidget:
        bar = QWidget(self)
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        self._top_bar_name = QLabel(bar)
        name_font = self._top_bar_name.font()
        name_font.setPointSize(11)
        name_font.setBold(True)
        self._top_bar_name.setFont(name_font)
        layout.addWidget(self._top_bar_name)

        self._top_bar_id = QLabel(bar)
        self._top_bar_id.setProperty("dialogRole", "muted")
        self._top_bar_id.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._top_bar_id)

        layout.addStretch(1)

        self._top_bar_status = QLabel(bar)
        self._top_bar_status.setProperty("dialogRole", "muted")
        self._top_bar_status.setStyleSheet(
            "padding: 2px 10px;"
            "border-radius: 10px;"
            "font-size: 11px;"
        )
        layout.addWidget(self._top_bar_status)

        return bar

    def _build_library_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setMinimumWidth(240)
        panel.setMaximumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 8, 0)
        layout.setSpacing(8)

        title = QLabel("Themes", panel)
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.theme_tree = QTreeWidget(panel)
        self.theme_tree.setHeaderHidden(True)
        self.theme_tree.setIndentation(16)
        self.theme_tree.setAlternatingRowColors(False)
        self.theme_tree.setRootIsDecorated(True)
        self.theme_tree.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self.theme_tree, stretch=1)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self.new_button = QPushButton("+ New", panel)
        self.duplicate_button = QPushButton("Duplicate", panel)
        row1.addWidget(self.new_button)
        row1.addWidget(self.duplicate_button)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.rename_button = QPushButton("Rename", panel)
        self.delete_button = QPushButton("Delete", panel)
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setProperty("dialogRole", "danger")
        row2.addWidget(self.rename_button)
        row2.addWidget(self.delete_button)
        layout.addLayout(row2)

        self.new_button.clicked.connect(self._create_theme)
        self.duplicate_button.clicked.connect(self._duplicate_selected_theme)
        self.rename_button.clicked.connect(self._rename_selected_theme)
        self.delete_button.clicked.connect(self._delete_selected_theme)

        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 0, 0)
        layout.setSpacing(6)

        self.preview_note = QLabel(panel)
        self.preview_note.setWordWrap(True)
        self.preview_note.setProperty("dialogRole", "muted")
        self.preview_note.setStyleSheet("font-size: 11px; padding: 2px 0;")
        layout.addWidget(self.preview_note)

        self.validation_message = QLabel("Fix invalid colors before closing. Use #RRGGBB or #AARRGGBB.", panel)
        self.validation_message.setWordWrap(True)
        self.validation_message.setProperty("dialogRole", "error")
        self.validation_message.hide()
        layout.addWidget(self.validation_message)

        preview_scroll = QScrollArea(panel)
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        preview_content = QWidget(preview_scroll)
        preview_layout = QVBoxLayout(preview_content)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(4)

        reference_theme = resolve_graph_theme(DEFAULT_GRAPH_THEME_ID)
        for section_name, section_title in self._TOKEN_SECTIONS:
            section_mapping = getattr(reference_theme, section_name).as_dict()
            token_count = len(section_mapping)

            initially_expanded = self._collapsed_sections.get(section_name, True)
            collapsible = CollapsibleSection(
                section_title, token_count, preview_content, initially_expanded=initially_expanded
            )
            self._collapsible_sections[section_name] = collapsible

            form = QFormLayout()
            form.setContentsMargins(8, 4, 8, 4)
            form.setSpacing(6)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            value_fields: dict[str, QLineEdit] = {}
            swatch_frames: dict[str, QFrame] = {}
            for token_name in section_mapping:
                if section_name == "node_tokens" and token_name in self._NODE_GRADIENT_ROWS:
                    (
                        label,
                        enabled_token,
                        color_token,
                        direction_token,
                    ) = self._NODE_GRADIENT_ROWS[token_name]
                    control, color_line_edit, color_swatch = self._build_gradient_token_control(
                        collapsible.content_widget,
                        section_name=section_name,
                        enabled_token=enabled_token,
                        color_token=color_token,
                        direction_token=direction_token,
                    )
                    form.addRow(label, control)
                    value_fields[color_token] = color_line_edit
                    swatch_frames[color_token] = color_swatch
                    continue
                if section_name == "node_tokens" and token_name in self._NODE_GRADIENT_BUILD_SKIP_TOKENS:
                    continue
                control = ColorHexFieldControl(
                    collapsible.content_widget,
                    allow_empty=False,
                    color_dialog_title=f"Pick color for {token_label(token_name)}",
                )
                control.setBeforeColorApply(self._ensure_preview_theme_editable)
                control.setObjectNames(
                    value_name=f"{section_name}_{token_name}_value",
                    swatch_name=f"{section_name}_{token_name}_swatch",
                )
                control.valueChanged.connect(
                    lambda text, current_section=section_name, current_token=token_name: self._on_token_text_changed(
                        current_section,
                        current_token,
                        text,
                    )
                )
                form.addRow(token_label(token_name), control)

                value_fields[token_name] = control.line_edit
                swatch_frames[token_name] = control.swatch

            self._token_value_fields[section_name] = value_fields
            self._token_swatch_frames[section_name] = swatch_frames
            collapsible.content_widget.layout().addLayout(form)
            preview_layout.addWidget(collapsible)

        preview_layout.addStretch(1)
        preview_scroll.setWidget(preview_content)
        layout.addWidget(preview_scroll, stretch=1)
        return panel

    def _build_gradient_token_control(
        self,
        parent: QWidget,
        *,
        section_name: str,
        enabled_token: str,
        color_token: str,
        direction_token: str,
    ) -> tuple[QWidget, QLineEdit, QFrame]:
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        enabled = QCheckBox("Gradient", row)
        enabled.setObjectName(f"{section_name}_{enabled_token}_value")
        enabled.stateChanged.connect(
            lambda _state, current_section=section_name, current_token=enabled_token, checkbox=enabled: (
                self._on_gradient_enabled_changed(current_section, current_token, checkbox.isChecked())
            )
        )
        self._gradient_enabled_fields[enabled_token] = enabled
        layout.addWidget(enabled, stretch=0)

        color = ColorHexFieldControl(
            row,
            allow_empty=False,
            color_dialog_title=f"Pick color for {token_label(color_token)}",
        )
        color.setBeforeColorApply(self._ensure_preview_theme_editable)
        color.setObjectNames(
            value_name=f"{section_name}_{color_token}_value",
            swatch_name=f"{section_name}_{color_token}_swatch",
        )
        color.valueChanged.connect(
            lambda text, current_section=section_name, current_token=color_token: self._on_token_text_changed(
                current_section,
                current_token,
                text,
            )
        )
        layout.addWidget(color, stretch=1)

        direction = QComboBox(row)
        direction.setObjectName(f"{section_name}_{direction_token}_value")
        for value in GRAPH_NODE_GRADIENT_DIRECTIONS:
            direction.addItem(value.title(), value)
        direction.currentIndexChanged.connect(
            lambda _index, current_section=section_name, current_token=direction_token, combo=direction: (
                self._on_gradient_direction_changed(current_section, current_token, combo.currentData())
            )
        )
        self._gradient_direction_fields[direction_token] = direction
        layout.addWidget(direction, stretch=0)

        return row, color.line_edit, color.swatch

    # ------------------------------------------------------------------
    # Theme tree
    # ------------------------------------------------------------------

    def _rebuild_theme_tree(self, *, selected_theme_id: object | None = None) -> None:
        selection = resolve_graph_theme_id(
            selected_theme_id if selected_theme_id is not None else self._preview_theme_id,
            custom_themes=self._custom_graph_themes,
        )

        self.theme_tree.blockSignals(True)
        self.theme_tree.clear()
        tree_roots, self._theme_items = build_theme_tree_items(
            custom_graph_themes=self._custom_graph_themes,
            explicit_theme_id=self._explicit_theme_id,
            theme_id_role=self._THEME_ID_ROLE,
        )
        for root_item in tree_roots:
            self.theme_tree.addTopLevelItem(root_item)
        self.theme_tree.blockSignals(False)

        self._select_theme_item(selection)

    def _select_theme_item(self, theme_id: object) -> None:
        resolved_theme_id = resolve_graph_theme_id(theme_id, custom_themes=self._custom_graph_themes)
        item = self._theme_items.get(resolved_theme_id)
        if item is None and self._theme_items:
            item = next(iter(self._theme_items.values()))
        if item is None:
            self._sync_preview()
            return
        self.theme_tree.setCurrentItem(item)
        self._preview_theme_id = str(item.data(0, self._THEME_ID_ROLE) or resolved_theme_id)
        self._sync_preview()

    def _on_current_item_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        theme_id = self._theme_id_from_item(current)
        if theme_id is not None:
            self._preview_theme_id = theme_id
        self._sync_preview()

    # ------------------------------------------------------------------
    # Preview sync
    # ------------------------------------------------------------------

    def _sync_preview(self) -> None:
        preview_metadata = resolve_preview_metadata(
            preview_theme_id=self._preview_theme_id,
            explicit_theme_id=self._explicit_theme_id,
            custom_graph_themes=self._custom_graph_themes,
            follow_shell_theme=self._follow_shell_theme,
        )
        theme = preview_metadata.theme
        is_custom = preview_metadata.is_custom

        # Top bar
        self._top_bar_name.setText(theme.label)
        self._top_bar_id.setText(theme.theme_id)
        self._top_bar_status.setText(preview_metadata.status_text)

        # Context note
        self.preview_note.setText(preview_metadata.preview_note)

        # Token fields
        self._suppress_token_sync = True
        try:
            for section_name, _section_title in self._TOKEN_SECTIONS:
                tokens = getattr(theme, section_name).as_dict()
                for token_name, token_value in tokens.items():
                    if section_name == "node_tokens" and token_name in self._gradient_enabled_fields:
                        checkbox = self._gradient_enabled_fields[token_name]
                        checkbox.setEnabled(is_custom)
                        checkbox.setChecked(bool(token_value))
                        continue
                    if section_name == "node_tokens" and token_name in self._gradient_direction_fields:
                        combo = self._gradient_direction_fields[token_name]
                        combo.setEnabled(is_custom)
                        index = combo.findData(str(token_value).strip().lower())
                        combo.setCurrentIndex(max(0, index))
                        continue
                    if section_name == "node_tokens" and token_name.endswith("_gradient_direction"):
                        continue
                    field = self._token_value_fields[section_name][token_name]
                    field.setReadOnly(not is_custom)
                    set_dialog_role(field, None)
                    field.setText(token_value)

                    swatch = self._token_swatch_frames[section_name][token_name]
                    if hasattr(swatch, "editable"):
                        swatch.editable = True
                    self._set_token_swatch(section_name, token_name, token_value)
        finally:
            self._suppress_token_sync = False

        self.validation_message.setVisible(False)

        action_state = resolve_theme_action_state(theme_id=theme.theme_id, is_custom=is_custom)
        self.duplicate_button.setEnabled(action_state.duplicate_enabled)
        self.use_selected_button.setEnabled(action_state.use_selected_enabled)
        self.rename_button.setEnabled(action_state.rename_enabled)
        self.delete_button.setEnabled(action_state.delete_enabled)

    # ------------------------------------------------------------------
    # Theme CRUD
    # ------------------------------------------------------------------

    def _create_theme(self) -> None:
        created_theme = create_blank_custom_graph_theme(custom_themes=self._custom_graph_themes)
        self._custom_graph_themes.append(created_theme.as_dict())
        self._rebuild_theme_tree(selected_theme_id=created_theme.theme_id)

    def _duplicate_selected_theme(self) -> None:
        source_theme_id = self._preview_theme_id
        created_theme = duplicate_graph_theme_as_custom(source_theme_id, custom_themes=self._custom_graph_themes)
        self._custom_graph_themes.append(created_theme.as_dict())
        self._rebuild_theme_tree(selected_theme_id=created_theme.theme_id)

    def _rename_selected_theme(self) -> None:
        theme_id = self._preview_theme_id
        index = custom_theme_index(self._custom_graph_themes, theme_id)
        if index < 0:
            return
        current_label = str(self._custom_graph_themes[index].get("label", "")).strip()
        label, accepted = QInputDialog.getText(
            self,
            "Rename Graph Theme",
            "Theme name:",
            text=current_label,
        )
        if not accepted:
            return
        normalized_label = str(label).strip()
        if not normalized_label:
            return
        self._custom_graph_themes[index]["label"] = normalized_label
        self._rebuild_theme_tree(selected_theme_id=theme_id)
        self._maybe_live_apply(theme_id)

    def _delete_selected_theme(self) -> None:
        theme_id = self._preview_theme_id
        index = custom_theme_index(self._custom_graph_themes, theme_id)
        if index < 0:
            return
        label = str(self._custom_graph_themes[index].get("label", theme_id)).strip() or str(theme_id)
        choice = QMessageBox.question(
            self,
            "Delete Graph Theme",
            f"Delete the custom graph theme '{label}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        del self._custom_graph_themes[index]
        self._preview_theme_id, self._explicit_theme_id = resolve_theme_ids_after_delete(
            theme_id=theme_id,
            explicit_theme_id=self._explicit_theme_id,
            custom_graph_themes=self._custom_graph_themes,
        )
        self._rebuild_theme_tree(selected_theme_id=self._preview_theme_id)

    def _use_selected_theme(self) -> None:
        if not self._validate_current_theme_before_save():
            return
        self._use_selected_requested = True
        self._follow_shell_theme = False
        self._explicit_theme_id = resolve_graph_theme_id(self._preview_theme_id, custom_themes=self._custom_graph_themes)
        self.accept()

    def _accept_without_using_selected(self) -> None:
        if not self._validate_current_theme_before_save():
            return
        self._use_selected_requested = False
        self.accept()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_current_theme_before_save(self) -> bool:
        validation = validate_custom_theme_tokens(
            preview_theme_id=self._preview_theme_id,
            custom_graph_themes=self._custom_graph_themes,
            token_values_by_section=self._token_field_values(),
        )
        if validation.is_valid:
            self.validation_message.setVisible(False)
            return True
        self.validation_message.setVisible(True)
        section_name = validation.invalid_section_name
        token_name = validation.invalid_token_name
        field = self._token_value_fields[section_name][token_name]
        set_dialog_role(field, "error")
        set_dialog_role(self._token_swatch_frames[section_name][token_name], "error")
        QMessageBox.warning(
            self,
            "Invalid Graph Theme Color",
            "Custom theme colors must use #RRGGBB or #AARRGGBB before the theme can be saved.",
        )
        field.setFocus(Qt.FocusReason.OtherFocusReason)
        return False

    # ------------------------------------------------------------------
    # Token editing
    # ------------------------------------------------------------------

    def _on_token_text_changed(self, section_name: str, token_name: str, text: str) -> None:
        if self._suppress_token_sync:
            return
        theme_id = self._preview_theme_id
        theme_index = custom_theme_index(self._custom_graph_themes, theme_id)
        if theme_index < 0:
            return

        field = self._token_value_fields[section_name][token_name]
        swatch = self._token_swatch_frames[section_name][token_name]
        normalized = str(text).strip()
        if not is_valid_hex_color(normalized):
            set_dialog_role(field, "error")
            set_dialog_role(swatch, "error")
            swatch.setStyleSheet(swatch_style(normalized))
            self._sync_validation_message()
            return

        set_dialog_role(field, None)
        set_dialog_role(swatch, None)
        update_custom_theme_token(
            custom_graph_themes=self._custom_graph_themes,
            theme_id=theme_id,
            section_name=section_name,
            token_name=token_name,
            token_value=normalized,
        )
        swatch.setStyleSheet(swatch_style(normalized))
        self._sync_validation_message()
        self._maybe_live_apply(theme_id)

    def _on_gradient_enabled_changed(self, section_name: str, token_name: str, checked: bool) -> None:
        if self._suppress_token_sync:
            return
        theme_id = self._preview_theme_id
        theme_index = custom_theme_index(self._custom_graph_themes, theme_id)
        if theme_index < 0:
            return
        update_custom_theme_token(
            custom_graph_themes=self._custom_graph_themes,
            theme_id=theme_id,
            section_name=section_name,
            token_name=token_name,
            token_value=bool(checked),
        )
        self._sync_validation_message()
        self._maybe_live_apply(theme_id)

    def _on_gradient_direction_changed(self, section_name: str, token_name: str, value: object) -> None:
        if self._suppress_token_sync:
            return
        theme_id = self._preview_theme_id
        theme_index = custom_theme_index(self._custom_graph_themes, theme_id)
        if theme_index < 0:
            return
        normalized = str(value or "").strip().lower()
        if normalized not in GRAPH_NODE_GRADIENT_DIRECTIONS:
            return
        update_custom_theme_token(
            custom_graph_themes=self._custom_graph_themes,
            theme_id=theme_id,
            section_name=section_name,
            token_name=token_name,
            token_value=normalized,
        )
        self._sync_validation_message()
        self._maybe_live_apply(theme_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _maybe_live_apply(self, theme_id: object) -> None:
        if self._live_apply_callback is None:
            return
        if not self._is_active_explicit_custom_theme(theme_id):
            return
        self._live_apply_callback(self.graph_theme_settings())

    def _is_active_explicit_custom_theme(self, theme_id: object) -> bool:
        return is_active_explicit_custom_theme(
            theme_id=theme_id,
            explicit_theme_id=self._explicit_theme_id,
            custom_graph_themes=self._custom_graph_themes,
            follow_shell_theme=self._follow_shell_theme,
        )

    def _ensure_preview_theme_editable(self, _selected_color: str) -> bool:
        theme_id = resolve_graph_theme_id(self._preview_theme_id, custom_themes=self._custom_graph_themes)
        if custom_theme_index(self._custom_graph_themes, theme_id) >= 0:
            return True
        created_theme = duplicate_graph_theme_as_custom(theme_id, custom_themes=self._custom_graph_themes)
        self._custom_graph_themes.append(created_theme.as_dict())
        self._rebuild_theme_tree(selected_theme_id=created_theme.theme_id)
        return True

    def _set_token_swatch(self, section_name: str, token_name: str, token_value: str) -> None:
        swatch = self._token_swatch_frames[section_name][token_name]
        set_dialog_role(swatch, None)
        swatch.setStyleSheet(swatch_style(token_value))

    def _token_field_values(self) -> dict[str, dict[str, str]]:
        return {
            section_name: {
                token_name: field.text().strip()
                for token_name, field in fields.items()
            }
            for section_name, fields in self._token_value_fields.items()
        }

    def _sync_validation_message(self) -> None:
        validation = validate_custom_theme_tokens(
            preview_theme_id=self._preview_theme_id,
            custom_graph_themes=self._custom_graph_themes,
            token_values_by_section=self._token_field_values(),
        )
        self.validation_message.setVisible(not validation.is_valid)

    def _theme_id_from_item(self, item: QTreeWidgetItem | None) -> str | None:
        if item is None:
            return None
        theme_id = item.data(0, self._THEME_ID_ROLE)
        if theme_id is None:
            return None
        normalized = str(theme_id).strip()
        return normalized or None

    def _resolve_tooltips_enabled(
        self,
        *,
        explicit_value: bool | None,
        parent: object | None,
    ) -> bool:
        if explicit_value is not None:
            return bool(explicit_value)
        tooltip_manager = getattr(parent, "tooltip_manager", None)
        if tooltip_manager is not None:
            category_enabled = getattr(tooltip_manager, "category_tooltips_enabled", None)
            if callable(category_enabled):
                return bool(category_enabled(TOOLTIP_CATEGORY_GENERAL))
        parent_value = getattr(parent, "graphics_show_tooltips", None)
        if parent_value is not None:
            return bool(parent_value)
        return True

__all__ = ["GraphThemeEditorDialog"]
