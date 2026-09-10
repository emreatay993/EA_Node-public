# Purpose: Prove the exact T10 built-in function cutover across catalog, runtime, and persistence.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_builtin_function_migration.py

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys
import threading

from ea_node_editor.custom_workflows import (
    export_custom_workflow_file,
    import_custom_workflow_file,
)
from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.graph.fragment_payloads import build_graph_fragment_payload
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.transform_fragment_ops import (
    build_subtree_fragment_payload_data,
    insert_graph_fragment,
)
from ea_node_editor.nodes.bootstrap import build_builtin_registry, build_default_registry
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.plugin_authoring import summarize_plugin_registry
from ea_node_editor.nodes.registry import PythonFunctionEntry, TrustedFactoryEntry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import DataTree, deserialize_runtime_value
from ea_node_editor.ui.shell.controllers.workspace_io_ops import WorkspaceIOOps
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog

_T10_CONVERTED_TYPE_IDS = (
    "core.if",
    "data.deconstruct_color",
    "data.construct_path",
    "data.deconstruct_path",
    "data.excel_cell",
    "utilities.deconstruct_date_time",
    "math.deconstruct_tensor",
    "math.deconstruct_interval_2d",
    "math.physical_quantity_container",
    "math.unit_system_container",
    "math.deconstruct_interval",
    "math.bounding_interval_2d",
    "math.field_vector_container",
    "reference.reverse_vector",
    "reference.deconstruct_vector",
    "reference.deconstruct_point",
    "reference.construct_point",
    "reference.construct_vector",
    "reference.xy_plane",
    "reference.construct_plane",
    "reference.vector_length",
    "geometry.chain_transforms",
    "geometry.unchain_transforms",
)
_T11_CONVERTED_TYPE_IDS = ("plot.signal",)
_T12_CONVERTED_TYPE_IDS = (
    "io.email_send",
    "io.excel_read",
    "io.excel_write",
    "io.file_read",
    "io.file_write",
    "io.image_export",
    "io.image_import",
    "io.process_run",
    "ssh_sftp.download",
    "ssh_sftp.host",
    "ssh_sftp.run_command",
    "ssh_sftp.run_script",
    "ssh_sftp.secret",
    "ssh_sftp.upload",
)
_T15_CONVERTED_TYPE_IDS = (
    "ai.create_vector_collection",
    "ai.inspect_vector_collection",
    "ai.large_language_model",
    "ai.sqlite_vector_database",
    "core.constant",
    "core.logger",
    "data.boolean_toggle",
    "data.number_slider",
    "data.panel",
    "data.select",
    "engineering.cad_import",
    "engineering.fe_import",
    "fea.force",
    "fea.load_container",
    "geometry.construct_group",
    "geometry.construct_transform",
    "geometry.cylinder",
    "geometry.deconstruct_transform",
    "math.construct_interval",
    "mesh.deconstruct_mesh_face",
    "model.viewer",
    "optimization.construct_design",
    "optimization.construct_parameters",
    "optimization.construct_responses",
    "reference.plane_container",
    "reporting.markdown_flowchart",
    "reporting.markdown_flowchart_node",
    "security.windows_authentication",
    "utilities.construct_view",
    "utilities.deconstruct_view",
)
_CONVERTED_TYPE_IDS = (
    *_T10_CONVERTED_TYPE_IDS,
    *_T11_CONVERTED_TYPE_IDS,
    *_T12_CONVERTED_TYPE_IDS,
    *_T15_CONVERTED_TYPE_IDS,
)
_NATIVE_FUNCTION_TYPE_IDS = (
    "io.combine_file_paths",
    "io.construct_file_path",
    "io.contents_in_directory",
    "io.create_directory",
    "io.deconstruct_file_path",
    "io.delete_file",
    "io.move_file",
    "io.temporary_file_path",
)
def test_exact_t10_entries_match_golden_and_leave_truthful_descriptor_boundary(
    tmp_path: Path,
) -> None:
    registry = build_builtin_registry(generation_root=tmp_path / "generations")
    expected = {
        row["spec"]["type_id"]: row["spec"]
        for row in load_current_repo_owned_catalog()
        if row["spec"]["type_id"] in _T10_CONVERTED_TYPE_IDS
    }

    assert len(_T10_CONVERTED_TYPE_IDS) == 23
    assert set(expected) == set(_T10_CONVERTED_TYPE_IDS)
    assert {
        spec.type_id
        for spec in registry.all_specs()
        if isinstance(registry.get_entry(spec.type_id), PythonFunctionEntry)
    } == set((*_CONVERTED_TYPE_IDS, *_NATIVE_FUNCTION_TYPE_IDS))
    for type_id in _T10_CONVERTED_TYPE_IDS:
        entry = registry.get_entry(type_id)
        assert isinstance(entry, PythonFunctionEntry)
        assert entry.owner_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID
        assert registry.descriptor_or_none(type_id) is None
        assert json.loads(json.dumps(asdict(entry.spec))) == expected[type_id]

    trusted_type_ids = {
        spec.type_id
        for spec in registry.all_specs()
        if isinstance(registry.get_entry(spec.type_id), TrustedFactoryEntry)
    }
    assert trusted_type_ids == {
        spec.type_id for spec in registry.all_specs()
    } - set((*_CONVERTED_TYPE_IDS, *_NATIVE_FUNCTION_TYPE_IDS))
    assert {
        "core.python_script",
        "core.stream_gate",
        "core.trigger",
        "optimization.parameter_pool",
        "optimization.parameter_setup",
        "optimization.response_pool",
    } <= trusted_type_ids

    bundle = registry.plugin_bundle_refs()[0]
    assert bundle.owner_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID
    assert len(bundle.functions) == len(_CONVERTED_TYPE_IDS) + len(_NATIVE_FUNCTION_TYPE_IDS)
    assert not any(
        name == f"_corex_plugin_{bundle.bundle_digest}"
        or name.startswith(f"_corex_plugin_{bundle.bundle_digest}.")
        for name in sys.modules
    )
    report = summarize_plugin_registry(registry)
    assert report.summary.bundle_count == report.summary.node_count == 0
    assert WorkspaceIOOps.collect_node_package_export_candidates(
        registry,
        tmp_path / "plugins",
    ) == []


