from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "node_catalog"
CURRENT_REPO_OWNED_CATALOG_PATH = FIXTURE_DIR / "current_repo_owned_catalog.json"
SOLUTION_REUSE_CLASSIFICATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "specs"
    / "perf"
    / "COREX_SOLUTION_REUSE_CLASSIFICATION.md"
)


def load_current_repo_owned_catalog(
    path: Path = CURRENT_REPO_OWNED_CATALOG_PATH,
) -> list[dict[str, Any]]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, list):
        raise ValueError("Repo-owned catalog must be a list")
    type_ids = [
        row.get("spec", {}).get("type_id")
        for row in catalog
        if isinstance(row, dict) and isinstance(row.get("spec"), dict)
    ]
    if len(type_ids) != len(catalog) or any(not isinstance(type_id, str) for type_id in type_ids):
        raise ValueError("Repo-owned catalog row is invalid")
    if len(type_ids) != len(set(type_ids)):
        raise ValueError("Repo-owned catalog type IDs must be unique")
    return catalog


def load_solution_reuse_scopes(
    path: Path = SOLUTION_REUSE_CLASSIFICATION_PATH,
) -> dict[str, str]:
    section = ""
    scopes: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "## Executable Row Inventory":
            section = "executable"
            continue
        if line == "## Excluded Row Inventory":
            section = "excluded"
            continue
        if line.startswith("## "):
            section = ""
            continue
        if not section or not line.startswith("| `"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        expected_columns = 14 if section == "executable" else 7
        if len(cells) != expected_columns:
            raise ValueError("Solution reuse classification row is malformed")
        type_id = cells[0]
        scope = cells[6] if section == "executable" else "never"
        if type_id in scopes or scope not in {"never", "session", "durable"}:
            raise ValueError(f"Invalid solution reuse classification for {type_id}")
        scopes[type_id] = scope
    return scopes


__all__ = [
    "CURRENT_REPO_OWNED_CATALOG_PATH",
    "SOLUTION_REUSE_CLASSIFICATION_PATH",
    "load_current_repo_owned_catalog",
    "load_solution_reuse_scopes",
]
