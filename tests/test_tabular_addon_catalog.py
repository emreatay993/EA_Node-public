from __future__ import annotations

from unittest.mock import patch

from ea_node_editor.addons import catalog as addon_catalog
from ea_node_editor.addons.tabular_data import catalog as tabular_catalog
from ea_node_editor.addons.tabular_data.metadata import (
    TABULAR_DATA_ADDON_CATEGORY,
    TABULAR_DATA_ADDON_ID,
    TABULAR_DATA_ADDON_MANIFEST,
    TABULAR_DATA_ADDON_VERSION,
    TABULAR_DATA_DEPENDENCIES,
    TABULAR_DATA_TOOLCHAIN_ID,
    TABULAR_DATA_TOOLCHAINS,
)
from ea_node_editor.app_preferences import default_app_preferences_document
from ea_node_editor.ui.shell.property_edit_adapters import (
    create_shell_property_edit_adapters,
)


def test_tabular_data_addon_manifest_publishes_stable_shell_metadata() -> None:
    assert TABULAR_DATA_ADDON_ID == "ea_node_editor.builtins.tabular_data"
    assert TABULAR_DATA_ADDON_CATEGORY == "Data"
    assert TABULAR_DATA_ADDON_VERSION == "0.1.0"
    assert TABULAR_DATA_ADDON_MANIFEST.addon_id == TABULAR_DATA_ADDON_ID
    assert TABULAR_DATA_ADDON_MANIFEST.display_name == "Tabular Data"
    assert TABULAR_DATA_ADDON_MANIFEST.apply_policy == "hot_apply"
    assert TABULAR_DATA_ADDON_MANIFEST.vendor == "COREX"
    assert TABULAR_DATA_ADDON_MANIFEST.version == TABULAR_DATA_ADDON_VERSION
    assert TABULAR_DATA_ADDON_MANIFEST.dependencies == TABULAR_DATA_DEPENDENCIES
    assert TABULAR_DATA_ADDON_MANIFEST.runtime_backends == ()
    assert TABULAR_DATA_ADDON_MANIFEST.toolchains == TABULAR_DATA_TOOLCHAINS

    toolchain = TABULAR_DATA_TOOLCHAINS[0]
    assert toolchain.toolchain_id == TABULAR_DATA_TOOLCHAIN_ID
    assert tuple(requirement.import_name for requirement in toolchain.requirements) == TABULAR_DATA_DEPENDENCIES


def test_tabular_data_backend_reports_missing_dependencies_without_importing_backends() -> None:
    missing = {"pandas", "pyarrow", "duckdb"}

    def fake_find_spec(module_name: str):
        return None if module_name in missing else object()

    with patch.object(tabular_catalog, "_find_spec", side_effect=fake_find_spec) as find_spec:
        availability = tabular_catalog.get_tabular_data_addon_availability()

    assert availability.state == "missing_dependency"
    assert availability.missing_dependencies == ("pandas", "pyarrow", "duckdb")
    assert "tabular dependency extra" in availability.summary
    assert [call.args[0] for call in find_spec.call_args_list] == list(TABULAR_DATA_DEPENDENCIES)


def test_tabular_data_backend_reports_available_when_optional_stack_is_discoverable() -> None:
    with patch.object(tabular_catalog, "_find_spec", return_value=object()):
        availability = tabular_catalog.get_tabular_data_addon_availability()

    assert availability.is_available
    assert availability.missing_dependencies == ()


