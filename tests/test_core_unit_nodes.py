from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtin_functions.unit_math import SOURCE
from ea_node_editor.nodes.builtins.core_media import (
    CELL_DATA_TYPE_ID,
    DATETIME_DATA_TYPE_ID,
    INTERVAL_2D_DATA_TYPE_ID,
    TENSOR_DATA_TYPE_ID,
)
from ea_node_editor.nodes.builtins.tree_path import (
    TREE_PATH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.builtins.units import (
    LENGTH_DATA_TYPE_ID,
    UNIT_SYSTEM_DATA_TYPE_ID,
    UNIT_SYSTEM_DERIVED_UNIT_ENUMS,
    UNIT_SYSTEM_IDENTIFIERS,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import (
    INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    PythonFunctionAdapter,
)
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.registry import PythonFunctionEntry
from ea_node_editor.runtime_contracts import Interval1D, TypedInlineValue
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog

CONSTRUCT_PATH_TYPE_ID = "data.construct_path"
DECONSTRUCT_PATH_TYPE_ID = "data.deconstruct_path"
DECONSTRUCT_DATE_TIME_TYPE_ID = "utilities.deconstruct_date_time"
DECONSTRUCT_TENSOR_TYPE_ID = "math.deconstruct_tensor"
EXCEL_CELL_TYPE_ID = "data.excel_cell"
DECONSTRUCT_INTERVAL_2D_TYPE_ID = "math.deconstruct_interval_2d"
PHYSICAL_QUANTITY_CONTAINER_TYPE_ID = "math.physical_quantity_container"
UNIT_SYSTEM_CONTAINER_TYPE_ID = "math.unit_system_container"


_DECLARATIONS = {
    declaration.spec.type_id: declaration
    for declaration in discover_plugin_declarations(
        SOURCE,
        filename="unit_math.py",
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
}
_FUNCTIONS: dict[str, object] = {"__name__": "tests.unit_math_functions"}
exec(compile(SOURCE, "unit_math.py", "exec"), _FUNCTIONS)  # noqa: S102
_TYPE_IDS = (
    CONSTRUCT_PATH_TYPE_ID,
    DECONSTRUCT_PATH_TYPE_ID,
    DECONSTRUCT_DATE_TIME_TYPE_ID,
    DECONSTRUCT_TENSOR_TYPE_ID,
    EXCEL_CELL_TYPE_ID,
    DECONSTRUCT_INTERVAL_2D_TYPE_ID,
    PHYSICAL_QUANTITY_CONTAINER_TYPE_ID,
    UNIT_SYSTEM_CONTAINER_TYPE_ID,
)


def _context(inputs: dict[str, object]) -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="node",
        workspace_id="workspace",
        inputs=inputs,
        properties={},
        emit_log=lambda _level, _message: None,
    )


def _plugin(type_id: str):
    declaration = _DECLARATIONS[type_id]
    return PythonFunctionAdapter(
        declaration.spec,
        _FUNCTIONS[declaration.function_name],  # type: ignore[arg-type]
    )


def test_specs_match_golden_and_use_function_entries(tmp_path: Path) -> None:
    expected = {
        item["spec"]["type_id"]: item["spec"]
        for item in load_current_repo_owned_catalog()
    }
    registry = build_builtin_registry(generation_root=tmp_path / "generations")

    for type_id in _TYPE_IDS:
        assert json.loads(json.dumps(asdict(registry.get_spec(type_id)))) == expected[type_id]
        assert isinstance(registry.get_entry(type_id), PythonFunctionEntry)
        assert registry.descriptor_or_none(type_id) is None






def test_path_date_tensor_and_interval_execution() -> None:
    path = (
        _plugin(CONSTRUCT_PATH_TYPE_ID)
        .execute(_context({"indices": [3, -2, 0]}))
        .outputs["path"]
    )
    assert type(path) is TypedInlineValue
    assert path.data_type_id == TREE_PATH_DATA_TYPE_ID
    assert _plugin(DECONSTRUCT_PATH_TYPE_ID).execute(
        _context({"path": path})
    ).outputs == {"indices": [3, -2, 0]}

    date_value = TypedInlineValue(
        DATETIME_DATA_TYPE_ID,
        1,
        {
            "year": 2026,
            "month": 7,
            "day": 29,
            "hour": 12,
            "minute": 34,
            "second": 56,
            "millisecond": 789,
            "kind": "Utc",
        },
    )
    assert _plugin(DECONSTRUCT_DATE_TIME_TYPE_ID).execute(
        _context({"date_and_time": date_value})
    ).outputs == {
        "year": 2026,
        "month": 7,
        "day": 29,
        "hour": 12,
        "minute": 34,
        "second": 56,
        "millisecond": 789,
    }

    tensor_payload = {"data": [1.0, 2.0, 3.0, 4.0], "dimensions": [2, 2]}
    tensor_result = _plugin(DECONSTRUCT_TENSOR_TYPE_ID).execute(
        _context({"tensor": TypedInlineValue(TENSOR_DATA_TYPE_ID, 1, tensor_payload)})
    )
    assert tensor_result.outputs == {
        "data": [1.0, 2.0, 3.0, 4.0],
        "dimensions": [2, 2],
    }
    assert tensor_result.outputs["data"] is not tensor_payload["data"]
    assert tensor_result.outputs["dimensions"] is not tensor_payload["dimensions"]

    interval_result = _plugin(DECONSTRUCT_INTERVAL_2D_TYPE_ID).execute(
        _context(
            {
                "interval": TypedInlineValue(
                    INTERVAL_2D_DATA_TYPE_ID,
                    1,
                    {
                        "u": {"start": -1.0, "end": 2.0},
                        "v": {"start": 3.0, "end": 4.5},
                    },
                )
            }
        )
    )
    assert interval_result.outputs == {
        "u": Interval1D(-1.0, 2.0),
        "v": Interval1D(3.0, 4.5),
    }


@pytest.mark.parametrize(
    ("column", "expected"),
    (
        ("A", "A"),
        ("aa", "AA"),
        ("1", "A"),
        ("00026", "Z"),
        ("27", "AA"),
        ("2147483647", "FXSHRXW"),
        ("ZZZZZZZZ", "ZZZZZZZZ"),
    ),
)
def test_excel_cell_normalizes_proven_columns(column: str, expected: str) -> None:
    cell = (
        _plugin(EXCEL_CELL_TYPE_ID)
        .execute(_context({"column": column, "row": 2}))
        .outputs["cell"]
    )
    assert cell == TypedInlineValue(
        CELL_DATA_TYPE_ID,
        1,
        {"Column": expected, "Row": 2},
    )


@pytest.mark.parametrize(
    "column",
    (
        "",
        " ",
        "+1",
        "-1",
        "0",
        "1.0",
        "2147483648",
        "A1",
        "A B",
        "١",
    ),
)
def test_excel_cell_rejects_unproven_columns(column: object) -> None:
    with pytest.raises(ValueError):
        _plugin(EXCEL_CELL_TYPE_ID).execute(_context({"column": column, "row": 1}))


@pytest.mark.parametrize("row", (True, 0, -1, 2_147_483_648, 1.0, "1"))
def test_excel_cell_rejects_non_positive_int32_rows(row: object) -> None:
    with pytest.raises(ValueError):
        _plugin(EXCEL_CELL_TYPE_ID).execute(_context({"column": "A", "row": row}))


def test_excel_cell_rejects_hostile_subclasses_without_invoking_them() -> None:
    class HostileString(str):
        def __iter__(self):
            raise AssertionError("hostile string was iterated")

        def __eq__(self, _other: object) -> bool:
            raise AssertionError("hostile string was compared")

        def __hash__(self) -> int:
            raise AssertionError("hostile string was hashed")

    class HostileInt(int):
        def __eq__(self, _other: object) -> bool:
            raise AssertionError("hostile integer was compared")

    with pytest.raises(ValueError):
        _plugin(EXCEL_CELL_TYPE_ID).execute(
            _context({"column": HostileString("A"), "row": 1})
        )
    with pytest.raises(ValueError):
        _plugin(EXCEL_CELL_TYPE_ID).execute(
            _context({"column": "A", "row": HostileInt(1)})
        )


def _valid_unit_system() -> TypedInlineValue:
    return TypedInlineValue(
        UNIT_SYSTEM_DATA_TYPE_ID,
        1,
        {
            "identifier": sorted(UNIT_SYSTEM_IDENTIFIERS)[0],
            "derived_units": {
                name: sorted(unit_names)[0]
                for name, unit_names in UNIT_SYSTEM_DERIVED_UNIT_ENUMS.items()
            },
        },
    )


@pytest.mark.parametrize(
    "type_id",
    (PHYSICAL_QUANTITY_CONTAINER_TYPE_ID, UNIT_SYSTEM_CONTAINER_TYPE_ID),
)
def test_containers_distinguish_absent_from_explicit_none(type_id: str) -> None:
    plugin = _plugin(type_id)
    assert plugin.execute(_context({})).outputs == {}
    assert plugin.execute(_context({"input": None})).outputs == {"output": None}


def test_containers_validate_typed_values_and_preserve_identity() -> None:
    quantity = TypedInlineValue(
        LENGTH_DATA_TYPE_ID,
        1,
        {"value": 12.5, "unit": "Meter"},
    )
    quantity_result = _plugin(PHYSICAL_QUANTITY_CONTAINER_TYPE_ID).execute(
        _context({"input": quantity})
    )
    assert quantity_result.outputs["output"] is quantity

    unit_system = _valid_unit_system()
    system_result = _plugin(UNIT_SYSTEM_CONTAINER_TYPE_ID).execute(
        _context({"input": unit_system})
    )
    assert system_result.outputs["output"] is unit_system

    with pytest.raises(ValueError):
        _plugin(PHYSICAL_QUANTITY_CONTAINER_TYPE_ID).execute(
            _context({"input": TypedInlineValue(LENGTH_DATA_TYPE_ID, 2, {})})
        )
    with pytest.raises(ValueError):
        _plugin(UNIT_SYSTEM_CONTAINER_TYPE_ID).execute(
            _context({"input": TypedInlineValue(UNIT_SYSTEM_DATA_TYPE_ID, 2, {})})
        )


@pytest.mark.parametrize(
    ("type_id", "input_key", "value"),
    (
        (CONSTRUCT_PATH_TYPE_ID, "indices", [True]),
        (
            DECONSTRUCT_PATH_TYPE_ID,
            "path",
            TypedInlineValue(TREE_PATH_DATA_TYPE_ID, 2, {"indices": [0]}),
        ),
        (
            DECONSTRUCT_DATE_TIME_TYPE_ID,
            "date_and_time",
            TypedInlineValue(DATETIME_DATA_TYPE_ID, 2, {}),
        ),
        (
            DECONSTRUCT_TENSOR_TYPE_ID,
            "tensor",
            TypedInlineValue(TENSOR_DATA_TYPE_ID, 1, {"data": [], "dimensions": []}),
        ),
        (
            DECONSTRUCT_INTERVAL_2D_TYPE_ID,
            "interval",
            TypedInlineValue(INTERVAL_2D_DATA_TYPE_ID, 2, {}),
        ),
    ),
)
def test_direct_execution_rejects_invalid_carriers(
    type_id: str,
    input_key: str,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        _plugin(type_id).execute(_context({input_key: value}))
