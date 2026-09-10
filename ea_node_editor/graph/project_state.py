from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ea_node_editor.graph.ids import new_id
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.settings import SCHEMA_VERSION


@dataclass(slots=True)
class ProjectData:
    project_id: str
    name: str
    schema_version: int = SCHEMA_VERSION
    active_workspace_id: str = ""
    workspaces: dict[str, WorkspaceData] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    project_document_revision: int = field(default=0, compare=False, repr=False)
    migration_report: tuple[str, ...] = field(default=(), compare=False, repr=False)
    migration_source_schema_version: int | None = field(default=None, compare=False, repr=False)

    def ensure_default_workspace(self) -> WorkspaceData:
        if not self.workspaces:
            workspace = WorkspaceData(workspace_id=new_id("ws"), name="Workspace 1")
            workspace.ensure_default_view()
            self.workspaces[workspace.workspace_id] = workspace
            self.active_workspace_id = workspace.workspace_id
            self.bump_project_document_revision()
        elif not self.active_workspace_id or self.active_workspace_id not in self.workspaces:
            self.active_workspace_id = next(iter(self.workspaces))
            self.bump_project_document_revision()
        return self.workspaces[self.active_workspace_id]

    def bump_project_document_revision(self) -> int:
        self.project_document_revision = int(getattr(self, "project_document_revision", 0) or 0) + 1
        return self.project_document_revision

    def replace_metadata(self, metadata: Mapping[str, Any] | None) -> bool:
        normalized_metadata = copy.deepcopy(dict(metadata)) if isinstance(metadata, Mapping) else {}
        if self.metadata == normalized_metadata and isinstance(self.metadata, dict):
            return False
        self.metadata = normalized_metadata
        self.bump_project_document_revision()
        return True

    def touch_metadata(self) -> int:
        return self.bump_project_document_revision()

    def document_epoch(self) -> tuple[Any, ...]:
        self.ensure_default_workspace()
        return (
            int(getattr(self, "project_document_revision", 0) or 0),
            int(self.schema_version),
            str(self.project_id),
            str(self.name),
            str(self.active_workspace_id),
            tuple(
                workspace.document_epoch_part()
                for workspace in self.workspaces.values()
            ),
        )


__all__ = ["ProjectData"]
