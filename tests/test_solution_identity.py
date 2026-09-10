from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

import ea_node_editor.execution.solution_identity as solution_identity_module
from ea_node_editor.execution.solution_identity import (
    ExecutionEnvironmentIdentity,
    IncomingEdgeIdentity,
    NodeSolutionIdentity,
    ProvenanceHashPolicy,
    SolutionIdentityError,
    canonical_digest,
    catalog_revision_digest,
    corex_build_digest,
    execution_policy_digest,
    hash_directory_provenance,
    hash_file_provenance,
    implementation_digest,
    provenance_digest,
    solution_key,
)
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.runtime_contracts import DataTree


_DIGESTS = tuple(character * 64 for character in "abcdef012")


def _identity() -> NodeSolutionIdentity:
    return NodeSolutionIdentity(
        solution_namespace_id="solution-namespace",
        workspace_id="workspace",
        node_id="node",
        node_type_id="data.number_slider",
        node_interface_revision=1,
        node_interface_digest=_DIGESTS[0],
        node_contract_digest=_DIGESTS[1],
        authored_properties=(("value", {"items": [1, 2.0, None]}),),
        incoming_edges=(
            IncomingEdgeIdentity("source", "value", "input", 0, "direct"),
        ),
        hidden_ordering_pairs=(("setup", "pool"),),
        dependency_solution_keys=(_DIGESTS[2],),
        trigger_publication_generations=(("trigger", 4),),
        input_provenance_digest=_DIGESTS[3],
        execution_policy_digest=_DIGESTS[4],
        implementation_digest=_DIGESTS[5],
        catalog_revision_digest=_DIGESTS[6],
        execution_environment_digest=_DIGESTS[7],
    )


def test_canonical_tagging_preserves_types_order_and_float_policy() -> None:
    first = {
        "map": {"b": 2, "a": 1},
        "set": {"beta", "alpha"},
        "tree": DataTree((((2,), ("second",)), ((0,), ("first",)))),
    }
    second = {
        "tree": DataTree((((0,), ("first",)), ((2,), ("second",)))),
        "set": {"alpha", "beta"},
        "map": {"a": 1, "b": 2},
    }

    assert canonical_digest(first) == canonical_digest(second)
    assert canonical_digest([1]) != canonical_digest((1,))
    assert canonical_digest(1) != canonical_digest(1.0)
    assert canonical_digest(0.0) != canonical_digest(-0.0)
    assert canonical_digest(float("nan")) == canonical_digest(float("nan"))
    assert canonical_digest(float("inf")) != canonical_digest(float("-inf"))
    assert canonical_digest(DataTree.from_list([1, 2])) != canonical_digest(
        DataTree.from_list([2, 1])
    )


