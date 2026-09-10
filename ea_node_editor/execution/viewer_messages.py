# Purpose: Define viewer messages, message families, and invalidation epoch normalization.
# Map: feature_routes/viewer_session_overlay_fullscreen.md
# Tests: tests/test_execution_viewer_protocol.py, tests/test_protocol_codec.py

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Literal

from ea_node_editor.execution.registry_agreement import (
    _bounded_catalog_text,
    _sha256_digest,
)
from ea_node_editor.execution.run_messages import normalize_target_node_ids
from ea_node_editor.execution.transport_fields import (
    nonnegative_int_value as _nonnegative_int_value,
)

VIEWER_COMMAND_TYPES = frozenset(
    {
        "open_viewer_session",
        "update_viewer_session",
        "close_viewer_session",
        "materialize_viewer_data",
        "query_viewer_session",
    }
)
VIEWER_RESPONSE_EVENT_TYPES = frozenset(
    {
        "viewer_session_opened",
        "viewer_session_updated",
        "viewer_session_closed",
        "viewer_data_materialized",
        "viewer_query_result",
        "viewer_session_failed",
    }
)


@dataclass(frozen=True)
class OpenViewerSessionCommand:
    type: Literal["open_viewer_session"] = "open_viewer_session"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    backend_id: str = ""
    data_refs: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)
    transport_revision: int = 0
    live_open_status: str = ""
    live_open_blocker: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    playback_state: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


@dataclass(frozen=True)
class UpdateViewerSessionCommand:
    type: Literal["update_viewer_session"] = "update_viewer_session"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    backend_id: str = ""
    data_refs: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)
    transport_revision: int = 0
    live_open_status: str = ""
    live_open_blocker: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    playback_state: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


@dataclass(frozen=True)
class CloseViewerSessionCommand:
    type: Literal["close_viewer_session"] = "close_viewer_session"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


@dataclass(frozen=True)
class MaterializeViewerDataCommand:
    type: Literal["materialize_viewer_data"] = "materialize_viewer_data"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    backend_id: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


@dataclass(frozen=True)
class QueryViewerSessionCommand(MaterializeViewerDataCommand):
    """Serializable viewer query routed through the existing worker command path."""

    type: Literal["query_viewer_session"] = "query_viewer_session"
    query_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ViewerSessionOpenedEvent:
    type: Literal["viewer_session_opened"] = "viewer_session_opened"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    backend_id: str = ""
    data_refs: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)
    transport_revision: int = 0
    live_open_status: str = ""
    live_open_blocker: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    playback_state: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


@dataclass(frozen=True)
class ViewerSessionUpdatedEvent:
    type: Literal["viewer_session_updated"] = "viewer_session_updated"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    backend_id: str = ""
    data_refs: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)
    transport_revision: int = 0
    live_open_status: str = ""
    live_open_blocker: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    playback_state: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


@dataclass(frozen=True)
class ViewerSessionClosedEvent:
    type: Literal["viewer_session_closed"] = "viewer_session_closed"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    backend_id: str = ""
    transport: dict[str, Any] = field(default_factory=dict)
    transport_revision: int = 0
    live_open_status: str = ""
    live_open_blocker: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    playback_state: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


@dataclass(frozen=True)
class ViewerDataMaterializedEvent:
    type: Literal["viewer_data_materialized"] = "viewer_data_materialized"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    backend_id: str = ""
    data_refs: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)
    transport_revision: int = 0
    live_open_status: str = ""
    live_open_blocker: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    playback_state: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


@dataclass(frozen=True)
class ViewerQueryResultEvent:
    type: Literal["viewer_query_result"] = "viewer_query_result"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    backend_id: str = ""
    query_type: str = ""
    supported: bool = False
    value: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


@dataclass(frozen=True)
class ViewerSessionFailedEvent:
    type: Literal["viewer_session_failed"] = "viewer_session_failed"
    request_id: str = ""
    workspace_id: str = ""
    node_id: str = ""
    session_id: str = ""
    command: str = ""
    error: str = ""
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


def normalize_viewer_invalidation_node_ids(
    value: Any,
) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)):
        raise TypeError("viewer_invalidation_node_ids must be a list or None")
    return normalize_target_node_ids(value)


