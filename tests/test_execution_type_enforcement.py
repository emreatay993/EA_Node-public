# Purpose: Prove worker-side semantic input preparation and output validation.
# Map: subsystems/execution.md
# Tests: tests/test_execution_type_enforcement.py

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ea_node_editor.runtime_contracts.settled_results import (
    RootExecutionError,
    SettledPortResult,
)
from ea_node_editor.execution.runtime_dto import RuntimeEdge
from ea_node_editor.execution.worker_runner import NodeExecutor
from ea_node_editor.nodes.node_specs import PortSpec
from ea_node_editor.runtime_contracts import (
    DataConversionSpec,
    DataTree,
    DataTypeCatalog,
    DataTypeFamilySpec,
    DataTypeSpec,
    TypedInlineValue,
)

_GRAPH = "Test.Graph"
_TEXT = "Test.Text"
_INTEGER = "Test.Integer"
_REAL = "Test.Real"
_TOKEN = "Test.Token"
_INLINE = "Test.Inline"


class _Plan:
    def __init__(
        self,
        *,
        nodes: dict[str, object],
        ports_by_key: dict[str, dict[str, PortSpec]],
        incoming: tuple[RuntimeEdge, ...] = (),
        outputs: tuple[PortSpec, ...] = (),
    ) -> None:
        self.nodes = nodes
        self.ports_by_key = ports_by_key
        self.source_contracts = {}
        self._incoming = incoming
        self._outputs = outputs

    def incoming_edges_for(
        self,
        node_id: str,
        port_key: str = "",
    ) -> tuple[RuntimeEdge, ...]:
        return tuple(
            edge
            for edge in self._incoming
            if edge.target_node_id == node_id
            and (not port_key or edge.target_port_key == port_key)
        )

    def output_ports(self, _node_id: str) -> tuple[PortSpec, ...]:
        return self._outputs


def _catalog(
    *,
    conversions: tuple[DataConversionSpec, ...] = (),
    integer_coercer=int,
) -> DataTypeCatalog:
    catalog = DataTypeCatalog()
    catalog.register_many(
        families=(DataTypeFamilySpec("test", "Test", "test", "test"),),
        types=(
            DataTypeSpec(
                _GRAPH,
                "Graph",
                "test",
                lambda _value: True,
                abstract=True,
            ),
            DataTypeSpec(
                _TEXT,
                "Text",
                "test",
                lambda value: isinstance(value, str),
                parents=(_GRAPH,),
            ),
            DataTypeSpec(
                _INTEGER,
                "Integer",
                "test",
                lambda value: isinstance(value, int) and not isinstance(value, bool),
                integer_coercer,
                parents=(_GRAPH,),
            ),
            DataTypeSpec(
                _REAL,
                "Real",
                "test",
                lambda value: isinstance(value, float),
                float,
                parents=(_GRAPH,),
            ),
            DataTypeSpec(
                _TOKEN,
                "Token",
                "test",
                lambda value: (
                    isinstance(value, tuple) and len(value) == 2 and value[0] == "token"
                ),
                parents=(_GRAPH,),
            ),
            DataTypeSpec(
                _INLINE,
                "Inline",
                "test",
                lambda value: (
                    type(value) is dict
                    and tuple(value) == ("value",)
                    and type(value["value"]) is int
                ),
                parents=(_GRAPH,),
                carriers=frozenset({"inline"}),
                persistence="inline",
            ),
        ),
        conversions=conversions,
        owner_id="tests.execution.types",
    )
    catalog.freeze()
    return catalog


def _port(
    key: str,
    data_type: str,
    *,
    direction: str = "in",
    accepted: tuple[str, ...] = (),
    data_access: str = "item",
    uses_property_default: bool = False,
) -> PortSpec:
    return PortSpec(
        key,
        direction,
        "data",
        data_type,
        required=False if direction == "in" else None,
        accepted_data_types=accepted,
        data_access=data_access,
        uses_property_default=uses_property_default,
    )


