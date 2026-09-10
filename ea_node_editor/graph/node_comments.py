from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ea_node_editor.graph.records import NodeCommentRecord


def _text(value: Any, default: str = "") -> str:
    text = "" if value is None else str(value)
    stripped = text.strip()
    return stripped if stripped else default


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False
        return default
    return bool(value)


def normalize_node_comment_record(
    *,
    comment_id: Any,
    body: Any,
    author: Any,
    created_at: Any = "",
    updated_at: Any = "",
    resolved: Any = False,
    unread: Any = True,
    pinned: Any = False,
    parent_id: Any = "",
) -> NodeCommentRecord | None:
    normalized_id = _text(comment_id)
    normalized_body = _text(body)
    if not normalized_id or not normalized_body:
        return None
    normalized_created_at = _text(created_at)
    normalized_updated_at = _text(updated_at, normalized_created_at)
    normalized_parent_id = _text(parent_id)
    if normalized_parent_id == normalized_id:
        normalized_parent_id = ""
    return NodeCommentRecord(
        comment_id=normalized_id,
        body=normalized_body,
        author=_text(author, "You"),
        created_at=normalized_created_at,
        updated_at=normalized_updated_at,
        resolved=_bool(resolved, False),
        unread=_bool(unread, True),
        pinned=_bool(pinned, False),
        parent_id=normalized_parent_id,
    )


def node_comment_record_from_mapping(payload: Any) -> NodeCommentRecord | None:
    if not isinstance(payload, Mapping):
        return None
    return normalize_node_comment_record(
        comment_id=payload.get("id", payload.get("comment_id", "")),
        body=payload.get("body", ""),
        author=payload.get("author", ""),
        created_at=payload.get("created_at", ""),
        updated_at=payload.get("updated_at", ""),
        resolved=payload.get("resolved", False),
        unread=payload.get("unread", True),
        pinned=payload.get("pinned", False),
        parent_id=payload.get("parent_id", ""),
    )


def node_comment_record_to_mapping(record: NodeCommentRecord) -> dict[str, Any]:
    return {
        "id": str(record.comment_id),
        "body": str(record.body),
        "author": str(record.author),
        "created_at": str(record.created_at),
        "updated_at": str(record.updated_at),
        "resolved": bool(record.resolved),
        "unread": bool(record.unread),
        "pinned": bool(record.pinned),
        "parent_id": str(record.parent_id),
    }


def node_comments_from_payload(value: Any) -> list[NodeCommentRecord]:
    if not isinstance(value, list):
        return []
    records: list[NodeCommentRecord] = []
    seen_ids: set[str] = set()
    for item in value:
        record = node_comment_record_from_mapping(item)
        if record is None or record.comment_id in seen_ids:
            continue
        seen_ids.add(record.comment_id)
        records.append(record)
    return records


def node_comments_to_payload(records: list[NodeCommentRecord]) -> list[dict[str, Any]]:
    return [node_comment_record_to_mapping(record) for record in records]


def node_comment_badge_payload(records: list[NodeCommentRecord]) -> dict[str, Any]:
    count = len(records)
    open_count = sum(1 for record in records if not record.resolved)
    indexed = list(enumerate(records))
    indexed.sort(key=lambda item: (not item[1].pinned, item[1].resolved, item[0]))
    return {
        "count": count,
        "open_count": open_count,
        "resolved_all": count > 0 and open_count == 0,
        "unread": any(record.unread for record in records),
        "preview_comments": [
            node_comment_record_to_mapping(record) for _, record in indexed[:2]
        ],
    }


__all__ = [
    "node_comment_badge_payload",
    "node_comment_record_from_mapping",
    "node_comment_record_to_mapping",
    "node_comments_from_payload",
    "node_comments_to_payload",
    "normalize_node_comment_record",
]
