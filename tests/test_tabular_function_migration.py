# Purpose: Prove the exact T13 Tabular function cutover across add-on, worker, and persistence.
# Map: feature_routes/tabular_data_addon_preview.md
# Tests: tests/test_tabular_function_migration.py

from __future__ import annotations

from dataclasses import asdict, replace
import importlib
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from ea_node_editor.addons import catalog as addon_catalog
from ea_node_editor.addons.tabular_data import catalog as tabular_catalog
from ea_node_editor.addons.tabular_data.metadata import TABULAR_DATA_ADDON_ID
from ea_node_editor.app_preferences import (
    default_app_preferences_document,
    set_addon_state,
)
from ea_node_editor.custom_workflows import (
    export_custom_workflow_file,
    import_custom_workflow_file,
)
from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.run_messages import (
    StartRunCommand,
)
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.graph.fragment_payloads import build_graph_fragment_payload
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.transform_fragment_ops import (
    build_subtree_fragment_payload_data,
    insert_graph_fragment,
)
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.plugin_contracts import (
    PluginAvailability,
    PluginBackendDescriptor,
    PluginContractManifest,
)
from ea_node_editor.addons.registry_contributions import register_plugin_backends
from ea_node_editor.nodes.registry import NodeRegistry, PythonFunctionEntry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import (
    ArrayDataRef,
    ArraySlice2DRef,
    DataTree,
    RuntimeArtifactRef,
    TabularDataRef,
    TabularWindowRef,
    deserialize_runtime_value,
)
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog


_CONVERTED_TYPE_IDS = tabular_catalog.TABULAR_DATA_FUNCTION_TYPE_IDS
def _tabular_bundle(registry):  # noqa: ANN001, ANN202
    bundles = tuple(
        bundle
        for bundle in registry.plugin_bundle_refs()
        if bundle.owner_id == TABULAR_DATA_ADDON_ID
    )
    assert len(bundles) == 1
    return bundles[0]


def _tabular_preferences(*, enabled: bool) -> dict[str, object]:
    return set_addon_state(
        default_app_preferences_document(),
        TABULAR_DATA_ADDON_ID,
        enabled=enabled,
        pending_restart=False,
    )


def _worker_command(registry: NodeRegistry, *, run_id: str) -> StartRunCommand:
    catalog_fingerprint, revisions = catalog_agreement(registry.data_types)
    plugin_fingerprint = registry.plugin_fingerprint()
    return StartRunCommand(
        run_id=run_id,
        catalog_fingerprint=catalog_fingerprint,
        catalog_revisions=revisions,
        plugin_bundles=registry.plugin_bundle_refs(),
        plugin_fingerprint=plugin_fingerprint,
        runtime_registry_fingerprint=runtime_registry_fingerprint(
            catalog_fingerprint,
            plugin_fingerprint,
        ),
        registry_contract_fingerprint=registry.contract_fingerprint(),
        addon_runtime_config=registry.addon_runtime_config(),
    )


def _settled_event(
    events: list[dict[str, object]],
    node_id: str,
) -> dict[str, object]:
    return next(
        event
        for event in events
        if event.get("type") == "node_settled" and event.get("node_id") == node_id
    )


def _settled_value(
    event: dict[str, object],
    port_key: str,
    *,
    catalog,
) -> object:  # noqa: ANN001
    outputs = event["outputs"]
    assert isinstance(outputs, dict)
    result = outputs[port_key]
    assert isinstance(result, dict) and result["status"] == "value"
    tree = deserialize_runtime_value(result["value"], catalog=catalog)
    assert isinstance(tree, DataTree)
    return tree.branches[0][1][0]


