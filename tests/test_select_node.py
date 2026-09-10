from __future__ import annotations

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.data_control import (
    NUMBER_SLIDER_PILL_HEIGHT,
    SELECT_TYPE_ID,
    execute_select,
)
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import STRING_DATA_TYPE_ID, DataTree
from ea_node_editor.ui_qml.graph_surface_metrics import (
    node_surface_metrics,
    resolved_node_surface_size,
)
from ea_node_editor.ui_qml.surface_contracts import surface_spec_for_node_type


class _Ctx:
    def __init__(self, properties):
        self.properties = properties


def _node(registry, **property_overrides) -> NodeInstance:
    properties = registry.default_properties(SELECT_TYPE_ID)
    properties.update(property_overrides)
    return NodeInstance(
        node_id="select-1",
        type_id=SELECT_TYPE_ID,
        title="Select",
        x=0.0,
        y=0.0,
        properties=properties,
    )


def test_select_contract_defaults_and_compact_surface() -> None:
    registry = build_builtin_registry()
    spec = registry.get_spec(SELECT_TYPE_ID)

    assert registry.python_function_ref_or_none(SELECT_TYPE_ID) is not None
    assert spec.display_name == "Select"
    assert spec.category_path == ("Data", "Control")
    assert spec.description == "A dropdown that allows to select a value from the list."
    assert spec.keywords == ("dropdown", "combobox", "option")
    assert spec.collapsible is False
    assert (spec.surface_family, spec.surface_variant) == ("standard", "select")
    assert len(spec.ports) == 1
    output = spec.ports[0]
    assert (
        output.key,
        output.label,
        output.direction,
        output.kind,
        output.data_type,
        output.data_access,
        output.exposed,
        output.description,
    ) == (
        "selected_value",
        "Selected value",
        "out",
        "data",
        STRING_DATA_TYPE_ID,
        "tree",
        True,
        "The value selected by the user.",
    )
    assert [(prop.key, prop.type, prop.inspector_visible) for prop in spec.properties] == [
        ("options", "json", False),
        ("selected_index", "int", False),
    ]
    assert registry.default_properties(SELECT_TYPE_ID) == {
        "options": [
            {"name": "Option A", "value": "0"},
            {"name": "Option B", "value": "1"},
        ],
        "selected_index": 0,
    }

    surface = surface_spec_for_node_type(type_id=SELECT_TYPE_ID, spec=spec)
    assert surface.qml_component == "passive/GraphSelectSurface.qml"
    payload = node_surface_metrics(_node(registry), spec).to_payload()
    assert payload["default_width"] == 280.0
    assert payload["default_height"] == NUMBER_SLIDER_PILL_HEIGHT
    assert payload["min_height"] == NUMBER_SLIDER_PILL_HEIGHT
    assert payload["header_height"] == 0.0
    assert payload["port_center_offset"] == NUMBER_SLIDER_PILL_HEIGHT / 2

    node = _node(registry)
    node.custom_width = 360.0
    node.custom_height = 200.0
    assert resolved_node_surface_size(node, spec) == (360.0, NUMBER_SLIDER_PILL_HEIGHT)


def test_select_normalization_and_runtime_keep_values_as_text() -> None:
    registry = build_builtin_registry()
    normalized = registry.normalize_properties(
        SELECT_TYPE_ID,
        {
            "options": [
                {"name": "First", "value": 7},
                "malformed",
                {"name": None, "value": None},
                {"name": "First", "value": 7},
            ],
            "selected_index": 99,
        },
    )
    assert normalized == {
        "options": [
            {"name": "First", "value": "7"},
            {"name": "", "value": ""},
            {"name": "First", "value": "7"},
        ],
        "selected_index": 2,
    }
    assert registry.normalize_properties(
        SELECT_TYPE_ID,
        {"options": [], "selected_index": -5},
    ) == {
        "options": [
            {"name": "Option A", "value": "0"},
            {"name": "Option B", "value": "1"},
        ],
        "selected_index": 0,
    }

    assert execute_select(_Ctx({})).outputs == {
        "selected_value": DataTree.from_item("0")
    }
    result = execute_select(_Ctx(normalized))
    assert result.outputs == {"selected_value": DataTree.from_item("7")}
    assert isinstance(result.outputs["selected_value"][(0,)][0], str)


def test_select_options_and_selection_round_trip_in_project_document() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    options = [
        {"name": "Small", "value": "0.5"},
        {"name": "Medium", "value": "1"},
        {"name": "Large", "value": "2"},
    ]
    node = model.add_node(
        workspace.workspace_id,
        SELECT_TYPE_ID,
        "Radius",
        20.0,
        40.0,
        properties={"options": options, "selected_index": 1},
    )
    serializer = JsonProjectSerializer(registry)
    loaded = serializer.from_document(serializer.to_document(model.project))
    restored = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]

    assert restored.properties["options"] == options
    assert restored.properties["selected_index"] == 1
