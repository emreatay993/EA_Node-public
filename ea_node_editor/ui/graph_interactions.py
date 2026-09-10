from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Protocol

from ea_node_editor.graph.effective_ports import (
    are_port_kinds_compatible,
    find_port,
    is_flow_edge_port,
    port_supports_incoming_edge,
    port_supports_outgoing_edge,
)
from ea_node_editor.graph.hierarchy import root_node_ids_for_fragment, subtree_node_ids
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.ui.shell.runtime_history import ACTION_DELETE_SELECTED
from ea_node_editor.ui.port_availability import (
    unavailable_connection_reason,
)

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory


@dataclass(slots=True)
class GraphActionResult:
    ok: bool
    message: str = ""


class _GraphSceneLike(Protocol):
    def current_workspace(self) -> WorkspaceData: ...

    def add_edge(
        self,
        source_node_id: str,
        source_port: str,
        target_node_id: str,
        target_port: str,
        append_requested: bool = False,
    ) -> str: ...

    def remove_edge(self, edge_id: str) -> None: ...

    def request_rewire_edges(
        self,
        edge_ids: list[object],
        endpoint: str,
        node_id: str,
        port_key: str,
        copy_requested: bool = False,
        append_requested: bool = False,
    ) -> bool: ...

    def remove_node(self, node_id: str) -> None: ...

    def set_node_title(self, node_id: str, title: str) -> None: ...

    def selectedItems(self) -> list[Any]: ...