def test_exact_t13_entries_match_golden_and_remove_legacy_exports(
    tmp_path: Path,
) -> None:
    registry = build_default_registry(
        include_public_plugins=False,
        preferences_document=_tabular_preferences(enabled=True),
        generation_root=tmp_path / "generations",
    )
    golden_rows = load_current_repo_owned_catalog()
    expected = {
        row["spec"]["type_id"]: row["spec"]
        for row in golden_rows
        if row["spec"]["type_id"] in _CONVERTED_TYPE_IDS
    }

    assert len(golden_rows) == 147
    assert len(_CONVERTED_TYPE_IDS) == 7
    assert set(expected) == set(_CONVERTED_TYPE_IDS)
    for type_id in _CONVERTED_TYPE_IDS:
        entry = registry.get_entry(type_id)
        assert isinstance(entry, PythonFunctionEntry)
        assert entry.owner_id == TABULAR_DATA_ADDON_ID
        assert registry.descriptor_or_none(type_id) is None
        assert json.loads(json.dumps(asdict(entry.spec))) == expected[type_id]
        assert entry.spec.settings_groups == ()

    bundle = _tabular_bundle(registry)
    assert tuple(
        registry.python_function_ref_or_none(type_id)
        for type_id in _CONVERTED_TYPE_IDS
    ) == bundle.functions
    assert not any(
        name == f"_corex_plugin_{bundle.bundle_digest}"
        or name.startswith(f"_corex_plugin_{bundle.bundle_digest}.")
        for name in sys.modules
    )

    legacy_exports = (
        "TABULAR_DATA_INPUT_NODE_DESCRIPTORS",
        "TABULAR_EXTRACTION_NODE_DESCRIPTORS",
        "load_tabular_data_plugin_descriptors",
        "TabularDataInputNodePlugin",
        "TabularTableWindowNodePlugin",
        "TabularArraySlice2DNodePlugin",
        "TabularWriteTableWindowNodePlugin",
        "TabularWriteArraySlice2DNodePlugin",
        "TabularMaterializeTableWindowNodePlugin",
        "TabularMaterializeArraySlice2DNodePlugin",
    )
    modules = (
        importlib.import_module("ea_node_editor.addons.tabular_data"),
        importlib.import_module("ea_node_editor.addons.tabular_data.input_node"),
        importlib.import_module("ea_node_editor.addons.tabular_data.extraction_nodes"),
    )
    assert not any(hasattr(module, name) for module in modules for name in legacy_exports)


def test_t13_disable_and_reenable_restores_exact_registry_identity(
    tmp_path: Path,
) -> None:
    generation_root = tmp_path / "generations"
    enabled = build_default_registry(
        include_public_plugins=False,
        preferences_document=_tabular_preferences(enabled=True),
        generation_root=generation_root,
    )
    disabled = build_default_registry(
        include_public_plugins=False,
        preferences_document=_tabular_preferences(enabled=False),
        generation_root=generation_root,
    )
    reenabled = build_default_registry(
        include_public_plugins=False,
        preferences_document=_tabular_preferences(enabled=True),
        generation_root=generation_root,
    )

    assert all(disabled.spec_or_none(type_id) is None for type_id in _CONVERTED_TYPE_IDS)
    assert not any(
        bundle.owner_id == TABULAR_DATA_ADDON_ID
        for bundle in disabled.plugin_bundle_refs()
    )
    assert enabled.plugin_fingerprint() != disabled.plugin_fingerprint()
    assert enabled.contract_fingerprint() != disabled.contract_fingerprint()
    assert enabled.plugin_fingerprint() == reenabled.plugin_fingerprint()
    assert enabled.contract_fingerprint() == reenabled.contract_fingerprint()
    assert _tabular_bundle(enabled) == _tabular_bundle(reenabled)


def test_worker_rejects_substituted_trusted_tabular_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ea_node_editor.addons.tabular_data import function_nodes

    preferences = _tabular_preferences(enabled=True)
    trusted = build_default_registry(
        include_public_plugins=False,
        preferences_document=preferences,
        generation_root=tmp_path / "trusted",
    )
    monkeypatch.setattr(
        function_nodes,
        "SOURCE",
        function_nodes.SOURCE + "\n# substituted trusted source\n",
    )
    substituted = build_default_registry(
        include_public_plugins=False,
        preferences_document=preferences,
        generation_root=tmp_path / "substituted",
    )

    with pytest.raises(ValueError, match="Trusted function generation is not attested"):
        WorkerPluginRuntime().prepare_registry(
            _worker_command(substituted, run_id="run_substituted_tabular"),
            trusted,
        )


