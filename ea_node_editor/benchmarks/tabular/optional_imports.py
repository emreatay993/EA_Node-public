from __future__ import annotations

from importlib import import_module, metadata
from typing import Any

from ea_node_editor.benchmarks.tabular.contracts import OptionalDependencyMissingError


PACKAGE_BY_MODULE = {
    "numpy": "numpy",
    "pandas": "pandas",
    "polars": "polars",
    "pyarrow": "pyarrow",
    "duckdb": "duckdb",
    "h5py": "h5py",
    "tables": "tables",
    "openpyxl": "openpyxl",
    "xlsxwriter": "XlsxWriter",
    "fastexcel": "fastexcel",
    "PyQt6": "PyQt6",
    "psutil": "psutil",
}


def load_module(module_name: str) -> Any:
    try:
        return import_module(module_name)
    except ModuleNotFoundError as exc:
        package_name = PACKAGE_BY_MODULE.get(module_name.split(".", 1)[0], module_name)
        raise OptionalDependencyMissingError(
            f"Optional dependency '{package_name}' is required for this tabular benchmark path."
        ) from exc


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for module_name, package_name in PACKAGE_BY_MODULE.items():
        try:
            versions[module_name] = metadata.version(package_name)
        except metadata.PackageNotFoundError:
            versions[module_name] = "missing"
    return versions

