# Purpose: Hold inert decorated source for ordinary spatial built-ins.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_spatial_values.py

SOURCE = r'''import corex
import math

from ea_node_editor.nodes.builtins.core_media import is_interval_2d_payload
from ea_node_editor.nodes.builtins.spatial_values import (
    _ordered_entries,
    _transform_entries_input,
    _transform_order,
    _is_field_vector_payload,
    _plane_value,
    chained_transform3d_transforms,
    make_chained_transform3d_value,
    make_point3d_value,
    make_transform3d_value,
    make_vector3d_value,
    point2d_coordinates,
    point3d_coordinates,
    transform3d_entries,
    vector3d_coordinates,
)
from ea_node_editor.runtime_contracts import TypedInlineValue


@corex.node(
    id="math.bounding_interval_2d",
    _solution_reuse_scope="durable",
    name="Bounding Interval 2D",
    category=("Math", "Interval"),
    icon="aspect_ratio",
    description="Create a numeric two-dimensional interval which encompasses a list of coordinates.",
    keywords=("interval", "2d", "bounding", "coordinates"),
)
@corex.input(
    "coordinates",
    value_type="COREX.DataTypes.Point2D",
    structure="list",
    required=True,
    label="Coordinates",
    description="2D-coordinates to include in the interval.",
)
@corex.output(
    "interval",
    value_type="COREX.DataTypes.Interval2D",
    label="Interval 2D",
    description="2D-Interval containing all given coordinates.",
)
def bounding_interval_2d(ctx, coordinates):
    coordinates = ctx.inputs["coordinates"]
    if type(coordinates) is not list or not coordinates:
        raise ValueError("Bounding Interval 2D requires a nonempty Point2D list")
    points = tuple(point2d_coordinates(value) for value in coordinates)
    x_values, y_values = zip(*points, strict=True)
    payload = {
        "u": {"start": float(min(x_values)), "end": float(max(x_values))},
        "v": {"start": float(min(y_values)), "end": float(max(y_values))},
    }
    if not is_interval_2d_payload(payload):
        raise ValueError("Bounding Interval 2D result is invalid")
    return {"interval": TypedInlineValue("COREX.DataTypes.Interval2D", 1, payload)}


@corex.node(
    id="math.field_vector_container",
    _solution_reuse_scope="session",
    name="Field Vector",
    category=("Math", "Container"),
    icon="storage",
    description="Storage space for {0} data. You can use this container to organize your data flow and to store data permanently by internalizing them (Right-click and Internalize). You can also use this container for filtering: All input data that cannot be converted to {0} will be set to null.",
    keywords=("field", "vector", "container"),
)
@corex.input(
    "input",
    value_type="COREX.DataTypes.FieldVector",
    required=False,
    label="Input",
    description="The input of the container.",
)
@corex.output(
    "output",
    value_type="COREX.DataTypes.FieldVector",
    label="Output",
    description="The output of the container.",
)
def field_vector_container(ctx, input):
    if "input" not in ctx.inputs:
        return {}
    if input is None:
        return {"output": None}
    if (
        type(input) is not TypedInlineValue
        or type(input.data_type_id) is not str
        or input.data_type_id != "COREX.DataTypes.FieldVector"
        or type(input.schema_version) is not int
        or input.schema_version != 1
        or not _is_field_vector_payload(input.payload)
    ):
        raise ValueError("Field Vector input is invalid")
    return {"output": input}


@corex.node(
    id="reference.reverse_vector",
    _solution_reuse_scope="durable",
    name="Reverse Vector",
    category=("Reference", "Vector"),
    icon="swap_horiz",
    description="Reverse a vector (multiply by -1).",
    keywords=("Flip",),
)
@corex.input(
    "vector",
    value_type="COREX.DataTypes.Vector3D",
    required=True,
    label="Vector",
    description="Vector to reverse.",
)
@corex.output(
    "reversed_vector",
    value_type="COREX.DataTypes.Vector3D",
    label="Vector",
    description="Reversed vector.",
)
def reverse_vector(ctx, vector):
    vector = ctx.inputs["vector"]
    x, y, z = vector3d_coordinates(vector)
    return {"reversed_vector": make_vector3d_value(-x, -y, -z)}


@corex.node(
    id="reference.deconstruct_vector",
    _solution_reuse_scope="durable",
    name="Deconstruct Vector",
    category=("Reference", "Vector"),
    icon="view_in_ar",
    description="Deconstruct a vector into its component parts.",
    keywords=("vector", "deconstruct", "coordinates"),
)
@corex.input(
    "vector",
    value_type="COREX.DataTypes.Vector3D",
    required=True,
    label="Vector",
    description="Vector to deconstruct into its coordinates.",
)
@corex.output(
    "x",
    value_type="COREX.DataTypes.Double",
    label="X-coordinate",
    description="X-coordinate of the vector.",
)
@corex.output(
    "y",
    value_type="COREX.DataTypes.Double",
    label="Y-coordinate",
    description="Y-coordinate of the vector.",
)
@corex.output(
    "z",
    value_type="COREX.DataTypes.Double",
    label="Z-coordinate",
    description="Z-coordinate of the vector.",
)
def deconstruct_vector(ctx, vector):
    vector = ctx.inputs["vector"]
    x, y, z = vector3d_coordinates(vector)
    return {"x": x, "y": y, "z": z}


@corex.node(
    id="reference.deconstruct_point",
    _solution_reuse_scope="durable",
    name="Deconstruct Point",
    category=("Reference", "Point"),
    icon="view_in_ar",
    description="Deconstruct a point into its x-, y- and z-coordinate.",
    keywords=("point", "deconstruct", "coordinates"),
)
@corex.input(
    "point",
    value_type="COREX.DataTypes.Point3D",
    required=True,
    label="Point",
    description="Point to deconstruct into its coordinates.",
)
@corex.output(
    "x",
    value_type="COREX.DataTypes.Double",
    label="X-coordinate",
    description="X-coordinate of the point.",
)
@corex.output(
    "y",
    value_type="COREX.DataTypes.Double",
    label="Y-coordinate",
    description="Y-coordinate of the point.",
)
@corex.output(
    "z",
    value_type="COREX.DataTypes.Double",
    label="Z-coordinate",
    description="Z-coordinate of the point.",
)
def deconstruct_point(ctx, point):
    point = ctx.inputs["point"]
    x, y, z = point3d_coordinates(point)
    return {"x": x, "y": y, "z": z}


@corex.node(
    id="reference.construct_point",
    _solution_reuse_scope="durable",
    name="Construct Point",
    category=("Reference", "Point"),
    icon="location_on",
    description="Create a point from global x-, y- and z-coordinates.",
    keywords=("point", "construct", "coordinates"),
)
@corex.input("x", value_type="COREX.DataTypes.Double", required=True, label="X-coordinate", description="Global x-coordinate of the point.")
@corex.input("y", value_type="COREX.DataTypes.Double", required=True, label="Y-coordinate", description="Global y-coordinate of the point.")
@corex.input("z", value_type="COREX.DataTypes.Double", required=True, label="Z-coordinate", description="Global z-coordinate of the point.")
@corex.output("point", value_type="COREX.DataTypes.Point3D", label="Point", description="Point at the supplied global coordinates.")
def construct_point(ctx, x, y, z):
    return {
        "point": make_point3d_value(
            ctx.inputs["x"], ctx.inputs["y"], ctx.inputs["z"]
        )
    }


@corex.node(
    id="reference.construct_vector",
    _solution_reuse_scope="durable",
    name="Construct Vector",
    category=("Reference", "Vector"),
    icon="arrow_forward",
    description="Create a vector from x-, y- and z-coordinates.",
    keywords=("vector", "construct", "coordinates"),
)
@corex.input("x", value_type="COREX.DataTypes.Double", required=True, label="X-coordinate", description="x-component of the vector.")
@corex.input("y", value_type="COREX.DataTypes.Double", required=True, label="Y-coordinate", description="y-component of the vector.")
@corex.input("z", value_type="COREX.DataTypes.Double", required=True, label="Z-coordinate", description="z-component of the vector.")
@corex.output("vector", value_type="COREX.DataTypes.Vector3D", label="Vector", description="Vector with the supplied components.")
def construct_vector(ctx, x, y, z):
    return {
        "vector": make_vector3d_value(
            ctx.inputs["x"], ctx.inputs["y"], ctx.inputs["z"]
        )
    }


@corex.node(
    id="reference.xy_plane",
    _solution_reuse_scope="durable",
    name="XY Plane",
    category=("Reference", "Plane"),
    icon="grid_4x4",
    description="Create an XY plane from an origin point.",
    keywords=("plane", "xy", "construct", "reference"),
)
@corex.input("origin", value_type="COREX.DataTypes.Point3D", required=True, label="Origin", description="Origin point of the XY plane.")
@corex.output("plane", value_type="COREX.DataTypes.Plane", label="Plane", description="XY plane at the supplied origin.")
def xy_plane(ctx, origin):
    return {
        "plane": _plane_value(
            ctx.inputs["origin"],
            make_vector3d_value(1.0, 0.0, 0.0),
            make_vector3d_value(0.0, 1.0, 0.0),
        )
    }


@corex.node(
    id="reference.construct_plane",
    _solution_reuse_scope="durable",
    name="Construct Plane",
    category=("Reference", "Plane"),
    icon="3d_rotation",
    description="Create a plane from an origin point and orthogonal x- and y-axes.",
    keywords=("plane", "construct", "reference", "axes"),
)
@corex.input("origin", value_type="COREX.DataTypes.Point3D", required=True, label="Origin", description="Origin point of the plane.")
@corex.input("x_axis", value_type="COREX.DataTypes.Vector3D", required=True, label="X-axis", description="Vector defining the plane x-axis.")
@corex.input("y_axis", value_type="COREX.DataTypes.Vector3D", required=True, label="Y-axis", description="Vector defining the plane y-axis.")
@corex.output("plane", value_type="COREX.DataTypes.Plane", label="Plane", description="Plane defined by the origin and axes.")
def construct_plane(ctx, origin, x_axis, y_axis):
    return {
        "plane": _plane_value(
            ctx.inputs["origin"],
            ctx.inputs["x_axis"],
            ctx.inputs["y_axis"],
        )
    }


@corex.node(
    id="geometry.construct_transform",
    _solution_reuse_scope="durable",
    name="Construct Transform",
    category=("Geometry", "Transform"),
    icon="matrix",
    description="Construct a 4x4 transformation matrix from 16 entries.",
    keywords=("transform", "matrix", "construct"),
)
@corex.input(
    "entries",
    value_type="COREX.DataTypes.Double",
    structure="list",
    required=True,
    label="Entries",
    description="Sixteen matrix entries in the selected order.",
)
@corex.number(
    "order",
    default=0,
    label="Order",
    minimum=0,
    maximum=1,
    step=1,
    port=True,
    _port_value_type="COREX.DataTypes.Int",
    _port_required=True,
    _port_description="Matrix entry order: row-major or column-major.",
)
@corex.output(
    "transform",
    value_type="COREX.DataTypes.Transform3D",
    label="Transform",
    description="Transform built from the supplied matrix entries.",
)
def construct_transform(ctx, entries, settings):
    del ctx
    return {
        "transform": make_transform3d_value(
            _ordered_entries(_transform_entries_input(entries), _transform_order(settings.order))
        )
    }


@corex.node(
    id="geometry.deconstruct_transform",
    _solution_reuse_scope="durable",
    name="Deconstruct Transform",
    category=("Geometry", "Transform"),
    icon="matrix",
    description="Deconstruct a 4x4 transformation matrix into its 16 entries.",
    keywords=("transform", "matrix", "deconstruct"),
)
@corex.input(
    "transform",
    value_type="COREX.DataTypes.Transform3D",
    required=True,
    label="Transform",
    description="Transform whose matrix entries will be extracted.",
)
@corex.number(
    "order",
    default=0,
    label="Order",
    minimum=0,
    maximum=1,
    step=1,
    port=True,
    _port_value_type="COREX.DataTypes.Int",
    _port_required=True,
    _port_description="Matrix entry order: row-major or column-major.",
)
@corex.output(
    "entries",
    value_type="COREX.DataTypes.Double",
    structure="list",
    label="Entries",
    description="Sixteen matrix entries in the selected order.",
)
def deconstruct_transform(ctx, transform, settings):
    del ctx
    return {
        "entries": list(
            _ordered_entries(transform3d_entries(transform), _transform_order(settings.order))
        )
    }


@corex.node(
    id="reference.vector_length",
    _solution_reuse_scope="durable",
    name="Vector Length",
    category=("Reference", "Vector"),
    icon="straighten",
    description="Compute length (amplitude) of a vector.",
    keywords=("vector", "length", "magnitude", "amplitude"),
)
@corex.input(
    "vector",
    value_type="COREX.DataTypes.Vector3D",
    required=True,
    label="Vector",
    description="Vector whose length shall be calculated.",
)
@corex.output(
    "length",
    value_type="COREX.DataTypes.Double",
    label="Length",
    description="Length of the vector.",
)
def vector_length(ctx, vector):
    vector = ctx.inputs["vector"]
    length = math.hypot(*vector3d_coordinates(vector))
    if not math.isfinite(length):
        raise ValueError("Vector Length result is invalid")
    return {"length": 0.0 if length == 0.0 else length}


@corex.node(
    id="geometry.chain_transforms",
    _solution_reuse_scope="durable",
    name="Chain Transforms",
    category=("Geometry", "Transform"),
    icon="matrix",
    description="Combine ordered transforms into one chained transform.",
    keywords=("transform", "matrix", "chain"),
)
@corex.input(
    "transforms",
    value_type="COREX.DataTypes.Transform3D",
    structure="list",
    required=True,
    label="Transforms",
    description="Ordered transforms to combine.",
)
@corex.output(
    "transform",
    value_type="COREX.DataTypes.ChainedTransform3D",
    label="Transform",
    description="Chained transform preserving the supplied order.",
)
def chain_transforms(ctx, transforms):
    return {"transform": make_chained_transform3d_value(ctx.inputs["transforms"])}


@corex.node(
    id="geometry.unchain_transforms",
    _solution_reuse_scope="durable",
    name="Unchain Transforms",
    category=("Geometry", "Transform"),
    icon="matrix",
    description="Restore the ordered transforms from a chained transform.",
    keywords=("transform", "matrix", "unchain"),
)
@corex.input(
    "transform",
    value_type="COREX.DataTypes.ChainedTransform3D",
    required=True,
    label="Transform",
    description="Chained transform to separate.",
)
@corex.output(
    "transforms",
    value_type="COREX.DataTypes.Transform3D",
    structure="list",
    label="Transforms",
    description="Ordered transforms stored in the chain.",
)
def unchain_transforms(ctx, transform):
    return {
        "transforms": list(chained_transform3d_transforms(ctx.inputs["transform"]))
    }
'''

__all__ = ["SOURCE"]
