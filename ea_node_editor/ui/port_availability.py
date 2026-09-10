from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.nodes.node_specs import NodeTypeSpec


PORT_AVAILABILITY_AVAILABLE = "available"
PORT_AVAILABILITY_AUTO = "auto"
PORT_AVAILABILITY_UNAVAILABLE = "unavailable"

_RuntimeOutputKind = str
_RuntimeAvailabilityByNode = dict[str, _RuntimeOutputKind]
_RuntimeAvailabilityByWorkspace = dict[str, _RuntimeAvailabilityByNode]
_RUNTIME_OUTPUT_KIND_BY_WORKSPACE: _RuntimeAvailabilityByWorkspace = {}


@dataclass(frozen=True, slots=True)
class PortAvailability:
    availability: str = PORT_AVAILABILITY_AVAILABLE
    reason: str = ""
    blocks_new_connections: bool = False
    warns_existing_connection: bool = False

    @property
    def unavailable(self) -> bool:
        return self.availability == PORT_AVAILABILITY_UNAVAILABLE


PortAvailabilityProvider = Callable[[WorkspaceData, NodeInstance, NodeTypeSpec], Mapping[str, PortAvailability]]

_PORT_AVAILABILITY_PROVIDERS: dict[str, PortAvailabilityProvider] = {}


def register_port_availability_provider(type_id: str, provider: PortAvailabilityProvider) -> None:
    normalized_type_id = str(type_id or "").strip()
    if not normalized_type_id:
        raise ValueError("Port availability provider type_id cannot be empty.")
    _PORT_AVAILABILITY_PROVIDERS[normalized_type_id] = provider


def port_availability_for_node(
    *,
    workspace: WorkspaceData,
    node: NodeInstance,
    spec: NodeTypeSpec,
) -> dict[str, PortAvailability]:
    provider = _PORT_AVAILABILITY_PROVIDERS.get(str(node.type_id))
    if provider is None:
        return {}
    return {
        str(key): availability
        for key, availability in provider(workspace, node, spec).items()
        if isinstance(availability, PortAvailability)
    }


def unavailable_connection_reason(
    *,
    workspace: WorkspaceData,
    source_node: NodeInstance,
    source_spec: NodeTypeSpec,
    source_port_key: str,
    target_node: NodeInstance,
    target_spec: NodeTypeSpec,
    target_port_key: str,
) -> str:
    source_availability = port_availability_for_node(
        workspace=workspace,
        node=source_node,
        spec=source_spec,
    ).get(source_port_key)
    if source_availability is not None and source_availability.blocks_new_connections:
        return source_availability.reason

    target_availability = port_availability_for_node(
        workspace=workspace,
        node=target_node,
        spec=target_spec,
    ).get(target_port_key)
    if target_availability is not None and target_availability.blocks_new_connections:
        return target_availability.reason
    return ""


def edge_availability_warning(
    *,
    workspace: WorkspaceData,
    edge: EdgeInstance,
    source_node: NodeInstance,
    source_spec: NodeTypeSpec,
    target_node: NodeInstance,
    target_spec: NodeTypeSpec,
) -> str:
    source_availability = port_availability_for_node(
        workspace=workspace,
        node=source_node,
        spec=source_spec,
    ).get(edge.source_port_key)
    if source_availability is not None and source_availability.warns_existing_connection:
        return source_availability.reason

    target_availability = port_availability_for_node(
        workspace=workspace,
        node=target_node,
        spec=target_spec,
    ).get(edge.target_port_key)
    if target_availability is not None and target_availability.warns_existing_connection:
        return target_availability.reason
    return ""


def observe_node_outputs(
    *,
    workspace_id: str,
    node_id: str,
    node_type_id: str,
    outputs: Mapping[str, Any],
) -> None:
    if str(node_type_id) != "tabular.input":
        return
    normalized_workspace_id = str(workspace_id or "").strip()
    normalized_node_id = str(node_id or "").strip()
    if not normalized_workspace_id or not normalized_node_id:
        return
    output_keys = {str(key) for key in outputs}
    if "table_data" in output_keys:
        _RUNTIME_OUTPUT_KIND_BY_WORKSPACE.setdefault(normalized_workspace_id, {})[normalized_node_id] = "table"
    elif "array_data" in output_keys:
        _RUNTIME_OUTPUT_KIND_BY_WORKSPACE.setdefault(normalized_workspace_id, {})[normalized_node_id] = "array"


