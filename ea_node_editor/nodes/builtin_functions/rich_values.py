# Purpose: Hold inert decorated source for the Plane container.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_rich_values.py

SOURCE = r"""import corex

from ea_node_editor.nodes.builtins.rich_value_nodes import plane_container_value


IDENTITY_PLANE = {
    "data_type_id": "COREX.DataTypes.Plane",
    "schema_version": 1,
    "payload": {
        "origin": [0.0, 0.0, 0.0],
        "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        "normal": [0.0, 0.0, 1.0],
    },
}


@corex.node(
    id="reference.plane_container",
    _solution_reuse_scope="durable",
    name="Plane",
    category=("Reference", "Container"),
    icon="3d_rotation",
    description="Stores or passes through one typed Plane value.",
    keywords=("Plane", "Reference", "Container", "Coordinate System"),
)
@corex.text(
    "input",
    default="",
    label="Plane",
    description="Typed inline Plane stored by this container.",
    port=True,
    _inline_editor="",
    _persistence_type="COREX.DataTypes.Plane",
    _port_description="Optional Plane value to store or pass through.",
    _port_label="Plane",
    _port_required=False,
    _port_uses_property_default=False,
    _port_value_type="COREX.DataTypes.Plane",
    _property_default=IDENTITY_PLANE,
    _property_type="json",
)
@corex.output(
    "output",
    value_type="COREX.DataTypes.Plane",
    label="Plane",
    description="The stored or incoming Plane value.",
)
def plane_container(ctx, input, settings):
    return {"output": plane_container_value(ctx, input, settings.to_dict()["input"])}
"""

__all__ = ["SOURCE"]
