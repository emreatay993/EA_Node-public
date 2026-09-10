from __future__ import annotations

import importlib.util

from ea_node_editor.addons.tabular_data.metadata import (
    TABULAR_DATA_ADDON_ID,
    TABULAR_DATA_ADDON_MANIFEST,
    TABULAR_DATA_DEPENDENCIES,
    TABULAR_DATA_TOOLCHAINS,
)
from ea_node_editor.nodes.plugin_contracts import (
    PluginAvailability,
    PluginBackendDescriptor,
)


TABULAR_DATA_FUNCTION_TYPE_IDS = (
    "tabular.input",
    "tabular.table_filter",
    "tabular.array_slice_2d",
    "tabular.write_table_filter",
    "tabular.write_array_slice_2d",
    "tabular.materialize_table_filter",
    "tabular.materialize_array_slice_2d",
)


def _find_spec(module_name: str):
    try:
        return importlib.util.find_spec(module_name)
    except (ImportError, ModuleNotFoundError, ValueError):
        return None


def missing_tabular_data_dependencies() -> tuple[str, ...]:
    return tuple(
        dependency
        for dependency in TABULAR_DATA_DEPENDENCIES
        if _find_spec(dependency) is None
    )


def get_tabular_data_addon_availability() -> PluginAvailability:
    missing = missing_tabular_data_dependencies()
    if missing:
        return PluginAvailability.missing_dependency(
            *missing,
            summary=(
                "The optional Tabular Data add-on requires the tabular dependency extra; "
                "missing modules: " + ", ".join(missing) + "."
            ),
        )
    return PluginAvailability.available(
        summary="The optional tabular dependency stack is installed; Tabular Data can be registered."
    )


def load_tabular_data_function_sources() -> tuple[tuple[str, str], ...]:
    from ea_node_editor.addons.tabular_data.function_nodes import SOURCE

    return (("tabular_data.py", SOURCE),)


def create_tabular_property_edit_adapters() -> tuple[object, ...]:
    from ea_node_editor.addons.tabular_data.property_edit_adapter import (
        create_tabular_property_edit_adapters as create_adapters,
    )

    return create_adapters()


TABULAR_DATA_PLUGIN_BACKEND = PluginBackendDescriptor(
    plugin_id=TABULAR_DATA_ADDON_MANIFEST.addon_id,
    display_name=TABULAR_DATA_ADDON_MANIFEST.display_name,
    get_availability=get_tabular_data_addon_availability,
    load_descriptors=lambda: (),
    load_function_sources=load_tabular_data_function_sources,
    function_type_ids=TABULAR_DATA_FUNCTION_TYPE_IDS,
    addon_manifest=TABULAR_DATA_ADDON_MANIFEST,
    toolchains=TABULAR_DATA_TOOLCHAINS,
)
PLUGIN_BACKENDS = (TABULAR_DATA_PLUGIN_BACKEND,)

__all__ = [
    "PLUGIN_BACKENDS",
    "TABULAR_DATA_ADDON_ID",
    "TABULAR_DATA_ADDON_MANIFEST",
    "TABULAR_DATA_DEPENDENCIES",
    "TABULAR_DATA_PLUGIN_BACKEND",
    "TABULAR_DATA_FUNCTION_TYPE_IDS",
    "TABULAR_DATA_TOOLCHAINS",
    "create_tabular_property_edit_adapters",
    "get_tabular_data_addon_availability",
    "load_tabular_data_function_sources",
    "missing_tabular_data_dependencies",
]
