"""Runtime workspace DTOs plus explicit graph conversion adapters.

This module owns the execution-time document shape. Graph objects enter only
through the ``from_*`` assembly adapters; worker execution and persistence
codecs stay outside this DTO layer.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

from ea_node_editor.execution.transport_fields import (
    bool_field as _bool_field,
    float_field as _float_field,
    nonnegative_int_field as _nonnegative_int_field,
    string_field as _string_field,
)

if TYPE_CHECKING:
    from ea_node_editor.graph.workspace_state import WorkspaceData
    from ea_node_editor.graph.records import EdgeInstance, NodeInstance

_RUNTIME_NODE_FIELDS = frozenset(
    {
        "node_id",
        "type_id",
        "title",
        "x",
        "y",
        "collapsed",
        "properties",
        "exposed_ports",
        "locked_ports",
        "port_labels",
        "port_modifiers",
        "principal_input_port_id",
        "visual_style",
        "parent_node_id",
        "custom_width",
        "custom_height",
    }
)


def _require_mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise ValueError(f"{field_name} must be a mapping.")


def _require_sequence(value: Any, *, field_name: str) -> list[Any] | tuple[Any, ...]:
    if isinstance(value, (list, tuple)):
        return value
    raise ValueError(f"{field_name} must be a list.")


def _mapping_field(
    payload: Mapping[str, Any],
    field_name: str,
) -> dict[str, Any]:
    if field_name not in payload:
        return {}
    value = _require_mapping(payload[field_name], field_name=field_name)
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings.")
        normalized[key] = copy.deepcopy(item)
    return normalized


def _bool_mapping_field(
    payload: Mapping[str, Any],
    field_name: str,
) -> dict[str, bool]:
    values = _mapping_field(payload, field_name)
    for key, value in values.items():
        if not isinstance(value, bool):
            raise ValueError(f"{field_name}.{key} must be a boolean.")
    return values


def _string_mapping_field(
    payload: Mapping[str, Any],
    field_name: str,
) -> dict[str, str]:
    values = _mapping_field(payload, field_name)
    for key, value in values.items():
        if not isinstance(value, str):
            raise ValueError(f"{field_name}.{key} must be a string.")
    return values


def _modifier_mapping_field(
    payload: Mapping[str, Any],
    field_name: str,
) -> dict[str, tuple[str, ...]]:
    values = _mapping_field(payload, field_name)
    normalized: dict[str, tuple[str, ...]] = {}
    for key, value in values.items():
        modifiers = _require_sequence(value, field_name=f"{field_name}.{key}")
        if any(not isinstance(modifier, str) for modifier in modifiers):
            raise ValueError(f"{field_name}.{key} entries must be strings.")
        normalized[key] = tuple(modifiers)
    return normalized


def _validate_workspace_document_fields(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    document_fields = {
        str(key): copy.deepcopy(value)
        for key, value in payload.items()
        if isinstance(key, str)
    }
    if len(document_fields) != len(payload):
        raise ValueError("runtime_workspace.document_fields keys must be strings.")

    workspace_id = _string_field(
        payload,
        "workspace_id",
        strip=True,
    )
    if not workspace_id:
        raise ValueError(
            "runtime_workspace.document_fields.workspace_id must be a non-empty string."
        )
    document_fields["workspace_id"] = workspace_id
    if "name" in payload:
        document_fields["name"] = _string_field(
            payload,
            "name",
            strip=False,
        )
    if "dirty" in payload:
        document_fields["dirty"] = _bool_field(
            payload,
            "dirty",
            default=False,
        )
    if "active_view_id" in payload:
        document_fields["active_view_id"] = _string_field(
            payload,
            "active_view_id",
            strip=True,
        )
    if "views" in payload:
        views: list[dict[str, Any]] = []
        for index, raw_view in enumerate(
            _require_sequence(
                payload["views"],
                field_name="runtime_workspace.document_fields.views",
            )
        ):
            view = _require_mapping(
                raw_view,
                field_name=f"runtime_workspace.document_fields.views[{index}]",
            )
            normalized_view = {
                str(key): copy.deepcopy(value)
                for key, value in view.items()
                if isinstance(key, str)
            }
            if len(normalized_view) != len(view):
                raise ValueError(
                    "runtime_workspace.document_fields.views entries require "
                    "string keys."
                )
            view_id = _string_field(view, "view_id", strip=True)
            if not view_id:
                raise ValueError(
                    "runtime_workspace.document_fields.views entries require "
                    "a non-empty view_id."
                )
            normalized_view["view_id"] = view_id
            if "name" in view:
                normalized_view["name"] = _string_field(
                    view,
                    "name",
                    strip=False,
                )
            for numeric_field, default in (
                ("zoom", 1.0),
                ("pan_x", 0.0),
                ("pan_y", 0.0),
            ):
                if numeric_field in view:
                    normalized_view[numeric_field] = _float_field(
                        view,
                        numeric_field,
                        default=default,
                    )
            if "scope_path" in view:
                scope_path = _require_sequence(
                    view["scope_path"],
                    field_name=(
                        f"runtime_workspace.document_fields.views[{index}].scope_path"
                    ),
                )
                if any(not isinstance(item, str) for item in scope_path):
                    raise ValueError(
                        "runtime_workspace.document_fields.views"
                        f"[{index}].scope_path entries must be strings."
                    )
                normalized_view["scope_path"] = list(scope_path)
            views.append(normalized_view)
        document_fields["views"] = views
    return document_fields


_RUNTIME_EDGE_FIELDS = frozenset(
    {
        "edge_id",
        "source_node_id",
        "source_port_key",
        "target_node_id",
        "target_port_key",
        "enabled",
        "input_order",
        "label",
        "visual_style",
    }
)


@dataclass(slots=True, frozen=True)
class RuntimeNode:
    node_id: str
    type_id: str
    title: str
    x: float
    y: float
    collapsed: bool = False
    properties: dict[str, Any] = field(default_factory=dict)
    exposed_ports: dict[str, bool] = field(default_factory=dict)
    port_labels: dict[str, str] = field(default_factory=dict)
    port_modifiers: dict[str, tuple[str, ...]] = field(default_factory=dict)
    principal_input_port_id: str | None = None
    visual_style: dict[str, Any] = field(default_factory=dict)
    parent_node_id: str | None = None
    custom_width: float | None = None
    custom_height: float | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> RuntimeNode | None:
        node_id = _string_field(payload, "node_id", strip=True)
        type_id = _string_field(payload, "type_id", strip=True)
        if not node_id or not type_id:
            return None
        title = _string_field(payload, "title", default=type_id, strip=False)
        return cls(
            node_id=node_id,
            type_id=type_id,
            title=title if isinstance(title, str) else type_id,
            x=float(_float_field(payload, "x", default=0.0)),
            y=float(_float_field(payload, "y", default=0.0)),
            collapsed=_bool_field(payload, "collapsed", default=False),
            properties=_mapping_field(payload, "properties"),
            exposed_ports=_bool_mapping_field(payload, "exposed_ports"),
            port_labels=_string_mapping_field(payload, "port_labels"),
            port_modifiers=_modifier_mapping_field(payload, "port_modifiers"),
            principal_input_port_id=(
                _string_field(
                    payload,
                    "principal_input_port_id",
                    strip=True,
                    allow_none=True,
                )
                or None
            ),
            visual_style=_mapping_field(payload, "visual_style"),
            parent_node_id=(
                _string_field(
                    payload,
                    "parent_node_id",
                    strip=True,
                    allow_none=True,
                )
                or None
            ),
            custom_width=_float_field(
                payload,
                "custom_width",
                default=None,
                allow_none=True,
            ),
            custom_height=_float_field(
                payload,
                "custom_height",
                default=None,
                allow_none=True,
            ),
            extra_fields={
                str(key): copy.deepcopy(value)
                for key, value in payload.items()
                if str(key) not in _RUNTIME_NODE_FIELDS
            },
        )

    @classmethod
    def from_node_instance(cls, node: "NodeInstance") -> RuntimeNode:
        from ea_node_editor.graph.record_payloads import node_instance_to_mapping

        runtime_node = cls.from_mapping(node_instance_to_mapping(node))
        if runtime_node is None:
            raise ValueError(f"Unable to materialize runtime node: {node.node_id}")
        return runtime_node

    def to_document(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.extra_fields)
        payload.update(
            {
                "node_id": self.node_id,
                "type_id": self.type_id,
                "title": self.title,
                "x": self.x,
                "y": self.y,
                "collapsed": self.collapsed,
                "properties": copy.deepcopy(self.properties),
                "exposed_ports": copy.deepcopy(self.exposed_ports),
                "port_labels": copy.deepcopy(self.port_labels),
                "port_modifiers": {
                    key: list(modifiers)
                    for key, modifiers in self.port_modifiers.items()
                },
                "principal_input_port_id": self.principal_input_port_id,
                "visual_style": copy.deepcopy(self.visual_style),
                "parent_node_id": self.parent_node_id,
                "custom_width": self.custom_width,
                "custom_height": self.custom_height,
            }
        )
        if RuntimeNode.from_mapping(payload) is None:
            raise ValueError("runtime node document requires node_id and type_id.")
        return payload


@dataclass(slots=True, frozen=True)
class RuntimeEdge:
    source_node_id: str
    source_port_key: str
    target_node_id: str
    target_port_key: str
    edge_id: str = ""
    enabled: bool = True
    input_order: int = 0
    label: str = ""
    visual_style: dict[str, Any] = field(default_factory=dict)
    extra_fields: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> RuntimeEdge | None:
        source_node_id = _string_field(payload, "source_node_id", strip=True)
        source_port_key = _string_field(payload, "source_port_key", strip=True)
        target_node_id = _string_field(payload, "target_node_id", strip=True)
        target_port_key = _string_field(payload, "target_port_key", strip=True)
        if (
            not source_node_id
            or not source_port_key
            or not target_node_id
            or not target_port_key
        ):
            return None
        return cls(
            source_node_id=source_node_id,
            source_port_key=source_port_key,
            target_node_id=target_node_id,
            target_port_key=target_port_key,
            edge_id=str(_string_field(payload, "edge_id", strip=True)),
            enabled=_bool_field(payload, "enabled", default=True),
            input_order=_nonnegative_int_field(payload, "input_order"),
            label=str(_string_field(payload, "label", strip=False)),
            visual_style=_mapping_field(payload, "visual_style"),
            extra_fields={
                str(key): copy.deepcopy(value)
                for key, value in payload.items()
                if str(key) not in _RUNTIME_EDGE_FIELDS
            },
        )

    @classmethod
    def from_edge_instance(cls, edge: "EdgeInstance") -> RuntimeEdge:
        from ea_node_editor.graph.record_payloads import edge_instance_to_mapping

        runtime_edge = cls.from_mapping(edge_instance_to_mapping(edge))
        if runtime_edge is None:
            raise ValueError(f"Unable to materialize runtime edge: {edge.edge_id}")
        return runtime_edge

    def to_document(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.extra_fields)
        payload.update(
            {
                "source_node_id": self.source_node_id,
                "source_port_key": self.source_port_key,
                "target_node_id": self.target_node_id,
                "target_port_key": self.target_port_key,
                "enabled": self.enabled,
                "input_order": self.input_order,
            }
        )
        if self.edge_id:
            payload["edge_id"] = self.edge_id
            payload["label"] = self.label
            payload["visual_style"] = copy.deepcopy(self.visual_style)
        if RuntimeEdge.from_mapping(payload) is None:
            raise ValueError("runtime edge document requires complete endpoint fields.")
        return payload


@dataclass(slots=True, frozen=True)
class RuntimeWorkspace:
    document_fields: dict[str, Any] = field(default_factory=dict)
    nodes: tuple[RuntimeNode, ...] = field(default_factory=tuple)
    edges: tuple[RuntimeEdge, ...] = field(default_factory=tuple)

    @property
    def workspace_id(self) -> str:
        return str(self.document_fields.get("workspace_id", ""))

    @property
    def nodes_by_id(self) -> dict[str, RuntimeNode]:
        return {node.node_id: node for node in self.nodes}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> RuntimeWorkspace:
        document_fields_payload = payload.get("document_fields")
        document_fields_source = _require_mapping(
            document_fields_payload,
            field_name="runtime_workspace.document_fields",
        )
        document_fields = _validate_workspace_document_fields(document_fields_source)

        nodes: list[RuntimeNode] = []
        for raw_node in _require_sequence(
            payload.get("nodes"), field_name="runtime_workspace.nodes"
        ):
            _require_mapping(raw_node, field_name="runtime_workspace.nodes entry")
            node = RuntimeNode.from_mapping(raw_node)
            if node is None:
                raise ValueError(
                    "runtime_workspace.nodes entries require node_id and type_id."
                )
            nodes.append(node)

        edges: list[RuntimeEdge] = []
        for raw_edge in _require_sequence(
            payload.get("edges"), field_name="runtime_workspace.edges"
        ):
            _require_mapping(raw_edge, field_name="runtime_workspace.edges entry")
            edge = RuntimeEdge.from_mapping(raw_edge)
            if edge is None:
                raise ValueError(
                    "runtime_workspace.edges entries require complete endpoint fields."
                )
            edges.append(edge)

        return cls(
            document_fields=document_fields,
            nodes=tuple(nodes),
            edges=tuple(edges),
        )

    @classmethod
    def from_workspace_data(cls, workspace: "WorkspaceData") -> RuntimeWorkspace:
        from ea_node_editor.graph.hierarchy import normalize_scope_path

        workspace.ensure_default_view()
        active_view_id = workspace.active_view_id
        if active_view_id not in workspace.views:
            active_view_id = next(iter(workspace.views))

        document_fields = {
            "workspace_id": workspace.workspace_id,
            "name": workspace.name,
            "dirty": workspace.dirty,
            "active_view_id": active_view_id,
            "views": [
                {
                    "view_id": view.view_id,
                    "name": view.name,
                    "zoom": view.zoom,
                    "pan_x": view.pan_x,
                    "pan_y": view.pan_y,
                    "scope_path": list(
                        normalize_scope_path(workspace, view.scope_path)
                    ),
                }
                for view in workspace.views.values()
            ],
        }
        return cls(
            document_fields=document_fields,
            nodes=tuple(
                RuntimeNode.from_node_instance(node)
                for node in sorted(
                    workspace.nodes.values(), key=lambda item: item.node_id
                )
            ),
            edges=tuple(
                RuntimeEdge.from_edge_instance(edge)
                for edge in sorted(
                    workspace.edges.values(),
                    key=lambda item: (
                        item.target_node_id,
                        item.target_port_key,
                        item.input_order,
                        item.edge_id,
                    ),
                )
            ),
        )

    def to_document(self) -> dict[str, Any]:
        payload = {
            "document_fields": copy.deepcopy(self.document_fields),
            "nodes": [node.to_document() for node in self.nodes],
            "edges": [edge.to_document() for edge in self.edges],
        }
        RuntimeWorkspace.from_mapping(payload)
        return payload


__all__ = ["RuntimeEdge", "RuntimeNode", "RuntimeWorkspace"]
