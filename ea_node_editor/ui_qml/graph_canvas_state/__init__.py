from __future__ import annotations

"""Graph-canvas state bridge package.

The QML-facing ``GraphCanvasStateBridge`` is composed from per-domain
plain-Python projection mixins; this composition root owns ONLY construction
and source resolution. A new canvas fact for QML is one ``@pyqtProperty`` in
the matching ``*_props`` module; viewport-virtualization logic lives in
``visible_scene_service.py``.
"""

from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import QObject, pyqtProperty

from ea_node_editor.ui_qml.bridge_runtime import connect_signal as _connect_signal
from ea_node_editor.ui_qml.graph_canvas_state.execution_state_props import (
    ExecutionStateProps,
    _lookup_node_ids,
)
from ea_node_editor.ui_qml.graph_canvas_state.graphics_preferences_props import (
    GraphicsPreferencesProps,
)
from ea_node_editor.ui_qml.graph_canvas_state.protocols import (
    _GraphCanvasExecutionSource,
    _GraphCanvasGraphicsSource,
    _GraphCanvasProjectSource,
    _GraphCanvasSceneStateSource,
    _GraphCanvasScenePolicySource,
)
from ea_node_editor.ui_qml.graph_canvas_state.scene_models_props import (
    SceneModelsProps,
    _MINIMAP_EMPTY_BOUNDS_PAYLOAD,
    _locked_node_status_summary,
)
from ea_node_editor.ui_qml.graph_canvas_state.view_state_props import ViewStateProps
from ea_node_editor.ui_qml.graph_canvas_state.visible_scene_service import (
    VisibleSceneModelOps,
)
from ea_node_editor.ui_qml.graph_canvas_viewport_index import (
    GraphCanvasViewportIndex,
    SceneRect,
)
from ea_node_editor.ui_qml.graph_canvas_visible_model import GraphCanvasVisibleModel

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
    from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge


def _resolve_scene_state_source(scene_bridge: object | None) -> _GraphCanvasSceneStateSource | None:
    if scene_bridge is None:
        return None
    return cast(
        _GraphCanvasSceneStateSource,
        getattr(scene_bridge, "state_bridge", scene_bridge),
    )


def _resolve_scene_policy_source(scene_bridge: object | None) -> _GraphCanvasScenePolicySource | None:
    if scene_bridge is None:
        return None
    return cast(
        _GraphCanvasScenePolicySource,
        getattr(scene_bridge, "policy_bridge", scene_bridge),
    )


