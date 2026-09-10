# Purpose: Discover public function plugins statically and publish immutable generations.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_plugin_loader.py

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ea_node_editor.common.path_safety import is_reparse_point
from ea_node_editor.nodes.function_bundle import (
    PreparedFunctionBundle,
    bounded_bundle_log_label,
    build_function_entries,
    materialize_prepared_function_bundle,
    missing_bundle_imports,
    node_inventory,
    registry_plugin_fingerprint,
    safe_bundle_segment,
    source_digest,
)
from ea_node_editor.nodes.function_plugin import PluginBundleRef
from ea_node_editor.nodes.plugin_contracts import PluginProvenance
from ea_node_editor.nodes.plugin_declaration import (
    PluginDeclarationError,
    discover_plugin_declarations,
)
from ea_node_editor.nodes.package_schema import (
    MANIFEST_FILENAME,
    PLUGIN_SOURCE_LIMIT,
    SCHEMA_1_UNSUPPORTED_MESSAGE,
    read_validated_package_directory,
    validated_package_declarations,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.settings import plugin_generations_dir, plugins_dir

logger = logging.getLogger(__name__)

_ROOT_ENTRY_LIMIT = 512


@dataclass(frozen=True, slots=True)
class PluginDiscoveryResult:
    type_ids: tuple[str, ...]
    bundles: tuple[PluginBundleRef, ...]
    plugin_fingerprint: str


def _read_bounded(path: Path, *, limit: int, label: str) -> bytes:
    try:
        if path.stat().st_size > limit:
            raise ValueError(f"{label} is too large")
        with path.open("rb") as stream:
            payload = stream.read(limit + 1)
    except OSError as exc:
        raise ValueError(f"{label} cannot be read") from exc
    if len(payload) > limit:
        raise ValueError(f"{label} is too large")
    return payload


def _prepare_loose_file(source_path: Path) -> PreparedFunctionBundle | None:
    if is_reparse_point(source_path) or not source_path.is_file():
        raise ValueError("Loose plugin source must be a regular file")
    payload = _read_bounded(
        source_path,
        limit=PLUGIN_SOURCE_LIMIT,
        label="Loose plugin source",
    )
    try:
        source = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Loose plugin source must be UTF-8") from exc
    declarations = discover_plugin_declarations(source, filename=source_path.name)
    if not declarations:
        return None
    if any(declaration.spec.icon for declaration in declarations):
        raise ValueError("Loose plugins cannot declare custom icons; export a package")
    name = safe_bundle_segment(source_path.stem, fallback="plugin")
    if name.startswith("_"):
        name = f"plugin{name}"
    owner_id = f"plugin:file:{name}"
    module_path = source_path.name
    inventory = node_inventory(tuple((module_path, item) for item in declarations))
    manifest: dict[str, object] = {
        "schema_version": 2,
        "name": name,
        "version": "0.0.0",
        "author": "",
        "description": "",
        "modules": [module_path],
        "sources": [{"path": module_path, "sha256": source_digest(payload)}],
        "assets": [],
        "nodes": inventory,
    }
    members = {module_path: payload}
    missing = missing_bundle_imports(members, {module_path})
    unavailable_reason = (
        f"{missing[0]} is not included in this COREX bundle." if missing else ""
    )
    return PreparedFunctionBundle(
        owner_id=owner_id,
        version="0.0.0",
        manifest=manifest,
        members=members,
        declarations=tuple((module_path, item) for item in declarations),
        unavailable_reason=unavailable_reason,
        log_label=bounded_bundle_log_label(owner_id),
        source_root=source_path.parent.resolve(),
    )


def _prepare_package(package_dir: Path) -> PreparedFunctionBundle:
    package = read_validated_package_directory(package_dir)
    owner_id = (
        f"plugin:package:{safe_bundle_segment(package.schema.name, fallback='package')}"
    )
    declarations = validated_package_declarations(
        package,
        filename_prefix=package.schema.name,
        owner_id=owner_id,
        require_declared_icons=True,
    )
    source_paths = {path for path, _digest in package.schema.sources}
    missing = missing_bundle_imports(package.members, source_paths)
    unavailable_reason = (
        f"{missing[0]} is not included in this COREX bundle." if missing else ""
    )
    return PreparedFunctionBundle(
        owner_id=owner_id,
        version=package.schema.version,
        manifest=package.manifest,
        members=package.members,
        declarations=declarations,
        unavailable_reason=unavailable_reason,
        log_label=bounded_bundle_log_label(owner_id),
        source_root=package_dir.resolve(),
        package_name=package.schema.name,
    )


def _register_public_function_bundle(
    prepared: PreparedFunctionBundle,
    registry: NodeRegistry,
    generation_root: Path,
) -> tuple[PluginBundleRef, tuple[str, ...]]:
    type_ids = [
        declaration.spec.type_id for _path, declaration in prepared.declarations
    ]
    if len(type_ids) != len(set(type_ids)):
        raise ValueError("Plugin bundle contains duplicate node ids")
    if any(registry.spec_or_none(type_id) is not None for type_id in type_ids):
        raise ValueError("Plugin bundle conflicts with an active node id")
    if any(
        bundle.owner_id == prepared.owner_id for bundle in registry.plugin_bundle_refs()
    ):
        raise ValueError("Plugin bundle owner is already active")
    if any(
        entry.owner_id == prepared.owner_id
        for entry in (
            registry.entry_or_none(spec.type_id) for spec in registry.all_specs()
        )
        if entry is not None
    ):
        raise ValueError("Plugin bundle owner is already active")
    for _module_path, declaration in prepared.declarations:
        registry.validate_spec(declaration.spec)

    bundle, generation = materialize_prepared_function_bundle(
        prepared,
        generation_root,
    )
    provenance_by_module = {
        module_path: (
            PluginProvenance(
                kind="package",
                source_path=generation / module_path,
                package_root=generation,
                package_name=prepared.package_name,
            )
            if prepared.package_name
            else PluginProvenance(
                kind="file",
                source_path=prepared.source_root / module_path,
            )
        )
        for module_path, _declaration in prepared.declarations
    }
    function_entries = build_function_entries(
        prepared,
        bundle,
        provenance_by_module,
    )
    for entry in function_entries:
        registry.register_python_function(
            entry.spec,
            entry.function_ref,
            provenance=entry.provenance,
            owner_id=entry.owner_id,
            unavailable_reason=entry.unavailable_reason,
        )
    return bundle, tuple(entry.spec.type_id for entry in function_entries)


def _root_entries(root: Path) -> tuple[Path, ...]:
    entries: list[Path] = []
    for index, entry in enumerate(root.iterdir()):
        if index >= _ROOT_ENTRY_LIMIT:
            raise ValueError("Plugin root contains too many entries")
        entries.append(entry)
    return tuple(sorted(entries, key=lambda path: path.name.casefold()))


def _prepared_static_bundles(
    roots: Sequence[Path],
    *,
    strict: bool,
    staged_package_root: Path | None,
) -> tuple[PreparedFunctionBundle, ...]:
    staged = (
        _prepare_package(Path(staged_package_root))
        if staged_package_root is not None
        else None
    )
    replacement_name = staged.package_name if staged is not None else ""
    replacement_root = Path(roots[0]).resolve() if replacement_name and roots else None
    candidates: list[PreparedFunctionBundle] = []
    seen_roots: set[Path] = set()
    for raw_root in roots:
        configured_root = Path(raw_root)
        if is_reparse_point(configured_root):
            if strict:
                raise ValueError("Plugin root must not be a path alias")
            logger.warning("Plugin root skipped [symlink_root]")
            continue
        root = configured_root.resolve()
        if root in seen_roots:
            continue
        seen_roots.add(root)
        if not root.is_dir():
            continue
        try:
            entries = _root_entries(root)
        except (OSError, ValueError):
            if strict:
                raise ValueError("Plugin root is invalid") from None
            logger.warning("Plugin root skipped [invalid_root]")
            continue
        for source_path in entries:
            if (
                source_path.suffix != ".py"
                or source_path.name.startswith("_")
                or is_reparse_point(source_path)
                or not source_path.is_file()
            ):
                continue
            try:
                prepared = _prepare_loose_file(source_path)
                if prepared is not None:
                    candidates.append(prepared)
            except OSError:
                if strict:
                    raise ValueError("Loose plugin source cannot be read") from None
                logger.warning(
                    "Plugin %s skipped [invalid_bundle]",
                    bounded_bundle_log_label(f"plugin:file:{source_path.stem}"),
                )
            except (ValueError, PluginDeclarationError):
                if strict:
                    raise
                logger.warning(
                    "Plugin %s skipped [invalid_bundle]",
                    bounded_bundle_log_label(f"plugin:file:{source_path.stem}"),
                )
        for package_dir in entries:
            if (
                not package_dir.is_dir()
                or is_reparse_point(package_dir)
                or package_dir.name.startswith((".", "_"))
                or not (package_dir / MANIFEST_FILENAME).exists()
            ):
                continue
            if (
                root == replacement_root
                and replacement_name
                and package_dir.name == replacement_name
            ):
                continue
            try:
                candidates.append(_prepare_package(package_dir))
            except OSError:
                if strict:
                    raise ValueError("Plugin package cannot be read") from None
                logger.warning(
                    "Plugin %s skipped [invalid_bundle]",
                    bounded_bundle_log_label(f"plugin:package:{package_dir.name}"),
                )
            except (ValueError, PluginDeclarationError) as exc:
                if strict:
                    raise
                label = bounded_bundle_log_label(f"plugin:package:{package_dir.name}")
                if str(exc) == SCHEMA_1_UNSUPPORTED_MESSAGE:
                    logger.warning(
                        "Plugin %s skipped [schema_1]: %s",
                        label,
                        SCHEMA_1_UNSUPPORTED_MESSAGE,
                    )
                else:
                    logger.warning("Plugin %s skipped [invalid_bundle]", label)
    if staged is not None:
        candidates.append(staged)
    return tuple(candidates)


def _discover_static_plugins(
    registry: NodeRegistry,
    *,
    roots: Sequence[Path],
    generation_root: Path,
    strict: bool,
    staged_package_root: Path | None = None,
) -> PluginDiscoveryResult:
    loaded: list[str] = []
    new_bundles: list[PluginBundleRef] = []
    candidates = _prepared_static_bundles(
        roots,
        strict=strict,
        staged_package_root=staged_package_root,
    )
    for prepared in candidates:
        try:
            bundle, type_ids = _register_public_function_bundle(
                prepared,
                registry,
                Path(generation_root),
            )
        except (OSError, TypeError, ValueError):
            if strict:
                raise
            logger.warning(
                "Plugin %s skipped [invalid_bundle]",
                prepared.log_label,
            )
            continue
        new_bundles.append(bundle)
        loaded.extend(type_ids)

    bundles = (*registry.plugin_bundle_refs(), *new_bundles)
    fingerprint = registry_plugin_fingerprint(registry, bundles)
    registry.set_python_plugin_catalog(tuple(bundles), plugin_fingerprint=fingerprint)
    return PluginDiscoveryResult(tuple(loaded), tuple(bundles), fingerprint)


def discover_static_plugins(
    registry: NodeRegistry,
    *,
    roots: Sequence[Path],
    generation_root: Path,
) -> PluginDiscoveryResult:
    return _discover_static_plugins(
        registry,
        roots=roots,
        generation_root=generation_root,
        strict=False,
    )


def discover_static_plugin_candidate(
    registry: NodeRegistry,
    *,
    roots: Sequence[Path],
    generation_root: Path,
    staged_package_root: Path | None = None,
) -> PluginDiscoveryResult:
    """Build one fail-closed public-plugin candidate without executing source."""

    return _discover_static_plugins(
        registry,
        roots=roots,
        generation_root=generation_root,
        strict=True,
        staged_package_root=staged_package_root,
    )


def discover_configured_static_plugins(
    registry: NodeRegistry,
    extra_dirs: list[Path] | None = None,
    *,
    generation_root: Path | None = None,
) -> list[str]:
    result = discover_static_plugins(
        registry,
        roots=(plugins_dir(), *(extra_dirs or ())),
        generation_root=generation_root or plugin_generations_dir(),
    )
    if result.type_ids:
        logger.info(
            "Loaded %d plugin node(s): %s",
            len(result.type_ids),
            ", ".join(result.type_ids),
        )
    return list(result.type_ids)
