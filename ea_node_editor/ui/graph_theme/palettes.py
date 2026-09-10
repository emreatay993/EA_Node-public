"""Extra built-in graph-theme palettes.

Each family provides a dark and light variant with harmonised node, edge,
and port-kind tokens.  Keeping them in a dedicated module
avoids bloating ``tokens.py`` while the registry picks them up automatically.
"""

from __future__ import annotations

from ea_node_editor.ui.graph_theme.tokens import (
    DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    GraphEdgeTokens,
    GraphNodeTokens,
    GraphPortKindTokens,
)

# ---------------------------------------------------------------------------
# Ocean  –  deep navy / teal accents
# ---------------------------------------------------------------------------

OCEAN_DARK_NODE_TOKENS = GraphNodeTokens(
    card_bg="#0f1a2e",
    card_border="#263852",
    card_selected_border="#38bdf8",
    card_gradient_enabled=False,
    card_gradient_color="#162640",
    card_gradient_direction=DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    header_fg="#e0ecf8",
    scope_badge_bg="#1470a8",
    scope_badge_border="#38bdf8",
    scope_badge_fg="#e8f4fc",
    inline_row_bg="#132236",
    inline_row_border="#2f4a6a",
    inline_label_fg="#9ab6d4",
    inline_input_fg="#e0ecf8",
    inline_input_bg="#0e1928",
    inline_input_border="#2f4a6a",
    inline_driven_fg="#7fa3c4",
    port_label_fg="#9ab6d4",
    port_interactive_fill="#38bdf8",
    port_interactive_border="#7dd3fc",
    port_interactive_ring_fill="#3038bdf857",
    port_interactive_ring_border="#5038bdf8",
)

OCEAN_LIGHT_NODE_TOKENS = GraphNodeTokens(
    card_bg="#f0f6fc",
    card_border="#afc8e0",
    card_selected_border="#0284c7",
    card_gradient_enabled=False,
    card_gradient_color="#dce8f4",
    card_gradient_direction=DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    header_fg="#0f1a2e",
    scope_badge_bg="#b8ddf5",
    scope_badge_border="#0284c7",
    scope_badge_fg="#0b1624",
    inline_row_bg="#ffffff",
    inline_row_border="#8dabc5",
    inline_label_fg="#476480",
    inline_input_fg="#0f1a2e",
    inline_input_bg="#ffffff",
    inline_input_border="#8dabc5",
    inline_driven_fg="#3b5670",
    port_label_fg="#476480",
    port_interactive_fill="#0284c7",
    port_interactive_border="#0369a1",
    port_interactive_ring_fill="#300284c7",
    port_interactive_ring_border="#500284c7",
)

OCEAN_DARK_EDGE_TOKENS = GraphEdgeTokens(
    warning_stroke="#f59e0b",
    selected_stroke="#e0ecf8",
    preview_stroke="#38bdf8",
    valid_drag_stroke="#38bdf8",
    invalid_drag_stroke="#9ab6d4",
)

OCEAN_LIGHT_EDGE_TOKENS = GraphEdgeTokens(
    warning_stroke="#d97706",
    selected_stroke="#0f1a2e",
    preview_stroke="#0284c7",
    valid_drag_stroke="#0284c7",
    invalid_drag_stroke="#476480",
)

OCEAN_PORT_KIND_TOKENS = GraphPortKindTokens(
    data="#7dd3fc",
    flow="#6ee7b7",
)

# ---------------------------------------------------------------------------
# Ember  –  warm charcoal / amber / copper
# ---------------------------------------------------------------------------

EMBER_DARK_NODE_TOKENS = GraphNodeTokens(
    card_bg="#1c1412",
    card_border="#4a3530",
    card_selected_border="#f97316",
    card_gradient_enabled=False,
    card_gradient_color="#2a1e1a",
    card_gradient_direction=DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    header_fg="#f5e6dd",
    scope_badge_bg="#b45309",
    scope_badge_border="#f97316",
    scope_badge_fg="#fef3e2",
    inline_row_bg="#231a16",
    inline_row_border="#5c433c",
    inline_label_fg="#c8a898",
    inline_input_fg="#f5e6dd",
    inline_input_bg="#1a1210",
    inline_input_border="#5c433c",
    inline_driven_fg="#b09080",
    port_label_fg="#c8a898",
    port_interactive_fill="#f97316",
    port_interactive_border="#fb923c",
    port_interactive_ring_fill="#30f9731657",
    port_interactive_ring_border="#50f9731698",
)

