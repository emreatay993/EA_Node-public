# Purpose: Own native viewer binding, cached previews, and inline/detached/fullscreen presentation.
# Map: subsystems/viewer_surfaces.md
# Tests: tests/test_viewer_host_service.py
# Landmarks: _ViewerHostSessionSnapshot; _DetachedViewerWindow; _ViewerHostPresentationService; ViewerHostService; presentation reconciliation

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QSize, Qt, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QCloseEvent, QImage
from PyQt6.QtQuickWidgets import QQuickWidget
from PyQt6.QtWidgets import QApplication, QGridLayout, QVBoxLayout, QWidget

from ea_node_editor.common.coercions import coerce_int as _coerce_int
from ea_node_editor.execution.viewer_session_service import coerce_viewer_session_model
from ea_node_editor.ui.plot_preview_cache_provider import ViewerPreviewCacheImageProvider
from ea_node_editor.ui_qml.embedded_viewer_overlay_manager import (
    EmbeddedViewerOverlayManager,
    EmbeddedViewerOverlaySpec,
)
from ea_node_editor.ui_qml.engineering_viewer_widget_binder import EngineeringViewerWidgetBinder
from ea_node_editor.ui_qml.native_overlay_owners import VIEWER_SESSION_OVERLAY_OWNER
from ea_node_editor.ui_qml.native_presentation_handoff import (
    NativePresentationHandoff,
)
from ea_node_editor.ui_qml.viewer_widget_binder import (
    ViewerWidgetBindRequest,
    ViewerWidgetBinder,
    ViewerWidgetBinderRegistry,
    ViewerWidgetNoBind,
    ViewerWidgetReleaseRequest,
)

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.content_fullscreen_bridge import ContentFullscreenBridge
    from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge

_OverlayKey = tuple[str, str]
_PRESENTATION_OVERLAY = "overlay"
_PRESENTATION_DETACHED = "detached"
_PRESENTATION_RETAINED_INLINE = "retained_inline"
_MAX_INLINE_VIEWER_PREVIEW_EDGE_PX = 640

