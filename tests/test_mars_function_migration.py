# Purpose: Prove the exact T14 MARS function cutover across add-on, worker, and persistence.
# Map: feature_routes/mars_solver_addon.md
# Tests: tests/test_mars_function_migration.py

from __future__ import annotations

from dataclasses import asdict, replace
import importlib
import json
from pathlib import Path
import queue
import subprocess
import sys

import pytest

from ea_node_editor.addons import catalog as addon_catalog
from ea_node_editor.addons.mars import catalog as mars_catalog
from ea_node_editor.addons.mars.metadata import MARS_ADDON_ID
from ea_node_editor.app_preferences import (
    default_app_preferences_document,
    set_addon_state,
)
from ea_node_editor.custom_workflows import (
    export_custom_workflow_file,
    import_custom_workflow_file,
)
from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.run_messages import (
    StartRunCommand,
)
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.worker import run_workflow
from ea_node_editor.graph.fragment_payloads import build_graph_fragment_payload
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.transform_fragment_ops import (
    build_subtree_fragment_payload_data,
    insert_graph_fragment,
)
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.plugin_contracts import PluginAvailability
from ea_node_editor.nodes.registry import NodeRegistry, PythonFunctionEntry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.ui_qml.node_title_icon_sources import (
    resolve_node_title_icon_source,
)
from tests.test_mars_nodes import _fake_success_command
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog


_CONVERTED_TYPE_IDS = mars_catalog.MARS_FUNCTION_TYPE_IDS
def _preferences(*, enabled: bool) -> dict[str, object]:
    return set_addon_state(
        default_app_preferences_document(),
        MARS_ADDON_ID,
        enabled=enabled,
        pending_restart=False,
    )


def _available_backend():  # noqa: ANN202
    return replace(
        mars_catalog.MARS_PLUGIN_BACKEND,
        get_availability=lambda: PluginAvailability.available(),
    )


def _enable_available_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mars_catalog, "PLUGIN_BACKENDS", (_available_backend(),))


def _mars_bundle(registry: NodeRegistry):  # noqa: ANN202
    bundles = tuple(
        bundle
        for bundle in registry.plugin_bundle_refs()
        if bundle.owner_id == MARS_ADDON_ID
    )
    assert len(bundles) == 1
    return bundles[0]


