from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices, QGuiApplication

from ea_node_editor.ui.shell.property_edit_adapters import (
    create_shell_property_edit_adapters,
)
from ea_node_editor.app_preferences import normalize_property_pane_variant
from ea_node_editor.graph.file_issue_state import (
    EXTERNAL_LINK_MODE,
    MANAGED_COPY_MODE,
    collect_node_file_issues,
    decode_file_repair_request,
    repair_modes_for_node_property,
)
from ea_node_editor.graph.node_comments import node_comments_to_payload
from ea_node_editor.nodes.builtins.subnode import (
    SUBNODE_PIN_DATA_TYPE_PROPERTY,
    SUBNODE_TYPE_ID,
)
from ea_node_editor.nodes.node_specs import property_inspector_editor
from ea_node_editor.platform_open import open_path_with_default_handler
from ea_node_editor.settings import DEFAULT_PROPERTY_PANE_VARIANT
from ea_node_editor.ui.support.node_presentation import build_user_facing_node_instance_number, has_focused_selector
from ea_node_editor.addons.property_edit_adapters import selector_metadata_signature
from ea_node_editor.ui.support.solution_output_cache import current_output_value
from ea_node_editor.ui.media_panel_source import media_panel_source_input_exposed
from ea_node_editor.ui.shell.inspector_projection import (
    build_pin_data_type_options,
    build_selected_node_header_data,
    build_selected_node_link_items,
    build_selected_node_port_items,
    build_selected_node_property_items,
)

from .contracts import _ShellInspectorPresenterHostProtocol, _presenter_parent


_SOURCE_STORAGE_PATH_MODES_BY_PROPERTY = {
    ("web.page_viewer", "start_location"): (MANAGED_COPY_MODE, EXTERNAL_LINK_MODE),
}