def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((_string(key), _freeze_value(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _cache_relevant_options(options: Mapping[str, Any]) -> dict[str, Any]:
    ignored_keys = {
        "export_formats",
        # The probe changes no committed pixels, so it must not invalidate
        # cached previews or camera state.
        "hover_probe",
        "live_mode",
        "output_profile",
        "playback",
        "playback_state",
        "step_index",
    }
    return {
        str(key): copy.deepcopy(value)
        for key, value in options.items()
        if str(key) not in ignored_keys
    }


def _playback_state_from_projection(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    playback = _mapping(state.get("playback"))
    if playback:
        return playback
    playback_state = _string(state.get("playback_state", "paused"))
    step_index = _coerce_int(state.get("step_index"), default=0)
    return {
        "state": playback_state or "paused",
        "step_index": step_index,
    }


def _projected_session(projected_state: Mapping[str, Any]) -> dict[str, Any]:
    return coerce_viewer_session_model(projected_state)


@dataclass(slots=True, frozen=True)
class _ViewerHostSessionSnapshot:
    workspace_id: str
    node_id: str
    session_id: str
    backend_id: str
    phase: str
    cache_state: str
    live_mode: str
    transport_revision: int
    live_open_status: str
    live_open_blocker: dict[str, Any] = field(default_factory=dict)
    data_refs: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    playback_state: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def overlay_key(self) -> _OverlayKey:
        return (self.workspace_id, self.node_id)

    def overlay_spec(self) -> EmbeddedViewerOverlaySpec:
        return EmbeddedViewerOverlaySpec(
            workspace_id=self.workspace_id,
            node_id=self.node_id,
            session_id=self.session_id,
        )

    def bind_request(self, *, container, current_widget) -> ViewerWidgetBindRequest:  # noqa: ANN001
        return ViewerWidgetBindRequest(
            workspace_id=self.workspace_id,
            node_id=self.node_id,
            session_id=self.session_id,
            backend_id=self.backend_id,
            transport_revision=self.transport_revision,
            live_mode=self.live_mode,
            cache_state=self.cache_state,
            live_open_status=self.live_open_status,
            live_open_blocker=copy.deepcopy(self.live_open_blocker),
            data_refs=copy.deepcopy(self.data_refs),
            transport=copy.deepcopy(self.transport),
            camera_state=copy.deepcopy(self.camera_state),
            playback_state=copy.deepcopy(self.playback_state),
            summary=copy.deepcopy(self.summary),
            options=copy.deepcopy(self.options),
            container=container,
            current_widget=current_widget,
        )

    def release_request(self, *, container, widget, reason: str) -> ViewerWidgetReleaseRequest:  # noqa: ANN001
        return ViewerWidgetReleaseRequest(
            workspace_id=self.workspace_id,
            node_id=self.node_id,
            session_id=self.session_id,
            backend_id=self.backend_id,
            transport_revision=self.transport_revision,
            data_refs=copy.deepcopy(self.data_refs),
            transport=copy.deepcopy(self.transport),
            summary=copy.deepcopy(self.summary),
            options=copy.deepcopy(self.options),
            container=container,
            widget=widget,
            reason=reason,
        )


@dataclass(slots=True)
class _BoundOverlay:
    binder: ViewerWidgetBinder
    snapshot: _ViewerHostSessionSnapshot
    signature: tuple[Any, ...]
    presentation: str = _PRESENTATION_OVERLAY
    container: QWidget | None = None
    widget: QWidget | None = None


class _DetachedViewerWindow(QWidget):
    def __init__(
        self,
        *,
        key: _OverlayKey,
        session_id: str,
        title: str,
        qml_engine: Any,
        on_closed: Callable[[_OverlayKey], bool],
    ) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self._key = key
        self.session_id = session_id
        self._on_closed = on_closed
        self._service_closing = False
        self._selection_visibility_root: QObject | None = None
        self._side_panel_width_connected = False
        self.widget: QWidget | None = None
        self.setObjectName(f"detachedViewerWindow::{key[0]}::{key[1]}")
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle(title)
        self.resize(1180, 760)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.container = QWidget(self)
        self.container.setObjectName(f"detachedViewerContainer::{key[0]}::{key[1]}")
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        layout.addWidget(self.container, 1, 0)
        layout.setRowStretch(1, 1)
        layout.setColumnStretch(0, 1)

        self.selection_controls: QQuickWidget | None = None
        self.side_panel: QQuickWidget | None = None
        self.quick_controls: QQuickWidget | None = None
        if qml_engine is not None:
            qml_dir = Path(__file__).resolve().parent / "components" / "graph" / "viewer"
            self.selection_controls = self._create_quick_widget(
                qml_engine,
                qml_dir / "ViewerSelectionControls.qml",
            )
            self.selection_controls.setMinimumHeight(0)
            self.selection_controls.setMaximumHeight(0)
            self.selection_controls.hide()
            layout.addWidget(self.selection_controls, 0, 0, 1, 2)
            self.side_panel = self._create_quick_widget(
                qml_engine,
                qml_dir / "ViewerSidePanel.qml",
            )
            self.side_panel.setMinimumWidth(28)
            self.side_panel.setMaximumWidth(320)
            layout.addWidget(self.side_panel, 1, 1)
            self.quick_controls = self._create_quick_widget(
                qml_engine,
                qml_dir / "ViewerQuickControls.qml",
            )
            self.quick_controls.setMinimumHeight(54)
            self.quick_controls.setMaximumHeight(72)
            layout.addWidget(self.quick_controls, 2, 0, 1, 2)

    def _create_quick_widget(self, engine: Any, source: Path) -> QQuickWidget:
        widget = QQuickWidget(engine, self)
        widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        widget.setSource(QUrl.fromLocalFile(str(source)))
        return widget

    def update_controls(self, *, node_id: str, fullscreen_bridge: QObject | None) -> None:
        for quick_widget in (self.selection_controls, self.side_panel, self.quick_controls):
            root = quick_widget.rootObject() if quick_widget is not None else None
            if root is None:
                continue
            root.setProperty("nodeId", node_id)
            root.setProperty("fullscreenBridgeRef", fullscreen_bridge)
            root.setProperty("detachedPresentation", True)
        selection_root = self.selection_controls.rootObject() if self.selection_controls is not None else None
        if self.selection_controls is not None and selection_root is not None:
            if self._selection_visibility_root is not selection_root:
                self._selection_visibility_root = selection_root
                changed = getattr(selection_root, "visibleChanged", None)
                if changed is not None:
                    changed.connect(self._sync_selection_controls_visibility)
            self._sync_selection_controls_visibility()
        side_panel_root = self.side_panel.rootObject() if self.side_panel is not None else None
        if self.side_panel is not None and side_panel_root is not None:
            if not self._side_panel_width_connected:
                for signal_name in ("implicitWidthChanged", "panelCollapsedChanged"):
                    changed = getattr(side_panel_root, signal_name, None)
                    if changed is not None:
                        changed.connect(self._sync_side_panel_width)
                self._side_panel_width_connected = True
            self._sync_side_panel_width()

    def _sync_selection_controls_visibility(self) -> None:
        root = self._selection_visibility_root
        controls = self.selection_controls
        if root is None or controls is None:
            return
        visible = bool(root.property("visible"))
        controls.setMinimumHeight(40 if visible else 0)
        controls.setMaximumHeight(48 if visible else 0)
        controls.setVisible(visible)

    def _sync_side_panel_width(self, *_args: Any) -> None:
        panel = self.side_panel
        root = panel.rootObject() if panel is not None else None
        if root is None or panel is None:
            return
        try:
            width = round(float(root.property("implicitWidth")))
        except (TypeError, ValueError):
            width = 28
        panel.setFixedWidth(min(320, max(28, width)))

    def prepare_destination(self) -> None:
        self.show()
        self.container.show()

    def attach_widget(self, widget: QWidget) -> None:
        self.prepare_destination()
        if self.widget is not None and self.widget is not widget:
            self.detach_widget(self.widget)
        if widget.parent() is not self.container:
            widget.setParent(self.container)
        layout = self.container.layout()
        if layout is not None and layout.indexOf(widget) < 0:
            layout.addWidget(widget)
        self.widget = widget
        widget.show()

    def detach_widget(self, widget: QWidget | None = None) -> None:
        target = widget or self.widget
        if target is None:
            return
        layout = self.container.layout()
        if layout is not None:
            layout.removeWidget(target)
        target.hide()
        if target.parent() is self.container:
            target.setParent(None)
        if self.widget is target:
            self.widget = None

    def focus_window(self) -> None:
        self.prepare_destination()
        self.raise_()
        self.activateWindow()

    def close_from_service(self) -> None:
        self._service_closing = True
        try:
            self.close()
        finally:
            self._service_closing = False

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if not self._service_closing and not self._on_closed(self._key):
            event.ignore()
            return
        super().closeEvent(event)


class _ViewerHostPresentationService:
    def __init__(
        self,
        *,
        content_fullscreen_bridge_provider: Callable[[], QObject | None],
    ) -> None:
        self._content_fullscreen_bridge_provider = content_fullscreen_bridge_provider

    def desired_overlays(
        self,
        projected_sessions: Any,
        binder_registry_provider: Callable[[], ViewerWidgetBinderRegistry],
    ) -> tuple[dict[_OverlayKey, tuple[_ViewerHostSessionSnapshot, ViewerWidgetBinder]], list[str]]:
        desired_overlays: dict[_OverlayKey, tuple[_ViewerHostSessionSnapshot, ViewerWidgetBinder]] = {}
        errors: list[str] = []
        binder_registry: ViewerWidgetBinderRegistry | None = None
        for item in projected_sessions if isinstance(projected_sessions, list) else []:
            projected_state = _mapping(item)
            if not self.should_host_overlay(projected_state):
                continue
            snapshot = self.snapshot_from_projected_state(projected_state)
            if snapshot is None:
                continue
            if binder_registry is None:
                binder_registry = binder_registry_provider()
            binder = binder_registry.lookup(snapshot.backend_id)
            if binder is None:
                errors.append(f"No viewer widget binder registered for backend '{snapshot.backend_id}'.")
                continue
            desired_overlays[snapshot.overlay_key] = (snapshot, binder)
        return desired_overlays, errors

    def content_fullscreen_overlay_spec(self) -> EmbeddedViewerOverlaySpec | None:
        bridge = self._content_fullscreen_bridge_provider()
        if bridge is None:
            return None
        if not bool(getattr(bridge, "open", False)):
            return None
        if _string(getattr(bridge, "content_kind", "")) != "viewer":
            return None
        workspace_id = _string(getattr(bridge, "workspace_id", ""))
        node_id = _string(getattr(bridge, "node_id", ""))
        if not workspace_id or not node_id:
            return None
        viewer_payload = _mapping(getattr(bridge, "viewer_payload", {}))
        if not self.surface_requires_native_overlay(viewer_payload):
            return None
        return EmbeddedViewerOverlaySpec(
            workspace_id=workspace_id,
            node_id=node_id,
            session_id=_string(viewer_payload.get("session_id", "")),
        )

    @staticmethod
    def surface_requires_native_overlay(viewer_payload: Mapping[str, Any]) -> bool:
        surface_spec = _mapping(viewer_payload.get("surface_spec"))
        native_overlay = _mapping(surface_spec.get("native_overlay"))
        return bool(native_overlay.get("required"))

    @staticmethod
    def snapshot_from_projected_state(
        projected_state: Mapping[str, Any],
    ) -> _ViewerHostSessionSnapshot | None:
        session = _projected_session(projected_state)
        if not session:
            return None
        workspace_id = _string(session.get("workspace_id"))
        node_id = _string(session.get("node_id"))
        if not workspace_id or not node_id:
            return None
        summary = _mapping(session.get("summary"))
        options = _mapping(session.get("options"))
        data_refs = _mapping(session.get("data_refs"))
        transport = _mapping(session.get("transport"))
        live_open_blocker = _mapping(session.get("live_open_blocker"))
        camera_state = _mapping(session.get("camera_state"))
        playback_state = _mapping(session.get("playback"))
        if not playback_state:
            playback_state = _playback_state_from_projection(session)
        backend_id = _string(session.get("backend_id"))
        if not backend_id:
            return None
        session_id = _string(session.get("session_id"))
        transport_revision = _coerce_int(session.get("transport_revision"), default=0)
        live_open_status = _string(session.get("live_open_status"))
        return _ViewerHostSessionSnapshot(
            workspace_id=workspace_id,
            node_id=node_id,
            session_id=session_id,
            backend_id=backend_id,
            phase=_string(session.get("phase")),
            cache_state=_string(session.get("cache_state")),
            live_mode=_string(session.get("live_mode")),
            transport_revision=transport_revision,
            live_open_status=live_open_status,
            live_open_blocker=live_open_blocker,
            data_refs=data_refs,
            transport=transport,
            camera_state=camera_state,
            playback_state=playback_state,
            summary=summary,
            options=options,
        )

    @staticmethod
    def should_host_overlay(projected_state: Mapping[str, Any]) -> bool:
        session = _projected_session(projected_state)
        if _string(session.get("phase")) != "open":
            return False
        live_mode = _string(session.get("live_mode"))
        if live_mode != "full":
            return False
        live_open_status = _string(session.get("live_open_status"))
        cache_state = _string(session.get("cache_state"))
        return live_open_status == "ready" or cache_state == "live_ready"

    @staticmethod
    def binding_signature(snapshot: _ViewerHostSessionSnapshot) -> tuple[Any, ...]:
        return (
            snapshot.session_id,
            snapshot.backend_id,
            snapshot.transport_revision,
            snapshot.live_mode,
            snapshot.cache_state,
            snapshot.live_open_status,
            _freeze_value(snapshot.live_open_blocker),
            _freeze_value(snapshot.transport),
            _freeze_value(snapshot.data_refs),
            _freeze_value(snapshot.camera_state),
            _freeze_value(snapshot.playback_state),
            _freeze_value(snapshot.options),
        )


class _FullscreenShortcutFilter(QObject):
    """Routes viewer shortcuts around the native interactor in fullscreen.

    The overlay manager focuses the native widget while a content-fullscreen
    target is active, so QML key handlers never see these keys.
    """

    def __init__(self, service: "ViewerHostService") -> None:
        super().__init__(service)
        self._service = service

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.KeyPress:
            try:
                if self._service._handle_presentation_shortcut(watched, event.key(), event.modifiers()):
                    return True
            except Exception:  # noqa: BLE001
                return False
        return False


class ViewerHostService(QObject):
    state_changed = pyqtSignal()
    last_error_changed = pyqtSignal()
    preview_cache_changed = pyqtSignal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        qml_engine_provider: Callable[[], Any],
        save_file_dialog: Callable[..., str],
        cycle_camera_bookmark: Callable[[str, int], bool],
        viewer_session_bridge: "ViewerSessionBridge | None" = None,
        content_fullscreen_bridge: "ContentFullscreenBridge",
        overlay_manager: EmbeddedViewerOverlayManager | None = None,
        preview_cache_provider: ViewerPreviewCacheImageProvider | None = None,
    ) -> None:
        super().__init__(parent)
        self._qml_engine_provider: Callable[[], Any] | None = qml_engine_provider
        self._save_file_dialog: Callable[..., str] | None = save_file_dialog
        self._cycle_camera_bookmark: Callable[[str, int], bool] | None = (
            cycle_camera_bookmark
        )
        self._viewer_session_bridge = viewer_session_bridge
        self._overlay_manager = overlay_manager
        self._preview_cache_provider = preview_cache_provider
        self._content_fullscreen_bridge: QObject | None = content_fullscreen_bridge
        self._binder_registry = ViewerWidgetBinderRegistry()
        self._binders_initialized = False
        self._custom_binders: dict[str, ViewerWidgetBinder] = {}
        self._engineering_binder: EngineeringViewerWidgetBinder | None = None
        self._bound_overlays: dict[_OverlayKey, _BoundOverlay] = {}
        self._retained_inline_key: _OverlayKey | None = None
        self._inline_retention_identities: dict[_OverlayKey, tuple[str, str, int]] = {}
        self._detached_windows: dict[_OverlayKey, _DetachedViewerWindow] = {}
        self._pending_detached_sessions: dict[_OverlayKey, str] = {}
        self._fullscreen_hold_key: _OverlayKey | None = None
        self._embedded_interaction_active: set[_OverlayKey] = set()
        self._native_presentation_handoff = NativePresentationHandoff(
            overlay_manager_provider=lambda: self._overlay_manager,
            completion_callback=self._complete_embedded_exit_demotion,
            timeout_ms=300,
        )
        self._viewer_render_signatures: dict[_OverlayKey, tuple[Any, ...]] = {}
        self._viewer_view_states: dict[_OverlayKey, tuple[tuple[Any, ...], object]] = {}
        self._preview_cache_revision = 0
        self._viewer_overlay_revision = 0
        self._owns_content_fullscreen_target = False
        self._presentation_service = _ViewerHostPresentationService(
            content_fullscreen_bridge_provider=lambda: self._content_fullscreen_bridge,
        )
        self._last_error = ""
        self._sync_queued = False
        self._sync_suspended = False
        self._shutdown = False
        self._fullscreen_shortcut_filter = _FullscreenShortcutFilter(self)
        self._shortcut_filtered_widgets: set[QWidget] = set()

        self._connect_signals()
        self._schedule_sync()

    @property
    def binder_registry(self) -> ViewerWidgetBinderRegistry:
        return self._ensure_binders_initialized()

    @property
    def overlay_manager(self) -> EmbeddedViewerOverlayManager | None:
        return self._overlay_manager

    @pyqtProperty(int, notify=state_changed)
    def active_overlay_count(self) -> int:
        return sum(
            bound.presentation != _PRESENTATION_RETAINED_INLINE
            for bound in self._bound_overlays.values()
        )

    @pyqtProperty(str, notify=state_changed)
    def retained_inline_viewer_node_id(self) -> str:
        return self._retained_inline_key[1] if self._retained_inline_key is not None else ""

    @pyqtProperty(int, notify=state_changed)
    def detached_viewer_count(self) -> int:
        return len(self._detached_windows)

    @pyqtProperty(int, notify=state_changed)
    def viewer_overlay_revision(self) -> int:
        return self._viewer_overlay_revision

    @pyqtProperty(str, notify=last_error_changed)
    def last_error(self) -> str:
        return self._last_error

    @pyqtProperty(int, notify=preview_cache_changed)
    def preview_cache_revision(self) -> int:
        return self._preview_cache_revision

    @pyqtSlot(str, bool)
    def set_embedded_interaction_active(self, node_id: str, active: bool) -> None:
        if self._shutdown:
            return
        key = self._key_for_node_id(node_id)
        if key is None:
            return
        changed = False
        demotion_deferred = False
        if bool(active):
            self._native_presentation_handoff.cancel(key)
            self._remember_inline_retention_identity(key)
            if key not in self._embedded_interaction_active:
                self._embedded_interaction_active.add(key)
                changed = True
        elif key in self._embedded_interaction_active:
            if self._content_fullscreen_key() != key:
                if not self._cached_preview_available(key):
                    demotion_deferred = self._capture_embedded_exit_state(key)
            self._embedded_interaction_active.remove(key)
            changed = True
        elif self._native_presentation_handoff.contains(key):
            # A deferred live-exit demotion is already in flight for this
            # key; its handoff (or timeout) notifies the session bridge.
            demotion_deferred = True
        bridge = self._viewer_session_bridge
        if not demotion_deferred and (bool(active) or self._content_fullscreen_key() != key):
            bridge_setter = getattr(bridge, "set_embedded_interaction_active", None)
            if callable(bridge_setter):
                try:
                    bridge_setter(key[1], bool(active), {"workspace_id": key[0]})
                except TypeError:
                    bridge_setter(key[1], bool(active))
        if changed:
            self._schedule_sync()

    @pyqtSlot(str, str)
    def notify_cached_preview_swapped(self, node_id: str, source: str) -> None:
        """QML confirms the cached preview Image now shows ``source``.

        The demotion that hides the live overlay must wait until the frame
        containing the freshly captured proxy image has actually rendered,
        or the reveal repaints a stale backing store and the old preview
        flashes between live and proxy modes.
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
        if self._content_fullscreen_key() == key:
            return
        bridge = self._viewer_session_bridge
        bridge_setter = getattr(bridge, "set_embedded_interaction_active", None)
        if callable(bridge_setter):
            try:
                bridge_setter(key[1], False, {"workspace_id": key[0]})
            except TypeError:
                bridge_setter(key[1], False)
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

    @pyqtSlot(str, result=bool)
    def open_detached_viewer(self, node_id: str) -> bool:
        if self._shutdown:
            return False
        key = self._key_for_node_id(node_id)
        if key is None:
            return False
        snapshot = self._snapshot_for_key(key)
        if snapshot is None or snapshot.phase != "open":
            return False
        if not self._snapshot_ready_for_live_widget(snapshot):
            self._acquire_presentation_hold(key)
            self._pending_detached_sessions[key] = snapshot.session_id
            self._schedule_sync()
            self.state_changed.emit()
            return True
        existing_window = self._detached_windows.get(key)
        if existing_window is not None and existing_window.session_id != snapshot.session_id:
            if not self._close_detached_window(key, reason="session_replaced"):
                return False
        self._acquire_presentation_hold(key)
        window = self._ensure_detached_window(snapshot)
        if window is None:
            self._release_presentation_hold_if_unused(key)
            return False
        self._pending_detached_sessions.pop(key, None)
        if self._content_fullscreen_key() == key:
            bridge = self._content_fullscreen_bridge
            close = getattr(bridge, "request_close", None) if bridge is not None else None
            if callable(close):
                close()
        else:
            window.focus_window()
        self._schedule_sync()
        self.state_changed.emit()
        return True

    @pyqtSlot(str, result=bool)
    def close_detached_viewer(self, node_id: str) -> bool:
        key = self._key_for_node_id(node_id)
        if key is None:
            return False
        if key not in self._detached_windows:
            if self._pending_detached_sessions.pop(key, None) is None:
                return False
            self._release_presentation_hold(key)
            self.state_changed.emit()
            return True
        if not self._close_detached_window(key, reason="detached_closed"):
            return False
        self.state_changed.emit()
        return True

    @pyqtSlot(str, result=bool)
    def detached_viewer_active(self, node_id: str) -> bool:
        key = self._key_for_node_id(node_id)
        if key is None:
            return False
        return key in self._detached_windows or key in self._pending_detached_sessions

    def owns_detached_viewer_window(self, window: QWidget | None = None) -> bool:
        candidate = window or QApplication.activeWindow()
        if not isinstance(candidate, QWidget):
            return False
        top_level = candidate.window()
        return any(top_level is detached for detached in self._detached_windows.values())

    def _acquire_presentation_hold(self, key: _OverlayKey) -> None:
        bridge = self._viewer_session_bridge
        adder = getattr(bridge, "add_viewer_presentation_hold", None) if bridge is not None else None
        if not callable(adder):
            return
        try:
            adder(key[1], {"workspace_id": key[0]})
        except TypeError:
            adder(key[1])
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))

    def _release_presentation_hold(self, key: _OverlayKey) -> None:
        bridge = self._viewer_session_bridge
        remover = getattr(bridge, "remove_viewer_presentation_hold", None) if bridge is not None else None
        if not callable(remover):
            return
        try:
            remover(key[1], {"workspace_id": key[0]})
        except TypeError:
            remover(key[1])
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))

    def _release_presentation_hold_if_unused(self, key: _OverlayKey) -> None:
        if (
            key in self._detached_windows
            or key in self._pending_detached_sessions
            or self._fullscreen_hold_key == key
        ):
            return
        self._release_presentation_hold(key)

    def _sync_fullscreen_hold(self) -> None:
        next_key = self._content_fullscreen_key()
        previous_key = self._fullscreen_hold_key
        if next_key == previous_key:
            return
        self._fullscreen_hold_key = next_key
        if next_key is not None:
            self._acquire_presentation_hold(next_key)
        if previous_key is not None:
            self._release_presentation_hold_if_unused(previous_key)

    def _clear_fullscreen_hold(self) -> None:
        key = self._fullscreen_hold_key
        self._fullscreen_hold_key = None
        if key is not None:
            self._release_presentation_hold_if_unused(key)

    def _clear_pending_detached_sessions(self) -> None:
        for key in list(self._pending_detached_sessions):
            self._pending_detached_sessions.pop(key, None)
            self._release_presentation_hold_if_unused(key)

    @pyqtSlot(str, result=bool)
    def embedded_live_overlay_ready(self, node_id: str) -> bool:
        if self._shutdown:
            return False
        key = self._key_for_node_id(node_id)
        if key is None or key not in self._embedded_interaction_active:
            return False
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

    def capture_overlay_camera_state(self, node_id: str, *, workspace_id: str = "") -> dict[str, Any]:
        if self._shutdown:
            return {}
        normalized_workspace_id = _string(workspace_id)
        if not normalized_workspace_id and self._viewer_session_bridge is not None:
            normalized_workspace_id = _string(self._viewer_session_bridge.active_workspace_id)
        normalized_node_id = _string(node_id)
        if not normalized_workspace_id or not normalized_node_id:
            return {}

        bound = self._bound_overlays.get((normalized_workspace_id, normalized_node_id))
        if bound is None:
            return {}
        widget = self._current_widget_for_bound_overlay(
            (normalized_workspace_id, normalized_node_id),
            bound,
        )
        if widget is None:
            return {}
        capture = getattr(bound.binder, "capture_camera_state", None)
        if not callable(capture):
            return {}
        try:
            return _mapping(capture(widget))
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return {}

    def refresh_bound_widget_canvas_theme(self) -> int:
        """Re-theme live viewer canvases after a shell theme switch."""
        if self._shutdown:
            return 0
        refreshed = 0
        for key, bound in list(self._bound_overlays.items()):
            apply_theme = getattr(bound.binder, "apply_canvas_theme", None)
            if not callable(apply_theme):
                continue
            widget = self._current_widget_for_bound_overlay(key, bound)
            if not isinstance(widget, QWidget):
                continue
            try:
                if apply_theme(widget, bound.snapshot.options):
                    refreshed += 1
            except Exception as exc:  # noqa: BLE001
                self._set_last_error(str(exc))
        return refreshed

    def _bound_overlay_widget_for_node(self, node_id: str) -> tuple[Any, QWidget | None]:
        key = self._key_for_node_id(node_id)
        if key is None:
            return None, None
        bound = self._bound_overlays.get(key)
        if bound is None:
            return None, None
        widget = self._current_widget_for_bound_overlay(key, bound)
        if not isinstance(widget, QWidget):
            return bound, None
        return bound, widget

    @pyqtSlot(str, result="QVariantMap")
    def viewer_render_stats(self, node_id: str) -> dict[str, Any]:
        if self._shutdown:
            return {}
        bound, widget = self._bound_overlay_widget_for_node(node_id)
        if bound is None or widget is None:
            return {}
        stats_getter = getattr(bound.binder, "render_stats", None)
        if not callable(stats_getter):
            return {}
        try:
            return _mapping(stats_getter(widget))
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return {}

    @pyqtSlot(str, str, bool, result=bool)
    def set_viewer_layer_visibility(self, node_id: str, layer_name: str, visible: bool) -> bool:
        if self._shutdown:
            return False
        bound, widget = self._bound_overlay_widget_for_node(node_id)
        setter = getattr(bound.binder, "set_layer_visibility", None) if bound is not None else None
        if widget is None or not callable(setter):
            return False
        try:
            changed = bool(setter(widget, str(layer_name), bool(visible)))
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return False
        if changed:
            self._bump_viewer_overlay_revision()
            self.state_changed.emit()
        return changed

    @pyqtSlot(str, str, result=bool)
    def isolate_viewer_layer(self, node_id: str, layer_name: str) -> bool:
        if self._shutdown:
            return False
        bound, widget = self._bound_overlay_widget_for_node(node_id)
        isolator = getattr(bound.binder, "isolate_layer", None) if bound is not None else None
        if widget is None or not callable(isolator):
            return False
        try:
            changed = bool(isolator(widget, str(layer_name)))
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return False
        if changed:
            self._bump_viewer_overlay_revision()
            self.state_changed.emit()
        return changed

    @pyqtSlot(str, result="QVariantMap")
    def viewer_selection_snapshot(self, node_id: str) -> dict[str, Any]:
        if self._shutdown:
            return {}
        bound, widget = self._bound_overlay_widget_for_node(node_id)
        snapshot = getattr(bound.binder, "selection_snapshot", None) if bound is not None else None
        if widget is None or not callable(snapshot):
            return {}
        try:
            return dict(snapshot(widget) or {})
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return {}

    @pyqtSlot(str, str, result=bool)
    def set_viewer_selection_filter(self, node_id: str, value: str) -> bool:
        if self._shutdown:
            return False
        bound, widget = self._bound_overlay_widget_for_node(node_id)
        setter = getattr(bound.binder, "set_selection_filter", None) if bound is not None else None
        if widget is None or not callable(setter):
            return False
        try:
            changed = bool(setter(widget, str(value)))
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return False
        if changed:
            self._bump_viewer_overlay_revision()
            self.state_changed.emit()
        return changed

    @pyqtSlot(str, "QVariantList", result=bool)
    def activate_viewer_selection(
        self,
        node_id: str,
        entities: list[Any],
    ) -> bool:
        if self._shutdown:
            return False
        bound, widget = self._bound_overlay_widget_for_node(node_id)
        activate = getattr(bound.binder, "activate_selection", None) if bound is not None else None
        if widget is None or not callable(activate):
            return False
        try:
            changed = bool(activate(widget, list(entities)))
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return False
        if changed:
            self._bump_viewer_overlay_revision()
            self.state_changed.emit()
        return changed

    @pyqtSlot(str, str, result=bool)
    def apply_standard_view(self, node_id: str, view_id: str) -> bool:
        if self._shutdown:
            return False
        _bound, widget = self._bound_overlay_widget_for_node(node_id)
        if widget is None:
            return False
        method_name = {
            "iso": "view_isometric",
            "xy": "view_xy",
            "xz": "view_xz",
            "yz": "view_yz",
        }.get(_string(view_id).lower())
        if method_name is None:
            return False
        method = getattr(widget, method_name, None)
        if not callable(method):
            return False
        try:
            method()
            render = getattr(widget, "render", None)
            if callable(render):
                render()
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return False
        return True

    @pyqtSlot(str, result=bool)
    def reset_overlay_camera(self, node_id: str) -> bool:
        if self._shutdown:
            return False
        _bound, widget = self._bound_overlay_widget_for_node(node_id)
        if widget is None:
            return False
        reset_camera = getattr(widget, "reset_camera", None)
        if not callable(reset_camera):
            return False
        try:
            reset_camera()
            render = getattr(widget, "render", None)
            if callable(render):
                render()
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return False
        return True

    @pyqtSlot(str, result=bool)
    def fit_viewer_selection(self, node_id: str) -> bool:
        if self._shutdown:
            return False
        bound, widget = self._bound_overlay_widget_for_node(node_id)
        fit = getattr(bound.binder, "fit_selection", None) if bound is not None else None
        if widget is None or not callable(fit):
            return False
        try:
            return bool(fit(widget))
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return False

    @pyqtSlot(str, bool, result=bool)
    def toggle_viewer_selection_isolate(self, node_id: str, update_selection: bool = False) -> bool:
        if self._shutdown:
            return False
        bound, widget = self._bound_overlay_widget_for_node(node_id)
        toggle = getattr(bound.binder, "toggle_selection_isolate", None) if bound is not None else None
        if widget is None or not callable(toggle):
            return False
        try:
            changed = bool(toggle(widget, bool(update_selection)))
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return False
        if changed:
            self._bump_viewer_overlay_revision()
            self.state_changed.emit()
        return changed

    @pyqtSlot(str, result="QVariantMap")
    def camera_state_snapshot(self, node_id: str) -> dict[str, Any]:
        return self.capture_overlay_camera_state(node_id)

    @pyqtSlot(str, "QVariantMap", result=bool)
    def apply_overlay_camera_state(self, node_id: str, state: dict[str, Any]) -> bool:
        if self._shutdown:
            return False
        bound, widget = self._bound_overlay_widget_for_node(node_id)
        if bound is None or widget is None:
            return False
        restore = getattr(bound.binder, "restore_view_state", None)
        if not callable(restore):
            return False
        try:
            return bool(restore(widget, _mapping(state)))
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return False

    @pyqtSlot(str, result="QVariantMap")
    def export_viewer_screenshot(self, node_id: str) -> dict[str, Any]:
        if self._shutdown:
            return {"ok": False, "path": "", "error": "Viewer host service is unavailable."}
        key = self._key_for_node_id(node_id)
        if key is None:
            return {"ok": False, "path": "", "error": "The viewer node is unavailable."}
        image = self.capture_overlay_preview_image(key[1], workspace_id=key[0])
        if image.isNull():
            image = self._cached_preview_image_for_key(key)
        if image.isNull():
            return {
                "ok": False,
                "path": "",
                "error": "No live viewer or cached preview is available to capture.",
            }
        suggested_name = self._suggested_screenshot_name(key)
        output_path = self._pick_screenshot_path(suggested_name)
        if not output_path:
            return {"ok": False, "path": "", "error": ""}
        try:
            saved = image.save(output_path)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "path": output_path, "error": str(exc)}
        if not saved:
            return {"ok": False, "path": output_path, "error": "Could not write the screenshot file."}
        return {"ok": True, "path": output_path, "error": ""}

    @pyqtSlot(str, result=bool)
    def copy_viewer_screenshot_to_clipboard(self, node_id: str) -> bool:
        if self._shutdown:
            return False
        image = self.capture_overlay_preview_image(node_id)
        application = QApplication.instance()
        if application is None or image.isNull():
            return False
        application.clipboard().setImage(image)
        return not application.clipboard().image().isNull()

    def _cached_preview_image_for_key(self, key: _OverlayKey) -> QImage:
        provider = self._preview_cache_provider
        request_image = getattr(provider, "requestImage", None)
        if not callable(request_image):
            return QImage()
        try:
            from urllib.parse import quote

            image, _size = request_image(
                f"preview?workspace={quote(key[0], safe='')}&node={quote(key[1], safe='')}",
                QSize(),
            )
        except Exception:  # noqa: BLE001
            return QImage()
        return image if isinstance(image, QImage) else QImage()

    def _suggested_screenshot_name(self, key: _OverlayKey) -> str:
        snapshot = self._snapshot_for_key(key)
        parts: list[str] = []
        if snapshot is not None:
            summary = _mapping(snapshot.summary)
            for value in (summary.get("result_name"), summary.get("set_label")):
                text = _string(value)
                if text:
                    parts.append(text)
        if not parts:
            parts.append(key[1])
        raw_name = "_".join(parts) + ".png"
        sanitized = "".join(
            character if character.isalnum() or character in {"-", "_", "."} else "_"
            for character in raw_name
        )
        return sanitized or "viewer_screenshot.png"

    def _pick_screenshot_path(self, suggested_name: str) -> str:
        picker = self._save_file_dialog
        if not callable(picker):
            return ""
        try:
            return _string(
                picker(
                    title="Export Viewer Screenshot",
                    suggested_path=suggested_name,
                    file_filter="PNG Image (*.png)",
                    default_suffix="png",
                )
            )
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return ""

    def capture_overlay_preview_image(self, node_id: str, *, workspace_id: str = "") -> QImage:
        if self._shutdown:
            return QImage()
        normalized_workspace_id = _string(workspace_id)
        if not normalized_workspace_id and self._viewer_session_bridge is not None:
            normalized_workspace_id = _string(self._viewer_session_bridge.active_workspace_id)
        normalized_node_id = _string(node_id)
        if not normalized_workspace_id or not normalized_node_id:
            return QImage()

        bound = self._bound_overlays.get((normalized_workspace_id, normalized_node_id))
        if bound is None:
            return QImage()
        widget = self._current_widget_for_bound_overlay(
            (normalized_workspace_id, normalized_node_id),
            bound,
        )
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

        grab_framebuffer = getattr(widget, "grabFramebuffer", None)
        if callable(grab_framebuffer):
            try:
                captured = grab_framebuffer()
            except Exception as exc:  # noqa: BLE001
                self._set_last_error(str(exc))
                return QImage()
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
        if pixmap.isNull():
            return QImage()
        image = pixmap.toImage()
        if image.isNull():
            return QImage()
        return self._normalized_overlay_preview_image(
            (normalized_workspace_id, normalized_node_id),
            image,
        )

    def _normalized_overlay_preview_image(self, key: _OverlayKey, image: QImage) -> QImage:
        if image.isNull():
            return QImage()
        bound = self._bound_overlays.get(key)
        container = bound.container if bound is not None else None
        if container is None and self._overlay_manager is not None:
            container = self._overlay_manager.overlay_container(key[1], workspace_id=key[0])
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
        longest_edge = max(expected_size.width(), expected_size.height())
        if longest_edge > _MAX_INLINE_VIEWER_PREVIEW_EDGE_PX:
            scale = _MAX_INLINE_VIEWER_PREVIEW_EDGE_PX / float(longest_edge)
            expected_size = QSize(
                max(1, round(expected_size.width() * scale)),
                max(1, round(expected_size.height() * scale)),
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

    def register_binder(self, backend_id: str, binder: ViewerWidgetBinder) -> None:
        if self._shutdown:
            return
        normalized_backend_id = _string(backend_id)
        if not normalized_backend_id:
            raise ValueError("viewer widget binder backend_id is required")
        self._custom_binders[normalized_backend_id] = binder
        if self._binders_initialized:
            self._binder_registry.register(normalized_backend_id, binder)
        self._schedule_sync()

    def _ensure_binders_initialized(self) -> ViewerWidgetBinderRegistry:
        if self._shutdown or self._binders_initialized:
            return self._binder_registry
        self._register_builtin_binders()
        for backend_id, binder in self._custom_binders.items():
            self._binder_registry.register(backend_id, binder)
        self._binders_initialized = True
        return self._binder_registry

    def _register_builtin_binders(self) -> None:
        if self._engineering_binder is not None:
            self._engineering_binder.shutdown()
        engineering_binder = EngineeringViewerWidgetBinder()
        engineering_binder.load_ready.connect(self._on_engineering_load_ready)
        engineering_binder.selection_changed.connect(self._on_engineering_selection_changed)
        self._engineering_binder = engineering_binder
        self._binder_registry.register(engineering_binder.backend_id, engineering_binder)

    def set_overlay_manager(self, overlay_manager: EmbeddedViewerOverlayManager | None) -> None:
        if self._shutdown:
            return
        if self._overlay_manager is overlay_manager:
            return
        self._native_presentation_handoff.flush()
        self._release_all_bindings(reason="overlay_manager_replaced")
        self._close_all_detached_windows(reason="overlay_manager_replaced")
        self._clear_pending_detached_sessions()
        previous_overlay_manager = self._overlay_manager
        self._overlay_manager = overlay_manager
        if previous_overlay_manager is not None:
            self._set_viewer_content_fullscreen_target(previous_overlay_manager, None, force_clear=True)
            self._set_active_viewer_overlays(previous_overlay_manager, ())
        self._schedule_sync()

    def reset(self, *, reason: str = "") -> None:
        if self._shutdown:
            return
        if self._engineering_binder is not None:
            self._engineering_binder.cancel_all_loads()
        self._native_presentation_handoff.flush()
        self._release_all_bindings(reason=reason or "reset")
        self._close_all_detached_windows(reason=reason or "reset")
        self._clear_pending_detached_sessions()
        self._clear_fullscreen_hold()
        self._embedded_interaction_active.clear()
        self._clear_all_cached_previews()
        overlay_manager = self._overlay_manager
        if overlay_manager is not None:
            self._set_viewer_content_fullscreen_target(overlay_manager, None)
            self._set_active_viewer_overlays(overlay_manager, ())
        self._sync_fullscreen_shortcut_filter()
        self._set_last_error("")
        self.state_changed.emit()

    def suspend_sync(self, *, reason: str = "") -> None:
        if self._shutdown:
            return
        self._sync_suspended = True
        if reason:
            self._set_last_error("")

    def resume_sync(self) -> None:
        if self._shutdown:
            return
        if not self._sync_suspended:
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
        self._sync_fullscreen_shortcut_filter()
        self._release_all_bindings(reason=reason or "shutdown")
        self._close_all_detached_windows(reason=reason or "shutdown")
        self._clear_pending_detached_sessions()
        self._clear_fullscreen_hold()
        bridge = self._content_fullscreen_bridge
        if bridge is not None:
            try:
                bridge.content_fullscreen_changed.disconnect(
                    self._on_content_fullscreen_changed
                )
            except (TypeError, RuntimeError):
                pass
        if self._engineering_binder is not None:
            self._engineering_binder.shutdown()
            self._engineering_binder = None
        self._embedded_interaction_active.clear()
        self._clear_all_cached_previews()
        overlay_manager = self._overlay_manager
        if overlay_manager is not None:
            self._set_viewer_content_fullscreen_target(overlay_manager, None)
            self._set_active_viewer_overlays(overlay_manager, ())
        self._overlay_manager = None
        self._content_fullscreen_bridge = None
        self._viewer_session_bridge = None
        self._qml_engine_provider = None
        self._save_file_dialog = None
        self._cycle_camera_bookmark = None
        self._set_last_error("")
        self.state_changed.emit()

    def _connect_signals(self) -> None:
        self._connect_signal(self._viewer_session_bridge, "sessions_changed", self._schedule_sync)
        self._connect_signal(self._viewer_session_bridge, "active_workspace_changed", self._schedule_sync)
        bridge = self._content_fullscreen_bridge
        if bridge is not None:
            bridge.content_fullscreen_changed.connect(
                self._on_content_fullscreen_changed
            )
        self._sync_fullscreen_hold()

    def _on_content_fullscreen_changed(self) -> None:
        self._sync_fullscreen_hold()
        self._schedule_sync()

    def _qml_engine(self) -> Any:
        provider = self._qml_engine_provider
        if provider is None:
            return None
        try:
            return provider()
        except Exception:  # noqa: BLE001
            return None

    def _ensure_detached_window(
        self,
        snapshot: _ViewerHostSessionSnapshot,
    ) -> _DetachedViewerWindow | None:
        key = snapshot.overlay_key
        title = _string(snapshot.summary.get("title")) or "Model Viewer"
        window = self._detached_windows.get(key)
        if window is not None:
            window.setWindowTitle(title)
            window.update_controls(
                node_id=snapshot.node_id,
                fullscreen_bridge=self._content_fullscreen_bridge,
            )
            return window
        engine = self._qml_engine()
        if engine is None:
            self._set_last_error("The QML engine is unavailable for the detached viewer controls.")
            return None
        window = _DetachedViewerWindow(
            key=key,
            session_id=snapshot.session_id,
            title=title,
            qml_engine=engine,
            on_closed=self._on_detached_window_closed,
        )
        window.update_controls(
            node_id=snapshot.node_id,
            fullscreen_bridge=self._content_fullscreen_bridge,
        )
        self._detached_windows[key] = window
        return window

    def _on_detached_window_closed(self, key: _OverlayKey) -> bool:
        window = self._detached_windows.get(key)
        if window is None:
            return True
        self._capture_cached_live_state_for_key(key)
        widget = window.widget
        if widget is not None:
            bound = self._bound_overlays.get(key)
            if bound is not None and bound.widget is widget:
                if not self._prepare_widget_for_reparent(bound.binder, widget):
                    return False
            self._detached_windows.pop(key, None)
            window.detach_widget(widget)
            if not self._prepare_detached_binding_for_inline(key, widget):
                self._schedule_sync()
        else:
            self._detached_windows.pop(key, None)
        self._release_presentation_hold_if_unused(key)
        window.deleteLater()
        self.state_changed.emit()
        return True

    def _close_detached_window(self, key: _OverlayKey, *, reason: str) -> bool:
        window = self._detached_windows.get(key)
        if window is None:
            return True
        self._capture_cached_live_state_for_key(key)
        widget = window.widget
        redock_ready = True
        if widget is not None:
            bound = self._bound_overlays.get(key)
            if bound is not None and bound.widget is widget:
                if not self._prepare_widget_for_reparent(bound.binder, widget):
                    return False
            self._detached_windows.pop(key, None)
            window.detach_widget(widget)
            redock_ready = self._prepare_detached_binding_for_inline(key, widget)
        else:
            self._detached_windows.pop(key, None)
        self._release_presentation_hold_if_unused(key)
        window.close_from_service()
        window.deleteLater()
        if reason and redock_ready:
            self._set_last_error("")
        if not redock_ready:
            self._schedule_sync()
        return True

    def _close_all_detached_windows(self, *, reason: str) -> None:
        for key in list(self._detached_windows):
            self._close_detached_window(key, reason=reason)

    def _prepare_detached_binding_for_inline(self, key: _OverlayKey, widget: QWidget) -> bool:
        bound = self._bound_overlays.get(key)
        if bound is None or bound.widget is not widget:
            return True
        overlay_manager = self._overlay_manager
        if overlay_manager is None:
            bound.presentation = _PRESENTATION_OVERLAY
            bound.container = None
            return True
        self._set_active_viewer_overlays(
            overlay_manager,
            (
                candidate.snapshot.overlay_spec()
                for candidate_key, candidate in self._bound_overlays.items()
                if candidate_key == key or candidate.presentation == _PRESENTATION_OVERLAY
            ),
        )
        self._sync_overlay_manager_now()
        destination = overlay_manager.overlay_container(
            bound.snapshot.node_id,
            workspace_id=bound.snapshot.workspace_id,
        )
        overlay_manager.attach_overlay_widget(
            bound.snapshot.node_id,
            widget,
            workspace_id=bound.snapshot.workspace_id,
        )
        self._sync_overlay_manager_now()
        refresh_result = self._refresh_widget_after_presentation_attach(bound.binder, widget)
        if refresh_result is None:
            return False
        if not refresh_result:
            refresh_error = self._last_error or "Viewer could not refresh after attachment."
            self._bound_overlays.pop(key, None)
            self._release_widget(
                snapshot=bound.snapshot,
                binder=bound.binder,
                container=destination,
                widget=widget,
                presentation=_PRESENTATION_OVERLAY,
                reason="attach_refresh_error",
            )
            self._set_last_error(refresh_error)
            self._sync_fullscreen_shortcut_filter()
            return False
        bound.presentation = _PRESENTATION_OVERLAY
        bound.container = destination
        self._sync_fullscreen_shortcut_filter()
        return True

    @staticmethod
    def _connect_signal(source: object | None, name: str, slot) -> None:  # noqa: ANN001
        signal = getattr(source, name, None) if source is not None else None
        if signal is not None and hasattr(signal, "connect"):
            signal.connect(slot)

    def _schedule_sync(self) -> None:
        if self._shutdown:
            return
        if self._sync_queued:
            return
        self._sync_queued = True
        QTimer.singleShot(0, self._run_queued_sync)

    @pyqtSlot(str, str, str, int)
    def _on_engineering_load_ready(
        self,
        _workspace_id: str,
        _node_id: str,
        _session_id: str,
        _transport_revision: int,
    ) -> None:
        self._schedule_sync()

    @pyqtSlot(str, str)
    def _on_engineering_selection_changed(self, _workspace_id: str, _node_id: str) -> None:
        self._bump_viewer_overlay_revision()
        self.state_changed.emit()

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
        bridge = self._viewer_session_bridge
        if overlay_manager is None or bridge is None:
            self._release_all_bindings(reason="overlay_manager_unavailable")
            self._close_all_detached_windows(reason="overlay_manager_unavailable")
            self._clear_pending_detached_sessions()
            if overlay_manager is not None:
                self._set_viewer_content_fullscreen_target(overlay_manager, None)
                self._set_active_viewer_overlays(overlay_manager, ())
            self.state_changed.emit()
            return

        self._sync_preview_cache_signatures()
        self._set_viewer_content_fullscreen_target(overlay_manager, self._content_fullscreen_overlay_spec())
        projected_sessions = bridge.sessions_model
        self._prune_inline_retention_identities()
        desired_overlays, errors = self._presentation_service.desired_overlays(
            projected_sessions,
            self._ensure_binders_initialized,
        )
        for key in list(self._detached_windows):
            desired = desired_overlays.get(key)
            if desired is None:
                self._close_detached_window(key, reason="node_unavailable")
            elif self._detached_windows[key].session_id != desired[0].session_id:
                self._close_detached_window(key, reason="session_replaced")

        for key, session_id in list(self._pending_detached_sessions.items()):
            snapshot = self._snapshot_for_key(key)
            if snapshot is None or snapshot.phase != "open" or snapshot.session_id != session_id:
                self._pending_detached_sessions.pop(key, None)
                self._release_presentation_hold_if_unused(key)
                continue
            desired = desired_overlays.get(key)
            if desired is not None:
                self._ensure_detached_window(desired[0])
                self._pending_detached_sessions.pop(key, None)
            elif self._snapshot_ready_for_live_widget(snapshot):
                self._pending_detached_sessions.pop(key, None)
                self._release_presentation_hold_if_unused(key)

        for key, bound in list(self._bound_overlays.items()):
            if bound.widget is not None and sip.isdeleted(bound.widget):
                self._bound_overlays.pop(key, None)
                self._inline_retention_identities.pop(key, None)
                if self._retained_inline_key == key:
                    self._retained_inline_key = None
                self._bump_viewer_overlay_revision()
                continue
            desired = desired_overlays.get(key)
            if desired is None:
                if self._retain_inline_binding(key):
                    continue
                self._capture_cached_live_state_for_key(key)
                self._release_binding(key, reason="inactive")
                continue
            if desired[0].backend_id != bound.snapshot.backend_id or desired[1] is not bound.binder:
                self._capture_cached_live_state_for_key(key)
                self._release_binding(key, reason="inactive")

        errors.extend(self._retarget_overlay_bindings_before_overlay_reconcile(desired_overlays))

        overlay_specs = [
            snapshot.overlay_spec()
            for key, (snapshot, _binder) in desired_overlays.items()
            if self._presentation_target_for_key(key) == _PRESENTATION_OVERLAY
        ]
        retained_key = self._retained_inline_key
        retained = self._bound_overlays.get(retained_key) if retained_key is not None else None
        if retained_key not in desired_overlays and retained is not None:
            overlay_specs.append(
                EmbeddedViewerOverlaySpec(
                    workspace_id=retained.snapshot.workspace_id,
                    node_id=retained.snapshot.node_id,
                    session_id=retained.snapshot.session_id,
                    visible=False,
                )
            )
        self._set_active_viewer_overlays(overlay_manager, overlay_specs)
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
            if presentation == _PRESENTATION_DETACHED:
                window = self._detached_windows.get(key)
                if window is not None:
                    window.prepare_destination()
            signature = self._binding_signature(snapshot)
            bound = self._bound_overlays.get(key)
            if (
                bound is not None
                and bound.presentation == _PRESENTATION_RETAINED_INLINE
                and bound.binder is binder
                and self._preview_cache_signature(bound.snapshot)
                == self._preview_cache_signature(snapshot)
                and bound.container is container
                and bound.widget is not None
            ):
                bound.presentation = presentation
                bound.snapshot = snapshot
                bound.signature = signature
                if self._retained_inline_key == key:
                    self._retained_inline_key = None
                self._bump_viewer_overlay_revision()
                continue
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
            if bound is not None:
                self._capture_cached_live_state_for_key(key)
                if bound.binder is binder and bound.widget is not None:
                    current_widget = bound.widget
            prepared_for_bind = False
            if (
                isinstance(current_widget, QWidget)
                and current_widget.parent() is not container
            ):
                if not self._prepare_widget_for_reparent(binder, current_widget):
                    errors.append(self._last_error or "Viewer could not change presentation.")
                    continue
                prepared_for_bind = True
            try:
                widget = binder.bind_widget(
                    snapshot.bind_request(
                        container=container,
                        current_widget=current_widget,
                    )
                )
            except ViewerWidgetNoBind as exc:
                self._bound_overlays.pop(key, None)
                self._release_widget(
                    snapshot=snapshot,
                    binder=binder,
                    container=container,
                    widget=current_widget,
                    presentation=presentation,
                    reason="load_pending" if bool(getattr(exc, "retry_when_ready", False)) else "no_bind",
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
            if not self._attach_widget_to_presentation(
                key,
                snapshot=snapshot,
                binder=binder,
                widget=widget,
                presentation=presentation,
                already_prepared=prepared_for_bind and widget is current_widget,
            ):
                errors.append(self._last_error or "Viewer could not change presentation.")
                continue
            refresh_result = self._refresh_widget_after_presentation_attach(binder, widget)
            if refresh_result is None:
                continue
            if not refresh_result:
                refresh_error = self._last_error or "Viewer could not refresh after attachment."
                self._bound_overlays.pop(key, None)
                self._release_widget(
                    snapshot=snapshot,
                    binder=binder,
                    container=container,
                    widget=widget,
                    presentation=presentation,
                    reason="attach_refresh_error",
                )
                errors.append(refresh_error)
                continue
            self._bound_overlays[key] = _BoundOverlay(
                binder=binder,
                snapshot=snapshot,
                signature=signature,
                presentation=presentation,
                container=container,
                widget=widget,
            )
            if self._retained_inline_key == key:
                self._retained_inline_key = None
            self._restore_cached_view_state_for_binding(
                key,
                binder,
                widget,
                self._camera_relevant_signature(snapshot),
            )
            self._bump_viewer_overlay_revision()

        retained_key = self._retained_inline_key
        if retained_key is not None:
            replacement_key = next(
                (
                    key
                    for key, (snapshot, _binder) in desired_overlays.items()
                    if key != retained_key
                    and key in self._embedded_interaction_active
                    and self._presentation_target_for_key(key) == _PRESENTATION_OVERLAY
                    and self._inline_retention_identity_matches(key, snapshot)
                    and key in self._bound_overlays
                ),
                None,
            )
            if replacement_key is not None:
                self._release_binding(retained_key, reason="viewer_replaced")
                self._set_active_viewer_overlays(
                    overlay_manager,
                    (
                        snapshot.overlay_spec()
                        for key, (snapshot, _binder) in desired_overlays.items()
                        if self._presentation_target_for_key(key) == _PRESENTATION_OVERLAY
                    ),
                )
                self._sync_overlay_manager_now()

        self._sync_fullscreen_shortcut_filter()
        self._set_last_error(errors[0] if errors else "")
        self.state_changed.emit()

    @staticmethod
    def _retention_identity(snapshot: _ViewerHostSessionSnapshot) -> tuple[str, str, int]:
        return snapshot.session_id, snapshot.backend_id, snapshot.transport_revision

    def _remember_inline_retention_identity(self, key: _OverlayKey) -> None:
        snapshot = self._snapshot_for_key(key)
        if snapshot is not None and snapshot.phase == "open":
            self._inline_retention_identities[key] = self._retention_identity(snapshot)

    def _inline_retention_identity_matches(
        self,
        key: _OverlayKey,
        snapshot: _ViewerHostSessionSnapshot,
    ) -> bool:
        return self._inline_retention_identities.get(key) == self._retention_identity(snapshot)

    def _prune_inline_retention_identities(self) -> None:
        for key, identity in list(self._inline_retention_identities.items()):
            snapshot = self._snapshot_for_key(key)
            if (
                snapshot is None
                or snapshot.phase != "open"
                or identity != self._retention_identity(snapshot)
            ):
                self._inline_retention_identities.pop(key, None)

    def _binding_can_be_retained(self, key: _OverlayKey) -> bool:
        bound = self._bound_overlays.get(key)
        if bound is None or bound.presentation not in {
            _PRESENTATION_OVERLAY,
            _PRESENTATION_RETAINED_INLINE,
        }:
            return False
        if bound.widget is None or sip.isdeleted(bound.widget):
            return False
        if key in self._detached_windows or self._content_fullscreen_key() == key:
            return False
        if key[0] != self._active_workspace_id():
            return False
        current = self._snapshot_for_key(key)
        return bool(
            current is not None
            and current.phase == "open"
            and current.session_id == bound.snapshot.session_id
            and current.backend_id == bound.snapshot.backend_id
            and current.transport_revision == bound.snapshot.transport_revision
            and self._inline_retention_identity_matches(key, current)
        )

    def _cached_preview_available(self, key: _OverlayKey) -> bool:
        provider = self._preview_cache_provider
        return bool(provider is not None and provider.preview_source(key[0], key[1]))

    def _retain_inline_binding(self, key: _OverlayKey) -> bool:
        if not self._binding_can_be_retained(key):
            return False
        bound = self._bound_overlays.get(key)
        if bound is None:
            return False
        if bound.presentation == _PRESENTATION_RETAINED_INLINE:
            current = self._snapshot_for_key(key)
            if current is not None:
                bound.snapshot = current
            self._retained_inline_key = key
            return True

        retained_key = self._retained_inline_key
        if retained_key is not None and retained_key != key:
            self._release_binding(retained_key, reason="viewer_replaced")
        widget = self._current_widget_for_bound_overlay(key, bound)
        if not isinstance(widget, QWidget):
            return False
        current = self._snapshot_for_key(key)
        if current is not None:
            bound.snapshot = current
        widget.hide()
        if bound.container is not None:
            bound.container.hide()
        bound.presentation = _PRESENTATION_RETAINED_INLINE
        bound.widget = widget
        self._retained_inline_key = key
        self._bump_viewer_overlay_revision()
        return True

    def _presentation_target_for_key(self, key: _OverlayKey) -> str:
        if self._content_fullscreen_key() == key:
            return _PRESENTATION_OVERLAY
        if key in self._detached_windows:
            return _PRESENTATION_DETACHED
        return _PRESENTATION_OVERLAY

    @staticmethod
    def _snapshot_ready_for_live_widget(snapshot: _ViewerHostSessionSnapshot) -> bool:
        return (
            snapshot.phase == "open"
            and snapshot.live_mode == "full"
            and (snapshot.live_open_status == "ready" or snapshot.cache_state == "live_ready")
        )

    def _retarget_overlay_bindings_before_overlay_reconcile(
        self,
        desired_overlays: Mapping[_OverlayKey, tuple[_ViewerHostSessionSnapshot, ViewerWidgetBinder]],
    ) -> list[str]:
        errors: list[str] = []
        overlay_manager = self._overlay_manager
        if overlay_manager is None:
            return errors
        for key, (snapshot, binder) in desired_overlays.items():
            bound = self._bound_overlays.get(key)
            if bound is not None and bound.presentation not in {
                _PRESENTATION_OVERLAY,
                _PRESENTATION_RETAINED_INLINE,
            }:
                continue
            if self._presentation_target_for_key(key) != _PRESENTATION_DETACHED:
                continue
            active_snapshot = bound.snapshot if bound is not None else snapshot
            active_binder = bound.binder if bound is not None else binder
            widget = (bound.widget if bound is not None else None) or overlay_manager.overlay_widget(
                active_snapshot.node_id,
                workspace_id=active_snapshot.workspace_id,
            )
            if not isinstance(widget, QWidget):
                continue
            window = self._detached_windows.get(key)
            if window is None:
                continue
            window.prepare_destination()
            if window.widget is not None and window.widget is not widget:
                if not self._prepare_widget_for_reparent(active_binder, window.widget):
                    continue
            if widget.parent() is not window.container:
                if not self._prepare_widget_for_reparent(active_binder, widget):
                    continue
            if overlay_manager.overlay_widget(
                active_snapshot.node_id,
                workspace_id=active_snapshot.workspace_id,
            ) is widget:
                take = getattr(overlay_manager, "take_overlay_widget", None)
                if callable(take):
                    taken = take(
                        active_snapshot.node_id,
                        workspace_id=active_snapshot.workspace_id,
                    )
                    if isinstance(taken, QWidget):
                        widget = taken
                else:
                    overlay_manager.detach_overlay_widget(
                        active_snapshot.node_id,
                        workspace_id=active_snapshot.workspace_id,
                    )
            window.attach_widget(widget)
            if bound is None:
                continue
            refresh_result = self._refresh_widget_after_presentation_attach(active_binder, widget)
            if refresh_result is None:
                continue
            if not refresh_result:
                refresh_error = self._last_error or "Viewer could not refresh after attachment."
                self._bound_overlays.pop(key, None)
                self._release_widget(
                    snapshot=active_snapshot,
                    binder=active_binder,
                    container=window.container,
                    widget=widget,
                    presentation=_PRESENTATION_DETACHED,
                    reason="attach_refresh_error",
                )
                self._set_last_error(refresh_error)
                errors.append(refresh_error)
                continue
            bound.presentation = _PRESENTATION_DETACHED
            bound.container = window.container
            bound.widget = widget
            if self._retained_inline_key == key:
                self._retained_inline_key = None
        return errors

    def _container_and_current_widget(
        self,
        key: _OverlayKey,
        *,
        snapshot: _ViewerHostSessionSnapshot,
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
        bound = self._bound_overlays.get(key)
        retained_widget = (
            bound.widget
            if bound is not None and bound.presentation == _PRESENTATION_RETAINED_INLINE
            else None
        )
        return (
            overlay_manager.overlay_container(snapshot.node_id, workspace_id=snapshot.workspace_id),
            retained_widget
            or overlay_manager.overlay_widget(snapshot.node_id, workspace_id=snapshot.workspace_id),
        )

    def _attach_widget_to_presentation(
        self,
        key: _OverlayKey,
        *,
        snapshot: _ViewerHostSessionSnapshot,
        binder: ViewerWidgetBinder,
        widget: QWidget,
        presentation: str,
        already_prepared: bool = False,
    ) -> bool:
        window = self._detached_windows.get(key)
        prepared_widget = bool(already_prepared)
        if presentation == _PRESENTATION_DETACHED:
            if window is not None:
                window.prepare_destination()
                if window.widget is not None and window.widget is not widget:
                    if not self._prepare_widget_for_reparent(binder, window.widget):
                        return False
                if widget.parent() is not window.container:
                    if not prepared_widget and not self._prepare_widget_for_reparent(
                        binder,
                        widget,
                    ):
                        return False
                window.attach_widget(widget)
            return True
        if window is not None and window.widget is widget:
            if not prepared_widget and not self._prepare_widget_for_reparent(binder, widget):
                return False
            prepared_widget = True
            window.detach_widget(widget)
            window.hide()
        overlay_manager = self._overlay_manager
        if overlay_manager is not None:
            destination = overlay_manager.overlay_container(
                snapshot.node_id,
                workspace_id=snapshot.workspace_id,
            )
            if widget.parent() is not destination:
                if not prepared_widget and not self._prepare_widget_for_reparent(binder, widget):
                    return False
            overlay_manager.attach_overlay_widget(
                snapshot.node_id,
                widget,
                workspace_id=snapshot.workspace_id,
            )
            self._sync_overlay_manager_now()
        return True

    def _show_bound_widget(self, key: _OverlayKey, bound: _BoundOverlay) -> None:
        widget = bound.widget
        if widget is None:
            return
        self._attach_widget_to_presentation(
            key,
            snapshot=bound.snapshot,
            binder=bound.binder,
            widget=widget,
            presentation=bound.presentation,
        )

    def _prepare_widget_for_reparent(
        self,
        binder: ViewerWidgetBinder,
        widget: QWidget,
    ) -> bool:
        prepare = getattr(binder, "prepare_for_reparent", None)
        if not callable(prepare):
            return True
        try:
            prepare(widget)
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return False
        return True

    def _refresh_widget_after_presentation_attach(
        self,
        binder: ViewerWidgetBinder,
        widget: QWidget,
    ) -> bool | None:
        refresh = getattr(binder, "refresh_after_attach", None)
        try:
            if callable(refresh):
                refresh_result = refresh(widget)
                if refresh_result is False:
                    self._set_last_error("Viewer could not refresh after attachment.")
                    return False
            else:
                widget.updateGeometry()
                widget.update()
                render = getattr(widget, "render", None)
                if callable(render):
                    render()
        except ViewerWidgetNoBind as exc:
            if bool(getattr(exc, "retry_when_ready", False)):
                return None
            self._set_last_error(str(exc))
            return False
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            return False
        return True

    def _sync_overlay_manager_now(self) -> None:
        sync = getattr(self._overlay_manager, "sync", None) if self._overlay_manager is not None else None
        if callable(sync):
            try:
                sync()
            except Exception as exc:  # noqa: BLE001
                self._set_last_error(str(exc))

    def _sync_fullscreen_shortcut_filter(self) -> None:
        desired: set[QWidget] = set()
        if not self._shutdown:
            for key in self._controlled_presentation_keys():
                bound = self._bound_overlays.get(key)
                if bound is None:
                    continue
                widget = self._current_widget_for_bound_overlay(key, bound)
                if isinstance(widget, QWidget):
                    desired.add(widget)
        for previous in self._shortcut_filtered_widgets - desired:
            try:
                previous.removeEventFilter(self._fullscreen_shortcut_filter)
            except RuntimeError:
                pass
        for widget in desired - self._shortcut_filtered_widgets:
            widget.installEventFilter(self._fullscreen_shortcut_filter)
        self._shortcut_filtered_widgets = desired

    def _handle_presentation_shortcut(self, watched: QObject, key: int, modifiers: Any) -> bool:
        for presentation_key in self._controlled_presentation_keys():
            bound = self._bound_overlays.get(presentation_key)
            if bound is not None and self._current_widget_for_bound_overlay(presentation_key, bound) is watched:
                return self._handle_shortcut_for_key(presentation_key, key, modifiers)
        return False

    def _handle_fullscreen_shortcut(self, key: int, modifiers: Any) -> bool:
        presentation_key = self._active_controlled_presentation_key()
        return (
            self._handle_shortcut_for_key(presentation_key, key, modifiers)
            if presentation_key is not None
            else False
        )

    def _handle_shortcut_for_key(
        self,
        presentation_key: _OverlayKey,
        key: int,
        modifiers: Any,
    ) -> bool:
        if self._shutdown:
            return False
        plain_modifiers = (
            Qt.KeyboardModifier.NoModifier,
            Qt.KeyboardModifier.KeypadModifier,
        )
        if modifiers not in plain_modifiers:
            return False
        node_id = presentation_key[1]
        bridge = self._viewer_session_bridge
        if key == Qt.Key.Key_Space and bridge is not None:
            state = _mapping(bridge.session_state(node_id))
            if _string(state.get("playback_state", "paused")) == "playing":
                return bool(bridge.pause(node_id))
            return bool(bridge.play(node_id))
        if key == Qt.Key.Key_Left and bridge is not None:
            step_back = getattr(bridge, "step_back", None)
            return bool(step_back(node_id)) if callable(step_back) else False
        if key == Qt.Key.Key_Right and bridge is not None:
            return bool(bridge.step(node_id))
        if key == Qt.Key.Key_Home:
            return self.reset_overlay_camera(node_id)
        if key == Qt.Key.Key_R:
            return self.apply_standard_view(node_id, "iso")
        if key in {Qt.Key.Key_PageUp, Qt.Key.Key_PageDown}:
            cycle = self._cycle_camera_bookmark
            if callable(cycle):
                return bool(cycle(node_id, -1 if key == Qt.Key.Key_PageUp else 1))
        return False

    def _active_controlled_presentation_key(self) -> _OverlayKey | None:
        keys = self._controlled_presentation_keys()
        return keys[0] if keys else None

    def _controlled_presentation_keys(self) -> tuple[_OverlayKey, ...]:
        fullscreen_key = self._content_fullscreen_key()
        if fullscreen_key is not None:
            return (fullscreen_key,)
        return tuple(key for key, window in self._detached_windows.items() if window.isVisible())

    def _content_fullscreen_overlay_spec(self) -> EmbeddedViewerOverlaySpec | None:
        return self._presentation_service.content_fullscreen_overlay_spec()

    def _content_fullscreen_key(self) -> _OverlayKey | None:
        overlay = self._content_fullscreen_overlay_spec()
        if overlay is None:
            return None
        workspace_id = _string(getattr(overlay, "workspace_id", ""))
        node_id = _string(getattr(overlay, "node_id", ""))
        if not workspace_id or not node_id:
            return None
        return workspace_id, node_id

    def _set_viewer_content_fullscreen_target(
        self,
        overlay_manager: EmbeddedViewerOverlayManager,
        overlay: EmbeddedViewerOverlaySpec | None,
        *,
        force_clear: bool = False,
    ) -> None:
        if overlay is not None:
            overlay_manager.set_content_fullscreen_target(overlay)
            self._owns_content_fullscreen_target = True
            return
        if force_clear or self._owns_content_fullscreen_target:
            overlay_manager.set_content_fullscreen_target(None)
        self._owns_content_fullscreen_target = False

    @staticmethod
    def _set_active_viewer_overlays(
        overlay_manager: EmbeddedViewerOverlayManager,
        overlays,
    ) -> None:  # noqa: ANN001
        overlay_manager.set_active_overlays_for_owner(VIEWER_SESSION_OVERLAY_OWNER, tuple(overlays))

    def _release_all_bindings(self, *, reason: str) -> None:
        for key in list(self._bound_overlays):
            self._release_binding(key, reason=reason)
        self._retained_inline_key = None
        self._inline_retention_identities.clear()

    def _release_binding(self, key: _OverlayKey, *, reason: str) -> bool:
        bound = self._bound_overlays.get(key)
        if bound is None:
            return True
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
        if not self._release_widget(
            snapshot=bound.snapshot,
            binder=bound.binder,
            container=container,
            widget=widget,
            reason=reason,
            presentation=bound.presentation,
        ):
            return False
        if self._bound_overlays.get(key) is bound:
            self._bound_overlays.pop(key, None)
        self._inline_retention_identities.pop(key, None)
        if self._retained_inline_key == key:
            self._retained_inline_key = None
        self._bump_viewer_overlay_revision()
        return True

    def _release_widget(
        self,
        *,
        snapshot: _ViewerHostSessionSnapshot,
        binder: ViewerWidgetBinder,
        container,
        widget,
        reason: str,
        presentation: str = _PRESENTATION_OVERLAY,
    ) -> bool:  # noqa: ANN001
        overlay_manager = self._overlay_manager
        if widget is None:
            return True
        if presentation == _PRESENTATION_RETAINED_INLINE and not widget.updatesEnabled():
            widget.setUpdatesEnabled(True)
        if presentation == _PRESENTATION_DETACHED:
            window = self._detached_windows.get(snapshot.overlay_key)
            if (
                window is not None
                and window.widget is widget
                and not self._prepare_widget_for_reparent(binder, widget)
            ):
                return False
        try:
            binder.release_widget(
                snapshot.release_request(
                    container=container,
                    widget=widget,
                    reason=reason,
                )
            )
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
        finally:
            if presentation == _PRESENTATION_DETACHED:
                window = self._detached_windows.get(snapshot.overlay_key)
                if window is not None and window.widget is widget:
                    window.detach_widget(widget)
                EmbeddedViewerOverlayManager._teardown_widget(widget)
            elif overlay_manager is not None and overlay_manager.overlay_widget(snapshot.node_id, workspace_id=snapshot.workspace_id) is widget:
                if container is not None:
                    try:
                        container.hide()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    widget.hide()
                except Exception:  # noqa: BLE001
                    pass
            if (
                presentation in {_PRESENTATION_OVERLAY, _PRESENTATION_RETAINED_INLINE}
                and overlay_manager is not None
                and overlay_manager.overlay_widget(
                    snapshot.node_id,
                    workspace_id=snapshot.workspace_id,
                )
                is widget
            ):
                overlay_manager.detach_overlay_widget(
                    snapshot.node_id,
                    workspace_id=snapshot.workspace_id,
                )
        return True

    def _snapshot_from_projected_state(
        self,
        projected_state: Mapping[str, Any],
    ) -> _ViewerHostSessionSnapshot | None:
        return self._presentation_service.snapshot_from_projected_state(projected_state)

    def _should_host_overlay(self, projected_state: Mapping[str, Any]) -> bool:
        return self._presentation_service.should_host_overlay(projected_state)

    def _binding_signature(self, snapshot: _ViewerHostSessionSnapshot) -> tuple[Any, ...]:
        return self._presentation_service.binding_signature(snapshot)

    def _active_workspace_id(self) -> str:
        bridge = self._viewer_session_bridge
        if bridge is not None:
            workspace_id = _string(getattr(bridge, "active_workspace_id", ""))
            if workspace_id:
                return workspace_id
        return ""

    def _key_for_node_id(self, node_id: str) -> _OverlayKey | None:
        workspace_id = self._active_workspace_id()
        normalized_node_id = _string(node_id)
        if not workspace_id or not normalized_node_id:
            return None
        return workspace_id, normalized_node_id

    def _snapshot_for_key(self, key: _OverlayKey) -> _ViewerHostSessionSnapshot | None:
        bridge = self._viewer_session_bridge
        if bridge is None:
            return None
        for item in bridge.sessions_model:
            projected_state = _mapping(item)
            if _string(projected_state.get("workspace_id")) != key[0]:
                continue
            if _string(projected_state.get("node_id")) != key[1]:
                continue
            return self._presentation_service.snapshot_from_projected_state(projected_state)
        return None

    def _capture_cached_live_state_for_key(self, key: _OverlayKey) -> None:
        bound = self._bound_overlays.get(key)
        if bound is None:
            return
        current_snapshot = self._snapshot_for_key(key)
        if current_snapshot is None:
            self._clear_cached_viewer_state(key)
            return
        camera_signature = self._camera_relevant_signature(current_snapshot)
        binding_signature = self._binding_signature(current_snapshot)
        signature = self._preview_cache_signature(current_snapshot)
        if binding_signature != bound.signature:
            # The camera is independent of visual options: keep it as long as
            # the session still shows the same transported geometry.
            if camera_signature == self._camera_relevant_signature(bound.snapshot):
                self._capture_cached_view_state_for_binding(key, bound, camera_signature)
            else:
                self._viewer_view_states.pop(key, None)
            if signature != self._preview_cache_signature(bound.snapshot):
                self._clear_cached_preview(key)
                return
        else:
            self._capture_cached_view_state_for_binding(key, bound, camera_signature)
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

    def _capture_cached_view_state_for_binding(
        self,
        key: _OverlayKey,
        bound: _BoundOverlay,
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
        self._viewer_view_states[key] = (signature, stored_state)

    def _restore_cached_view_state_for_binding(
        self,
        key: _OverlayKey,
        binder: ViewerWidgetBinder,
        widget: QWidget,
        signature: tuple[Any, ...],
    ) -> None:
        cached = self._viewer_view_states.get(key)
        if cached is None:
            return
        cached_signature, state = cached
        if cached_signature != signature:
            self._clear_cached_viewer_state(key)
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
        bound: _BoundOverlay,
    ) -> QWidget | None:
        if bound.presentation == _PRESENTATION_RETAINED_INLINE:
            return bound.widget if isinstance(bound.widget, QWidget) else None
        if bound.presentation == _PRESENTATION_DETACHED:
            window = self._detached_windows.get(key)
            widget = window.widget if window is not None else bound.widget
            return widget if isinstance(widget, QWidget) else None
        if self._overlay_manager is not None:
            widget = self._overlay_manager.overlay_widget(bound.snapshot.node_id, workspace_id=bound.snapshot.workspace_id)
            if isinstance(widget, QWidget):
                return widget
        return bound.widget if isinstance(bound.widget, QWidget) else None

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

    def _clear_cached_viewer_state(self, key: _OverlayKey) -> None:
        self._viewer_view_states.pop(key, None)
        self._clear_cached_preview(key)

    def _migrate_cached_viewer_state(
        self,
        key: _OverlayKey,
        snapshot: _ViewerHostSessionSnapshot,
    ) -> None:
        cached = self._viewer_view_states.get(key)
        if cached is not None and cached[0] != self._camera_relevant_signature(snapshot):
            self._viewer_view_states.pop(key, None)
        self._clear_cached_preview(key)

    def _clear_all_cached_previews(self) -> None:
        provider = self._preview_cache_provider
        changed = provider.clear_all() if provider is not None else False
        self._viewer_render_signatures.clear()
        self._viewer_view_states.clear()
        if changed:
            self._bump_preview_cache_revision()

    def _sync_preview_cache_signatures(self) -> None:
        bridge = self._viewer_session_bridge
        if bridge is None:
            self._clear_all_cached_previews()
            return
        current: dict[_OverlayKey, tuple[Any, ...]] = {}
        for item in bridge.sessions_model:
            snapshot = self._presentation_service.snapshot_from_projected_state(_mapping(item))
            if snapshot is None:
                continue
            key = snapshot.overlay_key
            signature = self._preview_cache_signature(snapshot)
            current[key] = signature
            previous_signature = self._viewer_render_signatures.get(key)
            cached_signature = (
                self._preview_cache_provider.preview_signature(key[0], key[1])
                if self._preview_cache_provider is not None
                else None
            )
            if (
                (previous_signature is not None and previous_signature != signature)
                or (cached_signature is not None and cached_signature != signature)
            ):
                self._migrate_cached_viewer_state(key, snapshot)
        for key in set(self._viewer_render_signatures) - set(current):
            self._clear_cached_viewer_state(key)
        self._viewer_render_signatures = current

    def _bump_preview_cache_revision(self) -> None:
        self._preview_cache_revision += 1
        self.preview_cache_changed.emit()

    def _bump_viewer_overlay_revision(self) -> None:
        self._viewer_overlay_revision += 1

    @staticmethod
    def _preview_cache_signature(snapshot: _ViewerHostSessionSnapshot) -> tuple[Any, ...]:
        return (
            snapshot.session_id,
            snapshot.backend_id,
            snapshot.transport_revision,
            _freeze_value(snapshot.transport),
            _freeze_value(snapshot.data_refs),
            _freeze_value(snapshot.playback_state),
            _freeze_value(_cache_relevant_options(snapshot.options)),
        )

    @staticmethod
    def _camera_relevant_signature(snapshot: _ViewerHostSessionSnapshot) -> tuple[Any, ...]:
        # Camera state survives option and playback changes; it resets only
        # when the transported geometry itself changes.
        return (
            snapshot.session_id,
            snapshot.backend_id,
            snapshot.transport_revision,
            _freeze_value(snapshot.transport),
            _freeze_value(snapshot.data_refs),
        )

    def _set_last_error(self, value: str) -> None:
        normalized = _string(value)
        if normalized == self._last_error:
            return
        self._last_error = normalized
        self.last_error_changed.emit()


__all__ = ["ViewerHostService"]
