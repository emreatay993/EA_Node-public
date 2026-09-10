# Purpose: Declare and adapt the COREX ViewerViewport value.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_viewer_viewport.py

from __future__ import annotations

import math
import struct
from types import MappingProxyType

from ea_node_editor.nodes.builtins.spatial_values import (
    POINT_3D_DATA_TYPE_ID,
    VECTOR_3D_DATA_TYPE_ID,
    make_point3d_value,
    make_vector3d_value,
    point3d_coordinates,
    vector3d_coordinates,
)
from ea_node_editor.nodes.core_data_types import (
    GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.plugin_contracts import (
    PluginContractManifest,
)
from ea_node_editor.runtime_contracts import DataTypeSpec, TypedInlineValue


COREX_VIEWER_VIEWPORT_OWNER_ID = "corex.viewer_viewport"
COREX_VIEWER_VIEWPORT_OWNER_VERSION = "1"

VIEWER_VIEWPORT_DATA_TYPE_ID = "COREX.DataTypes.ViewerViewport"
CONSTRUCT_VIEW_TYPE_ID = "utilities.construct_view"
DECONSTRUCT_VIEW_TYPE_ID = "utilities.deconstruct_view"


_SINGLE_MAX = 3.4028234663852886e38
_MAPPING_PROXY_TYPE = type(MappingProxyType({}))
_VIEWPORT_KEYS = frozenset(
    {
        "camera_position",
        "camera_target",
        "camera_up_vector",
        "field_width",
        "field_height",
        "display_mode",
        "projection_mode",
        "show_mesh_edges",
        "show_attribute_colors",
        "show_viewer_triad",
        "show_view_cube",
        "show_viewer_axes",
    }
)

DEFAULT_CAMERA_POSITION = make_point3d_value(-180.0, -180.0, 180.0)
DEFAULT_CAMERA_TARGET = make_point3d_value(0.0, 0.0, 0.0)
DEFAULT_CAMERA_UP_VECTOR = make_vector3d_value(
    0.4082483,
    0.4082483,
    0.8164966,
)


def _is_spatial_payload(value: object, data_type_id: str) -> bool:
    try:
        typed = TypedInlineValue(data_type_id, 1, value)
        if data_type_id == POINT_3D_DATA_TYPE_ID:
            point3d_coordinates(typed)
        else:
            vector3d_coordinates(typed)
    except ValueError:
        return False
    return True


def _is_single(value: object) -> bool:
    return type(value) is float and math.isfinite(value) and abs(value) <= _SINGLE_MAX


def is_viewer_viewport_payload(value: object) -> bool:
    if type(value) is not dict or len(value) != len(_VIEWPORT_KEYS):
        return False
    if any(type(key) is not str or key not in _VIEWPORT_KEYS for key in value):
        return False
    if not _is_spatial_payload(value["camera_position"], POINT_3D_DATA_TYPE_ID):
        return False
    if not _is_spatial_payload(value["camera_target"], POINT_3D_DATA_TYPE_ID):
        return False
    if not _is_spatial_payload(
        value["camera_up_vector"],
        VECTOR_3D_DATA_TYPE_ID,
    ):
        return False
    if not _is_single(value["field_width"]) or not _is_single(value["field_height"]):
        return False
    if type(value["display_mode"]) is not int or not 0 <= value["display_mode"] <= 3:
        return False
    if (
        type(value["projection_mode"]) is not int
        or not 0 <= value["projection_mode"] <= 1
    ):
        return False
    return all(
        type(value[key]) is bool
        for key in (
            "show_mesh_edges",
            "show_attribute_colors",
            "show_viewer_triad",
            "show_view_cube",
            "show_viewer_axes",
        )
    )


def _require_viewport(value: object) -> dict[str, object]:
    if (
        type(value) is not TypedInlineValue
        or type(value.data_type_id) is not str
        or value.data_type_id != VIEWER_VIEWPORT_DATA_TYPE_ID
        or type(value.schema_version) is not int
        or value.schema_version != 1
        or not is_viewer_viewport_payload(value.payload)
    ):
        raise ValueError("ViewerViewport input is invalid")
    return value.payload


def _single(value: float) -> float:
    try:
        result = struct.unpack("<f", struct.pack("<f", value))[0]
    except (OverflowError, struct.error) as exc:
        raise ValueError("camera distance is outside the Single range") from exc
    if not math.isfinite(result):
        raise ValueError("camera distance is outside the Single range")
    return result


def _field_dimension(
    position: tuple[int | float, int | float, int | float],
    target: tuple[int | float, int | float, int | float],
) -> float:
    try:
        distance = math.hypot(
            *(float(left) - float(right) for left, right in zip(position, target))
        )
    except OverflowError as exc:
        raise ValueError("camera distance is outside the Single range") from exc
    if not math.isfinite(distance):
        raise ValueError("camera distance is outside the Single range")
    return _single(_single(distance) / 2.5)


def make_viewer_viewport_value(
    *,
    camera_position: object,
    camera_target: object,
    camera_up_vector: object,
    field_width: object,
    field_height: object,
    display_mode: object,
    projection_mode: object,
    show_mesh_edges: object,
    show_attribute_colors: object,
    show_viewer_triad: object,
    show_view_cube: object,
    show_viewer_axes: object,
) -> TypedInlineValue:
    position = make_point3d_value(*point3d_coordinates(camera_position)).payload
    target = make_point3d_value(*point3d_coordinates(camera_target)).payload
    up_vector = make_vector3d_value(*vector3d_coordinates(camera_up_vector)).payload
    payload = {
        "camera_position": position,
        "camera_target": target,
        "camera_up_vector": up_vector,
        "field_width": field_width,
        "field_height": field_height,
        "display_mode": display_mode,
        "projection_mode": projection_mode,
        "show_mesh_edges": show_mesh_edges,
        "show_attribute_colors": show_attribute_colors,
        "show_viewer_triad": show_viewer_triad,
        "show_view_cube": show_view_cube,
        "show_viewer_axes": show_viewer_axes,
    }
    if not is_viewer_viewport_payload(payload):
        raise ValueError("ViewerViewport payload is invalid")
    return TypedInlineValue(VIEWER_VIEWPORT_DATA_TYPE_ID, 1, payload)


def _spatial_input(value: object, data_type_id: str) -> TypedInlineValue:
    if type(value) is TypedInlineValue:
        return value
    if _is_spatial_payload(value, data_type_id):
        return TypedInlineValue(data_type_id, 1, value)
    raise ValueError("spatial viewport input is invalid")


def execute_construct_view(ctx: ExecutionContext) -> NodeResult:
    camera_position = _spatial_input(
        ctx.inputs["camera_position"],
        POINT_3D_DATA_TYPE_ID,
    )
    camera_target = _spatial_input(
        ctx.inputs["camera_target"],
        POINT_3D_DATA_TYPE_ID,
    )
    camera_up_vector = _spatial_input(
        ctx.inputs["camera_up_vector"],
        VECTOR_3D_DATA_TYPE_ID,
    )
    position = point3d_coordinates(camera_position)
    target = point3d_coordinates(camera_target)
    vector3d_coordinates(camera_up_vector)
    display_mode = ctx.inputs["display_mode"]
    projection_mode = ctx.inputs["projection_mode"]
    if type(display_mode) is not int or not 0 <= display_mode <= 3:
        raise ValueError("display mode must be an integer from 0 to 3")
    if type(projection_mode) is not int or not 0 <= projection_mode <= 1:
        raise ValueError("projection mode must be an integer from 0 to 1")
    flag_keys = (
        "show_mesh_edges",
        "show_attribute_colors",
        "show_triad",
        "show_view_cube",
        "show_axes",
    )
    if any(type(ctx.inputs[key]) is not bool for key in flag_keys):
        raise ValueError("viewer visibility inputs must be booleans")
    field_dimension = _field_dimension(position, target)
    viewport = make_viewer_viewport_value(
        camera_position=camera_position,
        camera_target=camera_target,
        camera_up_vector=camera_up_vector,
        field_width=field_dimension,
        field_height=field_dimension,
        display_mode=display_mode,
        projection_mode=projection_mode,
        show_mesh_edges=(
            True if display_mode in {2, 3} else ctx.inputs["show_mesh_edges"]
        ),
        show_attribute_colors=ctx.inputs["show_attribute_colors"],
        show_viewer_triad=ctx.inputs["show_triad"],
        show_view_cube=ctx.inputs["show_view_cube"],
        show_viewer_axes=ctx.inputs["show_axes"],
    )
    return NodeResult(outputs={"viewport": viewport})


def execute_deconstruct_view(viewport: object) -> NodeResult:
    payload = _require_viewport(viewport)
    return NodeResult(
        outputs={
            "camera_position": make_point3d_value(
                *point3d_coordinates(
                    TypedInlineValue(
                        POINT_3D_DATA_TYPE_ID,
                        1,
                        payload["camera_position"],
                    )
                )
            ),
            "camera_target": make_point3d_value(
                *point3d_coordinates(
                    TypedInlineValue(
                        POINT_3D_DATA_TYPE_ID,
                        1,
                        payload["camera_target"],
                    )
                )
            ),
            "camera_up_vector": make_vector3d_value(
                *vector3d_coordinates(
                    TypedInlineValue(
                        VECTOR_3D_DATA_TYPE_ID,
                        1,
                        payload["camera_up_vector"],
                    )
                )
            ),
            "display_mode": payload["display_mode"],
            "projection_mode": payload["projection_mode"],
            "show_mesh_edges": payload["show_mesh_edges"],
            "show_attribute_colors": payload["show_attribute_colors"],
            "show_triad": payload["show_viewer_triad"],
            "show_view_cube": payload["show_view_cube"],
            "show_axes": payload["show_viewer_axes"],
        }
    )


COREX_VIEWER_VIEWPORT_DATA_TYPES = (
    DataTypeSpec(
        VIEWER_VIEWPORT_DATA_TYPE_ID,
        "Viewer Viewport",
        "viewer",
        is_viewer_viewport_payload,
        parents=(GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)


COREX_VIEWER_VIEWPORT_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_VIEWER_VIEWPORT_DATA_TYPES,
)

__all__ = [
    "CONSTRUCT_VIEW_TYPE_ID",
    "DECONSTRUCT_VIEW_TYPE_ID",
    "DEFAULT_CAMERA_POSITION",
    "DEFAULT_CAMERA_TARGET",
    "DEFAULT_CAMERA_UP_VECTOR",
    "COREX_VIEWER_VIEWPORT_CONTRACT_MANIFEST",
    "COREX_VIEWER_VIEWPORT_DATA_TYPES",
    "COREX_VIEWER_VIEWPORT_OWNER_ID",
    "COREX_VIEWER_VIEWPORT_OWNER_VERSION",
    "VIEWER_VIEWPORT_DATA_TYPE_ID",
    "execute_construct_view",
    "execute_deconstruct_view",
    "is_viewer_viewport_payload",
    "make_viewer_viewport_value",
]
