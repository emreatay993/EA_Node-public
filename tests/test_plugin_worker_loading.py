from __future__ import annotations

import hashlib
import json
import queue
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.trusted_client import TrustedInProcessExecutionClient
from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.run_messages import (
    StartRunCommand,
    StopRunCommand,
)
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.protocol_codec import (
    command_to_dict,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.worker_runner import WorkflowRunner
from ea_node_editor.execution.worker_runtime import (
    DEFAULT_RUNTIME_PREPARATION_CACHE,
    RuntimePreparationCache,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_builtin_registry, build_default_registry
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import PluginBundleRef, PythonFunctionRef
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.nodes.plugin_generation import read_verified_plugin_generation
from ea_node_editor.nodes.plugin_loader import discover_static_plugins
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import DataTree, deserialize_runtime_value


@pytest.fixture(autouse=True)
def _clear_worker_plugin_cache():
    DEFAULT_RUNTIME_PREPARATION_CACHE.clear()
    yield
    DEFAULT_RUNTIME_PREPARATION_CACHE.clear()


def _write_package(
    root: Path,
    *,
    name: str,
    sources: dict[str, str],
    nodes: list[dict[str, str]],
) -> Path:
    package_dir = root / name
    package_dir.mkdir(parents=True)
    source_records = []
    for relative_path, source in sources.items():
        path = package_dir / relative_path
        path.write_text(source, encoding="utf-8")
        source_records.append(
            {
                "path": relative_path,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "schema_version": 2,
        "name": name,
        "version": "1.0.0",
        "author": "",
        "description": "",
        "modules": list(dict.fromkeys(node["module"] for node in nodes)),
        "sources": source_records,
        "assets": [],
        "nodes": nodes,
    }
    (package_dir / "node_package.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return package_dir


def _discover(
    plugin_root: Path,
    generation_root: Path,
    *,
    registry: NodeRegistry | None = None,
) -> tuple[NodeRegistry, tuple[PluginBundleRef, ...]]:
    active_registry = registry or NodeRegistry()
    result = discover_static_plugins(
        active_registry,
        roots=(plugin_root,),
        generation_root=generation_root,
    )
    active_registry.freeze()
    return active_registry, result.bundles


def _command(
    registry: NodeRegistry,
    *,
    runtime_snapshot=None,  # noqa: ANN001
    run_id: str = "run_plugin",
    workspace_id: str = "workspace_plugin",
) -> StartRunCommand:
    catalog_fingerprint, revisions = catalog_agreement(registry.data_types)
    plugin_fingerprint = registry.plugin_fingerprint()
    return StartRunCommand(
        run_id=run_id,
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


def _context() -> ExecutionContext:
    return ExecutionContext(
        run_id="run_plugin",
        node_id="node_plugin",
        workspace_id="workspace_plugin",
        inputs={},
        properties={},
        emit_log=lambda _level, _message: None,
    )


def test_runtime_cache_uses_only_accepted_addon_configuration(monkeypatch) -> None:
    from ea_node_editor.nodes import bootstrap

    spec = NodeTypeSpec(
        type_id="tests.synthetic_addon",
        display_name="Synthetic Add-on",
        category_path=("Tests",),
        icon="",
        ports=(),
        properties=(),
    )
    builds: list[tuple[tuple[str, bool], ...]] = []

    def build_registry(*, addon_runtime_config, **_kwargs):  # noqa: ANN001
        config = tuple(addon_runtime_config)
        registry = NodeRegistry(addon_runtime_config=config)
        if dict(config).get("tests.synthetic_addon", False):
            registry.register_descriptor(spec, lambda: None, owner_id=spec.type_id)
        registry.freeze()
        builds.append(config)
        return registry

    monkeypatch.setattr(bootstrap, "build_default_registry", build_registry)
    cache = RuntimePreparationCache()
    disabled_config = (("tests.synthetic_addon", False),)
    enabled_config = (("tests.synthetic_addon", True),)

    disabled = cache.default_registry(disabled_config)
    assert cache.default_registry(disabled_config) is disabled
    with pytest.raises(ValueError, match="must be retired"):
        cache.default_registry(enabled_config)
    cache.clear()
    enabled = cache.default_registry(enabled_config)

    assert disabled.spec_or_none(spec.type_id) is None
    assert enabled.spec_or_none(spec.type_id) == spec
    assert disabled.data_types.fingerprint() == enabled.data_types.fingerprint()
    assert disabled.plugin_fingerprint() == enabled.plugin_fingerprint()
    assert disabled.contract_fingerprint() != enabled.contract_fingerprint()
    assert builds == [disabled_config, enabled_config]


def _loose_source(type_id: str, value: int, *, marker: Path | None = None) -> str:
    marker_source = (
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('loaded', encoding='utf-8')\n"
        if marker is not None
        else ""
    )
    return f'''import corex
{marker_source}
@corex.node(id={type_id!r}, name="Worker Node", category=("Tests",))
@corex.output("result", value_type=int)
def worker_node(ctx):
    return {{"result": {value}}}
'''


def _adapter(
    runtime: WorkerPluginRuntime,
    registry: NodeRegistry,
    type_id: str,
):
    function_ref = registry.python_function_ref_or_none(type_id)
    assert function_ref is not None
    return runtime.create_adapter(function_ref, registry.get_spec(type_id))


def test_digit_leading_loose_filename_round_trips_through_worker(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    type_id = "custom.numeric_loose.1234abcd"
    (plugin_root / "1_numeric.py").write_text(
        _loose_source(type_id, 7),
        encoding="utf-8",
    )
    registry, (bundle,) = _discover(plugin_root, tmp_path / "generations")

    generation = read_verified_plugin_generation(bundle)
    assert generation.manifest["name"] == "plugin_1_numeric"

    runtime = WorkerPluginRuntime()
    worker_registry = runtime.prepare_registry(_command(registry), registry)
    assert _adapter(runtime, worker_registry, type_id).execute(_context()).outputs == {
        "result": 7
    }
    runtime.clear()


def test_worker_rehashes_generation_before_first_import(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    marker = tmp_path / "loaded.txt"
    source_path = plugin_root / "tamper.py"
    source_path.write_text(
        _loose_source("custom.worker_tamper.1234abcd", 1, marker=marker),
        encoding="utf-8",
    )
    registry, (bundle,) = _discover(plugin_root, tmp_path / "generations")
    assert not marker.exists()

    generation_source = Path(bundle.approved_generation_root) / "tamper.py"
    generation_source.write_text("raise RuntimeError('tampered')\n", encoding="utf-8")

    runtime = WorkerPluginRuntime()
    with pytest.raises(ValueError, match="digest mismatch"):
        runtime.prepare_registry(_command(registry), registry)
    assert not marker.exists()
    runtime.clear()


def test_verified_bytes_survive_later_disk_mutation_and_clear_unloads_modules(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    first_type = "custom.worker_first.1234abcd"
    second_type = "custom.worker_second.1234abcd"
    _write_package(
        plugin_root,
        name="cached_bytes",
        sources={
            "first.py": _loose_source(first_type, 1),
            "second.py": _loose_source(second_type, 2),
        },
        nodes=[
            {"id": first_type, "module": "first.py", "function": "worker_node"},
            {"id": second_type, "module": "second.py", "function": "worker_node"},
        ],
    )
    registry, (bundle,) = _discover(plugin_root, tmp_path / "generations")
    command = _command(registry)
    runtime = WorkerPluginRuntime()
    worker_registry = runtime.prepare_registry(command, registry)

    first = _adapter(runtime, worker_registry, first_type)
    assert first.execute(_context()).outputs == {"result": 1}
    first_module = first._function.__module__  # noqa: SLF001
    assert bundle.bundle_digest in first_module

    generation_second = Path(bundle.approved_generation_root) / "second.py"
    generation_second.write_text("raise RuntimeError('mutated')\n", encoding="utf-8")
    second = _adapter(runtime, worker_registry, second_type)
    assert second.execute(_context()).outputs == {"result": 2}
    second_module = second._function.__module__  # noqa: SLF001
    assert bundle.bundle_digest in second_module

    runtime.clear()
    assert first_module not in sys.modules
    assert second_module not in sys.modules
    with pytest.raises(ValueError, match="digest mismatch"):
        runtime.prepare_registry(command, registry)
    runtime.clear()


def test_worker_generation_change_requires_retirement(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    source_path = plugin_root / "replace.py"
    type_id = "custom.worker_replace.1234abcd"
    source_path.write_text(_loose_source(type_id, 1), encoding="utf-8")
    first_registry, _bundles = _discover(plugin_root, tmp_path / "generations")
    source_path.write_text(_loose_source(type_id, 2), encoding="utf-8")
    second_registry, _bundles = _discover(plugin_root, tmp_path / "generations")

    runtime = WorkerPluginRuntime()
    first_worker_registry = runtime.prepare_registry(
        _command(first_registry),
        first_registry,
    )
    assert _adapter(runtime, first_worker_registry, type_id).execute(
        _context()
    ).outputs == {"result": 1}
    with pytest.raises(ValueError, match="must be retired"):
        runtime.prepare_registry(_command(second_registry), second_registry)

    runtime.clear()
    second_worker_registry = runtime.prepare_registry(
        _command(second_registry),
        second_registry,
    )
    assert _adapter(runtime, second_worker_registry, type_id).execute(
        _context()
    ).outputs == {"result": 2}
    runtime.clear()


def test_workflow_lazily_runs_async_datatree_iterations_and_ordered_warnings(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    load_marker = tmp_path / "used-loaded.txt"
    unused_marker = tmp_path / "unused-loaded.txt"
    nodes_source = f'''import asyncio
import corex
from pathlib import Path
from .helpers import bump
Path({str(load_marker)!r}).write_text("loaded", encoding="utf-8")

@corex.node(id="custom.worker_values.1234abcd", name="Values", category=("Tests",))
@corex.output("values", value_type=int, structure="list")
def values(ctx):
    return {{"values": [1, 2, 3]}}

@corex.node(id="custom.worker_scale.1234abcd", name="Scale", category=("Tests",))
@corex.input("value", value_type=int, required=True)
@corex.output("scaled", value_type=int)
@corex.number("factor", default=2)
async def scale(ctx, value, settings):
    await asyncio.sleep(0)
    ctx.warn(f"iteration-{{ctx.target_iteration}}", code="worker_iteration")
    return {{"scaled": bump(value) * settings.factor}}
'''
    _write_package(
        plugin_root,
        name="worker_flow",
        sources={
            "nodes.py": nodes_source,
            "helpers.py": "def bump(value):\n    return value + 1\n",
        },
        nodes=[
            {
                "id": "custom.worker_values.1234abcd",
                "module": "nodes.py",
                "function": "values",
            },
            {
                "id": "custom.worker_scale.1234abcd",
                "module": "nodes.py",
                "function": "scale",
            },
        ],
    )
    (plugin_root / "unused.py").write_text(
        _loose_source(
            "custom.worker_unused.1234abcd",
            99,
            marker=unused_marker,
        ),
        encoding="utf-8",
    )
    registry, _bundles = _discover(
        plugin_root,
        tmp_path / "generations",
        registry=build_builtin_registry(),
    )
    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(
        workspace.workspace_id,
        "custom.worker_values.1234abcd",
        "Values",
        0,
        0,
    )
    scale = model.add_node(
        workspace.workspace_id,
        "custom.worker_scale.1234abcd",
        "Scale",
        200,
        0,
        properties={"factor": 2},
    )
    model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "values",
        scale.node_id,
        "value",
    )
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    command = _command(
        registry,
        runtime_snapshot=snapshot,
        workspace_id=workspace.workspace_id,
        run_id="run_public_flow",
    )
    event_queue: queue.Queue = queue.Queue()

    with patch(
        "ea_node_editor.nodes.bootstrap.build_default_registry",
        return_value=registry,
    ):
        runner = WorkflowRunner(command, event_queue)
        assert runner._preflight_error is None  # noqa: SLF001
        assert not load_marker.exists()
        assert not unused_marker.exists()
        runner.run()

    events = list(event_queue.queue)
    settled = next(
        event
        for event in events
        if event.get("type") == "node_settled" and event.get("node_id") == scale.node_id
    )
    tree = deserialize_runtime_value(
        settled["outputs"]["scaled"]["value"],
        catalog=registry.data_types,
    )
    assert isinstance(tree, DataTree)
    assert tree.branches == (((0,), (4, 6, 8)),)
    assert tuple(settled["warnings"]) == (
        "iteration-0",
        "iteration-1",
        "iteration-2",
    )
    assert load_marker.read_text(encoding="utf-8") == "loaded"
    assert not unused_marker.exists()
    assert any(event.get("type") == "run_completed" for event in events)


def test_public_function_cancellation_uses_existing_worker_context(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    started_marker = tmp_path / "started.txt"
    cancelled_marker = tmp_path / "cancelled.txt"
    wait_source = f'''import corex
import time
from pathlib import Path

@corex.node(id="custom.worker_wait.1234abcd", name="Wait", category=("Tests",))
@corex.output("done", value_type=bool)
def wait(ctx):
    Path({str(started_marker)!r}).write_text("started", encoding="utf-8")
    ctx.register_cancel(lambda: Path({str(cancelled_marker)!r}).write_text("cancelled", encoding="utf-8"))
    deadline = time.monotonic() + 5.0
    while not ctx.should_stop() and time.monotonic() < deadline:
        time.sleep(0.01)
    return {{"done": False}}
'''
    _write_package(
        plugin_root,
        name="worker_cancel",
        sources={"wait.py": wait_source},
        nodes=[
            {
                "id": "custom.worker_wait.1234abcd",
                "module": "wait.py",
                "function": "wait",
            }
        ],
    )
    registry, _bundles = _discover(
        plugin_root,
        tmp_path / "generations",
        registry=build_builtin_registry(),
    )
    model = GraphModel()
    workspace = model.active_workspace
    model.add_node(
        workspace.workspace_id,
        "custom.worker_wait.1234abcd",
        "Wait",
        0,
        0,
    )
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    command = _command(
        registry,
        runtime_snapshot=snapshot,
        workspace_id=workspace.workspace_id,
        run_id="run_public_cancel",
    )
    event_queue: queue.Queue = queue.Queue()
    command_queue: queue.Queue = queue.Queue()

    with patch(
        "ea_node_editor.nodes.bootstrap.build_default_registry",
        return_value=registry,
    ):
        runner = WorkflowRunner(command, event_queue, command_queue=command_queue)
        thread = threading.Thread(target=runner.run)
        thread.start()
        deadline = time.monotonic() + 3.0
        while not started_marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert started_marker.exists()
        command_queue.put(
            command_to_dict(
                StopRunCommand(
                    run_id=command.run_id,
                    workspace_id=command.workspace_id,
                )
            )
        )
        thread.join(timeout=3.0)

    assert not thread.is_alive()
    assert cancelled_marker.read_text(encoding="utf-8") == "cancelled"
    assert any(event.get("type") == "run_stopped" for event in event_queue.queue)


def test_spawned_worker_uses_pinned_generation_after_author_source_is_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from ea_node_editor.settings import plugins_dir

    marker = tmp_path / "spawned-worker-loaded.txt"
    source_path = plugins_dir() / "spawned.py"
    type_id = "custom.worker_spawned.1234abcd"
    source_path.write_text(
        _loose_source(type_id, 7, marker=marker),
        encoding="utf-8",
    )
    registry = build_default_registry()
    assert registry.python_function_ref_or_none(type_id) is not None
    assert not marker.exists()

    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        type_id,
        "Spawned",
        0,
        0,
    )
    snapshot = build_runtime_snapshot(
        model.project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )
    source_path.unlink()

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

    failures = [event for event in events if event.get("type") == "run_failed"]
    assert failures == []
    settled = next(
        event
        for event in events
        if event.get("type") == "node_settled" and event.get("node_id") == node.node_id
    )
    tree = deserialize_runtime_value(
        settled["outputs"]["result"]["value"],
        catalog=registry.data_types,
    )
    assert isinstance(tree, DataTree)
    assert tree.branches == (((0,), (7,)),)
    assert marker.read_text(encoding="utf-8") == "loaded"


def test_trusted_client_rejects_public_generations_before_state_changes(
    tmp_path: Path,
) -> None:
    digest = "a" * 64
    function_ref = PythonFunctionRef(
        bundle_id="plugin:file:trusted_reject",
        bundle_digest=digest,
        module_relative_path="node.py",
        function_name="node",
        source_digest="b" * 64,
    )
    bundle = PluginBundleRef(
        owner_id=function_ref.bundle_id,
        version="0.0.0",
        generation_id=digest,
        bundle_digest=digest,
        approved_generation_root=str(tmp_path.resolve()),
        functions=(function_ref,),
    )
    client = TrustedInProcessExecutionClient()
    events: list[dict[str, object]] = []
    client.subscribe(events.append)
    try:
        run_id = client.start_run(
            "",
            "workspace",
            plugin_bundles=(bundle,),
            plugin_fingerprint="c" * 64,
            data_types=build_builtin_registry().data_types,
        )
        assert run_id == ""
        assert client._data_types is None  # noqa: SLF001
        assert client._catalog_generation_fingerprint == ""  # noqa: SLF001
        assert any(
            "require process-isolated execution" in str(event.get("error", ""))
            for event in events
        )
    finally:
        client.shutdown()
