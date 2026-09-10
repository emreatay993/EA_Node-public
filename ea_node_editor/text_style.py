from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

TEXT_STYLE_FORMATS = ("markdown", "plain")
TEXT_STYLE_FONT_WEIGHTS = ("normal", "medium", "demibold", "bold", "black")
TEXT_STYLE_HORIZONTAL_ALIGNMENTS = ("left", "center", "right", "justify")
TEXT_STYLE_VERTICAL_ALIGNMENTS = ("top", "middle", "bottom")
TEXT_STYLE_WRAP_MODES = ("word", "anywhere", "none")
TEXT_STYLE_RECENT_COLOR_LIMIT = 12
TEXT_ANNOTATION_STYLE_KEYS = (
    "font_family",
    "font_size",
    "font_weight",
    "italic",
    "underline",
    "strikeout",
    "text_color",
    "background_color",
    "horizontal_alignment",
    "vertical_alignment",
    "wrap_mode",
    "line_height",
    "letter_spacing",
    "padding",
    "opacity",
)
RICH_TEXT_INHERIT_FONT_SIZE = 0
RICH_TEXT_INHERIT_LINE_HEIGHT = 0.0
RICH_TEXT_INHERIT_LETTER_SPACING = -999.0
RICH_TEXT_INHERIT_PADDING = -1
RICH_TEXT_INHERIT_OPACITY = -1
RICH_TEXT_SLOT_STYLE_KEYS = TEXT_ANNOTATION_STYLE_KEYS

DEFAULT_TEXT_STYLE_PROPERTIES: dict[str, Any] = {
    "text": "Text",
    "format": "markdown",
    "font_family": "Caveat",
    "font_size": 18,
    "font_weight": "normal",
    "italic": False,
    "underline": False,
    "strikeout": False,
    "text_color": "",
    "background_color": "",
    "horizontal_alignment": "center",
    "vertical_alignment": "middle",
    "wrap_mode": "word",
    "line_height": 1.2,
    "letter_spacing": 0.0,
    "padding": 4,
    "opacity": 100,
}
DEFAULT_INHERITED_RICH_TEXT_STYLE_PROPERTIES: dict[str, Any] = {
    "format": "plain",
    "font_family": "",
    "font_size": RICH_TEXT_INHERIT_FONT_SIZE,
    "font_weight": "",
    "italic": False,
    "underline": False,
    "strikeout": False,
    "text_color": "",
    "background_color": "",
    "horizontal_alignment": "",
    "vertical_alignment": "",
    "wrap_mode": "",
    "line_height": RICH_TEXT_INHERIT_LINE_HEIGHT,
    "letter_spacing": RICH_TEXT_INHERIT_LETTER_SPACING,
    "padding": RICH_TEXT_INHERIT_PADDING,
    "opacity": RICH_TEXT_INHERIT_OPACITY,
}

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")


