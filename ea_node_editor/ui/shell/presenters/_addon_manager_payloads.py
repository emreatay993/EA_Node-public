from __future__ import annotations

import re
from typing import Any

from ea_node_editor.addons.catalog import registered_addon_registration_by_id

from ea_node_editor.addons.contracts import AddOnRecord

_VALID_TABS = ("about", "dependencies", "nodes", "changelog")
_VALID_FILTERS = ("all", "enabled", "disabled")
_NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")
_PRE_RELEASE_RE = re.compile(r"(?:^|[._-])(a|alpha|b|beta|rc|preview)(?:[._-]|\d|$)", re.IGNORECASE)


def canonical_token(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return _NON_ALNUM_RE.sub("", normalized)


def normalized_filter(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _VALID_FILTERS else "all"


def normalized_tab(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _VALID_TABS else "about"


def status_label(record: AddOnRecord) -> str:
    if record.status == "pending_restart":
        return "Pending restart"
    if record.status == "disabled":
        return "Disabled"
    if record.status == "unavailable":
        return "Unavailable"
    return "Loaded"


def policy_label(record: AddOnRecord) -> str:
    return "Hot-reloadable" if record.apply_policy == "hot_apply" else "Requires restart"


def policy_copy(record: AddOnRecord) -> str:
    if record.apply_policy == "hot_apply":
        return "Applies immediately to the live registry."
    return "Applies after the next COREX restart."


def availability_copy(record: AddOnRecord) -> str:
    summary = str(record.availability.summary or "").strip()
    if summary:
        return summary
    if record.availability.missing_dependencies:
        return "Missing dependencies: " + ", ".join(record.availability.missing_dependencies)
    return "The add-on is available."


def policy_badge_label(record: AddOnRecord) -> str:
    return "HOT-RELOADABLE" if record.apply_policy == "hot_apply" else "REQUIRES RESTART"


def is_builtin(record: AddOnRecord) -> bool:
    return record.addon_id.startswith("ea_node_editor.builtins.")


def is_pre_release(version: object) -> bool:
    return bool(_PRE_RELEASE_RE.search(str(version or "").strip()))


def node_items(record: AddOnRecord, *, registry: Any = None, limit: int | None = None) -> list[dict[str, Any]]:
    spec_or_none = getattr(registry, "spec_or_none", None)
    items: list[dict[str, Any]] = []
    type_ids = record.provided_node_type_ids if limit is None else record.provided_node_type_ids[:limit]
    for type_id in type_ids:
        spec = spec_or_none(type_id) if callable(spec_or_none) else None
        display_name = str(getattr(spec, "display_name", "") or "").strip()
        if not display_name:
            display_name = type_id.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ").title()
        items.append(
            {
                "displayName": display_name,
                "typeId": str(type_id),
                "category": str(getattr(spec, "category", "") or "").strip(),
                "runtimeBehavior": str(getattr(spec, "runtime_behavior", "") or "").replace("_", " ").strip().title(),
                "surfaceFamily": str(getattr(spec, "surface_family", "") or "").replace("_", " ").strip().title(),
            }
        )
    items.sort(key=lambda item: (str(item["displayName"]).casefold(), str(item["typeId"]).casefold()))
    return items


def dependency_items(record: AddOnRecord) -> list[dict[str, Any]]:
    missing_dependencies = {str(value) for value in record.availability.missing_dependencies}
    items: list[dict[str, Any]] = []
    for dependency in record.manifest.dependencies:
        dependency_name = str(dependency).strip()
        if not dependency_name:
            continue
        satisfied = dependency_name not in missing_dependencies
        items.append(
            {
                "name": dependency_name,
                "satisfied": satisfied,
                "statusLabel": (
                    "satisfied in COREX environment"
                    if satisfied
                    else "missing from COREX environment"
                ),
            }
        )
    return items


def category_label(record: AddOnRecord, item_rows: list[dict[str, Any]]) -> str:
    for item in item_rows:
        label = str(item.get("category", "")).strip()
        if label:
            return label
    return "Built-in" if is_builtin(record) else "Add-on"


def category_key(label: str) -> str:
    normalized = str(label).strip().lower()
    if "core" in normalized:
        return "core"
    if "integr" in normalized or normalized == "io":
        return "io"
    if "logic" in normalized:
        return "logic"
    if "phys" in normalized or "cad" in normalized:
        return "physics"
    return "addon"


def icon_glyph(key: str, label: str) -> str:
    return {
        "core": "C",
        "io": "I",
        "logic": "L",
        "physics": "P",
        "addon": "A",
    }.get(key, str(label[:1] or "A").upper())


def state_badges(record: AddOnRecord) -> list[dict[str, str]]:
    badges: list[dict[str, str]] = []
    if is_pre_release(record.version):
        badges.append({"label": "PRE-RELEASE", "tone": "warn"})
    if is_builtin(record):
        badges.append({"label": "BUILT-IN", "tone": "core"})
    if record.status == "pending_restart":
        badges.append({"label": "PENDING RESTART", "tone": "warn"})
    elif record.status == "unavailable":
        badges.append({"label": "UNAVAILABLE", "tone": "warn"})
    return badges


def about_facts(
    record: AddOnRecord,
    *,
    category_label_text: str,
    node_count: int,
    dependencies: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {"label": "Category", "value": category_label_text},
        {"label": "Activation", "value": policy_label(record)},
        {"label": "Nodes exposed", "value": str(node_count)},
        {
            "label": "Availability",
            "value": (
                "Ready in COREX environment"
                if record.availability.is_available
                else "Missing dependency"
            ),
        },
        {"label": "Dependencies", "value": str(len(dependencies))},
    ]


def changelog_entries(
    record: AddOnRecord,
    *,
    node_count: int,
    dependencies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = [
        {
            "versionLabel": f"v{record.version}" if str(record.version).strip() else "Current build",
            "dateLabel": status_label(record),
            "title": "Runtime state",
            "bullets": [
                str(record.details or record.summary or "No manifest summary published yet.").strip(),
                f"{node_count} descriptor(s) are currently discoverable from this add-on.",
                policy_copy(record),
            ],
        }
    ]
    if dependencies or record.availability.missing_dependencies:
        dependency_bullets = []
        if dependencies:
            dependency_bullets.append("Python requirements: " + ", ".join(str(item["name"]) for item in dependencies))
        dependency_bullets.append(availability_copy(record))
        entries.append(
            {
                "versionLabel": "Environment",
                "dateLabel": "Workspace",
                "title": "Dependency resolution",
                "bullets": dependency_bullets,
            }
        )
    return entries


def _base_payload(
    record: AddOnRecord,
    *,
    selected_addon_id: str,
    registry: Any = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], str, str, int]:
    total_node_count = len(record.provided_node_type_ids)
    item_rows = node_items(record, registry=registry, limit=12)
    dependencies = dependency_items(record)
    category_label_text = category_label(record, item_rows)
    category_key_text = category_key(category_label_text)
    registration = registered_addon_registration_by_id(record.addon_id)
    managed_package_ids = list(
        getattr(registration, "managed_runtime_package_ids", ()) or ()
    )
    missing_text = " ".join(record.availability.missing_dependencies).casefold()
    update_available = bool(managed_package_ids and "update" in missing_text)
    payload = {
        "addonId": record.addon_id,
        "displayName": record.display_name,
        "vendor": record.vendor,
        "version": record.version,
        "summary": record.summary,
        "details": record.details or record.summary,
        "enabled": bool(record.state.enabled),
        "status": record.status,
        "statusLabel": status_label(record),
        "applyPolicy": record.apply_policy,
        "policyLabel": policy_label(record),
        "policyBadgeLabel": policy_badge_label(record),
        "pendingRestart": record.status == "pending_restart",
        "requiresRestart": record.apply_policy == "restart_required",
        "supportsHotApply": record.apply_policy == "hot_apply",
        "available": bool(record.availability.is_available),
        "unavailable": not record.availability.is_available,
        "installable": bool(managed_package_ids),
        "managedRuntimePackageIds": managed_package_ids,
        "updateAvailable": update_available,
        "installActionLabel": "Update" if update_available else "Install",
        "selected": record.addon_id == selected_addon_id,
        "nodeCount": total_node_count,
        "dependencyCount": len(dependencies),
        "builtin": is_builtin(record),
        "preRelease": is_pre_release(record.version),
        "categoryLabel": category_label_text,
        "categoryKey": category_key_text,
        "iconGlyph": icon_glyph(category_key_text, category_label_text),
    }
    return payload, item_rows, dependencies, category_label_text, category_key_text, total_node_count


def row_payload(record: AddOnRecord, *, selected_addon_id: str, registry: Any = None) -> dict[str, Any]:
    payload, _, _, _, _, _ = _base_payload(record, selected_addon_id=selected_addon_id, registry=registry)
    payload["stateBadges"] = state_badges(record)
    return payload


def detail_payload(record: AddOnRecord, *, selected_addon_id: str, registry: Any = None) -> dict[str, Any]:
    payload, item_rows, dependencies, category_label_text, _, total_node_count = _base_payload(
        record,
        selected_addon_id=selected_addon_id,
        registry=registry,
    )
    payload.update(
        {
            "policyCopy": policy_copy(record),
            "availabilitySummary": availability_copy(record),
            "dependencyItems": dependencies,
            "missingDependencies": list(record.availability.missing_dependencies),
            "providedNodeTypeIds": list(record.provided_node_type_ids),
            "nodeItems": item_rows,
            "statusBadges": state_badges(record),
            "aboutFacts": about_facts(
                record,
                category_label_text=category_label_text,
                node_count=total_node_count,
                dependencies=dependencies,
            ),
            "pythonRequirement": ", ".join(str(item["name"]) for item in dependencies) or "No external dependency",
            "changelogEntries": changelog_entries(
                record,
                node_count=total_node_count,
                dependencies=dependencies,
            ),
        }
    )
    return payload
