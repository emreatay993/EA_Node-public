from __future__ import annotations

import pytest

from ea_node_editor.graph.boundary_adapters import resolve_node_type_size_override
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.data_control import (
    PANEL_DEFAULT_HEIGHT,
    PANEL_DEFAULT_WIDTH,
    PANEL_MIN_HEIGHT,
    PANEL_MIN_WIDTH,
    PANEL_MODE_DATA,
    PANEL_MODE_TEXT,
    PANEL_TYPE_ID,
    execute_panel,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.runtime_contracts import GRAPH_DATA_TYPE_ID, DataTree
from ea_node_editor.ui_qml.graph_surface_metrics import (
    node_surface_metrics,
    surface_port_local_point,
)


def _context(
    *,
    inputs: dict[str, object] | None = None,
    properties: dict[str, object] | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="panel",
        workspace_id="workspace",
        inputs=dict(inputs or {}),
        properties=dict(properties or {}),
        emit_log=lambda _level, _message: None,
    )


def test_panel_spec_defaults_and_two_dimension_size() -> None:
    registry = build_builtin_registry()
    spec = registry.get_spec(PANEL_TYPE_ID)
    ports = {port.key: port for port in spec.ports}

    assert spec.display_name == "Panel"
    assert spec.category_path == ("Data", "Control")
    assert spec.description == (
        "Enter text or branched data. Keep exact text, infer finite numbers automatically, "
        "or require numeric values. Connected input passes through unchanged."
    )
    assert spec.keywords == ('"', "text", "watch")
    assert spec.collapsible is False
    assert spec.surface_variant == "panel"
    assert (ports["input"].direction, ports["input"].data_type) == (
        "in",
        GRAPH_DATA_TYPE_ID,
    )
    assert ports["input"].required is False
    assert ports["input"].data_access == "tree"
    assert ports["input"].description == "The input value."
    assert (ports["output"].direction, ports["output"].data_type) == (
        "out",
        GRAPH_DATA_TYPE_ID,
    )
    assert ports["output"].data_access == "tree"
    assert ports["output"].description == "The output value."
    assert registry.default_properties(PANEL_TYPE_ID) == {
        "value": "",
        "mode": PANEL_MODE_TEXT,
        "font_size": 12,
        "alignment": 2,
        "auto_resize": True,
        "interpretation": "text",
    }

    node = NodeInstance("panel", PANEL_TYPE_ID, "Panel", 0.0, 0.0)
    metrics = node_surface_metrics(node, spec)
    assert metrics.port_height == 0.0
    assert metrics.port_center_offset == 20.0
    assert surface_port_local_point(node, spec, "input") == (0.0, 20.0)
    assert surface_port_local_point(node, spec, "output") == (280.0, 20.0)
    assert resolve_node_type_size_override(
        node,
        spec,
        base_width=240.0,
        base_height=160.0,
    ) == (PANEL_DEFAULT_WIDTH, PANEL_DEFAULT_HEIGHT)
    node.custom_width = 100.0
    node.custom_height = 20.0
    assert resolve_node_type_size_override(
        node,
        spec,
        base_width=100.0,
        base_height=20.0,
    ) == (PANEL_MIN_WIDTH, PANEL_MIN_HEIGHT)
    node.custom_width = 420.0
    node.custom_height = 260.0
    assert resolve_node_type_size_override(
        node,
        spec,
        base_width=420.0,
        base_height=260.0,
    ) == (420.0, 260.0)


def test_panel_text_mode_publishes_one_item_without_splitting_lines() -> None:
    result = execute_panel(
        _context(properties={"value": "first\nsecond", "mode": PANEL_MODE_TEXT})
    )
    assert result.outputs == {"output": DataTree.from_item("first\nsecond")}
    assert execute_panel(_context()).outputs == {
        "output": DataTree.from_item("")
    }


def test_panel_data_mode_builds_lists_and_tree_paths() -> None:
    result = execute_panel(
        _context(
            properties={
                "value": " root \n* 0;1\n child-a \nchild-b\n* 2\n leaf ",
                "mode": PANEL_MODE_DATA,
                "interpretation": "text",
            }
        )
    )
    assert result.outputs == {
        "output": DataTree(
            {
                (0,): (" root ",),
                (0, 1): (" child-a ", "child-b"),
                (2,): (" leaf ",),
            }
        )
    }


def test_panel_data_mode_keeps_an_authored_trailing_blank_item() -> None:
    result = execute_panel(
        _context(properties={"value": "first\n", "mode": PANEL_MODE_DATA})
    )
    assert result.outputs == {"output": DataTree.from_list(("first", ""))}


def test_panel_automatic_interpretation_is_opt_in_and_finite() -> None:
    value = "1\n-2\n3.5\n1e2\nnan\ninf\n2+3\ntrue"
    as_text = execute_panel(
        _context(
            properties={
                "value": value,
                "mode": PANEL_MODE_DATA,
                "interpretation": "text",
            }
        )
    )
    parsed = execute_panel(
        _context(
            properties={
                "value": value,
                "mode": PANEL_MODE_DATA,
                "interpretation": "auto",
            }
        )
    )

    assert as_text.outputs["output"] == DataTree.from_list(value.splitlines())
    assert parsed.outputs["output"] == DataTree.from_list(
        (1, -2, 3.5, 100.0, "nan", "inf", "2+3", "true")
    )


@pytest.mark.parametrize("value", ("*", "* nope", "* 0;;1"))
def test_panel_rejects_invalid_branch_syntax(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid Panel branch header"):
        execute_panel(
            _context(properties={"value": value, "mode": PANEL_MODE_DATA})
        )


def test_panel_passes_the_exact_incoming_tree_through() -> None:
    incoming = DataTree({(2, 1): (None, {"items": [1, 2]})})
    output = execute_panel(
        _context(
            inputs={"input": incoming},
            properties={"value": "ignored", "mode": PANEL_MODE_DATA, "interpretation": "number"},
        )
    ).outputs["output"]
    assert output is incoming


def test_panel_strict_numbers_preserve_branches_and_missing_samples() -> None:
    result = execute_panel(_context(properties={
        "value": "007\n 2.5 \n\n* 0;2\n-3\n1e3", "mode": PANEL_MODE_DATA,
        "interpretation": "number",
    }))
    assert result.outputs["output"] == DataTree({(0,): (7, 2.5, None), (0, 2): (-3, 1000.0)})


@pytest.mark.parametrize("invalid", ("NaN", "Infinity", "1e999", "1,25", "part-007", "true"))
def test_panel_strict_error_identifies_authored_line_and_branch(invalid: str) -> None:
    with pytest.raises(ValueError, match="line 3, branch 2;1:.*not a finite number.*Interpret values as"):
        execute_panel(_context(properties={
            "value": f"* 2;1\n12\n{invalid}", "mode": PANEL_MODE_DATA,
            "interpretation": "number",
        }))


@pytest.mark.parametrize("legacy,expected", ((False, "text"), (True, "auto")))
def test_panel_saved_legacy_interpretation_migrates_and_roundtrips(legacy: bool, expected: str) -> None:
    from ea_node_editor.graph.model import GraphModel
    from ea_node_editor.graph.fragment_payloads import (
        build_graph_fragment_payload, fragment_node_from_payload, normalize_graph_fragment_payload,
    )
    from ea_node_editor.persistence.serializer import JsonProjectSerializer

    registry = build_builtin_registry()
    serializer = JsonProjectSerializer(registry)
    model = GraphModel()
    workspace = model.active_workspace
    node = model.validated_mutations(workspace_id=workspace.workspace_id, registry=registry).add_node(
        type_id="data.panel", title="Panel", x=0, y=0,
        properties=registry.default_properties("data.panel"),
    )
    document = serializer.to_persistent_document(model.project)
    node_doc = document["workspaces"][0]["nodes"][0]
    node_doc["properties"].pop("interpretation")
    node_doc["properties"]["parse_numbers"] = legacy
    loaded = serializer.from_document(document)
    props = loaded.workspaces[workspace.workspace_id].nodes[node.node_id].properties
    assert props["interpretation"] == expected
    assert "parse_numbers" not in props
    saved = serializer.to_persistent_document(loaded)
    assert saved["workspaces"][0]["nodes"][0]["properties"]["interpretation"] == expected
    fragment_node = dict(node_doc, ref_id="panel")
    fragment = normalize_graph_fragment_payload(build_graph_fragment_payload(nodes=[fragment_node], edges=[]))
    assert fragment["nodes"][0]["properties"]["interpretation"] == expected
    assert "parse_numbers" not in fragment_node_from_payload(fragment_node).properties
    node_doc["properties"]["interpretation"] = "number"
    assert serializer.from_document(document).workspaces[workspace.workspace_id].nodes[node.node_id].properties["interpretation"] == "number"