def test_worker_rejects_private_metadata_for_manifest_only_owner(
    tmp_path: Path,
) -> None:
    owner_id = "tests.manifest_only_owner"
    type_id = "custom.manifest-collision.deadbeef"
    source = f'''import corex

@corex.node(id={type_id!r}, name="Manifest Collision", category=("Tests",))
@corex.text("value", default="", _inspector_visible=False)
@corex.output("result", value_type=str)
def manifest_collision(ctx, settings):
    return {{"result": settings.value}}
'''
    trusted = NodeRegistry()
    trusted.register_plugin_bundle(
        PluginContractManifest(),
        (),
        owner_id=owner_id,
    )
    trusted.freeze()
    requested = NodeRegistry()
    loaded = register_plugin_backends(
        (
            PluginBackendDescriptor(
                plugin_id=owner_id,
                display_name="Manifest Collision",
                get_availability=lambda: PluginAvailability.available(),
                load_descriptors=lambda: (),
                load_function_sources=lambda: (("collision.py", source),),
                function_type_ids=(type_id,),
            ),
        ),
        requested,
        owner_id,
        generation_root=tmp_path / "requested",
    )
    requested.freeze()

    assert loaded == [type_id]
    assert trusted.plugin_contract_manifest(owner_id) is not None
    assert trusted.plugin_bundle_refs() == ()
    with pytest.raises(ValueError, match="Private decorator field"):
        WorkerPluginRuntime().prepare_registry(
            _worker_command(requested, run_id="run_manifest_collision"),
            trusted,
        )


def test_t13_unavailable_and_discovery_paths_do_not_load_a_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_loaded() -> tuple[tuple[str, str], ...]:
        raise AssertionError("add-on discovery executed the function-source loader")

    discovery_backend = replace(
        tabular_catalog.TABULAR_DATA_PLUGIN_BACKEND,
        load_function_sources=fail_if_loaded,
    )
    monkeypatch.setattr(tabular_catalog, "PLUGIN_BACKENDS", (discovery_backend,))
    with monkeypatch.context() as availability_patch:
        availability_patch.setattr(tabular_catalog, "_find_spec", lambda _name: object())
        record = addon_catalog.addon_record_by_id(
            TABULAR_DATA_ADDON_ID,
            preferences_document=_tabular_preferences(enabled=True),
        )
    assert record is not None
    assert record.provided_node_type_ids == _CONVERTED_TYPE_IDS

    monkeypatch.setattr(tabular_catalog, "PLUGIN_BACKENDS", (tabular_catalog.TABULAR_DATA_PLUGIN_BACKEND,))
    monkeypatch.setattr(tabular_catalog, "_find_spec", lambda _name: None)
    unavailable = build_default_registry(
        include_public_plugins=False,
        preferences_document=_tabular_preferences(enabled=True),
        generation_root=tmp_path / "unavailable-generations",
    )
    assert all(unavailable.spec_or_none(type_id) is None for type_id in _CONVERTED_TYPE_IDS)
    assert not any(
        bundle.owner_id == TABULAR_DATA_ADDON_ID
        for bundle in unavailable.plugin_bundle_refs()
    )


