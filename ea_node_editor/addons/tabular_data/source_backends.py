# Purpose: Format-specific scan, read, array, and Parquet-conversion behavior for Tabular sources.
# Map: feature_routes/tabular_data_addon_preview
# Tests: tests/test_tabular_loaders.py
# Landmarks: SourceBackendMethods, TabularLoadOptions, SourceScanResult
from __future__ import annotations

import csv
import importlib
import math
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ea_node_editor.addons.tabular_data.policy import (
    CACHE_POLICY_APP_MANAGED_PARQUET,
    CACHE_POLICY_SOURCE_DIRECT,
)
from ea_node_editor.runtime_contracts import (
    ArrayMaterializationOptions,
    ArraySlice2DRequest,
    TabularArrowBatchOptions,
    TabularColumn,
    TabularDataWindow,
    TabularWindowRequest,
)


SUPPORTED_FORMAT_IDS = ("csv", "tsv", "txt", "xlsx", "xlsm", "parquet", "hdf5", "npy", "npz")
TEXT_FORMAT_IDS = frozenset({"csv", "tsv", "txt"})
EXCEL_FORMAT_IDS = frozenset({"xlsx", "xlsm"})
ARRAY_FORMAT_IDS = frozenset({"hdf5", "npy", "npz"})
HDF5_SUFFIXES = frozenset({".h5", ".hdf5", ".hdf"})


class TabularLoaderError(RuntimeError):
    recoverable = True


class MissingTabularDependencyError(TabularLoaderError):
    def __init__(self, *, format_id: str, dependency: str, purpose: str) -> None:
        self.format_id = format_id
        self.dependency = dependency
        self.purpose = purpose
        super().__init__(
            f"The {format_id} loader requires optional dependency {dependency!r} for {purpose}."
        )


class UnsupportedTabularFormatError(TabularLoaderError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Unsupported tabular data format for {path.name!r}.")


class SelectionRequiredError(TabularLoaderError):
    def __init__(self, *, format_id: str, choices: Sequence[SelectableObject]) -> None:
        self.format_id = format_id
        self.choices = tuple(choices)
        names = ", ".join(choice.object_id for choice in self.choices)
        super().__init__(f"The {format_id} source contains multiple objects; select one of: {names}.")


class LargeDataMaterializationError(TabularLoaderError):
    def __init__(self, message: str, *, size_bytes: int) -> None:
        self.size_bytes = size_bytes
        super().__init__(message)


class TabularCacheNotReadyError(TabularLoaderError):
    def __init__(self, *, source_path: Path, size_bytes: int) -> None:
        self.source_path = source_path
        self.size_bytes = size_bytes
        super().__init__(f"The managed cache for {source_path.name!r} is still being prepared.")


@dataclass(slots=True, frozen=True)
class TabularLoadOptions:
    delimiter: str | None = None
    encoding: str = "utf-8"
    header_row: int | None = 0
    skip_rows: int = 0
    schema_hints: Mapping[str, str] = field(default_factory=dict)
    selected_object: str = ""
    allow_npz_archive_preview: bool = False
    cache_policy: str = CACHE_POLICY_APP_MANAGED_PARQUET

    def __post_init__(self) -> None:
        delimiter = self.delimiter
        if delimiter == "\\t":
            delimiter = "\t"
        if delimiter is not None:
            delimiter = str(delimiter)
            if not delimiter:
                delimiter = None
            elif len(delimiter) != 1:
                raise ValueError("delimiter must be a single character")
        encoding = str(self.encoding or "utf-8").strip() or "utf-8"
        header_row = _normalize_optional_non_negative_int("header_row", self.header_row)
        skip_rows = _normalize_non_negative_int("skip_rows", self.skip_rows)
        hints = {
            str(key).strip(): str(value).strip()
            for key, value in dict(self.schema_hints or {}).items()
            if str(key).strip() and str(value).strip()
        }
        cache_policy = str(self.cache_policy or "").strip()
        if cache_policy not in {CACHE_POLICY_APP_MANAGED_PARQUET, CACHE_POLICY_SOURCE_DIRECT}:
            cache_policy = CACHE_POLICY_APP_MANAGED_PARQUET
        object.__setattr__(self, "delimiter", delimiter)
        object.__setattr__(self, "encoding", encoding)
        object.__setattr__(self, "header_row", header_row)
        object.__setattr__(self, "skip_rows", skip_rows)
        object.__setattr__(self, "schema_hints", hints)
        object.__setattr__(self, "selected_object", str(self.selected_object or "").strip())
        object.__setattr__(self, "allow_npz_archive_preview", bool(self.allow_npz_archive_preview))
        object.__setattr__(self, "cache_policy", cache_policy)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> TabularLoadOptions:
        if not isinstance(payload, Mapping):
            return cls()
        return cls(
            delimiter=payload.get("delimiter"),
            encoding=str(payload.get("encoding", "utf-8") or "utf-8"),
            header_row=payload.get("header_row", 0),
            skip_rows=payload.get("skip_rows", 0),
            schema_hints=payload.get("schema_hints") if isinstance(payload.get("schema_hints"), Mapping) else {},
            selected_object=str(payload.get("selected_object", "") or ""),
            allow_npz_archive_preview=bool(payload.get("allow_npz_archive_preview", False)),
            cache_policy=str(payload.get("cache_policy", "") or ""),
        )

    def with_selected_object(self, selected_object: str) -> TabularLoadOptions:
        return replace(self, selected_object=selected_object)

    def to_cache_payload(self) -> dict[str, Any]:
        return {
            "delimiter": self.delimiter,
            "encoding": self.encoding,
            "header_row": self.header_row,
            "skip_rows": self.skip_rows,
            "schema_hints": dict(sorted(self.schema_hints.items())),
            "selected_object": self.selected_object,
            "allow_npz_archive_preview": self.allow_npz_archive_preview,
            "cache_policy": self.cache_policy,
        }

    @property
    def uses_managed_cache(self) -> bool:
        return self.cache_policy != CACHE_POLICY_SOURCE_DIRECT


@dataclass(slots=True, frozen=True)
class SourceStats:
    size_bytes: int
    mtime_ns: int


@dataclass(slots=True, frozen=True)
class SelectableObject:
    object_id: str
    display_name: str
    kind: str
    row_count: int | None = None
    column_count: int | None = None
    shape: tuple[int, ...] = ()
    dtype: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "object_id": self.object_id,
            "display_name": self.display_name,
            "kind": self.kind,
        }
        if self.row_count is not None:
            payload["row_count"] = self.row_count
        if self.column_count is not None:
            payload["column_count"] = self.column_count
        if self.shape:
            payload["shape"] = list(self.shape)
        if self.dtype:
            payload["dtype"] = self.dtype
        if self.metadata:
            payload["metadata"] = json_safe_mapping(self.metadata)
        return payload


