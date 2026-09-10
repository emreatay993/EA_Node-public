from __future__ import annotations

import math
import traceback
from dataclasses import replace
from collections.abc import Mapping

from ea_node_editor.graph.boundary_adapters import register_node_type_size_resolver
from ea_node_editor.nodes.builtins.data_control import NUMBER_SLIDER_PILL_HEIGHT
from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type_spec
from ea_node_editor.nodes.decorators import (
    plugin_descriptor,
)
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.node_specs import (
    DynamicPortGroupSpec,
    NodeTypeSpec,
    PortSpec,
    PropertySpec,
)
from ea_node_editor.nodes.python_script_declaration import (
    python_script_output_keys,
    python_script_parameter_keys,
    python_script_runtime_namespace,
    resolve_python_script_spec,
)
from ea_node_editor.runtime_contracts import DataTree
from ea_node_editor.runtime_contracts.scientific_values import (
    materialize_script_values, snapshot_scientific_values,
)


PYTHON_SCRIPT_DEFAULT_SOURCE = """# Decorator templates: uncomment a line, then add its name to run(ctx, ...).
# @corex.input("values", value_type=float, structure="tree", required=True, section="Data")
# @corex.output("image", value_type=corex.Image)
# @corex.text("title", default="Plot", section="Display", port=True)
# @corex.number("count", default=10, minimum=1, maximum=100, section="Settings")
# @corex.switch("show_legend", default=True, section="Display", port=True)
# @corex.dropdown("mode", default="Mean", options=("Mean", "Maximum"), section="Settings")
# @corex.slider("line_width", default=2.0, minimum=0.5, maximum=8.0, step=0.5, section="Display", port=True)
# @corex.color("accent", default="#336699", section="Display")
# @corex.path("source_file", default="", file_filter="All files (*)", section="Files")
# @corex.text_area("notes", default="", section="Notes")
# @corex.interval("bounds", default=(0.0, 1.0), section="Ranges", port=True)
# @corex.list("labels", default=["A"], item_type=str, section="Data", port=True)

@corex.node
@corex.input("payload", value_type=corex.Any, description="Value supplied to the script.")
@corex.output("result", value_type=corex.Any, description="Value returned by the script.")
def run(ctx, payload):
    return {"result": payload}
"""


_PYTHON_SCRIPT_FRAME_FILENAME = "<string>"
_PYTHON_SCRIPT_FRAME_DISPLAY = "<script>"


class PythonScriptError(RuntimeError):
    """Raised when a Python Script node's user code fails.

    Carries a traceback limited to the user's own script frames so host
    internals stay hidden unless developer mode is active.
    """

    def __init__(self, message: str, *, user_traceback: str) -> None:
        super().__init__(message)
        self.user_traceback = user_traceback


def _sanitize_user_script_traceback(exc: BaseException) -> str:
    user_frames = [
        frame
        for frame in traceback.extract_tb(exc.__traceback__)
        if frame.filename == _PYTHON_SCRIPT_FRAME_FILENAME
    ]
    exception_only = traceback.format_exception_only(type(exc), exc)
    if not user_frames:
        return "".join(exception_only).strip()
    relabeled = [
        traceback.FrameSummary(
            _PYTHON_SCRIPT_FRAME_DISPLAY,
            frame.lineno,
            frame.name,
            line=frame.line,
        )
        for frame in user_frames
    ]
    return "".join(
        [
            "Traceback (most recent call last):\n",
            *traceback.format_list(relabeled),
            *exception_only,
        ]
    ).strip()


