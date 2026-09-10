from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from ea_node_editor.addons.tabular_data.loader_cache_service import (
    MissingTabularDependencyError,
    SelectionRequiredError,
    TabularLoadOptions,
    TabularLoaderCacheService,
    supported_format_ids,
)
from ea_node_editor.addons.tabular_data.source_backends import SourceBackendMethods
from ea_node_editor.runtime_contracts import (
    ArrayDataRef,
    ArraySlice2DRequest,
    TabularDataRef,
    TabularMaterializationOptions,
    TabularWindowRequest,
)


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _run_python_probe(code: str, *args: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-E", "-c", textwrap.dedent(code), *args],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert completed.returncode == 0, (
        f"Probe exited {completed.returncode}\n"
        f"STDOUT:\n{completed.stdout}\n"
        f"STDERR:\n{completed.stderr}"
    )


def test_supported_format_registry_matches_p03_scope() -> None:
    assert supported_format_ids() == (
        "csv",
        "tsv",
        "txt",
        "xlsx",
        "xlsm",
        "parquet",
        "hdf5",
        "npy",
        "npz",
    )


def test_format_specific_behavior_is_owned_by_source_backends() -> None:
    assert issubclass(TabularLoaderCacheService, SourceBackendMethods)
    for method_name in (
        "_scan_text",
        "_scan_excel",
        "_scan_parquet",
        "_scan_hdf5",
        "_scan_npy",
        "_scan_npz",
        "_read_parquet_window",
        "_write_parquet_cache",
    ):
        assert method_name in vars(SourceBackendMethods)
        assert method_name not in vars(TabularLoaderCacheService)


