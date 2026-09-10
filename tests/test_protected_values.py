from __future__ import annotations

import sys

import pytest

from ea_node_editor.common import protected_values
from ea_node_editor.common.protected_values import (
    protect_secret,
    reprotect_secret,
    secret_public_state,
    unprotect_secret,
)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI is required")
def test_dpapi_round_trip_and_scope_change_do_not_expose_ciphertext() -> None:
    envelope = protect_secret("not-for-logs", "Current user")

    assert envelope["schema"] == "corex.protected_secret.v1"
    assert envelope["provider"] == "windows_dpapi"
    assert envelope["scope"] == "CurrentUser"
    assert unprotect_secret(envelope) == "not-for-logs"
    assert secret_public_state(envelope) == {
        "has_value": True,
        "scope": "CurrentUser",
    }
    assert "ciphertext" not in repr(secret_public_state(envelope)).lower()

    machine_envelope = reprotect_secret(envelope, "All users on this machine")
    assert machine_envelope["scope"] == "LocalMachine"
    assert unprotect_secret(machine_envelope) == "not-for-logs"


def test_unset_secret_is_safe_for_clear_and_scope_edits() -> None:
    assert secret_public_state({}) == {"has_value": False, "scope": ""}
    assert secret_public_state(None) == {"has_value": False, "scope": ""}
    assert reprotect_secret({}, "Current user") == {}
    assert reprotect_secret(None, "Current user") == {}
    assert secret_public_state({"malformed": True}) == {
        "has_value": True,
        "scope": "",
    }


def test_invalid_envelopes_fail_closed_without_echoing_ciphertext() -> None:
    envelope = {
        "schema": "corex.protected_secret.v1",
        "provider": "windows_dpapi",
        "scope": "CurrentUser",
        "ciphertext_b64": "sensitive-marker%",
    }

    with pytest.raises(ValueError, match="valid base64") as error:
        unprotect_secret(envelope)

    assert "sensitive-marker" not in str(error.value)


def test_non_windows_secret_operations_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(protected_values.sys, "platform", "linux")

    with pytest.raises(OSError, match="only available on Windows"):
        protect_secret("value", "Current user")
