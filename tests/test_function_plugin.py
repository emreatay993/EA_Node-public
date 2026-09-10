from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from pathlib import PurePosixPath

import pytest

from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.function_plugin import (
    PluginBundleRef,
    PythonFunctionAdapter,
    PythonFunctionRef,
)
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.nodes.plugin_contracts import PluginDescriptor
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.registry import (
    NodeRegistry,
    PythonFunctionEntry,
    TrustedFactoryEntry,
)
from ea_node_editor.runtime_contracts import GRAPH_DATA_TYPE_ID

_DIGEST = "a" * 64
_SOURCE_DIGEST = "b" * 64


def _function_ref(*, is_async: bool = False) -> PythonFunctionRef:
    return PythonFunctionRef(
        bundle_id="custom.bundle",
        bundle_digest=_DIGEST,
        module_relative_path="nodes.py",
        function_name="scale",
        source_digest=_SOURCE_DIGEST,
        is_async=is_async,
    )


def _context(
    *,
    inputs: dict[str, object] | None = None,
    properties: dict[str, object] | None = None,
    iteration: int = 0,
    emitted: list[tuple[str, str]] | None = None,
) -> ExecutionContext:
    logs = emitted if emitted is not None else []
    return ExecutionContext(
        run_id="run-1",
        node_id="node-1",
        workspace_id="workspace-1",
        inputs=dict(inputs or {}),
        properties=dict(properties or {}),
        emit_log=lambda level, message: logs.append((level, message)),
        target_path=(2, iteration),
        target_iteration=iteration,
        iteration_count=2,
    )


def _function_spec(*, is_async: bool = False) -> NodeTypeSpec:
    return NodeTypeSpec(
        type_id="custom.adapter.1234abcd",
        display_name="Adapter",
        category_path=("Tests",),
        icon="",
        ports=(
            PortSpec("value", "in", "data", GRAPH_DATA_TYPE_ID, required=True),
            PortSpec("optional", "in", "data", GRAPH_DATA_TYPE_ID, required=False),
            PortSpec(
                "override",
                "in",
                "data",
                GRAPH_DATA_TYPE_ID,
                required=False,
                uses_property_default=True,
            ),
            PortSpec("result", "out", "data", GRAPH_DATA_TYPE_ID),
            PortSpec("explicit_none", "out", "data", GRAPH_DATA_TYPE_ID),
            PortSpec("omitted", "out", "data", GRAPH_DATA_TYPE_ID),
        ),
        properties=(
            PropertySpec("override", "json", "saved", "Override"),
            PropertySpec("local", "json", {"items": [1, 2]}, "Local"),
        ),
        is_async=is_async,
    )


def test_function_refs_and_bundle_refs_are_immutable_and_validated() -> None:
    function_ref = _function_ref()
    bundle = PluginBundleRef(
        owner_id="custom.bundle",
        version="1.0.0",
        generation_id="generation-1",
        bundle_digest=_DIGEST,
        approved_generation_root="C:/corex/runtime/plugin_generations/abc",
        functions=(function_ref,),
    )

    assert bundle.functions == (function_ref,)
    with pytest.raises(FrozenInstanceError):
        function_ref.function_name = "other"
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        PythonFunctionRef(
            "custom.bundle",
            "A" * 64,
            "nodes.py",
            "scale",
            _SOURCE_DIGEST,
        )
    for invalid_path in (
        "../nodes.py",
        "/outside.py",
        "C:/outside.py",
        "C:outside.py",
        "nodes.py:stream",
        "//server/share/nodes.py",
        ".\\nodes.py",
    ):
        with pytest.raises(ValueError, match="canonical relative"):
            PythonFunctionRef(
                "custom.bundle",
                _DIGEST,
                invalid_path,
                "scale",
                _SOURCE_DIGEST,
            )
    with pytest.raises(ValueError, match="must match bundle owner_id"):
        PluginBundleRef(
            owner_id="other.bundle",
            version="",
            generation_id="generation-1",
            bundle_digest=_DIGEST,
            approved_generation_root="C:/generation",
            functions=(function_ref,),
        )


def test_registry_keeps_trusted_factories_and_function_refs_mutually_exclusive() -> None:
    function_spec = _function_spec()
    function_ref = _function_ref()
    trusted_spec = NodeTypeSpec(
        type_id="tests.trusted",
        display_name="Trusted",
        category_path=("Tests",),
        icon="",
        ports=(),
        properties=(),
    )

    class TrustedPlugin:
        def spec(self) -> NodeTypeSpec:
            return trusted_spec

        def execute(self, _ctx: ExecutionContext) -> NodeResult:
            return NodeResult()

    registry = NodeRegistry()
    registry.register_descriptor(
        PluginDescriptor(spec=trusted_spec, factory=TrustedPlugin)
    )
    registry.register_python_function(
        function_spec,
        function_ref,
        owner_id="custom.bundle",
    )

    trusted_entry = registry.get_entry("tests.trusted")
    function_entry = registry.get_entry(function_spec.type_id)
    assert isinstance(trusted_entry, TrustedFactoryEntry)
    assert isinstance(function_entry, PythonFunctionEntry)
    assert function_entry.owner_id == "custom.bundle"
    assert not hasattr(function_entry, "factory")
    assert not hasattr(function_ref, "function")
    assert registry.create("tests.trusted").spec() == trusted_spec
    with pytest.raises(RuntimeError, match="worker resolution"):
        registry.create(function_spec.type_id)
    assert registry.descriptor_or_none(function_spec.type_id) is None
    with pytest.raises(TypeError, match="trusted descriptor"):
        registry.get_descriptor(function_spec.type_id)
    assert registry.python_function_ref_or_none(function_spec.type_id) == function_ref
    assert registry.all_python_function_refs() == (function_ref,)
    assert [item.spec.type_id for item in registry.all_descriptors()] == [
        "tests.trusted"
    ]
    assert {spec.type_id for spec in registry.all_specs()} == {
        "tests.trusted",
        function_spec.type_id,
    }
    with pytest.raises(ValueError, match="already registered"):
        registry.register_python_function(function_spec, function_ref)


