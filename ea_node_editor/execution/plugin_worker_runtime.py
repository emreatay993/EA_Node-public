# Purpose: Verify and lazily execute public function plugins inside isolated workers.
# Map: subsystems/execution.md
# Tests: tests/test_plugin_worker_loading.py

from __future__ import annotations

import builtins
import hashlib
import importlib.machinery
import importlib.util
import inspect
import keyword
import sys
import threading
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any

from ea_node_editor.execution.run_messages import (
    StartRunCommand,
)
from ea_node_editor.execution.registry_agreement import (
    runtime_registry_fingerprint,
)
from ea_node_editor.nodes.function_plugin import (
    EMPTY_PLUGIN_FINGERPRINT,
    INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    PluginBundleRef,
    PythonFunctionAdapter,
    PythonFunctionRef,
)
from ea_node_editor.nodes.function_bundle import registry_plugin_fingerprint
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.nodes.plugin_contracts import PluginProvenance
from ea_node_editor.nodes.plugin_generation import (
    VerifiedPluginGeneration,
    read_verified_plugin_generation,
)
from ea_node_editor.nodes.package_schema import (
    ValidatedPackage,
    validate_package_manifest,
    validated_package_declarations,
)
from ea_node_editor.nodes.registry import NodeRegistry


class WorkerPluginRuntime:
    """Pin one registry generation and resolve its public functions on demand."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runtime_fingerprint = ""
        self._contract_fingerprint = ""
        self._registry: NodeRegistry | None = None
        self._bundles: dict[str, PluginBundleRef] = {}
        self._generations: dict[str, VerifiedPluginGeneration] = {}
        self._functions: dict[PythonFunctionRef, Any] = {}
        self._modules: dict[str, ModuleType] = {}

    def prepare_registry(
        self,
        command: StartRunCommand,
        trusted_registry: NodeRegistry,
    ) -> NodeRegistry:
        if not isinstance(command, StartRunCommand):
            raise TypeError("command must be a StartRunCommand")
        if not isinstance(trusted_registry, NodeRegistry):
            raise TypeError("trusted_registry must be a NodeRegistry")
        requested_plugin_fingerprint = command.plugin_fingerprint or (
            EMPTY_PLUGIN_FINGERPRINT if not command.plugin_bundles else ""
        )
        with self._lock:
            if self._runtime_fingerprint:
                if (
                    self._registry is None
                    or requested_plugin_fingerprint
                    != self._registry.plugin_fingerprint()
                    or command.plugin_bundles
                    != self._registry.plugin_bundle_refs()
                    or (
                        command.runtime_registry_fingerprint
                        and command.runtime_registry_fingerprint
                        != self._runtime_fingerprint
                    )
                    or command.registry_contract_fingerprint
                    != self._contract_fingerprint
                ):
                    raise ValueError(
                        "Worker plugin generation must be retired before registry replacement"
                    )
                return self._registry

            expected_trusted = tuple(
                self._bundle_attestation(bundle)
                for bundle in trusted_registry.plugin_bundle_refs()
                if bundle.owner_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID
                or trusted_registry.plugin_contract_manifest(bundle.owner_id)
                is not None
            )
            trusted_owner_ids = {
                bundle.owner_id
                for bundle in trusted_registry.plugin_bundle_refs()
                if bundle.owner_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID
                or trusted_registry.plugin_contract_manifest(bundle.owner_id)
                is not None
            }
            requested_trusted = tuple(
                self._bundle_attestation(bundle)
                for bundle in command.plugin_bundles
                if bundle.owner_id in trusted_owner_ids
            )
            if requested_trusted and requested_trusted != expected_trusted:
                raise ValueError(
                    "Trusted function generation is not attested"
                )

            candidate = (
                trusted_registry
                if not command.plugin_bundles
                and not trusted_registry.all_python_function_refs()
                else trusted_registry.trusted_runtime_copy()
            )
            generations: dict[str, VerifiedPluginGeneration] = {}
            for bundle in command.plugin_bundles:
                generation = read_verified_plugin_generation(bundle)
                package = ValidatedPackage(
                    validate_package_manifest(generation.manifest),
                    dict(generation.members),
                )
                declarations = validated_package_declarations(
                    package,
                    filename_prefix=bundle.owner_id,
                    owner_id=bundle.owner_id,
                    allow_internal_metadata=bundle.owner_id in trusted_owner_ids,
                )
                declaration_by_identity = {
                    (module_path, declaration.function_name): declaration
                    for module_path, declaration in declarations
                }
                ref_by_identity = {
                    (ref.module_relative_path, ref.function_name): ref
                    for ref in bundle.functions
                }
                if set(declaration_by_identity) != set(ref_by_identity):
                    raise ValueError(
                        "Plugin generation declarations do not match function references"
                    )
                for identity, declaration in declaration_by_identity.items():
                    function_ref = ref_by_identity[identity]
                    if declaration.is_async != function_ref.is_async:
                        raise ValueError("Plugin function async state changed")
                    trusted_solution_reuse = bool(
                        declaration.spec.solution_reuse_scope != "never"
                        and bundle.owner_id in trusted_owner_ids
                    )
                    register_function = (
                        candidate._register_trusted_python_function  # noqa: SLF001
                        if trusted_solution_reuse
                        else candidate.register_python_function
                    )
                    provenance = None
                    if (
                        trusted_solution_reuse
                        and bundle.owner_id
                        == "ea_node_editor.builtins.tabular_data"
                    ):
                        package_root = Path(bundle.approved_generation_root)
                        provenance = PluginProvenance(
                            kind="package",
                            source_path=(
                                package_root / function_ref.module_relative_path
                            ),
                            package_root=package_root,
                            package_name="ea_node_editor_builtins_tabular_data",
                        )
                    register_function(
                        declaration.spec,
                        function_ref,
                        provenance=provenance,
                        owner_id=bundle.owner_id,
                        unavailable_reason=bundle.unavailable_reason,
                    )
                generations[bundle.bundle_digest] = generation

            computed_plugin_fingerprint = registry_plugin_fingerprint(
                candidate,
                command.plugin_bundles,
            )
            if requested_plugin_fingerprint != computed_plugin_fingerprint:
                raise ValueError(
                    "Public plugin fingerprint does not match verified declarations"
                )
            candidate.set_python_plugin_catalog(
                command.plugin_bundles,
                plugin_fingerprint=computed_plugin_fingerprint,
            )
            candidate.freeze()
            expected_runtime_fingerprint = runtime_registry_fingerprint(
                candidate.data_types.fingerprint(),
                computed_plugin_fingerprint,
            )
            requested_runtime_fingerprint = (
                command.runtime_registry_fingerprint
                or (expected_runtime_fingerprint if not command.plugin_bundles else "")
            )
            if requested_runtime_fingerprint != expected_runtime_fingerprint:
                raise ValueError(
                    "Public plugin registry does not match the requested generation"
                )
            if (
                command.catalog_fingerprint
                and command.catalog_fingerprint != candidate.data_types.fingerprint()
            ):
                raise ValueError(
                    "Public plugin registry uses a different data-type catalog"
                )
            expected_contract_fingerprint = candidate.contract_fingerprint()
            if command.registry_contract_fingerprint != expected_contract_fingerprint:
                raise ValueError(
                    "Worker registry contract does not match the requested generation"
                )
            self._runtime_fingerprint = expected_runtime_fingerprint
            self._contract_fingerprint = expected_contract_fingerprint
            self._registry = candidate
            self._bundles = {
                bundle.owner_id: bundle for bundle in command.plugin_bundles
            }
            self._generations = generations
            return candidate

    @staticmethod
    def _bundle_attestation(bundle: PluginBundleRef) -> tuple[object, ...]:
        return (
            bundle.owner_id,
            bundle.version,
            bundle.generation_id,
            bundle.bundle_digest,
            bundle.functions,
            bundle.unavailable_reason,
        )

    def create_adapter(
        self,
        function_ref: PythonFunctionRef,
        spec: NodeTypeSpec,
        *,
        unavailable_reason: str = "",
    ) -> PythonFunctionAdapter:
        if not isinstance(function_ref, PythonFunctionRef):
            raise TypeError("function_ref must be a PythonFunctionRef")
        if not isinstance(spec, NodeTypeSpec):
            raise TypeError("spec must be a NodeTypeSpec")
        with self._lock:
            if not self._runtime_fingerprint:
                raise RuntimeError("Worker plugin runtime is not bound")
            bundle = self._bundles.get(function_ref.bundle_id)
            if bundle is None or function_ref not in bundle.functions:
                raise RuntimeError("Public function reference is not in the active generation")
            reason = str(unavailable_reason or bundle.unavailable_reason).strip()
            if reason:
                raise RuntimeError(reason)
            function = self._functions.get(function_ref)
            if function is None:
                generation = self._generations.get(bundle.bundle_digest)
                if generation is None:
                    raise RuntimeError("Public plugin generation is not prepared")
                module = self._load_module(
                    bundle,
                    function_ref.module_relative_path,
                    generation.members,
                )
                function = getattr(module, function_ref.function_name, None)
                if not callable(function):
                    raise RuntimeError("Public plugin function is unavailable")
                if inspect.iscoroutinefunction(function) != function_ref.is_async:
                    raise RuntimeError("Public plugin function async state changed")
                self._functions[function_ref] = function
            return PythonFunctionAdapter(
                spec, function,
                native_inputs=function_ref.bundle_id != INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
            )

    def clear(self) -> None:
        with self._lock:
            for name, module in reversed(tuple(self._modules.items())):
                if sys.modules.get(name) is module:
                    del sys.modules[name]
            self._modules.clear()
            self._functions.clear()
            self._generations.clear()
            self._bundles.clear()
            self._registry = None
            self._runtime_fingerprint = ""
            self._contract_fingerprint = ""

    @staticmethod
    def _package_name(bundle_digest: str) -> str:
        return f"_corex_plugin_{bundle_digest}"

    @classmethod
    def _module_name(cls, bundle_digest: str, relative_path: str) -> str:
        stem = PurePosixPath(relative_path).stem
        if not stem.isidentifier() or keyword.iskeyword(stem):
            stem = "module_" + hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
        return f"{cls._package_name(bundle_digest)}.{stem}"

    @staticmethod
    def _source_paths(members: Mapping[str, bytes]) -> dict[str, str]:
        return {
            PurePosixPath(path).stem: path
            for path in members
            if PurePosixPath(path).suffix == ".py"
            and PurePosixPath(path).stem.isidentifier()
            and not keyword.iskeyword(PurePosixPath(path).stem)
        }

    def _ensure_package(self, bundle_digest: str) -> ModuleType:
        package_name = self._package_name(bundle_digest)
        existing = self._modules.get(package_name)
        if existing is not None:
            return existing
        if package_name in sys.modules:
            raise RuntimeError("Public plugin module namespace is already active")
        package = ModuleType(package_name)
        package.__file__ = f"<corex-plugin:{bundle_digest}:package>"
        package.__package__ = package_name
        package.__path__ = []  # type: ignore[attr-defined]
        package.__spec__ = importlib.machinery.ModuleSpec(
            package_name,
            loader=None,
            is_package=True,
        )
        sys.modules[package_name] = package
        self._modules[package_name] = package
        return package

    def _load_module(
        self,
        bundle: PluginBundleRef,
        relative_path: str,
        members: Mapping[str, bytes],
    ) -> ModuleType:
        module_name = self._module_name(bundle.bundle_digest, relative_path)
        existing = self._modules.get(module_name)
        if existing is not None:
            return existing
        payload = members.get(relative_path)
        if payload is None:
            raise RuntimeError("Public plugin module is absent from its generation")
        if module_name in sys.modules:
            raise RuntimeError("Public plugin module namespace is already active")

        package = self._ensure_package(bundle.bundle_digest)
        source_paths = self._source_paths(members)
        module = ModuleType(module_name)
        module.__file__ = f"<corex-plugin:{bundle.bundle_digest}:{relative_path}>"
        module.__package__ = package.__name__
        module.__loader__ = None
        module.__spec__ = importlib.machinery.ModuleSpec(module_name, loader=None)
        module_builtins = dict(vars(builtins))
        module_builtins["__import__"] = self._bundle_importer(
            bundle,
            members,
            source_paths,
        )
        module.__dict__["__builtins__"] = module_builtins
        sys.modules[module_name] = module
        self._modules[module_name] = module
        setattr(package, module_name.rpartition(".")[2], module)
        try:
            exec(
                compile(payload, module.__file__, "exec", dont_inherit=True),
                module.__dict__,
            )
        except BaseException:
            if sys.modules.get(module_name) is module:
                del sys.modules[module_name]
            self._modules.pop(module_name, None)
            if getattr(package, module_name.rpartition(".")[2], None) is module:
                delattr(package, module_name.rpartition(".")[2])
            raise
        return module

    def _bundle_importer(
        self,
        bundle: PluginBundleRef,
        members: Mapping[str, bytes],
        source_paths: Mapping[str, str],
    ):
        default_import = builtins.__import__
        package_name = self._package_name(bundle.bundle_digest)

        def import_from_bundle(
            name: str,
            globals: Mapping[str, object] | None = None,
            locals: Mapping[str, object] | None = None,
            fromlist: tuple[str, ...] | list[str] = (),
            level: int = 0,
        ) -> ModuleType:
            del locals
            with self._lock:
                if level == 0:
                    relative_name, separator, _remainder = name.partition(".")
                    relative_path = source_paths.get(relative_name)
                    if relative_path is None or separator:
                        return default_import(name, globals, None, fromlist, level)
                    return self._load_module(bundle, relative_path, members)

                caller_package = str((globals or {}).get("__package__", ""))
                try:
                    target = importlib.util.resolve_name(
                        "." * level + name,
                        caller_package,
                    )
                except (ImportError, ValueError):
                    return default_import(name, globals, None, fromlist, level)
                if target == package_name:
                    package = self._ensure_package(bundle.bundle_digest)
                    for item in fromlist:
                        relative_path = source_paths.get(item)
                        if relative_path is not None:
                            self._load_module(bundle, relative_path, members)
                    return package
                prefix = f"{package_name}."
                if target.startswith(prefix) and "." not in target[len(prefix) :]:
                    relative_path = source_paths.get(target[len(prefix) :])
                    if relative_path is not None:
                        return self._load_module(bundle, relative_path, members)
                return default_import(name, globals, None, fromlist, level)

        return import_from_bundle


__all__ = ["WorkerPluginRuntime"]
