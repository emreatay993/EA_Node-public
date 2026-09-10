from __future__ import annotations

# Purpose: Load central tooltip-copy JSON files for PyQt and QML lookups.
# Map: docs/agent_maps/feature_routes/tooltips_and_tiers.md
# Tests: tests/test_tooltip_copy_registry.py

import json
from functools import lru_cache
from importlib import resources

from ea_node_editor.ui.shell.tooltip_policy import (
    TOOLTIP_CATEGORY_GENERAL,
    TOOLTIP_CATEGORY_NAMES,
)

TOOLTIP_COPY_FILES = (
    "actions.json",
    "nodes.json",
    "settings.json",
    "graph.json",
    "inspector.json",
    "shell.json",
    "fullscreen.json",
    "viewer.json",
    "tabular.json",
)


@lru_cache(maxsize=1)
def tooltip_copy_registry() -> dict[str, dict[str, str]]:
    registry: dict[str, dict[str, str]] = {}
    for filename in TOOLTIP_COPY_FILES:
        data = json.loads(resources.files(__package__).joinpath(filename).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{filename} must contain a JSON object")
        for key, entry in data.items():
            if key in registry:
                raise ValueError(f"Duplicate tooltip copy key: {key}")
            if not isinstance(entry, dict):
                raise ValueError(f"{filename}:{key} must be a JSON object")
            text = str(entry.get("text", ""))
            category = str(entry.get("category", TOOLTIP_CATEGORY_GENERAL))
            if category not in TOOLTIP_CATEGORY_NAMES:
                raise ValueError(f"{filename}:{key} uses unknown tooltip category {category!r}")
            registry[str(key)] = {"text": text, "category": category}
    return registry


def tooltip_entry(key: object) -> dict[str, str] | None:
    return tooltip_copy_registry().get(str(key))


def tooltip_text(key: object, default: str = "") -> str:
    entry = tooltip_entry(key)
    if entry is None:
        return default
    return entry["text"]


def tooltip_category(key: object, default: str = TOOLTIP_CATEGORY_GENERAL) -> str:
    entry = tooltip_entry(key)
    if entry is None:
        return default
    return entry["category"]


def _clear_tooltip_copy_cache() -> None:
    tooltip_copy_registry.cache_clear()


__all__ = [
    "TOOLTIP_COPY_FILES",
    "_clear_tooltip_copy_cache",
    "tooltip_category",
    "tooltip_copy_registry",
    "tooltip_entry",
    "tooltip_text",
]
