# Purpose: Resolve the effective authored or runtime source for Media Panel UI consumers.
# Map: feature_routes/media_image_video_pdf_refocus
# Tests: tests/test_media_panel_source_resolution.py
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from PyQt6.QtCore import QUrl

from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.file_dialog_filters import media_kind_from_source
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
from ea_node_editor.runtime_contracts import DataTree, ImageValue, RuntimeArtifactRef
from ea_node_editor.ui.image_value_preview_provider import image_value_preview_source
from ea_node_editor.ui.media_preview_provider import (
    LOCAL_MEDIA_PREVIEW_PROVIDER_ID,
    describe_local_image,
)
from ea_node_editor.ui.pdf_preview_provider import describe_pdf_preview
from ea_node_editor.ui.support.solution_output_cache import retained_output_record


_READY_STATE = "ready"


def _safe_media_kind(value: object) -> str:
    try:
        return media_kind_from_source(value)
    except (OSError, TypeError, ValueError):
        return ""


@dataclass(frozen=True, slots=True)
class MediaPanelSourceResolution:
    authority: str
    input_exposed: bool
    input_connected: bool
    state: str
    media_kind: str = ""
    source_ref: str = ""
    resolved_source_url: str = ""
    preview_source_url: str = ""
    message: str = ""
    raw_value: object | None = field(default=None, repr=False, compare=False)

    def to_qml_payload(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "input_exposed": self.input_exposed,
            "input_connected": self.input_connected,
            "state": self.state,
            "media_kind": self.media_kind,
            "source_ref": self.source_ref,
            "resolved_source_url": self.resolved_source_url,
            "preview_source_url": self.preview_source_url,
            "message": self.message,
        }


def media_panel_source_input_exposed(node: object) -> bool:
    if str(getattr(node, "type_id", "") or "").strip() != MEDIA_PANEL_TYPE_ID:
        return False
    exposed_ports = getattr(node, "exposed_ports", {})
    return bool(
        exposed_ports.get("source", True)
        if isinstance(exposed_ports, Mapping)
        else True
    )


def _input_connected(workspace: object, node_id: str) -> bool:
    edges = getattr(workspace, "edges", {})
    values = edges.values() if isinstance(edges, Mapping) else edges
    for edge in values or ():
        if (
            bool(getattr(edge, "enabled", True))
            and str(getattr(edge, "target_node_id", "") or "").strip() == node_id
            and str(getattr(edge, "target_port_key", "") or "").strip()
            == "source"
        ):
            return True
    return False


def _latest_output_record(run_state: object | None, workspace_id: str, node_id: str):
    return retained_output_record(run_state, workspace_id, node_id)


def _node_execution_state(run_state: object | None, workspace_id: str, node_id: str) -> str:
    if run_state is None:
        return ""
    execution_workspace_id = str(
        getattr(run_state, "node_execution_workspace_id", "") or ""
    ).strip()
    if execution_workspace_id != workspace_id:
        return ""
    for state, attribute in (
        ("running", "running_node_ids"),
        ("failed", "failed_node_ids"),
        ("failed", "blocked_node_ids"),
        ("empty", "empty_node_ids"),
        ("completed", "completed_node_ids"),
    ):
        values = getattr(run_state, attribute, ())
        if isinstance(values, (set, frozenset, list, tuple)) and node_id in values:
            return state
    return ""


def _first_error_message(value: object) -> str:
    errors = getattr(value, "errors", ())
    for error in errors if isinstance(errors, (list, tuple)) else ():
        message = (
            error.get("error", "")
            if isinstance(error, Mapping)
            else getattr(error, "error", "")
        )
        normalized = str(message or "").strip()
        if normalized:
            return normalized[:400]
    return ""


def _failed_message(run_state: object | None, node_id: str) -> str:
    errors_by_node = getattr(run_state, "root_errors_by_node_id", {})
    errors = errors_by_node.get(node_id, ()) if isinstance(errors_by_node, Mapping) else ()
    for error in errors if isinstance(errors, (list, tuple)) else ():
        message = (
            error.get("error", "")
            if isinstance(error, Mapping)
            else getattr(error, "error", "")
        )
        normalized = str(message or "").strip()
        if normalized:
            return normalized[:400]
    return ""


def _invalid_failure(message: str) -> bool:
    normalized = str(message or "").casefold()
    return any(
        marker in normalized
        for marker in (
            "requires exactly one",
            "source input is empty",
            "source must be",
            "unsupported media",
        )
    )


def _non_ready(
    *,
    authority: str,
    input_exposed: bool,
    input_connected: bool,
    state: str,
    message: str,
) -> MediaPanelSourceResolution:
    return MediaPanelSourceResolution(
        authority=authority,
        input_exposed=input_exposed,
        input_connected=input_connected,
        state=state,
        message=message,
    )


