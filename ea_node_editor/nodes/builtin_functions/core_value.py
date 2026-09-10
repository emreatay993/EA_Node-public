# Purpose: Hold inert decorated source for ordinary core and value built-ins.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_builtin_function_infrastructure.py

SOURCE = '''import corex
import json

from ea_node_editor.nodes.builtins.core_values import (
    COLOR_DATA_TYPE_ID,
    is_color_payload,
)
from ea_node_editor.runtime_contracts import TypedInlineValue
from ea_node_editor.runtime_contracts.data_tree import resolve_single_run_inputs


@corex.node(
    id="core.constant",
    _solution_reuse_scope="session",
    name="Constant",
    category=("Core",),
    icon="core/data_object.svg",
    description="Publishes a reusable JSON-compatible value and its text representation.",
    keywords=("constant", "value", "json"),
    _property_output_collisions=("value",),
)
@corex.output(
    "value",
    value_type="COREX.DataTypes.JsonValue",
    label="",
    description="The configured JSON-compatible value.",
)
@corex.output(
    "as_text",
    value_type="COREX.DataTypes.String",
    label="",
    description="The configured value serialized as JSON text.",
)
@corex.text(
    "value",
    default="",
    label="Value",
    _property_type="json",
    _property_default={"value": 0},
    _inline_editor="",
)
def constant(ctx, settings):
    del ctx
    value = settings.to_dict()["value"]
    try:
        as_text = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Constant node value must be JSON serializable.") from exc
    return {"value": value, "as_text": as_text}


@corex.node(
    id="core.logger",
    name="Logger",
    category=("Core",),
    icon="core/article.svg",
    description="Writes an informational, warning, or error message to the workflow run log.",
    keywords=("log", "message", "diagnostics"),
)
@corex.text(
    "message",
    default="log message",
    label="Message",
    port=True,
    _port_label="",
    _port_description="Message to log; overrides the configured Message property when connected.",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.String",
)
@corex.dropdown(
    "level",
    default="info",
    label="Level",
    options=("info", "warning", "error"),
)
def logger(ctx, settings):
    inputs = resolve_single_run_inputs(ctx.inputs, node_name="Logger")
    message = str(inputs.get("message", settings.message))
    level = str(settings.level).strip().lower()
    if level not in {"info", "warning", "error"}:
        ctx.log_warning(f"Logger level '{level}' is invalid; using 'info'.")
        level = "info"
    if level == "warning":
        ctx.log_warning(message)
    elif level == "error":
        ctx.log_error(message)
    else:
        ctx.log_info(message)
    return {}


@corex.node(
    id="core.if",
    _solution_reuse_scope="session",
    name="If",
    category=("Core",),
    icon="call_split",
    description="Selects one of two data trees from a Boolean condition.",
    keywords=("if", "condition", "select", "branch"),
)
@corex.input(
    "condition",
    value_type="COREX.DataTypes.Bool",
    label="",
    required=True,
    description="Boolean item selecting the true or false value.",
)
@corex.input(
    "true_value",
    value_type="COREX.DataTypes.Any",
    structure="tree",
    label="",
    required=True,
    description="Tree returned when Condition is true.",
)
@corex.input(
    "false_value",
    value_type="COREX.DataTypes.Any",
    structure="tree",
    label="",
    required=False,
    description="Optional tree returned when Condition is false.",
)
@corex.output(
    "result",
    value_type="COREX.DataTypes.Any",
    structure="tree",
    label="",
    description="Selected tree; empty when the optional false value is absent.",
)
def core_if(ctx, condition, true_value, false_value):
    key = "true_value" if bool(condition) else "false_value"
    if key not in ctx.inputs:
        return {}
    return {"result": true_value if key == "true_value" else false_value}


@corex.node(
    id="data.deconstruct_color",
    _solution_reuse_scope="durable",
    name="Deconstruct Color",
    category=("Utilities", "Color"),
    icon="palette",
    description="Extracts the stored channels from a typed Color value.",
    keywords=("color", "deconstruct", "red", "green", "blue", "alpha"),
)
@corex.input(
    "color",
    value_type="COREX.DataTypes.Color",
    label="Color",
    required=True,
    description="Color value to deconstruct.",
)
@corex.output(
    "red",
    value_type="COREX.DataTypes.Double",
    label="Red",
    description="Red channel value.",
)
@corex.output(
    "green",
    value_type="COREX.DataTypes.Double",
    label="Green",
    description="Green channel value.",
)
@corex.output(
    "blue",
    value_type="COREX.DataTypes.Double",
    label="Blue",
    description="Blue channel value.",
)
@corex.output(
    "alpha",
    value_type="COREX.DataTypes.Double",
    label="Alpha",
    description="Alpha channel value.",
)
def deconstruct_color(ctx, color):
    del ctx
    if (
        not isinstance(color, TypedInlineValue)
        or color.data_type_id != COLOR_DATA_TYPE_ID
        or color.schema_version != 1
        or not is_color_payload(color.payload)
    ):
        raise ValueError("Color input is invalid")
    payload = color.payload
    return {
        "red": payload["R"],
        "green": payload["G"],
        "blue": payload["B"],
        "alpha": payload["A"],
    }
'''

__all__ = ["SOURCE"]
