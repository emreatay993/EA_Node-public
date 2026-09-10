from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from ea_node_editor.graph.hierarchy import validate_parent_node_id
from ea_node_editor.graph.ids import new_id as _new_id
from ea_node_editor.graph.node_comments import normalize_node_comment_record
from ea_node_editor.graph.node_links import (
    node_link_targets_node,
    normalize_node_link_record,
)
from ea_node_editor.graph.project_state import ProjectData as _ProjectData
from ea_node_editor.graph.records import EdgeInstance as _EdgeInstance
from ea_node_editor.graph.records import NodeCommentRecord as _NodeCommentRecord
from ea_node_editor.graph.records import NodeInstance as _NodeInstance
from ea_node_editor.graph.records import NodeLinkRecord as _NodeLinkRecord
from ea_node_editor.graph.workspace_state import ViewState as _ViewState
from ea_node_editor.graph.workspace_state import WorkspaceData as _WorkspaceData
from ea_node_editor.runtime_contracts import DATA_TREE_MODIFIER_ORDER

if TYPE_CHECKING:
    from ea_node_editor.graph.boundary_adapters import GraphBoundaryAdapters
    from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
    from ea_node_editor.graph.workspace_view_ops import WorkspaceViewMutation
    from ea_node_editor.nodes.registry import NodeRegistry


