from __future__ import annotations

from typing import Any, Protocol

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from ea_node_editor.common.number_slider_query import (
    number_slider_query_payload as _number_slider_query_payload,
    parse_number_slider_query as _parse_number_slider_query,
)
from ea_node_editor.common.protocols import SignalLike as _SignalLike


class _ShellLibrarySource(Protocol):
    node_library_changed: _SignalLike
    library_pane_reset_requested: _SignalLike
    graph_search_changed: _SignalLike
    connection_quick_insert_changed: _SignalLike
    graph_hint_changed: _SignalLike
    grouped_node_library_items: list[dict[str, Any]]
    display_node_library_items: list[dict[str, Any]]
    browser_library_items: list[dict[str, Any]]
    frequent_node_library_items: list[dict[str, Any]]
    library_category_options: list[dict[str, Any]]
    passive_node_library_display_mode: str
    graph_search_open: bool
    graph_search_query: str
    graph_search_enabled_scopes: list[str]
    graph_search_results: list[dict[str, Any]]
    graph_search_highlight_index: int
    connection_quick_insert_open: bool
    connection_quick_insert_overlay_x: float
    connection_quick_insert_overlay_y: float
    connection_quick_insert_scene_x: float
    connection_quick_insert_scene_y: float
    connection_quick_insert_source_summary: str
    connection_quick_insert_is_canvas_mode: bool
    connection_quick_insert_query: str
    connection_quick_insert_results: list[dict[str, Any]]
    connection_quick_insert_highlight_index: int
    graph_hint_visible: bool
    graph_hint_message: str

    def set_library_query(self, query: str) -> None: ...

    def request_add_node_from_library(self, type_id: str) -> None: ...

    def request_add_node_from_library_with_properties(self, type_id: str, properties: dict[str, Any]) -> bool: ...

    def request_rename_custom_workflow_from_library(
        self,
        workflow_id: str,
        workflow_scope: str,
    ) -> bool: ...

    def request_set_custom_workflow_scope(self, workflow_id: str, workflow_scope: str) -> bool: ...

    def request_delete_custom_workflow_from_library(
        self,
        workflow_id: str,
        workflow_scope: str,
    ) -> bool: ...

    def set_graph_search_query(self, query: str) -> None: ...

    def set_graph_search_scope_enabled(self, scope_id: str, enabled: bool) -> None: ...

    def request_graph_search_move(self, delta: int) -> None: ...

    def request_graph_search_accept(self) -> bool: ...

    def request_close_graph_search(self) -> None: ...

    def request_graph_search_highlight(self, index: int) -> None: ...

    def request_graph_search_jump(self, index: int) -> bool: ...

    def set_connection_quick_insert_query(self, query: str) -> None: ...

    def request_connection_quick_insert_move(self, delta: int) -> None: ...

    def request_connection_quick_insert_accept(self) -> bool: ...

    def request_close_connection_quick_insert(self) -> None: ...

    def request_connection_quick_insert_highlight(self, index: int) -> None: ...

    def request_connection_quick_insert_choose(self, index: int) -> bool: ...


def _copy_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _require_library_source(library_source: _ShellLibrarySource | None) -> _ShellLibrarySource:
    if library_source is None:
        raise TypeError("ShellLibraryBridge requires an explicit library source contract.")
    return library_source


