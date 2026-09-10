from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SUPPORTED_BACKENDS = ("numpy", "pandas", "polars", "arrow", "duckdb")
DEFAULT_FORMATS = (
    "csv",
    "tsv",
    "txt",
    "fixed_width_txt",
    "jsonl",
    "npy",
    "npz",
    "parquet",
    "feather",
    "hdf5",
    "xlsx",
    "orc",
)
DEFAULT_OPERATIONS = (
    "write",
    "read",
    "schema",
    "preview",
    "projection",
    "lookup",
    "filter",
    "groupby",
    "sort",
    "compute",
    "convert",
)
DEFAULT_PROFILES = ("mixed_table",)
SIZE_PRESETS = {
    "small": {"rows": 1_000, "columns": 12, "target_bytes": 0},
    "medium": {"rows": 50_000, "columns": 24, "target_bytes": 0},
    "large": {"rows": 25_000_000, "columns": 16, "target_bytes": 5 * 1024**3},
}


class TabularBenchmarkError(RuntimeError):
    """Base error for tabular benchmark setup and execution."""


class OptionalDependencyMissingError(TabularBenchmarkError):
    """Raised when a benchmark path needs an optional dependency."""


class UnsupportedBenchmarkCaseError(TabularBenchmarkError):
    """Raised when a backend, format, or operation combination is unsupported."""


@dataclass(slots=True, frozen=True)
class DatasetSpec:
    size: str
    profile: str = "mixed_table"
    rows: int = 1_000
    columns: int = 12
    seed: int = 1337
    target_bytes: int = 0

    @classmethod
    def from_size(cls, size: str, *, profile: str = "mixed_table", seed: int = 1337) -> "DatasetSpec":
        try:
            preset = SIZE_PRESETS[size]
        except KeyError as exc:
            raise ValueError(f"Unknown dataset size: {size}") from exc
        return cls(
            size=size,
            profile=profile,
            rows=int(preset["rows"]),
            columns=int(preset["columns"]),
            seed=seed,
            target_bytes=int(preset["target_bytes"]),
        )

    @property
    def dataset_id(self) -> str:
        return f"{self.profile}_{self.size}_{self.rows}x{self.columns}_seed{self.seed}"

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class BenchmarkConfig:
    output_dir: Path
    sizes: tuple[str, ...] = ("small",)
    profiles: tuple[str, ...] = DEFAULT_PROFILES
    formats: tuple[str, ...] = ("csv", "parquet", "npy")
    backends: tuple[str, ...] = ("pandas", "polars", "duckdb", "numpy")
    operations: tuple[str, ...] = DEFAULT_OPERATIONS
    preview_rows: int = 50
    seed: int = 1337
    allow_large: bool = False
    reuse_datasets: bool = False
    headless: bool = True
    max_errors: int = 0

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["output_dir"] = str(self.output_dir)
        return payload


@dataclass(slots=True)
class BenchmarkResult:
    dataset: DatasetSpec
    format_id: str
    backend_id: str
    operation: str
    elapsed_ms: float
    cpu_ms: float
    rss_before_bytes: int
    rss_after_bytes: int
    file_size_bytes: int
    success: bool
    throughput_mb_s: float = 0.0
    rows: int | None = None
    columns: int | None = None
    skipped: bool = False
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    rss_peak_bytes: int = 0

    def to_payload(self) -> dict[str, Any]:
        rss_peak_bytes = self.rss_peak_bytes or max(self.rss_before_bytes, self.rss_after_bytes)
        return {
            "dataset": self.dataset.to_payload(),
            "format_id": self.format_id,
            "backend_id": self.backend_id,
            "operation": self.operation,
            "elapsed_ms": self.elapsed_ms,
            "cpu_ms": self.cpu_ms,
            "rss_before_bytes": self.rss_before_bytes,
            "rss_after_bytes": self.rss_after_bytes,
            "rss_peak_bytes": rss_peak_bytes,
            "rss_delta_bytes": self.rss_after_bytes - self.rss_before_bytes,
            "rss_peak_delta_bytes": rss_peak_bytes - self.rss_before_bytes,
            "file_size_bytes": self.file_size_bytes,
            "success": self.success,
            "skipped": self.skipped,
            "throughput_mb_s": self.throughput_mb_s,
            "rows": self.rows,
            "columns": self.columns,
            "error": self.error,
            "details": self.details,
        }
