# Purpose: QML<->Python bridge for one active content-fullscreen lifecycle and
#          payload, using composition-supplied live owners instead of shell-host lookup.
# Map: feature_routes/qml_bridge_wiring
# Tests: tests/test_content_fullscreen_bridge.py, tests/test_content_fullscreen_bridge_lifecycle.py
# Landmarks: ContentFullscreenBridge, _FullscreenWebSurfaceBridge
from __future__ import annotations

import base64
import copy
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QObject,
    QPointF,
    QRectF,
    Qt,
    pyqtBoundSignal,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)

from ea_node_editor.nodes.builtins.excalidraw import (
    EXCALIDRAW_PREVIEW_REF_PROPERTY,
    EXCALIDRAW_STATE_PROPERTY,
)
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.builtins.web_viewer import (
    normalize_web_page_viewer_browser_state,
    web_page_viewer_browser_state_persistence_enabled,
)
from ea_node_editor.addons.tabular_data.input_node import (
    TABULAR_DATA_INPUT_NODE_TYPE_ID,
    TABULAR_SELECTED_COLUMNS_PROPERTY,
    TABULAR_TABLE_VIEW_STATE_PROPERTY,
    normalize_tabular_selected_columns,
    normalize_tabular_table_view_state,
)
from ea_node_editor.addons.tabular_data.extraction_nodes import (
    write_array_rows_to_path,
    write_table_rows_to_path,
)
from ea_node_editor.nodes.file_dialog_filters import (
    TABULAR_ARRAY_OUTPUT_FILES_FILTER,
    TABULAR_TABLE_OUTPUT_FILES_FILTER,
)
from ea_node_editor.common.artifact_refs import parse_artifact_ref
from ea_node_editor.ui.tabular_preview_provider import (
    TABULAR_PREVIEW_CONTENT_KIND,
    TABULAR_PREVIEW_FULLSCREEN_COLUMN_LIMIT,
    TABULAR_PREVIEW_FULLSCREEN_ROW_LIMIT,
    TabularPreviewProvider,
)
from ea_node_editor.ui.media_panel_source import resolve_media_panel_source
from ea_node_editor.ui.media_video_state import normalize_media_video_state
from ea_node_editor.ui_qml.graph_scene_payload import (
    PLOT_CONTENT_KIND,
    WEB_PAGE_CONTENT_KIND,
    build_content_fullscreen_media_payload,
    build_content_fullscreen_plot_payload,
    build_content_fullscreen_web_editor_payload,
    build_content_fullscreen_web_page_payload,
)
from ea_node_editor.ui_qml.surface_contracts import (
    fullscreen_content_kind_for_node_type,
    surface_spec_payload_for_node_type,
)

from ea_node_editor.web_host.bridge import WebSurfaceBridge
from ea_node_editor.web_host.navigation_policy import decide_web_navigation

if TYPE_CHECKING:
    from ea_node_editor.graph.model import GraphModel
    from ea_node_editor.graph.workspace_state import WorkspaceData
    from ea_node_editor.graph.records import NodeInstance
    from ea_node_editor.nodes.registry import NodeRegistry
    from ea_node_editor.nodes.node_specs import NodeTypeSpec
    from ea_node_editor.ui.shell.state import ShellRunState
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
    from ea_node_editor.ui_qml.script_editor_model import ScriptEditorModel
    from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge
    from ea_node_editor.web_host.bridge import WebSurfaceArtifactService


_ModelProvider = Callable[[], "GraphModel | None"]
_RegistryProvider = Callable[[], "NodeRegistry | None"]
_ActiveWorkspaceIdProvider = Callable[[], str]
_ProjectContextProvider = Callable[[], tuple[str | None, dict[str, Any] | None]]
_SaveFileDialog = Callable[..., str]
_TrimVideoReplace = Callable[
    [str, int, int, dict[str, Any]], Mapping[str, object] | None
]
_TrimVideoCopy = Callable[
    [str, int, int, float, float, dict[str, Any]], Mapping[str, object] | None
]
_WebSurfaceArtifactServiceFactory = Callable[
    [str, str, str, str, str], "WebSurfaceArtifactService"
]


@dataclass(frozen=True, slots=True)
class _FullscreenCandidate:
    workspace_id: str
    workspace_name: str
    node: "NodeInstance"
    spec: "NodeTypeSpec"
    title: str
    content_kind: str
    media_payload: dict[str, Any]
    viewer_payload: dict[str, Any]
    web_editor_payload: dict[str, Any]
    web_page_payload: dict[str, Any]
    plot_payload: dict[str, Any]
    tabular_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _FullscreenResolution:
    candidate: _FullscreenCandidate | None
    error: str


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 0
    return normalized if normalized > 0 else 0


_FALLBACK_PREVIEW_WIDTH = 640
_FALLBACK_PREVIEW_HEIGHT = 360
_FALLBACK_PREVIEW_PADDING = 32.0
_PLOT_FULLSCREEN_OPTION_KEYS = frozenset({"plot_theme", "hover_readout", "vertical_guide", "crosshair"})
_PLOT_FULLSCREEN_BOOL_OPTION_KEYS = frozenset({"hover_readout", "vertical_guide", "crosshair"})
_PLOT_FULLSCREEN_THEME_VALUES = frozenset({"system", "dark", "light"})


@dataclass(frozen=True, slots=True)
class _SceneBounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return max(self.max_x - self.min_x, 1.0)

    @property
    def height(self) -> float:
        return max(self.max_y - self.min_y, 1.0)


def _finite_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _normalized_plot_theme(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized == "auto":
        normalized = "system"
    return normalized if normalized in _PLOT_FULLSCREEN_THEME_VALUES else "system"


def _excalidraw_scene_elements(scene_state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    elements = scene_state.get("elements")
    if not isinstance(elements, list):
        return []
    return [
        element
        for element in elements
        if isinstance(element, Mapping) and not bool(element.get("isDeleted"))
    ]


def _element_text_dimensions(element: Mapping[str, Any]) -> tuple[float, float]:
    text = str(element.get("text") or "")
    font_size = max(_finite_float(element.get("fontSize"), 20.0), 8.0)
    lines = text.splitlines() or [text]
    width = max((len(line) for line in lines), default=0) * font_size * 0.62
    height = max(len(lines), 1) * font_size * 1.25
    return max(width, font_size), max(height, font_size)


def _element_points(element: Mapping[str, Any]) -> list[QPointF]:
    x = _finite_float(element.get("x"))
    y = _finite_float(element.get("y"))
    raw_points = element.get("points")
    points: list[QPointF] = []
    if isinstance(raw_points, list):
        for point in raw_points:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append(
                    QPointF(
                        x + _finite_float(point[0]),
                        y + _finite_float(point[1]),
                    )
                )
    if points:
        return points
    return [
        QPointF(x, y),
        QPointF(x + _finite_float(element.get("width")), y + _finite_float(element.get("height"))),
    ]


def _element_bounds(element: Mapping[str, Any]) -> _SceneBounds | None:
    element_type = str(element.get("type") or "").strip().lower()
    if element_type in {"line", "arrow", "freedraw"}:
        points = _element_points(element)
        if not points:
            return None
        stroke_pad = max(_finite_float(element.get("strokeWidth"), 1.0), 1.0)
        return _SceneBounds(
            min(point.x() for point in points) - stroke_pad,
            min(point.y() for point in points) - stroke_pad,
            max(point.x() for point in points) + stroke_pad,
            max(point.y() for point in points) + stroke_pad,
        )

    x = _finite_float(element.get("x"))
    y = _finite_float(element.get("y"))
    width = _finite_float(element.get("width"))
    height = _finite_float(element.get("height"))
    if element_type == "text" and (width <= 0 or height <= 0):
        text_width, text_height = _element_text_dimensions(element)
        width = max(width, text_width)
        height = max(height, text_height)
    min_x = min(x, x + width)
    max_x = max(x, x + width)
    min_y = min(y, y + height)
    max_y = max(y, y + height)
    if max_x <= min_x and max_y <= min_y:
        return None
    stroke_pad = max(_finite_float(element.get("strokeWidth"), 1.0), 1.0)
    return _SceneBounds(
        min_x - stroke_pad,
        min_y - stroke_pad,
        max_x + stroke_pad,
        max_y + stroke_pad,
    )


def _scene_content_bounds(elements: list[Mapping[str, Any]]) -> _SceneBounds | None:
    bounds = [bounds for element in elements if (bounds := _element_bounds(element)) is not None]
    if not bounds:
        return None
    return _SceneBounds(
        min(item.min_x for item in bounds),
        min(item.min_y for item in bounds),
        max(item.max_x for item in bounds),
        max(item.max_y for item in bounds),
    )


def _excalidraw_color(value: Any, fallback: str, opacity: float = 1.0) -> QColor:
    text = str(value or "").strip()
    if not text or text.lower() == "transparent":
        text = fallback
    color = QColor(text)
    if not color.isValid():
        color = QColor(fallback)
    color.setAlphaF(max(0.0, min(1.0, color.alphaF() * opacity)))
    return color


def _element_opacity(element: Mapping[str, Any]) -> float:
    return max(0.0, min(1.0, _finite_float(element.get("opacity"), 100.0) / 100.0))


def _element_pen(element: Mapping[str, Any]) -> QPen:
    stroke_color = str(element.get("strokeColor") or "").strip()
    if stroke_color.lower() == "transparent":
        return QPen(Qt.PenStyle.NoPen)
    pen = QPen(_excalidraw_color(stroke_color, "#1e1e1e", _element_opacity(element)))
    pen.setWidthF(max(_finite_float(element.get("strokeWidth"), 1.0), 1.0))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _element_brush(element: Mapping[str, Any]) -> QBrush:
    background = str(element.get("backgroundColor") or "").strip()
    if not background or background.lower() == "transparent":
        return QBrush(Qt.BrushStyle.NoBrush)
    return QBrush(_excalidraw_color(background, "transparent", _element_opacity(element)))


def _element_rect(element: Mapping[str, Any]) -> QRectF:
    x = _finite_float(element.get("x"))
    y = _finite_float(element.get("y"))
    width = _finite_float(element.get("width"))
    height = _finite_float(element.get("height"))
    if str(element.get("type") or "").strip().lower() == "text" and (width <= 0 or height <= 0):
        text_width, text_height = _element_text_dimensions(element)
        width = max(width, text_width)
        height = max(height, text_height)
    return QRectF(min(x, x + width), min(y, y + height), abs(width), abs(height))


def _draw_linear_element(painter: QPainter, element: Mapping[str, Any]) -> None:
    points = _element_points(element)
    if len(points) < 2:
        return
    path = QPainterPath(points[0])
    for point in points[1:]:
        path.lineTo(point)
    painter.drawPath(path)

    if str(element.get("type") or "").strip().lower() != "arrow":
        return
    start = points[-2]
    end = points[-1]
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length = math.hypot(dx, dy)
    if length <= 0:
        return
    unit_x = dx / length
    unit_y = dy / length
    head_length = max(12.0, min(24.0, length * 0.25))
    wing = head_length * 0.45
    base = QPointF(end.x() - unit_x * head_length, end.y() - unit_y * head_length)
    normal_x = -unit_y
    normal_y = unit_x
    painter.drawPolygon(
        QPolygonF(
            [
                end,
                QPointF(base.x() + normal_x * wing, base.y() + normal_y * wing),
                QPointF(base.x() - normal_x * wing, base.y() - normal_y * wing),
            ]
        )
    )


def _draw_shape_element(painter: QPainter, element: Mapping[str, Any]) -> None:
    element_type = str(element.get("type") or "").strip().lower()
    if element_type in {"line", "arrow", "freedraw"}:
        _draw_linear_element(painter, element)
        return

    rect = _element_rect(element)
    if rect.width() <= 0 or rect.height() <= 0:
        return

    angle = _finite_float(element.get("angle"))
    painter.save()
    if angle:
        center = rect.center()
        painter.translate(center)
        painter.rotate(math.degrees(angle))
        painter.translate(-center)

    if element_type == "ellipse":
        painter.drawEllipse(rect)
    elif element_type == "diamond":
        center = rect.center()
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(center.x(), rect.top()),
                    QPointF(rect.right(), center.y()),
                    QPointF(center.x(), rect.bottom()),
                    QPointF(rect.left(), center.y()),
                ]
            )
        )
    elif element_type == "text":
        font_size = max(_finite_float(element.get("fontSize"), 20.0), 8.0)
        font = QFont("Virgil")
        font.setPixelSize(round(font_size))
        painter.setFont(font)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(element.get("text") or ""))
    else:
        radius = min(rect.width(), rect.height(), 18.0) * 0.18
        painter.drawRoundedRect(rect, radius, radius)
    painter.restore()