class PythonScriptNodePlugin:
    def spec(self) -> NodeTypeSpec:
        return builtin_node_type_spec(
            type_id="core.python_script",
            display_name="Python Script",
            category_path=("Core",),
            description="Runs custom Python logic in trusted local mode.",
            keywords=("python", "script", "code"),
            ports=(),
            properties=(
                PropertySpec(
                    "script",
                    "str",
                    PYTHON_SCRIPT_DEFAULT_SOURCE,
                    "Script",
                ),
                PropertySpec(
                    "timeout_sec",
                    "float",
                    0.0,
                    "Timeout (sec)",
                ),
            ),
            instance_spec_resolver=resolve_python_script_spec,
        )

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        script = str(ctx.properties.get("script", ""))
        if not script.strip():
            return NodeResult()

        spec = resolve_python_script_spec(self.spec(), ctx.properties)
        parameter_keys = python_script_parameter_keys(spec)
        output_keys = python_script_output_keys(spec)
        scope = {"corex": python_script_runtime_namespace()}
        try:
            exec(
                compile(script, _PYTHON_SCRIPT_FRAME_FILENAME, "exec"),
                scope,
                scope,
            )
            entrypoint = scope.get("run")
            if not callable(entrypoint):
                raise TypeError("Python Script run entrypoint is not callable")
            ctx = replace(ctx, inputs=materialize_script_values(ctx.inputs))
            value = entrypoint(
                ctx,
                **{
                    key: (
                        ctx.inputs[key]
                        if key in ctx.inputs
                        else ctx.properties.get(key)
                    )
                    for key in parameter_keys
                },
            )
            if isinstance(value, NodeResult):
                result = value
            elif isinstance(value, Mapping):
                result = NodeResult(outputs=dict(value))
            else:
                raise TypeError("Python Script run must return a mapping or NodeResult")
            unknown_outputs = sorted(set(result.outputs) - set(output_keys))
            if unknown_outputs:
                raise ValueError(
                    "Python Script returned undeclared outputs: "
                    + ", ".join(unknown_outputs)
                )
            result = replace(result, outputs=snapshot_scientific_values(result.outputs))
        except BaseException as exc:  # noqa: BLE001
            user_traceback = _sanitize_user_script_traceback(exc)
            ctx.log_error(traceback.format_exc() if ctx.developer_mode else user_traceback)
            raise PythonScriptError(
                str(exc) or type(exc).__name__,
                user_traceback=user_traceback,
            ) from exc

        return result


TRIGGER_TYPE_ID = "core.trigger"
TRIGGER_SURFACE_VARIANT = "trigger"
# Button-only pill: narrower than the slider/select pills but height-locked to
# the same shared pill height (see _trigger_node_size and standard_metrics).
TRIGGER_DEFAULT_WIDTH = 160.0
TRIGGER_MIN_WIDTH = 120.0


class TriggerNodePlugin:
    def spec(self) -> NodeTypeSpec:
        return NodeTypeSpec(
            type_id=TRIGGER_TYPE_ID,
            display_name="Trigger",
            category_path=("Data", "Control"),
            description="Stop downstream nodes from running until you click the button.",
            icon="",
            keywords=("button", "action", "run", "dam", "gate", "block"),
            ports=(
                PortSpec(
                    "input",
                    "in",
                    "data",
                    'COREX.DataTypes.Any',
                    label="Input",
                    required=False,
                    data_access="tree",
                    description="The data that is blocked until you click the button.",
                ),
                PortSpec(
                    "output",
                    "out",
                    "data",
                    'COREX.DataTypes.Any',
                    label="Output",
                    data_access="tree",
                    description=(
                        "The current output. The output is not updated until you "
                        "click the button."
                    ),
                ),
            ),
            properties=(),
            collapsible=False,
            surface_variant=TRIGGER_SURFACE_VARIANT,
        )

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        value = ctx.inputs["input"] if "input" in ctx.inputs else DataTree.from_item(True)
        return NodeResult(outputs={"output": value})


def _trigger_node_size(node, _spec, *, base_width: float, base_height: float) -> tuple[float, float]:
    del base_height
    width = float(base_width)
    if getattr(node, "custom_width", None) is None:
        width = max(width, TRIGGER_DEFAULT_WIDTH)
    return max(width, TRIGGER_MIN_WIDTH), NUMBER_SLIDER_PILL_HEIGHT


register_node_type_size_resolver(TRIGGER_TYPE_ID, _trigger_node_size)


STREAM_GATE_OUTPUT_IDS_PROPERTY = "output_port_ids"
DEFAULT_STREAM_GATE_OUTPUT_IDS = ("output_0", "output_1")


def normalize_stream_gate_output_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return DEFAULT_STREAM_GATE_OUTPUT_IDS
    output_ids: list[str] = []
    for item in value:
        output_id = str(item).strip()
        if output_id and output_id not in {"stream", "gate"} and output_id not in output_ids:
            output_ids.append(output_id)
    return tuple(output_ids) or DEFAULT_STREAM_GATE_OUTPUT_IDS


