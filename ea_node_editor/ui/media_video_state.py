# Purpose: Normalize Media Panel video playback, bookmark, and clip state.
# Map: feature_routes/media_image_video_pdf_refocus.md
# Tests: tests/test_media_video_state.py
from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        number = default
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
    if not math.isfinite(number):
        number = default
    return max(minimum, min(maximum, number))


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def format_video_time(position_ms: int) -> str:
    total_seconds = _non_negative_int(position_ms) // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def normalize_video_fit_mode(value: Any) -> str:
    return "cover" if str(value or "").strip().lower() == "cover" else "contain"


def normalize_video_timeline_bookmarks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    bookmarks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            continue
        position_ms = _non_negative_int(item.get("position_ms"))
        bookmark_id = str(item.get("id", "") or "").strip() or f"bookmark-{position_ms}-{index}"
        if bookmark_id in seen_ids:
            continue
        seen_ids.add(bookmark_id)
        label = str(item.get("label", "") or "").strip() or format_video_time(position_ms)
        bookmarks.append({"id": bookmark_id, "label": label[:80], "position_ms": position_ms})
    bookmarks.sort(
        key=lambda item: (
            int(item["position_ms"]),
            str(item["label"]).casefold(),
            str(item["id"]),
        )
    )
    return bookmarks[:200]


def normalize_media_video_state(value: Any) -> dict[str, Any]:
    payload = value if isinstance(value, Mapping) else {}
    position_value = payload.get("position_ms") if "position_ms" in payload else payload.get("position")
    rate_value = payload.get("playback_rate") if "playback_rate" in payload else payload.get("rate")
    return {
        "position_ms": _non_negative_int(position_value),
        "playing": _bool_value(payload.get("playing")),
        "muted": _bool_value(payload.get("muted")),
        "volume": _bounded_float(payload.get("volume"), 1.0, 0.0, 1.0),
        "playback_rate": _bounded_float(rate_value, 1.0, 0.25, 4.0),
        "loop": _bool_value(payload.get("loop")),
        "fit_mode": normalize_video_fit_mode(payload.get("fit_mode")),
        "timeline_bookmarks": normalize_video_timeline_bookmarks(payload.get("timeline_bookmarks")),
        "clip_enabled": _bool_value(payload.get("clip_enabled")),
        "clip_start_ms": _non_negative_int(payload.get("clip_start_ms")),
        "clip_end_ms": _non_negative_int(payload.get("clip_end_ms")),
    }


def normalize_media_video_properties(value: Any) -> dict[str, Any]:
    payload = value if isinstance(value, Mapping) else {}
    state = normalize_media_video_state(payload)
    state.pop("playing")
    state["auto_play"] = _bool_value(payload.get("auto_play"))
    return state
