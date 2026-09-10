from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ea_node_editor.addons.mechanical.catalog import (
    MECHANICAL_FUNCTION_TYPE_IDS,
    MECHANICAL_PLUGIN_BACKEND,
    get_mechanical_addon_availability,
)
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import PythonFunctionAdapter
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.addons.mechanical.function_nodes import SOURCE
from ea_node_editor.nodes.execution_context import NodeInputNotReadyError
from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.run_messages import StartRunCommand
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
    runtime_registry_fingerprint,
)


def test_current_mechanical_declarations_and_open_is_fully_typed() -> None:
    registry = build_default_registry(
        include_public_plugins=False,
        addon_runtime_config=(("mechanical.corex", True),),
    )
    spec = registry.get_spec("mechanical.open_model")
    assert MECHANICAL_FUNCTION_TYPE_IDS == (
        "mechanical.open_model", "mechanical.search_tree", "mechanical.fea_table",
        "mechanical.camera_views", "mechanical.export_image", "mechanical.run_script",
        "mechanical.apdl_snippet",
        "mechanical.save_model",
    )
    assert spec.category_path == ("FEA", "ANSYS", "Mechanical")
    assert spec.solution_reuse_scope == "never"
    assert [(port.key, port.data_type) for port in spec.ports if port.direction == "in"] == [
        ("file", "COREX.DataTypes.Path"),
        ("system", "COREX.DataTypes.String"),
        ("mode", "COREX.DataTypes.String"),
        ("version", "COREX.DataTypes.Int"),
        ("working_folder", "COREX.DataTypes.Path"),
        ("timeout_s", "COREX.DataTypes.Double"),
    ]
    assert [(port.key, port.data_type) for port in spec.ports if port.direction == "out"] == [
        ("model", "COREX.Mechanical.Model"),
        ("info", "COREX.DataTypes.TableValue"),
    ]


def test_catalogue_availability_is_offline(monkeypatch) -> None:
    forbidden = {"ansys.mechanical.core", "ansys.workbench.core", "h5py"}
    before = forbidden & set(sys.modules)
    availability = get_mechanical_addon_availability()
    assert availability is not None
    assert (forbidden & set(sys.modules)) == before
    assert MECHANICAL_PLUGIN_BACKEND.function_type_ids == (
        "mechanical.open_model", "mechanical.search_tree", "mechanical.fea_table",
        "mechanical.camera_views", "mechanical.export_image", "mechanical.run_script",
        "mechanical.apdl_snippet",
        "mechanical.save_model",
    )
    assert MECHANICAL_PLUGIN_BACKEND.provenance is not None
    assert MECHANICAL_PLUGIN_BACKEND.provenance.package_root.name == "mechanical"


def test_mechanical_declares_hdf5_without_importing_it_for_discovery(monkeypatch):
    import builtins
    import ea_node_editor.addons.mechanical.catalog as catalogue

    assert "h5py" in catalogue.MECHANICAL_ADDON_MANIFEST.dependencies
    monkeypatch.setattr(catalogue, "distributions", lambda: [
        SimpleNamespace(metadata={"Name": name})
        for name in catalogue.MECHANICAL_ADDON_MANIFEST.dependencies if name != "h5py"
    ])
    original_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "h5py" or name.startswith("h5py."):
            pytest.fail("UI discovery imported HDF5")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    availability = get_mechanical_addon_availability()
    assert availability == catalogue.PluginAvailability.missing_dependency(
        "h5py", summary="Mechanical Python packages are unavailable; no Ansys process was started."
    )


def test_registered_function_forwards_unconnected_properties_as_settings(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.runtime.execute_open_model",
        lambda ctx, settings: captured.update(file=settings.file, mode=settings.mode) or {},
    )
    namespace = {}
    exec(SOURCE, namespace)
    declaration = discover_plugin_declarations(
        SOURCE, filename="mechanical_nodes.py", allow_reserved_ids=True,
        owner_id="mechanical.corex", allow_internal_metadata=True,
    )[0]
    context = ExecutionContext(
        run_id="run", node_id="open", workspace_id="workspace", inputs={},
        properties={"file": "model.mechdb", "mode": "background", "system": "", "version": 261, "working_folder": "", "timeout_s": 600.0},
        emit_log=lambda *_: None,
    )
    assert PythonFunctionAdapter(
        declaration.spec, namespace["open_mechanical_model"]
    ).execute(context).outputs == {}
    assert captured == {"file": "model.mechdb", "mode": "background"}


def test_registered_function_executes_real_open_with_fake_owned_session(tmp_path, monkeypatch) -> None:
    property_source = tmp_path / "property.mechdb"
    connected_source = tmp_path / "connected.mechdb"
    property_source.write_bytes(b"property")
    connected_source.write_bytes(b"connected")

    class Sessions:
        def open_session(self, **kwargs):
            self.opened = kwargs
            return SimpleNamespace(
                session_id="session", work_path=tmp_path / "work.mechdb", work_root=tmp_path
            )
        def operate(self, _session, **kwargs):
            self.operated = kwargs
            return {"status": "opened", "system_key": "standalone", "catalogue": "info"}
        def register_model(self, _session, **kwargs):
            self.registered = kwargs
            return "model"

    sessions = Sessions()
    services = SimpleNamespace(mechanical_session_service=sessions)
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.runtime.discover_mechanical_releases",
        lambda: (261,),
    )
    namespace = {}
    exec(SOURCE, namespace)
    declaration = discover_plugin_declarations(
        SOURCE, filename="mechanical_nodes.py", allow_reserved_ids=True,
        owner_id="mechanical.corex", allow_internal_metadata=True,
    )[0]
    adapter = PythonFunctionAdapter(declaration.spec, namespace["open_mechanical_model"])
    context = ExecutionContext(
        run_id="run", node_id="open", workspace_id="workspace",
        inputs={"file": str(connected_source)},
        properties={"file": str(property_source), "mode": "background", "system": "", "version": 261, "working_folder": "", "timeout_s": 600.0},
        emit_log=lambda *_: None, path_resolver=lambda value: Path(value),
        worker_services=services,
    )
    assert adapter.execute(context).outputs == {"info": "info", "model": "model"}
    assert sessions.opened["source_path"] == connected_source
    context.inputs["file"] = ""
    with pytest.raises(NodeInputNotReadyError):
        adapter.execute(context)


def test_worker_runtime_loads_registered_mechanical_package(tmp_path) -> None:
    registry = build_default_registry(
        include_public_plugins=False,
        addon_runtime_config=(("mechanical.corex", True),),
        generation_root=tmp_path / "generations",
    )
    fingerprint, revisions = catalog_agreement(registry.data_types)
    plugin_digest = registry.plugin_fingerprint()
    command = StartRunCommand(
        run_id="run", workspace_id="workspace", runtime_snapshot=None,
        catalog_fingerprint=fingerprint, catalog_revisions=revisions,
        plugin_bundles=registry.plugin_bundle_refs(), plugin_fingerprint=plugin_digest,
        runtime_registry_fingerprint=runtime_registry_fingerprint(fingerprint, plugin_digest),
        registry_contract_fingerprint=registry.contract_fingerprint(),
        addon_runtime_config=registry.addon_runtime_config(),
    )
    runtime = WorkerPluginRuntime()
    prepared = runtime.prepare_registry(command, registry)
    ref = prepared.python_function_ref_or_none("mechanical.open_model")
    assert ref is not None
    assert runtime.create_adapter(ref, prepared.get_spec("mechanical.open_model"))
    runtime.clear()
