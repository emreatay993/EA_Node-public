from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from ea_node_editor.common.protocols import SignalLike as _SignalLike

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


class _ShellInspectorSource(Protocol):
    selected_node_changed: _SignalLike
    workspace_state_changed: _SignalLike
    selected_node_title: str
    selected_node_subtitle: str
    selected_node_summary: str
    selected_node_id: str
    selected_node_workspace_id: str
    selected_node_header_items: list[dict[str, str]]
    has_selected_node: bool
    selected_node_collapsible: bool
    selected_node_collapsed: bool
    selected_node_is_subnode_pin: bool
    selected_node_is_subnode_shell: bool
    selected_node_property_items: list[dict[str, Any]]
    selected_node_link_items: list[dict[str, Any]]
    selected_node_comment_items: list[dict[str, Any]]
    selected_node_link_node_options: list[dict[str, Any]]
    selected_node_link_workspace_options: list[dict[str, Any]]
    selected_node_port_items: list[dict[str, Any]]
    pin_data_type_options: list[str]
    property_pane_variant: str

    def set_content_active(self, active: bool) -> None: ...

    def set_selected_node_property(self, key: str, value: Any) -> None: ...

    def upsert_selected_node_link(
        self,
        link_id: str,
        kind: str,
        title: str,
        target: str,
        subtitle: str = "",
        target_workspace_id: str = "",
        target_node_id: str = "",
    ) -> str: ...

    def remove_selected_node_link(self, link_id: str) -> bool: ...

    def move_selected_node_link(self, link_id: str, offset: int) -> bool: ...

    def open_selected_node_link(self, link_id: str) -> bool: ...
    def upsert_selected_node_comment(
        self,
        comment_id: str,
        body: str,
        parent_id: str = "",
        resolved: bool = False,
        unread: bool = True,
        pinned: bool = False,
    ) -> str: ...
    def remove_selected_node_comment(self, comment_id: str) -> bool: ...
    def set_selected_node_comment_resolved(self, comment_id: str, resolved: bool) -> bool: ...
    def set_selected_node_comment_pinned(self, comment_id: str, pinned: bool) -> bool: ...
    def resolve_all_selected_node_comments(self) -> bool: ...
    def mark_selected_node_comments_read(self) -> bool: ...

    def browse_selected_node_property_path(self, key: str, current_path: str, source_mode: str = "") -> str: ...

    def pick_selected_node_property_color(self, key: str, current_value: str) -> str: ...

    def set_selected_port_exposed(self, key: str, exposed: bool) -> None: ...

    def set_selected_port_label(self, key: str, label: str) -> bool: ...

    def set_selected_node_collapsed(self, collapsed: bool) -> None: ...

    def request_ungroup_selected_nodes(self) -> bool: ...

    def request_add_selected_subnode_pin(self, direction: str) -> str: ...

    def request_remove_selected_port(self, key: str) -> bool: ...


def _copy_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


_UNHANDLED = object()


def _require_inspector_source(inspector_source: _ShellInspectorSource | None) -> _ShellInspectorSource:
    if inspector_source is None:
        raise TypeError("ShellInspectorBridge requires an explicit inspector source contract.")
    return inspector_source


