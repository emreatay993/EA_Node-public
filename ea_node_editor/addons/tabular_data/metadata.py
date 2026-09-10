from __future__ import annotations

from ea_node_editor.nodes.plugin_contracts import (
    AddOnManifest,
    ToolchainRequirementSpec,
    ToolchainSpec,
)

TABULAR_DATA_ADDON_ID = "ea_node_editor.builtins.tabular_data"
TABULAR_DATA_ADDON_VERSION = "0.1.0"
TABULAR_DATA_ADDON_CATEGORY = "Data"
TABULAR_DATA_TOOLCHAIN_ID = "tabular_data.python_runtime"
TABULAR_DATA_DEPENDENCIES = (
    "numpy",
    "pandas",
    "polars",
    "pyarrow",
    "duckdb",
    "openpyxl",
    "h5py",
    "tables",
)

TABULAR_DATA_TOOLCHAINS = (
    ToolchainSpec(
        toolchain_id=TABULAR_DATA_TOOLCHAIN_ID,
        display_name="Tabular Data Python Runtime",
        kind="python",
        language="python",
        requirements=tuple(
            ToolchainRequirementSpec(
                requirement_id=dependency,
                kind="python_module",
                display_name=dependency,
                import_name=dependency,
            )
            for dependency in TABULAR_DATA_DEPENDENCIES
        ),
        notes="Required only when the optional Tabular Data add-on is enabled.",
    ),
)

TABULAR_DATA_ADDON_MANIFEST = AddOnManifest(
    addon_id=TABULAR_DATA_ADDON_ID,
    display_name="Tabular Data",
    apply_policy="hot_apply",
    vendor="COREX",
    version=TABULAR_DATA_ADDON_VERSION,
    summary="Enable tabular and dense-array data workflows when the optional tabular stack is installed.",
    details=(
        "Provides the repo-local Tabular Data Input node, "
        "lazy tabular/array references, loaders, managed cache, and preview surfaces. "
        "The add-on remains dependency-gated behind the tabular extra."
    ),
    dependencies=TABULAR_DATA_DEPENDENCIES,
    toolchains=TABULAR_DATA_TOOLCHAINS,
)

__all__ = [
    "TABULAR_DATA_ADDON_CATEGORY",
    "TABULAR_DATA_ADDON_ID",
    "TABULAR_DATA_ADDON_MANIFEST",
    "TABULAR_DATA_ADDON_VERSION",
    "TABULAR_DATA_DEPENDENCIES",
    "TABULAR_DATA_TOOLCHAIN_ID",
    "TABULAR_DATA_TOOLCHAINS",
]
