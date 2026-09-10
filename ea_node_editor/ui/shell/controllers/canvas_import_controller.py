# Purpose: Own external paste/drop choices, destination validation, and project artifact staging.
# Map: feature_routes/clipboard_undo_redo_mutation_history.md
# Tests: tests/test_canvas_import_controller.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QDialog, QMessageBox

from ea_node_editor.graph.hierarchy import scope_parent_id
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.ui.shell.canvas_import_dialog import CanvasImportDialog
from ea_node_editor.ui.shell.clipboard_paste_nodes import (
    CanvasImportChoice, CanvasImportSnapshot, CanvasImportSource, ClipboardPasteItem,
    capture_canvas_drop, capture_canvas_mime_data, classify_canvas_import,
    clipboard_paste_items_signature,
)
from ea_node_editor.ui.shell.controllers.dialog_support import resolve_dialog_parent
from ea_node_editor.ui_qml.graph_scene_mutation.node_creation_batch import NodeCreationRequest


@dataclass(frozen=True, slots=True)
class _Destination:
    model: Any
    project: Any
    workspace: Any
    scope: tuple[str, ...]
    scope_nodes: tuple[Any, ...]
    position: tuple[float, float]


class CanvasImportController:
    def __init__(self, host, *, effects) -> None:
        self._host = host
        self._effects = effects
        self._last_paste_signature = ""
        self._paste_count = 0
        self._pending_drop: CanvasImportSnapshot | None = None
        self._closed = False
        self._active_dialog: CanvasImportDialog | None = None

    def shutdown(self) -> None:
        self._closed = True
        self._pending_drop = None
        if self._active_dialog is not None and not sip.isdeleted(self._active_dialog):
            self._active_dialog.reject()

    def capture_native_drop(self, mime_data) -> None:
        snapshot = capture_canvas_mime_data(mime_data)
        self._pending_drop = snapshot
        QTimer.singleShot(0, lambda: self._expire_drop(snapshot))

    def _expire_drop(self, snapshot: CanvasImportSnapshot) -> None:
        if self._pending_drop is snapshot:
            self._pending_drop = None

    def paste(self, mime_data) -> bool:
        snapshot = capture_canvas_mime_data(mime_data)
        return self._import(snapshot, self._destination(self._viewport_center()), paste=True)

    def drop(self, urls, text: str, html: str, x: float, y: float) -> bool:
        snapshot = self._pending_drop
        self._pending_drop = None
        if snapshot is None:
            snapshot = capture_canvas_drop(urls, text=text, html=html)
        return self._queue_drop(snapshot, x, y)

    def drop_local_path(self, path: str, is_folder: bool, x: float, y: float) -> bool:
        return self._queue_drop(capture_canvas_drop([path], folder_hints=[is_folder]), x, y)

    def _queue_drop(self, snapshot: CanvasImportSnapshot, x: float, y: float) -> bool:
        destination = self._destination((float(x), float(y)))
        if destination is None or not classify_canvas_import(snapshot):
            return False
        # Release the native OS drag before opening any modal widget. Both the
        # payload and destination are owned values captured during dispatch.
        QTimer.singleShot(0, lambda: self._import(snapshot, destination, paste=False))
        return True

    def _viewport_center(self) -> tuple[float, float]:
        view = self._host.view
        center = view.mapToScene(view.viewport().rect().center())
        return (float(center.x()), float(center.y()))

    def _destination(self, position: tuple[float, float]) -> _Destination | None:
        parent = resolve_dialog_parent(self._host)
        if (self._closed or getattr(self._host, "_shell_teardown_started", False)
                or (parent is not None and sip.isdeleted(parent))):
            return None
        model = self._host.model
        project = model.project
        workspace_id = self._host.workspace_manager.active_workspace_id()
        workspace = project.workspaces.get(workspace_id)
        if workspace is None or self._host.scene.workspace_id != workspace_id:
            return None
        scope = tuple(self._host.scene.active_scope_path)
        return _Destination(model, project, workspace, scope,
                            tuple(workspace.nodes.get(node_id) for node_id in scope), position)

    def _destination_valid(self, destination: _Destination) -> bool:
        current = self._destination(destination.position)
        return bool(
            current is not None and current.model is destination.model
            and current.project is destination.project and current.workspace is destination.workspace
            and current.scope == destination.scope
            and all(node is not None and node is old
                    for node, old in zip(current.scope_nodes, destination.scope_nodes))
        )

    def unavailable_reason(self, choice: CanvasImportChoice) -> str:
        if choice.item is None or self._host.registry.spec_or_none(choice.item.type_id) is not None:
            return ""
        return f"{choice.label} is unavailable. Enable its node package or add-on to use it."

    def _choose(self, sources: tuple[CanvasImportSource, ...]) -> tuple[str, ...] | None:
        dialog = CanvasImportDialog(sources, self.unavailable_reason, resolve_dialog_parent(self._host))
        self._active_dialog = dialog
        try:
            return dialog.selected_keys() if dialog.exec() == QDialog.DialogCode.Accepted else None
        finally:
            self._active_dialog = None
            if not sip.isdeleted(dialog):
                dialog.deleteLater()

    def _report_failures(self, failures: list[str]) -> None:
        if failures:
            QMessageBox.warning(resolve_dialog_parent(self._host), "Add to Canvas", "\n\n".join(failures))

    def _import(self, snapshot: CanvasImportSnapshot, destination: _Destination | None, *, paste: bool) -> bool:
        sources = classify_canvas_import(snapshot)
        if not sources or destination is None or not self._destination_valid(destination):
            return False
        graphics = self._host.app_preferences_controller.graphics_settings()
        ask = graphics.get("interaction", {}).get("canvas_import_mode", "automatic") == "ask"
        keys = self._choose(sources) if ask else tuple(source.detected_choice for source in sources)
        if keys is None or not self._destination_valid(destination):
            return False
        choices = tuple(source.choice(key) for source, key in zip(sources, keys))
        signature = clipboard_paste_items_signature(tuple(choice.item for choice in choices if choice.item is not None))
        paste_count = self._paste_count if paste and signature == self._last_paste_signature else 0
        requests: list[NodeCreationRequest] = []
        labels: list[str] = []
        failures: list[str] = []
        for source, choice in zip(sources, choices):
            if choice.item is None:
                continue
            reason = self.unavailable_reason(choice)
            if reason:
                failures.append(f"{source.label}: {reason}")
                continue
            offset = 40.0 * (paste_count + len(requests))
            requests.append(self._creation_request(
                choice.item, destination.position[0] + offset, destination.position[1] + offset,
                scope_parent_id(destination.scope),
            ))
            labels.append(source.label)
        created = []
        if requests:
            results = self._host.scene.command_bridge.create_nodes_batch(tuple(requests))
            for label, result in zip(labels, results):
                if result.node_id:
                    created.append(result.node_id)
                else:
                    failures.append(f"{label}: {result.error}")
        if created:
            self._host.scene.clearSelection()
            for index, node_id in enumerate(created):
                self._host.scene.select_node(node_id, additive=index > 0)
            if paste:
                self._last_paste_signature = signature
                self._paste_count = paste_count + 1
            self._effects.after_fragment_pasted()
        self._report_failures(failures)
        return bool(created)

    def _creation_request(self, item: ClipboardPasteItem, x: float, y: float, parent_node_id: str | None) -> NodeCreationRequest:
        artifact = item.artifact
        owned_refs: list[str] = []

        def after_create(node, mutations) -> None:
            controller = self._host.project_session_controller
            ref = controller.stage_node_artifact_bytes(
                data=artifact.data, filename=artifact.filename, mime_type=artifact.mime_type,
                artifact_prefix=artifact.artifact_prefix, subdirectory=artifact.subdirectory,
                artifact_kind=artifact.artifact_kind, node_id=node.node_id,
            )
            if not ref:
                raise RuntimeError("Could not save the internal project copy.")
            owned_refs.append(ref)
            mutations.set_node_properties(node.node_id, {**item.properties, artifact.property_key: ref})

        def on_failure() -> None:
            if owned_refs:
                controller = self._host.project_session_controller
                store = controller.project_artifact_store()
                store.discard_staged_entries(owned_refs)
                controller.replace_project_artifact_store(store)

        return NodeCreationRequest(
            item.type_id, x, y, parent_node_id,
            properties={} if artifact else dict(item.properties),
            exposed_ports={"source": False} if item.type_id == MEDIA_PANEL_TYPE_ID else None,
            after_create=after_create if artifact else None,
            on_failure=on_failure if artifact else None,
        )
