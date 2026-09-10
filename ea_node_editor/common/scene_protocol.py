# Purpose: Define the dependency-light neutral scene metadata shared by import nodes and execution.
# Map: subsystems/execution.md
# Tests: tests/test_engineering_import_nodes.py, tests/test_engineering_viewer_node.py
from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


COREX_SCENE_SCHEMA = "corex.scene_bundle.v1"
COREX_SCENE_DATA_TYPE = "COREX.Engineering.Scene"
COREX_SCENE_HANDLE_KIND = "corex.scene"
ENGINEERING_VIEWER_BACKEND_ID = "corex_scene"
ENGINEERING_SELECTION_SCHEMA = "engineering_selection_set.v2"
ENGINEERING_SELECTION_TOPOLOGY_SCHEMA = "corex.selection_topology.v1"
ENGINEERING_SELECTION_DATA_TYPE = "COREX.Engineering.SelectionSet"
SCENE_IMPORTER_VERSION = 4
VIEWER_COLORMAP_VALUES = (
    "jet",
    "viridis",
    "turbo",
    "rainbow",
    "plasma",
    "coolwarm",
    "gray",
)
VIEWER_RESULT_COMPONENT_VALUES = ("magnitude", "x", "y", "z")
VIEWER_SCALAR_RANGE_MODE_VALUES = ("auto", "custom")
VIEWER_BACKGROUND_VALUES = ("theme", "white", "black", "gray")
VIEWER_VIEW_OPTION_KEYS = (
    "show_mesh_edges",
    "colormap",
    "result_component",
    "scalar_range_mode",
    "scalar_range_min",
    "scalar_range_max",
    "show_scalar_bar",
    "deform_scale",
    "hover_probe",
    "show_minmax_markers",
    "viewer_background",
)

_ENGINEERING_SELECTION_CAPABILITIES = (
    "cad_vertex_selection",
    "cad_edge_selection",
    "cad_face_selection",
    "cad_body_selection",
    "fe_node_selection",
    "fe_element_face_selection",
    "fe_element_selection",
    "tangent_edge_propagation",
    "tangent_face_propagation",
)

_ENGINEERING_ENTITY_ID_PATTERNS = {
    "cad_vertex": re.compile(r"part:[1-9]\d*/vertex:[1-9]\d*"),
    "cad_edge": re.compile(r"part:[1-9]\d*/edge:[1-9]\d*"),
    "cad_face": re.compile(r"part:[1-9]\d*/face:[1-9]\d*"),
    "cad_body": re.compile(r"part:[1-9]\d*/body:[1-9]\d*"),
    "fe_node": re.compile(r"block:(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))*/node:-?\d+"),
    "fe_element": re.compile(
        r"block:(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))*/element:-?\d+"
    ),
    "fe_element_face": re.compile(
        r"block:(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))*/element:-?\d+/face:\d+"
    ),
}

FE_SCENE_SUFFIXES = (
    ".vtk",
    ".vtu",
    ".vtm",
    ".vtkhdf",
    ".e",
    ".exo",
    ".ex2",
    ".xdmf",
    ".xmf",
)
CAD_SCENE_SUFFIXES = (
    ".stl",
    ".step",
    ".stp",
    ".iges",
    ".igs",
    ".brep",
)
OCP_CAD_SCENE_SUFFIXES = frozenset({".step", ".stp", ".iges", ".igs", ".brep"})

_LENGTH_UNIT_TO_METRES = {
    "m": 1.0,
    "mm": 1.0e-3,
    "cm": 1.0e-2,
    "in": 0.0254,
    "ft": 0.3048,
}


