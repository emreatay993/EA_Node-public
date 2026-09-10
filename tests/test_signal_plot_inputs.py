# Purpose: Prove scientific, tree and file-backed Signal Plot input equivalence.
# Map: feature_routes/plotter_nodes
# Tests: tests/test_signal_plot_inputs.py
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from ea_node_editor.addons.tabular_data.loader_cache_service import TabularLoadOptions, TabularLoaderCacheService
from ea_node_editor.execution.signal_plot_inputs import normalize_signal_inputs
from ea_node_editor.runtime_contracts import ArraySlice2DRef, DataTree, TabularWindowRef
from ea_node_editor.runtime_contracts.scientific_values import ArrayValue, snapshot_scientific_value


def test_tree_branches_and_container_items_keep_their_meaning():
    tree = DataTree({(2,): ([9, 4], np.array([[10, 20], [11, 21]])), (0,): (3, 2, 1)})
    traces = normalize_signal_inputs(tree)
    assert len(traces) == 3
    np.testing.assert_array_equal(traces[0].x, [0, 1, 2])
    np.testing.assert_array_equal(traces[0].y, [3, 2, 1])
    np.testing.assert_array_equal(traces[1].y, [9, 4])
    np.testing.assert_array_equal(traces[2].x, [10, 11])
    np.testing.assert_array_equal(traces[2].y, [20, 21])
    matrix = normalize_signal_inputs(DataTree.from_item([[10, 20], [11, 21]]))
    np.testing.assert_array_equal(matrix[0].x, traces[2].x)
    branches = normalize_signal_inputs(DataTree({(0,): (10, 20), (1,): (11, 21)}))
    assert len(branches) == 2
    np.testing.assert_array_equal(branches[0].x, [0, 1])


@pytest.mark.parametrize("value", [[2, 4, None, 9], np.array([2., 4., np.nan, 9.]), pd.Series([2., 4., np.nan, 9.], index=[8, 9, 10, 11], name="Force")])
def test_one_dimensional_values_use_sample_indices(value):
    trace, = normalize_signal_inputs(value)
    np.testing.assert_array_equal(trace.x, [0, 1, 2, 3])
    np.testing.assert_allclose(trace.y, [2, 4, np.nan, 9], equal_nan=True)
    assert not trace.x.flags.writeable
    assert not trace.y.flags.writeable


def test_immutable_inputs_share_buffers_and_preserve_integer_precision(monkeypatch):
    array = ArrayValue.from_numpy(np.array([[2**60, 3], [2**60 + 1, 4]], dtype=np.int64))
    trace, = normalize_signal_inputs(array)
    assert trace.x.dtype == np.dtype("int64")
    assert int(trace.x[1]) - int(trace.x[0]) == 1
    assert np.shares_memory(trace.y, array.to_numpy())
    table = snapshot_scientific_value(pd.DataFrame({"x": [1, 2], "y": [3, 4]}))
    monkeypatch.setattr(type(table), "to_pandas", lambda *_: pytest.fail("Built-in readers must not materialize pandas"))
    trace, = normalize_signal_inputs(table)
    assert np.shares_memory(trace.y, table.column_values(1))


def test_mixed_table_defaults_and_explicit_selection_preserve_order():
    frame = pd.DataFrame({"text": ["a", "b", "c"], "bool": [True, False, True], "X": [2, 1, 3], "Y": [5, 6, 7], "Z": pd.Series([8, None, 9], dtype="Int64")})
    traces = normalize_signal_inputs(frame)
    assert [trace.label for trace in traces] == ["Y", "Z"]
    np.testing.assert_array_equal(traces[0].x, [2, 1, 3])
    np.testing.assert_allclose(traces[1].y, [8, np.nan, 9], equal_nan=True)
    chosen = normalize_signal_inputs(frame, x_mode="column", x_column="Y", y_columns=["Z", "X"])
    assert [trace.label for trace in chosen] == ["Z", "X"]
    np.testing.assert_array_equal(chosen[0].x, [5, 6, 7])
    indexed = normalize_signal_inputs(frame, x_mode="index")
    assert [trace.label for trace in indexed] == ["X", "Y", "Z"]
    np.testing.assert_array_equal(indexed[0].x, [0, 1, 2])