def test_t11_signal_is_a_separate_internal_function_entry(tmp_path: Path) -> None:
    registry = build_builtin_registry(generation_root=tmp_path / "generations")
    entry = registry.get_entry("plot.signal")

    assert _T11_CONVERTED_TYPE_IDS == ("plot.signal",)
    assert isinstance(entry, PythonFunctionEntry)
    assert entry.owner_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID
    assert registry.descriptor_or_none("plot.signal") is None


def test_t10_representatives_execute_in_spawned_process_worker(
    tmp_path: Path,
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    registry = build_default_registry(include_public_plugins=False)
    model = GraphModel()
    workspace = model.active_workspace
    condition = model.add_node(
        workspace.workspace_id,
        "data.boolean_toggle",
        "Condition",
        0,
        0,
        properties={"value": True},
    )
    value = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Value",
        0,
        120,
        properties={"value": 7},
    )
    core_node = model.add_node(workspace.workspace_id, "core.if", "If", 240, 0)
    unit_node = model.add_node(
        workspace.workspace_id,
        "math.physical_quantity_container",
        "Quantity",
        240,
        160,
    )
    spatial_node = model.add_node(
        workspace.workspace_id,
        "math.field_vector_container",
        "Field Vector",
        240,
        320,
    )
    model.add_edge(
        workspace.workspace_id,
        condition.node_id,
        "boolean",
        core_node.node_id,
        "condition",
    )
    model.add_edge(
        workspace.workspace_id,
        value.node_id,
        "value",
        core_node.node_id,
        "true_value",
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
            "",
            workspace.workspace_id,
            {"runtime_snapshot": snapshot},
            data_types=registry.data_types,
            plugin_bundles=registry.plugin_bundle_refs(),
            plugin_fingerprint=registry.plugin_fingerprint(),
            registry_contract_fingerprint=registry.contract_fingerprint(),
            addon_runtime_config=registry.addon_runtime_config(),
        )
        assert run_id
        assert terminal.wait(timeout=20.0)
    finally:
        client.shutdown()

    assert not [event for event in events if event.get("type") == "run_failed"]
    settled = {
        str(event.get("node_id")): event
        for event in events
        if event.get("type") == "node_settled"
    }
    assert {core_node.node_id, unit_node.node_id, spatial_node.node_id} <= set(settled)
    core_result = settled[core_node.node_id]["outputs"]["result"]
    assert core_result["status"] == "value"
    assert deserialize_runtime_value(core_result["value"]) == DataTree.from_item(7)
    for node_id in (unit_node.node_id, spatial_node.node_id):
        assert settled[node_id]["status"] == "empty"
        assert settled[node_id]["outputs"]["output"]["status"] == "empty"


def test_converted_function_nodes_roundtrip_without_implementation_records(
    tmp_path: Path,
) -> None:
    registry = build_builtin_registry(generation_root=tmp_path / "generations")
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
    inserted = insert_graph_fragment(
        model=model,
        workspace_id=target.workspace_id,
        fragment_payload=fragment,
        delta_x=40.0,
        delta_y=40.0,
        registry=registry,
    )
    assert len(inserted) == len(_CONVERTED_TYPE_IDS)

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
            "workflow_id": "t10_functions",
            "name": "T10 Functions",
            "description": "",
            "revision": 1,
            "ports": [],
            "fragment": fragment,
        },
        tmp_path / "t10_functions",
    )
    imported_workflow = import_custom_workflow_file(workflow_path, registry=registry)
    assert {
        node["type_id"] for node in imported_workflow["fragment"]["nodes"]
    } == set(_CONVERTED_TYPE_IDS)

    serialized_payloads = (
        json.dumps(project_document, sort_keys=True),
        json.dumps(fragment, sort_keys=True),
        workflow_path.read_text(encoding="utf-8"),
    )
    bundle = registry.plugin_bundle_refs()[0]
    forbidden = {
        bundle.approved_generation_root,
        bundle.bundle_digest,
        *(function.source_digest for function in bundle.functions),
        "plugin_bundles",
        "function_name",
    }
    assert all(
        token not in payload
        for token in forbidden
        for payload in serialized_payloads
    )
