# Purpose: Hold inert decorated source for ordinary data-control built-ins.
# Map: feature_routes/surface_input_and_inline_controls.md
# Tests: tests/test_boolean_toggle_node.py

SOURCE = r'''import corex

from ea_node_editor.nodes.builtins.data_control import (
    execute_boolean_toggle,
    execute_number_slider,
    execute_panel,
    execute_select,
)


@corex.node(
    id="data.boolean_toggle",
    _solution_reuse_scope="durable",
    name="Boolean Toggle",
    category=("Data", "Control"),
    icon="check",
    description="Boolean (true/false) toggle.",
    keywords=("switch",),
    _collapsible=False,
    _surface_variant="boolean_toggle",
)
@corex.switch(
    "value",
    default=False,
    label="Value",
    _inspector_editor="toggle",
)
@corex.output(
    "boolean",
    value_type="COREX.DataTypes.Bool",
    structure="tree",
    label="",
    description="Current Boolean value as a single-item tree.",
)
def boolean_toggle(ctx, settings):
    result = execute_boolean_toggle(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="boolean_toggle")
    return dict(result.outputs)


@corex.node(
    id="data.number_slider",
    _solution_reuse_scope="durable",
    name="Number Slider",
    category=("Data", "Control"),
    icon="linear_scale",
    description="Publishes a numeric value chosen with an on-canvas slider between a configurable minimum and maximum. Double-click the value to edit the range, rounding mode, and decimal places.",
    keywords=("number", "slider", "value", "range", "constant", "control"),
    _collapsible=False,
    _property_output_collisions=("value",),
    _surface_variant="number_slider",
)
@corex.number("value", default=5.0, label="Value", _inline_editor="")
@corex.number("minimum", default=0.0, label="Minimum", _inline_editor="")
@corex.number("maximum", default=10.0, label="Maximum", _inline_editor="")
@corex.dropdown(
    "rounding",
    default="decimal",
    options=("decimal", "integer"),
    label="Rounding",
    _inline_editor="",
)
@corex.number("decimals", default=2, label="Decimal Places", _inline_editor="")
@corex.output(
    "value",
    value_type="COREX.DataTypes.Double",
    label="",
    description="The current slider value; whole numbers in integer rounding mode.",
)
def number_slider(ctx, settings):
    result = execute_number_slider(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="number_slider")
    return dict(result.outputs)


@corex.node(
    id="data.panel",
    _solution_reuse_scope="session",
    name="Panel",
    category=("Data", "Control"),
    icon="core/article.svg",
    description="Enter text or branched data. Keep exact text, infer finite numbers automatically, or require numeric values. Connected input passes through unchanged.",
    keywords=('"', "text", "watch"),
    _collapsible=False,
    _surface_variant="panel",
)
@corex.input(
    "input",
    value_type=corex.Any,
    structure="tree",
    required=False,
    label="Input",
    description="The input value.",
)
@corex.output(
    "output",
    value_type=corex.Any,
    structure="tree",
    label="Output",
    description="The output value.",
)
@corex.text_area(
    "value",
    default="",
    label="Value",
    _inline_editor="",
    _inspector_editor="textarea",
)
@corex.number("mode", default=0, label="Mode", _inline_editor="")
@corex.number("font_size", default=12, label="Font Size", _inline_editor="")
@corex.number("alignment", default=2, label="Alignment", _inline_editor="")
@corex.switch("auto_resize", default=True, label="Auto Resize", _inline_editor="")
@corex.dropdown("interpretation", default="text", options=("text", "auto", "number"), label="Interpret values as", _inline_editor="")
def panel(ctx, input, settings):
    result = execute_panel(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="panel")
    return dict(result.outputs)


@corex.node(
    id="data.select",
    _solution_reuse_scope="durable",
    name="Select",
    category=("Data", "Control"),
    icon="arrow_drop_down_circle",
    description="A dropdown that allows to select a value from the list.",
    keywords=("dropdown", "combobox", "option"),
    _collapsible=False,
    _surface_variant="select",
)
@corex.output(
    "selected_value",
    value_type="COREX.DataTypes.String",
    structure="tree",
    label="Selected value",
    description="The value selected by the user.",
)
@corex.text(
    "options",
    default="",
    label="Options",
    _property_type="json",
    _property_default=[
        {"name": "Option A", "value": "0"},
        {"name": "Option B", "value": "1"},
    ],
    _inline_editor="",
    _inspector_visible=False,
)
@corex.number(
    "selected_index",
    default=0,
    label="Selected Option",
    _inline_editor="",
    _inspector_visible=False,
)
def select(ctx, settings):
    result = execute_select(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="select")
    return dict(result.outputs)
'''

__all__ = ["SOURCE"]
