# Purpose: Open neutral CAD/FE scenes in the shared COREX viewer session surface.
# Map: feature_routes/viewer_session_overlay_fullscreen.md
# Tests: tests/test_engineering_viewer_node.py
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from ea_node_editor.common.scene_protocol import (
    COREX_SCENE_DATA_TYPE,
    COREX_SCENE_HANDLE_KIND,
    ENGINEERING_VIEWER_BACKEND_ID,
    empty_engineering_selection_set,
    normalize_engineering_selection_set,
    normalize_scene_styles,
    normalize_viewer_representation,
)
from ea_node_editor.nodes.builtins.geometry_primitives import (
    GEOMETRY_GROUP_DATA_TYPE_ID,
    OCP_BODY_DATA_TYPE_ID,
    _geometry_group_compound,
    _resolve_ocp_body,
    _resolve_geometry_group,
)
from ea_node_editor.nodes.execution_context import NodeInputNotReadyError, NodeResult
from ea_node_editor.nodes.node_specs import DynamicPortGroupSpec, PortSpec
from ea_node_editor.nodes.viewer_runtime_contracts import (
    MaterializeViewerDataCommand,
    OpenViewerSessionCommand,
    default_viewer_session_id,
    viewer_session_error,
    viewer_session_failed,
)
from ea_node_editor.runtime_contracts import coerce_runtime_handle_ref

ENGINEERING_VIEWER_NODE_TYPE_ID = "model.viewer"


def scene_input_ids(properties: Mapping[str, object]) -> tuple[str, ...]:
    values = properties.get("scene_input_ids", ["scene_1"])
    if (
        not isinstance(values, (list, tuple))
        or not values
        or any(not isinstance(key, str) or not key.startswith("scene_") or not key.isidentifier() for key in values)
        or len(set(values)) != len(values)
    ):
        raise ValueError("Model Viewer scene inputs require unique scene_ identifiers.")
    return tuple(values)


def resolve_scene_input_ports(properties: Mapping[str, object]) -> tuple[PortSpec, ...]:
    return tuple(
        PortSpec(
            key, "in", "data", COREX_SCENE_DATA_TYPE,
            label=f"Scene {index}", required=False,
            accepted_data_types=(OCP_BODY_DATA_TYPE_ID, GEOMETRY_GROUP_DATA_TYPE_ID),
            description="Prepared CAD/FE scene, OCP Body, or Geometry Group. Empty inputs are ignored.",
        )
        for index, key in enumerate(scene_input_ids(properties), start=1)
    )


def next_scene_input_id(_properties: Mapping[str, object]) -> str:
    # IDs are never reused, so removing and adding a scene cannot revive stale style/selection state.
    return f"scene_{uuid4().hex}"


SCENE_INPUT_GROUP = DynamicPortGroupSpec(
    group_id="scenes", property_key="scene_input_ids", direction="in",
    ports_resolver=resolve_scene_input_ports, key_factory=next_scene_input_id,
    minimum=1, rename_mode="label",
)


def _require_scene(value: object, *, label: str):  # noqa: ANN202
    runtime_ref = coerce_runtime_handle_ref(value)
    if (
        runtime_ref is None
        or runtime_ref.data_type_id != COREX_SCENE_DATA_TYPE
        or runtime_ref.kind != COREX_SCENE_HANDLE_KIND
    ):
        raise TypeError(
            f"Model Viewer requires {label} to be an engineering_scene input."
        )
    return runtime_ref


def _scene_fingerprint(scene_ref: Any) -> str:
    source = scene_ref.metadata.get("source")
    if not isinstance(source, dict):
        return ""
    return str(source.get("sha256", "")).strip()


def _prepare_scene(ctx, value: object, *, label: str):  # noqa: ANN001, ANN202
    runtime_ref = coerce_runtime_handle_ref(value)
    if runtime_ref is None:
        return _require_scene(value, label=label), None

    if runtime_ref.data_type_id == OCP_BODY_DATA_TYPE_ID:
        native_source_ref, shape = _resolve_ocp_body(ctx, value)
        source_name = "OCPBody"
    elif runtime_ref.data_type_id == GEOMETRY_GROUP_DATA_TYPE_ID:
        native_source_ref, group = _resolve_geometry_group(ctx, value)
        shape = _geometry_group_compound(ctx, group)
        source_name = "GeometryGroup"
    else:
        return _require_scene(value, label=label), None

    services = ctx.worker_services
    scene_ref = services.prepared_scene_runtime.prepare_cad_shape(
        shape,
        source_identity=(
            f"{native_source_ref.handle_id}:{native_source_ref.worker_generation}"
        ),
        owner_scope=services.run_owner_scope(ctx.run_id),
        source_name=source_name,
    )
    return scene_ref, native_source_ref