class GraphModel:
    def __init__(
        self,
        project: _ProjectData | None = None,
    ) -> None:
        self.project = project or _ProjectData(project_id=_new_id("proj"), name="untitled")
        self.project.ensure_default_workspace()

    @property
    def active_workspace(self) -> _WorkspaceData:
        self.project.ensure_default_workspace()
        return self.project.workspaces[self.project.active_workspace_id]

    def validated_mutations(
        self,
        workspace_id: str,
        registry: "NodeRegistry",
        *,
        boundary_adapters: "GraphBoundaryAdapters | None" = None,
    ) -> "ValidatedGraphMutation":
        if workspace_id not in self.project.workspaces:
            raise KeyError(f"Unknown workspace: {workspace_id}")
        from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation

        mutation_kwargs: dict[str, Any] = {}
        if boundary_adapters is not None:
            mutation_kwargs["boundary_adapters"] = boundary_adapters
        return ValidatedGraphMutation(
            model=self,
            workspace_id=workspace_id,
            registry=registry,
            **mutation_kwargs,
        )

    def workspace_view_mutations(self, workspace_id: str) -> "WorkspaceViewMutation":
        from ea_node_editor.graph.workspace_view_ops import workspace_view_mutations

        return workspace_view_mutations(self, workspace_id)

    def _create_workspace_record(self, name: str | None = None) -> _WorkspaceData:
        index = len(self.project.workspaces) + 1
        workspace = _WorkspaceData(workspace_id=_new_id("ws"), name=name or f"Workspace {index}")
        workspace.ensure_default_view()
        self.project.workspaces[workspace.workspace_id] = workspace
        self.project.bump_project_document_revision()
        return workspace

    def create_workspace(self, name: str | None = None) -> _WorkspaceData:
        workspace = self._create_workspace_record(name=name)
        self._set_active_workspace_id(workspace.workspace_id)
        return workspace

    def _duplicate_workspace_record(self, workspace_id: str) -> _WorkspaceData:
        source = self.project.workspaces[workspace_id]
        duplicated = source.clone(new_workspace_id=_new_id("ws"), name=f"{source.name} Copy")
        self.project.workspaces[duplicated.workspace_id] = duplicated
        self.project.bump_project_document_revision()
        return duplicated

    def duplicate_workspace(self, workspace_id: str) -> _WorkspaceData:
        duplicated = self._duplicate_workspace_record(workspace_id)
        self._set_active_workspace_id(duplicated.workspace_id)
        return duplicated

    def _close_workspace_record(self, workspace_id: str) -> None:
        if workspace_id not in self.project.workspaces:
            return
        if len(self.project.workspaces) == 1:
            raise ValueError("Cannot close the last workspace")
        del self.project.workspaces[workspace_id]
        self.project.bump_project_document_revision()

    def close_workspace(self, workspace_id: str) -> None:
        was_active = self.project.active_workspace_id == workspace_id
        self._close_workspace_record(workspace_id)
        if was_active and self.project.workspaces:
            self._set_active_workspace_id(next(iter(self.project.workspaces)))

    def _rename_workspace_record(self, workspace_id: str, new_name: str) -> None:
        workspace = self.project.workspaces[workspace_id]
        normalized_name = str(new_name)
        if workspace.name == normalized_name:
            return
        workspace.name = normalized_name
        workspace.bump_mutation_revision()

    def rename_workspace(self, workspace_id: str, new_name: str) -> None:
        self._rename_workspace_record(workspace_id, new_name)

    def _set_active_workspace_id(self, workspace_id: str) -> None:
        if workspace_id not in self.project.workspaces:
            raise KeyError(f"Unknown workspace: {workspace_id}")
        if self.project.active_workspace_id == workspace_id:
            return
        self.project.active_workspace_id = workspace_id
        self.project.bump_project_document_revision()

    def set_active_workspace(self, workspace_id: str) -> None:
        self._set_active_workspace_id(workspace_id)

    def _create_view_record(
        self,
        workspace_id: str,
        name: str | None = None,
        *,
        source_view_id: str | None = None,
    ) -> _ViewState:
        workspace = self.project.workspaces[workspace_id]
        source_view = workspace.views.get(source_view_id) if source_view_id else None
        view = _ViewState(
            view_id=_new_id("view"),
            name=name or f"V{len(workspace.views) + 1}",
            zoom=source_view.zoom if source_view is not None else 1.0,
            pan_x=source_view.pan_x if source_view is not None else 0.0,
            pan_y=source_view.pan_y if source_view is not None else 0.0,
            scope_path=list(source_view.scope_path) if source_view is not None else [],
            hide_optional_ports=source_view.hide_optional_ports if source_view is not None else False,
        )
        workspace.views[view.view_id] = view
        workspace.active_view_id = view.view_id
        workspace.bump_mutation_revision()
        return view

    def create_view(
        self,
        workspace_id: str,
        name: str | None = None,
        *,
        source_view_id: str | None = None,
    ) -> _ViewState:
        return self.workspace_view_mutations(workspace_id).create_view(
            name=name,
            source_view_id=source_view_id,
        )

    def _set_active_view_record(self, workspace_id: str, view_id: str) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.ensure_default_view()
        if view_id not in workspace.views:
            raise KeyError(f"Unknown view: {view_id}")
        if workspace.active_view_id == view_id:
            return
        workspace.active_view_id = view_id
        workspace.bump_mutation_revision()

    def set_active_view(self, workspace_id: str, view_id: str) -> None:
        self.workspace_view_mutations(workspace_id).set_active_view(view_id)

    def _close_view_record(self, workspace_id: str, view_id: str) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.ensure_default_view()
        if view_id not in workspace.views:
            return
        if len(workspace.views) == 1:
            raise ValueError("Cannot close the last view")
        ordered_view_ids = list(workspace.views)
        close_index = ordered_view_ids.index(view_id)
        was_active = workspace.active_view_id == view_id
        del workspace.views[view_id]
        if was_active:
            remaining_view_ids = list(workspace.views)
            next_index = min(max(close_index, 0), len(remaining_view_ids) - 1)
            workspace.active_view_id = remaining_view_ids[next_index]
        workspace.bump_mutation_revision()

    def close_view(self, workspace_id: str, view_id: str) -> None:
        self.workspace_view_mutations(workspace_id).close_view(view_id)

    def _rename_view_record(self, workspace_id: str, view_id: str, new_name: str) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.ensure_default_view()
        if view_id not in workspace.views:
            raise KeyError(f"Unknown view: {view_id}")
        normalized_name = str(new_name)
        if workspace.views[view_id].name == normalized_name:
            return
        workspace.views[view_id].name = normalized_name
        workspace.bump_mutation_revision()

    def rename_view(self, workspace_id: str, view_id: str, new_name: str) -> None:
        self.workspace_view_mutations(workspace_id).rename_view(view_id, new_name)

    def _move_view_record(self, workspace_id: str, from_index: int, to_index: int) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.ensure_default_view()
        if len(workspace.views) < 2:
            return
        if from_index < 0 or from_index >= len(workspace.views):
            return
        to_index = max(0, min(to_index, len(workspace.views) - 1))
        if from_index == to_index:
            return
        ordered_views = list(workspace.views.items())
        moved_view_id, moved_view = ordered_views.pop(from_index)
        ordered_views.insert(to_index, (moved_view_id, moved_view))
        workspace.views = dict(ordered_views)
        workspace.bump_mutation_revision()

    def move_view(self, workspace_id: str, from_index: int, to_index: int) -> None:
        self.workspace_view_mutations(workspace_id).move_view(from_index, to_index)

    def _add_node_record(
        self,
        workspace_id: str,
        *,
        type_id: str = "",
        title: str = "",
        x: float = 0.0,
        y: float = 0.0,
        properties: dict[str, Any] | None = None,
        exposed_ports: dict[str, bool] | None = None,
        port_labels: dict[str, str] | None = None,
        visual_style: dict[str, Any] | None = None,
        links: list[_NodeLinkRecord] | None = None,
        comments: list[_NodeCommentRecord] | None = None,
        parent_node_id: str | None = None,
        collapsed: bool = False,
        expanded_settings_group_ids: tuple[str, ...] = (),
        port_modifiers: dict[str, tuple[str, ...]] | None = None,
        principal_input_port_id: str | None = None,
        custom_width: float | None = None,
        custom_height: float | None = None,
    ) -> _NodeInstance:
        workspace = self.project.workspaces[workspace_id]
        record = _NodeInstance(
            node_id=_new_id("node"),
            type_id=type_id,
            title=title,
            x=float(x),
            y=float(y),
            collapsed=bool(collapsed),
            expanded_settings_group_ids=tuple(expanded_settings_group_ids),
            properties=copy.deepcopy(properties or {}),
            exposed_ports=dict(exposed_ports or {}),
            port_labels={str(key): str(value) for key, value in dict(port_labels or {}).items()},
            port_modifiers=copy.deepcopy(port_modifiers or {}),
            principal_input_port_id=str(principal_input_port_id).strip() if principal_input_port_id else None,
            visual_style=copy.deepcopy(visual_style or {}),
            links=copy.deepcopy(list(links or [])),
            comments=copy.deepcopy(list(comments or [])),
            parent_node_id=str(parent_node_id).strip() if parent_node_id else None,
            custom_width=custom_width,
            custom_height=custom_height,
        )
        workspace.nodes[record.node_id] = record
        workspace.mark_dirty()
        return record

    def add_node(
        self,
        workspace_id: str,
        type_id: str,
        title: str,
        x: float,
        y: float,
        properties: dict[str, Any] | None = None,
        exposed_ports: dict[str, bool] | None = None,
        visual_style: dict[str, Any] | None = None,
    ) -> _NodeInstance:
        return self._add_node_record(
            workspace_id,
            type_id=type_id,
            title=title,
            x=x,
            y=y,
            properties=properties,
            exposed_ports=exposed_ports,
            visual_style=visual_style,
        )

    def _remove_node_record(
        self,
        workspace_id: str,
        node_id: str,
        *,
        incident_edge_ids: set[str] | None = None,
    ) -> None:
        workspace = self.project.workspaces[workspace_id]
        for source_node in workspace.nodes.values():
            if source_node.node_id == node_id:
                continue
            next_links = [
                record
                for record in source_node.links
                if not node_link_targets_node(
                    record,
                    source_workspace_id=workspace_id,
                    target_workspace_id=workspace_id,
                    target_node_id=node_id,
                )
            ]
            if len(next_links) != len(source_node.links):
                source_node.links = next_links
        if node_id in workspace.nodes:
            del workspace.nodes[node_id]
        if incident_edge_ids is None:
            for edge_id in list(workspace.edges):
                edge = workspace.edges[edge_id]
                if edge.source_node_id == node_id or edge.target_node_id == node_id:
                    del workspace.edges[edge_id]
        else:
            for edge_id in list(incident_edge_ids):
                edge = workspace.edges.get(edge_id)
                if edge is None:
                    continue
                if edge.source_node_id == node_id or edge.target_node_id == node_id:
                    del workspace.edges[edge_id]
        workspace.mark_dirty()

    def remove_node(self, workspace_id: str, node_id: str) -> None:
        self._remove_node_record(workspace_id, node_id)

    def _set_node_position_record(self, workspace_id: str, node_id: str, x: float, y: float) -> None:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        node.x = x
        node.y = y
        workspace.mark_dirty()

    def set_node_position(self, workspace_id: str, node_id: str, x: float, y: float) -> None:
        self._set_node_position_record(workspace_id, node_id, x, y)

    def _set_node_geometry_record(
        self,
        workspace_id: str,
        node_id: str,
        x: float,
        y: float,
        width: float | None,
        height: float | None,
    ) -> None:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        node.x = x
        node.y = y
        node.custom_width = width
        node.custom_height = height
        workspace.mark_dirty()

    def set_node_geometry(
        self,
        workspace_id: str,
        node_id: str,
        x: float,
        y: float,
        width: float | None,
        height: float | None,
    ) -> None:
        self._set_node_geometry_record(workspace_id, node_id, x, y, width, height)

    def _set_node_size_record(
        self,
        workspace_id: str,
        node_id: str,
        width: float | None,
        height: float | None,
    ) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.nodes[node_id].custom_width = width
        workspace.nodes[node_id].custom_height = height
        workspace.mark_dirty()

    def set_node_size(self, workspace_id: str, node_id: str, width: float | None, height: float | None) -> None:
        self._set_node_size_record(workspace_id, node_id, width, height)

    def _set_node_collapsed_record(self, workspace_id: str, node_id: str, collapsed: bool) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.nodes[node_id].collapsed = collapsed
        workspace.mark_dirty()

    def set_node_collapsed(self, workspace_id: str, node_id: str, collapsed: bool) -> None:
        self._set_node_collapsed_record(workspace_id, node_id, collapsed)

    def _set_node_expanded_settings_group_ids_record(
        self,
        workspace_id: str,
        node_id: str,
        group_ids: tuple[str, ...],
    ) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.nodes[node_id].expanded_settings_group_ids = tuple(group_ids)
        workspace.mark_dirty()

    def set_node_expanded_settings_group_ids(
        self,
        workspace_id: str,
        node_id: str,
        group_ids: tuple[str, ...],
    ) -> None:
        self._set_node_expanded_settings_group_ids_record(workspace_id, node_id, group_ids)

    def _set_node_locked_record(self, workspace_id: str, node_id: str, locked: bool) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.nodes[node_id].locked = bool(locked)
        workspace.mark_dirty()

    def set_node_locked(self, workspace_id: str, node_id: str, locked: bool) -> None:
        self._set_node_locked_record(workspace_id, node_id, locked)

    def _set_node_property_record(self, workspace_id: str, node_id: str, key: str, value: Any) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.nodes[node_id].properties[key] = value
        workspace.mark_dirty()

    def set_node_property(self, workspace_id: str, node_id: str, key: str, value: Any) -> None:
        self._set_node_property_record(workspace_id, node_id, key, value)

    def _set_node_title_record(self, workspace_id: str, node_id: str, title: str) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.nodes[node_id].title = title
        workspace.mark_dirty()

    def set_node_title(self, workspace_id: str, node_id: str, title: str) -> None:
        self._set_node_title_record(workspace_id, node_id, title)

    def _set_node_visual_style_record(
        self,
        workspace_id: str,
        node_id: str,
        visual_style: dict[str, Any] | None,
    ) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.nodes[node_id].visual_style = copy.deepcopy(visual_style or {})
        workspace.mark_dirty()

    def _upsert_node_link_record(
        self,
        workspace_id: str,
        node_id: str,
        *,
        link_id: str,
        kind: str,
        title: str,
        target: str,
        subtitle: str = "",
        target_workspace_id: str = "",
        target_node_id: str = "",
    ) -> _NodeLinkRecord | None:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        record = normalize_node_link_record(
            link_id=link_id,
            kind=kind,
            title=title,
            target=target,
            subtitle=subtitle,
            target_workspace_id=target_workspace_id,
            target_node_id=target_node_id,
            source_workspace_id=workspace_id,
        )
        if record is None:
            return None
        for index, existing in enumerate(node.links):
            if existing.link_id != record.link_id:
                continue
            if existing == record:
                return existing
            node.links[index] = record
            workspace.mark_dirty()
            return record
        node.links.append(record)
        workspace.mark_dirty()
        return record

    def _remove_node_link_record(self, workspace_id: str, node_id: str, link_id: str) -> bool:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        normalized_link_id = str(link_id or "").strip()
        if not normalized_link_id:
            return False
        next_links = [record for record in node.links if record.link_id != normalized_link_id]
        if len(next_links) == len(node.links):
            return False
        node.links = next_links
        workspace.mark_dirty()
        return True

    def _move_node_link_record(self, workspace_id: str, node_id: str, link_id: str, offset: int) -> bool:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        normalized_link_id = str(link_id or "").strip()
        if not normalized_link_id or not node.links:
            return False
        from_index = next(
            (index for index, record in enumerate(node.links) if record.link_id == normalized_link_id),
            -1,
        )
        if from_index < 0:
            return False
        to_index = max(0, min(len(node.links) - 1, from_index + int(offset)))
        if to_index == from_index:
            return False
        moved = node.links.pop(from_index)
        node.links.insert(to_index, moved)
        workspace.mark_dirty()
        return True

    def _upsert_node_comment_record(
        self,
        workspace_id: str,
        node_id: str,
        *,
        comment_id: str,
        body: str,
        author: str,
        created_at: str = "",
        updated_at: str = "",
        resolved: bool = False,
        unread: bool = True,
        pinned: bool = False,
        parent_id: str = "",
    ) -> _NodeCommentRecord | None:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        existing = next(
            (record for record in node.comments if record.comment_id == str(comment_id or "").strip()),
            None,
        )
        record = normalize_node_comment_record(
            comment_id=comment_id,
            body=body,
            author=author,
            created_at=created_at or (existing.created_at if existing else ""),
            updated_at=updated_at or (existing.updated_at if existing else ""),
            resolved=resolved,
            unread=unread,
            pinned=pinned,
            parent_id=parent_id,
        )
        if record is None:
            return None
        for index, current in enumerate(node.comments):
            if current.comment_id != record.comment_id:
                continue
            if current == record:
                return current
            node.comments[index] = record
            workspace.mark_dirty()
            return record
        node.comments.append(record)
        workspace.mark_dirty()
        return record

    def _remove_node_comment_record(self, workspace_id: str, node_id: str, comment_id: str) -> bool:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        normalized_comment_id = str(comment_id or "").strip()
        if not normalized_comment_id:
            return False
        remove_ids = {normalized_comment_id}
        changed = True
        while changed:
            changed = False
            for record in node.comments:
                if record.parent_id in remove_ids and record.comment_id not in remove_ids:
                    remove_ids.add(record.comment_id)
                    changed = True
        next_comments = [record for record in node.comments if record.comment_id not in remove_ids]
        if len(next_comments) == len(node.comments):
            return False
        node.comments = next_comments
        workspace.mark_dirty()
        return True

    def _set_node_comment_resolved_record(
        self,
        workspace_id: str,
        node_id: str,
        comment_id: str,
        resolved: bool,
        updated_at: str = "",
    ) -> bool:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        normalized_comment_id = str(comment_id or "").strip()
        for record in node.comments:
            if record.comment_id != normalized_comment_id:
                continue
            normalized_updated_at = str(updated_at or record.updated_at or record.created_at)
            if record.resolved == bool(resolved) and record.updated_at == normalized_updated_at:
                return False
            record.resolved = bool(resolved)
            record.updated_at = normalized_updated_at
            workspace.mark_dirty()
            return True
        return False

    def _set_node_comment_pinned_record(self, workspace_id: str, node_id: str, comment_id: str, pinned: bool) -> bool:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        normalized_comment_id = str(comment_id or "").strip()
        for record in node.comments:
            if record.comment_id != normalized_comment_id:
                continue
            if record.pinned == bool(pinned):
                return False
            record.pinned = bool(pinned)
            workspace.mark_dirty()
            return True
        return False

    def _resolve_all_node_comments_record(self, workspace_id: str, node_id: str, updated_at: str = "") -> bool:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        changed = False
        for record in node.comments:
            if record.resolved:
                continue
            record.resolved = True
            record.updated_at = str(updated_at or record.updated_at or record.created_at)
            changed = True
        if changed:
            workspace.mark_dirty()
        return changed

    def _mark_node_comments_read_record(self, workspace_id: str, node_id: str) -> bool:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        changed = False
        for record in node.comments:
            if not record.unread:
                continue
            record.unread = False
            changed = True
        if changed:
            workspace.mark_dirty()
        return changed

    def _set_exposed_port_record(self, workspace_id: str, node_id: str, key: str, exposed: bool) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.nodes[node_id].exposed_ports[key] = exposed
        workspace.mark_dirty()

    def set_exposed_port(self, workspace_id: str, node_id: str, key: str, exposed: bool) -> None:
        self._set_exposed_port_record(workspace_id, node_id, key, exposed)

    def _set_node_parent_record(self, workspace_id: str, node_id: str, parent_node_id: str | None) -> bool:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        normalized_parent_id = validate_parent_node_id(workspace, node_id, parent_node_id)
        if node.parent_node_id == normalized_parent_id:
            return False
        node.parent_node_id = normalized_parent_id
        workspace.mark_dirty()
        return True

    def _set_port_label_record(self, workspace_id: str, node_id: str, port_key: str, label: str) -> None:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        if label:
            node.port_labels[port_key] = label
        else:
            node.port_labels.pop(port_key, None)
        workspace.mark_dirty()

    def set_port_label(self, workspace_id: str, node_id: str, port_key: str, label: str) -> None:
        self._set_port_label_record(workspace_id, node_id, port_key, label)

    def _set_port_modifiers_record(
        self,
        workspace_id: str,
        node_id: str,
        port_key: str,
        modifiers: tuple[str, ...] | list[str],
    ) -> None:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        requested = {str(modifier).strip().lower() for modifier in modifiers}
        unsupported = requested.difference(DATA_TREE_MODIFIER_ORDER)
        if unsupported:
            raise ValueError(f"Unsupported DataTree modifier: {', '.join(sorted(unsupported))}")
        normalized_key = str(port_key).strip()
        normalized = tuple(modifier for modifier in DATA_TREE_MODIFIER_ORDER if modifier in requested)
        if tuple(node.port_modifiers.get(normalized_key, ())) == normalized:
            return
        if normalized:
            node.port_modifiers[normalized_key] = normalized
        else:
            node.port_modifiers.pop(normalized_key, None)
        workspace.mark_dirty()

    def _set_principal_input_port_record(
        self,
        workspace_id: str,
        node_id: str,
        port_key: str | None,
    ) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.nodes[node_id].principal_input_port_id = str(port_key).strip() if port_key else None
        workspace.mark_dirty()

    def _add_edge_record(
        self,
        workspace_id: str,
        *,
        source_node_id: str = "",
        source_port_key: str = "",
        target_node_id: str = "",
        target_port_key: str = "",
        enabled: bool = True,
        input_order: int | None = None,
        label: str = "",
        visual_style: dict[str, Any] | None = None,
    ) -> _EdgeInstance:
        workspace = self.project.workspaces[workspace_id]
        if source_node_id not in workspace.nodes:
            raise KeyError(f"Unknown source node: {source_node_id}")
        if target_node_id not in workspace.nodes:
            raise KeyError(f"Unknown target node: {target_node_id}")
        for existing in workspace.edges.values():
            if (
                existing.source_node_id == source_node_id
                and existing.source_port_key == source_port_key
                and existing.target_node_id == target_node_id
                and existing.target_port_key == target_port_key
            ):
                return existing
        record = _EdgeInstance(
            edge_id=_new_id("edge"),
            source_node_id=source_node_id,
            source_port_key=source_port_key,
            target_node_id=target_node_id,
            target_port_key=target_port_key,
            enabled=bool(enabled),
            input_order=(
                max(0, int(input_order))
                if input_order is not None
                else 1
                + max(
                    (
                        edge.input_order
                        for edge in workspace.edges.values()
                        if edge.target_node_id == target_node_id and edge.target_port_key == target_port_key
                    ),
                    default=-1,
                )
            ),
            label=str(label),
            visual_style=copy.deepcopy(visual_style or {}),
        )
        workspace.edges[record.edge_id] = record
        workspace.mark_dirty()
        return record

    def add_edge(
        self,
        workspace_id: str,
        source_node_id: str,
        source_port_key: str,
        target_node_id: str,
        target_port_key: str,
        label: str = "",
        visual_style: dict[str, Any] | None = None,
    ) -> _EdgeInstance:
        return self._add_edge_record(
            workspace_id,
            source_node_id=source_node_id,
            source_port_key=source_port_key,
            target_node_id=target_node_id,
            target_port_key=target_port_key,
            label=label,
            visual_style=visual_style,
        )

    def _move_edge_endpoint_record(
        self,
        workspace_id: str,
        edge_id: str,
        *,
        source_node_id: str,
        source_port_key: str,
        target_node_id: str,
        target_port_key: str,
        input_order: int,
    ) -> None:
        workspace = self.project.workspaces[workspace_id]
        edge = workspace.edges[edge_id]
        edge.source_node_id = str(source_node_id)
        edge.source_port_key = str(source_port_key)
        edge.target_node_id = str(target_node_id)
        edge.target_port_key = str(target_port_key)
        edge.input_order = max(0, int(input_order))
        workspace.mark_dirty()

    def _set_edge_label_record(self, workspace_id: str, edge_id: str, label: str) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.edges[edge_id].label = str(label)
        workspace.mark_dirty()

    def set_edge_label(self, workspace_id: str, edge_id: str, label: str) -> None:
        self._set_edge_label_record(workspace_id, edge_id, label)

    def _set_edge_visual_style_record(
        self,
        workspace_id: str,
        edge_id: str,
        visual_style: dict[str, Any] | None,
    ) -> None:
        workspace = self.project.workspaces[workspace_id]
        workspace.edges[edge_id].visual_style = copy.deepcopy(visual_style or {})
        workspace.mark_dirty()

    def _set_edge_enabled_record(self, workspace_id: str, edge_id: str, enabled: bool) -> None:
        workspace = self.project.workspaces[workspace_id]
        edge = workspace.edges[edge_id]
        normalized = bool(enabled)
        if edge.enabled == normalized:
            return
        edge.enabled = normalized
        workspace.mark_dirty()

    def set_edge_visual_style(self, workspace_id: str, edge_id: str, visual_style: dict[str, Any] | None) -> None:
        self._set_edge_visual_style_record(workspace_id, edge_id, visual_style)

    def _remove_edge_record(self, workspace_id: str, edge_id: str) -> None:
        workspace = self.project.workspaces[workspace_id]
        if edge_id in workspace.edges:
            del workspace.edges[edge_id]
            workspace.mark_dirty()

    def remove_edge(self, workspace_id: str, edge_id: str) -> None:
        self._remove_edge_record(workspace_id, edge_id)

    def _set_node_fragment_state_record(
        self,
        workspace_id: str,
        node_id: str,
        *,
        collapsed: bool,
        expanded_settings_group_ids: tuple[str, ...],
        locked: bool,
        port_modifiers: dict[str, tuple[str, ...]],
        principal_input_port_id: str | None,
        custom_width: float | None,
        custom_height: float | None,
    ) -> None:
        workspace = self.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        node.collapsed = bool(collapsed)
        node.expanded_settings_group_ids = tuple(expanded_settings_group_ids)
        node.locked = bool(locked)
        node.port_modifiers = copy.deepcopy(port_modifiers)
        node.principal_input_port_id = principal_input_port_id
        node.custom_width = custom_width
        node.custom_height = custom_height
        workspace.mark_dirty()


__all__ = ["GraphModel"]
