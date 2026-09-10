from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.node_specs import NodeTypeSpec

NodeSizeResolver = Callable[
    [NodeInstance, NodeTypeSpec, Mapping[str, NodeInstance] | None],
    tuple[float, float],
]
NodeTypeSizeOverride = Callable[..., tuple[float, float]]

_DEFAULT_FALLBACK_NODE_WIDTH = 240.0
_DEFAULT_FALLBACK_NODE_HEIGHT = 160.0

# Per-type size overrides. Populated by plugin modules at import time via
# ``register_node_type_size_resolver``. Each override receives the
# base-resolved (width, height) — which already honors ``node.custom_width`` —
# and returns the final size. Used by ``_fallback_node_size``.
_NODE_TYPE_SIZE_RESOLVERS: dict[str, NodeTypeSizeOverride] = {}


def register_node_type_size_resolver(type_id: str, resolver: NodeTypeSizeOverride) -> None:
    """Register a width/height override for a single node type.

    ``resolver`` is called as ``resolver(node, spec, base_width=..., base_height=...)``
    and must return ``(width, height)``. ``base_width`` / ``base_height`` are the
    sizes that would otherwise be used (``node.custom_width`` or default).
    Registering the same ``type_id`` twice replaces the prior resolver — this
    keeps hot-reload and test isolation simple.
    """
    _NODE_TYPE_SIZE_RESOLVERS[type_id] = resolver


def unregister_node_type_size_resolver(type_id: str) -> None:
    """Remove a previously registered override. Safe if no resolver is registered."""
    _NODE_TYPE_SIZE_RESOLVERS.pop(type_id, None)


def resolve_node_type_size_override(
    node: NodeInstance,
    spec: NodeTypeSpec,
    *,
    base_width: float,
    base_height: float,
) -> tuple[float, float]:
    """Apply the registered per-type size override, if one exists."""
    override = _NODE_TYPE_SIZE_RESOLVERS.get(spec.type_id)
    if override is None:
        return max(1.0, float(base_width)), max(1.0, float(base_height))
    width, height = override(node, spec, base_width=base_width, base_height=base_height)
    return max(1.0, float(width)), max(1.0, float(height))


def _fallback_node_size(
    node: NodeInstance,
    spec: NodeTypeSpec,
    _workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    show_port_labels: bool = True,
) -> tuple[float, float]:
    del show_port_labels
    base_width = float(node.custom_width) if node.custom_width is not None else _DEFAULT_FALLBACK_NODE_WIDTH
    base_height = float(node.custom_height) if node.custom_height is not None else _DEFAULT_FALLBACK_NODE_HEIGHT
    return resolve_node_type_size_override(
        node,
        spec,
        base_width=base_width,
        base_height=base_height,
    )


@dataclass(slots=True)
class GraphBoundaryAdapters:
    node_size_resolver: NodeSizeResolver

    def node_size(
        self,
        node: NodeInstance,
        spec: NodeTypeSpec,
        workspace_nodes: Mapping[str, NodeInstance] | None = None,
        *,
        show_port_labels: bool = True,
    ) -> tuple[float, float]:
        return self.node_size_resolver(
            node,
            spec,
            workspace_nodes,
            show_port_labels=show_port_labels,
        )

def build_graph_boundary_adapters(
    *,
    node_size_resolver: NodeSizeResolver | None = None,
) -> GraphBoundaryAdapters:
    return GraphBoundaryAdapters(
        node_size_resolver=node_size_resolver or _fallback_node_size,
    )


def fallback_graph_boundary_adapters() -> GraphBoundaryAdapters:
    return build_graph_boundary_adapters()


__all__ = [
    "GraphBoundaryAdapters",
    "NodeSizeResolver",
    "NodeTypeSizeOverride",
    "build_graph_boundary_adapters",
    "fallback_graph_boundary_adapters",
    "register_node_type_size_resolver",
    "resolve_node_type_size_override",
    "unregister_node_type_size_resolver",
]
