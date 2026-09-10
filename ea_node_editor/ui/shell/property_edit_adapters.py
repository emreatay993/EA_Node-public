# Purpose: Compose core and live add-on property-edit adapters for shell consumers.
# Map: subsystems/ui_shell.md
# Tests: tests/test_inspector_projection.py, tests/test_tabular_addon_catalog.py

from __future__ import annotations

from typing import Any

from ea_node_editor.addons.property_edit_adapters import create_property_edit_adapters


def create_shell_property_edit_adapters(
    *,
    preferences_document: Any = None,
    store: Any = None,
) -> tuple[Any, ...]:
    return create_property_edit_adapters(
        preferences_document=preferences_document,
        store=store,
    )


__all__ = ["create_shell_property_edit_adapters"]
