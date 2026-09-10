from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import pyqtSlot

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow

_UNSET = object()


class ShellWindowLibraryOverlayStateMixin:
    def _set_graph_search_state(
        self: "ShellWindow",
        *,
        open_: bool | None = None,
        query: str | None = None,
        enabled_scopes: list[str] | None = None,
        results: list[dict[str, Any]] | None = None,
        highlight_index: int | None = None,
    ) -> None:
        self.shell_library_presenter._set_graph_search_state(
            open_=open_,
            query=query,
            enabled_scopes=enabled_scopes,
            results=results,
            highlight_index=highlight_index,
        )

    def _refresh_graph_search_results(self: "ShellWindow", query: str) -> None:
        self.shell_library_presenter._refresh_graph_search_results(query)

    def _set_connection_quick_insert_state(
        self: "ShellWindow",
        *,
        open_: bool | None = None,
        query: str | None = None,
        results: list[dict[str, Any]] | None = None,
        highlight_index: int | None = None,
        context: dict[str, Any] | None | object = _UNSET,
    ) -> None:
        self.shell_library_presenter._set_connection_quick_insert_state(
            open_=open_,
            query=query,
            results=results,
            highlight_index=highlight_index,
            context=context,
        )

    def _connection_quick_insert_context_for_port(
        self: "ShellWindow",
        node_id: str,
        port_key: str,
    ) -> dict[str, Any] | None:
        return self.shell_library_presenter._connection_quick_insert_context_for_port(node_id, port_key)

    def _refresh_connection_quick_insert_results(self: "ShellWindow", query: str) -> None:
        self.shell_library_presenter._refresh_connection_quick_insert_results(query)

    @pyqtSlot(str)
    def set_library_query(self: "ShellWindow", query: str) -> None:
        self.shell_library_presenter.set_library_query(query)

    @pyqtSlot(str)
    def set_library_category(self: "ShellWindow", category: str) -> None:
        self.shell_library_presenter.set_library_category(category)

    @pyqtSlot(str)
    def set_library_data_type(self: "ShellWindow", data_type: str) -> None:
        self.shell_library_presenter.set_library_data_type(data_type)

    @pyqtSlot(str)
    def set_library_direction(self: "ShellWindow", direction: str) -> None:
        self.shell_library_presenter.set_library_direction(direction)

    @pyqtSlot(str)
    @pyqtSlot(str, int)
    def show_graph_hint(self: "ShellWindow", message: str, timeout_ms: int = 3600) -> None:
        self.shell_library_presenter.show_graph_hint(message, timeout_ms)

    @pyqtSlot()
    def clear_graph_hint(self: "ShellWindow") -> None:
        self.shell_library_presenter.clear_graph_hint()

    @pyqtSlot()
    def request_open_graph_search(self: "ShellWindow") -> None:
        self.shell_library_presenter.request_open_graph_search()

    @pyqtSlot()
    def request_close_graph_search(self: "ShellWindow") -> None:
        self.shell_library_presenter.request_close_graph_search()

    @pyqtSlot(str, str, float, float, float, float, result=bool)
    def request_open_connection_quick_insert(
        self: "ShellWindow",
        node_id: str,
        port_key: str,
        scene_x: float,
        scene_y: float,
        overlay_x: float,
        overlay_y: float,
    ) -> bool:
        return bool(
            self.shell_library_presenter.request_open_connection_quick_insert(
                node_id,
                port_key,
                scene_x,
                scene_y,
                overlay_x,
                overlay_y,
            )
        )

    @pyqtSlot(float, float, float, float)
    def request_open_canvas_quick_insert(
        self: "ShellWindow",
        scene_x: float,
        scene_y: float,
        overlay_x: float,
        overlay_y: float,
    ) -> None:
        self.shell_library_presenter.request_open_canvas_quick_insert(
            scene_x,
            scene_y,
            overlay_x,
            overlay_y,
        )

    @pyqtSlot()
    def request_close_connection_quick_insert(self: "ShellWindow") -> None:
        self.shell_library_presenter.request_close_connection_quick_insert()

    @pyqtSlot(str)
    def set_connection_quick_insert_query(self: "ShellWindow", query: str) -> None:
        self.shell_library_presenter.set_connection_quick_insert_query(query)

    @pyqtSlot(int)
    def request_connection_quick_insert_move(self: "ShellWindow", delta: int) -> None:
        self.shell_library_presenter.request_connection_quick_insert_move(delta)

    @pyqtSlot(int)
    def request_connection_quick_insert_highlight(self: "ShellWindow", index: int) -> None:
        self.shell_library_presenter.request_connection_quick_insert_highlight(index)

    @pyqtSlot(result=bool)
    def request_connection_quick_insert_accept(self: "ShellWindow") -> bool:
        return bool(self.shell_library_presenter.request_connection_quick_insert_accept())

    @pyqtSlot(int, result=bool)
    def request_connection_quick_insert_choose(self: "ShellWindow", index: int) -> bool:
        return bool(self.shell_library_presenter.request_connection_quick_insert_choose(index))

    @pyqtSlot(str)
    def set_graph_search_query(self: "ShellWindow", query: str) -> None:
        self.shell_library_presenter.set_graph_search_query(query)

    @pyqtSlot(str, bool)
    def set_graph_search_scope_enabled(self: "ShellWindow", scope_id: str, enabled: bool) -> None:
        self.shell_library_presenter.set_graph_search_scope_enabled(scope_id, enabled)

    @pyqtSlot(int)
    def request_graph_search_move(self: "ShellWindow", delta: int) -> None:
        self.shell_library_presenter.request_graph_search_move(delta)

    @pyqtSlot(int)
    def request_graph_search_highlight(self: "ShellWindow", index: int) -> None:
        self.shell_library_presenter.request_graph_search_highlight(index)

    @pyqtSlot(result=bool)
    def request_graph_search_accept(self: "ShellWindow") -> bool:
        return bool(self.shell_library_presenter.request_graph_search_accept())

    @pyqtSlot(int, result=bool)
    def request_graph_search_jump(self: "ShellWindow", index: int) -> bool:
        return bool(self.shell_library_presenter.request_graph_search_jump(index))

    @pyqtSlot(str)
    def request_add_node_from_library(self: "ShellWindow", type_id: str) -> None:
        self.shell_library_presenter.request_add_node_from_library(type_id)

    @pyqtSlot(result=bool)
    def request_publish_custom_workflow_from_selected(self: "ShellWindow") -> bool:
        return bool(self.shell_library_presenter.request_publish_custom_workflow_from_selected())

    @pyqtSlot(result=bool)
    def request_publish_custom_workflow_from_scope(self: "ShellWindow") -> bool:
        return bool(self.shell_library_presenter.request_publish_custom_workflow_from_scope())

    @pyqtSlot(str, result=bool)
    def request_publish_custom_workflow_from_node(self: "ShellWindow", node_id: str) -> bool:
        return bool(self.shell_library_presenter.request_publish_custom_workflow_from_node(node_id))

    @pyqtSlot(str, result=bool)
    @pyqtSlot(str, str, result=bool)
    def request_delete_custom_workflow_from_library(
        self: "ShellWindow",
        workflow_id: str,
        workflow_scope: str = "",
    ) -> bool:
        return bool(
            self.shell_library_presenter.request_delete_custom_workflow_from_library(
                workflow_id,
                workflow_scope,
            )
        )

    @pyqtSlot(str, result=bool)
    @pyqtSlot(str, str, result=bool)
    def request_rename_custom_workflow_from_library(
        self: "ShellWindow",
        workflow_id: str,
        workflow_scope: str = "",
    ) -> bool:
        return bool(
            self.shell_library_presenter.request_rename_custom_workflow_from_library(
                workflow_id,
                workflow_scope,
            )
        )

    @pyqtSlot(str, str, result=bool)
    def request_set_custom_workflow_scope(
        self: "ShellWindow",
        workflow_id: str,
        workflow_scope: str,
    ) -> bool:
        return bool(self.shell_library_presenter.request_set_custom_workflow_scope(workflow_id, workflow_scope))

    @pyqtSlot(str, float, float, str, str, str, str, bool, result=bool)
    def request_drop_node_from_library(
        self: "ShellWindow",
        type_id: str,
        scene_x: float,
        scene_y: float,
        target_mode: str,
        target_node_id: str,
        target_port_key: str,
        target_edge_id: str,
        append_requested: bool = False,
    ) -> bool:
        result = self.workspace_drop_connect_controller.request_drop_node_from_library(
            type_id,
            scene_x,
            scene_y,
            target_mode,
            target_node_id,
            target_port_key,
            target_edge_id,
            append_requested,
        )
        return bool(result.payload)


__all__ = [
    "ShellWindowLibraryOverlayStateMixin",
]
