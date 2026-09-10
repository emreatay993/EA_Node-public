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
        "Panel for the input of text that can be converted into other types "
        "automatically, such as integers, numbers and boolean values."
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
        "parse_numbers": False,
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
                "parse_numbers": False,
            }
        )
    )
    assert result.outputs == {
        "output": DataTree(
            {
                (0,): ("root",),
                (0, 1): ("child-a", "child-b"),
                (2,): ("leaf",),
            }
        )
    }


def test_panel_data_mode_keeps_an_authored_trailing_blank_item() -> None:
    result = execute_panel(
        _context(properties={"value": "first\n", "mode": PANEL_MODE_DATA})
    )
    assert result.outputs == {"output": DataTree.from_list(("first", ""))}


def test_panel_parse_numbers_is_opt_in_and_finite() -> None:
    value = "1\n-2\n3.5\n1e2\nnan\ninf\n2+3\ntrue"
    as_text = execute_panel(
        _context(
            properties={
                "value": value,
                "mode": PANEL_MODE_DATA,
                "parse_numbers": False,
            }
        )
    )
    parsed = execute_panel(
        _context(
            properties={
                "value": value,
                "mode": PANEL_MODE_DATA,
                "parse_numbers": True,
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
            properties={"value": "ignored", "mode": PANEL_MODE_DATA},
        )
    ).outputs["output"]
    assert output is incoming
