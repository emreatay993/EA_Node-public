from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from ea_node_editor.app_preferences import normalize_passive_node_library_display_mode
from ea_node_editor.settings import DEFAULT_GRAPHICS_SETTINGS
from ea_node_editor.ui.shell.state import GRAPH_SEARCH_SCOPE_IDS
from ea_node_editor.ui.shell.library_projection import (
    build_combined_library_items,
    build_filtered_library_items,
    build_library_category_tree,
    build_library_category_options,
    build_library_data_type_options,
    build_library_direction_options,
    build_registry_library_items,
    library_item_matches_filters,
    project_display_library_items,
    project_grouped_library_items,
    rank_node_library_usage,
)
from ea_node_editor.ui.support.node_presentation import build_data_type_ui_projection

from .contracts import _ShellLibraryPresenterHostProtocol, _presenter_parent
from .state import (
    UNSET,
    build_connection_quick_insert_context,
    build_connection_quick_insert_results,
    connection_quick_insert_is_canvas_mode,
    connection_quick_insert_overlay_coordinate,
    connection_quick_insert_source_summary,
    update_connection_quick_insert_state,
)


class ShellLibraryPresenter(QObject):
    node_library_changed = pyqtSignal()
    library_pane_reset_requested = pyqtSignal(name="libraryPaneResetRequested")
    graph_search_changed = pyqtSignal()
    connection_quick_insert_changed = pyqtSignal()
    graph_hint_changed = pyqtSignal()

    def __init__(
        self,
        host: _ShellLibraryPresenterHostProtocol,
        *,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(_presenter_parent(host, parent))
        self._host = host
        self._registry_cache_owner: Any | None = None
        self._registry_cache_fingerprint = ""
        self._registry_items_cache: list[dict[str, Any]] | None = None
        self._data_type_projection_cache: dict[str, Any] | None = None
        self._custom_workflow_items_cache: list[dict[str, Any]] | None = None
        self._combined_items_cache: list[dict[str, Any]] | None = None
        self._filtered_items_cache: list[dict[str, Any]] | None = None
        self._category_tree_cache: dict[str, Any] | None = None
        self._grouped_items_cache: list[dict[str, Any]] | None = None
        self._display_items_cache: list[dict[str, Any]] | None = None
        self._display_items_cache_mode = ""
        self._category_options_cache: list[dict[str, Any]] | None = None
        self._data_type_options_cache: list[dict[str, str]] | None = None
        self._preserve_projection_caches = False
        host.node_library_changed.connect(self._on_node_library_changed)
        host.library_pane_reset_requested.connect(self.library_pane_reset_requested.emit)
        host.graph_search_changed.connect(self.graph_search_changed.emit)
        host.connection_quick_insert_changed.connect(self.connection_quick_insert_changed.emit)
        host.graph_hint_changed.connect(self.graph_hint_changed.emit)
        scene = getattr(host, "scene", None)
        if scene is not None:
            scene.nodes_changed.connect(self._on_connection_graph_changed)
            scene.workspace_changed.connect(self.request_close_connection_quick_insert)
            scene.scope_changed.connect(self.request_close_connection_quick_insert)

    def _on_connection_graph_changed(self) -> None:
        quick_insert = self._connection_quick_insert()
        if quick_insert.open:
            self._refresh_connection_quick_insert_results(quick_insert.query, preserve_selection=True)

    def _invalidate_filtered_items(self) -> None:
        self._filtered_items_cache = None
        self._category_tree_cache = None
        self._grouped_items_cache = None
        self._display_items_cache = None
        self._display_items_cache_mode = ""

    def _invalidate_combined_items(self) -> None:
        self._combined_items_cache = None
        self._category_options_cache = None
        self._data_type_options_cache = None
        self._invalidate_filtered_items()

    def _invalidate_custom_workflow_items(self) -> None:
        self._custom_workflow_items_cache = None
        self._invalidate_combined_items()

    def _invalidate_registry_items(self) -> None:
        self._registry_cache_owner = None
        self._registry_cache_fingerprint = ""
        self._registry_items_cache = None
        self._data_type_projection_cache = None
        self._invalidate_combined_items()

    def _on_node_library_changed(self) -> None:
        if self._registry_cache_owner is not None and self._registry_cache_owner is not self._host.registry:
            self._invalidate_registry_items()
        if not self._preserve_projection_caches:
            self._invalidate_custom_workflow_items()
        self.node_library_changed.emit()
        if getattr(self._host, "search_scope_state", None) is not None:
            self._on_connection_graph_changed()

    def _emit_filter_changed(self) -> None:
        self._invalidate_filtered_items()
        self._preserve_projection_caches = True
        try:
            self._host.node_library_changed.emit()
        finally:
            self._preserve_projection_caches = False

    def _ensure_registry_items(self) -> None:
        registry = self._host.registry
        fingerprint = registry.contract_fingerprint()
        if self._registry_cache_owner is registry and self._registry_cache_fingerprint == fingerprint and self._registry_items_cache is not None:
            return
        specs = registry.all_specs()
        data_type_projection = build_data_type_ui_projection(registry.data_types)
        items = build_registry_library_items(
            registry_specs=specs,
            data_types=registry.data_types,
            data_type_projection=data_type_projection,
        )
        self._invalidate_registry_items()
        self._registry_cache_owner = registry
        self._registry_cache_fingerprint = fingerprint
        self._registry_items_cache = items
        self._data_type_projection_cache = data_type_projection

    def _registry_library_items(self) -> list[dict[str, Any]]:
        self._ensure_registry_items()
        return list(self._registry_items_cache or ())

    def _custom_workflow_library_items(self) -> list[dict[str, Any]]:
        if self._custom_workflow_items_cache is None:
            self._custom_workflow_items_cache = (
                self._host.workflow_library_controller.custom_workflow_library_items()
            )
        return list(self._custom_workflow_items_cache)

    def _combined_library_items(self) -> list[dict[str, Any]]:
        self._ensure_registry_items()
        if self._combined_items_cache is None:
            self._combined_items_cache = build_combined_library_items(
                registry_items=self._registry_items_cache or (),
                custom_workflow_items=self._custom_workflow_library_items(),
                data_type_projection=self._data_type_projection_cache,
            )
        return list(self._combined_items_cache)

    def _graph_search(self): return self._host.search_scope_state.graph_search
    def _connection_quick_insert(self): return self._host.search_scope_state.connection_quick_insert
    def _connection_quick_insert_context(self) -> dict[str, Any]: return self._connection_quick_insert().context or {}

    @staticmethod
    def _library_item_matches_filters(
        item: dict[str, Any],
        *,
        query: str,
        category: str,
        data_type: str,
        direction: str,
    ) -> bool:
        return library_item_matches_filters(
            item,
            query=query,
            category=category,
            data_type=data_type,
            direction=direction,
        )

    @property
    def filtered_node_library_items(self) -> list[dict[str, Any]]:
        if self._filtered_items_cache is None:
            self._filtered_items_cache = build_filtered_library_items(
                combined_items=self._combined_library_items(),
                query=self._host.library_filter_state.library_query,
                category=self._host.library_filter_state.library_category,
                data_type=self._host.library_filter_state.library_data_type,
                direction=self._host.library_filter_state.library_direction,
            )
        return list(self._filtered_items_cache)

    @property
    def grouped_node_library_items(self) -> list[dict[str, Any]]:
        if self._grouped_items_cache is None:
            self._grouped_items_cache = project_grouped_library_items(
                category_tree=self._library_category_tree()
            )
        return list(self._grouped_items_cache)

    @property
    def browser_library_items(self) -> list[dict[str, Any]]:
        return self._combined_library_items()

    @property
    def frequent_node_library_items(self) -> list[dict[str, Any]]:
        controller = getattr(self._host, "app_preferences_controller", None)
        usage_reader = getattr(controller, "node_library_usage", None)
        usage = usage_reader() if callable(usage_reader) else []
        return rank_node_library_usage(
            combined_items=self._combined_library_items(),
            usage=usage,
        )

    @property
    def passive_node_library_display_mode(self) -> str:
        return normalize_passive_node_library_display_mode(
            getattr(
                getattr(self._host, "workspace_ui_state", None),
                "passive_node_library_display_mode",
                DEFAULT_GRAPHICS_SETTINGS["shell"]["passive_node_library_display_mode"],
            )
        )

    @property
    def display_node_library_items(self) -> list[dict[str, Any]]:
        display_mode = self.passive_node_library_display_mode
        if (
            self._display_items_cache is None
            or self._display_items_cache_mode != display_mode
        ):
            self._display_items_cache = project_display_library_items(
                category_tree=self._library_category_tree(),
                passive_node_library_display_mode=display_mode,
            )
            self._display_items_cache_mode = display_mode
        return list(self._display_items_cache)

    def _library_category_tree(self) -> dict[str, Any]:
        if self._category_tree_cache is None:
            self._category_tree_cache = build_library_category_tree(
                self.filtered_node_library_items
            )
        return self._category_tree_cache

    @property
    def library_category_options(self) -> list[dict[str, Any]]:
        self._ensure_registry_items()
        if self._category_options_cache is None:
            self._category_options_cache = build_library_category_options(
                combined_items=self._combined_library_items(),
            )
        return list(self._category_options_cache)

    @property
    def library_direction_options(self) -> list[dict[str, str]]: return build_library_direction_options()

    @property
    def library_data_type_options(self) -> list[dict[str, str]]:
        self._ensure_registry_items()
        if self._data_type_options_cache is None:
            self._data_type_options_cache = build_library_data_type_options(
                combined_items=self._combined_library_items(),
            )
        return list(self._data_type_options_cache)

    @property
    def graph_search_open(self) -> bool: return bool(self._graph_search().open)

    @property
    def graph_search_query(self) -> str: return self._graph_search().query

    @property
    def graph_search_enabled_scopes(self) -> list[str]: return list(self._graph_search().enabled_scopes)

    @property
    def graph_search_results(self) -> list[dict[str, Any]]: return list(self._graph_search().results)

    @property
    def graph_search_highlight_index(self) -> int: return int(self._graph_search().highlight_index)

    @property
    def connection_quick_insert_open(self) -> bool: return bool(self._connection_quick_insert().open)

    @property
    def connection_quick_insert_query(self) -> str: return str(self._connection_quick_insert().query)

    @property
    def connection_quick_insert_results(self) -> list[dict[str, Any]]:
        return list(self._connection_quick_insert().results)

    @property
    def connection_quick_insert_highlight_index(self) -> int:
        return int(self._connection_quick_insert().highlight_index)

    @property
    def connection_quick_insert_overlay_x(self) -> float:
        return connection_quick_insert_overlay_coordinate(self._connection_quick_insert_context(), "overlay_x")

    @property
    def connection_quick_insert_overlay_y(self) -> float:
        return connection_quick_insert_overlay_coordinate(self._connection_quick_insert_context(), "overlay_y")

    @property
    def connection_quick_insert_scene_x(self) -> float:
        return connection_quick_insert_overlay_coordinate(self._connection_quick_insert_context(), "scene_x")

    @property
    def connection_quick_insert_scene_y(self) -> float:
        return connection_quick_insert_overlay_coordinate(self._connection_quick_insert_context(), "scene_y")

    @property
    def connection_quick_insert_source_summary(self) -> str:
        return connection_quick_insert_source_summary(self._connection_quick_insert_context())

    @property
    def connection_quick_insert_is_canvas_mode(self) -> bool:
        return connection_quick_insert_is_canvas_mode(self._connection_quick_insert_context())

    @property
    def graph_hint_message(self) -> str: return str(self._host.search_scope_state.graph_hint_message)

    @property
    def graph_hint_visible(self) -> bool: return bool(self._host.search_scope_state.graph_hint_message.strip())

    @property
    def can_publish_custom_workflow_from_scope(self) -> bool: return bool(self._host.scene.active_scope_path)

    def set_library_query(self, query: str) -> None:
        normalized = str(query).strip()
        if normalized == self._host.library_filter_state.library_query:
            return
        self._host.library_filter_state.library_query = normalized
        self._emit_filter_changed()

    def set_library_category(self, category: str) -> None:
        normalized = str(category).strip()
        if normalized == self._host.library_filter_state.library_category:
            return
        self._host.library_filter_state.library_category = normalized
        self._emit_filter_changed()

    def set_library_data_type(self, data_type: str) -> None:
        normalized = str(data_type).strip()
        if normalized == self._host.library_filter_state.library_data_type:
            return
        self._host.library_filter_state.library_data_type = normalized
        self._emit_filter_changed()

    def set_library_direction(self, direction: str) -> None:
        normalized = str(direction).strip().lower()
        if normalized not in {"", "in", "out"}:
            normalized = ""
        if normalized == self._host.library_filter_state.library_direction:
            return
        self._host.library_filter_state.library_direction = normalized
        self._emit_filter_changed()

    def _set_graph_search_state(
        self,
        *,
        open_: bool | None = None,
        query: str | None = None,
        enabled_scopes: list[str] | None = None,
        results: list[dict[str, Any]] | None = None,
        highlight_index: int | None = None,
    ) -> None:
        self._host.search_scope_controller.set_graph_search_state(
            open_=open_,
            query=query,
            enabled_scopes=enabled_scopes,
            results=results,
            highlight_index=highlight_index,
        )

    def _refresh_graph_search_results(self, query: str) -> None:
        self._host.search_scope_controller.refresh_graph_search_results(query)

    def _set_connection_quick_insert_state(
        self,
        *,
        open_: bool | None = None,
        query: str | None = None,
        results: list[dict[str, Any]] | None = None,
        highlight_index: int | None = None,
        context: dict[str, Any] | None | object = UNSET,
    ) -> None:
        if update_connection_quick_insert_state(
            self._connection_quick_insert(),
            open_=open_,
            query=query,
            results=results,
            highlight_index=highlight_index,
            context=context,
        ):
            self._host.connection_quick_insert_changed.emit()

    def _connection_quick_insert_context_for_port(self, node_id: str, port_key: str) -> dict[str, Any] | None:
        return build_connection_quick_insert_context(self._host, node_id, port_key)

    def _refresh_connection_quick_insert_results(self, query: str, *, preserve_selection: bool = False) -> None:
        quick_insert = self._connection_quick_insert()
        previous_item = (quick_insert.results[quick_insert.highlight_index]
                         if 0 <= quick_insert.highlight_index < len(quick_insert.results) else None)
        context = quick_insert.context
        if context is not None and not connection_quick_insert_is_canvas_mode(context):
            live_context = self._connection_quick_insert_context_for_port(context["node_id"], context["port_key"])
            if live_context is None:
                self.request_close_connection_quick_insert()
                return
            self._set_connection_quick_insert_state(context={**context, **live_context})
        if quick_insert.context is None:
            self._set_connection_quick_insert_state(query=str(query), results=[], highlight_index=-1)
            return
        results, highlight_index = build_connection_quick_insert_results(
            self._host,
            self._combined_library_items(),
            query,
            quick_insert,
        )
        if preserve_selection:
            previous_ports = {port["key"] for port in previous_item.get("compatible_ports", ())} if previous_item else set()
            highlight_index = next((index for index, item in enumerate(results)
                if previous_item is not None and item.get("type_id") == previous_item.get("type_id")
                and previous_ports == {port["key"] for port in item.get("compatible_ports", ())}), -1)
        self._set_connection_quick_insert_state(
            query=str(query),
            results=results,
            highlight_index=highlight_index,
        )

    def request_open_graph_search(self) -> None:
        self._set_connection_quick_insert_state(open_=False, query="", results=[], highlight_index=-1, context=None)
        self._set_graph_search_state(
            open_=True,
            query="",
            enabled_scopes=list(GRAPH_SEARCH_SCOPE_IDS),
            results=[],
            highlight_index=-1,
        )

    def request_close_graph_search(self) -> None:
        self._set_graph_search_state(
            open_=False,
            query="",
            enabled_scopes=list(GRAPH_SEARCH_SCOPE_IDS),
            results=[],
            highlight_index=-1,
        )

    def set_graph_search_query(self, query: str) -> None:
        if self.graph_search_open:
            self._refresh_graph_search_results(query)

    def set_graph_search_scope_enabled(self, scope_id: str, enabled: bool) -> None:
        if self.graph_search_open:
            self._host.search_scope_controller.set_graph_search_scope_enabled(scope_id, enabled)

    def request_graph_search_move(self, delta: int) -> None:
        self._host.search_scope_controller.request_graph_search_move(delta)

    def request_graph_search_highlight(self, index: int) -> None:
        self._host.search_scope_controller.request_graph_search_highlight(index)

    def request_graph_search_accept(self) -> bool:
        return bool(self._host.search_scope_controller.request_graph_search_accept())

    def request_graph_search_jump(self, index: int) -> bool:
        return bool(self._host.search_scope_controller.request_graph_search_jump(index))

    def request_open_connection_quick_insert(
        self,
        node_id: str,
        port_key: str,
        scene_x: float,
        scene_y: float,
        overlay_x: float,
        overlay_y: float,
        append_requested: bool = False,
    ) -> bool:
        context = self._connection_quick_insert_context_for_port(node_id, port_key)
        if context is None:
            return False
        context["scene_x"] = float(scene_x)
        context["scene_y"] = float(scene_y)
        context["overlay_x"] = float(overlay_x)
        context["overlay_y"] = float(overlay_y)
        context["append_requested"] = bool(append_requested)
        self._set_graph_search_state(
            open_=False,
            query="",
            enabled_scopes=list(GRAPH_SEARCH_SCOPE_IDS),
            results=[],
            highlight_index=-1,
        )
        self._set_connection_quick_insert_state(open_=True, query="", results=[], highlight_index=-1, context=context)
        self._refresh_connection_quick_insert_results("")
        return True

    def request_open_canvas_quick_insert(
        self,
        scene_x: float,
        scene_y: float,
        overlay_x: float,
        overlay_y: float,
    ) -> None:
        context = {
            "mode": "canvas_insert",
            "scene_x": float(scene_x),
            "scene_y": float(scene_y),
            "overlay_x": float(overlay_x),
            "overlay_y": float(overlay_y),
        }
        self._set_graph_search_state(
            open_=False,
            query="",
            enabled_scopes=list(GRAPH_SEARCH_SCOPE_IDS),
            results=[],
            highlight_index=-1,
        )
        self._set_connection_quick_insert_state(open_=True, query="", results=[], highlight_index=-1, context=context)
        self._refresh_connection_quick_insert_results("")

    def request_close_connection_quick_insert(self) -> None:
        self._set_connection_quick_insert_state(open_=False, query="", results=[], highlight_index=-1, context=None)

    def set_connection_quick_insert_query(self, query: str) -> None:
        if self.connection_quick_insert_open:
            self._refresh_connection_quick_insert_results(query)

    def request_connection_quick_insert_move(self, delta: int) -> None:
        quick_insert = self._connection_quick_insert()
        if not quick_insert.open or not quick_insert.results:
            return
        current = 0 if quick_insert.highlight_index < 0 else quick_insert.highlight_index
        next_index = max(0, min(len(quick_insert.results) - 1, current + int(delta)))
        self._set_connection_quick_insert_state(highlight_index=next_index)

    def request_connection_quick_insert_highlight(self, index: int) -> None:
        quick_insert = self._connection_quick_insert()
        if quick_insert.open and 0 <= index < len(quick_insert.results):
            self._set_connection_quick_insert_state(highlight_index=int(index))

    def request_connection_quick_insert_accept(self) -> bool:
        quick_insert = self._connection_quick_insert()
        if not quick_insert.open or not quick_insert.results:
            return False
        return self.request_connection_quick_insert_choose(quick_insert.highlight_index)

    def request_connection_quick_insert_choose(self, index: int) -> bool:
        quick_insert = self._connection_quick_insert()
        if index < 0 or index >= len(quick_insert.results):
            return False
        context = quick_insert.context
        if context is None:
            return False
        selected_item = quick_insert.results[index]
        if not connection_quick_insert_is_canvas_mode(context):
            selected_type_id = selected_item.get("type_id")
            selected_port_keys = {port["key"] for port in selected_item.get("compatible_ports", ())}
            self._refresh_connection_quick_insert_results(quick_insert.query)
            context = quick_insert.context
            if context is None:
                return False
            live_item = next((item for item in quick_insert.results if item.get("type_id") == selected_type_id), None)
            if live_item is None:
                return False
            ports = [port for port in live_item.get("compatible_ports", ()) if port["key"] in selected_port_keys]
            if not ports:
                return False
            selected_item = {**live_item, "compatible_ports": ports}
        scene_x = float(context.get("scene_x", 0.0))
        scene_y = float(context.get("scene_y", 0.0))
        if connection_quick_insert_is_canvas_mode(context):
            created = self._host.workspace_drop_connect_controller.request_drop_node_from_library(
                str(selected_item.get("type_id", "")),
                scene_x,
                scene_y,
                "",
                "",
                "",
                "",
            ).payload
        else:
            offset = self._host._CONNECTION_QUICK_INSERT_OFFSET
            scene_x += -offset if str(context.get("direction", "")).strip().lower() == "in" else offset
            created = self._host.workspace_drop_connect_controller.request_drop_node_from_library(
                str(selected_item.get("type_id", "")),
                scene_x,
                scene_y,
                "port",
                str(context.get("node_id", "")),
                str(context.get("port_key", "")),
                "",
                bool(context.get("append_requested", False)),
                compatible_port_keys=tuple(
                    str(port["key"])
                    for port in selected_item.get("compatible_ports", ())
                ),
            ).payload
        self.request_close_connection_quick_insert()
        return bool(created)

    def show_graph_hint(self, message: str, timeout_ms: int = 3600) -> None: self._host.search_scope_controller.show_graph_hint(message, timeout_ms)
    def clear_graph_hint(self) -> None: self._host.search_scope_controller.clear_graph_hint()
    def request_add_node_from_library(self, type_id: str) -> None: self._host.workspace_drop_connect_controller.add_node_from_library(type_id)
    def request_add_node_from_library_with_properties(self, type_id: str, properties: dict[str, Any]) -> bool:
        return bool(self._host.workspace_drop_connect_controller.add_node_from_library_with_properties(type_id, properties))

    def request_publish_custom_workflow_from_selected(self) -> bool:
        result = self._host.workflow_library_controller.publish_custom_workflow_from_selected_subnode()
        return bool(result.payload)

    def request_publish_custom_workflow_from_scope(self) -> bool:
        result = self._host.workflow_library_controller.publish_custom_workflow_from_current_scope()
        return bool(result.payload)

    def request_publish_custom_workflow_from_node(self, node_id: str) -> bool:
        result = self._host.workflow_library_controller.publish_custom_workflow_from_node(node_id)
        return bool(result.payload)

    def request_delete_custom_workflow_from_library(self, workflow_id: str, workflow_scope: str) -> bool:
        result = self._host.workflow_library_controller.delete_custom_workflow(workflow_id, workflow_scope)
        return bool(result.payload)

    def request_rename_custom_workflow_from_library(self, workflow_id: str, workflow_scope: str) -> bool:
        result = self._host.workflow_library_controller.rename_custom_workflow(workflow_id, workflow_scope)
        return bool(result.payload)

    def request_set_custom_workflow_scope(self, workflow_id: str, workflow_scope: str) -> bool:
        result = self._host.workflow_library_controller.set_custom_workflow_scope(workflow_id, workflow_scope)
        return bool(result.payload)


__all__ = ["ShellLibraryPresenter"]
