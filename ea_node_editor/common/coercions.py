"""Canonical value-coercion helpers.

These replace the many byte-identical private ``_coerce_*`` copies scattered
across subsystems. Prefer importing from here for new code. Note that a few
legacy call sites still keep their own variants with intentionally different
semantics (e.g. positional-required defaults); migrate those only after
confirming behavior matches.
"""

from __future__ import annotations

from typing import Any


def coerce_int(value: Any, *, default: int = 0) -> int:
    """Return ``int(value)`` or ``default`` when conversion fails."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def coerce_float(value: Any, *, default: float = 0.0) -> float:
    """Return ``float(value)`` or ``default`` when conversion fails."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def coerce_bool(value: Any, *, default: bool = False) -> bool:
    """Coerce common truthy/falsey encodings to ``bool``.

    Handles native ``bool``, numeric values, and the usual string spellings
    (``true/false``, ``yes/no``, ``on/off``, ``1/0``); falls back to
    ``default`` for ``None`` or anything unrecognized.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return default


def coerce_str(value: Any, *, default: str = "") -> str:
    """Return ``str(value)`` or ``default`` when ``value`` is ``None``."""
    if value is None:
        return default
    return str(value)


def normalize_path_text(value: Any) -> str:
    """Normalize stored path text without touching the filesystem."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1].strip()
    return text
