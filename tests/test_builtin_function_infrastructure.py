# Purpose: Prove reserved built-in function source uses the normal attested worker path.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_builtin_function_infrastructure.py

from __future__ import annotations

from collections import Counter
import json
import threading
from pathlib import Path

import pytest

from ea_node_editor.addons.tabular_data.metadata import TABULAR_DATA_ADDON_ID
from ea_node_editor.execution.trusted_client import TrustedInProcessExecutionClient
from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.run_messages import (
    StartRunCommand,
)
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.protocol_codec import (
    command_to_dict,
    dict_to_command,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_builtin_registry, build_default_registry
from ea_node_editor.nodes.builtin_functions import (
    ai_agent,
    ai_vector_database,
    core_value,
    data_control,
    engineering_fem,
    engineering_geometry,
    engineering_imports,
    engineering_viewer,
    filesystem,
    integrations_email,
    integrations_file_io,
    integrations_process,
    integrations_spreadsheet,
    integrations_ssh_sftp,
    plot_signal,
    reporting,
    rich_values,
    security,
    source_modules,
    spatial,
    unit_math,
    viewer_viewport,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import (
    EMPTY_PLUGIN_FINGERPRINT,
    INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
)
from ea_node_editor.nodes.plugin_authoring import summarize_plugin_registry
from ea_node_editor.nodes.registry import PythonFunctionEntry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.ui.shell.controllers.workspace_io_ops import WorkspaceIOOps

_TYPE_ID = "tests.internal_function"


def _source(marker: Path | None = None) -> str:
    prelude = ""
    if marker is not None:
        prelude = (
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n"
        )
    return f'''import corex
{prelude}
@corex.node(id={_TYPE_ID!r}, name="Internal Function", category=("Tests",))
@corex.output("result", value_type=int)
def internal_function(ctx):
    return {{"result": 7}}
'''


def _command(registry, *, runtime_snapshot=None) -> StartRunCommand:  # noqa: ANN001
    catalog_fingerprint, revisions = catalog_agreement(registry.data_types)
    plugin_digest = registry.plugin_fingerprint()
    return StartRunCommand(
        run_id="run_internal",
        workspace_id="workspace_internal",
        runtime_snapshot=runtime_snapshot,
        catalog_fingerprint=catalog_fingerprint,
        catalog_revisions=revisions,
        plugin_bundles=registry.plugin_bundle_refs(),
        plugin_fingerprint=plugin_digest,
        runtime_registry_fingerprint=runtime_registry_fingerprint(
            catalog_fingerprint,
            plugin_digest,
        ),
        registry_contract_fingerprint=registry.contract_fingerprint(),
        addon_runtime_config=registry.addon_runtime_config(),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        run_id="run_internal",
        node_id="node_internal",
        workspace_id="workspace_internal",
        inputs={},
        properties={},
        emit_log=lambda _level, _message: None,
    )


def test_placeholder_sources_form_one_noop_internal_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:  # noqa: ANN001
    for module in (
        core_value,
        unit_math,
        spatial,
        plot_signal,
        integrations_file_io,
        integrations_process,
            integrations_email,
            integrations_spreadsheet,
            integrations_ssh_sftp,
            data_control,
            engineering_imports,
            engineering_viewer,
            filesystem,
            viewer_viewport,
            engineering_geometry,
            engineering_fem,
            ai_vector_database,
            ai_agent,
            reporting,
            security,
            rich_values,
    ):
        monkeypatch.setattr(module, "SOURCE", "import corex\n")

    registry = build_builtin_registry(generation_root=tmp_path / "generations")

    assert [path for path, _source_text in source_modules()] == [
        "core_value.py",
        "unit_math.py",
        "spatial.py",
        "plot_signal.py",
        "integrations_file_io.py",
        "integrations_process.py",
        "integrations_email.py",
        "integrations_spreadsheet.py",
        "integrations_ssh_sftp.py",
        "data_control.py",
        "engineering_imports.py",
        "engineering_viewer.py",
        "filesystem.py",
        "viewer_viewport.py",
        "engineering_geometry.py",
        "engineering_fem.py",
        "ai_vector_database.py",
        "ai_agent.py",
        "reporting.py",
        "security.py",
        "rich_values.py",
    ]
    assert registry.all_python_function_refs() == ()
    assert len(registry.plugin_bundle_refs()) == 1
    bundle = registry.plugin_bundle_refs()[0]
    assert bundle.owner_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID
    assert bundle.functions == ()


def test_internal_builtin_function_entries_keep_no_plugin_provenance(
    tmp_path: Path,
) -> None:
    registry = build_builtin_registry(
        generation_root=tmp_path / "builtin-generations"
    )

    entry = registry.get_entry("core.if")

    assert isinstance(entry, PythonFunctionEntry)
    assert entry.provenance is None


def test_internal_function_declarations_carry_the_accepted_reuse_scopes(
    tmp_path: Path,
) -> None:
    registry = build_builtin_registry(generation_root=tmp_path / "generations")
    function_entries = tuple(
        entry
        for spec in registry.all_specs()
        if isinstance((entry := registry.get_entry(spec.type_id)), PythonFunctionEntry)
    )

    assert len(function_entries) == 76
    assert Counter(entry.spec.solution_reuse_scope for entry in function_entries) == {
        "durable": 29,
        "session": 22,
        "never": 25,
    }


def test_internal_generation_is_static_lazy_and_path_independent(
    tmp_path: Path,
    monkeypatch,
) -> None:  # noqa: ANN001
    marker = tmp_path / "loaded.txt"
    monkeypatch.setattr(core_value, "SOURCE", _source(marker))
    first = build_builtin_registry(generation_root=tmp_path / "first")
    second = build_builtin_registry(generation_root=tmp_path / "second")

    assert not marker.exists()
    assert first.plugin_fingerprint() == second.plugin_fingerprint()
    assert first.contract_fingerprint() == second.contract_fingerprint()
    assert first.plugin_bundle_refs()[0].bundle_digest == (
        second.plugin_bundle_refs()[0].bundle_digest
    )
    assert first.plugin_bundle_refs()[0].approved_generation_root != (
        second.plugin_bundle_refs()[0].approved_generation_root
    )

    runtime = WorkerPluginRuntime()
    prepared = runtime.prepare_registry(_command(first), second)
    assert not marker.exists()
    function_ref = prepared.python_function_ref_or_none(_TYPE_ID)
    assert function_ref is not None
    adapter = runtime.create_adapter(function_ref, prepared.get_spec(_TYPE_ID))
    assert marker.read_text(encoding="utf-8") == "loaded"
    assert adapter.execute(_context()).outputs == {"result": 7}
    runtime.clear()


def test_worker_rejects_unattested_reserved_generation(
    tmp_path: Path,
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setattr(core_value, "SOURCE", _source())
    trusted = build_builtin_registry(generation_root=tmp_path / "trusted")
    monkeypatch.setattr(core_value, "SOURCE", _source().replace("result\": 7", "result\": 9"))
    requested = build_builtin_registry(generation_root=tmp_path / "requested")

    with pytest.raises(ValueError, match="not attested"):
        WorkerPluginRuntime().prepare_registry(_command(requested), trusted)


def test_internal_bundle_roundtrips_as_bounded_protocol_refs(
    tmp_path: Path,
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(core_value, "SOURCE", _source())
    registry = build_builtin_registry()
    model = GraphModel()
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=model.active_workspace.workspace_id,
        registry=registry,
    )
    command = _command(registry, runtime_snapshot=snapshot)

    payload = command_to_dict(command, catalog=registry.data_types)
    restored = dict_to_command(payload, catalog=registry.data_types)

    assert restored == command
    serialized = json.dumps(payload, sort_keys=True)
    assert _source() not in serialized
    assert "approved_generation_root" in serialized


def test_trusted_client_allows_only_attested_internal_function_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(core_value, "SOURCE", _source())
    registry = build_default_registry(
        include_public_plugins=False,
        addon_runtime_config=((TABULAR_DATA_ADDON_ID, False),),
    )
    model = GraphModel()
    workspace = model.active_workspace
    model.add_node(workspace.workspace_id, _TYPE_ID, "Internal", 0, 0)
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

    client = TrustedInProcessExecutionClient()
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
        assert terminal.wait(timeout=10.0)
    finally:
        client.shutdown()

    failures = [event for event in events if event.get("type") == "run_failed"]
    assert not failures, json.dumps(failures, sort_keys=True)
    settled = next(event for event in events if event.get("type") == "node_settled")
    assert settled["status"] == "completed"


def test_internal_functions_are_hidden_from_authoring_export_and_persistence(
    tmp_path: Path,
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setattr(core_value, "SOURCE", _source())
    registry = build_builtin_registry(generation_root=tmp_path / "generations")

    report = summarize_plugin_registry(registry)
    assert report.summary.bundle_count == 0
    assert report.summary.node_count == 0
    assert report.summary.plugin_digest == EMPTY_PLUGIN_FINGERPRINT
    assert WorkspaceIOOps.collect_node_package_export_candidates(
        registry,
        tmp_path / "plugins",
    ) == []

    model = GraphModel()
    workspace = model.active_workspace
    model.add_node(workspace.workspace_id, _TYPE_ID, "Internal", 0, 0)
    document = JsonProjectSerializer(registry).to_persistent_document(model.project)
    serialized = json.dumps(document, sort_keys=True)
    bundle = registry.plugin_bundle_refs()[0]
    function_ref = registry.python_function_ref_or_none(_TYPE_ID)
    assert function_ref is not None
    assert _TYPE_ID in serialized
    assert bundle.approved_generation_root not in serialized
    assert bundle.bundle_digest not in serialized
    assert function_ref.source_digest not in serialized
    assert "plugin_bundles" not in serialized
    assert "function_name" not in serialized
