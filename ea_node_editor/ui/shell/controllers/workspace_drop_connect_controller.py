# Purpose: Own library insertion, workflow drops, auto-connect, and connection picking.
# Map: feature_routes/workflow_library_drop_connect
# Tests: tests/test_workspace_drop_connect_controller.py
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ea_node_editor.custom_workflows import parse_custom_workflow_type_id
from ea_node_editor.graph.effective_ports import (
    EffectivePort,
    is_neutral_flow_port,
    is_subnode_pin_type,
    target_port_has_capacity,
)
from ea_node_editor.graph.hierarchy import scope_parent_id
from ea_node_editor.graph.invariant_kernel import GraphInvariantKernel, RegistryValidationPassMemo
from ea_node_editor.graph.type_forwarding import GraphTypeResolver
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.graph.transforms import encode_fragment_external_parent_id
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.builtins.subnode import SUBNODE_TYPE_ID
from ea_node_editor.ui.shell.controllers.mutation_ui_effects import MutationUiEffects
from ea_node_editor.ui.shell.controllers.result import ControllerResult
from ea_node_editor.ui.shell.runtime_clipboard import (
    build_graph_fragment_payload,
    normalize_graph_fragment_payload,
)
from ea_node_editor.ui.shell.runtime_history import ACTION_ADD_NODE

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


def _ordered_cardinal_sides_toward(
    *, node: NodeInstance, peer_node: NodeInstance
) -> tuple[str, ...]:
    dx = float(peer_node.x) - float(node.x)
    dy = float(peer_node.y) - float(node.y)

    if abs(dx) >= abs(dy):
        primary = "right" if dx >= 0.0 else "left"
        secondary = "bottom" if dy >= 0.0 else "top"
    else:
        primary = "bottom" if dy >= 0.0 else "top"
        secondary = "right" if dx >= 0.0 else "left"

    ordered = (
        primary,
        secondary,
        _opposite_cardinal_side(secondary),
        _opposite_cardinal_side(primary),
    )
    result: list[str] = []
    seen: set[str] = set()
    for side in ordered:
        if side in seen:
            continue
        seen.add(side)
        result.append(side)
    return tuple(result)


def _opposite_cardinal_side(side: str) -> str:
    if side == "top":
        return "bottom"
    if side == "right":
        return "left"
    if side == "bottom":
        return "top"
    return "right"


def _neutral_flow_ports(ports: list[EffectivePort]) -> list[EffectivePort]:
    return [port for port in ports if is_neutral_flow_port(port)]


def _preferred_neutral_flow_port(
    *,
    node: NodeInstance,
    peer_node: NodeInstance,
    neutral_ports: list[EffectivePort],
    excluded_keys: set[str] | None = None,
) -> EffectivePort | None:
    if not neutral_ports:
        return None

    excluded = excluded_keys or set()
    ordered_sides = _ordered_cardinal_sides_toward(node=node, peer_node=peer_node)
    for allow_excluded in (False, True):
        for side in ordered_sides:
            for port in neutral_ports:
                if port.side != side:
                    continue
                if not allow_excluded and port.key in excluded:
                    continue
                return port

    for port in neutral_ports:
        if port.key not in excluded:
            return port
    return neutral_ports[0]


def retarget_fragment_roots(
    fragment_payload: dict[str, Any],
    *,
    target_parent_id: str | None,
) -> dict[str, Any]:
    rewritten = copy.deepcopy(fragment_payload)
    nodes_payload = rewritten.get("nodes")
    if not isinstance(nodes_payload, list):
        return rewritten
    fragment_node_ids = {
        str(node_payload.get("ref_id", "")).strip()
        for node_payload in nodes_payload
        if isinstance(node_payload, dict)
    }
    for node_payload in nodes_payload:
        if not isinstance(node_payload, dict):
            continue
        normalized_parent = str(node_payload.get("parent_node_id", "")).strip()
        if normalized_parent and normalized_parent in fragment_node_ids:
            continue
        if target_parent_id and target_parent_id in fragment_node_ids:
            node_payload["parent_node_id"] = encode_fragment_external_parent_id(
                target_parent_id
            )
        else:
            node_payload["parent_node_id"] = target_parent_id
    return rewritten


