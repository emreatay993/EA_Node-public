from __future__ import annotations

from dataclasses import dataclass

from ea_node_editor.settings import (
    TABULAR_DATA_BACKEND_POLICY_REVISION,
    TABULAR_DATA_DEFAULT_PREVIEW_COLUMNS,
    TABULAR_DATA_DEFAULT_PREVIEW_ROWS,
    TABULAR_DATA_EXPLICIT_MATERIALIZATION_BYTES,
    TABULAR_DATA_LARGE_WARNING_BYTES,
    TABULAR_DATA_SMALL_FILE_BYTES,
)

SIZE_CLASS_SMALL = "small"
SIZE_CLASS_MEDIUM = "medium"
SIZE_CLASS_LARGE = "large"
SIZE_CLASS_HUGE = "huge"
WARNING_LARGE_SOURCE = "source_larger_than_1_gib"
WARNING_EXPLICIT_MATERIALIZATION_REQUIRED = "explicit_materialization_required_above_5_gib"
CACHE_POLICY_APP_MANAGED_PARQUET = "app_managed_parquet"
CACHE_POLICY_SOURCE_DIRECT = "source_direct"


@dataclass(slots=True, frozen=True)
class TabularBackendPolicy:
    revision: str = TABULAR_DATA_BACKEND_POLICY_REVISION
    small_threshold_bytes: int = TABULAR_DATA_SMALL_FILE_BYTES
    large_warning_bytes: int = TABULAR_DATA_LARGE_WARNING_BYTES
    explicit_materialization_threshold_bytes: int = TABULAR_DATA_EXPLICIT_MATERIALIZATION_BYTES
    preview_row_limit: int = TABULAR_DATA_DEFAULT_PREVIEW_ROWS
    preview_column_limit: int = TABULAR_DATA_DEFAULT_PREVIEW_COLUMNS

    def classify_size(self, size_bytes: int) -> str:
        size = max(0, int(size_bytes))
        if size < self.small_threshold_bytes:
            return SIZE_CLASS_SMALL
        if size <= self.large_warning_bytes:
            return SIZE_CLASS_MEDIUM
        if size <= self.explicit_materialization_threshold_bytes:
            return SIZE_CLASS_LARGE
        return SIZE_CLASS_HUGE

    def warnings_for_size(self, size_bytes: int) -> tuple[str, ...]:
        size = max(0, int(size_bytes))
        warnings: list[str] = []
        if size > self.large_warning_bytes:
            warnings.append(WARNING_LARGE_SOURCE)
        if self.requires_explicit_materialization(size):
            warnings.append(WARNING_EXPLICIT_MATERIALIZATION_REQUIRED)
        return tuple(warnings)

    def requires_explicit_materialization(self, size_bytes: int) -> bool:
        return max(0, int(size_bytes)) > self.explicit_materialization_threshold_bytes

    def choose_table_backend(self, format_id: str, size_bytes: int) -> str:
        normalized = str(format_id).strip().lower()
        size_class = self.classify_size(size_bytes)
        if normalized == "parquet":
            return "pyarrow_parquet_lazy" if size_class in {SIZE_CLASS_LARGE, SIZE_CLASS_HUGE} else "pyarrow_parquet"
        if normalized in {"csv", "tsv", "txt"}:
            return "pyarrow_text_cache" if size_class in {SIZE_CLASS_LARGE, SIZE_CLASS_HUGE} else "python_text_stream"
        if normalized in {"xlsx", "xlsm"}:
            return "openpyxl_stream"
        if normalized == "hdf5":
            return "hdf5_dataset"
        return "tabular_stream"

    def choose_array_backend(self, format_id: str, size_bytes: int) -> str:
        normalized = str(format_id).strip().lower()
        if normalized == "npy":
            return "npy_mmap"
        if normalized == "npz":
            return "npz_archive"
        if normalized == "hdf5":
            return "hdf5_dataset"
        return f"{normalized}_array"


DEFAULT_TABULAR_BACKEND_POLICY = TabularBackendPolicy()

__all__ = [
    "CACHE_POLICY_APP_MANAGED_PARQUET",
    "CACHE_POLICY_SOURCE_DIRECT",
    "DEFAULT_TABULAR_BACKEND_POLICY",
    "SIZE_CLASS_HUGE",
    "SIZE_CLASS_LARGE",
    "SIZE_CLASS_MEDIUM",
    "SIZE_CLASS_SMALL",
    "TABULAR_DATA_BACKEND_POLICY_REVISION",
    "WARNING_EXPLICIT_MATERIALIZATION_REQUIRED",
    "WARNING_LARGE_SOURCE",
    "TabularBackendPolicy",
]