def _worker_command(
    registry: NodeRegistry,
    *,
    run_id: str,
    project_path: str = "",
    workspace_id: str = "",
    runtime_snapshot=None,  # noqa: ANN001
) -> StartRunCommand:
    catalog_fingerprint, revisions = catalog_agreement(registry.data_types)
    plugin_fingerprint = registry.plugin_fingerprint()
    return StartRunCommand(
        run_id=run_id,
        project_path=project_path,
        workspace_id=workspace_id,
        runtime_snapshot=runtime_snapshot,
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


def test_exact_t14_entries_match_golden_and_remove_legacy_exports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_available_backend(monkeypatch)
    generation_root = tmp_path / "generations"
    registry = build_default_registry(
        include_public_plugins=False,
        preferences_document=_preferences(enabled=True),
        generation_root=generation_root,
    )
    golden_rows = load_current_repo_owned_catalog()
    expected = {
        row["spec"]["type_id"]: row["spec"]
        for row in golden_rows
        if row["spec"]["type_id"] in _CONVERTED_TYPE_IDS
    }

    assert len(golden_rows) == 147
    assert _CONVERTED_TYPE_IDS == (
        "mars.batch_solve",
        "mars.time_history",
        "mars.run_job",
    )
    assert set(expected) == set(_CONVERTED_TYPE_IDS)
    for type_id in _CONVERTED_TYPE_IDS:
        entry = registry.get_entry(type_id)
        assert isinstance(entry, PythonFunctionEntry)
        assert entry.owner_id == MARS_ADDON_ID
        assert registry.descriptor_or_none(type_id) is None
        assert json.loads(json.dumps(asdict(entry.spec))) == expected[type_id]
        assert entry.spec.settings_groups == ()
        assert entry.provenance is not None
        assert entry.provenance.kind == "package"
        assert entry.provenance.package_root == Path(mars_catalog.__file__).parent
        assert resolve_node_title_icon_source(
            entry.spec.icon,
            provenance=entry.provenance,
        ) == (entry.provenance.package_root / entry.spec.icon).resolve().as_uri()

    bundle = _mars_bundle(registry)
    assert tuple(
        registry.python_function_ref_or_none(type_id)
        for type_id in _CONVERTED_TYPE_IDS
    ) == bundle.functions
    assert {function.module_relative_path for function in bundle.functions} == {
        "mars_nodes.py"
    }
    assert Path(bundle.approved_generation_root).is_relative_to(generation_root)

    legacy_exports = (
        "MARS_NODE_DESCRIPTORS",
        "load_mars_plugin_descriptors",
        "MARSBatchSolveNodePlugin",
        "MARSTimeHistoryNodePlugin",
        "MARSRunJobNodePlugin",
    )
    modules = (
        importlib.import_module("ea_node_editor.addons.mars"),
        importlib.import_module("ea_node_editor.addons.mars.catalog"),
        importlib.import_module("ea_node_editor.addons.mars.nodes"),
    )
    assert not any(hasattr(module, name) for module in modules for name in legacy_exports)


def test_t14_disabled_unavailable_and_discovery_paths_load_no_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_loaded() -> tuple[tuple[str, str], ...]:
        raise AssertionError("add-on discovery executed the MARS source loader")

    discovery_backend = replace(
        _available_backend(),
        load_function_sources=fail_if_loaded,
    )
    monkeypatch.setattr(mars_catalog, "PLUGIN_BACKENDS", (discovery_backend,))
    record = addon_catalog.addon_record_by_id(
        MARS_ADDON_ID,
        preferences_document=_preferences(enabled=False),
    )
    assert record is not None
    assert record.state.enabled is False
    assert record.provided_node_type_ids == _CONVERTED_TYPE_IDS

    disabled = build_default_registry(
        include_public_plugins=False,
        preferences_document=_preferences(enabled=False),
        generation_root=tmp_path / "disabled",
    )
    assert all(disabled.spec_or_none(type_id) is None for type_id in _CONVERTED_TYPE_IDS)
    assert not any(
        bundle.owner_id == MARS_ADDON_ID for bundle in disabled.plugin_bundle_refs()
    )
    assert dict(disabled.addon_runtime_config())[MARS_ADDON_ID] is False

    unavailable_backend = replace(
        mars_catalog.MARS_PLUGIN_BACKEND,
        get_availability=lambda: PluginAvailability.missing_dependency("MARSBatch"),
    )
    monkeypatch.setattr(mars_catalog, "PLUGIN_BACKENDS", (unavailable_backend,))
    unavailable = build_default_registry(
        include_public_plugins=False,
        preferences_document=_preferences(enabled=True),
        generation_root=tmp_path / "unavailable",
    )
    assert all(
        unavailable.spec_or_none(type_id) is None for type_id in _CONVERTED_TYPE_IDS
    )
    assert not any(
        bundle.owner_id == MARS_ADDON_ID
        for bundle in unavailable.plugin_bundle_refs()
    )


def test_t14_discovery_imports_no_function_helper_or_solver_module() -> None:
    code = r'''
import json
import sys
from dataclasses import replace
from ea_node_editor.addons.mars import catalog as mars_catalog
from ea_node_editor.nodes.plugin_contracts import PluginAvailability

def fail_if_loaded():
    raise AssertionError("source loader executed")

mars_catalog.PLUGIN_BACKENDS = (
    replace(
        mars_catalog.MARS_PLUGIN_BACKEND,
        get_availability=lambda: PluginAvailability.available(),
        load_function_sources=fail_if_loaded,
    ),
)
from ea_node_editor.addons.catalog import addon_record_by_id
record = addon_record_by_id("mars.corex")
watched = (
    "ea_node_editor.addons.mars.function_nodes",
    "ea_node_editor.addons.mars.nodes",
)
print(json.dumps({
    "provided": list(record.provided_node_type_ids),
    "loaded": [name for name in watched if name in sys.modules],
    "solver_loaded": any(
        name == "mars_solver" or name.startswith("mars_solver.")
        for name in sys.modules
    ),
}))
'''
    completed = subprocess.run(
        [sys.executable, "-E", "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "provided": list(_CONVERTED_TYPE_IDS),
        "loaded": [],
        "solver_loaded": False,
    }


def test_t14_enabled_registry_identity_and_substitution_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_available_backend(monkeypatch)
    preferences = _preferences(enabled=True)
    trusted = build_default_registry(
        include_public_plugins=False,
        preferences_document=preferences,
        generation_root=tmp_path / "trusted",
    )
    repeated = build_default_registry(
        include_public_plugins=False,
        preferences_document=preferences,
        generation_root=tmp_path / "repeated",
    )

    assert _mars_bundle(trusted).bundle_digest == _mars_bundle(repeated).bundle_digest
    assert trusted.plugin_fingerprint() == repeated.plugin_fingerprint()
    assert trusted.contract_fingerprint() == repeated.contract_fingerprint()
    assert dict(trusted.addon_runtime_config())[MARS_ADDON_ID] is True

    from ea_node_editor.addons.mars import function_nodes

    monkeypatch.setattr(
        function_nodes,
        "SOURCE",
        function_nodes.SOURCE + "\n# substituted trusted MARS source\n",
    )
    substituted = build_default_registry(
        include_public_plugins=False,
        preferences_document=preferences,
        generation_root=tmp_path / "substituted",
    )
    with pytest.raises(ValueError, match="Trusted function generation is not attested"):
        WorkerPluginRuntime().prepare_registry(
            _worker_command(substituted, run_id="run_substituted_mars"),
            trusted,
        )


def test_t14_nodes_roundtrip_without_function_implementation_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_available_backend(monkeypatch)
    registry = build_default_registry(
        include_public_plugins=False,
        preferences_document=_preferences(enabled=True),
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
            "workflow_id": "t14_mars",
            "name": "T14 MARS",
            "description": "",
            "revision": 1,
            "ports": [],
            "fragment": fragment,
        },
        tmp_path / "t14_mars",
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
    bundle = _mars_bundle(registry)
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


def test_t14_all_three_functions_execute_through_worker_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_available_backend(monkeypatch)
    preferences = _preferences(enabled=True)
    registry = build_default_registry(
        include_public_plugins=False,
        preferences_document=preferences,
        generation_root=tmp_path / "generations",
    )
    modal_coordinates = tmp_path / "response.mcf"
    modal_coordinates.write_text("synthetic", encoding="utf-8")
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps({"mode": "batch"}), encoding="utf-8")

    model = GraphModel()
    workspace = model.active_workspace
    nodes = (
        model.add_node(
            workspace.workspace_id,
            "mars.batch_solve",
            "MARS Batch Solve",
            0,
            0,
            properties={"modal_coordinates": str(modal_coordinates)},
        ),
        model.add_node(
            workspace.workspace_id,
            "mars.time_history",
            "MARS Time History",
            0,
            120,
            properties={"modal_coordinates": str(modal_coordinates)},
        ),
        model.add_node(
            workspace.workspace_id,
            "mars.run_job",
            "MARS Run Job",
            0,
            240,
            properties={"job": str(job_path)},
        ),
    )
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    event_queue: queue.Queue = queue.Queue()
    monkeypatch.setattr(
        "ea_node_editor.addons.mars.runtime.managed_mars_batch_executable",
        lambda: Path(sys.executable),
    )
    monkeypatch.setattr(
        "ea_node_editor.addons.mars.runtime._build_mars_command",
        _fake_success_command,
    )

    run_workflow(
        _worker_command(
            registry,
            run_id="t14-mars-worker",
            project_path=str(tmp_path / "project.cxproj"),
            workspace_id=workspace.workspace_id,
            runtime_snapshot=snapshot,
        ),
        event_queue,
    )

    events = []
    while not event_queue.empty():
        events.append(event_queue.get())
    assert not [event for event in events if event.get("type") == "run_failed"]
    settled = {
        str(event.get("node_id")): event
        for event in events
        if event.get("type") == "node_settled"
    }
    assert {node.node_id for node in nodes} == set(settled)
    assert all(event["status"] == "completed" for event in settled.values())
    assert all(event["warnings"] for event in settled.values())
    assert not any(
        name == "mars_solver" or name.startswith("mars_solver.")
        for name in sys.modules
    )
