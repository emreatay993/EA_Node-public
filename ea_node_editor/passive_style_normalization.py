from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping, Sequence
from secrets import token_hex
from typing import Any, Literal

PresetKind = Literal["node", "edge"]

_FINAL_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")
_NODE_PRESET_ID_PATTERN = re.compile(r"^node_preset_[0-9a-f]{8}$")
_EDGE_PRESET_ID_PATTERN = re.compile(r"^edge_preset_[0-9a-f]{8}$")

PASSIVE_NODE_STYLE_FONT_WEIGHTS = ("normal", "bold")
PASSIVE_NODE_STYLE_GRADIENT_DIRECTIONS = ("north", "east", "south", "west", "radial")
DEFAULT_PASSIVE_NODE_STYLE_GRADIENT_DIRECTION = "south"
FLOW_EDGE_STYLE_PATTERNS = ("solid", "dashed", "dotted")
FLOW_EDGE_ARROW_HEADS = ("filled", "open", "none")
FLOW_EDGE_PATH_MODES = ("auto", "pipe", "bezier")
RETIRED_PASSIVE_NODE_STYLE_KEYS = frozenset(
    {
        "accent_color",
        "header_color",
        "header_gradient_enabled",
        "header_gradient_color",
        "header_gradient_direction",
    }
)
_PASSIVE_NODE_STYLE_KEYS = frozenset(
    {
        "fill_color",
        "border_color",
        "text_color",
        "gradient_enabled",
        "gradient_color",
        "gradient_direction",
        "border_width",
        "corner_radius",
        "font_size",
        "font_weight",
        *RETIRED_PASSIVE_NODE_STYLE_KEYS,
    }
)


def normalize_passive_style_presets(value: Any) -> dict[str, list[dict[str, Any]]]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "node_presets": normalize_style_preset_entries(source.get("node_presets"), kind="node"),
        "edge_presets": normalize_style_preset_entries(source.get("edge_presets"), kind="edge"),
    }


def normalize_style_preset_entries(value: Any, *, kind: PresetKind) -> list[dict[str, Any]]:
    style_normalizer = _style_normalizer(kind)
    normalized_entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, entry in enumerate(_as_sequence(value), start=1):
        if not isinstance(entry, Mapping):
            continue
        preset_id = _normalized_user_preset_id(
            entry.get("preset_id"),
            kind=kind,
            used_ids=seen_ids,
        )
        seen_ids.add(preset_id)
        normalized_entries.append(
            {
                "preset_id": preset_id,
                "name": _normalized_preset_name(entry.get("name"), kind=kind, index=index),
                "style": style_normalizer(entry.get("style")),
            }
        )
    return normalized_entries


def normalize_passive_node_style_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, Any] = {}

    for key in ("fill_color", "border_color", "text_color"):
        color_value = _normalized_hex_color(value.get(key))
        if color_value:
            normalized[key] = color_value

    _normalize_node_gradient_fields(
        value,
        normalized,
        enabled_key="gradient_enabled",
        color_key="gradient_color",
        direction_key="gradient_direction",
    )
    border_width = _normalized_positive_number(value.get("border_width"))
    if border_width is not None:
        normalized["border_width"] = border_width

    corner_radius = _normalized_nonnegative_number(value.get("corner_radius"))
    if corner_radius is not None:
        normalized["corner_radius"] = corner_radius

    font_size = _normalized_positive_int(value.get("font_size"))
    if font_size is not None:
        normalized["font_size"] = font_size

    font_weight = str(value.get("font_weight", "")).strip().lower()
    if font_weight in PASSIVE_NODE_STYLE_FONT_WEIGHTS:
        normalized["font_weight"] = font_weight

    return normalized


