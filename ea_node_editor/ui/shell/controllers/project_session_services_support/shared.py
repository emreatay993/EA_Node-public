from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.persistence.session_store import SessionAutosaveStore
from ea_node_editor.ui.shell.state import ShellProjectSessionState
from ea_node_editor.workspace.manager import WorkspaceManager


def normalize_project_path_value(path: str | Path | object) -> str:
    raw_path = str(path).strip()
    if not raw_path:
        return ""
    try:
        return str(Path(raw_path).expanduser().with_suffix(".cxproj"))
    except ValueError:
        return ""


def normalized_recent_project_paths_value(
    paths: Iterable[object],
    *,
    limit: int,
) -> list[str]:
    normalized_paths: list[str] = []
    seen_paths: set[str] = set()
    for path in paths:
        normalized_path = normalize_project_path_value(path)
        if not normalized_path or normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)
        normalized_paths.append(normalized_path)
        if len(normalized_paths) >= limit:
            break
    return normalized_paths


class _ProjectSessionHostProtocol(Protocol):
    def dialog_parent(self) -> object | None: ...


class _WorkspaceSessionProtocol(Protocol):
    def save_active_view_state(self) -> None: ...

    def refresh_workspace_tabs(self) -> None: ...

    def switch_workspace(self, workspace_id: str) -> None: ...


class _NodePropertyPathBrowserProtocol(Protocol):
    def browse_node_property_path(self, node_id: str, key: str, current_path: str) -> str: ...


class _RecentProjectsMenuProtocol(Protocol):
    def refresh_recent_projects_menu(self) -> None: ...


class _AutosaveRecoveryPromptProtocol(Protocol):
    def is_visible(self) -> bool: ...

    def prompt_recover_autosave(self, recovered_project: ProjectData | None = None): ...


class _ScriptEditorPanelProtocol(Protocol):
    @property
    def visible(self) -> bool: ...

    @property
    def floating(self) -> bool: ...

    @property
    def width(self) -> float: ...

    def set_floating(self, value: bool) -> None: ...

    def set_width(self, value: float) -> None: ...

    def set_visible(self, value: bool) -> None: ...

    def set_checked(self, value: bool) -> None: ...

    def set_node(self, node: Any) -> None: ...

    def focus_editor(self) -> None: ...


class _ViewerProjectLoaderProtocol(Protocol):
    def project_loaded(
        self,
        project: ProjectData,
        registry: Any,
        *,
        reseed_on_next_reset: bool = False,
    ) -> None: ...


class _ProjectFilesHostProtocol(Protocol):
    session_store: SessionAutosaveStore
    registry: Any
    model: GraphModel
    workspace_manager: WorkspaceManager
    scene: Any
    project_path: str


class _ProjectSessionLifecycleHostProtocol(Protocol):
    project_session_state: ShellProjectSessionState
    session_store: SessionAutosaveStore
    serializer: Any
    model: GraphModel
    project_meta_changed: Any
    project_path: str


class _ProjectDocumentIOHostProtocol(Protocol):
    app_preferences_controller: Any
    registry: Any
    model: GraphModel
    scene: Any
    viewer_host_service: Any
    workspace_manager: WorkspaceManager
    runtime_history: Any
    serializer: Any
    library_pane_reset_requested: Any
    node_library_changed: Any
    project_meta_changed: Any
    project_path: str


__all__ = [
    "_AutosaveRecoveryPromptProtocol",
    "_NodePropertyPathBrowserProtocol",
    "_ProjectDocumentIOHostProtocol",
    "_ProjectFilesHostProtocol",
    "_ProjectSessionHostProtocol",
    "_ProjectSessionLifecycleHostProtocol",
    "_RecentProjectsMenuProtocol",
    "_ScriptEditorPanelProtocol",
    "_ViewerProjectLoaderProtocol",
    "_WorkspaceSessionProtocol",
    "normalize_project_path_value",
    "normalized_recent_project_paths_value",
]
