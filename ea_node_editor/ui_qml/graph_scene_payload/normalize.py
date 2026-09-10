from __future__ import annotations

"""Pure payload normalization helpers (kind-agnostic and kind-specific inputs)."""


import copy
import json
import math
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from PyQt6.QtCore import QUrl

from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.nodes.builtins.web_viewer import (
    WEB_PAGE_VIEWER_SURFACE_FAMILY,
    WEB_PAGE_VIEWER_SURFACE_VARIANT,
    WEB_PAGE_VIEWER_TYPE_ID,
)
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
from ea_node_editor.ui.media_preview_provider import (
    LOCAL_MEDIA_PREVIEW_PROVIDER_ID,
)
from ea_node_editor.ui.port_availability import (
    edge_availability_warning,
)
from ea_node_editor.ui_qml.surface_contracts import (
    surface_spec_payload_for_node_type,
)
from ea_node_editor.web_host.navigation_policy import (
    decide_web_navigation,
    is_project_artifact_location,
)

if TYPE_CHECKING:
    pass


_PROJECT_ARTIFACT_REF_RE = re.compile(r"^(?:saved|temp)://[A-Za-z0-9][A-Za-z0-9._-]*$")
_WINDOWS_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
_UNC_PATH_RE = re.compile(r"^[/\\]{2}[^/\\]")
_IMAGE_FIT_MODES = frozenset({"contain", "cover", "original"})
WEB_PAGE_CONTENT_KIND = "web_page"
WEB_PAGE_SURFACE_FAMILY = WEB_PAGE_VIEWER_SURFACE_FAMILY
WEB_PAGE_SURFACE_VARIANT = WEB_PAGE_VIEWER_SURFACE_VARIANT
PLOT_CONTENT_KIND = "plot"


def _is_project_artifact_ref(value: str) -> bool:
    return bool(_PROJECT_ARTIFACT_REF_RE.match(value))


def _is_absolute_local_path(value: str) -> bool:
    return (
        bool(_WINDOWS_DRIVE_PATH_RE.match(value))
        or bool(_UNC_PATH_RE.match(value))
        or value.startswith("/")
    )


def _resolved_local_source_url(raw_value: object) -> str:
    source = str(raw_value or "").strip()
    if not source:
        return ""
    if _is_project_artifact_ref(source):
        return source
    if source.lower().startswith("file:"):
        url = QUrl(source.replace("\\", "/"))
        if url.isLocalFile():
            return url.toString()
        return ""
    if not _is_absolute_local_path(source):
        return ""
    return QUrl.fromLocalFile(source).toString()


def _resolved_local_file_source_url(
    raw_value: object,
    *,
    project_path: str | None = None,
    project_metadata: dict[str, Any] | None = None,
) -> str:
    source = str(raw_value or "").strip()
    if not source:
        return ""
    resolved_path = ProjectArtifactResolver(
        project_path=project_path,
        project_metadata=project_metadata,
    ).resolve_to_path(source)
    if resolved_path is None:
        return ""
    return QUrl.fromLocalFile(str(resolved_path)).toString()


def _resolved_web_page_navigation_location(
    raw_value: object,
    *,
    project_path: str | None = None,
    project_metadata: dict[str, Any] | None = None,
) -> str:
    source = str(raw_value or "").strip()
    if not source:
        return ""
    if not is_project_artifact_location(source):
        return source
    resolved_url = _resolved_local_file_source_url(
        source,
        project_path=project_path,
        project_metadata=project_metadata,
    )
    return resolved_url or source


def _image_preview_source_url(source_url: str) -> str:
    normalized = str(source_url or "").strip()
    if not normalized:
        return ""
    return f"image://{LOCAL_MEDIA_PREVIEW_PROVIDER_ID}/preview?source={quote(normalized, safe='')}"


