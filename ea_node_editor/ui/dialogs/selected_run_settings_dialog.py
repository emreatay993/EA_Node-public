from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ea_node_editor.app_preferences import normalize_selected_run_settings


class SelectedRunSettingsDialog(QDialog):
    def __init__(
        self,
        initial_settings: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Run Settings")
        self.setModal(True)
        self.resize(420, 180)

        settings = normalize_selected_run_settings(initial_settings or {})

        self.header_label = QLabel("Selected run behavior", self)
        self.header_label.setObjectName("selectedRunSettingsHeader")

        self.preview_before_run_check = QCheckBox("Show preview before selected runs", self)
        self.preview_before_run_check.setObjectName("selectedRunSettingsPreviewBeforeRunCheck")
        self.preview_before_run_check.setChecked(bool(settings.get("preview_before_run", True)))

        self.preview_detail_label = QLabel(
            "Review the selected run targets before execution.",
            self,
        )
        self.preview_detail_label.setWordWrap(True)
        self.preview_detail_label.setObjectName("selectedRunSettingsPreviewDetail")

        self.cancel_button = QPushButton("Cancel", self)
        self.ok_button = QPushButton("OK", self)
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button.clicked.connect(self.accept)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.ok_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(self.header_label)
        layout.addWidget(self.preview_before_run_check)
        layout.addWidget(self.preview_detail_label)
        layout.addStretch(1)
        layout.addLayout(actions)

    def values(self) -> dict[str, Any]:
        return normalize_selected_run_settings(
            {"preview_before_run": self.preview_before_run_check.isChecked()}
        )

    def selected_run_preview_before_run(self) -> bool:
        return bool(self.values()["preview_before_run"])
