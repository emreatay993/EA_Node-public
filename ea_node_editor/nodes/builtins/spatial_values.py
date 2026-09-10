# Purpose: Declare strict COREX spatial inline-value contracts and staged transforms.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_spatial_values.py, tests/test_transform3d.py
# Landmarks: make_point2d_value; make_transform3d_value; COREX_SPATIAL_VALUES_DECONSTRUCT_POINT_CANDIDATE_CONTRACT_MANIFEST; COREX_SPATIAL_VALUES_FIELD_VECTOR_CANDIDATE_CONTRACT_MANIFEST; COREX_SPATIAL_VALUES_FIELD_VECTOR_CONTAINER_CANDIDATE_CONTRACT_MANIFEST; COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_CONTRACT_MANIFEST; COREX_SPATIAL_VALUES_COORDINATE_SYSTEM_CANDIDATE_CONTRACT_MANIFEST

from __future__ import annotations

import math
from types import MappingProxyType

from ea_node_editor.nodes.core_data_types import GRAPH_DATA_TYPE_ID
from ea_node_editor.nodes.builtins.geometry_contracts import (
    COORDINATE_SYSTEM_DATA_TYPE_ID as _COORDINATE_SYSTEM_DATA_TYPE_ID,
    SPATIAL_OBJECT_DATA_TYPE_ID as _SPATIAL_OBJECT_DATA_TYPE_ID,
)
from ea_node_editor.nodes.builtins.rich_value_nodes import (
    PLANE_DATA_TYPE_ID,
    PLANE_FRAME_TOLERANCE,
    is_plane_payload,
)
from ea_node_editor.nodes.plugin_contracts import (
    PluginContractManifest,
)
from ea_node_editor.runtime_contracts import (
    DataTypeFamilySpec,
    DataTypeSpec,
    TypedInlineValue,
)

COREX_SPATIAL_VALUES_OWNER_ID = "corex.spatial_values"
COREX_SPATIAL_VALUES_OWNER_VERSION = "1"

IVECTOR_DATA_TYPE_ID = "COREX.DataTypes.IVector"
ISPATIAL_FIELD_DATA_TYPE_ID = "COREX.SpatialFields.ISpatialField"
POINT_2D_DATA_TYPE_ID = "COREX.DataTypes.Point2D"
POINT_3D_DATA_TYPE_ID = "COREX.DataTypes.Point3D"
VECTOR_2D_DATA_TYPE_ID = "COREX.DataTypes.Vector2D"
VECTOR_3D_DATA_TYPE_ID = "COREX.DataTypes.Vector3D"
TRANSFORM_3D_DATA_TYPE_ID = "COREX.DataTypes.Transform3D"
CHAINED_TRANSFORM_3D_DATA_TYPE_ID = "COREX.DataTypes.ChainedTransform3D"
CONCRETE_COORDINATE_SYSTEM_DATA_TYPE_ID = "COREX.DataTypes.CoordinateSystem"
FIELD_VECTOR_DATA_TYPE_ID = "COREX.DataTypes.FieldVector"
PLANAR_TREE_PATTERN_DATA_TYPE_ID = "COREX.SpatialPatterns.IPlanarTreePattern"

BOUNDING_INTERVAL_2D_TYPE_ID = "math.bounding_interval_2d"
REVERSE_VECTOR_TYPE_ID = "reference.reverse_vector"
DECONSTRUCT_VECTOR_TYPE_ID = "reference.deconstruct_vector"
DECONSTRUCT_POINT_TYPE_ID = "reference.deconstruct_point"
CONSTRUCT_POINT_TYPE_ID = "reference.construct_point"
CONSTRUCT_VECTOR_TYPE_ID = "reference.construct_vector"
XY_PLANE_TYPE_ID = "reference.xy_plane"
CONSTRUCT_PLANE_TYPE_ID = "reference.construct_plane"
FIELD_VECTOR_CONTAINER_TYPE_ID = "math.field_vector_container"
VECTOR_LENGTH_TYPE_ID = "reference.vector_length"
CHAIN_TRANSFORMS_TYPE_ID = "geometry.chain_transforms"
UNCHAIN_TRANSFORMS_TYPE_ID = "geometry.unchain_transforms"