def normalize_length_unit(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    aliases = {
        "meter": "m",
        "metre": "m",
        "meters": "m",
        "metres": "m",
        "millimeter": "mm",
        "millimetre": "mm",
        "millimeters": "mm",
        "millimetres": "mm",
        "centimeter": "cm",
        "centimetre": "cm",
        "centimeters": "cm",
        "centimetres": "cm",
        "inch": "in",
        "inches": "in",
        "foot": "ft",
        "feet": "ft",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in _LENGTH_UNIT_TO_METRES else ""


def length_unit_scale(from_unit: object, to_unit: object) -> float:
    source = normalize_length_unit(from_unit)
    target = normalize_length_unit(to_unit)
    if not source or not target:
        raise ValueError("Both source and target length units are required.")
    return _LENGTH_UNIT_TO_METRES[source] / _LENGTH_UNIT_TO_METRES[target]


def normalize_viewer_representation(value: object) -> str:
    normalized = str(value or "").strip().casefold().replace(" ", "_")
    aliases = {"surface_edges": "surface_with_edges", "edges": "surface_with_edges"}
    normalized = aliases.get(normalized, normalized)
    return (
        normalized
        if normalized
        in {
            "surface",
            "surface_with_edges",
            "wireframe",
            "wireframe_visible_edges",
            "points",
        }
        else "surface"
    )


def _normalize_viewer_choice(
    value: object,
    *,
    allowed: tuple[str, ...],
    default: str,
) -> str:
    normalized_default = str(default or allowed[0]).strip().casefold()
    if normalized_default not in allowed:
        normalized_default = allowed[0]
    normalized = str(value or "").strip().casefold()
    return normalized if normalized in allowed else normalized_default


def normalize_viewer_colormap(value: object, *, default: str = "jet") -> str:
    return _normalize_viewer_choice(
        value,
        allowed=VIEWER_COLORMAP_VALUES,
        default=default,
    )


def normalize_viewer_result_component(
    value: object,
    *,
    default: str = "magnitude",
) -> str:
    return _normalize_viewer_choice(
        value,
        allowed=VIEWER_RESULT_COMPONENT_VALUES,
        default=default,
    )


def normalize_viewer_scalar_range_mode(
    value: object,
    *,
    default: str = "auto",
) -> str:
    return _normalize_viewer_choice(
        value,
        allowed=VIEWER_SCALAR_RANGE_MODE_VALUES,
        default=default,
    )


def normalize_viewer_scalar_range_bound(value: object) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return ""
    return text if math.isfinite(parsed) else ""


def normalize_viewer_deform_scale(value: object, *, default: str = "off") -> str:
    normalized_default = str(default or "off").strip().casefold()
    if normalized_default not in {"off", "auto"}:
        normalized_default = "off"
    text = str(value if value is not None else "").strip().casefold()
    if not text:
        return normalized_default
    if text in {"off", "auto"}:
        return text
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return normalized_default
    return text if math.isfinite(parsed) and parsed > 0.0 else "off"


def normalize_viewer_background(value: object, *, default: str = "theme") -> str:
    return _normalize_viewer_choice(
        value,
        allowed=VIEWER_BACKGROUND_VALUES,
        default=default,
    )


def normalize_viewer_opacity(value: object, *, default: float) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        normalized = float(default)
    return min(1.0, max(0.0, normalized))


def normalize_scene_styles(value: object) -> dict[str, dict[str, Any]]:
    """Validate persisted and live per-scene appearance without importing UI code."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("Scene styles must be a mapping.")
    styles: dict[str, dict[str, Any]] = {}
    for scene_id, style in value.items():
        if not isinstance(scene_id, str) or not scene_id or scene_id != scene_id.strip():
            raise ValueError("Scene styles require non-empty scene IDs.")
        if not isinstance(style, Mapping) or set(style) - {"opacity", "color"}:
            raise ValueError("Scene styles support only opacity and color.")
        try:
            opacity = float(style.get("opacity", 1.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Scene opacity must be a finite number from 0 to 1.") from exc
        if not math.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ValueError("Scene opacity must be a finite number from 0 to 1.")
        color = style.get("color", "")
        if not isinstance(color, str) or (color and re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None):
            raise ValueError("Scene color must be #RRGGBB, or empty for Auto.")
        styles[scene_id] = {"opacity": opacity, "color": color.lower()}
    return styles


@dataclass(slots=True, frozen=True)
class SceneSourceMetadata:
    source_path: str
    resolved_path: str
    source_format: str
    size_bytes: int
    modified_time_ns: int
    sha256: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "resolved_path": self.resolved_path,
            "source_format": self.source_format,
            "size_bytes": self.size_bytes,
            "modified_time_ns": self.modified_time_ns,
            "sha256": self.sha256,
        }

    @classmethod
    def from_payload(cls, value: object) -> "SceneSourceMetadata":
        if not isinstance(value, Mapping):
            raise TypeError("Engineering scene source metadata must be a mapping.")
        payload = dict(value)
        return cls(
            source_path=str(payload["source_path"]),
            resolved_path=str(payload["resolved_path"]),
            source_format=str(payload["source_format"]),
            size_bytes=int(payload["size_bytes"]),
            modified_time_ns=int(payload["modified_time_ns"]),
            sha256=str(payload["sha256"]),
        )


@dataclass(slots=True, frozen=True)
class SceneDescriptor:
    scene_id: str
    source_kind: str
    source: SceneSourceMetadata
    display_artifact_path: str
    display_format: str
    cache_manifest_path: str
    dataset_kind: str
    point_count: int
    cell_count: int
    block_count: int
    bounds: tuple[float, float, float, float, float, float]
    length_unit: str
    coordinate_system: str = "model"
    importer_version: int = SCENE_IMPORTER_VERSION
    point_arrays: tuple[str, ...] = ()
    cell_arrays: tuple[str, ...] = ()
    hierarchy: tuple[dict[str, Any], ...] = ()
    geometry_assets: tuple[dict[str, Any], ...] = ()
    topology_mappings: dict[str, Any] = field(default_factory=dict)
    result_fields: tuple[dict[str, Any], ...] = ()
    time_steps: tuple[float, ...] = ()
    deformation: dict[str, Any] = field(default_factory=dict)
    capabilities: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    schema: str = COREX_SCENE_SCHEMA
    storage: str = "file"

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "scene_id": self.scene_id,
            "source_kind": self.source_kind,
            "source": self.source.to_payload(),
            "display_artifact_path": self.display_artifact_path,
            "display_format": self.display_format,
            "cache_manifest_path": self.cache_manifest_path,
            "dataset_kind": self.dataset_kind,
            "point_count": self.point_count,
            "cell_count": self.cell_count,
            "block_count": self.block_count,
            "bounds": list(self.bounds),
            "length_unit": self.length_unit,
            "coordinate_system": self.coordinate_system,
            "importer_version": self.importer_version,
            "point_arrays": list(self.point_arrays),
            "cell_arrays": list(self.cell_arrays),
            "hierarchy": [dict(value) for value in self.hierarchy],
            "geometry_assets": [dict(value) for value in self.geometry_assets],
            "topology_mappings": dict(self.topology_mappings),
            "result_fields": [dict(value) for value in self.result_fields],
            "time_steps": list(self.time_steps),
            "deformation": dict(self.deformation),
            "capabilities": list(self.capabilities),
            "provenance": dict(self.provenance),
        }
        if self.storage != "file":
            payload["storage"] = self.storage
        return payload

    @classmethod
    def from_payload(cls, value: object) -> "SceneDescriptor":
        payload = validate_scene_bundle(value)
        return cls(
            scene_id=str(payload["scene_id"]),
            source_kind=str(payload["source_kind"]),
            source=SceneSourceMetadata.from_payload(payload["source"]),
            display_artifact_path=str(payload["display_artifact_path"]),
            display_format=str(payload["display_format"]),
            cache_manifest_path=str(payload["cache_manifest_path"]),
            dataset_kind=str(payload["dataset_kind"]),
            point_count=int(payload["point_count"]),
            cell_count=int(payload["cell_count"]),
            block_count=int(payload["block_count"]),
            bounds=tuple(float(item) for item in payload["bounds"]),  # type: ignore[arg-type]
            length_unit=str(payload["length_unit"]),
            coordinate_system=str(payload["coordinate_system"]),
            importer_version=int(payload["importer_version"]),
            point_arrays=tuple(payload["point_arrays"]),
            cell_arrays=tuple(payload["cell_arrays"]),
            hierarchy=tuple(dict(item) for item in payload["hierarchy"]),
            geometry_assets=tuple(dict(item) for item in payload["geometry_assets"]),
            topology_mappings=dict(payload["topology_mappings"]),
            result_fields=tuple(dict(item) for item in payload["result_fields"]),
            time_steps=tuple(float(item) for item in payload["time_steps"]),
            deformation=dict(payload["deformation"]),
            capabilities=tuple(payload["capabilities"]),
            provenance=dict(payload["provenance"]),
            schema=str(payload["schema"]),
            storage=str(payload.get("storage", "file")),
        )


def _required_text(payload: Mapping[str, Any], key: str, *, context: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"{context} {key} is required.")
    return value


def _non_negative_int(payload: Mapping[str, Any], key: str, *, context: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        raise ValueError(f"{context} {key} must be a non-negative integer.")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} {key} must be a non-negative integer.") from exc
    if normalized < 0:
        raise ValueError(f"{context} {key} must be a non-negative integer.")
    return normalized


def _string_list(value: object, *, context: str) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{context} must be a list of strings.")
    normalized = [str(item).strip() for item in value]
    if any(not item for item in normalized) or len(set(normalized)) != len(normalized):
        raise ValueError(f"{context} must contain unique non-empty strings.")
    return normalized


def _mapping_list(value: object, *, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{context} must be a list of mappings.")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"{context} must contain only mappings.")
    return [dict(item) for item in value]


def _rgba8(value: object, *, context: str) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{context} must contain four byte values.")
    normalized: list[int] = []
    for item in value:
        if isinstance(item, bool):
            raise ValueError(f"{context} must contain four byte values.")
        try:
            component = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{context} must contain four byte values.") from exc
        if component < 0 or component > 255:
            raise ValueError(f"{context} components must be between 0 and 255.")
        normalized.append(component)
    return normalized


def _attribute_colors(value: object, *, context: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping.")
    colors = dict(value)
    if not isinstance(colors.get("available"), bool):
        raise ValueError(f"{context} available must be a boolean.")
    available = bool(colors["available"])
    array_name = str(colors.get("array_name", "")).strip()
    valid_mask_name = str(colors.get("valid_mask_name", "")).strip()
    association = str(colors.get("association", "")).strip().casefold()
    encoding = str(colors.get("encoding", "")).strip().casefold()
    source = str(colors.get("source", "")).strip()
    unsupported_reason = str(colors.get("unsupported_reason", "")).strip()
    component_count = _non_negative_int(
        colors,
        "component_count",
        context=context,
    )
    fallback_rgba = _rgba8(
        colors.get("fallback_rgba"),
        context=f"{context} fallback_rgba",
    )
    if available:
        if not array_name:
            raise ValueError(
                f"{context} array_name is required when colors are available."
            )
        if association not in {"point", "cell"}:
            raise ValueError(f"{context} association must be 'point' or 'cell'.")
        if component_count not in {3, 4}:
            raise ValueError(f"{context} component_count must be 3 or 4.")
        if encoding not in {"uint8", "float01"}:
            raise ValueError(f"{context} encoding must be 'uint8' or 'float01'.")
        if not source:
            raise ValueError(f"{context} source is required when colors are available.")
    elif not unsupported_reason:
        raise ValueError(
            f"{context} unsupported_reason is required when colors are unavailable."
        )
    colors.update(
        {
            "available": available,
            "array_name": array_name,
            "valid_mask_name": valid_mask_name,
            "association": association,
            "component_count": component_count,
            "encoding": encoding,
            "source": source,
            "fallback_rgba": fallback_rgba,
            "unsupported_reason": unsupported_reason,
        }
    )
    return colors


def validate_scene_bundle(value: object) -> dict[str, Any]:
    """Return a JSON-safe neutral scene bundle or raise a useful contract error."""

    if not isinstance(value, Mapping):
        raise TypeError("Engineering scene bundle must be a mapping.")
    payload = dict(value)
    if payload.get("schema") != COREX_SCENE_SCHEMA:
        raise ValueError(f"Engineering scene schema must be {COREX_SCENE_SCHEMA!r}.")
    source_kind = str(payload.get("source_kind", "")).strip().casefold()
    if source_kind not in {"cad", "fe"}:
        raise ValueError("Engineering scene source_kind must be 'cad' or 'fe'.")
    storage = str(payload.get("storage", "file")).strip().casefold()
    if storage not in {"file", "memory"}:
        raise ValueError("Engineering scene storage must be 'file' or 'memory'.")
    scene_id = _required_text(payload, "scene_id", context="Engineering scene")
    source = payload.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("Engineering scene source metadata is required.")
    normalized_source = dict(source)
    for key in ("source_path", "resolved_path", "source_format"):
        normalized_source[key] = _required_text(
            normalized_source,
            key,
            context="Engineering scene source",
        )
    for key in ("size_bytes", "modified_time_ns"):
        normalized_source[key] = _non_negative_int(
            normalized_source,
            key,
            context="Engineering scene source",
        )
    fingerprint = str(source.get("sha256", "")).strip().casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError(
            "Engineering scene source.sha256 must be a SHA-256 fingerprint."
        )
    bounds = payload.get("bounds")
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 6:
        raise ValueError("Engineering scene bounds must contain six values.")
    try:
        normalized_bounds = [float(item) for item in bounds]
    except (TypeError, ValueError) as exc:
        raise ValueError("Engineering scene bounds must be numeric.") from exc
    if not all(math.isfinite(item) for item in normalized_bounds):
        raise ValueError("Engineering scene bounds must be finite.")
    if any(
        normalized_bounds[index] > normalized_bounds[index + 1] for index in (0, 2, 4)
    ):
        raise ValueError("Engineering scene bounds minima must not exceed maxima.")
    length_unit = normalize_length_unit(payload.get("length_unit"))
    if not length_unit:
        raise ValueError("Engineering scene length_unit is required.")
    display_path = str(payload.get("display_artifact_path", "")).strip()
    if storage == "file" and not display_path:
        raise ValueError("Engineering scene display_artifact_path is required.")
    if storage == "memory" and display_path:
        raise ValueError(
            "Memory-backed engineering scenes cannot declare a display_artifact_path."
        )

    display_format = _required_text(
        payload,
        "display_format",
        context="Engineering scene",
    ).casefold()
    if not display_format.startswith("."):
        raise ValueError(
            "Engineering scene display_format must include its leading dot."
        )
    cache_manifest_path = str(payload.get("cache_manifest_path", "")).strip()
    if storage == "file" and not cache_manifest_path:
        raise ValueError("Engineering scene cache_manifest_path is required.")
    if storage == "memory" and cache_manifest_path:
        raise ValueError(
            "Memory-backed engineering scenes cannot declare a cache_manifest_path."
        )
    dataset_kind = _required_text(payload, "dataset_kind", context="Engineering scene")
    coordinate_system = _required_text(
        payload,
        "coordinate_system",
        context="Engineering scene",
    )
    importer_version = _non_negative_int(
        payload,
        "importer_version",
        context="Engineering scene",
    )
    if importer_version != SCENE_IMPORTER_VERSION:
        raise ValueError(
            f"Engineering scene importer_version must be {SCENE_IMPORTER_VERSION}."
        )

    point_arrays = _string_list(
        payload.get("point_arrays"),
        context="Engineering scene point_arrays",
    )
    cell_arrays = _string_list(
        payload.get("cell_arrays"),
        context="Engineering scene cell_arrays",
    )
    hierarchy = _mapping_list(
        payload.get("hierarchy"),
        context="Engineering scene hierarchy",
    )
    if not hierarchy:
        raise ValueError("Engineering scene hierarchy must contain a root entry.")
    hierarchy_ids = [
        _required_text(item, "id", context="Hierarchy entry") for item in hierarchy
    ]
    if len(set(hierarchy_ids)) != len(hierarchy_ids):
        raise ValueError("Engineering scene hierarchy IDs must be unique.")
    hierarchy_id_set = set(hierarchy_ids)
    if not any(not str(item.get("parent_id", "")).strip() for item in hierarchy):
        raise ValueError("Engineering scene hierarchy must contain a root entry.")
    for item in hierarchy:
        parent_id = str(item.get("parent_id", "")).strip()
        if parent_id and parent_id not in hierarchy_id_set:
            raise ValueError(f"Hierarchy parent_id {parent_id!r} does not exist.")
        _required_text(item, "name", context="Hierarchy entry")
        _required_text(item, "kind", context="Hierarchy entry")

    geometry_assets = _mapping_list(
        payload.get("geometry_assets"),
        context="Engineering scene geometry_assets",
    )
    asset_ids = [
        _required_text(item, "id", context="Geometry asset") for item in geometry_assets
    ]
    if len(set(asset_ids)) != len(asset_ids):
        raise ValueError("Engineering scene geometry asset IDs must be unique.")
    for item in geometry_assets:
        role = _required_text(item, "role", context="Geometry asset")
        asset_path = str(item.get("path", "")).strip()
        if storage == "file" and not asset_path:
            raise ValueError("Geometry asset path is required.")
        if storage == "memory" and asset_path:
            raise ValueError(
                "Memory-backed geometry assets cannot declare file paths."
            )
        item["path"] = asset_path
        asset_format = _required_text(
            item, "format", context="Geometry asset"
        ).casefold()
        if not asset_format.startswith("."):
            raise ValueError("Geometry asset format must include its leading dot.")
        content = _required_text(item, "content", context="Geometry asset").casefold()
        if content not in {
            "surface",
            "mesh",
            "topological_edges",
            "topological_vertices",
            "element_faces",
            "selection_topology",
        }:
            raise ValueError("Geometry asset content is not supported.")
        entity_arrays = item.get("entity_arrays")
        if not isinstance(entity_arrays, Mapping):
            raise ValueError("Geometry asset entity_arrays must be a mapping.")
        normalized_entity_arrays = {
            str(key).strip(): str(array_name).strip()
            for key, array_name in entity_arrays.items()
        }
        if any(
            not key or not array_name
            for key, array_name in normalized_entity_arrays.items()
        ):
            raise ValueError("Geometry asset entity_arrays must use non-empty names.")
        canonical_entity_arrays = {
            "part_index": "corex_part_index",
            "body_index": "corex_body_index",
            "face_index": "corex_face_index",
            "edge_index": "corex_edge_index",
            "vertex_index": "corex_vertex_index",
            "block_index": "corex_block_index",
            "node_index": "corex_node_index",
            "element_index": "corex_element_index",
            "element_face_index": "corex_element_face_index",
        }
        if any(
            canonical_entity_arrays.get(key) != array_name
            for key, array_name in normalized_entity_arrays.items()
        ):
            raise ValueError(
                "Geometry asset entity_arrays must use canonical COREX array names."
            )
        required_entity_arrays = {
            "surface": {
                "part_index": "corex_part_index",
                "body_index": "corex_body_index",
                "face_index": "corex_face_index",
            },
            "topological_edges": {
                "part_index": "corex_part_index",
                "edge_index": "corex_edge_index",
            },
            "topological_vertices": {
                "part_index": "corex_part_index",
                "vertex_index": "corex_vertex_index",
            },
            "element_faces": {
                "block_index": "corex_block_index",
                "element_index": "corex_element_index",
                "element_face_index": "corex_element_face_index",
            },
        }
        if (
            content in required_entity_arrays
            and normalized_entity_arrays != required_entity_arrays[content]
        ):
            raise ValueError(
                f"Geometry asset content {content!r} requires its canonical entity_arrays."
            )
        if role == "selection_identity" and (
            content != "mesh"
            or normalized_entity_arrays
            != {
                "block_index": "corex_block_index",
                "node_index": "corex_node_index",
                "element_index": "corex_element_index",
            }
        ):
            raise ValueError(
                "Selection-identity mesh assets require canonical block, node, and element arrays."
            )
        item["format"] = asset_format
        item["content"] = content
        item["attribute_colors"] = _attribute_colors(
            item.get("attribute_colors"),
            context="Geometry asset attribute_colors",
        )
        if content == "selection_topology":
            if asset_format != ".json":
                raise ValueError("Selection-topology assets must use JSON format.")
            if normalized_entity_arrays:
                raise ValueError(
                    "Selection-topology assets do not define entity arrays."
                )
            if item.get("schema") != ENGINEERING_SELECTION_TOPOLOGY_SCHEMA:
                raise ValueError(
                    "Selection-topology assets must declare the supported topology schema."
                )
            checksum = str(item.get("sha256", "")).strip().casefold()
            if not re.fullmatch(r"[0-9a-f]{64}", checksum):
                raise ValueError(
                    "Selection-topology assets require a SHA-256 checksum."
                )
            item["sha256"] = checksum
        item["entity_arrays"] = normalized_entity_arrays
    if not any(
        str(item.get("role", "")).strip() == "full"
        and str(item.get("content", "")).strip() in {"surface", "mesh"}
        for item in geometry_assets
    ):
        raise ValueError(
            "Engineering scene geometry_assets must contain a full-detail asset."
        )
    source_format = str(normalized_source["source_format"]).strip().casefold()
    required_assets = (
        {
            "coarse": "surface",
            "full": "surface",
            "topology_edges": "topological_edges",
            "topology_vertices": "topological_vertices",
            "selection_topology": "selection_topology",
        }
        if source_kind == "cad" and source_format in OCP_CAD_SCENE_SUFFIXES
        else {
            "full": "mesh",
            "selection_identity": "mesh",
            "element_faces": "element_faces",
            "selection_topology": "selection_topology",
        }
        if source_kind == "fe"
        else {}
    )
    for required_role, required_content in required_assets.items():
        matches = [
            item
            for item in geometry_assets
            if str(item.get("role", "")).strip().casefold() == required_role
            and str(item.get("content", "")).strip().casefold() == required_content
        ]
        if len(matches) != 1:
            raise ValueError(
                "Engineering scene importer version 4 requires exactly one "
                f"{required_role!r} {required_content!r} asset."
            )

    topology_mappings = payload.get("topology_mappings")
    if not isinstance(topology_mappings, Mapping):
        raise ValueError("Engineering scene topology_mappings must be a mapping.")
    result_fields = _mapping_list(
        payload.get("result_fields"),
        context="Engineering scene result_fields",
    )
    for item in result_fields:
        _required_text(item, "name", context="Result field")
        if str(item.get("location", "")).strip() not in {"point", "cell"}:
            raise ValueError("Result field location must be 'point' or 'cell'.")
        component_count = _non_negative_int(
            item, "component_count", context="Result field"
        )
        if component_count < 1:
            raise ValueError("Result field component_count must be positive.")
        components = _string_list(
            item.get("components"),
            context="Result field components",
        )
        expected_count = (
            component_count + 1 if component_count == 3 else component_count
        )
        if len(components) != expected_count:
            raise ValueError("Result field components do not match component_count.")

    raw_time_steps = payload.get("time_steps")
    if not isinstance(raw_time_steps, (list, tuple)):
        raise ValueError("Engineering scene time_steps must be a list.")
    try:
        time_steps = [float(item) for item in raw_time_steps]
    except (TypeError, ValueError) as exc:
        raise ValueError("Engineering scene time_steps must be numeric.") from exc
    if not all(math.isfinite(item) for item in time_steps):
        raise ValueError("Engineering scene time_steps must be finite.")
    if time_steps != sorted(set(time_steps)):
        raise ValueError("Engineering scene time_steps must be sorted and unique.")

    deformation = payload.get("deformation")
    if not isinstance(deformation, Mapping):
        raise ValueError("Engineering scene deformation must be a mapping.")
    normalized_deformation = dict(deformation)
    available = bool(normalized_deformation.get("available", False))
    enabled = bool(normalized_deformation.get("enabled", False))
    if enabled and not available:
        raise ValueError(
            "Engineering scene deformation cannot be enabled when unavailable."
        )
    try:
        scale_factor = float(normalized_deformation.get("scale_factor", 1.0))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Engineering scene deformation scale_factor must be finite."
        ) from exc
    if not math.isfinite(scale_factor) or scale_factor <= 0.0:
        raise ValueError(
            "Engineering scene deformation scale_factor must be positive and finite."
        )
    normalized_deformation.update(
        {"available": available, "enabled": enabled, "scale_factor": scale_factor}
    )

    capabilities = _string_list(
        payload.get("capabilities"),
        context="Engineering scene capabilities",
    )
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("Engineering scene provenance must be a mapping.")

    payload["scene_id"] = scene_id
    payload["source_kind"] = source_kind
    payload["source"] = normalized_source
    payload["source"]["sha256"] = fingerprint
    payload["bounds"] = normalized_bounds
    payload["length_unit"] = length_unit
    payload["display_artifact_path"] = display_path
    payload["display_format"] = display_format
    payload["cache_manifest_path"] = cache_manifest_path
    payload["dataset_kind"] = dataset_kind
    payload["coordinate_system"] = coordinate_system
    payload["importer_version"] = importer_version
    for key in ("point_count", "cell_count", "block_count"):
        payload[key] = _non_negative_int(payload, key, context="Engineering scene")
    payload["point_arrays"] = point_arrays
    payload["cell_arrays"] = cell_arrays
    payload["hierarchy"] = hierarchy
    payload["geometry_assets"] = geometry_assets
    payload["topology_mappings"] = dict(topology_mappings)
    payload["result_fields"] = result_fields
    payload["time_steps"] = time_steps
    payload["deformation"] = normalized_deformation
    payload["capabilities"] = capabilities
    payload["provenance"] = dict(provenance)
    if storage == "memory":
        payload["storage"] = storage
    else:
        payload.pop("storage", None)
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "Engineering scene bundle must contain only JSON-safe values."
        ) from exc
    return payload


def empty_engineering_selection_set(
    *,
    scene_fingerprint: str = "",
) -> dict[str, Any]:
    return {
        "schema": ENGINEERING_SELECTION_SCHEMA,
        "scene_fingerprint": str(scene_fingerprint).strip(),
        "published_name": "",
        "selections": [],
    }


def validate_engineering_selection_topology(value: object) -> dict[str, Any]:
    """Validate exact CAD/FE selection facts before capability projection."""

    if not isinstance(value, Mapping):
        raise TypeError("Engineering selection topology must be a mapping.")
    if value.get("schema") != ENGINEERING_SELECTION_TOPOLOGY_SCHEMA:
        raise ValueError("Engineering selection topology uses an unsupported schema.")

    raw_capabilities = value.get("capabilities")
    if not isinstance(raw_capabilities, Mapping):
        raise ValueError(
            "Engineering selection topology capabilities must be a mapping."
        )
    if set(raw_capabilities) != set(_ENGINEERING_SELECTION_CAPABILITIES):
        raise ValueError(
            "Engineering selection topology must declare every exact selection capability."
        )
    capabilities: dict[str, dict[str, Any]] = {}
    for capability_id in _ENGINEERING_SELECTION_CAPABILITIES:
        raw_capability = raw_capabilities[capability_id]
        if not isinstance(raw_capability, Mapping):
            raise ValueError(
                f"Engineering selection capability {capability_id!r} must be a mapping."
            )
        available = raw_capability.get("available")
        if not isinstance(available, bool):
            raise ValueError(
                f"Engineering selection capability {capability_id!r} availability must be boolean."
            )
        unsupported_reason = str(raw_capability.get("unsupported_reason", "")).strip()
        if available and unsupported_reason:
            raise ValueError(
                f"Available selection capability {capability_id!r} cannot have an unsupported reason."
            )
        if not available and not unsupported_reason:
            raise ValueError(
                f"Unavailable selection capability {capability_id!r} requires a reason."
            )
        capabilities[capability_id] = {
            "available": available,
            "unsupported_reason": unsupported_reason,
        }

    def mapping_list(raw: object, *, context: str) -> list[dict[str, Any]]:
        if raw is None:
            return []
        if not isinstance(raw, (list, tuple)):
            raise ValueError(f"{context} must be a list.")
        result: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, Mapping):
                raise ValueError(f"{context} entries must be mappings.")
            result.append(dict(item))
        return result

    def non_negative_int(raw: object, *, context: str) -> int:
        if isinstance(raw, bool):
            raise ValueError(f"{context} must be a non-negative integer.")
        try:
            result = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{context} must be a non-negative integer.") from exc
        if result < 0 or str(raw).strip() != str(result):
            raise ValueError(f"{context} must be a non-negative integer.")
        return result

    parts = mapping_list(value.get("parts"), context="Engineering CAD topology parts")
    entity_counts = {"vertices": 0, "edges": 0, "faces": 0, "bodies": 0}
    seen_part_indices: set[int] = set()
    cad_entity_ids = {
        "vertices": set(),
        "edges": set(),
        "faces": set(),
        "bodies": set(),
    }
    cad_vertex_edges: dict[str, list[str]] = {}
    cad_edge_vertices: dict[str, list[str]] = {}
    cad_edge_faces: dict[str, list[str]] = {}
    cad_face_edges: dict[str, list[str]] = {}
    for part in parts:
        part_index = non_negative_int(
            part.get("part_index"),
            context="Engineering CAD topology part_index",
        )
        if part_index < 1 or part_index in seen_part_indices:
            raise ValueError(
                "Engineering CAD topology part_index values must be unique and positive."
            )
        seen_part_indices.add(part_index)
        entities_by_plural: dict[str, list[dict[str, Any]]] = {}
        for plural, kind in (
            ("vertices", "vertex"),
            ("edges", "edge"),
            ("faces", "face"),
            ("bodies", "body"),
        ):
            entities = mapping_list(
                part.get(plural),
                context=f"Engineering CAD topology {plural}",
            )
            seen_ids: set[str] = set()
            for entity in entities:
                entity_id = str(entity.get("id", "")).strip()
                if not re.fullmatch(
                    rf"part:{part_index}/{kind}:[1-9]\d*",
                    entity_id,
                ):
                    raise ValueError(
                        f"Engineering CAD topology {kind} ID is not canonical: {entity_id!r}."
                    )
                if entity_id in seen_ids:
                    raise ValueError(
                        f"Engineering CAD topology {kind} IDs must be unique per part."
                    )
                seen_ids.add(entity_id)
                local_index = non_negative_int(
                    entity.get(f"{kind}_index"),
                    context=f"Engineering CAD topology {kind}_index",
                )
                if (
                    local_index < 1
                    or entity_id != f"part:{part_index}/{kind}:{local_index}"
                ):
                    raise ValueError(
                        f"Engineering CAD topology {kind} identity fields do not match."
                    )
                if (
                    non_negative_int(
                        entity.get("part_index"),
                        context=f"Engineering CAD topology {kind} part_index",
                    )
                    != part_index
                ):
                    raise ValueError(
                        f"Engineering CAD topology {kind} part_index does not match its part."
                    )
                if kind == "body" and str(entity.get("body_kind", "")).strip() not in {
                    "solid",
                    "shell",
                    "surface",
                }:
                    raise ValueError(
                        "Engineering CAD bodies require solid, shell, or surface body_kind."
                    )
            entity_counts[plural] += len(entities)
            entities_by_plural[plural] = entities

        entity_ids = {
            plural: {str(entity["id"]) for entity in entities}
            for plural, entities in entities_by_plural.items()
        }
        for plural, identifiers in entity_ids.items():
            cad_entity_ids[plural].update(identifiers)

        def references(
            entity: Mapping[str, Any],
            key: str,
            *,
            targets: str,
            context: str,
        ) -> list[str]:
            raw = entity.get(key)
            if not isinstance(raw, (list, tuple)):
                raise ValueError(f"Engineering CAD topology {context} must be a list.")
            result = [str(item).strip() for item in raw]
            if any(not item or item not in entity_ids[targets] for item in result):
                raise ValueError(
                    f"Engineering CAD topology {context} contains an unknown reference."
                )
            if len(result) != len(set(result)):
                raise ValueError(
                    f"Engineering CAD topology {context} contains duplicate references."
                )
            return result

        vertices = {str(item["id"]): item for item in entities_by_plural["vertices"]}
        edges = {str(item["id"]): item for item in entities_by_plural["edges"]}
        faces = {str(item["id"]): item for item in entities_by_plural["faces"]}
        bodies = {str(item["id"]): item for item in entities_by_plural["bodies"]}
        vertex_edges = {
            entity_id: references(
                entity,
                "edge_ids",
                targets="edges",
                context="vertex edge_ids",
            )
            for entity_id, entity in vertices.items()
        }
        edge_vertices = {
            entity_id: references(
                entity,
                "vertex_ids",
                targets="vertices",
                context="edge vertex_ids",
            )
            for entity_id, entity in edges.items()
        }
        edge_faces = {
            entity_id: references(
                entity,
                "face_ids",
                targets="faces",
                context="edge face_ids",
            )
            for entity_id, entity in edges.items()
        }
        face_edges = {
            entity_id: references(
                entity,
                "edge_ids",
                targets="edges",
                context="face edge_ids",
            )
            for entity_id, entity in faces.items()
        }
        face_bodies = {
            entity_id: references(
                entity,
                "body_ids",
                targets="bodies",
                context="face body_ids",
            )
            for entity_id, entity in faces.items()
        }
        body_faces = {
            entity_id: references(
                entity,
                "face_ids",
                targets="faces",
                context="body face_ids",
            )
            for entity_id, entity in bodies.items()
        }
        cad_vertex_edges.update(vertex_edges)
        cad_edge_vertices.update(edge_vertices)
        cad_edge_faces.update(edge_faces)
        cad_face_edges.update(face_edges)
        for vertex_id, edge_ids in vertex_edges.items():
            if any(vertex_id not in edge_vertices[edge_id] for edge_id in edge_ids):
                raise ValueError(
                    "Engineering CAD vertex-edge adjacency is not reciprocal."
                )
        for edge_id, vertex_ids in edge_vertices.items():
            if any(edge_id not in vertex_edges[vertex_id] for vertex_id in vertex_ids):
                raise ValueError(
                    "Engineering CAD edge-vertex adjacency is not reciprocal."
                )
        for edge_id, face_ids in edge_faces.items():
            if any(edge_id not in face_edges[face_id] for face_id in face_ids):
                raise ValueError(
                    "Engineering CAD edge-face adjacency is not reciprocal."
                )
        for face_id, edge_ids in face_edges.items():
            if any(face_id not in edge_faces[edge_id] for edge_id in edge_ids):
                raise ValueError(
                    "Engineering CAD face-edge adjacency is not reciprocal."
                )
        for face_id, body_ids in face_bodies.items():
            if any(face_id not in body_faces[body_id] for body_id in body_ids):
                raise ValueError(
                    "Engineering CAD face-body ownership is not reciprocal."
                )
        for body_id, face_ids in body_faces.items():
            if any(body_id not in face_bodies[face_id] for face_id in face_ids):
                raise ValueError(
                    "Engineering CAD body-face ownership is not reciprocal."
                )

    blocks = mapping_list(value.get("blocks"), context="Engineering FE topology blocks")
    seen_block_indices: set[int] = set()
    block_totals = {"nodes": 0, "elements": 0, "element_faces": 0}
    for block in blocks:
        block_index = non_negative_int(
            block.get("block_index"),
            context="Engineering FE topology block_index",
        )
        block_id = str(block.get("block_id", "")).strip()
        if block_index in seen_block_indices or not re.fullmatch(
            r"block:(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))*",
            block_id,
        ):
            raise ValueError(
                "Engineering FE topology block records require unique indices and canonical IDs."
            )
        seen_block_indices.add(block_index)
        for key in (
            "point_id_array",
            "cell_id_array",
            "element_face_id_array",
            "element_face_id_unsupported_reason",
        ):
            if not isinstance(block.get(key, ""), str):
                raise ValueError(f"Engineering FE topology {key} must be text.")
        element_face_id_array = str(block.get("element_face_id_array", "")).strip()
        element_face_reason = str(
            block.get("element_face_id_unsupported_reason", "")
        ).strip()
        if bool(element_face_id_array) == bool(element_face_reason):
            raise ValueError(
                "Engineering FE topology must declare either an authored element-face "
                "array or its unsupported reason."
            )
        for key, total_key in (
            ("point_count", "nodes"),
            ("cell_count", "elements"),
            ("exterior_element_face_count", "element_faces"),
        ):
            block_totals[total_key] += non_negative_int(
                block.get(key),
                context=f"Engineering FE topology {key}",
            )

    edge_continuity = mapping_list(
        value.get("edge_continuity"),
        context="Engineering edge continuity",
    )
    face_continuity = mapping_list(
        value.get("face_continuity"),
        context="Engineering face continuity",
    )
    for records, metric, maximum, context in (
        (edge_continuity, "tangent_deviation_degrees", 180.0, "edge"),
        (face_continuity, "angular_deviation_degrees", 90.0, "face"),
    ):
        for record in records:
            if context == "edge":
                first = str(record.get("edge_a", "")).strip()
                second = str(record.get("edge_b", "")).strip()
                shared = str(record.get("via_vertex", "")).strip()
                if (
                    first == second
                    or first not in cad_entity_ids["edges"]
                    or second not in cad_entity_ids["edges"]
                    or shared not in cad_entity_ids["vertices"]
                    or shared not in cad_edge_vertices.get(first, ())
                    or shared not in cad_edge_vertices.get(second, ())
                    or first not in cad_vertex_edges.get(shared, ())
                    or second not in cad_vertex_edges.get(shared, ())
                ):
                    raise ValueError(
                        "Engineering edge continuity does not reference a shared CAD vertex."
                    )
            else:
                first = str(record.get("face_a", "")).strip()
                second = str(record.get("face_b", "")).strip()
                shared = str(record.get("shared_edge", "")).strip()
                if (
                    first == second
                    or first not in cad_entity_ids["faces"]
                    or second not in cad_entity_ids["faces"]
                    or shared not in cad_entity_ids["edges"]
                    or first not in cad_edge_faces.get(shared, ())
                    or second not in cad_edge_faces.get(shared, ())
                    or shared not in cad_face_edges.get(first, ())
                    or shared not in cad_face_edges.get(second, ())
                ):
                    raise ValueError(
                        "Engineering face continuity does not reference a shared CAD edge."
                    )
            if not isinstance(record.get("supported"), bool):
                raise ValueError(
                    f"Engineering {context} continuity support must be boolean."
                )
            if not record["supported"]:
                if not str(record.get("reason", "")).strip():
                    raise ValueError(
                        f"Unsupported engineering {context} continuity requires a reason."
                    )
                continue
            try:
                deviation = float(record.get(metric))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Supported engineering {context} continuity requires {metric}."
                ) from exc
            if not math.isfinite(deviation) or not 0.0 <= deviation <= maximum:
                raise ValueError(
                    f"Engineering {context} continuity {metric} is outside 0..{maximum:g}."
                )

    availability_evidence = {
        "cad_vertex_selection": entity_counts["vertices"] > 0,
        "cad_edge_selection": entity_counts["edges"] > 0,
        "cad_face_selection": entity_counts["faces"] > 0,
        "cad_body_selection": entity_counts["bodies"] > 0,
        "fe_node_selection": block_totals["nodes"] > 0,
        "fe_element_selection": block_totals["elements"] > 0,
        "fe_element_face_selection": block_totals["element_faces"] > 0,
        "tangent_edge_propagation": bool(edge_continuity)
        and all(record["supported"] for record in edge_continuity),
        "tangent_face_propagation": bool(face_continuity)
        and all(record["supported"] for record in face_continuity),
    }
    for capability_id, has_evidence in availability_evidence.items():
        if capabilities[capability_id]["available"] != has_evidence:
            raise ValueError(
                f"Engineering selection capability {capability_id!r} does not match exact topology evidence."
            )

    normalized = dict(value)
    normalized["capabilities"] = capabilities
    normalized["parts"] = parts
    normalized["blocks"] = blocks
    normalized["edge_continuity"] = edge_continuity
    normalized["face_continuity"] = face_continuity
    return normalized


def normalize_engineering_selection_set(value: object) -> dict[str, Any]:
    if value is None:
        return empty_engineering_selection_set()
    if not isinstance(value, Mapping):
        raise TypeError("Engineering selection set must be a mapping.")
    if value.get("schema") != ENGINEERING_SELECTION_SCHEMA:
        raise ValueError(
            f"Engineering selection schema must be {ENGINEERING_SELECTION_SCHEMA!r}."
        )
    fingerprint = str(value.get("scene_fingerprint", "")).strip()
    if fingerprint and not re.fullmatch(r"[0-9a-fA-F]{64}", fingerprint):
        raise ValueError(
            "Engineering selection scene_fingerprint must be a SHA-256 fingerprint."
        )
    fingerprint = fingerprint.casefold()
    selections: list[dict[str, Any]] = []
    raw_selections = value.get("selections")
    if not isinstance(raw_selections, (list, tuple)):
        raise ValueError("Engineering selection selections must be a list.")
    names: set[str] = set()
    for entry in raw_selections:
        if not isinstance(entry, Mapping):
            raise ValueError("Engineering selection entries must be mappings.")
        name = str(entry.get("name", "")).strip()
        if not name:
            raise ValueError("Engineering selection name is required.")
        if name in names:
            raise ValueError(f"Engineering selection name {name!r} is duplicated.")
        entry_scene_fingerprint = (
            str(entry.get("scene_fingerprint", fingerprint)).strip().casefold()
        )
        for label, entry_fingerprint in (
            ("scene_fingerprint", entry_scene_fingerprint),
        ):
            if entry_fingerprint and not re.fullmatch(
                r"[0-9a-f]{64}", entry_fingerprint
            ):
                raise ValueError(
                    f"Engineering selection {label} must be a SHA-256 fingerprint."
                )
        if fingerprint and entry_scene_fingerprint != fingerprint:
            raise ValueError(
                "Engineering selection scene_fingerprint does not match its selection set."
            )

        raw_entities = entry.get("entities")
        if raw_entities is None:
            raise ValueError(
                "Engineering selection entries require structured entities."
            )
        if not isinstance(raw_entities, (list, tuple)):
            raise ValueError("Engineering selection entities must be a list.")
        normalized_entities: list[dict[str, str]] = []
        seen_entities: set[tuple[str, str, str, str]] = set()
        allowed_kinds = {
            "cad_vertex",
            "cad_edge",
            "cad_face",
            "cad_body",
            "fe_node",
            "fe_element_face",
            "fe_element",
        }
        for entity in raw_entities:
            if not isinstance(entity, Mapping):
                raise ValueError("Engineering selection entity refs must be mappings.")
            layer_id = str(entity.get("layer_id", "")).strip()
            source_fingerprint = (
                str(entity.get("source_fingerprint", "")).strip().casefold()
            )
            entity_kind = str(entity.get("entity_kind", "")).strip().casefold()
            entity_id = str(entity.get("entity_id", "")).strip()
            pattern = _ENGINEERING_ENTITY_ID_PATTERNS.get(entity_kind)
            if (
                not layer_id
                or entity_kind not in allowed_kinds
                or pattern is None
                or pattern.fullmatch(entity_id) is None
            ):
                raise ValueError(
                    "Engineering selection entity refs are incomplete or unsupported."
                )
            if not re.fullmatch(r"[0-9a-f]{64}", source_fingerprint):
                raise ValueError(
                    "Engineering selection entity source_fingerprint must be SHA-256."
                )
            identity = (layer_id, source_fingerprint, entity_kind, entity_id)
            if identity in seen_entities:
                continue
            seen_entities.add(identity)
            normalized_entities.append(
                {
                    "layer_id": layer_id,
                    "source_fingerprint": source_fingerprint,
                    "entity_kind": entity_kind,
                    "entity_id": entity_id,
                }
            )
        normalized_entities.sort(
            key=lambda item: (
                item["layer_id"],
                item["source_fingerprint"],
                item["entity_kind"],
                item["entity_id"],
            )
        )
        if not normalized_entities:
            raise ValueError("Engineering selection entities must not be empty.")
        names.add(name)
        selections.append(
            {
                "name": name,
                "entities": normalized_entities,
                "scene_fingerprint": entry_scene_fingerprint,
            }
        )
    published_name = str(value.get("published_name", "")).strip()
    if published_name not in {entry["name"] for entry in selections}:
        published_name = ""
    return {
        "schema": ENGINEERING_SELECTION_SCHEMA,
        "scene_fingerprint": fingerprint,
        "published_name": published_name,
        "selections": selections,
    }


__all__ = [
    "CAD_SCENE_SUFFIXES",
    "COREX_SCENE_DATA_TYPE",
    "COREX_SCENE_HANDLE_KIND",
    "COREX_SCENE_SCHEMA",
    "ENGINEERING_VIEWER_BACKEND_ID",
    "ENGINEERING_SELECTION_DATA_TYPE",
    "ENGINEERING_SELECTION_SCHEMA",
    "ENGINEERING_SELECTION_TOPOLOGY_SCHEMA",
    "FE_SCENE_SUFFIXES",
    "OCP_CAD_SCENE_SUFFIXES",
    "SCENE_IMPORTER_VERSION",
    "VIEWER_BACKGROUND_VALUES",
    "VIEWER_COLORMAP_VALUES",
    "VIEWER_RESULT_COMPONENT_VALUES",
    "VIEWER_SCALAR_RANGE_MODE_VALUES",
    "VIEWER_VIEW_OPTION_KEYS",
    "SceneDescriptor",
    "SceneSourceMetadata",
    "empty_engineering_selection_set",
    "length_unit_scale",
    "normalize_engineering_selection_set",
    "validate_engineering_selection_topology",
    "normalize_length_unit",
    "normalize_viewer_opacity",
    "normalize_viewer_background",
    "normalize_viewer_colormap",
    "normalize_viewer_deform_scale",
    "normalize_viewer_result_component",
    "normalize_viewer_scalar_range_bound",
    "normalize_viewer_scalar_range_mode",
    "normalize_scene_styles",
    "normalize_viewer_representation",
    "validate_scene_bundle",
]
