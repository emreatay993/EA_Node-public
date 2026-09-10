from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, QPointF, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices

from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.platform_open import open_path_with_default_handler
from ea_node_editor.ui.media_panel_source import resolve_media_panel_source
from ea_node_editor.ui_qml.graph_scene_mutation_history import GraphSceneMutationHistory
from ea_node_editor.ui_qml.graph_scene_mutation.node_creation_batch import NodeCreationRequest, NodeCreationResult

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

_SNAP_GRID_SIZE = 20.0


class GraphSceneCommandBridge(QObject):
    pending_surface_action_changed = pyqtSignal()

    def __init__(
        self,
        scene_bridge: GraphSceneBridge,
        *,
        scope_selection: Any,
        authoring_boundary: GraphSceneMutationHistory,
        pending_surface_action: Any,
    ) -> None:
        super().__init__(scene_bridge)
        self._scene_bridge = scene_bridge
        self._scope_selection = scope_selection
        self._authoring_boundary = authoring_boundary
        self._pending_surface_action = pending_surface_action
        scene_bridge.pending_surface_action_changed.connect(
            self.pending_surface_action_changed.emit
        )

    @property
    def scene_bridge(self) -> GraphSceneBridge:
        return self._scene_bridge

    @pyqtProperty(str, notify=pending_surface_action_changed)
    def pending_surface_action_node_id(self) -> str:
        return self._pending_surface_action.node_id

    def _timed_authoring_call(self, callback, *args, **kwargs):  # noqa: ANN001
        timing_active = getattr(self._scene_bridge, "mutation_timing_active", None)
        if not callable(timing_active) or not timing_active():
            return callback(*args, **kwargs)
        start = time.perf_counter()
        try:
            return callback(*args, **kwargs)
        finally:
            recorder = getattr(self._scene_bridge, "record_mutation_timing_phase", None)
            if callable(recorder):
                recorder("command_dispatch_ms", (time.perf_counter() - start) * 1000.0)

    def clearSelection(self) -> None:
        self._scope_selection.clear_selection()

    @pyqtSlot()
    def clear_selection(self) -> None:
        self._scope_selection.clear_selection()

    @pyqtSlot(str)
    @pyqtSlot(str, bool)
    def select_node(self, node_id: str, additive: bool = False) -> None:
        self._scope_selection.select_node(node_id, additive=additive)

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
        self._scope_selection.select_nodes_in_rect(
            x1,
            y1,
            x2,
            y2,
            additive=additive,
        )

    @pyqtSlot(bool, result=bool)
    def set_interact_with_locked_objects(self, enabled: bool) -> bool:
        return self._scope_selection.set_interact_with_locked_objects(enabled)

    @pyqtSlot(str)
    def set_pending_surface_action(self, node_id: str) -> None:
        if self._pending_surface_action.set(node_id):
            self._scene_bridge.pending_surface_action_changed.emit()

    @pyqtSlot(str, result=bool)
    def consume_pending_surface_action(self, node_id: str) -> bool:
        if self._pending_surface_action.consume(node_id):
            self._scene_bridge.pending_surface_action_changed.emit()
            return True
        return False

    @pyqtSlot(str, float, float, result=str)
    def add_node_from_type(self, type_id: str, x: float = 0.0, y: float = 0.0) -> str:
        return self._timed_authoring_call(
            self._authoring_boundary.add_node_from_type, type_id, x, y
        )

    def create_nodes_batch(self, requests: tuple[NodeCreationRequest, ...]) -> tuple[NodeCreationResult, ...]:
        return self._timed_authoring_call(self._authoring_boundary.create_nodes_batch, requests)

    def create_node_from_type(
        self,
        *,
        type_id: str,
        x: float,
        y: float,
        parent_node_id: str | None,
        select_node: bool,
        property_overrides: dict[str, Any] | None = None,
        exposed_port_overrides: dict[str, bool] | None = None,
        initial_title: str | None = None,
        custom_width: float | None = None,
        custom_height: float | None = None,
        after_create=None,  # noqa: ANN001
    ) -> str:
        return self._timed_authoring_call(
            self._authoring_boundary.create_node_from_type,
            type_id=type_id,
            x=x,
            y=y,
            parent_node_id=parent_node_id,
            select_node=select_node,
            property_overrides=property_overrides,
            exposed_port_overrides=exposed_port_overrides,
            initial_title=initial_title,
            custom_width=custom_width,
            custom_height=custom_height,
            after_create=after_create,
        )

    @pyqtSlot(str, str, float, float, result=str)
    def add_path_pointer_node(
        self, path: str, mode: str, x: float = 0.0, y: float = 0.0
    ) -> str:
        node_id = self._authoring_boundary.add_node_from_type("io.path_pointer", x, y)
        self._authoring_boundary.set_node_properties(
            node_id,
            {
                "path": str(path or ""),
                "mode": str(mode or "file").strip() or "file",
            },
        )
        return node_id

    @pyqtSlot(str, float, float, result=str)
    def add_folder_explorer_node(
        self, current_path: str, x: float = 0.0, y: float = 0.0
    ) -> str:
        node_id = self._authoring_boundary.add_node_from_type(
            "io.folder_explorer", x, y
        )
        self._authoring_boundary.set_node_property(
            node_id, "current_path", str(current_path or "")
        )
        return node_id

    def add_subnode_shell_pin(self, shell_node_id: str, pin_type_id: str) -> str:
        return self._timed_authoring_call(
            self._authoring_boundary.add_subnode_shell_pin, shell_node_id, pin_type_id
        )

    def add_edge(
        self,
        source_node_id: str,
        source_port: str,
        target_node_id: str,
        target_port: str,
        append_requested: bool = False,
    ) -> str:
        return self._timed_authoring_call(
            self._authoring_boundary.add_edge,
            source_node_id,
            source_port,
            target_node_id,
            target_port,
            append_requested,
        )

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
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.request_rewire_edges,
                list(edge_ids or []),
                endpoint,
                node_id,
                port_key,
                bool(copy_requested),
                bool(append_requested),
            )
        )

    @pyqtSlot(str, str, result=str)
    def connect_nodes(self, node_a_id: str, node_b_id: str) -> str:
        return self._timed_authoring_call(
            self._authoring_boundary.connect_nodes, node_a_id, node_b_id
        )

    def remove_edge(self, edge_id: str) -> None:
        self._timed_authoring_call(self._authoring_boundary.remove_edge, edge_id)

    def remove_node(self, node_id: str) -> None:
        self._timed_authoring_call(self._authoring_boundary.remove_node, node_id)

    def remove_workspace_node(self, node_id: str) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.remove_workspace_node, node_id
        )

    @pyqtSlot(str)
    def focus_node_slot(self, node_id: str) -> None:
        self.focus_node(node_id)

    def focus_node(self, node_id: str) -> QPointF | None:
        return self._authoring_boundary.focus_node(node_id)

    @pyqtSlot(str, bool, result=bool)
    def set_node_collapsed(self, node_id: str, collapsed: bool) -> bool:
        return bool(self._authoring_boundary.set_node_collapsed(node_id, collapsed))

    @pyqtSlot(str, str, bool, result=bool)
    def set_node_settings_group_expanded(
        self,
        node_id: str,
        group_id: str,
        expanded: bool,
    ) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.set_node_settings_group_expanded,
                node_id,
                group_id,
                expanded,
            )
        )

    @pyqtSlot(str, bool, result=bool)
    def set_node_locked(self, node_id: str, locked: bool) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.set_node_locked, node_id, locked
            )
        )

    @pyqtSlot(str, str, str)
    def set_node_port_label(self, node_id: str, port_key: str, label: str) -> None:
        self._authoring_boundary.set_node_port_label(node_id, port_key, label)

    @pyqtSlot(str, str, "QVariant")
    def set_node_property(self, node_id: str, key: str, value: Any) -> None:
        self._timed_authoring_call(
            self._authoring_boundary.set_node_property, node_id, key, value
        )

    @pyqtSlot(str, str, str, result=bool)
    def set_node_secret(self, node_id: str, key: str, plaintext: str) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.set_node_secret,
                node_id,
                key,
                plaintext,
            )
        )

    @pyqtSlot(str, str, result=bool)
    def clear_node_secret(self, node_id: str, key: str) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.clear_node_secret,
                node_id,
                key,
            )
        )

    @pyqtSlot(str, "QVariantMap", result=bool)
    def set_node_properties(self, node_id: str, values: dict[str, Any]) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.set_node_properties, node_id, values
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
        return str(
            self._timed_authoring_call(
                self._authoring_boundary.upsert_node_link,
                node_id,
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

    @pyqtSlot(str, str, result=bool)
    def remove_node_link(self, node_id: str, link_id: str) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.remove_node_link, node_id, link_id
            )
        )

    @pyqtSlot(str, str, int, result=bool)
    def move_node_link(self, node_id: str, link_id: str, offset: int) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.move_node_link, node_id, link_id, offset
            )
        )

    @pyqtSlot(str, result="QVariantList")
    def parameter_setup_link_options(self, pool_node_id: str) -> list[dict[str, Any]]:
        return list(
            self._authoring_boundary.parameter_setup_link_options(pool_node_id)
            or []
        )

    @pyqtSlot(str, result="QVariantMap")
    def parameter_setup_link_status(self, pool_node_id: str) -> dict[str, Any]:
        return dict(
            self._authoring_boundary.parameter_setup_link_status(pool_node_id)
            or {}
        )

    @pyqtSlot(str, str, result=bool)
    def link_parameter_setup(self, pool_node_id: str, setup_node_id: str) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.link_parameter_setup,
                pool_node_id,
                setup_node_id,
            )
        )

    @pyqtSlot(str, result=bool)
    def unlink_parameter_setup(self, pool_node_id: str) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.unlink_parameter_setup,
                pool_node_id,
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
            self._timed_authoring_call(
                self._authoring_boundary.upsert_node_comment,
                node_id,
                comment_id,
                body,
                author,
                parent_id,
                resolved,
                unread,
                pinned,
            )
            or ""
        )

    @pyqtSlot(str, str, result=bool)
    def remove_node_comment(self, node_id: str, comment_id: str) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.remove_node_comment, node_id, comment_id
            )
        )

    @pyqtSlot(str, str, bool, result=bool)
    def set_node_comment_resolved(
        self, node_id: str, comment_id: str, resolved: bool
    ) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.set_node_comment_resolved,
                node_id,
                comment_id,
                bool(resolved),
            )
        )

    @pyqtSlot(str, str, bool, result=bool)
    def set_node_comment_pinned(
        self, node_id: str, comment_id: str, pinned: bool
    ) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.set_node_comment_pinned,
                node_id,
                comment_id,
                bool(pinned),
            )
        )

    @pyqtSlot(str, result=bool)
    def resolve_all_node_comments(self, node_id: str) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.resolve_all_node_comments, node_id
            )
        )

    @pyqtSlot(str, result=bool)
    def mark_node_comments_read(self, node_id: str) -> bool:
        return bool(
            self._timed_authoring_call(
                self._authoring_boundary.mark_node_comments_read, node_id
            )
        )

    @pyqtSlot(str, str, result=bool)
    def open_node_link(self, node_id: str, link_id: str) -> bool:
        model = getattr(self._scene_bridge, "_model", None)
        workspace_id = str(
            getattr(self._scene_bridge, "_workspace_id", "") or ""
        ).strip()
        workspace = (
            model.project.workspaces.get(workspace_id) if model is not None else None
        )
        if workspace is None:
            return False
        node = workspace.nodes.get(str(node_id or "").strip())
        if node is None:
            return False
        link = next(
            (item for item in node.links if item.link_id == str(link_id or "").strip()),
            None,
        )
        if link is None:
            return False
        if link.kind == "url":
            target = str(link.target or "").strip()
            url = QUrl(target)
            if target and not url.scheme():
                url = QUrl(f"https://{target}")
            return bool(QDesktopServices.openUrl(url))
        if link.kind in {"file", "folder"}:
            return open_path_with_default_handler(link.target)
        if link.kind == "node":
            target_workspace_id = str(
                getattr(link, "target_workspace_id", "") or workspace_id
            ).strip()
            if target_workspace_id != workspace_id:
                return False
            target_node_id = str(getattr(link, "target_node_id", "") or link.target)
            position_ms = _video_link_position_ms(link.subtitle)
            target_node = workspace.nodes.get(target_node_id)
            source_resolution = None
            if target_node is not None and str(target_node.type_id) == MEDIA_PANEL_TYPE_ID:
                shell_window = self._scene_bridge.parent()
                project = getattr(model, "project", None)
                project_metadata = getattr(project, "metadata", None)
                try:
                    source_resolution = resolve_media_panel_source(
                        node=target_node,
                        workspace=workspace,
                        run_state=getattr(shell_window, "run_state", None),
                        project_path=(
                            str(getattr(shell_window, "project_path", "") or "").strip()
                            or None
                        ),
                        project_metadata=(
                            dict(project_metadata)
                            if isinstance(project_metadata, dict)
                            else None
                        ),
                    )
                except (OSError, TypeError, ValueError):
                    source_resolution = None
            if (
                position_ms is not None
                and source_resolution is not None
                and source_resolution.state == "ready"
                and source_resolution.media_kind == "video"
            ):
                self._timed_authoring_call(
                    self._authoring_boundary.set_node_property,
                    target_node_id,
                    "position_ms",
                    position_ms,
                )
            return self.focus_node(target_node_id) is not None
        return False

    @pyqtSlot("QVariant", result="QVariantMap")
    def normalize_node_visual_style(self, visual_style: Any) -> dict[str, Any]:
        return self._authoring_boundary.normalize_node_visual_style(visual_style)

    @pyqtSlot(str, "QVariant")
    def set_node_visual_style(self, node_id: str, visual_style: Any) -> None:
        self._authoring_boundary.set_node_visual_style(node_id, visual_style)

    @pyqtSlot(str)
    def clear_node_visual_style(self, node_id: str) -> None:
        self._authoring_boundary.clear_node_visual_style(node_id)

    @pyqtSlot(str, result=bool)
    def propagate_passive_node_style(self, node_id: str) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.propagate_passive_node_style, node_id
        )

    def set_node_title(self, node_id: str, title: str) -> None:
        self._timed_authoring_call(
            self._authoring_boundary.set_node_title, node_id, title
        )

    @pyqtSlot("QVariant", result=str)
    def normalize_edge_label(self, label: Any) -> str:
        return self._authoring_boundary.normalize_edge_label(label)

    @pyqtSlot(str, "QVariant")
    def set_edge_label(self, edge_id: str, label: Any) -> None:
        self._timed_authoring_call(
            self._authoring_boundary.set_edge_label, edge_id, label
        )

    @pyqtSlot(str)
    def clear_edge_label(self, edge_id: str) -> None:
        self._authoring_boundary.clear_edge_label(edge_id)

    @pyqtSlot("QVariant", result="QVariantMap")
    def normalize_edge_visual_style(self, visual_style: Any) -> dict[str, Any]:
        return self._authoring_boundary.normalize_edge_visual_style(visual_style)

    @pyqtSlot(str, "QVariant")
    def set_edge_visual_style(self, edge_id: str, visual_style: Any) -> None:
        self._timed_authoring_call(
            self._authoring_boundary.set_edge_visual_style, edge_id, visual_style
        )

    @pyqtSlot(str)
    def clear_edge_visual_style(self, edge_id: str) -> None:
        self._authoring_boundary.clear_edge_visual_style(edge_id)

    @pyqtSlot(str, bool, result=bool)
    def set_edge_enabled(self, edge_id: str, enabled: bool) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.set_edge_enabled, edge_id, enabled
        )

    @pyqtSlot("QVariantList", bool, result=bool)
    def set_edges_enabled(self, edge_ids: list[Any], enabled: bool) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.set_edges_enabled, edge_ids, enabled
        )

    @pyqtSlot("QVariantList", str, result=bool)
    def set_edges_display_mode(self, edge_ids: list[Any], mode: str) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.set_edges_display_mode, edge_ids, mode
        )

    @pyqtSlot(str, str, "QVariantList", result=bool)
    def set_port_modifiers(
        self, node_id: str, port_key: str, modifiers: list[Any]
    ) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.set_port_modifiers,
            node_id,
            port_key,
            modifiers,
        )

    @pyqtSlot(str, str, result=bool)
    def set_principal_input_port(self, node_id: str, port_key: str) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.set_principal_input_port,
            node_id,
            port_key,
        )

    @pyqtSlot(str, str, int, result=str)
    def insert_dynamic_port(
        self,
        node_id: str,
        group_id: str,
        ordinal: int,
    ) -> str:
        try:
            return str(
                self._timed_authoring_call(
                    self._authoring_boundary.insert_dynamic_port,
                    node_id,
                    group_id,
                    ordinal,
                )
                or ""
            )
        except (KeyError, IndexError, ValueError):
            return ""

    @pyqtSlot(str, str, str, result="QVariantMap")
    def remove_dynamic_port(
        self,
        node_id: str,
        group_id: str,
        port_key: str,
    ) -> dict[str, Any]:
        try:
            result = self._timed_authoring_call(
                self._authoring_boundary.remove_dynamic_port,
                node_id,
                group_id,
                port_key,
            )
        except (KeyError, IndexError, ValueError) as exc:
            message = exc.args[0] if isinstance(exc, KeyError) and exc.args else exc
            return {"error": {"message": str(message)}}
        if not result:
            return {}
        removed_port_key, removed_edge_ids = result
        return {
            "port_key": str(removed_port_key),
            "removed_edge_ids": [str(edge_id) for edge_id in removed_edge_ids],
        }

    @pyqtSlot(str, str, str, str, result="QVariantMap")
    def rename_dynamic_port(
        self,
        node_id: str,
        group_id: str,
        port_key: str,
        value: str,
    ) -> dict[str, Any]:
        try:
            result = self._timed_authoring_call(
                self._authoring_boundary.rename_dynamic_port,
                node_id,
                group_id,
                port_key,
                value,
            )
        except (KeyError, IndexError, ValueError) as exc:
            message = exc.args[0] if isinstance(exc, KeyError) and exc.args else exc
            return {"error": {"message": str(message)}}
        if not result:
            return {}
        resulting_port_key, removed_edge_ids = result
        return {
            "previous_port_key": str(port_key or "").strip(),
            "port_key": str(resulting_port_key),
            "removed_edge_ids": [str(edge_id) for edge_id in removed_edge_ids],
        }

    @pyqtSlot(bool, result=bool)
    def set_hide_optional_ports(self, hide_optional_ports: bool) -> bool:
        return self._authoring_boundary.set_hide_optional_ports(hide_optional_ports)

    @pyqtSlot(str, str, bool, result=bool)
    def set_exposed_port(self, node_id: str, key: str, exposed: bool) -> bool:
        self._timed_authoring_call(
            self._authoring_boundary.set_exposed_port, node_id, key, exposed
        )
        return True

    @pyqtSlot(str, float, float)
    def move_node(self, node_id: str, x: float, y: float) -> None:
        self._timed_authoring_call(self._authoring_boundary.move_node, node_id, x, y)

    @pyqtSlot(str, float, float)
    def resize_node(self, node_id: str, width: float, height: float) -> None:
        self._timed_authoring_call(
            self._authoring_boundary.resize_node, node_id, width, height
        )

    @pyqtSlot(str, float, float, float, float)
    def set_node_geometry(
        self, node_id: str, x: float, y: float, width: float, height: float
    ) -> None:
        self._timed_authoring_call(
            self._authoring_boundary.set_node_geometry, node_id, x, y, width, height
        )

    @pyqtSlot("QVariantList", float, float, result=bool)
    def move_nodes_by_delta(self, node_ids: list[Any], dx: float, dy: float) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.move_nodes_by_delta, node_ids, dx, dy
        )

    def align_selected_nodes(
        self,
        alignment: str,
        *,
        snap_to_grid: bool = False,
        grid_size: float = _SNAP_GRID_SIZE,
    ) -> bool:
        return self._authoring_boundary.align_selected_nodes(
            alignment,
            snap_to_grid=snap_to_grid,
            grid_size=grid_size,
        )

    def distribute_selected_nodes(
        self,
        orientation: str,
        *,
        snap_to_grid: bool = False,
        grid_size: float = _SNAP_GRID_SIZE,
    ) -> bool:
        return self._authoring_boundary.distribute_selected_nodes(
            orientation,
            snap_to_grid=snap_to_grid,
            grid_size=grid_size,
        )

    def set_selected_same_type_size(self, node_ids: list[Any], dimension: str) -> bool:
        return self._authoring_boundary.set_selected_same_type_size(node_ids, dimension)

    def straighten_selected_connections(self) -> bool:
        return self._authoring_boundary.straighten_selected_connections()

    @pyqtSlot("QVariantList", result=str)
    def wrap_node_ids_in_group_backdrop(self, node_ids: list[Any]) -> str:
        return self._authoring_boundary.wrap_nodes_in_group_backdrop(node_ids)

    @pyqtSlot(result=bool)
    def wrap_selected_nodes_in_group_backdrop(self) -> bool:
        return self._authoring_boundary.wrap_selected_nodes_in_group_backdrop()

    @pyqtSlot(result=bool)
    def group_selected_nodes(self) -> bool:
        return self._timed_authoring_call(self._authoring_boundary.group_selected_nodes)

    @pyqtSlot(result=bool)
    def ungroup_selected_subnode(self) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.ungroup_selected_subnode
        )

    @pyqtSlot(result=bool)
    def duplicate_selected_subgraph(self) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.duplicate_selected_subgraph
        )

    def serialize_selected_subgraph_fragment(self) -> dict[str, Any] | None:
        return self._authoring_boundary.serialize_selected_subgraph_fragment()

    def fragment_bounds_center(
        self, fragment_payload: Any
    ) -> tuple[float, float] | None:
        return self._authoring_boundary.fragment_bounds_center(fragment_payload)

    def paste_subgraph_fragment(
        self, fragment_payload: Any, center_x: float, center_y: float
    ) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.paste_subgraph_fragment,
            fragment_payload,
            center_x,
            center_y,
        )

    def delete_selected_graph_items(self, edge_ids: list[Any]) -> bool:
        return self._timed_authoring_call(
            self._authoring_boundary.delete_selected_graph_items, edge_ids
        )


__all__ = ["GraphSceneCommandBridge"]


def _video_link_position_ms(subtitle: str) -> int | None:
    text = str(subtitle or "").strip()
    if "video_position_ms=" not in text:
        return None
    for token in text.replace(";", " ").replace(",", " ").split():
        if not token.startswith("video_position_ms="):
            continue
        value = token.split("=", 1)[1].strip()
        try:
            return max(0, int(value))
        except ValueError:
            return None
    return None
