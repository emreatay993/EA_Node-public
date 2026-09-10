# Purpose: Externalize immutable ImageValue bytes into content-addressed project sidecar blobs.
# Map: subsystems/persistence
# Tests: tests/test_image_value.py
from __future__ import annotations

import copy
import hashlib
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ea_node_editor.persistence.artifact_store import (
    ProjectArtifactLayout,
    ensure_owned_artifact_directory,
    validate_owned_artifact_path,
)
from ea_node_editor.runtime_contracts import (
    IMAGE_VALUE_MAX_ENCODED_BYTES,
    DataTypeCatalog,
    ImageValue,
)

PROJECT_IMAGE_MARKER_KEY = "__ea_project_image__"
PROJECT_IMAGE_MARKER_VALUE = "image_blob"
PROJECT_IMAGE_METADATA_KEY = "image_blobs"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_MAX_RAW_BYTES = (IMAGE_VALUE_MAX_ENCODED_BYTES // 4) * 3
MAX_PROJECT_IMAGE_SCAN_ENTRIES = 100_000
MAX_PROJECT_IMAGE_GC_CANDIDATES = 10_000


@dataclass(frozen=True, slots=True)
class ProjectImageStage:
    document: dict[str, Any]
    previous_digests: frozenset[str]
    retained_digests: frozenset[str]
    cleanup_candidates: tuple[str, ...]
    staged_new_bytes: int


@dataclass(frozen=True, slots=True)
class ProjectImageGcResult:
    candidate_digests: tuple[str, ...]
    removed_digests: tuple[str, ...]
    remaining_digests: tuple[str, ...]
    has_more: bool

    def __post_init__(self) -> None:
        if type(self.has_more) is not bool:
            raise TypeError("project image GC has_more must be boolean")
        for values in (
            self.candidate_digests,
            self.removed_digests,
            self.remaining_digests,
        ):
            if (
                not isinstance(values, tuple)
                or values != tuple(sorted(set(values)))
                or len(values) > MAX_PROJECT_IMAGE_SCAN_ENTRIES
                or any(_SHA256_PATTERN.fullmatch(value) is None for value in values)
            ):
                raise ValueError("project image GC digests are invalid")
        candidates = set(self.candidate_digests)
        removed = set(self.removed_digests)
        remaining = set(self.remaining_digests)
        if (
            not removed.issubset(candidates)
            or not remaining.issubset(candidates)
            or removed.intersection(remaining)
            or self.has_more != bool(remaining)
        ):
            raise ValueError("project image GC result is inconsistent")


def _image_root(project_path: str | Path) -> Path:
    return ProjectArtifactLayout.from_project_path(project_path).sidecar_root / "images"


def _write_blob(root: Path, image: ImageValue) -> bool:
    root = ensure_owned_artifact_directory(root)
    try:
        target = validate_owned_artifact_path(root, f"{image.sha256}.png")
    except FileNotFoundError:
        target = validate_owned_artifact_path(root, f"{image.sha256}.png", allow_missing=True)
    else:
        if os.lstat(target).st_size > _MAX_RAW_BYTES:
            raise ValueError("project image digest conflict")
        existing = target.read_bytes()
        if len(existing) == len(image.encoded_bytes) and hashlib.sha256(existing).hexdigest() == image.sha256:
            return False
        raise ValueError("project image digest conflict")
    fd, temporary = tempfile.mkstemp(prefix=f".{image.sha256}.", suffix=".tmp", dir=root)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(image.encoded_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, target)
        except FileExistsError:
            winner = validate_owned_artifact_path(root, target.name)
            if os.lstat(winner).st_size > _MAX_RAW_BYTES:
                raise ValueError("project image digest conflict") from None
            existing = winner.read_bytes()
            if existing != image.encoded_bytes:
                raise ValueError("project image digest conflict") from None
            return False
        if validate_owned_artifact_path(root, target.name).read_bytes() != image.encoded_bytes:
            raise OSError("project image publication verification failed")
        return True
    finally:
        temporary_path.unlink(missing_ok=True)


def _project_marker(image: ImageValue) -> dict[str, Any]:
    return {
        PROJECT_IMAGE_MARKER_KEY: PROJECT_IMAGE_MARKER_VALUE,
        "schema_version": image.schema_version,
        "format": image.format,
        "width": image.width,
        "height": image.height,
        "sha256": image.sha256,
    }


def externalize_project_images(
    document: Mapping[str, Any],
    *,
    project_path: str | Path,
    catalog: DataTypeCatalog,
) -> dict[str, Any]:
    return stage_project_images(
        document,
        project_path=project_path,
        catalog=catalog,
    ).document


def stage_project_images(
    document: Mapping[str, Any],
    *,
    project_path: str | Path,
    catalog: DataTypeCatalog,
    previous_document: Mapping[str, Any] | None = None,
) -> ProjectImageStage:
    root = _image_root(project_path)
    referenced: set[str] = set()
    staged_new_bytes = 0

    def visit(value: Any) -> Any:
        if isinstance(value, Mapping):
            if value.get("__ea_runtime_value__") == "image_value":
                image = ImageValue.from_payload(value, catalog=catalog)
                if image is None:
                    raise ValueError("persistent ImageValue payload is incomplete")
                nonlocal staged_new_bytes
                if _write_blob(root, image):
                    staged_new_bytes += len(image.encoded_bytes)
                referenced.add(image.sha256)
                return _project_marker(image)
            return {str(key): visit(item) for key, item in value.items()}
        if isinstance(value, list):
            return [visit(item) for item in value]
        return copy.deepcopy(value)

    prepared = visit(document)
    if not isinstance(prepared, dict):
        raise TypeError("project document must be a mapping")
    metadata = dict(prepared.get("metadata", {})) if isinstance(prepared.get("metadata"), Mapping) else {}
    if referenced:
        metadata[PROJECT_IMAGE_METADATA_KEY] = sorted(referenced)
    else:
        metadata.pop(PROJECT_IMAGE_METADATA_KEY, None)
    prepared["metadata"] = metadata

    previous_digests = (
        tracked_project_image_digests(previous_document)
        if isinstance(previous_document, Mapping)
        else frozenset()
    )
    retained_digests = frozenset(referenced)
    return ProjectImageStage(
        document=prepared,
        previous_digests=previous_digests,
        retained_digests=retained_digests,
        cleanup_candidates=tuple(sorted(previous_digests - retained_digests)),
        staged_new_bytes=staged_new_bytes,
    )


def tracked_project_image_digests(document: Mapping[str, Any]) -> frozenset[str]:
    metadata = document.get("metadata")
    if not isinstance(metadata, Mapping):
        return frozenset()
    values = metadata.get(PROJECT_IMAGE_METADATA_KEY)
    if not isinstance(values, list):
        return frozenset()
    return frozenset(
        value
        for value in values[:MAX_PROJECT_IMAGE_SCAN_ENTRIES]
        if isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None
    )


def prune_project_images(
    *,
    project_path: str | Path,
    tracked_digests: frozenset[str] | set[str],
    retained_digests: frozenset[str] | set[str],
) -> None:
    collect_project_image_garbage(
        project_path=project_path,
        candidate_digests=tuple(sorted(set(tracked_digests) - set(retained_digests))),
        protected_digests=retained_digests,
    )


def collect_project_image_garbage(
    *,
    project_path: str | Path,
    candidate_digests: tuple[str, ...],
    protected_digests: frozenset[str] | set[str] = frozenset(),
    limit: int = MAX_PROJECT_IMAGE_GC_CANDIDATES,
) -> ProjectImageGcResult:
    root = _image_root(project_path)
    protected = set(protected_digests)
    removed: list[str] = []
    bounded_candidates: set[str] = set()
    for index, digest in enumerate(candidate_digests):
        if index >= MAX_PROJECT_IMAGE_SCAN_ENTRIES:
            break
        bounded_candidates.add(digest)
    ordered_candidates = tuple(sorted(bounded_candidates))
    selected = ordered_candidates[
        : min(max(int(limit), 0), MAX_PROJECT_IMAGE_GC_CANDIDATES)
    ]
    remaining: set[str] = set(ordered_candidates[len(selected) :])
    for digest in selected:
        if _SHA256_PATTERN.fullmatch(digest) is None:
            continue
        if digest in protected:
            remaining.add(digest)
            continue
        try:
            validate_owned_artifact_path(root, f"{digest}.png").unlink()
        except FileNotFoundError:
            removed.append(digest)
            continue
        except (OSError, ValueError):
            remaining.add(digest)
            continue
        removed.append(digest)
    try:
        validate_owned_artifact_path(
            root.parent,
            root.name,
            leaf_kind="directory",
        ).rmdir()
    except (FileNotFoundError, OSError, ValueError):
        pass
    return ProjectImageGcResult(
        candidate_digests=ordered_candidates,
        removed_digests=tuple(sorted(removed)),
        remaining_digests=tuple(sorted(remaining)),
        has_more=bool(remaining),
    )


def hydrate_project_images(
    document: Mapping[str, Any],
    *,
    project_path: str | Path,
    catalog: DataTypeCatalog,
) -> dict[str, Any]:
    root = _image_root(project_path)

    def visit(value: Any) -> Any:
        if isinstance(value, Mapping):
            if PROJECT_IMAGE_MARKER_KEY in value:
                expected = {
                    PROJECT_IMAGE_MARKER_KEY,
                    "schema_version",
                    "format",
                    "width",
                    "height",
                    "sha256",
                }
                if set(value) != expected or value[PROJECT_IMAGE_MARKER_KEY] != PROJECT_IMAGE_MARKER_VALUE:
                    raise ValueError("persistent image blob marker is invalid")
                digest = value["sha256"]
                if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
                    raise ValueError("persistent image blob sha256 is invalid")
                try:
                    path = validate_owned_artifact_path(root, f"{digest}.png")
                except FileNotFoundError:
                    raise ValueError(f"persistent image blob is missing or too large: {digest}") from None
                if os.lstat(path).st_size > _MAX_RAW_BYTES:
                    raise ValueError(f"persistent image blob is missing or too large: {digest}")
                image = ImageValue.from_png(path.read_bytes())
                if (
                    image.sha256 != digest
                    or image.schema_version != value["schema_version"]
                    or image.format != value["format"]
                    or image.width != value["width"]
                    or image.height != value["height"]
                ):
                    raise ValueError(f"persistent image blob metadata does not match: {digest}")
                return image.to_payload(catalog=catalog)
            return {str(key): visit(item) for key, item in value.items()}
        if isinstance(value, list):
            return [visit(item) for item in value]
        return copy.deepcopy(value)

    hydrated = visit(document)
    if not isinstance(hydrated, dict):
        raise TypeError("project document must be a mapping")
    return hydrated


__all__ = [
    "PROJECT_IMAGE_MARKER_KEY",
    "PROJECT_IMAGE_MARKER_VALUE",
    "PROJECT_IMAGE_METADATA_KEY",
    "ProjectImageStage",
    "ProjectImageGcResult",
    "collect_project_image_garbage",
    "externalize_project_images",
    "hydrate_project_images",
    "prune_project_images",
    "stage_project_images",
    "tracked_project_image_digests",
]
