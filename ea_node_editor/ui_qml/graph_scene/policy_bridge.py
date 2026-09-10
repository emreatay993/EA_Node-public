from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSlot

from ea_node_editor.graph.effective_ports import are_port_kinds_compatible
from ea_node_editor.ui_qml.graph_scene_mutation_history import GraphSceneMutationPolicy

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


class GraphScenePolicyBridge(QObject):
    def __init__(self, scene_bridge: GraphSceneBridge, policy: GraphSceneMutationPolicy) -> None:
        super().__init__(scene_bridge)
        self._scene_bridge = scene_bridge
        self._policy = policy

    @property
    def scene_bridge(self) -> GraphSceneBridge:
        return self._scene_bridge

    @pyqtSlot(str, str, str, str, result=bool)
    def are_ports_compatible(
        self,
        source_node_id: str,
        source_port: str,
        target_node_id: str,
        target_port: str,
    ) -> bool:
        return self._policy.are_ports_compatible(
            source_node_id,
            source_port,
            target_node_id,
            target_port,
        )

    @pyqtSlot(str, str, str, result="QVariantMap")
    def compatible_endpoint_snapshot(
        self,
        anchor_node_id: str,
        anchor_port_key: str,
        candidate_role: str,
    ) -> dict[str, object]:
        return self._policy.compatible_endpoint_snapshot(
            anchor_node_id,
            anchor_port_key,
            candidate_role,
        )

    @pyqtSlot("QVariantList", str, result="QVariantMap")
    @pyqtSlot("QVariantList", str, bool, bool, result="QVariantMap")
    def compatible_rewire_endpoint_snapshot(
        self,
        edge_ids: list[object],
        endpoint: str,
        copy_requested: bool = False,
        append_requested: bool = False,
    ) -> dict[str, object]:
        return self._policy.compatible_rewire_endpoint_snapshot(
            list(edge_ids or []),
            endpoint,
            bool(copy_requested),
            bool(append_requested),
        )

    @pyqtSlot(str, str, result=bool)
    def are_port_kinds_compatible(self, source_kind: str, target_kind: str) -> bool:
        return are_port_kinds_compatible(str(source_kind), str(target_kind))

    @pyqtSlot(str, str, result=bool)
    def are_data_types_compatible(self, source_type: str, target_type: str) -> bool:
        if str(source_type) == "flow" and str(target_type) == "flow":
            return True
        registry = self._scene_bridge._registry
        if registry is None:
            return False
        return registry.data_types.compatibility(
            str(source_type),
            str(target_type),
        ).is_compatible


__all__ = ["GraphScenePolicyBridge"]
