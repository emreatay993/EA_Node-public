from __future__ import annotations

"""Plot-kind payload contributions: embedded render policy and auto preview.

This module is the single insertion point for plot-node payload fields. The
same `apply_plot_surface_payload` runs in the full per-node build (via
`contribute`) and in the targeted connection-delta rebuild in `builder.py`.
"""

import copy
import hashlib
import json
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ea_node_editor.execution.plot_backend import AUTO_PLOT_BACKEND_ID
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.nodes.builtins.plot.generic import PLOT_NODE_DEFINITION_BY_TYPE_ID
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.ui_qml.graph_scene_payload.normalize import _bool_property
from ea_node_editor.ui_qml.plot_live_backend_resolution import builtin_plot_live_backend_id

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_scene_payload.factory import PayloadBuildContext
    from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge

_V1_PLOT_TYPES = frozenset(
    {
        "line",
        "scatter",
        "bar",
        "histogram",
        "heatmap",
        "contour",
        "surface",
        "point_cloud",
        "streamlines",
    }
)


def _normalize_plot_type(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def plot_type_for_values(*, type_id: str, surface_variant: str) -> str:
    """Spec-static plot-type resolution (empty string when not a plot kind)."""
    definition = PLOT_NODE_DEFINITION_BY_TYPE_ID.get(type_id)
    if definition is not None:
        raw_plot_type = definition.plot_type
    elif type_id.startswith("plot."):
        return ""
    else:
        raw_plot_type = surface_variant
    plot_type = _normalize_plot_type(raw_plot_type)
    return plot_type if plot_type in _V1_PLOT_TYPES else ""


def _plot_type_from_node_payload(*, node: Any, spec: NodeTypeSpec) -> str:
    return plot_type_for_values(
        type_id=str(getattr(node, "type_id", "") or "").strip(),
        surface_variant=str(getattr(spec, "surface_variant", "") or "").strip(),
    )


def _plot_embedded_render_policy(
    *,
    node: Any,
    spec: NodeTypeSpec,
    lightweight_canvas: bool,
) -> dict[str, Any] | None:
    plot_type = _plot_type_from_node_payload(node=node, spec=spec)
    if not plot_type:
        return None
    properties = getattr(node, "properties", {}) if hasattr(node, "properties") else {}
    requested_backend_id = (
        str(properties.get("backend") or AUTO_PLOT_BACKEND_ID).strip()
        if isinstance(properties, Mapping)
        else AUTO_PLOT_BACKEND_ID
    )
    render_in_canvas = _bool_property(
        properties.get("render_in_canvas") if isinstance(properties, Mapping) else None,
        True,
    )
    lightweight_canvas = bool(lightweight_canvas)
    suppressed_by = []
    if not render_in_canvas:
        suppressed_by.append("render_in_canvas")
    if lightweight_canvas:
        suppressed_by.append("lightweight_canvas")
    return {
        "plot_type": plot_type,
        "live_backend_id": builtin_plot_live_backend_id(
            plot_type=plot_type,
            requested_backend_id=requested_backend_id,
        ),
        "render_in_canvas": render_in_canvas,
        "lightweight_canvas": lightweight_canvas,
        "embedded_rendering_suppressed": bool(suppressed_by),
        "embedded_rendering_suppressed_by": suppressed_by,
    }


def _node_properties_with_defaults(*, node: Any, spec: NodeTypeSpec) -> dict[str, Any]:
    properties = {prop.key: copy.deepcopy(prop.default) for prop in getattr(spec, "properties", ())}
    raw_properties = getattr(node, "properties", {}) if hasattr(node, "properties") else {}
    if isinstance(raw_properties, Mapping):
        properties.update(copy.deepcopy(dict(raw_properties)))
    return properties


def _project_context_from_graph_theme_bridge(
    graph_theme_bridge: GraphThemeBridge | None,
) -> tuple[str | None, dict[str, Any] | None]:
    host = graph_theme_bridge.parent() if graph_theme_bridge is not None else None
    project_path = str(getattr(host, "project_path", "") or "").strip() if host is not None else ""
    project = getattr(getattr(host, "model", None), "project", None) if host is not None else None
    metadata = getattr(project, "metadata", None)
    return project_path or None, dict(metadata) if isinstance(metadata, dict) else None


# Tabular-input properties that change how the source parses or which columns
# feed the plot — part of the series signature.
_TABULAR_INPUT_SIGNATURE_PROPERTIES = (
    "path",
    "delimiter",
    "encoding",
    "header_row",
    "skip_rows",
    "schema_hints",
    "selected_object",
    "cache_policy",
    "allow_npz_archive_preview",
    "tabular_selected_columns",
    "array_slice_2d",
)

# Plot properties that change the rendered series/figure — part of the series
# signature (geometry/export-only properties excluded on purpose).
_PLOT_SIGNATURE_PROPERTIES = (
    "backend",
    "title",
    "x_label",
    "y_label",
    "z_label",
    "axis_limits",
    "log_scales",
    "grid",
    "legend",
    "colormap",
    "plot_options",
    "tabular_mapping",
)
_PLOT_SURFACE_REUSE_SAFE_CHANGED_FIELDS = frozenset({"node.title"})


def _signature_properties(properties: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: properties.get(key) for key in keys if key in properties}


def _reusable_plot_surface_payload(
    *,
    previous_payload: Mapping[str, Any] | None,
    changed_fields: frozenset[str] | None,
) -> dict[str, Any] | None:
    if previous_payload is None or changed_fields is None:
        return None
    if not changed_fields or not changed_fields.issubset(_PLOT_SURFACE_REUSE_SAFE_CHANGED_FIELDS):
        return None
    previous_plot_surface = previous_payload.get("plot_surface")
    if not isinstance(previous_plot_surface, Mapping):
        return None
    return copy.deepcopy(dict(previous_plot_surface))


def _apply_plot_policy_payload(payload: dict[str, Any], plot_policy: Mapping[str, Any]) -> None:
    payload["plot_surface"] = dict(plot_policy)
    payload["embedded_rendering_suppressed"] = bool(
        plot_policy.get("embedded_rendering_suppressed", False)
    )
    payload["embedded_rendering_suppressed_by"] = list(
        plot_policy.get("embedded_rendering_suppressed_by", [])
    )


def _source_edge_for_plot(node: Any, workspace: WorkspaceData) -> tuple[str, str] | None:
    node_id = str(getattr(node, "node_id", "") or "").strip()
    if not node_id:
        return None
    edge_values = workspace.edges.values() if isinstance(workspace.edges, Mapping) else workspace.edges
    for edge in edge_values:
        if (
            str(getattr(edge, "target_node_id", "") or "").strip() != node_id
            or str(getattr(edge, "target_port_key", "") or "").strip() != "series"
        ):
            continue
        source_node_id = str(getattr(edge, "source_node_id", "") or "").strip()
        source_port_key = str(getattr(edge, "source_port_key", "") or "").strip()
        if source_node_id:
            return source_node_id, source_port_key
    return None


def _upstream_input_node(
    node: Any,
    workspace: WorkspaceData,
    *,
    target_port_key: str,
    source_port_key: str,
) -> Any | None:
    node_id = str(getattr(node, "node_id", "") or "").strip()
    edge_values = workspace.edges.values() if isinstance(workspace.edges, Mapping) else workspace.edges
    for edge in edge_values:
        if (
            str(getattr(edge, "target_node_id", "") or "").strip() != node_id
            or str(getattr(edge, "target_port_key", "") or "").strip() != target_port_key
            or str(getattr(edge, "source_port_key", "") or "").strip() != source_port_key
        ):
            continue
        source_node = workspace.nodes.get(str(getattr(edge, "source_node_id", "") or "").strip())
        if source_node is not None and str(getattr(source_node, "type_id", "") or "").strip() == "tabular.input":
            return source_node
    return None


def _tabular_input_descriptor(
    source_node: Any,
    graph_theme_bridge: "GraphThemeBridge | None",
) -> dict[str, Any] | None:
    """Cheap (stat-only) description of a tabular input node's source."""

    properties = getattr(source_node, "properties", {}) or {}
    if not isinstance(properties, Mapping):
        return None
    raw_path = str(properties.get("path", "") or "").strip()
    if not raw_path:
        return None
    from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver

    project_path, project_metadata = _project_context_from_graph_theme_bridge(graph_theme_bridge)
    resolver = ProjectArtifactResolver(project_path=project_path, project_metadata=project_metadata)
    resolved = resolver.resolve_to_path(raw_path)
    if resolved is None:
        return None
    try:
        stat = os.stat(resolved)
        stamp = {"mtime_ns": int(stat.st_mtime_ns), "size": int(stat.st_size)}
    except OSError:
        return None
    return {
        "kind": "tabular_input",
        "node_id": str(getattr(source_node, "node_id", "") or ""),
        "resolved_path": str(resolved),
        "stamp": stamp,
        "properties": copy.deepcopy(
            _signature_properties(properties, _TABULAR_INPUT_SIGNATURE_PROPERTIES)
        ),
    }


def _plot_series_source_descriptor(
    *,
    node: Any,
    workspace: WorkspaceData,
    graph_theme_bridge: "GraphThemeBridge | None",
) -> dict[str, Any] | None:
    """Describe the tabular source connected to a plot node without touching it.

    The descriptor is JSON-safe, cheap to compute (one ``stat`` per source
    file), and carries everything the async build worker needs to resolve the
    ref later. Returns None when nothing plottable is connected.
    """

    source = _source_edge_for_plot(node, workspace)
    if source is None:
        return None
    source_node_id, source_port_key = source
    source_node = workspace.nodes.get(source_node_id)
    if source_node is None:
        return None
    source_type_id = str(getattr(source_node, "type_id", "") or "").strip()

    if source_type_id == "tabular.input" and source_port_key in {"table_data", "array_data"}:
        descriptor = _tabular_input_descriptor(source_node, graph_theme_bridge)
        if descriptor is None:
            return None
        descriptor["source_node_id"] = source_node_id
        descriptor["source_port_key"] = source_port_key
        return descriptor

    if source_type_id == "tabular.table_filter" and source_port_key == "window":
        input_node = _upstream_input_node(
            source_node, workspace, target_port_key="table_data", source_port_key="table_data"
        )
    elif source_type_id == "tabular.array_slice_2d" and source_port_key == "slice_2d":
        input_node = _upstream_input_node(
            source_node, workspace, target_port_key="array_data", source_port_key="array_data"
        )
    else:
        return None
    if input_node is None:
        return None
    input_descriptor = _tabular_input_descriptor(input_node, graph_theme_bridge)
    if input_descriptor is None:
        return None
    return {
        "kind": "table_filter" if source_type_id == "tabular.table_filter" else "array_slice_2d",
        "node_id": source_node_id,
        "source_node_id": source_node_id,
        "source_port_key": source_port_key,
        "properties": copy.deepcopy(dict(getattr(source_node, "properties", {}) or {})),
        "input": input_descriptor,
    }


def _series_signature(
    *,
    node_type_id: str,
    properties: Mapping[str, Any],
    descriptor: Mapping[str, Any],
) -> str:
    payload = {
        "node_type_id": node_type_id,
        "plot_properties": _signature_properties(properties, _PLOT_SIGNATURE_PROPERTIES),
        "source": descriptor,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _plot_auto_preview_payload(
    *,
    node: Any,
    spec: NodeTypeSpec,
    workspace: WorkspaceData,
    graph_theme_bridge: GraphThemeBridge | None,
) -> dict[str, Any] | None:
    """Pure-metadata auto-preview contribution (zero tabular data I/O).

    Publishes a staleness signature plus the cached render revision when the
    async build (PlotAutoPreviewService) has produced one; the render request
    itself never rides in the scene payload.
    """

    node_type_id = str(getattr(node, "type_id", "") or "").strip()
    if node_type_id not in PLOT_NODE_DEFINITION_BY_TYPE_ID:
        return None
    descriptor = _plot_series_source_descriptor(
        node=node,
        workspace=workspace,
        graph_theme_bridge=graph_theme_bridge,
    )
    if descriptor is None:
        return None
    properties = _node_properties_with_defaults(node=node, spec=spec)
    signature = _series_signature(
        node_type_id=node_type_id,
        properties=properties,
        descriptor=descriptor,
    )
    source_node_id = str(descriptor.get("source_node_id", "") or "")
    payload: dict[str, Any] = {
        "auto_preview": True,
        "series_signature": signature,
        "auto_preview_source_node_id": source_node_id,
    }

    from ea_node_editor.ui_qml.plot_auto_preview_service import shared_plot_render_request_cache

    workspace_id = str(getattr(workspace, "workspace_id", "") or "")
    node_id = str(getattr(node, "node_id", "") or "")
    entry = shared_plot_render_request_cache().get(workspace_id, node_id)
    if entry is not None and entry.signature == signature:
        if entry.error:
            payload["auto_preview_error"] = entry.error
            payload["render_revision"] = 0
            return payload
        payload["auto_preview_active"] = True
        payload["auto_preview_warnings"] = list(entry.warnings)
        payload["render_revision"] = entry.revision
        return payload
    payload["auto_preview_pending"] = True
    payload["render_revision"] = 0
    return payload


def apply_plot_surface_payload(
    payload: dict[str, Any],
    *,
    node: Any,
    spec: NodeTypeSpec,
    workspace: WorkspaceData,
    graph_theme_bridge: GraphThemeBridge | None,
    lightweight_canvas: bool = False,
    previous_payload: Mapping[str, Any] | None = None,
    changed_fields: frozenset[str] | None = None,
) -> None:
    plot_policy = _plot_embedded_render_policy(
        node=node,
        spec=spec,
        lightweight_canvas=lightweight_canvas,
    )
    if plot_policy is None:
        return
    reused_plot_surface = _reusable_plot_surface_payload(
        previous_payload=previous_payload,
        changed_fields=changed_fields,
    )
    if reused_plot_surface is not None:
        _apply_plot_policy_payload(payload, reused_plot_surface)
        return
    auto_preview_payload = _plot_auto_preview_payload(
        node=node,
        spec=spec,
        workspace=workspace,
        graph_theme_bridge=graph_theme_bridge,
    )
    if auto_preview_payload:
        plot_policy.update(auto_preview_payload)
    _apply_plot_policy_payload(payload, plot_policy)


def contribute(payload: dict[str, Any], ctx: "PayloadBuildContext") -> None:
    apply_plot_surface_payload(
        payload,
        node=ctx.node,
        spec=ctx.spec,
        workspace=ctx.workspace,
        graph_theme_bridge=ctx.graph_theme_bridge,
        lightweight_canvas=ctx.lightweight_canvas,
        previous_payload=ctx.previous_payload,
        changed_fields=ctx.changed_fields,
    )
