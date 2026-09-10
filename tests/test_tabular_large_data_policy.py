from __future__ import annotations

from pathlib import Path

import pytest

from ea_node_editor.addons.tabular_data.loader_cache_service import (
    LargeDataMaterializationError,
    SourceStats,
    TabularLoadOptions,
    TabularLoaderCacheService,
)
from ea_node_editor.addons.tabular_data.policy import (
    SIZE_CLASS_HUGE,
    SIZE_CLASS_LARGE,
    SIZE_CLASS_MEDIUM,
    SIZE_CLASS_SMALL,
    WARNING_EXPLICIT_MATERIALIZATION_REQUIRED,
    WARNING_LARGE_SOURCE,
    TabularBackendPolicy,
)
from ea_node_editor.runtime_contracts import TabularWindowRequest


def test_backend_policy_encodes_report_backed_size_thresholds() -> None:
    policy = TabularBackendPolicy()

    assert policy.classify_size(100 * 1024 * 1024 - 1) == SIZE_CLASS_SMALL
    assert policy.classify_size(100 * 1024 * 1024) == SIZE_CLASS_MEDIUM
    assert policy.classify_size(1024 * 1024 * 1024) == SIZE_CLASS_MEDIUM
    assert policy.classify_size(1024 * 1024 * 1024 + 1) == SIZE_CLASS_LARGE
    assert policy.classify_size(5 * 1024 * 1024 * 1024 + 1) == SIZE_CLASS_HUGE
    assert policy.warnings_for_size(1024 * 1024 * 1024 + 1) == (WARNING_LARGE_SOURCE,)
    assert policy.warnings_for_size(5 * 1024 * 1024 * 1024 + 1) == (
        WARNING_LARGE_SOURCE,
        WARNING_EXPLICIT_MATERIALIZATION_REQUIRED,
    )


def test_backend_policy_prefers_lazy_large_table_paths_and_npy_mmap() -> None:
    policy = TabularBackendPolicy()

    assert policy.choose_table_backend("csv", 10) == "python_text_stream"
    assert policy.choose_table_backend("csv", 2 * 1024 * 1024 * 1024) == "pyarrow_text_cache"
    assert policy.choose_table_backend("parquet", 2 * 1024 * 1024 * 1024) == "pyarrow_parquet_lazy"
    assert policy.choose_table_backend("xlsx", 10) == "openpyxl_stream"
    assert policy.choose_array_backend("npy", 10) == "npy_mmap"
    assert policy.choose_array_backend("npz", 10) == "npz_archive"


def test_large_text_open_does_not_count_all_rows_and_preview_stays_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "large.csv"
    source.write_text("name,value\nalpha,1\nbeta,2\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    monkeypatch.setattr(
        service,
        "_source_stats",
        lambda _path: SourceStats(size_bytes=2 * 1024 * 1024 * 1024, mtime_ns=1),
    )

    def fail_if_full_count(*_args, **_kwargs):
        raise AssertionError("large preview should not count every text row during open")

    monkeypatch.setattr(service, "_iter_text_records", fail_if_full_count)

    ref = service.open_source(source)
    window = service.window(ref, TabularWindowRequest(row_limit=1, column_limit=2))

    assert ref.row_count is None
    assert ref.backend_id == "pyarrow_text_cache"
    assert WARNING_LARGE_SOURCE in ref.metadata["warnings"]
    # Reads route through the managed parquet cache: typed values, and the
    # total row count backfills from the cache metadata.
    assert window.rows == ({"name": "alpha", "value": 1},)
    assert window.total_rows == 2


def test_large_npz_preview_is_gated_as_archive_unless_explicitly_allowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    numpy = pytest.importorskip("numpy")
    source = tmp_path / "archive.npz"
    numpy.savez(source, array=numpy.arange(4).reshape(2, 2))
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    monkeypatch.setattr(
        service,
        "_source_stats",
        lambda _path: SourceStats(size_bytes=2 * 1024 * 1024 * 1024, mtime_ns=1),
    )

    scan = service.scan_source(source)
    assert scan.selected_object_id == "array"
    assert scan.objects[0].metadata["archive_only"] is True
    with pytest.raises(LargeDataMaterializationError):
        service.open_source(source)

    ref = service.open_source(source, TabularLoadOptions(allow_npz_archive_preview=True))
    assert ref.backend_id == "npz_archive"
    assert ref.shape == (2, 2)


def test_explicit_materialization_gate_is_reported_above_five_gib() -> None:
    policy = TabularBackendPolicy()

    assert policy.requires_explicit_materialization(5 * 1024 * 1024 * 1024) is False
    assert policy.requires_explicit_materialization(5 * 1024 * 1024 * 1024 + 1) is True
