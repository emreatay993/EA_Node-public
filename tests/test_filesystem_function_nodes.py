# Purpose: Prove filesystem declarations, worker execution, and persistence.
# Map: feature_routes/core_integrations_file_process_email_spreadsheet.md
# Tests: tests/test_filesystem_function_nodes.py

from __future__ import annotations

from pathlib import Path
import threading

from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_builtin_registry, build_default_registry
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.registry import PythonFunctionEntry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import DataTree, deserialize_runtime_value


TYPE_IDS = (
    "io.combine_file_paths",
    "io.construct_file_path",
    "io.deconstruct_file_path",
    "io.contents_in_directory",
    "io.create_directory",
    "io.move_file",
    "io.delete_file",
    "io.temporary_file_path",
)


def test_filesystem_declarations_have_exact_contract() -> None:
    registry = build_builtin_registry()
    specs = {type_id: registry.get_spec(type_id) for type_id in TYPE_IDS}

    assert all(isinstance(registry.get_entry(type_id), PythonFunctionEntry) for type_id in TYPE_IDS)
    assert all(registry.get_entry(type_id).owner_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID for type_id in TYPE_IDS)
    assert all(spec.category_path == ("Utilities", "File System") for spec in specs.values())
    assert all(spec.solution_reuse_scope == "never" for spec in specs.values())
    assert {type_id: tuple(port.key for port in spec.ports) for type_id, spec in specs.items()} == {
        "io.combine_file_paths": ("paths", "final_path"),
        "io.construct_file_path": ("directory", "file_name", "file_extension", "file_path"),
        "io.deconstruct_file_path": ("file_path", "directory", "file_name", "file_extension"),
        "io.contents_in_directory": ("directory", "search_pattern", "subdirectory_levels", "content_type", "content_paths"),
        "io.create_directory": ("directory", "create_recursive", "created_directory"),
        "io.move_file": ("source_path", "target_path", "operation_mode", "overwrite_target_file", "successful"),
        "io.delete_file": ("file_path", "successful"),
        "io.temporary_file_path": ("file_name", "file_extension", "file_path"),
    }
    path_inputs = [
        port
        for spec in specs.values()
        for port in spec.ports
        if port.direction == "in" and port.data_type == "COREX.DataTypes.Path"
    ]
    assert all(port.accepted_data_types == ("COREX.DataTypes.String",) for port in path_inputs)
    assert specs["io.combine_file_paths"].ports[0].data_access == "list"
    assert specs["io.contents_in_directory"].ports[-1].data_access == "list"
    assert all(
        port.data_access == "item"
        for spec in specs.values()
        for port in spec.ports
        if port not in (specs["io.combine_file_paths"].ports[0], specs["io.contents_in_directory"].ports[-1])
    )

    props = {type_id: {prop.key: prop for prop in spec.properties} for type_id, spec in specs.items()}
    assert props["io.contents_in_directory"]["directory"].default == ""
    assert props["io.contents_in_directory"]["search_pattern"].default == "*"
    depth = props["io.contents_in_directory"]["subdirectory_levels"]
    assert (depth.default, depth.minimum, depth.maximum, depth.step, depth.inline_editor) == (0, 0, 10, 1, "slider")
    content = props["io.contents_in_directory"]["content_type"]
    assert (content.default, content.enum_values, content.enum_codes, content.inline_editor) == (0, ("Files", "Directories", "Files and Directories"), (0, 1, 2), "enum")
    mode = props["io.move_file"]["operation_mode"]
    assert (mode.default, mode.enum_values, mode.enum_codes, mode.inline_editor) == (0, ("Copy", "Move"), (0, 1), "enum")
    assert props["io.create_directory"]["create_recursive"].default is False
    assert props["io.move_file"]["overwrite_target_file"].default is False
    assert next(
        port
        for port in specs["io.construct_file_path"].ports
        if port.key == "file_extension"
    ).allow_empty_string is True
    assert all(
        not port.allow_empty_string
        for spec in specs.values()
        for port in spec.ports
        if not (spec.type_id == "io.construct_file_path" and port.key == "file_extension")
    )
    assert all(
        prop.inline_editor == ""
        for values in props.values()
        for prop in values.values()
        if prop.type in {"path", "str"}
    )


