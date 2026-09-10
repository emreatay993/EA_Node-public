from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from ea_node_editor.graph.ids import new_id
from ea_node_editor.graph.records import EdgeInstance, NodeInstance


@dataclass(slots=True)
class ViewState:
    view_id: str
    name: str
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    scope_path: list[str] = field(default_factory=list)
    hide_optional_ports: bool = False


@dataclass(eq=False)
class WorkspaceSnapshot:
    name: str
    nodes: dict[str, NodeInstance]
    edges: dict[str, EdgeInstance]
    views: dict[str, ViewState]
    active_view_id: str
    dirty: bool
    extra_state: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def capture(cls, workspace: "WorkspaceData") -> "WorkspaceSnapshot":
        return cls(
            name=str(workspace.name),
            nodes={node_id: node.clone() for node_id, node in workspace.nodes.items()},
            edges={edge_id: edge.clone() for edge_id, edge in workspace.edges.items()},
            views=copy.deepcopy(workspace.views),
            active_view_id=str(workspace.active_view_id),
            dirty=bool(workspace.dirty),
        )

    def restore(self, workspace: "WorkspaceData") -> None:
        workspace.name = str(self.name)
        workspace.nodes = {node_id: node.clone() for node_id, node in self.nodes.items()}
        workspace.edges = {edge_id: edge.clone() for edge_id, edge in self.edges.items()}
        workspace.views = copy.deepcopy(self.views)
        workspace.active_view_id = str(self.active_view_id)
        workspace.dirty = bool(self.dirty)
        workspace.ensure_default_view()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WorkspaceSnapshot):
            return NotImplemented
        return (
            self.name == other.name
            and self.nodes == other.nodes
            and self.edges == other.edges
            and self.views == other.views
            and self.active_view_id == other.active_view_id
            and self.dirty == other.dirty
            and self.extra_state == other.extra_state
        )


@dataclass
class WorkspaceData:
    workspace_id: str
    name: str
    nodes: dict[str, NodeInstance] = field(default_factory=dict)
    edges: dict[str, EdgeInstance] = field(default_factory=dict)
    views: dict[str, ViewState] = field(default_factory=dict)
    active_view_id: str = ""
    dirty: bool = False
    mutation_revision: int = field(default=0, compare=False, repr=False)

    def ensure_default_view(self) -> None:
        self.active_view_state()

    def active_view_state(self) -> ViewState:
        if not self.views:
            view = ViewState(view_id=new_id("view"), name="V1")
            self.views[view.view_id] = view
            self.active_view_id = view.view_id
            self.bump_mutation_revision()
            return view
        if not self.active_view_id or self.active_view_id not in self.views:
            self.active_view_id = next(iter(self.views))
            self.bump_mutation_revision()
        return self.views[self.active_view_id]

    def bump_mutation_revision(self) -> int:
        self.mutation_revision = int(getattr(self, "mutation_revision", 0) or 0) + 1
        return self.mutation_revision

    def document_epoch_part(self) -> tuple[Any, ...]:
        self.ensure_default_view()
        return (
            str(self.workspace_id),
            str(self.name),
            str(self.active_view_id),
            bool(self.dirty),
            int(getattr(self, "mutation_revision", 0) or 0),
            tuple(str(view_id) for view_id in self.views),
            len(self.nodes),
            len(self.edges),
        )

    def mark_dirty(self) -> None:
        self.dirty = True
        self.bump_mutation_revision()

    def capture_snapshot(self) -> WorkspaceSnapshot:
        return WorkspaceSnapshot.capture(self)

    def restore_snapshot(self, snapshot: WorkspaceSnapshot) -> None:
        snapshot.restore(self)
        self.bump_mutation_revision()

    def clone(self, new_workspace_id: str, name: str) -> "WorkspaceData":
        clone_nodes = {node_id: node.clone() for node_id, node in self.nodes.items()}
        clone_edges = {edge_id: edge.clone() for edge_id, edge in self.edges.items()}
        clone_views = copy.deepcopy(self.views)
        duplicate = WorkspaceData(
            workspace_id=new_workspace_id,
            name=name,
            nodes=clone_nodes,
            edges=clone_edges,
            views=clone_views,
            active_view_id=self.active_view_id,
            dirty=True,
        )
        duplicate.ensure_default_view()
        return duplicate

__all__ = ["ViewState", "WorkspaceData", "WorkspaceSnapshot"]
