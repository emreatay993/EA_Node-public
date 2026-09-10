from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QPointF, QRect, QRectF, Qt, QTimer, pyqtSlot
from PyQt6.QtQuick import QQuickItem
from PyQt6.QtWidgets import QWidget

from ea_node_editor.ui_qml.native_overlay_owners import VIEWER_SESSION_OVERLAY_OWNER

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
    from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

_OverlayKey = tuple[str, str]
_DEFAULT_OVERLAY_OWNER = "default"
_SYNC_MODE_FULL = "full"
_SYNC_MODE_TRANSFORM = "transform"
_TRANSFORM_ONLY_NODE_DELTA_REASONS = frozenset(
    {
        "history_node_position_delta",
        "node_position_delta",
        "node_resize_geometry_delta",
    }
)
_OVERLAY_VIEWPORT_PREFETCH_SCENE_PX = 256.0
_NATIVE_OVERLAY_INPUT_EVENTS = {
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease,
    QEvent.Type.MouseButtonDblClick,
    QEvent.Type.MouseMove,
    QEvent.Type.Wheel,
    QEvent.Type.ContextMenu,
    QEvent.Type.TouchBegin,
    QEvent.Type.TouchUpdate,
    QEvent.Type.TouchEnd,
    QEvent.Type.TouchCancel,
    QEvent.Type.TabletPress,
    QEvent.Type.TabletMove,
    QEvent.Type.TabletRelease,
    QEvent.Type.NativeGesture,
}


