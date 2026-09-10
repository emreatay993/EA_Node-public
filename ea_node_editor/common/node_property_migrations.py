# Purpose: Decode retired node property representations at document and fragment boundaries.
# Map: feature_routes/serialization_migration_legacy_rejection.md
# Tests: tests/test_panel_node.py
from collections.abc import Mapping
from typing import Any


def migrate_panel_properties(type_id: str, properties: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve the old opt-in numeric interpretation when importing saved nodes."""
    migrated = dict(properties)
    if type_id == "data.panel" and "parse_numbers" in migrated:
        legacy_value = migrated.pop("parse_numbers")
        migrated.setdefault("interpretation", "auto" if legacy_value is True else "text")
    return migrated
