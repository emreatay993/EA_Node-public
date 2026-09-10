from __future__ import annotations

from dataclasses import dataclass

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import EdgeInstance, NodeCommentRecord, NodeInstance, NodeLinkRecord
from ea_node_editor.graph.workspace_state import WorkspaceData


@dataclass(slots=True)
class GraphRecordMutation:
    model: GraphModel
    workspace_id: str

    @property
    def workspace(self) -> WorkspaceData:
        return self.model.project.workspaces[self.workspace_id]

    def _add_node_record(
        self,
        *,
        type_id: str,
        title: str,
        x: float,
        y: float,
        properties: dict[str, object] | None = None,
        exposed_ports: dict[str, bool] | None = None,
        visual_style: dict[str, object] | None = None,
        parent_node_id: str | None = None,
    ) -> NodeInstance:
        node = self.model._add_node_record(
            self.workspace_id,
            type_id=type_id,
            title=title,
            x=float(x),
            y=float(y),
            properties=None if properties is None else dict(properties),
            exposed_ports=None if exposed_ports is None else dict(exposed_ports),
            visual_style=None if visual_style is None else dict(visual_style),
        )
        self._set_node_parent_record(node.node_id, parent_node_id)
        return node

    def _add_edge_record(
        self,
        *,
        source_node_id: str,
        source_port_key: str,
        target_node_id: str,
        target_port_key: str,
        enabled: bool = True,
        input_order: int | None = None,
        label: str = "",
        visual_style: dict[str, object] | None = None,
    ) -> EdgeInstance:
        return self.model._add_edge_record(
            self.workspace_id,
            source_node_id=source_node_id,
            source_port_key=source_port_key,
            target_node_id=target_node_id,
            target_port_key=target_port_key,
            enabled=enabled,
            input_order=input_order,
            label=label,
            visual_style=None if visual_style is None else dict(visual_style),
        )

    def _remove_edge_record(self, edge_id: str) -> None:
        self.model._remove_edge_record(self.workspace_id, edge_id)

    def _remove_node_record(self, node_id: str, *, incident_edge_ids: set[str] | None = None) -> None:
        self.model._remove_node_record(
            self.workspace_id,
            node_id,
            incident_edge_ids=incident_edge_ids,
        )

    def _set_node_parent_record(self, node_id: str, parent_node_id: str | None) -> bool:
        return self.model._set_node_parent_record(self.workspace_id, node_id, parent_node_id)

    def _set_node_fragment_state_record(
        self,
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
        self.model._set_node_fragment_state_record(
            self.workspace_id,
            node_id,
            collapsed=collapsed,
            expanded_settings_group_ids=expanded_settings_group_ids,
            locked=locked,
            port_modifiers=port_modifiers,
            principal_input_port_id=principal_input_port_id,
            custom_width=custom_width,
            custom_height=custom_height,
        )

    def remove_edge(self, edge_id: str) -> None:
        self._remove_edge_record(edge_id)

    def remove_node(self, node_id: str, *, incident_edge_ids: set[str] | None = None) -> None:
        self._remove_node_record(node_id, incident_edge_ids=incident_edge_ids)

    def set_node_collapsed(self, node_id: str, collapsed: bool) -> None:
        self.model._set_node_collapsed_record(self.workspace_id, node_id, collapsed)

    def set_node_expanded_settings_group_ids(self, node_id: str, group_ids: tuple[str, ...]) -> None:
        self.model._set_node_expanded_settings_group_ids_record(self.workspace_id, node_id, group_ids)

    def set_node_locked(self, node_id: str, locked: bool) -> None:
        self.model._set_node_locked_record(self.workspace_id, node_id, locked)

    def set_node_position(self, node_id: str, x: float, y: float) -> None:
        self.model._set_node_position_record(self.workspace_id, node_id, x, y)

    def set_node_geometry(
        self,
        node_id: str,
        x: float,
        y: float,
        width: float | None,
        height: float | None,
    ) -> None:
        self.model._set_node_geometry_record(self.workspace_id, node_id, x, y, width, height)

    def set_node_title(self, node_id: str, title: str) -> None:
        self.model._set_node_title_record(self.workspace_id, node_id, title)

    def set_node_visual_style(self, node_id: str, visual_style: dict[str, object] | None) -> None:
        self.model._set_node_visual_style_record(
            self.workspace_id,
            node_id,
            None if visual_style is None else dict(visual_style),
        )

    def upsert_node_link(
        self,
        node_id: str,
        *,
        link_id: str,
        kind: str,
        title: str,
        target: str,
        subtitle: str = "",
        target_workspace_id: str = "",
        target_node_id: str = "",
    ) -> NodeLinkRecord | None:
        return self.model._upsert_node_link_record(
            self.workspace_id,
            node_id,
            link_id=link_id,
            kind=kind,
            title=title,
            target=target,
            subtitle=subtitle,
            target_workspace_id=target_workspace_id,
            target_node_id=target_node_id,
        )

    def remove_node_link(self, node_id: str, link_id: str) -> bool:
        return self.model._remove_node_link_record(self.workspace_id, node_id, link_id)

    def move_node_link(self, node_id: str, link_id: str, offset: int) -> bool:
        return self.model._move_node_link_record(self.workspace_id, node_id, link_id, offset)

    def upsert_node_comment(
        self,
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
    ) -> NodeCommentRecord | None:
        return self.model._upsert_node_comment_record(
            self.workspace_id,
            node_id,
            comment_id=comment_id,
            body=body,
            author=author,
            created_at=created_at,
            updated_at=updated_at,
            resolved=resolved,
            unread=unread,
            pinned=pinned,
            parent_id=parent_id,
        )

    def remove_node_comment(self, node_id: str, comment_id: str) -> bool:
        return self.model._remove_node_comment_record(self.workspace_id, node_id, comment_id)

    def set_node_comment_resolved(self, node_id: str, comment_id: str, resolved: bool, updated_at: str = "") -> bool:
        return self.model._set_node_comment_resolved_record(
            self.workspace_id,
            node_id,
            comment_id,
            resolved,
            updated_at,
        )

    def set_node_comment_pinned(self, node_id: str, comment_id: str, pinned: bool) -> bool:
        return self.model._set_node_comment_pinned_record(self.workspace_id, node_id, comment_id, pinned)

    def resolve_all_node_comments(self, node_id: str, updated_at: str = "") -> bool:
        return self.model._resolve_all_node_comments_record(self.workspace_id, node_id, updated_at)

    def mark_node_comments_read(self, node_id: str) -> bool:
        return self.model._mark_node_comments_read_record(self.workspace_id, node_id)

    def set_edge_label(self, edge_id: str, label: str) -> None:
        self.model._set_edge_label_record(self.workspace_id, edge_id, label)

    def set_edge_visual_style(self, edge_id: str, visual_style: dict[str, object] | None) -> None:
        self.model._set_edge_visual_style_record(
            self.workspace_id,
            edge_id,
            None if visual_style is None else dict(visual_style),
        )

    def set_edge_enabled(self, edge_id: str, enabled: bool) -> None:
        self.model._set_edge_enabled_record(self.workspace_id, edge_id, enabled)

    def set_port_label(self, node_id: str, port_key: str, label: str) -> None:
        self.model._set_port_label_record(self.workspace_id, node_id, port_key, label)

    def set_port_modifiers(self, node_id: str, port_key: str, modifiers: tuple[str, ...] | list[str]) -> None:
        self.model._set_port_modifiers_record(self.workspace_id, node_id, port_key, modifiers)

    def set_principal_input_port(self, node_id: str, port_key: str | None) -> None:
        self.model._set_principal_input_port_record(self.workspace_id, node_id, port_key)


__all__ = ["GraphRecordMutation"]
