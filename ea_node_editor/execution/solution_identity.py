# Purpose: Build deterministic solution identities and bounded external provenance.
# Map: subsystems/execution.md
# Tests: tests/test_solution_identity.py, tests/test_runtime_current_results.py
# Landmarks: canonical_identity_bytes; ProvenanceHashPolicy; corex_build_digest; solution_key

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys
import threading
from typing import Any, TYPE_CHECKING

from ea_node_editor.runtime_contracts import (
    DataTree,
    ImageValue,
    Interval1D,
    RuntimeArtifactRef,
    RuntimeHandleRef,
    TypedInlineValue,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
    from ea_node_editor.nodes.registry import NodeRegistry


_SHA256_CHARS = frozenset("0123456789abcdef")
_CANONICAL_SCHEMA_VERSION = 1
_SOLUTION_KEY_SCHEMA_VERSION = 3
_BUILD_DIGEST_SCHEMA_VERSION = 1
_HASH_CHUNK_SIZE = 1024 * 1024
MAX_CANONICAL_DEPTH = 32
MAX_CANONICAL_ITEMS = 1_000_000
MAX_CANONICAL_BYTES = 64 * 1024 * 1024

class SolutionIdentityError(ValueError):
    """Fail-closed identity error carrying a stable, non-sensitive reason code."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


def _identity_error(reason_code: str, message: str) -> SolutionIdentityError:
    return SolutionIdentityError(reason_code, message)


def _require_digest(field_name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in _SHA256_CHARS for character in value)
    ):
        raise _identity_error(
            "identity_digest_invalid",
            f"{field_name} must be a lowercase SHA-256 digest",
        )
    return value


def _require_text(field_name: str, value: object, *, allow_empty: bool = False) -> str:
    if type(value) is not str or value != value.strip() or (not value and not allow_empty):
        raise _identity_error(
            "identity_field_invalid",
            f"{field_name} must be a trimmed string",
        )
    return value


def _json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except UnicodeEncodeError:
        raise _identity_error(
            "identity_text_invalid",
            "canonical identity contains invalid Unicode text",
        ) from None


class _CanonicalEncoder:
    def __init__(self) -> None:
        self._active_container_ids: set[int] = set()
        self._item_count = 0

    def encode(self, value: object) -> bytes:
        tagged = {
            "schema_version": _CANONICAL_SCHEMA_VERSION,
            "value": self._tag(value, depth=0),
        }
        encoded = _json_bytes(tagged)
        if len(encoded) > MAX_CANONICAL_BYTES:
            raise _identity_error(
                "identity_size_limit_exceeded",
                "canonical identity exceeds the encoded byte limit",
            )
        return encoded

    def _count(self) -> None:
        self._item_count += 1
        if self._item_count > MAX_CANONICAL_ITEMS:
            raise _identity_error(
                "identity_item_limit_exceeded",
                "canonical identity exceeds the item limit",
            )

    def _container(self, value: object, depth: int, build) -> object:  # noqa: ANN001
        if depth > MAX_CANONICAL_DEPTH:
            raise _identity_error(
                "identity_depth_limit_exceeded",
                "canonical identity exceeds the depth limit",
            )
        identity = id(value)
        if identity in self._active_container_ids:
            raise _identity_error(
                "identity_cycle_forbidden",
                "canonical identity cannot contain cycles",
            )
        self._active_container_ids.add(identity)
        try:
            return build()
        finally:
            self._active_container_ids.remove(identity)

    def _tag(self, value: object, *, depth: int) -> object:
        if depth > MAX_CANONICAL_DEPTH:
            raise _identity_error(
                "identity_depth_limit_exceeded",
                "canonical identity exceeds the depth limit",
            )
        self._count()
        value_type = type(value)
        if value is None:
            return {"t": "none"}
        if value_type is bool:
            return {"t": "bool", "v": value}
        if value_type is int:
            return {"t": "int", "v": str(value)}
        if value_type is float:
            if math.isnan(value):
                token = "nan"
            elif math.isinf(value):
                token = "+inf" if value > 0 else "-inf"
            else:
                token = struct.pack(">d", value).hex()
            return {"t": "float64", "v": token}
        if value_type is str:
            return {"t": "str", "v": value}
        if value_type in {bytes, bytearray, memoryview}:
            raise _identity_error(
                "identity_raw_bytes_forbidden",
                "raw bytes require a validated content reference",
            )
        if value_type is list:
            return self._container(
                value,
                depth,
                lambda: {
                    "t": "list",
                    "v": [self._tag(item, depth=depth + 1) for item in value],
                },
            )
        if value_type is tuple:
            return self._container(
                value,
                depth,
                lambda: {
                    "t": "tuple",
                    "v": [self._tag(item, depth=depth + 1) for item in value],
                },
            )
        if value_type is dict:
            return self._container(value, depth, lambda: self._mapping(value, depth))
        if value_type in {set, frozenset}:
            return self._container(value, depth, lambda: self._set(value, depth))
        if value_type is DataTree:
            return self._data_tree(value, depth)
        if value_type is Interval1D:
            return {
                "t": "interval_1d",
                "v": [
                    self._tag(object.__getattribute__(value, "start"), depth=depth + 1),
                    self._tag(object.__getattribute__(value, "end"), depth=depth + 1),
                ],
            }
        if value_type is TypedInlineValue:
            return {
                "t": "typed_inline",
                "data_type_id": object.__getattribute__(value, "data_type_id"),
                "schema_version": object.__getattribute__(value, "schema_version"),
                "payload": self._tag(
                    object.__getattribute__(value, "payload"), depth=depth + 1
                ),
            }
        if value_type is ImageValue:
            return {
                "t": "image",
                "data_type_id": "COREX.DataTypes.Image",
                "schema_version": object.__getattribute__(value, "schema_version"),
                "format": object.__getattribute__(value, "format"),
                "width": object.__getattribute__(value, "width"),
                "height": object.__getattribute__(value, "height"),
                "size_bytes": len(object.__getattribute__(value, "encoded_bytes")),
                "sha256": object.__getattribute__(value, "sha256"),
            }
        if value_type is RuntimeArtifactRef:
            return {
                "t": "artifact_ref",
                "artifact_id": object.__getattribute__(value, "artifact_id"),
                "scope": object.__getattribute__(value, "scope"),
                "data_type_id": object.__getattribute__(value, "data_type_id"),
                "schema_version": object.__getattribute__(value, "schema_version"),
                "format": object.__getattribute__(value, "format"),
                "size_bytes": object.__getattribute__(value, "size_bytes"),
                "sha256": object.__getattribute__(value, "sha256"),
                "provenance": object.__getattribute__(value, "provenance"),
                "metadata": self._tag(
                    object.__getattribute__(value, "metadata"), depth=depth + 1
                ),
            }
        if value_type is RuntimeHandleRef:
            raise _identity_error(
                "identity_runtime_handle_forbidden",
                "runtime handles require separate generation validation",
            )
        raise _identity_error(
            "identity_unsupported_value",
            "canonical identity contains an unsupported value",
        )

    def _mapping(self, value: dict[object, object], depth: int) -> object:
        items: list[tuple[bytes, bytes, object, object]] = []
        for key, item in value.items():
            tagged_key = self._tag(key, depth=depth + 1)
            encoded_key = _json_bytes(tagged_key)
            tagged_item = self._tag(item, depth=depth + 1)
            encoded_item = _json_bytes(tagged_item)
            items.append((encoded_key, encoded_item, tagged_key, tagged_item))
        items.sort(key=lambda entry: (entry[0], entry[1]))
        return {
            "t": "map",
            "v": [[key, item] for _key_bytes, _item_bytes, key, item in items],
        }

    def _set(self, value: set[object] | frozenset[object], depth: int) -> object:
        items = [self._tag(item, depth=depth + 1) for item in value]
        items.sort(key=_json_bytes)
        return {"t": "frozenset" if type(value) is frozenset else "set", "v": items}

    def _data_tree(self, value: DataTree, depth: int) -> object:
        tagged_branches = []
        for path, items in object.__getattribute__(value, "_branches"):
            self._count()
            tagged_path = []
            for index in path:
                self._count()
                tagged_path.append(str(index))
            tagged_branches.append(
                {
                    "path": tagged_path,
                    "items": [
                        self._tag(item, depth=depth + 1) for item in items
                    ],
                }
            )
        return {"t": "data_tree", "v": tagged_branches}


def canonical_identity_bytes(value: object) -> bytes:
    """Encode supported identity values without invoking user callbacks."""

    return _CanonicalEncoder().encode(value)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_identity_bytes(value)).hexdigest()


@dataclass(slots=True, frozen=True)
class ProvenanceHashPolicy:
    schema_version: int = 1
    follow_symlinks_or_reparse_points: bool = False
    max_single_file_bytes: int = 68_719_476_736
    max_directory_total_bytes: int = 68_719_476_736
    max_directory_entries: int = 100_000
    max_directory_depth: int = 32

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("ProvenanceHashPolicy.schema_version must be 1")
        if self.follow_symlinks_or_reparse_points is not False:
            raise ValueError("Provenance hashing must not follow links or reparse points")
        for field_name in (
            "max_single_file_bytes",
            "max_directory_total_bytes",
            "max_directory_entries",
            "max_directory_depth",
        ):
            value = object.__getattribute__(self, field_name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"ProvenanceHashPolicy.{field_name} must be positive")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema_version": self.schema_version,
                "follow_symlinks_or_reparse_points": self.follow_symlinks_or_reparse_points,
                "max_single_file_bytes": self.max_single_file_bytes,
                "max_directory_total_bytes": self.max_directory_total_bytes,
                "max_directory_entries": self.max_directory_entries,
                "max_directory_depth": self.max_directory_depth,
            }
        )


DEFAULT_PROVENANCE_HASH_POLICY = ProvenanceHashPolicy()


@dataclass(slots=True, frozen=True)
class FileProvenance:
    size_bytes: int
    sha256: str
    policy_digest: str


@dataclass(slots=True, frozen=True)
class DirectoryProvenance:
    entry_count: int
    total_bytes: int
    sha256: str
    policy_digest: str


def _cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise _identity_error(
            "provenance_cancelled",
            "provenance hashing was cancelled",
        )


def _is_link(file_stat: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(file_stat, "st_file_attributes", 0)
    return stat.S_ISLNK(file_stat.st_mode) or bool(
        reparse_flag and attributes & reparse_flag
    )


def _same_file(
    expected: os.stat_result,
    actual: os.stat_result,
    *,
    compare_size: bool,
) -> bool:
    if (
        expected.st_dev != actual.st_dev
        or expected.st_ino != actual.st_ino
        or stat.S_IFMT(expected.st_mode) != stat.S_IFMT(actual.st_mode)
    ):
        return False
    if compare_size and expected.st_size != actual.st_size:
        return False
    expected_mtime = getattr(expected, "st_mtime_ns", None)
    actual_mtime = getattr(actual, "st_mtime_ns", None)
    return (
        expected_mtime is None
        or actual_mtime is None
        or expected_mtime == actual_mtime
    )


def _checked_stat(path: Path) -> os.stat_result:
    file_stat = os.lstat(path)
    if _is_link(file_stat):
        raise _identity_error(
            "provenance_link_forbidden",
            "provenance inputs must not contain links or reparse points",
        )
    return file_stat


def _require_same_directory(path: Path, expected: os.stat_result) -> None:
    current = _checked_stat(path)
    if not stat.S_ISDIR(current.st_mode) or not _same_file(
        expected,
        current,
        compare_size=False,
    ):
        raise _identity_error(
            "provenance_changed",
            "provenance directory changed while hashing",
        )


def _directory_entry_snapshot(
    directory: Path,
    expected_directory: os.stat_result,
) -> tuple[
    tuple[tuple[Path, os.stat_result], ...],
    tuple[tuple[str, int, int, int, int, int | None], ...],
]:
    _require_same_directory(directory, expected_directory)
    with os.scandir(directory) as iterator:
        entries = sorted(iterator, key=lambda entry: entry.name)
    _require_same_directory(directory, expected_directory)
    records: list[tuple[Path, os.stat_result]] = []
    facts: list[tuple[str, int, int, int, int, int | None]] = []
    for entry in entries:
        _require_same_directory(directory, expected_directory)
        entry_path = Path(entry.path)
        try:
            entry_stat = _checked_stat(entry_path)
        except FileNotFoundError:
            raise _identity_error(
                "provenance_changed",
                "provenance directory changed while hashing",
            ) from None
        records.append((entry_path, entry_stat))
        facts.append(
            (
                entry.name,
                entry_stat.st_dev,
                entry_stat.st_ino,
                stat.S_IFMT(entry_stat.st_mode),
                entry_stat.st_size,
                getattr(entry_stat, "st_mtime_ns", None),
            )
        )
    _require_same_directory(directory, expected_directory)
    return tuple(records), tuple(facts)


def _hash_regular_file(
    path: Path,
    *,
    expected: os.stat_result,
    policy: ProvenanceHashPolicy,
    cancel_event: threading.Event | None,
    digest: Any,
) -> int:
    if not stat.S_ISREG(expected.st_mode):
        raise _identity_error(
            "provenance_not_regular",
            "provenance input is not a regular file",
        )
    if expected.st_size > policy.max_single_file_bytes:
        raise _identity_error(
            "provenance_limit_exceeded",
            "provenance file exceeds the byte limit",
        )
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    actual_size = 0
    opened: os.stat_result | None = None
    final_opened: os.stat_result | None = None
    try:
        opened = os.fstat(descriptor)
        if not _same_file(expected, opened, compare_size=True):
            raise _identity_error(
                "provenance_changed",
                "provenance input changed while hashing",
            )
        while True:
            _cancelled(cancel_event)
            chunk = os.read(descriptor, _HASH_CHUNK_SIZE)
            if not chunk:
                break
            actual_size += len(chunk)
            digest.update(chunk)
        final_opened = os.fstat(descriptor)
        if not _same_file(opened, final_opened, compare_size=True):
            raise _identity_error(
                "provenance_changed",
                "provenance input changed while hashing",
            )
    finally:
        os.close(descriptor)
    final_path = _checked_stat(path)
    if (
        opened is None
        or final_opened is None
        or not _same_file(expected, final_path, compare_size=True)
        or not _same_file(final_opened, final_path, compare_size=True)
        or actual_size != expected.st_size
    ):
        raise _identity_error(
            "provenance_changed",
            "provenance input changed while hashing",
        )
    return actual_size


def hash_file_provenance(
    path: str | Path,
    *,
    policy: ProvenanceHashPolicy = DEFAULT_PROVENANCE_HASH_POLICY,
    cancel_event: threading.Event | None = None,
) -> FileProvenance:
    try:
        resolved = Path(path)
        expected = _checked_stat(resolved)
        digest = hashlib.sha256()
        size_bytes = _hash_regular_file(
            resolved,
            expected=expected,
            policy=policy,
            cancel_event=cancel_event,
            digest=digest,
        )
        return FileProvenance(size_bytes, digest.hexdigest(), policy.digest)
    except SolutionIdentityError:
        raise
    except FileNotFoundError:
        raise _identity_error(
            "provenance_missing",
            "provenance input is missing",
        ) from None
    except PermissionError:
        raise _identity_error(
            "provenance_permission_denied",
            "provenance input cannot be read",
        ) from None
    except OSError:
        raise _identity_error(
            "provenance_inspection_failed",
            "provenance input could not be inspected",
        ) from None


def _tree_entry(digest: Any, kind: bytes, relative_path: str, size_bytes: int = 0) -> None:
    try:
        path_bytes = relative_path.encode("utf-8")
    except UnicodeError:
        raise _identity_error(
            "provenance_name_invalid",
            "provenance input contains an invalid name",
        ) from None
    digest.update(kind)
    digest.update(len(path_bytes).to_bytes(8, "big"))
    digest.update(path_bytes)
    digest.update(size_bytes.to_bytes(8, "big"))


def hash_directory_provenance(
    path: str | Path,
    *,
    policy: ProvenanceHashPolicy = DEFAULT_PROVENANCE_HASH_POLICY,
    cancel_event: threading.Event | None = None,
) -> DirectoryProvenance:
    entry_count = 0
    total_bytes = 0
    digest = hashlib.sha256(b"corex-provenance-directory-v1\0")

    def visit(directory: Path, relative_parent: str, depth: int) -> None:
        nonlocal entry_count, total_bytes
        _cancelled(cancel_event)
        if depth > policy.max_directory_depth:
            raise _identity_error(
                "provenance_limit_exceeded",
                "provenance directory exceeds the depth limit",
            )
        expected_directory = _checked_stat(directory)
        if not stat.S_ISDIR(expected_directory.st_mode):
            raise _identity_error(
                "provenance_not_directory",
                "provenance input is not a directory",
            )
        entries, entry_facts = _directory_entry_snapshot(
            directory,
            expected_directory,
        )
        if len(entries) > policy.max_directory_entries - entry_count:
            raise _identity_error(
                "provenance_limit_exceeded",
                "provenance directory exceeds the entry limit",
            )
        for entry_path, entry_stat in entries:
            _cancelled(cancel_event)
            _require_same_directory(directory, expected_directory)
            entry_count += 1
            if entry_count > policy.max_directory_entries:
                raise _identity_error(
                    "provenance_limit_exceeded",
                    "provenance directory exceeds the entry limit",
                )
            entry_name = entry_path.name
            relative_path = (
                f"{relative_parent}/{entry_name}" if relative_parent else entry_name
            )
            if stat.S_ISDIR(entry_stat.st_mode):
                _tree_entry(digest, b"D", relative_path)
                visit(entry_path, relative_path, depth + 1)
                _require_same_directory(directory, expected_directory)
                continue
            if not stat.S_ISREG(entry_stat.st_mode):
                raise _identity_error(
                    "provenance_not_regular",
                    "provenance directory contains an unsupported entry",
                )
            if total_bytes + entry_stat.st_size > policy.max_directory_total_bytes:
                raise _identity_error(
                    "provenance_limit_exceeded",
                    "provenance directory exceeds the byte limit",
                )
            _tree_entry(digest, b"F", relative_path, entry_stat.st_size)
            total_bytes += _hash_regular_file(
                entry_path,
                expected=entry_stat,
                policy=policy,
                cancel_event=cancel_event,
                digest=digest,
            )
            if total_bytes > policy.max_directory_total_bytes:
                raise _identity_error(
                    "provenance_limit_exceeded",
                    "provenance directory exceeds the byte limit",
                )
            _require_same_directory(directory, expected_directory)
        _final_entries, final_entry_facts = _directory_entry_snapshot(
            directory,
            expected_directory,
        )
        if final_entry_facts != entry_facts:
            raise _identity_error(
                "provenance_changed",
                "provenance directory changed while hashing",
            )

    try:
        visit(Path(path), "", 0)
        return DirectoryProvenance(
            entry_count,
            total_bytes,
            digest.hexdigest(),
            policy.digest,
        )
    except SolutionIdentityError:
        raise
    except FileNotFoundError:
        raise _identity_error(
            "provenance_missing",
            "provenance input is missing",
        ) from None
    except PermissionError:
        raise _identity_error(
            "provenance_permission_denied",
            "provenance input cannot be read",
        ) from None
    except OSError:
        raise _identity_error(
            "provenance_inspection_failed",
            "provenance input could not be inspected",
        ) from None


def provenance_digest(
    value: FileProvenance | DirectoryProvenance,
    *,
    path_policy: str,
) -> str:
    if type(value) not in {FileProvenance, DirectoryProvenance}:
        raise TypeError("value must be FileProvenance or DirectoryProvenance")
    return canonical_digest(
        {
            "path_policy": _require_text("path_policy", path_policy),
            "provenance": {
                field_name: object.__getattribute__(value, field_name)
                for field_name in type(value).__dataclass_fields__
            },
            "kind": "file" if type(value) is FileProvenance else "directory",
        }
    )


def execution_policy_digest(
    *,
    provenance_policy: ProvenanceHashPolicy = DEFAULT_PROVENANCE_HASH_POLICY,
    policy_facts: dict[str, object] | None = None,
) -> str:
    return canonical_digest(
        {
            "provenance_policy_digest": provenance_policy.digest,
            "policy_facts": {} if policy_facts is None else policy_facts,
        }
    )


@dataclass(slots=True, frozen=True, kw_only=True)
class ExecutionEnvironmentIdentity:
    backend: str
    isolation_mode: str
    interpreter_build: str
    platform: str
    packages: tuple[tuple[str, str], ...] = ()
    addons: tuple[tuple[str, str, str], ...] = ()
    toolchains: tuple[tuple[str, str, str], ...] = ()
    execution_policy_digest: str

    def __post_init__(self) -> None:
        for field_name in ("backend", "isolation_mode", "interpreter_build", "platform"):
            _require_text(field_name, object.__getattribute__(self, field_name))
        _require_digest("execution_policy_digest", self.execution_policy_digest)
        for field_name, width in (("packages", 2), ("addons", 3), ("toolchains", 3)):
            values = object.__getattribute__(self, field_name)
            if type(values) is not tuple:
                raise TypeError(f"{field_name} must be a tuple")
            normalized = []
            for item in values:
                if type(item) is not tuple or len(item) != width:
                    raise TypeError(f"{field_name} entries must be {width}-tuples")
                normalized.append(
                    tuple(
                        (
                            _require_digest(f"{field_name} digest", part)
                            if width == 3 and index == 2
                            else _require_text(f"{field_name} entry", part)
                        )
                        for index, part in enumerate(item)
                    )
                )
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"{field_name} must not contain duplicates")
            object.__setattr__(self, field_name, tuple(sorted(normalized)))

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "backend": self.backend,
                "isolation_mode": self.isolation_mode,
                "interpreter_build": self.interpreter_build,
                "platform": self.platform,
                "packages": self.packages,
                "addons": self.addons,
                "toolchains": self.toolchains,
                "execution_policy_digest": self.execution_policy_digest,
            }
        )


def _build_tree_digest(source_root: Path) -> str:
    digest = hashlib.sha256(b"corex-build-v1\0")
    entry_count = 0
    total_bytes = 0
    for package_name in ("corex", "ea_node_editor"):
        package_root = source_root / package_name
        package_stat = _checked_stat(package_root)
        if not stat.S_ISDIR(package_stat.st_mode):
            raise _identity_error(
                "corex_build_identity_unavailable",
                "COREX build sources are unavailable",
            )
        for candidate in sorted(package_root.rglob("*"), key=lambda item: item.as_posix()):
            relative_parts = candidate.relative_to(source_root).parts
            if "__pycache__" in relative_parts or candidate.suffix in {".pyc", ".pyo"}:
                continue
            candidate_stat = _checked_stat(candidate)
            if stat.S_ISDIR(candidate_stat.st_mode):
                continue
            if not stat.S_ISREG(candidate_stat.st_mode):
                raise _identity_error(
                    "corex_build_identity_unavailable",
                    "COREX build contains an unsupported entry",
                )
            entry_count += 1
            if entry_count > DEFAULT_PROVENANCE_HASH_POLICY.max_directory_entries:
                raise _identity_error(
                    "corex_build_identity_unavailable",
                    "COREX build exceeds the entry limit",
                )
            relative = candidate.relative_to(source_root).as_posix()
            _tree_entry(digest, b"F", relative, candidate_stat.st_size)
            total_bytes += _hash_regular_file(
                candidate,
                expected=candidate_stat,
                policy=DEFAULT_PROVENANCE_HASH_POLICY,
                cancel_event=None,
                digest=digest,
            )
            if total_bytes > DEFAULT_PROVENANCE_HASH_POLICY.max_directory_total_bytes:
                raise _identity_error(
                    "corex_build_identity_unavailable",
                    "COREX build exceeds the byte limit",
                )
    return canonical_digest(
        {
            "schema_version": _BUILD_DIGEST_SCHEMA_VERSION,
            "entry_count": entry_count,
            "total_bytes": total_bytes,
            "tree_sha256": digest.hexdigest(),
        }
    )


def _frozen_executable_build_digest(executable: Path) -> str:
    provenance = hash_file_provenance(executable)
    return canonical_digest(
        {
            "schema_version": _BUILD_DIGEST_SCHEMA_VERSION,
            "authority": "frozen_executable",
            "size_bytes": provenance.size_bytes,
            "sha256": provenance.sha256,
        }
    )


@lru_cache(maxsize=2)
def _cached_corex_build_digest(authority: str, location: str) -> str:
    if authority == "frozen_executable":
        return _frozen_executable_build_digest(Path(location))
    return _build_tree_digest(Path(location))


def corex_build_digest(*, source_root: str | Path | None = None) -> str:
    """Return one process-cached digest for the source or frozen build authority."""

    try:
        if source_root is not None:
            return _build_tree_digest(Path(source_root))
        if bool(getattr(sys, "frozen", False)):
            return _cached_corex_build_digest(
                "frozen_executable",
                os.path.abspath(sys.executable),
            )
        return _cached_corex_build_digest(
            "source_tree",
            str(Path(__file__).resolve().parents[2]),
        )
    except SolutionIdentityError as exc:
        if exc.reason_code == "corex_build_identity_unavailable":
            raise
        raise _identity_error(
            "corex_build_identity_unavailable",
            "COREX build identity is unavailable",
        ) from None
    except OSError:
        raise _identity_error(
            "corex_build_identity_unavailable",
            "COREX build identity is unavailable",
        ) from None


def implementation_digest(
    registry: NodeRegistry,
    type_id: str,
    *,
    build_digest: str | None = None,
) -> str:
    from ea_node_editor.nodes.registry import PythonFunctionEntry

    entry = registry.get_entry(type_id)
    if not isinstance(entry, PythonFunctionEntry):
        raise _identity_error(
            "implementation_identity_unavailable",
            "trusted factory implementations are not reusable in T02",
        )
    bundle = next(
        (
            candidate
            for candidate in registry.plugin_bundle_refs()
            if candidate.owner_id == entry.owner_id
        ),
        None,
    )
    if bundle is None:
        raise _identity_error(
            "implementation_identity_unavailable",
            "function bundle identity is unavailable",
        )
    return canonical_digest(
        {
            "corex_build_digest": _require_digest(
                "build_digest",
                corex_build_digest() if build_digest is None else build_digest,
            ),
            "owner_id": entry.owner_id,
            "owner_version": bundle.version,
            "bundle_digest": entry.function_ref.bundle_digest,
            "source_digest": entry.function_ref.source_digest,
            "module_relative_path": entry.function_ref.module_relative_path,
            "function_name": entry.function_ref.function_name,
        }
    )


def catalog_revision_digest(
    catalog: Any,
    *,
    type_ids: Sequence[str],
    conversion_pairs: Sequence[tuple[str, str]] = (),
) -> str:
    requested_types = set(type_ids)
    requested_conversions = set(conversion_pairs)
    if len(requested_types) != len(tuple(type_ids)):
        raise ValueError("type_ids must not contain duplicates")
    if len(requested_conversions) != len(tuple(conversion_pairs)):
        raise ValueError("conversion_pairs must not contain duplicates")
    selected: list[dict[str, object]] = []
    found_types: set[str] = set()
    found_conversions: set[tuple[str, str]] = set()
    for record in catalog.snapshot():
        kind = record.get("kind")
        if kind == "type" and record.get("type_id") in requested_types:
            type_id = str(record["type_id"])
            found_types.add(type_id)
            selected.append(
                {
                    key: value
                    for key, value in record.items()
                    if key not in {"display_name", "description", "source_label"}
                }
            )
        elif kind == "conversion":
            pair = (
                str(record.get("source_type_id", "")),
                str(record.get("target_type_id", "")),
            )
            if pair in requested_conversions:
                found_conversions.add(pair)
                selected.append(
                    {
                        key: value
                        for key, value in record.items()
                        if key != "source_label"
                    }
                )
    if found_types != requested_types or found_conversions != requested_conversions:
        raise _identity_error(
            "catalog_identity_missing",
            "requested catalog identity is unavailable",
        )
    return canonical_digest(
        sorted(
            selected,
            key=lambda record: (
                str(record.get("kind", "")),
                str(record.get("type_id", record.get("source_type_id", ""))),
                str(record.get("target_type_id", "")),
            ),
        )
    )


def node_contract_digest(
    spec: NodeTypeSpec,
    effective_ports: Sequence[PortSpec],
    *,
    port_modifiers: Mapping[str, Sequence[str]] | None = None,
    principal_input_port_id: str | None = None,
    source_contracts: Mapping[str, object] | None = None,
) -> str:
    properties = {property_spec.key: property_spec for property_spec in spec.properties}
    modifiers = {} if port_modifiers is None else port_modifiers
    return canonical_digest(
        {
            "type_id": spec.type_id,
            "runtime_behavior": spec.runtime_behavior,
            "is_async": spec.is_async,
            "solution_reuse_scope": spec.solution_reuse_scope,
            "ports": [
                {
                    "key": port.key,
                    "direction": port.direction,
                    "kind": port.kind,
                    "data_type": port.data_type,
                    "accepted_data_types": port.accepted_data_types,
                    "type_from_input": port.type_from_input,
                    "source_contract": (source_contracts or {}).get(port.key),
                    "data_access": port.data_access,
                    "required": port.required,
                    "uses_property_default": port.uses_property_default,
                    "property_default": (
                        properties[port.key].default
                        if port.uses_property_default and port.key in properties
                        else None
                    ),
                    "exposed": port.exposed,
                    "allow_multiple_connections": port.allow_multiple_connections,
                    "modifiers": tuple(modifiers.get(port.key, ())),
                }
                for port in effective_ports
            ],
            "principal_input_port_id": principal_input_port_id,
            "readiness_requirements": [
                {
                    "any_of_ports": requirement.any_of_ports,
                    "any_of_properties": requirement.any_of_properties,
                    "when_ports_present": requirement.when_ports_present,
                    "when_properties": [
                        {
                            "property_key": condition.property_key,
                            "values": condition.values,
                        }
                        for condition in requirement.when_properties
                    ],
                }
                for requirement in spec.readiness_requirements
            ],
        }
    )


@dataclass(slots=True, frozen=True)
class IncomingEdgeIdentity:
    source_node_id: str
    source_port_key: str
    target_port_key: str
    input_order: int
    conversion_id: str = ""
    source_contract: tuple[tuple[str, ...], bool] = ((), False)


@dataclass(slots=True, frozen=True, kw_only=True)
class NodeSolutionIdentity:
    solution_namespace_id: str
    workspace_id: str
    node_id: str
    node_type_id: str
    node_interface_revision: int
    node_interface_digest: str
    node_contract_digest: str
    authored_properties: tuple[tuple[str, object], ...]
    incoming_edges: tuple[IncomingEdgeIdentity, ...]
    hidden_ordering_pairs: tuple[tuple[str, str], ...]
    dependency_solution_keys: tuple[str, ...]
    trigger_publication_generations: tuple[tuple[str, int], ...]
    input_provenance_digest: str
    execution_policy_digest: str
    implementation_digest: str
    catalog_revision_digest: str
    execution_environment_digest: str


@dataclass(slots=True, frozen=True, kw_only=True)
class AssembledNodeSolution:
    solution_key: str
    reason_code: str
    dependency_solution_keys: tuple[str, ...]
    node_interface_revision: int
    node_interface_digest: str
    node_contract_digest: str
    input_provenance_digest: str
    execution_policy_digest: str
    implementation_digest: str
    execution_environment_digest: str
    output_specs: tuple[tuple[str, str, str], ...]


def solution_key(identity: NodeSolutionIdentity) -> str:
    if type(identity) is not NodeSolutionIdentity:
        raise TypeError("identity must be a NodeSolutionIdentity")
    if type(identity.node_interface_revision) is not int or identity.node_interface_revision <= 0:
        raise _identity_error(
            "node_interface_revision_invalid",
            "node interface revision must be positive",
        )
    for field_name in (
        "node_interface_digest",
        "node_contract_digest",
        "input_provenance_digest",
        "execution_policy_digest",
        "implementation_digest",
        "catalog_revision_digest",
        "execution_environment_digest",
    ):
        _require_digest(field_name, object.__getattribute__(identity, field_name))
    for dependency_key in identity.dependency_solution_keys:
        _require_digest("dependency_solution_key", dependency_key)
    property_keys = [key for key, _value in identity.authored_properties]
    if (
        any(type(key) is not str or not key or key != key.strip() for key in property_keys)
        or len(property_keys) != len(set(property_keys))
    ):
        raise _identity_error(
            "authored_properties_invalid",
            "authored properties require unique trimmed keys",
        )
    for edge in identity.incoming_edges:
        if type(edge) is not IncomingEdgeIdentity:
            raise TypeError("incoming_edges must contain IncomingEdgeIdentity values")
        if type(edge.input_order) is not int or edge.input_order < 0:
            raise _identity_error(
                "incoming_edge_invalid",
                "incoming edge order must be non-negative",
            )
    for trigger_id, generation in identity.trigger_publication_generations:
        _require_text("trigger_id", trigger_id)
        if type(generation) is not int or generation < 0:
            raise _identity_error(
                "trigger_generation_invalid",
                "trigger publication generation must be non-negative",
            )
    return canonical_digest(
        {
            "schema_version": _SOLUTION_KEY_SCHEMA_VERSION,
            "solution_namespace_id": _require_text(
                "solution_namespace_id", identity.solution_namespace_id
            ),
            "workspace_id": _require_text("workspace_id", identity.workspace_id),
            "node_id": _require_text("node_id", identity.node_id),
            "node_type_id": _require_text("node_type_id", identity.node_type_id),
            "node_interface_revision": identity.node_interface_revision,
            "node_interface_digest": identity.node_interface_digest,
            "node_contract_digest": identity.node_contract_digest,
            "authored_properties": dict(identity.authored_properties),
            "incoming_edges": [
                {
                    "source_node_id": edge.source_node_id,
                    "source_port_key": edge.source_port_key,
                    "target_port_key": edge.target_port_key,
                    "input_order": edge.input_order,
                    "conversion_id": edge.conversion_id,
                    "source_contract": edge.source_contract,
                }
                for edge in sorted(
                    identity.incoming_edges,
                    key=lambda item: (
                        item.target_port_key,
                        item.input_order,
                        item.source_node_id,
                        item.source_port_key,
                    ),
                )
            ],
            "hidden_ordering_pairs": tuple(sorted(identity.hidden_ordering_pairs)),
            "dependency_solution_keys": identity.dependency_solution_keys,
            "trigger_publication_generations": tuple(
                sorted(identity.trigger_publication_generations)
            ),
            "input_provenance_digest": identity.input_provenance_digest,
            "execution_policy_digest": identity.execution_policy_digest,
            "implementation_digest": identity.implementation_digest,
            "catalog_revision_digest": identity.catalog_revision_digest,
            "execution_environment_digest": identity.execution_environment_digest,
        }
    )


def _node_input_provenance_digest(
    *,
    plan: Any,
    node_id: str,
    normalized_properties: Mapping[str, Any],
) -> str:
    facts: list[dict[str, Any]] = []
    for provenance_input in plan.node_specs[node_id].solution_provenance_inputs:
        if plan.incoming_edges_for(node_id, provenance_input.property_key):
            facts.append(
                {
                    "property_key": provenance_input.property_key,
                    "kind": provenance_input.kind,
                    "policy_revision": provenance_input.policy_revision,
                    "source": "dependency",
                }
            )
            continue
        raw_path = normalized_properties.get(provenance_input.property_key, "")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise SolutionIdentityError(
                "provenance_input_missing",
                "declared solution provenance input is unavailable",
            )
        provenance = (
            hash_file_provenance(raw_path)
            if provenance_input.kind == "file"
            else hash_directory_provenance(raw_path)
        )
        facts.append(
            {
                "property_key": provenance_input.property_key,
                "kind": provenance_input.kind,
                "policy_revision": provenance_input.policy_revision,
                "digest": provenance_digest(
                    provenance,
                    path_policy="content_only_no_links_v1",
                ),
            }
        )
    return canonical_digest({"inputs": facts})


def assemble_node_solution(
    *,
    preparation_id: str,
    solution_namespace_id: str,
    workspace_solution_revision: int,
    plan: Any,
    registry: NodeRegistry,
    node_id: str,
    keys_by_node: Mapping[str, str],
    execution_environment_digest: str,
    trigger_publication_generations: Mapping[str, int],
) -> AssembledNodeSolution:
    """Assemble the exact per-node identity used on both sides of dispatch."""

    node = plan.nodes[node_id]
    spec = plan.node_specs[node_id]
    fallback_digest = canonical_digest(
        {"preparation_id": preparation_id, "node_id": node_id}
    )
    contract_hash = fallback_digest
    provenance_hash = fallback_digest
    policy_hash = execution_policy_digest()
    implementation_hash = fallback_digest
    dependency_keys: tuple[str, ...] = ()
    interface_revision = plan.workflow_interface_revision
    interface_digest = plan.node_solution_interface_digest(node_id)
    try:
        normalized_properties = registry.normalize_properties(
            node.type_id,
            node.properties,
            include_defaults=True,
        )
        incoming_identities: list[IncomingEdgeIdentity] = []
        conversion_pairs: set[tuple[str, str]] = set()
        dependency_key_list: list[str] = []
        trigger_generations: list[tuple[str, int]] = []
        incoming_type_ids: set[str] = set()
        for edge in plan.incoming_edges_for(node_id):
            source_node_id = edge.source_node_id
            target_port = plan.ports_by_key[node_id][edge.target_port_key]
            contract = plan.type_resolver.source_contract(source_node_id, edge.source_port_key)
            incoming_type_ids.update(contract.type_ids)
            compatibility = plan.type_resolver.compatibility(source_node_id, edge.source_port_key, target_port)
            conversions = {
                (member.source_type_id, member.matched_type_id)
                for member in compatibility.members if member.status == "convertible"
            }
            conversion_pairs.update(conversions)
            conversion_id = ";".join(f"{source}->{target}" for source, target in sorted(conversions))
            incoming_identities.append(
                IncomingEdgeIdentity(
                    source_node_id=source_node_id,
                    source_port_key=edge.source_port_key,
                    target_port_key=edge.target_port_key,
                    input_order=edge.input_order,
                    conversion_id=conversion_id,
                    source_contract=contract.identity,
                )
            )
            if plan.is_trigger(source_node_id):
                try:
                    generation = trigger_publication_generations[source_node_id]
                except KeyError as exc:
                    raise SolutionIdentityError(
                        "trigger_generation_missing",
                        "trigger publication generation is unavailable",
                    ) from exc
                trigger_generations.append((source_node_id, generation))
            elif source_node_id in keys_by_node:
                dependency_key_list.append(keys_by_node[source_node_id])
        hidden_pairs = tuple(
            pair for pair in plan.hidden_ordering_pairs if pair[1] == node_id
        )
        dependency_key_list.extend(
            keys_by_node[source]
            for source, _target in hidden_pairs
            if source in keys_by_node
        )
        dependency_keys = tuple(dict.fromkeys(dependency_key_list))
        contract_hash = node_contract_digest(
            spec,
            plan.node_ports[node_id],
            port_modifiers=node.port_modifiers,
            principal_input_port_id=node.principal_input_port_id,
            source_contracts={port.key: plan.source_contracts[(node_id, port.key)].identity
                              for port in plan.output_ports(node_id) if port.kind == "data"},
        )
        provenance_hash = _node_input_provenance_digest(
            plan=plan,
            node_id=node_id,
            normalized_properties=normalized_properties,
        )
        implementation_hash = implementation_digest(registry, node.type_id)
        used_type_ids = {
            type_id
            for port in plan.node_ports[node_id]
            for type_id in (port.data_type, *port.accepted_data_types)
        }
        used_type_ids.update(incoming_type_ids)
        used_type_ids.update(type_id for port in plan.output_ports(node_id) if port.kind == "data"
                             for type_id in plan.source_contracts[(node_id, port.key)].type_ids)
        catalog_hash = catalog_revision_digest(
            registry.data_types,
            type_ids=tuple(sorted(used_type_ids)),
            conversion_pairs=tuple(sorted(conversion_pairs)),
        )
        key = solution_key(
            NodeSolutionIdentity(
                solution_namespace_id=solution_namespace_id,
                workspace_id=plan.workspace.workspace_id,
                node_id=node_id,
                node_type_id=node.type_id,
                node_interface_revision=interface_revision,
                node_interface_digest=interface_digest,
                node_contract_digest=contract_hash,
                authored_properties=tuple(sorted(normalized_properties.items())),
                incoming_edges=tuple(incoming_identities),
                hidden_ordering_pairs=hidden_pairs,
                dependency_solution_keys=dependency_keys,
                trigger_publication_generations=tuple(trigger_generations),
                input_provenance_digest=provenance_hash,
                execution_policy_digest=policy_hash,
                implementation_digest=implementation_hash,
                catalog_revision_digest=catalog_hash,
                execution_environment_digest=execution_environment_digest,
            )
        )
        reason = ""
    except (KeyError, OSError, TypeError, ValueError) as exc:
        reason = getattr(exc, "reason_code", "solution_identity_unavailable")
        key = execute_only_solution_key(
            solution_namespace_id=solution_namespace_id,
            workspace_id=plan.workspace.workspace_id,
            node_id=node_id,
            preparation_id=preparation_id,
            workspace_solution_revision=workspace_solution_revision,
            reason_code=reason,
        )
    return AssembledNodeSolution(
        solution_key=key,
        reason_code=reason,
        dependency_solution_keys=dependency_keys,
        node_interface_revision=interface_revision,
        node_interface_digest=interface_digest,
        node_contract_digest=contract_hash,
        input_provenance_digest=provenance_hash,
        execution_policy_digest=policy_hash,
        implementation_digest=implementation_hash,
        execution_environment_digest=execution_environment_digest,
        output_specs=tuple(
            (port.key, port.data_type, port.data_access)
            for port in plan.output_ports(node_id)
            if port.kind == "data"
        ),
    )


def execute_only_solution_key(
    *,
    solution_namespace_id: str,
    workspace_id: str,
    node_id: str,
    preparation_id: str,
    workspace_solution_revision: int,
    reason_code: str,
) -> str:
    """Build a per-preparation key that can never enter the reuse index."""

    if isinstance(workspace_solution_revision, bool) or not isinstance(
        workspace_solution_revision, int
    ):
        raise TypeError("workspace_solution_revision must be an integer")
    if workspace_solution_revision < 0:
        raise ValueError("workspace_solution_revision must be non-negative")
    return canonical_digest(
        {
            "schema_version": 1,
            "kind": "execute_only",
            "solution_namespace_id": _require_text(
                "solution_namespace_id", solution_namespace_id
            ),
            "workspace_id": _require_text("workspace_id", workspace_id),
            "node_id": _require_text("node_id", node_id),
            "preparation_id": _require_text("preparation_id", preparation_id),
            "workspace_solution_revision": workspace_solution_revision,
            "reason_code": _require_text("reason_code", reason_code),
        }
    )


__all__ = [
    "AssembledNodeSolution",
    "DEFAULT_PROVENANCE_HASH_POLICY",
    "DirectoryProvenance",
    "ExecutionEnvironmentIdentity",
    "FileProvenance",
    "IncomingEdgeIdentity",
    "MAX_CANONICAL_BYTES",
    "MAX_CANONICAL_DEPTH",
    "MAX_CANONICAL_ITEMS",
    "NodeSolutionIdentity",
    "ProvenanceHashPolicy",
    "SolutionIdentityError",
    "canonical_digest",
    "canonical_identity_bytes",
    "assemble_node_solution",
    "catalog_revision_digest",
    "corex_build_digest",
    "execution_policy_digest",
    "execute_only_solution_key",
    "hash_directory_provenance",
    "hash_file_provenance",
    "implementation_digest",
    "node_contract_digest",
    "provenance_digest",
    "solution_key",
]
