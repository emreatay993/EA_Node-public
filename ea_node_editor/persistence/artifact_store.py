# Purpose: Own project sidecar artifact metadata, safe paths, copy-on-write save staging, and cleanup.
# Map: feature_routes/managed_artifacts_project_data.md
# Tests: tests/test_project_artifact_store.py, tests/test_project_file_staging.py
# Landmarks: ProjectArtifactStore; stage_project_save; collect_project_save_garbage

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from uuid import uuid4

from ea_node_editor.common.payload_tools import artifact_content_integrity
from ea_node_editor.settings import (
    PROJECT_ARTIFACT_STORE_METADATA_KEY,
    PROJECT_DATA_DIR_SUFFIX,
    PROJECT_MANAGED_NODES_DIRNAME,
    PROJECT_MANAGED_WORKSPACES_DIRNAME,
    PROJECT_NODE_INPUTS_DIRNAME,
    PROJECT_NODE_OUTPUTS_DIRNAME,
    PROJECT_NODE_TEMP_DIRNAME,
)

from ea_node_editor.common.artifact_refs import (
    coerce_managed_artifact_id,
    coerce_staged_artifact_id,
    format_managed_artifact_ref,
    format_staged_artifact_ref,
    parse_artifact_ref,
)

_MANAGED_ROOT_NAMES = frozenset({PROJECT_MANAGED_NODES_DIRNAME, PROJECT_MANAGED_WORKSPACES_DIRNAME})
_NODE_IO_DIRS = frozenset({PROJECT_NODE_INPUTS_DIRNAME, PROJECT_NODE_OUTPUTS_DIRNAME})
_STAGING_ROOT_HINT_KIND_SESSION = "session_temp"
_INVALID_WINDOWS_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_COLLAPSED_SEPARATOR_CHARS = re.compile(r"[\s_-]+")
_NODE_FOLDER_PREFIX_LIMIT = 96
_UNSAFE_STAGED_DISCARD_MESSAGE = "staged artifact discard target is unsafe"
_WINDOWS_RESERVED_FILENAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CONIN$",
        "CONOUT$",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
        *(f"COM{index}" for index in "\N{SUPERSCRIPT ONE}\N{SUPERSCRIPT TWO}\N{SUPERSCRIPT THREE}"),
        *(f"LPT{index}" for index in "\N{SUPERSCRIPT ONE}\N{SUPERSCRIPT TWO}\N{SUPERSCRIPT THREE}"),
    }
)


def _coerce_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def _copy_mapping_excluding(payload: Mapping[str, Any], *excluded_keys: str) -> dict[str, Any]:
    excluded = set(excluded_keys)
    return {
        str(key): copy.deepcopy(value)
        for key, value in payload.items()
        if str(key) not in excluded
    }


def _normalize_relative_path(value: Any, *, allowed_roots: set[str] | frozenset[str] | None = None) -> str:
    text = _coerce_str(value).replace("\\", "/")
    if not text:
        return ""
    normalized_path = PurePosixPath(text)
    if normalized_path.is_absolute():
        return ""
    parts: list[str] = []
    for part in normalized_path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            return ""
        parts.append(part)
    if not parts:
        return ""
    if allowed_roots is not None and parts[0] not in allowed_roots:
        return ""
    return "/".join(parts)


def _normalize_absolute_path(value: Any) -> str | None:
    text = _coerce_str(value)
    if not text:
        return None
    path = Path(text)
    if path.is_absolute() or PureWindowsPath(text).is_absolute():
        return text
    return None


def _node_stable_key(*, workspace_id: Any, node_id: Any) -> str:
    source = f"{_coerce_str(workspace_id)}:{_coerce_str(node_id)}"
    return hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]


def _workspace_stable_key(*, workspace_id: Any) -> str:
    source = _coerce_str(workspace_id)
    return hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]


def _sanitize_node_folder_label(value: Any, *, fallback: str) -> str:
    text = _INVALID_WINDOWS_FILENAME_CHARS.sub("_", _coerce_str(value))
    text = _COLLAPSED_SEPARATOR_CHARS.sub(" ", text).strip(" ._-")
    if not text:
        text = fallback
    text = text[:_NODE_FOLDER_PREFIX_LIMIT].strip(" ._-")
    text = text or fallback
    if text.upper() in _WINDOWS_RESERVED_FILENAMES:
        text = f"{text}_"
    return text or fallback


def format_workspace_artifact_folder(
    *,
    workspace_id: Any,
    workspace_name: Any = "",
) -> str:
    stable_key = _workspace_stable_key(workspace_id=workspace_id)
    label = _sanitize_node_folder_label(workspace_name, fallback="Workspace")
    return f"{label} [{stable_key}]"


def format_node_artifact_folder(
    *,
    workspace_id: Any,
    node_id: Any,
    node_title: Any = "",
    node_type: Any = "",
) -> str:
    stable_key = _node_stable_key(workspace_id=workspace_id, node_id=node_id)
    type_label = _sanitize_node_folder_label(node_type, fallback="Node")
    title_label = _sanitize_node_folder_label(node_title, fallback="")
    if not title_label or title_label.casefold() == type_label.casefold():
        label = type_label
    else:
        label = f"{type_label} - {title_label}"
    label = label[:_NODE_FOLDER_PREFIX_LIMIT].strip(" ._-") or "Node"
    return f"{label} [{stable_key}]"


@dataclass(frozen=True, slots=True)
class _NodeRelativePathParts:
    parts: tuple[str, ...]
    workspace_folder_index: int | None
    node_folder_index: int
    content_index: int

    @property
    def is_workspace_scoped(self) -> bool:
        return self.workspace_folder_index is not None


def _node_relative_path_parts(relative_path: str | None) -> _NodeRelativePathParts | None:
    normalized = _normalize_relative_path(relative_path, allowed_roots=_MANAGED_ROOT_NAMES)
    parts = tuple(PurePosixPath(normalized).parts)
    if len(parts) >= 3 and parts[0] == PROJECT_MANAGED_NODES_DIRNAME:
        return _NodeRelativePathParts(
            parts=parts,
            workspace_folder_index=None,
            node_folder_index=1,
            content_index=2,
        )
    if (
        len(parts) >= 5
        and parts[0] == PROJECT_MANAGED_WORKSPACES_DIRNAME
        and parts[2] == PROJECT_MANAGED_NODES_DIRNAME
    ):
        return _NodeRelativePathParts(
            parts=parts,
            workspace_folder_index=1,
            node_folder_index=3,
            content_index=4,
        )
    return None


def _is_legacy_node_relative_path(relative_path: str | None) -> bool:
    parsed = _node_relative_path_parts(relative_path)
    return parsed is not None and not parsed.is_workspace_scoped


def _relative_path_with_parts(parts: tuple[str, ...] | list[str]) -> str:
    return PurePosixPath(*parts).as_posix()


def _node_tmp_relative_path_from_managed(relative_path: str) -> str:
    parsed = _node_relative_path_parts(relative_path)
    if parsed is None:
        return ""
    parts = list(parsed.parts)
    if len(parts) <= parsed.content_index or parts[parsed.content_index] not in _NODE_IO_DIRS:
        return ""
    return _relative_path_with_parts(
        [
            *parts[: parsed.content_index],
            PROJECT_NODE_TEMP_DIRNAME,
            parts[parsed.content_index],
            *parts[parsed.content_index + 1 :],
        ]
    )


def _managed_relative_path_from_node_tmp(relative_path: str | None) -> str:
    parsed = _node_relative_path_parts(relative_path)
    if parsed is None:
        return ""
    parts = list(parsed.parts)
    if len(parts) <= parsed.content_index + 1 or parts[parsed.content_index] != PROJECT_NODE_TEMP_DIRNAME:
        return ""
    if parts[parsed.content_index + 1] not in _NODE_IO_DIRS:
        return ""
    return _relative_path_with_parts(
        [
            *parts[: parsed.content_index],
            parts[parsed.content_index + 1],
            *parts[parsed.content_index + 2 :],
        ]
    )


def _replace_relative_node_folder(relative_path: str, old_folder: str, new_folder: str) -> str:
    normalized = _normalize_relative_path(relative_path, allowed_roots=_MANAGED_ROOT_NAMES)
    parsed = _node_relative_path_parts(normalized)
    if parsed is None:
        return normalized
    parts = list(parsed.parts)
    if parts[parsed.node_folder_index] != old_folder:
        return normalized
    parts[parsed.node_folder_index] = new_folder
    return _relative_path_with_parts(parts)


def _replace_relative_workspace_folder(relative_path: str, old_folder: str, new_folder: str) -> str:
    normalized = _normalize_relative_path(relative_path, allowed_roots=_MANAGED_ROOT_NAMES)
    parsed = _node_relative_path_parts(normalized)
    if parsed is None or parsed.workspace_folder_index is None:
        return normalized
    parts = list(parsed.parts)
    if parts[parsed.workspace_folder_index] != old_folder:
        return normalized
    parts[parsed.workspace_folder_index] = new_folder
    return _relative_path_with_parts(parts)


def _workspace_scoped_relative_path(relative_path: str, workspace_folder: str) -> str:
    normalized = _normalize_relative_path(relative_path, allowed_roots=_MANAGED_ROOT_NAMES)
    parsed = _node_relative_path_parts(normalized)
    if parsed is None:
        return normalized
    if parsed.workspace_folder_index is None:
        return PurePosixPath(PROJECT_MANAGED_WORKSPACES_DIRNAME, workspace_folder, normalized).as_posix()
    parts = list(parsed.parts)
    parts[parsed.workspace_folder_index] = workspace_folder
    return _relative_path_with_parts(parts)


def _normalize_node_io_dir(value: Any) -> str:
    normalized = _coerce_str(value).lower()
    if normalized in _NODE_IO_DIRS:
        return normalized
    raise ValueError("Node artifact io_dir must be 'in' or 'out'.")