class ShellInspectorBridge(QObject):
    selected_node_changed = pyqtSignal()
    workspace_state_changed = pyqtSignal()
    inspector_state_changed = pyqtSignal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        shell_window: object | None = None,
        inspector_source: _ShellInspectorSource | None = None,
        scene_bridge: "GraphSceneBridge | None" = None,
    ) -> None:
        super().__init__(parent)
        self._shell_window = shell_window if shell_window is not None else parent
        self._scene_bridge = scene_bridge
        self._inspector_source = _require_inspector_source(inspector_source)
        self._inspector_source_has_state_signal = False

        self._inspector_source.selected_node_changed.connect(self._on_selected_node_changed)
        self._inspector_source.workspace_state_changed.connect(self._on_workspace_state_changed)
        try:
            inspector_state_changed = self._inspector_source.inspector_state_changed  # type: ignore[attr-defined]
        except AttributeError:
            inspector_state_changed = None
        if inspector_state_changed is not None:
            inspector_state_changed.connect(self.inspector_state_changed.emit)
            self._inspector_source_has_state_signal = True

    def _on_selected_node_changed(self) -> None:
        self.selected_node_changed.emit()
        if not self._inspector_source_has_state_signal:
            self.inspector_state_changed.emit()

    def _on_workspace_state_changed(self) -> None:
        self.workspace_state_changed.emit()
        if not self._inspector_source_has_state_signal:
            self.inspector_state_changed.emit()

    @property
    def shell_window(self) -> None:
        return None

    @property
    def inspector_source(self) -> _ShellInspectorSource:
        return self._inspector_source

    @property
    def scene_bridge(self) -> "GraphSceneBridge | None":
        return self._scene_bridge

    def _selected_property_item(self, key: str) -> dict[str, Any] | None:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return None
        for item in _copy_list(self._inspector_source.selected_node_property_items):
            if not isinstance(item, dict):
                continue
            if str(item.get("key", "")).strip() == normalized_key:
                return item
        return None

    def _browse_folder_property_path(self, key: str, current_path: str) -> object:
        item = self._selected_property_item(key)
        if item is None:
            return _UNHANDLED
        if str(item.get("path_dialog_mode", "")).strip().lower() != "folder":
            return _UNHANDLED

        shell_host_presenter = getattr(self._shell_window, "shell_host_presenter", None)
        browse = getattr(shell_host_presenter, "browse_property_path_dialog", None)
        if not callable(browse):
            return _UNHANDLED
        label = str(item.get("label", "") or key).strip() or str(key)
        return str(
            browse(
                label,
                str(current_path or ""),
                dialog_mode="folder",
            )
            or ""
        )

    @pyqtProperty(str, notify=inspector_state_changed)
    def selected_node_title(self) -> str:
        return str(self._inspector_source.selected_node_title)

    @pyqtProperty(str, notify=inspector_state_changed)
    def selected_node_subtitle(self) -> str:
        return str(self._inspector_source.selected_node_subtitle)

    @pyqtProperty(str, notify=inspector_state_changed)
    def selected_node_summary(self) -> str:
        return str(self._inspector_source.selected_node_summary)

    @pyqtProperty(str, notify=inspector_state_changed)
    def selected_node_id(self) -> str:
        return str(getattr(self._inspector_source, "selected_node_id", "") or "")

    @pyqtProperty(str, notify=inspector_state_changed)
    def selected_node_workspace_id(self) -> str:
        return str(getattr(self._inspector_source, "selected_node_workspace_id", "") or "")

    @pyqtProperty("QVariantList", notify=inspector_state_changed)
    def selected_node_header_items(self) -> list[dict[str, str]]:
        return _copy_list(self._inspector_source.selected_node_header_items)

    @pyqtProperty(bool, notify=inspector_state_changed)
    def has_selected_node(self) -> bool:
        return bool(self._inspector_source.has_selected_node)

    @pyqtProperty(bool, notify=inspector_state_changed)
    def selected_node_collapsible(self) -> bool:
        return bool(self._inspector_source.selected_node_collapsible)

    @pyqtProperty(bool, notify=inspector_state_changed)
    def selected_node_collapsed(self) -> bool:
        return bool(self._inspector_source.selected_node_collapsed)

    @pyqtProperty(bool, notify=inspector_state_changed)
    def selected_node_is_subnode_pin(self) -> bool:
        return bool(self._inspector_source.selected_node_is_subnode_pin)

    @pyqtProperty(bool, notify=inspector_state_changed)
    def selected_node_is_subnode_shell(self) -> bool:
        return bool(self._inspector_source.selected_node_is_subnode_shell)

    @pyqtProperty("QVariantList", notify=inspector_state_changed)
    def selected_node_property_items(self) -> list[dict]:
        return _copy_list(self._inspector_source.selected_node_property_items)

    @pyqtProperty("QVariantList", notify=inspector_state_changed)
    def selected_node_link_items(self) -> list[dict]:
        return _copy_list(self._inspector_source.selected_node_link_items)

    @pyqtProperty("QVariantList", notify=inspector_state_changed)
    def selected_node_comment_items(self) -> list[dict]:
        return _copy_list(getattr(self._inspector_source, "selected_node_comment_items", []))

    @pyqtProperty("QVariantList", notify=inspector_state_changed)
    def selected_node_link_node_options(self) -> list[dict]:
        return _copy_list(getattr(self._inspector_source, "selected_node_link_node_options", []))

    @pyqtProperty("QVariantList", notify=inspector_state_changed)
    def selected_node_link_workspace_options(self) -> list[dict]:
        return _copy_list(getattr(self._inspector_source, "selected_node_link_workspace_options", []))

    @pyqtProperty("QVariantList", notify=inspector_state_changed)
    def selected_node_port_items(self) -> list[dict]:
        return _copy_list(self._inspector_source.selected_node_port_items)

    @pyqtProperty("QVariantList", notify=inspector_state_changed)
    def pin_data_type_options(self) -> list[str]:
        return _copy_list(self._inspector_source.pin_data_type_options)

    @pyqtProperty(str, notify=inspector_state_changed)
    def property_pane_variant(self) -> str:
        return str(getattr(self._inspector_source, "property_pane_variant", "") or "")

    @pyqtSlot(bool)
    def set_content_active(self, active: bool) -> None:
        self._inspector_source.set_content_active(active)

    @pyqtSlot(str, "QVariant")
    def set_selected_node_property(self, key: str, value) -> None:
        item = self._selected_property_item(key)
        if item is not None and bool(
            item.get("reprotects_sensitive_properties", False)
        ):
            if self._scene_bridge is not None and self.selected_node_id:
                self._scene_bridge.set_node_property(
                    self.selected_node_id,
                    str(key or "").strip(),
                    value,
                )
            return
        self._inspector_source.set_selected_node_property(key, value)

    @pyqtSlot(str, str, result=bool)
    def set_selected_node_secret(self, key: str, plaintext: str) -> bool:
        if self._scene_bridge is None or not self.selected_node_id:
            return False
        return bool(
            self._scene_bridge.set_node_secret(
                self.selected_node_id,
                str(key or "").strip(),
                plaintext,
            )
        )

    @pyqtSlot(str, result=bool)
    def clear_selected_node_secret(self, key: str) -> bool:
        if self._scene_bridge is None or not self.selected_node_id:
            return False
        return bool(
            self._scene_bridge.clear_node_secret(
                self.selected_node_id,
                str(key or "").strip(),
            )
        )

    @pyqtSlot(str, str, str, str, str, result=str)
    @pyqtSlot(str, str, str, str, str, str, str, result=str)
    def upsert_selected_node_link(
        self,
        link_id: str,
        kind: str,
        title: str,
        target: str,
        subtitle: str = "",
        target_workspace_id: str = "",
        target_node_id: str = "",
    ) -> str:
        return str(
            self._inspector_source.upsert_selected_node_link(
                link_id,
                kind,
                title,
                target,
                subtitle,
                target_workspace_id,
                target_node_id,
            )
            or ""
        )

    @pyqtSlot(str, result=bool)
    def remove_selected_node_link(self, link_id: str) -> bool:
        return bool(self._inspector_source.remove_selected_node_link(link_id))

    @pyqtSlot(str, int, result=bool)
    def move_selected_node_link(self, link_id: str, offset: int) -> bool:
        return bool(self._inspector_source.move_selected_node_link(link_id, int(offset)))

    @pyqtSlot(str, result=bool)
    def open_selected_node_link(self, link_id: str) -> bool:
        return bool(self._inspector_source.open_selected_node_link(link_id))

    @pyqtSlot(str, str, result=str)
    @pyqtSlot(str, str, str, bool, bool, bool, result=str)
    def upsert_selected_node_comment(
        self,
        comment_id: str,
        body: str,
        parent_id: str = "",
        resolved: bool = False,
        unread: bool = True,
        pinned: bool = False,
    ) -> str:
        return str(
            self._inspector_source.upsert_selected_node_comment(
                comment_id,
                body,
                parent_id,
                bool(resolved),
                bool(unread),
                bool(pinned),
            )
            or ""
        )

    @pyqtSlot(str, result=bool)
    def remove_selected_node_comment(self, comment_id: str) -> bool:
        return bool(self._inspector_source.remove_selected_node_comment(comment_id))

    @pyqtSlot(str, bool, result=bool)
    def set_selected_node_comment_resolved(self, comment_id: str, resolved: bool) -> bool:
        return bool(self._inspector_source.set_selected_node_comment_resolved(comment_id, bool(resolved)))

    @pyqtSlot(str, bool, result=bool)
    def set_selected_node_comment_pinned(self, comment_id: str, pinned: bool) -> bool:
        return bool(self._inspector_source.set_selected_node_comment_pinned(comment_id, bool(pinned)))

    @pyqtSlot(result=bool)
    def resolve_all_selected_node_comments(self) -> bool:
        return bool(self._inspector_source.resolve_all_selected_node_comments())

    @pyqtSlot(result=bool)
    def mark_selected_node_comments_read(self) -> bool:
        return bool(self._inspector_source.mark_selected_node_comments_read())

    @pyqtSlot(str, str, result=str)
    @pyqtSlot(str, str, str, result=str)
    def browse_selected_node_property_path(self, key: str, current_path: str, source_mode: str = "") -> str:
        folder_path = self._browse_folder_property_path(key, current_path)
        if folder_path is not _UNHANDLED:
            return str(folder_path)
        if str(source_mode or "").strip():
            return str(self._inspector_source.browse_selected_node_property_path(key, current_path, source_mode) or "")
        return str(self._inspector_source.browse_selected_node_property_path(key, current_path) or "")

    @pyqtSlot(str, str, result=str)
    def pick_selected_node_property_color(self, key: str, current_value: str) -> str:
        return str(self._inspector_source.pick_selected_node_property_color(key, current_value) or "")

    @pyqtSlot(str, bool)
    def set_selected_port_exposed(self, key: str, exposed: bool) -> None:
        self._inspector_source.set_selected_port_exposed(key, exposed)

    @pyqtSlot(str, str, result=bool)
    def set_selected_port_label(self, key: str, label: str) -> bool:
        return bool(self._inspector_source.set_selected_port_label(key, label))

    @pyqtSlot(bool)
    def set_selected_node_collapsed(self, collapsed: bool) -> None:
        self._inspector_source.set_selected_node_collapsed(collapsed)

    @pyqtSlot(result=bool)
    def request_ungroup_selected_nodes(self) -> bool:
        return bool(self._inspector_source.request_ungroup_selected_nodes())

    @pyqtSlot(str, result=str)
    def request_add_selected_subnode_pin(self, direction: str) -> str:
        return str(self._inspector_source.request_add_selected_subnode_pin(direction) or "")

    @pyqtSlot(str, result=bool)
    def request_remove_selected_port(self, key: str) -> bool:
        return bool(self._inspector_source.request_remove_selected_port(key))


__all__ = ["ShellInspectorBridge"]