_XY_KEYS = frozenset({"x", "y"})
_XYZ_KEYS = frozenset({"x", "y", "z"})
_TRANSFORM_KEYS = frozenset({"entries"})
_CHAINED_TRANSFORM_KEYS = frozenset({"entries", "transforms"})
_MAPPING_PROXY_TYPE = type(MappingProxyType({}))


def _is_finite_coordinate(value: object) -> bool:
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is not int:
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _is_coordinate_system_payload(value: object) -> bool:
    if type(value) is not dict or len(value) != 1:
        return False
    key = next(iter(value))
    if type(key) is not str or key != "entries":
        return False
    entries = value[key]
    if type(entries) is not list or len(entries) != 12:
        return False
    if not all(_is_finite_coordinate(entry) for entry in entries):
        return False

    numeric_entries = tuple(float(entry) for entry in entries)
    normalized_axes: list[tuple[float, float, float]] = []
    for offset in (3, 6, 9):
        axis = numeric_entries[offset : offset + 3]
        scale = max(abs(component) for component in axis)
        if scale == 0.0:
            return False
        scaled_axis = tuple(component / scale for component in axis)
        norm = math.hypot(*scaled_axis)
        normalized_axes.append(tuple(component / norm for component in scaled_axis))

    return all(
        abs(math.fsum(left * right for left, right in zip(first, second))) <= 1e-12
        for first, second in (
            (normalized_axes[0], normalized_axes[1]),
            (normalized_axes[0], normalized_axes[2]),
            (normalized_axes[1], normalized_axes[2]),
        )
    )


def _is_xyz_payload(value: object) -> bool:
    if type(value) is not dict or len(value) != len(_XYZ_KEYS):
        return False
    if any(type(key) is not str or key not in _XYZ_KEYS for key in value):
        return False
    return all(_is_finite_coordinate(value[key]) for key in ("x", "y", "z"))


def _is_xy_payload(value: object) -> bool:
    if type(value) is not dict or len(value) != len(_XY_KEYS):
        return False
    if any(type(key) is not str or key not in _XY_KEYS for key in value):
        return False
    return all(_is_finite_coordinate(value[key]) for key in ("x", "y"))


def _is_field_vector_payload(value: object) -> bool:
    return (
        type(value) is list
        and bool(value)
        and all(_is_finite_coordinate(item) for item in value)
    )


def make_point2d_value(x: object, y: object) -> TypedInlineValue:
    payload = {"x": x, "y": y}
    if not _is_xy_payload(payload):
        raise ValueError("Point2D coordinates are invalid")
    return TypedInlineValue(POINT_2D_DATA_TYPE_ID, 1, payload)


def point2d_coordinates(value: object) -> tuple[int | float, int | float]:
    if (
        type(value) is not TypedInlineValue
        or type(value.data_type_id) is not str
        or value.data_type_id != POINT_2D_DATA_TYPE_ID
        or type(value.schema_version) is not int
        or value.schema_version != 1
        or not _is_xy_payload(value.payload)
    ):
        raise ValueError("Point2D value is invalid")
    return (value.payload["x"], value.payload["y"])


def _make_spatial_value(
    data_type_id: str,
    x: object,
    y: object,
    z: object,
) -> TypedInlineValue:
    payload = {"x": x, "y": y, "z": z}
    if not _is_xyz_payload(payload):
        raise ValueError("spatial coordinates are invalid")
    return TypedInlineValue(data_type_id, 1, payload)


def _spatial_coordinates(
    value: object,
    data_type_id: str,
) -> tuple[int | float, int | float, int | float]:
    if (
        type(value) is not TypedInlineValue
        or type(value.data_type_id) is not str
        or value.data_type_id != data_type_id
        or type(value.schema_version) is not int
        or value.schema_version != 1
        or not _is_xyz_payload(value.payload)
    ):
        raise ValueError("spatial value is invalid")
    return (value.payload["x"], value.payload["y"], value.payload["z"])


def make_point3d_value(x: object, y: object, z: object) -> TypedInlineValue:
    return _make_spatial_value(POINT_3D_DATA_TYPE_ID, x, y, z)


