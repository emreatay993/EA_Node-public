from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from ea_node_editor.ui.shell.state import (
    ScopeCameraKey,
    ShellWindowSearchScopeState,
    normalize_graph_search_scope_id,
    normalize_graph_search_scopes,
)

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


class _SignalProtocol(Protocol):
    def emit(self) -> None: ...


class _ActionProtocol(Protocol):
    def isChecked(self) -> bool: ...

    def blockSignals(self, block: bool) -> bool: ...

    def setChecked(self, checked: bool) -> None: ...


class _SearchScopeHostProtocol(Protocol):
    state: Any
    graph_search_changed: _SignalProtocol
    graph_hint_changed: _SignalProtocol
    snap_to_grid_changed: _SignalProtocol
    graphics_preferences_changed: _SignalProtocol
    workspace_state_changed: _SignalProtocol
    action_snap_to_grid: _ActionProtocol
    app_preferences_controller: Any
    graph_hint_timer: Any
    model: Any
    scene: Any
    view: Any
    workspace_manager: Any
    workspace_navigation_controller: Any
    _GRAPH_SEARCH_LIMIT: int

    def request_close_graph_search(self) -> None: ...


class WindowSearchScopeController:
    def __init__(
        self,
        host: ShellWindow | _SearchScopeHostProtocol,
        state: ShellWindowSearchScopeState,
    ) -> None:
        self._host = host
        self._state = state

    def set_graph_search_state(
        self,
        *,
        open_: bool | None = None,
        query: str | None = None,
        enabled_scopes: list[str] | None = None,
        results: list[dict[str, Any]] | None = None,
        highlight_index: int | None = None,
    ) -> None:
        graph_search = self._state.graph_search
        changed = False
        if open_ is not None:
            normalized_open = bool(open_)
            if normalized_open != graph_search.open:
                graph_search.open = normalized_open
                changed = True
        if query is not None:
            normalized_query = str(query)
            if normalized_query != graph_search.query:
                graph_search.query = normalized_query
                changed = True
        if enabled_scopes is not None:
            normalized_scopes = normalize_graph_search_scopes(enabled_scopes)
            if normalized_scopes != graph_search.enabled_scopes:
                graph_search.enabled_scopes = normalized_scopes
                changed = True
        if results is not None:
            normalized_results = list(results)
            if normalized_results != graph_search.results:
                graph_search.results = normalized_results
                changed = True
        if highlight_index is not None:
            normalized_index = int(highlight_index)
            if normalized_index != graph_search.highlight_index:
                graph_search.highlight_index = normalized_index
                changed = True
        if changed:
            self._host.graph_search_changed.emit()

    def refresh_graph_search_results(self, query: str) -> None:
        graph_search = self._state.graph_search
        normalized_query = str(query).strip()
        if not normalized_query:
            self.set_graph_search_state(query="", results=[], highlight_index=-1)
            return
        ranked = self._host.workspace_navigation_controller.search_graph_nodes(
            normalized_query,
            limit=self._host._GRAPH_SEARCH_LIMIT,
            enabled_scopes=graph_search.enabled_scopes,
        )
        highlight = 0 if ranked else -1
        self.set_graph_search_state(query=normalized_query, results=ranked, highlight_index=highlight)

    def request_graph_search_move(self, delta: int) -> None:
        graph_search = self._state.graph_search
        if not graph_search.open or not graph_search.results:
            return
        step = 1 if int(delta) > 0 else -1 if int(delta) < 0 else 0
        if step == 0:
            return
        count = len(graph_search.results)
        current = graph_search.highlight_index
        if current < 0 or current >= count:
            next_index = 0 if step > 0 else count - 1
        else:
            next_index = max(0, min(count - 1, current + step))
        self.set_graph_search_state(highlight_index=next_index)

    def request_graph_search_highlight(self, index: int) -> None:
        graph_search = self._state.graph_search
        if not graph_search.open:
            return
        normalized = int(index)
        if normalized < 0 or normalized >= len(graph_search.results):
            return
        self.set_graph_search_state(highlight_index=normalized)

    def request_graph_search_accept(self) -> bool:
        graph_search = self._state.graph_search
        if not graph_search.open:
            return False
        if not graph_search.query.strip():
            return False
        if not graph_search.results:
            return False
        index = graph_search.highlight_index
        if index < 0 or index >= len(graph_search.results):
            index = 0
        result = graph_search.results[index]
        jumped = self._host.workspace_navigation_controller.jump_to_graph_node(
            result["workspace_id"], result["node_id"]
        )
        if jumped:
            self._host.request_close_graph_search()
        return bool(jumped)

    def request_graph_search_jump(self, index: int) -> bool:
        graph_search = self._state.graph_search
        normalized = int(index)
        if normalized < 0 or normalized >= len(graph_search.results):
            return False
        self.set_graph_search_state(highlight_index=normalized)
        return bool(self.request_graph_search_accept())

    def set_graph_search_scope_enabled(self, scope_id: str, enabled: bool) -> None:
        graph_search = self._state.graph_search
        normalized_scope_id = normalize_graph_search_scope_id(scope_id)
        if normalized_scope_id is None:
            return
        enabled_scopes = list(graph_search.enabled_scopes)
        if enabled:
            if normalized_scope_id in enabled_scopes:
                return
            enabled_scopes.append(normalized_scope_id)
            self.set_graph_search_state(enabled_scopes=enabled_scopes)
        else:
            if normalized_scope_id not in enabled_scopes or len(enabled_scopes) <= 1:
                return
            enabled_scopes = [scope for scope in enabled_scopes if scope != normalized_scope_id]
            self.set_graph_search_state(enabled_scopes=enabled_scopes)
        self.refresh_graph_search_results(graph_search.query)

    def active_scope_camera_key(
        self,
        scope_path: tuple[str, ...] | None = None,
    ) -> ScopeCameraKey | None:
        workspace_id = self._host.workspace_manager.active_workspace_id()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if workspace is None:
            return None
        workspace.ensure_default_view()
        view_id = workspace.active_view_id
        if not view_id:
            return None
        if scope_path is None:
            scope_path = tuple(str(value) for value in self._host.scene.active_scope_path)
        return workspace_id, view_id, tuple(scope_path)

    def remember_scope_camera(self, scope_path: tuple[str, ...] | None = None) -> None:
        key = self.active_scope_camera_key(scope_path)
        if key is None:
            return
        center = self._host.view.mapToScene(self._host.view.viewport().rect().center())
        self._state.runtime_scope_camera[key] = (
            float(self._host.view.zoom),
            float(center.x()),
            float(center.y()),
        )

    def restore_scope_camera(self, scope_path: tuple[str, ...] | None = None) -> bool:
        key = self.active_scope_camera_key(scope_path)
        if key is None:
            return False
        state = self._state.runtime_scope_camera.get(key)
        if state is None:
            return False
        zoom, pan_x, pan_y = state
        self._host.view.set_zoom(max(0.1, min(3.0, float(zoom))))
        self._host.view.centerOn(float(pan_x), float(pan_y))
        return True

    def discard_scope_camera_for_view(self, workspace_id: str, view_id: str) -> None:
        normalized_workspace_id = str(workspace_id or "").strip()
        normalized_view_id = str(view_id or "").strip()
        if not normalized_workspace_id or not normalized_view_id:
            return
        stale_scope_keys = [
            key
            for key in self._state.runtime_scope_camera
            if key[0] == normalized_workspace_id and key[1] == normalized_view_id
        ]
        for key in stale_scope_keys:
            del self._state.runtime_scope_camera[key]

    def navigate_scope(self, navigate_fn: Callable[[], bool]) -> bool:
        self.remember_scope_camera()
        changed = bool(navigate_fn())
        if not changed:
            return False
        if not self.restore_scope_camera():
            self._host.workspace_navigation_controller.frame_all()
        self._host.workspace_state_changed.emit()
        return True

    def set_snap_to_grid_enabled(self, enabled: bool, *, persist: bool = True) -> None:
        normalized = bool(enabled)
        if self._state.snap_to_grid_enabled == normalized:
            self._sync_snap_action(normalized)
            return
        self._state.snap_to_grid_enabled = normalized
        self._sync_snap_action(normalized)
        self._host.snap_to_grid_changed.emit()
        if persist:
            self._persist_graphics_updates(
                {
                    "interaction": {
                        "snap_to_grid": normalized,
                    },
                },
            )

    def set_graphics_minimap_expanded(self, expanded: bool, *, persist: bool = True) -> None:
        normalized = bool(expanded)
        if self._state.graphics_minimap_expanded == normalized:
            return
        self._state.graphics_minimap_expanded = normalized
        self._host.graphics_preferences_changed.emit()
        if persist:
            self._persist_graphics_updates(
                {
                    "canvas": {
                        "minimap_expanded": normalized,
                    },
                },
            )

    def show_graph_hint(self, message: str, timeout_ms: int = 3600) -> None:
        normalized = str(message).strip()
        if not normalized:
            self.clear_graph_hint()
            return
        self._state.graph_hint_message = normalized
        self._host.graph_hint_changed.emit()
        timer = getattr(self._host, "graph_hint_timer", None)
        if timer is None:
            return
        timeout_value = max(250, int(timeout_ms))
        timer.start(timeout_value)

    def clear_graph_hint(self) -> None:
        timer = getattr(self._host, "graph_hint_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
        if not self._state.graph_hint_message:
            return
        self._state.graph_hint_message = ""
        self._host.graph_hint_changed.emit()

    def _persist_graphics_updates(self, updates: dict[str, Any]) -> None:
        self._host.app_preferences_controller.update_graphics_settings(updates)

    def _sync_snap_action(self, enabled: bool) -> None:
        if self._host.action_snap_to_grid.isChecked() == enabled:
            return
        blocked = self._host.action_snap_to_grid.blockSignals(True)
        self._host.action_snap_to_grid.setChecked(enabled)
        self._host.action_snap_to_grid.blockSignals(blocked)
