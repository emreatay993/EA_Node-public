from __future__ import annotations

import json
from pathlib import Path

import pytest

from ea_node_editor.addons.tabular_data import loader_cache_service as loader_module
from ea_node_editor.addons.tabular_data.loader_cache_service import (
    MissingTabularDependencyError,
    SourceStats,
    TabularLoadOptions,
    TabularLoaderCacheService,
)
from ea_node_editor.settings import (
    DEFAULT_TABULAR_DATA_SETTINGS,
    TABULAR_DATA_BACKEND_POLICY_REVISION,
    TABULAR_DATA_CACHE_FORMAT,
)


def test_shared_policy_configures_before_or_after_first_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader_module.reset_shared_tabular_loader_cache_service()
    original_service_type = loader_module.TabularLoaderCacheService
    constructed: list[TabularLoaderCacheService] = []

    def recording_service(*args, **kwargs) -> TabularLoaderCacheService:  # noqa: ANN002, ANN003
        service = original_service_type(*args, **kwargs)
        constructed.append(service)
        return service

    monkeypatch.setattr(loader_module, "TabularLoaderCacheService", recording_service)

    loader_module.set_shared_tabular_ui_thread_conversion_allowed(False)
    assert constructed == []

    service = loader_module.shared_tabular_loader_cache_service()
    assert constructed == [service]
    assert service.ui_thread_conversion_allowed is False

    loader_module.set_shared_tabular_ui_thread_conversion_allowed(True)
    assert loader_module.shared_tabular_loader_cache_service() is service
    assert service.ui_thread_conversion_allowed is True

    loader_module.reset_shared_tabular_loader_cache_service()
    reset_service = loader_module.shared_tabular_loader_cache_service()
    assert reset_service is not service
    assert reset_service.ui_thread_conversion_allowed is True


def test_default_settings_publish_app_managed_parquet_cache_policy() -> None:
    assert DEFAULT_TABULAR_DATA_SETTINGS["backend_policy_revision"] == TABULAR_DATA_BACKEND_POLICY_REVISION
    assert DEFAULT_TABULAR_DATA_SETTINGS["cache_format"] == TABULAR_DATA_CACHE_FORMAT == "parquet"
    assert DEFAULT_TABULAR_DATA_SETTINGS["cache_dirname"] == "tabular_data_cache"
    assert DEFAULT_TABULAR_DATA_SETTINGS["small_file_bytes"] == 100 * 1024 * 1024
    assert DEFAULT_TABULAR_DATA_SETTINGS["large_warning_bytes"] == 1024 * 1024 * 1024
    assert DEFAULT_TABULAR_DATA_SETTINGS["explicit_materialization_bytes"] == 5 * 1024 * 1024 * 1024


def test_shared_cache_uses_lazy_isolated_pytest_directory(
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_dir = loader_module.tabular_data_cache_dir()
    assert cache_dir.parent == tmp_path_factory.getbasetemp()
    assert cache_dir.name.startswith("tabular_cache_")
    assert not cache_dir.exists()

    source = tmp_path / "data.csv"
    source.write_text("name,value\nalpha,1\n", encoding="utf-8")
    service = loader_module.shared_tabular_loader_cache_service()
    assert service.cache_dir == cache_dir

    monkeypatch.setattr(loader_module, "_import_optional", lambda *_args, **_kwargs: object())

    def run_cache_io(_operation, *args):
        if args:
            return args[-1].write_bytes(b"test parquet")
        return 1

    monkeypatch.setattr(
        service,
        "_run_io",
        run_cache_io,
    )

    entry = service.ensure_parquet_cache(source)

    assert cache_dir.is_dir()
    assert entry.cache_path.is_file()
    assert entry.metadata_path.is_file()


def test_parquet_cache_key_tracks_source_identity_options_selection_and_policy_revision(
    tmp_path: Path,
) -> None:
    source = tmp_path / "data.csv"
    source.write_text("name,value\nalpha,1\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    base = service.parquet_cache_key(source, TabularLoadOptions())
    with_schema_hint = service.parquet_cache_key(
        source,
        TabularLoadOptions(schema_hints={"value": "int64"}),
    )
    with_selection = service.parquet_cache_key(source, TabularLoadOptions(), selected_object="table")
    assert base.key != with_schema_hint.key
    assert base.key != with_selection.key
    assert base.payload["backend_policy_revision"] == TABULAR_DATA_BACKEND_POLICY_REVISION
    assert base.payload["source_path"] == str(source.resolve())

    source.write_text("name,value\nalpha,1\nbeta,2\n", encoding="utf-8")
    changed_source = service.parquet_cache_key(source, TabularLoadOptions())
    assert changed_source.key != base.key


def test_existing_cache_entry_is_returned_from_metadata_without_importing_pyarrow(
    tmp_path: Path,
) -> None:
    source = tmp_path / "data.csv"
    source.write_text("name,value\nalpha,1\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")
    cache_key = service.parquet_cache_key(source)
    cache_path, metadata_path = service.parquet_cache_paths(cache_key.key)
    cache_path.parent.mkdir(parents=True)
    cache_path.write_bytes(b"existing parquet")
    metadata = {
        "kind": "tabular_data_parquet_cache",
        "key": cache_key.key,
        "payload": cache_key.payload,
        "cache_path": str(cache_path),
        "backend_policy_revision": TABULAR_DATA_BACKEND_POLICY_REVISION,
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    entry = service.ensure_parquet_cache(source)

    assert entry.key == cache_key.key
    assert entry.cache_path == cache_path
    assert entry.metadata["payload"]["source_size_bytes"] == source.stat().st_size


def test_missing_pyarrow_for_cache_creation_is_format_specific_and_recoverable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "data.csv"
    source.write_text("name,value\nalpha,1\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    def fail_import(module_name: str, *, format_id: str, purpose: str):
        if module_name == "pyarrow.parquet":
            raise MissingTabularDependencyError(
                format_id=format_id,
                dependency="pyarrow",
                purpose=purpose,
            )
        raise AssertionError(module_name)

    monkeypatch.setattr(
        "ea_node_editor.addons.tabular_data.loader_cache_service._import_optional",
        fail_import,
    )

    with pytest.raises(MissingTabularDependencyError) as exc_info:
        service.ensure_parquet_cache(source)
    assert exc_info.value.format_id == "parquet_cache"
    assert exc_info.value.dependency == "pyarrow"
    assert exc_info.value.recoverable is True


def test_cache_key_uses_mtime_size_and_backend_policy_revision_from_source_stats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "data.csv"
    source.write_text("name,value\nalpha,1\n", encoding="utf-8")
    service = TabularLoaderCacheService(cache_dir=tmp_path / "cache")

    monkeypatch.setattr(service, "_source_stats", lambda _path: SourceStats(size_bytes=10, mtime_ns=1))
    first = service.parquet_cache_key(source)
    monkeypatch.setattr(service, "_source_stats", lambda _path: SourceStats(size_bytes=10, mtime_ns=2))
    changed_mtime = service.parquet_cache_key(source)
    monkeypatch.setattr(service, "_source_stats", lambda _path: SourceStats(size_bytes=11, mtime_ns=1))
    changed_size = service.parquet_cache_key(source)

    assert first.key != changed_mtime.key
    assert first.key != changed_size.key
    assert first.payload["backend_policy_revision"] == TABULAR_DATA_BACKEND_POLICY_REVISION