def point3d_coordinates(
    value: object,
) -> tuple[int | float, int | float, int | float]:
    return _spatial_coordinates(value, POINT_3D_DATA_TYPE_ID)


def make_vector3d_value(x: object, y: object, z: object) -> TypedInlineValue:
    return _make_spatial_value(VECTOR_3D_DATA_TYPE_ID, x, y, z)


def vector3d_coordinates(
    value: object,
) -> tuple[int | float, int | float, int | float]:
    return _spatial_coordinates(value, VECTOR_3D_DATA_TYPE_ID)


def _unit_vector(value: object, *, label: str) -> tuple[float, float, float]:
    vector = vector3d_coordinates(value)
    length = math.hypot(*(float(component) for component in vector))
    if not math.isfinite(length) or length == 0.0:
        raise ValueError(f"Construct Plane {label}-axis must be nonzero")
    return tuple(float(component) / length for component in vector)  # type: ignore[return-value]


def _plane_value(
    origin: object,
    x_axis: object,
    y_axis: object,
) -> TypedInlineValue:
    origin_coordinates = point3d_coordinates(origin)
    x = _unit_vector(x_axis, label="x")
    y = _unit_vector(y_axis, label="y")
    if not math.isclose(
        math.fsum(left * right for left, right in zip(x, y, strict=True)),
        0.0,
        rel_tol=0.0,
        abs_tol=PLANE_FRAME_TOLERANCE,
    ):
        raise ValueError("Construct Plane axes must be orthogonal")
    normal = (
        x[1] * y[2] - x[2] * y[1],
        x[2] * y[0] - x[0] * y[2],
        x[0] * y[1] - x[1] * y[0],
    )
    payload = {
        "origin": [float(component) for component in origin_coordinates],
        "axes": [list(x), list(y)],
        "normal": list(normal),
    }
    if not is_plane_payload(payload):
        raise ValueError("Construct Plane produced an invalid plane")
    return TypedInlineValue(PLANE_DATA_TYPE_ID, 1, payload)


def _is_transform_payload(value: object) -> bool:
    return (
        type(value) is dict
        and len(value) == 1
        and all(type(key) is str and key in _TRANSFORM_KEYS for key in value)
        and type(value["entries"]) is list
        and len(value["entries"]) == 16
        and all(_is_finite_coordinate(entry) for entry in value["entries"])
    )


def _transform_entries_input(value: object) -> tuple[int | float, ...]:
    if (
        type(value) not in {list, tuple}
        or len(value) != 16
        or not all(_is_finite_coordinate(entry) for entry in value)
    ):
        raise ValueError("Transform3D entries are invalid")
    return tuple(value)


def make_transform3d_value(entries: object) -> TypedInlineValue:
    values = _transform_entries_input(entries)
    return TypedInlineValue(
        TRANSFORM_3D_DATA_TYPE_ID,
        1,
        {"entries": list(values)},
    )


def _multiply_4x4(
    left: tuple[int | float, ...],
    right: tuple[int | float, ...],
) -> tuple[int | float, ...]:
    try:
        entries = tuple(
            sum(left[k * 4 + row] * right[column * 4 + k] for k in range(4))
            for column in range(4)
            for row in range(4)
        )
    except OverflowError as exc:
        raise ValueError("ChainedTransform3D composite is invalid") from exc
    if not all(_is_finite_coordinate(entry) for entry in entries):
        raise ValueError("ChainedTransform3D composite is invalid")
    return entries


def _composite_entries(
    transforms: list[dict[str, object]],
) -> tuple[int | float, ...]:
    composite = tuple(transforms[0]["entries"])  # type: ignore[arg-type]
    for transform in transforms[1:]:
        composite = _multiply_4x4(
            tuple(transform["entries"]),  # type: ignore[arg-type]
            composite,
        )
    return composite