@dataclass(slots=True, frozen=True)
class SourceScanResult:
    source_path: Path
    format_id: str
    objects: tuple[SelectableObject, ...]
    selected_object_id: str = ""
    requires_selection: bool = False
    size_bytes: int = 0
    size_class: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def selected_object(self) -> SelectableObject | None:
        if not self.selected_object_id:
            return None
        return next((item for item in self.objects if item.object_id == self.selected_object_id), None)

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "format_id": self.format_id,
            "objects": [item.to_payload() for item in self.objects],
            "selected_object_id": self.selected_object_id,
            "requires_selection": self.requires_selection,
            "size_bytes": self.size_bytes,
            "size_class": self.size_class,
            "warnings": list(self.warnings),
        }


@dataclass(slots=True, frozen=True)
class TableRecord:
    source_path: Path
    format_id: str
    options: TabularLoadOptions
    object_id: str
    backend_id: str
    columns: tuple[TabularColumn, ...]
    row_count: int | None
    size_bytes: int
    warnings: tuple[str, ...]
    stats: SourceStats = SourceStats(size_bytes=0, mtime_ns=0)


@dataclass(slots=True, frozen=True)
class ArrayRecord:
    source_path: Path
    format_id: str
    options: TabularLoadOptions
    object_id: str
    backend_id: str
    shape: tuple[int, ...]
    dtype: str
    size_bytes: int
    warnings: tuple[str, ...]
    stats: SourceStats = SourceStats(size_bytes=0, mtime_ns=0)


