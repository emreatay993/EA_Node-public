# Purpose: Coordinate Tabular refs, shared records, query-table reuse, conversion locks, and cache eviction.
# Map: feature_routes/tabular_data_addon_preview
# Tests: tests/test_tabular_cache_service.py
# Landmarks: TabularLoaderCacheService, ParquetCacheKey, ParquetCacheEntry
from __future__ import annotations

import hashlib
import importlib
import json
import os
import queue
import sys
import threading
from urllib.parse import urlparse
from urllib.request import url2pathname
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ea_node_editor.common.payload_tools import REF_METADATA_MAX_BYTES
from ea_node_editor.addons.tabular_data.policy import DEFAULT_TABULAR_BACKEND_POLICY, TabularBackendPolicy
from ea_node_editor.addons.tabular_data.preview_query import (
    NormalizedPreviewQuery,
    evaluate_arrow_query,
    evaluate_python_query,
)
from ea_node_editor.addons.tabular_data.source_backends import (
    ARRAY_FORMAT_IDS,
    EXCEL_FORMAT_IDS,
    HDF5_SUFFIXES,
    SUPPORTED_FORMAT_IDS,
    TEXT_FORMAT_IDS,
    ArrayRecord as _ArrayRecord,
    LargeDataMaterializationError,
    MissingTabularDependencyError,
    SelectableObject,
    SelectionRequiredError,
    SourceBackendMethods,
    SourceScanResult,
    SourceStats,
    TableRecord as _TableRecord,
    TabularCacheNotReadyError,
    TabularLoadOptions,
    TabularLoaderError,
    UnsupportedTabularFormatError,
    coerce_options as _coerce_options,
    detect_format_id,
    import_optional as _import_optional,
    json_safe_mapping as _json_safe_mapping,
    select_columns as _select_columns,
    supported_format_ids,
)
from ea_node_editor.runtime_contracts import (
    ArrayDataRef,
    ArrayMaterializationOptions,
    ArraySlice2D,
    ArraySlice2DRequest,
    TabularArrowBatchOptions,
    TabularColumn,
    TabularDataRef,
    TabularDataWindow,
    TabularMaterializationOptions,
    TabularSchema,
    TabularWindowRequest,
)
from ea_node_editor.settings import (
    TABULAR_DATA_CACHE_MAX_BYTES,
    TABULAR_DATA_INLINE_CONVERSION_BYTES,
    tabular_data_cache_dir,
)

def _preload_native_tabular_runtime() -> None:
    """Eagerly load every pyarrow native submodule used by this service.

    Lazily importing additional pyarrow extension DLLs (pyarrow.dataset via
    read_table, pyarrow._fs via ParquetWriter, ...) after a Qt Quick engine
    has run access-violates on Windows (observed with pyarrow 24.0 + PyQt6:
    the DLL static initializers corrupt the process and the next native call
    crashes). This module imports at registry build time — before any QML
    engine exists — so preloading here makes all later use safe. Best-effort:
    environments without the optional dependency keep working and report it
    through the normal _import_optional path.
    """

    if _running_in_pyinstaller_build_analysis():
        return

    for module_name in (
        "pyarrow",
        "pyarrow.compute",
        "pyarrow.csv",
        "pyarrow.dataset",
        "pyarrow.fs",
        "pyarrow.parquet",
    ):
        try:
            importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 - optional dependency may be absent
            return


def _running_in_pyinstaller_build_analysis() -> bool:
    """Return true while PyInstaller's isolated analysis child imports app modules."""

    return any(name == "PyInstaller" or name.startswith("PyInstaller.") for name in sys.modules)


_preload_native_tabular_runtime()

TABULAR_CACHE_RESOLVER_ID = "tabular.cache"
# Sort/filter/search previews must scan the source to be correct, but a preview
# must stay responsive. Cap the rows scanned per query and report truncation so
# the surface can tell the user results are limited to the first N source rows.
PREVIEW_QUERY_SCAN_ROW_CAP = 200_000


@dataclass(slots=True, frozen=True)
class ParquetCacheKey:
    key: str
    payload: Mapping[str, Any]


@dataclass(slots=True, frozen=True)
class ParquetCacheEntry:
    key: str
    cache_path: Path
    metadata_path: Path
    metadata: Mapping[str, Any]


_SCAN_CACHE_LIMIT = 64

# Native parquet/duckdb calls need more stack than the UI thread has left when
# graph-scene payload sync runs deep inside QML engine frames (observed access
# violations constructing ParquetWriter/ParquetFile there). Heavy reads and
# conversions therefore dispatch to this worker pool when invoked on the main
# thread; callers block on the result, so synchronous semantics are unchanged.
_io_executor_guard = threading.Lock()
_io_executor: Any = None


def _tabular_io_executor() -> Any:
    global _io_executor
    with _io_executor_guard:
        if _io_executor is None:
            from concurrent.futures import ThreadPoolExecutor

            _io_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tabular-io")
        return _io_executor