def _image_preview_url(source_url: str) -> str:
    return (
        f"image://{LOCAL_MEDIA_PREVIEW_PROVIDER_ID}/preview?"
        f"source={quote(source_url, safe='')}"
    )


def _resolve_value(
    value: object,
    *,
    authority: str,
    input_exposed: bool,
    input_connected: bool,
    project_path: str | Path | None,
    project_metadata: Mapping[str, Any] | None,
    page_number: object,
) -> MediaPanelSourceResolution:
    if type(value) is ImageValue:
        preview_url = image_value_preview_source(value)
        if not preview_url:
            return _non_ready(
                authority=authority,
                input_exposed=input_exposed,
                input_connected=input_connected,
                state="invalid",
                message="The Image value could not be prepared for display.",
            )
        return MediaPanelSourceResolution(
            authority=authority,
            input_exposed=input_exposed,
            input_connected=input_connected,
            state=_READY_STATE,
            media_kind="image",
            resolved_source_url=preview_url,
            preview_source_url=preview_url,
            raw_value=value,
        )

    if type(value) is RuntimeArtifactRef:
        source_ref = value.ref
        declared_kind = _safe_media_kind(f"source.{value.format}")
    elif type(value) is str or isinstance(value, os.PathLike):
        try:
            source_ref = os.fspath(value)
        except (OSError, TypeError, ValueError):
            source_ref = ""
        if not isinstance(source_ref, str):
            source_ref = ""
        source_ref = source_ref.strip()
        declared_kind = _safe_media_kind(source_ref)
    else:
        return _non_ready(
            authority=authority,
            input_exposed=input_exposed,
            input_connected=input_connected,
            state="invalid",
            message="Media Panel supports Path, String, or Image values.",
        )

    if not source_ref:
        return _non_ready(
            authority=authority,
            input_exposed=input_exposed,
            input_connected=input_connected,
            state="empty",
            message="The Media Panel source is empty.",
        )

    try:
        parsed = urlsplit(source_ref)
    except ValueError:
        parsed = urlsplit("")
    remote = parsed.scheme.casefold() in {"http", "https"}
    if remote:
        media_kind = declared_kind
        if not media_kind:
            return _non_ready(
                authority=authority,
                input_exposed=input_exposed,
                input_connected=input_connected,
                state="invalid",
                message="The URL does not identify a supported media file.",
            )
        return MediaPanelSourceResolution(
            authority=authority,
            input_exposed=input_exposed,
            input_connected=input_connected,
            state=_READY_STATE,
            media_kind=media_kind,
            source_ref=source_ref,
            resolved_source_url=source_ref,
            preview_source_url=source_ref if media_kind == "image" else "",
            raw_value=value,
        )

    resolver = ProjectArtifactResolver(
        project_path=project_path,
        project_metadata=(
            dict(project_metadata) if isinstance(project_metadata, Mapping) else None
        ),
    )
    try:
        resolution = resolver.resolve(source_ref)
    except (OSError, ValueError):
        return _non_ready(
            authority=authority,
            input_exposed=input_exposed,
            input_connected=input_connected,
            state="invalid",
            message="The Media Panel source could not be resolved.",
        )
    path = resolution.absolute_path
    if path is None:
        state = (
            "stale"
            if resolution.kind in {"managed_missing", "staged_missing"}
            else "invalid"
        )
        return _non_ready(
            authority=authority,
            input_exposed=input_exposed,
            input_connected=input_connected,
            state=state,
            message="The Media Panel source could not be resolved.",
        )
    try:
        source_exists = path.exists() and path.is_file()
    except OSError:
        source_exists = False
    if not source_exists:
        return _non_ready(
            authority=authority,
            input_exposed=input_exposed,
            input_connected=input_connected,
            state="stale",
            message="The Media Panel source file could not be found.",
        )

    media_kind = declared_kind or _safe_media_kind(path)
    if not media_kind:
        return _non_ready(
            authority=authority,
            input_exposed=input_exposed,
            input_connected=input_connected,
            state="invalid",
            message="The selected file is not a supported image, PDF, or video.",
        )
    resolved_url = QUrl.fromLocalFile(str(path)).toString()
    preview_url = ""
    if media_kind == "image":
        image_preview = describe_local_image(resolved_url)
        if str(image_preview.get("state", "")) != _READY_STATE:
            return _non_ready(
                authority=authority,
                input_exposed=input_exposed,
                input_connected=input_connected,
                state="invalid",
                message=str(image_preview.get("message", "") or "The image could not be decoded."),
            )
        preview_url = _image_preview_url(resolved_url)
    elif media_kind == "pdf":
        pdf_preview = describe_pdf_preview(resolved_url, page_number)
        if str(pdf_preview.get("state", "")) != _READY_STATE:
            return _non_ready(
                authority=authority,
                input_exposed=input_exposed,
                input_connected=input_connected,
                state="invalid",
                message=str(pdf_preview.get("message", "") or "The PDF could not be opened."),
            )
        preview_url = str(pdf_preview.get("preview_url", "") or "")

    return MediaPanelSourceResolution(
        authority=authority,
        input_exposed=input_exposed,
        input_connected=input_connected,
        state=_READY_STATE,
        media_kind=media_kind,
        source_ref=source_ref,
        resolved_source_url=resolved_url,
        preview_source_url=preview_url,
        raw_value=value,
    )


