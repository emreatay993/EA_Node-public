from __future__ import annotations

import ast
import shutil
import threading
from pathlib import Path

import corex

from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.plugin_loader import discover_static_plugin_candidate
from ea_node_editor.runtime_contracts import DataTree, deserialize_runtime_value
from ea_node_editor.settings import plugin_generations_dir


_REPO_ROOT = Path(__file__).parents[1]
_EXAMPLES = (
    _REPO_ROOT / "docs/examples/signal_plot_function_plugin.py",
    _REPO_ROOT / "docs/examples/strain_conditioner_plugin.py",
)
_TYPE_IDS = {
    "custom.signal_plot_style.7b9c2d4e",
    "custom.strain_conditioner.a7c31e9b",
}


def test_public_examples_are_static_corex_only_declarations() -> None:
    assert corex.__all__ == [
        "node",
        "input",
        "output",
        "text",
        "text_area",
        "number",
        "switch",
        "dropdown",
        "slider",
        "color",
        "path",
        "interval",
        "list",
        "Any",
        "Image",
        "Color",
        "Interval",
    ]

    found_ids: set[str] = set()
    for path in _EXAMPLES:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        imports = [
            alias.name
            for statement in tree.body
            if isinstance(statement, ast.Import)
            for alias in statement.names
        ]
        assert imports == ["corex"]
        assert not any(isinstance(statement, ast.ImportFrom) for statement in tree.body)
        assert not any(
            keyword.arg and keyword.arg.startswith("_")
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for keyword in node.keywords
        )
        found_ids.update(
            declaration.spec.type_id
            for declaration in discover_plugin_declarations(
                source,
                filename=path.name,
            )
        )

    assert found_ids == _TYPE_IDS


def test_public_guides_do_not_teach_removed_plugin_apis() -> None:
    paths = (
        _REPO_ROOT / "README.md",
        _REPO_ROOT / "docs/GETTING_STARTED.md",
        _REPO_ROOT / "docs/PYTHON_SCRIPT_GUIDE.md",
        _REPO_ROOT / "docs/PLUGIN_AUTHORING_GUIDE.md",
        *_EXAMPLES,
    )
    forbidden = (
        "from ea_node_editor.nodes import",
        "from ea_node_editor.nodes.types import",
        "from ea_node_editor.plugins",
        "@node_type(",
        "PLUGIN_DESCRIPTORS =",
        "PluginDescriptor(",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path}: removed public API {token!r}"


def test_port_typing_guides_require_explicit_types_and_explain_search_fallbacks() -> None:
    for name in ("PLUGIN_AUTHORING_GUIDE.md", "PLUGIN_MIGRATION_GUIDE.md", "PYTHON_SCRIPT_GUIDE.md"):
        text = (_REPO_ROOT / "docs" / name).read_text(encoding="utf-8")
        assert "requires explicit `value_type=`" in text, name
        assert "`value_type=corex.Any`" in text, name
        assert "`Broad data match`" in text, name
        assert "`Checked at runtime`" in text, name


def test_examples_build_one_candidate_registry_and_strain_runs_in_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    for example in _EXAMPLES:
        shutil.copyfile(example, plugin_root / example.name)

    generation_root = plugin_generations_dir()
    registry = build_builtin_registry(generation_root=generation_root)
    result = discover_static_plugin_candidate(
        registry,
        roots=(plugin_root,),
        generation_root=generation_root,
    )
    registry.freeze()

    assert set(result.type_ids) == _TYPE_IDS
    assert all(registry.unavailable_reason(type_id) == "" for type_id in _TYPE_IDS)

    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "custom.strain_conditioner.a7c31e9b",
        "Strain Conditioner",
        0,
        0,
        properties={
            "strain": 0.000037,
            "scale": 1000000.0,
            "absolute": False,
        },
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
        assert run_id, [event.get("error") for event in events]
        assert terminal.wait(timeout=30.0)
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
        settled["outputs"]["conditioned_strain"]["value"],
        catalog=registry.data_types,
    )
    assert isinstance(tree, DataTree)
    assert tree.branches == (((0,), (37.0,)),)
