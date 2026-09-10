# Purpose: Choose per-source representations for external canvas imports.
# Map: feature_routes/clipboard_undo_redo_mutation_history.md
# Tests: tests/test_canvas_import_controller.py
from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QScrollArea, QVBoxLayout, QWidget,
)

from ea_node_editor.ui.shell.clipboard_paste_nodes import CanvasImportChoice, CanvasImportSource


class CanvasImportDialog(QDialog):
    def __init__(
        self,
        sources: tuple[CanvasImportSource, ...],
        unavailable_reason: Callable[[CanvasImportChoice], str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add to Canvas")
        self.resize(660, min(660, 180 + 125 * len(sources)))
        self.sources = sources
        self.choice_combos: list[QComboBox] = []
        layout = QVBoxLayout(self)
        bulk = QHBoxLayout()
        bulk.addWidget(QLabel("Set all to"))
        self.bulk_combo = QComboBox()
        self.bulk_combo.setAccessibleName("Set all to")
        self.bulk_combo.addItem("Detected type", "detected")
        common = set.intersection(*(
            {choice.key for choice in source.choices if not unavailable_reason(choice)}
            for source in sources
        )) if sources else set()
        for choice in sources[0].choices if sources else ():
            if choice.key in common and choice.key != "skip":
                self.bulk_combo.addItem(choice.label, choice.key)
        self.bulk_combo.addItem("Skip", "skip")
        bulk.addWidget(self.bulk_combo, 1)
        layout.addLayout(bulk)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        rows = QWidget()
        row_layout = QVBoxLayout(rows)
        for source in sources:
            label = QLabel(source.label)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row_layout.addWidget(label)
            combo = QComboBox()
            combo.setAccessibleName(f"Insert as: {source.label}")
            explanations: list[str] = []
            for choice in source.choices:
                reason = unavailable_reason(choice)
                combo.addItem(choice.label + (" (unavailable)" if reason else ""), choice.key)
                index = combo.count() - 1
                explanation = "\n".join(part for part in (choice.explanation, reason) if part)
                combo.setItemData(index, explanation, Qt.ItemDataRole.ToolTipRole)
                if reason:
                    combo.model().item(index).setEnabled(False)
                explanations.append(explanation)
            combo.setCurrentIndex(combo.findData(source.detected_choice))
            detail = QLabel()
            detail.setTextFormat(Qt.TextFormat.PlainText)
            detail.setWordWrap(True)
            combo.currentIndexChanged.connect(
                lambda index, label=detail, text=explanations: label.setText(text[index])
            )
            detail.setText(explanations[combo.currentIndex()])
            row_layout.addWidget(QLabel("Insert as"))
            row_layout.addWidget(combo)
            row_layout.addWidget(detail)
            self.choice_combos.append(combo)
        row_layout.addStretch()
        scroll.setWidget(rows)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        add_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        add_button.setText("Add to Canvas")
        add_button.setMinimumWidth(add_button.fontMetrics().horizontalAdvance(add_button.text()) + 48)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.bulk_combo.activated.connect(self._set_all)

    def _set_all(self, index: int) -> None:
        key = self.bulk_combo.itemData(index)
        for source, combo in zip(self.sources, self.choice_combos):
            combo.setCurrentIndex(combo.findData(source.detected_choice if key == "detected" else key))

    def selected_keys(self) -> tuple[str, ...]:
        return tuple(str(combo.currentData()) for combo in self.choice_combos)
