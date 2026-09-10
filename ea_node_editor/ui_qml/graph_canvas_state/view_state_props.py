from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import pyqtProperty, pyqtSignal
from ea_node_editor.ui_qml.bridge_runtime import (
    copy_dict as _copy_dict,
)

from ea_node_editor.ui_qml.bridge_runtime import (
    copy_dict as _copy_dict,
    source_attr as _source_attr,
)
if TYPE_CHECKING:
    pass


class ViewStateProps:
    """Viewport view-state projections: zoom, center, visible scene rect."""

    view_state_changed = pyqtSignal()

    @pyqtProperty(float, notify=view_state_changed)
    def center_x(self) -> float:
        return float(_source_attr(self._view_bridge, "center_x", 0.0))

    @pyqtProperty(float, notify=view_state_changed)
    def center_y(self) -> float:
        return float(_source_attr(self._view_bridge, "center_y", 0.0))

    @pyqtProperty(float, notify=view_state_changed)
    def zoom_value(self) -> float:
        return float(_source_attr(self._view_bridge, "zoom_value", 1.0))

    @pyqtProperty("QVariantMap", notify=view_state_changed)
    def visible_scene_rect_payload(self) -> dict[str, Any]:
        payload = _source_attr(self._view_bridge, "visible_scene_rect_payload_cached", None)
        if payload is None:
            payload = _source_attr(self._view_bridge, "visible_scene_rect_payload", {})
        return _copy_dict(payload)

    @pyqtProperty("QVariantMap", notify=view_state_changed)
    def visible_scene_rect_payload_cached(self) -> dict[str, Any]:
        return self.visible_scene_rect_payload