def _fallback_preview_payload_from_scene(scene_state: Mapping[str, Any]) -> dict[str, Any]:
    elements = _excalidraw_scene_elements(scene_state)
    bounds = _scene_content_bounds(elements)
    if bounds is None:
        return {}

    width = _FALLBACK_PREVIEW_WIDTH
    height = _FALLBACK_PREVIEW_HEIGHT
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    app_state = scene_state.get("appState")
    background = "#ffffff"
    if isinstance(app_state, Mapping):
        background = str(app_state.get("viewBackgroundColor") or background)
    image.fill(_excalidraw_color(background, "#ffffff"))

    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        available_width = max(width - _FALLBACK_PREVIEW_PADDING * 2.0, 1.0)
        available_height = max(height - _FALLBACK_PREVIEW_PADDING * 2.0, 1.0)
        scale = min(available_width / bounds.width, available_height / bounds.height, 3.0)
        content_width = bounds.width * scale
        content_height = bounds.height * scale
        offset_x = (width - content_width) / 2.0 - bounds.min_x * scale
        offset_y = (height - content_height) / 2.0 - bounds.min_y * scale
        painter.translate(offset_x, offset_y)
        painter.scale(scale, scale)
        for element in elements:
            painter.setPen(_element_pen(element))
            painter.setBrush(_element_brush(element))
            _draw_shape_element(painter, element)
    finally:
        painter.end()

    buffer = QByteArray()
    device = QBuffer(buffer)
    if not device.open(QIODevice.OpenModeFlag.WriteOnly):
        return {}
    if not image.save(device, "PNG"):
        return {}
    payload = bytes(buffer)
    app_name = ""
    if isinstance(app_state, Mapping):
        app_name = str(app_state.get("name") or "").strip()
    return {
        "dataURL": f"data:image/png;base64,{base64.b64encode(payload).decode('ascii')}",
        "width": width,
        "height": height,
        "name": f"{app_name or 'excalidraw'}-preview.png",
        "scene_state": copy.deepcopy(dict(scene_state)),
    }


