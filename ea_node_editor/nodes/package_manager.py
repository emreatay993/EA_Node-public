# Purpose: Import and export deterministic schema-2 public-function node packages.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_package_manager.py

"""Validated, non-executing ``.cxpkg`` schema-2 package IO."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import stat
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from uuid import uuid4

from ea_node_editor.common.path_safety import is_reparse_point
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.package_schema import (
    MANIFEST_FILENAME,
    PLUGIN_ASSET_LIMIT,
    PLUGIN_ASSET_SUFFIXES,
    PLUGIN_MANIFEST_LIMIT,
    PLUGIN_MEMBER_LIMIT,
    PLUGIN_SOURCE_LIMIT,
    PLUGIN_TOTAL_LIMIT,
    SCHEMA_1_UNSUPPORTED_MESSAGE,
    ValidatedPackage,
    canonical_manifest_bytes,
    read_validated_package_directory,
    validate_package_declaration_inventory,
    validate_package_manifest,
    validate_package_members,
    validate_plugin_regular_file,
    validated_package_declarations,
    validated_package_name,
    validated_plugin_member_path,
)
from ea_node_editor.settings import plugins_dir

logger = logging.getLogger(__name__)

PACKAGE_EXTENSION = ".cxpkg"
_ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_HIDDEN_PACKAGE_PREFIXES = (".", "_")
_IMPORT_FILESYSTEM_ERROR = "Package import failed [filesystem]"
_EXPORT_FILESYSTEM_ERROR = "Package export failed [filesystem]"
_CLEANUP_CODES = frozenset(
    {"activation_backup", "export_archive", "export_validation", "import_staging"}
)


@dataclass(slots=True)
class PackageManifest:
    """Package metadata plus the validated generated inventory."""

    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    nodes: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)
    assets: list[dict[str, str]] = field(default_factory=list)
    schema_version: int = 2


class PackageInstallState(str, Enum):
    """Observable states for a reversible package installation."""

    STAGED = "staged"
    ACTIVATED = "activated"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass(slots=True)
class PackageInstallTransaction:
    """One validated package staged for reversible activation."""

    manifest: PackageManifest
    staged_package_root: Path
    installed_package_root: Path
    _container: Path = field(repr=False)
    _manifest_bytes: bytes = field(repr=False)
    _state: PackageInstallState = field(
        default=PackageInstallState.STAGED,
        init=False,
        repr=False,
    )
    _backup_root: Path | None = field(default=None, init=False, repr=False)
    _activation_completed: bool = field(default=False, init=False, repr=False)
    _had_previous_install: bool = field(default=False, init=False, repr=False)
    _rollback_filesystem_restored: bool = field(default=False, init=False, repr=False)
    _issues: tuple[str, ...] = field(default=(), init=False, repr=False)

    @property
    def state(self) -> PackageInstallState:
        return self._state

    @property
    def issues(self) -> tuple[str, ...]:
        """Stable, path-free codes for unresolved transaction work."""

        return self._issues

    def _require(self, action: str, *states: PackageInstallState) -> None:
        if self._state not in states:
            raise RuntimeError(
                f"Cannot {action} package install transaction from state "
                f"'{self._state.value}'"
            )

    def _fail(self, *issues: str) -> None:
        self._state = PackageInstallState.FAILED
        self._issues = tuple(dict.fromkeys(issues))
        raise RuntimeError(
            f"Package install rollback failed [{','.join(self._issues)}]"
        )

    def activate(self) -> None:
        """Publish the staged package while retaining any previous install."""

        if self._state is PackageInstallState.ACTIVATED:
            return
        self._require("activate", PackageInstallState.STAGED)
        self._issues = ()
        backup_root: Path | None = None
        try:
            current_manifest = _validated_package_directory(self.staged_package_root)
            if canonical_manifest_bytes(current_manifest) != self._manifest_bytes:
                raise ValueError("Staged package changed after validation")
            if self.installed_package_root.exists() or is_reparse_point(
                self.installed_package_root
            ):
                if is_reparse_point(
                    self.installed_package_root
                ) or not self.installed_package_root.is_dir():
                    raise ValueError(
                        "Installed package target is not a regular directory"
                    )
                backup_root = _temporary_container(
                    self.installed_package_root.parent,
                    self.installed_package_root.name,
                    kind="backup",
                )
                self.installed_package_root.replace(backup_root)
                self._backup_root = backup_root
                self._had_previous_install = True
            try:
                self.staged_package_root.replace(self.installed_package_root)
            except OSError:
                if backup_root is not None and not self.installed_package_root.exists():
                    try:
                        backup_root.replace(self.installed_package_root)
                    except OSError:
                        self._state = PackageInstallState.FAILED
                        self._issues = ("activation_prior_restore",)
                        raise OSError("package activation rollback failed") from None
                    self._backup_root = None
                raise
        except OSError:
            raise ValueError(_IMPORT_FILESYSTEM_ERROR) from None
        self._activation_completed = True
        self._state = PackageInstallState.ACTIVATED

    def commit(self) -> None:
        """Make the activated install final and remove retained staging."""

        if self._state is PackageInstallState.COMMITTED:
            self._cleanup_retained_paths()
            return
        self._require("commit", PackageInstallState.ACTIVATED)
        self._state = PackageInstallState.COMMITTED
        self._cleanup_retained_paths()

    def rollback(self) -> None:
        """Restore the exact install state that existed before staging."""

        if self._state is PackageInstallState.ROLLED_BACK:
            return
        self._require(
            "roll back",
            PackageInstallState.STAGED,
            PackageInstallState.ACTIVATED,
            PackageInstallState.FAILED,
        )
        self._issues = ()
        if self._rollback_filesystem_restored:
            self._finish_rollback()
            return

        backup_root = self._backup_root
        if not self._activation_completed:
            if backup_root is not None:
                if self.installed_package_root.exists() or is_reparse_point(
                    self.installed_package_root
                ):
                    self._fail("rollback_installed_state")
                if is_reparse_point(backup_root) or not backup_root.is_dir():
                    self._fail("rollback_backup_state")
                try:
                    backup_root.replace(self.installed_package_root)
                except OSError:
                    self._fail("rollback_prior_restore")
                self._backup_root = None
            self._finish_rollback()
            return

        if self._had_previous_install and backup_root is None:
            if is_reparse_point(
                self.installed_package_root
            ) or not self.installed_package_root.is_dir():
                self._fail("rollback_prior_state")
        else:
            installed_exists = self.installed_package_root.exists() or is_reparse_point(
                self.installed_package_root
            )
            staged_exists = self.staged_package_root.exists() or is_reparse_point(
                self.staged_package_root
            )
            if installed_exists:
                if is_reparse_point(
                    self.installed_package_root
                ) or not self.installed_package_root.is_dir():
                    self._fail("rollback_installed_state")
                if staged_exists:
                    self._fail("rollback_staging_state")
                try:
                    self.installed_package_root.replace(self.staged_package_root)
                except OSError:
                    self._fail("rollback_active_move")
            elif is_reparse_point(
                self.staged_package_root
            ) or not self.staged_package_root.is_dir():
                self._fail("rollback_staging_state")

            if self._had_previous_install:
                if backup_root is None or is_reparse_point(
                    backup_root
                ) or not backup_root.is_dir():
                    self._fail("rollback_backup_state")
                try:
                    backup_root.replace(self.installed_package_root)
                except OSError:
                    issues = ["rollback_prior_restore"]
                    try:
                        self.staged_package_root.replace(self.installed_package_root)
                    except OSError:
                        issues.append("rollback_active_restore")
                    self._fail(*issues)
                self._backup_root = None

        self._finish_rollback()

    def _finish_rollback(self) -> None:
        self._rollback_filesystem_restored = True
        if not _cleanup_path(self._container, code="import_staging"):
            self._fail("rollback_staging_cleanup")
        self._state = PackageInstallState.ROLLED_BACK
        self._issues = ()

    def _cleanup_retained_paths(self) -> None:
        issues: list[str] = []
        if self._backup_root is not None:
            if _cleanup_path(self._backup_root, code="activation_backup"):
                self._backup_root = None
            else:
                issues.append("commit_backup_cleanup")
        if not _cleanup_path(self._container, code="import_staging"):
            issues.append("commit_staging_cleanup")
        self._issues = tuple(issues)


@dataclass(frozen=True, slots=True)
class PackageExportSource:
    source_path: Path
    archive_name: str | None = None


@dataclass(frozen=True, slots=True)
class PackageExportAsset:
    source_path: Path
    archive_name: str | None = None


@dataclass(frozen=True, slots=True)
class _ExportMember:
    path: str
    payload: bytes
    is_asset: bool


def _read_local_member(path: Path, *, limit: int, label: str) -> bytes:
    if is_reparse_point(path) or not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    member_status = validate_plugin_regular_file(path)
    try:
        if member_status.st_size > limit:
            raise ValueError(f"{label} is too large")
        with path.open("rb") as stream:
            payload = stream.read(limit + 1)
    except OSError as exc:
        raise ValueError(f"{label} cannot be read") from exc
    if len(payload) > limit:
        raise ValueError(f"{label} is too large")
    return payload


def _export_source(value: PackageExportSource | Path | str) -> _ExportMember:
    item = value if isinstance(value, PackageExportSource) else PackageExportSource(Path(value))
    source_path = Path(item.source_path)
    archive_name = validated_plugin_member_path(
        item.archive_name or source_path.name,
        root_python=True,
    )
    if archive_name == MANIFEST_FILENAME:
        raise ValueError(f"{MANIFEST_FILENAME} is reserved for the package manifest")
    return _ExportMember(
        path=archive_name,
        payload=_read_local_member(
            source_path,
            limit=PLUGIN_SOURCE_LIMIT,
            label=f"Package source {archive_name}",
        ),
        is_asset=False,
    )


def _export_asset(value: PackageExportAsset | Path | str) -> _ExportMember:
    item = value if isinstance(value, PackageExportAsset) else PackageExportAsset(Path(value))
    source_path = Path(item.source_path)
    archive_name = validated_plugin_member_path(item.archive_name or source_path.name)
    if PurePosixPath(archive_name).suffix.lower() not in PLUGIN_ASSET_SUFFIXES:
        raise ValueError(f"Unsupported package asset: {archive_name}")
    return _ExportMember(
        path=archive_name,
        payload=_read_local_member(
            source_path,
            limit=PLUGIN_ASSET_LIMIT,
            label=f"Package asset {archive_name}",
        ),
        is_asset=True,
    )


def _export_payload(
    source_files: list[PackageExportSource | Path | str],
    assets: list[PackageExportAsset | Path | str],
    manifest: PackageManifest,
) -> ValidatedPackage:
    if not source_files:
        raise ValueError("Package export requires at least one Python source file")
    if not isinstance(manifest, PackageManifest):
        raise TypeError("manifest must be a PackageManifest")
    if type(manifest.schema_version) is not int or manifest.schema_version != 2:
        raise ValueError("Package export requires schema_version 2")
    if len(source_files) + len(assets) + 1 > PLUGIN_MEMBER_LIMIT:
        raise ValueError("Plugin package contains too many members")

    normalized = [*map(_export_source, source_files), *map(_export_asset, assets)]
    folded_paths = [member.path.casefold() for member in normalized]
    if len(folded_paths) != len(set(folded_paths)):
        raise ValueError("Package export members must be unique on Windows")

    members = {member.path: member.payload for member in normalized}
    total_size = sum(len(payload) for payload in members.values())
    if total_size > PLUGIN_TOTAL_LIMIT:
        raise ValueError("Plugin package expanded size is too large")

    modules: list[str] = []
    node_inventory: list[dict[str, str]] = []
    declarations_by_module = []
    for member in sorted(
        (item for item in normalized if not item.is_asset),
        key=lambda item: item.path,
    ):
        try:
            source = member.payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Plugin source is not UTF-8: {member.path}") from exc
        declarations = discover_plugin_declarations(
            source,
            filename=f"{manifest.name}:{member.path}",
        )
        if declarations:
            modules.append(member.path)
        for declaration in declarations:
            declarations_by_module.append((member.path, declaration))
            node_inventory.append(
                {
                    "id": declaration.spec.type_id,
                    "module": member.path,
                    "function": declaration.function_name,
                }
            )
    if not node_inventory:
        raise ValueError("Package export requires at least one declared node function")
    node_inventory.sort(key=lambda item: (item["id"], item["module"], item["function"]))
    discovered_node_ids = [item["id"] for item in node_inventory]
    if len(discovered_node_ids) != len(set(discovered_node_ids)):
        raise ValueError("Package export contains duplicate node ids")
    if manifest.nodes and (
        len(manifest.nodes) != len(set(manifest.nodes))
        or set(manifest.nodes) != set(discovered_node_ids)
    ):
        raise ValueError("Package manifest nodes do not match static declarations")

    source_records = [
        {"path": member.path, "sha256": hashlib.sha256(member.payload).hexdigest()}
        for member in sorted(
            (item for item in normalized if not item.is_asset),
            key=lambda item: item.path,
        )
    ]
    asset_records = [
        {"path": member.path, "sha256": hashlib.sha256(member.payload).hexdigest()}
        for member in sorted(
            (item for item in normalized if item.is_asset),
            key=lambda item: item.path,
        )
    ]
    package_manifest: dict[str, object] = {
        "schema_version": 2,
        "name": validated_package_name(manifest.name),
        "version": manifest.version,
        "author": manifest.author,
        "description": manifest.description,
        "modules": sorted(modules),
        "sources": source_records,
        "assets": asset_records,
        "nodes": node_inventory,
    }
    schema = validate_package_manifest(package_manifest)
    package = validate_package_members(schema, members, verify_hashes=False)
    validate_package_declaration_inventory(
        package,
        tuple(declarations_by_module),
        require_declared_icons=True,
    )
    return package


def _manifest_from_data(raw: object) -> PackageManifest:
    if not isinstance(raw, dict):
        raise ValueError("Plugin package manifest must be a JSON object")
    nodes = raw.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("Manifest nodes must be a list")
    return PackageManifest(
        schema_version=2,
        name=str(raw["name"]),
        version=str(raw["version"]),
        author=str(raw.get("author", "")),
        description=str(raw.get("description", "")),
        modules=[str(item) for item in raw["modules"]],  # type: ignore[index]
        sources=[dict(item) for item in raw["sources"]],  # type: ignore[index]
        assets=[dict(item) for item in raw["assets"]],  # type: ignore[index]
        nodes=[str(item["id"]) for item in nodes],
    )


def _archive_info_has_non_regular_mode(info: zipfile.ZipInfo) -> bool:
    file_type = stat.S_IFMT((info.external_attr >> 16) & 0xFFFF)
    return file_type not in {0, stat.S_IFREG}


def _read_archive_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    limit: int,
) -> bytes:
    if info.file_size > limit:
        raise ValueError(f"Package archive member is too large: {info.filename}")
    try:
        with archive.open(info, "r") as stream:
            payload = stream.read(limit + 1)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Package archive member cannot be read: {info.filename}") from exc
    if len(payload) > limit:
        raise ValueError(f"Package archive member is too large: {info.filename}")
    return payload


def _read_archive(
    archive: zipfile.ZipFile,
) -> ValidatedPackage:
    infos = archive.infolist()
    if len(infos) > PLUGIN_MEMBER_LIMIT:
        raise ValueError("Plugin package contains too many members")
    seen: set[str] = set()
    members: dict[str, bytes] = {}
    declared_expanded_size = 0
    expanded_size = 0
    for info in infos:
        if info.flag_bits & 0x1:
            raise ValueError("Package archive may not contain encrypted members")
        if (
            info.is_dir()
            or _archive_info_has_non_regular_mode(info)
        ):
            raise ValueError("Package archive members must be regular files")
        raw_member_name = info.orig_filename
        try:
            member_name = validated_plugin_member_path(raw_member_name)
        except ValueError as exc:
            raise ValueError(f"Unsafe package archive member: {raw_member_name}") from exc
        folded = member_name.casefold()
        if folded in seen:
            raise ValueError(f"Duplicate package archive member: {member_name}")
        seen.add(folded)
        suffix = PurePosixPath(member_name).suffix.lower()
        if member_name == MANIFEST_FILENAME:
            limit = PLUGIN_MANIFEST_LIMIT
        elif suffix == ".py":
            limit = PLUGIN_SOURCE_LIMIT
        elif suffix in PLUGIN_ASSET_SUFFIXES:
            limit = PLUGIN_ASSET_LIMIT
        else:
            raise ValueError(f"Unsupported package archive member: {member_name}")
        declared_expanded_size += info.file_size
        if declared_expanded_size > PLUGIN_TOTAL_LIMIT:
            raise ValueError("Plugin package expanded size is too large")
        payload = _read_archive_member(archive, info, limit=limit)
        expanded_size += len(payload)
        if expanded_size > PLUGIN_TOTAL_LIMIT:
            raise ValueError("Plugin package expanded size is too large")
        members[member_name] = payload

    try:
        manifest_bytes = members.pop(MANIFEST_FILENAME)
    except KeyError as exc:
        raise ValueError(f"Package is missing {MANIFEST_FILENAME}") from exc
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid UTF-8 JSON in {MANIFEST_FILENAME}") from exc
    schema = validate_package_manifest(manifest)
    return validate_package_members(
        schema,
        members,
        manifest_size=len(manifest_bytes),
    )


def _temporary_container(parent: Path, package_name: str, *, kind: str) -> Path:
    return parent / f".{package_name}.{kind}-{uuid4().hex}"


def _cleanup_path(path: Path, *, code: str) -> bool:
    cleanup_code = code if code in _CLEANUP_CODES else "unknown"
    try:
        file_status = path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        logger.warning("Package cleanup failed [%s]", cleanup_code)
        return False
    attributes = getattr(file_status, "st_file_attributes", 0)
    is_alias = stat.S_ISLNK(file_status.st_mode) or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )
    try:
        if stat.S_ISDIR(file_status.st_mode) and not is_alias:
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError:
        logger.warning("Package cleanup failed [%s]", cleanup_code)
        return False
    return True


def _write_package_directory(
    container: Path,
    manifest: dict[str, object],
    members: dict[str, bytes],
) -> Path:
    package_dir = container / str(manifest["name"])
    package_dir.mkdir(parents=True, exist_ok=False)
    (package_dir / MANIFEST_FILENAME).write_bytes(canonical_manifest_bytes(manifest))
    for relative_path, payload in members.items():
        destination = package_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    return package_dir


def _validated_package_directory(package_dir: Path) -> dict[str, object]:
    package = read_validated_package_directory(package_dir)
    validated_package_declarations(
        package,
        filename_prefix=package.schema.name,
        require_declared_icons=True,
    )
    return package.manifest


def _zip_info(member_name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(member_name, _ARCHIVE_TIMESTAMP)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def _write_archive(
    archive_path: Path,
    manifest: dict[str, object],
    members: dict[str, bytes],
) -> None:
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_STORED,
    ) as archive:
        archive.writestr(
            _zip_info(MANIFEST_FILENAME),
            canonical_manifest_bytes(manifest),
        )
        for member_name in sorted(members):
            archive.writestr(
                _zip_info(member_name),
                members[member_name],
            )


def stage_package_import(
    package_path: Path,
    target_dir: Path | None = None,
) -> PackageInstallTransaction:
    """Validate one schema-2 archive and stage it without activating it."""

    source = Path(package_path)
    if is_reparse_point(source) or not source.is_file():
        raise ValueError("Node package archive must be a regular file")
    target = Path(target_dir) if target_dir is not None else plugins_dir()
    if is_reparse_point(target):
        raise ValueError("Plugin install root must not be a path alias")
    transaction: PackageInstallTransaction | None = None
    container: Path | None = None
    try:
        target.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(source, "r") as archive:
                archive_package = _read_archive(archive)
        except zipfile.BadZipFile as exc:
            raise ValueError("Node package archive is not a valid ZIP file") from exc

        package_name = archive_package.schema.name
        container = _temporary_container(target, package_name, kind="incoming")
        staged_dir = _write_package_directory(
            container,
            archive_package.manifest,
            archive_package.members,
        )
        validated_manifest = _validated_package_directory(staged_dir)
        manifest_bytes = canonical_manifest_bytes(validated_manifest)
        transaction = PackageInstallTransaction(
            manifest=_manifest_from_data(validated_manifest),
            staged_package_root=staged_dir,
            installed_package_root=target / package_name,
            _container=container,
            _manifest_bytes=manifest_bytes,
        )
        return transaction
    except OSError:
        raise ValueError(_IMPORT_FILESYSTEM_ERROR) from None
    finally:
        if transaction is None and container is not None:
            _cleanup_path(container, code="import_staging")


def import_package(package_path: Path, target_dir: Path | None = None) -> PackageManifest:
    """Validate and atomically install one schema-2 archive without source execution."""

    transaction = stage_package_import(package_path, target_dir=target_dir)
    try:
        transaction.activate()
    except Exception:
        transaction.rollback()
        raise
    transaction.commit()

    manifest = transaction.manifest
    logger.info(
        "Imported node package '%s' v%s to %s",
        manifest.name,
        manifest.version,
        transaction.installed_package_root,
    )
    return manifest


def export_package(
    source_files: list[PackageExportSource | Path | str],
    manifest: PackageManifest,
    output_path: Path,
    *,
    assets: list[PackageExportAsset | Path | str] | None = None,
) -> Path:
    """Statically validate and deterministically export one schema-2 archive."""

    package = _export_payload(source_files, assets or [], manifest)
    destination = Path(output_path).with_suffix(PACKAGE_EXTENSION)
    if is_reparse_point(destination.parent):
        raise ValueError("Package export directory must not be a path alias")
    temporary_archive: Path | None = None
    verification_container: Path | None = None
    try:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary_archive = destination.with_name(
                f".{destination.stem}.export-{uuid4().hex}{PACKAGE_EXTENSION}"
            )
            _write_archive(temporary_archive, package.manifest, package.members)
            try:
                with zipfile.ZipFile(temporary_archive, "r") as archive:
                    archive_package = _read_archive(archive)
            except zipfile.BadZipFile as exc:
                raise ValueError("Package export failed [archive]") from exc
            verification_container = _temporary_container(
                destination.parent,
                package.schema.name,
                kind="archive-validation",
            )
            verification_dir = _write_package_directory(
                verification_container,
                archive_package.manifest,
                archive_package.members,
            )
            _validated_package_directory(verification_dir)
            temporary_archive.replace(destination)
        finally:
            if verification_container is not None:
                _cleanup_path(verification_container, code="export_validation")
            if temporary_archive is not None:
                _cleanup_path(temporary_archive, code="export_archive")
    except OSError:
        raise ValueError(_EXPORT_FILESYSTEM_ERROR) from None

    logger.info("Exported node package '%s' to %s", package.schema.name, destination)
    return destination


def list_installed_packages(target_dir: Path | None = None) -> list[PackageManifest]:
    target = Path(target_dir) if target_dir is not None else plugins_dir()
    if not target.is_dir() or is_reparse_point(target):
        return []
    manifests: list[PackageManifest] = []
    for child in sorted(target.iterdir(), key=lambda path: path.name.casefold()):
        if child.name.startswith(_HIDDEN_PACKAGE_PREFIXES) or not child.is_dir():
            continue
        try:
            raw = _validated_package_directory(child)
        except ValueError as exc:
            if str(exc) == SCHEMA_1_UNSUPPORTED_MESSAGE:
                raise
            logger.warning("Could not validate installed package %s", child.name)
            continue
        manifests.append(_manifest_from_data(raw))
    return manifests


def uninstall_package(package_name: str, target_dir: Path | None = None) -> bool:
    target = Path(target_dir) if target_dir is not None else plugins_dir()
    package_dir = target / validated_package_name(package_name)
    if is_reparse_point(target) or is_reparse_point(package_dir):
        raise ValueError("Package uninstall paths must not contain path aliases")
    if package_dir.is_dir():
        shutil.rmtree(package_dir)
        logger.info("Uninstalled node package '%s'", package_name)
        return True
    return False


__all__ = [
    "MANIFEST_FILENAME",
    "PACKAGE_EXTENSION",
    "PackageExportAsset",
    "PackageExportSource",
    "PackageInstallState",
    "PackageInstallTransaction",
    "PackageManifest",
    "export_package",
    "import_package",
    "list_installed_packages",
    "stage_package_import",
    "uninstall_package",
]