def _normalize_node_subdirectory(value: Any) -> str:
    normalized = _normalize_relative_path(value)
    if not normalized:
        return ""
    parts = [
        _sanitize_node_folder_label(part, fallback="files")
        for part in PurePosixPath(normalized).parts
        if part not in {"", "."}
    ]
    return PurePosixPath(*parts).as_posix() if parts else ""


def _sanitize_artifact_filename(value: Any, *, fallback: str) -> str:
    filename = _INVALID_WINDOWS_FILENAME_CHARS.sub("_", _coerce_str(value))
    filename = filename.strip(" .")
    if not filename:
        filename = fallback
    if filename.upper() in _WINDOWS_RESERVED_FILENAMES:
        filename = f"{filename}_"
    return filename or fallback


def _delete_path_strict(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return
    path.unlink()


def _verify_strict_moved(source: Path, destination: Path) -> None:
    if source.exists():
        raise PermissionError(f"Could not release artifact folder for rename: {source}")
    if not destination.exists():
        raise FileNotFoundError(f"Artifact rename destination was not created: {destination}")


def _merge_move_path(source: Path, destination: Path, *, strict: bool = False) -> bool:
    if not source.exists() or source == destination:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir() and not source.is_symlink():
        if strict and not destination.exists():
            shutil.move(str(source), str(destination))
            _verify_strict_moved(source, destination)
            return True
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            target = destination / child.name
            if target.exists():
                if strict:
                    _delete_path_strict(target)
                else:
                    _delete_path(target)
            shutil.move(str(child), str(target))
        if strict:
            shutil.rmtree(source)
            _verify_strict_moved(source, destination)
        else:
            shutil.rmtree(source, ignore_errors=True)
        return True
    if destination.exists():
        if strict:
            _delete_path_strict(destination)
        else:
            _delete_path(destination)
    shutil.move(str(source), str(destination))
    if strict:
        _verify_strict_moved(source, destination)
    return True


def _metadata_entry_relative_path(
    payload: Mapping[str, Any],
    *,
    allowed_roots: set[str] | frozenset[str] | None = None,
) -> str:
    legacy_keys = sorted(key for key in ("path", "root") if key in payload)
    if legacy_keys:
        raise ValueError(
            "Artifact metadata entries use current keys only; "
            f"remove legacy keys: {', '.join(legacy_keys)}."
        )
    if "relative_path" not in payload:
        return ""
    return _normalize_relative_path(payload.get("relative_path"), allowed_roots=allowed_roots)


def _path_from_relative(relative_path: str) -> Path:
    return Path(*PurePosixPath(relative_path).parts)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_link_or_reparse(file_stat: Any) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(file_stat.st_mode) or bool(
        getattr(file_stat, "st_file_attributes", 0) & reparse_flag
    )


def validate_owned_artifact_path(
    root: str | Path,
    relative_path: object,
    *,
    allow_missing: bool = False,
    leaf_kind: str = "file",
) -> Path:
    """Return an owned path only when every existing component is non-reparse."""

    try:
        if leaf_kind not in {"file", "directory"}:
            raise ValueError
        source_text = os.fspath(relative_path).replace("\\", "/")
        normalized = _normalize_relative_path(relative_path)
        if not normalized or normalized != source_text:
            raise ValueError
        root_path = Path(os.path.abspath(os.fspath(root)))
        target = Path(os.path.abspath(os.path.join(root_path, *_path_from_relative(normalized).parts)))
        root_key = os.path.normcase(os.fspath(root_path))
        target_key = os.path.normcase(os.fspath(target))
        if os.path.commonpath((root_key, target_key)) != root_key:
            raise ValueError

        parts = target.parts
        current = Path(parts[0])
        candidates = [current]
        for part in parts[1:]:
            current = current / part
            candidates.append(current)
        for index, candidate in enumerate(candidates):
            try:
                candidate_stat = os.lstat(candidate)
            except FileNotFoundError:
                if allow_missing:
                    return target
                raise
            if _is_link_or_reparse(candidate_stat):
                raise ValueError
            is_leaf = index == len(candidates) - 1
            if not is_leaf and not stat.S_ISDIR(candidate_stat.st_mode):
                raise ValueError
            if is_leaf:
                expected = stat.S_ISREG if leaf_kind == "file" else stat.S_ISDIR
                if not expected(candidate_stat.st_mode):
                    raise ValueError
        return target
    except FileNotFoundError:
        raise
    except (OSError, TypeError, ValueError):
        raise ValueError("managed artifact path is unsafe") from None


def ensure_owned_artifact_directory(path: str | Path) -> Path:
    directory = Path(os.path.abspath(os.fspath(path)))
    validate_owned_artifact_path(
        directory.parent,
        directory.name,
        allow_missing=True,
        leaf_kind="directory",
    )
    directory.mkdir(parents=True, exist_ok=True)
    return validate_owned_artifact_path(
        directory.parent,
        directory.name,
        leaf_kind="directory",
    )


def _validated_staged_discard_relative_path(value: object) -> tuple[str, PurePosixPath]:
    if not isinstance(value, str):
        raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)
    normalized_relative = _normalize_relative_path(
        value,
        allowed_roots=_MANAGED_ROOT_NAMES,
    )
    if not normalized_relative or normalized_relative != value:
        raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)

    relative_path = PurePosixPath(normalized_relative)
    for part in relative_path.parts:
        windows_stem = part.split(".", 1)[0].upper()
        if (
            part.rstrip(" .") != part
            or _INVALID_WINDOWS_FILENAME_CHARS.search(part)
            or windows_stem in _WINDOWS_RESERVED_FILENAMES
        ):
            raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)
    return normalized_relative, relative_path


def _staged_discard_paths_overlap(left: PurePosixPath, right: PurePosixPath) -> bool:
    left_key = PurePosixPath(*(os.path.normcase(part) for part in left.parts))
    right_key = PurePosixPath(*(os.path.normcase(part) for part in right.parts))
    return left_key.is_relative_to(right_key) or right_key.is_relative_to(left_key)


def _lstat_staged_discard_relative_path(
    root_path: Path,
    root_key: str,
    relative_path: PurePosixPath,
) -> Path | None:
    parts = relative_path.parts
    target_path = Path(os.path.abspath(os.path.join(root_path, *parts)))
    target_key = os.path.normcase(os.fspath(target_path))
    if os.path.commonpath((root_key, target_key)) != root_key:
        raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)

    current_path = root_path
    for index, part in enumerate(parts):
        current_path = current_path / part
        try:
            current_stat = os.lstat(current_path)
        except FileNotFoundError:
            return None
        if _is_link_or_reparse(current_stat):
            raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)
        if index < len(parts) - 1:
            if not stat.S_ISDIR(current_stat.st_mode):
                raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)
        elif not (
            stat.S_ISREG(current_stat.st_mode)
            or stat.S_ISDIR(current_stat.st_mode)
        ):
            raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)
    return target_path


def _prevalidate_staged_discard_paths(
    root: Path | None,
    relative_paths: Iterable[object],
    *,
    protected_relative_paths: Iterable[object],
) -> tuple[Path, tuple[tuple[str, Path | None], ...]]:
    try:
        selected_candidates = tuple(
            _validated_staged_discard_relative_path(value)
            for value in relative_paths
        )
        protected_paths = tuple(
            _validated_staged_discard_relative_path(value)[1]
            for value in protected_relative_paths
        )

        selected_paths: list[tuple[str, PurePosixPath]] = []
        seen_selected: set[str] = set()
        for normalized_relative, relative_path in selected_candidates:
            if len(relative_path.parts) == 1:
                raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)
            selected_key = os.path.normcase(normalized_relative)
            if selected_key in seen_selected:
                continue
            seen_selected.add(selected_key)
            if any(
                _staged_discard_paths_overlap(relative_path, protected_path)
                for protected_path in protected_paths
            ):
                raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)
            selected_paths.append((normalized_relative, relative_path))

        if root is None:
            raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)
        root_path = Path(os.path.abspath(os.fspath(root)))
        root_key = os.path.normcase(os.fspath(root_path))
        root_stat = os.lstat(root_path)
        if _is_link_or_reparse(root_stat) or not stat.S_ISDIR(root_stat.st_mode):
            raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)

        for protected_path in protected_paths:
            _lstat_staged_discard_relative_path(
                root_path,
                root_key,
                protected_path,
            )

        validated_targets: list[tuple[str, Path | None]] = []
        for normalized_relative, relative_path in selected_paths:
            validated_targets.append(
                (
                    normalized_relative,
                    _lstat_staged_discard_relative_path(
                        root_path,
                        root_key,
                        relative_path,
                    ),
                )
            )
    except (OSError, TypeError, ValueError):
        raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE) from None

    return root_path, tuple(validated_targets)


def _staged_discard_stop_roots(root: Path) -> tuple[Path, ...]:
    return (
        root,
        *(root / root_name for root_name in _MANAGED_ROOT_NAMES),
    )


def _delete_path(path: Path) -> bool:
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
            return True
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _prune_empty_ancestors(path: Path, *, stop_roots: tuple[Path, ...]) -> None:
    current = path
    while current not in stop_roots:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _artifact_integrity(path: Path) -> tuple[int, str]:
    return artifact_content_integrity(path.parent, path.name)


def _digest_suffixed_relative_path(relative_path: str, digest: str) -> str:
    path = PurePosixPath(relative_path)
    suffix = Path(path.name).suffix
    stem = path.name[: -len(suffix)] if suffix else path.name
    return path.with_name(f"{stem}.{digest}{suffix}").as_posix()


def _ensure_owned_relative_parent(root: Path, relative_path: str) -> Path:
    current = ensure_owned_artifact_directory(root)
    for part in PurePosixPath(relative_path).parent.parts:
        current = ensure_owned_artifact_directory(current / part)
    return current