class _FullscreenWebSurfaceBridge(WebSurfaceBridge):
    preview_export_finished = pyqtSignal("QVariantMap", name="previewExportFinished")

    def __init__(
        self,
        initial_state: dict[str, Any] | None = None,
        parent: QObject | None = None,
        *,
        preview_persist_callback: Callable[[dict[str, Any]], None] | None = None,
        artifact_service: "WebSurfaceArtifactService",
        artifact_scope: str,
    ) -> None:
        if artifact_service is None:
            raise ValueError("Fullscreen Web artifact storage is required.")
        super().__init__(
            initial_state,
            parent,
            artifact_service=artifact_service,
            artifact_scope=artifact_scope,
        )
        self._preview_persist_callback = preview_persist_callback

    @pyqtSlot(result="QVariantMap")
    @pyqtSlot(str, result="QVariantMap")
    @pyqtSlot("QVariant", result="QVariantMap")
    def export_preview(self, payload: Any = None) -> dict[str, Any]:
        self._save_state_from_preview_payload(payload)
        result = copy.deepcopy(super().export_preview(payload))
        result = self._result_with_preview_payload(result, payload)
        if result.get("ok") is True and self._preview_persist_callback is not None:
            self._preview_persist_callback(result)
        self.preview_export_finished.emit(result)
        return result

    def _save_state_from_preview_payload(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        scene_state = payload["scene_state"] if "scene_state" in payload else payload.get("sceneState")
        if isinstance(scene_state, Mapping):
            self.save_state(scene_state)

    @staticmethod
    def _result_with_preview_payload(result: dict[str, Any], payload: Any) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            return result
        payload_copy = copy.deepcopy(dict(payload))
        scene_state = payload_copy["scene_state"] if "scene_state" in payload_copy else payload_copy.get("sceneState")
        if isinstance(scene_state, Mapping) and "scene_state" not in result and "sceneState" not in result:
            result["scene_state"] = copy.deepcopy(dict(scene_state))
        if payload_copy and "host_payload" not in result and "hostPayload" not in result:
            result["host_payload"] = payload_copy
        return result

    def artifact_ref_resolves(self, artifact_ref: str) -> bool:
        service = self._artifact_service
        if service is None:
            return False
        try:
            store = service.store
            resolved_path = store.resolve_staged_path(
                artifact_ref
            ) or store.resolve_managed_path(artifact_ref)
        except Exception:  # noqa: BLE001
            return False
        return bool(resolved_path is not None and resolved_path.exists())


class ContentFullscreenBridge(QObject):
    content_fullscreen_changed = pyqtSignal()
    video_fullscreen_closed = pyqtSignal(str, "QVariantMap", name="videoFullscreenClosed")
    tabular_window_ready = pyqtSignal(str, "QVariantMap", name="tabularWindowReady")

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        model_provider: _ModelProvider,
        registry_provider: _RegistryProvider,
        active_workspace_id_provider: _ActiveWorkspaceIdProvider,
        project_context_provider: _ProjectContextProvider,
        scene_bridge: "GraphSceneBridge",
        viewer_session_bridge: "ViewerSessionBridge",
        run_state: "ShellRunState",
        execution_state_changed_signal: pyqtBoundSignal,
        script_editor: "ScriptEditorModel",
        save_file_dialog: _SaveFileDialog,
        trim_video_clip_replace: _TrimVideoReplace,
        trim_video_clip_copy: _TrimVideoCopy,
        create_web_surface_artifact_service: _WebSurfaceArtifactServiceFactory,
    ) -> None:
        super().__init__(parent)
        self._model_provider: _ModelProvider | None = model_provider
        self._registry_provider: _RegistryProvider | None = registry_provider
        self._active_workspace_id_provider: _ActiveWorkspaceIdProvider | None = (
            active_workspace_id_provider
        )
        self._project_context_provider: _ProjectContextProvider | None = (
            project_context_provider
        )
        self._scene_bridge = scene_bridge
        self._viewer_session_bridge = viewer_session_bridge
        self._run_state: ShellRunState | None = run_state
        self._execution_state_changed_signal: pyqtBoundSignal | None = (
            execution_state_changed_signal
        )
        self._script_editor: ScriptEditorModel | None = script_editor
        self._save_file_dialog: _SaveFileDialog | None = save_file_dialog
        self._trim_video_clip_replace: _TrimVideoReplace | None = (
            trim_video_clip_replace
        )
        self._trim_video_clip_copy: _TrimVideoCopy | None = trim_video_clip_copy
        self._create_web_surface_artifact_service: (
            _WebSurfaceArtifactServiceFactory | None
        ) = create_web_surface_artifact_service
        self._terminal = False
        self._lifecycle_connections: list[tuple[pyqtBoundSignal, Callable[..., Any]]] = []
        self._open = False
        self._node_id = ""
        self._workspace_id = ""
        self._content_kind = ""
        self._title = ""
        self._media_payload: dict[str, Any] = {}
        self._viewer_payload: dict[str, Any] = {}
        self._web_editor_payload: dict[str, Any] = {}
        self._web_page_payload: dict[str, Any] = {}
        self._plot_payload: dict[str, Any] = {}
        self._tabular_payload: dict[str, Any] = {}
        self._web_surface_bridge: WebSurfaceBridge | None = None
        self._web_surface_bridge_node_id = ""
        self._web_surface_bridge_artifact_scope = ""
        self._web_surface_bridge_initial_state: dict[str, Any] = {}
        self._last_error = ""
        self._tabular_preview_provider: TabularPreviewProvider | None = None
        self._tabular_preview_worker_pool = None
        self._pending_tabular_window_jobs: dict[str, dict] = {}
        self._pending_tabular_payload_job = ""
        self._pending_tabular_payload_node_id = ""
        self._tabular_payload_request_counter = 0
        self._tabular_window_request_counter = 0
        self._latest_tabular_window_request_id = ""
        self._connect_scene_lifecycle()

    def _ensure_tabular_preview_provider(self) -> TabularPreviewProvider:
        if self._terminal:
            raise RuntimeError("Content fullscreen bridge is shut down.")
        provider = self._tabular_preview_provider
        if provider is None:
            provider = TabularPreviewProvider(project_context_provider=self._project_context)
            self._tabular_preview_provider = provider
        return provider

    def _ensure_tabular_preview_worker_pool(self):  # noqa: ANN202
        if self._terminal:
            raise RuntimeError("Content fullscreen bridge is shut down.")
        pool = self._tabular_preview_worker_pool
        if pool is None:
            from ea_node_editor.ui.tabular_preview_async import TabularPreviewWorkerPool

            pool = TabularPreviewWorkerPool(self)
            pool.job_finished.connect(self._on_tabular_preview_job_finished)
            self._tabular_preview_worker_pool = pool
        return pool

    def _connect_scene_lifecycle(self) -> None:
        connections = (
            (self._scene_bridge.workspace_changed, self._on_workspace_changed),
            (self._scene_bridge.nodes_changed, self._on_nodes_changed),
            (self._scene_bridge.edges_changed, self._on_nodes_changed),
            (self._execution_state_changed_signal, self._on_nodes_changed),
        )
        for signal, slot in connections:
            signal.connect(slot)
            self._lifecycle_connections.append((signal, slot))

    def shutdown(self) -> None:
        if self._terminal:
            return
        self._terminal = True
        for signal, slot in self._lifecycle_connections:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._lifecycle_connections.clear()
        self._clear_tabular_preview_jobs()
        bridge_changed = self._clear_web_surface_bridge()
        self._set_state(
            open_=False,
            node_id="",
            workspace_id="",
            content_kind="",
            title="",
            media_payload={},
            viewer_payload={},
            web_editor_payload={},
            web_page_payload={},
            plot_payload={},
            tabular_payload={},
            last_error="",
            web_surface_bridge_changed=bridge_changed,
        )
        pool = self._tabular_preview_worker_pool
        self._tabular_preview_worker_pool = None
        if pool is not None:
            try:
                pool.job_finished.disconnect(self._on_tabular_preview_job_finished)
            except (TypeError, RuntimeError):
                pass
            pool.shutdown()
        self._tabular_preview_provider = None
        self._model_provider = None
        self._registry_provider = None
        self._active_workspace_id_provider = None
        self._project_context_provider = None
        self._execution_state_changed_signal = None
        self._run_state = None
        self._script_editor = None
        self._save_file_dialog = None
        self._trim_video_clip_replace = None
        self._trim_video_clip_copy = None
        self._create_web_surface_artifact_service = None
        self._scene_bridge = None  # type: ignore[assignment]
        self._viewer_session_bridge = None  # type: ignore[assignment]

    def _clear_tabular_preview_jobs(self) -> None:
        self._pending_tabular_window_jobs.clear()
        self._pending_tabular_payload_job = ""
        self._pending_tabular_payload_node_id = ""
        self._latest_tabular_window_request_id = ""

    def _resolve_candidate(self, node_id: str) -> _FullscreenResolution:
        if self._terminal:
            return _FullscreenResolution(None, "Content fullscreen is shut down.")
        normalized_node_id = str(node_id or "").strip()
        if not normalized_node_id:
            return _FullscreenResolution(
                None, "A node must be selected for content fullscreen."
            )
        model_provider = self._model_provider
        registry_provider = self._registry_provider
        active_workspace_id_provider = self._active_workspace_id_provider
        model = model_provider() if model_provider is not None else None
        registry = registry_provider() if registry_provider is not None else None
        manager_workspace_id = (
            str(active_workspace_id_provider() or "").strip()
            if active_workspace_id_provider is not None
            else ""
        )
        workspace_result = self._active_workspace_from_snapshot(
            model=model,
            registry=registry,
            manager_workspace_id=manager_workspace_id,
        )
        if isinstance(workspace_result, str):
            return _FullscreenResolution(None, workspace_result)
        workspace_id, workspace, resolved_registry = workspace_result
        node = workspace.nodes.get(normalized_node_id)
        if node is None:
            return _FullscreenResolution(
                None, "The selected node is no longer available."
            )
        spec = self._node_spec(resolved_registry, node.type_id)
        if spec is None:
            return _FullscreenResolution(
                None, "The selected node type is unavailable."
            )
        content_kind = self._content_kind_for_node(node, spec)
        if not content_kind:
            return _FullscreenResolution(
                None, "The selected node does not support content fullscreen."
            )
        if content_kind == "mail" and not str(
            node.properties.get("source_path", "") or ""
        ).strip():
            return _FullscreenResolution(
                None, "Mail Panel needs a source path before it can open fullscreen."
            )
        if content_kind == TABULAR_PREVIEW_CONTENT_KIND and not str(
            node.properties.get("path", "") or ""
        ).strip():
            return _FullscreenResolution(
                None,
                "Tabular data nodes need a source path before they can open fullscreen.",
            )
        project_path, project_metadata = self._project_context()
        source_resolution = (
            resolve_media_panel_source(
                node=node,
                workspace=workspace,
                run_state=self._run_state,
                project_path=project_path,
                project_metadata=project_metadata,
            )
            if content_kind == "media"
            else None
        )
        media_payload = (
            build_content_fullscreen_media_payload(
                workspace_id=workspace_id,
                node=node,
                spec=spec,
                project_path=project_path,
                project_metadata=project_metadata,
                source_resolution=source_resolution,
            )
            if content_kind in {"media", "mail"}
            else {}
        )
        return _FullscreenResolution(
            _FullscreenCandidate(
                workspace_id=workspace_id,
                workspace_name=str(workspace.name or "").strip(),
                node=node,
                spec=spec,
                title=str(node.title or spec.display_name),
                content_kind=content_kind,
                media_payload=media_payload,
                viewer_payload=(
                    self._build_viewer_payload(
                        workspace_id=workspace_id,
                        node=node,
                        spec=spec,
                    )
                    if content_kind == "viewer"
                    else {}
                ),
                web_editor_payload=(
                    build_content_fullscreen_web_editor_payload(
                        workspace_id=workspace_id,
                        node=node,
                        spec=spec,
                    )
                    if content_kind == "web_editor"
                    else {}
                ),
                web_page_payload=(
                    build_content_fullscreen_web_page_payload(
                        workspace_id=workspace_id,
                        node=node,
                        spec=spec,
                        project_path=project_path,
                        project_metadata=project_metadata,
                    )
                    if content_kind == WEB_PAGE_CONTENT_KIND
                    else {}
                ),
                plot_payload=(
                    build_content_fullscreen_plot_payload(
                        workspace_id=workspace_id,
                        node=node,
                        spec=spec,
                        scene_payload=self._scene_node_payload(node.node_id),
                    )
                    if content_kind == PLOT_CONTENT_KIND
                    else {}
                ),
                tabular_payload=(
                    self._build_tabular_payload(
                        workspace_id=workspace_id,
                        node=node,
                        spec=spec,
                    )
                    if content_kind == TABULAR_PREVIEW_CONTENT_KIND
                    else {}
                ),
            ),
            "",
        )

    def _active_workspace(
        self,
    ) -> tuple[str, "WorkspaceData", "NodeRegistry"] | str:
        if self._terminal:
            return "Content fullscreen is shut down."
        model_provider = self._model_provider
        registry_provider = self._registry_provider
        active_workspace_id_provider = self._active_workspace_id_provider
        return self._active_workspace_from_snapshot(
            model=model_provider() if model_provider is not None else None,
            registry=(
                registry_provider() if registry_provider is not None else None
            ),
            manager_workspace_id=(
                str(active_workspace_id_provider() or "").strip()
                if active_workspace_id_provider is not None
                else ""
            ),
        )

    def _active_workspace_from_snapshot(
        self,
        *,
        model: "GraphModel | None",
        registry: "NodeRegistry | None",
        manager_workspace_id: str,
    ) -> tuple[str, "WorkspaceData", "NodeRegistry"] | str:
        scene_workspace_id = str(self._scene_bridge.workspace_id or "").strip()
        if (
            scene_workspace_id
            and manager_workspace_id
            and scene_workspace_id != manager_workspace_id
        ):
            return "The active workspace state is ambiguous."
        workspace_id = scene_workspace_id or manager_workspace_id
        if not workspace_id:
            return "The active workspace state is ambiguous."
        if model is None or registry is None:
            return "The graph model is not ready."
        workspace = model.project.workspaces.get(workspace_id)
        if workspace is None:
            return "The active workspace state is ambiguous."
        return workspace_id, workspace, registry

    @staticmethod
    def _node_spec(
        registry: "NodeRegistry", type_id: str
    ) -> "NodeTypeSpec | None":
        spec_or_none = getattr(registry, "spec_or_none", None)
        if callable(spec_or_none):
            return spec_or_none(type_id)
        try:
            return registry.get_spec(type_id)
        except KeyError:
            return None

    @staticmethod
    def _content_kind_for_node(
        node: "NodeInstance", spec: "NodeTypeSpec"
    ) -> str:
        if str(node.type_id) == TABULAR_DATA_INPUT_NODE_TYPE_ID:
            return TABULAR_PREVIEW_CONTENT_KIND
        if str(node.type_id) == MEDIA_PANEL_TYPE_ID:
            return "media"
        content_kind = fullscreen_content_kind_for_node_type(
            type_id=node.type_id, spec=spec
        )
        if content_kind:
            return content_kind
        if str(node.type_id) == "web.page_viewer":
            return WEB_PAGE_CONTENT_KIND
        if (
            str(getattr(spec, "surface_family", "") or "").strip() == "web"
            and str(getattr(spec, "surface_variant", "") or "").strip()
            == "page_viewer"
        ):
            return WEB_PAGE_CONTENT_KIND
        return ""

    def _build_viewer_payload(
        self,
        *,
        workspace_id: str,
        node: "NodeInstance",
        spec: "NodeTypeSpec",
    ) -> dict[str, Any]:
        session_state = self._viewer_session_state(node.node_id)
        options = session_state.get("options", {})
        options_payload = options if isinstance(options, dict) else {}
        summary = session_state.get("summary", {})
        summary_payload = summary if isinstance(summary, dict) else {}
        return {
            "workspace_id": str(workspace_id),
            "node_id": str(node.node_id),
            "type_id": str(node.type_id),
            "title": str(node.title or spec.display_name),
            "display_name": str(spec.display_name),
            "surface_family": str(spec.surface_family or ""),
            "surface_variant": str(spec.surface_variant or ""),
            "surface_spec": surface_spec_payload_for_node_type(
                type_id=node.type_id, spec=spec
            ),
            "properties": copy.deepcopy(node.properties),
            "session_state": session_state,
            "session_id": str(session_state.get("session_id", "") or ""),
            "phase": str(session_state.get("phase", "closed") or "closed"),
            "cache_state": str(session_state.get("cache_state", "") or ""),
            "live_mode": str(
                session_state.get("live_mode", "")
                or options_payload.get("live_mode", "")
                or ""
            ),
            "summary": copy.deepcopy(summary_payload),
            "viewer_surface": self._scene_node_payload(node.node_id).get(
                "viewer_surface", {}
            ),
        }

    def _build_tabular_payload(
        self,
        *,
        workspace_id: str,
        node: "NodeInstance",
        spec: "NodeTypeSpec",
    ) -> dict[str, Any]:
        properties = copy.deepcopy(node.properties)
        table_view_state = normalize_tabular_table_view_state(
            properties.get(TABULAR_TABLE_VIEW_STATE_PROPERTY, {})
        )
        selected_columns = normalize_tabular_selected_columns(
            properties.get(TABULAR_SELECTED_COLUMNS_PROPERTY, [])
        )
        preview_payload = self._ensure_tabular_preview_provider().describe_preview(
            properties,
            {
                "row_limit": TABULAR_PREVIEW_FULLSCREEN_ROW_LIMIT,
                "column_limit": TABULAR_PREVIEW_FULLSCREEN_COLUMN_LIMIT,
            },
            mode="fullscreen",
        )
        surface_spec = surface_spec_payload_for_node_type(
            type_id=node.type_id, spec=spec
        )
        surface_spec["fullscreen"] = {
            "supported": True,
            "content_kind": TABULAR_PREVIEW_CONTENT_KIND,
            "action_id": "fullscreen",
            "action_label": "Fullscreen",
            "action_icon": "fullscreen",
            "action_kind": "tabular",
            "requires_bridge": True,
        }
        metadata = surface_spec.get("metadata")
        surface_spec["metadata"] = (
            copy.deepcopy(dict(metadata)) if isinstance(metadata, Mapping) else {}
        )
        surface_spec["metadata"]["tabular_preview"] = True
        return {
            "workspace_id": str(workspace_id),
            "node_id": str(node.node_id),
            "type_id": str(node.type_id),
            "title": str(node.title or spec.display_name),
            "display_name": str(spec.display_name),
            "surface_family": str(spec.surface_family or ""),
            "surface_variant": str(spec.surface_variant or ""),
            "surface_spec": surface_spec,
            "properties": properties,
            TABULAR_TABLE_VIEW_STATE_PROPERTY: table_view_state,
            TABULAR_SELECTED_COLUMNS_PROPERTY: selected_columns,
            "preview": preview_payload,
            "preview_state": str(preview_payload.get("state", "") or ""),
            "preview_kind": str(
                preview_payload.get("preview_kind", "") or ""
            ),
        }

    def _viewer_session_state(self, node_id: str) -> dict[str, Any]:
        try:
            state = self._viewer_session_bridge.session_state(node_id)
        except Exception:  # noqa: BLE001
            return {}
        return copy.deepcopy(state) if isinstance(state, dict) else {}

    def _scene_node_payload(self, node_id: str) -> dict[str, Any]:
        try:
            payloads = list(self._scene_bridge.nodes_model or [])
        except Exception:  # noqa: BLE001
            return {}
        normalized = str(node_id or "").strip()
        for payload in payloads:
            if (
                isinstance(payload, dict)
                and str(payload.get("node_id", "")).strip() == normalized
            ):
                return copy.deepcopy(payload)
        return {}

    def _project_context(self) -> tuple[str | None, dict[str, Any] | None]:
        provider = self._project_context_provider
        if provider is None:
            return None, None
        project_path, metadata = provider()
        normalized_path = str(project_path or "").strip() or None
        normalized_metadata = (
            copy.deepcopy(dict(metadata)) if isinstance(metadata, Mapping) else None
        )
        return normalized_path, normalized_metadata

    @pyqtProperty(bool, notify=content_fullscreen_changed)
    def open(self) -> bool:
        return self._open

    @pyqtProperty(str, notify=content_fullscreen_changed)
    def node_id(self) -> str:
        return self._node_id

    @pyqtProperty(str, notify=content_fullscreen_changed)
    def workspace_id(self) -> str:
        return self._workspace_id

    @pyqtProperty(str, notify=content_fullscreen_changed)
    def content_kind(self) -> str:
        return self._content_kind

    @pyqtProperty(str, notify=content_fullscreen_changed)
    def title(self) -> str:
        return self._title

    @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
    def media_payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._media_payload)

    @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
    def viewer_payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._viewer_payload)

    @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
    def web_editor_payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._web_editor_payload)

    @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
    def web_page_payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._web_page_payload)

    @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
    def plot_payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._plot_payload)

    @pyqtProperty("QVariantMap", notify=content_fullscreen_changed)
    def tabular_payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._tabular_payload)

    @pyqtProperty(QObject, notify=content_fullscreen_changed)
    def web_surface_bridge(self) -> QObject | None:
        return self._web_surface_bridge

    @pyqtProperty(str, notify=content_fullscreen_changed)
    def last_error(self) -> str:
        return self._last_error

    @pyqtSlot(str, result=bool)
    def request_open_node(self, node_id: str) -> bool:
        if self._terminal:
            return False
        resolution = self._resolve_candidate(node_id)
        if resolution.candidate is None:
            self._close_with_error(resolution.error)
            return False
        self._open_candidate(resolution.candidate)
        return True

    @pyqtSlot(str, "QVariantMap", result=bool)
    def request_open_node_with_state(self, node_id: str, state: dict[str, Any]) -> bool:
        if self._terminal:
            return False
        resolution = self._resolve_candidate(node_id)
        if resolution.candidate is None:
            self._close_with_error(resolution.error)
            return False
        self._open_candidate(resolution.candidate, runtime_state=normalize_media_video_state(state))
        return True

    @pyqtSlot(str, result=bool)
    def request_toggle_for_node(self, node_id: str) -> bool:
        if self._terminal:
            return False
        normalized = str(node_id or "").strip()
        if self._open and normalized and normalized == self._node_id:
            self.request_close()
            return True
        return self.request_open_node(normalized)

    @pyqtSlot(str, "QVariantMap", result=bool)
    def request_toggle_for_node_with_state(self, node_id: str, state: dict[str, Any]) -> bool:
        if self._terminal:
            return False
        normalized = str(node_id or "").strip()
        if self._open and normalized and normalized == self._node_id:
            if self._active_media_kind() == "video":
                return self.request_close_with_state(state)
            self.request_close()
            return True
        return self.request_open_node_with_state(normalized, state)

    @pyqtSlot()
    def request_close(self) -> None:
        if self._terminal:
            return
        if self._open and self._content_kind == "web_editor":
            self._persist_web_editor_state()
        self._clear_tabular_preview_jobs()
        self._set_state(
            open_=False,
            node_id="",
            workspace_id="",
            content_kind="",
            title="",
            media_payload={},
            viewer_payload={},
            web_editor_payload={},
            web_page_payload={},
            plot_payload={},
            tabular_payload={},
            last_error="",
            web_surface_bridge_changed=self._clear_web_surface_bridge(),
        )

    @pyqtSlot("QVariantMap", result=bool)
    def request_close_with_state(self, state: dict[str, Any]) -> bool:
        if self._terminal:
            return False
        if not self._open:
            self.request_close()
            return False
        if self._active_media_kind() != "video" or not self._node_id:
            self.request_close()
            return False
        node_id = self._node_id
        normalized_state = normalize_media_video_state(state)
        self._persist_video_fullscreen_state(node_id, normalized_state)
        self.request_close()
        self.video_fullscreen_closed.emit(node_id, normalized_state)
        return True

    @pyqtSlot(str, "QVariant", result=bool)
    def set_active_plot_option(self, key: str, value: Any) -> bool:
        option_key = str(key or "").strip()
        if (
            self._terminal
            or not self._open
            or self._content_kind != PLOT_CONTENT_KIND
            or not self._node_id
            or option_key not in _PLOT_FULLSCREEN_OPTION_KEYS
        ):
            return False
        normalized_value: Any
        if option_key in _PLOT_FULLSCREEN_BOOL_OPTION_KEYS:
            normalized_value = _bool_value(value, False)
        else:
            normalized_value = _normalized_plot_theme(value)

        if not self._set_plot_options_direct(option_key, normalized_value):
            return False
        self._refresh_active_plot_payload_option(option_key, normalized_value)
        self.content_fullscreen_changed.emit()
        return True

    @pyqtSlot("QVariantMap", result="QVariantMap")
    def request_trim_video_clip_replace(self, state: dict[str, Any]) -> dict[str, Any]:
        if (
            self._terminal
            or not self._open
            or self._active_media_kind() != "video"
            or not self._node_id
        ):
            return self._video_trim_bridge_error(
                "fullscreen_unavailable",
                "No fullscreen Media Panel in video mode is active.",
            )
        normalized_state = normalize_media_video_state(state)
        trim = self._trim_video_clip_replace
        if trim is None:
            return self._video_trim_bridge_error(
                "mutation_unavailable",
                "Media Panel actions are unavailable.",
            )
        return dict(
            trim(
                self._node_id,
                int(normalized_state["clip_start_ms"]),
                int(normalized_state["clip_end_ms"]),
                normalized_state,
            )
            or {}
        )

    @pyqtSlot("QVariantMap", result="QVariantMap")
    def request_trim_video_clip_copy(self, state: dict[str, Any]) -> dict[str, Any]:
        if (
            self._terminal
            or not self._open
            or self._active_media_kind() != "video"
            or not self._node_id
        ):
            return self._video_trim_bridge_error(
                "fullscreen_unavailable",
                "No fullscreen Media Panel in video mode is active.",
            )
        normalized_state = normalize_media_video_state(state)
        trim = self._trim_video_clip_copy
        if trim is None:
            return self._video_trim_bridge_error(
                "mutation_unavailable",
                "Media Panel actions are unavailable.",
            )
        return dict(
            trim(
                self._node_id,
                int(normalized_state["clip_start_ms"]),
                int(normalized_state["clip_end_ms"]),
                0.0,
                0.0,
                normalized_state,
            )
            or {}
        )

    @pyqtSlot(int, result=bool)
    def request_pdf_page_delta(self, delta: int) -> bool:
        page_state = self._current_pdf_page_state()
        if page_state is None:
            return False
        page_count, current_page = page_state
        try:
            normalized_delta = int(delta)
        except (TypeError, ValueError):
            normalized_delta = 0
        target_page = min(page_count, max(1, current_page + normalized_delta))
        if target_page == current_page:
            return True
        return self.request_pdf_page_number(target_page)

    @pyqtSlot(int, result=bool)
    def request_pdf_page_number(self, page_number: int) -> bool:
        page_state = self._current_pdf_page_state()
        if page_state is None:
            return False
        page_count, current_page = page_state
        try:
            normalized_page = int(page_number)
        except (TypeError, ValueError):
            normalized_page = 1
        target_page = min(page_count, max(1, normalized_page))
        if target_page == current_page:
            return True
        node_id = self._node_id
        if not self._set_node_property(node_id, "page_number", target_page):
            return False
        self._on_nodes_changed()
        return True

    @pyqtSlot(str, result=bool)
    def can_open_node(self, node_id: str) -> bool:
        return not self._terminal and self._resolve_candidate(node_id).candidate is not None

    @pyqtSlot("QVariant")
    def finish_web_editor_close(self, preview_result: Any = None) -> None:
        if self._terminal:
            return
        if self._open and self._content_kind == "web_editor":
            preview_result = self._materialize_web_editor_preview_result(preview_result)
            self._persist_web_editor_state_from_preview_result(preview_result)
            self._persist_web_editor_preview_result(preview_result)
        self.request_close()

    @pyqtSlot("QVariantMap", result="QVariantMap")
    def request_tabular_window(self, request: dict[str, Any]) -> dict[str, Any]:
        properties = self._current_tabular_node_properties()
        if isinstance(properties, str):
            return self._tabular_error_payload(properties)
        payload = self._ensure_tabular_preview_provider().table_window_payload(
            properties,
            request if isinstance(request, Mapping) else {},
            mode="fullscreen",
        )
        if isinstance(payload, dict) and payload.get("state") == "loading":
            request_id = self._schedule_tabular_window_job(properties, request, kind="table")
            payload = copy.deepcopy(payload)
            if request_id:
                payload["request_id"] = request_id
            else:
                payload = self._tabular_error_payload("Tabular preview worker is unavailable.")
        return payload

    @pyqtSlot("QVariantMap", result="QVariantMap")
    def request_tabular_slice_2d(self, request: dict[str, Any]) -> dict[str, Any]:
        properties = self._current_tabular_node_properties()
        if isinstance(properties, str):
            return self._tabular_error_payload(properties)
        payload = self._ensure_tabular_preview_provider().array_slice_payload(
            properties,
            request if isinstance(request, Mapping) else {},
            mode="fullscreen",
        )
        if isinstance(payload, dict) and payload.get("state") == "loading":
            request_id = self._schedule_tabular_window_job(properties, request, kind="array")
            payload = copy.deepcopy(payload)
            if request_id:
                payload["request_id"] = request_id
            else:
                payload = self._tabular_error_payload("Tabular preview worker is unavailable.")
        return payload

    def _schedule_tabular_window_job(
        self,
        properties: Mapping[str, Any],
        request: Mapping[str, Any] | None,
        *,
        kind: str,
    ) -> str:
        """Resolve a cold fullscreen window on the worker, then push it to QML."""

        properties_snapshot = copy.deepcopy(dict(properties))
        request_snapshot = copy.deepcopy(dict(request)) if isinstance(request, Mapping) else {}
        node_id = self._node_id
        self._tabular_window_request_counter += 1
        request_id = f"{kind}:{self._tabular_window_request_counter}"
        self._latest_tabular_window_request_id = request_id
        job_key = "fullscreen-window:" + json.dumps(
            {"node": node_id, "kind": kind, "request_id": request_id, "request": request_snapshot},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        result: dict[str, Any] = {}

        def build() -> None:
            if kind == "table":
                result.update(
                    self._ensure_tabular_preview_provider().table_window_payload(
                        properties_snapshot, request_snapshot, mode="fullscreen"
                    )
                )
            else:
                result.update(
                    self._ensure_tabular_preview_provider().array_slice_payload(
                        properties_snapshot, request_snapshot, mode="fullscreen"
                    )
                )

        if self._ensure_tabular_preview_worker_pool().schedule(job_key, build):
            self._pending_tabular_window_jobs[job_key] = {
                "node_id": node_id,
                "request_id": request_id,
                "result": result,
            }
            return request_id
        return ""

    def schedule_tabular_payload_refresh(self) -> None:
        """Rebuild the fullscreen tabular payload once the cache is warm."""

        if self._terminal or not self._open or self._content_kind != "tabular":
            return
        properties = self._current_tabular_node_properties()
        if isinstance(properties, str):
            return
        node_id = self._node_id
        self._tabular_payload_request_counter += 1
        job_key = f"fullscreen-payload:{node_id}:{self._tabular_payload_request_counter}"
        properties_snapshot = copy.deepcopy(dict(properties))

        def build() -> None:
            self._ensure_tabular_preview_provider().describe_preview(
                properties_snapshot,
                {
                    "row_limit": TABULAR_PREVIEW_FULLSCREEN_ROW_LIMIT,
                    "column_limit": TABULAR_PREVIEW_FULLSCREEN_COLUMN_LIMIT,
                },
                mode="fullscreen",
            )

        if self._ensure_tabular_preview_worker_pool().schedule(job_key, build):
            self._pending_tabular_payload_job = job_key
            self._pending_tabular_payload_node_id = node_id

    def _on_tabular_preview_job_finished(self, job_key: str, _error: str) -> None:
        if self._terminal:
            return
        if job_key == self._pending_tabular_payload_job:
            self._pending_tabular_payload_job = ""
            pending_node_id = self._pending_tabular_payload_node_id
            self._pending_tabular_payload_node_id = ""
            if not self._open or self._content_kind != "tabular" or self._node_id != pending_node_id:
                return
            if _error:
                next_tabular_payload = copy.deepcopy(self._tabular_payload)
                next_tabular_payload["preview_state"] = "error"
                next_tabular_payload["preview"] = self._tabular_error_payload(_error)
                self._set_state(
                    open_=self._open,
                    node_id=self._node_id,
                    workspace_id=self._workspace_id,
                    content_kind=self._content_kind,
                    title=self._title,
                    media_payload=self._media_payload,
                    viewer_payload=self._viewer_payload,
                    web_editor_payload=self._web_editor_payload,
                    web_page_payload=self._web_page_payload,
                    plot_payload=self._plot_payload,
                    tabular_payload=next_tabular_payload,
                    last_error=_error,
                )
                return
            self._on_nodes_changed()
            return
        pending = self._pending_tabular_window_jobs.pop(job_key, None)
        if pending is None:
            return
        if not self._open or self._node_id != str(pending.get("node_id", "")):
            return
        request_id = str(pending.get("request_id", "") or "")
        if not request_id or request_id != self._latest_tabular_window_request_id:
            return
        if _error:
            result = self._tabular_error_payload(_error)
        else:
            result = pending.get("result")
        if isinstance(result, dict) and result:
            payload = copy.deepcopy(result)
            payload["request_id"] = request_id
            self.tabular_window_ready.emit(request_id, payload)

    @pyqtSlot("QVariantMap", result="QVariantMap")
    def request_tabular_array_slice(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.request_tabular_slice_2d(request)

    @pyqtSlot("QVariantMap", result="QVariantMap")
    def export_tabular_visible_rows(self, payload: dict[str, Any]) -> dict[str, Any]:
        properties = self._current_tabular_node_properties()
        if isinstance(properties, str):
            return self._tabular_export_result(False, error=properties)
        return self._export_tabular_visible_rows_from_properties(properties, payload)

    @pyqtSlot(str, "QVariantMap", result="QVariantMap")
    def export_tabular_visible_rows_for_node(self, node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        resolution = self._resolve_candidate(node_id)
        candidate = resolution.candidate
        if candidate is None:
            return self._tabular_export_result(False, error=resolution.error)
        if candidate.content_kind != TABULAR_PREVIEW_CONTENT_KIND:
            return self._tabular_export_result(False, error="The selected node is not a tabular data node.")
        properties = candidate.tabular_payload.get("properties")
        if not isinstance(properties, Mapping):
            return self._tabular_export_result(False, error="The selected tabular node has no exportable properties.")
        return self._export_tabular_visible_rows_from_properties(dict(properties), payload)

    @pyqtSlot("QVariantMap", result=bool)
    def save_tabular_table_view_state(self, state: dict[str, Any]) -> bool:
        if not self._open or self._content_kind != TABULAR_PREVIEW_CONTENT_KIND or not self._node_id:
            return False
        normalized = normalize_tabular_table_view_state(state if isinstance(state, Mapping) else {})
        if not self._set_node_property(self._node_id, TABULAR_TABLE_VIEW_STATE_PROPERTY, normalized):
            return False
        next_tabular_payload = copy.deepcopy(self._tabular_payload)
        next_tabular_payload[TABULAR_TABLE_VIEW_STATE_PROPERTY] = normalized
        properties = next_tabular_payload.get("properties")
        if isinstance(properties, dict):
            properties[TABULAR_TABLE_VIEW_STATE_PROPERTY] = copy.deepcopy(normalized)
        self._set_state(
            open_=self._open,
            node_id=self._node_id,
            workspace_id=self._workspace_id,
            content_kind=self._content_kind,
            title=self._title,
            media_payload=self._media_payload,
            viewer_payload=self._viewer_payload,
            web_editor_payload=self._web_editor_payload,
            web_page_payload=self._web_page_payload,
            plot_payload=self._plot_payload,
            tabular_payload=next_tabular_payload,
            last_error=self._last_error,
        )
        return True

    @pyqtSlot("QVariantList", result=bool)
    def save_tabular_selected_columns(self, columns: list[Any]) -> bool:
        if not self._open or self._content_kind != TABULAR_PREVIEW_CONTENT_KIND or not self._node_id:
            return False
        normalized = normalize_tabular_selected_columns(columns)
        if not self._set_node_property(self._node_id, TABULAR_SELECTED_COLUMNS_PROPERTY, normalized):
            return False
        next_tabular_payload = copy.deepcopy(self._tabular_payload)
        next_tabular_payload[TABULAR_SELECTED_COLUMNS_PROPERTY] = list(normalized)
        properties = next_tabular_payload.get("properties")
        if isinstance(properties, dict):
            properties[TABULAR_SELECTED_COLUMNS_PROPERTY] = list(normalized)
        self._set_state(
            open_=self._open,
            node_id=self._node_id,
            workspace_id=self._workspace_id,
            content_kind=self._content_kind,
            title=self._title,
            media_payload=self._media_payload,
            viewer_payload=self._viewer_payload,
            web_editor_payload=self._web_editor_payload,
            web_page_payload=self._web_page_payload,
            plot_payload=self._plot_payload,
            tabular_payload=next_tabular_payload,
            last_error=self._last_error,
        )
        return True

    @pyqtSlot("QVariantMap", result=bool)
    def save_web_page_browser_state(self, state: dict[str, Any]) -> bool:
        if not self._open or self._content_kind != WEB_PAGE_CONTENT_KIND or not self._node_id:
            return False
        if not self._web_page_browser_state_persistence_enabled():
            return False
        normalized = self._normalized_web_page_browser_state(state if isinstance(state, Mapping) else {})
        if not normalized:
            return False
        if not self._set_node_property(self._node_id, "browser_state", normalized):
            return False
        self._sync_web_page_payload_browser_state(normalized)
        return True

    def _current_pdf_page_state(self) -> tuple[int, int] | None:
        if not self._open or self._active_media_kind() != "pdf" or not self._node_id:
            return None
        media_payload = self._media_payload if isinstance(self._media_payload, Mapping) else {}
        pdf_preview = media_payload.get("pdf_preview")
        preview_payload = pdf_preview if isinstance(pdf_preview, Mapping) else {}
        page_count = _positive_int(media_payload.get("page_count") or preview_payload.get("page_count"))
        if page_count <= 0:
            return None
        current_page = _positive_int(
            media_payload.get("resolved_page_number")
            or preview_payload.get("resolved_page_number")
            or media_payload.get("page_number")
            or preview_payload.get("requested_page_number")
        )
        if current_page <= 0:
            current_page = 1
        return page_count, min(page_count, max(1, current_page))

    def _on_workspace_changed(self, _workspace_id: str = "") -> None:
        if self._terminal:
            return
        if self._open:
            self.request_close()

    def _on_nodes_changed(self, *_args: object) -> None:
        if self._terminal or not self._open:
            return
        resolution = self._resolve_candidate(self._node_id)
        if resolution.candidate is None:
            self.request_close()
            return
        self._open_candidate(resolution.candidate)

    def _open_candidate(
        self,
        candidate: _FullscreenCandidate,
        runtime_state: Mapping[str, Any] | None = None,
    ) -> None:
        if candidate.content_kind == "web_editor":
            bridge_changed = self._ensure_web_surface_bridge(
                candidate,
                candidate.web_editor_payload.get("excalidraw_state", {}),
            )
        else:
            bridge_changed = self._clear_web_surface_bridge()
        if candidate.content_kind == "script_editor":
            self._retarget_script_editor(candidate.node)
        media_payload = copy.deepcopy(candidate.media_payload)
        if (
            str(media_payload.get("media_kind", "") or "") == "video"
            and runtime_state is not None
        ):
            media_payload["transient_state"] = normalize_media_video_state(runtime_state)
        self._set_state(
            open_=True,
            node_id=candidate.node.node_id,
            workspace_id=candidate.workspace_id,
            content_kind=candidate.content_kind,
            title=candidate.title,
            media_payload=media_payload,
            viewer_payload=candidate.viewer_payload,
            web_editor_payload=candidate.web_editor_payload,
            web_page_payload=candidate.web_page_payload,
            plot_payload=candidate.plot_payload,
            tabular_payload=candidate.tabular_payload,
            last_error="",
            web_surface_bridge_changed=bridge_changed,
        )
        if (
            candidate.content_kind == TABULAR_PREVIEW_CONTENT_KIND
            and str(candidate.tabular_payload.get("preview_state", "")) == "loading"
        ):
            # Fullscreen opened against a cold cache: warm it on the worker
            # and re-resolve so the first rows appear without blocking open.
            self.schedule_tabular_payload_refresh()

    def _retarget_script_editor(self, node: "NodeInstance") -> None:
        script_editor = self._script_editor
        if script_editor is None:
            return
        if str(script_editor.current_node_id or "").strip() == str(
            node.node_id
        ).strip():
            return
        script_editor.set_node(node)

    def _close_with_error(self, error: str) -> None:
        self._set_state(
            open_=False,
            node_id="",
            workspace_id="",
            content_kind="",
            title="",
            media_payload={},
            viewer_payload={},
            web_editor_payload={},
            web_page_payload={},
            plot_payload={},
            tabular_payload={},
            last_error=str(error or "Content cannot be opened fullscreen."),
            web_surface_bridge_changed=self._clear_web_surface_bridge(),
        )

    def _set_state(
        self,
        *,
        open_: bool,
        node_id: str,
        workspace_id: str,
        content_kind: str,
        title: str,
        media_payload: dict[str, Any],
        viewer_payload: dict[str, Any],
        web_editor_payload: dict[str, Any],
        web_page_payload: dict[str, Any],
        plot_payload: dict[str, Any],
        tabular_payload: dict[str, Any],
        last_error: str,
        web_surface_bridge_changed: bool = False,
    ) -> None:
        next_media_payload = copy.deepcopy(media_payload)
        next_viewer_payload = copy.deepcopy(viewer_payload)
        next_web_editor_payload = copy.deepcopy(web_editor_payload)
        next_web_page_payload = copy.deepcopy(web_page_payload)
        next_plot_payload = copy.deepcopy(plot_payload)
        next_tabular_payload = copy.deepcopy(tabular_payload)
        changed = (
            bool(web_surface_bridge_changed)
            or self._open != bool(open_)
            or self._node_id != str(node_id or "")
            or self._workspace_id != str(workspace_id or "")
            or self._content_kind != str(content_kind or "")
            or self._title != str(title or "")
            or self._media_payload != next_media_payload
            or self._viewer_payload != next_viewer_payload
            or self._web_editor_payload != next_web_editor_payload
            or self._web_page_payload != next_web_page_payload
            or self._plot_payload != next_plot_payload
            or self._tabular_payload != next_tabular_payload
            or self._last_error != str(last_error or "")
        )
        if not changed:
            return
        self._open = bool(open_)
        self._node_id = str(node_id or "")
        self._workspace_id = str(workspace_id or "")
        self._content_kind = str(content_kind or "")
        self._title = str(title or "")
        self._media_payload = next_media_payload
        self._viewer_payload = next_viewer_payload
        self._web_editor_payload = next_web_editor_payload
        self._web_page_payload = next_web_page_payload
        self._plot_payload = next_plot_payload
        self._tabular_payload = next_tabular_payload
        self._last_error = str(last_error or "")
        self.content_fullscreen_changed.emit()

    def _active_media_kind(self) -> str:
        return str(self._media_payload.get("media_kind", "") or "").strip()

    def _ensure_web_surface_bridge(
        self,
        candidate: _FullscreenCandidate,
        scene_state: object,
    ) -> bool:
        if self._terminal:
            return False
        normalized_node_id = str(candidate.node.node_id or "").strip()
        artifact_scope = self._web_surface_artifact_scope(
            candidate.workspace_id,
            normalized_node_id,
        )
        normalized_state = copy.deepcopy(scene_state) if isinstance(scene_state, dict) else {}
        if (
            self._web_surface_bridge is not None
            and self._web_surface_bridge_node_id == normalized_node_id
            and self._web_surface_bridge_artifact_scope == artifact_scope
            and self._web_surface_bridge.load_state() == normalized_state
        ):
            return False
        self._clear_web_surface_bridge()
        factory = self._create_web_surface_artifact_service
        if factory is None:
            return False
        artifact_service = factory(
            candidate.workspace_id,
            candidate.workspace_name,
            normalized_node_id,
            candidate.title,
            str(candidate.spec.display_name or candidate.node.type_id),
        )
        if artifact_service is None:
            raise RuntimeError("Fullscreen Web artifact storage is unavailable.")
        bridge = _FullscreenWebSurfaceBridge(
            normalized_state,
            parent=self,
            preview_persist_callback=self._persist_web_editor_preview_result,
            artifact_service=artifact_service,
            artifact_scope=artifact_scope,
        )
        bridge.state_changed.connect(self._persist_web_editor_state)
        self._web_surface_bridge = bridge
        self._web_surface_bridge_node_id = normalized_node_id
        self._web_surface_bridge_artifact_scope = artifact_scope
        self._web_surface_bridge_initial_state = copy.deepcopy(normalized_state)
        return True

    def _clear_web_surface_bridge(self) -> bool:
        bridge = self._web_surface_bridge
        if bridge is None:
            self._web_surface_bridge_node_id = ""
            self._web_surface_bridge_artifact_scope = ""
            return False
        try:
            bridge.state_changed.disconnect(self._persist_web_editor_state)
        except (TypeError, RuntimeError):
            pass
        bridge.deleteLater()
        self._web_surface_bridge = None
        self._web_surface_bridge_node_id = ""
        self._web_surface_bridge_artifact_scope = ""
        self._web_surface_bridge_initial_state = {}
        return True

    @staticmethod
    def _web_surface_artifact_scope(workspace_id: str, node_id: str) -> str:
        return ":".join(
            part
            for part in (str(workspace_id or "").strip(), str(node_id or "").strip())
            if part
        )

    def _persist_web_editor_state(self) -> None:
        bridge = self._web_surface_bridge
        if bridge is None or not self._open or self._content_kind != "web_editor" or not self._node_id:
            return
        self._set_node_property(self._node_id, EXCALIDRAW_STATE_PROPERTY, bridge.load_state())

    def _materialize_web_editor_preview_result(self, preview_result: Any) -> Any:
        if self._preview_ref_from_export_result(preview_result):
            return preview_result
        payload = self._preview_payload_from_export_result(preview_result)
        bridge = self._web_surface_bridge
        if bridge is None:
            return preview_result
        if payload:
            materialized_result = bridge.export_preview(copy.deepcopy(payload))
            if self._preview_ref_from_export_result(materialized_result):
                return materialized_result
        if self._should_keep_current_web_editor_preview_ref(preview_result):
            return preview_result
        fallback_payload = self._fallback_preview_payload_for_close(preview_result)
        if not fallback_payload:
            return preview_result
        fallback_result = bridge.export_preview(fallback_payload)
        if self._preview_ref_from_export_result(fallback_result):
            return fallback_result
        return preview_result

    def _persist_web_editor_state_from_preview_result(self, preview_result: Any) -> None:
        scene_state = self._scene_state_from_export_result(preview_result)
        if not isinstance(scene_state, Mapping):
            return
        bridge = self._web_surface_bridge
        if bridge is not None and bridge.save_state(copy.deepcopy(dict(scene_state))):
            self._persist_web_editor_state()
            return
        if self._open and self._content_kind == "web_editor" and self._node_id:
            self._set_node_property(self._node_id, EXCALIDRAW_STATE_PROPERTY, copy.deepcopy(dict(scene_state)))

    def _persist_web_editor_preview_result(self, preview_result: Any) -> None:
        if not self._open or self._content_kind != "web_editor" or not self._node_id:
            return
        preview_ref = self._preview_ref_from_export_result(preview_result)
        if not preview_ref:
            return
        self._set_node_property(self._node_id, EXCALIDRAW_PREVIEW_REF_PROPERTY, preview_ref)

    def _web_page_browser_state_persistence_enabled(self) -> bool:
        return web_page_viewer_browser_state_persistence_enabled(
            self._web_page_payload.get("persist_browser_state", True)
        )

    def _normalized_web_page_browser_state(self, state: Mapping[str, Any]) -> dict[str, Any]:
        return normalize_web_page_viewer_browser_state(
            state,
            fallback_location=str(self._web_page_payload.get("current_location") or ""),
            require_location=True,
        )

    def _web_page_navigation_decision_payload(self, location: str) -> dict[str, Any]:
        if not str(location or "").strip():
            return {}
        return decide_web_navigation(location).as_payload()

    def _sync_web_page_payload_browser_state(self, browser_state: Mapping[str, Any]) -> None:
        next_payload = copy.deepcopy(self._web_page_payload)
        next_browser_state = copy.deepcopy(dict(browser_state))
        current_url = str(next_browser_state.get("current_url") or "").strip()
        next_payload["browser_state"] = next_browser_state
        next_payload["current_location"] = current_url
        if current_url:
            navigation_location = current_url
            if (
                current_url == str(next_payload.get("start_location") or "").strip()
                and str(next_payload.get("navigation_location") or "").strip()
            ):
                navigation_location = str(next_payload.get("navigation_location") or "").strip()
            next_payload["navigation_location"] = navigation_location
            decision_payload = self._web_page_navigation_decision_payload(navigation_location)
            if decision_payload:
                next_payload["navigation_decision"] = decision_payload
        properties = next_payload.get("properties")
        if isinstance(properties, dict):
            properties["browser_state"] = copy.deepcopy(next_browser_state)
        self._set_state(
            open_=self._open,
            node_id=self._node_id,
            workspace_id=self._workspace_id,
            content_kind=self._content_kind,
            title=self._title,
            media_payload=self._media_payload,
            viewer_payload=self._viewer_payload,
            web_editor_payload=self._web_editor_payload,
            web_page_payload=next_payload,
            plot_payload=self._plot_payload,
            tabular_payload=self._tabular_payload,
            last_error=self._last_error,
        )

    def _current_web_editor_node_properties(self) -> Mapping[str, Any]:
        if not self._node_id:
            return {}
        model = self._current_model()
        project = getattr(model, "project", None)
        workspaces = getattr(project, "workspaces", {}) if project is not None else {}
        workspace = workspaces.get(self._workspace_id) if isinstance(workspaces, Mapping) else None
        nodes = getattr(workspace, "nodes", {}) if workspace is not None else {}
        node = nodes.get(self._node_id) if isinstance(nodes, Mapping) else None
        properties = getattr(node, "properties", None)
        return properties if isinstance(properties, Mapping) else {}

    def _current_web_editor_preview_ref_value(self) -> Any:
        return self._current_web_editor_node_properties().get(EXCALIDRAW_PREVIEW_REF_PROPERTY)

    def _should_keep_current_web_editor_preview_ref(self, preview_result: Any) -> bool:
        current_preview_ref = self._current_web_editor_preview_ref_value()
        if not self._has_preview_ref_value(current_preview_ref):
            return False
        if not self._current_web_editor_preview_ref_resolves(current_preview_ref):
            return False
        return not self._web_editor_scene_changed_since_open(preview_result)

    def _web_editor_scene_changed_since_open(self, preview_result: Any) -> bool:
        scene_state = self._scene_state_from_export_result(preview_result)
        bridge = self._web_surface_bridge
        if not isinstance(scene_state, Mapping) and bridge is not None:
            loaded_state = bridge.load_state()
            if isinstance(loaded_state, Mapping):
                scene_state = loaded_state
        if not isinstance(scene_state, Mapping):
            return False
        return copy.deepcopy(dict(scene_state)) != self._web_surface_bridge_initial_state

    def _current_web_editor_preview_ref_resolves(self, value: Any) -> bool:
        artifact_ref = self._artifact_ref_from_preview_ref_value(value)
        if not artifact_ref:
            return True
        bridge = self._web_surface_bridge
        if bridge is None:
            return False
        return bridge.artifact_ref_resolves(artifact_ref)

    def _fallback_preview_payload_for_close(self, preview_result: Any) -> dict[str, Any]:
        scene_state = self._scene_state_from_export_result(preview_result)
        bridge = self._web_surface_bridge
        if not isinstance(scene_state, Mapping) and bridge is not None:
            loaded_state = bridge.load_state()
            if isinstance(loaded_state, Mapping):
                scene_state = loaded_state
        if not isinstance(scene_state, Mapping):
            return {}
        return _fallback_preview_payload_from_scene(scene_state)

    def _persist_video_fullscreen_state(self, node_id: str, state: Mapping[str, Any]) -> None:
        normalized = normalize_media_video_state(state)
        for key in (
            "position_ms",
            "playback_rate",
            "volume",
            "muted",
            "loop",
            "fit_mode",
            "timeline_bookmarks",
            "clip_enabled",
            "clip_start_ms",
            "clip_end_ms",
        ):
            self._set_node_property(node_id, key, normalized[key])

    @staticmethod
    def _video_trim_bridge_error(code: str, message: str) -> dict[str, Any]:
        return {
            "success": False,
            "created_node_id": "",
            "created_type_id": MEDIA_PANEL_TYPE_ID,
            "source_ref": "",
            "request_id": "",
            "error": {
                "code": str(code or "failed"),
                "message": str(message or "Video trim failed."),
            },
        }

    def _set_node_property(self, node_id: str, key: str, value: Any) -> bool:
        if self._terminal:
            return False
        try:
            self._scene_bridge.set_node_property(
                str(node_id or ""), str(key or ""), copy.deepcopy(value)
            )
        except Exception:  # noqa: BLE001
            return False
        return True

    def _set_plot_options_direct(self, key: str, value: Any) -> bool:
        properties = self._current_plot_node_properties()
        if properties is None:
            properties = copy.deepcopy(self._plot_payload.get("properties")) if isinstance(self._plot_payload, Mapping) else {}
        options = dict(properties.get("plot_options")) if isinstance(properties.get("plot_options"), Mapping) else {}
        options[str(key or "")] = copy.deepcopy(value)
        return self._set_node_property(self._node_id, "plot_options", options)

    def _current_plot_node_properties(self) -> dict[str, Any] | None:
        if not self._node_id:
            return None
        workspace_result = self._active_workspace()
        if isinstance(workspace_result, str):
            return None
        _workspace_id, workspace, _registry = workspace_result
        node = workspace.nodes.get(self._node_id)
        if node is None:
            return None
        return copy.deepcopy(dict(node.properties))

    def _refresh_active_plot_payload_option(self, key: str, value: Any) -> None:
        payload = copy.deepcopy(self._plot_payload)
        properties = self._current_plot_node_properties()
        if properties is None:
            properties = dict(payload.get("properties")) if isinstance(payload.get("properties"), Mapping) else {}
            options = dict(properties.get("plot_options")) if isinstance(properties.get("plot_options"), Mapping) else {}
            options[str(key or "")] = copy.deepcopy(value)
            properties["plot_options"] = options
        payload["properties"] = properties
        self._plot_payload = payload

    def _current_tabular_node_properties(self) -> dict[str, Any] | str:
        if not self._open or self._content_kind != TABULAR_PREVIEW_CONTENT_KIND or not self._node_id:
            return "No tabular fullscreen node is open."
        workspace_result = self._active_workspace()
        if isinstance(workspace_result, str):
            return workspace_result
        _workspace_id, workspace, _registry = workspace_result
        node = workspace.nodes.get(self._node_id)
        if node is None:
            return "The selected node is no longer available."
        if str(node.type_id) != TABULAR_DATA_INPUT_NODE_TYPE_ID:
            return "The active fullscreen node is not a tabular data node."
        return copy.deepcopy(node.properties)

    def _export_tabular_visible_rows_from_properties(
        self,
        properties: Mapping[str, Any],
        payload: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        normalized_payload = payload if isinstance(payload, Mapping) else {}
        request = self._tabular_export_request(normalized_payload)
        preview_kind = self._tabular_export_kind(normalized_payload)
        if preview_kind not in {"table", "array"}:
            preview = self._ensure_tabular_preview_provider().describe_preview(
                properties,
                request,
                mode="fullscreen",
            )
            preview_kind = str(preview.get("preview_kind", "") or "").strip().lower()
        else:
            preview = (
                self._ensure_tabular_preview_provider().table_window_payload(
                    properties,
                    request,
                    mode="fullscreen",
                    include_schema=False,
                )
                if preview_kind == "table"
                else self._ensure_tabular_preview_provider().array_slice_payload(
                    properties,
                    request,
                    mode="fullscreen",
                )
            )
        if preview_kind not in {"table", "array"}:
            return self._tabular_export_result(False, error="The active tabular preview is not exportable.")
        if str(preview.get("state", "") or "") != "ready":
            message = str(preview.get("message", "") or "The active tabular preview is not ready to export.")
            return self._tabular_export_result(False, error=message)

        output_path = self._pick_tabular_export_path(preview_kind, properties)
        if not output_path:
            return self._tabular_export_result(False)
        try:
            if preview_kind == "table":
                window = preview.get("window")
                window_payload = window if isinstance(window, Mapping) else {}
                columns = [str(column) for column in self._tabular_sequence(window_payload.get("columns"))]
                rows = [
                    dict(row) if isinstance(row, Mapping) else {}
                    for row in self._tabular_sequence(window_payload.get("rows"))
                ]
                write_table_rows_to_path(Path(output_path), columns=columns, rows=rows)
            else:
                slice_payload = preview.get("slice_2d")
                normalized_slice = slice_payload if isinstance(slice_payload, Mapping) else {}
                rows = [
                    list(row) if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)) else [row]
                    for row in self._tabular_sequence(normalized_slice.get("values"))
                ]
                write_array_rows_to_path(Path(output_path), rows=rows)
        except Exception as exc:  # noqa: BLE001
            return self._tabular_export_result(False, path=output_path, error=str(exc))
        return self._tabular_export_result(True, path=output_path)

    @staticmethod
    def _tabular_export_result(ok: bool, *, path: str = "", error: str = "") -> dict[str, Any]:
        return {
            "ok": bool(ok),
            "path": str(path or ""),
            "error": str(error or ""),
        }

    @staticmethod
    def _tabular_export_kind(payload: Mapping[str, Any]) -> str:
        for key in ("preview_kind", "kind"):
            text = str(payload.get(key, "") or "").strip().lower()
            if text in {"table", "array"}:
                return text
        preview = payload.get("preview")
        if isinstance(preview, Mapping):
            return ContentFullscreenBridge._tabular_export_kind(preview)
        return ""

    @staticmethod
    def _tabular_export_request(payload: Mapping[str, Any]) -> dict[str, Any]:
        request = payload.get("request")
        if isinstance(request, Mapping):
            return copy.deepcopy(dict(request))
        output: dict[str, Any] = {}
        for key in (
            "row_offset",
            "row_limit",
            "column_offset",
            "column_limit",
            "columns",
            "sort",
            "filters",
            "filter",
            "search",
        ):
            if key in payload:
                output[key] = copy.deepcopy(payload[key])
        return output

    @staticmethod
    def _tabular_sequence(value: Any) -> list[Any]:
        if isinstance(value, list):
            return list(value)
        if isinstance(value, tuple):
            return list(value)
        return []

    def _pick_tabular_export_path(self, preview_kind: str, properties: Mapping[str, Any]) -> str:
        picker = self._save_file_dialog
        if self._terminal or picker is None:
            return ""
        default_suffix = ".csv"
        file_filter = (
            TABULAR_ARRAY_OUTPUT_FILES_FILTER
            if preview_kind == "array"
            else TABULAR_TABLE_OUTPUT_FILES_FILTER
        )
        suggested_path = self._suggested_tabular_export_path(preview_kind, properties, default_suffix)
        return str(
            picker(
                title="Export Visible Rows",
                suggested_path=suggested_path,
                file_filter=file_filter,
                default_suffix=default_suffix,
            )
            or ""
        ).strip()

    def _suggested_tabular_export_path(
        self,
        preview_kind: str,
        properties: Mapping[str, Any],
        suffix: str,
    ) -> str:
        raw_source = str(properties.get("path", "") or "").strip()
        stem = "array_visible" if preview_kind == "array" else "table_visible"
        if raw_source and "://" not in raw_source:
            try:
                source_stem = Path(raw_source).expanduser().stem
            except Exception:  # noqa: BLE001
                source_stem = ""
            if source_stem:
                stem = f"{source_stem}_visible"
        safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stem).strip("_")
        if not safe_stem:
            safe_stem = "tabular_visible"
        project_path = self._current_project_path()
        if project_path:
            parent = Path(project_path).expanduser().parent
        else:
            parent = Path.cwd()
        return str(parent / f"{safe_stem[:80]}{suffix}")

    @staticmethod
    def _tabular_error_payload(message: str) -> dict[str, Any]:
        return {
            "state": "error",
            "content_kind": TABULAR_PREVIEW_CONTENT_KIND,
            "preview_kind": "",
            "message": str(message or "Tabular preview is unavailable."),
            "error": {
                "code": "tabular_fullscreen_unavailable",
                "message": str(message or "Tabular preview is unavailable."),
                "recoverable": True,
            },
        }

    def _current_project_path(self) -> str:
        project_path, _metadata = self._project_context()
        return str(project_path or "").strip()

    def _current_model(self) -> "GraphModel | None":
        provider = self._model_provider
        return provider() if provider is not None else None

    @staticmethod
    def _preview_ref_from_export_result(preview_result: Any) -> dict[str, Any]:
        if not isinstance(preview_result, Mapping) or preview_result.get("ok") is not True:
            return {}
        artifact_ref = str(
            preview_result.get("artifact_ref") or preview_result.get("preview_ref") or ""
        ).strip()
        if not artifact_ref:
            return {}
        preview_ref: dict[str, Any] = {
            "artifact_ref": artifact_ref,
            "mime_type": str(preview_result.get("mime_type") or "image/png"),
            "status": "ready",
        }
        for key in ("width", "height", "size"):
            value = _positive_int(preview_result.get(key))
            if value > 0:
                preview_ref[key] = value
        sha256 = str(preview_result.get("sha256") or "").strip()
        if sha256:
            preview_ref["sha256"] = sha256
        return preview_ref

    @staticmethod
    def _has_preview_ref_value(value: Any) -> bool:
        if isinstance(value, Mapping):
            return any(
                str(value.get(key) or "").strip()
                for key in ("artifact_ref", "preview_ref", "uri", "ref", "path")
            )
        return bool(str(value or "").strip())

    @staticmethod
    def _artifact_ref_from_preview_ref_value(value: Any) -> str:
        if isinstance(value, Mapping):
            for key in ("artifact_ref", "preview_ref", "ref", "uri"):
                text = str(value.get(key) or "").strip()
                if parse_artifact_ref(text) is not None:
                    return text
            return ""
        text = str(value or "").strip()
        return text if parse_artifact_ref(text) is not None else ""

    @staticmethod
    def _preview_payload_from_export_result(preview_result: Any) -> dict[str, Any]:
        if not isinstance(preview_result, Mapping):
            return {}
        payload = preview_result.get("host_payload") or preview_result.get("hostPayload")
        if isinstance(payload, Mapping):
            return dict(payload)
        if preview_result.get("dataURL") or preview_result.get("data_url") or preview_result.get("previewDataURL"):
            return dict(preview_result)
        return {}

    @staticmethod
    def _scene_state_from_export_result(preview_result: Any) -> Mapping[str, Any] | None:
        if not isinstance(preview_result, Mapping):
            return None
        scene_state = preview_result["scene_state"] if "scene_state" in preview_result else preview_result.get("sceneState")
        if isinstance(scene_state, Mapping):
            return scene_state
        payload = preview_result.get("host_payload") or preview_result.get("hostPayload")
        if isinstance(payload, Mapping):
            scene_state = payload["scene_state"] if "scene_state" in payload else payload.get("sceneState")
            if isinstance(scene_state, Mapping):
                return scene_state
        return None


__all__ = ["ContentFullscreenBridge"]
