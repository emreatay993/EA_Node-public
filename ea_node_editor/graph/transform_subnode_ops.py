from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ea_node_editor.graph.effective_ports import effective_ports as resolve_effective_ports, port_side
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.graph.subnode_contract import (
    SUBNODE_INPUT_TYPE_ID,
    SUBNODE_OUTPUT_TYPE_ID,
    default_subnode_pin_label,
    is_subnode_shell_type,
    resolve_subnode_pin_definition,
)
from ea_node_editor.graph.transform_fragment_ops import build_subtree_fragment_payload_data
from ea_node_editor.nodes.registry import NodeRegistry


@dataclass(slots=True, frozen=True)
class SubnodeShellPinPlan:
    pin_type_id: str
    label: str
    x: float
    y: float


def plan_subnode_shell_pin_addition(
    *,
    workspace: WorkspaceData,
    shell_node_id: object,
    pin_type_id: object,
) -> SubnodeShellPinPlan | None:
    normalized_shell_node_id = str(shell_node_id).strip()
    normalized_pin_type_id = str(pin_type_id).strip()
    if not normalized_shell_node_id or not normalized_pin_type_id:
        return None

    shell_node = workspace.nodes.get(normalized_shell_node_id)
    if shell_node is None or not is_subnode_shell_type(shell_node.type_id):
        return None
    if normalized_pin_type_id not in {SUBNODE_INPUT_TYPE_ID, SUBNODE_OUTPUT_TYPE_ID}:
        return None

    same_direction_pins = [
        candidate
        for candidate in workspace.nodes.values()
        if candidate.parent_node_id == shell_node.node_id and str(candidate.type_id).strip() == normalized_pin_type_id
    ]

    base_label = default_subnode_pin_label(normalized_pin_type_id)
    existing_labels = {
        resolve_subnode_pin_definition(candidate.type_id, candidate.properties).label.strip().lower()
        for candidate in same_direction_pins
    }
    pin_label = base_label
    suffix = 2
    while pin_label.strip().lower() in existing_labels:
        pin_label = f"{base_label} {suffix}"
        suffix += 1

    y_positions = [float(candidate.y) for candidate in same_direction_pins]
    pin_y = (max(y_positions) + 90.0) if y_positions else (float(shell_node.y) + 60.0)
    pin_x = float(shell_node.x) + (40.0 if normalized_pin_type_id == SUBNODE_INPUT_TYPE_ID else 360.0)
    return SubnodeShellPinPlan(
        pin_type_id=normalized_pin_type_id,
        label=pin_label,
        x=pin_x,
        y=pin_y,
    )


def build_subnode_custom_workflow_snapshot_data(
    *,
    workspace: WorkspaceData,
    registry: NodeRegistry,
    shell_node_id: object,
) -> dict[str, Any] | None:
    normalized_shell_node_id = str(shell_node_id).strip()
    if not normalized_shell_node_id:
        return None
    shell_node = workspace.nodes.get(normalized_shell_node_id)
    if shell_node is None or not is_subnode_shell_type(shell_node.type_id):
        return None
    try:
        shell_spec = registry.get_spec(shell_node.type_id)
    except KeyError:
        return None

    fragment_payload = build_subtree_fragment_payload_data(
        workspace=workspace,
        selected_node_ids=[normalized_shell_node_id],
    )
    if fragment_payload is None:
        return None

    ports_payload: list[dict[str, Any]] = []
    for port in resolve_effective_ports(
        node=shell_node,
        spec=shell_spec,
        workspace_nodes=workspace.nodes,
    ):
        ports_payload.append(
            {
                "key": port.key,
                "label": port.label,
                "direction": port.direction,
                "kind": port.kind,
                "data_type": port.data_type,
                "accepted_data_types": list(port.accepted_data_types),
                "data_access": port.data_access,
                "side": port_side(port),
                "exposed": bool(port.exposed),
            }
        )

    return {
        "ports": ports_payload,
        "fragment": fragment_payload,
    }


__all__ = [
    "SubnodeShellPinPlan",
    "build_subnode_custom_workflow_snapshot_data",
    "plan_subnode_shell_pin_addition",
]