def test_data_tree_branches_count_toward_canonical_item_limit(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(solution_identity_module, "MAX_CANONICAL_ITEMS", 3)

    with pytest.raises(SolutionIdentityError) as error:
        canonical_digest(DataTree((((0,), ()), ((1,), ()))))

    assert error.value.reason_code == "identity_item_limit_exceeded"


def test_data_tree_path_indexes_count_toward_canonical_item_limit(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(solution_identity_module, "MAX_CANONICAL_ITEMS", 2)

    with pytest.raises(SolutionIdentityError) as error:
        canonical_digest(DataTree((((0, 1), ()),)))

    assert error.value.reason_code == "identity_item_limit_exceeded"


def test_hostile_values_invoke_no_callbacks_or_filesystem_access() -> None:
    calls: list[str] = []

    class Hostile:
        def __repr__(self) -> str:
            calls.append("repr")
            return "hostile"

        def __iter__(self):
            calls.append("iter")
            return iter(())

        def __fspath__(self) -> str:
            calls.append("fspath")
            return "forbidden"

        def __getattribute__(self, name: str):
            if name not in {"__class__"}:
                calls.append("getattribute")
            return object.__getattribute__(self, name)

    class HostileDict(dict):
        def items(self):
            calls.append("items")
            return super().items()

    for value in (Hostile(), HostileDict(value=1), b"raw"):
        with pytest.raises(SolutionIdentityError):
            canonical_digest(value)
    assert calls == []


def test_solution_key_is_stable_across_hash_seeds_and_processes() -> None:
    script = (
        "from ea_node_editor.execution.solution_identity import "
        "NodeSolutionIdentity,solution_key;"
        "d='a'*64;"
        "i=NodeSolutionIdentity(solution_namespace_id='namespace',workspace_id='ws',"
        "node_id='node',node_type_id='data.select',node_interface_revision=1,"
        "node_interface_digest=d,node_contract_digest=d,"
        "authored_properties=(('value',{'set':{'gamma','alpha','beta'}}),),"
        "incoming_edges=(),hidden_ordering_pairs=(),dependency_solution_keys=(),"
        "trigger_publication_generations=(),input_provenance_digest=d,"
        "execution_policy_digest=d,implementation_digest=d,catalog_revision_digest=d,"
        "execution_environment_digest=d);"
        "print(solution_key(i))"
    )
    outputs = []
    for seed in ("1", "73", "random"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = seed
        outputs.append(
            subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                text=True,
            ).strip()
        )
    assert len(set(outputs)) == 1


def test_file_and_directory_provenance_are_bounded_and_content_based(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("alpha", encoding="utf-8")
    first = hash_file_provenance(source)
    assert first.sha256 == hashlib.sha256(b"alpha").hexdigest()
    assert first.size_bytes == 5

    source.write_text("bravo", encoding="utf-8")
    second = hash_file_provenance(source)
    assert second.sha256 != first.sha256
    assert provenance_digest(first, path_policy="project_relative") != provenance_digest(
        second,
        path_policy="project_relative",
    )
    assert provenance_digest(first, path_policy="project_relative") != provenance_digest(
        first,
        path_policy="absolute_content_only",
    )

    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "b.txt").write_text("b", encoding="utf-8")
    (tree / "a.txt").write_text("a", encoding="utf-8")
    tree_identity = hash_directory_provenance(tree)
    assert tree_identity.entry_count == 2
    assert tree_identity.total_bytes == 2

    with pytest.raises(SolutionIdentityError) as size_error:
        hash_file_provenance(
            source,
            policy=ProvenanceHashPolicy(max_single_file_bytes=4),
        )
    assert size_error.value.reason_code == "provenance_limit_exceeded"

    with pytest.raises(SolutionIdentityError) as entry_error:
        hash_directory_provenance(
            tree,
            policy=ProvenanceHashPolicy(max_directory_entries=1),
        )
    assert entry_error.value.reason_code == "provenance_limit_exceeded"

    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(SolutionIdentityError) as cancel_error:
        hash_file_provenance(source, cancel_event=cancelled)
    assert cancel_error.value.reason_code == "provenance_cancelled"


def test_directory_provenance_rejects_root_replacement_after_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "original.txt").write_text("original", encoding="utf-8")
    displaced = tmp_path / "displaced"
    real_scandir = solution_identity_module.os.scandir
    swapped = False

    class SwappingScandir:
        def __init__(self, path: str | Path) -> None:
            self.path = Path(path)
            self.iterator = None

        def __enter__(self):
            self.iterator = real_scandir(self.path)
            return self.iterator

        def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
            nonlocal swapped
            assert self.iterator is not None
            self.iterator.close()
            if self.path == tree and not swapped:
                tree.rename(displaced)
                tree.mkdir()
                (tree / "replacement.txt").write_text(
                    "replacement",
                    encoding="utf-8",
                )
                swapped = True

    monkeypatch.setattr(solution_identity_module.os, "scandir", SwappingScandir)

    with pytest.raises(SolutionIdentityError) as error:
        hash_directory_provenance(tree)

    assert swapped
    assert error.value.reason_code == "provenance_changed"


def test_directory_provenance_rejects_replace_scan_restore(
    tmp_path: Path,
    monkeypatch,
) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "kept.txt").write_text("kept", encoding="utf-8")
    (tree / "omitted.txt").write_text("omitted", encoding="utf-8")
    original = tmp_path / "original"
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "kept.txt").write_text("replacement", encoding="utf-8")
    real_scandir = solution_identity_module.os.scandir
    swapped = False

    class RestoringScandir:
        def __init__(self, path: str | Path) -> None:
            self.path = Path(path)
            self.iterator = None
            self.did_swap = False

        def __enter__(self):
            nonlocal swapped
            if self.path == tree and not swapped:
                tree.rename(original)
                replacement.rename(tree)
                swapped = True
                self.did_swap = True
            self.iterator = real_scandir(self.path)
            return self.iterator

        def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
            assert self.iterator is not None
            self.iterator.close()
            if self.did_swap:
                tree.rename(replacement)
                original.rename(tree)

    monkeypatch.setattr(solution_identity_module.os, "scandir", RestoringScandir)

    with pytest.raises(SolutionIdentityError) as error:
        hash_directory_provenance(tree)

    assert swapped
    assert (tree / "kept.txt").is_file()
    assert (tree / "omitted.txt").is_file()
    assert error.value.reason_code == "provenance_changed"


def test_directory_entry_limit_counts_recursive_entries_and_later_siblings(
    tmp_path: Path,
) -> None:
    tree = tmp_path / "tree"
    nested = tree / "d1"
    nested.mkdir(parents=True)
    (nested / "nested.txt").write_text("nested", encoding="utf-8")
    (tree / "tail.txt").write_text("tail", encoding="utf-8")

    with pytest.raises(SolutionIdentityError) as error:
        hash_directory_provenance(
            tree,
            policy=ProvenanceHashPolicy(max_directory_entries=2),
        )
    accepted = hash_directory_provenance(
        tree,
        policy=ProvenanceHashPolicy(max_directory_entries=3),
    )

    assert error.value.reason_code == "provenance_limit_exceeded"
    assert accepted.entry_count == 3