def _is_chained_transform_payload(value: object) -> bool:
    if (
        type(value) is not dict
        or len(value) != len(_CHAINED_TRANSFORM_KEYS)
        or any(
            type(key) is not str or key not in _CHAINED_TRANSFORM_KEYS for key in value
        )
        or type(value["entries"]) is not list
        or len(value["entries"]) != 16
        or not all(_is_finite_coordinate(entry) for entry in value["entries"])
        or type(value["transforms"]) is not list
        or not value["transforms"]
        or not all(
            _is_transform_payload(transform) for transform in value["transforms"]
        )
    ):
        return False
    try:
        composite = _composite_entries(value["transforms"])
    except ValueError:
        return False
    return tuple(value["entries"]) == composite


def make_chained_transform3d_value(transforms: object) -> TypedInlineValue:
    if type(transforms) not in {list, tuple} or not transforms:
        raise ValueError("ChainedTransform3D transforms are invalid")
    payloads = []
    for transform in transforms:
        try:
            entries = transform3d_entries(transform)
        except ValueError:
            raise ValueError("ChainedTransform3D transforms are invalid")
        payloads.append({"entries": list(entries)})
    composite = _composite_entries(payloads)
    return TypedInlineValue(
        CHAINED_TRANSFORM_3D_DATA_TYPE_ID,
        1,
        {"entries": list(composite), "transforms": payloads},
    )


def transform3d_entries(value: object) -> tuple[int | float, ...]:
    if (
        type(value) is not TypedInlineValue
        or type(value.data_type_id) is not str
        or value.data_type_id
        not in {TRANSFORM_3D_DATA_TYPE_ID, CHAINED_TRANSFORM_3D_DATA_TYPE_ID}
        or type(value.schema_version) is not int
        or value.schema_version != 1
        or not (
            _is_transform_payload(value.payload)
            if value.data_type_id == TRANSFORM_3D_DATA_TYPE_ID
            else _is_chained_transform_payload(value.payload)
        )
    ):
        raise ValueError("Transform3D value is invalid")
    return tuple(value.payload["entries"])


def chained_transform3d_transforms(
    value: object,
) -> tuple[TypedInlineValue, ...]:
    if (
        type(value) is not TypedInlineValue
        or type(value.data_type_id) is not str
        or value.data_type_id != CHAINED_TRANSFORM_3D_DATA_TYPE_ID
        or type(value.schema_version) is not int
        or value.schema_version != 1
        or not _is_chained_transform_payload(value.payload)
    ):
        raise ValueError("ChainedTransform3D value is invalid")
    return tuple(
        TypedInlineValue(TRANSFORM_3D_DATA_TYPE_ID, 1, transform)
        for transform in value.payload["transforms"]
    )


def _transform_order(value: object) -> int:
    if type(value) is not int or value not in {0, 1}:
        raise ValueError("Transform3D order must be 0 or 1")
    return value


def _transpose_4x4(entries: tuple[int | float, ...]) -> tuple[int | float, ...]:
    return tuple(entries[row * 4 + column] for column in range(4) for row in range(4))


def _ordered_entries(
    entries: tuple[int | float, ...],
    order: int,
) -> tuple[int | float, ...]:
    return entries if _transform_order(order) == 0 else _transpose_4x4(entries)


_GRAPH_PARENT = (GRAPH_DATA_TYPE_ID,)

COREX_SPATIAL_VALUE_DATA_TYPES = (
    DataTypeSpec(
        IVECTOR_DATA_TYPE_ID,
        "Vector",
        "engineering",
        lambda _value: False,
        parents=_GRAPH_PARENT,
        abstract=True,
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        POINT_3D_DATA_TYPE_ID,
        "Point 3D",
        "engineering",
        _is_xyz_payload,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"inline"}),
        persistence="inline",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        VECTOR_3D_DATA_TYPE_ID,
        "Vector 3D",
        "engineering",
        _is_xyz_payload,
        parents=(IVECTOR_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_SPATIAL_VALUES_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_SPATIAL_VALUE_DATA_TYPES,
)


TRANSFORM_3D_DATA_TYPE_FAMILY = DataTypeFamilySpec(
    "geometry_value",
    "Geometry Value",
    "data.geometry",
    "model",
)

