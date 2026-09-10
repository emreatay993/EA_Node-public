from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

GRAPH_NODE_GRADIENT_DIRECTIONS = ("north", "east", "south", "west", "radial")
DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION = "south"


@dataclass(frozen=True, slots=True)
class GraphNodeTokens:
    card_bg: str
    card_border: str
    card_selected_border: str
    card_gradient_enabled: bool
    card_gradient_color: str
    card_gradient_direction: str
    header_fg: str
    scope_badge_bg: str
    scope_badge_border: str
    scope_badge_fg: str
    inline_row_bg: str
    inline_row_border: str
    inline_label_fg: str
    inline_input_fg: str
    inline_input_bg: str
    inline_input_border: str
    inline_driven_fg: str
    port_label_fg: str
    port_interactive_fill: str
    port_interactive_border: str
    port_interactive_ring_fill: str
    port_interactive_ring_border: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GraphEdgeTokens:
    warning_stroke: str
    selected_stroke: str
    preview_stroke: str
    valid_drag_stroke: str
    invalid_drag_stroke: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GraphPortKindTokens:
    data: str
    flow: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GraphPortStateTokens:
    """Grip-style port flow-state colors."""

    valid: str
    waiting_outline: str
    idle_outline: str
    invalid_fill: str
    invalid_border: str
    invalid_muted_fill: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


GRAPH_PORT_KIND_TOKENS_V1 = GraphPortKindTokens(
    data="#7AA8FF",
    flow="#67D487",
)


GRAPH_STITCH_DARK_PORT_STATE_TOKENS_V1 = GraphPortStateTokens(
    valid="#67D487",
    waiting_outline="#E8A838",
    idle_outline="#6b7280",
    invalid_fill="#D94F4F",
    invalid_border="#FF8C74",
    invalid_muted_fill="#f4f6f9",
)


GRAPH_STITCH_LIGHT_PORT_STATE_TOKENS_V1 = GraphPortStateTokens(
    valid="#55C45D",
    waiting_outline="#D58E1E",
    idle_outline="#8a96a5",
    invalid_fill="#C93B3B",
    invalid_border="#E2574B",
    invalid_muted_fill="#ffffff",
)


GRAPH_STITCH_DARK_NODE_TOKENS_V1 = GraphNodeTokens(
    card_bg="#22252b",
    card_border="#363a42",
    card_selected_border="#60CDFF",
    card_gradient_enabled=False,
    card_gradient_color="#2c2f36",
    card_gradient_direction=DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    header_fg="#f0f4fb",
    scope_badge_bg="#1D8CE0",
    scope_badge_border="#60CDFF",
    scope_badge_fg="#f2f4f8",
    inline_row_bg="#282b32",
    inline_row_border="#3e434d",
    inline_label_fg="#d0d5de",
    inline_input_fg="#f0f2f5",
    inline_input_bg="#24272e",
    inline_input_border="#454b56",
    inline_driven_fg="#bdc5d3",
    port_label_fg="#d0d5de",
    port_interactive_fill="#FFDA6B",
    port_interactive_border="#FFE48B",
    port_interactive_ring_fill="#44FFC857",
    port_interactive_ring_border="#66FFE29A",
)


GRAPH_STITCH_LIGHT_NODE_TOKENS_V1 = GraphNodeTokens(
    card_bg="#fbfcfe",
    card_border="#c9d3de",
    card_selected_border="#1D8CE0",
    card_gradient_enabled=False,
    card_gradient_color="#f1f4f8",
    card_gradient_direction=DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    header_fg="#1b2733",
    scope_badge_bg="#b9dcf7",
    scope_badge_border="#1D8CE0",
    scope_badge_fg="#162231",
    inline_row_bg="#ffffff",
    inline_row_border="#ccd6e0",
    inline_label_fg="#5f6b7a",
    inline_input_fg="#17212b",
    inline_input_bg="#ffffff",
    inline_input_border="#c2cedb",
    inline_driven_fg="#4f5e70",
    port_label_fg="#5f6b7a",
    port_interactive_fill="#FFDA6B",
    port_interactive_border="#E7C35D",
    port_interactive_ring_fill="#33A7D98A",
    port_interactive_ring_border="#5598C971",
)


GRAPH_STITCH_DARK_EDGE_TOKENS_V1 = GraphEdgeTokens(
    warning_stroke="#E8A838",
    selected_stroke="#f0f4fb",
    preview_stroke="#60CDFF",
    valid_drag_stroke="#60CDFF",
    invalid_drag_stroke="#d0d5de",
)


GRAPH_STITCH_LIGHT_EDGE_TOKENS_V1 = GraphEdgeTokens(
    warning_stroke="#D58E1E",
    selected_stroke="#1b2733",
    preview_stroke="#1D8CE0",
    valid_drag_stroke="#1D8CE0",
    invalid_drag_stroke="#5f6b7a",
)


__all__ = [
    "DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION",
    "GRAPH_NODE_GRADIENT_DIRECTIONS",
    "GRAPH_PORT_KIND_TOKENS_V1",
    "GRAPH_STITCH_DARK_EDGE_TOKENS_V1",
    "GRAPH_STITCH_DARK_NODE_TOKENS_V1",
    "GRAPH_STITCH_DARK_PORT_STATE_TOKENS_V1",
    "GRAPH_STITCH_LIGHT_EDGE_TOKENS_V1",
    "GRAPH_STITCH_LIGHT_NODE_TOKENS_V1",
    "GRAPH_STITCH_LIGHT_PORT_STATE_TOKENS_V1",
    "GraphEdgeTokens",
    "GraphNodeTokens",
    "GraphPortKindTokens",
    "GraphPortStateTokens",
]
