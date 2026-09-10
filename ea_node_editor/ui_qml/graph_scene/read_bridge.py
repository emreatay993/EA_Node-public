from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


class GraphSceneReadBridge(QObject):
    node_selected = pyqtSignal(str)
    workspace_changed = pyqtSignal(str)
    scope_changed = pyqtSignal()
    nodes_changed = pyqtSignal()
    edges_changed = pyqtSignal()
    selection_changed = pyqtSignal()
    interact_with_locked_objects_changed = pyqtSignal()

    def __init__(self, scene_bridge: GraphSceneBridge) -> None:
        super().__init__(scene_bridge)
        self._scene_bridge = scene_bridge
        self._node_delta_payload: dict[str, Any] = {}
        scene_bridge.node_selected.connect(self.node_selected.emit)
        scene_bridge.workspace_changed.connect(self.workspace_changed.emit)
        scene_bridge.scope_changed.connect(self.scope_changed.emit)
        scene_bridge.nodes_changed.connect(self.nodes_changed.emit)
        scene_bridge.edges_changed.connect(self.edges_changed.emit)
        scene_bridge.selection_changed.connect(self.selection_changed.emit)
        scene_bridge.interact_with_locked_objects_changed.connect(self.interact_with_locked_objects_changed.emit)

    @property
    def scene_bridge(self) -> GraphSceneBridge:
        return self._scene_bridge

    @pyqtProperty(str, notify=workspace_changed)
    def workspace_id(self) -> str:
        return self._scene_bridge.workspace_id

    @pyqtProperty("QVariantList", notify=nodes_changed)
    def nodes_model(self) -> list[dict[str, Any]]:
        return self._scene_bridge.nodes_model

    @pyqtProperty("QVariantList", notify=nodes_changed)
    def backdrop_nodes_model(self) -> list[dict[str, Any]]:
        return self._scene_bridge.backdrop_nodes_model

    @pyqtProperty("QVariantMap", notify=nodes_changed)
    def node_delta_payload(self) -> dict[str, Any]:
        return dict(self._node_delta_payload)

    @node_delta_payload.setter
    def node_delta_payload(self, value: dict[str, Any]) -> None:
        self._node_delta_payload = dict(value or {})

    @pyqtProperty("QVariantList", notify=edges_changed)
    def edges_model(self) -> list[dict[str, Any]]:
        return self._scene_bridge.edges_model

    @pyqtProperty("QVariantMap", notify=edges_changed)
    def edge_delta_payload(self) -> dict[str, Any]:
        return self._scene_bridge.edge_delta_payload

    @pyqtProperty("QVariantList", notify=nodes_changed)
    def minimap_nodes_model(self) -> list[dict[str, Any]]:
        return self._scene_bridge.minimap_nodes_model

    def minimap_payloads_for_node_ids(self, node_ids: list[str]) -> list[dict[str, Any]] | None:
        self._scene_bridge._ensure_payload_cache_current()
        cache = self._scene_bridge._payload_cache
        payloads: list[dict[str, Any]] = []
        for node_id in node_ids:
            status, index = cache.resolve_minimap_payload_slot(str(node_id))
            if status != "ok" or index is None:
                return None
            payloads.append(dict(cache.minimap_nodes[index]))
        return payloads

    @pyqtProperty("QVariantMap", notify=nodes_changed)
    def workspace_scene_bounds_payload(self) -> dict[str, float]:
        return self._scene_bridge.workspace_scene_bounds_payload

    @pyqtProperty(str, notify=node_selected)
    def selected_node_id_value(self) -> str:
        return self._scene_bridge.selected_node_id_value

    @pyqtProperty("QVariantMap", notify=selection_changed)
    def selected_node_lookup(self) -> dict[str, bool]:
        return self._scene_bridge.selected_node_lookup

    @pyqtProperty("QVariantList", notify=selection_changed)
    def selected_node_ids(self) -> list[str]:
        return self._scene_bridge.selected_node_ids

    @pyqtProperty(bool, notify=interact_with_locked_objects_changed)
    def interact_with_locked_objects(self) -> bool:
        return self._scene_bridge.interact_with_locked_objects

    @pyqtProperty("QVariantList", notify=scope_changed)
    def active_scope_path(self) -> list[str]:
        return self._scene_bridge.active_scope_path

    @pyqtProperty("QVariantList", notify=scope_changed)
    def scope_breadcrumb_model(self) -> list[dict[str, str]]:
        return self._scene_bridge.scope_breadcrumb_model

    @pyqtProperty(bool, notify=scope_changed)
    def can_navigate_scope_parent(self) -> bool:
        return self._scene_bridge.can_navigate_scope_parent

    @pyqtSlot(result="QVariantMap")
    def workspace_scene_bounds_map(self) -> dict[str, float]:
        return self._scene_bridge.workspace_scene_bounds_map()

    @pyqtSlot("QVariantMap", result="QVariantMap")
    def library_drop_preview_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._scene_bridge.library_drop_preview_payload(payload)


__all__ = ["GraphSceneReadBridge"]
