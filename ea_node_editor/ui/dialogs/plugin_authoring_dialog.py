# Purpose: Present the native novice plugin editor and validation diagnostics.
# Map: subsystems/pyqt_dialogs_panels_theme_editor.md
# Tests: tests/test_plugin_authoring_dialog.py

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut, QTextCursor
from PyQt6.QtWidgets import (
    QDialog,
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

from ea_node_editor.ui.editor.code_editor import PythonCodeEditor

if TYPE_CHECKING:
    from ea_node_editor.nodes.plugin_authoring import PluginIdentity, PluginValidationReport


@dataclass(frozen=True, slots=True)
class PluginAuthoringDraft:
    visible_name: str
    filename: str
    function_name: str
    node_id: str
    source: str


class PluginAuthoringDialog(QDialog):
    save_requested = pyqtSignal()
    validate_requested = pyqtSignal()
    reload_requested = pyqtSignal()
    open_plugins_folder_requested = pyqtSignal()

    _DIAGNOSTIC_COLUMNS = (
        "File",
        "Line",
        "Column",
        "Severity",
        "Node ID",
        "Digest",
        "Availability",
        "Message",
    )

    def __init__(
        self,
        *,
        identity: PluginIdentity,
        source: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Plugin")
        self.setModal(True)
        self.resize(1040, 760)
        self._function_name = identity.function_name
        self._last_saved_source = str(source)

        self.visible_name_edit = QLineEdit(identity.visible_name, self)
        self.visible_name_edit.setObjectName("pluginAuthoringVisibleNameEdit")
        self.filename_edit = QLineEdit(identity.filename, self)
        self.filename_edit.setObjectName("pluginAuthoringFilenameEdit")
        self.node_id_edit = QLineEdit(identity.node_id, self)
        self.node_id_edit.setObjectName("pluginAuthoringNodeIdEdit")
        self.node_id_edit.setReadOnly(True)

        identity_form = QFormLayout()
        identity_form.addRow("Visible name", self.visible_name_edit)
        identity_form.addRow("Filename", self.filename_edit)
        identity_form.addRow("Node ID", self.node_id_edit)

        self.editor = PythonCodeEditor(self)
        self.editor.setObjectName("pluginAuthoringEditor")
        self.editor.setPlainText(source)
        self.editor.textChanged.connect(self._sync_dirty_state)

        self.diagnostics_tree = QTreeWidget(self)
        self.diagnostics_tree.setObjectName("pluginAuthoringDiagnosticsTree")
        self.diagnostics_tree.setHeaderLabels(list(self._DIAGNOSTIC_COLUMNS))
        self.diagnostics_tree.setAlternatingRowColors(True)
        self.diagnostics_tree.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self.diagnostics_tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.diagnostics_tree.itemClicked.connect(self._focus_diagnostic_item)
        self.diagnostics_tree.itemActivated.connect(self._focus_diagnostic_item)

        self.summary_label = QLabel("Not validated.", self)
        self.summary_label.setObjectName("pluginAuthoringSummaryLabel")
        self.summary_label.setWordWrap(True)
        self.status_label = QLabel("", self)
        self.status_label.setObjectName("pluginAuthoringStatusLabel")
        self.status_label.setWordWrap(True)
        self.reload_status_label = QLabel("", self)
        self.reload_status_label.setObjectName("pluginAuthoringReloadStatusLabel")

        self.save_button = self._action_button("Save", "pluginAuthoringSaveButton")
        self.validate_button = self._action_button("Validate", "pluginAuthoringValidateButton")
        self.reload_button = self._action_button("Reload", "pluginAuthoringReloadButton")
        self.open_plugins_folder_button = self._action_button(
            "Open Plugins Folder",
            "pluginAuthoringOpenPluginsFolderButton",
        )
        self.close_button = self._action_button("Close", "pluginAuthoringCloseButton")
        self.save_button.clicked.connect(self.save_requested)
        self.validate_button.clicked.connect(self.validate_requested)
        self.reload_button.clicked.connect(self.reload_requested)
        self.open_plugins_folder_button.clicked.connect(self.open_plugins_folder_requested)
        self.close_button.clicked.connect(self.close)

        action_row = QHBoxLayout()
        action_row.addWidget(self.save_button)
        action_row.addWidget(self.validate_button)
        action_row.addWidget(self.reload_button)
        action_row.addWidget(self.open_plugins_folder_button)
        action_row.addStretch(1)
        action_row.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addLayout(identity_form)
        layout.addWidget(self.editor, 3)
        layout.addWidget(self.reload_status_label)
        layout.addWidget(self.diagnostics_tree, 2)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.status_label)
        layout.addLayout(action_row)

        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.save_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.save_shortcut.activated.connect(self.save_requested)
        self._sync_dirty_state()

    @property
    def dirty(self) -> bool:
        return self.editor.toPlainText() != self._last_saved_source

    def draft(self) -> PluginAuthoringDraft:
        return PluginAuthoringDraft(
            visible_name=self.visible_name_edit.text().strip(),
            filename=self.filename_edit.text().strip(),
            function_name=self._function_name,
            node_id=self.node_id_edit.text(),
            source=self.editor.toPlainText(),
        )

    def set_report(self, report: PluginValidationReport) -> None:
        self.diagnostics_tree.clear()
        for diagnostic in report.diagnostics:
            availability = (
                "Unavailable"
                if diagnostic.unavailable_reason or diagnostic.severity == "error"
                else "Available"
            )
            item = QTreeWidgetItem(
                [
                    diagnostic.filename,
                    str(diagnostic.line or ""),
                    str(diagnostic.column or ""),
                    diagnostic.severity,
                    diagnostic.node_id,
                    diagnostic.digest,
                    availability,
                    diagnostic.message,
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, diagnostic)
            self.diagnostics_tree.addTopLevelItem(item)
        for column in range(len(self._DIAGNOSTIC_COLUMNS)):
            self.diagnostics_tree.resizeColumnToContents(column)

        summary = report.summary
        if report.success and summary is not None:
            self.summary_label.setText(
                f"Validated {summary.bundle_count} bundle(s), {summary.node_count} node(s); "
                f"digest {summary.plugin_digest}; {summary.unavailable_node_count} unavailable."
            )
            self.status_label.setText("Validation succeeded.")
        else:
            self.summary_label.setText("Validation failed.")
            self.status_label.setText("Validation failed. Fix the diagnostics and try again.")

    def mark_saved(self, source: str | None = None) -> None:
        self._last_saved_source = self.editor.toPlainText() if source is None else str(source)
        self.status_label.setText("Saved.")
        self._sync_dirty_state()

    def mark_current(self) -> None:
        self._last_saved_source = self.editor.toPlainText()
        self.status_label.setText("Plugins are current.")
        self._sync_dirty_state()

    def focus_diagnostic(self, index: int) -> None:
        item = self.diagnostics_tree.topLevelItem(int(index))
        if item is None:
            return
        self.diagnostics_tree.setCurrentItem(item)
        self._focus_diagnostic_item(item, 0)

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        self.editor.setFocus(Qt.FocusReason.OtherFocusReason)

    @staticmethod
    def _action_button(label: str, object_name: str) -> QPushButton:
        button = QPushButton(label)
        button.setObjectName(object_name)
        button.setAutoDefault(False)
        button.setDefault(False)
        return button

    def _sync_dirty_state(self) -> None:
        dirty = self.dirty
        self.reload_button.setEnabled(not dirty)
        self.reload_status_label.setText("Save changes before reloading." if dirty else "")

    def _focus_diagnostic_item(self, item: QTreeWidgetItem, _column: int) -> None:
        diagnostic = item.data(0, Qt.ItemDataRole.UserRole)
        diagnostic_filename = str(getattr(diagnostic, "filename", "") or "").strip()
        draft_filename = self.filename_edit.text().strip()
        if not self._same_filename(diagnostic_filename, draft_filename):
            return
        line = int(getattr(diagnostic, "line", 0) or 0)
        if line <= 0:
            return
        block = self.editor.document().findBlockByNumber(line - 1)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        column = max(1, int(getattr(diagnostic, "column", 1) or 1))
        cursor.setPosition(min(block.position() + column - 1, block.position() + block.length() - 1))
        self.editor.setTextCursor(cursor)
        self.editor.centerCursor()
        self.editor.setFocus(Qt.FocusReason.OtherFocusReason)

    @staticmethod
    def _same_filename(left: str, right: str) -> bool:
        if not left or not right:
            return False
        normalized_left = left.replace("\\", "/")
        normalized_right = right.replace("\\", "/")
        return normalized_left == normalized_right


__all__ = ["PluginAuthoringDialog", "PluginAuthoringDraft"]