class ShellLibraryBridge(QObject):
    node_library_changed = pyqtSignal()
    library_pane_reset_requested = pyqtSignal(name="libraryPaneResetRequested")
    graph_search_changed = pyqtSignal()
    connection_quick_insert_changed = pyqtSignal()
    graph_hint_changed = pyqtSignal()
    node_browser_requested = pyqtSignal(str, float, float)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        shell_window: object | None = None,
        library_source: _ShellLibrarySource | None = None,
    ) -> None:
        super().__init__(parent)
        _ = shell_window
        self._library_source = _require_library_source(library_source)

        self._library_source.node_library_changed.connect(self.node_library_changed.emit)
        self._library_source.library_pane_reset_requested.connect(self.library_pane_reset_requested.emit)
        self._library_source.graph_search_changed.connect(self.graph_search_changed.emit)
        self._library_source.connection_quick_insert_changed.connect(self.connection_quick_insert_changed.emit)
        self._library_source.graph_hint_changed.connect(self.graph_hint_changed.emit)

    @property
    def shell_window(self) -> None:
        return None

    @property
    def library_source(self) -> _ShellLibrarySource:
        return self._library_source

    @pyqtProperty("QVariantList", notify=node_library_changed)
    def grouped_node_library_items(self) -> list[dict[str, Any]]:
        return _copy_list(self._library_source.grouped_node_library_items)

    @pyqtProperty("QVariantList", notify=node_library_changed)
    def display_node_library_items(self) -> list[dict[str, Any]]:
        return _copy_list(self._library_source.display_node_library_items)

    @pyqtProperty("QVariantList", notify=node_library_changed)
    def browser_library_items(self) -> list[dict[str, Any]]:
        return _copy_list(self._library_source.browser_library_items)

    @pyqtProperty("QVariantList", notify=connection_quick_insert_changed)
    def frequent_node_library_items(self) -> list[dict[str, Any]]:
        return _copy_list(self._library_source.frequent_node_library_items)

    @pyqtProperty("QVariantList", notify=node_library_changed)
    def library_category_options(self) -> list[dict[str, Any]]:
        return _copy_list(self._library_source.library_category_options)

    @pyqtProperty(str, notify=node_library_changed)
    def passive_node_library_display_mode(self) -> str:
        return str(self._library_source.passive_node_library_display_mode)

    @pyqtProperty(bool, notify=graph_search_changed)
    def graph_search_open(self) -> bool:
        return bool(self._library_source.graph_search_open)

    @pyqtProperty(str, notify=graph_search_changed)
    def graph_search_query(self) -> str:
        return str(self._library_source.graph_search_query)

    @pyqtProperty("QVariantList", notify=graph_search_changed)
    def graph_search_enabled_scopes(self) -> list[str]:
        return _copy_list(self._library_source.graph_search_enabled_scopes)

    @pyqtProperty("QVariantList", notify=graph_search_changed)
    def graph_search_results(self) -> list[dict[str, Any]]:
        return _copy_list(self._library_source.graph_search_results)

    @pyqtProperty(int, notify=graph_search_changed)
    def graph_search_highlight_index(self) -> int:
        return int(self._library_source.graph_search_highlight_index)

    @pyqtProperty(bool, notify=connection_quick_insert_changed)
    def connection_quick_insert_open(self) -> bool:
        return bool(self._library_source.connection_quick_insert_open)

    @pyqtProperty(float, notify=connection_quick_insert_changed)
    def connection_quick_insert_overlay_x(self) -> float:
        return float(self._library_source.connection_quick_insert_overlay_x)

    @pyqtProperty(float, notify=connection_quick_insert_changed)
    def connection_quick_insert_overlay_y(self) -> float:
        return float(self._library_source.connection_quick_insert_overlay_y)

    @pyqtProperty(float, notify=connection_quick_insert_changed)
    def connection_quick_insert_scene_x(self) -> float:
        return float(self._library_source.connection_quick_insert_scene_x)

    @pyqtProperty(float, notify=connection_quick_insert_changed)
    def connection_quick_insert_scene_y(self) -> float:
        return float(self._library_source.connection_quick_insert_scene_y)

    @pyqtProperty(str, notify=connection_quick_insert_changed)
    def connection_quick_insert_source_summary(self) -> str:
        return str(self._library_source.connection_quick_insert_source_summary)

    @pyqtProperty(bool, notify=connection_quick_insert_changed)
    def connection_quick_insert_is_canvas_mode(self) -> bool:
        return bool(self._library_source.connection_quick_insert_is_canvas_mode)

    @pyqtProperty(str, notify=connection_quick_insert_changed)
    def connection_quick_insert_query(self) -> str:
        return str(self._library_source.connection_quick_insert_query)

    @pyqtProperty("QVariantList", notify=connection_quick_insert_changed)
    def connection_quick_insert_results(self) -> list[dict[str, Any]]:
        return _copy_list(self._library_source.connection_quick_insert_results)

    @pyqtProperty(int, notify=connection_quick_insert_changed)
    def connection_quick_insert_highlight_index(self) -> int:
        return int(self._library_source.connection_quick_insert_highlight_index)

    @pyqtProperty(bool, notify=graph_hint_changed)
    def graph_hint_visible(self) -> bool:
        return bool(self._library_source.graph_hint_visible)

    @pyqtProperty(str, notify=graph_hint_changed)
    def graph_hint_message(self) -> str:
        return str(self._library_source.graph_hint_message)

    @pyqtSlot(str)
    def set_library_query(self, query: str) -> None:
        self._library_source.set_library_query(query)

    @pyqtSlot(str)
    def request_add_node_from_library(self, type_id: str) -> None:
        self._library_source.request_add_node_from_library(type_id)

    @pyqtSlot()
    @pyqtSlot(str, float, float)
    def request_open_node_browser(
        self,
        initial_query: str = "",
        scene_x: float = float("nan"),
        scene_y: float = float("nan"),
    ) -> None:
        self._library_source.request_close_connection_quick_insert()
        self.node_browser_requested.emit(str(initial_query), float(scene_x), float(scene_y))

    @pyqtSlot(str, "QVariantMap", result=bool)
    def request_add_node_from_library_with_properties(self, type_id: str, properties: dict[str, Any]) -> bool:
        return bool(
            self._library_source.request_add_node_from_library_with_properties(type_id, dict(properties))
        )

    @pyqtSlot(str, result="QVariantMap")
    def parse_number_slider_query(self, query: str) -> dict[str, Any]:
        return dict(_number_slider_query_payload(_parse_number_slider_query(query)))

    @pyqtSlot(str, str, result=bool)
    def request_rename_custom_workflow_from_library(self, workflow_id: str, workflow_scope: str) -> bool:
        return bool(
            self._library_source.request_rename_custom_workflow_from_library(
                workflow_id,
                workflow_scope,
            )
        )

    @pyqtSlot(str, str, result=bool)
    def request_set_custom_workflow_scope(self, workflow_id: str, workflow_scope: str) -> bool:
        return bool(self._library_source.request_set_custom_workflow_scope(workflow_id, workflow_scope))

    @pyqtSlot(str, str, result=bool)
    def request_delete_custom_workflow_from_library(self, workflow_id: str, workflow_scope: str) -> bool:
        return bool(
            self._library_source.request_delete_custom_workflow_from_library(
                workflow_id,
                workflow_scope,
            )
        )

    @pyqtSlot(str)
    def set_graph_search_query(self, query: str) -> None:
        self._library_source.set_graph_search_query(query)

    @pyqtSlot(str, bool)
    def set_graph_search_scope_enabled(self, scope_id: str, enabled: bool) -> None:
        self._library_source.set_graph_search_scope_enabled(scope_id, enabled)

    @pyqtSlot(int)
    def request_graph_search_move(self, delta: int) -> None:
        self._library_source.request_graph_search_move(delta)

    @pyqtSlot(result=bool)
    def request_graph_search_accept(self) -> bool:
        return bool(self._library_source.request_graph_search_accept())

    @pyqtSlot()
    def request_close_graph_search(self) -> None:
        self._library_source.request_close_graph_search()

    @pyqtSlot(int)
    def request_graph_search_highlight(self, index: int) -> None:
        self._library_source.request_graph_search_highlight(index)

    @pyqtSlot(int, result=bool)
    def request_graph_search_jump(self, index: int) -> bool:
        return bool(self._library_source.request_graph_search_jump(index))

    @pyqtSlot(str)
    def set_connection_quick_insert_query(self, query: str) -> None:
        self._library_source.set_connection_quick_insert_query(query)

    @pyqtSlot(int)
    def request_connection_quick_insert_move(self, delta: int) -> None:
        self._library_source.request_connection_quick_insert_move(delta)

    @pyqtSlot(result=bool)
    def request_connection_quick_insert_accept(self) -> bool:
        return bool(self._library_source.request_connection_quick_insert_accept())

    @pyqtSlot()
    def request_close_connection_quick_insert(self) -> None:
        self._library_source.request_close_connection_quick_insert()

    @pyqtSlot(int)
    def request_connection_quick_insert_highlight(self, index: int) -> None:
        self._library_source.request_connection_quick_insert_highlight(index)

    @pyqtSlot(int, result=bool)
    def request_connection_quick_insert_choose(self, index: int) -> bool:
        return bool(self._library_source.request_connection_quick_insert_choose(index))


__all__ = ["ShellLibraryBridge"]