def clear_port_availability_runtime_workspace(workspace_id: str) -> None:
    _RUNTIME_OUTPUT_KIND_BY_WORKSPACE.pop(str(workspace_id or "").strip(), None)


def clear_port_availability_runtime_node(workspace_id: str, node_id: str) -> None:
    workspace_key = str(workspace_id or "").strip()
    node_key = str(node_id or "").strip()
    workspace_state = _RUNTIME_OUTPUT_KIND_BY_WORKSPACE.get(workspace_key)
    if not workspace_state:
        return
    workspace_state.pop(node_key, None)
    if not workspace_state:
        _RUNTIME_OUTPUT_KIND_BY_WORKSPACE.pop(workspace_key, None)


def _tabular_connected_input_keys(workspace: WorkspaceData, node_id: str) -> set[str]:
    return {
        str(edge.target_port_key)
        for edge in workspace.edges.values()
        if edge.target_node_id == node_id
    }


def _tabular_runtime_kind(workspace_id: str, node_id: str) -> str:
    return _RUNTIME_OUTPUT_KIND_BY_WORKSPACE.get(workspace_id, {}).get(node_id, "")


def _tabular_source_kind_from_static_properties(node: NodeInstance) -> str:
    try:
        from ea_node_editor.addons.tabular_data.input_node import tabular_load_options_from_node_properties
        from ea_node_editor.addons.tabular_data.loader_cache_service import (
            shared_tabular_loader_cache_service,
        )
    except Exception:
        return ""

    raw_path = str(node.properties.get("path", "") or "").strip()
    if not raw_path:
        return ""
    path = Path(raw_path)
    if not path.exists() or not path.is_file():
        return ""
    try:
        options = tabular_load_options_from_node_properties(node.properties)
        scan = shared_tabular_loader_cache_service().scan_source(path, options)
    except Exception:
        return ""

    selected_object_id = str(options.selected_object or scan.selected_object_id or "").strip()
    if not selected_object_id:
        return ""
    selected = next((item for item in scan.objects if item.object_id == selected_object_id), None)
    if selected is None:
        return ""
    return "table" if selected.kind == "table" else "array"


def _tabular_output_availability(kind: str) -> dict[str, PortAvailability]:
    if kind == "table":
        return {
            "table_data": PortAvailability(PORT_AVAILABILITY_AVAILABLE),
            "array_data": PortAvailability(
                availability=PORT_AVAILABILITY_UNAVAILABLE,
                reason="Selected object is a table; choose an array dataset to use this output.",
                blocks_new_connections=True,
                warns_existing_connection=True,
            ),
        }
    if kind == "array":
        return {
            "table_data": PortAvailability(
                availability=PORT_AVAILABILITY_UNAVAILABLE,
                reason="Selected object is a dense array; choose a table object to use this output.",
                blocks_new_connections=True,
                warns_existing_connection=True,
            ),
            "array_data": PortAvailability(PORT_AVAILABILITY_AVAILABLE),
        }
    return {
        "table_data": PortAvailability(PORT_AVAILABILITY_AUTO),
        "array_data": PortAvailability(PORT_AVAILABILITY_AUTO),
    }


def _tabular_input_port_availability(
    workspace: WorkspaceData,
    node: NodeInstance,
    _spec: NodeTypeSpec,
) -> Mapping[str, PortAvailability]:
    connected_input_keys = _tabular_connected_input_keys(workspace, node.node_id)
    if "path" in connected_input_keys:
        kind = _tabular_runtime_kind(workspace.workspace_id, node.node_id)
    else:
        kind = _tabular_source_kind_from_static_properties(node)
    return _tabular_output_availability(kind)


register_port_availability_provider("tabular.input", _tabular_input_port_availability)


__all__ = [
    "PORT_AVAILABILITY_AUTO",
    "PORT_AVAILABILITY_AVAILABLE",
    "PORT_AVAILABILITY_UNAVAILABLE",
    "PortAvailability",
    "clear_port_availability_runtime_node",
    "clear_port_availability_runtime_workspace",
    "edge_availability_warning",
    "observe_node_outputs",
    "port_availability_for_node",
    "register_port_availability_provider",
    "unavailable_connection_reason",
]
