from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import pyqtSlot

from ea_node_editor.ui.media_preview_provider import (
    describe_local_image as build_image_preview_description,
)
from ea_node_editor.ui.mail_preview_provider import (
    describe_mail_preview as build_mail_preview_description,
)
from ea_node_editor.ui.pdf_preview_provider import (
    describe_pdf_preview as build_pdf_preview_description,
)
from ea_node_editor.ui.shell.graph_action_contracts import GraphActionId

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


class ShellWindowWorkspaceGraphActionsMixin:
    # Current QML-facing graph action slots stay public; controller dispatch is canonical.
    @pyqtSlot(result=bool)
    def request_navigate_scope_parent(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.NAVIGATE_SCOPE_PARENT.value))

    @pyqtSlot(result=bool)
    def request_navigate_scope_root(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.NAVIGATE_SCOPE_ROOT.value))

    @pyqtSlot(result=bool)
    def request_align_selection_left(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.ALIGN_SELECTION_LEFT.value))

    @pyqtSlot(result=bool)
    def request_align_selection_right(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.ALIGN_SELECTION_RIGHT.value))

    @pyqtSlot(result=bool)
    def request_align_selection_top(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.ALIGN_SELECTION_TOP.value))

    @pyqtSlot(result=bool)
    def request_align_selection_bottom(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.ALIGN_SELECTION_BOTTOM.value))

    @pyqtSlot(result=bool)
    def request_distribute_selection_horizontally(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.DISTRIBUTE_SELECTION_HORIZONTALLY.value))

    @pyqtSlot(result=bool)
    def request_distribute_selection_vertically(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.DISTRIBUTE_SELECTION_VERTICALLY.value))

    @pyqtSlot(result=bool)
    def request_straighten_selection_connections(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.STRAIGHTEN_SELECTION_CONNECTIONS.value))

    @pyqtSlot()
    def request_connect_selected_nodes(self: "ShellWindow") -> None:
        self.graph_action_controller.trigger(GraphActionId.CONNECT_SELECTED.value)

    @pyqtSlot(result=bool)
    def request_duplicate_selected_nodes(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.DUPLICATE_SELECTION.value))

    @pyqtSlot(result=bool)
    def request_wrap_selected_nodes_in_group_backdrop(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.WRAP_SELECTION_IN_GROUP_BACKDROP.value))

    @pyqtSlot(result=bool)
    def request_group_selected_nodes(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.GROUP_SELECTION.value))

    @pyqtSlot(result=bool)
    def request_ungroup_selected_nodes(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.UNGROUP_SELECTION.value))

    @pyqtSlot(result=bool)
    def request_copy_selected_nodes(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.COPY_SELECTION.value))

    @pyqtSlot(result=bool)
    def request_cut_selected_nodes(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.CUT_SELECTION.value))

    @pyqtSlot(result=bool)
    def request_paste_selected_nodes(self: "ShellWindow") -> bool:
        return bool(self.graph_action_controller.trigger(GraphActionId.PASTE_SELECTION.value))

    @pyqtSlot("QVariantList", result=bool)
    def request_delete_selected_graph_items(self: "ShellWindow", edge_ids: list[Any]) -> bool:
        return bool(
            self.graph_action_controller.trigger(
                GraphActionId.DELETE_SELECTION.value,
                {"edge_ids": edge_ids},
            )
        )

    @pyqtSlot()
    def request_create_workspace(self: "ShellWindow") -> None:
        self.shell_workspace_presenter.request_create_workspace()

    @pyqtSlot()
    def request_create_view(self: "ShellWindow") -> None:
        self.shell_workspace_presenter.request_create_view()

    @pyqtSlot(str)
    def request_switch_view(self: "ShellWindow", view_id: str) -> None:
        self.shell_workspace_presenter.request_switch_view(view_id)

    @pyqtSlot(str, result=bool)
    def request_open_subnode_scope(self: "ShellWindow", node_id: str) -> bool:
        normalized_node_id = str(node_id or "").strip()
        return bool(
            normalized_node_id
            and self.search_scope_controller.navigate_scope(
                lambda: self.scene.open_subnode_scope(normalized_node_id)
            )
        )

    @pyqtSlot(str, result=bool)
    def request_open_scope_breadcrumb(self: "ShellWindow", node_id: str) -> bool:
        return bool(self.shell_workspace_presenter.request_open_scope_breadcrumb(node_id))

    @pyqtSlot()
    def request_rename_workspace(self: "ShellWindow") -> None:
        self.workspace_navigation_controller.rename_active_workspace()

    @pyqtSlot(str, result=bool)
    def request_rename_workspace_by_id(self: "ShellWindow", workspace_id: str) -> bool:
        return bool(self.shell_workspace_presenter.request_rename_workspace_by_id(workspace_id))

    @pyqtSlot()
    def request_duplicate_workspace(self: "ShellWindow") -> None:
        self.workspace_navigation_controller.duplicate_active_workspace()

    @pyqtSlot()
    def request_close_workspace(self: "ShellWindow") -> None:
        self.workspace_navigation_controller.close_active_workspace()

    @pyqtSlot(str, result=bool)
    def request_close_workspace_by_id(self: "ShellWindow", workspace_id: str) -> bool:
        return bool(self.shell_workspace_presenter.request_close_workspace_by_id(workspace_id))

    @pyqtSlot(str, result=bool)
    def request_close_view(self: "ShellWindow", view_id: str) -> bool:
        return bool(self.shell_workspace_presenter.request_close_view(view_id))

    @pyqtSlot(str, result=bool)
    def request_rename_view(self: "ShellWindow", view_id: str) -> bool:
        return bool(self.shell_workspace_presenter.request_rename_view(view_id))

    def _export_canvas_views(self: "ShellWindow") -> bool:
        return bool(self.canvas_export_presenter.export_canvas_views())

    def _export_project_review_deck(self: "ShellWindow") -> bool:
        return bool(self.project_review_deck_presenter.export_project_review_deck())

    @pyqtSlot(int, int, result=bool)
    def request_move_workspace_tab(self: "ShellWindow", from_index: int, to_index: int) -> bool:
        return bool(self.shell_workspace_presenter.request_move_workspace_tab(from_index, to_index))

    @pyqtSlot(int, int, result=bool)
    def request_move_view_tab(self: "ShellWindow", from_index: int, to_index: int) -> bool:
        return bool(self.shell_workspace_presenter.request_move_view_tab(from_index, to_index))

    @pyqtSlot(result=bool)
    def request_undo(self: "ShellWindow") -> bool:
        return bool(self.workspace_edit_controller.undo())

    @pyqtSlot(result=bool)
    def request_redo(self: "ShellWindow") -> bool:
        return bool(self.workspace_edit_controller.redo())

    @pyqtSlot(str, str, str, str, bool, result=bool)
    def request_connect_ports(
        self: "ShellWindow",
        node_a_id: str,
        port_a: str,
        node_b_id: str,
        port_b: str,
        append_requested: bool = False,
    ) -> bool:
        result = self.workspace_edit_controller.request_connect_ports(
            node_a_id,
            port_a,
            node_b_id,
            port_b,
            append_requested,
        )
        if not result.payload and str(result.message or "").strip():
            self.show_graph_hint(str(result.message), 2400)
        return bool(result.payload)

    @pyqtSlot("QVariantList", str, str, str, bool, bool, result=bool)
    def request_rewire_edges(
        self: "ShellWindow",
        edge_ids: list[Any],
        endpoint: str,
        node_id: str,
        port_key: str,
        copy_requested: bool = False,
        append_requested: bool = False,
    ) -> bool:
        result = self.workspace_edit_controller.request_rewire_edges(
            edge_ids,
            endpoint,
            node_id,
            port_key,
            copy_requested,
            append_requested,
        )
        if not result.payload and str(result.message or "").strip():
            self.show_graph_hint(str(result.message), 2400)
        return bool(result.payload)

    @pyqtSlot(str, result=bool)
    def request_remove_edge(self: "ShellWindow", edge_id: str) -> bool:
        return bool(self.workspace_edit_controller.request_remove_edge(edge_id).payload)

    @pyqtSlot(str, result=bool)
    def request_ungroup_node(self: "ShellWindow", node_id: str) -> bool:
        return bool(self.workspace_edit_controller.request_ungroup_node(node_id).payload)

    @pyqtSlot(str, result=bool)
    def request_remove_node(self: "ShellWindow", node_id: str) -> bool:
        return bool(self.workspace_edit_controller.request_remove_node(node_id).payload)

    @pyqtSlot(str, result=str)
    def request_add_selected_subnode_pin(self: "ShellWindow", direction: str) -> str:
        return self.shell_inspector_presenter.request_add_selected_subnode_pin(direction)

    @pyqtSlot(str, result=bool)
    def request_rename_node(self: "ShellWindow", node_id: str) -> bool:
        return bool(self.workspace_edit_controller.request_rename_node(node_id).payload)

    @pyqtSlot(str, result=bool)
    def request_rename_selected_port(self: "ShellWindow", key: str) -> bool:
        return bool(self.workspace_edit_controller.request_rename_selected_port(key).payload)

    @pyqtSlot(str, result=bool)
    def request_remove_selected_port(self: "ShellWindow", key: str) -> bool:
        return bool(self.workspace_edit_controller.request_remove_selected_port(key).payload)

    @pyqtSlot(str, "QVariant")
    def set_selected_node_property(self: "ShellWindow", key: str, value: Any) -> None:
        self.shell_inspector_presenter.set_selected_node_property(key, value)

    @pyqtSlot(str, "QVariant", result="QVariantMap")
    def describe_pdf_preview(self: "ShellWindow", source: str, page_number: Any) -> dict[str, Any]:
        return build_pdf_preview_description(source, page_number)

    @pyqtSlot(str, result="QVariantMap")
    def describe_image_preview(self: "ShellWindow", source: str) -> dict[str, Any]:
        return build_image_preview_description(source)

    @pyqtSlot(str, result="QVariantMap")
    def describe_mail_preview(self: "ShellWindow", source: str) -> dict[str, Any]:
        return build_mail_preview_description(source)

    @pyqtSlot(str, str, result=str)
    @pyqtSlot(str, str, str, result=str)
    def browse_selected_node_property_path(
        self: "ShellWindow",
        key: str,
        current_path: str,
        source_mode: str = "",
    ) -> str:
        return self.shell_inspector_presenter.browse_selected_node_property_path(key, current_path, source_mode)

    @pyqtSlot(str, str, result=str)
    def pick_selected_node_property_color(self: "ShellWindow", key: str, current_value: str) -> str:
        return self.shell_inspector_presenter.pick_selected_node_property_color(key, current_value)

    @pyqtSlot(str, str, str, result=str)
    @pyqtSlot(str, str, str, str, result=str)
    def browse_node_property_path(
        self: "ShellWindow",
        node_id: str,
        key: str,
        current_path: str,
        source_mode: str = "",
    ) -> str:
        return self.shell_inspector_presenter.browse_node_property_path(
            node_id,
            key,
            current_path,
            source_mode,
        )

    @pyqtSlot(str, str, str, result=str)
    def internalize_node_property_path(self: "ShellWindow", node_id: str, key: str, current_path: str) -> str:
        return self.shell_inspector_presenter.internalize_node_property_path(
            node_id,
            key,
            current_path,
        )

    @pyqtSlot(str, str, str, result=str)
    def pick_node_property_color(self: "ShellWindow", node_id: str, key: str, current_value: str) -> str:
        return self.shell_inspector_presenter.pick_node_property_color(
            node_id,
            key,
            current_value,
        )

    def _browse_property_path_dialog(self: "ShellWindow", property_label: str, current_path: str) -> str:
        return self.shell_host_presenter.browse_property_path_dialog(property_label, current_path)

    def _pick_property_color_dialog(self: "ShellWindow", property_label: str, current_value: str) -> str:
        return self.shell_host_presenter.pick_property_color_dialog(property_label, current_value)

    def _repair_property_path_dialog(
        self: "ShellWindow",
        *,
        node_id: str = "",
        node_title: str = "",
        node_type: str = "",
        node_type_id: str,
        property_key: str,
        property_label: str,
        current_path: str,
        file_filter: str = "",
    ) -> str:
        return self.shell_host_presenter.repair_property_path_dialog(
            node_id=node_id,
            node_title=node_title,
            node_type=node_type,
            node_type_id=node_type_id,
            property_key=property_key,
            property_label=property_label,
            current_path=current_path,
            file_filter=file_filter,
        )

    @pyqtSlot(str, bool)
    def set_selected_port_exposed(self: "ShellWindow", key: str, exposed: bool) -> None:
        self.shell_inspector_presenter.set_selected_port_exposed(key, exposed)

    @pyqtSlot(str, str, result=bool)
    def set_selected_port_label(self: "ShellWindow", key: str, label: str) -> bool:
        return bool(self.shell_inspector_presenter.set_selected_port_label(key, label))

    @pyqtSlot(bool)
    def set_selected_node_collapsed(self: "ShellWindow", collapsed: bool) -> None:
        self.shell_inspector_presenter.set_selected_node_collapsed(collapsed)


__all__ = [
    "ShellWindowWorkspaceGraphActionsMixin",
]
