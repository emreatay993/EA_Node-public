from __future__ import annotations

from types import SimpleNamespace

import pytest

from ea_node_editor.runtime_contracts.settled_results import (
    RootExecutionError,
    SettledPortResult,
)
from ea_node_editor.execution.worker_runner import NodeExecutor
from ea_node_editor.graph.effective_ports import effective_ports
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.record_payloads import node_instance_from_mapping, node_instance_to_mapping
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.graph.type_forwarding import ResolvedSourceContract
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.runtime_contracts import (
    GRAPH_DATA_TYPE_ID,
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    DataTree,
    Interval1D,
)


def _input_result(
    value: object,
    *,
    data_access: str = "item",
    modifiers: tuple[str, ...] = (),
    incoming: SettledPortResult | None = None,
    data_type: str = GRAPH_DATA_TYPE_ID,
) -> SettledPortResult:
    edge = SimpleNamespace(source_node_id="source", source_port_key="result")
    plan = SimpleNamespace(
        nodes={
            "target": SimpleNamespace(
                type_id="tests.default_target",
                port_modifiers={"value": modifiers},
            )
        },
        ports_by_key={
            "source": {
                "result": SimpleNamespace(
                    data_type=data_type,
                    accepted_data_types=(),
                )
            }
        },
        incoming_edges_for=lambda _node_id, _port_key: [] if incoming is None else [edge],
        source_contracts={
            ("source", "result"): ResolvedSourceContract((data_type,)),
        },
    )
    executor = NodeExecutor.__new__(NodeExecutor)
    executor._plan = plan
    executor._data_types = build_default_registry().data_types
    executor.node_outputs = (
        {} if incoming is None else {"source": {"result": incoming}}
    )
    port = SimpleNamespace(
        key="value",
        data_access=data_access,
        data_type=data_type,
        accepted_data_types=(),
        uses_property_default=True,
    )
    return executor._input_result("target", port, {"value": value})


def test_registered_default_port_opt_in_is_explicit() -> None:
    registry = build_default_registry()
    spec = registry.get_spec("core.logger")
    node = NodeInstance("node", spec.type_id, spec.display_name, 0.0, 0.0)
    ports = {
        port.key: port
        for port in effective_ports(node=node, spec=spec, workspace_nodes={node.node_id: node})
    }

    assert ports["message"].uses_property_default is True


@pytest.mark.parametrize("value", [0, 0.0, False, "", None])
def test_falsey_item_defaults_are_values(value: object) -> None:
    result = _input_result(value)

    assert result == SettledPortResult(status="value", value=DataTree.from_item(value))


def test_list_tree_and_modifiers_share_the_existing_datatree_path() -> None:
    list_result = _input_result([None, 1], data_access="list", modifiers=("clean",))
    tree = DataTree((((2, 0), ("a", "b")),))
    tree_result = _input_result(tree, data_access="tree")

    assert list_result == SettledPortResult(
        status="value",
        value=DataTree((((0,), (1,)),)),
    )
    assert tree_result == SettledPortResult(status="value", value=tree)


def test_enabled_incoming_empty_failure_and_none_override_the_default() -> None:
    empty = _input_result("fallback", incoming=SettledPortResult(status="empty"))
    failed = _input_result(
        "fallback",
        incoming=SettledPortResult(
            status="failed",
            errors=(RootExecutionError(node_id="source", error="boom", traceback=""),),
        ),
    )
    none_value = _input_result(
        "fallback",
        incoming=SettledPortResult(status="value", value=DataTree.from_item(None)),
    )

    assert empty.status == "empty"
    assert failed == SettledPortResult(
        status="failed",
        errors=(RootExecutionError(node_id="source", error="boom", traceback=""),),
    )
    assert none_value == SettledPortResult(status="value", value=DataTree.from_item(None))


def test_enabled_interval_input_preserves_upstream_and_authored_endpoint_order() -> None:
    authored = Interval1D(10.0, 0.0)
    upstream = Interval1D(-2.0, 5.0)

    result = _input_result(
        authored,
        data_type=INTERVAL_1D_GRAPH_DATA_TYPE_ID,
        incoming=SettledPortResult(
            status="value", value=DataTree.from_item(upstream)
        ),
    )

    assert result == SettledPortResult(
        status="value", value=DataTree.from_item(Interval1D(-2.0, 5.0))
    )
    assert authored == Interval1D(10.0, 0.0)


def test_property_edit_preserves_connected_edge_and_disconnect_restores_default() -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    source = mutations.add_node(type_id="core.constant", title="Constant", x=0.0, y=0.0)
    target = mutations.add_node(type_id="core.logger", title="Logger", x=200.0, y=0.0)
    edge = mutations.add_edge(
        source_node_id=source.node_id,
        source_port_key="as_text",
        target_node_id=target.node_id,
        target_port_key="message",
    )

    mutations.set_node_property(target.node_id, "message", "saved default")

    assert edge.edge_id in workspace.edges
    assert target.properties["message"] == "saved default"
    mutations.move_edge_endpoint(edge.edge_id, "target", "", "")
    assert workspace.edges == {}
    assert target.properties["message"] == "saved default"


def test_stale_locked_ports_are_ignored_and_never_written() -> None:
    restored = node_instance_from_mapping(
        {
            "node_id": "node",
            "type_id": "core.logger",
            "title": "Logger",
            "x": 0,
            "y": 0,
            "locked_ports": "obsolete",
        },
        strict_payload=True,
    )

    assert restored is not None
    assert "locked_ports" not in node_instance_to_mapping(restored)