def test_corex_build_and_function_identity_are_content_based(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    (source_root / "corex").mkdir(parents=True)
    (source_root / "ea_node_editor").mkdir()
    build_file = source_root / "corex" / "__init__.py"
    build_file.write_text("VERSION = 1\n", encoding="utf-8")
    (source_root / "ea_node_editor" / "__init__.py").write_text(
        "VERSION = 1\n", encoding="utf-8"
    )
    first_build = corex_build_digest(source_root=source_root)
    build_file.write_text("VERSION = 2\n", encoding="utf-8")
    second_build = corex_build_digest(source_root=source_root)
    assert second_build != first_build

    registry = build_builtin_registry(generation_root=tmp_path / "generations")
    bool_catalog = catalog_revision_digest(
        registry.data_types,
        type_ids=("COREX.DataTypes.Bool",),
    )
    used_catalog = catalog_revision_digest(
        registry.data_types,
        type_ids=("COREX.DataTypes.String", "COREX.DataTypes.Bool"),
    )
    assert used_catalog == catalog_revision_digest(
        registry.data_types,
        type_ids=("COREX.DataTypes.Bool", "COREX.DataTypes.String"),
    )
    assert bool_catalog != used_catalog
    with pytest.raises(SolutionIdentityError) as catalog_error:
        catalog_revision_digest(
            registry.data_types,
            type_ids=("COREX.DataTypes.Missing",),
        )
    assert catalog_error.value.reason_code == "catalog_identity_missing"

    first_implementation = implementation_digest(
        registry,
        "data.boolean_toggle",
        build_digest=first_build,
    )
    assert first_implementation == implementation_digest(
        registry,
        "data.boolean_toggle",
        build_digest=first_build,
    )
    assert first_implementation != implementation_digest(
        registry,
        "data.boolean_toggle",
        build_digest=second_build,
    )
    with pytest.raises(SolutionIdentityError) as trusted_error:
        implementation_digest(
            registry,
            "core.trigger",
            build_digest=first_build,
        )
    assert trusted_error.value.reason_code == "implementation_identity_unavailable"


def test_default_corex_build_digest_uses_frozen_executable_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executable = tmp_path / "COREX_Node_Editor.exe"
    executable.write_bytes(b"frozen-corex-build")
    monkeypatch.setattr(solution_identity_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(solution_identity_module.sys, "executable", str(executable))

    digest = corex_build_digest()

    assert len(digest) == 64
    assert digest == corex_build_digest()


def test_corex_build_lookup_failures_use_one_safe_reason(
    tmp_path: Path,
    monkeypatch,
) -> None:
    missing = tmp_path / "missing.exe"
    monkeypatch.setattr(solution_identity_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(solution_identity_module.sys, "executable", str(missing))

    with pytest.raises(SolutionIdentityError) as frozen_error:
        corex_build_digest()
    with pytest.raises(SolutionIdentityError) as source_error:
        corex_build_digest(source_root=tmp_path / "missing-source")

    assert frozen_error.value.reason_code == "corex_build_identity_unavailable"
    assert source_error.value.reason_code == "corex_build_identity_unavailable"


def test_environment_and_solution_keys_bind_every_execution_identity() -> None:
    policy_digest = execution_policy_digest(policy_facts={"result_mode": "strict"})
    environment = ExecutionEnvironmentIdentity(
        backend="process",
        isolation_mode="managed",
        interpreter_build="cpython-3.11.6",
        platform="windows-amd64",
        packages=(("numpy", "2.1.0"), ("corex", "0.1.0")),
        addons=(("tabular", "1", _DIGESTS[0]),),
        toolchains=(("renderer", "1", _DIGESTS[1]),),
        execution_policy_digest=policy_digest,
    )
    reordered = replace(
        environment,
        packages=tuple(reversed(environment.packages)),
    )
    changed = replace(environment, backend="trusted")
    assert reordered.digest == environment.digest
    assert changed.digest != environment.digest

    baseline = _identity()
    baseline_key = solution_key(baseline)
    changes = (
        replace(baseline, authored_properties=(("value", 2),)),
        replace(
            baseline,
            incoming_edges=(
                replace(baseline.incoming_edges[0], input_order=1),
            ),
        ),
        replace(baseline, input_provenance_digest=_DIGESTS[8]),
        replace(baseline, implementation_digest=_DIGESTS[8]),
        replace(baseline, catalog_revision_digest=_DIGESTS[8]),
        replace(baseline, execution_environment_digest=_DIGESTS[8]),
        replace(baseline, node_interface_digest=_DIGESTS[8]),
    )
    assert all(solution_key(candidate) != baseline_key for candidate in changes)
