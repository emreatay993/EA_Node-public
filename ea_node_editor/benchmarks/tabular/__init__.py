"""Tabular backend and file-format benchmark workbench."""

from ea_node_editor.benchmarks.tabular.contracts import (
    BenchmarkConfig,
    BenchmarkResult,
    DatasetSpec,
)
from ea_node_editor.benchmarks.tabular.runner import run_benchmark_matrix

__all__ = [
    "BenchmarkConfig",
    "BenchmarkResult",
    "DatasetSpec",
    "run_benchmark_matrix",
]