class WorkspaceDropConnectController:
    def __init__(
        self,
        host: ShellWindow,
        *,
        active_workspace: Callable[[], WorkspaceData | None],
        resolve_custom_workflow_definition: Callable[[str], dict[str, Any] | None],
        prompt_connection_candidate: Callable[..., dict[str, Any] | None],
        effects: MutationUiEffects,
    ) -> None:
        self._host = host
        self._active_workspace = active_workspace
        self._resolve_custom_workflow_definition = resolve_custom_workflow_definition
        self._prompt_connection_candidate = prompt_connection_candidate
        self.mutation_ui_effects = effects
        self._effects = effects

    def add_node_from_library(self, type_id: str) -> None:
        center = self._host.view.mapToScene(self._host.view.viewport().rect().center())
        self.insert_library_node(type_id, center.x(), center.y())

    def add_node_from_library_with_properties(
        self, type_id: str, properties: dict[str, Any]
    ) -> bool:
        center = self._host.view.mapToScene(self._host.view.viewport().rect().center())
        return bool(
            self.insert_library_node_with_properties(
                type_id,
                properties,
                center.x(),
                center.y(),
            )
        )

    def insert_library_node(
        self,
        type_id: str,
        x: float,
        y: float,
        *,
        exposed_port_overrides: dict[str, bool] | None = None,
    ) -> str:
        normalized_type = str(type_id).strip()
        if not normalized_type:
            return ""
        custom_workflow_id = parse_custom_workflow_type_id(normalized_type)
        if custom_workflow_id:
            return self.insert_custom_workflow_snapshot(
                custom_workflow_id, float(x), float(y)
            )
        try:
            create_kwargs: dict[str, Any] = {
                "type_id": normalized_type,
                "x": float(x),
                "y": float(y),
                "parent_node_id": scope_parent_id(self._host.scene.active_scope_path),
                "select_node": False,
            }
            if exposed_port_overrides is not None:
                create_kwargs["exposed_port_overrides"] = dict(exposed_port_overrides)
            node_id = self._host.scene.create_node_from_type(
                **create_kwargs,
            )
        except (KeyError, RuntimeError, TypeError, ValueError):
            return ""
        self._record_library_usage(normalized_type, node_id)
        return node_id

    def insert_library_node_with_properties(
        self,
        type_id: str,
        properties: dict[str, Any],
        x: float,
        y: float,
    ) -> str:
        normalized_type = str(type_id).strip()
        if not normalized_type or parse_custom_workflow_type_id(normalized_type):
            return ""
        try:
            node_id = self._host.scene.create_node_from_type(
                type_id=normalized_type,
                x=float(x),
                y=float(y),
                parent_node_id=scope_parent_id(self._host.scene.active_scope_path),
                select_node=False,
                property_overrides=dict(properties or {}),
            )
        except (KeyError, RuntimeError, TypeError, ValueError):
            return ""
        self._record_library_usage(normalized_type, node_id)
        return node_id

    def _record_library_usage(self, type_id: str, node_id: str) -> None:
        if not str(node_id).strip():
            return
        controller = getattr(self._host, "app_preferences_controller", None)
        record = getattr(controller, "record_node_library_usage", None)
        if not callable(record):
            return
        try:
            record(type_id)
        except (OSError, RuntimeError, TypeError, ValueError):
            return

    def insert_custom_workflow_snapshot(
        self, workflow_id: str, x: float, y: float
    ) -> str:
        primary_node_id, _endpoints = (
            self.insert_custom_workflow_snapshot_with_endpoints(
                workflow_id,
                x,
                y,
            )
        )
        return primary_node_id

    def insert_custom_workflow_snapshot_with_endpoints(
        self,
        workflow_id: str,
        x: float,
        y: float,
        *,
        map_published_shell_ports: bool = False,
    ) -> tuple[str, list[dict[str, str]]]:
        workspace = self._active_workspace()
        if workspace is None:
            return "", []
        definition = self._resolve_custom_workflow_definition(workflow_id)
        if definition is None:
            return "", []
        fragment_payload = self._normalize_custom_workflow_fragment_payload(
            definition.get("fragment")
        )
        if fragment_payload is None:
            return "", []

        target_parent_id = scope_parent_id(self._host.scene.active_scope_path)
        scoped_fragment_payload = retarget_fragment_roots(
            fragment_payload,
            target_parent_id=target_parent_id,
        )

        before_node_ids = set(workspace.nodes)
        if not self._host.scene.paste_subgraph_fragment(
            scoped_fragment_payload, float(x), float(y)
        ):
            return "", []
        inserted_node_ids = [
            node_id for node_id in workspace.nodes if node_id not in before_node_ids
        ]
        if not inserted_node_ids:
            return "", []

        inserted_node_id_set = set(inserted_node_ids)
        shell_node_id = self._find_inserted_root_subnode_shell_id(
            workspace.nodes, inserted_node_id_set
        )
        if shell_node_id:
            primary_node_id = shell_node_id
        else:
            selected_node_id = self._host.scene.selected_node_id() or ""
            primary_node_id = (
                selected_node_id
                if selected_node_id in inserted_node_id_set
                else sorted(inserted_node_ids)[0]
            )

        node_ref_ids = [
            str(node_payload.get("ref_id", "")).strip()
            for node_payload in scoped_fragment_payload.get("nodes", [])
            if isinstance(node_payload, dict)
        ]
        node_id_by_ref = (
            dict(zip(node_ref_ids, inserted_node_ids, strict=True))
            if len(node_ref_ids) == len(inserted_node_ids)
            else {}
        )
        endpoints: list[dict[str, str]] = []
        for port in definition.get("ports", []):
            if not isinstance(port, dict):
                continue
            preview_key = str(port.get("key", "")).strip()
            node_ref_id = str(port.get("node_ref_id", "")).strip()
            node_id = node_id_by_ref.get(node_ref_id, "")
            port_key = str(port.get("port_key", "")).strip()
            if map_published_shell_ports and not node_ref_id and not port_key and shell_node_id:
                # Published shell ports are keyed by their original child-pin IDs.
                mapped_pin_id = node_id_by_ref.get(preview_key, "")
                mapped_pin = workspace.nodes.get(mapped_pin_id)
                if (
                    mapped_pin is None
                    or mapped_pin.parent_node_id != shell_node_id
                    or not is_subnode_pin_type(mapped_pin.type_id)
                ):
                    continue
                node_id = shell_node_id
                port_key = mapped_pin_id
            if not node_id or not port_key:
                continue
            endpoints.append(
                {
                    "key": preview_key,
                    "node_id": node_id,
                    "port_key": port_key,
                }
            )
        return primary_node_id, endpoints

    @staticmethod
    def _normalize_custom_workflow_fragment_payload(
        fragment_payload: Any,
    ) -> dict[str, Any] | None:
        if not isinstance(fragment_payload, dict):
            return None
        normalized_fragment = normalize_graph_fragment_payload(fragment_payload)
        if normalized_fragment is not None:
            return normalized_fragment
        nodes_payload = fragment_payload.get("nodes")
        edges_payload = fragment_payload.get("edges")
        if not isinstance(nodes_payload, list) or not isinstance(edges_payload, list):
            return None
        return normalize_graph_fragment_payload(
            build_graph_fragment_payload(
                nodes=copy.deepcopy(nodes_payload),
                edges=copy.deepcopy(edges_payload),
            )
        )

    @staticmethod
    def _find_inserted_root_subnode_shell_id(
        workspace_nodes: dict[str, NodeInstance],
        inserted_node_ids: set[str],
    ) -> str:
        shell_candidates: list[NodeInstance] = []
        for node_id in inserted_node_ids:
            node = workspace_nodes.get(node_id)
            if node is None or node.type_id != SUBNODE_TYPE_ID:
                continue
            parent_id = (
                str(node.parent_node_id).strip()
                if node.parent_node_id is not None
                else ""
            )
            if parent_id and parent_id in inserted_node_ids:
                continue
            shell_candidates.append(node)
        if not shell_candidates:
            return ""
        shell_candidates.sort(
            key=lambda node: (float(node.y), float(node.x), node.node_id)
        )
        return shell_candidates[0].node_id

    def auto_connect_dropped_node_to_port(
        self,
        new_node_id: str,
        target_node_id: str,
        target_port_key: str,
        append_requested: bool = False,
        *,
        compatible_port_keys: tuple[str, ...] | None = None,
    ) -> bool:
        workspace = self._active_workspace()
        if workspace is None:
            return False
        resolver = GraphTypeResolver(registry=self._host.registry, workspace_nodes=workspace.nodes, workspace_edges=workspace.edges.values())

        new_node = workspace.nodes.get(new_node_id)
        target_node = workspace.nodes.get(target_node_id)
        if new_node is None or target_node is None:
            return False

        new_spec = self._host.registry.resolve_spec(new_node.type_id, new_node.properties)
        target_spec = self._host.registry.resolve_spec(target_node.type_id, target_node.properties)
        target_port = resolver.port(target_node.node_id, str(target_port_key).strip())
        if target_port is None or not target_port.exposed:
            return False

        new_ports = [
            port
            for port in resolver.ports_for_node(new_node.node_id)
            if port.exposed and (compatible_port_keys is None or port.key in compatible_port_keys)
        ]
        candidates: list[dict[str, Any]] = []
        if is_neutral_flow_port(target_port):
            selected_port = _preferred_neutral_flow_port(
                node=new_node,
                peer_node=target_node,
                neutral_ports=_neutral_flow_ports(new_ports),
            )
            if selected_port is not None and resolver.compatibility(target_node.node_id, target_port.key, selected_port).is_compatible:
                candidates.append(
                    {
                        "source_node_id": target_node.node_id,
                        "source_port_key": target_port.key,
                        "target_node_id": new_node.node_id,
                        "target_port_key": selected_port.key,
                        "label": (
                            f"{target_spec.display_name}.{target_port.label or target_port.key} -> "
                            f"{new_spec.display_name}.{selected_port.label or selected_port.key}"
                        ),
                    }
                )
        elif target_port.direction == "in":
            if (
                append_requested
                and str(target_port.kind).strip().lower() == "flow"
                and not target_port_has_capacity(
                    edges=workspace.edges.values(),
                    node=target_node,
                    spec=target_spec,
                    workspace_nodes=workspace.nodes,
                    port_key=target_port.key,
                )
            ):
                return False
            for port in new_ports:
                if port.direction != "out":
                    continue
                if not resolver.compatibility(new_node.node_id, port.key, target_port).is_compatible:
                    continue
                candidates.append(
                    {
                        "source_node_id": new_node.node_id,
                        "source_port_key": port.key,
                        "target_node_id": target_node.node_id,
                        "target_port_key": target_port.key,
                        "label": (
                            f"{new_spec.display_name}.{port.label or port.key} -> "
                            f"{target_spec.display_name}.{target_port.label or target_port.key}"
                        ),
                    }
                )
        elif target_port.direction == "out":
            for port in new_ports:
                if port.direction != "in":
                    continue
                if not resolver.compatibility(target_node.node_id, target_port.key, port).is_compatible:
                    continue
                candidates.append(
                    {
                        "source_node_id": target_node.node_id,
                        "source_port_key": target_port.key,
                        "target_node_id": new_node.node_id,
                        "target_port_key": port.key,
                        "label": (
                            f"{target_spec.display_name}.{target_port.label or target_port.key} -> "
                            f"{new_spec.display_name}.{port.label or port.key}"
                        ),
                    }
                )
        else:
            return False

        selected = self._prompt_connection_candidate(
            title="Auto-Connect Port",
            label="Choose connection:",
            candidates=candidates,
        )
        if selected is None:
            return False

        try:
            self._host.scene.add_edge(
                selected["source_node_id"],
                selected["source_port_key"],
                selected["target_node_id"],
                selected["target_port_key"],
                bool(append_requested),
            )
            return True
        except (KeyError, ValueError):
            return False

    def auto_connect_dropped_node_to_edge(
        self, new_node_id: str, target_edge_id: str
    ) -> bool:
        workspace = self._active_workspace()
        if workspace is None:
            return False
        resolver = GraphTypeResolver(registry=self._host.registry, workspace_nodes=workspace.nodes, workspace_edges=workspace.edges.values())
        edge = workspace.edges.get(target_edge_id)
        new_node = workspace.nodes.get(new_node_id)
        if edge is None or new_node is None:
            return False

        source_node = workspace.nodes.get(edge.source_node_id)
        target_node = workspace.nodes.get(edge.target_node_id)
        if source_node is None or target_node is None:
            return False

        source_spec = self._host.registry.resolve_spec(source_node.type_id, source_node.properties)
        target_spec = self._host.registry.resolve_spec(target_node.type_id, target_node.properties)
        new_spec = self._host.registry.resolve_spec(new_node.type_id, new_node.properties)
        source_port = resolver.port(source_node.node_id, str(edge.source_port_key).strip())
        target_port = resolver.port(target_node.node_id, str(edge.target_port_key).strip())
        if source_port is None or target_port is None:
            return False

        new_ports = [
            port
            for port in resolver.ports_for_node(new_node.node_id)
            if port.exposed
        ]
        candidates: list[dict[str, Any]] = []
        if is_neutral_flow_port(source_port) and is_neutral_flow_port(target_port):
            neutral_ports = _neutral_flow_ports(new_ports)
            input_port = _preferred_neutral_flow_port(
                node=new_node,
                peer_node=source_node,
                neutral_ports=neutral_ports,
            )
            output_port = _preferred_neutral_flow_port(
                node=new_node,
                peer_node=target_node,
                neutral_ports=neutral_ports,
                excluded_keys={input_port.key} if input_port is not None else None,
            )
            if input_port is not None and output_port is not None:
                candidates.append(
                    {
                        "new_input_port": input_port.key,
                        "new_output_port": output_port.key,
                        "label": (
                            f"{source_spec.display_name}.{source_port.label or source_port.key} -> "
                            f"{new_spec.display_name}.{input_port.label or input_port.key}, "
                            f"{new_spec.display_name}.{output_port.label or output_port.key} -> "
                            f"{target_spec.display_name}.{target_port.label or target_port.key}"
                        ),
                    }
                )
        else:
            candidate_inputs = [
                port
                for port in new_ports
                if port.direction == "in"
                and resolver.compatibility(source_node.node_id, source_port.key, port).is_compatible
            ]
            for input_port in candidate_inputs:
                for output_port in new_ports:
                    if output_port.direction != "out" or not self._edge_insertion_is_valid(
                        workspace, edge, (new_node_id, input_port.key), (new_node_id, output_port.key)
                    ):
                        continue
                    candidates.append(
                        {
                            "new_input_port": input_port.key,
                            "new_output_port": output_port.key,
                            "label": (
                                f"{source_spec.display_name}.{source_port.label or source_port.key} -> "
                                f"{new_spec.display_name}.{input_port.label or input_port.key}, "
                                f"{new_spec.display_name}.{output_port.label or output_port.key} -> "
                                f"{target_spec.display_name}.{target_port.label or target_port.key}"
                            ),
                        }
                    )

        selected = self._prompt_connection_candidate(
            title="Auto-Insert On Edge",
            label="Choose inserted wiring:",
            candidates=candidates,
        )
        if selected is None:
            return False

        original = {
            "source_node_id": edge.source_node_id,
            "source_port_key": edge.source_port_key,
            "target_node_id": edge.target_node_id,
            "target_port_key": edge.target_port_key,
        }
        created_edge_ids: list[str] = []
        removed_original = False
        try:
            self._host.scene.remove_edge(target_edge_id)
            removed_original = True
            first_id = self._host.scene.add_edge(
                original["source_node_id"],
                original["source_port_key"],
                new_node_id,
                selected["new_input_port"],
            )
            created_edge_ids.append(first_id)
            second_id = self._host.scene.add_edge(
                new_node_id,
                selected["new_output_port"],
                original["target_node_id"],
                original["target_port_key"],
            )
            created_edge_ids.append(second_id)
            return True
        except (KeyError, ValueError):
            for edge_id in created_edge_ids:
                self._host.scene.remove_edge(edge_id)
            if removed_original:
                try:
                    self._host.scene.add_edge(
                        original["source_node_id"],
                        original["source_port_key"],
                        original["target_node_id"],
                        original["target_port_key"],
                    )
                except (KeyError, ValueError):
                    pass
            return False

    def _edge_insertion_is_valid(
        self,
        workspace: WorkspaceData,
        edge: EdgeInstance,
        input_endpoint: tuple[str, str],
        output_endpoint: tuple[str, str],
    ) -> bool:
        """Validate both new wires against the completed, proposed topology."""
        incoming, outgoing = edge.clone(), edge.clone()
        incoming.edge_id = "__insert_in_" + edge.edge_id
        outgoing.edge_id = "__insert_out_" + edge.edge_id
        incoming.target_node_id, incoming.target_port_key = input_endpoint
        outgoing.source_node_id, outgoing.source_port_key = output_endpoint
        retained = [current for current in workspace.edges.values()
                    if current.edge_id != edge.edge_id
                    and (current.target_node_id, current.target_port_key) != input_endpoint]
        kernel = GraphInvariantKernel(self._host.registry, workspace.nodes, [*retained, incoming, outgoing])
        memo = RegistryValidationPassMemo()
        try:
            for candidate in (incoming, outgoing):
                kernel.add_edge_or_raise(
                    source_node_id=candidate.source_node_id,
                    source_port_key=candidate.source_port_key,
                    target_node_id=candidate.target_node_id,
                    target_port_key=candidate.target_port_key,
                    append_requested=True,
                    capacity_excluded_edge_id=candidate.edge_id,
                    memo=memo,
                )
        except (KeyError, ValueError):
            return False
        return True

    def _connect_workflow_endpoint_to_port(
        self,
        endpoints: list[dict[str, str]],
        target_node_id: str,
        target_port_key: str,
        append_requested: bool = False,
        *,
        compatible_port_keys: tuple[str, ...] | None = None,
    ) -> bool:
        workspace = self._active_workspace()
        if workspace is None:
            return False
        resolver = GraphTypeResolver(registry=self._host.registry, workspace_nodes=workspace.nodes, workspace_edges=workspace.edges.values())
        target_node = workspace.nodes.get(str(target_node_id).strip())
        if target_node is None:
            return False
        target_spec = self._host.registry.resolve_spec(target_node.type_id, target_node.properties)
        target_port = resolver.port(target_node.node_id, str(target_port_key).strip())
        if target_port is None or not target_port.exposed:
            return False
        if (
            target_port.direction == "in"
            and append_requested
            and str(target_port.kind).strip().lower() == "flow"
            and not target_port_has_capacity(
                edges=workspace.edges.values(),
                node=target_node,
                spec=target_spec,
                workspace_nodes=workspace.nodes,
                port_key=target_port.key,
            )
        ):
            return False

        candidates: list[dict[str, Any]] = []
        for endpoint in endpoints:
            if compatible_port_keys is not None and endpoint["key"] not in compatible_port_keys:
                continue
            endpoint_node = workspace.nodes.get(endpoint["node_id"])
            if endpoint_node is None:
                continue
            endpoint_spec = self._host.registry.spec_or_none(endpoint_node.type_id)
            if endpoint_spec is None:
                continue
            endpoint_port = resolver.port(endpoint_node.node_id, endpoint["port_key"])
            if endpoint_port is None or not endpoint_port.exposed:
                continue
            if target_port.direction == "in":
                if endpoint_port.direction != "out" or not resolver.compatibility(endpoint_node.node_id, endpoint_port.key, target_port).is_compatible:
                    continue
                source_node_id, source_port_key = (
                    endpoint_node.node_id,
                    endpoint_port.key,
                )
                connected_target_node_id, connected_target_port_key = (
                    target_node.node_id,
                    target_port.key,
                )
            elif target_port.direction == "out":
                if endpoint_port.direction != "in" or not resolver.compatibility(target_node.node_id, target_port.key, endpoint_port).is_compatible:
                    continue
                if not target_port_has_capacity(
                    edges=workspace.edges.values(),
                    node=endpoint_node,
                    spec=endpoint_spec,
                    workspace_nodes=workspace.nodes,
                    port_key=endpoint_port.key,
                ):
                    continue
                source_node_id, source_port_key = target_node.node_id, target_port.key
                connected_target_node_id, connected_target_port_key = (
                    endpoint_node.node_id,
                    endpoint_port.key,
                )
            else:
                continue
            candidate = {
                "source_node_id": source_node_id,
                "source_port_key": source_port_key,
                "target_node_id": connected_target_node_id,
                "target_port_key": connected_target_port_key,
                "label": f"{endpoint_spec.display_name}.{endpoint_port.label or endpoint_port.key}",
            }
            if compatible_port_keys is not None:
                candidates.append(candidate)
                continue
            try:
                self._host.scene.add_edge(
                    candidate["source_node_id"],
                    candidate["source_port_key"],
                    candidate["target_node_id"],
                    candidate["target_port_key"],
                    bool(append_requested),
                )
                return True
            except (KeyError, ValueError):
                continue
        if compatible_port_keys is None:
            return False
        selected = self._prompt_connection_candidate(
            title="Auto-Connect Port", label="Choose connection:", candidates=candidates,
        )
        if selected is None:
            return False
        try:
            self._host.scene.add_edge(
                selected["source_node_id"], selected["source_port_key"],
                selected["target_node_id"], selected["target_port_key"],
                bool(append_requested),
            )
            return True
        except (KeyError, ValueError):
            return False

    def _connect_workflow_endpoints_to_edge(
        self,
        endpoints: list[dict[str, str]],
        target_edge_id: str,
    ) -> bool:
        workspace = self._active_workspace()
        if workspace is None:
            return False
        resolver = GraphTypeResolver(registry=self._host.registry, workspace_nodes=workspace.nodes, workspace_edges=workspace.edges.values())
        edge = workspace.edges.get(str(target_edge_id).strip())
        if edge is None:
            return False
        source_node = workspace.nodes.get(edge.source_node_id)
        target_node = workspace.nodes.get(edge.target_node_id)
        if source_node is None or target_node is None:
            return False
        source_spec = self._host.registry.resolve_spec(source_node.type_id, source_node.properties)
        target_spec = self._host.registry.resolve_spec(target_node.type_id, target_node.properties)
        source_port = resolver.port(source_node.node_id, edge.source_port_key)
        target_port = resolver.port(target_node.node_id, edge.target_port_key)
        if source_port is None or target_port is None:
            return False

        input_candidates, output_candidates = [], []
        for endpoint in endpoints:
            endpoint_port = resolver.port(endpoint["node_id"], endpoint["port_key"])
            if endpoint_port is None or not endpoint_port.exposed:
                continue
            pair = (endpoint["node_id"], endpoint["port_key"])
            if endpoint_port.direction == "in" and resolver.compatibility(source_node.node_id, source_port.key, endpoint_port).is_compatible:
                input_candidates.append(pair)
            elif endpoint_port.direction == "out":
                output_candidates.append(pair)
        pair = next(((input_endpoint, output_endpoint)
                     for input_endpoint in input_candidates for output_endpoint in output_candidates
                     if self._edge_insertion_is_valid(workspace, edge, input_endpoint, output_endpoint)), None)
        if pair is None:
            return False
        input_endpoint, output_endpoint = pair

        original = (
            edge.source_node_id,
            edge.source_port_key,
            edge.target_node_id,
            edge.target_port_key,
        )
        created_edge_ids: list[str] = []
        self._host.scene.remove_edge(edge.edge_id)
        try:
            created_edge_ids.append(
                self._host.scene.add_edge(
                    original[0], original[1], input_endpoint[0], input_endpoint[1]
                )
            )
            created_edge_ids.append(
                self._host.scene.add_edge(
                    output_endpoint[0], output_endpoint[1], original[2], original[3]
                )
            )
            return True
        except (KeyError, ValueError):
            for edge_id in created_edge_ids:
                self._host.scene.remove_edge(edge_id)
            try:
                self._host.scene.add_edge(*original)
            except (KeyError, ValueError):
                pass
            return False

    def request_drop_node_from_library(
        self,
        type_id: str,
        scene_x: float,
        scene_y: float,
        target_mode: str,
        target_node_id: str,
        target_port_key: str,
        target_edge_id: str,
        append_requested: bool = False,
        *,
        compatible_port_keys: tuple[str, ...] | None = None,
    ) -> ControllerResult[bool]:
        workspace = self._active_workspace()
        if workspace is None:
            return ControllerResult(False, "Workspace not found.", payload=False)

        with self._host.runtime_history.grouped_action(
            workspace.workspace_id,
            ACTION_ADD_NODE,
            workspace,
        ):
            mode = str(target_mode).strip().lower()
            custom_workflow_id = parse_custom_workflow_type_id(type_id)
            workflow_endpoints: list[dict[str, str]] = []
            if custom_workflow_id:
                created_node_id, workflow_endpoints = (
                    self.insert_custom_workflow_snapshot_with_endpoints(
                        custom_workflow_id,
                        scene_x,
                        scene_y,
                        map_published_shell_ports=mode == "port" and compatible_port_keys is not None,
                    )
                )
            else:
                created_node_id = self.insert_library_node(
                    type_id,
                    scene_x,
                    scene_y,
                    exposed_port_overrides=(
                        {"source": True}
                        if str(type_id).strip() == MEDIA_PANEL_TYPE_ID
                        and mode in {"port", "edge"}
                        else None
                    ),
                )
            if not created_node_id:
                return ControllerResult(
                    False, "Node could not be created.", payload=False
                )

            if mode == "port":
                if workflow_endpoints or (custom_workflow_id and compatible_port_keys is not None):
                    self._connect_workflow_endpoint_to_port(
                        workflow_endpoints,
                        str(target_node_id).strip(),
                        str(target_port_key).strip(),
                        append_requested,
                        compatible_port_keys=compatible_port_keys,
                    )
                else:
                    self.auto_connect_dropped_node_to_port(
                        created_node_id,
                        str(target_node_id).strip(),
                        str(target_port_key).strip(),
                        append_requested,
                        compatible_port_keys=compatible_port_keys,
                    )
            elif mode == "edge":
                if workflow_endpoints:
                    self._connect_workflow_endpoints_to_edge(
                        workflow_endpoints,
                        str(target_edge_id).strip(),
                    )
                else:
                    self.auto_connect_dropped_node_to_edge(
                        created_node_id,
                        str(target_edge_id).strip(),
                    )

        return ControllerResult(True, payload=True)


__all__ = ["WorkspaceDropConnectController", "retarget_fragment_roots"]
