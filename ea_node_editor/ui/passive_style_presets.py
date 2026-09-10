from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from secrets import token_hex
from typing import Any, Literal

from ea_node_editor.passive_style_normalization import (
    normalize_flow_edge_style_payload,
    normalize_passive_node_style_payload,
)

PresetKind = Literal["node", "edge"]

_NODE_PRESET_ID_PATTERN = re.compile(r"^node_preset_[0-9a-f]{8}$")
_EDGE_PRESET_ID_PATTERN = re.compile(r"^edge_preset_[0-9a-f]{8}$")

_RAW_BUILT_IN_NODE_PRESETS = (
    {
        "preset_id": "builtin_node_flowchart_classic",
        "name": "Flowchart Classic",
        "style": {
            "fill_color": "#F5FAFD",
            "border_color": "#61798B",
            "text_color": "#173247",
            "border_width": 2.0,
            "font_weight": "bold",
        },
    },
    {
        "preset_id": "builtin_node_planning_warm",
        "name": "Planning Warm",
        "style": {
            "fill_color": "#FFF4E7",
            "border_color": "#C97A2B",
            "text_color": "#4D2D12",
            "border_width": 2.0,
            "corner_radius": 18.0,
        },
    },
    {
        "preset_id": "builtin_node_planning_slate",
        "name": "Planning Slate",
        "style": {
            "fill_color": "#EEF2F7",
            "border_color": "#4F6478",
            "text_color": "#1E2A35",
            "border_width": 2.0,
            "corner_radius": 18.0,
            "font_weight": "bold",
        },
    },
)

_RAW_BUILT_IN_EDGE_PRESETS = (
    {
        "preset_id": "builtin_edge_flow_path",
        "name": "Flow Path",
        "style": {
            "stroke_color": "#2D6C96",
            "stroke_width": 2.5,
            "stroke_pattern": "solid",
            "arrow_head": "filled",
            "label_text_color": "#173247",
            "label_background_color": "#EAF4FB",
        },
    },
    {
        "preset_id": "builtin_edge_review_loop",
        "name": "Review Loop",
        "style": {
            "stroke_color": "#A6722C",
            "stroke_width": 2.0,
            "stroke_pattern": "dashed",
            "arrow_head": "open",
            "label_text_color": "#51310E",
            "label_background_color": "#FFF1DE",
        },
    },
    {
        "preset_id": "builtin_edge_annotation_hint",
        "name": "Annotation Hint",
        "style": {
            "stroke_color": "#657487",
            "stroke_width": 1.5,
            "stroke_pattern": "dotted",
            "arrow_head": "none",
            "label_text_color": "#27323D",
            "label_background_color": "#EEF2F7",
        },
    },
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


def built_in_style_presets(kind: PresetKind) -> list[dict[str, Any]]:
    raw_entries = _RAW_BUILT_IN_NODE_PRESETS if kind == "node" else _RAW_BUILT_IN_EDGE_PRESETS
    style_normalizer = _style_normalizer(kind)
    built_ins: list[dict[str, Any]] = []
    for entry in raw_entries:
        built_ins.append(
            {
                "preset_id": str(entry["preset_id"]),
                "name": str(entry["name"]),
                "style": style_normalizer(entry["style"]),
                "read_only": True,
            }
        )
    return built_ins


class PassiveStylePresetCatalog:
    def __init__(self, kind: PresetKind, user_presets: Any) -> None:
        self._kind = kind
        self._user_presets = normalize_style_preset_entries(user_presets, kind=kind)
        self._built_ins = built_in_style_presets(kind)

    def entries(self) -> list[dict[str, Any]]:
        return [*self.built_in_presets(), *self.user_presets()]

    def built_in_presets(self) -> list[dict[str, Any]]:
        return _clone_entries(self._built_ins)

    def user_presets(self) -> list[dict[str, Any]]:
        return _clone_entries(self._user_presets)

    def get(self, preset_id: str) -> dict[str, Any] | None:
        normalized_id = str(preset_id or "").strip()
        if not normalized_id:
            return None
        for entry in self._built_ins:
            if entry["preset_id"] == normalized_id:
                return copy.deepcopy(entry)
        for entry in self._user_presets:
            if entry["preset_id"] == normalized_id:
                result = copy.deepcopy(entry)
                result["read_only"] = False
                return result
        return None

    def matching_preset_id(self, style: Any) -> str:
        normalized_style = _style_normalizer(self._kind)(style)
        for entry in self._built_ins:
            if entry["style"] == normalized_style:
                return str(entry["preset_id"])
        for entry in self._user_presets:
            if entry["style"] == normalized_style:
                return str(entry["preset_id"])
        return ""

    def save_new(self, name: Any, style: Any) -> dict[str, Any] | None:
        normalized_name = _normalized_preset_name(name, kind=self._kind, index=len(self._user_presets) + 1)
        normalized_style = _style_normalizer(self._kind)(style)
        used_ids = {str(entry.get("preset_id", "")) for entry in [*self._built_ins, *self._user_presets]}
        entry = {
            "preset_id": _new_user_preset_id(self._kind, used_ids=used_ids),
            "name": normalized_name,
            "style": normalized_style,
        }
        self._user_presets.append(entry)
        result = copy.deepcopy(entry)
        result["read_only"] = False
        return result

    def overwrite(self, preset_id: str, style: Any) -> bool:
        index = self._user_index(preset_id)
        if index is None:
            return False
        self._user_presets[index]["style"] = _style_normalizer(self._kind)(style)
        return True

    def rename(self, preset_id: str, name: Any) -> bool:
        index = self._user_index(preset_id)
        if index is None:
            return False
        self._user_presets[index]["name"] = _normalized_preset_name(
            name,
            kind=self._kind,
            index=index + 1,
        )
        return True

    def delete(self, preset_id: str) -> bool:
        index = self._user_index(preset_id)
        if index is None:
            return False
        del self._user_presets[index]
        return True

    def is_user_preset(self, preset_id: str) -> bool:
        return self._user_index(preset_id) is not None

    def is_read_only(self, preset_id: str) -> bool:
        entry = self.get(preset_id)
        return bool(entry and entry.get("read_only"))

    def _user_index(self, preset_id: str) -> int | None:
        normalized_id = str(preset_id or "").strip()
        if not normalized_id:
            return None
        for index, entry in enumerate(self._user_presets):
            if entry["preset_id"] == normalized_id:
                return index
        return None


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
    return normalize_passive_node_style_payload if kind == "node" else normalize_flow_edge_style_payload


def _as_sequence(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _clone_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [copy.deepcopy(entry) for entry in entries]


__all__ = [
    "PassiveStylePresetCatalog",
    "PresetKind",
    "built_in_style_presets",
    "normalize_passive_style_presets",
    "normalize_style_preset_entries",
]
