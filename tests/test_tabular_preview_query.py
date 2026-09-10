from __future__ import annotations

from pathlib import Path

import pytest

import ea_node_editor.addons.tabular_data.loader_cache_service as loader_module
from ea_node_editor.addons.tabular_data.loader_cache_service import (
    TabularLoadOptions,
    TabularLoaderCacheService,
)
from ea_node_editor.addons.tabular_data.preview_query import (
    NormalizedPreviewQuery,
    evaluate_arrow_query,
    evaluate_python_query,
)
from ea_node_editor.runtime_contracts import TabularDataRef


_QUERY_CSV = (
    "station,temp,country\n"
    "Charlie,30,US\n"
    "alpha,21.5,FR\n"
    "Bravo,21.5,US\n"
    "delta,9,DE\n"
)


def _open_query_table(
    tmp_path: Path,
    *,
    options: TabularLoadOptions | None = None,
) -> tuple[TabularLoaderCacheService, TabularDataRef]:
    source = tmp_path / "query.csv"
    source.write_text(_QUERY_CSV, encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    ref = service.open_source(source, options)
    assert isinstance(ref, TabularDataRef)
    return service, ref


def _base_request(**overrides: object) -> dict[str, object]:
    request: dict[str, object] = {
        "row_offset": 0,
        "row_limit": 50,
        "column_offset": 0,
        "column_limit": 50,
    }
    request.update(overrides)
    return request


def _stations(window) -> list[str]:  # noqa: ANN001
    return [str(row["station"]) for row in window.rows]


def _logical_rows(window) -> tuple[tuple[object, ...], ...]:  # noqa: ANN001
    def logical(value: object) -> object:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return value

    return tuple(
        tuple(logical(row[column]) for column in window.columns)
        for row in window.rows
    )


def test_normalized_preview_query_covers_empty_columns_offsets_and_invalid_columns() -> None:
    columns = ("station", "temp", "country")

    empty = NormalizedPreviewQuery.from_mapping({}, columns)
    explicit = NormalizedPreviewQuery.from_mapping(
        _base_request(columns=["country", "station"], column_limit=1),
        columns,
    )
    offset = NormalizedPreviewQuery.from_mapping(
        _base_request(column_offset=1, column_limit=2),
        columns,
    )
    invalid = NormalizedPreviewQuery.from_mapping(
        _base_request(columns=["missing"]),
        columns,
    )

    assert empty.selected_columns == columns
    assert empty.row_offset == 0
    assert empty.row_limit == 50
    assert empty.predicates == ()
    assert empty.sort_directives == ()
    assert explicit.selected_columns == ("country",)
    assert offset.selected_columns == ("temp", "country")
    assert invalid.selected_columns == ()
    assert "_normalize_sort_directives" not in vars(loader_module)
    assert "_collect_query_predicates" not in vars(loader_module)


@pytest.mark.parametrize(
    ("query_request", "expected"),
    [
        pytest.param({}, ["Charlie", "alpha", "Bravo", "delta"], id="empty"),
        pytest.param(
            {"filters": {"text": "US"}},
            ["Charlie", "Bravo"],
            id="filter",
        ),
        pytest.param(
            {"search": "21.5"},
            ["alpha", "Bravo"],
            id="search",
        ),
        pytest.param(
            {"sort": {"column": "temp", "descending": True}},
            ["Charlie", "alpha", "Bravo", "delta"],
            id="sort",
        ),
        pytest.param(
            {"sort": [{"column": "temp"}, {"column": "station", "descending": True}]},
            ["delta", "Bravo", "alpha", "Charlie"],
            id="multi-sort",
        ),
        pytest.param(
            {"filters": [{"column": "temp", "op": "gte", "value": "21.5"}]},
            ["Charlie", "alpha", "Bravo"],
            id="numeric-filter",
        ),
        pytest.param(
            {"sort": {"column": "temp"}, "row_offset": 1, "row_limit": 2},
            ["alpha", "Bravo"],
            id="offset-limit",
        ),
        pytest.param(
            {"row_offset": 3, "row_limit": 1},
            ["delta"],
            id="deep-page",
        ),
    ],
)
def test_python_preview_query_cases(query_request: dict[str, object], expected: list[str]) -> None:
    rows = (
        {"station": "Charlie", "temp": "30", "country": "US"},
        {"station": "alpha", "temp": "21.5", "country": "FR"},
        {"station": "Bravo", "temp": "21.5", "country": "US"},
        {"station": "delta", "temp": "9", "country": "DE"},
    )
    query = NormalizedPreviewQuery.from_mapping(query_request, ("station", "temp", "country"))

    result = evaluate_python_query(query, rows, scan_row_cap=200_000)

    assert [row["station"] for row in result.rows] == expected
    assert result.backend == "python"
    assert result.truncated is False


def test_preview_window_source_direct_reports_bounded_total_and_truncation(
    tmp_path: Path,
) -> None:
    service, ref = _open_query_table(
        tmp_path,
        options=TabularLoadOptions(cache_policy="source_direct"),
    )
    query = NormalizedPreviewQuery.from_mapping(
        _base_request(sort={"column": "station"}),
        ("station", "temp", "country"),
    )

    result = evaluate_python_query(
        query,
        service._iter_all_table_records(service._table_record(ref)),  # noqa: SLF001
        scan_row_cap=2,
    )

    assert result.total_rows == 2
    assert result.truncated is True
    assert result.scanned_rows == 2


def test_preview_window_source_direct_publishes_truncation_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, ref = _open_query_table(
        tmp_path,
        options=TabularLoadOptions(cache_policy="source_direct"),
    )
    monkeypatch.setattr(loader_module, "PREVIEW_QUERY_SCAN_ROW_CAP", 2)

    window = service.preview_window(ref, _base_request(sort={"column": "station"}))

    assert window.total_rows == 2
    assert window.metadata["query_scan_truncated"] is True
    assert window.metadata["query_scanned_rows"] == 2


@pytest.mark.parametrize(
    "query_request",
    [
        pytest.param(_base_request(), id="empty"),
        pytest.param(_base_request(columns=["station", "country"]), id="selected-columns"),
        pytest.param(
            _base_request(filters={"text": "US"}, sort={"column": "station"}),
            id="filter",
        ),
        pytest.param(_base_request(search="21.5", sort={"column": "station"}), id="search"),
        pytest.param(
            _base_request(filters=[{"column": "temp", "op": "gte", "value": "21.5"}]),
            id="numeric-filter",
        ),
        pytest.param(
            _base_request(filters=[{"column": "station", "op": "startswith", "value": "b"}]),
            id="starts-with",
        ),
        pytest.param(
            _base_request(filters=[{"column": "station", "op": "endswith", "value": "a"}]),
            id="ends-with",
        ),
        pytest.param(
            _base_request(filters=[{"column": "country", "op": "not_contains", "value": "us"}]),
            id="not-contains",
        ),
        pytest.param(
            _base_request(filters=[{"column": "station", "op": "eq", "value": " BRAVO "}]),
            id="equality",
        ),
        pytest.param(
            _base_request(sort={"column": "temp", "descending": True}),
            id="descending-sort",
        ),
        pytest.param(
            _base_request(sort=[{"column": "temp"}, {"column": "station", "descending": True}]),
            id="multi-sort",
        ),
        pytest.param(
            _base_request(row_offset=1, row_limit=2, column_offset=1, column_limit=2),
            id="offset-limit",
        ),
        pytest.param(_base_request(row_offset=3, row_limit=1), id="deep-page"),
        pytest.param(_base_request(columns=["missing"]), id="invalid-column"),
    ],
)
def test_preview_window_arrow_and_python_match_for_query_case(
    tmp_path: Path,
    query_request: dict[str, object],
) -> None:
    pytest.importorskip("pyarrow")
    source = tmp_path / "query.csv"
    source.write_text(_QUERY_CSV, encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    managed_ref = service.open_source(source)
    direct_ref = service.open_source(source, TabularLoadOptions(cache_policy="source_direct"))

    managed = service.preview_window(managed_ref, query_request)
    direct = service.preview_window(direct_ref, query_request)

    assert managed.columns == direct.columns
    assert _logical_rows(managed) == _logical_rows(direct)
    assert managed.total_rows == direct.total_rows
    if managed.columns:
        assert managed.metadata.get("query_backend") == "arrow"


def test_managed_and_source_direct_queries_preserve_deliberate_source_typing(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    source = tmp_path / "query.csv"
    source.write_text(_QUERY_CSV, encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    managed_ref = service.open_source(source)
    direct_ref = service.open_source(source, TabularLoadOptions(cache_policy="source_direct"))

    managed = service.preview_window(managed_ref, _base_request())
    direct = service.preview_window(direct_ref, _base_request())

    assert isinstance(managed.rows[0]["temp"], (int, float))
    assert isinstance(direct.rows[0]["temp"], str)


_NULL_BLANK_ROWS = (
    {"id": "null", "value": None, "null_only": None, "blank_only": ""},
    {"id": "empty", "value": "", "null_only": None, "blank_only": " "},
    {"id": "blank", "value": "  ", "null_only": None, "blank_only": "\t"},
    {"id": "text", "value": "alpha", "null_only": None, "blank_only": ""},
    {"id": "numeric", "value": "10", "null_only": None, "blank_only": "  "},
    {"id": "contains", "value": "xray", "null_only": None, "blank_only": ""},
)


@pytest.mark.parametrize(
    ("query_filter", "expected_ids"),
    [
        pytest.param(
            {"column": "null_only", "op": "equals", "value": "anything"},
            [],
            id="null-positive-false",
        ),
        pytest.param(
            {"column": "blank_only", "op": "equals", "value": ""},
            [],
            id="blank-positive-false",
        ),
        pytest.param(
            {"column": "missing", "op": "contains", "value": ""},
            [],
            id="invalid-column-positive-false",
        ),
        pytest.param(
            {"column": "value", "op": "contains", "value": ""},
            ["text", "numeric", "contains"],
            id="contains-empty-skips-no-value-cells",
        ),
        pytest.param(
            {"column": "value", "op": "equals", "value": "alpha"},
            ["text"],
            id="equality",
        ),
        pytest.param(
            {"column": "value", "op": "gte", "value": "alpha"},
            ["text", "contains"],
            id="relational",
        ),
        pytest.param(
            {"column": "value", "op": "not_contains", "value": "x"},
            ["null", "empty", "blank", "text", "numeric"],
            id="not-contains-accepts-no-value-cells",
        ),
        pytest.param(
            {"column": "missing", "op": "not_contains", "value": "x"},
            ["null", "empty", "blank", "text", "numeric", "contains"],
            id="invalid-column-not-contains-true",
        ),
    ],
)
def test_named_column_no_value_policy_matches_arrow_and_python(
    tmp_path: Path,
    query_filter: dict[str, str],
    expected_ids: list[str],
) -> None:
    pyarrow = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    source = tmp_path / "null_blank.parquet"
    pq.write_table(
        pyarrow.table(
            {
                column: [row[column] for row in _NULL_BLANK_ROWS]
                for column in _NULL_BLANK_ROWS[0]
            }
        ),
        source,
    )
    query = NormalizedPreviewQuery.from_mapping(
        _base_request(columns=["id"], filters=[query_filter]),
        ("id", "value", "null_only", "blank_only"),
    )
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    arrow = evaluate_arrow_query(
        query,
        source,
        query_table_for=service._query_table_for,  # noqa: SLF001
        run_io=service._run_io,  # noqa: SLF001
    )
    python = evaluate_python_query(query, _NULL_BLANK_ROWS, scan_row_cap=200_000)

    assert arrow is not None
    assert [row["id"] for row in arrow.rows] == expected_ids
    assert [row["id"] for row in python.rows] == expected_ids
    assert arrow.total_rows == python.total_rows == len(expected_ids)


def _evaluate_parquet_and_python(
    tmp_path: Path,
    rows: tuple[dict[str, object], ...],
    query_request: dict[str, object],
):  # noqa: ANN202
    pyarrow = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    source = tmp_path / "parity.parquet"
    columns = tuple(rows[0])
    pq.write_table(
        pyarrow.table({column: [row[column] for row in rows] for column in columns}),
        source,
    )
    query = NormalizedPreviewQuery.from_mapping(query_request, columns)
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    arrow = evaluate_arrow_query(
        query,
        source,
        query_table_for=service._query_table_for,  # noqa: SLF001
        run_io=service._run_io,  # noqa: SLF001
    )
    python = evaluate_python_query(query, rows, scan_row_cap=200_000)
    assert arrow is not None
    return arrow, python


def test_mixed_direction_multi_key_sort_uses_each_keys_null_placement(tmp_path: Path) -> None:
    rows = (
        {"id": "g1-null", "a": 1, "b": None},
        {"id": "g1-high", "a": 1, "b": 3},
        {"id": "g1-low", "a": 1, "b": 1},
        {"id": "g2-null", "a": 2, "b": None},
        {"id": "g2-high", "a": 2, "b": 2},
    )
    arrow, python = _evaluate_parquet_and_python(
        tmp_path,
        rows,
        _base_request(
            columns=["id"],
            sort=[
                {"column": "a", "direction": "ascending"},
                {"column": "b", "direction": "descending"},
            ],
        ),
    )
    expected = ["g1-null", "g1-high", "g1-low", "g2-null", "g2-high"]

    assert [row["id"] for row in arrow.rows] == expected
    assert [row["id"] for row in python.rows] == expected


def test_arrow_sort_keys_remain_pyarrow_24_compatible_pairs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pa_compute = pytest.importorskip("pyarrow.compute")
    original_sort_indices = pa_compute.sort_indices
    captured_keys: list[tuple[str, str]] = []
    captured_null_placements: list[str | None] = []

    def capture_sort_indices(values, /, sort_keys=(), **kwargs):  # noqa: ANN001, ANN003, ANN202
        captured_keys.extend(sort_keys)
        captured_null_placements.append(kwargs.get("null_placement"))
        return original_sort_indices(values, sort_keys=sort_keys, **kwargs)

    monkeypatch.setattr(pa_compute, "sort_indices", capture_sort_indices)
    rows = (
        {"id": "null", "a": 1, "b": None},
        {"id": "finite", "a": 1, "b": 2},
    )

    _evaluate_parquet_and_python(
        tmp_path,
        rows,
        _base_request(
            columns=["id"],
            sort=[
                {"column": "a", "direction": "ascending"},
                {"column": "b", "direction": "descending"},
            ],
        ),
    )

    assert captured_keys
    assert all(len(key) == 2 for key in captured_keys)
    assert captured_null_placements == ["at_end"]


def test_internal_arrow_sort_key_names_do_not_shadow_user_columns(tmp_path: Path) -> None:
    rows = (
        {
            "id": "a",
            "__sort_kind_0": "group",
            "__sort_numeric_0": "user-a",
            "__sort_text_0": "text-a",
            "__sort_kind_1": 1.0,
            "__sort_numeric_1": "keep-a",
        },
        {
            "id": "b",
            "__sort_kind_0": "group",
            "__sort_numeric_0": "user-b",
            "__sort_text_0": "text-b",
            "__sort_kind_1": 2.0,
            "__sort_numeric_1": "keep-b",
        },
        {
            "id": "c",
            "__sort_kind_0": "alpha",
            "__sort_numeric_0": "user-c",
            "__sort_text_0": "text-c",
            "__sort_kind_1": 3.0,
            "__sort_numeric_1": "keep-c",
        },
    )
    selected_columns = list(rows[0])
    arrow, python = _evaluate_parquet_and_python(
        tmp_path,
        rows,
        _base_request(
            columns=selected_columns,
            sort=[
                {"column": "__sort_kind_0", "direction": "ascending"},
                {"column": "__sort_kind_1", "direction": "descending"},
            ],
        ),
    )
    expected = (rows[2], rows[1], rows[0])

    assert arrow.rows == python.rows == expected
    assert arrow.rows[0]["__sort_kind_0"] == "alpha"
    assert tuple(arrow.rows[0]) == tuple(selected_columns)


_NON_FINITE_ROWS = (
    {"id": "finite-low", "value": 1.0},
    {"id": "nan", "value": float("nan")},
    {"id": "positive-inf", "value": float("inf")},
    {"id": "negative-inf", "value": float("-inf")},
    {"id": "finite-high", "value": 2.0},
    {"id": "null", "value": None},
)


@pytest.mark.parametrize(
    ("query_filter", "expected_ids"),
    [
        pytest.param(
            {"column": "value", "op": "gt", "value": "1.5"},
            ["finite-high"],
            id="relational-excludes-non-finite",
        ),
        pytest.param(
            {"column": "value", "op": "contains", "value": ""},
            ["finite-low", "finite-high"],
            id="contains-empty-excludes-non-finite",
        ),
        pytest.param(
            {"column": "value", "op": "not_contains", "value": "1"},
            ["nan", "positive-inf", "negative-inf", "finite-high", "null"],
            id="not-contains-accepts-non-finite",
        ),
    ],
)
def test_non_finite_filter_policy_matches_arrow_and_python(
    tmp_path: Path,
    query_filter: dict[str, str],
    expected_ids: list[str],
) -> None:
    arrow, python = _evaluate_parquet_and_python(
        tmp_path,
        _NON_FINITE_ROWS,
        _base_request(columns=["id"], filters=[query_filter]),
    )

    assert [row["id"] for row in arrow.rows] == expected_ids
    assert [row["id"] for row in python.rows] == expected_ids
    assert arrow.total_rows == python.total_rows == len(expected_ids)


@pytest.mark.parametrize(
    ("descending", "expected_ids"),
    [
        pytest.param(
            False,
            ["finite-low", "finite-high", "nan", "positive-inf", "negative-inf", "null"],
            id="ascending-missing-last",
        ),
        pytest.param(
            True,
            ["nan", "positive-inf", "negative-inf", "null", "finite-high", "finite-low"],
            id="descending-missing-first",
        ),
    ],
)
def test_non_finite_sort_policy_matches_arrow_and_python(
    tmp_path: Path,
    descending: bool,
    expected_ids: list[str],
) -> None:
    arrow, python = _evaluate_parquet_and_python(
        tmp_path,
        _NON_FINITE_ROWS,
        _base_request(columns=["id"], sort={"column": "value", "descending": descending}),
    )

    assert [row["id"] for row in arrow.rows] == expected_ids
    assert [row["id"] for row in python.rows] == expected_ids


def test_native_parquet_preview_sorts_before_row_and_column_window(tmp_path: Path) -> None:
    pyarrow = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    source = tmp_path / "query.parquet"
    pq.write_table(
        pyarrow.table(
            {
                "station": ["Charlie", "alpha", "Bravo", "delta"],
                "temp": [30.0, 21.5, 21.5, 9.0],
                "country": ["US", "FR", "US", "DE"],
            }
        ),
        source,
    )
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    ref = service.open_source(source)

    window = service.preview_window(
        ref,
        _base_request(
            row_offset=1,
            row_limit=2,
            column_limit=1,
            columns=["station"],
            sort={"column": "temp"},
        ),
    )

    assert window.columns == ("station",)
    assert window.rows == ({"station": "alpha"}, {"station": "Bravo"})
    assert window.row_offset == 1
    assert window.column_offset == 0
    assert window.total_rows == 4
    assert window.total_columns == 3
    assert window.metadata["query_backend"] == "arrow"


def test_preview_window_arrow_matches_numeric_string_filter_and_sort(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    source = tmp_path / "codes.csv"
    source.write_text("code,label\n100,A\n3,B\n20,C\n", encoding="utf-8")
    options = TabularLoadOptions(schema_hints={"code": "string"})
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    managed_ref = service.open_source(source, options)
    direct_ref = service.open_source(
        source,
        TabularLoadOptions(schema_hints={"code": "string"}, cache_policy="source_direct"),
    )
    request = _base_request(
        filters=[{"column": "code", "op": "gt", "value": "20"}],
        sort={"column": "code"},
    )

    managed = service.preview_window(managed_ref, request)
    direct = service.preview_window(direct_ref, request)

    assert managed.metadata.get("query_backend") == "arrow"
    assert managed.rows == direct.rows == ({"code": "100", "label": "A"},)
    assert managed.total_rows == direct.total_rows == 1


def test_preview_window_arrow_query_cache_reads_only_needed_columns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pyarrow = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    source = tmp_path / "wide.parquet"
    pq.write_table(
        pyarrow.table(
            {
                "station": ["A", "B", "C"],
                "temp": [21.5, 22.0, 23.0],
                "payload": ["x" * 64, "y" * 64, "z" * 64],
            }
        ),
        source,
    )
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    monkeypatch.setattr(service, "_QUERY_TABLE_CACHE_MAX_BYTES", 1)
    original_read_table = pq.read_table
    read_columns: list[object] = []

    def tracking_read_table(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        read_columns.append(kwargs.get("columns"))
        return original_read_table(*args, **kwargs)

    monkeypatch.setattr(pq, "read_table", tracking_read_table)
    ref = service.open_source(source)

    window = service.preview_window(
        ref,
        _base_request(columns=["station", "temp"], sort={"column": "temp"}),
    )

    assert _stations(window) == ["A", "B", "C"]
    assert read_columns == [["station", "temp"]]


def test_preview_window_reopens_stale_ref_before_querying(tmp_path: Path) -> None:
    source = tmp_path / "changing.csv"
    source.write_text("station,temp\nA,1\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    ref = service.open_source(source)
    source.write_text("station,temp,country\nB,2,US\n", encoding="utf-8")

    window = service.preview_window(ref, _base_request(search="US"))

    assert window.columns == ("station", "temp", "country")
    assert window.rows == ({"station": "B", "temp": 2, "country": "US"},)
    assert window.total_rows == 1
