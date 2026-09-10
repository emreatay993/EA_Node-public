from __future__ import annotations

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.data_control import (
    BOOLEAN_TOGGLE_TYPE_ID,
    execute_boolean_toggle,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import BOOLEAN_DATA_TYPE_ID, DataTree
from ea_node_editor.ui.support.node_presentation import build_inline_property_items
from ea_node_editor.ui_qml.graph_surface_metrics import (
    node_surface_metrics,
    resolved_node_surface_size,
)
from ea_node_editor.ui_qml.surface_contracts import surface_spec_for_node_type


def _context(value: bool) -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="toggle",
        workspace_id="workspace",
        inputs={},
        properties={"value": value},
        emit_log=lambda _level, _message: None,
    )


def test_boolean_toggle_contract_and_runtime() -> None:
    registry = build_builtin_registry()
    spec = registry.get_spec(BOOLEAN_TOGGLE_TYPE_ID)
    port = spec.ports[0]
    prop = spec.properties[0]

    assert spec.display_name == "Boolean Toggle"
    assert spec.category_path == ("Data", "Control")
    assert spec.description == "Boolean (true/false) toggle."
    assert spec.keywords == ("switch",)
    assert spec.collapsible is False
    assert (spec.surface_family, spec.surface_variant) == ("standard", "boolean_toggle")
    assert (port.key, port.direction, port.kind, port.data_type, port.data_access) == (
        "boolean",
        "out",
        "data",
        BOOLEAN_DATA_TYPE_ID,
        "tree",
    )
    assert (prop.key, prop.type, prop.default, prop.inline_editor, prop.inspector_editor) == (
        "value",
        "bool",
        False,
        "toggle",
        "toggle",
    )
    assert execute_boolean_toggle(_context(False)).outputs == {
        "boolean": DataTree.from_item(False)
    }
    assert execute_boolean_toggle(_context(True)).outputs == {
        "boolean": DataTree.from_item(True)
    }


def test_boolean_toggle_uses_compact_surface_and_persists_value() -> None:
    registry = build_builtin_registry()
    spec = registry.get_spec(BOOLEAN_TOGGLE_TYPE_ID)
    node = NodeInstance(
        node_id="toggle",
        type_id=BOOLEAN_TOGGLE_TYPE_ID,
        title="Boolean Toggle",
        x=0.0,
        y=0.0,
        properties={"value": True},
    )
    metrics = node_surface_metrics(node, spec).to_payload()
    surface = surface_spec_for_node_type(type_id=BOOLEAN_TOGGLE_TYPE_ID, spec=spec)

    assert (metrics["default_width"], metrics["default_height"]) == (280.0, 40.0)
    assert metrics["port_center_offset"] == 20.0
    assert metrics["use_host_chrome"] is True
    node.custom_width = 400.0
    node.custom_height = 300.0
    assert resolved_node_surface_size(node, spec) == (400.0, 40.0)
    assert surface.qml_component == "passive/GraphBooleanToggleSurface.qml"

    inline_items = build_inline_property_items(
        node=node,
        spec=spec,
        workspace_nodes={node.node_id: node},
    )
    assert [(item["key"], item["value"], item["inline_editor"]) for item in inline_items] == [
        ("value", True, "toggle")
    ]

    model = GraphModel()
    workspace = model.active_workspace
    saved = model.add_node(
        workspace.workspace_id,
        BOOLEAN_TOGGLE_TYPE_ID,
        "Boolean Toggle",
        0.0,
        0.0,
        properties={"value": True},
    )
    serializer = JsonProjectSerializer(registry)
    loaded = serializer.from_document(serializer.to_persistent_document(model.project))
    assert loaded.workspaces[workspace.workspace_id].nodes[saved.node_id].properties["value"] is True