def test_registry_rejects_async_ref_and_spec_mismatch() -> None:
    registry = NodeRegistry()
    with pytest.raises(ValueError, match="async state"):
        registry.register_python_function(_function_spec(), _function_ref(is_async=True))
    with pytest.raises(ValueError, match="owner_id"):
        registry.register_python_function(
            _function_spec(),
            _function_ref(),
            owner_id="other.bundle",
        )


@pytest.mark.parametrize("override", (None, False, 0, "", [], {}))
def test_adapter_binds_inputs_controls_falsey_overrides_outputs_and_warnings(
    override: object,
) -> None:
    captured: dict[str, object] = {}

    def function(ctx, value, optional, settings):
        captured.update(
            value=value,
            optional=optional,
            settings=settings.to_dict(),
        )
        ctx.warn("First warning", code="first_warning")
        ctx.warn("Second warning")
        return {
            "result": settings.to_dict()["override"],
            "explicit_none": None,
        }

    emitted: list[tuple[str, str]] = []
    ctx = _context(
        inputs={"value": 3, "override": override},
        properties={"override": "saved", "local": {"items": [1, 2]}},
        emitted=emitted,
    )
    result = PythonFunctionAdapter(_function_spec(), function).execute(ctx)

    assert captured == {
        "value": 3,
        "optional": None,
        "settings": {"override": override, "local": {"items": [1, 2]}},
    }
    assert result.outputs == {"result": override, "explicit_none": None}
    assert "omitted" not in result.outputs
    assert result.warnings == ("First warning", "Second warning")
    assert [warning.code for warning in result.plugin_warnings] == [
        "first_warning",
        "plugin_warning",
    ]
    assert [warning.message for warning in result.plugin_warnings] == [
        "First warning",
        "Second warning",
    ]
    assert result.plugin_warnings[0].run_id == "run-1"
    assert result.plugin_warnings[0].node_id == "node-1"
    assert result.plugin_warnings[0].path == (2, 0)
    assert result.plugin_warnings[0].iteration == 0
    assert emitted == []


def test_disconnected_override_uses_saved_property_value() -> None:
    def function(_ctx, _value, _optional, settings):
        return {"result": settings.override}

    result = PythonFunctionAdapter(_function_spec(), function).execute(
        _context(
            inputs={"value": 1},
            properties={"override": "saved", "local": {}},
        )
    )
    assert result.outputs == {"result": "saved"}


@pytest.mark.parametrize(
    ("returned", "message"),
    (
        (None, "return a mapping"),
        (NodeResult(), "return a mapping"),
        ({1: "value"}, "keys must be strings"),
        ({"unknown": 1}, "undeclared output"),
    ),
)
def test_adapter_rejects_invalid_public_returns(returned: object, message: str) -> None:
    def function(_ctx, _value, _optional, _settings):
        return returned

    adapter = PythonFunctionAdapter(_function_spec(), function)
    with pytest.raises((TypeError, ValueError), match=message):
        adapter.execute(
            _context(
                inputs={"value": 1},
                properties={"override": "saved", "local": {}},
            )
        )


def test_async_adapter_awaits_function_and_preserves_warning_order() -> None:
    async def function(ctx, value, optional, settings):
        await asyncio.sleep(0)
        ctx.warn(f"iteration-{ctx.target_iteration}", code="iteration")
        return {"result": (value, optional, settings.override)}

    adapter = PythonFunctionAdapter(_function_spec(is_async=True), function)
    ordered_warnings: list[str] = []
    for iteration in (0, 1):
        result = asyncio.run(
            adapter.async_execute(
                _context(
                    inputs={"value": iteration},
                    properties={"override": "saved", "local": {}},
                    iteration=iteration,
                )
            )
        )
        ordered_warnings.extend(result.warnings)
        assert result.plugin_warnings[0].iteration == iteration

    assert ordered_warnings == ["iteration-0", "iteration-1"]
    with pytest.raises(TypeError, match="async state"):
        PythonFunctionAdapter(_function_spec(is_async=True), lambda: {})


@pytest.mark.parametrize(
    ("message", "code", "error"),
    (
        ("", "plugin_warning", "must not be empty"),
        (" ", "plugin_warning", "must not be empty"),
        ("x" * 2049, "plugin_warning", "at most 2048"),
        ("message", "Upper", "must match"),
        ("message", "1code", "must match"),
        ("message", "a" * 65, "at most 64"),
    ),
)
def test_ctx_warn_validates_message_and_code(
    message: str,
    code: str,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        _context().warn(message, code=code)


def test_plugin_parser_spec_can_feed_private_registry_without_a_callable() -> None:
    source = '''
import corex
@corex.node(id="custom.scale.1234abcd", name="Scale", category=("Math",))
@corex.input("value", value_type=float)
@corex.output("scaled", value_type=float)
@corex.number("factor", default=2.0)
def scale(ctx, value, settings): return {"scaled": value * settings.factor}
'''
    (declaration,) = discover_plugin_declarations(source, filename="nodes.py")
    registry = NodeRegistry()
    registry.register_python_function(declaration.spec, _function_ref())

    assert registry.spec_or_none(declaration.spec.type_id) == declaration.spec
    assert registry.descriptor_or_none(declaration.spec.type_id) is None
    assert PurePosixPath(
        registry.python_function_ref_or_none(declaration.spec.type_id).module_relative_path
    ) == PurePosixPath("nodes.py")