def normalize_viewer_node_invalidation_epochs(
    value: Any,
) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("viewer_node_invalidation_epochs must be a list")
    normalized: list[tuple[str, int]] = []
    for index, item in enumerate(value):
        if (
            not isinstance(item, (list, tuple))
            or len(item) != 2
            or not isinstance(item[0], str)
        ):
            raise ValueError(
                f"viewer_node_invalidation_epochs[{index}] must be [node_id, epoch]"
            )
        node_id = item[0].strip()
        if not node_id:
            raise ValueError(
                f"viewer_node_invalidation_epochs[{index}] node_id is required"
            )
        epoch = _nonnegative_int_value(
            item[1],
            field_name=f"viewer_node_invalidation_epochs[{index}].epoch",
        )
        normalized.append((node_id, epoch))
    result = tuple(normalized)
    if result != tuple(sorted(result)):
        raise ValueError("viewer_node_invalidation_epochs must be sorted")
    if len({node_id for node_id, _epoch in result}) != len(result):
        raise ValueError("viewer_node_invalidation_epochs contains duplicate nodes")
    return result


def viewer_epoch_snapshot_digest(
    *,
    workspace_id: str,
    node_ids: tuple[str, ...] | None,
    workspace_epoch: int,
    node_epochs: tuple[tuple[str, int], ...],
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "schema_version": 1,
                "workspace_id": workspace_id,
                "node_ids": None if node_ids is None else list(node_ids),
                "workspace_epoch": workspace_epoch,
                "node_epochs": [list(item) for item in node_epochs],
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def normalize_viewer_invalidation_fields(
    *,
    preparation_id: str,
    workspace_id: str,
    node_ids: Any,
    workspace_epoch: Any,
    node_epochs: Any,
    reservation_id: Any,
    snapshot_digest: Any,
) -> dict[str, Any]:
    normalized_node_ids = normalize_viewer_invalidation_node_ids(node_ids)
    normalized_workspace_epoch = _nonnegative_int_value(
        workspace_epoch,
        field_name="viewer_workspace_invalidation_epoch",
    )
    normalized_node_epochs = normalize_viewer_node_invalidation_epochs(node_epochs)
    normalized_reservation_id = _bounded_catalog_text(
        reservation_id,
        field_name="viewer_invalidation_reservation_id",
        max_length=128,
        allow_empty=True,
    )
    if normalized_reservation_id:
        normalized_digest = _sha256_digest(
            snapshot_digest,
            field_name="viewer_epoch_snapshot_digest",
        )
        if not preparation_id:
            raise ValueError(
                "viewer invalidation reservation requires prepared execution"
            )
        expected_node_ids = () if normalized_node_ids is None else normalized_node_ids
        if (
            tuple(node_id for node_id, _epoch in normalized_node_epochs)
            != expected_node_ids
        ):
            raise ValueError(
                "viewer node epochs must match the exact invalidation filter"
            )
        expected_digest = viewer_epoch_snapshot_digest(
            workspace_id=workspace_id,
            node_ids=normalized_node_ids,
            workspace_epoch=normalized_workspace_epoch,
            node_epochs=normalized_node_epochs,
        )
        if normalized_digest != expected_digest:
            raise ValueError("viewer invalidation snapshot digest mismatch")
    else:
        if preparation_id:
            raise ValueError(
                "prepared execution requires a viewer invalidation reservation"
            )
        if (
            normalized_workspace_epoch != 0
            or normalized_node_epochs
            or snapshot_digest not in {"", None}
        ):
            raise ValueError(
                "legacy start_run forbids viewer invalidation reservation fields"
            )
        normalized_digest = ""
    return {
        "viewer_invalidation_node_ids": normalized_node_ids,
        "viewer_workspace_invalidation_epoch": normalized_workspace_epoch,
        "viewer_node_invalidation_epochs": normalized_node_epochs,
        "viewer_invalidation_reservation_id": normalized_reservation_id,
        "viewer_epoch_snapshot_digest": normalized_digest,
    }


__all__ = [
    "CloseViewerSessionCommand",
    "MaterializeViewerDataCommand",
    "OpenViewerSessionCommand",
    "QueryViewerSessionCommand",
    "UpdateViewerSessionCommand",
    "VIEWER_COMMAND_TYPES",
    "VIEWER_RESPONSE_EVENT_TYPES",
    "ViewerDataMaterializedEvent",
    "ViewerQueryResultEvent",
    "ViewerSessionClosedEvent",
    "ViewerSessionFailedEvent",
    "ViewerSessionOpenedEvent",
    "ViewerSessionUpdatedEvent",
    "normalize_viewer_invalidation_fields",
    "normalize_viewer_invalidation_node_ids",
    "normalize_viewer_node_invalidation_epochs",
    "viewer_epoch_snapshot_digest",
]
