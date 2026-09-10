from __future__ import annotations

import argparse
import shutil
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ea_node_editor.benchmarks.tabular.adapters import FormatAdapter, available_format_adapters
from ea_node_editor.benchmarks.tabular.contracts import (
    DEFAULT_FORMATS,
    DEFAULT_OPERATIONS,
    DEFAULT_PROFILES,
    SUPPORTED_BACKENDS,
    BenchmarkConfig,
    BenchmarkResult,
    DatasetSpec,
    UnsupportedBenchmarkCaseError,
)
from ea_node_editor.benchmarks.tabular.optional_imports import load_module
from ea_node_editor.benchmarks.tabular.reports import write_reports

_LARGE_FREE_SPACE_MULTIPLIER = 1.2


def run_benchmark_matrix(config: BenchmarkConfig) -> tuple[list[BenchmarkResult], dict[str, Path]]:
    adapters = available_format_adapters()
    _validate_config(config, adapters)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    datasets_dir = config.output_dir / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)

    results: list[BenchmarkResult] = []
    error_count = 0
    for size in config.sizes:
        for profile in config.profiles:
            spec = DatasetSpec.from_size(size, profile=profile, seed=config.seed)
            _check_large_dataset_policy(config, spec)
            for format_id in config.formats:
                adapter = adapters[format_id]
                dataset_path = adapter.path_for(datasets_dir, spec)
                if not adapter.supports(spec):
                    results.append(
                        _failed_result(
                            spec,
                            adapter,
                            backend_id="native",
                            operation="write",
                            path=dataset_path,
                            error=f"{format_id} does not support profile '{profile}'.",
                        )
                    )
                    continue
                if "write" in config.operations:
                    write_result = _measure(
                        spec,
                        adapter,
                        backend_id="native",
                        operation="write",
                        path=dataset_path,
                        action=lambda: _write_dataset(config, adapter, spec, dataset_path),
                    )
                    results.append(write_result)
                    if not write_result.success:
                        error_count += 1
                        if _stop_after_error(config, error_count):
                            return _finish(config, results)
                        continue
                elif not dataset_path.exists():
                    bootstrap_result = _measure(
                        spec,
                        adapter,
                        backend_id="native",
                        operation="write",
                        path=dataset_path,
                        action=lambda: _write_dataset(config, adapter, spec, dataset_path),
                    )
                    results.append(bootstrap_result)
                    if not bootstrap_result.success:
                        continue

                for backend_id in config.backends:
                    for operation in config.operations:
                        if operation == "write":
                            continue
                        result = _measure(
                            spec,
                            adapter,
                            backend_id=backend_id,
                            operation=operation,
                            path=dataset_path,
                            action=lambda adapter=adapter, dataset_path=dataset_path, backend_id=backend_id, operation=operation: _run_operation(
                                adapter,
                                dataset_path,
                                backend_id,
                                operation,
                                preview_rows=config.preview_rows,
                            ),
                        )
                        results.append(result)
                        if not result.success:
                            error_count += 1
                            if _stop_after_error(config, error_count):
                                return _finish(config, results)
    return _finish(config, results)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark tabular file formats and dataframe backends.")
    parser.add_argument("--headless", action="store_true", help="run the benchmark without launching the GUI")
    parser.add_argument("--gui", action="store_true", help="launch the standalone PyQt/QML workbench")
    parser.add_argument("--out", default="artifacts/tabular_bench", help="output directory for datasets and reports")
    parser.add_argument("--sizes", default="small", help="comma-separated size presets: small, medium, large")
    parser.add_argument("--profiles", default=",".join(DEFAULT_PROFILES), help="comma-separated dataset profiles")
    parser.add_argument("--formats", default="csv,parquet", help="comma-separated formats or 'all'")
    parser.add_argument("--backends", default="pandas,polars,duckdb,numpy", help="comma-separated backends or 'all'")
    parser.add_argument("--operations", default="write,read,schema,preview,filter,groupby,compute", help="comma-separated operations or 'all'")
    parser.add_argument("--preview-rows", type=int, default=50)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--allow-large", action="store_true", help="allow generation of >5 GB datasets")
    parser.add_argument("--reuse-datasets", action="store_true", help="reuse existing generated datasets")
    parser.add_argument("--max-errors", type=int, default=0, help="stop after this many errors; 0 means no limit")
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> BenchmarkConfig:
    formats = _parse_csv_arg(args.formats, all_values=DEFAULT_FORMATS)
    backends = _parse_csv_arg(args.backends, all_values=SUPPORTED_BACKENDS)
    operations = _parse_csv_arg(args.operations, all_values=DEFAULT_OPERATIONS)
    return BenchmarkConfig(
        output_dir=Path(args.out),
        sizes=_parse_csv_arg(args.sizes, all_values=("small", "medium", "large")),
        profiles=_parse_csv_arg(args.profiles, all_values=DEFAULT_PROFILES),
        formats=formats,
        backends=backends,
        operations=operations,
        preview_rows=args.preview_rows,
        seed=args.seed,
        allow_large=args.allow_large,
        reuse_datasets=args.reuse_datasets,
        headless=bool(args.headless and not args.gui),
        max_errors=args.max_errors,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.gui and not args.headless:
        from ea_node_editor.benchmarks.tabular.gui import run_gui

        return run_gui(args)
    if not args.headless and not args.gui:
        from ea_node_editor.benchmarks.tabular.gui import run_gui

        return run_gui(args)

    config = config_from_args(args)
    try:
        results, paths = run_benchmark_matrix(config)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    print(f"Wrote JSON report: {paths['json']}")
    print(f"Wrote Markdown report: {paths['markdown']}")
    print(f"Wrote CSV results: {paths['csv']}")
    failures = sum(1 for result in results if not result.success and not result.skipped)
    skipped = sum(1 for result in results if result.skipped)
    print(f"Completed {len(results)} benchmark cases with {failures} failures and {skipped} skipped.")
    return 0


def _finish(config: BenchmarkConfig, results: list[BenchmarkResult]) -> tuple[list[BenchmarkResult], dict[str, Path]]:
    paths = write_reports(config, results)
    return results, paths


def _write_dataset(config: BenchmarkConfig, adapter: FormatAdapter, spec: DatasetSpec, path: Path) -> dict[str, Any]:
    if config.reuse_datasets and path.exists():
        return {"reused": True, "rows": adapter.row_count(path)}
    return adapter.write(spec, path)


def _run_operation(
    adapter: FormatAdapter,
    path: Path,
    backend_id: str,
    operation: str,
    *,
    preview_rows: int,
) -> dict[str, Any]:
    if operation == "read":
        data = adapter.read(path, backend_id)
        return _object_shape_payload(data)
    if operation == "schema":
        return {"schema": adapter.schema(path)}
    if operation == "preview":
        data = adapter.preview(path, rows=preview_rows, backend_id=backend_id)
        return _object_shape_payload(data)

    data = adapter.read(path, backend_id)
    if operation == "projection":
        return _projection(data)
    if operation == "lookup":
        return _lookup(data)
    if operation == "filter":
        return _filter(data)
    if operation == "groupby":
        return _groupby(data)
    if operation == "sort":
        return _sort(data)
    if operation == "compute":
        return _compute(data)
    if operation == "convert":
        return _convert(data, backend_id)
    raise UnsupportedBenchmarkCaseError(f"Unknown operation: {operation}")


def _measure(
    spec: DatasetSpec,
    adapter: FormatAdapter,
    *,
    backend_id: str,
    operation: str,
    path: Path,
    action: Callable[[], dict[str, Any]],
) -> BenchmarkResult:
    process = _process()
    rss_before = _rss(process)
    rss_peak = [rss_before]
    stop_sampling = threading.Event()
    sampler: threading.Thread | None = None
    if process is not None:
        sampler = threading.Thread(
            target=_sample_peak_rss,
            args=(process, stop_sampling, rss_peak),
            daemon=True,
        )
        sampler.start()
    cpu_before = time.process_time()
    start = time.perf_counter()
    success = True
    error = ""
    details: dict[str, Any] = {}
    try:
        details = action() or {}
    except UnsupportedBenchmarkCaseError as exc:
        success = False
        skipped = True
        error = str(exc)
    except Exception as exc:  # noqa: BLE001
        success = False
        skipped = False
        error = f"{type(exc).__name__}: {exc}"
    else:
        skipped = False
    finally:
        stop_sampling.set()
        if sampler is not None:
            sampler.join(timeout=0.25)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    cpu_ms = (time.process_time() - cpu_before) * 1000.0
    rss_after = _rss(process)
    rss_peak_bytes = max(rss_peak[0], rss_before, rss_after)
    file_size = _file_size(path)
    throughput = _throughput(file_size, elapsed_ms) if success else 0.0
    return BenchmarkResult(
        dataset=spec,
        format_id=adapter.format_id,
        backend_id=backend_id,
        operation=operation,
        elapsed_ms=elapsed_ms,
        cpu_ms=cpu_ms,
        rss_before_bytes=rss_before,
        rss_after_bytes=rss_after,
        rss_peak_bytes=rss_peak_bytes,
        file_size_bytes=file_size,
        success=success,
        skipped=skipped,
        throughput_mb_s=throughput,
        rows=_safe_int(details.get("rows")),
        columns=_safe_int(details.get("columns")),
        error=error,
        details=details,
    )


def _failed_result(
    spec: DatasetSpec,
    adapter: FormatAdapter,
    *,
    backend_id: str,
    operation: str,
    path: Path,
    error: str,
) -> BenchmarkResult:
    return BenchmarkResult(
        dataset=spec,
        format_id=adapter.format_id,
        backend_id=backend_id,
        operation=operation,
        elapsed_ms=0.0,
        cpu_ms=0.0,
        rss_before_bytes=0,
        rss_after_bytes=0,
        file_size_bytes=_file_size(path),
        success=False,
        skipped=True,
        error=error,
    )


def _validate_config(config: BenchmarkConfig, adapters: dict[str, FormatAdapter]) -> None:
    unknown_formats = sorted(set(config.formats) - set(adapters))
    if unknown_formats:
        raise ValueError(f"Unknown format(s): {', '.join(unknown_formats)}")
    unknown_backends = sorted(set(config.backends) - set(SUPPORTED_BACKENDS))
    if unknown_backends:
        raise ValueError(f"Unknown backend(s): {', '.join(unknown_backends)}")
    unknown_operations = sorted(set(config.operations) - set(DEFAULT_OPERATIONS))
    if unknown_operations:
        raise ValueError(f"Unknown operation(s): {', '.join(unknown_operations)}")


def _check_large_dataset_policy(config: BenchmarkConfig, spec: DatasetSpec) -> None:
    if spec.size != "large":
        return
    if not config.allow_large:
        raise ValueError("Large datasets are over 5 GB and require --allow-large.")
    config.output_dir.mkdir(parents=True, exist_ok=True)
    required = int(spec.target_bytes * _LARGE_FREE_SPACE_MULTIPLIER)
    free = shutil.disk_usage(config.output_dir).free
    if free < required:
        raise ValueError(
            f"Large benchmark requires at least {required} free bytes in {config.output_dir}; found {free}."
        )


def _projection(data: Any) -> dict[str, Any]:
    if _is_duckdb_relation(data):
        columns = data.columns[:2]
        if not columns:
            raise UnsupportedBenchmarkCaseError("DuckDB relation has no columns.")
        return {"rows": len(data.select(*(_quote_identifier(column) for column in columns)).limit(1000).fetchall()), "columns": len(columns)}
    frame = _to_pandas(data)
    columns = list(frame.columns[: min(2, len(frame.columns))])
    projected = frame[columns]
    return {"rows": len(projected), "columns": len(projected.columns), "columns_used": columns}


def _lookup(data: Any) -> dict[str, Any]:
    if _is_duckdb_relation(data):
        row = data.limit(1).fetchall()
        return {"rows": len(row), "columns": len(data.columns)}
    frame = _to_pandas(data)
    value = None if frame.empty else frame.iloc[min(5, len(frame) - 1), min(1, len(frame.columns) - 1)]
    return {"rows": 1 if value is not None else 0, "columns": 1, "value_type": type(value).__name__}


def _filter(data: Any) -> dict[str, Any]:
    if _is_duckdb_relation(data):
        column = _first_numeric_duckdb_column(data)
        if column is None:
            raise UnsupportedBenchmarkCaseError("No numeric column available for filter.")
        rows = data.filter(f"{_quote_identifier(column)} > 0").limit(10_000).fetchall()
        return {"rows": len(rows), "columns": len(data.columns), "predicate": f"{column} > 0"}
    frame = _to_pandas(data)
    column = _first_numeric_column(frame)
    if column is None:
        raise UnsupportedBenchmarkCaseError("No numeric column available for filter.")
    filtered = frame[frame[column] > 0]
    return {"rows": len(filtered), "columns": len(filtered.columns), "predicate": f"{column} > 0"}


def _groupby(data: Any) -> dict[str, Any]:
    if _is_duckdb_relation(data):
        columns = data.columns
        group_column = "group" if "group" in columns else columns[0]
        numeric_column = _first_numeric_duckdb_column(data)
        if numeric_column is None:
            raise UnsupportedBenchmarkCaseError("No numeric column available for group-by.")
        rows = data.aggregate(
            f"avg({_quote_identifier(numeric_column)}) AS mean_value",
            _quote_identifier(group_column),
        ).fetchall()
        return {"rows": len(rows), "columns": 2, "group_column": group_column}
    frame = _to_pandas(data)
    group_column = "group" if "group" in frame.columns else frame.columns[0]
    numeric_column = _first_numeric_column(frame)
    if numeric_column is None:
        raise UnsupportedBenchmarkCaseError("No numeric column available for group-by.")
    grouped = frame.groupby(group_column, dropna=False)[numeric_column].mean()
    return {"rows": len(grouped), "columns": 2, "group_column": str(group_column)}


def _sort(data: Any) -> dict[str, Any]:
    if _is_duckdb_relation(data):
        column = _first_numeric_duckdb_column(data)
        if column is None:
            raise UnsupportedBenchmarkCaseError("No numeric column available for sort.")
        rows = data.order(f"{_quote_identifier(column)} DESC").limit(100).fetchall()
        return {"rows": len(rows), "columns": len(data.columns), "sort_column": column}
    frame = _to_pandas(data)
    column = _first_numeric_column(frame)
    if column is None:
        raise UnsupportedBenchmarkCaseError("No numeric column available for sort.")
    sorted_frame = frame.sort_values(column, ascending=False).head(100)
    return {"rows": len(sorted_frame), "columns": len(sorted_frame.columns), "sort_column": str(column)}


def _compute(data: Any) -> dict[str, Any]:
    if _is_duckdb_relation(data):
        columns = data.columns[:2]
        if len(columns) < 2:
            raise UnsupportedBenchmarkCaseError("Need at least two columns for compute.")
        rows = data.project(
            f"{_quote_identifier(columns[0])} + {_quote_identifier(columns[1])} AS computed_value"
        ).limit(10_000).fetchall()
        return {"rows": len(rows), "columns": 1}
    frame = _to_pandas(data)
    numeric_columns = list(frame.select_dtypes("number").columns[:2])
    if len(numeric_columns) < 2:
        raise UnsupportedBenchmarkCaseError("Need at least two numeric columns for compute.")
    computed = frame[numeric_columns[0]] + frame[numeric_columns[1]]
    return {"rows": len(computed), "columns": 1}


def _convert(data: Any, backend_id: str) -> dict[str, Any]:
    frame = _to_pandas(data)
    if backend_id != "pandas":
        return {"rows": len(frame), "columns": len(frame.columns), "target": "pandas"}
    pa = load_module("pyarrow")
    table = pa.Table.from_pandas(frame, preserve_index=False)
    return {"rows": table.num_rows, "columns": table.num_columns, "target": "arrow"}


def _object_shape_payload(data: Any) -> dict[str, Any]:
    if _is_duckdb_relation(data):
        return {"rows": None, "columns": len(data.columns), "object_type": type(data).__name__}
    if hasattr(data, "shape"):
        shape = data.shape
        if len(shape) == 1:
            return {"rows": int(shape[0]), "columns": 1, "object_type": type(data).__name__}
        return {"rows": int(shape[0]), "columns": int(shape[1]), "object_type": type(data).__name__}
    if hasattr(data, "num_rows") and hasattr(data, "num_columns"):
        return {"rows": int(data.num_rows), "columns": int(data.num_columns), "object_type": type(data).__name__}
    return {"object_type": type(data).__name__}


def _to_pandas(data: Any) -> Any:
    if _is_duckdb_relation(data):
        return data.df()
    if hasattr(data, "to_pandas"):
        return data.to_pandas()
    if data.__class__.__module__.startswith("polars"):
        return data.to_pandas()
    if hasattr(data, "shape") and not hasattr(data, "columns"):
        pd = load_module("pandas")
        array = data
        if len(array.shape) > 2:
            array = array.reshape(array.shape[0], -1)
        return pd.DataFrame(array)
    return data


def _first_numeric_column(frame: Any) -> Any | None:
    numeric = list(frame.select_dtypes("number").columns)
    return None if not numeric else numeric[0]


def _first_numeric_duckdb_column(relation: Any) -> str | None:
    for column, dtype in zip(relation.columns, relation.types):
        if any(token in str(dtype).upper() for token in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "REAL")):
            return column
    return None


