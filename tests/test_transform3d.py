from __future__ import annotations

import json
from functools import lru_cache

import pytest

from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtin_functions.spatial import SOURCE
from ea_node_editor.nodes.builtins.spatial_values import (
    TRANSFORM_3D_DATA_TYPE,
    TRANSFORM_3D_DATA_TYPE_FAMILY,
    TRANSFORM_3D_DATA_TYPE_ID,
    make_transform3d_value,
    transform3d_entries,
)
from ea_node_editor.nodes.core_data_types import (
    DOUBLE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import (
    INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    PythonFunctionAdapter,
)
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.runtime_contracts import (
    DataTree,
    DataTypeCatalogError,
    TypedInlineValue,
    deserialize_runtime_value,
    serialize_runtime_value,
)



_COLUMN_MAJOR = list(range(16))
_ROW_MAJOR_TRANSPOSE = [0, 4, 8, 12, 1, 5, 9, 13, 2, 6, 10, 14, 3, 7, 11, 15]
_registry = build_builtin_registry


class _ListSubclass(list):
    def __len__(self) -> int:
        raise AssertionError("hostile list was read")

    def __iter__(self):
        raise AssertionError("hostile list was read")


class _DictSubclass(dict):
    def __len__(self) -> int:
        raise AssertionError("hostile dictionary was read")


class _InlineSubclass(TypedInlineValue):
    pass




def _context(
    *,
    inputs: dict[str, object],
    properties: dict[str, object] | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="node",
        workspace_id="workspace",
        inputs=inputs,
        properties={} if properties is None else properties,
        emit_log=lambda _level, _message: None,
    )


def _plugins() -> tuple[object, object]:
    adapters = _transform_function_adapters()
    return (
        adapters["geometry.construct_transform"],
        adapters["geometry.deconstruct_transform"],
    )


@lru_cache(maxsize=1)
def _transform_function_adapters() -> dict[str, PythonFunctionAdapter]:
    namespace: dict[str, object] = {}
    exec(compile(SOURCE, "spatial.py", "exec"), namespace)  # noqa: S102
    declarations = discover_plugin_declarations(
        SOURCE,
        filename="spatial.py",
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
    return {
        declaration.spec.type_id: PythonFunctionAdapter(
            declaration.spec,
            namespace[declaration.function_name],  # type: ignore[arg-type]
        )
        for declaration in declarations
        if declaration.spec.type_id
        in {"geometry.construct_transform", "geometry.deconstruct_transform"}
    }






















def test_transform3d_type_carrier_and_persistence_facts_are_exact() -> None:
    assert (
        TRANSFORM_3D_DATA_TYPE_FAMILY.family_id,
        TRANSFORM_3D_DATA_TYPE.family_id,
        TRANSFORM_3D_DATA_TYPE.type_id,
        TRANSFORM_3D_DATA_TYPE.parents,
        TRANSFORM_3D_DATA_TYPE.abstract,
        TRANSFORM_3D_DATA_TYPE.carriers,
        TRANSFORM_3D_DATA_TYPE.persistence,
        TRANSFORM_3D_DATA_TYPE.sensitivity,
        TRANSFORM_3D_DATA_TYPE.payload_schema_version,
        TRANSFORM_3D_DATA_TYPE.implementation_version,
    ) == (
        "geometry_value",
        "geometry_value",
        "COREX.DataTypes.Transform3D",
        (GRAPH_DATA_TYPE_ID,),
        False,
        frozenset({"inline"}),
        "inline",
        "normal",
        1,
        "1",
    )
    value = make_transform3d_value(_COLUMN_MAJOR)
    assert value == TypedInlineValue(
        TRANSFORM_3D_DATA_TYPE_ID,
        1,
        {"entries": _COLUMN_MAJOR},
    )
    assert transform3d_entries(value) == tuple(_COLUMN_MAJOR)

    registry = _registry()
    registry.data_types.validate_carrier(TRANSFORM_3D_DATA_TYPE_ID, value)
    with pytest.raises(DataTypeCatalogError, match="does not allow 'native'"):
        registry.data_types.validate_carrier(
            TRANSFORM_3D_DATA_TYPE_ID,
            {"entries": _COLUMN_MAJOR},
        )


def test_transform3d_direct_datatree_and_stdio_json_round_trip() -> None:
    registry = _registry()
    value = make_transform3d_value([index - 7.5 for index in range(16)])
    tree = DataTree(
        (
            ((0,), (value,)),
            ((3, -1), (value, value)),
        )
    )
    for candidate in (value, tree):
        wire = serialize_runtime_value(
            candidate,
            catalog=registry.data_types,
            declared_type_id=TRANSFORM_3D_DATA_TYPE_ID,
        )
        stdio = json.loads(json.dumps(wire, allow_nan=False))
        assert (
            deserialize_runtime_value(
                stdio,
                catalog=registry.data_types,
                declared_type_id=TRANSFORM_3D_DATA_TYPE_ID,
            )
            == candidate
        )


@pytest.mark.parametrize("order", (0, 1))
def test_construct_and_deconstruct_are_pure_inverses(order: int) -> None:
    construct, deconstruct = _plugins()
    constructed = construct.execute(
        _context(inputs={"entries": list(_COLUMN_MAJOR)}, properties={"order": order})
    ).outputs["transform"]
    expected_canonical = _COLUMN_MAJOR if order == 0 else _ROW_MAJOR_TRANSPOSE
    assert transform3d_entries(constructed) == tuple(expected_canonical)

    entries = deconstruct.execute(
        _context(inputs={"transform": constructed}, properties={"order": order})
    ).outputs["entries"]
    assert entries == _COLUMN_MAJOR
    assert type(entries) is list


def test_order_input_overrides_local_property_default_without_fresh_node_claim() -> (
    None
):
    construct, deconstruct = _plugins()
    value = construct.execute(
        _context(
            inputs={"entries": list(_COLUMN_MAJOR), "order": 1},
            properties={"order": 0},
        )
    ).outputs["transform"]
    assert transform3d_entries(value) == tuple(_ROW_MAJOR_TRANSPOSE)
    assert (
        deconstruct.execute(
            _context(
                inputs={"transform": value, "order": 1},
                properties={"order": 0},
            )
        ).outputs["entries"]
        == _COLUMN_MAJOR
    )


@pytest.mark.parametrize(
    "entries",
    (
        [],
        list(range(15)),
        list(range(17)),
        [True, *range(1, 16)],
        ["0", *range(1, 16)],
        [float("nan"), *range(1, 16)],
        [float("inf"), *range(1, 16)],
        [10**10_000, *range(1, 16)],
        _ListSubclass(range(16)),
    ),
)
def test_construct_rejects_wrong_count_non_numbers_nonfinite_and_hostile_inputs(
    entries: object,
) -> None:
    construct, _deconstruct = _plugins()
    with pytest.raises(ValueError, match="Transform3D entries are invalid"):
        construct.execute(
            _context(inputs={"entries": entries}, properties={"order": 0})
        )


@pytest.mark.parametrize("order", (True, False, -1, 2, 0.0, "0", None))
def test_nodes_reject_nonexact_order_values(order: object) -> None:
    construct, deconstruct = _plugins()
    value = make_transform3d_value(_COLUMN_MAJOR)
    with pytest.raises(ValueError, match="order must be 0 or 1"):
        construct.execute(
            _context(
                inputs={"entries": list(_COLUMN_MAJOR)}, properties={"order": order}
            )
        )
    with pytest.raises(ValueError, match="order must be 0 or 1"):
        deconstruct.execute(
            _context(inputs={"transform": value}, properties={"order": order})
        )


@pytest.mark.parametrize(
    "value",
    (
        None,
        {"entries": list(range(16))},
        TypedInlineValue(DOUBLE_DATA_TYPE_ID, 1, {"entries": list(range(16))}),
        TypedInlineValue(TRANSFORM_3D_DATA_TYPE_ID, 2, {"entries": list(range(16))}),
        TypedInlineValue(TRANSFORM_3D_DATA_TYPE_ID, 1, {"entries": list(range(15))}),
        TypedInlineValue(
            TRANSFORM_3D_DATA_TYPE_ID,
            1,
            {"entries": [False, *range(1, 16)]},
        ),
        _InlineSubclass(
            TRANSFORM_3D_DATA_TYPE_ID,
            1,
            {"entries": list(range(16))},
        ),
    ),
)
def test_deconstruct_rejects_wrong_carrier_type_schema_and_payload(
    value: object,
) -> None:
    _construct, deconstruct = _plugins()
    with pytest.raises(ValueError, match="Transform3D value is invalid"):
        deconstruct.execute(
            _context(inputs={"transform": value}, properties={"order": 0})
        )


def test_transform_payload_validator_rejects_hostile_containers_without_reading_them() -> (
    None
):
    assert (
        TRANSFORM_3D_DATA_TYPE.validate_item(
            _DictSubclass({"entries": list(range(16))})
        )
        is False
    )
    assert (
        TRANSFORM_3D_DATA_TYPE.validate_item({"entries": _ListSubclass(range(16))})
        is False
    )
