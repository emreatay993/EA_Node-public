from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSlot

from ea_node_editor.ui.shell.controllers.graph_action_controller import GraphActionController
from ea_node_editor.ui.shell.graph_action_contracts import (
    GRAPH_ACTION_SPECS,
    graph_action_metadata,
    graph_action_spec,
)


class GraphActionBridge(QObject):
    def __init__(
        self,
        parent: QObject | None = None,
        *,
        controller: GraphActionController,
    ) -> None:
        super().__init__(parent)
        self._controller = controller

    @property
    def controller(self) -> GraphActionController:
        return self._controller

    @pyqtProperty("QVariantList", constant=True)
    def actionIds(self) -> list[str]:  # noqa: N802
        return self.available_action_ids()

    @pyqtProperty("QVariantMap", constant=True)
    def actionMetadata(self) -> dict[str, dict[str, object]]:  # noqa: N802
        return {
            spec.action_id.value: graph_action_metadata(spec)
            for spec in GRAPH_ACTION_SPECS
        }

    @pyqtSlot(result="QVariantList")
    def available_action_ids(self) -> list[str]:
        return list(self._controller.available_action_ids)

    @pyqtSlot(str, result="QVariantMap")
    def action_metadata(self, action_id: str) -> dict[str, object]:
        try:
            spec = graph_action_spec(str(action_id or "").strip())
        except ValueError:
            return {}
        return graph_action_metadata(spec)

    @pyqtSlot(str, "QVariantMap", result=bool)
    def trigger_graph_action(self, action_id: str, payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        return bool(self._controller.trigger(str(action_id or ""), payload))


__all__ = ["GraphActionBridge"]
