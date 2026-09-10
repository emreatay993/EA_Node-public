# Purpose: Store and atomically compose node entries with their semantic data-type catalog.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_registry_validation.py, tests/test_plugin_runtime_agreement.py
# Landmarks: TrustedFactoryEntry; PythonFunctionEntry; NodeRegistry; atomic registration; catalog-aware property APIs

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any, Callable

from ea_node_editor.runtime_contracts import DataTypeCatalog

from . import instance_resolution, property_normalization, spec_validation

from .core_data_types import (
    CORE_DATA_CONVERSIONS,
    CORE_DATA_TYPE_FAMILIES,
    CORE_DATA_TYPE_OWNER_ID,
    CORE_DATA_TYPE_OWNER_VERSION,
    CORE_DATA_TYPES,
)
from .function_plugin import (
    EMPTY_PLUGIN_FINGERPRINT,
    PluginBundleRef,
    PythonFunctionRef,
    plugin_fingerprint,
)
from .node_specs import NodeTypeSpec, PortSpec
from .solution_provenance import trusted_solution_provenance_inputs
from .plugin_contracts import (
    NodePlugin,
    PluginContractManifest,
    PluginDescriptor,
    PluginProvenance,
)


@dataclass(slots=True, frozen=True)
class TrustedFactoryEntry:
    spec: NodeTypeSpec
    factory: Callable[[], NodePlugin]
    provenance: PluginProvenance | None = None
    owner_id: str = ""

    def descriptor(self) -> PluginDescriptor:
        return PluginDescriptor(
            spec=self.spec,
            factory=self.factory,
            provenance=self.provenance,
        )


@dataclass(slots=True, frozen=True)
class PythonFunctionEntry:
    spec: NodeTypeSpec
    function_ref: PythonFunctionRef
    provenance: PluginProvenance | None = None
    owner_id: str = ""
    unavailable_reason: str = ""

    def __post_init__(self) -> None:
        if self.spec.is_async != self.function_ref.is_async:
            raise ValueError(
                "Python function reference async state must match NodeTypeSpec.is_async"
            )
        if self.owner_id != self.function_ref.bundle_id:
            raise ValueError(
                "Python function entry owner_id must match function bundle_id"
            )
        if not isinstance(self.unavailable_reason, str):
            raise TypeError("Python function entry unavailable_reason must be a string")
        if self.unavailable_reason != self.unavailable_reason.strip():
            raise ValueError("Python function entry unavailable_reason must be trimmed")


RegistryEntry = TrustedFactoryEntry | PythonFunctionEntry


def _contract_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    if isinstance(value, partial):
        return {
            "__partial__": _contract_value(value.func),
            "args": _contract_value(value.args),
            "keywords": _contract_value(value.keywords or {}),
        }
    if callable(value):
        module = str(getattr(value, "__module__", "") or "")
        qualname = str(
            getattr(value, "__qualname__", getattr(value, "__name__", "")) or ""
        )
        if not module or not qualname:
            raise TypeError(
                "Registry contract callables require module and qualified names"
            )
        return {"__callable__": f"{module}:{qualname}"}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "__type__": f"{type(value).__module__}:{type(value).__qualname__}",
            **{
                item.name: _contract_value(getattr(value, item.name))
                for item in fields(value)
            },
        }
    if isinstance(value, Mapping):
        items = [
            (_contract_value(key), _contract_value(item)) for key, item in value.items()
        ]
        items.sort(
            key=lambda pair: json.dumps(
                pair[0], sort_keys=True, separators=(",", ":"), ensure_ascii=True
            )
        )
        return {"__mapping__": items}
    if isinstance(value, tuple):
        return {"__tuple__": [_contract_value(item) for item in value]}
    if isinstance(value, list):
        return {"__list__": [_contract_value(item) for item in value]}
    if isinstance(value, (set, frozenset)):
        items = [_contract_value(item) for item in value]
        items.sort(
            key=lambda item: json.dumps(
                item, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            )
        )
        return {"__set__": items}
    raise TypeError(
        "Registry contract contains unsupported value type "
        f"{type(value).__module__}.{type(value).__qualname__}"
    )


