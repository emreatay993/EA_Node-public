# Purpose: Own graph-host cursor, style, preview, and local-file actions.
# Map: feature_routes/graph_actions_and_context_menus.md
# Tests: tests/test_graph_canvas_host_presenter.py

from __future__ import annotations

import copy
import json
from typing import Any

from PyQt6.QtCore import QObject, Qt, QUrl
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QInputDialog

from ea_node_editor.graph.effective_ports import port_kind
from ea_node_editor.passive_style_normalization import (
    normalize_flow_edge_style_payload,
    normalize_passive_node_style_payload,
)
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
from ea_node_editor.platform_open import open_path_with_app_chooser, open_path_with_default_handler
from ea_node_editor.ui.media_preview_provider import describe_local_image
from ea_node_editor.ui.mail_preview_provider import describe_mail_preview
from ea_node_editor.ui.pdf_preview_provider import describe_pdf_preview
from ea_node_editor.ui.passive_style_presets import normalize_passive_style_presets
from ea_node_editor.ui.tabular_preview_async import TabularPreviewWorkerPool
from ea_node_editor.ui.tabular_preview_provider import TabularPreviewProvider

from .contracts import _GraphCanvasHostPresenterHostProtocol, _presenter_parent


_UNSET = object()
_PASSIVE_NODE_STYLE_CLIPBOARD_KIND = "passive-node-style"
_FLOW_EDGE_STYLE_CLIPBOARD_KIND = "flow-edge-style"
_STYLE_CLIPBOARD_APP_PROPERTY = "eaNodeEditorStyleClipboard"


