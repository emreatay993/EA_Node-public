# Purpose: Prove the exact T12 integration cutover across registry, worker, and persistence.
# Map: feature_routes/core_integrations_file_process_email_spreadsheet.md
# Tests: tests/test_builtin_integration_function_migration.py

from __future__ import annotations

from dataclasses import asdict
import importlib
import json
from pathlib import Path
import subprocess
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
from ea_node_editor.ui.shell.controllers.workspace_io_ops import WorkspaceIOOps
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog


_CONVERTED_TYPE_IDS = (
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
_TRUSTED_EXCEPTIONS = ("io.path_pointer", "io.folder_explorer")
def test_exact_t12_entries_match_golden_and_remove_legacy_exports(
    tmp_path: Path,
) -> None:
    registry = build_builtin_registry(generation_root=tmp_path / "generations")
    golden_rows = load_current_repo_owned_catalog()
    expected = {
        row["spec"]["type_id"]: row["spec"]
        for row in golden_rows
        if row["spec"]["type_id"] in _CONVERTED_TYPE_IDS
    }

    assert len(golden_rows) == 147
    assert len(_CONVERTED_TYPE_IDS) == 14
    assert set(expected) == set(_CONVERTED_TYPE_IDS)
    for type_id in _CONVERTED_TYPE_IDS:
        entry = registry.get_entry(type_id)
        assert isinstance(entry, PythonFunctionEntry)
        assert entry.owner_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID
        assert registry.descriptor_or_none(type_id) is None
        assert json.loads(json.dumps(asdict(entry.spec))) == expected[type_id]
    for type_id in _TRUSTED_EXCEPTIONS:
        assert isinstance(registry.get_entry(type_id), TrustedFactoryEntry)
        assert registry.descriptor_or_none(type_id) is not None

    assert len(registry.plugin_bundle_refs()[0].functions) == 76
    builtins_root = Path(__file__).parents[1] / "ea_node_editor" / "nodes" / "builtins"
    assert not (builtins_root / "integrations.py").exists()
    builtins_package = importlib.import_module("ea_node_editor.nodes.builtins")
    assert not any(
        hasattr(builtins_package, name)
        for name in (
            "EmailSendNodePlugin",
            "ExcelReadNodePlugin",
            "ExcelWriteNodePlugin",
            "FileReadNodePlugin",
            "FileWriteNodePlugin",
            "ImageExportNodePlugin",
            "ImageImportNodePlugin",
            "ProcessRunNodePlugin",
            "SecretNodePlugin",
            "SshSftpHostNodePlugin",
            "RunSshCommandNodePlugin",
            "RunSshScriptNodePlugin",
            "SftpUploadNodePlugin",
            "SftpDownloadNodePlugin",
        )
    )


def test_clean_registry_construction_imports_no_heavy_integration_dependency(
    tmp_path: Path,
) -> None:
    code = """
import json
from pathlib import Path
import sys
from ea_node_editor.nodes.bootstrap import build_builtin_registry

registry = build_builtin_registry(generation_root=Path(sys.argv[1]))
print(json.dumps({
    "count": len(registry.plugin_bundle_refs()[0].functions),
    "openpyxl": "openpyxl" in sys.modules,
    "paramiko": "paramiko" in sys.modules,
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "generations")],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "count": 76,
        "openpyxl": False,
        "paramiko": False,
    }


def test_t12_representatives_execute_in_spawned_process_worker(
    tmp_path: Path,
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    text_path = tmp_path / "input.txt"
    text_path.write_text("t12 file", encoding="utf-8")
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("name,value\nalpha,7\n", encoding="utf-8")

    registry = build_default_registry(include_public_plugins=False)
    model = GraphModel()
    workspace = model.active_workspace
    nodes = (
        model.add_node(
            workspace.workspace_id,
            "io.file_read",
            "File Read",
            0,
            0,
            properties={"path": str(text_path)},
        ),
        model.add_node(
            workspace.workspace_id,
            "io.excel_read",
            "Excel Read",
            0,
            120,
            properties={"path": str(csv_path)},
        ),
        model.add_node(
            workspace.workspace_id,
            "io.process_run",
            "Process Run",
            0,
            240,
            properties={
                "command": sys.executable,
                "args": ["-c", "print('t12 process')"],
            },
        ),
        model.add_node(
            workspace.workspace_id,
            "ssh_sftp.secret",
            "Secret",
            0,
            360,
            properties={
                "protected_value": {
                    "schema": "corex.protected_secret.v1",
                    "provider": "windows_dpapi",
                    "scope": "CurrentUser",
                    "ciphertext_b64": "AA==",
                },
                "data_protection_scope": "Current user",
            },
        ),
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
        assert terminal.wait(timeout=30.0)
    finally:
        client.shutdown()

    assert not [event for event in events if event.get("type") == "run_failed"]
    settled = {
        str(event.get("node_id")): event
        for event in events
        if event.get("type") == "node_settled"
    }
    assert {node.node_id for node in nodes} == set(settled)
    assert all(event["status"] == "completed" for event in settled.values())


def test_t12_nodes_roundtrip_without_internal_implementation_records(
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
            "workflow_id": "t12_integrations",
            "name": "T12 Integrations",
            "description": "",
            "revision": 1,
            "ports": [],
            "fragment": fragment,
        },
        tmp_path / "t12_integrations",
    )
    assert workflow_path.suffix == ".cxwf"
    imported = import_custom_workflow_file(workflow_path, registry=registry)
    assert {node["type_id"] for node in imported["fragment"]["nodes"]} == set(
        _CONVERTED_TYPE_IDS
    )

    payloads = (
        json.dumps(project_document, sort_keys=True),
        json.dumps(fragment, sort_keys=True),
        workflow_path.read_text(encoding="utf-8"),
    )
    bundle = registry.plugin_bundle_refs()[0]
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

    report = summarize_plugin_registry(registry)
    assert report.summary.bundle_count == report.summary.node_count == 0
    assert WorkspaceIOOps.collect_node_package_export_candidates(
        registry,
        tmp_path / "plugins",
    ) == []
