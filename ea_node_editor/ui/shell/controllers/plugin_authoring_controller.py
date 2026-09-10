# Purpose: Coordinate novice plugin authoring, validation, save, and atomic reload UI.
# Map: subsystems/ui_shell.md
# Tests: tests/test_plugin_authoring_controller.py

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtWidgets import QMessageBox

from ea_node_editor import platform_open
from ea_node_editor.nodes.plugin_authoring import (
    PluginAuthoringDiagnostic,
    PluginAuthoringSummary,
    PluginValidationReport,
    new_plugin_identity,
    read_saved_plugin_draft,
    render_plugin_template,
    save_plugin_draft,
    summarize_plugin_registry,
    suggest_plugin_filename,
    validate_plugin_draft,
)
from ea_node_editor.runtime_contracts import DataTypeCatalogError
from ea_node_editor.settings import plugins_dir
from ea_node_editor.ui.shell.controllers.dialog_support import resolve_dialog_parent

if TYPE_CHECKING:
    from ea_node_editor.nodes.plugin_authoring import PluginIdentity
    from ea_node_editor.ui.dialogs.plugin_authoring_dialog import PluginAuthoringDialog


_RELOAD_REFUSAL = "Save changes before reloading."
_RELOAD_FAILED = "Plugin reload failed."
_KNOWN_RELOAD_REFUSALS = frozenset(
    {
        "Cannot replace the registry during an active run",
        "Cannot replace the registry while viewer requests or sessions remain active",
        "Cannot replace the registry while viewer routes remain active",
        "Cannot replace the registry while a viewer session is active",
    }
)
logger = logging.getLogger(__name__)


def _bounded_text(value: object, fallback: str) -> str:
    text = " ".join(str(value or "").split()) or fallback
    return text[:600]