def test_selectors_are_exact_and_duplicates_require_positions():
    frame = pd.DataFrame([[1, 2, 3], [4, 5, 6]], columns=[" y ", "y", "y"])
    with pytest.raises(ValueError, match="duplicated"):
        normalize_signal_inputs(frame, y_columns=["y"])
    trace, = normalize_signal_inputs(frame, x_mode="column", x_column=" y ", y_columns=[2])
    np.testing.assert_array_equal(trace.y, [3, 6])
    with pytest.raises(ValueError, match="exact name"):
        normalize_signal_inputs(frame, x_mode="column", x_column=" Y ")
    with pytest.raises(ValueError, match="exact name"):
        normalize_signal_inputs(np.ones((2, 3)), y_columns=["Column 2"])


@pytest.mark.parametrize("timezone", [None, "Europe/Istanbul"])
def test_datetime_axis_is_typed_and_timezone_coordinates_are_utc(timezone):
    dates = pd.date_range("2026-01-01", periods=3, tz=timezone)
    frame = pd.DataFrame({"time": dates, "y": [2., np.nan, 4.]})
    trace, = normalize_signal_inputs(frame)
    assert trace.x_kind == "datetime"
    assert trace.x.dtype.kind == "M"
    np.testing.assert_array_equal(trace.x, dates.to_numpy(dtype="datetime64[us]"))
    explicit, = normalize_signal_inputs(frame, x_mode="column", x_column="time")
    np.testing.assert_array_equal(trace.x, explicit.x)
    frame["time"] = frame["time"].astype(str)
    trace, = normalize_signal_inputs(frame)
    assert trace.x_kind == "numeric"
    np.testing.assert_array_equal(trace.x, [0, 1, 2])
    with pytest.raises(ValueError, match="typed datetime"):
        normalize_signal_inputs(frame, x_mode="column", x_column="time")


def test_gaps_and_log_validation_leave_source_samples_intact():
    array = ArrayValue.from_numpy(np.array([1., np.inf, np.nan, -2., 0.]))
    trace, = normalize_signal_inputs(array, logarithmic_y=True)
    np.testing.assert_array_equal(trace.y, array.to_numpy())
    with pytest.raises(ValueError, match="positive finite"):
        normalize_signal_inputs([-1., 0., np.nan], logarithmic_y=True)


@pytest.mark.parametrize("value, message", [
    ([], "non-empty"),
    (DataTree(), "at least one"),
    ([[1, 2], [3]], "rectangular"),
    (np.ones((2, 2, 2)), "one- or two-dimensional"),
    (["1", "2"], "real numeric"),
    (np.array([1j, 2j]), "no numeric Y"),
    (pd.DataFrame({"a": [True, False]}), "no numeric Y"),
])
def test_invalid_sources_fail_clearly(value, message):
    with pytest.raises(ValueError, match=message):
        normalize_signal_inputs(value)


def test_invalid_explicit_selections_do_not_fall_back():
    frame = pd.DataFrame({"a": [1, 2], "b": [3, 4], "text": ["x", "y"]})
    for kwargs in ({"y_columns": [9]}, {"y_columns": [True]}, {"y_columns": ["A"]}, {"y_columns": ["a", "a"]}, {"y_columns": ["text"]}, {"x_mode": "column", "x_column": "text"}, {"x_mode": "guess"}):
        with pytest.raises(ValueError):
            normalize_signal_inputs(frame, **kwargs)


@pytest.mark.parametrize("value", [[1, True, 3], [1, np.bool_(False), 3]])
def test_plain_numeric_sequences_reject_boolean_samples_before_coercion(value):
    with pytest.raises(ValueError, match="Boolean samples"):
        normalize_signal_inputs(value)


@pytest.mark.parametrize("value", [[[True, 0, 2], [False, 1, 3]], [["left", 0, 2], ["right", 1, 3]]])
def test_plain_matrices_skip_boolean_and_text_columns_without_coercing_neighbors(value):
    trace, = normalize_signal_inputs(value)
    np.testing.assert_array_equal(trace.x, [0, 1])
    np.testing.assert_array_equal(trace.y, [2, 3])
    with pytest.raises(ValueError):
        normalize_signal_inputs(value, x_mode="column", x_column=0, y_columns=[2])
    with pytest.raises(ValueError):
        normalize_signal_inputs(value, x_mode="index", y_columns=[0])


