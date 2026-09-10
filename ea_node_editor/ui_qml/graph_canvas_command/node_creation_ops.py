from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import pyqtSlot

from ea_node_editor.ui_qml.bridge_runtime import (
    invoke as _invoke,
)

if TYPE_CHECKING:
    pass

class NodeCreationOps:
    """Node creation: library drops, path-pointer/folder-explorer nodes, quick insert, port connect."""

    @pyqtSlot(str, str, bool, result=bool)
    def request_update_path_pointer_node(
        self,
        node_id: str,
        path_or_url: str,
        is_folder: bool,
    ) -> bool:
        normalized_node_id = str(node_id or "").strip()
        path = self._path_from_url_or_path(path_or_url)
        if not normalized_node_id or not path:
            return False
        command_source = self._scene_command_source
        bulk_setter = getattr(command_source, "set_node_properties", None) if command_source is not None else None
        if not callable(bulk_setter):
            return False
        mode = "folder" if Path(path).is_dir() or bool(is_folder) else "file"
        return bool(bulk_setter(normalized_node_id, {"path": path, "mode": mode}))

    @pyqtSlot(str, bool, float, float, result="QVariantMap")
    def request_create_path_pointer_node(
        self,
        path_or_url: str,
        is_folder: bool,
        scene_x: float,
        scene_y: float,
    ) -> dict[str, Any]:
        path = self._path_from_url_or_path(path_or_url)
        if not path:
            return {
                "success": False,
                "path": "",
                "created_node_id": "",
                "created_type_id": "",
                "mode": "folder" if bool(is_folder) else "file",
                "error": {
                    "code": "missing_path",
                    "message": "A file or folder path is required.",
                },
            }
        path_obj = Path(path)
        mode = "folder" if path_obj.is_dir() or bool(is_folder) else "file"
        node_id = self._add_path_pointer_node(path, mode, float(scene_x), float(scene_y))
        if not node_id:
            return {
                "success": False,
                "path": path,
                "created_node_id": "",
                "created_type_id": "io.path_pointer",
                "mode": mode,
                "error": {
                    "code": "mutation_unavailable",
                    "message": "Graph scene command bridge cannot create an io.path_pointer node.",
                },
            }
        return {
            "success": True,
            "path": path,
            "created_node_id": node_id,
            "created_type_id": "io.path_pointer",
            "mode": mode,
            "error": {},
        }

    @pyqtSlot("QVariantList", str, str, float, float, result=bool)
    def request_canvas_import_drop(self, urls, text: str, html: str, scene_x: float, scene_y: float) -> bool:
        controller = self._canvas_import_controller
        return bool(controller and controller.drop(urls, text, html, scene_x, scene_y))

    @pyqtSlot(str, bool, float, float, result=bool)
    def request_canvas_import_local_path(self, path: str, is_folder: bool, scene_x: float, scene_y: float) -> bool:
        controller = self._canvas_import_controller
        return bool(controller and controller.drop_local_path(path, is_folder, scene_x, scene_y))

    @pyqtSlot(
        str,
        float,
        float,
        str,
        str,
        str,
        str,
        result=bool,
    )
    def request_drop_node_from_library(
        self,
        type_id: str,
        scene_x: float,
        scene_y: float,
        target_mode: str,
        target_node_id: str,
        target_port_key: str,
        target_edge_id: str,
    ) -> bool:
        result = _invoke(
            self._workspace_drop_connect_controller,
            "request_drop_node_from_library",
            type_id,
            float(scene_x),
            float(scene_y),
            target_mode,
            target_node_id,
            target_port_key,
            target_edge_id,
            default=False,
        )
        return bool(getattr(result, "payload", result))

    @pyqtSlot(str, float, float, "QVariantMap", result=bool)
    def request_drop_node_from_library_with_properties(
        self,
        type_id: str,
        scene_x: float,
        scene_y: float,
        properties: dict[str, Any],
    ) -> bool:
        return bool(
            _invoke(
                self._workspace_drop_connect_controller,
                "insert_library_node_with_properties",
                type_id,
                dict(properties or {}),
                float(scene_x),
                float(scene_y),
                default="",
            )
        )

    @pyqtSlot(str, str, str, str, bool, result=bool)
    def request_connect_ports(
        self,
        source_node_id: str,
        source_port_key: str,
        target_node_id: str,
        target_port_key: str,
        append_requested: bool = False,
    ) -> bool:
        result = _invoke(
            self._workspace_edit_controller,
            "request_connect_ports",
            source_node_id,
            source_port_key,
            target_node_id,
            target_port_key,
            bool(append_requested),
            default=False,
        )
        message = str(getattr(result, "message", "") or "").strip()
        payload = bool(getattr(result, "payload", result))
        if not payload and message and callable(self._show_graph_hint_callback):
            self._show_graph_hint_callback(message, 2400)
        return payload

    @pyqtSlot("QVariantList", str, str, str, bool, bool, result=bool)
    def request_rewire_edges(
        self,
        edge_ids: list[Any],
        endpoint: str,
        node_id: str,
        port_key: str,
        copy_requested: bool = False,
        append_requested: bool = False,
    ) -> bool:
        result = _invoke(
            self._workspace_edit_controller,
            "request_rewire_edges",
            list(edge_ids or []),
            endpoint,
            node_id,
            port_key,
            bool(copy_requested),
            bool(append_requested),
            default=False,
        )
        message = str(getattr(result, "message", "") or "").strip()
        payload = bool(getattr(result, "payload", result))
        if not payload and message and callable(self._show_graph_hint_callback):
            self._show_graph_hint_callback(message, 2400)
        return payload

    @pyqtSlot(str, str, float, float, float, float, bool, result=bool)
    def request_open_connection_quick_insert(
        self,
        node_id: str,
        port_key: str,
        cursor_scene_x: float,
        cursor_scene_y: float,
        overlay_x: float,
        overlay_y: float,
        append_requested: bool = False,
    ) -> bool:
        return bool(
            _invoke(
                self._library_source,
                "request_open_connection_quick_insert",
                node_id,
                port_key,
                float(cursor_scene_x),
                float(cursor_scene_y),
                float(overlay_x),
                float(overlay_y),
                bool(append_requested),
                default=False,
            )
        )

    @pyqtSlot(float, float, float, float)
    def request_open_canvas_quick_insert(
        self,
        scene_x: float,
        scene_y: float,
        overlay_x: float,
        overlay_y: float,
    ) -> None:
        _invoke(
            self._library_source,
            "request_open_canvas_quick_insert",
            float(scene_x),
            float(scene_y),
            float(overlay_x),
            float(overlay_y),
        )

    def _add_path_pointer_node(self, path: str, mode: str, x: float, y: float) -> str:
        command_source = self._scene_command_source
        if command_source is None:
            return ""
        add_path_pointer = getattr(command_source, "add_path_pointer_node", None)
        if callable(add_path_pointer):
            return str(add_path_pointer(path, mode, x, y) or "")
        if not self._can_set_node_properties():
            return ""
        node_id = self._add_node_from_type("io.path_pointer", x, y)
        if not node_id:
            return ""
        self._set_node_properties(node_id, {"path": path, "mode": mode})
        return node_id


    def _add_folder_explorer_node(self, current_path: str, x: float, y: float) -> str:
        command_source = self._scene_command_source
        if command_source is None:
            return ""
        add_folder_explorer = getattr(command_source, "add_folder_explorer_node", None)
        if callable(add_folder_explorer):
            return str(add_folder_explorer(current_path, x, y) or "")
        if not self._can_set_node_properties():
            return ""
        node_id = self._add_node_from_type("io.folder_explorer", x, y)
        if not node_id:
            return ""
        self._set_node_properties(node_id, {"current_path": current_path})
        return node_id

    def _add_node_from_type(self, type_id: str, x: float, y: float) -> str:
        command_source = self._scene_command_source
        callback = getattr(command_source, "add_node_from_type", None) if command_source is not None else None
        if not callable(callback):
            return ""
        return str(callback(type_id, float(x), float(y)) or "")