def test_filesystem_nodes_execute_in_spawned_worker_with_list_binding_overrides_and_warning(
    tmp_path: Path,
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    (tmp_path / "first.txt").write_text("first", encoding="utf-8")
    (tmp_path / "second.txt").write_text("second", encoding="utf-8")
    registry = build_default_registry(include_public_plugins=False)
    model = GraphModel()
    workspace = model.active_workspace
    contents = model.add_node(workspace.workspace_id, "io.contents_in_directory", "Contents", 0, 0, properties={"directory": str(tmp_path), "search_pattern": "*.txt", "subdirectory_levels": 0, "content_type": 0})
    combine = model.add_node(workspace.workspace_id, "io.combine_file_paths", "Combine", 220, 0)
    reader = model.add_node(workspace.workspace_id, "io.file_read", "Reader", 440, 0)
    construct = model.add_node(workspace.workspace_id, "io.construct_file_path", "Construct", 0, 180, properties={"directory": str(tmp_path), "file_name": "plain", "file_extension": ""})
    split = model.add_node(workspace.workspace_id, "io.deconstruct_file_path", "Split", 220, 180, properties={"file_path": str(tmp_path / "no_extension")})
    overridden = model.add_node(workspace.workspace_id, "io.construct_file_path", "Overridden", 440, 180, properties={"directory": str(tmp_path), "file_name": "connected", "file_extension": ".ignored"})
    ordinary_required = model.add_node(workspace.workspace_id, "io.deconstruct_file_path", "Ordinary required", 440, 300, properties={"file_path": str(tmp_path / "ignored")})
    missing = model.add_node(workspace.workspace_id, "io.delete_file", "Missing", 0, 360, properties={"file_path": str(tmp_path / "missing.txt")})
    model.add_edge(workspace.workspace_id, contents.node_id, "content_paths", combine.node_id, "paths")
    model.add_edge(workspace.workspace_id, contents.node_id, "content_paths", reader.node_id, "path")
    model.add_edge(workspace.workspace_id, split.node_id, "file_extension", overridden.node_id, "file_extension")
    model.add_edge(workspace.workspace_id, split.node_id, "file_extension", ordinary_required.node_id, "file_path")
    snapshot = build_runtime_snapshot(model.project, workspace_id=workspace.workspace_id, registry=registry)
    events: list[dict[str, object]] = []
    terminal = threading.Event()

    def collect(event: dict[str, object]) -> None:
        events.append(event)
        if event.get("type") in {"run_completed", "run_failed", "run_stopped"}:
            terminal.set()

    client = ProcessExecutionClient()
    client.subscribe(collect)
    try:
        client.start_run("", workspace.workspace_id, {"runtime_snapshot": snapshot}, data_types=registry.data_types, plugin_bundles=registry.plugin_bundle_refs(), plugin_fingerprint=registry.plugin_fingerprint(), registry_contract_fingerprint=registry.contract_fingerprint(), addon_runtime_config=registry.addon_runtime_config())
        assert terminal.wait(timeout=30.0)
    finally:
        client.shutdown()

    assert not [event for event in events if event.get("type") == "run_failed"]
    settled = {str(event.get("node_id")): event for event in events if event.get("type") == "node_settled"}
    assert {contents.node_id, combine.node_id, reader.node_id, construct.node_id, split.node_id, overridden.node_id, ordinary_required.node_id, missing.node_id} == set(settled)
    assert all(
        settled[node_id]["status"] == "completed"
        for node_id in (contents.node_id, combine.node_id, reader.node_id, construct.node_id, split.node_id, overridden.node_id, missing.node_id)
    )
    assert settled[ordinary_required.node_id]["status"] == "empty"
    assert settled[missing.node_id]["warnings"]
    def output_tree(node_id: str, port_key: str) -> DataTree:
        value = settled[node_id]["outputs"][port_key]
        assert value["status"] == "value"
        decoded = deserialize_runtime_value(value["value"], catalog=registry.data_types)
        assert isinstance(decoded, DataTree)
        return decoded

    listed = output_tree(contents.node_id, "content_paths").branches[0][1]
    assert listed == (str(tmp_path / "first.txt"), str(tmp_path / "second.txt"))
    assert output_tree(reader.node_id, "text").branches[0][1] == ("first", "second")
    assert output_tree(construct.node_id, "file_path") == DataTree.from_item(str(tmp_path / "plain"))
    assert output_tree(overridden.node_id, "file_path") == DataTree.from_item(str(tmp_path / "connected"))
    assert output_tree(missing.node_id, "successful") == DataTree.from_item(False)


def test_filesystem_nodes_roundtrip_current_serializer(tmp_path: Path) -> None:
    registry = build_builtin_registry(generation_root=tmp_path / "generations")
    model = GraphModel()
    workspace = model.active_workspace
    for index, type_id in enumerate(TYPE_IDS):
        model.add_node(workspace.workspace_id, type_id, type_id, index * 20.0, index * 10.0)
    serializer = JsonProjectSerializer(registry)
    restored = serializer.from_document(serializer.to_persistent_document(model.project))
    assert {
        node.type_id
        for restored_workspace in restored.workspaces.values()
        for node in restored_workspace.nodes.values()
    } == set(TYPE_IDS)
