from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.run_messages import (
    StartRunCommand,
)
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
    runtime_registry_fingerprint,
)
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.core_values import COLOR_DATA_TYPE_ID
from ea_node_editor.nodes.core_data_types import DOUBLE_DATA_TYPE_ID
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.registry import PythonFunctionEntry
from ea_node_editor.runtime_contracts import DataTree, TypedInlineValue
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog


DECONSTRUCT_COLOR_TYPE_ID = "data.deconstruct_color"
_TYPE_IDS = ("core.constant", "core.if", DECONSTRUCT_COLOR_TYPE_ID)


def _context(*, inputs: dict[str, object]) -> ExecutionContext:
    return ExecutionContext(
        run_id="core-value-run",
        node_id="core-value-node",
        workspace_id="core-value-workspace",
        inputs=inputs,
        properties={},
        emit_log=lambda _level, _message: None,
    )


def _adapter(tmp_path: Path, type_id: str):  # noqa: ANN202
    registry = build_builtin_registry(generation_root=tmp_path / "generations")
    catalog_fingerprint, revisions = catalog_agreement(registry.data_types)
    plugin_digest = registry.plugin_fingerprint()
    command = StartRunCommand(
        run_id="core-value-run",
        workspace_id="core-value-workspace",
        catalog_fingerprint=catalog_fingerprint,
        catalog_revisions=revisions,
        plugin_bundles=registry.plugin_bundle_refs(),
        plugin_fingerprint=plugin_digest,
        runtime_registry_fingerprint=runtime_registry_fingerprint(
            catalog_fingerprint,
            plugin_digest,
        ),
        registry_contract_fingerprint=registry.contract_fingerprint(),
    )
    runtime = WorkerPluginRuntime()
    prepared = runtime.prepare_registry(command, registry)
    entry = prepared.entry_or_none(type_id)
    assert isinstance(entry, PythonFunctionEntry)
    return runtime, runtime.create_adapter(entry.function_ref, entry.spec)


def test_converted_entries_match_pre_cutover_specs_without_descriptors(
    tmp_path: Path,
) -> None:
    expected = {
        row["spec"]["type_id"]: row["spec"]
        for row in load_current_repo_owned_catalog()
        if row["spec"]["type_id"] in _TYPE_IDS
    }
    registry = build_builtin_registry(generation_root=tmp_path / "generations")

    assert set(expected) == set(_TYPE_IDS)
    for type_id in _TYPE_IDS:
        assert isinstance(registry.entry_or_none(type_id), PythonFunctionEntry)
        assert registry.descriptor_or_none(type_id) is None
        actual = json.loads(json.dumps(asdict(registry.get_spec(type_id))))
        assert actual == expected[type_id]


def test_constant_serializes_only_finite_json(tmp_path: Path) -> None:
    runtime, adapter = _adapter(tmp_path, "core.constant")
    context = _context(inputs={})
    try:
        context.properties = {"value": {"value": 2.5}}
        assert adapter.execute(context).outputs == {
            "value": {"value": 2.5},
            "as_text": '{"value": 2.5}',
        }
        for non_finite in (float("nan"), float("inf"), float("-inf")):
            context.properties = {"value": {"value": non_finite}}
            with pytest.raises(ValueError, match="JSON serializable"):
                adapter.execute(context)
    finally:
        runtime.clear()


@pytest.mark.parametrize(
    ("inputs", "expected"),
    (
        (
            {
                "condition": True,
                "true_value": DataTree({(0,): (1, 2)}),
                "false_value": DataTree({(1,): (3,)}),
            },
            {"result": DataTree({(0,): (1, 2)})},
        ),
        (
            {"condition": False, "true_value": DataTree.from_item("unused")},
            {},
        ),
        (
            {
                "condition": None,
                "true_value": DataTree.from_item("unused"),
                "false_value": None,
            },
            {"result": None},
        ),
    ),
)
def test_if_worker_function_preserves_tree_and_optional_branch_behavior(
    tmp_path: Path,
    inputs: dict[str, object],
    expected: dict[str, object],
) -> None:
    runtime, adapter = _adapter(tmp_path, "core.if")
    try:
        assert adapter.execute(_context(inputs=inputs)).outputs == expected
    finally:
        runtime.clear()


def test_color_worker_function_preserves_channels_without_reinterpretation(
    tmp_path: Path,
) -> None:
    value = TypedInlineValue(
        COLOR_DATA_TYPE_ID,
        1,
        {
            "R": -0.25,
            "G": 0.125,
            "B": 1.25,
            "A": 0.75,
            "IsValid": False,
        },
    )
    runtime, adapter = _adapter(tmp_path, DECONSTRUCT_COLOR_TYPE_ID)
    try:
        assert adapter.execute(_context(inputs={"color": value})).outputs == {
            "red": -0.25,
            "green": 0.125,
            "blue": 1.25,
            "alpha": 0.75,
        }
    finally:
        runtime.clear()


@pytest.mark.parametrize(
    "value",
    (
        {"R": 0.0, "G": 0.0, "B": 0.0, "A": 1.0, "IsValid": True},
        TypedInlineValue(
            DOUBLE_DATA_TYPE_ID,
            1,
            {"R": 0.0, "G": 0.0, "B": 0.0, "A": 1.0, "IsValid": True},
        ),
        TypedInlineValue(
            COLOR_DATA_TYPE_ID,
            2,
            {"R": 0.0, "G": 0.0, "B": 0.0, "A": 1.0, "IsValid": True},
        ),
        TypedInlineValue(
            COLOR_DATA_TYPE_ID,
            1,
            {"R": 0.0, "G": 0.0, "B": "0", "A": 1.0, "IsValid": True},
        ),
    ),
    ids=("carrier", "type", "schema", "payload"),
)
def test_color_worker_function_rejects_invalid_typed_values(
    tmp_path: Path,
    value: object,
) -> None:
    runtime, adapter = _adapter(tmp_path, DECONSTRUCT_COLOR_TYPE_ID)
    try:
        with pytest.raises(ValueError, match="^Color input is invalid$"):
            adapter.execute(_context(inputs={"color": value}))
    finally:
        runtime.clear()