class PluginAuthoringController:
    def __init__(self, host: Any) -> None:
        self._host = host
        self._dialog: PluginAuthoringDialog | None = None
        self._identity: PluginIdentity | None = None
        self._generated_source = ""
        self._source_edited = False
        self._filename_edited = False
        self._updating_template = False
        self._saved_path: Path | None = None
        self._saved_source: str | None = None

    @property
    def dialog(self) -> PluginAuthoringDialog | None:
        return self._dialog

    @property
    def saved_path(self) -> Path | None:
        return self._saved_path

    def show_dialog(self) -> PluginAuthoringDialog:
        dialog = self._ensure_dialog()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def save_draft(self) -> bool:
        dialog = self._dialog
        if dialog is None:
            return False
        draft = dialog.draft()
        if self._saved_path is not None and draft.filename != self._saved_path.name:
            dialog.set_report(
                self._error_report(
                    draft.filename,
                    ValueError("Saved plugin filename cannot be changed."),
                )
            )
            return False
        try:
            saved_path = save_plugin_draft(
                draft.source,
                draft.filename,
                expected_source=self._saved_source,
            )
        except (OSError, TypeError, ValueError) as exc:
            dialog.set_report(self._error_report(draft.filename, exc))
            return False
        self._saved_path = saved_path
        self._saved_source = draft.source
        dialog.filename_edit.setReadOnly(True)
        dialog.mark_saved(draft.source)
        dialog.set_report(
            validate_plugin_draft(draft.source, saved_path.name, self._host.registry)
        )
        self._sync_reload_state()
        return True

    def validate_draft(self) -> PluginValidationReport | None:
        dialog = self._dialog
        if dialog is None:
            return None
        draft = dialog.draft()
        report = validate_plugin_draft(
            draft.source,
            draft.filename,
            self._host.registry,
        )
        dialog.set_report(report)
        return report

    def reload_draft(self) -> bool:
        dialog = self._dialog
        if dialog is None:
            return False
        try:
            saved_file_matches = self._draft_matches_saved_file()
        except (OSError, TypeError, ValueError) as exc:
            dialog.set_report(self._error_report(self._saved_filename(), exc))
            self._sync_reload_state()
            dialog.reload_button.setEnabled(False)
            dialog.reload_status_label.setText(_RELOAD_REFUSAL)
            return False
        if not saved_file_matches:
            dialog.set_report(
                self._error_report(
                    self._saved_filename(),
                    ValueError(_RELOAD_REFUSAL),
                )
            )
            self._sync_reload_state()
            dialog.reload_button.setEnabled(False)
            dialog.reload_status_label.setText(_RELOAD_REFUSAL)
            return False
        try:
            result = self._host.registry_replacement_coordinator.reload_plugins()
        except Exception as exc:  # noqa: BLE001
            message = self._reload_failure_message(exc)
            dialog.set_report(
                self._error_report(self._saved_filename(), ValueError(message))
            )
            dialog.reload_status_label.setText(message)
            return False
        if not result.applied:
            report = self._compatibility_report(result.report)
            dialog.set_report(report)
            dialog.reload_status_label.setText("Plugin reload was refused.")
            return False
        dialog.set_report(summarize_plugin_registry(result.registry))
        dialog.mark_current()
        dialog.reload_status_label.setText("")
        return True

    def reload_plugins(self) -> bool:
        try:
            result = self._host.registry_replacement_coordinator.reload_plugins()
        except Exception as exc:  # noqa: BLE001
            message = self._reload_failure_message(exc)
            QMessageBox.warning(
                resolve_dialog_parent(self._host),
                "Reload Plugins Failed",
                message,
            )
            return False
        if not result.applied:
            issues = tuple(getattr(result.report, "issues", ()))[:8]
            details = "\n".join(
                f"- {_bounded_text(getattr(issue, 'message', ''), 'Incompatible plugin change.')}"
                for issue in issues
            )
            QMessageBox.warning(
                resolve_dialog_parent(self._host),
                "Reload Plugins Refused",
                "The plugins are incompatible with the open project."
                + (f"\n\n{details}" if details else ""),
            )
            return False
        report = summarize_plugin_registry(result.registry)
        summary = report.summary
        QMessageBox.information(
            resolve_dialog_parent(self._host),
            "Plugins Reloaded",
            f"Reloaded {summary.bundle_count} bundle(s), {summary.node_count} node(s).\n"
            f"Digest: {summary.plugin_digest}\n"
            f"Unavailable nodes: {summary.unavailable_node_count}.",
        )
        return True

    def open_plugins_folder(self) -> bool:
        try:
            opened = platform_open.open_path_with_default_handler(plugins_dir())
        except Exception:  # noqa: BLE001
            logger.exception("Opening the plugins folder failed")
            opened = False
        if not opened:
            QMessageBox.warning(
                resolve_dialog_parent(self._host),
                "Open Plugins Folder Failed",
                "The plugins folder could not be opened.",
            )
        return opened

    def _ensure_dialog(self) -> PluginAuthoringDialog:
        if self._dialog is not None and self._dialog.isVisible():
            return self._dialog
        if self._dialog is not None:
            self._discard_dialog(self._dialog)
        from ea_node_editor.ui.dialogs.plugin_authoring_dialog import PluginAuthoringDialog

        self._identity = new_plugin_identity("New Plugin")
        self._generated_source = render_plugin_template(self._identity)
        dialog = PluginAuthoringDialog(
            identity=self._identity,
            source=self._generated_source,
            parent=resolve_dialog_parent(self._host),
        )
        dialog.save_requested.connect(self.save_draft)
        dialog.validate_requested.connect(self.validate_draft)
        dialog.reload_requested.connect(self.reload_draft)
        dialog.open_plugins_folder_requested.connect(self.open_plugins_folder)
        dialog.visible_name_edit.textChanged.connect(self._visible_name_changed)
        dialog.editor.textChanged.connect(self._source_changed)
        dialog.filename_edit.textEdited.connect(self._filename_changed_by_user)
        dialog.filename_edit.textChanged.connect(self._sync_reload_state)
        dialog.finished.connect(
            lambda _result, finished_dialog=dialog: self._discard_dialog(
                finished_dialog
            )
        )
        self._dialog = dialog
        self._sync_reload_state()
        return dialog

    def _visible_name_changed(self, visible_name: str) -> None:
        if self._dialog is None:
            return
        if not self._source_edited and self._identity is not None:
            updated = render_plugin_template(self._identity, visible_name=visible_name)
            self._generated_source = updated
            self._updating_template = True
            try:
                self._dialog.editor.setPlainText(updated)
            finally:
                self._updating_template = False
        if not self._filename_edited and not self._dialog.filename_edit.isReadOnly():
            self._dialog.filename_edit.setText(suggest_plugin_filename(visible_name))
        self._sync_reload_state()

    def _source_changed(self) -> None:
        if self._dialog is None:
            return
        if not self._updating_template and self._dialog.editor.toPlainText() != self._generated_source:
            self._source_edited = True
        self._sync_reload_state()

    def _filename_changed_by_user(self, _filename: str) -> None:
        self._filename_edited = True
        self._sync_reload_state()

    def _draft_matches_saved_file(self) -> bool:
        if self._dialog is None or self._saved_path is None or self._saved_source is None:
            return False
        actual_source = read_saved_plugin_draft(self._saved_path)
        draft = self._dialog.draft()
        return (
            actual_source == self._saved_source == draft.source
            and draft.filename == self._saved_path.name
        )

    def _sync_reload_state(self, *_args: object) -> None:
        if self._dialog is None:
            return
        ready = self._draft_matches_cached_save()
        self._dialog.reload_button.setEnabled(ready)
        self._dialog.reload_status_label.setText("" if ready else _RELOAD_REFUSAL)

    def _draft_matches_cached_save(self) -> bool:
        if self._dialog is None or self._saved_path is None or self._saved_source is None:
            return False
        draft = self._dialog.draft()
        return (
            draft.source == self._saved_source
            and draft.filename == self._saved_path.name
        )

    def _discard_dialog(self, dialog: PluginAuthoringDialog) -> None:
        if self._dialog is dialog:
            self._dialog = None
            self._identity = None
            self._generated_source = ""
            self._source_edited = False
            self._filename_edited = False
            self._updating_template = False
            self._saved_path = None
            self._saved_source = None
        dialog.deleteLater()

    @staticmethod
    def _reload_failure_message(error: BaseException) -> str:
        message = str(error)
        if isinstance(error, (RuntimeError, DataTypeCatalogError)) and message in _KNOWN_RELOAD_REFUSALS:
            return message
        logger.exception("Plugin reload failed")
        return _RELOAD_FAILED

    def _saved_filename(self) -> str:
        return self._saved_path.name if self._saved_path is not None else "plugin.py"

    def _compatibility_report(self, report: object) -> PluginValidationReport:
        diagnostics = tuple(
            PluginAuthoringDiagnostic(
                filename=self._saved_filename(),
                line=1,
                column=1,
                severity="error",
                message=_bounded_text(
                    getattr(issue, "message", ""),
                    "Incompatible plugin change.",
                ),
                node_id=str(getattr(issue, "node_id", "") or ""),
            )
            for issue in tuple(getattr(report, "issues", ()))[:64]
        )
        if not diagnostics:
            diagnostics = (
                PluginAuthoringDiagnostic(
                    filename=self._saved_filename(),
                    line=1,
                    column=1,
                    severity="error",
                    message="Plugin reload was refused.",
                ),
            )
        return PluginValidationReport(
            success=False,
            diagnostics=diagnostics,
            summary=PluginAuthoringSummary(0, 0, "", 0),
        )

    def _error_report(self, filename: str, error: BaseException) -> PluginValidationReport:
        return PluginValidationReport(
            success=False,
            diagnostics=(
                PluginAuthoringDiagnostic(
                    filename=filename or "plugin.py",
                    line=1,
                    column=1,
                    severity="error",
                    message=_bounded_text(error, "Plugin operation failed."),
                ),
            ),
            summary=PluginAuthoringSummary(0, 0, "", 0),
        )


__all__ = ["PluginAuthoringController"]
