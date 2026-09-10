from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote, unquote, urlsplit

from ea_node_editor.nodes.file_dialog_filters import is_supported_media_source_reference
from ea_node_editor.persistence.artifact_resolution import ArtifactResolution, ProjectArtifactResolver

FILE_REPAIR_REQUEST_PREFIX = "ea-file-repair:"
MANAGED_COPY_MODE = "managed_copy"
EXTERNAL_LINK_MODE = "external_link"

_TRACKED_REPAIR_MODES: dict[tuple[str, str], tuple[str, ...]] = {
    ("media.panel", "source"): (MANAGED_COPY_MODE, EXTERNAL_LINK_MODE),
    ("passive.media.mail_panel", "source_path"): (MANAGED_COPY_MODE, EXTERNAL_LINK_MODE),
    ("io.file_read", "path"): (EXTERNAL_LINK_MODE,),
    ("io.excel_read", "path"): (EXTERNAL_LINK_MODE,),
    ("tabular.input", "path"): (MANAGED_COPY_MODE, EXTERNAL_LINK_MODE),
}


@dataclass(frozen=True, slots=True)
class FileRepairRequest:
    current_value: str


@dataclass(frozen=True, slots=True)
class NodeFileIssue:
    node_id: str
    property_key: str
    property_label: str
    property_value: str
    issue_kind: str
    source_kind: str
    source_mode: str
    message: str
    repair_modes: tuple[str, ...]

    @property
    def repair_request(self) -> str:
        return encode_file_repair_request(self.property_value)

    @property
    def supports_managed_repair(self) -> bool:
        return MANAGED_COPY_MODE in self.repair_modes

    @property
    def supports_external_repair(self) -> bool:
        return EXTERNAL_LINK_MODE in self.repair_modes


def encode_file_repair_request(current_value: str) -> str:
    normalized_value = str(current_value or "").strip()
    return FILE_REPAIR_REQUEST_PREFIX + quote(normalized_value, safe="")


def decode_file_repair_request(value: str | None) -> FileRepairRequest | None:
    normalized = str(value or "").strip()
    if not normalized.startswith(FILE_REPAIR_REQUEST_PREFIX):
        return None
    return FileRepairRequest(current_value=unquote(normalized[len(FILE_REPAIR_REQUEST_PREFIX) :]))


def repair_modes_for_node_property(node_type_id: str, property_key: str) -> tuple[str, ...]:
    return _TRACKED_REPAIR_MODES.get((str(node_type_id or "").strip(), str(property_key or "").strip()), ())


def source_mode_for_resolution_kind(kind: str) -> str:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind in {"managed", "managed_missing", "staged", "staged_missing"}:
        return MANAGED_COPY_MODE
    return EXTERNAL_LINK_MODE


def preferred_repair_mode_for_value(
    value: str,
    *,
    project_path: str | None,
    project_metadata: Mapping[str, Any] | None,
    fallback_mode: str = EXTERNAL_LINK_MODE,
    allowed_modes: tuple[str, ...] = (),
) -> str:
    if not allowed_modes:
        return str(fallback_mode or EXTERNAL_LINK_MODE).strip().lower() or EXTERNAL_LINK_MODE
    fallback = str(fallback_mode or "").strip().lower()
    if fallback not in allowed_modes:
        fallback = allowed_modes[0]
    resolver = ProjectArtifactResolver(
        project_path=project_path,
        project_metadata=dict(project_metadata) if isinstance(project_metadata, Mapping) else None,
    )
    preferred = source_mode_for_resolution_kind(resolver.resolve(value).kind)
    return preferred if preferred in allowed_modes else fallback


def build_file_issue_payload(issue: NodeFileIssue | None) -> dict[str, Any]:
    if issue is None:
        return {
            "file_issue_active": False,
            "file_issue_kind": "",
            "file_issue_message": "",
            "file_issue_source_kind": "",
            "file_issue_source_mode": "",
            "file_issue_request": "",
            "file_issue_supports_managed_repair": False,
            "file_issue_supports_external_repair": False,
        }
    return {
        "file_issue_active": True,
        "file_issue_kind": issue.issue_kind,
        "file_issue_message": issue.message,
        "file_issue_source_kind": issue.source_kind,
        "file_issue_source_mode": issue.source_mode,
        "file_issue_request": issue.repair_request,
        "file_issue_supports_managed_repair": issue.supports_managed_repair,
        "file_issue_supports_external_repair": issue.supports_external_repair,
    }