class GraphCanvasHostPresenter(QObject):
    def __init__(
        self,
        host: _GraphCanvasHostPresenterHostProtocol,
        *,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(_presenter_parent(host, parent))
        self._host = host
        self._tabular_preview_provider = TabularPreviewProvider(
            project_context_provider=self._project_context,
        )
        self._tabular_preview_worker_pool = TabularPreviewWorkerPool(self)
        self._tabular_preview_worker_pool.job_finished.connect(self._on_tabular_preview_job_finished)
        self._tabular_preview_errors: dict[str, str] = {}

    def shutdown(self) -> None:
        self._tabular_preview_worker_pool.shutdown()
        self._tabular_preview_errors.clear()

    def request_navigate_scope_parent(self) -> bool:
        return bool(self._host.search_scope_controller.navigate_scope(self._host.scene.navigate_scope_parent))

    def request_navigate_scope_root(self) -> bool:
        return bool(self._host.search_scope_controller.navigate_scope(self._host.scene.navigate_scope_root))

    def set_graph_cursor_shape(self, cursor_shape: int) -> None:
        try:
            resolved_cursor = Qt.CursorShape(int(cursor_shape))
        except ValueError:
            resolved_cursor = Qt.CursorShape.ArrowCursor
        self._apply_graph_cursor(resolved_cursor)

    def clear_graph_cursor_shape(self) -> None:
        quick_widget = getattr(self._host, "quick_widget", None)
        if quick_widget is None:
            return
        quick_widget.unsetCursor()
        quick_window = quick_widget.quickWindow()
        if quick_window is not None:
            quick_window.unsetCursor()

    def _apply_graph_cursor(self, cursor_shape: Qt.CursorShape) -> None:
        quick_widget = getattr(self._host, "quick_widget", None)
        if quick_widget is None:
            return
        cursor = QCursor(cursor_shape)
        quick_widget.setCursor(cursor)
        quick_window = quick_widget.quickWindow()
        if quick_window is not None:
            quick_window.setCursor(cursor)

    def describe_pdf_preview(self, source: str, page_number: Any) -> dict[str, Any]:
        return describe_pdf_preview(source, page_number)

    def describe_image_preview(self, source: str) -> dict[str, Any]:
        return describe_local_image(source)

    def describe_mail_preview(self, source: str) -> dict[str, Any]:
        return describe_mail_preview(source)

    def open_local_file_source(self, source: str, chooser: bool = False) -> dict[str, Any]:
        project_path, project_metadata = self._project_context()
        resolver = ProjectArtifactResolver(
            project_path=project_path,
            project_metadata=project_metadata,
        )
        path = resolver.resolve_to_path(str(source or "").strip())
        if path is None or not path.exists() or not path.is_file():
            return {
                "success": False,
                "path": "",
                "error": {
                    "code": "missing_file",
                    "message": "The selected source file could not be opened.",
                },
            }
        opener = open_path_with_app_chooser if bool(chooser) else open_path_with_default_handler
        if not opener(path):
            return {
                "success": False,
                "path": str(path),
                "error": {
                    "code": "open_failed",
                    "message": f'Could not open "{path}".',
                },
            }
        return {"success": True, "path": str(path), "error": {}}

    def describe_tabular_preview(
        self,
        properties_or_source: dict[str, Any] | str,
        request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._tabular_preview_provider.describe_preview(
            properties_or_source,
            request,
            mode="inline",
        )
        if isinstance(payload, dict) and payload.get("state") == "loading":
            job_key = self._tabular_preview_job_key(properties_or_source, request)
            error = self._tabular_preview_errors.get(job_key, "")
            if error:
                return self._tabular_error_payload(error)
            # Cold cache: resolve on the worker (where conversion is allowed);
            # the provider's session caches absorb the result so the surface's
            # next describe is a warm hit.
            self._schedule_tabular_preview_build(properties_or_source, request, job_key=job_key)
        return payload

    def _schedule_tabular_preview_build(
        self,
        properties_or_source: dict[str, Any] | str,
        request: dict[str, Any] | None,
        *,
        job_key: str | None = None,
    ) -> None:
        properties_snapshot = copy.deepcopy(properties_or_source)
        request_snapshot = copy.deepcopy(request)
        normalized_job_key = job_key or self._tabular_preview_job_key(properties_snapshot, request_snapshot)

        def build() -> None:
            self._tabular_preview_provider.describe_preview(
                properties_snapshot,
                request_snapshot,
                mode="inline",
            )

        if self._tabular_preview_worker_pool.schedule(normalized_job_key, build):
            self._tabular_preview_errors.pop(normalized_job_key, None)

    @staticmethod
    def _tabular_preview_job_key(
        properties_or_source: dict[str, Any] | str,
        request: dict[str, Any] | None,
    ) -> str:
        return "inline:" + json.dumps(
            {"properties": properties_or_source, "request": request},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    def _on_tabular_preview_job_finished(self, job_key: str, error: str) -> None:
        if error:
            self._tabular_preview_errors[str(job_key)] = str(error)
        else:
            self._tabular_preview_errors.pop(str(job_key), None)

    @staticmethod
    def _tabular_error_payload(message: str) -> dict[str, Any]:
        return {
            "state": "error",
            "content_kind": "tabular",
            "preview_kind": "",
            "message": str(message or "Tabular preview is unavailable."),
            "error": {
                "code": "tabular_inline_unavailable",
                "message": str(message or "Tabular preview is unavailable."),
                "recoverable": True,
            },
        }

    def resolve_local_file_source_url(self, source: str) -> str:
        project_path, project_metadata = self._project_context()
        resolver = ProjectArtifactResolver(
            project_path=project_path,
            project_metadata=project_metadata,
        )
        path = resolver.resolve_to_path(str(source or "").strip())
        if path is None:
            return ""
        return QUrl.fromLocalFile(str(path)).toString()

    def _project_context(self) -> tuple[str | None, dict[str, Any] | None]:
        project_path = str(getattr(self._host, "project_path", "") or "").strip() or None
        model = getattr(self._host, "model", None)
        project = getattr(model, "project", None)
        metadata = getattr(project, "metadata", None)
        return project_path, dict(metadata) if isinstance(metadata, dict) else None

    def _active_workspace_data(self):
        workspace_id = self._host.workspace_manager.active_workspace_id()
        return self._host.model.project.workspaces.get(workspace_id)

    def _passive_node_context(self, node_id: str):
        workspace = self._active_workspace_data()
        if workspace is None:
            return None
        normalized_node_id = str(node_id).strip()
        if not normalized_node_id:
            return None
        node = workspace.nodes.get(normalized_node_id)
        if node is None:
            return None
        spec = self._host.registry.get_spec(node.type_id)
        if str(spec.runtime_behavior or "").strip().lower() != "passive":
            return None
        return node, spec, workspace

    def _flow_edge_context(self, edge_id: str):
        workspace = self._active_workspace_data()
        if workspace is None:
            return None
        normalized_edge_id = str(edge_id).strip()
        if not normalized_edge_id:
            return None
        edge = workspace.edges.get(normalized_edge_id)
        if edge is None:
            return None
        source_node = workspace.nodes.get(edge.source_node_id)
        target_node = workspace.nodes.get(edge.target_node_id)
        if source_node is None or target_node is None:
            return None
        source_spec = self._host.registry.get_spec(source_node.type_id)
        target_spec = self._host.registry.get_spec(target_node.type_id)
        try:
            source_kind = port_kind(
                node=source_node,
                spec=source_spec,
                workspace_nodes=workspace.nodes,
                port_key=edge.source_port_key,
            )
            target_kind = port_kind(
                node=target_node,
                spec=target_spec,
                workspace_nodes=workspace.nodes,
                port_key=edge.target_port_key,
            )
        except KeyError:
            return None
        if source_kind != "flow" or target_kind != "flow":
            return None
        return edge, workspace

    def _project_passive_style_presets(self) -> dict[str, list[dict[str, Any]]]:
        self._host.project_session_controller.ensure_project_metadata_defaults()
        metadata = self._host.model.project.metadata if isinstance(self._host.model.project.metadata, dict) else {}
        ui = metadata.get("ui", {}) if isinstance(metadata.get("ui"), dict) else {}
        normalized = normalize_passive_style_presets(ui.get("passive_style_presets"))
        if ui.get("passive_style_presets") != normalized:
            updated_ui = dict(ui)
            updated_ui["passive_style_presets"] = normalized
            updated_metadata = dict(metadata)
            updated_metadata["ui"] = updated_ui
            self._host.model.project.replace_metadata(updated_metadata)
        return normalize_passive_style_presets(normalized)

    def _set_project_passive_style_presets(
        self,
        *,
        node_presets: Any = _UNSET,
        edge_presets: Any = _UNSET,
    ) -> None:
        current = self._project_passive_style_presets()
        updated = {
            "node_presets": current["node_presets"],
            "edge_presets": current["edge_presets"],
        }
        if node_presets is not _UNSET:
            updated["node_presets"] = normalize_passive_style_presets(
                {"node_presets": node_presets, "edge_presets": current["edge_presets"]}
            )["node_presets"]
        if edge_presets is not _UNSET:
            updated["edge_presets"] = normalize_passive_style_presets(
                {"node_presets": updated["node_presets"], "edge_presets": edge_presets}
            )["edge_presets"]
        if updated == current:
            return
        metadata = self._host.model.project.metadata if isinstance(self._host.model.project.metadata, dict) else {}
        ui = metadata.get("ui", {}) if isinstance(metadata.get("ui"), dict) else {}
        updated_ui = dict(ui)
        updated_ui["passive_style_presets"] = updated
        updated_metadata = dict(metadata)
        updated_metadata["ui"] = updated_ui
        self._host.model.project.replace_metadata(updated_metadata)
        self._host.project_session_controller.persist_session()
        self._host.project_meta_changed.emit()

    def edit_passive_node_style(self, node_id: str) -> dict[str, Any] | None:
        context = self._passive_node_context(node_id)
        if context is None:
            return None
        node, _spec, _workspace = context
        from ea_node_editor.ui.dialogs import PassiveNodeStyleDialog

        user_presets = self._project_passive_style_presets()["node_presets"]
        dialog = PassiveNodeStyleDialog(
            initial_style=node.visual_style,
            parent=self._host,
            user_presets=user_presets,
        )
        result = dialog.exec()
        updated_user_presets = dialog.user_presets()
        if updated_user_presets != user_presets:
            self._set_project_passive_style_presets(node_presets=updated_user_presets)
        if result != dialog.DialogCode.Accepted:
            return None
        return dialog.node_style()

    def edit_flow_edge_style(self, edge_id: str) -> dict[str, Any] | None:
        context = self._flow_edge_context(edge_id)
        if context is None:
            return None
        edge, _workspace = context
        from ea_node_editor.ui.dialogs import FlowEdgeStyleDialog

        user_presets = self._project_passive_style_presets()["edge_presets"]
        dialog = FlowEdgeStyleDialog(
            initial_style=edge.visual_style,
            parent=self._host,
            user_presets=user_presets,
        )
        result = dialog.exec()
        updated_user_presets = dialog.user_presets()
        if updated_user_presets != user_presets:
            self._set_project_passive_style_presets(edge_presets=updated_user_presets)
        if result != dialog.DialogCode.Accepted:
            return None
        return dialog.edge_style()

    def _write_style_clipboard(self, *, kind: str, style: dict[str, Any]) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.setProperty(
            f"{_STYLE_CLIPBOARD_APP_PROPERTY}:{str(kind).strip()}",
            json.dumps(
                {
                    "kind": str(kind),
                    "version": 1,
                    "style": copy.deepcopy(style),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )

    def _read_style_clipboard(self, *, kind: str) -> dict[str, Any] | None:
        app = QApplication.instance()
        if app is None:
            return None
        return self._normalize_style_clipboard_payload(
            app.property(f"{_STYLE_CLIPBOARD_APP_PROPERTY}:{str(kind).strip()}"),
            kind=kind,
        )

    @staticmethod
    def _normalize_style_clipboard_payload(payload: Any, *, kind: str) -> dict[str, Any] | None:
        if isinstance(payload, str):
            raw_text = payload.strip()
            if not raw_text:
                return None
            try:
                payload = json.loads(raw_text)
            except ValueError:
                return None
        if not isinstance(payload, dict) or str(payload.get("kind", "")).strip() != str(kind):
            return None
        style = payload.get("style")
        if kind == _PASSIVE_NODE_STYLE_CLIPBOARD_KIND:
            return normalize_passive_node_style_payload(style)
        if kind == _FLOW_EDGE_STYLE_CLIPBOARD_KIND:
            return normalize_flow_edge_style_payload(style)
        return None

    def request_edit_flow_edge_style(self, edge_id: str) -> bool:
        style = self.edit_flow_edge_style(edge_id)
        if style is None:
            return False
        self._host.scene.set_edge_visual_style(edge_id, style)
        return True

    def request_edit_flow_edge_label(self, edge_id: str) -> bool:
        context = self._flow_edge_context(edge_id)
        if context is None:
            return False
        edge, _workspace = context
        label, accepted = QInputDialog.getText(
            self._host,
            "Edit Flow Edge Label",
            "Label:",
            text=str(edge.label or ""),
        )
        if not accepted:
            return False
        self._host.scene.set_edge_label(edge_id, label)
        return True

    def request_reset_flow_edge_style(self, edge_id: str) -> bool:
        if self._flow_edge_context(edge_id) is None:
            return False
        self._host.scene.clear_edge_visual_style(edge_id)
        return True

    def request_copy_flow_edge_style(self, edge_id: str) -> bool:
        context = self._flow_edge_context(edge_id)
        if context is None:
            return False
        edge, _workspace = context
        self._write_style_clipboard(
            kind=_FLOW_EDGE_STYLE_CLIPBOARD_KIND,
            style=normalize_flow_edge_style_payload(edge.visual_style),
        )
        return True

    def request_paste_flow_edge_style(self, edge_id: str) -> bool:
        if self._flow_edge_context(edge_id) is None:
            return False
        style = self._read_style_clipboard(kind=_FLOW_EDGE_STYLE_CLIPBOARD_KIND)
        if style is None:
            return False
        self._host.scene.set_edge_visual_style(edge_id, style)
        return True

    def request_remove_edge(self, edge_id: str) -> bool:
        result = self._host.workspace_edit_controller.request_remove_edge(edge_id)
        return bool(result.payload)

    def request_edit_passive_node_style(self, node_id: str) -> bool:
        style = self.edit_passive_node_style(node_id)
        if style is None:
            return False
        self._host.scene.set_node_visual_style(node_id, style)
        return True

    def request_reset_passive_node_style(self, node_id: str) -> bool:
        if self._passive_node_context(node_id) is None:
            return False
        self._host.scene.clear_node_visual_style(node_id)
        return True

    def request_copy_passive_node_style(self, node_id: str) -> bool:
        context = self._passive_node_context(node_id)
        if context is None:
            return False
        node, _spec, _workspace = context
        self._write_style_clipboard(
            kind=_PASSIVE_NODE_STYLE_CLIPBOARD_KIND,
            style=normalize_passive_node_style_payload(node.visual_style),
        )
        return True

    def request_paste_passive_node_style(self, node_id: str) -> bool:
        if self._passive_node_context(node_id) is None:
            return False
        style = self._read_style_clipboard(kind=_PASSIVE_NODE_STYLE_CLIPBOARD_KIND)
        if style is None:
            return False
        self._host.scene.set_node_visual_style(node_id, style)
        return True

    def request_propagate_passive_node_style(self, node_id: str) -> bool:
        if self._passive_node_context(node_id) is None:
            return False
        propagate = getattr(self._host.scene, "propagate_passive_node_style", None)
        if not callable(propagate):
            return False
        return bool(propagate(node_id))

    def request_rename_node(self, node_id: str) -> bool:
        result = self._host.workspace_edit_controller.request_rename_node(node_id)
        return bool(result.payload)

    def request_ungroup_node(self, node_id: str) -> bool:
        normalized_node_id = str(node_id).strip()
        if not normalized_node_id:
            return False
        self._host.scene.select_node(normalized_node_id)
        return bool(self._host.workspace_edit_controller.ungroup_selected_nodes())

    def request_remove_node(self, node_id: str) -> bool:
        result = self._host.workspace_edit_controller.request_remove_node(node_id)
        return bool(result.payload)


__all__ = ["GraphCanvasHostPresenter"]