def _executor(
    catalog: DataTypeCatalog,
    plan: _Plan,
    *,
    node_outputs: dict[str, dict[str, SettledPortResult]] | None = None,
) -> NodeExecutor:
    executor = object.__new__(NodeExecutor)
    executor._data_types = catalog
    executor._plan = plan
    executor.node_outputs = node_outputs or {}
    return executor


def test_forwarded_conversion_rejects_retained_value_outside_inferred_type() -> None:
    calls = []
    catalog = _catalog(conversions=(DataConversionSpec(
        _INTEGER, _TOKEN, lambda value: calls.append(value) or ("token", value),
    ),))
    executor = _executor(catalog, _Plan(nodes={"sink": SimpleNamespace(type_id="tests.sink")}, ports_by_key={}))
    with pytest.raises(ValueError, match="catalog reason"):
        executor._prepare_wired_item("sink", _port("value", _TOKEN), _GRAPH, "old text",
                                    path=(), item_index=0, source_type_candidates=(_INTEGER,))
    assert calls == []


def test_forwarded_union_conversion_failure_does_not_try_an_unselected_converter() -> None:
    calls = []

    def fail(value):
        calls.append("selected")
        raise ValueError("selected converter failed")

    catalog = _catalog(conversions=(
        DataConversionSpec(_INTEGER, _TOKEN, fail),
        DataConversionSpec(_INTEGER, _TEXT, lambda value: calls.append("alternative") or str(value)),
    ))
    executor = _executor(catalog, _Plan(nodes={"sink": SimpleNamespace(type_id="tests.sink")}, ports_by_key={}))
    with pytest.raises(ValueError, match="selected converter failed"):
        executor._prepare_wired_item("sink", _port("value", _TOKEN, accepted=(_TEXT,)), _GRAPH, 42,
                                    path=(), item_index=0, source_type_candidates=(_INTEGER,))
    assert calls == ["selected"]


def test_forwarded_conversion_validates_the_converted_carrier() -> None:
    catalog = _catalog(conversions=(DataConversionSpec(_INTEGER, _INLINE, lambda value: {"value": value}),))
    executor = _executor(catalog, _Plan(nodes={"sink": SimpleNamespace(type_id="tests.sink")}, ports_by_key={}))
    with pytest.raises(ValueError, match="native.*carriers"):
        executor._prepare_wired_item("sink", _port("value", _INLINE), _GRAPH, 42,
                                    path=(), item_index=0, source_type_candidates=(_INTEGER,))


def test_forwarded_abstract_source_conversion_has_direct_connection_parity() -> None:
    abstract = "Test.AbstractForwarded"
    catalog = _catalog().fork()
    catalog.register_many(types=(DataTypeSpec(
        abstract, "Abstract forwarded", "test", lambda value: type(value) is int,
        abstract=True, parents=(_GRAPH,),
    ),), conversions=(DataConversionSpec(abstract, _TOKEN, lambda value: ("token", value)),),
        owner_id="tests.abstract_forwarding")
    executor = _executor(catalog, _Plan(nodes={"sink": SimpleNamespace(type_id="tests.sink")}, ports_by_key={}))
    port = _port("value", _TOKEN)
    direct = executor._prepare_wired_item("sink", port, abstract, 42, path=(), item_index=0)
    forwarded = executor._prepare_wired_item("sink", port, _GRAPH, 42, path=(), item_index=0,
                                            source_type_candidates=(abstract,))
    assert direct == forwarded == ("token", 42)