def collect_node_file_issues(
    *,
    node: Any,
    spec: Any,
    project_path: str | None,
    project_metadata: Mapping[str, Any] | None,
) -> dict[str, NodeFileIssue]:
    issues: dict[str, NodeFileIssue] = {}
    node_id = str(getattr(node, "node_id", "")).strip()
    node_type_id = str(getattr(node, "type_id", "")).strip()
    if not node_id or not node_type_id:
        return issues

    resolver = ProjectArtifactResolver(
        project_path=project_path,
        project_metadata=dict(project_metadata) if isinstance(project_metadata, Mapping) else None,
    )
    node_properties = getattr(node, "properties", {})
    for prop in getattr(spec, "properties", ()):
        property_key = str(getattr(prop, "key", "")).strip()
        if (
            node_type_id == "media.panel"
            and property_key == "source"
            and bool(getattr(node, "exposed_ports", {}).get("source", True))
        ):
            continue
        repair_modes = repair_modes_for_node_property(node_type_id, property_key)
        if not repair_modes:
            continue
        property_label = str(getattr(prop, "label", property_key)).strip() or property_key
        property_value = str(getattr(node_properties, "get", lambda *_args: "")(property_key, getattr(prop, "default", "")) or "").strip()
        if node_type_id == "media.panel" and property_key == "source":
            try:
                remote_scheme = urlsplit(property_value).scheme.casefold()
            except ValueError:
                remote_scheme = ""
            if remote_scheme in {"http", "https"} and is_supported_media_source_reference(
                property_value
            ):
                continue
        issue = resolve_node_file_issue(
            node_id=node_id,
            property_key=property_key,
            property_label=property_label,
            property_value=property_value,
            repair_modes=repair_modes,
            resolver=resolver,
        )
        if issue is not None:
            issues[property_key] = issue
    return issues


def collect_workspace_file_issue_map(
    *,
    workspace: Any,
    registry: Any,
    project_path: str | None,
    project_metadata: Mapping[str, Any] | None,
) -> dict[tuple[str, str], NodeFileIssue]:
    issue_map: dict[tuple[str, str], NodeFileIssue] = {}
    nodes = getattr(workspace, "nodes", {})
    for node in getattr(nodes, "values", lambda: [])():
        spec = registry.get_spec(node.type_id)
        for property_key, issue in collect_node_file_issues(
            node=node,
            spec=spec,
            project_path=project_path,
            project_metadata=project_metadata,
        ).items():
            issue_map[(str(node.node_id), property_key)] = issue
    return issue_map


def resolve_node_file_issue(
    *,
    node_id: str,
    property_key: str,
    property_label: str,
    property_value: str,
    repair_modes: tuple[str, ...],
    resolver: ProjectArtifactResolver,
) -> NodeFileIssue | None:
    normalized_value = str(property_value or "").strip()
    if not normalized_value:
        return None

    resolution = resolver.resolve(normalized_value)
    issue_kind, message = _issue_details_for_resolution(property_label=property_label, resolution=resolution)
    if not issue_kind:
        return None

    return NodeFileIssue(
        node_id=str(node_id),
        property_key=str(property_key),
        property_label=str(property_label),
        property_value=normalized_value,
        issue_kind=issue_kind,
        source_kind=str(resolution.kind),
        source_mode=source_mode_for_resolution_kind(resolution.kind),
        message=message,
        repair_modes=tuple(repair_modes),
    )


def _issue_details_for_resolution(
    *,
    property_label: str,
    resolution: ArtifactResolution,
) -> tuple[str, str]:
    label = str(property_label or "File").strip() or "File"
    source_kind = str(resolution.kind or "").strip().lower()
    path = resolution.absolute_path

    if source_kind == "unresolved":
        return "unresolved_path", f"{label} must be an absolute local file or a project-managed file reference."

    if source_kind in {"managed_missing", "managed"} and (path is None or not path.exists() or not path.is_file()):
        return "managed_missing", f"{label} points to a managed project file that is missing."

    if source_kind in {"staged_missing", "staged"} and (path is None or not path.exists() or not path.is_file()):
        return "staged_missing", f"{label} points to staged project data that is missing."

    if path is None:
        return "unresolved_path", f"{label} could not be resolved to a local file."

    if not path.exists():
        return "external_missing", f"{label} points to a file that no longer exists."

    if not path.is_file():
        return "not_a_file", f"{label} must point to a file."

    return "", ""


__all__ = [
    "EXTERNAL_LINK_MODE",
    "FILE_REPAIR_REQUEST_PREFIX",
    "FileRepairRequest",
    "MANAGED_COPY_MODE",
    "NodeFileIssue",
    "build_file_issue_payload",
    "collect_node_file_issues",
    "collect_workspace_file_issue_map",
    "decode_file_repair_request",
    "encode_file_repair_request",
    "preferred_repair_mode_for_value",
    "repair_modes_for_node_property",
    "resolve_node_file_issue",
    "source_mode_for_resolution_kind",
]
