from __future__ import annotations

import json
from collections.abc import Sequence

CategoryPath = tuple[str, ...]

CATEGORY_DISPLAY_SEPARATOR = " > "
MAX_CATEGORY_PATH_DEPTH = 10
MIN_CATEGORY_PATH_DEPTH = 1


def normalize_category_path(path: Sequence[str]) -> CategoryPath:
    if isinstance(path, str):
        raise TypeError("category_path must be a sequence of strings, not a string")

    segments = tuple(path)
    if not (MIN_CATEGORY_PATH_DEPTH <= len(segments) <= MAX_CATEGORY_PATH_DEPTH):
        raise ValueError(
            "category_path must contain "
            f"{MIN_CATEGORY_PATH_DEPTH}..{MAX_CATEGORY_PATH_DEPTH} segments"
        )

    normalized: list[str] = []
    for segment in segments:
        if not isinstance(segment, str):
            raise TypeError("category_path segments must be strings")
        trimmed = segment.strip()
        if not trimmed:
            raise ValueError("category_path segments must be non-empty trimmed strings")
        normalized.append(trimmed)
    return tuple(normalized)


def category_display(path: Sequence[str]) -> str:
    return CATEGORY_DISPLAY_SEPARATOR.join(normalize_category_path(path))


def category_key(path: Sequence[str]) -> str:
    return json.dumps(normalize_category_path(path), ensure_ascii=True, separators=(",", ":"))


def category_path_matches_prefix(path: Sequence[str], prefix: Sequence[str]) -> bool:
    normalized_path = normalize_category_path(path)
    normalized_prefix = normalize_category_path(prefix)
    return normalized_path[: len(normalized_prefix)] == normalized_prefix


def category_path_ancestors(path: Sequence[str]) -> tuple[CategoryPath, ...]:
    normalized_path = normalize_category_path(path)
    return tuple(normalized_path[:depth] for depth in range(1, len(normalized_path) + 1))


__all__ = [
    "CATEGORY_DISPLAY_SEPARATOR",
    "MAX_CATEGORY_PATH_DEPTH",
    "MIN_CATEGORY_PATH_DEPTH",
    "CategoryPath",
    "category_display",
    "category_key",
    "category_path_ancestors",
    "category_path_matches_prefix",
    "normalize_category_path",
]
