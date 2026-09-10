from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import pyqtSlot

from ea_node_editor.ui_qml.bridge_runtime import (
    copy_dict as _copy_dict,
    invoke as _invoke,
    invoke_available as _invoke_available,
    variant_value as _variant_value,
)

if TYPE_CHECKING:
    pass

class SceneMutationOps:
    """Scene mutation command forwards: selection, node/edge properties, geometry,
node links, and port metadata. ALL scene mutations route uniformly through the
resolved scene command source (self._scene_command_source); do not call
scene_bridge.command_bridge directly."""

    @pyqtSlot(str, bool)
    def select_node(self, node_id: str, additive: bool = False) -> None:
        _invoke(self._scene_command_source, "select_node", node_id, bool(additive))

    @pyqtSlot()
    def clear_selection(self) -> None:
        _invoke(self._scene_command_source, "clear_selection")

    @pyqtSlot(float, float, float, float)
    @pyqtSlot(float, float, float, float, bool)
    def select_nodes_in_rect(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        additive: bool = False,
    ) -> None:
        _invoke(
            self._scene_command_source,
            "select_nodes_in_rect",
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            bool(additive),
        )

    @pyqtSlot(str, str, str)
    def set_node_port_label(self, node_id: str, port_key: str, label: str) -> None:
        _invoke(self._scene_command_source, "set_node_port_label", node_id, port_key, label)

    @pyqtSlot(str, str, bool, result=bool)
    def set_exposed_port(self, node_id: str, port_key: str, exposed: bool) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "set_exposed_port",
                node_id,
                port_key,
                bool(exposed),
                default=False,
            )
        )

    @pyqtSlot(str, str, "QVariant")
    def set_node_property(self, node_id: str, key: str, value: object) -> None:
        _invoke(self._scene_command_source, "set_node_property", node_id, key, _variant_value(value))

    @pyqtSlot(str)
    def set_pending_surface_action(self, node_id: str) -> None:
        _invoke(self._scene_command_source, "set_pending_surface_action", node_id)

    @pyqtSlot(str, result=bool)
    def consume_pending_surface_action(self, node_id: str) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "consume_pending_surface_action",
                node_id,
                default=False,
            )
        )

    @pyqtSlot(str, "QVariantMap", result=bool)
    def set_node_properties(self, node_id: str, values: dict[str, Any]) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "set_node_properties",
                node_id,
                _variant_value(dict(values or {})),
                default=False,
            )
        )

    @pyqtSlot(str, bool, result=bool)
    def set_node_collapsed(self, node_id: str, collapsed: bool) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "set_node_collapsed",
                node_id,
                bool(collapsed),
                default=False,
            )
        )

    @pyqtSlot(str, str, bool, result=bool)
    def set_node_settings_group_expanded(
        self,
        node_id: str,
        group_id: str,
        expanded: bool,
    ) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "set_node_settings_group_expanded",
                node_id,
                group_id,
                bool(expanded),
                default=False,
            )
        )

    @pyqtSlot(str, str, str, str, str, str, result=str)
    @pyqtSlot(str, str, str, str, str, str, str, str, result=str)
    def upsert_node_link(
        self,
        node_id: str,
        link_id: str,
        kind: str,
        title: str,
        target: str,
        subtitle: str = "",
        target_workspace_id: str = "",
        target_node_id: str = "",
    ) -> str:
        args = (node_id, link_id, kind, title, target, subtitle)
        if str(target_workspace_id or "").strip() or str(target_node_id or "").strip():
            args = (*args, target_workspace_id, target_node_id)
        return str(
            _invoke(
                self._scene_command_source,
                "upsert_node_link",
                *args,
                default="",
            )
            or ""
        )

    @pyqtSlot(str, str, result=bool)
    def remove_node_link(self, node_id: str, link_id: str) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "remove_node_link",
                node_id,
                link_id,
                default=False,
            )
        )

    @pyqtSlot(str, str, int, result=bool)
    def move_node_link(self, node_id: str, link_id: str, offset: int) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "move_node_link",
                node_id,
                link_id,
                int(offset),
                default=False,
            )
        )

    @pyqtSlot(str, result="QVariantList")
    def parameter_setup_link_options(self, pool_node_id: str) -> list[dict[str, Any]]:
        result = _invoke(
            self._scene_command_source,
            "parameter_setup_link_options",
            pool_node_id,
            default=[],
        )
        return [dict(item) for item in list(result or []) if isinstance(item, Mapping)]

    @pyqtSlot(str, result="QVariantMap")
    def parameter_setup_link_status(self, pool_node_id: str) -> dict[str, Any]:
        result = _invoke(
            self._scene_command_source,
            "parameter_setup_link_status",
            pool_node_id,
            default={},
        )
        return dict(result) if isinstance(result, Mapping) else {}

    @pyqtSlot(str, str, result=bool)
    def link_parameter_setup(self, pool_node_id: str, setup_node_id: str) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "link_parameter_setup",
                pool_node_id,
                setup_node_id,
                default=False,
            )
        )

    @pyqtSlot(str, result=bool)
    def unlink_parameter_setup(self, pool_node_id: str) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "unlink_parameter_setup",
                pool_node_id,
                default=False,
            )
        )

    @pyqtSlot(str, str, str, result=str)
    @pyqtSlot(str, str, str, str, str, bool, bool, bool, result=str)
    def upsert_node_comment(
        self,
        node_id: str,
        comment_id: str,
        body: str,
        author: str = "",
        parent_id: str = "",
        resolved: bool = False,
        unread: bool = True,
        pinned: bool = False,
    ) -> str:
        return str(
            _invoke(
                self._scene_command_source,
                "upsert_node_comment",
                node_id,
                comment_id,
                body,
                author,
                parent_id,
                bool(resolved),
                bool(unread),
                bool(pinned),
                default="",
            )
            or ""
        )

    @pyqtSlot(str, str, result=bool)
    def remove_node_comment(self, node_id: str, comment_id: str) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "remove_node_comment",
                node_id,
                comment_id,
                default=False,
            )
        )

    @pyqtSlot(str, str, bool, result=bool)
    def set_node_comment_resolved(self, node_id: str, comment_id: str, resolved: bool) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "set_node_comment_resolved",
                node_id,
                comment_id,
                bool(resolved),
                default=False,
            )
        )

    @pyqtSlot(str, str, bool, result=bool)
    def set_node_comment_pinned(self, node_id: str, comment_id: str, pinned: bool) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "set_node_comment_pinned",
                node_id,
                comment_id,
                bool(pinned),
                default=False,
            )
        )

    @pyqtSlot(str, result=bool)
    def resolve_all_node_comments(self, node_id: str) -> bool:
        return bool(_invoke(self._scene_command_source, "resolve_all_node_comments", node_id, default=False))

    @pyqtSlot(str, result=bool)
    def mark_node_comments_read(self, node_id: str) -> bool:
        return bool(_invoke(self._scene_command_source, "mark_node_comments_read", node_id, default=False))

    @pyqtSlot(str, str, result=bool)
    def open_node_link(self, node_id: str, link_id: str) -> bool:
        link = self._node_link_record(node_id, link_id)
        if link is not None and str(getattr(link, "kind", "") or "") == "workspace":
            return self._open_workspace_link(str(getattr(link, "target", "") or ""))
        if link is not None and str(getattr(link, "kind", "") or "") == "node":
            target_workspace_id = str(getattr(link, "target_workspace_id", "") or "").strip()
            target_node_id = str(getattr(link, "target_node_id", "") or getattr(link, "target", "") or "").strip()
            source_workspace_id = self._source_workspace_id_for_node_link(str(node_id or ""))
            if target_workspace_id and target_node_id and target_workspace_id != source_workspace_id:
                return self._open_node_link(target_workspace_id, target_node_id)
        return bool(
            _invoke(
                self._scene_command_source,
                "open_node_link",
                node_id,
                link_id,
                default=False,
            )
        )

    def _node_link_record(self, node_id: str, link_id: str) -> object | None:
        normalized_node_id = str(node_id or "").strip()
        normalized_link_id = str(link_id or "").strip()
        if not normalized_node_id or not normalized_link_id:
            return None
        model = getattr(self._scene_bridge, "_model", None)
        if model is None and callable(self._model_provider):
            model = self._model_provider()
        project = getattr(model, "project", None)
        workspaces = getattr(project, "workspaces", None)
        if not isinstance(workspaces, Mapping):
            return None
        workspace_ids: list[str] = []

        def add_workspace_id(value: object) -> None:
            normalized = str(value or "").strip()
            if normalized and normalized not in workspace_ids:
                workspace_ids.append(normalized)

        add_workspace_id(getattr(self._scene_bridge, "_workspace_id", ""))
        add_workspace_id(getattr(self._scene_bridge, "workspace_id", ""))
        if callable(self._active_workspace_id_provider):
            add_workspace_id(self._active_workspace_id_provider())
        workspace = next(
            (workspaces.get(workspace_id) for workspace_id in workspace_ids if workspaces.get(workspace_id) is not None),
            None,
        )
        nodes = getattr(workspace, "nodes", None)
        if not isinstance(nodes, Mapping):
            return None
        node = nodes.get(normalized_node_id)
        links = getattr(node, "links", []) if node is not None else []
        return next(
            (item for item in links if str(getattr(item, "link_id", "") or "").strip() == normalized_link_id),
            None,
        )

    def _source_workspace_id_for_node_link(self, node_id: str) -> str:
        normalized_node_id = str(node_id or "").strip()
        if not normalized_node_id:
            return ""
        model = getattr(self._scene_bridge, "_model", None)
        if model is None and callable(self._model_provider):
            model = self._model_provider()
        project = getattr(model, "project", None)
        workspaces = getattr(project, "workspaces", None)
        if not isinstance(workspaces, Mapping):
            return ""
        scene_workspace_id = str(
            getattr(self._scene_bridge, "_workspace_id", "")
            or getattr(self._scene_bridge, "workspace_id", "")
            or ""
        ).strip()
        if scene_workspace_id:
            workspace = workspaces.get(scene_workspace_id)
            nodes = getattr(workspace, "nodes", None)
            if isinstance(nodes, Mapping) and normalized_node_id in nodes:
                return scene_workspace_id
        for workspace_id, workspace in workspaces.items():
            nodes = getattr(workspace, "nodes", None)
            if isinstance(nodes, Mapping) and normalized_node_id in nodes:
                return str(workspace_id)
        return scene_workspace_id

    def _open_workspace_link(self, workspace_id: str) -> bool:
        normalized_workspace_id = str(workspace_id or "").strip()
        if not normalized_workspace_id:
            return False
        model = self._model_provider() if callable(self._model_provider) else None
        project = getattr(model, "project", None)
        workspaces = getattr(project, "workspaces", None)
        if isinstance(workspaces, Mapping) and normalized_workspace_id not in workspaces:
            return False
        navigation = self._workspace_navigation_controller
        switch_workspace = getattr(navigation, "switch_workspace", None)
        if not callable(switch_workspace):
            return False
        switch_workspace(normalized_workspace_id)
        return True

    def _open_node_link(self, workspace_id: str, node_id: str) -> bool:
        normalized_workspace_id = str(workspace_id or "").strip()
        normalized_node_id = str(node_id or "").strip()
        if not normalized_workspace_id or not normalized_node_id:
            return False
        navigation = self._workspace_navigation_controller
        jump = getattr(navigation, "jump_to_graph_node", None)
        return bool(
            callable(jump)
            and jump(
                normalized_workspace_id,
                normalized_node_id,
            )
        )

    @pyqtSlot(str, str, result=bool)
    def are_port_kinds_compatible(self, source_kind: str, target_kind: str) -> bool:
        return bool(
            _invoke(
                self._scene_policy_source,
                "are_port_kinds_compatible",
                source_kind,
                target_kind,
                default=False,
            )
        )

    @pyqtSlot(str, str, result=bool)
    def are_data_types_compatible(self, source_type: str, target_type: str) -> bool:
        return bool(
            _invoke(
                self._scene_policy_source,
                "are_data_types_compatible",
                source_type,
                target_type,
                default=False,
            )
        )

    @pyqtSlot("QVariantList", float, float, result=bool)
    def move_nodes_by_delta(self, node_ids: list, delta_x: float, delta_y: float) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "move_nodes_by_delta",
                node_ids,
                float(delta_x),
                float(delta_y),
                default=False,
            )
        )

    @pyqtSlot(str, float, float)
    def move_node(self, node_id: str, x: float, y: float) -> None:
        _invoke(self._scene_command_source, "move_node", node_id, float(x), float(y))

    @pyqtSlot(str, float, float)
    def resize_node(self, node_id: str, width: float, height: float) -> None:
        _invoke(self._scene_command_source, "resize_node", node_id, float(width), float(height))

    @pyqtSlot(str, float, float, float, float)
    def set_node_geometry(self, node_id: str, x: float, y: float, width: float, height: float) -> None:
        _invoke(
            self._scene_command_source,
            "set_node_geometry",
            node_id,
            float(x),
            float(y),
            float(width),
            float(height),
        )

    @pyqtSlot(str, bool, result=bool)
    def set_edge_enabled(self, edge_id: str, enabled: bool) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "set_edge_enabled",
                edge_id,
                bool(enabled),
                default=False,
            )
        )

    @pyqtSlot("QVariantList", bool, result=bool)
    def set_edges_enabled(self, edge_ids: list[Any], enabled: bool) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "set_edges_enabled",
                list(edge_ids or []),
                bool(enabled),
                default=False,
            )
        )

    @pyqtSlot("QVariantList", str, result=bool)
    def set_edges_display_mode(self, edge_ids: list[Any], mode: str) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "set_edges_display_mode",
                list(edge_ids or []),
                str(mode or ""),
                default=False,
            )
        )

    @pyqtSlot(str, str, "QVariantList", result=bool)
    def set_port_modifiers(
        self,
        node_id: str,
        port_key: str,
        modifiers: list[Any],
    ) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "set_port_modifiers",
                node_id,
                port_key,
                list(modifiers or []),
                default=False,
            )
        )

    @pyqtSlot(str, str, result=bool)
    def set_principal_input_port(self, node_id: str, port_key: str) -> bool:
        return bool(
            _invoke(
                self._scene_command_source,
                "set_principal_input_port",
                node_id,
                port_key,
                default=False,
            )
        )

    def _dynamic_port_edit_allowed(self, node_id: str) -> bool:
        message = _invoke(
            self._workspace_edit_controller, "dynamic_port_edit_error", node_id, default=""
        )
        if message and callable(self._show_graph_hint_callback):
            self._show_graph_hint_callback(str(message), 4000)
        return not message

    @pyqtSlot(str, str, int, result=str)
    def insert_dynamic_port(
        self,
        node_id: str,
        group_id: str,
        ordinal: int,
    ) -> str:
        if not self._dynamic_port_edit_allowed(node_id):
            return ""
        result = str(
            _invoke(
                self._scene_command_source,
                "insert_dynamic_port",
                node_id,
                group_id,
                int(ordinal),
                default="",
            )
            or ""
        )
        if not result and callable(self._show_graph_hint_callback):
            self._show_graph_hint_callback("Unable to add port. Check the script declarations in the editor.", 4000)
        if result:
            _invoke(self._workspace_edit_controller, "on_dynamic_ports_changed", node_id)
        return result

    @pyqtSlot(str, str, str, result="QVariantMap")
    def remove_dynamic_port(
        self,
        node_id: str,
        group_id: str,
        port_key: str,
    ) -> dict[str, Any]:
        if not self._dynamic_port_edit_allowed(node_id):
            return {}
        result = _copy_dict(
            _invoke(
                self._scene_command_source,
                "remove_dynamic_port",
                node_id,
                group_id,
                port_key,
                default={},
            )
        )
        message = result.get("error", {}).get("message", "")
        if message and callable(self._show_graph_hint_callback):
            self._show_graph_hint_callback(str(message), 4000)
        if result.get("port_key"):
            _invoke(self._workspace_edit_controller, "on_dynamic_ports_changed", node_id)
        return result

    @pyqtSlot(str, str, str, str, result="QVariantMap")
    def rename_dynamic_port(
        self,
        node_id: str,
        group_id: str,
        port_key: str,
        value: str,
    ) -> dict[str, Any]:
        return _copy_dict(
            _invoke(
                self._scene_command_source,
                "rename_dynamic_port",
                node_id,
                group_id,
                port_key,
                value,
                default={},
            )
        )

    @pyqtSlot("QVariant", result=str)
    def normalize_edge_label(self, label: Any) -> str:
        return str(
            _invoke(
                self._scene_command_source,
                "normalize_edge_label",
                _variant_value(label),
                default="",
            )
            or ""
        )

    @pyqtSlot(str, "QVariant", result=bool)
    def set_edge_label(self, edge_id: str, label: Any) -> bool:
        return _invoke_available(self._scene_command_source, "set_edge_label", edge_id, _variant_value(label))

    @pyqtSlot(str, result=bool)
    def clear_edge_label(self, edge_id: str) -> bool:
        return _invoke_available(self._scene_command_source, "clear_edge_label", edge_id)

    @pyqtSlot("QVariant", result="QVariantMap")
    def normalize_edge_visual_style(self, visual_style: Any) -> dict[str, Any]:
        return _copy_dict(
            _invoke(
                self._scene_command_source,
                "normalize_edge_visual_style",
                _variant_value(visual_style),
                default={},
            )
        )

    @pyqtSlot(str, "QVariant", result=bool)
    def set_edge_visual_style(self, edge_id: str, visual_style: Any) -> bool:
        return _invoke_available(
            self._scene_command_source,
            "set_edge_visual_style",
            edge_id,
            _variant_value(visual_style),
        )

    @pyqtSlot(str, result=bool)
    def clear_edge_visual_style(self, edge_id: str) -> bool:
        return _invoke_available(self._scene_command_source, "clear_edge_visual_style", edge_id)

    def _can_set_node_properties(self) -> bool:
        command_source = self._scene_command_source
        if command_source is None:
            return False
        return callable(getattr(command_source, "set_node_properties", None)) or callable(
            getattr(command_source, "set_node_property", None)
        )

    def _set_node_properties(self, node_id: str, properties: Mapping[str, object]) -> None:
        command_source = self._scene_command_source
        if command_source is None:
            return
        bulk = getattr(command_source, "set_node_properties", None)
        if callable(bulk) and bool(bulk(node_id, dict(properties))):
            return
        setter = getattr(command_source, "set_node_property", None)
        if not callable(setter):
            return
        for key, value in properties.items():
            setter(node_id, key, value)