@pytest.mark.parametrize("source_direct", [False, True])
def test_csv_source_matches_native_and_unknown_numeric_columns_are_inferred(tmp_path, source_direct):
    source = tmp_path / "data.csv"
    source.write_text("date,label,flag,x,y\n2026-01-01,a,true,10,2\n2026-01-02,b,false,8,\n2026-01-03,c,true,9,6\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    options = TabularLoadOptions(cache_policy="source_direct") if source_direct else TabularLoadOptions()
    ref = service.open_source(source, options)
    # Limit to columns whose declared/inferred meaning is equivalent on both paths.
    ref = replace(ref, metadata={**ref.metadata, "selected_columns": ["label", "flag", "x", "y"]})
    trace, = normalize_signal_inputs(ref, service=service)
    native, = normalize_signal_inputs(pd.DataFrame({"x": [10, 8, 9], "y": [2., np.nan, 6.]}))
    np.testing.assert_array_equal(trace.x, native.x)
    np.testing.assert_array_equal(trace.y, native.y)
    if source_direct:
        assert all(not column.dtype for column in service.schema(ref).columns)
        with pytest.raises(ValueError, match="typed datetime"):
            unrestricted = service.open_source(source, options)
            normalize_signal_inputs(unrestricted, service=service, x_mode="column", x_column="date", y_columns=["y"])


def test_explicit_file_mapping_reads_only_needed_columns_and_window_rows(tmp_path, monkeypatch):
    source = tmp_path / "data.parquet"
    pd.DataFrame({"text": ["a"] * 6, "x": range(6), "y": range(10, 16), "z": range(20, 26)}).to_parquet(source)
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    ref = service.open_source(source)
    calls = []
    original = service.column_arrays
    def capture(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(service, "column_arrays", capture)
    window = TabularWindowRef("selected", ref, row_offset=2, row_limit=2, columns=("z", "x", "y"))
    trace, = normalize_signal_inputs(window, service=service, x_mode="column", x_column="x", y_columns=["y"])
    np.testing.assert_array_equal(trace.x, [2, 3])
    np.testing.assert_array_equal(trace.y, [12, 13])
    assert len(calls) == 1
    assert set(calls[0]["columns"]) == {"x", "y"}
    assert calls[0]["row_offset"] == 2 and calls[0]["row_limit"] == 2
    with pytest.raises(ValueError, match="available column"):
        normalize_signal_inputs(window, service=service, y_columns=["text"])


def test_parquet_datetime_values_and_nulls_preserve_alignment(tmp_path):
    source = tmp_path / "dates.parquet"
    frame = pd.DataFrame({"date": pd.to_datetime(["2026-01-01", None, "2026-01-03"], utc=True), "y": [1, 2, 3]})
    frame.to_parquet(source)
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    file_trace, = normalize_signal_inputs(service.open_source(source), service=service)
    native_trace, = normalize_signal_inputs(frame)
    assert file_trace.x_kind == "datetime"
    np.testing.assert_array_equal(file_trace.x, native_trace.x)
    np.testing.assert_array_equal(file_trace.y, [1, 2, 3])


def test_array_refs_are_full_length_and_honor_slices_and_selected_columns(tmp_path, monkeypatch):
    source = tmp_path / "array.npy"
    data = np.arange(1200).reshape(300, 4)
    np.save(source, data)
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    ref = service.open_source(source)
    traces = normalize_signal_inputs(ref, service=service)
    assert len(traces) == 3 and len(traces[0].y) == 300
    np.testing.assert_array_equal(traces[0].x, data[:, 0])
    sliced = ArraySlice2DRef("slice", ref, row_offset=100, row_limit=5, column_offset=1, column_limit=2)
    trace, = normalize_signal_inputs(sliced, service=service)
    np.testing.assert_array_equal(trace.x, data[100:105, 1])
    np.testing.assert_array_equal(trace.y, data[100:105, 2])
    hinted = replace(ref, metadata={**ref.metadata, "node_options": {"array_slice_2d": {"row_offset": 105, "row_limit": 3, "column_offset": 2, "column_limit": 1}}})
    trace, = normalize_signal_inputs(hinted, service=service)
    np.testing.assert_array_equal(trace.x, range(3))
    np.testing.assert_array_equal(trace.y, data[105:108, 2])
    calls = []
    original = service.to_numpy
    def capture(ref, options):
        calls.append(options.slices)
        return original(ref, options)
    monkeypatch.setattr(service, "to_numpy", capture)
    normalize_signal_inputs(ref, service=service, x_mode="index", y_columns=[3])
    assert calls == [((0, 300), (3, 1))]


def test_explicit_refs_replace_input_preview_hints(tmp_path):
    array_path = tmp_path / "data.npy"
    data = np.arange(800).reshape(200, 4)
    np.save(array_path, data)
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    ref = service.open_source(array_path)
    ref = replace(ref, metadata={**ref.metadata, "node_options": {"array_slice_2d": {"row_limit": 50, "column_limit": 50}}})
    sliced = ArraySlice2DRef("slice", ref, row_offset=100, row_limit=3, column_limit=2)
    trace, = normalize_signal_inputs(sliced, service=service)
    np.testing.assert_array_equal(trace.x, data[100:103, 0])
    table_path = tmp_path / "table.parquet"
    pd.DataFrame({"a": range(5), "b": range(10, 15), "c": range(20, 25)}).to_parquet(table_path)
    ref = service.open_source(table_path)
    ref = replace(ref, metadata={**ref.metadata, "node_options": {"selected_columns": ["a"]}})
    window = TabularWindowRef("window", ref, row_offset=1, row_limit=2, columns=("b", "c"))
    trace, = normalize_signal_inputs(window, service=service)
    np.testing.assert_array_equal(trace.x, [11, 12])
    np.testing.assert_array_equal(trace.y, [21, 22])


def test_duplicate_parquet_names_support_positional_selection(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    source = tmp_path / "duplicate.parquet"
    pq.write_table(pa.Table.from_arrays([pa.array([1, 2]), pa.array([8, 9]), pa.array([3, 4])], names=["same", "same", "tail"]), source)
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    ref = service.open_source(source)
    trace, = normalize_signal_inputs(ref, service=service, x_mode="column", x_column=0, y_columns=[1])
    np.testing.assert_array_equal(trace.x, [1, 2])
    np.testing.assert_array_equal(trace.y, [8, 9])
    with pytest.raises(ValueError, match="duplicated"):
        normalize_signal_inputs(ref, service=service, y_columns=["same"])


def test_npz_decompresses_once_for_all_selected_traces(tmp_path, monkeypatch):
    source = tmp_path / "data.npz"
    data = np.arange(400).reshape(100, 4)
    np.savez_compressed(source, values=data)
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    ref = service.open_source(source, TabularLoadOptions(selected_object="values"))
    calls = []
    original = service.to_numpy
    def capture(ref, options):
        calls.append(options.slices)
        return original(ref, options)
    monkeypatch.setattr(service, "to_numpy", capture)
    traces = normalize_signal_inputs(ref, service=service)
    assert len(calls) == 1 and len(traces) == 3
    for i, trace in enumerate(traces, 1):
        np.testing.assert_array_equal(trace.y, data[:, i])
        assert np.may_share_memory(trace.x, trace.y)


def test_hdf5_typed_columns_preserve_integer_precision(tmp_path):
    h5py = pytest.importorskip("h5py")
    source = tmp_path / "table.hdf5"
    with h5py.File(source, "w") as file:
        file.create_dataset("table", data=np.array([(2**60, 1), (2**60 + 1, 2)], dtype=[("x", "i8"), ("y", "i8")]))
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    trace, = normalize_signal_inputs(service.open_source(source, TabularLoadOptions(selected_object="table")), service=service)
    assert trace.x.dtype == np.dtype("int64")
    assert int(trace.x[1]) - int(trace.x[0]) == 1


def test_typed_direct_csv_missing_samples_are_gaps(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("x,y\n1,3\n2,\n3,4\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    ref = service.open_source(source, TabularLoadOptions(cache_policy="source_direct", schema_hints={"x": "int64", "y": "float64"}))
    trace, = normalize_signal_inputs(ref, service=service)
    assert trace.x.dtype == np.dtype("int64")
    np.testing.assert_allclose(trace.y, [3, np.nan, 4], equal_nan=True)