class SourceBackendMethods:
    """Format behavior mixed into the one concrete loader/cache service."""

    def _scan_text(
        self,
        path: Path,
        format_id: str,
        options: TabularLoadOptions,
        stats: SourceStats,
    ) -> SourceScanResult:
        delimiter = self._resolve_text_delimiter(path, format_id, options)
        columns = self._text_columns(path, options, delimiter)
        item = SelectableObject(
            object_id="table",
            display_name=path.name,
            kind="table",
            row_count=self._cached_parquet_row_count(path, options.with_selected_object("table")),
            column_count=len(columns),
            metadata={"delimiter": delimiter, "encoding": options.encoding},
        )
        return self._single_object_scan(path, format_id, item, stats)

    def _scan_excel(
        self,
        path: Path,
        format_id: str,
        options: TabularLoadOptions,
        stats: SourceStats,
    ) -> SourceScanResult:
        openpyxl = import_optional("openpyxl", format_id=format_id, purpose="workbook sheet scanning")
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            objects = tuple(
                SelectableObject(
                    object_id=sheet_name,
                    display_name=sheet_name,
                    kind="table",
                    row_count=_excel_data_row_count(workbook[sheet_name], options),
                    column_count=int(workbook[sheet_name].max_column or 0),
                )
                for sheet_name in workbook.sheetnames
            )
        finally:
            workbook.close()
        return self._object_scan(path, format_id, objects, options, stats)

    def _scan_parquet(
        self,
        path: Path,
        options: TabularLoadOptions,
        stats: SourceStats,
    ) -> SourceScanResult:
        pq = import_optional("pyarrow.parquet", format_id="parquet", purpose="Parquet metadata scanning")

        def read_metadata() -> tuple[int, int]:
            with pq.ParquetFile(path) as parquet_file:
                return int(parquet_file.metadata.num_rows), len(parquet_file.schema.names)

        row_count, column_count = self._run_io(read_metadata)
        item = SelectableObject(
            object_id="table",
            display_name=path.name,
            kind="table",
            row_count=row_count,
            column_count=column_count,
        )
        return self._object_scan(path, "parquet", (item,), options, stats)

    def _scan_hdf5(
        self,
        path: Path,
        options: TabularLoadOptions,
        stats: SourceStats,
    ) -> SourceScanResult:
        h5py = import_optional("h5py", format_id="hdf5", purpose="HDF5 dataset scanning")
        objects: list[SelectableObject] = []
        with h5py.File(path, "r") as handle:

            def visitor(name: str, item: Any) -> None:
                if not isinstance(item, h5py.Dataset):
                    return
                shape = tuple(int(value) for value in (item.shape or ()))
                dtype = str(item.dtype)
                if item.dtype.names:
                    objects.append(
                        SelectableObject(
                            object_id=name,
                            display_name=name,
                            kind="table",
                            row_count=shape[0] if shape else None,
                            column_count=len(item.dtype.names),
                            dtype=dtype,
                        )
                    )
                else:
                    objects.append(
                        SelectableObject(
                            object_id=name,
                            display_name=name,
                            kind="array",
                            shape=shape,
                            dtype=dtype,
                        )
                    )

            handle.visititems(visitor)
        return self._object_scan(path, "hdf5", tuple(objects), options, stats)

    def _scan_npy(
        self,
        path: Path,
        options: TabularLoadOptions,
        stats: SourceStats,
    ) -> SourceScanResult:
        numpy = import_optional("numpy", format_id="npy", purpose="NPY metadata scanning")
        array = numpy.load(path, mmap_mode="r", allow_pickle=False)
        item = SelectableObject(
            object_id="array",
            display_name=path.name,
            kind="array",
            shape=tuple(int(value) for value in array.shape),
            dtype=str(array.dtype),
            metadata={"mmap": True},
        )
        return self._object_scan(path, "npy", (item,), options, stats)

    def _scan_npz(
        self,
        path: Path,
        options: TabularLoadOptions,
        stats: SourceStats,
    ) -> SourceScanResult:
        numpy = import_optional("numpy", format_id="npz", purpose="NPZ archive scanning")
        objects: list[SelectableObject] = []
        with numpy.load(path, allow_pickle=False) as archive:
            for key in archive.files:
                if stats.size_bytes > self.policy.large_warning_bytes:
                    objects.append(
                        SelectableObject(
                            object_id=key,
                            display_name=key,
                            kind="array",
                            metadata={"archive_only": True},
                        )
                    )
                    continue
                array = archive[key]
                objects.append(
                    SelectableObject(
                        object_id=key,
                        display_name=key,
                        kind="array",
                        shape=tuple(int(value) for value in array.shape),
                        dtype=str(array.dtype),
                        metadata={"archive_only": True},
                    )
                )
        return self._object_scan(path, "npz", tuple(objects), options, stats)

    def _object_scan(
        self,
        path: Path,
        format_id: str,
        objects: tuple[SelectableObject, ...],
        options: TabularLoadOptions,
        stats: SourceStats,
    ) -> SourceScanResult:
        selected = options.selected_object if options.selected_object else (
            objects[0].object_id if len(objects) == 1 else ""
        )
        return SourceScanResult(
            source_path=path,
            format_id=format_id,
            objects=objects,
            selected_object_id=selected,
            requires_selection=len(objects) > 1 and not options.selected_object,
            size_bytes=stats.size_bytes,
            size_class=self.policy.classify_size(stats.size_bytes),
            warnings=self.policy.warnings_for_size(stats.size_bytes),
        )

    def _single_object_scan(
        self,
        path: Path,
        format_id: str,
        item: SelectableObject,
        stats: SourceStats,
    ) -> SourceScanResult:
        return SourceScanResult(
            source_path=path,
            format_id=format_id,
            objects=(item,),
            selected_object_id=item.object_id,
            requires_selection=False,
            size_bytes=stats.size_bytes,
            size_class=self.policy.classify_size(stats.size_bytes),
            warnings=self.policy.warnings_for_size(stats.size_bytes),
        )

    def _resolve_selected_object(
        self,
        scan: SourceScanResult,
        options: TabularLoadOptions,
    ) -> SelectableObject:
        selected_object_id = options.selected_object or scan.selected_object_id
        if scan.requires_selection and not selected_object_id:
            raise SelectionRequiredError(format_id=scan.format_id, choices=scan.objects)
        for item in scan.objects:
            if item.object_id == selected_object_id:
                if (
                    scan.format_id == "npz"
                    and scan.size_bytes > self.policy.large_warning_bytes
                    and not options.allow_npz_archive_preview
                ):
                    raise LargeDataMaterializationError(
                        "Large NPZ archives are treated as import/export archives; preview requires explicit opt-in.",
                        size_bytes=scan.size_bytes,
                    )
                return item
        raise SelectionRequiredError(format_id=scan.format_id, choices=scan.objects)

    def _build_table_record(
        self,
        scan: SourceScanResult,
        selected: SelectableObject,
        options: TabularLoadOptions,
    ) -> TableRecord:
        if scan.format_id in TEXT_FORMAT_IDS:
            delimiter = self._resolve_text_delimiter(scan.source_path, scan.format_id, options)
            columns = self._tabular_columns(self._text_columns(scan.source_path, options, delimiter), options)
            row_count = selected.row_count
        elif scan.format_id in EXCEL_FORMAT_IDS:
            columns, row_count = self._excel_columns(scan.source_path, selected.object_id, options)
        elif scan.format_id == "parquet":
            columns, row_count = self._parquet_columns(scan.source_path)
        elif scan.format_id == "hdf5":
            columns, row_count = self._hdf5_table_columns(scan.source_path, selected.object_id)
        else:
            raise UnsupportedTabularFormatError(scan.source_path)
        return TableRecord(
            source_path=scan.source_path,
            format_id=scan.format_id,
            options=options,
            object_id=selected.object_id,
            backend_id=self.policy.choose_table_backend(scan.format_id, scan.size_bytes),
            columns=columns,
            row_count=row_count,
            size_bytes=scan.size_bytes,
            warnings=scan.warnings,
            stats=self._source_stats(scan.source_path),
        )

    def _build_array_record(
        self,
        scan: SourceScanResult,
        selected: SelectableObject,
        options: TabularLoadOptions,
    ) -> ArrayRecord:
        shape = selected.shape
        dtype = selected.dtype
        if scan.format_id == "npz" and not shape:
            numpy = import_optional("numpy", format_id="npz", purpose="NPZ selected array metadata")
            with numpy.load(scan.source_path, allow_pickle=False) as archive:
                array = archive[selected.object_id]
                shape = tuple(int(value) for value in array.shape)
                dtype = str(array.dtype)
        return ArrayRecord(
            source_path=scan.source_path,
            format_id=scan.format_id,
            options=options,
            object_id=selected.object_id,
            backend_id=self.policy.choose_array_backend(scan.format_id, scan.size_bytes),
            shape=tuple(int(value) for value in shape),
            dtype=str(dtype),
            size_bytes=scan.size_bytes,
            warnings=scan.warnings,
            stats=self._source_stats(scan.source_path),
        )

    def _iter_all_table_records(self, record: TableRecord) -> Iterable[dict[str, Any]]:
        if record.format_id in TEXT_FORMAT_IDS:
            delimiter = self._resolve_text_delimiter(record.source_path, record.format_id, record.options)
            columns = tuple(column.name for column in record.columns)
            yield from self._iter_text_records(record.source_path, record.options, delimiter, columns)
            return
        if record.format_id in EXCEL_FORMAT_IDS:
            openpyxl = import_optional(
                "openpyxl",
                format_id=record.format_id,
                purpose="workbook query preview",
            )
            workbook = openpyxl.load_workbook(record.source_path, read_only=True, data_only=True)
            try:
                worksheet = workbook[record.object_id]
                columns = tuple(column.name for column in record.columns)
                yield from _worksheet_records(worksheet, record.options, columns)
            finally:
                workbook.close()
            return
        if record.format_id == "parquet":
            pq = import_optional("pyarrow.parquet", format_id="parquet", purpose="Parquet query preview")
            columns = [column.name for column in record.columns]
            parquet_file = pq.ParquetFile(record.source_path)
            for batch in parquet_file.iter_batches(batch_size=4096, columns=columns):
                for row in batch.to_pylist():
                    yield json_safe_mapping(row)
            return
        if record.format_id == "hdf5":
            h5py = import_optional("h5py", format_id="hdf5", purpose="HDF5 query preview")
            columns = tuple(column.name for column in record.columns)
            with h5py.File(record.source_path, "r") as handle:
                dataset = handle[record.object_id]
                total = int(dataset.shape[0]) if dataset.shape else 0
                for start in range(0, total, 4096):
                    chunk = dataset[start : min(start + 4096, total)]
                    for item in chunk:
                        yield {column: json_safe_value(item[column]) for column in columns}
            return
        raise UnsupportedTabularFormatError(record.source_path)

    def _iter_parquet_batches(
        self,
        record: TableRecord,
        options: TabularArrowBatchOptions,
        parquet_path: Path,
    ) -> Iterable[Any]:
        pq = import_optional("pyarrow.parquet", format_id="parquet", purpose="Arrow batch reads")
        columns = tuple(options.columns) if options.columns else tuple(column.name for column in record.columns)
        remaining_skip = options.row_offset
        remaining_take = options.row_limit
        with pq.ParquetFile(parquet_path) as parquet_file:
            for batch in parquet_file.iter_batches(batch_size=options.batch_size, columns=list(columns)):
                if remaining_skip >= batch.num_rows:
                    remaining_skip -= batch.num_rows
                    continue
                if remaining_skip:
                    batch = batch.slice(remaining_skip)
                    remaining_skip = 0
                if batch.num_rows > remaining_take:
                    batch = batch.slice(0, remaining_take)
                remaining_take -= batch.num_rows
                yield batch
                if remaining_take <= 0:
                    return

    def _read_text_window(self, record: TableRecord, request: TabularWindowRequest) -> TabularDataWindow:
        delimiter = self._resolve_text_delimiter(record.source_path, record.format_id, record.options)
        columns = tuple(column.name for column in record.columns)
        selected_columns = select_columns(columns, request)
        rows: list[dict[str, Any]] = []
        for row_index, row in enumerate(
            self._iter_text_records(record.source_path, record.options, delimiter, columns)
        ):
            if row_index < request.row_offset:
                continue
            rows.append({column: row.get(column) for column in selected_columns})
            if request.row_limit > 0 and len(rows) >= request.row_limit:
                break
        return TabularDataWindow(
            columns=selected_columns,
            rows=tuple(rows),
            row_offset=request.row_offset,
            column_offset=request.column_offset,
            total_rows=record.row_count,
            total_columns=len(columns),
            metadata=self._record_metadata(record.format_id, record.size_bytes, record.warnings),
        )

    def _read_excel_window(self, record: TableRecord, request: TabularWindowRequest) -> TabularDataWindow:
        openpyxl = import_optional("openpyxl", format_id=record.format_id, purpose="workbook preview")
        workbook = openpyxl.load_workbook(record.source_path, read_only=True, data_only=True)
        try:
            worksheet = workbook[record.object_id]
            columns = tuple(column.name for column in record.columns)
            selected_columns = select_columns(columns, request)
            rows: list[dict[str, Any]] = []
            for row_index, row in enumerate(_worksheet_records(worksheet, record.options, columns)):
                if row_index < request.row_offset:
                    continue
                rows.append({column: row.get(column) for column in selected_columns})
                if request.row_limit > 0 and len(rows) >= request.row_limit:
                    break
        finally:
            workbook.close()
        return TabularDataWindow(
            columns=selected_columns,
            rows=tuple(rows),
            row_offset=request.row_offset,
            column_offset=request.column_offset,
            total_rows=record.row_count,
            total_columns=len(columns),
            metadata=self._record_metadata(record.format_id, record.size_bytes, record.warnings),
        )

    def _read_parquet_window(
        self,
        record: TableRecord,
        request: TabularWindowRequest,
        *,
        parquet_path: Path | None = None,
    ) -> TabularDataWindow:
        return self._run_io(self._read_parquet_window_impl, record, request, parquet_path=parquet_path)

    def _read_parquet_window_impl(
        self,
        record: TableRecord,
        request: TabularWindowRequest,
        *,
        parquet_path: Path | None = None,
    ) -> TabularDataWindow:
        pq = import_optional("pyarrow.parquet", format_id="parquet", purpose="bounded Parquet preview")
        columns = tuple(column.name for column in record.columns)
        selected_columns = select_columns(columns, request)
        rows: list[dict[str, Any]] = []
        remaining_skip = request.row_offset
        remaining_take = request.row_limit
        with pq.ParquetFile(parquet_path or record.source_path) as parquet_file:
            row_groups = self._row_groups_for_window(parquet_file, request)
            if row_groups is not None:
                skipped_rows, group_indexes = row_groups
                remaining_skip -= skipped_rows
                batches = parquet_file.iter_batches(
                    batch_size=max(request.row_limit, 4096) if request.row_limit > 0 else 4096,
                    columns=list(selected_columns),
                    row_groups=group_indexes,
                )
            else:
                batches = parquet_file.iter_batches(
                    batch_size=max(request.row_limit, 4096) if request.row_limit > 0 else 4096,
                    columns=list(selected_columns),
                )
            for batch in batches:
                if remaining_skip >= batch.num_rows:
                    remaining_skip -= batch.num_rows
                    continue
                if remaining_skip:
                    batch = batch.slice(remaining_skip)
                    remaining_skip = 0
                if remaining_take > 0 and batch.num_rows > remaining_take:
                    batch = batch.slice(0, remaining_take)
                rows.extend(json_safe_mapping(row) for row in batch.to_pylist())
                if remaining_take > 0:
                    remaining_take -= batch.num_rows
                if request.row_limit > 0 and len(rows) >= request.row_limit:
                    break
        return TabularDataWindow(
            columns=selected_columns,
            rows=tuple(rows),
            row_offset=request.row_offset,
            column_offset=request.column_offset,
            total_rows=record.row_count,
            total_columns=len(columns),
            metadata=self._record_metadata(record.format_id, record.size_bytes, record.warnings),
        )

    @staticmethod
    def _row_groups_for_window(
        parquet_file: Any,
        request: TabularWindowRequest,
    ) -> tuple[int, list[int]] | None:
        if request.row_limit <= 0:
            return None
        try:
            metadata = parquet_file.metadata
            group_count = int(metadata.num_row_groups)
        except Exception:  # noqa: BLE001 - metadata access is best-effort
            return None
        if group_count <= 1:
            return None
        start = request.row_offset
        stop = request.row_offset + request.row_limit
        cursor = 0
        skipped = 0
        selected: list[int] = []
        for index in range(group_count):
            group_rows = int(metadata.row_group(index).num_rows)
            group_start = cursor
            group_stop = cursor + group_rows
            cursor = group_stop
            if group_stop <= start:
                skipped += group_rows
                continue
            if group_start >= stop:
                break
            selected.append(index)
        return (skipped, selected) if selected else (0, [])

    def _read_hdf5_table_window(
        self,
        record: TableRecord,
        request: TabularWindowRequest,
    ) -> TabularDataWindow:
        h5py = import_optional("h5py", format_id="hdf5", purpose="bounded HDF5 table preview")
        columns = tuple(column.name for column in record.columns)
        selected_columns = select_columns(columns, request)
        rows: list[dict[str, Any]] = []
        with h5py.File(record.source_path, "r") as handle:
            dataset = handle[record.object_id]
            stop = (
                int(dataset.shape[0])
                if request.row_limit == 0
                else min(request.row_offset + request.row_limit, dataset.shape[0])
            )
            for item in dataset[request.row_offset:stop]:
                rows.append({column: json_safe_value(item[column]) for column in selected_columns})
        return TabularDataWindow(
            columns=selected_columns,
            rows=tuple(rows),
            row_offset=request.row_offset,
            column_offset=request.column_offset,
            total_rows=record.row_count,
            total_columns=len(columns),
            metadata=self._record_metadata(record.format_id, record.size_bytes, record.warnings),
        )

    def _read_array_slice(
        self,
        record: ArrayRecord,
        request: ArraySlice2DRequest,
    ) -> tuple[tuple[Any, ...], ...]:
        return _array_values_to_rows(_slice_array_2d(self._open_array(record), request))

    def _read_array_materialized(
        self,
        record: ArrayRecord,
        options: ArrayMaterializationOptions,
    ) -> Any:
        array = self._open_array(record)
        if options.slices:
            slices = tuple(slice(offset, offset + limit) for offset, limit in options.slices)
            return array[slices]
        if options.max_elements is not None:
            return array.reshape(-1)[: options.max_elements]
        return array[:]

    def _open_array(self, record: ArrayRecord) -> Any:
        numpy = import_optional("numpy", format_id=record.format_id, purpose="array preview")
        if record.format_id == "npy":
            return numpy.load(record.source_path, mmap_mode="r", allow_pickle=False)
        if record.format_id == "npz":
            if record.size_bytes > self.policy.large_warning_bytes and not record.options.allow_npz_archive_preview:
                raise LargeDataMaterializationError(
                    "Large NPZ archives require explicit preview opt-in.",
                    size_bytes=record.size_bytes,
                )
            archive = numpy.load(record.source_path, allow_pickle=False)
            return archive[record.object_id]
        if record.format_id == "hdf5":
            h5py = import_optional("h5py", format_id="hdf5", purpose="HDF5 array preview")
            return _Hdf5ArrayHandle(h5py.File(record.source_path, "r"), record.object_id)
        raise UnsupportedTabularFormatError(record.source_path)

    def _write_parquet_cache(
        self,
        source_path: Path,
        options: TabularLoadOptions,
        cache_path: Path,
    ) -> None:
        format_id = detect_format_id(source_path)
        if format_id == "parquet":
            _copy_file(source_path, cache_path)
            return
        if format_id in TEXT_FORMAT_IDS:
            self._write_text_parquet_cache(source_path, format_id, options, cache_path)
            return
        if format_id in EXCEL_FORMAT_IDS:
            self._write_excel_parquet_cache(source_path, format_id, options, cache_path)
            return
        raise UnsupportedTabularFormatError(source_path)

    def _write_text_parquet_cache(
        self,
        source_path: Path,
        format_id: str,
        options: TabularLoadOptions,
        cache_path: Path,
    ) -> None:
        delimiter = self._resolve_text_delimiter(source_path, format_id, options)
        columns = self._text_columns(source_path, options, delimiter)
        try:
            self._write_text_parquet_cache_arrow(source_path, options, cache_path, delimiter, columns)
        except MissingTabularDependencyError:
            raise
        except Exception:  # noqa: BLE001 - exotic inputs use the Python csv fallback
            if cache_path.exists():
                try:
                    cache_path.unlink()
                except OSError:
                    pass
            self._write_text_parquet_cache_python(source_path, options, cache_path, delimiter, columns)

    _ARROW_CSV_BLOCK_BYTES = 32 * 1024 * 1024
    _NEWLINE_SAFE_ENCODINGS = frozenset(
        {"utf-8", "utf8", "utf-8-sig", "ascii", "latin-1", "latin1", "iso-8859-1", "cp1252"}
    )

    def _write_text_parquet_cache_arrow(
        self,
        source_path: Path,
        options: TabularLoadOptions,
        cache_path: Path,
        delimiter: str,
        columns: tuple[str, ...],
    ) -> None:
        """Convert line-aligned blocks with read_csv; open_csv is unsafe with QML on Windows."""

        pyarrow = import_optional("pyarrow", format_id="parquet_cache", purpose="managed text-to-Parquet cache")
        pa_csv = import_optional("pyarrow.csv", format_id="parquet_cache", purpose="managed text-to-Parquet cache")
        pq = import_optional("pyarrow.parquet", format_id="parquet_cache", purpose="managed text-to-Parquet cache")
        if str(options.encoding).strip().lower() not in self._NEWLINE_SAFE_ENCODINGS:
            raise ValueError(
                f"chunked arrow csv conversion requires a newline-safe encoding, got {options.encoding!r}"
            )

        skip_rows = options.skip_rows + (options.header_row + 1 if options.header_row is not None else 0)
        parse_options = pa_csv.ParseOptions(delimiter=delimiter)
        column_types: dict[str, Any] = {}
        for name in columns:
            hint = options.schema_hints.get(name, "")
            if not hint:
                continue
            try:
                column_types[name] = pyarrow.type_for_alias(hint)
            except (KeyError, ValueError):
                continue

        def read_block(block: bytes) -> Any:
            read_options = pa_csv.ReadOptions(encoding=options.encoding, column_names=list(columns))
            convert_options = pa_csv.ConvertOptions(column_types=column_types) if column_types else None
            return pa_csv.read_csv(
                pyarrow.BufferReader(block),
                read_options=read_options,
                parse_options=parse_options,
                convert_options=convert_options,
            )

        writer = None
        schema = None
        try:
            for block in self._iter_line_aligned_blocks(source_path, skip_rows=skip_rows):
                table = read_block(block)
                if writer is None:
                    schema = table.schema
                    column_types.update({field.name: field.type for field in schema})
                    writer = pq.ParquetWriter(cache_path, schema)
                elif table.schema != schema:
                    table = table.cast(schema)
                writer.write_table(table)
            if writer is None:
                table = pyarrow.Table.from_pylist(
                    [],
                    schema=pyarrow.schema([(name, pyarrow.string()) for name in columns]),
                )
                pq.write_table(table, cache_path)
        finally:
            if writer is not None:
                writer.close()

    @classmethod
    def _iter_line_aligned_blocks(cls, source_path: Path, *, skip_rows: int) -> Iterable[bytes]:
        with source_path.open("rb") as handle:
            for _ in range(skip_rows):
                if not handle.readline():
                    return
            remainder = b""
            while True:
                block = handle.read(cls._ARROW_CSV_BLOCK_BYTES)
                if not block:
                    if remainder.strip():
                        yield remainder
                    return
                block = remainder + block
                cut = block.rfind(b"\n")
                while cut < 0:
                    extra = handle.read(cls._ARROW_CSV_BLOCK_BYTES)
                    if not extra:
                        break
                    block += extra
                    cut = block.rfind(b"\n")
                if cut < 0:
                    if block.strip():
                        yield block
                    return
                payload, remainder = block[: cut + 1], block[cut + 1 :]
                if payload.strip():
                    yield payload

    def _write_text_parquet_cache_python(
        self,
        source_path: Path,
        options: TabularLoadOptions,
        cache_path: Path,
        delimiter: str,
        columns: tuple[str, ...],
    ) -> None:
        pyarrow = import_optional("pyarrow", format_id="parquet_cache", purpose="managed text-to-Parquet cache")
        pq = import_optional("pyarrow.parquet", format_id="parquet_cache", purpose="managed text-to-Parquet cache")
        writer = None
        batch_rows: list[dict[str, Any]] = []
        try:
            for row in self._iter_text_records(source_path, options, delimiter, columns):
                batch_rows.append(row)
                if len(batch_rows) >= 4096:
                    writer = _write_parquet_batch(
                        pq,
                        writer,
                        cache_path,
                        pyarrow.Table.from_pylist(batch_rows, schema=None),
                    )
                    batch_rows = []
            if batch_rows:
                writer = _write_parquet_batch(
                    pq,
                    writer,
                    cache_path,
                    pyarrow.Table.from_pylist(batch_rows, schema=None),
                )
            if writer is None:
                pq.write_table(
                    pyarrow.Table.from_pylist(
                        [],
                        schema=pyarrow.schema([(name, pyarrow.string()) for name in columns]),
                    ),
                    cache_path,
                )
        finally:
            if writer is not None:
                writer.close()

    def _write_excel_parquet_cache(
        self,
        source_path: Path,
        format_id: str,
        options: TabularLoadOptions,
        cache_path: Path,
    ) -> None:
        pyarrow = import_optional("pyarrow", format_id="parquet_cache", purpose="managed Excel-to-Parquet cache")
        pq = import_optional("pyarrow.parquet", format_id="parquet_cache", purpose="managed Excel-to-Parquet cache")
        selected = options.selected_object
        if not selected:
            selected = self._resolve_selected_object(self.scan_source(source_path, options), options).object_id
        openpyxl = import_optional("openpyxl", format_id=format_id, purpose="workbook cache conversion")
        workbook = openpyxl.load_workbook(source_path, read_only=True, data_only=True)
        writer = None
        batch_rows: list[dict[str, Any]] = []
        try:
            worksheet = workbook[selected]
            columns, _row_count = self._excel_columns(source_path, selected, options)
            names = tuple(column.name for column in columns)
            for row in _worksheet_records(worksheet, options, names):
                batch_rows.append(row)
                if len(batch_rows) >= 4096:
                    writer = _write_parquet_batch(
                        pq,
                        writer,
                        cache_path,
                        pyarrow.Table.from_pylist(batch_rows, schema=None),
                    )
                    batch_rows = []
            if batch_rows:
                writer = _write_parquet_batch(
                    pq,
                    writer,
                    cache_path,
                    pyarrow.Table.from_pylist(batch_rows, schema=None),
                )
            if writer is None:
                pq.write_table(
                    pyarrow.Table.from_pylist(
                        [],
                        schema=pyarrow.schema([(name, pyarrow.string()) for name in names]),
                    ),
                    cache_path,
                )
        finally:
            workbook.close()
            if writer is not None:
                writer.close()

    def _resolve_text_delimiter(
        self,
        path: Path,
        format_id: str,
        options: TabularLoadOptions,
    ) -> str:
        if options.delimiter:
            return options.delimiter
        if format_id == "tsv":
            return "\t"
        if format_id == "csv":
            return ","
        try:
            with path.open("r", encoding=options.encoding, errors="replace") as handle:
                sample = handle.read(4096)
            return csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
        except Exception:
            return "\t" if path.suffix.lower() == ".tsv" else ","

    def _text_columns(
        self,
        path: Path,
        options: TabularLoadOptions,
        delimiter: str,
    ) -> tuple[str, ...]:
        with path.open("r", encoding=options.encoding, newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            for _ in range(options.skip_rows):
                next(reader, None)
            if options.header_row is None:
                return _generated_columns(len(next(reader, [])))
            for _ in range(options.header_row):
                next(reader, None)
            return _normalize_column_names(next(reader, []))

    def _iter_text_records(
        self,
        path: Path,
        options: TabularLoadOptions,
        delimiter: str,
        columns: Sequence[str],
    ) -> Iterable[dict[str, Any]]:
        with path.open("r", encoding=options.encoding, newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            for _ in range(options.skip_rows):
                next(reader, None)
            if options.header_row is None:
                first_row = next(reader, None)
                if first_row is not None:
                    yield _row_to_mapping(columns, first_row)
            else:
                for _ in range(options.header_row):
                    next(reader, None)
                next(reader, None)
            for row in reader:
                yield _row_to_mapping(columns, row)

    def _excel_columns(
        self,
        path: Path,
        sheet_name: str,
        options: TabularLoadOptions,
    ) -> tuple[tuple[TabularColumn, ...], int | None]:
        openpyxl = import_optional("openpyxl", format_id=detect_format_id(path), purpose="workbook schema")
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            worksheet = workbook[sheet_name]
            return (
                self._tabular_columns(_worksheet_columns(worksheet, options), options),
                _excel_data_row_count(worksheet, options),
            )
        finally:
            workbook.close()

    def _parquet_columns(self, path: Path) -> tuple[tuple[TabularColumn, ...], int | None]:
        pq = import_optional("pyarrow.parquet", format_id="parquet", purpose="Parquet schema")

        def read_schema() -> tuple[tuple[TabularColumn, ...], int]:
            with pq.ParquetFile(path) as parquet_file:
                schema = parquet_file.schema_arrow
                columns = tuple(
                    TabularColumn(field.name, str(field.type), field.nullable)
                    for field in schema
                )
                return columns, int(parquet_file.metadata.num_rows)

        return self._run_io(read_schema)

    def _hdf5_table_columns(
        self,
        path: Path,
        object_id: str,
    ) -> tuple[tuple[TabularColumn, ...], int | None]:
        h5py = import_optional("h5py", format_id="hdf5", purpose="HDF5 table schema")
        with h5py.File(path, "r") as handle:
            dataset = handle[object_id]
            names = tuple(dataset.dtype.names or ())
            columns = tuple(TabularColumn(name, str(dataset.dtype.fields[name][0])) for name in names)
            row_count = int(dataset.shape[0]) if dataset.shape else None
            return columns, row_count

    @staticmethod
    def _tabular_columns(
        names: Sequence[str],
        options: TabularLoadOptions,
    ) -> tuple[TabularColumn, ...]:
        return tuple(TabularColumn(name, options.schema_hints.get(name, ""), True) for name in names)


class _Hdf5ArrayHandle:
    def __init__(self, handle: Any, object_id: str) -> None:
        self._handle = handle
        self._dataset = handle[object_id]

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self._dataset.shape)

    def __getitem__(self, item: Any) -> Any:
        try:
            return self._dataset[item]
        finally:
            self._handle.close()


def detect_format_id(path: Path | str | os.PathLike[str]) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in HDF5_SUFFIXES:
        return "hdf5"
    format_id = suffix.lstrip(".")
    if format_id not in SUPPORTED_FORMAT_IDS:
        raise UnsupportedTabularFormatError(Path(path))
    return format_id


def supported_format_ids() -> tuple[str, ...]:
    return SUPPORTED_FORMAT_IDS


def coerce_options(
    options: TabularLoadOptions | Mapping[str, Any] | None,
) -> TabularLoadOptions:
    return options if isinstance(options, TabularLoadOptions) else TabularLoadOptions.from_mapping(options)


def import_optional(module_name: str, *, format_id: str, purpose: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        missing_name = exc.name or module_name
        if missing_name == module_name or module_name.startswith(f"{missing_name}."):
            raise MissingTabularDependencyError(
                format_id=format_id,
                dependency=missing_name,
                purpose=purpose,
            ) from exc
        raise


def select_columns(
    columns: Sequence[str],
    request: TabularWindowRequest,
) -> tuple[str, ...]:
    available = tuple(columns)
    if request.columns:
        selected = tuple(column for column in request.columns if column in available)
        return selected if request.column_limit == 0 else selected[: request.column_limit]
    if request.column_limit == 0:
        return available[request.column_offset:]
    return available[request.column_offset : request.column_offset + request.column_limit]


def json_safe_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): json_safe_value(value) for key, value in payload.items()}


