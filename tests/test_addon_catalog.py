from __future__ import annotations

from types import SimpleNamespace

from ea_node_editor.addons import catalog as addon_catalog
from ea_node_editor.addons.catalog import (
    TABULAR_DATA_ADDON_ID,
    AddOnRegistration,
    registered_addon_registration_by_id,
)
from ea_node_editor.addons.contracts import AddOnRecord, AddOnState
from ea_node_editor.app_preferences import (
    default_app_preferences_document,
    set_addon_state,
)
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.nodes.plugin_contracts import (
    AddOnManifest,
    PluginAvailability,
    PluginBackendDescriptor,
    PluginDescriptor,
    RuntimeBackendSpec,
)


def _descriptor(type_id: str, display_name: str) -> PluginDescriptor:
    spec = NodeTypeSpec(
        type_id=type_id,
        display_name=display_name,
        category_path=("Packet Tests",),
        icon="packet",
        ports=(),
        properties=(),
    )
    return PluginDescriptor(spec=spec, factory=lambda: None)  # type: ignore[arg-type]


def test_addon_registration_lookup_requires_canonical_addon_id() -> None:
    assert registered_addon_registration_by_id(TABULAR_DATA_ADDON_ID) is not None
    assert registered_addon_registration_by_id("tabular_data") is None


def test_discover_addon_records_reports_generic_manifest_and_state(monkeypatch) -> None:
    restart_runtime_backend = RuntimeBackendSpec(
        backend_id="packet.restart.runtime",
        display_name="Packet Restart Runtime",
        kind="python",
        adapter_module="packet.restart.runtime",
        adapter_factory="create_runtime",
    )
    available_backend = PluginBackendDescriptor(
        plugin_id="packet.restart",
        display_name="Packet Restart Add-On",
        get_availability=lambda: PluginAvailability.available("ready"),
        load_descriptors=lambda: (_descriptor("packet.restart.node", "Restart Node"),),
    )
    unavailable_backend = PluginBackendDescriptor(
        plugin_id="packet.unavailable",
        display_name="Packet Unavailable Add-On",
        get_availability=lambda: PluginAvailability.missing_dependency(
            "packet.unavailable.dep",
            summary="dependency missing",
        ),
        load_descriptors=lambda: (
            _descriptor("packet.unavailable.node", "Unavailable Node"),
        ),
    )
    registrations = (
        AddOnRegistration(
            manifest=AddOnManifest(
                addon_id="packet.restart",
                display_name="Packet Restart Add-On",
                apply_policy="restart_required",
                vendor="Packet Vendor",
                summary="Restart managed add-on",
                details="Requires a restart to finish applying.",
                dependencies=("packet.restart.dep",),
                runtime_backends=(restart_runtime_backend,),
            ),
            backend_module="packet.restart.module",
            backend_id="packet.restart",
            version_resolver_attr="resolve_version",
        ),
        AddOnRegistration(
            manifest=AddOnManifest(
                addon_id="packet.unavailable",
                display_name="Packet Unavailable Add-On",
                apply_policy="hot_apply",
                vendor="Packet Vendor",
                summary="Unavailable add-on",
                details="Stays unavailable until its dependency is installed.",
                dependencies=("packet.unavailable.dep",),
            ),
            backend_module="packet.unavailable.module",
            backend_id="packet.unavailable",
        ),
    )
    fake_modules = {
        "packet.restart.module": SimpleNamespace(
            PLUGIN_BACKENDS=(available_backend,),
            resolve_version=lambda: "9.9.9",
        ),
        "packet.unavailable.module": SimpleNamespace(
            PLUGIN_BACKENDS=(unavailable_backend,),
        ),
    }
    preferences = set_addon_state(
        default_app_preferences_document(),
        "packet.restart",
        enabled=False,
        pending_restart=True,
    )

    monkeypatch.setattr(addon_catalog, "REGISTERED_ADDON_REGISTRATIONS", registrations)
    monkeypatch.setattr(
        addon_catalog.importlib,
        "import_module",
        lambda module_name: fake_modules[module_name],
    )

    records = addon_catalog.discover_addon_records(preferences_document=preferences)
    records_by_id = {record.addon_id: record for record in records}

    restart_record = records_by_id["packet.restart"]
    assert isinstance(restart_record, AddOnRecord)
    assert isinstance(restart_record.state, AddOnState)
    assert restart_record.status == "pending_restart"
    assert restart_record.apply_policy == "restart_required"
    assert restart_record.vendor == "Packet Vendor"
    assert restart_record.version == "9.9.9"
    assert restart_record.summary == "Restart managed add-on"
    assert restart_record.details == "Requires a restart to finish applying."
    assert restart_record.provided_node_type_ids == ("packet.restart.node",)
    assert restart_record.runtime_backends == (restart_runtime_backend,)
    assert restart_record.manifest.contract_manifest.runtime_backends == (
        restart_runtime_backend,
    )

    unavailable_record = records_by_id["packet.unavailable"]
    assert unavailable_record.status == "unavailable"
    assert unavailable_record.apply_policy == "hot_apply"
    assert unavailable_record.version == ""
    assert unavailable_record.availability.missing_dependencies == (
        "packet.unavailable.dep",
    )
    assert unavailable_record.provided_node_type_ids == ()
