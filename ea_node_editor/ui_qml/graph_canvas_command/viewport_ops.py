from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import pyqtSlot

from ea_node_editor.ui_qml.bridge_runtime import (
    invoke as _invoke,
)

if TYPE_CHECKING:
    pass

class ViewportOps:
    """Viewport command forwards: zoom, pan, view state, viewport size, centering."""

    @pyqtSlot(float)
    def adjust_zoom(self, factor: float) -> None:
        _invoke(self._view_bridge, "adjust_zoom", float(factor))

    @pyqtSlot(float, float, float, result=bool)
    def adjust_zoom_at_viewport_point(self, factor: float, viewport_x: float, viewport_y: float) -> bool:
        return bool(
            _invoke(
                self._view_bridge,
                "adjust_zoom_at_viewport_point",
                float(factor),
                float(viewport_x),
                float(viewport_y),
                default=False,
            )
        )

    @pyqtSlot(float, float)
    def pan_by(self, delta_x: float, delta_y: float) -> None:
        _invoke(self._view_bridge, "pan_by", float(delta_x), float(delta_y))

    @pyqtSlot(float, float, float, result=bool)
    def set_view_state(self, zoom: float, center_x: float, center_y: float) -> bool:
        return bool(
            _invoke(
                self._view_bridge,
                "set_view_state",
                float(zoom),
                float(center_x),
                float(center_y),
                default=False,
            )
        )

    @pyqtSlot(float, float)
    def set_viewport_size(self, width: float, height: float) -> None:
        _invoke(self._view_bridge, "set_viewport_size", float(width), float(height))

    @pyqtSlot(float, float)
    def center_on_scene_point(self, x: float, y: float) -> None:
        _invoke(self._view_bridge, "center_on_scene_point", float(x), float(y))

