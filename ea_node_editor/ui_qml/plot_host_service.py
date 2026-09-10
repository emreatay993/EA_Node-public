# Purpose: Own native plot binding, cached previews, and inline/detached/fullscreen presentation.
# Map: subsystems/viewer_surfaces.md
# Tests: tests/test_plot_host_service.py
# Landmarks: _PlotHostSnapshot; _DetachedPlotWindow; _PlotHostPresentationService; PlotHostService; presentation reconciliation

from __future__ import annotations

import copy
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, QSize, Qt, QTimer, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QCloseEvent, QImage
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ea_node_editor.common.coercions import coerce_int as _coerce_int
from ea_node_editor.execution.plot_backend import (
    AUTO_PLOT_BACKEND_ID,
    PlotBackendRegistry,
    PlotRenderRequest,
    build_plot_render_request,
    create_default_plot_backend_registry,
    normalize_generic_plot_series,
    normalize_plot_type,
    plot_options_from_properties,
    plot_render_request_from_payload,
)
from ea_node_editor.execution.plot_backend_matplotlib import MATPLOTLIB_PLOT_BACKEND_ID
from ea_node_editor.execution.plot_backend_pyqtgraph import PYQTGRAPH_PLOT_BACKEND_ID
from ea_node_editor.execution.plot_backend_pyvista import PYVISTA_PLOT_BACKEND_ID
from ea_node_editor.ui_qml.embedded_viewer_overlay_manager import (
    EmbeddedViewerOverlayManager,
    EmbeddedViewerOverlaySpec,
)
from ea_node_editor.ui_qml.native_overlay_owners import PLOT_HOST_OVERLAY_OWNER
from ea_node_editor.ui_qml.native_presentation_handoff import (
    NativePresentationHandoff,
)
from ea_node_editor.ui.plot_preview_cache_provider import PlotPreviewCacheImageProvider
from ea_node_editor.ui_qml.plot_widget_binder import (
    MatplotlibPlotWidgetBinder,
    PlotWidgetBindRequest,
    PlotWidgetBinder,
    PlotWidgetBinderRegistry,
    PlotWidgetNoBind,
    PlotWidgetReleaseRequest,
    PyQtGraphPlotWidgetBinder,
    PyVistaPlotWidgetBinder,
)
from ea_node_editor.ui_qml.plot_live_backend_resolution import resolve_plot_live_backend_id

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.content_fullscreen_bridge import ContentFullscreenBridge
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

_OverlayKey = tuple[str, str]
_PRESENTATION_DETACHED = "detached"
_PRESENTATION_OVERLAY = "overlay"
_LIVE_PLOT_OPTION_KEYS = ("plot_theme", "hover_readout", "vertical_guide", "crosshair")

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


