# Purpose: Prepare, materialize, and fingerprint in-memory function bundle data.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_function_bundle.py, tests/test_builtin_function_infrastructure.py

from __future__ import annotations

import ast
import hashlib
import importlib.machinery
import importlib.util
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ea_node_editor.nodes.function_plugin import (
    PluginBundleRef,
    PythonFunctionRef,
    plugin_fingerprint as function_plugin_fingerprint,
)
from ea_node_editor.nodes.plugin_contracts import PluginProvenance
from ea_node_editor.nodes.plugin_declaration import (
    PythonFunctionDeclaration,
    discover_plugin_declarations,
)
from ea_node_editor.nodes.plugin_generation import materialize_plugin_generation
from ea_node_editor.nodes.package_schema import canonical_bundle_digest
from ea_node_editor.nodes.registry import NodeRegistry, PythonFunctionEntry

_SAFE_SEGMENT = re.compile(r"[^0-9A-Za-z_]+")
_PLUGIN_LOG_LABEL_LENGTH = 256
_BUNDLED_MODULE_ROOTS = frozenset(
    {
        "OCP",
        "PyQt6",
        "ansys",
        "corex",
        "duckdb",
        "ea_node_editor",
        "h5py",
        "imageio_ffmpeg",
        "llvmlite",
        "matplotlib",
        "numba",
        "numpy",
        "openpyxl",
        "pandas",
        "paramiko",
        "polars",
        "psutil",
        "pyarrow",
        "pyqtgraph",
        "pyvista",
        "pyvistaqt",
        "qtpy",
        "scipy",
        "tables",
        "vtkmodules",
        "xy",
    }
)


@dataclass(frozen=True, slots=True)
class PreparedFunctionBundle:
    owner_id: str
    version: str
    manifest: dict[str, object]
    members: dict[str, bytes]
    declarations: tuple[tuple[str, PythonFunctionDeclaration], ...]
    unavailable_reason: str
    log_label: str
    source_root: Path
    package_name: str = ""


def safe_bundle_segment(value: object, *, fallback: str) -> str:
    segment = _SAFE_SEGMENT.sub("_", str(value)).strip("_")
    if not segment:
        return fallback
    return f"_{segment}" if segment[0].isdigit() else segment


def bounded_bundle_log_label(value: object) -> str:
    text = str(value or "")
    if (
        text
        and len(text) <= _PLUGIN_LOG_LABEL_LENGTH
        and all(character.isalnum() or character in "._:@+-" for character in text)
    ):
        return text
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"plugin:opaque:{digest}"


def source_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def module_declarations(
    manifest: Mapping[str, object],
    members: Mapping[str, bytes],
    *,
    filename_prefix: str,
    owner_id: str = "",
    allow_internal_metadata: bool = False,
    allow_reserved_ids: bool = False,
) -> tuple[tuple[str, PythonFunctionDeclaration], ...]:
    declarations: list[tuple[str, PythonFunctionDeclaration]] = []
    for module_path in manifest["modules"]:  # type: ignore[union-attr]
        path = str(module_path)
        try:
            source = members[path].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Plugin source is not UTF-8: {path}") from exc
        parsed = discover_plugin_declarations(
            source,
            filename=f"{filename_prefix}:{path}",
            allow_reserved_ids=allow_reserved_ids,
            owner_id=owner_id,
            allow_internal_metadata=allow_internal_metadata,
        )
        declarations.extend((path, declaration) for declaration in parsed)
    return tuple(declarations)


def node_inventory(
    declarations: Sequence[tuple[str, PythonFunctionDeclaration]],
) -> list[dict[str, str]]:
    return [
        {
            "id": declaration.spec.type_id,
            "module": module_path,
            "function": declaration.function_name,
        }
        for module_path, declaration in declarations
    ]


def _pathfinder_module_available(module_name: str) -> bool:
    try:
        parts = module_name.split(".")
        qualified_name = parts[0]
        spec = importlib.machinery.PathFinder.find_spec(qualified_name)
        for part in parts[1:]:
            if spec is None or spec.submodule_search_locations is None:
                return False
            qualified_name = f"{qualified_name}.{part}"
            spec = importlib.machinery.PathFinder.find_spec(
                qualified_name,
                spec.submodule_search_locations,
            )
        return spec is not None
    except (ImportError, AttributeError, ValueError):
        return False


