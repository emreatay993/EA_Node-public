from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ea_node_editor.common.coercions import normalize_path_text
from ea_node_editor.execution.managed_runtime import (
    ManagedRuntimeInstallResult,
    prepare_managed_runtime,
    resolve_managed_runtime_paths,
)
from ea_node_editor.settings import DEFAULT_WORKFLOW_SETTINGS
from ea_node_editor.ui.dialogs.sectioned_settings_dialog import SectionedSettingsDialog
from ea_node_editor.ui.shell.tooltip_policy import tooltip_category_effectively_visible
from ea_node_editor.ui.tooltips import tooltip_category, tooltip_text


class _ManagedRuntimePrepareWorker(QObject):
    finished = pyqtSignal(object)

    def __init__(self, prepare: Callable[[], ManagedRuntimeInstallResult]) -> None:
        super().__init__()
        self._prepare = prepare

    def run(self) -> None:
        try:
            result = self._prepare()
        except Exception as exc:  # noqa: BLE001
            result = ManagedRuntimeInstallResult(
                success=False,
                error=f"Preparing the managed COREX runtime failed: {exc}",
            )
        self.finished.emit(result)


class WorkflowSettingsDialog(SectionedSettingsDialog):
    _SECTIONS = [
        ("general", "General"),
        ("solver_config", "Solver Config"),
        ("environment", "Environment"),
        ("plugins", "Plugins"),
        ("logging", "Logging"),
    ]

    def __init__(
        self,
        initial_settings: dict[str, Any] | None = None,
        parent=None,
        *,
        application_default_python_executable: str = "",
        managed_runtime_prepare: Callable[[], ManagedRuntimeInstallResult] | None = None,
    ) -> None:
        self._managed_runtime_prepare = managed_runtime_prepare or prepare_managed_runtime
        self._managed_runtime_thread: QThread | None = None
        self._managed_runtime_worker: _ManagedRuntimePrepareWorker | None = None
        self._tooltip_parent = parent
        super().__init__(
            window_title="Workflow Settings",
            header_text="Configure workflow defaults and runtime behavior.",
            sections=self._SECTIONS,
            section_list_object_name="workflowSettingsSectionList",
            header_object_name="workflowSettingsHeader",
            parent=parent,
        )
        self.application_python_path_edit.setText(
            normalize_path_text(application_default_python_executable)
        )
        self.set_values(initial_settings or {})

    def _build_pages(self) -> None:
        self.add_section_page(self._build_general_page())
        self.add_section_page(self._build_solver_page())
        self.add_section_page(self._build_environment_page())
        self.add_section_page(self._build_plugins_page())
        self.add_section_page(self._build_logging_page())

    def _build_general_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.project_name_edit = QLineEdit(page)
        self.author_edit = QLineEdit(page)
        self.description_edit = QTextEdit(page)
        self.description_edit.setMinimumHeight(100)
        form.addRow("Project Name", self.project_name_edit)
        form.addRow("Author", self.author_edit)
        form.addRow("Description", self.description_edit)
        return page

    def _build_solver_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.parallel_check = QCheckBox("Enable parallel processing", page)
        self.thread_count_spin = QSpinBox(page)
        self.thread_count_spin.setRange(1, 256)
        self.memory_limit_spin = QSpinBox(page)
        self.memory_limit_spin.setRange(1, 1024)
        self.memory_limit_spin.setSuffix(" GB")
        form.addRow(self.parallel_check)
        form.addRow("Thread Count", self.thread_count_spin)
        form.addRow("Memory Limit", self.memory_limit_spin)
        return page

    def _build_environment_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.application_python_path_edit = QLineEdit(page)
        self.application_python_path_edit.setObjectName("applicationPythonExecutableEdit")
        self.application_python_path_edit.setPlaceholderText(
            r"C:\path\to\venv\Scripts\python.exe"
        )
        self.application_python_browse_button = QPushButton("Browse", page)
        self.application_python_browse_button.setObjectName("browseApplicationPythonButton")
        self.application_python_browse_button.clicked.connect(
            self._browse_application_python_executable
        )
        application_python_field = QWidget(page)
        application_python_layout = QHBoxLayout(application_python_field)
        application_python_layout.setContentsMargins(0, 0, 0, 0)
        application_python_layout.addWidget(self.application_python_path_edit, stretch=1)
        application_python_layout.addWidget(self.application_python_browse_button)

        self.workflow_python_path_edit = QLineEdit(page)
        self.workflow_python_path_edit.setObjectName("workflowPythonOverrideEdit")
        self.workflow_python_path_edit.setPlaceholderText(
            r"C:\path\to\venv\Scripts\python.exe"
        )
        self.workflow_python_browse_button = QPushButton("Browse", page)
        self.workflow_python_browse_button.setObjectName("browseWorkflowPythonButton")
        self.workflow_python_browse_button.clicked.connect(
            self._browse_workflow_python_executable
        )
        workflow_python_field = QWidget(page)
        workflow_python_layout = QHBoxLayout(workflow_python_field)
        workflow_python_layout.setContentsMargins(0, 0, 0, 0)
        workflow_python_layout.addWidget(self.workflow_python_path_edit, stretch=1)
        workflow_python_layout.addWidget(self.workflow_python_browse_button)

        self.workdir_edit = QLineEdit(page)
        self.prepare_runtime_button = QPushButton("Create / Repair Managed Runtime", page)
        self.prepare_runtime_button.setObjectName("prepareCorexRuntimeButton")
        self.prepare_runtime_button.clicked.connect(self._prepare_managed_runtime)
        self.clear_application_runtime_button = QPushButton(
            "Clear Application Default", page
        )
        self.clear_application_runtime_button.setObjectName("clearApplicationPythonButton")
        self.clear_application_runtime_button.clicked.connect(
            self._clear_application_default
        )
        application_actions = QWidget(page)
        application_actions_layout = QHBoxLayout(application_actions)
        application_actions_layout.setContentsMargins(0, 0, 0, 0)
        application_actions_layout.addWidget(self.prepare_runtime_button)
        application_actions_layout.addWidget(self.clear_application_runtime_button)
        application_actions_layout.addStretch(1)

        self.inherit_application_runtime_button = QPushButton(
            "Inherit Application Default", page
        )
        self.inherit_application_runtime_button.setObjectName(
            "inheritApplicationPythonButton"
        )
        self.inherit_application_runtime_button.clicked.connect(
            self._inherit_application_default
        )
        self.runtime_help_label = QLabel(
            "External Python runs the entire workflow as trusted local execution, not a "
            "sandbox. User-managed environments must import "
            "ea_node_editor.execution.stdio_worker and may still be rejected by the "
            "startup handshake. Changes apply to the next run. The workflow override "
            "wins over the application default; built-in execution is used only when "
            "both are blank.",
            page,
        )
        self.runtime_help_label.setObjectName("pythonRuntimeHelpLabel")
        self.runtime_help_label.setWordWrap(True)
        self.managed_runtime_status_label = QLabel(page)
        self.managed_runtime_status_label.setObjectName("managedRuntimeStatusLabel")
        self.managed_runtime_status_label.setWordWrap(True)
        self.application_python_path_edit.textChanged.connect(
            self._runtime_path_text_changed
        )
        self.workflow_python_path_edit.textChanged.connect(self._runtime_path_text_changed)
        self._apply_environment_tooltips()
        form.addRow("Application Default Python Executable", application_python_field)
        form.addRow("Application Actions", application_actions)
        form.addRow("Workflow Override", workflow_python_field)
        form.addRow("Workflow Action", self.inherit_application_runtime_button)
        form.addRow("", self.runtime_help_label)
        form.addRow("", self.managed_runtime_status_label)
        form.addRow("Working Directory", self.workdir_edit)
        self._refresh_managed_runtime_status()
        return page

    def _build_plugins_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        info = QLabel("One plugin id per line.")
        info.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.plugins_text = QTextEdit(page)
        self.plugins_text.setPlaceholderText("plugin.alpha\nplugin.beta")
        layout.addWidget(info)
        layout.addWidget(self.plugins_text, stretch=1)
        return page

    def _build_logging_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.log_level_combo = QComboBox(page)
        for level in ("debug", "info", "warning", "error"):
            self.log_level_combo.addItem(level, level)
        self.capture_console_check = QCheckBox("Capture console output", page)
        form.addRow("Log Level", self.log_level_combo)
        form.addRow(self.capture_console_check)
        return page

    @staticmethod
    def _normalize(initial_settings: dict[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(DEFAULT_WORKFLOW_SETTINGS)
        for key, section in initial_settings.items():
            if key not in normalized or not isinstance(section, dict):
                continue
            for field, value in section.items():
                normalized[key][field] = value
        return normalized

    def set_values(self, initial_settings: dict[str, Any]) -> None:
        settings = self._normalize(initial_settings)
        self.project_name_edit.setText(str(settings["general"].get("project_name", "")))
        self.author_edit.setText(str(settings["general"].get("author", "")))
        self.description_edit.setPlainText(str(settings["general"].get("description", "")))
        self.parallel_check.setChecked(bool(settings["solver_config"].get("enable_parallel", True)))
        self.thread_count_spin.setValue(int(settings["solver_config"].get("thread_count", 8)))
        self.memory_limit_spin.setValue(int(settings["solver_config"].get("memory_limit_gb", 12)))
        self.workflow_python_path_edit.setText(
            normalize_path_text(settings["environment"].get("python_path"))
        )
        self.workdir_edit.setText(str(settings["environment"].get("working_directory", "")))
        plugins = settings["plugins"].get("enabled", [])
        if isinstance(plugins, list):
            self.plugins_text.setPlainText("\n".join(str(item) for item in plugins))
        else:
            self.plugins_text.setPlainText("")
        level = str(settings["logging"].get("level", "info"))
        idx = self.log_level_combo.findData(level)
        self.log_level_combo.setCurrentIndex(idx if idx >= 0 else 1)
        self.capture_console_check.setChecked(bool(settings["logging"].get("capture_console", True)))
        if hasattr(self, "managed_runtime_status_label"):
            self._refresh_managed_runtime_status()

    def values(self) -> dict[str, Any]:
        plugins = [
            line.strip()
            for line in self.plugins_text.toPlainText().splitlines()
            if line.strip()
        ]
        return {
            "general": {
                "project_name": self.project_name_edit.text().strip(),
                "author": self.author_edit.text().strip(),
                "description": self.description_edit.toPlainText().strip(),
            },
            "solver_config": {
                "enable_parallel": self.parallel_check.isChecked(),
                "thread_count": int(self.thread_count_spin.value()),
                "memory_limit_gb": int(self.memory_limit_spin.value()),
            },
            "environment": {
                "python_path": normalize_path_text(self.workflow_python_path_edit.text()),
                "working_directory": self.workdir_edit.text().strip(),
            },
            "plugins": {
                "enabled": plugins,
            },
            "logging": {
                "level": str(self.log_level_combo.currentData()),
                "capture_console": self.capture_console_check.isChecked(),
            },
        }

    def application_default_python_executable(self) -> str:
        return normalize_path_text(self.application_python_path_edit.text())

    def _effective_runtime_summary(self) -> str:
        workflow_path = normalize_path_text(self.workflow_python_path_edit.text())
        if workflow_path:
            return f"Effective next run: workflow override ({workflow_path})."
        application_path = self.application_default_python_executable()
        if application_path:
            return f"Effective next run: application default ({application_path})."
        return "Effective next run: built-in process-isolated runtime."

    def _refresh_managed_runtime_status(self, message: str | None = None) -> None:
        if message is None:
            try:
                paths = resolve_managed_runtime_paths()
                message = (
                    f"Managed runtime ready: {paths.python_executable}"
                    if paths.python_executable.exists()
                    else f"Managed runtime not prepared: {paths.python_executable}"
                )
            except Exception as exc:  # noqa: BLE001
                message = f"Managed runtime status unavailable: {exc}"
        self.managed_runtime_status_label.setText(
            f"{self._effective_runtime_summary()}\n{message}"
        )

    def _tooltip_category_enabled(self, category: str) -> bool:
        parent = self._tooltip_parent
        tooltip_manager = getattr(parent, "tooltip_manager", None)
        if tooltip_manager is not None:
            category_enabled = getattr(tooltip_manager, "category_tooltips_enabled", None)
            if callable(category_enabled):
                return bool(category_enabled(category))
        category_enabled = getattr(parent, "tooltip_category_enabled", None)
        if callable(category_enabled):
            return bool(category_enabled(category))
        return tooltip_category_effectively_visible(category)

    def _set_category_tooltip(self, widget: QWidget, tooltip_key: str) -> None:
        category = tooltip_category(tooltip_key)
        widget.setProperty("tooltip_category", category)
        widget.setToolTip(tooltip_text(tooltip_key) if self._tooltip_category_enabled(category) else "")

    def _apply_environment_tooltips(self) -> None:
        self._set_category_tooltip(
            self.application_python_path_edit,
            "settings.workflow.environment.application_default_python_executable",
        )
        self._set_category_tooltip(
            self.application_python_browse_button,
            "settings.workflow.environment.browse_application_python",
        )
        self._set_category_tooltip(
            self.prepare_runtime_button,
            "settings.workflow.environment.prepare_managed_runtime",
        )
        self._set_category_tooltip(
            self.clear_application_runtime_button,
            "settings.workflow.environment.clear_application_default",
        )
        self._set_category_tooltip(
            self.workflow_python_path_edit,
            "settings.workflow.environment.workflow_python_override",
        )
        self._set_category_tooltip(
            self.workflow_python_browse_button,
            "settings.workflow.environment.browse_workflow_python",
        )
        self._set_category_tooltip(
            self.inherit_application_runtime_button,
            "settings.workflow.environment.inherit_application_default",
        )
        self._set_category_tooltip(
            self.managed_runtime_status_label,
            "settings.workflow.environment.managed_runtime_status",
        )
        self._set_category_tooltip(
            self.workdir_edit,
            "settings.workflow.environment.working_directory",
        )

    def _set_runtime_controls_enabled(self, enabled: bool) -> None:
        for control in (
            self.prepare_runtime_button,
            self.application_python_browse_button,
            self.clear_application_runtime_button,
            self.workflow_python_browse_button,
            self.inherit_application_runtime_button,
        ):
            control.setEnabled(enabled)
        if hasattr(self, "ok_button"):
            self.ok_button.setEnabled(enabled)
        if hasattr(self, "cancel_button"):
            self.cancel_button.setEnabled(enabled)

    def _prepare_managed_runtime(self) -> None:
        if self._managed_runtime_thread is not None:
            return
        self._refresh_managed_runtime_status("Preparing managed COREX runtime...")
        self._set_runtime_controls_enabled(False)
        thread = QThread(self)
        worker = _ManagedRuntimePrepareWorker(self._managed_runtime_prepare)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._managed_runtime_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._managed_runtime_thread_finished)
        self._managed_runtime_thread = thread
        self._managed_runtime_worker = worker
        thread.start()

    def _managed_runtime_finished(self, result: ManagedRuntimeInstallResult) -> None:
        self._set_runtime_controls_enabled(True)
        if result.success:
            self.application_python_path_edit.setText(result.python_executable)
            self._refresh_managed_runtime_status(
                f"Managed runtime ready: {result.python_executable}"
            )
            return
        message = result.error or result.status.error or "Managed COREX runtime setup failed."
        self._refresh_managed_runtime_status(message)

    def _managed_runtime_thread_finished(self) -> None:
        self._managed_runtime_thread = None
        self._managed_runtime_worker = None

    def _browse_application_python_executable(self) -> None:
        self._browse_python_executable(
            self.application_python_path_edit,
            "Select Application Default Python Executable",
        )

    def _browse_workflow_python_executable(self) -> None:
        self._browse_python_executable(
            self.workflow_python_path_edit,
            "Select Workflow Override Python Executable",
        )

    def _browse_python_executable(self, target: QLineEdit, title: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            target.text(),
            "Python Executable (*.exe);;All Files (*)",
        )
        if path:
            target.setText(path)

    def _clear_application_default(self) -> None:
        self.application_python_path_edit.clear()
        self._refresh_managed_runtime_status("Application default cleared.")

    def _inherit_application_default(self) -> None:
        self.workflow_python_path_edit.clear()
        self._refresh_managed_runtime_status(
            "Workflow override cleared; inheriting application default."
        )

    def _runtime_path_text_changed(self, _text: str) -> None:
        self._refresh_managed_runtime_status()

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._managed_runtime_thread is not None:
            self._refresh_managed_runtime_status(
                "Preparing managed COREX runtime. Wait for setup to finish before closing."
            )
            event.ignore()
            return
        super().closeEvent(event)
