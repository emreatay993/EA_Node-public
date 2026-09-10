from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import pyqtSlot

from ea_node_editor.ui_qml.bridge_runtime import (
    invoke as _invoke,
    variant_value as _variant_value,
)

if TYPE_CHECKING:
    pass

class GraphicsSettingsOps:
    """Graphics/preferences command forwards for graph settings and themes."""

    @pyqtSlot(bool)
    def set_snap_to_grid_enabled(self, enabled: bool) -> None:
        _invoke(
            self._search_scope_controller,
            "set_snap_to_grid_enabled",
            bool(enabled),
        )

    @pyqtSlot(bool)
    def set_graphics_minimap_expanded(self, expanded: bool) -> None:
        _invoke(
            self._search_scope_controller,
            "set_graphics_minimap_expanded",
            bool(expanded),
        )

    @pyqtSlot(bool)
    def set_graphics_show_grid(self, show_grid: bool) -> None:
        _invoke(self._graphics_source, "set_graphics_show_grid", bool(show_grid))

    @pyqtSlot(str)
    def set_graphics_canvas_background_variant(self, variant: str) -> None:
        _invoke(self._graphics_source, "set_graphics_canvas_background_variant", variant)

    @pyqtSlot(str)
    def set_graphics_grid_style(self, style: str) -> None:
        _invoke(self._graphics_source, "set_graphics_grid_style", style)

    @pyqtSlot(str)
    def set_graphics_canvas_import_mode(self, mode: str) -> None:
        _invoke(self._graphics_source, "set_graphics_canvas_import_mode", mode)

    @pyqtSlot(bool)
    def set_graphics_show_port_labels(self, show_port_labels: bool) -> None:
        _invoke(self._graphics_source, "set_graphics_show_port_labels", bool(show_port_labels))

    @pyqtSlot(bool)
    def set_selected_run_preview_before_run(self, enabled: bool) -> None:
        getter = getattr(
            self._app_preferences_source,
            "selected_run_preview_before_run",
            None,
        )
        previous = bool(
            getter()
            if callable(getter)
            else getter
            if getter is not None
            else True
        )
        current = bool(
            _invoke(
                self._app_preferences_source,
                "set_selected_run_preview_before_run",
                bool(enabled),
                default=previous,
            )
        )
        if current != previous:
            emit = getattr(self._graphics_preferences_changed_signal, "emit", None)
            if callable(emit):
                emit()

    @pyqtSlot(bool)
    def set_graphics_node_shadow(self, enabled: bool) -> None:
        _invoke(self._graphics_source, "set_graphics_node_shadow", bool(enabled))

    @pyqtSlot(str)
    def set_graphics_floating_toolbar_style(self, style: str) -> None:
        _invoke(self._graphics_source, "set_graphics_floating_toolbar_style", style)

    @pyqtSlot(str)
    def set_graphics_floating_toolbar_size(self, size: str) -> None:
        _invoke(self._graphics_source, "set_graphics_floating_toolbar_size", size)

    @pyqtSlot(str)
    def set_graphics_selection_toolbar_mode(self, mode: str) -> None:
        _invoke(self._graphics_source, "set_graphics_selection_toolbar_mode", mode)

    @pyqtSlot(str)
    def set_graphics_selection_toolbar_minimal_menu_trigger(self, trigger: str) -> None:
        _invoke(
            self._graphics_source,
            "set_graphics_selection_toolbar_minimal_menu_trigger",
            trigger,
        )

    @pyqtSlot("QVariantMap")
    def set_folder_explorer_column_widths(self, widths: dict[str, Any]) -> None:
        payload = _variant_value(widths)
        _invoke(
            self._graphics_source,
            "set_folder_explorer_column_widths",
            dict(payload) if isinstance(payload, Mapping) else {},
        )

    @pyqtSlot(str)
    def record_recent_text_color(self, color: str) -> None:
        _invoke(self._graphics_source, "record_recent_text_color", str(color or ""))

    @pyqtSlot(str)
    def set_graphics_shell_theme(self, theme_id: str) -> None:
        _invoke(self._graphics_source, "set_graphics_shell_theme", theme_id)

    @pyqtSlot(bool)
    def set_graphics_graph_follow_shell_theme(self, follow_shell_theme: bool) -> None:
        _invoke(self._graphics_source, "set_graphics_graph_follow_shell_theme", bool(follow_shell_theme))

    @pyqtSlot(str)
    def set_graphics_graph_theme(self, theme_id: str) -> None:
        _invoke(self._graphics_source, "set_graphics_graph_theme", theme_id)

    @pyqtSlot(str)
    def set_graphics_node_elapsed_time_unit(self, unit: str) -> None:
        _invoke(self._graphics_source, "set_graphics_node_elapsed_time_unit", unit)

    @pyqtSlot(str)
    def set_graphics_node_elapsed_time_visibility(self, visibility: str) -> None:
        _invoke(self._graphics_source, "set_graphics_node_elapsed_time_visibility", visibility)

    @pyqtSlot(str)
    def set_graphics_node_comment_editor_default(self, value: str) -> None:
        _invoke(self._graphics_source, "set_graphics_node_comment_editor_default", value)

    @pyqtSlot()
    def request_open_graphics_settings(self) -> None:
        _invoke(self._graphics_source, "request_open_graphics_settings")