EMBER_LIGHT_NODE_TOKENS = GraphNodeTokens(
    card_bg="#fdf6f0",
    card_border="#d4b5a4",
    card_selected_border="#c2410c",
    card_gradient_enabled=False,
    card_gradient_color="#f5e6d8",
    card_gradient_direction=DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    header_fg="#2a1410",
    scope_badge_bg="#fed7aa",
    scope_badge_border="#c2410c",
    scope_badge_fg="#2a1410",
    inline_row_bg="#ffffff",
    inline_row_border="#b8977f",
    inline_label_fg="#7a5a48",
    inline_input_fg="#2a1410",
    inline_input_bg="#ffffff",
    inline_input_border="#b8977f",
    inline_driven_fg="#6a4838",
    port_label_fg="#7a5a48",
    port_interactive_fill="#c2410c",
    port_interactive_border="#9a3412",
    port_interactive_ring_fill="#30c2410c",
    port_interactive_ring_border="#50c2410c",
)

EMBER_DARK_EDGE_TOKENS = GraphEdgeTokens(
    warning_stroke="#eab308",
    selected_stroke="#f5e6dd",
    preview_stroke="#f97316",
    valid_drag_stroke="#f97316",
    invalid_drag_stroke="#c8a898",
)

EMBER_LIGHT_EDGE_TOKENS = GraphEdgeTokens(
    warning_stroke="#ca8a04",
    selected_stroke="#2a1410",
    preview_stroke="#c2410c",
    valid_drag_stroke="#c2410c",
    invalid_drag_stroke="#7a5a48",
)

EMBER_PORT_KIND_TOKENS = GraphPortKindTokens(
    data="#93c5fd",
    flow="#86efac",
)

# ---------------------------------------------------------------------------
# Verdant  –  deep forest greens / earthy tones
# ---------------------------------------------------------------------------

VERDANT_DARK_NODE_TOKENS = GraphNodeTokens(
    card_bg="#0f1a14",
    card_border="#26503a",
    card_selected_border="#34d399",
    card_gradient_enabled=False,
    card_gradient_color="#152e20",
    card_gradient_direction=DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    header_fg="#ddf0e6",
    scope_badge_bg="#0d7a4f",
    scope_badge_border="#34d399",
    scope_badge_fg="#e8fcf2",
    inline_row_bg="#122618",
    inline_row_border="#2e5c42",
    inline_label_fg="#8cbfa6",
    inline_input_fg="#ddf0e6",
    inline_input_bg="#0d1810",
    inline_input_border="#2e5c42",
    inline_driven_fg="#72a68a",
    port_label_fg="#8cbfa6",
    port_interactive_fill="#34d399",
    port_interactive_border="#6ee7b7",
    port_interactive_ring_fill="#3034d39957",
    port_interactive_ring_border="#5034d39998",
)

VERDANT_LIGHT_NODE_TOKENS = GraphNodeTokens(
    card_bg="#f0faf4",
    card_border="#a0ccb4",
    card_selected_border="#059669",
    card_gradient_enabled=False,
    card_gradient_color="#daf0e4",
    card_gradient_direction=DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    header_fg="#0f1a14",
    scope_badge_bg="#a7f3d0",
    scope_badge_border="#059669",
    scope_badge_fg="#0b1810",
    inline_row_bg="#ffffff",
    inline_row_border="#7aad94",
    inline_label_fg="#3d6e54",
    inline_input_fg="#0f1a14",
    inline_input_bg="#ffffff",
    inline_input_border="#7aad94",
    inline_driven_fg="#2d5a44",
    port_label_fg="#3d6e54",
    port_interactive_fill="#059669",
    port_interactive_border="#047857",
    port_interactive_ring_fill="#30059669",
    port_interactive_ring_border="#50059669",
)

