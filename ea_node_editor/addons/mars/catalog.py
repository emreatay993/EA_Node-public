# Purpose: Report managed MARS availability and lazily publish MARS function nodes.
# Map: feature_routes/mars_solver_addon.md
# Tests: tests/test_mars_nodes.py

from __future__ import annotations

from importlib.metadata import distributions
from pathlib import Path

from ea_node_editor.addons.mars.metadata import (
    MARS_ADDON_ID,
    MARS_ADDON_MANIFEST,
    MARS_ARTIFACTS,
    MARS_DISTRIBUTION,
    MARS_RUNTIME_BACKENDS,
    MARS_TOOLCHAINS,
)
from ea_node_editor.addons.mars.runtime import managed_mars_batch_executable
from ea_node_editor.nodes.plugin_contracts import (
    PluginAvailability,
    PluginBackendDescriptor,
    PluginProvenance,
)


_MARS_PACKAGE_ROOT = Path(__file__).resolve().parent
MARS_FUNCTION_TYPE_IDS = (
    "mars.batch_solve",
    "mars.time_history",
    "mars.run_job",
)


def _distribution_token(value: str) -> str:
    return str(value).strip().casefold().replace("_", "-")


def _managed_mars_version() -> str:
    from ea_node_editor.execution.managed_runtime import resolve_addon_runtime_paths

    paths = resolve_addon_runtime_paths()
    site_packages = [paths.venv_dir / "Lib" / "site-packages"]
    site_packages.extend((paths.venv_dir / "lib").glob("python*/site-packages"))
    expected = _distribution_token(MARS_DISTRIBUTION)
    for root in site_packages:
        if not root.is_dir():
            continue
        for distribution in distributions(path=[str(root)]):
            name = distribution.metadata.get("Name", "")
            if _distribution_token(name) == expected:
                return str(distribution.version or "").strip()
    return ""


def get_mars_addon_availability() -> PluginAvailability:
    from ea_node_editor.execution.managed_runtime import resolve_addon_runtime_paths

    missing: list[str] = []
    paths = resolve_addon_runtime_paths()
    installed_version = _managed_mars_version()
    expected_version = MARS_ADDON_MANIFEST.version
    if not installed_version:
        missing.append(MARS_DISTRIBUTION)
    elif installed_version != expected_version:
        missing.append(f"update {MARS_DISTRIBUTION} to {expected_version}")
    executable = managed_mars_batch_executable()
    if not executable.is_file():
        missing.append(str(executable))
    if missing:
        if not installed_version:
            summary = (
                "MARS is not installed in COREX's active Python environment: "
                f"{paths.python_executable}."
            )
        elif installed_version != expected_version:
            summary = (
                f"MARS {installed_version} is installed in COREX's active Python environment, "
                f"but version {expected_version} is required: {paths.python_executable}."
            )
        else:
            summary = (
                "MARSBatch is not available beside COREX's Python executable: "
                f"{executable}."
            )
        return PluginAvailability.missing_dependency(
            *missing,
            summary=summary,
        )
    return PluginAvailability.available(
        summary=f"MARSBatch is available at {executable}.",
    )


def resolve_mars_plugin_version() -> str:
    return _managed_mars_version()


def load_mars_function_sources() -> tuple[tuple[str, str], ...]:
    from ea_node_editor.addons.mars.function_nodes import SOURCE

    return (("mars_nodes.py", SOURCE),)


MARS_PLUGIN_BACKEND = PluginBackendDescriptor(
    plugin_id=MARS_ADDON_ID,
    display_name=MARS_ADDON_MANIFEST.display_name,
    get_availability=get_mars_addon_availability,
    load_descriptors=lambda: (),
    load_function_sources=load_mars_function_sources,
    function_type_ids=MARS_FUNCTION_TYPE_IDS,
    addon_manifest=MARS_ADDON_MANIFEST,
    runtime_backends=MARS_RUNTIME_BACKENDS,
    toolchains=MARS_TOOLCHAINS,
    artifacts=MARS_ARTIFACTS,
    provenance=PluginProvenance(
        kind="package",
        source_path=_MARS_PACKAGE_ROOT / "nodes.py",
        package_root=_MARS_PACKAGE_ROOT,
        package_name=_MARS_PACKAGE_ROOT.name,
    ),
)
PLUGIN_BACKENDS = (MARS_PLUGIN_BACKEND,)

__all__ = [
    "MARS_ADDON_ID",
    "MARS_ADDON_MANIFEST",
    "MARS_FUNCTION_TYPE_IDS",
    "MARS_PLUGIN_BACKEND",
    "PLUGIN_BACKENDS",
    "get_mars_addon_availability",
    "load_mars_function_sources",
    "resolve_mars_plugin_version",
]