class ShellInspectorPresenter(QObject):
    selected_node_changed = pyqtSignal()
    workspace_state_changed = pyqtSignal()
    inspector_state_changed = pyqtSignal()

    def __init__(
        self,
        host: _ShellInspectorPresenterHostProtocol,
        *,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(_presenter_parent(host, parent))
        self._host = host
        self._property_pane_variant = DEFAULT_PROPERTY_PANE_VARIANT
        self._pin_data_type_cache_key: tuple[Any, ...] | None = None
        self._pin_data_type_options_cache: list[str] = []
        host.selected_node_changed.connect(self._emit_selected_node_changed)
        host.workspace_state_changed.connect(self._emit_workspace_state_changed)
        self._last_selector_metadata = None
        self._runtime_schema_pending = False
        self._content_active = True
        host.node_execution_state_changed.connect(self._on_current_output_changed)
        app = QGuiApplication.instance()
        self._gui_app = app if isinstance(app, QGuiApplication) else None
        if self._gui_app is not None:
            self._gui_app.focusObjectChanged.connect(self._on_editor_focus_changed)

    def shutdown(self) -> None:
        if self._gui_app is not None:
            self._gui_app.focusObjectChanged.disconnect(self._on_editor_focus_changed)

    def _emit_selected_node_changed(self) -> None:
        self._runtime_schema_pending = False
        self._last_selector_metadata = None
        self.selected_node_changed.emit()
        self.inspector_state_changed.emit()

    def _emit_workspace_state_changed(self) -> None:
        self._runtime_schema_pending = False
        self._last_selector_metadata = None
        self.workspace_state_changed.emit()
        self.inspector_state_changed.emit()

    def _selector_metadata(self):
        selected = self._selected_node_context()
        if selected is None:
            return None
        workspace_id = self._host.workspace_manager.active_workspace_id()
        return workspace_id, selected[0].node_id, selector_metadata_signature(
            self._build_selected_node_property_items()
        )

    def _on_current_output_changed(self) -> None:
        if not self._content_active:
            return
        schema = self._selector_metadata()
        if schema is None or schema == self._last_selector_metadata:
            self._runtime_schema_pending = False
            return
        if has_focused_selector("inspectorPropertyEditor", "inspectorSelectorOptions"):
            self._runtime_schema_pending = True
            return
        self._runtime_schema_pending = False
        self._last_selector_metadata = schema
        self.inspector_state_changed.emit()

    def set_content_active(self, active: bool) -> None:
        """The visible Properties view owns demand for runtime schema projection."""
        self._content_active = bool(active)
        if not self._content_active:
            self._runtime_schema_pending = False

    def _on_editor_focus_changed(self, _focused: QObject | None) -> None:
        if self._runtime_schema_pending:
            QTimer.singleShot(0, self._on_current_output_changed)

    def _selected_node_context(self):
        return self._host.workspace_selection_context.selected_node_context()

    def _selected_node_header_data(self) -> dict[str, Any]:
        selected = self._selected_node_context()
        if selected is None:
            return {}
        node, spec = selected
        workspace = self._host.model.project.workspaces.get(self._host.workspace_manager.active_workspace_id())
        workflow_nodes = workspace.nodes if workspace is not None else {}
        return build_selected_node_header_data(node=node, spec=spec, workflow_nodes=workflow_nodes)

    @property
    def selected_node_title(self) -> str: return str(self._selected_node_header_data().get("title", ""))

    @property
    def selected_node_subtitle(self) -> str: return str(self._selected_node_header_data().get("subtitle", ""))

    @property
    def selected_node_header_items(self) -> list[dict[str, str]]:
        header_data = self._selected_node_header_data()
        items = header_data.get("metadata_items", [])
        return list(items) if isinstance(items, list) else []

    @property
    def selected_node_summary(self) -> str:
        header_data = self._selected_node_header_data()
        if not header_data:
            return "No node selected"
        lines = [str(header_data.get("title", "")).strip()]
        for item in self.selected_node_header_items:
            label = str(item.get("label", "")).strip()
            value = str(item.get("value", "")).strip()
            if label and value:
                lines.append(f"{label}: {value}")
        return "\n".join(line for line in lines if line)

    @property
    def has_selected_node(self) -> bool: return self._selected_node_context() is not None

    @property
    def selected_node_id(self) -> str:
        selected = self._selected_node_context()
        if selected is None:
            return ""
        node, _spec = selected
        return str(getattr(node, "node_id", "") or "")

    @property
    def selected_node_workspace_id(self) -> str:
        return str(self._host.workspace_manager.active_workspace_id() or "").strip() if self.has_selected_node else ""

    @property
    def selected_node_collapsible(self) -> bool:
        selected = self._selected_node_context()
        return bool(selected[1].collapsible) if selected is not None else False

    @property
    def selected_node_collapsed(self) -> bool:
        selected = self._selected_node_context()
        return bool(selected[0].collapsed) if selected is not None else False

    @property
    def selected_node_is_subnode_pin(self) -> bool:
        selected = self._selected_node_context()
        return bool(selected and selected[0].type_id in self._host._SUBNODE_PIN_TYPE_IDS)

    @property
    def selected_node_is_subnode_shell(self) -> bool:
        selected = self._selected_node_context()
        return bool(selected and selected[0].type_id == SUBNODE_TYPE_ID)

    @property
    def selected_node_property_items(self) -> list[dict[str, Any]]:
        items = self._build_selected_node_property_items()
        selected = self._selected_node_context()
        if selected is not None:
            self._last_selector_metadata = (
                self._host.workspace_manager.active_workspace_id(),
                selected[0].node_id,
                selector_metadata_signature(items),
            )
        return items

    def _build_selected_node_property_items(self) -> list[dict[str, Any]]:
        selected = self._selected_node_context()
        if selected is None:
            return []
        node, spec = selected
        workspace = self._host.model.project.workspaces.get(self._host.workspace_manager.active_workspace_id())
        if workspace is None:
            return []
        port_connection_counts: dict[tuple[str, str], int] = {}
        for edge in workspace.edges.values():
            if not bool(getattr(edge, "enabled", True)):
                continue
            source_key = (edge.source_node_id, edge.source_port_key)
            target_key = (edge.target_node_id, edge.target_port_key)
            port_connection_counts[source_key] = port_connection_counts.get(source_key, 0) + 1
            port_connection_counts[target_key] = port_connection_counts.get(target_key, 0) + 1
        metadata = self._host.model.project.metadata
        return build_selected_node_property_items(
            node=node,
            spec=spec,
            subnode_pin_type_ids=self._host._SUBNODE_PIN_TYPE_IDS,
            workspace_id=str(self._host.workspace_manager.active_workspace_id() or ""),
            workspace_nodes=workspace.nodes,
            workspace_edges=workspace.edges,
            port_connection_counts=port_connection_counts,
            file_issues_by_key=collect_node_file_issues(
                node=node,
                spec=spec,
                project_path=str(self._host.project_path or "").strip() or None,
                project_metadata=dict(metadata) if isinstance(metadata, dict) else None,
            ),
            project_path=str(self._host.project_path or "").strip() or None,
            project_metadata=dict(metadata) if isinstance(metadata, dict) else None,
            property_edit_adapters=self._property_edit_adapters(),
            current_output_provider=lambda node_id, port_key: current_output_value(
                self._host.run_state, workspace.workspace_id, node_id, port_key,
            ),
        )

    @property
    def selected_node_link_items(self) -> list[dict[str, Any]]:
        selected = self._selected_node_context()
        if selected is None:
            return []
        node, _spec = selected
        workspace = self._host.model.project.workspaces.get(self._host.workspace_manager.active_workspace_id())
        if workspace is None:
            return []
        return build_selected_node_link_items(
            node=node,
            workspace_nodes=workspace.nodes,
            workspaces=self._host.model.project.workspaces,
        )

    @property
    def selected_node_comment_items(self) -> list[dict[str, Any]]:
        selected = self._selected_node_context()
        if selected is None:
            return []
        node, _spec = selected
        return node_comments_to_payload(list(node.comments))

    @property
    def selected_node_link_node_options(self) -> list[dict[str, Any]]:
        selected = self._selected_node_context()
        if selected is None:
            return []
        source_node, _source_spec = selected
        source_workspace_id = str(self._host.workspace_manager.active_workspace_id() or "").strip()
        options: list[dict[str, Any]] = []
        for workspace in self._host.model.project.workspaces.values():
            workspace_id = str(getattr(workspace, "workspace_id", "") or "").strip()
            workspace_name = str(getattr(workspace, "name", "") or workspace_id).strip() or workspace_id
            nodes = getattr(workspace, "nodes", {})
            if not hasattr(nodes, "values"):
                continue
            for node in nodes.values():
                node_id = str(getattr(node, "node_id", "") or "").strip()
                if not node_id:
                    continue
                if workspace_id == source_workspace_id and node_id == str(source_node.node_id):
                    continue
                spec = self._host.registry.get_spec(getattr(node, "type_id", ""))
                label = str(getattr(node, "title", "") or getattr(spec, "display_name", "") or node_id).strip()
                display_name = str(getattr(spec, "display_name", "") or getattr(node, "type_id", "") or "").strip()
                instance_number = build_user_facing_node_instance_number(
                    node=node,
                    workflow_nodes=nodes,
                )
                instance_label = f"ID {instance_number}"
                subtitle_parts = [workspace_name]
                if display_name:
                    subtitle_parts.append(display_name)
                subtitle_parts.append(instance_label)
                options.append(
                    {
                        "kind": "node",
                        "target": node_id,
                        "target_node_id": node_id,
                        "target_workspace_id": workspace_id,
                        "workspace_id": workspace_id,
                        "workspace_name": workspace_name,
                        "label": label,
                        "title": label,
                        "subtitle": " - ".join(part for part in subtitle_parts if part),
                        "display_name": display_name,
                        "instance_label": instance_label,
                        "type_id": str(getattr(node, "type_id", "") or ""),
                    }
                )
        return sorted(
            options,
            key=lambda item: (
                str(item.get("workspace_name", "")).lower(),
                str(item.get("label", "")).lower(),
                str(item.get("target_node_id", "")).lower(),
            ),
        )

    @property
    def selected_node_link_workspace_options(self) -> list[dict[str, Any]]:
        active_workspace_id = str(self._host.workspace_manager.active_workspace_id() or "").strip()
        options: list[dict[str, Any]] = []
        for workspace in self._host.model.project.workspaces.values():
            workspace_id = str(getattr(workspace, "workspace_id", "") or "").strip()
            if not workspace_id:
                continue
            workspace_name = str(getattr(workspace, "name", "") or workspace_id).strip() or workspace_id
            active = workspace_id == active_workspace_id
            options.append(
                {
                    "kind": "workspace",
                    "target": workspace_id,
                    "target_workspace_id": workspace_id,
                    "label": workspace_name,
                    "title": workspace_name,
                    "subtitle": "Current workspace" if active else "Workspace",
                    "active": active,
                }
            )
        return sorted(options, key=lambda item: (not bool(item.get("active")), str(item.get("label", "")).lower()))

    def _property_edit_adapters(self) -> tuple[Any, ...]:
        controller = getattr(self._host, "app_preferences_controller", None)
        document = getattr(controller, "document", None)
        preferences_document = document() if callable(document) else None
        return create_shell_property_edit_adapters(
            preferences_document=preferences_document
        )

    @property
    def selected_node_port_items(self) -> list[dict[str, Any]]:
        selected = self._selected_node_context()
        if selected is None or self.selected_node_is_subnode_pin:
            return []
        node, spec = selected
        workspace = self._host.model.project.workspaces.get(self._host.workspace_manager.active_workspace_id())
        if workspace is None:
            return []
        return build_selected_node_port_items(node=node, spec=spec, workspace_nodes=workspace.nodes)

    @property
    def property_pane_variant(self) -> str:
        return str(self._property_pane_variant)

    def set_property_pane_variant(self, variant: str) -> None:
        normalized = normalize_property_pane_variant(variant, self._property_pane_variant)
        if normalized == self._property_pane_variant:
            return
        self._property_pane_variant = normalized
        self.inspector_state_changed.emit()

    @property
    def pin_data_type_options(self) -> list[str]:
        workspaces = self._host.model.project.workspaces.values()
        cache_key = (
            id(self._host.registry),
            tuple(
                (id(workspace), int(getattr(workspace, "mutation_revision", 0) or 0))
                for workspace in workspaces
            ),
        )
        if cache_key != self._pin_data_type_cache_key:
            self._pin_data_type_options_cache = build_pin_data_type_options(
                registry_specs=self._host.registry.all_specs(),
                workspaces=self._host.model.project.workspaces.values(),
                subnode_pin_type_ids=self._host._SUBNODE_PIN_TYPE_IDS,
                subnode_pin_data_type_property=SUBNODE_PIN_DATA_TYPE_PROPERTY,
            )
            self._pin_data_type_cache_key = cache_key
        return list(self._pin_data_type_options_cache)

    def _node_context_by_id(self, node_id: str):
        normalized_node_id = str(node_id or "").strip()
        if not normalized_node_id:
            return None
        workspace = self._host.model.project.workspaces.get(self._host.workspace_manager.active_workspace_id())
        if workspace is None:
            return None
        node = workspace.nodes.get(normalized_node_id)
        if node is None:
            return None
        return node, self._host.registry.resolve_spec(node.type_id, node.properties)

    def _node_property_spec(self, node_id: str, key: str):
        normalized_key = str(key).strip()
        if not normalized_key:
            return None
        node_context = self._node_context_by_id(node_id)
        if node_context is None:
            return None
        _node, spec = node_context
        return next((prop for prop in spec.properties if prop.key == normalized_key), None)

    def _selected_node_property_spec(self, key: str):
        selected = self._selected_node_context()
        if selected is None:
            return None
        node, _spec = selected
        return self._node_property_spec(node.node_id, key)

    @staticmethod
    def _property_edit_allowed(node: Any, key: str) -> bool:
        return not (
            str(key or "").strip() == "source"
            and media_panel_source_input_exposed(node)
        )

    @staticmethod
    def _path_dialog_mode(node: Any, property_spec: Any) -> str:
        if str(getattr(node, "type_id", "")).strip() != "io.path_pointer":
            return "file"
        if str(getattr(property_spec, "key", "")).strip() != "path":
            return "file"
        properties = getattr(node, "properties", None)
        if not hasattr(properties, "get"):
            return "file"
        return "folder" if str(properties.get("mode", "file")).strip().lower() == "folder" else "file"

    @staticmethod
    def _source_import_mode_for_path_property(node: Any, property_spec: Any, source_mode: str) -> str | None:
        normalized = str(source_mode or "").strip().lower()
        if not normalized:
            return ""
        if normalized not in {MANAGED_COPY_MODE, EXTERNAL_LINK_MODE}:
            return None
        node_type_id = str(getattr(node, "type_id", "")).strip()
        property_key = str(getattr(property_spec, "key", "")).strip()
        allowed_modes = _SOURCE_STORAGE_PATH_MODES_BY_PROPERTY.get((node_type_id, property_key))
        if allowed_modes is None:
            allowed_modes = repair_modes_for_node_property(node_type_id, property_key)
        return normalized if normalized in allowed_modes else None

    @staticmethod
    def _path_dialog_file_filter(property_spec: Any) -> str:
        return str(getattr(property_spec, "file_filter", "") or "").strip()

    def _path_dialog_start_path(self, current_path: str) -> str:
        normalized_current = str(current_path or "").strip()
        if normalized_current:
            candidate = Path(normalized_current).expanduser()
            if candidate.exists():
                return str(candidate)
            parent = candidate.parent
            if str(parent).strip() and parent.exists():
                return str(parent)
        normalized_project_path = str(self._host.project_path or "").strip()
        if normalized_project_path:
            project_path = Path(normalized_project_path).expanduser()
            parent = project_path.parent
            if str(parent).strip() and parent.exists():
                return str(parent)
        return str(Path.cwd())

    def set_selected_node_property(self, key: str, value: Any) -> None:
        selected = self._selected_node_context()
        if selected is None or not self._property_edit_allowed(selected[0], key):
            return
        self._host.workspace_edit_controller.set_selected_node_property(key, value)

    def upsert_selected_node_link(
        self,
        link_id: str,
        kind: str,
        title: str,
        target: str,
        subtitle: str = "",
        target_workspace_id: str = "",
        target_node_id: str = "",
    ) -> str:
        selected = self._selected_node_context()
        if selected is None:
            return ""
        node, _spec = selected
        scene = getattr(self._host, "scene", None)
        upsert = getattr(scene, "upsert_node_link", None)
        if not callable(upsert):
            return ""
        if str(target_workspace_id or "").strip() or str(target_node_id or "").strip():
            return str(
                upsert(
                    node.node_id,
                    link_id,
                    kind,
                    title,
                    target,
                    subtitle,
                    target_workspace_id,
                    target_node_id,
                )
                or ""
            )
        return str(
            upsert(
                node.node_id,
                link_id,
                kind,
                title,
                target,
                subtitle,
            )
            or ""
        )

    def remove_selected_node_link(self, link_id: str) -> bool:
        selected = self._selected_node_context()
        if selected is None:
            return False
        node, _spec = selected
        scene = getattr(self._host, "scene", None)
        remove = getattr(scene, "remove_node_link", None)
        return bool(remove(node.node_id, link_id)) if callable(remove) else False

    def move_selected_node_link(self, link_id: str, offset: int) -> bool:
        selected = self._selected_node_context()
        if selected is None:
            return False
        node, _spec = selected
        scene = getattr(self._host, "scene", None)
        move = getattr(scene, "move_node_link", None)
        return bool(move(node.node_id, link_id, int(offset))) if callable(move) else False

    @staticmethod
    def _normalized_link_url(target: str) -> QUrl:
        text = str(target or "").strip()
        if text and "://" not in text:
            text = f"https://{text}"
        return QUrl(text)

    def open_selected_node_link(self, link_id: str) -> bool:
        selected = self._selected_node_context()
        if selected is None:
            return False
        node, _spec = selected
        normalized_link_id = str(link_id or "").strip()
        link = next((item for item in node.links if item.link_id == normalized_link_id), None)
        if link is None:
            return False
        if link.kind == "url":
            return bool(QDesktopServices.openUrl(self._normalized_link_url(link.target)))
        if link.kind in {"file", "folder"}:
            return bool(open_path_with_default_handler(link.target))
        if link.kind == "node":
            workspace_id = str(getattr(link, "target_workspace_id", "") or self._host.workspace_manager.active_workspace_id())
            node_id = str(getattr(link, "target_node_id", "") or link.target)
            return bool(self._host.workspace_navigation_controller.jump_to_graph_node(workspace_id, node_id))
        if link.kind == "workspace":
            if link.target not in self._host.model.project.workspaces:
                return False
            self._host.workspace_navigation_controller.switch_workspace(link.target)
            return True
        return False

    def upsert_selected_node_comment(
        self,
        comment_id: str,
        body: str,
        parent_id: str = "",
        resolved: bool = False,
        unread: bool = True,
        pinned: bool = False,
    ) -> str:
        selected = self._selected_node_context()
        if selected is None:
            return ""
        node, _spec = selected
        scene = getattr(self._host, "scene", None)
        upsert = getattr(scene, "upsert_node_comment", None)
        if not callable(upsert):
            return ""
        return str(
            upsert(
                node.node_id,
                comment_id,
                body,
                "",
                parent_id,
                bool(resolved),
                bool(unread),
                bool(pinned),
            )
            or ""
        )

    def remove_selected_node_comment(self, comment_id: str) -> bool:
        selected = self._selected_node_context()
        if selected is None:
            return False
        node, _spec = selected
        scene = getattr(self._host, "scene", None)
        remove = getattr(scene, "remove_node_comment", None)
        return bool(remove(node.node_id, comment_id)) if callable(remove) else False

    def set_selected_node_comment_resolved(self, comment_id: str, resolved: bool) -> bool:
        selected = self._selected_node_context()
        if selected is None:
            return False
        node, _spec = selected
        scene = getattr(self._host, "scene", None)
        set_resolved = getattr(scene, "set_node_comment_resolved", None)
        return bool(set_resolved(node.node_id, comment_id, bool(resolved))) if callable(set_resolved) else False

    def set_selected_node_comment_pinned(self, comment_id: str, pinned: bool) -> bool:
        selected = self._selected_node_context()
        if selected is None:
            return False
        node, _spec = selected
        scene = getattr(self._host, "scene", None)
        set_pinned = getattr(scene, "set_node_comment_pinned", None)
        return bool(set_pinned(node.node_id, comment_id, bool(pinned))) if callable(set_pinned) else False

    def resolve_all_selected_node_comments(self) -> bool:
        selected = self._selected_node_context()
        if selected is None:
            return False
        node, _spec = selected
        scene = getattr(self._host, "scene", None)
        resolve_all = getattr(scene, "resolve_all_node_comments", None)
        return bool(resolve_all(node.node_id)) if callable(resolve_all) else False

    def mark_selected_node_comments_read(self) -> bool:
        selected = self._selected_node_context()
        if selected is None:
            return False
        node, _spec = selected
        scene = getattr(self._host, "scene", None)
        mark_read = getattr(scene, "mark_node_comments_read", None)
        return bool(mark_read(node.node_id)) if callable(mark_read) else False

    def browse_selected_node_property_path(self, key: str, current_path: str, source_mode: str = "") -> str:
        selected = self._selected_node_context()
        if selected is None:
            return ""
        node, _spec = selected
        property_spec = self._selected_node_property_spec(key)
        if (
            property_spec is None
            or property_inspector_editor(property_spec) != "path"
            or not self._property_edit_allowed(node, key)
        ):
            return ""
        dialog_mode = self._path_dialog_mode(node, property_spec)
        explicit_source_mode = self._source_import_mode_for_path_property(node, property_spec, source_mode)
        if explicit_source_mode is None:
            return ""
        repair_request = decode_file_repair_request(current_path)
        if repair_request is not None:
            if dialog_mode == "folder":
                return self._host.shell_host_presenter.browse_property_path_dialog(
                    property_spec.label,
                    repair_request.current_value,
                    dialog_mode=dialog_mode,
                    file_filter=self._path_dialog_file_filter(property_spec),
                    node_type_id=node.type_id,
                    property_key=property_spec.key,
                    node_id=node.node_id,
                    node_title=node.title,
                    node_type=getattr(_spec, "display_name", "") or node.type_id,
                )
            return self._host._repair_property_path_dialog(
                node_id=node.node_id,
                node_title=node.title,
                node_type=getattr(_spec, "display_name", "") or node.type_id,
                node_type_id=node.type_id,
                property_key=property_spec.key,
                property_label=property_spec.label,
                current_path=repair_request.current_value,
                file_filter=self._path_dialog_file_filter(property_spec),
            )
        return self._host.shell_host_presenter.browse_property_path_dialog(
            property_spec.label,
            current_path,
            dialog_mode=dialog_mode,
            source_mode=explicit_source_mode,
            file_filter=self._path_dialog_file_filter(property_spec),
            node_type_id=node.type_id,
            property_key=property_spec.key,
            node_id=node.node_id,
            node_title=node.title,
            node_type=getattr(_spec, "display_name", "") or node.type_id,
        )

    def browse_node_property_path(self, node_id: str, key: str, current_path: str, source_mode: str = "") -> str:
        node_context = self._node_context_by_id(node_id)
        if node_context is None:
            return ""
        node, spec = node_context
        property_spec = self._node_property_spec(node_id, key)
        if (
            property_spec is None
            or property_inspector_editor(property_spec) != "path"
            or not self._property_edit_allowed(node, key)
        ):
            return ""
        dialog_mode = self._path_dialog_mode(node, property_spec)
        explicit_source_mode = self._source_import_mode_for_path_property(node, property_spec, source_mode)
        if explicit_source_mode is None:
            return ""
        repair_request = decode_file_repair_request(current_path)
        if repair_request is not None:
            if dialog_mode == "folder":
                return self._host.shell_host_presenter.browse_property_path_dialog(
                    property_spec.label,
                    repair_request.current_value,
                    dialog_mode=dialog_mode,
                    file_filter=self._path_dialog_file_filter(property_spec),
                    node_type_id=node.type_id,
                    property_key=property_spec.key,
                    node_id=node.node_id,
                    node_title=node.title,
                    node_type=getattr(spec, "display_name", "") or node.type_id,
                )
            return self._host._repair_property_path_dialog(
                node_id=node.node_id,
                node_title=node.title,
                node_type=getattr(spec, "display_name", "") or node.type_id,
                node_type_id=node.type_id,
                property_key=property_spec.key,
                property_label=property_spec.label,
                current_path=repair_request.current_value,
                file_filter=self._path_dialog_file_filter(property_spec),
            )
        return self._host.shell_host_presenter.browse_property_path_dialog(
            property_spec.label,
            current_path,
            dialog_mode=dialog_mode,
            source_mode=explicit_source_mode,
            file_filter=self._path_dialog_file_filter(property_spec),
            node_type_id=node.type_id,
            property_key=property_spec.key,
            node_id=node.node_id,
            node_title=node.title,
            node_type=getattr(spec, "display_name", "") or node.type_id,
        )

    def internalize_node_property_path(self, node_id: str, key: str, current_path: str) -> str:
        node_context = self._node_context_by_id(node_id)
        if node_context is None:
            return ""
        node, spec = node_context
        property_spec = self._node_property_spec(node_id, key)
        if (
            property_spec is None
            or property_inspector_editor(property_spec) != "path"
            or not self._property_edit_allowed(node, key)
        ):
            return ""
        explicit_source_mode = self._source_import_mode_for_path_property(
            node,
            property_spec,
            MANAGED_COPY_MODE,
        )
        if explicit_source_mode != MANAGED_COPY_MODE:
            return ""
        if decode_file_repair_request(current_path) is not None:
            return ""
        return self._host.shell_host_presenter.internalize_property_path(
            property_spec.label,
            current_path,
            node_type_id=node.type_id,
            property_key=property_spec.key,
            node_id=node.node_id,
            node_title=node.title,
            node_type=getattr(spec, "display_name", "") or node.type_id,
        )

    def pick_selected_node_property_color(self, key: str, current_value: str) -> str:
        property_spec = self._selected_node_property_spec(key)
        if property_spec is None or property_inspector_editor(property_spec) != "color":
            return ""
        return self._host.shell_host_presenter.pick_property_color_dialog(property_spec.label, current_value)

    def pick_node_property_color(self, node_id: str, key: str, current_value: str) -> str:
        property_spec = self._node_property_spec(node_id, key)
        if property_spec is None or str(property_spec.inline_editor).strip() != "color":
            return ""
        return self._host.shell_host_presenter.pick_property_color_dialog(property_spec.label, current_value)

    def set_selected_port_exposed(self, key: str, exposed: bool) -> None:
        self._host.workspace_edit_controller.set_selected_port_exposed(key, exposed)

    def set_selected_port_label(self, key: str, label: str) -> bool:
        return bool(self._host.workspace_edit_controller.set_selected_port_label(key, label))

    def set_selected_node_collapsed(self, collapsed: bool) -> None:
        self._host.workspace_edit_controller.set_selected_node_collapsed(collapsed)

    def request_ungroup_selected_nodes(self) -> bool:
        return bool(self._host.workspace_edit_controller.ungroup_selected_nodes())

    def request_add_selected_subnode_pin(self, direction: str) -> str:
        result = self._host.workspace_edit_controller.request_add_selected_subnode_pin(direction)
        return str(result.payload or "")

    def request_remove_selected_port(self, key: str) -> bool:
        return bool(self._host.workspace_edit_controller.request_remove_selected_port(key).payload)


__all__ = ["ShellInspectorPresenter"]