class TabularLoaderCacheService(SourceBackendMethods):
    resolver_id = TABULAR_CACHE_RESOLVER_ID

    def __init__(
        self,
        *,
        cache_dir: Path | str | os.PathLike[str] | None = None,
        policy: TabularBackendPolicy = DEFAULT_TABULAR_BACKEND_POLICY,
    ) -> None:
        self.policy = policy
        self.cache_dir = Path(cache_dir) if cache_dir is not None else tabular_data_cache_dir()
        self._table_records: dict[str, _TableRecord] = {}
        self._array_records: dict[str, _ArrayRecord] = {}
        self._records_lock = threading.RLock()
        self._scan_cache: dict[str, SourceScanResult] = {}
        self._query_table_cache: dict[str, Any] | None = None
        self._conversion_locks: dict[str, threading.Lock] = {}
        self._conversion_locks_guard = threading.Lock()
        # Until async preview surfaces exist, interactive callers may convert
        # inline on the UI thread; the async preview layer flips this off so
        # large conversions always happen on workers.
        self.ui_thread_conversion_allowed = True

    def scan_source(
        self,
        source_path: Path | str | os.PathLike[str],
        options: TabularLoadOptions | Mapping[str, Any] | None = None,
    ) -> SourceScanResult:
        normalized_options = _coerce_options(options)
        path = self._resolve_path(source_path)
        format_id = detect_format_id(path)
        stats = self._source_stats(path)
        cache_key = json.dumps(
            {
                "path": str(path),
                "mtime_ns": stats.mtime_ns,
                "size": stats.size_bytes,
                "options": normalized_options.to_cache_payload(),
                "policy": self.policy.revision,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._records_lock:
            cached = self._scan_cache.get(cache_key)
        if cached is not None:
            return cached
        scan = self._scan_uncached(path, format_id, normalized_options, stats)
        with self._records_lock:
            if cache_key not in self._scan_cache and len(self._scan_cache) >= _SCAN_CACHE_LIMIT:
                self._scan_cache.pop(next(iter(self._scan_cache)), None)
            self._scan_cache[cache_key] = scan
        return scan

    def _scan_uncached(
        self,
        path: Path,
        format_id: str,
        normalized_options: TabularLoadOptions,
        stats: SourceStats,
    ) -> SourceScanResult:
        if format_id in TEXT_FORMAT_IDS:
            return self._scan_text(path, format_id, normalized_options, stats)
        if format_id in EXCEL_FORMAT_IDS:
            return self._scan_excel(path, format_id, normalized_options, stats)
        if format_id == "parquet":
            return self._scan_parquet(path, normalized_options, stats)
        if format_id == "hdf5":
            return self._scan_hdf5(path, normalized_options, stats)
        if format_id == "npy":
            return self._scan_npy(path, normalized_options, stats)
        if format_id == "npz":
            return self._scan_npz(path, normalized_options, stats)
        raise UnsupportedTabularFormatError(path)

    def open_source(
        self,
        source_path: Path | str | os.PathLike[str],
        options: TabularLoadOptions | Mapping[str, Any] | None = None,
    ) -> TabularDataRef | ArrayDataRef:
        normalized_options = _coerce_options(options)
        scan = self.scan_source(source_path, normalized_options)
        selected = self._resolve_selected_object(scan, normalized_options)
        options_with_selection = normalized_options.with_selected_object(selected.object_id)
        if selected.kind == "table":
            record = self._build_table_record(scan, selected, options_with_selection)
            ref_id = self._ref_id("table", record)
            with self._records_lock:
                existing = self._table_records.get(ref_id)
                if existing is not None and existing.row_count is not None and record.row_count is None:
                    record = existing
                self._table_records[ref_id] = record
            metadata = self._record_metadata(
                record.format_id, record.size_bytes, record.warnings, options=record.options,
            )
            metadata["column_schema"] = [{"name": column.name, "dtype": column.dtype} for column in record.columns]
            if len(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > REF_METADATA_MAX_BYTES:
                del metadata["column_schema"]
            return TabularDataRef(
                ref_id=ref_id,
                resolver_id=self.resolver_id,
                backend_id=record.backend_id,
                source_uri=_path_uri(record.source_path),
                object_id=record.object_id,
                row_count=record.row_count,
                column_count=len(record.columns),
                metadata=metadata,
            )
        record = self._build_array_record(scan, selected, options_with_selection)
        ref_id = self._ref_id("array", record)
        with self._records_lock:
            self._array_records[ref_id] = record
        return ArrayDataRef(
            ref_id=ref_id,
            resolver_id=self.resolver_id,
            backend_id=record.backend_id,
            source_uri=_path_uri(record.source_path),
            object_id=record.object_id,
            shape=record.shape,
            dtype=record.dtype,
            metadata=self._record_metadata(
                record.format_id,
                record.size_bytes,
                record.warnings,
                options=record.options,
            ),
        )

    def ensure_ref_open(self, ref: TabularDataRef | ArrayDataRef) -> TabularDataRef | ArrayDataRef:
        if isinstance(ref, TabularDataRef):
            return self.ensure_table_ref(ref)
        return self.ensure_array_ref(ref)

    def ensure_table_ref(self, ref: TabularDataRef) -> TabularDataRef:
        with self._records_lock:
            record = self._table_records.get(ref.ref_id)
            if record is not None and self._record_source_is_current(record):
                return ref
        reopened = self.open_source(_source_path_from_ref(ref), _load_options_from_ref(ref))
        if not isinstance(reopened, TabularDataRef):
            raise TypeError("tabular ref reopened as an array source")
        if reopened.ref_id != ref.ref_id:
            with self._records_lock:
                self._table_records[ref.ref_id] = self._table_records[reopened.ref_id]
        return ref

    def ensure_array_ref(self, ref: ArrayDataRef) -> ArrayDataRef:
        with self._records_lock:
            record = self._array_records.get(ref.ref_id)
            if record is not None and self._record_source_is_current(record):
                return ref
        reopened = self.open_source(_source_path_from_ref(ref), _load_options_from_ref(ref))
        if not isinstance(reopened, ArrayDataRef):
            raise TypeError("array ref reopened as a table source")
        if reopened.ref_id != ref.ref_id:
            with self._records_lock:
                self._array_records[ref.ref_id] = self._array_records[reopened.ref_id]
        return ref

    def schema(self, ref: TabularDataRef) -> TabularSchema:
        self.ensure_table_ref(ref)
        record = self._table_record(ref)
        if (
            record.row_count is None
            and (record.format_id in TEXT_FORMAT_IDS or record.format_id in EXCEL_FORMAT_IDS)
            and record.options.uses_managed_cache
        ):
            cached_count = self._cached_parquet_row_count(record.source_path, record.options)
            if cached_count is not None:
                updated = replace(record, row_count=cached_count)
                with self._records_lock:
                    for ref_id, existing in list(self._table_records.items()):
                        if existing is record:
                            self._table_records[ref_id] = updated
                record = updated
        return TabularSchema(
            columns=record.columns,
            row_count=record.row_count,
            metadata=self._record_metadata(
                record.format_id,
                record.size_bytes,
                record.warnings,
                options=record.options,
            ),
        )

    def column_schema(self, ref: TabularDataRef) -> TabularSchema:
        """Prepare typed execution metadata, including managed-cache inference.

        This may perform source IO/conversion; UI projections must use cached
        metadata instead. Direct-source columns may still have unknown dtypes.
        """
        self.ensure_table_ref(ref)
        record = self._table_record(ref)
        if (
            any(not column.dtype for column in record.columns)
            and record.format_id in TEXT_FORMAT_IDS | EXCEL_FORMAT_IDS
            and record.options.uses_managed_cache
        ):
            self._ensure_record_parquet_cache(ref, record)
        return self.schema(ref)

    def column_arrays(
        self,
        ref: TabularDataRef,
        *,
        columns: Sequence[str | int],
        row_offset: int = 0,
        row_limit: int | None = None,
    ) -> dict[str | int, Any]:
        """Load selected, aligned columns without row dictionaries on Arrow paths."""
        np = _import_optional("numpy", format_id="numpy", purpose="column materialization")
        chunks: dict[str | int, list[Any]] = {key: [] for key in columns}
        if not chunks:
            return {}
        schema_names = tuple(column.name for column in self.schema(ref).columns)
        requested = {}
        for key in columns:
            if type(key) is int:
                if not 0 <= key < len(schema_names):
                    raise ValueError("Column position is outside the table schema")
                name = schema_names[key]
                requested[key] = (name, schema_names[:key].count(name))
            else:
                requested[key] = (key, -1)
        options = TabularArrowBatchOptions(
            row_limit=row_limit if row_limit and row_limit > 0 else 2_147_483_647,
            batch_size=65_536,
            row_offset=row_offset,
            columns=tuple(dict.fromkeys(name for name, _ in requested.values())),
        )
        for batch in self.arrow_batches(ref, options):
            if isinstance(batch, list):
                for key, (name, _) in requested.items():
                    chunks[key].append(np.array([row.get(name) for row in batch], dtype=object))
                continue
            name_to_indexes: dict[str, list[int]] = {}
            for index, name in enumerate(batch.schema.names):
                name_to_indexes.setdefault(name, []).append(index)
            for key, (name, occurrence) in requested.items():
                indexes = name_to_indexes.get(name, [])
                index = indexes[occurrence] if indexes else None
                chunks[key].append(
                    np.full(batch.num_rows, None, dtype=object)
                    if index is None else batch.column(index).to_numpy(zero_copy_only=False)
                )
        return {
            name: np.array([], dtype=object) if not parts else parts[0] if len(parts) == 1 else np.concatenate(parts)
            for name, parts in chunks.items()
        }

    def metadata(self, ref: TabularDataRef | ArrayDataRef) -> Mapping[str, Any]:
        if isinstance(ref, TabularDataRef):
            self.ensure_table_ref(ref)
            record = self._table_record(ref)
            payload = self._record_metadata(
                record.format_id,
                record.size_bytes,
                record.warnings,
                options=record.options,
            )
            payload["row_count"] = record.row_count
            payload["column_count"] = len(record.columns)
            return payload
        self.ensure_array_ref(ref)
        record = self._array_record(ref)
        payload = self._record_metadata(
            record.format_id,
            record.size_bytes,
            record.warnings,
            options=record.options,
        )
        payload["shape"] = list(record.shape)
        payload["dtype"] = record.dtype
        return payload

    def window(self, ref: TabularDataRef, request: TabularWindowRequest) -> TabularDataWindow:
        self.ensure_table_ref(ref)
        record = self._table_record(ref)
        if record.format_id in TEXT_FORMAT_IDS or record.format_id in EXCEL_FORMAT_IDS:
            if record.options.uses_managed_cache:
                entry = self._ensure_record_parquet_cache(ref, record)
                record = self._table_record(ref)
                return self._read_parquet_window(record, request, parquet_path=entry.cache_path)
            if record.format_id in TEXT_FORMAT_IDS:
                return self._read_text_window(record, request)
            return self._read_excel_window(record, request)
        if record.format_id == "parquet":
            return self._read_parquet_window(record, request)
        if record.format_id == "hdf5":
            return self._read_hdf5_table_window(record, request)
        raise UnsupportedTabularFormatError(record.source_path)

    def preview_window(self, ref: TabularDataRef, request: Mapping[str, Any]) -> TabularDataWindow:
        self.ensure_table_ref(ref)
        record = self._table_record(ref)
        all_columns = tuple(column.name for column in record.columns)
        query = NormalizedPreviewQuery.from_mapping(request, all_columns)

        if query.selected_columns:
            parquet_path: Path | None = None
            if record.format_id == "parquet":
                parquet_path = record.source_path
            elif (
                record.format_id in TEXT_FORMAT_IDS or record.format_id in EXCEL_FORMAT_IDS
            ) and record.options.uses_managed_cache:
                parquet_path = self._ensure_record_parquet_cache(ref, record).cache_path
                record = self._table_record(ref)
            if parquet_path is not None:
                arrow_window = self._preview_window_arrow(
                    record,
                    parquet_path,
                    query=query,
                )
                if arrow_window is not None:
                    return arrow_window

        result = evaluate_python_query(
            query,
            self._iter_all_table_records(record),
            scan_row_cap=PREVIEW_QUERY_SCAN_ROW_CAP,
        )
        metadata = self._record_metadata(record.format_id, record.size_bytes, record.warnings)
        if result.truncated:
            metadata["query_scan_truncated"] = True
            metadata["query_scanned_rows"] = result.scanned_rows
        return TabularDataWindow(
            columns=query.selected_columns,
            rows=result.rows,
            row_offset=query.row_offset,
            column_offset=query.column_offset,
            total_rows=result.total_rows,
            total_columns=len(all_columns),
            metadata=metadata,
        )

    def _preview_window_arrow(
        self,
        record: _TableRecord,
        parquet_path: Path,
        *,
        query: NormalizedPreviewQuery,
    ) -> TabularDataWindow | None:
        result = evaluate_arrow_query(
            query,
            parquet_path,
            query_table_for=self._query_table_for,
            run_io=self._run_io,
        )
        if result is None:
            return None
        metadata = self._record_metadata(record.format_id, record.size_bytes, record.warnings)
        metadata["query_backend"] = "arrow"
        return TabularDataWindow(
            columns=query.selected_columns,
            rows=result.rows,
            row_offset=query.row_offset,
            column_offset=query.column_offset,
            total_rows=result.total_rows,
            total_columns=len(query.all_columns),
            metadata=metadata,
        )

    # Interactive sort/search re-queries the same parquet repeatedly while the
    # user types; keep ONE table (plus lazily lowered text views) in memory so
    # repeat queries skip the parquet read and the per-query string casts.
    _QUERY_TABLE_CACHE_MAX_BYTES = 1_536 * 1024 * 1024

    def _query_table_for(
        self,
        pq: Any,
        parquet_path: Path,
        needed: Sequence[str],
    ) -> tuple[Any, dict[str, Any]] | None:
        try:
            stat = parquet_path.stat()
        except OSError:
            return None
        stamp = (str(parquet_path), int(stat.st_mtime_ns), int(stat.st_size))
        with self._records_lock:
            entry = self._query_table_cache
            if (
                entry is not None
                and entry["stamp"] == stamp
                and set(needed) <= set(entry["table"].column_names)
            ):
                return entry["table"], entry["text_views"]
        estimate = self._query_table_cache_size_estimate(pq, parquet_path, needed)
        if estimate is not None and estimate > self._QUERY_TABLE_CACHE_MAX_BYTES:
            return None
        table = pq.read_table(parquet_path, columns=list(needed))
        if int(getattr(table, "nbytes", 0)) > self._QUERY_TABLE_CACHE_MAX_BYTES:
            return None
        entry = {"stamp": stamp, "table": table, "text_views": {}}
        with self._records_lock:
            self._query_table_cache = entry
        return table, entry["text_views"]

    def _query_table_cache_size_estimate(
        self,
        pq: Any,
        parquet_path: Path,
        needed: Sequence[str],
    ) -> int | None:
        try:
            parquet_file = pq.ParquetFile(parquet_path)
            metadata = parquet_file.metadata
            schema_names = list(getattr(metadata.schema, "names", []) or [])
            needed_set = set(needed)
            needed_indexes = {
                index for index, name in enumerate(schema_names) if name in needed_set
            }
            if not needed_indexes:
                return 0
            total = 0
            for row_group_index in range(int(metadata.num_row_groups)):
                row_group = metadata.row_group(row_group_index)
                for column_index in needed_indexes:
                    column = row_group.column(column_index)
                    total += int(getattr(column, "total_uncompressed_size", 0) or 0)
            return total or None
        except Exception:  # noqa: BLE001 - best-effort guard before cache read
            return None

    def rows(self, ref: TabularDataRef, request: TabularWindowRequest) -> Sequence[Mapping[str, Any]]:
        return self.window(ref, request).rows

    def window_columns(self, ref: TabularDataRef, request: TabularWindowRequest) -> tuple[str, ...]:
        self.ensure_table_ref(ref)
        record = self._table_record(ref)
        columns = tuple(column.name for column in record.columns)
        return _select_columns(columns, request)

    def iter_window_rows(
        self,
        ref: TabularDataRef,
        request: TabularWindowRequest,
    ) -> Iterable[Mapping[str, Any]]:
        self.ensure_table_ref(ref)
        record = self._table_record(ref)
        selected_columns = self.window_columns(ref, request)
        if (
            record.format_id in TEXT_FORMAT_IDS or record.format_id in EXCEL_FORMAT_IDS
        ) and record.options.uses_managed_cache:
            parquet_path = self._ensure_record_parquet_cache(ref, record).cache_path
            record = self._table_record(ref)
            batch_options = TabularArrowBatchOptions(
                row_limit=request.row_limit if request.row_limit > 0 else (record.row_count or 2_147_483_647),
                batch_size=4096,
                row_offset=request.row_offset,
                columns=selected_columns,
            )
            for batch in self._iter_parquet_batches(record, batch_options, parquet_path):
                for row in batch.to_pylist():
                    yield _json_safe_mapping(row)
            return
        emitted = 0
        for row_index, source_row in enumerate(self._iter_all_table_records(record)):
            if row_index < request.row_offset:
                continue
            yield {column: source_row.get(column) for column in selected_columns}
            emitted += 1
            if request.row_limit > 0 and emitted >= request.row_limit:
                return

    def arrow_batches(self, ref: TabularDataRef, options: TabularArrowBatchOptions) -> Iterable[Any]:
        self.ensure_table_ref(ref)
        record = self._table_record(ref)
        parquet_path: Path | None = None
        if record.format_id == "parquet":
            parquet_path = record.source_path
        elif (
            record.format_id in TEXT_FORMAT_IDS or record.format_id in EXCEL_FORMAT_IDS
        ) and record.options.uses_managed_cache:
            parquet_path = self._ensure_record_parquet_cache(ref, record).cache_path
            record = self._table_record(ref)
        if parquet_path is not None:
            yield from self._iter_parquet_batches_safely(record, options, parquet_path)
            return
        request = TabularWindowRequest(
            row_offset=options.row_offset,
            row_limit=options.row_limit,
            column_limit=len(options.columns) if options.columns else len(record.columns),
            columns=options.columns,
        )
        rows = list(self.rows(ref, request))
        if rows:
            yield rows

    def _iter_parquet_batches_safely(
        self,
        record: _TableRecord,
        options: TabularArrowBatchOptions,
        parquet_path: Path,
    ) -> Iterable[Any]:
        """Stream parquet batches while keeping native reads off the UI stack."""

        if threading.current_thread() is not threading.main_thread():
            yield from self._iter_parquet_batches(record, options, parquet_path)
            return

        sentinel = object()
        stop = threading.Event()
        batches: queue.Queue[Any] = queue.Queue(maxsize=4)

        def put(item: Any) -> None:
            while not stop.is_set():
                try:
                    batches.put(item, timeout=0.1)
                    return
                except queue.Full:
                    continue

        def produce() -> None:
            try:
                for batch in self._iter_parquet_batches(record, options, parquet_path):
                    put(batch)
                    if stop.is_set():
                        return
            except Exception as exc:  # noqa: BLE001 - reraised on the caller thread
                put(exc)
            finally:
                put(sentinel)

        future = _tabular_io_executor().submit(produce)
        try:
            while True:
                item = batches.get()
                if item is sentinel:
                    future.result()
                    return
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            stop.set()

    def to_pandas(self, ref: TabularDataRef, options: TabularMaterializationOptions) -> Any:
        self.ensure_table_ref(ref)
        record = self._table_record(ref)
        self._enforce_table_materialization_gate(record, options)
        pandas = _import_optional("pandas", format_id=record.format_id, purpose="pandas materialization")
        rows = self.window(ref, _window_request_from_materialization(record, options)).rows
        return pandas.DataFrame(list(rows))

    def to_polars(self, ref: TabularDataRef, options: TabularMaterializationOptions) -> Any:
        self.ensure_table_ref(ref)
        record = self._table_record(ref)
        self._enforce_table_materialization_gate(record, options)
        polars = _import_optional("polars", format_id=record.format_id, purpose="Polars materialization")
        rows = self.window(ref, _window_request_from_materialization(record, options)).rows
        return polars.DataFrame(list(rows))

    def to_numpy(self, ref: TabularDataRef | ArrayDataRef, options: TabularMaterializationOptions | ArrayMaterializationOptions) -> Any:
        numpy = _import_optional("numpy", format_id="numpy", purpose="NumPy materialization")
        if isinstance(ref, TabularDataRef):
            if not isinstance(options, TabularMaterializationOptions):
                raise TypeError("tabular refs require TabularMaterializationOptions")
            self.ensure_table_ref(ref)
            record = self._table_record(ref)
            self._enforce_table_materialization_gate(record, options)
            rows = self.window(ref, _window_request_from_materialization(record, options)).rows
            return numpy.array([list(row.values()) for row in rows], dtype=object)
        if not isinstance(options, ArrayMaterializationOptions):
            raise TypeError("array refs require ArrayMaterializationOptions")
        self.ensure_array_ref(ref)
        record = self._array_record(ref)
        self._enforce_array_materialization_gate(record, options)
        return self._read_array_materialized(record, options)

    def slice_2d(self, ref: ArrayDataRef, request: ArraySlice2DRequest) -> ArraySlice2D:
        self.ensure_array_ref(ref)
        record = self._array_record(ref)
        values = self._read_array_slice(record, request)
        return ArraySlice2D(
            values=values,
            row_offset=request.row_offset,
            column_offset=request.column_offset,
            shape=record.shape,
            dtype=record.dtype,
            metadata=self._record_metadata(record.format_id, record.size_bytes, record.warnings),
        )

    def parquet_cache_key(
        self,
        source_path: Path | str | os.PathLike[str],
        options: TabularLoadOptions | Mapping[str, Any] | None = None,
        *,
        selected_object: str = "",
    ) -> ParquetCacheKey:
        normalized_options = _coerce_options(options)
        path = self._resolve_path(source_path)
        stats = self._source_stats(path)
        selected = selected_object.strip() or normalized_options.selected_object
        payload = {
            "source_path": str(path),
            "source_mtime_ns": stats.mtime_ns,
            "source_size_bytes": stats.size_bytes,
            "parser_options": normalized_options.to_cache_payload(),
            "selected_object": selected,
            "backend_policy_revision": self.policy.revision,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return ParquetCacheKey(hashlib.sha256(raw).hexdigest(), payload)

    def parquet_cache_paths(self, key: str) -> tuple[Path, Path]:
        safe_key = str(key).strip().lower()
        if not safe_key:
            raise ValueError("cache key must be non-empty")
        bucket = self.cache_dir / safe_key[:2]
        return bucket / f"{safe_key}.parquet", bucket / f"{safe_key}.json"

    def ensure_parquet_cache(
        self,
        source_path: Path | str | os.PathLike[str],
        options: TabularLoadOptions | Mapping[str, Any] | None = None,
        *,
        selected_object: str = "",
    ) -> ParquetCacheEntry:
        normalized_options = _coerce_options(options)
        cache_key = self.parquet_cache_key(
            source_path,
            normalized_options,
            selected_object=selected_object,
        )
        cache_path, metadata_path = self.parquet_cache_paths(cache_key.key)
        if cache_path.is_file() and metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            return ParquetCacheEntry(cache_key.key, cache_path, metadata_path, metadata)
        with self._conversion_lock(cache_key.key):
            if cache_path.is_file() and metadata_path.is_file():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                return ParquetCacheEntry(cache_key.key, cache_path, metadata_path, metadata)
            _import_optional("pyarrow.parquet", format_id="parquet_cache", purpose="managed Parquet cache")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = cache_path.with_name(f"{cache_path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
            try:
                self._run_io(
                    self._write_parquet_cache,
                    self._resolve_path(source_path),
                    normalized_options.with_selected_object(selected_object or normalized_options.selected_object),
                    temp_path,
                )
                os.replace(temp_path, cache_path)
            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
            metadata = {
                "kind": "tabular_data_parquet_cache",
                "key": cache_key.key,
                "payload": cache_key.payload,
                "cache_path": str(cache_path),
                "backend_policy_revision": self.policy.revision,
                "row_count": self._parquet_row_count(cache_path),
            }
            metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        self.enforce_cache_size_limit(preserve_paths=(cache_path,))
        return ParquetCacheEntry(cache_key.key, cache_path, metadata_path, metadata)

    @staticmethod
    def _run_io(fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run heavy native I/O off the main thread (see _tabular_io_executor)."""

        if threading.current_thread() is threading.main_thread():
            return _tabular_io_executor().submit(fn, *args, **kwargs).result()
        return fn(*args, **kwargs)

    def _record_source_is_current(self, record: _TableRecord | _ArrayRecord) -> bool:
        try:
            return self._source_stats(record.source_path) == record.stats
        except OSError:
            return False

    def _conversion_lock(self, cache_key: str) -> threading.Lock:
        with self._conversion_locks_guard:
            lock = self._conversion_locks.get(cache_key)
            if lock is None:
                lock = threading.Lock()
                self._conversion_locks[cache_key] = lock
            return lock

    def _parquet_row_count(self, parquet_path: Path) -> int | None:
        def read_count() -> int | None:
            try:
                pq = _import_optional("pyarrow.parquet", format_id="parquet_cache", purpose="managed Parquet cache")
                with pq.ParquetFile(parquet_path) as parquet_file:
                    return int(parquet_file.metadata.num_rows)
            except Exception:  # noqa: BLE001 - row counts are best-effort metadata
                return None

        return self._run_io(read_count)

    def _ensure_record_parquet_cache(self, ref: TabularDataRef, record: _TableRecord) -> ParquetCacheEntry:
        cache_key = self.parquet_cache_key(
            record.source_path,
            record.options,
            selected_object=record.object_id,
        )
        cache_path, metadata_path = self.parquet_cache_paths(cache_key.key)
        if not (cache_path.is_file() and metadata_path.is_file()) and not self._conversion_allowed(record):
            raise TabularCacheNotReadyError(source_path=record.source_path, size_bytes=record.size_bytes)
        entry = self.ensure_parquet_cache(
            record.source_path,
            record.options,
            selected_object=record.object_id,
        )
        self._backfill_record_from_cache(ref, record, entry)
        return entry

    def _conversion_allowed(self, record: _TableRecord) -> bool:
        if self.ui_thread_conversion_allowed:
            return True
        if record.size_bytes <= TABULAR_DATA_INLINE_CONVERSION_BYTES:
            return True
        return threading.current_thread() is not threading.main_thread()

    def _backfill_record_from_cache(
        self,
        ref: TabularDataRef,
        record: _TableRecord,
        entry: ParquetCacheEntry,
    ) -> None:
        """Backfill row count and typed column dtypes once the cache exists."""

        needs_row_count = record.row_count is None
        needs_dtypes = any(not column.dtype for column in record.columns)
        if not needs_row_count and not needs_dtypes:
            return

        def read_metadata() -> tuple[int, dict[str, str]] | None:
            try:
                pq = _import_optional("pyarrow.parquet", format_id="parquet_cache", purpose="managed Parquet cache")
                with pq.ParquetFile(entry.cache_path) as parquet_file:
                    return (
                        int(parquet_file.metadata.num_rows),
                        {field.name: str(field.type) for field in parquet_file.schema_arrow},
                    )
            except Exception:  # noqa: BLE001 - backfill is best-effort
                return None

        metadata = self._run_io(read_metadata)
        if metadata is None:
            return
        row_count, arrow_types = metadata
        columns = tuple(
            TabularColumn(column.name, column.dtype or arrow_types.get(column.name, ""), column.nullable)
            for column in record.columns
        )
        updated = replace(record, row_count=row_count, columns=columns)
        with self._records_lock:
            for ref_id, existing in list(self._table_records.items()):
                if existing is record:
                    self._table_records[ref_id] = updated

    def _cached_parquet_row_count(
        self,
        path: Path,
        options: TabularLoadOptions,
    ) -> int | None:
        if not options.uses_managed_cache:
            return None
        try:
            cache_key = self.parquet_cache_key(path, options)
            _cache_path, metadata_path = self.parquet_cache_paths(cache_key.key)
            if not metadata_path.is_file():
                return None
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        row_count = metadata.get("row_count")
        return int(row_count) if isinstance(row_count, int) else None

    def _table_record(self, ref: TabularDataRef) -> _TableRecord:
        record = self._table_records.get(ref.ref_id)
        if record is None:
            raise KeyError(f"Unknown tabular data ref {ref.ref_id!r}.")
        return record

    def _array_record(self, ref: ArrayDataRef) -> _ArrayRecord:
        record = self._array_records.get(ref.ref_id)
        if record is None:
            raise KeyError(f"Unknown array data ref {ref.ref_id!r}.")
        return record

    def _enforce_table_materialization_gate(
        self,
        record: _TableRecord,
        options: TabularMaterializationOptions,
    ) -> None:
        if (
            self.policy.requires_explicit_materialization(record.size_bytes)
            and not options.allow_full_materialization
            and options.row_limit is None
            and options.column_limit is None
            and not options.columns
        ):
            raise LargeDataMaterializationError(
                "Full table materialization above 5 GiB requires explicit allow_full_materialization.",
                size_bytes=record.size_bytes,
            )

    def _enforce_array_materialization_gate(
        self,
        record: _ArrayRecord,
        options: ArrayMaterializationOptions,
    ) -> None:
        if (
            self.policy.requires_explicit_materialization(record.size_bytes)
            and not options.allow_full_materialization
            and options.max_elements is None
            and not options.slices
        ):
            raise LargeDataMaterializationError(
                "Full array materialization above 5 GiB requires explicit allow_full_materialization.",
                size_bytes=record.size_bytes,
            )

    def _record_metadata(
        self,
        format_id: str,
        size_bytes: int,
        warnings: Sequence[str],
        *,
        options: TabularLoadOptions | None = None,
    ) -> dict[str, Any]:
        payload = {
            "format_id": format_id,
            "size_bytes": size_bytes,
            "size_class": self.policy.classify_size(size_bytes),
            "warnings": list(warnings),
            "backend_policy_revision": self.policy.revision,
        }
        if options is not None:
            payload["load_options"] = options.to_cache_payload()
        return payload

    def _ref_id(self, kind: str, record: _TableRecord | _ArrayRecord) -> str:
        payload = {
            "kind": kind,
            "source_path": str(record.source_path),
            "format_id": record.format_id,
            "object_id": record.object_id,
            "options": record.options.to_cache_payload(),
            "size_bytes": record.size_bytes,
            "mtime_ns": record.stats.mtime_ns,
            "policy_revision": self.policy.revision,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return f"{kind}_{hashlib.sha256(raw).hexdigest()[:24]}"

    def _resolve_path(self, source_path: Path | str | os.PathLike[str]) -> Path:
        path = Path(source_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def _source_stats(self, path: Path) -> SourceStats:
        stat = path.stat()
        return SourceStats(size_bytes=int(stat.st_size), mtime_ns=int(stat.st_mtime_ns))

    def sweep_stale_cache_entries(self) -> int:
        """Delete cache entries written under a different backend policy revision."""

        removed = 0
        for metadata_path in self.cache_dir.glob("*/*.json"):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if str(metadata.get("backend_policy_revision", "")) == self.policy.revision:
                continue
            cache_path = metadata_path.with_suffix(".parquet")
            for stale in (cache_path, metadata_path):
                try:
                    stale.unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    continue
        return removed

    def enforce_cache_size_limit(
        self,
        max_bytes: int = TABULAR_DATA_CACHE_MAX_BYTES,
        *,
        preserve_paths: Sequence[Path] | None = None,
    ) -> int:
        """Evict least-recently-used cache entries past the size cap."""

        preserved = {
            Path(path).resolve(strict=False)
            for path in (preserve_paths or ())
        }
        entries: list[tuple[float, int, Path, Path]] = []
        total = 0
        for cache_path in self.cache_dir.glob("*/*.parquet"):
            try:
                stat = cache_path.stat()
            except OSError:
                continue
            size = int(stat.st_size)
            total += size
            entries.append((stat.st_mtime, size, cache_path, cache_path.with_suffix(".json")))
        if total <= max_bytes:
            return 0
        removed = 0
        for _mtime, size, cache_path, metadata_path in sorted(entries):
            if total <= max_bytes:
                break
            if cache_path.resolve(strict=False) in preserved:
                continue
            try:
                cache_path.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
            except OSError:
                continue
            total -= size
            removed += 1
        return removed


_shared_service_guard = threading.Lock()
_shared_service: TabularLoaderCacheService | None = None
_shared_ui_thread_conversion_allowed = True


def set_shared_tabular_ui_thread_conversion_allowed(allowed: bool) -> None:
    """Configure the shared service without forcing its first allocation."""

    global _shared_ui_thread_conversion_allowed
    with _shared_service_guard:
        _shared_ui_thread_conversion_allowed = bool(allowed)
        if _shared_service is not None:
            _shared_service.ui_thread_conversion_allowed = _shared_ui_thread_conversion_allowed


def shared_tabular_loader_cache_service() -> TabularLoaderCacheService:
    """Process-wide tabular loader service.

    One shared instance keeps table/array records, scan results, and the
    managed parquet cache warm across execution, previews, and scene payload
    builds. Thread-safe; the first call sweeps cache entries written under a
    previous backend policy revision.
    """

    global _shared_service
    with _shared_service_guard:
        if _shared_service is None:
            service = TabularLoaderCacheService()
            service.ui_thread_conversion_allowed = _shared_ui_thread_conversion_allowed
            try:
                service.sweep_stale_cache_entries()
            except OSError:
                pass
            _shared_service = service
        return _shared_service


def reset_shared_tabular_loader_cache_service() -> None:
    """Drop the process-wide service (test isolation hook)."""

    global _shared_service, _shared_ui_thread_conversion_allowed
    with _shared_service_guard:
        _shared_service = None
        _shared_ui_thread_conversion_allowed = True


def scan_tabular_source(
    source_path: Path | str | os.PathLike[str],
    options: TabularLoadOptions | Mapping[str, Any] | None = None,
    *,
    cache_dir: Path | str | os.PathLike[str] | None = None,
    policy: TabularBackendPolicy = DEFAULT_TABULAR_BACKEND_POLICY,
) -> SourceScanResult:
    return TabularLoaderCacheService(cache_dir=cache_dir, policy=policy).scan_source(source_path, options)


def open_tabular_source(
    source_path: Path | str | os.PathLike[str],
    options: TabularLoadOptions | Mapping[str, Any] | None = None,
    *,
    cache_dir: Path | str | os.PathLike[str] | None = None,
    policy: TabularBackendPolicy = DEFAULT_TABULAR_BACKEND_POLICY,
) -> tuple[TabularLoaderCacheService, TabularDataRef | ArrayDataRef]:
    service = TabularLoaderCacheService(cache_dir=cache_dir, policy=policy)
    return service, service.open_source(source_path, options)


def _source_path_from_ref(ref: TabularDataRef | ArrayDataRef) -> Path:
    source_uri = str(ref.source_uri or "").strip()
    if not source_uri:
        raise ValueError(f"Cannot reopen tabular ref {ref.ref_id!r} without source_uri.")
    parsed = urlparse(source_uri)
    if parsed.scheme and parsed.scheme != "file":
        raise ValueError(f"Unsupported tabular ref source URI scheme: {parsed.scheme!r}.")
    if parsed.scheme == "file":
        netloc = f"//{parsed.netloc}" if parsed.netloc else ""
        return Path(url2pathname(netloc + parsed.path)).expanduser().resolve()
    return Path(source_uri).expanduser().resolve()


def _load_options_from_ref(ref: TabularDataRef | ArrayDataRef) -> TabularLoadOptions:
    metadata = ref.metadata if isinstance(ref.metadata, Mapping) else {}
    load_options = metadata.get("load_options")
    options = TabularLoadOptions.from_mapping(load_options if isinstance(load_options, Mapping) else None)
    if ref.object_id:
        return options.with_selected_object(ref.object_id)
    return options


def _window_request_from_materialization(
    record: _TableRecord,
    options: TabularMaterializationOptions,
) -> TabularWindowRequest:
    if options.row_limit is not None:
        row_limit = options.row_limit
    elif record.row_count is not None:
        row_limit = record.row_count
    else:
        row_limit = 0
    column_limit = options.column_limit if options.column_limit is not None else len(record.columns)
    return TabularWindowRequest(
        row_limit=row_limit,
        column_limit=column_limit,
        columns=options.columns,
    )


def _path_uri(path: Path) -> str:
    try:
        return path.as_uri()
    except ValueError:
        return path.resolve().as_uri()


__all__ = [
    "ARRAY_FORMAT_IDS",
    "EXCEL_FORMAT_IDS",
    "HDF5_SUFFIXES",
    "LargeDataMaterializationError",
    "MissingTabularDependencyError",
    "ParquetCacheEntry",
    "ParquetCacheKey",
    "SUPPORTED_FORMAT_IDS",
    "SelectableObject",
    "SelectionRequiredError",
    "SourceScanResult",
    "SourceStats",
    "TABULAR_CACHE_RESOLVER_ID",
    "TEXT_FORMAT_IDS",
    "TabularCacheNotReadyError",
    "TabularLoadOptions",
    "TabularLoaderCacheService",
    "TabularLoaderError",
    "UnsupportedTabularFormatError",
    "detect_format_id",
    "open_tabular_source",
    "reset_shared_tabular_loader_cache_service",
    "scan_tabular_source",
    "set_shared_tabular_ui_thread_conversion_allowed",
    "shared_tabular_loader_cache_service",
    "supported_format_ids",
]
