from __future__ import annotations

import json
from typing import Any

from ea_node_editor.graph.fragment_payloads import (
    GRAPH_FRAGMENT_KIND,
    GRAPH_FRAGMENT_VERSION,
    build_graph_fragment_payload,
    normalize_edge_label,
    normalize_graph_fragment_payload,
    normalize_visual_style_payload,
)

GRAPH_FRAGMENT_MIME_TYPE = "application/x-ea-node-editor-graph-fragment+json"


def serialize_graph_fragment_payload(payload: Any) -> str | None:
    normalized = normalize_graph_fragment_payload(payload)
    if normalized is None:
        return None
    try:
        return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None


def parse_graph_fragment_payload(raw_text: str) -> dict[str, Any] | None:
    text = str(raw_text)
    if not text.strip():
        return None
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return None
    return normalize_graph_fragment_payload(decoded)


__all__ = [
    "GRAPH_FRAGMENT_KIND",
    "GRAPH_FRAGMENT_MIME_TYPE",
    "GRAPH_FRAGMENT_VERSION",
    "build_graph_fragment_payload",
    "normalize_edge_label",
    "normalize_graph_fragment_payload",
    "normalize_visual_style_payload",
    "parse_graph_fragment_payload",
    "serialize_graph_fragment_payload",
]