def _composition_fingerprint(layer_fingerprints: Mapping[str, str]) -> str:
    if not layer_fingerprints or any(not value for value in layer_fingerprints.values()):
        return ""
    return hashlib.sha256(
        json.dumps(list(layer_fingerprints.items()), separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _selection_output_for_scene(
    value: object,
    *,
    layer_fingerprints: dict[str, str],
) -> dict[str, Any]:
    current_layer_fingerprints = {
        str(layer_id).strip(): str(fingerprint).strip().casefold()
        for layer_id, fingerprint in layer_fingerprints.items()
        if str(layer_id).strip() and str(fingerprint).strip()
    }
    current_fingerprint = _composition_fingerprint(current_layer_fingerprints)
    if not current_fingerprint:
        return empty_engineering_selection_set()
    try:
        normalized = normalize_engineering_selection_set(value)
    except (TypeError, ValueError):
        return empty_engineering_selection_set(scene_fingerprint=current_fingerprint)
    if not normalized["selections"]:
        return empty_engineering_selection_set(scene_fingerprint=current_fingerprint)
    if normalized["scene_fingerprint"] != current_fingerprint:
        return empty_engineering_selection_set(scene_fingerprint=current_fingerprint)

    selections = []
    for entry in normalized["selections"]:
        if entry["scene_fingerprint"] != current_fingerprint:
            continue
        entities = [
            entity
            for entity in entry["entities"]
            if current_layer_fingerprints.get(entity["layer_id"])
            == entity["source_fingerprint"]
        ]
        if entities:
            selections.append({**entry, "entities": entities})
    published_name = str(normalized["published_name"])
    if published_name not in {entry["name"] for entry in selections}:
        published_name = ""
    return {
        "schema": normalized["schema"],
        "scene_fingerprint": current_fingerprint,
        "published_name": published_name,
        "selections": selections,
    }


def _metadata_sequence_sample(metadata: dict[str, Any], key: str) -> list[Any]:
    value = metadata.get(key, metadata.get(f"{key}_sample", ()))
    if not isinstance(value, (list, tuple)):
        return []
    return list(value)


def _metadata_sequence_count(
    metadata: dict[str, Any],
    key: str,
    sample: list[Any],
) -> int:
    try:
        return max(0, int(metadata.get(f"{key}_count", len(sample))))
    except (TypeError, ValueError):
        return len(sample)


def _scene_summary(scene_id: str, name: str, scene_ref: Any) -> dict[str, Any]:
    point_arrays = _metadata_sequence_sample(scene_ref.metadata, "point_arrays")
    cell_arrays = _metadata_sequence_sample(scene_ref.metadata, "cell_arrays")
    point_array_count = _metadata_sequence_count(
        scene_ref.metadata,
        "point_arrays",
        point_arrays,
    )
    cell_array_count = _metadata_sequence_count(
        scene_ref.metadata,
        "cell_arrays",
        cell_arrays,
    )
    hierarchy = [
        dict(item)
        for item in _metadata_sequence_sample(
            scene_ref.metadata,
            "hierarchy",
        )
        if isinstance(item, dict)
    ]
    hierarchy_count = _metadata_sequence_count(
        scene_ref.metadata,
        "hierarchy",
        hierarchy,
    )
    capabilities = {
        "attribute_colors": False,
        "body_edges": False,
        "camera": True,
        "camera_bookmarks": True,
        "clipping": True,
        "deformation": False,
        "export_3d": True,
        "live_field_controls": False,
        "live_query_transport": True,
        "measure": True,
        "mesh_edges": True,
        "minmax": bool(point_array_count or cell_array_count),
        "model_tree": bool(hierarchy_count),
        "playback": False,
        "probe": bool(point_array_count or cell_array_count),
        "saved_selections": True,
        "scalar_results": bool(point_array_count or cell_array_count),
        "scene_layers": True,
        "selection_isolate": True,
        "fit_selection": True,
        "orientation_triad": True,
        "projection": True,
        "topological_edges": False,
        "view_cube": True,
        "wireframe_visible_edges": True,
        "world_axes": True,
    }
    return {
        "id": scene_id,
        "name": name,
        "source_kind": str(scene_ref.metadata.get("source_kind", "")),
        "capabilities": capabilities,
        "model_tree": hierarchy,
        "result_name": (point_arrays + cell_arrays)[0]
        if point_arrays or cell_arrays
        else "Geometry",
        "location": (
            "Point/Cell"
            if point_array_count and cell_array_count
            else "Point"
            if point_array_count
            else "Cell"
            if cell_array_count
            else ""
        ),
        "unit": str(scene_ref.metadata.get("length_unit", "")),
        "length_unit": str(scene_ref.metadata.get("length_unit", "")),
    }


def _viewer_summary(scenes: Mapping[str, Any], labels: Mapping[str, str]) -> dict[str, Any]:
    layers = [_scene_summary(key, labels[key], ref) for key, ref in scenes.items()]
    source_kinds = {layer["source_kind"] for layer in layers}
    return {
        **{key: value for key, value in layers[0].items() if key not in {"id", "name"}},
        "viewer_kind": "engineering_scene",
        "source_kind": layers[0]["source_kind"] if len(source_kinds) == 1 else "mixed",
        "result_name": layers[0]["result_name"] if len(layers) == 1 else f"{len(layers)} scenes",
        "scene_layers": layers,
        "scene_fingerprint": _composition_fingerprint({key: _scene_fingerprint(ref) for key, ref in scenes.items()}),
        "capabilities": {
            key: any(layer["capabilities"].get(key, False) for layer in layers)
            for key in layers[0]["capabilities"]
        },
        "model_tree": [
            {**item, "layer_id": layer["id"]}
            for layer in layers for item in layer["model_tree"]
        ],
    }


def _open_engineering_viewer_session(
    ctx,
    *,
    scenes: Mapping[str, Any],
    native_sources: Mapping[str, Any],
    labels: Mapping[str, str],
):  # noqa: ANN001, ANN202
    service = getattr(ctx.worker_services, "viewer_session_service", None)
    if service is None:
        raise RuntimeError("Model Viewer requires viewer session services.")
    session_id = default_viewer_session_id(ctx.workspace_id, ctx.node_id)
    options = {
        "live_mode": "proxy",
        "playback_state": "paused",
        "step_index": 0,
        "show_mesh_edges": bool(ctx.properties.get("show_mesh_edges", False)),
        "show_attribute_colors": bool(
            ctx.properties.get("show_attribute_colors", False)
        ),
        "show_orientation_triad": bool(
            ctx.properties.get("show_orientation_triad", True)
        ),
        "show_view_cube": bool(ctx.properties.get("show_view_cube", True)),
        "show_world_axes": bool(ctx.properties.get("show_world_axes", False)),
        "viewer_background": str(
            ctx.properties.get("viewer_background", "theme") or "theme"
        ),
        "representation": normalize_viewer_representation(
            ctx.properties.get("representation")
        ),
        "scene_styles": {
            key: style for key, style in normalize_scene_styles(ctx.properties.get("scene_styles")).items()
            if key in scenes
        },
        "active_scene_id": next(iter(scenes)),
        "parallel_projection": bool(ctx.properties.get("parallel_projection", False)),
        "clip_enabled": bool(ctx.properties.get("clip_enabled", False)),
        "clip_axis": str(ctx.properties.get("clip_axis", "x") or "x"),
        "clip_offset": float(ctx.properties.get("clip_offset", 0.0) or 0.0),
    }
    data_refs = {
        "scene_order": list(scenes),
        "scene_labels": dict(labels),
        **{f"scene:{key}": ref for key, ref in scenes.items()},
        **{f"native_source:{key}": ref for key, ref in native_sources.items()},
    }
    opened = service.open_session(
        OpenViewerSessionCommand(
            workspace_id=ctx.workspace_id,
            node_id=ctx.node_id,
            session_id=session_id,
            backend_id=ENGINEERING_VIEWER_BACKEND_ID,
            data_refs=data_refs,
            playback_state={"state": "paused", "step_index": 0},
            summary=_viewer_summary(scenes, labels),
            options=options,
        )
    )
    if viewer_session_failed(opened):
        raise RuntimeError(viewer_session_error(opened))
    materialized = service.materialize_data(
        MaterializeViewerDataCommand(
            workspace_id=ctx.workspace_id,
            node_id=ctx.node_id,
            session_id=session_id,
            backend_id=ENGINEERING_VIEWER_BACKEND_ID,
            options={"output_profile": "memory"},
        )
    )
    if viewer_session_failed(materialized):
        raise RuntimeError(viewer_session_error(materialized))
    return service.session_handle(ctx.workspace_id, session_id)


def execute_engineering_viewer(ctx) -> NodeResult:  # noqa: ANN001
    scenes = {}
    native_sources = {}
    labels = {}
    port_labels = ctx.node_port_labels
    for index, key in enumerate(scene_input_ids(ctx.properties), start=1):
        value = ctx.inputs.get(key)
        if value is None:
            continue
        label = port_labels.get(key) or f"Scene {index}"
        try:
            scenes[key], native_source = _prepare_scene(ctx, value, label=label)
        except (TypeError, ValueError) as exc:
            raise type(exc)(f"{label} ({key}): {exc}") from exc
        labels[key] = label
        if native_source is not None:
            native_sources[key] = native_source
    if not scenes:
        raise NodeInputNotReadyError("Connect at least one scene to Model Viewer.")
    layer_fingerprints = {key: _scene_fingerprint(ref) for key, ref in scenes.items()}
    selections = _selection_output_for_scene(
        ctx.properties.get("saved_selections"),
        layer_fingerprints=layer_fingerprints,
    )
    session_payload = _open_engineering_viewer_session(
        ctx,
        scenes=scenes,
        native_sources=native_sources,
        labels=labels,
    )
    return NodeResult(
        outputs={
            "session": session_payload,
            "selections": selections,
        }
    )


__all__ = [
    "ENGINEERING_VIEWER_NODE_TYPE_ID",
    "execute_engineering_viewer",
]
