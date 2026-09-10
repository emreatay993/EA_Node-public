# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata


# The upstream pyarrow hook collects every pyarrow submodule. In the COREX full
# profile that pushes PyInstaller into optional test/dev/native adapters the app
# never uses, and PyInstaller's isolated dependency scan can access-violate on
# Windows. Keep this hook aligned with loader_cache_service's preload list.
hiddenimports = [
    "pyarrow._compute",
    "pyarrow._csv",
    "pyarrow._dataset",
    "pyarrow._dataset_orc",
    "pyarrow._dataset_parquet",
    "pyarrow._fs",
    "pyarrow._parquet",
    "pyarrow.compute",
    "pyarrow.csv",
    "pyarrow.dataset",
    "pyarrow.fs",
    "pyarrow.parquet",
]

datas = collect_data_files(
    "pyarrow",
    excludes=[
        "**/benchmark*",
        "**/conftest.py",
        "**/tests/**",
        "**/*_tests.*",
    ],
)
datas += copy_metadata("pyarrow")
binaries = collect_dynamic_libs("pyarrow")
