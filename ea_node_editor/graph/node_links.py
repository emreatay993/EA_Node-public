from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from ea_node_editor.graph.records import NodeLinkRecord

NODE_LINK_KINDS: tuple[str, ...] = ("url", "file", "folder", "workspace", "node")
COREX_LINK_SCHEME = "corex-link:"


def normalize_node_link_kind(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in NODE_LINK_KINDS else "url"


def default_node_link_title(kind: Any, target: Any) -> str:
    normalized_kind = normalize_node_link_kind(kind)
    normalized_target = str(target or "").strip()
    if not normalized_target:
        return {
            "url": "Web link",
            "file": "File link",
            "folder": "Folder link",
            "workspace": "Workspace link",
            "node": "Node link",
        }[normalized_kind]
    if normalized_kind == "url":
        parsed = urlparse(normalized_target)
        return parsed.netloc or parsed.path or normalized_target
    if normalized_kind in {"file", "folder"}:
        try:
            name = Path(normalized_target).name
        except (OSError, ValueError):
            name = ""
        return name or normalized_target
    return normalized_target


def normalize_node_link_record(
    *,
    link_id: Any,
    kind: Any,
    title: Any,
    target: Any,
    subtitle: Any = "",
    target_workspace_id: Any = "",
    target_node_id: Any = "",
    source_workspace_id: Any = "",
) -> NodeLinkRecord | None:
    normalized_id = str(link_id or "").strip()
    normalized_kind = normalize_node_link_kind(kind)
    normalized_target_node_id = str(target_node_id or "").strip()
    normalized_target = str(target or "").strip()
    if normalized_kind == "node" and normalized_target_node_id:
        normalized_target = normalized_target_node_id
    if not normalized_id or not normalized_target:
        return None
    normalized_target_workspace_id = str(target_workspace_id or "").strip()
    if normalized_kind == "node":
        normalized_target_node_id = normalized_target_node_id or normalized_target
        normalized_target_workspace_id = normalized_target_workspace_id or str(source_workspace_id or "").strip()
    else:
        normalized_target_node_id = ""
        normalized_target_workspace_id = ""
    normalized_title = str(title or "").strip() or default_node_link_title(normalized_kind, normalized_target)
    return NodeLinkRecord(
        link_id=normalized_id,
        kind=normalized_kind,
        title=normalized_title,
        target=normalized_target,
        subtitle=str(subtitle or "").strip(),
        target_workspace_id=normalized_target_workspace_id,
        target_node_id=normalized_target_node_id,
    )


def node_link_record_from_mapping(
    payload: Any,
    *,
    source_workspace_id: Any = "",
) -> NodeLinkRecord | None:
    if not isinstance(payload, Mapping):
        return None
    return normalize_node_link_record(
        link_id=payload.get("id", payload.get("link_id", "")),
        kind=payload.get("kind", ""),
        title=payload.get("title", ""),
        target=payload.get("target", ""),
        subtitle=payload.get("subtitle", ""),
        target_workspace_id=payload.get("target_workspace_id", ""),
        target_node_id=payload.get("target_node_id", ""),
        source_workspace_id=source_workspace_id,
    )


def node_link_record_to_mapping(
    record: NodeLinkRecord,
    *,
    source_workspace_id: Any = "",
) -> dict[str, str]:
    kind = normalize_node_link_kind(record.kind)
    target = str(record.target)
    payload = {
        "id": str(record.link_id),
        "kind": kind,
        "title": str(record.title),
        "target": target,
        "subtitle": str(record.subtitle),
    }
    if kind == "node":
        target_node_id = str(record.target_node_id or target).strip()
        target_workspace_id = str(record.target_workspace_id or source_workspace_id or "").strip()
        if target_node_id:
            payload["target_node_id"] = target_node_id
        if target_workspace_id:
            payload["target_workspace_id"] = target_workspace_id
    return payload


def node_links_from_payload(
    value: Any,
    *,
    source_workspace_id: Any = "",
) -> list[NodeLinkRecord]:
    if not isinstance(value, list):
        return []
    records: list[NodeLinkRecord] = []
    seen_ids: set[str] = set()
    for item in value:
        record = node_link_record_from_mapping(item, source_workspace_id=source_workspace_id)
        if record is None or record.link_id in seen_ids:
            continue
        seen_ids.add(record.link_id)
        records.append(record)
    return records


def node_links_to_payload(
    records: list[NodeLinkRecord],
    *,
    source_workspace_id: Any = "",
) -> list[dict[str, str]]:
    return [
        node_link_record_to_mapping(record, source_workspace_id=source_workspace_id)
        for record in records
    ]


def node_link_targets_node(
    record: NodeLinkRecord,
    *,
    source_workspace_id: object,
    target_workspace_id: object,
    target_node_id: object,
) -> bool:
    if normalize_node_link_kind(record.kind) != "node":
        return False
    normalized_source_workspace_id = str(source_workspace_id or "").strip()
    normalized_target_workspace_id = str(target_workspace_id or "").strip()
    normalized_target_node_id = str(target_node_id or "").strip()
    record_workspace_id = str(
        record.target_workspace_id or normalized_source_workspace_id
    ).strip()
    record_node_id = str(record.target_node_id or record.target or "").strip()
    return bool(
        normalized_target_workspace_id
        and normalized_target_node_id
        and record_workspace_id == normalized_target_workspace_id
        and record_node_id == normalized_target_node_id
    )


def corex_link_href(link_id: Any) -> str:
    normalized = str(link_id or "").strip()
    return f"{COREX_LINK_SCHEME}{normalized}" if normalized else ""


def corex_link_id_from_href(href: Any) -> str:
    text = str(href or "").strip()
    if not text.startswith(COREX_LINK_SCHEME):
        return ""
    return text[len(COREX_LINK_SCHEME):].strip()


def unwrap_corex_link_anchors(text: Any, link_id: Any) -> str:
    source = str(text or "")
    normalized_id = str(link_id or "").strip()
    if not source or not normalized_id:
        return source
    href = re.escape(corex_link_href(normalized_id))
    return re.sub(rf"\[([^\]]+)\]\({href}\)", r"\1", source)


__all__ = [
    "COREX_LINK_SCHEME",
    "NODE_LINK_KINDS",
    "corex_link_href",
    "corex_link_id_from_href",
    "default_node_link_title",
    "node_link_record_from_mapping",
    "node_link_record_to_mapping",
    "node_link_targets_node",
    "node_links_from_payload",
    "node_links_to_payload",
    "normalize_node_link_kind",
    "normalize_node_link_record",
    "unwrap_corex_link_anchors",
]
