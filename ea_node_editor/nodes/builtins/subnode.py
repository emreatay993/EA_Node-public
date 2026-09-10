from __future__ import annotations

from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type
from ea_node_editor.graph.subnode_contract import (
    SUBNODE_AUTHORING_TYPE_IDS,
    SUBNODE_INPUT_TYPE_ID,
    SUBNODE_OUTPUT_TYPE_ID,
    SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY,
    SUBNODE_PIN_DATA_ACCESS_PROPERTY,
    SUBNODE_PIN_DATA_ACCESS_VALUES,
    SUBNODE_PIN_DATA_TYPE_PROPERTY,
    SUBNODE_PIN_KIND_PROPERTY,
    SUBNODE_PIN_KIND_VALUES,
    SUBNODE_PIN_LABEL_PROPERTY,
    SUBNODE_PIN_PORT_KEY,
    SUBNODE_PIN_TYPE_IDS,
    SUBNODE_TYPE_ID,
    SubnodePinDefinition,
    default_subnode_pin_label,
    is_subnode_authoring_type,
    is_subnode_input_type,
    is_subnode_output_type,
    is_subnode_pin_type,
    is_subnode_shell_type,
    normalize_subnode_pin_accepted_data_types,
    normalize_subnode_pin_data_type,
    normalize_subnode_pin_data_access,
    normalize_subnode_pin_kind,
    resolve_subnode_pin_definition,
)
from ea_node_editor.nodes.decorators import in_port, out_port, plugin_descriptor, prop_enum, prop_str
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.node_specs import PropertySpec
from ea_node_editor.runtime_contracts import GRAPH_DATA_TYPE_ID


@builtin_node_type(
    type_id=SUBNODE_TYPE_ID,
    display_name="Subnode",
    category_path=("Subnode",),
    description="Container shell whose outer ports are derived from direct child pin nodes.",
    keywords=("subnode", "group", "container"),
    ports=(),
    properties=(),
    runtime_behavior="compile_only",
)
class SubnodeNodePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


@builtin_node_type(
    type_id=SUBNODE_INPUT_TYPE_ID,
    display_name="Subnode Input",
    category_path=("Subnode",),
    description="Pin node that exposes one input port on its parent subnode shell.",
    keywords=("subnode", "input", "pin"),
    ports=(
        out_port(
            SUBNODE_PIN_PORT_KEY,
            kind="data",
            data_type=GRAPH_DATA_TYPE_ID,
            description="Carries the parent subnode input value into the nested graph.",
        ),
    ),
    properties=(
        prop_str(SUBNODE_PIN_LABEL_PROPERTY, "Input", "Label"),
        prop_enum(
            SUBNODE_PIN_KIND_PROPERTY,
            "data",
            "Kind",
            values=SUBNODE_PIN_KIND_VALUES,
        ),
        prop_str(SUBNODE_PIN_DATA_TYPE_PROPERTY, GRAPH_DATA_TYPE_ID, "Data Type"),
        PropertySpec(
            SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY,
            "json",
            [],
            "Accepted Data Types",
            inspector_visible=False,
        ),
        PropertySpec(
            SUBNODE_PIN_DATA_ACCESS_PROPERTY,
            "enum",
            "item",
            "Data Access",
            enum_values=SUBNODE_PIN_DATA_ACCESS_VALUES,
            inspector_visible=False,
        ),
    ),
    runtime_behavior="compile_only",
)
class SubnodeInputNodePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


@builtin_node_type(
    type_id=SUBNODE_OUTPUT_TYPE_ID,
    display_name="Subnode Output",
    category_path=("Subnode",),
    description="Pin node that exposes one output port on its parent subnode shell.",
    keywords=("subnode", "output", "pin"),
    ports=(
        in_port(
            SUBNODE_PIN_PORT_KEY,
            kind="data",
            data_type=GRAPH_DATA_TYPE_ID,
            description="Carries a nested graph value to the parent subnode output.",
        ),
    ),
    properties=(
        prop_str(SUBNODE_PIN_LABEL_PROPERTY, "Output", "Label"),
        prop_enum(
            SUBNODE_PIN_KIND_PROPERTY,
            "data",
            "Kind",
            values=SUBNODE_PIN_KIND_VALUES,
        ),
        prop_str(SUBNODE_PIN_DATA_TYPE_PROPERTY, GRAPH_DATA_TYPE_ID, "Data Type"),
        PropertySpec(
            SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY,
            "json",
            [],
            "Accepted Data Types",
            inspector_visible=False,
        ),
        PropertySpec(
            SUBNODE_PIN_DATA_ACCESS_PROPERTY,
            "enum",
            "item",
            "Data Access",
            enum_values=SUBNODE_PIN_DATA_ACCESS_VALUES,
            inspector_visible=False,
        ),
    ),
    runtime_behavior="compile_only",
)
class SubnodeOutputNodePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


SUBNODE_NODE_DESCRIPTORS = (
    plugin_descriptor(SubnodeNodePlugin),
    plugin_descriptor(SubnodeInputNodePlugin),
    plugin_descriptor(SubnodeOutputNodePlugin),
)


__all__ = [
    "SUBNODE_AUTHORING_TYPE_IDS",
    "SUBNODE_PIN_DATA_TYPE_PROPERTY",
    "SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY",
    "SUBNODE_PIN_DATA_ACCESS_PROPERTY",
    "SUBNODE_PIN_DATA_ACCESS_VALUES",
    "SUBNODE_PIN_TYPE_IDS",
    "SUBNODE_PIN_KIND_PROPERTY",
    "SUBNODE_PIN_KIND_VALUES",
    "SUBNODE_PIN_LABEL_PROPERTY",
    "SUBNODE_PIN_PORT_KEY",
    "SUBNODE_INPUT_TYPE_ID",
    "SUBNODE_OUTPUT_TYPE_ID",
    "SUBNODE_TYPE_ID",
    "SUBNODE_NODE_DESCRIPTORS",
    "SubnodePinDefinition",
    "SubnodeInputNodePlugin",
    "SubnodeNodePlugin",
    "SubnodeOutputNodePlugin",
    "default_subnode_pin_label",
    "is_subnode_authoring_type",
    "is_subnode_input_type",
    "is_subnode_output_type",
    "is_subnode_pin_type",
    "is_subnode_shell_type",
    "normalize_subnode_pin_data_type",
    "normalize_subnode_pin_accepted_data_types",
    "normalize_subnode_pin_data_access",
    "normalize_subnode_pin_kind",
    "resolve_subnode_pin_definition",
]
