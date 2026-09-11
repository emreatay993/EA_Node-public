# Purpose: Render neutral engineering scene transports in a reusable PyVista Qt widget.
# Map: feature_routes/viewer_session_overlay_fullscreen.md
# Tests: tests/test_engineering_viewer_widget_binder.py
# Landmarks: EngineeringViewerWidgetBinder, _populate_interactor, _mesh_kwargs, selection isolate, orientation aids
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QWidget

from ea_node_editor.app_preferences import (
    AppPreferencesStore,
    engineering_viewer_tangent_selection_angle,
)
from ea_node_editor.common.scene_protocol import normalize_scene_styles
from ea_node_editor.execution.viewer_backend_engineering import (
    ENGINEERING_VIEWER_BACKEND_ID,
    ENGINEERING_VIEWER_SHARED_MEMORY_ASSET_SCHEMA,
    ENGINEERING_VIEWER_TRANSPORT_KIND,
    ENGINEERING_VIEWER_TRANSPORT_SCHEMA,
)
from ea_node_editor.execution.viewer_camera_state import apply_camera_state, extract_camera_state
from ea_node_editor.execution.viewer_pyvista_style import viewer_canvas_style
from ea_node_editor.ui_qml.viewer_widget_binder import (
    ViewerWidgetBindRequest,
    ViewerWidgetNoBind,
    ViewerWidgetReleaseRequest,
)

_NATIVE_WINDOW_OVERLAY_PROPERTY = "ea.nativeWindowOverlay"
_VIEWER_BACKGROUND_OPTION = "viewer_background"
_SHOW_MESH_EDGES_OPTION = "show_mesh_edges"
_SHOW_ATTRIBUTE_COLORS_OPTION = "show_attribute_colors"
_SHOW_ORIENTATION_TRIAD_OPTION = "show_orientation_triad"
_SHOW_VIEW_CUBE_OPTION = "show_view_cube"
_SHOW_WORLD_AXES_OPTION = "show_world_axes"
_MAX_SHARED_MEMORY_ASSET_COUNT = 32
_MAX_SHARED_MEMORY_SEGMENT_BYTES = 512 * 1024 * 1024
_MAX_SHARED_MEMORY_TOTAL_BYTES = 1024 * 1024 * 1024
_MAX_SHARED_MEMORY_NAME_BYTES = 255
_MAX_SHARED_MEMORY_DESCRIPTOR_BYTES = 64 * 1024
_SHARED_MEMORY_DESCRIPTOR_KEYS = frozenset(
    {
        "schema",
        "version",
        "storage",
        "name",
        "byte_length",
        "sha256",
        "format",
        "role",
        "content",
        "attribute_colors",
        "entity_arrays",
    }
)
_SELECTION_FILTERS = {
    "cad_vertex",
    "cad_edge",
    "cad_face",
    "cad_body",
    "fe_node",
    "fe_element_face",
    "fe_element",
}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = _string(value).casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    return default


@dataclass(slots=True)
class _EngineeringWidgetState:
    backend_id: str
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    transport_revision: int = 0
    layer_count: int = 0
    actors: dict[str, Any] = field(default_factory=dict)
    topology_actors: dict[str, Any] = field(default_factory=dict)
    layers: dict[str, dict[str, Any]] = field(default_factory=dict)
    layer_visibility: dict[str, bool] = field(default_factory=dict)
    current_options: dict[str, Any] = field(default_factory=dict)
    scene_fingerprint: str = ""
    selection_filter: str = "cad_body"
    selected_entities: list[dict[str, str]] = field(default_factory=list)
    selection_highlight_actor: Any | None = None
    selection_isolate_actor: Any | None = None
    selection_source_actors: dict[str, dict[str, Any]] = field(default_factory=dict)
    selection_isolated: bool = False
    selection_observers: list[tuple[Any, Any]] = field(default_factory=list)
    selection_press_position: tuple[int, int] | None = None
    selection_dragged: bool = False
    selection_camera_interacting: bool = False
    selection_camera_interaction_revision: int = 0
    selection_press_camera_revision: int = 0
    selection_last_click_position: tuple[int, int] | None = None
    selection_last_click_time: float = 0.0
    view_cube_widget: Any | None = None
    orientation_triad_widget: Any | None = None
    orientation_triad_actor: Any | None = None
    triad_drag_observers: list[tuple[Any, Any]] = field(default_factory=list)
    triad_drag_active: bool = False
    triad_drag_last_position: tuple[int, int] | None = None
    triad_drag_style: Any | None = None
    triad_drag_style_was_enabled: bool = True
    world_axes_actors: list[Any] = field(default_factory=list)
    hidden_line_enabled: bool = False
    interaction_observers: list[tuple[Any, Any]] = field(default_factory=list)
    lod_restore_timer: QTimer | None = None
    attach_refresh_pending: bool = False
    attach_refresh_deferred_once: bool = False
    presentation_attach_required: bool = False
    initial_attach_pending: bool = False
    pending_camera_state: dict[str, Any] = field(default_factory=dict)
    initial_camera_reset_pending: bool = False


_LoadKey = tuple[str, str, str, int]


@dataclass(slots=True)
class _EngineeringLoadResult:
    layers: list[dict[str, Any]] = field(default_factory=list)
    error: BaseException | None = None


class _EngineeringViewerLoadPending(ViewerWidgetNoBind):
    retry_when_ready = True


class _EngineeringViewerAttachPending(ViewerWidgetNoBind):
    retry_when_ready = True


