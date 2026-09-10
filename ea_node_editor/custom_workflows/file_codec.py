from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ea_node_editor.nodes.registry import NodeRegistry

from .codec import normalize_custom_workflow_metadata

CUSTOM_WORKFLOW_FILE_EXTENSION = ".cxwf"
CUSTOM_WORKFLOW_FILE_KIND = "ea-node-editor/custom-workflow"
CUSTOM_WORKFLOW_FILE_VERSION = 2
_LEGACY_CUSTOM_WORKFLOW_FILE_VERSION = 1


def normalize_custom_workflow_definition(
    value: Any,
    *,
    registry: NodeRegistry | None = None,
    migration_report: list[str] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    normalized_definitions = normalize_custom_workflow_metadata(
        [value],
        registry=registry,
        migration_report=migration_report,
    )
    if len(normalized_definitions) != 1:
        return None
    definition = normalized_definitions[0]
    return definition


def to_custom_workflow_file_document(definition: Any) -> dict[str, Any]:
    normalized_definition = normalize_custom_workflow_definition(definition)
    if normalized_definition is None:
        raise ValueError("Custom workflow definition is invalid.")
    return {
        "kind": CUSTOM_WORKFLOW_FILE_KIND,
        "version": CUSTOM_WORKFLOW_FILE_VERSION,
        "workflow": normalized_definition,
    }


def from_custom_workflow_file_document(
    document: Any,
    *,
    registry: NodeRegistry | None = None,
    migration_report: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("Custom workflow file must contain a JSON object.")
    if str(document.get("kind", "")).strip() != CUSTOM_WORKFLOW_FILE_KIND:
        raise ValueError("Custom workflow file kind is invalid.")

    try:
        version = int(document.get("version"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Custom workflow file version is invalid.") from exc
    if version not in {_LEGACY_CUSTOM_WORKFLOW_FILE_VERSION, CUSTOM_WORKFLOW_FILE_VERSION}:
        raise ValueError(
            f"Unsupported custom workflow file version '{version}'. "
            f"Expected version {_LEGACY_CUSTOM_WORKFLOW_FILE_VERSION} or {CUSTOM_WORKFLOW_FILE_VERSION}."
        )

    workflow_payload = document.get("workflow")
    if _workflow_requires_legacy_registry(workflow_payload, file_version=version) and registry is None:
        raise ValueError("Legacy custom workflow migration requires the active node registry.")

    local_report: list[str] = []
    normalized_definition = normalize_custom_workflow_definition(
        workflow_payload,
        registry=registry,
        migration_report=local_report,
    )
    if normalized_definition is None:
        _merge_sorted_report(migration_report, local_report)
        details = f" {' '.join(local_report)}" if local_report else ""
        raise ValueError(f"Custom workflow file payload is invalid or empty.{details}")
    if version == _LEGACY_CUSTOM_WORKFLOW_FILE_VERSION:
        local_report.append(
            f"Migrated custom workflow file version {version} to {CUSTOM_WORKFLOW_FILE_VERSION}."
        )
    _merge_sorted_report(migration_report, local_report)
    return normalized_definition


def export_custom_workflow_file(definition: Any, output_path: Path) -> Path:
    output_path = Path(output_path).with_suffix(CUSTOM_WORKFLOW_FILE_EXTENSION)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = to_custom_workflow_file_document(definition)
    output_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def import_custom_workflow_file(
    path: Path,
    *,
    registry: NodeRegistry | None = None,
    migration_report: list[str] | None = None,
) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return from_custom_workflow_file_document(
        payload,
        registry=registry,
        migration_report=migration_report,
    )


def _workflow_requires_legacy_registry(value: Any, *, file_version: int) -> bool:
    if file_version == _LEGACY_CUSTOM_WORKFLOW_FILE_VERSION:
        return True
    if not isinstance(value, dict):
        return False
    fragment = value.get("fragment")
    if not isinstance(fragment, dict):
        return False
    try:
        return int(fragment.get("version", -1)) == 1
    except (TypeError, ValueError):
        return False


def _merge_sorted_report(target: list[str] | None, entries: list[str]) -> None:
    if target is None or not entries:
        return
    target[:] = sorted(set((*target, *entries)))
