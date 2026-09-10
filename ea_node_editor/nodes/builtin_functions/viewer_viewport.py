# Purpose: Hold inert decorated source for ViewerViewport utility built-ins.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_viewer_viewport.py

SOURCE = r"""import corex

from ea_node_editor.nodes.builtins.viewer_viewport import (
    execute_construct_view,
    execute_deconstruct_view,
)


@corex.node(
    id="utilities.construct_view",
    _solution_reuse_scope="durable",
    name="Construct View",
    category=("Utilities", "Viewer"),
    icon="visibility",
    description="Constructs a typed viewer viewport from camera settings.",
    keywords=("viewer", "view", "camera", "construct"),
)
@corex.text(
    "camera_position",
    default="",
    label="Camera Position",
    port=True,
    _inline_editor="",
    _inspector_visible=False,
    _property_type="json",
    _property_default={
        "data_type_id": "COREX.DataTypes.Point3D",
        "schema_version": 1,
        "payload": {"x": -180.0, "y": -180.0, "z": 180.0},
    },
    _persistence_type="COREX.DataTypes.Point3D",
    _port_label="Camera Position",
    _port_description="Camera position in world coordinates.",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Point3D",
)
@corex.text(
    "camera_target",
    default="",
    label="Camera Target",
    port=True,
    _inline_editor="",
    _inspector_visible=False,
    _property_type="json",
    _property_default={
        "data_type_id": "COREX.DataTypes.Point3D",
        "schema_version": 1,
        "payload": {"x": 0.0, "y": 0.0, "z": 0.0},
    },
    _persistence_type="COREX.DataTypes.Point3D",
    _port_label="Camera Target",
    _port_description="World-space point viewed by the camera.",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Point3D",
)
@corex.text(
    "camera_up_vector",
    default="",
    label="Camera Up Vector",
    port=True,
    _inline_editor="",
    _inspector_visible=False,
    _property_type="json",
    _property_default={
        "data_type_id": "COREX.DataTypes.Vector3D",
        "schema_version": 1,
        "payload": {"x": 0.4082483, "y": 0.4082483, "z": 0.8164966},
    },
    _persistence_type="COREX.DataTypes.Vector3D",
    _port_label="Camera Up Vector",
    _port_description="Vector defining the camera's upward direction.",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Vector3D",
)
@corex.number(
    "display_mode",
    default=1,
    minimum=0,
    maximum=3,
    label="Display Mode",
    port=True,
    _inline_editor="",
    _inspector_visible=False,
    _port_label="Display Mode",
    _port_description="Viewer display mode code.",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Int",
)
@corex.number(
    "projection_mode",
    default=0,
    minimum=0,
    maximum=1,
    label="Projection Mode",
    port=True,
    _inline_editor="",
    _inspector_visible=False,
    _port_label="Projection Mode",
    _port_description="Viewer projection mode code.",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Int",
)
@corex.switch(
    "show_mesh_edges",
    default=True,
    label="Show Mesh Edges",
    port=True,
    _inline_editor="",
    _inspector_visible=False,
    _port_label="Show Mesh Edges",
    _port_description="Whether mesh edges are visible.",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Bool",
)
@corex.switch(
    "show_attribute_colors",
    default=False,
    label="Show Attribute Colors",
    port=True,
    _inline_editor="",
    _inspector_visible=False,
    _port_label="Show Attribute Colors",
    _port_description="Whether attribute colors are visible.",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Bool",
)
@corex.switch(
    "show_triad",
    default=True,
    label="Show Triad",
    port=True,
    _inline_editor="",
    _inspector_visible=False,
    _port_label="Show Triad",
    _port_description="Whether the orientation triad is visible.",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Bool",
)
@corex.switch(
    "show_view_cube",
    default=True,
    label="Show View Cube",
    port=True,
    _inline_editor="",
    _inspector_visible=False,
    _port_label="Show View Cube",
    _port_description="Whether the view cube is visible.",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Bool",
)
@corex.switch(
    "show_axes",
    default=True,
    label="Show Axes",
    port=True,
    _inline_editor="",
    _inspector_visible=False,
    _port_label="Show Axes",
    _port_description="Whether coordinate axes are visible.",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Bool",
)
@corex.output(
    "viewport",
    value_type="COREX.DataTypes.ViewerViewport",
    label="Viewport",
    description="Viewport assembled from the camera and display settings.",
)
def construct_view(ctx, settings):
    del settings
    result = execute_construct_view(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="construct_view")
    return dict(result.outputs)


@corex.node(
    id="utilities.deconstruct_view",
    _solution_reuse_scope="durable",
    name="Deconstruct View",
    category=("Utilities", "Viewer"),
    icon="visibility",
    description="Extracts camera settings from a typed viewer viewport.",
    keywords=("viewer", "view", "camera", "deconstruct"),
)
@corex.input(
    "viewport",
    value_type="COREX.DataTypes.ViewerViewport",
    required=True,
    label="Viewport",
    description="Viewport whose camera and display settings will be extracted.",
)
@corex.output("camera_position", value_type="COREX.DataTypes.Point3D", label="Camera Position", description="Camera position in world coordinates.")
@corex.output("camera_target", value_type="COREX.DataTypes.Point3D", label="Camera Target", description="World-space point viewed by the camera.")
@corex.output("camera_up_vector", value_type="COREX.DataTypes.Vector3D", label="Camera Up Vector", description="Vector defining the camera's upward direction.")
@corex.output("display_mode", value_type="COREX.DataTypes.Int", label="Display Mode", description="Viewer display mode code.")
@corex.output("projection_mode", value_type="COREX.DataTypes.Int", label="Projection Mode", description="Viewer projection mode code.")
@corex.output("show_mesh_edges", value_type="COREX.DataTypes.Bool", label="Show Mesh Edges", description="Whether mesh edges are visible.")
@corex.output("show_attribute_colors", value_type="COREX.DataTypes.Bool", label="Show Attribute Colors", description="Whether attribute colors are visible.")
@corex.output("show_triad", value_type="COREX.DataTypes.Bool", label="Show Triad", description="Whether the orientation triad is visible.")
@corex.output("show_view_cube", value_type="COREX.DataTypes.Bool", label="Show View Cube", description="Whether the view cube is visible.")
@corex.output("show_axes", value_type="COREX.DataTypes.Bool", label="Show Axes", description="Whether coordinate axes are visible.")
def deconstruct_view(ctx, viewport):
    result = execute_deconstruct_view(viewport)
    for warning in result.warnings:
        ctx.warn(warning, code="deconstruct_view")
    return dict(result.outputs)
"""

__all__ = ["SOURCE"]
