from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from ea_node_editor.common.payload_tools import INLINE_PAYLOAD_MAX_BYTES
from ea_node_editor.nodes.bootstrap import (
    build_builtin_registry,
)
from ea_node_editor.nodes.builtin_functions.reporting import (
    SOURCE as REPORTING_SOURCE,
)
from ea_node_editor.nodes.builtins.reporting import (
    FLOWCHART_NODE_DATA_TYPE_ID,
    MARKDOWN_FLOWCHART_NODE_TYPE_ID,
    MARKDOWN_FLOWCHART_TYPE_ID,
    is_flowchart_node_payload,
    make_flowchart_node_value,
    render_flowchart,
)
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.runtime_contracts import (
    TypedInlineValue,
    deserialize_runtime_value,
    serialize_runtime_value,
)
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog


def _plain_node(
    text: str = "Node",
    *,
    input_nodes: list[dict[str, object]] | None = None,
    shape: int = 0,
    link_type: int = 0,
    link_text: str = "",
) -> dict[str, object]:
    return {
        "text": text,
        "input_nodes": [] if input_nodes is None else input_nodes,
        "shape": shape,
        "link_type": link_type,
        "link_text": link_text,
    }


def test_reporting_function_specs_match_frozen_catalog() -> None:
    declarations = discover_plugin_declarations(
        REPORTING_SOURCE,
        filename="builtin_functions/reporting.py",
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
    ids = {MARKDOWN_FLOWCHART_NODE_TYPE_ID, MARKDOWN_FLOWCHART_TYPE_ID}
    golden = load_current_repo_owned_catalog()
    expected = {
        row["spec"]["type_id"]: row["spec"]
        for row in golden
        if row["spec"]["type_id"] in ids
    }

    assert {
        declaration.spec.type_id: json.loads(json.dumps(asdict(declaration.spec)))
        for declaration in declarations
    } == expected


@pytest.mark.parametrize(
    "payload",
    (
        {"text": "Node", "input_nodes": [], "shape": 0, "link_type": 0},
        {**_plain_node(), "extra": 1},
        {**_plain_node(), "text": 1},
        {**_plain_node(), "input_nodes": ()},
        {
            **_plain_node(),
            "input_nodes": [
                TypedInlineValue(FLOWCHART_NODE_DATA_TYPE_ID, 1, _plain_node())
            ],
        },
        {**_plain_node(), "shape": True},
        {**_plain_node(), "shape": 9},
        {**_plain_node(), "link_type": False},
        {**_plain_node(), "link_type": 4},
    ),
)
def test_payload_schema_rejects_missing_extra_and_nonexact_values(
    payload: object,
) -> None:
    assert not is_flowchart_node_payload(payload)


def test_recursive_payload_round_trip_and_shared_depth_size_guards() -> None:
    leaf = make_flowchart_node_value(text="Leaf")
    root = make_flowchart_node_value(
        text="Root",
        input_nodes=[leaf],
        shape=8,
        link_type=3,
        link_text="feeds",
    )
    catalog = build_builtin_registry().data_types
    encoded = serialize_runtime_value(
        root,
        catalog=catalog,
        declared_type_id=FLOWCHART_NODE_DATA_TYPE_ID,
    )
    restored = deserialize_runtime_value(
        encoded,
        catalog=catalog,
        declared_type_id=FLOWCHART_NODE_DATA_TYPE_ID,
    )
    assert restored == root
    assert restored.payload["input_nodes"] == [leaf.payload]

    cyclic = _plain_node()
    cyclic["input_nodes"].append(cyclic)
    assert not is_flowchart_node_payload(cyclic)

    accepted = _plain_node("depth-0")
    for depth in range(1, 40):
        candidate = _plain_node(f"depth-{depth}", input_nodes=[accepted])
        if not is_flowchart_node_payload(candidate):
            break
        accepted = candidate
    else:  # pragma: no cover - guards a changed shared depth policy
        raise AssertionError("shared JSON depth limit was not reached")
    assert is_flowchart_node_payload(accepted)
    assert not is_flowchart_node_payload(candidate)
    assert not is_flowchart_node_payload(
        _plain_node("x" * (INLINE_PAYLOAD_MAX_BYTES + 1))
    )


def test_execution_covers_all_shapes_links_directions_escaping_and_dedup() -> None:
    shaped = [
        make_flowchart_node_value(
            text=f"Node{shape}",
            shape=shape,
            link_type=0,
        )
        for shape in range(9)
    ]
    td = render_flowchart(shaped, 0)
    assert td.startswith("```mermaid\ngraph TD\n")
    assert td.endswith("\n```\n")
    for expected in (
        "Node0",
        "Node1(Node1)",
        "Node2([Node2])",
        "Node3[[Node3]]",
        "Node4[(Node4)]",
        "Node5((Node5))",
        "Node6>Node6]",
        "Node7{Node7}",
        "Node8{{Node8}}",
    ):
        assert f"    {expected}\n" in td

    child = make_flowchart_node_value(text="Input")
    linked = [
        make_flowchart_node_value(
            text=f"Output{link_type}",
            input_nodes=[child],
            link_type=link_type,
        )
        for link_type in range(4)
    ]
    lr = render_flowchart(linked, 1)
    assert lr.startswith("```mermaid\ngraph LR\n")
    for token, target in zip(("-->", "---", "-.->", "==>"), range(4), strict=True):
        assert f"Input {token} Output{target}" in lr

    escaped_parent = make_flowchart_node_value(
        text='A | "B" <C> & D\nE',
        input_nodes=[make_flowchart_node_value(text="A-B")],
        link_text='x|"<&\ny',
    )
    collision = make_flowchart_node_value(text="A B")
    escaped = render_flowchart([escaped_parent, collision, escaped_parent], 0)
    assert (
        'A____B___C____D_E["A &#124; &quot;B&quot; &lt;C&gt; &amp; D<br/>E"]' in escaped
    )
    assert 'A_B_2["A B"]' in escaped
    assert "x&#124;&quot;&lt;&amp;<br/>y" in escaped
    assert escaped.count(" -->|") == 1

    with pytest.raises(ValueError, match="direction"):
        render_flowchart([], True)
    with pytest.raises(ValueError, match="shape"):
        make_flowchart_node_value(text="bad", shape=True, link_type=0)
