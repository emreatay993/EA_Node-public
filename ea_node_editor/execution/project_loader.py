# Purpose: Load and select project workspaces at the sole headless persistence composition boundary.
# Map: subsystems/execution.md
# Tests: tests/test_project_loader.py
# Landmarks: load_project; select_workspace; LoadedProject
"""Qt-free Corex runtime API and CLI entry point."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ea_node_editor.execution.runtime_requests import (
    ProjectLoadRequest,
    WorkspaceSelection,
)
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.persistence.serializer import JsonProjectSerializer


@dataclass(frozen=True, slots=True)
class LoadedProject:
    project_path: Path
    project: ProjectData
    registry: NodeRegistry

    def select_workspace(
        self, selection: "WorkspaceSelection | str | None" = None
    ) -> WorkspaceData:
        return select_workspace(self, selection)


def load_project(
    request: ProjectLoadRequest | str | Path,
    *,
    registry: NodeRegistry | None = None,
    extra_plugin_dirs: Sequence[Path] | None = None,
) -> LoadedProject:
    if isinstance(request, ProjectLoadRequest):
        load_request = request
    else:
        load_request = ProjectLoadRequest(
            project_path=request,
            extra_plugin_dirs=tuple(extra_plugin_dirs or ()),
        )
    runtime_registry = registry or build_default_registry(
        extra_plugin_dirs=list(load_request.extra_plugin_dirs)
    )
    project_path = load_request.normalized_path()
    project = JsonProjectSerializer(runtime_registry).load(str(project_path))
    return LoadedProject(
        project_path=project_path,
        project=project,
        registry=runtime_registry,
    )


def select_workspace(
    project: LoadedProject | ProjectData,
    selection: WorkspaceSelection | str | None = None,
) -> WorkspaceData:
    project_data = project.project if isinstance(project, LoadedProject) else project
    if isinstance(selection, WorkspaceSelection):
        requested_workspace_id = str(selection.workspace_id or "").strip()
    else:
        requested_workspace_id = str(selection or "").strip()

    if not requested_workspace_id:
        return project_data.ensure_default_workspace()

    try:
        workspace = project_data.workspaces[requested_workspace_id]
    except KeyError as exc:
        raise KeyError(f"Workspace not found: {requested_workspace_id}") from exc
    project_data.active_workspace_id = requested_workspace_id
    return workspace
