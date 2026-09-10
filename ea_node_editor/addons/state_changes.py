# Purpose: Prepare pure add-on enabled-state changes for the shell transaction owner.
# Map: subsystems/addons.md
# Tests: tests/test_addon_state_changes.py

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ea_node_editor.addons.catalog import registered_addon_registration_by_id
from ea_node_editor.app_preferences import (
    default_app_preferences_document,
    normalize_app_preferences_document,
    set_addon_state,
)

if TYPE_CHECKING:
    from ea_node_editor.nodes.registry import NodeRegistry


@dataclass(slots=True, frozen=True)
class AddOnApplyResult:
    addon_id: str
    enabled: bool
    apply_policy: str
    restart_required: bool
    preferences_document: dict[str, Any]
    registry: NodeRegistry | None = None


def prepare_addon_enabled_state(
    addon_id: str,
    *,
    enabled: bool,
    preferences_document: Any,
) -> AddOnApplyResult:
    """Return one normalized proposed state without I/O or runtime publication."""

    registration = registered_addon_registration_by_id(addon_id)
    if registration is None:
        raise KeyError(f"Unknown add-on id: {addon_id!r}")

    base_document = normalize_app_preferences_document(
        default_app_preferences_document()
        if preferences_document is None
        else preferences_document
    )
    restart_required = registration.manifest.apply_policy != "hot_apply"
    updated_document = set_addon_state(
        base_document,
        registration.manifest.addon_id,
        enabled=enabled,
        pending_restart=restart_required,
    )
    return AddOnApplyResult(
        addon_id=registration.manifest.addon_id,
        enabled=bool(enabled),
        apply_policy=registration.manifest.apply_policy,
        restart_required=restart_required,
        preferences_document=updated_document,
    )


__all__ = ["AddOnApplyResult", "prepare_addon_enabled_state"]
