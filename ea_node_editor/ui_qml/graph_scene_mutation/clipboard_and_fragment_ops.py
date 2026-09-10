from __future__ import annotations

from typing import Any

from ea_node_editor.ui.shell.runtime_clipboard import normalize_graph_fragment_payload
from ea_node_editor.ui.shell.runtime_history import ACTION_DUPLICATE_SUBGRAPH, ACTION_PASTE_SUBGRAPH

DUPLICATE_OFFSET_X = 40.0
DUPLICATE_OFFSET_Y = 40.0


def duplicate_selected_subgraph(self) -> bool:
    fragment_payload = self.serialize_selected_subgraph_fragment()
    normalized_fragment = normalize_graph_fragment_payload(fragment_payload)
    if normalized_fragment is None:
        return False
    duplicated_node_ids = self._insert_fragment(
        normalized_fragment,
        action_type=ACTION_DUPLICATE_SUBGRAPH,
        delta_x=DUPLICATE_OFFSET_X,
        delta_y=DUPLICATE_OFFSET_Y,
    )
    if not duplicated_node_ids:
        return False
    self._scope_selection.set_selected_node_ids(duplicated_node_ids)
    self._scene_context.rebuild_models()
    return True


def serialize_selected_subgraph_fragment(self) -> dict[str, Any] | None:
    model = self._scene_context.model
    if model is None:
        return None
    workspace = model.project.workspaces.get(self._scene_context.workspace_id)
    if workspace is None:
        return None
    selected_node_ids = self._expanded_selected_node_ids_for_fragment(workspace)
    if not selected_node_ids:
        return None
    return self._build_subgraph_fragment_payload(workspace, selected_node_ids)


def fragment_bounds_center(self, fragment_payload: Any) -> tuple[float, float] | None:
    normalized = normalize_graph_fragment_payload(fragment_payload)
    if normalized is None:
        return None
    bounds = self._fragment_bounds(normalized["nodes"])
    if bounds is None:
        return None
    return (bounds.center().x(), bounds.center().y())


def paste_subgraph_fragment(self, fragment_payload: Any, center_x: float, center_y: float) -> bool:
    normalized_fragment = normalize_graph_fragment_payload(fragment_payload)
    if normalized_fragment is None:
        return False
    workspace = self._scene_context.workspace_or_none()
    if workspace is None:
        return False

    fragment_bounds = self._fragment_bounds(normalized_fragment["nodes"])
    if fragment_bounds is None:
        return False

    delta_x = float(center_x) - fragment_bounds.center().x()
    delta_y = float(center_y) - fragment_bounds.center().y()
    edge_ids_before = set(workspace.edges)
    pasted_node_ids = self._insert_fragment(
        normalized_fragment,
        action_type=ACTION_PASTE_SUBGRAPH,
        delta_x=delta_x,
        delta_y=delta_y,
    )
    if not pasted_node_ids:
        return False

    selection_changed = self._scope_selection.set_selected_node_ids(
        pasted_node_ids,
        emit_signals=False,
    )
    if not self._scene_context.publish_node_additions_delta(
        pasted_node_ids,
        added_edge_ids=set(workspace.edges) - edge_ids_before,
        publication_path="fragment_addition_delta",
    ):
        self._scene_context.rebuild_models()
    if selection_changed:
        selected_node_ids = self._scene_context.selected_node_ids
        self._scene_context.emit_selection_changed(
            selected_node_ids[-1] if selected_node_ids else ""
        )
    return True


__all__ = [
    "DUPLICATE_OFFSET_X",
    "DUPLICATE_OFFSET_Y",
    "duplicate_selected_subgraph",
    "fragment_bounds_center",
    "paste_subgraph_fragment",
    "serialize_selected_subgraph_fragment",
]