def bundled_module_available(module_name: str) -> bool:
    if module_name in {"corex", "__future__"}:
        return True
    root = module_name.partition(".")[0]
    if root in sys.builtin_module_names:
        return module_name == root
    if root in getattr(sys, "stdlib_module_names", ()):
        return module_name == root or _pathfinder_module_available(module_name)
    if root not in _BUNDLED_MODULE_ROOTS:
        return False
    if getattr(sys, "frozen", False):
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, AttributeError, ValueError):
            return False
    return _pathfinder_module_available(module_name)


def missing_bundle_imports(
    members: Mapping[str, bytes],
    source_paths: set[str],
) -> tuple[str, ...]:
    source_stems = {PurePosixPath(path).stem for path in source_paths}
    missing: set[str] = set()
    for source_path in sorted(source_paths):
        try:
            tree = ast.parse(members[source_path].decode("utf-8"), filename=source_path)
        except (UnicodeDecodeError, SyntaxError) as exc:
            raise ValueError(f"Plugin source cannot be parsed: {source_path}") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.partition(".")[0]
                    bundled_source = alias.name == root and root in source_stems
                    if not bundled_source and not bundled_module_available(alias.name):
                        missing.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if node.level != 1:
                        missing.add(node.module or node.names[0].name)
                        continue
                    if node.module:
                        relative_source = f"{node.module.replace('.', '/')}.py"
                        if relative_source not in source_paths:
                            missing.add(node.module)
                    else:
                        for alias in node.names:
                            relative_source = f"{alias.name}.py"
                            if relative_source not in source_paths:
                                missing.add(alias.name)
                    continue
                root = (node.module or "").partition(".")[0]
                module_name = node.module or ""
                bundled_source = module_name == root and root in source_stems
                if (
                    module_name
                    and not bundled_source
                    and not bundled_module_available(module_name)
                ):
                    missing.add(module_name)
    return tuple(sorted(missing))


def materialize_prepared_function_bundle(
    prepared: PreparedFunctionBundle,
    generation_root: Path,
) -> tuple[PluginBundleRef, Path]:
    bundle_digest = canonical_bundle_digest(prepared.manifest, prepared.members)
    function_refs = tuple(
        PythonFunctionRef(
            bundle_id=prepared.owner_id,
            bundle_digest=bundle_digest,
            module_relative_path=module_path,
            function_name=declaration.function_name,
            source_digest=source_digest(prepared.members[module_path]),
            is_async=declaration.is_async,
        )
        for module_path, declaration in prepared.declarations
    )
    generation = materialize_plugin_generation(
        generation_root,
        bundle_digest=bundle_digest,
        manifest=prepared.manifest,
        members=prepared.members,
    )
    bundle_ref = PluginBundleRef(
        owner_id=prepared.owner_id,
        version=prepared.version,
        generation_id=bundle_digest,
        bundle_digest=bundle_digest,
        approved_generation_root=str(generation),
        functions=function_refs,
        unavailable_reason=prepared.unavailable_reason,
    )
    return bundle_ref, generation


def build_function_entries(
    prepared: PreparedFunctionBundle,
    bundle: PluginBundleRef,
    provenance_by_module: Mapping[str, PluginProvenance | None],
) -> tuple[PythonFunctionEntry, ...]:
    module_paths = tuple(path for path, _declaration in prepared.declarations)
    if set(provenance_by_module) != set(module_paths):
        raise ValueError("Function entry provenance must cover every declared module")
    return tuple(
        PythonFunctionEntry(
            spec=declaration.spec,
            function_ref=function_ref,
            provenance=provenance_by_module[module_path],
            owner_id=prepared.owner_id,
            unavailable_reason=prepared.unavailable_reason,
        )
        for (module_path, declaration), function_ref in zip(
            prepared.declarations,
            bundle.functions,
            strict=True,
        )
    )


def registry_plugin_fingerprint(
    registry: NodeRegistry,
    bundles: Sequence[PluginBundleRef],
) -> str:
    entries = tuple(
        (spec, function_ref)
        for spec in registry.all_specs()
        if (function_ref := registry.python_function_ref_or_none(spec.type_id))
        is not None
    )
    return function_plugin_fingerprint(entries, bundles)


__all__ = [
    "PreparedFunctionBundle",
    "build_function_entries",
    "bounded_bundle_log_label",
    "bundled_module_available",
    "materialize_prepared_function_bundle",
    "missing_bundle_imports",
    "module_declarations",
    "node_inventory",
    "registry_plugin_fingerprint",
    "safe_bundle_segment",
    "source_digest",
]
