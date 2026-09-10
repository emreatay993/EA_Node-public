from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.settings import user_data_dir

from .codec import normalize_custom_workflow_metadata

_GLOBAL_CUSTOM_WORKFLOW_STORE_KIND = "ea-node-editor/custom-workflow-library"
_GLOBAL_CUSTOM_WORKFLOW_STORE_VERSION = 2
_LEGACY_GLOBAL_CUSTOM_WORKFLOW_STORE_VERSION = 1
_GLOBAL_CUSTOM_WORKFLOW_STORE_FILENAME = "custom_workflows_global.json"


def global_custom_workflows_path() -> Path:
    return user_data_dir() / _GLOBAL_CUSTOM_WORKFLOW_STORE_FILENAME


def load_global_custom_workflow_definitions(
    *,
    registry: NodeRegistry | None = None,
    migration_report: list[str] | None = None,
) -> list[dict[str, Any]]:
    path = global_custom_workflows_path()
    if not path.exists():
        return []
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(raw_payload, dict):
        return []
    try:
        version = int(raw_payload.get("version", 0) or 0)
    except (TypeError, ValueError):
        return []
    if (
        str(raw_payload.get("kind", "")).strip() != _GLOBAL_CUSTOM_WORKFLOW_STORE_KIND
        or version not in {
            _LEGACY_GLOBAL_CUSTOM_WORKFLOW_STORE_VERSION,
            _GLOBAL_CUSTOM_WORKFLOW_STORE_VERSION,
        }
    ):
        return []
    definitions_payload = raw_payload.get("custom_workflows", [])
    if _store_requires_legacy_registry(definitions_payload, store_version=version) and registry is None:
        raise ValueError("Legacy global custom workflow migration requires the active node registry.")

    local_report: list[str] = []
    normalized = normalize_custom_workflow_metadata(
        definitions_payload,
        registry=registry,
        migration_report=local_report,
    )
    if version == _LEGACY_GLOBAL_CUSTOM_WORKFLOW_STORE_VERSION:
        local_report.append(
            "Migrated global custom workflow store version "
            f"{version} to {_GLOBAL_CUSTOM_WORKFLOW_STORE_VERSION}."
        )
    _merge_sorted_report(migration_report, local_report)
    return normalized


def save_global_custom_workflow_definitions(definitions: Any) -> list[dict[str, Any]]:
    normalized = normalize_custom_workflow_metadata(definitions)
    path = global_custom_workflows_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "kind": _GLOBAL_CUSTOM_WORKFLOW_STORE_KIND,
        "version": _GLOBAL_CUSTOM_WORKFLOW_STORE_VERSION,
        "custom_workflows": normalized,
    }
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return normalized


def _store_requires_legacy_registry(value: Any, *, store_version: int) -> bool:
    if store_version == _LEGACY_GLOBAL_CUSTOM_WORKFLOW_STORE_VERSION:
        return True
    if not isinstance(value, list):
        return False
    for definition in value:
        if not isinstance(definition, dict):
            continue
        fragment = definition.get("fragment")
        if not isinstance(fragment, dict):
            continue
        try:
            if int(fragment.get("version", -1)) == 1:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _merge_sorted_report(target: list[str] | None, entries: list[str]) -> None:
    if target is None or not entries:
        return
    target[:] = sorted(set((*target, *entries)))