def test_each_incoming_tree_is_converted_before_ordered_fan_in_and_modifiers() -> None:
    calls: list[str] = []
    catalog = _catalog(
        conversions=(
            DataConversionSpec(
                _TEXT,
                _INTEGER,
                lambda value: calls.append(value) or int(value),
            ),
        )
    )
    target = _port("values", _INTEGER)
    source_port = _port("value", _TEXT, direction="out")
    edges = (
        RuntimeEdge("source-a", "value", "sink", "values", input_order=0),
        RuntimeEdge("source-b", "value", "sink", "values", input_order=1),
    )
    plan = _Plan(
        nodes={
            "sink": SimpleNamespace(
                type_id="tests.typed_sink",
                port_modifiers={"values": ("reverse",)},
            )
        },
        ports_by_key={
            "source-a": {"value": source_port},
            "source-b": {"value": source_port},
        },
        incoming=edges,
    )
    executor = _executor(
        catalog,
        plan,
        node_outputs={
            "source-a": {
                "value": SettledPortResult(
                    status="value",
                    value=DataTree((((0,), ("2", "1")),)),
                )
            },
            "source-b": {
                "value": SettledPortResult(
                    status="value",
                    value=DataTree((((0,), ("3",)),)),
                )
            },
        },
    )

    result = executor._input_result("sink", target, {})

    assert result.status == "value"
    assert result.value == DataTree((((0,), (3, 1, 2)),))
    assert calls == ["2", "1", "3"]


def test_upstream_failure_wins_before_any_sibling_conversion() -> None:
    calls: list[str] = []
    catalog = _catalog(
        conversions=(
            DataConversionSpec(
                _TEXT,
                _INTEGER,
                lambda value: (
                    calls.append(value)
                    or (_ for _ in ()).throw(ValueError("must not run"))
                ),
            ),
        )
    )
    target = _port("values", _INTEGER)
    source_port = _port("value", _TEXT, direction="out")
    edges = (
        RuntimeEdge("value-source", "value", "sink", "values", input_order=0),
        RuntimeEdge("failed-source", "value", "sink", "values", input_order=1),
    )
    upstream_error = RootExecutionError(
        node_id="failed-source",
        error="upstream failed",
        traceback="trace",
    )
    plan = _Plan(
        nodes={
            "sink": SimpleNamespace(
                type_id="tests.typed_sink",
                port_modifiers={},
            )
        },
        ports_by_key={
            "value-source": {"value": source_port},
            "failed-source": {"value": source_port},
        },
        incoming=edges,
    )
    executor = _executor(
        catalog,
        plan,
        node_outputs={
            "value-source": {
                "value": SettledPortResult(
                    status="value",
                    value=DataTree.from_item("2"),
                )
            },
            "failed-source": {
                "value": SettledPortResult(
                    status="failed",
                    errors=(upstream_error,),
                )
            },
        },
    )

    result = executor._input_result("sink", target, {})

    assert result == SettledPortResult(
        status="failed",
        errors=(upstream_error,),
    )
    assert calls == []


def test_accepted_assignable_candidate_wins_over_primary_conversion() -> None:
    conversion_calls: list[str] = []
    catalog = _catalog(
        conversions=(
            DataConversionSpec(
                _TEXT,
                _INTEGER,
                lambda value: conversion_calls.append(value) or int(value),
            ),
        )
    )
    port = _port("value", _INTEGER, accepted=(_TEXT,))
    plan = _Plan(
        nodes={"sink": SimpleNamespace(type_id="tests.typed_sink", port_modifiers={})},
        ports_by_key={},
    )

    prepared = _executor(catalog, plan)._prepare_wired_item(
        "sink",
        port,
        _TEXT,
        "12",
        path=(3,),
        item_index=0,
    )

    assert prepared == "12"
    assert conversion_calls == []


def test_runtime_check_selects_a_candidate_per_item_in_a_heterogeneous_tree() -> None:
    catalog = _catalog()
    port = _port("value", _INTEGER, accepted=(_TEXT,), data_access="tree")
    source_port = _port("value", _GRAPH, direction="out")
    edge = RuntimeEdge("source", "value", "sink", "value")
    plan = _Plan(
        nodes={"sink": SimpleNamespace(type_id="tests.typed_sink", port_modifiers={})},
        ports_by_key={"source": {"value": source_port}},
    )
    tree = DataTree((((2, 4), (7, "word")),))

    prepared = _executor(catalog, plan)._prepare_wired_tree(
        "sink",
        port,
        edge,
        tree,
    )

    assert prepared == tree


