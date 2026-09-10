# Purpose: Own native shell dialogs, import policy, preferences, and presentation actions.
# Map: subsystems/ui_shell.md
# Tests: tests/test_shell_project_session_controller.py, tests/test_tabular_project_managed_data.py
# Landmarks: ShellHostPresenter; property path dialogs; graphics preferences

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
import weakref

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
from PyQt6.QtWidgets import QApplication, QColorDialog, QFileDialog, QInputDialog

from ea_node_editor.graph.file_issue_state import (
    EXTERNAL_LINK_MODE,
    MANAGED_COPY_MODE,
    preferred_repair_mode_for_value,
    repair_modes_for_node_property,
)
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
from ea_node_editor.settings import (
    DEFAULT_GRAPHICS_SETTINGS,
    PROJECT_NODE_INPUTS_DIRNAME,
)
from ea_node_editor.telemetry.status_service import EngineState, ShellStatusService
from ea_node_editor.ui.media_preview_provider import set_media_preview_project_context_provider
from ea_node_editor.ui.mail_preview_provider import set_mail_preview_project_context_provider
from ea_node_editor.ui.dialogs.passive_style_controls import color_to_hex, is_valid_hex_color
from ea_node_editor.ui.pdf_preview_provider import set_pdf_preview_project_context_provider
from ea_node_editor.ui.shell.controllers.app_preferences_controller import normalize_graph_theme_settings
from ea_node_editor.ui.shell.tooltip_policy import (
    TOOLTIP_CATEGORY_GENERAL,
    normalize_tooltip_category_preferences,
)
from ea_node_editor.ui.theme import build_theme_stylesheet, resolve_theme_tokens
from ea_node_editor.ui.theme.styles import build_theme_palette

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


_TABULAR_INPUT_NODE_TYPE_ID = "tabular.input"
_TABULAR_INPUT_PATH_PROPERTY = "path"
_MEDIA_PANEL_NODE_TYPE_ID = "media.panel"
_MEDIA_PANEL_SOURCE_PROPERTY = "source"
_WEB_PAGE_VIEWER_NODE_TYPE_ID = "web.page_viewer"
_WEB_PAGE_VIEWER_START_LOCATION_PROPERTY = "start_location"
_JUPYTER_NOTEBOOK_NODE_TYPE_ID = "code.jupyter_notebook"
_JUPYTER_NOTEBOOK_NOTEBOOK_REF_PROPERTY = "notebook_ref"


@dataclass(frozen=True, slots=True)
class _ProjectManagedImportTarget:
    io_dir: str
    subdirectory: str
    artifact_prefix: str
    extra: Mapping[str, Any] = field(default_factory=dict)


_SOURCE_IMPORT_TARGETS = {
    "image source": _ProjectManagedImportTarget(
        PROJECT_NODE_INPUTS_DIRNAME,
        "media",
        "image_source",
    ),
    "pdf source": _ProjectManagedImportTarget(
        PROJECT_NODE_INPUTS_DIRNAME,
        "media",
        "pdf_source",
    ),
    "video source": _ProjectManagedImportTarget(
        PROJECT_NODE_INPUTS_DIRNAME,
        "media",
        "video_source",
    ),
    "mail source": _ProjectManagedImportTarget(
        PROJECT_NODE_INPUTS_DIRNAME,
        "mail",
        "mail_source",
    ),
    "file path": _ProjectManagedImportTarget(
        PROJECT_NODE_INPUTS_DIRNAME,
        "files",
        "source_file",
    ),
}
_TABULAR_SOURCE_IMPORT_TARGET = _ProjectManagedImportTarget(
    PROJECT_NODE_INPUTS_DIRNAME,
    "tabular/source",
    "tabular_source",
    {"artifact_kind": "tabular_source"},
)
_MEDIA_SOURCE_IMPORT_TARGET = _ProjectManagedImportTarget(
    PROJECT_NODE_INPUTS_DIRNAME,
    "media",
    "media_source",
)
_WEB_HTML_IMPORT_TARGET = _ProjectManagedImportTarget(
    PROJECT_NODE_INPUTS_DIRNAME,
    "web/html",
    "html_source",
    {"artifact_kind": "web_html_source"},
)
_JUPYTER_NOTEBOOK_IMPORT_TARGET = _ProjectManagedImportTarget(
    PROJECT_NODE_INPUTS_DIRNAME,
    "jupyter/notebooks",
    "jupyter_notebook",
    {"artifact_kind": "jupyter_notebook"},
)
_RENDERER_LABELS = {
    QSGRendererInterface.GraphicsApi.Direct3D11Rhi: "Direct3D 11",
    QSGRendererInterface.GraphicsApi.Direct3D12: "Direct3D 12",
    QSGRendererInterface.GraphicsApi.MetalRhi: "Metal",
    QSGRendererInterface.GraphicsApi.NullRhi: "Null",
    QSGRendererInterface.GraphicsApi.OpenGL: "OpenGL",
    QSGRendererInterface.GraphicsApi.OpenVG: "OpenVG",
    QSGRendererInterface.GraphicsApi.Software: "Software",
    QSGRendererInterface.GraphicsApi.VulkanRhi: "Vulkan",
}


