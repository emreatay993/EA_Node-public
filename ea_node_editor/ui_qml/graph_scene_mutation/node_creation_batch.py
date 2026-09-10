# Purpose: Create independent node requests in one graph-owned history action.
# Map: feature_routes/clipboard_undo_redo_mutation_history.md
# Tests: tests/test_canvas_import_controller.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.ui_qml.graph_scene_mutation.selection_and_scope_ops import _create_node_from_type


@dataclass(frozen=True, slots=True)
class NodeCreationRequest:
    type_id: str
    x: float
    y: float
    parent_node_id: str | None
    properties: dict[str, Any] = field(default_factory=dict)
    exposed_ports: dict[str, bool] | None = None
    after_create: Callable[[NodeInstance, ValidatedGraphMutation], bool | None] | None = None
    on_failure: Callable[[], None] | None = None


@dataclass(frozen=True, slots=True)
class NodeCreationResult:
    node_id: str = ""
    error: str = ""


def create_nodes_batch(self, requests: tuple[NodeCreationRequest, ...]) -> tuple[NodeCreationResult, ...]:
    context = self._scene_context
    workspace = context.workspace_or_none()
    if workspace is None:
        return tuple(NodeCreationResult(error="The destination workspace is unavailable.") for _ in requests)
    results: list[NodeCreationResult] = []
    with context.grouped_history_action("import-canvas-items", workspace):
        for request in requests:
            try:
                node_id = _create_node_from_type(self,
                    type_id=request.type_id, x=request.x, y=request.y,
                    parent_node_id=request.parent_node_id, select_node=False,
                    property_overrides=request.properties,
                    exposed_port_overrides=request.exposed_ports,
                    after_create=request.after_create,
                )
                if not node_id:
                    raise RuntimeError("The node could not be created.")
            except Exception as error:
                message = str(error) or type(error).__name__
                if request.on_failure is not None:
                    try:
                        request.on_failure()
                    except Exception as cleanup_error:
                        message += f" Internal copy cleanup failed: {cleanup_error}"
                results.append(NodeCreationResult(error=message))
            else:
                results.append(NodeCreationResult(node_id=node_id))
    return tuple(results)