def test_typed_inputs_never_chain_conversions_or_fall_through_after_failure() -> None:
    chained = _catalog(
        conversions=(
            DataConversionSpec(_TEXT, _INTEGER, int),
            DataConversionSpec(_INTEGER, _REAL, float),
        )
    )
    port = _port("value", _REAL)
    plan = _Plan(
        nodes={"sink": SimpleNamespace(type_id="tests.typed_sink", port_modifiers={})},
        ports_by_key={},
    )
    executor = _executor(chained, plan)
    with pytest.raises(ValueError, match="no_declared_relation"):
        executor._prepare_wired_item(
            "sink",
            port,
            _TEXT,
            "2",
            path=(0,),
            item_index=0,
        )

    calls: list[str] = []
    direct = _catalog(
        conversions=(
            DataConversionSpec(
                _TEXT,
                _INTEGER,
                lambda _value: (_ for _ in ()).throw(ValueError("first failed")),
            ),
            DataConversionSpec(
                _TEXT,
                _REAL,
                lambda value: calls.append(value) or float(value),
            ),
        )
    )
    port = _port("value", _INTEGER, accepted=(_REAL,))
    with pytest.raises(ValueError, match="first failed"):
        _executor(direct, plan)._prepare_wired_item(
            "sink",
            port,
            _TEXT,
            "2",
            path=(0,),
            item_index=0,
        )
    assert calls == []


def test_property_defaults_preserve_valid_candidates_coerce_invalid_values_and_keep_none() -> (
    None
):
    coercion_calls: list[object] = []
    catalog = _catalog(
        integer_coercer=lambda value: coercion_calls.append(value) or int(value)
    )
    plan = _Plan(
        nodes={
            "sink": SimpleNamespace(type_id="tests.default_sink", port_modifiers={})
        },
        ports_by_key={},
    )
    executor = _executor(catalog, plan)

    accepted = _port("value", _INTEGER, accepted=(_TEXT,))
    assert executor._prepare_untyped_tree(
        "sink",
        accepted,
        DataTree.from_item("kept"),
    ) == DataTree.from_item("kept")
    integer = _port("value", _INTEGER)
    assert executor._prepare_untyped_tree(
        "sink",
        integer,
        DataTree.from_item("4"),
    ) == DataTree.from_item(4)
    assert executor._prepare_untyped_tree(
        "sink",
        integer,
        DataTree.from_item(None),
    ) == DataTree.from_item(None)
    assert coercion_calls == ["4"]


def test_exact_typed_inline_property_default_reaches_input_unchanged() -> None:
    catalog = _catalog()
    plan = _Plan(
        nodes={
            "sink": SimpleNamespace(type_id="tests.default_sink", port_modifiers={})
        },
        ports_by_key={},
    )
    port = _port(
        "value",
        _INTEGER,
        accepted=(_INLINE,),
        uses_property_default=True,
    )
    default = TypedInlineValue(_INLINE, 1, {"value": 7})

    result = _executor(catalog, plan)._input_result(
        "sink",
        port,
        {"value": default},
    )

    assert result.status == "value"
    assert isinstance(result.value, DataTree)
    assert result.value.branches[0][1][0] is default


def test_wrong_typed_inline_property_default_identity_has_bounded_error() -> None:
    catalog = _catalog()
    plan = _Plan(
        nodes={
            "sink": SimpleNamespace(type_id="tests.default_sink", port_modifiers={})
        },
        ports_by_key={},
    )
    port = _port("value", _INLINE, uses_property_default=True)
    wrong_identity = TypedInlineValue(_TEXT, 1, {"value": 7})

    with pytest.raises(ValueError) as failure:
        _executor(catalog, plan)._input_result(
            "sink",
            port,
            {"value": wrong_identity},
        )

    message = str(failure.value)
    for expected in (
        "tests.default_sink",
        "sink",
        "value",
        _INLINE,
        _TEXT,
        "DataPath (0,)",
        "item index 0",
    ):
        assert expected in message