def json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "item"):
        return json_safe_value(value.item())
    if isinstance(value, Mapping):
        return json_safe_mapping(value)
    if isinstance(value, (list, tuple)):
        return [json_safe_value(item) for item in value]
    return str(value)


def _normalize_optional_non_negative_int(field_name: str, value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be an integer") from exc
    if normalized < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return normalized


def _normalize_non_negative_int(field_name: str, value: Any) -> int:
    normalized = _normalize_optional_non_negative_int(field_name, value)
    if normalized is None:
        raise ValueError(f"{field_name} must be an integer")
    return normalized


def _normalize_column_names(values: Sequence[Any]) -> tuple[str, ...]:
    names: list[str] = []
    seen: dict[str, int] = {}
    for index, value in enumerate(values):
        base = str(value).strip() if value is not None else ""
        if not base:
            base = f"column_{index + 1}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        names.append(base if count == 1 else f"{base}_{count}")
    return tuple(names)


def _generated_columns(count: int) -> tuple[str, ...]:
    return tuple(f"column_{index + 1}" for index in range(max(0, int(count))))


def _row_to_mapping(columns: Sequence[str], values: Sequence[Any]) -> dict[str, Any]:
    return {
        column: json_safe_value(values[index] if index < len(values) else None)
        for index, column in enumerate(columns)
    }


def _worksheet_columns(worksheet: Any, options: TabularLoadOptions) -> tuple[str, ...]:
    rows = worksheet.iter_rows(values_only=True)
    for _ in range(options.skip_rows):
        next(rows, None)
    if options.header_row is None:
        return _generated_columns(len(next(rows, None) or ()))
    for _ in range(options.header_row):
        next(rows, None)
    return _normalize_column_names(next(rows, None) or ())


def _worksheet_records(
    worksheet: Any,
    options: TabularLoadOptions,
    columns: Sequence[str],
) -> Iterable[dict[str, Any]]:
    rows = worksheet.iter_rows(values_only=True)
    for _ in range(options.skip_rows):
        next(rows, None)
    if options.header_row is None:
        first_row = next(rows, None)
        if first_row is not None:
            yield _row_to_mapping(columns, first_row)
    else:
        for _ in range(options.header_row):
            next(rows, None)
        next(rows, None)
    for row in rows:
        yield _row_to_mapping(columns, row)


def _excel_data_row_count(worksheet: Any, options: TabularLoadOptions) -> int | None:
    max_row = worksheet.max_row
    if max_row is None:
        return None
    header_rows = 0 if options.header_row is None else options.header_row + 1
    return max(0, int(max_row) - options.skip_rows - header_rows)


def _slice_array_2d(array: Any, request: ArraySlice2DRequest) -> Any:
    shape = tuple(int(value) for value in getattr(array, "shape", ()))
    row_stop = None if request.row_limit == 0 else request.row_offset + request.row_limit
    column_stop = None if request.column_limit == 0 else request.column_offset + request.column_limit
    if len(shape) == 0:
        return [[array[()]]]
    if len(shape) == 1:
        return array[request.row_offset:row_stop]
    base = (
        slice(request.row_offset, row_stop),
        slice(request.column_offset, column_stop),
    )
    if len(shape) > 2:
        base = base + tuple(0 for _ in shape[2:])
    return array[base]


def _array_values_to_rows(values: Any) -> tuple[tuple[Any, ...], ...]:
    shape = tuple(int(value) for value in getattr(values, "shape", ()))
    if len(shape) == 0:
        return ((json_safe_value(values.item() if hasattr(values, "item") else values),),)
    if len(shape) == 1:
        return tuple((json_safe_value(value),) for value in values.tolist())
    return tuple(tuple(json_safe_value(value) for value in row) for row in values.tolist())


def _copy_file(source_path: Path, cache_path: Path) -> None:
    import shutil

    shutil.copy2(source_path, cache_path)


def _write_parquet_batch(pq: Any, writer: Any, cache_path: Path, table: Any) -> Any:
    if writer is None:
        writer = pq.ParquetWriter(cache_path, table.schema)
    writer.write_table(table)
    return writer


__all__ = [
    "ARRAY_FORMAT_IDS",
    "EXCEL_FORMAT_IDS",
    "HDF5_SUFFIXES",
    "LargeDataMaterializationError",
    "MissingTabularDependencyError",
    "SUPPORTED_FORMAT_IDS",
    "SelectableObject",
    "SelectionRequiredError",
    "SourceBackendMethods",
    "SourceScanResult",
    "SourceStats",
    "TEXT_FORMAT_IDS",
    "TabularCacheNotReadyError",
    "TabularLoadOptions",
    "TabularLoaderError",
    "UnsupportedTabularFormatError",
    "coerce_options",
    "detect_format_id",
    "import_optional",
    "json_safe_mapping",
    "json_safe_value",
    "select_columns",
    "supported_format_ids",
]