def test_tabular_data_backend_exposes_function_nodes_when_available() -> None:
    with patch.object(tabular_catalog, "_find_spec", return_value=object()):
        availability = tabular_catalog.TABULAR_DATA_PLUGIN_BACKEND.get_availability()

    assert tabular_catalog.TABULAR_DATA_PLUGIN_BACKEND.function_type_ids == (
        "tabular.input",
        "tabular.table_filter",
        "tabular.array_slice_2d",
        "tabular.write_table_filter",
        "tabular.write_array_slice_2d",
        "tabular.materialize_table_filter",
        "tabular.materialize_array_slice_2d",
    )
    assert availability.is_available
    assert tabular_catalog.TABULAR_DATA_PLUGIN_BACKEND.load_descriptors() == ()
    sources = tabular_catalog.TABULAR_DATA_PLUGIN_BACKEND.load_function_sources
    assert sources is not None
    assert tuple(path for path, _source in sources()) == ("tabular_data.py",)
    assert tabular_catalog.TABULAR_DATA_PLUGIN_BACKEND.addon_manifest == TABULAR_DATA_ADDON_MANIFEST
    assert tabular_catalog.TABULAR_DATA_PLUGIN_BACKEND.toolchains == TABULAR_DATA_TOOLCHAINS
    assert tabular_catalog.TABULAR_DATA_PLUGIN_BACKEND.contract_manifest.runtime_backends == ()


def test_registered_addon_catalog_reports_tabular_data_unavailable_without_nodes_when_missing() -> None:
    registration = addon_catalog.registered_addon_registration_by_id(TABULAR_DATA_ADDON_ID)
    assert registration is not None
    assert registration.manifest == TABULAR_DATA_ADDON_MANIFEST
    assert registration.backend_module == "ea_node_editor.addons.tabular_data.catalog"
    assert registration.backend_id == TABULAR_DATA_ADDON_ID

    with patch.object(tabular_catalog, "_find_spec", return_value=None):
        record = addon_catalog.addon_record_by_id(
            TABULAR_DATA_ADDON_ID,
            preferences_document=default_app_preferences_document(),
        )

    assert record is not None
    assert record.status == "unavailable"
    assert record.availability.state == "missing_dependency"
    assert record.availability.missing_dependencies == TABULAR_DATA_DEPENDENCIES
    assert record.provided_node_type_ids == ()
    assert record.manifest.contract_manifest.toolchains == TABULAR_DATA_TOOLCHAINS


def test_registered_addon_catalog_reports_function_ids_when_available() -> None:
    with patch.object(tabular_catalog, "_find_spec", return_value=object()):
        enabled = addon_catalog.addon_record_by_id(
            TABULAR_DATA_ADDON_ID,
            preferences_document=default_app_preferences_document(),
        )
        preferences = default_app_preferences_document()
        preferences["addons"]["states"][TABULAR_DATA_ADDON_ID] = {
            "enabled": False,
            "pending_restart": False,
        }
        disabled = addon_catalog.addon_record_by_id(
            TABULAR_DATA_ADDON_ID,
            preferences_document=preferences,
        )

    assert enabled is not None
    assert enabled.provided_node_type_ids == tabular_catalog.TABULAR_DATA_FUNCTION_TYPE_IDS
    assert disabled is not None
    assert disabled.provided_node_type_ids == tabular_catalog.TABULAR_DATA_FUNCTION_TYPE_IDS


def test_registered_addon_catalog_exposes_tabular_property_edit_adapter_factory() -> None:
    registration = addon_catalog.registered_addon_registration_by_id(TABULAR_DATA_ADDON_ID)
    assert registration is not None
    assert registration.property_edit_adapter_factory_attr == "create_tabular_property_edit_adapters"

    adapters = addon_catalog.create_live_property_edit_adapters(
        preferences_document=default_app_preferences_document(),
    )

    assert [adapter.__class__.__name__ for adapter in adapters] == [
        "TabularDataPropertyEditAdapter",
        "MechanicalPropertyEditAdapter",
    ]
    assert [
        adapter.__class__.__name__
        for adapter in create_shell_property_edit_adapters(
            preferences_document=default_app_preferences_document()
        )
        ] == [
            "PlotPropertyEditAdapter",
            "TabularDataPropertyEditAdapter",
            "MechanicalPropertyEditAdapter",
        ]
