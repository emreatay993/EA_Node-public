from __future__ import annotations

from ea_node_editor.nodes.node_specs import PortSpec

CARDINAL_PASSIVE_FLOW_PORTS = (
    PortSpec(
        "top",
        "neutral",
        "flow",
        "flow",
        side="top",
        allow_multiple_connections=True,
        description="Connects this passive item to a visual flow from its top edge.",
    ),
    PortSpec(
        "right",
        "neutral",
        "flow",
        "flow",
        side="right",
        allow_multiple_connections=True,
        description="Connects this passive item to a visual flow from its right edge.",
    ),
    PortSpec(
        "bottom",
        "neutral",
        "flow",
        "flow",
        side="bottom",
        allow_multiple_connections=True,
        description="Connects this passive item to a visual flow from its bottom edge.",
    ),
    PortSpec(
        "left",
        "neutral",
        "flow",
        "flow",
        side="left",
        allow_multiple_connections=True,
        description="Connects this passive item to a visual flow from its left edge.",
    ),
)


__all__ = ["CARDINAL_PASSIVE_FLOW_PORTS"]
