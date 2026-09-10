# Purpose: Hold inert decorated source for the MARS add-on function nodes.
# Map: feature_routes/mars_solver_addon.md
# Tests: tests/test_mars_nodes.py

SOURCE = r'''import corex

from ea_node_editor.addons.mars.nodes import (
    execute_mars_batch_solve,
    execute_mars_run_job,
    execute_mars_time_history,
)


MARS_INPUT_FILTER = (
    "MARS and Ansys inputs (*.mcf *.pch *.csv *.txt *.rst);;"
    "CSV files (*.csv);;Ansys result files (*.rst);;All files (*)"
)
MARS_JOB_FILTER = "MARS jobs (*.json);;JSON files (*.json);;All files (*)"
TIME_HISTORY_OUTPUTS = (
    "von_mises",
    "max_principal",
    "min_principal",
    "deformation",
    "velocity",
    "acceleration",
    "force_moment",
)


@corex.node(
    id="mars.batch_solve",
    name="MARS Batch Solve",
    category=("MARS",),
    icon="icons/mars_icon_64.png",
    description="Builds and runs a MARS all-node envelope job with managed results.",
    keywords=("mars", "batch", "envelope"),
    _readiness_requirements=(
        {
            "any_of_properties": ("fatigue_A",),
            "when_properties": (
                {"property_key": "output_damage", "values": (True,)},
            ),
        },
        {
            "any_of_properties": ("fatigue_m",),
            "when_properties": (
                {"property_key": "output_damage", "values": (True,)},
            ),
        },
    ),
)
@corex.path(
    "modal_coordinates",
    default="",
    label="Modal Coordinates",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="path",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Path to modal coordinates used to reconstruct physical responses.",
    _port_label="Modal Coordinates",
    _port_required=True,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "modal_stress",
    default="",
    label="Modal Stress",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Path to modal stress coefficients for response recovery.",
    _port_label="Modal Stress",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "modal_deformation",
    default="",
    label="Modal Deformation",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Path to modal deformation coefficients for response recovery.",
    _port_label="Modal Deformation",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "modal_force_moment",
    default="",
    label="Modal Force / Moment",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Path to modal force and moment coefficients for response recovery.",
    _port_label="Modal Force / Moment",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "steady_state_stress",
    default="",
    label="Steady-State Stress",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Optional path to steady-state stress values added to the modal response.",
    _port_label="Steady-State Stress",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "temperature_field",
    default="",
    label="Temperature Field",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Optional path to the temperature field used for material evaluation.",
    _port_label="Temperature Field",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "material_profile",
    default="",
    label="Material Profile",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Optional path to temperature-dependent material properties.",
    _port_label="Material Profile",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "modal_rst",
    default="",
    label="Modal RST",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Optional Ansys modal result file used as a guided MARS input.",
    _port_label="Modal RST",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.output(
    "von_mises",
    value_type="COREX.DataTypes.Path",
    label="Von Mises",
    description="Managed path to the recovered von Mises stress result.",
)
@corex.output(
    "max_principal",
    value_type="COREX.DataTypes.Path",
    label="Max Principal",
    description="Managed path to the recovered maximum principal stress result.",
)
@corex.output(
    "min_principal",
    value_type="COREX.DataTypes.Path",
    label="Min Principal",
    description="Managed path to the recovered minimum principal stress result.",
)
@corex.output(
    "deformation",
    value_type="COREX.DataTypes.Path",
    label="Deformation",
    description="Managed path to the recovered deformation result.",
)
@corex.output(
    "velocity",
    value_type="COREX.DataTypes.Path",
    label="Velocity",
    description="Managed path to the recovered velocity result.",
)
@corex.output(
    "acceleration",
    value_type="COREX.DataTypes.Path",
    label="Acceleration",
    description="Managed path to the recovered acceleration result.",
)
@corex.output(
    "damage",
    value_type="COREX.DataTypes.Path",
    label="Damage",
    description="Managed path to the calculated fatigue damage result.",
)
@corex.output(
    "force",
    value_type="COREX.DataTypes.Path",
    label="Force",
    description="Managed path to the recovered force result.",
)
@corex.output(
    "moment",
    value_type="COREX.DataTypes.Path",
    label="Moment",
    description="Managed path to the recovered moment result.",
)
@corex.output(
    "manifest",
    value_type="COREX.DataTypes.Path",
    label="Result Manifest",
    description="Managed path to the MARS result manifest.",
)
@corex.output(
    "files",
    value_type=corex.Any,
    label="Result Files",
    description="Collection of managed result artifacts published by MARS.",
)
@corex.text(
    "rst_scope_name",
    default="All result-support nodes",
    label="RST Scope Name",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="RST",
)
@corex.dropdown(
    "rst_shell_layer",
    default="top",
    options=("top", "bottom", "mid"),
    label="RST Shell Layer",
    _inline_editor="",
    _inspector_editor="enum",
    _property_group="RST",
)
@corex.switch(
    "output_von_mises",
    default=True,
    label="Von Mises",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Results",
)
@corex.switch(
    "output_max_principal",
    default=False,
    label="Maximum Principal",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Results",
)
@corex.switch(
    "output_min_principal",
    default=False,
    label="Minimum Principal",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Results",
)
@corex.switch(
    "output_deformation",
    default=False,
    label="Deformation",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Results",
)
@corex.switch(
    "output_velocity",
    default=False,
    label="Velocity",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Results",
)
@corex.switch(
    "output_acceleration",
    default=False,
    label="Acceleration",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Results",
)
@corex.switch(
    "output_force_moment",
    default=False,
    label="Force / Moment",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Results",
)
@corex.switch(
    "output_damage",
    default=False,
    label="Fatigue Damage",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Results",
)
@corex.number(
    "skip_first_modes",
    default=0,
    label="Skip First Modes",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Modes",
)
@corex.number(
    "skip_last_modes",
    default=0,
    label="Skip Last Modes",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Modes",
)
@corex.switch(
    "include_steady_state",
    default=False,
    label="Include Steady-State Stress",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Modes",
)
@corex.text(
    "fatigue_A",
    default="",
    label="Fatigue A",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Fatigue",
)
@corex.text(
    "fatigue_m",
    default="",
    label="Fatigue m",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Fatigue",
)
@corex.switch(
    "plasticity_enabled",
    default=False,
    label="Enable Plasticity",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Plasticity",
)
@corex.dropdown(
    "plasticity_method",
    default="neuber",
    options=("neuber", "glinka", "ibg"),
    label="Method",
    _inline_editor="",
    _inspector_editor="enum",
    _property_group="Plasticity",
)
@corex.number(
    "plasticity_max_iterations",
    default=60,
    label="Maximum Iterations",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Plasticity",
)
@corex.number(
    "plasticity_tolerance",
    default=1e-10,
    label="Tolerance",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Plasticity",
)
@corex.text(
    "plasticity_default_temperature",
    default="",
    label="Default Temperature",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Plasticity",
)
@corex.text(
    "plasticity_temperature_column",
    default="",
    label="Temperature Column",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Plasticity",
)
@corex.text(
    "plasticity_poisson_ratio",
    default="",
    label="Poisson Ratio",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Plasticity",
)
@corex.dropdown(
    "plasticity_extrapolation_mode",
    default="linear",
    options=("linear", "plateau"),
    label="Extrapolation",
    _inline_editor="",
    _inspector_editor="enum",
    _property_group="Plasticity",
)
@corex.number(
    "timeout_seconds",
    default=3600.0,
    label="Timeout (seconds)",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="Runtime",
)
@corex.number(
    "termination_grace_seconds",
    default=2.0,
    label="Termination Grace (seconds)",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="Runtime",
)
def mars_batch_solve(ctx, settings):
    result = execute_mars_batch_solve(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="mars_runtime")
    return dict(result.outputs)


@corex.node(
    id="mars.time_history",
    name="MARS Time History",
    category=("MARS",),
    icon="icons/mars_icon_64.png",
    description="Builds and runs one MARS node time-history job and returns its CSV.",
    keywords=("mars", "time history", "response"),
)
@corex.path(
    "modal_coordinates",
    default="",
    label="Modal Coordinates",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="path",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Path to modal coordinates used to reconstruct physical responses.",
    _port_label="Modal Coordinates",
    _port_required=True,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "modal_stress",
    default="",
    label="Modal Stress",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Path to modal stress coefficients for response recovery.",
    _port_label="Modal Stress",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "modal_deformation",
    default="",
    label="Modal Deformation",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Path to modal deformation coefficients for response recovery.",
    _port_label="Modal Deformation",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "modal_force_moment",
    default="",
    label="Modal Force / Moment",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Path to modal force and moment coefficients for response recovery.",
    _port_label="Modal Force / Moment",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "steady_state_stress",
    default="",
    label="Steady-State Stress",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Optional path to steady-state stress values added to the modal response.",
    _port_label="Steady-State Stress",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "temperature_field",
    default="",
    label="Temperature Field",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Optional path to the temperature field used for material evaluation.",
    _port_label="Temperature Field",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "material_profile",
    default="",
    label="Material Profile",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Optional path to temperature-dependent material properties.",
    _port_label="Material Profile",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.path(
    "modal_rst",
    default="",
    label="Modal RST",
    file_filter=MARS_INPUT_FILTER,
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Optional Ansys modal result file used as a guided MARS input.",
    _port_label="Modal RST",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.output(
    "history_csv",
    value_type="COREX.DataTypes.Path",
    label="Time History CSV",
    description="Managed CSV containing the recovered response history for the selected node.",
)
@corex.output(
    "manifest",
    value_type="COREX.DataTypes.Path",
    label="Result Manifest",
    description="Managed path to the MARS result manifest.",
)
@corex.output(
    "files",
    value_type=corex.Any,
    label="Result Files",
    description="Collection of managed result artifacts published by MARS.",
)
@corex.text(
    "rst_scope_name",
    default="All result-support nodes",
    label="RST Scope Name",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="RST",
)
@corex.dropdown(
    "rst_shell_layer",
    default="top",
    options=("top", "bottom", "mid"),
    label="RST Shell Layer",
    _inline_editor="",
    _inspector_editor="enum",
    _property_group="RST",
)
@corex.number(
    "node_id",
    default=1,
    label="Node ID",
    _inline_editor="text",
    _inspector_editor="",
    _property_group="Modes",
)
@corex.dropdown(
    "output",
    default="von_mises",
    options=TIME_HISTORY_OUTPUTS,
    label="Result",
    _inline_editor="enum",
    _inspector_editor="enum",
    _property_group="Results",
)
@corex.number(
    "skip_first_modes",
    default=0,
    label="Skip First Modes",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Modes",
)
@corex.number(
    "skip_last_modes",
    default=0,
    label="Skip Last Modes",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Modes",
)
@corex.switch(
    "include_steady_state",
    default=False,
    label="Include Steady-State Stress",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Modes",
)
@corex.switch(
    "plasticity_enabled",
    default=False,
    label="Enable Plasticity",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Plasticity",
)
@corex.dropdown(
    "plasticity_method",
    default="neuber",
    options=("neuber", "glinka", "ibg"),
    label="Method",
    _inline_editor="",
    _inspector_editor="enum",
    _property_group="Plasticity",
)
@corex.number(
    "plasticity_max_iterations",
    default=60,
    label="Maximum Iterations",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Plasticity",
)
@corex.number(
    "plasticity_tolerance",
    default=1e-10,
    label="Tolerance",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Plasticity",
)
@corex.text(
    "plasticity_default_temperature",
    default="",
    label="Default Temperature",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Plasticity",
)
@corex.text(
    "plasticity_temperature_column",
    default="",
    label="Temperature Column",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Plasticity",
)
@corex.text(
    "plasticity_poisson_ratio",
    default="",
    label="Poisson Ratio",
    _inline_editor="",
    _inspector_editor="",
    _property_group="Plasticity",
)
@corex.dropdown(
    "plasticity_extrapolation_mode",
    default="linear",
    options=("linear", "plateau"),
    label="Extrapolation",
    _inline_editor="",
    _inspector_editor="enum",
    _property_group="Plasticity",
)
@corex.number(
    "timeout_seconds",
    default=3600.0,
    label="Timeout (seconds)",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="Runtime",
)
@corex.number(
    "termination_grace_seconds",
    default=2.0,
    label="Termination Grace (seconds)",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="Runtime",
)
def mars_time_history(ctx, settings):
    result = execute_mars_time_history(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="mars_runtime")
    return dict(result.outputs)


@corex.node(
    id="mars.run_job",
    name="MARS Run Job",
    category=("MARS",),
    icon="icons/mars_icon_64.png",
    description="Runs an existing MARS schema-v1 JSON job while containing all outputs inside COREX-managed storage.",
    keywords=("mars", "job", "json"),
)
@corex.path(
    "job",
    default="",
    label="MARS Job",
    file_filter=MARS_JOB_FILTER,
    port=True,
    _inline_editor="path",
    _inspector_editor="path",
    _property_group="Inputs",
    _port_accepted_data_types=(),
    _port_description="Path to an existing MARS schema-v1 JSON job.",
    _port_label="MARS Job",
    _port_required=True,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.output(
    "von_mises",
    value_type="COREX.DataTypes.Path",
    label="Von Mises",
    description="Managed path to the recovered von Mises stress result.",
)
@corex.output(
    "max_principal",
    value_type="COREX.DataTypes.Path",
    label="Max Principal",
    description="Managed path to the recovered maximum principal stress result.",
)
@corex.output(
    "min_principal",
    value_type="COREX.DataTypes.Path",
    label="Min Principal",
    description="Managed path to the recovered minimum principal stress result.",
)
@corex.output(
    "deformation",
    value_type="COREX.DataTypes.Path",
    label="Deformation",
    description="Managed path to the recovered deformation result.",
)
@corex.output(
    "velocity",
    value_type="COREX.DataTypes.Path",
    label="Velocity",
    description="Managed path to the recovered velocity result.",
)
@corex.output(
    "acceleration",
    value_type="COREX.DataTypes.Path",
    label="Acceleration",
    description="Managed path to the recovered acceleration result.",
)
@corex.output(
    "damage",
    value_type="COREX.DataTypes.Path",
    label="Damage",
    description="Managed path to the calculated fatigue damage result.",
)
@corex.output(
    "force",
    value_type="COREX.DataTypes.Path",
    label="Force",
    description="Managed path to the recovered force result.",
)
@corex.output(
    "moment",
    value_type="COREX.DataTypes.Path",
    label="Moment",
    description="Managed path to the recovered moment result.",
)
@corex.output(
    "manifest",
    value_type="COREX.DataTypes.Path",
    label="Result Manifest",
    description="Managed path to the MARS result manifest.",
)
@corex.output(
    "files",
    value_type=corex.Any,
    label="Result Files",
    description="Collection of managed result artifacts published by MARS.",
)
@corex.number(
    "timeout_seconds",
    default=3600.0,
    label="Timeout (seconds)",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="Runtime",
)
@corex.number(
    "termination_grace_seconds",
    default=2.0,
    label="Termination Grace (seconds)",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="Runtime",
)
def mars_run_job(ctx, settings):
    result = execute_mars_run_job(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="mars_runtime")
    return dict(result.outputs)
'''

__all__ = ["SOURCE"]
