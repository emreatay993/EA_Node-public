# Purpose: Register Mechanical semantic contracts without loading Ansys runtimes.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_contracts.py, tests/mechanical_catalogue/test_catalogue.py, tests/mechanical_catalogue/test_image_export.py, tests/mechanical_catalogue/test_snippets.py, tests/mechanical_catalogue/test_standalone_save.py

from __future__ import annotations

from importlib.metadata import distributions
import os
from pathlib import Path

from ea_node_editor.addons.mechanical.contracts import (
    MECHANICAL_CONTRACT_MANIFEST,
    MECHANICAL_DATA_TYPE_FAMILY,
    MECHANICAL_DATA_TYPES,
)
from ea_node_editor.nodes.plugin_contracts import (
    AddOnManifest,
    PluginAvailability,
    PluginBackendDescriptor,
    PluginProvenance,
)
from ea_node_editor.addons.mechanical.property_edit import (
    create_mechanical_property_edit_adapters,
)

MECHANICAL_ADDON_ID = "mechanical.corex"
_DEPENDENCIES = ("ansys-mechanical-core", "ansys-workbench-core", "h5py", "numpy", "pandas")
MECHANICAL_FUNCTION_TYPE_IDS = (
    "mechanical.open_model",
    "mechanical.search_tree",
    "mechanical.fea_table",
    "mechanical.camera_views",
    "mechanical.export_image",
    "mechanical.run_script",
    "mechanical.apdl_snippet",
    "mechanical.save_model",
)
_DISCOVERED_RELEASES: tuple[int, ...] = ()
_MECHANICAL_PACKAGE_ROOT = Path(__file__).resolve().parent


MECHANICAL_ADDON_MANIFEST = AddOnManifest(
    addon_id=MECHANICAL_ADDON_ID,
    display_name="Mechanical",
    apply_policy="hot_apply",
    vendor="COREX",
    version="1.0.0",
    summary="Use typed Mechanical models, objects, properties, views, tables, and images.",
    details="Provides typed Mechanical model opening, data-only discovery, tables, camera snapshots, viewport images, mutations, and explicit standalone or whole-Workbench saving.",
    dependencies=_DEPENDENCIES,
    data_type_families=(MECHANICAL_DATA_TYPE_FAMILY,),
    data_types=MECHANICAL_DATA_TYPES,
)


def get_mechanical_addon_availability() -> PluginAvailability:
    global _DISCOVERED_RELEASES
    installed = {
        str(distribution.metadata.get("Name", "")).casefold().replace("_", "-")
        for distribution in distributions()
    }
    missing = tuple(
        distribution
        for distribution in _DEPENDENCIES
        if distribution.casefold() not in installed
    )
    if missing:
        return PluginAvailability.missing_dependency(
            *missing,
            summary="Mechanical Python packages are unavailable; no Ansys process was started.",
        )
    _DISCOVERED_RELEASES = tuple(
        sorted(
            {
                int(name.removeprefix("AWP_ROOT"))
                for name, root in os.environ.items()
                if name.startswith("AWP_ROOT")
                and name.removeprefix("AWP_ROOT").isdigit()
                and int(name.removeprefix("AWP_ROOT")) >= 261
                and (Path(root) / "aisol" / "bin" / "winx64" / "AnsysWBU.exe").is_file()
            },
            reverse=True,
        )
    )
    return PluginAvailability.available(
        summary="Mechanical Python packages are available; installations are checked when a model opens."
    )


def mechanical_release_choices() -> tuple[int, ...]:
    """Return the last add-on-discovery snapshot without performing UI-time I/O."""
    return _DISCOVERED_RELEASES


def record_mechanical_release_choices(releases: tuple[int, ...]) -> None:
    global _DISCOVERED_RELEASES
    _DISCOVERED_RELEASES = tuple(sorted({int(code) for code in releases if int(code) >= 261}, reverse=True))


MECHANICAL_PLUGIN_BACKEND = PluginBackendDescriptor(
    plugin_id=MECHANICAL_ADDON_ID,
    display_name=MECHANICAL_ADDON_MANIFEST.display_name,
    get_availability=get_mechanical_addon_availability,
    load_descriptors=lambda: (),
    load_function_sources=lambda: (("mechanical_nodes.py", _function_source()),),
    function_type_ids=MECHANICAL_FUNCTION_TYPE_IDS,
    addon_manifest=MECHANICAL_ADDON_MANIFEST,
    data_type_families=MECHANICAL_CONTRACT_MANIFEST.data_type_families,
    data_types=MECHANICAL_CONTRACT_MANIFEST.data_types,
    provenance=PluginProvenance(
        kind="package",
        source_path=_MECHANICAL_PACKAGE_ROOT / "function_nodes.py",
        package_root=_MECHANICAL_PACKAGE_ROOT,
        package_name=_MECHANICAL_PACKAGE_ROOT.name,
    ),
)


def _function_source() -> str:
    from ea_node_editor.addons.mechanical.function_nodes import SOURCE
    return SOURCE


PLUGIN_BACKENDS = (MECHANICAL_PLUGIN_BACKEND,)

__all__ = [
    "MECHANICAL_ADDON_ID",
    "MECHANICAL_ADDON_MANIFEST",
    "MECHANICAL_FUNCTION_TYPE_IDS",
    "MECHANICAL_PLUGIN_BACKEND",
    "PLUGIN_BACKENDS",
    "get_mechanical_addon_availability",
    "create_mechanical_property_edit_adapters",
]