def resolve_stream_gate_output_ports(
    properties: Mapping[str, object],
) -> tuple[PortSpec, ...]:
    return tuple(
        PortSpec(
            output_id,
            "out",
            "data",
            'COREX.DataTypes.Any',
            label=f"Output {ordinal}",
            data_access="tree",
            description=f"Tree published when Gate selects output {ordinal}.",
        )
        for ordinal, output_id in enumerate(
            normalize_stream_gate_output_ids(
                properties.get(
                    STREAM_GATE_OUTPUT_IDS_PROPERTY,
                    DEFAULT_STREAM_GATE_OUTPUT_IDS,
                )
            )
        )
    )


def next_stream_gate_output_id(properties: Mapping[str, object]) -> str:
    used = set(
        normalize_stream_gate_output_ids(
            properties.get(
                STREAM_GATE_OUTPUT_IDS_PROPERTY,
                DEFAULT_STREAM_GATE_OUTPUT_IDS,
            )
        )
    )
    suffix = 0
    while f"output_{suffix}" in used:
        suffix += 1
    return f"output_{suffix}"


def stream_gate_index(value: object) -> int:
    if isinstance(value, (bool, str, bytes, bytearray)):
        raise ValueError("Stream Gate gate must be numeric.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Stream Gate gate must be numeric.") from exc
    if not math.isfinite(numeric):
        raise ValueError("Stream Gate gate must be finite.")
    return math.floor(numeric + 0.5) if numeric >= 0 else math.ceil(numeric - 0.5)


class StreamGateNodePlugin:
    def spec(self) -> NodeTypeSpec:
        return builtin_node_type_spec(
            type_id="core.stream_gate",
            display_name="Stream Gate",
            category_path=("Core",),
            description="Routes a data tree to one selected output.",
            keywords=("stream", "gate", "route", "switch"),
            ports=(
                PortSpec(
                    "stream",
                    "in",
                    "data",
                    'COREX.DataTypes.Any',
                    required=True,
                    data_access="tree",
                    description="Tree to route.",
                ),
                PortSpec(
                    "gate",
                    "in",
                    "data",
                    'COREX.DataTypes.Double',
                    required=False,
                    uses_property_default=True,
                    accepted_data_types=('COREX.DataTypes.Int',),
                    description="Zero-based output index; midpoint values round away from zero.",
                ),
            ),
            properties=(
                PropertySpec("gate", "float", 0.0, "Gate", inline_editor="number"),
                PropertySpec(
                    STREAM_GATE_OUTPUT_IDS_PROPERTY,
                    "json",
                    list(DEFAULT_STREAM_GATE_OUTPUT_IDS),
                    "Outputs",
                    inspector_visible=False,
                ),
            ),
            dynamic_port_groups=(
                DynamicPortGroupSpec(
                    group_id="outputs",
                    property_key=STREAM_GATE_OUTPUT_IDS_PROPERTY,
                    direction="out",
                    ports_resolver=resolve_stream_gate_output_ports,
                    key_factory=next_stream_gate_output_id,
                    minimum=1,
                    rename_mode="label",
                ),
            ),
        )

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        output_ids = normalize_stream_gate_output_ids(
            ctx.properties.get(STREAM_GATE_OUTPUT_IDS_PROPERTY, DEFAULT_STREAM_GATE_OUTPUT_IDS)
        )
        index = stream_gate_index(ctx.inputs.get("gate", ctx.properties.get("gate", 0.0)))
        if index < 0 or index >= len(output_ids):
            raise ValueError(
                f"Stream Gate output index {index} is outside 0..{len(output_ids) - 1}."
            )
        return NodeResult(outputs={output_ids[index]: ctx.inputs["stream"]})


CORE_NODE_DESCRIPTORS = (
    plugin_descriptor(PythonScriptNodePlugin),
    plugin_descriptor(TriggerNodePlugin),
    plugin_descriptor(StreamGateNodePlugin),
)


__all__ = [
    "CORE_NODE_DESCRIPTORS",
    "DEFAULT_STREAM_GATE_OUTPUT_IDS",
    "STREAM_GATE_OUTPUT_IDS_PROPERTY",
    "StreamGateNodePlugin",
    "TriggerNodePlugin",
    "normalize_stream_gate_output_ids",
    "stream_gate_index",
]
