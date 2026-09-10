# Purpose: Direct project loading and workspace-selection boundary tests.
# Map: subsystems/execution.md

from __future__ import annotations

from pathlib import Path

import pytest

from ea_node_editor.execution.project_loader import load_project, select_workspace
from ea_node_editor.execution.runtime_requests import (
    ProjectLoadRequest,
    WorkspaceSelection,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.serializer import JsonProjectSerializer


def test_load_project_uses_supplied_registry_and_selects_workspace(
    tmp_path: Path,
) -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    project_path = tmp_path / "loader.cxproj"
    JsonProjectSerializer(registry).save(str(project_path), model.project)

    loaded = load_project(ProjectLoadRequest(project_path), registry=registry)
    selected = loaded.select_workspace(WorkspaceSelection(workspace.workspace_id))

    assert loaded.registry is registry
    assert loaded.project_path == project_path
    assert selected.workspace_id == workspace.workspace_id
    assert loaded.project.active_workspace_id == workspace.workspace_id


def test_select_workspace_defaults_and_missing_id_are_strict(tmp_path: Path) -> None:
    del tmp_path
    project = GraphModel().project
    assert select_workspace(project).workspace_id == project.active_workspace_id
    with pytest.raises(KeyError, match="Workspace not found: missing"):
        select_workspace(project, "missing")
