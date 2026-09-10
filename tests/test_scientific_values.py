# Purpose: Prove scientific snapshot ownership, bounded transport and native script interfaces.
# Map: subsystems/supporting_runtime_assets.md
# Tests: tests/test_scientific_values.py

from __future__ import annotations

from dataclasses import FrozenInstanceError
from collections import namedtuple
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.core import PythonScriptNodePlugin
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.runtime_contracts.data_tree import DataTree
from ea_node_editor.runtime_contracts.scientific_values import (
    ARRAY_VALUE_TYPE_ID,
    SERIES_VALUE_TYPE_ID,
    TABLE_VALUE_TYPE_ID,
    ArrayValue,
    TableValue,
    materialize_script_values,
    snapshot_scientific_value,
)
from ea_node_editor.runtime_contracts.value_codec import (
    deserialize_runtime_value,
    serialize_runtime_value,
)


@pytest.fixture(scope="module")
def catalog():
    return build_builtin_registry().data_types


def _roundtrip(value, catalog):
    return deserialize_runtime_value(
        serialize_runtime_value(value, catalog=catalog), catalog=catalog
    )


@pytest.mark.parametrize(
    "dtype",
    [
        "bool",
        "i1",
        "u2",
        ">i4",
        "i8",
        "f2",
        "f4",
        "f8",
        "c8",
        "c16",
        "datetime64[ns]",
        "timedelta64[ms]",
        "S5",
        "U5",
    ],
)
def test_array_roundtrip_preserves_dtype_shape_and_independent_writable_access(
    catalog, dtype
):
    source = np.asarray([[0, 1], [2, 3]], dtype=dtype)
    restored = _roundtrip(source, catalog)
    assert type(restored) is ArrayValue
    np.testing.assert_array_equal(restored.to_numpy(), source)
    assert restored.to_numpy().dtype == source.dtype
    assert not restored.to_numpy().flags.writeable
    with pytest.raises(ValueError):
        restored.to_numpy().flags.writeable = True
    writable = materialize_script_values(restored)
    assert writable.flags.writeable
    writable.flat[0] = writable.flat[-1]
    np.testing.assert_array_equal(restored.to_numpy(), source)


def test_array_snapshot_retains_no_mutable_alias_and_accepts_strided_sources(catalog):
    original = np.arange(20.0).reshape(4, 5)
    view = original[::2, ::-1]
    expected = view.copy()
    owned = snapshot_scientific_value(view)
    original[:] = -1
    np.testing.assert_array_equal(owned.to_numpy(), expected)
    assert (
        _roundtrip(np.asarray([np.nan, np.inf, -np.inf]), catalog).to_numpy()[1]
        == np.inf
    )
    assert _roundtrip(np.empty((0, 3)), catalog).shape == (0, 3)
    assert _roundtrip(np.asarray(3), catalog).shape == ()
    with pytest.raises(FrozenInstanceError):
        owned.buffer = b""


def test_pandas_dtype_index_labels_and_missing_roundtrip(catalog):
    source = pd.DataFrame(
        {
            "number": [1.5, np.nan, np.inf, -3.0],
            "nullable_int": pd.Series([1, None, 3, 4], dtype="Int64"),
            "nullable_float": pd.Series([1, None, 3, 4], dtype="Float32"),
            "nullable_bool": pd.Series([True, None, False, True], dtype="boolean"),
            "text": pd.Series(["x", None, "", pd.NA], dtype="string"),
            "object_text": pd.Series(["x", None, float("nan"), pd.NA], dtype=object),
            "complex": np.asarray([1j, 2j, 3j, 4j]),
            "utc_time": pd.date_range("2026-01-01", periods=4, tz="Europe/Istanbul"),
            "duration": pd.to_timedelta([1, 2, 3, 4], unit="s"),
        }
    )
    source.index = pd.Index(["a", "b", "c", "d"], name="row")
    source.columns.name = "signals"
    owned = _roundtrip(source, catalog)
    assert type(owned) is TableValue and owned.kind == "frame"
    pd.testing.assert_frame_equal(owned.to_pandas(), source)
    assert owned.column_names == tuple(source.columns)
    assert not owned.column_values(0).flags.writeable
    assert np.isnan(owned.column_values(1)[1])
    first, sibling = owned.to_pandas(), owned.to_pandas()
    first.iloc[0, 0] = 999
    assert sibling.iloc[0, 0] == source.iloc[0, 0] == owned.column_values(0)[0]