def test_input_errors_include_node_port_types_path_index_and_catalog_reason() -> None:
    catalog = _catalog(
        conversions=(
            DataConversionSpec(
                _TEXT,
                _INTEGER,
                lambda _value: (_ for _ in ()).throw(ValueError("bad integer")),
            ),
        )
    )
    port = _port("numbers", _INTEGER)
    plan = _Plan(
        nodes={"sink": SimpleNamespace(type_id="tests.error_sink", port_modifiers={})},
        ports_by_key={},
    )
    executor = _executor(catalog, plan)

    with pytest.raises(ValueError) as wired:
        executor._prepare_wired_item(
            "sink",
            port,
            _TEXT,
            "bad",
            path=(7, 2),
            item_index=3,
        )
    message = str(wired.value)
    for expected in (
        "tests.error_sink",
        "sink",
        "numbers",
        _INTEGER,
        _TEXT,
        "builtins.str",
        "(7, 2)",
        "item index 3",
        "bad integer",
    ):
        assert expected in message

    token_port = _port("token", _TOKEN)
    with pytest.raises(ValueError) as untyped:
        executor._prepare_untyped_tree(
            "sink",
            token_port,
            DataTree((((9,), ("bad",)),)),
        )
    default_message = str(untyped.value)
    assert "source semantic type 'untyped'" in default_message
    assert "no untyped coercer" in default_message
    assert "DataPath (9,)" in default_message


def test_outputs_are_validated_without_coercion_and_report_item_location() -> None:
    coercion_calls: list[object] = []
    catalog = _catalog(
        integer_coercer=lambda value: coercion_calls.append(value) or int(value)
    )
    port = _port("result", _INTEGER, direction="out", data_access="tree")
    plan = _Plan(
        nodes={
            "source": SimpleNamespace(
                type_id="tests.invalid_source",
                port_modifiers={},
            )
        },
        ports_by_key={},
        outputs=(port,),
    )
    executor = _executor(catalog, plan)

    with pytest.raises(ValueError) as error:
        executor._validate_outputs(
            "source",
            {"result": DataTree((((4, 2), (1, "5")),))},
            target_path=(0,),
        )

    assert coercion_calls == []
    message = str(error.value)
    for expected in (
        "tests.invalid_source",
        "source",
        "result",
        _INTEGER,
        "builtins.str",
        "DataPath (4, 2)",
        "item index 1",
        "output value is invalid",
    ):
        assert expected in message


def test_outputs_accept_deduplicated_primary_and_accepted_candidates_without_coercion() -> (
    None
):
    coercion_calls: list[object] = []
    catalog = _catalog(
        integer_coercer=lambda value: coercion_calls.append(value) or int(value)
    )
    port = _port(
        "result",
        _INTEGER,
        direction="out",
        accepted=(_INTEGER, _TEXT),
    )
    plan = _Plan(
        nodes={
            "source": SimpleNamespace(
                type_id="tests.union_source",
                port_modifiers={},
            )
        },
        ports_by_key={},
        outputs=(port,),
    )

    outputs = _executor(catalog, plan)._validate_outputs(
        "source",
        {"result": "kept"},
        target_path=(6,),
    )

    assert outputs["result"] == DataTree.from_item("kept", path=(6,))
    assert coercion_calls == []


def test_abstract_output_accepts_a_registered_concrete_descendant() -> None:
    catalog = _catalog()
    port = _port("result", _GRAPH, direction="out")
    plan = _Plan(
        nodes={
            "source": SimpleNamespace(
                type_id="tests.abstract_source",
                port_modifiers={},
            )
        },
        ports_by_key={},
        outputs=(port,),
    )

    outputs = _executor(catalog, plan)._validate_outputs(
        "source",
        {"result": 8},
        target_path=(5,),
    )

    assert outputs["result"] == DataTree.from_item(8, path=(5,))