def _string(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((_string(key), _freeze_value(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _plot_options(properties: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(plot_options_from_properties(properties))


def _live_plot_options(payload: Mapping[str, Any]) -> dict[str, Any]:
    properties = _mapping(payload.get("properties"))
    options = _mapping(properties.get("plot_options"))
    return {key: copy.deepcopy(options[key]) for key in _LIVE_PLOT_OPTION_KEYS if key in options}


def _with_live_plot_options(request: PlotRenderRequest, payload: Mapping[str, Any]) -> PlotRenderRequest:
    live_options = _live_plot_options(payload)
    if not live_options:
        return request
    options = dict(request.options)
    options.update(live_options)
    return PlotRenderRequest(
        plot_type=request.plot_type,
        series=request.series,
        title=request.title,
        x_label=request.x_label,
        y_label=request.y_label,
        options=options,
    )


def _render_request_from_payload(
    payload: Mapping[str, Any],
    *,
    workspace_id: str = "",
) -> PlotRenderRequest | None:
    plot_surface = _mapping(payload.get("plot_surface"))
    signature = _string(plot_surface.get("series_signature"))
    if signature:
        # Auto-preview render requests live in the async cache, never in the
        # scene payload. A pending/stale signature means "no live bind yet" —
        # the QML surface keeps showing the cached preview image.
        from ea_node_editor.ui_qml.plot_auto_preview_service import (
            shared_plot_render_request_cache,
        )

        node_id = _string(payload.get("node_id"))
        revision = _coerce_int(plot_surface.get("render_revision"), default=0)
        entry = shared_plot_render_request_cache().get(
            _string(payload.get("workspace_id")) or workspace_id,
            node_id,
        )
        if (
            entry is None
            or entry.error
            or not entry.request_payload
            or revision <= 0
            or entry.revision != revision
        ):
            return None
        explicit_request = dict(entry.request_payload)
        if not explicit_request.get("plot_type"):
            explicit_request["plot_type"] = plot_surface.get("plot_type")
        return _with_live_plot_options(plot_render_request_from_payload(explicit_request), payload)

    explicit_request = _mapping(plot_surface.get("render_request"))
    if not explicit_request:
        explicit_request = _mapping(payload.get("render_request"))
    if explicit_request:
        if not explicit_request.get("plot_type"):
            explicit_request["plot_type"] = plot_surface.get("plot_type")
        return _with_live_plot_options(plot_render_request_from_payload(explicit_request), payload)

    properties = _mapping(payload.get("properties"))
    series = properties.get("series")
    return _with_live_plot_options(
        build_plot_render_request(
            plot_type=plot_surface.get("plot_type") or payload.get("surface_variant"),
            series=normalize_generic_plot_series(series),
            properties={**properties, "title": properties.get("title") or payload.get("title")},
            options=_plot_options(properties),
        ),
        payload,
    )


@dataclass(slots=True, frozen=True)
class _PlotHostSnapshot:
    workspace_id: str
    node_id: str
    plot_type: str
    backend_id: str
    render_request: PlotRenderRequest
    render_revision: int = 0
    properties: dict[str, Any] = field(default_factory=dict)
    plot_surface: dict[str, Any] = field(default_factory=dict)

    @property
    def overlay_key(self) -> _OverlayKey:
        return (self.workspace_id, self.node_id)

    def overlay_spec(self) -> EmbeddedViewerOverlaySpec:
        return EmbeddedViewerOverlaySpec(
            workspace_id=self.workspace_id,
            node_id=self.node_id,
            session_id=f"plot::{self.node_id}",
        )

    def bind_request(self, *, container, current_widget) -> PlotWidgetBindRequest:  # noqa: ANN001
        return PlotWidgetBindRequest(
            workspace_id=self.workspace_id,
            node_id=self.node_id,
            plot_type=self.plot_type,
            backend_id=self.backend_id,
            render_request=self.render_request,
            render_revision=self.render_revision,
            properties=copy.deepcopy(self.properties),
            plot_surface=copy.deepcopy(self.plot_surface),
            container=container,
            current_widget=current_widget,
        )

    def release_request(self, *, container, widget, reason: str) -> PlotWidgetReleaseRequest:  # noqa: ANN001
        return PlotWidgetReleaseRequest(
            workspace_id=self.workspace_id,
            node_id=self.node_id,
            plot_type=self.plot_type,
            backend_id=self.backend_id,
            render_revision=self.render_revision,
            properties=copy.deepcopy(self.properties),
            plot_surface=copy.deepcopy(self.plot_surface),
            container=container,
            widget=widget,
            reason=reason,
        )


@dataclass(slots=True)
class _BoundPlotOverlay:
    binder: PlotWidgetBinder
    snapshot: _PlotHostSnapshot
    signature: tuple[Any, ...]
    presentation: str = _PRESENTATION_OVERLAY
    container: QWidget | None = None
    widget: QWidget | None = None


class _DetachedPlotWindow(QWidget):
    def __init__(
        self,
        *,
        key: _OverlayKey,
        title: str,
        on_closed: Callable[[_OverlayKey], None],
    ) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self._key = key
        self._on_closed = on_closed
        self._service_closing = False
        self.widget: QWidget | None = None
        self.setObjectName(f"detachedPlotWindow::{key[0]}::{key[1]}")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle(title)
        self.resize(900, 650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.container = QWidget(self)
        self.container.setObjectName(f"detachedPlotContainer::{key[0]}::{key[1]}")
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        layout.addWidget(self.container)

    def attach_widget(self, widget: QWidget) -> None:
        if self.widget is widget:
            self.show()
            widget.show()
            return
        if self.widget is not None:
            self.detach_widget(self.widget)
        if widget.parent() is not self.container:
            widget.setParent(self.container)
        layout = self.container.layout()
        if layout is not None and layout.indexOf(widget) < 0:
            layout.addWidget(widget)
        self.widget = widget
        widget.show()
        self.show()

    def detach_widget(self, widget: QWidget | None = None) -> None:
        target = widget or self.widget
        if target is None:
            return
        layout = self.container.layout()
        if layout is not None:
            layout.removeWidget(target)
        if self.widget is target:
            self.widget = None

    def close_from_service(self) -> None:
        self._service_closing = True
        try:
            self.close()
        finally:
            self._service_closing = False

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if not self._service_closing:
            self._on_closed(self._key)
        super().closeEvent(event)


class _PlotHostPresentationService:
    def __init__(
        self,
        *,
        scene_bridge_provider: Callable[[], "GraphSceneBridge | None"],
        content_fullscreen_bridge_provider: Callable[[], QObject | None],
        embedded_interaction_active_provider: Callable[[str, str], bool],
        backend_registry_provider: Callable[[], PlotBackendRegistry],
    ) -> None:
        self._scene_bridge_provider = scene_bridge_provider
        self._content_fullscreen_bridge_provider = content_fullscreen_bridge_provider
        self._embedded_interaction_active_provider = embedded_interaction_active_provider
        self._backend_registry_provider = backend_registry_provider

    def desired_overlays(
        self,
        binder_registry_provider: Callable[[], PlotWidgetBinderRegistry],
    ) -> tuple[dict[_OverlayKey, tuple[_PlotHostSnapshot, PlotWidgetBinder]], list[str]]:
        desired: dict[_OverlayKey, tuple[_PlotHostSnapshot, PlotWidgetBinder]] = {}
        errors: list[str] = []
        binder_registry: PlotWidgetBinderRegistry | None = None
        fullscreen_key = self.content_fullscreen_overlay_key()
        content_fullscreen_open = self.content_fullscreen_open()
        for payload in self.scene_plot_payloads():
            node_id = _string(payload.get("node_id"))
            workspace_id = _string(payload.get("workspace_id")) or self.active_workspace_id()
            if not node_id or not workspace_id:
                continue
            key = (workspace_id, node_id)
            embedded_active = self._embedded_interaction_active_provider(workspace_id, node_id)
            fullscreen_active = fullscreen_key == key
            if content_fullscreen_open and not fullscreen_active:
                continue
            if not fullscreen_active and not self.should_host_embedded(payload, embedded_active=embedded_active):
                continue
            snapshot = self.snapshot_from_node_payload(payload, workspace_id=workspace_id)
            if snapshot is None:
                continue
            if binder_registry is None:
                binder_registry = binder_registry_provider()
            binder = binder_registry.lookup(snapshot.backend_id)
            if binder is None:
                errors.append(f"No plot widget binder registered for backend '{snapshot.backend_id}'.")
                continue
            desired[key] = (snapshot, binder)
        fullscreen_snapshot = self.content_fullscreen_snapshot()
        if fullscreen_snapshot is not None and fullscreen_snapshot.overlay_key not in desired:
            if binder_registry is None:
                binder_registry = binder_registry_provider()
            binder = binder_registry.lookup(fullscreen_snapshot.backend_id)
            if binder is None:
                errors.append(f"No plot widget binder registered for backend '{fullscreen_snapshot.backend_id}'.")
            else:
                desired[fullscreen_snapshot.overlay_key] = (fullscreen_snapshot, binder)
        return desired, errors

    def scene_plot_payloads(self) -> tuple[dict[str, Any], ...]:
        scene_bridge = self._scene_bridge_provider()
        if scene_bridge is None:
            return ()
        try:
            model = getattr(scene_bridge, "nodes_model", [])
        except Exception:  # noqa: BLE001
            return ()
        payloads: list[dict[str, Any]] = []
        for item in model if isinstance(model, list) else []:
            payload = _mapping(item)
            if _mapping(payload.get("plot_surface")):
                payloads.append(payload)
        return tuple(payloads)

    def active_workspace_id(self) -> str:
        scene_bridge = self._scene_bridge_provider()
        return _string(getattr(scene_bridge, "workspace_id", "")) if scene_bridge is not None else ""

    def content_fullscreen_open(self) -> bool:
        bridge = self._content_fullscreen_bridge_provider()
        return bool(getattr(bridge, "open", False)) if bridge is not None else False

    def content_fullscreen_overlay_key(self) -> _OverlayKey | None:
        bridge = self._content_fullscreen_bridge_provider()
        if bridge is None or not bool(getattr(bridge, "open", False)):
            return None
        if _string(getattr(bridge, "content_kind", "")) != "plot":
            return None
        workspace_id = _string(getattr(bridge, "workspace_id", ""))
        node_id = _string(getattr(bridge, "node_id", ""))
        if not workspace_id or not node_id:
            return None
        return (workspace_id, node_id)

    def content_fullscreen_overlay_spec(self) -> EmbeddedViewerOverlaySpec | None:
        key = self.content_fullscreen_overlay_key()
        if key is None:
            return None
        return EmbeddedViewerOverlaySpec(workspace_id=key[0], node_id=key[1], session_id=f"plot::{key[1]}")

    def content_fullscreen_snapshot(self) -> _PlotHostSnapshot | None:
        bridge = self._content_fullscreen_bridge_provider()
        if bridge is None or _string(getattr(bridge, "content_kind", "")) != "plot":
            return None
        payload = _mapping(getattr(bridge, "plot_payload", {}))
        if not payload:
            return None
        payload.setdefault("node_id", _string(getattr(bridge, "node_id", "")))
        payload.setdefault("workspace_id", _string(getattr(bridge, "workspace_id", "")))
        return self.snapshot_from_node_payload(payload, workspace_id=_string(payload.get("workspace_id")))

    @staticmethod
    def should_host_embedded(payload: Mapping[str, Any], *, embedded_active: bool) -> bool:
        plot_surface = _mapping(payload.get("plot_surface"))
        if _bool(plot_surface.get("embedded_rendering_suppressed"), False):
            return False
        return bool(embedded_active)

    def snapshot_from_node_payload(
        self,
        payload: Mapping[str, Any],
        *,
        workspace_id: str,
    ) -> _PlotHostSnapshot | None:
        plot_surface = _mapping(payload.get("plot_surface"))
        try:
            plot_type = normalize_plot_type(plot_surface.get("plot_type") or payload.get("surface_variant"))
        except ValueError:
            return None
        if not plot_type:
            return None
        node_id = _string(payload.get("node_id"))
        if not workspace_id or not node_id:
            return None
        backend_id = self.resolve_live_backend_id(
            plot_type=plot_type,
            requested_backend_id=_string(_mapping(payload.get("properties")).get("backend")) or AUTO_PLOT_BACKEND_ID,
        )
        if not backend_id:
            return None
        render_request = _render_request_from_payload(payload, workspace_id=workspace_id)
        if render_request is None:
            return None
        return _PlotHostSnapshot(
            workspace_id=workspace_id,
            node_id=node_id,
            plot_type=plot_type,
            backend_id=backend_id,
            render_request=render_request,
            render_revision=self.render_revision(payload),
            properties=_mapping(payload.get("properties")),
            plot_surface=plot_surface,
        )

    def resolve_live_backend_id(self, *, plot_type: str, requested_backend_id: str) -> str:
        return resolve_plot_live_backend_id(
            self._backend_registry_provider(),
            plot_type=plot_type,
            requested_backend_id=requested_backend_id,
        )

    @staticmethod
    def render_revision(payload: Mapping[str, Any]) -> int:
        explicit = payload.get("plot_render_revision")
        if explicit is None:
            explicit = _mapping(payload.get("plot_surface")).get("render_revision")
        if explicit is not None:
            return _coerce_int(explicit, default=0)
        signature = _freeze_value(
            {
                "title": payload.get("title"),
                "properties": _mapping(payload.get("properties")),
                "plot_surface": _mapping(payload.get("plot_surface")),
            }
        )
        return zlib.adler32(repr(signature).encode("utf-8")) & 0x7FFFFFFF

    @staticmethod
    def binding_signature(snapshot: _PlotHostSnapshot) -> tuple[Any, ...]:
        # The render revision already covers the full render request; freezing
        # the (potentially huge) series payload per sync is the O(cells) cost
        # this signature used to impose on every scene publish.
        return (
            snapshot.backend_id,
            snapshot.plot_type,
            snapshot.render_revision,
            snapshot.render_request.title,
            tuple((key, _freeze_value(snapshot.render_request.options.get(key))) for key in _LIVE_PLOT_OPTION_KEYS),
        )


class PlotHostService(QObject):
    state_changed = pyqtSignal()
    last_error_changed = pyqtSignal()
    preview_cache_changed = pyqtSignal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        active_workspace_id_provider: Callable[[], str],
        scene_bridge: "GraphSceneBridge | None" = None,
        content_fullscreen_bridge: "ContentFullscreenBridge",
        overlay_manager: EmbeddedViewerOverlayManager | None = None,
        backend_registry: PlotBackendRegistry | None = None,
        preview_cache_provider: PlotPreviewCacheImageProvider | None = None,
    ) -> None:
        super().__init__(parent)
        self._active_workspace_id_provider: Callable[[], str] | None = (
            active_workspace_id_provider
        )
        self._scene_bridge = scene_bridge
        self._overlay_manager = overlay_manager
        self._content_fullscreen_bridge: QObject | None = content_fullscreen_bridge
        self._preview_cache_provider = preview_cache_provider
        self._backend_registry = backend_registry or create_default_plot_backend_registry()
        self._binder_registry = PlotWidgetBinderRegistry()
        self._binders_initialized = False
        self._custom_binders: dict[str, PlotWidgetBinder] = {}
        self._bound_overlays: dict[_OverlayKey, _BoundPlotOverlay] = {}
        self._detached_windows: dict[_OverlayKey, _DetachedPlotWindow] = {}
        self._embedded_interaction_active: set[_OverlayKey] = set()
        self._native_presentation_handoff = NativePresentationHandoff(
            overlay_manager_provider=lambda: self._overlay_manager,
            completion_callback=self._complete_embedded_exit_demotion,
            timeout_ms=300,
        )
        self._plot_render_signatures: dict[_OverlayKey, tuple[Any, ...]] = {}
        self._plot_view_states: dict[_OverlayKey, tuple[tuple[Any, ...], object]] = {}
        self._preview_cache_revision = 0
        self._plot_overlay_revision = 0
        self._last_error = ""
        self._sync_queued = False
        self._sync_suspended = False
        self._shutdown = False
        self._owns_content_fullscreen_target = False
        self._plot_content_fullscreen_target_key: _OverlayKey | None = None
        self._presentation_service = _PlotHostPresentationService(
            scene_bridge_provider=lambda: self._scene_bridge,
            content_fullscreen_bridge_provider=lambda: self._content_fullscreen_bridge,
            embedded_interaction_active_provider=self._embedded_interaction_active_for,
            backend_registry_provider=lambda: self._backend_registry,
        )
        self._connect_signals()
        self._schedule_sync()

    @property
    def binder_registry(self) -> PlotWidgetBinderRegistry:
        return self._ensure_binders_initialized()

    @property
    def overlay_manager(self) -> EmbeddedViewerOverlayManager | None:
        return self._overlay_manager

    @pyqtProperty(int, notify=state_changed)
    def active_overlay_count(self) -> int:
        return len(self._bound_overlays)

    @pyqtProperty(int, notify=state_changed)
    def plot_overlay_revision(self) -> int:
        return self._plot_overlay_revision

    @pyqtProperty(int, notify=state_changed)
    def detached_window_count(self) -> int:
        return len(self._detached_windows)

    @pyqtProperty(str, notify=last_error_changed)
    def last_error(self) -> str:
        return self._last_error

    @pyqtProperty(int, notify=preview_cache_changed)
    def preview_cache_revision(self) -> int:
        return self._preview_cache_revision

    def register_binder(self, backend_id: str, binder: PlotWidgetBinder) -> None:
        if self._shutdown:
            return
        normalized_backend_id = _string(backend_id)
        if not normalized_backend_id:
            raise ValueError("plot widget binder backend_id is required")
        self._custom_binders[normalized_backend_id] = binder
        if self._binders_initialized:
            self._binder_registry.register(normalized_backend_id, binder)
        self._schedule_sync()

    def set_backend_registry(self, registry: PlotBackendRegistry) -> None:
        if self._shutdown:
            return
        self._backend_registry = registry
        self._schedule_sync()

    def set_overlay_manager(self, overlay_manager: EmbeddedViewerOverlayManager | None) -> None:
        if self._shutdown:
            return
        if self._overlay_manager is overlay_manager:
            return
        self._native_presentation_handoff.flush()
        self._release_all_bindings(reason="overlay_manager_replaced")
        previous_overlay_manager = self._overlay_manager
        self._overlay_manager = overlay_manager
        if previous_overlay_manager is not None:
            self._set_plot_content_fullscreen_target(previous_overlay_manager, None, force_clear=True)
            self._set_plot_active_overlays(previous_overlay_manager, ())
        self._schedule_sync()

    @pyqtSlot(str, bool)
    def set_embedded_interaction_active(self, node_id: str, active: bool) -> None:
        if self._shutdown:
            return
        workspace_id = self._active_workspace_id()
        normalized_node_id = _string(node_id)
        if not workspace_id or not normalized_node_id:
            return
        key = (workspace_id, normalized_node_id)
        changed = False
        if bool(active):
            self._native_presentation_handoff.cancel(key)
            if key not in self._embedded_interaction_active:
                self._embedded_interaction_active.add(key)
                changed = True
        elif key in self._embedded_interaction_active:
            demotion_deferred = False
            if self._presentation_service.content_fullscreen_overlay_key() == key:
                self._capture_cached_live_state_for_key(key)
            else:
                demotion_deferred = self._capture_embedded_exit_state(key)
            self._embedded_interaction_active.remove(key)
            if not demotion_deferred:
                self._release_inactive_embedded_overlay(key)
            changed = True
        if changed:
            self._schedule_sync()

    @pyqtSlot(str, str)
    def notify_cached_preview_swapped(self, node_id: str, source: str) -> None:
        """QML confirms the cached preview Image now shows ``source``.

        The live-exit release that hides the plot overlay must wait until
        the frame containing the freshly captured raster has actually
        rendered, or the reveal repaints a stale backing store and the old
        preview flashes between live and proxy modes.
        """
        if self._shutdown:
            return
        key = self._key_for_node_id(node_id)
        if key is None:
            return
        self._native_presentation_handoff.notify_preview_swapped(key, source)

    def _capture_embedded_exit_state(self, key: _OverlayKey) -> bool:
        """Capture the live frame and report whether demotion was deferred."""
        provider = self._preview_cache_provider
        source_before = provider.preview_source(key[0], key[1]) if provider is not None else ""
        self._capture_cached_live_state_for_key(key)
        if provider is None:
            return False
        source_after = provider.preview_source(key[0], key[1])
        if not source_after or source_after == source_before:
            return False
        if not self._embedded_exit_overlay_visible(key):
            return False
        return self._native_presentation_handoff.begin(
            key, expected_source=source_after
        )

    def _embedded_exit_overlay_visible(self, key: _OverlayKey) -> bool:
        bound = self._bound_overlays.get(key)
        if bound is None or bound.presentation != _PRESENTATION_OVERLAY:
            return False
        overlay_manager = self._overlay_manager
        if overlay_manager is None:
            return False
        if overlay_manager.overlay_widget(key[1], workspace_id=key[0]) is None:
            return False
        geometry_ready = getattr(overlay_manager, "overlay_geometry_ready", None)
        if callable(geometry_ready):
            try:
                return bool(geometry_ready(key[1], workspace_id=key[0]))
            except Exception as exc:  # noqa: BLE001
                self._set_last_error(str(exc))
                return False
        return True

    def _complete_embedded_exit_demotion(self, key: _OverlayKey) -> None:
        if self._shutdown:
            return
        if key in self._embedded_interaction_active:
            return
        if self._presentation_service.content_fullscreen_overlay_key() == key:
            return
        self._release_inactive_embedded_overlay(key)
        self._schedule_sync()

    @pyqtSlot(str, result=str)
    def cached_preview_source(self, node_id: str) -> str:
        provider = self._preview_cache_provider
        if self._shutdown or provider is None:
            return ""
        key = self._key_for_node_id(node_id)
        if key is None:
            return ""
        return provider.preview_source(key[0], key[1])

    def capture_overlay_preview_image(self, node_id: str, *, workspace_id: str = "") -> QImage:
        if self._shutdown:
            return QImage()
        normalized_workspace_id = _string(workspace_id) or self._active_workspace_id()
        normalized_node_id = _string(node_id)
        if not normalized_workspace_id or not normalized_node_id:
            return QImage()
        bound = self._bound_overlays.get((normalized_workspace_id, normalized_node_id))
        overlay_manager = self._overlay_manager
        if bound is None or overlay_manager is None:
            return QImage()
        widget = overlay_manager.overlay_widget(normalized_node_id, workspace_id=normalized_workspace_id)
        if not isinstance(widget, QWidget):
            return QImage()
        capture = getattr(bound.binder, "capture_preview_image", None)
        if callable(capture):
            try:
                captured = capture(widget)
            except Exception as exc:  # noqa: BLE001
                self._set_last_error(str(exc))
            else:
                if isinstance(captured, QImage) and not captured.isNull():
                    return self._normalized_overlay_preview_image(
                        (normalized_workspace_id, normalized_node_id),
                        captured,
                    )
        try:
            pixmap = widget.grab()
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return QImage()
        image = pixmap.toImage() if not pixmap.isNull() else QImage()
        if image.isNull():
            return QImage()
        return self._normalized_overlay_preview_image(
            (normalized_workspace_id, normalized_node_id),
            image,
        )

    def _normalized_overlay_preview_image(self, key: _OverlayKey, image: QImage) -> QImage:
        if image.isNull():
            return QImage()
        overlay_manager = self._overlay_manager
        if overlay_manager is None:
            return image.copy()
        container = overlay_manager.overlay_container(key[1], workspace_id=key[0])
        if not isinstance(container, QWidget) or container.width() <= 0 or container.height() <= 0:
            return image.copy()
        try:
            dpr = float(container.devicePixelRatioF())
        except Exception:  # noqa: BLE001
            dpr = 1.0
        if dpr <= 0.0:
            try:
                dpr = float(image.devicePixelRatio())
            except Exception:  # noqa: BLE001
                dpr = 1.0
        dpr = max(1.0, dpr)
        expected_size = QSize(
            max(1, round(container.width() * dpr)),
            max(1, round(container.height() * dpr)),
        )
        normalized = image.copy()
        if normalized.size() != expected_size:
            normalized = normalized.scaled(
                expected_size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        normalized.setDevicePixelRatio(dpr)
        return normalized

    @pyqtSlot(str, result=bool)
    def open_detached_plot(self, node_id: str) -> bool:
        if self._shutdown:
            return False
        key = self._key_for_node_id(node_id)
        if key is None:
            return False
        snapshot = self._snapshot_for_key(key)
        if snapshot is None:
            return False
        self._ensure_detached_window(snapshot)
        self._schedule_sync()
        self.state_changed.emit()
        return True

    @pyqtSlot(str, result=bool)
    def close_detached_plot(self, node_id: str) -> bool:
        key = self._key_for_node_id(node_id)
        if key is None:
            return False
        if key not in self._detached_windows:
            return False
        self._close_detached_window(key, reason="detached_closed")
        self._schedule_sync()
        self.state_changed.emit()
        return True

    @pyqtSlot(str, result=bool)
    def detached_plot_active(self, node_id: str) -> bool:
        key = self._key_for_node_id(node_id)
        return key in self._detached_windows if key is not None else False

    @pyqtSlot(str, result=bool)
    def embedded_live_overlay_ready(self, node_id: str) -> bool:
        if self._shutdown:
            return False
        key = self._key_for_node_id(node_id)
        if key is None or key not in self._embedded_interaction_active:
            return False
        bound = self._bound_overlays.get(key)
        if bound is None or bound.presentation != _PRESENTATION_OVERLAY or bound.widget is None:
            return False
        overlay_manager = self._overlay_manager
        if overlay_manager is None:
            return False
        if overlay_manager.overlay_widget(key[1], workspace_id=key[0]) is not bound.widget:
            return False
        geometry_ready = getattr(overlay_manager, "overlay_geometry_ready", None)
        if callable(geometry_ready):
            try:
                return bool(geometry_ready(key[1], workspace_id=key[0]))
            except Exception as exc:  # noqa: BLE001
                self._set_last_error(str(exc))
                return False
        return True

    def reset(self, *, reason: str = "") -> None:
        if self._shutdown:
            return
        self._native_presentation_handoff.flush()
        self._release_all_bindings(reason=reason or "reset")
        self._close_all_detached_windows(reason=reason or "reset")
        self._clear_all_cached_previews()
        overlay_manager = self._overlay_manager
        if overlay_manager is not None:
            self._set_plot_content_fullscreen_target(overlay_manager, None, force_clear=True)
            self._set_plot_active_overlays(overlay_manager, ())
        self._set_last_error("")
        self.state_changed.emit()

    def suspend_sync(self, *, reason: str = "") -> None:
        if self._shutdown:
            return
        self._sync_suspended = True
        if reason:
            self._set_last_error("")

    def resume_sync(self) -> None:
        if self._shutdown or not self._sync_suspended:
            return
        self._sync_suspended = False
        self._schedule_sync()

    def shutdown(self, *, reason: str = "") -> None:
        if self._shutdown:
            return
        self._shutdown = True
        self._sync_queued = False
        self._sync_suspended = False
        self._native_presentation_handoff.shutdown()
        self._release_all_bindings(reason=reason or "shutdown")
        self._close_all_detached_windows(reason=reason or "shutdown")
        self._clear_all_cached_previews()
        overlay_manager = self._overlay_manager
        if overlay_manager is not None:
            self._set_plot_content_fullscreen_target(overlay_manager, None, force_clear=True)
            self._set_plot_active_overlays(overlay_manager, ())
        bridge = self._content_fullscreen_bridge
        if bridge is not None:
            try:
                bridge.content_fullscreen_changed.disconnect(
                    self._on_content_fullscreen_changed
                )
            except (TypeError, RuntimeError):
                pass
        self._overlay_manager = None
        self._content_fullscreen_bridge = None
        self._scene_bridge = None
        self._active_workspace_id_provider = None
        self._embedded_interaction_active.clear()
        self._plot_content_fullscreen_target_key = None
        self._plot_overlay_revision = 0
        self._set_last_error("")
        self.state_changed.emit()

    def _ensure_binders_initialized(self) -> PlotWidgetBinderRegistry:
        if self._shutdown or self._binders_initialized:
            return self._binder_registry
        self._register_builtin_binders()
        for backend_id, binder in self._custom_binders.items():
            self._binder_registry.register(backend_id, binder)
        self._binders_initialized = True
        return self._binder_registry

    def _register_builtin_binders(self) -> None:
        self._binder_registry.register(MATPLOTLIB_PLOT_BACKEND_ID, MatplotlibPlotWidgetBinder())
        self._binder_registry.register(PYQTGRAPH_PLOT_BACKEND_ID, PyQtGraphPlotWidgetBinder())
        self._binder_registry.register(PYVISTA_PLOT_BACKEND_ID, PyVistaPlotWidgetBinder())

    def _connect_signals(self) -> None:
        self._connect_signal(self._scene_bridge, "nodes_changed", self._schedule_sync)
        self._connect_signal(self._scene_bridge, "workspace_changed", self._on_workspace_changed)
        bridge = self._content_fullscreen_bridge
        if bridge is not None:
            bridge.content_fullscreen_changed.connect(
                self._on_content_fullscreen_changed
            )

    @pyqtSlot()
    def _on_content_fullscreen_changed(self) -> None:
        if self._shutdown:
            return
        overlay_manager = self._overlay_manager
        bridge = self._content_fullscreen_bridge
        previous_key = self._plot_content_fullscreen_target_key
        next_key = self._presentation_service.content_fullscreen_overlay_key()
        fullscreen_open = bool(getattr(bridge, "open", False)) if bridge is not None else False
        if overlay_manager is not None and fullscreen_open:
            overlay_spec = None
            if next_key is not None:
                overlay_spec = EmbeddedViewerOverlaySpec(
                    workspace_id=next_key[0],
                    node_id=next_key[1],
                    session_id=f"plot::{next_key[1]}",
                )
                self._set_plot_content_fullscreen_target(overlay_manager, overlay_spec, force_clear=True)
            elif previous_key is not None:
                self._set_plot_content_fullscreen_target(overlay_manager, None, force_clear=True)
            self._release_overlay_bindings_except(next_key, reason="content_fullscreen_active")
            self._set_plot_active_overlays(overlay_manager, (overlay_spec,) if overlay_spec is not None else ())
            self._sync_overlay_manager_now()
            self._bump_plot_overlay_revision()
            self.state_changed.emit()
        elif overlay_manager is not None and previous_key is not None:
            self._set_plot_content_fullscreen_target(overlay_manager, None, force_clear=True)
            self._release_overlay_bindings_except(None, reason="content_fullscreen_closed")
            self._set_plot_active_overlays(overlay_manager, ())
            self._sync_overlay_manager_now()
            self._bump_plot_overlay_revision()
            self.state_changed.emit()
        self._schedule_sync()

    @staticmethod
    def _connect_signal(source: object | None, name: str, slot) -> None:  # noqa: ANN001
        signal = getattr(source, name, None) if source is not None else None
        if signal is not None and hasattr(signal, "connect"):
            signal.connect(slot)

    def _on_workspace_changed(self, _workspace_id: str = "") -> None:
        self._native_presentation_handoff.flush()
        self._embedded_interaction_active.clear()
        self._close_all_detached_windows(reason="workspace_changed")
        self._clear_all_cached_previews()
        self._schedule_sync()

    def _active_workspace_id(self) -> str:
        if self._scene_bridge is not None:
            workspace_id = _string(getattr(self._scene_bridge, "workspace_id", ""))
            if workspace_id:
                return workspace_id
        provider = self._active_workspace_id_provider
        if provider is None:
            return ""
        try:
            return _string(provider())
        except Exception:  # noqa: BLE001
            return ""

    def _embedded_interaction_active_for(self, workspace_id: str, node_id: str) -> bool:
        key = (_string(workspace_id), _string(node_id))
        if key in self._embedded_interaction_active:
            return True
        # A pending live-exit demotion keeps the overlay hosted until QML
        # confirms the swapped preview frame (or the handoff times out).
        return self._native_presentation_handoff.contains(key)

    def _key_for_node_id(self, node_id: str) -> _OverlayKey | None:
        workspace_id = self._active_workspace_id()
        normalized_node_id = _string(node_id)
        if not workspace_id or not normalized_node_id:
            return None
        return (workspace_id, normalized_node_id)

    def _snapshot_for_key(self, key: _OverlayKey) -> _PlotHostSnapshot | None:
        payload = self._payload_for_key(key)
        if payload is None:
            return None
        return self._presentation_service.snapshot_from_node_payload(
            payload,
            workspace_id=key[0],
        )

    def _payload_for_key(self, key: _OverlayKey) -> dict[str, Any] | None:
        for payload in self._presentation_service.scene_plot_payloads():
            node_id = _string(payload.get("node_id"))
            workspace_id = _string(payload.get("workspace_id")) or self._active_workspace_id()
            if (workspace_id, node_id) != key:
                continue
            payload = dict(payload)
            payload.setdefault("workspace_id", workspace_id)
            return payload
        return None

    def _ensure_detached_window(self, snapshot: _PlotHostSnapshot) -> _DetachedPlotWindow:
        key = snapshot.overlay_key
        window = self._detached_windows.get(key)
        title = snapshot.render_request.title or snapshot.plot_type.replace("_", " ").title()
        if window is not None:
            window.setWindowTitle(title)
            window.show()
            return window
        window = _DetachedPlotWindow(
            key=key,
            title=title,
            on_closed=self._on_detached_window_closed,
        )
        self._detached_windows[key] = window
        window.show()
        return window

    def _on_detached_window_closed(self, key: _OverlayKey) -> None:
        window = self._detached_windows.pop(key, None)
        if window is None:
            return
        self._capture_detached_view_state_for_key(key)
        if window.widget is not None:
            window.detach_widget(window.widget)
        window.deleteLater()
        self._set_last_error("")
        self._schedule_sync()
        self.state_changed.emit()

    def _close_detached_window(self, key: _OverlayKey, *, reason: str) -> None:
        window = self._detached_windows.pop(key, None)
        if window is None:
            return
        self._capture_detached_view_state_for_key(key)
        if window.widget is not None:
            window.detach_widget(window.widget)
        window.close_from_service()
        window.deleteLater()
        if reason:
            self._set_last_error("")

    def _close_all_detached_windows(self, *, reason: str) -> None:
        for key in list(self._detached_windows):
            self._close_detached_window(key, reason=reason)

    def _schedule_sync(self) -> None:
        if self._shutdown or self._sync_queued:
            return
        self._sync_queued = True
        QTimer.singleShot(0, self._run_queued_sync)

    @pyqtSlot()
    def _run_queued_sync(self) -> None:
        if self._shutdown:
            self._sync_queued = False
            return
        if self._sync_suspended:
            self._sync_queued = False
            return
        self._sync_queued = False
        self.sync()

    @pyqtSlot()
    def sync(self) -> None:
        if self._shutdown or self._sync_suspended:
            return
        overlay_manager = self._overlay_manager
        if self._scene_bridge is None:
            self._release_all_bindings(reason="scene_bridge_unavailable")
            self._close_all_detached_windows(reason="scene_bridge_unavailable")
            self._clear_all_cached_previews()
            if overlay_manager is not None:
                self._set_plot_content_fullscreen_target(overlay_manager, None)
                self._set_plot_active_overlays(overlay_manager, ())
            self._bump_plot_overlay_revision()
            self.state_changed.emit()
            return

        self._sync_preview_cache_signatures()
        if overlay_manager is not None:
            self._set_plot_content_fullscreen_target(
                overlay_manager,
                self._presentation_service.content_fullscreen_overlay_spec(),
            )
        desired_overlays, errors = self._presentation_service.desired_overlays(
            self._ensure_binders_initialized
        )
        detached_desired, detached_errors = self._detached_desired_overlays()
        errors.extend(detached_errors)
        for key, desired in detached_desired.items():
            desired_overlays.setdefault(key, desired)

        for key, bound in list(self._bound_overlays.items()):
            desired = desired_overlays.get(key)
            if desired is None or desired[0].backend_id != bound.snapshot.backend_id or desired[1] is not bound.binder:
                self._release_binding(key, reason="inactive")

        self._retarget_overlay_bindings_before_overlay_reconcile(desired_overlays)

        if overlay_manager is not None:
            self._set_plot_active_overlays(
                overlay_manager,
                (
                    snapshot.overlay_spec()
                    for key, (snapshot, _binder) in desired_overlays.items()
                    if self._presentation_target_for_key(key) == _PRESENTATION_OVERLAY
                ),
            )
            self._sync_overlay_manager_now()

        for key, (snapshot, binder) in desired_overlays.items():
            presentation = self._presentation_target_for_key(key)
            container, current_widget = self._container_and_current_widget(
                key,
                snapshot=snapshot,
                presentation=presentation,
            )
            if container is None:
                continue
            signature = self._binding_signature(snapshot)
            bound = self._bound_overlays.get(key)
            if (
                bound is not None
                and bound.binder is binder
                and bound.signature == signature
                and bound.presentation == presentation
                and bound.container is container
                and bound.widget is not None
            ):
                self._show_bound_widget(key, bound)
                continue
            if bound is not None and bound.binder is binder and bound.widget is not None:
                current_widget = bound.widget
            try:
                widget = binder.bind_widget(snapshot.bind_request(container=container, current_widget=current_widget))
            except PlotWidgetNoBind:
                self._bound_overlays.pop(key, None)
                self._release_widget(
                    snapshot=snapshot,
                    binder=binder,
                    container=container,
                    widget=current_widget,
                    presentation=presentation,
                    reason="no_bind",
                )
                continue
            except Exception as exc:  # noqa: BLE001
                self._bound_overlays.pop(key, None)
                self._release_widget(
                    snapshot=snapshot,
                    binder=binder,
                    container=container,
                    widget=current_widget,
                    presentation=presentation,
                    reason="bind_error",
                )
                errors.append(str(exc))
                continue
            if widget is None:
                self._bound_overlays.pop(key, None)
                self._release_widget(
                    snapshot=snapshot,
                    binder=binder,
                    container=container,
                    widget=current_widget,
                    presentation=presentation,
                    reason="no_bind",
                )
                continue
            self._restore_cached_view_state_for_binding(key, binder, widget, signature)
            self._attach_widget_to_presentation(
                key,
                snapshot=snapshot,
                widget=widget,
                presentation=presentation,
            )
            self._refresh_widget_after_presentation_attach(binder, widget)
            self._bound_overlays[key] = _BoundPlotOverlay(
                binder=binder,
                snapshot=snapshot,
                signature=signature,
                presentation=presentation,
                container=container,
                widget=widget,
            )

        self._set_last_error(errors[0] if errors else "")
        self._bump_plot_overlay_revision()
        self.state_changed.emit()

    def _detached_desired_overlays(
        self,
    ) -> tuple[dict[_OverlayKey, tuple[_PlotHostSnapshot, PlotWidgetBinder]], list[str]]:
        desired: dict[_OverlayKey, tuple[_PlotHostSnapshot, PlotWidgetBinder]] = {}
        errors: list[str] = []
        for key in list(self._detached_windows):
            snapshot = self._snapshot_for_key(key)
            if snapshot is None:
                self._close_detached_window(key, reason="node_unavailable")
                continue
            window = self._detached_windows.get(key)
            if window is not None:
                window.setWindowTitle(snapshot.render_request.title or snapshot.plot_type.replace("_", " ").title())
            binder = self._ensure_binders_initialized().lookup(snapshot.backend_id)
            if binder is None:
                errors.append(f"No plot widget binder registered for backend '{snapshot.backend_id}'.")
                continue
            desired[key] = (snapshot, binder)
        return desired, errors

    def _presentation_target_for_key(self, key: _OverlayKey) -> str:
        if self._presentation_service.content_fullscreen_overlay_key() == key:
            return _PRESENTATION_OVERLAY
        if key in self._detached_windows:
            return _PRESENTATION_DETACHED
        return _PRESENTATION_OVERLAY

    def _retarget_overlay_bindings_before_overlay_reconcile(
        self,
        desired_overlays: Mapping[_OverlayKey, tuple[_PlotHostSnapshot, PlotWidgetBinder]],
    ) -> None:
        overlay_manager = self._overlay_manager
        if overlay_manager is None:
            return
        for key, bound in list(self._bound_overlays.items()):
            if key not in desired_overlays:
                continue
            if bound.presentation != _PRESENTATION_OVERLAY:
                continue
            target = self._presentation_target_for_key(key)
            if target != _PRESENTATION_DETACHED:
                continue
            widget = bound.widget or overlay_manager.overlay_widget(
                bound.snapshot.node_id,
                workspace_id=bound.snapshot.workspace_id,
            )
            if widget is None:
                continue
            if overlay_manager.overlay_widget(bound.snapshot.node_id, workspace_id=bound.snapshot.workspace_id) is widget:
                take_overlay_widget = getattr(overlay_manager, "take_overlay_widget", None)
                if callable(take_overlay_widget):
                    taken_widget = take_overlay_widget(
                        bound.snapshot.node_id,
                        workspace_id=bound.snapshot.workspace_id,
                    )
                    if isinstance(taken_widget, QWidget):
                        widget = taken_widget
                else:
                    overlay_manager.detach_overlay_widget(
                        bound.snapshot.node_id,
                        workspace_id=bound.snapshot.workspace_id,
                    )
            window = self._detached_windows.get(key)
            if window is None:
                continue
            window.attach_widget(widget)
            bound.container = window.container
            bound.presentation = target
            bound.widget = widget

    def _container_and_current_widget(
        self,
        key: _OverlayKey,
        *,
        snapshot: _PlotHostSnapshot,
        presentation: str,
    ) -> tuple[QWidget | None, QWidget | None]:
        if presentation == _PRESENTATION_DETACHED:
            window = self._detached_windows.get(key)
            if window is None:
                return None, None
            return window.container, window.widget
        overlay_manager = self._overlay_manager
        if overlay_manager is None:
            return None, None
        container = overlay_manager.overlay_container(snapshot.node_id, workspace_id=snapshot.workspace_id)
        widget = overlay_manager.overlay_widget(snapshot.node_id, workspace_id=snapshot.workspace_id)
        return container, widget

    def _attach_widget_to_presentation(
        self,
        key: _OverlayKey,
        *,
        snapshot: _PlotHostSnapshot,
        widget: QWidget,
        presentation: str,
    ) -> None:
        if presentation == _PRESENTATION_DETACHED:
            window = self._detached_windows.get(key)
            if window is not None:
                window.attach_widget(widget)
            return
        overlay_manager = self._overlay_manager
        if overlay_manager is not None:
            overlay_manager.attach_overlay_widget(snapshot.node_id, widget, workspace_id=snapshot.workspace_id)
            self._sync_overlay_manager_now()

    def _refresh_widget_after_presentation_attach(self, binder: PlotWidgetBinder, widget: QWidget) -> None:
        refresh = getattr(binder, "refresh_after_attach", None)
        if not callable(refresh):
            return
        try:
            refresh(widget)
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))

    def _set_plot_active_overlays(
        self,
        overlay_manager: EmbeddedViewerOverlayManager,
        overlays,  # noqa: ANN001
    ) -> None:
        overlay_specs = tuple(overlays)
        set_for_owner = getattr(overlay_manager, "set_active_overlays_for_owner", None)
        if callable(set_for_owner):
            set_for_owner(PLOT_HOST_OVERLAY_OWNER, overlay_specs)
            return
        overlay_manager.set_active_overlays(overlay_specs)

    def _set_plot_content_fullscreen_target(
        self,
        overlay_manager: EmbeddedViewerOverlayManager,
        overlay: EmbeddedViewerOverlaySpec | None,
        *,
        force_clear: bool = False,
    ) -> None:
        if overlay is not None:
            overlay_manager.set_content_fullscreen_target(overlay)
            self._owns_content_fullscreen_target = True
            self._plot_content_fullscreen_target_key = (
                _string(getattr(overlay, "workspace_id", "")),
                _string(getattr(overlay, "node_id", "")),
            )
            return
        if force_clear or self._owns_content_fullscreen_target:
            overlay_manager.set_content_fullscreen_target(None)
        self._owns_content_fullscreen_target = False
        self._plot_content_fullscreen_target_key = None

    def _sync_overlay_manager_now(self) -> None:
        overlay_manager = self._overlay_manager
        sync = getattr(overlay_manager, "sync", None) if overlay_manager is not None else None
        if not callable(sync):
            return
        try:
            sync()
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))

    def _show_bound_widget(self, key: _OverlayKey, bound: _BoundPlotOverlay) -> None:
        widget = bound.widget
        if widget is None:
            return
        if bound.presentation == _PRESENTATION_DETACHED:
            window = self._detached_windows.get(key)
            if window is not None:
                window.attach_widget(widget)
            return
        self._attach_widget_to_presentation(
            key,
            snapshot=bound.snapshot,
            widget=widget,
            presentation=bound.presentation,
        )

    def _release_inactive_embedded_overlay(self, key: _OverlayKey) -> None:
        bound = self._bound_overlays.get(key)
        if bound is None or bound.presentation != _PRESENTATION_OVERLAY:
            return
        if self._presentation_service.content_fullscreen_overlay_key() == key:
            return
        self._release_binding(key, reason="embedded_inactive")
        self._bump_plot_overlay_revision()
        self.state_changed.emit()

    def _release_overlay_bindings_except(self, keep_key: _OverlayKey | None, *, reason: str) -> bool:
        released = False
        for key, bound in list(self._bound_overlays.items()):
            if keep_key is not None and key == keep_key:
                continue
            if bound.presentation != _PRESENTATION_OVERLAY:
                continue
            if key in self._embedded_interaction_active:
                self._capture_cached_live_state_for_key(key)
            self._release_binding(key, reason=reason)
            released = True
        return released

    def _release_all_bindings(self, *, reason: str) -> None:
        for key in list(self._bound_overlays):
            self._release_binding(key, reason=reason)

    def _release_binding(self, key: _OverlayKey, *, reason: str) -> None:
        bound = self._bound_overlays.pop(key, None)
        if bound is None:
            return
        overlay_manager = self._overlay_manager
        container = bound.container
        widget = bound.widget
        if bound.presentation == _PRESENTATION_OVERLAY and overlay_manager is not None:
            container = overlay_manager.overlay_container(bound.snapshot.node_id, workspace_id=bound.snapshot.workspace_id)
            widget = overlay_manager.overlay_widget(bound.snapshot.node_id, workspace_id=bound.snapshot.workspace_id) or widget
        elif bound.presentation == _PRESENTATION_DETACHED:
            window = self._detached_windows.get(key)
            if window is not None:
                container = window.container
                widget = window.widget or widget
        self._release_widget(
            snapshot=bound.snapshot,
            binder=bound.binder,
            container=container,
            widget=widget,
            presentation=bound.presentation,
            reason=reason,
        )

    def _release_widget(
        self,
        *,
        snapshot: _PlotHostSnapshot,
        binder: PlotWidgetBinder,
        container,
        widget,
        presentation: str,
        reason: str,
    ) -> None:  # noqa: ANN001
        overlay_manager = self._overlay_manager
        if widget is None:
            return
        try:
            binder.release_widget(snapshot.release_request(container=container, widget=widget, reason=reason))
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
        if (
            presentation == _PRESENTATION_OVERLAY
            and overlay_manager is not None
            and overlay_manager.overlay_widget(snapshot.node_id, workspace_id=snapshot.workspace_id) is widget
        ):
            if container is not None:
                try:
                    container.hide()
                except Exception:  # noqa: BLE001
                    pass
            try:
                widget.hide()
            except Exception:  # noqa: BLE001
                pass
        elif presentation == _PRESENTATION_DETACHED:
            window = self._detached_windows.get(snapshot.overlay_key)
            if window is not None and window.widget is widget:
                window.detach_widget(widget)
            try:
                widget.hide()
            except Exception:  # noqa: BLE001
                pass
        if presentation != _PRESENTATION_OVERLAY or overlay_manager is None:
            return
        if overlay_manager.overlay_widget(snapshot.node_id, workspace_id=snapshot.workspace_id) is widget:
            overlay_manager.detach_overlay_widget(snapshot.node_id, workspace_id=snapshot.workspace_id)

    def _capture_cached_live_state_for_key(self, key: _OverlayKey) -> None:
        bound = self._bound_overlays.get(key)
        if bound is None or bound.presentation != _PRESENTATION_OVERLAY:
            return
        current_snapshot = self._snapshot_for_key(key)
        if current_snapshot is None:
            self._clear_cached_plot_state(key)
            return
        signature = self._binding_signature(current_snapshot)
        if signature != bound.signature:
            self._clear_cached_plot_state(key)
            return
        self._capture_cached_view_state_for_binding(key, bound, signature)
        provider = self._preview_cache_provider
        if provider is None:
            return
        cached_signature = provider.preview_signature(key[0], key[1])
        if cached_signature is not None and cached_signature != signature:
            self._clear_cached_preview(key)
        image = self.capture_overlay_preview_image(bound.snapshot.node_id, workspace_id=bound.snapshot.workspace_id)
        if image.isNull():
            return
        self._set_cached_preview(key, image, signature)

    def _capture_detached_view_state_for_key(self, key: _OverlayKey) -> None:
        bound = self._bound_overlays.get(key)
        if bound is None or bound.presentation != _PRESENTATION_DETACHED:
            return
        current_snapshot = self._snapshot_for_key(key)
        if current_snapshot is None:
            self._clear_cached_plot_state(key)
            return
        signature = self._binding_signature(current_snapshot)
        if signature != bound.signature:
            self._clear_cached_plot_state(key)
            return
        self._capture_cached_view_state_for_binding(key, bound, signature)

    def _capture_cached_view_state_for_binding(
        self,
        key: _OverlayKey,
        bound: _BoundPlotOverlay,
        signature: tuple[Any, ...],
    ) -> None:
        capture = getattr(bound.binder, "capture_view_state", None)
        if not callable(capture):
            return
        widget = self._current_widget_for_bound_overlay(key, bound)
        if widget is None:
            return
        try:
            state = capture(widget)
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return
        if state is None:
            return
        try:
            stored_state = copy.deepcopy(state)
        except Exception:  # noqa: BLE001
            stored_state = state
        self._plot_view_states[key] = (signature, stored_state)

    def _restore_cached_view_state_for_binding(
        self,
        key: _OverlayKey,
        binder: PlotWidgetBinder,
        widget: QWidget,
        signature: tuple[Any, ...],
    ) -> None:
        cached = self._plot_view_states.get(key)
        if cached is None:
            return
        cached_signature, state = cached
        if cached_signature != signature:
            self._clear_cached_plot_state(key)
            return
        restore = getattr(binder, "restore_view_state", None)
        if not callable(restore):
            return
        try:
            state_to_restore = copy.deepcopy(state)
        except Exception:  # noqa: BLE001
            state_to_restore = state
        try:
            restore(widget, state_to_restore)
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))

    def _current_widget_for_bound_overlay(
        self,
        key: _OverlayKey,
        bound: _BoundPlotOverlay,
    ) -> QWidget | None:
        if bound.presentation == _PRESENTATION_OVERLAY and self._overlay_manager is not None:
            widget = self._overlay_manager.overlay_widget(bound.snapshot.node_id, workspace_id=bound.snapshot.workspace_id)
            return widget if isinstance(widget, QWidget) else bound.widget
        return bound.widget

    def _set_cached_preview(
        self,
        key: _OverlayKey,
        image: QImage,
        signature: tuple[Any, ...],
    ) -> None:
        provider = self._preview_cache_provider
        if provider is None:
            return
        if provider.set_preview(key[0], key[1], image, signature=signature):
            self._bump_preview_cache_revision()

    def _clear_cached_preview(self, key: _OverlayKey) -> None:
        provider = self._preview_cache_provider
        if provider is None:
            return
        if provider.clear_preview(key[0], key[1]):
            self._bump_preview_cache_revision()

    def _clear_cached_plot_state(self, key: _OverlayKey) -> None:
        self._plot_view_states.pop(key, None)
        self._clear_cached_preview(key)

    def _clear_all_cached_previews(self) -> None:
        provider = self._preview_cache_provider
        changed = provider.clear_all() if provider is not None else False
        self._plot_render_signatures.clear()
        self._plot_view_states.clear()
        if changed:
            self._bump_preview_cache_revision()

    def _sync_preview_cache_signatures(self) -> None:
        current: dict[_OverlayKey, tuple[Any, ...]] = {}
        for payload in self._presentation_service.scene_plot_payloads():
            node_id = _string(payload.get("node_id"))
            workspace_id = _string(payload.get("workspace_id")) or self._active_workspace_id()
            if not workspace_id or not node_id:
                continue
            snapshot = self._presentation_service.snapshot_from_node_payload(payload, workspace_id=workspace_id)
            if snapshot is None:
                continue
            key = (workspace_id, node_id)
            signature = self._binding_signature(snapshot)
            current[key] = signature
            previous_signature = self._plot_render_signatures.get(key)
            cached_signature = (
                self._preview_cache_provider.preview_signature(key[0], key[1])
                if self._preview_cache_provider is not None
                else None
            )
            if (
                (previous_signature is not None and previous_signature != signature)
                or (cached_signature is not None and cached_signature != signature)
            ):
                self._clear_cached_plot_state(key)
        for key in set(self._plot_render_signatures) - set(current):
            self._clear_cached_plot_state(key)
        self._plot_render_signatures = current

    def _bump_preview_cache_revision(self) -> None:
        self._preview_cache_revision += 1
        self.preview_cache_changed.emit()

    def _bump_plot_overlay_revision(self) -> None:
        self._plot_overlay_revision += 1

    def _binding_signature(self, snapshot: _PlotHostSnapshot) -> tuple[Any, ...]:
        return self._presentation_service.binding_signature(snapshot)

    def _set_last_error(self, value: str) -> None:
        normalized = _string(value)
        if normalized == self._last_error:
            return
        self._last_error = normalized
        self.last_error_changed.emit()


__all__ = ["PlotHostService"]