def _copy_artifact_cow(
    source: Path,
    destination_root: Path,
    relative_path: str,
) -> tuple[str, int]:
    source_stat = os.lstat(source)
    if _is_link_or_reparse(source_stat) or not (
        stat.S_ISREG(source_stat.st_mode) or stat.S_ISDIR(source_stat.st_mode)
    ):
        raise ValueError("artifact save source is unsafe")
    source_size, source_digest = _artifact_integrity(source)
    leaf_kind = "directory" if stat.S_ISDIR(source_stat.st_mode) else "file"

    def target_for(relative: str) -> Path:
        try:
            target = validate_owned_artifact_path(
                destination_root,
                relative,
                leaf_kind=leaf_kind,
            )
        except FileNotFoundError:
            return validate_owned_artifact_path(
                destination_root,
                relative,
                allow_missing=True,
                leaf_kind=leaf_kind,
            )
        target_size, target_digest = _artifact_integrity(target)
        if (target_size, target_digest) == (source_size, source_digest):
            return target
        raise FileExistsError

    selected_relative = relative_path
    try:
        target = target_for(selected_relative)
    except FileExistsError:
        selected_relative = _digest_suffixed_relative_path(
            relative_path,
            source_digest,
        )
        try:
            target = target_for(selected_relative)
        except FileExistsError:
            raise ValueError("immutable artifact digest target conflicts") from None
    if target.exists():
        return selected_relative, 0

    parent = _ensure_owned_relative_parent(destination_root, selected_relative)
    target = parent / PurePosixPath(selected_relative).name
    if stat.S_ISREG(source_stat.st_mode):
        fd, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=parent,
        )
        temporary_path = Path(temporary)
        try:
            with source.open("rb") as source_stream, os.fdopen(fd, "wb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)
                target_stream.flush()
                os.fsync(target_stream.fileno())
            if _artifact_integrity(source) != (source_size, source_digest):
                raise OSError("artifact source changed during copy")
            if _artifact_integrity(temporary_path) != (source_size, source_digest):
                raise OSError("artifact copy verification failed")
            try:
                os.link(temporary_path, target)
            except FileExistsError:
                if _artifact_integrity(target) != (source_size, source_digest):
                    raise ValueError("immutable artifact target changed during copy") from None
                return selected_relative, 0
        finally:
            temporary_path.unlink(missing_ok=True)
    else:
        temporary_path = Path(
            tempfile.mkdtemp(prefix=f".{target.name}.", suffix=".tmp", dir=parent)
        )
        try:
            shutil.copytree(source, temporary_path, dirs_exist_ok=True)
            if _artifact_integrity(source) != (source_size, source_digest):
                raise OSError("artifact source changed during copy")
            if _artifact_integrity(temporary_path) != (source_size, source_digest):
                raise OSError("artifact copy verification failed")
            try:
                os.rename(temporary_path, target)
            except FileExistsError:
                if _artifact_integrity(target) != (source_size, source_digest):
                    raise ValueError("immutable artifact target changed during copy") from None
                return selected_relative, 0
        finally:
            if temporary_path.exists():
                shutil.rmtree(temporary_path, ignore_errors=True)
    if _artifact_integrity(target) != (source_size, source_digest):
        raise OSError("published artifact verification failed")
    return selected_relative, source_size


@dataclass(frozen=True, slots=True)
class ProjectArtifactLayout:
    project_file: Path
    sidecar_root: Path
    workspaces_root: Path
    nodes_root: Path

    @classmethod
    def from_project_path(cls, project_path: str | Path) -> "ProjectArtifactLayout":
        project_file = Path(project_path)
        sidecar_root = project_file.with_name(f"{project_file.stem}{PROJECT_DATA_DIR_SUFFIX}")
        return cls(
            project_file=project_file,
            sidecar_root=sidecar_root,
            workspaces_root=sidecar_root / PROJECT_MANAGED_WORKSPACES_DIRNAME,
            nodes_root=sidecar_root / PROJECT_MANAGED_NODES_DIRNAME,
        )

    def absolute_path_for_relative(self, relative_path: str) -> Path:
        return self.sidecar_root.joinpath(_path_from_relative(relative_path))


@dataclass(frozen=True, slots=True)
class NodeArtifactPaths:
    workspace_folder: str
    node_folder: str
    staged_relative_path: str
    managed_relative_path: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _ArtifactOwnerContext:
    workspace_id: str = ""
    workspace_name: str = ""
    node_id: str = ""
    node_title: str = ""
    node_type: str = ""


def _workspace_values(workspaces: Mapping[str, Any] | Iterable[Any]) -> list[tuple[str, Any]]:
    if isinstance(workspaces, Mapping):
        return [(_coerce_str(key), value) for key, value in workspaces.items()]
    values: list[tuple[str, Any]] = []
    for workspace in workspaces:
        values.append((_coerce_str(getattr(workspace, "workspace_id", "")), workspace))
    return values


def _workspace_lookup(workspaces: Mapping[str, Any] | Iterable[Any]) -> dict[str, Any]:
    return {
        workspace_id: workspace
        for workspace_id, workspace in _workspace_values(workspaces)
        if workspace_id
    }


def _workspace_name(workspace: Any, *, fallback: str = "") -> str:
    return _coerce_str(getattr(workspace, "name", ""),) or fallback


def _node_values(workspace: Any) -> list[tuple[str, Any]]:
    nodes = getattr(workspace, "nodes", {})
    if isinstance(nodes, Mapping):
        return [(_coerce_str(key), value) for key, value in nodes.items()]
    return []


def _collect_artifact_ref_ids(value: Any, collected: set[str]) -> None:
    if isinstance(value, str):
        parsed = parse_artifact_ref(value)
        if parsed is not None:
            collected.add(parsed.artifact_id)
        return
    if isinstance(value, Mapping):
        for item in value.values():
            _collect_artifact_ref_ids(item, collected)
        return
    if isinstance(value, list | tuple | set | frozenset):
        for item in value:
            _collect_artifact_ref_ids(item, collected)


def _artifact_owner_lookup(workspaces: Mapping[str, Any] | Iterable[Any]) -> dict[str, _ArtifactOwnerContext]:
    lookup: dict[str, _ArtifactOwnerContext] = {}
    for workspace_id, workspace in _workspace_values(workspaces):
        if not workspace_id:
            continue
        workspace_name = _workspace_name(workspace, fallback=workspace_id)
        for node_id, node in _node_values(workspace):
            normalized_node_id = _coerce_str(getattr(node, "node_id", "")) or node_id
            if not normalized_node_id:
                continue
            ref_ids: set[str] = set()
            _collect_artifact_ref_ids(getattr(node, "properties", {}), ref_ids)
            if not ref_ids:
                continue
            context = _ArtifactOwnerContext(
                workspace_id=workspace_id,
                workspace_name=workspace_name,
                node_id=normalized_node_id,
                node_title=_coerce_str(getattr(node, "title", "")),
                node_type=_coerce_str(getattr(node, "type_id", "")),
            )
            for artifact_id in ref_ids:
                lookup.setdefault(artifact_id, context)
    return lookup


def _artifact_owner_context(
    artifact_id: str,
    extra: Mapping[str, Any],
    *,
    workspaces: Mapping[str, Any] | Iterable[Any],
    owner_lookup: Mapping[str, _ArtifactOwnerContext] | None = None,
) -> _ArtifactOwnerContext:
    workspace_id = _coerce_str(extra.get("node_workspace_id"))
    node_id = _coerce_str(extra.get("node_id"))
    workspace_map = _workspace_lookup(workspaces)
    fallback = owner_lookup.get(artifact_id) if owner_lookup is not None else None
    if not workspace_id and fallback is not None:
        workspace_id = fallback.workspace_id
    if not node_id and fallback is not None:
        node_id = fallback.node_id

    workspace = workspace_map.get(workspace_id)
    workspace_name = _workspace_name(workspace, fallback=workspace_id) if workspace is not None else ""
    if not workspace_name:
        workspace_name = _coerce_str(extra.get("node_workspace_name"))
    if not workspace_name and fallback is not None:
        workspace_name = fallback.workspace_name

    return _ArtifactOwnerContext(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        node_id=node_id,
        node_title=_coerce_str(extra.get("node_title")) or (fallback.node_title if fallback is not None else ""),
        node_type=_coerce_str(extra.get("node_type")) or (fallback.node_type if fallback is not None else ""),
    )


def _workspace_scoped_entry_payload(
    *,
    artifact_id: str,
    relative_path: str | None,
    extra: Mapping[str, Any],
    workspaces: Mapping[str, Any] | Iterable[Any],
    owner_lookup: Mapping[str, _ArtifactOwnerContext] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    payload = copy.deepcopy(dict(extra))
    if not relative_path:
        return relative_path, payload
    normalized = _normalize_relative_path(relative_path, allowed_roots=_MANAGED_ROOT_NAMES)
    parsed = _node_relative_path_parts(normalized)
    if parsed is None:
        return normalized or relative_path, payload

    owner = _artifact_owner_context(
        artifact_id,
        payload,
        workspaces=workspaces,
        owner_lookup=owner_lookup,
    )
    if not owner.workspace_id:
        return normalized, payload

    workspace_folder = format_workspace_artifact_folder(
        workspace_id=owner.workspace_id,
        workspace_name=owner.workspace_name,
    )
    node_folder = parsed.parts[parsed.node_folder_index]
    scoped_relative_path = _workspace_scoped_relative_path(normalized, workspace_folder)

    payload["node_workspace_id"] = owner.workspace_id
    payload["node_workspace_name"] = owner.workspace_name
    payload["workspace_folder"] = workspace_folder
    payload["node_folder"] = node_folder
    if owner.node_id:
        payload["node_id"] = owner.node_id
    if owner.node_title:
        payload["node_title"] = owner.node_title
    if owner.node_type:
        payload["node_type"] = owner.node_type

    managed_relative_path = _normalize_relative_path(
        payload.get("managed_relative_path"),
        allowed_roots=_MANAGED_ROOT_NAMES,
    )
    if managed_relative_path:
        payload["managed_relative_path"] = _workspace_scoped_relative_path(
            managed_relative_path,
            workspace_folder,
        )
    return scoped_relative_path, payload


@dataclass(frozen=True, slots=True)
class ManagedArtifactEntry:
    artifact_id: str
    relative_path: str
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def root_name(self) -> str:
        return PurePosixPath(self.relative_path).parts[0]

    def to_metadata_entry(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.extra)
        payload["relative_path"] = self.relative_path
        return payload

    def absolute_path(self, layout: ProjectArtifactLayout) -> Path:
        return layout.absolute_path_for_relative(self.relative_path)

    @classmethod
    def from_metadata(cls, artifact_id: str, payload: Any) -> "ManagedArtifactEntry" | None:
        normalized_id = coerce_managed_artifact_id(artifact_id)
        if not normalized_id:
            raise ValueError("Managed artifact metadata requires a non-empty artifact id.")
        if not isinstance(payload, Mapping):
            raise ValueError("Managed artifact metadata entries must be JSON objects.")
        relative_path = _metadata_entry_relative_path(payload, allowed_roots=_MANAGED_ROOT_NAMES)
        if not relative_path:
            raise ValueError("Managed artifact metadata entries require a valid relative_path.")
        return cls(
            artifact_id=normalized_id,
            relative_path=relative_path,
            extra=_copy_mapping_excluding(payload, "relative_path"),
        )


@dataclass(frozen=True, slots=True)
class StagingRootHint:
    kind: str
    absolute_path: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_metadata_entry(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.extra)
        payload["kind"] = self.kind
        payload["absolute_path"] = self.absolute_path
        return payload

    def as_path(self) -> Path:
        return Path(self.absolute_path)

    @classmethod
    def from_metadata(cls, payload: Any) -> "StagingRootHint" | None:
        if payload is None:
            return None
        if isinstance(payload, str):
            raise ValueError("staging_root must be a JSON object with absolute_path.")
        if not isinstance(payload, Mapping):
            raise ValueError("staging_root must be a JSON object with absolute_path.")
        if "path" in payload:
            raise ValueError("staging_root uses legacy key 'path'; use 'absolute_path'.")
        absolute_path = _normalize_absolute_path(payload.get("absolute_path"))
        if absolute_path is None:
            raise ValueError("staging_root requires a valid absolute_path.")
        kind = _coerce_str(payload.get("kind")) or _STAGING_ROOT_HINT_KIND_SESSION
        return cls(
            kind=kind,
            absolute_path=absolute_path,
            extra=_copy_mapping_excluding(payload, "kind", "absolute_path"),
        )


@dataclass(frozen=True, slots=True)
class StagedArtifactEntry:
    artifact_id: str
    relative_path: str | None = None
    absolute_path_hint: str | None = None
    slot: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_metadata_entry(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.extra)
        if self.relative_path:
            payload["relative_path"] = self.relative_path
        if self.absolute_path_hint:
            payload["absolute_path"] = self.absolute_path_hint
        if self.slot:
            payload["slot"] = self.slot
        return payload

    def absolute_path(
        self,
        layout: ProjectArtifactLayout | None,
        staging_root_hint: StagingRootHint | None = None,
    ) -> Path | None:
        if self.absolute_path_hint:
            return Path(self.absolute_path_hint)
        if self.relative_path:
            if staging_root_hint is not None:
                return staging_root_hint.as_path().joinpath(_path_from_relative(self.relative_path))
            if layout is not None:
                return layout.absolute_path_for_relative(self.relative_path)
        return None

    @classmethod
    def from_metadata(cls, artifact_id: str, payload: Any) -> "StagedArtifactEntry" | None:
        normalized_id = coerce_staged_artifact_id(artifact_id)
        if not normalized_id:
            raise ValueError("Staged artifact metadata requires a non-empty artifact id.")
        if not isinstance(payload, Mapping):
            raise ValueError("Staged artifact metadata entries must be JSON objects.")
        relative_path = _metadata_entry_relative_path(payload, allowed_roots=_MANAGED_ROOT_NAMES)
        absolute_path_hint = _normalize_absolute_path(payload.get("absolute_path"))
        slot = _coerce_str(payload.get("slot")) or None
        extra = _copy_mapping_excluding(payload, "absolute_path", "relative_path", "slot")
        if not relative_path and not absolute_path_hint:
            raise ValueError("Staged artifact metadata entries require relative_path or absolute_path.")
        return cls(
            artifact_id=normalized_id,
            relative_path=relative_path or None,
            absolute_path_hint=absolute_path_hint,
            slot=slot,
            extra=extra,
        )


@dataclass(frozen=True, slots=True)
class ArtifactStoreState:
    artifacts: dict[str, ManagedArtifactEntry] = field(default_factory=dict)
    staged: dict[str, StagedArtifactEntry] = field(default_factory=dict)
    staging_root: StagingRootHint | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_metadata(cls, payload: Any) -> "ArtifactStoreState":
        if payload is None:
            metadata: Mapping[str, Any] = {}
        elif isinstance(payload, Mapping):
            metadata = payload
        else:
            raise ValueError("Artifact store metadata must be a JSON object.")
        raw_artifacts = metadata.get("artifacts")
        raw_staged = metadata.get("staged")
        artifacts: dict[str, ManagedArtifactEntry] = {}
        if raw_artifacts is not None and not isinstance(raw_artifacts, Mapping):
            raise ValueError("Artifact store 'artifacts' must be a JSON object.")
        artifact_items = raw_artifacts.items() if isinstance(raw_artifacts, Mapping) else ()
        for artifact_id, entry_payload in sorted(artifact_items):
            entry = ManagedArtifactEntry.from_metadata(str(artifact_id), entry_payload)
            if entry is not None:
                artifacts[entry.artifact_id] = entry
        staged: dict[str, StagedArtifactEntry] = {}
        if raw_staged is not None and not isinstance(raw_staged, Mapping):
            raise ValueError("Artifact store 'staged' must be a JSON object.")
        staged_items = raw_staged.items() if isinstance(raw_staged, Mapping) else ()
        for artifact_id, entry_payload in sorted(staged_items):
            entry = StagedArtifactEntry.from_metadata(str(artifact_id), entry_payload)
            if entry is not None:
                staged[entry.artifact_id] = entry
        return cls(
            artifacts=artifacts,
            staged=staged,
            staging_root=StagingRootHint.from_metadata(metadata.get("staging_root")),
            extra=_copy_mapping_excluding(metadata, "artifacts", "staged", "staging_root"),
        )

    def to_metadata(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.extra)
        payload["artifacts"] = {
            artifact_id: entry.to_metadata_entry()
            for artifact_id, entry in sorted(self.artifacts.items())
        }
        payload["staged"] = {
            artifact_id: entry.to_metadata_entry()
            for artifact_id, entry in sorted(self.staged.items())
        }
        if self.staging_root is not None:
            payload["staging_root"] = self.staging_root.to_metadata_entry()
        return payload


@dataclass(frozen=True, slots=True)
class ProjectArtifactSaveStage:
    destination_store: "ProjectArtifactStore"
    ref_replacements: dict[str, str]
    previous_relative_paths: tuple[str, ...]
    retained_relative_paths: tuple[str, ...]
    cleanup_candidates: tuple[str, ...]
    promoted_artifact_ids: tuple[str, ...]
    staged_new_bytes: int
    expected_integrity_facts: tuple["ProjectArtifactIntegrityFact", ...]


@dataclass(frozen=True, slots=True)
class ProjectArtifactIntegrityFact:
    artifact_id: str
    relative_path: str
    kind: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if coerce_managed_artifact_id(self.artifact_id) != self.artifact_id:
            raise ValueError("project artifact integrity ID is invalid")
        if (
            _normalize_relative_path(
                self.relative_path,
                allowed_roots=_MANAGED_ROOT_NAMES,
            )
            != self.relative_path
            or self.kind not in {"file", "directory"}
            or type(self.size_bytes) is not int
            or self.size_bytes < 0
            or not isinstance(self.sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None
        ):
            raise ValueError("project artifact integrity fact is invalid")


@dataclass(frozen=True, slots=True)
class ProjectArtifactGcResult:
    candidate_relative_paths: tuple[str, ...]
    removed_relative_paths: tuple[str, ...]
    remaining_relative_paths: tuple[str, ...]
    has_more: bool

    def __post_init__(self) -> None:
        if type(self.has_more) is not bool:
            raise TypeError("project artifact GC has_more must be boolean")
        for values in (
            self.candidate_relative_paths,
            self.removed_relative_paths,
            self.remaining_relative_paths,
        ):
            if (
                not isinstance(values, tuple)
                or values != tuple(sorted(set(values)))
                or len(values) > 100_000
            ):
                raise ValueError("project artifact GC paths are invalid")
        candidates = set(self.candidate_relative_paths)
        removed = set(self.removed_relative_paths)
        remaining = set(self.remaining_relative_paths)
        if (
            not removed.issubset(candidates)
            or not remaining.issubset(candidates)
            or removed.intersection(remaining)
            or self.has_more != bool(remaining)
        ):
            raise ValueError("project artifact GC result is inconsistent")


def normalize_artifact_store_metadata(payload: Any) -> dict[str, Any]:
    return ArtifactStoreState.from_metadata(payload).to_metadata()


def artifact_store_metadata_from_project_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        return normalize_artifact_store_metadata(None)
    return normalize_artifact_store_metadata(metadata.get(PROJECT_ARTIFACT_STORE_METADATA_KEY))


class ProjectArtifactStore:
    def __init__(
        self,
        *,
        project_path: str | Path | None,
        metadata: Mapping[str, Any] | ArtifactStoreState | None = None,
    ) -> None:
        self._project_path = Path(project_path) if project_path else None
        self._state = metadata if isinstance(metadata, ArtifactStoreState) else ArtifactStoreState.from_metadata(metadata)

    @classmethod
    def from_project_metadata(
        cls,
        *,
        project_path: str | Path | None,
        project_metadata: Mapping[str, Any] | None,
    ) -> "ProjectArtifactStore":
        return cls(
            project_path=project_path,
            metadata=artifact_store_metadata_from_project_metadata(project_metadata),
        )

    @property
    def project_path(self) -> Path | None:
        return self._project_path

    @property
    def layout(self) -> ProjectArtifactLayout | None:
        if self._project_path is None:
            return None
        return ProjectArtifactLayout.from_project_path(self._project_path)

    @property
    def state(self) -> ArtifactStoreState:
        return self._state

    @property
    def metadata(self) -> dict[str, Any]:
        return self._state.to_metadata()

    @property
    def staging_root_hint(self) -> StagingRootHint | None:
        return self._state.staging_root

    def project_save_context_digest(self) -> str:
        project_path = (
            os.path.normcase(os.path.abspath(os.fspath(self._project_path)))
            if self._project_path is not None
            else ""
        )
        raw = json.dumps(
            {
                "schema_version": 1,
                "project_path": project_path,
                "metadata": self.metadata,
            },
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def expected_integrity_facts(
        self,
        artifact_ids: Iterable[object],
    ) -> tuple[ProjectArtifactIntegrityFact, ...]:
        layout = self.layout
        if layout is None:
            raise ValueError("project path is required for artifact integrity")
        facts: list[ProjectArtifactIntegrityFact] = []
        normalized_ids = tuple(
            sorted(
                {
                    artifact_id
                    for artifact_id in (
                        coerce_managed_artifact_id(value) for value in artifact_ids
                    )
                    if artifact_id
                }
            )
        )
        for artifact_id in normalized_ids:
            entry = self.managed_entry(artifact_id)
            if entry is None:
                raise ValueError("expected managed artifact is not registered")
            target = entry.absolute_path(layout)
            target_stat = os.lstat(target)
            if _is_link_or_reparse(target_stat):
                raise ValueError("expected managed artifact is unsafe")
            if stat.S_ISREG(target_stat.st_mode):
                kind = "file"
            elif stat.S_ISDIR(target_stat.st_mode):
                kind = "directory"
            else:
                raise ValueError("expected managed artifact kind is invalid")
            validated = validate_owned_artifact_path(
                layout.sidecar_root,
                entry.relative_path,
                leaf_kind=kind,
            )
            if validated != target:
                raise ValueError("expected managed artifact path is invalid")
            size_bytes, sha256 = _artifact_integrity(target)
            facts.append(
                ProjectArtifactIntegrityFact(
                    artifact_id=artifact_id,
                    relative_path=entry.relative_path,
                    kind=kind,
                    size_bytes=size_bytes,
                    sha256=sha256,
                )
            )
        return tuple(facts)

    def managed_ref(self, artifact_id: str) -> str:
        return format_managed_artifact_ref(artifact_id)

    def staged_ref(self, artifact_id: str) -> str:
        return format_staged_artifact_ref(artifact_id)

    def node_artifact_paths(
        self,
        *,
        artifact_id: str,
        workspace_id: Any,
        workspace_name: Any = "",
        node_id: Any,
        node_title: Any = "",
        node_type: Any = "",
        io_dir: str,
        subdirectory: Any = "",
        filename: Any = "",
    ) -> NodeArtifactPaths:
        normalized_artifact_id = coerce_staged_artifact_id(artifact_id)
        if not normalized_artifact_id:
            raise ValueError(f"Invalid node artifact id: {artifact_id!r}")
        normalized_io_dir = _normalize_node_io_dir(io_dir)
        workspace_folder = format_workspace_artifact_folder(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
        )
        node_folder = format_node_artifact_folder(
            workspace_id=workspace_id,
            node_id=node_id,
            node_title=node_title,
            node_type=node_type,
        )
        normalized_subdirectory = _normalize_node_subdirectory(subdirectory)
        normalized_filename = _sanitize_artifact_filename(
            filename,
            fallback=normalized_artifact_id,
        )
        tail_parts = [
            *PurePosixPath(normalized_subdirectory).parts,
            normalized_filename,
        ] if normalized_subdirectory else [normalized_filename]
        managed_relative_path = PurePosixPath(
            PROJECT_MANAGED_WORKSPACES_DIRNAME,
            workspace_folder,
            PROJECT_MANAGED_NODES_DIRNAME,
            node_folder,
            normalized_io_dir,
            *tail_parts,
        ).as_posix()
        staged_relative_path = _node_tmp_relative_path_from_managed(managed_relative_path)
        metadata = {
            "managed_relative_path": managed_relative_path,
            "node_workspace_id": _coerce_str(workspace_id),
            "node_workspace_name": _coerce_str(workspace_name),
            "workspace_folder": workspace_folder,
            "node_id": _coerce_str(node_id),
            "node_title": _coerce_str(node_title),
            "node_type": _coerce_str(node_type),
            "node_folder": node_folder,
            "io_dir": normalized_io_dir,
        }
        return NodeArtifactPaths(
            workspace_folder=workspace_folder,
            node_folder=node_folder,
            staged_relative_path=staged_relative_path,
            managed_relative_path=managed_relative_path,
            metadata=metadata,
        )

    def managed_entry(self, artifact_id_or_ref: object) -> ManagedArtifactEntry | None:
        artifact_id = coerce_managed_artifact_id(artifact_id_or_ref)
        if not artifact_id:
            return None
        return self._state.artifacts.get(artifact_id)

    def staged_entry(self, artifact_id_or_ref: object) -> StagedArtifactEntry | None:
        artifact_id = coerce_staged_artifact_id(artifact_id_or_ref)
        if not artifact_id:
            return None
        return self._state.staged.get(artifact_id)

    def resolve_managed_path(self, artifact_id_or_ref: object) -> Path | None:
        entry = self.managed_entry(artifact_id_or_ref)
        layout = self.layout
        if entry is None or layout is None:
            return None
        return entry.absolute_path(layout)

    def inspect_durable_artifact(self, value: object) -> Path:
        """Verify one managed runtime artifact without catalog or value callbacks."""

        from ea_node_editor.runtime_contracts.value_refs import RuntimeArtifactRef

        if type(value) is not RuntimeArtifactRef or value.scope != "managed":
            raise ValueError("durable artifact must be an exact managed reference")
        entry = self.managed_entry(value.artifact_id)
        layout = self.layout
        if entry is None or layout is None:
            raise FileNotFoundError("durable artifact is not registered")
        resolved_path = entry.absolute_path(layout)
        trusted_path = layout.absolute_path_for_relative(entry.relative_path)
        if (
            os.path.normcase(os.path.abspath(os.fspath(resolved_path)))
            != os.path.normcase(os.path.abspath(os.fspath(trusted_path)))
        ):
            raise ValueError("durable artifact target does not match")
        descriptor = entry.extra.get("runtime_artifact")
        expected_descriptor = {
            "data_type_id": value.data_type_id,
            "schema_version": value.schema_version,
            "format": value.format,
            "size_bytes": value.size_bytes,
            "sha256": value.sha256,
            "provenance": value.provenance,
        }
        if (
            type(descriptor) is not dict
            or set(descriptor) != set(expected_descriptor)
            or any(
                type(descriptor.get(field_name)) is not type(expected_value)
                or descriptor.get(field_name) != expected_value
                for field_name, expected_value in expected_descriptor.items()
            )
        ):
            raise ValueError("durable artifact descriptor does not match")
        size_bytes, sha256 = artifact_content_integrity(
            layout.sidecar_root,
            entry.relative_path,
        )
        if size_bytes != value.size_bytes or sha256 != value.sha256:
            raise ValueError("durable artifact content does not match")
        return resolved_path

    def resolve_staged_path(self, artifact_id_or_ref: object) -> Path | None:
        entry = self.staged_entry(artifact_id_or_ref)
        if entry is None:
            return None
        return entry.absolute_path(self.layout, self._state.staging_root)

    def active_staging_root(self) -> Path | None:
        if self._state.staging_root is not None:
            return self._state.staging_root.as_path()
        layout = self.layout
        return layout.sidecar_root if layout is not None else None

    def staged_target_path(self, relative_path: object) -> Path:
        normalized_relative = _normalize_relative_path(
            relative_path,
            allowed_roots=_MANAGED_ROOT_NAMES,
        )
        if not normalized_relative:
            raise ValueError("staged target requires a valid relative path")
        root = self.active_staging_root()
        if root is None:
            raise ValueError("staging root has not been allocated")
        return root.joinpath(_path_from_relative(normalized_relative))

    def ensure_staging_root(self, *, temporary_root_parent: str | Path | None = None) -> Path:
        layout = self.layout
        if layout is not None:
            layout.workspaces_root.mkdir(parents=True, exist_ok=True)
            return layout.sidecar_root

        if self._state.staging_root is not None:
            root = self._state.staging_root.as_path()
            root.mkdir(parents=True, exist_ok=True)
            return root

        if temporary_root_parent is None:
            raise ValueError("temporary_root_parent is required for unsaved project staging")

        parent = Path(temporary_root_parent)
        parent.mkdir(parents=True, exist_ok=True)
        root = parent / f"project-{uuid4().hex}"
        root.mkdir(parents=True, exist_ok=False)
        self._state = replace(
            self._state,
            staging_root=StagingRootHint(
                kind=_STAGING_ROOT_HINT_KIND_SESSION,
                absolute_path=str(root),
            ),
        )
        return root

    def clear_staging_root_hint(self) -> None:
        if self._state.staging_root is None:
            return
        self._state = replace(self._state, staging_root=None)

    def workspace_scoped_managed_entry(
        self,
        entry: ManagedArtifactEntry,
        *,
        workspaces: Mapping[str, Any] | Iterable[Any],
    ) -> ManagedArtifactEntry:
        return self._workspace_scoped_managed_entry(
            entry,
            workspaces=workspaces,
            owner_lookup=_artifact_owner_lookup(workspaces),
        )

    def workspace_scoped_staged_entry(
        self,
        entry: StagedArtifactEntry,
        *,
        workspaces: Mapping[str, Any] | Iterable[Any],
    ) -> StagedArtifactEntry:
        return self._workspace_scoped_staged_entry(
            entry,
            workspaces=workspaces,
            owner_lookup=_artifact_owner_lookup(workspaces),
        )

    def migrate_workspace_artifact_folders(
        self,
        *,
        workspaces: Mapping[str, Any] | Iterable[Any],
    ) -> bool:
        if not self._state.artifacts and not self._state.staged:
            return False
        if not any(
            _is_legacy_node_relative_path(relative_path)
            for entries in (self._state.artifacts.values(), self._state.staged.values())
            for entry in entries
            for relative_path in (entry.relative_path, entry.extra.get("managed_relative_path"))
        ):
            return False

        owner_lookup = _artifact_owner_lookup(workspaces)
        changed = False
        stop_roots = self._cleanup_stop_roots()
        layout = self.layout

        artifacts: dict[str, ManagedArtifactEntry] = {}
        for artifact_id, entry in self._state.artifacts.items():
            source_path = entry.absolute_path(layout) if layout is not None else None
            scoped_entry = self._workspace_scoped_managed_entry(
                entry,
                workspaces=workspaces,
                owner_lookup=owner_lookup,
            )
            destination_path = scoped_entry.absolute_path(layout) if layout is not None else None
            if (
                source_path is not None
                and destination_path is not None
                and source_path != destination_path
                and _merge_move_path(source_path, destination_path)
            ):
                _prune_empty_ancestors(source_path.parent, stop_roots=stop_roots)
                changed = True
            changed = changed or scoped_entry != entry
            artifacts[artifact_id] = scoped_entry

        staged: dict[str, StagedArtifactEntry] = {}
        for artifact_id, entry in self._state.staged.items():
            source_path = entry.absolute_path(layout, self._state.staging_root)
            scoped_entry = self._workspace_scoped_staged_entry(
                entry,
                workspaces=workspaces,
                owner_lookup=owner_lookup,
            )
            destination_path = scoped_entry.absolute_path(layout, self._state.staging_root)
            if (
                source_path is not None
                and destination_path is not None
                and source_path != destination_path
                and _merge_move_path(source_path, destination_path)
            ):
                _prune_empty_ancestors(source_path.parent, stop_roots=stop_roots)
                changed = True
            changed = changed or scoped_entry != entry
            staged[artifact_id] = scoped_entry

        if changed:
            self._state = replace(self._state, artifacts=artifacts, staged=staged)
        return changed

    def rename_workspace_artifact_folder(
        self,
        *,
        workspace_id: Any,
        old_name: Any,
        new_name: Any,
    ) -> bool:
        normalized_workspace_id = _coerce_str(workspace_id)
        if not normalized_workspace_id:
            return False
        old_folder = format_workspace_artifact_folder(
            workspace_id=normalized_workspace_id,
            workspace_name=old_name,
        )
        new_folder = format_workspace_artifact_folder(
            workspace_id=normalized_workspace_id,
            workspace_name=new_name,
        )

        def _relative_workspace_folder(relative_path: str | None) -> str:
            parsed = _node_relative_path_parts(relative_path)
            if parsed is None or parsed.workspace_folder_index is None:
                return ""
            return parsed.parts[parsed.workspace_folder_index]

        def _matches_workspace(entry: ManagedArtifactEntry | StagedArtifactEntry) -> bool:
            return (
                _coerce_str(entry.extra.get("node_workspace_id")) == normalized_workspace_id
                or _relative_workspace_folder(entry.relative_path) == old_folder
            )

        def _updated_extra(extra: Mapping[str, Any]) -> dict[str, Any]:
            payload = copy.deepcopy(dict(extra))
            managed_relative_path = _normalize_relative_path(
                payload.get("managed_relative_path"),
                allowed_roots=_MANAGED_ROOT_NAMES,
            )
            if managed_relative_path:
                payload["managed_relative_path"] = _replace_relative_workspace_folder(
                    managed_relative_path,
                    old_folder,
                    new_folder,
                )
            payload["node_workspace_id"] = normalized_workspace_id
            payload["node_workspace_name"] = _coerce_str(new_name)
            payload["workspace_folder"] = new_folder
            return payload

        changed = False
        artifacts: dict[str, ManagedArtifactEntry] = {}
        for artifact_id, entry in self._state.artifacts.items():
            if not _matches_workspace(entry):
                artifacts[artifact_id] = entry
                continue
            relative_path = _replace_relative_workspace_folder(entry.relative_path, old_folder, new_folder)
            updated_entry = replace(entry, relative_path=relative_path, extra=_updated_extra(entry.extra))
            changed = changed or updated_entry != entry
            artifacts[artifact_id] = updated_entry

        staged: dict[str, StagedArtifactEntry] = {}
        for artifact_id, entry in self._state.staged.items():
            if not _matches_workspace(entry):
                staged[artifact_id] = entry
                continue
            relative_path = (
                _replace_relative_workspace_folder(entry.relative_path, old_folder, new_folder)
                if entry.relative_path
                else None
            )
            updated_entry = replace(entry, relative_path=relative_path, extra=_updated_extra(entry.extra))
            changed = changed or updated_entry != entry
            staged[artifact_id] = updated_entry

        roots: list[Path] = []
        layout = self.layout
        if layout is not None:
            roots.append(layout.workspaces_root)
        if self._state.staging_root is not None:
            roots.append(self._state.staging_root.as_path() / PROJECT_MANAGED_WORKSPACES_DIRNAME)

        stop_roots = self._cleanup_stop_roots()
        for workspace_root in roots:
            source = workspace_root / old_folder
            destination = workspace_root / new_folder
            if _merge_move_path(source, destination):
                _prune_empty_ancestors(source.parent, stop_roots=stop_roots)
                changed = True

        if changed:
            self._state = replace(self._state, artifacts=artifacts, staged=staged)
        return changed

    def register_staged_entry(
        self,
        artifact_id: str,
        *,
        relative_path: str | None = None,
        absolute_path_hint: str | Path | None = None,
        slot: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> StagedArtifactEntry:
        normalized_id = coerce_staged_artifact_id(artifact_id)
        if not normalized_id:
            raise ValueError(f"Invalid staged artifact id: {artifact_id!r}")

        normalized_relative = _normalize_relative_path(relative_path, allowed_roots=_MANAGED_ROOT_NAMES) or None
        normalized_absolute = _normalize_absolute_path(absolute_path_hint)
        normalized_slot = _coerce_str(slot) or None
        payload_extra = copy.deepcopy(dict(extra)) if isinstance(extra, Mapping) else {}

        if not normalized_relative and not normalized_absolute:
            raise ValueError("A staged entry requires a relative path or an absolute path hint")

        entry = StagedArtifactEntry(
            artifact_id=normalized_id,
            relative_path=normalized_relative,
            absolute_path_hint=normalized_absolute,
            slot=normalized_slot,
            extra=payload_extra,
        )

        current_state = self._state
        displaced_entries: list[tuple[str, StagedArtifactEntry]] = []
        current_entry = current_state.staged.get(normalized_id)
        if current_entry is not None:
            displaced_entries.append((normalized_id, current_entry))
        for existing_id, existing_entry in current_state.staged.items():
            if existing_id == normalized_id or not normalized_slot:
                continue
            if existing_entry.slot == normalized_slot:
                displaced_entries.append((existing_id, existing_entry))

        if any(
            displaced_entry.absolute_path_hint is not None
            for _, displaced_entry in displaced_entries
        ):
            raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)

        next_staged = dict(current_state.staged)
        for displaced_id, _ in displaced_entries:
            next_staged.pop(displaced_id, None)
        next_staged[normalized_id] = entry

        cleanup_relative_paths = tuple(
            displaced_entry.relative_path
            for _, displaced_entry in displaced_entries
            if not (
                normalized_relative is not None
                and displaced_entry.relative_path == normalized_relative
            )
        )
        root: Path | None = None
        validated_targets: tuple[tuple[str, Path | None], ...] = ()
        if cleanup_relative_paths:
            if any(
                staged_entry.absolute_path_hint is not None
                for staged_entry in next_staged.values()
            ):
                raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)
            protected_relative_paths = (
                *(managed_entry.relative_path for managed_entry in current_state.artifacts.values()),
                *(
                    staged_entry.relative_path
                    for staged_entry in next_staged.values()
                    if staged_entry.relative_path is not None
                ),
            )
            root, validated_targets = _prevalidate_staged_discard_paths(
                self.active_staging_root(),
                cleanup_relative_paths,
                protected_relative_paths=protected_relative_paths,
            )

        self._state = replace(current_state, staged=next_staged)
        if root is not None:
            stop_roots = _staged_discard_stop_roots(root)
            for _, target in sorted(
                validated_targets,
                key=lambda item: len(PurePosixPath(item[0]).parts),
                reverse=True,
            ):
                if target is not None and _delete_path(target):
                    _prune_empty_ancestors(target.parent, stop_roots=stop_roots)
        return entry

    def discard_staged_payloads(self) -> bool:
        removed_any = False
        roots_to_remove: list[Path] = []
        if self.layout is None and self._state.staging_root is not None:
            roots_to_remove.append(self._state.staging_root.as_path())

        deduped_roots: list[Path] = []
        seen_roots: set[str] = set()
        for root in roots_to_remove:
            key = str(root)
            if key in seen_roots:
                continue
            seen_roots.add(key)
            deduped_roots.append(root)

        for root in sorted(deduped_roots, key=lambda item: len(item.parts), reverse=True):
            if root.exists():
                shutil.rmtree(root, ignore_errors=True)
                removed_any = True

        stop_roots = self._cleanup_stop_roots()
        for entry in self._state.staged.values():
            path = entry.absolute_path(self.layout, self._state.staging_root)
            if path is None:
                continue
            if any(path == root or _is_relative_to(path, root) for root in deduped_roots):
                continue
            if _delete_path(path):
                removed_any = True
                _prune_empty_ancestors(path.parent, stop_roots=stop_roots)

        if self._state.staging_root is not None:
            self._state = replace(self._state, staging_root=None)
        return removed_any

    def discard_staged_entries(self, artifact_ids: Iterable[object]) -> tuple[str, ...]:
        normalized_ids: list[str] = []
        seen_ids: set[str] = set()
        for value in artifact_ids:
            artifact_id = coerce_staged_artifact_id(value)
            if not artifact_id or artifact_id in seen_ids:
                continue
            seen_ids.add(artifact_id)
            normalized_ids.append(artifact_id)

        if not normalized_ids:
            return ()

        current_state = self._state
        selected_entries = tuple(
            (artifact_id, current_state.staged[artifact_id])
            for artifact_id in normalized_ids
            if artifact_id in current_state.staged
        )
        if not selected_entries:
            return ()

        if any(entry.absolute_path_hint is not None for _, entry in selected_entries):
            raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)

        selected_ids = frozenset(artifact_id for artifact_id, _ in selected_entries)
        if any(
            artifact_id not in selected_ids and entry.absolute_path_hint is not None
            for artifact_id, entry in current_state.staged.items()
        ):
            raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)
        protected_relative_paths = (
            *(entry.relative_path for entry in current_state.artifacts.values()),
            *(
                entry.relative_path
                for artifact_id, entry in current_state.staged.items()
                if artifact_id not in selected_ids and entry.relative_path is not None
            ),
        )
        root, validated_targets = _prevalidate_staged_discard_paths(
            self.active_staging_root(),
            (entry.relative_path for _, entry in selected_entries),
            protected_relative_paths=protected_relative_paths,
        )
        stop_roots = _staged_discard_stop_roots(root)
        for _, target in sorted(
            validated_targets,
            key=lambda item: len(PurePosixPath(item[0]).parts),
            reverse=True,
        ):
            if target is not None and _delete_path(target):
                _prune_empty_ancestors(target.parent, stop_roots=stop_roots)

        staged = dict(current_state.staged)
        removed_ids = []
        for artifact_id, _ in selected_entries:
            staged.pop(artifact_id)
            removed_ids.append(artifact_id)
        self._state = replace(current_state, staged=staged)
        return tuple(removed_ids)

    def discard_staged_paths(self, relative_paths: Iterable[object]) -> tuple[str, ...]:
        try:
            requested_paths = tuple(relative_paths)
        except TypeError:
            raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE) from None
        if not requested_paths:
            return ()

        current_state = self._state
        if any(
            entry.absolute_path_hint is not None
            for entry in current_state.staged.values()
        ):
            raise ValueError(_UNSAFE_STAGED_DISCARD_MESSAGE)
        protected_relative_paths = (
            *(entry.relative_path for entry in current_state.artifacts.values()),
            *(
                entry.relative_path
                for entry in current_state.staged.values()
                if entry.relative_path is not None
            ),
        )
        root, validated_targets = _prevalidate_staged_discard_paths(
            self.active_staging_root(),
            requested_paths,
            protected_relative_paths=protected_relative_paths,
        )
        stop_roots = _staged_discard_stop_roots(root)
        for _, target in sorted(
            validated_targets,
            key=lambda item: len(PurePosixPath(item[0]).parts),
            reverse=True,
        ):
            if target is not None and _delete_path(target):
                _prune_empty_ancestors(target.parent, stop_roots=stop_roots)
        return tuple(relative_path for relative_path, _ in validated_targets)

    def rename_node_artifact_folder(
        self,
        *,
        workspace_id: Any,
        node_id: Any,
        old_title: Any,
        new_title: Any,
        node_type: Any = "",
    ) -> bool:
        normalized_workspace_id = _coerce_str(workspace_id)
        normalized_node_id = _coerce_str(node_id)
        if not normalized_node_id:
            return False
        old_folder = format_node_artifact_folder(
            workspace_id=normalized_workspace_id,
            node_id=normalized_node_id,
            node_title=old_title,
            node_type=node_type,
        )
        new_folder = format_node_artifact_folder(
            workspace_id=normalized_workspace_id,
            node_id=normalized_node_id,
            node_title=new_title,
            node_type=node_type,
        )

        def _matches_node(extra: Mapping[str, Any]) -> bool:
            return (
                _coerce_str(extra.get("node_workspace_id")) == normalized_workspace_id
                and _coerce_str(extra.get("node_id")) == normalized_node_id
            )

        def _updated_extra(extra: Mapping[str, Any]) -> dict[str, Any]:
            payload = copy.deepcopy(dict(extra))
            managed_relative_path = _normalize_relative_path(
                payload.get("managed_relative_path"),
                allowed_roots=_MANAGED_ROOT_NAMES,
            )
            if managed_relative_path:
                payload["managed_relative_path"] = _replace_relative_node_folder(
                    managed_relative_path,
                    old_folder,
                    new_folder,
                )
            payload["node_title"] = _coerce_str(new_title)
            payload["node_type"] = _coerce_str(node_type)
            payload["node_folder"] = new_folder
            return payload

        changed = False
        artifacts: dict[str, ManagedArtifactEntry] = {}
        for artifact_id, entry in self._state.artifacts.items():
            if not _matches_node(entry.extra):
                artifacts[artifact_id] = entry
                continue
            relative_path = _replace_relative_node_folder(entry.relative_path, old_folder, new_folder)
            updated_entry = replace(entry, relative_path=relative_path, extra=_updated_extra(entry.extra))
            changed = changed or updated_entry != entry
            artifacts[artifact_id] = updated_entry

        staged: dict[str, StagedArtifactEntry] = {}
        for artifact_id, entry in self._state.staged.items():
            if not _matches_node(entry.extra):
                staged[artifact_id] = entry
                continue
            relative_path = (
                _replace_relative_node_folder(entry.relative_path, old_folder, new_folder)
                if entry.relative_path
                else None
            )
            updated_entry = replace(entry, relative_path=relative_path, extra=_updated_extra(entry.extra))
            changed = changed or updated_entry != entry
            staged[artifact_id] = updated_entry

        roots: list[Path] = []
        layout = self.layout
        if layout is not None:
            roots.append(layout.nodes_root)
            for entry in (*artifacts.values(), *staged.values()):
                parsed = _node_relative_path_parts(entry.relative_path)
                if parsed is None or parsed.workspace_folder_index is None:
                    continue
                workspace_folder = parsed.parts[parsed.workspace_folder_index]
                roots.append(layout.workspaces_root / workspace_folder / PROJECT_MANAGED_NODES_DIRNAME)
        if self._state.staging_root is not None:
            roots.append(self._state.staging_root.as_path() / PROJECT_MANAGED_NODES_DIRNAME)
            for entry in (*artifacts.values(), *staged.values()):
                parsed = _node_relative_path_parts(entry.relative_path)
                if parsed is None or parsed.workspace_folder_index is None:
                    continue
                workspace_folder = parsed.parts[parsed.workspace_folder_index]
                roots.append(
                    self._state.staging_root.as_path()
                    / PROJECT_MANAGED_WORKSPACES_DIRNAME
                    / workspace_folder
                    / PROJECT_MANAGED_NODES_DIRNAME
                )
        deduped_roots: list[Path] = []
        seen_roots: set[str] = set()
        for nodes_root in roots:
            root_key = str(nodes_root)
            if root_key in seen_roots:
                continue
            seen_roots.add(root_key)
            deduped_roots.append(nodes_root)
        for nodes_root in deduped_roots:
            source = nodes_root / old_folder
            destination = nodes_root / new_folder
            if _merge_move_path(source, destination, strict=True):
                changed = True

        if changed:
            self._state = replace(self._state, artifacts=artifacts, staged=staged)
        return changed

    def stage_project_save(
        self,
        *,
        destination_project_path: str | Path,
        workspaces: Mapping[str, Any] | Iterable[Any],
        referenced_managed_ids: Iterable[object] = (),
        referenced_staged_ids: Iterable[object] = (),
        required_managed_artifact_ids: Iterable[object] = (),
    ) -> ProjectArtifactSaveStage:
        destination_path = Path(destination_project_path)
        destination_layout = ProjectArtifactLayout.from_project_path(destination_path)
        destination_root = ensure_owned_artifact_directory(destination_layout.sidecar_root)
        document_managed_ids = {
            artifact_id
            for artifact_id in (
                coerce_managed_artifact_id(value) for value in referenced_managed_ids
            )
            if artifact_id
        }
        solution_managed_ids = {
            artifact_id
            for artifact_id in (
                coerce_managed_artifact_id(value)
                for value in required_managed_artifact_ids
            )
            if artifact_id
        }
        staged_ids = {
            artifact_id
            for artifact_id in (
                coerce_staged_artifact_id(value) for value in referenced_staged_ids
            )
            if artifact_id
        }
        owner_lookup = _artifact_owner_lookup(workspaces)
        artifacts: dict[str, ManagedArtifactEntry] = {}
        replacements: dict[str, str] = {}
        promoted: list[str] = []
        staged_new_bytes = 0

        for artifact_id in sorted(document_managed_ids | solution_managed_ids):
            entry = self._state.artifacts.get(artifact_id)
            if entry is None:
                if artifact_id in document_managed_ids:
                    raise ValueError("referenced managed artifact is not registered")
                continue
            source = self.resolve_managed_path(artifact_id)
            if source is None or not source.exists():
                if artifact_id in document_managed_ids:
                    raise ValueError("referenced managed artifact is missing")
                continue
            scoped = self._workspace_scoped_managed_entry(
                entry,
                workspaces=workspaces,
                owner_lookup=owner_lookup,
            )
            selected_relative, copied_bytes = _copy_artifact_cow(
                source,
                destination_root,
                scoped.relative_path,
            )
            artifacts[artifact_id] = replace(
                scoped,
                relative_path=selected_relative,
            )
            staged_new_bytes += copied_bytes

        for artifact_id in sorted(staged_ids):
            entry = self._state.staged.get(artifact_id)
            if entry is None:
                raise ValueError("referenced staged artifact is not registered")
            source = self.resolve_staged_path(artifact_id)
            if source is None or not source.exists():
                raise ValueError("referenced staged artifact is missing")
            scoped = self._workspace_scoped_staged_entry(
                entry,
                workspaces=workspaces,
                owner_lookup=owner_lookup,
            )
            relative_path = self._managed_relative_path_for_staged_entry(
                artifact_id,
                scoped,
                source_path=source,
            )
            selected_relative, copied_bytes = _copy_artifact_cow(
                source,
                destination_root,
                relative_path,
            )
            artifacts[artifact_id] = ManagedArtifactEntry(
                artifact_id=artifact_id,
                relative_path=selected_relative,
                extra=self._managed_extra_from_staged_entry(scoped),
            )
            replacements[self.staged_ref(artifact_id)] = self.managed_ref(artifact_id)
            promoted.append(artifact_id)
            staged_new_bytes += copied_bytes

        same_project = bool(
            self._project_path is not None
            and os.path.normcase(os.path.abspath(os.fspath(self._project_path)))
            == os.path.normcase(os.path.abspath(os.fspath(destination_path)))
        )
        previous_relative_paths = (
            tuple(
                sorted(
                    {
                        *(entry.relative_path for entry in self._state.artifacts.values()),
                        *(
                            entry.relative_path
                            for entry in self._state.staged.values()
                            if entry.relative_path is not None
                        ),
                    }
                )
            )
            if same_project
            else ()
        )
        retained_relative_paths = tuple(
            sorted(entry.relative_path for entry in artifacts.values())
        )
        destination_store = ProjectArtifactStore(
            project_path=destination_path,
            metadata=ArtifactStoreState(
                artifacts=artifacts,
                staged={},
                staging_root=None,
                extra=copy.deepcopy(self._state.extra),
            ),
        )
        return ProjectArtifactSaveStage(
            destination_store=destination_store,
            ref_replacements=replacements,
            previous_relative_paths=previous_relative_paths,
            retained_relative_paths=retained_relative_paths,
            cleanup_candidates=tuple(
                sorted(set(previous_relative_paths) - set(retained_relative_paths))
            ),
            promoted_artifact_ids=tuple(promoted),
            staged_new_bytes=staged_new_bytes,
            expected_integrity_facts=destination_store.expected_integrity_facts(
                artifacts
            ),
        )

    @staticmethod
    def collect_project_save_garbage(
        *,
        project_path: str | Path,
        candidate_relative_paths: Iterable[str],
        protected_relative_paths: Iterable[str],
        limit: int = 10_000,
    ) -> ProjectArtifactGcResult:
        root = ProjectArtifactLayout.from_project_path(project_path).sidecar_root
        protected: set[str] = set()
        for index, relative in enumerate(protected_relative_paths):
            if index >= 100_000:
                break
            protected.add(relative)
        candidates: set[str] = set()
        for index, relative in enumerate(candidate_relative_paths):
            if index >= 100_000:
                break
            candidates.add(relative)
        ordered_candidates = tuple(sorted(candidates))
        selected = ordered_candidates[: min(max(int(limit), 0), 10_000)]
        removed: list[str] = []
        remaining: set[str] = set(ordered_candidates[len(selected) :])
        scanned = 0
        for relative in selected:
            relative_path = PurePosixPath(relative)
            if any(
                relative_path.is_relative_to(PurePosixPath(item))
                or PurePosixPath(item).is_relative_to(relative_path)
                for item in protected
            ):
                remaining.add(relative)
                continue
            normalized = _normalize_relative_path(relative, allowed_roots=_MANAGED_ROOT_NAMES)
            if not normalized or normalized != relative:
                remaining.add(relative)
                continue
            try:
                file_target = validate_owned_artifact_path(root, relative)
                target_stat = os.lstat(file_target)
            except FileNotFoundError:
                removed.append(relative)
                continue
            except ValueError:
                try:
                    file_target = validate_owned_artifact_path(
                        root,
                        relative,
                        leaf_kind="directory",
                    )
                    target_stat = os.lstat(file_target)
                except (FileNotFoundError, OSError, ValueError):
                    remaining.add(relative)
                    continue
            if stat.S_ISREG(target_stat.st_mode):
                try:
                    file_target.unlink()
                except OSError:
                    remaining.add(relative)
                    continue
                removed.append(relative)
                continue
            if not stat.S_ISDIR(target_stat.st_mode):
                remaining.add(relative)
                continue
            safe = True
            for directory, directory_names, filenames in os.walk(file_target):
                scanned += len(directory_names) + len(filenames)
                if scanned > 100_000:
                    safe = False
                    break
                for name in (*directory_names, *filenames):
                    try:
                        child_stat = os.lstat(Path(directory) / name)
                    except OSError:
                        safe = False
                        break
                    if _is_link_or_reparse(child_stat):
                        safe = False
                        break
                if not safe:
                    break
            if not safe:
                remaining.add(relative)
                continue
            try:
                shutil.rmtree(file_target)
            except OSError:
                remaining.add(relative)
                continue
            removed.append(relative)
        return ProjectArtifactGcResult(
            candidate_relative_paths=ordered_candidates,
            removed_relative_paths=tuple(sorted(removed)),
            remaining_relative_paths=tuple(sorted(remaining)),
            has_more=bool(remaining),
        )

    def _cleanup_stop_roots(self) -> tuple[Path, ...]:
        roots: list[Path] = []
        if self.layout is not None:
            roots.append(self.layout.sidecar_root)
        if self._state.staging_root is not None:
            roots.append(self._state.staging_root.as_path())
        return tuple(roots)

    def _workspace_scoped_managed_entry(
        self,
        entry: ManagedArtifactEntry,
        *,
        workspaces: Mapping[str, Any] | Iterable[Any],
        owner_lookup: Mapping[str, _ArtifactOwnerContext],
    ) -> ManagedArtifactEntry:
        relative_path, extra = _workspace_scoped_entry_payload(
            artifact_id=entry.artifact_id,
            relative_path=entry.relative_path,
            extra=entry.extra,
            workspaces=workspaces,
            owner_lookup=owner_lookup,
        )
        if not relative_path:
            return entry
        return replace(entry, relative_path=relative_path, extra=extra)

    def _workspace_scoped_staged_entry(
        self,
        entry: StagedArtifactEntry,
        *,
        workspaces: Mapping[str, Any] | Iterable[Any],
        owner_lookup: Mapping[str, _ArtifactOwnerContext],
    ) -> StagedArtifactEntry:
        relative_path, extra = _workspace_scoped_entry_payload(
            artifact_id=entry.artifact_id,
            relative_path=entry.relative_path,
            extra=entry.extra,
            workspaces=workspaces,
            owner_lookup=owner_lookup,
        )
        return replace(entry, relative_path=relative_path, extra=extra)

    def _managed_relative_path_for_staged_entry(
        self,
        artifact_id: str,
        entry: StagedArtifactEntry,
        *,
        source_path: Path | None,
    ) -> str:
        existing_entry = self._state.artifacts.get(artifact_id)
        if existing_entry is not None:
            return existing_entry.relative_path

        managed_relative_path = _normalize_relative_path(
            entry.extra.get("managed_relative_path"),
            allowed_roots=_MANAGED_ROOT_NAMES,
        )
        if managed_relative_path:
            return managed_relative_path

        source_relative_path = _managed_relative_path_from_node_tmp(entry.relative_path)
        if source_relative_path:
            return source_relative_path

        source_suffix = ""
        if source_path is not None:
            source_suffix = source_path.suffix
        elif entry.absolute_path_hint:
            source_suffix = Path(entry.absolute_path_hint).suffix
        node_folder = _sanitize_node_folder_label(entry.extra.get("node_folder"), fallback="")
        if not node_folder:
            node_folder = format_node_artifact_folder(
                workspace_id=entry.extra.get("node_workspace_id", ""),
                node_id=entry.extra.get("node_id", artifact_id),
                node_title=entry.extra.get("node_title", ""),
                node_type=entry.extra.get("node_type", "Node"),
            )
        filename = _sanitize_artifact_filename(f"{artifact_id}{source_suffix}", fallback=artifact_id)
        return PurePosixPath(
            PROJECT_MANAGED_WORKSPACES_DIRNAME,
            format_workspace_artifact_folder(
                workspace_id=entry.extra.get("node_workspace_id", ""),
                workspace_name=entry.extra.get("node_workspace_name", ""),
            ),
            PROJECT_MANAGED_NODES_DIRNAME,
            node_folder,
            PROJECT_NODE_OUTPUTS_DIRNAME,
            filename,
        ).as_posix()

    @staticmethod
    def _managed_extra_from_staged_entry(entry: StagedArtifactEntry) -> dict[str, Any]:
        payload = copy.deepcopy(entry.extra)
        payload.pop("managed_relative_path", None)
        if entry.slot:
            payload["slot"] = entry.slot
        return payload