VERDANT_DARK_EDGE_TOKENS = GraphEdgeTokens(
    warning_stroke="#f59e0b",
    selected_stroke="#ddf0e6",
    preview_stroke="#34d399",
    valid_drag_stroke="#34d399",
    invalid_drag_stroke="#8cbfa6",
)

VERDANT_LIGHT_EDGE_TOKENS = GraphEdgeTokens(
    warning_stroke="#d97706",
    selected_stroke="#0f1a14",
    preview_stroke="#059669",
    valid_drag_stroke="#059669",
    invalid_drag_stroke="#3d6e54",
)

VERDANT_PORT_KIND_TOKENS = GraphPortKindTokens(
    data="#7dd3fc",
    flow="#86efac",
)

# ---------------------------------------------------------------------------
# Amethyst  –  elegant violet / plum
# ---------------------------------------------------------------------------

AMETHYST_DARK_NODE_TOKENS = GraphNodeTokens(
    card_bg="#18121e",
    card_border="#3e2a56",
    card_selected_border="#a78bfa",
    card_gradient_enabled=False,
    card_gradient_color="#241a30",
    card_gradient_direction=DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    header_fg="#ece4f6",
    scope_badge_bg="#7c3aed",
    scope_badge_border="#a78bfa",
    scope_badge_fg="#f3edfc",
    inline_row_bg="#1e1628",
    inline_row_border="#4e3870",
    inline_label_fg="#b8a0d4",
    inline_input_fg="#ece4f6",
    inline_input_bg="#14101a",
    inline_input_border="#4e3870",
    inline_driven_fg="#a08abc",
    port_label_fg="#b8a0d4",
    port_interactive_fill="#a78bfa",
    port_interactive_border="#c4b5fd",
    port_interactive_ring_fill="#30a78bfa57",
    port_interactive_ring_border="#50a78bfa98",
)

AMETHYST_LIGHT_NODE_TOKENS = GraphNodeTokens(
    card_bg="#f8f4fc",
    card_border="#c8b4e0",
    card_selected_border="#7c3aed",
    card_gradient_enabled=False,
    card_gradient_color="#ede4f6",
    card_gradient_direction=DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    header_fg="#18121e",
    scope_badge_bg="#ddd6fe",
    scope_badge_border="#7c3aed",
    scope_badge_fg="#18101e",
    inline_row_bg="#ffffff",
    inline_row_border="#a892c4",
    inline_label_fg="#5e4878",
    inline_input_fg="#18121e",
    inline_input_bg="#ffffff",
    inline_input_border="#a892c4",
    inline_driven_fg="#4e3868",
    port_label_fg="#5e4878",
    port_interactive_fill="#7c3aed",
    port_interactive_border="#6d28d9",
    port_interactive_ring_fill="#307c3aed",
    port_interactive_ring_border="#507c3aed",
)

AMETHYST_DARK_EDGE_TOKENS = GraphEdgeTokens(
    warning_stroke="#f59e0b",
    selected_stroke="#ece4f6",
    preview_stroke="#a78bfa",
    valid_drag_stroke="#a78bfa",
    invalid_drag_stroke="#b8a0d4",
)

AMETHYST_LIGHT_EDGE_TOKENS = GraphEdgeTokens(
    warning_stroke="#d97706",
    selected_stroke="#18121e",
    preview_stroke="#7c3aed",
    valid_drag_stroke="#7c3aed",
    invalid_drag_stroke="#5e4878",
)

AMETHYST_PORT_KIND_TOKENS = GraphPortKindTokens(
    data="#93c5fd",
    flow="#86efac",
)

# ---------------------------------------------------------------------------
# Nord  –  arctic blue-greys (inspired by the Nord palette)
# ---------------------------------------------------------------------------

