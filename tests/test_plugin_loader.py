from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest

import ea_node_editor.nodes as nodes_package
from ea_node_editor.common import path_safety
from ea_node_editor.nodes import bootstrap, plugin_loader
from ea_node_editor.nodes import plugin_generation
from ea_node_editor.nodes import package_schema
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.nodes import plugin_contracts
from ea_node_editor.nodes.plugin_contracts import PluginProvenance
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.plugin_generation import prune_plugin_generations


def _write_text(path: Path, contents: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def test_bootstrap_import_keeps_builtin_and_public_plugin_routes_lazy() -> None:
    script = """
import sys
import ea_node_editor.nodes.bootstrap
assert 'ea_node_editor.nodes.builtin_catalog' not in sys.modules
assert 'ea_node_editor.nodes.plugin_loader' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def _function_source(
    type_id: str,
    *,
    description: str = "",
    prelude: str = "",
    import_line: str = "",
) -> str:
    extra_import = f"{import_line}\n" if import_line else ""
    return f"""import corex
{extra_import}{prelude}
@corex.node(
    id={type_id!r},
    name="Static Node",
    category=("Tests",),
    description={description!r},
)
@corex.input("value", value_type=float)
@corex.output("result", value_type=float)
def static_node(ctx, value):
    return {{"result": value}}
"""


def _write_schema2_package(
    root: Path,
    *,
    name: str,
    sources: dict[str, str],
    modules: list[str],
    nodes: list[dict[str, str]],
) -> Path:
    package_dir = root / name
    source_records = []
    for relative_path, source in sources.items():
        source_path = _write_text(package_dir / relative_path, source)
        payload = source_path.read_bytes()
        source_records.append(
            {"path": relative_path, "sha256": hashlib.sha256(payload).hexdigest()}
        )
    manifest = {
        "schema_version": 2,
        "name": name,
        "version": "1.0.0",
        "author": "",
        "description": "",
        "modules": modules,
        "sources": source_records,
        "assets": [],
        "nodes": nodes,
    }
    _write_text(
        package_dir / "node_package.json",
        json.dumps(manifest, indent=2) + "\n",
    )
    return package_dir


def _write_function_package(
    root: Path,
    *,
    name: str,
    type_id: str,
    source: str,
) -> Path:
    return _write_schema2_package(
        root,
        name=name,
        sources={"nodes.py": source},
        modules=["nodes.py"],
        nodes=[{"id": type_id, "module": "nodes.py", "function": "static_node"}],
    )


def test_candidate_registry_statically_overrides_package_and_matches_final(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed_root = tmp_path / "installed"
    loose_type_id = "custom.candidate_loose.1234abcd"
    replaced_type_id = "custom.candidate_replaced.1234abcd"
    _write_text(installed_root / "loose.py", _function_source(loose_type_id))
    installed_package = _write_function_package(
        installed_root,
        name="candidate_package",
        type_id=replaced_type_id,
        source=_function_source(replaced_type_id, description="installed"),
    )
    installed_bytes = (installed_package / "nodes.py").read_bytes()
    marker = tmp_path / "executed.txt"
    replacement_source = _function_source(
        replaced_type_id,
        description="replacement",
        prelude=(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')"
        ),
    )
    staged_package = _write_function_package(
        tmp_path / "staged",
        name="candidate_package",
        type_id=replaced_type_id,
        source=replacement_source,
    )
    baseline = bootstrap.build_default_registry(include_public_plugins=False)
    monkeypatch.setattr(bootstrap, "plugins_dir", lambda: installed_root)

    candidate_root = tmp_path / "candidate-generations"
    candidate = bootstrap.build_plugin_candidate_registry(
        generation_root=candidate_root,
        staged_package_root=staged_package,
    )

    assert candidate.get_spec(replaced_type_id).description == "replacement"
    assert candidate.spec_or_none(loose_type_id) is not None
    assert (installed_package / "nodes.py").read_bytes() == installed_bytes
    assert not marker.exists()
    assert {
        Path(bundle.approved_generation_root).parent
        for bundle in candidate.plugin_bundle_refs()
    } == {candidate_root.resolve()}
    assert candidate.data_types.fingerprint() == baseline.data_types.fingerprint()
    assert {
        spec.type_id
        for spec in candidate.all_specs()
        if candidate.python_function_ref_or_none(spec.type_id) is None
    } == {
        spec.type_id
        for spec in baseline.all_specs()
        if baseline.python_function_ref_or_none(spec.type_id) is None
    }

    final_root = tmp_path / "final-installed"
    _write_text(final_root / "loose.py", _function_source(loose_type_id))
    _write_function_package(
        final_root,
        name="candidate_package",
        type_id=replaced_type_id,
        source=replacement_source,
    )
    monkeypatch.setattr(bootstrap, "plugins_dir", lambda: final_root)
    final = bootstrap.build_plugin_candidate_registry(
        generation_root=tmp_path / "canonical-generations",
    )

    assert candidate.plugin_fingerprint() == final.plugin_fingerprint()
    assert {bundle.bundle_digest for bundle in candidate.plugin_bundle_refs()} == {
        bundle.bundle_digest for bundle in final.plugin_bundle_refs()
    }
    assert not marker.exists()


def test_candidate_registry_rejects_conflict_outside_replaced_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed_root = tmp_path / "installed"
    replaced_type_id = "custom.replaced.1234abcd"
    retained_type_id = "custom.retained.1234abcd"
    _write_function_package(
        installed_root,
        name="replace_me",
        type_id=replaced_type_id,
        source=_function_source(replaced_type_id),
    )
    _write_function_package(
        installed_root,
        name="retain_me",
        type_id=retained_type_id,
        source=_function_source(retained_type_id),
    )
    staged_package = _write_function_package(
        tmp_path / "staged",
        name="replace_me",
        type_id=retained_type_id,
        source=_function_source(retained_type_id, description="conflict"),
    )
    monkeypatch.setattr(bootstrap, "plugins_dir", lambda: installed_root)

    with pytest.raises(ValueError, match="conflicts with an active node id"):
        bootstrap.build_plugin_candidate_registry(
            generation_root=tmp_path / "generations",
            staged_package_root=staged_package,
        )


def test_candidate_override_requires_exact_installed_package_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed_root = tmp_path / "installed"
    _write_function_package(
        installed_root,
        name="same-owner",
        type_id="custom.same_owner_old.1234abcd",
        source=_function_source("custom.same_owner_old.1234abcd"),
    )
    staged_package = _write_function_package(
        tmp_path / "staged",
        name="same_owner",
        type_id="custom.same_owner_new.1234abcd",
        source=_function_source("custom.same_owner_new.1234abcd"),
    )
    monkeypatch.setattr(bootstrap, "plugins_dir", lambda: installed_root)

    with pytest.raises(ValueError, match="owner is already active"):
        bootstrap.build_plugin_candidate_registry(
            generation_root=tmp_path / "generations",
            staged_package_root=staged_package,
        )


def test_loose_function_plugins_are_discovered_without_execution_and_materialized(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    generation_root = tmp_path / "generations"
    marker = tmp_path / "executed.txt"
    source_path = _write_text(
        plugin_root / "safe_node.py",
        _function_source(
            "custom.safe_node.1234abcd",
            prelude=(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')"
            ),
        ),
    )
    source_bytes = source_path.read_bytes()
    registry = NodeRegistry()

    result = plugin_loader.discover_static_plugins(
        registry,
        roots=(plugin_root,),
        generation_root=generation_root,
    )

    assert result.type_ids == ("custom.safe_node.1234abcd",)
    assert len(result.bundles) == 1
    bundle = result.bundles[0]
    generation = Path(bundle.approved_generation_root)
    assert generation.parent == generation_root.resolve()
    assert (generation / "safe_node.py").read_bytes() == source_bytes
    assert (generation / "node_package.json").is_file()
    assert not marker.exists()
    assert registry.spec_or_none("custom.safe_node.1234abcd") is not None
    assert registry.descriptor_or_none("custom.safe_node.1234abcd") is None
    assert registry.plugin_bundle_refs() == (bundle,)
    assert registry.plugin_fingerprint() == result.plugin_fingerprint
    assert len(result.plugin_fingerprint) == 64
    with pytest.raises(RuntimeError, match="worker resolution"):
        registry.create("custom.safe_node.1234abcd")


def test_generation_reuse_and_source_changes_are_content_addressed(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    generation_root = tmp_path / "generations"
    source_path = _write_text(
        plugin_root / "scale.py",
        _function_source("custom.scale.1234abcd", description="first"),
    )

    first_registry = NodeRegistry()
    first = plugin_loader.discover_static_plugins(
        first_registry,
        roots=(plugin_root,),
        generation_root=generation_root,
    )
    first_bundle = first.bundles[0]
    first_generation = Path(first_bundle.approved_generation_root)
    first_bytes = (first_generation / "scale.py").read_bytes()

    second = plugin_loader.discover_static_plugins(
        NodeRegistry(),
        roots=(plugin_root,),
        generation_root=generation_root,
    )
    assert second.bundles[0].bundle_digest == first_bundle.bundle_digest
    assert second.bundles[0].approved_generation_root == str(first_generation)
    assert second.plugin_fingerprint == first.plugin_fingerprint

    source_path.write_text(
        _function_source("custom.scale.1234abcd", description="second"),
        encoding="utf-8",
    )
    third_registry = NodeRegistry()
    third = plugin_loader.discover_static_plugins(
        third_registry,
        roots=(plugin_root,),
        generation_root=generation_root,
    )
    assert third.bundles[0].bundle_digest != first_bundle.bundle_digest
    assert third.plugin_fingerprint != first.plugin_fingerprint
    assert third_registry.get_spec("custom.scale.1234abcd").description == "second"
    assert (first_generation / "scale.py").read_bytes() == first_bytes

    source_path.write_text(
        "raise RuntimeError('mutable source changed')\n", encoding="utf-8"
    )
    assert third_registry.get_spec("custom.scale.1234abcd").description == "second"
    assert (first_generation / "scale.py").read_bytes() == first_bytes
    assert (
        len(
            [
                path
                for path in generation_root.iterdir()
                if path.is_dir() and len(path.name) == 64
            ]
        )
        == 2
    )


def test_missing_import_keeps_node_visible_with_exact_locked_reason(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    missing_module = "codex_missing_dependency_7f31a9"
    _write_text(
        plugin_root / "missing.py",
        _function_source(
            "custom.missing.1234abcd",
            import_line=f"import {missing_module}",
        ),
    )
    registry = NodeRegistry()

    result = plugin_loader.discover_static_plugins(
        registry,
        roots=(plugin_root,),
        generation_root=tmp_path / "generations",
    )

    reason = f"{missing_module} is not included in this COREX bundle."
    assert result.type_ids == ("custom.missing.1234abcd",)
    assert registry.spec_or_none("custom.missing.1234abcd") is not None
    assert registry.unavailable_reason("custom.missing.1234abcd") == reason
    assert result.bundles[0].unavailable_reason == reason
    assert str(tmp_path) not in reason
    with pytest.raises(RuntimeError, match=re.escape(reason)):
        registry.create("custom.missing.1234abcd")


def test_invalid_and_conflicting_loose_bundles_fail_closed_without_side_effects(
    tmp_path: Path,
    caplog,
) -> None:
    plugin_root = tmp_path / "plugins"
    generation_root = tmp_path / "generations"
    marker = tmp_path / "invalid-executed.txt"
    _write_text(
        plugin_root / "a_first.py",
        _function_source("custom.duplicate.1234abcd", description="first"),
    )
    _write_text(
        plugin_root / "b_duplicate.py",
        _function_source("custom.duplicate.1234abcd", description="second"),
    )
    _write_text(
        plugin_root / "c_invalid.py",
        f"""import corex
from pathlib import Path
Path({str(marker)!r}).write_text("executed", encoding="utf-8")
@corex.node(id="custom.invalid.1234abcd", name="Invalid", category=("Tests",))
@corex.number("factor", default=make_default())
def invalid(ctx, settings): return {{}}
""",
    )
    _write_text(
        plugin_root / "d_partial.py",
        """import corex
@corex.node(id="custom.partial_good.1234abcd", name="Good", category=("Tests",))
def good(ctx): return {}
@corex.node(id="custom.partial_bad.1234abcd", name="Bad", category=("Tests",))
@corex.output("value", value_type="Missing.Type")
def bad(ctx): return {"value": 1}
""",
    )
    caplog.set_level(logging.WARNING, logger=plugin_loader.__name__)
    registry = NodeRegistry()

    result = plugin_loader.discover_static_plugins(
        registry,
        roots=(plugin_root,),
        generation_root=generation_root,
    )

    assert result.type_ids == ("custom.duplicate.1234abcd",)
    assert registry.get_spec("custom.duplicate.1234abcd").description == "first"
    assert registry.spec_or_none("custom.invalid.1234abcd") is None
    assert registry.spec_or_none("custom.partial_good.1234abcd") is None
    assert registry.spec_or_none("custom.partial_bad.1234abcd") is None
    assert not marker.exists()
    assert str(tmp_path) not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert (
        len([path for path in generation_root.iterdir() if len(path.name) == 64]) == 1
    )


def test_schema2_package_is_static_and_schema1_directory_is_rejected(
    tmp_path: Path,
    caplog,
) -> None:
    plugin_root = tmp_path / "plugins"
    marker = tmp_path / "package-executed.txt"
    nodes_source = f"""import corex
from pathlib import Path
from .helpers import helper
Path({str(marker)!r}).write_text("executed", encoding="utf-8")
@corex.node(id="custom.package_node.1234abcd", name="Package Node", category=("Tests",))
@corex.input("value", value_type=float)
@corex.output("result", value_type=float)
def package_node(ctx, value): return {{"result": helper(value)}}
"""
    package_dir = _write_schema2_package(
        plugin_root,
        name="static_package",
        sources={
            "nodes.py": nodes_source,
            "helpers.py": "def helper(value): return value\n",
        },
        modules=["nodes.py"],
        nodes=[
            {
                "id": "custom.package_node.1234abcd",
                "module": "nodes.py",
                "function": "package_node",
            }
        ],
    )
    legacy_dir = plugin_root / "legacy_package"
    _write_text(
        legacy_dir / "node_package.json",
        json.dumps({"name": "legacy_package", "version": "1.0.0", "nodes": []}),
    )
    caplog.set_level(logging.WARNING, logger=plugin_loader.__name__)
    registry = NodeRegistry()

    result = plugin_loader.discover_static_plugins(
        registry,
        roots=(plugin_root,),
        generation_root=tmp_path / "generations",
    )

    assert result.type_ids == ("custom.package_node.1234abcd",)
    bundle = result.bundles[0]
    generation = Path(bundle.approved_generation_root)
    provenance = registry.provenance_or_none("custom.package_node.1234abcd")
    assert (generation / "nodes.py").read_text(encoding="utf-8") == nodes_source
    assert (generation / "helpers.py").read_text(encoding="utf-8") == (
        package_dir / "helpers.py"
    ).read_text(encoding="utf-8")
    assert not marker.exists()
    assert registry.spec_or_none("custom.package_node.1234abcd") is not None
    assert provenance == PluginProvenance(
        kind="package",
        source_path=generation / "nodes.py",
        package_root=generation,
        package_name="static_package",
    )
    assert "plugin:package:legacy_package" in caplog.text
    assert str(tmp_path) not in caplog.text

    candidate_registry = NodeRegistry()
    candidate = plugin_loader.discover_static_plugin_candidate(
        candidate_registry,
        roots=(),
        generation_root=tmp_path / "direct-generations",
        staged_package_root=package_dir,
    )
    assert candidate.type_ids == ("custom.package_node.1234abcd",)


def test_dotted_bundled_source_and_dev_only_imports_are_locked(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    nodes_source = """import corex
from .helpers.missing import value
@corex.node(id="custom.dotted.1234abcd", name="Dotted", category=("Tests",))
def dotted(ctx): return {}
"""
    _write_schema2_package(
        plugin_root,
        name="dotted_package",
        sources={"nodes.py": nodes_source, "helpers.py": "VALUE = 1\n"},
        modules=["nodes.py"],
        nodes=[
            {
                "id": "custom.dotted.1234abcd",
                "module": "nodes.py",
                "function": "dotted",
            }
        ],
    )
    _write_text(
        plugin_root / "dev_only.py",
        _function_source(
            "custom.dev_only.1234abcd",
            import_line="import pytest",
        ),
    )
    registry = NodeRegistry()

    result = plugin_loader.discover_static_plugins(
        registry,
        roots=(plugin_root,),
        generation_root=tmp_path / "generations",
    )

    assert set(result.type_ids) == {
        "custom.dev_only.1234abcd",
        "custom.dotted.1234abcd",
    }
    assert registry.unavailable_reason("custom.dotted.1234abcd") == (
        "helpers.missing is not included in this COREX bundle."
    )
    assert registry.unavailable_reason("custom.dev_only.1234abcd") == (
        "pytest is not included in this COREX bundle."
    )


def test_symlinked_discovery_roots_and_entries_are_rejected(
    tmp_path: Path,
    monkeypatch,
) -> None:
    linked_root = tmp_path / "linked-root"
    _write_text(
        linked_root / "outside.py",
        _function_source("custom.outside.1234abcd"),
    )
    regular_root = tmp_path / "regular-root"
    linked_file = _write_text(
        regular_root / "linked.py",
        _function_source("custom.linked_entry.1234abcd"),
    )
    simulated_symlinks = {linked_root, linked_file}
    monkeypatch.setattr(
        plugin_loader,
        "is_reparse_point",
        lambda path: path in simulated_symlinks,
    )

    registry = NodeRegistry()
    result = plugin_loader.discover_static_plugins(
        registry,
        roots=(linked_root, regular_root),
        generation_root=tmp_path / "generations",
    )

    assert result.type_ids == ()
    assert registry.spec_or_none("custom.outside.1234abcd") is None


def test_path_alias_detector_recognizes_posix_symlink_mode(monkeypatch) -> None:
    monkeypatch.setattr(
        path_safety.os,
        "lstat",
        lambda _path: SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0),
    )

    assert path_safety.is_reparse_point(Path("alias"))


def test_oversized_sources_and_unbounded_roots_fail_before_full_discovery(
    tmp_path: Path,
) -> None:
    oversized_root = tmp_path / "oversized"
    oversized_root.mkdir()
    (oversized_root / "huge.py").write_bytes(b"#" * (256 * 1024 + 1))
    oversized = plugin_loader.discover_static_plugins(
        NodeRegistry(),
        roots=(oversized_root,),
        generation_root=tmp_path / "oversized-generations",
    )
    assert oversized.type_ids == ()

    crowded_root = tmp_path / "crowded"
    crowded_root.mkdir()
    for index in range(513):
        (crowded_root / f"empty-{index}.txt").touch()
    crowded = plugin_loader.discover_static_plugins(
        NodeRegistry(),
        roots=(crowded_root,),
        generation_root=tmp_path / "crowded-generations",
    )
    assert crowded.type_ids == ()


def test_package_aggregate_limit_rejects_before_reading_excess_member(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = tmp_path / "plugins" / "aggregate_package"
    source_path = _write_text(package_dir / "nodes.py", "import corex\n")
    zero_digest = hashlib.sha256(b"\0" * (4 * 1024 * 1024)).hexdigest()
    assets = []
    for index in range(4):
        asset_path = package_dir / f"asset-{index}.png"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        with asset_path.open("wb") as stream:
            stream.seek(4 * 1024 * 1024 - 1)
            stream.write(b"\0")
        assets.append({"path": asset_path.name, "sha256": zero_digest})
    manifest = {
        "schema_version": 2,
        "name": "aggregate_package",
        "version": "1.0.0",
        "modules": ["nodes.py"],
        "sources": [
            {
                "path": "nodes.py",
                "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            }
        ],
        "assets": assets,
        "nodes": [],
    }
    _write_text(package_dir / "node_package.json", json.dumps(manifest))
    calls: list[str] = []
    read_member = package_schema._read_package_member  # noqa: SLF001

    def recording_read_member(package_root, relative_path, *, limit):  # noqa: ANN001
        calls.append(relative_path)
        return read_member(package_root, relative_path, limit=limit)

    monkeypatch.setattr(package_schema, "_read_package_member", recording_read_member)

    with pytest.raises(ValueError, match="expanded size"):
        package_schema.read_validated_package_directory(package_dir)
    assert calls == ["nodes.py", "asset-0.png", "asset-1.png", "asset-2.png"]


def test_package_aggregate_limit_checks_actual_bytes_after_each_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = tmp_path / "plugins" / "actual_size_package"
    source_path = _write_text(package_dir / "nodes.py", "x")
    manifest = {
        "schema_version": 2,
        "name": package_dir.name,
        "version": "1.0.0",
        "modules": [source_path.name],
        "sources": [
            {
                "path": source_path.name,
                "sha256": hashlib.sha256(b"xyz").hexdigest(),
            }
        ],
        "assets": [],
        "nodes": [],
    }
    manifest_path = _write_text(
        package_dir / package_schema.MANIFEST_FILENAME,
        json.dumps(manifest),
    )
    monkeypatch.setattr(
        package_schema,
        "PLUGIN_TOTAL_LIMIT",
        len(manifest_path.read_bytes()) + 2,
    )
    monkeypatch.setattr(
        package_schema,
        "_read_package_member",
        lambda _root, _path, *, limit: b"xyz",
    )

    with pytest.raises(ValueError, match="expanded size"):
        package_schema.read_validated_package_directory(package_dir)


def test_plugin_fingerprint_is_independent_of_install_and_generation_roots(
    tmp_path: Path,
) -> None:
    source = _function_source("custom.portable.1234abcd")
    root_a = tmp_path / "install-a" / "plugins"
    root_b = tmp_path / "install-b" / "plugins"
    _write_text(root_a / "portable.py", source)
    _write_text(root_b / "portable.py", source)

    first = plugin_loader.discover_static_plugins(
        NodeRegistry(),
        roots=(root_a,),
        generation_root=tmp_path / "generations-a",
    )
    second = plugin_loader.discover_static_plugins(
        NodeRegistry(),
        roots=(root_b,),
        generation_root=tmp_path / "generations-b",
    )

    assert first.plugin_fingerprint == second.plugin_fingerprint
    assert first.bundles[0].bundle_digest == second.bundles[0].bundle_digest
    assert (
        first.bundles[0].approved_generation_root
        != second.bundles[0].approved_generation_root
    )


def test_tampered_existing_generation_is_never_reused(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    generation_root = tmp_path / "generations"
    _write_text(
        plugin_root / "tamper.py",
        _function_source("custom.tamper.1234abcd"),
    )
    first = plugin_loader.discover_static_plugins(
        NodeRegistry(),
        roots=(plugin_root,),
        generation_root=generation_root,
    )
    generation = Path(first.bundles[0].approved_generation_root)
    (generation / "tamper.py").write_text("tampered\n", encoding="utf-8")
    registry = NodeRegistry()

    second = plugin_loader.discover_static_plugins(
        registry,
        roots=(plugin_root,),
        generation_root=generation_root,
    )

    assert second.type_ids == ()
    assert registry.spec_or_none("custom.tamper.1234abcd") is None


def test_symlinked_generation_member_is_never_accepted_as_immutable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin_root = tmp_path / "plugins"
    generation_root = tmp_path / "generations"
    _write_text(
        plugin_root / "alias.py",
        _function_source("custom.alias_generation.1234abcd"),
    )
    first = plugin_loader.discover_static_plugins(
        NodeRegistry(),
        roots=(plugin_root,),
        generation_root=generation_root,
    )
    generation_source = Path(first.bundles[0].approved_generation_root) / "alias.py"
    monkeypatch.setattr(
        plugin_generation,
        "is_reparse_point",
        lambda path: path == generation_source,
    )

    registry = NodeRegistry()
    second = plugin_loader.discover_static_plugins(
        registry,
        roots=(plugin_root,),
        generation_root=generation_root,
    )

    assert second.type_ids == ()
    assert registry.spec_or_none("custom.alias_generation.1234abcd") is None


def test_hard_linked_generation_member_is_never_accepted_as_immutable(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    generation_root = tmp_path / "generations"
    source_path = _write_text(
        plugin_root / "hardlink.py",
        _function_source("custom.hardlink_generation.1234abcd"),
    )
    first = plugin_loader.discover_static_plugins(
        NodeRegistry(),
        roots=(plugin_root,),
        generation_root=generation_root,
    )
    generation_source = Path(first.bundles[0].approved_generation_root) / "hardlink.py"
    generation_source.unlink()
    os.link(source_path, generation_source)
    assert generation_source.stat().st_nlink > 1

    registry = NodeRegistry()
    second = plugin_loader.discover_static_plugins(
        registry,
        roots=(plugin_root,),
        generation_root=generation_root,
    )

    assert second.type_ids == ()
    assert registry.spec_or_none("custom.hardlink_generation.1234abcd") is None


def test_generation_pruning_preserves_active_referenced_and_unknown_directories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    generation_root = tmp_path / "generations"
    active = "a" * 64
    referenced = "b" * 64
    inactive = "c" * 64
    aliased = "d" * 64
    for name in (active, referenced, inactive, aliased, "manual-not-a-generation"):
        _write_text(generation_root / name / "marker.txt", name)
    monkeypatch.setattr(
        plugin_generation,
        "is_reparse_point",
        lambda path: path == generation_root / aliased,
    )

    removed = prune_plugin_generations(
        generation_root,
        active_digests=(active,),
        referenced_digests=(referenced,),
    )

    assert removed == (inactive,)
    assert (generation_root / active).is_dir()
    assert (generation_root / referenced).is_dir()
    assert not (generation_root / inactive).exists()
    assert (generation_root / aliased).is_dir()
    assert (generation_root / "manual-not-a-generation").is_dir()


def test_legacy_public_sdk_and_class_loading_surfaces_are_absent() -> None:
    source = Path(plugin_loader.__file__).read_text(encoding="utf-8")
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    assert {
        "in_port",
        "node_type",
        "out_port",
        "prop_bool",
        "prop_enum",
        "prop_float",
        "prop_int",
        "prop_interval_1d",
        "prop_json",
        "prop_str",
    }.isdisjoint(vars(nodes_package))
    assert importlib.util.find_spec("ea_node_editor.nodes.types") is None
    assert not hasattr(plugin_contracts, "AsyncNodePlugin")
    assert not hasattr(plugin_contracts, "__all__")
    assert set(get_args(plugin_contracts.PluginProvenanceKind)) == {
        "file",
        "package",
        "runtime",
    }
    assert {"distribution_name", "entry_point_name"}.isdisjoint(
        PluginProvenance.__dataclass_fields__
    )
    assert not hasattr(plugin_loader, "discover_and_load_plugins")
    assert not hasattr(plugin_loader, "discover_package_plugins")
    assert not hasattr(plugin_loader, "discover_addon_records")
    assert not hasattr(plugin_loader, "addon_record_by_id")
    assert not hasattr(plugin_loader, "__all__")
    for legacy_surface in (
        "ENTRY_POINT_GROUP",
        "PLUGIN_BACKENDS",
        "PLUGIN_DESCRIPTORS",
        ".load()",
        "exec_module",
        "getmembers",
    ):
        assert legacy_surface not in source
    assert "ea_node_editor.plugins" not in pyproject