def _mapping(value: Any) -> dict[str, Any]:
    normalized = value.toVariant() if hasattr(value, "toVariant") else value
    if isinstance(normalized, Mapping):
        return dict(normalized)
    if hasattr(normalized, "items"):
        try:
            return dict(normalized.items())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _number(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return number


def _string(value: Any) -> str:
    return str(value).strip()


def _bool(value: Any) -> bool:
    return bool(value)


def _rect_payload(value: Any) -> dict[str, float]:
    payload = _mapping(value)
    return {
        "x": max(0.0, _number(payload.get("x"), 0.0)),
        "y": max(0.0, _number(payload.get("y"), 0.0)),
        "width": max(0.0, _number(payload.get("width"), 0.0)),
        "height": max(0.0, _number(payload.get("height"), 0.0)),
    }


def _aligned_rect(rect: QRectF) -> QRect:
    normalized = QRectF(rect).normalized()
    left = math.floor(normalized.left())
    top = math.floor(normalized.top())
    right = math.ceil(normalized.right())
    bottom = math.ceil(normalized.bottom())
    return QRect(
        int(left),
        int(top),
        max(0, int(right - left)),
        max(0, int(bottom - top)),
    )


@dataclass(slots=True, frozen=True)
class EmbeddedViewerOverlaySpec:
    workspace_id: str
    node_id: str
    session_id: str = ""
    visible: bool = True


@dataclass(slots=True, frozen=True)
class EmbeddedViewerExportOverlaySnapshot:
    owner: str
    workspace_id: str
    node_id: str
    session_id: str
    rect: QRectF


@dataclass(slots=True)
class _OverlayRecord:
    workspace_id: str
    node_id: str
    session_id: str
    container: QWidget
    overlay_widget: QWidget | None = None
    node_card_item: QQuickItem | None = None
    viewer_geometry_item: QQuickItem | None = None
    updates_suspended: bool = False
    fullscreen_target_active: bool = False
    geometry_retry_budget: int = 0
    geometry_ready: bool = False
    ready_geometry: QRect | None = None


def _empty_overlay_metrics() -> dict[str, int | float | str | bool]:
    return {
        "sync_mode": _SYNC_MODE_FULL,
        "total_count": 0,
        "visible_count": 0,
        "hidden_count": 0,
        "skipped_offscreen_count": 0,
        "sync_ms": 0.0,
        "geometry_only_updates": 0,
        "content_updates": 0,
        "skipped_delta_sync_count": 0,
    }


class _OverlayGeometryService:
    def __init__(
        self,
        *,
        view_bridge_provider: Callable[[], "ViewportBridge | None"],
    ) -> None:
        self._view_bridge_provider = view_bridge_provider

    def overlay_geometry(
        self,
        *,
        root_item: QQuickItem,
        graph_canvas_item: QQuickItem,
        node_payload: Mapping[str, Any],
        node_card_item: QQuickItem | None = None,
        viewer_viewport_item: QQuickItem | None = None,
    ) -> QRect | None:
        canvas_origin = graph_canvas_item.mapToItem(root_item, QPointF(0.0, 0.0))
        canvas_width = max(0.0, _number(graph_canvas_item.width(), 0.0))
        canvas_height = max(0.0, _number(graph_canvas_item.height(), 0.0))
        if canvas_width <= 0.0 or canvas_height <= 0.0:
            return None
        scene_geometry = self.node_scene_geometry(
            graph_canvas_item,
            node_payload,
            node_card_item=node_card_item,
        )
        node_local_rect = self.viewer_viewport_local_rect(
            node_card_item=node_card_item,
            viewer_viewport_item=viewer_viewport_item,
        )
        return self.overlay_geometry_from_scene(
            canvas_origin=canvas_origin,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            node_payload=node_payload,
            scene_geometry=scene_geometry,
            node_local_rect=node_local_rect,
        )

    def overlay_geometry_from_scene(
        self,
        *,
        canvas_origin: QPointF,
        canvas_width: float,
        canvas_height: float,
        node_payload: Mapping[str, Any],
        scene_geometry: Mapping[str, Any],
        node_local_rect: Mapping[str, Any] | None = None,
    ) -> QRect | None:
        view_bridge = self._view_bridge_provider()
        zoom_value = max(1e-6, _number(getattr(view_bridge, "zoom_value", 1.0), 1.0))
        center_x = _number(getattr(view_bridge, "center_x", 0.0), 0.0)
        center_y = _number(getattr(view_bridge, "center_y", 0.0), 0.0)
        live_rect = (
            _rect_payload(node_local_rect)
            if node_local_rect is not None
            else self.viewer_live_rect(
                node_payload,
                scene_width=_number(scene_geometry.get("width"), 0.0),
                scene_height=_number(scene_geometry.get("height"), 0.0),
            )
        )
        if live_rect["width"] <= 0.0 or live_rect["height"] <= 0.0:
            return None

        rect = QRectF(
            canvas_origin.x() + (canvas_width * 0.5) + ((_number(scene_geometry.get("x"), 0.0) + live_rect["x"] - center_x) * zoom_value),
            canvas_origin.y() + (canvas_height * 0.5) + ((_number(scene_geometry.get("y"), 0.0) + live_rect["y"] - center_y) * zoom_value),
            live_rect["width"] * zoom_value,
            live_rect["height"] * zoom_value,
        )
        if rect.width() <= 0.0 or rect.height() <= 0.0:
            return None

        canvas_rect = QRectF(canvas_origin.x(), canvas_origin.y(), canvas_width, canvas_height)
        if not rect.intersects(canvas_rect):
            return None
        clipped_rect = rect.intersected(canvas_rect)
        if clipped_rect.width() <= 0.0 or clipped_rect.height() <= 0.0:
            return None
        return _aligned_rect(clipped_rect)

    @staticmethod
    def viewer_viewport_local_rect(
        *,
        node_card_item: QQuickItem | None,
        viewer_viewport_item: QQuickItem | None,
    ) -> dict[str, float] | None:
        if not isinstance(node_card_item, QQuickItem) or not isinstance(viewer_viewport_item, QQuickItem):
            return None
        if not viewer_viewport_item.isVisible():
            return None
        viewport_width = max(0.0, _number(viewer_viewport_item.width(), 0.0))
        viewport_height = max(0.0, _number(viewer_viewport_item.height(), 0.0))
        if viewport_width <= 0.0 or viewport_height <= 0.0:
            return None
        top_left = viewer_viewport_item.mapToItem(node_card_item, QPointF(0.0, 0.0))
        bottom_right = viewer_viewport_item.mapToItem(node_card_item, QPointF(viewport_width, viewport_height))
        rect = QRectF(top_left, bottom_right).normalized()
        if rect.width() <= 0.0 or rect.height() <= 0.0:
            return None
        return {
            "x": max(0.0, float(rect.x())),
            "y": max(0.0, float(rect.y())),
            "width": max(0.0, float(rect.width())),
            "height": max(0.0, float(rect.height())),
        }

    @staticmethod
    def overlay_geometry_from_viewport_item(
        *,
        root_item: QQuickItem,
        graph_canvas_item: QQuickItem,
        viewer_viewport_item: QQuickItem,
    ) -> QRect | None:
        if not viewer_viewport_item.isVisible():
            return None
        viewport_width = max(0.0, _number(viewer_viewport_item.width(), 0.0))
        viewport_height = max(0.0, _number(viewer_viewport_item.height(), 0.0))
        if viewport_width <= 0.0 or viewport_height <= 0.0:
            return None
        top_left = viewer_viewport_item.mapToItem(root_item, QPointF(0.0, 0.0))
        bottom_right = viewer_viewport_item.mapToItem(root_item, QPointF(viewport_width, viewport_height))
        rect = QRectF(top_left, bottom_right).normalized()
        if rect.width() <= 0.0 or rect.height() <= 0.0:
            return None
        canvas_origin = graph_canvas_item.mapToItem(root_item, QPointF(0.0, 0.0))
        canvas_rect = QRectF(
            canvas_origin.x(),
            canvas_origin.y(),
            max(0.0, _number(graph_canvas_item.width(), 0.0)),
            max(0.0, _number(graph_canvas_item.height(), 0.0)),
        )
        if not rect.intersects(canvas_rect):
            return None
        clipped_rect = rect.intersected(canvas_rect)
        if clipped_rect.width() <= 0.0 or clipped_rect.height() <= 0.0:
            return None
        return _aligned_rect(clipped_rect)

    @staticmethod
    def content_fullscreen_geometry(
        *,
        root_item: QQuickItem,
        viewer_viewport_item: QQuickItem | None,
    ) -> QRect | None:
        if not isinstance(viewer_viewport_item, QQuickItem) or not viewer_viewport_item.isVisible():
            return None
        viewport_width = max(0.0, _number(viewer_viewport_item.width(), 0.0))
        viewport_height = max(0.0, _number(viewer_viewport_item.height(), 0.0))
        if viewport_width <= 0.0 or viewport_height <= 0.0:
            return None
        top_left = viewer_viewport_item.mapToItem(root_item, QPointF(0.0, 0.0))
        bottom_right = viewer_viewport_item.mapToItem(root_item, QPointF(viewport_width, viewport_height))
        rect = QRectF(top_left, bottom_right).normalized()
        root_rect = QRectF(
            0.0,
            0.0,
            max(0.0, _number(root_item.width(), 0.0)),
            max(0.0, _number(root_item.height(), 0.0)),
        )
        if root_rect.width() <= 0.0 or root_rect.height() <= 0.0 or not rect.intersects(root_rect):
            return None
        clipped_rect = rect.intersected(root_rect)
        if clipped_rect.width() <= 0.0 or clipped_rect.height() <= 0.0:
            return None
        return _aligned_rect(clipped_rect)

    @staticmethod
    def node_scene_geometry(
        graph_canvas_item: QQuickItem,
        node_payload: Mapping[str, Any],
        *,
        node_card_item: QQuickItem | None = None,
    ) -> dict[str, float | bool]:
        node_id = _string(node_payload.get("node_id"))
        scene_x = _number(node_payload.get("x"), 0.0)
        scene_y = _number(node_payload.get("y"), 0.0)
        scene_width = max(0.0, _number(node_payload.get("width"), 0.0))
        scene_height = max(0.0, _number(node_payload.get("height"), 0.0))

        live_geometry_by_id = _mapping(graph_canvas_item.property("liveNodeGeometry"))
        live_geometry = _mapping(live_geometry_by_id.get(node_id))
        if live_geometry:
            return {
                "x": _number(live_geometry.get("x"), scene_x),
                "y": _number(live_geometry.get("y"), scene_y),
                "width": max(0.0, _number(live_geometry.get("width"), scene_width)),
                "height": max(0.0, _number(live_geometry.get("height"), scene_height)),
                "has_live_preview": True,
            }

        live_drag_node_lookup = _mapping(graph_canvas_item.property("liveDragNodeLookup"))
        node_is_dragged = bool(live_drag_node_lookup.get(node_id))
        live_drag_dx = (
            _number(graph_canvas_item.property("liveDragDx"), 0.0) if node_is_dragged else 0.0
        )
        live_drag_dy = (
            _number(graph_canvas_item.property("liveDragDy"), 0.0) if node_is_dragged else 0.0
        )
        scene_geometry: dict[str, float | bool] = {
            "x": scene_x + live_drag_dx,
            "y": scene_y + live_drag_dy,
            "width": scene_width,
            "height": scene_height,
            "has_live_preview": node_is_dragged,
        }
        if bool(scene_geometry.get("has_live_preview")):
            return scene_geometry

        rendered_geometry = _OverlayGeometryService.node_card_scene_geometry(
            node_card_item,
            fallback_geometry=scene_geometry,
        )
        return rendered_geometry or scene_geometry

    @staticmethod
    def node_card_scene_geometry(
        node_card_item: QQuickItem | None,
        *,
        fallback_geometry: Mapping[str, Any],
    ) -> dict[str, float | bool] | None:
        if not isinstance(node_card_item, QQuickItem):
            return None
        fallback_x = _number(fallback_geometry.get("x"), 0.0)
        fallback_y = _number(fallback_geometry.get("y"), 0.0)
        fallback_width = max(0.0, _number(fallback_geometry.get("width"), 0.0))
        fallback_height = max(0.0, _number(fallback_geometry.get("height"), 0.0))

        if _bool(node_card_item.property("_liveGeometryActive")):
            return {
                "x": _number(node_card_item.property("_liveX"), fallback_x),
                "y": _number(node_card_item.property("_liveY"), fallback_y),
                "width": max(0.0, _number(node_card_item.property("_liveWidth"), fallback_width)),
                "height": max(0.0, _number(node_card_item.property("_liveHeight"), fallback_height)),
                "has_live_preview": True,
            }

        world_offset = _number(node_card_item.property("worldOffset"), 0.0)
        rendered_width = max(0.0, _number(node_card_item.width(), fallback_width))
        rendered_height = max(0.0, _number(node_card_item.height(), fallback_height))
        if rendered_width <= 0.0 and fallback_width > 0.0:
            rendered_width = fallback_width
        if rendered_height <= 0.0 and fallback_height > 0.0:
            rendered_height = fallback_height

        live_drag_dx = _number(node_card_item.property("liveDragDx"), 0.0)
        live_drag_dy = _number(node_card_item.property("liveDragDy"), 0.0)
        return {
            "x": _number(node_card_item.x(), fallback_x + world_offset) - world_offset + live_drag_dx,
            "y": _number(node_card_item.y(), fallback_y + world_offset) - world_offset + live_drag_dy,
            "width": rendered_width,
            "height": rendered_height,
            "has_live_preview": abs(live_drag_dx) >= 0.01 or abs(live_drag_dy) >= 0.01,
        }

    @staticmethod
    def viewer_live_rect(
        node_payload: Mapping[str, Any],
        *,
        scene_width: float,
        scene_height: float,
    ) -> dict[str, float]:
        viewer_surface = _mapping(node_payload.get("viewer_surface"))
        live_rect = _mapping(viewer_surface.get("live_rect"))
        payload_width = max(0.0, _number(node_payload.get("width"), 0.0))
        payload_height = max(0.0, _number(node_payload.get("height"), 0.0))
        live_size_matches_payload = (
            abs(scene_width - payload_width) < 1e-6
            and abs(scene_height - payload_height) < 1e-6
        )
        if live_rect and live_size_matches_payload:
            return _rect_payload(live_rect)
        body_rect = _mapping(viewer_surface.get("body_rect"))
        if body_rect and live_size_matches_payload:
            return _rect_payload(body_rect)

        surface_metrics = _mapping(node_payload.get("surface_metrics"))
        body_x = max(0.0, _number(surface_metrics.get("body_left_margin"), 0.0))
        body_y = max(0.0, _number(surface_metrics.get("body_top"), 0.0))
        ports = node_payload.get("ports")
        try:
            port_count = len(ports) if ports is not None else 0
        except TypeError:
            port_count = 0
        port_reserve = max(0.0, port_count * _number(surface_metrics.get("port_height"), 0.0))
        body_bottom_margin = max(0.0, _number(surface_metrics.get("body_bottom_margin"), 0.0))
        body_width = max(
            0.0,
            scene_width - body_x - max(0.0, _number(surface_metrics.get("body_right_margin"), 0.0)),
        )
        minimum_body_height = max(
            0.0,
            _number(surface_metrics.get("min_height"), 0.0) - body_y - port_reserve - body_bottom_margin,
        )
        available_body_height = max(
            0.0,
            scene_height - body_y - port_reserve - body_bottom_margin,
        )
        body_height = max(minimum_body_height, available_body_height)
        return {
            "x": body_x,
            "y": body_y,
            "width": body_width,
            "height": body_height,
        }


class _OverlayWidgetPresentationService:
    @staticmethod
    def apply_widget_geometry(widget: QWidget, geometry: QRect) -> bool:
        current_geometry = widget.geometry()
        if current_geometry == geometry:
            return False
        position_changed = current_geometry.topLeft() != geometry.topLeft()
        size_changed = current_geometry.size() != geometry.size()
        if position_changed and size_changed:
            widget.setGeometry(geometry)
        elif position_changed:
            widget.move(geometry.topLeft())
        elif size_changed:
            widget.resize(geometry.size())
        return True

    @classmethod
    def show_record(cls, record: _OverlayRecord, geometry: QRect, *, focus: bool = False) -> None:
        cls.apply_widget_geometry(record.container, geometry)
        widget = record.overlay_widget
        if widget is None:
            record.container.hide()
            return
        container_rect = record.container.rect()
        cls.apply_widget_geometry(widget, container_rect)
        container_was_hidden = not record.container.isVisible()
        widget_was_hidden = not widget.isVisible()
        if container_was_hidden:
            record.container.show()
        if widget_was_hidden:
            widget.show()
        if container_was_hidden or widget_was_hidden or focus:
            record.container.raise_()
        if focus:
            widget.setFocus(Qt.FocusReason.OtherFocusReason)

class EmbeddedViewerOverlayManager(QObject):
    def __init__(
        self,
        parent: QObject | None = None,
        *,
        quick_widget: Any,
        overlay_parent_widget: QWidget | None = None,
        event_filter_widget: QObject | None = None,
        shell_window: "ShellWindow | None" = None,
        scene_bridge: "GraphSceneBridge | None" = None,
        view_bridge: "ViewportBridge | None" = None,
    ) -> None:
        resolved_overlay_parent = overlay_parent_widget or (quick_widget if isinstance(quick_widget, QWidget) else None)
        resolved_event_filter = event_filter_widget or resolved_overlay_parent or quick_widget
        super().__init__(parent or resolved_overlay_parent or quick_widget)
        self._quick_widget = quick_widget
        self._overlay_parent_widget = resolved_overlay_parent
        self._event_filter_widget = resolved_event_filter
        self._shell_window = shell_window
        self._scene_bridge = scene_bridge
        self._view_bridge = view_bridge
        self._geometry_service = _OverlayGeometryService(
            view_bridge_provider=lambda: self._view_bridge,
        )
        self._observed_graph_canvas: QQuickItem | None = None
        self._desired_overlays: dict[_OverlayKey, EmbeddedViewerOverlaySpec] = {}
        self._desired_overlay_sources: dict[str, dict[_OverlayKey, EmbeddedViewerOverlaySpec]] = {}
        self._overlay_records: dict[_OverlayKey, _OverlayRecord] = {}
        self._content_fullscreen_target: _OverlayKey | None = None
        self._last_error = ""
        self._sync_queued = False
        self._queued_sync_mode: str | None = None
        self._syncing = False
        self._skipped_node_delta_sync_count = 0
        self._overlay_metrics = _empty_overlay_metrics()

        install_event_filter = getattr(self._event_filter_widget, "installEventFilter", None)
        if callable(install_event_filter):
            install_event_filter(self)
        self._connect_signals()
        self._schedule_sync()

    @property
    def quick_widget(self) -> Any:
        return self._quick_widget

    @property
    def overlay_parent_widget(self) -> QWidget | None:
        return self._overlay_parent_widget

    @property
    def event_filter_widget(self) -> QObject | None:
        return self._event_filter_widget

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def overlay_metrics(self) -> dict[str, int | float | str | bool]:
        return self.overlay_metrics_snapshot()

    def overlay_metrics_snapshot(self) -> dict[str, int | float | str | bool]:
        return dict(self._overlay_metrics)

    def set_active_overlays(self, overlays: Iterable[EmbeddedViewerOverlaySpec]) -> None:
        self.set_active_overlays_for_owner(_DEFAULT_OVERLAY_OWNER, overlays)

    def set_active_overlays_for_owner(
        self,
        owner: str,
        overlays: Iterable[EmbeddedViewerOverlaySpec],
    ) -> None:
        normalized_owner = _string(owner) or _DEFAULT_OVERLAY_OWNER
        desired_overlays: dict[_OverlayKey, EmbeddedViewerOverlaySpec] = {}
        for overlay in overlays:
            workspace_id = _string(getattr(overlay, "workspace_id", ""))
            node_id = _string(getattr(overlay, "node_id", ""))
            if not workspace_id or not node_id:
                continue
            desired_overlays[(workspace_id, node_id)] = EmbeddedViewerOverlaySpec(
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=_string(getattr(overlay, "session_id", "")),
                visible=bool(getattr(overlay, "visible", True)),
            )

        if desired_overlays:
            self._desired_overlay_sources[normalized_owner] = desired_overlays
        else:
            self._desired_overlay_sources.pop(normalized_owner, None)

        merged_desired_overlays: dict[_OverlayKey, EmbeddedViewerOverlaySpec] = {}
        for source_overlays in self._desired_overlay_sources.values():
            merged_desired_overlays.update(source_overlays)

        removed_keys = [key for key in self._overlay_records if key not in merged_desired_overlays]
        self._desired_overlays = merged_desired_overlays
        for key, overlay in merged_desired_overlays.items():
            self._ensure_record(key=key, session_id=overlay.session_id)
        for key in removed_keys:
            self._teardown_record(key)
        self._schedule_sync()

    def set_content_fullscreen_target(self, overlay: EmbeddedViewerOverlaySpec | None) -> None:
        next_target: _OverlayKey | None = None
        if overlay is not None:
            workspace_id = _string(getattr(overlay, "workspace_id", ""))
            node_id = _string(getattr(overlay, "node_id", ""))
            if workspace_id and node_id:
                next_target = (workspace_id, node_id)
        if next_target == self._content_fullscreen_target:
            return
        self._content_fullscreen_target = next_target
        for key, record in self._overlay_records.items():
            record.fullscreen_target_active = key == next_target
            if key == next_target:
                record.geometry_retry_budget = max(record.geometry_retry_budget, 3)
        self._schedule_sync()

    def overlay_widget(self, node_id: str, *, workspace_id: str = "") -> QWidget | None:
        resolved_workspace_id = _string(workspace_id) or self._active_workspace_id()
        record = self._overlay_records.get((resolved_workspace_id, _string(node_id)))
        if record is None:
            return None
        return record.overlay_widget

    def overlay_container(self, node_id: str, *, workspace_id: str = "") -> QWidget | None:
        resolved_workspace_id = _string(workspace_id) or self._active_workspace_id()
        record = self._overlay_records.get((resolved_workspace_id, _string(node_id)))
        if record is None:
            return None
        return record.container

    def overlay_geometry_ready(self, node_id: str, *, workspace_id: str = "") -> bool:
        resolved_workspace_id = _string(workspace_id) or self._active_workspace_id()
        record = self._overlay_records.get((resolved_workspace_id, _string(node_id)))
        if record is None or record.overlay_widget is None:
            return False
        return (
            record.geometry_ready
            and record.ready_geometry is not None
            and record.container.isVisible()
            and record.overlay_widget.isVisible()
            and record.container.geometry() == record.ready_geometry
            and record.container.width() > 0
            and record.container.height() > 0
            and record.overlay_widget.geometry() == record.container.rect()
        )

    def export_overlay_snapshots(self) -> tuple[EmbeddedViewerExportOverlaySnapshot, ...]:
        if not self._syncing:
            self.sync()
        root_item = self._root_item()
        graph_canvas_item = self._graph_canvas_item(root_item)
        if root_item is None or graph_canvas_item is None:
            return ()
        canvas_origin = graph_canvas_item.mapToItem(root_item, QPointF(0.0, 0.0))
        canvas_rect = QRectF(
            canvas_origin.x(),
            canvas_origin.y(),
            float(graph_canvas_item.width()),
            float(graph_canvas_item.height()),
        )
        if canvas_rect.width() <= 0.0 or canvas_rect.height() <= 0.0:
            return ()

        owners_by_key = self._overlay_owners_by_key()
        snapshots: list[EmbeddedViewerExportOverlaySnapshot] = []
        for key, record in self._overlay_records.items():
            if record.overlay_widget is None or record.ready_geometry is None:
                continue
            if not self.overlay_geometry_ready(record.node_id, workspace_id=record.workspace_id):
                continue
            root_rect = QRectF(record.ready_geometry)
            clipped_rect = root_rect.intersected(canvas_rect)
            if clipped_rect.width() <= 0.0 or clipped_rect.height() <= 0.0:
                continue
            snapshots.append(
                EmbeddedViewerExportOverlaySnapshot(
                    owner=owners_by_key.get(key, _DEFAULT_OVERLAY_OWNER),
                    workspace_id=record.workspace_id,
                    node_id=record.node_id,
                    session_id=record.session_id,
                    rect=QRectF(
                        clipped_rect.x() - canvas_origin.x(),
                        clipped_rect.y() - canvas_origin.y(),
                        clipped_rect.width(),
                        clipped_rect.height(),
                    ),
                )
            )
        return tuple(snapshots)

    def attach_overlay_widget(self, node_id: str, widget: QWidget, *, workspace_id: str = "") -> bool:
        resolved_workspace_id = _string(workspace_id) or self._active_workspace_id()
        normalized_node_id = _string(node_id)
        if not resolved_workspace_id or not normalized_node_id:
            self._last_error = "workspace_id and node_id are required to attach an overlay widget."
            return False
        record = self._overlay_records.get((resolved_workspace_id, normalized_node_id))
        if record is None:
            record = self._ensure_record(
                key=(resolved_workspace_id, normalized_node_id),
                session_id="",
            )
        if record is None:
            self._last_error = "Unable to create overlay container."
            return False
        if record.overlay_widget is widget:
            self._last_error = ""
            self._schedule_sync()
            return True
        if record.overlay_widget is not None:
            self._teardown_widget(record.overlay_widget)
        if widget.parent() is not record.container:
            widget.setParent(record.container)
        if not widget.objectName():
            widget.setObjectName(f"embeddedViewerWidget::{resolved_workspace_id}::{normalized_node_id}")
        record.overlay_widget = widget
        record.viewer_geometry_item = None
        record.geometry_retry_budget = 3
        record.geometry_ready = False
        record.ready_geometry = None
        widget.setGeometry(record.container.rect())
        if not _bool(widget.property("ea.plotLiveOverlay")):
            overlay_parent = self._overlay_parent_widget
            parent_visible = overlay_parent.isVisible() if overlay_parent is not None else True
            if record.container.width() > 0 and record.container.height() > 0 and parent_visible:
                record.container.show()
                widget.show()
                record.container.raise_()
        self._last_error = ""
        self._schedule_sync()
        return True

    def detach_overlay_widget(self, node_id: str, *, workspace_id: str = "") -> None:
        resolved_workspace_id = _string(workspace_id) or self._active_workspace_id()
        record = self._overlay_records.get((resolved_workspace_id, _string(node_id)))
        if record is None or record.overlay_widget is None:
            return
        widget = record.overlay_widget
        record.overlay_widget = None
        self._teardown_widget(widget)
        self._schedule_sync()

    def take_overlay_widget(self, node_id: str, *, workspace_id: str = "") -> QWidget | None:
        resolved_workspace_id = _string(workspace_id) or self._active_workspace_id()
        record = self._overlay_records.get((resolved_workspace_id, _string(node_id)))
        if record is None or record.overlay_widget is None:
            return None
        widget = record.overlay_widget
        self._set_widget_updates_suspended(record, False)
        record.overlay_widget = None
        record.fullscreen_target_active = False
        record.geometry_ready = False
        record.ready_geometry = None
        record.container.hide()
        self._schedule_sync()
        return widget

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if watched is self._event_filter_widget and event is not None:
            event_type = event.type()
            if event_type in _NATIVE_OVERLAY_INPUT_EVENTS and self._event_hits_visible_native_overlay(event):
                accept = getattr(event, "accept", None)
                if callable(accept):
                    accept()
                return True
            if event_type in {
                QEvent.Type.Show,
                QEvent.Type.Resize,
                QEvent.Type.Move,
                QEvent.Type.LayoutRequest,
                QEvent.Type.WindowStateChange,
            }:
                graph_canvas_item = self._graph_canvas_item(self._root_item())
                if (
                    graph_canvas_item is None
                    or not self._native_overlay_suppression_active(graph_canvas_item)
                ):
                    self._schedule_sync()
            elif event_type == QEvent.Type.Hide:
                self._hide_all_records()
            elif event_type == QEvent.Type.Close:
                self._clear_records()
        return super().eventFilter(watched, event)

    @staticmethod
    def _quick_event_position(event: QEvent) -> object | None:
        for accessor_name in ("position", "pos"):
            accessor = getattr(event, accessor_name, None)
            if not callable(accessor):
                continue
            try:
                value = accessor()
            except Exception:  # noqa: BLE001
                continue
            to_point = getattr(value, "toPoint", None)
            return to_point() if callable(to_point) else value
        return None

    def _event_hits_visible_native_overlay(self, event: QEvent) -> bool:
        position = self._quick_event_position(event)
        if position is None:
            return False
        for record in self._overlay_records.values():
            widget = record.overlay_widget
            if widget is None or not _bool(widget.property("ea.nativeWindowOverlay")):
                continue
            if record.container.isVisible() and record.container.geometry().contains(position):
                return True
        return False

    def _connect_signals(self) -> None:
        self._connect_signal(self._quick_widget, "statusChanged", self._on_quick_widget_status_changed)
        self._connect_signal(self._scene_bridge, "nodes_changed", self._on_scene_nodes_changed)
        self._connect_signal(self._scene_bridge, "workspace_changed", self._schedule_sync)
        self._connect_signal(self._view_bridge, "view_state_changed", self._schedule_transform_sync)

    def _on_scene_nodes_changed(self) -> None:
        source = getattr(self._scene_bridge, "state_bridge", self._scene_bridge)
        delta = _mapping(getattr(source, "node_delta_payload", {}))
        if _string(delta.get("kind")) != "node_delta":
            self._schedule_sync()
            return

        affected_node_ids = {
            _string(payload.get("node_id"))
            for collection_name in ("nodes", "backdrop_nodes")
            for payload in (_mapping(item) for item in (delta.get(collection_name) or ()))
            if _string(payload.get("node_id"))
        }
        affected_node_ids.update(
            _string(node_id)
            for collection_name in ("added_node_ids", "removed_node_ids")
            for node_id in (delta.get(collection_name) or ())
            if _string(node_id)
        )
        if not affected_node_ids:
            self._schedule_sync()
            return
        desired_node_ids = {node_id for _workspace_id, node_id in self._desired_overlays}
        if affected_node_ids.isdisjoint(desired_node_ids):
            self._skipped_node_delta_sync_count += 1
            self._overlay_metrics["skipped_delta_sync_count"] = self._skipped_node_delta_sync_count
            return

        if _string(delta.get("reason")) in _TRANSFORM_ONLY_NODE_DELTA_REASONS:
            self._schedule_transform_sync()
            return
        self._schedule_sync()

    @staticmethod
    def _connect_signal(source: object | None, name: str, slot) -> None:  # noqa: ANN001
        signal = getattr(source, name, None) if source is not None else None
        if signal is not None and hasattr(signal, "connect"):
            signal.connect(slot)

    def _on_quick_widget_status_changed(self, _status) -> None:  # noqa: ANN001
        self._schedule_sync()

    def _schedule_sync(self) -> None:
        graph_canvas_item = self._graph_canvas_item(self._root_item())
        native_only = bool(self._desired_overlays) and all(
            (record := self._overlay_records.get(key)) is not None
            and self._record_uses_native_window_overlay(record)
            for key in self._desired_overlays
        )
        if (
            self._content_fullscreen_target is None
            and native_only
            and graph_canvas_item is not None
            and self._native_overlay_suppression_active(graph_canvas_item)
        ):
            self._queue_sync(_SYNC_MODE_TRANSFORM)
            return
        self._queue_sync(_SYNC_MODE_FULL)

    def _schedule_transform_sync(self) -> None:
        self._queue_sync(_SYNC_MODE_TRANSFORM)

    def _queue_sync(self, sync_mode: str) -> None:
        normalized_mode = _SYNC_MODE_TRANSFORM if sync_mode == _SYNC_MODE_TRANSFORM else _SYNC_MODE_FULL
        if self._sync_queued:
            if normalized_mode == _SYNC_MODE_FULL:
                self._queued_sync_mode = _SYNC_MODE_FULL
            return
        self._sync_queued = True
        self._queued_sync_mode = normalized_mode
        QTimer.singleShot(0, self._run_queued_sync)

    @pyqtSlot()
    def _sync_immediately(self) -> None:
        if self._syncing:
            self._schedule_sync()
            return
        self._sync_queued = False
        self._queued_sync_mode = None
        self.sync()

    @pyqtSlot()
    def _run_queued_sync(self) -> None:
        sync_mode = self._queued_sync_mode or _SYNC_MODE_FULL
        if self._syncing:
            self._sync_queued = False
            self._queued_sync_mode = None
            self._queue_sync(sync_mode)
            return
        self._sync_queued = False
        self._queued_sync_mode = None
        if sync_mode == _SYNC_MODE_TRANSFORM:
            self.sync_transform_only()
        else:
            self.sync()

    def _active_workspace_id(self) -> str:
        if self._scene_bridge is not None:
            return _string(getattr(self._scene_bridge, "workspace_id", ""))
        return ""

    @pyqtSlot()
    def sync(self) -> None:
        if self._syncing:
            self._schedule_sync()
            return
        self._syncing = True
        try:
            self._sync_impl(transform_only=False)
        finally:
            self._syncing = False

    def sync_transform_only(self) -> None:
        if self._syncing:
            self._schedule_transform_sync()
            return
        self._syncing = True
        try:
            self._sync_impl(transform_only=True)
        finally:
            self._syncing = False

    def _sync_impl(self, *, transform_only: bool = False) -> None:
        started = time.perf_counter()
        metrics = _empty_overlay_metrics()
        metrics["sync_mode"] = _SYNC_MODE_TRANSFORM if transform_only else _SYNC_MODE_FULL
        metrics["total_count"] = len(self._desired_overlays)
        metrics["skipped_delta_sync_count"] = self._skipped_node_delta_sync_count
        try:
            root_item = self._root_item()
            graph_canvas_item = self._ensure_graph_canvas_observed(root_item)
            if root_item is None or graph_canvas_item is None:
                self._hide_all_records()
                metrics["hidden_count"] = len(self._overlay_records)
                return

            if not self._desired_overlays:
                self._clear_records()
                return

            if self._native_overlay_suppression_active(graph_canvas_item):
                suppressed_keys = {
                    key
                    for key in self._desired_overlays
                    if key != self._content_fullscreen_target
                    and (record := self._overlay_records.get(key)) is not None
                    and self._record_uses_native_window_overlay(record)
                }
                for key in suppressed_keys:
                    record = self._overlay_records[key]
                    record.fullscreen_target_active = False
                    self._set_widget_updates_suspended(record, True)
                    self._hide_record(key)
                if suppressed_keys == set(self._desired_overlays):
                    metrics["hidden_count"] = len(suppressed_keys)
                    return

            node_payloads = self._node_payloads_by_id(
                {node_id for _workspace_id, node_id in self._desired_overlays}
            )
            managed_keys = set(self._desired_overlays)
            fullscreen_target = self._content_fullscreen_target if self._content_fullscreen_target in managed_keys else None
            viewport_scene_rect = self._expanded_viewport_scene_rect(graph_canvas_item)
            for key, overlay in self._desired_overlays.items():
                record = self._ensure_record(
                    key=key,
                    session_id=overlay.session_id,
                )
                if record is None:
                    continue
                if not overlay.visible:
                    record.fullscreen_target_active = False
                    self._set_widget_updates_suspended(record, True)
                    self._hide_record(key)
                    metrics["hidden_count"] = int(metrics["hidden_count"]) + 1
                    continue
                node_payload = node_payloads.get(key[1])
                if node_payload is None or _bool(node_payload.get("collapsed")):
                    self._teardown_record(key)
                    metrics["hidden_count"] = int(metrics["hidden_count"]) + 1
                    continue
                if (
                    key != fullscreen_target
                    and self._record_uses_native_window_overlay(record)
                    and self._native_overlay_suppression_active(graph_canvas_item)
                ):
                    record.fullscreen_target_active = False
                    self._set_widget_updates_suspended(record, True)
                    self._hide_record(key)
                    metrics["hidden_count"] = int(metrics["hidden_count"]) + 1
                    continue

                cached_node_card_item = record.node_card_item if self._is_alive_item(record.node_card_item) else None
                cached_viewer_viewport_item = (
                    record.viewer_geometry_item if self._is_alive_item(record.viewer_geometry_item) else None
                )
                if key != fullscreen_target and self._overlay_is_outside_expanded_viewport(
                    graph_canvas_item=graph_canvas_item,
                    node_payload=node_payload,
                    viewport_scene_rect=viewport_scene_rect,
                    node_card_item=cached_node_card_item,
                    viewer_viewport_item=cached_viewer_viewport_item,
                ):
                    record.fullscreen_target_active = False
                    self._set_widget_updates_suspended(record, False)
                    self._hide_record(key)
                    metrics["hidden_count"] = int(metrics["hidden_count"]) + 1
                    metrics["skipped_offscreen_count"] = int(metrics["skipped_offscreen_count"]) + 1
                    continue

                node_card_item, viewer_viewport_item = self._overlay_items(
                    record,
                    graph_canvas_item,
                    cached_only=transform_only,
                )
                if viewer_viewport_item is None or viewer_viewport_item.objectName() != "graphNodeViewerViewport":
                    if transform_only:
                        self._schedule_sync()
                    elif record.overlay_widget is not None and record.geometry_retry_budget > 0:
                        record.geometry_retry_budget -= 1
                        self._schedule_sync()
                else:
                    record.geometry_retry_budget = 0
                self._ensure_overlay_chain_polished(viewer_viewport_item or node_card_item)
                self._observe_overlay_geometry_chain(node_card_item, viewer_viewport_item)

                fullscreen_viewport_item = (
                    self._content_fullscreen_viewport_item(root_item)
                    if key == fullscreen_target
                    else None
                )
                if fullscreen_viewport_item is not None:
                    self._observe_overlay_geometry_item(fullscreen_viewport_item)
                    self._ensure_overlay_chain_polished(fullscreen_viewport_item)
                plot_live_overlay = record.overlay_widget is not None and _bool(
                    record.overlay_widget.property("ea.plotLiveOverlay")
                )
                fullscreen_geometry = self._content_fullscreen_geometry(
                    root_item=root_item,
                    viewer_viewport_item=fullscreen_viewport_item,
                )
                record.fullscreen_target_active = fullscreen_geometry is not None
                plot_fullscreen_waiting_for_viewport = (
                    key == fullscreen_target
                    and plot_live_overlay
                    and fullscreen_geometry is None
                )
                if plot_fullscreen_waiting_for_viewport and record.geometry_retry_budget > 0:
                    record.geometry_retry_budget -= 1
                    self._schedule_sync()
                geometry = (
                    None
                    if plot_fullscreen_waiting_for_viewport
                    else fullscreen_geometry
                    or self._overlay_geometry(
                        root_item=root_item,
                        graph_canvas_item=graph_canvas_item,
                        node_payload=node_payload,
                        node_card_item=node_card_item,
                        viewer_viewport_item=viewer_viewport_item,
                    )
                )
                live_preview_active = (
                    False
                    if record.fullscreen_target_active
                    else self._overlay_live_preview_active(node_card_item, node_payload, graph_canvas_item)
                )
                native_window_overlay = self._record_uses_native_window_overlay(record)
                direct_viewport_geometry = None
                if (
                    plot_live_overlay
                    and key != fullscreen_target
                    and not record.fullscreen_target_active
                    and viewer_viewport_item is not None
                    and viewer_viewport_item.objectName() == "graphNodeViewerViewport"
                ):
                    direct_viewport_geometry = self._overlay_geometry_from_viewport_item(
                        root_item=root_item,
                        graph_canvas_item=graph_canvas_item,
                        viewer_viewport_item=viewer_viewport_item,
                    )
                    geometry = direct_viewport_geometry
                exact_viewport_geometry = (
                    record.fullscreen_target_active
                    or direct_viewport_geometry is not None
                )
                self._set_widget_updates_suspended(
                    record,
                    (
                        False
                        if (
                            record.fullscreen_target_active
                            or native_window_overlay
                            or plot_live_overlay
                        )
                        else live_preview_active
                    ),
                )
                if geometry is None:
                    record.fullscreen_target_active = False
                    record.geometry_ready = False
                    record.ready_geometry = None
                    self._hide_record(key)
                    metrics["hidden_count"] = int(metrics["hidden_count"]) + 1
                    continue
                if plot_live_overlay and not exact_viewport_geometry:
                    record.geometry_ready = False
                    record.ready_geometry = None
                    self._hide_record(key)
                    metrics["hidden_count"] = int(metrics["hidden_count"]) + 1
                    continue
                if native_window_overlay and not record.fullscreen_target_active and (
                    live_preview_active or self._canvas_interaction_active(graph_canvas_item)
                ):
                    record.geometry_ready = False
                    record.ready_geometry = None
                    self._hide_record(key)
                    metrics["hidden_count"] = int(metrics["hidden_count"]) + 1
                    continue

                self._show_record(record, geometry, focus=record.fullscreen_target_active)
                record.geometry_ready = exact_viewport_geometry or not plot_live_overlay
                record.ready_geometry = QRect(geometry) if record.geometry_ready else None
                metrics["visible_count"] = int(metrics["visible_count"]) + 1
                if transform_only:
                    metrics["geometry_only_updates"] = int(metrics["geometry_only_updates"]) + 1
                else:
                    metrics["content_updates"] = int(metrics["content_updates"]) + 1

            for key in list(self._overlay_records):
                if key not in managed_keys:
                    self._teardown_record(key)
        finally:
            metrics["sync_ms"] = (time.perf_counter() - started) * 1000.0
            self._overlay_metrics = metrics

    def _root_item(self) -> QQuickItem | None:
        root_object = self._quick_widget.rootObject()
        return root_object if isinstance(root_object, QQuickItem) else None

    @staticmethod
    def _graph_canvas_item(root_item: QQuickItem | None) -> QQuickItem | None:
        if root_item is None:
            return None
        if root_item.objectName() == "graphCanvas":
            return root_item
        graph_canvas = root_item.findChild(QObject, "graphCanvas")
        return graph_canvas if isinstance(graph_canvas, QQuickItem) else None

    def _node_payloads_by_id(self, node_ids: set[str] | None = None) -> dict[str, dict[str, Any]]:
        payloads: dict[str, dict[str, Any]] = {}
        nodes_model = getattr(self._scene_bridge, "nodes_model", [])
        target_node_ids = {str(node_id) for node_id in node_ids or set() if str(node_id)}
        for payload in nodes_model if isinstance(nodes_model, list) else []:
            payload_map = _mapping(payload)
            node_id = _string(payload_map.get("node_id"))
            if not node_id:
                continue
            if target_node_ids and node_id not in target_node_ids:
                continue
            payloads[node_id] = payload_map
            if target_node_ids and len(payloads) >= len(target_node_ids):
                break
        return payloads

    def _expanded_viewport_scene_rect(self, graph_canvas_item: QQuickItem) -> QRectF | None:
        view_bridge = self._view_bridge
        payload = _mapping(getattr(view_bridge, "visible_scene_rect_payload_cached", {}))
        width = max(0.0, _number(payload.get("width"), 0.0))
        height = max(0.0, _number(payload.get("height"), 0.0))
        if width <= 0.0 or height <= 0.0:
            zoom_value = max(1e-6, _number(getattr(view_bridge, "zoom_value", 1.0), 1.0))
            canvas_width = max(0.0, _number(graph_canvas_item.width(), 0.0))
            canvas_height = max(0.0, _number(graph_canvas_item.height(), 0.0))
            if canvas_width <= 0.0 or canvas_height <= 0.0:
                return None
            width = canvas_width / zoom_value
            height = canvas_height / zoom_value
            x = _number(getattr(view_bridge, "center_x", 0.0), 0.0) - (width * 0.5)
            y = _number(getattr(view_bridge, "center_y", 0.0), 0.0) - (height * 0.5)
        else:
            x = _number(payload.get("x"), 0.0)
            y = _number(payload.get("y"), 0.0)
        expansion = max(_OVERLAY_VIEWPORT_PREFETCH_SCENE_PX, max(width, height) * 0.25)
        return QRectF(
            x - expansion,
            y - expansion,
            width + (expansion * 2.0),
            height + (expansion * 2.0),
        )

    def _overlay_is_outside_expanded_viewport(
        self,
        *,
        graph_canvas_item: QQuickItem,
        node_payload: Mapping[str, Any],
        viewport_scene_rect: QRectF | None,
        node_card_item: QQuickItem | None = None,
        viewer_viewport_item: QQuickItem | None = None,
    ) -> bool:
        if viewport_scene_rect is None or viewport_scene_rect.width() <= 0.0 or viewport_scene_rect.height() <= 0.0:
            return False
        overlay_scene_rect = self._overlay_scene_rect(
            graph_canvas_item=graph_canvas_item,
            node_payload=node_payload,
            node_card_item=node_card_item,
            viewer_viewport_item=viewer_viewport_item,
        )
        return overlay_scene_rect is not None and not overlay_scene_rect.intersects(viewport_scene_rect)

    def _overlay_scene_rect(
        self,
        *,
        graph_canvas_item: QQuickItem,
        node_payload: Mapping[str, Any],
        node_card_item: QQuickItem | None = None,
        viewer_viewport_item: QQuickItem | None = None,
    ) -> QRectF | None:
        scene_geometry = self._node_scene_geometry(
            graph_canvas_item,
            node_payload,
            node_card_item=node_card_item,
        )
        node_local_rect = _OverlayGeometryService.viewer_viewport_local_rect(
            node_card_item=node_card_item,
            viewer_viewport_item=viewer_viewport_item,
        )
        live_rect = (
            _rect_payload(node_local_rect)
            if node_local_rect is not None
            else self._viewer_live_rect(
                node_payload,
                scene_width=_number(scene_geometry.get("width"), 0.0),
                scene_height=_number(scene_geometry.get("height"), 0.0),
            )
        )
        if live_rect["width"] <= 0.0 or live_rect["height"] <= 0.0:
            return None
        return QRectF(
            _number(scene_geometry.get("x"), 0.0) + live_rect["x"],
            _number(scene_geometry.get("y"), 0.0) + live_rect["y"],
            live_rect["width"],
            live_rect["height"],
        )

    def _walk_items(self, item: QQuickItem | None):
        if not isinstance(item, QQuickItem):
            return
        yield item
        for child in item.childItems():
            if isinstance(child, QQuickItem):
                yield from self._walk_items(child)

    def _node_card_item(self, graph_canvas_item: QQuickItem, node_id: str) -> QQuickItem | None:
        normalized_node_id = _string(node_id)
        if not normalized_node_id:
            return None
        for item in self._walk_items(graph_canvas_item):
            if item.objectName() != "graphNodeCard":
                continue
            node_data = _mapping(item.property("nodeData"))
            if _string(node_data.get("node_id")) == normalized_node_id:
                return item
        return None

    def _viewer_geometry_item(self, node_card_item: QQuickItem | None) -> QQuickItem | None:
        if not isinstance(node_card_item, QQuickItem):
            return None
        body_frame_item: QQuickItem | None = None
        for item in self._walk_items(node_card_item):
            object_name = item.objectName()
            if object_name == "graphNodeViewerViewport":
                return item
            if object_name == "graphNodeViewerBodyFrame" and body_frame_item is None:
                body_frame_item = item
        return body_frame_item

    @staticmethod
    def _is_alive_item(item: QQuickItem | None) -> bool:
        return isinstance(item, QQuickItem) and not sip.isdeleted(item)

    @staticmethod
    def _is_descendant_item(item: QQuickItem | None, ancestor: QQuickItem | None) -> bool:
        if not isinstance(item, QQuickItem) or not isinstance(ancestor, QQuickItem):
            return False
        current: QQuickItem | None = item
        while isinstance(current, QQuickItem):
            if current is ancestor:
                return True
            current = current.parentItem()
        return False

    def _overlay_items(
        self,
        record: _OverlayRecord,
        graph_canvas_item: QQuickItem,
        *,
        cached_only: bool = False,
    ) -> tuple[QQuickItem | None, QQuickItem | None]:
        node_card_item = record.node_card_item if self._is_alive_item(record.node_card_item) else None
        if node_card_item is not None:
            node_data = _mapping(node_card_item.property("nodeData"))
            if (
                node_card_item.objectName() != "graphNodeCard"
                or _string(node_data.get("node_id")) != record.node_id
                or not self._is_descendant_item(node_card_item, graph_canvas_item)
            ):
                node_card_item = None
        if node_card_item is None:
            if cached_only:
                return None, None
            node_card_item = self._node_card_item(graph_canvas_item, record.node_id)
            record.node_card_item = node_card_item
            record.viewer_geometry_item = None
        viewer_geometry_item = (
            record.viewer_geometry_item if self._is_alive_item(record.viewer_geometry_item) else None
        )
        if viewer_geometry_item is not None and (
            node_card_item is None
            or viewer_geometry_item.objectName() not in {"graphNodeViewerViewport", "graphNodeViewerBodyFrame"}
            or not self._is_descendant_item(viewer_geometry_item, node_card_item)
        ):
            viewer_geometry_item = None
        if viewer_geometry_item is None or viewer_geometry_item.objectName() != "graphNodeViewerViewport":
            if cached_only:
                return node_card_item, viewer_geometry_item
            preferred_geometry_item = self._viewer_geometry_item(node_card_item)
            if preferred_geometry_item is not None:
                viewer_geometry_item = preferred_geometry_item
            record.viewer_geometry_item = viewer_geometry_item
        return node_card_item, viewer_geometry_item

    @staticmethod
    def _content_fullscreen_viewport_item(root_item: QQuickItem | None) -> QQuickItem | None:
        if not isinstance(root_item, QQuickItem):
            return None
        item = root_item.findChild(QObject, "contentFullscreenViewerViewport")
        return item if isinstance(item, QQuickItem) else None

    def _overlay_live_preview_active(
        self,
        node_card_item: QQuickItem | None,
        node_payload: Mapping[str, Any],
        graph_canvas_item: QQuickItem,
    ) -> bool:
        scene_geometry = self._node_scene_geometry(graph_canvas_item, node_payload)
        if bool(scene_geometry.get("has_live_preview")):
            return True
        if not isinstance(node_card_item, QQuickItem):
            return False
        if _bool(node_card_item.property("_liveGeometryActive")):
            return True
        return (
            abs(_number(node_card_item.property("liveDragDx"), 0.0)) >= 0.01
            or abs(_number(node_card_item.property("liveDragDy"), 0.0)) >= 0.01
        )

    @staticmethod
    def _canvas_interaction_active(graph_canvas_item: QQuickItem) -> bool:
        return _bool(graph_canvas_item.property("interactionActive")) or _bool(
            graph_canvas_item.property("viewportInteractionWorldCacheActive")
        )

    @staticmethod
    def _native_overlay_suppression_active(graph_canvas_item: QQuickItem) -> bool:
        value = graph_canvas_item.property("nativeOverlaySuppressionActive")
        if value is not None:
            return _bool(value)
        return EmbeddedViewerOverlayManager._canvas_interaction_active(graph_canvas_item)

    @staticmethod
    def _record_uses_native_window_overlay(record: _OverlayRecord) -> bool:
        widget = record.overlay_widget
        return widget is not None and _bool(widget.property("ea.nativeWindowOverlay"))

    @staticmethod
    def _set_widget_updates_suspended(record: _OverlayRecord, suspended: bool) -> None:
        widget = record.overlay_widget
        if widget is None:
            return
        if record.updates_suspended == suspended:
            return
        widget.setUpdatesEnabled(not suspended)
        record.updates_suspended = suspended
        if not suspended:
            widget.update()

    def _overlay_geometry(
        self,
        *,
        root_item: QQuickItem,
        graph_canvas_item: QQuickItem,
        node_payload: Mapping[str, Any],
        node_card_item: QQuickItem | None = None,
        viewer_viewport_item: QQuickItem | None = None,
    ) -> QRect | None:
        return self._geometry_service.overlay_geometry(
            root_item=root_item,
            graph_canvas_item=graph_canvas_item,
            node_payload=node_payload,
            node_card_item=node_card_item,
            viewer_viewport_item=viewer_viewport_item,
        )

    def _overlay_geometry_from_scene(
        self,
        *,
        canvas_origin: QPointF,
        canvas_width: float,
        canvas_height: float,
        node_payload: Mapping[str, Any],
        scene_geometry: Mapping[str, Any],
        node_local_rect: Mapping[str, Any] | None = None,
    ) -> QRect | None:
        return self._geometry_service.overlay_geometry_from_scene(
            canvas_origin=canvas_origin,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            node_payload=node_payload,
            scene_geometry=scene_geometry,
            node_local_rect=node_local_rect,
        )

    def _overlay_owners_by_key(self) -> dict[_OverlayKey, str]:
        owners: dict[_OverlayKey, str] = {}
        for owner, overlays in self._desired_overlay_sources.items():
            for key in overlays:
                owners[key] = owner
        return owners

    def _overlay_geometry_from_viewport_item(
        self,
        *,
        root_item: QQuickItem,
        graph_canvas_item: QQuickItem,
        viewer_viewport_item: QQuickItem,
    ) -> QRect | None:
        return self._geometry_service.overlay_geometry_from_viewport_item(
            root_item=root_item,
            graph_canvas_item=graph_canvas_item,
            viewer_viewport_item=viewer_viewport_item,
        )

    def _content_fullscreen_geometry(
        self,
        *,
        root_item: QQuickItem,
        viewer_viewport_item: QQuickItem | None,
    ) -> QRect | None:
        return self._geometry_service.content_fullscreen_geometry(
            root_item=root_item,
            viewer_viewport_item=viewer_viewport_item,
        )

    def _node_scene_geometry(
        self,
        graph_canvas_item: QQuickItem,
        node_payload: Mapping[str, Any],
        *,
        node_card_item: QQuickItem | None = None,
    ) -> dict[str, float | bool]:
        return self._geometry_service.node_scene_geometry(
            graph_canvas_item,
            node_payload,
            node_card_item=node_card_item,
        )

    @staticmethod
    def _viewer_live_rect(
        node_payload: Mapping[str, Any],
        *,
        scene_width: float,
        scene_height: float,
    ) -> dict[str, float]:
        return _OverlayGeometryService.viewer_live_rect(
            node_payload,
            scene_width=scene_width,
            scene_height=scene_height,
        )

    def _ensure_record(self, *, key: _OverlayKey, session_id: str) -> _OverlayRecord | None:
        record = self._overlay_records.get(key)
        if record is not None:
            record.session_id = session_id or record.session_id
            return record

        container = QWidget(self._overlay_parent_widget)
        container.setObjectName(f"embeddedViewerOverlay::{key[0]}::{key[1]}")
        container.hide()
        record = _OverlayRecord(
            workspace_id=key[0],
            node_id=key[1],
            session_id=session_id,
            container=container,
        )
        self._overlay_records[key] = record
        self._last_error = ""
        return record

    @staticmethod
    def _apply_widget_geometry(widget: QWidget, geometry: QRect) -> bool:
        return _OverlayWidgetPresentationService.apply_widget_geometry(widget, geometry)

    @staticmethod
    def _show_record(record: _OverlayRecord, geometry: QRect, *, focus: bool = False) -> None:
        _OverlayWidgetPresentationService.show_record(record, geometry, focus=focus)

    def _hide_record(self, key: _OverlayKey) -> None:
        record = self._overlay_records.get(key)
        if record is None:
            return
        record.geometry_ready = False
        record.ready_geometry = None
        if record.overlay_widget is not None:
            record.overlay_widget.hide()
        record.container.hide()

    def _hide_all_records(self) -> None:
        for key in list(self._overlay_records):
            self._hide_record(key)

    def _teardown_record(self, key: _OverlayKey) -> None:
        record = self._overlay_records.pop(key, None)
        if record is None:
            return
        record.fullscreen_target_active = False
        if record.overlay_widget is not None:
            self._teardown_widget(record.overlay_widget)
        record.container.close()
        record.container.deleteLater()

    @staticmethod
    def _teardown_widget(widget: QWidget) -> None:
        widget.close()
        widget.deleteLater()

    @staticmethod
    def _ensure_overlay_chain_polished(item: QQuickItem | None) -> None:
        # Positioners and layouts move overlay ancestors (for example the
        # viewer body Column repositioning the viewport row) in the polish
        # pass, which runs on frame boundaries and can land after a queued
        # sync. mapToItem-based geometry must not read that half-applied
        # layout, so force any pending polish along the ancestor chain first.
        current = item
        while isinstance(current, QQuickItem) and not sip.isdeleted(current):
            current.ensurePolished()
            current = current.parentItem()

    def _observe_overlay_geometry_chain(
        self,
        node_card_item: QQuickItem | None,
        viewer_viewport_item: QQuickItem | None,
    ) -> None:
        if isinstance(node_card_item, QQuickItem):
            self._observe_overlay_geometry_item(node_card_item)
        # A positioner can move an intermediate container between the
        # viewport and the card without firing any geometry signal on either
        # endpoint, so every chain link needs observation.
        current = viewer_viewport_item
        while isinstance(current, QQuickItem) and not sip.isdeleted(current):
            self._observe_overlay_geometry_item(current)
            if current is node_card_item:
                break
            current = current.parentItem()

    def _observe_overlay_geometry_item(self, item: QQuickItem) -> None:
        if bool(item.property("ea.overlayGeometryObserved")):
            return
        item.setProperty("ea.overlayGeometryObserved", True)
        for signal_name in (
            "xChanged",
            "yChanged",
            "widthChanged",
            "heightChanged",
            "visibleChanged",
            "liveDragDxChanged",
            "liveDragDyChanged",
            "_liveGeometryActiveChanged",
            "_liveXChanged",
            "_liveYChanged",
            "_liveWidthChanged",
            "_liveHeightChanged",
        ):
            self._connect_signal(item, signal_name, self._schedule_transform_sync)

    def _ensure_graph_canvas_observed(self, root_item: QQuickItem | None) -> QQuickItem | None:
        graph_canvas_item = self._graph_canvas_item(root_item)
        if graph_canvas_item is None or graph_canvas_item is self._observed_graph_canvas:
            return graph_canvas_item
        self._observed_graph_canvas = graph_canvas_item
        self._connect_signal(graph_canvas_item, "liveNodeGeometryChanged", self._schedule_transform_sync)
        self._connect_signal(graph_canvas_item, "liveDragRevisionChanged", self._schedule_transform_sync)
        self._connect_signal(graph_canvas_item, "interactionActiveChanged", self._schedule_transform_sync)
        self._connect_signal(graph_canvas_item, "viewportInteractionWorldCacheActiveChanged", self._schedule_transform_sync)
        self._connect_signal(graph_canvas_item, "nativeOverlaySuppressionActiveChanged", self._schedule_transform_sync)
        return graph_canvas_item

    def _clear_records(self) -> None:
        for key in list(self._overlay_records):
            self._teardown_record(key)


__all__ = [
    "EmbeddedViewerExportOverlaySnapshot",
    "EmbeddedViewerOverlayManager",
    "EmbeddedViewerOverlaySpec",
    "VIEWER_SESSION_OVERLAY_OWNER",
]
