from __future__ import annotations

from pathlib import Path

import pytest

from ea_node_editor.addons.tabular_data.loader_cache_service import (
    MissingTabularDependencyError,
    SelectableObject,
    SourceScanResult,
    TabularLoaderCacheService,
    UnsupportedTabularFormatError,
)
from ea_node_editor.common.artifact_refs import format_managed_artifact_ref
from ea_node_editor.runtime_contracts import (
    ArrayDataRef,
    ArraySlice2D,
    ArraySlice2DRequest,
    TabularColumn,
    TabularDataRef,
    TabularDataWindow,
    TabularSchema,
    TabularWindowRequest,
)
from ea_node_editor.ui.tabular_preview_provider import (
    TABULAR_PREVIEW_INLINE_COLUMN_LIMIT,
    TABULAR_PREVIEW_INLINE_ROW_LIMIT,
    TabularPreviewProvider,
    describe_tabular_selector,
)


class _FakeTableService:
    def __init__(self) -> None:
        self.window_requests: list[TabularWindowRequest] = []
        self.backend_requests: list[dict] = []
        self.materialization_calls = 0

    def scan_source(self, source_path: Path, _options) -> SourceScanResult:  # noqa: ANN001
        return SourceScanResult(
            source_path=Path(source_path),
            format_id="csv",
            objects=(
                SelectableObject(
                    object_id="table",
                    display_name="table",
                    kind="table",
                    row_count=1_000_000,
                    column_count=80,
                ),
            ),
            selected_object_id="table",
            size_bytes=2 * 1024 * 1024 * 1024,
            size_class="large",
            warnings=("large_source",),
        )

    def open_source(self, _source_path: Path, _options) -> TabularDataRef:  # noqa: ANN001
        return TabularDataRef(
            ref_id="table_ref",
            resolver_id="tabular.cache",
            backend_id="fake_table_backend",
            object_id="table",
            row_count=1_000_000,
            column_count=80,
            metadata={
                "warnings": ["large_source"],
                "warning_facts": [
                    {
                        "code": "large_source",
                        "severity": "warning",
                        "source_name": "large.csv",
                    }
                ],
            },
        )

    def schema(self, ref: TabularDataRef) -> TabularSchema:
        return TabularSchema(
            columns=tuple(TabularColumn(f"col_{index}", "str") for index in range(ref.column_count or 0)),
            row_count=ref.row_count,
        )

    def metadata(self, ref: TabularDataRef) -> dict[str, object]:
        return {
            "row_count": ref.row_count,
            "column_count": ref.column_count,
            "warnings": ["large_source"],
        }

    def window(self, _ref: TabularDataRef, request: TabularWindowRequest) -> TabularDataWindow:
        self.window_requests.append(request)
        columns = tuple(f"col_{index}" for index in range(request.column_offset, request.column_offset + request.column_limit))
        rows = tuple(
            {column: f"{column}_row_{request.row_offset + row_index}" for column in columns}
            for row_index in range(request.row_limit)
        )
        return TabularDataWindow(
            columns=columns,
            rows=rows,
            row_offset=request.row_offset,
            column_offset=request.column_offset,
            total_rows=1_000_000,
            total_columns=80,
        )

    def preview_window(self, ref: TabularDataRef, request: dict) -> TabularDataWindow:
        self.backend_requests.append(dict(request))
        return self.window(
            ref,
            TabularWindowRequest(
                row_offset=request["row_offset"],
                row_limit=request["row_limit"],
                column_offset=request["column_offset"],
                column_limit=request["column_limit"],
                columns=tuple(request.get("columns", ())),
            ),
        )

    def to_pandas(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
        self.materialization_calls += 1
        raise AssertionError("preview provider must not materialize pandas data")

    def to_polars(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
        self.materialization_calls += 1
        raise AssertionError("preview provider must not materialize polars data")

    def to_numpy(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
        self.materialization_calls += 1
        raise AssertionError("preview provider must not materialize numpy data")


class _FakeArrayService:
    def __init__(self) -> None:
        self.slice_requests: list[ArraySlice2DRequest] = []

    def scan_source(self, source_path: Path, _options) -> SourceScanResult:  # noqa: ANN001
        return SourceScanResult(
            source_path=Path(source_path),
            format_id="npy",
            objects=(
                SelectableObject(
                    object_id="array",
                    display_name="array",
                    kind="array",
                    shape=(4096, 2048),
                    dtype="float32",
                ),
            ),
            selected_object_id="array",
            size_bytes=1024,
            size_class="small",
        )

    def open_source(self, _source_path: Path, _options) -> ArrayDataRef:  # noqa: ANN001
        return ArrayDataRef(
            ref_id="array_ref",
            resolver_id="tabular.cache",
            backend_id="npy_mmap",
            object_id="array",
            shape=(4096, 2048),
            dtype="float32",
        )

    def metadata(self, ref: ArrayDataRef) -> dict[str, object]:
        return {"shape": list(ref.shape), "dtype": ref.dtype}

    def slice_2d(self, ref: ArrayDataRef, request: ArraySlice2DRequest) -> ArraySlice2D:
        self.slice_requests.append(request)
        values = tuple(
            tuple(float(row_index + column_index) for column_index in range(request.column_limit))
            for row_index in range(request.row_limit)
        )
        return ArraySlice2D(
            values=values,
            row_offset=request.row_offset,
            column_offset=request.column_offset,
            shape=ref.shape,
            dtype=ref.dtype,
        )


class _SelectionRequiredService(_FakeTableService):
    def scan_source(self, source_path: Path, _options) -> SourceScanResult:  # noqa: ANN001
        return SourceScanResult(
            source_path=Path(source_path),
            format_id="xlsx",
            objects=(
                SelectableObject("Sheet1", "Sheet1", "table", row_count=1, column_count=1),
                SelectableObject("Sheet2", "Sheet2", "table", row_count=1, column_count=1),
            ),
            requires_selection=True,
            size_bytes=128,
            size_class="small",
        )

    def open_source(self, _source_path: Path, _options) -> TabularDataRef:  # noqa: ANN001
        raise AssertionError("preview provider should not open ambiguous multi-object sources")


class _MissingDependencyService(_FakeTableService):
    def scan_source(self, _source_path: Path, _options) -> SourceScanResult:  # noqa: ANN001
        raise MissingTabularDependencyError(
            format_id="xlsx",
            dependency="openpyxl",
            purpose="workbook sheet scanning",
        )


class _UnsupportedSelectorService(_FakeTableService):
    def scan_source(self, source_path: Path, _options) -> SourceScanResult:  # noqa: ANN001
        raise UnsupportedTabularFormatError(Path(source_path))


def test_tabular_preview_provider_caps_inline_table_windows_without_materialization(tmp_path: Path) -> None:
    source = tmp_path / "large.csv"
    source.write_text("col_0,col_1\nA,B\n", encoding="utf-8")
    service = _FakeTableService()
    provider = TabularPreviewProvider(service_factory=lambda: service)

    payload = provider.describe_preview(
        {"path": str(source)},
        {"row_limit": 10_000, "column_limit": 1_000},
        mode="inline",
    )

    assert payload["state"] == "ready"
    assert payload["preview_kind"] == "table"
    assert payload["schema"]["row_count"] == 1_000_000
    assert len(payload["window"]["rows"]) == TABULAR_PREVIEW_INLINE_ROW_LIMIT
    assert len(payload["window"]["columns"]) == TABULAR_PREVIEW_INLINE_COLUMN_LIMIT
    assert payload["window"]["bounded"] is True
    assert payload["window"]["client_side_full_scan"] is False
    assert payload["warnings"][0]["source_name"] == "large.csv"
    assert "source_path" not in payload["warnings"][0]
    assert service.window_requests[0].row_limit == TABULAR_PREVIEW_INLINE_ROW_LIMIT
    assert service.window_requests[0].column_limit == TABULAR_PREVIEW_INLINE_COLUMN_LIMIT
    assert service.materialization_calls == 0


def test_tabular_preview_provider_reuses_identical_inline_table_payload(tmp_path: Path) -> None:
    source = tmp_path / "large.csv"
    source.write_text("col_0,col_1\nA,B\n", encoding="utf-8")
    service = _FakeTableService()
    provider = TabularPreviewProvider(service_factory=lambda: service)
    request = {"row_limit": 50, "column_limit": 50}

    payload = provider.describe_preview({"path": str(source)}, request, mode="inline")
    payload["window"]["rows"][0]["col_0"] = "mutated"
    repeated = provider.describe_preview({"path": str(source)}, dict(request), mode="inline")

    assert len(service.window_requests) == 1
    assert repeated["state"] == "ready"
    assert repeated["window"]["rows"][0]["col_0"] == "col_0_row_0"


def test_tabular_preview_provider_routes_search_filter_sort_to_backend_request(tmp_path: Path) -> None:
    source = tmp_path / "query.csv"
    source.write_text("col_0,col_1\nA,B\n", encoding="utf-8")
    service = _FakeTableService()
    provider = TabularPreviewProvider(service_factory=lambda: service)

    payload = provider.table_window_payload(
        {"path": str(source)},
        {
            "row_offset": 25,
            "row_limit": 12,
            "column_offset": 2,
            "column_limit": 4,
            "sort": [{"column": "col_3", "direction": "ascending"}],
            "filters": [{"column": "col_4", "op": "contains", "value": "A"}],
            "search": "station",
        },
    )

    assert payload["state"] == "ready"
    assert service.backend_requests
    assert service.backend_requests[0]["search"] == "station"
    assert service.backend_requests[0]["filters"][0]["column"] == "col_4"
    assert payload["window"]["request"]["sort"][0]["column"] == "col_3"
    assert payload["window"]["row_offset"] == 25


def test_tabular_preview_provider_executes_real_backend_sort_and_filter(tmp_path: Path) -> None:
    source = tmp_path / "weather.csv"
    source.write_text(
        "station,temp\nCharlie,30\nalpha,21.5\nBravo,21.5\ndelta,9\n",
        encoding="utf-8",
    )
    provider = TabularPreviewProvider(
        service_factory=lambda: TabularLoaderCacheService(cache_dir=tmp_path / "cache"),
    )
    request_base = {"row_offset": 0, "row_limit": 50, "column_offset": 0, "column_limit": 50}

    sorted_payload = provider.table_window_payload(
        {"path": str(source)},
        {**request_base, "sort": {"column": "temp", "descending": False}},
    )
    filtered_payload = provider.table_window_payload(
        {"path": str(source)},
        {**request_base, "filters": {"text": "21.5"}},
    )

    assert sorted_payload["state"] == "ready"
    assert [row["station"] for row in sorted_payload["window"]["rows"]] == [
        "delta",
        "alpha",
        "Bravo",
        "Charlie",
    ]
    assert filtered_payload["state"] == "ready"
    assert filtered_payload["window"]["total_rows"] == 2
    assert sorted(row["station"] for row in filtered_payload["window"]["rows"]) == [
        "Bravo",
        "alpha",
    ]


def test_tabular_preview_provider_describes_array_slice_metadata(tmp_path: Path) -> None:
    source = tmp_path / "array.npy"
    source.write_bytes(b"fake")
    service = _FakeArrayService()
    provider = TabularPreviewProvider(service_factory=lambda: service)

    payload = provider.describe_preview(
        {"path": str(source)},
        {"row_offset": 4, "column_offset": 7, "row_limit": 5, "column_limit": 3},
        mode="fullscreen",
    )

    assert payload["state"] == "ready"
    assert payload["preview_kind"] == "array"
    assert payload["array"] == {"shape": [4096, 2048], "dtype": "float32", "object_id": "array"}
    assert payload["slice_2d"]["request"] == {
        "row_offset": 4,
        "row_limit": 5,
        "column_offset": 7,
        "column_limit": 3,
    }
    assert payload["slice_2d"]["shape"] == [4096, 2048]
    assert service.slice_requests[0].row_limit == 5


def test_tabular_preview_provider_reports_selector_state_without_opening_source(tmp_path: Path) -> None:
    source = tmp_path / "book.xlsx"
    source.write_bytes(b"fake")
    service = _SelectionRequiredService()
    provider = TabularPreviewProvider(service_factory=lambda: service)

    payload = provider.describe_preview({"path": str(source)})

    assert payload["state"] == "selection_required"
    assert payload["selector"]["requires_selection"] is True
    assert [item["object_id"] for item in payload["selector"]["objects"]] == ["Sheet1", "Sheet2"]
    assert payload["error"]["code"] == "selector_required"


def test_tabular_selector_lists_real_excel_sheets_and_honors_selected_sheet(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "book.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.title = "First"
    workbook["First"].append(["name", "value"])
    second = workbook.create_sheet("Second")
    second.append(["name", "value"])
    workbook.save(source)

    provider = TabularPreviewProvider(
        service_factory=lambda: TabularLoaderCacheService(cache_dir=tmp_path / "cache"),
    )

    missing_selection = provider.describe_selector({"path": str(source)})
    selected = provider.describe_selector({"path": str(source), "selected_object": "Second"})

    assert missing_selection["state"] == "selection_required"
    assert [item["object_id"] for item in missing_selection["selector"]["objects"]] == ["First", "Second"]
    assert selected["state"] == "ready"
    assert selected["selector"]["selected_object"] == "Second"
    assert selected["selector"]["requires_selection"] is False


def test_tabular_selector_reports_missing_source_and_recoverable_scan_errors(tmp_path: Path) -> None:
    missing = TabularPreviewProvider().describe_selector({"path": str(tmp_path / "missing.xlsx")})
    source = tmp_path / "book.xlsx"
    source.write_bytes(b"fake")
    missing_backend = TabularPreviewProvider(
        service_factory=lambda: _MissingDependencyService(),
    ).describe_selector({"path": str(source)})
    unsupported = TabularPreviewProvider(
        service_factory=lambda: _UnsupportedSelectorService(),
    ).describe_selector({"path": str(source)})

    assert missing["state"] == "error"
    assert missing["error"]["code"] == "missing_source"
    assert missing_backend["state"] == "error"
    assert missing_backend["error"]["code"] == "missing_backend"
    assert missing_backend["error"]["recoverable"] is True
    assert unsupported["state"] == "error"
    assert unsupported["error"]["code"] == "unsupported_format"


def test_describe_tabular_selector_wrapper_uses_scan_only_payload() -> None:
    payload = describe_tabular_selector({})

    assert payload["state"] == "placeholder"
    assert payload["content_kind"] == "tabular"


def test_tabular_preview_provider_resolves_project_managed_source_refs(tmp_path: Path) -> None:
    project_path = tmp_path / "project.cxproj"
    managed_source = tmp_path / "project.data" / "nodes" / "tabular-source" / "in" / "weather.csv"
    managed_source.parent.mkdir(parents=True)
    managed_source.write_text("col_0,col_1\nA,B\n", encoding="utf-8")
    service = _FakeTableService()
    provider = TabularPreviewProvider(
        service_factory=lambda: service,
        project_context_provider=lambda: (
            project_path,
            {
                "artifact_store": {
                    "artifacts": {
                        "tabular_source.weather": {
                                "relative_path": "nodes/tabular-source/in/weather.csv",
                        }
                    },
                    "staged": {},
                }
            },
        ),
    )

    payload = provider.describe_preview({"path": format_managed_artifact_ref("tabular_source.weather")})

    assert payload["state"] == "ready"
    assert payload["source"]["resolution_kind"] == "managed"
    assert payload["source"]["resolved_path"] == str(managed_source)
