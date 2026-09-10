from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from PyQt6.QtCore import QRectF

from ea_node_editor.graph.effective_ports import effective_ports
from ea_node_editor.ui.shell.controllers.dialog_support import resolve_dialog_parent
from ea_node_editor.ui.shell.state import normalize_graph_search_scopes
from ea_node_editor.ui.support.node_presentation import build_user_facing_node_instance_number
from ea_node_editor.ui.shell.workspace_flow import build_workspace_tab_items, next_workspace_tab_index
from ea_node_editor.ui_qml.viewport_bridge import FRAME_PADDING_PX

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


class _WorkspaceViewNavControllerProtocol(Protocol):
    def save_active_view_state(self) -> None: ...

    def restore_active_view_state(self) -> None: ...

    def refresh_workspace_tabs(self) -> None: ...

    def switch_workspace(self, workspace_id: str) -> None: ...

    def reveal_parent_chain(self, workspace_id: str, node_id: str) -> list[str]: ...

    def center_on_node(self, node_id: str) -> bool: ...

    def center_on_selection(self) -> bool: ...


class WorkspaceViewNavOps:
    _GRAPH_SEARCH_LABEL_SCOPE_RANKS = {
        "title_prefix": 0,
        "title_substring": 1,
        "type_prefix": 2,
        "type_substring": 3,
        "content_prefix": 4,
        "content_substring": 5,
        "port_prefix": 6,
        "port_substring": 7,
    }
    _GRAPH_SEARCH_CONTENT_NAMES = frozenset(
        {
            "body",
            "caption",
            "subtitle",
            "message",
            "mitigation",
            "outcome",
            "summary",
            "notes",
            "note",
            "text",
        }
    )

    def __init__(
        self,
        host: ShellWindow,
        controller: _WorkspaceViewNavControllerProtocol,
    ) -> None:
        self._host = host
        self._controller = controller

    def switch_workspace_by_offset(self, offset: int) -> None:
        target = next_workspace_tab_index(
            self._host.workspace_tabs.count(),
            self._host.workspace_tabs.currentIndex(),
            offset,
        )
        if target is None:
            return
        self._host.workspace_tabs.setCurrentIndex(target)

    def refresh_workspace_tabs(self) -> None:
        current_workspace = self._host.workspace_manager.active_workspace_id()
        tabs = build_workspace_tab_items(self._host.workspace_manager.list_workspaces())
        self._host.workspace_tabs.set_tabs(tabs, current_workspace)
        self._host.workspace_state_changed.emit()

    def switch_workspace(self, workspace_id: str) -> None:
        self._controller.save_active_view_state()
        if workspace_id not in self._host.model.project.workspaces:
            return
        self._host.workspace_manager.set_active_workspace(workspace_id)
        self._host.scene.set_workspace(self._host.model, self._host.registry, workspace_id)
        self._controller.restore_active_view_state()
        self._controller.refresh_workspace_tabs()
        self._host.script_editor.set_node(None)
        self._host.run_projection_controller.update_run_actions()
        self._host.workspace_state_changed.emit()

    def save_active_view_state(self) -> None:
        workspace_id = str(self._host.scene.workspace_id or "").strip()
        if not workspace_id:
            return
        if workspace_id not in self._host.model.project.workspaces:
            return
        mutation_service = self._host.model.workspace_view_mutations(workspace_id)
        center = self._host.view.mapToScene(self._host.view.viewport().rect().center())
        mutation_service.save_active_view_state(
            zoom=self._host.view.zoom,
            pan_x=center.x(),
            pan_y=center.y(),
        )

    def restore_active_view_state(self) -> None:
        workspace_id = self._host.workspace_manager.active_workspace_id()
        if workspace_id not in self._host.model.project.workspaces:
            return
        view_state = self._host.model.workspace_view_mutations(workspace_id).active_view_state()
        self._host.view.set_zoom(max(0.1, min(3.0, view_state.zoom)))
        self._host.view.centerOn(view_state.pan_x, view_state.pan_y)

    def visible_scene_rect(self) -> QRectF:
        return self._host.view.visible_scene_rect()

    def current_workspace_scene_bounds(self) -> QRectF | None:
        return self._host.scene.workspace_scene_bounds()

    def selection_bounds(self) -> QRectF | None:
        return self._host.scene.selection_bounds()

    def frame_all(self) -> bool:
        return self.frame_scene_bounds(self.current_workspace_scene_bounds())

    def frame_selection(self) -> bool:
        return self.frame_scene_bounds(self.selection_bounds())

    def frame_node(self, node_id: str) -> bool:
        return self.frame_scene_bounds(self._host.scene.node_bounds(str(node_id).strip()))

    def center_on_node(self, node_id: str) -> bool:
        bounds = self._host.scene.node_bounds(str(node_id).strip())
        if bounds is None:
            return False
        return self._host.view.center_on_scene_rect(bounds)

    def center_on_selection(self) -> bool:
        bounds = self.selection_bounds()
        if bounds is None:
            return False
        return self._host.view.center_on_scene_rect(bounds)

    def frame_scene_bounds(self, bounds: QRectF | None) -> bool:
        if bounds is None:
            return False
        if bounds.width() <= 0.0 or bounds.height() <= 0.0:
            return False
        return self._host.view.frame_scene_rect(bounds, padding_px=FRAME_PADDING_PX)

    @staticmethod
    def _match_rank(
        query: str,
        *,
        candidate_text: str,
        prefix_rank: int,
        substring_rank: int,
    ) -> int | None:
        if not query:
            return None
        normalized_text = str(candidate_text or "").strip().lower()
        if not normalized_text:
            return None
        if normalized_text.startswith(query):
            return prefix_rank
        if query in normalized_text:
            return substring_rank
        return None

    @classmethod
    def graph_search_rank(
        cls,
        query: str,
        *,
        title: str,
        display_name: str,
        type_id: str,
    ) -> int | None:
        title_match = cls._title_match(query, title)
        if title_match is not None:
            return int(title_match["rank"])
        type_match = cls._type_match(query, display_name=display_name, type_id=type_id)
        if type_match is not None:
            return int(type_match["rank"])
        return None

    @classmethod
    def _title_match(cls, query: str, node_title: str) -> dict[str, Any] | None:
        rank = cls._match_rank(
            query,
            candidate_text=node_title,
            prefix_rank=cls._GRAPH_SEARCH_LABEL_SCOPE_RANKS["title_prefix"],
            substring_rank=cls._GRAPH_SEARCH_LABEL_SCOPE_RANKS["title_substring"],
        )
        if rank is None:
            return None
        return {
            "rank": rank,
            "match_scope": "title",
            "match_label": "Title",
            "match_preview": node_title,
        }

    @classmethod
    def _type_match(
        cls,
        query: str,
        *,
        display_name: str,
        type_id: str,
    ) -> dict[str, Any] | None:
        best_match: dict[str, Any] | None = None
        for preview in (display_name, type_id):
            rank = cls._match_rank(
                query,
                candidate_text=preview,
                prefix_rank=cls._GRAPH_SEARCH_LABEL_SCOPE_RANKS["type_prefix"],
                substring_rank=cls._GRAPH_SEARCH_LABEL_SCOPE_RANKS["type_substring"],
            )
            if rank is None:
                continue
            candidate = {
                "rank": rank,
                "match_scope": "type",
                "match_label": "Node Type",
                "match_preview": preview,
            }
            if best_match is None or int(candidate["rank"]) < int(best_match["rank"]):
                best_match = candidate
        return best_match

    @classmethod
    def _property_is_content_searchable(cls, property_spec: Any) -> bool:
        if str(getattr(property_spec, "type", "")).strip().lower() != "str":
            return False
        if not bool(getattr(property_spec, "inspector_visible", True)):
            return False
        normalized_key = str(getattr(property_spec, "key", "")).strip().lower()
        if normalized_key == "title":
            return False
        normalized_label = str(getattr(property_spec, "label", "")).strip().lower()
        inline_editor = str(getattr(property_spec, "inline_editor", "")).strip().lower()
        inspector_editor = str(getattr(property_spec, "inspector_editor", "")).strip().lower()
        if inline_editor == "textarea" or inspector_editor == "textarea":
            return True
        return normalized_key in cls._GRAPH_SEARCH_CONTENT_NAMES or normalized_label in cls._GRAPH_SEARCH_CONTENT_NAMES

    @staticmethod
    def _compact_search_preview(value: object, *, max_length: int = 72) -> str:
        preview = " ".join(str(value or "").split())
        if len(preview) <= max_length:
            return preview
        if max_length <= 3:
            return preview[:max_length]
        return preview[: max_length - 3].rstrip() + "..."

    @classmethod
    def _content_match(cls, query: str, *, node: Any, spec: Any) -> dict[str, Any] | None:
        best_match: dict[str, Any] | None = None
        for property_spec in getattr(spec, "properties", ()):
            if not cls._property_is_content_searchable(property_spec):
                continue
            property_key = str(getattr(property_spec, "key", "")).strip()
            if property_key not in getattr(node, "properties", {}):
                continue
            property_value = node.properties.get(property_key)
            preview = str(property_value or "").strip()
            if not preview:
                continue
            rank = cls._match_rank(
                query,
                candidate_text=preview,
                prefix_rank=cls._GRAPH_SEARCH_LABEL_SCOPE_RANKS["content_prefix"],
                substring_rank=cls._GRAPH_SEARCH_LABEL_SCOPE_RANKS["content_substring"],
            )
            if rank is None:
                continue
            candidate = {
                "rank": rank,
                "match_scope": "content",
                "match_label": str(getattr(property_spec, "label", "")).strip() or property_key,
                "match_preview": cls._compact_search_preview(preview),
            }
            if best_match is None or int(candidate["rank"]) < int(best_match["rank"]):
                best_match = candidate
        return best_match

    @classmethod
    def _port_match(
        cls,
        query: str,
        *,
        node: Any,
        spec: Any,
        workspace_nodes: dict[str, Any],
    ) -> dict[str, Any] | None:
        best_match: dict[str, Any] | None = None
        for port in effective_ports(node=node, spec=spec, workspace_nodes=workspace_nodes):
            if not bool(port.exposed):
                continue
            preview = str(port.label or port.key).strip()
            if not preview:
                continue
            rank = cls._match_rank(
                query,
                candidate_text=preview,
                prefix_rank=cls._GRAPH_SEARCH_LABEL_SCOPE_RANKS["port_prefix"],
                substring_rank=cls._GRAPH_SEARCH_LABEL_SCOPE_RANKS["port_substring"],
            )
            if rank is None:
                continue
            candidate = {
                "rank": rank,
                "match_scope": "port",
                "match_label": "Port Label",
                "match_preview": cls._compact_search_preview(preview),
            }
            if best_match is None or int(candidate["rank"]) < int(best_match["rank"]):
                best_match = candidate
        return best_match

    @classmethod
    def _graph_search_match(
        cls,
        query: str,
        *,
        enabled_scopes: list[str],
        node: Any,
        spec: Any,
        workspace_nodes: dict[str, Any],
    ) -> dict[str, Any] | None:
        node_title = str(getattr(node, "title", ""))
        display_name = str(getattr(spec, "display_name", ""))
        type_id = str(getattr(node, "type_id", ""))
        for scope_id in enabled_scopes:
            if scope_id == "title":
                match = cls._title_match(query, node_title)
            elif scope_id == "type":
                match = cls._type_match(query, display_name=display_name, type_id=type_id)
            elif scope_id == "content":
                match = cls._content_match(query, node=node, spec=spec)
            elif scope_id == "port":
                match = cls._port_match(query, node=node, spec=spec, workspace_nodes=workspace_nodes)
            else:
                match = None
            if match is not None:
                return match
        return None

    def search_graph_nodes(
        self,
        query: str,
        limit: int,
        *,
        enabled_scopes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        normalized_query = str(query).strip().lower()
        if not normalized_query:
            return []

        normalized_scopes = normalize_graph_search_scopes(enabled_scopes)
        max_results = max(0, int(limit))
        ranked: list[tuple[int, str, str, dict[str, Any]]] = []
        for workspace_ref in self._host.workspace_manager.list_workspaces():
            workspace = self._host.model.project.workspaces.get(workspace_ref.workspace_id)
            if workspace is None:
                continue
            workspace_name_lower = workspace.name.lower()
            for node in workspace.nodes.values():
                spec = self._host.registry.get_spec(node.type_id)
                node_title = str(node.title)
                node_title_lower = node_title.lower()
                display_name = str(spec.display_name)
                type_id = str(node.type_id)
                node_id = str(node.node_id)
                instance_number = build_user_facing_node_instance_number(
                    node=node,
                    workflow_nodes=workspace.nodes,
                )
                match = self._graph_search_match(
                    normalized_query,
                    enabled_scopes=normalized_scopes,
                    node=node,
                    spec=spec,
                    workspace_nodes=workspace.nodes,
                )
                if match is None:
                    continue
                ranked.append(
                    (
                        int(match["rank"]),
                        workspace_name_lower,
                        node_title_lower,
                        {
                            "workspace_id": workspace.workspace_id,
                            "workspace_name": workspace.name,
                            "node_id": node_id,
                            "node_title": node_title,
                            "display_name": display_name,
                            "instance_number": int(instance_number),
                            "instance_label": f"ID {instance_number}",
                            "type_id": type_id,
                            "match_scope": str(match["match_scope"]),
                            "match_label": str(match["match_label"]),
                            "match_preview": str(match["match_preview"]),
                        },
                    )
                )

        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        return [item[3] for item in ranked[:max_results]]

    def jump_to_graph_node(self, workspace_id: str, node_id: str) -> bool:
        normalized_workspace_id = str(workspace_id).strip()
        normalized_node_id = str(node_id).strip()
        if not normalized_workspace_id or not normalized_node_id:
            return False

        workspace = self._host.model.project.workspaces.get(normalized_workspace_id)
        if workspace is None or normalized_node_id not in workspace.nodes:
            return False

        if normalized_workspace_id != self._host.workspace_manager.active_workspace_id():
            self._controller.switch_workspace(normalized_workspace_id)

        self._controller.reveal_parent_chain(normalized_workspace_id, normalized_node_id)
        self._host.scene.open_scope_for_node(normalized_node_id)
        if self._host.scene.focus_node(normalized_node_id) is None:
            return False
        return self._controller.center_on_selection()

    def _failed_node_title(self, workspace_id: str, node_id: str) -> str:
        normalized_workspace_id = str(workspace_id or "").strip()
        normalized_node_id = str(node_id or "").strip()
        if not normalized_workspace_id or not normalized_node_id:
            return ""
        workspace = self._host.model.project.workspaces.get(normalized_workspace_id)
        if workspace is None:
            return ""
        node = workspace.nodes.get(normalized_node_id)
        if node is None:
            return ""
        return str(node.title or "").strip()

    def create_view(self) -> None:
        workspace_id = self._host.workspace_manager.active_workspace_id()
        self._controller.save_active_view_state()
        if workspace_id not in self._host.model.project.workspaces:
            return
        mutation_service = self._host.model.workspace_view_mutations(workspace_id)
        source_view_id = mutation_service.active_view_state().view_id
        presenter = getattr(self._host, "shell_host_presenter", None)
        prompt_text_value = getattr(presenter, "prompt_text_value", None)
        if callable(prompt_text_value):
            name, ok = prompt_text_value(title="New View", label="View name:")
        else:
            from PyQt6.QtWidgets import QInputDialog

            name, ok = QInputDialog.getText(resolve_dialog_parent(self._host), "New View", "View name:")
        if not ok:
            return
        normalized_name = str(name).strip()
        view = mutation_service.create_view(
            name=normalized_name or None,
            source_view_id=source_view_id,
        )
        mutation_service.set_active_view(view.view_id)
        self._controller.restore_active_view_state()
        self._host.workspace_state_changed.emit()

    def switch_view(self, view_id: str) -> None:
        workspace_id = self._host.workspace_manager.active_workspace_id()
        self._controller.save_active_view_state()
        if workspace_id not in self._host.model.project.workspaces:
            return
        self._host.model.workspace_view_mutations(workspace_id).set_active_view(view_id)
        self._controller.restore_active_view_state()
        self._host.workspace_state_changed.emit()

    def focus_failed_node(self, workspace_id: str, node_id: str) -> None:
        if workspace_id and workspace_id != self._host.workspace_manager.active_workspace_id():
            self._controller.switch_workspace(workspace_id)

        focus_candidates: list[str] = []
        if node_id:
            focus_candidates.append(node_id)
        focus_candidates.extend(self._controller.reveal_parent_chain(workspace_id, node_id))

        focused_node_id = ""
        for target_node_id in focus_candidates:
            self._host.scene.open_scope_for_node(target_node_id)
            if self._host.scene.focus_node(target_node_id) is not None:
                focused_node_id = target_node_id
                break
        if focused_node_id:
            self._controller.center_on_node(focused_node_id)
        failure_workspace_id = str(self._host.workspace_manager.active_workspace_id() or "").strip()
        failure_node_id = str(focused_node_id or node_id or "").strip()
        failure_node_title = self._failed_node_title(failure_workspace_id, failure_node_id)
        if failure_node_id:
            self._host.run_projection_controller.set_run_failure_focus(
                failure_workspace_id,
                failure_node_id,
                node_title=failure_node_title,
            )
            if failure_node_title:
                self._host.show_graph_hint(f'Execution halted at "{failure_node_title}".', 4800)
            else:
                self._host.show_graph_hint("Execution halted at the failed node.", 4800)

    def reveal_parent_chain(self, workspace_id: str, node_id: str) -> list[str]:
        if not workspace_id or not node_id:
            return []
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if workspace is None:
            return []
        node = workspace.nodes.get(node_id)
        if node is None:
            return []

        chain: list[str] = []
        seen: set[str] = set()
        parent_id = node.parent_node_id
        while parent_id and parent_id not in seen:
            seen.add(parent_id)
            parent_node = workspace.nodes.get(parent_id)
            if parent_node is None:
                break
            chain.append(parent_id)
            parent_id = parent_node.parent_node_id

        for candidate_id in reversed(chain):
            parent_node = workspace.nodes.get(candidate_id)
            if parent_node is not None and parent_node.collapsed:
                self._host.scene.set_node_collapsed(candidate_id, False)
        return chain
