"""Shared duck-typed invocation and payload-coercion helpers for QML bridges.

Single home for the helpers that were previously duplicated across the
graph-canvas command bridge, state bridge, and facade modules. Bridge
modules import these under their established
private aliases (``from ... import invoke as _invoke``) so call sites stay
unchanged.

These helpers are deliberately tolerant: bridge sources are optional
shell/controller objects resolved at runtime, so missing sources or missing
attributes degrade to defaults instead of raising.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def invoke(source: object | None, name: str, *args, default: Any = None) -> Any:
    callback = getattr(source, name, None) if source is not None else None
    if not callable(callback):
        return default
    return callback(*args)


def invoke_bool(source: object | None, name: str, *args) -> bool:
    callback = getattr(source, name, None) if source is not None else None
    if not callable(callback):
        return False
    return bool(callback(*args))


def invoke_value(source: object | None, name: str, *args) -> Any:
    callback = getattr(source, name, None) if source is not None else None
    if not callable(callback):
        return None
    return callback(*args)


def source_attr(source: object | None, name: str, default: Any) -> Any:
    if source is None:
        return default
    return getattr(source, name, default)


def invoke_available(source: object | None, name: str, *args) -> bool:
    callback = getattr(source, name, None) if source is not None else None
    if not callable(callback):
        return False
    callback(*args)
    return True


def invoke_chain(sources: tuple[object | None, ...], name: str, *args) -> bool:
    for source in sources:
        callback = getattr(source, name, None) if source is not None else None
        if callable(callback):
            callback(*args)
            return True
    return False


def connect_signal(source: object | None, name: str, slot) -> None:  # noqa: ANN001
    signal = getattr(source, name, None) if source is not None else None
    if signal is not None and hasattr(signal, "connect"):
        signal.connect(slot)


def variant_value(value: Any) -> Any:
    converter = getattr(value, "toVariant", None)
    if callable(converter):
        value = converter()
    if isinstance(value, Mapping):
        return {str(key): variant_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [variant_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(variant_value(item) for item in value)
    return value


def copy_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def copy_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def payload_str(payload: Mapping[str, object], key: str, default: str = "") -> str:
    value = payload.get(key, default)
    return str(value if value is not None else "").strip()


def payload_float(payload: Mapping[str, object], key: str, default: float = 0.0) -> float:
    try:
        return float(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def payload_bool(payload: Mapping[str, object], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return bool(value)


def first_payload_str(payload: Mapping[str, object], *keys: str, default: str = "") -> str:
    for key in keys:
        value = payload_str(payload, key)
        if value:
            return value
    return default


__all__ = [
    "connect_signal",
    "copy_dict",
    "copy_list",
    "first_payload_str",
    "invoke",
    "invoke_available",
    "invoke_bool",
    "invoke_chain",
    "invoke_value",
    "payload_bool",
    "payload_float",
    "payload_str",
    "variant_value",
]