TRANSFORM_3D_DATA_TYPE = DataTypeSpec(
    TRANSFORM_3D_DATA_TYPE_ID,
    "Transform 3D",
    TRANSFORM_3D_DATA_TYPE_FAMILY.family_id,
    _is_transform_payload,
    parents=_GRAPH_PARENT,
    carriers=frozenset({"inline"}),
    persistence="inline",
    sensitivity="normal",
    payload_schema_version=1,
    implementation_version="1",
)

CHAINED_TRANSFORM_3D_DATA_TYPE = DataTypeSpec(
    CHAINED_TRANSFORM_3D_DATA_TYPE_ID,
    "Chained Transform 3D",
    TRANSFORM_3D_DATA_TYPE_FAMILY.family_id,
    _is_chained_transform_payload,
    parents=(TRANSFORM_3D_DATA_TYPE_ID,),
    carriers=frozenset({"inline"}),
    persistence="inline",
    sensitivity="normal",
    payload_schema_version=1,
    implementation_version="1",
)

ISPATIAL_FIELD_DATA_TYPE = DataTypeSpec(
    ISPATIAL_FIELD_DATA_TYPE_ID,
    "Spatial Field",
    "engineering",
    lambda _value: False,
    parents=_GRAPH_PARENT,
    abstract=True,
    carriers=frozenset({"handle"}),
    persistence="never",
    sensitivity="normal",
    payload_schema_version=1,
    implementation_version="1",
)

POINT_2D_DATA_TYPE = DataTypeSpec(
    POINT_2D_DATA_TYPE_ID,
    "Point 2D",
    TRANSFORM_3D_DATA_TYPE_FAMILY.family_id,
    _is_xy_payload,
    parents=_GRAPH_PARENT,
    carriers=frozenset({"inline"}),
    persistence="inline",
    sensitivity="normal",
    payload_schema_version=1,
    implementation_version="1",
)


COREX_SPATIAL_VALUES_STAGE_3_CANDIDATE_DATA_TYPES = (
    *COREX_SPATIAL_VALUE_DATA_TYPES,
    TRANSFORM_3D_DATA_TYPE,
)

COREX_SPATIAL_VALUES_STAGE_3_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_type_families=(TRANSFORM_3D_DATA_TYPE_FAMILY,),
    data_types=COREX_SPATIAL_VALUES_STAGE_3_CANDIDATE_DATA_TYPES,
)

COREX_SPATIAL_VALUES_CHAINED_TRANSFORM_CANDIDATE_DATA_TYPES = (
    *COREX_SPATIAL_VALUES_STAGE_3_CANDIDATE_DATA_TYPES,
    CHAINED_TRANSFORM_3D_DATA_TYPE,
)

COREX_SPATIAL_VALUES_CHAINED_TRANSFORM_CANDIDATE_CONTRACT_MANIFEST = (
    PluginContractManifest(
        data_type_families=(TRANSFORM_3D_DATA_TYPE_FAMILY,),
        data_types=COREX_SPATIAL_VALUES_CHAINED_TRANSFORM_CANDIDATE_DATA_TYPES,
    )
)

COREX_SPATIAL_VALUES_BOUNDING_INTERVAL_2D_CANDIDATE_DATA_TYPES = (
    *COREX_SPATIAL_VALUES_CHAINED_TRANSFORM_CANDIDATE_DATA_TYPES,
    ISPATIAL_FIELD_DATA_TYPE,
    POINT_2D_DATA_TYPE,
)

COREX_SPATIAL_VALUES_BOUNDING_INTERVAL_2D_CANDIDATE_CONTRACT_MANIFEST = (
    PluginContractManifest(
        data_type_families=(TRANSFORM_3D_DATA_TYPE_FAMILY,),
        data_types=COREX_SPATIAL_VALUES_BOUNDING_INTERVAL_2D_CANDIDATE_DATA_TYPES,
    )
)

