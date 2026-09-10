# Purpose: Resolve topology and cached runtime facts into presentation-only
#          data-port flow states.
# Map: feature_routes/node_execution_visualization
# Tests: tests/test_port_flow_state.py
"""Grip-style port flow-state resolution for node surface presentation.

Maps what the scene payload already knows about a port (direction, kind,
connection, requiredness, inactivity) onto the visual "grip" states rendered
by GraphNodePortsLayer.qml:

- ``flowing``       filled with the valid-state green (data is moving)
- ``default``       outlined with the valid-state green (unconnected input
                    falling back to its default/property value)
- ``waiting``       outlined with the warning token (unconnected required
                    data input with nothing to fall back to)
- ``idle``          outlined with the neutral token (no data flowing)
- ``invalid``       filled with the error token (declared edge types do not
                    match)
- ``invalid_muted`` reserved for a future muted-invalid presentation; disabled
                    type-invalid wires intentionally remain ``invalid``.

Passive flow ports have no default/waiting semantics: they are either flowing
or idle.
"""

from __future__ import annotations

from collections.abc import Mapping

from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.runtime_contracts.data_tree import DataTree
from ea_node_editor.ui.support.solution_output_cache import (
    retained_output_record_from_records,
)

PORT_FLOW_STATES = (
    "flowing",
    "default",
    "waiting",
    "idle",
    "invalid",
    "invalid_muted",
)

_CONTROL_FLOW_KINDS = frozenset({"flow"})


def resolve_port_flow_state(
    *,
    direction: str,
    kind: str,
    connected: bool,
    required: bool,
    inactive: bool,
    has_default: bool = False,
) -> str:
    """Resolve the visual flow state for one port.

    This is the topology fallback stored in the scene payload. Retained
    runtime outputs refine it for the live canvas.
    """
    if connected:
        return "flowing"
    if inactive:
        return "idle"
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind in _CONTROL_FLOW_KINDS:
        return "idle"
    normalized_direction = str(direction or "").strip().lower()
    if normalized_direction == "out":
        return "idle"
    return "default" if has_default else ("waiting" if required else "idle")


def _latest_outputs(records: object, fact: object | None) -> Mapping[str, object]:
    latest_record = retained_output_record_from_records(
        records,
        fact,
        current_only=True,
    )
    if latest_record is None:
        return {}
    if not bool(latest_record.get("outputs_available", True)):
        return {}
    outputs = latest_record.get("outputs")
    return outputs if isinstance(outputs, Mapping) else {}


def _output_has_data(value: object) -> bool:
    return (
        isinstance(value, SettledPortResult)
        and str(value.status).strip().lower() == "value"
        and isinstance(value.value, DataTree)
        and value.value.item_count > 0
    )


def resolve_runtime_port_flow_states(
    *,
    node_payloads: object,
    edge_payloads: object,
    output_records_by_node: object,
    solution_facts_by_node: object = None,
) -> dict[str, dict[str, str]]:
    """Refine topology fallback states with retained runtime output presence."""
    records_by_node = (
        output_records_by_node if isinstance(output_records_by_node, Mapping) else {}
    )
    facts_by_node = (
        solution_facts_by_node if isinstance(solution_facts_by_node, Mapping) else {}
    )
    latest_outputs_by_node = {
        str(raw_node_id or "").strip(): _latest_outputs(
            records,
            facts_by_node.get(raw_node_id),
        )
        for raw_node_id, records in records_by_node.items()
        if str(raw_node_id or "").strip()
    }
    output_keys_by_node: dict[str, frozenset[str]] = {}
    for node_id, outputs in latest_outputs_by_node.items():
        output_keys_by_node[node_id] = frozenset(
            port_key
            for raw_port_key, value in outputs.items()
            if (port_key := str(raw_port_key or "").strip())
            and _output_has_data(value)
        )
    incoming_by_port: dict[tuple[str, str], list[tuple[str, str, bool, bool]]] = {}
    for edge in edge_payloads if isinstance(edge_payloads, (list, tuple)) else ():
        if not isinstance(edge, Mapping):
            continue
        source_node_id = str(edge.get("source_node_id", "") or "").strip()
        source_port_key = str(edge.get("source_port_key", "") or "").strip()
        target_node_id = str(edge.get("target_node_id", "") or "").strip()
        target_port_key = str(edge.get("target_port_key", "") or "").strip()
        if not all((source_node_id, source_port_key, target_node_id, target_port_key)):
            continue
        incoming_by_port.setdefault((target_node_id, target_port_key), []).append(
            (
                source_node_id,
                source_port_key,
                bool(edge.get("data_type_warning", False)),
                bool(edge.get("enabled", True)),
            )
        )

    lookup: dict[str, dict[str, str]] = {}
    for node in node_payloads if isinstance(node_payloads, (list, tuple)) else ():
        if not isinstance(node, Mapping):
            continue
        node_id = str(node.get("node_id", "") or "").strip()
        ports = node.get("ports")
        if not node_id or not isinstance(ports, (list, tuple)):
            continue
        node_states: dict[str, str] = {}
        node_output_keys = output_keys_by_node.get(node_id, frozenset())
        for port in ports:
            if not isinstance(port, Mapping):
                continue
            port_key = str(port.get("key", "") or "").strip()
            if not port_key:
                continue
            direction = str(port.get("direction", "") or "").strip().lower()
            kind = str(port.get("kind", "") or "").strip().lower()
            state = str(port.get("flow_state", "") or "").strip().lower()
            if state not in PORT_FLOW_STATES:
                state = resolve_port_flow_state(
                    direction=direction,
                    kind=kind,
                    connected=bool(port.get("connected", False)),
                    required=not bool(port.get("optional", False)),
                    inactive=bool(port.get("inactive", False)),
                    has_default=port.get("default_property") is not None,
                )
            if bool(port.get("inactive", False)):
                state = "idle"
            elif kind in _CONTROL_FLOW_KINDS:
                pass
            elif direction == "out":
                state = "flowing" if port_key in node_output_keys else "idle"
            elif direction == "in":
                incoming = incoming_by_port.get((node_id, port_key), ())
                if any(
                    data_type_warning and enabled
                    for _node_id, _port_key, data_type_warning, enabled in incoming
                ):
                    state = "invalid"
                else:
                    enabled_incoming = tuple(edge for edge in incoming if edge[3])
                    if not enabled_incoming:
                        state = (
                            "idle"
                            if kind in _CONTROL_FLOW_KINDS
                            else (
                                "default"
                                if port.get("default_property") is not None
                                else ("idle" if bool(port.get("optional", False)) else "waiting")
                            )
                        )
                        node_states[port_key] = state
                        continue
                    has_data = any(
                        source_port_key
                        in output_keys_by_node.get(source_node_id, frozenset())
                        for source_node_id, source_port_key, _warning, _enabled in enabled_incoming
                    )
                    if has_data:
                        state = "flowing"
                    elif kind in _CONTROL_FLOW_KINDS:
                        state = "idle"
                    else:
                        state = (
                            "idle" if bool(port.get("optional", False)) else "waiting"
                        )
            node_states[port_key] = state
        if node_states:
            lookup[node_id] = node_states
    return lookup


__all__ = [
    "PORT_FLOW_STATES",
    "resolve_port_flow_state",
    "resolve_runtime_port_flow_states",
]