class EngineeringViewerWidgetBinder(QObject):
    """Bind neutral CAD/FE scene files to one reusable PyVista interactor."""

    backend_id = ENGINEERING_VIEWER_BACKEND_ID
    load_ready = pyqtSignal(str, str, str, int)
    selection_changed = pyqtSignal(str, str)

    def __init__(
        self,
        *,
        interactor_factory: Callable[[QWidget | None], QWidget] | None = None,
        dataset_loader: Callable[[str], Any] | None = None,
        picker_factory: Callable[[str], Any] | None = None,
        tangent_selection_angle_provider: Callable[[], float] | None = None,
        background_loading: bool = True,
    ) -> None:
        super().__init__()
        self._interactor_factory = interactor_factory or self._create_interactor
        self._dataset_loader = dataset_loader or self._load_dataset
        self._picker_factory = picker_factory or self._create_picker
        self._preferences_store = AppPreferencesStore()
        self._tangent_selection_angle_provider = (
            tangent_selection_angle_provider
            or self._stored_tangent_selection_angle
        )
        self._background_loading = bool(background_loading)
        self._widget_state: WeakKeyDictionary[QWidget, _EngineeringWidgetState] = WeakKeyDictionary()
        self._load_lock = threading.Lock()
        self._load_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="corex-viewer-load")
        self._pending_loads: dict[_LoadKey, Future[list[dict[str, Any]]]] = {}
        self._loaded_results: dict[_LoadKey, _EngineeringLoadResult] = {}
        self._active_loads: dict[tuple[str, str], _LoadKey] = {}
        self._shutdown = False

    def bind_widget(self, request: ViewerWidgetBindRequest) -> QWidget:
        if self._shutdown:
            raise ViewerWidgetNoBind("Model viewer binder is shut down.")
        current = request.current_widget
        state = self._widget_state.get(current) if isinstance(current, QWidget) else None
        if (
            state is not None
            and state.session_id == request.session_id
            and state.transport_revision == request.transport_revision
            and state.actors
        ):
            self._update_existing_actors(current, state=state, request=request)
            return current
        descriptors = self._layer_descriptors(request)
        if self._background_loading:
            layers = self._loaded_layers(request)
            if layers is None:
                self._start_background_load(request, descriptors)
                raise _EngineeringViewerLoadPending("Model viewer scene is loading.")
        else:
            layers = self._load_layer_datasets(descriptors)
        reusable_current = self._is_reusable_interactor(request.current_widget)
        interactor = self._resolve_interactor(
            container=request.container,
            current_widget=request.current_widget,
        )
        self._populate_interactor(
            interactor,
            request=request,
            layers=layers,
            defer_until_attach=not reusable_current and request.container is not None,
        )
        return interactor

    def release_widget(self, request: ViewerWidgetReleaseRequest) -> None:
        if request.reason != "load_pending":
            self._cancel_loads_for_scope(request.workspace_id, request.node_id)
        widget = request.widget
        if not self._is_reusable_interactor(widget):
            return
        state = self._widget_state.get(widget)
        if state is not None:
            self._detach_interaction_lod(state)
            self._detach_selection_picking(state)
            self._remove_selection_highlight(widget, state)
            self._remove_selection_isolate(widget, state)
            self._remove_orientation_aids(widget, state)
            self._sync_hidden_line_removal(widget, state, enabled=False)
            state.actors.clear()
            state.topology_actors.clear()
            state.layers.clear()
            state.layer_visibility.clear()
            state.selection_source_actors.clear()
            state.selected_entities.clear()
        clear = getattr(widget, "clear", None)
        if callable(clear):
            clear()
        render = getattr(widget, "render", None)
        if callable(render):
            render()
        self._widget_state[widget] = _EngineeringWidgetState(backend_id=self.backend_id)

    def cancel_all_loads(self) -> None:
        with self._load_lock:
            futures = list(self._pending_loads.values())
            self._pending_loads.clear()
            self._loaded_results.clear()
            self._active_loads.clear()
        for future in futures:
            future.cancel()

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        self.cancel_all_loads()
        self._load_executor.shutdown(wait=False, cancel_futures=True)

    def prepare_for_reparent(self, widget: QWidget | None) -> None:
        if not isinstance(widget, QWidget):
            return
        state = self._widget_state.get(widget)
        if state is None:
            return
        self._detach_selection_picking(state)
        self._detach_interaction_lod(state)
        self._remove_view_cube(widget, state)
        self._remove_orientation_triad(widget, state)
        state.presentation_attach_required = True

    def refresh_after_attach(self, widget: QWidget | None) -> bool:
        if not isinstance(widget, QWidget):
            return False
        state = self._widget_state.get(widget)
        if state is None:
            return False
        if not self._native_interactor_ready(widget):
            if state.attach_refresh_pending:
                raise _EngineeringViewerAttachPending(
                    "Model viewer native attachment is pending."
                )
            if state.attach_refresh_deferred_once:
                raise RuntimeError(
                    "Model viewer native interactor was not ready after attachment."
                )
            state.attach_refresh_pending = True
            expected_state = state

            def retry() -> None:
                current = self._widget_state.get(widget)
                if current is not expected_state or not current.attach_refresh_pending:
                    return
                current.attach_refresh_pending = False
                current.attach_refresh_deferred_once = True
                self.load_ready.emit(
                    current.workspace_id,
                    current.node_id,
                    current.session_id,
                    current.transport_revision,
                )

            QTimer.singleShot(0, retry)
            raise _EngineeringViewerAttachPending(
                "Model viewer native attachment is pending."
            )
        state.attach_refresh_pending = False
        state.attach_refresh_deferred_once = False
        self._refresh_after_attach_now(widget, state)
        state.presentation_attach_required = False
        return True

    def _refresh_after_attach_now(
        self,
        widget: QWidget,
        state: _EngineeringWidgetState,
    ) -> None:
        if state.initial_attach_pending:
            if state.pending_camera_state:
                apply_camera_state(widget, state.pending_camera_state)
            elif state.initial_camera_reset_pending:
                reset_camera = getattr(getattr(widget, "renderer", None), "reset_camera", None)
                if not callable(reset_camera):
                    reset_camera = getattr(widget, "reset_camera", None)
                if callable(reset_camera):
                    try:
                        reset_camera(render=False)
                    except TypeError:
                        reset_camera()
            reset_clipping = getattr(widget, "reset_camera_clipping_range", None)
            if callable(reset_clipping):
                reset_clipping()
            state.initial_attach_pending = False
            state.pending_camera_state.clear()
            state.initial_camera_reset_pending = False
        self._sync_orientation_aids(widget, state, state.current_options)
        if not state.selection_observers:
            self._install_selection_picking(widget, state)
        if not state.interaction_observers:
            self._install_interaction_lod(widget, state)
        widget.updateGeometry()
        widget.update()
        render = getattr(widget, "render", None)
        if callable(render):
            render()

    @staticmethod
    def _native_interactor_ready(widget: QWidget) -> bool:
        target = getattr(widget, "iren", None) or getattr(widget, "interactor", None)
        if target is None:
            return False
        raw = getattr(target, "interactor", target)
        get_window = getattr(raw, "GetRenderWindow", None)
        return not callable(get_window) or get_window() is not None

    def capture_camera_state(self, widget: QWidget | None) -> dict[str, Any]:
        return extract_camera_state(widget) if self._is_reusable_interactor(widget) else {}

    def capture_view_state(self, widget: QWidget | None) -> dict[str, Any]:
        return self.capture_camera_state(widget)

    def restore_view_state(self, widget: QWidget | None, state: Mapping[str, Any]) -> bool:
        if not self._is_reusable_interactor(widget):
            return False
        apply_camera_state(widget, _mapping(state))
        reset_clipping = getattr(widget, "reset_camera_clipping_range", None)
        if callable(reset_clipping):
            reset_clipping()
        render = getattr(widget, "render", None)
        if callable(render):
            render()
        return True

    def render_stats(self, widget: QWidget | None) -> dict[str, Any]:
        if not isinstance(widget, QWidget):
            return {}
        state = self._widget_state.get(widget)
        if state is None:
            return {}
        return {
            "layer_count": state.layer_count,
            "dataset_count": sum(
                1 + (1 if layer.get("interaction_dataset") is not None else 0)
                for layer in state.layers.values()
                if layer.get("dataset") is not None
            ),
            "selected_entity_count": len(state.selected_entities),
            "selection_isolated": state.selection_isolated,
            "display_state": {
                **state.current_options,
                "layer_visibility": dict(state.layer_visibility),
            },
            "layers": [
                {
                    "id": name,
                    "name": _string(state.layers.get(name, {}).get("name")),
                    "visible": state.layer_visibility.get(name, True),
                    "topological_edges": name in state.topology_actors,
                }
                for name in state.actors
            ],
        }

    def set_layer_visibility(self, widget: QWidget | None, name: str, visible: bool) -> bool:
        if not isinstance(widget, QWidget):
            return False
        state = self._widget_state.get(widget)
        normalized_name = str(name).strip()
        if state is None or normalized_name not in state.actors:
            return False
        state.layer_visibility[normalized_name] = bool(visible)
        self._sync_actor_visibility(state)
        render = getattr(widget, "render", None)
        if callable(render):
            render()
        return True

    def isolate_layer(self, widget: QWidget | None, name: str) -> bool:
        if not isinstance(widget, QWidget):
            return False
        state = self._widget_state.get(widget)
        normalized_name = str(name).strip()
        if state is None or normalized_name not in state.actors:
            return False
        for actor_name in state.actors:
            state.layer_visibility[actor_name] = actor_name == normalized_name
        self._sync_actor_visibility(state)
        render = getattr(widget, "render", None)
        if callable(render):
            render()
        return True

    def selection_snapshot(self, widget: QWidget | None) -> dict[str, Any]:
        if not isinstance(widget, QWidget):
            return {}
        state = self._widget_state.get(widget)
        if state is None:
            return {}
        return {
            "scene_fingerprint": state.scene_fingerprint,
            "entities": [dict(entity) for entity in state.selected_entities],
            "isolate_active": state.selection_isolated,
            "selection_filter": state.selection_filter,
        }

    def set_selection_filter(self, widget: QWidget | None, value: str) -> bool:
        if not isinstance(widget, QWidget):
            return False
        state = self._widget_state.get(widget)
        normalized = _string(value).casefold()
        if (
            state is None
            or normalized not in _SELECTION_FILTERS
            or not any(
                source["entity_kind"] == normalized
                for source in state.selection_source_actors.values()
            )
        ):
            return False
        if state.selection_filter == normalized:
            return True
        state.selection_filter = normalized
        state.selected_entities.clear()
        self._remove_selection_highlight(widget, state)
        if state.selection_isolated:
            state.selection_isolated = False
            self._remove_selection_isolate(widget, state)
            self._sync_actor_visibility(state)
        self._sync_selection_source_cues(state)
        self.selection_changed.emit(state.workspace_id, state.node_id)
        render = getattr(widget, "render", None)
        if callable(render):
            render()
        return True

    def activate_selection(
        self,
        widget: QWidget | None,
        entities: list[Any],
    ) -> bool:
        if not isinstance(widget, QWidget):
            return False
        state = self._widget_state.get(widget)
        if state is None:
            return False
        normalized: list[dict[str, str]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for value in entities:
            entity = _mapping(value)
            normalized_entity = {
                "layer_id": _string(entity.get("layer_id")),
                "source_fingerprint": _string(entity.get("source_fingerprint")).casefold(),
                "entity_kind": _string(entity.get("entity_kind")).casefold(),
                "entity_id": _string(entity.get("entity_id")),
            }
            identity = tuple(normalized_entity.values())
            if (
                not normalized_entity["layer_id"]
                or len(normalized_entity["source_fingerprint"]) != 64
                or normalized_entity["entity_kind"] not in _SELECTION_FILTERS
                or not normalized_entity["entity_id"]
                or identity in seen
            ):
                continue
            seen.add(identity)
            normalized.append(normalized_entity)
        if not normalized:
            return False
        entity_kinds = {entity["entity_kind"] for entity in normalized}
        if len(entity_kinds) != 1:
            return False
        state.selection_filter = normalized[0]["entity_kind"]
        self._sync_selection_source_cues(state)
        return self._set_selected_entities(widget, state, normalized)

    def fit_selection(self, widget: QWidget | None) -> bool:
        if not isinstance(widget, QWidget):
            return False
        state = self._widget_state.get(widget)
        reset_camera = getattr(widget, "reset_camera", None)
        if state is None or not callable(reset_camera):
            return False
        selected = self._selected_layer_datasets(state)
        bounds = self._combined_bounds(selected.values())
        if bounds is None:
            return False
        try:
            reset_camera(bounds=bounds, render=False)
        except TypeError:
            reset_camera(bounds=bounds)
        render = getattr(widget, "render", None)
        if callable(render):
            render()
        return True

    def toggle_selection_isolate(self, widget: QWidget | None, update: bool = False) -> bool:
        if not isinstance(widget, QWidget):
            return False
        state = self._widget_state.get(widget)
        if state is None:
            return False
        if state.selection_isolated and not bool(update):
            state.selection_isolated = False
            self._remove_selection_isolate(widget, state)
            self._sync_actor_visibility(state)
        elif not self._rebuild_selection_isolate(widget, state):
            return False
        render = getattr(widget, "render", None)
        if callable(render):
            render()
        return True

    def capture_preview_image(self, widget: QWidget | None) -> QImage | None:
        if not self._is_reusable_interactor(widget):
            return QImage()
        render = getattr(widget, "render", None)
        if callable(render):
            try:
                render()
            except Exception:  # noqa: BLE001
                return QImage()
        screenshot = getattr(widget, "screenshot", None)
        if not callable(screenshot):
            return QImage()
        try:
            return self._qimage_from_screenshot(screenshot(return_img=True))
        except Exception:  # noqa: BLE001
            return QImage()

    def apply_canvas_theme(self, widget: QWidget | None, options: Mapping[str, Any] | None = None) -> bool:
        if not isinstance(widget, QWidget):
            return False
        normalized_options = _mapping(options)
        self._apply_canvas_background(
            widget,
            _string(normalized_options.get(_VIEWER_BACKGROUND_OPTION)),
            flat=self._representation(normalized_options) == "wireframe_visible_edges",
        )
        render = getattr(widget, "render", None)
        if callable(render):
            render()
        return True

    def _layer_descriptors(self, request: ViewerWidgetBindRequest) -> list[dict[str, Any]]:
        if _string(request.live_open_status).casefold() != "ready":
            raise ViewerWidgetNoBind("Model viewer transport is not ready for live binding.")
        transport = _mapping(request.transport)
        if _string(transport.get("kind")) != ENGINEERING_VIEWER_TRANSPORT_KIND:
            raise ViewerWidgetNoBind("Model viewer scene transport is unavailable.")
        if _string(transport.get("schema")) != ENGINEERING_VIEWER_TRANSPORT_SCHEMA:
            raise ValueError("Model viewer scene transport schema is not supported.")
        if _string(transport.get("status")).casefold() == "blocked":
            raise ViewerWidgetNoBind("Model viewer scene transport is blocked.")

        layers = transport.get("layers")
        if not isinstance(layers, list) or not layers:
            raise ViewerWidgetNoBind("Model viewer scene layers are missing.")

        descriptors: list[dict[str, Any]] = []
        shared_memory_asset_count = 0
        shared_memory_total_bytes = 0
        layer_ids: set[str] = set()
        for raw_layer in layers:
            layer = _mapping(raw_layer)
            layer_id = _string(layer.get("id"))
            if not layer_id or layer_id in layer_ids:
                raise ValueError("Model viewer scene layer IDs must be nonempty and unique.")
            layer_ids.add(layer_id)
            display_asset_value = layer.get("display_asset")
            display_asset = (
                self._shared_memory_descriptor(display_asset_value)
                if display_asset_value is not None
                else {}
            )
            if display_asset:
                shared_memory_asset_count += 1
                shared_memory_total_bytes += int(display_asset["byte_length"])
                if (
                    shared_memory_asset_count > _MAX_SHARED_MEMORY_ASSET_COUNT
                    or shared_memory_total_bytes > _MAX_SHARED_MEMORY_TOTAL_BYTES
                ):
                    raise ValueError(
                        "Model viewer shared-memory asset descriptor is invalid."
                    )
            display_path_text = _string(layer.get("display_path"))
            display_path = Path(display_path_text) if display_path_text else None
            if not display_asset and (
                display_path is None or not display_path.is_file()
            ):
                raise ViewerWidgetNoBind(f"Model viewer display file is missing: {display_path}")
            interaction_path_value = layer.get("interaction_display_path")
            interaction_path_text = (
                _string(interaction_path_value)
                if interaction_path_value is not None and interaction_path_value != ""
                else ""
            )
            interaction_path = Path(interaction_path_text) if interaction_path_text else None
            if interaction_path is not None and not interaction_path.is_file():
                raise ViewerWidgetNoBind(
                    f"Model viewer interaction LOD file is missing: {interaction_path}"
                )
            geometry_assets = [
                _mapping(value)
                for value in layer.get("geometry_assets", ())
                if isinstance(value, Mapping)
            ]
            surface_asset = next(
                (
                    value
                    for value in geometry_assets
                    if _string(value.get("content")).casefold() in {"surface", "mesh"}
                    and _string(value.get("role")).casefold() in {"full", "display", ""}
                ),
                {},
            )
            topology = _mapping(layer.get("topological_edges"))
            if not topology:
                topology = next(
                    (
                        value
                        for value in geometry_assets
                        if _string(value.get("content")).casefold() == "topological_edges"
                    ),
                    {},
                )
            if not topology and _string(layer.get("topological_edge_path")):
                topology = {"display_path": _string(layer.get("topological_edge_path"))}
            topology_path_text = _string(
                topology.get("display_path", topology.get("path", ""))
            )
            topology_path = Path(topology_path_text) if topology_path_text else None
            if topology and topology_path is None:
                raise ViewerWidgetNoBind("Model viewer topological-edge asset has no path.")
            if topology_path is not None and not topology_path.is_file():
                raise ViewerWidgetNoBind(
                    f"Model viewer topological-edge file is missing: {topology_path}"
                )
            selection_assets: dict[str, dict[str, Any]] = {}
            source_kind = _string(layer.get("source_kind")).casefold()
            surface_arrays = _mapping(
                display_asset.get(
                    "entity_arrays",
                    surface_asset.get("entity_arrays"),
                )
            )
            if source_kind == "cad":
                if "face_index" in surface_arrays:
                    selection_assets["cad_face"] = {
                        **surface_asset,
                        "path": str(display_path) if display_path is not None else "",
                        "display_asset": display_asset,
                        "association": "cell",
                    }
                if "body_index" in surface_arrays:
                    selection_assets["cad_body"] = {
                        **surface_asset,
                        "path": str(display_path) if display_path is not None else "",
                        "display_asset": display_asset,
                        "association": "cell",
                    }
            for asset in geometry_assets:
                content = _string(asset.get("content")).casefold()
                role = _string(asset.get("role")).casefold()
                if content == "topological_edges":
                    selection_assets["cad_edge"] = {
                        **asset,
                        "association": "cell",
                    }
                elif content == "topological_vertices":
                    selection_assets["cad_vertex"] = {
                        **asset,
                        "association": "cell",
                    }
                elif content == "mesh" and role == "selection_identity":
                    selection_assets["fe_node"] = {
                        **asset,
                        "association": "point",
                    }
                    selection_assets["fe_element"] = {
                        **asset,
                        "association": "cell",
                    }
                elif content == "element_faces":
                    selection_assets["fe_element_face"] = {
                        **asset,
                        "association": "cell",
                    }
            for selection_asset in selection_assets.values():
                selection_path_text = _string(selection_asset.get("path"))
                selection_path = (
                    Path(selection_path_text) if selection_path_text else None
                )
                if not _mapping(selection_asset.get("display_asset")) and (
                    selection_path is None or not selection_path.is_file()
                ):
                    raise ViewerWidgetNoBind(
                        f"Model viewer selection asset is missing: {selection_path}"
                    )
                selection_asset["path"] = (
                    str(selection_path) if selection_path is not None else ""
                )
            selection_topology_asset = next(
                (
                    value
                    for value in geometry_assets
                    if _string(value.get("content")).casefold() == "selection_topology"
                ),
                {},
            )
            if selection_topology_asset:
                selection_topology_path = Path(
                    _string(selection_topology_asset.get("path"))
                )
                if not selection_topology_path.is_file():
                    raise ViewerWidgetNoBind(
                        "Model viewer selection-topology file is missing: "
                        f"{selection_topology_path}"
                    )
                selection_topology_asset["path"] = str(selection_topology_path)
            descriptors.append(
                {
                    **layer,
                    "display_path": str(display_path) if display_path is not None else "",
                    "display_asset": display_asset,
                    "interaction_display_path": str(interaction_path) if interaction_path is not None else "",
                    "attribute_colors": _mapping(
                        display_asset.get(
                            "attribute_colors",
                            layer.get(
                                "attribute_colors",
                                surface_asset.get("attribute_colors"),
                            ),
                        )
                    ),
                    "entity_arrays": _mapping(
                        display_asset.get(
                            "entity_arrays",
                            layer.get(
                                "entity_arrays",
                                surface_asset.get("entity_arrays"),
                            ),
                        )
                    ),
                    "selection_assets": selection_assets,
                    "selection_topology_asset": selection_topology_asset,
                    "topological_edges": {
                        **topology,
                        "display_path": str(topology_path) if topology_path is not None else "",
                        "attribute_colors": _mapping(topology.get("attribute_colors")),
                        "entity_arrays": _mapping(topology.get("entity_arrays")),
                    }
                    if topology
                    else {},
                }
            )
        if not descriptors:
            raise ViewerWidgetNoBind("Model viewer scene has no layers.")
        return descriptors

    @staticmethod
    def _shared_memory_descriptor(value: Any) -> dict[str, Any]:
        invalid = "Model viewer shared-memory asset descriptor is invalid."
        if not isinstance(value, Mapping):
            raise ValueError(invalid)
        descriptor = dict(value)
        if set(descriptor) != _SHARED_MEMORY_DESCRIPTOR_KEYS:
            raise ValueError(invalid)
        name = descriptor.get("name")
        byte_length = descriptor.get("byte_length")
        checksum = descriptor.get("sha256")
        if (
            descriptor.get("schema")
            != ENGINEERING_VIEWER_SHARED_MEMORY_ASSET_SCHEMA
            or type(descriptor.get("version")) is not int
            or descriptor["version"] != 1
            or descriptor.get("storage") != "shared_memory"
            or not isinstance(name, str)
            or not name
            or name != name.strip()
            or "\x00" in name
            or len(name.encode("utf-8")) > _MAX_SHARED_MEMORY_NAME_BYTES
            or type(byte_length) is not int
            or not 0 < byte_length <= _MAX_SHARED_MEMORY_SEGMENT_BYTES
            or not isinstance(checksum, str)
            or len(checksum) != 64
            or checksum != checksum.casefold()
            or any(character not in "0123456789abcdef" for character in checksum)
            or descriptor.get("format") != "vtkxml-polydata"
            or descriptor.get("role") not in {"full", "display"}
            or descriptor.get("content") not in {"surface", "mesh"}
            or not isinstance(descriptor.get("attribute_colors"), Mapping)
            or not isinstance(descriptor.get("entity_arrays"), Mapping)
        ):
            raise ValueError(invalid)
        descriptor["attribute_colors"] = dict(descriptor["attribute_colors"])
        descriptor["entity_arrays"] = dict(descriptor["entity_arrays"])
        try:
            encoded = json.dumps(
                descriptor,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeEncodeError):
            raise ValueError(invalid) from None
        if len(encoded) > _MAX_SHARED_MEMORY_DESCRIPTOR_BYTES:
            raise ValueError(invalid)
        return descriptor

    def _load_layer_datasets(self, descriptors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        loaded: list[dict[str, Any]] = []
        for layer in descriptors:
            source_kind = _string(layer.get("source_kind")).casefold()
            display_asset = _mapping(layer.get("display_asset"))
            dataset = self._prepare_shaded_dataset(
                self._load_shared_memory_dataset(display_asset)
                if display_asset
                else self._dataset_loader(str(layer["display_path"])),
                source_kind=source_kind,
            )
            interaction_path = _string(layer.get("interaction_display_path"))
            interaction_dataset = (
                self._prepare_shaded_dataset(
                    self._dataset_loader(interaction_path),
                    source_kind=source_kind,
                )
                if interaction_path
                else None
            )
            topology = _mapping(layer.get("topological_edges"))
            topology_path = _string(topology.get("display_path"))
            topology_dataset = self._dataset_loader(topology_path) if topology_path else None
            selection_datasets: dict[str, Any] = {}
            loaded_paths: dict[str, Any] = {str(layer["display_path"]): dataset}
            if topology_path and topology_dataset is not None:
                loaded_paths[topology_path] = topology_dataset
            for entity_kind, asset in _mapping(layer.get("selection_assets")).items():
                path = _string(_mapping(asset).get("path"))
                asset_display = _mapping(_mapping(asset).get("display_asset"))
                if asset_display:
                    selection_datasets[entity_kind] = dataset
                    continue
                if not path:
                    continue
                if path not in loaded_paths:
                    loaded_paths[path] = self._dataset_loader(path)
                selection_datasets[entity_kind] = loaded_paths[path]
            topology_payload: dict[str, Any] = {}
            topology_asset = _mapping(layer.get("selection_topology_asset"))
            topology_metadata_path = _string(topology_asset.get("path"))
            if topology_metadata_path:
                topology_payload = _mapping(
                    json.loads(Path(topology_metadata_path).read_text(encoding="utf-8"))
                )
            try:
                scale_factor = float(layer.get("scale_factor", 1.0) or 1.0)
            except (TypeError, ValueError):
                scale_factor = 1.0
            if scale_factor != 1.0:
                dataset = self._scaled_dataset(dataset, scale_factor)
                if interaction_dataset is not None:
                    interaction_dataset = self._scaled_dataset(interaction_dataset, scale_factor)
                if topology_dataset is not None:
                    topology_dataset = self._scaled_dataset(topology_dataset, scale_factor)
                selection_datasets = {
                    entity_kind: self._scaled_dataset(value, scale_factor)
                    for entity_kind, value in selection_datasets.items()
                }
            loaded.append(
                {
                    **layer,
                    "dataset": dataset,
                    "interaction_dataset": interaction_dataset,
                    "topological_edges_dataset": topology_dataset,
                    "selection_datasets": selection_datasets,
                    "selection_topology": topology_payload,
                }
            )
        return loaded

    @staticmethod
    def _load_shared_memory_dataset(descriptor: Mapping[str, Any]) -> Any:
        invalid = "Model viewer shared-memory geometry is unavailable."
        segment: SharedMemory | None = None
        try:
            segment = SharedMemory(name=str(descriptor["name"]), create=False)
            byte_length = int(descriptor["byte_length"])
            if (
                len(segment.buf) < byte_length
                or len(segment.buf) > _MAX_SHARED_MEMORY_SEGMENT_BYTES
            ):
                raise ValueError(invalid)
            payload = bytes(segment.buf[:byte_length])
        except Exception:  # noqa: BLE001
            raise ValueError(invalid) from None
        finally:
            if segment is not None:
                segment.close()
        if hashlib.sha256(payload).hexdigest() != descriptor["sha256"]:
            raise ValueError(invalid)
        try:
            import pyvista as pv
            from vtkmodules.vtkIOXML import vtkXMLPolyDataReader

            reader = vtkXMLPolyDataReader()
            reader.SetReadFromInputString(True)
            reader.SetInputString(payload)
            reader.Update()
            if reader.GetErrorCode() != 0:
                raise ValueError(invalid)
            return pv.wrap(reader.GetOutput()).copy(deep=True)
        except Exception:  # noqa: BLE001
            raise ValueError(invalid) from None

    @staticmethod
    def _scaled_dataset(dataset: Any, scale_factor: float) -> Any:
        scale = getattr(dataset, "scale", None)
        if not callable(scale):
            raise TypeError("Model viewer scene dataset cannot apply unit conversion.")
        scaled = scale(scale_factor, inplace=False)
        return dataset if scaled is None else scaled

    @staticmethod
    def _prepare_shaded_dataset(dataset: Any, *, source_kind: str) -> Any:
        if source_kind != "cad":
            return dataset
        clear_active_scalars = getattr(dataset, "set_active_scalars", None)
        if callable(clear_active_scalars):
            clear_active_scalars(None)
        compute_normals = getattr(dataset, "compute_normals", None)
        if not callable(compute_normals):
            return dataset
        try:
            prepared = compute_normals(
                cell_normals=False,
                point_normals=True,
                split_vertices=False,
                consistent_normals=True,
                inplace=False,
            )
        except (TypeError, RuntimeError, ValueError):
            return dataset
        return dataset if prepared is None else prepared

    @staticmethod
    def _load_key(request: ViewerWidgetBindRequest) -> _LoadKey:
        return (
            str(request.workspace_id),
            str(request.node_id),
            str(request.session_id),
            int(request.transport_revision),
        )

    def _loaded_layers(self, request: ViewerWidgetBindRequest) -> list[dict[str, Any]] | None:
        key = self._load_key(request)
        with self._load_lock:
            result = self._loaded_results.get(key)
            if result is None:
                return None
            if result.error is None:
                self._loaded_results.pop(key, None)
        if result.error is not None:
            raise result.error
        return result.layers

    def _start_background_load(
        self,
        request: ViewerWidgetBindRequest,
        descriptors: list[dict[str, Any]],
    ) -> None:
        key = self._load_key(request)
        scope = (key[0], key[1])
        with self._load_lock:
            if key in self._pending_loads or key in self._loaded_results:
                return
            previous_key = self._active_loads.get(scope)
            if previous_key is not None and previous_key != key:
                previous = self._pending_loads.pop(previous_key, None)
                if previous is not None:
                    previous.cancel()
                self._loaded_results.pop(previous_key, None)
            self._active_loads[scope] = key
            future = self._load_executor.submit(self._load_layer_datasets, descriptors)
            self._pending_loads[key] = future
        future.add_done_callback(lambda completed, load_key=key: self._load_finished(load_key, completed))

    def _load_finished(
        self,
        key: _LoadKey,
        future: Future[list[dict[str, Any]]],
    ) -> None:
        if future.cancelled():
            return
        try:
            result = _EngineeringLoadResult(layers=future.result())
        except BaseException as exc:  # noqa: BLE001
            result = _EngineeringLoadResult(error=exc)
        scope = (key[0], key[1])
        with self._load_lock:
            self._pending_loads.pop(key, None)
            if self._shutdown or self._active_loads.get(scope) != key:
                return
            self._loaded_results[key] = result
        self.load_ready.emit(key[0], key[1], key[2], key[3])

    def _cancel_loads_for_scope(self, workspace_id: str, node_id: str) -> None:
        scope = (str(workspace_id), str(node_id))
        with self._load_lock:
            active_key = self._active_loads.pop(scope, None)
            future = self._pending_loads.pop(active_key, None) if active_key is not None else None
            if active_key is not None:
                self._loaded_results.pop(active_key, None)
        if future is not None:
            future.cancel()

    def _resolve_interactor(
        self,
        *,
        container: QWidget | None,
        current_widget: QWidget | None,
    ) -> QWidget:
        if self._is_reusable_interactor(current_widget):
            interactor = current_widget
            self._mark_native_window_overlay(interactor)
            if container is not None and interactor.parent() is not container:
                interactor.setParent(container)
            return interactor
        interactor = self._interactor_factory(container)
        if not isinstance(interactor, QWidget):
            raise TypeError("Model viewer interactor factory must return a QWidget instance.")
        self._mark_native_window_overlay(interactor)
        if container is not None and interactor.parent() is not container:
            interactor.setParent(container)
        self._apply_canvas_background(interactor)
        self._widget_state[interactor] = _EngineeringWidgetState(backend_id=self.backend_id)
        return interactor

    def _populate_interactor(
        self,
        interactor: QWidget,
        *,
        request: ViewerWidgetBindRequest,
        layers: list[dict[str, Any]],
        defer_until_attach: bool = False,
    ) -> None:
        clear = getattr(interactor, "clear", None)
        add_mesh = getattr(interactor, "add_mesh", None)
        if not callable(clear) or not callable(add_mesh):
            raise TypeError("Model viewer interactor must expose clear() and add_mesh().")

        camera_state = _mapping(request.camera_state)
        previous_state = self._widget_state.get(interactor)
        if previous_state is not None and previous_state.session_id:
            live_camera_state = extract_camera_state(interactor)
            if live_camera_state:
                camera_state = live_camera_state

        if previous_state is not None:
            self._detach_interaction_lod(previous_state)
            self._detach_selection_picking(previous_state)
            self._remove_selection_highlight(interactor, previous_state)
            self._remove_selection_isolate(interactor, previous_state)
            self._remove_orientation_aids(interactor, previous_state)
            self._sync_hidden_line_removal(interactor, previous_state, enabled=False)

        clear()
        enable_lightkit = getattr(interactor, "enable_lightkit", None)
        if callable(enable_lightkit):
            enable_lightkit()
        self._apply_canvas_background(
            interactor,
            _string(request.options.get(_VIEWER_BACKGROUND_OPTION)),
            flat=self._representation(request.options) == "wireframe_visible_edges",
        )
        self._apply_projection(interactor, request.options)
        actors: dict[str, Any] = {}
        topology_actors: dict[str, Any] = {}
        for layer in layers:
            actor = add_mesh(layer["dataset"], **self._mesh_kwargs(layer, options=request.options))
            name = _string(layer.get("id"))
            actors[name] = actor
            topology_dataset = layer.get("topological_edges_dataset")
            if topology_dataset is not None:
                topology_actors[name] = add_mesh(
                    topology_dataset,
                    **self._topological_edge_kwargs(layer, options=request.options),
                )
        for actor in (*actors.values(), *topology_actors.values()):
            self._apply_clipping(actor, request.options)
        if not defer_until_attach:
            if camera_state:
                apply_camera_state(interactor, camera_state)
            else:
                reset_camera = getattr(interactor, "reset_camera", None)
                if callable(reset_camera):
                    reset_camera()
        state = _EngineeringWidgetState(
            backend_id=self.backend_id,
            workspace_id=request.workspace_id,
            node_id=request.node_id,
            session_id=request.session_id,
            transport_revision=request.transport_revision,
            layer_count=len(layers),
            actors=actors,
            topology_actors=topology_actors,
            layers={_string(layer.get("id")): dict(layer) for layer in layers},
            layer_visibility={
                _string(layer.get("id")): (
                    previous_state.layer_visibility.get(_string(layer.get("id")), True)
                    if previous_state is not None and previous_state.session_id == request.session_id
                    else layer.get("visible") is not False
                )
                for layer in layers
            },
            current_options=dict(request.options),
            scene_fingerprint=_string(request.summary.get("scene_fingerprint")),
            presentation_attach_required=bool(defer_until_attach),
            initial_attach_pending=bool(defer_until_attach),
            pending_camera_state=dict(camera_state) if defer_until_attach else {},
            initial_camera_reset_pending=bool(defer_until_attach and not camera_state),
            selection_filter=(
                _string(request.summary.get("default_selection_filter")).casefold()
                or "cad_body"
            ),
        )
        self._widget_state[interactor] = state
        self._add_selection_source_actors(interactor, state)
        if not any(
            source["entity_kind"] == state.selection_filter
            for source in state.selection_source_actors.values()
        ):
            available_filters = {
                source["entity_kind"]
                for source in state.selection_source_actors.values()
            }
            state.selection_filter = (
                "cad_body"
                if "cad_body" in available_filters
                else "fe_element"
                if "fe_element" in available_filters
                else next(iter(sorted(available_filters)), "cad_body")
            )
        self._sync_selection_source_cues(state)
        self._sync_hidden_line_removal(
            interactor,
            state,
            enabled=self._representation(request.options) == "wireframe_visible_edges",
        )
        self._sync_actor_visibility(state)
        if not defer_until_attach:
            self._sync_orientation_aids(interactor, state, request.options)
            self._install_selection_picking(interactor, state)
            self._install_interaction_lod(interactor, state)
            render = getattr(interactor, "render", None)
            if callable(render):
                render()

    def _update_existing_actors(
        self,
        interactor: QWidget,
        *,
        state: _EngineeringWidgetState,
        request: ViewerWidgetBindRequest,
    ) -> None:
        self._apply_canvas_background(
            interactor,
            _string(request.options.get(_VIEWER_BACKGROUND_OPTION)),
            flat=self._representation(request.options) == "wireframe_visible_edges",
        )
        self._apply_projection(interactor, request.options)
        old_attribute_colors = _coerce_bool(state.current_options.get(_SHOW_ATTRIBUTE_COLORS_OPTION))
        new_attribute_colors = _coerce_bool(request.options.get(_SHOW_ATTRIBUTE_COLORS_OPTION))
        self._replace_direct_color_actors(
            interactor, state, request.options,
            attribute_colors_changed=old_attribute_colors != new_attribute_colors,
        )
        old_representation = self._representation(state.current_options)
        new_representation = self._representation(request.options)
        if (old_representation == "wireframe_visible_edges") != (
            new_representation == "wireframe_visible_edges"
        ):
            self._replace_cad_surface_actors(interactor, state, request.options)
        for name, actor in list(state.actors.items()):
            layer = state.layers.get(name, {})
            kwargs = self._mesh_kwargs(layer, options=request.options)
            actor_property = getattr(actor, "GetProperty", lambda: None)()
            if actor_property is not None:
                opacity_setter = getattr(actor_property, "SetOpacity", None)
                if callable(opacity_setter):
                    opacity_setter(float(kwargs["opacity"]))
                edge_setter = getattr(actor_property, "SetEdgeVisibility", None)
                if callable(edge_setter):
                    edge_setter(1 if kwargs["show_edges"] else 0)
                representation = str(kwargs["style"])
                representation_setter = getattr(
                    actor_property,
                    {
                        "wireframe": "SetRepresentationToWireframe",
                        "points": "SetRepresentationToPoints",
                    }.get(representation, "SetRepresentationToSurface"),
                    None,
                )
                if callable(representation_setter):
                    representation_setter()
                self._apply_actor_material(actor_property, kwargs)
            self._apply_clipping(actor, request.options)
        for name, actor in state.topology_actors.items():
            kwargs = self._topological_edge_kwargs(state.layers[name], options=request.options)
            actor_property = getattr(actor, "GetProperty", lambda: None)()
            opacity_setter = getattr(actor_property, "SetOpacity", None)
            if callable(opacity_setter):
                opacity_setter(float(kwargs["opacity"]))
            self._apply_clipping(actor, request.options)
        self._apply_clipping(state.selection_highlight_actor, request.options)
        self._apply_clipping(state.selection_isolate_actor, request.options)
        state.current_options = dict(request.options)
        self._sync_hidden_line_removal(
            interactor,
            state,
            enabled=self._representation(request.options) == "wireframe_visible_edges",
        )
        if not state.presentation_attach_required:
            self._sync_orientation_aids(interactor, state, request.options)
        if state.selection_isolated:
            self._rebuild_selection_isolate(interactor, state)
        self._sync_actor_visibility(state)
        if not state.presentation_attach_required:
            render = getattr(interactor, "render", None)
            if callable(render):
                render()

    def _add_selection_source_actors(
        self,
        interactor: QWidget,
        state: _EngineeringWidgetState,
    ) -> None:
        add_mesh = getattr(interactor, "add_mesh", None)
        if not callable(add_mesh):
            return
        for name, layer in state.layers.items():
            layer_id = _string(layer.get("id"))
            source = _mapping(layer.get("source"))
            source_fingerprint = _string(source.get("sha256")).casefold()
            assets = _mapping(layer.get("selection_assets"))
            for entity_kind, dataset in _mapping(layer.get("selection_datasets")).items():
                asset = _mapping(assets.get(entity_kind))
                if dataset is None or entity_kind not in _SELECTION_FILTERS:
                    continue
                kwargs: dict[str, Any] = {
                    "name": f"__engineering_pick_source__:{name}:{entity_kind}",
                    "color": "#38bdf8",
                    "opacity": 0.0,
                    "pickable": True,
                    "reset_camera": False,
                    "render": False,
                    "show_scalar_bar": False,
                }
                if entity_kind == "cad_vertex":
                    kwargs.update(
                        style="points",
                        point_size=8,
                        render_points_as_spheres=True,
                    )
                elif entity_kind == "cad_edge":
                    kwargs["line_width"] = 2
                actor = add_mesh(dataset, **kwargs)
                set_use_bounds = getattr(actor, "SetUseBounds", None)
                if callable(set_use_bounds):
                    set_use_bounds(0)
                state.selection_source_actors[f"{layer_id}:{entity_kind}"] = {
                    "actor": actor,
                    "association": _string(asset.get("association")) or "cell",
                    "dataset": dataset,
                    "entity_kind": entity_kind,
                    "layer_id": layer_id,
                    "source_fingerprint": source_fingerprint,
                }
        self._sync_selection_source_cues(state)

    @staticmethod
    def _sync_selection_source_cues(state: _EngineeringWidgetState) -> None:
        for source in state.selection_source_actors.values():
            actor = source.get("actor")
            actor_property = getattr(actor, "GetProperty", lambda: None)()
            if actor_property is None:
                continue
            entity_kind = _string(source.get("entity_kind")).casefold()
            active = entity_kind == state.selection_filter and entity_kind in {
                "cad_edge",
                "cad_vertex",
            }
            opacity = getattr(actor_property, "SetOpacity", None)
            if callable(opacity):
                opacity(0.18 if active else 0.0)
            if entity_kind == "cad_edge":
                line_width = getattr(actor_property, "SetLineWidth", None)
                if callable(line_width):
                    line_width(2.0 if active else 1.0)
            elif entity_kind == "cad_vertex":
                point_size = getattr(actor_property, "SetPointSize", None)
                if callable(point_size):
                    point_size(8.0 if active else 1.0)

    def _install_selection_picking(
        self,
        interactor: QWidget,
        state: _EngineeringWidgetState,
    ) -> None:
        target = getattr(interactor, "iren", None) or getattr(interactor, "interactor", None)
        if target is None or state.selection_observers:
            return

        def camera_interaction(*_args: Any) -> None:
            if state.selection_press_position is None:
                return
            position = self._triad_event_position(target)
            if position is not None and position != state.selection_press_position:
                state.selection_camera_interaction_revision += 1
                state.selection_camera_interacting = True

        def press(*_args: Any) -> None:
            position = self._triad_event_position(target)
            size = self._triad_render_size(target)
            if (
                position is None
                or size is None
                or self._position_in_triad(position, size)
                or self._position_in_view_cube(position, size)
            ):
                state.selection_press_position = None
                return
            state.selection_press_position = position
            state.selection_dragged = False
            state.selection_camera_interacting = False
            state.selection_press_camera_revision = state.selection_camera_interaction_revision

        def move(*_args: Any) -> None:
            if state.selection_press_position is None:
                return
            position = self._triad_event_position(target)
            if position is None:
                return
            delta_x = position[0] - state.selection_press_position[0]
            delta_y = position[1] - state.selection_press_position[1]
            threshold = self._selection_click_threshold(interactor)
            if delta_x * delta_x + delta_y * delta_y > threshold * threshold:
                state.selection_dragged = True

        def release(*_args: Any) -> None:
            position = self._triad_event_position(target)
            stationary = (
                position is not None
                and state.selection_press_position is not None
                and not state.selection_dragged
                and not state.triad_drag_active
                and not state.selection_camera_interacting
                and state.selection_press_camera_revision
                == state.selection_camera_interaction_revision
            )
            state.selection_press_position = None
            state.selection_dragged = False
            if stationary:
                now = time.monotonic()
                threshold = self._selection_click_threshold(interactor)
                previous = state.selection_last_click_position
                double_click = (
                    previous is not None
                    and now - state.selection_last_click_time
                    <= max(0.1, QApplication.doubleClickInterval() / 1000.0)
                    and (position[0] - previous[0]) ** 2
                    + (position[1] - previous[1]) ** 2
                    <= threshold * threshold
                )
                if double_click:
                    state.selection_last_click_position = None
                    state.selection_last_click_time = 0.0
                else:
                    state.selection_last_click_position = position
                    state.selection_last_click_time = now
                toggle = self._control_key_active(target)
                self._pick_selection(
                    interactor,
                    state,
                    position,
                    propagate=double_click,
                    toggle=toggle,
                    undo_prior_single=double_click and toggle,
                )
            else:
                state.selection_last_click_position = None
                state.selection_last_click_time = 0.0

        for event_name, callback in (
            ("LeftButtonPressEvent", press),
            ("MouseMoveEvent", move),
            ("LeftButtonReleaseEvent", release),
            ("LeaveEvent", lambda *_args: self._cancel_selection_click(state)),
            ("StartInteractionEvent", camera_interaction),
            ("EndInteractionEvent", camera_interaction),
        ):
            observer_target, observer_id = self._add_triad_observer(
                target,
                event_name,
                callback,
            )
            if observer_id is not None:
                state.selection_observers.append((observer_target, observer_id))

    @staticmethod
    def _cancel_selection_click(state: _EngineeringWidgetState) -> None:
        state.selection_press_position = None
        state.selection_dragged = False
        state.selection_camera_interacting = False

    @staticmethod
    def _selection_click_threshold(interactor: QWidget) -> int:
        ratio_getter = getattr(interactor, "devicePixelRatioF", None)
        try:
            ratio = float(ratio_getter()) if callable(ratio_getter) else 1.0
        except (TypeError, ValueError):
            ratio = 1.0
        base = QApplication.startDragDistance()
        return max(1, round(float(base) * max(1.0, ratio)))

    @staticmethod
    def _control_key_active(target: Any) -> bool:
        raw = getattr(target, "interactor", target)
        getter = getattr(raw, "GetControlKey", None)
        if not callable(getter):
            getter = getattr(target, "GetControlKey", None)
        try:
            return bool(getter()) if callable(getter) else False
        except (TypeError, RuntimeError):
            return False

    @classmethod
    def _detach_selection_picking(cls, state: _EngineeringWidgetState) -> None:
        cls._cancel_selection_click(state)
        for target, observer_id in state.selection_observers:
            remove = getattr(target, "remove_observer", None)
            if not callable(remove):
                remove = getattr(target, "RemoveObserver", None)
            if callable(remove):
                try:
                    remove(observer_id)
                except (TypeError, RuntimeError):
                    pass
        state.selection_observers.clear()

    def _pick_selection(
        self,
        interactor: QWidget,
        state: _EngineeringWidgetState,
        position: tuple[int, int],
        *,
        propagate: bool,
        toggle: bool,
        undo_prior_single: bool = False,
    ) -> None:
        entity_kind = state.selection_filter
        sources = [
            value
            for value in state.selection_source_actors.values()
            if value["entity_kind"] == entity_kind
            and state.layer_visibility.get(value["layer_id"], True)
        ]
        renderer = getattr(interactor, "renderer", None)
        if not sources or renderer is None:
            return
        association = "point" if entity_kind == "fe_node" else "cell"
        picker = self._picker_factory(association)
        pick_from_list = getattr(picker, "PickFromListOn", None)
        if callable(pick_from_list):
            pick_from_list()
        add_pick = getattr(picker, "AddPickList", None)
        if callable(add_pick):
            for source in sources:
                add_pick(source["actor"])
        pick = getattr(picker, "Pick", None)
        if not callable(pick) or not pick(position[0], position[1], 0.0, renderer):
            if not toggle:
                self._set_selected_entities(interactor, state, [])
            return
        actor_getter = getattr(picker, "GetActor", None) or getattr(
            picker,
            "GetViewProp",
            None,
        )
        actor = actor_getter() if callable(actor_getter) else None
        source = next((value for value in sources if value["actor"] is actor), None)
        if source is None:
            return
        index_getter = getattr(
            picker,
            "GetPointId" if association == "point" else "GetCellId",
            None,
        )
        index = int(index_getter()) if callable(index_getter) else -1
        entity = self._entity_ref(source, index)
        if entity is None:
            return
        selected = self._expand_tangent_selection(state, entity) if propagate else [entity]
        if toggle:
            current = [dict(value) for value in state.selected_entities]
            if undo_prior_single:
                current = self._toggle_entities(current, [entity])
            selected = self._toggle_entities(current, selected)
        self._set_selected_entities(interactor, state, selected)

    @staticmethod
    def _toggle_entities(
        current: list[dict[str, str]],
        candidates: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        def identity(entity: Mapping[str, Any]) -> tuple[str, str, str, str]:
            return (
                _string(entity.get("layer_id")),
                _string(entity.get("source_fingerprint")).casefold(),
                _string(entity.get("entity_kind")).casefold(),
                _string(entity.get("entity_id")),
            )

        ordered = {identity(entity): dict(entity) for entity in current}
        for entity in candidates:
            key = identity(entity)
            if key in ordered:
                ordered.pop(key)
            else:
                ordered[key] = dict(entity)
        return list(ordered.values())

    @staticmethod
    def _entity_ref(source: Mapping[str, Any], index: int) -> dict[str, str] | None:
        if index < 0:
            return None
        dataset = source.get("dataset")
        entity_kind = _string(source.get("entity_kind")).casefold()
        association = _string(source.get("association")).casefold()
        data = getattr(dataset, f"{association}_data", {})

        def value(name: str) -> int | None:
            values = data.get(name)
            if values is None:
                return None
            try:
                return int(values[index])
            except (IndexError, TypeError, ValueError):
                return None

        if entity_kind.startswith("cad_"):
            part_index = value("corex_part_index")
            local_index = value(f"corex_{entity_kind.removeprefix('cad_')}_index")
            if part_index is None or local_index is None:
                return None
            entity_id = (
                f"part:{part_index}/{entity_kind.removeprefix('cad_')}:{local_index}"
            )
        else:
            block_index = value("corex_block_index")
            if block_index is None:
                return None
            if entity_kind == "fe_node":
                node_index = value("corex_node_index")
                if node_index is None:
                    return None
                entity_id = f"block:{block_index}/node:{node_index}"
            else:
                element_index = value("corex_element_index")
                if element_index is None:
                    return None
                entity_id = f"block:{block_index}/element:{element_index}"
                if entity_kind == "fe_element_face":
                    face_index = value("corex_element_face_index")
                    if face_index is None:
                        return None
                    entity_id += f"/face:{face_index}"
        fingerprint = _string(source.get("source_fingerprint")).casefold()
        if len(fingerprint) != 64:
            return None
        return {
            "layer_id": _string(source.get("layer_id")),
            "source_fingerprint": fingerprint,
            "entity_kind": entity_kind,
            "entity_id": entity_id,
        }

    def _expand_tangent_selection(
        self,
        state: _EngineeringWidgetState,
        entity: dict[str, str],
    ) -> list[dict[str, str]]:
        entity_kind = entity["entity_kind"]
        if entity_kind not in {"cad_edge", "cad_face"}:
            return [entity]
        layer = next(
            (
                value
                for value in state.layers.values()
                if _string(value.get("id")) == entity["layer_id"]
                and _string(_mapping(value.get("source")).get("sha256")).casefold()
                == entity["source_fingerprint"]
            ),
            None,
        )
        topology = _mapping(_mapping(layer).get("selection_topology"))
        records = topology.get(
            "edge_continuity" if entity_kind == "cad_edge" else "face_continuity"
        )
        if not isinstance(records, list):
            return [entity]
        graph: dict[str, set[str]] = {}
        angle = self._tangent_selection_angle()
        for raw_record in records:
            record = _mapping(raw_record)
            if not _coerce_bool(record.get("supported")):
                continue
            if entity_kind == "cad_edge":
                try:
                    deviation = float(record.get("tangent_deviation_degrees"))
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(deviation) or deviation > angle:
                    continue
                first, second = _string(record.get("edge_a")), _string(record.get("edge_b"))
            else:
                try:
                    deviation = float(record.get("angular_deviation_degrees"))
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(deviation) or deviation > angle:
                    continue
                first, second = _string(record.get("face_a")), _string(record.get("face_b"))
            if first and second:
                graph.setdefault(first, set()).add(second)
                graph.setdefault(second, set()).add(first)
        visited = {entity["entity_id"]}
        pending = [entity["entity_id"]]
        while pending:
            for adjacent in graph.get(pending.pop(), ()):
                if adjacent not in visited:
                    visited.add(adjacent)
                    pending.append(adjacent)
        return [
            {**entity, "entity_id": entity_id}
            for entity_id in sorted(visited)
        ]

    def _tangent_selection_angle(self) -> float:
        try:
            value = float(self._tangent_selection_angle_provider())
        except (TypeError, ValueError, OSError):
            return 5.0
        return min(90.0, max(0.0, value)) if math.isfinite(value) else 5.0

    def _set_selected_entities(
        self,
        interactor: QWidget,
        state: _EngineeringWidgetState,
        entities: list[dict[str, str]],
    ) -> bool:
        self._remove_selection_highlight(interactor, state)
        state.selected_entities = [dict(entity) for entity in entities]
        if not state.selected_entities:
            if state.selection_isolated:
                state.selection_isolated = False
                self._remove_selection_isolate(interactor, state)
                self._sync_actor_visibility(state)
            self.selection_changed.emit(state.workspace_id, state.node_id)
            render = getattr(interactor, "render", None)
            if callable(render):
                render()
            return True
        selected = self._selected_layer_datasets(state)
        dataset = self._combine_selection_datasets(selected.values())
        add_mesh = getattr(interactor, "add_mesh", None)
        if dataset is None or not callable(add_mesh):
            state.selected_entities.clear()
            return False
        entity_kind = state.selected_entities[0]["entity_kind"]
        state.selection_highlight_actor = add_mesh(
            dataset,
            **self._selection_actor_kwargs(entity_kind, highlight=True),
        )
        self._apply_clipping(state.selection_highlight_actor, state.current_options)
        if state.selection_isolated:
            self._rebuild_selection_isolate(interactor, state)
        self.selection_changed.emit(state.workspace_id, state.node_id)
        render = getattr(interactor, "render", None)
        if callable(render):
            render()
        return True

    @staticmethod
    def _remove_actor(interactor: QWidget, actor: Any) -> None:
        remove_actor = getattr(interactor, "remove_actor", None)
        if actor is None or not callable(remove_actor):
            return
        try:
            remove_actor(actor, render=False)
        except (TypeError, RuntimeError):
            pass

    @classmethod
    def _remove_selection_highlight(
        cls,
        interactor: QWidget,
        state: _EngineeringWidgetState,
    ) -> None:
        cls._remove_actor(interactor, state.selection_highlight_actor)
        state.selection_highlight_actor = None

    @classmethod
    def _remove_selection_isolate(
        cls,
        interactor: QWidget,
        state: _EngineeringWidgetState,
    ) -> None:
        cls._remove_actor(interactor, state.selection_isolate_actor)
        state.selection_isolate_actor = None

    def _selected_layer_datasets(self, state: _EngineeringWidgetState) -> dict[str, Any]:
        selected: dict[str, Any] = {}
        by_source: dict[tuple[str, str, str], set[str]] = {}
        for entity in state.selected_entities:
            key = (
                entity["layer_id"],
                entity["source_fingerprint"],
                entity["entity_kind"],
            )
            by_source.setdefault(key, set()).add(entity["entity_id"])
        for source in state.selection_source_actors.values():
            key = (
                source["layer_id"],
                source["source_fingerprint"],
                source["entity_kind"],
            )
            entity_ids = by_source.get(key)
            if not entity_ids:
                continue
            stable_ids = self._stable_entity_ids(
                source["dataset"],
                entity_kind=source["entity_kind"],
                association=source["association"],
            )
            indices = [
                index
                for index, stable_id in enumerate(stable_ids)
                if stable_id in entity_ids
            ]
            dataset = self._extract_selection_dataset(
                source["dataset"],
                indices,
                entity_kind=source["entity_kind"],
            )
            if dataset is not None:
                selected[f"{source['layer_id']}:{source['entity_kind']}"] = dataset
        return selected

    @staticmethod
    def _stable_entity_ids(
        dataset: Any,
        *,
        entity_kind: str,
        association: str,
    ) -> list[str]:
        data = getattr(dataset, f"{association}_data", {})

        def values(name: str) -> list[Any]:
            raw = data.get(name)
            if raw is None:
                return []
            tolist = getattr(raw, "tolist", None)
            return list(tolist() if callable(tolist) else raw)

        if entity_kind.startswith("cad_"):
            part_values = values("corex_part_index")
            local_kind = entity_kind.removeprefix("cad_")
            local_values = values(f"corex_{local_kind}_index")
            if len(part_values) != len(local_values):
                return []
            return [
                f"part:{int(part_index)}/{local_kind}:{int(local_index)}"
                for part_index, local_index in zip(
                    part_values,
                    local_values,
                    strict=True,
                )
            ]
        block_values = values("corex_block_index")
        if entity_kind == "fe_node":
            node_values = values("corex_node_index")
            if len(block_values) != len(node_values):
                return []
            return [
                f"block:{int(block_index)}/node:{int(node_index)}"
                for block_index, node_index in zip(
                    block_values,
                    node_values,
                    strict=True,
                )
            ]
        element_values = values("corex_element_index")
        if len(block_values) != len(element_values):
            return []
        if entity_kind == "fe_element":
            return [
                f"block:{int(block_index)}/element:{int(element_index)}"
                for block_index, element_index in zip(
                    block_values,
                    element_values,
                    strict=True,
                )
            ]
        face_values = values("corex_element_face_index")
        if len(block_values) != len(face_values):
            return []
        return [
            f"block:{int(block_index)}/element:{int(element_index)}/face:{int(face_index)}"
            for block_index, element_index, face_index in zip(
                block_values,
                element_values,
                face_values,
                strict=True,
            )
        ]

    @staticmethod
    def _extract_selection_dataset(
        dataset: Any,
        indices: list[int],
        *,
        entity_kind: str,
    ) -> Any | None:
        if not indices:
            return None
        if entity_kind == "fe_node":
            extract_points = getattr(dataset, "extract_points", None)
            if not callable(extract_points):
                return None
            try:
                return extract_points(
                    indices,
                    adjacent_cells=False,
                    include_cells=False,
                )
            except TypeError:
                return extract_points(indices, adjacent_cells=False)
        extract_cells = getattr(dataset, "extract_cells", None)
        return extract_cells(indices) if callable(extract_cells) else None

    @staticmethod
    def _combine_selection_datasets(datasets) -> Any | None:  # noqa: ANN001
        values = [value for value in datasets if value is not None]
        if not values:
            return None
        if len(values) == 1:
            return values[0]
        import pyvista as pv

        return pv.MultiBlock(values).combine(merge_points=False)

    @staticmethod
    def _selection_actor_kwargs(
        entity_kind: str,
        *,
        highlight: bool,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "name": (
                "__engineering_selection_highlight__"
                if highlight
                else "__engineering_selection_isolate__"
            ),
            "color": "#ffe066" if highlight else "#9ca3af",
            "pickable": False,
            "reset_camera": False,
            "render": False,
            "show_scalar_bar": False,
        }
        if entity_kind in {"cad_vertex", "fe_node"}:
            kwargs.update(
                {
                    "style": "points",
                    "point_size": 14 if highlight else 9,
                    "render_points_as_spheres": True,
                }
            )
        elif entity_kind == "cad_edge":
            kwargs["line_width"] = 5 if highlight else 3
        else:
            kwargs.update(
                {
                    "style": "surface",
                    "opacity": 0.45 if highlight else 1.0,
                    "show_edges": highlight,
                    "line_width": 2,
                    "smooth_shading": entity_kind.startswith("cad_"),
                    "lighting": True,
                }
            )
        return kwargs

    def _rebuild_selection_isolate(
        self,
        interactor: QWidget,
        state: _EngineeringWidgetState,
    ) -> bool:
        selected = self._selected_layer_datasets(state)
        add_mesh = getattr(interactor, "add_mesh", None)
        if not selected or not callable(add_mesh):
            return False
        self._remove_selection_isolate(interactor, state)
        dataset = self._combine_selection_datasets(selected.values())
        if dataset is None:
            return False
        entity_kind = state.selected_entities[0]["entity_kind"]
        state.selection_isolate_actor = add_mesh(
            dataset,
            **self._selection_actor_kwargs(entity_kind, highlight=False),
        )
        self._apply_clipping(state.selection_isolate_actor, state.current_options)
        state.selection_isolated = True
        self._sync_actor_visibility(state)
        return True

    @staticmethod
    def _combined_bounds(datasets) -> tuple[float, float, float, float, float, float] | None:  # noqa: ANN001
        result: list[float] | None = None
        for dataset in datasets:
            values = getattr(dataset, "bounds", None)
            if not isinstance(values, (list, tuple)) or len(values) != 6:
                continue
            try:
                bounds = [float(value) for value in values]
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(value) for value in bounds):
                continue
            if any(bounds[index] > bounds[index + 1] for index in (0, 2, 4)):
                continue
            if result is None:
                result = bounds
                continue
            result = [
                min(result[0], bounds[0]),
                max(result[1], bounds[1]),
                min(result[2], bounds[2]),
                max(result[3], bounds[3]),
                min(result[4], bounds[4]),
                max(result[5], bounds[5]),
            ]
        return tuple(result) if result is not None else None

    @classmethod
    def _sync_actor_visibility(cls, state: _EngineeringWidgetState) -> None:
        representation = cls._representation(state.current_options)
        for name, actor in state.actors.items():
            source_kind = _string(state.layers.get(name, {}).get("source_kind")).casefold()
            mode_visible = not (
                source_kind == "cad" and representation == "wireframe"
            )
            setter = getattr(actor, "SetVisibility", None)
            if callable(setter):
                setter(
                    1
                    if state.layer_visibility.get(name, True)
                    and not state.selection_isolated
                    and mode_visible
                    else 0
                )
        for name, actor in state.topology_actors.items():
            source_kind = _string(state.layers.get(name, {}).get("source_kind")).casefold()
            topology_visible = source_kind == "cad" and representation in {
                "surface_with_edges",
                "wireframe",
                "wireframe_visible_edges",
            }
            setter = getattr(actor, "SetVisibility", None)
            if callable(setter):
                setter(
                    1
                    if state.layer_visibility.get(name, True)
                    and not state.selection_isolated
                    and topology_visible
                    else 0
                )
        for source in state.selection_source_actors.values():
            setter = getattr(source.get("actor"), "SetVisibility", None)
            if callable(setter):
                setter(
                    1
                    if state.layer_visibility.get(source.get("layer_id"), True)
                    and not state.selection_isolated
                    else 0
                )
        isolate_setter = getattr(state.selection_isolate_actor, "SetVisibility", None)
        if callable(isolate_setter):
            isolate_setter(1 if state.selection_isolated else 0)

    def _replace_direct_color_actors(
        self,
        interactor: QWidget,
        state: _EngineeringWidgetState,
        options: Mapping[str, Any],
        *,
        attribute_colors_changed: bool,
    ) -> None:
        add_mesh = getattr(interactor, "add_mesh", None)
        remove_actor = getattr(interactor, "remove_actor", None)
        if not callable(add_mesh) or not callable(remove_actor):
            return
        old_styles = normalize_scene_styles(state.current_options.get("scene_styles", {}))
        new_styles = normalize_scene_styles(options.get("scene_styles", {}))
        for name, layer in state.layers.items():
            color_changed = old_styles.get(name, {}).get("color", "") != new_styles.get(name, {}).get("color", "")
            if color_changed or (attribute_colors_changed and self._attribute_colors_available(layer)):
                old_actor = state.actors.get(name)
                if old_actor is not None:
                    remove_actor(old_actor, render=False)
                actor = add_mesh(layer["dataset"], **self._mesh_kwargs(layer, options=options))
                self._apply_clipping(actor, options)
                state.actors[name] = actor
            topology = _mapping(layer.get("topological_edges"))
            if name in state.topology_actors and (
                color_changed or (attribute_colors_changed and self._attribute_colors_available(topology))
            ):
                remove_actor(state.topology_actors[name], render=False)
                actor = add_mesh(
                    layer["topological_edges_dataset"],
                    **self._topological_edge_kwargs(layer, options=options),
                )
                self._apply_clipping(actor, options)
                state.topology_actors[name] = actor

    def _replace_cad_surface_actors(
        self,
        interactor: QWidget,
        state: _EngineeringWidgetState,
        options: Mapping[str, Any],
    ) -> None:
        add_mesh = getattr(interactor, "add_mesh", None)
        remove_actor = getattr(interactor, "remove_actor", None)
        if not callable(add_mesh) or not callable(remove_actor):
            return
        for name, layer in state.layers.items():
            if _string(layer.get("source_kind")).casefold() != "cad":
                continue
            old_actor = state.actors.get(name)
            if old_actor is not None:
                remove_actor(old_actor, render=False)
            actor = add_mesh(layer["dataset"], **self._mesh_kwargs(layer, options=options))
            self._apply_clipping(actor, options)
            state.actors[name] = actor

    @staticmethod
    def _attribute_colors_available(value: Mapping[str, Any]) -> bool:
        return _coerce_bool(_mapping(value.get("attribute_colors")).get("available"))

    @staticmethod
    def _direct_color_kwargs(
        value: Mapping[str, Any],
        *,
        options: Mapping[str, Any],
        dataset: Any,
    ) -> dict[str, Any]:
        if not _coerce_bool(options.get(_SHOW_ATTRIBUTE_COLORS_OPTION)):
            return {}
        metadata = _mapping(value.get("attribute_colors"))
        if not _coerce_bool(metadata.get("available")):
            return {}
        array_name = _string(metadata.get("array_name"))
        association = _string(metadata.get("association", "cell")).casefold()
        try:
            component_count = int(metadata.get("component_count", 0) or 0)
        except (TypeError, ValueError):
            component_count = 0
        if not array_name or association not in {"point", "cell"} or component_count not in {3, 4}:
            raise ValueError("Model viewer attribute-color metadata is invalid.")
        if not EngineeringViewerWidgetBinder._all_dataset_leaves_have_array(
            dataset,
            association=association,
            array_name=array_name,
        ):
            raise ValueError(
                f"Model viewer attribute-color array is missing: {array_name}"
            )
        return {
            "scalars": array_name,
            "rgb": True,
            "preference": association,
            "show_scalar_bar": False,
        }

    @staticmethod
    def _all_dataset_leaves_have_array(
        dataset: Any,
        *,
        association: str,
        array_name: str,
    ) -> bool:
        try:
            import pyvista
        except ModuleNotFoundError:
            return False
        leaves: list[Any] = []

        def visit(value: Any) -> None:
            if isinstance(value, pyvista.MultiBlock):
                for child in value:
                    if child is not None:
                        visit(child)
                return
            leaves.append(value)

        visit(dataset)
        return bool(leaves) and all(
            array_name in getattr(leaf, f"{association}_data", {})
            for leaf in leaves
        )

    @classmethod
    def _topological_edge_kwargs(
        cls,
        layer: Mapping[str, Any],
        *,
        options: Mapping[str, Any],
    ) -> dict[str, Any]:
        topology = _mapping(layer.get("topological_edges"))
        dataset = layer.get("topological_edges_dataset")
        scene_style = normalize_scene_styles(options.get("scene_styles", {})).get(_string(layer.get("id")), {})
        color = _string(scene_style.get("color"))
        kwargs: dict[str, Any] = {
            "name": f"{_string(layer.get('id'))}::topological_edges",
            "color": color or _string(_mapping(layer.get("style")).get("edge_color")) or "#374151",
            "line_width": 2,
            "opacity": scene_style.get("opacity", 1.0),
            "pickable": False,
            "reset_camera": False,
            "render": False,
        }
        direct = {} if color else cls._direct_color_kwargs(topology, options=options, dataset=dataset)
        if direct:
            kwargs.pop("color", None)
            kwargs.update(direct)
        return kwargs

    @staticmethod
    def _sync_hidden_line_removal(
        interactor: QWidget,
        state: _EngineeringWidgetState,
        *,
        enabled: bool,
    ) -> None:
        if enabled == state.hidden_line_enabled:
            return
        method_name = "enable_hidden_line_removal" if enabled else "disable_hidden_line_removal"
        method = getattr(interactor, method_name, None)
        if not callable(method):
            if enabled:
                raise RuntimeError("Visible-edge wireframe is unavailable in this viewer runtime.")
            state.hidden_line_enabled = False
            return
        method()
        state.hidden_line_enabled = enabled

    def _sync_orientation_aids(
        self,
        interactor: QWidget,
        state: _EngineeringWidgetState,
        options: Mapping[str, Any],
    ) -> None:
        show_cube = _coerce_bool(options.get(_SHOW_VIEW_CUBE_OPTION), default=True)
        if show_cube and state.view_cube_widget is None:
            add_cube = getattr(interactor, "add_camera_orientation_widget", None)
            if callable(add_cube):
                state.view_cube_widget = add_cube()
                representation = getattr(state.view_cube_widget, "GetRepresentation", lambda: None)()
                anchor = getattr(representation, "AnchorToLowerLeft", None)
                if callable(anchor):
                    anchor()
        elif not show_cube and state.view_cube_widget is not None:
            self._remove_view_cube(interactor, state)

        show_triad = _coerce_bool(options.get(_SHOW_ORIENTATION_TRIAD_OPTION), default=True)
        if show_triad and state.orientation_triad_widget is None:
            add_axes = getattr(interactor, "add_axes", None)
            if callable(add_axes):
                state.orientation_triad_actor = add_axes(
                    interactive=False,
                    viewport=(0.82, 0.0, 1.0, 0.18),
                    x_color="#ef4444",
                    y_color="#22c55e",
                    z_color="#3b82f6",
                )
                pickable_off = getattr(state.orientation_triad_actor, "PickableOff", None)
                if callable(pickable_off):
                    pickable_off()
                renderer = getattr(interactor, "renderer", None)
                state.orientation_triad_widget = getattr(renderer, "axes_widget", None)
                self._install_orientation_triad_drag(interactor, state)
        elif not show_triad and state.orientation_triad_widget is not None:
            self._remove_orientation_triad(interactor, state)

        show_world_axes = _coerce_bool(options.get(_SHOW_WORLD_AXES_OPTION))
        if show_world_axes and not state.world_axes_actors:
            self._add_world_axes(interactor, state)
        for actor in state.world_axes_actors:
            setter = getattr(actor, "SetVisibility", None)
            if callable(setter):
                setter(1 if show_world_axes else 0)

    def _add_world_axes(self, interactor: QWidget, state: _EngineeringWidgetState) -> None:
        bounds = self._combined_bounds(
            layer.get("dataset") for layer in state.layers.values()
        )
        add_mesh = getattr(interactor, "add_mesh", None)
        if bounds is None or not callable(add_mesh):
            return
        import pyvista as pv

        span = max(abs(value) for value in bounds) or 1.0
        span *= 1.15
        colors = {"x": "#ef4444", "y": "#22c55e", "z": "#3b82f6"}
        for axis_index, axis_name in enumerate(("x", "y", "z")):
            points: list[tuple[float, float, float]] = []
            lines: list[int] = []
            segment_length = (2.0 * span) / 24.0
            for index in range(24):
                start = -span + index * segment_length
                end = start + segment_length * 0.58
                start_point = [0.0, 0.0, 0.0]
                end_point = [0.0, 0.0, 0.0]
                start_point[axis_index] = start
                end_point[axis_index] = end
                point_index = len(points)
                points.extend((tuple(start_point), tuple(end_point)))
                lines.extend((2, point_index, point_index + 1))
            dataset = pv.PolyData(points, lines=lines)
            actor = add_mesh(
                dataset,
                name=f"__engineering_world_axis__:{axis_name}",
                color=colors[axis_name],
                line_width=1,
                pickable=False,
                reset_camera=False,
                render=False,
            )
            set_use_bounds = getattr(actor, "SetUseBounds", None)
            if callable(set_use_bounds):
                set_use_bounds(0)
            state.world_axes_actors.append(actor)

    def _remove_orientation_aids(
        self,
        interactor: QWidget,
        state: _EngineeringWidgetState,
    ) -> None:
        self._remove_view_cube(interactor, state)
        self._remove_orientation_triad(interactor, state)
        remove_actor = getattr(interactor, "remove_actor", None)
        if callable(remove_actor):
            for actor in state.world_axes_actors:
                try:
                    remove_actor(actor, render=False)
                except (TypeError, RuntimeError):
                    pass
        state.world_axes_actors.clear()

    def _install_orientation_triad_drag(
        self,
        interactor: QWidget,
        state: _EngineeringWidgetState,
    ) -> None:
        target = getattr(interactor, "iren", None) or getattr(interactor, "interactor", None)
        if target is None or state.triad_drag_observers:
            return

        def press(*_args: Any) -> None:
            position = self._triad_event_position(target)
            size = self._triad_render_size(target)
            if position is None or size is None or not self._position_in_triad(position, size):
                return
            state.triad_drag_active = True
            state.triad_drag_last_position = position
            style = self._triad_interactor_style(target)
            state.triad_drag_style = style
            enabled_getter = getattr(style, "GetEnabled", None)
            state.triad_drag_style_was_enabled = (
                bool(enabled_getter()) if callable(enabled_getter) else True
            )
            self._set_interactor_style_enabled(style, False)

        def move(*_args: Any) -> None:
            if not state.triad_drag_active or state.triad_drag_last_position is None:
                return
            position = self._triad_event_position(target)
            if position is None:
                return
            previous_x, previous_y = state.triad_drag_last_position
            delta_x = position[0] - previous_x
            delta_y = position[1] - previous_y
            state.triad_drag_last_position = position
            if delta_x == 0 and delta_y == 0:
                return
            camera = getattr(interactor, "camera", None)
            if camera is None:
                renderer = getattr(interactor, "renderer", None)
                camera = getattr(renderer, "GetActiveCamera", lambda: None)()
            azimuth = getattr(camera, "Azimuth", None)
            elevation = getattr(camera, "Elevation", None)
            if not callable(azimuth) or not callable(elevation):
                return
            azimuth(-0.4 * float(delta_x))
            elevation(0.4 * float(delta_y))
            orthogonalize = getattr(camera, "OrthogonalizeViewUp", None)
            if callable(orthogonalize):
                orthogonalize()
            reset_clipping = getattr(interactor, "reset_camera_clipping_range", None)
            if callable(reset_clipping):
                reset_clipping()
            render = getattr(interactor, "render", None)
            if callable(render):
                render()

        def release(*_args: Any) -> None:
            self._finish_orientation_triad_drag(state)

        for event_name, callback in (
            ("LeftButtonPressEvent", press),
            ("MouseMoveEvent", move),
            ("LeftButtonReleaseEvent", release),
            ("LeaveEvent", release),
        ):
            observer_target, observer_id = self._add_triad_observer(
                target,
                event_name,
                callback,
            )
            if observer_id is not None:
                state.triad_drag_observers.append((observer_target, observer_id))

    @staticmethod
    def _add_triad_observer(target: Any, event_name: str, callback) -> tuple[Any, Any]:  # noqa: ANN001
        raw_interactor = getattr(target, "interactor", None)
        add_observer = getattr(raw_interactor, "AddObserver", None)
        if callable(add_observer):
            try:
                return raw_interactor, add_observer(event_name, callback, 1.0)
            except (TypeError, RuntimeError):
                pass
        add_observer = getattr(target, "add_observer", None)
        if not callable(add_observer):
            add_observer = getattr(target, "AddObserver", None)
        if not callable(add_observer):
            return target, None
        try:
            return target, add_observer(event_name, callback)
        except (TypeError, RuntimeError):
            return target, None

    @staticmethod
    def _triad_event_position(target: Any) -> tuple[int, int] | None:
        getter = getattr(target, "get_event_position", None)
        if not callable(getter):
            raw_interactor = getattr(target, "interactor", target)
            getter = getattr(raw_interactor, "GetEventPosition", None)
        if not callable(getter):
            return None
        try:
            x_value, y_value = getter()
            return int(x_value), int(y_value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _triad_render_size(target: Any) -> tuple[int, int] | None:
        raw_interactor = getattr(target, "interactor", target)
        render_window = getattr(raw_interactor, "GetRenderWindow", lambda: None)()
        getter = getattr(render_window, "GetSize", None)
        if not callable(getter):
            return None
        try:
            width, height = getter()
            return int(width), int(height)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _position_in_triad(position: tuple[int, int], size: tuple[int, int]) -> bool:
        x_value, y_value = position
        width, height = size
        return (
            width > 0
            and height > 0
            and 0.82 * width <= x_value <= width
            and 0 <= y_value <= 0.18 * height
        )

    @staticmethod
    def _position_in_view_cube(
        position: tuple[int, int],
        size: tuple[int, int],
    ) -> bool:
        x_value, y_value = position
        width, height = size
        return (
            width > 0
            and height > 0
            and 0 <= x_value <= 0.2 * width
            and 0 <= y_value <= 0.2 * height
        )

    @staticmethod
    def _triad_interactor_style(target: Any) -> Any:
        getter = getattr(target, "get_interactor_style", None)
        if callable(getter):
            return getter()
        raw_interactor = getattr(target, "interactor", target)
        return getattr(raw_interactor, "GetInteractorStyle", lambda: None)()

    @staticmethod
    def _set_interactor_style_enabled(style: Any, enabled: bool) -> None:
        setter = getattr(style, "SetEnabled", None)
        if callable(setter):
            setter(1 if enabled else 0)
            return
        method = getattr(style, "EnabledOn" if enabled else "EnabledOff", None)
        if callable(method):
            method()

    @classmethod
    def _finish_orientation_triad_drag(cls, state: _EngineeringWidgetState) -> None:
        if state.triad_drag_style is not None:
            cls._set_interactor_style_enabled(
                state.triad_drag_style,
                state.triad_drag_style_was_enabled,
            )
        state.triad_drag_active = False
        state.triad_drag_last_position = None
        state.triad_drag_style = None
        state.triad_drag_style_was_enabled = True

    @classmethod
    def _detach_orientation_triad_drag(cls, state: _EngineeringWidgetState) -> None:
        cls._finish_orientation_triad_drag(state)
        for target, observer_id in state.triad_drag_observers:
            remove_observer = getattr(target, "remove_observer", None)
            if not callable(remove_observer):
                remove_observer = getattr(target, "RemoveObserver", None)
            if callable(remove_observer):
                try:
                    remove_observer(observer_id)
                except (TypeError, RuntimeError):
                    pass
        state.triad_drag_observers.clear()

    @staticmethod
    def _remove_view_cube(interactor: QWidget, state: _EngineeringWidgetState) -> None:
        widget = state.view_cube_widget
        disable = getattr(widget, "Off", None)
        get_interactor = getattr(widget, "GetInteractor", None)
        can_disable = not callable(get_interactor) or get_interactor() is not None
        if can_disable and callable(disable):
            disable()
            detach = getattr(widget, "SetInteractor", None)
            if callable(detach):
                detach(None)
        # PyVista 0.47 stores widget collections directly on the plotter.
        widgets = getattr(interactor, "widgets", interactor)
        camera_widgets = getattr(widgets, "camera_widgets", None)
        if isinstance(camera_widgets, list) and widget in camera_widgets:
            camera_widgets.remove(widget)
        state.view_cube_widget = None

    @classmethod
    def _remove_orientation_triad(cls, interactor: QWidget, state: _EngineeringWidgetState) -> None:
        cls._detach_orientation_triad_drag(state)
        widget = state.orientation_triad_widget
        disable = getattr(widget, "EnabledOff", None) or getattr(widget, "Off", None)
        get_interactor = getattr(widget, "GetInteractor", None)
        can_disable = not callable(get_interactor) or get_interactor() is not None
        if can_disable and callable(disable):
            disable()
            detach = getattr(widget, "SetInteractor", None)
            if callable(detach):
                detach(None)
        renderer = getattr(interactor, "renderer", None)
        if renderer is not None and getattr(renderer, "axes_widget", None) is widget:
            renderer.axes_widget = None
            renderer.axes_actor = None
        state.orientation_triad_widget = None
        state.orientation_triad_actor = None

    @staticmethod
    def _actor_mapper(actor: Any) -> Any:
        mapper = getattr(actor, "mapper", None)
        if mapper is not None:
            return mapper
        getter = getattr(actor, "GetMapper", None)
        return getter() if callable(getter) else None

    @classmethod
    def _apply_clipping(cls, actor: Any, options: Mapping[str, Any]) -> None:
        mapper = cls._actor_mapper(actor)
        if mapper is None:
            return
        remove = getattr(mapper, "RemoveAllClippingPlanes", None)
        if callable(remove):
            remove()
        if not _coerce_bool(options.get("clip_enabled")):
            return
        axis = _string(options.get("clip_axis", "x")).casefold()
        normals = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
        normal = normals.get(axis, normals["x"])
        try:
            offset = float(options.get("clip_offset", 0.0) or 0.0)
        except (TypeError, ValueError):
            offset = 0.0
        try:
            from vtkmodules.vtkCommonDataModel import vtkPlane

            plane = vtkPlane()
            plane.SetNormal(*normal)
            plane.SetOrigin(*(component * offset for component in normal))
            add = getattr(mapper, "AddClippingPlane", None)
            if callable(add):
                add(plane)
        except (ImportError, RuntimeError, TypeError):
            return

    def _install_interaction_lod(
        self,
        interactor: QWidget,
        state: _EngineeringWidgetState,
    ) -> None:
        if not any(layer.get("interaction_dataset") is not None for layer in state.layers.values()):
            return
        observer_target = getattr(interactor, "iren", None) or getattr(interactor, "interactor", None)
        add_observer = getattr(observer_target, "add_observer", None)
        if not callable(add_observer):
            add_observer = getattr(observer_target, "AddObserver", None)
        if not callable(add_observer):
            return

        timer = QTimer(interactor)
        timer.setSingleShot(True)
        timer.setInterval(150)
        timer.timeout.connect(lambda: self._set_interaction_lod(interactor, state, coarse=False))
        state.lod_restore_timer = timer

        def interaction_started(*_args: Any) -> None:
            timer.stop()
            self._set_interaction_lod(interactor, state, coarse=True)

        def interaction_finished(*_args: Any) -> None:
            timer.start()

        for event_name, callback in (
            ("StartInteractionEvent", interaction_started),
            ("EndInteractionEvent", interaction_finished),
        ):
            try:
                observer_id = add_observer(event_name, callback)
            except (TypeError, RuntimeError):
                continue
            state.interaction_observers.append((observer_target, observer_id))

    def _set_interaction_lod(
        self,
        interactor: QWidget,
        state: _EngineeringWidgetState,
        *,
        coarse: bool,
    ) -> None:
        changed = False
        for name, actor in state.actors.items():
            layer = state.layers.get(name, {})
            dataset = layer.get("interaction_dataset") if coarse else layer.get("dataset")
            if dataset is None:
                continue
            mapper = self._actor_mapper(actor)
            setter = getattr(mapper, "SetInputData", None)
            if not callable(setter):
                continue
            setter(dataset)
            changed = True
        if changed:
            render = getattr(interactor, "render", None)
            if callable(render):
                render()

    @staticmethod
    def _detach_interaction_lod(state: _EngineeringWidgetState) -> None:
        timer = state.lod_restore_timer
        if timer is not None:
            timer.stop()
            timer.deleteLater()
            state.lod_restore_timer = None
        for target, observer_id in state.interaction_observers:
            remove = getattr(target, "remove_observer", None)
            if not callable(remove):
                remove = getattr(target, "RemoveObserver", None)
            if callable(remove):
                try:
                    remove(observer_id)
                except (TypeError, RuntimeError):
                    pass
        state.interaction_observers.clear()

    @staticmethod
    def _mesh_kwargs(layer: Mapping[str, Any], *, options: Mapping[str, Any]) -> dict[str, Any]:
        source_kind = _string(layer.get("source_kind")).casefold()
        style = _mapping(layer.get("style"))
        scene_style = normalize_scene_styles(options.get("scene_styles", {})).get(_string(layer.get("id")), {})
        representation_mode = EngineeringViewerWidgetBinder._representation(options, style=style)
        representation = representation_mode
        if source_kind == "cad" and representation in {
            "surface_with_edges",
            "wireframe",
            "wireframe_visible_edges",
        }:
            representation = "surface"
        elif representation in {"surface_with_edges", "wireframe_visible_edges"}:
            representation = "wireframe" if representation == "wireframe_visible_edges" else "surface"
        if representation_mode == "surface_with_edges":
            representation = "surface"
        if representation not in {"surface", "wireframe", "points"}:
            representation = "surface"

        show_edges = (
            source_kind != "cad"
            and
            representation == "surface"
            and _coerce_bool(options.get(_SHOW_MESH_EDGES_OPTION))
        )
        kwargs: dict[str, Any] = {
            "name": _string(layer.get("id")),
            "opacity": scene_style.get("opacity", 1.0),
            "pickable": True,
            "reset_camera": False,
            "render": False,
            "show_edges": show_edges,
            "style": representation,
            "lighting": representation == "surface",
        }
        if representation == "surface":
            smooth_shading = source_kind == "cad" or EngineeringViewerWidgetBinder._has_authored_normals(
                layer.get("dataset")
            )
            kwargs.update(
                {
                    "ambient": 0.18,
                    "diffuse": 0.78,
                    "specular": 0.22,
                    "specular_power": 32.0,
                    "smooth_shading": smooth_shading,
                }
            )
        color_override = _string(scene_style.get("color"))
        color = color_override or _string(style.get("color"))
        scalars = _string(style.get("scalars"))
        if color:
            kwargs["color"] = color
        if scalars and not color_override:
            kwargs["scalars"] = scalars
        cmap = _string(options.get("colormap", style.get("cmap")))
        if cmap:
            kwargs["cmap"] = cmap
        clim = style.get("clim")
        if _string(options.get("scalar_range_mode")).casefold() == "custom":
            try:
                clim = (
                    float(options.get("scalar_range_min")),
                    float(options.get("scalar_range_max")),
                )
            except (TypeError, ValueError):
                pass
        if isinstance(clim, (list, tuple)) and len(clim) == 2:
            kwargs["clim"] = tuple(clim)
        for key in ("line_width", "point_size"):
            if key in style:
                kwargs[key] = style[key]
        if "smooth_shading" in style:
            kwargs["smooth_shading"] = _coerce_bool(style.get("smooth_shading"))
        direct_colors = {} if color_override else EngineeringViewerWidgetBinder._direct_color_kwargs(
            layer,
            options=options,
            dataset=layer.get("dataset"),
        )
        if direct_colors:
            for key in ("color", "cmap", "clim"):
                kwargs.pop(key, None)
            kwargs.update(direct_colors)
        if source_kind == "cad" and representation_mode == "wireframe_visible_edges":
            for key in (
                "scalars",
                "cmap",
                "clim",
                "rgb",
                "preference",
                "show_scalar_bar",
            ):
                kwargs.pop(key, None)
            canvas = viewer_canvas_style(options.get(_VIEWER_BACKGROUND_OPTION))
            kwargs.update(
                {
                    "color": str(canvas["background_bottom"]),
                    "opacity": 1.0,
                    "lighting": False,
                    "smooth_shading": False,
                }
            )
        return kwargs

    @staticmethod
    def _has_authored_normals(dataset: Any) -> bool:
        point_data = getattr(dataset, "point_data", None)
        active_name = getattr(point_data, "active_normals_name", None)
        if _string(active_name):
            return True
        if isinstance(point_data, Mapping):
            return any(_string(name).casefold() == "normals" for name in point_data)
        return False

    @staticmethod
    def _apply_actor_material(actor_property: Any, kwargs: Mapping[str, Any]) -> None:
        lighting = bool(kwargs.get("lighting"))
        setter = getattr(actor_property, "SetLighting", None)
        if callable(setter):
            setter(1 if lighting else 0)
        for key, method_name in (
            ("ambient", "SetAmbient"),
            ("diffuse", "SetDiffuse"),
            ("specular", "SetSpecular"),
            ("specular_power", "SetSpecularPower"),
        ):
            setter = getattr(actor_property, method_name, None)
            if key in kwargs and callable(setter):
                setter(float(kwargs[key]))
        interpolation = (
            "SetInterpolationToPhong"
            if lighting and bool(kwargs.get("smooth_shading"))
            else "SetInterpolationToFlat"
        )
        setter = getattr(actor_property, interpolation, None)
        if callable(setter):
            setter()

    @staticmethod
    def _representation(
        options: Mapping[str, Any],
        *,
        style: Mapping[str, Any] | None = None,
    ) -> str:
        representation = _string(
            options.get("representation", _mapping(style).get("representation", "surface"))
        ).casefold()
        if representation not in {
            "surface",
            "surface_with_edges",
            "wireframe",
            "wireframe_visible_edges",
            "points",
        }:
            return "surface"
        return representation

    def _is_reusable_interactor(self, widget: QWidget | None) -> bool:
        if not isinstance(widget, QWidget):
            return False
        state = self._widget_state.get(widget)
        return (
            state is not None
            and state.backend_id == self.backend_id
            and callable(getattr(widget, "clear", None))
            and callable(getattr(widget, "add_mesh", None))
        )

    @staticmethod
    def _apply_canvas_background(
        widget: QWidget,
        background: str = "",
        *,
        flat: bool = False,
    ) -> None:
        set_background = getattr(widget, "set_background", None)
        if not callable(set_background):
            return
        style = viewer_canvas_style(background)
        top = style["background_bottom"] if flat else style["background_top"]
        try:
            set_background(str(style["background_bottom"]), top=str(top))
        except TypeError:
            set_background(str(style["background_bottom"]))

    @staticmethod
    def _apply_projection(widget: QWidget, options: Mapping[str, Any]) -> None:
        parallel = _coerce_bool(options.get("parallel_projection"))
        method_name = "enable_parallel_projection" if parallel else "disable_parallel_projection"
        setter = getattr(widget, method_name, None)
        if callable(setter):
            setter()

    @staticmethod
    def _qimage_from_screenshot(value: Any) -> QImage:
        if isinstance(value, QImage):
            return value.copy()
        shape = getattr(value, "shape", None)
        tobytes = getattr(value, "tobytes", None)
        if not isinstance(shape, (tuple, list)) or len(shape) < 2 or not callable(tobytes):
            return QImage()
        try:
            height, width = int(shape[0]), int(shape[1])
            channels = int(shape[2]) if len(shape) >= 3 else 1
            payload = tobytes()
        except (TypeError, ValueError):
            return QImage()
        formats = {
            1: (QImage.Format.Format_Grayscale8, width),
            3: (QImage.Format.Format_RGB888, width * 3),
            4: (QImage.Format.Format_RGBA8888, width * 4),
        }
        image_format, bytes_per_line = formats.get(channels, (None, 0))
        if image_format is None or width <= 0 or height <= 0 or len(payload) < bytes_per_line * height:
            return QImage()
        image = QImage(payload, width, height, bytes_per_line, image_format)
        return image.copy() if not image.isNull() else QImage()

    @staticmethod
    def _create_interactor(_container: QWidget | None) -> QWidget:
        from pyvistaqt import QtInteractor

        platform = os.environ.get("QT_QPA_PLATFORM", "").strip().casefold()
        return QtInteractor(
            parent=None,
            auto_update=False,
            off_screen=platform in {"minimal", "offscreen"},
        )

    @staticmethod
    def _create_picker(association: str) -> Any:
        if association == "point":
            from vtkmodules.vtkRenderingCore import vtkPointPicker

            picker = vtkPointPicker()
            picker.SetTolerance(0.01)
            return picker
        from vtkmodules.vtkRenderingCore import vtkCellPicker

        picker = vtkCellPicker()
        picker.SetTolerance(0.0005)
        return picker

    def _stored_tangent_selection_angle(self) -> float:
        return engineering_viewer_tangent_selection_angle(
            self._preferences_store.load_document()
        )

    @staticmethod
    def _load_dataset(display_path: str) -> Any:
        import pyvista as pv

        return pv.read(display_path)

    @staticmethod
    def _mark_native_window_overlay(widget: QWidget) -> None:
        # QOpenGLWidget-based interactors need a native surface before joining
        # the Qt Quick host, whose compositor can use a different graphics API.
        # Qt manages this boundary, including context lifetime during reparenting.
        widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        widget.setProperty(_NATIVE_WINDOW_OVERLAY_PROPERTY, True)


__all__ = ["EngineeringViewerWidgetBinder"]
