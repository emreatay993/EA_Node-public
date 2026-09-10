from __future__ import annotations

from ea_node_editor.ui.media_video_state import (
    format_video_time,
    normalize_media_video_properties,
    normalize_media_video_state,
    normalize_video_timeline_bookmarks,
)


def test_video_state_normalizes_malformed_values_and_aliases() -> None:
    state = normalize_media_video_state(
        {
            "position": "1250",
            "playing": "yes",
            "muted": "off",
            "volume": 9,
            "rate": "nan",
            "loop": 1,
            "fit_mode": " COVER ",
            "clip_enabled": "true",
            "clip_start_ms": -5,
            "clip_end_ms": "4800",
        }
    )

    assert state == {
        "position_ms": 1250,
        "playing": True,
        "muted": False,
        "volume": 1.0,
        "playback_rate": 1.0,
        "loop": True,
        "fit_mode": "cover",
        "timeline_bookmarks": [],
        "clip_enabled": True,
        "clip_start_ms": 0,
        "clip_end_ms": 4800,
    }


def test_video_bookmarks_drop_duplicates_sort_and_cap() -> None:
    raw = [
        {"id": "same", "label": "Later", "position_ms": 2000},
        {"id": "same", "label": "Duplicate", "position_ms": 1},
        {"id": "", "label": "", "position_ms": 1000},
        {"id": "alpha", "label": "alpha", "position_ms": 2000},
        "invalid",
    ] + [
        {"id": f"extra-{index}", "label": f"Extra {index}", "position_ms": 3000 + index}
        for index in range(205)
    ]

    bookmarks = normalize_video_timeline_bookmarks(raw)

    assert bookmarks[:3] == [
        {"id": "bookmark-1000-2", "label": "0:01", "position_ms": 1000},
        {"id": "alpha", "label": "alpha", "position_ms": 2000},
        {"id": "same", "label": "Later", "position_ms": 2000},
    ]
    assert len(bookmarks) == 200
    assert format_video_time(3_661_000) == "1:01:01"


def test_video_properties_share_state_normalization_without_transient_playing() -> None:
    properties = normalize_media_video_properties(
        {"auto_play": "yes", "playing": True, "position_ms": 250, "volume": 0.4}
    )

    assert properties["auto_play"] is True
    assert properties["position_ms"] == 250
    assert properties["volume"] == 0.4
    assert "playing" not in properties
