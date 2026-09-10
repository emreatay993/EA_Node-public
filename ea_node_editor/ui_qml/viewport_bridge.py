from __future__ import annotations

import math

from PyQt6.QtCore import QObject, QPointF, QRect, QRectF, pyqtProperty, pyqtSignal, pyqtSlot

from ea_node_editor.ui_qml.graph_canvas_viewport_index import (
    DEFAULT_VIEWPORT_MODEL_BUCKET_PX,
    DEFAULT_VIEWPORT_MODEL_HYSTERESIS_PADDING_PX,
    bucketed_hysteresis_visible_scene_rect,
    expanded_visible_scene_rect,
    inflate_scene_rect,
    rects_equal,
    scene_padding_for_viewport_pixels,
    scene_rect_payload,
    visible_scene_rect,
)

MIN_ZOOM = 0.1
MAX_ZOOM = 3.0
FRAME_PADDING_PX = 80.0


class ViewportBridge(QObject):
    zoom_changed = pyqtSignal(float)
    center_changed = pyqtSignal(float, float)
    view_state_changed = pyqtSignal()
    node_render_activation_scene_rect_changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._zoom = 1.0
        self._center_x = 0.0
        self._center_y = 0.0
        self._viewport_rect = QRect(0, 0, 1600, 900)
        self._visible_scene_rect = QRectF()
        self._visible_scene_rect_payload: dict[str, float] = {}
        self._node_render_activation_scene_rect = None
        self._node_render_activation_scene_rect_payload: dict[str, float] = {}
        self._refresh_visible_scene_rect_cache(emit_node_activation_changed=False)

    @property
    def zoom(self) -> float:
        return self._zoom

    @pyqtProperty(float, notify=view_state_changed)
    def zoom_value(self) -> float:
        return self._zoom

    @pyqtProperty(float, notify=view_state_changed)
    def center_x(self) -> float:
        return self._center_x

    @pyqtProperty(float, notify=view_state_changed)
    def center_y(self) -> float:
        return self._center_y

    @pyqtProperty("QVariantMap", notify=view_state_changed)
    def visible_scene_rect_payload(self) -> dict[str, float]:
        return self._visible_scene_rect_payload

    @pyqtProperty("QVariantMap", notify=view_state_changed)
    def visible_scene_rect_payload_cached(self) -> dict[str, float]:
        return self._visible_scene_rect_payload

    @pyqtProperty(float, constant=True)
    def visible_model_hysteresis_padding_px(self) -> float:
        return DEFAULT_VIEWPORT_MODEL_HYSTERESIS_PADDING_PX

    @pyqtProperty(float, constant=True)
    def visible_model_bucket_px(self) -> float:
        return DEFAULT_VIEWPORT_MODEL_BUCKET_PX

    @pyqtProperty("QVariantMap", notify=view_state_changed)
    def expanded_visible_scene_rect_payload(self) -> dict[str, float]:
        return scene_rect_payload(
            expanded_visible_scene_rect(
                self._visible_scene_rect_payload,
                zoom=self._zoom,
            )
        )

    @pyqtProperty("QVariantMap", notify=node_render_activation_scene_rect_changed)
    def node_render_activation_scene_rect_payload(self) -> dict[str, float]:
        return self._node_render_activation_scene_rect_payload

    def _clamp_zoom(self, zoom: float) -> float:
        normalized = float(zoom)
        if not math.isfinite(normalized):
            return self._zoom
        return max(MIN_ZOOM, min(normalized, MAX_ZOOM))

    def _scene_dimensions_for_zoom(self, zoom: float) -> tuple[float, float]:
        normalized_zoom = self._clamp_zoom(zoom)
        scene_width = float(self._viewport_rect.width()) / normalized_zoom
        scene_height = float(self._viewport_rect.height()) / normalized_zoom
        return scene_width, scene_height

    def _visible_scene_rect_for_state(
        self,
        *,
        zoom: float | None = None,
        center_x: float | None = None,
        center_y: float | None = None,
    ) -> QRectF:
        resolved_zoom = self._zoom if zoom is None else self._clamp_zoom(zoom)
        resolved_center_x = self._center_x if center_x is None else float(center_x)
        resolved_center_y = self._center_y if center_y is None else float(center_y)
        scene_width, scene_height = self._scene_dimensions_for_zoom(resolved_zoom)
        return QRectF(
            resolved_center_x - (scene_width * 0.5),
            resolved_center_y - (scene_height * 0.5),
            scene_width,
            scene_height,
        )

    def _refresh_visible_scene_rect_cache(self, *, emit_node_activation_changed: bool = True) -> None:
        self._visible_scene_rect = self._visible_scene_rect_for_state()
        self._visible_scene_rect_payload = self._rect_payload(self._visible_scene_rect)
        next_activation_rect = bucketed_hysteresis_visible_scene_rect(
            self._visible_scene_rect_payload,
            zoom=self._zoom,
            hysteresis_padding_px=DEFAULT_VIEWPORT_MODEL_HYSTERESIS_PADDING_PX,
            bucket_px=DEFAULT_VIEWPORT_MODEL_BUCKET_PX,
        )
        if rects_equal(self._node_render_activation_scene_rect, next_activation_rect):
            return
        self._node_render_activation_scene_rect = next_activation_rect
        self._node_render_activation_scene_rect_payload = scene_rect_payload(next_activation_rect)
        if emit_node_activation_changed:
            self.node_render_activation_scene_rect_changed.emit()

    def scene_point_for_viewport_point(self, viewport_x: float, viewport_y: float, *, zoom: float | None = None) -> QPointF:
        resolved_zoom = self._zoom if zoom is None else self._clamp_zoom(zoom)
        half_width = float(self._viewport_rect.width()) * 0.5
        half_height = float(self._viewport_rect.height()) * 0.5
        return QPointF(
            self._center_x + ((float(viewport_x) - half_width) / resolved_zoom),
            self._center_y + ((float(viewport_y) - half_height) / resolved_zoom),
        )

    def _center_for_scene_anchor(self, scene_x: float, scene_y: float, viewport_x: float, viewport_y: float, *, zoom: float) -> QPointF:
        resolved_zoom = self._clamp_zoom(zoom)
        half_width = float(self._viewport_rect.width()) * 0.5
        half_height = float(self._viewport_rect.height()) * 0.5
        return QPointF(
            float(scene_x) - ((float(viewport_x) - half_width) / resolved_zoom),
            float(scene_y) - ((float(viewport_y) - half_height) / resolved_zoom),
        )

    @pyqtSlot(float, float, float, result=bool)
    def set_view_state(self, zoom: float, center_x: float, center_y: float) -> bool:
        clamped_zoom = self._clamp_zoom(zoom)
        next_center_x = float(center_x)
        next_center_y = float(center_y)
        if not math.isfinite(next_center_x) or not math.isfinite(next_center_y):
            return False

        zoom_changed = abs(self._zoom - clamped_zoom) >= 1e-6
        center_changed = (
            abs(self._center_x - next_center_x) >= 1e-6
            or abs(self._center_y - next_center_y) >= 1e-6
        )
        if not zoom_changed and not center_changed:
            return False

        self._zoom = clamped_zoom
        self._center_x = next_center_x
        self._center_y = next_center_y
        self._refresh_visible_scene_rect_cache()

        if zoom_changed:
            self.zoom_changed.emit(self._zoom)
        if center_changed:
            self.center_changed.emit(self._center_x, self._center_y)
        self.view_state_changed.emit()
        return True

    def set_zoom(self, zoom: float) -> None:
        self.set_view_state(zoom, self._center_x, self._center_y)

    @pyqtSlot(float)
    def adjust_zoom(self, factor: float) -> None:
        self.set_view_state(self._zoom * float(factor), self._center_x, self._center_y)

    @pyqtSlot(float, float, float, result=bool)
    def adjust_zoom_at_viewport_point(self, factor: float, viewport_x: float, viewport_y: float) -> bool:
        target_zoom = self._clamp_zoom(self._zoom * float(factor))
        anchor_scene_point = self.scene_point_for_viewport_point(viewport_x, viewport_y)
        anchored_center = self._center_for_scene_anchor(
            anchor_scene_point.x(),
            anchor_scene_point.y(),
            viewport_x,
            viewport_y,
            zoom=target_zoom,
        )
        return self.set_view_state(target_zoom, anchored_center.x(), anchored_center.y())

    def centerOn(self, x: float | QPointF, y: float | None = None) -> None:  # noqa: N802
        if isinstance(x, QPointF):
            cx = float(x.x())
            cy = float(x.y())
        elif y is None:
            cx = float(x)
            cy = self._center_y
        else:
            cx = float(x)
            cy = float(y)

        self.set_view_state(self._zoom, cx, cy)

    @pyqtSlot(float, float)
    def pan_by(self, delta_x: float, delta_y: float) -> None:
        self.set_view_state(self._zoom, self._center_x + float(delta_x), self._center_y + float(delta_y))

    def mapToScene(self, point) -> QPointF:  # noqa: ANN001, N802
        point_x = getattr(point, "x", None)
        point_y = getattr(point, "y", None)
        if point_x is None or point_y is None:
            return QPointF(self._center_x, self._center_y)
        viewport_x = point_x() if callable(point_x) else point_x
        viewport_y = point_y() if callable(point_y) else point_y
        if not math.isfinite(float(viewport_x)) or not math.isfinite(float(viewport_y)):
            return QPointF(self._center_x, self._center_y)
        return self.scene_point_for_viewport_point(float(viewport_x), float(viewport_y))

    def viewport(self) -> "ViewportBridge":
        return self

    def rect(self) -> QRect:
        return QRect(self._viewport_rect)

    def visible_scene_rect(self) -> QRectF:
        return QRectF(self._visible_scene_rect)

    def _rect_payload(self, rect: QRectF) -> dict[str, float]:
        normalized = QRectF(rect).normalized()
        return {
            "x": float(normalized.x()),
            "y": float(normalized.y()),
            "width": float(max(0.0, normalized.width())),
            "height": float(max(0.0, normalized.height())),
        }

    @pyqtSlot(result="QVariantMap")
    def visible_scene_rect_map(self) -> dict[str, float]:
        return dict(self._visible_scene_rect_payload)

    @pyqtSlot(float, result=float)
    def scene_padding_for_viewport_pixels(self, padding_px: float) -> float:
        return scene_padding_for_viewport_pixels(float(padding_px), self._zoom)

    @pyqtSlot("QVariantMap", float, result="QVariantMap")
    def inflate_scene_rect_payload(self, rect_like: object, padding: float) -> dict[str, float]:
        rect = visible_scene_rect(rect_like)
        if rect is None:
            return {}
        return scene_rect_payload(inflate_scene_rect(rect, float(padding)))

    @pyqtSlot(float, float)
    def center_on_scene_point(self, x: float, y: float) -> None:
        self.centerOn(float(x), float(y))

    def fit_zoom_for_scene_rect(self, scene_rect: QRectF, padding_px: float = FRAME_PADDING_PX) -> float:
        normalized = QRectF(scene_rect).normalized()
        width = max(1e-6, float(normalized.width()))
        height = max(1e-6, float(normalized.height()))
        padding = max(0.0, float(padding_px))
        viewport_width = max(1.0, float(self._viewport_rect.width()) - (padding * 2.0))
        viewport_height = max(1.0, float(self._viewport_rect.height()) - (padding * 2.0))
        fitted = min(viewport_width / width, viewport_height / height)
        return self._clamp_zoom(fitted)

    def center_on_scene_rect(self, scene_rect: QRectF) -> bool:
        normalized = QRectF(scene_rect).normalized()
        if not normalized.isValid():
            return False
        self.centerOn(normalized.center())
        return True

    def frame_scene_rect(self, scene_rect: QRectF, padding_px: float = FRAME_PADDING_PX) -> bool:
        normalized = QRectF(scene_rect).normalized()
        if not normalized.isValid():
            return False
        if normalized.width() <= 0.0 or normalized.height() <= 0.0:
            return False
        return self.set_view_state(
            self.fit_zoom_for_scene_rect(normalized, padding_px=padding_px),
            normalized.center().x(),
            normalized.center().y(),
        )

    @pyqtSlot(float, float, float, float, result=bool)
    @pyqtSlot(float, float, float, float, float, result=bool)
    def frame_scene_rect_payload(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        padding_px: float = FRAME_PADDING_PX,
    ) -> bool:
        return self.frame_scene_rect(
            QRectF(float(x), float(y), float(width), float(height)),
            padding_px=float(padding_px),
        )

    @pyqtSlot(float, float)
    def set_viewport_size(self, width: float, height: float) -> None:
        w = max(1, int(round(width)))
        h = max(1, int(round(height)))
        if self._viewport_rect.width() == w and self._viewport_rect.height() == h:
            return
        self._viewport_rect = QRect(0, 0, w, h)
        self._refresh_visible_scene_rect_cache()
        self.view_state_changed.emit()


__all__ = ["ViewportBridge"]
