# Purpose: Register availability-gated trusted add-on contracts, descriptors, and functions atomically.
# Map: subsystems/addons.md
# Tests: tests/test_addon_registry_contributions.py

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from ea_node_editor.nodes.function_bundle import (
    PreparedFunctionBundle,
    bounded_bundle_log_label,
    build_function_entries,
    materialize_prepared_function_bundle,
    missing_bundle_imports,
    module_declarations,
    node_inventory,
    safe_bundle_segment,
    source_digest,
)
from ea_node_editor.nodes.package_schema import (
    PLUGIN_MANIFEST_LIMIT,
    PLUGIN_MEMBER_LIMIT,
    PLUGIN_SOURCE_LIMIT,
    PLUGIN_TOTAL_LIMIT,
    canonical_manifest_bytes,
    validated_plugin_member_path,
)
from ea_node_editor.nodes.plugin_contracts import (
    PluginBackendDescriptor,
    PluginContractManifest,
    PluginDescriptor,
    PluginProvenance,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.settings import plugin_generations_dir

logger = logging.getLogger(__name__)


def _prepare_backend_function_bundle(
    backend: PluginBackendDescriptor,
) -> PreparedFunctionBundle:
    load_sources = backend.load_function_sources
    if load_sources is None:
        raise ValueError("Plugin backend does not declare function sources")
    raw_sources = load_sources()
    if not isinstance(raw_sources, tuple) or not raw_sources:
        raise TypeError("Plugin backend function sources must be a non-empty tuple")
    if len(raw_sources) + 1 > PLUGIN_MEMBER_LIMIT:
        raise ValueError("Plugin backend function bundle contains too many members")

    members: dict[str, bytes] = {}
    seen_paths: set[str] = set()
    module_names: list[str] = []
    for index, raw_item in enumerate(raw_sources):
        if not isinstance(raw_item, tuple) or len(raw_item) != 2:
            raise TypeError(
                f"Plugin backend function source {index} must be a path/source tuple"
            )
        raw_path, source = raw_item
        path = validated_plugin_member_path(raw_path, root_python=True)
        folded_path = path.casefold()
        if folded_path in seen_paths:
            raise ValueError("Plugin backend function source paths must be unique")
        if not isinstance(source, str):
            raise TypeError("Plugin backend function source must be a string")
        payload = source.encode("utf-8")
        if len(payload) > PLUGIN_SOURCE_LIMIT:
            raise ValueError("Plugin backend function source is too large")
        seen_paths.add(folded_path)
        module_names.append(path)
        members[path] = payload

    package_name = safe_bundle_segment(backend.plugin_id, fallback="addon")
    version = backend.addon_manifest.version if backend.addon_manifest else "0.0.0"
    manifest: dict[str, object] = {
        "schema_version": 2,
        "name": package_name,
        "version": version,
        "author": "",
        "description": "",
        "modules": module_names,
        "sources": [
            {"path": path, "sha256": source_digest(members[path])}
            for path in module_names
        ],
        "assets": [],
        "nodes": [],
    }
    declarations = module_declarations(
        manifest,
        members,
        filename_prefix=backend.plugin_id,
        owner_id=backend.plugin_id,
        allow_internal_metadata=True,
        allow_reserved_ids=True,
    )
    parsed_type_ids = tuple(
        declaration.spec.type_id for _path, declaration in declarations
    )
    if parsed_type_ids != backend.function_type_ids:
        raise ValueError(
            "Plugin backend function type ids do not match static declarations"
        )
    manifest["nodes"] = node_inventory(declarations)
    manifest_size = len(canonical_manifest_bytes(manifest))
    if manifest_size > PLUGIN_MANIFEST_LIMIT:
        raise ValueError("Plugin backend function manifest is too large")
    if manifest_size + sum(map(len, members.values())) > PLUGIN_TOTAL_LIMIT:
        raise ValueError("Plugin backend function bundle is too large")
    missing = missing_bundle_imports(members, set(module_names))
    return PreparedFunctionBundle(
        owner_id=backend.plugin_id,
        version=version,
        manifest=manifest,
        members=members,
        declarations=declarations,
        unavailable_reason=(
            f"{missing[0]} is not included in this COREX bundle." if missing else ""
        ),
        log_label=bounded_bundle_log_label(backend.plugin_id),
        source_root=Path(__file__).parents[1] / "nodes",
        package_name=package_name,
    )


def _merge_contract_manifests(
    *manifests: PluginContractManifest,
) -> PluginContractManifest:
    return PluginContractManifest(
        runtime_backends=tuple(
            item for manifest in manifests for item in manifest.runtime_backends
        ),
        toolchains=tuple(
            item for manifest in manifests for item in manifest.toolchains
        ),
        artifacts=tuple(item for manifest in manifests for item in manifest.artifacts),
        surface_capabilities=tuple(
            item for manifest in manifests for item in manifest.surface_capabilities
        ),
        data_type_families=tuple(
            item for manifest in manifests for item in manifest.data_type_families
        ),
        data_types=tuple(
            item for manifest in manifests for item in manifest.data_types
        ),
        data_conversions=tuple(
            item for manifest in manifests for item in manifest.data_conversions
        ),
    )


def _trusted_owner_id(source: Path | str, provenance: PluginProvenance | None) -> str:
    if provenance is not None and provenance.kind == "package":
        return (
            "plugin:package:"
            f"{safe_bundle_segment(provenance.package_name, fallback='package')}"
        )
    source_path = provenance.source_path if provenance is not None else None
    source_name = (
        source_path.stem if source_path is not None else Path(str(source)).stem
    )
    return f"plugin:file:{safe_bundle_segment(source_name, fallback='plugin')}"


def _plugin_source_identity(provenance: PluginProvenance | None) -> str:
    if provenance is None or provenance.source_path is None:
        return ""
    return os.path.normcase(str(provenance.source_path.resolve()))


def _register_plugin_descriptors(
    descriptors: tuple[PluginDescriptor, ...],
    registry: NodeRegistry,
    source: Path | str,
    *,
    provenance: PluginProvenance | None = None,
    manifest: PluginContractManifest | None = None,
    owner_id: str = "",
    owner_version: str = "",
) -> list[str]:
    normalized_descriptors = tuple(
        descriptor
        if provenance is None or descriptor.provenance == provenance
        else replace(descriptor, provenance=provenance)
        for descriptor in descriptors
    )
    normalized_owner_id = owner_id or _trusted_owner_id(source, provenance)
    try:
        registry.register_plugin_bundle(
            manifest,
            normalized_descriptors,
            owner_id=normalized_owner_id,
            owner_version=owner_version,
            source_label=str(source),
            source_identity=_plugin_source_identity(provenance),
            replace_owner=True,
        )
    except (KeyError, TypeError, ValueError):
        logger.warning(
            "Plugin %s skipped [invalid_bundle]",
            bounded_bundle_log_label(normalized_owner_id),
        )
        return []
    return [descriptor.spec.type_id for descriptor in normalized_descriptors]


def _register_plugin_backend(
    backend: PluginBackendDescriptor,
    registry: NodeRegistry,
    source: Path | str,
    *,
    provenance: PluginProvenance | None = None,
    generation_root: Path,
) -> list[str]:
    availability = backend.get_availability()
    if not availability.is_available:
        logger.info(
            "Plugin backend %s skipped [unavailable]",
            bounded_bundle_log_label(backend.plugin_id),
        )
        return []
    owner_version = backend.addon_manifest.version if backend.addon_manifest else ""
    manifest = _merge_contract_manifests(backend.contract_manifest)
    descriptors = backend.load_descriptors()
    if backend.load_function_sources is not None:
        prepared = _prepare_backend_function_bundle(backend)
        effective_provenance = backend.provenance or provenance
        bundle, generation = materialize_prepared_function_bundle(
            prepared,
            generation_root,
        )
        provenance_by_module = {
            module_path: (
                effective_provenance
                if effective_provenance is not None
                else PluginProvenance(
                    kind="package",
                    source_path=generation / module_path,
                    package_root=generation,
                    package_name=prepared.package_name,
                )
            )
            for module_path, _declaration in prepared.declarations
        }
        function_entries = build_function_entries(
            prepared,
            bundle,
            provenance_by_module,
        )
        normalized_descriptors = tuple(
            descriptor
            if effective_provenance is None
            or descriptor.provenance == effective_provenance
            else replace(descriptor, provenance=effective_provenance)
            for descriptor in descriptors
        )
        registry.register_plugin_bundle(
            manifest,
            normalized_descriptors,
            owner_id=backend.plugin_id,
            owner_version=owner_version,
            source_label=str(source),
            source_identity=_plugin_source_identity(effective_provenance),
            replace_owner=True,
            python_function_entries=function_entries,
            plugin_bundle=bundle,
        )
        return [
            *(descriptor.spec.type_id for descriptor in normalized_descriptors),
            *(entry.spec.type_id for entry in function_entries),
        ]
    return _register_plugin_descriptors(
        descriptors,
        registry,
        source,
        provenance=backend.provenance or provenance,
        manifest=manifest,
        owner_id=backend.plugin_id,
        owner_version=owner_version,
    )


def register_plugin_backends(
    backends: Sequence[PluginBackendDescriptor],
    registry: NodeRegistry,
    source: Path | str,
    *,
    provenance: PluginProvenance | None = None,
    generation_root: Path | None = None,
) -> list[str]:
    loaded: list[str] = []
    resolved_generation_root = generation_root or plugin_generations_dir()
    for backend in backends:
        try:
            loaded.extend(
                _register_plugin_backend(
                    backend,
                    registry,
                    source,
                    provenance=provenance,
                    generation_root=resolved_generation_root,
                )
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Plugin backend %s failed [backend_load]",
                bounded_bundle_log_label(backend.plugin_id),
            )
    return loaded


def register_live_addon_contributions(
    registry: NodeRegistry,
    *,
    preferences_document: object,
    store: object = None,
    generation_root: Path,
) -> None:
    from ea_node_editor.addons.catalog import live_addon_backend_collections

    for collection in live_addon_backend_collections(
        preferences_document=preferences_document,
        store=store,
    ):
        register_plugin_backends(
            collection.backends,
            registry,
            collection.source,
            generation_root=generation_root,
        )


__all__ = ["register_live_addon_contributions", "register_plugin_backends"]