class ShellHostPresenter(QObject):
    def __init__(self, host: "ShellWindow") -> None:
        super().__init__(host)
        self._host = host
        self._status_service = ShellStatusService()
        host_ref = weakref.ref(host)

        def _preview_context():
            current_host = host_ref()
            if current_host is None:
                return None
            metadata = current_host.model.project.metadata
            return (
                str(current_host.project_path or "").strip() or None,
                dict(metadata) if isinstance(metadata, dict) else None,
            )

        self._preview_context_provider = _preview_context
        set_media_preview_project_context_provider(self._preview_context_provider)
        set_mail_preview_project_context_provider(self._preview_context_provider)
        set_pdf_preview_project_context_provider(self._preview_context_provider)

    def _project_artifact_resolver(self) -> ProjectArtifactResolver:
        metadata = self._host.model.project.metadata
        return ProjectArtifactResolver(
            project_path=str(self._host.project_path or "").strip() or None,
            project_metadata=dict(metadata) if isinstance(metadata, dict) else None,
        )

    def _resolve_source_file_path(self, source_value: str) -> Path | None:
        normalized_value = str(source_value or "").strip()
        if not normalized_value:
            return None
        resolved = self._project_artifact_resolver().resolve_to_path(normalized_value)
        if resolved is not None:
            return resolved
        return Path(normalized_value).expanduser()

    def _path_dialog_start_path(self, current_path: str) -> str:
        normalized_current = str(current_path or "").strip()
        if normalized_current:
            candidate = self._project_artifact_resolver().resolve_to_path(normalized_current)
            if candidate is None:
                candidate = Path(normalized_current).expanduser()
            if candidate.exists():
                return str(candidate)
            parent = candidate.parent
            if str(parent).strip() and parent.exists():
                return str(parent)
        normalized_project_path = str(self._host.project_path or "").strip()
        if normalized_project_path:
            project_path = Path(normalized_project_path).expanduser()
            parent = project_path.parent
            if str(parent).strip() and parent.exists():
                return str(parent)
        return str(Path.cwd())

    def browse_property_path_dialog(
        self,
        property_label: str,
        current_path: str,
        *,
        dialog_mode: str = "file",
        source_mode: str = "",
        node_type_id: str = "",
        property_key: str = "",
        node_id: str = "",
        node_title: str = "",
        node_type: str = "",
        file_filter: str = "",
    ) -> str:
        normalized_dialog_mode = str(dialog_mode or "file").strip().lower()
        start_path = self._path_dialog_start_path(current_path)
        if normalized_dialog_mode == "folder":
            selected_path = QFileDialog.getExistingDirectory(
                self._host,
                f"Choose {property_label}",
                start_path,
            )
            return str(selected_path or "").strip()

        selected_path, _selected_filter = QFileDialog.getOpenFileName(
            self._host,
            f"Choose {property_label}",
            start_path,
            file_filter,
        )
        normalized_path = str(selected_path or "").strip()
        if not normalized_path:
            return ""
        normalized_source_mode = str(source_mode or "").strip().lower()
        if normalized_source_mode == EXTERNAL_LINK_MODE:
            return normalized_path
        if (
            normalized_source_mode != MANAGED_COPY_MODE
            and self._host.app_preferences_controller.source_import_mode() == EXTERNAL_LINK_MODE
        ):
            return normalized_path
        managed_ref = self._stage_property_source_file(
            property_label=property_label,
            current_path=current_path,
            selected_path=normalized_path,
            node_type_id=node_type_id,
            property_key=property_key,
            node_id=node_id,
            node_title=node_title,
            node_type=node_type,
        )
        return managed_ref or normalized_path

    def internalize_property_path(
        self,
        property_label: str,
        current_path: str,
        *,
        node_type_id: str = "",
        property_key: str = "",
        node_id: str = "",
        node_title: str = "",
        node_type: str = "",
    ) -> str:
        normalized_current = str(current_path or "").strip()
        if not normalized_current:
            return ""
        resolution = self._project_artifact_resolver().resolve(normalized_current)
        if resolution.kind not in {"external_path", "external_file_url"}:
            return ""
        source_path = resolution.absolute_path
        if source_path is None or not source_path.exists() or not source_path.is_file():
            return ""
        return self._stage_property_source_file(
            property_label=property_label,
            current_path=normalized_current,
            selected_path=str(source_path),
            node_type_id=node_type_id,
            property_key=property_key,
            node_id=node_id,
            node_title=node_title,
            node_type=node_type,
        )

    def save_file_dialog(
        self,
        *,
        title: str,
        suggested_path: str = "",
        file_filter: str = "",
        default_suffix: str = "",
    ) -> str:
        normalized_suggested = str(suggested_path or "").strip()
        start_path = self._path_dialog_start_path(normalized_suggested)
        if normalized_suggested:
            candidate = Path(normalized_suggested).expanduser()
            if candidate.parent.exists():
                start_path = str(candidate)
        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            self._host,
            str(title or "Save File").strip() or "Save File",
            start_path,
            file_filter,
        )
        normalized_path = str(selected_path or "").strip()
        if not normalized_path:
            return ""
        suffix = str(default_suffix or "").strip()
        if suffix and not suffix.startswith("."):
            suffix = f".{suffix}"
        if suffix and not Path(normalized_path).suffix:
            normalized_path = f"{normalized_path}{suffix}"
        return normalized_path

    def choose_output_folder_dialog(self, *, title: str, suggested_path: str = "") -> str:
        start_path = self._path_dialog_start_path(str(suggested_path or ""))
        selected_path = QFileDialog.getExistingDirectory(
            self._host,
            str(title or "Choose Output Folder").strip() or "Choose Output Folder",
            start_path,
        )
        return str(selected_path or "").strip()

    def pick_property_color_dialog(self, property_label: str, current_value: str) -> str:
        normalized_current = str(current_value or "").strip()
        initial_color = QColor(normalized_current) if is_valid_hex_color(normalized_current) else QColor("#FFFFFF")
        selected = QColorDialog.getColor(
            initial_color,
            self._host,
            f"Pick color for {property_label}",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not selected.isValid():
            return ""
        return color_to_hex(selected)

    def repair_property_path_dialog(
        self,
        *,
        node_type_id: str,
        property_key: str,
        property_label: str,
        current_path: str,
        node_id: str = "",
        node_title: str = "",
        node_type: str = "",
        file_filter: str = "",
    ) -> str:
        repair_modes = repair_modes_for_node_property(node_type_id, property_key)
        normalized_label = str(property_label or "").strip() or "File"
        normalized_current_path = str(current_path or "").strip()
        if not repair_modes:
            return self.browse_property_path_dialog(
                normalized_label,
                normalized_current_path,
                node_id=node_id,
                node_title=node_title,
                node_type=node_type,
                file_filter=file_filter,
            )

        selected_mode = repair_modes[0]
        if len(repair_modes) > 1:
            metadata = self._host.model.project.metadata
            default_mode = preferred_repair_mode_for_value(
                normalized_current_path,
                project_path=str(self._host.project_path or "").strip() or None,
                project_metadata=dict(metadata) if isinstance(metadata, dict) else None,
                fallback_mode=self._host.app_preferences_controller.source_import_mode(),
                allowed_modes=repair_modes,
            )
            options = ["Managed Copy", "External Link"]
            default_index = 0 if default_mode == MANAGED_COPY_MODE else 1
            selection, accepted = QInputDialog.getItem(
                self._host,
                "Repair file...",
                f"Store repaired {normalized_label.lower()} as:",
                options,
                default_index,
                False,
            )
            if not accepted:
                return ""
            selected_mode = MANAGED_COPY_MODE if str(selection or "").strip() == options[0] else EXTERNAL_LINK_MODE

        selected_path, _selected_filter = QFileDialog.getOpenFileName(
            self._host,
            f"Repair {normalized_label}",
            self._path_dialog_start_path(normalized_current_path),
            file_filter,
        )
        normalized_selected_path = str(selected_path or "").strip()
        if not normalized_selected_path:
            return ""
        if selected_mode == EXTERNAL_LINK_MODE:
            return normalized_selected_path

        managed_ref = self._stage_property_source_file(
            property_label=normalized_label,
            current_path=normalized_current_path,
            selected_path=normalized_selected_path,
            node_type_id=node_type_id,
            property_key=property_key,
            node_id=node_id,
            node_title=node_title,
            node_type=node_type,
        )
        return managed_ref or normalized_selected_path

    def prompt_text_value(
        self,
        *,
        title: str,
        label: str,
        text: str = "",
    ) -> tuple[str, bool]:
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

        dialog = QDialog(self._host)
        dialog.setWindowTitle(str(title or "").strip())
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        prompt_label = QLabel(str(label or "").strip(), dialog)
        prompt_field = QLineEdit(dialog)
        prompt_field.setText(str(text or ""))
        prompt_field.selectAll()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        layout.addWidget(prompt_label)
        layout.addWidget(prompt_field)
        layout.addWidget(buttons)

        prompt_field.setFocus(Qt.FocusReason.PopupFocusReason)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return prompt_field.text(), accepted

    def _stage_property_source_file(
        self,
        *,
        property_label: str,
        current_path: str,
        selected_path: str,
        node_type_id: str = "",
        property_key: str = "",
        node_id: str = "",
        node_title: str = "",
        node_type: str = "",
    ) -> str:
        import_target = self._source_import_target(
            property_label,
            node_type_id=node_type_id,
            property_key=property_key,
        )
        if import_target is None:
            return ""

        source_path = self._resolve_source_file_path(selected_path)
        if source_path is None:
            return ""

        return self._host.project_session_controller.stage_node_artifact_file(
            source_path,
            artifact_prefix=import_target.artifact_prefix,
            io_dir=import_target.io_dir,
            artifact_id=self._current_source_artifact_id(current_path),
            subdirectory=import_target.subdirectory,
            filename=source_path.name,
            entry_metadata=import_target.extra,
            node_id=node_id,
            node_title=node_title,
            node_type=node_type or node_type_id,
        )

    @staticmethod
    def _source_import_target(
        property_label: str,
        *,
        node_type_id: str = "",
        property_key: str = "",
    ) -> _ProjectManagedImportTarget | None:
        if (
            str(node_type_id or "").strip() == _MEDIA_PANEL_NODE_TYPE_ID
            and str(property_key or "").strip() == _MEDIA_PANEL_SOURCE_PROPERTY
        ):
            return _MEDIA_SOURCE_IMPORT_TARGET
        if (
            str(node_type_id or "").strip() == _TABULAR_INPUT_NODE_TYPE_ID
            and str(property_key or "").strip() == _TABULAR_INPUT_PATH_PROPERTY
        ):
            return _TABULAR_SOURCE_IMPORT_TARGET
        if (
            str(node_type_id or "").strip() == _WEB_PAGE_VIEWER_NODE_TYPE_ID
            and str(property_key or "").strip() == _WEB_PAGE_VIEWER_START_LOCATION_PROPERTY
        ):
            return _WEB_HTML_IMPORT_TARGET
        if (
            str(node_type_id or "").strip() == _JUPYTER_NOTEBOOK_NODE_TYPE_ID
            and str(property_key or "").strip() == _JUPYTER_NOTEBOOK_NOTEBOOK_REF_PROPERTY
        ):
            return _JUPYTER_NOTEBOOK_IMPORT_TARGET
        return _SOURCE_IMPORT_TARGETS.get(str(property_label or "").strip().lower())

    def _current_source_artifact_id(self, current_path: str) -> str:
        resolution = self._project_artifact_resolver().resolve(current_path)
        return str(resolution.artifact_id or "").strip()

    def sync_graphics_show_port_labels_action(self, show_port_labels: bool) -> None:
        action = getattr(self._host, "action_show_port_labels", None)
        if action is None or action.isChecked() == show_port_labels:
            return
        blocked = action.blockSignals(True)
        action.setChecked(show_port_labels)
        action.blockSignals(blocked)

    def sync_general_help_tooltips_action(self, enabled: bool) -> None:
        action = getattr(self._host, "action_general_help_tooltips", None)
        if action is None or action.isChecked() == enabled:
            return
        blocked = action.blockSignals(True)
        action.setChecked(enabled)
        action.blockSignals(blocked)

    def refresh_active_workspace_scene_payload(self) -> None:
        workspace_manager = getattr(self._host, "workspace_manager", None)
        scene = getattr(self._host, "scene", None)
        if workspace_manager is None or scene is None:
            return
        workspace_id = str(workspace_manager.active_workspace_id() or "").strip()
        if not workspace_id:
            return
        scene.refresh_workspace_from_model(workspace_id)

    def apply_graphics_preferences(self, graphics: Any) -> dict[str, Any]:
        previous_passive_node_library_display_mode = str(
            getattr(
                getattr(self._host, "workspace_ui_state", None),
                "passive_node_library_display_mode",
                DEFAULT_GRAPHICS_SETTINGS["shell"]["passive_node_library_display_mode"],
            )
        )
        resolved = self._host.shell_workspace_presenter.apply_graphics_preferences(graphics)
        canvas = resolved.get("canvas", {}) if isinstance(resolved, dict) else {}
        shell = resolved.get("shell", {}) if isinstance(resolved, dict) else {}
        current_show_port_labels = bool(
            canvas.get(
                "show_port_labels",
                self._host.shell_workspace_presenter.graphics_show_port_labels,
            )
        )
        tooltip_categories = normalize_tooltip_category_preferences(shell.get("tooltip_categories"))
        current_general_tooltips = bool(tooltip_categories[TOOLTIP_CATEGORY_GENERAL])
        current_passive_node_library_display_mode = str(
            shell.get(
                "passive_node_library_display_mode",
                previous_passive_node_library_display_mode,
            )
        )
        self.sync_graphics_show_port_labels_action(current_show_port_labels)
        self.sync_general_help_tooltips_action(current_general_tooltips)
        if previous_passive_node_library_display_mode != current_passive_node_library_display_mode:
            self._host.node_library_changed.emit()
        return resolved

    def apply_theme(self, theme_id: Any) -> str:
        resolved_theme_id = self._host.theme_bridge.apply_theme(theme_id)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_theme_stylesheet(resolved_theme_id))
            app.setPalette(build_theme_palette(resolved_theme_id))
        self._apply_viewer_canvas_theme(resolved_theme_id)
        return resolved_theme_id

    def _apply_viewer_canvas_theme(self, resolved_theme_id: str) -> None:
        from ea_node_editor.execution.viewer_pyvista_style import set_viewer_canvas_dark

        # icon_variant "light" means light icons on a dark shell, i.e. a dark theme.
        tokens = resolve_theme_tokens(resolved_theme_id)
        set_viewer_canvas_dark(tokens.icon_variant == "light")
        viewer_host_service = getattr(self._host, "viewer_host_service", None)
        refresh = getattr(viewer_host_service, "refresh_bound_widget_canvas_theme", None)
        if callable(refresh):
            refresh()

    def preview_graph_theme_settings(self, graph_theme_settings: Any) -> str:
        normalized = normalize_graph_theme_settings(graph_theme_settings)
        return self._host.graph_theme_bridge.apply_settings(
            shell_theme_id=self._host.active_theme_id,
            graph_theme_settings=normalized,
        )

    def active_renderer_label(self) -> str:
        api = QSGRendererInterface.GraphicsApi.Unknown
        quick_widget = getattr(self._host, "quick_widget", None)
        if quick_widget is not None:
            quick_window = quick_widget.quickWindow()
            if quick_window is not None:
                renderer_interface = quick_window.rendererInterface()
                if renderer_interface is not None:
                    api = renderer_interface.graphicsApi()
        if api == QSGRendererInterface.GraphicsApi.Unknown:
            api = QQuickWindow.graphicsApi()
        return _RENDERER_LABELS.get(api, "Unavailable")

    def show_graphics_settings_dialog(self, _checked: bool = False) -> None:
        from ea_node_editor.ui.dialogs import GraphicsSettingsDialog

        preferences = self._host.app_preferences_controller
        dialog = GraphicsSettingsDialog(
            initial_settings=preferences.graphics_settings(),
            available_graph_themes=preferences.graph_theme_choices(),
            manage_graph_themes_callback=self.edit_graph_theme_settings,
            active_renderer_label=self.active_renderer_label(),
            tooltips_enabled=bool(self._host.graphics_show_tooltips),
            parent=self._host,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        preferences.set_graphics_settings(dialog.values(), host=self._host)

    def show_selected_run_settings_dialog(self, _checked: bool = False) -> None:
        from ea_node_editor.ui.dialogs import SelectedRunSettingsDialog

        dialog = SelectedRunSettingsDialog(
            initial_settings=self._host.app_preferences_controller.selected_run_settings(),
            parent=self._host,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        preferences = self._host.app_preferences_controller
        previous = preferences.selected_run_preview_before_run()
        current = preferences.set_selected_run_preview_before_run(
            dialog.selected_run_preview_before_run()
        )
        if current != previous:
            self._host.graphics_preferences_changed.emit()

    def show_keyboard_mouse_reference_dialog(self, _checked: bool = False) -> None:
        from ea_node_editor.ui.dialogs import InputReferenceDialog

        dialog = InputReferenceDialog(parent=self._host)
        dialog.exec()

    def show_third_party_notices_dialog(self, _checked: bool = False) -> None:
        from ea_node_editor.ui.dialogs import ThirdPartyNoticesDialog

        dialog = ThirdPartyNoticesDialog(parent=self._host)
        dialog.exec()

    def edit_graph_theme_settings(
        self,
        graph_theme_settings: Any,
        *,
        enable_live_apply: bool = False,
    ) -> dict[str, Any] | None:
        from ea_node_editor.ui.dialogs import GraphThemeEditorDialog

        dialog = GraphThemeEditorDialog(
            initial_settings=graph_theme_settings,
            parent=self._host,
            live_apply_callback=self.preview_graph_theme_settings if enable_live_apply else None,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return None
        return dialog.graph_theme_settings()

    def show_graph_theme_editor_dialog(self, _checked: bool = False) -> None:
        graph_theme_settings = self.edit_graph_theme_settings(
            self._host.app_preferences_controller.graph_theme_settings(),
            enable_live_apply=True,
        )
        if graph_theme_settings is None:
            return
        graphics = self._host.app_preferences_controller.graphics_settings()
        graphics["graph_theme"] = graph_theme_settings
        self._host.app_preferences_controller.set_graphics_settings(graphics, host=self._host)

    def update_metrics(self) -> None:
        metrics = self._status_service.collect_system_metrics()
        self.update_system_metrics(
            metrics.cpu_percent,
            metrics.ram_used_gb,
            metrics.ram_total_gb,
            disk_read_mb_s=metrics.disk_read_mb_s,
            disk_write_mb_s=metrics.disk_write_mb_s,
            show_fps=bool(
                getattr(
                    getattr(self._host, "workspace_ui_state", None),
                    "show_fps_telemetry",
                    True,
                )
            ),
        )

    def update_engine_status(
        self,
        state: EngineState,
        details: str = "",
    ) -> None:
        presentation = self._status_service.engine_status(state, details)
        self._host.status_engine.set_icon(presentation.icon)
        self._host.status_engine.set_text(presentation.text)

    def update_job_counters(self, running: int, queued: int, done: int, failed: int) -> None:
        presentation = self._status_service.job_counters(
            running=running,
            queued=queued,
            done=done,
            failed=failed,
        )
        self._host.status_jobs.set_text(presentation.text)

    def update_system_metrics(
        self,
        cpu_percent: float,
        ram_used_gb: float,
        ram_total_gb: float,
        fps: float | None = None,
        disk_read_mb_s: float = 0.0,
        disk_write_mb_s: float = 0.0,
        show_fps: bool = True,
    ) -> None:
        fps_value = max(0.0, float(fps)) if fps is not None else self._host._frame_rate_sampler.snapshot().fps
        presentation = self._status_service.system_metrics(
            fps=fps_value if show_fps else None,
            cpu_percent=cpu_percent,
            ram_used_gb=ram_used_gb,
            ram_total_gb=ram_total_gb,
            disk_read_mb_s=disk_read_mb_s,
            disk_write_mb_s=disk_write_mb_s,
            show_fps=show_fps,
        )
        self._host.status_metrics.set_text(presentation.text)

    def update_notification_counters(self, warnings: int, errors: int) -> None:
        presentation = self._status_service.notification_counters(warnings=warnings, errors=errors)
        self._host.status_notifications.set_text(presentation.text)
