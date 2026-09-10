"""Documentation-only custom-node declaration for the declarative controls guide.

This intentionally does not register a production Signal Plot node.  The
validation helper exists so the documentation test imports this exact module
through the public SDK and validates the declaration with the real registry.
"""

from __future__ import annotations

from ea_node_editor.nodes.decorators import (
    in_port,
    node_type,
    out_port,
    prop_bool,
    prop_enum,
    prop_float,
    prop_int,
    prop_interval_1d,
    prop_str,
)
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.node_specs import (
    PropertyConditionSpec,
    SettingsGroupItemSpec,
    SettingsGroupSpec,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    GRAPH_DICTIONARY_DATA_TYPE_ID,
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
    Interval1D,
)


@node_type(
    type_id="docs.signal_plot_style_controls",
    display_name="Signal Plot Style Controls (Documentation)",
    category_path=("Documentation", "Examples"),
    # A custom plugin ships this local asset beside its Python module.
    icon="icons/signal-plot.svg",
    description="Documentation-only declaration for COREX declarative node controls.",
    keywords=("documentation", "signal", "plot", "interval", "controls"),
    ports=(
        in_port(
            "signal_name",
            data_type=STRING_DATA_TYPE_ID,
            required=False,
            uses_property_default=True,
            description="Optional upstream signal name; otherwise use the authored local value.",
        ),
        in_port(
            "result_bound",
            data_type=INTERVAL_1D_GRAPH_DATA_TYPE_ID,
            required=False,
            uses_property_default=True,
            description="Optional upstream interval; otherwise use the authored local bound.",
        ),
        out_port(
            "plot_request",
            data_type=GRAPH_DICTIONARY_DATA_TYPE_ID,
        ),
    ),
    properties=(
        prop_str(
            "signal_name",
            "Pressure",
            "Signal name",
            inline_editor="text",
            inspector_editor="text",
        ),
        prop_float(
            "sample_rate_hz",
            48_000.0,
            "Sample rate (Hz)",
            minimum=8_000.0,
            maximum=192_000.0,
            step=1_000.0,
            inline_editor="slider",
        ),
        prop_bool(
            "show_grid",
            True,
            "Show grid",
            inline_editor="toggle",
            inspector_editor="toggle",
        ),
        prop_enum(
            "cyclic_symmetry_mode",
            "None",
            "Cyclic symmetry mode",
            values=("None", "Manual", "Automatic"),
            inline_editor="enum",
            inspector_editor="enum",
        ),
        prop_int(
            "number_of_sectors",
            12,
            "Number of sectors",
            minimum=2,
            maximum=360,
            step=1,
            inline_editor="slider",
            enabled_when=PropertyConditionSpec(
                property_key="cyclic_symmetry_mode",
                values=("Manual",),
            ),
        ),
        prop_enum(
            "color_map",
            "Viridis",
            "Color map",
            values=("Viridis", "Plasma", "Magma", "Cividis", "Turbo"),
            inline_editor="enum",
            inspector_editor="enum",
            searchable=True,
        ),
        prop_interval_1d(
            "result_bound",
            Interval1D(0.0, 100.0),
            "Result bound",
            minimum=-200.0,
            maximum=200.0,
            step=0.1,
            direction="increasing",
        ),
    ),
    settings_groups=(
        SettingsGroupSpec(
            group_id="signal",
            label="Signal",
            items=(
                SettingsGroupItemSpec(port_key="signal_name", property_key="signal_name"),
                SettingsGroupItemSpec(property_key="sample_rate_hz"),
                SettingsGroupItemSpec(property_key="show_grid"),
            ),
        ),
        SettingsGroupSpec(
            group_id="display",
            label="Display",
            items=(
                SettingsGroupItemSpec(property_key="cyclic_symmetry_mode"),
                SettingsGroupItemSpec(property_key="number_of_sectors"),
                SettingsGroupItemSpec(property_key="color_map"),
                SettingsGroupItemSpec(port_key="result_bound", property_key="result_bound"),
            ),
        ),
    ),
)
class SignalPlotStyleControlsNode:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult(
            outputs={
                "plot_request": {
                    "signal_name": ctx.inputs.get("signal_name", ctx.properties["signal_name"]),
                    "result_bound": ctx.inputs.get("result_bound", ctx.properties["result_bound"]),
                }
            }
        )


def validate_declaration():
    """Validate the documentation declaration with the real Node SDK registry."""
    registry = NodeRegistry()
    registry.register(SignalPlotStyleControlsNode)
    return registry.get_spec("docs.signal_plot_style_controls")