@pytest.mark.parametrize(
    "index",
    [
        pd.RangeIndex(2, 8, 2, name="sample"),
        pd.Index([3, 1, 2], name="sample"),
        pd.date_range("2026-01-01", periods=3, tz="UTC", name="sample"),
    ],
)
def test_series_and_duplicate_columns_survive(catalog, index):
    series = pd.Series([1, None, 3], index=index, dtype="Int16", name="force")
    owned = _roundtrip(series, catalog)
    assert owned.data_type_id == SERIES_VALUE_TYPE_ID
    pd.testing.assert_series_equal(owned.to_pandas(), series, check_freq=False)
    frame = pd.DataFrame([[1, 2], [3, 4]], columns=["same", "same"])
    pd.testing.assert_frame_equal(_roundtrip(frame, catalog).to_pandas(), frame)


@pytest.mark.parametrize(
    "source",
    [
        np.asarray([object()]),
        np.zeros(2, dtype=[("x", "i4")]),
        pd.Series([{"x": 1}]),
        pd.Series(pd.Categorical(["a", "b"])),
        pd.Series([1], index=pd.MultiIndex.from_tuples([("a", "b")])),
    ],
)
def test_unsupported_objects_fail_actionably(catalog, source):
    with pytest.raises(
        (TypeError, ValueError), match="unsupported|Unsupported|support|MultiIndex"
    ):
        _roundtrip(source, catalog)


def test_native_subclasses_rejected(catalog):
    class ArraySubclass(np.ndarray):
        pass

    class FrameSubclass(pd.DataFrame):
        pass

    for source in (np.arange(3).view(ArraySubclass), FrameSubclass({"x": [1]})):
        with pytest.raises(TypeError, match="subclasses"):
            _roundtrip(source, catalog)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(version=2),
        lambda p: p.update(unknown=True),
        lambda p: p["array"].update(dtype="|O"),
        lambda p: p["array"].update(shape=[False]),
        lambda p: p["array"].update(shape=[2**40]),
        lambda p: p["array"].update(shape=[1]),
        lambda p: p["array"].update(buffer="!!!!"),
    ],
)
def test_malformed_scientific_payloads_are_rejected_before_use(catalog, mutation):
    payload = serialize_runtime_value(np.arange(3.0), catalog=catalog)
    mutation(payload)
    with pytest.raises((TypeError, ValueError)):
        deserialize_runtime_value(payload, catalog=catalog)


def test_per_value_and_cumulative_bounds_preflight_before_buffer_decode(catalog):
    payload = serialize_runtime_value(np.arange(8, dtype="u1"), catalog=catalog)
    with (
        patch(
            "ea_node_editor.runtime_contracts.scientific_values.SCIENTIFIC_VALUE_MAX_BYTES",
            7,
        ),
        patch("ea_node_editor.runtime_contracts.scientific_codec._decode") as decode,
    ):
        with pytest.raises(ValueError, match="limit"):
            deserialize_runtime_value(payload, catalog=catalog)
        decode.assert_not_called()
    with (
        patch(
            "ea_node_editor.runtime_contracts.scientific_values.SCIENTIFIC_OPERATION_MAX_BYTES",
            15,
        ),
        patch("ea_node_editor.runtime_contracts.scientific_codec._decode") as decode,
    ):
        with pytest.raises(ValueError, match="cumulative"):
            deserialize_runtime_value({"nested": [payload, payload]}, catalog=catalog)
        decode.assert_not_called()


def test_catalog_and_durable_constraints(catalog):
    owned = snapshot_scientific_value(np.arange(4))
    serialize_runtime_value(
        owned, catalog=catalog, declared_type_id=ARRAY_VALUE_TYPE_ID
    )
    for type_id in (
        "COREX.DataTypes.GraphArray",
        TABLE_VALUE_TYPE_ID,
        SERIES_VALUE_TYPE_ID,
    ):
        with pytest.raises(ValueError):
            serialize_runtime_value(owned, catalog=catalog, declared_type_id=type_id)
    from ea_node_editor.runtime_contracts.durable_values import _validate_durable_value

    assert (
        _validate_durable_value(owned, catalog=catalog, artifact_context=None, depth=0)
        == "durable_value_ineligible"
    )


def test_python_script_gets_native_mutable_inputs_but_publishes_owned_snapshots(
    catalog,
):
    script = """@corex.node
@corex.input("array", value_type="COREX.DataTypes.ArrayValue")
@corex.input("table", value_type="COREX.DataTypes.TableValue")
@corex.output("out_array", value_type="COREX.DataTypes.ArrayValue")
@corex.output("out_table", value_type="COREX.DataTypes.TableValue")
def run(ctx, array, table):
    import numpy as np, pandas as pd
    assert type(array) is np.ndarray and type(table) is pd.DataFrame
    assert ctx.inputs['array'] is array
    array[0] = 99
    table.iloc[0, 0] = 99
    return {'out_array': array, 'out_table': table}
"""
    inputs = {
        "array": snapshot_scientific_value(np.arange(3)),
        "table": snapshot_scientific_value(pd.DataFrame({"x": [1, 2, 3]})),
    }
    context = ExecutionContext(
        "run", "script", "ws", inputs, {"script": script}, lambda *_: None
    )
    result = PythonScriptNodePlugin().execute(context)
    assert type(result.outputs["out_array"]) is ArrayValue
    assert type(result.outputs["out_table"]) is TableValue
    assert result.outputs["out_array"].to_numpy()[0] == 99
    assert inputs["array"].to_numpy()[0] == 0
    assert inputs["table"].column_values(0)[0] == 1
    assert context.inputs is inputs
    # One native conversion per invocation; sibling readers always start from retained data.
    assert materialize_script_values(inputs)["array"][0] == 0


