from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import pyqtSlot

from ea_node_editor.ui_qml.bridge_runtime import (
    copy_dict as _copy_dict,
    invoke as _invoke,
)

if TYPE_CHECKING:
    pass

class CanvasHostOps:
    """Host/shell command forwards: scope navigation, comment peek, cursor shape,
node-property dialogs, preview descriptions, and local-file URL resolution.
Comment-peek calls intentionally target the scene bridge itself (the peek
API lives on GraphSceneBridgeBase, not the scene command sub-bridge)."""

    @pyqtSlot(str, result=bool)
    def trigger_node(self, node_id: str) -> bool:
        return bool(_invoke(self._run_controller, "trigger_node", node_id, default=False))

    @pyqtSlot(str, result=bool)
    def request_open_subnode_scope(self, node_id: str) -> bool:
        normalized_node_id = str(node_id or "").strip()
        navigate = getattr(self._search_scope_controller, "navigate_scope", None)
        open_scope = getattr(self._scene_bridge, "open_subnode_scope", None)
        if not normalized_node_id or not callable(navigate) or not callable(open_scope):
            return False
        return bool(navigate(lambda: open_scope(normalized_node_id)))

    @pyqtSlot(str, result=bool)
    def can_open_comment_peek(self, node_id: str) -> bool:
        return bool(_invoke(self._scene_bridge, "can_open_comment_peek", node_id, default=False))

    @pyqtSlot(result=bool)
    def request_close_comment_peek(self) -> bool:
        return bool(_invoke(self._scene_bridge, "close_comment_peek", default=False))

    @pyqtSlot(result=str)
    def active_comment_peek_node_id(self) -> str:
        return str(getattr(self._scene_bridge, "active_comment_peek_node_id", "") or "")

    @pyqtSlot(str, str, str, result=str)
    @pyqtSlot(str, str, str, str, result=str)
    def browse_node_property_path(self, node_id: str, key: str, current_path: str, source_mode: str = "") -> str:
        args = [node_id, key, current_path]
        if str(source_mode or "").strip():
            args.append(source_mode)
        return str(
            _invoke(
                self._inspector_source,
                "browse_node_property_path",
                *args,
                default="",
            )
            or ""
        )

    @pyqtSlot(str, str, str, result=str)
    def internalize_node_property_path(self, node_id: str, key: str, current_path: str) -> str:
        return str(
            _invoke(
                self._inspector_source,
                "internalize_node_property_path",
                node_id,
                key,
                current_path,
                default="",
            )
            or ""
        )

    @pyqtSlot(str, str, str, result=str)
    def pick_node_property_color(self, node_id: str, key: str, current_value: str) -> str:
        return str(
            _invoke(
                self._inspector_source,
                "pick_node_property_color",
                node_id,
                key,
                current_value,
                default="",
            )
            or ""
        )

    @pyqtSlot("QVariantList", result=bool)
    def request_delete_selected_graph_items(self, edge_ids: list) -> bool:
        return bool(
            _invoke(
                self._host_source,
                "request_delete_selected_graph_items",
                edge_ids,
                default=False,
            )
        )

    @pyqtSlot(result=bool)
    def request_navigate_scope_parent(self) -> bool:
        return bool(
            _invoke(
                self._host_source,
                "request_navigate_scope_parent",
                default=False,
            )
        )

    @pyqtSlot(result=bool)
    def request_navigate_scope_root(self) -> bool:
        return bool(
            _invoke(
                self._host_source,
                "request_navigate_scope_root",
                default=False,
            )
        )

    @pyqtSlot(int)
    def set_graph_cursor_shape(self, cursor_shape: int) -> None:
        _invoke(self._host_source, "set_graph_cursor_shape", int(cursor_shape))

    @pyqtSlot()
    def clear_graph_cursor_shape(self) -> None:
        _invoke(self._host_source, "clear_graph_cursor_shape")

    @pyqtSlot(str, "QVariant", result="QVariantMap")
    def describe_pdf_preview(self, source: str, page_number: Any) -> dict[str, Any]:
        return _copy_dict(
            _invoke(
                self._host_source,
                "describe_pdf_preview",
                source,
                page_number,
                default={},
            )
        )

    @pyqtSlot(str, result="QVariantMap")
    def describe_image_preview(self, source: str) -> dict[str, Any]:
        return _copy_dict(
            _invoke(
                self._host_source,
                "describe_image_preview",
                source,
                default={},
            )
        )

    @pyqtSlot(str, result="QVariantMap")
    def describe_mail_preview(self, source: str) -> dict[str, Any]:
        return _copy_dict(
            _invoke(
                self._host_source,
                "describe_mail_preview",
                source,
                default={},
            )
        )

    @pyqtSlot(str, bool, result="QVariantMap")
    def open_local_file_source(self, source: str, chooser: bool) -> dict[str, Any]:
        return _copy_dict(
            _invoke(
                self._host_source,
                "open_local_file_source",
                source,
                bool(chooser),
                default={},
            )
        )

    @pyqtSlot("QVariantMap", "QVariantMap", result="QVariantMap")
    def describe_tabular_preview(
        self,
        properties: dict[str, Any],
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return _copy_dict(
            _invoke(
                self._host_source,
                "describe_tabular_preview",
                dict(properties or {}),
                dict(request or {}),
                default={},
            )
        )

    @pyqtSlot(str, result=str)
    def resolve_local_file_source_url(self, source: str) -> str:
        return str(
            _invoke(
                self._host_source,
                "resolve_local_file_source_url",
                source,
                default="",
            )
            or ""
        )