def _is_duckdb_relation(data: Any) -> bool:
    return data.__class__.__module__.startswith(("duckdb", "_duckdb")) and data.__class__.__name__ == "DuckDBPyRelation"


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _parse_csv_arg(value: str, *, all_values: tuple[str, ...]) -> tuple[str, ...]:
    if value.strip().lower() == "all":
        return all_values
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _stop_after_error(config: BenchmarkConfig, error_count: int) -> bool:
    return config.max_errors > 0 and error_count >= config.max_errors


def _process() -> Any:
    try:
        psutil = load_module("psutil")
        return psutil.Process()
    except Exception:
        return None


def _rss(process: Any) -> int:
    if process is None:
        return 0
    try:
        return int(process.memory_info().rss)
    except Exception:
        return 0


def _sample_peak_rss(process: Any, stop_event: threading.Event, rss_peak: list[int]) -> None:
    while not stop_event.is_set():
        rss_peak[0] = max(rss_peak[0], _rss(process))
        stop_event.wait(0.025)
    rss_peak[0] = max(rss_peak[0], _rss(process))


def _file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def _throughput(file_size: int, elapsed_ms: float) -> float:
    if file_size <= 0 or elapsed_ms <= 0:
        return 0.0
    return (file_size / 1024 / 1024) / (elapsed_ms / 1000.0)


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
