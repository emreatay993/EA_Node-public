# Purpose: Hold inert decorated source for FEM and optimization constructors.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_fem_contracts.py

SOURCE = r'''import corex

from ea_node_editor.nodes.builtins.fem_contracts import (
    execute_construct_design,
    execute_construct_parameters,
    execute_construct_responses,
    execute_force,
    execute_load_container,
)


def _outputs(ctx, result, code):
    for warning in result.warnings:
        ctx.warn(warning, code=code)
    return result.outputs


@corex.node(
    id="fea.force",
    _solution_reuse_scope="session",
    name="Force",
    category=("FEA", "Loads"),
    icon="arrow_forward",
    description="Creates a bounded Force from ordered OCP bodies, tolerances, and a Vector3D.",
    keywords=("FEA", "force", "load", "geometry", "vector"),
)
@corex.input(
    "name",
    value_type="COREX.DataTypes.String",
    required=True,
    label="Name",
    description="Name assigned to the force load.",
)
@corex.input(
    "index",
    value_type="COREX.DataTypes.Int",
    required=False,
    label="Index",
    description="Optional load index.",
)
@corex.input(
    "geometry",
    value_type="COREX.Geometry.OCPBody",
    structure="list",
    required=True,
    label="Geometry",
    description="Ordered geometry bodies receiving the force.",
)
@corex.input(
    "tolerances",
    value_type="COREX.DataTypes.Double",
    structure="list",
    required=False,
    label="Tolerances",
    description="Optional per-body selection tolerances.",
)
@corex.input(
    "vector",
    value_type="COREX.DataTypes.Vector3D",
    required=True,
    label="Vector",
    description="Force vector applied to the selected geometry.",
)
@corex.output(
    "load",
    value_type="COREX.Fem.Force",
    label="Load",
    description="Constructed force load handle.",
)
def force(ctx, name, index, geometry, tolerances, vector):
    return _outputs(ctx, execute_force(ctx), "fea_force")


@corex.node(
    id="fea.load_container",
    _solution_reuse_scope="session",
    name="Load Container",
    category=("FEA", "Loads"),
    icon="inventory_2",
    description="Validates and passes through one live ILoad handle.",
    keywords=("FEA", "load", "container", "pass through"),
)
@corex.input(
    "load",
    value_type="COREX.Fem.Loads.ILoad",
    required=True,
    label="Load",
    description="Load handle to validate and pass through.",
)
@corex.output(
    "output",
    value_type="COREX.Fem.Loads.ILoad",
    label="Output",
    description="Validated load handle.",
)
def load_container(ctx, load):
    return _outputs(ctx, execute_load_container(ctx), "fea_load_container")


@corex.node(
    id="optimization.construct_parameters",
    _solution_reuse_scope="session",
    name="Construct Parameters",
    category=("Optimization",),
    icon="tune",
    description="Constructs optimization parameter handles from parallel lists.",
    keywords=("optimization", "parameter", "variable"),
)
@corex.input(
    "names",
    value_type="COREX.DataTypes.String",
    structure="list",
    required=True,
    label="Names",
    description="Names of the optimization parameters.",
)
@corex.input(
    "minimum_values",
    value_type="COREX.DataTypes.Double",
    structure="list",
    required=True,
    label="Minimum Values",
    description="Minimum value for each parameter.",
)
@corex.input(
    "maximum_values",
    value_type="COREX.DataTypes.Double",
    structure="list",
    required=True,
    label="Maximum Values",
    description="Maximum value for each parameter.",
)
@corex.input(
    "decimal_places",
    value_type="COREX.DataTypes.Int",
    structure="list",
    required=True,
    label="Decimal Places",
    description="Decimal precision for each parameter.",
)
@corex.output(
    "parameters",
    value_type="COREX.DataTypes.Optimization.OptimizationParameter",
    structure="list",
    label="Parameters",
    description="Constructed optimization parameter handles.",
)
def construct_parameters(
    ctx,
    names,
    minimum_values,
    maximum_values,
    decimal_places,
):
    return _outputs(
        ctx,
        execute_construct_parameters(ctx),
        "optimization_construct_parameters",
    )


@corex.node(
    id="optimization.construct_responses",
    _solution_reuse_scope="session",
    name="Construct Responses",
    category=("Optimization",),
    icon="analytics",
    description="Constructs optimization response handles from parallel lists.",
    keywords=("optimization", "response", "objective", "constraint"),
)
@corex.input(
    "names",
    value_type="COREX.DataTypes.String",
    structure="list",
    required=True,
    label="Names",
    description="Names of the optimization responses.",
)
@corex.input(
    "objectives",
    value_type="COREX.DataTypes.Int",
    structure="list",
    required=True,
    label="Objectives",
    description="Objective code for each response.",
)
@corex.input(
    "minimum_constraints",
    value_type="COREX.DataTypes.Double",
    structure="list",
    required=False,
    label="Minimum Constraints",
    description="Optional list; null items are preserved as no constraint.",
)
@corex.input(
    "maximum_constraints",
    value_type="COREX.DataTypes.Double",
    structure="list",
    required=False,
    label="Maximum Constraints",
    description="Optional list; null items are preserved as no constraint.",
)
@corex.output(
    "responses",
    value_type="COREX.DataTypes.Optimization.OptimizationResponse",
    structure="list",
    label="Responses",
    description="Constructed optimization response handles.",
)
def construct_responses(
    ctx,
    names,
    objectives,
    minimum_constraints,
    maximum_constraints,
):
    return _outputs(
        ctx,
        execute_construct_responses(ctx),
        "optimization_construct_responses",
    )


@corex.node(
    id="optimization.construct_design",
    _solution_reuse_scope="session",
    name="Construct Design",
    category=("Control", "Parameter Optimization"),
    icon="design_services",
    description="Create a design for a parameter study.",
    keywords=("optimization", "design", "parameter", "response"),
)
@corex.input(
    "parameters_and_responses",
    value_type="COREX.DataTypes.Optimization.OptimizationVariable",
    structure="list",
    required=True,
    label="Parameters & Responses",
    description="Parameters and responses of the design.",
)
@corex.text(
    "name",
    default="Design",
    label="Name",
    description="The name of the design.",
    port=True,
    _inline_editor="",
    _inspector_editor="",
    _port_description="The name of the design.",
    _port_label="Name",
    _port_required=True,
    _port_structure="item",
    _port_uses_property_default=True,
    _port_value_type="COREX.DataTypes.String",
)
@corex.input(
    "parameter_values",
    value_type="COREX.DataTypes.Double",
    structure="list",
    required=False,
    label="Parameter values",
    description="Optional values of the parameters. If no values are given, the minimum values of the parameters are used.",
)
@corex.input(
    "response_values",
    value_type="COREX.DataTypes.Double",
    structure="list",
    required=False,
    label="Response values",
    description="Optional values of the responses.",
)
@corex.output(
    "design",
    value_type="COREX.DataTypes.Optimization.OptimizationDesign",
    label="Design",
    description="The created design.",
)
def construct_design(
    ctx,
    parameters_and_responses,
    parameter_values,
    response_values,
    settings,
):
    return _outputs(
        ctx,
        execute_construct_design(ctx),
        "optimization_construct_design",
    )
'''

__all__ = ["SOURCE"]