def test_addon_discovery_imports_no_tabular_source_or_heavy_dependency() -> None:
    code = """
import json
import sys
from ea_node_editor.app_preferences import (
    default_app_preferences_document,
    normalize_app_preferences_document,
)

preferences = normalize_app_preferences_document(default_app_preferences_document())
watched = (
    "ea_node_editor.addons.tabular_data.function_nodes",
    "ea_node_editor.addons.tabular_data.input_node",
    "ea_node_editor.addons.tabular_data.extraction_nodes",
    "ea_node_editor.addons.tabular_data.loader_cache_service",
    "pyarrow",
    "numpy",
    "pandas",
    "openpyxl",
    "h5py",
    "duckdb",
)
baseline = {name for name in watched if name in sys.modules}

from ea_node_editor.addons.catalog import discover_addon_records

records = discover_addon_records(
    preferences_document=preferences,
)
tabular = next(
    record
    for record in records
    if record.addon_id == "ea_node_editor.builtins.tabular_data"
)
print(json.dumps({
    "provided": list(tabular.provided_node_type_ids),
    "newly_loaded": [
        name for name in watched if name in sys.modules and name not in baseline
    ],
}))
"""
    completed = subprocess.run(
        [sys.executable, "-E", "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "provided": list(_CONVERTED_TYPE_IDS),
        "newly_loaded": [],
    }


def test_t13_nodes_roundtrip_without_function_implementation_records(
    tmp_path: Path,
) -> None:
    registry = build_default_registry(
        include_public_plugins=False,
        preferences_document=_tabular_preferences(enabled=True),
        generation_root=tmp_path / "generations",
    )
    model = GraphModel()
    workspace = model.active_workspace
    node_ids = [
        model.add_node(
            workspace.workspace_id,
            type_id,
            type_id,
            float(index * 20),
            float(index * 10),
        ).node_id
        for index, type_id in enumerate(_CONVERTED_TYPE_IDS)
    ]
    duplicate = model.duplicate_workspace(workspace.workspace_id)
    assert {node.type_id for node in duplicate.nodes.values()} == set(
        _CONVERTED_TYPE_IDS
    )

    fragment_data = build_subtree_fragment_payload_data(
        workspace=workspace,
        selected_node_ids=node_ids,
    )
    assert fragment_data is not None
    fragment = build_graph_fragment_payload(**fragment_data)
    target = model.create_workspace("Fragment Target")
    assert len(
        insert_graph_fragment(
            model=model,
            workspace_id=target.workspace_id,
            fragment_payload=fragment,
            delta_x=40.0,
            delta_y=40.0,
            registry=registry,
        )
    ) == len(_CONVERTED_TYPE_IDS)

    serializer = JsonProjectSerializer(registry)
    project_document = serializer.to_persistent_document(model.project)
    restored = serializer.from_document(project_document)
    assert set(_CONVERTED_TYPE_IDS) <= {
        node.type_id
        for restored_workspace in restored.workspaces.values()
        for node in restored_workspace.nodes.values()
    }

    workflow_path = export_custom_workflow_file(
        {
            "workflow_id": "t13_tabular",
            "name": "T13 Tabular",
            "description": "",
            "revision": 1,
            "ports": [],
            "fragment": fragment,
        },
        tmp_path / "t13_tabular",
    )
    imported = import_custom_workflow_file(workflow_path, registry=registry)
    assert {node["type_id"] for node in imported["fragment"]["nodes"]} == set(
        _CONVERTED_TYPE_IDS
    )

    payloads = (
        json.dumps(project_document, sort_keys=True),
        json.dumps(fragment, sort_keys=True),
        workflow_path.read_text(encoding="utf-8"),
    )
    bundle = _tabular_bundle(registry)
    forbidden = {
        bundle.approved_generation_root,
        bundle.bundle_digest,
        *(function.module_relative_path for function in bundle.functions),
        *(function.source_digest for function in bundle.functions),
        "approved_generation_root",
        "plugin_bundles",
        "source_digest",
        "function_name",
    }
    assert all(token not in payload for token in forbidden for payload in payloads)


def test_t13_table_and_array_pipelines_execute_in_spawned_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    numpy = pytest.importorskip("numpy")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    table_path = tmp_path / "weather.csv"
    table_path.write_text(
        "station,temp,pressure\nA,21.5,100\nB,22.0,101\n",
        encoding="utf-8",
    )
    array_path = tmp_path / "values.npy"
    numpy.save(array_path, numpy.arange(12).reshape(3, 4))

    registry = build_default_registry(
        include_public_plugins=False,
        preferences_document=_tabular_preferences(enabled=True),
    )
    model = GraphModel()
    workspace = model.active_workspace
    table_input = model.add_node(
        workspace.workspace_id,
        "tabular.input",
        "Table Input",
        0,
        0,
        properties={"path": str(table_path)},
    )
    table_filter = model.add_node(
        workspace.workspace_id,
        "tabular.table_filter",
        "Table Filter",
        200,
        0,
        properties={"row_limit": 0, "column_limit": 0},
    )
    table_materialize = model.add_node(
        workspace.workspace_id,
        "tabular.materialize_table_filter",
        "Materialize Table",
        400,
        0,
    )
    table_writer = model.add_node(
        workspace.workspace_id,
        "tabular.write_table_filter",
        "Write Table",
        400,
        100,
        properties={"path": ""},
    )
    array_input = model.add_node(
        workspace.workspace_id,
        "tabular.input",
        "Array Input",
        0,
        240,
        properties={"path": str(array_path)},
    )
    array_slice = model.add_node(
        workspace.workspace_id,
        "tabular.array_slice_2d",
        "Array Slice",
        200,
        240,
        properties={"row_limit": 0, "column_limit": 0},
    )
    array_materialize = model.add_node(
        workspace.workspace_id,
        "tabular.materialize_array_slice_2d",
        "Materialize Array",
        400,
        240,
    )
    array_writer = model.add_node(
        workspace.workspace_id,
        "tabular.write_array_slice_2d",
        "Write Array",
        400,
        340,
        properties={"path": ""},
    )

    for source, source_port, target, target_port in (
        (table_input, "table_data", table_filter, "table_data"),
        (table_filter, "window", table_materialize, "window"),
        (table_filter, "window", table_writer, "window"),
        (array_input, "array_data", array_slice, "array_data"),
        (array_slice, "slice_2d", array_materialize, "slice_2d"),
        (array_slice, "slice_2d", array_writer, "slice_2d"),
    ):
        model.add_edge(
            workspace.workspace_id,
            source.node_id,
            source_port,
            target.node_id,
            target_port,
        )

    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    events: list[dict[str, object]] = []
    terminal = threading.Event()

    def collect(event: dict[str, object]) -> None:
        events.append(event)
        if event.get("type") in {"run_completed", "run_failed", "run_stopped"}:
            terminal.set()

    client = ProcessExecutionClient()
    client.subscribe(collect)
    try:
        run_id = client.start_run(
            str(tmp_path / "project.cxproj"),
            workspace.workspace_id,
            {"runtime_snapshot": snapshot},
            data_types=registry.data_types,
            plugin_bundles=registry.plugin_bundle_refs(),
            plugin_fingerprint=registry.plugin_fingerprint(),
            registry_contract_fingerprint=registry.contract_fingerprint(),
            addon_runtime_config=registry.addon_runtime_config(),
        )
        assert run_id, events[-1].get("error") if events else events
        assert terminal.wait(timeout=60.0)
    finally:
        client.shutdown()

    assert not [event for event in events if event.get("type") == "run_failed"]
    nodes = (
        table_input,
        table_filter,
        table_materialize,
        table_writer,
        array_input,
        array_slice,
        array_materialize,
        array_writer,
    )
    settled = {node.node_id: _settled_event(events, node.node_id) for node in nodes}
    assert all(event["status"] == "completed" for event in settled.values())

    assert isinstance(
        _settled_value(
            settled[table_input.node_id],
            "table_data",
            catalog=registry.data_types,
        ),
        TabularDataRef,
    )
    assert isinstance(
        _settled_value(
            settled[table_filter.node_id],
            "window",
            catalog=registry.data_types,
        ),
        TabularWindowRef,
    )
    assert isinstance(
        _settled_value(
            settled[array_input.node_id],
            "array_data",
            catalog=registry.data_types,
        ),
        ArrayDataRef,
    )
    assert isinstance(
        _settled_value(
            settled[array_slice.node_id],
            "slice_2d",
            catalog=registry.data_types,
        ),
        ArraySlice2DRef,
    )
    for writer in (table_writer, array_writer):
        assert isinstance(
            _settled_value(
                settled[writer.node_id],
                "written_path",
                catalog=registry.data_types,
            ),
            RuntimeArtifactRef,
        )
    assert settled[table_materialize.node_id]["warnings"]
    assert settled[array_materialize.node_id]["warnings"]