def test_nested_tree_values_keep_structure(catalog):
    tree = DataTree((((2, 1), (np.arange(3), {"table": pd.Series([1, 2])})),))
    restored = _roundtrip(tree, catalog)
    assert restored.paths == tree.paths
    assert type(restored[(2, 1)][0]) is ArrayValue
    assert type(restored[(2, 1)][1]["table"]) is TableValue


def test_plain_json_tuple_subclasses_and_numpy_json_scalars_keep_existing_behavior():
    Pair = namedtuple("Pair", "first second")
    assert serialize_runtime_value(Pair(np.float64(1.5), np.str_("x"))) == [1.5, "x"]
    tree = DataTree.from_list([1.0, 2.0])
    assert materialize_script_values(tree) is tree


def test_native_adapter_leaves_custom_containers_to_consumer_validation():
    class HostileList(list):
        def __iter__(self):
            raise AssertionError("custom list must not be traversed")

    class HostileMapping(dict):
        def items(self):
            raise AssertionError("custom mapping must not be traversed")

    for value in (HostileList([1]), HostileMapping(x=1)):
        assert materialize_script_values({"input": value})["input"] is value


def test_direct_table_constructor_rejects_mutable_labels(catalog):
    owned = _roundtrip(pd.Series([1, 2]), catalog)
    with pytest.raises(TypeError, match="names"):
        TableValue(
            owned.kind, owned.columns, (np.array([1]),), owned.index, owned.range_index
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["columns"][0].update(dtype="custom"),
        lambda p: p["columns"][0].update(mask=""),
        lambda p: p["columns"][0].update(timezone="UTC"),
        lambda p: p["columns"][1].update(offsets=[0, 900, 900]),
        lambda p: p.update(range_index=[0, 2, 0]),
        lambda p: p.update(range_index=[0, 1, 1]),
        lambda p: p.update(range_index=None),
    ],
)
def test_table_metadata_preflight_happens_before_any_buffer_decode(catalog, mutation):
    payload = serialize_runtime_value(
        pd.DataFrame({"n": pd.Series([1, None], dtype="Int64"), "s": ["a", "b"]}),
        catalog=catalog,
    )
    mutation(payload)
    with patch("ea_node_editor.runtime_contracts.scientific_codec._decode") as decode:
        with pytest.raises((TypeError, ValueError)):
            deserialize_runtime_value(payload, catalog=catalog)
        decode.assert_not_called()


def test_empty_nullable_series_preserves_dtype(catalog):
    for dtype in ("Int64", "Float32", "boolean", "string", "object"):
        source = pd.Series([], dtype=dtype, name="empty")
        pd.testing.assert_series_equal(_roundtrip(source, catalog).to_pandas(), source)


def test_custom_extension_dtype_named_like_builtin_is_rejected():
    class SpoofedInteger(pd.api.extensions.ExtensionDtype):
        name = "Int64"
        type = np.int64
        kind = "i"
        na_value = pd.NA

    from ea_node_editor.runtime_contracts.scientific_values import (
        _validate_pandas_dtype,
    )

    with pytest.raises(TypeError, match="custom"):
        _validate_pandas_dtype(SpoofedInteger())


def test_native_preflight_rejects_oversized_table_before_capture():
    frame = pd.DataFrame({"a": np.arange(8, dtype="u1"), "b": np.arange(8, dtype="u1")})
    with (
        patch(
            "ea_node_editor.runtime_contracts.scientific_values.SCIENTIFIC_VALUE_MAX_BYTES",
            15,
        ),
        patch.object(ArrayValue, "from_numpy") as capture,
    ):
        with pytest.raises(ValueError, match="limit"):
            snapshot_scientific_value(frame)
        capture.assert_not_called()


def test_nullable_float_preserves_unmasked_nan_separately_from_missing(catalog):
    source = pd.Series(
        pd.arrays.FloatingArray(
            np.asarray([np.nan, 1.0, 0.0]), np.asarray([False, False, True])
        )
    )
    restored = _roundtrip(source, catalog).to_pandas()
    pd.testing.assert_series_equal(restored, source)
    assert restored.isna().tolist() == [False, False, True]