class GraphInteractions:
    def __init__(
        self,
        scene: _GraphSceneLike,
        registry: NodeRegistry,
        history: RuntimeGraphHistory | None = None,
    ) -> None:
        self._scene = scene
        self._registry = registry
        self._history = history

    def replace_registry(self, registry: NodeRegistry) -> None:
        if not isinstance(registry, NodeRegistry):
            raise TypeError("registry must be a NodeRegistry")
        self._registry = registry

    def connect_ports(
        self,
        node_a_id: str,
        port_a_key: str,
        node_b_id: str,
        port_b_key: str,
        append_requested: bool = False,
    ) -> GraphActionResult:
        source_node_id = str(node_a_id).strip()
        source_port_key = str(port_a_key).strip()
        target_node_id = str(node_b_id).strip()
        target_port_key = str(port_b_key).strip()
        if not source_node_id or not source_port_key or not target_node_id or not target_port_key:
            return GraphActionResult(False, "Port connection request is incomplete.")

        workspace = self._scene.current_workspace()
        node_a = workspace.nodes.get(source_node_id)
        node_b = workspace.nodes.get(target_node_id)
        if node_a is None or node_b is None:
            return GraphActionResult(False, "One or more nodes are missing.")

        port_a = self._port(workspace, node_a, source_port_key)
        port_b = self._port(workspace, node_b, target_port_key)
        if port_a is None or port_b is None:
            return GraphActionResult(False, "One or more ports are missing.")
        direction_a = port_a.direction
        direction_b = port_b.direction
        kind_a = port_a.kind
        kind_b = port_b.kind
        if not self._are_port_kinds_compatible(kind_a, kind_b):
            return GraphActionResult(
                False,
                f"Incompatible port kinds: {kind_a} -> {kind_b}.",
            )
        if source_node_id == target_node_id and is_flow_edge_port(port_a) and is_flow_edge_port(port_b):
            return GraphActionResult(False, "Flow edges cannot connect ports on the same node.")

        can_a_to_b = port_supports_outgoing_edge(port_a) and port_supports_incoming_edge(port_b)
        can_b_to_a = port_supports_outgoing_edge(port_b) and port_supports_incoming_edge(port_a)
        final_target_port = port_b

        if direction_a == "neutral" and direction_b == "neutral":
            source_node_id, source_port_key, target_node_id, target_port_key = (
                source_node_id,
                source_port_key,
                target_node_id,
                target_port_key,
            )
        elif can_a_to_b and not can_b_to_a:
            source_node_id, source_port_key, target_node_id, target_port_key = (
                source_node_id,
                source_port_key,
                target_node_id,
                target_port_key,
            )
        elif can_b_to_a and not can_a_to_b:
            source_node_id, source_port_key, target_node_id, target_port_key = (
                target_node_id,
                target_port_key,
                source_node_id,
                source_port_key,
            )
            final_target_port = port_a
        elif direction_a == "out" and direction_b == "in":
            source_node_id, source_port_key, target_node_id, target_port_key = (
                source_node_id,
                source_port_key,
                target_node_id,
                target_port_key,
            )
        elif direction_a == "in" and direction_b == "out":
            source_node_id, source_port_key, target_node_id, target_port_key = (
                target_node_id,
                target_port_key,
                source_node_id,
                source_port_key,
            )
            final_target_port = port_a
        else:
            return GraphActionResult(False, "Ports must have compatible directions.")

        source_node = workspace.nodes.get(source_node_id)
        target_node = workspace.nodes.get(target_node_id)
        if source_node is None or target_node is None:
            return GraphActionResult(False, "One or more nodes are missing.")
        try:
            source_spec = self._registry.get_spec(source_node.type_id)
            target_spec = self._registry.get_spec(target_node.type_id)
        except KeyError:
            return GraphActionResult(False, "One or more node types are missing.")
        availability_reason = unavailable_connection_reason(
            workspace=workspace,
            source_node=source_node,
            source_spec=source_spec,
            source_port_key=source_port_key,
            target_node=target_node,
            target_spec=target_spec,
            target_port_key=target_port_key,
        )
        if availability_reason:
            return GraphActionResult(False, availability_reason)

        try:
            self._scene.add_edge(
                source_node_id,
                source_port_key,
                target_node_id,
                target_port_key,
                bool(append_requested),
            )
        except (KeyError, ValueError) as exc:
            return GraphActionResult(False, str(exc))
        return GraphActionResult(True)

    def remove_edge(self, edge_id: str) -> GraphActionResult:
        normalized_edge_id = str(edge_id).strip()
        if not normalized_edge_id:
            return GraphActionResult(False, "Connection id is required.")
        workspace = self._scene.current_workspace()
        if normalized_edge_id not in workspace.edges:
            return GraphActionResult(False, "Connection not found.")
        self._scene.remove_edge(normalized_edge_id)
        return GraphActionResult(True)

    def rewire_edges(
        self,
        edge_ids: list[object],
        endpoint: str,
        node_id: str,
        port_key: str,
        copy_requested: bool = False,
        append_requested: bool = False,
    ) -> GraphActionResult:
        normalized_endpoint = str(endpoint or "").strip().lower()
        normalized_node_id = str(node_id or "").strip()
        normalized_port_key = str(port_key or "").strip()
        normalized_edge_ids: list[str] = []
        seen_edge_ids: set[str] = set()
        for value in edge_ids:
            edge_id = str(value or "").strip()
            if edge_id and edge_id not in seen_edge_ids:
                seen_edge_ids.add(edge_id)
                normalized_edge_ids.append(edge_id)
        if not normalized_edge_ids:
            return GraphActionResult(False, "Connection id is required.")
        if normalized_endpoint not in {"source", "target"}:
            return GraphActionResult(False, "Connection endpoint must be source or target.")
        if bool(normalized_node_id) != bool(normalized_port_key):
            return GraphActionResult(False, "Connection endpoint request is incomplete.")

        workspace = self._scene.current_workspace()
        if any(edge_id not in workspace.edges for edge_id in normalized_edge_ids):
            return GraphActionResult(False, "Connection not found.")
        if normalized_node_id:
            for edge_id in normalized_edge_ids:
                edge = workspace.edges[edge_id]
                source_node_id = (
                    normalized_node_id
                    if normalized_endpoint == "source"
                    else edge.source_node_id
                )
                source_port_key = (
                    normalized_port_key
                    if normalized_endpoint == "source"
                    else edge.source_port_key
                )
                target_node_id = (
                    normalized_node_id
                    if normalized_endpoint == "target"
                    else edge.target_node_id
                )
                target_port_key = (
                    normalized_port_key
                    if normalized_endpoint == "target"
                    else edge.target_port_key
                )
                source_node = workspace.nodes.get(source_node_id)
                target_node = workspace.nodes.get(target_node_id)
                if source_node is None or target_node is None:
                    return GraphActionResult(False, "One or more nodes are missing.")
                try:
                    source_spec = self._registry.get_spec(source_node.type_id)
                    target_spec = self._registry.get_spec(target_node.type_id)
                except KeyError:
                    return GraphActionResult(
                        False,
                        "Unavailable add-on connections cannot be edited.",
                    )
                availability_reason = unavailable_connection_reason(
                    workspace=workspace,
                    source_node=source_node,
                    source_spec=source_spec,
                    source_port_key=source_port_key,
                    target_node=target_node,
                    target_spec=target_spec,
                    target_port_key=target_port_key,
                )
                if availability_reason:
                    return GraphActionResult(False, availability_reason)

        try:
            changed = self._scene.request_rewire_edges(
                normalized_edge_ids,
                normalized_endpoint,
                normalized_node_id,
                normalized_port_key,
                bool(copy_requested),
                bool(append_requested),
            )
        except (KeyError, ValueError) as exc:
            return GraphActionResult(False, str(exc))
        if not changed:
            return GraphActionResult(False, "Connection was not changed.")
        return GraphActionResult(True)

    def move_edge_endpoint(
        self,
        edge_id: str,
        endpoint: str,
        node_id: str,
        port_key: str,
        append_requested: bool = False,
    ) -> GraphActionResult:
        return self.rewire_edges(
            [edge_id],
            endpoint,
            node_id,
            port_key,
            append_requested=append_requested,
        )

    def remove_node(self, node_id: str) -> GraphActionResult:
        normalized_node_id = str(node_id).strip()
        if not normalized_node_id:
            return GraphActionResult(False, "Node id is required.")
        workspace = self._scene.current_workspace()
        if normalized_node_id not in workspace.nodes:
            # The delete request came from a rendered visual the model no
            # longer owns; remove_node resyncs the stale scene view so the
            # phantom does not linger on canvas.
            self._scene.remove_node(normalized_node_id)
            return GraphActionResult(False, "Node not found.")
        self._scene.remove_node(normalized_node_id)
        if normalized_node_id in workspace.nodes:
            return GraphActionResult(False, "Node could not be removed from the current scope.")
        return GraphActionResult(True)

    def rename_node(self, node_id: str, title: str) -> GraphActionResult:
        normalized_node_id = str(node_id).strip()
        normalized_title = str(title).strip()
        if not normalized_node_id:
            return GraphActionResult(False, "Node id is required.")
        if not normalized_title:
            return GraphActionResult(False, "Node title cannot be empty.")

        workspace = self._scene.current_workspace()
        node = workspace.nodes.get(normalized_node_id)
        if node is None:
            return GraphActionResult(False, "Node not found.")
        if node.title == normalized_title:
            return GraphActionResult(True)
        try:
            self._scene.set_node_title(normalized_node_id, normalized_title)
        except OSError as exc:
            return GraphActionResult(False, f"Node artifact folder could not be renamed: {exc}")
        return GraphActionResult(True)

    def delete_selected_items(self, edge_ids: Iterable[Any]) -> GraphActionResult:
        workspace = self._scene.current_workspace()
        removed_any = False
        history_group = nullcontext()
        if self._history is not None:
            history_group = self._history.grouped_action(
                workspace.workspace_id,
                ACTION_DELETE_SELECTED,
                workspace,
            )

        with history_group:
            requested_edge_ids: list[str] = []
            seen_edge_ids: set[str] = set()
            for value in edge_ids:
                edge_id = str(value).strip()
                if not edge_id or edge_id in seen_edge_ids:
                    continue
                seen_edge_ids.add(edge_id)
                requested_edge_ids.append(edge_id)

            for edge_id in requested_edge_ids:
                if edge_id not in workspace.edges:
                    continue
                self._scene.remove_edge(edge_id)
                removed_any = True

            selected_node_ids: list[str] = []
            seen_node_ids: set[str] = set()
            for item in self._scene.selectedItems():
                node = getattr(item, "node", None)
                node_id = getattr(node, "node_id", "")
                normalized_node_id = str(node_id).strip()
                if not normalized_node_id or normalized_node_id in seen_node_ids:
                    continue
                seen_node_ids.add(normalized_node_id)
                selected_node_ids.append(normalized_node_id)

            removable_roots = root_node_ids_for_fragment(workspace, selected_node_ids)
            removable_ids = subtree_node_ids(workspace, removable_roots)
            for removable_node_id in reversed(removable_ids):
                if removable_node_id not in workspace.nodes:
                    continue
                self._scene.remove_node(removable_node_id)
                removed_any = True

        if not removed_any:
            return GraphActionResult(False, "No selected graph items to remove.")
        return GraphActionResult(True)

    def _port(self, workspace: WorkspaceData, node: NodeInstance, port_key: str):
        try:
            spec = self._registry.get_spec(node.type_id)
        except KeyError:
            return None
        return find_port(
            node=node,
            spec=spec,
            workspace_nodes=workspace.nodes,
            port_key=port_key,
        )

    @staticmethod
    def _are_port_kinds_compatible(source_kind: str, target_kind: str) -> bool:
        return are_port_kinds_compatible(source_kind, target_kind)