class GraphCanvasStateBridge(
    GraphicsPreferencesProps,
    ExecutionStateProps,
    SceneModelsProps,
    ViewStateProps,
    VisibleSceneModelOps,
    QObject,
):
    def __init__(
        self,
        parent: QObject | None = None,
        *,
        session_state: object | None = None,
        snap_to_grid_changed_signal: object | None = None,
        snap_grid_size: float = 20.0,
        app_preferences_source: object | None = None,
        graphics_source: _GraphCanvasGraphicsSource | None = None,
        execution_source: _GraphCanvasExecutionSource | None = None,
        project_source: _GraphCanvasProjectSource | None = None,
        scene_bridge: "GraphSceneBridge | None" = None,
        view_bridge: "ViewportBridge | None" = None,
    ) -> None:
        super().__init__(parent)
        self._scene_bridge = scene_bridge
        self._view_bridge = view_bridge
        self._session_state = session_state
        self._snap_to_grid_changed_signal = snap_to_grid_changed_signal
        self._snap_grid_size = float(snap_grid_size)
        self._app_preferences_source = app_preferences_source
        self._graphics_source = graphics_source
        self._execution_source = execution_source
        self._project_source = project_source
        self._scene_state_source = _resolve_scene_state_source(scene_bridge)
        self._scene_policy_source = _resolve_scene_policy_source(scene_bridge)
        self._node_model_revision = 0
        self._visible_node_index = GraphCanvasViewportIndex()
        self._visible_backdrop_index = GraphCanvasViewportIndex()
        self._visible_nodes_model = GraphCanvasVisibleModel(self)
        self._visible_badge_nodes_model = GraphCanvasVisibleModel(self)
        self._visible_backdrop_nodes_model = GraphCanvasVisibleModel(self)
        self._visible_scene_models_dirty = True
        self._visible_scene_models_deferred = False
        self._visible_scene_query_rect: SceneRect | None = None
        self._pending_visible_scene_query_rect: SceneRect | None = None
        self._visible_scene_view_refresh_pending = False
        self._visible_scene_model_deferred_refresh_count = 0
        self._visible_scene_model_skipped_view_change_count = 0
        self._visible_scene_model_exact_refresh_count = 0
        self._visible_scene_model_delta_update_count = 0
        self._visible_scene_model_delta_fallback_count = 0
        self._visible_scene_model_delta_row_update_count = 0
        self._visible_scene_model_duplicate_count = 0
        self._visible_scene_model_duplicate_last_ids: tuple[str, ...] = ()
        self._visible_scene_model_duplicate_resync_count = 0
        self._visible_model_duplicate_resync_pending = False
        self._visible_model_active_node_ids: set[str] = set()
        self._visible_selection_node_ids = _lookup_node_ids(
            getattr(self._scene_state_source, "selected_node_lookup", {})
        )
        self._minimap_nodes_model_cache: list[dict[str, Any]] = []
        self._minimap_node_index_by_id: dict[str, int] = {}
        self._workspace_scene_bounds_payload_cache: dict[str, float] = dict(_MINIMAP_EMPTY_BOUNDS_PAYLOAD)
        self._minimap_scene_model_dirty = True
        self._minimap_scene_model_notify_pending = False
        self._edge_endpoint_nodes_model_cache: list[dict[str, Any]] = []
        self._edge_endpoint_node_index_by_id: dict[str, int] = {}
        self._edge_endpoint_nodes_model_dirty = True
        self._locked_node_status_summary_cache = _locked_node_status_summary([])
        self._locked_node_status_summary_dirty = True
        self._locked_node_status_notify_pending = False

        _connect_signal(
            self._graphics_source,
            "graphics_preferences_changed",
            self._handle_graphics_preferences_changed,
        )
        connect_snap = getattr(snap_to_grid_changed_signal, "connect", None)
        if callable(connect_snap):
            connect_snap(self.snap_to_grid_changed.emit)
        _connect_signal(self._scene_state_source, "nodes_changed", self._handle_scene_nodes_changed)
        _connect_signal(self._scene_state_source, "nodes_changed", self.port_flow_state_changed.emit)
        _connect_signal(self._scene_state_source, "edges_changed", self.scene_edges_changed.emit)
        _connect_signal(self._scene_state_source, "edges_changed", self.port_flow_state_changed.emit)
        _connect_signal(self._scene_state_source, "selection_changed", self.scene_selection_changed.emit)
        _connect_signal(self._scene_state_source, "selection_changed", self._handle_scene_selection_changed)
        _connect_signal(self._scene_state_source, "workspace_changed", self._handle_scene_workspace_changed)
        _connect_signal(self._scene_state_source, "workspace_changed", self.port_flow_state_changed.emit)
        _connect_signal(execution_source, "run_failure_changed", self.failure_highlight_changed.emit)
        _connect_signal(execution_source, "run_failure_changed", self._invalidate_visible_scene_models)
        _connect_signal(execution_source, "node_execution_state_changed", self.node_execution_state_changed.emit)
        _connect_signal(execution_source, "node_execution_state_changed", self.port_flow_state_changed.emit)
        _connect_signal(execution_source, "node_execution_state_changed", self._invalidate_visible_scene_models)
        _connect_signal(view_bridge, "view_state_changed", self.view_state_changed.emit)
        _connect_signal(view_bridge, "view_state_changed", self._handle_view_state_changed)
        self._visible_nodes_model.duplicate_node_ids_detected.connect(
            self._handle_visible_model_duplicate_node_ids
        )
        self._visible_backdrop_nodes_model.duplicate_node_ids_detected.connect(
            self._handle_visible_model_duplicate_node_ids
        )

    @property
    def execution_source(self) -> _GraphCanvasExecutionSource | None:
        return self._execution_source

    @property
    def graphics_source(self) -> _GraphCanvasGraphicsSource | None:
        return self._graphics_source

    @property
    def project_source(self) -> _GraphCanvasProjectSource | None:
        return self._project_source

    @property
    def scene_bridge(self) -> "GraphSceneBridge | None":
        return self._scene_bridge

    @property
    def scene_state_source(self) -> _GraphCanvasSceneStateSource | None:
        return self._scene_state_source

    @property
    def scene_policy_source(self) -> _GraphCanvasScenePolicySource | None:
        return self._scene_policy_source

    @property
    def view_bridge(self) -> "ViewportBridge | None":
        return self._view_bridge

    @pyqtProperty(QObject, constant=True)
    def viewport_bridge(self) -> "ViewportBridge | None":
        return self._view_bridge


__all__ = [
    "GraphCanvasStateBridge",
]