NORD_DARK_NODE_TOKENS = GraphNodeTokens(
    card_bg="#2e3440",
    card_border="#434c5e",
    card_selected_border="#88c0d0",
    card_gradient_enabled=False,
    card_gradient_color="#3b4252",
    card_gradient_direction=DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    header_fg="#eceff4",
    scope_badge_bg="#5e81ac",
    scope_badge_border="#88c0d0",
    scope_badge_fg="#eceff4",
    inline_row_bg="#333a47",
    inline_row_border="#4c566a",
    inline_label_fg="#d8dee9",
    inline_input_fg="#eceff4",
    inline_input_bg="#2e3440",
    inline_input_border="#4c566a",
    inline_driven_fg="#b8c4d4",
    port_label_fg="#d8dee9",
    port_interactive_fill="#88c0d0",
    port_interactive_border="#8fbcbb",
    port_interactive_ring_fill="#3088c0d057",
    port_interactive_ring_border="#5088c0d098",
)

NORD_LIGHT_NODE_TOKENS = GraphNodeTokens(
    card_bg="#eceff4",
    card_border="#b4bece",
    card_selected_border="#5e81ac",
    card_gradient_enabled=False,
    card_gradient_color="#d8dee9",
    card_gradient_direction=DEFAULT_GRAPH_NODE_GRADIENT_DIRECTION,
    header_fg="#2e3440",
    scope_badge_bg="#b4d0e0",
    scope_badge_border="#5e81ac",
    scope_badge_fg="#2e3440",
    inline_row_bg="#f8f9fb",
    inline_row_border="#97a5b8",
    inline_label_fg="#4c566a",
    inline_input_fg="#2e3440",
    inline_input_bg="#f8f9fb",
    inline_input_border="#97a5b8",
    inline_driven_fg="#434c5e",
    port_label_fg="#4c566a",
    port_interactive_fill="#5e81ac",
    port_interactive_border="#4c6d94",
    port_interactive_ring_fill="#305e81ac",
    port_interactive_ring_border="#505e81ac",
)

NORD_DARK_EDGE_TOKENS = GraphEdgeTokens(
    warning_stroke="#ebcb8b",
    selected_stroke="#eceff4",
    preview_stroke="#88c0d0",
    valid_drag_stroke="#88c0d0",
    invalid_drag_stroke="#d8dee9",
)

NORD_LIGHT_EDGE_TOKENS = GraphEdgeTokens(
    warning_stroke="#d08770",
    selected_stroke="#2e3440",
    preview_stroke="#5e81ac",
    valid_drag_stroke="#5e81ac",
    invalid_drag_stroke="#4c566a",
)

NORD_PORT_KIND_TOKENS = GraphPortKindTokens(
    data="#81a1c1",
    flow="#a3be8c",
)


__all__ = [
    "AMETHYST_DARK_EDGE_TOKENS",
    "AMETHYST_DARK_NODE_TOKENS",
    "AMETHYST_LIGHT_EDGE_TOKENS",
    "AMETHYST_LIGHT_NODE_TOKENS",
    "AMETHYST_PORT_KIND_TOKENS",
    "EMBER_DARK_EDGE_TOKENS",
    "EMBER_DARK_NODE_TOKENS",
    "EMBER_LIGHT_EDGE_TOKENS",
    "EMBER_LIGHT_NODE_TOKENS",
    "EMBER_PORT_KIND_TOKENS",
    "NORD_DARK_EDGE_TOKENS",
    "NORD_DARK_NODE_TOKENS",
    "NORD_LIGHT_EDGE_TOKENS",
    "NORD_LIGHT_NODE_TOKENS",
    "NORD_PORT_KIND_TOKENS",
    "OCEAN_DARK_EDGE_TOKENS",
    "OCEAN_DARK_NODE_TOKENS",
    "OCEAN_LIGHT_EDGE_TOKENS",
    "OCEAN_LIGHT_NODE_TOKENS",
    "OCEAN_PORT_KIND_TOKENS",
    "VERDANT_DARK_EDGE_TOKENS",
    "VERDANT_DARK_NODE_TOKENS",
    "VERDANT_LIGHT_EDGE_TOKENS",
    "VERDANT_LIGHT_NODE_TOKENS",
    "VERDANT_PORT_KIND_TOKENS",
]
