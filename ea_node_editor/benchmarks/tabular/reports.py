from __future__ import annotations

import csv
import json
import platform
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ea_node_editor.benchmarks.tabular.contracts import BenchmarkConfig, BenchmarkResult
from ea_node_editor.benchmarks.tabular.optional_imports import package_versions


def environment_payload() -> dict[str, Any]:
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname": socket.gethostname(),
        "packages": package_versions(),
    }


def build_report(config: BenchmarkConfig, results: list[BenchmarkResult]) -> dict[str, Any]:
    return {
        "kind": "tabular_backend_format_benchmark",
        "schema_version": 1,
        "environment": environment_payload(),
        "config": config.to_payload(),
        "summary": summarize_results(results),
        "results": [result.to_payload() for result in results],
    }


def summarize_results(results: list[BenchmarkResult]) -> dict[str, Any]:
    successes = [result for result in results if result.success and not result.skipped]
    skipped = [result for result in results if result.skipped]
    failures = [result for result in results if not result.success and not result.skipped]
    fastest_by_operation: dict[str, dict[str, Any]] = {}
    for result in successes:
        key = f"{result.dataset.size}:{result.dataset.profile}:{result.operation}"
        current = fastest_by_operation.get(key)
        if current is None or result.elapsed_ms < current["elapsed_ms"]:
            fastest_by_operation[key] = {
                "format_id": result.format_id,
                "backend_id": result.backend_id,
                "elapsed_ms": result.elapsed_ms,
                "throughput_mb_s": result.throughput_mb_s,
                "rss_peak_delta_bytes": result.to_payload()["rss_peak_delta_bytes"],
            }
    return {
        "result_count": len(results),
        "success_count": len(successes),
        "skipped_count": len(skipped),
        "failure_count": len(failures),
        "fastest_by_operation": fastest_by_operation,
    }


def write_reports(config: BenchmarkConfig, results: list[BenchmarkResult]) -> dict[str, Path]:
    report = build_report(config, results)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = config.output_dir / "tabular_benchmark_report.json"
    markdown_path = config.output_dir / "tabular_benchmark_report.md"
    csv_path = config.output_dir / "tabular_benchmark_results.csv"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(format_markdown(report), encoding="utf-8")
    write_csv(csv_path, results)
    return {"json": json_path, "markdown": markdown_path, "csv": csv_path}


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Tabular Benchmark Report",
        "",
        f"- Generated: `{report['environment']['generated_at_utc']}`",
        f"- Python: `{report['environment']['python_executable']}`",
        f"- Platform: `{report['environment']['platform']}`",
        (
            f"- Results: `{report['summary']['success_count']}` succeeded, "
            f"`{report['summary']['skipped_count']}` skipped, `{report['summary']['failure_count']}` failed"
        ),
        "",
        "## Fastest Successful Cases",
        "",
        "| Dataset/Operation | Format | Backend | Time (ms) | Throughput (MB/s) | Peak RSS Delta (MB) |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for key, value in sorted(report["summary"]["fastest_by_operation"].items()):
        lines.append(
            "| "
            + " | ".join(
                [
                    key,
                    value["format_id"],
                    value["backend_id"],
                    f"{value['elapsed_ms']:.3f}",
                    f"{value['throughput_mb_s']:.3f}",
                    f"{value['rss_peak_delta_bytes'] / 1024 / 1024:.3f}",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Failures", ""])
    failures = [result for result in report["results"] if not result["success"] and not result.get("skipped")]
    if not failures:
        lines.append("No failures recorded.")
    else:
        lines.extend(["| Dataset | Format | Backend | Operation | Error |", "| --- | --- | --- | --- | --- |"])
        for result in failures[:100]:
            dataset = result["dataset"]
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"{dataset['profile']}:{dataset['size']}",
                        result["format_id"],
                        result["backend_id"],
                        result["operation"],
                        result["error"].replace("|", "\\|"),
                    ]
                )
                + " |"
            )
    lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, results: list[BenchmarkResult]) -> None:
    fieldnames = [
        "profile",
        "size",
        "rows",
        "columns",
        "format_id",
        "backend_id",
        "operation",
        "success",
        "skipped",
        "elapsed_ms",
        "cpu_ms",
        "rss_before_bytes",
        "rss_after_bytes",
        "rss_peak_bytes",
        "rss_delta_bytes",
        "rss_peak_delta_bytes",
        "file_size_bytes",
        "throughput_mb_s",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            payload = result.to_payload()
            dataset = payload["dataset"]
            writer.writerow(
                {
                    "profile": dataset["profile"],
                    "size": dataset["size"],
                    "rows": dataset["rows"],
                    "columns": dataset["columns"],
                    "format_id": payload["format_id"],
                    "backend_id": payload["backend_id"],
                    "operation": payload["operation"],
                    "success": payload["success"],
                    "skipped": payload["skipped"],
                    "elapsed_ms": f"{payload['elapsed_ms']:.6f}",
                    "cpu_ms": f"{payload['cpu_ms']:.6f}",
                    "rss_before_bytes": payload["rss_before_bytes"],
                    "rss_after_bytes": payload["rss_after_bytes"],
                    "rss_peak_bytes": payload["rss_peak_bytes"],
                    "rss_delta_bytes": payload["rss_delta_bytes"],
                    "rss_peak_delta_bytes": payload["rss_peak_delta_bytes"],
                    "file_size_bytes": payload["file_size_bytes"],
                    "throughput_mb_s": f"{payload['throughput_mb_s']:.6f}",
                    "error": payload["error"],
                }
            )
