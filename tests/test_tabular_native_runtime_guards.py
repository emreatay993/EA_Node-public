"""Guards for the pyarrow/Qt native-runtime constraints.

Empirically established on Windows (pyarrow 24.0 + PyQt6): lazily loading
additional native extension DLLs (pyarrow.dataset, pyarrow._fs, duckdb) after
a Qt Quick engine has run access-violates the process — the DLL static
initializers corrupt memory and a later native call (often a QML signal emit)
crashes. Two rules keep the app safe:

1. The tabular addon preloads every pyarrow submodule it uses at import time
   (registry build happens before any QML engine exists).
2. duckdb must never be imported by GUI-process code paths; the preview query
   backend uses pyarrow.compute instead.
"""
from __future__ import annotations

import importlib.util
import inspect
import sys

import pytest

import ea_node_editor.addons.tabular_data.loader_cache_service as loader_module
import ea_node_editor.addons.tabular_data.preview_query as query_module
import ea_node_editor.addons.tabular_data.source_backends as backends_module


def test_tabular_addon_preloads_pyarrow_native_submodules() -> None:
    if importlib.util.find_spec("pyarrow") is None:
        pytest.skip("pyarrow not installed")
    # loader_cache_service imported above; the preload must already be done.
    for module_name in (
        "pyarrow",
        "pyarrow.compute",
        "pyarrow.csv",
        "pyarrow.dataset",
        "pyarrow.fs",
        "pyarrow.parquet",
    ):
        assert module_name in sys.modules, f"{module_name} must preload at addon import"


def test_tabular_preload_skips_pyinstaller_analysis_child(monkeypatch: pytest.MonkeyPatch) -> None:
    imported: list[str] = []

    def fake_import_module(module_name: str) -> object:
        imported.append(module_name)
        return object()

    monkeypatch.setitem(sys.modules, "PyInstaller.isolated._child", object())
    monkeypatch.setattr(loader_module.importlib, "import_module", fake_import_module)

    loader_module._preload_native_tabular_runtime()

    assert imported == []


def test_loader_service_never_imports_duckdb_or_streaming_csv_reader() -> None:
    source = "\n".join(
        inspect.getsource(module)
        for module in (loader_module, backends_module, query_module)
    )
    assert 'import_module("duckdb")' not in source
    assert "import duckdb" not in source
    # pyarrow.csv.open_csv's background readahead thread is part of the same
    # crash class; conversions must use the chunked read_csv path.
    assert "open_csv(" not in source