def normalize_text_style_properties(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    normalized = dict(DEFAULT_TEXT_STYLE_PROPERTIES)
    normalized["text"] = str(source.get("text", normalized["text"]))
    normalized["format"] = _normalized_choice(
        source.get("format"),
        TEXT_STYLE_FORMATS,
        str(normalized["format"]),
    )
    normalized["font_family"] = str(
        (source["font_family"] if "font_family" in source else normalized["font_family"]) or ""
    ).strip()
    normalized["font_size"] = _normalized_int(source.get("font_size"), 18, 6, 144)
    normalized["font_weight"] = _normalized_choice(
        source.get("font_weight"),
        TEXT_STYLE_FONT_WEIGHTS,
        str(normalized["font_weight"]),
    )
    normalized["italic"] = _normalized_bool(source.get("italic"), False)
    normalized["underline"] = _normalized_bool(source.get("underline"), False)
    normalized["strikeout"] = _normalized_bool(source.get("strikeout"), False)
    normalized["text_color"] = normalize_text_style_color(
        source.get("text_color"),
        str(normalized["text_color"]),
    )
    normalized["background_color"] = normalize_text_style_color(
        source.get("background_color"),
        "",
        allow_empty=True,
    )
    normalized["horizontal_alignment"] = _normalized_choice(
        source.get("horizontal_alignment"),
        TEXT_STYLE_HORIZONTAL_ALIGNMENTS,
        str(normalized["horizontal_alignment"]),
    )
    normalized["vertical_alignment"] = _normalized_choice(
        source.get("vertical_alignment"),
        TEXT_STYLE_VERTICAL_ALIGNMENTS,
        str(normalized["vertical_alignment"]),
    )
    normalized["wrap_mode"] = _normalized_choice(
        source.get("wrap_mode"),
        TEXT_STYLE_WRAP_MODES,
        str(normalized["wrap_mode"]),
    )
    normalized["line_height"] = _normalized_float(source.get("line_height"), 1.2, 0.5, 4.0)
    normalized["letter_spacing"] = _normalized_float(source.get("letter_spacing"), 0.0, -10.0, 20.0)
    normalized["padding"] = _normalized_int(source.get("padding"), 4, 0, 64)
    normalized["opacity"] = _normalized_int(source.get("opacity"), 100, 0, 100)
    return normalized


def normalize_text_annotation_style_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    present_keys = [key for key in TEXT_ANNOTATION_STYLE_KEYS if key in value]
    normalized = normalize_text_style_properties(value)
    return {key: normalized[key] for key in present_keys}


def rich_text_format_property_key(content_key: str) -> str:
    normalized = str(content_key or "").strip()
    return "format" if normalized == "text" else f"{normalized}_format"


def rich_text_style_property_key(content_key: str, style_key: str) -> str:
    normalized_content = str(content_key or "").strip()
    normalized_style = str(style_key or "").strip()
    if normalized_content == "text":
        return normalized_style
    return f"{normalized_content}_{normalized_style}"


def rich_text_slot_property_keys(content_key: str) -> tuple[str, ...]:
    return (
        str(content_key or "").strip(),
        rich_text_format_property_key(content_key),
        *(
            rich_text_style_property_key(content_key, style_key)
            for style_key in RICH_TEXT_SLOT_STYLE_KEYS
        ),
    )


def normalize_text_style_color(
    value: Any,
    default: str = "",
    *,
    allow_empty: bool = False,
) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return "" if allow_empty else default
    if not _HEX_COLOR.match(normalized):
        return default
    return normalized.upper()


def normalize_recent_text_colors(
    value: Any,
    *,
    limit: int = TEXT_STYLE_RECENT_COLOR_LIMIT,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in _as_sequence(value):
        color = normalize_text_style_color(item, "", allow_empty=True)
        if not color or color in seen:
            continue
        normalized.append(color)
        seen.add(color)
        if len(normalized) >= max(0, int(limit)):
            break
    return normalized


def record_recent_text_color(
    colors: Any,
    color: Any,
    *,
    limit: int = TEXT_STYLE_RECENT_COLOR_LIMIT,
) -> list[str]:
    normalized_color = normalize_text_style_color(color, "", allow_empty=True)
    existing = normalize_recent_text_colors(colors, limit=limit)
    if not normalized_color:
        return existing
    return normalize_recent_text_colors([normalized_color, *existing], limit=limit)


def _normalized_choice(value: Any, allowed: Sequence[str], default: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else default


def _normalized_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    return default


def _normalized_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        numeric = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric):
        return default
    return max(minimum, min(numeric, maximum))


def _normalized_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric):
        return default
    return max(minimum, min(numeric, maximum))


def _as_sequence(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


__all__ = [
    "DEFAULT_TEXT_STYLE_PROPERTIES",
    "DEFAULT_INHERITED_RICH_TEXT_STYLE_PROPERTIES",
    "RICH_TEXT_INHERIT_FONT_SIZE",
    "RICH_TEXT_INHERIT_LETTER_SPACING",
    "RICH_TEXT_INHERIT_LINE_HEIGHT",
    "RICH_TEXT_INHERIT_OPACITY",
    "RICH_TEXT_INHERIT_PADDING",
    "RICH_TEXT_SLOT_STYLE_KEYS",
    "TEXT_ANNOTATION_STYLE_KEYS",
    "TEXT_STYLE_FONT_WEIGHTS",
    "TEXT_STYLE_FORMATS",
    "TEXT_STYLE_HORIZONTAL_ALIGNMENTS",
    "TEXT_STYLE_RECENT_COLOR_LIMIT",
    "TEXT_STYLE_VERTICAL_ALIGNMENTS",
    "TEXT_STYLE_WRAP_MODES",
    "normalize_text_annotation_style_payload",
    "normalize_recent_text_colors",
    "normalize_text_style_color",
    "normalize_text_style_properties",
    "record_recent_text_color",
    "rich_text_format_property_key",
    "rich_text_slot_property_keys",
    "rich_text_style_property_key",
]
