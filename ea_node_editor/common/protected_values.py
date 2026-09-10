# Purpose: Protect and reveal persisted secret values with Windows DPAPI.
# Map: feature_routes/ssh_sftp_nodes.md
# Tests: tests/test_protected_values.py

from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes
from typing import Any


PROTECTED_SECRET_SCHEMA = "corex.protected_secret.v1"
WINDOWS_DPAPI_PROVIDER = "windows_dpapi"
CURRENT_USER_SCOPE = "CurrentUser"
LOCAL_MACHINE_SCOPE = "LocalMachine"

_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_CRYPTPROTECT_LOCAL_MACHINE = 0x4
_SCOPE_ALIASES = {
    "currentuser": CURRENT_USER_SCOPE,
    "current user": CURRENT_USER_SCOPE,
    "current_user": CURRENT_USER_SCOPE,
    "localmachine": LOCAL_MACHINE_SCOPE,
    "local machine": LOCAL_MACHINE_SCOPE,
    "local_machine": LOCAL_MACHINE_SCOPE,
    "all users on this machine": LOCAL_MACHINE_SCOPE,
}


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _normalize_scope(scope: str) -> str:
    normalized = _SCOPE_ALIASES.get(str(scope).strip().lower())
    if normalized is None:
        raise ValueError("Secret scope must be CurrentUser or LocalMachine.")
    return normalized


def _require_windows() -> None:
    if sys.platform != "win32":
        raise OSError("Windows DPAPI secret operations are only available on Windows.")


def _validate_envelope(envelope: dict[str, Any]) -> dict[str, str]:
    if not isinstance(envelope, dict):
        raise TypeError("Protected secret must be a mapping.")
    if envelope.get("schema") != PROTECTED_SECRET_SCHEMA:
        raise ValueError("Unsupported protected-secret schema.")
    if envelope.get("provider") != WINDOWS_DPAPI_PROVIDER:
        raise ValueError("Unsupported protected-secret provider.")
    scope = _normalize_scope(str(envelope.get("scope", "")))
    ciphertext = envelope.get("ciphertext_b64")
    if not isinstance(ciphertext, str):
        raise ValueError("Protected secret ciphertext must be text.")
    return {
        "schema": PROTECTED_SECRET_SCHEMA,
        "provider": WINDOWS_DPAPI_PROVIDER,
        "scope": scope,
        "ciphertext_b64": ciphertext,
    }


def _input_blob(payload: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(payload, max(1, len(payload)))
    blob = _DataBlob(
        len(payload),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return blob, buffer


def _crypt_protect(payload: bytes, scope: str) -> bytes:
    _require_windows()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = (
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    )
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel32.LocalFree.restype = ctypes.c_void_p

    input_blob, input_buffer = _input_blob(payload)
    output_blob = _DataBlob()
    flags = _CRYPTPROTECT_UI_FORBIDDEN
    if scope == LOCAL_MACHINE_SCOPE:
        flags |= _CRYPTPROTECT_LOCAL_MACHINE
    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        flags,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        del input_buffer
        kernel32.LocalFree(output_blob.pbData)


def _crypt_unprotect(payload: bytes) -> bytes:
    _require_windows()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = (
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    )
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel32.LocalFree.restype = ctypes.c_void_p

    input_blob, input_buffer = _input_blob(payload)
    output_blob = _DataBlob()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        del input_buffer
        kernel32.LocalFree(output_blob.pbData)


def protect_secret(plaintext: str, scope: str) -> dict[str, str]:
    """Protect plaintext for the current Windows user or local machine."""

    if not isinstance(plaintext, str):
        raise TypeError("Secret plaintext must be text.")
    canonical_scope = _normalize_scope(scope)
    encrypted = _crypt_protect(plaintext.encode("utf-8"), canonical_scope)
    return {
        "schema": PROTECTED_SECRET_SCHEMA,
        "provider": WINDOWS_DPAPI_PROVIDER,
        "scope": canonical_scope,
        "ciphertext_b64": base64.b64encode(encrypted).decode("ascii"),
    }


def unprotect_secret(envelope: dict[str, Any]) -> str:
    """Reveal a protected secret in the current Windows security context."""

    validated = _validate_envelope(envelope)
    try:
        encrypted = base64.b64decode(validated["ciphertext_b64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Protected secret ciphertext is not valid base64.") from exc
    try:
        return _crypt_unprotect(encrypted).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Protected secret plaintext is not valid UTF-8.") from exc


def reprotect_secret(
    envelope: dict[str, Any] | None,
    target_scope: str,
) -> dict[str, str]:
    """Decrypt then protect a secret for another DPAPI scope."""

    if not envelope:
        return {}
    return protect_secret(unprotect_secret(envelope), target_scope)


def secret_public_state(envelope: dict[str, Any] | None) -> dict[str, Any]:
    """Return UI-safe state without revealing protected bytes."""

    if not envelope:
        return {"has_value": False, "scope": ""}
    try:
        validated = _validate_envelope(envelope)
    except (TypeError, ValueError):
        return {"has_value": True, "scope": ""}
    return {
        "has_value": bool(validated["ciphertext_b64"]),
        "scope": validated["scope"],
    }


__all__ = [
    "CURRENT_USER_SCOPE",
    "LOCAL_MACHINE_SCOPE",
    "PROTECTED_SECRET_SCHEMA",
    "WINDOWS_DPAPI_PROVIDER",
    "protect_secret",
    "reprotect_secret",
    "secret_public_state",
    "unprotect_secret",
]
