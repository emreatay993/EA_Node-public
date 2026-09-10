"""Shared JSON / mapping payload helpers.

Moved here from ``ea_node_editor/persistence/utils.py`` because these helpers
are used across layers (persistence, app preferences, controllers), so they
belong in the shared ``common`` leaf rather than inside ``persistence``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import stat
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

JSON_MAX_DEPTH = 32
INLINE_PAYLOAD_MAX_BYTES = 1024 * 1024
REF_METADATA_MAX_BYTES = 64 * 1024
_ARTIFACT_HASH_CHUNK_SIZE = 1024 * 1024
_ARTIFACT_TREE_HASH_HEADER = b"corex-artifact-tree-v1\0"

_SECRET_KEY_PARTS = (
    "apikey",
    "password",
    "secret",
    "token",
    "credential",
    "authorization",
    "cookie",
    "privatekey",
)
_OPAQUE_SECRET_MARKERS = frozenset({"secret_data", "ssh_sftp_host_data"})


def copy_json_safe(
    value: Any,
    *,
    field_name: str,
    max_depth: int = JSON_MAX_DEPTH,
    max_encoded_bytes: int | None = None,
    reject_sensitive_metadata: bool = False,
) -> Any:
    """Return a detached, strict JSON value or fail before wire encoding."""

    def copy_item(item: Any, depth: int) -> Any:
        if depth > max_depth:
            raise ValueError(f"{field_name} exceeds maximum JSON depth {max_depth}")
        if item is None or isinstance(item, (str, bool, int)):
            if (
                reject_sensitive_metadata
                and isinstance(item, str)
                and _is_absolute_path(item)
            ):
                raise ValueError(f"{field_name} must not contain absolute paths")
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError(
                    f"{field_name} must contain only finite JSON-safe numbers"
                )
            return item
        if isinstance(item, Mapping):
            if (
                reject_sensitive_metadata
                and item.get("__ea_runtime_value__") in _OPAQUE_SECRET_MARKERS
            ):
                raise ValueError(
                    f"{field_name} contains forbidden sensitive runtime data"
                )
            copied: dict[str, Any] = {}
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise TypeError(
                        f"{field_name} mapping keys must be strings"
                    )
                if reject_sensitive_metadata and _is_secret_key(key):
                    raise ValueError(
                        f"{field_name} contains prohibited metadata key"
                    )
                copied[key] = copy_item(nested, depth + 1)
            return copied
        if isinstance(item, (list, tuple)):
            return [copy_item(nested, depth + 1) for nested in item]
        raise TypeError(
            f"{field_name} must contain only strict JSON values; "
            f"received {type(item).__name__}"
        )

    copied = copy_item(value, 0)
    if max_encoded_bytes is not None:
        encoded_size = len(
            json.dumps(
                copied,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if encoded_size > max_encoded_bytes:
            raise ValueError(
                f"{field_name} exceeds encoded size limit {max_encoded_bytes} bytes"
            )
    return copied


def copy_json_mapping(
    value: Mapping[str, Any] | None,
    *,
    field_name: str,
    max_encoded_bytes: int | None = None,
    reject_sensitive_metadata: bool = False,
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    copied = copy_json_safe(
        value,
        field_name=field_name,
        max_encoded_bytes=max_encoded_bytes,
        reject_sensitive_metadata=reject_sensitive_metadata,
    )
    return dict(copied)


def validate_payload_fields(
    payload: Mapping[str, Any],
    *,
    label: str,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    """Require an exact set of fields while keeping stable error text."""

    missing = required.difference(payload)
    if missing:
        raise ValueError(f"{label} is missing: " + ", ".join(sorted(missing)))
    unexpected = set(payload).difference(required | optional)
    if unexpected:
        raise ValueError(
            f"{label} has unexpected fields: "
            + ", ".join(sorted(str(key) for key in unexpected))
        )


def compact_sequence_metadata(
    field_name: str,
    values: Iterable[Any],
    *,
    max_inline_items: int = 64,
    max_inline_bytes: int = 8 * 1024,
    sample_items: int = 16,
    max_sample_bytes: int = 4 * 1024,
) -> dict[str, Any]:
    """Return deterministic exact-or-summary metadata for a JSON sequence."""

    normalized_field_name = str(field_name).strip()
    if not normalized_field_name:
        raise ValueError("field_name must be a non-empty string")
    normalized_values = tuple(
        copy_json_safe(item, field_name=f"{normalized_field_name} item")
        for item in values
    )
    digest = hashlib.sha256()
    digest.update(b"[")
    encoded_items: list[bytes] = []
    encoded_size = 2
    for index, item in enumerate(normalized_values):
        encoded = json.dumps(
            item,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        encoded_items.append(encoded)
        if index:
            digest.update(b",")
            encoded_size += 1
        digest.update(encoded)
        encoded_size += len(encoded)
    digest.update(b"]")

    metadata: dict[str, Any] = {
        f"{normalized_field_name}_count": len(normalized_values),
    }
    if (
        len(normalized_values) <= max_inline_items
        and encoded_size <= max_inline_bytes
    ):
        metadata[normalized_field_name] = list(normalized_values)
        return metadata

    sample: list[Any] = []
    sample_size = 2
    for item, encoded in zip(
        normalized_values[:sample_items],
        encoded_items[:sample_items],
        strict=True,
    ):
        candidate_size = sample_size + len(encoded) + (1 if sample else 0)
        if candidate_size > max_sample_bytes:
            break
        sample.append(item)
        sample_size = candidate_size
    metadata[f"{normalized_field_name}_sample"] = sample
    metadata[f"{normalized_field_name}_sha256"] = digest.hexdigest()
    return metadata


def artifact_content_integrity(
    trusted_root: str | Path,
    relative_path: str,
) -> tuple[int, str]:
    """Hash one artifact below a trusted root without following links."""

    try:
        root_path = Path(os.path.abspath(os.fspath(trusted_root)))
        relative_parts = _artifact_relative_parts(relative_path)
        root_stat = os.lstat(root_path)
        _reject_artifact_link(root_stat, nested=False)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ValueError("artifact trusted root must be a directory")

        component_stats: list[tuple[Path, Any]] = [(root_path, root_stat)]
        artifact_path = root_path
        for index, part in enumerate(relative_parts):
            artifact_path = artifact_path / part
            component_stat = os.lstat(artifact_path)
            _reject_artifact_link(component_stat, nested=True)
            if (
                index < len(relative_parts) - 1
                and not stat.S_ISDIR(component_stat.st_mode)
            ):
                raise ValueError(
                    "artifact payload parent components must be directories"
                )
            component_stats.append((artifact_path, component_stat))

        artifact_stat = component_stats[-1][1]
        if stat.S_ISREG(artifact_stat.st_mode):
            digest = hashlib.sha256()
            size_bytes = _hash_artifact_file(
                artifact_path,
                expected_stat=artifact_stat,
                digest=digest,
            )
        elif stat.S_ISDIR(artifact_stat.st_mode):
            digest = hashlib.sha256(_ARTIFACT_TREE_HASH_HEADER)
            _update_artifact_tree_entry(digest, b"D", b"")
            size_bytes = _hash_artifact_directory(
                artifact_path,
                relative_parent="",
                expected_stat=artifact_stat,
                digest=digest,
            )
        else:
            raise ValueError(
                "artifact payload must be a regular file or directory"
            )

        for component_path, expected_stat in component_stats[:-1]:
            current_stat = os.lstat(component_path)
            _reject_artifact_link(current_stat, nested=True)
            _require_artifact_binding(
                expected_stat,
                current_stat,
                compare_size=False,
                compare_mtime=True,
            )
        return size_bytes, digest.hexdigest()
    except FileNotFoundError:
        raise FileNotFoundError("artifact payload is missing") from None
    except ValueError:
        raise
    except OSError as exc:
        if str(exc) == "artifact payload changed while hashing":
            raise
        raise OSError("artifact payload could not be inspected") from None


def _hash_artifact_directory(
    directory: Path,
    *,
    relative_parent: str,
    expected_stat: Any,
    digest: Any,
) -> int:
    current_stat = os.lstat(directory)
    _reject_artifact_link(current_stat, nested=True)
    if not stat.S_ISDIR(current_stat.st_mode):
        raise OSError("artifact payload changed while hashing")
    _require_artifact_binding(
        expected_stat,
        current_stat,
        compare_size=False,
        compare_mtime=True,
    )

    size_bytes = 0
    with os.scandir(directory) as iterator:
        entries = sorted(iterator, key=lambda entry: entry.name)
        for entry in entries:
            entry_stat = os.lstat(entry.path)
            _reject_artifact_link(entry_stat, nested=True)
            relative_path = (
                f"{relative_parent}/{entry.name}"
                if relative_parent
                else entry.name
            )
            relative_bytes = relative_path.encode("utf-8")
            if stat.S_ISDIR(entry_stat.st_mode):
                _update_artifact_tree_entry(digest, b"D", relative_bytes)
                size_bytes += _hash_artifact_directory(
                    Path(entry.path),
                    relative_parent=relative_path,
                    expected_stat=entry_stat,
                    digest=digest,
                )
                continue
            if not stat.S_ISREG(entry_stat.st_mode):
                raise ValueError(
                    "artifact payload must contain only regular files "
                    "and directories"
                )
            _update_artifact_tree_entry(
                digest,
                b"F",
                relative_bytes,
                size_bytes=entry_stat.st_size,
            )
            size_bytes += _hash_artifact_file(
                Path(entry.path),
                expected_stat=entry_stat,
                digest=digest,
            )

    final_stat = os.lstat(directory)
    _reject_artifact_link(final_stat, nested=True)
    _require_artifact_binding(
        expected_stat,
        final_stat,
        compare_size=False,
        compare_mtime=True,
    )
    return size_bytes


def _hash_artifact_file(
    path: Path,
    *,
    expected_stat: Any,
    digest: Any,
) -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    actual_size = 0
    try:
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise OSError("artifact payload changed while hashing")
        _require_artifact_binding(
            expected_stat,
            opened_stat,
            compare_size=True,
            compare_mtime=True,
        )
        while chunk := os.read(descriptor, _ARTIFACT_HASH_CHUNK_SIZE):
            actual_size += len(chunk)
            digest.update(chunk)
        final_opened_stat = os.fstat(descriptor)
        _require_artifact_binding(
            opened_stat,
            final_opened_stat,
            compare_size=True,
            compare_mtime=True,
        )
    finally:
        os.close(descriptor)

    final_path_stat = os.lstat(path)
    _reject_artifact_link(final_path_stat, nested=True)
    _require_artifact_binding(
        expected_stat,
        final_path_stat,
        compare_size=True,
        compare_mtime=True,
    )
    _require_artifact_binding(
        final_opened_stat,
        final_path_stat,
        compare_size=True,
        compare_mtime=True,
    )
    if actual_size != expected_stat.st_size:
        raise OSError("artifact payload changed while hashing")
    return actual_size


def _artifact_relative_parts(relative_path: str) -> tuple[str, ...]:
    if not isinstance(relative_path, str):
        raise TypeError("artifact relative path must be a string")
    normalized = PurePosixPath(relative_path.replace("\\", "/"))
    if normalized.is_absolute():
        raise ValueError("artifact relative path is invalid")
    parts = tuple(
        part for part in normalized.parts if part not in {"", "."}
    )
    if not parts or ".." in parts:
        raise ValueError("artifact relative path is invalid")
    return parts


def _require_artifact_binding(
    expected_stat: Any,
    actual_stat: Any,
    *,
    compare_size: bool,
    compare_mtime: bool,
) -> None:
    if (
        getattr(expected_stat, "st_dev", None)
        != getattr(actual_stat, "st_dev", None)
        or getattr(expected_stat, "st_ino", None)
        != getattr(actual_stat, "st_ino", None)
        or stat.S_IFMT(expected_stat.st_mode)
        != stat.S_IFMT(actual_stat.st_mode)
    ):
        raise OSError("artifact payload changed while hashing")
    if compare_size and expected_stat.st_size != actual_stat.st_size:
        raise OSError("artifact payload changed while hashing")
    expected_mtime = getattr(expected_stat, "st_mtime_ns", None)
    actual_mtime = getattr(actual_stat, "st_mtime_ns", None)
    if (
        compare_mtime
        and expected_mtime is not None
        and actual_mtime is not None
        and expected_mtime != actual_mtime
    ):
        raise OSError("artifact payload changed while hashing")


def _reject_artifact_link(file_stat: Any, *, nested: bool) -> None:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(file_stat, "st_file_attributes", 0)
    if stat.S_ISLNK(file_stat.st_mode) or (
        reparse_flag and file_attributes & reparse_flag
    ):
        location = "contain symbolic links or reparse points" if nested else (
            "be a symbolic link or reparse point"
        )
        raise ValueError(f"artifact payload must not {location}")


def _update_artifact_tree_entry(
    digest: Any,
    kind: bytes,
    relative_path: bytes,
    *,
    size_bytes: int | None = None,
) -> None:
    digest.update(kind)
    digest.update(len(relative_path).to_bytes(8, "big"))
    digest.update(relative_path)
    if size_bytes is not None:
        digest.update(size_bytes.to_bytes(8, "big"))


def _is_secret_key(value: str) -> bool:
    normalized = "".join(char for char in value.casefold() if char.isalnum())
    return any(part in normalized for part in _SECRET_KEY_PARTS)


def _is_absolute_path(value: str) -> bool:
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def merge_defaults(values: Any, defaults: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(defaults)
    if not isinstance(values, Mapping):
        return merged
    for key, value in values.items():
        normalized_key = str(key)
        if (
            normalized_key in merged
            and isinstance(merged[normalized_key], dict)
            and isinstance(value, Mapping)
        ):
            merged[normalized_key] = merge_defaults(dict(value), merged[normalized_key])
        else:
            merged[normalized_key] = copy.deepcopy(value)
    return merged


def coerce_timestamp(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def encode_json_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


def document_fingerprint(project_doc: dict[str, Any], *, encoded_payload: str | None = None) -> str:
    canonical_payload = encoded_payload if encoded_payload is not None else encode_json_payload(project_doc)
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
    *,
    encoded_payload: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(
        encoded_payload if encoded_payload is not None else encode_json_payload(payload),
        encoding="utf-8",
    )
    temp_path.replace(path)
