# Purpose: Validate schema-2 node-package manifests, members, and declarations.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_package_manager.py, tests/test_plugin_loader.py

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from ea_node_editor.common.path_safety import is_reparse_point
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.plugin_declaration import (
    PythonFunctionDeclaration,
    discover_plugin_declarations,
)

MANIFEST_FILENAME = "node_package.json"
PLUGIN_MANIFEST_LIMIT = 64 * 1024
PLUGIN_SOURCE_LIMIT = 256 * 1024
PLUGIN_ASSET_LIMIT = 4 * 1024 * 1024
PLUGIN_MEMBER_LIMIT = 128
PLUGIN_TOTAL_LIMIT = 16 * 1024 * 1024
PLUGIN_ASSET_SUFFIXES = frozenset({".svg", ".png", ".jpg", ".jpeg"})
PLUGIN_REGULAR_FILE_MESSAGE = (
    "Plugin members must be regular files with exactly one link"
)
SCHEMA_1_UNSUPPORTED_MESSAGE = (
    "Node package schema 1 is unsupported. Use schema 2; see "
    "docs/PLUGIN_MIGRATION_GUIDE.md#node-package-schema-1."
)

_PACKAGE_PATH_ENTRY_LIMIT = 256
_REQUIRED_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "name",
        "version",
        "modules",
        "sources",
        "assets",
        "nodes",
    }
)
_ALLOWED_MANIFEST_FIELDS = _REQUIRED_MANIFEST_FIELDS | {"author", "description"}
_SHA256_LENGTH = 64
_WINDOWS_RESERVED_NAMES = frozenset(
    {"aux", "con", "conin$", "conout$", "nul", "prn"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
    | {f"com{index}" for index in ("¹", "²", "³")}
    | {f"lpt{index}" for index in ("¹", "²", "³")}
)

PackageMemberRecord = tuple[str, str]
PackageNodeRecord = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class ValidatedPackageManifest:
    manifest: dict[str, object]
    name: str
    version: str
    modules: tuple[str, ...]
    sources: tuple[PackageMemberRecord, ...]
    assets: tuple[PackageMemberRecord, ...]
    nodes: tuple[PackageNodeRecord, ...]


@dataclass(frozen=True, slots=True)
class ValidatedPackage:
    schema: ValidatedPackageManifest
    members: dict[str, bytes]

    @property
    def manifest(self) -> dict[str, object]:
        return self.schema.manifest


def validate_plugin_regular_file(path: Path) -> os.stat_result:
    try:
        file_status = path.stat()
    except OSError as exc:
        raise ValueError(PLUGIN_REGULAR_FILE_MESSAGE) from exc
    if not stat.S_ISREG(file_status.st_mode) or file_status.st_nlink != 1:
        raise ValueError(PLUGIN_REGULAR_FILE_MESSAGE)
    return file_status


def validated_plugin_member_path(
    value: object,
    *,
    root_python: bool = False,
) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError("plugin members must use trimmed string paths")
    text = value
    path = PurePosixPath(text)
    windows_path = PureWindowsPath(text)
    if (
        not text
        or "\\" in text
        or ":" in text
        or path.is_absolute()
        or windows_path.drive
        or windows_path.root
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(
            part.endswith((" ", "."))
            or any(ord(character) < 32 or character in '<>"|?*' for character in part)
            or part.partition(".")[0].casefold() in _WINDOWS_RESERVED_NAMES
            for part in path.parts
        )
        or (root_python and (len(path.parts) != 1 or path.suffix != ".py"))
    ):
        raise ValueError("generation members must use canonical relative paths")
    return text


def canonical_manifest_bytes(manifest: Mapping[str, object]) -> bytes:
    return json.dumps(
        dict(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_bundle_digest(
    manifest: Mapping[str, object],
    members: Mapping[str, bytes],
) -> str:
    normalized = {
        validated_plugin_member_path(path): bytes(payload)
        for path, payload in members.items()
    }
    digest = hashlib.sha256(canonical_manifest_bytes(manifest))
    for path in sorted(normalized):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(normalized[path])
    return digest.hexdigest()


def _trimmed(field_name: str, value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError(f"{field_name} must be a trimmed string")
    if not value and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    return value


def validated_package_name(value: object, *, field_name: str = "Package name") -> str:
    candidate = validated_plugin_member_path(_trimmed(field_name, value))
    if len(PurePosixPath(candidate).parts) != 1 or candidate.startswith((".", "_")):
        raise ValueError(f"{field_name} must be a safe visible directory name")
    return candidate


def _sha256(field_name: str, value: object) -> str:
    text = _trimmed(field_name, value)
    if len(text) != _SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return text


def _manifest_records(
    manifest: Mapping[str, object],
    field_name: str,
    *,
    asset: bool,
) -> tuple[PackageMemberRecord, ...]:
    raw_records = manifest.get(field_name)
    if not isinstance(raw_records, list):
        raise ValueError(f"Manifest {field_name} must be a list")
    records: list[PackageMemberRecord] = []
    seen: set[str] = set()
    for raw_record in raw_records:
        if not isinstance(raw_record, dict) or set(raw_record) != {"path", "sha256"}:
            raise ValueError(f"Manifest {field_name} entries require path and sha256")
        path = validated_plugin_member_path(
            raw_record["path"],
            root_python=not asset,
        )
        if asset and PurePosixPath(path).suffix.lower() not in PLUGIN_ASSET_SUFFIXES:
            raise ValueError(f"Unsupported plugin asset: {path}")
        folded = path.casefold()
        if folded in seen:
            raise ValueError(f"Manifest {field_name} paths must be unique")
        seen.add(folded)
        records.append((path, _sha256(f"{field_name} sha256", raw_record["sha256"])))
    return tuple(records)


def _manifest_nodes(manifest: Mapping[str, object]) -> tuple[PackageNodeRecord, ...]:
    raw_nodes = manifest.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("Manifest nodes must be a list")
    nodes: list[PackageNodeRecord] = []
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict) or set(raw_node) != {
            "id",
            "module",
            "function",
        }:
            raise ValueError("Manifest node entries require id, module, and function")
        nodes.append(
            (
                _trimmed("node id", raw_node["id"]),
                validated_plugin_member_path(raw_node["module"], root_python=True),
                _trimmed("node function", raw_node["function"]),
            )
        )
    if len(nodes) != len(set(nodes)):
        raise ValueError("Manifest node entries must be unique")
    return tuple(nodes)


def validate_package_manifest(
    raw_manifest: object,
    *,
    expected_name: str | None = None,
) -> ValidatedPackageManifest:
    if not isinstance(raw_manifest, Mapping):
        raise ValueError("Plugin package manifest must be a JSON object")
    manifest = dict(raw_manifest)
    schema_version = manifest.get("schema_version")
    if schema_version is None or (type(schema_version) is int and schema_version == 1):
        raise ValueError(SCHEMA_1_UNSUPPORTED_MESSAGE)
    if type(schema_version) is not int or schema_version != 2:
        raise ValueError("Only node package schema 2 is supported")
    if set(manifest) - _ALLOWED_MANIFEST_FIELDS:
        raise ValueError("Plugin package manifest contains unknown fields")
    if _REQUIRED_MANIFEST_FIELDS - set(manifest):
        raise ValueError("Plugin package manifest is missing required fields")

    name = validated_package_name(manifest["name"], field_name="Manifest name")
    if expected_name is not None and expected_name != name:
        raise ValueError("Installed package directory must match manifest name")
    version = _trimmed("Manifest version", manifest["version"])
    for optional_field in ("author", "description"):
        if optional_field in manifest:
            _trimmed(optional_field, manifest[optional_field], allow_empty=True)

    raw_modules = manifest["modules"]
    if not isinstance(raw_modules, list) or not raw_modules:
        raise ValueError("Manifest modules must be a non-empty list")
    modules = tuple(
        validated_plugin_member_path(value, root_python=True) for value in raw_modules
    )
    if len({module.casefold() for module in modules}) != len(modules):
        raise ValueError("Manifest modules must be unique")

    sources = _manifest_records(manifest, "sources", asset=False)
    assets = _manifest_records(manifest, "assets", asset=True)
    source_paths = {path for path, _digest in sources}
    if not set(modules) <= source_paths:
        raise ValueError("Manifest modules must be declared sources")
    folded_paths = [path.casefold() for path, _digest in (*sources, *assets)]
    if len(folded_paths) != len(set(folded_paths)):
        raise ValueError("Manifest member paths must be unique")
    if len(folded_paths) + 1 > PLUGIN_MEMBER_LIMIT:
        raise ValueError("Plugin package contains too many members")

    return ValidatedPackageManifest(
        manifest=manifest,
        name=name,
        version=version,
        modules=modules,
        sources=sources,
        assets=assets,
        nodes=_manifest_nodes(manifest),
    )


def validate_package_members(
    schema: ValidatedPackageManifest,
    members: Mapping[str, bytes],
    *,
    manifest_size: int | None = None,
    verify_hashes: bool = True,
) -> ValidatedPackage:
    if not isinstance(schema, ValidatedPackageManifest):
        raise TypeError("schema must be a ValidatedPackageManifest")
    normalized = {
        validated_plugin_member_path(path): bytes(payload)
        for path, payload in members.items()
    }
    records = (*schema.sources, *schema.assets)
    declared_paths = {path for path, _digest in records}
    if set(normalized) != declared_paths:
        raise ValueError("Plugin package contains undeclared members")

    expanded_size = (
        len(canonical_manifest_bytes(schema.manifest))
        if manifest_size is None
        else int(manifest_size)
    )
    if expanded_size > PLUGIN_MANIFEST_LIMIT:
        raise ValueError("Plugin package manifest is too large")
    if expanded_size > PLUGIN_TOTAL_LIMIT:
        raise ValueError("Plugin package expanded size is too large")
    asset_paths = {path for path, _digest in schema.assets}
    for path, expected_digest in records:
        payload = normalized[path]
        limit = PLUGIN_ASSET_LIMIT if path in asset_paths else PLUGIN_SOURCE_LIMIT
        if len(payload) > limit:
            raise ValueError(f"Declared package member {path} is too large")
        expanded_size += len(payload)
        if expanded_size > PLUGIN_TOTAL_LIMIT:
            raise ValueError("Plugin package expanded size is too large")
        if verify_hashes and hashlib.sha256(payload).hexdigest() != expected_digest:
            raise ValueError(f"Plugin package hash mismatch: {path}")
    return ValidatedPackage(schema=schema, members=normalized)


def validated_package_declarations(
    package: ValidatedPackage,
    *,
    filename_prefix: str,
    owner_id: str = "",
    allow_internal_metadata: bool = False,
    require_declared_icons: bool = False,
) -> tuple[tuple[str, PythonFunctionDeclaration], ...]:
    declarations: list[tuple[str, PythonFunctionDeclaration]] = []
    for path in package.schema.modules:
        try:
            source = package.members[path].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Plugin source is not UTF-8: {path}") from exc
        declarations.extend(
            (path, declaration)
            for declaration in discover_plugin_declarations(
                source,
                filename=f"{filename_prefix}:{path}",
                allow_reserved_ids=(
                    owner_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID
                    or allow_internal_metadata
                ),
                owner_id=owner_id,
                allow_internal_metadata=allow_internal_metadata,
            )
        )

    validated = tuple(declarations)
    validate_package_declaration_inventory(
        package,
        validated,
        require_declared_icons=require_declared_icons,
    )
    return validated


def validate_package_declaration_inventory(
    package: ValidatedPackage,
    declarations: tuple[tuple[str, PythonFunctionDeclaration], ...],
    *,
    require_declared_icons: bool = False,
) -> None:
    type_ids = [declaration.spec.type_id for _path, declaration in declarations]
    if len(type_ids) != len(set(type_ids)):
        raise ValueError("Plugin bundle contains duplicate node ids")
    discovered = {
        (declaration.spec.type_id, path, declaration.function_name)
        for path, declaration in declarations
    }
    if discovered != set(package.schema.nodes):
        raise ValueError("Manifest nodes do not match static declarations")

    if not require_declared_icons:
        return
    asset_paths = {path for path, _digest in package.schema.assets}
    for _path, declaration in declarations:
        icon = declaration.spec.icon
        if not icon:
            continue
        try:
            icon_path = validated_plugin_member_path(icon)
        except ValueError as exc:
            raise ValueError(f"Plugin node icon path is invalid: {icon}") from exc
        if icon_path not in asset_paths:
            raise ValueError(f"Plugin node icon is not a declared asset: {icon_path}")


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


def _read_package_member(package_dir: Path, relative_path: str, *, limit: int) -> bytes:
    target = package_dir / relative_path
    cursor = package_dir
    for part in PurePosixPath(relative_path).parts:
        cursor /= part
        if is_reparse_point(cursor):
            raise ValueError("Plugin package may not contain path aliases")
    if not target.is_file():
        raise ValueError(f"Declared package member is unavailable: {relative_path}")
    validate_plugin_regular_file(target)
    try:
        target.resolve().relative_to(package_dir.resolve())
    except ValueError as exc:
        raise ValueError("Declared package member escapes the package root") from exc
    return _read_bounded(
        target,
        limit=limit,
        label=f"Declared package member {relative_path}",
    )


def read_validated_package_directory(package_dir: Path) -> ValidatedPackage:
    package_dir = Path(package_dir)
    if is_reparse_point(package_dir) or not package_dir.is_dir():
        raise ValueError("Installed plugin package must be a regular directory")
    manifest_path = package_dir / MANIFEST_FILENAME
    if not manifest_path.is_file() or is_reparse_point(manifest_path):
        raise ValueError(f"Installed plugin package requires {MANIFEST_FILENAME}")
    validate_plugin_regular_file(manifest_path)
    raw_manifest = _read_bounded(
        manifest_path,
        limit=PLUGIN_MANIFEST_LIMIT,
        label="Plugin package manifest",
    )
    try:
        manifest = json.loads(raw_manifest)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Plugin package manifest is not valid UTF-8 JSON") from exc
    schema = validate_package_manifest(manifest, expected_name=package_dir.name)

    members: dict[str, bytes] = {}
    expanded_size = len(raw_manifest)
    if expanded_size > PLUGIN_TOTAL_LIMIT:
        raise ValueError("Plugin package expanded size is too large")
    asset_paths = {path for path, _digest in schema.assets}
    for path, _expected_digest in (*schema.sources, *schema.assets):
        try:
            declared_size = (package_dir / path).stat().st_size
        except OSError as exc:
            raise ValueError(f"Declared package member is unavailable: {path}") from exc
        if expanded_size + declared_size > PLUGIN_TOTAL_LIMIT:
            raise ValueError("Plugin package expanded size is too large")
        payload = _read_package_member(
            package_dir,
            path,
            limit=PLUGIN_ASSET_LIMIT if path in asset_paths else PLUGIN_SOURCE_LIMIT,
        )
        if expanded_size + len(payload) > PLUGIN_TOTAL_LIMIT:
            raise ValueError("Plugin package expanded size is too large")
        members[path] = payload
        expanded_size += len(payload)

    declared_files = {MANIFEST_FILENAME, *members}
    actual_files: set[str] = set()
    for index, path in enumerate(package_dir.rglob("*")):
        if index >= _PACKAGE_PATH_ENTRY_LIMIT:
            raise ValueError("Plugin package contains too many path entries")
        if is_reparse_point(path):
            raise ValueError("Plugin package may not contain symlinks")
        if path.is_file():
            actual_files.add(path.relative_to(package_dir).as_posix())
    if actual_files != declared_files:
        raise ValueError("Plugin package contains undeclared members")
    return validate_package_members(schema, members, manifest_size=len(raw_manifest))


__all__ = [
    "MANIFEST_FILENAME",
    "PLUGIN_ASSET_LIMIT",
    "PLUGIN_ASSET_SUFFIXES",
    "PLUGIN_MANIFEST_LIMIT",
    "PLUGIN_MEMBER_LIMIT",
    "PLUGIN_REGULAR_FILE_MESSAGE",
    "PLUGIN_SOURCE_LIMIT",
    "PLUGIN_TOTAL_LIMIT",
    "SCHEMA_1_UNSUPPORTED_MESSAGE",
    "ValidatedPackage",
    "ValidatedPackageManifest",
    "canonical_bundle_digest",
    "canonical_manifest_bytes",
    "read_validated_package_directory",
    "validate_package_manifest",
    "validate_package_members",
    "validate_package_declaration_inventory",
    "validate_plugin_regular_file",
    "validated_package_declarations",
    "validated_package_name",
    "validated_plugin_member_path",
]
