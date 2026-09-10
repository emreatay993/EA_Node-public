from __future__ import annotations

from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.core import (
    TRIGGER_DEFAULT_WIDTH,
    TRIGGER_MIN_WIDTH,
    TRIGGER_TYPE_ID,
    TriggerNodePlugin,
)
from ea_node_editor.nodes.builtins.data_control import NUMBER_SLIDER_PILL_HEIGHT
from ea_node_editor.runtime_contracts import GRAPH_DATA_TYPE_ID
from ea_node_editor.ui_qml.graph_surface_metrics import (
    node_surface_metrics,
    resolved_node_surface_size,
)
from ea_node_editor.ui_qml.surface_contracts import surface_spec_for_node_type


def _node(registry) -> NodeInstance:
    return NodeInstance(
        node_id="trigger-1",
        type_id=TRIGGER_TYPE_ID,
        title="Trigger",
        x=0.0,
        y=0.0,
        properties=registry.default_properties(TRIGGER_TYPE_ID),
    )


def test_trigger_contract_copy_and_compact_surface() -> None:
    registry = build_builtin_registry()
    spec = registry.get_spec(TRIGGER_TYPE_ID)

    assert registry.create(TRIGGER_TYPE_ID).__class__ is TriggerNodePlugin
    assert spec.display_name == "Trigger"
    assert spec.category_path == ("Data", "Control")
    assert spec.description == (
        "Stop downstream nodes from running until you click the button."
    )
    assert spec.keywords == ("button", "action", "run", "dam", "gate", "block")
    assert spec.collapsible is False
    assert (spec.surface_family, spec.surface_variant) == ("standard", "trigger")
    assert spec.properties == ()

    ports = {port.key: port for port in spec.ports}
    assert len(spec.ports) == 2
    node_input = ports["input"]
    assert (
        node_input.label,
        node_input.direction,
        node_input.kind,
        node_input.data_type,
        node_input.data_access,
        node_input.required,
        node_input.description,
    ) == (
        "Input",
        "in",
        "data",
        GRAPH_DATA_TYPE_ID,
        "tree",
        False,
        "The data that is blocked until you click the button.",
    )
    node_output = ports["output"]
    assert (
        node_output.label,
        node_output.direction,
        node_output.kind,
        node_output.data_type,
        node_output.data_access,
        node_output.description,
    ) == (
        "Output",
        "out",
        "data",
        GRAPH_DATA_TYPE_ID,
        "tree",
        "The current output. The output is not updated until you click the button.",
    )

    surface = surface_spec_for_node_type(type_id=TRIGGER_TYPE_ID, spec=spec)
    assert surface.qml_component == "passive/GraphTriggerSurface.qml"
    assert (surface.family, surface.variant) == ("standard", "trigger")

    payload = node_surface_metrics(_node(registry), spec).to_payload()
    assert payload["default_width"] == TRIGGER_DEFAULT_WIDTH
    assert payload["min_width"] == TRIGGER_MIN_WIDTH
    assert payload["default_height"] == NUMBER_SLIDER_PILL_HEIGHT
    assert payload["min_height"] == NUMBER_SLIDER_PILL_HEIGHT
    assert payload["header_height"] == 0.0
    assert payload["port_center_offset"] == NUMBER_SLIDER_PILL_HEIGHT / 2


def test_trigger_pill_size_is_height_locked_and_width_clamped() -> None:
    registry = build_builtin_registry()
    spec = registry.get_spec(TRIGGER_TYPE_ID)

    node = _node(registry)
    assert resolved_node_surface_size(node, spec) == (
        TRIGGER_DEFAULT_WIDTH,
        NUMBER_SLIDER_PILL_HEIGHT,
    )

    node.custom_width = 360.0
    node.custom_height = 200.0
    assert resolved_node_surface_size(node, spec) == (360.0, NUMBER_SLIDER_PILL_HEIGHT)

    node.custom_width = 60.0
    assert resolved_node_surface_size(node, spec) == (
        TRIGGER_MIN_WIDTH,
        NUMBER_SLIDER_PILL_HEIGHT,
    )
