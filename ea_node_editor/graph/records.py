from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NodeLinkRecord:
    link_id: str
    kind: str
    title: str
    target: str
    subtitle: str = ""
    target_workspace_id: str = ""
    target_node_id: str = ""

    def clone(self) -> "NodeLinkRecord":
        return copy.deepcopy(self)


@dataclass(slots=True)
class NodeCommentRecord:
    comment_id: str
    body: str
    author: str
    created_at: str
    updated_at: str
    resolved: bool = False
    unread: bool = True
    pinned: bool = False
    parent_id: str = ""

    def clone(self) -> "NodeCommentRecord":
        return copy.deepcopy(self)


@dataclass(slots=True)
class NodeInstance:
    node_id: str
    type_id: str
    title: str
    x: float
    y: float
    collapsed: bool = False
    expanded_settings_group_ids: tuple[str, ...] = ()
    properties: dict[str, Any] = field(default_factory=dict)
    exposed_ports: dict[str, bool] = field(default_factory=dict)
    port_labels: dict[str, str] = field(default_factory=dict)
    port_modifiers: dict[str, tuple[str, ...]] = field(default_factory=dict)
    principal_input_port_id: str | None = None
    visual_style: dict[str, Any] = field(default_factory=dict)
    links: list[NodeLinkRecord] = field(default_factory=list)
    comments: list[NodeCommentRecord] = field(default_factory=list)
    parent_node_id: str | None = None
    custom_width: float | None = None
    custom_height: float | None = None
    locked: bool = False

    def clone(self) -> "NodeInstance":
        return copy.deepcopy(self)


@dataclass(slots=True)
class EdgeInstance:
    edge_id: str
    source_node_id: str
    source_port_key: str
    target_node_id: str
    target_port_key: str
    enabled: bool = True
    input_order: int = 0
    label: str = ""
    visual_style: dict[str, Any] = field(default_factory=dict)

    def clone(self) -> "EdgeInstance":
        return copy.deepcopy(self)


__all__ = ["EdgeInstance", "NodeCommentRecord", "NodeInstance", "NodeLinkRecord"]
