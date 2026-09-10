from __future__ import annotations

from typing import Any, Callable


class MutationUiEffects:
    """Shell-owned UI aftermath for graph mutations.

    Graph-scene publishers still own model payload rebuilds and delta emission.
    This class keeps the shell refresh work explicit per action.
    """

    def __init__(
        self,
        *,
        host: Any,
        refresh_workspace_tabs: Callable[[], None],
    ) -> None:
        self._host = host
        self._refresh_workspace_tabs = refresh_workspace_tabs

    def notify_selected_node_changed(self) -> None:
        signal = getattr(self._host, "selected_node_changed", None)
        emit = getattr(signal, "emit", None)
        if callable(emit):
            emit()

    def refresh_workspace_tabs(self) -> None:
        self._refresh_workspace_tabs()

    def refresh_scene_from_model(self, workspace_id: str) -> None:
        scene = getattr(self._host, "scene", None)
        refresh = getattr(scene, "refresh_workspace_from_model", None)
        if callable(refresh):
            refresh(str(workspace_id))

    def show_graph_hint(self, message: str, timeout_ms: int = 3600) -> None:
        show_hint = getattr(self._host, "show_graph_hint", None)
        if callable(show_hint):
            show_hint(str(message), int(timeout_ms))

    def sync_script_editor_node(self, node_id: str, *, workspace: Any | None = None) -> None:
        script_editor = getattr(self._host, "script_editor", None)
        if script_editor is None:
            return
        if str(getattr(script_editor, "current_node_id", "") or "") != str(node_id):
            return
        resolved_workspace = workspace if workspace is not None else self._active_workspace()
        if resolved_workspace is None:
            return
        nodes = getattr(resolved_workspace, "nodes", {})
        set_node = getattr(script_editor, "set_node", None)
        if callable(set_node):
            set_node(nodes.get(str(node_id)))

    def after_subnode_pin_added(self) -> None:
        self._selected_node_and_workspace_tabs()

    def after_subnode_pin_removed(self) -> None:
        self._selected_node_and_workspace_tabs()

    def after_selected_port_label_changed(self) -> None:
        self._selected_node_and_workspace_tabs()

    def after_selected_node_property_changed(
        self,
        node_id: str,
        key: str,
        value: Any = None,
        *,
        workspace: Any | None,
        refresh_scene_payload: bool,
    ) -> None:
        if refresh_scene_payload and workspace is not None:
            self.refresh_scene_from_model(str(workspace.workspace_id))
        if str(key) == "script":
            self.sync_script_editor_node(str(node_id), workspace=workspace)
        self.sync_viewer_session_node_property(str(node_id), str(key), value, workspace=workspace)
        self._selected_node_and_workspace_tabs()

    def sync_viewer_session_node_property(
        self,
        node_id: str,
        key: str,
        value: Any,
        *,
        workspace: Any | None,
    ) -> None:
        workspace_id = str(getattr(workspace, "workspace_id", "") or "").strip()
        if not workspace_id:
            return
        viewer_session_bridge = getattr(self._host, "viewer_session_bridge", None)
        sync_node_property_option = getattr(viewer_session_bridge, "sync_node_property_option", None)
        if callable(sync_node_property_option):
            sync_node_property_option(
                str(node_id),
                str(key),
                value,
                {"workspace_id": workspace_id},
            )

    def after_selected_port_exposure_changed(self) -> None:
        self._selected_node_and_workspace_tabs()

    def after_selected_node_collapse_changed(self) -> None:
        self._selected_node_and_workspace_tabs()

    def after_ports_connected(self) -> None:
        self.refresh_workspace_tabs()

    def after_fragment_duplicated(self) -> None:
        self._selected_node_and_workspace_tabs()

    def after_group_backdrop_wrapped(self) -> None:
        self._selected_node_and_workspace_tabs()

    def after_grouping_changed(self) -> None:
        self._selected_node_and_workspace_tabs()

    def after_layout_action(
        self,
        *,
        created_overlap_pairs: int,
        normalized_action: str | None,
    ) -> None:
        self._show_layout_overlap_hint(
            created_overlap_pairs=created_overlap_pairs,
            normalized_action=normalized_action,
        )
        self._selected_node_and_workspace_tabs()

    def after_connections_straightened(self) -> None:
        self._selected_node_and_workspace_tabs()

    def after_fragment_pasted(self) -> None:
        self._selected_node_and_workspace_tabs()

    def after_history_replayed(self, workspace_id: str, entry: object) -> None:
        self.refresh_scene_from_model(workspace_id)
        script_editor = getattr(self._host, "script_editor", None)
        if script_editor is not None:
            self.sync_script_editor_node(str(getattr(script_editor, "current_node_id", "")))
        self.invalidate_solution_for_history_entry(workspace_id, entry)
        self.refresh_workspace_tabs()

    def after_connected_ports_request(self) -> None:
        self.refresh_workspace_tabs()

    def after_edge_removed(self) -> None:
        self.refresh_workspace_tabs()

    def after_node_removed(self) -> None:
        self._selected_node_and_workspace_tabs()

    def after_node_renamed(self) -> None:
        self._selected_node_and_workspace_tabs()

    def after_selected_graph_items_deleted(self) -> None:
        self._selected_node_and_workspace_tabs()

    def invalidate_solution_for_history_entry(
        self,
        workspace_id: str,
        entry: object,
    ) -> None:
        hook = getattr(self._host, "invalidate_solution_for_history_action", None)
        if not callable(hook):
            return
        hook(
            workspace_id,
            getattr(entry, "action_type", ""),
            before_snapshot=getattr(entry, "before", None),
            after_snapshot=getattr(entry, "after", None),
        )

    def _selected_node_and_workspace_tabs(self) -> None:
        self.notify_selected_node_changed()
        self.refresh_workspace_tabs()

    def _show_layout_overlap_hint(
        self,
        *,
        created_overlap_pairs: int,
        normalized_action: str | None,
    ) -> None:
        if normalized_action is None or created_overlap_pairs <= 0:
            return
        tidy_action = "Distribute Vertically" if normalized_action in {"left", "right"} else "Distribute Horizontally"
        overlap_word = "overlap" if created_overlap_pairs == 1 else "overlaps"
        self.show_graph_hint(
            f"{created_overlap_pairs} {overlap_word} created. Press {tidy_action} to tidy."
        )

    def _active_workspace(self) -> Any | None:
        model = getattr(self._host, "model", None)
        project = getattr(model, "project", None)
        workspaces = getattr(project, "workspaces", None)
        workspace_manager = getattr(self._host, "workspace_manager", None)
        active_workspace_id = ""
        if workspace_manager is not None:
            active_workspace_id_fn = getattr(workspace_manager, "active_workspace_id", None)
            if callable(active_workspace_id_fn):
                active_workspace_id = str(active_workspace_id_fn() or "").strip()
        if not active_workspace_id:
            active_workspace_id = str(getattr(self._host, "active_workspace_id", "") or "").strip()
        if not active_workspace_id or not isinstance(workspaces, dict):
            return None
        return workspaces.get(active_workspace_id)


__all__ = ["MutationUiEffects"]