def resolve_media_panel_source(
    *,
    node: object,
    workspace: object,
    run_state: object | None = None,
    project_path: str | Path | None = None,
    project_metadata: Mapping[str, Any] | None = None,
) -> MediaPanelSourceResolution:
    input_exposed = media_panel_source_input_exposed(node)
    node_id = str(getattr(node, "node_id", "") or "").strip()
    workspace_id = str(getattr(workspace, "workspace_id", "") or "").strip()
    input_connected = _input_connected(workspace, node_id)
    properties = getattr(node, "properties", {})
    properties = properties if isinstance(properties, Mapping) else {}
    page_number = properties.get("page_number", 1)

    if not input_exposed:
        return _resolve_value(
            properties.get("source", ""),
            authority="property",
            input_exposed=False,
            input_connected=input_connected,
            project_path=project_path,
            project_metadata=project_metadata,
            page_number=page_number,
        )

    if not input_connected:
        return _non_ready(
            authority="input",
            input_exposed=True,
            input_connected=False,
            state="waiting",
            message="Connect a Path, String, or Image value to Source.",
        )

    execution_state = _node_execution_state(run_state, workspace_id, node_id)
    if execution_state == "running":
        return _non_ready(
            authority="input",
            input_exposed=True,
            input_connected=True,
            state="running",
            message="Media Panel is running.",
        )

    record = _latest_output_record(run_state, workspace_id, node_id)
    if record is not None and not bool(record.get("outputs_available", True)):
        return _non_ready(
            authority="input",
            input_exposed=True,
            input_connected=True,
            state="unavailable",
            message="The connected runtime output is unavailable.",
        )
    if record is not None and bool(record.get("stale", False)):
        return _non_ready(
            authority="input",
            input_exposed=True,
            input_connected=True,
            state="stale",
            message="The Media Panel input is stale because the graph changed.",
        )

    outputs = record.get("outputs") if isinstance(record, Mapping) else None
    result = outputs.get("_surface_source") if isinstance(outputs, Mapping) else None
    if execution_state == "failed":
        message = (
            _first_error_message(result)
            if isinstance(result, SettledPortResult)
            and str(result.status or "").strip().casefold() == "failed"
            else ""
        ) or _failed_message(run_state, node_id)
        return _non_ready(
            authority="input",
            input_exposed=True,
            input_connected=True,
            state="invalid" if _invalid_failure(message) else "failed",
            message=message or "Media Panel is blocked by an upstream failure.",
        )
    if execution_state == "empty":
        return _non_ready(
            authority="input",
            input_exposed=True,
            input_connected=True,
            state="empty",
            message="The connected source produced no media.",
        )
    if isinstance(result, SettledPortResult):
        status = str(result.status or "").strip().casefold()
        if status == "failed":
            message = _first_error_message(result) or _failed_message(run_state, node_id)
            return _non_ready(
                authority="input",
                input_exposed=True,
                input_connected=True,
                state="invalid" if _invalid_failure(message) else "failed",
                message=message or "Media Panel failed to resolve its source input.",
            )
        if status == "empty" or result.value is None:
            return _non_ready(
                authority="input",
                input_exposed=True,
                input_connected=True,
                state="empty",
                message="The connected source produced no media.",
            )
        tree = result.value
        if not isinstance(tree, DataTree) or tree.item_count != 1:
            return _non_ready(
                authority="input",
                input_exposed=True,
                input_connected=True,
                state="invalid",
                message="Media Panel source requires exactly one runtime item.",
            )
        raw_value = next(
            item for _path, items in tree.branches for item in items
        )
        return _resolve_value(
            raw_value,
            authority="input",
            input_exposed=True,
            input_connected=True,
            project_path=project_path,
            project_metadata=project_metadata,
            page_number=page_number,
        )

    if execution_state == "completed":
        return _non_ready(
            authority="input",
            input_exposed=True,
            input_connected=True,
            state="empty",
            message="The connected source produced no media.",
        )
    return _non_ready(
        authority="input",
        input_exposed=True,
        input_connected=True,
        state="waiting",
        message="Run the Media Panel to display the connected source.",
    )


__all__ = [
    "MediaPanelSourceResolution",
    "media_panel_source_input_exposed",
    "resolve_media_panel_source",
]
