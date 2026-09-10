# Purpose: Strict field decoding shared by execution DTO and wire adapters.
# Map: subsystems/execution.md
# Tests: tests/test_protocol_codec.py

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any


def string_field(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    default: str | None = "",
    strip: bool = False,
    allow_none: bool = False,
) -> str | None:
    if field_name not in payload:
        return default
    value = payload[field_name]
    if allow_none and value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    return value.strip() if strip else value


def bool_field(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    default: bool = False,
) -> bool:
    if field_name not in payload:
        return default
    value = payload[field_name]
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean.")
    return value


def float_field(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    default: float | None = 0.0,
    allow_none: bool = False,
) -> float | None:
    if field_name not in payload:
        return default
    value = payload[field_name]
    if allow_none and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number.")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite.")
    return normalized


def nonnegative_int_field(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    default: int = 0,
) -> int:
    if field_name not in payload:
        return default
    value = payload[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")
    return value


def string_list_field(
    payload: Mapping[str, Any],
    field_name: str,
) -> tuple[str, ...]:
    if field_name not in payload:
        return ()
    value = payload[field_name]
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list.")
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"{field_name}[{index}] must be a string.")
        item = item.strip()
        if item:
            normalized.append(item)
    return tuple(normalized)


def string_value(value: Any, *, field_name: str) -> str:
    normalized = string_field({field_name: value}, field_name)
    assert isinstance(normalized, str)
    return normalized


def bool_value(value: Any, *, field_name: str) -> bool:
    return bool_field({field_name: value}, field_name)


def float_value(value: Any, *, field_name: str) -> float:
    normalized = float_field({field_name: value}, field_name)
    assert isinstance(normalized, float)
    return normalized


def nonnegative_int_value(value: Any, *, field_name: str) -> int:
    return nonnegative_int_field({field_name: value}, field_name)


__all__ = [
    "bool_field",
    "bool_value",
    "float_field",
    "float_value",
    "nonnegative_int_field",
    "nonnegative_int_value",
    "string_field",
    "string_list_field",
    "string_value",
]
