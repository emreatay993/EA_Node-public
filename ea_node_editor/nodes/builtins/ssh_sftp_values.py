# Purpose: Validate SSH/SFTP tagged values without importing the Paramiko runtime.
# Map: feature_routes/ssh_sftp_nodes.md
# Tests: tests/test_ssh_sftp_node_contracts.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ea_node_editor.common.protected_values import (
    PROTECTED_SECRET_SCHEMA,
    WINDOWS_DPAPI_PROVIDER,
    secret_public_state,
)
from ea_node_editor.nodes.execution_context import (
    ExecutionContext,
    NodeInputNotReadyError,
    NodeResult,
)


RUNTIME_VALUE_TAG = "__ea_runtime_value__"
SECRET_RUNTIME_TYPE = "secret_data"
HOST_RUNTIME_TYPE = "ssh_sftp_host_data"
RUNTIME_VALUE_REVISION = 1


def _runtime_secret(envelope: Mapping[str, Any]) -> dict[str, Any]:
    state = secret_public_state(dict(envelope))
    return {
        RUNTIME_VALUE_TAG: SECRET_RUNTIME_TYPE,
        "revision": RUNTIME_VALUE_REVISION,
        "provider": WINDOWS_DPAPI_PROVIDER,
        "scope": state["scope"],
        "ciphertext_b64": str(envelope["ciphertext_b64"]),
    }


def _coerce_secret(value: Any, *, input_name: str) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{input_name} must be connected to a Secret value.")
    payload = dict(value)
    if (
        payload.get(RUNTIME_VALUE_TAG) != SECRET_RUNTIME_TYPE
        or payload.get("revision") != RUNTIME_VALUE_REVISION
        or payload.get("provider") != WINDOWS_DPAPI_PROVIDER
        or not isinstance(payload.get("scope"), str)
        or not isinstance(payload.get("ciphertext_b64"), str)
    ):
        raise TypeError(f"{input_name} must be connected to a Secret value.")
    return {
        RUNTIME_VALUE_TAG: SECRET_RUNTIME_TYPE,
        "revision": RUNTIME_VALUE_REVISION,
        "provider": WINDOWS_DPAPI_PROVIDER,
        "scope": payload["scope"],
        "ciphertext_b64": payload["ciphertext_b64"],
    }


def _secret_envelope(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": PROTECTED_SECRET_SCHEMA,
        "provider": WINDOWS_DPAPI_PROVIDER,
        "scope": value["scope"],
        "ciphertext_b64": value["ciphertext_b64"],
    }


def compute_secret(ctx: ExecutionContext) -> NodeResult:
    envelope = ctx.properties.get("protected_value")
    if not envelope:
        raise NodeInputNotReadyError("Secret requires a stored value.")
    if not isinstance(envelope, Mapping):
        raise TypeError("Secret protected value is invalid.")
    runtime_value = _runtime_secret(envelope)
    configured_scope = str(ctx.properties.get("data_protection_scope", "")).strip()
    if configured_scope:
        aliases = {
            "Current user": "CurrentUser",
            "All users on this machine": "LocalMachine",
        }
        if aliases.get(configured_scope, configured_scope) != runtime_value["scope"]:
            raise ValueError(
                "Secret protection scope is out of sync; replace the secret value."
            )
    return NodeResult(outputs={"secret_value": runtime_value})


def compute_host(ctx: ExecutionContext) -> NodeResult:
    address = str(ctx.inputs.get("address", "")).strip()
    username = str(ctx.inputs.get("username", "")).strip()
    if not address:
        raise ValueError("SSH/SFTP Host requires an Address.")
    if not username:
        raise ValueError("SSH/SFTP Host requires a Username.")
    try:
        port = int(ctx.inputs.get("port", 22))
    except (TypeError, ValueError) as exc:
        raise ValueError("SSH/SFTP Host Port must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("SSH/SFTP Host Port must be between 1 and 65535.")

    password = _coerce_secret(ctx.inputs.get("password"), input_name="Password")
    private_key_path = str(ctx.inputs.get("private_key_path", "") or "").strip()
    private_key_passphrase = _coerce_secret(
        ctx.inputs.get("private_key_passphrase"),
        input_name="Private key passphrase",
    )
    use_openssh_agent = bool(ctx.inputs.get("use_openssh_agent", False))
    use_pageant = bool(ctx.inputs.get("use_pageant", False))
    if private_key_passphrase is not None and not private_key_path:
        raise ValueError("Private key passphrase requires a Private key path.")
    if not any((password, private_key_path, use_openssh_agent, use_pageant)):
        raise NodeInputNotReadyError(
            "SSH/SFTP Host requires a password, private key, or enabled SSH agent."
        )

    host = {
        RUNTIME_VALUE_TAG: HOST_RUNTIME_TYPE,
        "revision": RUNTIME_VALUE_REVISION,
        "address": address,
        "port": port,
        "username": username,
        "password": password,
        "private_key_path": private_key_path,
        "private_key_passphrase": private_key_passphrase,
        "use_openssh_agent": use_openssh_agent,
        "use_pageant": use_pageant,
    }
    return NodeResult(outputs={"host": host})


def _coerce_host(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("Target Host must be connected to an SSH/SFTP Host value.")
    host = dict(value)
    if (
        host.get(RUNTIME_VALUE_TAG) != HOST_RUNTIME_TYPE
        or host.get("revision") != RUNTIME_VALUE_REVISION
    ):
        raise TypeError("Target Host must be connected to an SSH/SFTP Host value.")
    address = str(host.get("address", "")).strip()
    username = str(host.get("username", "")).strip()
    try:
        port = int(host.get("port", 22))
    except (TypeError, ValueError) as exc:
        raise ValueError("Target Host contains an invalid port.") from exc
    if not address or not username or not 1 <= port <= 65535:
        raise ValueError("Target Host is incomplete or invalid.")
    password = _coerce_secret(host.get("password"), input_name="Password")
    private_key_path = str(host.get("private_key_path", "") or "").strip()
    private_key_passphrase = _coerce_secret(
        host.get("private_key_passphrase"),
        input_name="Private key passphrase",
    )
    use_openssh_agent = bool(host.get("use_openssh_agent", False))
    use_pageant = bool(host.get("use_pageant", False))
    if private_key_passphrase is not None and not private_key_path:
        raise ValueError("Target Host has a passphrase without a private key.")
    if not any((password, private_key_path, use_openssh_agent, use_pageant)):
        raise ValueError("Target Host has no configured authentication source.")
    return {
        RUNTIME_VALUE_TAG: HOST_RUNTIME_TYPE,
        "revision": RUNTIME_VALUE_REVISION,
        "address": address,
        "port": port,
        "username": username,
        "password": password,
        "private_key_path": private_key_path,
        "private_key_passphrase": private_key_passphrase,
        "use_openssh_agent": use_openssh_agent,
        "use_pageant": use_pageant,
    }


__all__ = ["compute_host", "compute_secret"]