def _normalize_addon_runtime_config(
    value: Iterable[tuple[str, bool]],
) -> tuple[tuple[str, bool], ...]:
    normalized: dict[str, bool] = {}
    for addon_id, enabled in value:
        normalized_id = str(addon_id).strip()
        if not normalized_id:
            raise ValueError("add-on runtime ids must be non-empty strings")
        if type(enabled) is not bool:
            raise TypeError("add-on runtime enabled states must be booleans")
        if normalized_id in normalized:
            raise ValueError(f"duplicate add-on runtime id: {normalized_id}")
        normalized[normalized_id] = enabled
    return tuple(sorted(normalized.items()))


class NodeRegistry:
    def __init__(
        self,
        *,
        data_types: DataTypeCatalog | None = None,
        addon_runtime_config: Iterable[tuple[str, bool]] = (),
    ) -> None:
        if data_types is None:
            data_types = DataTypeCatalog()
            data_types.register_many(
                families=CORE_DATA_TYPE_FAMILIES,
                types=CORE_DATA_TYPES,
                conversions=CORE_DATA_CONVERSIONS,
                owner_id=CORE_DATA_TYPE_OWNER_ID,
                owner_version=CORE_DATA_TYPE_OWNER_VERSION,
                source_label="ea_node_editor.nodes.core_data_types",
            )
        elif not isinstance(data_types, DataTypeCatalog):
            raise TypeError("data_types must be a DataTypeCatalog")
        self._data_types = data_types
        self._entries: dict[str, RegistryEntry] = {}
        self._contract_manifests: dict[str, PluginContractManifest] = {}
        self._contract_manifest_versions: dict[str, str] = {}
        self._owner_source_identities: dict[str, str] = {}
        self._plugin_bundle_refs: dict[str, PluginBundleRef] = {}
        self._plugin_fingerprint = EMPTY_PLUGIN_FINGERPRINT
        self._addon_runtime_config = _normalize_addon_runtime_config(
            addon_runtime_config
        )
        self._contract_fingerprint = ""

    @property
    def data_types(self) -> DataTypeCatalog:
        return self._data_types

    def freeze(self) -> None:
        self._data_types.freeze()
        self._contract_fingerprint = ""

    def plugin_contract_manifest(self, owner_id: str) -> PluginContractManifest | None:
        return self._contract_manifests.get(str(owner_id).strip())

    def register_plugin_bundle(
        self,
        manifest: PluginContractManifest | None,
        descriptors: Iterable[PluginDescriptor],
        *,
        owner_id: str,
        owner_version: str = "",
        source_label: str = "",
        source_identity: str = "",
        replace_owner: bool = False,
        python_function_entries: Iterable[PythonFunctionEntry] = (),
        plugin_bundle: PluginBundleRef | None = None,
    ) -> None:
        normalized_owner_id = str(owner_id).strip()
        if not normalized_owner_id:
            raise ValueError(
                "Plugin bundle owner_id must be a non-empty trimmed string"
            )
        normalized_source_identity = str(source_identity).strip()
        owner_is_active = (
            normalized_owner_id in self._contract_manifests
            or normalized_owner_id in self._contract_manifest_versions
            or normalized_owner_id in self._owner_source_identities
            or any(
                entry.owner_id == normalized_owner_id
                for entry in self._entries.values()
            )
            or any(
                record.get("owner_id") == normalized_owner_id
                for record in self._data_types.snapshot()
            )
            or normalized_owner_id in self._plugin_bundle_refs
        )
        if owner_is_active and not replace_owner:
            raise ValueError(
                f"Plugin bundle owner {normalized_owner_id!r} is already active; "
                "pass replace_owner=True to replace it"
            )
        existing_source_identity = self._owner_source_identities.get(
            normalized_owner_id,
            "",
        )
        if (
            existing_source_identity
            and normalized_source_identity
            and existing_source_identity != normalized_source_identity
        ):
            raise ValueError(
                f"Plugin bundle owner {normalized_owner_id!r} is already "
                "registered from a different source"
            )
        if manifest is None:
            normalized_manifest = PluginContractManifest()
        elif isinstance(manifest, PluginContractManifest):
            normalized_manifest = manifest
        else:
            raise TypeError(
                "Plugin bundle manifest must be a PluginContractManifest or None"
            )
        normalized_owner_version = str(owner_version)
        was_frozen = self._data_types.is_frozen
        staged_catalog = self._data_types.fork(
            excluding_owner_id=normalized_owner_id if replace_owner else "",
        )
        staged = NodeRegistry(
            data_types=staged_catalog,
            addon_runtime_config=self._addon_runtime_config,
        )
        staged._entries = {
            type_id: entry
            for type_id, entry in self._entries.items()
            if not replace_owner or entry.owner_id != normalized_owner_id
        }
        staged._contract_manifests = {
            existing_owner: existing_manifest
            for existing_owner, existing_manifest in self._contract_manifests.items()
            if not replace_owner or existing_owner != normalized_owner_id
        }
        staged._contract_manifest_versions = {
            existing_owner: version
            for existing_owner, version in self._contract_manifest_versions.items()
            if not replace_owner or existing_owner != normalized_owner_id
        }
        staged._owner_source_identities = {
            existing_owner: identity
            for existing_owner, identity in self._owner_source_identities.items()
            if not replace_owner or existing_owner != normalized_owner_id
        }
        staged._plugin_bundle_refs = {
            existing_owner: bundle
            for existing_owner, bundle in self._plugin_bundle_refs.items()
            if not replace_owner or existing_owner != normalized_owner_id
        }
        staged._plugin_fingerprint = self._plugin_fingerprint
        staged_catalog.register_many(
            families=normalized_manifest.data_type_families,
            types=normalized_manifest.data_types,
            conversions=normalized_manifest.data_conversions,
            owner_id=normalized_owner_id,
            owner_version=normalized_owner_version,
            source_label=str(source_label),
        )
        staged.register_descriptors(descriptors, owner_id=normalized_owner_id)
        function_entries = tuple(python_function_entries)
        for entry in function_entries:
            if not isinstance(entry, PythonFunctionEntry):
                raise TypeError(
                    "python_function_entries must contain PythonFunctionEntry values"
                )
            if entry.owner_id != normalized_owner_id:
                raise ValueError(
                    "Python function entry owner_id must match plugin bundle owner_id"
                )
            trusted_solution_reuse = bool(
                normalized_owner_id == "ea_node_editor.builtins.tabular_data"
                and entry.provenance is not None
                and entry.provenance.kind == "package"
                and entry.provenance.package_name
                == "ea_node_editor_builtins_tabular_data"
                and entry.provenance.package_root is not None
                and plugin_bundle is not None
                and Path(plugin_bundle.approved_generation_root)
                == entry.provenance.package_root
            )
            register_function = (
                staged._register_trusted_python_function
                if trusted_solution_reuse
                else staged.register_python_function
            )
            register_function(
                entry.spec,
                entry.function_ref,
                provenance=entry.provenance,
                owner_id=entry.owner_id,
                unavailable_reason=entry.unavailable_reason,
            )
        if plugin_bundle is not None:
            if not isinstance(plugin_bundle, PluginBundleRef):
                raise TypeError("plugin_bundle must be a PluginBundleRef or None")
            if plugin_bundle.owner_id != normalized_owner_id:
                raise ValueError(
                    "plugin_bundle owner_id must match registry bundle owner_id"
                )
            if set(plugin_bundle.functions) != {
                entry.function_ref for entry in function_entries
            }:
                raise ValueError(
                    "plugin_bundle functions must match Python function entries"
                )
            staged._plugin_bundle_refs[normalized_owner_id] = plugin_bundle
        elif function_entries:
            raise ValueError("plugin_bundle is required with Python function entries")
        bundles = tuple(
            staged._plugin_bundle_refs[owner]
            for owner in sorted(staged._plugin_bundle_refs)
        )
        fingerprint = plugin_fingerprint(
            tuple(
                (entry.spec, entry.function_ref)
                for entry in staged._entries.values()
                if isinstance(entry, PythonFunctionEntry)
            ),
            bundles,
        )
        staged.set_python_plugin_catalog(
            bundles,
            plugin_fingerprint=fingerprint,
        )
        for entry in staged._entries.values():
            spec_validation.validate_node_spec(entry.spec, data_types=staged_catalog)
        staged._contract_manifests[normalized_owner_id] = normalized_manifest
        staged._contract_manifest_versions[normalized_owner_id] = (
            normalized_owner_version
        )
        committed_source_identity = (
            normalized_source_identity or existing_source_identity
        )
        if committed_source_identity:
            staged._owner_source_identities[normalized_owner_id] = (
                committed_source_identity
            )
        if was_frozen:
            staged.freeze()
        self._data_types = staged._data_types
        self._entries = staged._entries
        self._contract_manifests = staged._contract_manifests
        self._contract_manifest_versions = staged._contract_manifest_versions
        self._owner_source_identities = staged._owner_source_identities
        self._plugin_bundle_refs = staged._plugin_bundle_refs
        self._plugin_fingerprint = staged._plugin_fingerprint
        self._contract_fingerprint = ""

    def register(
        self,
        factory: Callable[[], NodePlugin],
        *,
        provenance: PluginProvenance | None = None,
        owner_id: str = "",
    ) -> None:
        plugin = factory()
        spec = plugin.spec()
        self.register_descriptor(
            spec,
            factory,
            provenance=provenance,
            owner_id=owner_id,
        )

    def register_descriptor(
        self,
        spec: NodeTypeSpec | PluginDescriptor,
        factory: Callable[[], NodePlugin] | None = None,
        *,
        provenance: PluginProvenance | None = None,
        owner_id: str = "",
    ) -> None:
        if isinstance(spec, PluginDescriptor):
            descriptor = spec
            spec = descriptor.spec
            factory = descriptor.factory
            if provenance is None:
                provenance = descriptor.provenance
        if factory is None or not callable(factory):
            raise TypeError("Plugin factory must be callable")
        spec_validation.validate_node_spec(spec, data_types=self._data_types)
        if spec.solution_provenance_inputs:
            raise ValueError("Trusted factory nodes cannot declare solution provenance")
        if spec.solution_reuse_scope != "never":
            raise ValueError(
                "Trusted factory nodes must use solution_reuse_scope='never'"
            )
        if spec.type_id in self._entries:
            raise ValueError(f"Node type already registered: {spec.type_id}")
        self._entries[spec.type_id] = TrustedFactoryEntry(
            spec=spec,
            factory=factory,
            provenance=provenance,
            owner_id=str(owner_id).strip(),
        )
        self._contract_fingerprint = ""

    def register_descriptors(
        self,
        descriptors: Iterable[PluginDescriptor],
        *,
        owner_id: str = "",
    ) -> None:
        descriptor_items = tuple(descriptors)
        staged_entries = dict(self._entries)
        normalized_owner_id = str(owner_id).strip()
        for descriptor in descriptor_items:
            if not isinstance(descriptor, PluginDescriptor):
                raise TypeError(
                    "register_descriptors entries must be PluginDescriptor values"
                )
            if not callable(descriptor.factory):
                raise TypeError("Plugin factory must be callable")
            spec_validation.validate_node_spec(
                descriptor.spec, data_types=self._data_types
            )
            if descriptor.spec.solution_provenance_inputs:
                raise ValueError(
                    "Trusted factory nodes cannot declare solution provenance"
                )
            if descriptor.spec.solution_reuse_scope != "never":
                raise ValueError(
                    "Trusted factory nodes must use solution_reuse_scope='never'"
                )
            type_id = descriptor.spec.type_id
            if type_id in staged_entries:
                raise ValueError(f"Node type already registered: {type_id}")
            staged_entries[type_id] = TrustedFactoryEntry(
                spec=descriptor.spec,
                factory=descriptor.factory,
                provenance=descriptor.provenance,
                owner_id=normalized_owner_id,
            )
        self._entries = staged_entries
        self._contract_fingerprint = ""

    def register_python_function(
        self,
        spec: NodeTypeSpec,
        function_ref: PythonFunctionRef,
        *,
        provenance: PluginProvenance | None = None,
        owner_id: str = "",
        unavailable_reason: str = "",
    ) -> None:
        self._register_python_function(
            spec,
            function_ref,
            provenance=provenance,
            owner_id=owner_id,
            unavailable_reason=unavailable_reason,
            trusted_solution_reuse=False,
        )

    def _register_trusted_python_function(
        self,
        spec: NodeTypeSpec,
        function_ref: PythonFunctionRef,
        *,
        provenance: PluginProvenance | None = None,
        owner_id: str = "",
        unavailable_reason: str = "",
    ) -> None:
        normalized_owner_id = str(owner_id).strip() or function_ref.bundle_id
        trusted_builtin = bool(
            normalized_owner_id == "corex:builtin:functions" and provenance is None
        )
        trusted_tabular = bool(
            normalized_owner_id == "ea_node_editor.builtins.tabular_data"
            and provenance is not None
            and provenance.kind == "package"
            and provenance.package_name == "ea_node_editor_builtins_tabular_data"
            and provenance.package_root is not None
            and provenance.source_path is not None
            and provenance.source_path.parent == provenance.package_root
        )
        if not trusted_builtin and not trusted_tabular:
            raise ValueError("Trusted solution reuse provenance is invalid")
        if trusted_builtin and spec.type_id == "model.viewer":
            from .builtins.engineering_viewer import SCENE_INPUT_GROUP

            spec = replace(spec, dynamic_port_groups=(SCENE_INPUT_GROUP,))
        self._register_python_function(
            spec,
            function_ref,
            provenance=provenance,
            owner_id=owner_id,
            unavailable_reason=unavailable_reason,
            trusted_solution_reuse=True,
        )

    def _register_python_function(
        self,
        spec: NodeTypeSpec,
        function_ref: PythonFunctionRef,
        *,
        provenance: PluginProvenance | None,
        owner_id: str,
        unavailable_reason: str,
        trusted_solution_reuse: bool,
    ) -> None:
        if not isinstance(function_ref, PythonFunctionRef):
            raise TypeError("function_ref must be a PythonFunctionRef")
        normalized_owner_id = str(owner_id).strip() or function_ref.bundle_id
        if normalized_owner_id != function_ref.bundle_id:
            raise ValueError("owner_id must match function_ref.bundle_id")
        trusted_provenance = (
            trusted_solution_provenance_inputs(
                normalized_owner_id,
                spec.type_id,
            )
            if trusted_solution_reuse
            else ()
        )
        if spec.solution_provenance_inputs:
            raise ValueError(
                "Python function declarations cannot supply solution provenance"
            )
        if trusted_provenance:
            spec = replace(spec, solution_provenance_inputs=trusted_provenance)
        spec_validation.validate_node_spec(spec, data_types=self._data_types)
        if spec.solution_reuse_scope != "never" and not trusted_solution_reuse:
            raise ValueError(
                "Untrusted function nodes must use solution_reuse_scope='never'"
            )
        if spec.type_id in self._entries:
            raise ValueError(f"Node type already registered: {spec.type_id}")
        self._entries[spec.type_id] = PythonFunctionEntry(
            spec=spec,
            function_ref=function_ref,
            provenance=provenance,
            owner_id=normalized_owner_id,
            unavailable_reason=unavailable_reason,
        )
        self._plugin_fingerprint = ""
        self._contract_fingerprint = ""

    def create(self, type_id: str) -> NodePlugin:
        try:
            entry = self._entries[type_id]
        except KeyError as exc:
            raise KeyError(f"Unknown node type: {type_id}") from exc
        if isinstance(entry, PythonFunctionEntry):
            if entry.unavailable_reason:
                raise RuntimeError(entry.unavailable_reason)
            raise RuntimeError(f"Function node {type_id!r} requires worker resolution")
        return entry.factory()

    def entry_or_none(self, type_id: str) -> RegistryEntry | None:
        return self._entries.get(type_id)

    def get_entry(self, type_id: str) -> RegistryEntry:
        try:
            return self._entries[type_id]
        except KeyError as exc:
            raise KeyError(f"Unknown node type: {type_id}") from exc

    def python_function_ref_or_none(self, type_id: str) -> PythonFunctionRef | None:
        entry = self._entries.get(type_id)
        return entry.function_ref if isinstance(entry, PythonFunctionEntry) else None

    def provenance_or_none(self, type_id: str) -> PluginProvenance | None:
        entry = self._entries.get(type_id)
        return entry.provenance if entry is not None else None

    def unavailable_reason(self, type_id: str) -> str:
        entry = self._entries.get(type_id)
        return (
            entry.unavailable_reason if isinstance(entry, PythonFunctionEntry) else ""
        )

    def get_spec(self, type_id: str) -> NodeTypeSpec:
        try:
            return self._entries[type_id].spec
        except KeyError as exc:
            raise KeyError(f"Unknown node type: {type_id}") from exc

    def validate_spec(self, spec: NodeTypeSpec) -> None:
        spec_validation.validate_node_spec(spec, data_types=self._data_types)

    def resolve_spec(
        self,
        type_id: str,
        properties: Mapping[str, object],
    ) -> NodeTypeSpec:
        base_spec = self.get_spec(type_id)
        resolved = instance_resolution.resolve_instance_spec(base_spec, properties)
        if resolved is not base_spec:
            spec_validation.validate_node_spec(resolved, data_types=self._data_types)
        return resolved

    def spec_or_none(self, type_id: str) -> NodeTypeSpec | None:
        entry = self._entries.get(type_id)
        if entry is None:
            return None
        return entry.spec

    def get_descriptor(self, type_id: str) -> PluginDescriptor:
        try:
            entry = self._entries[type_id]
        except KeyError as exc:
            raise KeyError(f"Unknown node type: {type_id}") from exc
        if isinstance(entry, PythonFunctionEntry):
            raise TypeError(f"Node type {type_id!r} does not use a trusted descriptor")
        return entry.descriptor()

    def descriptor_or_none(self, type_id: str) -> PluginDescriptor | None:
        entry = self._entries.get(type_id)
        if entry is None:
            return None
        return entry.descriptor() if isinstance(entry, TrustedFactoryEntry) else None

    def all_specs(self) -> list[NodeTypeSpec]:
        return [entry.spec for entry in self._entries.values()]

    def all_descriptors(self) -> list[PluginDescriptor]:
        return [
            entry.descriptor()
            for entry in self._entries.values()
            if isinstance(entry, TrustedFactoryEntry)
        ]

    def trusted_runtime_copy(self) -> NodeRegistry:
        staged = NodeRegistry(
            data_types=self._data_types,
            addon_runtime_config=self._addon_runtime_config,
        )
        staged._entries = {
            type_id: entry
            for type_id, entry in self._entries.items()
            if isinstance(entry, TrustedFactoryEntry)
        }
        staged._contract_manifests = dict(self._contract_manifests)
        staged._contract_manifest_versions = dict(self._contract_manifest_versions)
        staged._owner_source_identities = dict(self._owner_source_identities)
        return staged

    def all_python_function_refs(self) -> tuple[PythonFunctionRef, ...]:
        return tuple(
            entry.function_ref
            for entry in self._entries.values()
            if isinstance(entry, PythonFunctionEntry)
        )

    def set_python_plugin_catalog(
        self,
        bundles: tuple[PluginBundleRef, ...],
        *,
        plugin_fingerprint: str,
    ) -> None:
        if not isinstance(bundles, tuple) or not all(
            isinstance(bundle, PluginBundleRef) for bundle in bundles
        ):
            raise TypeError("bundles must be a tuple of PluginBundleRef values")
        owners = [bundle.owner_id for bundle in bundles]
        if len(owners) != len(set(owners)):
            raise ValueError("Plugin bundle owner ids must be unique")
        bundled_functions = {
            function for bundle in bundles for function in bundle.functions
        }
        if bundled_functions != set(self.all_python_function_refs()):
            raise ValueError(
                "Plugin bundles must match registered Python function refs"
            )
        fingerprint = str(plugin_fingerprint)
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise ValueError("plugin_fingerprint must be a lowercase SHA-256 digest")
        self._plugin_bundle_refs = {bundle.owner_id: bundle for bundle in bundles}
        self._plugin_fingerprint = fingerprint
        self._contract_fingerprint = ""

    def plugin_bundle_refs(self) -> tuple[PluginBundleRef, ...]:
        return tuple(
            self._plugin_bundle_refs[owner_id]
            for owner_id in sorted(self._plugin_bundle_refs)
        )

    def plugin_fingerprint(self) -> str:
        return self._plugin_fingerprint

    def set_addon_runtime_config(
        self,
        value: Iterable[tuple[str, bool]],
    ) -> None:
        self._addon_runtime_config = _normalize_addon_runtime_config(value)
        self._contract_fingerprint = ""

    def addon_runtime_config(self) -> tuple[tuple[str, bool], ...]:
        return self._addon_runtime_config

    def execution_environment_facts(self) -> dict[str, object]:
        """Return deterministic declared environment inputs for route handshakes."""

        enabled_by_id = dict(self._addon_runtime_config)
        toolchains = []
        package_names: set[str] = set()
        for owner_id, manifest in sorted(self._contract_manifests.items()):
            for toolchain in manifest.toolchains:
                requirements = tuple(
                    (
                        requirement.requirement_id,
                        requirement.kind,
                        requirement.import_name,
                        requirement.command,
                        requirement.version_spec,
                        requirement.optional,
                    )
                    for requirement in toolchain.requirements
                )
                toolchains.append(
                    (
                        owner_id,
                        toolchain.toolchain_id,
                        toolchain.kind,
                        toolchain.language,
                        requirements,
                    )
                )
                package_names.update(
                    requirement.import_name or requirement.requirement_id
                    for requirement in toolchain.requirements
                    if requirement.kind == "python_module"
                )
        return {
            "addons": tuple(
                (
                    owner_id,
                    enabled,
                    self._contract_manifest_versions.get(owner_id, ""),
                )
                for owner_id, enabled in sorted(enabled_by_id.items())
            ),
            "plugin_bundles": tuple(
                (
                    bundle.owner_id,
                    bundle.version,
                    bundle.bundle_digest,
                )
                for bundle in self.plugin_bundle_refs()
            ),
            "toolchains": tuple(toolchains),
            "python_packages": tuple(sorted(package_names)),
        }

    def contract_fingerprint(self) -> str:
        if self._contract_fingerprint:
            return self._contract_fingerprint
        entries = []
        for type_id, entry in sorted(self._entries.items()):
            implementation = (
                entry.function_ref
                if isinstance(entry, PythonFunctionEntry)
                else entry.factory
            )
            entries.append(
                {
                    "type_id": type_id,
                    "kind": type(entry).__name__,
                    "owner_id": entry.owner_id,
                    "spec": _contract_value(entry.spec),
                    "implementation": _contract_value(implementation),
                }
            )
        payload = {
            "schema_version": 1,
            "data_type_catalog": self._data_types.fingerprint(),
            "public_plugins": self._plugin_fingerprint,
            "addon_runtime_config": list(self._addon_runtime_config),
            "entries": entries,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if self._data_types.is_frozen:
            self._contract_fingerprint = fingerprint
        return fingerprint

    def default_properties(self, type_id: str) -> dict[str, Any]:
        return self.normalize_properties(type_id, {}, include_defaults=True)

    def normalize_property_value(
        self,
        type_id: str,
        key: str,
        value: Any,
        *,
        properties: Mapping[str, object] | None = None,
    ) -> Any:
        spec = self.get_spec(type_id)
        return property_normalization.normalize_property_value(
            spec,
            key,
            value,
            properties=properties,
            data_types=self._data_types,
        )

    def normalize_properties(
        self,
        type_id: str,
        values: dict[str, Any] | None,
        *,
        include_defaults: bool = True,
    ) -> dict[str, Any]:
        spec = self.get_spec(type_id)
        return property_normalization.normalize_properties(
            spec,
            values,
            include_defaults=include_defaults,
            data_types=self._data_types,
        )


def default_port(spec: NodeTypeSpec, key: str) -> PortSpec:
    for port in spec.ports:
        if port.key == key:
            return port
    raise KeyError(f"Port {key} not found in {spec.type_id}")