def normalize_flow_edge_style_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, Any] = {}

    for key in ("stroke_color", "label_text_color", "label_background_color"):
        color_value = _normalized_hex_color(value.get(key))
        if color_value:
            normalized[key] = color_value

    stroke_width = _normalized_positive_number(value.get("stroke_width"))
    if stroke_width is not None:
        normalized["stroke_width"] = stroke_width

    stroke_pattern = str(value.get("stroke_pattern", "")).strip().lower()
    if stroke_pattern in FLOW_EDGE_STYLE_PATTERNS:
        normalized["stroke_pattern"] = stroke_pattern

    arrow_head = str(value.get("arrow_head", "")).strip().lower()
    if arrow_head in FLOW_EDGE_ARROW_HEADS:
        normalized["arrow_head"] = arrow_head

    path_mode = str(value.get("path_mode", "")).strip().lower()
    if path_mode in FLOW_EDGE_PATH_MODES and path_mode != "auto":
        normalized["path_mode"] = path_mode

    return normalized


def _normalized_user_preset_id(value: Any, *, kind: PresetKind, used_ids: set[str]) -> str:
    normalized = str(value or "").strip().lower()
    pattern = _NODE_PRESET_ID_PATTERN if kind == "node" else _EDGE_PRESET_ID_PATTERN
    if normalized and pattern.match(normalized) and normalized not in used_ids:
        return normalized
    return _new_user_preset_id(kind, used_ids=used_ids)


def _new_user_preset_id(kind: PresetKind, *, used_ids: set[str]) -> str:
    prefix = "node_preset_" if kind == "node" else "edge_preset_"
    while True:
        candidate = f"{prefix}{token_hex(4)}"
        if candidate not in used_ids:
            return candidate


def _normalized_preset_name(value: Any, *, kind: PresetKind, index: int) -> str:
    normalized = str(value or "").strip()
    if normalized:
        return normalized
    return f"{kind.title()} Preset {index}"


def _style_normalizer(kind: PresetKind):
    return _normalize_project_node_preset_style if kind == "node" else normalize_flow_edge_style_payload


def _normalize_project_node_preset_style(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    normalized = {
        str(key): copy.deepcopy(item)
        for key, item in value.items()
        if str(key) not in _PASSIVE_NODE_STYLE_KEYS
    }
    normalized.update(normalize_passive_node_style_payload(value))
    return normalized


def _as_sequence(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _normalized_hex_color(value: Any) -> str:
    normalized = str(value or "").strip()
    if not _FINAL_HEX_COLOR.match(normalized):
        return ""
    return normalized


def _normalize_node_gradient_fields(
    source: Mapping[str, Any],
    target: dict[str, Any],
    *,
    enabled_key: str,
    color_key: str,
    direction_key: str,
) -> None:
    enabled = _normalized_optional_bool(source.get(enabled_key))
    if enabled is False:
        target[enabled_key] = False
        return
    color_value = _normalized_hex_color(source.get(color_key))
    if enabled is True:
        if not color_value:
            return
        target[enabled_key] = True
        target[color_key] = color_value
        target[direction_key] = _normalized_gradient_direction(source.get(direction_key))
        return
    if color_value:
        target[color_key] = color_value
        target[direction_key] = _normalized_gradient_direction(source.get(direction_key))


def _normalized_optional_bool(value: Any) -> bool | None:
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
    return None


def _normalized_gradient_direction(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in PASSIVE_NODE_STYLE_GRADIENT_DIRECTIONS:
        return normalized
    return DEFAULT_PASSIVE_NODE_STYLE_GRADIENT_DIRECTION


def _normalized_positive_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or numeric <= 0.0:
        return None
    return numeric


def _normalized_nonnegative_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or numeric < 0.0:
        return None
    return numeric


def _normalized_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    return numeric


__all__ = [
    "DEFAULT_PASSIVE_NODE_STYLE_GRADIENT_DIRECTION",
    "FLOW_EDGE_ARROW_HEADS",
    "FLOW_EDGE_PATH_MODES",
    "FLOW_EDGE_STYLE_PATTERNS",
    "PASSIVE_NODE_STYLE_GRADIENT_DIRECTIONS",
    "PASSIVE_NODE_STYLE_FONT_WEIGHTS",
    "PresetKind",
    "RETIRED_PASSIVE_NODE_STYLE_KEYS",
    "normalize_flow_edge_style_payload",
    "normalize_passive_node_style_payload",
    "normalize_passive_style_presets",
    "normalize_style_preset_entries",
]