def _float_property(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _normalized_crop_rect(properties: Mapping[str, Any]) -> dict[str, float]:
    left = _float_property(properties.get("crop_x"), 0.0)
    top = _float_property(properties.get("crop_y"), 0.0)
    width = _float_property(properties.get("crop_w"), 1.0)
    height = _float_property(properties.get("crop_h"), 1.0)
    if not all(math.isfinite(value) for value in (left, top, width, height)):
        return {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    if width <= 0.0 or height <= 0.0:
        return {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    left = max(0.0, min(left, 1.0))
    top = max(0.0, min(top, 1.0))
    right = max(left, min(left + width, 1.0))
    bottom = max(top, min(top + height, 1.0))
    if right <= left or bottom <= top:
        return {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    return {
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
    }


def _normalized_fit_mode(value: object) -> str:
    normalized = str(value or "contain").strip().lower()
    return normalized if normalized in _IMAGE_FIT_MODES else "contain"


def _normalized_image_rotation_degrees(value: object) -> int:
    degrees = _int_property(value, 0) % 360
    return degrees if degrees % 90 == 0 else 0


def _int_property(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _is_web_page_surface_spec(*, type_id: object = "", spec: NodeTypeSpec) -> bool:
    normalized_type_id = str(type_id or "").strip()
    family = str(getattr(spec, "surface_family", "") or "").strip()
    variant = str(getattr(spec, "surface_variant", "") or "").strip()
    return normalized_type_id == WEB_PAGE_VIEWER_TYPE_ID or (
        family == WEB_PAGE_SURFACE_FAMILY and variant == WEB_PAGE_SURFACE_VARIANT
    )


def _surface_spec_payload_for_node(
    *, type_id: object, spec: NodeTypeSpec
) -> dict[str, Any]:
    return surface_spec_payload_for_node_type(type_id=type_id, spec=spec)


def _bool_property(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _mapping_value(value: object) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _web_page_navigation_decision_payload(location: object) -> dict[str, Any]:
    text = str(location or "").strip()
    if not text:
        return {
            "allowed": False,
            "target_url": "",
            "reason": "Web navigation location must not be empty.",
            "original_location": "",
            "scheme": "",
            "origin": "",
            "is_local": False,
            "qwebchannel_allowed": False,
        }
    return decide_web_navigation(text).as_payload()


def _normalized_json_object(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return {}
        try:
            decoded = json.loads(normalized)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, dict):
            return copy.deepcopy(decoded)
    return {}


def _normalized_preview_ref(value: object) -> object:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return ""
        try:
            decoded = json.loads(normalized)
        except json.JSONDecodeError:
            return normalized
        return (
            copy.deepcopy(decoded) if isinstance(decoded, (dict, list)) else normalized
        )
    if isinstance(value, (list, tuple)):
        return copy.deepcopy(list(value))
    return copy.deepcopy(value) if value is not None else ""


def _is_standard_surface(spec: NodeTypeSpec) -> bool:
    family = str(spec.surface_family or "standard").strip() or "standard"
    return family == "standard"


def _uses_dynamic_title_band_surface(spec: NodeTypeSpec) -> bool:
    family = str(spec.surface_family or "standard").strip() or "standard"
    return family in {"standard", "viewer"}


def _annotate_edge_payload_availability(
    payload_item: dict[str, Any],
    *,
    workspace: WorkspaceData,
    edge: Any,
    workspace_nodes: Mapping[str, Any],
    node_specs: Mapping[str, NodeTypeSpec],
) -> None:
    source_node = workspace_nodes.get(edge.source_node_id)
    target_node = workspace_nodes.get(edge.target_node_id)
    source_spec = node_specs.get(edge.source_node_id)
    target_spec = node_specs.get(edge.target_node_id)
    if (
        source_node is None
        or target_node is None
        or source_spec is None
        or target_spec is None
    ):
        return
    reason = edge_availability_warning(
        workspace=workspace,
        edge=edge,
        source_node=source_node,
        source_spec=source_spec,
        target_node=target_node,
        target_spec=target_spec,
    )
    payload_item["availability_warning"] = bool(reason)
    payload_item["availability_reason"] = reason