@pytest.mark.parametrize(
    ("filename", "contents", "options", "expected_columns", "expected_second_value"),
    [
        (
            "weather.csv",
            "# generated\nstation,temp\nA,21.5\nB,22.0\n",
            TabularLoadOptions(skip_rows=1, schema_hints={"temp": "float64"}),
            ("station", "temp"),
            22.0,
        ),
        (
            "weather.tsv",
            "station\ttemp\nA\t21.5\nB\t22.0\n",
            TabularLoadOptions(),
            ("station", "temp"),
            22.0,
        ),
        (
            "weather.txt",
            "station|temp\nA|21.5\nB|22.0\n",
            TabularLoadOptions(delimiter="|"),
            ("station", "temp"),
            22.0,
        ),
    ],
)
def test_text_loaders_infer_or_honor_options_and_return_bounded_windows(
    tmp_path: Path,
    filename: str,
    contents: str,
    options: TabularLoadOptions,
    expected_columns: tuple[str, str],
    expected_second_value: float,
) -> None:
    source = tmp_path / filename
    source.write_text(contents, encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    scan = service.scan_source(source, options)
    assert scan.selected_object_id == "table"
    assert scan.requires_selection is False
    # Open never scans the source for row counts; they backfill from the
    # managed parquet cache after the first read.
    assert scan.objects[0].row_count is None

    ref = service.open_source(source, options)
    assert isinstance(ref, TabularDataRef)
    assert ref.resolver_id == "tabular.cache"
    assert ref.backend_id == "python_text_stream"
    assert ref.row_count is None

    window = service.window(ref, TabularWindowRequest(row_offset=1, row_limit=1, column_limit=2))
    assert window.columns == expected_columns
    assert window.rows == ({"station": "B", "temp": expected_second_value},)
    assert window.total_rows == 2

    schema = service.schema(ref)
    assert tuple(column.name for column in schema.columns) == expected_columns
    assert schema.row_count == 2
    if "temp" in options.schema_hints:
        assert schema.columns[1].dtype == "float64"


def test_txt_delimiter_detection_reads_only_the_first_4096_characters(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    source = tmp_path / "large.txt"
    source.write_text("a|b\n" * 5000, encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    real_open = Path.open
    read_sizes: list[int] = []

    class _TrackingReader:
        def __init__(self, handle):  # noqa: ANN001
            self._handle = handle

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *args):  # noqa: ANN002, ANN204
            self._handle.close()

        def read(self, size: int = -1) -> str:
            read_sizes.append(size)
            return self._handle.read(size)

    def tracking_open(path: Path, *args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        handle = real_open(path, *args, **kwargs)
        if path == source and args and args[0] == "r":
            return _TrackingReader(handle)
        return handle

    monkeypatch.setattr(Path, "open", tracking_open)

    delimiter = service._resolve_text_delimiter(source, "txt", TabularLoadOptions())

    assert delimiter == "|"
    assert read_sizes == [4096]


def test_text_materialization_without_cached_row_count_reads_all_rows(tmp_path: Path) -> None:
    pytest.importorskip("pandas")
    source = tmp_path / "weather.csv"
    source.write_text("station,temp\nA,21.5\nB,22.0\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    ref = service.open_source(source)
    assert isinstance(ref, TabularDataRef)
    assert ref.row_count is None

    frame = service.to_pandas(ref, TabularMaterializationOptions(allow_full_materialization=True))

    assert list(frame["station"]) == ["A", "B"]
    assert list(frame["temp"]) == [21.5, 22.0]


def test_text_loader_supports_headerless_files(tmp_path: Path) -> None:
    source = tmp_path / "raw.txt"
    source.write_text("A|21.5\nB|22.0\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    ref = service.open_source(source, TabularLoadOptions(delimiter="|", header_row=None))
    window = service.window(ref, TabularWindowRequest(row_limit=2, column_limit=2))

    assert isinstance(ref, TabularDataRef)
    assert window.columns == ("column_1", "column_2")
    assert window.rows == (
        {"column_1": "A", "column_2": 21.5},
        {"column_1": "B", "column_2": 22.0},
    )


def test_tabular_ref_reopens_from_source_uri_and_load_options(tmp_path: Path) -> None:
    source = tmp_path / "raw.txt"
    source.write_text("A|21.5\nB|22.0\n", encoding="utf-8")
    original = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    ref = original.open_source(source, TabularLoadOptions(delimiter="|", header_row=None))
    fresh = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    fresh.ensure_table_ref(ref)
    window = fresh.window(ref, TabularWindowRequest(row_limit=2, column_limit=2))

    assert window.columns == ("column_1", "column_2")
    assert window.rows == (
        {"column_1": "A", "column_2": 21.5},
        {"column_1": "B", "column_2": 22.0},
    )


def test_existing_tabular_ref_reopens_when_source_schema_changes(tmp_path: Path) -> None:
    source = tmp_path / "changing.csv"
    source.write_text("time,temp\n0,21.5\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    ref = service.open_source(source)

    assert tuple(column.name for column in service.schema(ref).columns) == ("time", "temp")

    source.write_text("time,temp,pressure\n1,22.0,101.3\n", encoding="utf-8")
    window = service.window(ref, TabularWindowRequest(row_limit=1, column_limit=0))

    assert window.columns == ("time", "temp", "pressure")
    assert window.rows == ({"time": 1, "temp": 22.0, "pressure": 101.3},)


def test_parquet_arrow_batches_stream_before_exhausting_source(tmp_path: Path) -> None:
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    produced = 0

    def fake_iter(_record, _options, _path):  # noqa: ANN001
        nonlocal produced
        for index in range(20):
            produced += 1
            yield {"batch": index}

    service._iter_parquet_batches = fake_iter  # type: ignore[method-assign]
    iterator = service._iter_parquet_batches_safely(object(), object(), tmp_path / "dummy.parquet")  # type: ignore[arg-type]
    try:
        first = next(iterator)
        time.sleep(0.05)
        assert first == {"batch": 0}
        assert produced < 20
    finally:
        iterator.close()


def test_excel_loader_requires_selection_for_multi_sheet_workbook_and_streams_selected_sheet(
    tmp_path: Path,
) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "book.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.title = "First"
    workbook["First"].append(["name", "value"])
    workbook["First"].append(["alpha", 1])
    second = workbook.create_sheet("Second")
    second.append(["name", "value"])
    second.append(["beta", 2])
    workbook.save(source)

    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    scan = service.scan_source(source)

    assert scan.requires_selection is True
    assert tuple(item.object_id for item in scan.objects) == ("First", "Second")
    with pytest.raises(SelectionRequiredError):
        service.open_source(source)

    ref = service.open_source(source, TabularLoadOptions(selected_object="Second"))
    window = service.window(ref, TabularWindowRequest(row_limit=1, column_limit=2))
    assert isinstance(ref, TabularDataRef)
    assert ref.object_id == "Second"
    assert window.rows == ({"name": "beta", "value": 2},)


def test_npy_loader_uses_mmap_backed_array_refs_and_bounded_slices(tmp_path: Path) -> None:
    numpy = pytest.importorskip("numpy")
    source = tmp_path / "array.npy"
    numpy.save(source, numpy.arange(12, dtype=numpy.float64).reshape(3, 4))
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    ref = service.open_source(source)
    result = service.slice_2d(ref, ArraySlice2DRequest(row_offset=1, row_limit=1, column_offset=1, column_limit=2))

    assert isinstance(ref, ArrayDataRef)
    assert ref.backend_id == "npy_mmap"
    assert ref.metadata["format_id"] == "npy"
    assert ref.shape == (3, 4)
    assert ref.dtype == "float64"
    assert result.values == ((5.0, 6.0),)


def test_npz_loader_requires_key_selection_and_treats_archive_as_array_source(tmp_path: Path) -> None:
    numpy = pytest.importorskip("numpy")
    source = tmp_path / "archive.npz"
    numpy.savez(source, first=numpy.arange(4).reshape(2, 2), second=numpy.arange(6).reshape(3, 2))
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    scan = service.scan_source(source)
    assert scan.requires_selection is True
    assert tuple(item.object_id for item in scan.objects) == ("first", "second")
    with pytest.raises(SelectionRequiredError):
        service.open_source(source)

    ref = service.open_source(source, TabularLoadOptions(selected_object="second"))
    result = service.slice_2d(ref, ArraySlice2DRequest(row_limit=2, column_limit=1))
    assert isinstance(ref, ArrayDataRef)
    assert ref.backend_id == "npz_archive"
    assert ref.shape == (3, 2)
    assert result.values == ((0,), (2,))


def test_parquet_loader_lane_loads_tiny_fixture_or_reports_recoverable_dependency_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "table.parquet"
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    if not _module_available("pyarrow"):
        source.write_bytes(b"not parquet")
        with pytest.raises(MissingTabularDependencyError) as exc_info:
            service.scan_source(source)
        assert exc_info.value.format_id == "parquet"
        assert exc_info.value.dependency == "pyarrow"
        assert exc_info.value.recoverable is True
        return

    _run_python_probe(
        """
        import sys
        from pathlib import Path

        import pyarrow
        import pyarrow.parquet as pq

        from ea_node_editor.addons.tabular_data.loader_cache_service import TabularLoaderCacheService
        from ea_node_editor.runtime_contracts import TabularDataRef, TabularWindowRequest

        root = Path(sys.argv[1])
        source = root / "table.parquet"
        pq.write_table(pyarrow.table({"name": ["alpha", "beta"], "value": [1, 2]}), source)

        service = TabularLoaderCacheService(cache_dir=root / "cache")
        ref = service.open_source(source)
        window = service.window(ref, TabularWindowRequest(row_limit=1, column_limit=2))

        assert isinstance(ref, TabularDataRef)
        assert ref.metadata["format_id"] == "parquet"
        assert window.rows == ({"name": "alpha", "value": 1},)
        """,
        str(tmp_path),
    )


def test_hdf5_loader_lane_loads_tiny_fixture_or_reports_recoverable_dependency_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "arrays.h5"
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    if not _module_available("h5py"):
        source.write_bytes(b"not hdf5")
        with pytest.raises(MissingTabularDependencyError) as exc_info:
            service.scan_source(source)
        assert exc_info.value.format_id == "hdf5"
        assert exc_info.value.dependency == "h5py"
        assert exc_info.value.recoverable is True
        return

    h5py = pytest.importorskip("h5py")
    numpy = pytest.importorskip("numpy")
    with h5py.File(source, "w") as handle:
        handle.create_dataset("matrix", data=numpy.arange(6).reshape(3, 2))

    ref = service.open_source(source)
    result = service.slice_2d(ref, ArraySlice2DRequest(row_offset=1, row_limit=2, column_limit=2))
    assert isinstance(ref, ArrayDataRef)
    assert ref.backend_id == "hdf5_dataset"
    assert ref.object_id == "matrix"
    assert result.values == ((2, 3), (4, 5))


def test_managed_cache_eviction_preserves_entry_returned_to_caller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("pyarrow")
    source = tmp_path / "weather.csv"
    source.write_text("station,temp\nA,21.5\nB,22.0\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    original_enforce = service.enforce_cache_size_limit

    def tiny_enforce(*, preserve_paths=None):  # noqa: ANN001, ANN202
        return original_enforce(max_bytes=1, preserve_paths=preserve_paths)

    monkeypatch.setattr(service, "enforce_cache_size_limit", tiny_enforce)
    ref = service.open_source(source)

    window = service.window(ref, TabularWindowRequest(row_limit=2, column_limit=2))

    assert window.rows == ({"station": "A", "temp": 21.5}, {"station": "B", "temp": 22.0})
    assert list((tmp_path / "cache").glob("*/*.parquet"))