COREX_SPATIAL_VALUES_VECTOR_2D_CANDIDATE_DATA_TYPES = (
    *COREX_SPATIAL_VALUES_BOUNDING_INTERVAL_2D_CANDIDATE_DATA_TYPES,
    DataTypeSpec(
        VECTOR_2D_DATA_TYPE_ID,
        "Vector 2D",
        "engineering",
        _is_xy_payload,
        parents=(_SPATIAL_OBJECT_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_SPATIAL_VALUES_VECTOR_2D_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_type_families=(TRANSFORM_3D_DATA_TYPE_FAMILY,),
    data_types=COREX_SPATIAL_VALUES_VECTOR_2D_CANDIDATE_DATA_TYPES,
)

COREX_SPATIAL_VALUES_REVERSE_VECTOR_CANDIDATE_CONTRACT_MANIFEST = (
    PluginContractManifest(
        data_type_families=(TRANSFORM_3D_DATA_TYPE_FAMILY,),
        data_types=COREX_SPATIAL_VALUES_VECTOR_2D_CANDIDATE_DATA_TYPES,
    )
)

COREX_SPATIAL_VALUES_DECONSTRUCT_VECTOR_CANDIDATE_CONTRACT_MANIFEST = (
    PluginContractManifest(
        data_type_families=(TRANSFORM_3D_DATA_TYPE_FAMILY,),
        data_types=COREX_SPATIAL_VALUES_VECTOR_2D_CANDIDATE_DATA_TYPES,
    )
)

COREX_SPATIAL_VALUES_DECONSTRUCT_POINT_CANDIDATE_CONTRACT_MANIFEST = (
    PluginContractManifest(
        data_type_families=(TRANSFORM_3D_DATA_TYPE_FAMILY,),
        data_types=COREX_SPATIAL_VALUES_VECTOR_2D_CANDIDATE_DATA_TYPES,
    )
)

COREX_SPATIAL_VALUES_FIELD_VECTOR_CANDIDATE_DATA_TYPES = (
    *COREX_SPATIAL_VALUES_VECTOR_2D_CANDIDATE_DATA_TYPES,
    DataTypeSpec(
        FIELD_VECTOR_DATA_TYPE_ID,
        "Field Vector",
        TRANSFORM_3D_DATA_TYPE_FAMILY.family_id,
        _is_field_vector_payload,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_SPATIAL_VALUES_FIELD_VECTOR_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_type_families=(TRANSFORM_3D_DATA_TYPE_FAMILY,),
    data_types=COREX_SPATIAL_VALUES_FIELD_VECTOR_CANDIDATE_DATA_TYPES,
)

COREX_SPATIAL_VALUES_FIELD_VECTOR_CONTAINER_CANDIDATE_CONTRACT_MANIFEST = (
    PluginContractManifest(
        data_type_families=(TRANSFORM_3D_DATA_TYPE_FAMILY,),
        data_types=COREX_SPATIAL_VALUES_FIELD_VECTOR_CANDIDATE_DATA_TYPES,
    )
)

COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_DATA_TYPES = (
    *COREX_SPATIAL_VALUES_FIELD_VECTOR_CANDIDATE_DATA_TYPES,
    DataTypeSpec(
        PLANAR_TREE_PATTERN_DATA_TYPE_ID,
        "Planar Tree Pattern",
        "engineering",
        lambda _value: False,
        parents=_GRAPH_PARENT,
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_CONTRACT_MANIFEST = (
    PluginContractManifest(
        data_type_families=(TRANSFORM_3D_DATA_TYPE_FAMILY,),
        data_types=COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_DATA_TYPES,
    )
)

COREX_SPATIAL_VALUES_VECTOR_LENGTH_CANDIDATE_CONTRACT_MANIFEST = (
    PluginContractManifest(
        data_type_families=(TRANSFORM_3D_DATA_TYPE_FAMILY,),
        data_types=COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_DATA_TYPES,
    )
)

COREX_SPATIAL_VALUES_COORDINATE_SYSTEM_CANDIDATE_DATA_TYPES = (
    *COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_DATA_TYPES,
    DataTypeSpec(
        CONCRETE_COORDINATE_SYSTEM_DATA_TYPE_ID,
        "Coordinate System",
        TRANSFORM_3D_DATA_TYPE_FAMILY.family_id,
        _is_coordinate_system_payload,
        parents=(_COORDINATE_SYSTEM_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_SPATIAL_VALUES_COORDINATE_SYSTEM_CANDIDATE_CONTRACT_MANIFEST = (
    PluginContractManifest(
        data_type_families=(TRANSFORM_3D_DATA_TYPE_FAMILY,),
        data_types=COREX_SPATIAL_VALUES_COORDINATE_SYSTEM_CANDIDATE_DATA_TYPES,
    )
)

__all__ = [
    "BOUNDING_INTERVAL_2D_TYPE_ID",
    "CHAINED_TRANSFORM_3D_DATA_TYPE",
    "CHAINED_TRANSFORM_3D_DATA_TYPE_ID",
    "CHAIN_TRANSFORMS_TYPE_ID",
    "CONCRETE_COORDINATE_SYSTEM_DATA_TYPE_ID",
    "DECONSTRUCT_POINT_TYPE_ID",
    "DECONSTRUCT_VECTOR_TYPE_ID",
    "FIELD_VECTOR_CONTAINER_TYPE_ID",
    "FIELD_VECTOR_DATA_TYPE_ID",
    "IVECTOR_DATA_TYPE_ID",
    "ISPATIAL_FIELD_DATA_TYPE",
    "ISPATIAL_FIELD_DATA_TYPE_ID",
    "POINT_2D_DATA_TYPE",
    "POINT_2D_DATA_TYPE_ID",
    "POINT_3D_DATA_TYPE_ID",
    "PLANAR_TREE_PATTERN_DATA_TYPE_ID",
    "REVERSE_VECTOR_TYPE_ID",
    "COREX_SPATIAL_VALUE_DATA_TYPES",
    "COREX_SPATIAL_VALUES_CONTRACT_MANIFEST",
    "COREX_SPATIAL_VALUES_COORDINATE_SYSTEM_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_SPATIAL_VALUES_COORDINATE_SYSTEM_CANDIDATE_DATA_TYPES",
    "COREX_SPATIAL_VALUES_OWNER_ID",
    "COREX_SPATIAL_VALUES_OWNER_VERSION",
    "COREX_SPATIAL_VALUES_CHAINED_TRANSFORM_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_SPATIAL_VALUES_CHAINED_TRANSFORM_CANDIDATE_DATA_TYPES",
    "COREX_SPATIAL_VALUES_DECONSTRUCT_POINT_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_SPATIAL_VALUES_DECONSTRUCT_VECTOR_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_SPATIAL_VALUES_FIELD_VECTOR_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_SPATIAL_VALUES_FIELD_VECTOR_CANDIDATE_DATA_TYPES",
    "COREX_SPATIAL_VALUES_FIELD_VECTOR_CONTAINER_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_DATA_TYPES",
    "COREX_SPATIAL_VALUES_BOUNDING_INTERVAL_2D_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_SPATIAL_VALUES_BOUNDING_INTERVAL_2D_CANDIDATE_DATA_TYPES",
    "COREX_SPATIAL_VALUES_STAGE_3_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_SPATIAL_VALUES_STAGE_3_CANDIDATE_DATA_TYPES",
    "COREX_SPATIAL_VALUES_REVERSE_VECTOR_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_SPATIAL_VALUES_VECTOR_2D_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_SPATIAL_VALUES_VECTOR_2D_CANDIDATE_DATA_TYPES",
    "TRANSFORM_3D_DATA_TYPE",
    "TRANSFORM_3D_DATA_TYPE_FAMILY",
    "TRANSFORM_3D_DATA_TYPE_ID",
    "UNCHAIN_TRANSFORMS_TYPE_ID",
    "VECTOR_2D_DATA_TYPE_ID",
    "VECTOR_3D_DATA_TYPE_ID",
    "VECTOR_LENGTH_TYPE_ID",
    "COREX_SPATIAL_VALUES_VECTOR_LENGTH_CANDIDATE_CONTRACT_MANIFEST",
    "chained_transform3d_transforms",
    "make_chained_transform3d_value",
    "make_point2d_value",
    "make_point3d_value",
    "make_transform3d_value",
    "make_vector3d_value",
    "point3d_coordinates",
    "point2d_coordinates",
    "transform3d_entries",
    "vector3d_coordinates",
]
