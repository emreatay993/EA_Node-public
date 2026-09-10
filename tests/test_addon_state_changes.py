from __future__ import annotations

from copy import deepcopy

import pytest

from ea_node_editor.addons.catalog import AddOnRegistration, TABULAR_DATA_ADDON_ID
from ea_node_editor.addons.state_changes import prepare_addon_enabled_state
from ea_node_editor.app_preferences import (
    addon_state,
    default_app_preferences_document,
    normalize_app_preferences_document,
    set_addon_state,
)
from ea_node_editor.nodes.plugin_contracts import AddOnManifest


def test_generic_addon_state_normalization_preserves_enabled_and_pending_restart() -> None:
    document = normalize_app_preferences_document(
        {
            "kind": "ea-node-editor/app-preferences",
            "version": 5,
            "addons": {
                "states": {
                    "packet.restart": {
                        "enabled": False,
                        "pending_restart": True,
                    }
                }
            },
        }
    )

    assert addon_state(document, "packet.restart") == {
        "enabled": False,
        "pending_restart": True,
    }


def test_set_addon_state_updates_the_generic_addon_state_store() -> None:
    document = set_addon_state(
        default_app_preferences_document(),
        "packet.toggle",
        enabled=False,
        pending_restart=True,
    )

    assert addon_state(document, "packet.toggle") == {
        "enabled": False,
        "pending_restart": True,
    }


def test_prepare_hot_apply_state_is_pure_and_leaves_source_unchanged() -> None:
    source = default_app_preferences_document()
    original = deepcopy(source)

    result = prepare_addon_enabled_state(
        TABULAR_DATA_ADDON_ID,
        enabled=False,
        preferences_document=source,
    )

    assert source == original
    assert result.registry is None
    assert result.restart_required is False
    assert addon_state(result.preferences_document, TABULAR_DATA_ADDON_ID) == {
        "enabled": False,
        "pending_restart": False,
    }


def test_prepare_restart_required_state_marks_pending_without_runtime_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registration = AddOnRegistration(
        manifest=AddOnManifest(
            addon_id="tests.addons.restart_only",
            display_name="Restart Only",
            apply_policy="restart_required",
        ),
        backend_module="tests.addons.restart_only",
        backend_id="tests.addons.restart_only",
    )
    monkeypatch.setattr(
        "ea_node_editor.addons.state_changes.registered_addon_registration_by_id",
        lambda _addon_id: registration,
    )

    result = prepare_addon_enabled_state(
        registration.manifest.addon_id,
        enabled=False,
        preferences_document=default_app_preferences_document(),
    )

    assert result.restart_required is True
    assert result.registry is None
    assert addon_state(result.preferences_document, registration.manifest.addon_id) == {
        "enabled": False,
        "pending_restart": True,
    }


def test_prepare_rejects_unknown_addon() -> None:
    with pytest.raises(KeyError, match="Unknown add-on id"):
        prepare_addon_enabled_state(
            "tests.addons.unknown",
            enabled=True,
            preferences_document=default_app_preferences_document(),
        )
