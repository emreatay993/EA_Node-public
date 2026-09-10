# Purpose: Define private public-function references, bundles, and execution adapter.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_function_plugin.py

from __future__ import annotations

import hashlib
import inspect
import json
import keyword
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from corex import _Settings
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.runtime_contracts.scientific_values import (
    materialize_script_values, snapshot_scientific_values,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
INTERNAL_BUILTIN_FUNCTION_OWNER_ID = "corex:builtin:functions"
EMPTY_PLUGIN_FINGERPRINT = hashlib.sha256(
    b'{"bundles":[],"entries":[]}'
).hexdigest()


def _trimmed(field_name: str, value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if value != value.strip():
        raise ValueError(f"{field_name} must be trimmed")
    if not value and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    return value


def _digest(field_name: str, value: object) -> str:
    normalized = _trimmed(field_name, value)
    if _SHA256.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return normalized


@dataclass(slots=True, frozen=True)
class PythonFunctionRef:
    bundle_id: str
    bundle_digest: str
    module_relative_path: str
    function_name: str
    source_digest: str
    is_async: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle_id", _trimmed("bundle_id", self.bundle_id))
        object.__setattr__(
            self,
            "bundle_digest",
            _digest("bundle_digest", self.bundle_digest),
        )
        module_path = _trimmed("module_relative_path", self.module_relative_path)
        parsed_path = PurePosixPath(module_path)
        windows_path = PureWindowsPath(module_path)
        if (
            "\\" in module_path
            or ":" in module_path
            or parsed_path.is_absolute()
            or windows_path.drive
            or windows_path.root
            or parsed_path.as_posix() != module_path
            or any(part in {"", ".", ".."} for part in parsed_path.parts)
            or parsed_path.suffix != ".py"
        ):
            raise ValueError("module_relative_path must be a canonical relative .py path")
        object.__setattr__(self, "module_relative_path", module_path)
        function_name = _trimmed("function_name", self.function_name)
        if not function_name.isidentifier() or keyword.iskeyword(function_name):
            raise ValueError("function_name must be a valid Python identifier")
        object.__setattr__(self, "function_name", function_name)
        object.__setattr__(
            self,
            "source_digest",
            _digest("source_digest", self.source_digest),
        )
        if not isinstance(self.is_async, bool):
            raise TypeError("is_async must be a bool")


@dataclass(slots=True, frozen=True)
class PluginBundleRef:
    owner_id: str
    version: str
    generation_id: str
    bundle_digest: str
    approved_generation_root: str
    functions: tuple[PythonFunctionRef, ...]
    unavailable_reason: str = ""

    def __post_init__(self) -> None:
        owner_id = _trimmed("owner_id", self.owner_id)
        object.__setattr__(self, "owner_id", owner_id)
        object.__setattr__(
            self,
            "version",
            _trimmed("version", self.version, allow_empty=True),
        )
        object.__setattr__(
            self,
            "generation_id",
            _trimmed("generation_id", self.generation_id),
        )
        bundle_digest = _digest("bundle_digest", self.bundle_digest)
        object.__setattr__(self, "bundle_digest", bundle_digest)
        object.__setattr__(
            self,
            "approved_generation_root",
            _trimmed("approved_generation_root", self.approved_generation_root),
        )
        if not isinstance(self.functions, tuple) or not all(
            isinstance(item, PythonFunctionRef) for item in self.functions
        ):
            raise TypeError("functions must be a tuple of PythonFunctionRef values")
        identities = [
            (item.module_relative_path.casefold(), item.function_name)
            for item in self.functions
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("functions must not contain duplicate module/function pairs")
        for function in self.functions:
            if function.bundle_id != owner_id:
                raise ValueError("function bundle_id must match bundle owner_id")
            if function.bundle_digest != bundle_digest:
                raise ValueError("function bundle_digest must match bundle_digest")
        object.__setattr__(
            self,
            "unavailable_reason",
            _trimmed(
                "unavailable_reason",
                self.unavailable_reason,
                allow_empty=True,
            ),
        )


def _stable_fingerprint_value(value: object, *, approved_callbacks: tuple = ()) -> object:
    if callable(value) and value in approved_callbacks:
        return {"__callable__": f"{value.__module__}:{value.__qualname__}"}
    if is_dataclass(value):
        return {
            field.name: _stable_fingerprint_value(getattr(value, field.name), approved_callbacks=approved_callbacks)
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _stable_fingerprint_value(item, approved_callbacks=approved_callbacks)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_stable_fingerprint_value(item, approved_callbacks=approved_callbacks) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_stable_fingerprint_value(item, approved_callbacks=approved_callbacks) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, Enum):
        return _stable_fingerprint_value(value.value)
    if isinstance(value, Path):
        return value.as_posix()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(
        f"Unsupported plugin fingerprint value: {type(value).__qualname__}"
    )


def plugin_fingerprint(
    entries: Sequence[tuple[NodeTypeSpec, PythonFunctionRef]],
    bundles: Sequence[PluginBundleRef],
) -> str:
    from .builtins.engineering_viewer import next_scene_input_id, resolve_scene_input_ports

    included_owners = {bundle.owner_id for bundle in bundles}
    entry_payload = [
        {
            "spec": _stable_fingerprint_value(
                spec,
                approved_callbacks=(resolve_scene_input_ports, next_scene_input_id)
                if function_ref.bundle_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID and spec.type_id == "model.viewer"
                else (),
            ),
            "function": _stable_fingerprint_value(function_ref),
        }
        for spec, function_ref in sorted(entries, key=lambda item: item[0].type_id)
        if function_ref.bundle_id in included_owners
    ]
    bundle_payload = [
        {
            "owner_id": bundle.owner_id,
            "version": bundle.version,
            "generation_id": bundle.generation_id,
            "bundle_digest": bundle.bundle_digest,
            "functions": _stable_fingerprint_value(bundle.functions),
            "unavailable_reason": bundle.unavailable_reason,
        }
        for bundle in sorted(bundles, key=lambda item: item.owner_id)
    ]
    payload = json.dumps(
        {"bundles": bundle_payload, "entries": entry_payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class PythonFunctionAdapter:
    __slots__ = (
        "_control_keys",
        "_function",
        "_input_keys",
        "_output_keys",
        "_override_keys",
        "_native_inputs",
        "_spec",
    )

    def __init__(self, spec: NodeTypeSpec, function: Callable[..., object], *, native_inputs: bool = True) -> None:
        if not isinstance(spec, NodeTypeSpec):
            raise TypeError("spec must be a NodeTypeSpec")
        if not callable(function):
            raise TypeError("function must be callable")
        if inspect.iscoroutinefunction(function) != spec.is_async:
            raise TypeError("function async state must match NodeTypeSpec.is_async")
        self._spec = spec
        self._native_inputs = native_inputs
        self._function = function
        self._control_keys = tuple(prop.key for prop in spec.properties)
        self._override_keys = frozenset(
            port.key
            for port in spec.ports
            if port.direction == "in" and port.uses_property_default
        )
        self._input_keys = tuple(
            port.key
            for port in spec.ports
            if port.direction == "in" and port.key not in self._override_keys
        )
        self._output_keys = frozenset(
            port.key for port in spec.ports if port.direction == "out"
        )

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def _arguments(self, ctx: ExecutionContext) -> tuple[object, ...]:
        arguments: list[object] = [ctx]
        arguments.extend(ctx.inputs.get(key) for key in self._input_keys)
        if self._control_keys:
            values = {
                key: (
                    ctx.inputs[key]
                    if key in self._override_keys and key in ctx.inputs
                    else ctx.properties.get(key)
                )
                for key in self._control_keys
            }
            arguments.append(_Settings(values))
        return tuple(arguments)

    def _result(
        self,
        value: object,
        ctx: ExecutionContext,
        warning_cursor: int,
    ) -> NodeResult:
        if not isinstance(value, Mapping):
            raise TypeError("Public node functions must return a mapping")
        outputs = dict(value)
        if any(not isinstance(key, str) for key in outputs):
            raise TypeError("Public node function output keys must be strings")
        unknown = sorted(set(outputs) - self._output_keys)
        if unknown:
            raise ValueError(
                "Public node function returned undeclared output key(s): "
                + ", ".join(unknown)
            )
        plugin_warnings = ctx._plugin_warnings_since(warning_cursor)
        return NodeResult(
            outputs=snapshot_scientific_values(outputs),
            warnings=tuple(warning.message for warning in plugin_warnings),
            plugin_warnings=plugin_warnings,
        )

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        if self._spec.is_async:
            raise TypeError("Async public node functions require async_execute")
        warning_cursor = ctx._plugin_warning_cursor()
        if self._native_inputs:
            ctx = replace(ctx, inputs=materialize_script_values(ctx.inputs))
        value = self._function(*self._arguments(ctx))
        if inspect.isawaitable(value):
            close = getattr(value, "close", None)
            if callable(close):
                close()
            raise TypeError("Synchronous public node functions must not return awaitables")
        return self._result(value, ctx, warning_cursor)

    async def async_execute(self, ctx: ExecutionContext) -> NodeResult:
        if not self._spec.is_async:
            return self.execute(ctx)
        warning_cursor = ctx._plugin_warning_cursor()
        if self._native_inputs:
            ctx = replace(ctx, inputs=materialize_script_values(ctx.inputs))
        value = self._function(*self._arguments(ctx))
        if not inspect.isawaitable(value):
            raise TypeError("Async public node functions must return an awaitable")
        return self._result(await value, ctx, warning_cursor)


__all__ = [
    "EMPTY_PLUGIN_FINGERPRINT",
    "INTERNAL_BUILTIN_FUNCTION_OWNER_ID",
    "PluginBundleRef",
    "PythonFunctionAdapter",
    "PythonFunctionRef",
    "plugin_fingerprint",
]
